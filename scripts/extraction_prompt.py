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


def _layout_note(texto: str) -> str:
    """The #44 caveat, tied to the line-number rule of #103 — only when it actually applies."""
    if measure_layout.analizar(texto)["frac"] < measure_layout.UMBRAL_ARCHIVO:
        return ""
    return (
        "- ⚠ **Este `.txt` viene a DOS COLUMNAS entrelazadas**: cada línea física concatena un\n"
        "  fragmento de la columna izquierda y otro de la derecha, que son párrafos distintos. El nº\n"
        "  de línea sirve para `grep`, pero **no es un localizador único**: al citar, decí de qué\n"
        "  columna sale el fragmento, y no leas la línea entera como una sola frase.\n"
    )


def _ocr_note(texto: str) -> str:
    if not texto.startswith(cfg.FULLTEXT_OCR_MARK):
        return ""
    return (
        "- ⚠ **Este `.txt` es OCR** (la capa de texto del PDF era ilegible): citable **con salvedad**.\n"
        "  El OCR puede errar símbolos, ligaduras y notación matemática; la cita textual vale para\n"
        "  prosa. Ante duda de un símbolo o de un número, abrí el PDF.\n"
    )


def build_prompt(slug: str, bibcode: str, name: str, aliases, texto: str,
                 out_dir: str = "", kind: str = "star") -> str:
    """The prompt for one (paper, subject) pair. `texto` is the `.txt` as it sits on disk."""
    #  @inv INV-100
    pats = subject_patterns(name, aliases, kind)
    greps = "\n".join(f"  grep -niE '{p}' \"{_txt_rel(slug, bibcode)}\"" for p in pats)
    out = f"{out_dir.rstrip('/')}/{bibcode}.json" if out_dir else f"build/{slug}/extraccion/{bibcode}.json"
    alias_str = ", ".join(f"`{a}`" for a in [name, *(aliases or [])])
    return f"""Sos un extractor de UNA sola fuente. Trabajás desde la raíz del repo.

Leé COMPLETO `{_txt_rel(slug, bibcode)}` y extraé lo que esa fuente dice sobre
**{name}** (alias: {alias_str}).

## Búsqueda
Corré estos patrones —cortos a propósito— antes de decidir nada:

{greps}

- Si la fuente **no dice nada** del sujeto, eso es un resultado válido y legítimo: decilo.
- Un `grep` vacío **no prueba ausencia** en papers pre-digitales ni en escaneos: el OCR de ADS
  pierde filas de tabla. Corroborá abriendo la tabla o el PDF antes de afirmar que no está.
- **Mirá las TABLAS, no sólo el texto.** En papers viejos las tablas son **imágenes**: el dato del
  sujeto vive ahí y es invisible a cualquier búsqueda de texto.
- Si es tabla multi-objeto, **verificá la fila correcta** y decí cómo la verificaste.
{_layout_note(texto)}{_ocr_note(texto)}
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

{{"bibcode":"{bibcode}","role":["fundacional"|"aplicacion"|"arbitro"],"methods":[],"thesis_links":[],
 "ground_truth":[{{"que":"","valor":"","linea":"","regimen":"","segunda_mano":null}}],
 "ejes":{{"discovery":"","rv":"","activity":"","planet":"","method":""}},
 "aporte":"","hueco":"","salvedades":[]}}

⛔ Sin comas finales: tiene que parsear con `json.loads`. El nombre del archivo lleva el bibcode
porque varios extractores corren en paralelo y un nombre genérico se pisa **en silencio**.
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
    cfg.print_seguro(build_prompt(args.slug, args.bibcode, name, cfg.as_list(meta.get("aliases")),
                                  texto, args.out_dir, "theme" if args.theme else "star"))
    return 0


if __name__ == "__main__":
    cfg.stdout_tolerante()
    sys.exit(main())
