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
    """Clasificador determinista para los tests (query_ads compila el real al importar). Resetea la
    regla de combinación a su default (require=[], min_topics=1) para no heredar la del objective.yaml
    real; los tests de la regla declarativa la sobre-escriben."""
    monkeypatch.setattr(qa, "TOPIC_PATTERNS", {
        "actividad": re.compile("activity|starspot", re.I),
        "rv": re.compile("radial velocity", re.I),
    })
    monkeypatch.setattr(qa, "NOISE_DOCTYPES", {"catalog", "proposal"})
    monkeypatch.setattr(qa, "REQUIRE_TOPICS", [])
    monkeypatch.setattr(qa, "MIN_TOPICS", 1)


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


# ── regla de combinación declarativa: require / min_topics (#15) ──────────────

def test_classify_require_faceta_obligatoria(toy_classifier, monkeypatch):
    """`require: [rv]` → un paper que matchea sólo `actividad` deja de ser core; el que matchea
    `rv` (aunque no `actividad`) sí. La faceta del eje se vuelve AND, no OR."""
    monkeypatch.setattr(qa, "REQUIRE_TOPICS", ["rv"])
    assert qa.classify({"title": ["starspot activity"], "doctype": "article"}) == (["actividad"], False)
    t, rel = qa.classify({"title": ["radial velocity survey"], "doctype": "article"})
    assert t == ["rv"] and rel is True
    # matchea ambas → core (require ⊆ matched)
    _, rel2 = qa.classify({"title": ["radial velocity"], "abstract": "activity", "doctype": "article"})
    assert rel2 is True


def test_classify_min_topics_dos(toy_classifier, monkeypatch):
    """`min_topics: 2` → una sola faceta no alcanza; hacen falta ≥2 cualesquiera."""
    monkeypatch.setattr(qa, "MIN_TOPICS", 2)
    assert qa.classify({"title": ["radial velocity"], "doctype": "article"}) == (["rv"], False)
    t, rel = qa.classify({"title": ["radial velocity"], "abstract": "starspot activity",
                          "doctype": "article"})
    assert set(t) == {"actividad", "rv"} and rel is True


def test_classify_require_y_ruido_componen(toy_classifier, monkeypatch):
    """require se combina con el filtro de doctype ruido (AND de las tres condiciones)."""
    monkeypatch.setattr(qa, "REQUIRE_TOPICS", ["rv"])
    _, rel = qa.classify({"title": ["radial velocity"], "doctype": "catalog"})
    assert rel is False                                   # matchea require pero es doctype ruido


def test_exclusion_reason_motivos(toy_classifier, monkeypatch):
    """#30: el motivo de exclusión se computa donde se decide (única implementación de la regla).
    Un excluido por `require` con facetas matcheadas y doctype limpio NO se etiqueta por doctype
    (el bug: el apéndice "Excluidos" decía `doctype: article`)."""
    monkeypatch.setattr(qa, "REQUIRE_TOPICS", ["rv"])
    assert qa.exclusion_reason([], "article") == "sin tópico"              # rótulo histórico
    assert qa.exclusion_reason(["actividad"], "catalog") == "doctype: catalog"   # ídem
    why = qa.exclusion_reason(["actividad"], "article")
    assert "rv" in why and "require" in why and "doctype" not in why
    assert qa.exclusion_reason(["rv"], "article") is None                  # core → sin motivo


def test_exclusion_reason_min_topics(toy_classifier, monkeypatch):
    monkeypatch.setattr(qa, "MIN_TOPICS", 2)
    assert "min_topics=2" in qa.exclusion_reason(["rv"], "article")
    assert qa.exclusion_reason(["rv", "actividad"], "article") is None


def test_classify_coherente_con_exclusion_reason(toy_classifier, monkeypatch):
    """`relevant` de classify ⟺ exclusion_reason None — no hay dos implementaciones de la regla."""
    monkeypatch.setattr(qa, "REQUIRE_TOPICS", ["rv"])
    for rec_, why_topics in [({"title": ["starspot activity"], "doctype": "article"}, ["actividad"]),
                             ({"title": ["radial velocity"], "doctype": "article"}, ["rv"]),
                             ({"title": ["asteroseismology"], "doctype": "article"}, [])]:
        topics, rel = qa.classify(rec_)
        assert topics == why_topics
        assert rel is (qa.exclusion_reason(topics, rec_["doctype"]) is None)


def test_combination_rule_defaults():
    """Sin declarar nada → (require=[], min_topics=1): el comportamiento histórico (≥1 faceta OR)."""
    assert qa.combination_rule({}, {"rv": None, "actividad": None}) == ([], 1)
    assert qa.combination_rule({"min_topics": 2, "require": ["rv"]},
                               {"rv": None, "actividad": None}) == (["rv"], 2)


def test_require_faceta_inexistente_falla():
    """Guard de config: una faceta en `require` ausente de `topics` filtraría TODO en silencio →
    falla ruidoso (mismo camino que corre al importar el módulo)."""
    with pytest.raises(RuntimeError, match="require nombra facetas ausentes"):
        qa.combination_rule({"require": ["no-existe"]}, {"rv": None})


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


# ── rescate por glifo: nombres Bayer con lookalike Unicode (#28) ─────────────

def test_greek_targets_detecta_bayer():
    assert qa.greek_targets(["eps Eridani", "ε Eri", "HD 22049", "GJ 144"]) == {
        "epsilon": {"Eridani", "Eri"}}
    assert qa.greek_targets(["epsilon Eridani"]) == {"epsilon": {"Eridani"}}


def test_greek_targets_sin_lookalike_no_gasta_query():
    """τ no tiene lookalike conocido (ADS unifica τ/tau) → sin agujero, sin superset."""
    assert qa.greek_targets(["tau Ceti", "HD 10700"]) == {}


def test_greek_targets_ignora_no_bayer():
    assert qa.greek_targets(["AU Mic", "HD 197481", "51 Peg"]) == {}


def test_glyph_pattern_es_letra_especifica():
    pat = qa.glyph_pattern("epsilon", {"Eridani", "Eri"})
    assert pat.search("Evidence for a Long-Period Planet Orbiting ∊ Eridani")   # ∊ (ApJ/AJ)
    assert pat.search("the disk of ϵEri")                                       # ϵ sin espacio
    assert pat.search("ε Eridani revisited")                                    # ε canónica
    assert not pat.search("The τ Eri system")          # otra letra griega: no se cuela
    assert not pat.search("Eridanus II dwarf galaxy")       # constelación suelta: no alcanza


def test_glyph_rescue_filtra_client_side(toy_classifier, ads_token, no_sleep, monkeypatch):
    """Trae el superset de la constelación y se queda SÓLO con los que llevan el glifo; los
    devuelve clasificados y marcados via: glyph."""
    docs = [
        {"bibcode": "2000ApJ...544L.145H", "title": ["Planet Orbiting ∊ Eridani"],
         "abstract": "radial velocity", "doctype": "article"},
        {"bibcode": "2015noise...1..1X", "title": ["Eridanus II dwarf galaxy"],
         "abstract": "radial velocity of member stars", "doctype": "article"},
    ]
    consultas = []
    def fake_get(url, headers=None, params=None, timeout=None):
        consultas.append(params["q"])
        return FakeResp(200, payload(docs))
    monkeypatch.setattr(qa, "requests", SimpleNamespace(get=fake_get))
    out = qa.glyph_rescue(["eps Eridani", "ε Eri"], rows=100)
    assert [r["bibcode"] for r in out] == ["2000ApJ...544L.145H"]
    assert out[0]["via"] == "glyph" and out[0]["relevant"] is True
    assert consultas == ['title:"Eri" OR abs:"Eri" OR title:"Eridani" OR abs:"Eridani"']


def test_main_rescate_glifo_siembra_el_chaining(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """El rescate corre ANTES del chaining (el descubrimiento recuperado siembra el grafo) y sus
    core nuevos entran a ads.json con via: glyph, deduplicados contra la query directa."""
    stars = {"eps Eridani": {"slug": "test_star", "simbad": "s", "ads_object": "eps Eridani",
                             "aliases": ["ε Eri"]}}
    write_yaml(cfg.STARS_YAML, stars)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "glyph_rescue",
                        lambda names, rows: [dict(rec("2000ApJ...544L.145H"), via="glyph"),
                                             dict(rec("2020dirA....1A"), via="glyph")])  # dup → afuera
    sembrados = {}
    def fake_chain(bibs, rows, filt):
        sembrados["core"] = list(bibs)
        return []
    monkeypatch.setattr(qa, "chain_candidates", fake_chain)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert set(sembrados["core"]) == {"2020dirA....1A", "2000ApJ...544L.145H"}
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    bibs = {r["bibcode"]: r["via"] for r in data["records"]}
    assert bibs == {"2020dirA....1A": "query", "2000ApJ...544L.145H": "glyph"}


def test_main_no_glyph_desactiva(toy_vault, toy_classifier, no_sleep, monkeypatch):
    stars = {"eps Eridani": {"slug": "test_star", "simbad": "s", "ads_object": "eps Eridani",
                             "aliases": []}}
    write_yaml(cfg.STARS_YAML, stars)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "glyph_rescue", lambda *a: pytest.fail("no debe rescatar"))
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    assert run_main(monkeypatch, ["test_star", "--no-glyph"]) == 0


def test_main_sujeto_no_bayer_no_rescata(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """toy_vault trae 'Test Star' (no Bayer): el rescate ni se dispara — sin query extra."""
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "glyph_rescue", lambda *a: pytest.fail("no debe rescatar"))
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    assert run_main(monkeypatch, ["test_star"]) == 0


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
    assert r["why_excluded"] is None          # core → sin motivo (#30)


def test_query_ads_persiste_why_excluded(toy_classifier, ads_token, no_sleep, monkeypatch):
    """#30: el registro no-core lleva su motivo REAL en ads.json — acá el caso que el fallback
    viejo etiquetaba mal (facetas matcheadas + doctype limpio, excluido por `require`)."""
    monkeypatch.setattr(qa, "REQUIRE_TOPICS", ["rv"])
    doc = {"bibcode": "2020ApJ...2..2B", "title": ["Starspot survey"], "doctype": "article"}
    monkeypatch.setattr(qa, "requests", SimpleNamespace(get=fake_get_seq([FakeResp(200, payload([doc]))])))
    r = qa.query_ads("q", rows=10)[0]
    assert r["relevant"] is False and r["topics"] == ["actividad"]
    assert "require" in r["why_excluded"] and "doctype" not in r["why_excluded"]


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


def test_query_ads_cero_espurio_reintenta_y_recupera(toy_classifier, ads_token, no_sleep, monkeypatch):
    """#27: `numFound: 0` con HTTP 200 es sospechoso cuando se esperan hits — se reintenta con el
    mismo backoff y la corrida siguiente (338 papers en el caso real) es la que vale."""
    doc = {"bibcode": "2020ApJ...1..1A", "title": ["Starspots"], "doctype": "article"}
    monkeypatch.setattr(qa, "requests", SimpleNamespace(get=fake_get_seq([
        FakeResp(200, payload([], num_found=0)),          # cero espurio
        FakeResp(200, payload([doc])),                    # la misma query, ahora con datos
    ])))
    out = qa.query_ads("q", rows=10, expect_hits=True)
    assert [r["bibcode"] for r in out] == ["2020ApJ...1..1A"]
    assert no_sleep == [5]


def test_query_ads_cero_persistente_lanza(toy_classifier, ads_token, no_sleep, monkeypatch):
    """Si el 0 sobrevive a todos los reintentos, falla ruidoso (exit ≠ 0 en el CLI) en vez de
    persistir un corpus vacío; el mensaje deriva al nombre/alias del sujeto."""
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(200, payload([], num_found=0))] * 4)))
    with pytest.raises(qa.EmptyResultError, match="stars.yaml"):
        qa.query_ads("q", rows=10, expect_hits=True)
    assert len(no_sleep) == 3                 # 3 backoffs, 4 intentos


def test_query_ads_cero_legitimo_sin_expect_hits(toy_classifier, ads_token, no_sleep, monkeypatch):
    """Los ceros válidos (chaining, --sweep, --probe, fetch_bibcodes) no se tocan: sin
    `expect_hits` un 0 vuelve como lista vacía, sin reintentos."""
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(200, payload([], num_found=0))])))
    assert qa.query_ads("q", rows=10) == []
    assert no_sleep == []


def test_main_query_directa_espera_hits(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """El call-site de la query directa (estrella) pasa expect_hits=True; el chaining, no."""
    seen = {}
    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False):
        seen["expect_hits"] = expect_hits
        return [rec("2020dirA....1A")]
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert seen["expect_hits"] is True


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
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False: [dict(r) for r in direct])
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
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False: [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: called.append(a) or [])
    run_main(monkeypatch, ["test_star", "--no-chain"])
    assert called == []


def test_main_persiste_truncado(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """Query directa truncada → main persiste `truncated: {num_found, rows}` en ads.json (#17),
    convirtiendo el aviso de stdout en una marca que el lint surface."""
    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False):
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
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False: [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    monkeypatch.setattr(qa, "fetch_bibcodes",
                        lambda bibs: [dict(rec("1988old.....1O", relevant=True), via="manual")])
    run_main(monkeypatch, ["test_star"])
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    manual = [r for r in data["records"] if r["via"] == "manual"]
    assert [r["bibcode"] for r in manual] == ["1988old.....1O"]


def test_main_extra_core_rescata_del_corte(toy_vault, toy_classifier, no_sleep, monkeypatch, capsys):
    """#39: el paper que la query SÍ trajo pero la lente descartó se rescata en el lugar
    (relevant/why_excluded/via) — antes `extra_core` sólo agregaba los ausentes y declararlo no
    hacía nada. El que ADS no devolvió se sigue trayendo por bibcode."""
    stars = {"Estrella Test": {"slug": "test_star", "simbad": "s", "ads_object": "Test Star",
                               "aliases": [], "extra_core": ["1991AJ....102.1813F", "1988old.....1O"]}}
    write_yaml(cfg.STARS_YAML, stars)
    directo = [rec("2020dirA....1A"),
               dict(rec("1991AJ....102.1813F", relevant=False), why_excluded="sin faceta obligatoria (rv)")]
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [dict(r) for r in directo])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    pedidos = []
    def fake_fetch(bibs):
        pedidos.extend(bibs)
        return [dict(rec("1988old.....1O", relevant=True), via="manual")]
    monkeypatch.setattr(qa, "fetch_bibcodes", fake_fetch)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert pedidos == ["1988old.....1O"]        # sólo se pide a ADS el que falta
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    bibs = {r["bibcode"]: r for r in data["records"]}
    r = bibs["1991AJ....102.1813F"]
    assert r["relevant"] is True and r["why_excluded"] is None and r["via"] == "manual"
    assert bibs["2020dirA....1A"]["via"] == "query"     # el resto no se toca
    assert data["n_relevant"] == 3
    assert "1 traídos de ADS · 1 rescatados del corte" in capsys.readouterr().out


def test_main_extra_core_avisa_bibcode_inexistente(toy_vault, toy_classifier, no_sleep, monkeypatch, capsys):
    """Un bibcode declarado que ADS no devuelve (typo) deja de desaparecer en silencio."""
    stars = {"Estrella Test": {"slug": "test_star", "simbad": "s", "ads_object": "Test Star",
                               "aliases": [], "extra_core": ["2020typo....1X"]}}
    write_yaml(cfg.STARS_YAML, stars)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    monkeypatch.setattr(qa, "fetch_bibcodes", lambda bibs: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert "2020typo....1X" in capsys.readouterr().out


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


# ── dry-run del delta de re-clasificación (#40) ──────────────────────────────

def write_ads_json(toy_vault, slug, records):
    d = toy_vault.ROOT / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"kind": "star", "slug": slug,
                                            "n_total": len(records), "records": records}),
                                encoding="utf-8")


def test_note_state_distingue_extraccion_de_stub(toy_vault):
    from conftest import mk_note
    mk_note(cfg.PAPERS, "2020extr....1A", {"bibcode": "2020extr....1A", "methods": ["ccf"]})
    mk_note(cfg.PAPERS, "2020stub....1B", {"bibcode": "2020stub....1B", "methods": []})
    assert qa.note_state("2020extr....1A") == "extraida"
    assert qa.note_state("2020stub....1B") == "stub"
    assert qa.note_state("2020nada....1C") == "sin_nota"


def test_classify_record_lee_el_formato_persistido(toy_classifier):
    """En ads.json `title` es string (no lista como en la respuesta cruda de ADS)."""
    assert qa.classify_record({"title": "Starspot evolution", "doctype": "article"})[1] is True
    # via: manual es override del usuario (#39): la regla no lo re-juzga
    assert qa.classify_record({"title": "algo ajeno", "doctype": "article", "via": "manual"})[1] is True


def test_reclass_diff_reporta_el_delta(toy_vault, toy_classifier, monkeypatch, capsys):
    """#40: con `require: [rv]` declarada, un paper de actividad SALE del core — y el reporte
    separa el que tiene extracción LLM (la decisión real) de los stubs."""
    from conftest import mk_note
    monkeypatch.setattr(qa, "REQUIRE_TOPICS", ["rv"])
    write_ads_json(toy_vault, "test_star", [
        {"bibcode": "1991AJ....102.1813F", "title": "rotation and activity", "abstract": "",
         "keyword": [], "doctype": "article", "relevant": True, "via": "query", "citation_count": 40},
        {"bibcode": "2015stub....1S", "title": "starspot survey", "abstract": "",
         "keyword": [], "doctype": "article", "relevant": True, "via": "chain:citations"},
        {"bibcode": "2020rv.....1R", "title": "radial velocity of the star", "abstract": "",
         "keyword": [], "doctype": "article", "relevant": True, "via": "query"},
        {"bibcode": "2021new....1N", "title": "radial velocity activity", "abstract": "",
         "keyword": [], "doctype": "article", "relevant": False, "via": "chain:references"},
    ])
    mk_note(cfg.PAPERS, "1991AJ....102.1813F", {"bibcode": "1991AJ....102.1813F",
                                                "methods": ["ccf", "bisector"]})
    mk_note(cfg.PAPERS, "2015stub....1S", {"bibcode": "2015stub....1S", "methods": []})
    assert qa.reclass_diff(["test_star"]) == 0
    out = capsys.readouterr().out
    assert "core 3 → 2" in out
    assert "SALEN del core: 2 — con extracción LLM: 1 · stubs: 1" in out
    assert "1991AJ....102.1813F" in out and "2015stub....1S" not in out   # stubs sólo se cuentan
    assert "ENTRAN al core: 1 — sin nota (a crear): 1  (1 chain:references)" in out


def test_reclass_diff_no_escribe_nada(toy_vault, toy_classifier):
    """Dry-run: ni ads.json ni la bóveda se tocan."""
    recs = [{"bibcode": "2020a....1A", "title": "activity", "abstract": "", "keyword": [],
             "doctype": "article", "relevant": True, "via": "query"}]
    write_ads_json(toy_vault, "test_star", recs)
    antes = (toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text()
    qa.reclass_diff(["test_star"])
    assert (toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text() == antes
    assert list(cfg.PAPERS.iterdir()) == []


def test_main_dry_run_sin_slug_barre_los_ingestados(toy_vault, toy_classifier, monkeypatch, capsys):
    write_ads_json(toy_vault, "test_star", [])
    write_ads_json(toy_vault, "otra", [])
    monkeypatch.setattr(qa, "query_ads", lambda *a, **kw: pytest.fail("el dry-run no consulta ADS"))
    assert run_main(monkeypatch, ["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "test_star:" in out and "otra:" in out


def test_main_dry_run_sin_corpus_error_amigable(toy_vault, toy_classifier, monkeypatch):
    with pytest.raises(SystemExit, match="ads.json"):
        run_main(monkeypatch, ["--dry-run"])


def test_probe_lista_todo_el_core(toy_classifier, capsys):
    recs = [rec(f"2020core...{i}A", cites=i) for i in range(30)] + [rec("2020non....1N", relevant=False)]
    qa.print_probe("q", recs)
    out = capsys.readouterr().out
    assert "30 CORE" in out
    assert out.count("[CORE]") == 30          # el core se lista completo, no top-N


# ── --sweep: barrido full-text 2b (issue #25) ────────────────────────────────

def mk_ads_json(root, slug, bibs):
    d = root / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"records": [{"bibcode": b} for b in bibs]}),
                                encoding="utf-8")


def test_sweep_lista_solo_core_nuevos(toy_vault, toy_classifier, no_sleep, monkeypatch, capsys):
    """--sweep: query full: con TODAS las grafías de nombre+aliases, y a la salida SÓLO los core
    que ads.json no tiene (ni los ya bajados, ni los no-core). No encadena ni escribe build/."""
    mk_ads_json(toy_vault.ROOT, "test_star", ["2020dirA....1A"])
    hits = [rec("2020dirA....1A", cites=9),               # ya en el corpus → afuera
            rec("1978survW...1W", cites=100),             # core nuevo → candidato
            rec("2020non....1N", relevant=False)]         # no-core → afuera
    queries = []
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, **kw: queries.append(q) or [dict(r) for r in hits])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: pytest.fail("--sweep no encadena"))
    before = (toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text()
    assert run_main(monkeypatch, ["test_star", "--sweep"]) == 0
    out = capsys.readouterr().out
    # la query expande alias y grafías sola (HD 12345 ↔ HD12345), sin probes a mano
    assert 'full:"Test Star"' in queries[0]
    assert 'full:"HD 12345"' in queries[0] and 'full:"HD12345"' in queries[0]
    assert "1 core NUEVOS" in out
    assert "t 1978survW...1W" in out
    assert "t 2020dirA....1A" not in out and "t 2020non....1N" not in out
    assert "extra_core" in out                            # el próximo paso queda dicho
    assert (toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text() == before   # preview


def test_sweep_corpus_cubierto(toy_vault, toy_classifier, no_sleep, monkeypatch, capsys):
    """0 candidatos → lo dice con el caveat epistemológico (0 acá NO prueba ausencia)."""
    mk_ads_json(toy_vault.ROOT, "test_star", ["2020dirA....1A"])
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, **kw: [rec("2020dirA....1A")])
    assert run_main(monkeypatch, ["test_star", "--sweep"]) == 0
    out = capsys.readouterr().out
    assert "ya cubre" in out and "NO prueba ausencia" in out


def test_sweep_sin_ads_json_error_amigable(toy_vault, toy_classifier, monkeypatch):
    with pytest.raises(SystemExit, match="corré primero"):
        run_main(monkeypatch, ["test_star", "--sweep"])


def test_sweep_con_topic_error(toy_vault, toy_classifier, monkeypatch, capsys):
    with pytest.raises(SystemExit):                       # ap.error → exit 2
        run_main(monkeypatch, ["gp", "--topic", "--sweep"])
    assert "retro-tag 3b" in capsys.readouterr().err
