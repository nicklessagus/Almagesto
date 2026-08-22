"""lib_config: token ADS, loaders de config, áreas de concepts (declarado vs tolerante)."""
from pathlib import Path
import pytest

import lib_config as cfg
from conftest import write_yaml


# ── token ADS ────────────────────────────────────────────────────────────────

def test_token_env_gana(toy_vault, monkeypatch):
    monkeypatch.setenv("ADS_DEV_KEY", "  tok-env  ")
    toy_vault.ADS_KEY_FILE.write_text("tok-file\n")
    assert cfg.get_ads_token() == "tok-env"


def test_token_desde_archivo(toy_vault, monkeypatch):
    monkeypatch.delenv("ADS_DEV_KEY", raising=False)
    toy_vault.ADS_KEY_FILE.write_text("tok-file\n")
    assert cfg.get_ads_token() == "tok-file"


def test_token_faltante(toy_vault, monkeypatch):
    monkeypatch.delenv("ADS_DEV_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ADS_DEV_KEY"):
        cfg.get_ads_token()


# ── stars / topics ───────────────────────────────────────────────────────────

def test_load_stars_y_slug(toy_vault):
    stars = cfg.load_stars()
    assert "Estrella Test" in stars
    name, meta = cfg.star_by_slug("test_star")
    assert name == "Estrella Test"
    assert meta["ads_object"] == "Test Star"


def test_star_by_slug_desconocido(toy_vault):
    with pytest.raises(KeyError, match="stars.yaml"):
        cfg.star_by_slug("nope")


def test_star_by_slug_yaml_vacio(toy_vault):
    """Regresión (#26): stars.yaml vacío (instancia recién creada) parsea a None — el KeyError
    amigable, no un AttributeError sobre None.items()."""
    toy_vault.STARS_YAML.write_text("# sólo comentarios\n", encoding="utf-8")
    assert cfg.load_stars() == {}
    with pytest.raises(KeyError, match="stars.yaml"):
        cfg.star_by_slug("nope")


def test_load_topics_sin_archivo(toy_vault):
    toy_vault.TOPICS_YAML.unlink()
    assert cfg.load_topics() == {}


def test_load_topics_vacio(toy_vault):
    toy_vault.TOPICS_YAML.write_text("")
    assert cfg.load_topics() == {}


def test_topic_by_slug(toy_vault):
    write_yaml(toy_vault.TOPICS_YAML, {"gp": {"title": "Gaussian processes", "area": "methods", "concept": "gp"}})
    slug, meta = cfg.topic_by_slug("gp")
    assert slug == "gp" and meta["concept"] == "gp"
    with pytest.raises(KeyError, match="topics.yaml"):
        cfg.topic_by_slug("nope")


# ── objective / concept_areas ────────────────────────────────────────────────

def test_load_objective_faltante(toy_vault):
    toy_vault.OBJECTIVE_YAML.unlink()
    with pytest.raises(RuntimeError, match="objective.yaml"):
        cfg.load_objective()


def test_concept_areas_declaradas_mas_reservadas(toy_vault):
    areas = cfg.load_concept_areas()
    # declaradas en orden + reservadas sin duplicar (methods/hypotheses ya declaradas)
    assert areas == ["indicators", "methods", "activity", "hypotheses"]


def test_concept_areas_reservadas_se_agregan(toy_vault):
    obj = dict(cfg.load_objective())
    obj["concept_areas"] = ["indicators"]
    write_yaml(toy_vault.OBJECTIVE_YAML, obj)
    assert cfg.load_concept_areas() == ["indicators", "methods", "hypotheses"]


def test_concept_areas_modo_tolerante(toy_vault):
    """Sin `concept_areas` declarado: carpetas existentes + reservadas (instancia vieja)."""
    obj = dict(cfg.load_objective())
    obj.pop("concept_areas")
    write_yaml(toy_vault.OBJECTIVE_YAML, obj)
    (toy_vault.CONCEPTS / "zzz").mkdir()
    (toy_vault.CONCEPTS / "activity").mkdir()
    assert cfg.load_concept_areas() == ["activity", "zzz", "methods", "hypotheses"]


def test_version_unica_fuente():
    """ALMAGESTO_VERSION es la ÚNGaussian processes fuente de versión: los UA de los fetchers derivan de la
    constante, y ningún script hardcodea 'Almagesto/x.y' (el drift que tenían los UA en 0.1)."""
    import re

    import check_retractions
    import fetch_arxiv
    import fetch_pdf
    from conftest import SCRIPTS
    v = cfg.ALMAGESTO_VERSION
    assert f"Almagesto/{v}" in fetch_arxiv.HEADERS["User-Agent"]
    assert f"Almagesto/{v}" in fetch_pdf.UA["User-Agent"]
    assert f"Almagesto/{v}" in check_retractions._ua()["User-Agent"]
    for p in sorted(SCRIPTS.glob("*.py")):
        for m in re.finditer(r"Almagesto/\d[\w.]*", p.read_text(encoding="utf-8")):
            raise AssertionError(
                f"{p.name}: versión hardcodeada {m.group()!r} — interpolá cfg.ALMAGESTO_VERSION")


def test_require_field(toy_vault):
    """Guard de config: campo obligatorio faltante → salida amigable, no KeyError crudo."""
    meta = {"slug": "x", "ads_object": "Test Star", "vacio": ""}
    assert cfg.require_field(meta, "ads_object", "Estrella Test", "stars.yaml") == "Test Star"
    with pytest.raises(SystemExit, match=r"'Estrella Test' no tiene `simbad` en vault/config/stars.yaml"):
        cfg.require_field(meta, "simbad", "Estrella Test", "stars.yaml")
    with pytest.raises(SystemExit):
        cfg.require_field(meta, "vacio", "Estrella Test", "stars.yaml")   # vacío = faltante
    with pytest.raises(SystemExit, match="usá ingest_topic"):
        cfg.require_field(meta, "query", "gp", "topics.yaml", hint="usá ingest_topic.")


def test_concept_areas_sin_nada(toy_vault):
    obj = dict(cfg.load_objective())
    obj.pop("concept_areas")
    write_yaml(toy_vault.OBJECTIVE_YAML, obj)
    assert cfg.load_concept_areas() == ["methods", "hypotheses"]


# ── orden por citas/año (política única de #79) ──────────────────────────────

def test_citation_rate_descuenta_la_edad():
    """La cuenta cruda premia al viejo por haber tenido más tiempo; la tasa lo normaliza. La edad
    cuenta el año de publicación (un paper de este año vale 1 año, no una fracción), así que la
    tasa no explota para lo recién salido — el sesgo simétrico que la corrección podría introducir."""
    viejo = {"bibcode": "1995A", "citation_count": 500, "year": 1995}
    nuevo = {"bibcode": "2026B", "citation_count": 12, "year": 2026}
    assert cfg.citation_rate(viejo, now_year=2026) == 500 / 32
    assert cfg.citation_rate(nuevo, now_year=2026) == 12.0        # edad 1, no 1/12 de año
    assert cfg.citation_rate({"citation_count": 0, "year": 2020}, now_year=2026) == 0.0


@pytest.mark.parametrize("year", [None, "", "in press", 2030])
def test_citation_rate_ano_inusable_vale_edad_1(year):
    """Sin año utilizable (o con fecha futura: in-press) no se inventa una tasa ni se manda al
    fondo — se lo trata como del año en curso."""
    assert cfg.citation_rate({"citation_count": 7, "year": year}, now_year=2026) == 7.0


def test_citation_rate_tolera_campos_ausentes_o_nulos():
    """ADS devuelve `citation_count: null` para papers sin citas registradas."""
    assert cfg.citation_rate({}, now_year=2026) == 0.0
    assert cfg.citation_rate({"citation_count": None, "year": None}, now_year=2026) == 0.0


def test_sort_by_citation_rate_ordena_y_desempata_determinista():
    """Orden descendente por tasa; ante empate, la cuenta cruda y después el bibcode — dos corridas
    sobre el mismo ads.json tienen que imprimir lo mismo (los listados se comparan a ojo)."""
    recs = [{"bibcode": "D", "citation_count": 0, "year": 2020},
            {"bibcode": "A", "citation_count": 500, "year": 1995},    # 15.6/año
            {"bibcode": "C", "citation_count": 30, "year": 2024},     # 10/año
            {"bibcode": "B", "citation_count": 12, "year": 2026}]     # 12/año
    assert [r["bibcode"] for r in cfg.sort_by_citation_rate(recs, 2026)] == ["A", "B", "C", "D"]
    empate = [{"bibcode": "Z", "citation_count": 10, "year": 2026},
              {"bibcode": "Y", "citation_count": 10, "year": 2026},
              {"bibcode": "X", "citation_count": 20, "year": 2025}]   # misma tasa, más citas
    assert [r["bibcode"] for r in cfg.sort_by_citation_rate(empate, 2026)] == ["X", "Y", "Z"]


def test_sort_by_citation_rate_no_muta_ni_exige_lista():
    """Devuelve una lista nueva (los callers pasan generadores y siguen usando el original)."""
    recs = [{"bibcode": "B", "citation_count": 1, "year": 2026},
            {"bibcode": "A", "citation_count": 9, "year": 2026}]
    out = cfg.sort_by_citation_rate(r for r in recs)
    assert [r["bibcode"] for r in out] == ["A", "B"]
    assert [r["bibcode"] for r in recs] == ["B", "A"]      # el original intacto


def test_citation_rate_usa_el_ano_en_curso_por_default():
    """Sin `now_year` toma el año de hoy: un paper del año en curso nunca da edad 0 (ZeroDivision)."""
    import datetime as dt
    assert cfg.citation_rate({"citation_count": 5, "year": dt.date.today().year}) == 5.0


def test_toda_ruta_del_vault_esta_aislada_en_el_fixture(toy_vault):
    """Invariante del harness: TODA constante de ruta que cuelgue de VAULT tiene que estar
    monkeypatcheada por el fixture. Si se agrega una nueva (pasó con REGISTRO, #51) y no se declara
    en conftest, los tests que escriben por ahí lo hacen en el repo REAL — falla silenciosa que sólo
    se nota mirando `git status`."""
    real_vault = Path(__file__).resolve().parent.parent / "vault"
    escapadas = [name for name, val in vars(cfg).items()
                 if name.isupper() and isinstance(val, Path)
                 and (val == real_vault or real_vault in val.parents)]
    assert not escapadas, (f"rutas sin aislar en conftest.toy_vault: {escapadas} — agregalas al "
                           "dict `paths` del fixture")
