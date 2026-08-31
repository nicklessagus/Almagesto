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

#  Catalogue prefixes never stand on their own as a search pattern.
CATALOGUE_PREFIXES = {
    "HD", "HR", "GJ", "GL", "HIP", "BD", "CD", "SAO", "TIC", "TYC", "WDS",
    "2MASS", "NLTT", "LHS", "LTT", "WISE", "TOI", "KIC", "EPIC", "KOI",
}
#  Shortest alphabetic token worth a pattern of its own, and the abbreviated-spelling prefix
#  length (`Ceti` → `Cet`, `Eridani` → `Eri`, `epsilon` → `eps`).
MIN_ALPHA = 4
ABBREV = 3
#  A whole name this short is itself a usable pattern (`AU Mic`, `55 Cnc`, `K2-18`). Without this,
#  a name made only of short tokens produced ZERO patterns — see the docstring.
MAX_NAME = 14
#  A designation mixing letters and digits is unambiguous on its own: `K2-18`, `TRAPPIST-1`,
#  `WASP-12b`, `HAT-P-11`. `isalpha()` rejects them, which is why they used to fall through.
DESIGNATION = re.compile(r"[A-Za-z]{1,10}[-\d][\w.+-]*$")
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

    ⛔ **Devolvía `[]` para una familia entera de nombres reales** — medido el 2026-08-28:
    `AU Mic`, `55 Cnc`, `eps Eri`, `K2-18` y `TRAPPIST-1`, todos `[]`. `AU Mic` es el ejemplo del
    propio skill `ingest-star`. Tres huecos que se tapaban entre sí:

    · `MIN_ALPHA = 4` generaba la abreviatura **desde** el token largo (`Ceti` → `Cet`) y **rechazaba
      el nombre ya abreviado**, que es justamente la grafía que esta función existe para perseguir;
    · una designación con dígitos (`K2-18`, `TRAPPIST-1`) no es `isalpha()` y caía por el costado;
    · y nada devolvía el **nombre entero** cuando ningún token calificaba solo.

    El daño es el que el párrafo de arriba nombra: el prompt salía con el bloque de búsqueda
    **vacío** bajo un encabezado que promete patrones, y un `grep` que no corre se lee como «el
    paper no reporta este parámetro».
    """
    #  @inv INV-100
    pats: set[str] = set()
    for raw in [name, *(aliases or [])]:
        limpio = str(raw or "").strip()
        tokens = [t for t in re.split(r"[\s_]+", limpio) if t]
        #  El nombre entero, cuando es corto: es la grafía literal y ningún token la reconstruye.
        if 0 < len(limpio) <= MAX_NAME and len(tokens) > 1:
            pats.add(limpio.replace(" ", " ?"))     # el espacio es opcional en medio corpus
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
            elif kind == "star" and DESIGNATION.fullmatch(tok) and any(c.isdigit() for c in tok):
                pats.add(tok)                       # `K2-18`, `TRAPPIST-1`, `WASP-12b`
            elif tok.isalpha() and len(tok) >= (ABBREV if kind == "star" else MIN_ALPHA):
                pats.add(tok)
                if kind == "star" and len(tok) > ABBREV:
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


def _media_note(slug: str, bibcode: str) -> str:
    """Tablas y figuras, leyendo el PDF (#195 → #205).

    Con el `.txt` como fuente, la mitad de esta regla era «levantalo del PDF». Leyendo el PDF eso
    es redundante y queda lo que sigue siendo **criterio de lectura**:

    · **la fila correcta** — en una tabla multi-objeto la fila equivocada es el modo de falla, y
      el extractor tiene que decir cómo la verificó;
    · **el permiso de leer una figura**, que no depende de qué archivo se abra sino de cómo se
      declara: es la doctrina de `inferencia` —la bóveda puede sostener algo que ninguna fuente
      escribe **siempre que declare de dónde salió**—. Sin la declaración, una estimación visual
      entra como si fuera un valor publicado.

    Medido (#195): 29 de 65 vistas de un tema real (45 %) declaran datos que viven sólo en figuras
    o tablas-imagen, y varias veces la figura **es** el resultado.

    #281 lo extiende con el caso que #195 no contempla: una figura que es un **campo** (contornos,
    mapa de color, densidad) y no una curva. Ahí «el valor a x» no está definido sin el **nivel**, y
    dos lecturas honestas devuelven números distintos. Medido: la Fig. H.2 de
    `2023A&A...680A..64D` es un mapa de probabilidad de detección, y tres lecturas
    «irreconciliables» de la banda de 30-50 M_J (2-3, 1,8-4 y 3,5-6 UA) eran los contornos del
    10, 50 y 90 % de la MISMA figura. El costo no fue un número mal copiado: fue **declarar un
    hueco que no existía**. De ahí el orden del bloque — sospechar de la figura ANTES de la salida
    «hueco declarado», que cierra la puerta.

    @inv INV-100"""
    return (
        "- **Tablas:** transcribí la fila y **decí cómo la verificaste**. En una tabla "
        "multi-objeto la fila equivocada es el modo de falla — conteo de columnas, cierre contra "
        "el total, lo que hayas usado.\n"
        "- 📈 **Una FIGURA se puede leer, declarada como tal.** Cuando el número existe **sólo "
        "como curva** no hay cita textual posible, y eso no lo vuelve inservible: podés estimarlo "
        "visualmente, y entonces viaja con las tres cosas que lo distinguen de inventarlo — la "
        "**figura y su página** (`Fig. 3, p. 7`) en el localizador, el **`≈` explícito** (o el "
        "rango) en el valor, y la palabra **lectura de gráfico** en el régimen. No es un valor "
        "publicado y no puede entrar como si lo fuera.\n"
        "- 🗺 **Si la figura es un CAMPO —mapa de contornos, mapa de color, diagrama de densidad— "
        "el valor NO EXISTE sin el nivel.** «El valor a x» está definido en una curva y no en un "
        "campo: dos lectores honestos leyendo la misma figura devuelven números distintos sin que "
        "ninguno se equivoque. Se cita `Fig. N, p. M, contorno del X %` (o el nivel que "
        "corresponda), y si el dato necesita varios niveles, se dan todos. Antes de leer, mirá la "
        "escala de color o la leyenda de niveles: si la figura tiene una, es un campo.\n"
        "  ⛔ Leer «la curva» de un campo es la forma de producir tres lecturas incompatibles y "
        "archivarlas como hueco. Medido (#281): una banda de 30-50 M_J leída como 2-3, 1,8-4 y "
        "3,5-6 UA eran los contornos del 10, 50 y 90 % de la MISMA figura.\n"
        "  ⛔ **Si dos lecturas de la misma figura no reconcilian, la primera hipótesis es figura "
        "SUBESPECIFICADA (¿es un campo? ¿leíste dos niveles distintos?), no dato ilegible.** El "
        "orden importa: la segunda cierra la puerta —el hueco declarado es una promesa de que la "
        "bóveda no puede responder— y la primera la abre.\n"
        "  ⛔ Es un **permiso, no una obligación**: si la figura no permite leer el valor con "
        "confianza, sigue siendo un **hueco declarado**. Forzar un número de una curva ilegible es "
        "peor que el hueco.\n")


def _pdf_rel(slug: str, bibcode: str) -> str:
    """Repo-root-relative path of the pair's PDF — **the copy that exists** (#305).

    The prompt used to name `vault/raw/pdfs/<slug del sujeto>/…` unconditionally, so for a
    retro-tagged paper (whose PDF lives under the slug that first ingested it) it pointed at a file
    that is not there. Falls back to the subject's slug, which is the right path for the message
    that says the PDF is missing."""
    return f"vault/raw/pdfs/{cfg.pdf_slug(bibcode, slug) or slug}/{bibcode}.pdf"


CORTO = """## Cómo leerlo: empezá por las CONCLUSIONES
Antes de recorrer el paper, leé **abstract y conclusiones**. De ahí sale la lista de **ejes** que el
trabajo dice aportar, y con esa lista vas al cuerpo — es más rápido que leer linealmente y no te
perdés lo que el paper considera su resultado.

⛔ **Tratalas como hipótesis a confirmar, no como resumen confiable.** Está medido (RSOS 2025, 4900
resúmenes / 10 modelos): el resumen afirma **más fuerte** que el cuerpo — genérico donde el cuerpo
acota, presente donde el cuerpo usa pasado, prescriptivo donde el cuerpo describe. Por cada eje,
chequeá en el cuerpo si se sostiene y **con qué condiciones**. Si el cuerpo dice menos que las
conclusiones, eso va en `salvedades`: es un hallazgo sobre la FUENTE, no un error tuyo."""
"""How to read a SHORT source: the whole paper rasterises, so it starts from the conclusions."""

LARGO = """## Cómo leerlo: es un DOCUMENTO LARGO — empezá por el ÍNDICE
⛔ **No lo rasterices entero.** Esta fuente declara `unidad_cita: {unidad}`: es un libro, un handbook
o una tesis. Abrí **las primeras páginas** del PDF, ubicá el índice y de ahí los rangos de página de
los capítulos que entran. Después grepeá el `.txt` para afinar y abrí **sólo esas páginas** del PDF.

⛔ **El ALCANCE declarado, que es lo que entra y nada más:**
    {alcance}
Si lo que el sujeto necesita está **fuera** de ese alcance, **no lo amplíes solo**: extraé lo que hay
dentro y decilo en `salvedades`. Ampliar el alcance en silencio deja el campo `alcance` de la nota
afirmando algo falso, y el chequeo de completitud de `verify-citations` —que existe para distinguir
un recorte deliberado de una omisión— pierde el único dato que lo hace decidible.

⚠ **`conclusiones` va VACÍO.** Un libro no tiene esa sección y transcribir algo que no existe fabrica
contenido. Es una exclusión estructural, no un umbral de largo.

⚠ **Citá por PÁGINA** (`p. 214`), nunca por línea: «línea 18443» no es una referencia utilizable.
"""
"""How to read a LONG source (#80/#241): table of contents, declared scope, only those pages."""


def _long_document(bibcode: str) -> tuple[str, str]:
    """`(unidad_cita, alcance)` of a paper note, or `("", "")` when it is not a long document.

    #241 — the two fields #80 created were wired end to end EXCEPT the last leg: `themes.yaml`
    declares them, `ingest_theme` validates them, `write_web_paper_note` stamps them and the lint
    reports the missing one — and the prompt never read them. So a 161-page thesis got the same
    instructions as an 11-page paper: one telling it to rasterise the whole PDF (700 pages do not
    rasterise, as the contract says two sections above) and one telling it to start from the
    conclusions (a book has none, and the same contract forbids transcribing them).
    """
    nota = cfg.PAPERS / f"{bibcode}.md"
    if not nota.exists():
        return "", ""
    fm = cfg.split_fm(nota.read_text(encoding="utf-8")) or {}
    unidad = str(fm.get("unidad_cita") or "").strip()
    return (unidad, str(fm.get("alcance") or "").strip()) if unidad and unidad != "linea" else ("", "")


SIN_PDF = """⛔ **NO HAY PDF de esta fuente en disco** (`{pdf}` no existe). La vista sale del
**`## Abstract` de la nota** — `vault/wiki/papers/{bibcode}.md` — y de nada más, así que la
**declarás `fuente: abstract`** en `vista` (#207). No inventes páginas: sin PDF no hay localizador
de página, y el `linea` de cada valor dice de dónde salió (`abstract`).

⛔ **El abstract es justo donde la fuente afirma DE MÁS.** Medido (RSOS 2025, 4900 resúmenes / 10
modelos): el resumen es genérico donde el cuerpo acota, presente donde el cuerpo usa pasado,
prescriptivo donde el cuerpo describe. Todo lo que saques de acá viaja con esa condición, y lo que
el paper sostenga en su cuerpo **no se puede afirmar desde esta lectura**: eso va a `hueco`.

⚠ Una vista de ocho líneas de abstract **no puede quedar indistinguible** de haber leído el paper:
ése es el falso limpio que `fuente` existe para cerrar. Si el abstract no alcanza para decir nada
del sujeto, decilo — es un resultado válido."""
"""Reading block when the paper has NO PDF on disk (#255): the abstract is the source, and it says so."""

SIN_TXT = """## Búsqueda — NO HAY ÍNDICE
⛔ **No existe `{txt}`**, así que no hay `grep` que correr sobre esta fuente. Un `grep` que **no
corrió** no es «el paper no lo dice» (D-43): si no podés confirmar algo, va a `hueco`, no a una
afirmación negativa."""
"""Search block when there is no `.txt` (#255): saying so beats emitting greps over a missing file."""


def _source_section(slug: str, bibcode: str, name: str, alias_str: str) -> str:
    '''The source block, branched by DISK TRUTH (#255).

    `fuente: abstract` (#207) was wired everywhere — schema, the harvester's disk cross-check, the
    lint category — except this last leg. For a paper with no PDF the prompt still ordered, in bold
    and with a stop sign, "read the PDF", pointed at a `.txt` that does not exist and told the
    extractor to start from the conclusions; the only warning went to **stderr**, which every pipe
    drops, and the skill tells the subagent to follow what the command *prints*. Worse than the
    silence of #241: the prompt does not omit the instruction, it orders the opposite one.

    @inv INV-144'''
    if cfg.pdf_slug(bibcode, slug):        # #305: bajo CUALQUIER slug, como el cosechador
        return f"""⛔ **Leé el PDF: `{_pdf_rel(slug, bibcode)}`.** `Read` lo rasteriza, así que **ves** la página —
ecuaciones, tablas y figuras incluidas. Extraé lo que esa fuente dice sobre **{name}**
(alias: {alias_str}), y **citá por PÁGINA del PDF**."""
    return SIN_PDF.format(pdf=_pdf_rel(slug, bibcode), bibcode=bibcode)


def _search_section(slug: str, bibcode: str, greps: str, hay_txt: bool) -> str:
    """The search block, branched by disk truth (#255).

    Emitting a dozen `grep` commands over a `.txt` that does not exist is worse than emitting
    nothing: they all come back empty, and an empty grep reads as "the paper does not say this" —
    the exact inference D-43 forbids.  @inv INV-144"""
    if not hay_txt:
        return SIN_TXT.format(txt=_txt_rel(slug, bibcode))
    return ("## Búsqueda — para UBICAR, no para citar\n"
            "Estos patrones sobre el `.txt` te dicen **en qué parte del paper** mirar; el dato lo "
            f"leés del PDF:\n\n{greps}")


def _reading_section(bibcode: str, hay_pdf: bool = True) -> str:
    """The reading-strategy section, branched by `unidad_cita` (#241) and by disk truth (#255).

    Without a PDF there is no document to walk, so the CORTO block —«open the conclusions, then go
    to the body»— names two things that do not exist. The abstract-only block already says how to
    read what there is."""
    if not hay_pdf:
        return ""
    unidad, alcance = _long_document(bibcode)
    if not unidad:
        return CORTO
    return LARGO.format(unidad=unidad, alcance=alcance or
                        "⛔ NO DECLARADO — pedilo antes de leer: sin alcance no se sabe qué parte entra")


def _lens_section(bibcode: str, sujeto: str, enfasis: str) -> str:
    """The framing of a SECOND reading of the same subject, under another lens (#239/#308).

    ⛔ #239 built the whole harvesting half —`### Lente — <énfasis>`, the `(sujeto, enfasis)`
    identity, the refusal to overwrite— and nothing could PRODUCE that JSON: `extraction_prompt`
    did not mention `enfasis` and had no flag, so the only path was writing the JSON by hand, which
    is what INV-100 forbids for the measured reason this repo already recorded (a subagent prompt
    written from memory loses the skill's rules). Same shape as #210/INV-132: a documented
    capability whose expensive half exists and that no user entry can reach.

    The second reading must also SEE the first one — that is what makes it cheap, and why `#124`
    keeps the lens-free `## Conclusiones` around."""
    if not enfasis:
        return ""
    return f"""
⛔ **Ésta es una SEGUNDA lectura del mismo sujeto, bajo la lente «{enfasis}» (#239).** La vista
anterior **no se pisa**: las dos conviven como sub-secciones de la misma `## Vista — {sujeto}`.
- Leé primero lo que ya está en `vault/wiki/papers/{bibcode}.md` (`## Vista — {sujeto}` y las
  `## Conclusiones`, que son sin lente): **no re-narres** lo que la vista anterior ya dice.
- Contestá lo que esta lente pregunta y **nada más**; si el paper no tiene nada bajo esta lente, eso
  es un resultado válido: decilo en `aporte`.
- Devolvé `"enfasis": "{enfasis}"` dentro de `vista` — sin eso, el cosechador escribe sobre la
  lectura anterior en vez de convivir con ella."""


def axes_skeleton(meta=None) -> str:
    """The `ejes` skeleton of the output JSON, DERIVED from the lens in force (#254 + #307).

    With `meta` (the theme's entry) it uses the theme's own `ejes:` when declared — the symmetric
    half of D-26, which `cfg.theme_axes` documents with its measurement.

    `CLAUDE.md` already says these bullets are the facets of this vault's objective, never a fixed
    list from memory, and the prompt wrote them as a five-key literal that never read the objective. The five hardcoded ones are the template's example lens, so every
    facet an instance declares beyond them was **never asked of any extractor** — and the view comes
    back without the key, which is indistinguishable from "somebody looked and there is nothing":
    the false clean that #188 introduced `vistas[]` to close, reappearing one level down.

    Measured on a vault whose objective declares eight facets, over 28 extractions of one star: the
    five wired ones score 28/28 and the three the instance added — `detection`, `ml`, `simulation`,
    one per thesis chapter — score 1 to 2 of 28, and those few came from extractors who went and
    read `objective.yaml` on their own initiative.

    Same family as INV-100: a rule that lives in the skill and not in the prompt falls silently at
    that boundary. Here the rule is the *instance's* objective, which makes it worse — the framework
    promises each vault that its lens defines what is searched for, and the most expensive step of
    the chain ignored it.

    Order follows the YAML, so two runs compare. An unreadable or empty lens is SAID, not degraded
    back to the old literal: same doctrine as `query_ads`, which refuses to classify with a lens it
    cannot read instead of silently falling back to an empty one (INV-80).

    @inv INV-143"""
    propios = cfg.theme_axes(meta)        # #307: la mitad simétrica de D-26
    if propios is not None:
        if not propios:
            return ('{"SIN_EJES": "el tema declara `ejes: []` — NO se piden ejes en esta lectura; '
                    'lo que el paper aporte va en `aporte` y `ground_truth`."}')
        return "{" + ",".join(f'"{k}":""' for k in propios) + "}"
    try:
        facets = cfg.as_map(cfg.as_map(cfg.load_objective().get("relevance")).get("facets"))
    except Exception:                     # objetivo ilegible: se DICE, no se inventa una lente
        facets = {}
    if not facets:
        return ('{"SIN_FACETAS": "⛔ `relevance.facets` de `vault/config/objective.yaml` no se pudo '
                'leer o vino vacia: NO inventes ejes. Frena y avisale al orquestador."}')
    return "{" + ",".join(f'"{k}":""' for k in facets) + "}"


#: #245 · cuántos métodos conocidos entran al prompt. Es un tope DECLARADO, no silencioso: en una
#: bóveda con 291 métodos, pegarlos todos ahoga el prompt, y cortar sin decirlo es el defecto que
#: #107 midió (una conclusión estructural sacada de un truncamiento que nadie declaró).
MAX_METODOS_PROMPT = 60


def known_methods(tope: int = MAX_METODOS_PROMPT) -> str:
    """The vocabulary of methods this vault already has a note for, for the extractor to reuse (#245).

    The canonical name of a method is the stem of its concept note and `aliases` is its synonym
    table — the list exists and nothing showed it to the extractor, which invents a spelling per
    paper. Measured on a real vault: 136 distinct `methods`, **121 with no destination page**, many
    of them the same method under two names.

    ⛔ It does not close the vocabulary: a method with no note is a legitimate answer (that is what
    the backlog is for). What it does is stop the avoidable divergence. With no concepts it SAYS so
    instead of emitting an empty list, which would read as «this vault knows no methods» — same
    doctrine as `axes_skeleton`'s `SIN_FACETAS`."""
    # Se leen los alias TAL COMO están escritos, no la clave normalizada: el extractor tiene que
    # ver el nombre humano (`bisector span`), que es el que va a reconocer en el paper.
    por_stem: dict = {}
    if cfg.CONCEPTS.exists():
        for nota in cfg.note_paths(cfg.CONCEPTS, "*/*.md"):
            try:
                fm = cfg.split_fm(nota.read_text(encoding="utf-8")) or {}
            except OSError:
                continue
            por_stem[nota.stem] = {str(a).strip() for a in cfg.as_list(fm.get("aliases"))
                                   if str(a).strip() and str(a).strip() != nota.stem}
    if not por_stem:
        return ("⚠ Esta bóveda todavía no tiene notas de `concepts/`: no hay vocabulario que "
                "reusar. Escribí el método como lo nombra el paper.")
    nombres = sorted(por_stem)
    recorte = nombres[:tope]
    lineas = [f"- `{stem}`" + (f" (alias: {', '.join(sorted(por_stem[stem]))})"
                               if por_stem[stem] else "")
              for stem in recorte]
    cola = (f"\n… y {len(nombres) - tope} más (tope declarado: {tope})" if len(nombres) > tope
            else "")
    return "\n".join(lineas) + cola


def build_prompt(slug: str, bibcode: str, name: str, aliases, texto: str = "",
                 out_dir: str = "", kind: str = "star", sujeto: str | None = None,
                 meta=None, enfasis: str = "", ejes_cli=None) -> str:
    """The prompt for one (paper, subject) pair.

    ⚠ `texto` is DEAD since #205 and kept only so the positional call sites do not have to move:
    it used to feed the layout detector that decided `.txt` vs PDF, and that decision no longer
    exists — the source is the PDF. Nothing in the prompt reads it, so `main` no longer loads the
    whole fulltext to hand it over (AUD-133).

    `sujeto` (#188) is the name the VIEW is filed under — the same string the paper uses in
    `stars[]` / `thesis_links[]`, which is what makes claim and reading comparable. It defaults to
    `name` and only differs for a theme, where `theme_by_slug` hands back the slug while the paper
    declares the `concept`; writing the slug there would make `reclamo_sin_vista` fire forever.

    @inv INV-134"""
    #  @inv INV-100
    pats = subject_patterns(name, aliases, kind)
    #  ⛔ Sin patrones el prompt salía con el bloque de búsqueda VACÍO bajo un encabezado que
    #  promete patrones, y el extractor concluía «no dice nada del sujeto» sin haber buscado — un
    #  falso limpio en el peor lugar. Si vuelve a pasar (un nombre que ninguna regla cubre), se
    #  **declara** en el prompt en vez de callar. Medido el 2026-08-28: `AU Mic`, `55 Cnc`,
    #  `eps Eri`, `K2-18` y `TRAPPIST-1` daban `[]`.
    if not pats:
        greps = ("  ⛔ NINGÚN patrón se pudo generar para este sujeto: buscalo A MANO en el PDF y "
                 "**decilo en `salvedades`**.\n"
                 "  ⚠ Un `grep` que no corrió NO es «el paper no lo reporta».")
    else:
        greps = "\n".join(f"  grep -niE '{_anclado(p)}' \"{_txt_rel(slug, bibcode)}\"" for p in pats)
    sujeto = sujeto or name
    tipo = "theme" if kind == "theme" else "star"
    out = (f"{out_dir.rstrip('/')}/{bibcode}.json" if out_dir else
           f"{(cfg.EXTRACCION / slug).relative_to(cfg.ROOT).as_posix()}/{bibcode}.json")
    alias_str = ", ".join(f"`{a}`" for a in [name, *(aliases or [])])
    # #254 los ejes son la lente de ESTA bóveda; #307 los del TEMA si los declara; #308 los que
    # pide una segunda lectura con otra lente, que es lo que la hace distinta de la primera.
    ejes = ("{" + ",".join(f'"{e}":""' for e in ejes_cli) + "}") if ejes_cli \
        else axes_skeleton(meta)
    metodos_conocidos = known_methods()   # #245: el vocabulario que la bóveda ya tiene
    hay_pdf = cfg.pdf_slug(bibcode, slug) is not None    # #305: la misma resolución que el cosechador
    hay_txt = (cfg.FULLTEXT / slug / f"{bibcode}.txt").exists()
    txt_nota = f"""
⛔ **El `.txt` NO es fuente.** `{_txt_rel(slug, bibcode)}` lo produce `pdftotext` y es el **índice
de búsqueda** del corpus, no material de lectura: sirve para *ubicar* dónde se menciona el sujeto,
nunca para transcribir ni para citar. Medido el 2026-08-28 sobre dos papers, uno de ellos con los
tres chequeos de calidad **en verde**: el `.txt` había perdido el radical `√` (sale como una `r`
suelta), la prima de `p′` (como `p0`), superíndices de transpuesta, y un subíndice que hacía leer
una autocovarianza como una inversa. Nada de eso se ve desde el `.txt`.
""" if (hay_pdf and hay_txt) else ""
    return f"""Sos un extractor de UNA sola fuente. Trabajás desde la raíz del repo.

{_source_section(slug, bibcode, name, alias_str)}
{txt_nota}
Esto es **una VISTA**, no «la extracción del paper» (#188): el mismo paper leído desde otro sujeto
da otra vista, y por eso el producto lleva de quién es. Va a la sección `## Vista — {sujeto}` de
`vault/wiki/papers/{bibcode}.md`. Lo que la fuente diga sobre **otros** sujetos no entra acá.
{_lens_section(bibcode, sujeto, enfasis)}

{_reading_section(bibcode, hay_pdf)}
{_search_section(slug, bibcode, greps, hay_txt)}

- Si la fuente **no dice nada** del sujeto, eso es un resultado válido y legítimo: decilo.
- Un `grep` vacío **no prueba ausencia**: el `.txt` no tiene lo que vive en tablas-imagen, figuras
  ni fórmulas. Confirmalo en el PDF antes de afirmar que no está.
{_media_note(slug, bibcode)}
## Cómo anotar cada valor
- El localizador va en el campo `linea` del JSON: {cfg.REGLA_LOCALIZADOR[len("el **localizador** es "):]}.
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

## Métodos: reusá el vocabulario que la bóveda ya tiene (#245)
Estos métodos ya tienen nota en `concepts/`. Si el paper usa uno de ellos, **escribilo con ese
nombre** (o con uno de sus alias) en `methods`; así el roll-up lo linkea en vez de dejarlo colgando.
⛔ El vocabulario **no está cerrado**: si el paper usa un método que no está en la lista, escribilo
como lo nombra el paper — eso es una respuesta legítima, no un error.

{metodos_conocidos}

## Salida
⚠ **Si te pidieron RE-leer este paper con otra lente** (#239), agregá `"enfasis": "<nombre de la
lente>"` dentro de `vista`: la lectura anterior **no se pisa**, las dos conviven como sub-secciones
de la misma `## Vista`. Sin ese pedido, no lo pongas.

Escribí el resultado en `{out}` y devolvé el mismo JSON en **un solo bloque** ```json:

{{"bibcode":"{bibcode}","vista":{{"sujeto":"{sujeto}","tipo":"{tipo}","txt":"{slug}","fuente":"pdf"}},
 "role":["fundacional"|"aplicacion"|"arbitro"],"methods":[],"thesis_links":[],"refuta":[],
 "ground_truth":[{{"que":"","valor":"","linea":"","regimen":"","segunda_mano":null}}],
 "ejes":{ejes},
 "aporte":"","hueco":"","salvedades":[],
 "abstract":"","abstract_es":"","conclusiones":"","conclusiones_es":""}}

⛔ Sin comas finales: tiene que parsear con `json.loads`. El nombre del archivo lleva el bibcode
porque varios extractores corren en paralelo y un nombre genérico se pisa **en silencio**.
`vista` va tal cual: dice de quién es esta lectura y de qué copia del `.txt` salió. La `fecha` y la
`lente` no las escribís vos — las estampa el cosechador, que las sabe con certeza.
⛔ **Las ayudas de lectura** (#124). `abstract_es` es la traducción al castellano del `## Abstract`
—la traducción va **al lado**, el original no se pisa—. `abstract`: dejalo **vacío** si la nota ya
trae la sección (viene del catálogo y es la capa auditable); llenalo, transcrito del PDF, **sólo si
la nota no la tiene** — pasa en fuentes off-ADS viejas, y el texto lo tenés a mano porque ya
abriste el PDF;
`conclusiones` es la transcripción de las conclusiones del paper y `conclusiones_es` su traducción.
Son lo que el paper afirma **sin lente**, así que sirven para leerlo "en chico" sin abrir el PDF y
para que otro sujeto lo lea después sin re-abrirlo. ⚠ Si el `.txt`/PDF es un **documento largo**
(`unidad_cita: pagina` en el frontmatter: un libro, un handbook) **dejá `conclusiones` vacío** — no
tiene esa sección y transcribir algo que no existe fabrica contenido. Vacío = no consta; el
cosechador no crea la sección.
⛔ Y la regla de uso: **son ayuda de lectura, nunca fuente de la que citar.** Si citás, citás del
original con su página.

⛔ **`ground_truth` se publica como TABLA, así que la `|` de tu prosa PARTE la fila (#240).** No
tenés que escaparla vos —el cosechador lo hace al renderizar la celda—, pero sabé que va a
aparecer escapada: `\\|` en prosa y `\\vert` dentro de `$…$`, porque en LaTeX `\\|` es la doble
barra ‖ y escapar a ciegas cambiaría la fórmula. Si transcribís las columnas de una tabla del
paper, preferí describirlas en palabras: una fila partida deja la afirmación **invisible para el
lector** aunque el lint la siga contando como verificada.

⛔ **Las `salvedades` que afirman algo DECIDIBLE sobre un archivo van ESTRUCTURADAS (#213),
porque un script las chequea.** Vocabulario cerrado, dos formas:

    {{"tipo":"txt_pierde","cadena":"ζ_{{×+×}}"}}     → el `.txt` NO contiene esa cadena
    {{"tipo":"pdf_paginas","n":17}}                 → el PDF tiene N páginas

Todo lo demás va como **string**, y la nota lo publica marcado **⚠ NO VERIFICADA — juicio del
extractor**, en su propio bloque. La razón: una salvedad sobre el **artefacto** no lleva
`[[bibcode]]` —es una afirmación sobre el archivo, no sobre el paper— así que `verify-citations` la
deja afuera **por construcción**, y ninguna red la mira. Medido: un extractor afirmó una degradación
del `.txt` que **no existía**, invocando #205 para darse autoridad, y lo cazó un duplicado
accidental de la extracción. Esa afirmación iba a entrar bajo `**Salvedades:**`, que es justo la
sección que el consumidor lee para saber **cuánto confiar** en la extracción.
⚠ La estructurada que **no resista su propio chequeo NO se publica** y el cosechador la grita con tu
nombre de archivo. Si la afirmación es decidible, estructurala: es más barata y más fuerte que la
prosa.

⛔ **`refuta` es el único campo que puede DESHACER un reclamo (#212).** El frontmatter de la nota
trae `stars[]` / `thesis_links[]` sembrados **antes** de leer: son **reclamos**, no lecturas. Si
leíste el paper entero y el sujeto que lo reclama **no tiene ningún sustento** —el caso típico es
la **polisemia**: un paper de flujos de acreción entró a un tema de ICA porque dice *«six mutually
independent components»* del tensor de tensiones—, poné ese nombre en `refuta`. Con la lista vacía
(el caso normal) no pasa nada. ⚠ `refuta` **no** es «el paper aporta poco»: eso es `aporte`. Es «el
reclamo es FALSO». Nadie borra nada por tu cuenta: el cosechador lo **registra** en la vista y te
imprime el comando de curación listo para pegar — la decisión de sacar el paper del sujeto es del
usuario, porque el paper puede ser core de OTRO sujeto.

⛔ **`fuente` dice DE QUÉ construiste la vista.** `pdf` es el caso normal. Poné **`abstract`** si el
PDF no está y sólo pudiste leer el `## Abstract` de la nota: la vista igual vale, pero una lectura
de ocho líneas no puede quedar indistinguible de haber leído el paper —y el abstract es justo donde
la fuente afirma **de más**—. El cosechador lo cruza contra el disco: declarar `pdf` sin PDF
**rechaza** la extracción entera.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug")
    ap.add_argument("bibcode")
    ap.add_argument("--theme", action="store_true", help="el slug es un tema, no una estrella")
    ap.add_argument("--out-dir", default="", help="directorio de salida (default vault/raw/extraccion/<slug> — #311: "
                         "versionado, porque una extracción no es regenerable como un `ads.json`)")
    ap.add_argument("--enfasis", default="", metavar="LENTE",
                    help="#239/#308: SEGUNDA lectura del mismo sujeto bajo otra lente. La vista "
                         "anterior no se pisa: las dos conviven como sub-secciones de la misma "
                         "`## Vista`. El prompt lo pide en el JSON y manda leer primero lo que ya "
                         "está, para no re-narrarlo.")
    ap.add_argument("--ejes", default="", metavar="E1,E2",
                    help="ejes de ESTA lectura, si son otros que los de la lente (los del tema "
                         "vía `ejes:` de themes.yaml, o los de `relevance.facets`). Van al "
                         "esqueleto del JSON: es lo que hace distinta a una segunda lente.")
    args = ap.parse_args()

    # #343 — la negativa va ANTES de imprimir nada: sin ella, `extraction_prompt.py <tema> <bib>`
    # moría con el `KeyError` de `star_by_slug`, que manda definir en `stars.yaml` un slug que
    # está bien definido en `themes.yaml`. Acá el remedio SÍ es un flag (a diferencia de
    # `fetch_ground_truth`), y el comando va completo: sin el bibcode no se copia y pega.
    remedio = (f"Corré: `python scripts/extraction_prompt.py {args.slug} {args.bibcode}"
               f"{'' if args.theme else ' --theme'}`")
    if (motivo := cfg.subject_refusal(args.slug, "theme" if args.theme else "star",
                                      "no se generó ningún prompt", remedio)) is not None:
        cfg.print_seguro(motivo)
        return 2

    if args.theme:
        name, meta = cfg.theme_by_slug(args.slug)
    else:
        name, meta = cfg.star_by_slug(args.slug)
    # AUD-133 — la precondición miraba el `.txt` y abortaba, mientras el prompt que emite dice
    # «⛔ Leé el PDF». Era una regresión de #205: se validaba el artefacto viejo y **nunca** el que
    # se lee. Hoy manda el PDF, y la ausencia del `.txt` es una degradación DECLARADA (los `grep`
    # del prompt no van a correr) en vez de un corte.
    txt_rel, pdf_rel = _txt_rel(args.slug, args.bibcode), _pdf_rel(args.slug, args.bibcode)
    hay_pdf = (cfg.ROOT / pdf_rel).exists()
    hay_txt = (cfg.ROOT / txt_rel).exists()
    nota = cfg.PAPERS / f"{args.bibcode.replace('/', '_')}.md"
    if not hay_pdf and not nota.exists():
        # #334 — sólo la SEGUNDA mitad pasa por `make_notes_cmd`: el sujeto habitual de este
        # generador es un tema, y sin `--theme` el comando no corre. ⛔ `fetch_pdf` toma el slug
        # pelado y **no tiene** `--theme`: la primera mitad ya estaba bien y no se contagia.
        cfg.print_seguro(f"⛔ no hay ni PDF (`{pdf_rel}`) ni nota (`{nota.name}`) — no hay nada que "
                         f"leer; corré `fetch_pdf.py {args.slug}` y "
                         f"`{cfg.make_notes_cmd(args.slug)}`")
        return 1
    if not hay_pdf:
        # #207: sin PDF la vista se construye del `## Abstract` y se DECLARA `fuente: abstract`.
        # No es un corte —una lectura de ocho líneas puede traer lo que la ficha necesita— pero
        # tampoco puede quedar indistinguible de haber leído el paper.
        cfg.print_seguro(f"⚠ no existe {pdf_rel} — la vista sólo puede salir del `## Abstract` de "
                         f"la nota: declarala `fuente: abstract` (#207). Para leer el paper, "
                         f"conseguí el PDF (`fetch_pdf.py {args.slug}`).", file=sys.stderr)
    if not hay_txt:
        cfg.print_seguro(f"⚠ no existe {txt_rel} — los `grep` del prompt NO van a correr (el `.txt` "
                         f"es el índice de búsqueda, no la fuente); un grep que no corrió no es "
                         f"«el paper no lo dice» → `extract_fulltext.py {args.slug}`",
                         file=sys.stderr)
    # #188 · el sujeto de la VISTA es el nombre con el que el paper declara la entidad: para un
    # tema es el `concept` (lo que va en `thesis_links`), no el slug que devuelve `theme_by_slug`.
    sujeto = (meta.get("concept") or args.slug) if args.theme else name
    ejes_cli = [e.strip() for e in args.ejes.split(",") if e.strip()] or None
    # #308 — la decisión de re-leer bajo la MISMA clave es del usuario, con el mismo criterio con
    # que `harvest_views` rehúsa pisar: si `(sujeto, enfasis)` ya tiene prosa escrita, se rehúsa.
    if args.enfasis and nota.exists():
        import lib_config as _c
        _fm = _c.split_fm(nota.read_text(encoding="utf-8"))
        if any(str(v.get("sujeto")) == str(sujeto) and str(v.get("enfasis") or "") == args.enfasis
               for v in _c.as_list(_fm.get("vistas")) if isinstance(v, dict)):
            cfg.print_seguro(f"⛔ `{args.bibcode}` ya tiene una vista de «{sujeto}» bajo la lente "
                             f"«{args.enfasis}»: re-leer bajo la MISMA clave pisaría esa lectura. "
                             f"Usá otro `--enfasis`, o borrá la vista a mano si es lo que querés.")
            return 1
    cfg.print_seguro(build_prompt(args.slug, args.bibcode, name, cfg.as_list(meta.get("aliases")),
                                  "", args.out_dir, "theme" if args.theme else "star", sujeto,
                                  meta=meta, enfasis=args.enfasis, ejes_cli=ejes_cli))
    return 0


if __name__ == "__main__":
    cfg.stdout_tolerante()
    cfg.cli_exit(main)
