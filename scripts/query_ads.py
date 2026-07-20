"""Consulta NASA ADS por estrella → metadata de papers + clasificación de relevancia.

Uso:
    python query_ads.py <slug> [--rows N] [--no-chain]

Escribe build/<slug>/ads.json con la lista de registros (bibcode, título, autores,
año, abstract, arxiv_id, doctype, citation_count, topics, relevant, via) y, si la query directa
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


def classify(rec: dict) -> tuple[list[str], bool]:
    """Devuelve (topics, relevant). Relevante si matchea ≥1 topic y no es doctype ruido."""
    text = " ".join(filter(None, [
        " ".join(rec.get("title", []) or []),
        rec.get("abstract", "") or "",
        " ".join(rec.get("keyword", []) or []),
    ])).lower()
    topics = [t for t, pat in TOPIC_PATTERNS.items() if pat.search(text)]
    doctype = rec.get("doctype", "")
    relevant = bool(topics) and doctype not in NOISE_DOCTYPES
    return topics, relevant


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


def query_ads(q: str, rows: int = 2000, quiet_truncate: bool = False,
              meta: dict | None = None) -> list[dict]:
    """Corre una query Solr `q` ya armada contra ADS y devuelve registros clasificados.
    Para estrellas, armar `q` con build_query(names); para temas, usar la query cruda del topic.
    Reintenta con backoff ante 429/5xx y avisa si el resultado quedó truncado (numFound > rows;
    `quiet_truncate` lo silencia — en el chaining el truncado a top-por-citas es por diseño).

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
        break
    try:
        response = resp.json()["response"]
        docs = response["docs"]
    except (ValueError, KeyError) as exc:   # cuerpo de error con 200 / formato inesperado
        raise RuntimeError(f"Respuesta inesperada de ADS (sin response.docs): {resp.text[:200]}") from exc
    num_found = response.get("numFound", len(docs))
    truncated = num_found > rows
    if meta is not None:
        meta.update(num_found=num_found, rows=rows, truncated=truncated)
    if truncated and not quiet_truncate:
        print(f"  ⚠ truncado: ADS reporta {num_found} resultados y sólo se trajeron {rows} "
              f"(top por citas) — subí --rows para cubrir todo (queda marcado en ads.json → lint)")
    out = []
    for d in docs:
        topics, relevant = classify(d)
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
            r["via"] = "manual"
            out.append(r)
        time.sleep(1.0)
    return out


def print_probe(q: str, recs: list, noncore_top: int = 25) -> int:
    """Modo preview del skill `setup`: muestra el corte core/no-core de una query sin bajar nada,
    para afinar la regla de relevancia (relevance.topics) contra papers reales. Lista **TODO el core**
    (el barrido full-text 2b de ingest-star necesita ver el core completo, no un top-N — papers
    recientes/poco citados caen al fondo del ranking pero pueden ser core); del no-core muestra sólo
    el top `noncore_top` por citas (chequeo de sanidad del corte)."""
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
    args = ap.parse_args()

    if args.probe:
        return print_probe(args.probe, query_ads(args.probe, rows=args.rows))

    if not args.slug:
        ap.error('falta el slug (o usá --probe "<query>" para previsualizar la regla de relevancia)')
    if args.extra_only and not args.topic:
        ap.error("--extra-only es de temas (--topic): una estrella siempre tiene query (ads_object)")

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
        recs = query_ads(q, rows=args.rows, meta=qmeta)
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
    sys.exit(main())
