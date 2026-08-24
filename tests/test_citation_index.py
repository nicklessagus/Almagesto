"""citation_index: índice invertido obra-citada → papers del corpus que la citan.

Insumo de la **puerta 1** de D-26 (INV-88): un trabajo que citan N papers core es un CANDIDATO del
triage, nunca core automático. La red se falsea siempre: `build` recibe los dos fetchers inyectados.
"""
from __future__ import annotations

import json

import pytest

import citation_index as ci
import lib_config as cfg
from conftest import mk_note


def paper(stem, doi=None, arxiv=None, relevance="high", **extra):
    fm = {"tags": ["paper"], "bibcode": stem, "title": stem, "relevance": relevance,
          "doi": doi, "arxiv_id": arxiv, **extra}
    mk_note(cfg.PAPERS, stem, fm)


def fetchers(ads_map=None, oa_map=None, oa_sin=None):
    """Fetchers deterministas que reemplazan la red.

    ⚠ El de OpenAlex normaliza la clave con `_bare_doi`, **igual que la función real que
    reemplaza**. Antes indexaba por el input verbatim, y esa diferencia de contrato entre el doble
    y el original era exactamente el bug B2: escondía que `build` consultaba con el DOI crudo."""
    import openalex as _oa_mod

    def _ads(bibcodes):
        return {b: list(ads_map.get(b, [])) for b in bibcodes if b in (ads_map or {})}

    def _oa(dois):
        norm = {_oa_mod._bare_doi(d) for d in dois}
        m = {k: list(v) for k, v in (oa_map or {}).items() if k in norm}
        return m, sorted(norm - set(m))
    return _ads, _oa


# ── el índice ────────────────────────────────────────────────────────────────

def test_indice_invertido_es_exacto(toy_vault, tmp_path):
    """Patrón Censo: se comparan los STEMS, no los conteos — dos papers distintos citando la misma
    obra y un conteo igual pueden ser dos índices distintos."""
    paper("2020A", doi="10.1/a")
    paper("2020B", doi="10.1/b")
    paper("2020C", doi="10.1/c")
    ads, oa = fetchers(
        ads_map={"2020A": ["1994Comon..X"], "2020B": ["1994Comon..X", "1999Hyva...Y"]},
        oa_map={"10.1/c": ["W1994", "W1999"]})
    out = ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa)
    idx = ci.load(out)
    assert ci.cited_by_corpus("1994Comon..X", idx) == ["2020A", "2020B"]
    assert ci.cited_by_corpus("1999Hyva...Y", idx) == ["2020B"]
    assert ci.cited_by_corpus("W1994", idx) == ["2020C"]
    assert ci.cited_by_corpus("no-citada-por-nadie", idx) == []


def test_solo_los_core_entran(toy_vault, tmp_path):
    """La puerta 1 pregunta «cuántos papers CORE lo citan». Un `relevance: low` no vota."""
    paper("2020Core", doi="10.1/core")
    paper("2020Low", doi="10.1/low", relevance="low")
    ads, oa = fetchers(oa_map={"10.1/core": ["W1"], "10.1/low": ["W1"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    assert ci.cited_by_corpus("W1", idx) == ["2020Core"]


def test_las_dos_fuentes_se_unen_por_paper(toy_vault, tmp_path):
    """R-9: ADS gana en astro y OpenAlex en no-astro, así que el mismo paper puede tener
    referencias en las dos. Se unen, sin duplicar la obra que las dos reportan."""
    paper("2020A", doi="10.1/a")
    ads, oa = fetchers(ads_map={"2020A": ["1994Comon..X"]},
                       oa_map={"10.1/a": ["W1994", "W1999"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    assert sorted(idx["citas"]) == ["1994Comon..X", "W1994", "W1999"]


def test_cobertura_declarada(toy_vault, tmp_path):
    """INV-87 y la medición de R-9: el techo de la unión fue 83% sobre un corpus real. Un índice
    que no dice de cuántos papers pudo leer referencias se lee como completo."""
    paper("2020Con", doi="10.1/con")
    paper("2020Sin", doi="10.1/sin")
    paper("2020NiDoi")                      # sin doi y sin refs en ADS: ciego para las dos fuentes
    ads, oa = fetchers(oa_map={"10.1/con": ["W1"]}, )
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    cob = idx["cobertura"]
    assert cob["n_core"] == 3
    assert cob["con_referencias"] == 1
    assert sorted(cob["ciegos"]) == ["2020NiDoi", "2020Sin"], "los ciegos van NOMBRADOS, no contados"
    assert cob["sin_clave"] == []


def test_paper_sin_clave_se_cuenta_aparte(toy_vault, tmp_path):
    """Medido contra la API real: `openalex.to_record` devuelve `bibcode: None` para una obra sin
    autor listado (1 de 60). No se saltea en silencio: se cuenta y se nombra."""
    paper("2020A", doi="10.1/a")
    mk_note(cfg.PAPERS, "sin_clave", {"tags": ["paper"], "bibcode": None, "relevance": "high"})
    ads, oa = fetchers(oa_map={"10.1/a": ["W1"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    assert idx["cobertura"]["sin_clave"] == ["sin_clave"]
    assert idx["cobertura"]["n_core"] == 1, "el que no tiene clave no cuenta como core medible"


# ── determinismo y offline ───────────────────────────────────────────────────

def test_determinista_byte_a_byte(toy_vault, tmp_path):
    paper("2020A", doi="10.1/a")
    paper("2020B", doi="10.1/b")
    ads, oa = fetchers(ads_map={"2020B": ["X2", "X1"]}, oa_map={"10.1/a": ["W2", "W1"]})
    a = (tmp_path / "1.json"); b = (tmp_path / "2.json")
    ci.build(a, fetch_ads=ads, fetch_oa=oa)
    ci.build(b, fetch_ads=ads, fetch_oa=oa)
    assert a.read_bytes() == b.read_bytes()


def test_lookup_es_offline(toy_vault, tmp_path, monkeypatch):
    """El lookup lo consume el triage en cada corrida: si tocara la red, la compuerta dependería
    de que OpenAlex esté de buen humor — y hoy midiendo dio 504 a rachas."""
    paper("2020A", doi="10.1/a")
    ads, oa = fetchers(oa_map={"10.1/a": ["W1"]})
    out = ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa)
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("el lookup tocó la red"))
    idx = ci.load(out)
    assert ci.cited_by_corpus("W1", idx) == ["2020A"]


def test_vive_en_build_no_en_el_vault(toy_vault, tmp_path):
    """Regla de oro del registro: `build/` guarda lo regenerable. El índice se recupera pidiéndolo
    de nuevo a las APIs, así que no va al vault ni al versionado."""
    paper("2020A", doi="10.1/a")
    ads, oa = fetchers(oa_map={"10.1/a": ["W1"]})
    out = ci.build(fetch_ads=ads, fetch_oa=oa)
    assert out.is_relative_to(cfg.ROOT / "build")
    assert not out.is_relative_to(cfg.VAULT)



# ── la puerta 1: un trabajo tiene varias llaves, y el corpus puede citarlo por cualquiera ─────

def test_lookup_acepta_las_varias_llaves_del_mismo_trabajo(toy_vault, tmp_path):
    """La puerta 1 pregunta «¿alguien de mi corpus cita a ESTE candidato?». El candidato llega con
    bibcode Y doi, y el índice tiene dos espacios de identificadores —ADS devuelve bibcodes,
    OpenAlex ids `W…`— así que preguntar por una sola llave da un **falso negativo**: el corpus lo
    cita, pero por la otra vía. Medido sobre datos reales: Zechmeister & Kürster 2009 aparecía como
    `2009A&A...496..577Z` (94 citadores) **y** como `W4292309267` (82), el mismo trabajo."""
    paper("2020A", doi="10.1/a")
    paper("2020B", doi="10.1/b")
    ads, oa = fetchers(ads_map={"2020A": ["2009BIB"]}, oa_map={"10.1/b": ["W99"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    # el candidato es el mismo trabajo, conocido por sus dos llaves
    assert ci.cited_by_corpus(["2009BIB", "W99"], idx) == ["2020A", "2020B"]
    assert ci.cited_by_corpus(["2009BIB"], idx) == ["2020A"]
    assert ci.cited_by_corpus(["no", "tampoco"], idx) == []


def test_lookup_con_una_sola_llave_sigue_andando(toy_vault, tmp_path):
    """Compatibilidad de uso, no de schema: pasar un string es el caso común."""
    paper("2020A", doi="10.1/a")
    ads, oa = fetchers(oa_map={"10.1/a": ["W1"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    assert ci.cited_by_corpus("W1", idx) == ["2020A"]


# ── B2/B3/B4: las llaves tienen que normalizarse igual de los dos lados ───────────────────────

def test_doi_con_prefijo_no_se_reporta_como_ciego(toy_vault, tmp_path):
    """Bug medido por la auditoría: `refs_of` devuelve el mapa con la clave **normalizada**
    (`_bare_doi`) y `build` lo consultaba con el `doi` **crudo** del frontmatter. Un paper con
    `doi: https://doi.org/10.1/a` quedaba en `cobertura.ciegos` — o sea que el artefacto declaraba
    *"OpenAlex no tenía referencias para éste"* cuando el código había mirado la clave equivocada.
    Peor que una cobertura faltante: cobertura **mal atribuida**."""
    paper("2020A", doi="https://doi.org/10.1/A")
    ads, oa = fetchers(oa_map={"10.1/a": ["W1"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    assert idx["cobertura"]["ciegos"] == []
    assert ci.cited_by_corpus("W1", idx) == ["2020A"]


def test_la_cobertura_declara_lo_que_openalex_no_resolvio(toy_vault, tmp_path):
    """`refs_of` calcula los no-resueltos «porque sin él un mapa incompleto se lee como completo»
    y `build` los tiraba (`oa_refs, _oa_sin = ...`). El módulo que exige declarar el techo estaba
    tirando la mitad del techo: un paper con refs de ADS cuyo DOI OpenAlex no resolvió no es
    `ciego`, así que su cobertura parcial era invisible."""
    paper("2020A", doi="10.1/a")
    ads, oa = fetchers(ads_map={"2020A": ["BIB1"]})      # ADS sí, OpenAlex no lo resuelve
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    assert idx["cobertura"]["ciegos"] == [], "tiene refs de ADS: no es ciego"
    assert idx["cobertura"]["sin_refs_openalex"] == ["10.1/a"]


def test_lookup_acepta_la_url_de_openalex(toy_vault, tmp_path):
    """`to_record` guarda `openalex_id` como URL completa y el índice guarda el id pelado. Un
    consumidor que pase las dos llaves del registro —lo que el docstring promete— fallaba el 100%
    del lado OpenAlex."""
    paper("2020A", doi="10.1/a")
    ads, oa = fetchers(oa_map={"10.1/a": ["W9"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    assert ci.cited_by_corpus(["2020Otro", "https://openalex.org/W9"], idx) == ["2020A"]


def test_sin_indice_construido_no_dice_que_nadie_cita(toy_vault):
    """El módulo predica contra el falso limpio y su lookup lo producía: sin índice, `[]` es
    indistinguible de «nadie lo cita». Ahora levanta, que es lo que INV-87 pide de un chequeo que
    no puede correr."""
    with pytest.raises(RuntimeError) as e:
        ci.cited_by_corpus("2009A&A...496..577Z")
    assert "citation_index" in str(e.value)
