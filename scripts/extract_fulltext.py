"""Convierte los PDFs de una estrella a texto plano para búsqueda local y re-extracción.

Uso:
    python extract_fulltext.py <slug> [--force]

pdfs/<slug>/<bibcode>.pdf  →  fulltext/<slug>/<bibcode>.txt

El .txt se commitea (es liviano, greppable y permite `git grep` sobre todo el corpus, además
de re-preguntar al corpus cuando cambia el pipeline sin re-parsear el PDF). Requiere `pdftotext`
(poppler-utils). Idempotente: no re-extrae salvo --force.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

import lib_config as cfg

FULLTEXT = cfg.FULLTEXT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if shutil.which("pdftotext") is None:
        sys.exit(
            "Falta `pdftotext` (paquete poppler), necesario para extraer texto de los PDFs:\n"
            "  Debian/Ubuntu: sudo apt install poppler-utils   ·  macOS: brew install poppler\n"
            "  Fedora: sudo dnf install poppler-utils           ·  Windows: conda install -c conda-forge poppler"
        )

    srcdir = cfg.PDFS / args.slug
    if not srcdir.exists():
        print(f"No hay PDFs en {srcdir}")
        return 1
    outdir = FULLTEXT / args.slug
    outdir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(srcdir.glob("*.pdf"))
    done = skipped = failed = 0
    for pdf in pdfs:
        out = outdir / (pdf.stem + ".txt")
        if out.exists() and not args.force:
            skipped += 1
            continue
        # -layout preserva columnas/tablas razonablemente; quitarlo si molesta
        r = subprocess.run(["pdftotext", "-layout", str(pdf), str(out)],
                           capture_output=True, text=True)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            done += 1
        else:
            failed += 1
            print(f"  ! fallo {pdf.name}: {r.stderr.strip()[:120]}")

    print(f"{args.slug}: {done} extraídos, {skipped} ya estaban, {failed} fallaron "
          f"→ {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
