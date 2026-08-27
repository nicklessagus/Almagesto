"""discover.py — cascada multi-backend, dedup por DOI, anclaje y resolución de archivo (#104)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import discover as d  # noqa: E402
import lib_config as cfg  # noqa: E402
from conftest import write_yaml  # noqa: E402


# Doble ÚNICO de una respuesta HTTP: trae `status_code` además de `json()`, como el objeto real
# (regla de método #3). Los dobles locales que sólo tenían `json()` divergían del real, y el chequeo
# de status que `_json` agregó murió en esa diferencia — no en el código.
class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        if self._p is None:
            raise ValueError("no json")
        return self._p


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
        status_code = 200
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
        status_code = 200
        @staticmethod
        def json():
            return {"results": [{"id": "W1", "title": "a", "cited_by_count": 10},
                                {"id": "W2", "title": "b", "cited_by_count": 1000}]}
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: R())
    assert len(d.seed("T1", min_citas=500)) == 1


def test_topics_devuelve_id_pelado(monkeypatch):
    class R:
        status_code = 200
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
        status_code = 200
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
            status_code = 200
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
        status_code = 200
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
                status_code = 200
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
            status_code = 200
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
        status_code = 200
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


# ── la cascada: corre los tres y DECLARA lo que no corrió (contrato 3) ───────
def test_cascade_declara_los_backends_que_no_corrieron():
    """Saltear un backend en silencio deja una cascada de tres que corrió una, y el resultado se
    lee como «los tres miraron y esto es todo lo que hay» — el falso limpio de INV-87."""
    out = d.cascade()
    assert out["records"] == []
    motivos = {b: err for b, _n, err in out["cobertura"]}
    assert set(motivos) == {"ads", "arxiv", "openalex"}
    assert all(m.startswith("NO CORRIÓ") for m in motivos.values())
    assert "query:" in motivos["ads"] and "topic:" in motivos["openalex"]


def test_cascade_mergea_los_tres_por_doi(monkeypatch):
    import query_ads, search_arxiv
    monkeypatch.setattr(query_ads, "query_ads",
                        lambda q, rows=100: [{"doi": "10.1/a", "title": "A", "citation_count": 5}])
    monkeypatch.setattr(search_arxiv, "search",
                        lambda q, rows=100: [{"doi": "10.1/A", "title": "A", "citation_count": None},
                                             {"doi": "10.1/b", "title": "B"}])
    monkeypatch.setattr(d, "seed", lambda t, rows=200, min_citas=None: [
        {"doi": "10.1/c", "title": "C", "citation_count": 99}])
    out = d.cascade(ads_query="q", arxiv_terms=["t"], topic_id="T1")
    porid = {r["doi"].lower(): r for r in out["records"]}
    assert set(porid) == {"10.1/a", "10.1/b", "10.1/c"}
    assert porid["10.1/a"]["found_in"] == ["ads", "arxiv"]     # el mismo trabajo, dos backends
    assert d.only_from(out["records"], "openalex")[0]["doi"] == "10.1/c"


def test_cascade_no_se_cae_si_un_backend_revienta(monkeypatch):
    import query_ads
    def boom(q, rows=100):
        raise RuntimeError("ADS 503")
    monkeypatch.setattr(query_ads, "query_ads", boom)
    monkeypatch.setattr(d, "seed", lambda t, rows=200, min_citas=None: [{"doi": "10.1/c"}])
    out = d.cascade(ads_query="q", topic_id="T1")
    err = dict((b, e) for b, _n, e in out["cobertura"])["ads"]
    assert "ADS 503" in err and not err.startswith("NO CORRIÓ")   # falló ≠ no corrió
    assert len(out["records"]) == 1                                # el resto igual sirve


def test_print_cobertura_distingue_fallo_de_no_corrio(capsys):
    d.print_cobertura([("ads", 3, None), ("arxiv", 0, "NO CORRIÓ: sin aliases"),
                       ("openalex", 0, "timeout")])
    out = capsys.readouterr().out
    assert "ads" in out and "3" in out
    assert "NO CORRIÓ" in out
    assert "FALLÓ" in out and "NO significa" in out     # 0 por caída ≠ 0 por no tener nada


# ── el conteo de citas que NADIE miró no es cero ─────────────────────────────
def test_row_muestra_interrogante_cuando_no_hay_conteo():
    """arXiv no publica citas y `to_record` pone None a propósito. Un `0` en la columna que el
    operador usa para decidir qué mandar a triage descarta un fundacional de un vistazo."""
    assert "?" in d._row({"citation_count": None, "year": 1994, "title": "t"})
    assert "0" not in d._row({"citation_count": None, "year": 1994, "title": "t"}).split("1994")[0]


def test_row_muestra_cero_real_cuando_el_conteo_ES_cero():
    assert "0" in d._row({"citation_count": 0, "year": 2026, "title": "t"})


# ── el ancla se lee con el parser del tooling, NUNCA con grep ───────────────
def test_theme_anchor_lee_las_dos_formas_de_thesis_links(tmp_path, monkeypatch):
    """`thesis_links` viene en bloque (lo escribe make_notes) y en flow (lo deja el retro-linkeo).
    Un match textual pierde una de las dos — está registrado dos veces en CLAUDE.md."""
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "bloque.md").write_text(
        "---\ntitle: A\ndoi: 10.1/a\nthesis_links:\n- ica\n---\ncuerpo\n", encoding="utf-8")
    (papers / "flow.md").write_text(
        "---\ntitle: B\ndoi: 10.1/b\nthesis_links: [ica]\n---\ncuerpo\n", encoding="utf-8")
    (papers / "otro.md").write_text(
        "---\ntitle: C\ndoi: 10.1/c\nthesis_links: [gp]\n---\ncuerpo\n", encoding="utf-8")
    (papers / "sin_doi.md").write_text(
        "---\ntitle: D\nthesis_links: [ica]\n---\ncuerpo\n", encoding="utf-8")
    monkeypatch.setattr(d.cfg, "PAPERS", papers)
    dois = sorted(r["doi"] for r in d._theme_anchor("ica"))
    assert dois == ["10.1/a", "10.1/b"]        # las dos formas; sin el de otro tema ni el sin DOI


def test_theme_anchor_no_confunde_slugs_que_se_prefijan(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "x.md").write_text(
        "---\ndoi: 10.1/x\nthesis_links: [ica-noise]\n---\n", encoding="utf-8")
    monkeypatch.setattr(d.cfg, "PAPERS", papers)
    assert d._theme_anchor("ica") == []        # compara por ELEMENTO, no por substring


# ── preview de un tema ──────────────────────────────────────────────────────
def test_preview_theme_slug_desconocido(monkeypatch, capsys):
    monkeypatch.setattr(d.cfg, "load_themes", lambda: {})
    assert d._preview_theme("noexiste") == 2
    assert "no está en themes.yaml" in capsys.readouterr().out


def test_preview_theme_corre_la_cascada_y_el_anclaje(monkeypatch, capsys):
    monkeypatch.setattr(d.cfg, "load_themes", lambda: {
        "ica": {"title": "ICA", "query": "q", "aliases": ["ICA"], "topic": "T11447"}})
    monkeypatch.setattr(d, "cascade", lambda **k: {
        "records": [{"doi": "10.1/a", "title": "A", "citation_count": 9, "found_in": ["openalex"]}],
        "undedupable": [{"title": "sin id"}],
        "cobertura": [("ads", 1, None)]})
    monkeypatch.setattr(d, "_theme_anchor", lambda s: [{"doi": "10.1/z"}])
    monkeypatch.setattr(d, "anchored_records", lambda a, min_citadores=2, rows=25: (
        [{"title": "canon", "citation_count": 8266, "citadores": 8, "found_in": ["anclado"]}],
        ["10.1/no-resuelto"]))
    assert d._preview_theme("ica") == 0
    out = capsys.readouterr().out
    assert "SÓLO OpenAlex" in out                  # la procedencia enruta al triage
    assert "sin identificador (NO mergeados)" in out
    assert "sin referencias resueltas" in out      # cobertura del anclaje, declarada
    assert "CANDIDATOS" in out                     # propone, no clasifica


def test_preview_theme_sin_ancla_lo_dice(monkeypatch, capsys):
    monkeypatch.setattr(d.cfg, "load_themes", lambda: {"ica": {"title": "ICA", "topic": "T1"}})
    monkeypatch.setattr(d, "cascade", lambda **k: {"records": [], "undedupable": [],
                                                   "cobertura": []})
    monkeypatch.setattr(d, "_theme_anchor", lambda s: [])
    assert d._preview_theme("ica") == 0
    assert "sin anclaje" in capsys.readouterr().out


def test_preview_theme_infiere_el_topic_y_avisa_que_lo_eligio_solo(monkeypatch, capsys):
    monkeypatch.setattr(d.cfg, "load_themes", lambda: {
        "ica": {"title": "blind source separation", "aliases": ["ICA"]}})
    monkeypatch.setattr(d, "topics", lambda q, rows=1: [{"id": "T11447", "name": "BSS"}])
    visto = {}
    monkeypatch.setattr(d, "cascade", lambda **k: visto.update(k) or {
        "records": [], "undedupable": [], "cobertura": []})
    monkeypatch.setattr(d, "_theme_anchor", lambda s: [])
    d._preview_theme("ica")
    assert visto["topic_id"] == "T11447"
    assert "elegido por alias" in capsys.readouterr().out   # nunca en silencio


# ── seed_terms: el segundo eje, opt-in por medición (#107) ───────────────────
def test_seed_terms_una_slice_por_termino_y_dedup(monkeypatch):
    urls = []

    def fake(url, **k):
        urls.append(url)

        class R:
            status_code = 200
            @staticmethod
            def json():
                return {"results": [{"id": "https://openalex.org/W1", "title": "t",
                                     "cited_by_count": 3}]}
        return R()
    monkeypatch.setattr(d.requests, "get", fake)
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    out = d.seed_terms("T11447", ["noisy ICA", "quasi-whitening"])
    assert len(urls) == 2                      # una request por término
    assert len(out) == 1                       # el mismo work no se duplica entre slices
    assert out[0]["found_in"] == ["openalex"]
    assert "topics.id" in urls[0] and "title_and_abstract.search" in urls[0]


def test_seed_terms_declara_el_termino_que_falla_y_sigue(monkeypatch, capsys):
    def fake(url, **k):
        if "malo" in url:
            raise RuntimeError("500")

        class R:
            status_code = 200
            @staticmethod
            def json():
                return {"results": [{"id": "W1", "title": "t"}]}
        return R()
    monkeypatch.setattr(d.requests, "get", fake)
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    out = d.seed_terms("T1", ["malo", "bueno"])
    assert len(out) == 1
    assert "«malo» falló" in capsys.readouterr().out


def test_cascade_no_usa_term_slices_por_default(monkeypatch):
    """#107: medido, sumaban 217 candidatos y recuperaban 1 de 18. Off por default no es una
    preferencia — es el resultado. Si alguien lo cablea sin querer, este test lo frena."""
    llamado = []
    monkeypatch.setattr(d, "seed", lambda t, rows=200, min_citas=None: [{"doi": "10.1/a"}])
    monkeypatch.setattr(d, "seed_terms", lambda t, terms, **k: llamado.append(terms) or [])
    # #123: `arxiv_terms` dispara el backend de arXiv, que hacía una petición HTTP REAL desde la
    # suite. El test no mide eso —mide qué backends se llaman—, así que el doble es lo correcto.
    import search_arxiv
    monkeypatch.setattr(search_arxiv, "search", lambda q, rows=100: [])
    d.cascade(topic_id="T1", arxiv_terms=["noisy ICA"])
    assert llamado == [], "arxiv_terms NO debe disparar slices de OpenAlex"


def test_cascade_usa_term_slices_si_se_piden(monkeypatch):
    llamado = []
    monkeypatch.setattr(d, "seed", lambda t, rows=200, min_citas=None: [])
    monkeypatch.setattr(d, "seed_terms",
                        lambda t, terms, **k: llamado.append(terms) or [{"doi": "10.1/b"}])
    out = d.cascade(topic_id="T1", term_slices=["quasi-whitening"])
    assert llamado == [["quasi-whitening"]]
    assert len(out["records"]) == 1


def test_seed_terms_avisa_si_el_slice_tiene_mas_de_lo_que_trajo(monkeypatch, capsys):
    """No silent caps (#107). El tope de 15 filas por término no avisaba, y de su salida se dedujo
    un «límite estructural» que era falso: los papers estaban en los puestos 28/44/110/121 de un
    slice de 579. Un tope que esconde su efecto produce conclusiones, no sólo resultados faltantes."""
    class R:
        status_code = 200
        @staticmethod
        def json():
            return {"meta": {"count": 579},
                    "results": [{"id": f"W{i}", "title": "t"} for i in range(15)]}
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    d.seed_terms("T11447", ["noisy ICA"], rows_por_termino=15)
    out = capsys.readouterr().out
    assert "579" in out and "15" in out and "rows_por_termino" in out


def test_seed_terms_calla_si_trajo_todo_el_slice(monkeypatch, capsys):
    class R:
        status_code = 200
        @staticmethod
        def json():
            return {"meta": {"count": 3}, "results": [{"id": f"W{i}"} for i in range(3)]}
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    d.seed_terms("T1", ["quasi-whitening"])
    assert "⚠" not in capsys.readouterr().out


def test_seed_terms_default_no_es_un_tope_chico():
    """El default es una MEDICIÓN: con 15 la recuperación daba 7/18; con el slice completo, 13/18."""
    import inspect
    assert inspect.signature(d.seed_terms).parameters["rows_por_termino"].default >= 200


# ── el cero silencioso de OpenAlex: 429 con payload de error (#110) ──────────
def test_json_levanta_ante_payload_de_error(monkeypatch):
    """Medido en vivo: con el presupuesto diario agotado OpenAlex responde 429 con
    {error, message, …} y SIN `results`. Leer sólo `results` daba 0 y la cobertura imprimía
    «openalex 0 registros» como si el backend hubiera mirado — «se acabó la cuota» y «el tema no
    existe en OpenAlex» son conclusiones opuestas (INV-87)."""
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: _Resp(
        {"error": "Rate limit exceeded", "message": "Insufficient budget"}, 429))
    with pytest.raises(RuntimeError, match="Rate limit"):
        d._json("http://x")


def test_json_levanta_ante_status_de_error_sin_payload(monkeypatch):
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: _Resp({"results": []}, 503))
    with pytest.raises(RuntimeError, match="503"):
        d._json("http://x")


def test_json_levanta_ante_respuesta_no_json(monkeypatch):
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: _Resp(None, 502))
    with pytest.raises(RuntimeError, match="no-JSON"):
        d._json("http://x")


def test_json_devuelve_el_payload_bueno(monkeypatch):
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: _Resp({"results": [1]}, 200))
    assert d._json("http://x") == {"results": [1]}


def test_cascade_reporta_el_429_como_FALLO_no_como_cero(monkeypatch):
    """La consecuencia que importa: la cobertura dice FALLÓ, no «0 registros»."""
    monkeypatch.setattr(d.requests, "get", lambda *a, **k: _Resp(
        {"error": "Rate limit exceeded", "message": "budget"}, 429))
    out = d.cascade(topic_id="T11447")
    err = dict((b, e) for b, _n, e in out["cobertura"])["openalex"]
    assert err and not err.startswith("NO CORRIÓ")
    assert "Rate limit" in err


# ── #77 · el descubrimiento off-ADS deja registro ────────────────────────────────────────────────

def test_la_cascada_registra_su_corrida(toy_vault, monkeypatch, capsys):
    """#77: la cascada corre tres backends y su resultado moría en stdout. Un tema off-ADS no podía
    responder «sobre qué universo afirma esta nota, y con qué se buscó» — que es justo lo que #64 /
    D-28 garantizan para un tema ADS con `busquedas`.

    Y lo que hay que registrar no son sólo los hallazgos: la **cobertura por backend**, con sus tres
    estados (corrió con N · FALLÓ · NO CORRIÓ y por qué). Un backend que no corrió y uno que corrió
    y no trajo nada se leen igual en un total, y esa distinción es la que hace que «los tres miraron
    y esto es todo lo que hay» sea o no una afirmación honesta.

    @inv INV-121"""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "area": "methods", "concept": "ica",
                                         "source": "web", "query": 'abs:"independent component"',
                                         "aliases": ["ICA"], "topic": "T11447"}})
    monkeypatch.setattr(d, "cascade", lambda **k: {
        "records": [{"doi": "10.1/a", "bibcode": "2000Hyv", "title": "T", "found_in": ["openalex"]}],
        "undedupable": [],
        "cobertura": [("ads", 3, None), ("arxiv", 0, "timeout"), ("openalex", 1, None)]})
    d._preview_theme("ica", rows=10, min_citadores=2)
    reg = cfg.load_registro("ica") or {}
    ds = cfg.as_list(reg.get("descubrimientos"))
    assert len(ds) == 1
    assert ds[0]["n_records"] == 1 and ds[0]["fecha"]
    cob = ds[0]["cobertura"]
    assert cob["ads"] == {"n": 3, "error": None}
    assert cob["arxiv"] == {"n": 0, "error": "timeout"}, "un backend caído NO es «no hay nada»"
