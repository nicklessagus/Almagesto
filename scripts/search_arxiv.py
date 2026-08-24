"""Backend de descubrimiento sobre la API Atom de arXiv (sin key, sin cuenta).

Complementa a ADS en el eje **tema**: un tema de método —estadística, ML, signal processing— tiene
su bibliografía reciente en arXiv antes (o en vez) de en ADS. Normaliza al **mismo schema de
registro** que `query_ads` y `openalex`, para que la lente de `objective.yaml` clasifique los tres
backends sin adaptadores: en cuanto un backend trae su propio schema, trae también su propio
clasificador, y la bóveda deja de tener una sola definición de "core".

Rate limit de arXiv: 1 request cada 3 s (mismo que `fetch_arxiv`).
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
    return {
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
        "citation_count": 0,      # arXiv no lo publica; queda en 0, no en None (schema compartido)
        "keyword": cats,          # las categorías SON las keywords que la lente puede leer
        "via": "arxiv",
    }


def search(query: str, categories: list | None = None, rows: int = 100) -> list:
    """Busca en arXiv y devuelve registros normalizados. `categories` acota por `cat:`."""
    q = f"all:{query}" if ":" not in query else query
    if categories:
        q = f"({q}) AND ({' OR '.join(f'cat:{c}' for c in categories)})"
    url = f"{API}?{urllib.parse.urlencode({'search_query': q, 'max_results': rows})}"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return [to_record(e) for e in ET.fromstring(r.text).findall("a:entry", NS)]
