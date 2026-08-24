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
    """Fetchers deterministas que reemplazan la red."""
    def _ads(bibcodes):
        return {b: list(ads_map.get(b, [])) for b in bibcodes if b in (ads_map or {})}

    def _oa(dois):
        m = {d: list((oa_map or {}).get(d, [])) for d in dois if d in (oa_map or {})}
        return m, [d for d in dois if d not in m]
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


# ── la puerta 1: PROPONE, no clasifica ───────────────────────────────────────

def test_candidatos_por_umbral(toy_vault, tmp_path):
    paper("2020A", doi="10.1/a")
    paper("2020B", doi="10.1/b")
    paper("2020C", doi="10.1/c")
    ads, oa = fetchers(oa_map={"10.1/a": ["W1", "W2"], "10.1/b": ["W1"], "10.1/c": ["W1"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    assert ci.candidates(min_citers=2, index=idx) == [("W1", ["2020A", "2020B", "2020C"])]
    assert [c[0] for c in ci.candidates(min_citers=1, index=idx)] == ["W1", "W2"]


def test_no_propone_lo_que_el_corpus_YA_tiene(toy_vault, tmp_path):
    """Un paper que ya está en la bóveda no es un candidato: proponerlo es ruido puro."""
    paper("2020A", doi="10.1/a")
    paper("2020Ya", doi="10.1/ya")
    ads, oa = fetchers(ads_map={"2020A": ["2020Ya"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    assert ci.candidates(min_citers=1, index=idx) == []


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
    assert ci.candidates(1, idx)


def test_vive_en_build_no_en_el_vault(toy_vault, tmp_path):
    """Regla de oro del registro: `build/` guarda lo regenerable. El índice se recupera pidiéndolo
    de nuevo a las APIs, así que no va al vault ni al versionado."""
    paper("2020A", doi="10.1/a")
    ads, oa = fetchers(oa_map={"10.1/a": ["W1"]})
    out = ci.build(fetch_ads=ads, fetch_oa=oa)
    assert out.is_relative_to(cfg.ROOT / "build")
    assert not out.is_relative_to(cfg.VAULT)


# ── fusión por DOI, SÓLO sobre los candidatos (los dos espacios de ids se solapan) ────────────

def test_candidatos_se_fusionan_por_doi(toy_vault, tmp_path):
    """Medido contra datos reales (2026-08-24): el candidato más citado del corpus salía **partido
    en dos** — `2009A&A...496..577Z` con 94 citadores y `W4292309267` con 82 son el MISMO paper
    (Zechmeister & Kürster 2009, DOI 10.1051/0004-6361:200811296); ídem Mayor & Queloz con 85 y 68.
    Sin fusionar, el triage ve dos candidatos con la mitad del peso cada uno.

    La fusión se hace **sólo sobre los candidatos que pasan el umbral**, no sobre las 20.824 obras
    citadas: ahí el costo de red sería proporcional a todas las referencias del corpus."""
    paper("2020A", doi="10.1/a")
    paper("2020B", doi="10.1/b")
    ads, oa = fetchers(ads_map={"2020A": ["2009BIB"], "2020B": ["2009BIB"]},
                       oa_map={"10.1/a": ["W99"], "10.1/b": ["W99"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    crudos = ci.candidates(2, idx)
    assert len(crudos) == 2, "sin fusionar son dos entradas distintas"

    dois = {"2009BIB": "10.1051/x", "W99": "10.1051/x"}       # el mismo trabajo
    fusion = ci.merge_candidates(crudos, resolver=lambda ks: {k: dois.get(k) for k in ks})
    assert len(fusion) == 1
    obra, citadores, alias = fusion[0]
    assert obra == "10.1051/x"
    assert citadores == ["2020A", "2020B"], "los citadores se UNEN, no se suman con repetidos"
    assert sorted(alias) == ["2009BIB", "W99"], "los ids originales quedan a la vista"


def test_sin_doi_no_se_fusiona_a_ciegas(toy_vault, tmp_path):
    """Una obra sin DOI (medido: OpenAlex devuelve works sin DOI ni título) NO se fusiona con nada:
    inventar la equivalencia crea una arista falsa, que es peor que una faltante."""
    paper("2020A", doi="10.1/a")
    paper("2020B", doi="10.1/b")
    ads, oa = fetchers(ads_map={"2020A": ["SIN_DOI_1"], "2020B": ["SIN_DOI_2"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    fusion = ci.merge_candidates(ci.candidates(1, idx), resolver=lambda ks: {k: None for k in ks})
    assert len(fusion) == 2
    assert all(a == [] for _, _, a in fusion), "sin DOI no hay alias que declarar"


def test_fusion_es_determinista(toy_vault, tmp_path):
    paper("2020A", doi="10.1/a")
    paper("2020B", doi="10.1/b")
    ads, oa = fetchers(ads_map={"2020A": ["B1", "B2"], "2020B": ["B2", "B1"]})
    idx = ci.load(ci.build(tmp_path / "ci.json", fetch_ads=ads, fetch_oa=oa))
    r = lambda ks: {k: "10.1/z" for k in ks}
    assert ci.merge_candidates(ci.candidates(1, idx), resolver=r) == \
           ci.merge_candidates(ci.candidates(1, idx), resolver=r)
