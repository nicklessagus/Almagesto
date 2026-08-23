"""Genera notas markdown de la bóveda a partir de lo bajado por los otros scripts.

Uso:
    python scripts/make_notes.py <slug> [--all] [--force]        # estrella
    python scripts/make_notes.py --topic <slug> [--all] [--force]  # tema (concept + papers)
    python scripts/make_notes.py --web <clave> --concept <c> [--url … | --pending …] [--slug-hint <s>]
    python scripts/make_notes.py --restamp-pdf-links             # backfill del link PDF, sin slug
    python scripts/make_notes.py --restamp-headers               # backfill de la cabecera, sin slug
    python scripts/make_notes.py --migrate-disputes              # migración #71 de disputes, sin slug

- vault/wiki/stars/<slug>.md            : ficha índice de la estrella (frontmatter + Dataview).
- vault/wiki/concepts/<area>/<c>.md     : stub del concept durable de un tema (--topic).
- vault/wiki/papers/<bibcode>.md        : una nota por paper relevante (metadata + placeholders LLM).

Idempotente: NO pisa notas existentes (protege la extracción LLM) salvo --force. Las
excepciones NUNCA tocan la extracción LLM; todas menos la última son además quirúrgicas (editan
líneas puntuales, no re-serializan): (a) add-only, en una nota de paper
que ya existía mergea los seeds del ingest actual (`stars` / `thesis_links`) si faltan —
retro-linkeo, ver merge_frontmatter_list; (b) en una ficha/concept que ya existía re-estampa
el apéndice máquina "## Excluidos por el filtro" con el ads.json vigente — ver stamp_excluded
(#35: el sub-modo re-clasificar de maintain lo necesita sin pisar la síntesis); (c) en una
nota de paper que ya existía re-estampa el link `[📄 PDF]` de la línea de cabecera desde el
frontmatter `pdf:` — ver stamp_pdf_link (#47: la cabecera es metadata derivada, no contenido
de escritura única); (d) en una ficha/concept que ya existía re-estampa la línea de puntero
`> _Búsqueda …_` de la cabecera desde `vault/config/registro/<slug>.yaml` — ver stamp_search_line
(#64). Aparte, `stamp_fulltext` (lo llama extract_fulltext al cerrar) estampa
`fulltext`/`fulltext_source`/`pdf_source` sobre notas ya existentes. Backfill masivo del link PDF:
`python scripts/make_notes.py --restamp-pdf-links` (sin slug).
(e) `--migrate-disputes` (#71) es la ÚNICA que no es quirúrgica: cambia la estructura del
frontmatter, así que lo re-serializa — por eso toca sólo las fichas con disputas del schema viejo y
el cuerpo se conserva byte a byte. Ver migrate_disputes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import yaml

import lib_config as cfg

EXCLUDED_TOP_N = 10  # cuántos no-core mostrar en la tabla de excluidos (top por citas)


def fm(d: dict) -> str:
    """Frontmatter YAML entre --- ---."""
    body = yaml.safe_dump(d, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"---\n{body}---\n"


def safe_name(bibcode: str) -> str:
    return bibcode.replace("/", "_")


def _txt_provenance(path) -> str:
    """Provenance de un .txt por la marca de su primera línea: `ocr` (rescate tesseract —
    citable con salvedad), `web` (snapshot defuddle) o `pdftotext` (extracción determinista,
    sin marca). Un solo lugar de verdad para leer el header."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        first = fh.readline()
    return ("ocr" if first.startswith(cfg.FULLTEXT_OCR_MARK)
            else "web" if first.startswith(cfg.FULLTEXT_WEB_MARK)
            else "pdftotext")


def pdf_source_info(slug: str | None, stem: str) -> tuple[str | None, str | None]:
    """(pdf_source, eprint_version) de un paper: de QUÉ DOCUMENTO salió el PDF/texto (#57), no con
    qué método se extrajo (eso es `fulltext_source`). Valores: `eprint` (arXiv — puede ser un v1
    pre-referato), `ads` (escaneo alojado por ADS), `publisher` (versión publicada), `web`
    (snapshot) o None si no se sabe.

    Precedencia: manda la **verdad de disco** —la marca que arXiv estampa en cada página, visible
    en el .txt—, porque no depende de que el fetcher haya dejado registro y por eso funciona
    retroactivamente sobre un corpus ya bajado (y porque un ADS_PDF que sirve el eprint ES el
    eprint, diga lo que diga la rama). Sin marca, vale lo que registró el fetcher de la corrida
    (`build/<slug>/pdf_source.json`). Sin ninguna de las dos: None (desconocido, no "publicado":
    afirmar de más acá sería peor que no saber)."""
    if not slug:
        return None, None
    txt = cfg.FULLTEXT / slug / f"{stem}.txt"
    if txt.exists():
        if _txt_provenance(txt) == "web":
            return "web", None
        head = txt.read_text(encoding="utf-8", errors="replace")[:cfg.ARXIV_STAMP_SCAN_CHARS]
        ver = cfg.arxiv_stamp(head)
        if ver is not None:
            return "eprint", (ver or None)
    reg = cfg.ROOT / "build" / slug / "pdf_source.json"
    if reg.exists():
        try:
            src = (json.loads(reg.read_text(encoding="utf-8")) or {}).get(stem)
        except ValueError:
            src = None
        if src:
            return src, None
    return None, None


# Calidad de fulltext para desempatar entre copias del mismo paper bajo distintos slugs (#16):
# `pdftotext`/`web` son extracción/snapshot limpios; `ocr` es rescate "citable con salvedad".
# Mayor = mejor; desconocido = 0.
_FULLTEXT_QUALITY = {"pdftotext": 2, "web": 2, "ocr": 1}


def fulltext_info(slug: str | None, stem: str) -> tuple[str | None, str | None]:
    """(ruta relativa, provenance) del fulltext `.txt` de un paper, por VERDAD DE DISCO —
    (None, None) si no hay extracción. `stem` es el nombre en disco (safe_name del bibcode /
    citekey). La provenance sale de la marca en la primera línea del .txt: `ocr` (rescate
    tesseract — citable con salvedad), `web` (snapshot defuddle) o `pdftotext` (extracción
    determinista, sin marca). Es el lado barato del contrato máquina-legible: el consumidor
    lee el .txt, no el PDF."""
    if not slug:
        return None, None
    p = cfg.FULLTEXT / slug / f"{stem}.txt"
    if not p.exists():
        return None, None
    return f"../../raw/fulltext/{slug}/{stem}.txt", _txt_provenance(p)


def stamp_fulltext(dest, stem: str, slug: str | None) -> bool:
    """Estampa/actualiza `fulltext:` + `fulltext_source:` (verdad de disco) en una nota que YA
    existe. Hace falta porque en la cadena ADS el stub nace ANTES que el .txt (make_notes corre
    antes que extract_fulltext, que llama esto al cerrar); de paso migra notas pre-contrato que
    no traen los campos. Edición QUIRÚRGICA a nivel texto (como unpend_note/merge_frontmatter_list):
    sólo esas dos líneas del frontmatter — actualiza las existentes o las inserta tras `pdf:` —,
    nunca la extracción LLM. Sin .txt en disco no des-estampa (la ausencia ya la surface el lint).

    Precedencia declarada + preferencia por calidad (#16): un paper relevante para varios sujetos
    tiene su `.txt` extraído bajo CADA slug (contenido idéntico), pero la nota es una sola. Sin
    esto el campo se repunta al slug que corrió último → ruido de diff y `fulltext_source` que
    alterna según el orden de ejecución. Regla: si la nota ya apunta a un `.txt` que existe en
    disco, el candidato de la corrida en curso sólo lo reemplaza si es de MEJOR calidad
    (`pdftotext`/`web` > `ocr`); en empate gana el primer escritor → re-correr cualquier slug no
    toca la nota. Devuelve True si modificó."""
    rel, src = fulltext_info(slug, stem)
    if rel is None or not dest.exists():
        return False
    text = dest.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end < 0:
        return False
    lines = text[4:end].split("\n")

    # Si ya hay un `fulltext:` válido (apunta a un .txt que existe), decidir quién gana ANTES de
    # estampar: sólo un candidato de calidad estrictamente mayor pisa al ya estampado. En empate
    # (misma calidad, incluido otro slug con el mismo contenido) el existente se queda → idempotente.
    cur_rel = next((ln.split(":", 1)[1].strip().strip("'\"")
                    for ln in lines if ln.startswith("fulltext:")), None)
    if cur_rel and cur_rel not in ("null", "~") and cur_rel != rel:
        cur_path = (dest.parent / cur_rel).resolve()
        if cur_path.exists():
            cur_src = _txt_provenance(cur_path)
            if _FULLTEXT_QUALITY.get(src, 0) <= _FULLTEXT_QUALITY.get(cur_src, 0):
                rel, src = cur_rel, cur_src   # el existente gana → estampá SU provenance

    def upsert(field: str, value: str, anchors: tuple[str, ...]) -> bool:
        want = f"{field}: {value}"
        for i, ln in enumerate(lines):
            if ln.startswith(f"{field}:"):
                if ln == want:
                    return False
                lines[i] = want
                return True
        for anchor in anchors:                       # insertar tras el primer ancla presente
            for i, ln in enumerate(lines):
                if ln.startswith(f"{anchor}:"):
                    lines.insert(i + 1, want)
                    return True
        lines.append(want)
        return True

    changed = upsert("fulltext", rel, ("pdf",))
    changed = upsert("fulltext_source", src, ("fulltext", "pdf")) or changed
    # `pdf_source` viaja con los otros dos porque se conoce en el mismo momento (el .txt ya está en
    # disco) y porque así se estampa RETROACTIVAMENTE en cualquier bóveda ya ingestada: re-correr
    # extract_fulltext alcanza, no hay que re-bajar nada.
    psrc, pver = pdf_source_info(slug, stem)
    if psrc:
        changed = upsert("pdf_source", psrc, ("fulltext_source", "fulltext", "pdf")) or changed
        if pver:
            changed = upsert("eprint_version", pver, ("pdf_source",)) or changed
    if changed:
        dest.write_text("---\n" + "\n".join(lines) + text[end:], encoding="utf-8")
    return changed


PDF_LINK_RE = re.compile(r" · \[📄 PDF\]\([^)]*\)")


def find_header_line(text: str) -> tuple[int, int] | None:
    """(inicio, fin) de la línea de CABECERA de una nota de paper, o None si la nota no tiene una
    que cumpla el contrato. Fuente de verdad ÚNICA de "qué es la cabecera" (#48): la usan
    stamp_pdf_link para re-estampar y el lint para detectar las notas que quedan fuera del
    contrato — si cada uno la definiera por su lado, el detector dejaría de cubrir al fixer.

    Contrato: primera línea del cuerpo, ANTES de la primera sección `## `, que empieza con `· `
    y trae la clave entre backticks (`ADS: \\`bibcode\\`` / `fuente off-ADS · \\`citekey\\``). Las
    líneas de URL/snapshot de las notas off-ADS no la traen, y una línea `· ` dentro de la
    extracción LLM queda fuera por el corte en la primera sección."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    pos = end + len("\n---\n")
    first_sec = text.find("\n## ", pos)
    limit = len(text) if first_sec < 0 else first_sec
    while pos < limit:
        nl = text.find("\n", pos, limit)
        line_end = limit if nl < 0 else nl
        if text[pos:line_end].startswith("· ") and "`" in text[pos:line_end]:
            return pos, line_end
        pos = line_end + 1
    return None


def stamp_pdf_link(dest) -> bool:
    """Re-estampa el link `[📄 PDF]` de la línea de cabecera de una nota de paper EXISTENTE
    según el frontmatter `pdf:` (#47). La cabecera es metadata DERIVADA (como `fulltext:` o el
    apéndice Excluidos), no contenido de escritura única: el link nació en #13 y toda nota
    creada antes —o cuyo PDF llegó DESPUÉS del stub— quedó sin él aunque el frontmatter esté
    sano; el cuerpo no lo miraba nadie hasta el chequeo hermano del lint, #48). Cirugía a
    nivel texto (familia stamp_fulltext): toca SÓLO la línea de cabecera (ver
    find_header_line): agrega el link si falta, corrige la ruta si cambió y lo QUITA si `pdf:`
    es null o apunta a un archivo que ya no existe (drift inverso). Nunca la extracción LLM.
    Idempotente. Devuelve True si modificó."""
    if not dest.exists():
        return False
    text = dest.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end < 0:
        return False
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return False                    # frontmatter roto: lo surface el lint, acá no se toca
    pdf_rel = data.get("pdf")
    # verdad frontmatter + disco: link sólo si el campo apunta a un PDF que existe
    want = (f" · [📄 PDF]({pdf_rel})"
            if pdf_rel and (dest.parent / pdf_rel).resolve().exists() else "")
    span = find_header_line(text)
    if span is None:
        return False                    # cabecera fuera del contrato: no adivinar (lo marca el lint)
    pos, line_end = span
    line = text[pos:line_end]
    new_line = PDF_LINK_RE.sub("", line) + want
    if new_line == line:
        return False
    dest.write_text(text[:pos] + new_line + text[line_end:], encoding="utf-8")
    return True


def restamp_pdf_links() -> int:
    """Backfill #47: barre TODAS las notas de papers y re-estampa el link de cabecera. Para
    el corpus pre-#13 de una instancia (re-correr cadena por cadena sería carísimo y build/
    es scratch que puede no existir); en el flujo normal el re-estampado viaja solo con el
    re-run idempotente de la cadena."""
    notes = sorted(cfg.PAPERS.glob("*.md")) if cfg.PAPERS.exists() else []
    changed = sum(1 for p in notes if stamp_pdf_link(p))
    print(f"papers: {changed} de {len(notes)} re-estampados (link [📄 PDF] ↔ frontmatter `pdf`)")
    return 0


def restamp_headers() -> int:
    """Backfill #69: barre TODAS las fichas y conceptos y les estampa la cabecera si les falta.
    Para el corpus creado antes de que la cabecera existiera (medido en una bóveda real: 21 de 25
    notas sin el aviso de capa LLM). Regenerar con --force sí escribiría la cabecera, pero PISA la
    síntesis LLM, que es el trabajo caro: por eso esto es cirugía y no regeneración."""
    notes = sorted(cfg.STARS.glob("*.md")) if cfg.STARS.exists() else []
    notes += sorted(cfg.CONCEPTS.glob("*/*.md")) if cfg.CONCEPTS.exists() else []
    changed = sum(1 for n in notes if stamp_header(n))
    print(f"cabeceras: {changed} de {len(notes)} estampadas "
          f"(aviso de capa LLM + línea del generador, versión leída del frontmatter)")
    if changed:
        print("  → ahora los estampadores de cabecera (p. ej. el puntero de búsqueda de #64) "
              "pueden actuar sobre esas notas; re-corré la cadena o make_notes del sujeto.")
    return 0


# `field` viejo (dentro de planets[]) → clave del frontmatter con el valor de NEA, para materializar
# la posición `{source: ground_truth}` con su valor real. `existence` no tiene valor numérico: lo que
# NEA sostiene es el `status` del planeta.
LEGACY_FIELD_TO_GT = {"P": "P_days", "K": "K_ms", "e": "e", "msini": "mass_earth",
                      "existence": "status"}


def migrate_disputes(dest) -> bool:
    """Migración #71 de UNA ficha: `planets[].disputes[]` (polo de verdad hardcodeado) → `disputes`
    a nivel nota, con **posiciones explícitas**.

    Cada disputa vieja tenía un solo lado escrito (el paper discrepante, con `alt`); el otro era
    implícito: el valor del frontmatter, o sea NEA. Acá ese lado se **materializa** como
    `{source: ground_truth, value: <el valor que la ficha tiene hoy>}` — que es justamente la
    información que el schema viejo no podía expresar y el consumidor necesita ver ("hay autoridad"
    vs "la bóveda no sabe").

    A diferencia del resto de la familia `--restamp-*`, esto NO es cirugía a nivel línea: cambia la
    ESTRUCTURA del frontmatter, así que se re-serializa. Por eso toca **sólo** las fichas que
    realmente tienen disputas viejas (una bóveda sin disputas no se reescribe) y **nunca** el
    cuerpo: la prosa se conserva byte a byte. Idempotente: sin `planets[].disputes[]` no hace nada."""
    if not dest.exists():
        return False
    text = dest.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end < 0:
        return False
    try:
        front = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        print(f"  ⚠ {dest.name}: frontmatter no parseable — migralo a mano")
        return False
    if not any((pl or {}).get("disputes") for pl in (front.get("planets") or [])):
        return False
    nuevas = list(front.get("disputes") or [])
    for pl in front.get("planets") or []:
        letra = str((pl or {}).get("letter", "")).strip()
        for d in (pl.pop("disputes", None) or []):
            campo = str(d.get("field", "")).strip()
            gt_key = LEGACY_FIELD_TO_GT.get(campo)
            gt_pos = {"source": "ground_truth"}
            if gt_key is not None and pl.get(gt_key) is not None:
                gt_pos["value"] = pl.get(gt_key)
            nueva = {"field": f"{letra}.{campo}" if letra else campo,
                     "posiciones": [{"ref": d.get("ref"), "value": d.get("alt")}, gt_pos]}
            if d.get("note"):
                nueva["note"] = d["note"]
            nuevas.append(nueva)
    # `disputes` va donde vivía la información: justo después de `planets`. Si la ficha ya lo tiene
    # (migración a medias, o disputas nuevas escritas a mano), se respeta su lugar y se acumula.
    # `planets` existe sí o sí: sin él la función ya habría vuelto arriba.
    if "disputes" in front:
        front["disputes"] = nuevas
    else:
        reordenado = {}
        for k, v in front.items():
            reordenado[k] = v
            if k == "planets":
                reordenado["disputes"] = nuevas
        front = reordenado
    dest.write_text(fm(front) + text[end + 5:], encoding="utf-8")
    print(f"  {dest.name}: {len(nuevas)} disputa(s) migradas a posiciones explícitas")
    return True


def migrate_all_disputes() -> int:
    """Backfill #71 sobre toda la bóveda. Ver migrate_disputes para el porqué del alcance."""
    notes = sorted(cfg.STARS.glob("*.md")) if cfg.STARS.exists() else []
    changed = sum(1 for n in notes if migrate_disputes(n))
    print(f"disputas: {changed} de {len(notes)} ficha(s) migradas al schema con posiciones (#71)")
    if changed:
        print("  → el frontmatter se re-serializó (la prosa NO se tocó): revisá el diff antes de "
              "commitear.")
    else:
        print("  → nada que migrar. (El lint NO lee el schema viejo: si queda alguno, lo reporta "
              "como bloqueante en vez de ignorarlo en silencio.)")
    return 0


def parse_year(year) -> int | None:
    """Año tolerante para metadata off-ADS (provista a mano): acepta int, '2020', '2020a'
    (→ 2020); un valor sin año reconocible ('in press') queda null con aviso — la metadata
    de una fuente nunca aborta la cadena."""
    if year in (None, ""):
        return None
    m = re.search(r"(?<!\d)(\d{4})(?!\d)", str(year))   # 4 dígitos no rodeados de dígitos ('2020a' → 2020)
    if m:
        return int(m.group(1))
    print(f"  ⚠ year no numérico: {year!r} → queda null (completalo a mano en la nota si aplica)")
    return None


def parse_int(value, field: str) -> int | None:
    """Entero tolerante para metadata off-ADS: no numérico → null con aviso, no aborta."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        print(f"  ⚠ {field} no numérico: {value!r} → queda null")
        return None


def merge_frontmatter_list(dest, field: str, values: list) -> bool:
    """Retro-linkeo add-only: agrega a la lista `field` del frontmatter de `dest` los `values`
    que falten. Edita el TEXTO en el lugar (no re-serializa el YAML) para preservar byte a byte
    el resto del frontmatter — orden, comentarios y todo lo que haya tocado la extracción LLM.
    Nunca saca ni pisa nada. Devuelve True si modificó el archivo."""
    text = dest.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end < 0:
        return False
    head = text[4:end]
    try:
        data = yaml.safe_load(head) or {}
    except yaml.YAMLError:
        return False
    current = data.get(field) or []
    if not isinstance(current, list):
        return False
    missing = [v for v in values if v not in current]
    if not missing:
        return False
    lines = head.split("\n")
    idx = next((i for i, ln in enumerate(lines) if ln.startswith(f"{field}:")), None)
    if idx is None:
        return False   # campo ausente: no inventar posición (el stub siempre lo trae)
    rest = lines[idx][len(field) + 1:].strip()
    if rest.startswith("[") and rest.endswith("]"):
        # lista inline: `field: []` o `field: [a, b]`
        inner = rest[1:-1].strip()
        items = ([x.strip() for x in inner.split(",")] if inner else []) + missing
        lines[idx] = f"{field}: [{', '.join(items)}]"
    elif rest == "" or rest.startswith("#") or data.get(field) is None:
        # lista en bloque (o campo null): insertar tras el último "- item" existente
        j = idx + 1
        while j < len(lines) and lines[j].lstrip().startswith("- "):
            j += 1
        indent = lines[j - 1][:len(lines[j - 1]) - len(lines[j - 1].lstrip())] if j > idx + 1 else ""
        if rest and not rest.startswith("#"):
            lines[idx] = f"{field}:"                # normaliza un `field: null` explícito
        lines[j:j] = [f"{indent}- {v}" for v in missing]
    else:
        return False   # forma no reconocida (escalar con valor): no tocar
    dest.write_text("---\n" + "\n".join(lines) + text[end:], encoding="utf-8")
    return True


def excluded_table(slug: str) -> str:
    """Tabla breve (snapshot del ingest) de los papers que el clasificador dejó AFUERA (no-core):
    top por citas, con motivo y link a ADS. Es un puntero "por las dudas" para cazar falsos negativos
    y afinar relevance.topics — los no-core NO se bajan ni se fichan. Vacío si no hay ads.json/excluidos.
    Frontera dura OK: son papers reales (bibcode citable) con motivo reproducible, no afirmación suelta."""
    adsfile = cfg.ROOT / "build" / slug / "ads.json"
    if not adsfile.exists():
        return ""
    out = [r for r in json.loads(adsfile.read_text(encoding="utf-8")).get("records", [])
           if not r.get("relevant")]
    if not out:
        return ""
    out.sort(key=lambda r: r.get("citation_count", 0) or 0, reverse=True)
    rows = []
    for r in out[:EXCLUDED_TOP_N]:
        url = f"https://ui.adsabs.harvard.edu/abs/{quote(r.get('bibcode', ''), safe='')}"
        # colapsar espacios/saltos, truncar y RECIÉN escapar (|, []) para no romper el link/tabla
        title = " ".join((r.get("title") or "(sin título)").split())[:70] \
            .replace("|", r"\|").replace("[", r"\[").replace("]", r"\]")
        # motivo REAL persistido por query_ads (`why_excluded`, #30 — cubre también la regla de
        # combinación require/min_topics); fallback a la dicotomía del OR histórico para un
        # ads.json viejo sin el campo (build/ es scratch: puede ser pre-#30)
        motivo = r.get("why_excluded") or (
            "sin tópico" if not r.get("topics") else f"doctype: {r.get('doctype')}")
        rows.append(f"| [{title}]({url}) | {r.get('year') or ''} | {r.get('citation_count') or 0} | {motivo} |")
    extra = len(out) - len(rows)
    tail = f"\n\n_(+ {extra} más excluidos por el filtro)_" if extra > 0 else ""
    return ("\n## Excluidos por el filtro (no-core · snapshot del ingest)\n"
            "> Top por citas de lo que el clasificador dejó afuera (no matchea `relevance.topics`, "
            "no cumple la regla de combinación `require`/`min_topics`, o doctype ruido). **No se bajan "
            "ni se fichan** — esto es un puntero por las dudas. Si ves un falso negativo, ajustá "
            "`relevance.topics` (o la regla de combinación) y re-ingestá con `--force`.\n\n"
            "| Paper | Año | Citas | Motivo |\n|---|---|---|---|\n"
            + "\n".join(rows) + tail + "\n")


EXCLUDED_HEADER = "\n## Excluidos por el filtro"


def stamp_excluded(slug: str, dest) -> bool:
    """Re-estampa el apéndice "Excluidos por el filtro" de una ficha/concept EXISTENTE con el
    ads.json vigente (#35 — sub-modo re-clasificar de maintain: cambió la regla y el snapshot
    del apéndice quedó viejo; regenerar la nota entera con --force pisaría la síntesis LLM).
    Cirugía a nivel texto (familia stamp_fulltext): reemplaza SÓLO la sección estampada por
    máquina —del header del apéndice hasta la sección siguiente o el EOF—, la agrega al final
    si la nota no la tenía, o la QUITA si la corrida vigente ya no excluye nada. Nunca toca la
    prosa LLM. Sin `build/<slug>/ads.json` NO hace nada (build/ es scratch — post-clone o
    limpieza no hay con qué re-estampar, y quitar el apéndice destruiría el snapshot del
    ingest). Idempotente: sin cambios no reescribe. Devuelve True si modificó."""
    if not dest.exists():
        return False
    if not (cfg.ROOT / "build" / slug / "ads.json").exists():
        return False                            # sin corrida vigente: ni re-estampa ni quita
    new = excluded_table(slug)                  # "" si la corrida no dejó excluidos
    text = dest.read_text(encoding="utf-8")
    start = text.find(EXCLUDED_HEADER)
    if start < 0:
        if not new:
            return False
        out = text.rstrip("\n") + "\n" + new
    else:
        nxt = text.find("\n## ", start + 1)
        end = len(text) if nxt < 0 else nxt
        out = text[:start] + new.rstrip("\n") + ("\n" if new else "") + text[end:]
    if out == text:
        return False
    dest.write_text(out, encoding="utf-8")
    return True


GENERATOR_LINE = "> _Generado con Almagesto v"
# Aviso de capa LLM de la cabecera. Vive acá y NO inline en los templates de cuerpo porque lo
# escriben dos caminos —la creación de la nota y el backfill `stamp_header` (#69)— y si divergen, el
# backfill estampa un texto distinto del que promete el README. Un solo lugar de verdad.
LLM_DISCLAIMER = {
    "star": """> ⚠ **Capa LLM — revisar antes de citar.** El ground-truth del frontmatter (NEA/SIMBAD) es auditable, pero
> la prosa (Resumen, Huecos, extracción) la sintetizó un LLM desde las fuentes: trazable por `[[bibcode]]` y
> chequeable con `verify-citations`, que es **juicio de LLM, no prueba**. Verificá contra la fuente antes de
> llevar un dato a un paper/tesis.""",
    "concept": """> ⚠ **Capa LLM — revisar antes de citar.** La síntesis la compiló un LLM desde los papers citados:
> chequeable con `verify-citations`, que es **juicio de LLM, no prueba**. Verificá contra la fuente antes
> de llevar un dato a un paper/tesis.""",
}
SEARCH_LINE_RE = re.compile(r"^> _Búsqueda .*_$\n?", re.M)


# Paso de CONTRASTE cross-paper (#72): la sección que va entre leer los papers y escribir la
# síntesis. Vive acá, compartida por la ficha y el concept, por el mismo motivo que LLM_DISCLAIMER:
# la escriben dos templates y divergirían. Es el paso con más apalancamiento de la cadena y era el
# menos especificado — sin él, tres papers que reportan tres valores distintos terminan en una frase
# con un solo `[[bibcode]]`, y se evapora que los otros dos existen.
# ⛔ La columna que NO está es deliberada: "valor adoptado" sería juicio de LLM en un artefacto que
# se lee como bibliografía, y **decide por el consumidor** — flujo unidireccional de la regla #0.
# Régimen de validez (#74) — SÓLO en conceptos. En una estrella comparás el mismo número medido dos
# veces; en un método, dos papers pueden decir cosas distintas y **estar los dos bien**, porque valen
# bajo condiciones distintas (SNR, muestreo, tamaño de muestra, definición del observable). Por eso
# el modo de falla dominante acá no es "dos números no coinciden" sino **generalizar de más**: el
# paper afirma X bajo condiciones C y el concepto afirma X pelado. `verify-citations` NO lo agarra —
# la afirmación pelada sí está en el paper, así que el fan-out la devuelve `soportada` y la condición
# perdida no la ve ninguna capa. Es el "afirmar de menos" de las tablas truncadas, en versión
# conceptual. La unidad de síntesis de un concepto no es (campo, valor, fuente) sino
# **(afirmación, condiciones bajo las que vale, fuente, rol)**.
REGIMEN = """## Régimen de validez
_(Una fila por afirmación **condicionada**: bajo qué condiciones vale y de dónde sale. Es el destino
de los desacuerdos que `find-contradictions` juzga **`aparente`** —"distinto régimen, distinta
definición, distinta época"—: en una estrella eso se descarta como no-disputa, acá **es el
hallazgo**._
_Distinto del `## Inventario por eje`, que es para el desacuerdo **real bajo las mismas
condiciones**: si dos papers dicen cosas distintas y los dos tienen razón, la fila va acá._
_`Rol` es el `role` de la nota del paper (#73): una **aplicación** acota el régimen de una
**fundacional**, no la contradice._
_El hueco accionable que sale de esta tabla es **"régimen no cubierto"** → a `## Huecos`.)_

| Afirmación | Vale bajo (régimen) | Fuente | Rol |
|---|---|---|---|
|  |  |  |  |
"""


INVENTARIO = """## Inventario por eje
_(Paso de **contraste**, antes de escribir la síntesis: una fila por paper para cada eje —parámetro
o hecho— donde los papers **no coinciden**. Los ejes con acuerdo unánime no entran (misma regla de
poda que la prosa): el inventario existe para lo que está en disputa._
_⛔ **Sin columna "valor adoptado" ni "por qué"**: la bóveda reporta el **estado de la literatura**,
no decide por quien la consume (regla #0). Si hay lectura propia —p. ej. "11.5 d es el armónico de
34 d"— va aparte y marcada `inferencia`._
_Cada fila es una transcripción citada: `verify-citations` la chequea, incluida la **completitud**
(¿hay más papers del corpus que reportan este eje?). Si no hay ningún eje en disputa, borrar la
sección y decirlo en el `log`.)_

| Eje | Paper | Dice | Método / baseline |
|---|---|---|---|
|  |  |  |  |
"""


# Bullets de `## Extracción (LLM)` del stub de nota de paper. Viven acá y NO inline en los dos
# templates de cuerpo —la rama ADS (write_paper_notes) y la off-ADS (write_web_paper_note)— por el
# mismo motivo que LLM_DISCLAIMER: los escriben varios caminos y divergirían. Ramifican por TIPO DE
# SUJETO (#76), como ya ramificaban los seeds del frontmatter: el eje tema/concepto es agnóstico de
# disciplina, así que un tema no puede nacer pidiendo planetas y actividad; y el eje estrella es
# astro por schema (ground-truth NEA) pero sus ejes de CONTENIDO salen del objetivo de la bóveda,
# no de un hardcodeo a "actividad".
_BULLET_METHODS = "- **Métodos:** _(llenar `methods:` del frontmatter con `concepts/methods/`)_"
# El ROL es del paper, no del tipo de sujeto (#73): va en las dos ramas. Sin él, "contrastar dos
# papers" no está definido — fundacional↔aplicación NO es contraste sino instanciación, y tratarlo
# como desacuerdo fabrica disputas falsas. La regex del clasificador no puede inferirlo (clasifica
# TEMA), así que sale de la extracción o no sale.
_BULLET_ROLE = ("- **Rol del paper:** _(`fundacional` introduce el método/mecanismo · `aplicacion` lo "
                "instancia en un caso · `arbitro` reanaliza y resuelve una tensión previa; llenar "
                "`role:` del frontmatter, uno o varios)_")


def objective_lens() -> tuple[list, str]:
    """La LENTE de la bóveda para orientar el stub: (facetas declaradas en `relevance.topics`,
    `short` del objetivo). Es lo único que sabe de qué trata ESTA instancia. Degrada a ([], "")
    si no hay objective.yaml (make_notes corrido suelto, fuera de la cadena): el stub sale
    genérico, nunca inventado."""
    try:
        obj = cfg.load_objective()
    except Exception:
        return [], ""
    facetas = list((obj.get("relevance") or {}).get("topics") or {})
    return facetas, (obj.get("short") or "").strip()


def extraction_block(topic: bool) -> str:
    """Sección `## Extracción (LLM)` del stub de una nota de paper, ramificada por tipo de sujeto
    (#76). Tema → el eje del concept (aporte, mecanismo/ecuación, régimen). Estrella → el
    ground-truth (que es del schema de `stars/`, no del objetivo) y los ejes de la lente. El rol
    del paper (fundacional/aplicación/árbitro) es #73, que define el campo antes que el bullet."""
    facetas, short = objective_lens()
    objetivo = (f"«{short}»: qué aporta, qué hueco deja" if short
                else "relevancia para el objetivo de la bóveda / huecos")
    if topic:
        bullets = [
            "- **Aporte al tema:** _(qué agrega al eje del concept: definición, mecanismo/ecuación, "
            "método, signo)_",
            "- **Régimen de validez:** _(en qué condiciones vale lo que aporta: rango de parámetros, "
            "tipo de dato, supuestos)_",
        ]
    else:
        ejes = f" ({' · '.join(facetas)})" if facetas else ""
        bullets = [
            "- **Ground-truth (planetas / parámetros):** _(P, K, e por planeta; comparar contra "
            "`vault/raw/ground_truth/`)_",
            f"- **Ejes del objetivo{ejes}:** _(qué dice el paper sobre cada eje de la lente; salen "
            "de `relevance.topics` en `objective.yaml`)_",
        ]
    bullets += [_BULLET_METHODS, _BULLET_ROLE, f"- **Para el objetivo:** _({objetivo})_"]
    return "## Extracción (LLM)\n" + "\n".join(bullets) + "\n"


def search_line(slug: str) -> str:
    """Puntero de UNA línea al registro de búsqueda versionado (#64), para la cabecera de la ficha
    o del concept. El registro completo —query efectiva, límites, conteos, versión— vive en
    `vault/config/registro/<slug>.yaml`; acá va sólo lo que el que abre la nota necesita saber sin
    abrir nada: CUÁNDO se buscó y sobre QUÉ universo afirma la nota. "" si no hay registro."""
    b = cfg.load_registro(slug).get("busqueda") or {}
    if not b.get("fecha"):
        return ""
    universo = b.get("n_found") or b.get("n_total")
    partes = [f"> _Búsqueda {b['fecha']}"]
    partes.append(f": {universo} → {b.get('n_core', '?')} core" if universo
                  else f": {b.get('n_core', '?')} core")
    if b.get("n_candidates"):
        partes.append(f" · {b['n_candidates']} sin juzgar")
    if b.get("n_dropped"):
        partes.append(f" · {b['n_dropped']} descartados")
    if b.get("truncated"):
        partes.append(" · ⚠ truncada")
    partes.append(f" · registro en `config/registro/{slug}.yaml`._")
    return "".join(partes) + "\n"


H1_RE = re.compile(r"^# .+$", re.M)


def note_kind(dest) -> str | None:
    """`star` | `concept` según DÓNDE vive la nota (verdad de disco, no heurística sobre el texto).
    None si no es ninguna de las dos (una nota de paper tiene su propio contrato de cabecera, #48)."""
    d = str(dest.resolve())
    if d.startswith(str(cfg.STARS.resolve())):
        return "star"
    if d.startswith(str(cfg.CONCEPTS.resolve())):
        return "concept"
    return None


def stamp_header(dest) -> bool:
    """Backfill de la CABECERA de una ficha/concepto que nació sin ella (#69).

    Por qué hace falta un estampador propio y no alcanza con la familia `stamp_*`: todas ellas
    anclan en `GENERATOR_LINE` y se niegan a actuar si falta (criterio de #48, "no inventamos"),
    que es exactamente la población a arreglar — medido en una bóveda real: 21 de 25 notas sin el
    aviso, y las mismas 21 sin el ancla. Un backfill anclado ahí sería no-op sobre el 100% de los
    casos. Éste ancla en el `# H1`, que toda nota tiene.

    La **versión no se inventa**: sale del `generator` del propio frontmatter, que es la versión con
    la que la nota se creó de verdad. Si la nota es tan vieja que ni eso tiene, la línea va SIN
    versión (mejor sin dato que con uno supuesto). Quirúrgico: inserta después del H1 y no toca una
    línea de la prosa — el blockquote que esas notas ya tienen es texto del LLM, no la cabecera del
    template, y se conserva debajo. Idempotente: si ya hay aviso o ancla, no hace nada."""
    if not dest.exists():
        return False
    kind = note_kind(dest)
    if kind is None:
        return False
    text = dest.read_text(encoding="utf-8")
    if "Capa LLM" in text or GENERATOR_LINE in text:
        return False                                  # ya tiene cabecera: nada que backfillear
    m = H1_RE.search(text)
    if not m:
        return False                                  # sin H1 no hay ancla honesta: no inventamos
    gen = (cfg.split_fm(text) or {}).get("generator")
    linea_gen = (f"> _{gen.replace('Almagesto v', 'Generado con Almagesto v')}._"
                 if isinstance(gen, str) and gen.startswith("Almagesto v")
                 else "> _Cabecera normalizada por Almagesto; la nota no registra con qué versión "
                      "se creó._")
    bloque = f"\n\n{LLM_DISCLAIMER[kind]}\n>\n{linea_gen}"
    out = text[:m.end()] + bloque + text[m.end():]
    dest.write_text(out, encoding="utf-8")
    return True


def stamp_search_line(slug: str, dest) -> bool:
    """Estampa/actualiza el puntero de búsqueda en la cabecera de una nota EXISTENTE (familia
    stamp_fulltext/stamp_excluded: cirugía a nivel texto, nunca toca la prosa LLM). Va justo antes
    de la línea `_Generado con Almagesto v…_` del blockquote de cabecera; si esa ancla no está, la
    cabecera está fuera del contrato y NO se toca nada (mismo criterio que stamp_pdf_link, #48).
    Idempotente: sin cambios no reescribe. Devuelve True si modificó."""
    if not dest.exists():
        return False
    new = search_line(slug)
    text = dest.read_text(encoding="utf-8")
    out = SEARCH_LINE_RE.sub("", text, count=1)      # sacar el puntero viejo (si lo había)
    if new:
        i = out.find(GENERATOR_LINE)
        if i < 0:
            return False                             # cabecera fuera del contrato: no inventamos
        out = out[:i] + new + out[i:]
    if out == text:
        return False
    dest.write_text(out, encoding="utf-8")
    return True


def write_star_note(slug: str, force: bool) -> None:
    name, meta = cfg.star_by_slug(slug)
    dest = cfg.STARS / f"{slug}.md"
    if dest.exists() and not force:
        # la nota no se pisa; sólo se refresca el apéndice máquina con el ads.json vigente (#35)
        stamped = stamp_excluded(slug, dest) | stamp_search_line(slug, dest)
        print(f"  star: {dest.name} ya existe"
              + (" — apéndice Excluidos / puntero de búsqueda re-estampados" if stamped
                 else " (usa --force para regenerar)"))
        return
    gt_file = cfg.GROUND_TRUTH / f"{slug}.json"
    gt = json.loads(gt_file.read_text(encoding="utf-8")) if gt_file.exists() else {"host": {}, "planets": []}
    host = gt.get("host", {})
    # Espejo puro de NEA (#70): un null acá es un null de NEA (pl_rvamp/pl_orbeccen faltan seguido,
    # el caso es normal, no excepcional) y NO se rellena con el valor de un paper — ése va al cuerpo
    # con su `[[bibcode]]`, o a `disputes[]` si discrepa. Lo vigila el lint.
    planets = [{"letter": p.get("letter"), "P_days": p.get("P_days"),
                "K_ms": p.get("K_ms"), "e": p.get("e"),
                "mass_earth": p.get("mass_earth"),   # masa NEA (M⊕); RV-only ≈ m·sini. Lint valida consistencia.
                "status": p.get("status")}
               for p in gt.get("planets", [])]

    front = {
        "name": name,
        "slug": slug,
        "aliases": meta.get("aliases", []),
        "simbad_id": meta.get("simbad"),
        "spectral_type": host.get("spectral_type"),
        "teff_K": host.get("teff_K"),
        "dist_pc": host.get("dist_pc"),
        # ESPEJO PURO de NEA (#70): si NEA no lo tiene, el campo queda NULL — no se rellena con
        # literatura. El frontmatter es la capa auditable que la cabecera promete; meterle un
        # número extraído por un LLM lo vuelve indistinguible del de NEA y borra esa distinción.
        # El valor de literatura va al CUERPO, citado `[[bibcode]]` (la autosuficiencia se cumple
        # igual: el dato está, con su fuente). Lo vigila el lint.
        "P_rot_days": host.get("st_rotp_days"),
        "activity_indicators_expected": [],           # poblar con extracción LLM
        "planets": planets,
        # Desacuerdos con POSICIONES EXPLÍCITAS (#71), a nivel nota: `field` nombra el eje
        # (`P_rot`, `b.K`, `b.existence`) y cada posición dice quién la sostiene —`ref` un paper, o
        # `source: ground_truth` cuando NEA arbitra—. El schema viejo (dentro de `planets[]`) tenía
        # el polo de verdad hardcodeado y no podía expresar paper↔paper, que es el caso normal
        # cuando NEA calla. Migración: make_notes.py --migrate-disputes.
        "disputes": [],
        "data_local": meta.get("data_local"),
        "methods_applied": {"literature": [], "ours": []},
        "confidence": "medium",          # patrón LLM Wiki; subir a high tras síntesis revisada
        "tags": ["star"],
        "generator": f"Almagesto v{cfg.ALMAGESTO_VERSION}",   # provenance (con qué versión se armó)
    }
    body = f"""{fm(front)}
# {name}

> Ficha índice. El frontmatter de arriba es la fuente de verdad máquina-legible
> (lo leen Obsidian/Dataview y cualquier consumidor de la bóveda); la prosa y los `[[links]]` son la capa humana.
>
{LLM_DISCLAIMER["star"]}
>
> _Generado con Almagesto v{cfg.ALMAGESTO_VERSION}._

## Resumen
_(síntesis por LLM: qué se sabe, qué indicadores deberían correlacionar con actividad para este
tipo espectral, planetas confirmados/dudosos)._

{INVENTARIO}
## Huecos
_(qué falta para que la ficha alcance sola: parámetros sin valor (¿`P_rot`?), señales RV sin árbitro,
indicadores esperados no medidos, métodos no aplicados. Lista corta y accionable — abrir queries para imputar.
El valor que NEA no tiene NO se copia al frontmatter: va acá o en el Resumen, citado `[[bibcode]]`,
o marcado `inferencia` si es lectura propia.)_

## Planetas (ground-truth NASA Exoplanet Archive)
```dataviewjs
const p = dv.current().planets ?? [];
dv.table(["letter","P (d)","K (m/s)","e","M (M⊕)","status"],
  p.map(x => [x.letter, x.P_days, x.K_ms, x.e, x.mass_earth, x.status]));
```

## Papers
```dataview
TABLE year, topics, relevance, citation_count
FROM "wiki/papers"
WHERE contains(stars, "{name}")
SORT citation_count DESC
```

## Métodos aplicados a esta estrella
```dataview
TABLE WITHOUT ID method, file.link, year
FROM "wiki/papers"
WHERE contains(stars, "{name}") AND methods
FLATTEN methods AS method
SORT method ASC
```

## Datos crudos
`{meta.get('data_local')}`
"""
    body += excluded_table(slug)
    # como los otros dos writers (concept y papers): la carpeta puede no existir — git no
    # versiona directorios vacíos, así que una bóveda sin `vault/wiki/stars/` (clon con el
    # scratch limpiado, árbol armado a mano) moría con un traceback de FileNotFound.
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    stamp_search_line(slug, dest)
    print(f"  star: {dest.name} escrito")


def write_concept_note(slug: str, force: bool) -> None:
    """Para temas (ingest-topic): stub del concept durable destino. Idempotente: NO pisa la
    síntesis LLM de un concept ya existente salvo --force (protege la síntesis)."""
    _, meta = cfg.topic_by_slug(slug)
    area = cfg.require_field(meta, "area", slug, "topics.yaml")
    concept = cfg.require_field(meta, "concept", slug, "topics.yaml")
    # Las áreas de concepts/ son ABIERTAS: no se prohíbe ninguna (podés investigar cualquier tema).
    # `concept_areas` (objective.yaml) es sólo una REFERENCIA para distinguir un typo de un área nueva
    # legítima → si el área no está declarada, AVISAR (nunca bloquear) para que un typo no pase mudo.
    # El lint la marca después; si era un área nueva real, agregala a concept_areas para silenciar el aviso.
    if (areas_ref := cfg.load_concept_areas()) and area not in areas_ref:
        print(f"  ⚠ área '{area}' (topic '{slug}') no está en concept_areas (objective.yaml). "
              f"Si es un typo, corregí topics.yaml; si es un área nueva, agregala a la lista. Creo igual.")
    dest = cfg.CONCEPTS / area / f"{concept}.md"
    if dest.exists() and not force:
        # la síntesis no se pisa; sólo se refresca el apéndice máquina con el ads.json vigente (#35)
        stamped = stamp_excluded(slug, dest) | stamp_search_line(slug, dest)
        print(f"  concept: {area}/{concept}.md ya existe"
              + (" — apéndice Excluidos / puntero de búsqueda re-estampados" if stamped
                 else " (no se pisa sin --force; los papers enganchan por thesis_links)"))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    front = {"name": meta.get("title", concept)}
    if area == "hypotheses":          # `status` sólo en hipótesis (schema name,status; ver CLAUDE.md)
        front["status"] = "active"
    front.update({
        "aliases": meta.get("aliases", []),   # sinónimos EN+ES para grep; sembrado del topic, el LLM enriquece
        # Acá la disputa es SIMÉTRICA por definición (#71): no hay valor de frontmatter contra el
        # cual poner un `alt`, así que las posiciones explícitas son la única forma que sirve.
        "disputes": [],
        "tags": [area, "thesis"],
        "confidence": "medium",
        "generator": f"Almagesto v{cfg.ALMAGESTO_VERSION}",   # provenance (con qué versión se armó)
    })
    # Retro-link de la tabla: una ficha-MÉTODO junta además todo paper ya tagueado con el método
    # en `methods:` (aunque no tenga `thesis_links`) — los papers extraídos antes de crear la ficha
    # aparecen solos, sin re-taguear (issue #4a).
    link_pred = f'contains(thesis_links, "{concept}")'
    if area == "methods":
        link_pred += f' OR contains(methods, "{concept}")'
    body = f"""{fm(front)}
# {meta.get('title', concept)}

> Concept durable (tema). Síntesis por LLM: destilar acá lo que aprenden los papers de abajo, de modo
> que el tema se entienda **sin abrir ningún paper**. Trazabilidad por `[[bibcode]]`.
>
{LLM_DISCLAIMER["concept"]}
>
> _Generado con Almagesto v{cfg.ALMAGESTO_VERSION}._

## Síntesis
_(qué se sabe del tema: mecanismos, signos, desfasajes, regímenes)._

{INVENTARIO}
{REGIMEN}
## Huecos
_(qué falta para entender/implementar el tema sin abrir papers: pasos o ecuaciones faltantes,
**regímenes no cubiertos** (los que la tabla de arriba deja fuera: ¿en qué condiciones nadie lo
midió?), contradicciones sin resolver.)_

## Papers que tocan este tema (auto)
```dataview
TABLE bearing, year, file.link
FROM "wiki/papers"
WHERE {link_pred}
SORT year ASC
```
"""
    body += excluded_table(slug)
    dest.write_text(body, encoding="utf-8")
    stamp_search_line(slug, dest)
    print(f"  concept: {area}/{concept}.md escrito (stub)")


def write_paper_notes(slug: str, include_all: bool, force: bool, topic: bool = False) -> None:
    if topic:
        _, tmeta = cfg.topic_by_slug(slug)
        name, link, seed_links = None, tmeta["concept"], [tmeta["concept"]]
    else:
        name, _ = cfg.star_by_slug(slug)
        link, seed_links = slug, []
    adsfile = cfg.ROOT / "build" / slug / "ads.json"
    if not adsfile.exists():
        print(f"  (sin {adsfile}; corré query_ads.py primero)")
        return
    recs = json.loads(adsfile.read_text(encoding="utf-8"))["records"]
    if not include_all:
        recs = [r for r in recs if r["relevant"]]
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    extraccion = extraction_block(topic)     # una sola lectura del objetivo para toda la corrida
    written = skipped = merged = restamped = 0
    for r in recs:
        bib = r["bibcode"]
        dest = cfg.PAPERS / f"{safe_name(bib)}.md"
        if dest.exists() and not force:
            # Retro-linkeo add-only (issue #4b): el paper ya estaba en el corpus (ingest previo de
            # otra estrella/tema) → no se pisa la extracción LLM, pero SÍ se mergean los seeds de
            # este ingest (tema → thesis_links; estrella → stars) para que la nota aparezca en las
            # tablas Dataview de la entidad nueva. Idempotente: si ya están, no toca nada.
            seeds = seed_links if topic else ([name] if name else [])
            if seeds and merge_frontmatter_list(dest, "thesis_links" if topic else "stars", seeds):
                merged += 1
            else:
                skipped += 1
            if stamp_pdf_link(dest):    # cabecera ↔ frontmatter `pdf` (#47) — cirugía, no pisa nada
                restamped += 1
            continue
        authors = r.get("authors", [])
        # PDF ↔ disco (verdad de disco, como en off-ADS): linkear sólo el PDF realmente bajado
        # (fetch_arxiv/fetch_pdf ya corrieron en la cadena) — no adivinar por arxiv_id, que
        # dejaba punteros a archivos inexistentes cuando la bajada fallaba.
        pdf_rel = (f"../../raw/pdfs/{slug}/{safe_name(bib)}.pdf"
                   if (cfg.PDFS / slug / f"{safe_name(bib)}.pdf").exists() else None)
        # En la cadena el .txt suele no existir todavía (extract_fulltext corre después y
        # estampa vía stamp_fulltext); en un re-run sí está y el stub nace completo.
        txt_rel, txt_src = fulltext_info(slug, safe_name(bib))
        pdf_src, pdf_ver = pdf_source_info(slug, safe_name(bib))
        front = {
            "bibcode": bib,
            "title": r.get("title"),
            "first_author": authors[0] if authors else None,
            "n_authors": len(authors),
            "year": int(r["year"]) if r.get("year") else None,
            "arxiv_id": r.get("arxiv_id"),
            "doi": r.get("doi"),
            "bibstem": r.get("bibstem"),
            "stars": [name] if name else [],
            "topics": r.get("topics", []),
            "methods": [],                 # poblar con extracción LLM
            "thesis_links": list(seed_links),  # tema: pre-sembrado al concept; estrella: vacío
            "bearing": None,               # supports | challenges | method (respecto a thesis_links)
            # ROL del paper dentro del tema/entidad (#73), poblado por la EXTRACCIÓN:
            # fundacional | aplicacion | arbitro (uno o varios). `bearing` dice la POSTURA respecto
            # de una tesis; `role` dice QUÉ TIPO DE APORTE es, que es lo que define la operación de
            # contraste. El clasificador no puede darlo: la regex clasifica tema, no rol.
            "role": [],
            "relevance": "high" if r.get("relevant") else "low",
            "citation_count": r.get("citation_count", 0),
            "pdf": pdf_rel,
            "fulltext": txt_rel,           # el artefacto BARATO del contrato: leer/grep esto, no el PDF
            "fulltext_source": txt_src,    # pdftotext | ocr (citable con salvedad) | web
            # de QUÉ documento salió (#57), distinto del método de extracción de arriba:
            # eprint (arXiv, puede ser un v1 pre-referato) | ads | publisher | web | null
            "pdf_source": pdf_src,
            **({"eprint_version": pdf_ver} if pdf_ver else {}),
            "confidence": "medium",      # patrón LLM Wiki
            "tags": ["paper"],
            "generator": f"Almagesto v{cfg.ALMAGESTO_VERSION}",   # provenance (con qué versión se armó)
        }
        abstract = (r.get("abstract") or "").strip()
        body = f"""{fm(front)}
# {r.get('title')}

**{', '.join(authors[:6])}{' et al.' if len(authors) > 6 else ''}** ({r.get('year')})
· [[{link}]] · ADS: `{bib}`{' · arXiv: ' + r['arxiv_id'] if r.get('arxiv_id') else ''}{f' · [📄 PDF]({pdf_rel})' if pdf_rel else ''}

## Abstract
{abstract or '_(no disponible)_'}

{extraccion}"""
        dest.write_text(body, encoding="utf-8")
        written += 1
    print(f"  papers: {written} escritos, {skipped} ya existían"
          + (f", {merged} retro-linkeados (seeds add-only)" if merged else "")
          + (f", {restamped} con link [📄 PDF] re-estampado" if restamped else ""))


def unpend_note(dest, citekey: str, slug: str | None) -> bool:
    """Des-pendea una nota cuya fuente YA llegó: si el frontmatter tiene `pending_source` y el
    material existe en disco (PDF en raw/pdfs/<slug>/ o snapshot .txt en raw/fulltext/<slug>/),
    saca el flag (y el blockquote ⏳ del cuerpo), y linkea `pdf` si estaba null. Edición QUIRÚRGICA
    a nivel texto (como merge_frontmatter_list): sólo toca líneas estampadas por la máquina, nunca
    la extracción LLM. Devuelve True si modificó."""
    if not slug:
        return False
    text = dest.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end < 0 or "\npending_source:" not in text[:end]:
        return False
    has_pdf = (cfg.PDFS / slug / f"{safe_name(citekey)}.pdf").exists()
    has_txt = (cfg.FULLTEXT / slug / f"{citekey}.txt").exists()
    if not (has_pdf or has_txt):
        return False                     # la fuente sigue faltando: el flag se queda
    head, body = text[4:end], text[end:]
    lines = [ln for ln in head.split("\n") if not ln.startswith("pending_source:")]
    if has_pdf:
        pdf_rel = f"../../raw/pdfs/{slug}/{safe_name(citekey)}.pdf"
        lines = [f"pdf: {pdf_rel}" if ln.strip() == "pdf: null" else ln for ln in lines]
    body = "\n".join(ln for ln in body.split("\n")
                     if not ln.startswith("> ⏳ **Fuente pendiente"))
    dest.write_text("---\n" + "\n".join(lines) + body, encoding="utf-8")
    print(f"  papers: {dest.name} — fuente obtenida → pending_source removido"
          + (" y `pdf` linkeado" if has_pdf else ""))
    return True


def write_web_paper_note(citekey: str, *, url: str | None = None, slug: str | None = None,
                         concept: str | None = None, title: str | None = None,
                         first_author: str | None = None, year=None, n_authors=None,
                         doi: str | None = None, venue: str | None = None,
                         accessed: str | None = None, pending: str | None = None,
                         force: bool = False) -> bool:
    """Stub de nota de paper para una fuente **off-ADS** (web o PDF sin bibcode ADS) — modo off-ADS de
    ingest-topic. Análogo a write_paper_notes pero **sin ads.json**: la metadata la provee quien llama
    (fetch_web.py, ingest_topic.py o el usuario). `bibcode` = clave sintética AAAA+Autor; `arxiv_id`
    null; `n_authors`/`doi` los del item de `sources:` si se declararon (un PDF con DOI sigue siendo
    off-ADS — no tiene bibcode ADS — pero el DOI habilita check_retractions);
    `pdf` normalmente null (el respaldo citable es el snapshot `.txt` de fulltext/) — salvo que el
    PDF off-ADS ya esté copiado en raw/pdfs/<slug>/<citekey>.pdf (fuente local-pdfs, lo hace
    ingest_topic.py), en cuyo caso se linkea solo (así el chequeo PDF↔disco del lint no marca drift);
    `thesis_links` pre-sembrado al concept. Para fuentes web, `source_url` + `accessed` son la
    provenance bibliográfica (el "Retrieved <fecha>" de una cita web); `accessed` = la fecha del
    snapshot (la pasa fetch_web.py; si es web y no se pasó, se reusa la `retrieved` del snapshot
    en disco y, sólo si no hay, hoy UTC — #34). El tag distingue el
    tipo de fuente: `web` = snapshot de URL; `local-pdf` = PDF provisto (off-ADS).

    `pending` (fallback fuentes no-conseguibles): la fuente todavía NO se pudo obtener —
    `paywall` (sin copia libre), `scan` (escaneo sin capa de texto) o `unextractable` (mojibake) —
    y queda DERIVADA al usuario: se estampa `pending_source` en el frontmatter (el lint lo lista
    como precondición) y `url`/`doi` quedan como puntero conocido, sin snapshot (`accessed` null).

    Idempotente: NO pisa una nota existente salvo force. Devuelve True si escribió. Mismo template
    que las notas ADS."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    dest = cfg.PAPERS / f"{safe_name(citekey)}.md"
    if dest.exists() and not force:
        # la nota no se pisa, pero si estaba PENDIENTE y la fuente ya llegó, se des-pendea
        # (edición quirúrgica del flag; la extracción LLM no se toca). Ídem el contrato
        # fulltext: si el snapshot/.txt ya está en disco, se estampa en la nota existente.
        if not pending and unpend_note(dest, citekey, slug):
            stamp_fulltext(dest, safe_name(citekey), slug)
            stamp_pdf_link(dest)         # unpend_note pudo linkear `pdf:` → la cabecera lo sigue (#47)
            return False
        if not pending and stamp_fulltext(dest, safe_name(citekey), slug):
            stamp_pdf_link(dest)
            print(f"  papers: {dest.name} — fulltext estampado (contrato máquina)")
            return False
        if not pending and stamp_pdf_link(dest):
            print(f"  papers: {dest.name} — link [📄 PDF] de cabecera re-estampado (#47)")
            return False
        print(f"  papers: {dest.name} ya existe (no se pisa sin --force)")
        return False
    bibstem = venue or (urlparse(url).netloc if url else None)   # venue: dominio web por default
    if accessed is None and url and not pending:
        # fuente web sin fecha explícita: reusar la `retrieved` del snapshot en disco (#34 — la
        # nota debe coincidir con el .txt; el flujo "sin Node" del skill guarda el snapshot a mano
        # y stubbea después) y recién si no hay snapshot, hoy UTC. (pending: sin snapshot → null)
        snap = (cfg.FULLTEXT / slug / f"{safe_name(citekey)}.txt") if slug else None
        accessed = ((cfg.snapshot_retrieved(snap) if snap and snap.exists() else None)
                    or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    # PDF↔disco: si el PDF off-ADS ya está copiado a raw/pdfs/<slug>/, linkearlo (verdad de disco)
    pdf_rel = None
    if slug and (cfg.PDFS / slug / f"{safe_name(citekey)}.pdf").exists():
        pdf_rel = f"../../raw/pdfs/{slug}/{safe_name(citekey)}.pdf"
    # fulltext↔disco: fetch_web escribe el snapshot ANTES de llamar acá → la nota web nace con el
    # contrato completo; para local-pdfs lo estampa extract_fulltext al extraer (stamp_fulltext).
    txt_rel, txt_src = fulltext_info(slug, safe_name(citekey))
    pdf_src, pdf_ver = pdf_source_info(slug, safe_name(citekey))
    front = {
        "bibcode": citekey,
        "title": title,
        "first_author": first_author,
        "n_authors": parse_int(n_authors, "n_authors"),
        "year": parse_year(year),
        "arxiv_id": None,
        "doi": doi,                  # un PDF con DOI sigue siendo off-ADS (sin bibcode ADS)
        "source_url": url,           # fuente web off-ADS (provenance); null para fuente PDF
        "accessed": accessed,        # fecha del snapshot — bibliografía web ("Retrieved <fecha>")
        "bibstem": bibstem,
        "stars": [],
        "topics": [],
        "methods": [],                       # poblar con extracción LLM
        "thesis_links": [concept] if concept else [],   # pre-sembrado al concept
        "bearing": None,                     # supports | challenges | method
        "role": [],                          # fundacional | aplicacion | arbitro (#73) — extracción
        "relevance": "high",
        "citation_count": 0,
        "pdf": pdf_rel,                      # off-ADS: null salvo PDF local ya copiado a raw/pdfs/<slug>/
        "fulltext": txt_rel,                 # el artefacto BARATO del contrato: leer/grep esto, no el PDF
        "fulltext_source": txt_src,          # pdftotext | ocr (citable con salvedad) | web
        "pdf_source": pdf_src,               # de QUÉ documento salió (#57): web | eprint | … | null
        **({"eprint_version": pdf_ver} if pdf_ver else {}),
        # fuente aún no obtenida (paywall|scan|unextractable) → derivada al usuario; sólo si aplica
        **({"pending_source": pending} if pending else {}),
        "confidence": "medium",
        "tags": ["paper", "web" if url else "local-pdf"],   # tipo de fuente off-ADS (findability)
        "generator": f"Almagesto v{cfg.ALMAGESTO_VERSION}",   # provenance
    }
    txt_ptr = f"vault/raw/fulltext/{slug or '<slug>'}/{citekey}.txt"
    src_line = f"· {url}\n" if url else ""
    acc_line = f"· snapshot {accessed}\n" if accessed else ""
    pend_line = ("" if not pending else
                 f"\n> ⏳ **Fuente pendiente (`{pending}`):** todavía sin fulltext — el usuario debe "
                 "proveer el PDF/fuente (puntero `doi`/`source_url` en el frontmatter). Al conseguirla, "
                 "re-correr la cadena y completar la extracción.\n")
    # off-ADS es el modo opt-in de ingest-topic (CLAUDE.md): acá el sujeto es SIEMPRE un tema.
    body = f"""{fm(front)}
# {title or citekey}

**{first_author or '(autor desconocido)'}** ({year or 's.f.'})
· {'[[' + concept + ']] · ' if concept else ''}fuente off-ADS · `{citekey}`{f' · [📄 PDF]({pdf_rel})' if pdf_rel else ''}
{src_line}{acc_line}
> Fuente **off-ADS** (fuera de ADS). El respaldo citable es el snapshot determinista
> `{txt_ptr}` (`source_url` + `accessed` en el frontmatter), verificable por `verify-citations`.
> El frontmatter es máquina-legible como en cualquier nota de paper.
{pend_line}
{extraction_block(topic=True)}"""
    dest.write_text(body, encoding="utf-8")
    print(f"  papers: {dest.name} escrito (stub off-ADS)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?",
                    help="slug de estrella/tema; en --web es la CLAVE de cita (AAAA+Autor). "
                         "Opcional sólo con --restamp-pdf-links.")
    ap.add_argument("--all", action="store_true", help="incluir papers no-relevantes")
    ap.add_argument("--restamp-pdf-links", action="store_true", dest="restamp_pdf_links",
                    help="backfill #47: barre TODAS las notas de papers y re-estampa el link "
                         "[📄 PDF] de la cabecera desde el frontmatter `pdf` (agrega/corrige/quita). "
                         "No toca la extracción LLM; no requiere slug.")
    ap.add_argument("--restamp-headers", action="store_true", dest="restamp_headers",
                    help="backfill #69: barre TODAS las fichas/conceptos y estampa la cabecera "
                         "(aviso de capa LLM + línea del generador) a las que nacieron sin ella. "
                         "La versión sale del `generator` del frontmatter, no se inventa. No toca "
                         "la síntesis LLM; no requiere slug.")
    ap.add_argument("--migrate-disputes", action="store_true", dest="migrate_disputes",
                    help="migración #71: pasa `planets[].disputes[]` (polo de verdad hardcodeado) a "
                         "`disputes` a nivel nota con posiciones explícitas. Toca sólo las fichas "
                         "que tienen disputas viejas; no toca el cuerpo. No requiere slug.")
    ap.add_argument("--force", action="store_true", help="pisar notas existentes")
    ap.add_argument("--topic", action="store_true",
                    help="el slug es un TEMA de vault/config/topics.yaml: genera concept en vez de ficha de estrella")
    ap.add_argument("--web", action="store_true",
                    help="modo off-ADS: el positional es la CLAVE de cita de una fuente web/PDF sin ADS; crea sólo la nota de paper (stub)")
    ap.add_argument("--url", help="(--web) URL fuente del snapshot")
    ap.add_argument("--slug-hint", dest="slug_hint", help="(--web) tema al que pertenece, para el puntero al .txt")
    ap.add_argument("--concept", help="(--web) concept destino → thesis_links")
    ap.add_argument("--title", help="(--web) título de la fuente")
    ap.add_argument("--author", help="(--web) primer autor")
    ap.add_argument("--year", help="(--web) año")
    ap.add_argument("--n-authors", dest="n_authors", help="(--web) cantidad de autores")
    ap.add_argument("--doi", help="(--web) DOI de la fuente, si existe (habilita check_retractions)")
    ap.add_argument("--venue", help="(--web) venue/bibstem (default: dominio de --url)")
    ap.add_argument("--accessed", help="(--web) fecha del snapshot AAAA-MM-DD (default: la "
                                       "`retrieved` del .txt en disco; si no hay, hoy UTC)")
    ap.add_argument("--pending", choices=["paywall", "scan", "unextractable"],
                    help="(--web) fuente aún no conseguible: estampa pending_source y deriva al usuario")
    args = ap.parse_args()

    if args.restamp_pdf_links:
        return restamp_pdf_links()
    if args.restamp_headers:
        return restamp_headers()
    if args.migrate_disputes:
        return migrate_all_disputes()
    if not args.slug:
        ap.error("falta el slug (sólo --restamp-pdf-links, --restamp-headers y --migrate-disputes "
                 "corren sin slug)")

    if args.web:
        write_web_paper_note(args.slug, url=args.url, slug=args.slug_hint, concept=args.concept,
                             title=args.title, first_author=args.author, year=args.year,
                             n_authors=args.n_authors, doi=args.doi, venue=args.venue,
                             accessed=args.accessed, pending=args.pending, force=args.force)
        return 0

    print(f"Generando notas para {args.slug}")
    if args.topic:
        write_concept_note(args.slug, args.force)
    else:
        write_star_note(args.slug, args.force)
    write_paper_notes(args.slug, args.all, args.force, topic=args.topic)
    return 0


if __name__ == "__main__":
    sys.exit(main())
