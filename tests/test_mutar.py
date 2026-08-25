"""El gate de mutación (red #1) tiene que ver el código NUEVO.

`--diff` seleccionaba con `git diff --name-only HEAD`, que **no lista untracked**. O sea que un
archivo recién creado en `scripts/` —el caso exacto para el que existe la regla «toda función nueva
de `scripts/` pasa por esto antes de cerrar el issue»— quedaba fuera, y el gate salía en verde sin
haberlo mirado. Medido el 2026-08-25: `extraction_prompt.py` (dos funciones nuevas) no se mutó.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import mutar


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "scripts").mkdir(parents=True)
    (r / "scripts" / "viejo.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t"); _git(r, "config", "user.name", "t")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    return r


def test_diff_incluye_el_archivo_nuevo_sin_trackear(repo: Path, monkeypatch):
    """Es el caso que la regla nombra: función nueva de `scripts/`."""
    # @inv INV-101
    (repo / "scripts" / "nuevo.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    monkeypatch.setattr(mutar, "RAIZ", repo)
    nombres = {p.name for p in mutar.archivos_del_diff()}
    assert "nuevo.py" in nombres, "el gate no ve el código nuevo: sale verde sin mirarlo"


def test_diff_sigue_incluyendo_el_archivo_modificado(repo: Path, monkeypatch):
    (repo / "scripts" / "viejo.py").write_text("def f():\n    return 99\n", encoding="utf-8")
    monkeypatch.setattr(mutar, "RAIZ", repo)
    assert {p.name for p in mutar.archivos_del_diff()} == {"viejo.py"}


def test_diff_no_trae_lo_que_esta_fuera_de_scripts_ni_lo_ignorado(repo: Path, monkeypatch):
    # @inv INV-101
    (repo / ".gitignore").write_text("scripts/ignorado.py\n", encoding="utf-8")
    (repo / "scripts" / "ignorado.py").write_text("def h(): return 3\n", encoding="utf-8")
    (repo / "otro.py").write_text("def i(): return 4\n", encoding="utf-8")
    (repo / "scripts" / "notas.md").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(mutar, "RAIZ", repo)
    nombres = {p.name for p in mutar.archivos_del_diff()}
    assert nombres == set(), f"coló algo que no es código nuevo de scripts/: {nombres}"


def test_diff_no_repite_un_archivo_nuevo_ya_stageado(repo: Path, monkeypatch):
    """Un archivo agregado con `git add` aparece en el diff Y en el listado de untracked de
    algunas configuraciones: mutarlo dos veces duplicaría el costo del gate."""
    (repo / "scripts" / "nuevo.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    _git(repo, "add", "scripts/nuevo.py")
    monkeypatch.setattr(mutar, "RAIZ", repo)
    encontrados = [p.name for p in mutar.archivos_del_diff()]
    assert encontrados.count("nuevo.py") == 1
