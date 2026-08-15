"""Consulta NASA ADS por estrella → metadata de papers + clasificación de relevancia.

Uso:
    python query_ads.py <slug> [--rows N] [--no-chain] [--sweep]

Escribe build/<slug>/ads.json con la lista de registros (bibcode, título, autores,
año, abstract, arxiv_id, doctype, citation_count, topics, relevant, why_excluded —el motivo real
de exclusión si es no-core; lo consume el apéndice "Excluidos" de make_notes—, via) y, si la query directa
quedó truncada (numFound > --rows), la marca `truncated: {num_found, rows}` que el lint surface
como corpus incompleto (si no truncó, `truncated: null`).

Usa la API REST de ADS directamente (control total de campos y filas). Rate: ~5000/día.
La query por estrella se arma con `title:`/`abs:` sobre nombre+alias (ver `build_query`; `object:`
no es campo válido en la API Solr de ADS). Para temas, query Solr cruda de `topics.yaml`.

Tras la query directa hace **citation chaining** (snowballing): pide a ADS `references()` y
`citations()` de los papers core encontrados, **ancladas al sujeto** server-side —para ESTRELLAS el
`full:"nombre"` OR alias; para TEMAS la propia query del tema— (sin ese ancla el grafo devuelve los
mega-citados genéricos del área, no papers del sujeto), clasifica los candidatos con el mismo
`relevance.topics` y agrega los que resulten core (dedup por bibcode; provenance en el campo
`via`: `query` | `chain:references` | `chain:citations` | `manual`). Recupera papers que la query por
título/abstract pierde (p. ej. surveys que tabulan la estrella sin nombrarla en el abstract).
Sólo entran los core: los no-core encadenados no se agregan (inundarían el apéndice "Excluidos").
Desactivar con --no-chain. `--probe` no encadena (es sólo preview; lista TODO el core del corte).

**Curación manual persistente:** `extra_core: [bibcode, …]` en la entrada de `stars.yaml`/`topics.yaml`
lista papers que el clasificador perdió; se traen por bibcode, se marcan core (`via: manual`) y se
mergean. Vive en config (se commitea) → sobrevive al re-run, a diferencia de editar `build/` (scratch).

**`--sweep` (barrido full-text, paso 2b de ingest-star):** corre `full:` sobre nombre+aliases con
TODAS las variantes de espaciado y lista SÓLO los core que `build/<slug>/ads.json` no tiene — los
candidatos a `extra_core`. Preview como `--probe` (no baja nada ni escribe build/). Ver sweep_star.

**Cero espurio (#27):** la query DIRECTA de un sujeto corre con `expect_hits` — ADS devuelve
intermitentemente `numFound: 0` con HTTP 200; se reintenta con el mismo backoff y, si persiste, la
corrida **falla** (`EmptyResultError`, exit ≠ 0) en vez de persistir un `ads.json` vacío con exit 0
(que además pisaría el bueno de un re-ingest). Los ceros legítimos —chaining, `--sweep`, `--probe`,
`--extra-only`— no se tocan.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

import requests

import lib_config as cfg

API = "https://api.adsabs.harvard.edu/v1/search/query"
FIELDS = ("bibcode,title,author,year,pubdate,abstract,identifier,doctype,"
          "citation_count,bibstem,doi,keyword")

# Clasificación de relevancia: se LEE de vault/config/objective.yaml (el archivo que define
# el objetivo de la bóveda → qué paper es "core"). No hardcodear acá: editar el YAML.
_OBJ = cfg.load_objective()
_REL = (_OBJ.get("relevance") or {})
TOPIC_PATTERNS = {
    name: re.compile(pat, re.I)
    for name, pat in (_REL.get("topics") or {}).items()
}
NOISE_DOCTYPES = set(_REL.get("noise_doctypes") or [])
if not TOPIC_PATTERNS:
    raise RuntimeError(
        "vault/config/objective.yaml no define relevance.topics (el clasificador de papers core). "
        "Completalo antes de consultar ADS."
    )

# Regla de COMBINACIÓN de facetas — declarativa (objective.yaml), no hardcodeada (#15). El default
# histórico es OR (≥1 faceta cualquiera), calibrado para el pool chico de la query directa; el
# citation chaining amplía el pool a "todo lo que el grafo conecta y menciona al sujeto", mucho más
# ruidoso, y ahí una faceta laxa deja de discriminar (medido: exigir la faceta del eje recorta 928→254).
# La palanca es la OBLIGATORIEDAD, no podar regex. Cada instancia declara cuáles de SUS facetas son
# load-bearing sin tocar el framework:
#   relevance.require:    [faceta, ...]  → AND: TODAS deben matchear
#   relevance.min_topics: N              → al menos N facetas cualesquiera (default 1)
# Sin nada declarado (require=[], min_topics=1) se recupera exactamente el comportamiento de hoy.
def combination_rule(rel: dict, topic_names) -> tuple[list[str], int]:
    """(require, min_topics) validados desde relevance. `require` debe ⊆ topics: una faceta
    obligatoria inexistente filtraría TODO a no-core en silencio → falla ruidoso."""
    require = list(rel.get("require") or [])
    min_topics = rel.get("min_topics") or 1
    unknown = [t for t in require if t not in topic_names]
    if unknown:
        raise RuntimeError(
            f"vault/config/objective.yaml: relevance.require nombra facetas ausentes de "
            f"relevance.topics: {unknown}. Una faceta obligatoria que no existe filtraría TODO a "
            f"no-core en silencio."
        )
    return require, min_topics


REQUIRE_TOPICS, MIN_TOPICS = combination_rule(_REL, TOPIC_PATTERNS)


def exclusion_reason(topics: list[str], doctype: str) -> str | None:
    """Motivo por el que un paper queda FUERA del core (None = es core). ÚNICA implementación de
    la regla de relevancia: `classify` deriva su booleano de acá y `query_ads` persiste el motivo
    por registro en ads.json (`why_excluded`), del que lo lee el apéndice "Excluidos por el
    filtro" (make_notes). Sin esto, la dicotomía vieja "sin tópico"/doctype etiquetaba con un
    motivo FALSO (`doctype: article`) a los excluidos por la regla de combinación (#15) —
    require/min_topics con facetas matcheadas y doctype limpio (#30). Precedencia: sin tópico →
    doctype ruido → require → min_topics (las dos primeras preservan los rótulos históricos)."""
    if not topics:
        return "sin tópico"
    if doctype in NOISE_DOCTYPES:
        return f"doctype: {doctype}"
    missing = [t for t in REQUIRE_TOPICS if t not in topics]
    if missing:
        return f"sin faceta obligatoria ({', '.join(missing)}) — relevance.require"
    if len(topics) < MIN_TOPICS:
        return f"sólo {len(topics)} faceta(s), min_topics={MIN_TOPICS}"
    return None


def classify(rec: dict) -> tuple[list[str], bool]:
    """Devuelve (topics, relevant). Relevante ⟺ `exclusion_reason` no encuentra motivo de
    exclusión (≥ MIN_TOPICS facetas, TODAS las de REQUIRE_TOPICS y doctype no-ruido; con los
    defaults min_topics=1, require=[] es el histórico ≥1 faceta cualquiera)."""
    text = " ".join(filter(None, [
        " ".join(rec.get("title", []) or []),
        rec.get("abstract", "") or "",
        " ".join(rec.get("keyword", []) or []),
    ])).lower()
    topics = [t for t, pat in TOPIC_PATTERNS.items() if pat.search(text)]
    return topics, exclusion_reason(topics, rec.get("doctype", "")) is None


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


def query_ads(q: str, rows: int = 2000, quiet_truncate: bool = False,
              meta: dict | None = None, expect_hits: bool = False) -> list[dict]:
    """Corre una query Solr `q` ya armada contra ADS y devuelve registros clasificados.
    Para estrellas, armar `q` con build_query(names); para temas, usar la query cruda del topic.
    Reintenta con backoff ante 429/5xx y avisa si el resultado quedó truncado (numFound > rows;
    `quiet_truncate` lo silencia — en el chaining el truncado a top-por-citas es por diseño).

    `expect_hits=True` (sólo la query directa de un sujeto): trata `numFound == 0` como sospechoso
    —el cero espurio con HTTP 200 de #27— y lo reintenta con el mismo backoff; si persiste, levanta
    `EmptyResultError` en vez de devolver una lista vacía, para que la cadena aborte en vez de
    persistir un corpus vacío con exit 0.

    Si se pasa `meta` (dict mutable), se rellena con `num_found`/`rows`/`truncated` de ESTA corrida
    — así el caller persiste la marca de truncamiento (`build/<slug>/ads.json`) para que el lint la
    surface como backlog en vez de que el aviso muera en el stdout (#17). Se mantiene el tipo de
    retorno (lista) para no tocar al resto de los callers."""
    token = cfg.get_ads_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": q, "fl": FIELDS, "rows": rows,
              "sort": "citation_count desc", "fq": "database:astronomy"}
    for wait in (*RETRY_WAITS_S, None):
        resp = requests.get(API, headers=headers, params=params, timeout=60)
        if resp.status_code in RETRY_STATUS and wait is not None:
            print(f"  ADS HTTP {resp.status_code} — reintento en {wait} s")
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
            print(f"  ADS devolvió 0 resultados con HTTP 200 (cero espurio) — reintento en {wait} s")
            time.sleep(wait)
            continue
        break
    if expect_hits and num_found == 0:
        raise EmptyResultError(
            "ADS devolvió 0 resultados (HTTP 200) en todos los reintentos para la query directa:\n"
            f"  {q}\n"
            "Si el sujeto existe en ADS es el cero espurio de #27 (intermitente): re-corré, la "
            "cadena es idempotente. Si se repite, revisá el nombre/alias del sujeto en "
            "vault/config/stars.yaml (`ads_object`, `aliases`) o la `query` en topics.yaml.")
    truncated = num_found > rows
    if meta is not None:
        meta.update(num_found=num_found, rows=rows, truncated=truncated)
    if truncated and not quiet_truncate:
        print(f"  ⚠ truncado: ADS reporta {num_found} resultados y sólo se trajeron {rows} "
              f"(top por citas) — subí --rows para cubrir todo (queda marcado en ads.json → lint)")
    out = []
    for d in docs:
        topics, relevant = classify(d)
        why = None if relevant else exclusion_reason(topics, d.get("doctype", ""))
        out.append({
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
            "topics": topics,
            "relevant": relevant,
            "why_excluded": why,   # motivo real de exclusión (None si core) → apéndice "Excluidos"
        })
    return out


CHAIN_CHUNK = 40   # bibcodes por sub-query encadenada (mantiene la URL corta)


def chain_candidates(core_bibcodes: list[str], rows: int, subject_filter: str) -> list[dict]:
    """Citation chaining (snowballing) sobre el grafo de citas de ADS: `references()` (hacia atrás,
    qué citan los core) y `citations()` (hacia adelante, quién los cita). Un paper clave que se le
    escapó a la query directa casi seguro cita o es citado por alguno que sí entró.

    `subject_filter` (obligatorio) ancla cada sub-query al SUJETO server-side — para estrellas, el
    `full:` de nombre+alias (`build_fulltext_filter`). Sin él, el grafo de citas devuelve los
    mega-citados genéricos del área (Gaia, métodos, catálogos): matchean las facetas de
    `relevance.topics` pero no hablan del sujeto (medido: 31/31 falsos positivos en tau Ceti).

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


def _probe_row(r: dict) -> str:
    mark = "CORE" if r["relevant"] else "—   "
    tp = ",".join(r["topics"]) or "(ninguno)"
    cites = r.get("citation_count") or 0              # ADS puede devolver citation_count null
    title = " ".join((r.get("title") or "").split())[:68]
    return f"  [{mark}] {cites:>5}  {title}  «{tp}»"


def fetch_bibcodes(bibs: list[str]) -> list[dict]:
    """Trae registros ADS de una lista explícita de bibcodes (curación manual `extra_core`). Se
    marcan `relevant: True` a la fuerza (el usuario los declaró core: entraron porque el clasificador
    los perdió, no para re-juzgarlos) y `via: manual`."""
    out = []
    for i in range(0, len(bibs), CHAIN_CHUNK):
        chunk = bibs[i:i + CHAIN_CHUNK]
        q = " OR ".join(f'bibcode:"{b}"' for b in chunk)
        for r in query_ads(q, rows=len(chunk), quiet_truncate=True):
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
    names = [cfg.require_field(meta, "ads_object", name, "stars.yaml")] + meta.get("aliases", [])
    q = build_fulltext_filter(names)
    print(f"Barrido full-text (2b) de {name} — q: {q}")
    hits = query_ads(q, rows=rows)
    news = sorted((r for r in hits if r["relevant"] and r.get("bibcode") not in known),
                  key=lambda r: r.get("citation_count") or 0, reverse=True)
    print(f"  {len(hits)} papers con la estrella en el CUERPO · {len(news)} core NUEVOS "
          "(no están en ads.json)")
    for r in news:
        print(_probe_row(r))
    if news:
        print("\n  → revisá cuáles corresponden y agregalos a `extra_core: [<bibcode>, …]` en la "
              "entrada de la estrella en vault/config/stars.yaml (persistente, via: manual); después "
              "re-corré la cadena (idempotente). Los que decidas NO bajar, listalos en el log — no "
              "curar en silencio.")
    else:
        print("  → el corpus ya cubre el barrido full-text. (Ojo: en papers pre-digitales un 0 acá "
              "NO prueba ausencia — el OCR del escaneo pierde filas de tabla; ver skill ingest-star.)")
    return 0


def print_probe(q: str, recs: list, noncore_top: int = 25) -> int:
    """Modo preview del skill `setup`: muestra el corte core/no-core de una query sin bajar nada,
    para afinar la regla de relevancia (relevance.topics) contra papers reales. Lista **TODO el core**
    (no un top-N: papers recientes/poco citados caen al fondo del ranking pero pueden ser core); del
    no-core muestra sólo el top `noncore_top` por citas (chequeo de sanidad del corte). El barrido
    2b de ingest-star, que antes se hacía con probes manuales, hoy corre por --sweep (sweep_star)."""
    core = sorted((r for r in recs if r["relevant"]), key=lambda r: r.get("citation_count") or 0, reverse=True)
    noncore = sorted((r for r in recs if not r["relevant"]), key=lambda r: r.get("citation_count") or 0, reverse=True)
    print(f"Probe (no baja PDFs ni escribe build/). q: {q}")
    print(f"  {len(recs)} papers · {len(core)} CORE · {len(noncore)} no-core\n")
    print(f"  CORE (todos, por citas)  [tópicos que matchearon]:")
    for r in core:
        print(_probe_row(r))
    shown = noncore[:noncore_top]
    print(f"\n  no-core (top {len(shown)} de {len(noncore)}, chequeo de sanidad):")
    for r in shown:
        print(_probe_row(r))
    print("\n  → ajustá relevance.topics en objective.yaml y re-corré --probe hasta que el corte cierre.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?",
                    help="slug de estrella (o tema con --topic). Se omite con --probe.")
    ap.add_argument("--rows", type=int, default=2000,
                    help="tope de registros por query (default 2000 ≈ el máximo de una request ADS; "
                         "cubre la enorme mayoría de sujetos sin truncar). Si igual trunca, queda "
                         "marcado en build/<slug>/ads.json y el lint lo surface")
    ap.add_argument("--no-chain", action="store_true",
                    help="desactivar el citation chaining (references/citations de los papers core)")
    ap.add_argument("--topic", action="store_true",
                    help="el slug es un TEMA de vault/config/topics.yaml (query Solr cruda), no una estrella")
    ap.add_argument("--extra-only", action="store_true",
                    help="traer SÓLO los bibcodes de `extra_core` (sin query ni chaining) — la vía ADS "
                         "de un tema off-ADS MIXTO: su bibliografía canónica vive fuera de ADS (sin "
                         "`query`), pero los papers que SÍ tienen bibcode van en extra_core. "
                         "La corre ingest_topic.py solo.")
    ap.add_argument("--probe", metavar="QUERY",
                    help="PREVIEW (skill setup): corre una query Solr CRUDA y muestra el corte "
                         "core/no-core con títulos, clasificando con relevance.topics de objective.yaml. "
                         "No baja PDFs ni escribe build/ — sólo para afinar la regla de relevancia.")
    ap.add_argument("--sweep", action="store_true",
                    help="barrido full-text del paso 2b de ingest-star: corre full: sobre "
                         "nombre+aliases (todas las grafías, sin probes a mano) y lista SÓLO los "
                         "core que build/<slug>/ads.json no tiene — candidatos a extra_core en "
                         "stars.yaml. Preview: no baja nada ni escribe build/. Sólo estrellas.")
    args = ap.parse_args()

    if args.probe:
        return print_probe(args.probe, query_ads(args.probe, rows=args.rows))

    if not args.slug:
        ap.error('falta el slug (o usá --probe "<query>" para previsualizar la regla de relevancia)')
    if args.extra_only and not args.topic:
        ap.error("--extra-only es de temas (--topic): una estrella siempre tiene query (ads_object)")
    if args.sweep:
        if args.topic:
            ap.error("--sweep es de estrellas (surveys que tabulan la estrella sin nombrarla en "
                     "título/abstract); el análogo para temas es el retro-tag 3b del skill "
                     "ingest-topic (grep de aliases sobre el corpus local)")
        return sweep_star(args.slug, args.rows)

    if args.topic:
        _, meta = cfg.topic_by_slug(args.slug)
        if args.extra_only:
            # Tema MIXTO (off-ADS + extra_core): sin `query` no hay búsqueda ni chaining — la
            # única fuente ADS es la curación manual de `extra_core` (el bloque de abajo).
            q, chain_filter = None, None
            print(f"Consultando ADS (tema, sólo extra_core): {meta.get('title', args.slug)}")
            head = {"kind": "topic", "slug": args.slug, "title": meta.get("title"),
                    "concept": meta.get("concept"), "area": meta.get("area"), "query": None}
        else:
            q = cfg.require_field(meta, "query", args.slug, "topics.yaml",
                                  hint="Si es un tema off-ADS (source: web|local-pdfs) no va por "
                                       "query_ads: corré ingest_topic.py, que despacha por `source`.")
            # el "sujeto" de un tema es su propia query: anclar el chaining con ella deja on-topic a los
            # papers del grafo de citas (sin ancla traería los mega-citados genéricos, como en estrellas).
            chain_filter = f"({q})"
            print(f"Consultando ADS (tema): {meta.get('title', args.slug)}\n  q: {q}")
            head = {"kind": "topic", "slug": args.slug, "title": meta.get("title"),
                    "concept": meta.get("concept"), "area": meta.get("area"), "query": q}
    else:
        name, meta = cfg.star_by_slug(args.slug)
        names = [cfg.require_field(meta, "ads_object", name, "stars.yaml")] + meta.get("aliases", [])
        q = build_query(names)
        chain_filter = build_fulltext_filter(names)
        print(f"Consultando ADS: {name}  (nombres: {', '.join(names)})")
        head = {"kind": "star", "star": name, "slug": args.slug, "ads_object": meta["ads_object"]}

    qmeta: dict = {}                # truncamiento de la query DIRECTA (el chaining trunca por diseño)
    if q is None:
        recs, rel = [], []          # --extra-only: todo entra por el bloque extra_core de abajo
    else:
        # expect_hits: la query directa de un sujeto NO puede volver vacía — un 0 es el cero
        # espurio de ADS (#27) o un nombre mal escrito; en ambos casos abortar > persistir vacío.
        recs = query_ads(q, rows=args.rows, meta=qmeta, expect_hits=True)
        for r in recs:
            r["via"] = "query"
        rel = [r for r in recs if r["relevant"]]
        print(f"  query directa: {len(recs)} registros, {len(rel)} relevantes")

    if not args.no_chain and rel and chain_filter:
        seen = {r["bibcode"] for r in recs if r.get("bibcode")}
        core_bibs = [r["bibcode"] for r in rel if r.get("bibcode")]
        chained = []
        for c in chain_candidates(core_bibs, args.rows, chain_filter):
            b = c.get("bibcode")
            if c["relevant"] and b and b not in seen:   # sólo core nuevos (dedup vs query y entre ops)
                seen.add(b)
                chained.append(c)
        anchor = "full-text del sujeto" if not args.topic else "la query del tema"
        print(f"  chaining: +{len(chained)} core nuevos vía el grafo de citas de {len(core_bibs)} core "
              f"(anclado a {anchor})")
        recs += chained
        rel = [r for r in recs if r["relevant"]]

    # curación manual persistente: bibcodes en `extra_core` de stars.yaml/topics.yaml que el
    # clasificador perdió (build/ es scratch y se pisa; esto sobrevive porque vive en config).
    extra = [b for b in (meta.get("extra_core") or []) if b]
    if args.extra_only and not extra:
        sys.exit(f"--extra-only pero la entrada '{args.slug}' no declara `extra_core` en topics.yaml "
                 "— listá ahí los bibcodes ADS del tema mixto.")
    if extra:
        seen = {r["bibcode"] for r in recs if r.get("bibcode")}
        manual = [m for m in fetch_bibcodes(extra) if m.get("bibcode") and m["bibcode"] not in seen]
        print(f"  extra_core: +{len(manual)} curados a mano (de {len(extra)} en config)")
        recs += manual
        rel = [r for r in recs if r["relevant"]]

    recs.sort(key=lambda r: r.get("citation_count") or 0, reverse=True)
    print(f"  total: {len(recs)} registros, {len(rel)} relevantes")

    # marca de truncamiento de la query directa (sólo si realmente se cortó): persistida para que el
    # lint la surface como corpus incompleto. El truncado del chaining NO se registra (es por diseño).
    truncated = ({"num_found": qmeta["num_found"], "rows": qmeta["rows"]}
                 if qmeta.get("truncated") else None)
    if truncated:
        print(f"  ⚠ corpus truncado: ADS reporta {truncated['num_found']} y se trajeron "
              f"{truncated['rows']} — marcado en ads.json (el lint lo surface)")

    outdir = cfg.ROOT / "build" / args.slug
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {**head, "n_total": len(recs), "n_relevant": len(rel),
               "truncated": truncated, "records": recs}
    (outdir / "ads.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    print(f"  → {outdir / 'ads.json'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EmptyResultError as exc:   # #27: exit ≠ 0 → el orquestador aborta la cadena
        sys.exit(str(exc))
