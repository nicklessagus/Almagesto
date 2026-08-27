#!/usr/bin/env python3
"""Canonical extraction prompt for the per-paper fan-out (step 3 of `ingest-star`/`ingest-theme`).

The extraction rules live in `CLAUDE.md` and in the skills, but the prompt handed to each
subagent used to be written freehand, once per operation. Every rule that does not make it into
the prompt is dropped **silently** at that boundary: measured on the tau Ceti ingest
(2026-08-25, 79 papers), 54 extractors rediscovered the two-column interleaving of #44 on their
own, 23 rediscovered that the subject is spelled `tau Cet`/`HD 10700` rather than `tau Ceti`, and
three overwrote each other's output file because the path was not per-bibcode.

So the prompt is generated from what the vault already knows: the aliases in
`stars.yaml`/`themes.yaml`, and the actual `.txt` on disk (OCR marker, column layout).

    python scripts/extraction_prompt.py <slug> <bibcode>

⛔ The emitted prompt asks only for things that can be **checked** afterwards — line number,
regime, second-hand attribution, verbatim tense and quantifier. It carries no plea for accuracy:
per *Generalization bias in LLM summarization of scientific research* (RSOS 2025, 4900 summaries
over 10 models), prompts that explicitly ask to avoid imprecision **double** over-generalisation
(the "algorithmic ironic rebound effect"). `tests/test_extraction_prompt.py` keeps that executable.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import extract_fulltext
import lib_config as cfg
import measure_layout

#  Catalogue prefixes never stand on their own as a search pattern.
CATALOGUE_PREFIXES = {
    "HD", "HR", "GJ", "GL", "HIP", "BD", "CD", "SAO", "TIC", "TYC", "WDS",
    "2MASS", "NLTT", "LHS", "LTT", "WISE", "TOI", "KIC", "EPIC", "KOI",
}
#  Shortest alphabetic token worth a pattern of its own, and the abbreviated-spelling prefix
#  length (`Ceti` → `Cet`, `Eridani` → `Eri`, `epsilon` → `eps`).
MIN_ALPHA = 4
ABBREV = 3
#  An all-caps token of this length is an acronym worth searching on its own (`ICA`, `PCA`, `SVD`).
ACRONYM = range(3, 7)


def subject_patterns(name: str, aliases=(), kind: str = "star") -> list[str]:
    """Short `grep -niE` patterns that find the subject under every spelling it appears in.

    Short on purpose (#44): the `.txt` interleaves both PDF columns on one physical line, so a
    long pattern straddles the gutter and never matches — and here a false negative reads as
    "the paper does not report this parameter", which is exactly what the extraction decides.

    `kind` matters: truncating a token to three letters recovers the abbreviated spelling that
    astronomical names actually use in print (`Ceti` → `Cet`, `epsilon` → `eps`, and the whole
    constellation-genitive convention). For a *theme* the tokens are ordinary words, so the same
    truncation only yields noise (`procesos` → `pro`); there the useful short form is the acronym.
    """
    #  @inv INV-100
    pats: set[str] = set()
    for raw in [name, *(aliases or [])]:
        tokens = [t for t in re.split(r"[\s_]+", str(raw or "").strip()) if t]
        for i, tok in enumerate(tokens):
            if tok.upper() in CATALOGUE_PREFIXES:
                nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
                if re.fullmatch(r"[\d.+-]+[A-Za-z]?", nxt):
                    pats.add(f"{tok} ?{nxt}")       # the space is optional in half the corpus
                continue
            if re.fullmatch(r"\d{4,}", tok):
                pats.add(tok)                       # a long catalogue number is unambiguous alone
            elif tok.isalpha() and tok.isupper() and len(tok) in ACRONYM:
                pats.add(tok)                       # acronym: `ICA`, `PCA`, `SVD`
            elif tok.isalpha() and len(tok) >= MIN_ALPHA:
                pats.add(tok)
                if kind == "star":
                    pats.add(tok[:ABBREV])          # the abbreviated spelling astro papers use
    return sorted(pats)


def _txt_rel(slug: str, bibcode: str) -> str:
    """Repo-root-relative path of the fulltext, the way every script and grep names it."""
    return f"{(cfg.FULLTEXT / slug / (bibcode + '.txt')).relative_to(cfg.ROOT).as_posix()}"


def is_extraction(d) -> bool:
    """¿Este JSON es una extracción, o es otra cosa que también trae `bibcode`?

    El cosechador del fan-out no puede identificarlo por `bibcode`: la salida de
    `verify-citations` **también** lo lleva. Medido el 2026-08-25: un cosechador que aceptaba
    cualquier JSON con ese campo levantó 13 salidas de verify de OTRA estrella y pisó 13 notas ya
    terminadas — con JSON perfectamente válido, así que el fallo fue silencioso. La identidad es la
    **forma**: `ejes` (mapa) + `ground_truth` (lista).
    """
    #  @inv INV-103
    return (isinstance(d, dict)
            and isinstance(d.get("ejes"), dict)
            and isinstance(d.get("ground_truth"), list)
            and bool(str(d.get("bibcode") or "").strip()))


def _anclado(patron: str) -> str:
    """Frontera de palabra a la izquierda de un patrón alfabético.

    Sin ella la abreviatura de tres letras engancha dentro de otra palabra — medido: `Cet` matchea
    «Princeton» en una lista de afiliaciones, y un extractor tuvo que descartar el hit a mano. La
    frontera va sólo a la izquierda: `Cet` tiene que seguir matcheando `Ceti`.
    """
    #  @inv INV-100
    return rf"\b{patron}" if patron[:1].isalpha() else patron


def _layout_note(texto: str) -> str:
    """The #44 caveat, tied to the line-number rule of #103 — and the MEASUREMENT behind it (#193).

    The warning used to fire only above the threshold and say nothing below, so a misclassification
    was indistinguishable from a correct call. Measured on a real vault: two errors in OPPOSITE
    directions, both hugging the threshold (0.276 filed as single-column while being two-column;
    0.379 filed as two-column while being single), and 12 of 167 files sit in that grey band.

    So the prompt now publishes the number and its threshold in both directions and asks the reader
    to say so when it does not match what they see. No new threshold is invented: moving a cut that
    fails in both directions would only trade one error for the other.

    @inv INV-38"""
    frac = measure_layout.analizar(texto)["frac"]
    medida = (f"  (fracción medida de líneas con canaleta: **{frac:.2f}**, umbral "
              f"{measure_layout.UMBRAL_ARCHIVO:.2f}; si no coincide con lo que ves al leer, "
              f"decilo en `salvedades`.)\n")
    if frac < measure_layout.UMBRAL_ARCHIVO:
        return ("- Este `.txt` se midió como de **UNA columna**, así que el nº de línea es un\n"
                "  localizador válido.\n" + medida)
    return (
        "- ⚠ **Este `.txt` viene a DOS COLUMNAS entrelazadas**: cada línea física concatena un\n"
        "  fragmento de la columna izquierda y otro de la derecha, que son párrafos distintos. El nº\n"
        "  de línea sirve para `grep`, pero **no es un localizador único**: al citar, decí de qué\n"
        "  columna sale el fragmento, y no leas la línea entera como una sola frase.\n" + medida
    )


def _ocr_note(texto: str) -> str:
    if not texto.startswith(cfg.FULLTEXT_OCR_MARK):
        return ""
    return (
        "- ⚠ **Este `.txt` es OCR** (la capa de texto del PDF era ilegible): citable **con salvedad**.\n"
        "  El OCR puede errar símbolos, ligaduras y notación matemática; la cita textual vale para\n"
        "  prosa. Ante duda de un símbolo o de un número, abrí el PDF.\n"
    )


def _symbols_note(slug: str, bibcode: str, texto: str) -> str:
    """UNA sola regla para las ecuaciones: el `.txt` no es fuente confiable, se confirma en el PDF.

    Los tres estados del detector (#113, #192, #194) terminan todos en la misma instrucción, así que
    tener tres redacciones distintas era decir lo mismo tres veces y dejar que el extractor tratara
    dos de ellas como si fueran un permiso:

    · `True`  — `pdftotext` dejó el marcador `(3)` y vació el cuerpo: la fórmula **no está**.
    · `None`  — no hay marcadores suficientes para medir (41 % de un corpus real), y en un `.txt`
                de OCR es el caso normal, porque el OCR se lleva el marcador junto con el cuerpo.
    · `False` — **no es una garantía**: la sustitución de caracteres deja la fórmula con cuerpo y
                cambiada, y ningún chequeo la ve. Medido contra el PDF: `tanh⁻¹` por `tan⁻¹`,
                `si = 1` por `si = ±1`, «model (8)» por «(3)», `f(y)"y` por `f_i(y)=y³`.

    Lo único que el estado cambia es el **alcance**: con `True` se muda toda la lectura de fórmulas
    al PDF y se cita por PÁGINA; en los otros dos la cita sigue siendo por línea y el PDF es el
    chequeo antes de transcribir. El estado medido viaja igual, entre paréntesis, para que se sepa
    qué se sabía.

    @inv INV-38"""
    # La MARCA del header manda sobre el detector corrido en vivo: la estampó `extract_fulltext`
    # al escribir el `.txt` (#113) y es verdad de disco. Re-medir acá y creerle al resultado nuevo
    # sería dejar que el prompt contradiga al archivo.
    medido, motivo = extract_fulltext.symbols_lost(texto)
    if texto.startswith(cfg.FULLTEXT_SYMBOLS_MARK):
        medido, motivo = True, "marca del header"
    estado = ("el `.txt` vació el cuerpo de sus ecuaciones" if medido
              else f"no se pudo medir — {motivo}" if medido is None
              else "sin ecuaciones vaciadas, lo que NO prueba que los símbolos sobrevivieron")
    regla = ("- ⛔ **El `.txt` no es fuente confiable para una ECUACIÓN.** Antes de transcribir "
             f"cualquier fórmula, confirmala contra `{_pdf_rel(slug, bibcode)}` — `Read` lo "
             "rasteriza, así que **ves** la ecuación. Vale siempre: el `.txt` puede haberla "
             "vaciado, haberla dejado con el cuerpo **cambiado**, o no haberse podido medir.\n"
             f"  (Detector: {estado}.)\n")
    if not medido:
        return regla
    return regla + (
        "- ⛔ Acá el detector la confirma: **las ecuaciones NO están en este `.txt`** (#113), así "
        "que la lectura de fórmulas se hace **del PDF** y se cita **página del PDF**, no línea del "
        "`.txt`. Grepear el `.txt` por la fórmula no la va a encontrar, y su ausencia **no** "
        "significa que no esté en el paper.\n"
        "- La prosa sí está y se cita normal, por línea. Es un eje independiente del OCR.\n")


def _pdf_rel(slug: str, bibcode: str) -> str:
    """Ruta repo-root-relative del PDF del par, que es de donde salen las fórmulas con #113."""
    return f"vault/raw/pdfs/{slug}/{bibcode}.pdf"


def build_prompt(slug: str, bibcode: str, name: str, aliases, texto: str,
                 out_dir: str = "", kind: str = "star", sujeto: str | None = None) -> str:
    """The prompt for one (paper, subject) pair. `texto` is the `.txt` as it sits on disk.

    `sujeto` (#188) is the name the VIEW is filed under — the same string the paper uses in
    `stars[]` / `thesis_links[]`, which is what makes claim and reading comparable. It defaults to
    `name` and only differs for a theme, where `theme_by_slug` hands back the slug while the paper
    declares the `concept`; writing the slug there would make `reclamo_sin_vista` fire forever.

    @inv INV-134"""
    #  @inv INV-100
    pats = subject_patterns(name, aliases, kind)
    sujeto = sujeto or name
    tipo = "theme" if kind == "theme" else "star"
    greps = "\n".join(f"  grep -niE '{_anclado(p)}' \"{_txt_rel(slug, bibcode)}\"" for p in pats)
    out = f"{out_dir.rstrip('/')}/{bibcode}.json" if out_dir else f"build/{slug}/extraccion/{bibcode}.json"
    alias_str = ", ".join(f"`{a}`" for a in [name, *(aliases or [])])
    return f"""Sos un extractor de UNA sola fuente. Trabajás desde la raíz del repo.

Leé COMPLETO `{_txt_rel(slug, bibcode)}` y extraé lo que esa fuente dice sobre
**{name}** (alias: {alias_str}).

Esto es **una VISTA**, no «la extracción del paper» (#188): el mismo paper leído desde otro sujeto
da otra vista, y por eso el producto lleva de quién es. Va a la sección `## Vista — {sujeto}` de
`vault/wiki/papers/{bibcode}.md`. Lo que la fuente diga sobre **otros** sujetos no entra acá.

## Búsqueda
Corré estos patrones —cortos a propósito— antes de decidir nada:

{greps}

- Si la fuente **no dice nada** del sujeto, eso es un resultado válido y legítimo: decilo.
- Un `grep` vacío **no prueba ausencia** en papers pre-digitales ni en escaneos: el OCR de ADS
  pierde filas de tabla. Corroborá abriendo la tabla o el PDF antes de afirmar que no está.
- **Mirá las TABLAS, no sólo el texto.** En papers viejos las tablas son **imágenes**: el dato del
  sujeto vive ahí y es invisible a cualquier búsqueda de texto.
- Si es tabla multi-objeto, **verificá la fila correcta** y decí cómo la verificaste.
{_layout_note(texto)}{_ocr_note(texto)}{_symbols_note(slug, bibcode, texto)}
## Cómo anotar cada valor
- El **nº de línea** del `.txt` (de `grep -n`, nunca de `splitlines()`: hay form feeds).
- El **régimen** en que la fuente lo afirma: muestra, época, corte de datos, instrumento, modelo.
- El **tiempo verbal y el cuantificador de la fuente, tal cual**. Si dice «was associated», no
  escribas «is associated»; si dice «el 75 % de la muestra», no escribas «la muestra». Un
  resultado descriptivo no se convierte en recomendación.
- Si la fuente **atribuye el valor a otro trabajo** («according to X», «(X et al.)»), marcalo
  **segunda mano** con la cita a X: el número **no es de esta fuente**.
- Mirá si el `.txt` es un **preprint** de arXiv (marca de agua): si lo es, decilo en `salvedades`,
  porque un valor que discrepa del publicado es candidato a diferencia de versión.
- ⛔ **Nada de prosa comparativa con otros papers.** Comparar dos fuentes es tarea del
  orquestador y va al `## Inventario por eje`, no a esta nota.

## Salida
Escribí el resultado en `{out}` y devolvé el mismo JSON en **un solo bloque** ```json:

{{"bibcode":"{bibcode}","vista":{{"sujeto":"{sujeto}","tipo":"{tipo}","txt":"{slug}"}},
 "role":["fundacional"|"aplicacion"|"arbitro"],"methods":[],"thesis_links":[],
 "ground_truth":[{{"que":"","valor":"","linea":"","regimen":"","segunda_mano":null}}],
 "ejes":{{"discovery":"","rv":"","activity":"","planet":"","method":""}},
 "aporte":"","hueco":"","salvedades":[]}}

⛔ Sin comas finales: tiene que parsear con `json.loads`. El nombre del archivo lleva el bibcode
porque varios extractores corren en paralelo y un nombre genérico se pisa **en silencio**.
`vista` va tal cual: dice de quién es esta lectura y de qué copia del `.txt` salió. La `fecha` y la
`lente` no las escribís vos — las estampa el cosechador, que las sabe con certeza.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug")
    ap.add_argument("bibcode")
    ap.add_argument("--theme", action="store_true", help="el slug es un tema, no una estrella")
    ap.add_argument("--out-dir", default="", help="directorio de salida (default build/<slug>/extraccion)")
    args = ap.parse_args()

    if args.theme:
        name, meta = cfg.theme_by_slug(args.slug)
    else:
        name, meta = cfg.star_by_slug(args.slug)
    path = _txt_rel(args.slug, args.bibcode)
    p = cfg.ROOT / path
    if not p.exists():
        cfg.print_seguro(f"⛔ no existe {path} — corré `extract_fulltext.py {args.slug}` primero")
        return 1
    texto = p.read_text(encoding="utf-8", errors="replace")
    # #188 · el sujeto de la VISTA es el nombre con el que el paper declara la entidad: para un
    # tema es el `concept` (lo que va en `thesis_links`), no el slug que devuelve `theme_by_slug`.
    sujeto = (meta.get("concept") or args.slug) if args.theme else name
    cfg.print_seguro(build_prompt(args.slug, args.bibcode, name, cfg.as_list(meta.get("aliases")),
                                  texto, args.out_dir, "theme" if args.theme else "star", sujeto))
    return 0


if __name__ == "__main__":
    cfg.stdout_tolerante()
    sys.exit(main())
