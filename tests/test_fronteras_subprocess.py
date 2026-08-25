"""Las tres fronteras con subprocess que sobrevivían a la mutación, probadas con un doble.

Red #2 del `CLAUDE.md`: los tres módulos prometen la misma forma —lanzar un comando, leer su
salida y **degradar sin lanzar** si el comando no está—, así que se prueban una vez parametrizada
en vez de con prosa en tres docstrings.

Salieron del issue #97: eran 3 de las 8 funciones que sobrevivían al gate de mutación. Las otras 5
son clientes de red de verdad y piden un smoke test contra el servicio real (regla de método #1),
que es otra cosa y va aparte.

⚠ Lo que estos tests fijan es el **contrato de degradación**, que es lo que hace que la cadena no
muera por un detalle de entorno: sin `tesseract` no hay OCR pero el ingest sigue; sin Node no hay
snapshot web pero el resto corre. Un `Exception` acá mataría una pasada entera.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import extract_fulltext            # noqa: E402
import fetch_web                   # noqa: E402
import sweep_external              # noqa: E402
import lib_config as cfg           # noqa: E402


class _R:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


# (módulo, función, salida simulada, lo que debe devolver, valor de degradación)
VERSIONES = [
    pytest.param(extract_fulltext, "tesseract_version",
                 _R(stdout="tesseract 5.3.0\nleptonica-1.82\n"), "tesseract 5.3.0",
                 "tesseract (versión desconocida)", id="tesseract"),
    pytest.param(fetch_web, "defuddle_version",
                 _R(stdout="  0.4.1\n"), "0.4.1", "desconocida", id="defuddle"),
]


@pytest.mark.parametrize("mod, fn, salida, esperado, degradado", VERSIONES)
def test_lee_la_version_de_la_salida_del_comando(mod, fn, salida, esperado, degradado, monkeypatch):
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: salida)
    assert getattr(mod, fn)() == esperado


@pytest.mark.parametrize("mod, fn, salida, esperado, degradado", VERSIONES)
def test_sin_el_binario_degrada_y_no_lanza(mod, fn, salida, esperado, degradado, monkeypatch):
    def no_esta(*a, **k):
        raise FileNotFoundError(a[0][0] if a and a[0] else "cmd")
    monkeypatch.setattr(mod.subprocess, "run", no_esta)
    assert getattr(mod, fn)() == degradado


@pytest.mark.parametrize("mod, fn, salida, esperado, degradado", VERSIONES)
def test_un_timeout_tampoco_lanza(mod, fn, salida, esperado, degradado, monkeypatch):
    def cuelga(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)
    monkeypatch.setattr(mod.subprocess, "run", cuelga)
    assert getattr(mod, fn)() == degradado


def test_tesseract_lee_stderr_si_stdout_viene_vacio(monkeypatch):
    """`tesseract --version` escribe en stderr en varias builds; por eso el `or`."""
    monkeypatch.setattr(extract_fulltext.subprocess, "run",
                        lambda *a, **k: _R(stdout="", stderr="tesseract 4.1.1\notra\n"))
    assert extract_fulltext.tesseract_version() == "tesseract 4.1.1"


def test_run_lanza_el_script_de_la_boveda_y_propaga_su_codigo(monkeypatch):
    """`_run` es el que dispara cada detector de la pasada de red: si perdiera el returncode, un
    detector fallido se leería como exitoso y `_cubrir` estamparía `cubrio:` sobre una pasada que
    no corrió — el mismo registro falso que AUD-43 cerró por la otra punta."""
    visto = {}

    def fake(cmd, **k):
        visto["cmd"], visto["cwd"] = cmd, k.get("cwd")
        return _R(returncode=3)

    monkeypatch.setattr(sweep_external.subprocess, "run", fake)
    assert sweep_external._run("check_retractions.py", "--slug", "tau_ceti") == 3
    assert visto["cmd"][0] == sys.executable
    assert visto["cmd"][1].endswith("scripts/check_retractions.py")
    assert visto["cmd"][2:] == ["--slug", "tau_ceti"]
    assert Path(visto["cwd"]) == cfg.ROOT / "scripts"
