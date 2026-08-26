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

import argparse
import inspect
import xml.etree.ElementTree as ET

import pytest

import lib_config as cfg
import openalex as oa
import query_ads as qa
import search_arxiv as sx

# El schema lo DEFINE `query_ads.to_records`, que es el original; los otros dos lo espejan.
CLAVES = {
    "bibcode", "title", "authors", "year", "pubdate", "abstract", "arxiv_id", "doi",
    "doctype", "bibstem", "citation_count", "keyword", "facets", "relevant", "why_excluded",
    "sin_abstract",
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
    # @inv INV-96
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


# ── red #2 · `_flags_usados`: una implementación, siete clientes ────────────

FLAGS_CLIENTES = ["fetch_pdf", "extract_fulltext", "fetch_ground_truth", "check_retractions",
                  "fetch_arxiv", "make_notes", "query_ads"]


@pytest.mark.parametrize("modulo", FLAGS_CLIENTES)
def test_flags_usados_delega_en_la_implementacion_unica(modulo):
    """Vivía copiada en los siete (seis idénticas y una con `chr(95)/chr(45)`), y las siete tenían
    **el mismo agujero**: sólo miraban `v is True`. Red #2 — si N módulos prometen la misma forma,
    se prueba una vez parametrizada, no con prosa en N docstrings."""
    import importlib
    m = importlib.import_module(modulo)
    fuente = inspect.getsource(m._flags_usados)
    assert "cfg.flags_usados(args, ap)" in fuente, (
        f"{modulo}._flags_usados reimplementa en vez de delegar:\n{fuente}")


def test_flags_usados_registra_el_flag_con_valor():
    """`--limit` es el flag que MÁS cambia lo que la corrida hizo —con `--limit 1` sobre cuatro
    pendientes, tres papers no se intentaron siquiera— y no se registraba: la traza decía "corrió
    fetch_pdf" igual que una corrida completa."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--rows", type=int, default=2000)
    assert cfg.flags_usados(ap.parse_args([]), ap) == []
    assert cfg.flags_usados(ap.parse_args(["--limit", "1"]), ap) == ["--limit=1"]
    assert cfg.flags_usados(ap.parse_args(["--force", "--rows", "5000"]), ap) == \
        ["--force", "--rows=5000"]
    assert cfg.flags_usados(ap.parse_args(["--rows", "2000"]), ap) == [], "el default no es escotilla"


def test_flags_usados_sin_parser_solo_booleanos():
    """Sin el parser no se puede saber qué valor es default y cuál lo pusieron a mano. Degradar a
    "todos los valores" llenaría la traza de ruido constante; se degrada a los booleanos, que es lo
    que siempre se supo."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--rows", type=int, default=2000)
    assert cfg.flags_usados(ap.parse_args(["--force", "--rows", "9"])) == ["--force"]
