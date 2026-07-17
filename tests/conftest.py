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
# los tests de clasificación parchean query_ads.TOPIC_PATTERNS explícitamente (query_ads
# compila el clasificador al importar, desde la bóveda real — ver test_query_ads).
OBJECTIVE = {
    "name": "Bóveda de juguete (tests)",
    "short": "toy",
    "description": "instancia sintética para la suite de tests",
    "concept_areas": ["indicators", "methods", "activity", "hypotheses"],
    "relevance": {
        "topics": {
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


def mk_note(dirpath: Path, stem: str, fm: dict, body: str = "") -> Path:
    """Nota .md con frontmatter, mismo formato que make_notes.fm()."""
    dirpath.mkdir(parents=True, exist_ok=True)
    head = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, default_flow_style=False)
    p = dirpath / f"{stem}.md"
    p.write_text(f"---\n{head}---\n{body}", encoding="utf-8")
    return p


def read_fm(path: Path) -> dict:
    """Frontmatter parseado de una nota (para asserts)."""
    parts = path.read_text(encoding="utf-8").split("---")
    return yaml.safe_load(parts[1]) or {}


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
        "TOPICS_YAML": vault / "config" / "topics.yaml",
        "OBJECTIVE_YAML": vault / "config" / "objective.yaml",
        "ADS_KEY_FILE": vault / "config" / "ads_dev_key",
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
    write_yaml(paths["TOPICS_YAML"], {})
    return SimpleNamespace(**paths)
