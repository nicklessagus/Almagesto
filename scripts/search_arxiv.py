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
