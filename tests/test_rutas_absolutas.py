"""INV-66 — ninguna ruta absoluta de la máquina llega a un archivo versionado.

El invariante estaba enunciado desde siempre y su **única** marca era la de
`tests/test_mailto_paridad.py`, que prueba el polite pool: una marca mal atribuida (hallazgo del
frente D de la pasada `/auditar` del 2026-08-28). O sea que INV-66 no tenía test y el ratchet
sub-reportaba —decía 6 sin test cuando eran 7—, que es peor que un techo alto: **un mapa que
atribuye mal es peor que uno vacío** (regla de método #4).

Se cierra escribiendo el test que el invariante pide, no subiendo el techo.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# Prefijos de ruta absoluta de las tres plataformas. `C:\` va sin `re.I`: `c:` en prosa es común.
ABSOLUTA = re.compile(r"(?<![\w.])(?:/home/|/Users/|/root/|C:\\\\)")
# Un `/home/agus/...` dentro de una cadena de EJEMPLO en prosa de doc sería un falso positivo, así
# que el barrido es sobre CÓDIGO y config, no sobre `.md`: la doc puede citar la ruta de alguien
# para explicar un caso. El daño que INV-66 nombra es el puntero que el código usa.
EXT = (".py", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".json")


# Este archivo se excluye de su propio barrido: contiene los prefijos por construcción (la regex y
# el comentario que la explica). ⚠ No es una excepción cómoda — es la única, va nombrada, y el test
# de abajo fija que el barrido igual mira el resto del árbol. Se descubrió al commitear: mientras el
# archivo estaba **sin trackear**, `git ls-files` no lo devolvía y el test pasaba; o sea que el
# «verlo morir» de la regla de método #3 se había hecho sobre una población que no era la final.
YO = "tests/test_rutas_absolutas.py"


def _versionados() -> list[Path]:
    r = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True)
    return [RAIZ / f for f in r.stdout.split() if f.endswith(EXT) and f != YO]


def test_ningun_archivo_versionado_lleva_una_ruta_absoluta_de_maquina():
    """  @inv INV-66"""
    hits = []
    for f in _versionados():
        try:
            texto = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, ln in enumerate(texto.split("\n"), 1):
            if ABSOLUTA.search(ln):
                hits.append(f"{f.relative_to(RAIZ)}:{n}: {ln.strip()[:90]}")
    assert hits == [], (
        "rutas absolutas de la máquina en archivos versionados — no viajan entre máquinas:\n  "
        + "\n  ".join(hits))


def test_el_barrido_mira_algo():
    """Sin esto, un `git ls-files` que devuelva vacío daría verde: el cero que nadie midió."""
    assert len(_versionados()) > 50, "el barrido no encontró archivos versionados que mirar"
