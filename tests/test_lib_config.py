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


def test_load_themes_sin_archivo(toy_vault):
    toy_vault.THEMES_YAML.unlink()
    assert cfg.load_themes() == {}


def test_load_themes_vacio(toy_vault):
    toy_vault.THEMES_YAML.write_text("")
    assert cfg.load_themes() == {}


def test_theme_by_slug(toy_vault):
    write_yaml(toy_vault.THEMES_YAML, {"gp": {"title": "Gaussian processes", "area": "methods", "concept": "gp"}})
    slug, meta = cfg.theme_by_slug("gp")
    assert slug == "gp" and meta["concept"] == "gp"
    with pytest.raises(KeyError, match="themes.yaml"):
        cfg.theme_by_slug("nope")


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
    lo contrario de lo que el chequeo hace. El lint reporta la lista ausente.  @inv INV-47"""
    obj = dict(cfg.load_objective())
    obj.pop("concept_areas")
    write_yaml(toy_vault.OBJECTIVE_YAML, obj)
    (toy_vault.CONCEPTS / "zzz").mkdir()
    (toy_vault.CONCEPTS / "activity").mkdir()
    assert cfg.load_concept_areas() == []


def test_version_unica_fuente():
    """ALMAGESTO_VERSION es la ÚNICA fuente de versión: los UA de los fetchers derivan de la
    constante, y ningún script hardcodea 'Almagesto/x.y' (el drift que tenían los UA en 0.1).

    Mide **la mitad "única fuente de verdad"** de INV-62, no la otra (que cada NOTA declare con qué
    versión se generó, y que una cirugía posterior no la reetiquete): eso son los User-Agents de los
    fetchers, que no son notas. La otra mitad la miden
    `tests/test_make_notes.py::test_la_nota_declara_su_version` y
    `::test_restamp_headers_no_reetiqueta_la_nota`.  @inv INV-62"""
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
    with pytest.raises(SystemExit, match="usá ingest_theme"):
        cfg.require_field(meta, "query", "gp", "themes.yaml", hint="usá ingest_theme.")


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
    frontmatter (tipo de nota, retracción, espejo, roles) queda mudo para esa nota.  @inv INV-36"""
    fm = cfg.split_fm(NOTA_CON_GUIONES)
    assert fm.get("bibcode") == "2020aaa...1..1A", f"frontmatter perdido: {fm!r}"


# ── escritura del registro: atomicidad y no pisar lo ilegible (#51/#64) ──────

REGISTRO_ROTO = 'busqueda:\n  motivo: "sin cerrar\n  fecha: 2026-08-01\n'


def test_no_se_pisa_un_registro_ilegible(toy_vault):
    """El registro es, por definición del repo, lo que NO es regenerable (#51/#64). Si la lectura
    falló, escribir encima destruye `busqueda` y todos los juicios de curación en silencio — y el
    framework INSTRUYE editar ese archivo a mano (`ingest_theme.py:197`), así que un YAML roto es
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
                         "ingest_theme.py", "fetch_ground_truth.py", "check_retractions.py",
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


def test_objective_error_distingue_los_tres_estados(toy_vault):
    """`load_objective` colapsa "YAML roto" y "objetivo vacío" en el mismo `{}`. `objective_error`
    los separa para el llamador estricto, sin cambiarle la firma al tolerante.  @inv INV-80, INV-56"""
    assert cfg.objective_error() is None                     # el toy_vault trae uno sano
    cfg.OBJECTIVE_YAML.write_text("name: X\nrelevance:\n  topics:\n    rv: activity: starspot\n", encoding="utf-8")
    err = cfg.objective_error()
    assert err and "objective.yaml" in err
    cfg.OBJECTIVE_YAML.write_text("- una lista, no un mapa\n", encoding="utf-8")
    assert "mapa" in (cfg.objective_error() or "")
    cfg.OBJECTIVE_YAML.unlink()
    assert "no existe" in (cfg.objective_error() or "").lower()


# ── issue 2.1 · D-28: `busquedas` es una LISTA; el embudo no se suma (INV-89) ────────────────────
#
# Hasta 1.25.0 `save_busqueda` PISABA: cada corrida borraba la anterior, así que el registro sólo
# sabía de la última y la cabecera de la ficha publicaba SU embudo como si fuera el universo entero.
# Con dos corridas solapadas, sumar los `n_total` cuenta dos veces los papers que ya estaban.

def test_dos_busquedas_con_solapamiento_no_suman(toy_vault):
    """El experimento del contrato: A trae {1,2,3}, B trae {2,3,4}. El universo acumulado es 4, no
    6, y la entrada B distingue lo nuevo de lo que ya estaba.  @inv INV-89"""
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "n_total": 3,
                                    "bibcodes": ["1", "2", "3"]})
    cfg.save_busqueda("test_star", {"fecha": "2026-02-01", "n_total": 3,
                                    "bibcodes": ["2", "3", "4"]})
    bs = cfg.load_busquedas("test_star")
    assert len(bs) == 2
    assert bs[1]["n_nuevos"] == 1 and bs[1]["n_ya_estaban"] == 2
    assert cfg.universo_acumulado("test_star") == 4


def test_segunda_corrida_no_pisa_la_primera(toy_vault):
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "query": "A", "n_total": 1})
    cfg.save_busqueda("test_star", {"fecha": "2026-02-01", "query": "B", "n_total": 1})
    assert [b["query"] for b in cfg.load_busquedas("test_star")] == ["A", "B"]


def test_busqueda_preserva_decisiones(toy_vault):
    """No se rompe la garantía vieja: `decisiones` (el juicio de curación, lo NO regenerable) sigue
    intacto al appendear una búsqueda.  @inv INV-53"""
    cfg.save_decisiones("test_star", {"2020X": {"decision": "descartado", "motivo": "ruido"}})
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "n_total": 1})
    assert cfg.load_decisiones("test_star")["2020X"]["motivo"] == "ruido"


def test_universo_acumulado_sin_bibcodes_cae_al_maximo(toy_vault):
    """Una entrada vieja sin `bibcodes` no puede aportar identidad, sólo cardinalidad: se toma el
    MÁXIMO (cota inferior honesta del universo), nunca la suma — sumar es el bug que D-28 cierra."""
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "n_total": 30})
    cfg.save_busqueda("test_star", {"fecha": "2026-02-01", "n_total": 40})
    assert cfg.universo_acumulado("test_star") == 40


# ── issue 2.2 · D-57: cada paso deja traza estructurada en `cadena:` (INV-91) ───────────────────

def test_save_paso_appendea_con_fecha_version_y_via(toy_vault, monkeypatch):
    """R-6, decidida por el usuario: **cada script se estampa a sí mismo**. `via` distingue el paso
    corrido por el orquestador del corrido a mano — con la alternativa (estampar sólo desde
    `run()`) un paso suelto quedaba invisible y el lint reportaba un corte que no ocurrió.
    @inv INV-91"""
    monkeypatch.delenv("ALMAGESTO_VIA", raising=False)
    cfg.save_paso("test_star", "fetch_pdf", flags=["--force"])
    monkeypatch.setenv("ALMAGESTO_VIA", "orquestador")
    cfg.save_paso("test_star", "make_notes")
    cadena = cfg.load_cadena("test_star")
    assert [(p["paso"], p["via"]) for p in cadena] == [
        ("fetch_pdf", "suelto"), ("make_notes", "orquestador")]
    assert cadena[0]["flags"] == ["--force"]
    assert cadena[0]["version"] == cfg.ALMAGESTO_VERSION and cadena[0]["fecha"]


def test_save_paso_idempotente_el_mismo_dia(toy_vault, monkeypatch):
    """D-54 aplicado acá: re-correr el mismo paso el mismo día con los mismos flags no agrega
    ruido de diff — el registro queda byte-idéntico."""
    monkeypatch.delenv("ALMAGESTO_VIA", raising=False)
    cfg.save_paso("test_star", "fetch_pdf")
    antes = cfg.registro_path("test_star").read_bytes()
    cfg.save_paso("test_star", "fetch_pdf")
    assert cfg.registro_path("test_star").read_bytes() == antes


def test_save_paso_con_flags_distintos_si_registra(toy_vault, monkeypatch):
    """Lo que cambia sustantivamente sí entra: `--force` no es la misma corrida que sin él."""
    monkeypatch.delenv("ALMAGESTO_VIA", raising=False)
    cfg.save_paso("test_star", "fetch_ground_truth")
    cfg.save_paso("test_star", "fetch_ground_truth", flags=["--force"])
    assert len(cfg.load_cadena("test_star")) == 2


def test_save_paso_preserva_busquedas_y_decisiones(toy_vault, monkeypatch):
    monkeypatch.delenv("ALMAGESTO_VIA", raising=False)
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "n_total": 1})
    cfg.save_decisiones("test_star", {"2020X": {"decision": "descartado", "motivo": "ruido"}})
    cfg.save_paso("test_star", "query_ads")
    assert cfg.load_busquedas("test_star") and cfg.load_decisiones("test_star")


# ── issue 2.4 · D-52: el descarte re-aceptado queda ANULADO, no contradicho ─────────────────────

def test_descartado_luego_declarado_queda_anulado(toy_vault):
    """Hoy, al re-aceptar un bibcode que estaba descartado, la decisión vieja **se queda ahí
    contradiciendo lo que se hizo**: el registro dice "descartado por ruido" sobre un paper que
    está ingestado. Anularla explícito preserva las dos mitades — que se descartó, y que se
    revirtió."""
    cfg.save_decisiones("test_star", {"2020X": {"decision": "descartado", "motivo": "ruido",
                                                "fecha": "2026-01-01"}})
    assert cfg.anular_decision("test_star", "2020X", por="extra_core") is True
    d = cfg.load_decisiones("test_star")["2020X"]
    assert d["decision"] == "anulada" and d["anulada_por"] == "extra_core" and d["fecha"]


def test_anulacion_preserva_el_juicio_previo(toy_vault):
    """El motivo viejo sigue legible: es el dato NO regenerable, y perderlo al revertir es el mismo
    agujero que #51 cerró para el descarte."""
    cfg.save_decisiones("test_star", {"2020X": {"decision": "descartado", "motivo": "ruido",
                                                "fecha": "2026-01-01"}})
    cfg.anular_decision("test_star", "2020X", por="extra_core")
    previa = cfg.load_decisiones("test_star")["2020X"]["previa"]
    assert previa["motivo"] == "ruido" and previa["fecha"] == "2026-01-01"


def test_anular_lo_que_no_estaba_descartado_no_hace_nada(toy_vault):
    assert cfg.anular_decision("test_star", "2099Z", por="extra_core") is False


def test_anular_no_cruza_carriles(toy_vault):
    """Los dos carriles (#51 chaining, #81 fuente declarada) conviven en `decisiones`: anular el
    descarte de una fuente declarada no puede tocar el del chaining con la misma clave."""
    cfg.save_decisiones("test_star", {
        "2020X": {"decision": "descartado", "motivo": "chaining", "origen": "chaining"},
    })
    assert cfg.anular_decision("test_star", "2020X", por="sources", carril="fuente-declarada") is False
    assert cfg.load_decisiones("test_star")["2020X"]["decision"] == "descartado"


# ── issue 2.5 · D-58 / R-2: `extra_core` estructurado, con detector ─────────────────────────────

EC_OK = [{"bibcode": "2020X", "via": "triage", "motivo": "reanaliza la señal b"}]


def test_load_extra_core_forma_canonica(toy_vault):
    assert cfg.load_extra_core({"extra_core": EC_OK}, entry="test_star") == EC_OK


def test_extra_core_escalar_detectado(toy_vault):
    """R-2 (decidida por el usuario): forma dura con DETECTOR, no lector tolerante. El atajo
    `extra_core: 2020X` era YAML válido y `_listify_curado` lo aceptaba; el costo es que el
    registro no dice ni quién lo aceptó ni por qué — el mismo agujero que #51 cerró para el
    descarte, en el carril de la aceptación."""
    with pytest.raises(SystemExit) as exc:
        cfg.load_extra_core({"extra_core": "2020X"}, entry="test_star")
    assert "extra_core" in str(exc.value) and "bibcode:" in str(exc.value)


def test_extra_core_lista_de_strings_detectada(toy_vault):
    with pytest.raises(SystemExit) as exc:
        cfg.load_extra_core({"extra_core": ["2020X", "2021Y"]}, entry="test_star")
    assert "2020X" in str(exc.value)          # el mensaje trae el snippet ya armado


def test_extra_core_sin_via_o_sin_motivo_detectado(toy_vault):
    for meta in ({"extra_core": [{"bibcode": "2020X", "motivo": "m"}]},
                 {"extra_core": [{"bibcode": "2020X", "via": "triage"}]},
                 {"extra_core": [{"via": "triage", "motivo": "m"}]}):
        with pytest.raises(SystemExit):
            cfg.load_extra_core(meta, entry="test_star")


def test_extra_core_via_fuera_de_vocabulario_detectado(toy_vault):
    with pytest.raises(SystemExit) as exc:
        cfg.load_extra_core({"extra_core": [{"bibcode": "2020X", "via": "a-mano", "motivo": "m"}]},
                            entry="test_star")
    assert "usuario" in str(exc.value)        # el mensaje lista el vocabulario


def test_extra_core_ausente_es_lista_vacia(toy_vault):
    assert cfg.load_extra_core({}, entry="test_star") == []


# ── Tanda 4 · D-1: autoridad por campo del ground-truth (INV-76) ────────────────────────────────

def test_autoridad_por_campo_declarada():
    """La declaración vive en UN lugar y la comparten los tres consumidores (fetch_ground_truth
    escribe, make_notes la publica en la cabecera, lint la vigila). Repetirla es cómo se
    desincronizan.  @inv INV-14"""
    assert cfg.AUTORIDAD_CAMPO["spectral_type"] == "simbad"
    assert cfg.AUTORIDAD_CAMPO["teff_K"] == "nea"
    assert cfg.AUTORIDAD_CAMPO["st_rotp_days"] == "nea"   # clave del JSON, no la de la ficha
    assert all(v in ("nea", "simbad") for v in cfg.AUTORIDAD_CAMPO.values())


# ── Archivos de instancia protegidos del merge (INV-68) ──────────────────────

def test_gitattributes_cubre_los_archivos_de_instancia():
    """@inv INV-68 — los archivos "propios de la instancia" tienen que estar bajo `merge=ours`, o
    el próximo `git merge upstream/main` los pisa con la versión del template. Es mecanismo
    declarativo (`.gitattributes`), así que sin un test que lo lea NADIE lo vigila: fue justo lo que
    pasó con el renombre R-5 —`topics.yaml` quedó protegido y `themes.yaml`, el archivo real, no—.
    La lista es la que declara `CLAUDE.md` §Framework vs instancia."""
    raiz = Path(__file__).resolve().parent.parent
    ga = (raiz / ".gitattributes").read_text(encoding="utf-8")
    protegidos = {l.split()[0] for l in ga.splitlines()
                  if l.strip() and not l.startswith("#") and "merge=ours" in l}
    esperados = {
        "vault/config/objective.yaml", "vault/config/stars.yaml", "vault/config/themes.yaml",
        "vault/STATUS.md", "vault/wiki/index.md", "vault/wiki/log.md",
        "vault/wiki/matrices/method_star.md",
    }
    assert esperados <= protegidos, f"sin merge=ours: {sorted(esperados - protegidos)}"
    # Y a la inversa: nada protegido que ya no exista (un puntero muerto se lee como cobertura).
    huerfanos = [r for r in protegidos - esperados if not (raiz / r).exists()]
    assert huerfanos == [], f"`.gitattributes` protege rutas inexistentes: {huerfanos}"


# ── D-50 · `downstream: []` (los consumidores declarados) ────────────────────

def test_load_downstream_lista(toy_vault):
    obj = dict(cfg.load_objective()); obj["downstream"] = ["ICA", "pipeline-rv"]
    write_yaml(cfg.OBJECTIVE_YAML, obj)
    assert cfg.load_downstream() == ["ICA", "pipeline-rv"]


def test_load_downstream_ausente_o_vacio_apaga(toy_vault):
    """Vacío/ausente = mitad apagada. `load_concept_areas` reporta su ausencia porque un typo de
    área es un error; acá NO hay nada que reportar: una bóveda sin consumidor nombrado es el caso
    normal (el flujo es unidireccional)."""
    assert cfg.load_downstream() == []
    obj = dict(cfg.load_objective()); obj["downstream"] = []
    write_yaml(cfg.OBJECTIVE_YAML, obj)
    assert cfg.load_downstream() == []


def test_load_downstream_escalar_se_toma_como_un_elemento(toy_vault):
    """`downstream: ICA` sin corchetes es YAML válido y la forma natural de declarar UNO. Tratarlo
    como forma inválida perdería la curación en silencio (mismo criterio que extra_core/aliases)."""
    obj = dict(cfg.load_objective()); obj["downstream"] = "ICA"
    write_yaml(cfg.OBJECTIVE_YAML, obj)
    assert cfg.load_downstream() == ["ICA"]


def test_el_token_no_sale_en_ningun_artefacto_ni_en_la_salida(toy_vault, capsys, monkeypatch):
    """INV-67 (P0) — la credencial no se escribe en ningún artefacto versionado ni en la salida de
    ninguna corrida, **mensajes de error incluidos**.

    La marca vivía en `test_download_pdf_token_solo_a_ads`, que mide **egress de red** (a quién se
    le manda el header) — otra propiedad. La mitad que este invariante enuncia es la **persistencia**
    y la **salida**, que es donde un token se filtra de verdad: un traceback con la URL firmada, un
    registro que guarda el header, una nota con el valor pegado.  @inv INV-67"""
    TOKEN = "TOKENSECRETO123456"
    cfg.ADS_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.ADS_KEY_FILE.write_text(TOKEN + "\n", encoding="utf-8")
    monkeypatch.delenv("ADS_DEV_KEY", raising=False)
    assert cfg.get_ads_token() == TOKEN

    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "query": "q", "n_total": 1})
    cfg.save_decisiones("test_star", {"2020X": {"decision": "descartado", "motivo": "ruido",
                                                "fecha": "2026-01-01"}})
    cfg.save_paso("test_star", "query_ads", flags=["--rows"])
    cfg.save_extraccion("test_star", subconjunto=False, criterio="todos")

    versionados = [f for f in cfg.VAULT.rglob("*")
                   if f.is_file() and f.name != cfg.ADS_KEY_FILE.name]
    for f in versionados:
        assert TOKEN not in f.read_text(encoding="utf-8", errors="replace"), \
            f"el token quedó escrito en {f.relative_to(cfg.VAULT)}"
    assert TOKEN not in capsys.readouterr().out, "el token salió por stdout"


def test_el_archivo_del_token_esta_gitignored():
    """La otra punta: el único archivo que SÍ lo tiene no se commitea. Se lee el `.gitignore` real
    del repo, no el de la bóveda de juguete — es el que protege la credencial de verdad."""
    # @inv INV-67
    ignore = (Path(__file__).resolve().parent.parent / ".gitignore").read_text(encoding="utf-8")
    assert any("ads_dev_key" in ln for ln in ignore.split("\n")), ignore


def test_save_busqueda_pliega_la_clave_vieja_en_vez_de_borrarla(toy_vault):
    """INV-53 — "escribir un registro nuevo no borra el juicio ya registrado, y la historia es
    reconstruible". `save_busqueda` hacía `data.pop("busqueda")`: la única corrida que un registro
    pre-D-28 documenta se perdía al migrar, justo en el **único artefacto no regenerable** de la
    bóveda. Ahora se pliega al frente de la lista, marcada.  @inv INV-53"""
    cfg.save_registro("test_star", {"slug": "test_star", "busqueda": {
        "fecha": "2026-01-01", "query": "vieja", "n_total": 40, "n_core": 12}})
    cfg.save_busqueda("test_star", {"fecha": "2026-08-24", "query": "nueva", "n_total": 50})
    bs = cfg.load_busquedas("test_star")
    assert len(bs) == 2 and bs[0]["query"] == "vieja" and bs[1]["query"] == "nueva"
    assert "pre-D-28" in bs[0]["schema"], "la plegada se declara como tal, no se hace pasar por nueva"
    assert cfg.load_registro("test_star").get("busqueda") is None, "la clave vieja no sobrevive"


def test_save_busqueda_no_pliega_si_ya_hay_historial(toy_vault):
    """Si el registro ya tiene `busquedas:`, un `busqueda:` residual sería un artefacto de edición
    a mano, no historia que rescatar: plegarlo inventaría una corrida en medio del historial."""
    cfg.save_busqueda("test_star", {"fecha": "2026-08-01", "query": "a", "n_total": 1})
    reg = cfg.load_registro("test_star")
    reg["busqueda"] = {"fecha": "2020-01-01", "query": "residuo"}
    cfg.save_registro("test_star", reg)
    cfg.save_busqueda("test_star", {"fecha": "2026-08-24", "query": "b", "n_total": 2})
    bs = cfg.load_busquedas("test_star")
    assert [b["query"] for b in bs] == ["a", "b"]
