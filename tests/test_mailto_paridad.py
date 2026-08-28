"""Los dos `_mailto` (Crossref y OpenAlex) son gemelos: se prueban UNA VEZ, parametrizado.

Red #2 del CLAUDE.md: *si N módulos prometen la misma forma, se prueba una vez parametrizada, no con
prosa en N docstrings*. Los dos leen el mismo lector opt-in (`lib_config.get_mailto`) para el "polite
pool" de su API, los dos prometen no hardcodear la dirección (es per-instancia) y los dos degradan al
pool público si no hay.

⛔ **Desde 2026-08-28 el mailto NO sale de `git config user.email`.** Esa dirección es dato personal
del operador, entregado a git para autoría — no para egress a tres servicios de terceros en cada
corrida, sin opt-in y sin forma de apagarlo. Medido en vivo ese día: doce llamadas lo llevaron,
embebido en la URL y por lo tanto en cualquier mensaje de `raise_for_status` y en cualquier log de
proxy. Ahora se declara una vez, en un archivo gitignored, exactamente como el token de ADS.

Salieron de la pasada `/auditar` del 2026-08-24: eran 2 de las 10 funciones que sobrevivían al gate
de mutación, y las únicas de esas 10 que no necesitan red, o sea las más baratas de bajar del techo
(AUD-35).

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
def test_mailto_sale_del_opt_in_declarado(mod, vacio, monkeypatch, toy_vault):
    """  @inv INV-67"""
    monkeypatch.setenv("ALMAGESTO_MAILTO", "  alguien@example.org \n")
    assert mod._mailto() == "alguien@example.org", "se usa el opt-in declarado, sin espacios"
    monkeypatch.delenv("ALMAGESTO_MAILTO")
    toy_vault.MAILTO_FILE.parent.mkdir(parents=True, exist_ok=True)
    toy_vault.MAILTO_FILE.write_text("otro@example.org\n", encoding="utf-8")
    assert mod._mailto() == "otro@example.org", "el archivo de config es la otra mitad del opt-in"


@pytest.mark.parametrize("mod, vacio", GEMELOS)
def test_sin_opt_in_cae_al_pool_publico(mod, vacio, monkeypatch, toy_vault):
    """Sin declaración explícita **no sale ninguna dirección**. Las tres APIs funcionan igual; el
    mailto sólo compra un tier de rate-limit más rápido."""
    monkeypatch.delenv("ALMAGESTO_MAILTO", raising=False)
    assert mod._mailto() == vacio


@pytest.mark.parametrize("mod, vacio", GEMELOS)
def test_el_email_de_git_NO_se_usa(mod, vacio, monkeypatch, toy_vault):
    """La regresión que este cambio cierra: aunque `git config user.email` esté configurado —el caso
    normal en cualquier repo— **no** viaja a OpenAlex, Crossref ni Unpaywall."""
    monkeypatch.delenv("ALMAGESTO_MAILTO", raising=False)
    llamadas = []

    class R:
        stdout = "personal@midominio.org\n"

    def espia(*a, **k):
        llamadas.append(a)
        return R()

    monkeypatch.setattr(mod.subprocess, "run", espia)
    assert mod._mailto() == vacio, "el email de git se filtró al polite pool"
    assert llamadas == [], "ni siquiera se le pregunta a git por el email"


@pytest.mark.parametrize("mod, vacio", GEMELOS)
def test_mailto_no_hardcodea_ninguna_direccion(mod, vacio):
    """La promesa explícita de los dos docstrings: la dirección es per-instancia. `openalex` tenía
    una de ejemplo fija y toda request salía con un mail falso — lo contrario de la cortesía que el
    pool pide."""
    fuente = (SCRIPTS / f"{mod.__name__}.py").read_text(encoding="utf-8")
    assert "@example." not in fuente.split('"""', 2)[-1], "dirección hardcodeada fuera del docstring"
