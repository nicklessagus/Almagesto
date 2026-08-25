"""`merge=ours` sin driver registrado: la protección de los archivos de instancia no existe (#99).

Salió del clean-room del 2026-08-25: `.gitattributes` pide registrar el driver «una vez por clon» y
**nada lo verifica** — ni el lint, ni la cadena, ni un hook. Medido sobre tres clones reales, dos no
lo tenían. Es la misma familia que #93: un mecanismo de protección cuya precondición falla en
silencio.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lib_config as cfg
import lint


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env={"PATH": "/usr/bin:/bin", "HOME": str(repo)})


@pytest.fixture
def clon(tmp_path, monkeypatch):
    """Un repo git de verdad con `.gitattributes` declarando `merge=ours`, y un commit inicial."""
    repo = tmp_path / "clon"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    (repo / ".gitattributes").write_text("vault/config/objective.yaml merge=ours\n", encoding="utf-8")
    (repo / "vault" / "config").mkdir(parents=True)
    (repo / "vault" / "config" / "objective.yaml").write_text("name: X\n", encoding="utf-8")
    _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "init")
    monkeypatch.setattr(cfg, "ROOT", repo)
    return repo


def test_sin_driver_y_con_cambios_propios_se_reporta(clon):
    """El caso que #99 cubre: la instancia personalizó su config y un `git pull` la pisaría."""
    (clon / "vault" / "config" / "objective.yaml").write_text("name: MI TEMA\n", encoding="utf-8")
    riesgo, err = lint.merge_ours_unprotected()
    assert err is None
    assert riesgo == ["vault/config/objective.yaml"], riesgo


def test_sin_driver_pero_sin_cambios_no_se_reporta(clon):
    """Un clon recién hecho —el template, cualquier corrida de CI— no tiene nada que perder: el
    archivo se re-escribiría idéntico. Sin este recorte el chequeo hablaba SIEMPRE, y un hallazgo
    que aparece siempre se deja de mirar."""
    assert lint.merge_ours_unprotected() == ([], None)


def test_con_driver_registrado_no_se_reporta_aunque_haya_cambios(clon):
    """El lado positivo del contrato: registrar el driver es exactamente lo que apaga el hallazgo."""
    (clon / "vault" / "config" / "objective.yaml").write_text("name: MI TEMA\n", encoding="utf-8")
    _git(clon, "config", "merge.ours.driver", "true")
    assert lint.merge_ours_unprotected() == ([], None)


def test_sin_gitattributes_el_chequeo_no_aplica(clon):
    """«No aplica» ≠ «no evaluado» (D-43). Sin nada declarado no hay protección que verificar, y
    mandarlo a *no evaluado* pondría en rojo toda bóveda sin `.gitattributes`."""
    (clon / ".gitattributes").unlink()
    assert lint.merge_ours_unprotected() == ([], None)


def test_sin_git_el_chequeo_no_aplica(clon, monkeypatch):
    """`merge=ours` es un mecanismo de git: sin git no hay `pull` que pueda pisar nada.

    Mandarlo a *no evaluado* —que cuenta para el exit— ponía en rojo toda copia sin `.git`,
    incluida la que arma `tools/mutar.py`, y ahí se detectó: el gate abortó con «la suite ya está
    roja sin mutar». Es distinto del caso de la verificación stale (D-43), donde sin git queda algo
    real sin medir; acá no queda nada."""
    monkeypatch.setattr(lint, "git_out", lambda *a: None)
    assert lint.merge_ours_unprotected() == ([], None)
