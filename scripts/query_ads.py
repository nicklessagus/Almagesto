"""Consulta NASA ADS por estrella → metadata de papers + clasificación de relevancia.

Uso:
    python scripts/query_ads.py <slug> [--rows N] [--no-chain] [--no-glyph] [--sweep]
    python scripts/query_ads.py <slug> --theme            # tema (query cruda de themes.yaml)
    python scripts/query_ads.py <slug> --extra-only       # sólo los bibcodes de extra_core (tema mixto)
    python scripts/query_ads.py <slug> --dry-run          # re-clasificar en memoria, sin red ni escritura
    python scripts/query_ads.py --probe "<query>"         # previsualizar el corte core/no-core, sin bajar

Escribe build/<slug>/ads.json con la lista de registros (bibcode, título, autores,
año, abstract, arxiv_id, doctype, citation_count, facets, relevant, why_excluded —el motivo real
de exclusión si es no-core; lo consume el apéndice "Excluidos" de make_notes—, via) y, si la query directa
quedó truncada (numFound > --rows), la marca `truncated: {num_found, rows, recent}` que el lint
surface como corpus incompleto (si no truncó, `truncated: null`).

**Segunda pasada por fecha al truncar (#79):** el `sort` viaja en la request, así que cuando ADS
corta se queda con el top por CITAS — y las citas se acumulan con la edad, o sea que lo que queda
afuera es sistemáticamente lo reciente (un árbitro nuevo tiene pocas citas por construcción). Ningún
re-ordenamiento local lo arregla: si truncó, se vuelve a preguntar la MISMA query ordenada por fecha
(`recent_pass`) y lo que la primera no trajo entra con `via: query:recent`. Corre antes de
extra_core/glifo/chaining, así que lo recuperado siembra también el grafo de citas. La marca
`truncated` NO se levanta —sigue faltando el medio del universo—: se le agrega `recent`, cuántos
rescató la pasada.

Escribe TAMBIÉN el registro de búsqueda VERSIONADO del sujeto, `vault/config/registro/<slug>.yaml`
(clave `busquedas`, lista — una entrada por corrida, D-28: fecha, query efectiva, rows, conteos, truncado, versión del framework y la
**lente** con la que se clasificó) — #64: el ads.json es scratch regenerable, pero saber sobre qué
universo afirma una ficha y con qué filtro se recortó tiene que viajar con la bóveda. No se escribe
en los modos que no consultan un sujeto (`--probe`) ni en los que no clasifican de nuevo
(`--dry-run`), que retornan antes.

Usa la API REST de ADS directamente (control total de campos y filas). Rate: ~5000/día.
La query por estrella se arma con `title:`/`abs:` sobre nombre+alias (ver `build_query`; `object:`
no es campo válido en la API Solr de ADS). Para temas, query Solr cruda de `themes.yaml`.

Tras la query directa hace **citation chaining** (snowballing): pide a ADS `references()` y
`citations()` de los papers core encontrados, **ancladas al sujeto** server-side —para ESTRELLAS el
`full:"nombre"` OR alias; para TEMAS la propia query del tema— (sin ese ancla el grafo devuelve los
mega-citados genéricos del área, no papers del sujeto), clasifica los candidatos con el mismo
`relevance.facets` y agrega los que resulten core (dedup por bibcode; provenance en el campo
`via`: `query` | `chain:references` | `chain:citations` | `manual`). Recupera papers que la query por
título/abstract pierde (p. ej. surveys que tabulan la estrella sin nombrarla en el abstract).
Sólo entran los core: los no-core encadenados no se agregan (inundarían el apéndice "Excluidos").
Desactivar con --no-chain. `--probe` no encadena (es sólo preview; lista TODO el core del corte).

**Compuerta de triage del chaining (#38, estrellas):** el chaining PROMOVÍA a core todo lo que el
grafo traía y matcheaba la lente, pero la lente clasifica **tema** y lo que hay que filtrar acá es
**pertinencia al sujeto** (medido: 18% de precisión en los core nuevos del grafo). Ahora entra solo
el que lleva **el sujeto en el título** (1 falso positivo en 310) y el resto queda como
**candidato** —clave `candidates` de `ads.json`, NO se baja— para el juicio del LLM
(`scripts/triage.py` + paso 2c del skill ingest-star). Las decisiones persisten:
aceptado → `extra_core`; descartado → `decisiones` de `vault/config/registro/<slug>.yaml` (#51:
versionado, viaja en git; no se re-propone). En **temas** no
aplica (la query *es* la definición del tema). **No se puede desactivar** (D-48): el flag
`--no-triage` se eliminó porque permitía que un candidato ya descartado —con su motivo,
persistido en el registro— volviera a entrar en silencio.

**Curación manual persistente:** `extra_core: [bibcode, …]` en la entrada de `stars.yaml`/`themes.yaml`
lista papers que el clasificador perdió. Es un **override del clasificador** (#39): el que ADS no
devolvió se trae por bibcode y el que **sí** devolvió pero quedó no-core se **rescata en el lugar**
(`relevant: true`, `via: manual`) — antes sólo se agregaban los ausentes, así que declarar el caso
más común de la curación (paper del sujeto que la lente descarta) no hacía nada. Vive en config
(se commitea) → sobrevive al re-run, a diferencia de editar `build/` (scratch). Se mergea **antes**
del rescate por glifo y del chaining (#42): un paper que el usuario ya aceptó a `extra_core` está en
`recs` cuando el chaining calcula su dedup — no vuelve a la cola de triage (la persistencia de la
compuerta vale para los dos lados de la decisión) — y además siembra el grafo de citas.

**`--sweep` (barrido full-text, paso 2b de ingest-star):** corre `full:` sobre nombre+aliases con
TODAS las variantes de espaciado y lista SÓLO los core que `build/<slug>/ads.json` no tiene — los
candidatos a `extra_core`. Preview como `--probe` (no baja nada ni escribe build/). Ver sweep_star.

**`--dry-run` (delta de re-clasificación, #40):** re-clasifica **en memoria** los `ads.json` ya
bajados con la regla vigente de `objective.yaml` y reporta el delta —core antes/después, los que
**salen** del core separando *con extracción LLM* (la decisión real) de *stubs*, y los que **entran**
sin nota por vía— sin consultar ADS ni escribir nada. Es el paso 2 del sub-modo D de `maintain`,
que antes había que hacer con scripts descartables.

**Rescate por glifo (#28):** para sujetos con nombre **Bayer** (letra griega + constelación) hay un
agujero de recall sistemático — ADS unifica `epsilon`/`eps`/`ε`, pero **descarta** los lookalikes
`ϵ` (U+03F5) y `∊` (U+220A, el glifo de ApJ/AJ/MNRAS), así que esos papers quedan indexados sólo por
la constelación y `title:"epsilon Eridani"` no los ve nunca (medido en ε Eri: **121 core perdidos**,
incluido el descubrimiento). Tras la query directa se trae el superset de la constelación y se filtra
**client-side** por el glifo pegado al nombre (`via: glyph`); corre antes del chaining, así lo
recuperado siembra el grafo. Sólo aplica si el nombre/alias es Bayer; se desactiva con `--no-glyph`.
Si el superset supera `--rows` el corte top-por-citas pasa **antes** del filtro por glifo — justo
donde vive la señal—: el truncamiento queda marcado aparte (`truncated_glyph` en ads.json, distinto
del `truncated` de la query directa) y el lint lo surface como rescate incompleto (#43).

**Cero espurio (#27):** la query DIRECTA de un sujeto corre con `expect_hits` — ADS devuelve
intermitentemente `numFound: 0` con HTTP 200; se reintenta con el mismo backoff y, si persiste, la
corrida **falla** (`EmptyResultError`, exit ≠ 0) en vez de persistir un `ads.json` vacío con exit 0
(que además pisaría el bueno de un re-ingest). Los ceros legítimos —chaining, `--sweep`, `--probe`,
`--extra-only`— no se tocan.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time

import requests

import lib_config as cfg

API = "https://api.adsabs.harvard.edu/v1/search/query"
FIELDS = ("bibcode,title,author,year,pubdate,abstract,identifier,doctype,"
          "citation_count,bibstem,doi,keyword")
# Lente astro del BUSCADOR (fq de Solr): acota el universo de toda query de DESCUBRIMIENTO.
# No se aplica cuando el universo ya lo fijó el usuario con una lista de bibcodes — ver
# `fetch_bibcodes` y el parámetro `fq` de `query_ads` (#68).
ASTRO_FQ = "database:astronomy"


# Normalización de campos de CURACIÓN MANUAL: vive en `lib_config` desde que el diff de lente
# offline (D-49) la necesita también desde el lint, que no puede importar este módulo (arrastraría
# `requests`). Se reexporta con el nombre viejo para no tocar los call-sites.
_listify_curado = cfg.listify_curado


# Clasificación de relevancia: se LEE de vault/config/objective.yaml (el archivo que define
# el objetivo de la bóveda → qué paper es "core"). No hardcodear acá: editar el YAML.
_OBJ = cfg.load_objective()
# `cfg.as_map`, no `or {}`: un `relevance:` escalar es truthy y el `or` no dispara — el `.get`
# siguiente reventaba con `AttributeError` a nivel de MÓDULO, llevándose puesto el import entero,
# tres líneas antes de llegar al RuntimeError con instrucciones que ya existe para este caso (R2).
_REL = cfg.as_map(_OBJ.get("relevance"))
FACET_PATTERNS = {
    # ídem: `facets` es un MAPA faceta→regex; escribirlo como lista (copiando los nombres de la
    # prosa del skill) revienta `.items()` con `AttributeError` en vez de caer en el RuntimeError
    # de abajo (R3). `as_map` de una lista da `{}` → FACET_PATTERNS queda vacío → cae ahí, prolijo.
    name: re.compile(pat, re.I)
    for name, pat in cfg.as_map(_REL.get("facets")).items()
}
NOISE_DOCTYPES = set(_listify_curado(_REL.get("noise_doctypes"), "relevance.noise_doctypes"))
# `objective_error() is None` = el archivo se leyó bien y GENUINAMENTE no declara facetas. Cuando
# el YAML está roto, `load_objective` degrada a `{}` y `FACET_PATTERNS` queda vacío por la MISMA
# vía: sin esta condición el import moría acusando "no define relevance.facets" sobre un archivo
# que sí las define y sólo no parsea — un mensaje falso que manda a completar lo que ya está
# escrito. Ese caso lo atiende `main()`, con el motivo real (D-6).
if not FACET_PATTERNS and cfg.objective_error() is None:
    raise RuntimeError(
        "vault/config/objective.yaml no define relevance.facets (el clasificador de papers core). "
        "Completalo antes de consultar ADS."
    )

# La regla de COMBINACIÓN vive en `lib_config` (es lógica de la lente, no de ADS): la necesitan
# tanto el clasificador de acá como el diff de lente offline del lint, que no puede importar este
# módulo sin arrastrar `requests`. Se reexporta con el nombre de siempre.
combination_rule = cfg.combination_rule


REQUIRE_FACETS, MIN_FACETS = combination_rule(_REL, FACET_PATTERNS)


def exclusion_reason(facets: list[str], doctype: str) -> str | None:
    """Motivo por el que un paper queda FUERA del core (None = es core). ÚNICA implementación de
    la regla de relevancia: `classify` deriva su booleano de acá y `query_ads` persiste el motivo
    por registro en ads.json (`why_excluded`), del que lo lee el apéndice "Excluidos por el
    filtro" (make_notes). Sin esto, la dicotomía vieja "sin tópico"/doctype etiquetaba con un
    motivo FALSO (`doctype: article`) a los excluidos por la regla de combinación (#15) —
    require/min_facets con facetas matcheadas y doctype limpio (#30). Precedencia: sin tópico →
    doctype ruido → require → min_facets (las dos primeras preservan los rótulos históricos)."""
    if not facets:
        return "sin tópico"
    if doctype in NOISE_DOCTYPES:
        return f"doctype: {doctype}"
    missing = [t for t in REQUIRE_FACETS if t not in facets]
    if missing:
        return f"sin faceta obligatoria ({', '.join(missing)}) — relevance.require"
    if len(facets) < MIN_FACETS:
        return f"sólo {len(facets)} faceta(s), min_facets={MIN_FACETS}"
    return None


def classify(rec: dict) -> tuple[list[str], bool]:
    """Devuelve (facets, relevant). Relevante ⟺ `exclusion_reason` no encuentra motivo de
    exclusión (≥ MIN_FACETS facetas, TODAS las de REQUIRE_FACETS y doctype no-ruido; con los
    defaults min_facets=1, require=[] es el histórico ≥1 faceta cualquiera)."""
    # @inv INV-24
    text = " ".join(filter(None, [
        " ".join(cfg.as_list(rec.get("title"))),
        rec.get("abstract", "") or "",
        " ".join(cfg.as_list(rec.get("keyword"))),
    ])).lower()
    facets = [t for t, pat in FACET_PATTERNS.items() if pat.search(text)]
    return facets, exclusion_reason(facets, rec.get("doctype", "")) is None


def extract_arxiv(identifiers: list[str]) -> str | None:
    for ident in identifiers or []:
        m = re.match(r"arXiv:(\S+)", ident, re.I)
        if m:
            return m.group(1)
    return None


# Designación de catálogo <acrónimo alfabético 1-4><número…> donde el espacio es COSMÉTICO: los
# papers escriben "HD 40307" o "HD40307" indistintamente y ADS los tokeniza distinto en title:/abs:
# (dos tokens vs uno) → una frase no matchea la otra. Guard de patrón para NO expandir nombres propios
# ("tau Ceti"), designaciones numéricas ("51 Peg", el espacio separa tokens con sentido) ni variables
# con sufijo ("V889 Her"): sólo entra <letras><dígito+resto> que termina en el número.
_CATALOG_DESIG = re.compile(r"^([A-Za-z]{2,4})\s*(\d[\w.+-]*)$")


def name_variants(n: str) -> list[str]:
    """Variantes de espaciado de UNA designación de catálogo: 'HD 40307' → ['HD 40307', 'HD40307']
    (y 'HD40307' → lo mismo). Cualquier nombre que no matchee el guard se devuelve tal cual, sin tocar."""
    n = n.strip()
    m = _CATALOG_DESIG.match(n)
    if not m:
        return [n]
    prefix, rest = m.group(1), m.group(2)
    return [f"{prefix} {rest}", f"{prefix}{rest}"]   # con espacio y sin espacio


def expand_variants(names: list[str]) -> list[str]:
    """Nombre + alias con sus variantes de espaciado, deduplicados en orden."""
    variants: list[str] = []
    for n in names:
        for v in name_variants(n):
            if v not in variants:      # dedup: alias ya listado en ambas formas no duplica cláusulas
                variants.append(v)
    return variants


def build_query(names: list[str]) -> str:
    """OR del nombre y alias sobre título y abstract (papers que discuten la estrella, no que la citan
    de pasada). Para designaciones de catálogo expande las **variantes de espaciado** (HD 40307 ↔
    HD40307) porque ADS las indexa distinto y los papers usan ambas formas. `object:` no es campo
    válido en la API Solr de ADS."""
    clauses = []
    for v in expand_variants(names):
        clauses.append(f'title:"{v}"')
        clauses.append(f'abs:"{v}"')
    return " OR ".join(clauses)


# ── rescate por glifo (#28) ──────────────────────────────────────────────────
# Los nombres Bayer se escriben con letra griega y la literatura usa lookalikes Unicode que ADS
# **no** unifica: `ε` (U+03B5) sí se normaliza con `epsilon`/`eps`, pero `ϵ` (U+03F5) y `∊`
# (U+220A —el glifo de ApJ/AJ/MNRAS—) se los come el tokenizer, así que "Evidence for a Long-Period
# Planet Orbiting ∊ Eridani" queda indexado sólo como "Eridani" y `title:"epsilon Eridani"` NO lo
# matchea nunca. Medido en ε Eri: 121 core perdidos por la query canónica, incluido el paper de
# descubrimiento. Como el carácter se DESCARTA (no es que falte la variante), agregar grafías a
# expand_variants no alcanza: hay que traer el superset de la constelación y filtrar client-side
# por el glifo, que es determinista y barato.
_GREEK = {   # letra → (grafías ASCII: nombre + abreviatura Bayer, glifo canónico, LOOKALIKES)
    # El glifo canónico ADS lo unifica con la grafía ASCII (verificado: ε/epsilon/eps → mismo
    # numFound); los lookalikes NO. Sin lookalikes conocidos no hay agujero → no se gasta la query
    # del superset (el rescate corre sólo para las letras de la última columna).
    "alpha":   (("alpha", "alf", "alp"), "α", "ⲁ"),
    "beta":    (("beta", "bet"), "β", "ϐ"),
    "gamma":   (("gamma", "gam"), "γ", "ɣ"),
    "delta":   (("delta", "del"), "δ", "ẟ"),
    "epsilon": (("epsilon", "eps"), "ε", "ϵ∊ɛ"),
    "zeta":    (("zeta", "zet"), "ζ", ""),
    "eta":     (("eta",), "η", ""),
    "theta":   (("theta", "tet", "the"), "θ", "ϑ"),
    "iota":    (("iota", "iot"), "ι", ""),
    "kappa":   (("kappa", "kap"), "κ", "ϰ"),
    "lambda":  (("lambda", "lam"), "λ", ""),
    "mu":      (("mu",), "μ", "µ"),
    "nu":      (("nu",), "ν", ""),
    "xi":      (("xi", "ksi"), "ξ", ""),
    "omicron": (("omicron", "omi"), "ο", ""),
    "pi":      (("pi",), "π", "ϖ"),
    "rho":     (("rho",), "ρ", "ϱ"),
    "sigma":   (("sigma", "sig"), "σ", "ςϲ"),
    "tau":     (("tau",), "τ", ""),
    "upsilon": (("upsilon", "ups"), "υ", "ϒ"),
    "phi":     (("phi",), "φ", "ϕ"),
    "chi":     (("chi",), "χ", ""),
    "psi":     (("psi",), "ψ", ""),
    "omega":   (("omega", "ome"), "ω", ""),
}
_LETTER_BY_TOKEN = {tok: letter for letter, (toks, *_) in _GREEK.items() for tok in toks}
_LETTER_BY_TOKEN.update({g: letter for letter, (_, canon, look) in _GREEK.items()
                         for g in canon + look})
_SPACE = r"[\s\u00a0]"                    # los papers separan con espacio normal o NBSP
_BAYER = re.compile(rf"^(\S+){_SPACE}+([A-Za-z]{{2,}})$")   # "<letra> <constelación>"


def greek_targets(names: list[str]) -> dict[str, set[str]]:
    """Nombres Bayer del sujeto → {letra canónica: {constelaciones}}, SÓLO para las letras con
    lookalikes conocidos (las otras no tienen agujero: ADS unifica su glifo canónico con la grafía
    ASCII → no se gasta la query del superset). 'eps Eridani' + 'ε Eri' → {'epsilon': {'Eridani',
    'Eri'}}; 'tau Ceti' → {} (τ no tiene lookalike). Los nombres no-Bayer (HD 22049, AU Mic) no aportan."""
    out: dict[str, set[str]] = {}
    for n in names:
        m = _BAYER.match(n.strip())
        if not m:
            continue
        letter = _LETTER_BY_TOKEN.get(m.group(1).lower().rstrip("."))
        if letter and _GREEK[letter][2]:
            out.setdefault(letter, set()).add(m.group(2))
    return out


def glyph_pattern(letter: str, consts: set[str]) -> re.Pattern:
    """Regex del filtro client-side: un lookalike de `letter` pegado a la constelación
    (`∊ Eridani`, `ϵEri`). Letra-específica: en el superset de 'Eridani' no se cuela `τ Eri`."""
    glyphs = re.escape(_GREEK[letter][1] + _GREEK[letter][2])
    alt = "|".join(re.escape(c) for c in sorted(consts, key=len, reverse=True))
    return re.compile(rf"[{glyphs}]{_SPACE}*(?:{alt})\b")


def glyph_rescue(names: list[str], rows: int, meta: dict | None = None) -> list[dict]:
    """Recupera los papers que nombran al sujeto con un lookalike Unicode (#28). Por cada letra
    Bayer detectada trae el superset de la constelación (`title:`/`abs:`, degradado y ruidoso: 2342
    hits para 'Eridani') y se queda con los que contienen el glifo pegado a la constelación en
    título/abstract. Devuelve TODOS los que pasan el filtro, clasificados y con `via: glyph`;
    el caller filtra core + dedup.

    Si el superset supera `rows`, el corte top-por-citas pasa ANTES del filtro por glifo — y los
    papers que escriben `∊ Eri` no son necesariamente los más citados: el rescate queda INCOMPLETO,
    sin forma de saber cuánto quedó en la cola (#43). Cada truncamiento se registra en `meta`
    (`truncated_glyph`: lista de {letter, constellations, num_found, rows}) para que el caller lo
    persista en ads.json y el lint lo surface. El warning genérico de `query_ads` se silencia
    (quiet_truncate): hablaría de la marca de la query DIRECTA, que acá no se llena — el aviso
    mentiría (visto en la primera corrida real: warning en stdout, `truncated: null` en disco)."""
    out = []
    truncs = []
    for letter, consts in greek_targets(names).items():
    #  @inv INV-52
        q = " OR ".join(f'title:"{c}" OR abs:"{c}"' for c in sorted(consts))
        pat = glyph_pattern(letter, consts)
        qm: dict = {}
        for r in query_ads(q, rows=rows, quiet_truncate=True, meta=qm):
            text = f"{r.get('title') or ''} {r.get('abstract') or ''}"
            if pat.search(text):
                r["via"] = "glyph"
                out.append(r)
        if qm.get("truncated"):
            truncs.append({"letter": letter, "constellations": sorted(consts),
                           "num_found": qm["num_found"], "rows": qm["rows"]})
        time.sleep(1.0)
    if meta is not None:
        meta["truncated_glyph"] = truncs
    return out


def build_fulltext_filter(names: list[str]) -> str:
    """OR de `full:` sobre nombre+alias (y variantes de espaciado): papers cuyo TEXTO menciona la
    estrella aunque el título/abstract no (surveys que la tabulan). Ancla el chaining al sujeto."""
    return " OR ".join(f'full:"{v}"' for v in expand_variants(names))


RETRY_STATUS = (429, 500, 502, 503, 504)   # rate-limit / errores transitorios de ADS
RETRY_WAITS_S = (5, 15, 30)                # backoff entre reintentos


class EmptyResultError(RuntimeError):
    """La query que DEBE traer resultados volvió en 0 tras todos los reintentos (#27).

    ADS devuelve intermitentemente `numFound: 0` con HTTP 200 (medido ~2/6 corridas sobre la misma
    query): el status no distingue el cero espurio del legítimo, así que sin esto la cadena
    persistía un corpus vacío y salía con exit 0 (peor: pisaba un `ads.json` bueno). Los callers de
    la query DIRECTA de estrella/tema pasan `expect_hits=True`; el chaining, `--sweep`, `--probe` y
    `fetch_bibcodes` no (un cero ahí es un resultado válido)."""


# Órdenes que se le piden a ADS. Sólo actúan al truncar (ver `sort` en query_ads).
CITES_SORT = "citation_count desc"     # el histórico: top por citas
RECENT_SORT = "date desc"              # la segunda pasada de #79: la cola reciente


def query_ads(q: str, rows: int = 2000, quiet_truncate: bool = False,
              meta: dict | None = None, expect_hits: bool = False,
              fq: str | None = ASTRO_FQ, sort: str = CITES_SORT) -> list[dict]:
    """Corre una query Solr `q` ya armada contra ADS y devuelve registros clasificados.
    Para estrellas, armar `q` con build_query(names); para temas, usar la query cruda del theme.
    Reintenta con backoff ante 429/5xx y avisa si el resultado quedó truncado (numFound > rows;
    `quiet_truncate` lo silencia — en el chaining el truncado a top-por-citas es por diseño).

    `expect_hits=True` (sólo la query directa de un sujeto): trata `numFound == 0` como sospechoso
    —el cero espurio con HTTP 200 de #27— y lo reintenta con el mismo backoff; si persiste, levanta
    `EmptyResultError` en vez de devolver una lista vacía, para que la cadena aborte en vez de
    persistir un corpus vacío con exit 0.

    Si se pasa `meta` (dict mutable), se rellena con `num_found`/`rows`/`truncated` de ESTA corrida
    — así el caller persiste la marca de truncamiento (`build/<slug>/ads.json`) para que el lint la
    surface como backlog en vez de que el aviso muera en el stdout (#17). Se mantiene el tipo de
    retorno (lista) para no tocar al resto de los callers.

    `sort` es el orden que se le pide a ADS y sólo importa cuando la query TRUNCA (`numFound >
    rows`): ahí decide qué mitad del universo vuelve. El default `CITES_SORT` es el histórico; la
    segunda pasada de `recent_pass` pide `RECENT_SORT` para recuperar la cola que ese orden esconde
    (#79). Es server-side: no hay forma de arreglarlo re-ordenando lo que ya volvió.

    `fq` es la **lente astro** (`ASTRO_FQ`) y es el default correcto para toda query de
    **descubrimiento** (directa, chaining, glifo, sweep, probe): ahí filtrar lo no-astro es el
    punto. `fq=None` la apaga, y es lo que corresponde cuando el universo de búsqueda ya lo fijó el
    usuario —una lista explícita de bibcodes— porque entonces el filtro no puede sacar ruido, sólo
    sacar de más (#68)."""
    token = cfg.get_ads_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": q, "fl": FIELDS, "rows": rows, "sort": sort}
    if fq:
        params["fq"] = fq
    for wait in (*RETRY_WAITS_S, None):
        resp = requests.get(API, headers=headers, params=params, timeout=60)
        if resp.status_code in RETRY_STATUS and wait is not None:
            cfg.print_seguro(f"  ADS HTTP {resp.status_code} — reintento en {wait} s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        try:
            response = resp.json()["response"]
            docs = response["docs"]
        except (ValueError, KeyError) as exc:   # cuerpo de error con 200 / formato inesperado
            raise RuntimeError(
                f"Respuesta inesperada de ADS (sin response.docs): {resp.text[:200]}") from exc
        num_found = response.get("numFound", len(docs))
        if expect_hits and num_found == 0 and wait is not None:
            cfg.print_seguro(f"  ADS devolvió 0 resultados con HTTP 200 (cero espurio) — reintento en {wait} s")
            time.sleep(wait)
            continue
        break
    if expect_hits and num_found == 0:
        raise EmptyResultError(
            "ADS devolvió 0 resultados (HTTP 200) en todos los reintentos para la query directa:\n"
            f"  {q}\n"
            "Si el sujeto existe en ADS es el cero espurio de #27 (intermitente): re-corré, la "
            "cadena es idempotente. Si se repite, revisá el nombre/alias del sujeto en "
            "vault/config/stars.yaml (`ads_object`, `aliases`) o la `query` en themes.yaml.")
    truncated = num_found > rows
    if meta is not None:
        meta.update(num_found=num_found, rows=rows, truncated=truncated)
    if truncated and not quiet_truncate:
        # la coletilla sólo vale si alguien PERSISTE la marca: con `meta=None` (--sweep, --probe)
        # el aviso prometía un backlog que nadie escribe (mismo defecto que #43 arregló en el glifo).
        marca = " (queda marcado en ads.json → lint)" if meta is not None else \
                " (esta query NO deja marca en ads.json: el corte no queda registrado)"
        cfg.print_seguro(f"  ⚠ truncado: ADS reporta {num_found} resultados y sólo se trajeron {rows} "
              f"(top por citas) — subí --rows para cubrir todo{marca}")
    return [to_record(d) for d in docs]


def recent_pass(q: str, rows: int, known: set[str]) -> list[dict]:
    """Segunda pasada de la query directa ordenada por FECHA, para cuando la primera truncó (#79).

    Con `numFound > rows` ADS devuelve el top por citas y **corta el resto**. Ese corte no es
    neutral: las citas se acumulan con la edad, así que lo que queda afuera es sistemáticamente lo
    reciente — y un árbitro nuevo (el reanálisis que resuelve una tensión, el paper de este año que
    revisa la señal) tiene pocas citas por construcción. Como el `sort` viaja en la request, ningún
    re-ordenamiento local lo arregla: hay que volver a preguntar.

    Misma `q` y mismo `rows`, sólo cambia el orden; se devuelven los registros que la primera pasada
    no trajo (dedup contra `known`, que se actualiza in situ), marcados `via: query:recent` para que
    la provenance diga por qué entraron. No filtra por core: es la misma query, otra página — los
    no-core alimentan el apéndice "Excluidos" igual que los de la primera.

    Sigue siendo un corpus incompleto (faltan los del medio): la marca `truncated` NO se levanta,
    se le agrega cuántos rescató esta pasada.

    Corre con `expect_hits`: es **la misma query** que acaba de reportar `numFound > rows`, así que
    un cero acá es imposible como resultado — es el cero espurio de ADS (#27). Sin esa guarda volvía
    `[]` en silencio y la marca quedaba en `recent: 0`, que el lint lee como "la cola reciente ya
    está cubierta": afirmar de más justo donde #57 dice que no saber es mejor."""
    time.sleep(1.0)          # cortesía entre requests, como el chaining y el rescate por glifo
    out = []
    for r in query_ads(q, rows=rows, quiet_truncate=True, sort=RECENT_SORT, expect_hits=True):
        b = r.get("bibcode")
        if b and b not in known:
            known.add(b)
            r["via"] = "query:recent"
            out.append(r)
    return out


CHAIN_CHUNK = 40   # bibcodes por sub-query encadenada (mantiene la URL corta)


def chain_candidates(core_bibcodes: list[str], rows: int, subject_filter: str) -> list[dict]:
    """Citation chaining (snowballing) sobre el grafo de citas de ADS: `references()` (hacia atrás,
    qué citan los core) y `citations()` (hacia adelante, quién los cita). Un paper clave que se le
    escapó a la query directa casi seguro cita o es citado por alguno que sí entró.

    `subject_filter` (obligatorio) ancla cada sub-query al SUJETO server-side — para estrellas, el
    `full:` de nombre+alias (`build_fulltext_filter`). Sin él, el grafo de citas devuelve los
    mega-citados genéricos del área (Gaia, métodos, catálogos): matchean las facetas de
    `relevance.facets` pero no hablan del sujeto (medido: 31/31 falsos positivos en tau Ceti).

    Devuelve TODOS los candidatos clasificados y marcados con `via`; el caller filtra core + dedup.
    Cada sub-query trae el top `rows` por citas (truncado por diseño: ronda de recall, no censo)."""
    out = []
    for op in ("references", "citations"):
        for i in range(0, len(core_bibcodes), CHAIN_CHUNK):
            chunk = core_bibcodes[i:i + CHAIN_CHUNK]
            inner = " OR ".join(f'bibcode:"{b}"' for b in chunk)
            hits = query_ads(f"{op}({inner}) AND ({subject_filter})", rows=rows, quiet_truncate=True)
            for h in hits:
                h["via"] = f"chain:{op}"
            out += hits
            time.sleep(1.0)   # cortesía entre sub-queries
    return out


# ── compuerta de triage del chaining (#38) ───────────────────────────────────
# El chaining PROMOVÍA a core todo lo que el grafo traía y matcheaba la lente. Pero la lente
# clasifica TEMA y lo que hay que filtrar acá es PERTINENCIA AL SUJETO: anclado a "menciona al
# sujeto en el fulltext", el grafo trae cualquier paper del área que tabule la estrella una vez.
# Medido (4 estrellas, con `require: [rv]` ya declarada): de 378 core nuevos, 368 vinieron del
# chaining y sólo el 18% era pertinente. Y no es una propiedad sintáctica — la densidad de mención
# sale INVERTIDA (los ruidosos nombran al sujeto 27 veces de mediana; los valiosos, 2) — así que
# el juicio no se aproxima con una regex: se le hace lugar en la cadena.
# Nivel 0 (entra solo): sujeto en el TÍTULO — precisión medida de 1 falso positivo en 310.
# Nivel 1 (juicio del LLM, skill ingest-star paso 2c): el resto queda como CANDIDATO en ads.json,
# sin bajarse; `scripts/triage.py` lo lista y persiste las decisiones.


def _variant_hit(low: str, var: str) -> bool:
    """`var` aparece en `low` sin que un dígito extienda su número de catálogo (INV-72)."""
    i = low.find(var)
    while i != -1:
        fin = i + len(var)
        if not (var[-1:].isdigit() and fin < len(low) and low[fin].isdigit()):
    #  @inv INV-72
            return True
        i = low.find(var, i + 1)
    return False


def subject_in_title(title: str | None, names: list[str]) -> bool:
    """¿El sujeto está en el título? Auto-aceptación del nivel 0: cubre las grafías de catálogo
    (HD 22049 ↔ HD22049) y los lookalikes de nombre Bayer (∊ Eridani ≡ eps Eridani, #28)."""
    raw = " ".join((title or "").split())
    low = raw.lower()
    # Containment pelado matchea `GJ 71` dentro de `GJ 710`, que es OTRA estrella — y como esto es
    # la auto-aceptación de nivel 0, el match espurio mete el paper al corpus ajeno sin que nadie
    # lo juzgue. El corte es el DÍGITO: en una designación de catálogo un número más largo es otro
    # objeto. La continuación alfabética sigue valiendo (`tau Cet` ↔ `tau Ceti`), que es como están
    # escritos los alias Bayer.
    if any(_variant_hit(low, v.lower()) for v in expand_variants(names)):
    #  @inv INV-50
        return True
    return any(glyph_pattern(letter, consts).search(raw)
               for letter, consts in greek_targets(names).items())


def load_triage(slug: str) -> set[str]:
    """Bibcodes ya DESCARTADOS en un triage previo — no se re-proponen en el próximo refresh (si no,
    cada re-run vuelve a pedir el mismo juicio sobre el mismo ruido). Salen del registro VERSIONADO
    (`vault/config/registro/<slug>.yaml`, #51): antes el juicio vivía en scratch gitignored y se
    perdía al clonar o limpiar (el `build/<slug>/triage.json` pre-1.9.0 ya NO se lee — se migra con
    `triage.py --migrate` y el lint lo bloquea mientras exista).

    **Sólo el carril del chaining** (#81): un rechazo de *fuente declarada* de un tema off-ADS vive
    en las mismas `decisiones` y no tiene nada que ver con los candidatos del grafo de citas."""
    # @inv INV-49
    return {b for b, d in cfg.load_decisiones(slug).items()
            if d.get("decision") == "descartado" and cfg.es_del_carril(d, "chaining")}


def excluidos_del_sujeto(slug: str) -> dict:
    """Papers que el usuario declaró **fuera de ESTE sujeto**: `{bibcode: motivo}` (#112).

    POR QUÉ EXISTE. `extra_core` fuerza la ENTRADA de un paper que la lente dejó afuera, y no había
    simétrico: un paper que la lente dice core no se podía sacar. `triage --drop` registraba la
    decisión pero se consultaba **sólo** para no re-proponer candidatos del chaining, así que sobre
    un core no tenía efecto — medido en el tema `ica`: 7 papers off-topic descartados con motivo
    seguían siendo core corrida tras corrida. Una decisión de curación que el clasificador ignora en
    silencio es peor que no tomarla: queda escrita, se lee como aplicada, y no lo está.

    El carril es **`sujeto`**, no global, y eso es deliberado: la exclusión es del par
    `(paper, sujeto)`. Los papers que se sacan de `ica` son de geofísica o de Marte y entraron por
    polisemia —"componentes independientes" de un tensor— pero podrían ser legítimamente core de
    otro tema. Un descarte global decidiría por bóvedas que no son ésta.

    INV-24 sigue en pie por la misma razón que con `extra_core`: core es `f(paper, lente)` **módulo
    curación declarada**, y la curación es auditable —motivo obligatorio, fechada, versionada, y el
    registro viaja—. Lo que NO sería auditable es que el veredicto cambiara sin que nadie firme."""
    return {b: (d.get("motivo") or "(sin motivo)")
            for b, d in cfg.load_decisiones(slug).items()
            if d.get("decision") == "descartado" and cfg.es_del_carril(d, "sujeto")}


def aplicar_excluidos(recs: list, slug: str) -> list:
    """Marca como no-core los `recs` que el usuario excluyó de este sujeto. Devuelve los excluidos.

    ⛔ **No los borra de `recs`**: los deja con `relevant: False`, `via: manual-drop` y el motivo en
    `why_excluded`. Que sigan visibles es el punto — si desaparecieran, dentro de tres meses el
    registro se leería como «la búsqueda nunca los encontró», que es falso y borra el juicio."""
    fuera = excluidos_del_sujeto(slug)
    tocados = []
    for r in recs:
        if r.get("bibcode") in fuera and r.get("relevant"):
            r["relevant"] = False
            r["via"] = "manual-drop"
            r["why_excluded"] = f"excluido del sujeto por decisión: {fuera[r['bibcode']]}"
            tocados.append(r["bibcode"])
    return tocados


def n_dropped_chaining(slug: str) -> int:
    """Cuántas decisiones del carril chaining son DESCARTES — no toda decisión del carril, que
    también incluye `aceptado` (candidatos que pasaron a `extra_core`). Este número lo persiste
    `busqueda` en el registro y la cabecera de la ficha lo publica tal cual como "N descartados": si
    no mirara `decision`, un aceptado inflaría lo que la bóveda afirma sobre su propio universo de
    papers (alcanzable con `--migrate`, que importa el juicio viejo tal cual)."""
    return sum(1 for d in cfg.load_decisiones(slug).values()
               if d.get("decision") == "descartado" and cfg.es_del_carril(d, "chaining"))


def _probe_row(r: dict) -> str:
    mark = "CORE" if r["relevant"] else "—   "
    tp = ",".join(r["facets"]) or "(ninguno)"
    cites = r.get("citation_count") or 0              # ADS puede devolver citation_count null
    title = " ".join((r.get("title") or "").split())[:52]
    # El bibcode va en la fila (#104): en un tema MIXTO el operador lee este preview y tiene que
    # copiar bibcodes a `extra_core:`; sin la columna hay que re-llamar a query_ads() a mano.
    bib = r.get("bibcode") or "-"
    return f"  [{mark}] {cites:>5}  {bib:<19}  {title}  «{tp}»"


def fetch_bibcodes(bibs: list[str]) -> list[dict]:
    """Trae registros ADS de una lista explícita de bibcodes (curación manual `extra_core`). Se
    marcan `relevant: True` a la fuerza (el usuario los declaró core: entraron porque el clasificador
    los perdió, no para re-juzgarlos) y `via: manual`.

    Corre **sin la lente astro** (`fq=None`, #68): `extra_core` es override del clasificador, y el
    `fq` era un segundo filtro que el override no esquivaba — un bibcode real pero fuera de
    `database:astronomy` (eprint de `math.ST`/`eess.SP`, el caso CENTRAL del tema mixto: métodos de
    otra disciplina al servicio del foco astro) no volvía, y la cadena lo reportaba como typo. Acá
    el universo lo fijó el usuario: no hay ruido que filtrar, el `fq` sólo puede sacar de más."""
    out = []
    for i in range(0, len(bibs), CHAIN_CHUNK):
        chunk = bibs[i:i + CHAIN_CHUNK]
        q = " OR ".join(f'bibcode:"{b}"' for b in chunk)
        for r in query_ads(q, rows=len(chunk), quiet_truncate=True, fq=None):
            r["relevant"] = True
            r["why_excluded"] = None   # forzado core por el usuario: sin motivo de exclusión
            r["via"] = "manual"
            out.append(r)
        time.sleep(1.0)
    return out


def sweep_star(slug: str, rows: int) -> int:
    """Barrido full-text (paso 2b de ingest-star — antes manual, una --probe por alias y grafía).

    La query directa busca en título+abstract y los surveys de muestra grande tabulan la estrella
    sin nombrarla ahí; el chaining trae los conectados por citas al corpus, y este barrido caza los
    que quedan FUERA del grafo: corre `full:` sobre nombre+aliases con TODAS las variantes de
    espaciado (expand_variants — sin olvidos de grafía) y lista SÓLO los core que
    build/<slug>/ads.json no tiene, la lista corta de candidatos a `extra_core` en stars.yaml.
    Preview como --probe: no baja PDFs, no encadena, no escribe build/. El criterio de qué agregar
    sigue siendo del operador; acá sólo lo mecánico."""
    name, meta = cfg.star_by_slug(slug)
    adsfile = cfg.ROOT / "build" / slug / "ads.json"
    if not adsfile.exists():
        sys.exit(f"--sweep compara contra build/{slug}/ads.json y no existe — corré primero la "
                 f"cadena de ingest (o query_ads.py {slug}).")
    known = {r.get("bibcode") for r in json.loads(adsfile.read_text(encoding="utf-8"))["records"]}
    # `_listify_curado`, no el default posicional `get(..., [])`: éste sólo actúa si la clave está
    # AUSENTE — un `aliases: HD 12345` (un solo alias, sin corchetes) sigue presente y `list + str`
    # revienta con TypeError antes de mandar una sola query a ADS (R16, Anexo A).
    names = [cfg.require_field(meta, "ads_object", name, "stars.yaml")] + \
        _listify_curado(meta.get("aliases"), "aliases")
    q = build_fulltext_filter(names)
    cfg.print_seguro(f"Barrido full-text (2b) de {name} — q: {q}")
    hits = query_ads(q, rows=rows)
    # Orden por citas/AÑO (#79 punto 1, política única en lib_config): este barrido existe para
    # rescatar "core poco citados que caen al fondo del ranking", así que rankearlo por citas crudas
    # lo hacía repetir el sesgo del mecanismo que le falló.
    news = cfg.sort_by_citation_rate(r for r in hits
                                     if r["relevant"] and r.get("bibcode") not in known)
    cfg.print_seguro(f"  {len(hits)} papers con la estrella en el CUERPO · {len(news)} core NUEVOS "
          "(no están en ads.json)")
    for r in news:
        cfg.print_seguro(_probe_row(r))
    if news:
        cfg.print_seguro("\n  → revisá cuáles corresponden y agregalos a `extra_core: [<bibcode>, …]` en la "
              "entrada de la estrella en vault/config/stars.yaml (persistente, via: manual); después "
              "re-corré la cadena (idempotente). Los que decidas NO bajar, listalos en el log — no "
              "curar en silencio.")
    else:
        cfg.print_seguro("  → el corpus ya cubre el barrido full-text. (Ojo: en papers pre-digitales un 0 acá "
              "NO prueba ausencia — el OCR del escaneo pierde filas de tabla; ver skill ingest-star.)")
    return 0


# ── dry-run de re-clasificación (#40) ────────────────────────────────────────

def to_record(d: dict) -> dict:
    """Un doc crudo de ADS → el **registro canónico** que persiste `ads.json`.

    Esta función **define** el schema que `openalex.to_record` y `search_arxiv.to_record` espejan,
    @inv INV-96
    y por eso es una función y no un bloque adentro de `query_ads()`: mientras vivió inline no se
    podía llamar sin red, así que la promesa de "mismo schema" era prosa en tres docstrings — y
    dos de los tres backends terminaron sin las claves del clasificador. La paridad se prueba
    parametrizada en `tests/test_backends_schema.py`."""
    facets, relevant = classify(d)
    return {
        "bibcode": d.get("bibcode"),
        "title": (d.get("title") or [""])[0],
        "authors": d.get("author", []),
        "year": d.get("year"),
        "pubdate": d.get("pubdate"),
        "abstract": d.get("abstract", ""),
        "arxiv_id": extract_arxiv(d.get("identifier", [])),
        "doi": (d.get("doi") or [None])[0],
        "doctype": d.get("doctype"),
        "bibstem": (d.get("bibstem") or [None])[0],
        "citation_count": d.get("citation_count", 0),
        "keyword": d.get("keyword", []),
        "facets": facets,
        "relevant": relevant,
        # #86: este paper se juzgó SIN abstract, o sea con título + keywords y nada más — una
        # fracción de la información con la que se juzga a los demás. ADS no tiene abstract para
        # buena parte de los escaneos viejos, así que el efecto es un sesgo sistemático contra lo
        # pre-digital; y como los no-core no se bajan, nunca vuelve a mirarse. Es el espejo exacto
        # de #79, que sesga contra lo reciente.
        # ⚠ Es INFORMACIÓN, no una regla: NO mueve el corte core/no-core. Si lo moviera, ser core
        # dejaría de ser función de `(paper, lente)` y se rompería INV-24.
        # @inv INV-110
        "sin_abstract": not (d.get("abstract") or "").strip(),
        # motivo real de exclusión (None si core) → apéndice "Excluidos por el filtro"
        "why_excluded": None if relevant else exclusion_reason(facets, d.get("doctype", "")),
    }


def _facet_propia(meta: dict):
    """La lente propia del tema, compilada. Muere con mensaje si falta o no compila.

    Extraída porque la usan DOS caminos (`classify_theme` y `puertas_abiertas`) y la regla tiene que
    ser una sola: dos copias de la misma regla es exactamente donde vive el bug (regla de método
    nº 2)."""
    facet_raw = (meta or {}).get("facet")
    if not facet_raw:
        sys.exit(f"themes.yaml: el tema '{(meta or {}).get('title', '?')}' no declara `facet:` — es "
                 "la lente propia del tema y sin ella no hay regla que aplicar (D-26). Agregala:\n"
                 "  facet: 'independent component|blind source separation'")
    try:
        return re.compile(facet_raw, re.I)
    except re.error as exc:
        sys.exit(f"themes.yaml: `facet:` del tema no compila como regex ({exc})")


def _texto_clasificable(rec: dict) -> str:
    """Título + abstract + keywords, en minúsculas — el texto sobre el que matchea toda lente.
    Tolera `title` como string o como lista (los backends no coinciden)."""
    return " ".join(filter(None, [
        " ".join(cfg.as_list(rec.get("title")) or [rec.get("title") or ""]),
        rec.get("abstract") or "",
        " ".join(cfg.as_list(rec.get("keyword"))),
    ])).lower()


def classify_theme(rec: dict, meta: dict) -> tuple[list[str], bool, str | None]:
    """Relevancia de un paper para un **tema de método** (D-26 / INV-88). Devuelve
    `(facets_globales, core, motivo)`; `motivo` es `None` sii es core.

    La lente global no sirve acá, y no por falta de ajuste: es **activamente dañina**. Con
    `require: [rv]` mata al paper fundacional de ICA —Hyvärinen no menciona RV ni una vez—, y sin
    filtro *"independent component analysis"* devuelve miles de papers de fMRI, EEG y finanzas.

    Por eso el tema trae su **faceta propia** (`facet:` en `themes.yaml`), y la regla es::

        core = faceta propia  Y  (puerta 2  OR  puerta 3)

    - **faceta propia** — precondición, no puerta: sin ella no se mira nada más.
    - **puerta 2, fundacional en su campo** — muy citado. El umbral **se declara** en el tema
      (`fundacional_min_citas`); D-26 no fija un número y ponerle un default escondido sería
      decidir por el usuario. Sin declarar, la puerta no abre **y el motivo lo dice**: misma
      doctrina que la lente ilegible de INV-80, nunca degradar en silencio.
    - **puerta 3, lente astro global** — la aplicación del método en astro, aunque tenga 3 citas.

    ⛔ **La puerta 1 (`lo cita tu corpus`) NO está acá**, a propósito: por la resolución §4.3 del
    plan **propone y no clasifica**, así que alimenta los candidatos del triage
    (`citation_index.cited_by_corpus`). Si clasificara, ser core dejaría de ser función de
    `(paper, lente)` y INV-24 se rompería."""
    propia = _facet_propia(meta)
    texto = _texto_clasificable(rec)
    facets_globales, core_global = classify_record(rec)

    if not propia.search(texto):
        return facets_globales, False, "sin la faceta propia del tema"
    doctype = rec.get("doctype") or ""
    if doctype in NOISE_DOCTYPES:
        return facets_globales, False, f"doctype: {doctype}"

    umbral = (meta or {}).get("fundacional_min_citas")
    citas = rec.get("citation_count")
    # `None` es **no sé**, no «pocas»: arXiv no publica el conteo. Tratarlo como 0 dejaría a todo
    # paper venido de ese backend fuera de la puerta 2 por construcción, que es el cero inventado
    # que INV-87 prohíbe — un chequeo que no se puede evaluar se DECLARA, no se resuelve en contra.
    p2_evaluable = isinstance(umbral, int) and citas is not None
    puerta2 = p2_evaluable and citas >= umbral
    puerta3 = core_global
    if puerta2 or puerta3:
        return facets_globales, True, None
    # (la puerta que abrió se recupera con `puertas_abiertas`, que comparte esta misma regla)
    if umbral is None:
        return facets_globales, False, ("ninguna puerta abre; la 2 (fundacional) está apagada "
                                        "porque el tema no declara `fundacional_min_citas`")
    if citas is None:
        return facets_globales, False, ("la lente astro no lo trae y la puerta 2 (fundacional) "
                                        "**no se pudo evaluar**: el registro viene sin dato de "
                                        "citas (arXiv no lo publica) — enriquecer por DOI o "
                                        "juzgarlo a mano")
    return facets_globales, False, "ninguna puerta abre (ni fundacional ni lente astro)"


# #126 · vocabulario CERRADO de las puertas de D-26, en el orden en que se evalúan.
PUERTAS = ("fundacional", "astro")


def puertas_abiertas(rec: dict, meta: dict) -> tuple:
    """Qué puerta(s) de D-26 admiten a este paper: `("fundacional",)`, `("astro",)`, las dos, o `()`.

    `classify_theme` calculaba las dos por separado y, cuando el paper entraba, devolvía
    `(facets, True, None)`: **se perdía cuál abrió**. El `motivo` sólo existía para el NO, así que
    la bóveda podía decir por qué un paper quedó afuera y no por qué está adentro.

    Es la única metadata que distingue **sin leer el paper** un fundamento de su campo (muy citado,
    puede no mencionar astro ni una vez) de una aplicación astro (tres citas, pero es lo que esta
    bóveda busca). ⚠ `role` no sirve para esto: lo puebla la EXTRACCIÓN, o sea después de leer, y
    esta decisión se toma antes — es la que dice qué se lee.

    Habilita curar por **política** («sólo fundacionales», «fundacionales + astro») en vez de paper
    por paper, y auditar después por qué un paper es core.

    @inv INV-116"""
    propia = _facet_propia(meta)
    texto = _texto_clasificable(rec)
    if not propia.search(texto) or (rec.get("doctype") or "") in NOISE_DOCTYPES:
        return ()
    umbral = (meta or {}).get("fundacional_min_citas")
    citas = rec.get("citation_count")
    out = []
    if isinstance(umbral, int) and citas is not None and citas >= umbral:
        out.append("fundacional")
    if classify_record(rec)[1]:
        out.append("astro")
    return tuple(out)


def reclassify_for_theme(recs: list, meta: dict) -> tuple[list, list]:
    """Re-juzga `recs` con la regla del tema (D-26) y devuelve `(entraron, salieron)` por bibcode.

    Los registros llegan clasificados por la lente **global** (`to_records`); para un tema de
    método esa lente es la equivocada, así que hay que volver a pasarlos. Se devuelven los dos
    deltas —no un booleano ni un total— porque una regla que reclasifica en silencio es una regla
    que nadie puede auditar: el ingest los imprime y quedan en el registro de la corrida.

    Dos recortes: un tema **sin `facet:`** es no-op (sigue con la lente global — rehusar es lo que
    hace `classify_theme` si alguien la llama directo, no esto, que corre dentro de la cadena); y
    los `via: manual` **no se tocan**, porque `extra_core` es juicio del usuario y pisa a cualquier
    clasificador (#68/#39).  @inv INV-88"""
    if not (meta or {}).get("facet"):
        return [], []
    entraron, salieron = [], []
    for r in recs:
        if r.get("via") == "manual":
            continue
        antes = bool(r.get("relevant"))
        _, ahora, why = classify_theme(r, meta)
        if ahora != antes:
            (entraron if ahora else salieron).append(r.get("bibcode"))
        r["relevant"], r["why_excluded"] = ahora, why
        # #126: por qué está ADENTRO. `why_excluded` sólo explicaba el NO, así que la bóveda podía
        # decir por qué un paper quedó afuera y no por qué es core. Lista vacía = no es core; el
        # campo existe siempre, así que "no consta" y "ninguna puerta" no se confunden.
        r["puertas"] = list(puertas_abiertas(r, meta)) if ahora else []
    return entraron, salieron


def gate_cited_by_corpus(recs: list, index: dict | None = None) -> list:
    """**Puerta 1** de D-26: los registros que la regla del tema NO hizo core pero que **el corpus
    cita**, propuestos como candidatos del triage.

    ⛔ Propone y **no clasifica** (resolución §4.3 del plan): no toca `relevant` de nadie. Si
    clasificara, ser core dejaría de ser función de `(paper, lente)` y se rompería INV-24 — y sería
    encima la clase de regla que nadie puede auditar después, porque depende del estado del corpus
    en el momento de la corrida.

    Es la señal que ninguna regex puede expresar: Hyvärinen tiene ~30k citas, casi todas de fMRI y
    finanzas; lo que lo vuelve **tuyo** es que **tu** gente lo cita.

    Se consulta con **todas** las llaves del registro (bibcode, id de OpenAlex): el corpus pudo
    citarlo por cualquiera de las dos fuentes y preguntar por una sola da un falso negativo.
    Sin índice construido, no aporta nada — no inventa candidatos ni rompe la cadena.  @inv INV-88"""
    import citation_index
    idx = index if index is not None else citation_index.load()
    if not (idx or {}).get("citas"):
        return []
    props = []
    for r in recs:
        if r.get("relevant"):
            continue
        llaves = [k for k in (r.get("bibcode"),
                              (r.get("openalex_id") or "").rsplit("/", 1)[-1] or None) if k]
        citadores = citation_index.cited_by_corpus(llaves, idx)
        if citadores:
            props.append({**r, "via": "citado-por-corpus", "citado_por": citadores})
    return props


def classify_record(r: dict) -> tuple[list[str], bool]:
    """`classify` sobre un registro YA persistido en ads.json (title es string, no lista como en
    la respuesta cruda de ADS). Los `via: manual` son core por decisión del usuario (override de
    `extra_core`, #39): la regla no los toca."""
    facets, relevant = classify({"title": [r.get("title") or ""],
                                 "abstract": r.get("abstract") or "",
                                 "keyword": cfg.as_list(r.get("keyword")),
                                 "doctype": r.get("doctype") or ""})
    return facets, True if r.get("via") == "manual" else relevant


def note_state(bibcode: str) -> str:
    """Estado de la nota de un paper: `extraida` (tiene extracción LLM — `methods` poblado),
    `stub` (existe pero mudo) o `sin_nota`. Es el número que decide en la re-clasificación:
    "342 notas salen del core" asusta hasta ver que 338 son stubs y sólo 4 tenían trabajo encima."""
    dest = cfg.PAPERS / f"{bibcode.replace('/', '_')}.md"
    if not dest.exists():
        return "sin_nota"
    fm = cfg.split_fm(dest.read_text(encoding="utf-8"))
    return "extraida" if cfg.as_list(fm.get("methods")) else "stub"


# ── D-49: la lente, del lado del que CLASIFICA ────────────────────────────────────────────────────
#
# Acá vive sólo `lens_used`: la lente que ESTE proceso compiló, que es lo que el registro tiene que
# guardar. Toda la comparación (`lens_current`, `lens_delta`, `lens_diff_offline`, …) vive en
# `lib_config`, porque su consumidor es el **lint**: es lógica de config y regex, sin una línea de
# red, y dejarla acá obligaba al lint a importar `requests` para compararla — lo que lo hacía
# **fallar en CI**, donde ese paquete no se instala. Un chequeo que existe para no producir falsos
# limpios no puede volverse él mismo un falso rojo por una dependencia que no necesita.
def lens_used(meta: dict | None = None) -> dict:
    """La lente COMPILADA que este proceso usó para clasificar (las constantes de módulo). Es lo
    que `main()` persiste: el registro dice con qué filtro se recortó ESA corrida.

    Con `meta` (la entrada del tema) suma **la regla del tema** —`facet` y el umbral de la puerta
    2—, y eso no es decorativo (#106). La puerta 2 admite un paper por `citation_count`, o sea por
    metadata que **cambia sola con el tiempo**: la función es estable y su entrada deriva, así que
    el veredicto puede moverse sin que nadie edite nada. El framework ya trata así a las otras
    cinco cosas que cambian afuera (retracciones, correcciones, versiones, snapshot web,
    ground-truth) y la respuesta nunca fue congelar: es **detectar, reportar, no aplicar solo**. Sin
    guardar el umbral no hay contra qué comparar, y la puerta quedaba siendo la única dependencia
    del mundo **sin vigilancia**."""
    lente = {"facets": {name: pat.pattern for name, pat in FACET_PATTERNS.items()},
             "require": list(REQUIRE_FACETS),
             "min_facets": MIN_FACETS,
             "noise_doctypes": sorted(NOISE_DOCTYPES)}
    if meta:
        # `"umbral" in` y no `or None`: un umbral declarado en 0 es una decisión (la puerta abre
        # para todos) y no puede leerse igual que "no lo declaró" (la puerta no abre). Es la misma
        # distinción que D-26 protege al no ponerle default.
        regla = {"facet": meta.get("facet")}
        if "fundacional_min_citas" in meta:
            regla["umbral"] = meta.get("fundacional_min_citas")
        lente["regla_tema"] = regla
    return lente



def reclass_diff(slugs: list[str]) -> int:
    """Preview del delta de re-clasificación (sub-modo D de `maintain`): re-clasifica **en memoria**
    los `build/<slug>/ads.json` existentes con la regla VIGENTE de objective.yaml y reporta el delta
    contra el `relevant` persistido. No consulta ADS, no escribe build/ ni toca la bóveda.

    Reporta por slug: core antes/después, los papers que SALEN del core separando los que tienen
    extracción LLM (lista completa: son pocos y son la decisión real) de los stubs (sólo conteo), y
    los que ENTRAN al core sin nota, por vía de entrada."""
    total_out = total_out_llm = total_in = 0
    for slug in slugs:
        adsfile = cfg.ROOT / "build" / slug / "ads.json"
        if not adsfile.exists():
    #  @inv INV-58
            cfg.print_seguro(f"{slug}: sin build/{slug}/ads.json — nada que re-clasificar")
            continue
        recs = json.loads(adsfile.read_text(encoding="utf-8"))["records"]
        aplicar_excluidos(recs, slug)      # #112: lo ya excluido no se re-propone en cada re-clasif.
        before = [r for r in recs if r.get("relevant")]
        after, salen, entran = [], [], []
        for r in recs:
            _, now = classify_record(r)
            if now:
                after.append(r)
            if r.get("relevant") and not now:
                salen.append(r)
            elif now and not r.get("relevant"):
                entran.append(r)
        factor = (len(after) / len(before)) if before else float("inf")
        cfg.print_seguro(f"\n{slug}: {len(recs)} registros · core {len(before)} → {len(after)}  "
              f"(factor {factor:.2f})")

        estado = {r["bibcode"]: note_state(r["bibcode"]) for r in salen}
        con_llm = [r for r in salen if estado[r["bibcode"]] == "extraida"]
        stubs = [r for r in salen if estado[r["bibcode"]] == "stub"]
        cfg.print_seguro(f"  SALEN del core: {len(salen)} — con extracción LLM: {len(con_llm)} · "
              f"stubs: {len(stubs)} · sin nota: {len(salen) - len(con_llm) - len(stubs)}")
        for r in sorted(con_llm, key=lambda r: r.get("citation_count") or 0, reverse=True):
            cfg.print_seguro(f"    ← {r['bibcode']}  {' '.join((r.get('title') or '').split())[:64]}")

        sin_nota = [r for r in entran if note_state(r["bibcode"]) == "sin_nota"]
        vias: dict[str, int] = {}
        for r in sin_nota:
            vias[r.get("via") or "?"] = vias.get(r.get("via") or "?", 0) + 1
        detalle = " · ".join(f"{v} {k}" for k, v in sorted(vias.items())) or "—"
        cfg.print_seguro(f"  ENTRAN al core: {len(entran)} — sin nota (a crear): {len(sin_nota)}  ({detalle})")
        total_out += len(salen)
        total_out_llm += len(con_llm)
        total_in += len(sin_nota)
    if len(slugs) > 1:
        cfg.print_seguro(f"\nTotal: salen {total_out} (con extracción LLM {total_out_llm}) · "
              f"entran sin nota {total_in}")
    cfg.print_seguro("\n  → dry-run: no se escribió nada. Para aplicar, re-corré la cadena del sujeto "
          "(query_ads/make_notes) — sub-modo D del skill maintain.")
    return 0


def built_slugs() -> list[str]:
    """Slugs con `build/<slug>/ads.json` (los sujetos ya ingestados: el universo del dry-run)."""
    builds = cfg.ROOT / "build"
    return sorted(p.parent.name for p in builds.glob("*/ads.json")) if builds.exists() else []


def count_core(recs: list, require: list[str], min_facets: int) -> int:
    """Cuántos registros serían core bajo una regla de combinación HIPOTÉTICA (misma precedencia que
    `exclusion_reason`, sobre los `facets` ya clasificados). Insumo del contraste del `--probe`."""
    return sum(1 for r in recs
               if r["facets"] and r.get("doctype") not in NOISE_DOCTYPES
               and all(t in r["facets"] for t in require)
               and len(r["facets"]) >= min_facets)


def print_combination_contrast(recs: list) -> None:
    """Corte CON y SIN faceta obligatoria (#41). La regla de combinación es la palanca real contra el
    ruido —una faceta laxa deja de discriminar apenas el pool se amplía por chaining— pero `--probe`
    sólo mostraba el corte vigente, así que la decisión de declarar `require` se discutía en vez de
    medirse. Si ya hay regla declarada, se contrasta contra el OR puro; si no, se muestra qué pasaría
    con cada faceta como eje."""
    base = count_core(recs, [], 1)      # OR puro: ≥1 faceta cualquiera (el default histórico)
    if REQUIRE_FACETS or MIN_FACETS > 1:
        regla = (f"require={REQUIRE_FACETS or '[]'}, min_facets={MIN_FACETS}")
        cfg.print_seguro(f"  regla de combinación vigente: {regla} · en OR puro serían {base} CORE")
        return
    cfg.print_seguro(f"  regla de combinación vigente: OR (≥1 faceta cualquiera) → {base} CORE.")
    cfg.print_seguro("  Si declararas una faceta-eje obligatoria (relevance.require) el corte sería:")
    for t in FACET_PATTERNS:
        n = count_core(recs, [t], 1)
        pct = f"−{100 * (base - n) / base:.0f}%" if base else "—"
        cfg.print_seguro(f"    require: [{t}]{' ' * max(0, 14 - len(t))}→ {n:>5} CORE  ({pct})")


def print_probe(q: str, recs: list, noncore_top: int = 25) -> int:
    """Modo preview del skill `setup`: muestra el corte core/no-core de una query sin bajar nada,
    para afinar la regla de relevancia (relevance.facets) contra papers reales. Lista **TODO el core**
    (no un top-N: papers recientes/poco citados caen al fondo del ranking pero pueden ser core); del
    no-core muestra sólo el top `noncore_top` por citas (chequeo de sanidad del corte). Cierra con el
    contraste de la regla de combinación (#41). El barrido 2b de ingest-star, que antes se hacía con
    probes manuales, hoy corre por --sweep (sweep_star)."""
    # @inv INV-59
    core = sorted((r for r in recs if r["relevant"]), key=lambda r: r.get("citation_count") or 0, reverse=True)
    noncore = sorted((r for r in recs if not r["relevant"]), key=lambda r: r.get("citation_count") or 0, reverse=True)
    cfg.print_seguro(f"Probe (no baja PDFs ni escribe build/). q: {q}")
    cfg.print_seguro(f"  {len(recs)} papers · {len(core)} CORE · {len(noncore)} no-core")
    # T-3: la lente es un PRESUPUESTO, no sólo un filtro. El probe existe para afinar el corte, y
    # el costo de leer lo que entra es la otra mitad de esa decisión (D-13 promete leer TODOS los
    # core). Proyección gruesa y declarada como tal: n_core × la mediana de tokens por fulltext.
    proyectado = len(core) * cfg.TOKENS_POR_PAPER
    cfg.print_seguro(f"  costo proyectado de leer el core: ~{proyectado // 1000}k tokens "
                     f"({len(core)} × {cfg.TOKENS_POR_PAPER // 1000}k, mediana del corpus)")
    print_combination_contrast(recs)
    cfg.print_seguro("")
    cfg.print_seguro(f"  CORE (todos, por citas)  [tópicos que matchearon]:")
    for r in core:
        cfg.print_seguro(_probe_row(r))
    shown = noncore[:noncore_top]
    cfg.print_seguro(f"\n  no-core (top {len(shown)} de {len(noncore)}, chequeo de sanidad):")
    for r in shown:
        cfg.print_seguro(_probe_row(r))
    cfg.print_seguro("\n  → ajustá relevance.facets en objective.yaml y re-corré --probe hasta que el corte cierre.")
    return 0



def _flags_usados(args, ap=None) -> list:
    """Los flags no-default de esta corrida, para dejarlos en `cadena:` del registro (D-48/D-57).
    Son las **escotillas**: `--force`, `--yes`, `--all` cambian lo que la corrida hizo, y sin
    registrarlas la traza dice "corrió make_notes" sobre dos corridas que no hicieron lo mismo."""
    return cfg.flags_usados(args, ap)

def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    # D-6 / INV-80 — la lente vacía REHÚSA operar.  @inv INV-80
    #
    # `load_objective` degrada un YAML ilegible a `{}` en silencio (es lo correcto para el lint,
    # cuyo contrato es reportar y no morirse). Para el CLASIFICADOR esa tolerancia es un agujero:
    # seguía corriendo con una regla que nadie escribió, marcaba core/no-core con la lente vacía, y
    # el registro guardaba ESA lente como si fuera la vigente — o sea, el artefacto que documenta
    # "con qué lente se filtró" quedaba mintiendo. Se chequea acá y no a nivel módulo para que
    # `--help` siga funcionando con la config rota.
    if (err := cfg.objective_error()):
        sys.exit(f"⛔ no se puede clasificar: {err}\n"
                 "   Arreglá la lente antes de consultar ADS — clasificar con una lente vacía "
                 "marcaría el corpus entero con una regla que nadie escribió.")
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?",
                    help="slug de estrella (o tema con --theme). Se omite con --probe.")
    ap.add_argument("--rows", type=int, default=2000,
                    help="tope de registros por query (default 2000 ≈ el máximo de una request ADS; "
                         "cubre la enorme mayoría de sujetos sin truncar). Si igual trunca, queda "
                         "marcado en build/<slug>/ads.json y el lint lo surface")
    ap.add_argument("--no-chain", action="store_true",
                    help="desactivar el citation chaining (references/citations de los papers core)")
    ap.add_argument("--no-glyph", action="store_true",
                    help="desactivar el rescate por glifo de nombres Bayer (ε/ϵ/∊ Eri): trae el "
                         "superset de la constelación y filtra client-side. Sólo corre si el "
                         "sujeto tiene nombre de letra griega; desactivarlo si el superset es "
                         "demasiado grande y preferís curar a mano")
    ap.add_argument("--theme", action="store_true",
                    help="el slug es un TEMA de vault/config/themes.yaml (query Solr cruda), no una estrella")
    ap.add_argument("--extra-only", action="store_true",
                    help="traer SÓLO los bibcodes de `extra_core` (sin query ni chaining) — la vía ADS "
                         "de un tema off-ADS MIXTO: su bibliografía canónica vive fuera de ADS (sin "
                         "`query`), pero los papers que SÍ tienen bibcode van en extra_core. "
                         "La corre ingest_theme.py solo.")
    ap.add_argument("--probe", metavar="QUERY",
                    help="PREVIEW (skill setup): corre una query Solr CRUDA y muestra el corte "
                         "core/no-core con títulos, clasificando con relevance.facets de objective.yaml. "
                         "No baja PDFs ni escribe build/ — sólo para afinar la regla de relevancia.")
    ap.add_argument("--dry-run", action="store_true",
                    help="PREVIEW de re-clasificación (sub-modo D de maintain): re-clasifica EN "
                         "MEMORIA los build/<slug>/ads.json ya existentes con la regla vigente de "
                         "objective.yaml y reporta el delta (core antes/después, papers que salen "
                         "—separando los que tienen extracción LLM de los stubs— y los que entran "
                         "sin nota, por vía). No consulta ADS ni escribe nada. Sin slug: TODOS los "
                         "sujetos ya ingestados.")
    ap.add_argument("--sweep", action="store_true",
                    help="barrido full-text del paso 2b de ingest-star: corre full: sobre "
                         "nombre+aliases (todas las grafías, sin probes a mano) y lista SÓLO los "
                         "core que build/<slug>/ads.json no tiene — candidatos a extra_core en "
                         "stars.yaml. Preview: no baja nada ni escribe build/. Sólo estrellas.")
    args = ap.parse_args()

    if args.probe:
        return print_probe(args.probe, query_ads(args.probe, rows=args.rows))

    if args.dry_run:   # offline: sólo re-clasifica lo que ya está en build/ (no toca ADS)
        slugs = [args.slug] if args.slug else built_slugs()
        if not slugs:
            sys.exit("no hay ningún build/<slug>/ads.json — el dry-run compara contra un corpus "
                     "ya bajado (corré la cadena de ingest primero).")
        return reclass_diff(slugs)

    if not args.slug:
        ap.error('falta el slug (o usá --probe "<query>" para previsualizar la regla de relevancia)')
    if args.extra_only and not args.theme:
        ap.error("--extra-only es de temas (--theme): una estrella siempre tiene query (ads_object)")
    if args.sweep:
        if args.theme:
            ap.error("--sweep es de estrellas (surveys que tabulan la estrella sin nombrarla en "
                     "título/abstract); el análogo para temas es el retro-tag 3b del skill "
                     "ingest-theme (grep de aliases sobre el corpus local)")
        return sweep_star(args.slug, args.rows)

    star_names: list[str] = []      # sólo estrellas: insumo del rescate por glifo (#28)
    tema_meta = None                # se persiste en la `lente` del registro (regla del tema, #106)
    if args.theme:
        _, meta = cfg.theme_by_slug(args.slug)
        tema_meta = meta
        if args.extra_only:
            # Tema MIXTO (off-ADS + extra_core): sin `query` no hay búsqueda ni chaining — la
            # única fuente ADS es la curación manual de `extra_core` (el bloque de abajo).
            q, chain_filter = None, None
            cfg.print_seguro(f"Consultando ADS (tema, sólo extra_core): {meta.get('title', args.slug)}")
            head = {"kind": "theme", "slug": args.slug, "title": meta.get("title"),
                    "concept": meta.get("concept"), "area": meta.get("area"), "query": None}
        else:
            q = cfg.require_field(meta, "query", args.slug, "themes.yaml",
                                  hint="Si es un tema off-ADS (source: web|local-pdfs) no va por "
                                       "query_ads: corré ingest_theme.py, que despacha por `source`.")
            # el "sujeto" de un tema es su propia query: anclar el chaining con ella deja on-theme a los
            # papers del grafo de citas (sin ancla traería los mega-citados genéricos, como en estrellas).
            chain_filter = f"({q})"
            cfg.print_seguro(f"Consultando ADS (tema): {meta.get('title', args.slug)}\n  q: {q}")
            head = {"kind": "theme", "slug": args.slug, "title": meta.get("title"),
                    "concept": meta.get("concept"), "area": meta.get("area"), "query": q}
    else:
        name, meta = cfg.star_by_slug(args.slug)
        # mismo motivo que en `sweep_fulltext`: un `aliases:` escalar no debe tumbar el arranque
        # del ingest con un TypeError que no dice qué corregir (R16).
        names = [cfg.require_field(meta, "ads_object", name, "stars.yaml")] + \
            _listify_curado(meta.get("aliases"), "aliases")
        star_names = names
        q = build_query(names)
        chain_filter = build_fulltext_filter(names)
        cfg.print_seguro(f"Consultando ADS: {name}  (nombres: {', '.join(names)})")
        # `query`: la Solr EFECTIVA, tal cual se manda (#64). En un tema la escribe el usuario en
        # themes.yaml (versionada); en una estrella la arma build_query y hasta ahora se tiraba →
        # no había forma de reconstruir sobre qué universo afirma la ficha.
        head = {"kind": "star", "star": name, "slug": args.slug, "ads_object": meta["ads_object"],
                "query": q}

    qmeta: dict = {}                # truncamiento de la query DIRECTA (el chaining trunca por diseño)
    if q is None:
        recs, rel = [], []          # --extra-only: todo entra por el bloque extra_core de abajo
    else:
        # expect_hits: la query directa de un sujeto NO puede volver vacía — un 0 es el cero
        # espurio de ADS (#27) o un nombre mal escrito; en ambos casos abortar > persistir vacío.
        recs = query_ads(q, rows=args.rows, meta=qmeta, expect_hits=True)
        for r in recs:
            r["via"] = "query"
        # D-26: para un tema de método la lente global es la equivocada (mata al fundacional y deja
        # pasar miles de fMRI). Se re-juzga con la regla del tema y se IMPRIME el delta.
        if head.get("kind") == "theme":
            entraron, salieron = reclassify_for_theme(recs, meta)
            if entraron or salieron:
                cfg.print_seguro(f"  regla del tema (D-26): +{len(entraron)} core / -{len(salieron)}"
                                 f" · entran {entraron[:5]} · salen {salieron[:5]}")
        # #112: la exclusión declarada se aplica DESPUÉS de la regla del tema y ANTES de contar —
        # si se aplicara antes, la re-clasificación del tema la volvería a marcar core.
        _fuera = aplicar_excluidos(recs, args.slug)
        if _fuera:
            cfg.print_seguro(f"  excluidos por decisión del sujeto (#112): {len(_fuera)} "
                             f"· {_fuera[:5]}")
        rel = [r for r in recs if r["relevant"]]
        cfg.print_seguro(f"  query directa: {len(recs)} registros, {len(rel)} relevantes")
        # Segunda pasada por fecha (#79): el corte por citas de la primera es ciego a la edad, así
        # que lo que truncó es sistemáticamente lo reciente. Corre ANTES de extra_core/glifo/
        # chaining para que lo recuperado siembre también el grafo de citas (mismo criterio que #42).
        if qmeta.get("truncated"):
            conocidos = {r["bibcode"] for r in recs if r.get("bibcode")}
            try:
                recientes = recent_pass(q, args.rows, conocidos)
            except (EmptyResultError, RuntimeError, requests.RequestException) as e:
                # Rescate BEST-EFFORT: la query directa ya volvió bien y su `ads.json` vale. Antes
                # cualquier excepción acá abortaba antes de escribirlo y tiraba la corrida entera.
                # Se degrada al estado honesto: `recent` AUSENTE = "no sé si la cola está cubierta"
                # (que es lo que el lint distingue de `0`), no un cero que afirma cobertura.
                cfg.print_seguro(f"  ⚠ la segunda pasada por fecha falló ({type(e).__name__}): "
                      f"{e or 'sin detalle'} — sigo con lo que trajo la query directa; el corpus "
                      f"queda marcado truncado SIN afirmar nada sobre la cola reciente")
                recientes = None
            if recientes is not None:
                qmeta["recent"] = len(recientes)
                recs += recientes
                rel = [r for r in recs if r["relevant"]]
                cfg.print_seguro(f"  segunda pasada por fecha: +{len(recientes)} registros que el top por "
                      f"citas dejaba afuera ({sum(1 for r in recientes if r['relevant'])} core)")

    # curación manual persistente: bibcodes en `extra_core` de stars.yaml/themes.yaml que el
    # clasificador perdió (build/ es scratch y se pisa; esto sobrevive porque vive en config).
    # Corre ANTES del glifo y del chaining (#42): si mergea después, los curados no están en `recs`
    # cuando el chaining arma su dedup y la cola de triage RE-PROPONE papers ya aceptados (medido:
    # 14 de 50 extra_core de ε Eri de vuelta como candidatos). Acá, además, siembran el grafo.
    # D-58/R-2: forma dura. `load_extra_core` valida y aborta con el snippet correcto ante el
    # atajo viejo (`extra_core: [bibcode]`), en vez de aceptarlo sin `via` ni `motivo`. Eso además
    # cierra R13 de raíz: el escalar suelto que `_listify_curado` "rescataba" letra por letra ya no
    # es una forma válida que haya que adivinar.
    entradas = cfg.load_extra_core(meta, entry=args.slug)
    extra = [e["bibcode"] for e in entradas]
    via_de = {e["bibcode"]: e["via"] for e in entradas}
    if args.extra_only and not extra:
        sys.exit(f"--extra-only pero la entrada '{args.slug}' no declara `extra_core` en themes.yaml "
                 "— listá ahí los bibcodes ADS del tema mixto.")
    if extra:
        # `extra_core` es un OVERRIDE del clasificador, no un "sumá lo ausente" (#39): el caso más
        # común de la curación es el paper que ADS SÍ devuelve y la lente descarta (p. ej. papers
        # de actividad que arbitran señales pero no dicen "radial velocity" en título/abstract).
        # Traerlo por bibcode no alcanzaba: el registro ya estaba en `recs` con relevant: False.
        present = {r["bibcode"]: r for r in recs if r.get("bibcode")}
        rescued = []
        for b in extra:
            r = present.get(b)
            if r is not None and not r["relevant"]:
                # el `via` declarado en la config reemplaza al "manual" hardcodeado: la ficha puede
                # decir si ese paper entró por juicio del usuario, por el triage o por el corpus.
                r["relevant"], r["why_excluded"], r["via"] = True, None, via_de.get(b, "manual")
                rescued.append(b)
            # D-52: si ese bibcode figuraba DESCARTADO, la aceptación lo revierte — se anula la
            # decisión preservando el motivo viejo, en vez de dejarla contradiciendo lo hecho.
            if cfg.anular_decision(args.slug, b, por="extra_core"):
                cfg.print_seguro(f"  ↩ {b}: figuraba descartado y está en `extra_core` → decisión "
                                 "ANULADA en el registro (el motivo viejo queda en `previa`)")
        manual = [m for m in fetch_bibcodes([b for b in extra if b not in present])
                  if m.get("bibcode")]
        cfg.print_seguro(f"  extra_core: +{len(manual)} traídos de ADS · {len(rescued)} rescatados del corte "
              f"(de {len(extra)} en config)")
        fetched = {m["bibcode"] for m in manual}
        missing = [b for b in extra if b not in present and b not in fetched]
        if missing:
            # La búsqueda por bibcode corre SIN la lente astro (#68), así que un faltante ya no se
            # explica por "está en ADS pero no en database:astronomy" — el diagnóstico honesto es
            # bibcode mal escrito o registro que ADS retiró/renombró.
            cfg.print_seguro(f"  ⚠ extra_core: {len(missing)} bibcode(s) que ADS no encontró — revisá que el "
                  f"bibcode sea exacto (ADS a veces los renombra): {', '.join(missing)}")
        recs += manual
        rel = [r for r in recs if r["relevant"]]

    # rescate por glifo (#28) — ANTES del chaining, para que los recuperados (típicamente el paper
    # de descubrimiento) siembren también el grafo de citas.
    gmeta: dict = {}                # truncamiento del superset del rescate por glifo (#43)
    if not args.no_glyph and star_names and greek_targets(star_names):
        seen = {r["bibcode"] for r in recs if r.get("bibcode")}
        rescued = []
        for g in glyph_rescue(star_names, args.rows, meta=gmeta):
            b = g.get("bibcode")
            if g["relevant"] and b and b not in seen:
                seen.add(b)
                rescued.append(g)
        cfg.print_seguro(f"  glifo: +{len(rescued)} core nuevos que escriben el nombre con un lookalike "
              "Unicode (∊/ϵ) — invisibles a title:/abs:")
        for t in gmeta.get("truncated_glyph") or []:
            cfg.print_seguro(f"  ⚠ rescate por glifo incompleto: el superset de "
                  f"{'/'.join(t['constellations'])} reporta {t['num_found']} y se escanearon "
                  f"{t['rows']} (top por citas, ANTES del filtro por glifo) — subí --rows para "
                  f"cubrir la cola (queda marcado en ads.json → lint)")
        recs += rescued
        rel = [r for r in recs if r["relevant"]]

    candidatos: list[dict] = []      # chaining pendiente de triage (#38): NO son core, no se bajan
    if not args.no_chain and rel and chain_filter:
        seen = {r["bibcode"] for r in recs if r.get("bibcode")}
        core_bibs = [r["bibcode"] for r in rel if r.get("bibcode")]
        # La compuerta es de ESTRELLAS: en un tema la query ES la definición del tema, así que su
        # core (y el del grafo anclado a esa query) entra solo.
        # D-48: NO hay flag para apagarla. Existía `--no-triage` "para restaurar el comportamiento
        # viejo", y ese comportamiento es el que #55 midió con 18% de precisión — pero lo grave no
        # es el ruido: con el flag, un bibcode ya descartado (con su motivo, persistido por #51)
        # volvía a entrar EN SILENCIO. Una escotilla que pisa el juicio curado no es una escotilla,
        # es una fuga.
        gate = bool(star_names)
        descartados = load_triage(args.slug) if gate else set()
        chained, ya_descartados = [], 0
        for c in chain_candidates(core_bibs, args.rows, chain_filter):
            b = c.get("bibcode")
            if not (c["relevant"] and b and b not in seen):  # sólo core nuevos (dedup vs query y ops)
                continue
            seen.add(b)
            if not gate or subject_in_title(c.get("title"), star_names):
                chained.append(c)          # nivel 0: entra solo (sujeto en el título)
            elif b in descartados:
                ya_descartados += 1        # decisión persistida: no re-proponer
            else:
                candidatos.append(c)       # nivel 1: al triage (juicio del LLM, sin bajar nada)
        anchor = "full-text del sujeto" if not args.theme else "la query del tema"
        cfg.print_seguro(f"  chaining: +{len(chained)} core nuevos vía el grafo de citas de {len(core_bibs)} core "
              f"(anclado a {anchor})")
        if gate:
            cfg.print_seguro(f"  triage: {len(candidatos)} candidatos pendientes de juicio "
                  f"({ya_descartados} ya descartados antes) — no se bajan hasta decidirlos: "
                  f"python scripts/triage.py {args.slug}")
        recs += chained
        rel = [r for r in recs if r["relevant"]]

    # Puerta 1 de D-26: lo que la regla del tema dejó afuera pero el corpus CITA se propone al
    # triage (nunca se vuelve core solo — §4.3). Va después del chaining para juzgar `recs` ya
    # completo, y sólo en temas: en una estrella la señal la da el chaining anclado al full-text.
    if head.get("kind") == "theme":
        ya_prop = {c.get("bibcode") for c in candidatos}
        p1 = [c for c in gate_cited_by_corpus(recs) if c.get("bibcode") not in ya_prop]
        if p1:
            candidatos += p1
            cfg.print_seguro(f"  puerta 1 (lo cita tu corpus): +{len(p1)} candidatos al triage "
                             f"— no son core, los juzgás vos: python scripts/triage.py {args.slug}")

    recs.sort(key=lambda r: r.get("citation_count") or 0, reverse=True)
    cfg.print_seguro(f"  total: {len(recs)} registros, {len(rel)} relevantes")

    # marca de truncamiento de la query directa (sólo si realmente se cortó): persistida para que el
    # lint la surface como corpus incompleto. El truncado del chaining NO se registra (es por diseño).
    # `recent` SIN default: la clave ausente es el estado "la pasada no corrió / falló" y el lint
    # discrimina por eso (`rec_n is None`) — un `0` es la afirmación positiva "corrió y no encontró
    # nada", que es lo contrario de lo que pasó.
    truncated = ({"num_found": qmeta["num_found"], "rows": qmeta["rows"],
                  **({"recent": qmeta["recent"]} if "recent" in qmeta else {})}
                 if qmeta.get("truncated") else None)
    if truncated:
        rescate = (f" + {truncated['recent']} de la segunda pasada por fecha"
                   if "recent" in truncated else " (la segunda pasada por fecha no pudo correr)")
        cfg.print_seguro(f"  ⚠ corpus truncado: ADS reporta {truncated['num_found']} y se trajeron "
              f"{truncated['rows']}{rescate} — sigue faltando el medio del universo; marcado en "
              "ads.json (el lint lo surface)")

    outdir = cfg.ROOT / "build" / args.slug
    outdir.mkdir(parents=True, exist_ok=True)
    # `candidates` va en su PROPIA clave: no son core (no se bajan) ni no-core del corte (no
    # inundan el apéndice "Excluidos" de make_notes) — son juicio pendiente. Ver triage.py.
    # `truncated_glyph` (#43) es la marca HERMANA de `truncated`, pero del superset del rescate por
    # glifo: ahí el corte pasa antes del filtro, así que la cola puede esconder papers del sujeto.
    payload = {**head, "n_total": len(recs), "n_relevant": len(rel),
               "truncated": truncated,
               "truncated_glyph": gmeta.get("truncated_glyph") or None,
               "records": recs,
               "candidates": sorted(candidatos, key=lambda r: r.get("citation_count") or 0,
                                    reverse=True)}
    (outdir / "ads.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    cfg.print_seguro(f"  → {outdir / 'ads.json'}")

    # Registro de búsqueda VERSIONADO (#64): el ads.json de arriba es scratch regenerable, pero el
    # registro reproducible de QUÉ se buscó, CUÁNDO, con qué límite y con qué corte tiene que viajar
    # con la bóveda — es lo que permite saber sobre qué universo de papers afirma una ficha (y con
    # qué versión del clasificador). Preserva `decisiones` (las escribe triage.py).
    cfg.save_busqueda(args.slug, {
        "fecha": dt.date.today().isoformat(),
        "query": q,                                   # la Solr efectiva (None con --extra-only)
        "rows": args.rows,
        "n_found": qmeta.get("num_found"),            # lo que ADS dice que hay (None sin query directa)
        "n_total": len(recs),                         # lo que se trajo (query + extra_core + chaining)
        # D-28: los bibcodes de ESTA corrida. Es lo que permite que el universo del sujeto sea una
        # UNIÓN y no una suma (dos refrescos solapados no cuentan dos veces lo que ya estaba), y lo
        # que deja calcular `n_nuevos`/`n_ya_estaban` de la corrida siguiente.
        "bibcodes": sorted({r["bibcode"] for r in recs if r.get("bibcode")}),
        "n_core": len(rel),
        # #86: cuántos de los que se clasificaron NO tenían abstract, o sea se juzgaron con título +
        # keywords y nada más. No cambia el corte (INV-24): hace **medible** el sesgo contra lo
        # pre-digital, que hasta ahora era invisible en los tres lugares donde se podía ver.
        "n_sin_abstract": sum(1 for r in recs if r.get("sin_abstract")),
        "n_candidates": len(candidatos),              # triage pendiente al cerrar esta corrida
        # sólo el carril del chaining: `busqueda` describe la BÚSQUEDA (encontrados → core →
        # sin juzgar → descartados) y una fuente declarada de un tema off-ADS no participó de
        # ninguna búsqueda — contarla ahí hace que la cabecera de la nota publique un descarte
        # que nadie descartó de la query (#81).
        "n_dropped": n_dropped_chaining(args.slug),
        "truncated": bool(truncated),
        # D-48: las escotillas usadas en ESTA corrida. Cambian lo que la búsqueda hizo (`--yes`
        # saltea la guardia de expansión, `--extra-only` no consulta ADS), así que sin ellas dos
        # entradas idénticas del registro pueden describir corridas que no hicieron lo mismo. De
        # acá llegan a la cabecera de la ficha vía `search_line`.
        "escotillas": _flags_usados(args, ap),
        "almagesto_version": cfg.ALMAGESTO_VERSION,
        # La LENTE con la que se clasificó, textual (#64 → auditoría 1.10.3). `almagesto_version`
        # es la versión del framework, NO la de la regla: cambiar una regex de `relevance.facets`
        # mueve el corte core/no-core sin mover la versión. Sin esto el registro dice sobre qué
        # universo se buscó pero no con qué filtro se recortó, que es la otra mitad de "reproducible".
        "lente": lens_used(tema_meta),
    })
    cfg.print_seguro(f"  → {cfg.registro_path(args.slug)} (registro de búsqueda, versionado)")
    cfg.save_paso(args.slug, "query_ads", flags=_flags_usados(args, ap))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EmptyResultError as exc:   # #27: exit ≠ 0 → el orquestador aborta la cadena
        sys.exit(str(exc))
