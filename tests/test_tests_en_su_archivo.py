"""Un test vive en el archivo del módulo que prueba, o las redes por módulo no lo ven (#439).

`mutar --dirigida` y `--guardas` (AUD-213) corren SÓLO `tests/test_<módulo>.py` — a propósito, es
lo que las hace baratas — así que una función testeada desde otro archivo sale «sin test propio que
la mate» aunque tenga diez. Medido cerrando #437: 9 guardas de `quote_verdict`, el juez del gate de
cierre (#324), reportadas vivas con doce tests escritos en `tests/test_lib_config.py`. Por AST: 36
funciones en 11 módulos en la misma situación. Ratchet: sólo baja, y un nombre nuevo fuera de
`conocidos` pone esto en rojo aunque el total no suba.
"""
from __future__ import annotations

import ast
import re
import warnings
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
RATCHET = RAIZ / "tools" / "tests-ratchet.yaml"


def funciones_testeadas_desde_otro_archivo() -> list[str]:
    """`archivo.py::función` de `scripts/`+`tools/` que ALGÚN `tests/test_*.py` llama y
    `tests/test_<módulo>.py` no. Funciones públicas: las `_privadas` se prueban a través de quien
    las llama, y exigirles archivo propio sería pedir tests de implementación."""
    tests = {p.name: p.read_text(encoding="utf-8") for p in (RAIZ / "tests").glob("test_*.py")}
    out = []
    for mod in sorted((RAIZ / "scripts").glob("*.py")) + sorted((RAIZ / "tools").glob("*.py")):
        propio = f"test_{mod.stem}.py"
        src = tests.get(propio, "")
        for n in ast.walk(ast.parse(mod.read_text(encoding="utf-8"))):
            if not isinstance(n, ast.FunctionDef) or n.name.startswith("_"):
                continue
            pat = re.compile(r"\b" + re.escape(n.name) + r"\(")
            if pat.search(src):
                continue
            if any(t != propio and pat.search(s) for t, s in tests.items()):
                out.append(f"{mod.name}::{n.name}")
    return sorted(out)


def test_ninguna_funcion_NUEVA_se_testea_solo_desde_otro_archivo():
    """El detector mira dónde se LLAMA la función, no dónde se define el test: `cfg.quote_verdict(`
    en `test_lib_config.py` cuenta como test de `lib_quotes` desde otro archivo, que es el caso
    medido (la re-exportación no cambia qué archivo mira `--guardas`)."""
    hoy = funciones_testeadas_desde_otro_archivo()
    ratchet = yaml.safe_load(RATCHET.read_text(encoding="utf-8")) or {}
    techo, conocidos = int(ratchet.get("techo", 0)), set(ratchet.get("conocidos") or [])
    nuevos = [x for x in hoy if x not in conocidos]
    assert not nuevos, (
        "funciones NUEVAS testeadas sólo desde el archivo de OTRO módulo — `mutar --dirigida` y "
        "`--guardas` no van a ver esos tests (#439). Mové el test a `tests/test_<módulo>.py`:\n  "
        + "\n  ".join(nuevos))
    assert len(hoy) <= techo, f"{len(hoy)} > techo {techo}:\n  " + "\n  ".join(hoy)
    if len(hoy) < techo:
        warnings.warn(f"bajó a {len(hoy)} (techo {techo}): actualizá `techo` y `conocidos` en "
                      f"{RATCHET.name}", stacklevel=2)


def test_el_detector_ve_la_llamada_re_exportada():
    """Regla de método 3: el detector tiene que morir por la línea que prueba. Sobre el propio repo,
    `lib_quotes.py::quote_verdict` NO puede estar en la lista (se mudó en #439) y la lista tiene que
    ser un subconjunto de `conocidos` — si el detector dejara de ver llamadas, la lista quedaría
    vacía y el ratchet «pasaría» sin mirar (D-43)."""
    hoy = funciones_testeadas_desde_otro_archivo()
    assert "lib_quotes.py::quote_verdict" not in hoy
    conocidos = set((yaml.safe_load(RATCHET.read_text(encoding="utf-8")) or {}).get("conocidos") or [])
    assert conocidos, "el ratchet declara su deuda; vacío no es «no hay»"
    assert set(hoy) <= conocidos
