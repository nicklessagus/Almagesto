"""Convierte los PDFs de una estrella a texto plano para búsqueda local y re-extracción.

Uso:
    python extract_fulltext.py <slug> [--force]

pdfs/<slug>/<bibcode>.pdf  →  fulltext/<slug>/<bibcode>.txt

El .txt se commitea (es liviano, greppable y permite `git grep` sobre todo el corpus, además
de re-preguntar al corpus cuando cambia el pipeline sin re-parsear el PDF). Requiere `pdftotext`
(poppler-utils). Idempotente: no re-extrae salvo --force.

Chequeo de legibilidad: un PDF escaneado sin capa de texto o con fuentes Type3/custom sin
ToUnicode produce un .txt vacío o mojibake — inservible para grep y para `verify-citations`
(que necesita las palabras reales). Cada .txt recién extraído se valida con `is_legible()`
(determinista: mínimo de chars no-espacio + fracción de imprimibles ASCII); si no pasa, se
AVISA (el .txt queda como evidencia, el lint lo surfacea como precondición) sin frenar la
cadena. El rescate es reemplazar el PDF por uno con capa de texto sana, o marcar la fuente
`pending` en `sources:` para derivarla al usuario.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

import lib_config as cfg

FULLTEXT = cfg.FULLTEXT

# Umbrales de legibilidad (issue #7): deterministas y laxos a propósito — un paper sano da
# ~99% ASCII imprimible (los acentos/símbolos raros no llegan a 15%); el mojibake cae a ~0%.
LEGIBLE_MIN_RATIO = 0.85   # fracción mínima de chars imprimibles ASCII entre los no-espacio
LEGIBLE_MIN_CHARS = 200    # mínimo de chars no-espacio (un escaneo sin capa de texto da ~0)


def is_legible(text: str) -> tuple[bool, str]:
    """(ok, motivo) — ¿el texto extraído sirve para grep/verify? Determinista. Falla por
    (a) casi sin contenido (escaneo sin capa de texto: pdftotext devuelve sólo espacios/form
    feeds) o (b) mojibake (fuentes sin ToUnicode: mayoría de chars fuera de ASCII imprimible)."""
    content = [c for c in text if not c.isspace()]
    if len(content) < LEGIBLE_MIN_CHARS:
        return False, f"casi sin texto ({len(content)} chars no-espacio) — ¿escaneo sin capa de texto?"
    ratio = sum(1 for c in content if " " <= c <= "~") / len(content)
    if ratio < LEGIBLE_MIN_RATIO:
        return False, f"mojibake: {ratio:.0%} de chars legibles (<{LEGIBLE_MIN_RATIO:.0%}) — ¿fuentes sin ToUnicode?"
    return True, ""


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
    done = skipped = failed = illegible = 0
    for pdf in pdfs:
        out = outdir / (pdf.stem + ".txt")
        if out.exists() and not args.force:
            skipped += 1
            continue
        # -layout preserva columnas/tablas razonablemente; quitarlo si molesta
        r = subprocess.run(["pdftotext", "-layout", str(pdf), str(out)],
                           capture_output=True, text=True)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            ok, why = is_legible(out.read_text(encoding="utf-8", errors="replace"))
            if ok:
                done += 1
            else:
                # No frena la cadena (degradar limpio, issue #7): el .txt queda como evidencia y el
                # lint lo surfacea. Rescate: PDF con capa de texto sana, o `pending` en sources.
                illegible += 1
                print(f"  ⚠ {pdf.name}: fulltext ILEGIBLE — {why}")
                print("     el .txt no sirve para grep/verify-citations; reemplazá el PDF o marcá "
                      "la fuente `pending` en sources: (el lint lo lista como precondición)")
        else:
            failed += 1
            out.unlink(missing_ok=True)  # no dejar un .txt vacío/a medias que la idempotencia congele
            print(f"  ! fallo {pdf.name}: {r.stderr.strip()[:120]}")

    print(f"{args.slug}: {done} extraídos, {skipped} ya estaban, {failed} fallaron"
          + (f", {illegible} ilegibles (⚠ ver arriba)" if illegible else "")
          + f" → {outdir}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
