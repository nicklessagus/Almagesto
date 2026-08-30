"""lib_config: token ADS, loaders de config, áreas de concepts (declarado vs tolerante)."""
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


# ── #270 · los ejes que una vista contesta ──────────────────────────────────────────────────────

_VISTA_EJES = """## Vista — tau Cet (2026-08-30)

**Ejes:**

- **rv:** una medición
- **activity:** otra

**Aporte:** algo

- **Hueco:** falta el PDF
"""


def test_view_axes_lee_los_bullets_del_bloque_de_ejes():
    assert cfg.view_axes(_VISTA_EJES) == {"tau Cet": {"rv", "activity"}}


def test_view_axes_no_cuenta_los_bullets_de_fuera_del_bloque():
    """⛔ `- **Aporte:**` y `- **Hueco:**` no son ejes: una regex de bullets en negrita a secas los
    contaría y taparía justo el hueco que el detector de #270 busca."""
    assert "Hueco" not in cfg.view_axes(_VISTA_EJES)["tau Cet"]


def test_view_axes_ignora_un_encabezado_dentro_de_un_fence():
    """Paridad con AUD-178: un `## Vista` dentro de un ```fence``` es un EJEMPLO de la doc, no una
    sección — y contarlo produce hallazgos sobre notas correctas."""
    assert cfg.view_axes("```\n" + _VISTA_EJES + "```\n") == {}


def test_view_axes_sin_bloque_de_ejes_no_inventa_la_clave():
    """Una vista sin `**Ejes:**` no contesta ninguno: la clave ausente y el conjunto vacío se leen
    distinto aguas arriba (sin lente declarada no hay nada que comparar)."""
    assert cfg.view_axes("## Vista — X\n\n**Aporte:** algo\n") == {}
