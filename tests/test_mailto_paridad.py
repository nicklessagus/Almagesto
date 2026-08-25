"""Los dos `_mailto` (Crossref y OpenAlex) son gemelos: se prueban UNA VEZ, parametrizado.

Red #2 del CLAUDE.md: *si N módulos prometen la misma forma, se prueba una vez parametrizada, no con
prosa en N docstrings*. Los dos leen `git config user.email` para el "polite pool" de su API, los dos
prometen no hardcodear la dirección (es per-instancia) y los dos degradan al pool público si no hay.

Salieron de la pasada `/auditar` del 2026-08-24: eran 2 de las 10 funciones que sobrevivían al gate
de mutación, y las únicas de esas 10 que no necesitan red —leen un subprocess local— o sea las más
baratas de bajar del techo (AUD-35).

⚠ La única diferencia entre los dos es el **valor de ausencia**, y es deliberada: Crossref devuelve
`None` (el llamador arma el User-Agent con o sin mailto) y OpenAlex `""` (va como query param). Por
eso el vacío se parametriza en vez de asumirse igual — si alguien los "unifica", este test lo dice.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_retractions          # noqa: E402
import openalex                   # noqa: E402

GEMELOS = [
    pytest.param(check_retractions, None, id="crossref"),
    pytest.param(openalex, "", id="openalex"),
]


@pytest.mark.parametrize("mod, vacio", GEMELOS)
def test_mailto_toma_el_email_de_git_config(mod, vacio, monkeypatch):
    """  @inv INV-66"""
    class R:
        stdout = "  alguien@example.org \n"
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: R())
    assert mod._mailto() == "alguien@example.org", "se usa el email de git config, sin espacios"


@pytest.mark.parametrize("mod, vacio", GEMELOS)
def test_mailto_sin_email_configurado_cae_al_pool_publico(mod, vacio, monkeypatch):
    class R:
        stdout = "\n"
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: R())
    assert mod._mailto() == vacio


@pytest.mark.parametrize("mod, vacio", GEMELOS)
def test_mailto_no_propaga_el_fallo_de_git(mod, vacio, monkeypatch):
    """Sin `git` en el PATH (o con el repo roto) la consulta a la API sigue: el mailto es cortesía,
    no un requisito. Que esto lance mataría una pasada entera por un detalle de entorno."""
    def explota(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(mod.subprocess, "run", explota)
    assert mod._mailto() == vacio


@pytest.mark.parametrize("mod, vacio", GEMELOS)
def test_mailto_no_hardcodea_ninguna_direccion(mod, vacio):
    """La promesa explícita de los dos docstrings: la dirección es per-instancia. `openalex` tenía
    una de ejemplo fija y toda request salía con un mail falso — lo contrario de la cortesía que el
    pool pide."""
    fuente = (SCRIPTS / f"{mod.__name__}.py").read_text(encoding="utf-8")
    assert "@example." not in fuente.split('"""', 2)[-1], "dirección hardcodeada fuera del docstring"
