"""openalex: cliente de OpenAlex — descubrimiento (`works`) y referencias por lote (`refs_of`).

La red está siempre falseada: ningún test toca OpenAlex de verdad."""
from __future__ import annotations

import pytest
import requests as real_requests

import openalex as oa
import query_ads as qa


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload = status, payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.HTTPError(f"HTTP {self.status_code}")


def fake_get(monkeypatch, responses, calls=None):
    it = iter(responses)

    def _get(url, **kw):
        if calls is not None:
            calls.append(url)
        return next(it)
    monkeypatch.setattr(oa.requests, "get", _get)


def work(oid="W1", doi="10.1/a", title="Independent component analysis", year=1994,
         refs=(), cited=7):
    return {"id": f"https://openalex.org/{oid}", "doi": f"https://doi.org/{doi}",
            "title": title, "publication_year": year,
            "referenced_works": [f"https://openalex.org/{r}" for r in refs],
            "cited_by_count": cited,
            "primary_location": {"source": {"display_name": "Signal Processing"}},
            "keywords": [{"display_name": "Periodogram"}, {"display_name": "Estimator"}],
            "topics": [{"display_name": "Astronomical Observations"}],
            "authorships": [{"author": {"display_name": "P. Comon"}}]}


# ── normalización al schema de registro ──────────────────────────────────────

def test_normaliza_al_mismo_schema_que_ads():
    """El registro de OpenAlex tiene que pasar por `query_ads.classify` sin tocarlo: si el schema
    diverge, cada backend nuevo obliga a un clasificador propio y la lente deja de ser una."""
    r = oa.to_record(work())
    for campo in ("bibcode", "title", "authors", "year", "abstract", "arxiv_id", "doi",
                  "doctype", "bibstem", "citation_count", "keyword"):
        assert campo in r, f"falta {campo}"
    assert r["doi"] == "10.1/a"                      # sin el prefijo https://doi.org/
    assert r["year"] == 1994 and r["citation_count"] == 7
    assert r["via"] == "openalex"


def test_el_registro_pasa_por_classify_sin_adaptador(monkeypatch):
    """El schema compartido no es cosmético: la lente tiene que clasificar un registro de OpenAlex
    **tal cual**. Si hiciera falta un adaptador, cada backend nuevo traería su propio clasificador y
    `objective.yaml` dejaría de ser la única lente.

    El punto de entrada es `classify_record` (no `classify`): `to_record` produce la forma
    **persistida** —`title` string, `keyword` lista— que es la de `ads.json`, no la respuesta cruda
    de ADS donde `title` viene como lista de un elemento."""
    monkeypatch.setattr(qa, "FACET_PATTERNS",
                        {"method": __import__("re").compile("independent component", 2)})
    monkeypatch.setattr(qa, "NOISE_DOCTYPES", set())
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    monkeypatch.setattr(qa, "MIN_FACETS", 1)
    facets, relevant = qa.classify_record(oa.to_record(work()))
    assert facets == ["method"] and relevant is True


def test_clave_sintetica_cuando_no_hay_bibcode():
    """OpenAlex no da bibcodes. La clave es la sintética AAAA+Autor que ya usa el modo off-ADS,
    no el id de OpenAlex: el vault cita por clave legible, no por identificador de proveedor."""
    assert oa.to_record(work())["bibcode"] == "1994Comon"


def test_sin_doi_ni_autor_no_inventa_clave():
    w = work(doi=None, year=None)
    w["doi"] = None
    w["authorships"] = []
    assert oa.to_record(w)["bibcode"] is None


# ── paginación por cursor ────────────────────────────────────────────────────

def test_works_pagina_por_cursor_y_deduplica(monkeypatch):
    p1 = {"results": [work("W1", "10.1/a"), work("W2", "10.1/b")],
          "meta": {"next_cursor": "c2"}}
    p2 = {"results": [work("W2", "10.1/b"), work("W3", "10.1/c")],
          "meta": {"next_cursor": None}}
    calls = []
    fake_get(monkeypatch, [FakeResp(200, p1), FakeResp(200, p2)], calls)
    got = list(oa.works("concepts.id:C1", per_page=2))
    assert [w["id"].split("/")[-1] for w in got] == ["W1", "W2", "W3"]
    assert len(calls) == 2 and "cursor=c2" in calls[1]


# ── referencias por lote, con cobertura DECLARADA (R-9) ──────────────────────

def test_refs_of_por_lote_devuelve_mapa_por_doi(monkeypatch):
    payload = {"results": [work("W1", "10.1/a", refs=("W9", "W8")),
                           work("W2", "10.1/b", refs=())],
               "meta": {"next_cursor": None}}
    fake_get(monkeypatch, [FakeResp(200, payload)])
    refs, sin = oa.refs_of(["10.1/a", "10.1/b"])
    assert refs["10.1/a"] == ["W9", "W8"]
    assert refs["10.1/b"] == []
    assert sin == []


def test_refs_of_declara_lo_que_no_resolvio(monkeypatch):
    """R-9 medido: OpenAlex no resuelve el 3,5% de los DOI del corpus y `referenced_works` está
    vacío en el 13% de los que sí resuelve. El índice tiene que **declarar** esa cobertura, no
    devolver un mapa incompleto que se lee como completo (INV-87)."""
    payload = {"results": [work("W1", "10.1/a", refs=("W9",))], "meta": {"next_cursor": None}}
    fake_get(monkeypatch, [FakeResp(200, payload)])
    refs, sin = oa.refs_of(["10.1/a", "10.1/NO-EXISTE"])
    assert refs["10.1/a"] == ["W9"]
    assert sin == ["10.1/no-existe"], "el DOI que no resolvió tiene que salir nombrado"


def test_refs_of_no_pide_nada_con_lista_vacia(monkeypatch):
    def _boom(*a, **k):
        pytest.fail("no debería tocar la red con una lista vacía")
    monkeypatch.setattr(oa.requests, "get", _boom)
    assert oa.refs_of([]) == ({}, [])


# ── el servicio se cae (INV-69: no inventar, pero tampoco morir en el primer hipo) ────────────

def test_reintenta_ante_5xx_transitorio(monkeypatch):
    """Medido en vivo el 2026-08-24: OpenAlex devolvió **504 en todos** sus endpoints, incluido el
    raíz, una hora después de contestar bien. Un índice de citas que se cae en el primer 5xx no se
    puede construir; uno que lo ignora inventa cobertura. La respuesta correcta es reintentar con
    espera y, si no cede, **levantar** (nunca devolver un mapa a medias)."""
    # ⚠ **Intermitente sin causa demostrada (2026-08-24).** Falló 2 veces sobre ~45 corridas de la
    # suite completa, las dos **inmediatamente después de editar un archivo del repo** (una con
    # `tools/mutar.py` copiando el árbol en paralelo). No se reprodujo: 8 corridas aisladas, 25
    # corridas de la suite entera y 3 forzando `__pycache__` stale, todas verdes. La sospecha —sin
    # evidencia— es el `subprocess` de `git config user.email` que `_mailto()` corre en cada
    # request y que bajo carga puede tardar o fallar. Se anota acá y **no se da por cerrado**: un
    # test intermitente que nadie declara se termina ignorando cuando falla de verdad.
    esperas = []
    monkeypatch.setattr(oa.time, "sleep", lambda s: esperas.append(s))
    fake_get(monkeypatch, [FakeResp(504), FakeResp(504),
                           FakeResp(200, {"results": [work()], "meta": {"next_cursor": None}})])
    assert len(list(oa.works("x"))) == 1
    assert len(esperas) == 2 and esperas == sorted(esperas), "la espera tiene que crecer"


def test_5xx_persistente_levanta(monkeypatch):
    """No degrada a lista vacía: una lista vacía es indistinguible de «no hay resultados»."""
    monkeypatch.setattr(oa.time, "sleep", lambda s: None)
    fake_get(monkeypatch, [FakeResp(504)] * oa.MAX_ATTEMPTS)
    with pytest.raises(real_requests.HTTPError):
        list(oa.works("x"))


def test_429_tambien_reintenta(monkeypatch):
    monkeypatch.setattr(oa.time, "sleep", lambda s: None)
    fake_get(monkeypatch, [FakeResp(429),
                           FakeResp(200, {"results": [], "meta": {"next_cursor": None}})])
    assert list(oa.works("x")) == []


def test_4xx_no_reintenta(monkeypatch):
    """Un 400 es una query mal armada: reintentarla es gastar cuota para el mismo error."""
    calls = []
    monkeypatch.setattr(oa.time, "sleep", lambda s: None)
    fake_get(monkeypatch, [FakeResp(400)] * 3, calls)
    with pytest.raises(real_requests.HTTPError):
        list(oa.works("x"))
    assert len(calls) == 1, "un 4xx se reintentó y no debería"


def test_las_keywords_de_openalex_llegan_a_la_lente():
    """La lente matchea sobre título + abstract + **keywords**. OpenAlex las tiene (medido: 13
    `keywords` y 3 `topics` en un paper real) y el cliente no las pedía en el `select`, así que
    `to_record` devolvía `keyword: []` y la lente buscaba en dos de tres fuentes — perdiendo señal
    en silencio, que es peor que no tenerla."""
    assert "keywords" in oa.SELECT and "topics" in oa.SELECT
    r = oa.to_record(work())
    assert r["keyword"] == ["Periodogram", "Estimator", "Astronomical Observations"]


def test_sin_keywords_no_revienta():
    w = work(); w.pop("keywords"); w.pop("topics")
    assert oa.to_record(w)["keyword"] == []


def test_el_registro_trae_el_veredicto_del_clasificador():
    """«Mismo schema que `query_ads`» tiene que incluir las tres claves del **clasificador**:
    `facets`, `relevant`, `why_excluded`. Sin ellas, medido: los consumidores que indexan con
    corchetes revientan (`fetch_pdf`, `fetch_arxiv`, `make_notes`) y los que usan `.get()` dan
    **falsos limpios** — `ingest_theme` ve `core` vacío, y `make_notes` marca toda nota
    `relevance: low`, lo que además las saca de `citation_index.corpus_idents`, o sea de la puerta
    1 que estos backends existen para alimentar."""
    r = oa.to_record(work())
    for campo in ("facets", "relevant", "why_excluded"):
        assert campo in r, f"falta {campo}: el registro no es del mismo schema"
    assert isinstance(r["relevant"], bool) and isinstance(r["facets"], list)


def test_el_abstract_invertido_se_rearma_en_orden():
    """El gate de mutación lo encontró: `_abstract` **no se ejecutaba en ningún test**, porque el
    fixture `work()` nunca trae `abstract_inverted_index`. No es cosmético — `classify_record` lee
    `abstract`, así que un abstract vacío cambia el veredicto core/no-core del registro."""
    w = work()
    w["abstract_inverted_index"] = {"blind": [0, 4], "source": [1], "separation": [2],
                                    "of": [3], "signals": [5]}
    assert oa.to_record(w)["abstract"] == "blind source separation of blind signals"


def test_sin_abstract_invertido_devuelve_cadena_vacia():
    assert oa.to_record(work())["abstract"] == ""
