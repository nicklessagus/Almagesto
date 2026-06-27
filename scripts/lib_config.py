"""Configuración compartida de los scripts de ingesta de la bóveda.

- Resuelve rutas del repo (sin asumir cwd).
- Lee el token ADS de config/ads_dev_key o de la variable de entorno ADS_DEV_KEY.
- Carga config/stars.yaml, config/topics.yaml y config/objective.yaml.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent  # raíz del repo
CONFIG = ROOT / "config"
STARS_YAML = CONFIG / "stars.yaml"
TOPICS_YAML = CONFIG / "topics.yaml"
OBJECTIVE_YAML = CONFIG / "objective.yaml"
ADS_KEY_FILE = CONFIG / "ads_dev_key"

# raw/ = fuentes inmutables (el LLM lee, no modifica) | wiki/ = el LLM escribe y mantiene
RAW = ROOT / "raw"
WIKI = ROOT / "wiki"

PDFS = RAW / "pdfs"
FULLTEXT = RAW / "fulltext"
GROUND_TRUTH = RAW / "ground_truth"

STARS = WIKI / "stars"
PAPERS = WIKI / "papers"
CONCEPTS = WIKI / "concepts"
QUERIES = WIKI / "queries"
MATRICES = WIKI / "matrices"
INDEX = WIKI / "index.md"
LOG = WIKI / "log.md"


def get_ads_token() -> str:
    """Token ADS desde env ADS_DEV_KEY o config/ads_dev_key (gitignored — nunca se commitea)."""
    tok = os.environ.get("ADS_DEV_KEY")
    if tok:
        return tok.strip()
    if ADS_KEY_FILE.exists():
        return ADS_KEY_FILE.read_text().strip()
    raise RuntimeError(
        "No hay token ADS. Poné config/ads_dev_key o exportá ADS_DEV_KEY. "
        "Token gratis en https://ui.adsabs.harvard.edu/user/settings/token"
    )


def load_stars() -> dict:
    """dict {nombre_canonico: {slug, simbad, ads_object, aliases, data_local}}."""
    with open(STARS_YAML, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def star_by_slug(slug: str) -> tuple[str, dict]:
    """Devuelve (nombre_canonico, meta) buscando por slug. Lanza KeyError si no existe."""
    for name, meta in load_stars().items():
        if meta.get("slug") == slug:
            return name, meta
    raise KeyError(f"slug desconocido: {slug!r}. Definilo en config/stars.yaml")


def load_topics() -> dict:
    """dict {slug: {title, area, concept, query, aliases}} (registro de temas, análogo a stars)."""
    if not TOPICS_YAML.exists():
        return {}
    with open(TOPICS_YAML, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def topic_by_slug(slug: str) -> tuple[str, dict]:
    """Devuelve (slug, meta) del tema. La clave del YAML ES el slug. KeyError si no existe."""
    topics = load_topics()
    if slug in topics:
        return slug, topics[slug]
    raise KeyError(f"tema desconocido: {slug!r}. Definilo en config/topics.yaml")


def load_objective() -> dict:
    """El OBJETIVO de la bóveda (config/objective.yaml): name/short/description y el
    clasificador de relevancia (`relevance.topics`, `relevance.noise_doctypes`). Es
    lo que define qué papers son 'core'."""
    if not OBJECTIVE_YAML.exists():
        raise RuntimeError(
            "Falta config/objective.yaml. Es el archivo que define el objetivo de la "
            "bóveda y el clasificador de relevancia. Partí del ejemplo del template."
        )
    with open(OBJECTIVE_YAML, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
