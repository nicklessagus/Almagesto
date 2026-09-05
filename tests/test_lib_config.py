"""lib_config: token ADS, loaders de config, áreas de concepts (declarado vs tolerante)."""
import pathlib
from pathlib import Path
import re

import pytest

import lib_config as cfg
from conftest import mk_note, write_yaml


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


# AUD-53: acá vivía `test_concept_areas_sin_nada`, mismo camino y mismos datos que
# `test_concept_areas_sin_declarar_apaga_el_chequeo` (los dos `mkdir` que parecían diferenciarlo
# eran inertes: `load_concept_areas` lee sólo `objective.yaml`). Borrado — el que queda tiene el
# docstring con el porqué y la marca `@inv`.


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
    un YAML roto o que no parsea a mapa tiene que degradar, no reventar al lint/triage/query_ads.

    ⚠ La tolerancia es de `load_registro`, NO de `load_decisiones` (AUD-131): ahí el `{}` significa
    «no hay ninguna decisión», que es lo contrario de lo que el archivo dice — la curación quedaba
    revertida en silencio. Ver `test_load_decisiones_rehusa_sobre_registro_ilegible`."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("x").write_text("- esto es una lista\n", encoding="utf-8")
    assert cfg.load_registro("x") == {}
    cfg.registro_path("y").write_text("decisiones:\n  2019A: descartado\n", encoding="utf-8")
    assert cfg.load_decisiones("y") == {}          # la entrada escalar se descarta, no rompe


def test_load_decisiones_rehusa_sobre_registro_ilegible(toy_vault):
    """AUD-131 — el registro ilegible NO puede leerse como «no hay ninguna decisión».

    `load_registro` degrada a `{}` a propósito (el lint tiene que reportar, no morirse). En el
    camino de la CURACIÓN ese mismo `{}` revierte todo: los `--drop` dejan de aplicarse, los
    `--drop-core` vuelven a ser core y el triage los re-propone SIN el motivo — el bug de #51 más
    el de #112, disparados por un `:` sin comillas y sin que nada lo diga.  @inv INV-139"""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("roto").write_text("decisiones: [\n", encoding="utf-8")
    with pytest.raises(cfg.UnreadableRegistro) as exc:
        cfg.load_decisiones("roto")
    assert "curación" in str(exc.value)
    # el registro AUSENTE sigue siendo legítimo: no hay curación que revertir
    assert cfg.load_decisiones("nunca_ingestado") == {}
    assert cfg.registro_error("nunca_ingestado") is None
    # y la forma inválida (parsea, pero no a mapa) cuenta igual que el YAML roto
    cfg.registro_path("lista").write_text("- uno\n", encoding="utf-8")
    with pytest.raises(cfg.UnreadableRegistro):
        cfg.load_decisiones("lista")


def test_cli_exit_traduce_la_negativa_en_una_salida_limpia(toy_vault):
    """La negativa de INV-139 tiene que llegar a la terminal como GUARDA, no como traceback.

    Un `UnreadableRegistro` sin traducir se lee como que la herramienta se rompió, y el operador
    busca el bug en el script en vez de en su YAML. Se centraliza en un solo wrapper por el patrón
    más caro de la auditoría: el arreglo aplicado a un sitio y no a su gemelo.  @inv INV-139"""
    def revienta():
        raise cfg.UnreadableRegistro("registro roto de prueba")

    with pytest.raises(SystemExit) as exc:
        cfg.cli_exit(revienta)
    assert "⛔" in str(exc.value) and "registro roto de prueba" in str(exc.value)

    # y el camino normal sigue siendo `sys.exit(main())`: el código de salida pasa tal cual
    with pytest.raises(SystemExit) as ok:
        cfg.cli_exit(lambda: 0)
    assert ok.value.code == 0


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
    # @inv INV-90
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


# #137 · marcador para eximir UNA línea del guard de atomicidad: su destino no está en `vault/`
# (típicamente un reporte en `outputs/`, scratch regenerable). Es explícito a propósito — una
# exención tiene que ser una decisión visible en la línea, no un nombre ausente de una lista.
VAULT_WRITE_EXENTA = "# noqa: vault-write"

# Rutas de la bóveda: si un módulo nombra alguna, escribe (o puede escribir) adentro.
_VAULT_CONST = re.compile(
    r"\bcfg\.(VAULT|WIKI|RAW|CONFIG|STARS|PAPERS|CONCEPTS|QUERIES|MATRICES|PDFS|FULLTEXT"
    r"|GROUND_TRUTH|REGISTRO|STARS_YAML|THEMES_YAML|OBJECTIVE_YAML|registro_path)\b")


def modules_writing_to_vault() -> tuple:
    """Los módulos de `scripts/` en alcance del guard de INV-90, DERIVADOS del árbol (#137).

    El criterio es «nombra una ruta de `vault/`», no una lista curada: lo que importa es que un
    módulo nuevo entre **solo**, porque el modo de falla medido fue justamente uno que nadie agregó.
    `lib_config` entra por definición (define las rutas)."""
    from pathlib import Path
    return tuple(sorted(
        p.name for p in Path(cfg.ROOT, "scripts").glob("*.py")
        if p.name == "lib_config.py" or _VAULT_CONST.search(p.read_text(encoding="utf-8"))))


def test_sin_escrituras_directas_a_vault():
    """Criterio de aceptación de D-53, como test y no como `grep` que alguien tiene que acordarse
    de correr: ningún módulo que escribe en `vault/` puede llamar `write_text`/`write_bytes` sobre
    su destino. Los módulos cuyo destino es `build/`/`outputs/` (scratch regenerable) quedan fuera
    a propósito — ahí un archivo torn se recupera re-corriendo el paso.

    ⚠ Cubre también `shutil.copy*`: el guard miraba sólo `write_text`/`write_bytes` y por esa puerta
    `ingest_theme.repoint_source_pdf` copiaba el PDF de una fuente declarada **directo al destino
    final** (`shutil.copy2(src, dest)`), con el mismo modo de falla que H-07 cerró.  @inv INV-90"""
    import re
    from pathlib import Path
    import trace_invariants as ti
    # #137: la población se DERIVA. Acá había una allowlist de 9 nombres escrita a mano que no
    # incluía `entity.py` —un writer real de la bóveda—, así que mutar su escritura a una no atómica
    # dejaba el guard en verde. Un gate que mide una lista no mide la garantía (regla de método #2),
    # y nadie mantenía la lista sincronizada: la misma falla ya había ocurrido por el otro lado
    # (AUD-02, `shutil.copy*`). Ahora un módulo nuevo que toque `vault/` entra solo.
    escriben_en_vault = modules_writing_to_vault()
    directo = re.compile(r"(?<!def )\b\w+\.(?:write_(?:text|bytes)|copy2?|copyfile)\(")
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
            if "tmp.write_" in ln or ", tmp)" in ln:
                continue          # el helper mismo (`_publicar`): el destino ES el temporal
            if VAULT_WRITE_EXENTA in ln:
                continue          # destino declarado FUERA de vault/ (ver la constante)
            ofensores.append(f"{nombre}:{n}: {ln.strip()}")
    assert ofensores == [], (
        "escrituras directas (no atómicas) a vault/ — usar cfg.write_text_atomic / "
        "cfg.write_bytes_atomic / cfg.copy_file_atomic:\n  " + "\n  ".join(ofensores))


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


def test_yaml_error_distingue_ausente_roto_y_no_mapa(tmp_path):
    """AUD-289: `yaml_error` es la única pieza pública del trío `stars_error`/`themes_error` sin
    test directo. Tres estados (INV-80): ausente es legítimo (`None`); YAML roto nombra el archivo
    y el `que`; válido pero no-mapa también es error. Sano → `None`.  @inv INV-80"""
    f = tmp_path / "cosas.yaml"
    assert cfg.yaml_error(f, "cada clave es una cosa") is None
    f.write_text("a:\n  title: mal: sin comillas\n", encoding="utf-8")
    err = cfg.yaml_error(f, "cada clave es una cosa")
    assert err and "cosas.yaml" in err
    f.write_text("- lista\n", encoding="utf-8")
    assert "mapa" in (cfg.yaml_error(f, "cada clave es una cosa") or "")
    f.write_text("a:\n  title: bien\n", encoding="utf-8")
    assert cfg.yaml_error(f, "cada clave es una cosa") is None


def test_load_red_pass_distingue_los_cuatro_estados_y_red_path_es_UNA(toy_vault):
    """AUD-282: la pasada de red vive en `cfg.RED_FILE` (antes `sweep_external` y el lint la
    deletreaban cada uno). Ausente, ilegible y sin `ultima_pasada_red` → `{}`; sana → el mapa."""
    assert cfg.red_path() == cfg.REGISTRO / "_red.yaml"
    assert cfg.load_red_pass() == {}
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.red_path().write_text("ultima_pasada_red: [mal\n", encoding="utf-8")
    assert cfg.load_red_pass() == {}
    cfg.red_path().write_text("otra_clave: 1\n", encoding="utf-8")
    assert cfg.load_red_pass() == {}
    cfg.red_path().write_text("ultima_pasada_red:\n  fecha: \"2026-09-04\"\n  cubrio: [versiones]\n",
                              encoding="utf-8")
    assert cfg.load_red_pass() == {"fecha": "2026-09-04", "cubrio": ["versiones"]}


def test_extra_core_snippet_DECLARA_el_tope_en_vez_de_cortar_en_silencio():
    """AUD-285: `tope=10` era un parámetro que nadie variaba y `query_ads --sweep` cortaba el
    snippet a 10 sin decirlo (triage lo decía a mano, con otro `10` literal). Hoy el snippet lo
    declara él mismo, para los dos carriles."""
    recs = [{"bibcode": f"2020x....{i:02d}A"} for i in range(cfg.EXTRA_CORE_SNIPPET_TOPE + 3)]
    out = cfg.extra_core_snippet(recs)
    assert out.count("- bibcode:") == cfg.EXTRA_CORE_SNIPPET_TOPE
    assert "3 candidato(s) más" in out and "snippet acotado" in out
    assert cfg.EXTRA_CORE_MOTIVO_PLACEHOLDER in out
    assert "candidato(s) más" not in cfg.extra_core_snippet(recs[:2])


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


def test_cadena_cortada_distingue_los_tres_estados(toy_vault):
    """AUD-149 / INV-139 — sin `cadena` devolvía `None`, que es el valor de «corrieron todos».

    Los tres estados son distintos y accionables por separado: completa (nada que hacer), cortada
    en X (re-correr desde ahí), sin traza (no se puede saber). Colapsar el tercero en el primero
    saca al sujeto del chequeo por la puerta del verde."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("s").write_text("slug: s\n", encoding="utf-8")
    assert cfg.cadena_cortada("s") == cfg.CADENA_SIN_TRAZA        # sin traza ≠ completa
    canonica = ("uno", "dos")
    cfg.save_paso("s", "uno")
    assert cfg.cadena_cortada("s", canonica) == "dos"             # cortada: nombra el paso
    cfg.save_paso("s", "dos")
    assert cfg.cadena_cortada("s", canonica) is None              # completa

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
    # @inv INV-60
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


# ── D-49 · la lente: forma, comparación y diff offline ──────────────────────
#
# Viven acá y no en `test_query_ads` desde que la comparación se mudó a `lib_config`: su consumidor
# es el **lint**, que corre offline con `pyyaml` y nada más. Importar `query_ads` para compararla
# arrastraba `requests` y hacía fallar el lint en CI.

def test_lens_shape_no_revienta_con_require_invalido():
    """`combination_rule` ABORTA si `require` nombra una faceta inexistente (con razón: filtraría
    todo a no-core en silencio). Pero `lens_shape` sólo DESCRIBE la regla para compararla — si
    reventara, el lint perdería la categoría entera por una config que él mismo va a reportar."""
    forma = cfg.lens_shape({"facets": {"rv": "radial velocity"}, "require": ["no_existe"]})
    assert forma["require"] == ["no_existe"] and forma["facets"] == {"rv": "radial velocity"}


def test_lens_delta_nombra_que_cambio():
    a = {"facets": {"x": "aa", "y": "bb"}, "require": [], "min_facets": 1, "noise_doctypes": []}
    b = {"facets": {"x": "aa", "z": "cc"}, "require": ["x"], "min_facets": 2, "noise_doctypes": ["catalog"]}
    d = cfg.lens_delta(a, b)
    assert "faceta `y` eliminada" in d and "faceta `z` nueva" in d
    assert any(s.startswith("require ") for s in d) and "min_facets 1 → 2" in d
    assert cfg.lens_delta(a, dict(a)) == [], "lentes idénticas: sin delta"


def test_lens_delta_ignora_el_orden_de_require():
    """Reordenar `require` no mueve el corte (todas son obligatorias): reportarlo sería un hallazgo
    falso que manda a re-correr la cadena de todos los sujetos para nada."""
    a = {"facets": {}, "require": ["a", "b"], "min_facets": 1, "noise_doctypes": []}
    b = {**a, "require": ["b", "a"]}
    assert cfg.lens_delta(a, b) == []


def test_lens_textual_changed_separa_la_mitad_evaluable():
    solo_doctypes = ["noise_doctypes [] → ['catalog']"]
    assert cfg.lens_textual_changed(solo_doctypes) is False
    assert cfg.lens_textual_changed(solo_doctypes + ["faceta `x` nueva"]) is True


def test_note_lens_text_toma_titulo_abstract_y_keywords():
    fm = {"title": "Starspot Evolution", "keywords": ["stellar activity", "RV"]}
    body = "# T\n\n## Abstract\nWe measure the RADIAL velocity.\n\n## Extracción\nno cuenta\n"
    t = cfg.note_lens_text(fm, body)
    assert "starspot evolution" in t and "radial velocity" in t and "stellar activity" in t
    assert "no cuenta" not in t, "sólo la sección Abstract, no el resto del cuerpo"


def test_note_lens_text_no_toma_el_marcador_de_abstract_ausente():
    """`_(no disponible)_` es lo que `write_paper_notes` deja cuando ADS no devolvió abstract: no es
    texto del paper y no puede matchear una faceta."""
    assert cfg.note_lens_text({"title": None}, "## Abstract\n_(no disponible)_\n").strip() == ""


def test_lens_diff_offline_no_saca_del_core_un_extra_core(toy_vault, monkeypatch):
    """`extra_core` es override del usuario (igual que `via: manual` en `classify_record`): la regla
    no lo toca, así que nunca puede aparecer como 'saldría'."""
    write_yaml(cfg.STARS_YAML, {"Estrella Test": {"slug": "test_star", "ads_object": "Test Star",
                                                  "extra_core": [{"bibcode": "2020Curado"}]}})
    cfg.save_registro("test_star", {"slug": "test_star", "busquedas": [
        {"fecha": "2026-01-01", "bibcodes": ["2020Curado", "2020Comun"], "lente": {}}]})
    for stem in ("2020Curado", "2020Comun"):
        (cfg.PAPERS / f"{stem}.md").write_text(
            f"---\nbibcode: {stem}\ntitle: nada que ver\nstars: [Estrella Test]\n"
            f"keywords: []\nrelevance: high\ntags: [paper]\n---\n## Abstract\nasteroseismology\n",
            encoding="utf-8")
    entran, salen, sin_nota = cfg.lens_diff_offline("test_star")
    assert salen == ["2020Comun"], f"el curado no sale; {salen}"
    assert entran == [] and sin_nota == []


def test_lens_diff_offline_declara_los_papers_sin_nota(toy_vault):
    """El techo del chequeo: sin `--all` el no-core no deja nota, así que `entran` sólo puede hablar
    de lo que alguien escribió. Publicar el faltante evita leer un `entran: 0` como 'no entra nada'."""
    cfg.save_registro("test_star", {"slug": "test_star", "busquedas": [
        {"fecha": "2026-01-01", "bibcodes": ["2020ConNota", "2020SinNota"], "lente": {}}]})
    (cfg.PAPERS / "2020ConNota.md").write_text(
        "---\nbibcode: 2020ConNota\ntitle: activity\nstars: [Estrella Test]\nkeywords: []\n"
        "relevance: high\ntags: [paper]\n---\n## Abstract\nstarspot activity\n", encoding="utf-8")
    entran, salen, sin_nota = cfg.lens_diff_offline("test_star")
    assert sin_nota == ["2020SinNota"]


def test_load_registro_tolera_un_yaml_en_otra_codificacion(toy_vault):
    """`load_registro` promete `{}` si el registro «no es legible» y ser **tolerante a la edición a
    mano, que el framework instruye explícitamente**.

    AUD-41: atrapaba `(yaml.YAMLError, OSError)`, así que un registro guardado en latin-1 —el caso
    natural: `motivo:` lleva prosa acentuada— propagaba `UnicodeDecodeError` y **tumbaba a los tres
    lectores que el docstring dice proteger** (lint, triage, query_ads), sobre el único artefacto no
    regenerable de la bóveda.  @inv INV-51
    """
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    (cfg.REGISTRO / "test_star.yaml").write_bytes(
        "decisiones:\n  2020Foo:\n    motivo: revisión metodológica\n".encode("latin-1"))
    assert cfg.load_registro("test_star") == {}
    assert cfg.load_busquedas("test_star") == []
    # AUD-131: en el camino de la curación la tolerancia se invierte — ver
    # `test_load_decisiones_rehusa_sobre_registro_ilegible`.
    with pytest.raises(cfg.UnreadableRegistro):
        cfg.load_decisiones("test_star")


def test_flags_usados_no_reporta_el_posicional_como_flag():
    """AUD-44: `flags_usados` promete los **flags** no-default y devolvía también el posicional.

    `--slug=<x>` salía en TODA corrida de los seis scripts cuyo posicional se llama `slug`, o sea el
    «ruido constante» que el docstring dice evitar, en `cadena:` del registro versionado. Que
    `ignorar` listara `theme` a mano muestra que la exclusión era intencional: se derivan del
    parser.  @inv INV-44
    """
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    assert cfg.flags_usados(ap.parse_args(["tau-cet"]), ap) == []
    assert cfg.flags_usados(ap.parse_args(["tau-cet", "--force"]), ap) == ["--force"]
    assert cfg.flags_usados(ap.parse_args(["tau-cet", "--limit", "1"]), ap) == ["--limit=1"]


def test_ninguna_copia_directa_al_destino_final_en_vault():
    """Hermano del guard de `write_text`/`write_bytes`, para el caso «el origen es otro archivo».

    `shutil.copy2(src, dest)` escribe en el destino FINAL: un corte deja un PDF truncado que la
    cadena da por bajado (`if dest.exists() and not force`) — exactamente el modo de falla que H-07
    cerró para `write_bytes`, vivo por otra puerta. `ingest_theme.repoint_source_pdf` lo hacía y el
    guard no lo veía porque buscaba sólo `.write_text(`/`.write_bytes(` (AUD-02).  @inv INV-90"""
    import re
    from pathlib import Path
    ofensores = []
    for nombre in ("ingest_theme.py", "make_notes.py", "fetch_pdf.py", "fetch_arxiv.py",
                   "fetch_web.py", "extract_fulltext.py", "fetch_ground_truth.py"):
        src = (Path(cfg.ROOT) / "scripts" / nombre).read_text(encoding="utf-8")
        for n, linea in enumerate(src.splitlines(), 1):
            if re.search(r"shutil\.copy(2|file)?\(", linea) and not linea.lstrip().startswith("#"):
                if ", tmp)" in linea:
                    continue                      # el helper mismo: el destino ES el temporal
                ofensores.append(f"{nombre}:{n}: {linea.strip()}")
    assert not ofensores, ("copia no atómica dentro de vault/ — usar cfg.copy_file_atomic:\n  "
                           + "\n  ".join(ofensores))


# ── puerta 2: la única metadata que cambia sola y admite core (#106, INV-104) ──
def _tema(tmp_path, monkeypatch, umbral_yaml, umbral_registro, notas):
    """Arma un tema con su registro y sus notas. `umbral_*` acepta el centinela "sin" = no declarado."""
    meta = {"title": "T", "facet": "x"}
    if umbral_yaml != "sin":
        meta["fundacional_min_citas"] = umbral_yaml
    monkeypatch.setattr(cfg, "theme_by_slug", lambda s: ("T", meta))
    regla = {"facet": "x"}
    if umbral_registro != "sin":
        regla["umbral"] = umbral_registro
    monkeypatch.setattr(cfg, "load_busquedas",
                        lambda s: [{"fecha": "2026-01-01", "lente": {"regla_tema": regla}}])
    monkeypatch.setattr(cfg, "notes_of_subject",
                        lambda s: [(b, {"bibcode": b, "citation_count": n}, "") for b, n in notas])


def test_puerta2_umbral_igual_no_reporta_nada(tmp_path, monkeypatch):
    """@inv INV-104 — El caso normal, y tiene que ser gratis: sin cambio de umbral no se mira ninguna nota."""
    _tema(tmp_path, monkeypatch, 2000, 2000, [("A", 5000)])
    assert cfg.puerta2_cruces("ica") == ([], [], 0)


def test_puerta2_bajar_el_umbral_hace_entrar(tmp_path, monkeypatch):
    _tema(tmp_path, monkeypatch, 1000, 3000, [("A", 2000), ("B", 500)])
    entran, salen, sin = cfg.puerta2_cruces("ica")
    assert entran == [("A", 2000)] and salen == [] and sin == 0


def test_puerta2_subir_el_umbral_hace_salir(tmp_path, monkeypatch):
    _tema(tmp_path, monkeypatch, 5000, 1000, [("A", 2000)])
    _entran, salen, _sin = cfg.puerta2_cruces("ica")
    assert salen == [("A", 2000)]


def test_puerta2_umbral_no_declarado_es_puerta_CERRADA_no_cero(tmp_path, monkeypatch):
    """D-26: sin declarar, la puerta NO abre. Tratarlo como umbral 0 la abriría para todos —
    exactamente al revés."""
    _tema(tmp_path, monkeypatch, "sin", 2000, [("A", 5000)])
    assert cfg.puerta2_cruces("ica") == ([], [], 0)


def test_puerta2_umbral_cero_declarado_NO_es_lo_mismo_que_sin_declarar(tmp_path, monkeypatch):
    """Declarar `fundacional_min_citas: 0` es una decisión (la puerta abre para todos) y tiene que
    poder distinguirse de no declararlo. Con truthiness los dos se leían igual."""
    _tema(tmp_path, monkeypatch, 0, 2000, [("A", 5)])
    entran, _salen, _sin = cfg.puerta2_cruces("ica")
    assert entran == [("A", 5)]


def test_puerta2_declara_las_notas_sin_conteo(tmp_path, monkeypatch):
    """Un `entran: 0` sobre notas que nadie pudo evaluar se lee como «no cambia nada» (INV-87)."""
    _tema(tmp_path, monkeypatch, 100, 200, [("A", None), ("B", "muchas")])
    entran, salen, sin = cfg.puerta2_cruces("ica")
    assert (entran, salen) == ([], []) and sin == 2


def test_puerta2_sin_umbral_previo_en_el_registro_no_inventa_salidas(tmp_path, monkeypatch):
    """Registro viejo (pre-#106) sin `regla_tema`: lo que cruza hacia arriba se reporta, pero nada
    puede 'salir' de un umbral que nunca se guardó."""
    _tema(tmp_path, monkeypatch, 1000, "sin", [("A", 2000), ("B", 5)])
    entran, salen, _sin = cfg.puerta2_cruces("ica")
    assert entran == [("A", 2000)] and salen == []


def test_puerta2_slug_que_no_es_tema_no_rompe(monkeypatch):
    def boom(s):
        raise KeyError(s)
    monkeypatch.setattr(cfg, "theme_by_slug", boom)
    assert cfg.puerta2_cruces("tau_ceti") == ([], [], 0)


def test_lens_delta_reporta_el_umbral_y_la_faceta_del_tema():
    d = cfg.lens_delta({"regla_tema": {"facet": "a", "umbral": 2000}},
                       {"regla_tema": {"facet": "b", "umbral": 500}})
    assert any("`facet` del tema" in x for x in d)
    assert any("fundacional_min_citas 2000 → 500" in x for x in d)


def test_lens_delta_distingue_sin_declarar_de_cero():
    d = cfg.lens_delta({"regla_tema": {"facet": "a"}},
                       {"regla_tema": {"facet": "a", "umbral": 0}})
    assert any("sin declarar (puerta 2 cerrada) → 0" in x for x in d)


def test_lens_delta_sin_regla_de_tema_no_inventa_cambios():
    """Una estrella no tiene regla de tema: su ausencia en las dos lentes no es un cambio."""
    assert cfg.lens_delta({"facets": {}}, {"facets": {}}) == []


def test_lens_current_de_un_tema_incluye_su_regla(monkeypatch):
    """#106: sin esto la comparación es peras contra manzanas — el registro del tema SÍ guarda
    `regla_tema`, así que `lens_delta` veía «estaba y ya no» y reportaba un cambio inventado sobre
    un tema que no cambió nada. Encontrado corriendo el lint contra una bóveda real; los unitarios
    no lo vieron porque cubrían «ninguno de los dos lados la trae», no «sólo uno»."""
    monkeypatch.setattr(cfg, "theme_by_slug",
                        lambda s: ("T", {"facet": "x", "fundacional_min_citas": 2000}))
    monkeypatch.setattr(cfg, "load_objective", lambda: {"relevance": {"facets": {}}})
    assert cfg.lens_current("ica")["regla_tema"] == {"facet": "x", "umbral": 2000}
    assert cfg.lens_delta(cfg.lens_current("ica"), cfg.lens_current("ica")) == []


def test_lens_current_de_una_estrella_no_inventa_regla_de_tema(monkeypatch):
    def boom(s):
        raise KeyError(s)
    monkeypatch.setattr(cfg, "theme_by_slug", boom)
    monkeypatch.setattr(cfg, "load_objective", lambda: {"relevance": {"facets": {}}})
    assert "regla_tema" not in cfg.lens_current("tau_ceti")


def test_lens_delta_no_reporta_cambio_cuando_solo_falta_modelar_la_regla(monkeypatch):
    """El bug exacto: stored la trae, current no la modela ⇒ NO es un cambio del usuario."""
    monkeypatch.setattr(cfg, "theme_by_slug",
                        lambda s: ("T", {"facet": "x", "fundacional_min_citas": 2000}))
    monkeypatch.setattr(cfg, "load_objective", lambda: {"relevance": {"facets": {}}})
    stored = dict(cfg.lens_current("ica"))
    assert cfg.lens_delta(stored, cfg.lens_current("ica")) == []


def test_el_umbral_solo_NO_es_un_cambio_textual():
    """#106: `lens_diff_offline` re-clasifica con la lente GLOBAL, así que sobre un tema de método
    devolvía «saldrían los 17 del tema» —cierto de la lente global, y sin ninguna relación con el
    umbral que se movió—. Atribuir mal es peor que no decir nada (regla de método #4)."""
    assert cfg.lens_textual_changed(["fundacional_min_citas 2000 → 30"]) is False
    assert cfg.lens_textual_changed(["noise_doctypes ['a'] → ['b']"]) is False
    # pero si además cambió algo textual, sí hay que evaluarlo
    assert cfg.lens_textual_changed(["fundacional_min_citas 2000 → 30",
                                     "faceta `rv`: regex cambiada"]) is True
    assert cfg.lens_textual_changed(["`facet` del tema: regex cambiada"]) is True


# ── stdout_tolerante: hueco pre-existente que el gate de mutación destapó ────
def test_stdout_tolerante_reconfigura_los_dos_streams(monkeypatch):
    """La consola no-UTF8 mataba el `--help` de los 11 CLIs con exit 1 — un exit code que miente.
    `print_seguro` no lo tapaba porque argparse escribe directo a `sys.stdout`."""
    vistos = []

    class Fake:
        def reconfigure(self, **kw):
            vistos.append(kw)
    monkeypatch.setattr(cfg.sys, "stdout", Fake())
    monkeypatch.setattr(cfg.sys, "stderr", Fake())
    cfg.stdout_tolerante()
    assert vistos == [{"errors": "replace"}, {"errors": "replace"}]


@pytest.mark.parametrize("exc", [AttributeError, ValueError, OSError])
def test_stdout_tolerante_no_se_cae_con_un_stream_no_reconfigurable(monkeypatch, exc):
    """Bajo pytest los streams están reemplazados: si esto lanzara, tumbaría cada `main()`."""
    class Roto:
        def reconfigure(self, **kw):
            raise exc("no se puede")
    monkeypatch.setattr(cfg.sys, "stdout", Roto())
    monkeypatch.setattr(cfg.sys, "stderr", Roto())
    cfg.stdout_tolerante()          # no lanza


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Ítem 5 (#63) · `find-contradictions` no re-litiga: los `aparente` se PERSISTEN
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# El fan-out de `find-contradictions` gasta un subagente por par y devuelve tres veredictos. El
# `real` tiene carril: se convierte en `disputes`, queda en la nota y el barrido siguiente lo ve.
# El `aparente` —«distinto régimen, distinta definición, distinta época»— **no tiene ninguno**: el
# skill lo reporta al chat y ahí muere. Consecuencia: cada auditoría vuelve a pagar el mismo par
# para volver a concluir lo mismo, y el motivo por el que la vez pasada no era disputa no lo tiene
# nadie. Es el mismo agujero que #51 cerró para el triage (el juicio de descarte vivía en `build/`,
# gitignored) y que #81 cerró para las fuentes declaradas: los cuatro cuadrantes de la curación
# dejan registro versionado, y éste es el que faltaba del lado de la revisión.
#
# Los tres símbolos son nuevos, así que estos tests mueren hoy con `AttributeError` — incluidos los
# contra-casos, que acá no se pueden separar de la API que los define.

def _no_disputa(bib_a="2018Autor", bib_b="2021Autor", eje="P_rot",
                veredicto="aparente", motivo="distinta época de observación",
                fecha="2026-08-26") -> dict:
    """Una entrada de `no_disputas` con la forma que fija la spec.

    La clave la calcula `par_key`, no el test: si el helper la armara a mano (`f"{a}|{b}|{eje}"`)
    sería un doble con distinto contrato que la función real, y el bug viviría exactamente en esa
    diferencia — la red #3 de `CLAUDE.md`, medida en `refs_of`/`_bare_doi`."""
    return {"par": cfg.par_key(bib_a, bib_b, eje), "bibcodes": [bib_a, bib_b], "eje": eje,
            "veredicto": veredicto, "motivo": motivo, "fecha": fecha}


def test_par_key_es_simetrica_y_distingue_el_eje():
    """La clave del par tiene que ser **simétrica**: el barrido no controla en qué orden le tocan A
    y B —depende de cómo salieron del `glob` de notas—, así que una clave orientada haría que el
    mismo par juzgado al revés no matchee y el fan-out se pague dos veces. Eso convierte a la
    persistencia en decorativa, que es peor que no tenerla: parece que hay red y no la hay.

    Y tiene que **distinguir el eje**: los mismos dos papers pueden estar de acuerdo en `P_rot` y no
    en `K`. Una clave por par de bibcodes silenciaría el segundo desacuerdo con el juicio del
    primero — un falso «ya lo miramos» sobre algo que nadie miró, que es justo el falso limpio que
    D-43 persigue.  @inv INV-125"""
    assert cfg.par_key("2018Autor", "2021Autor", "P_rot") == \
           cfg.par_key("2021Autor", "2018Autor", "P_rot")
    assert cfg.par_key("2018Autor", "2021Autor", "P_rot") != \
           cfg.par_key("2018Autor", "2021Autor", "K")


def test_save_no_disputa_appendea_y_se_consulta_por_la_clave_del_par(toy_vault):
    """Acumulativo como `busquedas` (D-28) y `barridos` (#88): cada par juzgado suma una entrada, no
    pisa la anterior. Y `load_no_disputas` devuelve un **índice por clave** —no una lista— porque el
    consumidor es el filtro del barrido, que pregunta *«¿este par ya se juzgó?»* una vez por par:
    con una lista eso es O(N) dentro de un bucle O(N²) sobre los pares del corpus."""
    cfg.save_no_disputa("test_star", _no_disputa("2018Autor", "2021Autor", "P_rot"))
    cfg.save_no_disputa("test_star", _no_disputa("2018Autor", "2021Autor", "K",
                                                 motivo="distinta definición de K"))
    idx = cfg.load_no_disputas("test_star")
    assert set(idx) == {cfg.par_key("2018Autor", "2021Autor", "P_rot"),
                        cfg.par_key("2018Autor", "2021Autor", "K")}
    guardada = idx[cfg.par_key("2021Autor", "2018Autor", "P_rot")]   # simétrica: se consulta al revés
    assert guardada["motivo"] == "distinta época de observación"
    assert guardada["veredicto"] == "aparente"
    assert sorted(guardada["bibcodes"]) == ["2018Autor", "2021Autor"]


def test_load_no_disputas_sin_registro_es_vacio(toy_vault):
    """Un sujeto que nunca se auditó devuelve `{}` y no revienta: el filtro del barrido corre sobre
    cualquier slug, y la primera auditoría de una entidad es el caso normal, no el borde."""
    assert cfg.load_no_disputas("test_star") == {}


def test_no_disputa_sin_motivo_aborta(toy_vault):
    """Mismo criterio que el `--reason` obligatorio del triage (#51/#111): **en seis meses lo que
    sirve es el motivo, no la categoría**. Un `aparente` sin motivo persiste el veredicto y tira la
    única información que no es regenerable —por qué el desacuerdo no era desacuerdo—, y encima
    bloquea el par para siempre: el barrido lo saltea y ya nadie puede revisar el juicio.

    Peor que no persistirlo, que al menos se vuelve a mirar.  @inv INV-125"""
    with pytest.raises((ValueError, RuntimeError)):
        cfg.save_no_disputa("test_star", _no_disputa(motivo=""))
    assert cfg.load_no_disputas("test_star") == {}, "abortó pero igual escribió"


def test_un_veredicto_real_no_entra_al_carril_de_no_disputas(toy_vault):
    """`real` tiene otro carril: se convierte en `disputes` de la nota, que es el artefacto que el
    consumidor lee y que el lint vigila. Dejarlo entrar acá lo **entierra**: el barrido siguiente lo
    saltea por «ya juzgado» y la disputa real nunca llega a la bóveda.

    El vocabulario de `veredicto` es cerrado (`aparente` | `no-concluyente`) por el mismo motivo que
    `role` (#73) y `status` (D-37): un valor fuera de la lista deja el campo mudo para su único
    consumidor, y un campo mudo se lee como «no se sabe».  @inv INV-125"""
    with pytest.raises((ValueError, RuntimeError)):
        cfg.save_no_disputa("test_star", _no_disputa(veredicto="real",
                                                     motivo="valores incompatibles"))
    assert cfg.load_no_disputas("test_star") == {}


def test_no_disputa_no_toca_los_otros_carriles_del_registro(toy_vault, monkeypatch):
    """El registro versionado es el **único artefacto no regenerable** de la bóveda (INV-53) y tiene
    dueños distintos por sección: `busquedas` la escribe `query_ads`, `decisiones` el `triage`,
    `barridos` el `--sweep`, `descubrimientos` la cascada. Un `save_` que lea-modifique-escriba mal
    borra el trabajo de otro dueño en silencio — el modo de falla exacto que `save_registro` frena
    cuando el YAML no parsea, acá por la puerta de al lado."""
    monkeypatch.delenv("ALMAGESTO_VIA", raising=False)
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "query": "q", "n_total": 1,
                                    "bibcodes": ["2018Autor"]})
    cfg.save_decisiones("test_star", {"2020X": {"decision": "descartado", "motivo": "ruido"}})
    cfg.save_barrido("test_star", {"fecha": "2026-01-02", "n_hits": 0})
    cfg.save_descubrimiento("test_star", {"fecha": "2026-01-03", "cobertura": {}})

    cfg.save_no_disputa("test_star", _no_disputa())

    assert [b["query"] for b in cfg.load_busquedas("test_star")] == ["q"]
    assert cfg.load_decisiones("test_star")["2020X"]["motivo"] == "ruido"
    reg = cfg.load_registro("test_star")
    assert len(reg["barridos"]) == 1 and len(reg["descubrimientos"]) == 1
    assert len(cfg.load_no_disputas("test_star")) == 1


def test_persistir_un_par_no_toca_las_disputes_de_la_nota(toy_vault):
    """Persistir un `aparente` **sólo evita re-juzgarlo**: no borra nada, no reabre nada y no toca
    las `disputes[]` que ya están tagueadas en la ficha. Los dos carriles conviven —el barrido
    excluye los pares ya juzgados *y* los ya tagueados— y son de dueños distintos: `disputes` es
    contenido de la bóveda que el usuario aprobó, `no_disputas` es bitácora de la revisión.

    El assert es sobre los **bytes** de la nota: cualquier reescritura, aunque preserve el YAML,
    es un efecto colateral sobre prosa que alguien verificó (y movería el ancla de D-4)."""
    from conftest import mk_note
    nota = mk_note(toy_vault.STARS, "test_star",
                   {"name": "Estrella Test", "slug": "test_star", "tags": ["star"],
                    "disputes": [{"field": "P_rot",
                                  "posiciones": [{"ref": "2018Autor", "value": 33},
                                                 {"ref": "2021Autor", "value": 11.5}]}]},
                   "# Estrella Test\n\nprosa.\n")
    antes = nota.read_bytes()
    cfg.save_no_disputa("test_star", _no_disputa())
    assert nota.read_bytes() == antes


def test_la_guarda_de_boveda_real_frena_una_escritura(tmp_path, monkeypatch):
    """La red de INV-126, probada contra sí misma: escribir bajo el `vault/` del repo REAL explota.

    Sin un test propio, la guarda es una fixture que nadie sabe si funciona — el mismo defecto que
    venía a cubrir. Se prueba con una ruta **construida**, no escribiendo de verdad: si la guarda
    fallara, este test crearía basura en la bóveda, que es justo lo prohibido.

    @inv INV-126"""
    from pathlib import Path
    from conftest import BovedaRealTocada, _VAULT_REAL
    with pytest.raises(BovedaRealTocada, match="ESCRIBIR en la bóveda real"):
        cfg.write_text_atomic(_VAULT_REAL / "config" / "no-deberia-existir.yaml", "x")
    # y una ruta de fuera de la bóveda sigue funcionando
    destino = tmp_path / "libre.txt"
    cfg.write_text_atomic(destino, "ok")
    assert destino.read_text(encoding="utf-8") == "ok"


def test_save_no_disputa_estampa_la_fecha_si_no_viene(toy_vault):
    """A3 del addendum: `save_no_disputa` estampa `fecha` cuando el llamador no la trae, y respeta la
    suya cuando sí. Es un registro de **juicio**, y el precedente de esa familia (`save_sintesis`,
    `save_extraccion`) la estampa solo — sin fecha, un juicio archivado no se puede pesar después.

    ⚠ Este test existe porque el requisito estaba en el addendum y **ningún test lo verificaba**: un
    requisito que nadie chequea es un deseo, no un contrato.  @inv INV-125"""
    import datetime as _dt
    cfg.save_no_disputa("test_star", {"bibcodes": ["2020A", "2021B"], "eje": "P_rot",
                                      "veredicto": "aparente", "motivo": "distinta época"})
    idx = cfg.load_no_disputas("test_star")
    assert list(idx.values())[0]["fecha"] == _dt.date.today().isoformat()

    cfg.save_no_disputa("test_star", {"bibcodes": ["2020C", "2021D"], "eje": "K",
                                      "veredicto": "aparente", "motivo": "otro régimen",
                                      "fecha": "2020-01-01"})
    prop = cfg.load_no_disputas("test_star")[cfg.par_key("2020C", "2021D", "K")]
    assert prop["fecha"] == "2020-01-01", "la del llamador no se pisa"


def test_re_juzgar_un_par_appendea_y_gana_el_ultimo(toy_vault):
    """A6 del addendum: un par puede volver a juzgarse cuando cambió la evidencia. Se **appendea**
    —el registro es historial, y borrar el juicio viejo perdería por qué se pensó distinto— y la
    consulta devuelve **el último**.

    ⚠ Otro requisito del addendum que no tenía test.  @inv INV-125"""
    for motivo in ("distinta época", "revisado: distinta definición del observable"):
        cfg.save_no_disputa("test_star", {"bibcodes": ["2020A", "2021B"], "eje": "P_rot",
                                          "veredicto": "aparente", "motivo": motivo,
                                          "fecha": "2026-01-01"})
    crudo = cfg.as_list((cfg.load_registro("test_star") or {}).get("no_disputas"))
    assert len(crudo) == 2, "el historial guarda los dos juicios"
    idx = cfg.load_no_disputas("test_star")
    assert len(idx) == 1 and "distinta definición" in list(idx.values())[0]["motivo"], "gana el último"


def test_la_poblacion_del_guard_de_atomicidad_se_DERIVA_no_se_lista():
    """Issue #137 — la red de INV-90 corría sobre una allowlist **escrita a mano** de 9 módulos que
    no incluía `entity.py`, que sí escribe en `vault/` (`stars.yaml`, `themes.yaml`, frontmatter de
    notas). Medido: mutar `entity.py:161` a `path.write_text(...)` dejaba el guard en VERDE.

    El gate medía una lista, no la garantía enunciada — el patrón de la regla de método #2. Y nadie
    mantenía la lista sincronizada, así que la misma falla ya había ocurrido una vez por el otro lado
    (AUD-02, `shutil.copy2`). La población se deriva: **todo módulo de `scripts/` que nombre una ruta
    de `vault/`**, así que un módulo nuevo entra solo.  @inv INV-90"""
    pob = modules_writing_to_vault()
    assert "entity.py" in pob, "el módulo que motivó #137 entra solo"
    assert len(pob) >= 15, "la población es derivada, no una lista corta escrita a mano"
    assert "openalex.py" not in pob, "y no arrastra a los que no tocan la bóveda"


# ── #188 paso 1 · `vistas[]`: la extracción es una lectura CON LENTE ────────────────────────────
#
# La nota de paper es UNA por bibcode y la extracción es una proyección del paper sobre un sujeto
# (el prompt pregunta «¿qué dice este paper SOBRE {name}?», con los grep armados desde los alias de
# ese sujeto). Sin declarar qué lectura se hizo, el silencio de la nota sobre un eje es
# indistinguible de «se miró y no hay nada» — el falso limpio que D-34 persigue en las hipótesis.
#
# Forma dura como `extra_core` (D-58) y por el mismo motivo: `vistas: [eps Eridani]` sería la misma
# conflación reclamo↔lectura con otro nombre. La diferencia con `load_extra_core` es DÓNDE vive el
# dato: `extra_core` está en config y lo lee un script de CLI (aborta); `vistas[]` está en el
# frontmatter de una nota y lo lee el LINT, que tiene que poder REPORTAR la nota rota sin morirse
# en la primera — por eso levanta `VistasError`, no `SystemExit`.

V_OK = [{"sujeto": "eps Eridani", "tipo": "star", "fecha": "2026-08-27",
         "txt": "eps_eridani", "lente": ["discovery", "rv"]}]


def test_load_vistas_forma_canonica(toy_vault):
    """@inv INV-134"""
    assert cfg.load_vistas({"vistas": V_OK}, entry="2000ApJ...544L.145H") == V_OK


def test_vistas_ausente_o_vacia_es_lista_vacia(toy_vault):
    assert cfg.load_vistas({}, entry="X") == []
    assert cfg.load_vistas({"vistas": None}, entry="X") == []
    assert cfg.load_vistas({"vistas": []}, entry="X") == []


def test_vistas_escalar_detectado(toy_vault):
    """El escalar y la lista de strings BLOQUEAN: sin `sujeto`+`tipo` la entrada no dice desde qué
    lente se leyó, que es todo lo que `vistas[]` viene a declarar."""
    with pytest.raises(cfg.VistasError) as exc:
        cfg.load_vistas({"vistas": "eps Eridani"}, entry="2000ApJ...544L.145H")
    assert "vistas" in str(exc.value) and "sujeto:" in str(exc.value)


def test_vistas_lista_de_strings_detectada(toy_vault):
    with pytest.raises(cfg.VistasError) as exc:
        cfg.load_vistas({"vistas": ["eps Eridani", "s_index"]}, entry="X")
    assert "eps Eridani" in str(exc.value)     # el mensaje trae el snippet ya armado


def test_vistas_entrada_no_mapa_detectada(toy_vault):
    with pytest.raises(cfg.VistasError):
        cfg.load_vistas({"vistas": [{"sujeto": "eps Eridani", "tipo": "star"}, "s_index"]},
                        entry="X")


def test_vistas_sin_sujeto_o_sin_tipo_detectada(toy_vault):
    for v in ([{"tipo": "star"}],
              [{"sujeto": "eps Eridani"}],
              [{"sujeto": "  ", "tipo": "star"}],
              [{"sujeto": "eps Eridani", "tipo": ""}]):
        with pytest.raises(cfg.VistasError):
            cfg.load_vistas({"vistas": v}, entry="X")


def test_vistas_tipo_fuera_de_vocabulario_detectado(toy_vault):
    """`tipo` se DECLARA (decisión del usuario, 2026-08-27): es duplicación respecto de
    stars.yaml/themes.yaml y se acepta a cambio de que el lint cace el typo."""
    with pytest.raises(cfg.VistasError) as exc:
        cfg.load_vistas({"vistas": [{"sujeto": "s_index", "tipo": "tema"}]}, entry="X")
    assert "tema" in str(exc.value) and "theme" in str(exc.value)


def test_vistas_error_no_es_system_exit(toy_vault):
    """Contra-caso: el lint recorre TODAS las notas, así que una rota tiene que reportarse, no
    tumbar la corrida. `SystemExit` no hereda de `Exception`: si `VistasError` fuera un exit, el
    `except Exception` de un llamador no lo agarraría y una sola nota mataría el barrido."""
    assert issubclass(cfg.VistasError, Exception)
    assert not issubclass(cfg.VistasError, SystemExit)


def test_vistas_campos_opcionales_no_se_inventan(toy_vault):
    """`fecha`, `txt` y `lente` son opcionales y el loader NO los rellena: la ausencia es «no
    consta» y un `None` inventado se leería igual que un `null` declarado por el migrador."""
    out = cfg.load_vistas({"vistas": [{"sujeto": "eps Eridani", "tipo": "star"}]}, entry="X")
    assert out == [{"sujeto": "eps Eridani", "tipo": "star"}]


def test_vistas_normaliza_sujeto_tipo_y_lente(toy_vault):
    out = cfg.load_vistas({"vistas": [{"sujeto": " eps Eridani ", "tipo": " star ",
                                       "lente": "rv"}]}, entry="X")
    assert out == [{"sujeto": "eps Eridani", "tipo": "star", "lente": ["rv"]}]


def test_vistas_no_muta_el_meta_original(toy_vault):
    meta = {"vistas": [{"sujeto": " eps Eridani ", "tipo": "star"}]}
    cfg.load_vistas(meta, entry="X")
    assert meta["vistas"][0]["sujeto"] == " eps Eridani "


def test_vista_tipos_declarado_una_sola_vez(toy_vault):
    """Mismo criterio que HYP_STATUS tras #175: el vocabulario vive en `lib_config` y lo comparten
    generador y validador. Dos declaraciones es cómo el generador escribe lo que el validador
    bloquea."""
    assert cfg.VISTA_TIPOS == ("star", "theme")


# ── #188 paso 2 · `no_vista`: la escotilla del reclamo que nadie leyó ───────────────────────────
#
# Un paper reclamado por tres sujetos y leído desde uno no es de por sí un defecto: la vista de un
# sujeto que sólo aporta al roll-up es OPCIONAL. Lo que no puede pasar es que sea SILENCIOSA —
# mismo criterio y mismo argumento que `no_sintetizado` (#75) y que el `--reason` del triage: no
# curar en silencio. Por sujeto, porque un paper compartido se saltea por motivos distintos en cada
# uno; el escalar del issue no puede expresar eso.

def test_load_no_vista_forma_canonica(toy_vault):
    nv = [{"sujeto": "s_index", "motivo": "sólo aporta al roll-up de métodos"}]
    assert cfg.load_no_vista({"no_vista": nv}, entry="X") == nv


def test_no_vista_ausente_es_lista_vacia(toy_vault):
    assert cfg.load_no_vista({}, entry="X") == []
    assert cfg.load_no_vista({"no_vista": None}, entry="X") == []


def test_no_vista_escalar_detectado(toy_vault):
    """El `no_vista: <motivo>` suelto que el issue escribe no dice DE QUÉ SUJETO se declara: en un
    paper que tres sujetos reclaman, la escotilla sin sujeto exime a los tres."""
    with pytest.raises(cfg.VistasError) as exc:
        cfg.load_no_vista({"no_vista": "sólo aporta al roll-up"}, entry="X")
    assert "sujeto:" in str(exc.value) and "motivo:" in str(exc.value)


def test_no_vista_sin_motivo_detectado(toy_vault):
    """Motivo obligatorio: sin él la escotilla apaga el hallazgo y no deja nada en su lugar, que es
    exactamente lo que `--reason` existe para impedir."""
    with pytest.raises(cfg.VistasError):
        cfg.load_no_vista({"no_vista": [{"sujeto": "s_index"}]}, entry="X")
    with pytest.raises(cfg.VistasError):
        cfg.load_no_vista({"no_vista": [{"motivo": "m"}]}, entry="X")


def test_no_vista_normaliza_y_no_muta(toy_vault):
    meta = {"no_vista": [{"sujeto": " s_index ", "motivo": " roll-up "}]}
    assert cfg.load_no_vista(meta, entry="X") == [{"sujeto": "s_index", "motivo": "roll-up"}]
    assert meta["no_vista"][0]["sujeto"] == " s_index "


def test_fuente_de_una_vista_es_vocabulario_cerrado():
    """#207 — opcional (ausente = no consta, como `fecha`) pero cerrada cuando está: un typo la
    dejaría muda justo para la pregunta que existe para contestar."""
    #  @inv INV-138
    ok = cfg.load_vistas({"vistas": [{"sujeto": "tau Cet", "tipo": "star", "fuente": "abstract"}]})
    assert ok[0]["fuente"] == "abstract"
    assert cfg.load_vistas({"vistas": [{"sujeto": "tau Cet", "tipo": "star"}]})[0].get("fuente") is None
    with pytest.raises(cfg.VistasError, match="fuente"):
        cfg.load_vistas({"vistas": [{"sujeto": "tau Cet", "tipo": "star", "fuente": "pdftotext"}]})


@pytest.mark.parametrize("bloque, tipo", [
    ("- a\n- b", "list"), ("una frase suelta", "str"), ("42", "int"), ("2026-01-01", "date"),
])
def test_split_fm_honra_su_firma_con_yaml_valido_no_mapa(bloque, tipo):
    """`split_fm` firma `-> dict` y promete «dict vacío si no hay o no parsea», pero un YAML
    **válido y no-mapa** volvía tal cual y reventaba a los 22 llamadores. Medido el 2026-08-28: una
    sola nota así tumbaba `lint.main()` entero con `AttributeError`, **sin reporte, sin nombre de
    archivo y sin escribir ningún output** — con un wikilink roto sembrado que nunca se reportó.
    `isinstance`, no `or {}`: un escalar truthy no cae en el `or`.  @inv INV-36"""
    assert cfg.split_fm(f"---\n{bloque}\n---\ncuerpo\n") == {}


@pytest.mark.parametrize("prefijo", ["", "﻿"])
def test_un_BOM_no_vuelve_invisible_el_frontmatter(prefijo):
    """U+FEFF al principio —lo escribe cualquier editor de Windows sin avisar— rompía el ancla
    `matches[0].start() != 0`: `frontmatter_span` devolvía `None`, `split_fm` `{}`, y `lint.fm_error`
    tampoco lo veía (chequea `startswith("---")`). La nota evadía **todos** los chequeos de su tipo
    —incluido `retracted`— sin una línea de reporte.  @inv INV-36"""
    fm = cfg.split_fm(f"{prefijo}---\nname: X\nretracted: true\n---\ncuerpo\n")
    assert fm == {"name": "X", "retracted": True}


# ── AUD-142/144/163: la lente, con la misma regla en todos lados ─────────────

def test_gate2_threshold_es_una_sola_regla():
    """AUD-142 — tres llamadores implementaban esto con tres contratos: `classify_theme` y
    `puertas_abiertas` con `isinstance(int)`, `puerta2_cruces` con `(int, float)`.

    Un `30000.0` —o el mucho más probable `"30000"` entre comillas en un YAML editado a mano—
    cerraba la puerta 2 para el clasificador y la dejaba abierta para el detector de drift, y el
    motivo que el clasificador publicaba decía «el tema no declara `fundacional_min_citas`», que es
    FALSO: lo declara. Un motivo equivocado es peor que ninguno — manda a agregar lo que ya está.
    @inv INV-141"""
    assert cfg.gate2_threshold({}) == (None, None)                  # ausente: legítimo (D-26)
    assert cfg.gate2_threshold({"fundacional_min_citas": 30000}) == (30000, None)
    assert cfg.gate2_threshold({"fundacional_min_citas": 30000.0}) == (30000, None)
    assert cfg.gate2_threshold({"fundacional_min_citas": 0}) == (0, None)   # umbral 0 es una decisión
    for malo in ("30000", 30.5, [30], {"a": 1}):
        umbral, motivo = cfg.gate2_threshold({"fundacional_min_citas": malo})
        assert umbral is None and motivo, malo
    # un bool ES un int en Python: `fundacional_min_citas: yes` valdría umbral 1
    assert cfg.gate2_threshold({"fundacional_min_citas": True}) == (None, cfg.gate2_threshold(
        {"fundacional_min_citas": True})[1])
    assert "booleano" in cfg.gate2_threshold({"fundacional_min_citas": True})[1]


def test_lens_diff_offline_respeta_el_extra_core_de_un_TEMA(toy_vault, monkeypatch):
    """AUD-144 — sólo miraba `star_by_slug`, así que en un tema el `extra_core` no se excluía y el
    diff proponía «saldría» para siempre lo que el usuario ya metió a mano.

    Y los temas son justo donde `extra_core` se usa más: en off-ADS y en la mitad ADS de un tema
    mixto es la vía normal de entrada. Una categoría que repite lo ya resuelto se deja de mirar."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"slug": "ica", "concept": "ICA",
                                         "extra_core": [{"bibcode": "1994Comon", "via": "usuario",
                                                         "fecha": "2026-08-28", "motivo": "canon"}]}})
    mk_note(cfg.PAPERS, "1994Comon", {"bibcode": "1994Comon", "tags": ["paper"],
                                      "relevance": "high", "thesis_links": ["ICA"],
                                      "title": "nada que la lente matchee"}, "cuerpo\n")
    entran, salen, _sin = cfg.lens_diff_offline("ica")
    assert salen == [], "el `extra_core` de un tema es core por decisión del usuario"


def test_una_faceta_que_no_compila_se_DICE(capsys):
    """AUD-163 — era un `continue` mudo, y «no compila» se contaba igual que «no matchea»: el diff
    devolvía un veredicto sobre una faceta que nadie evaluó. No revienta (la lente GUARDADA puede
    traer facetas viejas y el chequeo no puede volverse un falso rojo), pero lo dice."""
    cfg._FACETAS_ROTAS.clear()
    lente = {"facets": {"rota": "(sin cerrar", "ok": "radial velocity"}, "min_facets": 1}
    assert cfg.lens_core_text(lente, "radial velocity study") is True
    assert "no compila" in capsys.readouterr().err


def test_no_se_propaga_un_PDF_truncado_entre_slugs(toy_vault, capsys):
    """AUD-161 — el reuso D-18 copiaba lo que hubiera bajo el otro slug **sin mirarlo**.

    Un PDF truncado por un corte —el caso exacto que `--force` existe para reparar— se propagaba al
    slug nuevo y encima lo sacaba de `pendientes`: el paper quedaba «bajado» con un archivo que no
    se puede abrir, y la verdad de disco, que es la regla del framework acá, pasaba a mentir en dos
    lugares en vez de uno."""
    stem = "2020aaaA...1..1A"
    (cfg.PDFS / "otro").mkdir(parents=True, exist_ok=True)
    roto = cfg.PDFS / "otro" / f"{stem}.pdf"
    roto.write_bytes(b"<html>404 not found")
    assert cfg.artefacto_en_otro_slug(cfg.PDFS, "test_star", stem, ".pdf") is None
    assert "no empieza con `%PDF`" in capsys.readouterr().err

    roto.write_bytes(b"%PDF-1.4\n...")
    assert cfg.artefacto_en_otro_slug(cfg.PDFS, "test_star", stem, ".pdf") == roto
    # el `.txt` NO se valida por magic: es texto, y su legibilidad la mide `is_legible`
    (cfg.FULLTEXT / "otro").mkdir(parents=True, exist_ok=True)
    txt = cfg.FULLTEXT / "otro" / f"{stem}.txt"
    txt.write_text("prosa", encoding="utf-8")
    assert cfg.artefacto_en_otro_slug(cfg.FULLTEXT, "test_star", stem, ".txt") == txt


def test_la_marca_de_arxiv_se_busca_por_PAGINA_no_por_tope_de_chars():
    """AUD-164 / INV-29 — la marca va en el margen y `pdftotext` la emite donde caiga dentro de la
    página; una primera página a dos columnas pasa holgadamente los 4000 caracteres.

    Con el corte fijo, un **preprint** quedaba clasificado `publisher`, que es justo la distinción
    que #57 existe para hacer: con `eprint` una discrepancia numérica es candidata a diferencia de
    versión y no a error de la ficha. El alcance sigue acotado a dos páginas, y eso también importa:
    leer el paper entero traería los `arXiv:` de la BIBLIOGRAFÍA, que son de otros trabajos."""
    relleno = "x" * 6000
    assert cfg.arxiv_stamp(relleno + " arXiv:2101.00001v2 " + "y" * 100) == "v2"
    # dos páginas alcanzan; la tercera (donde suele empezar la bibliografía) ya no cuenta
    assert cfg.arxiv_stamp("p1\f" + relleno + "\fp3 arXiv:2101.00001v2") is None
    # y el piso de 4000 sigue cubriendo el `.txt` sin saltos de página
    assert cfg.arxiv_stamp("arXiv:2101.00001") == ""
    assert cfg.arxiv_stamp("un paper cualquiera sin marca") is None


def test_reattach_yaml_comments_devuelve_la_curacion_a_su_lugar():
    """AUD-169 / INV-139 — `yaml.safe_dump` tira TODOS los comentarios, y el framework instruye
    editar estos archivos a mano: esos comentarios son curación que nadie puede reconstruir.

    Se restauran las dos formas que la gente escribe —el bloque de arriba, re-anclado a su clave, y
    el comentario al final de la línea— y lo que no se pudo re-anclar vuelve como huérfano, nunca en
    silencio: ése es el punto."""
    original = ("# curado a mano el 2026-08-01\n"
                "bibcode: 2020X\n"
                "teff_K: 5344  # SIMBAD, no NEA\n"
                "# el P_rot lo puso el usuario\n"
                "P_rot_days: 34\n")
    nuevo = "otra: 1\nbibcode: 2020X\nteff_K: 5344\n"        # `P_rot_days` ya no está
    head, huerfanos = cfg.reattach_yaml_comments(original, nuevo)
    assert "# curado a mano el 2026-08-01\nbibcode: 2020X" in head
    assert "teff_K: 5344  # SIMBAD, no NEA" in head
    assert huerfanos == ["# el P_rot lo puso el usuario"], "lo no re-anclable se NOMBRA"
    # un `#` dentro de un escalar entrecomillado es contenido, no comentario
    h2, _ = cfg.reattach_yaml_comments('title: "un # adentro"\n', 'title: "un # adentro"\n')
    assert h2.strip() == 'title: "un # adentro"'


def test_la_corrida_migrada_cuenta_para_n_nuevos(toy_vault):
    """AUD-172 / INV-89 — el plegado del schema viejo iba DESPUÉS de computar `conocidos`.

    Así, los bibcodes de la corrida migrada no contaban como conocidos y la primera corrida
    post-migración reportaba como `n_nuevos` todo lo que ya estaba: justo el número que D-28
    introdujo para distinguir «traje 40» de «traje 40 y 38 ya estaban», mintiendo en la única
    corrida donde importa."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.save_registro("s", {"slug": "s", "busqueda": {"fecha": "2026-01-01",
                                                      "bibcodes": ["2019A", "2019B"]}})
    cfg.save_busqueda("s", {"fecha": "2026-08-28", "bibcodes": ["2019A", "2019B", "2020C"]})
    bs = cfg.load_busquedas("s")
    assert len(bs) == 2 and bs[0].get("schema", "").startswith("pre-D-28")
    assert bs[-1]["n_nuevos"] == 1 and bs[-1]["n_ya_estaban"] == 2


def test_par_key_no_colisiona_por_el_separador(toy_vault):
    """AUD-180 / INV-125 — el `eje` es texto libre, así que un `::` adentro corría el separador y
    dos pares distintos colapsaban en la misma clave: el falso «ya lo miramos» que el propio
    docstring de `par_key` dice evitar, por la puerta del formato en vez de por la del eje."""
    assert cfg.par_key("A", "B", "x::y") != cfg.par_key("A", "B::x", "y")
    assert cfg.par_key("A", "B", "eje") == cfg.par_key("B", "A", "eje")   # sigue siendo simétrica
    assert cfg.par_key("A", "B", "P_rot") != cfg.par_key("A", "B", "K")   # y sigue distinguiendo el eje


def test_no_disputas_con_forma_invalida_se_DICE(toy_vault, capsys):
    """AUD-180 — era un `continue` mudo. El registro se edita a mano, así que una entrada rota es
    alcanzable, y descartarla en silencio deja el par fuera del índice: el barrido lo vuelve a
    proponer **sin el motivo** por el que alguien ya lo había juzgado no-disputa."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.save_registro("s", {"slug": "s", "no_disputas": [
        "2019A vs 2020B",                                   # no es un mapa
        {"motivo": "distinto régimen"},                     # sin bibcodes ni par
        {"bibcodes": ["2019A", "2020B"], "eje": "K", "motivo": "ok"},
    ]})
    idx = cfg.load_no_disputas("s")
    assert list(idx) == [cfg.par_key("2019A", "2020B", "K")]
    assert "2 entrada(s) de `no_disputas`" in capsys.readouterr().err


def test_save_registro_no_pisa_un_registro_en_otra_codificacion(toy_vault):
    """AUD-192 / INV-25 — `UnicodeDecodeError` faltaba en la guarda, y es el caso NATURAL: `motivo:`
    lleva prosa acentuada, así que un registro en latin-1 es alcanzable (`load_registro` ya lo
    lista desde AUD-41).

    Sin él la excepción subía sin traducir, y esta guarda existe justamente para NO pisar a ciegas
    lo único no regenerable de la bóveda. `UnicodeDecodeError` es subclase de `ValueError`, no de
    `OSError`, así que el `except` viejo no la agarraba."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    original = "decisiones:\n  2020Foo:\n    motivo: revisión metodológica\n".encode("latin-1")
    cfg.registro_path("test_star").write_bytes(original)
    with pytest.raises(RuntimeError, match="no lo piso a ciegas"):
        cfg.save_registro("test_star", {"slug": "test_star"})
    assert cfg.registro_path("test_star").read_bytes() == original


def test_las_traducciones_son_secciones_estampadas():
    """#214 — el nombre en `SECCIONES_ESTAMPADAS` va COMPLETO. Con `## Traducción` pelado, el
    sufijo del encabezado real (« del abstract») empieza con letra y la regla de sufijo de INV-98
    lo rechaza: las traducciones NO quedaban exentas para `_es_estampada`/`solo_prosa`, mientras el
    `startswith` pelado de `lib_blocks` (la regla vieja) sí las eximía. Dos copias de la misma
    regla con semánticas opuestas, o sea cada consumidor con un conjunto distinto."""
    assert cfg.is_stamped_section("## Traducción del abstract")
    assert cfg.is_stamped_section("## Traducción de las conclusiones")
    assert cfg.is_stamped_section("## Abstract")
    # y la regla de sufijo sigue en pie: una sección PROPIA con nombre parecido no se exime
    assert not cfg.is_stamped_section("## Papers relevantes para el método")
    assert not cfg.is_stamped_section("## Vista — tau Cet")


def test_solo_prosa_saca_la_traduccion():
    """#214 — consecuencia medible: `solo_prosa` es lo que alimenta al gate R-1 (¿la nota tiene
    citas en prosa?), así que una traducción contada como prosa mueve un chequeo de cierre."""
    cuerpo = ("## Síntesis\nprosa real\n\n"
              "## Traducción del abstract\nAdemás, nuestro código usa entropía máxima.\n")
    assert "prosa real" in cfg.solo_prosa(cuerpo)
    assert "nuestro código" not in cfg.solo_prosa(cuerpo)


# ── #260 · el encabezado pegado a una fila de tabla ──────────────────────────────────────────────


def test_headings_glued_to_table_caza_el_encabezado_sin_linea_en_blanco():
    """#260 — hermano de `table_shape_issues`: otro mecanismo, la misma doctrina.

    GFM corta la tabla en el encabezado y Obsidian lo muestra bien, así que esto es invisible donde
    la bóveda se lee normalmente. Python-Markdown + `tables` —MkDocs y media cadena de export— lo
    absorbe **como una fila más**, y el `##` desaparece del outline con la población que D-10/INV-81
    obligan a publicar en el título."""
    body = ("| Letra | P |\n|---|---|\n| b | 4.3 |\n"
            "## Papers (49 · 28 sintetizados en esta ficha)\n\n| Bibcode |\n|---|\n| x |\n")
    assert cfg.headings_glued_to_table(body) == [
        (4, "## Papers (49 · 28 sintetizados en esta ficha)")]


def test_headings_glued_to_table_no_grita_por_el_encabezado_bien_separado():
    """El caso normal es gratis: con la línea en blanco no hay hallazgo."""
    body = ("| Letra | P |\n|---|---|\n| b | 4.3 |\n\n## Papers\n\n| Bibcode |\n|---|\n| x |\n")
    assert cfg.headings_glued_to_table(body) == []


def test_headings_glued_to_table_ignora_lo_que_no_es_fila_de_tabla():
    """Sólo cuenta una **fila de tabla** como línea previa (#260).

    Un `##` pegado a un párrafo o a un cierre de fence es feo y parsea como encabezado en todos
    lados; reportarlo sería ruido, y una categoría de alta señal que grita en falso se deja de
    mirar. Medido: `index.md` tiene tres `##` pegados a un ``` y ninguno se degrada."""
    assert cfg.headings_glued_to_table("prosa cualquiera\n## Papers\n") == []
    assert cfg.headings_glued_to_table("```\n## Papers\n") == []
    # Las dos mitades de «es una fila», cada una aislada: sin esto la mutación por cláusula
    # sobrevive, porque el caso de arriba falla las dos a la vez y no distingue cuál manda (#204).
    assert cfg.headings_glued_to_table("| celda sin cerrar\n## Papers\n") == [], \
        "arranca con `|` pero no termina: no es una fila de tabla"
    assert cfg.headings_glued_to_table("una tubería al final |\n## Papers\n") == [], \
        "termina en `|` pero no arranca: no es una fila de tabla"


def test_headings_glued_to_table_no_mira_atras_de_la_primera_linea():
    """El `##` en la línea 0 no tiene línea previa: sin la guarda, `lines[-1]` mira **el final del
    archivo** y puede reportar un hallazgo inventado sobre una nota que arranca con un encabezado."""
    assert cfg.headings_glued_to_table("## Papers\n\ntexto\n\n| a |\n|---|\n| b |") == []


# ── #275 · el comparador de citas: guión de corte y de-entrelazado por canaleta ──────────────────

def test_el_guion_de_corte_no_rompe_una_cita_con_guion_real():
    """#275 — la fuente trae `p-\\nmode` (guión de corte de `pdftotext`) y la nota cita `p-mode`.

    Sin borrar el guión de los DOS lados, la fuente queda `pmode` y la cita `p-mode`: toda cita con
    un guión real fallaba contra una fuente donde ese guión cayó en un fin de línea."""
    src = cfg.normalize_source_text("not related to the onset of p-\nmode oscillations.")
    assert cfg.quote_found("not related to the onset of p-mode oscillations", src)


def test_de_hifenado_sigue_uniendo_la_palabra_partida():
    """⛔ El ORDEN de las dos operaciones: si el `-` se borra ANTES del join, `inde-\\npendent` da
    `inde pendent` y el defecto se invierte."""
    src = cfg.normalize_source_text("inde-\npendent component analysis of the data")
    assert cfg.quote_found("independent component analysis of the data", src)


def test_el_guion_de_corte_absorbe_la_SANGRIA_de_la_continuacion():
    """#336 — en un `.txt` de `pdftotext -layout` la continuación viene INDENTADA (es la columna
    física), así que `homoscedas-\\n     tic` quedaba `homoscedas tic`: la palabra partida no se unía
    y toda cita que la contenga fallaba contra su propia fuente. Medido: **141 de 155** `.txt` de una
    bóveda real, **4232** ocurrencias."""
    src = cfg.normalize_source_text("the model is homoscedas-\n     tic and the noise is white")
    assert cfg.quote_found("the model is homoscedastic and the noise is white", src)


def test_una_cita_sin_ningun_fragmento_util_NO_cuenta_como_encontrada():
    """⛔ La dirección peligrosa de `quote_found`: si todos los fragmentos caen por debajo de
    `QUOTE_FRAG_MIN`, `all(...)` sobre la lista vacía es `True` y la cita pasaría como verbatim
    contra **cualquier** fuente. La guarda `frags and …` es la que lo impide, y sin test no se
    distingue de no tenerla."""
    src = cfg.normalize_source_text("el paper habla de una cosa completamente distinta")
    assert not cfg.quote_found("A … B", src)


def test_el_texto_FUENTE_no_pierde_lo_que_haya_entre_dos_signos_de_peso():
    """#336 — borrar el span `$…$` es correcto sobre la CITA (la nota re-marcó una fórmula que el
    `.txt` no puede tener igual, #287/#326) y no sobre la FUENTE: ahí los `$` son caracteres del
    documento —el copyright de Elsevier trae uno— y borrar entre dos se come el texto del medio.
    Medido: **10 de 155** `.txt` pierden texto, los tres peores el 37,9 %, 26,1 % y 22,5 %
    de una columna."""
    src = cfg.normalize_source_text(
        "0925-2312/98/$ - see front matter. The mixing matrix is estimated from the data, "
        "and the residual cost is $ 0.02 at convergence.")
    assert cfg.quote_found("The mixing matrix is estimated from the data", src)


_DOS_COLUMNAS = "\n".join([
    "We validated the fidelity of the shift by computing              The Whittle approximation applies only in the",
    "heliocentric velocities. We find that the temporal               case of noise-free models. In this work, by",
    "variance of the residual ACF is between 2.5 and 4.5              contrast, we take additive noise into account",
])
# vive entera en la columna 1, partida en tres líneas físicas
_CITA_COL1 = "the temporal variance of the residual ACF is between 2.5 and 4.5"
# frase que el paper NUNCA escribió: cruza la canaleta (fin col.1 + arranque col.2)
_EMPALME = "between 2.5 and 4.5 contrast, we take additive noise"


def test_deinterleave_columns_separa_las_dos_columnas():
    """`pdftotext -layout` conserva la página física: cada línea lleva col.1, la canaleta y col.2."""
    cols = cfg.deinterleave_columns(_DOS_COLUMNAS)
    assert len(cols) == 2
    assert "The Whittle" not in cols[0] and "The Whittle" in cols[1]


def test_deinterleave_de_una_columna_devuelve_un_solo_stream():
    """Un `.txt` de una columna da exactamente un stream: el llamador no ramifica por maqueta —que
    es el punto, porque si el PDF es a dos columnas no lo declara nadie."""
    assert cfg.deinterleave_columns("una linea sin canaleta\notra linea igual") == \
        ["una linea sin canaleta\notra linea igual"]


def test_source_texts_encuentra_la_cita_partida_en_tres_lineas_de_la_columna_1():
    """El texto plano **interleava** las dos columnas, así que ninguna cita de más de una línea
    física se encuentra. Buscando por columna, sí."""
    assert any(cfg.quote_found(_CITA_COL1, s) for s in cfg.source_texts(_DOS_COLUMNAS))
    assert not cfg.quote_found(_CITA_COL1, cfg.normalize_source_text(_DOS_COLUMNAS)), \
        "si el texto plano ya la encontrara, este test no probaría nada"


def test_source_texts_NO_valida_el_empalme_por_la_canaleta():
    """⛔ La dirección peligrosa (pineada desde #46): el texto plano contiene el empalme
    columna1→columna2, o sea una frase que no escribió nadie. Buscar ahí «por las dudas» la haría
    pasar como verbatim."""
    assert not any(cfg.quote_found(_EMPALME, s) for s in cfg.source_texts(_DOS_COLUMNAS))


def test_paridad_de_la_canaleta_entre_lib_config_y_measure_layout():
    """Regla de método 2: el que MIDE la maqueta y el que PARTE por ella comparten la definición, o
    divergen sin que nadie se entere."""
    import measure_layout as ml
    assert ml.CANALETA_MIN is cfg.CANALETA_MIN
    assert ml.GUTTER is cfg.GUTTER


# ── #332 · la canaleta es de la PÁGINA, no de cada línea ────────────────────────────────────────

# Página de dos columnas donde la canaleta se ANGOSTA en una línea (7 espacios: la columna
# izquierda casi llega al borde) y se ENSANCHA en otra. Renglón a renglón eso corre el índice de
# columna, así que la oración de la derecha —una sola, continua, partida en cuatro renglones
# físicos— cae en lecturas distintas. Es la forma exacta del caso medido en #332 sobre
# `1994SigPr..36..287C` (p. 296).
_PAGINA_CANALETA_IRREGULAR = "\n".join([
    "3. Optimization criteria                                    16 fails to separate them (this is the",
    "H(p) = - I(p),          where y = Q x.    (3.1)             same behaviour as for Gaussian compo-",
    "In practice the densities are not known, so that the        nents). However, as in Theorem 11, at",
    "criterion cannot be directly utilized. The aim of this      most one source component is allowed",
    "section is to express the contrast as a function of         to have a null cumulant.",
])
_ORACION_COL2 = ("same behaviour as for Gaussian components). However, as in Theorem 11, at most "
                 "one source component is allowed to have a null cumulant.")


def test_source_texts_no_parte_una_oracion_continua_entre_dos_lecturas():
    """#332 — la oración vive ENTERA en la columna derecha; el cortador la partía en dos lecturas.

    El paso 1 de `quote_verdict` (`en_su_txt`, #324) es el que evita el falso «mal atribuido», y
    desde #323 ese gate frena operaciones: una cita que SÍ está verbatim en el `.txt` de su fuente
    no puede salir «no está» porque el cortador la repartió."""
    lecturas = cfg.source_texts(_PAGINA_CANALETA_IRREGULAR)
    assert any(cfg.quote_found(_ORACION_COL2, s) for s in lecturas), \
        "la oración de la columna derecha no está entera en ninguna lectura"


def test_source_texts_da_UNA_lectura_POR_COLUMNA_FISICA():
    """#332 — una página impresa tiene una o dos columnas. Medido sobre una bóveda real: **148 de
    155** `.txt` devolvían más de dos lecturas, hasta **19**; con 19 lecturas sobre un paper de dos
    columnas, qué cita sobrevive es un accidente del corte."""
    assert len(cfg.source_texts(_PAGINA_CANALETA_IRREGULAR)) == 2


_PAGINA_CON_TITULO_Y_LINEA_CORTA = "\n".join([
    'THEOREM 14. For a standardized scalar variable Z, the negentropy is approximated by',
    'We start with the Edgeworth expansion of a         and the calculus of the mutual information',
    'density. A central limit theorem says that         of a standardized vector needs not only',
    'if z is a sum of m independent variables,          the marginal negentropy of each component',
    'then the cumulant of z is of order two.            but also the joint negentropy of it.',
    'Q.E.D.',
])


def test_la_linea_a_todo_ancho_no_se_corta_por_el_borde_de_la_pagina():
    """#332 — un enunciado, un título o un epígrafe cruza la página entera: en el borde de columna
    lleva TEXTO, no espacios. Cortarlo ahí partiría en dos una frase que la fuente escribió
    seguida; queda entero del lado izquierdo, que es donde vive el flujo que lo rodea."""
    titulo = "standardized scalar variable Z, the negentropy is approximated by"
    lecturas = cfg.source_texts(_PAGINA_CON_TITULO_Y_LINEA_CORTA)
    assert cfg.quote_found(titulo, lecturas[0])


def test_la_linea_mas_corta_que_el_borde_queda_entera_a_la_izquierda():
    """#332 — el último renglón de un párrafo no llega al borde de columna. No tiene mitad derecha:
    va entero a la izquierda (y leer más allá de su largo sería leer otra línea)."""
    lecturas = cfg.source_texts(_PAGINA_CON_TITULO_Y_LINEA_CORTA)
    assert "q.e.d." in lecturas[0]


def test_source_texts_de_un_txt_en_blanco_no_devuelve_una_lectura_vacia():
    """Una lectura vacía no es una lectura: `fulltext_readings` la pasaría como fuente y
    `quote_verdict` leería «hay `.txt` y la cita no está» donde lo cierto es *no evaluable* (D-43).
    Pasa de verdad: un escaneo cuyo OCR no sacó nada deja un `.txt` de puros espacios."""
    assert cfg.source_texts("   \n  \n") == []


def test_source_texts_deduplica_dos_lecturas_identicas():
    """El contrato dice «deduplicated»: dos columnas que normalizan igual son UNA lectura, o el
    llamador paga dos veces el mismo `quote_found` y cualquier conteo de lecturas miente."""
    assert len(cfg.source_texts("una frase repetida a los dos lados        "
                                "una frase repetida a los dos lados")) == 1


def test_source_texts_sigue_sin_validar_el_empalme_con_canaleta_irregular():
    """⛔ La dirección peligrosa de #46/#275 no se afloja para arreglar #332: el empalme
    columna1→columna2 sigue siendo una frase que no escribió nadie."""
    empalme = "the contrast as a function of to have a null cumulant"
    assert not any(cfg.quote_found(empalme, s)
                   for s in cfg.source_texts(_PAGINA_CANALETA_IRREGULAR))


# ── #270 · los ejes que una vista contesta ──────────────────────────────────────────────────────

_VISTA_EJES = """## Vista — tau Cet (2026-08-30)

**Ejes:**

- **rv:** una medición
- **activity:** otra

**Aporte:** algo

- **Hueco:** falta el PDF
"""


def test_view_axes_lee_los_bullets_del_bloque_de_ejes():
    assert cfg.view_axes(_VISTA_EJES) == {("tau Cet", ""): {"rv", "activity"}}


def test_view_axes_no_cuenta_los_bullets_de_fuera_del_bloque():
    """⛔ `- **Aporte:**` y `- **Hueco:**` no son ejes: una regex de bullets en negrita a secas los
    contaría y taparía justo el hueco que el detector de #270 busca."""
    assert "Hueco" not in cfg.view_axes(_VISTA_EJES)[("tau Cet", "")]


def test_el_bloque_de_ejes_CORTA_en_la_linea_en_blanco():
    """La mitad que `_VISTA_EJES` no distingue: ahí lo que sigue al blanco es prosa (`**Aporte:**`),
    que corta por ser no-bullet. Un BULLET después del blanco —`- **Hueco:**`, la forma real de una
    vista— sólo queda afuera porque el blanco ya cerró el bloque; sin eso entraba al conjunto de
    ejes y tapaba el hueco que el detector busca."""
    texto = "## Vista — X\n\n**Ejes:**\n\n- **rv:** una medición\n\n- **Hueco:** falta el PDF\n"
    assert cfg.view_axes(texto) == {("X", ""): {"rv"}}


def test_el_bloque_de_ejes_no_arranca_despues_de_prosa():
    """El simétrico: los blancos INICIALES se saltean (el escritor deja uno), pero una línea con
    texto antes del primer bullet cierra el bloque ahí — si no, cualquier bullet de más abajo se
    leería como eje de una sección que no los declaró."""
    texto = "## Vista — X\n\n**Ejes:**\n\ntexto suelto\n- **rv:** una medición\n"
    assert cfg.view_axes(texto) == {}


def test_view_axes_lee_cada_LENTE_por_separado():
    """#395c — la clave es el par `(sujeto, énfasis)`. Antes se tomaba el PRIMER `**Ejes:**` de la
    sección y se indexaba por sujeto, así que la segunda lectura del mismo sujeto (#239) se
    comparaba contra los ejes de la primera: medido, 13 vistas reportadas como «no contesta NINGUNO
    de sus 7 ejes» con los siete contestados ahí mismo, en su `### Lente — …`."""
    texto = ("## Vista — tau Cet\n\n**Ejes:**\n\n- **rv:** algo\n- **activity:** _(sin datos)_\n"
             "\n### Lente — cuantas componentes\n\n**Ejes:**\n\n- **whitening:** otra cosa\n")
    assert cfg.view_axes(texto) == {("tau Cet", ""): {"rv", "activity"},
                                    ("tau Cet", "cuantas componentes"): {"whitening"}}


def test_view_lens_spans_marca_el_limite_de_cada_lectura():
    """El mismo corte, con offsets, para quien tiene que ESCRIBIR adentro de una lectura (#395b):
    un backfill que no viera el límite pegaría los ejes de una lente en la sub-sección de la otra."""
    texto = ("## Vista — X (2026-08-30)\n\n**Ejes:**\n\n- **rv:** a\n"
             "\n### Lente — L2\n\n**Ejes:**\n\n- **w:** b\n")
    spans = cfg.view_lens_spans(texto)
    # El sufijo que arranca con puntuación se recorta (AUD-178): el sujeto es `X`, no `X (2026-…)`.
    assert [(s, e) for s, e, _i, _f in spans] == [("X", ""), ("X", "L2")]
    assert texto[spans[1][2]:spans[1][3]].startswith("### Lente — L2")
    assert "rv" not in texto[spans[1][2]:spans[1][3]]


def test_view_axes_ignora_un_encabezado_dentro_de_un_fence():
    """Paridad con AUD-178: un `## Vista` dentro de un ```fence``` es un EJEMPLO de la doc, no una
    sección — y contarlo produce hallazgos sobre notas correctas."""
    assert cfg.view_axes("```\n" + _VISTA_EJES + "```\n") == {}


def test_view_axes_sin_bloque_de_ejes_no_inventa_la_clave():
    """Una vista sin `**Ejes:**` no contesta ninguno: la clave ausente y el conjunto vacío se leen
    distinto aguas arriba (sin lente declarada no hay nada que comparar)."""
    assert cfg.view_axes("## Vista — X\n\n**Aporte:** algo\n") == {}


# ── #271 · el markup de catálogo dentro de la capa auditable ─────────────────────────────────────

def test_clean_catalog_markup_saca_astrobj_y_el_link():
    """#271 — medido en una bóveda real: 249 ocurrencias en 42 notas dentro de `## Abstract`, y
    111 de ellas fuera de las seis etiquetas que la lista original cubría. `<ASTROBJ>` deja el
    nombre del objeto **invisible** en un renderer que no escapa, y `<A href>` convierte una copia
    que se promete verbatim en un **link vivo**."""
    sucio = 'R<SUB>p</SUB> de <ASTROBJ>HD 40307</ASTROBJ> en <A href="http://cds">la tabla</A>'
    assert cfg.clean_catalog_markup(sucio) == "Rp de HD 40307 en la tabla"
    assert cfg.clean_catalog_markup("<inline-formula><mml:math>x</mml:math></inline-formula>") == "x"
    assert cfg.clean_catalog_markup("un<P />parrafo<BR />cortado") == "unparrafocortado"


def test_no_convierte_una_entidad_escapada_en_markup_vivo():
    """⛔ El ORDEN: con `html.unescape` primero y una sola pasada, un `&lt;P /&gt;` que el catálogo
    mandó **escapado** se convertía en un `<P />` vivo — la función fabricaba el markup que existe
    para sacar."""
    assert cfg.clean_catalog_markup("&lt;P /&gt;dos parrafos") == "dos parrafos"
    assert cfg.clean_catalog_markup("Ca II H&amp;K") == "Ca II H&K", "las entidades normales sí se desescapan"


def test_no_se_come_texto_que_no_es_markup():
    """La dirección peligrosa: sin el borde de nombre de etiqueta, `A` matchea el arranque de
    `<Author>` y la limpieza borra texto real de un abstract."""
    assert cfg.clean_catalog_markup("texto <Author> que no es markup") == "texto <Author> que no es markup"
    assert cfg.clean_catalog_markup("a < b y c > d") == "a < b y c > d"


def test_los_tres_backends_limpian_el_markup_de_catalogo():
    """Los tres prometen el MISMO schema de registro (`tests/test_backends_schema.py`), así que la
    limpieza no puede vivir en uno solo: hasta 1.118.x sólo la hacía `query_ads`."""
    import openalex
    import search_arxiv
    for mod in (openalex, search_arxiv):
        fuente = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        assert "clean_catalog_markup" in fuente, mod.__name__


# ── #245 · el vocabulario canónico de métodos (stems + aliases) ─────────────────────────────────

def _concepto(toy_vault, stem, aliases=()):
    return mk_note(cfg.CONCEPTS / "methods", stem,
                   {"tags": ["concept"], "name": stem, "aliases": list(aliases)}, f"# {stem}\n")


def test_el_indice_resuelve_un_metodo_por_su_sinonimo(toy_vault):
    """#245 — el nombre canónico de un método ES el stem de su nota y `aliases` es la tabla de
    sinónimos que el schema ya pide; nadie la leía, así que `bisector span` y `bis` contaban como
    dos métodos y el backlog reportaba dos deudas donde hay una."""
    _concepto(toy_vault, "bis", ["bisector span", "bisector velocity span"])
    idx = cfg.concept_alias_index()
    assert cfg.method_target("Bisector Span", idx) == "bis"
    assert cfg.method_target("bis", idx) == "bis"
    assert cfg.method_target("algo que nadie declaró", idx) is None


def test_el_stem_gana_sobre_un_alias_ajeno(toy_vault):
    """⛔ Si `pca.md` existe y otra nota reclama `pca` como alias, el destino es `pca`: un índice que
    eligiera por orden de glob no sería determinista."""
    _concepto(toy_vault, "pca")
    _concepto(toy_vault, "ica-ruido", ["pca"])
    assert cfg.method_target("PCA") == "pca"


def test_el_universo_declarado_se_indexa_y_se_consulta_por_clave(toy_vault):
    """#348 — `name_index` + `declared_name` son la ÚNICA implementación de «¿este nombre denota un
    concepto/tema declarado?». La pregunta estaba re-implementada por string crudo tres veces en
    `lint.py`, y una de ellas —`thesis_links` sin página destino— es BLOQUEANTE: `PCA` contra la
    nota `pca.md` salía colgante mientras `theme_membership` decía que es el mismo concepto.

    Los tres invariantes del par, cada uno con su caso simétrico: se compara por clave, se devuelve
    el nombre DECLARADO (no la grafía del reclamo), y el nombre vacío no denota nada — dejarlo entrar
    haría que `""` matcheara todo reclamo en blanco."""
    idx = cfg.name_index(["pca", "Bisector Span", "", "   "])
    assert cfg.declared_name("PCA", idx) == "pca", "se compara por `method_key`, no por el string"
    assert cfg.declared_name("bisector-span", idx) == "Bisector Span", \
        "devuelve el nombre DECLARADO, no la grafía con la que se preguntó"
    assert cfg.declared_name("wPCA", idx) is None, "`wpca` no es `pca`: el detector no es siempre-sí"
    assert cfg.declared_name("", idx) is None and "" not in idx, "el nombre vacío no denota nada"


def test_el_indice_de_nombres_resuelve_una_colision_en_orden_ESTABLE(toy_vault):
    """Dos grafías que colapsan en la misma clave tienen que resolver siempre igual: construido
    sobre un `set`, el ganador dependía del orden de iteración y el universo dejaba de ser
    auditable."""
    assert cfg.name_index({"PCA", "pca", "p.c.a."})["pca"] == \
        cfg.name_index({"pca", "p.c.a.", "PCA"})["pca"] == "PCA", \
        "el primero en orden alfabético, no el primero que salga del set"


def test_la_colision_alias_alias_se_REPORTA_no_se_resuelve(toy_vault):
    """Cuál concepto denota un nombre es curación: elegir en silencio decide por el usuario."""
    _concepto(toy_vault, "aaa", ["señal común"])
    _concepto(toy_vault, "bbb", ["señal común"])
    colisiones = cfg.alias_collisions()
    assert len(colisiones) == 1 and sorted(colisiones[0][1]) == ["aaa", "bbb"]


def test_indicator_key_saca_la_glosa_final_y_nada_mas():
    """#250 — `activity_indicators_expected` es prosa para un humano, así que comparar crudo hace
    dangling al 100 % y el backlog nace todo falso. ⛔ Sólo el paréntesis FINAL, y sólo al comparar:
    el campo nunca se reescribe."""
    assert cfg.indicator_key("BIS (bisector de la CCF)") == "bis"
    assert cfg.indicator_key("S-index (Ca II H&K)") == "s-index"
    assert cfg.indicator_key("FWHM de la CCF") == cfg.method_key("FWHM de la CCF"), \
        "sin paréntesis se comporta como `method_key`"
    assert cfg.indicator_key("índice (a) de (b)") == cfg.method_key("índice (a) de"), \
        "sólo el paréntesis final: el del medio puede ser parte del nombre"


def test_vista_key_distingue_dos_lecturas_del_mismo_sujeto():
    """#239 — la identidad de una vista es `(sujeto, enfasis)`. Con el sujeto a secas, la segunda
    lectura con otra lente no tenía dónde ir y el cosechador pisaba la primera en silencio."""
    a = {"sujeto": "tau Cet", "tipo": "star"}
    b = {"sujeto": "tau Cet", "tipo": "star", "enfasis": "ruido"}
    assert cfg.vista_key(a) != cfg.vista_key(b)
    assert cfg.vista_key(a) == ("tau Cet", "")
    assert cfg.vista_key({"sujeto": " tau Cet ", "enfasis": " ruido "}) == cfg.vista_key(b)


def test_el_enfasis_vacio_no_crea_una_lectura_distinta():
    """Presente y vacío es «no consta», no otra lente: si no, dos entradas que son la MISMA lectura
    convivirían y el roll-up contaría dos."""
    v = cfg.load_vistas({"vistas": [{"sujeto": "X", "tipo": "star", "enfasis": ""}]})[0]
    assert "enfasis" not in v
    assert cfg.vista_key(v) == ("X", "")


# ── D-19 · el bibcode que ya es alias de otra nota no se vuelve a bajar ──────────────────────────

def test_alias_bibcodes_devuelve_los_declarados_en_versions(toy_vault):
    """D-19 — el preprint y el publicado son dos bibcodes del MISMO trabajo. Nada se lo decía a los
    fetchers, así que después de un `--rename-paper` la próxima corrida re-bajaba el preprint y el
    lint reportaba el par PDF+`.txt` como artefacto colgado **para siempre**: no tiene nota, y no
    puede tenerla (#229 bloquea la segunda). Medido en una bóveda real."""
    mk_note(cfg.PAPERS, "2026RASTI...5ag038F",
            {"bibcode": "2026RASTI...5ag038F", "tags": ["paper"], "stars": ["X"],
             "versions": [{"bibcode": "2026arXiv260528635F", "tipo": "eprint"}]}, "# p\n")
    assert cfg.alias_bibcodes() == {"2026arXiv260528635F"}


def test_un_alias_que_TIENE_su_propia_nota_no_se_saltea(toy_vault):
    """⚠ Ese caso es el BLOQUEANTE de #229 (o es alias y no debe haber nota, o es otro trabajo y no
    va en `versions[]`): un fetcher que lo saltee en silencio lo taparía."""
    mk_note(cfg.PAPERS, "2026RASTI...5ag038F",
            {"bibcode": "2026RASTI...5ag038F", "tags": ["paper"], "stars": ["X"],
             "versions": [{"bibcode": "2026arXiv260528635F"}]}, "# p\n")
    mk_note(cfg.PAPERS, "2026arXiv260528635F",
            {"bibcode": "2026arXiv260528635F", "tags": ["paper"], "stars": ["X"]}, "# p\n")
    assert cfg.alias_bibcodes() == set()


def test_la_cita_con_matematica_en_el_medio_se_busca_de_las_DOS_formas():
    """#287 — `normalize_quote` **borra** el span `$…$` (correcto cuando la nota re-marcó una
    fórmula que el `.txt` no puede tener igual), pero eso convierte «of either $A$ and $S$» en «of
    either and», que no está en ninguna fuente **aunque el paper diga exactamente esa frase** con
    las letras sueltas. Medido al desactivar la exención de #275 sobre una bóveda real."""
    fuente = cfg.normalize_source_text(
        "…without any additional prior knowledge of either A and S. The estimation…")
    assert cfg.quote_found("without any additional prior knowledge of either $A$ and $S$", fuente)


def test_las_dos_lecturas_no_aflojan_el_chequeo():
    """⛔ La dirección peligrosa: las palabras siguen teniendo que estar en la fuente. Lo único que
    cambia es contra cuál de los dos markups de las MISMAS palabras se compara."""
    fuente = cfg.normalize_source_text("el paper habla de otra cosa completamente distinta")
    assert not cfg.quote_found("without any additional prior knowledge of either $A$ and $S$", fuente)
    assert cfg.quote_variants("sin matemática ninguna acá") == ["sin matemática ninguna acá"], \
        "sin `$…$` hay UNA sola lectura: no se duplica trabajo"


def test_quote_found_degraded_clasifica_la_cita_que_el_txt_parte():
    """#288 — números de línea de un preprint a dos columnas metidos EN MEDIO de la frase. La
    fuente dice la cita; el `.txt` la parte. Es otro trabajo y otra severidad: en la nota no hay
    nada que corregir."""
    src = cfg.normalize_source_text(
        "since wpca constructs orthogonal components by 87.0 design, real-world systematics")
    q = "since wPCA constructs orthogonal components by design, real-world systematics"
    assert not cfg.quote_found(q, src), "el chequeo estricto NO se afloja"
    assert cfg.quote_found_degraded(q, src)


def test_quote_found_degraded_no_acepta_una_cita_ajena():
    """⛔ Sólo CLASIFICA un hallazgo que ya falló: sacar números de los dos lados es exactamente lo
    que haría matchear un número equivocado, así que nunca puede aceptar por su cuenta."""
    src = cfg.normalize_source_text("el paper habla de otra cosa completamente distinta")
    assert not cfg.quote_found_degraded("since wPCA constructs orthogonal components", src)


# ── #291 · particionar una faceta por alternación de NIVEL 0 ─────────────────
def test_la_particion_de_la_faceta_respeta_los_grupos():
    """⚠ Medido al escribir #291: partir con `split('|')` corta adentro de los grupos —
    `line-by-line` aparece dos veces porque vive en dos grupos distintos, se lee como duplicada, y
    deduplicar sobre eso rompe `(telluric|line-by-line|stellar activity)`: el diff de
    re-clasificación da **−1** (se pierde un paper real del core). El chequeo que existe para
    cuidar la lente no puede ser el que la rompe."""
    patron = r"(telluric|line-by-line|stellar activity)|non-?gaussianity matrix"
    assert cfg.facet_alternatives(patron) == ["(telluric|line-by-line|stellar activity)",
                                              "non-?gaussianity matrix"]
    assert cfg.facet_duplicated_alternatives(
        r"(a|line-by-line)|(b|line-by-line)") == [], "los grupos NO son alternativas de nivel 0"
    assert cfg.facet_alternatives(r"a\|b") == [r"a\|b"], "el `|` escapado es un literal"
    assert cfg.facet_alternatives(r"[a|b]c") == [r"[a|b]c"], "adentro de una clase tampoco parte"
    assert cfg.facet_alternatives(r"[ab]x|c") == [r"[ab]x", "c"], "y la clase CIERRA"
    assert cfg.facet_alternatives("") == [] and cfg.facet_alternatives(None) == []


def test_la_alternativa_muerta_se_reporta_y_la_viva_no():
    """La dirección simétrica de #236: una alternativa que no matchea nada no se ve nunca — la
    faceta compila, el corte da un número plausible y el término no participa."""
    fuera = dict(cfg.facet_dead_alternatives("negentropy|non-?gaussianity matrix",
                                             ["bla negentropy y non-gaussianity bla"]))
    assert "non-?gaussianity matrix" in fuera and "no matchea" in fuera["non-?gaussianity matrix"]
    assert "negentropy" not in fuera, "la alternativa VIVA no es un hallazgo"


def test_alternativa_que_no_compila_sale_como_no_evaluada():
    """D-43 — un `(0)` que nadie midió se lee como veredicto. Si una alternativa no compila por
    separado, eso se DICE: no se saltea en silencio."""
    fuera = dict(cfg.facet_dead_alternatives("buena|(mala", ["buena"]))
    assert "no se pudo evaluar" in fuera["(mala"]


def test_la_duplicada_se_nombra_UNA_vez():
    """Tres copias de la misma alternativa son UN hallazgo: repetir la fila por cada copia
    convierte una señal barata en ruido."""
    assert cfg.facet_duplicated_alternatives("a|negentropy|b|negentropy|negentropy") == ["negentropy"]
    assert cfg.facet_duplicated_alternatives("a|A") == ["A"], "la faceta se compila con re.I"
    assert cfg.facet_duplicated_alternatives("a|b") == []


# ── #297 · la línea del reuso D-18 dice QUÉ NO SE CHEQUEÓ ────────────────────
def test_la_linea_del_reuso_declara_lo_que_no_miro(toy_vault, tmp_path):
    """#297 — `↺ copiado sin ir a la red` se lee como «nos ahorramos una descarga»; lo que también
    pasó es que un sujeto nuevo heredó un artefacto cuya antigüedad nadie chequeó. INV-87 aplicado
    al reuso: lo que **no** se miró se declara."""
    (cfg.PDFS / "ica").mkdir(parents=True, exist_ok=True)
    origen = cfg.PDFS / "ica" / "2002Cardoso.pdf"
    origen.write_bytes(b"%PDF-1.4\n")
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2002Cardoso.md").write_text(
        "---\nbibcode: 2002Cardoso\npdf_source: eprint\n---\n\n## Abstract\n\nx\n", encoding="utf-8")
    linea = cfg.reuse_note("2002Cardoso", origen)
    assert "ya estaba bajo `ica`" in linea and "D-18" in linea
    assert "pdf_source: eprint" in linea
    assert "no se chequeó si hay versión publicada" in linea


def test_la_linea_del_reuso_no_inventa_la_procedencia(toy_vault):
    """Sin nota (o sin `pdf_source`), la línea dice **no consta** en vez de callar: «desconocido» y
    «eprint» mandan a leer la nota de maneras opuestas (#57)."""
    (cfg.PDFS / "ica").mkdir(parents=True, exist_ok=True)
    origen = cfg.PDFS / "ica" / "2020Sin.pdf"
    origen.write_bytes(b"%PDF-1.4\n")
    assert "pdf_source: no consta" in cfg.reuse_note("2020Sin", origen)


# ── #305/#307 · dos resoluciones que tienen que ser UNA ─────────────────────
def test_pdf_slug_resuelve_bajo_cualquier_slug_con_precedencia(toy_vault):
    """#305 — las dos mitades de #207 buscaban el PDF distinto: el prompt sólo bajo el slug del
    sujeto, el cosechador bajo todos. Resultado: el prompt mandaba declarar `fuente: abstract` sobre
    papers que SÍ están en disco (7 de 31 medidos, el núcleo fundacional de un tema y dos libros).
    Precedencia declarada, como `artefacto_en_otro_slug`: el preferido primero, después el menor."""
    for slug in ("zeta", "ica"):
        (cfg.PDFS / slug).mkdir(parents=True, exist_ok=True)
        (cfg.PDFS / slug / "2002Cardoso.pdf").write_bytes(b"%PDF")
    assert cfg.pdf_slug("2002Cardoso") == "ica", "sin preferencia, el menor: determinista"
    assert cfg.pdf_slug("2002Cardoso", "zeta") == "zeta", "el preferido, si está"
    assert cfg.pdf_slug("2002Cardoso", "no_existe") == "ica", "cae al menor, no a None"
    assert cfg.pdf_slug("2020nada") is None


def test_theme_axes_tiene_los_tres_estados(toy_vault):
    """#307 / D-43 — sin declarar hereda los ejes globales; declarado son ésos; declarado **vacío**
    es la decisión explícita de no preguntar ejes, que no se lee igual que no declarar nada."""
    assert cfg.theme_axes({"title": "T"}) is None
    assert cfg.theme_axes({"title": "T", "ejes": ["a", " b "]}) == ["a", "b"]
    assert cfg.theme_axes({"title": "T", "ejes": []}) == []
    assert cfg.theme_axes({"title": "T", "ejes": None}) == []
    assert cfg.theme_axes(None) is None


# ── #309 · el marcador ESCAPADO no abre nada ────────────────────────────────
def test_unclosed_markers_honra_el_escape():
    """#309 — `\\$` es el arreglo CORRECTO de un dólar literal (Obsidian lo renderiza y no abre
    matemática) y el detector lo seguía contando, así que el operador elegía entre un bug de
    renderizado real, un backlog permanente, o borrar el carácter de una transcripción verbatim. El
    caso real: la línea «1070-9908/04$20.00 © 2004 IEEE» transcrita de un pie de página para probar
    que el PDF es la versión publicada. Cuarta vez de la misma ceguera al markdown (#168/#276/#283)."""
    assert list(cfg.unclosed_markers(r"precio de 04\$20.00 pesos")) == []
    assert list(cfg.unclosed_markers(r"texto con $x$ y precio 04\$20.00")) == []
    assert list(cfg.unclosed_markers(r"un \` backtick literal")) == []
    # dos backslashes escapan al BACKSLASH, no al marcador: ahí el `$` sí abre
    doble = "dos backslashes " + chr(92) * 2 + " y un $ suelto"
    assert [m for _l, m, _i in cfg.unclosed_markers(doble)] == ["$"]
    # y el control: un `$` de verdad sin cerrar se sigue reportando
    assert [m for _l, m, _i in cfg.unclosed_markers("una $formula sin cerrar")] == ["$"]


def test_unclosed_markers_nombra_la_LINEA_del_impar():
    """El reporte apuntaba al arranque del párrafo, no a la línea culpable: con párrafos de seis
    bullets, es mandar al operador a buscar a mano lo que el detector ya sabe."""
    parrafo = "- uno con $x$\n- dos con $y$\n- tres con un $ suelto\n- cuatro"
    assert list(cfg.unclosed_markers(parrafo)) == [(1, "$", 3)]


# ── #349 · el duplicado se cuenta DENTRO de su vista ────────────────────────
#: Un párrafo largo, para pasar `_DUP_MIN` sin depender de la prosa que lo rodea.
_LARGO = ("Que el defecto sea estructural no implica que el método lo arregle en datos reales, y el "
          "único paper del corpus que lo mide contra verdad conocida encuentra que ")


def test_duplicate_paragraphs_cada_vista_es_su_propio_ambito():
    """#349 — con varias vistas (#239) cada una estampa la misma línea estructural (el eje que la
    lente preguntó y la fuente calló, la salvedad chequeada) y son idénticas **por construcción**:
    medido en una bóveda real, 7 hallazgos y los 7 falsos. `## Vista` y `### Lente` son ámbitos."""
    dos_vistas = (f"## Vista — tau Cet\n\n{_LARGO}sí.\n\n"
                  f"## Vista — s_index\n\n{_LARGO}sí.\n")
    assert cfg.duplicate_paragraphs(dos_vistas) == []
    # ⚠ y la segunda lectura del MISMO sujeto tampoco se compara contra la primera
    con_lente = (f"## Vista — tau Cet\n\n{_LARGO}sí.\n\n"
                 f"### Lente — cumulantes\n\n{_LARGO}sí.\n")
    assert cfg.duplicate_paragraphs(con_lente) == []


def test_duplicate_paragraphs_dentro_del_mismo_ambito_sigue_siendo_hallazgo():
    """#349, la mitad que no se afloja: acotar el ámbito no puede apagar el caso de #227. Vale
    dentro de una vista y, sin ninguna vista, sobre la nota entera — que es donde vivía el empalme
    medido (dos copias con el párrafo introductorio de OTRA sección en el medio)."""
    dentro = f"## Vista — tau Cet\n\n{_LARGO}sí.\n\notra cosa\n\n{_LARGO}no.\n"
    assert [ln for ln, _t in cfg.duplicate_paragraphs(dentro)] == [7]
    entre_secciones = f"## Síntesis\n\n{_LARGO}sí.\n\n## Huecos\n\nintro\n\n{_LARGO}no.\n"
    assert [ln for ln, _t in cfg.duplicate_paragraphs(entre_secciones)] == [9]
    # y un `###` FUERA de una vista es prosa normal: no abre ámbito, así que un duplicado que lo
    # cruza se sigue viendo. Sin esta mitad, «`###` siempre abre ámbito» pasa los otros asserts.
    fuera = f"{_LARGO}sí.\n\n### Un subtítulo\n\n{_LARGO}no.\n"
    assert [ln for ln, _t in cfg.duplicate_paragraphs(fuera)] == [5]


def test_duplicate_paragraphs_no_mira_dentro_de_un_fence():
    """#227 — un bloque ```…``` repite texto a propósito (dos ejemplos de la misma forma) y no es
    un empalme. Sin la guarda, el ejemplo duplicado de la doc entra a la categoría."""
    fence = f"{_LARGO}sí.\n\n```\n\n{_LARGO}sí.\n\n```\n"
    assert cfg.duplicate_paragraphs(fence) == []


def test_extraction_texts_memoiza_por_boveda(toy_vault, monkeypatch):
    """#320 — misma asimetría que #275 arregló en `_source_readings`: el chequeo corre **por cita**,
    así que sin caché el mismo JSON de ~25 KB se lee, recorre y normaliza decenas de veces.
    ⚠ La clave incluye el directorio: `EXTRACCION` se re-apunta, y una caché por bibcode pelado
    devolvería la extracción de otra bóveda."""
    (cfg.EXTRACCION / "ica").mkdir(parents=True, exist_ok=True)
    f = cfg.EXTRACCION / "ica" / "2013Voss.json"
    f.write_text('{"bibcode": "2013Voss", "ground_truth": [{"valor": "la frase de la fuente"}]}',
                 encoding="utf-8")
    lecturas = []
    real = pathlib.Path.read_text

    def contando(self, *a, **k):
        if self.suffix == ".json":
            lecturas.append(self.name)
        return real(self, *a, **k)
    monkeypatch.setattr(pathlib.Path, "read_text", contando)
    assert "la frase de la fuente" in cfg.extraction_texts("2013Voss")[0]
    cfg.extraction_texts("2013Voss")
    cfg.extraction_texts("2013Voss")
    assert lecturas.count("2013Voss.json") == 1, "el JSON se lee UNA vez por corrida"


def test_una_cita_con_MATEMATICA_se_encuentra_en_un_texto_normalizado_como_FUENTE():
    """#326/#373 — las dos normalizaciones son asimétricas y no había variante que las uniera: la de
    la CITA borra el span `$…$` y la de la FUENTE lo conserva desarmado (`$mathbf{a}^{1}$`). Así que
    una cita cuyo contenido es sobre todo matemática no se encontraba **nunca** en su propia fuente,
    aunque estuviera ahí carácter por carácter.

    Estaba latente: hasta #373 esas citas vivían en las `## Vista`, que ninguna capa miraba. Al
    entrar a la población el defecto salió como **7 hallazgos, los 7 falsos** sobre una bóveda real,
    los 7 «el arranque coincide y la cola diverge» contra su propia extracción — y un falso positivo
    acá **frena operaciones** (#323)."""
    q = r"one has $\mathbf{A}^{-1} = \mathbf{A}^{T}(\mathbf{I}-\Sigma)^{-1}$"
    fuente = cfg.normalize_source_text("Tras esferizar los datos «" + q + "», que en el caso ...")
    assert cfg.quote_found(q, fuente), "la cita está en su fuente, carácter por carácter"


# ── #364/#388 · bajar el RUIDO de la acusación del `.txt` sin bajar su sensibilidad ──

def test_las_comillas_TeX_no_son_una_diferencia_de_PALABRAS():
    """#364/#388 — el PDF compone las comillas dobles con **dos simples** (`\u2018\u2018…\u2019\u2019`, el modo TeX) y
    la extracción escribe `"`. Cero diferencia de palabras, y sin embargo la acusación salía: una
    lectura de PDF por hallazgo, sobre el aviso que existe justamente para cuando el determinista le
    GANA al LLM. Plegar los glifos en los dos lados no puede tapar una alteración de palabras."""
    assert cfg.normalize_quote("dice \u2018\u2018tight\u2019\u2019 cluster") == cfg.normalize_quote('dice "tight" cluster')


def test_las_ligaduras_no_son_una_diferencia_de_PALABRAS():
    """La otra mitad barata: `pdftotext` deja la ligadura tipográfica (`\ufb01`, `\ufb02`) como UN carácter,
    y la extracción escribe las dos letras. Es un carácter, no un borde de palabra, así que la
    guarda de #333 no lo veía."""
    assert cfg.normalize_source_text("the \ufb01nal \ufb02ux") == cfg.normalize_source_text("the final flux")


def test_el_EMPALME_de_columnas_no_es_una_contradiccion():
    """#388 — el caso literal medido: `pdftotext` intercala la columna de referencias renglón por
    renglón, y lo que intercala es texto real que **arranca en un borde de palabra perfecto**. Ahí
    el argumento de #333 se rompe: la guarda existe porque `pdftotext` rompe PALABRAS, y el empalme
    no rompe ninguna.

    El discriminante es que la cita **REANUDA** más adelante en la misma fuente: si el `.txt` trae
    la continuación, no está diciendo otra cosa — está diciendo lo mismo con algo metido en el
    medio. En el caso verdadero de esa misma medición la cola **seguía la misma frase** y no
    reanuda, así que el filtro no lo toca."""
    txt = cfg.normalize_source_text(
        "Speed is, however, a crucial factor because we have to run the ICA "
        "Duann, J.-R., Jung, T.-P., Sejnowski, T., Makeig, S., 2003. What is consistent in ICA "
        "algorithm many times, which is why FastICA is very suitable for this purpose.")
    assert cfg.txt_accuses(
        "Speed is, however, a crucial factor because we have to run the ICA algorithm many times, "
        "which is why FastICA is very suitable for this purpose.", [txt]) is None


def test_una_SONDA_corta_no_alcanza_para_perdonar_el_empalme():
    """El recorte del filtro de arriba: la reanudación se prueba con la COLA de la cita, y una cola
    corta matchea por casualidad —cualquier `.txt` largo contiene «of the data» en algún lado—. Con
    la sonda por debajo de `CITA_COLA_MIN` el filtro no opina y la acusación queda en pie, que es la
    dirección segura: sobre-reportar, nunca perdonar de más."""
    txt = cfg.normalize_source_text(
        "the reproducibility index is computed over the whole set of runs and then a completely "
        "different sentence follows here for a while. data of it appears again later on.")
    a = cfg.txt_accuses(
        "the reproducibility index is computed over the whole set of runs and data of it", [txt])
    assert a is not None, "la cola («data of it», 10 caracteres) no prueba reanudación"


def test_el_borde_de_palabra_sigue_acusando_lo_que_DEBE():
    """⛔ El control que impide aflojar de más: el verdadero positivo medido en `icasso` —la
    extracción escribió «power line interferences» donde el PDF dice «power line artifact», mezclando
    dos frases vecinas de la misma columna— tiene que seguir acusando."""
    txt = cfg.normalize_source_text(
        "the signal clearly corresponds to a 150 Hz harmonics due to the power line artifact. Here "
        "we encounter again the previously discussed problem of the number of components")
    a = cfg.txt_accuses("clearly corresponds to a 150 Hz harmonics due to the power line interferences", [txt])
    assert a is not None and "artifact" in a["cola_txt"]


# ── #371 · el archivo de una SEGUNDA lente no puede ser el de la primera ──

def test_lens_filename_sin_lente_es_el_canonico():
    """El recorte: la primera lectura sigue escribiendo `<bibcode>.json`. Un nombre distinto ahí
    movería todo el corpus existente."""
    assert cfg.lens_filename("2013Voss") == "2013Voss.json"
    assert cfg.lens_filename("2013Voss", "   ") == "2013Voss.json"


def test_lens_filename_con_lente_NO_pisa_la_primera():
    """#371 — el prompt decía «la vista anterior no se pisa» y mandaba escribir al archivo de la
    primera lente. Lo que #239 protege es la vista en la NOTA; la extracción quedaba desprotegida, y
    es el artefacto que #311 declara versionado y **no regenerable**."""
    assert cfg.lens_filename("2013Voss", "orden") == "2013Voss__orden.json"
    assert cfg.lens_filename("2013Voss", "orden") != cfg.lens_filename("2013Voss")


def test_lens_filename_normaliza_la_lente_para_ser_un_ARCHIVO():
    """La lente es texto libre del operador y termina en un nombre de archivo: separadores, acentos
    y mayúsculas no pueden viajar. Comparte la transformación con `method_key` y NO su regla —
    aquélla normaliza sólo al comparar, ésta normaliza justamente para escribir."""
    n = cfg.lens_filename("2013Voss", "¿Cuántas componentes? (orden/PCA)")
    assert n == "2013Voss__cuantas-componentes-orden-pca.json"
    assert "/" not in n and n.isascii()


# ── #324 · la regla compartida: `quote_verdict` y su lector de `.txt` ──────────────────────────────
# Viven acá, y no sólo en los tests de sus dos llamadores, porque la función ES el contrato: hasta
# 1.134.0 la misma regla estaba implementada dos veces (lint y contrast) y ya divergía —13 contra 12
# sobre el mismo corpus el mismo día—, con el número duplicado y un comentario que declaraba que
# tenían que coincidir. Regla de método nº 2.

def _extr_324(bib: str, valor: str, slug: str = "tema"):
    import json
    (cfg.EXTRACCION / slug).mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / slug / f"{bib}.json").write_text(
        json.dumps({"bibcode": bib, "ground_truth": [{"que": "x", "valor": valor}]}), encoding="utf-8")


def _txt_324(bib: str, texto: str, slug: str = "tema"):
    (cfg.FULLTEXT / slug).mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / slug / f"{bib}.txt").write_text(texto, encoding="utf-8")


CITA_324 = "the whitening step is not enough to identify the model"


def test_fulltext_readings_sin_txt_devuelve_vacio_no_una_negacion(toy_vault):
    """Sin `.txt` en disco la respuesta es *no evaluable*, nunca «la cita no está» (D-43)."""
    assert cfg.fulltext_readings("2013SinTxt") == []
    _txt_324("2013Voss", f"prosa. {CITA_324}. más prosa.")
    assert any(CITA_324 in t for t in cfg.fulltext_readings("2013Voss"))


def test_quote_verdict_la_cita_en_SU_txt_no_dice_nada(toy_vault):
    """#324, el paso 1 y el falso positivo medido: la cita está verbatim en el `.txt` del paper que
    la nota cita, su extracción —selectiva (#188)— no la transcribió, y la de otro paper sí. El
    `.txt` es un índice degradado (#205), no un mal testigo: encontrar la cadena ahí prueba que la
    frase es de ESE paper, y no hay nada que reportar."""
    _txt_324("citado", f"prosa. {CITA_324}. más prosa.")
    _extr_324("citado", "otra cosa que este paper aporta")
    _extr_324("ajeno", CITA_324)
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado", "ajeno"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "en_su_txt"


def test_quote_verdict_la_extraccion_la_dice_y_el_txt_no(toy_vault):
    """#315 — la extracción se hizo leyendo el PDF: si la cita está ahí, la nota es fiel y el que
    falló es el índice."""
    _txt_324("citado", "un `.txt` que perdió la frase")
    _extr_324("citado", CITA_324)
    ver, det = cfg.quote_verdict(CITA_324, ["citado"], {"citado"},
                                 {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado" and det["en_extraccion"] == ["citado"]


def test_quote_verdict_atribucion_movida_BLOQUEA(toy_vault):
    """La mitad más frecuente de los verdaderos positivos (6 de 12): la frase está verbatim en la
    extracción de otro bibcode de la misma nota, y en el `.txt` de su fuente no está."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_324("citado", "otra cosa")
    _extr_324("ajeno", CITA_324)
    ver, det = cfg.quote_verdict(CITA_324, ["citado"], {"citado", "ajeno"},
                                 {"citado": cfg.fulltext_readings("citado")})
    assert ver == "alterada" and det["otro_bib"] == ["ajeno"]


def test_quote_verdict_cola_alterada_BLOQUEA(toy_vault):
    """La otra mitad (6 de 12): coincide un prefijo largo y diverge la cola — el patrón de #314."""
    largo = CITA_324 + " under gaussian noise of known covariance"
    _txt_324("citado", "prosa que no dice la cita")
    _extr_324("citado", largo)
    ver, det = cfg.quote_verdict(largo[:len(largo) - 20] + " y una cola inventada",
                                 ["citado"], {"citado"},
                                 {"citado": cfg.fulltext_readings("citado")})
    assert ver == "alterada" and det["prefijo"] and not det["otro_bib"]


def test_quote_verdict_el_SILENCIO_no_bloquea(toy_vault):
    """#321 — la extracción es selectiva y se cita del PDF: su silencio no prueba fabricación."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_324("citado", "otra cosa")
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "no_verbatim"


def test_quote_verdict_sin_txt_es_NO_EVALUABLE(toy_vault):
    """D-43 — sin el `.txt` de su fuente no se puede descartar que la frase esté en ese paper, así
    que ni siquiera la evidencia positiva alcanza: el chequeo no pudo correr."""
    _extr_324("ajeno", CITA_324)
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado", "ajeno"}, {})
    assert ver == "no_evaluable"


def test_quote_verdict_la_cita_AMBIGUA_no_bloquea(toy_vault):
    """#316 — sin `[[bibcode]]` adyacente la cita se probó contra todas las fuentes del bloque: el
    hallazgo es más débil y no puede frenar un cierre."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_324("citado", "otra cosa")
    _extr_324("ajeno", CITA_324)
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado", "ajeno"},
                               {"citado": cfg.fulltext_readings("citado")}, ambiguo=True)
    assert ver == "no_verbatim"


def test_quote_verdict_sin_EXTRACCION_de_la_fuente_no_bloquea(toy_vault):
    """#318 — «no está en la extracción» sólo significa algo si la extracción existe. La fuente
    off-ADS sin extraer, o la bóveda pre-#311 sin migrar, no es una cita alterada: es un chequeo que
    no se pudo correr, aunque la frase aparezca en la extracción de otro paper."""
    _txt_324("citado", "prosa que no dice la cita")          # `.txt` sí, extracción no
    _extr_324("ajeno", CITA_324)
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado", "ajeno"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "no_verbatim"


def test_fulltext_readings_memoiza(toy_vault):
    """#320/#324 — el chequeo corre **por cita**, así que sin caché el mismo `.txt` se lee y
    normaliza decenas de veces en la pasada que `CLAUDE.md` describe como barata."""
    _txt_324("2013Voss", f"prosa. {CITA_324}. más prosa.")
    assert cfg.fulltext_readings("2013Voss") is cfg.fulltext_readings("2013Voss")


def test_quote_verdict_el_txt_que_PARTE_la_cita_no_es_culpa_de_la_nota(toy_vault):
    """#288 — la fuente sí la dice y el `.txt` la parte (números de línea de un preprint a dos
    columnas metidos en medio de la frase). Es otro trabajo y otra severidad: no hay nada que
    corregir en la nota. Medido sobre cinco hallazgos abiertos uno por uno, CUATRO eran esto."""
    partido = CITA_324.replace("enough", "enough 1234")     # el número que inyecta el `.txt`
    _txt_324("citado", f"prosa. {partido}. más prosa.")
    _extr_324("citado", "otra cosa")
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_parte"


def test_la_matematica_PARTE_la_cita_como_la_elipsis(toy_vault):
    """#326 — `$…$` se borraba y las dos mitades se PEGABAN, produciendo una cadena que no existe en
    ningún `.txt`: «Reaching such a high $S/N_{cont}$ is not achievable» quedaba *«reaching such a
    high is not achievable»*, con `s/ncont` en el medio del archivo. Es el mismo argumento que
    `quote_fragments` hace para la elipsis, aplicado al marcador equivocado.

    Pesa porque `CLAUDE.md` **manda** `$...$` en `vault/wiki/`: 412 de 3036 citas de una bóveda real
    lo llevan, y ninguna podía pasar el paso 1 de `quote_verdict` — el detector mandaba a corregir
    algo ya correcto, y no había corrección que lo apagara."""
    cita = ("Reaching such a high $S/N_{cont}$ is not achievable for any star and telescope that "
            "put strong constraints on the observational method")
    txt = cfg.normalize_source_text(
        "bla. reaching such a high s/ncont is not achievable for any star and telescope that put "
        "strong constraints on the observational method. fin")
    assert cfg.quote_found(cita, txt)


def test_la_matematica_partida_NO_acepta_una_cita_que_la_fuente_no_dice(toy_vault):
    """El control: partir en la matemática no afloja el chequeo — las palabras de cada lado tienen
    que seguir estando, y las piezas cortas se descartan igual (`QUOTE_FRAG_MIN`)."""
    cita = ("Reaching such a high $S/N_{cont}$ is not achievable for any star and telescope that "
            "put strong constraints on the observational method")
    txt = cfg.normalize_source_text("reaching such a high s/ncont is not achievable for any star. fin")
    assert not cfg.quote_found(cita, txt)


def test_el_backtick_y_el_wikilink_DESENVUELVEN_no_borran(toy_vault):
    """#326, la ⚠ del issue, medida: sólo `$…$` tenía el trato de «borrar y pegar». El backtick y el
    `[[wikilink]]` pierden sus DELIMITADORES y conservan el texto, así que no fabrican una cadena
    inexistente."""
    txt = cfg.normalize_source_text("el parámetro alpha vale 3 y el resto de la frase sigue acá")
    assert cfg.quote_found("el parámetro `alpha` vale 3 y el resto de la frase sigue acá", txt)


# ── #333 · el `.txt` puede ACUSAR, en un dominio acotado ─────────────────────────────────────────
# El caso real que lo produjo, medido sobre `Almagesto-Tesis` el 2026-08-31 con el cortador de #332
# ya arreglado: `2026A&A...705A.234O` dice «real-world systematics **that are not orthogonal**
# might become entangled» y la extracción transcribió «**do not become orthogonal and** might become
# entangled». La nota copió la extracción, fielmente, y `contrast --validar` daba `0 ✅` porque su
# juez ES la extracción. El `.txt` —`pdftotext`, determinista— lo tenía bien.

CITA_333 = "since wPCA constructs orthogonal components by design, real-world systematics "


def test_txt_accuses_la_cola_divergente_EN_PROSA_es_evidencia(toy_vault):
    """#333, la clase que el issue pide detectar: prefijo largo compartido y cola distinta, en prosa
    y arrancando en un borde de palabra. Gana el lector determinista sobre el LLM."""
    _txt_324("citado", "bla. " + CITA_333 + "that are not orthogonal might become entangled "
                                            "within the same vector. bla")
    _extr_324("citado", CITA_333 + "do not become orthogonal and might become entangled")
    ver, det = cfg.quote_verdict(CITA_333 + "do not become orthogonal and might become entangled",
                                 ["citado"], {"citado"},
                                 {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_acusa" and det["bib"] == "citado"
    assert det["cola_cita"].startswith("do not become orthogonal")
    assert det["cola_txt"].startswith("that are not orthogonal")


def test_txt_accuses_NO_opina_cuando_la_divergencia_toca_la_matematica(toy_vault):
    """#333, paso 2 de la regla: `$…$` es exactamente donde el `.txt` degrada (#205/#326), así que
    ahí no es testigo — la respuesta es el PDF, no una marca. Medido: los 3 casos con matemática de
    esa bóveda habrían acusado sin esta guarda, y los tres tienen la fórmula EN el punto de
    divergencia."""
    cita = CITA_333 + "the inverse covariance $V^{-1}_j$ is just a diagonal matrix"
    _txt_324("citado", "bla. " + CITA_333 + "the inverse covariance v-1 is just a diagonal ma~ "
                                            "col . note that the covariance. bla")
    _extr_324("citado", cita)
    ver, _ = cfg.quote_verdict(cita, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_la_AUSENCIA_LIMPIA_no_acusa(toy_vault):
    """#333, paso 3: el `.txt` simplemente no tiene la cadena → como siempre, `txt_degradado`. Sin
    prefijo compartido no hay evidencia positiva de nada, y ésta es la clase mayoritaria (11 de 25
    en la re-medición)."""
    _txt_324("citado", "un `.txt` que perdió la frase entera y habla de otra cosa completamente")
    _extr_324("citado", CITA_333 + "do not become orthogonal and might become entangled")
    ver, _ = cfg.quote_verdict(CITA_333 + "do not become orthogonal and might become entangled",
                               ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_la_divergencia_A_MEDIA_PALABRA_es_del_ARTEFACTO(toy_vault):
    """#333, el discriminador que compró la re-medición. `pdftotext` rompe PALABRAS —la ligadura
    `ﬁ`, la palabra partida por un espacio pelado (`mix tures`), el empalme— y un LLM que transcribe
    mal cambia PALABRAS. Sobre 7 candidatos de una bóveda real: los **4** que divergen dentro de una
    palabra eran artefactos del `.txt`, los **3** que divergen en un borde eran alteraciones reales.
    Sin esta guarda el detector nacería con 4 falsos positivos de 7."""
    _txt_324("citado", "bla. " + CITA_333 + "do not become orthogonal and might become entangled "
                                            "within the same vec tor of the run. bla")
    largo = CITA_333 + "do not become orthogonal and might become entangled within the same vector"
    _extr_324("citado", largo)
    ver, _ = cfg.quote_verdict(largo, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_el_txt_que_SE_CORTA_no_dice_otra_cosa(toy_vault):
    """#333 — una lectura que se queda sin texto (borde de página o de columna) calla, no
    contradice: sin `CITA_COLA_MIN` caracteres más, no hay divergencia que declarar. La divergencia
    cae en un borde de palabra —o sea que pasa la otra guarda— y aun así el `.txt` no acusa: lo que
    tiene después del corte no alcanza para afirmar que dice otra cosa."""
    _txt_324("citado", "bla. " + CITA_333 + "that")
    largo = CITA_333 + "do not become orthogonal and might become entangled"
    _extr_324("citado", largo)
    ver, _ = cfg.quote_verdict(largo, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_no_opina_si_la_CITA_cruza_un_borde_de_celda(toy_vault):
    """#333, la otra mitad del paso 2. Desde #240 una cita que viaja en una celda lleva su `\\|`
    escapado, y ahí lo que se está comparando ya no es prosa corrida: la respuesta es el PDF."""
    cita = CITA_333 + "do not become orthogonal \\| might become entangled here"
    _txt_324("citado", "bla. " + CITA_333 + "that are not orthogonal might become entangled. bla")
    _extr_324("citado", cita)
    ver, _ = cfg.quote_verdict(cita, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_no_opina_si_el_TXT_cruza_un_borde_de_celda(toy_vault):
    """El otro lado del mismo paso: un `.txt` normalizado colapsa los espacios, así que una tabla
    queda con forma de prosa y su «cola» son celdas vecinas, no una oración que diga otra cosa."""
    cita = CITA_333 + "do not become orthogonal and might become entangled here"
    _txt_324("citado", "bla. " + CITA_333 + "that | are | not | orthogonal | 0.12. bla")
    _extr_324("citado", cita)
    ver, _ = cfg.quote_verdict(cita, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_se_queda_con_la_MEJOR_ocurrencia(toy_vault):
    """#333 — un paper repite su propia frase, y la comparación es contra la ocurrencia que **más**
    comparte: quedarse con la primera haría que un arranque repetido en otro contexto tapara la
    lectura que de verdad contradice a la extracción."""
    corto = CITA_333[:CITA_333.index("systematics")]      # comparte menos que la ocurrencia buena
    _txt_324("citado", "bla. " + corto + "systemic drifts dominate the budget. otra cosa. "
                       + CITA_333 + "that are not orthogonal might become entangled. bla")
    largo = CITA_333 + "do not become orthogonal and might become entangled"
    _extr_324("citado", largo)
    ver, det = cfg.quote_verdict(largo, ["citado"], {"citado"},
                                 {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_acusa" and det["cola_txt"].startswith("that are not orthogonal")


def test_txt_accuses_la_cita_ENTERA_en_el_txt_no_es_divergencia(toy_vault):
    """El contrato de la función, que la misma línea del borde de palabra ya sostiene: si el `.txt`
    la tiene completa no hay cola que comparar, y una «acusación» con la cola vacía sería una marca
    sobre nada. Lo cierra `normalize_quote`, que recorta el espacio final — una coincidencia entera
    termina en una letra, nunca en un borde. (Por el llamador esto no debería llegar: el paso 1 la
    habría absuelto; la función se puede llamar sola.)"""
    lectura = cfg.normalize_source_text("bla. " + CITA_333 + "do not become orthogonal. bla")
    assert cfg.txt_accuses(CITA_333 + "do not become orthogonal", [lectura]) is None


def test_txt_accuses_la_cita_ELIDIDA_no_se_juzga_por_su_cola(toy_vault):
    """#333 — «A … B» no está verbatim en ningún lado por construcción (`quote_fragments`), así que
    su «cola divergente» sería el propio recorte. Se chequea por fragmentos o no se chequea."""
    _txt_324("citado", "bla. " + CITA_333 + "that are not orthogonal might become entangled. bla")
    cita = CITA_333 + "… and might become entangled within the same vector of the run"
    _extr_324("citado", cita)
    ver, _ = cfg.quote_verdict(cita, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_el_txt_de_OTRO_bibcode_no_acusa(toy_vault):
    """#333 — la evidencia es entre los DOS artefactos de una misma fuente. Cruzarla con el `.txt`
    de otro paper fabricaría la atribución que este framework más persigue."""
    _txt_324("ajeno", "bla. " + CITA_333 + "that are not orthogonal might become entangled. bla")
    largo = CITA_333 + "do not become orthogonal and might become entangled"
    _extr_324("citado", largo)
    _txt_324("citado", "un `.txt` que perdió la frase")
    ver, _ = cfg.quote_verdict(largo, ["citado"], {"citado", "ajeno"},
                               {"citado": cfg.fulltext_readings("citado"),
                                "ajeno": cfg.fulltext_readings("ajeno")})
    assert ver == "txt_degradado"


def test_verificar_pdf_mark_lleva_el_MOTIVO_y_la_FECHA():
    """#225/#341 — la marca es `⚠verificar en el PDF (<qué se dudó>, <fecha>)`, y las dos partes son
    del contrato: en seis meses sirve **el motivo**, no una categoría, y la fecha dice desde cuándo
    la deuda está abierta. Una sola definición, porque desde 1.162.0 la emite una herramienta
    (`contrast --validar`) y la busca otra (el detector del lint)."""
    import datetime as _dt
    m = cfg.verificar_pdf_mark("el `.txt` y la extracción difieren en la cola", "2026-08-31")
    assert m == "⚠verificar en el PDF (el `.txt` y la extracción difieren en la cola, 2026-08-31)"
    assert m.startswith(cfg.VERIFICAR_PDF_MARK)
    assert cfg.verificar_pdf_mark("x").endswith(f", {_dt.date.today().isoformat()})")


def test_txt_accuses_sin_txt_devuelve_None():
    """D-43 — sin lectura en disco no hay testigo, y eso no es una acusación vacía: es no evaluable."""
    assert cfg.txt_accuses(CITA_333 + "do not become orthogonal", []) is None


# ── #327 · «el bloque de una clave», una sola definición ──────────────────────────────────────────

def test_fm_key_span_toma_las_lineas_de_CONTINUACION():
    """#327 — un escalar de YAML envuelve, y tocar sólo su primera línea deja la continuación
    huérfana bajo la clave siguiente: el frontmatter deja de parsear y la nota evade todos los
    chequeos de su tipo. Es la cuarta vez que el repo paga esta forma (#244 el borrado, el renombre,
    #306 la lista flow, #327 el reemplazo), así que la noción vive en UN lugar."""
    #  @inv INV-147
    lines = ["bibcode: 2010CJ",
             "alcance: caps. 2-3 (formulación del problema y métodos de separación); 161",
             "  páginas, el resto es aplicación a audio y no entra",
             "tags: [paper]"]
    assert cfg.fm_key_span(lines, "alcance") == (1, 3)
    assert cfg.fm_key_span(lines, "tags") == (3, 4)
    assert cfg.fm_key_span(lines, "no_existe") is None, "«no está» no es «está vacía»"


def test_fm_key_span_toma_los_items_de_una_lista_en_BLOQUE():
    """La otra forma multilínea del frontmatter de esta bóveda: la lista en bloque que escribe
    `make_notes` al crear la nota, con o sin indentación."""
    lines = ["salvedades:", "  - la primera", "  - la segunda", "stars:", "- tau Cet", "year: 2020"]
    assert cfg.fm_key_span(lines, "salvedades") == (0, 3)
    assert cfg.fm_key_span(lines, "stars") == (3, 5)


def test_fm_key_span_arranca_donde_se_le_pide():
    """`desde` existe para recorrer una clave REPETIDA sin volver a encontrar la primera — es lo que
    hace decidible el borrado de todas sus apariciones."""
    lines = ["a: 1", "b: 2", "a: 3"]
    assert cfg.fm_key_span(lines, "a") == (0, 1)
    assert cfg.fm_key_span(lines, "a", 1) == (2, 3)


# ── #331 · UNA implementación de «¿este slug es estrella o tema?» ─────────────
def test_subject_kinds_responde_por_config_y_no_inventa(toy_vault):
    """La pregunta que todo «próximo paso» tiene que contestar antes de imprimir un comando.
    Estaba contestada de rebote en tres lugares y ninguno la contestaba: los dos que imprimían el
    comando lo hacían sin `--theme`, y `make_notes` la contestaba muriendo. Un slug que no está en
    ninguna config devuelve la tupla vacía — que NO es «es una estrella».

    @inv INV-141"""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods"}})
    assert cfg.subject_kinds("test_star") == ("star",)
    assert cfg.subject_kinds("ica") == ("theme",)
    assert cfg.subject_kinds("no-existe") == ()


def test_subject_kinds_con_una_config_ILEGIBLE_no_se_muere(toy_vault):
    """Alimenta MENSAJES: un `themes.yaml` roto tiene que dejar el hint corto, no tumbar al script
    que lo imprime (el YAML roto lo reportan `themes_error` y el lint, que es su lugar)."""
    cfg.THEMES_YAML.write_text("ica: [sin cerrar\n", encoding="utf-8")
    assert cfg.subject_kinds("test_star") == ("star",)
    assert cfg.subject_kinds("ica") == ()


def test_all_subjects_saca_el_slug_del_tema_de_la_CLAVE(toy_vault):
    """#346 — el barrido de sujetos, en UNA implementación: en `stars.yaml` el slug es un CAMPO de
    la entrada y en `themes.yaml` es la CLAVE del YAML.

    Pedirle `slug` al mapa del tema devuelve `None` y saltea el sujeto en silencio, que es cómo
    `extraccion_no_declarada` (INV-83) quedó apagado para todo tema. `name` es cómo lo NOMBRA un
    paper (`stars`/`thesis_links`), no el slug: en una estrella los dos difieren.  @inv INV-83"""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "componentes-independientes",
                                         "area": "methods"}})
    porkind = {k: (slug, name, meta) for k, slug, name, meta in cfg.all_subjects()}
    assert porkind["star"][:2] == ("test_star", "Estrella Test")
    assert porkind["theme"][:2] == ("ica", "ica")
    assert porkind["theme"][2]["concept"] == "componentes-independientes"


def test_all_subjects_con_una_config_ILEGIBLE_aporta_lo_que_puede(toy_vault):
    """Los llamadores son DETECTORES del lint: morir sobre un `themes.yaml` roto no reportaría nada
    de la mitad sana, y el YAML roto ya lo levanta su propia categoría (`themes_error`).

    La entrada sin slug resoluble se cae acá por el mismo motivo por el que se caía en los dos
    call sites: sin slug no hay nota ni registro a los que apuntar. Y una entrada que **no es un
    mapa** parsea sin error (el YAML es válido, la forma no): sin el `isinstance`, `meta.get`
    tumba al detector entero con un `AttributeError` en vez de reportar la mitad sana."""
    cfg.THEMES_YAML.write_text("ica: [sin cerrar\n", encoding="utf-8")
    assert [k for k, *_ in cfg.all_subjects()] == ["star"]
    write_yaml(cfg.STARS_YAML, {"Sin Slug": {"simbad": "x"}, "No Es Un Mapa": "test_star"})
    assert cfg.all_subjects() == []


def test_make_notes_cmd_pone_theme_SOLO_donde_corresponde(toy_vault):
    """El constructor del comando: es lo que hace que el remedio impreso corra."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods"}})
    assert cfg.make_notes_cmd("ica") == "python scripts/make_notes.py ica --theme"
    assert cfg.make_notes_cmd("test_star") == "python scripts/make_notes.py test_star"
    assert cfg.make_notes_cmd("no-existe") == "python scripts/make_notes.py no-existe"


def test_subject_refusal_calla_cuando_el_sujeto_ES_del_tipo_pedido(toy_vault):
    """#343 — la negativa la usan TRES scripts (`make_notes`, `extraction_prompt`,
    `fetch_ground_truth`), así que vive acá y no copiada: es el molde de #215/#324/#335, ya
    divergido tres veces en este repo. El caso bueno tiene que callar, o cada corrida legítima
    aborta.

    @inv INV-141"""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods"}})
    assert cfg.subject_refusal("test_star", "star", "no se hizo nada") is None
    assert cfg.subject_refusal("ica", "theme", "no se hizo nada") is None


def test_subject_refusal_nombra_las_DOS_configs_y_el_remedio_del_LLAMADOR(toy_vault):
    """El mensaje que reemplaza al `KeyError`: nombra las dos configs (el `KeyError` acertaba a
    medias — nombraba una sola, y la equivocada) y pega el remedio **que le pasa el llamador**,
    porque no es el mismo en los tres: en `extraction_prompt` es «te faltó `--theme`», en
    `fetch_ground_truth` es «los temas no tienen ground-truth»."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods"}})
    msg = cfg.subject_refusal("ica", "star", "no se bajó nada", "Corré: `otra cosa`")
    assert "themes.yaml" in msg and "stars.yaml" in msg
    assert "no se bajó nada" in msg, "la consecuencia es del llamador, no una genérica"
    assert msg.endswith("Corré: `otra cosa`"), "el remedio va en su propia línea, al final"


def test_subject_refusal_SIN_remedio_no_inventa_una_linea_vacia(toy_vault):
    """`fetch_ground_truth` no tiene comando que ofrecer: un tema no tiene ground-truth. El
    remedio es opcional, y sin él el mensaje termina en la diagnosis — nunca en un renglón
    colgado que se lea como un comando cortado."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods"}})
    msg = cfg.subject_refusal("ica", "star", "no se bajó ningún ground-truth")
    assert "\n" not in msg and msg.endswith(".")


def test_subject_refusal_sin_NINGUNA_config_no_ofrece_comando(toy_vault):
    """Sin entrada en ninguna de las dos no hay invocación alternativa: lo que sí hay que decir es
    dónde se define un sujeto. Y no se inventa un `--theme` para un slug que no está en
    `themes.yaml`."""
    msg = cfg.subject_refusal("no-existe", "star", "no se hizo nada", "Corré: `no me llames`")
    assert "stars.yaml" in msg and "themes.yaml" in msg
    assert "no me llames" not in msg, "el remedio del llamador no aplica: no hay a qué mandar"
    assert "--theme" not in msg


# ── #351 · qué `fq` hereda un tema de MÉTODO que no declara el suyo ──────────

def test_objective_search_fq_tiene_TRES_estados(toy_vault):
    """#85 / D-43 — sin declarar → el default astro; con valor → ése; `null` declarado → no acota.
    La cascada vive acá desde 1.166.0 porque el lint la necesita y no puede importar `query_ads`
    (arrastraría `requests`): dos implementaciones es cómo un `null` termina significando cosas
    distintas según quién lo lea."""
    write_yaml(cfg.OBJECTIVE_YAML, {"relevance": {"facets": {"a": "x"}}})
    assert cfg.objective_search_fq() == cfg.ASTRO_FQ
    write_yaml(cfg.OBJECTIVE_YAML, {"relevance": {"search_fq": "database:physics"}})
    assert cfg.objective_search_fq() == "database:physics"
    write_yaml(cfg.OBJECTIVE_YAML, {"relevance": {"search_fq": None}})
    assert cfg.objective_search_fq() is None


def test_theme_inherited_fq_avisa_solo_cuando_hay_exclusion(toy_vault):
    """#351 — un tema con `facet:` propia y sin `search_fq` hereda el del objetivo, que le excluye
    su literatura server-side (medido en `ica`: 0 papers por la puerta fundacional con el fq
    heredado, 2 sin él). Devuelve lo que hereda; `None` cuando no hay nada que avisar."""
    write_yaml(cfg.OBJECTIVE_YAML, {"relevance": {"search_fq": "database:astronomy"}})
    assert cfg.theme_inherited_fq({"facet": "independent component"}) == "database:astronomy"
    # `search_fq` DECLARADO —`null` incluido— es una decisión, y no se lee como no declarar nada
    assert cfg.theme_inherited_fq({"facet": "ica", "search_fq": None}) is None
    assert cfg.theme_inherited_fq({"facet": "ica", "search_fq": "database:physics"}) is None
    # sin `facet:` propia no es un tema de método: heredar la lente global es lo que corresponde
    assert cfg.theme_inherited_fq({"query": "abs:x"}) is None
    assert cfg.theme_inherited_fq(None) is None


def test_theme_inherited_fq_calla_si_el_objetivo_no_acota(toy_vault):
    """#351 — heredar `search_fq: null` no deja nada afuera: nombrar una exclusión inexistente es
    la atribución falsa que la regla de método nº 4 prohíbe."""
    write_yaml(cfg.OBJECTIVE_YAML, {"relevance": {"search_fq": None}})
    assert cfg.theme_inherited_fq({"facet": "independent component"}) is None


def test_fq_value_rechaza_la_lista(toy_vault):
    """AUD-182 / INV-119 — `str(v)` sobre una lista manda el `repr` de Python a Solr y filtra el
    corpus con una regla que nadie escribió. Falla ruidoso, como el resto de la config."""
    assert cfg.fq_value("", "x", "y") is None
    with pytest.raises(RuntimeError, match="search_fq tiene que ser un string"):
        cfg.fq_value(["a", "b"], "themes.yaml", "la entrada del tema")

# ── #344 · el hermano de auditoría es un archivo, no una nota ────────────────────────────────────

def test_verif_sidecar_es_el_hermano_en_el_MISMO_directorio(tmp_path):
    """#344 — `<nota>.verif.md` al lado, NO un `.verif/` con punto: con punto Obsidian lo esconde y
    el par deja de ser obvio. Es la ÚNICA definición de dónde vive la tabla de una nota: los cuatro
    consumidores (lint, make_notes, reverify_subset, contrast) pasan por acá."""
    assert cfg.verif_sidecar(tmp_path / "wiki" / "ica.md") == tmp_path / "wiki" / "ica.verif.md"
    assert cfg.verif_sidecar(tmp_path / "2020A&A...1..1X.md").name == "2020A&A...1..1X.verif.md"


def test_is_verif_sidecar_distingue_el_hermano_de_la_nota(tmp_path):
    """La otra mitad: `note_paths` lo usa para sacar los hermanos de TODO enumerador. Con la
    pregunta al revés, cada barrido tomaría los hermanos por notas —sin frontmatter, sin tipo— y
    con la respuesta siempre `True` no quedaría ninguna nota."""
    assert cfg.is_verif_sidecar(tmp_path / "ica.verif.md")
    assert not cfg.is_verif_sidecar(tmp_path / "ica.md")
    assert not cfg.is_verif_sidecar(tmp_path / "verif.md")


def test_note_paths_saca_los_hermanos_y_ordena(tmp_path):
    """El enumerador único (#344). El orden estable es de INV-43: sin él, cada barrido reporta lo
    mismo en otro orden y dos reportes dejan de ser comparables."""
    for n in ("b.md", "a.md", "a.verif.md"):
        (tmp_path / n).write_text("x", encoding="utf-8")
    assert [p.name for p in cfg.note_paths(tmp_path)] == ["a.md", "b.md"]
    assert cfg.note_paths(tmp_path / "no-existe") == []


# ── #360 · el simétrico de #351: los EJES que un tema de método hereda en silencio ───────────────

def test_theme_inherited_axes_es_el_simetrico_de_theme_inherited_fq(toy_vault):
    """#360 — #307 midió que a un tema de método se le preguntan los ejes de una bóveda astro (6 de
    8 facetas vacías en 12 extracciones; los ejes que el tema necesitaba nunca se preguntaron).
    `search_fq` tuvo su aviso (#351) y `ejes:` no. Mismos tres estados (D-43): sin declarar →
    hereda y se DICE cuáles; declarado → calla; `ejes: []` → decisión explícita, calla."""
    globales = list(cfg.as_map(cfg.as_map(cfg.load_objective().get("relevance")).get("facets")))
    assert globales, "el toy_vault declara facetas globales"
    assert cfg.theme_inherited_axes({"facet": "independent component"}) == globales
    assert cfg.theme_inherited_axes({"facet": "ica", "ejes": []}) is None
    assert cfg.theme_inherited_axes({"facet": "ica", "ejes": ["identificabilidad"]}) is None
    assert cfg.theme_inherited_axes({"title": "GP", "query": "abs:x"}) is None, "sin facet propia no es tema de método"
    assert cfg.theme_inherited_axes(None) is None


def test_los_dos_heredados_comparten_la_senal_de_tema_de_metodo(toy_vault):
    """#360 — paridad fq↔ejes: la señal de «tema de método» es UNA (la `facet:` propia). Si un día
    divergen, un tema avisa por un eje y calla por el otro."""
    for meta in ({"facet": "ica"}, {"title": "x"}, {"facet": "ica", "search_fq": None, "ejes": []}):
        assert (cfg.theme_inherited_fq(meta) is None) == (cfg.theme_inherited_axes(meta) is None), meta


# ── #382 · una fuente LARGA con bibcode ADS se declara larga en `extra_core` ─────────────────────

def test_extra_core_acepta_unidad_cita_y_alcance_con_la_misma_validacion_que_sources(toy_vault):
    """#382 — `unidad_cita`/`alcance` (#80) sólo existían en `sources:`; una tesis con bibcode ADS
    va por contrato en `extra_core` y no podía declararse larga: el prompt no ramificaba y el
    chequeo de completitud no distinguía recorte de omisión. Misma validación que en `sources:`."""
    ok = [{"bibcode": "2021PhDT.........6D", "via": "usuario", "motivo": "tesis",
           "unidad_cita": "pagina", "alcance": "caps. 2-3"}]
    assert cfg.load_extra_core({"extra_core": ok}, entry="t") == ok
    with pytest.raises(SystemExit) as e:
        cfg.load_extra_core({"extra_core": [{**ok[0], "alcance": None}]}, entry="t")
    assert "alcance" in str(e.value) and "2021PhDT" in str(e.value)
    with pytest.raises(SystemExit) as e:
        cfg.load_extra_core({"extra_core": [{**ok[0], "unidad_cita": "hoja"}]}, entry="t")
    assert "unidad_cita: hoja" in str(e.value) and "pagina" in str(e.value)
    # `linea` (o ausente) no exige alcance: no es un documento largo
    assert cfg.load_extra_core({"extra_core": [{**ok[0], "unidad_cita": "linea", "alcance": None}]},
                               entry="t")


def test_extra_core_scope_devuelve_solo_las_entradas_con_alcance(toy_vault):
    """#382 — el mapa que `make_notes` estampa y `--restamp-alcance` re-sincroniza: sólo las
    entradas que declaran algo; el resto no es un documento largo."""
    ec = [{"bibcode": "2021PhDT.........6D", "via": "usuario", "motivo": "t", "unidad_cita": "pagina",
           "alcance": "caps. 2-3"},
          {"bibcode": "2020X", "via": "usuario", "motivo": "t"}]
    assert cfg.extra_core_scope({"extra_core": ec}, entry="t") == {
        "2021PhDT.........6D": ("caps. 2-3", "pagina")}
    assert cfg.extra_core_scope({}, entry="t") == {}


# ── Auditoría 2026-09-04 · tests rojos (xfail estricto) ─────────────────────────────────────────

# AUD-217 — cerrado en la pasada de fix de la auditoría 2026-09-04
def test_AUD217_subject_refusal_no_manda_a_definir_un_sujeto_que_esta_en_un_yaml_roto(toy_vault):
    """AUD-217 — con `stars.yaml` inválido el sujeto SÍ está definido; «definilo ahí» es la receta
    que el propio docstring describe como la que fabrica una estrella falsa. Tiene que decir que
    el YAML no parsea (INV-80)."""
    cfg.STARS_YAML.write_text("test_star:\n  name: X\n  bad: [unclosed\n", encoding="utf-8")
    r = cfg.subject_refusal("test_star", "star", "no se hizo nada")
    assert r is not None and "desconocido" not in r and "yaml" in r.lower(), r


def test_note_has_reading_es_UNA_regla_para_todos_los_borradores():
    """AUD-219/223 — `methods` poblado O una vista fechada; una vista sin fecha no es lectura."""
    assert cfg.note_has_reading({"methods": ["ica"]}) is True
    assert cfg.note_has_reading({"vistas": [{"sujeto": "x", "fecha": "2026-09-01"}]}) is True
    assert cfg.note_has_reading({"vistas": [{"sujeto": "x"}], "methods": []}) is False
    assert cfg.note_has_reading({}) is False and cfg.note_has_reading(None) is False


def test_wikilink_re_cubre_las_cuatro_formas_y_no_el_prefijo():
    """AUD-218 — una sola regex para los dos renombradores: alias, anclas `#` y `^`, y nunca un
    stem que sólo prefija a otro."""
    rx = cfg.wikilink_re("GJ 581")
    for s in ("[[GJ 581]]", "[[GJ 581|alias]]", "[[GJ 581#Planetas]]", "[[GJ 581^blk]]"):
        assert rx.search(s), s
    assert not rx.search("[[GJ 5811]]")


# ── AUD-273 / AUD-286 · `note_stem` y `note_state`: una regla, no trece ni dos ───────────────

def test_note_stem_es_la_unica_regla_del_stem():
    """AUD-273: tres `safe_name` y diez `replace("/", "_")` inline eran la misma identidad
    archivo↔bibcode. Un bibcode sin `/` es su propio stem; el estilo arXiv viejo cambia la barra."""
    assert cfg.note_stem("astro-ph/9605059") == "astro-ph_9605059"
    assert cfg.note_stem("2020ApJ...1..1A") == "2020ApJ...1..1A"
    assert cfg.note_stem("a/b/c") == "a_b_c"


def _nota_paper(stem: str, fm: dict) -> None:
    from conftest import mk_note
    mk_note(cfg.PAPERS, stem, {"bibcode": stem, "tags": ["paper"], **fm})


def test_note_state_sin_sujeto_usa_la_regla_de_lectura(toy_vault):
    """AUD-286: `query_ads` llamaba «extraída» a `methods` poblado —que `make_notes` mergea
    add-only sin leer— y `triage` exigía una vista FECHADA. Una sola regla (#189, vía
    `note_has_reading`): la vista fechada alcanza aunque `methods` esté vacío, y `methods` sigue
    alcanzando (es suficiente, no necesario)."""
    _nota_paper("2020meth....1A", {"methods": ["gls"]})
    _nota_paper("2020view....1B", {"vistas": [{"sujeto": "Estrella Test", "tipo": "star",
                                              "fecha": "2026-09-01"}]})
    _nota_paper("2020stub....1C", {"vistas": [{"sujeto": "Estrella Test", "tipo": "star"}]})
    assert cfg.note_state("2020meth....1A") == cfg.NOTE_READ
    assert cfg.note_state("2020view....1B") == cfg.NOTE_READ, \
        "vista fechada sin `methods`: ANTES `query_ads` la llamaba `stub` (el caso que cambia)"
    assert cfg.note_state("2020stub....1C") == cfg.NOTE_STUB, "vista sin fecha = lectura no hecha"
    assert cfg.note_state("2020nada....1D") == cfg.NOTE_ABSENT
    assert cfg.note_state("astro-ph/0001") == cfg.NOTE_ABSENT, "resuelve por `note_stem`"


def test_note_state_con_sujeto_exige_la_vista_fechada_de_ese_sujeto(toy_vault):
    """Con sujeto la pregunta es «¿se leyó PARA este sujeto?»: sólo cuenta la vista de ese sujeto
    con `fecha`; `methods` poblado NO alcanza (lo mergea el retro-linkeo sin leer, #188)."""
    _nota_paper("2020view....1B", {"methods": ["gls"],
                                   "vistas": [{"sujeto": "Estrella Test", "tipo": "star",
                                               "fecha": "2026-09-01"}]})
    assert cfg.note_state("2020view....1B", "Estrella Test") == cfg.NOTE_READ
    assert cfg.note_state("2020view....1B", "Otro Sujeto") == cfg.NOTE_STUB
    assert cfg.note_state("2020nada....1D", "Estrella Test") == cfg.NOTE_ABSENT


def test_note_state_con_vistas_mal_formadas_degrada_a_stub(toy_vault):
    """Una `vistas[]` mal formada es hallazgo del lint, no de acá: hay nota y la lectura no consta."""
    _nota_paper("2020mal.....1E", {"vistas": "no-es-lista"})
    assert cfg.note_state("2020mal.....1E", "Estrella Test") == cfg.NOTE_STUB


# ── #397 · el escritor quirúrgico de frontmatter y el lector de BibTeX ───────────────────────────

def test_stamp_fm_fields_reemplaza_la_clave_vieja_y_no_toca_el_cuerpo(tmp_path):
    """Vivía en `check_retractions` y ahora es de `lib_config` (#397): lo usan el estampador de
    retracciones y el de BibTeX, y una segunda implementación del mismo borrado quirúrgico es
    justamente lo que este repo pagó siete veces en un día.

    Lo que garantiza: edita el TEXTO —no re-serializa el YAML—, así que el orden y los comentarios
    que dejó la extracción LLM quedan; y al reemplazar una clave se lleva su bloque indentado
    entero, sin dejar ítems huérfanos que el YAML absorba en la clave anterior."""
    f = tmp_path / "n.md"
    f.write_text("---\nbibcode: X\n# comentario de la extracción\nretraction:\n  type: vieja\n"
                 "  date: '2020-01-01'\ntags: [paper]\n---\n\n# cuerpo\n\nprosa\n", encoding="utf-8")
    texto = f.read_text(encoding="utf-8")
    cfg.stamp_fm_fields(f, cfg.split_fm(texto), texto.split("\n---\n", 1)[-1],
                        {"retraction": {"type": "nueva"}})
    salida = f.read_text(encoding="utf-8")
    fm = cfg.split_fm(salida)
    assert fm["retraction"] == {"type": "nueva"} and fm["bibcode"] == "X"
    assert "vieja" not in salida and "2020-01-01" not in salida, "el bloque viejo se fue entero"
    assert "# comentario de la extracción" in salida and "prosa" in salida


def test_bibtex_fields_lee_las_tres_formas_de_valor():
    """`{…}`, `"…"` y pelado (un año va sin llaves). Y desenvuelve las llaves de protección: ADS
    escribe `title = "{A Jupiter-mass…}"`, y comparar eso crudo contra el `title` del frontmatter
    daría la discrepancia que el chequeo de #397 existe para NO inventar."""
    entrada = ('@ARTICLE{k,\n  year = 2004,\n  title = "{Identifiability Issues}",\n'
               '  doi = {10.1109/LSP.2004.836989},\n  author = {{Davies}, Mike},\n}\n')
    campos = cfg.bibtex_fields(entrada)
    assert campos == {"year": "2004", "title": "Identifiability Issues",
                      "doi": "10.1109/LSP.2004.836989", "author": "Davies, Mike"}
    assert cfg.bibtex_fields("") == {} and cfg.bibtex_fields("sin nada") == {}


def test_is_ads_bibcode_no_confunde_una_clave_sintetica():
    """#399 — `BIBCODE_LIKE_RE` es la heurística LAXA de los wikilinks (`^\\d{4}[A-Za-z]`) y una
    clave sintética `AAAA+Autor` la pasa. Un bibcode de ADS son **19 caracteres exactos**, y la
    diferencia no es cosmética: mandar las sintéticas al export de ADS devuelve 404 para el lote
    entero, y la corrida lo anunciaba como caída de red sobre papers que sí se evaluaron bien."""
    assert cfg.is_ads_bibcode("1995Natur.378..355M")
    assert not cfg.is_ads_bibcode("2011Naik") and not cfg.is_ads_bibcode("1998HyvarinenICANN")
    assert not cfg.is_ads_bibcode("") and not cfg.is_ads_bibcode(None)
    assert not cfg.is_ads_bibcode("x" * 19), "la forma también: 19 caracteres cualesquiera no basta"
