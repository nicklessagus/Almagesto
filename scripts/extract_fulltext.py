"""Convierte los PDFs de una estrella a texto plano para búsqueda local y re-extracción.

Uso:
    python extract_fulltext.py <slug> [--force] [--ocr]

pdfs/<slug>/<bibcode>.pdf  →  fulltext/<slug>/<bibcode>.txt

El .txt se commitea (es liviano, greppable y permite `git grep` sobre todo el corpus, además
de re-preguntar al corpus cuando cambia el pipeline sin re-parsear el PDF). Requiere `pdftotext`
(poppler-utils). Idempotente: no re-extrae salvo --force.

Chequeo de legibilidad: un PDF escaneado sin capa de texto o con fuentes Type3/custom sin
ToUnicode produce un .txt vacío o mojibake — inservible para grep y para `verify-citations`
(que necesita las palabras reales). Cada .txt recién extraído se valida con `is_legible()`
(determinista: mínimo de chars no-espacio + fracción de imprimibles ASCII).

Rescate por OCR (opt-in por instalación): si el texto de `pdftotext` NO es legible y hay
`tesseract` (+ `pdftoppm`, de poppler) instalado, se cae SOLO a OCR (pdftoppm 300 dpi + tesseract
por página) y el .txt queda marcado con un header `source: ocr` — **citable con salvedad**: el OCR
puede errar símbolos/ligaduras/notación matemática; la cita textual vale para prosa (ver
verify-citations). `--ocr` fuerza la vía OCR aunque la capa de texto pase el umbral (con --force
re-extrae también los existentes). Un .txt viejo ilegible se re-extrae solo cuando aparece
tesseract (upgrade automático; un .txt ya-OCR ilegible no se reintenta). Si tampoco hay OCR o
tampoco rinde, se AVISA sin frenar la cadena (el lint lo surfacea); el rescate restante es un PDF
con capa de texto sana o marcar la fuente `pending` en `sources:`.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import lib_config as cfg

FULLTEXT = cfg.FULLTEXT

OCR_DPI = 300                                   # rasterizado pdftoppm (probado: rescate ~99% ASCII)
OCR_MARK = "# Almagesto — fulltext por OCR"     # primera línea de un .txt OCR (lo detecta verify)

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


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None and shutil.which("pdftoppm") is not None


def tesseract_version() -> str:
    """Primera línea de `tesseract --version` (provenance del header OCR)."""
    try:
        r = subprocess.run(["tesseract", "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return (r.stdout or r.stderr).splitlines()[0].strip()
    except Exception:
        return "tesseract (versión desconocida)"


def ocr_header(why: str) -> str:
    """Header del .txt OCR: marca la provenance (`source: ocr`) y la salvedad de citabilidad,
    para que verify-citations (y cualquier lector) sepa que el texto puede errar en símbolos."""
    return (
        f"{OCR_MARK}: citable CON SALVEDAD\n"
        f"# source    : ocr ({tesseract_version()}; pdftoppm {OCR_DPI} dpi)\n"
        f"# motivo    : {why}\n"
        "# salvedad  : el OCR puede errar simbolos/ligaduras/notacion matematica; la cita\n"
        "#             textual vale para prosa (ver verify-citations).\n"
        "# ---- contenido OCR ----\n\n"
    )


def ocr_pdf(pdf: Path) -> str | None:
    """PDF → texto por OCR: `pdftoppm -r 300 -png` por página + `tesseract` a stdout, unidas con
    form feed (como pdftotext). Determinista para una misma versión de tesseract. None si falla."""
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(["pdftoppm", "-r", str(OCR_DPI), "-png", str(pdf), str(Path(td) / "p")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            print(f"    ! pdftoppm falló: {r.stderr.strip()[:120]}")
            return None
        pages = sorted(Path(td).glob("p*.png"))
        if not pages:
            print("    ! pdftoppm no produjo páginas")
            return None
        out = []
        for pg in pages:
            r = subprocess.run(["tesseract", str(pg), "stdout", "--dpi", str(OCR_DPI)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode:
                print(f"    ! tesseract falló en {pg.name}: {r.stderr.strip()[:120]}")
                return None
            out.append(r.stdout)
        return "\f".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--ocr", action="store_true",
                    help="extraer por OCR (tesseract) en vez de pdftotext; sin este flag el OCR "
                         "corre solo como fallback cuando la capa de texto no es legible")
    args = ap.parse_args()

    if args.ocr and not ocr_available():
        sys.exit(
            "--ocr pide `tesseract` (+ `pdftoppm`, de poppler), y falta alguno:\n"
            "  Debian/Ubuntu: sudo apt install tesseract-ocr   ·  macOS: brew install tesseract\n"
            "  Fedora: sudo dnf install tesseract               ·  Windows: conda install -c conda-forge tesseract"
        )

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
    done = ocred = skipped = failed = illegible = 0
    for pdf in pdfs:
        out = outdir / (pdf.stem + ".txt")
        if out.exists() and not args.force:
            # Upgrade automático: un .txt viejo ILEGIBLE se re-extrae por OCR apenas hay tesseract
            # (instalarlo + re-correr alcanza). Un .txt ya-OCR que sigue ilegible no se reintenta.
            prev = out.read_text(encoding="utf-8", errors="replace")
            if not (ocr_available() and not prev.startswith(OCR_MARK) and not is_legible(prev)[0]):
                skipped += 1
                continue
            print(f"  {pdf.name}: .txt existente ilegible → reintento con OCR")
        text, why = None, "forzado con --ocr"
        if not args.ocr:
            # -layout preserva columnas/tablas razonablemente; quitarlo si molesta
            r = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0 and r.stdout:
                text = r.stdout
                ok, why = is_legible(text)
                if not ok and ocr_available():
                    print(f"  {pdf.name}: capa de texto ilegible ({why}) → fallback OCR")
                    text = None                      # cae al OCR de abajo
            else:
                print(f"  ! fallo pdftotext {pdf.name}: {r.stderr.strip()[:120]}")
                why = "pdftotext falló o no devolvió texto"
        via_ocr = text is None
        if via_ocr:
            if not ocr_available():
                failed += 1
                out.unlink(missing_ok=True)  # no dejar un .txt vacío/a medias que la idempotencia congele
                continue
            ocr_text = ocr_pdf(pdf)
            if ocr_text is None:
                failed += 1
                out.unlink(missing_ok=True)
                continue
            ok, _why2 = is_legible(ocr_text)
            text = ocr_header(why) + ocr_text        # header source: ocr → citable con salvedad
            why = _why2
        out.write_text(text, encoding="utf-8")
        if ok:
            done += 1
            ocred += 1 if via_ocr else 0
        else:
            # No frena la cadena (degradar limpio, issue #7): el .txt queda como evidencia y el
            # lint lo surfacea. Rescate: OCR (si falta tesseract), PDF sano, o `pending` en sources.
            illegible += 1
            print(f"  ⚠ {pdf.name}: fulltext ILEGIBLE — {why}"
                  + (" (ni con OCR)" if via_ocr else ""))
            print("     no sirve para grep/verify-citations; "
                  + ("reemplazá el PDF o marcá la fuente `pending` en sources:"
                     if via_ocr else
                     "instalá `tesseract-ocr` para rescatarlo por OCR (ver docs/operacion.md), "
                     "reemplazá el PDF, o marcá la fuente `pending` en sources:")
                  + " (el lint lo lista como precondición)")

    print(f"{args.slug}: {done} extraídos" + (f" ({ocred} por OCR)" if ocred else "")
          + f", {skipped} ya estaban, {failed} fallaron"
          + (f", {illegible} ilegibles (⚠ ver arriba)" if illegible else "")
          + f" → {outdir}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
