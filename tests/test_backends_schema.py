"""Los backends de descubrimiento comparten UN schema de registro — como assert, no como prosa.

Los tres módulos (`query_ads`, `openalex`, `search_arxiv`) afirmaban en su docstring "el mismo
schema de registro", y a dos les faltaban las tres claves del **clasificador**. La consecuencia
medida: los consumidores que indexan con corchetes revientan y los que usan `.get()` dan falsos
limpios — `make_notes` marcaría toda nota `relevance: low`, sacándolas de `citation_index`, o sea
de la puerta 1 que esos backends existen para alimentar.

Una promesa compartida por N módulos se prueba **una vez, parametrizada**: agregar un backend
obliga a agregarlo acá, y el test dice qué clave falta.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

import openalex as oa
import query_ads as qa
import search_arxiv as sx

# El schema lo DEFINE `query_ads.to_records`, que es el original; los otros dos lo espejan.
CLAVES = {
    "bibcode", "title", "authors", "year", "pubdate", "abstract", "arxiv_id", "doi",
    "doctype", "bibstem", "citation_count", "keyword", "facets", "relevant", "why_excluded",
}

_ATOM = """<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry><id>http://arxiv.org/abs/1404.2986v3</id><published>2014-04-10T18:00:00Z</published>
  <title>T</title><summary>S</summary><author><name>J Shlens</name></author>
  <category term="cs.LG"/></entry></feed>"""

_OA_WORK = {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/a", "title": "T",
            "publication_year": 2000, "cited_by_count": 3, "type": "article",
            "authorships": [{"author": {"display_name": "P Comon"}}],
            "primary_location": {"source": {"display_name": "Signal Processing"}}}


def _ads():
    docs = [{"bibcode": "2020X....1..1X", "title": ["T"], "abstract": "S", "year": "2020",
             "doctype": "article", "author": ["A"], "citation_count": 3}]
    return qa.to_record(docs[0])


BACKENDS = [
    ("query_ads", _ads),
    ("openalex", lambda: oa.to_record(_OA_WORK)),
    ("search_arxiv", lambda: sx.to_record(ET.fromstring(_ATOM).findall("a:entry", sx.NS)[0])),
]


@pytest.mark.parametrize("nombre,hacer", BACKENDS, ids=[b[0] for b in BACKENDS])
def test_el_registro_tiene_exactamente_las_claves_del_schema(nombre, hacer, toy_vault):
    rec = hacer()
    faltan, sobran = CLAVES - set(rec), set(rec) - CLAVES
    assert not faltan, f"{nombre}: faltan {sorted(faltan)}"
    # `via`/`openalex_id` son extras legítimos (procedencia); cualquier otra sobra es divergencia.
    assert not (sobran - {"via", "openalex_id"}), f"{nombre}: claves fuera del schema {sorted(sobran)}"


@pytest.mark.parametrize("nombre,hacer", BACKENDS, ids=[b[0] for b in BACKENDS])
def test_el_veredicto_del_clasificador_tiene_el_tipo_correcto(nombre, hacer, toy_vault):
    """`relevant` bool y `facets` lista: un `None` acá haría que el consumidor lo lea como no-core
    en vez de romper, que es el falso limpio."""
    rec = hacer()
    assert isinstance(rec["relevant"], bool), f"{nombre}: relevant={rec['relevant']!r}"
    assert isinstance(rec["facets"], list), f"{nombre}: facets={rec['facets']!r}"
    assert rec["why_excluded"] is None or isinstance(rec["why_excluded"], str)
