"""Configuración compartida de los scripts de ingesta de la bóveda.

- Resuelve rutas del repo (sin asumir cwd).
- Lee el token ADS de vault/config/ads_dev_key o de la variable de entorno ADS_DEV_KEY.
- Carga vault/config/stars.yaml, vault/config/themes.yaml y vault/config/objective.yaml.
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
ALMAGESTO_VERSION = "1.44.0"

# PLACEHOLDER de `name` que trae el template en vault/config/objective.yaml. Es un placeholder
# explícito (no un nombre de ejemplo plausible: un objetivo real que coincida con el del ejemplo
# daría WARN permanente sin forma de apagarlo). El lint AVISA (WARN) mientras `name` siga siendo
# este string — la instancia no definió su objetivo (skill `setup`) y clasifica "core" con la
# regex del ejemplo. Mantener en sync con el YAML del template.
# @inv INV-57
DEFAULT_OBJECTIVE_NAME = "<definir con el skill setup>"

ROOT = Path(__file__).resolve().parent.parent  # raíz del repo (andamiaje + bóveda)
VAULT = ROOT / "vault"                          # la bóveda: contenido (config/wiki/raw); Obsidian abre acá
CONFIG = VAULT / "config"
STARS_YAML = CONFIG / "stars.yaml"
THEMES_YAML = CONFIG / "themes.yaml"
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


def snapshot_url(path) -> str | None:
    """`source_url` del header de un snapshot web, o `None`. Gemelo de `snapshot_retrieved`: el
    header lo escribe `fetch_web` y el parser vive acá, un solo lugar de verdad. Lo necesita el
    quinto detector de la pasada de red (D-41): para saber si la página cambió hay que saber **qué
    página era**, y esa URL está en el `.txt`, no en la nota (que puede no existir)."""
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[:8]:
            m = re.match(r"source_url\s*:\s*(\S+)", line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return None


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

# ── secciones ESTAMPADAS por la máquina (D-11 / INV-81) ──────────────────────────────────────────
# No son prosa: son metadata materializada. Vive acá y no en cada consumidor porque son TRES los
# módulos que necesitan el mismo recorte —`lint` (proxies y cobertura), `make_notes` (¿está citado
# en esta ficha?) y `lib_blocks` (el fan-out de verify-citations)— y hasta 1.38.1 cada uno tenía su
# propia copia, con listas DISTINTAS: la de `make_notes` no incluía `## Planetas` ni
# `## Verificación de citas`, y `lib_blocks` no tenía ninguna. Es la red #2 aplicada: si N módulos
# prometen la misma forma, se declara una vez.
#
# El modo de falla que cierran: un artefacto que se mide a sí mismo siempre da el resultado que su
# propia existencia produce. Medido en el clean-room del 2026-08-25 sobre la ficha de HD 40307,
# `lib_blocks.pairs_of` devolvía **178** pares (afirmación, bibcode) contra **68** reales — 110 de
# metadata—, y entre ellos nueve bibcodes que NO están en ninguna afirmación: los cuatro sin
# fulltext y los cinco declarados `no_sintetizado`. Correr `verify-citations` según el skill habría
# lanzado 110 subagentes a verificar filas de tabla, cuatro de ellos contra un `.txt` inexistente.
SECCIONES_ESTAMPADAS = ("## Planetas", "## Papers", "## Métodos aplicados a esta estrella",
                        "## Papers que tocan este tema (auto)", "## Excluidos por el filtro",
                        "## Verificación de citas")


def solo_prosa(body: str) -> str:
    """El cuerpo SIN las secciones que estampa la máquina — lo que alguien escribió de verdad."""
    out, saltando = [], False
    for ln in body.split("\n"):
        if ln.startswith("## "):
            saltando = any(ln.startswith(h) for h in SECCIONES_ESTAMPADAS)
        if not saltando:
            out.append(ln)
    return "\n".join(out)


def section_start(text: str, header: str) -> int:
    """Index where the `header` section starts, anchored to a line break, or -1 if absent.

    A bare `str.find(header)` also matches a mention **inside** a line — and pointing the reader at
    a section from prose is exactly what a well-written note does: ``Valores en `## Inventario por
    eje` ``. The bare find takes that mention, the caller slices up to the real header, and the
    section comes back empty.

    Measured (2026-08-25): `lint.inventario_sin_llenar` reported a ficha whose inventory had **36
    rows** as *"the cross-paper contrast left no trace"* — the #101 detector accusing the very step
    that did run. A map that misattributes is worse than an empty one.

    Trailing text after the header is allowed on purpose: real headers carry suffixes
    (`## Papers (25 · 16 sintetizados…)`, `## Verificación de citas (2026-08-25)`). What is NOT
    allowed is anything before it on the same line — that is the whole point.
    """
    #  @inv INV-98
    if text.startswith(header):
        return 0
    i = text.find("\n" + header)
    return -1 if i < 0 else i + 1


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
    #  @inv INV-67
        return ADS_KEY_FILE.read_text().strip()
    raise RuntimeError(
        "No hay token ADS. Poné vault/config/ads_dev_key o exportá ADS_DEV_KEY. "
        "Token gratis en https://ui.adsabs.harvard.edu/user/settings/token"
    )


def require_field(meta: dict, key: str, entry: str, yaml_name: str, hint: str = ""):
    """Campo OBLIGATORIO de una entrada de config: si falta o está vacío, salida amigable
    (qué entrada, qué campo, en qué archivo) en vez de un KeyError crudo con traceback.
    Para los índices duros que los scripts acceden a pelo (`ads_object`/`simbad` en stars,
    `query` en themes) — un campo olvidado al cargar la entrada a mano es el caso típico."""
    val = meta.get(key)
    if val in (None, ""):
        raise SystemExit(
            f"la entrada '{entry}' no tiene `{key}` en vault/config/{yaml_name} — "
            "agregalo (ver el ejemplo comentado del YAML)." + (f" {hint}" if hint else ""))
    return val


def load_stars() -> dict:
    """dict {nombre_canonico: {slug, simbad, ads_object, aliases, data_local}}. Un YAML vacío
    (instancia recién creada / sólo comentarios) parsea a None → {} para que star_by_slug dé su
    KeyError amigable y no un AttributeError (mismo guard que load_themes)."""
    with open(STARS_YAML, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def star_by_slug(slug: str) -> tuple[str, dict]:
    """Devuelve (nombre_canonico, meta) buscando por slug. Lanza KeyError si no existe."""
    for name, meta in load_stars().items():
        if meta.get("slug") == slug:
            return name, meta
    raise KeyError(f"slug desconocido: {slug!r}. Definilo en vault/config/stars.yaml")


def load_themes() -> dict:
    """dict {slug: {title, area, concept, query, aliases}} (registro de temas, análogo a stars)."""
    if not THEMES_YAML.exists():
        return {}
    with open(THEMES_YAML, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def theme_by_slug(slug: str) -> tuple[str, dict]:
    """Devuelve (slug, meta) del tema. La clave del YAML ES el slug. KeyError si no existe."""
    themes = load_themes()
    if slug in themes:
        return slug, themes[slug]
    raise KeyError(f"tema desconocido: {slug!r}. Definilo en vault/config/themes.yaml")


def load_objective() -> dict:
    """El OBJETIVO de la bóveda (vault/config/objective.yaml): name/short/description y el
    clasificador de relevancia (`relevance.facets`, `relevance.noise_doctypes`). Es
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
    except (yaml.YAMLError, UnicodeDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def yaml_error(path: Path, que: str) -> str | None:
    """Motivo por el que `path` no se puede usar como registro de sujetos, o `None` si está sano.

    Hermano de `objective_error` para `stars.yaml`/`themes.yaml`. D-6 cerró la puerta de la lente
    y dejó estas dos abiertas: `load_stars`/`load_themes` **propagan** el `yaml.YAMLError`, así que
    un `:` sin comillas en un título hace morir a `lint.py` con traceback — que no es "reportar
    como bloqueante", es llevarse puestos los otros chequeos sin dejar reporte. Un chequeo que no
    puede correr tiene que decirlo (INV-87), no tumbar al que lo llama.  @inv INV-80"""
    if not path.exists():
        return None                      # ausente es legítimo: una bóveda puede no tener temas
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return f"{path} no parsea como YAML: {' '.join(str(exc).split())} ({que})"
    except OSError as exc:
        return f"{path} no se pudo leer: {exc}"
    if data is not None and not isinstance(data, dict):
        return f"{path} parsea, pero no a un mapa (es {type(data).__name__}) — {que}"
    return None


def stars_error() -> str | None:
    """@inv INV-80"""
    return yaml_error(STARS_YAML, "cada clave es una estrella")


def themes_error() -> str | None:
    """@inv INV-80"""
    return yaml_error(THEMES_YAML, "cada clave es un tema")


def objective_error() -> str | None:
    """Motivo por el que `objective.yaml` no se puede usar como lente, o `None` si está sano.

    `load_objective` colapsa tres estados en dos: archivo ausente (`RuntimeError`) y **todo lo
    demás** (YAML roto, YAML válido con forma equivocada, objetivo legítimamente vacío) en el mismo
    `{}` mudo. Esa fusión es el HUECO-1 / INV-80: el clasificador seguía corriendo con una regla
    que nadie escribió, el registro guardaba esa lente vacía como si fuera la vigente, y el lint no
    decía nada.

    Esta función separa los estados **para el llamador estricto** —`query_ads`, que rehúsa operar,
    y el lint, que lo reporta como *no evaluado*— sin cambiarle la firma a `load_objective`: sus
    llamadores tolerantes siguen igual, que es lo que hace que el lint no se muera ante una bóveda
    rara.  @inv INV-80"""
    if not OBJECTIVE_YAML.exists():
        return f"{OBJECTIVE_YAML} no existe (es el archivo que define el objetivo de la bóveda)"
    try:
        with open(OBJECTIVE_YAML, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        motivo = " ".join(str(exc).split())
        return (f"{OBJECTIVE_YAML} no parsea como YAML: {motivo}. El error más probable es un `:` "
                "sin comillas dentro de una regex de `relevance.facets` — entrecomillá el patrón.")
    except OSError as exc:
        return f"{OBJECTIVE_YAML} no se pudo leer: {exc}"
    if data is None:
        return f"{OBJECTIVE_YAML} está vacío — no hay lente con la que clasificar"
    if not isinstance(data, dict):
        return (f"{OBJECTIVE_YAML} parsea, pero no a un mapa (es {type(data).__name__}) — la lente "
                "tiene que ser un mapa con `name`/`relevance`")
    return None


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
    # @inv INV-36
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


def load_downstream() -> list:
    """Nombres propios de los **consumidores** de la bóveda, declarados en `downstream: []` de
    `objective.yaml`. Insumo del detector de fuga (D-50), NO de la clasificación.

    Existe porque la mitad más frecuente de la fuga de la frontera dura no es un `w_j` suelto: es
    la **auto-referencia** — la nota explicando para qué le sirve el dato a quien la consume ("los
    scripts de ICA lo usan para…"). Los marcadores genéricos (`nuestro pipeline`, `downstream`) se
    detectan sin declarar nada; el nombre propio del repo consumidor no se puede adivinar, y
    hardcodear uno metería el nombre del consumidor en el framework, que es exactamente lo que la
    regla #0 prohíbe.

    **Vacío o ausente = esa mitad está APAGADA, sin WARN de ausencia** (a diferencia de
    `concept_areas`): declarar a quién le sirve la bóveda es opcional por diseño — el flujo es
    unidireccional y una bóveda sin consumidor nombrado es el caso normal, no una config a medias.
    Un escalar (`downstream: ICA`) se toma como un solo elemento: perder la curación por no poner
    corchetes es el defecto que R1/R13/R16 ya midieron."""
    # @inv INV-04
    raw = load_objective().get("downstream")
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    return [str(raw)] if raw and str(raw).strip() else []


def load_concept_areas() -> list:
    """Lista de REFERENCIA de áreas de vault/wiki/concepts/ (para el typo-check; NO restringe — las
    áreas son abiertas). Salen de `concept_areas` en objective.yaml, más las reservadas
    (methods, hypotheses). Devuelve los nombres en orden, deduplicados.

    **`[]` = typo-check APAGADO**: el objetivo no declara la lista. Antes había un modo tolerante
    (inferir las áreas de las carpetas existentes) para instancias pre-feature; se sacó junto con las
    demás capas de compatibilidad — inferir la lista de lo que hay en disco convierte cualquier typo
    ya cometido en "área declarada", que es lo contrario de lo que el chequeo hace. El lint reporta
    la lista ausente para que se declare."""
    # @inv INV-47
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
    inventada ni lo castigamos mandándolo al fondo.

    ⚠ `citation_count` se coerce igual que `year`. Un `ads.json` con tipos torcidos es un estado
    alcanzable —`make_notes.excluded_table` tiene un test que lo siembra a propósito y promete
    **nunca lanzar**—, así que la política compartida no puede ser el eslabón que revienta: si acá
    saltara un `TypeError`, la cadena moriría DESPUÉS de gastar la red, y encima en la función que
    varios llamadores usan justamente para no duplicar el criterio."""
    try:
        cites = float(rec.get("citation_count") or 0)
    except (TypeError, ValueError):
        cites = 0.0
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
    def _cuenta(r) -> float:
        try:                                  # mismo motivo que en `citation_rate`: el desempate
            return float(r.get("citation_count") or 0)   # no puede ser el que revienta la cadena
        except (TypeError, ValueError):
            return 0.0

    return sorted(recs, key=lambda r: (-citation_rate(r, now_year), -_cuenta(r),
                                       str(r.get("bibcode") or "")))


# ── registro de ingesta por sujeto (#51/#64) ─────────────────────────────────

# ── escritura atómica: el ÚNICO writer del repo (D-53 / INV-90) ──────────────────────────────────

def write_text_atomic(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Publica `text` en `path` sin dejarlo nunca a medio escribir.  @inv INV-90

    Se escribe primero a un temporal en el **mismo directorio** (mismo filesystem, condición para
    que el rename sea atómico en POSIX) y se publica con `os.replace`, que sustituye el archivo de
    una sola vez: o está el viejo entero, o el nuevo entero, nunca la mitad.

    ⚠ Por qué NO alcanza "respaldar el original y restaurar en el `except`": ese patrón sólo cubre
    el corte que llega como **excepción**. Ante un `SIGKILL` o un corte de energía no corre ningún
    `except` y el archivo queda truncado igual.

    El `try/finally` limpia el temporal cuando el fallo ocurre **antes** de publicar — el caso que
    los writers viejos no cubrían: `save_registro` escribía el tmp fuera de todo `try`, así que un
    disco lleno a mitad de esa escritura dejaba un `.tmp<pid>` huérfano en `vault/config/`. El
    archivo real nunca se corrompía; era basura de disco, pero basura que se commitea.

    Medido con `ulimit -f` sobre el writer que más escribe: el `write_text` directo dejaba una nota
    de 16.071 B en 8.192 B, con 198 de 400 ocurrencias de la extracción LLM —lo MENOS regenerable
    de la bóveda— desaparecidas sin aviso.

    `os.replace` se llama como atributo del módulo `os` para que un test pueda interceptarlo."""
    _publicar(path, lambda tmp: tmp.write_text(text, encoding=encoding))


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Gemela binaria de `write_text_atomic` (PDFs).  @inv INV-90

    H-07: un `dest.write_bytes(...)` directo cortado a la mitad deja un PDF TRUNCADO en el destino
    FINAL (medido: 35 B), y el único chequeo de idempotencia de la cadena es `dest.exists()`: ese
    PDF roto cuenta como "ya bajado" para siempre, sin forma de reintentarlo salvo borrarlo a mano."""
    _publicar(path, lambda tmp: tmp.write_bytes(data))


def copy_file_atomic(src: Path, dest: Path) -> None:
    """Copia un archivo AL DESTINO FINAL de forma atómica, preservando mtime (`copy2`).  @inv INV-90

    Misma garantía que `write_bytes_atomic`, para el caso en que el origen es otro archivo y no un
    buffer en memoria. Existe porque `shutil.copy2(src, dest)` directo tiene **exactamente** el modo
    de falla que H-07 cerró para `write_bytes`: escribe en el destino final, así que un corte deja un
    PDF truncado que `if dest.exists()` da por bajado para siempre. El guard estático de
    `tests/test_lib_config.py` no lo veía porque buscaba `.write_text(`/`.write_bytes(`."""
    import shutil
    _publicar(dest, lambda tmp: shutil.copy2(src, tmp))


def _publicar(path: Path, llenar) -> None:
    """tmp en el mismo directorio → `llenar(tmp)` → `os.replace`. Limpia el temporal ante cualquier
    fallo, en las dos mitades (llenando el tmp, y publicando)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    try:
        llenar(tmp)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


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
    #  @inv INV-25
        return {}
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError):
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
    archivo a mano (`ingest_theme.py` avisa "sacá la entrada de `decisiones`"), así que un YAML
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
    #  @inv INV-53
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
    write_text_atomic(
        f, yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False))


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


# Vocabulario CERRADO de `via` en `extra_core` (D-58): de dónde salió la aceptación de ese paper.
# Cerrado por el mismo motivo que `role` (#73): un typo deja el campo mudo para el único consumidor
# que existe —la columna Origen de la ficha—, y un campo mudo se lee como "no se sabe".
EXTRA_CORE_VIA = ("usuario", "triage", "citado-por-corpus")


def load_extra_core(meta: dict, *, entry: str = "?") -> list:
    """`extra_core` en su forma canónica: lista de mapas `{bibcode, via, motivo[, fecha]}`.

    **R-2 (decidida con el usuario, 2026-08-24): forma dura con detector**, no lector tolerante.
    Hasta 1.26.0 el atajo `extra_core: [2020X]` (y hasta el escalar `extra_core: 2020X`) se aceptaba
    vía `_listify_curado`. El costo no es de estilo: una aceptación así no dice **quién** la aceptó
    ni **por qué**, que es exactamente el dato no regenerable que #51 persiste para el carril del
    **descarte**. Los dos carriles de curación tienen que registrar lo mismo, o el registro cuenta
    media historia — y era la mitad optimista: lo que se dejó afuera, con motivo; lo que se metió,
    a ciegas.

    El costo de UX quedó acotado porque `triage.py` imprime el snippet ya estructurado para pegar:
    sólo se siente al agregar un bibcode 100% a mano, que es cuando más importa saber por qué está.

    Aborta con el snippet correcto en el mensaje ante cualquier forma vieja — un detector que no
    muestra la salida obliga a leer la doc, y ahí es donde la gente inventa una tercera forma."""
    v = meta.get("extra_core")
    if v is None:
        return []
    if not isinstance(v, list) or any(not isinstance(x, dict) for x in v):
    #  @inv INV-60
        sueltos = [v] if isinstance(v, str) else [x for x in as_list(v) if isinstance(x, str)]
        sys.exit(_extra_core_error(entry, sueltos,
                                   "`extra_core` ya no acepta un bibcode suelto ni una lista de "
                                   "strings (D-58): sin `via` y `motivo` el registro no dice quién "
                                   "aceptó ese paper ni por qué"))
    for x in v:
        faltan = [k for k in ("bibcode", "via", "motivo") if not x.get(k)]
        if faltan:
            sys.exit(_extra_core_error(entry, [x.get("bibcode") or "<bibcode>"],
                                       f"a una entrada de `extra_core` le falta {', '.join(faltan)}"))
        if x["via"] not in EXTRA_CORE_VIA:
            sys.exit(_extra_core_error(
                entry, [x["bibcode"]],
                f"`via: {x['via']}` no está en el vocabulario ({' | '.join(EXTRA_CORE_VIA)})"))
    return v


def _extra_core_error(entry: str, bibcodes: list, motivo: str) -> str:
    """El mensaje del detector, con la forma nueva ya escrita para pegar."""
    ejemplo = "\n".join(
        f"  - bibcode: {b}\n    via: usuario        # {' | '.join(EXTRA_CORE_VIA)}\n"
        f"    fecha: AAAA-MM-DD\n    motivo: <por qué este paper es core>"
        for b in (bibcodes or ["<bibcode>"]))
    return (f"'{entry}': {motivo}. Forma canónica:\n\nextra_core:\n{ejemplo}\n")


# Costo de leer un paper, en tokens de fulltext. Mediana medida sobre el corpus real (T-3): sirve
# para proyectar el costo del ingest desde el conteo core, que es la otra mitad de la decisión que
# el probe existe para tomar.
TOKENS_POR_PAPER = 24_000


# ── D-1 / INV-76: autoridad por campo del ground-truth ───────────────────────────────────────────
#
# Cada campo del espejo tiene UNA autoridad declarada. Si esa autoridad calla, el campo es `null`
# **aunque la otra tenga el dato** — porque el contrato promete que el frontmatter es la capa
# auditable, y un valor cuya procedencia depende de quién contestó primero no lo es: el consumidor
# no puede distinguirlo de uno con una sola fuente.
#
# `spectral_type` ← SIMBAD porque es su dominio (clasificación espectral curada); el resto ← NEA
# (pscomppars), que es la autoridad del sistema planetario. Hasta 1.27.0 `spectral_type` salía de
# NEA y SIMBAD sólo rellenaba el hueco, sin registrar cuál ganó.
#
# La declaración vive acá y no en cada script porque la comparten tres consumidores
# (`fetch_ground_truth` escribe, `make_notes` la publica en la cabecera de la ficha, `lint` la
# vigila): repetirla es cómo se desincronizan.  @inv INV-76
# @inv INV-14
AUTORIDAD_CAMPO = {
    "spectral_type": "simbad",
    "teff_K": "nea",
    "dist_pc": "nea",
    "st_rotp_days": "nea",   # clave del JSON; en la ficha es `P_rot_days`
    "mass_msun": "nea",
    "Vmag": "nea",
    "ra_deg": "nea",
    "dec_deg": "nea",
}

# Nombre legible de cada autoridad, para la cabecera de la ficha.
AUTORIDAD_NOMBRE = {"nea": "NASA Exoplanet Archive (pscomppars)", "simbad": "SIMBAD"}

# Cómo se llama cada campo del JSON EN LA FICHA. La cabecera nombra lo que el lector ve en el
# frontmatter, no la clave interna del ground-truth (`st_rotp_days` no aparece en ninguna ficha).
CAMPO_EN_FICHA = {"st_rotp_days": "P_rot_days"}


def artefacto_en_otro_slug(base: Path, slug: str, stem: str, sufijo: str):
    """El mismo artefacto (`<stem><sufijo>`) ya bajado bajo OTRO slug, o `None` (D-18).

    Un paper relevante para dos sujetos se bajaba dos veces — medido: 33 copias en la instancia
    real. El archivo es idéntico (mismo bibcode), y la red es a la vez el recurso caro y el que
    puede fallar: re-bajarlo no agrega nada y agrega un modo de falla. Se devuelve la ruta para
    que el llamador copie (no symlink: `raw/` viaja en git-lfs y un enlace roto es peor que una
    copia).

    Determinista: si hay varias, gana la primera en orden alfabético de slug."""
    for candidato in sorted(base.glob(f"*/{stem}{sufijo}")):
        if candidato.parent.name != slug:
            return candidato
    return None


def load_extraccion(slug: str) -> dict:
    """Qué declaró el ingest sobre lo que leyó (D-13/D-14): `{subconjunto, criterio, fecha}`."""
    return as_map(load_registro(slug).get("extraccion"))


def save_extraccion(slug: str, *, subconjunto: bool, criterio: str) -> None:
    """Declara.  @inv INV-83 que este ingest leyó (o no) todos los core, y con qué criterio recortó.

    El contrato dice que el ingest lee **todos** los core; la reconciliación anticipa que el
    subconjunto va a ser el caso normal (≈6M tokens por estrella si no). Lo que no puede pasar es
    que el recorte sea **invisible**: la ficha se presenta como snapshot del universo, y un lector
    no tiene forma de saber que se sintetizó desde 8 de 42 papers. El criterio declarado es la
    pieza que más se va a leer — por eso es texto libre y obligatorio, no un booleano."""
    data = load_registro(slug)
    data.setdefault("slug", slug)
    data["extraccion"] = {"subconjunto": bool(subconjunto), "criterio": criterio,
                          "fecha": _dt.date.today().isoformat()}
    save_registro(slug, data)


def save_sintesis(slug: str, *, n_papers: int | None = None, nota: str = "") -> None:
    """Declara CUÁNDO se sintetizó el sujeto — la tercera fecha de INV-82.  @inv INV-82

    El contrato promete tres fechas distinguibles (búsqueda, síntesis, verificación) que pueden
    divergir **sin que ninguna mienta**, y había dos: la de búsqueda la escribe `query_ads` y la de
    verificación sale del encabezado del bloque de citas, pero **la síntesis no dejaba rastro**. El
    efecto es el que INV-82 existe para impedir: refrescar el corpus movía la fecha de búsqueda y la
    ficha se leía como re-sintetizada, cuando la prosa era la de tres meses atrás.

    No se puede derivar: `git` da la fecha del último toque al ARCHIVO (una cirugía de cabecera
    cuenta igual que reescribir el resumen) y fuera de un repo no da nada. Así que se **declara**,
    como el recorte de lectura — mismo canal (`triage.py --sintesis`) y mismo criterio: lo que la
    máquina no puede medir, alguien lo dice y queda versionado."""
    data = load_registro(slug)
    data.setdefault("slug", slug)
    entrada = {"fecha": _dt.date.today().isoformat(), "version": ALMAGESTO_VERSION}
    if n_papers is not None:
        entrada["n_papers"] = int(n_papers)
    if nota:
        entrada["nota"] = nota
    data["sintesis"] = entrada
    save_registro(slug, data)


def anular_decision(slug: str, clave: str, *, por: str, carril: str = "chaining") -> bool:
    """Anula un descarte que se está revirtiendo, preservando el juicio viejo adentro (D-52).

    El problema que cierra: al re-aceptar un bibcode que estaba descartado —agregándolo a
    `extra_core`, o volviendo a declarar la fuente en `sources:`— la decisión vieja **se quedaba
    ahí contradiciendo lo que se hizo**. El registro decía "descartado por ruido" sobre un paper
    que está ingestado, y el consumidor no tiene forma de saber cuál de las dos afirmaciones vale.
    `query_ads` sólo lo salteaba y `ingest_theme` sólo avisaba: ninguno tocaba el registro.

    Anular no es borrar. El motivo viejo queda en `previa`, porque es exactamente el dato **no
    regenerable** que #51 existe para conservar: por qué alguien miró ese paper y dijo que no. La
    entrada nueva agrega quién la revirtió y cuándo.

    Respeta los dos carriles (#51 chaining, #81 fuente declarada): anular un descarte de fuente
    declarada no toca el del chaining con la misma clave. Devuelve `True` si anuló algo."""
    decisiones = load_decisiones(slug)
    d = decisiones.get(clave)
    if not d or d.get("decision") != "descartado" or not es_del_carril(d, carril):
        return False
    decisiones[clave] = {
        "decision": "anulada",
        "fecha": _dt.date.today().isoformat(),
        "anulada_por": por,
        "origen": d.get("origen") or "chaining",
        "previa": dict(d),
    }
    save_decisiones(slug, decisiones)
    return True


def save_decisiones(slug: str, decisiones: dict) -> None:
    """Persiste las decisiones preservando `busqueda` (la escribe query_ads, no el triage)."""
    data = load_registro(slug)
    data.setdefault("slug", slug)
    data["decisiones"] = decisiones
    save_registro(slug, data)


def load_busquedas(slug: str) -> list:
    """Las búsquedas del sujeto, en orden cronológico de corrida (D-28).  @inv INV-89

    Lector ESTRICTO: sólo entiende `busquedas: []`. Un registro con la clave vieja `busqueda:`
    (mapa, una sola corrida) devuelve `[]` — y el lint lo reporta como schema viejo, bloqueante.
    Sin lector tolerante: dos semánticas conviviendo en el lector es complejidad permanente, y un
    registro que el lector ignora en silencio deja la ficha afirmando sobre un universo que nadie
    puede reconstruir."""
    return [b for b in as_list(load_registro(slug).get("busquedas")) if isinstance(b, dict)]


def universo_acumulado(slug: str) -> int:
    """Cuántos papers distintos vio el sujeto en TODAS sus búsquedas — unión, no suma (INV-89).

    Sumar los `n_total` cuenta dos veces los papers que ya estaban: con dos corridas solapadas de 3
    papers cada una que comparten 2, la suma dice 6 y la verdad es 4. Cuando una entrada trae
    `bibcodes` la unión es exacta; si alguna no los trae (registro viejo, o una corrida que no los
    guardó) esa entrada sólo puede aportar **cardinalidad**, y ahí se toma el MÁXIMO: es la cota
    inferior honesta del universo. Nunca la suma."""
    vistos: set = set()
    tope = 0
    for b in load_busquedas(slug):
        bibs = as_list(b.get("bibcodes"))
        if bibs:
            vistos.update(bibs)
        tope = max(tope, int(b.get("n_total") or 0))
    return max(len(vistos), tope)


def save_busqueda(slug: str, busqueda: dict) -> None:
    """APPENDEA una corrida a `busquedas: []`, preservando `decisiones` (las escribe triage.py).

    D-28: antes esto PISABA. Cada corrida borraba la anterior, así que el registro sólo sabía de la
    última y la cabecera de la ficha publicaba SU embudo como si fuera el universo entero — una
    ficha refrescada tres veces mostraba el recorte de la tercera corrida y nada de las otras dos.

    La entrada nueva se estampa con `n_nuevos` / `n_ya_estaban` contra el conjunto ya conocido del
    sujeto (los `bibcodes` de las corridas previas): es lo que distingue "traje 40 papers" de
    "traje 40 papers de los cuales 38 ya estaban", que es la pregunta real de un refresh."""
    # @inv INV-51
    data = load_registro(slug)
    data.setdefault("slug", slug)
    previas = [b for b in as_list(data.get("busquedas")) if isinstance(b, dict)]
    conocidos: set = set()
    for b in previas:
        conocidos.update(as_list(b.get("bibcodes")))
    entrada = dict(busqueda)
    bibs = as_list(entrada.get("bibcodes"))
    if bibs:
        entrada["n_nuevos"] = len([b for b in bibs if b not in conocidos])
        entrada["n_ya_estaban"] = len([b for b in bibs if b in conocidos])
    # D-28: la clave vieja `busqueda:` (mapa, UNA corrida) es el schema pre-1.26. El lector nuevo
    # no la entiende y el lint la bloquea — pero **borrarla destruye la única corrida que ese
    # registro documenta**, y el registro es el único artefacto no regenerable de la bóveda
    # (INV-53: "escribir un registro nuevo no borra el juicio ya registrado, y la historia es
    # reconstruible"). Se PLIEGA al frente de la lista, marcada, en vez de perderse: así la
    # migración no cuesta información y el universo acumulado la puede contar.
    vieja = data.pop("busqueda", None)
    if isinstance(vieja, dict) and not previas:
        vieja = {**vieja, "schema": "pre-D-28 (plegada al migrar; una sola corrida)"}
        previas = [vieja]
    data["busquedas"] = previas + [entrada]
    save_registro(slug, data)


# Orden canónico de la cadena de ESTRELLAS. Fuente de verdad del orden: el header de
# `ingest_star.py` (y su constante `CHAIN`); acá vive la copia que el lint usa para nombrar el paso
# donde se cortó, con `check_retractions` al final, que el orquestador corre aparte.
CADENA_ESTRELLA = ("query_ads", "fetch_arxiv", "fetch_pdf", "fetch_ground_truth",
                   "make_notes", "extract_fulltext", "check_retractions")

# Variable que el orquestador exporta al lanzar cada paso, para que el propio paso sepa si lo
# corrió la cadena o una mano. No es un flag porque tiene que atravesar el `subprocess.run`.
VIA_ENV = "ALMAGESTO_VIA"
# Las escotillas del ORQUESTADOR (INV-44). `save_paso` estampa los flags del PASO, y cada script se
# estampa a sí mismo — pero el `--yes` que saltea la guardia de expansión es del orquestador, no de
# ningún paso, así que no llegaba a ninguna entrada: la escotilla que más cambia lo que la cadena
# hizo era la única sin traza. Viaja por entorno, como `VIA_ENV`, porque tiene que atravesar el
# `subprocess.run` sin tocarle el CLI a cada script. Se estampan con prefijo `orquestador:` para
# que no se confundan con los del paso.
FLAGS_ENV = "ALMAGESTO_FLAGS"


def load_cadena(slug: str) -> list:
    """Los pasos que corrieron para este sujeto, en orden (D-57).  @inv INV-91"""
    return [p for p in as_list(load_registro(slug).get("cadena")) if isinstance(p, dict)]


def flags_usados(args, ap=None, ignorar=("theme",)) -> list:
    """Los flags NO-DEFAULT de esta corrida, para `cadena:` del registro (D-48/D-57).  @inv INV-44

    Implementación **única**: vivía copiada en siete scripts (seis idénticas y una con
    `chr(95)/chr(45)` en vez de los literales), y las siete tenían el mismo agujero — sólo miraban
    `v is True`, así que **`--limit` no se registraba**, que es justamente el flag que más cambia lo
    que la corrida hizo: con `--limit 1` sobre cuatro pendientes, tres papers no se intentaron
    siquiera, y la traza decía "corrió fetch_pdf" igual que una corrida completa. Red #2: si N
    módulos prometen la misma forma, se prueba **una vez parametrizada**, no con prosa en N
    docstrings.

    Con `ap` (el `ArgumentParser`) se incluyen además los flags **con valor** que difieren de su
    default, como `--limit=1` o `--rows=5000`. Sin `ap` no se puede saber qué es default y qué lo
    pusieron a mano, así que sólo salen los booleanos — degradar a "todos los valores" llenaría la
    traza de ruido constante y degradar a "ninguno" es el agujero que esto cierra."""
    # Los POSICIONALES no son flags: `--slug=tau-cet` salía en TODA corrida de los seis scripts
    # cuyo posicional se llama `slug`, que es el ruido constante que este docstring dice evitar
    # (AUD-44). `ignorar` listaba `theme` a mano — la exclusión era intencional y se perdió para el
    # resto. Con `ap` se derivan del parser en vez de enumerarlos.
    posicionales = set()
    if ap is not None:
        posicionales = {a.dest for a in ap._actions if not a.option_strings}
    out = []
    for k, v in vars(args).items():
        if k in ignorar or k in posicionales:
            continue
        nombre = f"--{k.replace('_', '-')}"
        if v is True:
            out.append(nombre)
        elif ap is not None and v is not None and not isinstance(v, bool):
            default = ap.get_default(k)
            if v != default and not isinstance(v, (list, dict)):
                out.append(f"{nombre}={v}")
    return sorted(out)


# Regla de COMBINACIÓN de facetas — declarativa (objective.yaml), no hardcodeada (#15). El default
# histórico es OR (≥1 faceta cualquiera), calibrado para el pool chico de la query directa; el
# citation chaining amplía el pool a "todo lo que el grafo conecta y menciona al sujeto", mucho más
# ruidoso, y ahí una faceta laxa deja de discriminar (medido: exigir la faceta del eje recorta 928→254).
# La palanca es la OBLIGATORIEDAD, no podar regex. Cada instancia declara cuáles de SUS facetas son
# load-bearing sin tocar el framework:
#   relevance.require:    [faceta, ...]  → AND: TODAS deben matchear
#   relevance.min_facets: N              → al menos N facetas cualesquiera (default 1)
# Sin nada declarado (require=[], min_facets=1) se recupera exactamente el comportamiento de hoy.
def combination_rule(rel: dict, topic_names) -> tuple[list[str], int]:
    """(require, min_facets) validados desde relevance. `require` debe ⊆ facets: una faceta
    obligatoria inexistente filtraría TODO a no-core en silencio → falla ruidoso."""
    # @inv INV-55
    raw_require = rel.get("require")
    # A diferencia de `extra_core`/`aliases`/`noise_doctypes`, ACÁ no conviene adivinar un solo
    # elemento: `require: rv` (escalar) truthy no caía en el `or []` y `list("rv")` lo desarmaba
    # CARÁCTER POR CARÁCTER (`['r','v']`) — el módulo abortaba igual (ninguna letra sola es una
    # faceta real) pero el RuntimeError de abajo culpaba a `['r', 'v']`, un valor que el usuario
    # nunca escribió (R4). `as_list` de un escalar da `[]`; si la forma cruda era truthy y el
    # resultado quedó vacío, es que no era una lista — se rechaza con el valor REAL, no sus letras.
    require = as_list(raw_require)
    if raw_require and not require:
        raise RuntimeError(
            f"vault/config/objective.yaml: relevance.require debe ser una lista — aunque sea de "
            f"un solo elemento, [{raw_require!r}] — no un escalar suelto: {raw_require!r}."
        )
    min_facets = rel.get("min_facets") or 1
    unknown = [t for t in require if t not in topic_names]
    if unknown:
        raise RuntimeError(
            f"vault/config/objective.yaml: relevance.require nombra facetas ausentes de "
            f"relevance.facets: {unknown}. Una faceta obligatoria que no existe filtraría TODO a "
            f"no-core en silencio."
        )
    return require, min_facets


def listify_curado(v, campo: str):
    """Normaliza un campo de CURACIÓN MANUAL (`extra_core`, `aliases`, `noise_doctypes`) que el
    framework instruye editar a mano en YAML. Un `campo: <valor>` sin corchetes es la forma natural
    de declarar UN solo elemento y es YAML válido — a diferencia de `cfg.as_list` (que trataría el
    escalar como forma inválida y lo degradaría a `[]`), acá conviene PRESERVAR la intención: la
    curación del usuario no se pierde por no poner corchetes (gemelo de R1/R13/R16 — perder un
    `extra_core`/alias/doctype escalar en silencio es justo el defecto que esto reemplaza). Reporta
    igual, para que la forma se corrija en origen."""
    if isinstance(v, list):
        return v
    if v:
        print_seguro(
            f"  ⚠ `{campo}` está escrito como escalar ({v!r}) en vez de lista — se toma como un "
            f"solo elemento; para declarar más de uno usá `{campo}: [{v!r}, ...]`."
        )
        return [v]
    return []


# ── D-49: la lente desincronizada, por ficha y OFFLINE ────────────────────────────────────────────
#
# ⚠ Vive en `lib_config` y NO en `query_ads` aunque la lente sea de éste: es lógica de **config y
# regex pura**, sin una sola llamada de red, y su consumidor es el **lint** — que corre offline y
# cuyo único requisito declarado es `pyyaml`. Cuando esto vivía en `query_ads`, importarlo arrastraba
# `requests` y el lint **fallaba en CI**, donde ese paquete no se instala: el chequeo que existe para
# no producir falsos limpios se volvía él mismo un falso rojo por una dependencia que no necesita.
# `busquedas[].lente` guarda la regla con la que se clasificó CADA corrida (#64). Cambiar una regex
# de `relevance.facets` mueve el corte core/no-core **sin mover `almagesto_version`**: el corpus ya
# ingestado queda clasificado con una lente que ya no es la vigente, y nada lo dice. `reclass_diff`
# ya medía ese delta, pero **necesita `build/<slug>/ads.json`** — scratch gitignored: en otra
# máquina, post-clone o después de limpiar, el chequeo no puede correr justo cuando más falta.
# De ahí el "offline": el insumo son las NOTAS, que sí viajan (título + abstract + `keywords`, D-17).
#
# ⚠ Alcance declarado — este diff evalúa la mitad TEXTUAL de la lente (`facets`/`require`/
# `min_facets`) y **no** `noise_doctypes`: la nota de paper no guarda `doctype`. No es una omisión
# que se pueda tapar con un default —"asumir no-ruido" inventaría entradas al core— así que cuando
# lo único que cambió son los doctypes de ruido el diff se declara **no evaluable** en vez de
# devolver un cero (D-43). En los demás casos el término del doctype es el MISMO de los dos lados
# de la comparación y se cancela.
# Dos lentes con nombres distintos porque son dos hechos distintos, y confundirlos es un mapa que
# atribuye mal: `lens_used` es la que ESTE proceso compiló y con la que de verdad clasificó (lo que
# el registro tiene que guardar: si el YAML se editó a mitad de corrida, guardar la de disco haría
# que el registro atribuyera a la corrida un filtro que no usó); `lens_current` es la VIGENTE en
# disco, releída, que es contra la que el lint compara. Coinciden salvo edición concurrente, y esa
# paridad la fija un test — no la prosa (red #3: un doble con distinto contrato que el real esconde
# el bug en la diferencia).
def lens_shape(rel: dict) -> dict:
    """Un `relevance:` → la forma canónica de `busquedas[].lente`. Punto único: si la corrida
    guardara una forma y el diff leyera otra, toda lente se vería 'cambiada' (o ninguna)."""
    facets = {name: str(pat) for name, pat in as_map(rel.get("facets")).items()}
    try:
        require, min_facets = combination_rule(rel, facets)
    except RuntimeError:
        # `require` nombrando una faceta inexistente aborta la CLASIFICACIÓN (con razón: filtraría
        # todo a no-core en silencio), pero acá sólo se está describiendo la regla para compararla.
        # Reventar dejaría al lint sin la categoría entera por una config que él mismo va a reportar.
        require, min_facets = as_list(rel.get("require")), (rel.get("min_facets") or 1)
    return {"facets": facets,
            "require": list(require),
            "min_facets": min_facets,
            "noise_doctypes": sorted(listify_curado(rel.get("noise_doctypes"), "relevance.noise_doctypes"))}


def lens_current() -> dict:
    """La lente VIGENTE en `objective.yaml`, **releída en cada llamada**. El lint corre en un
    proceso que importó `query_ads` antes de saber qué bóveda va a auditar: comparar contra las
    constantes del import haría que toda lente se viera igual a sí misma — el chequeo entero
    devolvería un cero que nadie midió."""
    return lens_shape(as_map(load_objective().get("relevance")))


def lens_stored(slug: str) -> dict | None:
    """La lente de la ÚLTIMA corrida del sujeto, o `None` si esa corrida no la guardó.

    Se mira la última y sólo la última: es la que dejó los `relevance:` que hay hoy en las notas.
    Heredar la lente de una corrida anterior le atribuiría a esta un filtro que no usó — un mapa
    que atribuye mal es peor que uno vacío. `None` ≠ `{}`: la ausencia es *no evaluado*, no
    'lente sin facetas'."""
    bs = load_busquedas(slug)
    lente = bs[-1].get("lente") if bs else None
    return lente if isinstance(lente, dict) else None


def lens_delta(stored: dict, current: dict) -> list[str]:
    """Qué cambió entre dos lentes, en prosa corta y determinista. Lista vacía = son la misma regla.

    `require` se compara como CONJUNTO (reordenarlo no cambia el corte: todas son obligatorias) y
    `facets` textualmente por regex (cambiar un patrón sí lo mueve). Devuelve la lista, no un bool,
    porque el reporte tiene que decir QUÉ cambió: 'la lente cambió' no es accionable."""
    delta = []
    fa, fb = as_map(stored.get("facets")), as_map(current.get("facets"))
    for name in sorted(set(fa) | set(fb)):
        if name not in fb:
            delta.append(f"faceta `{name}` eliminada")
        elif name not in fa:
            delta.append(f"faceta `{name}` nueva")
        elif fa[name] != fb[name]:
            delta.append(f"faceta `{name}`: regex cambiada")
    ra, rb = set(as_list(stored.get("require"))), set(as_list(current.get("require")))
    if ra != rb:
        delta.append(f"require {sorted(ra) or '[]'} → {sorted(rb) or '[]'}")
    ma, mb = stored.get("min_facets") or 1, current.get("min_facets") or 1
    if ma != mb:
        delta.append(f"min_facets {ma} → {mb}")
    da, db = set(as_list(stored.get("noise_doctypes"))), set(as_list(current.get("noise_doctypes")))
    if da != db:
        delta.append(f"noise_doctypes {sorted(da)} → {sorted(db)}")
    return delta


def lens_textual_changed(delta: list[str]) -> bool:
    """¿El delta toca la mitad que una nota PUEDE evaluar? Un cambio que sólo mueve
    `noise_doctypes` es real pero invisible offline (la nota no guarda `doctype`)."""
    return any(not d.startswith("noise_doctypes ") for d in delta)


def lens_core_text(lens: dict, text: str) -> bool:
    """¿`text` es core bajo `lens`, por la mitad TEXTUAL de la regla? Espeja la precedencia de
    `exclusion_reason` (sin tópico → require → min_facets) salteando el doctype, que no está en la
    nota. Compila las regex de la lente GUARDADA, que puede tener facetas que ya no existen."""
    facets = []
    for name, pat in as_map(lens.get("facets")).items():
        try:
            if re.search(pat, text, re.I):
                facets.append(name)
        except (re.error, TypeError):
            continue          # regex inválida en un registro viejo: no clasifica, no revienta
    if not facets:
        return False
    if any(t not in facets for t in as_list(lens.get("require"))):
        return False
    return len(facets) >= (lens.get("min_facets") or 1)


def note_lens_text(fm: dict, body: str) -> str:
    """El texto que la lente lee, reconstruido desde la NOTA — mismo insumo que `classify`:
    título + abstract + keywords, en minúsculas. El abstract vive en el cuerpo (`## Abstract`),
    no en el frontmatter, así que se recorta esa sección; `_(no disponible)_` es el marcador que
    `write_paper_notes` deja cuando ADS no lo devolvió y no es texto del paper."""
    m = re.search(r"^##\s+Abstract\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    abstract = (m.group(1).strip() if m else "")
    if abstract == "_(no disponible)_":
        abstract = ""
    return " ".join(filter(None, [
        " ".join(as_list(fm.get("title")) or ([fm["title"]] if fm.get("title") else [])),
        abstract,
        " ".join(str(k) for k in as_list(fm.get("keywords"))),
    ])).lower()


def notes_of_subject(slug: str) -> list:
    """Las notas de paper del sujeto, leyendo el frontmatter con el MISMO parser que el tooling
    (`split_fm`) y no por grep: `stars: [tau Cet]` en flow style y en bloque conviven en el mismo
    corpus, y el matcheo textual confunde `GJ 71` con `GJ 710`. Estrella → `stars`;
    tema → `thesis_links` (el concepto que `ingest_theme` siembra)."""
    try:
        name, _ = star_by_slug(slug)
        campo = "stars"
    except (KeyError, RuntimeError):
        try:
            _, tmeta = theme_by_slug(slug)
        except (KeyError, RuntimeError):
            return []
        name, campo = tmeta.get("concept"), "thesis_links"
    if not name:
        return []
    out = []
    for f in sorted(PAPERS.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        fm = split_fm(text)
        if name in as_list(fm.get(campo)):
            out.append((f.stem, fm, text))
    return out


def lens_diff_offline(slug: str) -> tuple[list[str], list[str], list[str]]:
    """Delta de re-clasificación **sin `build/`**: `(entran, salen, sin_nota)`.

    - `entran`: notas hoy `relevance: low` que la lente vigente haría core.
    - `salen`:  notas hoy `relevance: high` que la lente vigente dejaría fuera — menos las de
      `extra_core`, que son core por decisión del usuario y la regla no las toca (igual que el
      `via: manual` de `classify_record`).
    - `sin_nota`: bibcodes del universo acumulado del sujeto (`busquedas[].bibcodes`) que no tienen
      nota en disco. Es el **techo declarado** del chequeo, no un descarte: sin `--all`, el no-core
      no deja nota, así que `entran` sólo puede hablar de lo que alguien escribió. Publicarlo evita
      leer un `entran: 0` como 'no entra nada'.

    Se compara nota contra nota (`relevance` persistido vs lente vigente), no lente vieja contra
    lente nueva: el `relevance` del frontmatter ES lo que la bóveda afirma hoy, y es lo que el
    consumidor lee."""
    # @inv INV-58
    try:
        _, meta = star_by_slug(slug)
        extra = {str(e.get("bibcode") if isinstance(e, dict) else e)
                 for e in listify_curado(meta.get("extra_core"), "extra_core")}
    except (KeyError, RuntimeError):
        extra = set()
    lens = lens_current()
    entran, salen = [], []
    con_nota = set()
    for stem, fm, text in notes_of_subject(slug):
        con_nota.add((fm.get("bibcode") or stem))
        core_ahora = lens_core_text(lens, note_lens_text(fm, text))
        era_core = (fm.get("relevance") == "high")
        if core_ahora and not era_core:
            entran.append(stem)
        elif era_core and not core_ahora and (fm.get("bibcode") or stem) not in extra:
            salen.append(stem)
    universo: set = set()
    for b in load_busquedas(slug):
        universo.update(as_list(b.get("bibcodes")))
    return sorted(entran), sorted(salen), sorted(universo - con_nota)


def save_paso(slug: str, paso: str, flags=()) -> None:
    """Estampa un paso de la cadena en `cadena:` del registro.  @inv INV-91

    **R-6 (decidida con el usuario, 2026-08-24): cada script se estampa a sí mismo** al salir 0.
    La alternativa —estampar sólo desde `ingest_theme.run()`, un único punto de escritura— dejaba
    invisible el paso corrido a mano, y entonces el lint reportaba "se cortó en `fetch_pdf`" sobre
    un paso que **sí corrió**. Un falso positivo así erosiona la categoría entera: la primera vez
    que alguien la ve mentir, deja de mirarla.

    `via` sale de la variable de entorno que exporta el orquestador (`orquestador`) o vale
    `suelto`. Es la distinción que hace legible la traza: una cadena entera corrida de una vez se
    lee distinto de seis pasos sueltos a lo largo de una semana.

    **Idempotente (D-54):** si ya hay una entrada de ese paso con la misma fecha, los mismos flags
    y la misma vía, no se re-escribe — re-correr un paso el mismo día no debe generar ruido de
    diff. Lo que cambia sustantivamente (otros flags) sí entra."""
    data = load_registro(slug)
    data.setdefault("slug", slug)
    previos = [p for p in as_list(data.get("cadena")) if isinstance(p, dict)]
    entrada = {
        "paso": paso,
        "fecha": _dt.date.today().isoformat(),
        "version": ALMAGESTO_VERSION,
        "via": os.environ.get(VIA_ENV) or "suelto",
        "flags": list(flags) + [f"orquestador:{f}" for f in
                                (os.environ.get(FLAGS_ENV) or "").split() if f],
    }
    if any(p == entrada for p in previos):
        return                       # misma corrida, mismo día: sin ruido de diff
    data["cadena"] = previos + [entrada]
    save_registro(slug, data)


def cadena_cortada(slug: str, canonica=CADENA_ESTRELLA) -> str | None:
    """El primer paso de `canonica` que NO figura en el registro, o `None` si están todos.

    Nombra el paso, no cuenta pasos: "se cortó en `fetch_ground_truth`" es accionable y
    "faltan 4 pasos" no. Si el registro no tiene `cadena` en absoluto devuelve `None` — eso es
    "nunca se estampó" (sujeto anterior a D-57), no "se cortó en el primero"."""
    corridos = {p.get("paso") for p in load_cadena(slug)}
    if not corridos:
        return None
    return next((paso for paso in canonica if paso not in corridos), None)


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
    write_text_atomic(f, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))
