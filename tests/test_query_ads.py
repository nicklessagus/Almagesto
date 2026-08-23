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
                        lambda names, rows, meta=None: [dict(rec("2000ApJ...544L.145H"), via="glyph"),
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
    assert data["truncated_glyph"] is None       # el superset no truncó (mock no llena meta) (#43)


def test_glyph_rescue_marca_truncamiento_del_superset(toy_classifier, ads_token, no_sleep,
                                                      monkeypatch, capsys):
    """#43: si el superset de la constelación supera `rows`, el corte top-por-citas pasa ANTES del
    filtro por glifo → rescate incompleto. La marca va a `meta["truncated_glyph"]` (para persistir
    en ads.json) y el warning genérico de query_ads se silencia: hablaría de la marca de la query
    DIRECTA, que acá no se llena — el aviso mentiría (visto en ε Eri: warning en stdout,
    `truncated: null` en disco)."""
    docs = [{"bibcode": "2000ApJ...544L.145H", "title": ["Planet Orbiting ∊ Eridani"],
             "abstract": "radial velocity", "doctype": "article"}]
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=lambda url, headers=None, params=None, timeout=None:
        FakeResp(200, payload(docs, num_found=2342))))
    meta = {}
    out = qa.glyph_rescue(["eps Eridani", "ε Eri"], rows=100, meta=meta)
    assert [r["bibcode"] for r in out] == ["2000ApJ...544L.145H"]
    assert meta["truncated_glyph"] == [{"letter": "epsilon", "constellations": ["Eri", "Eridani"],
                                        "num_found": 2342, "rows": 100}]
    assert "truncado" not in capsys.readouterr().out     # el warning genérico no se imprime


def test_main_persiste_truncado_glifo(toy_vault, toy_classifier, no_sleep, monkeypatch, capsys):
    """#43: main persiste `truncated_glyph` en ads.json (marca HERMANA de `truncated`, pero del
    superset del rescate) y avisa en stdout — el lint la surface como rescate incompleto."""
    stars = {"eps Eridani": {"slug": "test_star", "simbad": "s", "ads_object": "eps Eridani",
                             "aliases": ["ε Eri"]}}
    write_yaml(cfg.STARS_YAML, stars)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [rec("2020dirA....1A")])
    marca = [{"letter": "epsilon", "constellations": ["Eri", "Eridani"],
              "num_found": 2342, "rows": 2000}]
    def fake_glyph(names, rows, meta=None):
        if meta is not None:
            meta["truncated_glyph"] = list(marca)
        return []
    monkeypatch.setattr(qa, "glyph_rescue", fake_glyph)
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    assert data["truncated"] is None and data["truncated_glyph"] == marca
    assert "rescate por glifo incompleto" in capsys.readouterr().out


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


def test_query_ads_avisa_truncado_sin_meta_no_promete_marca(toy_classifier, ads_token, no_sleep,
                                                             monkeypatch, capsys):
    """`--sweep` y `--probe` llaman query_ads() sin `meta` (nadie va a persistir el corte en
    ads.json): la coletilla del aviso tiene que decirlo, no repetir la promesa de "queda marcado en
    ads.json → lint" que sólo vale cuando SÍ hay un `meta` para escribir esa marca (#17 al revés)."""
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(200, payload([], num_found=500))])))
    qa.query_ads("q", rows=10, meta=None)
    out = capsys.readouterr().out
    assert "esta query NO deja marca en ads.json" in out
    assert "queda marcado en ads.json" not in out


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
                        lambda q, rows=400, quiet_truncate=False, fq=qa.ASTRO_FQ:
                        [rec("2019man....1M", relevant=False)])
    out = qa.fetch_bibcodes(["2019man....1M"])
    assert out[0]["relevant"] is True and out[0]["via"] == "manual"


def test_query_ads_aplica_la_lente_astro_por_default(toy_classifier, ads_token, no_sleep, monkeypatch):
    """Toda query de DESCUBRIMIENTO acota el universo a database:astronomy."""
    calls = []
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(200, payload([]))], calls=calls)))
    qa.query_ads("q", rows=10)
    assert calls[0]["params"]["fq"] == "database:astronomy"


def test_el_sort_pedido_viaja_en_la_request(toy_classifier, ads_token, no_sleep, monkeypatch):
    """#79 punto 2 es **server-side**: con `numFound > rows` ADS devuelve el top por `sort` y CORTA
    el resto, así que la segunda pasada rescata algo sólo si su `date desc` llega a los params. El
    cableado `sort` → request no lo miraba nadie (los tests de `recent_pass` mockean `query_ads`, o
    sea el lado de acá del parámetro): hardcodear el orden dejaba la pasada re-pidiendo la MISMA
    página —el rescate entero mudo— con la suite entera en verde."""
    calls = []
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(200, payload([])), FakeResp(200, payload([]))], calls=calls)))
    qa.query_ads("q", rows=10)                                   # default: el histórico
    qa.query_ads("q", rows=10, sort=qa.RECENT_SORT)              # el de la segunda pasada
    assert [c["params"]["sort"] for c in calls] == [qa.CITES_SORT, qa.RECENT_SORT]


def test_fetch_bibcodes_no_aplica_la_lente_astro(toy_classifier, ads_token, no_sleep, monkeypatch):
    """#68: `extra_core` es override del clasificador, pero el `fq` era un SEGUNDO filtro que el
    override no esquivaba — un bibcode real fuera de database:astronomy (eprint de math.ST /
    eess.SP: el caso central del tema mixto) no volvía y la cadena lo reportaba como typo. Con el
    universo fijado por el usuario no hay ruido que filtrar: el fq sólo puede sacar de más."""
    calls = []
    doc = {"bibcode": "2024arXiv240513912Z", "title": ["Spectral estimators"], "doctype": "eprint"}
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(200, payload([doc]))], calls=calls)))
    out = qa.fetch_bibcodes(["2024arXiv240513912Z"])
    assert "fq" not in calls[0]["params"]                  # sin lente astro
    assert out[0]["bibcode"] == "2024arXiv240513912Z"
    assert out[0]["relevant"] is True and out[0]["via"] == "manual"


# ── main(): integración con red mockeada ─────────────────────────────────────

def run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["query_ads.py", *argv])
    return qa.main()


def test_main_estrella_chaining_dedup_y_via(toy_vault, toy_classifier, no_sleep, monkeypatch):
    direct = [rec("2020dirA....1A", cites=5), rec("2020dirB....1B", relevant=False, cites=9)]
    chained = [rec("2020chC....1C", cites=2, title="Test Star revisited"),  # sujeto en el título → entra
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
    """Query directa truncada → main persiste `truncated: {num_found, rows, recent}` en ads.json
    (#17 + #79), convirtiendo el aviso de stdout en una marca que el lint surface. La segunda
    pasada NO levanta la marca: sigue faltando el medio del universo."""
    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False,
                sort=qa.CITES_SORT):
        if meta is not None:
            meta.update(num_found=410, rows=rows, truncated=True)
        return [rec("2020dirA....1A")]           # la pasada por fecha no trae nada nuevo
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    assert run_main(monkeypatch, ["test_star", "--rows", "400"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    assert data["truncated"] == {"num_found": 410, "rows": 400, "recent": 0}


def test_main_segunda_pasada_por_fecha_al_truncar(toy_vault, toy_classifier, no_sleep, monkeypatch,
                                                  capsys):
    """#79 punto 2: con la query truncada, el `sort: citation_count desc` que viaja en la request
    se queda con lo VIEJO (las citas se acumulan con la edad) y corta la cola reciente. Como el
    orden es server-side, la única salida es volver a preguntar por fecha; lo recuperado entra con
    `via: query:recent` y —por correr antes del chaining— siembra también el grafo de citas."""
    ordenes = []

    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False,
                sort=qa.CITES_SORT):
        ordenes.append(sort)
        if sort == qa.CITES_SORT:
            if meta is not None:
                meta.update(num_found=5000, rows=rows, truncated=True)
            return [rec("1995oldA....1A", cites=500, year="1995")]
        return [rec("1995oldA....1A", cites=500, year="1995"),      # ya estaba → dedup
                rec("2026newB....1B", cites=1, year="2026"),        # la cola reciente
                rec("2026nonC....1C", relevant=False, year="2026")]  # no-core: es la misma query
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    sembrados = {}
    monkeypatch.setattr(qa, "chain_candidates",
                        lambda bibs, rows, filt: sembrados.setdefault("core", list(bibs)) and [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert ordenes == [qa.CITES_SORT, qa.RECENT_SORT]
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    vias = {r["bibcode"]: r["via"] for r in data["records"]}
    assert vias == {"1995oldA....1A": "query", "2026newB....1B": "query:recent",
                    "2026nonC....1C": "query:recent"}
    assert data["truncated"]["recent"] == 2
    assert set(sembrados["core"]) == {"1995oldA....1A", "2026newB....1B"}   # siembra el grafo
    assert "segunda pasada por fecha: +2" in capsys.readouterr().out


def test_main_sin_truncar_no_hay_segunda_pasada(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """La pasada extra cuesta una request a ADS: sólo corre si la primera realmente se cortó."""
    ordenes = []
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False,
                        sort=qa.CITES_SORT: ordenes.append(sort) or [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert ordenes == [qa.CITES_SORT]


def test_fallo_de_la_segunda_pasada_no_tira_la_corrida(toy_vault, toy_classifier, no_sleep,
                                                      monkeypatch, capsys):
    """La 2ª pasada es un rescate BEST-EFFORT sobre una query directa que ya volvió bien: cualquier
    excepción abortaba antes de escribir `ads.json` y el registro, tirando trabajo bueno. Degrada al
    estado honesto: `recent` AUSENTE = "no sé si la cola está cubierta", que es lo que el lint
    distingue de un `0` (que afirma cobertura)."""
    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False,
                sort=qa.CITES_SORT):
        if sort == qa.RECENT_SORT:
            raise RuntimeError("ADS 502")
        if meta is not None:
            meta.update(num_found=5000, rows=rows, truncated=True)
        return [rec("2020dirA....1A")]
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    assert data["truncated"]["num_found"] == 5000
    assert "recent" not in data["truncated"]          # no afirma nada sobre la cola
    out = capsys.readouterr().out
    assert "la segunda pasada por fecha falló" in out


def test_segunda_pasada_vacia_no_se_traga_el_cero_espurio(toy_classifier, no_sleep, monkeypatch):
    """Es la MISMA query que acaba de reportar numFound > rows: un cero ahí es el cero espurio de
    ADS (#27), no un resultado. Sin `expect_hits` volvía [] y la marca quedaba en `recent: 0`, que
    el lint lee como "la cola reciente ya está cubierta"."""
    # Hermético: `recent_pass` llega a `query_ads`, que pide el token ANTES de la request. Sin esto
    # el test lee el `vault/config/ads_dev_key` real —gitignored— y en un clone limpio o en CI muere
    # con RuntimeError antes de ejercitar nada de lo que dice testear.
    monkeypatch.setenv("ADS_DEV_KEY", "tok-test")
    vacías = [FakeResp(200, payload([], num_found=0))] * (len(qa.RETRY_WAITS_S) + 1)
    monkeypatch.setattr(qa, "requests", SimpleNamespace(get=fake_get_seq(vacías)))
    with pytest.raises(qa.EmptyResultError):
        qa.recent_pass("title:x", 10, set())


def test_recent_pass_pide_fecha_dedup_y_marca_via(toy_classifier, no_sleep, monkeypatch):
    """Unitario de la segunda pasada: misma `q` y mismo `rows`, sólo cambia el orden; silencia el
    aviso de truncado (hablaría del mismo corte que ya se reportó); devuelve SÓLO lo que la primera
    no trajo, actualizando `known` in situ (el caller lo usa después para el dedup del chaining)."""
    llamadas = []

    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False,
                sort=qa.CITES_SORT):
        llamadas.append({"q": q, "rows": rows, "sort": sort, "quiet": quiet_truncate})
        return [rec("2020viejo...1V"), rec("2026nuevo...1N"),
                rec("2026noncore..1C", relevant=False)]
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    known = {"2020viejo...1V"}
    out = qa.recent_pass("title:x", rows=400, known=known)
    assert llamadas == [{"q": "title:x", "rows": 400, "sort": qa.RECENT_SORT, "quiet": True}]
    assert no_sleep == [1.0]      # cortesía entre requests, como el resto de las queries a ADS
    assert [r["bibcode"] for r in out] == ["2026nuevo...1N", "2026noncore..1C"]
    assert all(r["via"] == "query:recent" for r in out)   # provenance: por qué entró
    assert known == {"2020viejo...1V", "2026nuevo...1N", "2026noncore..1C"}


def test_recent_pass_sin_novedad_devuelve_vacio(toy_classifier, no_sleep, monkeypatch):
    """Si la cola por fecha es la misma que ya trajo el top por citas, no inventa registros."""
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, **kw: [rec("2020viejo...1V")])
    assert qa.recent_pass("title:x", rows=400, known={"2020viejo...1V"}) == []


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


def test_probe_contrasta_facetas_eje_candidatas(toy_classifier, capsys):
    """#41: sin regla declarada, el probe muestra qué cortaría cada faceta si fuera obligatoria —
    el contraste que hace medible la decisión de declarar `require` (antes se discutía)."""
    recs = [
        {"title": "radial velocity and activity", "topics": ["rv", "actividad"],
         "doctype": "article", "relevant": True, "citation_count": 5},
        {"title": "starspot survey", "topics": ["actividad"], "doctype": "article",
         "relevant": True, "citation_count": 3},
        {"title": "asteroseismology", "topics": [], "doctype": "article",
         "relevant": False, "citation_count": 9},
    ]
    qa.print_probe("q", recs)
    out = capsys.readouterr().out
    assert "OR (≥1 faceta cualquiera) → 2 CORE" in out
    assert "require: [rv]" in out and "1 CORE" in out          # la eje corta a la mitad
    assert "require: [actividad]" in out


def test_probe_contrasta_regla_declarada_contra_or(toy_classifier, monkeypatch, capsys):
    """Con `require` ya declarada, el contraste es contra el OR puro (qué se está cortando)."""
    monkeypatch.setattr(qa, "REQUIRE_TOPICS", ["rv"])
    recs = [
        {"title": "rv", "topics": ["rv"], "doctype": "article", "relevant": True, "citation_count": 1},
        {"title": "act", "topics": ["actividad"], "doctype": "article", "relevant": False,
         "citation_count": 1},
    ]
    qa.print_probe("q", recs)
    out = capsys.readouterr().out
    assert "require=['rv'], min_topics=1" in out and "en OR puro serían 2 CORE" in out


def test_count_core_respeta_doctype_ruido(toy_classifier):
    recs = [{"topics": ["rv"], "doctype": "catalog"}, {"topics": ["rv"], "doctype": "article"},
            {"topics": [], "doctype": "article"}]
    assert qa.count_core(recs, [], 1) == 1
    assert qa.count_core(recs, ["actividad"], 1) == 0
    assert qa.count_core(recs, [], 2) == 0


def test_probe_lista_todo_el_core(toy_classifier, capsys):
    recs = [rec(f"2020core...{i}A", cites=i) for i in range(30)] + [rec("2020non....1N", relevant=False)]
    qa.print_probe("q", recs)
    out = capsys.readouterr().out
    assert "30 CORE" in out
    assert out.count("[CORE]") == 30          # el core se lista completo, no top-N


def test_main_probe_no_pide_slug_y_cablea_query_y_rows(toy_classifier, monkeypatch, capsys):
    """`--probe` es el único modo que `main()` despacha SIN pedir `slug` (ni siquiera lo mira: el
    `ap.error` de slug faltante queda más abajo). Nadie ejercita ese cableado a través de `main()` —
    los tests de arriba llaman `print_probe` directo—, así que un `dest` roto en el argumento (p.
    ej. `args.probe_query` sin actualizar el `if args.probe:`) o un default que apague la rama
    pasarían la suite entera y recién explotarían en el primer preview real del skill `setup`."""
    seen = {}
    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, fq=None,
                sort=qa.CITES_SORT):
        seen["q"], seen["rows"] = q, rows
        return [rec("2020probe.1P", cites=3)]
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    assert run_main(monkeypatch, ["--probe", 'abs:"radial velocity"', "--rows", "50"]) == 0
    assert seen == {"q": 'abs:"radial velocity"', "rows": 50}
    assert "1 CORE" in capsys.readouterr().out


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


def test_sweep_rankea_por_citas_por_ano(toy_vault, toy_classifier, no_sleep, monkeypatch, capsys):
    """#79 punto 1: el barrido existe para rescatar core POCO CITADO que se cayó del ranking, así
    que ordenarlo por citas crudas repetía el sesgo del mecanismo que le falló. Con citas/año el
    paper reciente que casi no tuvo tiempo de acumular citas deja de salir último."""
    mk_ads_json(toy_vault.ROOT, "test_star", [])
    hits = [rec("1978survW...1W", cites=100, year="1978"),   # tasa ~2/año
            rec("2026arbX....1X", cites=50, year="2026")]    # tasa 50/año pese a la mitad de citas
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, **kw: [dict(r) for r in hits])
    assert run_main(monkeypatch, ["test_star", "--sweep"]) == 0
    filas = [ln for ln in capsys.readouterr().out.splitlines() if "[CORE]" in ln]
    assert len(filas) == 2                                       # los dos son core nuevos
    assert "2026arbX....1X" in filas[0] and "1978survW...1W" in filas[1]


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


# ── compuerta de triage del chaining (#38) ───────────────────────────────────

def test_subject_in_title_cubre_grafias_y_glifos():
    assert qa.subject_in_title("HD22049 revisited", ["HD 22049"])          # sin espacio
    assert qa.subject_in_title("Planet orbiting ∊ Eridani", ["eps Eridani"])   # lookalike (#28)
    assert not qa.subject_in_title("A survey of nearby K dwarfs", ["eps Eridani"])
    assert not qa.subject_in_title(None, ["eps Eridani"])


def test_main_chaining_solo_auto_acepta_sujeto_en_titulo(toy_vault, toy_classifier, no_sleep,
                                                         monkeypatch, capsys):
    """El core del grafo con el sujeto en el título entra; el resto queda como CANDIDATO en
    ads.json (no se baja) a la espera del juicio."""
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [
        dict(rec("2020tit....1T", title="Activity of Test Star"), via="chain:citations"),
        dict(rec("2023PhDT....1P", title="Hunting for New Physics"), via="chain:references"),
    ])
    assert run_main(monkeypatch, ["test_star"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    assert {r["bibcode"] for r in data["records"]} == {"2020dirA....1A", "2020tit....1T"}
    assert [c["bibcode"] for c in data["candidates"]] == ["2023PhDT....1P"]
    assert "1 candidatos pendientes de juicio" in capsys.readouterr().out


def test_main_triage_no_repropone_descartados(toy_vault, toy_classifier, no_sleep, monkeypatch, capsys):
    d = toy_vault.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    cfg.save_decisiones("test_star", {
        "2023PhDT....1P": {"decision": "descartado", "motivo": "física de partículas"}})
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [
        dict(rec("2023PhDT....1P", title="Hunting for New Physics"), via="chain:references")])
    assert run_main(monkeypatch, ["test_star"]) == 0
    data = json.loads((d / "ads.json").read_text())
    assert data["candidates"] == [] and len(data["records"]) == 1
    assert "1 ya descartados antes" in capsys.readouterr().out


def test_load_triage_no_suprime_descartes_de_fuente_declarada(toy_vault):
    """#81: `decisiones` mezcla los DOS carriles — el candidato del citation chaining (`triage
    --drop`, sin `origen`) y la fuente DECLARADA de un tema off-ADS (`triage --drop-source`,
    `origen: fuente-declarada`). `load_triage` alimenta la compuerta del chaining (#38): un rechazo
    del otro carril no es un candidato del grafo de citas y no tiene que apagar la cola de
    candidatos por triage.py. Sin el filtro `es_del_carril` (query_ads.py:553) los dos descartes se
    confunden y el gate suprime de más."""
    cfg.save_decisiones("test_star", {
        "2020a....1A": {"decision": "descartado", "motivo": "ruido"},                       # chaining
        "2006RasmussenWilliams": {"decision": "descartado", "origen": "fuente-declarada",
                                  "motivo": "libro de texto general"},                       # otro carril
    })
    assert qa.load_triage("test_star") == {"2020a....1A"}


def test_n_dropped_chaining_no_cuenta_fuente_declarada(toy_vault):
    """#81/#64: `n_dropped_chaining` alimenta `busqueda.n_dropped`, que la cabecera de la ficha
    publica tal cual como "N descartados" del universo que trajo la QUERY del sujeto. Una fuente
    declarada de un tema off-ADS nunca participó de esa búsqueda (no hay `busqueda` en un tema
    off-ADS puro): contarla infla el número que se lee como el recorte del chaining. Tampoco cuenta
    un `aceptado` del propio carril chaining (pasó a `extra_core`, no es un descarte)."""
    cfg.save_decisiones("test_star", {
        "2020a....1A": {"decision": "descartado", "motivo": "ruido"},                       # cuenta
        "2020b....1B": {"decision": "aceptado", "motivo": "sí, va a extra_core"},           # no cuenta
        "2006RasmussenWilliams": {"decision": "descartado", "origen": "fuente-declarada",
                                  "motivo": "libro de texto general"},                       # no cuenta
    })
    assert qa.n_dropped_chaining("test_star") == 1


def test_n_dropped_chaining_no_cuenta_decision_no_descartada(toy_vault):
    """`n_dropped` es el campo del registro que la cabecera de la ficha PUBLICA como "N
    descartados". Hoy cuenta toda decisión del carril chaining sin mirar el campo `decision`, así
    que una decisión que no es un descarte —`--migrate` importa el juicio viejo tal cual, y el
    registro se edita a mano por instrucción del propio framework— infla el número que la bóveda
    afirma sobre su propio universo de papers."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.save_decisiones("test_star", {
        "2020aaa...1..1A": {"decision": "descartado", "motivo": "ruido", "fecha": "2026-08-01"},
        "2020bbb...1..1B": {"decision": "aceptado", "motivo": "pertinente", "fecha": "2026-08-01"},
    })
    assert qa.n_dropped_chaining("test_star") == 1


def test_main_extra_core_no_vuelve_a_la_cola_de_triage(toy_vault, toy_classifier, no_sleep,
                                                       monkeypatch):
    """#42: el merge de `extra_core` corre ANTES del chaining, así que un paper ya curado (sin el
    sujeto en el título) que el grafo vuelve a traer NO se re-propone como candidato — la
    persistencia de la compuerta vale para los DOS lados de la decisión (descartes en triage.json,
    aceptaciones en extra_core) — y el curado además siembra el grafo de citas."""
    stars = {"Estrella Test": {"slug": "test_star", "simbad": "s", "ads_object": "Test Star",
                               "aliases": [], "extra_core": ["2010ext.....1E"]}}
    write_yaml(cfg.STARS_YAML, stars)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "fetch_bibcodes",
                        lambda bibs: [dict(rec("2010ext.....1E"), via="manual")])
    sembrados = {}
    def fake_chain(bibs, rows, filt):
        sembrados["core"] = list(bibs)
        return [dict(rec("2010ext.....1E"), via="chain:citations"),      # ya curado → NO re-proponer
                dict(rec("2023PhDT....1P", title="Hunting for New Physics"), via="chain:references")]
    monkeypatch.setattr(qa, "chain_candidates", fake_chain)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert "2010ext.....1E" in sembrados["core"]          # el curado siembra el grafo
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    bibs = {r["bibcode"]: r["via"] for r in data["records"]}
    assert bibs["2010ext.....1E"] == "manual"             # core por decisión del usuario…
    assert [c["bibcode"] for c in data["candidates"]] == ["2023PhDT....1P"]   # …y FUERA de la cola


def test_main_no_triage_restaura_el_comportamiento_viejo(toy_vault, toy_classifier, no_sleep,
                                                         monkeypatch):
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [
        dict(rec("2023PhDT....1P", title="Hunting for New Physics"), via="chain:references")])
    assert run_main(monkeypatch, ["test_star", "--no-triage"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    assert len(data["records"]) == 2 and data["candidates"] == []


def test_main_tema_no_aplica_la_compuerta(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """En un tema la query ES la definición del tema → su core (y el del grafo anclado) entra solo."""
    write_yaml(cfg.TOPICS_YAML, {"gp": {"title": "GP", "area": "methods", "concept": "gp",
                                        "query": 'abs:"gaussian process"'}})
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a: [
        dict(rec("2020chX....1X", title="cualquier cosa"), via="chain:references")])
    assert run_main(monkeypatch, ["gp", "--topic"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "gp" / "ads.json").read_text())
    assert len(data["records"]) == 2 and data["candidates"] == []


def test_main_persiste_el_registro_de_busqueda(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """#64: al cerrar la corrida queda el registro VERSIONADO del sujeto — query efectiva, fecha,
    límite, conteos y versión del clasificador. La query de una estrella la arma build_query y
    antes se tiraba: no había forma de saber sobre qué universo afirma la ficha."""
    direct = [rec("2020dirA....1A", cites=5), rec("2020dirB....1B", relevant=False, cites=9)]

    def fake_query(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, fq=None,
                   sort=qa.CITES_SORT):
        if meta is not None:
            meta.update(num_found=1837, rows=rows, truncated=True)
        return [dict(r) for r in direct]
    monkeypatch.setattr(qa, "query_ads", fake_query)
    monkeypatch.setattr(qa, "chain_candidates", lambda bibs, rows, filt: [])
    cfg.save_decisiones("test_star", {"2019old....1..1O": {"decision": "descartado"}})
    assert run_main(monkeypatch, ["test_star"]) == 0
    b = cfg.load_registro("test_star")["busqueda"]
    assert b["fecha"] and b["query"] and "Test Star" in b["query"]     # la Solr efectiva, no None
    assert b["n_found"] == 1837 and b["n_core"] == 1 and b["truncated"] is True
    assert b["n_dropped"] == 1                                        # lee las decisiones vigentes
    assert b["almagesto_version"] == cfg.ALMAGESTO_VERSION
    # la LENTE queda registrada textual: almagesto_version es la del framework, no la de la regla
    # (cambiar una regex mueve el corte sin mover la versión)
    assert b["lente"]["topics"] and isinstance(b["lente"]["topics"], dict)
    assert b["lente"]["require"] == list(qa.REQUIRE_TOPICS)
    assert b["lente"]["min_topics"] == qa.MIN_TOPICS
    assert cfg.load_registro("test_star")["decisiones"]                # no pisó el juicio del triage
