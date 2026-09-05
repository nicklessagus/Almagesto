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
    # #179 · `puertas` (#126) entra al schema COMPARTIDO. Vivía sólo en `reclassify_for_theme`, que
    # es no-op para un tema sin `facet:`, así que el campo aparecía o no según el camino — y
    # CLAUDE.md promete que **existe siempre**, para que «no consta» y «ninguna puerta» no se
    # confundan. Si vive en el schema, los tres backends lo emiten y este test lo fija (red #2).
    "puertas",
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


@pytest.mark.parametrize("nombre,hacer,ausente", [
    ("query_ads", lambda: qa.to_record({"bibcode": "2020X....1..1X", "title": ["T"],
                                        "year": "2020", "doctype": "article"}), None),
    ("openalex", lambda: oa.to_record({k: v for k, v in _OA_WORK.items()
                                       if k != "cited_by_count"}), None),
    ("search_arxiv", lambda: sx.to_record(ET.fromstring(_ATOM).findall("a:entry", sx.NS)[0]), None),
], ids=["query_ads", "openalex", "search_arxiv"])
def test_citation_count_ausente_es_None_no_cero(nombre, hacer, ausente, toy_vault):
    """AUD-166 / INV-69 — la clave AUSENTE es «no consta», nunca «cero citas».

    Un `0` afirma «no lo cita nadie» sobre un dato que nadie miró, y aguas abajo la puerta 2 de
    D-26 (`citation_count >= umbral`) lo lee como «no es fundacional»: excluye por construcción
    justo a los papers que esa puerta existe para dejar entrar. `search_arxiv` escribía la regla
    correcta —y su motivo— desde que nació, y los otros dos la contraria: dos backends del mismo
    schema con contratos opuestos es exactamente lo que la red #2 existe para cazar."""
    assert hacer()["citation_count"] is ausente


# ── red #2 · `cfg.flags_usados`: una implementación, siete clientes ──────────

FLAGS_CLIENTES = ["fetch_pdf", "extract_fulltext", "fetch_ground_truth", "check_retractions",
                  "fetch_arxiv", "make_notes", "query_ads"]


def _escenario(modulo: str, monkeypatch) -> list:
    """The cheapest argv that drives `<modulo>.main()` to its `cfg.save_paso` with ONE
    non-default flag set, with every network/tool boundary patched out. Returns the argv."""
    import json
    import shutil
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text(json.dumps({"records": [], "star": "Test Star"}),
                                    encoding="utf-8")
    monkeypatch.setattr(cfg, "get_ads_token", lambda: "tok")
    if modulo in ("fetch_pdf", "fetch_arxiv"):
        return ["test_star", "--limit", "1"]
    if modulo == "extract_fulltext":
        (cfg.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
        return ["test_star", "--force"]
    if modulo == "fetch_ground_truth":
        import fetch_ground_truth as gt
        monkeypatch.setattr(gt, "fetch_pscomppars", lambda host: [])
        monkeypatch.setattr(gt, "fetch_host", lambda host, tab: {})
        monkeypatch.setattr(gt, "fetch_planets", lambda tab, mass: [])
        monkeypatch.setattr(gt, "unresolved_aliases", lambda host, aliases: [])
        monkeypatch.setattr(gt, "simbad_identifiers", lambda host: None)
        return ["test_star", "--force"]
    if modulo == "check_retractions":
        import check_retractions as cr
        from conftest import mk_note
        mk_note(cfg.PAPERS, "2020ok....1..1X",
                {"bibcode": "2020ok....1..1X", "title": "Sano", "doi": "10.1/ok", "tags": ["paper"]})
        (build / "ads.json").write_text(
            json.dumps({"records": [{"bibcode": "2020ok....1..1X", "relevant": True}]}),
            encoding="utf-8")
        monkeypatch.setattr(cr, "crossref_retraction", lambda doi, headers: (None, [], "ok"))
        return ["--slug", "test_star", "--force"]
    if modulo == "make_notes":
        return ["test_star", "--all"]
    if modulo == "query_ads":
        monkeypatch.setattr(qa, "sweep_star", lambda slug, rows: 0)
        return ["test_star", "--sweep"]
    raise AssertionError(modulo)


@pytest.mark.parametrize("modulo", FLAGS_CLIENTES)
def test_cada_script_estampa_sus_flags_via_la_implementacion_unica(modulo, toy_vault, monkeypatch):
    """`_flags_usados` vivía copiada en los siete (seis idénticas y una con `chr(95)/chr(45)`), y
    las siete tenían **el mismo agujero**: sólo miraban `v is True`. Red #2 — si N módulos prometen
    la misma forma, se prueba una vez parametrizada. El test anterior leía el TEXTO FUENTE del
    wrapper (AUD, frente D); éste mira el comportamiento: `main()` llega a `cfg.save_paso` con
    `flags=` calculado por `cfg.flags_usados`, y el flag no-default que se pasó está adentro."""
    import importlib
    import sys
    m = importlib.import_module(modulo)
    argv = _escenario(modulo, monkeypatch)
    flag = next(a for a in argv if a.startswith("--") and a != "--slug")
    llamadas: list = []
    real = cfg.flags_usados

    def espia(args, ap=None, **kw):
        out = real(args, ap, **kw)
        llamadas.append(out)
        return out

    monkeypatch.setattr(cfg, "flags_usados", espia)
    estampas: list = []
    monkeypatch.setattr(cfg, "save_paso",
                        lambda slug, paso, flags=None, **kw: estampas.append((paso, flags)))
    monkeypatch.setattr(sys, "argv", [f"{modulo}.py", *argv])
    assert m.main() == 0
    assert estampas, f"{modulo}.main() no llegó a `cfg.save_paso`"
    assert llamadas, f"{modulo}.main() no pasó por `cfg.flags_usados`"
    paso, flags = estampas[-1]
    assert paso == modulo
    assert flags == llamadas[-1], "los flags estampados no son los que devolvió `cfg.flags_usados`"
    assert any(f.startswith(flag) for f in flags), f"{flag!r} no quedó en {flags!r}"


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
