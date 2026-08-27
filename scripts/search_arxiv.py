"""Backend de descubrimiento sobre la API Atom de arXiv (sin key, sin cuenta).

Complementa a ADS en el eje **tema**: un tema de método —estadística, ML, signal processing— tiene
su bibliografía reciente en arXiv antes (o en vez) de en ADS. Normaliza al **mismo schema de
registro** que `query_ads` y `openalex`, para que la lente de `objective.yaml` clasifique los tres
backends sin adaptadores: en cuanto un backend trae su propio schema, trae también su propio
clasificador, y la bóveda deja de tener una sola definición de "core".

⚠ **Rate limit**: arXiv pide 1 request cada 3 s. `search()` hace **una** request y **no duerme**;
el que la llame en bucle tiene que espaciar (`fetch_arxiv` sí lo hace, con `SLEEP_S = 3.0`). Decía
"mismo que fetch_arxiv" y era falso: este módulo ni importaba `time`.
"""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET

import requests

import lib_config as cfg

API = "https://export.arxiv.org/api/query"
TIMEOUT = 60
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
HEADERS = {"User-Agent": f"Almagesto/{cfg.ALMAGESTO_VERSION} (academic literature vault)"}

_VERSION_RE = re.compile(r"v\d+$")


def _texto(el) -> str:
    """El texto de un nodo Atom, colapsado. arXiv **hard-wrapea** títulos y abstracts: sin esto,
    un título llega con saltos de línea y sangría y no matchea ninguna regex de la lente."""
    return " ".join((el.text or "").split()) if el is not None else ""


def _arxiv_id(url: str) -> str | None:
    """`http://arxiv.org/abs/1404.2986v3` → `1404.2986`.

    La versión se **descarta**: `v1` y `v3` son revisiones del MISMO trabajo, y la identidad de un
    paper es su `doi`/`arxiv_id` (D-19). Conservarla crearía dos notas para un solo trabajo, que es
    justo el doble conteo que esa decisión cerró."""
    if not url:
        return None
    ident = url.rstrip("/").split("/abs/")[-1]
    return _VERSION_RE.sub("", ident) or None


def _citekey(anio, autores: list) -> str | None:
    """Clave sintética `AAAA+Autor`, la convención del modo off-ADS (arXiv no da bibcodes)."""
    if not anio or not autores:
        return None
    apellido = re.sub(r"[^A-Za-zÀ-ÿ]", "", (autores[0] or "").split()[-1] if autores[0] else "")
    return f"{anio}{apellido}" if apellido else None


def to_record(entry) -> dict:
    """Normaliza una `<entry>` del feed al schema de registro compartido."""
    autores = [_texto(n) for n in entry.findall("a:author/a:name", NS)]
    published = _texto(entry.find("a:published", NS))
    anio = int(published[:4]) if published[:4].isdigit() else None
    doi = _texto(entry.find("arxiv:doi", NS)) or None
    cats = [c.get("term") for c in entry.findall("a:category", NS) if c.get("term")]
    rec = {
        "bibcode": _citekey(anio, autores),
        "title": _texto(entry.find("a:title", NS)),
        "authors": autores,
        "year": anio,
        "pubdate": published[:10] or None,
        "abstract": _texto(entry.find("a:summary", NS)),
        "arxiv_id": _arxiv_id(_texto(entry.find("a:id", NS))),
        "doi": doi,
        "doctype": "eprint",
        "bibstem": "arXiv",
        # arXiv NO publica el conteo de citas. Va `None` = «no lo sé», nunca 0: un 0 afirma
        # «no lo cita nadie» sobre un dato que nadie miró, y aguas abajo la puerta 2 de D-26
        # (`citation_count >= umbral`) lo leería como «no es fundacional» — excluyendo por
        # construcción justo a los papers que esa puerta existe para dejar entrar.
        "citation_count": None,
        "keyword": cats,          # las categorías SON las keywords que la lente puede leer
        "via": "arxiv",
    }
    # Las tres claves del CLASIFICADOR. Sin ellas el registro no es del mismo schema y los
    # consumidores o revientan (indexan con corchetes) o dan falsos limpios: `core` vacío en
    # `ingest_theme`, y toda nota naciendo `relevance: low` en `make_notes` — lo que encima
    # las excluye de `citation_index.corpus_idents`, o sea de la puerta 1 que estos backends
    # existen para alimentar. Se clasifica acá con `classify_record`, la ÚNICA lente.
    import query_ads
    facets, relevant = query_ads.classify_record(rec)
    rec["facets"], rec["relevant"] = facets, relevant
    # #126/#179: el schema declara `puertas` SIEMPRE (lista vacía = ninguna), así que «no
    # consta» y «ninguna puerta» no se confunden. Lo fija `tests/test_backends_schema.py`.
    rec["puertas"] = []
    # #86: se juzgó sin abstract (título + keywords y nada más). Mismo schema que
    # `query_ads.to_record`, que es quien lo define — la paridad la fija un test.
    rec["sin_abstract"] = not (rec.get("abstract") or "").strip()
    rec["why_excluded"] = None if relevant else query_ads.exclusion_reason(
        facets, rec.get("doctype") or "")
    return rec



def search(query: str, categories: list | None = None, rows: int = 100) -> list:
    """Busca en arXiv y devuelve registros normalizados. `categories` acota por `cat:`."""
    q = f"all:{query}" if ":" not in query else query
    if categories:
        q = f"({q}) AND ({' OR '.join(f'cat:{c}' for c in categories)})"
    url = f"{API}?{urllib.parse.urlencode({'search_query': q, 'max_results': rows})}"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return [to_record(e) for e in ET.fromstring(r.text).findall("a:entry", NS)]


def main(argv=()) -> int:
    """CLI de exploración — **preview, no ingesta**: imprime lo que la query trae y cómo lo
    clasifica la lente de `objective.yaml`, sin escribir nada en la bóveda.

    Por qué existe (#95): el módulo estaba implementado y testeado, y `CLAUDE.md` lo nombra como uno
    de los backends de descubrimiento fuera de ADS, pero **no tenía ningún llamador ni forma de
    invocarlo** — la promesa se leía como capacidad vigente y no había manera de ejercerla. Esto no
    lo cablea a la cadena de ingest (esa es una decisión aparte, con su alcance por definir): lo hace
    **usable y auditable**, que es lo que faltaba para poder decidir con datos si vale cablearlo.

    Es el gemelo de `query_ads --probe`: mismo trabajo, otro backend."""
    import argparse
    import query_ads
    ap = argparse.ArgumentParser(description="Preview de una query a arXiv (no escribe nada).")
    ap.add_argument("query", help='query en sintaxis arXiv, p. ej. "independent component analysis"')
    ap.add_argument("--categories", default=None,
                    help="categorías arXiv separadas por coma (p. ej. astro-ph.EP,stat.ML)")
    ap.add_argument("--rows", type=int, default=25)
    args = ap.parse_args(list(argv))
    cats = [c.strip() for c in args.categories.split(",")] if args.categories else None
    recs = search(args.query, categories=cats, rows=args.rows)
    core = 0
    for r in recs:
        # ⛔ #173: acá había `query_ads.classify(r)`, y `r` es un registro YA normalizado por
        # `to_record`, donde `title` es un **string**. `classify` hace
        # `" ".join(cfg.as_list(rec.get("title")))` y `as_list("…") == []`, así que el título se
        # DESCARTABA: el preview contradecía el veredicto que `to_record` acababa de calcular, y
        # justo para el caso que D-26 documenta (un fundacional que se reconoce por el título,
        # Hyvärinen/ICA). La función para un registro persistido es `classify_record` — la misma que
        # usa `to_record`, que es lo que hace que core sea función de `(paper, lente)` y no del
        # backend (INV-24 / INV-96).
        facets, relevante = query_ads.classify_record(r)
        r["facets"], r["relevant"] = facets, relevante
        core += bool(relevante)
        motivo = None if relevante else query_ads.exclusion_reason(facets, r.get("doctype") or "")
        marca = "core" if relevante else f"—    ({motivo or 'no matchea la lente'})"
        cfg.print_seguro(f"  [{marca}] {r.get('arxiv_id') or r.get('citekey')}  {(r.get('title') or '')[:70]}")
    cfg.print_seguro(f"\n{len(recs)} resultados · {core} core con la lente vigente. "
                     "Preview: no se bajó ni se escribió nada.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
