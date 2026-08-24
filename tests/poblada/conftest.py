"""Fixtures de la bóveda POBLADA (tier `poblada`/`instancia`) — la contraparte a escala de
`tests/conftest.py::toy_vault`. Cuatro fixtures (plan §2.2):

- `arbol_poblado`   (session-scoped): siembra UNA vez por sesión, no monkeypatchea nada.
- `boveda_poblada`  (function-scoped): vista READ-ONLY del árbol de sesión — re-apunta
  `lib_config` (mismo patrón que `toy_vault`).
- `boveda_poblada_mutable` (function-scoped): COPIA del árbol de sesión para tests que escriben.
- `instancia_real`  (session-scoped, opt-in): la instancia real del usuario, SIEMPRE read-only —
  copia lo liviano, symlinkea lo pesado, nunca escribe en la ruta original.

Sembrar 900 notas por test rompería el presupuesto del tier (`pytest.ini`: ≤ 90 s el tier
`poblada`); sembrar una vez por sesión y copiar sólo donde hace falta mutar lo mantiene en
segundos. Ver `generador.py` para `sembrar_corpus`/`Censo`.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

THIS_DIR = Path(__file__).resolve().parent            # tests/poblada — para `import generador`
SCRIPTS = THIS_DIR.parent.parent / "scripts"
# `tests/poblada/__init__.py` existe (necesario: sin él, pytest importa este archivo y
# `tests/conftest.py` BAJO EL MISMO nombre de módulo "conftest" — los dos se llaman igual y
# ninguno de los dos directorios tenía paquete propio — y cualquier `from conftest import X` de
# CUALQUIER módulo de `tests/` resuelve contra el que haya ganado esa carrera, no necesariamente
# el correcto: reproducido de verdad al escribir este módulo, tests/test_query_ads.py y
# tests/test_triage.py — que SÍ hacen `from conftest import write_yaml` — se rompían al correr
# `pytest` completo con este archivo presente). Con el paquete, pytest nombra a ESTE conftest
# `poblada.conftest` (único) e inserta `tests/` en sys.path — pero no `tests/poblada/`, así que
# `import generador` necesita esta línea.
for _p in (THIS_DIR, SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lib_config as cfg               # noqa: E402
import extract_fulltext                # noqa: E402  (alias FULLTEXT tomado a nivel módulo)

from generador import sembrar_corpus   # noqa: E402

# Mismas claves que tests/conftest.py::toy_vault — un solo "shape" de `paths` para los dos mundos
# (bóveda de juguete de 1-2 notas y bóveda poblada de cientos): cualquier test/fixture que ya sepa
# leer `toy_vault.STARS`, `toy_vault.PAPERS`, etc. lee `boveda_poblada.STARS` igual.
_PATH_ATTRS = ("ROOT", "VAULT", "CONFIG", "STARS_YAML", "THEMES_YAML", "OBJECTIVE_YAML",
              "ADS_KEY_FILE", "REGISTRO", "RAW", "WIKI", "PDFS", "FULLTEXT", "GROUND_TRUTH",
              "STARS", "PAPERS", "CONCEPTS", "QUERIES", "MATRICES", "INDEX", "LOG")


def _build_paths(root: Path) -> SimpleNamespace:
    """El mismo dict de rutas que arma `tests/conftest.py::toy_vault`, pero como función libre
    (reusable desde un fixture session-scoped, donde `tmp_path`/`monkeypatch` no aplican)."""
    vault = root / "vault"
    paths = {
        "ROOT": root, "VAULT": vault, "CONFIG": vault / "config",
        "STARS_YAML": vault / "config" / "stars.yaml",
        "THEMES_YAML": vault / "config" / "themes.yaml",
        "OBJECTIVE_YAML": vault / "config" / "objective.yaml",
        "ADS_KEY_FILE": vault / "config" / "ads_dev_key",
        "REGISTRO": vault / "config" / "registro",
        "RAW": vault / "raw", "WIKI": vault / "wiki",
        "PDFS": vault / "raw" / "pdfs", "FULLTEXT": vault / "raw" / "fulltext",
        "GROUND_TRUTH": vault / "raw" / "ground_truth",
        "STARS": vault / "wiki" / "stars", "PAPERS": vault / "wiki" / "papers",
        "CONCEPTS": vault / "wiki" / "concepts", "QUERIES": vault / "wiki" / "queries",
        "MATRICES": vault / "wiki" / "matrices",
        "INDEX": vault / "wiki" / "index.md", "LOG": vault / "wiki" / "log.md",
    }
    return SimpleNamespace(**paths)


def _patch_cfg(paths: SimpleNamespace, monkeypatch=None) -> list:
    """Re-apunta TODAS las constantes de módulo de `lib_config` (patrón `toy_vault`) a `paths`.

    Con `monkeypatch` (fixture function-scoped de pytest): usa ESE mecanismo, que auto-revierte al
    final del test — es lo que usan `boveda_poblada`/`boveda_poblada_mutable`.
    Sin `monkeypatch` (None): save/restore MANUAL — hace falta para `instancia_real`, que es
    session-scoped y por eso NO PUEDE pedir el fixture `monkeypatch` (function-scoped; pedirlo
    ahí es un `ScopeMismatch` de pytest). Devuelve la lista de `(attr, valor_viejo)` para que el
    llamador la pase a `_restore_cfg` en su `finally`."""
    saved = []
    for k in _PATH_ATTRS:
        v = getattr(paths, k)
        if monkeypatch is not None:
            monkeypatch.setattr(cfg, k, v)
        else:
            saved.append((k, getattr(cfg, k)))
            setattr(cfg, k, v)
    if monkeypatch is not None:
        monkeypatch.setattr(extract_fulltext, "FULLTEXT", paths.FULLTEXT)
    else:
        saved.append(("__extract_fulltext_FULLTEXT__", extract_fulltext.FULLTEXT))
        extract_fulltext.FULLTEXT = paths.FULLTEXT
    return saved


def _restore_cfg(saved: list) -> None:
    for k, v in saved:
        if k == "__extract_fulltext_FULLTEXT__":
            extract_fulltext.FULLTEXT = v
        else:
            setattr(cfg, k, v)


def _snapshot_mtimes(root: Path) -> dict:
    """(ruta relativa → mtime) de todo archivo bajo `root` — el cinturón de `instancia_real`: si
    esto difiere antes/después de la sesión, algo escribió en la instancia real (bug: un test
    mutante debía operar sobre SU COPIA)."""
    out = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            try:
                out[str(p.relative_to(root))] = p.stat().st_mtime
            except OSError:
                pass
    return out


@pytest.fixture(scope="session")
def arbol_poblado(tmp_path_factory):
    """Siembra UNA vez por sesión (~segundos — ver el tiempo medido en el reporte del generador).
    Devuelve `(paths, censo)`. NO monkeypatchea `lib_config`: eso es trabajo de
    `boveda_poblada`/`boveda_poblada_mutable` (function-scoped) para no filtrar el patch de un
    test a otro — dos tests que pidieran esta fixture directamente y esperaran `cfg` re-apuntado
    se romperían en un orden y no en otro."""
    root = tmp_path_factory.mktemp("arbol_poblado")
    paths = _build_paths(root)
    censo = sembrar_corpus(paths)
    return paths, censo


@pytest.fixture
def boveda_poblada(arbol_poblado, monkeypatch):
    """Vista READ-ONLY del árbol de sesión: re-apunta `lib_config` (patrón `toy_vault`) para que
    `lint.main()`/los scripts corran contra el corpus poblado. NO mutar nada acá — el árbol es
    compartido entre TODOS los tests que pidan esta fixture en la sesión; para tests que escriben
    (migradores, estampadores, lo que sea), usar `boveda_poblada_mutable`."""
    paths, censo = arbol_poblado
    _patch_cfg(paths, monkeypatch)
    ns = SimpleNamespace(**vars(paths))
    ns.censo = censo
    return ns


@pytest.fixture
def boveda_poblada_mutable(arbol_poblado, tmp_path, monkeypatch):
    """Copia del árbol de sesión (~1 s: es I/O sobre unos miles de archivos chicos) para tests que
    mutan. Nunca toca el árbol de sesión — dos tests mutantes en la misma sesión no interfieren
    entre sí, cada uno tiene su propia copia."""
    paths, censo = arbol_poblado
    dest_root = tmp_path / "repo"
    shutil.copytree(paths.ROOT, dest_root)
    new_paths = _build_paths(dest_root)
    _patch_cfg(new_paths, monkeypatch)
    ns = SimpleNamespace(**vars(new_paths))
    ns.censo = replace(censo, paths=new_paths)   # mismos stems/anomalías, `paths` apunta a LA COPIA
    return ns


@pytest.fixture
def sembrar(tmp_path, monkeypatch):
    """Factory `sembrar(**kwargs) -> (paths, censo)`: siembra un árbol PROPIO de este test (bajo
    `tmp_path`, no el de sesión) y re-apunta `lib_config`. Para tests que necesitan parámetros
    propios (`anomalias`, `vintage`, un `n` chico para ir rápido) y por eso no pueden compartir
    `arbol_poblado` — evita además que cada test tenga que importar `_build_paths`/`_patch_cfg` a
    mano (y con eso, cualquier ambigüedad de import: dos archivos se llaman `conftest.py` en este
    árbol — `tests/conftest.py` y este mismo — así que un test que hiciera `from conftest import
    X` podría resolver contra el que no es; los fixtures de pytest no tienen ese problema)."""
    contador = {"n": 0}

    def _sembrar(**kwargs):
        contador["n"] += 1
        paths = _build_paths(tmp_path / f"repo{contador['n']}")
        censo = sembrar_corpus(paths, **kwargs)
        _patch_cfg(paths, monkeypatch)
        return paths, censo

    return _sembrar


@pytest.fixture(scope="session")
def _instancia_arbol(tmp_path_factory):
    """La instancia real del usuario (`ALMAGESTO_INSTANCIA`), SIEMPRE read-only. Opt-in: sin la
    variable de entorno, SKIP con motivo VISIBLE — nunca "pasa" en silencio (mismo principio que
    "el 0 que no miró" del lint: un tier que se saltea sin decirlo es el mismo bug con otro nombre).

    Copia lo LIVIANO (`wiki/`, `config/`, `raw/ground_truth`, `raw/refs` — unos 5 MB, medido) y
    SYMLINKEA lo pesado (`raw/pdfs`, `raw/fulltext`, `build/`) — nunca se duplican los PDFs/fulltext
    completos. Los tests que mutan deben mutar su PROPIA copia de este árbol (análogo a
    `boveda_poblada_mutable`, no provisto acá: es trabajo de la ola de tests §3.3, no de este
    módulo) — este fixture en sí NUNCA escribe sobre `ALMAGESTO_INSTANCIA`.

    Cinturón: mtimes de `<ALMAGESTO_INSTANCIA>/vault` y `<ALMAGESTO_INSTANCIA>/build` ANTES y
    DESPUÉS de la sesión completa — si algo cambió, la garantía read-only se rompió y el fixture
    lo grita con un `AssertionError`, no un `assert` que nadie corre."""
    root_env = os.environ.get("ALMAGESTO_INSTANCIA")
    if not root_env:
        pytest.skip(
            "ALMAGESTO_INSTANCIA no está seteada — el tier `instancia` es opt-in: correlo con "
            "`ALMAGESTO_INSTANCIA=/ruta/a/tu/instancia python -m pytest -m instancia -q`. Sin la "
            "variable, este fixture SKIPEA con este motivo en vez de pasar en silencio."
        )
    src = Path(root_env).expanduser().resolve()
    if not (src / "vault").is_dir():
        pytest.skip(f"ALMAGESTO_INSTANCIA={src} no tiene `vault/` — no parece una instancia "
                    "Almagesto (¿ruta equivocada?).")

    antes = {**_snapshot_mtimes(src / "vault"), **_snapshot_mtimes(src / "build")}

    root = tmp_path_factory.mktemp("instancia_real")
    vault = root / "vault"
    src_vault = src / "vault"
    if (src_vault / "wiki").is_dir():
        shutil.copytree(src_vault / "wiki", vault / "wiki")
    if (src_vault / "config").is_dir():
        shutil.copytree(src_vault / "config", vault / "config")
    (vault / "raw").mkdir(parents=True, exist_ok=True)
    if (src_vault / "raw" / "ground_truth").is_dir():
        shutil.copytree(src_vault / "raw" / "ground_truth", vault / "raw" / "ground_truth")
    if (src_vault / "raw" / "refs").is_dir():
        shutil.copytree(src_vault / "raw" / "refs", vault / "raw" / "refs")
    for pesado, destino in ((src_vault / "raw" / "pdfs", vault / "raw" / "pdfs"),
                            (src_vault / "raw" / "fulltext", vault / "raw" / "fulltext")):
        if pesado.is_dir():
            destino.symlink_to(pesado, target_is_directory=True)
    src_build = src / "build"
    if src_build.is_dir():
        (root / "build").symlink_to(src_build, target_is_directory=True)
    else:
        (root / "build").mkdir()

    paths = _build_paths(root)
    try:
        yield SimpleNamespace(**vars(paths), instancia_src=src)
    finally:
        despues = {**_snapshot_mtimes(src / "vault"), **_snapshot_mtimes(src / "build")}
        assert antes == despues, (
            f"ALMAGESTO_INSTANCIA={src}: `vault/`/`build/` cambiaron durante la sesión de tests — "
            "la garantía read-only se rompió (algún test escribió en la instancia real en vez de "
            "su copia). Revisar qué fixture/test tocó la ruta original.")


@pytest.fixture(scope="module")
def instancia_real(_instancia_arbol):
    """La copia de la instancia real, con `lib_config` re-apuntado mientras dure ESTE módulo.

    Dos scopes distintos a propósito. El **árbol** (`_instancia_arbol`) es de sesión porque copiarlo
    es caro. El **re-apuntado de `lib_config`** vive acá, en scope de módulo, y se **revierte al
    cerrar el módulo**: mientras estuvo en el fixture de sesión, las constantes quedaban apuntando a
    la copia de la instancia **durante todo el resto de la corrida**, así que cualquier test de otro
    archivo que confiara en `cfg.ROOT` corría contra la instancia sin saberlo. Se detectó corriendo
    el modo "todo junto" (`-m ""` con `ALMAGESTO_INSTANCIA` seteada): `tests/test_lint.py` rompía por
    eso, y el síntoma **no aparecía en ningún tier corrido por separado**.

    ¿Por qué módulo y no función (que auto-revertiría con `monkeypatch`)? Porque los tests de este
    tier comparten un fixture module-scoped que corre el lint UNA vez sobre la instancia (~5 s) y
    reparte el reporte; con `instancia_real` function-scoped eso es un `ScopeMismatch`. Módulo es el
    scope más chico que sostiene esa optimización, y alcanza para que la fuga no cruce de archivo."""
    saved = _patch_cfg(_instancia_arbol, monkeypatch=None)
    try:
        yield _instancia_arbol
    finally:
        _restore_cfg(saved)
