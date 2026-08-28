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

import pytest

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
    """Los archivos VERSIONADOS que este invariante mira, de `git ls-files`.

    ⛔ **Sin repo git, esto SKIPEA con motivo — no degrada a caminar el árbol.** La población de
    INV-66 son los archivos *versionados*, y sin git no se puede saber cuáles son: medido el
    2026-08-28, el fallback por árbol levantaba `.claude/settings.local.json` —lleno de rutas
    absolutas y perfectamente ignorado, pero por el `~/.config/git/ignore` **global**, que ninguna
    regla local puede reproducir—. Dos poblaciones distintas dando veredictos opuestos es justo lo
    que D-43 prohíbe.

    Y hace falta porque `tools/mutar.py` copia el repo **sin `.git`**: con `check=True` pelado, este
    test reventaba dentro de la copia y el gate de mutación —la red #1— se negaba a correr entero.
    Un test agregado hoy dejaba inoperable el gate que audita a todos los demás.

    El skip **con motivo visible** es el precedente que el propio framework bendice para el tier 2
    (`pytest.ini`: *«`instancia` sin la env var skipea con motivo visible, nunca pasa en silencio»*).
    """
    try:
        r = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        pytest.skip(f"sin repo git ({exc.__class__.__name__}): la población de INV-66 son los "
                    f"archivos VERSIONADOS y sin git no se puede saber cuáles son")
    return [RAIZ / f for f in r.stdout.split()
            if f.endswith(EXT) and f != YO]


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
    """Sin esto, una población vacía daría verde: el cero que nadie midió."""
    assert len(_versionados()) > 50, "el barrido no encontró archivos versionados que mirar"
