"""measure_layout: el único script sin un test hasta esta pasada (149 líneas, 19% de cobertura —
ese 19% era sólo un import de CANALETA_MIN desde otro test). Cubre los dos defectos de la 7ª
auditoría (#1: "Exit 0 siempre" es falso bajo stdout ascii en el camino feliz; #2: publica un `(0)`
que significa "no miré" en vez de "medí cero") más lo básico: denominador cero, `--json`,
early-returns y el contrato de `CANALETA_MIN` que `test_multicolumn_matching.py` importa.
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import measure_layout  # noqa: E402

# Línea "útil" (≥ MIN_LINEA, sin canaleta ni corte de guión): sirve para poblar archivos que SÍ
# deben contar en las métricas.
TEXTO_UTIL = "\n".join([
    "Esta linea de relleno es suficientemente larga para ser considerada util.",
    "Otra linea tambien larga sin canaleta ni guion para el analisis de maqueta.",
]) + "\n"

# Línea corta (< MIN_LINEA): archivo "sin líneas útiles" — el caso que Defecto 2 volvía invisible.
TEXTO_SIN_LINEAS_UTILES = "corta\notra corta\n"


def _write_txt(vault, slug: str, stem: str, texto: str) -> Path:
    d = vault.FULLTEXT / slug
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{stem}.txt"
    p.write_text(texto, encoding="utf-8")
    return p


@pytest.fixture
def ml_vault(toy_vault, monkeypatch):
    """`toy_vault` ya crea `vault/raw/fulltext` en disco y repunta `cfg.RAW`/`cfg.ROOT`, pero
    `measure_layout.py` hace `from lib_config import RAW, ROOT`: un alias propio, tomado a nivel
    módulo, al que el monkeypatch de `cfg.RAW` NO le llega (mismo problema que `conftest.py` ya
    resuelve para `extract_fulltext.FULLTEXT`). Repunta el alias del propio módulo."""
    monkeypatch.setattr(measure_layout, "RAW", toy_vault.RAW)
    monkeypatch.setattr(measure_layout, "ROOT", toy_vault.ROOT)
    return toy_vault


# ── Defecto 1 — "Exit 0 siempre" es falso bajo stdout ascii ─────────────────────────────────────

def test_defecto1_no_muere_con_stdout_ascii_en_la_corrida_por_defecto(ml_vault, monkeypatch):
    """La corrida por defecto (sin --json) imprime '←' en la tabla legible. Con un stdout real
    codificado ascii (CI/consola mal configurada) eso es un UnicodeEncodeError sin capturar que
    tumba el proceso con exit 1 — el camino FELIZ por defecto, no un edge case (los early-returns
    se salvan solos por ir a stderr, que CPython degrada con backslashreplace). `capsys` no lo
    detecta porque acepta cualquier str sin importar el encoding real de la consola; por eso acá se
    usa un `TextIOWrapper` de verdad con `encoding='ascii'`."""
    _write_txt(ml_vault, "test_star", "2020Test", TEXTO_UTIL)
    buf = io.BytesIO()
    stdout_ascii = io.TextIOWrapper(buf, encoding="ascii", errors="strict")
    monkeypatch.setattr(sys, "stdout", stdout_ascii)
    monkeypatch.setattr(sys, "argv", ["measure_layout.py"])

    rc = measure_layout.main()
    stdout_ascii.flush()

    assert rc == 0
    salida = buf.getvalue().decode("ascii")
    assert "archivos multi-columna" in salida


# ── Defecto 2 — el "(0)" que significa "no miré" ─────────────────────────────────────────────────

def test_defecto2_saltados_no_quedan_indistinguibles_de_corpus_vacio(ml_vault, capsys, monkeypatch):
    """5 archivos .txt reales en disco, todos sin líneas útiles: antes del fix el script publicaba
    `0 / 0 (0%)` y `"archivos": 0` en el --json — indistinguible de "no había nada que medir". El
    fix debe exponer cuántos archivos se encontraron y cuántos se saltaron, en tabla y en JSON."""
    for i in range(5):
        _write_txt(ml_vault, "test_star", f"corta{i}", TEXTO_SIN_LINEAS_UTILES)
    monkeypatch.setattr(sys, "argv", ["measure_layout.py", "--json"])

    rc = measure_layout.main()
    data = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert data["archivos"] == 5
    assert data["archivos_saltados"] == 5


def test_defecto2_denominador_cuenta_todos_los_archivos_no_solo_los_medidos(
    ml_vault, capsys, monkeypatch
):
    """Con 3 archivos en disco donde 1 no tiene líneas útiles, el denominador de "archivos
    multi-columna" debía decir 2 (sólo los medidos) en vez de 3 (todos los .txt encontrados) — el
    segundo número medido de la auditoría. Se chequea en la tabla legible Y en el --json."""
    _write_txt(ml_vault, "test_star", "a", TEXTO_UTIL)
    _write_txt(ml_vault, "test_star", "b", TEXTO_UTIL)
    _write_txt(ml_vault, "test_star", "c", TEXTO_SIN_LINEAS_UTILES)

    monkeypatch.setattr(sys, "argv", ["measure_layout.py"])
    rc = measure_layout.main()
    salida = capsys.readouterr().out
    assert rc == 0
    m = re.search(r"archivos multi-columna\s+(\d+)\s*/\s*(\d+)", salida)
    assert m is not None, salida
    assert int(m.group(2)) == 3, "el denominador debe contar los 3 .txt en disco, no sólo los 2 medidos"

    monkeypatch.setattr(sys, "argv", ["measure_layout.py", "--json"])
    rc = measure_layout.main()
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["archivos"] == 3
    assert data["archivos_saltados"] == 1


# ── denominador cero en `analizar()` ─────────────────────────────────────────────────────────────

def test_analizar_sin_lineas_utiles_no_revienta_por_denominador_cero():
    """`analizar` sobre un texto sin líneas ≥ MIN_LINEA no debe intentar dividir por `len(lineas)`
    en cero (ZeroDivisionError) — debe devolver el degenerado `frac: 0.0`."""
    m = measure_layout.analizar(TEXTO_SIN_LINEAS_UTILES)
    assert m == {"utiles": 0, "canaleta": 0, "guion": 0, "frac": 0.0}


def test_analizar_detecta_canaleta_y_guion_y_calcula_la_fraccion():
    """Caza una regresión en el conteo/fracción: una línea con canaleta (dos no-espacios separados
    por ≥ CANALETA_MIN espacios) y una línea con corte de guión al final, ambas ≥ MIN_LINEA."""
    linea_canaleta = (
        "columna uno con texto de relleno"
        + " " * measure_layout.CANALETA_MIN
        + "columna dos con mas texto de relleno"
    )
    linea_guion = "esta linea larga termina con una palabra partida por guio-"
    assert len(linea_canaleta.strip()) >= measure_layout.MIN_LINEA
    assert len(linea_guion.strip()) >= measure_layout.MIN_LINEA

    m = measure_layout.analizar(linea_canaleta + "\n" + linea_guion + "\n")
    assert m["utiles"] == 2
    assert m["canaleta"] == 1
    assert m["guion"] == 1
    assert m["frac"] == pytest.approx(0.5)


# ── --json parseable con las claves documentadas ─────────────────────────────────────────────────

def test_json_es_parseable_y_trae_las_claves_documentadas(ml_vault, capsys, monkeypatch):
    _write_txt(ml_vault, "test_star", "2020Test", TEXTO_UTIL)
    monkeypatch.setattr(sys, "argv", ["measure_layout.py", "--json"])

    rc = measure_layout.main()
    salida = capsys.readouterr().out
    data = json.loads(salida)  # explota si no es JSON válido

    assert rc == 0
    for clave in (
        "archivos",
        "archivos_saltados",
        "multicolumna",
        "lineas_utiles",
        "lineas_con_canaleta",
        "lineas_con_guion",
        "umbral_archivo",
    ):
        assert clave in data, f"falta la clave documentada '{clave}' en el --json"
    assert data["archivos"] == 1
    assert data["archivos_saltados"] == 0
    assert data["umbral_archivo"] == measure_layout.UMBRAL_ARCHIVO


def test_json_con_por_slug_desglosa_por_slug(ml_vault, capsys, monkeypatch):
    _write_txt(ml_vault, "test_star", "2020Test", TEXTO_UTIL)
    monkeypatch.setattr(sys, "argv", ["measure_layout.py", "--json", "--por-slug"])

    rc = measure_layout.main()
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "por_slug" in data
    assert "test_star" in data["por_slug"]


# ── early-returns (exit 0, mensaje a stderr) ─────────────────────────────────────────────────────

def test_early_return_sin_directorio_fulltext(tmp_path, capsys, monkeypatch):
    """`vault/raw/fulltext` no existe en absoluto — caso distinto de "existe pero está vacío"."""
    monkeypatch.setattr(measure_layout, "RAW", tmp_path / "raw")
    monkeypatch.setattr(measure_layout, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["measure_layout.py"])

    rc = measure_layout.main()
    err = capsys.readouterr().err
    assert rc == 0
    assert "no existe" in err


def test_early_return_slug_inexistente(ml_vault, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["measure_layout.py", "slug-que-no-existe"])

    rc = measure_layout.main()
    err = capsys.readouterr().err
    assert rc == 0
    assert "slug-que-no-existe" in err


def test_early_return_sin_txt_en_el_arbol(ml_vault, capsys, monkeypatch):
    """`fulltext/` existe pero no tiene ni un .txt (ni siquiera un subdirectorio de slug)."""
    monkeypatch.setattr(sys, "argv", ["measure_layout.py"])

    rc = measure_layout.main()
    err = capsys.readouterr().err
    assert rc == 0
    assert "sin .txt" in err


# ── CANALETA_MIN — contrato compartido con test_multicolumn_matching.py (#46) ────────────────────

def test_canaleta_min_sigue_siendo_el_minimo_que_usa_gutter():
    """`test_multicolumn_matching.py` importa `CANALETA_MIN` como single source de verdad del
    tamaño de canaleta (#46). Si alguien lo renombra, lo borra o lo desincroniza de `GUTTER`, esa
    regresión queda muda ahí — este test la caza acá, donde vive la constante."""
    assert isinstance(measure_layout.CANALETA_MIN, int)
    assert measure_layout.CANALETA_MIN > 0

    justo = "a" + " " * measure_layout.CANALETA_MIN + "b"
    un_espacio_menos = "a" + " " * (measure_layout.CANALETA_MIN - 1) + "b"
    assert measure_layout.GUTTER.search(justo)
    assert not measure_layout.GUTTER.search(un_espacio_menos)
