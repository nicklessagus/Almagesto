"""Cross what a `sources:` item DECLARES against what its DOI or its PDF says (#353).

An off-ADS source declares its metadata by hand (`title`/`author`/`year`) and nothing checked it:
measured in a real vault, a note published the author and title of ANOTHER paper — the synthetic
key, `first_author`, `title` and even the `motivo` in `themes.yaml` were all derived from the PDF's
FILE NAME (`RAICAR-N.pdf`), not from the document, whose first page names the real authors. Only
the `doi` and the PDF were right. It survived because the paper was never read (`sin vista`); the
first view would have propagated the false attribution into prose. Rule of method 4: a map that
attributes wrongly is worse than an empty one.

Two evidence rails, both already at hand:
- **`doi`** → Crossref (the same call `check_retractions` makes): first author, year, title.
- **no `doi` but a PDF** → its FIRST PAGE via `pdftotext -f 1 -l 1`: author surname and year must
  appear there (title is not judged from a page: too many layout artefacts).
Neither → `no-evaluable`, with the reason (D-43): never green.

It REPORTS and never rewrites `sources:` (curated, versioned config — same doctrine as
`triage --accept-source`). The verdict is PERSISTED in the versioned registry
(`fuentes_chequeadas`) together with a snapshot of what was declared, so the lint —offline by
contract— can report it: `autor`/`anio` block (a published false attribution), `titulo` and
`no-evaluable` are backlog, and a source whose declaration changed since the check counts as
unchecked. `ingest_theme` runs it at declare time; `python scripts/check_sources.py <slug>` runs
it on demand (`--dry-run` measures without writing).
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import lib_config as cfg
import check_retractions as cr

VEREDICTOS = ("ok", "autor", "anio", "titulo", "no-evaluable")
_SPLIT_AUTHORS = re.compile(r",|&|;|\band\b|\bet al\b|\by\b", re.I)


def norm(s) -> str:
    """Comparison form: accents stripped, casefolded, non-alphanumerics collapsed to one space.

    Combining marks AND standalone modifier symbols go: `pdftotext` renders «Hyvärinen» as
    `Hyv¨arinen` (a bare diaeresis before the vowel), measured on 6 of 7 first pages of one
    author, and the surname was reported missing from every one of them."""
    t = "".join(ch for ch in str(s or "") if unicodedata.category(ch) != "Sk")   # `¨` suelto
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = t.encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t.casefold()).split())


def declared_family(author) -> str:
    """The first author's SURNAME from a hand-written `author` field, normalised. Accepts
    `Hyvärinen, A.`, `Pendse et al.`, `Rasmussen & Williams`, `Gautam V. Pendse`."""
    chunk = _SPLIT_AUTHORS.split(str(author or ""), 1)[0].strip()
    tokens = [t for t in chunk.split() if not t.endswith(".")] or chunk.split()
    return norm(tokens[-1]) if tokens else ""


def declared_of(item: dict) -> dict:
    """The snapshot of what the item declares — what the verdict was computed against."""
    return {"author": str(item.get("author") or "").strip(),
            "year": _year(item.get("year")),
            "title": str(item.get("title") or "").strip()}


def _year(v) -> int | None:
    """Four-digit year inside a hand-written value (`2011`, `"2011a"`, `2011-12-12`), or `None`."""
    m = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", str(v or ""))
    return int(m.group(1)) if m else None


def crossref_meta(msg: dict) -> dict:
    """`{family, year, title}` from a Crossref `message` (double derived from a real response)."""
    autores = [cfg.as_map(a) for a in cfg.as_list(msg.get("author"))]
    primero = next((a for a in autores if str(a.get("sequence") or "") == "first"),
                   autores[0] if autores else {})
    partes = cfg.as_list(cfg.as_map(msg.get("issued")).get("date-parts"))
    year = None
    if partes and cfg.as_list(partes[0]):
        year = _year(cfg.as_list(partes[0])[0])
    titulo = cfg.as_list(msg.get("title"))
    return {"family": str(primero.get("family") or ""), "year": year,
            "title": str(titulo[0]) if titulo else ""}


def compare_crossref(declared: dict, found: dict) -> tuple[str, str]:
    """Verdict of declared-vs-Crossref. Author and year are decidable and block; the title is
    compared normalised and is backlog (punctuation and case vary legitimately)."""
    if not found.get("family") and not found.get("year"):
        return "no-evaluable", "Crossref no trae autor ni año para ese DOI"
    fam_d, fam_f = declared_family(declared.get("author")), norm(found.get("family"))
    if fam_d and fam_f and fam_d != fam_f:
        return "autor", f"declarado «{declared['author']}», Crossref dice «{found['family']}»"
    if declared.get("year") and found.get("year") and declared["year"] != found["year"]:
        return "anio", f"declarado {declared['year']}, Crossref dice {found['year']}"
    if declared.get("title") and found.get("title") and norm(declared["title"]) != norm(found["title"]):
        return "titulo", f"declarado «{declared['title']}», Crossref dice «{found['title']}»"
    return "ok", ""


def compare_pdf(declared: dict, page: str) -> tuple[str, str]:
    """Verdict of declared-vs-first-page: the surname and the year must be ON that page."""
    texto = norm(page)
    if not texto.strip():
        return "no-evaluable", "la primera página del PDF no tiene texto (¿escaneo sin OCR?)"
    fam = declared_family(declared.get("author"))
    if fam and not re.search(rf"\b{re.escape(fam)}\b", texto):
        return "autor", f"declarado «{declared['author']}» y el apellido no está en la primera página del PDF"
    if declared.get("year") and not re.search(rf"\b{declared['year']}\b", texto):
        return "anio", f"declarado {declared['year']} y ese año no aparece en la primera página del PDF"
    if not fam and not declared.get("year"):
        return "no-evaluable", "el item no declara `author` ni `year`: no hay nada que cruzar"
    return "ok", ""


def pdf_first_page(pdf: Path) -> str | None:
    """Text of page 1 via `pdftotext -f 1 -l 1`; `None` when the tool or the file is missing."""
    if shutil.which("pdftotext") is None or not pdf.is_file():
        return None
    r = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(pdf), "-"],
                       capture_output=True, text=True, errors="replace")
    return r.stdout if r.returncode == 0 else None


def resolve_pdf_path(item: dict, slug: str) -> Path | None:
    """The vault copy first (`raw/pdfs/<slug>/<key>.pdf`), else the declared `pdf:` path."""
    key = str(item.get("key") or "").strip()
    copia = cfg.PDFS / slug / f"{key.replace('/', '_')}.pdf"
    if copia.is_file():
        return copia
    decl = str(item.get("pdf") or "").strip()
    if not decl:
        return None
    p = Path(decl).expanduser()
    return p if p.is_absolute() else cfg.ROOT / p


def check_item(item: dict, slug: str) -> dict:
    """One item → its record: `{key, fecha, via, doi, declarado, encontrado, veredicto, detalle}`."""
    key = str(item.get("key") or "").strip()
    declared = declared_of(item)
    rec = {"key": key, "fecha": dt.date.today().isoformat(), "doi": item.get("doi") or None,
           "declarado": declared, "encontrado": {}, "via": None}
    doi = str(item.get("doi") or "").strip()
    sin_crossref = ""
    if doi:
        msg, estado = cr.crossref_message(doi, cr._ua())
        if msg is not None:
            rec["via"] = "crossref"
            found = crossref_meta(msg)
            rec["encontrado"] = found
            rec["veredicto"], rec["detalle"] = compare_crossref(declared, found)
            return rec
        # Measured: 5 of 32 DOIs in one vault are `10.48550/arXiv.*`, which Crossref does not
        # register — so the PDF rail is the fallback, not a dead end.
        sin_crossref = f"Crossref: {estado} para {doi}; "
    pdf = resolve_pdf_path(item, slug)
    page = pdf_first_page(pdf) if pdf else None
    rec["via"] = "pdf"
    if page is None:
        rec.update(veredicto="no-evaluable",
                   detalle=sin_crossref
                   + ("sin PDF legible en disco" if pdf is None or not pdf.is_file()
                      else "`pdftotext` no está o falló") + " — no hay contra qué cruzar")
        return rec
    rec["encontrado"] = {"primera_pagina": " ".join(page.split())[:200]}
    rec["veredicto"], rec["detalle"] = compare_pdf(declared, page)
    return rec


def run(slug: str, dry_run: bool = False) -> dict:
    """Check every `sources:` item of `slug`; persist to the registry unless `dry_run`."""
    _, meta = cfg.theme_by_slug(slug)
    items = [s for s in cfg.as_list(meta.get("sources")) if isinstance(s, dict) and s.get("key")]
    records = {}
    for it in items:
        r = check_item(it, slug)
        records[r["key"]] = r
        marca = {"ok": "✓", "no-evaluable": "?"}.get(r["veredicto"], "⛔" if r["veredicto"] in ("autor", "anio") else "⚠")
        cfg.print_seguro(f"  {marca} {r['key']} [{r['via']}] {r['veredicto']}"
                         + (f": {r['detalle']}" if r["detalle"] else ""))
    n = {v: sum(1 for r in records.values() if r["veredicto"] == v) for v in VEREDICTOS}
    cfg.print_seguro(f"check_sources `{slug}`: {len(records)} fuente(s) — "
                     + " · ".join(f"{k} {v}" for k, v in n.items() if v)
                     + (" (dry-run: el registro NO se escribe)" if dry_run else ""))
    if not dry_run and records:
        data = cfg.load_registro(slug)
        data.setdefault("slug", slug)
        prev = cfg.as_map(data.get("fuentes_chequeadas"))
        prev.update(records)
        data["fuentes_chequeadas"] = prev
        cfg.save_registro(slug, data)
        cfg.print_seguro(f"  → registrado en {cfg.registro_path(slug)} (`fuentes_chequeadas`)")
    return records


def main(argv=None) -> int:
    """CLI: `check_sources.py <slug> [--dry-run]` — cross every declared source of one theme."""
    cfg.stdout_tolerante()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slug")
    ap.add_argument("--dry-run", action="store_true", help="mide y no escribe el registro")
    args = ap.parse_args(argv)
    run(args.slug, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    cfg.cli_exit(main)
