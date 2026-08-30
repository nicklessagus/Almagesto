"""Genera notas markdown de la bóveda a partir de lo bajado por los otros scripts.

Uso:
    python scripts/make_notes.py <slug> [--all] [--force]        # estrella
    python scripts/make_notes.py --theme <slug> [--all] [--force]  # tema (concept + papers)
    python scripts/make_notes.py --web <clave> --concept <c> [--url … | --pending …] [--slug-hint <s>]
    python scripts/make_notes.py --restamp-pdf-links             # backfill del link PDF, sin slug
    python scripts/make_notes.py --restamp-headers               # backfill de la cabecera, sin slug
    python scripts/make_notes.py --migrate-disputes              # migración #71 de disputes, sin slug
    python scripts/make_notes.py --migrate-vistas                # migración #188 de vistas, sin slug
    python scripts/make_notes.py --sync-mirror                   # backfill espejo NEA (#70), sin slug

- vault/wiki/stars/<slug>.md            : ficha índice de la estrella (frontmatter + Dataview).
- vault/wiki/concepts/<area>/<c>.md     : stub del concept durable de un tema (--theme).
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
`> _Estado — …_` de la cabecera desde `vault/config/registro/<slug>.yaml` — ver stamp_estado
(#64). Aparte, `stamp_fulltext` (lo llama extract_fulltext al cerrar) estampa
`fulltext`/`fulltext_source`/`pdf_source` sobre notas ya existentes. Backfill masivo del link PDF:
`python scripts/make_notes.py --restamp-pdf-links` (sin slug).
(e) `--migrate-disputes` (#71) cambia la estructura del frontmatter, así que lo re-serializa — por
eso toca sólo las fichas con disputas del schema viejo y el cuerpo se conserva byte a byte. Ver
migrate_disputes. (f) `--sync-mirror` rellena en `stars/` los campos espejo de NEA (#70) que están
en null y el ground-truth trae — también re-serializa sólo el frontmatter, add-only y en un solo
sentido (nunca pisa un valor existente ni distinto del ground-truth). Ver sync_mirror.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import yaml

import lib_config as cfg
import lib_blocks as lb              # bloque de verificación (#117)

EXCLUDED_TOP_N = 10  # cuántos no-core mostrar en la tabla de excluidos (top por citas)


# #182 · era una COPIA de `cfg.listify_curado` —mismo cuerpo, mismo docstring reescrito—. Dos
# implementaciones de la misma promesa es la garantía de que una envejece (red #3: un doble con
# distinto contrato que la función real esconde el bug en la diferencia). Se re-exporta el nombre
# porque lo usan tres call sites de este módulo.
_listify_curado = cfg.listify_curado


def fm(d: dict) -> str:
    """Frontmatter YAML entre --- ---."""
    # @inv INV-71
    body = yaml.safe_dump(d, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"---\n{body}---\n"


def safe_name(bibcode: str) -> str:
    return bibcode.replace("/", "_")


def _txt_provenance(path) -> str:
    """Provenance de un .txt por la marca de su primera línea: `ocr` (rescate tesseract —
    citable con salvedad), `web` (snapshot defuddle) o `pdftotext` (extracción determinista,
    sin marca). Un solo lugar de verdad para leer el header."""
    # @inv INV-26
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
    #  @inv INV-29
        if _txt_provenance(txt) == "web":
            return "web", None
        # AUD-164: el alcance lo decide `arxiv_stamp` (por PÁGINA, no por un tope de caracteres);
        # recortar acá antes de llamarla volvía a imponer el corte que el fix sacó.
        ver = cfg.arxiv_stamp(txt.read_text(encoding="utf-8", errors="replace"))
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


def best_fulltext(stem: str) -> tuple[str | None, str | None]:
    """The `.txt` this paper should point at, chosen across ALL slugs: `(rel path, provenance)`.

    ⛔ INV-23 / INC-3 — this closes the last INCUMPLIDO of the contract. A paper relevant to several
    subjects has its `.txt` extracted under **each** slug (identical content), and the note is one.
    Everything else the invariant promises held —re-running does not repoint, and quality precedence
    works in both directions— but the **first** stamp took whatever slug happened to run, so `A,B`
    and `B,A` produced a different `fulltext:` byte for byte. No information is lost and nothing is
    misstated; what it produces is a diff that depends on ingest order, which is noise, and it made
    `CLAUDE.md`'s «idempotente, sin ruido de diff» read stronger than the code delivered.

    The tie-break is DECLARED: highest quality first (`pdftotext`/`web` > `ocr`), then the
    lexicographically smallest slug — the same rule `lib_config.artefacto_en_otro_slug` already uses
    to pick among copies, so the two do not diverge."""
    cands = []
    for d in sorted(cfg.FULLTEXT.glob(f"*/{stem}.txt")) if cfg.FULLTEXT.exists() else []:
        rel, src = fulltext_info(d.parent.name, stem)
        if rel:
            cands.append((-_FULLTEXT_QUALITY.get(src, 0), d.parent.name, rel, src))
    if not cands:
        return None, None
    _q, _slug, rel, src = min(cands)
    return rel, src


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
    # INV-23: el candidato NO es el del slug que corrió, es el mejor de la bóveda con desempate
    # declarado. Así el primer estampado deja de depender del orden de ingesta.
    rel, src = best_fulltext(stem)
    if rel is None or not dest.exists():
        return False
    text = dest.read_text(encoding="utf-8")
    lim = cfg.fm_bounds(text)             # AUD-147: el MISMO localizador que `split_fm`
    if lim is None:
        return False
    ini, end = lim
    lines = text[ini:end].split("\n")

    # Si ya hay un `fulltext:` válido (apunta a un .txt que existe), decidir quién gana ANTES de
    # estampar: sólo un candidato de calidad estrictamente mayor pisa al ya estampado. En empate
    # (misma calidad, incluido otro slug con el mismo contenido) el existente se queda → idempotente.
    cur_rel = next((ln.split(":", 1)[1].strip().strip("'\"")
                    for ln in lines if ln.startswith("fulltext:")), None)
    slug_ganador = slug
    if cur_rel and cur_rel not in ("null", "~") and cur_rel != rel:
        cur_path = (dest.parent / cur_rel).resolve()
        if cur_path.exists():
            cur_src = _txt_provenance(cur_path)
            if _FULLTEXT_QUALITY.get(src, 0) <= _FULLTEXT_QUALITY.get(cur_src, 0):
                rel, src = cur_rel, cur_src   # el existente gana → estampá SU provenance
                # AUD-186 / INV-23 — y su `pdf_source` TAMBIÉN. La regla de estabilidad cubría
                # `fulltext`/`fulltext_source` y no al tercero, así que un paper compartido por dos
                # slugs quedaba con el `.txt` de uno y la procedencia del PDF del otro, **alternando
                # en cada corrida**: el frontmatter dejaba de ser idempotente y el consumidor leía
                # `pdf_source: eprint` sobre el `.txt` de un slug cuyo PDF era el publicado.
                slug_ganador = cur_path.parent.name

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
    psrc, pver = pdf_source_info(slug_ganador, stem)
    if psrc:
        changed = upsert("pdf_source", psrc, ("fulltext_source", "fulltext", "pdf")) or changed
        if pver:
            changed = upsert("eprint_version", pver, ("pdf_source",)) or changed
    if changed:
        cfg.write_text_atomic(dest, text[:ini] + "\n".join(lines) + text[end:])
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
    lim = cfg.fm_bounds(text)             # AUD-147
    #  @inv INV-17
    if lim is None:
        return None
    end = lim[1]
    pos = text.find("\n", end + 1) + 1    # arranca DESPUÉS de la línea del `---` de cierre
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
    #  @inv INV-18
        return False
    text = dest.read_text(encoding="utf-8")
    lim = cfg.fm_bounds(text)             # AUD-147
    if lim is None:
        return False
    try:
        data = yaml.safe_load(text[lim[0]:lim[1]]) or {}
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
    cfg.write_text_atomic(dest, text[:pos] + new_line + text[line_end:])
    return True


def retarget_artifacts(stem: str) -> bool:
    """Re-point one paper note's `pdf:`/`fulltext:` at DISK TRUTH, nulling them when nothing is
    left, and re-stamp the header link accordingly (#217). Returns True if it changed the note.

    `drop_core` always deletes the PDF and the `.txt` and **sometimes** keeps the note (the paper
    belongs to another subject, or carries paid extraction). In that second case the note was left
    claiming `pdf: ../../raw/pdfs/<slug>/<bib>.pdf` for a file that no longer exists — and both
    fields are, by contract, disk truth. Before #215 the drift healed itself on the next
    `make_notes` run, which re-stamped both by disk truth; the #215 fix filters dropped papers out
    **before** writing notes — which is right, we do not want the dropped paper resurrected — so
    those notes never pass through the re-stamp again and the drift went from transient to
    **permanent**. It is not an argument against #215: the cleanup belongs to whoever deleted the
    files, which is the only code that knows what it deleted.

    ⚠ Not a blanket null: a paper living under several slugs may still have a copy under another
    one, and the field is stable by design (quality precedence, INV-23). So it re-points to the
    surviving copy and only nulls when there is none — `best_fulltext` for the `.txt` (which is the
    same tie-break `stamp_fulltext` uses, not a second rule) and the alphabetically first surviving
    PDF, the same rule as `artefacto_en_otro_slug`.

    ⛔ It does NOT touch the view or the extraction: the reading happened and its page locators are
    still valid. What changed is that there is no longer a source to re-verify it against."""
    dest = cfg.PAPERS / f"{safe_name(stem)}.md"
    if not dest.exists():
        return False
    text = dest.read_text(encoding="utf-8")
    lim = cfg.fm_bounds(text)
    if lim is None:
        return False
    pdfs = sorted(cfg.PDFS.glob(f"*/{safe_name(stem)}.pdf")) if cfg.PDFS.exists() else []
    pdf_rel = f"../../raw/pdfs/{pdfs[0].parent.name}/{safe_name(stem)}.pdf" if pdfs else None
    ft_rel, ft_src = best_fulltext(safe_name(stem))
    ini, end = lim
    lines, cambio = text[ini:end].split("\n"), False
    for i, ln in enumerate(lines):
        for campo, valor in (("pdf", pdf_rel), ("fulltext", ft_rel), ("fulltext_source", ft_src)):
            if ln.startswith(f"{campo}:"):
                nueva = f"{campo}: {valor}" if valor else f"{campo}: null"
                if ln.rstrip() != nueva:
                    lines[i], cambio = nueva, True
    if cambio:
        cfg.write_text_atomic(dest, text[:ini] + "\n".join(lines) + text[end:])
    # el link de cabecera es metadata derivada del campo `pdf`: se re-estampa desde ahí (#47)
    return stamp_pdf_link(dest) or cambio


INDEX_SECCIONES = ("## Estrellas", "## Conceptos (por área)", "## Papers")
"""The index sections this stamps. `## Matrices` is hand-written prose and is left alone."""

INDEX_PAPERS_TOP = 50

#: The Dataview block each section keeps BELOW its materialised table. #60 forbids Dataview being
#: the only form —an agent opening the `.md` sees the query, not its results, and the plugin is not
#: versioned—; it does not forbid it existing as a convenience for whoever opens Obsidian.
INDEX_DATAVIEW = {
    "## Estrellas": '```dataview\nTABLE spectral_type AS "Tipo", P_rot_days AS "P_rot (d)", '
                    'length(planets) AS "Planetas"\nFROM "wiki/stars"\nSORT file.name ASC\n```',
    "## Conceptos (por área)": '```dataview\nTABLE status, confidence\nFROM "wiki/concepts"\n'
                               'SORT file.folder ASC, file.name ASC\n```',
    "## Papers": '```dataview\nTABLE WITHOUT ID file.link AS "Paper", year AS "Año", '
                 'relevance AS "Rel."\nFROM "wiki/papers"\nSORT citation_count DESC\nLIMIT 50\n```',
}


def index_tables(fms: dict | None = None) -> dict:
    """The index's three tables, materialised from frontmatter truth (#237).

    `index.md` was the vault's only artifact left 100 % Dataview — the very thing #60 forbade for the
    roll-ups, and with more force here: the catalogue is the FIRST thing an agent opens to orient
    itself, and `CLAUDE.md` names it as one of the four pieces of the in-repo memory. A ```dataview```
    block shows whoever opens the `.md` **the query, not its results**, and the plugin is not even
    versioned (`.obsidian/plugins/` is gitignored while `community-plugins.json` declares dataview).
    On top of that the skill's bookkeeping step said «add the concept to `index.md`» and the file had
    no static line to add it to, so the step could not be done as written — measured: the three
    commits touching a real instance's `index.md` all predate its instantiation.

    Same rule as the roll-ups: read with `split_fm`, never grep the frontmatter (a list written in
    block style and one in flow style are both normal here).
    """
    # `fms` es el índice `{stem: frontmatter}` que el llamador YA parseó. Sin él esta función
    # re-lee y re-parsea la bóveda entera, y como el lint la llama en cada corrida eso duplicaba el
    # parseo de todo el corpus — medido en el tier `poblada`: el ratio de `yaml.safe_load` por nota
    # saltó de 2,0x a 3,2x sobre 900 notas. El default (None) mantiene el uso suelto del estampador.
    def _fm(f):
        """El frontmatter de esa nota: el que el llamador ya parseó, o uno recién leído."""
        if fms is not None and f.stem in fms:
            return fms[f.stem]
        return cfg.split_fm(f.read_text(encoding="utf-8")) or {}

    stars, concepts, papers = [], [], []
    for f in sorted(cfg.STARS.glob("*.md")) if cfg.STARS.exists() else []:
        fm = _fm(f)
        stars.append((f.stem, fm.get("spectral_type"), fm.get("P_rot_days"),
                      len(cfg.as_list(fm.get("planets")))))
    for f in sorted(cfg.CONCEPTS.glob("*/*.md")) if cfg.CONCEPTS.exists() else []:
        fm = _fm(f)
        concepts.append((f.parent.name, f.stem, fm.get("status"), fm.get("confidence")))
    for f in sorted(cfg.PAPERS.glob("*.md")) if cfg.PAPERS.exists() else []:
        fm = _fm(f)
        papers.append((f.stem, fm.get("year"), fm.get("relevance"),
                       fm.get("citation_count") or 0))
    papers.sort(key=lambda r: (-(r[3] or 0), r[0]))
    return {"## Estrellas": _index_stars(stars),
            "## Conceptos (por área)": _index_concepts(concepts),
            "## Papers": _index_papers(papers)}


def _celda_idx(v) -> str:
    """A frontmatter value as an index cell: `—` for absent, so «no value» and «no column» differ."""
    return "—" if v in (None, "", []) else str(v)


def _index_stars(rows: list) -> str:
    """The `## Estrellas` table."""
    out = ["| Estrella | Tipo | P_rot (d) | Planetas |", "|---|---|---|---|"]
    out += [f"| [[{n}]] | {_celda_idx(t)} | {_celda_idx(p)} | {k} |" for n, t, p, k in rows]
    return "\n".join(out) if rows else "_(sin estrellas todavía)_"


def _index_concepts(rows: list) -> str:
    """The `## Conceptos (por área)` table. `status` only exists for hypotheses, and that is why the
    column says `—` elsewhere instead of being silently empty (the Dataview version showed a blank
    column by design and nothing said why)."""
    out = ["| Área | Concepto | Estado | Confianza |", "|---|---|---|---|"]
    out += [f"| {a} | [[{n}]] | {_celda_idx(st)} | {_celda_idx(c)} |" for a, n, st, c in rows]
    return "\n".join(out) if rows else "_(sin conceptos todavía)_"


def _index_papers(rows: list) -> str:
    """The `## Papers` table: the top by citations, with the total said out loud — a truncated list
    that does not declare its cut reads as the whole corpus."""
    if not rows:
        return "_(sin papers todavía)_"
    top = rows[:INDEX_PAPERS_TOP]
    out = [f"_{len(rows)} nota(s) de paper; se listan las {len(top)} más citadas._", "",
           "| Paper | Año | Rel. | Citas |", "|---|---|---|---|"]
    out += [f"| [[{n}]] | {_celda_idx(y)} | {_celda_idx(r)} | {c} |" for n, y, r, c in top]
    return "\n".join(out)


def restamp_index() -> int:
    """Materialise `index.md`'s tables from disk (#237). Idempotent, surgical, prose untouched."""
    dest = cfg.WIKI / "index.md"
    if not dest.exists():
        cfg.print_seguro("no hay vault/wiki/index.md — nada que estampar")
        return 0
    # `_reemplazar_seccion` reemplaza DESDE el encabezado, así que el cuerpo lo lleva puesto. Y el
    # bloque ```dataview``` queda debajo, a propósito: es comodidad para quien abre Obsidian. Lo que
    # #60 prohíbe es que sea la ÚNICA forma, no que exista.
    # ⛔ Si la sección NO existe, se CREA. `_reemplazar_seccion` es cirugía y por contrato no
    # inventa secciones —correcto para una ficha, donde inventar una la pondría fuera de lugar—,
    # pero el índice es un catálogo **estampado por máquina**: una bóveda cuyo `index.md` perdió (o
    # nunca tuvo) `## Papers` no podía recuperarla con el estampador, y el lint la iba a reportar
    # para siempre con un arreglo sólo manual. Se inserta antes de `## Matrices`, que es la única
    # sección de prosa a mano, o al final.
    texto = dest.read_text(encoding="utf-8")
    faltan = [h for h in INDEX_SECCIONES if cfg.section_start(texto, h) < 0]
    if faltan:
        corte = cfg.section_start(texto, "## Matrices")
        corte = len(texto) if corte < 0 else corte
        nuevo = "".join(f"{h}\n\n_(pendiente de estampar)_\n\n" for h in faltan)
        cfg.write_text_atomic(dest, texto[:corte] + nuevo + texto[corte:])
        cfg.print_seguro(f"index.md: {len(faltan)} sección(es) creadas ({', '.join(faltan)})")
    cambios = sum(1 for h, cuerpo in index_tables().items()
                  if _reemplazar_seccion(
                      dest, h, f"{h}\n\n{cuerpo}\n\n{INDEX_DATAVIEW[h]}\n\n"))
    cfg.print_seguro(f"index.md: {cambios} de {len(INDEX_SECCIONES)} sección(es) actualizadas")
    return 0


def restamp_pdf_links() -> int:
    """Backfill #47: barre TODAS las notas de papers y re-estampa el link de cabecera. Para
    el corpus pre-#13 de una instancia (re-correr cadena por cadena sería carísimo y build/
    es scratch que puede no existir); en el flujo normal el re-estampado viaja solo con el
    re-run idempotente de la cadena."""
    notes = sorted(cfg.PAPERS.glob("*.md")) if cfg.PAPERS.exists() else []
    changed = sum(1 for p in notes if stamp_pdf_link(p))
    cfg.print_seguro(f"papers: {changed} de {len(notes)} re-estampados (link [📄 PDF] ↔ frontmatter `pdf`)")
    return 0


def stamp_accessed(dest, accessed: str) -> bool:
    """Re-stamp `accessed:` on an existing web note. True when it changed the file.

    ⛔ AUD-170 — `fetch_web --force` re-downloads the snapshot with today's date and the note keeps
    the old one, because the note is only rewritten with `--force-note`. `accessed` **is** the
    citation's "Retrieved <fecha>", so the note ended up publishing a retrieval date that does not
    match the `.txt` sitting next to it — and that `.txt` is the artifact `verify-citations` reads.
    Machine metadata like `pdf`/`fulltext`, so it is surgery on its own line: the LLM extraction and
    every other field are preserved byte for byte."""
    if not dest.exists():
        return False
    text = dest.read_text(encoding="utf-8")
    lim = cfg.fm_bounds(text)
    if lim is None:
        return False
    ini, end = lim
    lines = text[ini:end].split("\n")
    idx = next((i for i, ln in enumerate(lines) if ln.startswith("accessed:")), None)
    if idx is None:
        return False                     # sin el campo no se inventa la posición (mismo criterio)
    nueva = f"accessed: {accessed}"
    if lines[idx] == nueva:
        return False
    lines[idx] = nueva
    cfg.write_text_atomic(dest, text[:ini] + "\n".join(lines) + text[end:])
    return True


def stamp_keywords(dest, keywords: list) -> bool:
    """Estampa `keywords:` en una nota de paper que no las tiene. Cirugía sobre el TEXTO, como
    `merge_frontmatter_list` —preserva byte a byte el resto del frontmatter, incluida la extracción
    LLM— pero con una diferencia que aquélla no cubre: acá el campo puede estar **ausente** (la nota
    nació antes de D-17) y `merge_frontmatter_list` devuelve False sin tocar nada, a propósito, para
    no inventar posiciones. Se inserta después de `facets:`, que es su vecino en el stub.

    **Add-only estricto:** si la nota ya trae `keywords` con contenido, no se toca. Devuelve True si
    modificó."""
    text = dest.read_text(encoding="utf-8")
    lim = cfg.fm_bounds(text)             # AUD-147
    if lim is None or not keywords:
        return False
    ini, end = lim
    head = text[ini:end]
    try:
        data = yaml.safe_load(head) or {}
    except yaml.YAMLError:
        return False                    # frontmatter roto: lo surface el lint, acá no se toca
    if data.get("keywords"):
        return False                    # ya poblado: add-only
    lines = head.split("\n")
    linea = "keywords: " + yaml.safe_dump(list(keywords), default_flow_style=True,
                                          allow_unicode=True).strip()
    idx = next((i for i, ln in enumerate(lines) if ln.startswith("keywords:")), None)
    if idx is not None:
        lines[idx] = linea              # `keywords: []` (o null) de una nota post-D-17 vacía
    else:
        ancla = next((i for i, ln in enumerate(lines) if ln.startswith("facets:")), None)
        if ancla is None:
            return False                # cabecera fuera del contrato: no adivinar
        j = ancla + 1
        while j < len(lines) and lines[j].lstrip().startswith("- "):
            j += 1                      # `facets:` en bloque: saltar sus ítems
        lines[j:j] = [linea]
    cfg.write_text_atomic(dest, text[:ini] + "\n".join(lines) + text[end:])
    return True


def restamp_keywords() -> int:
    """Backfill D-17: estampa `keywords:` en las notas de paper que nacieron sin ellas, leyendo el
    registro de `build/<slug>/ads.json` (ADS ya las devolvía; la nota las tiraba).

    Hace falta porque la lente matchea **título + abstract + keywords**: sin ellas, re-clasificar
    desde la nota da un veredicto distinto del que dio el ingest — un diff inventado. Son lo que
    hace posible el diff de lente **offline** (D-49).

    ⚠ **`build/` es scratch gitignored.** Sin él no hay de dónde sacarlas y esto **no puede
    inventar un cero**: se dice cuántas notas quedaron sin cubrir y por qué. Recuperarlas ahí es un
    fetch de metadata por bibcode — sub-modo *refrescar* de `maintain`."""
    kw: dict = {}
    for aj in sorted((cfg.ROOT / "build").glob("*/ads.json")) if (cfg.ROOT / "build").exists() else []:
        try:
            data = cfg.as_map(json.loads(aj.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
        for r in cfg.as_list(data.get("records")):
            if isinstance(r, dict) and r.get("bibcode") and cfg.as_list(r.get("keyword")):
                kw.setdefault(r["bibcode"], cfg.as_list(r["keyword"]))
    notes = sorted(cfg.PAPERS.glob("*.md")) if cfg.PAPERS.exists() else []
    changed = sin_registro = 0
    for n in notes:
        fm = cfg.split_fm(n.read_text(encoding="utf-8"))
        if fm.get("keywords"):
            continue
        bib = fm.get("bibcode") or n.stem
        if bib not in kw:
            sin_registro += 1
            continue
        changed += stamp_keywords(n, kw[bib])
    cfg.print_seguro(f"keywords: {changed} de {len(notes)} notas estampadas "
                     f"(desde {len(kw)} registros de build/*/ads.json)")
    if sin_registro:
        cfg.print_seguro(
            f"  ⚠ {sin_registro} nota(s) sin keywords y sin registro en build/ — NO es 0, es "
            f"'no había de dónde': build/ es scratch gitignored. Recuperarlas es un fetch de "
            f"metadata por bibcode (sub-modo refrescar de `maintain`), o re-correr la cadena.")
    return 0


def restamp_headers() -> int:
    """Backfill #69: barre TODAS las fichas y conceptos y les estampa la cabecera si les falta.
    Para el corpus creado antes de que la cabecera existiera (medido en una bóveda real: 22 de 25
    notas sin el aviso de capa LLM). Regenerar con --force sí escribiría la cabecera, pero PISA la
    síntesis LLM, que es el trabajo caro: por eso esto es cirugía y no regeneración."""
    notes = sorted(cfg.STARS.glob("*.md")) if cfg.STARS.exists() else []
    notes += sorted(cfg.CONCEPTS.glob("*/*.md")) if cfg.CONCEPTS.exists() else []
    notes += sorted(cfg.PAPERS.glob("*.md")) if cfg.PAPERS.exists() else []   # #247
    changed = sum(1 for n in notes if stamp_header(n))
    cfg.print_seguro(f"cabeceras: {changed} de {len(notes)} estampadas "
          f"(aviso de capa LLM + línea del generador, versión leída del frontmatter)")
    if changed:
        cfg.print_seguro("  → ahora los estampadores de cabecera (p. ej. el puntero de búsqueda de #64) "
              "pueden actuar sobre esas notas; re-corré la cadena o make_notes del sujeto.")
    return 0


#: #277 · la marca por la que se reconoce el aviso de capa LLM en el cuerpo. La miden el lint y
#: `stamp_header`, así que vive una sola vez: con dos literales, el detector y el reparador pueden
#: dejar de hablar del mismo texto sin que nadie se entere.
AVISO_LLM_MARCA = "Capa LLM"


#: #269 · el bullet de anotación ANTERIOR a 1.117.0, embebido sólo para que el migrador reconozca
#: el stub viejo. Se borra cuando la migración termine: una copia del texto retirado que sobreviva
#: es exactamente lo que este issue arregla.
_BULLET_ANOTACION_VIEJO = (
    "- **Cómo anotar cada valor (#103):** pegá el **nº de línea** del `.txt` (`grep -n`, nunca "
    "`splitlines()`) junto a cada número que copies, y el **régimen** en el que la fuente lo afirma "
    "(muestra, época, corte de datos, modelo). Si la fuente **atribuye el valor a otro trabajo** "
    "(«according to X», «(X et al.)»), marcalo **segunda mano** y citá a X: el número **no es de "
    "esta fuente**. Copiá el **tiempo verbal y el cuantificador tal cual** (si dice «was "
    "associated», no escribas «is associated»; si dice «el 75 % de la muestra», no escribas «la "
    "muestra»). ⛔ No escribas prosa que compare este paper con otro — comparar es `inferencia` "
    "y va al `## Inventario por eje` de la ficha, no acá._")


def _no_vista_declarada(fm: dict, stem: str, sujetos: set) -> bool:
    """Did this note declare `no_vista` for the subject of this roll-up? (#268)

    ⛔ A broken `no_vista` must not abort the chain: `papers_universe` runs inside note writing, and
    one malformed note cannot stop the whole pass (same doctrine as `fm_broken` in the lint). It
    falls back to the plain ladder, and the lint reports the malformed field on its own."""
    try:
        declaradas = {v["sujeto"] for v in cfg.load_no_vista(fm, entry=stem)}
    except cfg.VistasError:
        return False
    return bool(declaradas & sujetos)


def restamp_vista_stub() -> int:
    """Migration #269: re-stamps the view template on notes that still carry the OLD one.

    Needed because `harvest_views.write_view_section` only overwrites a view section **while it is
    still the template**, comparing against the live `vista_block`. Changing the template therefore
    makes every already-written stub stop matching, and the next harvest would print «ya tiene prosa
    redactada → NO se pisa» and **write no view at all** — the fix would break the harvest it is
    meant to unblock.

    Only sections that are byte-for-byte the old template are touched: a view with real prose is
    left alone (its anchors hang off the exact text)."""
    import harvest_views as hv          # import local: `harvest_views` importa `make_notes`
    notes = sorted(cfg.PAPERS.glob("*.md")) if cfg.PAPERS.exists() else []
    tocadas = 0
    for dest in notes:
        text = dest.read_text(encoding="utf-8")
        fm = cfg.split_fm(text) or {}
        for v in cfg.as_list(fm.get("vistas")):
            if not isinstance(v, dict) or not (suj := str(v.get("sujeto") or "").strip()):
                continue
            theme = str(v.get("tipo") or "") == "theme"
            span = hv.section_span(text, f"## Vista — {suj}")
            if span is None:
                continue
            actual = text[span[0]:span[1]]
            viejo = vista_block(suj, theme).replace(_BULLET_ANOTACION, _BULLET_ANOTACION_VIEJO)
            if hv._norm(actual) != hv._norm(viejo):
                continue                 # o ya está migrada, o tiene prosa: no se toca
            sep = "\n\n" if span[1] < len(text) else "\n"
            text = text[:span[0]] + vista_block(suj, theme).rstrip("\n") + sep + text[span[1]:]
            tocadas += 1
        if text != dest.read_text(encoding="utf-8"):
            cfg.write_text_atomic(dest, text)
    cfg.print_seguro(f"vistas: {tocadas} sección(es) de stub re-estampadas con la plantilla vigente "
                     f"(#269: la anterior mandaba citar por nº de línea del `.txt`, la doctrina que "
                     f"#205 retiró)")
    return 0


def clean_catalog_markup_notes() -> int:
    """Backfill #271: strips the catalog's raw markup from `## Abstract` in every paper note.

    `## Abstract` is **verbatim from catalog** and ADS returns live markup: `<SUB>`, `<SUP>`,
    `<ASTROBJ>`, `<A href>`, `<P />`. Measured on a real vault: **249 occurrences in 42 notes**, and
    what they do when rendered is not cosmetic — `<ASTROBJ>HD 40307</ASTROBJ>` leaves the object's
    name **invisible** in a renderer that does not escape, `<A href>` turns a copy promised verbatim
    into a live link, and `<SUB>` silently drops the subscript. Worse, the result depends on the
    parser, so the layer the contract calls **auditable** says different things to different readers.

    ⚠ Only the `## Abstract` section is touched, and only with `cfg.clean_catalog_markup` — the same
    function the three backends now use, so a note cleaned here reads exactly like one ingested
    today. ⛔ Two consumers read those bytes back —the duplicate detector (#216) and the offline lens
    diff (D-49)— so the command reports how many notes it changed: whoever runs it re-measures."""
    notes = sorted(cfg.PAPERS.glob("*.md")) if cfg.PAPERS.exists() else []
    tocadas = 0
    for dest in notes:
        text = dest.read_text(encoding="utf-8")
        ini = cfg.section_start(text, "## Abstract")
        if ini < 0:
            continue
        fin = text.find("\n## ", ini + 1)
        fin = len(text) if fin < 0 else fin
        limpio = cfg.clean_catalog_markup(text[ini:fin])
        if limpio == text[ini:fin]:
            continue
        cfg.write_text_atomic(dest, text[:ini] + limpio + text[fin:])
        tocadas += 1
    cfg.print_seguro(
        f"markup de catálogo: {tocadas} de {len(notes)} notas de paper limpiadas en `## Abstract` "
        f"(#271). ⚠ Re-medí el detector de duplicados (#216) y el diff de lente offline (D-49): "
        f"los dos leen esos bytes.")
    return 0


def restamp_abstracts() -> int:
    """Backfill #277: writes the `## Abstract` section into every paper note that lacks it.

    The section is the body's only **auditable** layer and `classify_offline` reads it to
    re-classify without `build/` (D-49), yet nothing ever checked it was there: measured on a real
    vault, **39 of 138** notes had no `## Abstract` with the lint at rc 0 — the off-ADS stub never
    wrote it. The content is the placeholder, never invented: what is missing is the SECTION, and
    the harvester fills it from the PDF on the next extraction (it overwrites the placeholder,
    never a verbatim already in place).

    Surgery, not regeneration: the section goes right after the header blockquote and no prose is
    touched. Idempotent."""
    notes = sorted(cfg.PAPERS.glob("*.md")) if cfg.PAPERS.exists() else []
    changed = 0
    for dest in notes:
        text = dest.read_text(encoding="utf-8")
        if cfg.section_start(text, "## Abstract") >= 0:
            continue
        i = text.find(GENERATOR_LINE)
        if i < 0:
            # Sin la línea del generador no hay dónde anclar: se dice, no se adivina un punto de
            # inserción (mismo criterio que `stamp_estado`). `--restamp-headers` la pone primero.
            cfg.print_seguro(f"  ⚠ {dest.name}: sin la línea del generador — corré "
                             f"`--restamp-headers` antes")
            continue
        corte = text.find("\n", i) + 1
        nuevo = (text[:corte] + f"\n## Abstract\n{cfg.ABSTRACT_PLACEHOLDER}\n" + text[corte:])
        cfg.write_text_atomic(dest, nuevo)
        changed += 1
    cfg.print_seguro(f"abstracts: {changed} de {len(notes)} notas de paper recuperaron su "
                     f"`## Abstract` (contenido `{cfg.ABSTRACT_PLACEHOLDER}`: falta la copia de "
                     f"catálogo, la completa la próxima extracción)")
    return 0


# `field` viejo (dentro de planets[]) → clave del frontmatter con el valor de NEA, para materializar
# la posición `{source: ground_truth}` con su valor real. `existence` no tiene valor numérico: lo que
# NEA sostiene es el `status` del planeta.
LEGACY_FIELD_TO_GT = {"P": "P_days", "K": "K_ms", "e": "e", "msini": "mass_earth",
                      "existence": "status"}


def migrate_verif_archivo(dest) -> int:
    """Migración #117 de UNA nota: prefija cada celda `Hash fuente` con el archivo que se leyó
    (`txt:` / `pdf:`). Devuelve cuántas filas cambió.

    ⛔ **No infiere del frontmatter: deduce del HASH.** Inferir de un campo del frontmatter
    escribiría una declaración **falsa** justo en las filas que motivaron el issue. En cambio se
    calculan los dos hashes y se declara el que **coincide** con lo que la fila ya guardaba: eso no
    es heurística, es identificar el archivo por su huella.

    Si no coincide ninguno, el par está vencido igual (hay que re-verificarlo) y ahí sí se cae a la
    regla del frontmatter, avisando: la fila declara algo que el próximo `verify-citations` va a
    reescribir. Cirugía a nivel celda: no toca la prosa. Idempotente — una celda ya prefijada se
    saltea.

    @inv INV-107"""
    if not dest.exists():
        return 0
    text = dest.read_text(encoding="utf-8")
    filas = lb.parse_verif_table(text)
    if not filas:
        return 0
    fm = cfg.split_fm(text)
    cambios, lineas = 0, text.split("\n")
    for fila in filas:
        if fila.source_kind is not None:
            continue                                  # ya migrada
        if not fila.source_hash:
            cfg.print_seguro(f"  ⚠ {dest.name}: la fila de {fila.bibcode} no tiene hash de fuente — "
                             f"no hay archivo que identificar; re-verificar el par")
            continue
        bib = fila.bibcode
        h_txt = next((lb.source_hash(f) for f in cfg.FULLTEXT.glob(f"**/{safe_name(bib)}.txt")), None)
        h_pdf = next((lb.bytes_hash(f) for f in cfg.PDFS.glob(f"**/{safe_name(bib)}.pdf")), None)
        if fila.source_hash and fila.source_hash == h_pdf:
            kind = "pdf"
        elif fila.source_hash and fila.source_hash == h_txt:
            kind = "txt"
        else:
            # ninguno coincide ⇒ el par ya está vencido. Se declara `txt:`, que es de donde se
            # leía cuando estas filas se escribieron (#205 movió la lectura al PDF), y se avisa: no
            # es una verificación, es un puntero para re-verificar.
            kind = "txt"
            cfg.print_seguro(f"  ⚠ {dest.name}: la fila de {bib} no coincide con ningún archivo en "
                             f"disco — se declara `txt:` (el default de cuando se escribió) y hay "
                             f"que re-verificar el par")
        viejo = f"| {fila.source_hash} |"
        for i, ln in enumerate(lineas):
            if ln.lstrip().startswith("|") and viejo in ln and fila.anchor in ln:
                lineas[i] = ln.replace(viejo, f"| {kind}:{fila.source_hash} |", 1)
                cambios += 1
                break
    if cambios:
        cfg.write_text_atomic(dest, "\n".join(lineas))
    return cambios


def migrate_all_verif_archivo() -> int:
    """Backfill #117 sobre toda la bóveda. Toca sólo notas con bloque de verificación."""
    total = tocadas = 0
    for nota in sorted(cfg.WIKI.rglob("*.md")):
        n = migrate_verif_archivo(nota)
        if n:
            total, tocadas = total + n, tocadas + 1
            cfg.print_seguro(f"  → {nota.relative_to(cfg.WIKI)}: {n} fila(s)")
    cfg.print_seguro(f"#117: {total} fila(s) declaran su archivo en {tocadas} nota(s).")
    return 0


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
    lim = cfg.fm_bounds(text)             # AUD-147
    if lim is None:
        return False
    ini, end = lim
    try:
        front = yaml.safe_load(text[ini:end]) or {}
    except yaml.YAMLError:
        cfg.print_seguro(f"  ⚠ {dest.name}: frontmatter no parseable — migralo a mano")
        return False
    # Cobarde ante cualquier forma que no entiende: si `planets` no es una lista de mapas, o
    # `disputes` a nivel nota no es una lista, NO toca el archivo. Antes un solo planeta mal formado
    # tiraba `migrate_all_disputes` a mitad del barrido y dejaba la bóveda medio migrada, y un
    # `disputes:` escalar se convertía en una lista de CARACTERES escrita a disco.
    planets = front.get("planets")
    if not isinstance(planets, list) or not all(isinstance(pl, dict) for pl in planets if pl):
        cfg.print_seguro(f"  ⚠ {dest.name}: `planets` no es una lista de mapas — migralo a mano")
        return False
    if "disputes" in front and not isinstance(front.get("disputes") or [], list):
        cfg.print_seguro(f"  ⚠ {dest.name}: `disputes` a nivel nota no es una lista — migralo a mano")
        return False
    if not any((pl or {}).get("disputes") for pl in planets):
        return False
    nuevas = list(front.get("disputes") or [])
    for pl in planets:
        letra = str((pl or {}).get("letter") or "").strip()      # `letter: null` daba "None.K"
        # NO hacer `pop` acá: hasta no saber que la entrada efectivamente migró, el dato sigue
        # siendo el único respaldo en disco de esa disputa (bibcode + valor discrepante). `pop`
        # antes de las guardas de forma era el bug — el `continue` "cobarde" saltaba con el dato
        # YA fuera del dict, y el `write_text` de abajo lo borraba para siempre.
        viejas = (pl or {}).get("disputes")
        if viejas is None:
            continue
        if not isinstance(viejas, list):
            cfg.print_seguro(f"  ⚠ {dest.name}: `planets[{letra or '?'}].disputes` no es una lista — esa quedó "
                  f"sin migrar, revisala a mano")
            continue                          # se deja intacta en el planeta: nada que pop-ear
        sin_migrar = []                       # elementos que no se pudieron migrar: se quedan acá
        for d in viejas:
            if not isinstance(d, dict):
                cfg.print_seguro(f"  ⚠ {dest.name}: disputa vieja de `{letra or '?'}` que no es un mapa — sin "
                      f"migrar, revisala a mano")
                sin_migrar.append(d)
                continue
            campo = str(d.get("field") or "").strip()
            gt_key = LEGACY_FIELD_TO_GT.get(campo)
            gt_pos = {"source": "ground_truth"}
            if gt_key is not None and pl.get(gt_key) is not None:
                gt_pos["value"] = pl.get(gt_key)
            # El lado del paper se arma con la MISMA regla que el de NEA: `value` sólo si hay valor.
            # `alt` era exclusivo de las disputas de VALOR, así que en una de `existence` —el caso
            # más frecuente— quedaba `value: null`, que por la convención del otro polo se lee como
            # "esta fuente calla": lo contrario de lo que el paper sostiene.
            paper_pos = {"ref": d.get("ref")}
            if d.get("alt") is not None:
                paper_pos["value"] = d["alt"]
            if not d.get("ref"):
                cfg.print_seguro(f"  ⚠ {dest.name}: disputa `{campo or '?'}` sin `ref` → la posición queda sin "
                      f"quién la sostenga y el lint la va a bloquear: agregá el bibcode a mano")
            if not campo:
                cfg.print_seguro(f"  ⚠ {dest.name}: disputa de `{letra or '?'}` sin `field` → queda sin eje y "
                      f"el lint la va a bloquear: nombrá el eje a mano")
            nueva = {"field": f"{letra}.{campo}" if (letra and campo) else campo,
                     "posiciones": [paper_pos, gt_pos]}
            if d.get("note"):
                nueva["note"] = d["note"]
            nuevas.append(nueva)
        # Recién acá se decide qué pasa con `planets[].disputes`: lo que migró se saca (ya vive en
        # `nuevas`), lo que no migró se queda escrito — visible, no perdido — para revisar a mano.
        if sin_migrar:
            pl["disputes"] = sin_migrar
        else:
            pl.pop("disputes", None)
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
    cfg.write_text_atomic(dest, text[:ini]
                          + _fm_preservando_comentarios(fm(front), text[ini:end], dest)
                          + text[end:])
    cfg.print_seguro(f"  {dest.name}: {len(nuevas)} disputa(s) migradas a posiciones explícitas")
    return True


def migrate_all_facets() -> int:
    """Migrador de un solo uso de R-5: renombra `topics:` → `facets:` en las notas de paper.

    INV-64 pide **dos piezas** por cambio de schema: migración idempotente y detector bloqueante de
    la forma vieja. R-5 entregó el detector y **no** el migrador: el mensaje del lint mandaba a
    "renombrarlo" a mano, nota por nota (medido en una instancia real: 908 de 908 notas traían el
    campo viejo). Un cambio de schema sin migrador convierte a la instancia en trabajo manual, que
    es exactamente lo que la regla de "sin capa de retrocompatibilidad" asume resuelto.

    Renombre **quirúrgico a nivel línea** (como `merge_frontmatter_list`): no toca la extracción
    LLM ni el cuerpo. Si la nota ya trae `facets:`, el `topics:` residual se **borra** en vez de
    pisarlo — el vigente manda.  @inv INV-64"""
    n = 0
    for f in sorted(cfg.PAPERS.glob("*.md")):
        texto = f.read_text(encoding="utf-8")
        span = cfg.frontmatter_span(texto)
        if span is None:
            continue
        head, resto = span
        lineas = head.split("\n")
        if not any(ln.startswith("topics:") for ln in lineas):
            continue
        ya_tiene = any(ln.startswith("facets:") for ln in lineas)
        out, dropping = [], False
        for ln in lineas:
            if dropping:
                if ln[:1] in (" ", "\t", "-"):
                    if not ya_tiene:
                        out.append(ln)
                    continue
                dropping = False
            if ln.startswith("topics:"):
                dropping = True
                if not ya_tiene:
                    out.append("facets:" + ln[len("topics:"):])
                continue
            out.append(ln)
        # ⚠ Reconstrucción EXACTA: `head` ya viene con su `\n` inicial y final desde
        # `frontmatter_span`. Agregar `"\n---\n"` metía una línea en blanco DENTRO del
        # frontmatter y `resto.lstrip("\n")` borraba la de después del `---`: las dos rompían el
        # "byte a byte" que el docstring promete (AUD-38/39, auditoría 2026-08-24).
        cfg.write_text_atomic(f, "---" + "\n".join(out) + "---" + resto)
        n += 1
    cfg.print_seguro(f"`topics:` → `facets:` en {n} nota(s) de paper (R-5).")
    return n


def migrate_all_registros() -> int:
    """Migrador de un solo uso de D-28: `busqueda:` (mapa, una corrida) → `busquedas: []`.

    La otra mitad que INV-64 pedía y no existía: el lint bloqueaba el registro viejo y mandaba a
    "re-correr la cadena", que cuesta una pasada de red entera **y pierde la corrida vieja**. El
    registro es el único artefacto no regenerable de la bóveda, así que la corrida se **pliega**
    (marcada como pre-D-28), no se recrea.  @inv INV-64"""
    n = 0
    for rf in sorted(cfg.REGISTRO.glob("*.yaml")) if cfg.REGISTRO.exists() else []:
        slug = rf.stem
        data = cfg.load_registro(slug)
        vieja = data.get("busqueda")
        if not isinstance(vieja, dict):
            continue
        previas = [b for b in cfg.as_list(data.get("busquedas")) if isinstance(b, dict)]
        data.pop("busqueda", None)
        data["busquedas"] = ([{**vieja, "schema": "pre-D-28 (plegada al migrar; una sola corrida)"}]
                             if not previas else previas)
        cfg.save_registro(slug, data)
        n += 1
    cfg.print_seguro(f"`busqueda:` → `busquedas: []` en {n} registro(s) (D-28).")
    return n


def migrate_all_txt_fields() -> int:
    """Migrador de un solo uso de #205: saca `symbols_lost:` y `fulltext_layout:` de las notas.

    Los dos campos existían para una sola decisión —**¿el extractor lee el `.txt` o el PDF?**— y esa
    decisión ya no se toma: la fuente es el PDF, siempre. Un campo sin lector no se deja «por las
    dudas»: se lee como un gate vivo, y éstos además **mienten**. Medido el 2026-08-28: un paper con
    `symbols_lost: False` y `single-column` había perdido igual el radical `√`, la prima de `p′` y
    superíndices de transpuesta.

    Es borrado puro y no pierde nada recuperable: los dos se derivan del `.txt`, que sigue en disco.
    Edición **quirúrgica a nivel línea** (como `migrate_all_bearing`): no toca la extracción LLM ni
    el cuerpo.  @inv INV-26"""
    n = 0
    for f in sorted(cfg.PAPERS.glob("*.md")):
        texto = f.read_text(encoding="utf-8")
        lim = cfg.fm_bounds(texto)        # AUD-147
        if lim is None:
            continue
        ini, fin = lim
        head, resto = texto[ini:fin], texto[fin:]
        lineas = [ln for ln in head.split("\n")
                  if not ln.startswith(("symbols_lost:", "fulltext_layout:"))]
        if len(lineas) == len(head.split("\n")):
            continue
        cfg.write_text_atomic(f, texto[:ini] + "\n".join(lineas) + resto)
        n += 1
    return n


def migrate_all_source_fields() -> tuple[int, list]:
    """One-shot migrator for #296: a `pdf_source`/`fulltext_source` outside its closed vocabulary.

    The value becomes `null` —which is the legitimate value for *unknown*, and not "published"—
    and the prose that was living in the field is **moved, never dropped**: measured, one of the
    two real cases was a legitimate acquisition note (*«the user gets it; ADS only indexes a REVIEW
    of the book»*) that ended up in the wrong field because the schema had nowhere to put it. It
    goes to `pending_motivo` when the note declares `pending_source`, and to `salvedades`
    otherwise, so the migration cannot destroy information the operator wrote on purpose.

    Returns `(migrated, [(stem, where the prose went)])`, and writes nothing when the resulting
    frontmatter stops parsing (#244)."""
    n, movidas = 0, []
    for f in sorted(cfg.PAPERS.glob("*.md")):
        texto = f.read_text(encoding="utf-8")
        fm = cfg.split_fm(texto)
        lim = cfg.fm_bounds(texto)
        if not fm or lim is None:
            continue
        malos = {campo: str(fm[campo]).strip()
                 for campo, ok in (("pdf_source", cfg.PDF_SOURCE_OK),
                                   ("fulltext_source", cfg.FULLTEXT_SOURCE_OK))
                 if fm.get(campo) not in (None, "") and str(fm[campo]).strip() not in ok}
        if not malos:
            continue
        ini, fin = lim
        head, resto = texto[ini:fin], texto[fin:]
        lineas = _drop_keys(head, tuple(f"{c}:" for c in malos))
        destino = "pending_motivo" if fm.get("pending_source") else "salvedades"
        for campo, valor in sorted(malos.items()):
            lineas.append(f"{campo}: null")
            nota = f"[{campo} decía] {valor}"
            if destino == "pending_motivo" and not str(fm.get("pending_motivo") or "").strip():
                lineas = [ln for ln in lineas if not ln.startswith("pending_motivo:")]
                lineas.append(f"pending_motivo: {json.dumps(nota, ensure_ascii=False)}")
            else:
                lineas.append(f"salvedades:\n  - {json.dumps(nota, ensure_ascii=False)}"
                              if not fm.get("salvedades") else
                              f"# ⚠ #296 — mové a mano esta nota: {nota}")
        nuevo = texto[:ini] + "\n".join(lineas) + resto
        if not cfg.split_fm(nuevo):
            cfg.print_seguro(f"  ⛔ {f.name}: la migración dejaría el frontmatter sin parsear — NO "
                             f"se escribe. Movelo a mano.")
            continue
        cfg.write_text_atomic(f, nuevo)
        movidas.append((f.stem, destino))
        n += 1
    return n, movidas


EXTRACCION_VIEJA_RE = re.compile(r"^##\s+Extracci[oó]n\s*\(LLM\)\s*$", re.M)


def migrate_all_vistas() -> tuple[int, list]:
    """One-shot migrator for #188: `## Extracción (LLM)` → `vistas[]` + `## Vista — <sujeto>`.

    ⛔ AUD-175 / INV-64 — #188 shipped a **blocking detector with no migrator**, which is half of
    the contract this repo set itself: «a new schema means a one-shot migrator plus a blocking
    detector, never a tolerant reader». Without it every note older than 1.68.0 stays red with no
    way out but hand-editing them one by one (measured in a real vault: 908 paper notes).

    What can be migrated and what cannot. The view's **subject** comes from the note's own claim
    (`stars` / `thesis_links`): with exactly **one** it is unambiguous. With two or more it is NOT
    guessed — picking one would assert a reading nobody performed from there — and the note comes
    back in the ambiguous list along with its candidates.

    `fecha` is NOT stamped: the old extraction did happen, but **when** and **through which lens**
    is not on record, and absent means exactly «not on record» (#188). The lint then reports it as
    *vista sin fecha*, which is backlog and is the truth. `fuente` (#207) is not invented either.

    Returns `(migrated, ambiguous)`."""
    migradas, ambiguas = 0, []
    for f in sorted(cfg.PAPERS.glob("*.md")) if cfg.PAPERS.exists() else []:
        text = f.read_text(encoding="utf-8")
        if not EXTRACCION_VIEJA_RE.search(text):
            continue
        fm = cfg.split_fm(text)
        if cfg.as_list(fm.get("vistas")):
            continue                      # ya migrada (o escrita con el schema nuevo)
        estrellas = [str(x) for x in cfg.as_list(fm.get("stars")) if str(x).strip()]
        temas = [str(x) for x in cfg.as_list(fm.get("thesis_links")) if str(x).strip()]
        reclamos = [(n, "star") for n in estrellas] + [(n, "theme") for n in temas]
        if len(reclamos) != 1:
            ambiguas.append((f.stem, [n for n, _ in reclamos]))
            continue
        sujeto, tipo = reclamos[0]
        lim = cfg.fm_bounds(text)
        if lim is None:
            ambiguas.append((f.stem, []))
            continue
        ini, end = lim
        bloque = yaml.safe_dump({"vistas": [{"sujeto": sujeto, "tipo": tipo}]},
                                sort_keys=False, allow_unicode=True, default_flow_style=False)
        head = text[ini:end].rstrip("\n") + "\n" + bloque.rstrip("\n")
        cuerpo = EXTRACCION_VIEJA_RE.sub(f"## Vista — {sujeto}", text[end:])
        cfg.write_text_atomic(f, text[:ini] + head + cuerpo)
        migradas += 1
    return migradas, ambiguas


def migrate_all_bearing() -> int:
    """Migrador de un solo uso de D-21: saca `bearing:` del frontmatter de las notas de paper.

    La **postura** de un paper respecto de una tesis no es propiedad del paper —depende de la tesis,
    y un paper puede tocar varias—, así que vive en la tabla de evidencia de la hipótesis. Dejarla
    en el paper obligaba a elegir una sola postura para todas.

    Es borrado puro y no pierde nada recuperable: el dato viejo era un único valor para N tesis, o
    sea que ya estaba mal por construcción. Edición **quirúrgica a nivel línea** (como
    `merge_frontmatter_list`): no toca la extracción LLM ni el cuerpo.  @inv INV-13"""
    n = 0
    for f in sorted(cfg.PAPERS.glob("*.md")):
        texto = f.read_text(encoding="utf-8")
        lim = cfg.fm_bounds(texto)        # AUD-147
        if lim is None:
            continue
        ini, fin = lim
        head, resto = texto[ini:fin], texto[fin:]
        lineas = [ln for ln in head.split("\n") if not ln.startswith("bearing:")]
        if len(lineas) == len(head.split("\n")):
            continue
        cfg.write_text_atomic(f, texto[:ini] + "\n".join(lineas) + resto)
        n += 1
    return n


def migrate_all_disputes() -> int:
    """Backfill #71 sobre toda la bóveda. Ver migrate_disputes para el porqué del alcance."""
    # @inv INV-64
    notes = sorted(cfg.STARS.glob("*.md")) if cfg.STARS.exists() else []
    changed = sum(1 for n in notes if migrate_disputes(n))
    cfg.print_seguro(f"disputas: {changed} de {len(notes)} ficha(s) migradas al schema con posiciones (#71)")
    if changed:
        cfg.print_seguro("  → el frontmatter se re-serializó (la prosa NO se tocó): revisá el diff antes de "
              "commitear.")
    else:
        cfg.print_seguro("  → nada que migrar. (El lint NO lee el schema viejo: si queda alguno, lo reporta "
              "como bloqueante en vez de ignorarlo en silencio.)")
    return 0


def sync_mirror() -> int:
    """Backfill: rellena el frontmatter de `stars/` —espejo puro de NEA (#70)— con lo que el
    ground-truth trae y la ficha todavía tiene en `null`. Resuelve el residuo medido al migrar una
    instancia de una versión anterior (1.11.0 → 1.22.1): 13 contradicciones que el lint bloqueaba
    campo por campo, 12 de ellas el mismo caso trivial —`campo: null` en la ficha, valor en NEA—
    que hoy hay que llenar a mano, planeta por planeta.

    **Contrato ADD-ONLY y en un solo sentido.** La 13ª contradicción medida (`hd40307
    P_rot_days: 48` con NEA sin `st_rotp`) es la que define la frontera, no una excepción a
    ignorar: ese número salió de literatura, y decidir qué hacer con él —adoptarlo, borrarlo, o
    copiarlo hacia el ground-truth— es DECISIÓN DEL CONSUMIDOR, que es justo lo que la regla #0 de
    CLAUDE.md le prohíbe al migrador (y volvería a romper #70, en la otra dirección). Por eso:
      · ficha en `null` + ground-truth con valor  → se copia (el único caso que se toca).
      · ficha con valor + ground-truth en `null`  → se deja y se reporta: es un número de
        literatura, no relleno mecánico (va al cuerpo citado, o a `disputes[]` si hay desacuerdo).
      · ficha y ground-truth con valores DISTINTOS → se deja y se reporta: es una `disputes[]`, no
        un error de sincronización — pisarlo borraría una posición sin dejar rastro.
      · planeta en la ficha sin contraparte en el ground-truth (o viceversa) → no se toca: qué
        planetas lista la ficha es una contradicción aparte que el lint ya reporta (podría ser una
        señal no confirmada → `disputes` como `<letra>.existence`); agregar un planeta entero no es
        sincronizar un campo.

    Reusa el mapeo y el comparador de `lint.py` (`MIRROR_HOST`, `MIRROR_PLANET`, `same_value`) para
    que el espejo del lint y el del migrador no puedan divergir — si el lint cambia qué campos
    espeja, este backfill los sigue solo. El import es LOCAL (no al tope del archivo): `lint.py`
    importa de `make_notes.py` a nivel de módulo (`find_header_line`, `GENERATOR_LINE`), así que un
    import arriba crearía un ciclo; adentro de la función, cuando se llama, `make_notes` ya terminó
    de cargar y el ciclo no existe.

    Como el resto de la familia de migradores del archivo: no toca la prosa (re-serializa sólo el
    frontmatter, igual que `migrate_disputes`), es idempotente (segunda corrida, cero cambios: ya
    no hay más `null` que rellenar) y sin ground-truth para una ficha no hace nada —sin autoridad
    no hay contra qué espejar, y tocarla igual sería inventar."""
    from lint import MIRROR_HOST, MIRROR_PLANET, same_value

    def reportar(nombre: str, dest_name: str, val_ficha, val_gt) -> None:
        nonlocal reportados
        if val_gt is None:
            cfg.print_seguro(f"  {dest_name}: `{nombre}` sin tocar — la ficha tiene {val_ficha!r} y el "
                  f"ground-truth no trae el valor: es un número de literatura, no relleno mecánico "
                  f"(documentalo en el cuerpo con su [[bibcode]], o revisá si corresponde una "
                  f"`disputes[]`)")
        else:
            cfg.print_seguro(f"  {dest_name}: `{nombre}` sin tocar — ficha={val_ficha!r} vs "
                  f"ground-truth={val_gt!r}: valores distintos son una `disputes[]`, no un error de "
                  f"sincronización")
        reportados += 1

    notes = sorted(cfg.STARS.glob("*.md")) if cfg.STARS.exists() else []
    rellenados = reportados = 0
    for dest in notes:
        text = dest.read_text(encoding="utf-8")
        lim = cfg.fm_bounds(text)         # AUD-147
    #  @inv INV-08
        if lim is None:
            continue
        ini, end = lim
        try:
            front = yaml.safe_load(text[ini:end]) or {}
        except yaml.YAMLError:
            cfg.print_seguro(f"  ⚠ {dest.name}: frontmatter no parseable — sincronizalo a mano")
            continue
        gt_path = cfg.GROUND_TRUTH / f"{dest.stem}.json"
        if not gt_path.exists():
            continue    # sin autoridad no hay contra qué espejar: no inventar
        try:
            gt = json.loads(gt_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cfg.print_seguro(f"  ⚠ {dest.name}: ground-truth no parseable — sincronizalo a mano")
            continue
        # `--sync-mirror` es el consumidor NUEVO (23-08) del ground-truth en disco; `lint.py`
        # (795-815) ya endurece este mismo artefacto campo por campo y sigue vivo — acá no había
        # NINGUNA de esas guardas y un `host`/`planets` con forma inesperada (edición a mano del
        # JSON, poco común pero posible) reventaba con `AttributeError` a mitad de la escritura en
        # las fichas (R8/R9). `cfg.as_map`/`cfg.as_list` no alcanzan solos: acá SÍ hace falta
        # reportar la forma inválida (con el nombre de la ficha) en vez de degradarla en silencio —
        # un backfill que no rellena nada y tampoco avisa es un falso limpio.
        raw_host = gt.get("host")
        if raw_host and not isinstance(raw_host, dict):
            cfg.print_seguro(f"  ⚠ {dest.name}: `host` del ground-truth no es un mapa ({raw_host!r}) "
                  "— sincronizalo a mano")
        host = cfg.as_map(raw_host)
        planets = front.get("planets")
        # Cobarde ante una forma que no entiende, mismo criterio que migrate_disputes: si
        # `planets` no es una lista de mapas, no tocar nada en vez de arriesgar basura escrita.
        if planets is not None and (not isinstance(planets, list)
                                     or not all(isinstance(pl, dict) for pl in planets if pl)):
            cfg.print_seguro(f"  ⚠ {dest.name}: `planets` no es una lista de mapas — sincronizalo a mano")
            continue
        raw_gt_planets = gt.get("planets")
        if raw_gt_planets and not isinstance(raw_gt_planets, list):
            cfg.print_seguro(f"  ⚠ {dest.name}: `planets` del ground-truth no es una lista — "
                  "sincronizalo a mano")
        gt_planets = {str(p.get("letter")): p for p in cfg.as_list(raw_gt_planets)
                      if isinstance(p, dict)}
        changed = False

        for campo, key in MIRROR_HOST:
            val, val_gt = front.get(campo), host.get(key)
            if campo not in front:
                # #272 — la clave que FALTA se escribe, aunque la autoridad calle: `mass_msun` entró
                # al schema después de que estas fichas se crearan, y sin la clave la nota evade el
                # espejo y el lint la reporta como schema incompleto. Escribir `null` es el estado
                # correcto (la autoridad contestó y no tiene el dato), no un campo a completar.
                front[campo] = val_gt
                changed = True
                rellenados += 1
                continue
            if same_value(val, val_gt):
                continue
            if val is None:
                front[campo] = val_gt
                changed = True
                rellenados += 1
            else:
                reportar(campo, dest.name, val, val_gt)

        for pl in (planets or []):
            ref = gt_planets.get(str((pl or {}).get("letter")))
            if ref is None:
                continue    # planeta sin contraparte en el GT: otra contradicción, no se toca acá
            for campo in MIRROR_PLANET:
                val, val_gt = pl.get(campo), ref.get(campo)
                if same_value(val, val_gt):
                    continue
                if val is None:
                    pl[campo] = val_gt
                    changed = True
                    rellenados += 1
                else:
                    reportar(f"{pl.get('letter')}.{campo}", dest.name, val, val_gt)

        if changed:
            cfg.write_text_atomic(dest, text[:ini]
                                  + _fm_preservando_comentarios(fm(front), text[ini:end], dest)
                                  + text[end:])

    cfg.print_seguro(f"sync-mirror: {rellenados} campo(s) rellenados desde el ground-truth "
          f"({len(notes)} ficha(s) revisadas); {reportados} sin tocar (motivo arriba de cada uno).")
    if reportados:
        cfg.print_seguro("  → lo sin tocar no es un fallo del backfill: es la parte que necesita juicio "
              "humano (número de literatura o disputa real). Resolvelo a mano.")
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
    cfg.print_seguro(f"  ⚠ year no numérico: {year!r} → queda null (completalo a mano en la nota si aplica)")
    return None


def parse_int(value, field: str) -> int | None:
    """Entero tolerante para metadata off-ADS: no numérico → null con aviso, no aborta."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        cfg.print_seguro(f"  ⚠ {field} no numérico: {value!r} → queda null")
        return None


def _yaml_block_item(v: str) -> str:
    """`v` written as a BLOCK-context scalar, so that PyYAML reads back the very same string.

    AUD-145: the merge edits the frontmatter as TEXT, so a value carrying YAML punctuation —a
    `: ` (which turns the item into a mapping), a leading `#`, a quote— was re-read as something
    else. `v not in current` then stayed true and the value was appended **on every run, without
    a ceiling**. Round-tripping through the dumper is what makes «add-only» actually idempotent.

    ⚠ Block context only: a comma is legal inside a plain block scalar and NOT inside a flow one,
    so the `field: [a, b]` branch dumps the whole list instead of quoting item by item.  @inv INV-139"""
    return yaml.safe_dump(v, default_flow_style=False, allow_unicode=True).strip().removesuffix("...").strip()


def merge_frontmatter_list(dest, field: str, values: list) -> bool:
    """Retro-linkeo add-only: agrega a la lista `field` del frontmatter de `dest` los `values`
    que falten. Edita el TEXTO en el lugar (no re-serializa el YAML) para preservar byte a byte
    el resto del frontmatter — orden, comentarios y todo lo que haya tocado la extracción LLM.
    Nunca saca ni pisa nada. Devuelve True si modificó el archivo.

    ⛔ **Una NEGATIVA se dice** (AUD-146 / INV-139). Seis de los siete `return False` no son «ya
    estaban»: son *no pude* —sin frontmatter, frontmatter sin cerrar, YAML roto, el campo no es
    lista, el campo no está, forma no reconocida—. El llamador cuenta el `False` como `skipped`,
    o sea «ya estaba linkeado», así que la entidad nueva **nunca entraba al roll-up** y nada lo
    decía. Los seis avisan por stderr nombrando archivo, campo y motivo; el único mudo es el
    legítimo (`not missing`), que es el caso normal e idempotente."""
    def _no(motivo: str) -> bool:
        """Say the refusal out loud and return False, so the caller's `skipped` is not a lie."""
        cfg.print_seguro(f"  ⚠ no pude linkear `{field}` en {dest.name}: {motivo}", file=sys.stderr)
        return False

    text = dest.read_text(encoding="utf-8")
    lim = cfg.fm_bounds(text)             # AUD-147
    #  @inv INV-16
    if lim is None:
        return _no("la nota no tiene frontmatter delimitado por dos líneas `---`")
    ini, end = lim
    head = text[ini:end]
    try:
        data = yaml.safe_load(head) or {}
    except yaml.YAMLError as exc:
        return _no(f"el frontmatter no parsea ({' '.join(str(exc).split())[:80]})")
    current = data.get(field) or []
    if not isinstance(current, list):
        return _no(f"`{field}` no es una lista (es {type(current).__name__})")
    missing = [v for v in values if v not in current]
    if not missing:
        return False                       # el ÚNICO mudo: no había nada que agregar (idempotente)
    lines = head.split("\n")
    idx = next((i for i, ln in enumerate(lines) if ln.startswith(f"{field}:")), None)
    if idx is None:
        # campo ausente: no inventar posición (el stub siempre lo trae)
        return _no(f"`{field}` no está en el frontmatter — no se inventa la posición")
    rest = lines[idx][len(field) + 1:].strip()
    if rest.startswith("[") and rest.endswith("]"):
        # Lista inline (`field: []` / `field: [a, b]`): se re-emite ENTERA con el dumper, no se
        # concatena texto. Partir por `,` rompía cualquier item que llevara una coma —propia o de
        # un valor nuevo— y en contexto flow la coma no se puede dejar sin comillas (AUD-145).
        lines[idx] = f"{field}: " + yaml.safe_dump(
            list(current) + list(missing), default_flow_style=True, allow_unicode=True).strip()
    elif rest == "" or rest.startswith("#") or data.get(field) is None:
        # lista en bloque (o campo null): insertar tras el último "- item" existente
        j = idx + 1
        while j < len(lines) and lines[j].lstrip().startswith("- "):
            j += 1
        indent = lines[j - 1][:len(lines[j - 1]) - len(lines[j - 1].lstrip())] if j > idx + 1 else ""
        if rest and not rest.startswith("#"):
            lines[idx] = f"{field}:"                # normaliza un `field: null` explícito
        lines[j:j] = [f"{indent}- {_yaml_block_item(str(v))}" for v in missing]
    else:
        return _no("forma no reconocida (escalar con valor) — no se toca")
    cfg.write_text_atomic(dest, text[:ini] + "\n".join(lines) + text[end:])
    return True


def _fm_preservando_comentarios(nuevo_bloque: str, head_viejo: str, dest) -> str:
    """The re-serialised YAML block (no delimiters) carrying the old head's comments.

    AUD-169 / INV-139 — `sync_mirror` and `migrate_disputes` re-serialise the whole frontmatter with
    `yaml.safe_dump`, which drops every comment. The framework tells people to hand-edit these
    files, so those comments are curation: a stamper that erases them destroys work nobody can
    reconstruct, and reports success while doing it. Whatever cannot be re-anchored is **named**
    instead of disappearing."""
    cuerpo = nuevo_bloque[4:-4] if nuevo_bloque.startswith("---\n") else nuevo_bloque
    if "#" not in head_viejo:
        return cuerpo.strip("\n")                    # el caso normal, y es gratis
    merged, huerfanos = cfg.reattach_yaml_comments(head_viejo, cuerpo)
    if huerfanos:
        cfg.print_seguro(f"  ⚠ {dest.name}: {len(huerfanos)} comentario(s) del frontmatter no se "
                         f"pudieron re-anclar (su clave ya no está) → van al final; revisalos:")
        for c in huerfanos:
            cfg.print_seguro(f"      {c}")
        merged = merged.rstrip("\n") + "\n" + "\n".join(huerfanos)
    return merged.strip("\n")


def excluded_table(slug: str) -> str:
    """Tabla breve (snapshot del ingest) de los papers que el clasificador dejó AFUERA (no-core):
    top por citas, con motivo y link a ADS. Es un puntero "por las dudas" para cazar falsos negativos
    y afinar relevance.facets — los no-core NO se bajan ni se fichan. Vacío si no hay ads.json/excluidos.
    Frontera dura OK: son papers reales (bibcode citable) con motivo reproducible, no afirmación suelta.

    Se llama desde `write_star_note`/`write_concept_note`: si esto lanza, la cadena muere DESPUÉS de
    gastar la red. Un `ads.json` truncado por un Ctrl-C a mitad de `query_ads` (JSON incompleto) o con
    tipos torcidos (`bibcode` no-str, `citation_count` string) es un estado alcanzable, no hipotético
    — así que acá se DEGRADA (registro que no es mapa se saltea, valores se coercen) y nunca se lanza;
    siempre devuelve un `str` (`""` si no hay nada mostrable)."""
    adsfile = cfg.ROOT / "build" / slug / "ads.json"
    if not adsfile.exists():
        return ""
    try:
        data = json.loads(adsfile.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""                             # JSON truncado/corrupto: sin snapshot confiable
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        return ""
    out = [r for r in records if isinstance(r, dict) and not r.get("relevant")]
    if not out:
        return ""

    def citas(r: dict) -> int:
        try:
            return int(r.get("citation_count") or 0)
        except (TypeError, ValueError):
            return 0                          # `citation_count` no numérico: no ordena, no rompe

    # Orden por TASA (citas/año), delegando en la política única de `lib_config` (#94): la cuenta
    # cruda está sesgada por la edad, y este apéndice es el ÚNICO canal dentro de la nota para cazar
    # falsos negativos de la lente — con orden crudo, "lo que la lente descartó" son sistemáticamente
    # los papers más viejos y un falso negativo reciente queda abajo del corte. `sweep_star` ya la
    # usaba; esto era el clon que la contradecía, exactamente lo que ese docstring dice evitar.
    out = cfg.sort_by_citation_rate(out)
    rows = []
    for r in out[:EXCLUDED_TOP_N]:
        bibcode = str(r.get("bibcode") or "")   # `bibcode` no-str (p. ej. int): coercer, no crashear
        url = f"https://ui.adsabs.harvard.edu/abs/{quote(bibcode, safe='')}"
        # colapsar espacios/saltos, truncar y RECIÉN escapar (|, []) para no romper el link/tabla
        title = _titulo_corto(" ".join(str(r.get("title") or "(sin título)").split()), 70) \
            .replace("|", r"\|").replace("[", r"\[").replace("]", r"\]")
        # motivo REAL persistido por query_ads (`why_excluded`, #30 — cubre también la regla de
        # combinación require/min_facets). Sin el campo (ads.json pre-#30) NO se reconstruye con la
        # dicotomía vieja: etiquetaba con un motivo FALSO (`doctype: article`) a los excluidos por
        # la regla de combinación — y ese texto se ESCRIBE en la bóveda, en el apéndice de la ficha.
        motivo = r.get("why_excluded") or ("(motivo no registrado: `ads.json` anterior a #30 — "
                                           "re-corré `query_ads`)")
        rows.append(f"| [{title}]({url}) | {r.get('year') or ''} | {citas(r)} | {motivo} |")
    extra = len(out) - len(rows)
    tail = f"\n\n_(+ {extra} más excluidos por el filtro)_" if extra > 0 else ""
    return ("\n## Excluidos por el filtro (no-core · snapshot del ingest)\n"
            "> Top por TASA de citas (citas/año, política única de `lib_config`) de lo que el clasificador dejó afuera (no matchea `relevance.facets`, "
            "no cumple la regla de combinación `require`/`min_facets`, o doctype ruido). **No se bajan "
            "ni se fichan** — esto es un puntero por las dudas. Si ves un falso negativo, ajustá "
            "`relevance.facets` (o la regla de combinación) y re-ingestá con `--force`.\n\n"
            "| Paper | Año | Citas | Motivo |\n|---|---|---|---|\n"
            + "\n".join(rows) + tail + "\n")


EXCLUDED_HEADER = "## Excluidos por el filtro"


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
    adsfile = cfg.ROOT / "build" / slug / "ads.json"
    if not adsfile.exists():
        return False                            # sin corrida vigente: ni re-estampa ni quita
    # AUD-202 / INV-139 — `excluded_table` DEGRADA a "" ante un `ads.json` corrupto (promete no
    # lanzar), y acá "" significa «la corrida vigente no excluye a nadie» → se QUITABA el apéndice.
    # O sea: un JSON cortado a mitad borraba contenido ya publicado de la bóveda. Las dos cosas
    # están bien por separado; lo que faltaba era distinguirlas antes de decidir el borrado.
    try:
        json.loads(adsfile.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        cfg.print_seguro(
            f"  ⚠ {dest.name}: `build/{slug}/ads.json` no se puede leer "
            f"({type(exc).__name__}) → NO se re-estampa «Excluidos por el filtro» (dejarlo vacío "
            f"borraría el snapshot del ingest); re-corré `python scripts/query_ads.py {slug}`",
            file=sys.stderr)
        return False
    new = excluded_table(slug)                  # "" si la corrida no dejó excluidos
    text = dest.read_text(encoding="utf-8")
    start = cfg.section_start(text, EXCLUDED_HEADER)
    if start < 0:
        if not new:
            return False
        out = text.rstrip("\n") + "\n" + new
    else:
        nxt = text.find("\n## ", start + 1)
        end = len(text) if nxt < 0 else nxt
        # `excluded_table` trae su propio "\n" inicial: se le saca UNO al prefijo (no un rstrip,
        # que se comería también la línea en blanco que separa la sección anterior).
        out = text[:start][:-1] + new.rstrip("\n") + ("\n" if new else "") + text[end:]
    if out == text:
        return False
    cfg.write_text_atomic(dest, out)
    return True


# @inv INV-62
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
    # #247 — la nota de PAPER era la única de las tres sin aviso, y es la que MÁS contenido generado
    # tiene: la vista es 100 % prosa de un LLM, escrita **con una lente** y en castellano sobre una
    # fuente en inglés. La confusión ya ocurrió con un usuario que conoce el sistema. El aviso dice
    # las tres capas por separado, porque en esta nota conviven las tres en secciones distintas.
    "paper": """> ⚠ **Capa LLM — revisar antes de citar.** En esta nota conviven tres capas: **auditable** el
> `## Abstract` (copia verbatim del catálogo) y el frontmatter de catálogo; **traducción de un LLM** las
> secciones `## Traducción …` —ayuda de lectura, **nunca fuente de la que citar**: si citás, citás el
> original con su página—; y **síntesis de un LLM** la `## Vista — <sujeto>`, que además está escrita
> **con una lente** (dice qué aporta el paper *a ese sujeto*, no qué dice el paper). Las citas textuales
> van en el idioma original y se chequean contra el PDF con `verify-citations`, que es **juicio de LLM,
> no prueba**.""",
}


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
# #178 · las TRES cosas propias de una hipótesis (CLAUDE.md), que ninguna otra nota lleva. Sin
# scaffoldearlas la nota NACÍA con backlog (`Alcance de hipótesis sin declarar`), contra D-5 —la
# nota nace 100 % verificada— y contra la doctrina de que cuando el lint habla hay algo real.
HIPOTESIS_SECCIONES = """## Alcance

> Alcance <AAAA-MM-DD> · temas: [...] + estrellas: [...] · N papers · M con hits
_(D-34: define qué SIGNIFICA el veredicto. "No hay evidencia" no es "no existe evidencia": es "no
hay evidencia en estos temas, con estos N papers, a esta fecha". Los slugs son directorios de
`raw/fulltext/`, así que el universo se puede re-contar — y el lint marca la hipótesis si quedó
corta.)_

## Evidencia

_(D-21: una fila por paper. La POSTURA vive acá, no en la nota del paper: depende de la tesis, y un
paper puede tocar varias. Suelta en el paper sería un veredicto sin evidencia que `verify-citations`
no puede chequear; acá hay cita, así que es verificable.)_

| Paper | Postura | Qué dice (cita textual) | L | Régimen |
|---|---|---|---|---|
| [[bibcode]] | apoya \\| desafía \\| método | "…" | 123 | … |

## Veredicto

_(D-36: agregar N filas en una conclusión es juicio del agente, no algo que una fuente diga → va
marcado `inferencia` NOMBRANDO sus premisas: `(inferencia de [[b1]], [[b2]])`. Sin al menos un
bibcode la marca es una afirmación sin respaldo disfrazada de marca, y el lint la bloquea. El
`status` del frontmatter se DERIVA de la tabla de arriba.)_

"""

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


# @inv INV-11
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


# Bullets de la sección `## Vista — <sujeto>` del stub de nota de paper. Viven acá y NO inline en los dos
# templates de cuerpo —la rama ADS (write_paper_notes) y la off-ADS (write_web_paper_note)— por el
# mismo motivo que LLM_DISCLAIMER: los escriben varios caminos y divergirían. Ramifican por TIPO DE
# SUJETO (#76), como ya ramificaban los seeds del frontmatter: el eje tema/concepto es agnóstico de
# disciplina, así que un tema no puede nacer pidiendo planetas y actividad; y el eje estrella es
# astro por schema (ground-truth NEA) pero sus ejes de CONTENIDO salen del objetivo de la bóveda,
# no de un hardcodeo a "actividad".
# #103 — la REGLA DE ANOTACIÓN, común a las dos ramas. No es cosmética: sale de medir los defectos
# que el fan-out de verify-citations encontró en una ficha real (2026-08-25, HD 40307: 68 pares, 14
# defectos, 0 inventados). Los 14 caen en seis mecanismos, y CUATRO de ellos —número de otra fila de
# la tabla, cantidad parecida confundida, epígrafe que el cuerpo contradice, y la mitad de las citas
# de segunda mano— son mecánicamente detectables si cada valor viaja con su línea. El dato está
# delante de los ojos en el momento de leer; escribirlo cuesta nada y convierte "juicio" en "chequeo".
# La REGLA DE SOMBRA (tiempo verbal + cuantificador, 1.42.0) cubre los otros dos tipos de la
# taxonomía de sobre-generalización medida por Royal Society Open Science 2025 sobre 4900
# resúmenes: "cuantificado → genérico" y "pasado → presente". Son verificables contra el .txt,
# que es el punto — el mismo paper mide que PEDIR exactitud en el prompt DUPLICA el sesgo.
#: #269 — hasta 1.116.x este bullet mandaba *«pegá el nº de línea del `.txt`»*, o sea la doctrina
#: que #205 retiró, **publicada dentro de la nota**: el stub se estampa en el cuerpo de toda nota de
#: paper, así que el texto obsoleto sobrevivía exactamente donde nadie había extraído todavía. La
#: regla del localizador sale de `cfg.REGLA_LOCALIZADOR`, compartida con el prompt.
_BULLET_ANOTACION = (
    f"- **Cómo anotar cada valor (#103):** {cfg.REGLA_LOCALIZADOR}. Anotá también el **régimen** "
    "en el que la fuente lo afirma "
    "(muestra, época, corte de datos, modelo). Si la fuente **atribuye el valor a otro trabajo** "
    "(«according to X», «(X et al.)»), marcalo **segunda mano** y citá a X: el número **no es de "
    "esta fuente**. Copiá el **tiempo verbal y el cuantificador tal cual** (si dice «was "
    "associated», no escribas «is associated»; si dice «el 75 % de la muestra», no escribas «la "
    "muestra»). ⛔ No escribas prosa que compare este paper con otro — comparar es `inferencia` "
    "y va al `## Inventario por eje` de la ficha, no acá._")
_BULLET_METHODS = "- **Métodos:** _(llenar `methods:` del frontmatter con `concepts/methods/`)_"
# El ROL es del paper, no del tipo de sujeto (#73): va en las dos ramas. Sin él, "contrastar dos
# papers" no está definido — fundacional↔aplicación NO es contraste sino instanciación, y tratarlo
# como desacuerdo fabrica disputas falsas. La regex del clasificador no puede inferirlo (clasifica
# TEMA), así que sale de la extracción o no sale.
_BULLET_ROLE = ("- **Rol del paper:** _(`fundacional` introduce el método/mecanismo · `aplicacion` lo "
                "instancia en un caso · `arbitro` reanaliza y resuelve una tensión previa; llenar "
                "`role:` del frontmatter, uno o varios)_")


def objective_lens() -> tuple[list, str]:
    """La LENTE de la bóveda para orientar el stub: (facetas declaradas en `relevance.facets`,
    `short` del objetivo). Es lo único que sabe de qué trata ESTA instancia. Degrada a ([], "")
    si no hay objective.yaml (make_notes corrido suelto, fuera de la cadena) **y también si lo hay
    pero está mal formado**: el `try` cubre la lectura Y la forma, porque el stub es el único lector
    de `short` —ni `query_ads` ni el lint lo miran— y un `short: 2026` mataba la generación de notas
    a mitad de cadena, después de gastar la red. El stub sale genérico, nunca inventado."""
    try:
        obj = cfg.load_objective()
        obj = obj if isinstance(obj, dict) else {}
        rel = obj.get("relevance")
        facets = (rel or {}).get("facets") if isinstance(rel, dict) else None
        # `isinstance(facets, dict)`, no `list(...)` a secas: con `facets` escrito como string (una
        # regex sin nombre de faceta) el `list()` lo deshace en CARACTERES y el stub sale pidiendo
        # facetas fabricadas — justo lo que la degradación promete que nunca pasa.
        facetas = [str(f) for f in facets] if isinstance(facets, dict) else []
        short = obj.get("short")
        return facetas, (short.strip() if isinstance(short, str) else "")
    except Exception:
        return [], ""


def vista_block(sujeto: str, theme: bool) -> str:
    """Sección `## Vista — <sujeto>` del stub de una nota de paper, ramificada por tipo de sujeto
    (#76). Tema → el eje del concept (aporte, mecanismo/ecuación, régimen). Estrella → el
    ground-truth (que es del schema de `stars/`, no del objetivo) y los ejes de la lente. El rol
    del paper (fundacional/aplicación/árbitro) es #73, que define el campo antes que el bullet.

    El SUJETO va en el encabezado (#188): hasta 1.68.0 esto era `## Extracción (LLM)`, una sola
    sección por bibcode, y la extracción es una proyección del paper sobre un sujeto —el prompt
    pregunta *«¿qué dice sobre {name}?»*, con los grep armados desde SUS alias—. Sin el scope, el
    silencio de la nota sobre un eje no se distingue de «se miró y no hay nada»."""
    facetas, short = objective_lens()
    objetivo = (f"«{short}»: qué aporta, qué hueco deja" if short
                else "relevancia para el objetivo de la bóveda / huecos")
    if theme:
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
            "de `relevance.facets` en `objective.yaml`)_",
        ]
    bullets += [_BULLET_METHODS, _BULLET_ROLE, f"- **Para el objetivo:** _({objetivo})_",
                _BULLET_ANOTACION]
    return f"## Vista — {sujeto}\n" + "\n".join(bullets) + "\n"


H1_RE = re.compile(r"^# .+$", re.M)


def note_kind(dest) -> str | None:
    """`star` | `concept` | `paper` según DÓNDE vive la nota (verdad de disco, no heurística).

    #247 — la nota de paper se sumó: era la única de las tres clases **sin** aviso de capa LLM, y
    es la que más contenido generado tiene (la vista es 100 % prosa de un LLM, escrita con una
    lente y en castellano sobre una fuente en inglés). `None` sólo para lo que no es ninguna.
    """
    d = str(dest.resolve())
    if d.startswith(str(cfg.STARS.resolve())):
        return "star"
    if d.startswith(str(cfg.CONCEPTS.resolve())):
        return "concept"
    if d.startswith(str(cfg.PAPERS.resolve())):
        return "paper"
    return None


def stamp_header(dest) -> bool:
    """Backfill de la CABECERA de una ficha/concepto que nació sin ella (#69).

    Por qué hace falta un estampador propio y no alcanza con la familia `stamp_*`: todas ellas
    anclan en `GENERATOR_LINE` y se niegan a actuar si falta (criterio de #48, "no inventamos"),
    que es exactamente la población a arreglar — medido en una bóveda real: 22 de 25 notas sin el
    aviso, y las mismas 21 sin el ancla. Un backfill anclado ahí sería no-op sobre el 100% de los
    casos. Éste ancla en el `# H1`, que toda nota tiene.

    La **versión no se inventa**: sale del `generator` del propio frontmatter, que es la versión con
    la que la nota se creó de verdad. Si la nota es tan vieja que ni eso tiene, la línea va SIN
    versión (mejor sin dato que con uno supuesto). Quirúrgico: inserta después del H1 y no toca una
    línea de la prosa — el blockquote que esas notas ya tienen es texto del LLM, no la cabecera del
    template, y se conserva debajo. Idempotente: si ya está `GENERATOR_LINE`, no hace nada.

    El ancla de "ya tiene cabecera" es **sólo** `GENERATOR_LINE` — es lo único que el lint mide
    (`lint.py`, categoría "cabecera no estampable", #69). La versión vieja frenaba también con sólo
    "Capa LLM" en el texto, y eso era el deadlock: una nota con el disclaimer pero sin la línea del
    generador —22 de 25 en el corpus real de una instancia, típicamente porque el disclaimer se
    escribió a mano antes de que `GENERATOR_LINE` existiera— quedaba marcada por el lint para
    siempre, y el comando que el propio mensaje del lint receta no-opeaba en silencio (0 de 25
    estampadas). Acá, si falta sólo la línea, se agrega al pie del blockquote de "Capa LLM" que ya
    hay — sin duplicar el disclaimer."""
    if not dest.exists():
        return False
    kind = note_kind(dest)
    if kind is None:
        return False
    text = dest.read_text(encoding="utf-8")
    if GENERATOR_LINE in text and AVISO_LLM_MARCA in text:
        return False                                  # ya tiene la línea que el lint mide: nada que hacer
    if GENERATOR_LINE in text:
        # #277 — la línea está y el AVISO no: alguien lo borró. Con el early-return de arriba pelado
        # esa nota no se reparaba nunca y la categoría del lint era incerrable — el deadlock de #69
        # espejado. Se inserta sólo el blockquote que falta, sin duplicar la línea del generador.
        i = text.find(GENERATOR_LINE)
        cfg.write_text_atomic(dest, text[:i] + LLM_DISCLAIMER[kind].strip() + "\n" + text[i:])
        return True
    gen = (cfg.split_fm(text) or {}).get("generator")
    # La rama de fallback TIENE que llevar `GENERATOR_LINE`. Medido corriendo el ensayo de deploy
    # sobre un corpus real: la línea vieja ("Cabecera normalizada por Almagesto; la nota no registra
    # con qué versión se creó") no la llevaba, y `GENERATOR_LINE` no es decorativa — es el **punto de
    # inserción** que `stamp_estado` busca (`if i < 0: return False`). O sea que la cabecera
    # "arreglada" no servía para lo único que la cabecera existe para habilitar: el lint seguía
    # marcando la nota y `--restamp-headers` informaba éxito **en cada corrida** (22 estampadas, 21
    # reportadas, para siempre). Es el no-op silencioso de #69 una capa más abajo.
    # La versión NO se inventa (criterio de #48, "mejor sin dato que con uno supuesto"): se lleva el
    # ancla y se dice explícitamente que se desconoce.
    linea_gen = (f"> _{gen.replace('Almagesto v', 'Generado con Almagesto v')}._"
                 if isinstance(gen, str) and gen.startswith("Almagesto v")
                 else f"{GENERATOR_LINE}desconocida — la nota no registra con qué versión se creó "
                      "(cabecera normalizada)._")
    # ⚠ AUD-135 — las DOS ramas buscan sólo en el CUERPO. La del H1 ya lo hacía (un comentario
    # YAML `# Título` matcheaba `H1_RE`, que corre con `re.M`); la de «Capa LLM» seguía barriendo
    # el texto entero, así que un frontmatter que mencionara esas dos palabras —un comentario de
    # curación, un `motivo:`— metía el blockquote ADENTRO del frontmatter: `split_fm` devolvía `{}`
    # y la nota caía en una categoría BLOQUEANTE. Lo dispara `--restamp-headers`, o sea el comando
    # que el lint receta: la reparación fabricaba el daño que venía a arreglar. Es el arreglo
    # aplicado a un sitio y no a su gemelo, con el motivo escrito al lado.
    partes = cfg.frontmatter_span(text)
    offset = len(text) - len(partes[1]) if partes else 0
    idx = text.find("Capa LLM", offset)
    if idx >= 0:
        # Tiene disclaimer pero no la línea: no re-estampar el bloque entero (duplicaría el aviso),
        # sólo agregar `linea_gen` al final del párrafo blockquote que ya existe — la primera línea
        # después de "Capa LLM" que deja de empezar con ">" (o el EOF) marca el final del párrafo.
        pos = text.find("\n", idx)
        while pos >= 0 and text[pos + 1:pos + 2] == ">":
            pos = text.find("\n", pos + 1)
        insert_at = pos + 1 if pos >= 0 else len(text)
        out = text[:insert_at] + f">\n{linea_gen}\n" + text[insert_at:]
        cfg.write_text_atomic(dest, out)
        return True
    # ⚠ El H1 se busca SÓLO EN EL CUERPO. `H1_RE` corre con `re.M`, así que sobre el texto entero
    # matchea también un **comentario YAML** del frontmatter (`# P_rot lo puso el usuario a mano`,
    # que el framework instruye editar a mano) y el bloque se insertaba ADENTRO del frontmatter:
    # `split_fm` devolvía `{}` y la nota caía en una categoría BLOQUEANTE del lint. Como esto lo
    # dispara `--restamp-headers` —lo que el lint recomienda para las notas sin cabecera— la
    # reparación fabricaba el daño que venía a arreglar.
    m = H1_RE.search(text, offset)
    if not m:
        return False                                  # sin H1 no hay ancla honesta: no inventamos
    bloque = f"\n\n{LLM_DISCLAIMER[kind]}\n>\n{linea_gen}"
    out = text[:m.end()] + bloque + text[m.end():]
    cfg.write_text_atomic(dest, out)
    return True


# ── D-10/D-11/D-24: la lista de papers, MATERIALIZADA ────────────────────────────────────────────
#
# Qué problema cierra. Una ficha promete en su roll-up `## Papers` un universo (medido en la
# instancia real: 155) y su prosa discute otra cosa (8). Y ese roll-up es un bloque ```dataview```:
# un agente que abre el `.md` ve el CÓDIGO de la query, no sus resultados, y el plugin ni siquiera
# está versionado. El contrato dice que la ficha sirve a una audiencia-modelo; una promesa que
# depende de un plugin no la cumple (D-11). Acá la tabla se ESTAMPA, con el estado de cada paper.

PAPERS_HEADER = "## Papers"
PLANETAS_HEADER = "## Planetas (ground-truth NASA Exoplanet Archive)"
METODOS_HEADER = "## Métodos aplicados a esta estrella"
INDICADORES_HEADER = "## Indicadores de actividad esperados"   # #250
CONCEPT_ROLLUP_HEADER = "## Papers que tocan este tema (auto)"

# Los cuatro estados posibles de un paper del universo de un sujeto. El orden es el del embudo:
# cada uno es un paso menos recorrido que el anterior.
ESTADO_SINTETIZADO = "sintetizado"
ESTADO_EXTRAIDO = "extraído, no sintetizado"
ESTADO_SIN_EXTRAER = "sin extraer"
#: #268 · el paper cuyo dueño DECLARÓ que no lo va a leer para este sujeto (`no_vista` + motivo).
#: Sin este escalón se publicaba como `sin extraer`, o sea deuda, y la declaración del usuario no
#: valía nada en el roll-up — la misma escotilla que #256 hizo alcanzable, ignorada por las otras
#: tres redes que cuentan esa nota.
ESTADO_SIN_VISTA = "sin vista (declarado)"
ESTADO_FUERA = "fuera del filtro"
# #116: el paper que el USUARIO sacó del sujeto con `--drop-core`. Distinto de `fuera del filtro`
# (que lo decidió la lente) y sobre todo de `sin extraer` (que se lee como «todavía no llegamos»,
# el estado OPUESTO al real). #112 promete que el excluido «queda VISIBLE» y esa visibilidad vivía
# sólo en `build/` y el registro — no en la ficha, que es el artefacto que viaja.
ESTADO_DROPEADO = "excluido a mano"


def papers_fm_index() -> dict:
    """`{stem: frontmatter}` de todas las notas de paper — UNA pasada de parseo.

    Existe por una regresión medida: `papers_universe` re-parseaba `papers/` entero por cada
    sujeto, y con 4 estrellas sobre 900 notas el lint saltó de ~2,0 a **5,9 parseos YAML por nota**
    (el techo del test de escala es 2,3). Un consumidor que ya tiene el índice lo pasa; el resto
    paga una sola pasada."""
    return {f.stem: cfg.split_fm(f.read_text(encoding="utf-8"))
            for f in sorted(cfg.PAPERS.glob("*.md"))}


def _papers_del_sujeto(slug: str, kind: str, fms: dict | None = None) -> list:
    """(stem, frontmatter) de cada nota de paper que declara este sujeto.

    Se parsea con `cfg.split_fm`, **nunca** con grep: es la lección que `CLAUDE.md` registra medida
    dos veces — `grep -l 'stars:.*<nombre>'` da 0 hits con la lista en bloque, y el `awk` con ámbito
    de campo da 0 con la lista en flow style, que es como la deja el retro-linkeo. Las dos formas
    conviven en el mismo corpus."""
    if kind == "star":
        nombre, _ = cfg.star_by_slug(slug)
        return [(stem, fm) for stem, fm in (fms if fms is not None else papers_fm_index()).items()
                if nombre in (cfg.as_list(fm.get("stars")) or [])]
    # Un TEMA no se declara en `facets` (eso son las facetas de la lente, otro eje): la pertenencia
    # de un paper a un tema vive en `thesis_links` —lo que siembra el ingest— y en `methods`. Es la
    # misma unión que `concept_rollup_rows` (D-24), y por eso se delega ahí: dos predicados de
    # pertenencia distintos para el mismo tema es cómo la tabla y el roll-up terminan discrepando.
    _, meta = cfg.theme_by_slug(slug)
    concept = meta.get("concept") or slug
    return [(stem, fm) for stem, fm in (fms if fms is not None else papers_fm_index()).items()
            if concept in (cfg.as_list(fm.get("thesis_links")) or [])
            or concept in (cfg.as_list(fm.get("methods")) or [])]


# Secciones ESTAMPADAS por máquina: no son síntesis. Se excluyen al medir "citado en esta ficha"
# porque se citan a sí mismas — la tabla de `## Papers` lleva un `[[bibcode]]` por fila, así que sin
# este recorte TODO paper aparece como sintetizado apenas se estampa la tabla. Es el mismo lazo que
# el bloque `## Verificación de citas` en `lib_blocks`: un artefacto que se mide a sí mismo siempre
# da el resultado que su propia existencia produce.
SECCIONES_MAQUINA = cfg.SECCIONES_ESTAMPADAS
_prosa = cfg.solo_prosa


def papers_universe(slug: str, kind: str, fms: dict | None = None) -> list:
    """El universo de papers del sujeto.  @inv INV-81, por paper: `{stem, year, relevance, origen, via, estado}`.

    `estado` mide **cuán lejos llegó ese paper en el embudo**, que es la pregunta que la ficha no
    podía responder: `fuera del filtro` (no-core) → `sin extraer` → `extraído, no sintetizado`
    (`methods` poblado pero su bibcode no aparece citado en ESTA ficha) → `sintetizado`.

    `origen` es `manual` si el paper está en `extra_core` (el juicio del usuario pisa a la lente,
    #68) y `lente` si no; `via` trae el valor declarado en la config (D-58)."""
    dest = (cfg.STARS / f"{slug}.md") if kind == "star" else _concept_dest(slug)
    cuerpo = _prosa(dest.read_text(encoding="utf-8")) if dest and dest.exists() else ""
    meta = (cfg.star_by_slug(slug)[1] if kind == "star" else cfg.theme_by_slug(slug)[1])
    via_de = {e["bibcode"]: e["via"] for e in cfg.load_extra_core(meta, entry=slug)}
    # #116: los `--drop-core` viven en el registro VERSIONADO, que es lo que viaja con la bóveda —
    # no en `build/`, que es scratch. Sin esto la ficha los publica como `sin extraer`.
    # `origen: sujeto` es lo que escribe `--drop-core`; `fuente-declarada` es `--drop-source` y la
    # ausencia de `origen` es el descarte de un candidato del chaining (`--drop`), que NO era core.
    dropeados = set(cfg.dropped_from_subject(slug))
    # #268 — cómo se nombra ESTE sujeto en una nota de paper: `no_vista[].sujeto` usa el mismo
    # nombre que `stars`/`thesis_links`, que es el canónico del YAML, no el slug.
    try:
        _sujetos = {slug, (cfg.star_by_slug(slug)[0] if kind == "star"
                           else cfg.theme_by_slug(slug)[0])}
    except (KeyError, IndexError, TypeError):
        _sujetos = {slug}
    filas = []
    for stem, fm in _papers_del_sujeto(slug, kind, fms):
        if stem in dropeados:
            estado = ESTADO_DROPEADO
        elif (fm.get("relevance") or "").lower() == "low":
            estado = ESTADO_FUERA
        elif not (fm.get("methods") or []):
            estado = (ESTADO_SIN_VISTA if _no_vista_declarada(fm, stem, _sujetos)
                      else ESTADO_SIN_EXTRAER)
        elif f"[[{stem}" in cuerpo:
            estado = ESTADO_SINTETIZADO
        else:
            estado = ESTADO_EXTRAIDO
        # @inv INV-115
        # #125: el TÍTULO. Sin él, la fila es un bibcode pelado y para saber si un paper `sin
        # extraer` te sirve hay que abrir la nota, una por una (25 en un caso real). Es la puerta de
        # entrada a los papers que están en el corpus buscable y todavía no en la síntesis.
        filas.append({"stem": stem, "title": " ".join(str(fm.get("title") or "").split()),
                      "year": fm.get("year") or "", "relevance": fm.get("relevance") or "",
                      "origen": "manual-drop" if stem in dropeados else ("manual" if stem in via_de else "lente"),
                      "via": via_de.get(stem, ""), "estado": estado})
    return sorted(filas, key=lambda r: r["stem"])


def _concept_dest(slug: str):
    """La nota del concepto de un tema, por su `area`/`concept` de themes.yaml."""
    try:
        _, meta = cfg.theme_by_slug(slug)
    except KeyError:
        return None
    return cfg.CONCEPTS / str(meta.get("area") or "") / f"{meta.get('concept') or slug}.md"


def papers_table(rows: list) -> str:
    """La sección `## Papers` estampada: encabezado con los DOS números (universo y sintetizados) y
    una fila por paper. El encabezado no puede prometer un número que la tabla no sostenga — ése
    era el defecto medido."""
    n_sint = sum(1 for r in rows if r["estado"] == ESTADO_SINTETIZADO)
    out = [f"{PAPERS_HEADER} ({len(rows)} · {n_sint} sintetizados en esta ficha)", ""]
    if not rows:
        out += ["_(ninguna nota de paper declara este sujeto todavía.)_", ""]
        return "\n".join(out)
    out += ["| Bibcode | Título | Año | Relevancia | Origen | Estado |",
            "|---|---|---|---|---|---|"]
    for r in rows:
        origen = r["origen"] + (f" ({r['via']})" if r["via"] else "")
        # el título se trunca y se escapa DESPUÉS: un `|` en el título parte la fila y corre todas
        # las columnas de la derecha, que es el mismo defecto que INV-99 arregló en el bloque de
        # verificación.
        titulo = _titulo_corto(r.get("title"), 80).replace("|", "\\|")
        out.append(f"| [[{r['stem']}]] | {titulo} | {r['year']} | {r['relevance']} | {origen} "
                   f"| {r['estado']} |")
    out.append("")
    return "\n".join(out)


def concept_rollup_rows(slug: str, fms: dict | None = None) -> list:
    """Roll-up de un concepto: **unión** de `methods` y `thesis_links`, declarando por cuál entró.

    D-24: en la instancia real esas dos llaves viven en papers distintos, así que quedarse con una
    sola pierde la mitad del roll-up sin decirlo."""
    try:
        _, meta = cfg.theme_by_slug(slug)
    except KeyError:
        return []
    concept = meta.get("concept") or slug
    filas = []
    for stem, fm in (fms if fms is not None else papers_fm_index()).items():
    #  @inv INV-35
        # #243 — comparado por CLAVE NORMALIZADA, no por string exacto: `methods` lo puebla la
        # extracción sin vocabulario cerrado, y el mismo método llega escrito de varias maneras.
        # Medido: un concepto `pca` alcanzaba 21 papers de 24 y no decía nada de los 3 que
        # escribieron `PCA` — un roll-up subdeclarando su propio universo en silencio.
        por_m = cfg.method_matches(concept, fm.get("methods"))
        por_t = cfg.method_matches(concept, fm.get("thesis_links"))
        if not (por_m or por_t):
            continue
        filas.append({"stem": stem, "year": fm.get("year") or "",
                      "entro_por": "ambos" if por_m and por_t else ("methods" if por_m else "thesis_links")})
    return sorted(filas, key=lambda r: r["stem"])


def concept_rollup_table(rows: list) -> str:
    out = [f"{CONCEPT_ROLLUP_HEADER} ({len(rows)})", ""]
    if not rows:
        out += ["_(ninguna nota de paper declara este tema todavía.)_", ""]
        return "\n".join(out)
    # Sin columna `Bearing`: D-21 la retiró del paper — la postura depende de la TESIS y un
    # paper puede tocar varias, así que vive en la tabla de evidencia de la hipótesis.
    out += ["| Bibcode | Año | Entró por |", "|---|---|---|"]
    for r in rows:
        out.append(f"| [[{r['stem']}]] | {r['year']} | {r['entro_por']} |")
    out.append("")
    return "\n".join(out)


def _titulo_corto(title, n: int) -> str:
    """`title` cut to `n` chars, with the cut MARKED (#260-family, #264).

    Both stamped roll-ups cut silently, so a title lost its tail with nothing to say so — and the
    declared audience of this vault is a model, which then cites the paper as *«…and Fe-group
    element»*. Measured on a real note: 31 of 49 rows of `## Papers` and 4 of 10 of `## Excluidos`.
    It was also incoherent inside the same artefact: `## Verificación de citas`, three sections
    below, does mark its truncations because #226 demands it.

    The `rstrip()` before the ellipsis also closes the orphan space that `excluded_table` left
    before the `]` of its markdown link (`Neptunes: ]`)."""
    t = str(title or "").strip()
    return t[:n].rstrip() + "…" if len(t) > n else t


def indicadores_table(fm: dict, names: set | None = None) -> str:
    """`## Indicadores de actividad esperados` materialised, with its link to the concept (#250).

    `activity_indicators_expected` was the only list field of `stars/` whose entries had **no
    destination checked and no link**: `thesis_links` blocks, `methods` is backlog, and this one had
    neither — so the note names five indicators and the reader has no way to reach the concept that
    explains any of them. Read from the note's own frontmatter, like `planetas_table`: cheap,
    idempotent, no cross-note sweep.

    The destination resolves through the alias index of #245 after dropping the gloss (#250): the
    field is prose for a human, so `BIS (bisector de la CCF)` has to reach `bis.md`."""
    names = note_names() if names is None else names
    inds = [str(x).strip() for x in cfg.as_list(fm.get("activity_indicators_expected"))
            if str(x).strip()]
    out = [f"{INDICADORES_HEADER} ({len(inds)})", ""]
    if not inds:
        out += ["_(la ficha no declara indicadores esperados todavía — los puebla la síntesis.)_", ""]
        return "\n".join(out)
    idx = cfg.concept_alias_index()
    out += ["| Indicador | Concepto |", "|---|---|"]
    for ind in inds:
        destino = cfg.method_target(cfg.indicator_key(ind), idx)
        if destino is None and cfg.indicator_key(ind) in {cfg.method_key(n) for n in names}:
            destino = next(n for n in names if cfg.method_key(n) == cfg.indicator_key(ind))
        out.append(f"| `{ind}` | " + (f"[[{destino}]]" if destino else "_(sin nota)_") + " |")
    out.append("")
    return "\n".join(out)


def planetas_table(fm: dict) -> str:
    """`## Planetas` **materializada** (D-11 / INV-81). Era un bloque ```dataviewjs``` — el peor de
    los tres, porque los cinco campos por planeta son **ground-truth de NEA**, la capa que el
    contrato promete auditable, y un agente que abría el `.md` veía el CÓDIGO de la query, no los
    valores. El plugin ni siquiera está versionado.

    Se estampa desde el frontmatter de la propia ficha, que es el espejo de NEA: no re-lee el JSON
    (dos lectores del mismo hecho pueden divergir; el que compara los dos es el lint)."""
    planets = [pl for pl in cfg.as_list(fm.get("planets")) if isinstance(pl, dict)]
    out = [f"{PLANETAS_HEADER} ({len(planets)})", ""]
    if not planets:
        out += ["_(NEA no lista planetas confirmados para esta estrella. Una señal discutida no va "
                "acá: va como `disputes` con `field: <letra>.existence`.)_", ""]
        return "\n".join(out)
    out += ["| Letra | P (d) | K (m/s) | e | m·sini (M⊕) | Estado |", "|---|---|---|---|---|---|"]
    for pl in planets:
        vals = [pl.get("letter"), pl.get("P_days"), pl.get("K_ms"), pl.get("e"),
                pl.get("mass_earth"), pl.get("status")]
        # `null` explícito, no celda vacía: NEA calla seguido en `K_ms` y `e`, y el contrato dice
        # que ese null es el estado CORRECTO — una celda en blanco se lee como "falta el dato".
        out.append("| " + " | ".join("null" if v is None else str(v) for v in vals) + " |")
    out.append("")
    return "\n".join(out)


def metodos_rows(name: str, fms: dict | None = None) -> list:
    """`[(método, stem, año)]` — los métodos DE los papers de esta estrella (no todo paper de la
    bóveda que use el método). Es el mismo recorte que documenta `CLAUDE.md` para el equivalente
    determinista, y se parsea con `split_fm`, **no** con grep: `stars: [tau Cet]` en flow style y
    en bloque conviven en el mismo corpus, y el matcheo textual confunde `GJ 71` con `GJ 710`."""
    filas = []
    for stem, fm in (fms if fms is not None else papers_fm_index()).items():
        if name not in cfg.as_list(fm.get("stars")):
            continue
        for m in cfg.as_list(fm.get("methods")):
            filas.append((str(m), stem, fm.get("year") or ""))
    return sorted(filas)


def note_names() -> set:
    """Los stems de TODA nota de `vault/wiki/` — para no estampar un `[[link]]` hacia una página que
    no existe. Mismo criterio que el detector de wikilinks rotos del lint, que es quien lo cobra."""
    return {f.stem for f in cfg.WIKI.rglob("*.md")} if cfg.WIKI.exists() else set()


#: #273 · cuántos métodos se listan antes de colapsar el resto en un `<details>`. El tope es
#: **declarado**, nunca silencioso (#107): el `<summary>` dice cuántos quedaron adentro.
TOPE_METODOS = 40


def metodos_table(rows: list, names: set | None = None, tope: int = TOPE_METODOS) -> str:
    """`## Métodos aplicados a esta estrella` materializada (D-11 / INV-81), **agrupada** (#273).

    ⚠ El método se estampa como `[[wikilink]]` **sólo si su nota existe** —por stem o por `aliases`
    del concepto (#245)—; si no, va como código. Por qué: `methods` lo puebla la EXTRACCIÓN (paso 3
    de `ingest-star`) y las notas de `concepts/methods/` las crea `ingest-theme`, que es **otra
    operación**. Con el link incondicional, seguir `ingest-star` al pie de la letra dejaba el lint
    en decenas de *wikilinks rotos* —bloqueantes— que no se podían cerrar dentro de la operación que
    los creó (medido: 106 sobre dos estrellas). La señal no se pierde: el lint la reporta como
    backlog.

    #273 — **una fila por MÉTODO, no por par (método, paper)**. Medido en una ficha real: 369 filas
    sobre 291 métodos, 374 de 1278 líneas, o sea el 30 % de la nota para una tabla que nadie puede
    leer. Agrupar por clave normalizada sola baja a 291 (21 %) y **no alcanza** —está medido—, así
    que además se colapsa la cola en un `<details>` cuyo `summary` **declara cuántos hay adentro**.
    ⛔ La grafía que eligió el extractor NO se reescribe: se agrupa, y las variantes se muestran.
    El detalle par a par sigue siendo recuperable con el one-liner determinista de `CLAUDE.md`.
    """
    names = note_names() if names is None else names
    idx = cfg.concept_alias_index()
    # #262 — se cuenta por CLAVE NORMALIZADA, no por string crudo: `methods` lo puebla la extracción
    # con vocabulario abierto, así que el mismo método llega escrito de varias maneras y contar
    # grafías **sobre**declara el universo (medido: 297 publicados sobre 291 reales).
    grupos: dict = {}
    for m, stem, year in rows:
        g = grupos.setdefault(cfg.method_key(m), {"variantes": [], "papers": set(), "anios": set()})
        if m not in g["variantes"]:
            g["variantes"].append(m)
        g["papers"].add(stem)
        if str(year).strip():
            g["anios"].add(str(year).strip())
    out = [f"{METODOS_HEADER} ({len(grupos)} método(s) · {len(rows)} aplicación(es))", ""]
    if not rows:
        out += ["_(ningún paper de esta estrella declara `methods` todavía — o no se extrajo "
                "ninguno, o la extracción no pobló el campo.)_", ""]
        return "\n".join(out)

    def _fila(clave: str) -> str:
        """One row: the destination link, the spellings the extractors used, and the two counts."""
        g = grupos[clave]
        principal = g["variantes"][0]
        destino = principal if principal in names else cfg.method_target(principal, idx)
        # ⚠ El alias-link `[[stem|texto]]` NO se usa: el `|` dentro de una celda hay que escaparlo
        # (#240/#227) y un escape de más parte la fila. Se linkea el destino y las variantes van al
        # lado como código — que además deja ver POR QUÉ resolvió ahí.
        etiqueta = (f"[[{principal}]]" if destino == principal else
                    f"[[{destino}]]" if destino else "")
        # Las variantes se muestran sólo cuando AGREGAN algo: si la única es el nombre del
        # destino, repetirla es ruido en una tabla que este issue existe para achicar.
        extras = [v for v in g["variantes"] if v != destino]
        variantes = " · ".join(f"`{cfg.escape_cell(v)}`" for v in extras)
        celda = " · ".join(x for x in (etiqueta, variantes) if x)
        anios = sorted(g["anios"])
        rango = "—" if not anios else (anios[0] if anios[0] == anios[-1]
                                       else f"{anios[0]}-{anios[-1]}")
        return f"| {celda} | {len(g['papers'])} | {rango} |"

    orden = sorted(grupos, key=lambda k: (-len(grupos[k]["papers"]), k))
    cabeza, cola = orden[:tope], orden[tope:]
    out += ["_(una fila por método; el detalle par a par sale del one-liner determinista de "
            "`CLAUDE.md`.)_", "",
            "| Método | Papers | Años |", "|---|---|---|"]
    out += [_fila(k) for k in cabeza]
    out.append("")
    if cola:
        # El tope se DECLARA (#107): un corte silencioso es cómo se saca una conclusión estructural
        # de un truncamiento que nadie anunció. El `<details>` va FUERA de la tabla —con su línea en
        # blanco— para no romper la forma del artefacto (#227/#260).
        out += [f"<details><summary>{len(cola)} método(s) más, con menos aplicaciones</summary>", "",
                "| Método | Papers | Años |", "|---|---|---|"]
        out += [_fila(k) for k in cola]
        out += ["", "</details>", ""]
    return "\n".join(out)


def _reemplazar_seccion(dest, header: str, nuevo: str) -> bool:
    """Cirugía anclada: reemplaza la sección que empieza en `header` hasta el próximo `## ` (o EOF).

    Familia `stamp_excluded`/`stamp_fulltext`: nunca toca la prosa LLM de las otras secciones, y es
    idempotente (sin cambios no reescribe). Si la nota no tiene esa sección, no la inventa —
    agregarla al final la pondría después del apéndice de excluidos, fuera de su lugar."""
    if not dest.exists():
    #  @inv INV-15
        return False
    text = dest.read_text(encoding="utf-8")
    inicio = cfg.section_start(text, header)
    if inicio < 0:
        return False
    nxt = text.find("\n## ", inicio + 1)
    fin = len(text) if nxt < 0 else nxt + 1
    # #260 — `fin = nxt + 1` deja `text[fin:]` arrancando EN el `## ` siguiente, así que la línea en
    # blanco que separaba las dos secciones cae dentro del tramo reemplazado; el `rstrip` borra
    # además la que el generador sí produce (las tres tablas terminan con `out.append("")`). Con un
    # solo `\n` el encabezado queda pegado a la última fila, y Python-Markdown —el parser de MkDocs
    # y de media cadena de export— lo absorbe **como una celda más**: medido, 3 de los 8 `##` de una
    # ficha real desaparecían del outline, y con ellos la población que D-10/INV-81 obligan a
    # publicar en el título. GFM (Obsidian) lo tolera, así que no se veía. `stamp_excluded` ya lo
    # hacía bien y lo documentaba: la comprensión estaba, no había llegado hasta acá.
    sep = "\n\n" if nxt >= 0 else "\n"
    out = text[:inicio] + nuevo.rstrip("\n") + sep + text[fin:]
    if out == text:
        return False
    cfg.write_text_atomic(dest, out)
    return True


def missing_anchors(dest, headers) -> list:
    """The headers a stamper could NOT find in the note (#196).

    `_reemplazar_seccion` returns `False` for two different things: the section was already up to
    date (an idempotent no-op, fine) and the section **is not there** (the surgery has nothing to
    anchor on, a defect). Conflating them is what kept the bug mute: `--theme` skipped the rich
    `## Papers` table on notes carrying the ficha-style header and said nothing, so a stale table
    published `66 · 41` over a real universe of `90 · 57`. Same failure mode as #69 — a promise the
    system quietly stopped keeping.

    Callers use this to NAME the sections they could not stamp instead of returning a bare `False`.
    """
    #  @inv INV-136
    if not dest.exists():
        return list(headers)
    text = dest.read_text(encoding="utf-8")
    return [h for h in headers if cfg.section_start(text, h) < 0]


def stamp_papers_table(slug: str, dest, kind: str = "star") -> bool:
    """Reemplaza el bloque ```dataview``` de `## Papers` por la tabla materializada (D-10/D-11)."""
    return _reemplazar_seccion(dest, PAPERS_HEADER, papers_table(papers_universe(slug, kind)))


def stamp_star_rollups(slug: str, dest) -> bool:
    """Las otras dos tablas de la ficha de estrella (D-11 / INV-81): `## Planetas` y
    `## Métodos aplicados a esta estrella`. D-11 se había cumplido **sólo** para `## Papers`, así
    que la promesa "ninguna promesa del contrato depende de un plugin" valía para un tercio de los
    roll-ups — y justo el de planetas expone el ground-truth, la capa que el contrato vende como
    auditable. Devuelve True si tocó algo (cirugía idempotente, no toca la prosa)."""
    if not dest.exists():
        return False
    fm = cfg.split_fm(dest.read_text(encoding="utf-8"))
    try:
        name, _ = cfg.star_by_slug(slug)
    except (KeyError, RuntimeError):
        name = fm.get("name") or slug
    tocado = _reemplazar_seccion(dest, PLANETAS_HEADER, planetas_table(fm))
    tocado = _reemplazar_seccion(dest, INDICADORES_HEADER, indicadores_table(fm)) or tocado   # #250
    return _reemplazar_seccion(dest, METODOS_HEADER, metodos_table(metodos_rows(name))) or tocado


def stamp_concept_rollup(slug: str, dest) -> bool:
    """Ídem para el roll-up de un concepto, con la unión de las dos llaves (D-24)."""
    return _reemplazar_seccion(dest, CONCEPT_ROLLUP_HEADER,
                               concept_rollup_table(concept_rollup_rows(slug)))


# ── D-19 / INV-84: identidad del paper y renombre preprint → publicado ───────────────────────────
#
# La identidad de un trabajo es su `doi`/`arxiv_id`, no su bibcode: el mismo paper tiene un bibcode
# de preprint y otro de publicado. Medido en la instancia real: 2 trabajos con dos notas cada uno.
# Para todo lo que cuenta papers eso es doble conteo; para el consumidor son dos fuentes donde hay
# una; y para #75 ("extraído no sintetizado") es un falso positivo permanente, porque la ficha cita
# una de las dos.

# Wikilink al stem exacto: `[[stem]]` o `[[stem|alias]]`. Deliberadamente NO matchea el bibcode
# suelto en prosa — una cita transcripta del paper que lo menciona textualmente no es un link a la
# nota, y un replace ciego la reescribiría (adversario con test propio).
def _wikilink_re(stem: str):
    """`[[stem]]`, `[[stem|alias]]`, `[[stem#section]]` and `[[stem^block]]`, without matching a
    stem that merely prefixes it.

    ⚠ AUD-168 / INV-84 — the two Obsidian ANCHOR forms (`#` and `^`) were missing, and those are
    exactly what a long note uses to point at one section or one block of a paper. A rename left
    them pointing at the old bibcode — broken, and **listed by nobody**: the lint's broken-wikilink
    detector does read them (its `LINK_RE` cuts at `#`), so they showed up as a finding right after
    the rename, over a link the renamer was supposed to have fixed. The captured group is re-emitted
    verbatim, so the anchor survives untouched."""
    return re.compile(r"\[\[" + re.escape(stem) + r"(\||\]\]|#|\^)")


# #114: el DOI que DataCite le asigna a un eprint de arXiv. `10.48550/arXiv.2605.28635`
# y `arxiv_id: 2605.28635` son el mismo trabajo, y compararlos como strings distintos deja ciego
# al detector de duplicados en la forma MÁS común del caso que D-19 existe para cazar.
_DOI_ARXIV_RE = re.compile(r"^10\.48550/arxiv\.(.+)$")


def identidad(fm: dict) -> tuple | None:
    """La identidad del trabajo: `("arxiv", id)` o `("doi", id)`, o `None` si no declara ninguna.

    `arxiv_id` primero porque es el que sobrevive al ciclo preprint→publicado (el DOI del preprint
    y el del publicado suelen ser distintos, el arXiv id no cambia).

    #114: un DOI DataCite `10.48550/arXiv.<id>` **es** un arXiv id disfrazado — es el que ADS le pone
    al registro del preprint. Sin normalizarlo, el preprint queda con identidad `("doi", "10.48550/…")`
    y no matchea al publicado aunque éste declare el mismo `arxiv_id`.
    """
    for campo, clave in (("arxiv_id", "arxiv"), ("doi", "doi")):
        v = fm.get(campo)
        if not v:
            continue
        v = str(v).strip().lower()
        if clave == "doi" and (m := _DOI_ARXIV_RE.match(v)):
            return ("arxiv", m.group(1))          # DOI DataCite → la identidad real es el arXiv id
        return (clave, v)
    return None


def _reescribir_wikilinks(old_stem: str, new_bibcode: str) -> int:
    """Reescribe `[[old_stem]]` → `[[new_bibcode]]` en TODA la bóveda. Devuelve notas tocadas.

    Extraído de `rename_paper` para que la consolidación de duplicados (#115) use el MISMO código:
    dos caminos que reescriben links con reglas distintas es exactamente donde vive un bug (regla
    de método #2).

    `cfg.VAULT`, no `cfg.WIKI`: el alcance DECLARADO es `vault/`, y `STATUS.md` (que vive un nivel
    arriba de `wiki/`) cita bibcodes como cualquier nota. Y `safe_name(new_bibcode)`, no el bibcode
    crudo: el archivo se crea con el stem saneado y todos los wikilinks que el repo genera usan el
    stem — escribir el crudo hacía que cada link reescrito apuntara a una nota inexistente.
    """
    patron = _wikilink_re(safe_name(old_stem))
    tocadas = 0
    for f in sorted(cfg.VAULT.rglob("*.md")):
        cuerpo = f.read_text(encoding="utf-8")
        nuevo_cuerpo = patron.sub(lambda m: f"[[{safe_name(new_bibcode)}{m.group(1)}", cuerpo)
        if nuevo_cuerpo != cuerpo:
            cfg.write_text_atomic(f, nuevo_cuerpo)
            tocadas += 1
    return tocadas


def _better_txt(candidato, actual) -> bool:
    """¿El `.txt` `candidato` es de calidad ESTRICTAMENTE mayor que `actual`? (#170)

    Misma escala que `stamp_fulltext` (`_FULLTEXT_QUALITY`: `pdftotext`/`web` > `ocr`) y misma regla
    de empate — gana el que ya está, así que consolidar dos veces no alterna."""
    return _FULLTEXT_QUALITY.get(_txt_provenance(candidato), 0) > \
        _FULLTEXT_QUALITY.get(_txt_provenance(actual), 0)


def _consolidar_duplicado(old, new, old_stem: str, new_bibcode: str) -> None:
    """Fusiona dos notas del MISMO trabajo hacia la canónica (#115). `new` sobrevive.

    `rename_paper` cubría sólo *«existe el preprint y todavía no el publicado»*. Cuando existen las
    dos —que es literalmente el duplicado que D-19 nombra— abortaba con «resolvé a mano», así que la
    doc prometía un remedio que no corría. Consolidar es: el bibcode viejo pasa a `versions[]` de la
    canónica, se conserva el MEJOR artefacto de cada tipo, se borra la nota vieja y se reescriben los
    wikilinks de toda la bóveda.

    ⛔ Rehúsa si la nota vieja tiene extracción LLM y la canónica no: descartar el paso más caro de
    la cadena en silencio es justo lo que el framework evita en todos lados (cf. `entity.py delete`,
    que avisa y no borra el paper compartido). La salida es renombrar al revés, o mover la prosa a
    mano y volver a correr.
    """
    fm_old = cfg.split_fm(old.read_text(encoding="utf-8")) or {}
    fm_new = cfg.split_fm(new.read_text(encoding="utf-8")) or {}
    if fm_old.get("methods") and not fm_new.get("methods"):
        raise SystemExit(
            f"⛔ {old.name} tiene extracción LLM (`methods` poblado) y {new.name} no: consolidar "
            f"hacia {new.name} la perdería.\n"
            f"   Salidas: renombrar al revés (`--rename-paper {new_bibcode} {old_stem}`), o mover "
            f"la prosa a mano y volver a correr.")

    versions = [v for v in cfg.as_list(fm_new.get("versions")) if isinstance(v, dict)]
    if not any(str(v.get("bibcode")) == old_stem for v in versions):
        versions.append({"bibcode": old_stem, "pdf_source": fm_old.get("pdf_source"),
                         "eprint_version": fm_old.get("eprint_version")})

    # Artefactos: se queda el de MEJOR calidad, y el otro se borra. Dejar los dos haría que #108 los
    # reporte para siempre como extracción pagada sin nota, y que el `.txt` huérfano siga saliendo
    # en los greps del corpus.
    #
    # ⛔ #170: acá el `if destino.exists(): art_old.unlink()` conservaba SIEMPRE el del bibcode
    # canónico, sin mirar calidad — o sea que consolidar podía borrar un `.txt` limpio de
    # `pdftotext` y dejar un escaneo OCR mojibake. El borrado es irreversible sobre `raw/`, que el
    # contrato declara *código fuente inmutable*, y degrada la fuente que después leen
    # `verify-citations` y todo `grep` del corpus. El comparador ya existía en este archivo
    # (`_FULLTEXT_QUALITY`, usado por `stamp_fulltext`): sólo faltaba usarlo. Un PDF no lleva
    # header de provenance, así que ahí no hay nada que comparar y se mantiene el criterio viejo.
    movidos, borrados = [], []
    for base in (cfg.PDFS, cfg.FULLTEXT):
        for art_old in sorted(base.glob(f"*/{safe_name(old_stem)}.*")):
            destino = art_old.with_name(f"{safe_name(new_bibcode)}{art_old.suffix}")
            if not destino.exists():
                art_old.rename(destino); movidos.append(destino.name)
            elif base is cfg.FULLTEXT and _better_txt(art_old, destino):
                destino.unlink(); art_old.rename(destino)
                borrados.append(destino.name)
            else:
                art_old.unlink(); borrados.append(art_old.name)

    old.unlink()
    _set_lista_de_mapas(new, "versions", versions)
    _move_extraction(old_stem, new_bibcode)     # #228: mismo camino que `rename_paper`
    n = _reescribir_wikilinks(old_stem, new_bibcode)
    cfg.print_seguro(
        f"  ✓ consolidado: {old.name} → {new.name} (canónica). `versions[]` += {old_stem}; "
        f"{len(movidos)} artefacto(s) movido(s), {len(borrados)} duplicado(s) borrado(s); "
        f"{n} wikilink(s) reescrito(s).")


def rename_paper(old_stem: str, new_bibcode: str) -> None:
    """Renombra una nota de paper y TODO lo que la referencia (D-19).  @inv INV-84

    Mueve la nota y sus artefactos (`raw/pdfs/*/`, `raw/fulltext/*/`), agrega el bibcode viejo a
    `versions[]` —el alias: lo que el mundo exterior conserva— y **reescribe los wikilinks de toda
    la bóveda**. Sin esa reescritura el renombre deja links rotos, que es la mitad del trabajo y la
    que no se nota hasta que el lint la grita.

    Alcance declarado: `vault/`. Lo que vive afuera (un paper que cita el bibcode viejo) se resuelve
    por el alias en `versions[]`, no por reescritura."""
    old = cfg.PAPERS / f"{safe_name(old_stem)}.md"
    if not old.exists():
        raise SystemExit(f"no existe la nota {old.name} — nada que renombrar")
    new = cfg.PAPERS / f"{safe_name(new_bibcode)}.md"
    if new.exists():
        _consolidar_duplicado(old, new, old_stem, new_bibcode)
        return

    texto = old.read_text(encoding="utf-8")
    fm = cfg.split_fm(texto)
    version = {"bibcode": old_stem, "pdf_source": fm.get("pdf_source"),
               "eprint_version": fm.get("eprint_version")}
    versions = [v for v in cfg.as_list(fm.get("versions")) if isinstance(v, dict)] + [version]

    # artefactos: se mueven, no se copian — dejar el `.txt` viejo al lado haría que el hash de
    # fuente del ancla (D-20) apunte a un archivo que ya nadie referencia.
    for base in (cfg.PDFS, cfg.FULLTEXT):
        for viejo in base.glob(f"*/{safe_name(old_stem)}.*"):
            viejo.rename(viejo.with_name(f"{safe_name(new_bibcode)}{viejo.suffix}"))

    cfg.write_text_atomic(new, texto)
    old.unlink()
    _set_campo(new, "bibcode", new_bibcode)
    _set_lista_de_mapas(new, "versions", versions)

    _finish_rename(new, old_stem, new_bibcode)

    tocadas = _reescribir_wikilinks(old_stem, new_bibcode)
    cfg.print_seguro(f"  {old.name} → {new.name} · {tocadas} nota(s) con wikilinks reescritos · "
                     f"alias en `versions[]`")


def _finish_rename(nota, old_stem: str, new_bibcode: str) -> None:
    """The layers `--rename-paper` promised to touch and did not (#228).

    Renaming was leaving the identity half migrated: the canonical note of the PUBLISHED work
    showed the PREPRINT's bibcode **in its header line** —derived metadata that `make_notes`
    re-stamps in every other context— and kept its `bibstem`. Worse, the extraction JSON stayed
    under the old bibcode: `harvest_views` maps JSON→note by `data["bibcode"]`, so the harvester
    printed «no hay nota en `papers/`» and **skipped the note** on every later run. Measured on a
    real vault, the note left out of the harvester's reach was exactly the one carrying a false
    salvedad — a re-run to fix it would not have touched it.

    ⚠ `build/` is regenerable scratch, but an EXTRACTION is not: it does not come back without
    paying the most expensive step of the chain again. That is why it moves.

    `bibstem` is NOT invented here: it is catalog truth and this function has no catalog. It is
    cleared —«no consta» rather than the preprint's value— and said out loud, which is the honest
    half of the two options the issue named.
    """
    texto = nota.read_text(encoding="utf-8")
    span = find_header_line(texto)
    if span is not None:
        i, j = span
        linea = texto[i:j].replace(f"`{old_stem}`", f"`{new_bibcode}`")
        cfg.write_text_atomic(nota, texto[:i] + linea + texto[j:])

    fm = cfg.split_fm(nota.read_text(encoding="utf-8"))
    if str(fm.get("bibstem") or "").strip():
        _set_campo(nota, "bibstem", "null")
        cfg.print_seguro("  ⚠ `bibstem` era del bibcode viejo y no se puede derivar sin catálogo: "
                         "queda en null (no consta). Re-corré `make_notes <slug>` para repoblarlo.")

    _move_extraction(old_stem, new_bibcode)


def _slugs_of_bibcode(bibcode: str) -> list:
    """Which subject slugs hold artifacts for this bibcode, by disk truth (#231).

    A paper can live under several slugs (its `.txt` extracted under each), so the rename is a step
    in every one of those chains; stamping only one would leave the others reading as a cut.
    """
    fuera = set()
    for base in (cfg.PDFS, cfg.FULLTEXT):
        for art in base.glob(f"*/{safe_name(bibcode)}.*"):
            fuera.add(art.parent.name)
    return sorted(fuera)


def _move_extraction(old_stem: str, new_bibcode: str) -> int:
    """Move `build/<slug>/extraccion/<old>.json` to the new bibcode, rewriting its `bibcode` (#228).

    `harvest_views` maps JSON→note by `data["bibcode"]`, so an extraction left behind makes the
    harvester print «no hay nota en `papers/`» and **skip the note** on every later run — forever,
    and silently. If the canonical bibcode already has its own extraction, the old one is left
    alone: choosing between two paid readings is judgement, not mechanics.
    """
    movidos = 0
    for viejo in sorted(cfg.ROOT.glob(f"build/*/extraccion/{safe_name(old_stem)}.json")):
        nuevo = viejo.with_name(f"{safe_name(new_bibcode)}.json")
        if nuevo.exists():
            cfg.print_seguro(f"  ⚠ {nuevo.parent.parent.name}: ya hay extracción para "
                             f"{new_bibcode}; la de {old_stem} se deja donde está (elegir entre dos "
                             f"lecturas pagadas es juicio, no mecánica)")
            continue
        try:
            data = json.loads(viejo.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("bibcode"):
                data["bibcode"] = new_bibcode
                cfg.write_text_atomic(viejo, json.dumps(data, ensure_ascii=False, indent=2))
        except (json.JSONDecodeError, OSError):
            pass                      # se mueve igual: un JSON ilegible movido sigue siendo mejor
        viejo.rename(nuevo)           # que uno ilegible que además el cosechador no encuentra
        movidos += 1
    if movidos:
        cfg.print_seguro(f"  {movidos} extracción(es) de `build/` movidas al bibcode nuevo — sin "
                         f"esto `harvest_views` saltea la nota para siempre")
    return movidos


def _set_lista_de_mapas(dest, clave: str, valor: list) -> None:
    """Escribe una lista de mapas en el frontmatter, reemplazando el bloque viejo de esa clave.

    Cirugía a nivel texto (familia `merge_frontmatter_list`): no re-serializa el YAML entero, así
    que los comentarios y el orden de la extracción LLM sobreviven byte a byte."""
    text = dest.read_text(encoding="utf-8")
    span = cfg.frontmatter_span(text)
    if span is None:
        return
    yaml_block, _ = span
    # `frontmatter_span` corta JUSTO después del `---` de apertura y JUSTO antes del de cierre, así
    # que el bloque empieza y termina con "\n" y el split deja una cadena vacía en cada punta. Esas
    # dos NO son líneas en blanco: son la separación con los delimitadores. El `if ln.strip()` que
    # había acá las filtraba junto con las de verdad, y el resultado fusionaba el `---` con la
    # primera clave (`---bibcode: 2021pubY`) → `cfg.split_fm` devolvía `{}` y la nota quedaba
    # ILEGIBLE para todo el tooling después de un `--rename-paper`. Se reconstruyen a mano.
    lineas = yaml_block.split("\n")
    cuerpo, dropping = [], False
    for ln in lineas[1:-1]:
        if dropping:
            if ln[:1] in (" ", "\t", "-"):
                continue
            dropping = False
        if ln.startswith(f"{clave}:"):
            dropping = True
            continue
        if ln.strip():
            cuerpo.append(ln)
    bloque = yaml.safe_dump({clave: valor}, sort_keys=False, allow_unicode=True,
                            default_flow_style=False).rstrip("\n")
    nuevo = "\n" + "\n".join(cuerpo + bloque.split("\n")) + "\n"
    cfg.write_text_atomic(dest, text.replace(yaml_block, nuevo, 1))


def _set_campo(dest, clave: str, valor: str) -> None:
    """Reemplaza un escalar del frontmatter editando el TEXTO (no re-serializa: preserva la
    extracción LLM byte a byte, misma familia que `merge_frontmatter_list`)."""
    text = dest.read_text(encoding="utf-8")
    span = cfg.frontmatter_span(text)
    if span is None:
        return
    yaml_block, _ = span
    lineas = [f"{clave}: {valor}" if ln.startswith(f"{clave}:") else ln
              for ln in yaml_block.split("\n")]
    cfg.write_text_atomic(dest, text.replace(yaml_block, "\n".join(lineas), 1))


# ── procedencia del ground-truth, EN la ficha (D-1) ──────────────────────────────────────────────
#
# Un lector abre la ficha y ve `teff_K: 5344` en el frontmatter sin nada que diga de dónde salió.
# La procedencia estaba en la doc del framework, no en el artefacto — y el artefacto es lo que
# viaja: una ficha copiada, exportada o leída por un agente llega sin la doc al lado. Va ARRIBA,
# en el blockquote de cabecera donde ya vive el disclaimer de capa-LLM, porque es lo primero que se
# lee y no se pierde al scrollear.
def _header_block(text: str) -> tuple[int, int] | None:
    """`(inicio, fin)` del blockquote de cabecera — el que contiene `_Generado con Almagesto…_`.

    Las cirugías de cabecera (`stamp_estado`, `stamp_ground_truth_line`) borraban su línea vieja con
    un `sub(count=1)` sobre el **texto entero**, así que se llevaban puesta la primera línea del
    CUERPO que empezara igual. Medido el 2026-08-28: una nota con
    `> _Estado del arte: la señal de 13.9 d sigue disputada_ [[2020smith]].` en `## Síntesis` perdía
    esa línea —prosa con cita— en una corrida **normal**, sin `--force` y sin aviso. Es la negación
    literal de INV-15: *«destruir prosa exige una acción explícita distinta de la corrida normal»*.

    El ancla ya existía y se usaba para **insertar**; lo que faltaba era usarla para **borrar**. El
    bloque son las líneas contiguas que empiezan con `>` alrededor del ancla.
    """
    #  @inv INV-15
    i = text.find(GENERATOR_LINE)
    if i < 0:
        return None
    lineas = text.split("\n")
    n = text[:i].count("\n")                       # índice de la línea del ancla
    ini = n
    while ini > 0 and lineas[ini - 1].startswith(">"):
        ini -= 1
    fin = n
    while fin + 1 < len(lineas) and lineas[fin + 1].startswith(">"):
        fin += 1
    return (sum(len(x) + 1 for x in lineas[:ini]),
            sum(len(x) + 1 for x in lineas[:fin + 1]))


def _sub_en_cabecera(text: str, patron) -> str:
    """Borra la línea vieja de una cirugía de cabecera **sólo dentro del bloque de cabecera**."""
    #  @inv INV-15
    span = _header_block(text)
    if span is None:
        return text
    ini, fin = span
    return text[:ini] + patron.sub("", text[ini:fin], count=1) + text[fin:]


GT_LINE_RE = re.compile(r"^> _Ground-truth.*\n", re.M)


def ground_truth_line(slug: str) -> str:
    """La línea de procedencia: qué autoridad respondió cada campo canónico, cuándo, y dónde mirar.

    Se arma desde `_autoridad` del propio JSON (verdad de disco), no desde la tabla declarativa:
    lo que la ficha publica tiene que ser lo que **efectivamente** contestó, no lo que debería
    haber contestado. Si el JSON no existe, no se inventa nada."""
    gt_file = cfg.GROUND_TRUTH / f"{slug}.json"
    if not gt_file.exists():
        return ""
    try:
        gt = json.loads(gt_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    host = cfg.as_map(gt.get("host") if isinstance(gt, dict) else None)
    autoridad = cfg.as_map(host.get("_autoridad"))
    if not autoridad:
        return ""
    def visible(campo: str) -> str:
        # #272 — el campo que la ficha NO publica se nombra como lo que es. La cabecera existe para
        # que el artefacto viaje solo, así que prometer autoridad sobre un valor que el consumidor
        # no va a encontrar en el frontmatter es peor que no nombrarlo.
        nombre = cfg.CAMPO_EN_FICHA.get(campo, campo)
        if campo in cfg.CAMPO_EN_FRONTMATTER:
            return f"`{nombre}`"
        return f"`{nombre}` (sólo en el JSON)"

    por_fuente: dict = {}
    for campo, fuente in sorted(autoridad.items()):
        por_fuente.setdefault(fuente, []).append(visible(campo))
    if gt.get("planets"):
        por_fuente.setdefault("nea", []).append("`planets[]`")
    partes = [f"{', '.join(campos)} ← **{cfg.AUTORIDAD_NOMBRE.get(f, f)}**"
              for f, campos in sorted(por_fuente.items())]
    # Los campos canónicos que volvieron VACÍOS se nombran aparte. "La autoridad contestó y no
    # tiene el dato" y "nadie preguntó" se ven idénticos en el frontmatter (`null` en los dos), y
    # es justo la distinción que el lector necesita para saber si vale la pena buscarlo.
    sin_dato = sorted(visible(c) for c in cfg.AUTORIDAD_CAMPO
                      if c in host and host.get(c) in (None, "") and c not in autoridad)
    vacios = f" · sin dato: {', '.join(sin_dato)}" if sin_dato else ""
    cuando = gt.get("consultado")
    fecha = f", consultado {cuando}" if cuando else ""
    return ("> _Ground-truth — " + " · ".join(partes) + fecha + vacios +
            ". Cada campo vale lo que dice **su** autoridad o `null`: si calla, no se rellena con "
            f"literatura (va al cuerpo, citada). Detalle en `raw/ground_truth/{slug}.json`._\n")


def stamp_ground_truth_line(slug: str, dest) -> bool:
    """Estampa/actualiza la línea de procedencia. Mismo contrato que `stamp_estado`: cirugía
    anclada en `_Generado con Almagesto…_`, idempotente, nunca inventa cabecera."""
    if not dest.exists():
        return False
    new = ground_truth_line(slug)
    text = dest.read_text(encoding="utf-8")
    out = _sub_en_cabecera(text, GT_LINE_RE)
    if new:
        i = out.find(GENERATOR_LINE)
        if i < 0:
            return False
        out = out[:i] + new + out[i:]
    if out == text:
        return False
    cfg.write_text_atomic(dest, out)
    return True


# ── D-12: las TRES fechas de una nota ────────────────────────────────────────────────────────────
#
# Una nota tiene tres estados que avanzan por separado y **pueden divergir sin que ninguno mienta**:
# cuándo se buscó el corpus, cuándo se sintetizó la prosa, cuándo se verificaron las citas. Con una
# sola fecha, refrescar el corpus hacía parecer re-verificado lo que nadie volvió a chequear.
ESTADO_LINE_RE = re.compile(r"^> _Estado.*\n", re.M)


def estado_line(slug: str, dest) -> str:
    """La línea de estado de la cabecera: **búsqueda · síntesis · verificación** (INV-82). `""` si
    no hay ninguna.  @inv INV-82

    Las tres avanzan por separado y pueden divergir sin que ninguna mienta: refrescar el corpus
    mueve la de búsqueda y **no** la de síntesis, que es exactamente lo que hace legible que la
    prosa sea más vieja que el universo que la ficha declara."""
    bs = cfg.load_busquedas(slug)
    b = bs[-1] if bs else {}
    partes = []
    if b.get("fecha"):
        # Con UNA búsqueda se muestra `n_found` (lo que ADS dice que hay), como siempre. Con varias
        # se muestra el universo ACUMULADO (unión, D-28): ahí es donde el número viejo mentía, al
        # publicar el embudo de la última corrida como si fuera todo lo que la ficha vio.
        universo = (cfg.universo_acumulado(slug) if len(bs) > 1
                    else (b.get("n_found") or b.get("n_total") or "?"))
        # `acumulado`, NO `len(bs)` (#105). El conteo de CORRIDAS es bitácora, no contenido: crece
        # en cada re-run aunque no entre un solo paper nuevo, así que la nota cambiaba sin que
        # cambiara nada de lo que afirma — y el chequeo de idempotencia de la regla 6 ("corré dos
        # veces y hasheá vault/") daba falsa alarma para TODA estrella y TODO tema. Medido: dos
        # corridas idénticas de `ingest_theme.py ica` diferían sólo en esta línea (y en el
        # registro, que es la bitácora y sí debe crecer, D-28). Lo que el lector necesita saber es
        # que el universo es la UNIÓN de varias búsquedas y no el embudo de la última — eso lo dice
        # la palabra; cuántas veces se miró y cuándo lo dice el registro, que la línea ya linkea.
        # AUD-173 / INV-81 — los dos números tienen ALCANCES distintos cuando hay varias corridas:
        # el universo es la UNIÓN (D-28) y `n_core` es el de la ÚLTIMA. Publicarlos como `A → B`
        # los presenta como el embudo de una misma población, así que la ficha decía «1200 → 8
        # core» donde el 8 es de la última corrida sobre 40. Cada número lleva su alcance escrito.
        if len(bs) > 1:
            # ⚠ Sin `len(bs)`: el conteo de CORRIDAS es bitácora y crece en cada re-run aunque no
            # entre un paper nuevo — rompería la idempotencia de la regla 6 (#105).
            partes.append(f"búsqueda {b['fecha']} ({universo} acumulados; "
                          f"{b.get('n_core', '?')} core en esta corrida)")
        else:
            partes.append(f"búsqueda {b['fecha']} ({universo} → {b.get('n_core', '?')} core)")
        if b.get("n_candidates"):
            partes.append(f"{b['n_candidates']} sin juzgar")
        if b.get("truncated"):
            partes.append("⚠ truncada")
        if b.get("escotillas"):
            partes.append(f"escotillas {' '.join(b['escotillas'])}")
    sint = cfg.as_map(cfg.load_registro(slug).get("sintesis"))
    if sint.get("fecha"):
        # La declara el agente al cerrar la síntesis (`triage.py --sintesis`): no se puede derivar
        # —git fecha el ARCHIVO, y una cirugía de cabecera cuenta igual que reescribir el resumen—
        # y sin ella un refresh dejaba la ficha leyéndose como re-sintetizada.
        n = sint.get("n_papers")
        partes.append(f"síntesis {sint['fecha']}" + (f" ({n} papers)" if n else ""))
    texto = dest.read_text(encoding="utf-8") if dest.exists() else ""
    # AUD-136 — acá se buscaba el PRIMER encabezado con un regex propio, y el lint toma el MÁXIMO
    # (una nota acumula varios bloques: pasadas sucesivas sobre secciones distintas). Dos
    # implementaciones de la misma regla, contradictorias: la cabecera publicaba una fecha vieja
    # sobre una nota que el lint daba por re-verificada. Una sola función, en `lib_config`.
    _hay, fecha_verif = cfg.verification_date(texto)
    if fecha_verif:
        # La fecha es la de la última PASADA. La vigencia real es **por par** y la dicen las anclas
        # (D-4): sin la salvedad, esta fecha se lee como "todo verificado a esta fecha", que es
        # justamente la lectura que el ancla vino a corregir.
        partes.append(f"verificación {fecha_verif} (vigencia por par: la dicen las anclas)")
    if not partes:
        return ""
    # el puntero al registro es lo que hace auditable la línea: el detalle (query efectiva,
    # límites, lente, juicios de curación) vive ahí y no se duplica en la nota (#64).
    partes.append(f"registro en `config/registro/{slug}.yaml`")
    return "> _Estado — " + " · ".join(partes) + "._\n"


def stamp_estado(slug: str, dest) -> bool:
    """Estampa/actualiza la línea de estado en la cabecera de una nota existente.

    Mismo contrato que el viejo `stamp_search_line` (#64), al que ABSORBE — dos estampadores de
    cabecera conviviendo son la misma complejidad permanente que un lector tolerante: cirugía
    anclada en la línea
    `_Generado con Almagesto v…_`, nunca toca la prosa, y si la cabecera está fuera del contrato no
    inventa nada. **D-54:** si el contenido nuevo es idéntico al que ya está, no reescribe — un
    stamper que re-fecha en cada corrida ensucia el diff y hace ilegible qué cambió de verdad."""
    if not dest.exists():
        return False
    new = estado_line(slug, dest)
    text = dest.read_text(encoding="utf-8")
    out = _sub_en_cabecera(text, ESTADO_LINE_RE)
    if new:
        i = out.find(GENERATOR_LINE)
        if i < 0:
            return False
        out = out[:i] + new + out[i:]
    if out == text:
        return False
    cfg.write_text_atomic(dest, out)
    return True


def write_star_note(slug: str, force: bool) -> None:
    # @inv INV-01, INV-07
    name, meta = cfg.star_by_slug(slug)
    dest = cfg.STARS / f"{slug}.md"
    if dest.exists() and not force:
        # la nota no se pisa; sólo se refresca el apéndice máquina con el ads.json vigente (#35)
        stamped = (stamp_excluded(slug, dest) | stamp_papers_table(slug, dest, "star")
                   | stamp_ground_truth_line(slug, dest) | stamp_estado(slug, dest))
        cfg.print_seguro(f"  star: {dest.name} ya existe"
              + (" — apéndice Excluidos / lista de papers / puntero de búsqueda re-estampados" if stamped
                 else " (usa --force para regenerar)"))
        return
    gt_file = cfg.GROUND_TRUTH / f"{slug}.json"
    gt = json.loads(gt_file.read_text(encoding="utf-8")) if gt_file.exists() else {"host": {}, "planets": []}
    # ⛔ Las cuatro formas malformadas que el LINT sí contempla (`host` null o no-mapa, `planets`
    # null o con elementos que no son mapas) reventaban acá con `AttributeError`/`TypeError`:
    # `sync_mirror` las blindó en este mismo archivo y `write_star_note` quedó afuera. Es el patrón
    # que la auditoría del 2026-08-28 encontró seis veces —el arreglo aplicado a un sitio y no a su
    # gemelo—. Cobarde y RUIDOSO, mismo criterio que `sync_mirror`: se avisa cuál es la forma mala
    # y se sigue con lo que se puede, en vez de tumbar la escritura de la ficha entera.
    gt = cfg.as_map(gt)
    raw_host = gt.get("host")
    if raw_host is not None and not isinstance(raw_host, dict):
        cfg.print_seguro(f"  ⚠ {slug}: `host` del ground-truth no es un mapa ({raw_host!r}) — la "
                         f"ficha se escribe con los campos estelares vacíos")
    host = cfg.as_map(raw_host)
    raw_planets = gt.get("planets")
    if raw_planets is not None and (not isinstance(raw_planets, list)
                                    or not all(isinstance(pl, dict) for pl in raw_planets if pl)):
        cfg.print_seguro(f"  ⚠ {slug}: `planets` del ground-truth no es una lista de mapas — la "
                         f"ficha se escribe SIN planetas; arreglá el JSON y re-corré")
        raw_planets = []
    # Espejo puro de NEA (#70): un null acá es un null de NEA (pl_rvamp/pl_orbeccen faltan seguido,
    # el caso es normal, no excepcional) y NO se rellena con el valor de un paper — ése va al cuerpo
    # con su `[[bibcode]]`, o a `disputes[]` si discrepa. Lo vigila el lint.
    planets = [{"letter": p.get("letter"), "P_days": p.get("P_days"),
                "K_ms": p.get("K_ms"), "e": p.get("e"),
                "mass_earth": p.get("mass_earth"),   # masa NEA (M⊕); RV-only ≈ m·sini. Lint valida consistencia.
                "status": p.get("status")}
               for p in (raw_planets or []) if isinstance(p, dict)]

    front = {
        "name": name,
        "slug": slug,
        "aliases": _listify_curado(meta.get("aliases"), "aliases"),
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
        # #272 — la masa estelar, espejo puro como los de arriba. Es el factor que convierte K en
        # m·sini, así que sin él la ficha no puede publicar ni siquiera como `inferencia` cuánto
        # mueve a las masas mínimas la dispersión de la literatura.
        "mass_msun": host.get("mass_msun"),
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
_(se estampa determinista: `make_notes.py {slug}` lo regenera.)_

## Papers
_(se estampa determinista: `make_notes.py {slug}` lo regenera. D-11 — ninguna promesa del contrato
depende de un plugin.)_

## Indicadores de actividad esperados
_(se estampa determinista: `make_notes.py {slug}` lo regenera.)_

## Métodos aplicados a esta estrella
_(se estampa determinista: `make_notes.py {slug}` lo regenera.)_

<!-- AUD-189 / INV-5: `data_local` NO se copia al cuerpo. La regla afinada de la frontera dura
     (CLAUDE.md) permite el puntero downstream como CAMPO ESTRUCTURAL del frontmatter —es parte del
     contrato máquina-legible— y lo prohíbe en PROSA, que es donde describe al consumidor. La
     sección `## Datos crudos` hacía exactamente eso: duplicaba texto libre del usuario, con rutas
     de otra máquina, en la capa que el contrato declara síntesis. El dato sigue en el frontmatter,
     que es su lugar. -->
"""
    body += excluded_table(slug)
    # como los otros dos writers (concept y papers): la carpeta puede no existir — git no
    # versiona directorios vacíos, así que una bóveda sin `vault/wiki/stars/` (clon con el
    # scratch limpiado, árbol armado a mano) moría con un traceback de FileNotFound.
    dest.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text_atomic(dest, body)
    stamp_papers_table(slug, dest, "star")
    stamp_star_rollups(slug, dest)
    stamp_ground_truth_line(slug, dest)
    stamp_estado(slug, dest)
    cfg.print_seguro(f"  star: {dest.name} escrito")


def write_concept_note(slug: str, force: bool) -> None:
    """Para temas (ingest-theme): stub del concept durable destino. Idempotente: NO pisa la
    síntesis LLM de un concept ya existente salvo --force (protege la síntesis)."""
    _, meta = cfg.theme_by_slug(slug)
    area = cfg.require_field(meta, "area", slug, "themes.yaml")
    concept = cfg.require_field(meta, "concept", slug, "themes.yaml")
    # Las áreas de concepts/ son ABIERTAS: no se prohíbe ninguna (podés investigar cualquier tema).
    # `concept_areas` (objective.yaml) es sólo una REFERENCIA para distinguir un typo de un área nueva
    # legítima → si el área no está declarada, AVISAR (nunca bloquear) para que un typo no pase mudo.
    # El lint la marca después; si era un área nueva real, agregala a concept_areas para silenciar el aviso.
    if (areas_ref := cfg.load_concept_areas()) and area not in areas_ref:
        cfg.print_seguro(f"  ⚠ área '{area}' (theme '{slug}') no está en concept_areas (objective.yaml). "
              f"Si es un typo, corregí themes.yaml; si es un área nueva, agregala a la lista. Creo igual.")
    dest = cfg.CONCEPTS / area / f"{concept}.md"
    if dest.exists() and not force:
        # la síntesis no se pisa; sólo se refresca el apéndice máquina con el ads.json vigente (#35)
        # #196: `stamp_papers_table` va TAMBIÉN. Una nota de concepto puede llevar el encabezado
        # estilo ficha (`## Papers`) en vez del roll-up de tema, y `stamp_concept_rollup` ancla sólo
        # en el suyo: sobre esa nota la tabla quedaba congelada y la cirugía devolvía `False` sin
        # decir nada. Los dos estampadores conviven porque cada uno ancla en su propio encabezado y
        # el que no matchea es un no-op.
        stamped = (stamp_excluded(slug, dest) | stamp_papers_table(slug, dest, kind="theme")
                   | stamp_concept_rollup(slug, dest) | stamp_estado(slug, dest))
        cfg.print_seguro(f"  concept: {area}/{concept}.md ya existe"
              + (" — apéndice Excluidos / tabla de papers / roll-up / puntero de búsqueda re-estampados"
                 if stamped else " (no se pisa sin --force; los papers enganchan por thesis_links)"))
        # El roll-up de papers tiene que existir bajo ALGUNO de los dos encabezados. Si no está
        # ninguno, la nota se queda sin esa cirugía para siempre y hasta #196 no lo decía nadie
        # (`stamp_excluded` agrega su sección si falta, y la cabecera ya la vigila el lint por #69,
        # así que ésas no hacen falta acá).
        if missing_anchors(dest, [PAPERS_HEADER, CONCEPT_ROLLUP_HEADER]) == [PAPERS_HEADER,
                                                                            CONCEPT_ROLLUP_HEADER]:
            cfg.print_seguro(f"  ⚠ la nota no tiene `{PAPERS_HEADER}` ni `{CONCEPT_ROLLUP_HEADER}`: "
                             "el roll-up de papers no se puede estampar (agregá uno de los dos)")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    front = {"name": meta.get("title", concept)}
    if area == "hypotheses":          # `status` sólo en hipótesis (schema name,status; ver CLAUDE.md)
        # #175: acá decía `"active"`, que no está en el vocabulario cerrado de D-37 — así que toda
        # hipótesis nueva nacía con un bloqueante del lint que la propia máquina se fabricaba. Sale
        # de `lib_config`, la misma constante que el lint valida.
        front["status"] = cfg.HYP_STATUS_INICIAL
    front.update({
        "aliases": _listify_curado(meta.get("aliases"), "aliases"),   # sinónimos EN+ES para grep; sembrado del theme, el LLM enriquece
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
    propias = HIPOTESIS_SECCIONES if area == "hypotheses" else ""
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
{REGIMEN}{propias}## Huecos
_(qué falta para entender/implementar el tema sin abrir papers: pasos o ecuaciones faltantes,
**regímenes no cubiertos** (los que la tabla de arriba deja fuera: ¿en qué condiciones nadie lo
midió?), contradicciones sin resolver.)_

## Papers que tocan este tema (auto)
_(se estampa determinista: `make_notes.py {slug} --theme` lo regenera. D-11/D-24 — unión de
`methods` y `thesis_links`, declarando por cuál entró.)_
"""
    body += excluded_table(slug)
    cfg.write_text_atomic(dest, body)
    stamp_concept_rollup(slug, dest)
    stamp_estado(slug, dest)
    cfg.print_seguro(f"  concept: {area}/{concept}.md escrito (stub)")


def write_paper_notes(slug: str, include_all: bool, force: bool, theme: bool = False) -> None:
    if theme:
        _, tmeta = cfg.theme_by_slug(slug)
        name, link, seed_links = None, tmeta["concept"], [tmeta["concept"]]
    else:
        name, _ = cfg.star_by_slug(slug)
        link, seed_links = slug, []
    adsfile = cfg.ROOT / "build" / slug / "ads.json"
    if not adsfile.exists():
        cfg.print_seguro(f"  (sin {adsfile}; corré query_ads.py primero)")
        return
    recs = json.loads(adsfile.read_text(encoding="utf-8"))["records"]
    # #112 (cuarto consumidor): `--drop-core` vive en el registro VERSIONADO; `relevant` vive en
    # `build/`, que sólo `query_ads` reescribe. Sin este filtro, correr `make_notes` solo —lo que el
    # propio aviso del drop invita a hacer— RESUCITA el paper dropeado como stub, y encima encima de
    # la extracción que el drop acababa de borrar: la nota vuelve a existir y vuelve vacía. Va antes
    # que `include_all` a propósito: `--all` pide los no-core, no lo que el usuario sacó a mano.
    dropeados = set(cfg.dropped_from_subject(slug))
    if dropeados and (n := sum(1 for r in recs if r.get("bibcode") in dropeados)):
        recs = [r for r in recs if r.get("bibcode") not in dropeados]
        cfg.print_seguro(f"  ({n} paper(s) excluidos del sujeto por `--drop-core`: no se les "
                         f"escribe nota)")
    if not include_all:
        recs = [r for r in recs if r["relevant"]]
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    # El SUJETO de esta corrida (#188): el mismo nombre con el que el paper lo declara en
    # `stars`/`thesis_links`, que es lo que hace comparables reclamo y lectura.
    sujeto = link if theme else name
    extraccion = vista_block(sujeto, theme)  # una sola lectura del objetivo para toda la corrida
    # D-19: identidades ya presentes en el corpus. Crear una segunda nota del MISMO trabajo (el
    # preprint y el publicado tienen bibcodes distintos y el mismo `arxiv_id`) mete doble conteo en
    # todo lo que cuenta papers, y un falso positivo permanente de #75 —la ficha cita una de las
    # dos—. Se atajan acá, que es donde nacen.
    ya_en_corpus = {}
    for f in cfg.PAPERS.glob("*.md"):
        if (ident := identidad(cfg.split_fm(f.read_text(encoding="utf-8")))):
            ya_en_corpus.setdefault(ident, f.stem)
    written = skipped = merged = restamped = duplicados = 0
    for r in recs:
        bib = r["bibcode"]
        dest = cfg.PAPERS / f"{safe_name(bib)}.md"
        if not dest.exists() and (ident := identidad(r)) and ident in ya_en_corpus:
            otro = ya_en_corpus[ident]
            cfg.print_seguro(
                f"  ⊘ {bib}: mismo trabajo que {otro} ({ident[0]}: {ident[1]}) — NO se crea una "
                f"segunda nota. Si {bib} es la versión que corresponde, renombrá: "
                f"`python scripts/make_notes.py --rename-paper {otro} {bib}`")
            duplicados += 1
            continue
        # AUD-197 — `--force` significa «pisá la nota de ESTE sujeto», no «pisá cualquier nota».
        # Un paper compartido lleva la vista y la extracción de OTRO sujeto (#188: medido, 141 de
        # 908 notas las reclaman 2+), y reescribirla desde el stub las borra: trabajo caro, ajeno a
        # la operación en curso y que nadie pidió tocar. Se saltea y se dice cómo seguir.
        if dest.exists() and force:
            _fm_prev = cfg.split_fm(dest.read_text(encoding="utf-8"))
            _ajenos = sorted(
                {str(v_.get("sujeto")) for v_ in cfg.as_list(_fm_prev.get("vistas"))
                 if isinstance(v_, dict) and str(v_.get("sujeto") or "").strip() != sujeto}
                | ({str(x) for x in cfg.as_list(_fm_prev.get("thesis_links" if theme else "stars"))}
                   - {sujeto}))
            if _ajenos:
                cfg.print_seguro(
                    f"  ⊘ {bib}: `--force` NO lo pisa — la nota también es de "
                    f"{', '.join('«%s»' % a for a in _ajenos[:3])}"
                    + (" …" if len(_ajenos) > 3 else "")
                    + ", y reescribirla desde el stub borraría su vista y su extracción. Editala a "
                      "mano, o corré `--force` desde el sujeto que la escribió.")
                skipped += 1
                continue
        if dest.exists() and not force:
            # Retro-linkeo add-only (issue #4b): el paper ya estaba en el corpus (ingest previo de
            # otra estrella/tema) → no se pisa la extracción LLM, pero SÍ se mergean los seeds de
            # este ingest (tema → thesis_links; estrella → stars) para que la nota aparezca en las
            # tablas Dataview de la entidad nueva. Idempotente: si ya están, no toca nada.
            seeds = seed_links if theme else ([name] if name else [])
            if seeds and merge_frontmatter_list(dest, "thesis_links" if theme else "stars", seeds):
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
            "facets": r.get("facets", []),
            # D-17. ADS ya las devuelve y `ads.json` ya las persiste; la nota las tiraba. Hacen falta
            # para el diff de lente OFFLINE (D-49): la lente matchea sobre título + abstract +
            # KEYWORDS, así que re-clasificar desde una nota sin ellas daría un veredicto distinto
            # del que dio el ingest — un diff inventado.
            "keywords": cfg.as_list(r.get("keyword")),
            # #86: este paper se clasificó SIN abstract (título + keywords y nada más). Va a la nota
            # por el mismo motivo que las keywords (D-17): si muere en `build/`, que es gitignored,
            # el diff de lente offline no puede saber con cuánta información se lo juzgó.
            **({"sin_abstract": True} if r.get("sin_abstract") else {}),
            "methods": [],                 # poblar con extracción LLM
            "thesis_links": list(seed_links),  # tema: pre-sembrado al concept; estrella: vacío
            # ROL del paper dentro del tema/entidad (#73), poblado por la EXTRACCIÓN:
            # fundacional | aplicacion | arbitro (uno o varios). `bearing` dice la POSTURA respecto
            # de una tesis; `role` dice QUÉ TIPO DE APORTE es, que es lo que define la operación de
            # contraste. El clasificador no puede darlo: la regex clasifica tema, no rol.
            "role": [],
            # #188 · la vista de ESTE sujeto, declarada al crear el stub. Sin `fecha`: la lectura
            # todavía no ocurrió, y la ausencia es «no consta» (paso 1). La estampa la extracción
            # cuando lee (con `txt` y `lente`), y el lint reporta como backlog la vista sin fecha.
            # ⛔ El RETRO-LINK no pasa por acá y no debe: `stars`/`thesis_links` se mergean
            # add-only **sin leer nada**, así que siguen siendo RECLAMOS. Si el retro-link
            # declarara vistas, volvemos al problema que el campo vino a cerrar.
            "vistas": [{"sujeto": sujeto, "tipo": "theme" if theme else "star"}],
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

{LLM_DISCLAIMER["paper"]}

## Abstract
{abstract or cfg.ABSTRACT_PLACEHOLDER}

{extraccion}"""
        cfg.write_text_atomic(dest, body)
        written += 1
    cfg.print_seguro(f"  papers: {written} escritos, {skipped} ya existían"
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
    lim = cfg.fm_bounds(text)             # AUD-147
    if lim is None:
        return False
    ini, end = lim
    if "\npending_source:" not in text[:end]:
        return False
    has_pdf = (cfg.PDFS / slug / f"{safe_name(citekey)}.pdf").exists()
    has_txt = (cfg.FULLTEXT / slug / f"{citekey}.txt").exists()
    if not (has_pdf or has_txt):
        return False                     # la fuente sigue faltando: el flag se queda
    head, body = text[ini:end], text[end:]
    # `pending_motivo` viaja con `pending_source` (#80) y sale con él: dejarlo suelto deja la nota
    # con el motivo de un estado que ya no existe —«nadie la está consiguiendo»— sobre una fuente
    # que YA llegó. Hallazgo de la pasada `/auditar` del 2026-08-28.
    lines = _drop_keys(head, ("pending_source:", "pending_motivo:"))
    if has_pdf:
        pdf_rel = f"../../raw/pdfs/{slug}/{safe_name(citekey)}.pdf"
        lines = [f"pdf: {pdf_rel}" if ln.strip() == "pdf: null" else ln for ln in lines]
    body = "\n".join(ln for ln in body.split("\n")
                     if not ln.startswith("> ⏳ **Fuente pendiente"))
    nuevo = text[:ini] + "\n".join(lines) + body
    # #244 — red decisiva: una operación no puede dejar la nota PEOR de lo que la encontró. Si el
    # frontmatter dejó de parsear, no se escribe. Mismo principio que contar los pares antes y
    # después en `apply_fixes` (#222), y acá cuesta un `split_fm`.
    if cfg.split_fm(text) and not cfg.split_fm(nuevo):
        cfg.print_seguro(f"  ⛔ {dest.name}: sacar `pending_source` dejaría el frontmatter sin "
                         f"parsear — NO se escribe. Revisá el YAML a mano.")
        return False
    cfg.write_text_atomic(dest, nuevo)
    cfg.print_seguro(f"  papers: {dest.name} — fuente obtenida → pending_source removido"
          + (" y `pdf` linkeado" if has_pdf else ""))
    return True


def _drop_keys(yaml_block: str, prefijos: tuple) -> list:
    """Frontmatter lines with those keys removed, **including their continuation lines** (#244).

    Filtering by `startswith` alone deletes the first line of a block scalar and leaves the
    indented continuation orphaned, so the YAML stops parsing — and the note then evades every
    per-type check, which the lint reports as BLOCKING. It is not a rare case: `pending_motivo` is
    mandatory free text (#80), so any motive over ~90 characters serialises multi-line, and the
    happy path of #80 —«when the source arrives, replace `pending` by `pdf:` and re-run»— broke the
    note every time.

    ⛔ Third time this repo pays for this shape: `_set_lista_de_mapas` already carries the same
    `dropping` flag, and its own comment records that without it a `--rename-paper` left the note
    ILLEGIBLE for the whole tooling.
    """
    out, dropping = [], False
    for ln in yaml_block.split("\n"):
        if ln.startswith(prefijos):
            dropping = True
            continue
        if dropping:
            if ln[:1] in (" ", "\t") and ln.strip():
                continue                  # línea de continuación del escalar que se borró
            dropping = False
        out.append(ln)
    return out


def write_web_paper_note(citekey: str, *, url: str | None = None, slug: str | None = None,
                         concept: str | None = None, title: str | None = None,
                         first_author: str | None = None, year=None, n_authors=None,
                         doi: str | None = None, venue: str | None = None,
                         accessed: str | None = None, pending: str | None = None,
                         pending_motivo: str | None = None,
                         unidad_cita: str | None = None, alcance: str | None = None,
                         force: bool = False) -> bool:
    """Stub de nota de paper para una fuente **off-ADS** (web o PDF sin bibcode ADS) — modo off-ADS de
    ingest-theme. Análogo a write_paper_notes pero **sin ads.json**: la metadata la provee quien llama
    (fetch_web.py, ingest_theme.py o el usuario). `bibcode` = clave sintética AAAA+Autor; `arxiv_id`
    null; `n_authors`/`doi` los del item de `sources:` si se declararon (un PDF con DOI sigue siendo
    off-ADS — no tiene bibcode ADS — pero el DOI habilita check_retractions);
    `pdf` normalmente null (el respaldo citable es el snapshot `.txt` de fulltext/) — salvo que el
    PDF off-ADS ya esté copiado en raw/pdfs/<slug>/<citekey>.pdf (fuente local-pdfs, lo hace
    ingest_theme.py), en cuyo caso se linkea solo (así el chequeo PDF↔disco del lint no marca drift);
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
    #  @inv INV-61
            stamp_fulltext(dest, safe_name(citekey), slug)
            stamp_pdf_link(dest)         # unpend_note pudo linkear `pdf:` → la cabecera lo sigue (#47)
            return False
        if not pending and stamp_fulltext(dest, safe_name(citekey), slug):
            stamp_pdf_link(dest)
            cfg.print_seguro(f"  papers: {dest.name} — fulltext estampado (contrato máquina)")
            return False
        if not pending and stamp_pdf_link(dest):
            cfg.print_seguro(f"  papers: {dest.name} — link [📄 PDF] de cabecera re-estampado (#47)")
            return False
        cfg.print_seguro(f"  papers: {dest.name} ya existe (no se pisa sin --force)")
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
        "facets": [],
        "keywords": [],                      # off-ADS: no hay keywords de catálogo que copiar
        "methods": [],                       # poblar con extracción LLM
        "thesis_links": [concept] if concept else [],   # pre-sembrado al concept
        "role": [],                          # fundacional | aplicacion | arbitro (#73) — extracción
        "relevance": "high",
        # `null`, NO 0 (#106). Off-ADS no hay catálogo que dé el conteo, así que el valor honesto es
        # «no lo sé». Un 0 afirma «no lo cita nadie» sobre un dato que nadie miró — medido: la nota
        # de Comon 1994 decía 0 y el trabajo tiene 8266 citas. No es cosmético: la **puerta 2** de
        # D-26 admite core por este número y su detector (INV-104) lo compara contra el umbral, así
        # que un 0 inventado se lee como «no llega, y lo verificamos». Es la misma doctrina que
        # `search_arxiv.to_record`, que ya pone None por esto mismo.
        "citation_count": None,
        "pdf": pdf_rel,                      # off-ADS: null salvo PDF local ya copiado a raw/pdfs/<slug>/
        "fulltext": txt_rel,                 # el artefacto BARATO del contrato: leer/grep esto, no el PDF
        "fulltext_source": txt_src,          # pdftotext | ocr (citable con salvedad) | web
        "pdf_source": pdf_src,               # de QUÉ documento salió (#57): web | eprint | … | null
        **({"eprint_version": pdf_ver} if pdf_ver else {}),
        # fuente aún no obtenida (paywall|scan|unextractable) → derivada al usuario; sólo si aplica
        **({"pending_source": pending} if pending else {}),
        # #80: el motivo libre viaja al lado de la categoría. Sin él, `pending_source: paywall` en
        # una nota no dice si alguien la está consiguiendo o si nadie la miró nunca.
        **({"pending_motivo": pending_motivo} if pending and pending_motivo else {}),
        # #80: cómo se apunta dentro de esta fuente y qué parte de ella entró. `linea` es el default
        # y no se estampa: el campo existe para el caso raro —un libro, un handbook— donde citar por
        # línea no sirve y la fuente NO entra entera.
        **({"unidad_cita": unidad_cita} if unidad_cita and unidad_cita != "linea" else {}),
        **({"alcance": alcance} if alcance else {}),
        # #188 · off-ADS el sujeto es SIEMPRE un tema (es el modo opt-in de ingest-theme).
        "vistas": [{"sujeto": concept or citekey, "tipo": "theme"}],
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
    # off-ADS es el modo opt-in de ingest-theme (CLAUDE.md): acá el sujeto es SIEMPRE un tema.
    body = f"""{fm(front)}
# {title or citekey}

**{first_author or '(autor desconocido)'}** ({year or 's.f.'})
· {'[[' + concept + ']] · ' if concept else ''}fuente off-ADS · `{citekey}`{f' · [📄 PDF]({pdf_rel})' if pdf_rel else ''}
{src_line}{acc_line}
> Fuente **off-ADS** (fuera de ADS). El respaldo citable es el snapshot determinista
> `{txt_ptr}` (`source_url` + `accessed` en el frontmatter), verificable por `verify-citations`.
> El frontmatter es máquina-legible como en cualquier nota de paper.

{LLM_DISCLAIMER["paper"]}
{pend_line}
## Abstract
{cfg.ABSTRACT_PLACEHOLDER}

{vista_block(concept or citekey, theme=True)}"""
    cfg.write_text_atomic(dest, body)
    cfg.print_seguro(f"  papers: {dest.name} escrito (stub off-ADS)")
    return True



def _flags_usados(args, ap=None) -> list:
    """Los flags no-default de esta corrida, para dejarlos en `cadena:` del registro (D-48/D-57).
    Son las **escotillas**: `--force`, `--yes`, `--all` cambian lo que la corrida hizo, y sin
    registrarlas la traza dice "corrió make_notes" sobre dos corridas que no hicieron lo mismo."""
    return cfg.flags_usados(args, ap)

def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser()
    ap.add_argument("--rename-paper", nargs=2, metavar=("VIEJO", "NUEVO"),
                    help="renombra una nota de paper y sus artefactos, agrega el bibcode viejo a "
                         "`versions[]` y reescribe los wikilinks de la bóveda (ciclo "
                         "preprint→publicado, D-19)")
    ap.add_argument("slug", nargs="?",
                    help="slug de estrella/tema; en --web es la CLAVE de cita (AAAA+Autor). "
                         "Opcional sólo con --restamp-pdf-links.")
    ap.add_argument("--all", action="store_true", help="incluir papers no-relevantes")
    ap.add_argument("--restamp-pdf-links", action="store_true", dest="restamp_pdf_links",
                    help="backfill #47: barre TODAS las notas de papers y re-estampa el link "
                         "[📄 PDF] de la cabecera desde el frontmatter `pdf` (agrega/corrige/quita). "
                         "No toca la extracción LLM; no requiere slug.")
    ap.add_argument("--restamp-keywords", action="store_true", dest="restamp_keywords",
                    help="backfill D-17: estampa `keywords:` en las notas de paper que nacieron "
                         "sin ellas, desde build/*/ads.json. Add-only (no pisa las que ya están); "
                         "declara cuántas quedaron sin cubrir por falta de build/. No requiere slug.")
    ap.add_argument("--restamp-index", action="store_true", dest="restamp_index",
                    help="#237: materializa las tablas de `vault/wiki/index.md` por verdad de "
                         "frontmatter (estrellas, conceptos, papers). El catálogo era el único "
                         "artefacto 100%% Dataview —lo que #60 prohibió para los roll-ups— y el paso "
                         "de bookkeeping mandaba «agregar el concepto» a un archivo sin una sola "
                         "línea estática. Idempotente, cirugía: no toca `## Matrices` ni la prosa. "
                         "No requiere slug.")
    ap.add_argument("--restamp-headers", action="store_true", dest="restamp_headers",
                    help="backfill #69: barre TODAS las fichas/conceptos y estampa la cabecera "
                         "(aviso de capa LLM + línea del generador) a las que nacieron sin ella. "
                         "La versión sale del `generator` del frontmatter, no se inventa. No toca "
                         "la síntesis LLM; no requiere slug.")
    ap.add_argument("--migrate-facets", action="store_true", dest="migrate_facets",
                    help="migración R-5: renombra `topics:` → `facets:` en las notas de paper "
                         "(quirúrgico, no toca la extracción LLM). No requiere slug.")
    ap.add_argument("--migrate-registros", action="store_true", dest="migrate_registros",
                    help="migración D-28: pliega `busqueda:` (mapa) en `busquedas: []` "
                         "preservando la corrida vieja. No requiere slug.")
    ap.add_argument("--migrate-disputes", action="store_true", dest="migrate_disputes",
                    help="migración #71: pasa `planets[].disputes[]` (polo de verdad hardcodeado) a "
                         "`disputes` a nivel nota con posiciones explícitas. Toca sólo las fichas "
                         "que tienen disputas viejas; no toca el cuerpo. No requiere slug.")
    ap.add_argument("--migrate-verif-archivo", action="store_true", dest="migrate_verif_archivo",
                    help="migración #117: prefija cada `Hash fuente` del bloque de verificación con "
                         "el archivo que se leyó (`txt:`/`pdf:`), deducido del hash que la fila ya "
                         "guardaba. No requiere slug.")
    ap.add_argument("--migrate-bearing", action="store_true", dest="migrate_bearing",
                    help="migración D-21: saca `bearing:` del frontmatter de las notas de paper (la "
                         "postura vive en la tabla de evidencia de la hipótesis). No requiere slug.")
    ap.add_argument("--migrate-txt-fields", action="store_true", dest="migrate_txt_fields",
                    help="migración #205: saca `symbols_lost:` y `fulltext_layout:` del frontmatter "
                         "de las notas de paper (la fuente de lectura es el PDF, así que ya no "
                         "deciden nada). No requiere slug.")
    ap.add_argument("--migrate-source-fields", action="store_true", dest="migrate_source_fields",
                    help="migración #296: `pdf_source`/`fulltext_source` fuera de su vocabulario "
                         "cerrado → `null`, y la prosa que vivía en el campo se MUEVE (a "
                         "`pending_motivo` o a `salvedades`), no se tira. No requiere slug.")
    ap.add_argument("--migrate-vistas", action="store_true", dest="migrate_vistas",
                    help="migración #188: `## Extracción (LLM)` → `vistas[]` + `## Vista — "
                         "<sujeto>`. El sujeto sale del reclamo de la nota cuando es UNO solo; con "
                         "varios se lista para declararlo a mano (elegir uno afirmaría una lectura "
                         "que nadie hizo). No estampa `fecha`: ausente es «no consta». Sin slug.")
    ap.add_argument("--clean-catalog-markup", action="store_true", dest="clean_catalog_markup",
                    help="backfill #271: saca el markup crudo de catálogo (`<SUB>`, `<ASTROBJ>`, "
                         "`<A href>`…) de `## Abstract` en las notas de paper. ⚠ Cambia bytes que "
                         "leen el detector de duplicados (#216) y el diff de lente (D-49): "
                         "re-medilos después. Sin slug.")
    ap.add_argument("--restamp-vista-stub", action="store_true", dest="restamp_vista_stub",
                    help="migración #269: re-estampa la plantilla de `## Vista` en las notas que "
                         "todavía traen la anterior (la que mandaba citar por nº de línea del "
                         "`.txt`). Sin ella el cosechador deja de reconocerlas y no escribe la "
                         "vista. No toca una vista con prosa. Sin slug.")
    ap.add_argument("--restamp-abstracts", action="store_true", dest="restamp_abstracts",
                    help="backfill #277: escribe el `## Abstract` que falte en una nota de paper "
                         "(contenido `_(no disponible)_` — lo completa la próxima extracción). La "
                         "sección es obligatoria: es la capa auditable del cuerpo. Sin slug.")
    ap.add_argument("--sync-mirror", action="store_true", dest="sync_mirror",
                    help="backfill: rellena en `stars/` los campos espejo de NEA (#70) que están en "
                         "null y el ground-truth sí trae (spectral_type/teff_K/dist_pc/P_rot_days y "
                         "los cinco de cada planeta). Add-only: nunca pisa un valor existente ni "
                         "distinto del ground-truth (eso se reporta, no se toca). No requiere slug.")
    ap.add_argument("--force", action="store_true", help="pisar notas existentes")
    ap.add_argument("--theme", action="store_true",
                    help="el slug es un TEMA de vault/config/themes.yaml: genera concept en vez de ficha de estrella")
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
    # #154: los `choices` salen de `cfg.PENDING_OK`, no de una copia a mano. La lista literal se
    # quedó en tres cuando #80 agregó `adquisicion` (un libro que el usuario va a conseguir NO
    # falló: tiene otra latencia), así que el único CLI que estampa `pending_source` no podía emitir
    # el valor que el vocabulario declara. La asimetría era silenciosa porque el otro camino
    # (`themes.yaml` vía `ingest_theme`) sí valida contra la constante.
    ap.add_argument("--pending", choices=list(cfg.PENDING_OK),
                    help="(--web) fuente aún no conseguible: estampa pending_source y deriva al "
                         "usuario. Exige --reason (el motivo es obligatorio, #80)")
    # #164: el camino CLI no podía producir `pending_motivo` —ni bandera ni paso en la llamada—, así
    # que escribía una nota FUERA del schema de #80 y ningún chequeo del lint la cazaba. Mismo
    # argumento que el `--reason` del triage: en seis meses sirve el motivo, no la categoría.
    ap.add_argument("--reason", dest="pending_motivo",
                    help="(--web --pending) POR QUÉ está pendiente y quién la consigue (obligatorio)")
    args = ap.parse_args()

    if args.restamp_pdf_links:
        return restamp_pdf_links()
    if args.restamp_keywords:
        return restamp_keywords()
    if args.restamp_index:
        return restamp_index()
    if args.restamp_headers:
        return restamp_headers()
    if args.restamp_abstracts:
        return restamp_abstracts()
    if args.restamp_vista_stub:
        return restamp_vista_stub()
    if args.clean_catalog_markup:
        return clean_catalog_markup_notes()
    if args.migrate_bearing:
        n = migrate_all_bearing()
        cfg.print_seguro(f"`bearing` retirado de {n} nota(s) de paper (D-21).")
        return 0
    if args.migrate_txt_fields:
        n = migrate_all_txt_fields()
        cfg.print_seguro(f"`symbols_lost`/`fulltext_layout` retirados de {n} nota(s) (#205).")
        return 0

    if args.migrate_source_fields:
        n, movidas = migrate_all_source_fields()
        cfg.print_seguro(f"{n} nota(s) con `pdf_source`/`fulltext_source` fuera de vocabulario → "
                         f"`null` (#296).")
        for stem, destino in movidas:
            cfg.print_seguro(f"  {stem}: la prosa se movió a `{destino}` — revisala")
        return 0

    if args.migrate_vistas:
        n, ambiguas = migrate_all_vistas()
        cfg.print_seguro(f"{n} nota(s) migradas a `vistas[]` + `## Vista — <sujeto>` (#188).")
        if ambiguas:
            cfg.print_seguro(
                f"  ⚠ {len(ambiguas)} nota(s) NO se pudieron migrar solas: el sujeto de la vista "
                f"no es inequívoco (elegir uno afirmaría una lectura que nadie hizo desde ahí). "
                f"Declarala a mano en cada una:")
            for stem, cands in ambiguas[:20]:
                cfg.print_seguro(f"      {stem}: {', '.join(cands) or '(sin reclamos)'}")
            if len(ambiguas) > 20:
                cfg.print_seguro(f"      … y {len(ambiguas) - 20} más")
        return 0

    if args.migrate_verif_archivo:
        return migrate_all_verif_archivo()
    if args.migrate_facets:
        migrate_all_facets()
        return 0
    if args.migrate_registros:
        migrate_all_registros()
        return 0
    if args.migrate_disputes:
        return migrate_all_disputes()
    if args.sync_mirror:
        return sync_mirror()
    # `--rename-paper VIEJO NUEVO` ANTES del guard de slug: sus dos bibcodes son el argumento y no
    # hay slug que dar. El despacho estaba después, así que **el comando que la doc publica**
    # —`CLAUDE.md`, el stdout de `make_notes`, el del lint y el de `sweep_external` lo imprimen sin
    # slug— moría con exit 2 antes de llegar a su rama. Un comando publicado que no corre es peor
    # que uno ausente: el usuario lo copia y el ciclo preprint→publicado queda a medias.
    if args.rename_paper:
        rename_paper(*args.rename_paper)
        # #231 / D-57 — la rama retornaba ANTES del `save_paso` del final, así que consolidar un
        # duplicado —una operación que mueve archivos y reescribe wikilinks de TODA la bóveda— no
        # dejaba rastro en `cadena`. El slug sale de dónde viven los artefactos del bibcode nuevo:
        # es la misma verdad de disco con la que se movieron.
        for _slug in _slugs_of_bibcode(args.rename_paper[1]):
            cfg.save_paso(_slug, "make_notes", flags=["rename-paper"])
        return 0
    if not args.slug:
        ap.error("falta el slug (corren sin slug: --restamp-pdf-links, --restamp-keywords, "
                 "--restamp-headers, --restamp-abstracts, --restamp-vista-stub, "
                 "--clean-catalog-markup, "
                 "--migrate-disputes, --migrate-bearing, "
                 "--migrate-txt-fields, --migrate-vistas, --sync-mirror y --rename-paper)")

    if args.web:
        if args.pending and not str(args.pending_motivo or "").strip():
            ap.error("--pending exige --reason: sin el motivo la nota queda fuera del schema de #80 "
                     "y nadie sabe si alguien está consiguiendo la fuente o si nadie la miró nunca")
        write_web_paper_note(args.slug, url=args.url, slug=args.slug_hint, concept=args.concept,
                             title=args.title, first_author=args.author, year=args.year,
                             n_authors=args.n_authors, doi=args.doi, venue=args.venue,
                             accessed=args.accessed, pending=args.pending,
                             pending_motivo=args.pending_motivo, force=args.force)
        return 0

    cfg.print_seguro(f"Generando notas para {args.slug}")
    if args.theme:
        write_concept_note(args.slug, args.force)
    else:
        write_star_note(args.slug, args.force)
    write_paper_notes(args.slug, args.all, args.force, theme=args.theme)
    # Re-estampar DESPUÉS de crear las notas de paper: los roll-ups los estampa
    # `write_star_note`/`write_concept_note`, que corren ANTES, así que en una corrida limpia leían
    # un universo donde esas notas todavía no existían y la ficha quedaba diciendo «ninguna nota de
    # paper declara este sujeto todavía» sobre las N que sí. Correr el mismo comando otra vez lo
    # arreglaba: era puro orden. No era silencioso (el lint lo reportaba como backlog), y ése era el
    # problema — un hallazgo que aparece en TODA ingesta nueva es ruido fijo, y un chequeo que
    # siempre habla se deja de mirar. Es cirugía idempotente y barata: no toca la prosa.
    dest_final = _concept_dest(args.slug) if args.theme else (cfg.STARS / f"{args.slug}.md")
    if dest_final.exists():
        if args.theme:
            # #176: en un concepto el roll-up ES `stamp_concept_rollup` —la unión de `methods` y
            # `thesis_links` con la columna *Entró por* (D-24)—, no la tabla de estrella. Llamar a
            # `stamp_papers_table` acá no sólo era de más: su ancla `## Papers` es prefijo de la del
            # roll-up, así que se comía la sección y dejaba a `stamp_concept_rollup` sin dónde
            # escribir. La causa raíz la cerró `section_start`; esto saca la llamada que sobraba.
            stamp_concept_rollup(args.slug, dest_final)
        else:
            stamp_papers_table(args.slug, dest_final, "star")
            stamp_star_rollups(args.slug, dest_final)
    cfg.save_paso(args.slug, "make_notes", flags=_flags_usados(args, ap))
    return 0


if __name__ == "__main__":
    cfg.cli_exit(main)
