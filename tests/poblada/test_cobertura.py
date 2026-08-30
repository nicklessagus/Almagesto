"""Ninguna función de `scripts/` puede quedar SIN EJECUTARSE por la suite.

No pide que esté bien probada: pide saber **cuáles no mira nadie**. Medido en esta sesión,
`citation_index._fetch_ads_default` y `_resolver_default` —las rutas de red de verdad— tenían cero
ejecuciones, y eso no lo dice ningún test: los dobles se inyectan siempre.

Es el hermano barato del gate de mutación (`tools/mutar.py`): una función nunca ejecutada
**siempre** sobrevive a la mutación, así que esto la detecta en 15 s en vez de en una corrida por
función. Ratchet: el número de no-ejecutadas sólo puede bajar.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.poblada

RAIZ = Path(__file__).resolve().parent.parent.parent
RATCHET = RAIZ / "tools" / "cobertura-ratchet.yaml"


def _sin_ejecutar(tmp_path) -> list[str]:
    """Corre la suite tier 0 bajo `coverage` y devuelve `archivo::funcion` sin un solo hit."""
    datafile = tmp_path / ".coverage"
    r_run = subprocess.run([sys.executable, "-m", "coverage", "run", "--source=scripts",
                            f"--data-file={datafile}", "-m", "pytest", "tests/", "-q", "--no-header"],
                           cwd=RAIZ, capture_output=True, text=True, timeout=900)
    salida = tmp_path / "cov.json"
    r_json = subprocess.run([sys.executable, "-m", "coverage", "json", f"--data-file={datafile}",
                             "-o", str(salida)], cwd=RAIZ, capture_output=True, text=True,
                            timeout=300)
    # D-43 — un chequeo que NO PUDO CORRER se declara con su motivo, no muere con un
    # `FileNotFoundError` sobre el archivo que el paso anterior no llegó a escribir. Medido: en CI
    # faltaba `coverage` en las deps del job y el fallo se leía como «falta cov.json», que manda a
    # buscar el defecto donde no está.
    if not salida.exists():
        raise AssertionError(
            "el barrido de cobertura NO PUDO CORRER, así que este test no midió nada (D-43).\n"
            f"  `coverage run` rc={r_run.returncode}: {(r_run.stderr or r_run.stdout or '')[-400:]}\n"
            f"  `coverage json` rc={r_json.returncode}: {(r_json.stderr or '')[-200:]}\n"
            "  ¿está instalado `coverage` en este entorno?")
    datos = json.loads(salida.read_text(encoding="utf-8"))
    import ast
    faltan = []
    for arch, info in sorted(datos.get("files", {}).items()):
        ejecutadas = set(info.get("executed_lines") or [])
        fuente = (RAIZ / arch).read_text(encoding="utf-8")
        for n in ast.walk(ast.parse(fuente)):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            cuerpo = [x for x in range(n.body[0].lineno, (n.end_lineno or 0) + 1)]
            if not (set(cuerpo) & ejecutadas):
                faltan.append(f"{Path(arch).name}::{n.name}")
    return sorted(faltan)


def test_ninguna_funcion_queda_sin_ejecutar(tmp_path):
    faltan = _sin_ejecutar(tmp_path)
    techo = (yaml.safe_load(RATCHET.read_text(encoding="utf-8")) or {}) if RATCHET.exists() else {}
    n_techo = techo.get("techo", 0)
    assert len(faltan) <= n_techo, (
        f"{len(faltan)} funciones sin ejecutar (techo {n_techo}) — la suite no las mira:\n  "
        + "\n  ".join(faltan))
    if len(faltan) < n_techo:
        # AUD-50: acá había `pytest.warns  # noqa`, una sentencia no-op (referencia el atributo sin
        # llamarlo, y el noqa callaba al linter). El `print` se lo traga pytest salvo con `-s`, así
        # que bajar del techo no producía NINGUNA señal visible. Su hermano
        # `test_invariantes_instancia.py` ya lo hacía bien con `warnings.warn`.
        import warnings
        warnings.warn(f"cobertura bajó a {len(faltan)} (techo {n_techo}): "
                      f"actualizá `techo` en {RATCHET.name}", stacklevel=2)
        print(f"✅ bajó a {len(faltan)}: actualizá `techo` en {RATCHET.name}")
