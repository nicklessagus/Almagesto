"""Configuración compartida de los scripts de ingesta de la bóveda.

- Resuelve rutas del repo (sin asumir cwd).
- Lee el token ADS de vault/config/ads_dev_key o de la variable de entorno ADS_DEV_KEY.
- Carga vault/config/stars.yaml, vault/config/topics.yaml y vault/config/objective.yaml.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

# Versión del framework Almagesto (bump MANUAL; no hay release formal todavía). Se estampa en el
# frontmatter `generator` de cada nota que genera make_notes → traza con qué versión se armó la ficha.
ALMAGESTO_VERSION = "0.1.0"

ROOT = Path(__file__).resolve().parent.parent  # raíz del repo (andamiaje + bóveda)
VAULT = ROOT / "vault"                          # la bóveda: contenido (config/wiki/raw); Obsidian abre acá
CONFIG = VAULT / "config"
STARS_YAML = CONFIG / "stars.yaml"
TOPICS_YAML = CONFIG / "topics.yaml"
OBJECTIVE_YAML = CONFIG / "objective.yaml"
ADS_KEY_FILE = CONFIG / "ads_dev_key"

# raw/ = fuentes inmutables (el LLM lee, no modifica) | wiki/ = el LLM escribe y mantiene
RAW = VAULT / "raw"
WIKI = VAULT / "wiki"
# build/ y outputs/ son scratch del tooling (gitignored, regenerable): viven en la raíz del
# repo, FUERA de vault/, para no contaminar la bóveda de Obsidian. Resolver vía cfg.ROOT.

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
    """Token ADS desde env ADS_DEV_KEY o vault/config/ads_dev_key (gitignored — nunca se commitea)."""
    tok = os.environ.get("ADS_DEV_KEY")
    if tok:
        return tok.strip()
    if ADS_KEY_FILE.exists():
        return ADS_KEY_FILE.read_text().strip()
    raise RuntimeError(
        "No hay token ADS. Poné vault/config/ads_dev_key o exportá ADS_DEV_KEY. "
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
    raise KeyError(f"slug desconocido: {slug!r}. Definilo en vault/config/stars.yaml")


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
    raise KeyError(f"tema desconocido: {slug!r}. Definilo en vault/config/topics.yaml")


def load_objective() -> dict:
    """El OBJETIVO de la bóveda (vault/config/objective.yaml): name/short/description y el
    clasificador de relevancia (`relevance.topics`, `relevance.noise_doctypes`). Es
    lo que define qué papers son 'core'."""
    if not OBJECTIVE_YAML.exists():
        raise RuntimeError(
            "Falta vault/config/objective.yaml. Es el archivo que define el objetivo de la "
            "bóveda y el clasificador de relevancia. Partí del ejemplo del template."
        )
    with open(OBJECTIVE_YAML, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# Áreas de vault/wiki/concepts/ RESERVADAS (siempre válidas): `methods` es universal;
# `hypotheses` es estructural (schema name/status + roll-up Dataview). Ver CLAUDE.md.
RESERVED_CONCEPT_AREAS = ("methods", "hypotheses")


def load_concept_areas() -> list:
    """Lista de REFERENCIA de áreas de vault/wiki/concepts/ (para el typo-check; NO restringe — las
    áreas son abiertas). Salen de `concept_areas` en objective.yaml; siempre incluyen las reservadas
    (methods, hypotheses).

    Si objective.yaml NO declara `concept_areas` (instancia vieja, pre-feature), cae a un
    modo tolerante: reservadas + las carpetas ya existentes en concepts/ (no marca falsos
    positivos hasta que declares la lista). Devuelve los nombres en orden, deduplicados."""
    declared = load_objective().get("concept_areas") or []
    if declared:
        return list(dict.fromkeys([*declared, *RESERVED_CONCEPT_AREAS]))
    existing = sorted(p.name for p in CONCEPTS.iterdir() if p.is_dir()) if CONCEPTS.exists() else []
    return list(dict.fromkeys([*existing, *RESERVED_CONCEPT_AREAS]))
