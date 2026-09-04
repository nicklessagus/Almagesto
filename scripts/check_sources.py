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
    t = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", t)          # `Herrero1`: el superindice de afiliacion
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t.casefold()).split())


def family_match(declared_author, found_family) -> bool:
    """Does the declared author name the same surname Crossref/the page gives? Compound surnames
    (`Le Bihan`, `van der Baan`, `Gomez-Herrero`) compare with spaces collapsed, and a declared
    LAST token (`Bihan`) matches a compound found surname: the last token alone was blocking
    correct entries (measured by the instance with the module, not among its 52 sources)."""
    nd, nf = norm(declared_family(declared_author)), norm(found_family)
    nd_full = norm(_SPLIT_AUTHORS.split(str(declared_author or ""), maxsplit=1)[0])
    if not nd or not nf:
        return False
    return nd == nf or nd_full.replace(" ", "") == nf.replace(" ", "") or nd == nf.split()[-1]


def declared_family(author) -> str:
    """The first author's SURNAME from a hand-written `author` field, normalised. Accepts
    `Hyvärinen, A.`, `Pendse et al.`, `Rasmussen & Williams`, `Gautam V. Pendse`."""
    chunk = _SPLIT_AUTHORS.split(str(author or ""), maxsplit=1)[0].strip()
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


def compare_crossref(declared: dict, found: dict, fuente: str = "Crossref") -> tuple[str, str]:
    """Verdict of declared-vs-a-structured-record (Crossref, or the user's `.bib`, #392). Author
    and year are decidable and block; the title is compared normalised and is backlog
    (punctuation and case vary legitimately)."""
    if not found.get("family") and not found.get("year"):
        return "no-evaluable", f"{fuente} no trae autor ni año para esta fuente"
    if declared.get("author") and found.get("family") and not family_match(declared["author"], found["family"]):
        return "autor", f"declarado «{declared['author']}», {fuente} dice «{found['family']}»"
    if declared.get("year") and found.get("year") and declared["year"] != found["year"]:
        return "anio", f"declarado {declared['year']}, {fuente} dice {found['year']}"
    if declared.get("title") and found.get("title") and norm(declared["title"]) != norm(found["title"]):
        return "titulo", f"declarado «{declared['title']}», {fuente} dice «{found['title']}»"
    return "ok", ""


# ── the user's own `.bib` next to the PDFs (#392, point 3) ──────────────────────────────────────
_BIB_ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.S)
_BIB_FIELD = re.compile(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)", re.S)


_TEX_ACCENT_BRACED = re.compile(r"\{\\[\"'`^~=.uvHrcdb]\s*([A-Za-z])\}")      # {\"a}
_TEX_ACCENT = re.compile(r"\\[\"'`^~=.uvHrcdb]\s*\{?\s*([A-Za-z])\s*\}?")   # \"a · \"{a}


def _untex(v: str) -> str:
    """Fold TeX accent commands (`Hyv{\\"a}rinen`, `Mars, J\\'er\\^ome`) to the bare letter: the
    comparison strips accents anyway, and the detail line should not print them raw."""
    return _TEX_ACCENT.sub(r"\1", _TEX_ACCENT_BRACED.sub(r"\1", v))


def bib_entries(path: Path) -> list:
    """Entries of a BibTeX file as `{tipo, clave, <fields lowercased>}`; braces/quotes stripped,
    one level of nested braces tolerated. Small on purpose (no dependency): the fields this rail
    reads are `author`, `year`, `title`, `doi`, `file`."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for m in _BIB_ENTRY.finditer(text):
        ini = m.end()
        fin = text.find("\n@", ini)
        cuerpo = text[ini:fin if fin > 0 else len(text)]
        campos = {"tipo": m.group(1).lower(), "clave": m.group(2)}
        for f in _BIB_FIELD.finditer(cuerpo):
            v = f.group(2).strip().strip(",").strip()
            if v[:1] in "{\"":
                v = v[1:-1]
            campos[f.group(1).lower()] = " ".join(_untex(v).replace("{", "").replace("}", "").split())
        out.append(campos)
    return out


def bib_meta(entry: dict) -> dict:
    """`{family, year, title}` from a `.bib` entry: the first author's surname (`Last, First and
    …` or `First Last and …`), the four-digit year, the title without braces."""
    primero = re.split(r"\s+and\s+", str(entry.get("author") or ""), maxsplit=1)[0].strip()
    family = primero.split(",")[0].strip() if "," in primero else (primero.split() or [""])[-1]
    return {"family": family, "year": _year(entry.get("year")), "title": str(entry.get("title") or "")}


def bib_match(item: dict, entries: list) -> dict | None:
    """The `.bib` entry for this `sources:` item: by DOI, else by the PDF's file name inside the
    entry's `file` field, else by normalised title. Never by author (that is what is being checked)."""
    doi = str(item.get("doi") or "").strip().casefold()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    if doi:
        for e in entries:
            if re.sub(r"^https?://(dx\.)?doi\.org/", "", str(e.get("doi") or "").strip().casefold()) == doi:
                return e
    nombre = Path(str(item.get("pdf") or "")).name
    if nombre:
        for e in entries:
            if nombre in str(e.get("file") or ""):
                return e
    titulo = norm(item.get("title"))
    if titulo:
        for e in entries:
            if norm(e.get("title")) == titulo:
                return e
    return None


def bib_files_near(item: dict) -> list:
    """`*.bib` in the directory of the DECLARED `pdf:` path (the user's library, not the vault
    copy): that is where the spreadsheet with the four right answers was sitting (#392)."""
    decl = str(item.get("pdf") or "").strip()
    if not decl:
        return []
    p = Path(decl).expanduser()
    d = (p if p.is_absolute() else cfg.ROOT / p).parent
    return sorted(d.glob("*.bib")) if d.is_dir() else []


def web_snapshot(item: dict, slug: str) -> str | None:
    """Body of the web snapshot `fetch_web` wrote for a `url:` source, or `None` (#392, point 4)."""
    key = str(item.get("key") or "").strip()
    f = cfg.FULLTEXT / slug / f"{key.replace('/', '_')}.txt"
    if not key or not f.is_file():
        return None
    text = f.read_text(encoding="utf-8", errors="replace")
    if cfg.FULLTEXT_WEB_MARK not in text.split("\n", 1)[0]:
        return None
    marca = "# ---- contenido extraído (defuddle) ----"
    i = text.find(marca)
    return text[i + len(marca):] if i >= 0 else text


def compare_pdf(declared: dict, page: str, donde: str = "la primera página del PDF") -> tuple[str, str]:
    """Verdict of declared-vs-a-page of text (PDF first page, or the head of a web snapshot): the
    surname and the year must be ON it. Weak evidence: never blocks (see the lint)."""
    texto = norm(page)
    if not texto.strip():
        return "no-evaluable", f"{donde} no tiene texto (¿escaneo sin OCR?)"
    import extract_fulltext
    ok, motivo = extract_fulltext.is_legible(page)
    if not ok:
        # Measured on the instance: four PDFs of one author render as glyphs (fonts without
        # ToUnicode) and the rail said «the surname is missing». Illegible is not evaluable.
        return "no-evaluable", f"{donde} ilegible ({motivo}) — abrila a ojo"
    fam = declared_family(declared.get("author"))
    fam_full = norm(_SPLIT_AUTHORS.split(str(declared.get("author") or ""), maxsplit=1)[0]).replace(" ", "")
    if fam and not re.search(rf"\b{re.escape(fam)}\b", texto) and fam_full not in texto.replace(" ", ""):
        return "autor", f"declarado «{declared['author']}» y el apellido no está en {donde}"
    if declared.get("year") and not re.search(rf"\b{declared['year']}\b", texto):
        return "anio", f"declarado {declared['year']} y ese año no aparece en {donde}"
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
    # #392 (3): the user's own `.bib` next to the PDFs — structured, offline, and in the measured
    # case it held the four right answers nobody consulted. Same comparison as Crossref.
    for bib in bib_files_near(item):
        e = bib_match(item, bib_entries(bib))
        if e is not None:
            rec["via"] = "bib"
            rec["encontrado"] = {**bib_meta(e), "bib": bib.name, "clave": e.get("clave")}
            rec["veredicto"], rec["detalle"] = compare_crossref(declared, bib_meta(e), fuente=f"`{bib.name}`")
            return rec
    pdf = resolve_pdf_path(item, slug)
    page = pdf_first_page(pdf) if pdf else None
    rec["via"] = "pdf"
    if page is None:
        # #392 (4): a `url:` source has no PDF; the head of the snapshot `fetch_web` wrote is the
        # page to look at (defuddle puts the page title first). Weak evidence, like the PDF rail.
        cuerpo = web_snapshot(item, slug)
        if cuerpo is not None:
            rec["via"] = "web"
            rec["encontrado"] = {"snapshot": " ".join(cuerpo.split())[:200]}
            rec["veredicto"], rec["detalle"] = compare_pdf(declared, "\n".join(cuerpo.split("\n")[:60]),
                                                           donde="el arranque del snapshot web")
            return rec
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
