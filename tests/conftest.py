"""Fixtures compartidas de la suite: bóveda de juguete aislada + helpers.

`lib_config` resuelve rutas por constantes de módulo derivadas de __file__; la fixture
`toy_vault` las re-apunta TODAS a un árbol temporal, incluidos los alias que otros módulos
toman al importar (extract_fulltext.FULLTEXT). Ningún test toca la bóveda real.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import lib_config as cfg          # noqa: E402
import extract_fulltext           # noqa: E402  (alias FULLTEXT tomado a nivel módulo)


# Config mínima de la instancia de juguete. Las regex de relevance NO son las del template:
# los tests de clasificación parchean query_ads.FACET_PATTERNS explícitamente (query_ads
# compila el clasificador al importar, desde la bóveda real — ver test_query_ads).
OBJECTIVE = {
    "name": "Bóveda de juguete (tests)",
    "short": "toy",
    "description": "instancia sintética para la suite de tests",
    "concept_areas": ["indicators", "methods", "activity", "hypotheses"],
    "relevance": {
        "facets": {
            "actividad": "activity|starspot",
            "rv": "radial velocity",
        },
        "noise_doctypes": ["catalog", "proposal"],
    },
}

STARS = {
    "Estrella Test": {
        "slug": "test_star",
        "simbad": "tst Star",
        "ads_object": "Test Star",
        "aliases": ["HD 12345"],
        "data_local": None,
    },
}


def write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def mk_note(dirpath: Path, stem: str, fm: dict, body: str = "", crudo: bool = False) -> Path:
    """Nota .md con frontmatter, mismo formato que make_notes.fm().

    `crudo=True` apaga los defaults de abajo: es lo que usa el test que quiere justamente la nota
    **sin** lo que el schema exige (si el helper lo rellenara siempre, esa categoría no se podría
    probar)."""
    # D-23: una nota de paper SIN destino (`stars`/`thesis_links`/`methods`) es un hallazgo
    # bloqueante — no pertenece a nada y ninguna síntesis la alcanza. En la vida real
    # `make_notes` siempre siembra uno; acá se le da el default para que las fixtures mínimas
    # no disparen la categoría. El test que quiere el caso vacío pone las tres claves a mano.
    if "paper" in (fm.get("tags") or []) and not any(
            k in fm for k in ("stars", "thesis_links", "methods")) and not crudo:
        fm = {**fm, "stars": ["Estrella Test"]}
    # #277 — mismo criterio con `## Abstract`, que desde 1.113.0 BLOQUEA: en la vida real lo escribe
    # `make_notes` (los dos raíles), así que una fixture sin él probaría un estado que la cadena no
    # produce. Se agrega al final para no correr la primera línea del cuerpo, que varios tests usan
    # como ancla de línea.
    if "paper" in (fm.get("tags") or []) and not crudo and "## Abstract" not in body:
        body = f"{body}\n## Abstract\n{cfg.ABSTRACT_PLACEHOLDER}\n"
    dirpath.mkdir(parents=True, exist_ok=True)
    head = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, default_flow_style=False)
    p = dirpath / f"{stem}.md"
    p.write_text(f"---\n{head}---\n{body}", encoding="utf-8")
    return p


def read_fm(path: Path) -> dict:
    """Frontmatter parseado de una nota (para asserts) — **con el mismo parser que el tooling**.

    Antes esto hacía `split("---")[1]`, que es justo lo que el docstring de `frontmatter_span`
    prohíbe: parsea notas que `cfg.split_fm` **no puede leer**. Medido: `--rename-paper` dejaba el
    frontmatter fusionado (`---bibcode: 2021pubY`) y `split_fm` devolvía `{}`, pero el test que
    cubre INV-84 pasaba en verde porque este helper lo leía igual. Es el patrón `refs_of`/`_bare_doi`
    otra vez: un doble con distinto contrato que la función real esconde el bug en la diferencia
    (red #3). Delegar es la única forma de que un test acá signifique lo que dice."""
    return cfg.split_fm(path.read_text(encoding="utf-8"))


# ── #123 · la promesa «sin red» pasa a ser un assert ─────────────────────────────────────────────
# `tests/README.md` promete que todo lo que toca afuera se mockea. Vivía en prosa y en un docstring,
# así que nadie la sostenía: medido con cProfile, un test de `ingest_theme` hacía DOS peticiones HTTP
# reales (OpenAlex y Unpaywall, 1,5 s de los ~9,5 s del tier 0) y pasaba en verde porque las dos
# fallaban con 404. Una suite que depende de la conexión no es determinista, y en CI pega contra
# servicios de terceros.
# Es autouse y global: la red no se "olvida de mockear" en un test nuevo, explota.
class RedProhibida(RuntimeError):
    pass


class BovedaRealTocada(RuntimeError):
    pass


# La bóveda REAL del repo, resuelta al importar — antes de que `toy_vault` re-apunte nada.
_VAULT_REAL = Path(__file__).resolve().parent.parent / "vault"


@pytest.fixture(autouse=True)
def sin_tocar_la_boveda_real(monkeypatch):
    """Ningún test puede escribir dentro de `vault/` del repo real.

    Hermana de `sin_red` y por el mismo motivo: el principio 2 de `tests/README.md` promete que
    «ningún test lee ni escribe la bóveda real», vivía en prosa y **nadie lo sostenía**. Medido el
    2026-08-26: al cablear #77, un test preexistente de `discover` que no usa `toy_vault` empezó a
    crear `vault/config/registro/ica.yaml` en cada corrida de la suite. En el repo template eso se
    ve; en una **instancia** appendearía una entrada falsa al **único artefacto no regenerable** de
    la bóveda (INV-53), y sin que nada avise.

    Es barato porque el repo tiene **un solo writer** (D-53/INV-90): basta interceptar ahí. Lo que
    `toy_vault` re-apunta cae en `tmp_path` y no toca esta guarda.

    @inv INV-126"""
    real = cfg.write_text_atomic
    real_b = cfg.write_bytes_atomic

    def _guard(fn):
        def _w(path, *a, **k):
            p = Path(path).resolve()
            if p == _VAULT_REAL or _VAULT_REAL in p.parents:
                raise BovedaRealTocada(
                    f"un test intentó ESCRIBIR en la bóveda real ({p}). Los tests corren sobre la "
                    f"fixture `toy_vault`, que re-apunta todas las rutas de `lib_config` a un árbol "
                    f"temporal — si tu test no la usa, agregala.")
            return fn(path, *a, **k)
        return _w

    monkeypatch.setattr(cfg, "write_text_atomic", _guard(real))
    monkeypatch.setattr(cfg, "write_bytes_atomic", _guard(real_b))


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Cualquier petición HTTP real desde un test explota **y queda registrada**.  @inv INV-114

    ⚠ La marca vive ACÁ desde #136. INV-114 dice *"la suite no sale a la red, y eso es un assert"*, y
    sus dos únicos punteros apuntaban a código y test de **producción** (`ingest_theme.ingest_offads`
    evitando `resolve_pdf` para `pending: adquisicion`, que el contrato mismo describe como *efecto
    colateral*). O sea: un P0 contaba como *con implementación marcada* y *con test marcado*, y quien
    siguiera el puntero para auditar «¿qué impide que la suite salga a la red?» llegaba a un
    `if why != "adquisicion"`. El assert es esta fixture.

    ⚠ Las dos mitades hacen falta. Levantar la excepción sola no alcanza: el código de producción
    está lleno de `except` que degradan limpio ante un backend caído —que es la conducta correcta
    en producción— así que se traga la guardia y el test sigue en verde. Medido: con sólo la
    excepción, el test que motivó #123 pasaba igual, nada más que rápido. El registro se chequea al
    CERRAR el test, así que la violación sale a la luz la atrape quien la atrape."""
    import requests
    intentos: list = []

    def _prohibido(self, method, url, *a, **k):
        intentos.append(f"{method} {url}")
        raise RedProhibida(
            f"un test intentó salir a la red ({url!r}). La suite es determinista y offline "
            f"(tests/README.md, principio 1): mockeá `requests` en ese camino — el `fake_run` "
            f"sólo cubre los SUBPROCESOS, no las llamadas HTTP.")

    monkeypatch.setattr(requests.sessions.Session, "request", _prohibido)
    yield intentos
    assert not intentos, ("este test salió a la red (y alguien se tragó la excepción):\n  "
                          + "\n  ".join(intentos))


@pytest.fixture
def toy_vault(tmp_path, monkeypatch):
    """Árbol repo+vault temporal con config mínima; re-apunta lib_config entero."""
    root = tmp_path / "repo"
    vault = root / "vault"
    paths = {
        "ROOT": root,
        "VAULT": vault,
        "CONFIG": vault / "config",
        "STARS_YAML": vault / "config" / "stars.yaml",
        "THEMES_YAML": vault / "config" / "themes.yaml",
        "OBJECTIVE_YAML": vault / "config" / "objective.yaml",
        "ADS_KEY_FILE": vault / "config" / "ads_dev_key",
        "MAILTO_FILE": vault / "config" / "mailto",
        "REGISTRO": vault / "config" / "registro",
        "RAW": vault / "raw",
        "WIKI": vault / "wiki",
        "PDFS": vault / "raw" / "pdfs",
        "FULLTEXT": vault / "raw" / "fulltext",
        "GROUND_TRUTH": vault / "raw" / "ground_truth",
        "STARS": vault / "wiki" / "stars",
        "PAPERS": vault / "wiki" / "papers",
        "CONCEPTS": vault / "wiki" / "concepts",
        "QUERIES": vault / "wiki" / "queries",
        "MATRICES": vault / "wiki" / "matrices",
        "INDEX": vault / "wiki" / "index.md",
        "LOG": vault / "wiki" / "log.md",
    }
    for k, v in paths.items():
        monkeypatch.setattr(cfg, k, v)
    monkeypatch.setattr(extract_fulltext, "FULLTEXT", paths["FULLTEXT"])
    for k in ("RAW", "WIKI", "PDFS", "FULLTEXT", "GROUND_TRUTH",
              "STARS", "PAPERS", "CONCEPTS", "QUERIES", "MATRICES"):
        paths[k].mkdir(parents=True, exist_ok=True)
    (vault / "raw" / "refs").mkdir(parents=True, exist_ok=True)
    write_yaml(paths["OBJECTIVE_YAML"], OBJECTIVE)
    write_yaml(paths["STARS_YAML"], STARS)
    write_yaml(paths["THEMES_YAML"], {})
    return SimpleNamespace(**paths)
