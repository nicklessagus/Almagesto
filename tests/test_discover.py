"""discover.py — cascada multi-backend, dedup por DOI, anclaje y resolución de archivo (#104)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import discover as d  # noqa: E402


# ── identidad / dedup (contrato 2: la llave es el DOI, NUNCA el título) ──────
def test_ident_prefiere_doi_y_normaliza():
    assert d.ident({"doi": "https://doi.org/10.1/AB"}) == "doi:10.1/ab"
    assert d.ident({"doi": None, "arxiv_id": "1234.5678"}) == "arxiv:1234.5678"
    assert d.ident({"doi": None, "arxiv_id": ""}) is None


def test_ident_ignora_el_titulo():
    """Dos registros con el mismo título y sin identificador NO son el mismo trabajo: matchear por
    título resolvió 18/25 casos y 2 apuntaban a otra obra (medición de openalex.py)."""
    a = {"title": "Independent component analysis", "doi": None, "arxiv_id": None}
    assert d.ident(a) is None


def test_dedup_mergea_por_doi_y_acumula_procedencia():
    ads = [{"doi": "10.1/x", "title": "X", "citation_count": 5}]
    oax = [{"doi": "https://doi.org/10.1/X", "title": "X", "citation_count": 7}]
    merged, undedup = d.dedup([("ads", ads), ("openalex", oax)])
    assert len(merged) == 1 and undedup == []
    assert merged[0]["found_in"] == ["ads", "openalex"]
    assert merged[0]["citation_count"] == 5          # gana el primer backend de la cascada


def test_dedup_rellena_citas_faltantes_del_backend_posterior():
    merged, _ = d.dedup([("ads", [{"doi": "10.1/x", "citation_count": 0}]),
                         ("openalex", [{"doi": "10.1/x", "citation_count": 42}])])
    assert merged[0]["citation_count"] == 42


def test_dedup_no_mergea_lo_que_no_tiene_identificador():
    """Contrato 3: lo no-deduplicable se DECLARA, no se adivina."""
    sin_id = [{"title": "A", "doi": None}, {"title": "A", "doi": None}]
    merged, undedup = d.dedup([("web", sin_id)])
    assert merged == [] and len(undedup) == 2
    assert all(r["found_in"] == ["web"] for r in undedup)


def test_dedup_no_muta_los_registros_de_entrada():
    entrada = {"doi": "10.1/x"}
    d.dedup([("ads", [entrada])])
    assert "found_in" not in entrada


def test_only_from_aisla_lo_que_solo_trajo_un_backend():
    merged, _ = d.dedup([("ads", [{"doi": "10.1/a"}]),
                         ("openalex", [{"doi": "10.1/a"}, {"doi": "10.1/b"}])])
    solo = d.only_from(merged, "openalex")
    assert [r["doi"] for r in solo] == ["10.1/b"]


# ── el normalizador de id: el bug que hacía que el ranking anclado diera todo 0 ──
@pytest.mark.parametrize("crudo,esperado", [
    ("https://openalex.org/W123", "W123"),
    ("W123", "W123"),
    (None, ""),
])
def test_oa_id_normaliza_las_dos_formas(crudo, esperado):
    """`refs_of` devuelve `W123` y `to_record` guarda la URL completa: unir por la clave cruda daba
    cero matches y un ranking de todos-ceros igual imprime una lista plausible."""
    assert d._oa_id(crudo) == esperado


def test_anchored_sin_dois_no_llama_a_la_red(monkeypatch):
    monkeypatch.setattr(d.oa, "refs_of", lambda i: pytest.fail("no debería consultar la red"))
    assert d.anchored([{"doi": None}]) == ([], [])


def test_anchored_cuenta_citadores_y_respeta_el_minimo(monkeypatch):
    # dos de los tres papers del ancla citan W1; sólo uno cita W2
    monkeypatch.setattr(d.oa, "refs_of", lambda idents: (
        {"10.1/a": ["W1", "W2"], "10.1/b": ["W1"], "10.1/c": []}, ["10.1/z"]))
    pares, no_res = d.anchored([{"doi": "10.1/a"}, {"doi": "10.1/b"}, {"doi": "10.1/c"}],
                               min_citadores=2)
    assert pares == [("W1", 2)]
    assert no_res == ["10.1/z"]          # contrato 3: la cobertura se declara


def test_anchored_no_cuenta_dos_veces_la_misma_referencia(monkeypatch):
    monkeypatch.setattr(d.oa, "refs_of", lambda i: ({"10.1/a": ["W1", "W1", "W1"]}, []))
    assert d.anchored([{"doi": "10.1/a"}], min_citadores=2) == ([], [])


def test_anchored_records_hace_el_join_y_ordena_por_consenso(monkeypatch):
    monkeypatch.setattr(d.oa, "refs_of", lambda i: (
        {"10.1/a": ["W1", "W2"], "10.1/b": ["W1", "W2"], "10.1/c": ["W2"]}, []))
    monkeypatch.setattr(d, "hydrate", lambda ids, rows=40: [
        {"openalex_id": "https://openalex.org/W1", "title": "uno", "citation_count": 999},
        {"openalex_id": "https://openalex.org/W2", "title": "dos", "citation_count": 1}])
    recs, _ = d.anchored_records([{"doi": "10.1/a"}, {"doi": "10.1/b"}, {"doi": "10.1/c"}],
                                 min_citadores=2)
    # W2 lo citan 3 y W1 sólo 2: manda el consenso del corpus, no el conteo global de citas
    assert [r["title"] for r in recs] == ["dos", "uno"]
    assert [r["citadores"] for r in recs] == [3, 2]
    assert all(r["found_in"] == ["anclado"] for r in recs)


# ── descubrimiento PROPONE, no clasifica (contrato 1 / INV-24) ───────────────
def test_seed_estampa_procedencia_y_no_decide_core(monkeypatch):
    class R:
        @staticmethod
        def json():
            return {"results": [{"id": "https://openalex.org/W1", "title": "T",
                                 "cited_by_count": 10, "publication_year": 1994}]}
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: R())
    recs = d.seed("T11447", rows=5)
    assert recs[0]["found_in"] == ["openalex"]
    assert "relevant" in recs[0]      # lo clasifica la ÚNICA lente, vía to_record — no este módulo


def test_seed_filtra_por_citas_minimas(monkeypatch):
    class R:
        @staticmethod
        def json():
            return {"results": [{"id": "W1", "title": "a", "cited_by_count": 10},
                                {"id": "W2", "title": "b", "cited_by_count": 1000}]}
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: R())
    assert len(d.seed("T1", min_citas=500)) == 1


def test_topics_devuelve_id_pelado(monkeypatch):
    class R:
        @staticmethod
        def json():
            return {"results": [{"id": "https://openalex.org/T11447",
                                 "display_name": "Blind Source Separation Techniques",
                                 "works_count": 55210}]}
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: R())
    t = d.topics("blind source separation")
    assert t[0]["id"] == "T11447" and t[0]["works_count"] == 55210


# ── resolución del archivo: encontrar ≠ conseguir ───────────────────────────
def test_resolve_pdf_sin_doi_no_consulta_nada(monkeypatch):
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: pytest.fail("no debería consultar"))
    url, why = d.resolve_pdf(None)
    assert url is None and "sin DOI" in why


def test_resolve_pdf_prefiere_openalex(monkeypatch):
    class R:
        @staticmethod
        def json():
            return {"best_oa_location": {"pdf_url": "http://x/a.pdf"}}
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: R())
    assert d.resolve_pdf("10.1/x") == ("http://x/a.pdf", "OpenAlex best_oa_location")


def test_resolve_pdf_cae_a_unpaywall(monkeypatch):
    llamadas = []

    def fake(url, **k):
        llamadas.append(url)

        class R:
            @staticmethod
            def json():
                if d.UNPAYWALL in url:
                    return {"best_oa_location": {"url_for_pdf": "http://u/b.pdf"}}
                return {"best_oa_location": {"pdf_url": None}}
        return R()
    monkeypatch.setattr(d.requests, "get", fake)
    assert d.resolve_pdf("10.1/x") == ("http://u/b.pdf", "Unpaywall")
    assert len(llamadas) == 2


def test_resolve_pdf_declara_el_fallo_sin_inventar(monkeypatch):
    class R:
        @staticmethod
        def json():
            return {}
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: R())
    url, why = d.resolve_pdf("10.1/x")
    assert url is None and "pending" in why


def test_resolve_pdf_no_se_cae_si_un_backend_revienta(monkeypatch):
    def fake(url, **k):
        if d.UNPAYWALL in url:
            class R:
                @staticmethod
                def json():
                    return {"best_oa_location": {"url_for_pdf": "http://u/b.pdf"}}
            return R()
        raise RuntimeError("openalex caído")
    monkeypatch.setattr(d.requests, "get", fake)
    assert d.resolve_pdf("10.1/x")[0] == "http://u/b.pdf"


# ── hydrate: los ids del anclaje sin título no sirven para triage ────────────
def test_hydrate_lotea_de_a_50_y_normaliza_ids(monkeypatch):
    vistos = []

    def fake(url, **k):
        vistos.append(url)

        class R:
            @staticmethod
            def json():
                return {"results": [{"id": "https://openalex.org/W1", "title": "t",
                                     "cited_by_count": 1}]}
        return R()
    monkeypatch.setattr(d.requests, "get", fake)
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    out = d.hydrate(["https://openalex.org/W%d" % i for i in range(120)], rows=200)
    assert len(vistos) == 3                      # 120 ids → 3 lotes de 50
    assert "openalex_id%3AW0" in vistos[0] or "openalex_id:W0" in vistos[0]
    assert len(out) == 3


def test_hydrate_corta_en_rows(monkeypatch):
    class R:
        @staticmethod
        def json():
            return {"results": [{"id": f"https://openalex.org/W{i}", "title": "t"}
                                for i in range(50)]}
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    assert len(d.hydrate([f"W{i}" for i in range(100)], rows=10)) == 10


def test_hydrate_declara_el_lote_que_falla_y_sigue(monkeypatch, capsys):
    """Contrato 3: un lote perdido en silencio deja un resultado incompleto que se lee completo."""
    def fake(url, **k):
        raise RuntimeError("timeout")
    monkeypatch.setattr(d.requests, "get", fake)
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    assert d.hydrate(["W1"]) == []
    assert "sin resolver" in capsys.readouterr().out


# ── preview ─────────────────────────────────────────────────────────────────
def test_row_muestra_procedencia_y_consenso():
    fila = d._row({"citation_count": 8266, "year": 1994, "found_in": ["anclado"],
                   "citadores": 8, "title": "Independent component analysis, a new concept?"})
    assert "8266" in fila and "1994" in fila and "anclado" in fila and "citado x8" in fila


def test_row_sin_consenso_no_inventa_la_columna():
    assert "citado x" not in d._row({"citation_count": 1, "year": 2000, "title": "t"})


def test_main_topics(monkeypatch, capsys):
    monkeypatch.setattr(d, "topics", lambda q, rows=5: [
        {"id": "T11447", "name": "Blind Source Separation Techniques", "works_count": 55210}])
    assert d.main(["--topics", "bss"]) == 0
    out = capsys.readouterr().out
    assert "T11447" in out and "55210" in out


def test_main_seed(monkeypatch, capsys):
    monkeypatch.setattr(d, "seed", lambda t, rows=25: [
        {"title": "x", "citation_count": 3, "year": 1994, "found_in": ["openalex"]}])
    assert d.main(["--seed", "T11447", "--rows", "1"]) == 0
    assert "candidatos a triage" in capsys.readouterr().out


def test_main_resolve_devuelve_1_si_no_hay_copia(monkeypatch, capsys):
    monkeypatch.setattr(d, "resolve_pdf", lambda doi, title=None: (None, "sin copia libre"))
    assert d.main(["--resolve", "10.1/x"]) == 1
    assert "sin copia libre" in capsys.readouterr().out


def test_main_resolve_devuelve_0_con_url(monkeypatch, capsys):
    monkeypatch.setattr(d, "resolve_pdf", lambda doi, title=None: ("http://a/b.pdf", "OpenAlex"))
    assert d.main(["--resolve", "10.1/x"]) == 0
    assert "http://a/b.pdf" in capsys.readouterr().out


def test_main_sin_modo_es_error():
    with pytest.raises(SystemExit):
        d.main([])
