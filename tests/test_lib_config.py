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


def test_concept_areas_sin_declarar_apaga_el_chequeo(toy_vault):
    """Sin `concept_areas` declarado el typo-check queda APAGADO (`[]`), no inferido de las carpetas
    que hay en disco: inferirlo convertiría cualquier typo ya cometido en "área declarada", que es
    lo contrario de lo que el chequeo hace. El lint reporta la lista ausente."""
    obj = dict(cfg.load_objective())
    obj.pop("concept_areas")
    write_yaml(toy_vault.OBJECTIVE_YAML, obj)
    (toy_vault.CONCEPTS / "zzz").mkdir()
    (toy_vault.CONCEPTS / "activity").mkdir()
    assert cfg.load_concept_areas() == []


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
    assert cfg.load_concept_areas() == []


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


# ── forma del objetivo y del registro (robustez del lector) ──────────────────

def test_concept_areas_escalar_no_se_deshace_en_caracteres(toy_vault):
    """`concept_areas: indicators` (una bóveda de un área, el caso natural) se desempaquetaba
    CARÁCTER POR CARÁCTER y el typo-check se invertía: marcaba como no declarada justo el área
    recién declarada. Un escalar = lista no declarada → chequeo apagado."""
    write_yaml(cfg.OBJECTIVE_YAML, {"name": "x", "concept_areas": "indicators"})
    assert cfg.load_concept_areas() == []


def test_registro_ilegible_no_tumba_a_sus_lectores(toy_vault):
    """El framework INSTRUYE editar el registro a mano ("sacá la entrada de `decisiones`"), así que
    un YAML roto o que no parsea a mapa tiene que degradar, no reventar al lint/triage/query_ads."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("x").write_text("- esto es una lista\n", encoding="utf-8")
    assert cfg.load_registro("x") == {} and cfg.load_decisiones("x") == {}
    cfg.registro_path("y").write_text("decisiones:\n  2019A: descartado\n", encoding="utf-8")
    assert cfg.load_decisiones("y") == {}          # la entrada escalar se descarta, no rompe


def test_es_del_carril_distingue_los_dos_juicios():
    """Sin este filtro `origen` es decorativo: el gate de candidatos del chaining se comía los
    rechazos de fuentes declaradas (#81) y al revés."""
    assert cfg.es_del_carril({"decision": "descartado"}, "chaining")             # sin origen = chaining
    assert cfg.es_del_carril({"origen": "fuente-declarada"}, "fuente-declarada")
    assert not cfg.es_del_carril({"origen": "fuente-declarada"}, "chaining")


# ── split_fm: un `---` dentro de un valor no debe cortar el frontmatter ──────

NOTA_CON_GUIONES = (
    '---\n'
    'bibcode: 2020aaa...1..1A\n'
    'title: "Un titulo con --- adentro"\n'
    'tags:\n'
    '- paper\n'
    '---\n'
    'cuerpo\n'
)


def test_split_fm_no_corta_dentro_de_un_valor():
    """El split por `---` es TEXTUAL y corta a la mitad de un escalar entrecomillado, así que
    `split_fm` devuelve `{}` sobre un frontmatter que **es YAML válido**. Todo lo que cuelga del
    frontmatter (tipo de nota, retracción, espejo, roles) queda mudo para esa nota."""
    fm = cfg.split_fm(NOTA_CON_GUIONES)
    assert fm.get("bibcode") == "2020aaa...1..1A", f"frontmatter perdido: {fm!r}"


# ── escritura del registro: atomicidad y no pisar lo ilegible (#51/#64) ──────

REGISTRO_ROTO = 'busqueda:\n  motivo: "sin cerrar\n  fecha: 2026-08-01\n'


def test_no_se_pisa_un_registro_ilegible(toy_vault):
    """El registro es, por definición del repo, lo que NO es regenerable (#51/#64). Si la lectura
    falló, escribir encima destruye `busqueda` y todos los juicios de curación en silencio — y el
    framework INSTRUYE editar ese archivo a mano (`ingest_topic.py:197`), así que un YAML roto es
    un estado alcanzable, no una hipótesis."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    f = cfg.registro_path("test_star")
    f.write_text(REGISTRO_ROTO, encoding="utf-8")
    with pytest.raises(Exception):
        cfg.save_decisiones("test_star", {"2020aaa...1..1A": {"decision": "descartado",
                                                             "motivo": "ruido",
                                                             "fecha": "2026-08-23"}})
    assert f.read_text(encoding="utf-8") == REGISTRO_ROTO, "se pisó un registro que no se pudo leer"


def test_save_registro_es_atomico(toy_vault, monkeypatch):
    """`write_text` directo deja el archivo torn si el proceso muere a mitad — medido: con un
    registro de 111 KB, 17 de 46 lecturas concurrentes vieron el archivo cortado. tmp+rename hace
    que el original sobreviva a cualquier fallo posterior a la escritura del temporal."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.save_registro("test_star", {"busqueda": {"fecha": "2026-08-01", "n_core": 37}})
    original = cfg.registro_path("test_star").read_text(encoding="utf-8")

    import os
    def boom(*a, **k):
        raise OSError("corte simulado al publicar el temporal")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        cfg.save_registro("test_star", {"busqueda": {"fecha": "2026-08-23", "n_core": 99}})
    assert cfg.registro_path("test_star").read_text(encoding="utf-8") == original, (
        "el registro original no sobrevivió a un fallo de escritura → save_registro no es atómico")


# ── issue 0.2 · helper atómico único (D-53) ──────────────────────────────────────────────────────
#
# Hasta 1.23.1 el repo tenía CINCO writers atómicos —tres clones del patrón tmp+os.replace
# (`save_registro`, `write_ground_truth`, `check_retractions._write_atomic`) y dos para binarios
# (`fetch_arxiv`/`fetch_pdf.write_pdf_atomic`)— y el writer que MÁS escribe, `make_notes`, no era
# atómico en ninguna de sus 15 escrituras a `vault/wiki/`. Cada tanda posterior del plan agrega
# writers: el helper sube al principio para que no haya un sexto clon.

def _tmps(d):
    return sorted(p.name for p in d.iterdir() if ".tmp" in p.name)


def test_write_text_atomic_publica(tmp_path):
    dest = tmp_path / "x.md"
    cfg.write_text_atomic(dest, "hola\n")
    assert dest.read_text(encoding="utf-8") == "hola\n"
    assert _tmps(tmp_path) == []


def test_fallo_en_replace_no_corrompe(tmp_path, monkeypatch):
    """El corte llega en la publicación: el archivo original queda **byte-idéntico** y no queda
    basura `.tmp` en el directorio. La primera mitad ya la daban los writers viejos; la segunda es
    la cola #5 de STATUS (el temporal huérfano)."""
    dest = tmp_path / "x.md"
    dest.write_text("original\n", encoding="utf-8")
    def boom(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(cfg.os, "replace", boom)
    with pytest.raises(OSError):
        cfg.write_text_atomic(dest, "nuevo\n")
    assert dest.read_text(encoding="utf-8") == "original\n"
    assert _tmps(tmp_path) == []


def test_fallo_escribiendo_el_temporal_no_deja_basura(tmp_path, monkeypatch):
    """El corte llega ANTES de publicar, mientras se llena el temporal. `save_registro` escribía el
    tmp fuera de todo `try`, así que ese caso dejaba un `.tmp<pid>` huérfano en `vault/config/`
    (el archivo real nunca se corrompía — es basura de disco, pero basura versionable)."""
    dest = tmp_path / "x.md"
    dest.write_text("original\n", encoding="utf-8")
    real = cfg.Path.write_text
    def boom(self, *a, **k):
        if ".tmp" in self.name:
            raise OSError("disco lleno")
        return real(self, *a, **k)
    monkeypatch.setattr(cfg.Path, "write_text", boom)
    with pytest.raises(OSError):
        cfg.write_text_atomic(dest, "nuevo\n")
    assert dest.read_text(encoding="utf-8") == "original\n"
    assert _tmps(tmp_path) == []


def test_write_bytes_atomic(tmp_path, monkeypatch):
    dest = tmp_path / "x.pdf"
    cfg.write_bytes_atomic(dest, b"%PDF-1.4\n")
    assert dest.read_bytes() == b"%PDF-1.4\n"
    dest2 = tmp_path / "y.pdf"
    monkeypatch.setattr(cfg.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(OSError):
        cfg.write_bytes_atomic(dest2, b"data")
    assert not dest2.exists()
    assert _tmps(tmp_path) == []


def test_write_text_atomic_crea_el_directorio(tmp_path):
    dest = tmp_path / "sub" / "dir" / "x.md"
    cfg.write_text_atomic(dest, "hola\n")
    assert dest.read_text(encoding="utf-8") == "hola\n"


def test_sin_escrituras_directas_a_vault():
    """Criterio de aceptación de D-53, como test y no como `grep` que alguien tiene que acordarse
    de correr: ningún módulo que escribe en `vault/` puede llamar `write_text`/`write_bytes` sobre
    su destino. Los módulos cuyo destino es `build/`/`outputs/` (scratch regenerable) quedan fuera
    a propósito — ahí un archivo torn se recupera re-corriendo el paso.  @inv INV-90"""
    import re
    from pathlib import Path
    import trace_invariants as ti
    escriben_en_vault = ("make_notes.py", "extract_fulltext.py", "fetch_web.py",
                         "ingest_topic.py", "fetch_ground_truth.py", "check_retractions.py",
                         "fetch_arxiv.py", "fetch_pdf.py", "lib_config.py")
    directo = re.compile(r"(?<!def )\b\w+\.write_(?:text|bytes)\(")
    ofensores = []
    for nombre in escriben_en_vault:
        src = (Path(cfg.ROOT) / "scripts" / nombre).read_text(encoding="utf-8")
        # los docstrings de estos módulos CITAN el patrón viejo para explicar por qué se fue
        # (`dest.write_bytes(buf)` directo…): son prosa, no código. Se descartan con el mismo
        # detector que usa el recolector de trazabilidad para no marcar texto citado.
        prosa = ti.lineas_declarativas(src)
        for n, ln in enumerate(src.splitlines(), 1):
            if n in prosa or not directo.search(ln):
                continue
            if "tmp.write_" in ln:
                continue          # el helper mismo (`_publicar`)
            ofensores.append(f"{nombre}:{n}: {ln.strip()}")
    assert ofensores == [], (
        "escrituras directas (no atómicas) a vault/ — usar cfg.write_text_atomic / "
        "cfg.write_bytes_atomic:\n  " + "\n  ".join(ofensores))
