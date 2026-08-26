"""Convierte los PDFs de una estrella a texto plano para búsqueda local y re-extracción.

Uso:
    python scripts/extract_fulltext.py <slug> [--force] [--ocr]

vault/raw/pdfs/<slug>/<bibcode>.pdf  →  vault/raw/fulltext/<slug>/<bibcode>.txt

Al cerrar estampa en las notas de paper (cirugía de make_notes.stamp_fulltext, nunca sobre la
extracción LLM): `fulltext`, `fulltext_source` (pdftotext|ocr|web) y `pdf_source` (#57: de qué
DOCUMENTO salió el texto — eprint|ads|publisher|web — leyendo la marca que arXiv estampa en el
propio .txt). Por eso re-correrlo es el **backfill** de un corpus ya bajado —no re-baja ningún
PDF, sólo re-lee lo que ya está en disco—: de `pdf_source`, y también de la marca de **garble**
(#104), que hasta ahora sólo corría sobre texto recién extraído, así que un .txt escrito antes de
que ese chequeo existiera se quedaba `pdftotext` para siempre (el camino de skip lo re-leía sólo
para preguntarle si era ILEGIBLE, y un escaneo del editor es perfectamente legible).

El .txt se commitea (es liviano, greppable y permite `git grep` sobre todo el corpus, además
de re-preguntar al corpus cuando cambia el pipeline sin re-parsear el PDF). Requiere `pdftotext`
(poppler-utils). Idempotente: no re-extrae salvo --force.

Chequeo de legibilidad: un PDF escaneado sin capa de texto o con fuentes Type3/custom sin
ToUnicode produce un .txt vacío o mojibake — inservible para grep y para `verify-citations`
(que necesita las palabras reales). Cada .txt recién extraído se valida con `is_legible()`
(determinista: mínimo de chars no-espacio + densidad por página + fracción de imprimibles ASCII).
La densidad por página (#50) agarra el escaneo cuya única capa de texto es la **marca de agua** de
ADS —el bibcode repetido por página—: pasa el mínimo global y antes se contaba como extraído.

Rescate por OCR (opt-in por instalación): si el texto de `pdftotext` NO es legible y hay
`tesseract` (+ `pdftoppm`, de poppler) instalado, se cae SOLO a OCR (pdftoppm 300 dpi + tesseract
por página) y el .txt queda marcado con un header `source: ocr` — **citable con salvedad**: el OCR
puede errar símbolos/ligaduras/notación matemática; la cita textual vale para prosa (ver
verify-citations). `--ocr` fuerza la vía OCR aunque la capa de texto pase el umbral (con --force
re-extrae también los existentes). Un .txt viejo ilegible se re-extrae solo cuando aparece
tesseract (upgrade automático; un .txt ya-OCR ilegible no se reintenta). Si el rescate por OCR
RINDE ALGO (texto, aunque siga sin pasar `is_legible` — p. ej. mojibake u OCR de baja calidad), se
AVISA sin frenar la cadena (el lint lo surfacea); el rescate restante es un PDF con capa de texto
sana o marcar la fuente `pending` en `sources:`.

Distinto es el caso de **cero contenido rescatable** (ni pdftotext ni, si corresponde, OCR
devuelven nada usable — típicamente un PDF corrupto/ilegible como archivo, no sólo "sin capa de
texto"): ESE sí hace que `main()` devuelva 1 y frene la cadena (issue H-04). Es deliberado, no un
resabio: sin ningún .txt que dejar como evidencia no hay nada que el lint pueda surfacear después
—al contrario que el caso ilegible-pero-con-contenido de arriba—, así que la única forma de que un
humano se entere es que la cadena pare y lo diga. El mensaje en pantalla explica qué hacer: un
re-run sin cambiar nada no arregla esto (no es transitorio); hace falta reemplazar el PDF,
instalar/arreglar OCR, o marcar la fuente `pending` en `sources:`.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import lib_config as cfg
import make_notes

FULLTEXT = cfg.FULLTEXT

OCR_DPI = 300                                   # rasterizado pdftoppm (probado: rescate ~99% ASCII)
OCR_MARK = cfg.FULLTEXT_OCR_MARK                # primera línea de un .txt OCR (verify/make_notes la leen)
SYMBOLS_MARK = cfg.FULLTEXT_SYMBOLS_MARK        # ídem para el .txt sin cuerpo de ecuaciones (#113)

# Umbrales de legibilidad (issue #7): deterministas y laxos a propósito — un paper sano da
# ~99% ASCII imprimible (los acentos/símbolos raros no llegan a 15%); el mojibake cae a ~0%.
LEGIBLE_MIN_RATIO = 0.85   # fracción mínima de chars imprimibles ASCII entre los no-espacio
LEGIBLE_MIN_CHARS = 200    # mínimo de chars no-espacio (un escaneo sin capa de texto da ~0)
LEGIBLE_MIN_CHARS_PAGE = 200   # mínimo de chars no-espacio POR PÁGINA (issue #50): un escaneo cuya
                               # única capa de texto es la MARCA DE AGUA de ADS (el bibcode repetido
                               # por página) pasaba el mínimo global y se contaba como extraído
                               # (medido: Baranne+1996, 378 bytes en ~20 páginas ≈ 19 chars/página;
                               # un paper sano da miles). Conservador: 10× arriba de la marca de agua
                               # y 10× abajo de una página de texto real.


def is_legible(text: str) -> tuple[bool, str]:
    """(ok, motivo) — ¿el texto extraído sirve para grep/verify? Determinista. Falla por
    (a) casi sin contenido (escaneo sin capa de texto: pdftotext devuelve sólo espacios/form
    feeds), (b) contenido sólo de marca de agua (densidad por página bajísima) o (c) mojibake
    (fuentes sin ToUnicode: mayoría de chars fuera de ASCII imprimible)."""
    # @inv INV-28
    content = [c for c in text if not c.isspace()]
    if len(content) < LEGIBLE_MIN_CHARS:
        return False, f"casi sin texto ({len(content)} chars no-espacio) — ¿escaneo sin capa de texto?"
    pages = text.count("\f") or 1          # pdftotext deja un form feed por página (OCR las une igual)
    if pages >= 2 and len(content) / pages < LEGIBLE_MIN_CHARS_PAGE:
        return False, (f"~{int(len(content) / pages)} chars no-espacio por página ({pages} páginas) — "
                       "¿escaneo sin capa de texto, con sólo la marca de agua del bibcode?")
    ratio = sum(1 for c in content if " " <= c <= "~") / len(content)
    if ratio < LEGIBLE_MIN_RATIO:
        return False, f"mojibake: {ratio:.0%} de chars legibles (<{LEGIBLE_MIN_RATIO:.0%}) — ¿fuentes sin ToUnicode?"
    return True, ""


# Umbral de GARBLE (#104): la capa de texto existe y es ASCII limpio, pero es OCR del EDITOR
# (un escaneo con su propia capa de texto). `is_legible` no lo ve: mide *extraible*, no *correcto*.
# Importa porque `verify-citations` promete "las palabras reales del paper", y una cita de
# `Coni~nunicatedby` no lo es. Medido sobre 787 .txt de dos bovedas reales: 749 dan exactamente 0,
# p99 = 0.19, y los dos unicos escaneos conocidos dan 5.55 (Bell&Sejnowski 1995) y 2.13
# (Comon 1994); el no-escaneo mas alto da 0.61. El umbral es la media geometrica de ese hueco.
GARBLE_MAX_PER_KWORD = 1.2
# Tilde DENTRO de un token palabra-como y largo. El corte en 8 chars sin digitos es lo que separa
# `Coni~nunicatedby` (dano) de `e~ql` / `e~a2(t~t0)` (matematica mal extraida, falso positivo real
# medido en 1999ApJ...510..986K).
_GARBLE_TOK = re.compile(r"[A-Za-z~]{8,}")
# Runs de letras aisladas: `m a x i m u m`, `n p u t`. SOLO minusculas y con >=3 letras distintas:
# en mayusculas son titulos con tracking tipografico (`D U C T I O N`, estilo MNRAS) y con una sola
# letra son relleno de tabla (`o o o o o`, `T T T T T`) — los tres, falsos positivos medidos.
_GARBLE_RUN = re.compile(r"\b(?:[a-z] ){3,}[a-z]\b")


def garble_score(text: str) -> tuple[float, int, int]:
    """(hits por 1000 palabras, n_tokens_con_tilde, n_runs) — densidad de dano tipico de OCR.
    Determinista. Ver GARBLE_MAX_PER_KWORD para la calibracion."""
    palabras = max(len(text.split()), 1)
    tok = [m for m in _GARBLE_TOK.findall(text) if "~" in m]
    run = [m for m in _GARBLE_RUN.findall(text) if len(set(m.replace(" ", ""))) >= 3]
    return (len(tok) + len(run)) * 1000.0 / palabras, len(tok), len(run)


def is_garbled(text: str) -> tuple[bool, str]:
    """(si, motivo) — la capa de texto del PDF es OCR del editor, no texto nativo.
    Complementa `is_legible`: aquel decide si el .txt SIRVE; este, si sus palabras son las del
    paper. No frena nada — hace que la salvedad OCR viaje."""
    # @inv INV-28
    score, tok, run = garble_score(text)
    if score < GARBLE_MAX_PER_KWORD:
        return False, ""
    return True, (f"{score:.1f} marcas de OCR por 1000 palabras "
                  f"(>={GARBLE_MAX_PER_KWORD}; {tok} palabras con tilde interna, "
                  f"{run} runs de letras sueltas) — la capa de texto parece OCR del editor")


def scanned_header(why: str) -> str:
    """Header del .txt cuya CAPA DE TEXTO ya era OCR (escaneo del editor). Arranca con la misma
    marca que `ocr_header` a proposito: `make_notes` la lee para estampar `fulltext_source: ocr`,
    y la salvedad de citabilidad es exactamente la misma. Lo que cambia es de donde salio el OCR
    — el editor, no tesseract — asi que no se re-OCRea: el texto del PDF ya es el mejor que hay
    (para forzar el rescate con tesseract esta `--ocr`)."""
    return (
        f"{OCR_MARK}: citable CON SALVEDAD\n"
        "# source    : ocr (capa de texto del PDF; OCR del editor, no tesseract)\n"
        f"# motivo    : {why}\n"
        "# salvedad  : el OCR puede errar simbolos/ligaduras/notacion matematica; la cita\n"
        "#             textual vale para prosa (ver verify-citations).\n"
        "# ---- contenido (capa de texto del PDF) ----\n\n"
    )


# Umbral de SIMBOLOS PERDIDOS (#113): el .txt es ASCII limpio y `is_legible`/`is_garbled` lo dan
# por bueno, pero las ECUACIONES se perdieron — sobrevive el marcador "(3)" y desaparecen las
# variables. Modo de falla medido en papers matematicos: `pdftotext` deja el numero de ecuacion y
# vacia su cuerpo, asi que el .txt PARECE tener la formula. Importa porque rompe el estandar
# implementation-ready de concepts/methods y porque `verify-citations`, que lee el mismo .txt, no
# puede hallar una ecuacion que no esta: devolveria `no-soportada` sobre una afirmacion correcta.
# Calibrado sobre 813 .txt de dos bovedas reales: de los 295 con >=4 marcadores, p50=0.00, p75=0.14,
# p90=0.20, p95=0.33, y despues un salto al grupo de rotos (0.98-1.00). El umbral cae en ese hueco.
# Un solo glifo matematico a la izquierda alcanza: exigir dos marcaba EXACTAMENTE los mismos 13
# archivos pero descartaba 3633 marcadores en vez de 1381 (una ecuacion corta como `s = Wx  (6)`
# tiene un unico `=`), asi que bajaba la poblacion evaluable de 343 a 276 sin cambiar un veredicto.
SYMBOLS_LOST_MIN_EQ = 4      # menos que esto no es medicion, es ruido -> se declara NO EVALUADO
SYMBOLS_LOST_MAX_FRAC = 0.60 # marca 13 de 295 (4.4%) en el corpus de calibracion

# La senal esta a la IZQUIERDA del marcador, en la linea fisica. Tres formas que hay que separar:
#   `kurt(v) = E{v4} - 3(E{v2})2 .        (2.1)`  -> cuerpo presente : ecuacion VIVA
#   `                                      (1)  `  -> nada a la izq  : ecuacion PERDIDA
#   `(1) Parameters for the ICA estimation`        -> item de lista, no ecuacion
#   `... as shown in (5), the estimator ...`       -> referencia en prosa, no ecuacion
# NO se parte por la canaleta de 8+ espacios (la convencion de measure_layout): en un paper de UNA
# columna el numero de ecuacion va alineado a la derecha, separado del cuerpo por exactamente esa
# tira, y partir ahi hace que las fuentes MAS limpias parezcan las mas rotas (medido: el .txt mas
# limpio del corpus daba 87% perdidas con esa variante).
_MATH_GLYPHS = set("=+-*/^_<>{}") | set("\u2212\u2211\u222b\u2202\u2207\u2264\u2265\u2248\u2260\u00b1\u00b7\u00d7\u2208")
_EQ_MARKER = re.compile(r"\(\s*\d{1,2}(?:\.\d{1,2})?\s*\)")
_EQ_LIST_ITEM = re.compile(r"^\(\s*\d{1,2}(?:\.\d{1,2})?\s*\)\s+[A-Z(]")


def symbols_lost_score(text: str) -> tuple[int, int]:
    """(ecuaciones con cuerpo, ecuaciones vacias) — determinista. Ver los umbrales de arriba."""
    alive = lost = 0
    for line in text.split("\n"):
        if _EQ_LIST_ITEM.match(line.strip()):
            continue                                   # enumeracion en prosa, no ecuacion
        for m in _EQ_MARKER.finditer(line):
            if line[m.end():].strip():
                continue                               # el marcador no cierra la linea: es una cita
            left = line[: m.start()]
            if not left.strip():
                lost += 1
            elif any(c in _MATH_GLYPHS for c in left):
                alive += 1
            # prosa sin matematica a la izquierda: una referencia "(3)", no una ecuacion
    return alive, lost


def symbols_lost(text: str) -> tuple[bool | None, str]:
    """(si, motivo) — ¿el .txt perdio el cuerpo de sus ecuaciones?

    Devuelve **None** cuando no hay marcadores suficientes para medir: ese caso es *no evaluado*,
    no *esta bien* (D-43). Un `False` ahi seria un cero que nadie midio, leido como veredicto — el
    mismo falso limpio que el lint existe para no producir. Medido: 275 de 813 .txt del corpus de
    calibracion caen en este caso (34%), asi que no es un borde raro.
    """
    # @inv INV-28
    alive, lost = symbols_lost_score(text)
    total = alive + lost
    if total < SYMBOLS_LOST_MIN_EQ:
        return None, (f"{total} marcador(es) de ecuacion: por debajo de {SYMBOLS_LOST_MIN_EQ}, "
                      "no alcanza para medir")
    frac = lost / total
    if frac < SYMBOLS_LOST_MAX_FRAC:
        return False, ""
    return True, (f"{lost} de {total} ecuaciones ({frac:.0%}) quedaron con el marcador y SIN cuerpo "
                  f"(>={SYMBOLS_LOST_MAX_FRAC:.0%}) — pdftotext perdio los simbolos; para citar una "
                  "formula de este paper hay que abrir el PDF")


def symbols_header(why: str) -> str:
    """Aviso al tope del .txt: los simbolos no estan aca. Lo lee `make_notes` para estampar
    `symbols_lost: true` en la nota, y de ahi lo consume el extractor (que abre el PDF) y
    `verify-citations` (que cita PAGINA, no linea, para las formulas de esta fuente)."""
    return (
        f"{SYMBOLS_MARK}: las ECUACIONES no estan en este archivo\n"
        f"# motivo    : {why}\n"
        "# implica   : grepear este .txt por una formula de este paper NO la va a encontrar.\n"
        "#             La prosa si es citable y los nº de linea valen para ella.\n"
        "# ---- contenido (capa de texto del PDF) ----\n\n"
    )


def backfill_scanned_mark(prev: str) -> str | None:
    """Reason to stamp the OCR caveat on an ALREADY EXTRACTED .txt, or None if there is none.

    `is_garbled` only ever ran on freshly extracted text, so a .txt written before that check
    existed keeps `fulltext_source: pdftotext` forever: the skip path below re-reads it only to
    ask whether it is ILLEGIBLE, and an editor-OCR scan is perfectly legible. Measured on a real
    vault: 3 of the 42 .txt of one theme, and one of them was a paper whose equations the note
    had transcribed with an OCR-induced subscript error nobody caught.

    No re-extraction: for an editor-OCR scan the PDF's own text layer is already the best text
    available (see `scanned_header`), so this is a header stamp — and it stays idempotent,
    because a .txt that already carries the mark is not garble-scored again.
    """
    # @inv INV-28
    if prev.startswith(OCR_MARK) or prev.startswith(SYMBOLS_MARK) or not is_legible(prev)[0]:
        return None
    garbled, why = is_garbled(prev)
    return why if garbled else None


def backfill_symbols_mark(prev: str) -> str | None:
    """Gemelo de `backfill_scanned_mark` para el eje de #113: motivo si hay que estampar, None si no.

    Mismo problema y misma forma: el chequeo sólo corría sobre texto recién extraído, así que un
    `.txt` escrito antes se queda mudo para siempre. Idempotente por la marca; no pisa el carril
    del garble (un `.txt` que ya avisa que es OCR ya le dice al lector que abra el PDF ante una
    duda de símbolos, y apilar los dos headers sería ruido).
    """
    # @inv INV-28
    if prev.startswith(OCR_MARK) or prev.startswith(SYMBOLS_MARK) or not is_legible(prev)[0]:
        return None
    perdidos, why = symbols_lost(prev)
    return why if perdidos else None


def ocr_available() -> bool:
    # @inv INV-70
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



def _flags_usados(args, ap=None) -> list:
    """Los flags no-default de esta corrida, para dejarlos en `cadena:` del registro (D-48/D-57).
    Son las **escotillas**: `--force`, `--yes`, `--all` cambian lo que la corrida hizo, y sin
    registrarlas la traza dice "corrió make_notes" sobre dos corridas que no hicieron lo mismo."""
    return cfg.flags_usados(args, ap)

def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
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
    done = ocred = skipped = failed = illegible = backfilled = bf_symbols = 0
    for pdf in pdfs:
        out = outdir / (pdf.stem + ".txt")
        if out.exists() and not args.force:
            # Upgrade automático: un .txt viejo ILEGIBLE se re-extrae por OCR apenas hay tesseract
            # (instalarlo + re-correr alcanza). Un .txt ya-OCR que sigue ilegible no se reintenta.
            prev = out.read_text(encoding="utf-8", errors="replace")
            if not (ocr_available() and not prev.startswith(OCR_MARK) and not is_legible(prev)[0]):
                gwhy = backfill_scanned_mark(prev)
                if gwhy is not None:
                    cfg.write_text_atomic(out, scanned_header(gwhy) + prev)
                    print(f"  {pdf.name}: {gwhy} → marcado `source: ocr` (backfill)")
                    backfilled += 1
                    continue
                swhy = backfill_symbols_mark(prev)
                if swhy is not None:
                    cfg.write_text_atomic(out, symbols_header(swhy) + prev)
                    print(f"  {pdf.name}: {swhy} (backfill)")
                    bf_symbols += 1
                    continue
                skipped += 1
                continue
            print(f"  {pdf.name}: .txt existente ilegible → reintento con OCR")
        # D-18: el mismo bibcode ya extraído bajo otro slug es el MISMO texto — copiarlo evita
        # re-correr pdftotext/OCR (el paso más caro después de la red). Se reusa sólo si la copia
        # es LEGIBLE: una copia mojibake no ahorra nada, sólo propaga el problema a otro slug.
        # `not args.ocr`: el atajo D-18 copia el `.txt` que otro slug ya extrajo, y ese `.txt` es de
        # **pdftotext**. Con `--ocr` (que existe justamente para forzar la vía OCR aunque la capa de
        # texto pase el umbral) el atajo lo dejaba sin correr, sin header `source: ocr` y con
        # `fulltext_source: pdftotext`: la escotilla no hacía nada y no lo decía.
        if not args.force and not args.ocr and not out.exists():
            otro = cfg.artefacto_en_otro_slug(cfg.FULLTEXT, args.slug, pdf.stem, ".txt")
            if otro is not None:
                prev = otro.read_text(encoding="utf-8", errors="replace")
                if is_legible(prev)[0]:
                    cfg.write_text_atomic(out, prev)
                    print(f"  ↺ {pdf.stem}: ya extraído bajo `{otro.parent.name}` — copiado (D-18)")
                    done += 1
                    continue
        text, why = None, "forzado con --ocr"
        if not args.ocr:
            # -layout preserva columnas/tablas razonablemente; quitarlo si molesta
            r = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0 and r.stdout:
                text = r.stdout
                ok, why = is_legible(text)
                if ok and not text.startswith(OCR_MARK):
                    garbled, gwhy = is_garbled(text)
                    if garbled:
                        print(f"  {pdf.name}: {gwhy} → marcado `source: ocr`")
                        text = scanned_header(gwhy) + text
                    else:
                        # #113: eje INDEPENDIENTE del garble — los dos casos medidos (1999Hyvarinen,
                        # 1999HyvarinenNoisy) dan garble 0.00 y 100% de ecuaciones vacías.
                        perdidos, swhy = symbols_lost(text)
                        if perdidos:
                            print(f"  {pdf.name}: {swhy}")
                            text = symbols_header(swhy) + text
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
                # H-04: antes este caso quedaba MUDO (sólo el "! fallo pdftotext" de arriba, si
                # aplicaba) y `main()` devuelve 1 más abajo — frena la cadena de ingest a propósito
                # (ver docstring del módulo), pero sin este aviso el operador no tenía ninguna
                # pista de QUÉ hacer, y "corregí y re-corré" (mensaje del orquestador) es ambiguo:
                # un re-run sin cambiar nada repite el mismo fallo para siempre.
                cfg.print_seguro(
                    f"  ⛔ {pdf.name}: SIN contenido rescatable (pdftotext no devolvió texto usable "
                    "y no hay tesseract instalado) — un re-run SIN cambiar nada no arregla esto: "
                    "instalá tesseract-ocr, reemplazá el PDF, o marcá la fuente `pending` en sources:.")
                continue
            ocr_text = ocr_pdf(pdf)
            if ocr_text is None:
                failed += 1
                out.unlink(missing_ok=True)
                cfg.print_seguro(
                    f"  ⛔ {pdf.name}: SIN contenido rescatable (pdftotext falló y el propio OCR "
                    "también falló técnicamente — ver el error de pdftoppm/tesseract arriba) — un "
                    "re-run SIN cambiar nada no arregla esto: reemplazá el PDF o marcá la fuente "
                    "`pending` en sources:.")
                continue
            ok, _why2 = is_legible(ocr_text)
            text = ocr_header(why) + ocr_text        # header source: ocr → citable con salvedad
            why = _why2
        cfg.write_text_atomic(out, text)
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
          + (f", {backfilled} marcados `source: ocr` (backfill)" if backfilled else "")
          + (f", {bf_symbols} marcados sin ecuaciones (backfill)" if bf_symbols else "")
          + (f", {illegible} ilegibles (⚠ ver arriba)" if illegible else "")
          + f" → {outdir}")

    # Contrato máquina: estampar `fulltext:`/`fulltext_source:`/`pdf_source:` en las notas de paper
    # para TODOS los .txt del slug (recién extraídos, viejos y snapshots web) — el stub nace antes
    # que el .txt (make_notes corre primero en la cadena), así que este paso cierra el contrato; de
    # paso un re-run idempotente migra notas pre-contrato sin los campos (es el backfill de
    # `pdf_source` en un corpus ya bajado, #57: la marca de arXiv ya está en el .txt, no hay que
    # re-bajar ningún PDF). Cirugía de make_notes: nunca toca la extracción LLM.
    stamped = sum(make_notes.stamp_fulltext(cfg.PAPERS / f"{t.stem}.md", t.stem, args.slug)
                  for t in sorted(outdir.glob("*.txt")))
    if stamped:
        print(f"  notas: {stamped} con fulltext:/fulltext_source:/pdf_source: estampados "
              "(contrato máquina)")
    if not failed:
        cfg.save_paso(args.slug, "extract_fulltext", flags=_flags_usados(args, ap))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
