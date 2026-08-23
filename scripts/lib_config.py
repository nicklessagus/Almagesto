"""Configuración compartida de los scripts de ingesta de la bóveda.

- Resuelve rutas del repo (sin asumir cwd).
- Lee el token ADS de vault/config/ads_dev_key o de la variable de entorno ADS_DEV_KEY.
- Carga vault/config/stars.yaml, vault/config/topics.yaml y vault/config/objective.yaml.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

import yaml

# Versión del framework Almagesto — ÚNICA fuente de versión del repo (bump MANUAL + tag git
# `vX.Y.Z` al bumpear). La consumen: el frontmatter `generator` de cada nota que genera make_notes
# (provenance: con qué versión se armó la ficha) y los User-Agent de los fetchers (no hardcodear
# "Almagesto/x" en ningún otro lado — lo vigila un test). Semver: 1.0.0 = contrato estable
# (schema de frontmatter/config/cadena); un cambio que rompa ese contrato exige major bump.
ALMAGESTO_VERSION = "1.23.0"

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
    lo que define qué papers son 'core'.

    Un YAML inválido degrada a `{}` (no propaga `YAMLError`/`OSError`): el skill `setup` hace que
    el agente escriba REGEX dentro de YAML —un `:` sin comillas dentro de un patrón es el error más
    probable de toda la config— y `load_objective` lo llama el lint, que es la compuerta de CI y
    cuyo contrato es "ante una bóveda rara reporta, no se muere". El archivo AUSENTE sigue siendo
    un error duro (`RuntimeError` explícito): no hay ejemplo del template que copiar por default,
    así que ahí sí conviene frenar en vez de seguir con un objetivo vacío."""
    if not OBJECTIVE_YAML.exists():
        raise RuntimeError(
            "Falta vault/config/objective.yaml. Es el archivo que define el objetivo de la "
            "bóveda y el clasificador de relevancia. Partí del ejemplo del template."
        )
    try:
        with open(OBJECTIVE_YAML, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


# Línea delimitadora de frontmatter: `---` SOLA en su propia línea (con espacio final tolerado).
# `re.MULTILINE` para que `^`/`$` anclen a cada línea, no a los bordes del string entero.
_FM_DELIM_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)


def frontmatter_span(text: str) -> tuple[str, str] | None:
    """Ubica el frontmatter por DELIMITADOR DE LÍNEA, no por búsqueda textual de la subcadena
    `---` (H-11). Un `text.split("---")`/`text.split("---", 2)` corta también dentro de un
    escalar entrecomillado que lleva un `---` adentro (p. ej. `title: "Un titulo con ---
    adentro"`, YAML perfectamente válido): el split textual parte el valor a la mitad y el
    frontmatter que resulta ya no es el YAML real de la nota. Acá una línea sólo cuenta como
    delimitador si, ELLA SOLA (salvo espacio en blanco final), es `---`; un `---` en medio de una
    línea con más contenido no cuenta.

    Devuelve `(bloque_yaml, resto_del_texto)` recortados entre la primera línea delimitadora
    (debe estar en la posición 0 del texto) y la segunda, o `None` si no hay esa apertura en la
    posición 0 o no hay una segunda línea delimitadora (frontmatter sin cerrar) — en ambos casos
    el llamador decide qué reportar (nota sin frontmatter vs. frontmatter roto)."""
    matches = list(_FM_DELIM_RE.finditer(text))
    if len(matches) < 2 or matches[0].start() != 0:
        return None
    apertura, cierre = matches[0], matches[1]
    return text[apertura.end():cierre.start()], text[cierre.end():]


def split_fm(text: str) -> dict:
    """Frontmatter YAML de una nota (dict vacío si no hay o no parsea — el lint reporta aparte las
    notas cuyo YAML está roto). Compartido: lo usan el lint y el dry-run de re-clasificación."""
    span = frontmatter_span(text)
    if span is None:
        return {}
    yaml_block, _body = span
    try:
        return yaml.safe_load(yaml_block) or {}
    except Exception:
        return {}


def as_map(v) -> dict:
    """`v` si es un dict; `{}` si no. El idioma `X.get(k) or {}` asume que `X` tiene la forma
    esperada, pero `X` sale seguido de YAML/JSON editado a mano o de disco ajeno: si el valor es un
    escalar o una lista, ese `or {}` NO salva nada (un escalar truthy no cae en el `or`) y el
    `.get`/`[...]` siguiente revienta con `AttributeError`/`TypeError`. La auditoría encontró el
    mismo guard faltante repetido en 59 líneas de los scripts — centralizarlo acá evita un chequeo
    por sitio (y el que se olvida)."""
    return v if isinstance(v, dict) else {}


def stdout_tolerante() -> None:
    """Hace que **todo** lo que salga por stdout/stderr degrade en vez de matar el proceso en una
    consola no-UTF8 (`ascii`, `cp1252`).

    `print_seguro` cubre los `print` propios, pero **no lo que escribe argparse**: el texto de
    `--help` (con sus `⚠`, `→` y acentos) va directo a `sys.stdout`, así que un `--help` seguía
    saliendo con **exit 1** en los 11 CLIs del repo. Es el mismo modo de falla —un exit code que
    miente— por la única puerta que el helper no podía tapar.

    Se llama desde cada `main()`, no al importar: reconfigurar el stdout del proceso es correcto
    para un CLI, pero sería un efecto colateral inaceptable en una librería que los tests importan
    (rompería la captura de `capsys`)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")     # 3.7+; no-op si ya es UTF-8
        except (AttributeError, ValueError, OSError):
            pass                                     # stream reemplazado por un test o no reconfigurable


def print_seguro(texto: str) -> None:
    """`print` tolerante a consolas no-UTF8. Compartido (nace en `lint.py` como `_print_seguro`,
    6ª pasada de auditoría; se midió después que otros 10 scripts mueren por el mismo motivo —
    quedan acá para que los usen).

    Los mensajes de esta bóveda llevan `⛔`/`⚠`/`→` y están en español: en una consola
    `ascii`/`cp1252` (CI mal configurado, alguna terminal Windows) el encode del stream por
    defecto tira `UnicodeEncodeError` y el proceso muere con exit 1 — indistinguible de "hay
    hallazgos" en un script que usa el exit code como compuerta — aunque el artefacto en disco
    (que se escribe aparte, siempre en UTF-8) haya quedado perfecto. El exit code es la salida
    real de una compuerta de CI; el texto lindo en pantalla es el lujo. Si el stream no puede con
    los caracteres, se degrada el texto en vez de dejar morir la corrida."""
    try:
        print(texto)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(texto.encode(enc, errors="replace").decode(enc))


def as_list(v) -> list:
    """`v` si es una lista; `[]` si no. Hermano de `as_map` para el otro lado del mismo defecto: un
    campo que el schema declara lista (`planets`, `thesis_links`, `posiciones`) pero que llega
    escalar o `None` desde un YAML editado a mano — iterarlo a pelo itera caracteres de un string o
    revienta con `TypeError` en vez de comportarse como la lista vacía que es el caso degenerado
    correcto."""
    return v if isinstance(v, list) else []


# Áreas de vault/wiki/concepts/ RESERVADAS (siempre válidas): `methods` es universal;
# `hypotheses` es estructural (schema name/status + roll-up Dataview). Ver CLAUDE.md.
RESERVED_CONCEPT_AREAS = ("methods", "hypotheses")


def load_concept_areas() -> list:
    """Lista de REFERENCIA de áreas de vault/wiki/concepts/ (para el typo-check; NO restringe — las
    áreas son abiertas). Salen de `concept_areas` en objective.yaml, más las reservadas
    (methods, hypotheses). Devuelve los nombres en orden, deduplicados.

    **`[]` = typo-check APAGADO**: el objetivo no declara la lista. Antes había un modo tolerante
    (inferir las áreas de las carpetas existentes) para instancias pre-feature; se sacó junto con las
    demás capas de compatibilidad — inferir la lista de lo que hay en disco convierte cualquier typo
    ya cometido en "área declarada", que es lo contrario de lo que el chequeo hace. El lint reporta
    la lista ausente para que se declare."""
    declared = load_objective().get("concept_areas") or []
    # `isinstance(list)`: un `concept_areas: indicators` (escalar, el caso natural de una bóveda de
    # un área) se desempaquetaba CARÁCTER POR CARÁCTER y el typo-check se invertía — marcaba como
    # no declarada justo el área recién declarada. Un escalar = lista no declarada: chequeo apagado.
    if not isinstance(declared, list) or not declared:
        return []
    return list(dict.fromkeys([*[str(a) for a in declared], *RESERVED_CONCEPT_AREAS]))


# ── orden de listas de papers (política única, #79) ──────────────────────────
# La cadena decide RELEVANCIA sin mirar citas (`classify()` es regex sobre el contenido), pero
# ORDENA por citas en varios lados, y la cuenta cruda de citas está sesgada por la EDAD del paper:
# los viejos tuvieron más tiempo de acumularlas (*ageing bias*). Donde el orden decide qué se ve —o
# qué sobrevive a un corte— eso empuja lo reciente al fondo, justo lo que los rescates existen para
# recuperar. La política vive acá, en un solo lugar, porque hay varias listas que ordenar en
# archivos distintos y si se cambia una las otras quedan viejas sin que nadie lo note.

def citation_rate(rec: dict, now_year: int | None = None) -> float:
    """Citas por año desde la publicación — el orden que no castiga a lo reciente.

    La tasa cruda tiene el sesgo simétrico (un paper de dos meses con 1 cita tendría una tasa
    enorme), así que la edad se cuenta en años **cumplidos incluyendo el de publicación** y nunca
    baja de 1: lo publicado este año se compara a 1 año, no a una fracción. Es simple y auditable;
    el estándar bibliométrico normaliza por percentil dentro de la cohorte del año, que necesita
    la distribución completa y no la tenemos acá.

    Un `year` ausente, no numérico o futuro (in-press) vale edad 1: no lo premiamos con una tasa
    inventada ni lo castigamos mandándolo al fondo."""
    cites = rec.get("citation_count") or 0
    try:
        year = int(rec.get("year") or 0)
    except (TypeError, ValueError):
        year = 0
    now = now_year if now_year is not None else _dt.date.today().year
    edad = max(1, now - year + 1) if 0 < year <= now else 1
    return cites / edad


def sort_by_citation_rate(recs, now_year: int | None = None) -> list:
    """Lista ordenada por citas/año descendente, DETERMINISTA: ante empate de tasa desempata la
    cuenta cruda y después el bibcode, para que dos corridas sobre el mismo `ads.json` impriman lo
    mismo (los listados se comparan a ojo entre corridas)."""
    return sorted(recs, key=lambda r: (-citation_rate(r, now_year),
                                       -(r.get("citation_count") or 0),
                                       r.get("bibcode") or ""))


# ── registro de ingesta por sujeto (#51/#64) ─────────────────────────────────

def registro_path(slug: str) -> Path:
    return REGISTRO / f"{slug}.yaml"


def legacy_triage_path(slug: str) -> Path:
    """Ubicación PRE-#51 de las decisiones de triage (scratch gitignored). Ya NO se lee en el flujo
    normal: sólo la usan el migrador (`triage.py --migrate`) y el detector del lint, que la reporta
    como bloqueante mientras exista. Nunca se escribe ahí."""
    return ROOT / "build" / slug / "triage.json"


def load_registro(slug: str) -> dict:
    """Registro versionado del sujeto ({} si no existe o si no es legible).

    **Tolerante a la edición a mano, que el framework instruye explícitamente** (el aviso de #81
    manda "sacá la entrada de `decisiones`"): un YAML roto o que no parsea a mapa devuelve `{}` en
    vez de tumbar a sus tres lectores (lint, triage, query_ads). No es una capa de compatibilidad
    —no hay dos schemas— sino la misma política que el frontmatter: ante una bóveda rara se reporta
    y se sigue. El lint reporta el registro ilegible como hallazgo."""
    f = registro_path(slug)
    if not f.exists():
        return {}
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_registro(slug: str, data: dict) -> None:
    """Escribe el registro. Punto único por el que pasan `save_decisiones` y `save_busqueda` — las
    dos garantías de abajo cubren a los dos.

    **No pisa un registro existente que no se pudo leer.** El registro es, por definición del
    repo, lo que NO es regenerable (#51/#64: `busqueda` — sobre qué universo de papers afirma la
    ficha — y `decisiones` — el juicio de curación). `load_registro` degrada un YAML roto a `{}`
    para no tumbar a sus lectores (lint, triage, query_ads); pero si ESE `{}` tolerante después se
    guarda acá, el archivo original se pierde en silencio. Y el framework instruye editar este
    archivo a mano (`ingest_topic.py` avisa "sacá la entrada de `decisiones`"), así que un YAML
    roto es un estado alcanzable, no una hipótesis: mejor frenar con un mensaje accionable que
    perder curación que nadie puede reconstruir.

    **Escritura atómica.** `write_text` directo deja el archivo torn si el proceso muere a mitad de
    la escritura (medido: con un registro de 111 KB, 17 de 46 lecturas concurrentes vieron el
    archivo cortado). Se escribe a un temporal en el MISMO directorio (mismo filesystem, para que
    el rename sea atómico en POSIX) y se publica con `os.replace`, que sustituye el archivo de una
    sola vez — un fallo antes del `replace` deja el original intacto."""
    REGISTRO.mkdir(parents=True, exist_ok=True)
    f = registro_path(slug)
    if f.exists():
        try:
            existente = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as exc:
            raise RuntimeError(
                f"{f} existe pero no se pudo leer (YAML roto) — no lo piso a ciegas: se "
                "perderían `busqueda` y las `decisiones` de curación que tiene adentro, y no son "
                "regenerables. Arreglalo a mano (es un archivo que el framework instruye editar "
                "directamente) y volvé a correr la operación."
            ) from exc
        if not isinstance(existente, dict):
            raise RuntimeError(
                f"{f} existe pero no parsea a un mapa (YAML válido con forma equivocada) — no lo "
                "piso a ciegas: se perderían `busqueda` y las `decisiones` de curación. Arreglalo "
                "a mano y volvé a correr la operación."
            )
    tmp = f.with_name(f.name + f".tmp{os.getpid()}")
    tmp.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8")
    try:
        os.replace(tmp, f)
    except Exception:
        # publicación fallida: no dejar el temporal como basura silenciosa, pero priorizar
        # propagar el error real por sobre uno de limpieza.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def load_decisiones(slug: str) -> dict:
    """Decisiones de triage del sujeto, **del registro versionado y nada más**.

    Antes esto mergeaba también el `build/<slug>/triage.json` pre-1.9.0 (migración transparente).
    Se sacó: una capa de compatibilidad en el lector es complejidad permanente, y el juicio viejo
    tiene un camino explícito —`python scripts/triage.py <slug> --migrate`—. Lo que NO puede pasar
    es que ese archivo quede **mudo** y el triage vuelva a proponer lo ya descartado sin decir nada:
    el lint lo detecta y bloquea."""
    d = load_registro(slug).get("decisiones") or {}
    if not isinstance(d, dict):
        return {}
    # una entrada que no es mapa (edición a mano: `2006R: descartado`) se descarta en vez de
    # reventar a los lectores con AttributeError; el lint la reporta.
    return {k: v for k, v in d.items() if isinstance(v, dict)}


# Los DOS CARRILES de curación viven en las mismas `decisiones` (#51 chaining, #81 fuente
# declarada) y se distinguen por `origen`. Sin `origen` = chaining (las decisiones anteriores a #81).
def es_del_carril(d: dict, carril: str) -> bool:
    """¿Esta decisión es del carril pedido? Sin este filtro `origen` es **decorativo**: el gate de
    candidatos del chaining se comía los rechazos de fuentes declaradas (y al revés), que es
    justamente la distinción que #81 introdujo."""
    return (d.get("origen") or "chaining") == carril


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
