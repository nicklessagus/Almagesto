"""El aislamiento del corpus de test cubre TODAS las constantes de path de `lib_config` (#461).

Sin esto el mapa se escribía a mano en dos conftest y ya divergió una vez: `EXTRACCION` faltaba en
el de `poblada`, así que los nueve módulos que la leen —entre ellos `lib_quotes`, el juez de citas
de #324, y `entity`/`replace_pdf`, que además ESCRIBEN— veían la bóveda real de la máquina desde el
corpus sintético. Medido en una instancia poblada: `extraccion_despaginada (68)` —el conteo de la
bóveda de verdad— rompiendo los dos tests que existen para fijar el comportamiento del lint, verdes
en el template (bóveda semilla, 0 extracciones) y rojos en cualquier instancia.

⛔ Es el corolario de INV-101 un nivel más abajo: **una red que no mira lo mismo que el código no es
una red**. Acá el gate `poblada` no podía distinguir «regresión» de «bóveda poblada».
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import lib_config as cfg

# ⚠ Por ruta y no por `from conftest import …`: hay DOS conftest en el path (`tests/` y
# `tests/poblada/`) y el import resolvía al de arriba, que es justamente el que NO divergió.
_spec = importlib.util.spec_from_file_location(
    "_poblada_conftest", Path(__file__).parent / "conftest.py")
_conf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_conf)
_PATH_ATTRS = _conf._PATH_ATTRS


def constantes_de_path() -> set:
    """Las constantes de módulo de `lib_config` que son un `Path`, leídas del módulo y no de una
    lista: si mañana aparece una nueva, este test la exige sin que nadie se acuerde."""
    return {n for n in dir(cfg) if n.isupper() and isinstance(getattr(cfg, n), Path)}


@pytest.mark.poblada
def test_461_el_mapa_de_aislamiento_cubre_TODA_constante_de_path():
    faltan = constantes_de_path() - set(_PATH_ATTRS)
    assert not faltan, (
        f"{sorted(faltan)} no está(n) en `_PATH_ATTRS`: los módulos que la(s) lean van a ver la "
        f"BÓVEDA REAL de la máquina desde el corpus sintético (#461). Agregala(s) al mapa de "
        f"`_build_paths` y a esta tupla — las dos, en este mismo cambio.")
    sobran = set(_PATH_ATTRS) - constantes_de_path()
    assert not sobran, f"{sorted(sobran)} ya no existe(n) en `lib_config`: sacala(s) del mapa"


@pytest.mark.poblada
def test_461_el_corpus_sintetico_APUNTA_ahi(boveda_poblada):
    """Y la otra mitad: que estén en la lista no alcanza si el fixture no las re-apunta."""
    for attr in _PATH_ATTRS:
        real = getattr(cfg, attr)
        assert str(real).startswith(str(boveda_poblada.ROOT)), \
            f"`cfg.{attr}` apunta a {real}, fuera del corpus sintético (#461)"
