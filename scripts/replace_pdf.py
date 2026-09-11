#!/usr/bin/env python3
"""Replace a paper's PDF with another copy — the preprint by its published version (#436).

WHY IT EXISTS. `#298` is the largest backlog category of a real vault (161 of 264 paper notes: a
note whose bibcode is the published one while the PDF it reads is the preprint) and its `→` sent the
operator to `fetch_pdf.py <slug> --force`, which **does not apply to the normal case**: the
publisher's copy is behind a paywall and the user brings the file by hand. When the file arrives,
there was no command that installed it — measured replacing 11 preprints, the whole thing ran from a
scratch script that was never versioned, and three of the pieces it had to touch contradicted each
other:

1. the PDF lives under **every slug** that ingested the paper (`2010ApJ...722..937D` under `gj_581`
   AND `rv-doppler`), and nobody enumerated them;
2. re-extracting ONE `.txt` was impossible: `extract_fulltext.py` takes a **slug** and its
   `--force` re-extracts all of it, which expires the source anchors (D-20) of every paper in the
   theme — collateral damage on pairs nobody touched. That is why this needs `--bibcode` (#436);
3. the guard of `#383` (a changed `pdf_sha` nulls `pdf_source`/`eprint_version`) **cannot fire** on
   most of the vault: 247 notes have a PDF and only 25 have a `pdf_sha`, so on the other 222 the
   replacement is invisible and the note keeps saying `pdf_source: eprint` over a publisher's PDF.

⛔ **And the piece that did not exist anywhere: the EXTRACTION keeps the preprint's pages.**
`raw/extraccion/**` is versioned and not regenerable (#311), so after the replacement the vault
holds an extraction citing `p. 5` of a document that is no longer on disk while the new PDF
paginates by volume (Cardoso 1998 starts at 2009; Dawson 2010 at 937). The quoted text stays right —
`contrast --validar` gave **0 alterations** over the five notes touched — but **every locator is
wrong**, and nothing surfaced it. This stamps `_paginacion` on the extraction (metadata, the same
shape `sweep_external` uses for the ground-truth `_cambios`) and the lint reports it.

What it does NOT do, on purpose: it does not re-verify, it does not rewrite a locator, and it does
not touch the prose. It prints the re-verification scope and stops — 11 replacements expired **76**
pairs, ~7 per paper, and extrapolated to the 70 high-priority ones of that vault that is of the
order of **500** pairs. Deciding when to pay that is not this script's call.

    python scripts/replace_pdf.py <bibcode> <ruta.pdf> --source publisher --reason "<motivo>"
    python scripts/replace_pdf.py <bibcode> <ruta.pdf> --source publisher --reason "…" --dry-run
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

import lib_config as cfg
import lib_blocks as lb
import make_notes as mn


class ReplaceError(RuntimeError):
    """A refusal of this script: the replacement does not happen and nothing is written."""


def pdf_copies(bibcode: str) -> list:
    """Every copy of this paper's PDF on disk, one per slug that ingested it (#436).

    ⛔ The unit of the replacement is the PAPER and the unit of storage is the **slug**, so a
    replacement that writes one copy leaves the others reading the old document — and `pdf_slug`
    resolves only ONE (declared precedence, #305), which is right for reading and wrong for
    writing. Measured: 2 of the 11 papers replaced lived under two slugs each."""
    stem = cfg.note_stem(bibcode)
    return sorted(cfg.PDFS.glob(f"*/{stem}.pdf")) if cfg.PDFS.exists() else []


def first_pages_text(pdf: Path) -> str:
    """The text of the first pages of a PDF — enough for the arXiv stamp (INV-29).

    `pdftotext -f 1 -l 2`, the same two-page scope `cfg.arxiv_stamp` reads, because the stamp sits
    in the side margin of **every** page and reading further would pick up the `arXiv:` ids of the
    bibliography, which belong to other works. An empty string when `pdftotext` is missing or
    fails: *unknown*, never «there is no stamp»."""
    try:
        r = subprocess.run(["pdftotext", "-layout", "-f", "1", "-l", "2", str(pdf), "-"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def check_incoming(bibcode: str, nuevo: Path, source: str) -> list:
    """Refusals BEFORE touching anything: same file, wrong vocabulary, preprint sold as published.

    Three of them, and each one happened in the measured session:
    - the file handed over was **the same preprint** already on disk (equal sha: nothing to
      replace, and going ahead would expire 7 pairs for nothing);
    - `--source` outside the closed vocabulary (#296), which would fall through the `else` of
      every `== "eprint"` in silence;
    - the file carries the **arXiv stamp** in its margin and is being declared `publisher`/`ads`.
      That one is the whole point of `pdf_source` (#57): with `eprint`, a numeric discrepancy
      against a published value is a candidate version difference and the note is NOT «corrected»
      towards the preprint. A document that declares itself a preprint cannot be filed as the
      published one."""
    errores = []
    if not nuevo.exists():
        errores.append(f"{nuevo}: no existe")
        return errores
    if nuevo.read_bytes()[:4] != b"%PDF":
        errores.append(f"{nuevo}: no empieza con el magic `%PDF` — ¿es un PDF?")
        return errores
    if source not in cfg.PDF_SOURCE_OK:
        errores.append(f"`--source {source}` no está en el vocabulario cerrado (#296): "
                       f"{' | '.join(cfg.PDF_SOURCE_OK)}")
    sha_nuevo = lb.sha10(nuevo.read_bytes())
    iguales = [c for c in pdf_copies(bibcode) if lb.sha10(c.read_bytes()) == sha_nuevo]
    if iguales:
        errores.append(f"el archivo entrante es BYTE A BYTE el que ya está en "
                       f"`{iguales[0].parent.name}` (sha {sha_nuevo}): no hay nada que reemplazar, "
                       f"y hacerlo vencería los pares anclados a ese PDF por nada")
    marca = cfg.arxiv_stamp(first_pages_text(nuevo))
    if marca is not None and source in ("publisher", "ads"):
        version = f" {marca}" if marca else ""
        errores.append(f"el PDF entrante lleva la marca de arXiv{version} en el margen y se lo "
                       f"está declarando `{source}`: es un PREPRINT. Con `pdf_source: eprint` una "
                       f"discrepancia numérica es candidata a diferencia de versión (#57), así que "
                       f"archivarlo como publicado hace que la nota mande a re-verificar contra el "
                       f"documento equivocado")
    return errores


def page_warning(saliente: Path, entrante: Path) -> str | None:
    """A WARNING —never a refusal— when the incoming PDF has fewer pages than the one it replaces (#437).

    The one replacement that had to be REVERTED in the measured session passed both refusals: the
    *Science Express* copy of `2014Sci...345..440R` has **7 pages and no Supplementary Materials**,
    the arXiv preprint has **33**, and the note cites **§S1.1** — no arXiv stamp, different sha, and
    the replacement would have left the note citing a section the new document does not contain,
    with 9 expired pairs on top. `pdfinfo` says it for free, and it is the only one of the three
    signals that cannot be reconstructed afterwards: the outgoing PDF is on disk only now.

    ⚠ A warning, on purpose: a shorter publisher's copy can be legitimate (no cover letter, no
    duplicated appendices). Who decides is whoever looks. `None` when both counts are available
    and the incoming is not shorter; a *non-evaluable* line when either count is unknown (D-43:
    «no se pudo contar» is not «no es más corto»)."""
    n_out, why_out = cfg.pdf_page_count(saliente)
    n_in, why_in = cfg.pdf_page_count(entrante)
    if n_out is None or n_in is None:
        return (f"no se pudieron comparar las páginas ({why_out or why_in}): revisá a mano que "
                f"el entrante no pierda material (apéndices, Supplementary)")
    if n_in < n_out:
        return (f"el PDF entrante tiene {n_out - n_in} página(s) MENOS que el que reemplaza "
                f"({n_in} contra {n_out}): si la ficha cita apéndices o Supplementary Materials, "
                f"puede quedar citando una sección que el documento nuevo no contiene")
    return None


def reverification_scope(bibcode: str) -> list:
    """`[(nota, n_filas)]` — the verified pairs that cite this source, per note (#436/D-20).

    The source hash of every one of those rows was taken over the PDF that is being replaced, so
    replacing it expires them: they were verified against a file that no longer exists. This is the
    number that decides when to pay the round (76 pairs over 6 notes for 11 papers, measured), and
    it comes out ready for `verify_fanout --fuentes`."""
    out = []
    for base, patron in ((cfg.STARS, "*.md"), (cfg.CONCEPTS, "*/*.md"),
                         (cfg.QUERIES, "*.md"), (cfg.PAPERS, "*.md")):
        for nota in cfg.note_paths(base, patron):
            filas = lb.verif_rows(nota) or []
            n = sum(1 for f in filas if f.bibcode == bibcode)
            if n:
                out.append((nota, n))
    return sorted(out, key=lambda x: (-x[1], x[0].name))


def stamp_depagination(bibcode: str, sha_viejo: str, sha_nuevo: str, motivo: str,
                       dry_run: bool = False) -> list:
    """Mark every extraction of this bibcode as carrying the OLD document's locators (#436/#311).

    The extraction is versioned and not regenerable, so it is neither rewritten nor deleted: it gets
    `_paginacion` —the same shape `sweep_external` leaves as `_cambios` on the ground-truth JSON
    (AUD-42)— and the lint reports it as backlog. Without this the vault holds `p. 5` of a document
    it no longer has, and no layer looks at a locator: `verify-citations` checks that the source
    says it, `contrast --validar` that the string was not altered, and both are right while the page
    number points nowhere."""
    tocadas = []
    for f in sorted(cfg.EXTRACCION.glob(f"*/{cfg.note_stem(bibcode)}*.json")) \
            if cfg.EXTRACCION.exists() else []:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cfg.print_seguro(f"  ⚠ {f}: no se pudo leer como JSON — marcala a mano")
            continue
        if not isinstance(data, dict):
            continue
        data["_paginacion"] = {
            "reemplazo": _dt.date.today().isoformat(), "pdf_sha_anterior": sha_viejo,
            "pdf_sha": sha_nuevo, "motivo": motivo,
            "aviso": "los localizadores de esta extracción son del documento ANTERIOR: el PDF se "
                     "reemplazó y la paginación cambió (#436)"}
        if not dry_run:
            cfg.write_text_atomic(f, json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        tocadas.append(f)
    return tocadas


def replace(bibcode: str, nuevo: Path, source: str, reason: str,
            dry_run: bool = False) -> dict:
    """Install `nuevo` as this paper's PDF under every slug, and leave the trace (#436).

    Order matters and it is the issue's: refuse first, then copy, then re-extract only that `.txt`
    per slug, then the note (`pdf_sha`, `pdf_source`, `eprint_version: null`, and the signed
    `pdf_reemplazo`), then mark the extraction, then print the scope.

    ⚠ The trace goes in the PAPER's note and not in a subject's registro, which is where the issue
    put it: a PDF is shared by every slug that ingested it, so the registro would hold N copies of
    one fact and the registro is keyed by subject. The note is versioned, travels, and is the
    artefact that the consumer of the claim reads.

    ⛔ #437 — and it is WRITTEN, not just promised: `pdf_reemplazo: [{fecha, source, sha_anterior,
    sha, paginas, motivo}]`, add-only. The v1.256.0 docstring named that field and the code never
    wrote it —one occurrence in the whole repo, the promise— so the `--reason` survived only in
    `_paginacion` of the extraction and in stdout, and the note of the paper (what travels, what
    the consumer of the claim reads) did not say the PDF had been replaced nor why. That motive is
    exactly what was needed when a replacement had to be reverted."""
    errores = check_incoming(bibcode, nuevo, source)
    if errores:
        raise ReplaceError("\n".join(f"⛔ {e}" for e in errores))
    copias = pdf_copies(bibcode)
    if not copias:
        raise ReplaceError(f"⛔ no hay ningún PDF de {bibcode} en `vault/raw/pdfs/**` — esto "
                           f"REEMPLAZA una copia existente; para la primera, `fetch_pdf.py`")
    sha_viejo, sha_nuevo = lb.sha10(copias[0].read_bytes()), lb.sha10(nuevo.read_bytes())
    alcance = reverification_scope(bibcode)         # ANTES de tocar: las filas se leen igual, pero
    slugs = [c.parent.name for c in copias]         # el orden documenta que el número es el de antes
    # #437 — la comparación de páginas va ANTES de copiar, y por el mismo motivo que el alcance: el
    # PDF saliente está en disco sólo ahora, y es la única señal que no se reconstruye después.
    aviso_paginas = page_warning(copias[0], nuevo)
    paginas = (cfg.pdf_page_count(copias[0])[0], cfg.pdf_page_count(nuevo)[0])
    for c in copias:
        cfg.print_seguro(f"  {'(dry-run) ' if dry_run else ''}→ {c}")
        if not dry_run:
            # ⛔ ATÓMICA (INV-90): un corte en medio de un `shutil.copy2` al destino final deja un
            # PDF truncado que `if dest.exists()` da por bajado para siempre — el modo de falla
            # que H-07 cerró, y acá el destino es un artefacto de `raw/` que viaja en git-lfs.
            cfg.copy_file_atomic(nuevo, c)
    txts = []
    for slug in slugs:
        txt = cfg.FULLTEXT / slug / f"{cfg.note_stem(bibcode)}.txt"
        if not txt.exists():
            continue
        txts.append(txt)
        if not dry_run:
            # ⛔ acotado al bibcode (#436): `--force` sobre el slug entero vencería las anclas de
            # fuente de TODOS los papers del tema. Y sí hay que re-extraer: el `.txt` es el índice
            # de búsqueda del corpus y quedó describiendo otro documento.
            subprocess.run([sys.executable, str(Path(__file__).with_name("extract_fulltext.py")),
                            slug, "--bibcode", cfg.note_stem(bibcode), "--force"], check=False)
    nota = cfg.PAPERS / f"{cfg.note_stem(bibcode)}.md"
    if nota.exists() and not dry_run:
        cfg.set_fm_scalar(nota, "pdf_sha", sha_nuevo)
        cfg.set_fm_scalar(nota, "pdf_source", source)
        # #383 bloquea `pdf_source` de editor con `eprint_version`: el valor viejo describía el
        # documento que acabamos de sacar de disco.
        if source != "eprint":
            cfg.set_fm_scalar(nota, "eprint_version", "null", crear=False)
        # #437 — el rastro FIRMADO, add-only: la historia de reemplazos de este PDF, en la nota que
        # viaja. Se escribe con el mismo escritor de listas de mapas que usa el resto del framework.
        previos = cfg.as_list((cfg.split_fm(nota.read_text(encoding="utf-8")) or {})
                              .get("pdf_reemplazo"))
        mn._set_lista_de_mapas(nota, "pdf_reemplazo", [x for x in previos if isinstance(x, dict)] + [
            {"fecha": _dt.date.today().isoformat(), "source": source,
             "sha_anterior": sha_viejo, "sha": sha_nuevo,
             "paginas": f"{paginas[0] if paginas[0] is not None else '?'} → "
                        f"{paginas[1] if paginas[1] is not None else '?'}",
             "motivo": reason}])
    elif not nota.exists():
        cfg.print_seguro(f"  ⚠ no hay nota `{nota.name}`: el PDF se reemplazó y el frontmatter no "
                         f"se pudo estampar (¿`make_notes.py` todavía no la creó?)")
    extracciones = stamp_depagination(bibcode, sha_viejo, sha_nuevo, reason, dry_run=dry_run)
    return {"bibcode": bibcode, "slugs": slugs, "sha_anterior": sha_viejo, "sha": sha_nuevo,
            "txts": [str(t) for t in txts], "extracciones": [str(e) for e in extracciones],
            "alcance": [(str(n), k) for n, k in alcance], "pares": sum(k for _n, k in alcance),
            "aviso_paginas": aviso_paginas, "paginas": paginas}


def print_report(r: dict, source: str, reason: str) -> None:
    """What the operator has to do next, with the numbers that decide whether to do it now."""
    cfg.print_seguro(
        f"\n{r['bibcode']}: PDF reemplazado en {len(r['slugs'])} slug(s) "
        f"({', '.join(r['slugs'])}) · sha {r['sha_anterior']} → {r['sha']} · "
        f"`pdf_source: {source}`")
    if r.get("aviso_paginas"):
        cfg.print_seguro(f"  ⚠ PÁGINAS: {r['aviso_paginas']} (#437)")
    cfg.print_seguro(f"  · `.txt` re-extraídos: {len(r['txts'])} (acotado al bibcode, #436)")
    cfg.print_seguro(f"  · extracciones marcadas `_paginacion`: {len(r['extracciones'])} — sus "
                     f"localizadores son del documento ANTERIOR (#311: no se reescriben)")
    cfg.print_seguro(f"\n  ⚠ ALCANCE DE LA RE-VERIFICACIÓN: {r['pares']} par(es) en "
                     f"{len(r['alcance'])} nota(s) se verificaron contra el PDF que se acaba de "
                     f"reemplazar (D-20). Listo para pegar:")
    for nota, n in r["alcance"]:
        cfg.print_seguro(f"      python scripts/verify_fanout.py {nota} "
                         f"--fuentes {r['bibcode']}    # {n} par(es)")
    if not r["alcance"]:
        cfg.print_seguro("      (ninguno: ninguna nota verificada cita esta fuente)")
    cfg.print_seguro(f"\n  → anotá el reemplazo en `vault/wiki/log.md` con su motivo "
                     f"(«{reason}») y commiteá `raw/` junto con las notas: el PDF viaja por "
                     f"git-lfs y la extracción marcada es versionada.")


def main(argv=()) -> int:
    """CLI. Refusals come back as exit 2 with their reason; nothing is written on a refusal."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bibcode")
    ap.add_argument("pdf", help="el archivo entrante (el que trajo el usuario)")
    ap.add_argument("--source", required=True, metavar="|".join(cfg.PDF_SOURCE_OK),
                    help="procedencia del documento NUEVO (vocabulario cerrado, #296). ⛔ Se "
                         "rehúsa `publisher`/`ads` sobre un PDF que lleva la marca de arXiv.")
    ap.add_argument("--reason", required=True,
                    help="por qué se reemplaza — viaja a la marca `_paginacion` de la extracción "
                         "y al reporte (mismo criterio que el `--reason` del triage)")
    ap.add_argument("--dry-run", action="store_true",
                    help="mostrar qué se tocaría (incluido el alcance de re-verificación) sin "
                         "escribir nada")
    args = ap.parse_args(list(argv))
    try:
        r = replace(args.bibcode, Path(args.pdf), args.source, args.reason, dry_run=args.dry_run)
    except ReplaceError as e:
        cfg.print_seguro(str(e))
        return 2
    print_report(r, args.source, args.reason)
    return 0


if __name__ == "__main__":
    cfg.stdout_tolerante()
    cfg.cli_exit(lambda: main(sys.argv[1:]))
