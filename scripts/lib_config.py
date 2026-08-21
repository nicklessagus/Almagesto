"""Configuración compartida de los scripts de ingesta de la bóveda.

- Resuelve rutas del repo (sin asumir cwd).
- Lee el token ADS de vault/config/ads_dev_key o de la variable de entorno ADS_DEV_KEY.
- Carga vault/config/stars.yaml, vault/config/topics.yaml y vault/config/objective.yaml.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

# Versión del framework Almagesto — ÚNICA fuente de versión del repo (bump MANUAL + tag git
# `vX.Y.Z` al bumpear). La consumen: el frontmatter `generator` de cada nota que genera make_notes
# (provenance: con qué versión se armó la ficha) y los User-Agent de los fetchers (no hardcodear
# "Almagesto/x" en ningún otro lado — lo vigila un test). Semver: 1.0.0 = contrato estable
# (schema de frontmatter/config/cadena); un cambio que rompa ese contrato exige major bump.
ALMAGESTO_VERSION = "1.10.0"

# PLACEHOLDER de `name` que trae el template en vault/config/objective.yaml. Es un placeholder
# explícito (no un nombre de ejemplo plausible: un objetivo real que coincida con el del ejemplo
# daría WARN permanente sin forma de apagarlo). El lint AVISA (WARN) mientras `name` siga siendo
# este string — la instancia no definió su objetivo (skill `setup`) y clasifica "core" con la
# regex del ejemplo. Mantener en sync con el YAML del template.
DEFAULT_OBJECTIVE_NAME = "<definir con el skill setup>"

ROOT = Path(__file__).resolve().parent.parent  # raíz del repo (andamiaje + bóveda)
VAULT = ROOT / "vault"                          # la bóveda: contenido (config/wiki/raw); Obsidian abre acá
CONFIG = VAULT / "config"
STARS_YAML = CONFIG / "stars.yaml"
TOPICS_YAML = CONFIG / "topics.yaml"
OBJECTIVE_YAML = CONFIG / "objective.yaml"
ADS_KEY_FILE = CONFIG / "ads_dev_key"
# Registro de ingesta por sujeto (#51/#64): VERSIONADO (se commitea) porque guarda las dos cosas
# que `build/` no puede guardar. (a) `decisiones`: el juicio del triage —qué candidato del chaining
# se descartó y POR QUÉ—, que no es regenerable (un ads.json sí: se le vuelve a pedir a ADS; tu
# juicio sobre título+abstract, no). Vivía en build/<slug>/triage.json, gitignored: en otra máquina
# el triage re-proponía todo lo descartado, sin el motivo. (b) `busqueda`: el registro reproducible
# de la búsqueda (query efectiva, fecha, límites y conteos — los 16 ítems de PRISMA-S llevados a lo
# que esta cadena hace), que antes no se escribía en ningún lado: la query de una estrella se armaba
# en memoria y se tiraba. Simetría que faltaba: los candidatos ACEPTADOS ya persistían en config
# (`extra_core`), los rechazados no.
REGISTRO = CONFIG / "registro"

# raw/ = fuentes inmutables (el LLM lee, no modifica) | wiki/ = el LLM escribe y mantiene
RAW = VAULT / "raw"
WIKI = VAULT / "wiki"
# build/ y outputs/ son scratch del tooling (gitignored, regenerable): viven en la raíz del
# repo, FUERA de vault/, para no contaminar la bóveda de Obsidian. Resolver vía cfg.ROOT.

PDFS = RAW / "pdfs"
FULLTEXT = RAW / "fulltext"
GROUND_TRUTH = RAW / "ground_truth"

# Marcas de provenance en la PRIMERA línea de un .txt de fulltext/ — las escriben
# extract_fulltext (OCR) y fetch_web (snapshot); las lee make_notes para estampar
# `fulltext_source` en la nota (ocr|web; sin marca = pdftotext). Un solo lugar de verdad:
# si cambia el header, cambia acá.
FULLTEXT_OCR_MARK = "# Almagesto — fulltext por OCR"
FULLTEXT_WEB_MARK = "# Almagesto — snapshot web"

# Marca que arXiv estampa en el margen de CADA página del PDF que sirve
# ("arXiv:2201.01234v3 [astro-ph.EP] 5 Jan 2022"; los IDs viejos son "astro-ph/0601123v2").
# Es la señal de DISCO de que el .txt salió del **eprint** y no de la versión publicada (#57):
# no depende de que el fetcher haya dejado registro, así que funciona retroactivamente sobre un
# corpus ya bajado. Importa porque `verify-citations` promete que la cita textual son "las palabras
# reales del paper" y un v1 pre-referato puede decir otra cosa que el publicado.
ARXIV_STAMP_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?",
                            re.I)
ARXIV_STAMP_SCAN_CHARS = 4000     # la marca está en la 1ª página; no hace falta leer el paper entero


def arxiv_stamp(text: str) -> str | None:
    """Versión del eprint ("v3", o "" si la marca no la trae) si el texto arranca con la marca de
    arXiv; None si no está. Sólo mira el principio (la marca va en el margen de la 1ª página)."""
    m = ARXIV_STAMP_RE.search(text[:ARXIV_STAMP_SCAN_CHARS])
    return (m.group(2) or "") if m else None


def snapshot_retrieved(path) -> str | None:
    """Fecha `retrieved` (AAAA-MM-DD) del header de un snapshot web de fulltext/, o None si el
    archivo no existe o no la trae. El header lo escribe fetch_web (FULLTEXT_WEB_MARK); el parser
    vive acá —un solo lugar de verdad, como las marcas— porque lo comparten fetch_web (reuso de
    la fecha al re-correr sin --force) y make_notes (#34: la nota debe estampar `accessed` = la
    fecha del snapshot en disco, no la de hoy)."""
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[:8]:
            m = re.match(r"retrieved\s*:\s*(\d{4}-\d{2}-\d{2})", line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return None

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


def require_field(meta: dict, key: str, entry: str, yaml_name: str, hint: str = ""):
    """Campo OBLIGATORIO de una entrada de config: si falta o está vacío, salida amigable
    (qué entrada, qué campo, en qué archivo) en vez de un KeyError crudo con traceback.
    Para los índices duros que los scripts acceden a pelo (`ads_object`/`simbad` en stars,
    `query` en topics) — un campo olvidado al cargar la entrada a mano es el caso típico."""
    val = meta.get(key)
    if val in (None, ""):
        raise SystemExit(
            f"la entrada '{entry}' no tiene `{key}` en vault/config/{yaml_name} — "
            "agregalo (ver el ejemplo comentado del YAML)." + (f" {hint}" if hint else ""))
    return val


def load_stars() -> dict:
    """dict {nombre_canonico: {slug, simbad, ads_object, aliases, data_local}}. Un YAML vacío
    (instancia recién creada / sólo comentarios) parsea a None → {} para que star_by_slug dé su
    KeyError amigable y no un AttributeError (mismo guard que load_topics)."""
    with open(STARS_YAML, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


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


def split_fm(text: str) -> dict:
    """Frontmatter YAML de una nota (dict vacío si no hay o no parsea — el lint reporta aparte las
    notas cuyo YAML está roto). Compartido: lo usan el lint y el dry-run de re-clasificación."""
    parts = text.split("---")
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


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


# ── registro de ingesta por sujeto (#51/#64) ─────────────────────────────────

def registro_path(slug: str) -> Path:
    return REGISTRO / f"{slug}.yaml"


def legacy_triage_path(slug: str) -> Path:
    """Ubicación PRE-#51 de las decisiones de triage (scratch gitignored). Se sigue LEYENDO para no
    perder juicio ya hecho en una bóveda vieja; nunca se escribe más ahí."""
    return ROOT / "build" / slug / "triage.json"


def load_registro(slug: str) -> dict:
    """Registro versionado del sujeto ({} si no existe). No mergea el legacy: para las decisiones
    usar `load_decisiones`, que sí lo hace."""
    f = registro_path(slug)
    if not f.exists():
        return {}
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


def save_registro(slug: str, data: dict) -> None:
    REGISTRO.mkdir(parents=True, exist_ok=True)
    registro_path(slug).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8")


def load_decisiones(slug: str) -> dict:
    """Decisiones de triage del sujeto: las del registro versionado MERGEADAS con las del
    `triage.json` viejo (migración transparente — el registro gana ante el mismo bibcode). Que el
    legacy siga contando es lo que evita que una bóveda pre-#51 vuelva a proponer lo ya descartado
    antes de su primer `--drop`."""
    out: dict = {}
    legacy = legacy_triage_path(slug)
    if legacy.exists():
        try:
            out.update(json.loads(legacy.read_text(encoding="utf-8")).get("decisiones") or {})
        except (ValueError, OSError):
            pass
    out.update(load_registro(slug).get("decisiones") or {})
    return out


def save_decisiones(slug: str, decisiones: dict) -> None:
    """Persiste las decisiones preservando `busqueda` (la escribe query_ads, no el triage)."""
    data = load_registro(slug)
    data.setdefault("slug", slug)
    data["decisiones"] = decisiones
    save_registro(slug, data)


def save_busqueda(slug: str, busqueda: dict) -> None:
    """Persiste el registro de búsqueda preservando `decisiones` (las escribe triage.py)."""
    data = load_registro(slug)
    data.setdefault("slug", slug)
    data["busqueda"] = busqueda
    save_registro(slug, data)


def record_pdf_source(slug: str, stem: str, source: str) -> None:
    """Deja constancia de QUÉ rama entregó el PDF de un paper (#57): `eprint` (arXiv), `ads`
    (escaneo alojado por ADS) o `publisher`. Vive en `build/<slug>/pdf_source.json` —scratch a
    propósito: es un puente dentro de la MISMA corrida de la cadena (fetch_* → make_notes), y lo
    durable termina en el frontmatter de la nota, que se commitea. La señal fuerte igual es la
    marca de arXiv en el .txt (verdad de disco, retroactiva); esto cubre lo que la marca no
    distingue (ads vs publisher, y un eprint sin marca)."""
    f = ROOT / "build" / slug / "pdf_source.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8")) or {}
        except ValueError:
            data = {}
    data[stem] = source
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
