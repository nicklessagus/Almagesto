"""query_ads: clasificador, variantes de designación, retry/truncado, chaining, main()."""
import importlib.util
import json
import re
import sys
from types import SimpleNamespace

import pytest
import requests as real_requests

import query_ads as qa
from conftest import SCRIPTS, write_yaml
import lib_config as cfg


@pytest.fixture
def toy_classifier(monkeypatch):
    """Clasificador determinista para los tests (query_ads compila el real al importar). Resetea la
    regla de combinación a su default (require=[], min_facets=1) para no heredar la del objective.yaml
    real; los tests de la regla declarativa la sobre-escriben."""
    monkeypatch.setattr(qa, "FACET_PATTERNS", {
        "actividad": re.compile("activity|starspot", re.I),
        "rv": re.compile("radial velocity", re.I),
    })
    monkeypatch.setattr(qa, "NOISE_DOCTYPES", {"catalog", "proposal"})
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    monkeypatch.setattr(qa, "MIN_FACETS", 1)


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
    facets, relevant = qa.classify({"title": ["activity survey"], "doctype": "catalog"})
    assert facets == ["actividad"] and relevant is False


def test_classify_sin_match(toy_classifier):
    assert qa.classify({"title": ["asteroseismology"], "doctype": "article"}) == ([], False)


# ── regla de combinación declarativa: require / min_facets (#15) ──────────────

def test_classify_require_faceta_obligatoria(toy_classifier, monkeypatch):
    """`require: [rv]` → un paper que matchea sólo `actividad` deja de ser core; el que matchea
    `rv` (aunque no `actividad`) sí. La faceta del eje se vuelve AND, no OR.  @inv INV-55"""
    monkeypatch.setattr(qa, "REQUIRE_FACETS", ["rv"])
    assert qa.classify({"title": ["starspot activity"], "doctype": "article"}) == (["actividad"], False)
    t, rel = qa.classify({"title": ["radial velocity survey"], "doctype": "article"})
    assert t == ["rv"] and rel is True
    # matchea ambas → core (require ⊆ matched)
    _, rel2 = qa.classify({"title": ["radial velocity"], "abstract": "activity", "doctype": "article"})
    assert rel2 is True


def test_classify_min_facets_dos(toy_classifier, monkeypatch):
    """`min_facets: 2` → una sola faceta no alcanza; hacen falta ≥2 cualesquiera."""
    monkeypatch.setattr(qa, "MIN_FACETS", 2)
    assert qa.classify({"title": ["radial velocity"], "doctype": "article"}) == (["rv"], False)
    t, rel = qa.classify({"title": ["radial velocity"], "abstract": "starspot activity",
                          "doctype": "article"})
    assert set(t) == {"actividad", "rv"} and rel is True


def test_classify_require_y_ruido_componen(toy_classifier, monkeypatch):
    """require se combina con el filtro de doctype ruido (AND de las tres condiciones)."""
    monkeypatch.setattr(qa, "REQUIRE_FACETS", ["rv"])
    _, rel = qa.classify({"title": ["radial velocity"], "doctype": "catalog"})
    assert rel is False                                   # matchea require pero es doctype ruido


def test_exclusion_reason_motivos(toy_classifier, monkeypatch):
    """#30: el motivo de exclusión se computa donde se decide (única implementación de la regla).
    Un excluido por `require` con facetas matcheadas y doctype limpio NO se etiqueta por doctype
    (el bug: el apéndice "Excluidos" decía `doctype: article`)."""
    monkeypatch.setattr(qa, "REQUIRE_FACETS", ["rv"])
    assert qa.exclusion_reason([], "article") == "sin tópico"              # rótulo histórico
    assert qa.exclusion_reason(["actividad"], "catalog") == "doctype: catalog"   # ídem
    why = qa.exclusion_reason(["actividad"], "article")
    assert "rv" in why and "require" in why and "doctype" not in why
    assert qa.exclusion_reason(["rv"], "article") is None                  # core → sin motivo


def test_exclusion_reason_min_facets(toy_classifier, monkeypatch):
    monkeypatch.setattr(qa, "MIN_FACETS", 2)
    assert "min_facets=2" in qa.exclusion_reason(["rv"], "article")
    assert qa.exclusion_reason(["rv", "actividad"], "article") is None


def test_classify_coherente_con_exclusion_reason(toy_classifier, monkeypatch):
    """`relevant` de classify ⟺ exclusion_reason None — no hay dos implementaciones de la regla.  @inv INV-24"""
    monkeypatch.setattr(qa, "REQUIRE_FACETS", ["rv"])
    for rec_, why_topics in [({"title": ["starspot activity"], "doctype": "article"}, ["actividad"]),
                             ({"title": ["radial velocity"], "doctype": "article"}, ["rv"]),
                             ({"title": ["asteroseismology"], "doctype": "article"}, [])]:
        facets, rel = qa.classify(rec_)
        assert facets == why_topics
        assert rel is (qa.exclusion_reason(facets, rec_["doctype"]) is None)


def test_combination_rule_defaults():
    """Sin declarar nada → (require=[], min_facets=1): el comportamiento histórico (≥1 faceta OR)."""
    assert qa.combination_rule({}, {"rv": None, "actividad": None}) == ([], 1)
    assert qa.combination_rule({"min_facets": 2, "require": ["rv"]},
                               {"rv": None, "actividad": None}) == (["rv"], 2)


def test_require_faceta_inexistente_falla():
    """Guard de config: una faceta en `require` ausente de `facets` filtraría TODO en silencio →
    falla ruidoso (mismo camino que corre al importar el módulo)."""
    with pytest.raises(RuntimeError, match="require nombra facetas ausentes"):
        qa.combination_rule({"require": ["no-existe"]}, {"rv": None})


def test_min_facets_invalido_falla_ruidoso():
    """AUD-143 — `min_facets` no se validaba, y es la otra mitad EXACTA del argumento que ya
    justificaba el chequeo de `require`.

    `min_facets: 99` sobre dos facetas deja TODO el corpus no-core **en silencio**; un `0` o un
    string hacen lo simétrico (core a todo, o se leen como el default por el `or 1`). Los tres son
    decisiones que alguien escribió en el YAML, no ausencias.  @inv INV-141"""
    facets = {"rv": None, "actividad": None}
    with pytest.raises(RuntimeError, match="sólo hay 2 faceta"):
        qa.combination_rule({"min_facets": 99}, facets)
    with pytest.raises(RuntimeError, match="entero ≥ 1"):
        qa.combination_rule({"min_facets": 0}, facets)
    with pytest.raises(RuntimeError, match="entero ≥ 1"):
        qa.combination_rule({"min_facets": "2"}, facets)
    assert qa.combination_rule({}, facets) == ([], 1)          # ausente sigue siendo el default


def test_una_faceta_vacia_o_rota_falla_ruidoso():
    """AUD-143 — `re.search("", texto)` matchea SIEMPRE: un `rv:` sin valor en el YAML hace core al
    corpus entero. Y una regex que no compila no matchea nunca, que se lee como «este paper no
    habla del tema» sobre un paper que nadie clasificó (AUD-163)."""
    with pytest.raises(RuntimeError, match="regex vacía"):
        qa.combination_rule({"facets": {"rv": "", "actividad": "x"}}, {"rv": None, "actividad": None})
    with pytest.raises(RuntimeError, match="no compilan"):
        qa.combination_rule({"facets": {"rv": "(sin cerrar"}}, {"rv": None})


# ── objective.yaml compilado a nivel de módulo: formas raras editadas a mano ──

def fresh_query_ads(monkeypatch, objective: dict):
    """Instancia FRESCA de `query_ads` compilada contra `objective`.

    Los tres sitios de `query_ads` que leen `objective.yaml` (líneas 117/120/122) corren a
    **nivel de módulo**: la lente se compila al importar. Para ejercitarlos hay que volver a
    ejecutar el módulo, y se hace bajo OTRO nombre para no dejar el `query_ads` compartido de la
    suite en un estado raro.
    """
    monkeypatch.setattr(cfg, "load_objective", lambda: objective)
    spec = importlib.util.spec_from_file_location("query_ads_f3probe", SCRIPTS / "query_ads.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # ← acá corren las líneas 117/120/122
    return mod


def test_noise_doctypes_escalar_no_desarma_el_filtro_de_ruido(monkeypatch):
    """`query_ads.py:122` — `NOISE_DOCTYPES = set(_REL.get("noise_doctypes") or [])`.

    Declarar UN solo doctype de ruido sin corchetes (`noise_doctypes: erratum`) es YAML válido y
    el error de edición más natural que existe. El `or []` no dispara (string truthy) y `set()`
    lo desarma en LETRAS: el filtro de ruido queda apagado en silencio y un erratum entra como
    **core**. Es exactamente el bug que `lib_config:236` ya documenta para `concept_areas`
    ("un `concept_areas: indicators` se desempaquetaba CARÁCTER POR CARÁCTER"), sin arreglar acá.
    """
    obj = {"relevance": {"facets": {"rv": "radial velocity"}, "noise_doctypes": "erratum"}}
    mod = fresh_query_ads(monkeypatch, obj)
    assert mod.NOISE_DOCTYPES == {"erratum"}, (
        f"la lente se desarmó en letras: {sorted(mod.NOISE_DOCTYPES)}")
    _, relevante = mod.classify({"title": ["a radial velocity survey"], "doctype": "erratum"})
    assert relevante is False, "un erratum entró como CORE: el filtro de ruido está apagado"


def test_relevance_escalar_reporta_en_vez_de_reventar_al_importar(monkeypatch):
    """`query_ads.py:117` — `_REL = (_OBJ.get("relevance") or {})`.

    Tres líneas más abajo el módulo YA tiene el error correcto para "objective.yaml sin
    relevance.facets": un `RuntimeError` que dice qué completar. Con `relevance:` escalar nunca
    se llega: el `_REL.get` de la línea 120 revienta antes con un `AttributeError` pelado, y como
    es a nivel de módulo se lleva puesto el import entero.
    """
    obj = {"relevance": "facets"}
    with pytest.raises(RuntimeError, match="relevance.facets"):
        fresh_query_ads(monkeypatch, obj)


def test_topics_como_lista_reporta_en_vez_de_reventar(monkeypatch):
    """`query_ads.py:120` — `(_REL.get("facets") or {}).items()`.

    `facets` es un MAPA faceta→regex. Escribirlo como lista de nombres es el error de forma
    esperable de un humano que copia la lista de facetas de la prosa del skill. Debería caer en
    el `RuntimeError` documentado ("no define relevance.facets"), no en un `AttributeError`.
    """
    obj = {"relevance": {"facets": ["actividad", "rv"]}}
    with pytest.raises(RuntimeError, match="relevance.facets"):
        fresh_query_ads(monkeypatch, obj)


def test_require_escalar_no_se_desarma_en_letras(monkeypatch):
    """`query_ads.py:141` — `require = list(rel.get("require") or [])`.

    `require: rv` (escalar, la forma natural para UNA faceta obligatoria) se convierte en
    `['r','v']`. El módulo sí aborta —bien—, pero el mensaje le dice al usuario que faltan las
    facetas `['r', 'v']` cuando lo que escribió es `rv`: el diagnóstico apunta al síntoma
    equivocado y manda a editar `facets`, que está bien.
    """
    obj = {"relevance": {"facets": {"rv": "radial velocity"}, "require": "rv"}}
    with pytest.raises(RuntimeError) as exc:
        fresh_query_ads(monkeypatch, obj)
    assert "'r'" not in str(exc.value), f"el require se desarmó en letras: {exc.value}"


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
    # @inv INV-52
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
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "glyph_rescue",
                        lambda names, rows, meta=None: [dict(rec("2000ApJ...544L.145H"), via="glyph"),
                                                        dict(rec("2020dirA....1A"), via="glyph")])  # dup → afuera
    sembrados = {}
    def fake_chain(bibs, rows, filt, **k):
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
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    marca = [{"letter": "epsilon", "constellations": ["Eri", "Eridani"],
              "num_found": 2342, "rows": 2000}]
    def fake_glyph(names, rows, meta=None):
        if meta is not None:
            meta["truncated_glyph"] = list(marca)
        return []
    monkeypatch.setattr(qa, "glyph_rescue", fake_glyph)
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    assert data["truncated"] is None and data["truncated_glyph"] == marca
    assert "rescate por glifo incompleto" in capsys.readouterr().out


def test_main_no_glyph_desactiva(toy_vault, toy_classifier, no_sleep, monkeypatch):
    stars = {"eps Eridani": {"slug": "test_star", "simbad": "s", "ads_object": "eps Eridani",
                             "aliases": []}}
    write_yaml(cfg.STARS_YAML, stars)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "glyph_rescue", lambda *a: pytest.fail("no debe rescatar"))
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    assert run_main(monkeypatch, ["test_star", "--no-glyph"]) == 0


def test_main_sujeto_no_bayer_no_rescata(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """toy_vault trae 'Test Star' (no Bayer): el rescate ni se dispara — sin query extra."""
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "glyph_rescue", lambda *a: pytest.fail("no debe rescatar"))
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
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
    assert r["facets"] == ["actividad"] and r["relevant"] is True
    assert r["why_excluded"] is None          # core → sin motivo (#30)


def test_query_ads_persiste_why_excluded(toy_classifier, ads_token, no_sleep, monkeypatch):
    """#30: el registro no-core lleva su motivo REAL en ads.json — acá el caso que el fallback
    viejo etiquetaba mal (facetas matcheadas + doctype limpio, excluido por `require`)."""
    monkeypatch.setattr(qa, "REQUIRE_FACETS", ["rv"])
    doc = {"bibcode": "2020ApJ...2..2B", "title": ["Starspot survey"], "doctype": "article"}
    monkeypatch.setattr(qa, "requests", SimpleNamespace(get=fake_get_seq([FakeResp(200, payload([doc]))])))
    r = qa.query_ads("q", rows=10)[0]
    assert r["relevant"] is False and r["facets"] == ["actividad"]
    assert "require" in r["why_excluded"] and "doctype" not in r["why_excluded"]


def test_query_ads_retry_429_luego_ok(toy_classifier, ads_token, no_sleep, monkeypatch):
    monkeypatch.setattr(qa, "requests", SimpleNamespace(
        get=fake_get_seq([FakeResp(429), FakeResp(200, payload([]))])))
    assert qa.query_ads("q") == []
    assert no_sleep == [5]                    # un retry con el primer backoff


def test_query_ads_5xx_persistente_lanza(toy_classifier, ads_token, no_sleep, monkeypatch):
    # @inv INV-69
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
    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k):
        seen["expect_hits"] = expect_hits
        return [rec("2020dirA....1A")]
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
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
            "keyword": [], "facets": ["actividad"] if relevant else [], "relevant": relevant}
    base.update(kw)
    return base


def test_chain_candidates_arma_subqueries_ancladas(no_sleep, monkeypatch):
    queries = []

    def fake_qa(q, rows=400, quiet_truncate=False, **k):
        queries.append(q)
        return [rec("2020chain...1C")]
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    bibs = [f"2020bib{i:04d}" for i in range(45)]     # 45 → chunks de 40+5 por operación
    out = qa.chain_candidates(bibs, rows=10, subject_filter='full:"X"')
    assert len(queries) == 4
    assert queries[0].startswith("references(") and 'AND (full:"X")' in queries[0]
    assert queries[2].startswith("citations(")
    assert all(h["via"] in ("chain:references", "chain:citations") for h in out)


def test_fetch_bibcodes_marca_la_curacion(no_sleep, monkeypatch):
    """#303 — el paper traído por bibcode entra core por CURACIÓN, y eso se registra en `puertas`
    (#126), no en un `via` hardcodeado: el `via` es el DECLARADO en la config (`EXTRA_CORE_VIA`), el
    mismo que escribe la otra rama del merge. Antes, el mismo item salía `manual` o `usuario` según
    si la query de ADS había devuelto ese bibcode — un reparto que no decidió nadie, y `manual` ni
    siquiera es un valor válido del vocabulario.

    @inv INV-60"""
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=400, quiet_truncate=False, fq=qa.ASTRO_FQ:
                        [rec("2019man....1M", relevant=False)])
    out = qa.fetch_bibcodes(["2019man....1M"], {"2019man....1M": "usuario"})
    assert out[0]["relevant"] is True
    assert out[0]["via"] == "usuario" and out[0]["via"] in cfg.EXTRA_CORE_VIA
    assert out[0]["puertas"] == ["manual"], "la procedencia de curación, siempre registrada"


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
    out = qa.fetch_bibcodes(["2024arXiv240513912Z"], {"2024arXiv240513912Z": "triage"})
    assert "fq" not in calls[0]["params"]                  # sin lente astro
    assert out[0]["bibcode"] == "2024arXiv240513912Z"
    assert out[0]["relevant"] is True and out[0]["via"] == "triage"


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
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k: [dict(r) for r in direct])
    monkeypatch.setattr(qa, "chain_candidates", lambda bibs, rows, filt, **k: [dict(r) for r in chained])
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
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k: [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: called.append(a) or [])
    run_main(monkeypatch, ["test_star", "--no-chain"])
    assert called == []


def test_main_persiste_truncado(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """Query directa truncada → main persiste `truncated: {num_found, rows, recent}` en ads.json
    (#17 + #79), convirtiendo el aviso de stdout en una marca que el lint surface. La segunda
    pasada NO levanta la marca: sigue faltando el medio del universo.  @inv INV-52"""
    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False,
                sort=qa.CITES_SORT, **k):
        if meta is not None:
            meta.update(num_found=410, rows=rows, truncated=True)
        return [rec("2020dirA....1A")]           # la pasada por fecha no trae nada nuevo
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
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
                sort=qa.CITES_SORT, **k):
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
                        lambda bibs, rows, filt, **k: sembrados.setdefault("core", list(bibs)) and [])
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
                        sort=qa.CITES_SORT, **k: ordenes.append(sort) or [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert ordenes == [qa.CITES_SORT]


def test_fallo_de_la_segunda_pasada_no_tira_la_corrida(toy_vault, toy_classifier, no_sleep,
                                                      monkeypatch, capsys):
    """La 2ª pasada es un rescate BEST-EFFORT sobre una query directa que ya volvió bien: cualquier
    excepción abortaba antes de escribir `ads.json` y el registro, tirando trabajo bueno. Degrada al
    estado honesto: `recent` AUSENTE = "no sé si la cola está cubierta", que es lo que el lint
    distingue de un `0` (que afirma cobertura)."""
    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False,
                sort=qa.CITES_SORT, **k):
        if sort == qa.RECENT_SORT:
            raise RuntimeError("ADS 502")
        if meta is not None:
            meta.update(num_found=5000, rows=rows, truncated=True)
        return [rec("2020dirA....1A")]
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
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
                sort=qa.CITES_SORT, **k):
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
                               "aliases": [], "extra_core": [{"bibcode": "1988old.....1O", "via": "usuario", "motivo": "test"}]}}
    write_yaml(cfg.STARS_YAML, stars)
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k: [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    monkeypatch.setattr(qa, "fetch_bibcodes",
                        lambda bibs, via_de=None: [dict(rec("1988old.....1O", relevant=True),
                                                          via="usuario", puertas=["manual"])])
    run_main(monkeypatch, ["test_star"])
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    # #303: la curación se reconoce por `puertas: [manual]` (la procedencia), y el `via` es el
    # DECLARADO en la config — no un string que dos ramas del merge escribían distinto.
    curados = [r for r in data["records"] if "manual" in (r.get("puertas") or [])]
    assert [r["bibcode"] for r in curados] == ["1988old.....1O"]
    assert curados[0]["via"] == "usuario"


def test_main_extra_core_rescata_del_corte(toy_vault, toy_classifier, no_sleep, monkeypatch, capsys):
    """#39: el paper que la query SÍ trajo pero la lente descartó se rescata en el lugar
    (relevant/why_excluded/via) — antes `extra_core` sólo agregaba los ausentes y declararlo no
    hacía nada. El que ADS no devolvió se sigue trayendo por bibcode."""
    stars = {"Estrella Test": {"slug": "test_star", "simbad": "s", "ads_object": "Test Star",
                               "aliases": [], "extra_core": [{"bibcode": "1991AJ....102.1813F", "via": "usuario", "motivo": "test"}, {"bibcode": "1988old.....1O", "via": "usuario", "motivo": "test"}]}}
    write_yaml(cfg.STARS_YAML, stars)
    directo = [rec("2020dirA....1A"),
               dict(rec("1991AJ....102.1813F", relevant=False), why_excluded="sin faceta obligatoria (rv)")]
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [dict(r) for r in directo])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    pedidos = []
    def fake_fetch(bibs, via_de=None):
        pedidos.extend(bibs)
        return [dict(rec("1988old.....1O", relevant=True), via="manual")]
    monkeypatch.setattr(qa, "fetch_bibcodes", fake_fetch)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert pedidos == ["1988old.....1O"]        # sólo se pide a ADS el que falta
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    bibs = {r["bibcode"]: r for r in data["records"]}
    r = bibs["1991AJ....102.1813F"]
    # D-58: el `via` declarado en la config reemplaza al "manual" hardcodeado — la ficha puede
    # decir si el paper entró por juicio del usuario, por el triage o por el corpus.
    assert r["relevant"] is True and r["why_excluded"] is None and r["via"] == "usuario"
    # #303 — y con su PUERTA registrada. En una ESTRELLA no corre `reclassify_for_theme`, así que
    # el único lugar donde puede quedar la marca de curación es este merge.
    assert "manual" in (r.get("puertas") or []), "el rescatado del corte quedó sin puerta"
    assert bibs["2020dirA....1A"]["via"] == "query"     # el resto no se toca
    assert data["n_relevant"] == 3
    assert "1 traídos de ADS · 1 rescatados del corte" in capsys.readouterr().out


def test_main_extra_core_avisa_bibcode_inexistente(toy_vault, toy_classifier, no_sleep, monkeypatch, capsys):
    """Un bibcode declarado que ADS no devuelve (typo) deja de desaparecer en silencio."""
    stars = {"Estrella Test": {"slug": "test_star", "simbad": "s", "ads_object": "Test Star",
                               "aliases": [], "extra_core": [{"bibcode": "2020typo....1X", "via": "usuario", "motivo": "test"}]}}
    write_yaml(cfg.STARS_YAML, stars)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    monkeypatch.setattr(qa, "fetch_bibcodes", lambda bibs, via_de=None: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert "2020typo....1X" in capsys.readouterr().out


def test_main_extra_core_escalar_no_pierde_la_curacion(toy_vault, monkeypatch, capsys):
    """`query_ads.py:910` — `extra = [b for b in (meta.get("extra_core") or []) if b]`.

    Gemelo de R5 (`test_check_retractions.py`) en el consumidor donde más duele. `extra_core` es
    el ÚNICO lugar donde sobrevive la aceptación de un candidato del triage (`build/` es scratch;
    los rechazos van al registro, las aceptaciones acá). Con un escalar, lo que se le pide a ADS
    son N bibcodes de una letra y el bibcode real **no se pide nunca**: el paper que el usuario
    acaba de curar a mano no entra al core y nadie avisa. El aviso de "bibcode inexistente" que
    existe desde #39 dispara, pero nombrando las letras.
    """
    write_yaml(cfg.STARS_YAML, {"Estrella Test": {
        "slug": "test_star", "simbad": "s", "ads_object": "Test Star",
        "aliases": [], "extra_core": [{"bibcode": "1988old.....1O", "via": "usuario", "motivo": "test"}]}})
    monkeypatch.setattr(qa, "FACET_PATTERNS", {"rv": re.compile("radial velocity", 2)})
    monkeypatch.setattr(qa, "NOISE_DOCTYPES", set())
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    monkeypatch.setattr(qa, "MIN_FACETS", 1)
    monkeypatch.setattr(qa, "time", type("T", (), {"sleep": staticmethod(lambda s: None)})())
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k: [])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    pedidos: list = []
    monkeypatch.setattr(qa, "fetch_bibcodes", lambda bibs, via_de=None: pedidos.extend(bibs) or [])
    run_main(monkeypatch, ["test_star"])
    assert pedidos == ["1988old.....1O"], f"se le pidió a ADS: {pedidos}"


def test_main_aliases_escalar_en_stars_yaml(toy_vault, monkeypatch, capsys):
    """`query_ads.py:860` (y su gemelo 613, `make_notes.py:984/1093`) —
    `[cfg.require_field(...)] + meta.get("aliases", [])`.

    Fuera del grep canónico (usa el default posicional en vez de `or []`) pero es el MISMO
    defecto: el default sólo actúa si la clave está **ausente**; una `aliases:` presente y
    escalar pasa igual y `list + str` levanta `TypeError`. Escribir UN alias sin corchetes es la
    forma natural de la primera edición de `stars.yaml`, que es un archivo de instancia editado a
    mano por definición. El fallo cae en el arranque mismo del ingest, sin decir qué corregir.
    """
    write_yaml(cfg.STARS_YAML, {"Estrella Test": {
        "slug": "test_star", "simbad": "s", "ads_object": "Test Star", "aliases": "HD 12345"}})
    monkeypatch.setattr(qa, "FACET_PATTERNS", {"rv": re.compile("radial velocity", 2)})
    monkeypatch.setattr(qa, "NOISE_DOCTYPES", set())
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    monkeypatch.setattr(qa, "MIN_FACETS", 1)
    monkeypatch.setattr(qa, "time", type("T", (), {"sleep": staticmethod(lambda s: None)})())
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k: [])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    monkeypatch.setattr(qa, "fetch_bibcodes", lambda bibs, via_de=None: [])
    # ⚠ **#182.** Esto asserteaba SÓLO «no revienta con TypeError», y el comentario afirmaba además
    # que «el alias mal escrito se reporta» sin medirlo. Con eso, cambiar `_listify_curado` por
    # `cfg.as_list` —que TIRA el escalar en vez de preservarlo— dejaba la suite ENTERA verde: el
    # alias se perdía en silencio, y un alias que falta es un paper que nunca aparece, degradando
    # los tres mecanismos de recall a la vez (#82). Se mide lo que la función promete.
    queries: list = []
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        queries.append(q) or [])
    run_main(monkeypatch, ["test_star"])
    assert queries and "HD 12345" in queries[0], (
        "el alias escalar tiene que LLEGAR a la query, no perderse: `listify_curado` lo preserva "
        f"(`as_list` lo tiraría). Query efectiva: {queries[0] if queries else None!r}")
    assert "escrito como escalar" in capsys.readouterr().out, \
        "y se reporta, para que la forma se corrija en origen"


def test_main_tema_extra_only(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """Tema off-ADS MIXTO: --extra-only trae SÓLO los extra_core (sin query ni chaining), y no
    exige `query` — la vía ADS de un tema cuya bibliografía canónica vive fuera de ADS."""
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "Gaussian processes", "area": "methods",
                                        "concept": "gaussian-processes", "source": "web",
                                        "extra_core": [{"bibcode": "2012PASP..124.1015B", "via": "usuario", "motivo": "test"}]}})
    monkeypatch.setattr(qa, "query_ads", lambda *a, **kw: pytest.fail("no debe correr la query"))
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: pytest.fail("no debe encadenar"))
    monkeypatch.setattr(qa, "fetch_bibcodes",
                        lambda bibs, via_de=None: [dict(rec("2012PASP..124.1015B", relevant=True),
                                                          via="usuario", puertas=["manual"])])
    assert run_main(monkeypatch, ["gp", "--theme", "--extra-only"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "gp" / "ads.json").read_text())
    assert data["kind"] == "theme" and data["query"] is None
    assert [r["bibcode"] for r in data["records"]] == ["2012PASP..124.1015B"]
    assert data["records"][0]["via"] == "usuario"                     # #303: el declarado
    assert data["records"][0]["puertas"] == ["manual"]


def test_main_extra_only_sin_extra_core_error(toy_vault, toy_classifier, monkeypatch):
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "GP", "area": "methods",
                                        "concept": "gaussian-processes", "source": "web"}})
    with pytest.raises(SystemExit, match="no declara `extra_core`"):
        run_main(monkeypatch, ["gp", "--theme", "--extra-only"])


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
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "Gaussian processes", "area": "methods", "concept": "gaussian-processes",
                                         "source": "web"}})
    with pytest.raises(SystemExit, match="no tiene `query`.*ingest_theme"):
        run_main(monkeypatch, ["gp", "--theme"])


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
    separa el que tiene extracción LLM (la decisión real) de los stubs.  @inv INV-58"""
    from conftest import mk_note
    monkeypatch.setattr(qa, "REQUIRE_FACETS", ["rv"])
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
    """Dry-run: ni ads.json ni la bóveda se tocan. Es **una** de las dos caras del preview; la otra
    (`--probe`) la mide `test_probe_no_escribe_nada`.  @inv INV-59"""
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
        {"title": "radial velocity and activity", "facets": ["rv", "actividad"],
         "doctype": "article", "relevant": True, "citation_count": 5},
        {"title": "starspot survey", "facets": ["actividad"], "doctype": "article",
         "relevant": True, "citation_count": 3},
        {"title": "asteroseismology", "facets": [], "doctype": "article",
         "relevant": False, "citation_count": 9},
    ]
    qa.print_probe("q", recs)
    out = capsys.readouterr().out
    assert "OR (≥1 faceta cualquiera) → 2 CORE" in out
    assert "require: [rv]" in out and "1 CORE" in out          # la eje corta a la mitad
    assert "require: [actividad]" in out


def test_probe_contrasta_regla_declarada_contra_or(toy_classifier, monkeypatch, capsys):
    """Con `require` ya declarada, el contraste es contra el OR puro (qué se está cortando)."""
    monkeypatch.setattr(qa, "REQUIRE_FACETS", ["rv"])
    recs = [
        {"title": "rv", "facets": ["rv"], "doctype": "article", "relevant": True, "citation_count": 1},
        {"title": "act", "facets": ["actividad"], "doctype": "article", "relevant": False,
         "citation_count": 1},
    ]
    qa.print_probe("q", recs)
    out = capsys.readouterr().out
    assert "require=['rv'], min_facets=1" in out and "en OR puro serían 2 CORE" in out


def test_count_core_respeta_doctype_ruido(toy_classifier):
    recs = [{"facets": ["rv"], "doctype": "catalog"}, {"facets": ["rv"], "doctype": "article"},
            {"facets": [], "doctype": "article"}]
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
                sort=qa.CITES_SORT, **k):
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
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: pytest.fail("--sweep no encadena"))
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
        run_main(monkeypatch, ["gp", "--theme", "--sweep"])
    assert "retro-tag 3b" in capsys.readouterr().err


# ── compuerta de triage del chaining (#38) ───────────────────────────────────

def test_subject_in_title_cubre_grafias_y_glifos():
    assert qa.subject_in_title("HD22049 revisited", ["HD 22049"])          # sin espacio
    assert qa.subject_in_title("Planet orbiting ∊ Eridani", ["eps Eridani"])   # lookalike (#28)
    assert not qa.subject_in_title("A survey of nearby K dwarfs", ["eps Eridani"])
    assert not qa.subject_in_title(None, ["eps Eridani"])


def test_subject_in_title_no_matchea_por_prefijo_de_catalogo():
    """@inv INV-72 — el número de catálogo más largo es OTRO objeto: `GJ 71` (tau Ceti) no puede
    matchear un título sobre `GJ 710`. Es el mismo modo de falla por containment que `CLAUDE.md`
    documenta para `grep` sobre el frontmatter, acá adentro de la compuerta de triage: un match
    espurio **auto-acepta** el paper (nivel 0, sin juicio humano) y lo mete al corpus de otra
    estrella. La continuación ALFABÉTICA sigue valiendo (`tau Cet` ↔ `tau Ceti`): lo que distingue
    a un objeto de otro en una designación de catálogo es el dígito."""
    assert not qa.subject_in_title("A close encounter with GJ 710", ["GJ 71"])
    assert not qa.subject_in_title("HD 220490 photometry", ["HD 22049"])
    assert qa.subject_in_title("Planets around GJ 71", ["GJ 71"])          # el sujeto real
    assert qa.subject_in_title("GJ 71 b confirmed", ["GJ 71"])             # seguido de letra
    assert qa.subject_in_title("tau Ceti revisited", ["tau Cet"])          # alfabético: sigue OK
    # AUD-174: el sufijo DECIMAL es convención real del catálogo Gliese — `GJ 84.1` es otra estrella
    assert not qa.subject_in_title("Rotation of GJ 84.1", ["GJ 84"])
    assert not qa.subject_in_title("GJ 1002.1 in the survey", ["GJ 1002"])
    assert qa.subject_in_title("GJ 84. A new planet", ["GJ 84"])           # punto de oración, no sufijo
    # y por la izquierda: un alias que es puro número no matchea la cola de otro
    assert not qa.subject_in_title("HD 3122064 revisited", ["122064"])


def test_main_chaining_solo_auto_acepta_sujeto_en_titulo(toy_vault, toy_classifier, no_sleep,
                                                         monkeypatch, capsys):
    """El core del grafo con el sujeto en el título entra; el resto queda como CANDIDATO en
    ads.json (no se baja) a la espera del juicio.  @inv INV-50"""
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [
        dict(rec("2020tit....1T", title="Activity of Test Star"), via="chain:citations"),
        dict(rec("2023PhDT....1P", title="Hunting for New Physics"), via="chain:references"),
    ])
    assert run_main(monkeypatch, ["test_star"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    assert {r["bibcode"] for r in data["records"]} == {"2020dirA....1A", "2020tit....1T"}
    assert [c["bibcode"] for c in data["candidates"]] == ["2023PhDT....1P"]
    assert "1 candidatos pendientes de juicio" in capsys.readouterr().out


def test_la_politica_de_auto_aceptacion_se_declara(toy_vault, toy_classifier, no_sleep,
                                                   monkeypatch, capsys):
    """AUD-196 / INV-55 — la política de auto-aceptación se DECLARA, no se hardcodea.

    No es una regla de relevancia (eso ya lo decidió la lente: estos candidatos son todos
    `relevant`), es la **compuerta de curación** que dice cuáles del grafo entran sin juicio humano.
    Cableada, era la única decisión de admisión que una instancia no podía tocar — y su precisión
    depende del corpus: `titulo` mide 18 % en una bóveda de estrellas y no significa nada en un tema
    de método."""
    obj = cfg.load_objective()
    obj["relevance"]["chain_autoaccept"] = "never"
    write_yaml(cfg.OBJECTIVE_YAML, obj)
    monkeypatch.setattr(qa, "_OBJ", obj)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [
        dict(rec("2020tit....1T", title="Activity of Test Star"), via="chain:citations")])
    assert run_main(monkeypatch, ["test_star"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    # con `never`, ni siquiera el que trae el sujeto en el título entra solo
    assert [c["bibcode"] for c in data["candidates"]] == ["2020tit....1T"]
    assert "2020tit....1T" not in {r["bibcode"] for r in data["records"]}

    obj["relevance"]["chain_autoaccept"] = "por-el-titulo"      # typo
    write_yaml(cfg.OBJECTIVE_YAML, obj)
    monkeypatch.setattr(qa, "_OBJ", obj)
    with pytest.raises(SystemExit, match="chain_autoaccept"):
        run_main(monkeypatch, ["test_star"])


def test_main_triage_no_repropone_descartados(toy_vault, toy_classifier, no_sleep, monkeypatch, capsys):
    # @inv INV-49
    d = toy_vault.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    cfg.save_decisiones("test_star", {
        "2023PhDT....1P": {"decision": "descartado", "motivo": "física de partículas"}})
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [
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
                               "aliases": [], "extra_core": [{"bibcode": "2010ext.....1E", "via": "usuario", "motivo": "test"}]}}
    write_yaml(cfg.STARS_YAML, stars)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "fetch_bibcodes",
                        lambda bibs, via_de=None: [dict(rec("2010ext.....1E"), via="usuario",
                                                          puertas=["manual"])])
    sembrados = {}
    def fake_chain(bibs, rows, filt, **k):
        sembrados["core"] = list(bibs)
        return [dict(rec("2010ext.....1E"), via="chain:citations"),      # ya curado → NO re-proponer
                dict(rec("2023PhDT....1P", title="Hunting for New Physics"), via="chain:references")]
    monkeypatch.setattr(qa, "chain_candidates", fake_chain)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert "2010ext.....1E" in sembrados["core"]          # el curado siembra el grafo
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    bibs = {r["bibcode"]: r["via"] for r in data["records"]}
    assert bibs["2010ext.....1E"] == "usuario"            # core por decisión del usuario (#303)…
    assert [c["bibcode"] for c in data["candidates"]] == ["2023PhDT....1P"]   # …y FUERA de la cola


def test_no_triage_ya_no_existe(toy_vault, monkeypatch, capsys):
    """D-48: la compuerta de triage NO se puede apagar por flag. Existía `--no-triage` "para
    restaurar el comportamiento viejo", y ese comportamiento es justo el que #55 midió con 18% de
    precisión: con el flag, todo lo que el grafo trae y clasifica core entra directo — incluidos
    los bibcodes que ya habías descartado con su motivo. El juicio persistido (#51) podía pisarse
    en silencio con un flag."""
    monkeypatch.setattr(sys, "argv", ["query_ads.py", "test_star", "--no-triage"])
    with pytest.raises(SystemExit) as exc:
        qa.main()
    assert exc.value.code == 2                      # argparse: flag desconocido
    assert "no-triage" in capsys.readouterr().err


def test_la_compuerta_no_se_puede_apagar(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """La otra mitad: sin el flag, el gate corre SIEMPRE para una estrella. Grabador sobre
    `load_triage` — si nadie lo consulta, el descarte persistido no está gateando nada."""
    consultado = []
    monkeypatch.setattr(qa, "load_triage", lambda slug: consultado.append(slug) or set())
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [
        dict(rec("2023PhDT....1P", title="Hunting for New Physics"), via="chain:references")])
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert consultado == ["test_star"]
    data = json.loads((toy_vault.ROOT / "build" / "test_star" / "ads.json").read_text())
    assert data["candidates"], "el candidato del chaining entró directo: la compuerta no corrió"


def test_main_tema_no_aplica_la_compuerta(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """En un tema la query ES la definición del tema → su core (y el del grafo anclado) entra solo."""
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "GP", "area": "methods", "concept": "gp",
                                        "query": 'abs:"gaussian process"'}})
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [
        dict(rec("2020chX....1X", title="cualquier cosa"), via="chain:references")])
    assert run_main(monkeypatch, ["gp", "--theme"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "gp" / "ads.json").read_text())
    assert len(data["records"]) == 2 and data["candidates"] == []


def test_main_persiste_el_registro_de_busqueda(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """#64: al cerrar la corrida queda el registro VERSIONADO del sujeto — query efectiva, fecha,
    límite, conteos y versión del clasificador. La query de una estrella la arma build_query y
    antes se tiraba: no había forma de saber sobre qué universo afirma la ficha.  @inv INV-51"""
    direct = [rec("2020dirA....1A", cites=5), rec("2020dirB....1B", relevant=False, cites=9)]

    def fake_query(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, fq=None,
                   sort=qa.CITES_SORT, **k):
        if meta is not None:
            meta.update(num_found=1837, rows=rows, truncated=True)
        return [dict(r) for r in direct]
    monkeypatch.setattr(qa, "query_ads", fake_query)
    monkeypatch.setattr(qa, "chain_candidates", lambda bibs, rows, filt, **k: [])
    cfg.save_decisiones("test_star", {"2019old....1..1O": {"decision": "descartado"}})
    assert run_main(monkeypatch, ["test_star"]) == 0
    b = cfg.load_busquedas("test_star")[-1]
    assert b["fecha"] and b["query"] and "Test Star" in b["query"]     # la Solr efectiva, no None
    assert b["n_found"] == 1837 and b["n_core"] == 1 and b["truncated"] is True
    assert b["n_dropped"] == 1                                        # lee las decisiones vigentes
    assert b["almagesto_version"] == cfg.ALMAGESTO_VERSION
    # la LENTE queda registrada textual: almagesto_version es la del framework, no la de la regla
    # (cambiar una regex mueve el corte sin mover la versión)
    assert b["lente"]["facets"] and isinstance(b["lente"]["facets"], dict)
    assert b["lente"]["require"] == list(qa.REQUIRE_FACETS)
    assert b["lente"]["min_facets"] == qa.MIN_FACETS
    assert cfg.load_registro("test_star")["decisiones"]                # no pisó el juicio del triage


def test_query_ads_rehusa_lente_vacia(toy_vault, monkeypatch, capsys):
    """D-6 / INV-80: con `objective.yaml` ilegible la lente queda vacía y el clasificador marcaría
    TODO como no-core (o todo como core, según la regla) con una regla que nadie escribió — y el
    registro guardaría esa lente vacía como si fuera la vigente. `main()` rehúsa operar nombrando
    el archivo y el motivo; `classify` no llega a correr.  @inv INV-80"""
    cfg.OBJECTIVE_YAML.write_text("name: X\nrelevance:\n  facets:\n    rv: activity: starspot\n", encoding="utf-8")
    llamadas = []
    monkeypatch.setattr(qa, "classify", lambda *a, **k: llamadas.append(a) or [])
    monkeypatch.setattr(sys, "argv", ["query_ads.py", "test_star"])
    with pytest.raises(SystemExit) as exc:
        qa.main()
    assert "objective.yaml" in str(exc.value)
    assert llamadas == []


def test_escotillas_quedan_en_el_registro(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """D-48: lo que no se puede apagar se registra. Dos entradas del registro con los mismos
    conteos pueden describir corridas distintas si una usó `--yes` y la otra no.  @inv INV-44"""
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2020dirA....1A")])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    assert run_main(monkeypatch, ["test_star", "--no-chain"]) == 0
    assert "--no-chain" in cfg.load_busquedas("test_star")[-1]["escotillas"]


def test_probe_reporta_el_costo_proyectado(capsys):
    """T-3: la lente es un PRESUPUESTO, no sólo un filtro. El probe existe para afinar el corte
    core/no-core, y hasta ahora mostraba cuántos papers entran pero no qué cuesta leerlos — que es
    la mitad de la decisión (D-13: el ingest promete leer TODOS los core)."""
    recs = [rec(f"2020a{i:03d}...1A") for i in range(10)]
    qa.print_probe("title:(x)", recs)
    out = capsys.readouterr().out
    assert "tokens" in out.lower()
    assert "240" in out or "240k" in out.lower()      # 10 core × 24k


# ── D-26 / INV-88: la relevancia de un tema de método es PROPIA del tema ──────────────────────

def _tema(facet="independent component|blind source separation", **extra):
    return {"title": "ICA", "area": "methods", "concept": "ica", "facet": facet, **extra}


def _rec(title="x", abstract="", citas=0, doctype="article"):
    return {"title": title, "abstract": abstract, "citation_count": citas,
            "doctype": doctype, "keyword": []}


def test_sin_faceta_propia_ninguna_puerta_abre(toy_vault):
    """La faceta propia es la precondición, no una puerta: `core = faceta propia Y (≥1 puerta)`.
    Un paper de fMRI muy citado no entra por ser popular."""
    tema = _tema(fundacional_min_citas=100)
    facets, core, why = qa.classify_theme(_rec("fMRI resting state", citas=5000), tema)
    assert core is False and "faceta propia" in why


def test_puerta_2_el_fundacional_entra_sin_lente_astro(toy_vault, monkeypatch):
    """El caso Hyvärinen, que es el que motiva D-26: el paper fundacional de ICA **no menciona RV
    ni una vez**, así que la lente global con `require: [rv]` lo mata. Entra por ser fundacional en
    su campo: faceta propia + muchas citas.  @inv INV-88"""
    monkeypatch.setattr(qa, "REQUIRE_FACETS", ["rv"])
    tema = _tema(fundacional_min_citas=1000)
    facets, core, why = qa.classify_theme(
        _rec("Independent component analysis: algorithms and applications", citas=30000), tema)
    assert core is True and why is None


def test_puerta_3_la_lente_astro_global(toy_vault, monkeypatch):
    """Una aplicación astro del método entra por la lente global aunque tenga pocas citas."""
    monkeypatch.setattr(qa, "FACET_PATTERNS", {"rv": re.compile("radial velocity", re.I)})
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    monkeypatch.setattr(qa, "MIN_FACETS", 1)
    tema = _tema(fundacional_min_citas=1000)
    _, core, why = qa.classify_theme(
        _rec("Blind source separation applied to radial velocity data", citas=3), tema)
    assert core is True and why is None


def test_faceta_propia_sola_no_alcanza(toy_vault, monkeypatch):
    """El otro lado: sin filtro, «independent component analysis» devuelve miles de papers de fMRI,
    EEG y finanzas. La faceta propia sola los dejaría entrar a todos."""
    monkeypatch.setattr(qa, "FACET_PATTERNS", {"rv": re.compile("radial velocity", re.I)})
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    tema = _tema(fundacional_min_citas=1000)
    _, core, why = qa.classify_theme(_rec("Independent component analysis of EEG", citas=12), tema)
    assert core is False and "ninguna puerta" in why


def test_la_puerta_2_sin_umbral_declarado_se_apaga_y_se_dice(toy_vault, monkeypatch):
    """El umbral de «muy citado» NO se inventa: D-26 no fija un número y un default escondido
    decidiría por el usuario. Sin `fundacional_min_citas` declarado la puerta 2 **no abre**, y el
    motivo lo dice — no se degrada en silencio (misma doctrina que la lente vacía, INV-80).

    Se aísla la lente global (si no, la faceta `method` de la `objective.yaml` real abre la puerta
    3 y el test mediría otra cosa)."""
    monkeypatch.setattr(qa, "FACET_PATTERNS", {"rv": re.compile("radial velocity", re.I)})
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    _, core, why = qa.classify_theme(_rec("Independent component analysis", citas=99999), _tema())
    assert core is False and "fundacional_min_citas" in why


def test_doctype_ruido_sigue_afuera(toy_vault):
    tema = _tema(fundacional_min_citas=10)
    _, core, why = qa.classify_theme(
        _rec("Independent component analysis", citas=5000, doctype="catalog"), tema)
    assert core is False and "doctype" in why


def test_tema_sin_facet_declarada_no_clasifica(toy_vault):
    """Un tema de método sin `facet:` no puede usar esta regla: es la lente del tema, y sin ella
    no hay nada que aplicar. Rehúsa en vez de caer a la lente global en silencio."""
    with pytest.raises(SystemExit) as e:
        qa.classify_theme(_rec("x"), {"title": "T", "area": "methods"})
    assert "facet" in str(e.value)


def test_reclasificar_por_tema_cambia_el_veredicto_y_lo_cuenta(toy_vault, monkeypatch):
    """El cableado de D-26: los registros llegan clasificados por la lente GLOBAL (`to_records`), y
    para un tema de método hay que volver a juzgarlos con la regla del tema. La función devuelve
    cuántos cambió en cada dirección — sin eso, un ingest reclasifica en silencio y nadie puede
    auditar qué hizo la regla nueva."""
    monkeypatch.setattr(qa, "FACET_PATTERNS", {"rv": re.compile("radial velocity", re.I)})
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    monkeypatch.setattr(qa, "MIN_FACETS", 1)
    tema = _tema(fundacional_min_citas=1000)
    recs = [
        # entra por la puerta 2 aunque la lente global lo excluya (el caso Hyvärinen)
        dict(_rec("Independent component analysis: algorithms", citas=30000), bibcode="A",
             relevant=False, why_excluded="sin tópico"),
        # la lente global lo daba core (menciona RV) pero NO tiene la faceta propia del tema
        dict(_rec("Radial velocity survey of M dwarfs", citas=10), bibcode="B",
             relevant=True, why_excluded=None),
        # ya era core y sigue siéndolo: faceta propia + lente astro
        dict(_rec("Blind source separation of radial velocity data", citas=5), bibcode="C",
             relevant=True, why_excluded=None),
    ]
    entraron, salieron = qa.reclassify_for_theme(recs, tema)
    assert (entraron, salieron) == (["A"], ["B"])
    assert [r["relevant"] for r in recs] == [True, False, True]
    assert recs[1]["why_excluded"] == "sin la faceta propia del tema"


def test_reclasificar_no_toca_los_forzados_a_mano(toy_vault, monkeypatch):
    """`extra_core` es juicio del usuario y pisa a cualquier clasificador (#68/#39): la regla del
    tema no puede sacar lo que una persona metió a propósito."""
    monkeypatch.setattr(qa, "FACET_PATTERNS", {"rv": re.compile("radial velocity", re.I)})
    tema = _tema(fundacional_min_citas=1000)
    recs = [dict(_rec("Nada que ver", citas=1), bibcode="M", relevant=True,
                 why_excluded=None, via="manual")]
    assert qa.reclassify_for_theme(recs, tema) == ([], [])
    assert recs[0]["relevant"] is True


def test_reclasificar_sin_facet_es_no_op(toy_vault):
    """Un tema sin `facet:` no usa la regla nueva: la cadena sigue con la lente global, sin
    rehusar. (Rehusar es lo que hace `classify_theme` si alguien la llama directo.)"""
    recs = [dict(_rec("x"), bibcode="A", relevant=True, why_excluded=None)]
    assert qa.reclassify_for_theme(recs, {"title": "T"}) == ([], [])
    assert recs[0]["relevant"] is True


def test_main_aplica_la_regla_del_tema_a_la_query_directa(toy_vault, toy_classifier, no_sleep,
                                                          monkeypatch, capsys):
    """Integración del cableado: un tema con `facet:` re-juzga los registros de la query directa con
    la regla de D-26 y **persiste** el veredicto nuevo en `ads.json`. Sin este test la función
    existía pero nadie comprobaba que la cadena la llamara — el modo de falla que más veces mordió
    en este repo (una feature implementada y no cableada).  @inv INV-88"""
    write_yaml(cfg.THEMES_YAML, {"ica": {
        "title": "ICA", "area": "methods", "concept": "ica",
        "query": 'abs:"independent component"',
        "facet": "independent component",
        "fundacional_min_citas": 1000}})
    fundacional = dict(rec("2000fundA...1A", title="Independent component analysis: algorithms"),
                       citation_count=30000)
    ajeno = dict(rec("2020ajenB...1B", title="Something else entirely"), citation_count=5)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [fundacional, ajeno])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    assert run_main(monkeypatch, ["ica", "--theme"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "ica" / "ads.json").read_text())
    por_bib = {r["bibcode"]: r for r in data["records"]}
    assert por_bib["2000fundA...1A"]["relevant"] is True, "el fundacional entra por la puerta 2"
    assert por_bib["2020ajenB...1B"]["relevant"] is False
    assert por_bib["2020ajenB...1B"]["why_excluded"] == "sin la faceta propia del tema"
    assert "regla del tema (D-26)" in capsys.readouterr().out


def test_puerta_2_con_citas_desconocidas_no_evalua_en_vez_de_excluir(toy_vault, monkeypatch):
    """`citation_count: None` significa **no sé**, no «pocas». Si la puerta 2 lo tratara como 0,
    todo paper venido de arXiv quedaría no-fundacional por construcción. Se declara que la puerta
    no se pudo evaluar, con el motivo — INV-87 aplicado a la clasificación."""
    monkeypatch.setattr(qa, "FACET_PATTERNS", {"rv": re.compile("radial velocity", re.I)})
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    tema = _tema(fundacional_min_citas=1000)
    rec = _rec("Independent component analysis: algorithms", citas=None)
    _, core, why = qa.classify_theme(rec, tema)
    assert core is False
    assert "no se pudo evaluar" in why and "sin dato de citas" in why


def test_puerta_2_con_pocas_citas_dice_otra_cosa(toy_vault, monkeypatch):
    """El control: 3 citas SÍ es un dato, y el motivo tiene que distinguirse del anterior."""
    monkeypatch.setattr(qa, "FACET_PATTERNS", {"rv": re.compile("radial velocity", re.I)})
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    _, core, why = qa.classify_theme(_rec("Independent component analysis", citas=3),
                                     _tema(fundacional_min_citas=1000))
    assert core is False and "no se pudo evaluar" not in why


def test_puerta_1_propone_lo_que_el_corpus_cita_y_no_lo_clasifica(toy_vault, monkeypatch):
    """Puerta 1 de D-26 (§4.3 del plan): un paper que la query trajo, que la regla del tema **no**
    hace core, pero que **tu corpus cita**, pasa a CANDIDATO del triage — nunca a core.

    Es la señal que ninguna regex puede expresar: Hyvärinen tiene ~30k citas casi todas de fMRI y
    finanzas, y lo que lo vuelve tuyo es que tu gente lo cita. Y es lo que INV-24 obliga a que sea
    una propuesta: si clasificara, ser core dejaría de ser función de `(paper, lente)`.  @inv INV-88"""
    recs = [
        dict(_rec("Independent component analysis of EEG"), bibcode="A", doi="10.1/a",
             relevant=False, why_excluded="ninguna puerta abre (ni fundacional ni lente astro)"),
        dict(_rec("Otro que nadie cita"), bibcode="B", doi="10.1/b",
             relevant=False, why_excluded="sin la faceta propia del tema"),
        dict(_rec("Ya es core"), bibcode="C", relevant=True, why_excluded=None),
    ]
    idx = {"citas": {"A": ["2020Mio", "2021Mio"]}}
    props = qa.gate_cited_by_corpus(recs, index=idx)
    assert [p["bibcode"] for p in props] == ["A"]
    assert props[0]["via"] == "citado-por-corpus"
    assert props[0]["citado_por"] == ["2020Mio", "2021Mio"]
    assert recs[0]["relevant"] is False, "la puerta 1 PROPONE: no puede volver core a nadie"


def test_puerta_1_busca_por_todas_las_llaves_del_paper(toy_vault):
    """El corpus puede citarlo por bibcode (vía ADS) o por id de OpenAlex (vía OpenAlex): preguntar
    por una sola llave da un falso negativo. Se prueban todas las que el registro tenga."""
    recs = [dict(_rec("x"), bibcode="A", doi="10.1/a", openalex_id="https://openalex.org/W9",
                 relevant=False, why_excluded="x")]
    props = qa.gate_cited_by_corpus(recs, index={"citas": {"W9": ["2020Mio"]}})
    assert [p["bibcode"] for p in props] == ["A"]


def test_puerta_1_sin_indice_no_propone_nada(toy_vault):
    """Sin `build/citation_index.json` la puerta simplemente no aporta — no inventa candidatos ni
    rompe la cadena."""
    recs = [dict(_rec("x"), bibcode="A", relevant=False, why_excluded="x")]
    assert qa.gate_cited_by_corpus(recs, index={}) == []


def test_main_puerta_1_deja_el_candidato_en_ads_json(toy_vault, toy_classifier, no_sleep,
                                                     monkeypatch, capsys):
    """Integración: la cadena consulta el índice y **persiste** el candidato con su `via` y quiénes
    lo citan. Sin este test la puerta existía sin estar cableada.  @inv INV-88"""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "area": "methods", "concept": "ica",
                                         "query": 'abs:"independent component"',
                                         "facet": "independent component"}})
    (toy_vault.ROOT / "build").mkdir(parents=True, exist_ok=True)
    (toy_vault.ROOT / "build" / "citation_index.json").write_text(
        json.dumps({"citas": {"2005eegX....1X": ["2020Mio", "2021Mio"]}}), encoding="utf-8")
    eeg = dict(rec("2005eegX....1X", title="Independent component analysis of EEG"),
               citation_count=12)
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k: [eeg])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    assert run_main(monkeypatch, ["ica", "--theme"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "ica" / "ads.json").read_text())
    cand = {c["bibcode"]: c for c in data["candidates"]}
    assert "2005eegX....1X" in cand, "el que cita el corpus tiene que llegar al triage"
    assert cand["2005eegX....1X"]["via"] == "citado-por-corpus"
    assert cand["2005eegX....1X"]["citado_por"] == ["2020Mio", "2021Mio"]
    assert all(not r["relevant"] for r in data["records"]), "la puerta 1 no vuelve core a nadie"
    assert "puerta 1" in capsys.readouterr().out

# ── D-49 · la lente: forma, paridad y diff offline ───────────────────────────

def test_lens_used_y_lens_current_coinciden_sin_edicion():
    """RED #3 (doble vs real). `query_ads.lens_used` describe lo COMPILADO al importar y
    `lib_config.lens_current` re-lee el YAML: dos caminos al mismo hecho, y desde que la comparación
    se mudó a `lib_config` viven en **módulos distintos** — más razón para atarlos con un test. Si divergen, el lint reporta "lente cambiada" sobre una
    bóveda intacta (o calla sobre una que cambió). La paridad se FIJA acá, no se promete en prosa.

    Sin `toy_vault` A PROPÓSITO: la condición que interesa es la de producción —un proceso que
    importó `query_ads` y lee el MISMO `objective.yaml` que compiló—. Con la bóveda de juguete
    habría que recargar el módulo, y el reload dejaría las constantes apuntando al tmpdir para
    todos los tests que corren después."""
    assert qa.lens_used() == cfg.lens_current()
    assert cfg.lens_current()["facets"] == cfg.as_map(
        cfg.as_map(cfg.load_objective().get("relevance")).get("facets"))


def test_probe_no_escribe_nada(toy_vault, toy_classifier, capsys):
    """INV-59, la otra cara: `--probe` muestra el corte **sin bajar un archivo ni tocar config o
    vault**. El contrato lo daba por "la misma familia (sin hash-test propio)" y la marca vivía sólo
    en el dry-run, así que la mitad que un usuario corre en el `setup` —la que edita `objective.yaml`
    entre iteración e iteración— no la medía nadie.  @inv INV-59"""
    import hashlib

    def hash_arbol(base):
        h = hashlib.sha256()
        for f in sorted(base.rglob("*")):
            if f.is_file():
                h.update(str(f.relative_to(base)).encode())
                h.update(f.read_bytes())
        return h.hexdigest()

    antes = hash_arbol(toy_vault.VAULT)
    recs = [{"bibcode": "2020a....1A", "title": "starspot activity", "abstract": "",
             "keyword": [], "doctype": "article", "facets": ["actividad"], "relevant": True,
             "citation_count": 7, "why_excluded": None},
            {"bibcode": "2020b....1B", "title": "asteroseismology", "abstract": "",
             "keyword": [], "doctype": "article", "facets": [], "relevant": False,
             "citation_count": 3, "why_excluded": "sin tópico"}]
    assert qa.print_probe("abs:activity", recs) == 0
    assert hash_arbol(toy_vault.VAULT) == antes, "el probe escribió en vault/"
    assert not (toy_vault.ROOT / "build").exists(), "el probe no deja scratch"
    out = capsys.readouterr().out
    assert "1 CORE · 1 no-core" in out and "starspot activity" in out


# ── la exclusión declarada es VINCULANTE al clasificar (#112) ────────────────
def test_aplicar_excluidos_marca_no_core_y_deja_el_motivo(monkeypatch):
    monkeypatch.setattr(qa.cfg, "load_decisiones", lambda slug: {
        "2009Icar..201..504M": {"decision": "descartado", "origen": "sujeto",
                                "motivo": "off-topic por polisemia"}})
    recs = [{"bibcode": "2009Icar..201..504M", "relevant": True, "via": "query"},
            {"bibcode": "2012ApJ...747...12W", "relevant": True, "via": "query"}]
    tocados = qa.aplicar_excluidos(recs, "ica")
    assert tocados == ["2009Icar..201..504M"]
    # NO se borra del set: sigue visible, o el registro se leería como «la búsqueda nunca lo trajo»
    assert len(recs) == 2
    assert recs[0]["relevant"] is False and recs[0]["via"] == "manual-drop"
    assert "off-topic por polisemia" in recs[0]["why_excluded"]
    assert recs[1]["relevant"] is True


def test_aplicar_excluidos_ignora_el_carril_del_chaining(monkeypatch):
    """Un candidato del chaining descartado NO es lo mismo que un core excluido del sujeto: el
    filtro por carril es lo que hace que `origen` no sea decorativo (#81)."""
    monkeypatch.setattr(qa.cfg, "load_decisiones", lambda slug: {
        "2009Icar..201..504M": {"decision": "descartado", "motivo": "ruido del grafo"}})
    recs = [{"bibcode": "2009Icar..201..504M", "relevant": True}]
    assert qa.aplicar_excluidos(recs, "ica") == []
    assert recs[0]["relevant"] is True


def test_la_exclusion_se_aplica_DESPUES_de_todos_los_caminos_de_entrada(monkeypatch):
    """#112 al nivel de la corrida, no de la función. `aplicar_excluidos` corría **una sola vez**,
    justo después de la query directa — o sea ANTES de que sumen registros la 2ª pasada por fecha
    (#79), `extra_core`, el rescate por glifo (#28) y el chaining. Por esos cuatro caminos un paper
    sacado con `--drop-core` volvía con `relevant: True`, y `relevant` es lo que consumen
    `fetch_pdf` y `make_notes`: se bajaba y se le hacía nota.

    Es textualmente lo que #112 declara cerrado: *«una decisión que el clasificador ignora en
    silencio es peor que no tomarla»*. Este test fija la SEGUNDA pasada, que es la que decide."""
    import pathlib
    fuente = pathlib.Path(qa.__file__).read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("def main("):]
    llamadas = cuerpo.count("aplicar_excluidos(recs, args.slug)")
    assert llamadas >= 2, ("`aplicar_excluidos` corre una sola vez y los cuatro caminos que suman "
                           "registros después la esquivan")
    # y la última corre DESPUÉS del chaining, que es el último que agrega
    assert cuerpo.rindex("aplicar_excluidos(recs, args.slug)") > cuerpo.rindex("recs += chained")


def test_la_segunda_pasada_no_pisa_extra_core(monkeypatch):
    """La otra mitad: correr de nuevo tiene que ser SEGURO. Quien está en `extra_core` ya tuvo su
    decisión **anulada** en el registro (D-52), así que `excluidos_del_sujeto` no lo devuelve — y
    una segunda pasada no puede volver a sacarlo."""
    monkeypatch.setattr(qa.cfg, "load_decisiones", lambda slug: {})   # anulada por extra_core
    recs = [{"bibcode": "1994Comon", "relevant": True, "via": "extra_core"}]
    assert qa.aplicar_excluidos(recs, "ica") == []
    assert recs[0]["relevant"] is True


def test_excluidos_del_sujeto_solo_descartes(monkeypatch):
    monkeypatch.setattr(qa.cfg, "load_decisiones", lambda slug: {
        "A": {"decision": "descartado", "origen": "sujeto", "motivo": "m"},
        "B": {"decision": "aceptado", "origen": "sujeto", "motivo": "m"}})
    assert set(qa.excluidos_del_sujeto("ica")) == {"A"}


# ── #86 · un registro SIN abstract se juzga con menos información, y nada lo marca ───────────────

def test_registro_sin_abstract_queda_marcado(toy_classifier):
    """ADS no tiene abstract para buena parte de los escaneos viejos. Para esos papers la lente
    opera sobre **título + keywords** y nada más — una fracción de la información con la que juzga
    a los demás— y el veredicto sale igual de liso que cualquier otro.

    El efecto es un sesgo sistemático contra lo pre-digital, y como los no-core **no se bajan**,
    nunca vuelve a mirarse. Es el espejo exacto de #79, que sesga contra lo reciente.

    @inv INV-110"""
    r = qa.to_record({"bibcode": "1968Old...1..1A", "title": ["Photoelectric observations"],
                      "doctype": "article"})
    assert r["sin_abstract"] is True, "el registro declara que se juzgó sin abstract"

    r2 = qa.to_record({"bibcode": "2020New...1..1A", "title": ["Starspot evolution"],
                       "abstract": "we measure activity", "doctype": "article"})
    assert r2["sin_abstract"] is False


def test_sin_abstract_no_cambia_el_veredicto(toy_classifier):
    """La marca es **información**, no una regla nueva: no mueve el corte core/no-core. Cambiarlo
    haría que ser core dejara de ser función de `(paper, lente)` — INV-24."""
    d = {"bibcode": "1968Old...1..1A", "title": ["Starspot evolution"], "doctype": "article"}
    assert qa.to_record(d)["relevant"] is True


# ── #126 · por qué puerta entró cada paper de un tema de método ──────────────────────────────────

def test_la_puerta_que_admitio_al_paper_queda_registrada(toy_classifier):
    """`classify_theme` computa las dos puertas por separado y, cuando el paper entra, devolvía
    `(facets, True, None)`: **se perdía cuál abrió**. El `motivo` sólo existía para el NO.

    Es la única metadata que distingue, **sin leer el paper**, un fundamento de su campo de una
    aplicación astro — y está disponible ANTES de la extracción, que es cuando hay que decidir qué
    se lee. (`role` no sirve: lo puebla la extracción, o sea después.)

    @inv INV-116"""
    meta = {"facet": "independent component", "fundacional_min_citas": 2000}
    # registros YA persistidos: `title` es string (así los deja `to_record`)
    fund = {"title": "Independent component analysis: algorithms", "citation_count": 9000,
            "doctype": "article"}
    astro = {"title": "Independent component analysis of stellar activity",
             "abstract": "radial velocity", "citation_count": 3, "doctype": "article"}
    assert qa.classify_theme(fund, meta)[1] is True
    assert qa.puertas_abiertas(fund, meta) == ("fundacional",)
    assert qa.puertas_abiertas(astro, meta) == ("astro",)
    ambas = {"title": "Independent component analysis of stellar activity",
             "abstract": "radial velocity", "citation_count": 9000, "doctype": "article"}
    assert qa.puertas_abiertas(ambas, meta) == ("fundacional", "astro")
    fuera = {"title": "something else", "citation_count": 5, "doctype": "article"}
    assert qa.puertas_abiertas(fuera, meta) == ()


def test_la_puerta_viaja_en_el_registro_del_paper(toy_classifier):
    """Guardarla en `to_record` es lo que permite curar por POLÍTICA («sólo fundacionales»,
    «fundacionales + astro») en vez de paper por paper, y auditar después por qué un paper es core.

    @inv INV-116"""
    meta = {"facet": "independent component", "fundacional_min_citas": 2000}
    recs = [qa.to_record({"bibcode": "2000Hyv", "title": ["Independent component analysis"],
                          "citation_count": 9000, "doctype": "article"}),
            qa.to_record({"bibcode": "2020Fuera", "title": ["asteroseismology of red giants"],
                          "citation_count": 5, "doctype": "article"})]
    qa.reclassify_for_theme(recs, meta)
    assert recs[0]["puertas"] == ["fundacional"]
    assert recs[1]["puertas"] == [], "no es core: lista vacía, no ausencia del campo"
    assert "puertas" in recs[1], "el campo existe siempre — «no consta» y «ninguna» no se confunden"


# ── #88 · el barrido full-text deja rastro versionado ────────────────────────────────────────────

def test_el_sweep_queda_en_el_registro(toy_vault, monkeypatch, capsys):
    """#88: `--sweep` era un **preview puro de stdout**. Cuando la terminal scrollea no queda nada.

    Es el mismo modo de falla que #55 arregló para el triage —el aviso vivía sólo en la corrida, y
    un ingest podía cerrarse «en 0» con el juicio pendiente invisible—, y acá pesa más: el barrido
    es **el único camino** para el punto ciego de la query directa (los surveys que TABULAN la
    estrella sin nombrarla en el abstract y que no están en el grafo de citas). Sin registro no se
    sabe si esa segunda red se tendió, ni cuándo, ni qué encontró.

    @inv INV-118"""
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text(json.dumps({"records": [{"bibcode": "2020ya....1..1A"}]}),
                                    encoding="utf-8")
    monkeypatch.setattr(qa, "query_ads", lambda *a, **k: [
        {"bibcode": "2019new...1..1A", "title": "survey que tabula", "doctype": "article",
         "abstract": "we measure radial velocity", "citation_count": 7, "year": "2019",
         "relevant": True, "facets": ["rv"]}])
    qa.sweep_star("test_star", rows=50)
    reg = cfg.load_registro("test_star") or {}
    barridos = cfg.as_list(reg.get("barridos"))
    assert len(barridos) == 1, "una entrada por corrida, acumulativa como `busquedas` (D-28)"
    b = barridos[0]
    assert b["n_nuevos"] == 1 and "2019new...1..1A" in b["bibcodes"]
    assert b["fecha"] and b["almagesto_version"], "fechado y con la versión que lo corrió"


def test_el_sweep_se_estampa_a_si_mismo_en_la_cadena(toy_vault, toy_classifier, no_sleep,
                                                    monkeypatch):
    """#265 — el `return sweep_star(...)` salía **antes** del `save_paso` del final de `main`.

    D-57 dice que **cada script se estampa a sí mismo**, «así que un paso corrido a mano deja rastro
    en vez de leerse como un corte». El barrido era el único del carril que no lo hacía: la traza no
    se perdía del todo —`barridos` la guarda— pero sí en el lugar donde se reconstruye qué corrió y
    cuándo, y el lint no lo caza porque compara contra el orden canónico del orquestador, donde
    `--sweep` no está. Medido en una estrella real: 27 pasos en `cadena`, ninguno con `--sweep`,
    contra 5 entradas en `barridos`."""
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text(json.dumps({"records": [{"bibcode": "2020ya....1..1A"}]}),
                                    encoding="utf-8")
    monkeypatch.setattr(qa, "query_ads", lambda *a, **k: [])
    monkeypatch.setattr(sys, "argv", ["query_ads.py", "test_star", "--sweep"])
    qa.main()
    pasos = [p for p in cfg.as_list((cfg.load_registro("test_star") or {}).get("cadena"))
             if isinstance(p, dict)]
    assert any(p["paso"] == "query_ads" and "--sweep" in p.get("flags", []) for p in pasos), \
        f"el barrido no dejó rastro en `cadena` (D-57): {pasos}"


def test_el_sweep_sin_hallazgos_tambien_deja_rastro(toy_vault, monkeypatch, capsys):
    """Un barrido que no encontró nada **es** información: dice que la red se tendió y volvió vacía.
    Si sólo se registraran los hallazgos, «no se corrió» y «se corrió y no había» se leerían igual —
    la distinción que D-43 protege en todo el framework.  @inv INV-118"""
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text(json.dumps({"records": [{"bibcode": "2020ya....1..1A"}]}),
                                    encoding="utf-8")
    monkeypatch.setattr(qa, "query_ads", lambda *a, **k: [])
    qa.sweep_star("test_star", rows=50)
    b = cfg.as_list((cfg.load_registro("test_star") or {}).get("barridos"))
    assert len(b) == 1 and b[0]["n_nuevos"] == 0 and b[0]["bibcodes"] == []


# ── #251 · el barrido resta las decisiones ya persistidas ────────────────────────────────────────

def _toy_ads_json(bibcodes=("2020ya....1..1A",)):
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text(
        json.dumps({"records": [{"bibcode": b} for b in bibcodes]}), encoding="utf-8")


def _hit(bibcode):
    return {"bibcode": bibcode, "title": "survey que tabula", "doctype": "article",
            "abstract": "we measure radial velocity", "citation_count": 7, "year": "2019",
            "relevant": True, "facets": ["rv"]}


def test_el_sweep_no_repropone_lo_ya_descartado(toy_vault, monkeypatch, capsys):
    """#251: el barrido restaba **sólo** `ads.json`, así que un paper descartado con motivo volvía
    como «core NUEVO» corrida tras corrida — el bug que #51 cerró para el chaining, intacto en el
    carril de al lado, y encima con el propio código mandando el juicio al `log.md`, que no lee
    ningún script.

    Medido en el ingest real de `hd_40307` (2026-08-29): tras persistir 52 descartes con motivo, el
    barrido siguiente devolvió esos **52 de 52** como core nuevos.

    @inv INV-118"""
    _toy_ads_json()
    monkeypatch.setattr(qa, "query_ads",
                        lambda *a, **k: [_hit("2019new...1..1A"), _hit("2019out...1..1A")])
    cfg.save_decisiones("test_star", {"2019out...1..1A": {
        "decision": "descartado", "motivo": "otro sistema es el sujeto", "fecha": "2026-08-29"}})
    qa.sweep_star("test_star", rows=50)
    b = cfg.as_list((cfg.load_registro("test_star") or {}).get("barridos"))[0]
    assert b["bibcodes"] == ["2019new...1..1A"], \
        "el descartado con motivo no vuelve a proponerse"
    assert b["n_descartados_antes"] == 1, \
        "y no desaparece en silencio: se cuenta (D-43 — «no hay nada nuevo» != «no se miró»)"
    assert "1 ya descartados antes" in capsys.readouterr().out


def test_el_sweep_manda_el_descarte_al_registro_y_no_al_log(toy_vault, monkeypatch, capsys):
    """La instrucción decía *«listalos en el log — no curar en silencio»*: mandaba el juicio a un
    artefacto que **ningún script lee**, mientras `decisiones` —que sí se lee— quedaba vacío. Por
    eso el barrido de `hd_40307` cerró con 61 descartes y `decisiones: {}`.  @inv INV-118"""
    _toy_ads_json()
    monkeypatch.setattr(qa, "query_ads", lambda *a, **k: [_hit("2019new...1..1A")])
    qa.sweep_star("test_star", rows=50)
    out = capsys.readouterr().out
    assert "triage.py test_star --drop" in out, "el comando que PERSISTE el descarte, con el slug"
    assert "--reason" in out, "y con el motivo, que es lo que #51 existe para preservar"


def test_el_barrido_distingue_una_corrida_repetida_de_un_hallazgo(toy_vault, monkeypatch, capsys):
    """#251(b): `save_barrido` decía en su docstring «acumulativo como `busquedas` (D-28)» y sólo
    appendeaba — sin el `n_nuevos`/`n_ya_estaban` que **es** D-28. Medido: tres entradas idénticas
    del barrido de `hd_40307`, con los mismos 83 bibcodes, declarando las tres `n_nuevos: 83`.

    @inv INV-118"""
    _toy_ads_json()
    monkeypatch.setattr(qa, "query_ads", lambda *a, **k: [_hit("2019new...1..1A")])
    qa.sweep_star("test_star", rows=50)
    qa.sweep_star("test_star", rows=50)
    b = cfg.as_list((cfg.load_registro("test_star") or {}).get("barridos"))
    assert len(b) == 2, "acumulativo: una entrada por corrida"
    assert (b[0]["n_nuevos"], b[0]["n_ya_estaban"]) == (1, 0)
    assert (b[1]["n_nuevos"], b[1]["n_ya_estaban"]) == (0, 1), \
        "la segunda corrida no descubrió nada: el mismo bibcode ya estaba en la primera"


# ── #85 · la lente del BUSCADOR sale del objetivo, no del código ─────────────────────────────────

def test_el_fq_del_buscador_sale_del_objetivo(toy_vault):
    """#85: `ASTRO_FQ = "database:astronomy"` era constante de módulo. Es el `fq` de Solr de toda
    query de descubrimiento y **acota el universo antes de traer nada**, server-side — o sea que
    recorta más fuerte que `relevance.facets`, que actúa después y sí es configurable.

    Que la mitad más restrictiva del filtro no salga de `objective.yaml` es incoherente con todo el
    resto de la lente, y bloquea el caso que el framework declara soportar: los **métodos de otras
    disciplinas** (estadística, ML) cuya bibliografía canónica no está en `database:astronomy`.

    @inv INV-119"""
    write_yaml(cfg.OBJECTIVE_YAML, {"name": "x", "relevance": {"facets": {"rv": "radial"},
                                                               "search_fq": "database:physics"}})
    assert qa.search_fq() == "database:physics"


def test_sin_declarar_el_fq_sigue_siendo_astro(toy_vault):
    """Compatibilidad de comportamiento, no de schema: una bóveda que no declara nada sigue
    buscando en astronomía, que es el default correcto para el foco de este framework. Lo que
    cambia es que ahora **se puede** declarar otra cosa.  @inv INV-119"""
    write_yaml(cfg.OBJECTIVE_YAML, {"name": "x", "relevance": {"facets": {"rv": "radial"}}})
    assert qa.search_fq() == "database:astronomy"


def test_fq_nulo_explicito_no_acota_nada(toy_vault):
    """`search_fq: null` declarado es una DECISIÓN —buscar en todo ADS— y no puede leerse igual que
    no declararlo (que deja el default astro). Misma distinción que D-26 protege con
    `fundacional_min_citas`.  @inv INV-119"""
    write_yaml(cfg.OBJECTIVE_YAML, {"name": "x",
                                    "relevance": {"facets": {"rv": "radial"}, "search_fq": None}})
    assert qa.search_fq() is None


# ── #83 · minar el `--probe`: qué faceta le falta a la lente ─────────────────────────────────────

def test_el_probe_propone_facetas_desde_los_no_core(toy_classifier):
    """#83: el skill `setup` sólo **pregunta** y traduce lo que el usuario supo nombrar. El agente,
    en cambio, tiene el corpus delante — y no lo mira.

    La señal existe y es determinista: entre los **no-core**, los términos que se repiten y que
    **ninguna faceta matchea**. Y no son términos inventados: son las `keywords` que el propio ADS
    devuelve (D-17), el único vocabulario de la bóveda que no sale de una regex nuestra ni de la
    memoria de un LLM.

    ⛔ Es una PROPUESTA, no una edición: cuáles entran a `relevance.facets` lo decide el usuario.

    @inv INV-124"""
    recs = [
        {"bibcode": f"2020a{i}", "relevant": False, "facets": [],
         "keyword": ["asteroseismology", "stellar oscillations"]} for i in range(4)
    ] + [
        {"bibcode": "2020b1", "relevant": False, "facets": [], "keyword": ["debris disk"]},
        {"bibcode": "2020c1", "relevant": True, "facets": ["rv"], "keyword": ["radial velocity"]},
    ]
    prop = qa.propose_facets(recs, min_n=3)
    assert prop and prop[0][0] == "asteroseismology" and prop[0][1] == 4
    assert all(t != "debris disk" for t, _ in prop), "1 sola aparición no es un agrupamiento"
    assert all("radial velocity" != t for t, _ in prop), "lo que ya es core no se propone"


def test_no_propone_lo_que_una_faceta_ya_cubre(toy_classifier):
    """Contra-caso: un término frecuente entre los no-core que **sí** matchea una faceta existente
    no es una faceta faltante — es un paper que quedó afuera por otra razón (doctype, `require`,
    `min_facets`). Proponerlo mandaría a agregar lo que ya está.  @inv INV-124"""
    recs = [{"bibcode": f"2020d{i}", "relevant": False, "facets": ["rv"],
             "keyword": ["radial velocity"]} for i in range(5)]
    assert qa.propose_facets(recs, min_n=3) == []


def test_puertas_existe_SIEMPRE_en_el_registro(toy_vault):
    """Issue #179 — `CLAUDE.md:520` (#126) promete: *"Lista vacía = no es core; **el campo existe
    siempre**, así que «no consta» y «ninguna puerta» no se confunden"*. `to_record` —que el propio
    módulo declara el schema canónico— no lo definía, y `reclassify_for_theme` es no-op para un tema
    sin `facet:` y hace `continue` sobre los `via: manual`.

    La distinción se caía justo donde importa: los `extra_core` de un tema de método **son core** y
    quedaban bajo *"(sin puerta registrada)"* en `triage --prioridad`, indistinguibles de «nadie
    miró». Y es la única metadata que separa, sin leer el paper, un fundamento de su campo de una
    aplicación astro."""
    rec = qa.to_record({"bibcode": "2020X", "title": ["T"], "abstract": "", "doctype": "article"})
    assert "puertas" in rec, "el campo existe siempre (#126)"
    assert rec["puertas"] == [], "vacío = no entró por ninguna puerta, distinto de «no consta»"


def test_un_extra_core_de_tema_declara_por_que_puerta_entro(toy_vault):
    """La otra mitad de #179: un `via: manual` es core **por decisión del usuario**, y eso también
    es una procedencia. `reclassify_for_theme` lo salteaba con `continue`, así que el paper que el
    usuario metió a mano quedaba sin `puertas` — el caso más frecuente en un tema de método."""
    meta = {"title": "ICA", "facet": "independent component", "fundacional_min_citas": 1000}
    recs = [{"bibcode": "2020M", "title": "Independent component analysis", "abstract": "",
             "via": "manual", "relevant": True, "citation_count": 5, "keyword": []}]
    qa.reclassify_for_theme(recs, meta)
    assert "puertas" in recs[0], "el campo existe también para el aceptado a mano"
    assert recs[0]["puertas"] == ["manual"], "y dice que entró porque alguien lo pidió"


def test_el_sweep_dicta_un_snippet_que_el_framework_ACEPTA(toy_vault, capsys, monkeypatch):
    """Issue #161 — el texto que `--sweep` imprimía al terminar mandaba a escribir
    `extra_core: [<bibcode>, …]` con `via: manual`, y **las dos mitades abortan**: D-58 rechaza el
    escalar y la lista de strings, y `manual` no está en `EXTRA_CORE_VIA`.

    El usuario copia lo que el script le dicta y la siguiente corrida de la cadena muere.
    `triage.py` ya imprimía el snippet canónico: la asimetría era sólo de este carril. Acá se fija
    que lo impreso **parsea con el loader real**, no que contenga tal o cual frase."""
    import yaml
    recs = [{"bibcode": "2020ApJ...900....1X", "title": "T", "year": 2020, "citation_count": 5,
             "abstract": "", "facets": [], "relevant": False}]
    monkeypatch.setattr(qa, "sweep_records", lambda *a, **k: recs, raising=False)
    texto = qa.extra_core_snippet(recs)
    bloque = yaml.safe_load(texto)
    assert isinstance(bloque, dict) and isinstance(bloque["extra_core"], list)
    entradas = qa.cfg.load_extra_core(bloque, entry="sweep")
    assert entradas and entradas[0]["bibcode"] == "2020ApJ...900....1X"
    assert entradas[0]["via"] in qa.cfg.EXTRA_CORE_VIA


def test_search_fq_con_forma_invalida_falla_ruidoso(toy_vault, monkeypatch):
    """AUD-182 / INV-119 — `str(v)` sobre una lista manda el **repr de Python** a Solr
    (`['a', 'b']`), que no es una query.

    ADS devuelve otra cosa (o nada) y el corpus queda filtrado por un `fq` que nadie escribió, con
    el registro guardando ese repr como la lente vigente. La forma se valida como el resto de la
    config: falla ruidoso."""
    monkeypatch.setattr(qa.cfg, "load_objective",
                        lambda: {"relevance": {"search_fq": ["database:astronomy", "x"]}})
    with pytest.raises(RuntimeError, match="search_fq tiene que ser un string"):
        qa.search_fq()
    monkeypatch.setattr(qa.cfg, "load_objective",
                        lambda: {"relevance": {"search_fq": "database:astronomy"}})
    assert qa.search_fq() == "database:astronomy"
    monkeypatch.setattr(qa.cfg, "load_objective", lambda: {"relevance": {"search_fq": None}})
    assert qa.search_fq() is None            # `null` declarado: no acotar, a propósito (#85)


# ── #208 · --probe con la lente del TEMA ─────────────────────────────────────

def _recs_ica():
    """El caso medido en la ingesta real de `ica`: la lente global invierte el veredicto.

    El paper de separación de componentes NO matchea `rv` (la faceta global), y la binaria
    eclipsante SÍ — así que el `--probe` viejo imprimía la binaria como CORE y mandaba los papers
    del tema al no-core."""
    return [
        {"bibcode": "2012MNRAS.423.2518C", "doctype": "article", "citation_count": 193,
         "title": "Foreground removal using FASTICA: LOFAR", "abstract": "independent component",
         "keyword": [], "facets": [], "relevant": False},
        {"bibcode": "2020ecl..conf....1X", "doctype": "article", "citation_count": 4,
         "title": "Radial velocity survey of eclipsing binaries", "abstract": "radial velocity",
         "keyword": [], "facets": ["rv"], "relevant": True},
    ]


def test_probe_con_lente_del_tema_invierte_el_corte(toy_classifier, capsys):
    """#208 — `print_probe` leía `r["relevant"]` (lente GLOBAL) y nunca pasaba por
    `classify_theme`. Para un tema de método eso no es «menos preciso»: es el veredicto OPUESTO,
    sobre exactamente la población que el tema existe para capturar."""
    meta = {"title": "ICA", "facet": "independent component", "query": "abs:x",
            "fundacional_min_citas": 100}
    recs = _recs_ica()
    assert qa.print_probe("q", recs, theme_meta=meta) == 0
    out = capsys.readouterr().out
    assert "[CORE]" in out
    linea_ica = next(l for l in out.splitlines() if "2012MNRAS.423.2518C" in l)
    linea_bin = next(l for l in out.splitlines() if "2020ecl..conf....1X" in l)
    assert "[CORE]" in linea_ica          # entra por la faceta propia del tema
    assert "[CORE]" not in linea_bin      # la binaria sale, aunque matchee `rv`


def test_probe_del_tema_muestra_por_que_puerta_entro(toy_classifier, capsys):
    """#208 punto 2 — la puerta (#126) es la única metadata que distingue, sin leer el paper, un
    fundamento de su campo de una aplicación astro. Ningún preview la mostraba."""
    meta = {"title": "ICA", "facet": "independent component", "fundacional_min_citas": 100}
    qa.print_probe("q", _recs_ica(), theme_meta=meta)
    out = capsys.readouterr().out
    assert "por qué puerta entró cada core" in out
    # la fila del desglose, no la coletilla de la línea de cierre (que nombra las dos puertas
    # siempre): sin la reclasificación el core es la binaria y el desglose diría «(ninguna …)»
    assert any(l.strip() == "1  fundacional" for l in out.splitlines()), out
    linea_ica = next(l for l in out.splitlines() if "2012MNRAS.423.2518C" in l)
    assert "[fundacional]" in linea_ica          # y la puerta va en la fila del paper


def test_probe_del_tema_manda_a_themes_yaml(toy_classifier, capsys):
    """#208 punto 3 — la línea de cierre mandaba a `objective.yaml`, que no es el archivo que
    decide este corte: para un tema son `facet:` / `fundacional_min_citas` de themes.yaml."""
    meta = {"title": "ICA", "facet": "independent component"}
    qa.print_probe("q", _recs_ica(), theme_meta=meta)
    out = capsys.readouterr().out
    assert "themes.yaml" in out
    assert "ajustá relevance.facets en objective.yaml" not in out


def test_probe_sin_tema_no_cambia(toy_classifier, capsys):
    """#208 punto 4 — sin `--theme`, comportamiento histórico intacto."""
    qa.print_probe("q", _recs_ica())
    out = capsys.readouterr().out
    assert "ajustá relevance.facets en objective.yaml" in out
    assert "por qué puerta entró" not in out


def test_probe_theme_sin_slug_rehusa(toy_vault, monkeypatch, capsys):
    """#208 — `--probe --theme` sin slug NO degrada a la lente global: rehúsa y lo dice (D-43).
    Degradar sería un preview que dice una cosa y un ingest que hace otra."""
    monkeypatch.setattr(sys, "argv", ["query_ads.py", "--theme", "--probe", "abs:x"])
    with pytest.raises(SystemExit):
        qa.main()
    assert "necesita el slug del tema" in capsys.readouterr().err


def test_probe_theme_slug_inexistente_rehusa(toy_vault, monkeypatch, capsys):
    """#208 — ídem si el slug no está en themes.yaml."""
    write_yaml(cfg.THEMES_YAML, {"otro": {"title": "Otro", "facet": "x"}})
    monkeypatch.setattr(sys, "argv", ["query_ads.py", "ica", "--theme", "--probe", "abs:x"])
    with pytest.raises(SystemExit, match="no tiene la entrada"):
        qa.main()


def test_probe_theme_sin_facet_rehusa(toy_vault, monkeypatch):
    """#208 — un tema sin `facet:` no tiene lente propia: rehusar, no caer a la global."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "query": "abs:x"}})
    monkeypatch.setattr(sys, "argv", ["query_ads.py", "ica", "--theme", "--probe"])
    with pytest.raises(SystemExit, match="facet"):
        qa.main()


def test_probe_theme_toma_la_query_del_tema(toy_vault, monkeypatch, capsys):
    """#208 — con `--theme` la QUERY se puede omitir: sale de `query:` de themes.yaml, que es
    donde ya está declarada (copiarla a mano en cada corrida es cómo el preview y el ingest
    terminan mirando queries distintas)."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "facet": "independent component",
                                         "query": 'abs:"independent component"'}})
    vistas = {}
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, **k: vistas.setdefault("q", q) and [] or [])
    monkeypatch.setattr(sys, "argv", ["query_ads.py", "ica", "--theme", "--probe"])
    assert qa.main() == 0
    assert vistas["q"] == 'abs:"independent component"'


def test_probe_del_tema_no_propone_facetas_globales(toy_classifier, capsys):
    """#208 — `propose_facets` propone facetas para `objective.yaml`, o sea el archivo que NO
    decide el corte de un tema. Mostrarlas en modo tema manda a editar el archivo equivocado, que
    es exactamente el defecto que este issue arregla en la línea de cierre."""
    meta = {"title": "ICA", "facet": "independent component", "fundacional_min_citas": 100}
    recs = _recs_ica() + [{"bibcode": f"2020x{i}", "doctype": "article", "citation_count": 1,
                           "title": "sismo", "abstract": "", "keyword": ["asteroseismology"],
                           "facets": [], "relevant": False} for i in range(4)]
    qa.print_probe("q", recs, theme_meta=meta)
    assert "¿FALTA UNA FACETA?" not in capsys.readouterr().out
    qa.print_probe("q", recs)                                   # sin tema sí la propone
    assert "¿FALTA UNA FACETA?" in capsys.readouterr().out


def test_desglose_de_puertas_con_cero_core_lo_dice(capsys):
    """#208 — 0 core no es «el desglose está vacío»: es que ninguna puerta abrió, y el archivo a
    revisar es `facet:` del tema. Sin la rama, el preview imprimía un encabezado y nada debajo."""
    qa.print_gate_breakdown([])
    assert "ninguna puerta abrió" in capsys.readouterr().out


def test_probe_de_una_ESTRELLA_deriva_la_query_de_stars_yaml(toy_vault, monkeypatch, capsys):
    """#248 — para un TEMA `--probe` deriva la query de `themes.yaml` (#208) y para una ESTRELLA no
    derivaba nada, aunque la maquinaria es la misma que el ingest usa (`build_query`). El preview es
    el ÚNICO lugar donde el corte core/no-core se decide antes de pagar descargas, así que tipear la
    query a mano lo vuelve un preview de OTRO universo: la del ingest expande las variantes de
    espaciado (`HD 40307` ↔ `HD40307`), que es justo la parte que un humano no tipea."""
    write_yaml(cfg.STARS_YAML, {"HD 40307": {"slug": "hd_40307", "ads_object": "HD 40307",
                                             "aliases": ["HD 40307", "GJ 2046"]}})
    vistas = {}
    monkeypatch.setattr(qa, "query_ads", lambda q, rows=2000, **k: vistas.setdefault("q", q) or [])
    monkeypatch.setattr(qa, "print_probe", lambda q, recs, theme_meta=None: 0)
    monkeypatch.setattr(sys, "argv", ["query_ads.py", "hd_40307", "--probe"])
    assert qa.main() == 0
    q = vistas["q"]
    assert 'title:"HD 40307"' in q and 'abs:"GJ 2046"' in q
    assert 'title:"HD40307"' in q, "la variante SIN espacio es la mitad que un humano no tipea"


# ── #289 · el probe de un tema dice POR QUÉ quedó afuera cada no-core ────────
def test_probe_del_tema_desglosa_el_no_core_por_motivo(toy_classifier, capsys):
    """#289 — medido sobre un tema real: **261** no-core sin la faceta propia contra **32** que
    pasan la faceta y mueren en la puerta. Las dos poblaciones piden lo contrario —apretar la
    faceta / abrir la puerta o declarar `extra_core`— y la pantalla las mostraba idénticas, con la
    línea de cierre mandando a tocar una de las dos cosas sin decir cuál. El dato ya estaba
    calculado y pegado al registro (`why_excluded`): el printer no lo leía."""
    meta = {"title": "ICA", "facet": "independent component"}
    recs = [
        # pasa la faceta propia, pero la lente astro no lo trae y la puerta 2 está apagada
        rec("2012PASP..124.1015B", relevant=False, cites=90,
            title="Principal Component Analysis with Noisy Data",
            abstract="independent component analysis of noisy data"),
        # ni siquiera pasa la faceta del tema
        rec("2020otroA....1A", relevant=False, cites=5, title="Eclipsing binaries",
            abstract="radial velocity of eclipsing binaries"),
    ]
    qa.print_probe("q", recs, theme_meta=meta)
    out = capsys.readouterr().out
    assert "por qué quedó afuera cada no-core" in out
    assert "sin la faceta propia del tema" in out
    assert "pasan la faceta, ninguna puerta abre" in out
    # y el bloque que más rinde: la lista de la que sale `extra_core`
    assert "no-core que PASAN la faceta" in out
    assert "2012PASP..124.1015B" in out.split("no-core que PASAN la faceta")[1]


def test_el_desglose_del_no_core_es_SOLO_del_modo_tema(toy_classifier, capsys):
    """En modo global el diagnóstico del no-core es `propose_facets` (#83). El desglose por puerta
    habla de D-26, que en una bóveda global no rige: mostrarlo mandaría a tocar `themes.yaml` por
    un corte que decide `objective.yaml`."""
    qa.print_probe("q", [rec("2020noA....1A", relevant=False)])
    assert "por qué quedó afuera cada no-core" not in capsys.readouterr().out


def test_clase_noncore_no_inventa_un_motivo(toy_classifier):
    """D-43 — un registro sin `why_excluded` no se clasifica en ninguna de las dos poblaciones: se
    declara «no consta». Meterlo en cualquiera de las dos manda a tocar la perilla equivocada."""
    assert qa._clase_noncore(None) == "sin motivo registrado (no consta)"
    assert qa._clase_noncore("sin la faceta propia del tema") == "sin la faceta propia del tema"
    assert qa._clase_noncore("doctype: abstract") == "doctype de ruido"
    assert qa._clase_noncore("ninguna puerta abre; la 2 (fundacional) está apagada porque el tema "
                             "no declara `fundacional_min_citas`") == "pasan la faceta, ninguna puerta abre"
    assert qa._clase_noncore("excluido del sujeto por decisión: off-topic") == \
        "excluido por decisión (#112)"
    # el no evaluable NO se cuenta como «la puerta lo rechazó»: no se sabe (D-43)
    assert qa._clase_noncore("ninguna puerta abre; la 2 (fundacional) NO se pudo evaluar: umbral "
                             "mal formado") == "pasan la faceta; la puerta 2 NO se pudo evaluar"
    assert qa._clase_noncore("la lente astro no lo trae y la puerta 2 (fundacional) **no se pudo "
                             "evaluar**: el registro viene sin dato de citas") == \
        "pasan la faceta; la puerta 2 NO se pudo evaluar"


def test_el_desglose_calla_si_no_hay_no_core(toy_classifier, capsys):
    """Con 0 no-core no hay nada que desglosar, y un encabezado con la tabla vacía debajo se lee
    como si el desglose hubiera fallado."""
    qa.print_noncore_breakdown([])
    assert capsys.readouterr().out == ""


# ── #295 · el `fq` del tema: la mitad más restrictiva, al nivel de D-26 ──────
def test_search_fq_del_tema_pisa_al_del_objetivo(toy_vault, monkeypatch):
    """#295 — D-26 hizo propia la lente del tema y dejó GLOBAL la mitad **más restrictiva**. En una
    bóveda astro, un tema de signal processing se buscaba sobre un universo que excluye su
    literatura por construcción, y ninguna `facet:` propia puede recuperarla: la faceta clasifica
    lo ya traído. Medido: 306 resultados con `database:astronomy` contra 6946 sin él, y
    `title:"noisy ICA"` —el término que da nombre al tema— devolviendo CERO bajo el fq."""
    monkeypatch.setattr(qa.cfg, "load_objective",
                        lambda: {"relevance": {"search_fq": "database:astronomy"}})
    assert qa.search_fq() == "database:astronomy"
    assert qa.search_fq({"title": "ICA"}) == "database:astronomy", "sin declarar: hereda"
    assert qa.search_fq({"search_fq": "database:astronomy OR database:physics"}) == \
        "database:astronomy OR database:physics"
    # `null` DECLARADO en el tema: no acotar, a propósito — distinto de no declararlo
    assert qa.search_fq({"search_fq": None}) is None
    assert qa.search_fq({"search_fq": ""}) is None, "el YAML vacío es el mismo `null` declarado"


def test_search_fq_del_tema_valida_la_forma(toy_vault, monkeypatch):
    """AUD-182 vale igual en el nivel nuevo: una lista se manda como su `repr` de Python y filtra el
    corpus con una regla que nadie escribió. El mensaje nombra el archivo del tema, no el objetivo."""
    monkeypatch.setattr(qa.cfg, "load_objective", lambda: {"relevance": {}})
    with pytest.raises(RuntimeError, match="themes.yaml"):
        qa.search_fq({"search_fq": ["database:astronomy", "x"]})


def test_la_corrida_del_tema_usa_y_REGISTRA_su_propio_fq(toy_vault, toy_classifier, no_sleep,
                                                         monkeypatch):
    """Las dos mitades de #295: el `fq` resuelto viaja a la búsqueda **y** al registro. Si el
    registro guardara el global, volvería a mentir sobre la corrida — que es justo lo que #238
    arregló para el caso en que el `fq` no se registraba en absoluto."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods",
                                         "facet": "independent component",
                                         "search_fq": "database:astronomy OR database:physics",
                                         "query": 'abs:"independent component"'}})
    monkeypatch.setattr(qa.cfg, "load_objective",
                        lambda: {"relevance": {"search_fq": "database:astronomy"}})
    vistos = []

    def fake_qa(q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k):
        vistos.append(k.get("fq"))
        return [rec("2020icaA....1A", abstract="independent component analysis")]
    monkeypatch.setattr(qa, "query_ads", fake_qa)
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    assert run_main(monkeypatch, ["ica", "--theme"]) == 0
    assert vistos and all(f == "database:astronomy OR database:physics" for f in vistos)
    bs = cfg.load_busquedas("ica")
    assert bs[-1]["fq"] == "database:astronomy OR database:physics"


def test_el_fq_del_tema_entra_en_la_lente_guardada(toy_vault, monkeypatch):
    """Consecuencia 2 de #295: cambiar el `fq` de un tema **re-clasifica su universo**, igual que
    cambiar la faceta, así que tiene que estar en la lente que el registro guarda o el detector de
    lente desincronizada no puede verlo."""
    monkeypatch.setattr(qa.cfg, "load_objective", lambda: {"relevance": {}})
    con = qa.lens_used({"facet": "ica", "search_fq": "database:physics"})
    assert con["regla_tema"]["search_fq"] == "database:physics"
    sin = qa.lens_used({"facet": "ica"})
    assert "search_fq" not in sin["regla_tema"], "no declararlo NO es un cambio de lente"
    assert cfg.lens_delta(sin, con) == ["`search_fq` del tema sin declarar (hereda el objetivo) → "
                                        "database:physics"]
    # `null` declarado es una decisión, y no se lee igual que no declarar nada
    nulo = qa.lens_used({"facet": "ica", "search_fq": None})
    assert cfg.lens_delta(sin, nulo) == ["`search_fq` del tema sin declarar (hereda el objetivo) → "
                                         "null (no acota)"]


# ── #303 · la guarda de #179 nunca corría para `extra_core` ──────────────────
def test_los_curados_quedan_CON_PUERTA_registrada(toy_vault, toy_classifier, no_sleep, monkeypatch):
    """#303 — la guarda de #179 existía para que un paper aceptado a mano no quedara sin `puertas`
    («indistinguible de nadie miró»), y **nunca corría** para `extra_core`: `reclassify_for_theme`
    se ejecuta sobre la query directa y el merge ocurre ~40 líneas después. Medido sobre un tema
    real: 12 de 15 core con `puertas: []`, y `triage.py --prioridad` pidiendo elegir una política
    sobre un corpus donde el 80 % no tiene política registrada.

    Las DOS ramas del merge dejan la misma marca: la rescatada del corte (el bibcode que la query
    devolvió no-core) y la traída por bibcode. Cuál de las dos toca no lo decide nadie: lo decide
    si ADS devolvió ese bibcode."""
    write_yaml(cfg.THEMES_YAML, {"ica": {
        "title": "ICA", "concept": "ica", "area": "methods", "facet": "independent component",
        "query": 'abs:"independent component"',
        "extra_core": [{"bibcode": "2012PASP..124.1015B", "via": "usuario", "motivo": "blanqueo"},
                       {"bibcode": "2015MNRAS.446.3545D", "via": "usuario", "motivo": "weighted PCA"}]}})
    # el primero lo devuelve la query (no-core: no matchea la faceta del tema) → rama RESCATADA;
    # el segundo no lo devuelve → rama traída por bibcode.
    monkeypatch.setattr(qa, "query_ads",
                        lambda q, rows=2000, quiet_truncate=False, meta=None, expect_hits=False, **k:
                        [rec("2012PASP..124.1015B", relevant=False, title="PCA with noisy data"),
                         rec("2020icaA....1A", abstract="independent component analysis")])
    monkeypatch.setattr(qa, "fetch_bibcodes",
                        lambda bibs, via_de=None: [dict(rec("2015MNRAS.446.3545D", relevant=True),
                                                        via=(via_de or {}).get("2015MNRAS.446.3545D"),
                                                        puertas=["manual"])])
    monkeypatch.setattr(qa, "chain_candidates", lambda *a, **k: [])
    assert run_main(monkeypatch, ["ica", "--theme"]) == 0
    data = json.loads((toy_vault.ROOT / "build" / "ica" / "ads.json").read_text())
    por_bib = {r["bibcode"]: r for r in data["records"]}
    for b in ("2012PASP..124.1015B", "2015MNRAS.446.3545D"):
        assert por_bib[b]["relevant"] is True
        assert "manual" in (por_bib[b].get("puertas") or []), f"{b} quedó sin puerta registrada"
        assert por_bib[b]["via"] == "usuario", "un solo `via` por decisión, el declarado"
    assert set(por_bib["2020icaA....1A"]["puertas"]) <= set(qa.PUERTAS)


def test_la_regla_del_tema_no_re_juzga_un_curado(toy_classifier):
    """El predicado es «está en `extra_core`», no el string `via`: la mitad rescatada del corte
    lleva el `via` de la config, así que testear `via == "manual"` la dejaba afuera de la guarda."""
    meta = {"title": "ICA", "facet": "independent component"}
    recs = [rec("2012PASP..124.1015B", relevant=True, via="usuario", title="PCA noisy")]
    entraron, salieron = qa.reclassify_for_theme(recs, meta, curados={"2012PASP..124.1015B"})
    assert (entraron, salieron) == ([], []), "la curación pisa al clasificador (#39/#68)"
    assert recs[0]["relevant"] is True and recs[0]["puertas"] == ["manual"]
    # sin declararlo curado, la regla del tema SÍ lo saca: es el control del test de arriba
    otro = [rec("2012PASP..124.1015B", relevant=True, via="usuario", title="PCA noisy")]
    assert qa.reclassify_for_theme(otro, meta)[1] == ["2012PASP..124.1015B"]
