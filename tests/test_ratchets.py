"""Los CUATRO ratchets del repo no se aflojan en silencio (AUD-139 / INV-140).

`trazabilidad`, `idioma`, `cobertura` y `mutación` llevan los cuatro la misma promesa escrita —«el
techo sólo puede bajar»— y hasta 1.73.0 la mecánica que la sostenía existía **sólo** para el
primero, hardcodeada en `trace_invariants`. En los otros tres nada impedía subir el techo en el
mismo commit que rompía la cobertura: el agujero que #96 cerró una vez, abierto en tres copias.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lib_config as cfg

RAIZ = Path(__file__).resolve().parents[1]

# `(archivo, campos)` — la lista es el contrato: un ratchet nuevo que no entre acá queda sin guarda,
# que es exactamente el estado que AUD-139 encontró.
RATCHETS = [
    ("docs/trazabilidad-ratchet.yaml", ("sin_marca", "sin_test")),
    ("tools/idioma-ratchet.yaml", ("techo", "docstrings_castellano", "sin_docstring")),
    ("tools/cobertura-ratchet.yaml", ("techo",)),
    ("tools/mutacion-ratchet.yaml", ("techo",)),
]


@pytest.mark.parametrize("rel,campos", RATCHETS, ids=[r for r, _ in RATCHETS])
def test_los_cuatro_ratchets_no_aflojan(rel, campos):
    """El árbol real: ningún techo subió respecto de `HEAD` sin escotilla declarada.  @inv INV-140"""
    subidas = cfg.ratchet_raises(rel, campos, RAIZ)
    if subidas is None:
        pytest.skip("no evaluable: sin git, o el archivo todavía no está en HEAD")
    assert subidas == [], f"techo(s) subidos sin escotilla en {rel}: {subidas}"


@pytest.fixture
def repo_git(tmp_path: Path) -> Path:
    """Un repo git de verdad con un ratchet commiteado — `ratchet_raises` compara contra `HEAD`."""
    (tmp_path / "tools").mkdir()
    yaml_rel = "tools/x-ratchet.yaml"
    (tmp_path / yaml_rel).write_text("techo: 3\n", encoding="utf-8")
    for cmd in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
                   cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_una_subida_sin_escotilla_se_reporta(repo_git: Path):
    """Sin esto, subir el techo y romper la cobertura entra en el mismo commit y sale verde."""
    (repo_git / "tools" / "x-ratchet.yaml").write_text("techo: 5\n", encoding="utf-8")
    assert cfg.ratchet_raises("tools/x-ratchet.yaml", ("techo",), repo_git) == [("techo", 3, 5)]


def test_bajar_el_techo_siempre_pasa(repo_git: Path):
    (repo_git / "tools" / "x-ratchet.yaml").write_text("techo: 1\n", encoding="utf-8")
    assert cfg.ratchet_raises("tools/x-ratchet.yaml", ("techo",), repo_git) == []


def test_la_escotilla_esta_atada_a_la_transicion(repo_git: Path):
    """Y por eso **caduca sola**: una escotilla genérica quedaría en el archivo para siempre y la
    subida siguiente pasaría gratis amparada por el motivo de la anterior.  @inv INV-140"""
    f = repo_git / "tools" / "x-ratchet.yaml"
    f.write_text("techo: 5\n# ratchet-sube: techo 3→5 — entraron dos casos que nadie puede cubrir\n",
                 encoding="utf-8")
    assert cfg.ratchet_raises("tools/x-ratchet.yaml", ("techo",), repo_git) == []

    # la MISMA escotilla no cubre la subida siguiente
    f.write_text("techo: 7\n# ratchet-sube: techo 3→5 — entraron dos casos que nadie puede cubrir\n",
                 encoding="utf-8")
    assert cfg.ratchet_raises("tools/x-ratchet.yaml", ("techo",), repo_git) == [("techo", 3, 7)]

    # y una escotilla SIN motivo tampoco: un gate no se afloja en silencio
    f.write_text("techo: 5\n# ratchet-sube: techo 3→5 —\n", encoding="utf-8")
    assert cfg.ratchet_raises("tools/x-ratchet.yaml", ("techo",), repo_git) == [("techo", 3, 5)]


def test_sin_git_es_no_evaluado_no_un_verde(tmp_path: Path):
    """`None` es *no evaluado* (D-43): fuera de un repo el chequeo no puede correr, y devolver `[]`
    lo haría indistinguible de «miré y ningún techo subió»."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "x-ratchet.yaml").write_text("techo: 3\n", encoding="utf-8")
    assert cfg.ratchet_raises("tools/x-ratchet.yaml", ("techo",), tmp_path) is None


def test_campo_ausente_o_no_numerico_no_inventa_una_subida(repo_git: Path):
    """Un techo que no está no es un techo 0: compararlo contra 0 fabricaría subidas."""
    (repo_git / "tools" / "x-ratchet.yaml").write_text("otra_cosa: 9\n", encoding="utf-8")
    assert cfg.ratchet_raises("tools/x-ratchet.yaml", ("techo",), repo_git) == []
