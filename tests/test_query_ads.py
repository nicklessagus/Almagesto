"""query_ads: clasificador, variantes de designación, retry/truncado, chaining, main()."""
import json
import re
import sys
from types import SimpleNamespace

import pytest
import requests as real_requests

import query_ads as qa
from conftest import write_yaml
import lib_config as cfg


@pytest.fixture
def toy_classifier(monkeypatch):
    """Clasificador determinista para los tests (query_ads compila el real al importar)."""
    monkeypatch.setattr(qa, "TOPIC_PATTERNS", {
        "actividad": re.compile("activity|starspot", re.I),
        "rv": re.compile("radial velocity", re.I),
    })
    monkeypatch.setattr(qa, "NOISE_DOCTYPES", {"catalog", "proposal"})


@pytest.fixture
def no_sleep(monkeypatch):
    waits = []
    monkeypatch.setattr(qa, "time", SimpleNamespace(sleep=waits.append))
    return waits


# ── classify ─────────────────────────────────────────────────────────────────

def test_classify_por_titulo_abstract_keyword(toy_classifier):
    assert qa.classify({"title": ["Starspot evolution"], "doctype": "article"}) == (["actividad"], True)
    assert qa.classify({"abstract": "we measure RADIAL VELOCITY", "doctype": "article"}) == (["rv"], True)
    assert qa.classify({"keyword": ["stellar activity"], "doctype": "article"}) == (["actividad"], True)


def test_classify_doctype_ruido_no_es_core(toy_classifier):
    topics, relevant = qa.classify({"title": ["activity survey"], "doctype": "catalog"})
    assert topics == ["actividad"] and relevant is False


def test_classify_sin_match(toy_classifier):
    assert qa.classify({"title": ["asteroseismology"], "doctype": "article"}) == ([], False)


# ── designaciones / queries ──────────────────────────────────────────────────

def test_extract_arxiv():
    assert qa.extract_arxiv(["doi:x", "arXiv:2101.00001"]) == "2101.00001"
    assert qa.extract_arxiv(["arxiv:astro-ph/9605059"]) == "astro-ph/9605059"
    assert qa.extract_arxiv(["doi:x"]) is None
    assert qa.extract_arxiv(None) is None


@pytest.mark.parametrize("name,expected", [
    ("HD 40307", ["HD 40307", "HD40307"]),
    ("HD40307", ["HD 40307", "HD40307"]),
    ("GJ 581", ["GJ 581", "GJ581"]),
    ("tau Ceti", ["tau Ceti"]),        # nombre propio: no expandir
    ("51 Peg", ["51 Peg"]),            # designación numérica: no expandir
    ("V889 Her", ["V889 Her"]),        # variable con sufijo: no expandir
    ("HIP 8102", ["HIP 8102", "HIP8102"]),
])
def test_name_variants(name, expected):
    assert qa.name_variants(name) == expected


def test_expand_variants_dedup():
    assert qa.expand_variants(["HD 40307", "HD40307"]) == ["HD 40307", "HD40307"]


def test_build_query_y_fulltext_filter():
    q = qa.build_query(["tau Ceti", "HD 10700"])
    assert 'title:"tau Ceti"' in q and 'abs:"tau Ceti"' in q
    assert 'title:"HD 10700"' in q and 'title:"HD10700"' in q
    f = qa.build_fulltext_filter(["tau Ceti"])
    assert f == 'full:"tau Ceti"'


# ── query_ads() con red falsa ────────────────────────────────────────────────

class FakeResp:
    def __init__(self, status=200, payload=None, text="body"):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.HTTPError(f"HTTP {self.status_code}")


def fake_get_seq(responses, calls=None):
    it = iter(responses)

    def get(url, headers=None, params=None, timeout=None):
        if calls is not None:
            calls.append({"url": url, "headers": headers, "params": params})
        return next(it)
    return get


def payload(docs, num_found=None):
    return {"response": {"docs": docs, "numFound": num_found if num_found is not None else len(docs)}}


@pytest.fixture
def ads_token(monkeypatch):
    monkeypatch.setenv("ADS_DEV_KEY", "tok-test")


def test_query_ads_mapea_campos(toy_classifier, ads_token, no_sleep, monkeypatch):
    doc = {"bibcode": "2020ApJ...1..1A", "title": ["Starspots"], "author": ["Ana", "Bob"],
           "year": "2020", "pubdate": "2020-01", "abstract": "activity", "doctype": "article",
           "identifier": ["arXiv:2101.00001"], "doi": ["10.1/x"], "bibstem": ["ApJ"],
           "citation_count": 7, "keyword": ["spots"]}
    monkeypatch.setattr(qa, "requests", SimpleNamespace(get=fake_get_seq([FakeResp(200, payload([doc]))])))
    out = qa.query_ads("q", rows=10)
    assert len(out) == 1
    r = out[0]
    assert r["bibcode"] == "2020ApJ...1..1A"
    assert r["title"] == "Starspots"          # lista → primer elemento
    assert r["doi"] == "10.1/x"
    assert r["bibstem"] == "ApJ"
    assert r["arxiv_id"] == "2101.00001"
    assert r["topics"] == ["actividad"] and r["relevant"] is True


def test_query_ads_retry_429_luego_ok(toy_classifier, ads_token, no_sleep, monkeypatch):
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(429), FakeResp(200, payload([]))])))
    assert qa.query_ads("q") == []
    assert no_sleep == [5]                    # un retry con el primer backoff


def test_query_ads_5xx_persistente_lanza(toy_classifier, ads_token, no_sleep, monkeypatch):
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(500)] * 4)))
    with pytest.raises(real_requests.HTTPError):
        qa.query_ads("q")
    assert len(no_sleep) == 3                 # 3 backoffs, 4 intentos


def test_query_ads_200_cuerpo_raro(toy_classifier, ads_token, no_sleep, monkeypatch):
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(200, {"foo": 1})])))
    with pytest.raises(RuntimeError, match="Respuesta inesperada"):
        qa.query_ads("q")


def test_query_ads_avisa_truncado(toy_classifier, ads_token, no_sleep, monkeypatch, capsys):
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(200, payload([], num_found=500))])))
    m = {}
    qa.query_ads("q", rows=10, meta=m)
    assert "truncado" in capsys.readouterr().out
    assert m == {"num_found": 500, "rows": 10, "truncated": True}   # marca persistible (#17)
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(200, payload([], num_found=500))])))
    qa.query_ads("q", rows=10, quiet_truncate=True)
    assert "truncado" not in capsys.readouterr().out


def test_query_ads_meta_sin_truncar(toy_classifier, ads_token, no_sleep, monkeypatch):
    """meta reporta truncated=False cuando numFound ≤ rows (así el caller escribe `truncated: null`)."""
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(200, payload([], num_found=1))])))
    m = {}
    qa.query_ads("q", rows=2000, meta=m)
    assert m["truncated"] is False and m["num_found"] == 1


# ── chaining / extra_core ────────────────────────────────────────────────────

def rec(bib, relevant=True, cites=0, **kw):
    base = {"bibcode": bib, "title": f"t {bib}", "authors": ["A"], "year": "2020",
            "pubdate": None, "abstract": "", "arxiv_id": None, "doi": None,
            "doctype": "article", "bibstem": "ApJ", "citation_count": cites,
            "keyword": [], "topics": ["actividad"] if relevant else [], "relevant": relevant}
    base.update(kw)
    return base


def test_chain_candidates_arma_subqueries_ancladas(no_sleep, monkeypatch):
    queries = []

    def fake_qa(q, rows=400, quiet_truncate=False):
        queries.append(q)
        return [rec("2020chain...1C")]
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    bibs = [f"2020bib{i:04d}" for i in range(45)]     # 45 → chunks de 40+5 por operación
    out = qa.chain_candidates(bibs, rows=10, subject_filter='full:"X"')
    assert len(queries) == 4
    assert queries[0].startswith("references(") and 'AND (full:"X")' in queries[0]
    assert queries[2].startswith("citations(")
    assert all(h["via"] in ("chain:references", "chain:citations") for h in out)


def test_fetch_bibcodes_marca_manual(no_sleep, monkeypatch):
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=400, quiet_truncate=False: [rec("2019man....1M", relevant=False)])
    out = qa.fetch_bibcodes(["2019man....1M"])
    assert out[0]["relevant"] is True and out[0]["via"] == "manual"


# ── main(): integración con red mockeada ─────────────────────────────────────

def run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["query_ads.py", *argv])
    return qa.main()


def test_main_estrella_chaining_dedup_y_via(toy_vault, toy_classifier, no_sleep, monkeypatch):
    direct = [rec("2020dirA....1A", cites=5), rec("2020dirB....1B", relevant=False, cites=9)]
    chained = [rec("2020chC....1C", cites=2),                    # core nuevo → entra
               rec("2020dirA....1A", cites=5),                   # dup de la query → afuera
               rec("2020chD....1D", relevant=False)]             # no-core encadenado → afuera
    for c in chained:
        c["via"] = "chain:references"
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, quiet_truncate=False, meta=None: [dict(r) for r in direct])
    monkeypatch.setattr(qa, "chain_candidates", lambda bibs, rows, filt: [dict(r) for r in chained])
    assert run_main(monkeypatch, ["test_star"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    assert data["truncated"] is None                    # meta vacío (mock) → no truncó (#17)
    bibs = {r["bibcode"]: r for r in data["records"]}
    assert set(bibs) == {"2020dirA....1A", "2020dirB....1B", "2020chC....1C"}
    assert bibs["2020dirA....1A"]["via"] == "query"
    assert bibs["2020chC....1C"]["via"] == "chain:references"
    assert data["n_relevant"] == 2
    # ordenado por citas desc
    assert [r["bibcode"] for r in data["records"]][:2] == ["2020dirB....1B", "2020dirA....1A"]


def test_main_no_chain(toy_vault, toy_classifier, no_sleep, monkeypatch):
    called = []
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, quiet_truncate=False, meta=None: [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: called.append(a) or [])
    run_main(monkeypatch, ["test_star", "--no-chain"])
    assert called == []


def test_main_persiste_truncado(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """Query directa truncada → main persiste `truncated: {num_found, rows}` en ads.json (#17),
    convirtiendo el aviso de stdout en una marca que el lint surface."""
    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None):
        if meta is not None:
            meta.update(num_found=410, rows=rows, truncated=True)
        return [rec("2020dirA....1A")]
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    assert run_main(monkeypatch, ["test_star", "--rows", "400"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    assert data["truncated"] == {"num_found": 410, "rows": 400}


def test_main_extra_core_persistente(toy_vault, toy_classifier, no_sleep, monkeypatch):
    stars = {"Estrella Test": {"slug": "test_star", "simbad": "s", "ads_object": "Test Star",
                               "aliases": [], "extra_core": ["1988old.....1O"]}}
    write_yaml(cfg.STARS_YAML, stars)
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, quiet_truncate=False, meta=None: [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    monkeypatch.setattr(qa, "fetch_bibcodes",
                        lambda bibs: [dict(rec("1988old.....1O", relevant=True), via="manual")])
    run_main(monkeypatch, ["test_star"])
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    manual = [r for r in data["records"] if r["via"] == "manual"]
    assert [r["bibcode"] for r in manual] == ["1988old.....1O"]


def test_main_tema_extra_only(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """Tema off-ADS MIXTO: --extra-only trae SÓLO los extra_core (sin query ni chaining), y no
    exige `query` — la vía ADS de un tema cuya bibliografía canónica vive fuera de ADS."""
    write_yaml(cfg.TOPICS_YAML, {"gp": {"title": "Gaussian processes", "area": "methods",
                                        "concept": "gaussian-processes", "source": "web",
                                        "extra_core": ["2012PASP..124.1015B"]}})
    monkeypatch.setattr(qa, "query_ads", lambda *a, **kw: pytest.fail("no debe correr la query"))
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: pytest.fail("no debe encadenar"))
    monkeypatch.setattr(qa, "fetch_bibcodes",
                        lambda bibs: [dict(rec("2012PASP..124.1015B", relevant=True), via="manual")])
    assert run_main(monkeypatch, ["gp", "--topic", "--extra-only"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "gp" / "ads.json").read_text())
    assert data["kind"] == "topic" and data["query"] is None
    assert [r["bibcode"] for r in data["records"]] == ["2012PASP..124.1015B"]
    assert data["records"][0]["via"] == "manual"


def test_main_extra_only_sin_extra_core_error(toy_vault, toy_classifier, monkeypatch):
    write_yaml(cfg.TOPICS_YAML, {"gp": {"title": "GP", "area": "methods",
                                        "concept": "gaussian-processes", "source": "web"}})
    with pytest.raises(SystemExit, match="no declara `extra_core`"):
        run_main(monkeypatch, ["gp", "--topic", "--extra-only"])


def test_main_extra_only_requiere_topic(toy_vault, toy_classifier, monkeypatch):
    with pytest.raises(SystemExit):                  # ap.error → exit 2
        run_main(monkeypatch, ["test_star", "--extra-only"])


def test_main_estrella_sin_ads_object_error_amigable(toy_vault, toy_classifier, monkeypatch):
    """Guard de config: entrada de stars.yaml cargada a mano sin ads_object → mensaje, no traceback."""
    write_yaml(cfg.STARS_YAML, {"Estrella Test": {"slug": "test_star", "simbad": "s"}})
    with pytest.raises(SystemExit, match="no tiene `ads_object`"):
        run_main(monkeypatch, ["test_star"])


def test_main_tema_sin_query_sugiere_offads(toy_vault, toy_classifier, monkeypatch):
    """Guard de config: tema sin `query` (típico: es off-ADS) → mensaje con la pista, no KeyError."""
    write_yaml(cfg.TOPICS_YAML, {"gp": {"title": "Gaussian processes", "area": "methods", "concept": "gaussian-processes",
                                         "source": "web"}})
    with pytest.raises(SystemExit, match="no tiene `query`.*ingest_topic"):
        run_main(monkeypatch, ["gp", "--topic"])


def test_probe_lista_todo_el_core(toy_classifier, capsys):
    recs = [rec(f"2020core...{i}A", cites=i) for i in range(30)] + [rec("2020non....1N", relevant=False)]
    qa.print_probe("q", recs)
    out = capsys.readouterr().out
    assert "30 CORE" in out
    assert out.count("[CORE]") == 30          # el core se lista completo, no top-N
