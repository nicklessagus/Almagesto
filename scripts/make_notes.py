"""Genera notas markdown de la bóveda a partir de lo bajado por los otros scripts.

Uso:
    python make_notes.py <slug> [--all] [--force]

- stars/<slug>.md  : ficha índice de la estrella (frontmatter máquina-legible + Dataview).
- papers/<bibcode>.md : una nota por paper relevante (metadata + abstract + placeholders LLM).

Idempotente: NO pisa notas existentes (protege la extracción LLM) salvo --force. Única
excepción (add-only, no destructiva): en una nota de paper que ya existía, mergea los seeds
del ingest actual (`stars` / `thesis_links`) si faltan — retro-linkeo, ver merge_frontmatter_list.
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
        motivo = "sin tópico" if not r.get("topics") else f"doctype: {r.get('doctype')}"
        rows.append(f"| [{title}]({url}) | {r.get('year') or ''} | {r.get('citation_count') or 0} | {motivo} |")
    extra = len(out) - len(rows)
    tail = f"\n\n_(+ {extra} más excluidos por el filtro)_" if extra > 0 else ""
    return ("\n## Excluidos por el filtro (no-core · snapshot del ingest)\n"
            "> Top por citas de lo que el clasificador dejó afuera (no matchea `relevance.topics` o "
            "doctype ruido). **No se bajan ni se fichan** — esto es un puntero por las dudas. Si ves un "
            "falso negativo, ajustá `relevance.topics` y re-ingestá con `--force`.\n\n"
            "| Paper | Año | Citas | Motivo |\n|---|---|---|---|\n"
            + "\n".join(rows) + tail + "\n")


def write_star_note(slug: str, force: bool) -> None:
    name, meta = cfg.star_by_slug(slug)
    dest = cfg.STARS / f"{slug}.md"
    if dest.exists() and not force:
        print(f"  star: {dest.name} ya existe (usa --force para regenerar)")
        return
    gt_file = cfg.GROUND_TRUTH / f"{slug}.json"
    gt = json.loads(gt_file.read_text(encoding="utf-8")) if gt_file.exists() else {"host": {}, "planets": []}
    host = gt.get("host", {})
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
        "P_rot_days": host.get("st_rotp_days"),      # llenar con literatura si falta
        "activity_indicators_expected": [],           # poblar con extracción LLM
        "planets": planets,
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
> ⚠ **Capa LLM — revisar antes de citar.** El ground-truth del frontmatter (NEA/SIMBAD) es auditable, pero
> la prosa (Resumen, Huecos, extracción) la sintetizó un LLM desde las fuentes: trazable por `[[bibcode]]` y
> chequeable con `verify-citations`, que es **juicio de LLM, no prueba**. Verificá contra la fuente antes de
> llevar un dato a un paper/tesis.
>
> _Generado con Almagesto v{cfg.ALMAGESTO_VERSION}._

## Resumen
_(síntesis por LLM: qué se sabe, qué indicadores deberían correlacionar con actividad para este
tipo espectral, planetas confirmados/dudosos)._

## Huecos
_(qué falta para que la ficha alcance sola: parámetros sin valor (¿`P_rot`?), señales RV sin árbitro,
indicadores esperados no medidos, métodos no aplicados. Lista corta y accionable — abrir queries para imputar.)_

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
    dest.write_text(body, encoding="utf-8")
    print(f"  star: {dest.name} escrito")


def write_concept_note(slug: str, force: bool) -> None:
    """Para temas (ingest-topic): stub del concept durable destino. Idempotente: NO pisa la
    síntesis LLM de un concept ya existente salvo --force (protege la síntesis)."""
    _, meta = cfg.topic_by_slug(slug)
    area, concept = meta["area"], meta["concept"]
    # Las áreas de concepts/ son ABIERTAS: no se prohíbe ninguna (podés investigar cualquier tema).
    # `concept_areas` (objective.yaml) es sólo una REFERENCIA para distinguir un typo de un área nueva
    # legítima → si el área no está declarada, AVISAR (nunca bloquear) para que un typo no pase mudo.
    # El lint la marca después; si era un área nueva real, agregala a concept_areas para silenciar el aviso.
    if area not in cfg.load_concept_areas():
        print(f"  ⚠ área '{area}' (topic '{slug}') no está en concept_areas (objective.yaml). "
              f"Si es un typo, corregí topics.yaml; si es un área nueva, agregala a la lista. Creo igual.")
    dest = cfg.CONCEPTS / area / f"{concept}.md"
    if dest.exists() and not force:
        print(f"  concept: {area}/{concept}.md ya existe (no se pisa sin --force; los papers enganchan por thesis_links)")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    front = {"name": meta.get("title", concept)}
    if area == "hypotheses":          # `status` sólo en hipótesis (schema name,status; ver CLAUDE.md)
        front["status"] = "active"
    front.update({
        "aliases": meta.get("aliases", []),   # sinónimos EN+ES para grep; sembrado del topic, el LLM enriquece
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
> ⚠ **Capa LLM — revisar antes de citar.** La síntesis la compiló un LLM desde los papers citados:
> chequeable con `verify-citations`, que es **juicio de LLM, no prueba**. Verificá contra la fuente antes
> de llevar un dato a un paper/tesis.
>
> _Generado con Almagesto v{cfg.ALMAGESTO_VERSION}._

## Síntesis
_(qué se sabe del tema: mecanismos, signos, desfasajes, regímenes)._

## Huecos
_(qué falta para entender/implementar el tema sin abrir papers: pasos o ecuaciones faltantes,
regímenes no cubiertos, contradicciones sin resolver.)_

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
    written = skipped = merged = 0
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
            continue
        authors = r.get("authors", [])
        pdf_rel = f"../../raw/pdfs/{slug}/{safe_name(bib)}.pdf" if r.get("arxiv_id") else None
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
            "relevance": "high" if r.get("relevant") else "low",
            "citation_count": r.get("citation_count", 0),
            "pdf": pdf_rel,
            "confidence": "medium",      # patrón LLM Wiki
            "tags": ["paper"],
            "generator": f"Almagesto v{cfg.ALMAGESTO_VERSION}",   # provenance (con qué versión se armó)
        }
        abstract = (r.get("abstract") or "").strip()
        body = f"""{fm(front)}
# {r.get('title')}

**{', '.join(authors[:6])}{' et al.' if len(authors) > 6 else ''}** ({r.get('year')})
· [[{link}]] · ADS: `{bib}`{' · arXiv: ' + r['arxiv_id'] if r.get('arxiv_id') else ''}

## Abstract
{abstract or '_(no disponible)_'}

## Extracción (LLM)
- **Planetas / parámetros:** _(P, K, e por planeta; comparar contra ground-truth)_
- **Actividad / indicadores:** _(qué indicadores se usaron y qué correlaciones se reportan)_
- **Métodos:** _(llenar `methods:` del frontmatter con `concepts/methods/`)_
- **Para mi objetivo:** _(relevancia para el objetivo de la bóveda / huecos)_
"""
        dest.write_text(body, encoding="utf-8")
        written += 1
    print(f"  papers: {written} escritos, {skipped} ya existían"
          + (f", {merged} retro-linkeados (seeds add-only)" if merged else ""))


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
    snapshot (la pasa fetch_web.py; si es web y no se pasó, default = hoy UTC). El tag distingue el
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
        # (edición quirúrgica del flag; la extracción LLM no se toca).
        if not pending and unpend_note(dest, citekey, slug):
            return False
        print(f"  papers: {dest.name} ya existe (no se pisa sin --force)")
        return False
    bibstem = venue or (urlparse(url).netloc if url else None)   # venue: dominio web por default
    if accessed is None and url and not pending:                 # fuente web sin fecha explícita → hoy
        accessed = datetime.now(timezone.utc).strftime("%Y-%m-%d")   # (pending: sin snapshot → null)
    # PDF↔disco: si el PDF off-ADS ya está copiado a raw/pdfs/<slug>/, linkearlo (verdad de disco)
    pdf_rel = None
    if slug and (cfg.PDFS / slug / f"{safe_name(citekey)}.pdf").exists():
        pdf_rel = f"../../raw/pdfs/{slug}/{safe_name(citekey)}.pdf"
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
        "relevance": "high",
        "citation_count": 0,
        "pdf": pdf_rel,                      # off-ADS: null salvo PDF local ya copiado a raw/pdfs/<slug>/
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
    body = f"""{fm(front)}
# {title or citekey}

**{first_author or '(autor desconocido)'}** ({year or 's.f.'})
· {'[[' + concept + ']] · ' if concept else ''}fuente off-ADS · `{citekey}`
{src_line}{acc_line}
> Fuente **off-ADS** (fuera de ADS). El respaldo citable es el snapshot determinista
> `{txt_ptr}` (`source_url` + `accessed` en el frontmatter), verificable por `verify-citations`.
> El frontmatter es máquina-legible como en cualquier nota de paper.
{pend_line}
## Extracción (LLM)
- **Aporte al tema:** _(qué agrega al eje del concept: definición, ecuación, método, signo, régimen)_
- **Métodos:** _(llenar `methods:` del frontmatter con `concepts/methods/`)_
- **Para mi objetivo:** _(relevancia para el objetivo de la bóveda / huecos)_
"""
    dest.write_text(body, encoding="utf-8")
    print(f"  papers: {dest.name} escrito (stub off-ADS)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="slug de estrella/tema; en --web es la CLAVE de cita (AAAA+Autor)")
    ap.add_argument("--all", action="store_true", help="incluir papers no-relevantes")
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
    ap.add_argument("--pending", choices=["paywall", "scan", "unextractable"],
                    help="(--web) fuente aún no conseguible: estampa pending_source y deriva al usuario")
    args = ap.parse_args()

    if args.web:
        write_web_paper_note(args.slug, url=args.url, slug=args.slug_hint, concept=args.concept,
                             title=args.title, first_author=args.author, year=args.year,
                             n_authors=args.n_authors, doi=args.doi,
                             venue=args.venue, pending=args.pending, force=args.force)
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
