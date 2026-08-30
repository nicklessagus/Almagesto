"""Configuración compartida de los scripts de ingesta de la bóveda.

- Resuelve rutas del repo (sin asumir cwd).
- Lee el token ADS de vault/config/ads_dev_key o de la variable de entorno ADS_DEV_KEY.
- Carga vault/config/stars.yaml, vault/config/themes.yaml y vault/config/objective.yaml.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import os
import re
import unicodedata
import sys
from pathlib import Path

import yaml

# Versión del framework Almagesto — ÚNICA fuente de versión del repo (bump MANUAL + tag git
# `vX.Y.Z` al bumpear). La consumen: el frontmatter `generator` de cada nota que genera make_notes
# (provenance: con qué versión se armó la ficha) y los User-Agent de los fetchers (no hardcodear
# "Almagesto/x" en ningún otro lado — lo vigila un test). Semver: 1.0.0 = contrato estable
# (schema de frontmatter/config/cadena); un cambio que rompa ese contrato exige major bump.
ALMAGESTO_VERSION = "1.133.0"

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
MAILTO_FILE = CONFIG / "mailto"
# Registro de ingesta por sujeto (#51/#64): VERSIONADO (se commitea) porque guarda las dos cosas
# que `build/` no puede guardar. (a) `decisiones`: el juicio del triage —qué candidato del chaining
# se descartó y POR QUÉ—, que no es regenerable (un ads.json sí: se le vuelve a pedir a ADS; tu
# juicio sobre título+abstract, no). Vivía en build/<slug>/triage.json, gitignored: en otra máquina
# el triage re-proponía todo lo descartado, sin el motivo. (b) `busqueda`: el registro reproducible
# de la búsqueda (query efectiva, fecha, límites y conteos — los 16 ítems de PRISMA-S llevados a lo
# que esta cadena hace), que antes no se escribía en ningún lado: la query de una estrella se armaba
# en memoria y se tiraba. Simetría que faltaba: los candidatos ACEPTADOS ya persistían en config
# (`extra_core`), los rechazados no.
# #80 · por qué una fuente declarada todavía NO está en disco. Vocabulario CERRADO y validado:
# se escribía verbatim en la nota, así que un typo entraba mudo y el lint lo listaba como
# precondición legítima — la familia de `role` y de `via`.
# Los tres primeros describen un FALLO de adquisición o de extracción; `adquisicion` describe algo
# distinto y que antes entraba forzado como `paywall`: un libro que el usuario va a conseguir no
# falló, tiene otra latencia. Todos llevan MOTIVO libre obligatorio — mismo argumento que el
# `--reason` del triage: lo que sirve en seis meses es el motivo, no la categoría.
PENDING_OK = ("paywall", "scan", "unextractable", "adquisicion")

# #80 · CÓMO se apunta dentro de una fuente. Vocabulario CERRADO; default `linea`.
# Todo el contrato de `verify-citations` asume un `.txt` que un subagente lee ENTERO y del que
# devuelve cita textual + nº de línea. Un libro de 700 páginas revienta ese fan-out, y «línea 18443»
# no es una referencia utilizable: la unidad tiene que ser página o sección. Es un eje distinto del
# `txt:`/`pdf:` de #117 —aquél dice QUÉ ARCHIVO se leyó, éste CÓMO se apunta adentro— y hacen falta
# los dos: el `.txt` de un libro tampoco se cita por línea.
UNIDAD_CITA_OK = ("linea", "pagina", "seccion")

# #296 · DE QUÉ DOCUMENTO salió la lectura, y CÓMO se extrajo el índice. Vocabularios CERRADOS —la
# familia de `role`/`pending`/`unidad_cita`— y hasta ahora los únicos dos declarados cerrados en
# `CLAUDE.md` que nadie validaba. No es cosmético: `pdf_source: eprint` es una EXENCIÓN que apaga el
# chequeo de cita textual (#220/#275), así que un valor fuera de vocabulario cae por el `else` de
# todo `== "eprint"` en silencio, y un `eprint` mal escrito enciende un chequeo que iba a estar
# exento y produce hallazgos que no lo son. Medido sobre 138 notas: 85 `eprint`, 50 sin valor, 1
# `ads` y **2 con prosa dentro del campo** (una de ellas, información legítima de adquisición que
# terminó en el campo equivocado sin que nada lo dijera).
# ⚠ `null`/ausente es el valor legítimo para **desconocido**, que NO es «publicado» (#57).
PDF_SOURCE_OK = ("eprint", "ads", "publisher", "web")
FULLTEXT_SOURCE_OK = ("pdftotext", "ocr", "web")

# D-37 · en qué quedó una hipótesis. Vocabulario CERRADO: `status` es lo ÚNICO que un consumidor lee
# para decidir si se apoya en ella, y en prosa libre no dice nada (el caso medido en la instancia
# real: `supuesto operativo con caveat conocido`).
#
# ⚠ Vive acá, no en `lint.py`, desde #175: el GENERADOR (`make_notes.write_concept_note`) escribía
# `active` mientras el VALIDADOR tenía la lista, así que toda hipótesis nueva nacía con un
# bloqueante que la máquina se fabricaba sola. Con una sola declaración eso no se puede repetir.
HYP_STATUS = ("abierta", "sostenida", "disputada", "refutada")
HYP_STATUS_INICIAL = HYP_STATUS[0]      # una hipótesis recién planteada no está sostenida ni refutada

# #73 · qué TIPO de aporte es el paper. Chico y cerrado a propósito: el rol define QUÉ OPERACIÓN de
# contraste corresponde entre dos papers, y un valor libre no la determina.
ROLES = ("fundacional", "aplicacion", "arbitro")

REGISTRO = CONFIG / "registro"

# raw/ = fuentes inmutables (el LLM lee, no modifica) | wiki/ = el LLM escribe y mantiene
RAW = VAULT / "raw"
WIKI = VAULT / "wiki"
# build/ y outputs/ son scratch del tooling (gitignored, regenerable): viven en la raíz del
# repo, FUERA de vault/, para no contaminar la bóveda de Obsidian. Resolver vía cfg.ROOT.

PDFS = RAW / "pdfs"
FULLTEXT = RAW / "fulltext"
#: #311 · las EXTRACCIONES del fan-out. Viven en `raw/` —versionadas, viajan— y no en `build/`,
#: porque la regla de oro del scratch es «`build/` guarda lo REGENERABLE» y una extracción no lo es
#: en ese sentido: un `ads.json` se recupera con una llamada HTTP, una extracción cuesta volver a
#: leer el PDF con un LLM (medido: 33 extracciones ≈ 4,9 M tokens de subagente, 988 KB en disco, y
#: `git ls-files build/` devolvía 0 — o sea que no viajaban a ninguna otra máquina). Convive con
#: `fulltext/`, que también lo produce esta cadena y también es inmutable una vez escrito.
EXTRACCION = RAW / "extraccion"
GROUND_TRUTH = RAW / "ground_truth"

# Marcas de provenance en la PRIMERA línea de un .txt de fulltext/ — las escriben
# extract_fulltext (OCR) y fetch_web (snapshot); las lee make_notes para estampar
# `fulltext_source` en la nota (ocr|web; sin marca = pdftotext). Un solo lugar de verdad:
# si cambia el header, cambia acá.
FULLTEXT_OCR_MARK = "# Almagesto — fulltext por OCR"
# Primera línea de un .txt cuyas ECUACIONES se perdieron en la extracción (#113). Hermana de
# FULLTEXT_OCR_MARK: `make_notes` la lee para estampar `symbols_lost` en la nota del paper.
FULLTEXT_SYMBOLS_MARK = "# Almagesto — simbolos NO extraidos"
FULLTEXT_WEB_MARK = "# Almagesto — snapshot web"

# Marca que arXiv estampa en el margen de CADA página del PDF que sirve
# ("arXiv:2201.01234v3 [astro-ph.EP] 5 Jan 2022"; los IDs viejos son "astro-ph/0601123v2").
# Es la señal de DISCO de que el .txt salió del **eprint** y no de la versión publicada (#57):
# no depende de que el fetcher haya dejado registro, así que funciona retroactivamente sobre un
# corpus ya bajado. Importa porque `verify-citations` promete que la cita textual son "las palabras
# reales del paper" y un v1 pre-referato puede decir otra cosa que el publicado.
ARXIV_STAMP_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?",
                            re.I)
ARXIV_STAMP_SCAN_CHARS = 4000     # piso: la marca está en el margen, y `pdftotext` la ubica donde
ARXIV_STAMP_SCAN_PAGES = 2        # quiera dentro de la página — ver `arxiv_stamp`


def arxiv_stamp(text: str) -> str | None:
    """The eprint version ("v3", or "" when the stamp carries none) if `text` shows the arXiv stamp
    in its first pages; None otherwise.

    ⚠ AUD-164 / INV-29 — the scope is defined by **page**, not by a fixed character budget. The
    stamp sits in the side margin and `pdftotext` emits it wherever it falls inside that page's
    flow: a two-column paper's first page comfortably exceeds 4000 characters, and there the fixed
    cut left a **preprint** classified as `publisher` — which is exactly the distinction #57 exists
    to draw, because with `eprint` a numeric discrepancy is a candidate version difference rather
    than an error in the note.

    The scope is still bounded, on purpose: the stamp appears on **every** page, so two are plenty,
    and reading the whole paper would pick up the `arXiv:` ids of the bibliography — which belong
    to OTHER works and would turn any paper into an eprint. The 4000-character floor covers a
    `.txt` with no page breaks (a single-page OCR, a web snapshot)."""
    paginas = text.split("\f")[:ARXIV_STAMP_SCAN_PAGES]
    alcance = "\f".join(paginas)
    if len(alcance) < ARXIV_STAMP_SCAN_CHARS:
        alcance = text[:ARXIV_STAMP_SCAN_CHARS]
    m = ARXIV_STAMP_RE.search(alcance)
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
                        # #250 — la sección de indicadores es ESTAMPADA: sin esto `solo_prosa` no
                        # la descuenta, sus `[[links]]` cuentan como citas de prosa y contaminan el
                        # proxy de «planeta discutido» — el falso limpio permanente que el lint
                        # documenta para `## Planetas`.
                        "## Indicadores de actividad esperados",
                        "## Papers que tocan este tema (auto)", "## Excluidos por el filtro",
                        "## Verificación de citas",
                        # #124 · las ayudas de lectura de una nota de paper: el original de la
                        # fuente y su traducción. Ninguna es una afirmación de la bóveda, así que el
                        # fan-out no tiene qué contrastar. ⛔ La regla que las acompaña: **son ayuda
                        # de lectura, nunca fuente de la que citar** — si citás, citás del original
                        # con su página.
                        # ⚠ Las traducciones se llaman `## Traducción …` y NO `## Abstract (es)`:
                        # ese nombre volvía a `## Abstract` un **prefijo** del suyo, y
                        # `section_start` tolera a propósito un sufijo que arranca con puntuación
                        # (lo necesita para `## Vista — X (2026-08-27)`). Medido el 2026-08-28: con
                        # sólo la traducción presente, el guard del verbatim la daba por el original
                        # y no lo estampaba **nunca** — dejando a `note_lens_text` sin abstract para
                        # siempre. Es la trampa de prefijo de #176, instanciada en el vocabulario
                        # propio del framework; se saca renombrando, no aflojando el cortador.
                        # ⚠ Los nombres van COMPLETOS (#214): con `## Traducción` pelado, el
                        # sufijo del encabezado real (« del abstract») empieza con letra y la regla
                        # de sufijo de INV-98 lo rechaza — así que las traducciones NO quedaban
                        # exentas en `_es_estampada`, mientras el `startswith` pelado de
                        # `lib_blocks` (la regla vieja) sí las eximía. Dos copias de la misma regla
                        # con semánticas opuestas: cada consumidor veía un conjunto distinto de
                        # secciones estampadas, que es exactamente el bug de la regla de método nº2.
                        "## Abstract", "## Conclusiones",
                        "## Traducción del abstract", "## Traducción de las conclusiones")


def _es_estampada(linea: str) -> bool:
    """¿Este encabezado es de una sección que estampa la máquina?

    ⛔ **Misma regla de sufijo que `section_start`, no un `startswith` pelado.** Ésta era una copia
    con la regla vieja: `## Papers` es prefijo de `## Papers relevantes para el método`, así que una
    sección PROPIA con ese nombre se saltaba entera. Medido el 2026-08-28: la nota perdía toda su
    prosa, lo que (a) apagaba en silencio el gate R-1 —`unverified` mira si hay citas en prosa— y
    (b) además reportaba algo **falso**: *«concepto sin citas `[[bibcode]]`»* sobre una nota que sí
    las tiene. Es la trampa de #176, que se arregló dentro de `section_start` y no llegó acá.

    Un sufijo es puntuación, nunca más palabras: `## Papers (25 · 16 sintetizados)` sí,
    `## Papers relevantes…` no.
    """
    #  @inv INV-98
    for h in SECCIONES_ESTAMPADAS:
        if linea.startswith(h):
            resto = linea[len(h):].strip()
            if not resto or not resto[0].isalnum():
                return True
    return False


# ── INV-63 · el schema de cada tipo de nota, declarado UNA vez ────────────────────────────────────
#
# Hasta 1.74.0 el schema vivía en la prosa de `CLAUDE.md` y se chequeaba campo por campo, ad-hoc:
# no había forma de preguntar «¿esta nota cumple el schema de su tipo?», que es la mitad del P0 que
# faltaba (la otra —la forma que EVADE los chequeos— ya bloquea vía `fm_broken`).
#
# ⚠ Lo que se exige es que la CLAVE esté, no que tenga valor. Un `null` es el caso normal y a
# propósito: el espejo #70 deja en `null` lo que la autoridad no trae, y rellenarlo con literatura
# está prohibido. Exigir valor convertiría el chequeo en lo contrario de lo que el contrato manda.
#
# La lista es exactamente la que ESCRIBEN los writers de `make_notes`, no una copia de la prosa: así
# el enunciado «toda nota generada lo cumple» es verdadero por construcción y lo que el detector
# encuentra son notas anteriores al campo, que es deuda real. Backlog, no bloqueante (decidido con
# el usuario, 2026-08-28): el corpus viejo tiene notas incompletas por diseño y un bloqueante nace
# en rojo sobre trabajo correcto — el falso positivo que erosiona la categoría entera.
#: #124/#277 · lo que va en `## Abstract` cuando el catálogo no devolvió ninguno. La sección es
#: OBLIGATORIA aunque el contenido falte: es la capa auditable del cuerpo, y su ausencia y su vacío
#: se arreglan distinto (una nota sin la sección no se puede re-clasificar offline; una con el
#: placeholder está esperando que el cosechador la complete desde el PDF).
#: #205/#269 · dónde se apunta un valor. Vive una sola vez porque la escriben DOS artefactos —el
#: prompt de extracción y la plantilla de la vista que se estampa en la nota— y divergieron: el
#: stub siguió mandando citar por nº de línea del `.txt` durante 40 versiones después de que #205
#: hiciera del PDF la fuente, publicando dentro del vault la doctrina retirada.
REGLA_LOCALIZADOR = (
    "el **localizador** es la **página** del PDF (`p. 7`); `L1234` sólo en fuente web o documento "
    "largo (#80/#200), y `Fig. N, p. M` en lectura de gráfico (#195). El `grep -n` sobre el `.txt` "
    "sirve para **ubicar** dónde mirar, no para citar")

ABSTRACT_PLACEHOLDER = "_(no disponible)_"

SCHEMA_NOTA = {
    # #272 — `mass_msun` es el campo con más consecuencias aguas abajo después de `planets[]`:
    # m·sini ∝ M★^(2/3), así que el rango 0,699–0,78 M☉ que la literatura publica mueve cada masa
    # mínima un 7,6 %. NEA ya lo arbitra (`_autoridad.mass_msun`), y sin lugar en el frontmatter la
    # ficha declaraba un HUECO de arbitraje sobre un campo para el que su propia autoridad tiene
    # valor. Rige el espejo puro (#70): lo copia el script, `null` si NEA calla, y no se rellena con
    # literatura. `Vmag`/`ra_deg`/`dec_deg` NO entran: no cambian ninguna lectura de una señal RV.
    "star": ("name", "slug", "aliases", "simbad_id", "spectral_type", "dist_pc", "mass_msun",
             "activity_indicators_expected", "planets", "disputes", "data_local",
             "methods_applied", "tags"),
    "paper": ("bibcode", "title", "first_author", "n_authors", "year", "arxiv_id", "doi",
              "bibstem", "stars", "facets", "keywords", "methods", "thesis_links", "role",
              "relevance", "citation_count", "pdf", "fulltext", "fulltext_source", "pdf_source",
              "tags"),
    "concept": ("name", "aliases", "disputes", "tags"),
    "hypothesis": ("name", "status", "tags"),
}


def missing_schema_fields(tipo: str, fm: dict) -> list:
    """Keys that `tipo`'s schema declares and this note does not carry.  @inv INV-63

    Presence, not value: see the comment on `SCHEMA_NOTA`. An unknown type returns `[]` — there is
    no schema to measure it against, and inventing one would be worse than not checking."""
    return [k for k in SCHEMA_NOTA.get(tipo, ()) if k not in fm]


def table_shape_issues(body: str) -> list:
    """Table rows whose cell count does not match their header's (#227). `[(line_no, got, want)]`.

    ⛔ **The artefact is what travels.** A row with more cells than its header does not render —
    GFM drops the excess— so the content is lost *in the reader's view* while still being there
    for every tool that parses the file. Measured on a real note: two rows of `## Régimen de
    validez` fused into one physical line (10 pipes in a 4-column table), so an entire claim —its
    only precondition on calibrating PCA against synthetic data— became invisible… and it was a
    **verified pair**: the note certified as checked a claim its own artefact does not show.

    Nothing looked at this. The lint parsed table cells in exactly two places, both counting
    content, never shape; `verify-citations` checked the fused row's text without noticing the row
    does not render.

    Line numbers are 1-based over the WHOLE file, the `grep -n` convention of this repo (#29).
    """
    out, header, sep = [], None, False
    for i, raw in enumerate(body.split("\n"), 1):
        ln = raw.strip()
        if not ln.startswith("|"):
            header, sep = None, False
            continue
        n = _n_cells(ln)
        if header is None:
            header, sep = n, False
            continue
        if not sep:                     # la línea de separación `|---|---|`
            sep = True
            continue
        if n != header:
            out.append((i, n, header))
    return out


def _n_cells(row: str) -> int:
    """Cells of a markdown table row, honouring the escaped pipe (INV-99).

    Splitting on a bare `|` is the bug INV-99 already paid for once: a cell that legitimately
    carries an escaped pipe —a quotation that includes a table row of the paper— would be counted
    as two, and this detector would report every such row as malformed."""
    cuerpo = row.strip().strip("|")
    return len(re.split(r"(?<!\\)\|", cuerpo))


def headings_glued_to_table(body: str) -> list:
    """`## ` headings with no blank line after a table row: `[(line_no, heading)]` (#260).

    Sibling of `table_shape_issues`, same doctrine —**the artefact is what travels**— and a
    different mechanism. GFM (markdown-it, what Obsidian is closest to) breaks the table at the
    heading and renders both correctly, so this is invisible where the vault is normally read.
    Python-Markdown + `tables` —MkDocs and much of the static-export chain— does NOT: the `## …`
    line becomes **one more row of the table above**, and the heading vanishes from the outline.

    Measured on a real star note: 3 of its 8 `##` disappeared that way, and with them the very
    metadata this framework added so a roll-up cannot under-declare its universe in silence — the
    `49 · 28 sintetizados` D-10 mandates, the method count, and the four INV-81 counts in the
    verification block's header.

    Backlog and not blocking, deliberately: unlike a fused row, GFM does not drop anything here, so
    the damage is renderer-dependent. The producer was `_reemplazar_seccion`, fixed in the same
    change; this is the net that keeps a third splice site from re-introducing it.

    Only a **table row** counts as the previous line. A heading right after a paragraph or a code
    fence is ugly and parses as a heading everywhere, so reporting it would be noise — and a
    high-signal category that cries wolf stops being read.

    Line numbers are 1-based over the WHOLE file, the `grep -n` convention of this repo (#29).
    """
    out, lines = [], body.split("\n")
    for i, raw in enumerate(lines):
        if i == 0 or not raw.startswith("## "):
            continue
        prev = lines[i - 1].strip()
        if prev.startswith("|") and prev.endswith("|"):
            out.append((i + 1, raw.strip()))
    return out


_ESCAPADO_RE = re.compile(r"\\+[`$]")


def _drop_escaped(texto: str) -> str:
    """Text with markdown-ESCAPED markers removed, so they neither open nor close (#309).

    ⛔ Fourth time this repo pays for the same blindness (#168 the markdown ornament, #276 the
    `inferencia` mark under emphasis, #283 `condition_kind` against `**contextualiza**`, this one).
    An escaped dollar is the CORRECT fix for a literal one —Obsidian renders it and does not open
    math— and
    the detector kept reporting it, so the operator's options were a real rendering bug, a
    permanent backlog entry, or deleting the character from a verbatim transcription. The framework
    ASKS for verbatim transcriptions (`## Abstract`, textual quotes, artefact caveats), so a price,
    a `$PATH` or a currency was going to collide sooner or later. An even number of backslashes
    escapes the backslash, not the marker, so only the odd case is dropped."""
    return _ESCAPADO_RE.sub(lambda m: "" if len(m.group(0)) % 2 == 0 else m.group(0)[:-2] + m.group(0)[-1],
                            texto)


def unclosed_markers(body: str) -> list:
    """Inline markers left open in a paragraph: `[(line_no, marker, line_no del impar)]` (#227).

    Backtick and `$…$` are the two that swallow the rest of the note when left open. Measured: a
    `` ` `` opened on line 104 whose next backtick was on line **372** — 268 lines inside an
    inline-code that never closes, produced by a spliced edit and invisible to every check.

    ⛔ Counted per **paragraph** (contiguous non-empty lines), never per line: notes here are
    hard-wrapped at ~100 columns, so a formula or an inline-code legitimately straddles a line
    break. Per-line counting fires in false on every wrapped `$…$` — measured, 5 false positives
    on the first note tried — and a high-signal category that cries wolf is one that stops being
    read. Fenced code blocks are skipped whole.

    Line numbers are 1-based over the WHOLE file, the `grep -n` convention of this repo (#29).
    """
    out, fenced, ini, acc = [], False, 0, []

    def cerrar():
        """Close the paragraph being accumulated and report the markers left open in it.

        #309 — reports TWO line numbers: the paragraph that stays open and the line where the count
        turns odd. With six-bullet paragraphs, sending the operator to the paragraph's first line is
        making them hand-search what the detector already knows."""
        if not acc:
            return
        for marca in ("`", "$"):
            # `$$` de bloque va en línea propia y no abre inline; `\$` está escapado y no abre (#309)
            def _n(t):
                limpio = _drop_escaped(t)
                return (limpio.replace("$$", "") if marca == "$" else limpio).count(marca)
            if sum(_n(t) for t in acc) % 2 == 0:
                continue
            impar, corridos = ini, 0
            for offset, t in enumerate(acc):
                corridos += _n(t)
                if corridos % 2:
                    impar = ini + offset
                    break
            out.append((ini, marca, impar))

    for i, raw in enumerate(body.split("\n"), 1):
        ln = raw.strip()
        if ln.startswith("```"):
            cerrar(); acc = []
            fenced = not fenced
            continue
        if fenced:
            continue
        if not ln:
            cerrar(); acc = []
            continue
        if not acc:
            ini = i
        acc.append(ln)
    cerrar()
    return out


def duplicate_paragraphs(body: str) -> list:
    """Paragraphs that appear more than once in the same note: `[(line_no, first_line)]` (#227).

    A spliced edit duplicates a paragraph and nothing notices: measured, one repeated verbatim
    eleven lines apart, with two different endings, and between the two copies the introductory
    paragraph of a DIFFERENT section — which left that section published with no prose at all.

    Only paragraphs long enough to identify themselves (`_DUP_MIN`): a short line repeated is
    normal (a table separator, a `—`, a heading-like bullet), and reporting those would drown the
    real case. Fenced blocks and stamped sections are skipped: a roll-up legitimately repeats.
    """
    vistos, out, fenced, ini, acc, saltando = {}, [], False, 0, [], False

    def cerrar():
        """Close the paragraph being accumulated and check whether its opening was already seen."""
        if not acc or saltando:
            return
        texto = " ".join(acc)
        if len(texto) < _DUP_MIN:
            return
        # ⛔ Se compara el ARRANQUE, no el texto entero: el caso medido es un párrafo duplicado por
        # un empalme **con dos finales distintos**, y exigir igualdad exacta lo pierde justo donde
        # la edición fallida es más probable. Es el mismo criterio con que #216 compara abstracts.
        clave = texto[:_DUP_CLAVE]
        if clave in vistos:
            out.append((ini, acc[0][:70]))
        else:
            vistos[clave] = ini

    for i, raw in enumerate(body.split("\n"), 1):
        ln = raw.strip()
        if ln.startswith("```"):
            cerrar(); acc = []
            fenced = not fenced
            continue
        if fenced:
            continue
        if ln.startswith("## "):
            cerrar(); acc = []
            saltando = is_stamped_section(ln)
            continue
        if not ln:
            cerrar(); acc = []
            continue
        if not acc:
            ini = i
        acc.append(ln)
    cerrar()
    return out


#: Largo mínimo (normalizado) para que un párrafo repetido cuente como duplicado. Por debajo, la
#: repetición es normal —un `—`, un bullet corto, una celda— y reportarla ahogaría el caso real.
_DUP_MIN = 120
#: Cuántos caracteres del arranque identifican al párrafo. Ver el comentario de arriba: un empalme
#: duplica el párrafo y suele dejarle otro final, así que la igualdad exacta no lo ve.
_DUP_CLAVE = 100


#: #234 · señales de que una salvedad en prosa está haciendo una afirmación DECIDIBLE sobre un
#: archivo — o sea, una que `SALVEDAD_TIPOS` podría chequear con un `grep` o un `pdfinfo` en vez de
#: dejarla como juicio. Heurística de alta señal, como el detector de fuga: cada hit se mira a mano.
_SALVEDAD_DECIDIBLE = re.compile(
    r"(?:`?\.txt`?|pdftotext).{0,80}?(?:no (?:lo |los |la |las )?(?:contiene|trae|tiene)|pierde|"
    r"perdi[óo]|falta|renderiza)|(?:tiene|son|de)\s+\d+\s+p[áa]ginas", re.I)


#: #236 · largo hasta el cual un token alfabético de una faceta necesita frontera de palabra. Por
#: encima, la probabilidad de que caiga dentro de otra palabra es despreciable; por debajo es alta y
#: está medida (`expres` → *Venus Express*, `neid` → *Schneider*).
FACETA_TOKEN_CORTO = 8


def facet_tokens_without_boundary(patron: str) -> list:
    """Alternatives of a facet regex that are short, alphabetic and carry **no word boundary** (#236).

    A facet is a regex over title + abstract + keywords, so a short acronym without `\b` matches
    **inside** another word. Measured on a real vault's `rv` axis-facet: `expres` (for the EXPRES
    spectrograph) matched **21** records via `expressed`, `expressions`, *Venus **Expres**s* and
    *Mars **Expres**s*; `neid` matched the surname `Sch**neid**er`. **19 of the 193 records with
    that facet had it only through those**, and since the vault declared `require: [rv]`, that
    facet was the only gate: **4 of 32 live papers were core by accident**.

    ⛔ Why this needs a detector and not just care: a facet's **false positive leaves no trace** —
    the paper enters, is downloaded, read and synthesised. It is the mirror of the false negative
    the contract already warns about (*what the lens discards is never downloaded, so it leaves no
    trace*), and only one of the two had a net (`propose_facets`).

    Returns the offending alternatives, in order. Case and the `(?i)` flag are irrelevant here."""
    fuera = []
    for alt in re.split(r"(?<!\\)\|", str(patron or "")):
        t = alt.strip()
        if not t or len(t) > FACETA_TOKEN_CORTO:
            continue
        if not t.replace(" ", "").isalpha():        # tiene dígitos, clases o metacaracteres
            continue
        if "\\b" in alt or "\\B" in alt:
            continue
        fuera.append(t)
    return fuera


def reuse_note(bibcode: str, origen) -> str:
    """The D-18 reuse line, saying WHAT WAS NOT CHECKED about the artefact it imports (#297).

    `↺ … copiado sin ir a la red` reads as *"we saved a download"*, and what also happened is
    *"a subject just inherited an artefact whose age nobody checked"*. The framework HAS the
    version detector (`sweep_external`, one of the six expiries) and the ingest chain does not run
    it, which is coherent — the chain only checks the subject at hand — except that the moment of
    reuse is exactly when an old artefact enters a new subject. And the answer one would expect
    («if there were a newer version the search would have returned ANOTHER bibcode, and D-19 joins
    them») is false in the frequent case: the preprint's DOI identifies the *deposit*, so #216
    **guarantees** preprint and published never collide. Measured on a real vault: 85 of 138 notes
    are `pdf_source: eprint` (62 %) and `_red.yaml` did not exist — the network pass had never run.

    So the line declares the two facts the operator needs and stops there (INV-87: what was NOT
    looked at is stated). It does not go to the network: the reuse must stay cheap."""
    fecha = ""
    try:
        fecha = _dt.date.fromtimestamp(Path(origen).stat().st_mtime).isoformat()
    except (OSError, ValueError, TypeError):
        pass
    nota = PAPERS / f"{bibcode}.md"
    src = None
    if nota.exists():
        try:
            src = split_fm(nota.read_text(encoding="utf-8")).get("pdf_source")
        except OSError:
            src = None
    detalle = ", ".join(filter(None, [f"en disco desde {fecha}" if fecha else "",
                                      f"pdf_source: {src}" if src else "pdf_source: no consta"]))
    return (f"  ↺ {bibcode}: ya estaba bajo `{Path(origen).parent.name}` — copiado sin ir "
            f"a la red (D-18; {detalle}) — no se chequeó si hay versión publicada")


def facet_alternatives(patron: str) -> list:
    """A facet regex → its **level-0** alternatives, groups kept whole (#291).

    ⚠ This is NOT `patron.split("|")`, and the difference is measured. A naive split cuts INSIDE
    groups: with it, `line-by-line` shows up twice — it lives in two different `(...)` groups — and
    reads as a duplicate; deduping on that breaks `(telluric|line-by-line|stellar activity)` and
    the reclassification diff comes out **−1** (one real paper leaves the core). A check that
    exists to look after the lens cannot be the thing that breaks it.

    ⚠ It is deliberately NOT shared with `facet_tokens_without_boundary`, whose naive split is
    correct for ITS question: a short token without `\b` leaks whether or not it sits inside a
    group, so that detector wants the inner alternatives too. Same string, two questions."""
    fuera, actual, depth, in_class, esc = [], [], 0, False, False
    for ch in str(patron or ""):
        if esc:
            actual.append(ch)
            esc = False
            continue
        if ch == "\\":
            actual.append(ch)
            esc = True
            continue
        if in_class:
            actual.append(ch)
            if ch == "]":
                in_class = False
            continue
        if ch == "[":
            in_class = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "|" and depth == 0:
            fuera.append("".join(actual))
            actual = []
            continue
        actual.append(ch)
    fuera.append("".join(actual))
    return [a for a in (x.strip() for x in fuera) if a]


def facet_dead_alternatives(patron: str, textos) -> list:
    """Alternatives of a facet that match **nothing** in `textos` (#291), as `(alternativa, motivo)`.

    #236 built the machinery to audit a facet alternative by alternative and covered ONE direction
    —the alternative that matches too much—, leaving open the quieter one: **the alternative that
    matches nothing**. A dead alternative is never seen. The facet still compiles, the cut still
    prints a plausible number, the registry stores the lens as current, and the term simply does
    not participate — indistinguishable from "that term does not appear in the literature".

    Measured on a real theme: `non-?gaussianity matrix` (almost certainly a lost `|`) required the
    literal phrase, which **0** files hold, while 29 hold `non-gaussianity` — so non-Gaussianity,
    one of the two or three terms that DEFINE the theme and a declared alias of it, never
    classified anybody, and no net said so.

    The caller must declare the population: over 0 notes this is **not evaluable**, not "all dead"
    (D-43). An alternative that does not compile on its own is reported as such rather than
    silently skipped — a `(0)` nobody measured reads as a verdict."""
    fuera = []
    for alt in facet_alternatives(patron):
        try:
            rx = re.compile(alt, re.I)
        except re.error as exc:
            fuera.append((alt, f"no compila por separado ({exc}) — no se pudo evaluar"))
            continue
        if not any(rx.search(str(t or "")) for t in textos):
            fuera.append((alt, "no matchea NINGUNA nota del sujeto"))
    return fuera


def facet_duplicated_alternatives(patron: str) -> list:
    """Alternatives repeated verbatim within the same facet (#291). Harmless, and the cheap signal
    that the chain was hand-edited blind — which is how the dead alternative above got there."""
    vistos, repetidas = set(), []
    for alt in facet_alternatives(patron):
        clave = alt.casefold()
        if clave in vistos and alt not in repetidas:
            repetidas.append(alt)
        vistos.add(clave)
    return repetidas


def facet_token_leaks(token: str, textos) -> list:
    """The distinct WORDS a short facet token matched inside, over an already-downloaded corpus (#236).

    The token alone is a suspicion; this turns it into evidence. Without it the operator reads
    `«rv»` in a probe and cannot know it was `Schneider`. Returns at most `_LEAK_MAX` examples,
    which is enough to recognise the leak and short enough to fit one report line."""
    rx = re.compile(r"\w*" + re.escape(token) + r"\w*", re.I)
    fuera, vistos = [], set()
    for t in textos:
        for m in rx.finditer(str(t or "")):
            palabra = m.group(0)
            if palabra.lower() == token.lower():
                continue                       # matcheó la palabra entera: es el uso legítimo
            if palabra.lower() not in vistos:
                vistos.add(palabra.lower())
                fuera.append(palabra)
                if len(fuera) >= _LEAK_MAX:
                    return fuera
    return fuera


#: Cuántas palabras-ejemplo alcanzan para reconocer una fuga de faceta sin inflar el reporte.
_LEAK_MAX = 4


#: #220 · largo mínimo de una cita textual para chequearla contra su fuente. Por debajo, una
#: coincidencia no dice nada (una frase de cinco palabras aparece en cualquier paper del tema) y el
#: ruido de falsos positivos por markup se come la señal.
QUOTE_MIN = 40

#: Fragmento mínimo tras partir por elipsis: la cita cortada («A … B») se chequea por partes, y una
#: parte muy corta no es evidencia de nada.
QUOTE_FRAG_MIN = 25

_QUOTE_RE = re.compile(r"«([^»]+)»")
_QUOTE_MARKUP_RE = re.compile(r"\$[^$]*\$|\[\[|\]\]|[*_`\\]")
_QUOTE_ELLIPSIS_RE = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]|…|\.\.\.")
_QUOTE_SUBS = (("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'"),
               ("\u2013", "-"), ("\u2014", "-"), ("\u00ad", ""))


def normalize_quote(s: str) -> str:
    """A quoted string reduced to what can be compared against a `.txt`.

    The normalization is deliberately minimal and DECLARED (#220): inline math and markdown markup
    are dropped —the note necessarily re-marked the quote up, so `$A$` would never match the source
    verbatim—, typographic quotes and dashes are unified, soft hyphens go, whitespace collapses and
    case is folded. Anything beyond that would start matching text the source does not have.
    """
    s = _QUOTE_MARKUP_RE.sub("", s)
    for a, b in _QUOTE_SUBS:
        s = s.replace(a, b)
    # #275 — el guión se borra de los DOS lados. `normalize_source_text` ya unió el corte de línea
    # (`inde-\npendent` → `independent`), así que el `-` que queda es el de `p-mode`, que el `.txt`
    # puede traer partido (`p-\nmode` → `pmode`) o entero. Sin esto, toda cita con un guión real
    # fallaba contra una fuente donde ese guión cayó en un fin de línea. ⛔ El orden importa: borrar
    # el `-` ANTES del join daría `p mode` y el defecto se invierte.
    s = s.replace("-", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def normalize_source_text(t: str) -> str:
    """The same normalization on the source side, plus the hyphen that `pdftotext` leaves at a line
    break (`inde-\npendent`): without joining it, every quote crossing a line break would fail."""
    return normalize_quote(t.replace("-\n", ""))


def quote_fragments(quote: str) -> list[str]:
    """The pieces of a quote that can be looked up, split at the ellipsis that marks an elision.

    A quote written «A … B» does not appear verbatim anywhere: what the source has is A and B, with
    something in between. Checking the pieces is what makes the elided quote decidable at all;
    pieces below `QUOTE_FRAG_MIN` are dropped, since a short one matches anything.
    """
    return [f for f in (x.strip() for x in _QUOTE_ELLIPSIS_RE.split(quote))
            if len(f) >= QUOTE_FRAG_MIN]


def quotes_in(text: str) -> list[str]:
    """The «…» quotes of a block that are long enough to be worth checking (`QUOTE_MIN`)."""
    return [q.strip() for q in _QUOTE_RE.findall(text) if len(q.strip()) >= QUOTE_MIN]


#: #46/#275 · la canaleta: el hueco de espacios que separa dos columnas en un `.txt` de
#: `pdftotext -layout`. Se DEFINE una vez acá; `measure_layout` la **detecta** (con `\S…\S`, que
#: exige contenido a los lados) y `deinterleave_columns` **parte** por ella. Lo que no puede pasar
#: es que difieran en qué cuenta como canaleta — lo fija un test de paridad (regla de método 2).
CANALETA_MIN = 8
GUTTER = re.compile(rf"\S {{{CANALETA_MIN},}}\S")
_GUTTER_SPLIT = re.compile(rf" {{{CANALETA_MIN},}}")


def deinterleave_columns(t: str) -> list:
    """The physical COLUMNS of a `pdftotext -layout` `.txt`, one string per column index (#275).

    `-layout` keeps the physical page: in a two-column paper every line carries column 1, a run of
    spaces (the gutter) and column 2, so the flat text **interleaves** them and no quote longer than
    one physical line can be found. Segment `i` of every line feeds stream `i`, joined with `\n` so
    the end-of-line hyphen still joins inside its own column. A single-column file yields exactly
    one stream, identical to the flat text.

    ⛔ The flat text is NOT searched as a fallback: it contains the column-1→column-2 splice, so a
    quote nobody ever wrote would pass as verbatim (pinned since #46)."""
    columnas: list = []
    for linea in str(t or "").split("\n"):
        for i, seg in enumerate(_GUTTER_SPLIT.split(linea)):
            while len(columnas) <= i:
                columnas.append([])
            columnas[i].append(seg.rstrip())
    return ["\n".join(c) for c in columnas]


def source_texts(raw: str) -> list:
    """Every normalized reading of a `.txt` a quote may legitimately live in (#275).

    One per physical column, deduplicated. A single-column source gives exactly one, so the caller
    does not branch on layout — which is the point: whether the `.txt` is interleaved is a property
    of the PDF nobody declared anywhere."""
    vistos, out = set(), []
    for col in deinterleave_columns(raw):
        norm = normalize_source_text(col)
        if norm and norm not in vistos:
            vistos.add(norm)
            out.append(norm)
    return out


#: #287 · las DOS lecturas de una cita con matemática en el medio. `normalize_quote` **borra** el
#: span `$…$` —correcto cuando la nota re-marcó una fórmula que el `.txt` no puede tener igual—,
#: pero eso convierte «of either $A$ and $S$» en «of either and», que no está en ninguna fuente
#: aunque el paper diga exactamente esa frase con las letras sueltas. Medido al desactivar la
#: exención de #275 sobre una bóveda real: falsos positivos en masa, sobre citas correctas.
_MATH_DELIMS = re.compile(r"\$([^$\n]*)\$")


def quote_variants(quote: str) -> list:
    """The normalized readings of a quote a source may legitimately contain (#287).

    Two, and both are conservative: the math span **dropped** (the note re-marked a formula the
    `.txt` cannot carry) and the math span **unwrapped** (`$A$` → `A`, which is exactly how a plain
    letter appears in the extracted text). A quote counts as found if **either** reading is there —
    the words still have to be in the source; what changes is which of the two markups of the same
    words we compare against."""
    directa = normalize_quote(quote)
    sin_delim = normalize_quote(_MATH_DELIMS.sub(r"\1", str(quote or "")))
    return [directa] if sin_delim == directa else [directa, sin_delim]


#: #288 · tokens que la EXTRACCIÓN mete en medio de la prosa y el paper no tiene: números de línea
#: de un preprint A&A, marcas de columna, coordenadas. Sirven para **clasificar** un hallazgo que ya
#: falló, nunca para aceptarlo.
_TOKEN_RUIDO = re.compile(r"(?<![a-z])\d+(?:[.,]\d+)?(?![a-z])")


def quote_found_degraded(quote: str, source_norm: str) -> bool:
    """Would this quote be in that source if the extraction had not degraded it? (#288)

    ⛔ **This never makes a finding pass.** It only tells apart two things that need opposite work:
    a note that misquotes its source (fix the note) and a `.txt` whose extraction dropped the quote
    apart — line numbers of a two-column preprint injected mid-sentence, a neighbouring column
    spliced in. Measured on a real vault: of five findings opened one by one, **four** were the
    artefact and only one was the note.

    The comparison drops standalone numeric tokens from BOTH sides, which is exactly what would make
    a wrong number match — hence it may never accept, only classify, and the message it produces
    sends the reader to the PDF."""
    limpio = _TOKEN_RUIDO.sub(" ", source_norm)
    for variante in quote_variants(quote):
        frags = quote_fragments(_TOKEN_RUIDO.sub(" ", variante))
        if frags and all(re.sub(r"\s+", " ", f).strip() in re.sub(r"\s+", " ", limpio)
                         for f in frags):
            return True
    return False


#: #320 · caché de `extraction_texts`, por bibcode. Misma asimetría que #275 arregló en
#: `_source_readings`: el chequeo corre **por cita**, así que sin caché el mismo JSON de ~25 KB se
#: leía, recorría y normalizaba decenas de veces en la pasada que `CLAUDE.md` describe como barata.
#: ⚠ La clave incluye el DIRECTORIO, no sólo el bibcode: `EXTRACCION` se re-apunta (los tests lo
#: hacen por fixture), y una caché por bibcode pelado devolvería la extracción de otra bóveda.
_EXTRACCION_CACHE: dict = {}


def extraction_texts(bibcode: str) -> list:
    """Every textual field of this paper's EXTRACTIONS, normalised for quote lookup (#315/#317).

    ⛔ The decisive comparison nobody was making. #220 tests a note's verbatim quote against the
    `.txt`, which #205 declares a degraded index — so the check reports the degradation of the
    `.txt` as if it were a defect of the note: measured, **2 of 17** real findings in one concept
    and **0 of 35** in another. The extraction JSON, on the other hand, is the transcription made
    **while reading the PDF**, so comparing against it makes *"the synthesiser invented this quote"*
    decidable offline and without opening the PDF: if the quote is not in any extraction of its
    bibcode, no degraded-artefact excuse applies.

    Returns the normalised readings (same shape `quote_found` expects), one per JSON on disk.
    Memoised per bibcode (#320): the check runs per QUOTE, and this is the only disk read left
    uncached on that hot path."""
    clave = (str(EXTRACCION), bibcode)
    if clave in _EXTRACCION_CACHE:
        return _EXTRACCION_CACHE[clave]
    out = []
    for f in sorted(EXTRACCION.glob(f"*/{bibcode}.json")) if EXTRACCION.exists() else []:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        trozos: list = []

        def _walk(v):
            """Every string inside the JSON — the extractor's quotes live in several fields."""
            if isinstance(v, str):
                trozos.append(v)
            elif isinstance(v, dict):
                for x in v.values():
                    _walk(x)
            elif isinstance(v, list):
                for x in v:
                    _walk(x)
        _walk(data)
        out.append(normalize_source_text(" \n ".join(trozos)))
    _EXTRACCION_CACHE[clave] = out
    return out


def quote_found(quote: str, source_norm: str) -> bool:
    """Is this quote in that (already normalized) source text? All its fragments must be."""
    for variante in quote_variants(quote):
        frags = quote_fragments(variante)
        if frags and all(f in source_norm for f in frags):
            return True
    return False


# #271 — el markup que los catálogos meten en título y abstract. La lista original cubría seis
# etiquetas y dejaba afuera 111 de las 249 ocurrencias medidas en una bóveda real: `<ASTROBJ>` deja
# el nombre del objeto INVISIBLE en un renderer que no escapa, `<A href>` convierte una copia
# verbatim en un link vivo, y `<P />`/`<BR />` parten el párrafo, así que la estructura publicada no
# es la del abstract de catálogo. Y el comportamiento depende del parser —markdown-it y pandoc
# escapan, Python-Markdown no—, o sea que la capa que el contrato declara **auditable** dice cosas
# distintas según quién la abra.
# ⚠ El `(?=[\s/>])` no es cosmético: sin él, `A` matchea el arranque de `<Author>` y la limpieza
# se come texto que no es markup.
_CATALOG_TAG_RE = re.compile(
    r"</?(?:SUB|SUP|SUP1|I|B|BR|P|A|ASTROBJ|INLINE-FORMULA|MML:[A-Z]+)(?=[\s/>])[^<>]*>", re.I)


def clean_catalog_markup(s: str) -> str:
    """Catalog text (title, abstract) with ADS's HTML markup resolved (#230).

    ADS returns `Ca II H&amp;K`, `H<SUB>2</SUB>O`, `m s<SUP>-1</SUP>` verbatim, and nobody
    normalised them: the string went into the note's `title:`, got published in every roll-up, and
    broke any title↔text cross-check —which is what the alias grep, the lens diff and the duplicate
    detector all do—. Entities are unescaped and the sub/superscript tags dropped: the digit stays,
    which is what a plain-text index needs, and no attempt is made to render `₂` (guessing a
    typographic form the source did not send would be inventing).
    """
    if not isinstance(s, str) or not s:
        return s
    # ⛔ Dos pasadas, y el orden importa (#271): con `unescape` PRIMERO y una sola pasada, un
    # `&lt;P /&gt;` que el catálogo mandó escapado se convertía en un `<P />` **vivo** — la función
    # fabricaba el markup que existe para sacar. Se limpia el crudo, se desescapan las entidades
    # (`&amp;` → `&`, que es lo que se quiere ver), y se limpia otra vez lo que haya aparecido.
    return _CATALOG_TAG_RE.sub("", html.unescape(_CATALOG_TAG_RE.sub("", s)))


_MATH_SPAN_RE = re.compile(r"\$[^$\n]*\$")


def escape_cell(texto: str) -> str:
    r"""Prose safe to put in a markdown table CELL: every `|` neutralised (#240).

    The extractor writes prose into the cells of the view table —an equation, the transcribed
    columns of a table in the paper, a `grep` alternation— and a raw `|` there SPLITS THE ROW: the
    extra cells do not render, so a cited and verified claim becomes invisible to the reader while
    the lint still counts its row. Measured on a real vault: **19 rows in 13 notes of one theme**.
    The rule existed (INV-99) and lived only in the `verify-citations` skill, for the other table.

    ⛔ Inside `$…$` the escape is ``\\vert``, NOT ``\\|``: in LaTeX ``\\|`` is the DOUBLE bar ‖, so escaping
    blindly would silently change the formula — 19 invisible rows turned into 19 wrong equations,
    which is worse (the invisible row is noticed; the altered formula is not).
    """
    if "|" not in str(texto or ""):
        return texto
    out, i = [], 0
    for m in _MATH_SPAN_RE.finditer(texto):
        out.append(texto[i:m.start()].replace("|", r"\|"))
        out.append(m.group(0).replace("|", r"\vert "))
        i = m.end()
    out.append(texto[i:].replace("|", r"\|"))
    # `\vert ` necesita el espacio para no pegarse a la letra siguiente; cuando ya venía uno,
    # quedaban dos y el diff se llenaba de ruido invisible.
    return re.sub(r"\\vert\s+", r"\\vert ", "".join(out))


def method_key(nombre) -> str:
    r"""A method name reduced to its comparison key: casefold, NFKD, non-alphanumerics to `-` (#243).

    `methods` is populated by the EXTRACTION —one LLM per paper— with an open vocabulary and no
    normalisation, so the same method arrives spelled several ways. Measured over 30 notes of one
    theme: 64 methods, 69 spellings, five collisions (`PCA`/`pca`, `MCMC`/`mcmc`, `SVD`/`svd`,
    `SysRem`/`sysrem`, `wPCA`/`wpca`). The roll-up compared the raw string, so a concept named `pca`
    reached **21 papers out of 24** and said nothing about the three it missed — a roll-up
    under-declaring its own universe in silence, which is what D-10 exists to prevent.

    ⛔ Normalising at COMPARISON time, never at write time: the spelling the extractor chose is
    information about how the paper names it, and rewriting it would destroy that.
    """
    s = unicodedata.normalize("NFKD", str(nombre or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.casefold()).strip("-")


def concept_alias_index() -> dict:
    """`{method_key(name): stem}` for every ingested concept: its own stem **and** its `aliases`.

    The canonical name of a method IS the stem of its note, and `aliases` is the synonym table the
    schema already asks for — and nobody read it: the roll-up and the lint compared only against the
    stem, so `bisector span` and `bis` were two different methods. Measured on a real vault: of 121
    `methods` without a destination page, the alias index closes 7 (`ff-prime` → the activity
    indicators note, `rv-color` → `crx`, `heteroscedastic-noise` → `ica-noise`…). Small, and the
    right kind of small: what fills that backlog is the extractor SEEING the list before inventing
    a spelling, not the index alone.

    ⛔ The stem wins over a foreign alias: if `pca.md` exists and another note claims `pca` as an
    alias, the destination is `pca`. An index that picked by glob order would not be deterministic.
    ⚠ An alias↔alias collision is **not resolved here**: the first stem in alphabetical order wins
    and `alias_collisions` reports it — choosing in silence would decide for the user which concept
    a name denotes."""
    if not CONCEPTS.exists():
        return {}
    stems = sorted(p_.stem for p_ in CONCEPTS.glob("*/*.md"))
    idx: dict = {}
    for nota in sorted(CONCEPTS.glob("*/*.md")):   # los alias primero: el stem los pisa después
        try:
            fm = split_fm(nota.read_text(encoding="utf-8")) or {}
        except OSError:
            continue
        for alias in as_list(fm.get("aliases")):
            idx.setdefault(method_key(alias), nota.stem)
    for stem in stems:                       # el stem SIEMPRE gana
        idx[method_key(stem)] = stem
    return {k: v for k, v in idx.items() if k}


def alias_collisions() -> list:
    """`[(alias, [stems])]` — aliases claimed by more than one concept (#245).

    The alias is reported with the SPELLING the note wrote, not its comparison key: the user has to
    find it in a YAML, and `senal-comun` is not what is written there.

    Reported, never resolved: which concept a name denotes is curation, and picking one in silence
    is deciding for the user (regla de método 5)."""
    if not CONCEPTS.exists():
        return []
    por_clave: dict = {}
    for nota in sorted(CONCEPTS.glob("*/*.md")):
        try:
            fm = split_fm(nota.read_text(encoding="utf-8")) or {}
        except OSError:
            continue
        for alias in as_list(fm.get("aliases")):
            if (k := method_key(alias)):
                por_clave.setdefault(k, []).append((nota.stem, str(alias).strip()))
    return [(pares[0][1], [st for st, _ in pares])
            for _k, pares in sorted(por_clave.items())
            if len({st for st, _ in pares}) > 1]


def method_target(nombre, index: dict | None = None) -> str | None:
    """The concept note this method name denotes (stem), or `None` (#245)."""
    idx = concept_alias_index() if index is None else index
    return idx.get(method_key(nombre))


_GLOSA_FINAL = re.compile(r"\s*\([^()]*\)\s*$")


def indicator_key(nombre) -> str:
    """`method_key` after dropping the trailing parenthetical GLOSS (#250).

    `activity_indicators_expected` is prose written for a human —`BIS (bisector de la CCF)`,
    `S-index (Ca II H&K)`— so comparing it raw against concept stems makes **every** entry dangle,
    and a backlog that is born 100 % false is one nobody looks at again. ⛔ Only the trailing
    parenthesis, and only when COMPARING: the field itself is never rewritten (same doctrine as
    `method_key`)."""
    return method_key(_GLOSA_FINAL.sub("", str(nombre or "").strip()))


def method_matches(concepto: str, nombres) -> bool:
    """Does any of those method names denote `concepto`? Compared by `method_key` (#243)."""
    clave = method_key(concepto)
    return bool(clave) and any(method_key(n) == clave for n in as_list(nombres))


def looks_decidable(salvedad: str) -> bool:
    """Does this prose caveat make a claim a script could settle? (#234)

    The measured failure of #213 is a caveat that **invents** a defect of the artefact — «the
    `.txt` lost this symbol» — published under the very heading a consumer reads to decide how much
    to trust the extraction. #213 gave that claim a structured form and a `grep`; what it did not
    give is anything that makes the extractor USE it. Measured on a real vault: **0 of 43**
    extractions emitted a structured caveat, and one false one slipped through again.

    High-signal heuristic, same contract as the implementation-leak detector: it points at caveats
    worth restating as `SALVEDAD_TIPOS`, it does not judge them."""
    return bool(_SALVEDAD_DECIDIBLE.search(str(salvedad or "")))


def is_stamped_section(heading: str) -> bool:
    """Public entry point for the stamped-section test (#214).

    `solo_prosa` was the only consumer, so the predicate stayed private — but a second detector
    needs it **keeping line numbers**, which `solo_prosa` cannot give (it drops lines). Exposing
    the predicate is the fix; re-implementing the heading match at the call site is exactly the
    duplicated-rule bug that method rule nº 2 is about."""
    return _es_estampada(heading)


_VISTA_HEAD = re.compile(r"^##\s+Vista\s*[—–-]\s*(.+?)\s*$", re.M)
_EJES_HEAD = re.compile(r"^\*\*Ejes:\*\*\s*$", re.M)
_EJE_BULLET = re.compile(r"^-\s+\*\*(.+?):\*\*", re.M)


def view_axes(text: str) -> dict:
    """`{subject: {axes answered}}` — the bullets of each view's `**Ejes:**` block (#270).

    #254 made the prompt derive its axes from `relevance.facets` and left no net: nothing compares
    the axes a view **answers** against the lens it **declares**. Measured on a real vault: 257 gaps
    over 79 views that declare a lens.

    ⚠ Only bullets INSIDE the `**Ejes:**` block count: `- **Aporte:**`, `- **Métodos:**` and
    `- **Hueco:**` are not axes, and a plain bold-bullet regex would count them. Headings inside a
    code fence are skipped, same as `lint.vistas_en_cuerpo` (AUD-178)."""
    dentro = _offsets_en_fence(text)
    encabezados = [(m.start(), m.group(1).strip()) for m in _VISTA_HEAD.finditer(text)
                   if m.start() not in dentro]
    out: dict = {}
    for i, (ini, sujeto) in enumerate(encabezados):
        fin = encabezados[i + 1][0] if i + 1 < len(encabezados) else len(text)
        seccion = text[ini:fin]
        if (corte := re.search(r"\s+[^\w\s]", sujeto)):
            sujeto = sujeto[:corte.start()].strip()
        m_ejes = _EJES_HEAD.search(seccion)
        if not m_ejes:
            continue
        # El bloque son los bullets CONTIGUOS que siguen al encabezado: se saltean las líneas en
        # blanco iniciales (el escritor deja una) y se corta en la primera línea que no es un
        # bullet, blanco incluido. Sin cortar en el blanco, `- **Aporte al tema:**` —que vive más
        # abajo y NO es un eje— entraba al conjunto y tapaba el hueco que el detector busca.
        bloque, arranco = [], False
        for linea in seccion[m_ejes.end():].split("\n"):
            if linea.strip().startswith("- "):
                bloque.append(linea); arranco = True
            elif arranco or linea.strip():
                break
        out.setdefault(sujeto, set()).update(m.group(1).strip()
                                             for m in _EJE_BULLET.finditer("\n".join(bloque)))
    return out


def solo_prosa(body: str) -> str:
    """El cuerpo SIN las secciones que estampa la máquina — lo que alguien escribió de verdad."""
    out, saltando = [], False
    for ln in body.split("\n"):
        if ln.startswith("## "):
            saltando = _es_estampada(ln)
        if not saltando:
            out.append(ln)
    return "\n".join(out)


def _offsets_en_fence(text: str) -> set:
    """Offsets de comienzo de línea que caen DENTRO de un ```code fence```.

    ⛔ `section_start` matcheaba un encabezado de ejemplo dentro de un fence. Medido el 2026-08-28:
    una nota con el bloque de verificación ilustrado en un fence y el bloque **real** más abajo hacía
    que `parse_verif_table` leyera **el del ejemplo** — devolvía una sola fila, la del fence, con su
    `no-soportada` de muestra (bloqueante) mientras **todos los pares reales caían a «sin
    verificar»**.

    Es una asimetría dentro del mismo framework: `lib_blocks.split_blocks` excluye los fences **a
    propósito** y este cortador no. La doc del repo está llena de bloques de ejemplo en fences, así
    que la población existe.
    """
    #  @inv INV-98
    dentro, fenced, off = set(), False, 0
    for ln in text.split("\n"):
        if ln.lstrip().startswith("```"):
            fenced = not fenced
            dentro.add(off)
        elif fenced:
            dentro.add(off)
        off += len(ln) + 1
    return dentro


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

    A suffix is punctuation, never more words (#176). `## Papers` is a **prefix** of
    `## Papers que tocan este tema (auto)`, so the loose match had `stamp_papers_table` overwrite
    the concept roll-up and `stamp_concept_rollup` return `False` forever — silently, and taking
    D-24's *Entró por* column with it. Any two sections where one names a prefix of the other hit
    the same trap, so the rule lives here and not at the call site.
    """
    #  @inv INV-98
    dentro = _offsets_en_fence(text)
    for i in ([0] if text.startswith(header) else []) + _header_hits(text, header):
        if i in dentro:
            continue        # el encabezado vive dentro de un ```code fence```: es un EJEMPLO
        resto = text[i + len(header):].split("\n", 1)[0].strip()
        if not resto or not resto[0].isalnum():
            return i
    return -1


def section_span(text: str, header: str) -> tuple[int, int] | None:
    """`(start, end)` of the section opening at `header`, up to the next `## ` (or EOF).

    Lives here, next to `section_start`, because it has TWO consumers (the stamper of the reading
    aids and the duplicate detector of #216) and "where does a section end" is exactly the kind of
    rule that grows a second, subtly different copy at the second call site — the failure this repo
    already paid for twice (`section_start` itself, and `_es_estampada`)."""
    inicio = section_start(text, header)
    if inicio < 0:
        return None
    nxt = text.find("\n## ", inicio + 1)
    return inicio, (len(text) if nxt < 0 else nxt + 1)


def _header_hits(text: str, header: str) -> list[int]:
    """Every line-anchored occurrence of `header`, in order. Plural because the first one may be a
    longer heading that only *starts* with it (#176) and the real section comes later."""
    out, j = [], text.find("\n" + header)
    while j >= 0:
        out.append(j + 1)
        j = text.find("\n" + header, j + 1)
    return out


STARS = WIKI / "stars"
PAPERS = WIKI / "papers"
CONCEPTS = WIKI / "concepts"
QUERIES = WIKI / "queries"
MATRICES = WIKI / "matrices"
INDEX = WIKI / "index.md"
LOG = WIKI / "log.md"
STATUS = VAULT / "STATUS.md"        # #302: estado vigente de la instancia (se REESCRIBE, no se appendea)


def get_mailto() -> str:
    """Contact email for the polite pools of OpenAlex, Crossref and Unpaywall — **opt-in**.

    Reads `ALMAGESTO_MAILTO` or `vault/config/mailto`, and returns `""` when neither is set. The
    three services work without it; the address only buys a faster rate-limit tier.

    ⛔ It is NOT taken from `git config user.email` any more. That address is the operator's personal
    data, offered to git for authorship — not for egress to three third parties on every run, with
    no opt-in and no way to turn it off. Measured on 2026-08-28: twelve live calls carried it,
    embedded in the URL and therefore in any `raise_for_status` message and any proxy log. Sending
    a personal identifier is a decision that belongs to whoever owns the address, so it is declared
    once, in a gitignored file, exactly like the ADS token.
    """
    #  @inv INV-67
    v = os.environ.get("ALMAGESTO_MAILTO")
    if v and v.strip():
        return v.strip()
    if MAILTO_FILE.exists():
        return MAILTO_FILE.read_text(encoding="utf-8").strip()
    return ""


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
#  U+FEFF al principio del archivo. Un editor de Windows lo escribe sin avisar y **rompe el ancla**:
#  `matches[0].start() != 0`, así que `frontmatter_span` devolvía `None`, `split_fm` `{}` y
#  `lint.fm_error` tampoco lo veía (chequea `text.startswith("---")`). La nota evadía **todos** los
#  chequeos de su tipo —incluido `retracted`— sin una línea de reporte. Medido el 2026-08-28.
#  Se saca al leer, no en cada consumidor: todos abren con `utf-8`, no con `utf-8-sig`.
BOM = "\ufeff"


def fm_bounds(text: str) -> tuple[int, int] | None:
    """`(ini, fin)` — the offsets of the YAML block inside `text`, for a surgery that rebuilds the
    note as `text[:ini] + nuevo_head + text[fin:]`.

    ⛔ AUD-147 — eleven surgeries in `make_notes` located the frontmatter with
    `startswith("---\n")` + `find("\n---\n", 4)` while `frontmatter_span` (the parser everything
    else uses) matches the delimiter as a **line**: `^---[ \t]*$`. So a note whose closing `---`
    carries a trailing space parses perfectly for `split_fm` and every one of those eleven
    surgeries turns into a **silent no-op** — the stamper reports «nothing to do» over a note it
    could not read. A leading BOM does the same to the opening one (AUD-116, one layer down): here
    `text[:ini]` carries it through instead of dropping it on rebuild.

    Same delimiter rule as `frontmatter_span`, and that is the point: one locator, not two."""
    off = len(text) - len(text.lstrip(BOM))
    cuerpo = text[off:]
    matches = list(_FM_DELIM_RE.finditer(cuerpo))
    if len(matches) < 2 or matches[0].start() != 0:
        return None
    return off + matches[0].end() + 1, off + matches[1].start() - 1


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
    text = text.lstrip(BOM)
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
        fm = yaml.safe_load(yaml_block)
    except Exception:
        return {}
    # ⛔ La firma dice `-> dict` y el docstring promete «dict vacío si no hay o no parsea». Un YAML
    # **válido pero no-mapa** —`---\n- a\n- b\n---`, `---\nuna frase suelta\n---`, `---\n42\n---`—
    # devolvía la lista/str/int tal cual y reventaba a los 22 llamadores: medido el 2026-08-28, una
    # sola nota así tumbaba `lint.main()` entero con `AttributeError` en `normalize_lists`, sin
    # reporte, sin nombre de archivo y sin escribir ningún output. `isinstance`, no `or {}`: un
    # escalar truthy no cae en el `or` (el mismo argumento que `as_map` documenta al lado).
    # La otra mitad —que la nota GRITE en vez de evadir— la pone `lint.fm_error`.
    return fm if isinstance(fm, dict) else {}


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


VERIF_HEAD_RE = re.compile(r"^##\s+Verificaci[oó]n de citas\b(.*)$", re.M)
_VERIF_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def verification_date(text: str) -> tuple[bool, str | None]:
    """(does the note carry a `## Verificación de citas` block?, date of the most recent one).

    The date lives in the heading by the skill's convention (`## Verificación de citas
    (AAAA-MM-DD)`): it is the only thing that says whether what was verified is still current or
    fell behind a later edit. A note can accumulate **several** blocks — up to 11 measured in a
    real vault, successive passes over different sections — so currency is the **maximum** date,
    not the first one: keeping the first leaves the note stale forever no matter how often it is
    re-verified.

    ⛔ AUD-136 — this rule had two implementations that disagreed: the lint took the maximum and
    `make_notes.estado_line` took the FIRST, so the header a note publishes and the verdict the
    lint computes about that same note could name different dates. One rule, one function.
    @inv INV-31"""
    heads = VERIF_HEAD_RE.findall(text)
    if not heads:
        return False, None
    dates = [m.group(0) for m in (_VERIF_DATE_RE.search(h) for h in heads) if m]
    return True, max(dates) if dates else None


def ratchet_raises(rel_path: str, fields, root: Path | None = None) -> list | None:
    """Which ceilings of `rel_path` went UP since HEAD without a declared escape hatch.

    Returns a list of `(field, before, now)`, `[]` when nothing rose (or every rise is justified),
    and **`None` when the check could not run** — no git, file not in HEAD, unreadable YAML. `None`
    is *not evaluated*, never *did not rise*: saying so is the difference between «I looked and it
    is fine» and «I did not look» (D-43).

    ⛔ AUD-139 — this guard existed only for `docs/trazabilidad-ratchet.yaml`, hardcoded inside
    `trace_invariants`. The repo has four ratchets and all four carry the same written promise
    («the ceiling only goes down»); on three of them that promise was held up by human review
    alone, so nothing stopped raising the ceiling in the very commit that broke the coverage — the
    exact hole #96 closed for the fourth one.

    The escape hatch is a `# ratchet-sube: <field> <before>→<now> — <reason>` comment in the YAML,
    with a **mandatory reason** (same criterion as `triage.py --reason`: a gate is never loosened
    in silence) and **bound to the concrete transition**. The second half matters as much as the
    first: a generic hatch would sit in the file forever and disable the check from then on, with
    the next rise riding for free on the previous one's reason. Requiring an explicit `2→3` makes
    the justification **expire by itself**.  @inv INV-140"""
    import subprocess
    base = root or ROOT
    path = base / rel_path
    try:
        r = subprocess.run(["git", "show", f"HEAD:{rel_path}"],
                           cwd=base, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        antes_doc = yaml.safe_load(r.stdout) or {}
        ahora_doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        texto = path.read_text(encoding="utf-8")
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(antes_doc, dict) or not isinstance(ahora_doc, dict):
        return None
    subidas = []
    for campo in fields:
        antes, ahora = _ratchet_value(antes_doc, campo), _ratchet_value(ahora_doc, campo)
        if antes is None or ahora is None or ahora <= antes:
            continue
        patron = re.compile(
            rf"#\s*ratchet-sube:.*\b{re.escape(campo)}\b\s*{antes}\s*(?:→|->)\s*{ahora}\s*[—:-]\s*\S")
        if not patron.search(texto):
            subidas.append((campo, antes, ahora))
    return subidas


def _ratchet_value(doc: dict, campo: str) -> int | None:
    """The ceiling named `campo`, at top level or under `techos:`; None when absent or not a number."""
    v = doc.get(campo)
    if v is None and isinstance(doc.get("techos"), dict):
        v = doc["techos"].get(campo)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def gate2_threshold(meta) -> tuple[int | None, str | None]:
    """The theme's `fundacional_min_citas` as `(threshold, why it is unusable)`.

    ⛔ AUD-142 — three call sites implemented this rule with three different contracts:
    `classify_theme` and `puertas_abiertas` took `isinstance(umbral, int)` while `puerta2_cruces`
    took `(int, float)`. So a `fundacional_min_citas: 30000.0` — or the far likelier
    `"30000"`, a quoted number in hand-edited YAML — closed gate 2 for the classifier and left it
    open for the drift detector, and the classifier's motive then said *«el tema no declara
    `fundacional_min_citas`»*, which is **false**: it declares it. A wrong reason is worse than no
    reason (the audit's rule of method #4), and here it sends the operator to add a key that is
    already there.

    Absent is legitimate and returns `(None, None)`: D-26 deliberately gives the threshold no
    default —30k citations is normal in ML and enormous in astro— so the gate stays shut and the
    `why_excluded` says so. Anything present but unusable returns the reason, which the caller
    publishes instead of inventing one. A `bool` is rejected on purpose: in Python it *is* an
    `int`, so `fundacional_min_citas: yes` would silently become a threshold of 1.  @inv INV-141"""
    v = as_map(meta).get("fundacional_min_citas") if isinstance(meta, dict) else None
    if v is None:
        return None, None
    if isinstance(v, bool):
        return None, ("`fundacional_min_citas: {}` es un booleano, no un número de citas — en YAML "
                      "`yes`/`no`/`true` parsean como bool y en Python un bool ES un int, así que "
                      "sin este chequeo el umbral valdría 1".format(v))
    if isinstance(v, int):
        return v, None
    if isinstance(v, float):
        if v.is_integer():
            return int(v), None
        return None, f"`fundacional_min_citas: {v}` tiene decimales — un conteo de citas es entero"
    return None, (f"`fundacional_min_citas: {v!r}` no es un número (es {type(v).__name__}) — si lo "
                  f"escribiste entre comillas en `themes.yaml`, sacáselas")


_YAML_KEY_RE = re.compile(r"^(\s*)([A-Za-z_][\w.-]*):")


def reattach_yaml_comments(original: str, nuevo: str) -> tuple[str, list[str]]:
    """Put back into `nuevo` the YAML comments that `original` carried. `(head, huérfanos)`.

    ⛔ AUD-169 / INV-139 — `sync_mirror` and `migrate_disputes` re-serialize the whole frontmatter
    with `yaml.safe_dump`, which **silently drops every comment**. The framework explicitly tells
    people to hand-edit these files («el `P_rot` lo puso el usuario a mano», «sacá la entrada de
    `decisiones`»), so those comments are curation: a stamper that erases them destroys work nobody
    can reconstruct, and does it while reporting success.

    Two shapes are restored, which are the two people write: the **standalone block** above a key
    (re-anchored to that key, so it survives a reordering) and the **trailing comment** on a key's
    own line. Anything whose anchor key no longer exists comes back in `huérfanos` for the caller to
    report — never dropped in silence, which is the whole point.

    Deliberately naive about nesting: it anchors by `(indent, key)` on the first match. A frontmatter
    with the same key at the same indentation twice (two planets with a commented `K_ms`) puts the
    comment on the first one. Better a comment slightly out of place than a comment deleted."""
    bloque: list[str] = []
    pendientes: list[tuple[str, str, list[str]]] = []     # (indent, key, comment lines)
    trailing: dict[tuple[str, str], str] = {}
    for ln in original.split("\n"):
        desnudo = ln.strip()
        if desnudo.startswith("#"):
            bloque.append(ln)
            continue
        m = _YAML_KEY_RE.match(ln)
        if m:
            if bloque:
                pendientes.append((m.group(1), m.group(2), bloque))
                bloque = []
            resto = ln[m.end():]
            if (i := _trailing_comment_at(resto)) is not None:
                trailing[(m.group(1), m.group(2))] = resto[i:]
        elif desnudo:
            bloque = []                                   # el bloque colgaba de algo que no es clave
    huerfanos = list(bloque)                              # comentarios al final, sin clave abajo
    lineas = nuevo.split("\n")
    for indent, clave, comentario in pendientes:
        idx = next((i for i, ln in enumerate(lineas)
                    if (m := _YAML_KEY_RE.match(ln)) and (m.group(1), m.group(2)) == (indent, clave)),
                   None)
        if idx is None:
            huerfanos.extend(comentario)
            continue
        lineas[idx:idx] = comentario
    for (indent, clave), comentario in trailing.items():
        for i, ln in enumerate(lineas):
            m = _YAML_KEY_RE.match(ln)
            if m and (m.group(1), m.group(2)) == (indent, clave) and \
                    _trailing_comment_at(ln[m.end():]) is None:
                lineas[i] = ln.rstrip() + comentario
                break
        else:
            huerfanos.append(f"{clave}:{comentario}")
    return "\n".join(lineas), huerfanos


def _trailing_comment_at(resto: str) -> int | None:
    """Offset of the ` #` that opens a trailing comment in `resto`, or None. Quote-aware: a `#`
    inside a quoted scalar (`title: "a # b"`) is content, not a comment."""
    comilla = ""
    for i, c in enumerate(resto):
        if comilla:
            if c == comilla:
                comilla = ""
        elif c in "\"'":
            comilla = c
        elif c == "#" and (i == 0 or resto[i - 1] in " \t"):
            j = i
            while j > 0 and resto[j - 1] in " \t":   # el espaciado antes del `#` es parte del
                j -= 1                                # comentario: sin él queda pegado al valor
            return j
    return None


def print_seguro(texto: str, file=None) -> None:
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
    stream = file if file is not None else sys.stdout
    try:
        print(texto, file=stream)
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "ascii"
        print(texto.encode(enc, errors="replace").decode(enc), file=stream)


def as_list(v) -> list:
    """`v` si es una lista; `[]` si no. Hermano de `as_map` para el otro lado del mismo defecto: un
    campo que el schema declara lista (`planets`, `thesis_links`, `posiciones`) pero que llega
    escalar o `None` desde un YAML editado a mano — iterarlo a pelo itera caracteres de un string o
    revienta con `TypeError` en vez de comportarse como la lista vacía que es el caso degenerado
    correcto."""
    return v if isinstance(v, list) else []


# Áreas de vault/wiki/concepts/ RESERVADAS (siempre válidas): `methods` es universal;
# `hypotheses` es estructural (schema name/status + roll-up ESTAMPADO). Desde D-10/D-11
# ningún roll-up es Dataview: `make_notes` los materializa, porque un bloque ```dataview```
# le muestra a un agente que abre el `.md` el código de la query, no sus resultados (#180).
# Ver CLAUDE.md.
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


class UnreadableRegistro(RuntimeError):
    """The subject's registro exists on disk but cannot be parsed into a mapping.

    Raised by `load_decisiones` so that no curation consumer can silently fall back to «no
    decisions at all». See its docstring for why the tolerant `{}` of `load_registro` is a hole on
    this particular path.  @inv INV-139"""


def cli_exit(main_fn) -> None:
    """Run a script's `main()` and turn the framework's declared refusals into a clean exit.

    Single wrapper instead of one `try/except` per script: the audit's most expensive pattern is
    «the fix was applied to one site and not to its twin», and a refusal that reaches the terminal
    as a traceback reads like a crash of the tool rather than like the guard it is.  @inv INV-139"""
    try:
        sys.exit(main_fn())
    except UnreadableRegistro as exc:
        sys.exit(f"⛔ {exc}")


def registro_error(slug: str) -> str | None:
    """Reason why `<slug>.yaml` cannot be used as this subject's registro, or `None` if healthy.

    Sibling of `objective_error` / `yaml_error`, and it exists for the same reason (INV-80): the
    tolerant loader collapses three states into one `{}` — file absent (legitimate: a subject may
    never have been ingested), broken YAML, and valid YAML with the wrong shape — and the strict
    callers need to tell them apart. An absent file is **not** an error.  @inv INV-139"""
    f = registro_path(slug)
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None                      # ausente es legítimo: el sujeto puede no estar ingestado
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return (f"{f} no parsea como YAML: {' '.join(str(exc).split())} — es el archivo que guarda "
                f"la curación del sujeto (`decisiones`) y el universo de sus búsquedas")
    except OSError as exc:
        return f"{f} no se pudo leer: {exc}"
    if data is not None and not isinstance(data, dict):
        return (f"{f} parsea, pero no a un mapa (es {type(data).__name__}) — el registro es un "
                f"mapa con `decisiones`/`busquedas`/`cadena`")
    return None


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
        # AUD-192 / INV-25 — `UnicodeDecodeError` faltaba, y es el caso NATURAL: `motivo:` lleva
        # prosa acentuada, así que un registro guardado en latin-1 es alcanzable (`load_registro` ya
        # lo lista desde AUD-41). Sin él la guarda no se disparaba: la excepción subía sin traducir
        # y, peor, este `if` existe justamente para NO pisar a ciegas lo único no regenerable de la
        # bóveda. `UnicodeDecodeError` es subclase de `ValueError`, no de `OSError`.
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            raise RuntimeError(
                f"{f} existe pero no se pudo leer ({type(exc).__name__}) — no lo piso a ciegas: se "
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
    el lint lo detecta y bloquea.

    ⛔ **REHÚSA operar sobre un registro ilegible** (AUD-131 / INV-139). `load_registro` degrada un
    YAML roto a `{}` a propósito —el framework instruye editar el archivo a mano, y sus lectores
    tolerantes (el lint) tienen que reportar en vez de morirse—, pero en ESTE camino ese `{}`
    significa *«no hay ninguna decisión»*, que es exactamente lo contrario de lo que el archivo
    dice: los `--drop` dejan de aplicarse, los `--drop-core` vuelven a ser core, `fetch_pdf` los
    baja de nuevo y el triage los re-propone **sin el motivo**. O sea el bug que #51 cerró, más el
    que #112 cerró, disparados por un `:` sin comillas y sin que nada lo diga. Es la misma doctrina
    que la lente ilegible de INV-80: una config que no parsea rehúsa operar, no degrada en
    silencio.  @inv INV-139"""
    if (err := registro_error(slug)):
        raise UnreadableRegistro(
            f"{err}\n   ⛔ No se puede aplicar la curación de `{slug}`: un registro ilegible se "
            f"leería como «no hay ninguna decisión» y los papers descartados volverían a entrar.")
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


def dropped_from_subject(slug: str) -> dict:
    """Papers the user declared OUT of THIS subject: ``{bibcode: motivo}`` (#112, carril `sujeto`).

    Canonical implementation, and it is canonical for a reason. The same comprehension lived
    copy-pasted in four places —`query_ads.excluidos_del_sujeto`, the roll-up of `make_notes`, the
    lens diff here— and the fourth consumer, the one that decides WHICH paper notes get written,
    simply never got a copy. That gap resurrected a dropped paper as an empty stub on top of the
    extraction that `--drop-core` had just deleted: a curation decision ignored in silence, which
    is the very bug #112 closed one layer above.

    The `sujeto` rail is deliberate (the exclusion is of the PAIR paper-subject), and the
    `decision == "descartado"` guard matters just as much: `origen: sujeto` alone also matches
    decisions that are not discards."""
    return {b: (d.get("motivo") or "(sin motivo)")
            for b, d in load_decisiones(slug).items()
            if d.get("decision") == "descartado" and es_del_carril(d, "sujeto")}


# Vocabulario CERRADO de `via` en `extra_core` (D-58): de dónde salió la aceptación de ese paper.
# Cerrado por el mismo motivo que `role` (#73): un typo deja el campo mudo para el único consumidor
# que existe —la columna Origen de la ficha—, y un campo mudo se lee como "no se sabe".
EXTRA_CORE_VIA = ("usuario", "triage", "citado-por-corpus")


def extra_core_snippet(recs, via: str = "usuario", motivo: str = "<por qué es core para este sujeto>",
                       tope: int = 10) -> str:
    """El bloque `extra_core:` listo para pegar, en la forma DURA de D-58 (#161).

    Una sola implementación para los dos carriles que lo imprimen. `query_ads --sweep` dictaba
    `extra_core: [<bibcode>, …]` con `via: manual`, y las dos mitades **abortan**: D-58 rechaza el
    escalar y la lista de strings, y `manual` no está en `EXTRA_CORE_VIA`. Un script que le dicta al
    usuario una forma que el propio framework bloquea es peor que no decir nada: el usuario copia,
    pega, y la corrida siguiente muere.

    El `via` sale de `EXTRA_CORE_VIA` y se valida acá, así que un typo revienta al generar el
    snippet y no seis pasos después, al cargar la config."""
    if via not in EXTRA_CORE_VIA:
        raise ValueError(f"`via: {via}` no está en el vocabulario ({' | '.join(EXTRA_CORE_VIA)})")
    hoy = _dt.date.today().isoformat()
    out = ["extra_core:"]
    for r in list(recs)[:tope]:
        out.append(f"  - bibcode: {r['bibcode']}\n    via: {via}\n    fecha: {hoy}\n"
                   f"    motivo: {motivo}")
    return "\n".join(out) + "\n"


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


def load_discarded_aliases(meta: dict, *, entry: str = "?") -> list:
    """`aliases_descartados: [{id, motivo}]` — a SIMBAD identifier CONSIDERED AND REJECTED (#252).

    WHY IT EXISTS. The `aliases` rail was the only curation rail with no way to record the NO.
    The #82 check compares what SIMBAD knows against what `stars.yaml` declares, and its own
    message tells you to leave the machine-catalogue identifiers (`Gaia DR3`, `2MASS J`) out — so
    it **instructs you to discard and then reports the discard as debt**, forever.
    Measured on `hd_40307` with the curation done and documented one identifier at a time in a YAML
    comment: 18 identifiers reported anyway. Not a rare case — SIMBAD returns machine-catalogue ids
    for every star — so the category stayed permanently red, and a category that cries wolf stops
    being read: precisely the one whose own text says that a missing alias is a paper that never
    shows up, silently.

    Same contract as its siblings (`--drop`, `no_vista`, `no_sintetizado`): **motive required**,
    versioned, travels in git. And the same HARD FORM as `extra_core` (D-58): a bare scalar and a
    list of strings **abort**, because an identifier without a motive cannot say whether anyone
    looked at it.

    What this field is NOT: a pattern filter. Excluding `Gaia DR3`/`2MASS J` from code would be the
    framework curating for the user, and the real cut depends on the field (a `TYC` can be useful
    in older material). The framework **proposes**, curation **decides and signs**.

    @inv INV-142"""
    v = meta.get("aliases_descartados")
    if v is None:
        return []
    if not isinstance(v, list) or any(not isinstance(x, dict) for x in v):
        sueltos = [v] if isinstance(v, str) else [x for x in as_list(v) if isinstance(x, str)]
        sys.exit(_discarded_alias_error(
            entry, sueltos, "`aliases_descartados` no acepta un identificador suelto ni una lista "
                            "de strings: sin `motivo` no se distingue «lo miré y no sirve» de «no "
                            "lo miró nadie», que es toda la información que el campo aporta"))
    for x in v:
        faltan = [k for k in ("id", "motivo") if not x.get(k)]
        if faltan:
            sys.exit(_discarded_alias_error(entry, [x.get("id") or "<identificador>"],
                                            f"a una entrada le falta {', '.join(faltan)}"))
    return v


def _discarded_alias_error(entry: str, ids: list, motivo: str) -> str:
    """The detector's message, with the canonical form already written out to paste.  @inv INV-142"""
    ejemplo = "\n".join(
        f"  - id: {i}\n    motivo: <por qué NO sirve para buscar este sujeto>"
        for i in (ids or ["<identificador de SIMBAD>"]))
    return (f"'{entry}': {motivo}. Forma canónica:\n\naliases_descartados:\n{ejemplo}\n")


# ── #188 · `vistas[]`: extraction is a reading WITH A LENS ───────────────────────────────────────
#
# The extraction prompt never asks "what does this paper say?" but "what does it say ABOUT {name}?",
# with the greps built from that subject's aliases and the bullets branched by subject type (#76).
# The note, though, is ONE per bibcode with a single `## Extracción (LLM)` and no scope — so a note
# that says nothing about an axis is indistinguishable from "somebody looked and there is nothing".
# That is the same false clean D-34 chases in hypotheses (*"no evidence" is not "no evidence
# exists"*) and the one `discover`'s coverage report solves by telling "ran with N" from "DID NOT
# RUN". Measured in a real vault: 141 of 908 notes are claimed by 2+ subjects and NOT ONE has a
# second extraction section.
#
# `vistas[]` are READINGS; `stars` / `thesis_links` / `methods` stay CLAIMS (`make_notes` merges
# those add-only without reading anything). Only the extraction writes a view — never the retro-link.
VISTA_TIPOS = ("star", "theme")
# De QUÉ documento se construyó la vista (#207). Vocabulario cerrado: leyendo el PDF (el caso normal
# desde #205) o sólo el abstract, que es lo único que queda cuando el PDF no se pudo conseguir.
# Ausente = **no consta**, igual que `fecha`: no se rellena, porque un `pdf` inventado sería peor
# que el silencio. Una vista `abstract` es legítima y declarada; lo que el lint pide es el PDF.
VISTA_FUENTES = ("pdf", "abstract")

#: #213 · vocabulario CERRADO de las salvedades ESTRUCTURADAS — las que hacen una afirmación
#: **decidible sobre un archivo**, o sea las que un script chequea y ningún LLM tiene que juzgar.
#: Existe porque una salvedad inventada no la miraba nadie: `verify-citations` descompone la nota en
#: pares (afirmación, `[[bibcode]]`) y una salvedad del tipo *«el `.txt` perdió este símbolo»* no
#: lleva bibcode —es una afirmación sobre el ARTEFACTO, no sobre el paper— así que se cae del
#: fan-out por construcción. Medido: un extractor afirmó una degradación del `.txt` que no existía,
#: invocando #205 para darse autoridad, y lo cazó un duplicado ACCIDENTAL de la extracción.
#: ⚠ Cerrado y chico a propósito: lo que no es decidible por un script no entra acá — se escribe
#: como salvedad de prosa y la nota la marca **NO VERIFICADA**, que es la otra mitad del arreglo.
SALVEDAD_TIPOS = {
    "txt_pierde": "cadena",      # el `.txt` NO contiene `cadena` (la fuente sí): un grep lo decide
    "pdf_paginas": "n",          # el PDF tiene `n` páginas: lo decide el propio PDF
}


class VistasError(RuntimeError):
    """Raised by `load_vistas` on a malformed `vistas[]`.

    NOT a `SystemExit`, unlike `load_extra_core`'s abort, and the difference is the caller: that one
    lives in config and is read by a CLI script, so dying is the whole point. `vistas[]` lives in a
    note's frontmatter and its main reader is the LINT, which walks every note — one broken note has
    to be REPORTED, not take the run down with it. `SystemExit` does not inherit from `Exception`,
    so an `except Exception` around the walk would not even catch it."""


def load_vistas(meta: dict, *, entry: str = "?") -> list:
    """`vistas` in canonical form: a list of maps `{sujeto, tipo[, fecha, txt, lente]}`.

    Hard form with a detector, same rule and same reason as `extra_core` (D-58, R-2): `vistas:
    [eps Eridani]` would be the very claim↔reading conflation this field exists to end, only under a
    new name. `sujeto` and `tipo` are required — without both, the entry does not say from which
    lens the paper was read; `fecha`, `txt` and `lente` are optional and are NOT filled in, because
    absence means "not stated" and an invented `None` would read like a `null` the migrator declared
    on purpose.

    `tipo` is declared, not derived (user's call, 2026-08-27): it duplicates what
    `stars.yaml`/`themes.yaml` already know, and that is accepted so the lint can catch the typo —
    the same trade every other closed vocabulary of this schema makes.

    `fuente` (#207) says WHAT the view was built from: the PDF, or only the abstract when no PDF
    could be obtained. Optional like `fecha` — absent means *not stated* — but closed when present.
    Without it a view written from eight lines of abstract is indistinguishable from one written
    reading the paper, which is D-34's false clean applied to reading; and the abstract is precisely
    where the source overclaims (generalization bias), so it has to be visible.

    Returns fresh dicts (`sujeto`/`tipo` stripped, `lente` listified); never mutates `meta`."""
    v = meta.get("vistas")
    if v is None:
        return []
    if not isinstance(v, list) or any(not isinstance(x, dict) for x in v):
        sueltos = [v] if isinstance(v, str) else [x for x in as_list(v) if isinstance(x, str)]
        raise VistasError(_vistas_error(
            entry, sueltos,
            "`vistas` no acepta un sujeto suelto ni una lista de strings: sin `tipo` la entrada no "
            "dice desde qué lente se leyó el paper, que es todo lo que este campo declara"))
    out = []
    for x in v:
        sujeto, tipo = str(x.get("sujeto") or "").strip(), str(x.get("tipo") or "").strip()
        faltan = [k for k, val in (("sujeto", sujeto), ("tipo", tipo)) if not val]
        if faltan:
            raise VistasError(_vistas_error(entry, [sujeto or "<sujeto>"],
                                            f"a una entrada de `vistas` le falta {', '.join(faltan)}"))
        if tipo not in VISTA_TIPOS:
            raise VistasError(_vistas_error(
                entry, [sujeto],
                f"`tipo: {tipo}` no está en el vocabulario ({' | '.join(VISTA_TIPOS)})"))
        # `fuente` es OPCIONAL (ausente = no consta) pero, si está, cerrada: un typo la dejaría muda
        # justo para la pregunta que existe para contestar —¿esta vista salió del paper o de ocho
        # líneas de abstract?—, que es la distinción que #207 vino a hacer visible.
        #  @inv INV-138
        if (fuente := str(x.get("fuente") or "").strip()) and fuente not in VISTA_FUENTES:
            raise VistasError(_vistas_error(
                entry, [sujeto],
                f"`fuente: {fuente}` no está en el vocabulario ({' | '.join(VISTA_FUENTES)})"))
        # #239 — `enfasis` OPCIONAL: la segunda lectura del mismo sujeto con otra lente. Sin él,
        # `vistas[]` se indexa por sujeto a secas y la segunda lectura no tiene dónde ir — peor, el
        # cosechador PISABA la anterior en silencio. Ausente = la lectura por default del sujeto.
        enfasis = str(x.get("enfasis") or "").strip()
        nueva = dict(x, sujeto=sujeto, tipo=tipo)
        if enfasis:
            nueva["enfasis"] = enfasis
        elif "enfasis" in nueva:
            # presente y vacío es «no consta», no una lente distinta: se saca para que la CLAVE de
            # las dos formas coincida y no convivan dos entradas que son la misma lectura.
            nueva.pop("enfasis")
        if "lente" in nueva:
            # NOT `as_list`: that one drops a scalar to `[]`, and a `lente: rv` written by hand
            # would vanish in silence — the informational field would then read as "no lens
            # recorded", which is the failure this whole issue is about.
            lente = nueva["lente"]
            nueva["lente"] = lente if isinstance(lente, list) else ([] if lente in (None, "") else [lente])
        out.append(nueva)
    return out


def alias_bibcodes() -> set:
    """Bibcodes some note declares as an ALIAS of itself in `versions[]` (D-19).

    The preprint and the published paper are two bibcodes for the **same work**: there is one
    canonical note and the old bibcodes live in `versions[]`. Nothing told the fetchers, so after a
    `--rename-paper` the next run of the chain **re-downloaded the preprint under its old bibcode** —
    a byte-identical copy of a PDF already on disk, which the lint then reports as a hanging
    artefact **for ever** (it has no note, and it cannot have one: #229 blocks the second note).
    Measured in a real vault: the leftover pair was dated a day AFTER the consolidation.

    ⚠ A bibcode that HAS its own note is not returned: that case is the blocking one of #229 and
    must not be silently skipped by a fetcher."""
    if not PAPERS.exists():
        return set()
    stems = {f.stem for f in PAPERS.glob("*.md")}
    out = set()
    for f in sorted(PAPERS.glob("*.md")):
        try:
            fm = split_fm(f.read_text(encoding="utf-8")) or {}
        except OSError:
            continue
        for v in as_list(fm.get("versions")):
            bib = str((v or {}).get("bibcode") if isinstance(v, dict) else v or "").strip()
            if bib and bib not in stems:
                out.add(bib)
    return out


def vista_key(vista: dict) -> tuple:
    """The identity of a view: `(sujeto, enfasis)` (#239).

    A paper read twice for the same subject **with a different lens** is two readings, not one: the
    second used to have nowhere to go, and the harvester overwrote the first in silence. The
    emphasis defaults to `""`, so a view without one keeps the identity it always had."""
    return (str((vista or {}).get("sujeto") or "").strip(),
            str((vista or {}).get("enfasis") or "").strip())


def load_no_vista(meta: dict, *, entry: str = "?") -> list:
    """`no_vista` in canonical form: a list of maps `{sujeto, motivo}`.

    The escape hatch for a subject that claims the paper and was never read from: the view of a
    subject that only feeds a roll-up is OPTIONAL — what it cannot be is SILENT. Same rule and same
    argument as `no_sintetizado` (#75) and the triage's `--reason`: no curating in silence.

    Per subject, not the bare `no_vista: <motivo>` of the issue: a paper three subjects claim gets
    skipped for a different reason in each, and a hatch without a subject would exempt all three.
    `motivo` is required — a hatch that turns the finding off and leaves nothing in its place is
    exactly what `--reason` exists to prevent.

    ⛔ #256 — this field was parsed and its result consumed by nobody: the lint read it inside the
    `reclamos - declaradas` branch, which the stub seeding of #188 leaves ALWAYS empty (one
    `vistas[]` entry per claim). Measured on a real corpus: 0 of 138 notes could reach it. The hatch
    now decides over the DATELESS view, which is where a pending claim actually lives.

    @inv INV-145"""
    v = meta.get("no_vista")
    if v is None:
        return []
    if not isinstance(v, list) or any(not isinstance(x, dict) for x in v):
        raise VistasError(_no_vista_error(
            entry, "`no_vista` no acepta un motivo suelto ni una lista de strings: sin `sujeto` la "
                   "escotilla no dice de QUÉ reclamo se declara, y en un paper compartido eximiría "
                   "a todos"))
    out = []
    for x in v:
        sujeto, motivo = str(x.get("sujeto") or "").strip(), str(x.get("motivo") or "").strip()
        faltan = [k for k, val in (("sujeto", sujeto), ("motivo", motivo)) if not val]
        if faltan:
            raise VistasError(_no_vista_error(
                entry, f"a una entrada de `no_vista` le falta {', '.join(faltan)}"))
        out.append(dict(x, sujeto=sujeto, motivo=motivo))
    return out


def _no_vista_error(entry: str, motivo: str) -> str:
    return (f"'{entry}': {motivo}. Forma canónica:\n\nno_vista:\n  - sujeto: <el mismo nombre "
            f"que usan stars[]/thesis_links[]>\n    motivo: <por qué este reclamo no se leyó>\n")


def _vistas_error(entry: str, sujetos: list, motivo: str) -> str:
    """The detector's message, with the canonical form already written out to paste."""
    ejemplo = "\n".join(
        f"  - sujeto: {s}\n    tipo: {VISTA_TIPOS[0]}          # {' | '.join(VISTA_TIPOS)}\n"
        f"    fecha: AAAA-MM-DD\n    txt: <slug del .txt que se leyó>\n"
        f"    lente: [<facetas vigentes al leer>]"
        for s in (sujetos or ["<sujeto>"]))
    return (f"'{entry}': {motivo}. Forma canónica:\n\nvistas:\n{ejemplo}\n")


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

#: #272 · qué campos del ground-truth el frontmatter de la ficha PUBLICA. La cabecera prometía
#: autoridad NEA sobre cuatro que la nota no tiene dónde mostrar (`Vmag`, `ra_deg`, `dec_deg` y
#: —hasta que entró al schema— `mass_msun`): el consumidor leía la promesa, bajaba al frontmatter y
#: no los encontraba, en la línea que existe justamente para que el artefacto viaje solo.
CAMPO_EN_FRONTMATTER = frozenset({"spectral_type", "teff_K", "dist_pc", "st_rotp_days", "mass_msun"})


def theme_axes(meta) -> list | None:
    """The theme's own reading axes (`ejes:` in themes.yaml), or `None` when it does not declare
    them (#307). `[]` is a DECLARED decision: do not ask for axes.

    ⛔ D-26 made a method theme classify with its **own facet** because the global lens is
    *"actively harmful"* there; #254 then derived the extractor's reading axes from the lens — the
    **global** one. Nobody did the symmetric half, so a statistics theme was asked the axes of an
    astronomy vault. Measured over 32 extractions of one method theme: `rv`, `activity`, `planet`
    and `discovery` came back populated in **7 of 32** (the same 7: its only astro sources), while
    the axes the theme actually needed —identifiability, heteroscedasticity per epoch and per
    channel, what whitening guarantees— were **never asked**, so they came back scattered across
    `aporte` with no key to compare them by. That is #254's own argument one level down: a key the
    view does not carry is indistinguishable from *"somebody looked and there is nothing"*.

    Three states, like the rest of the lens (D-43): absent → the global facets; declared → those;
    declared empty → no axes, on purpose.

    @inv INV-146"""
    m = as_map(meta)
    if "ejes" not in m:
        return None
    v = m.get("ejes")
    if v is None:
        return []
    return [str(e).strip() for e in as_list(v) if str(e).strip()]


def pdf_slug(stem: str, prefiere: str | None = None) -> str | None:
    """Which slug actually holds this paper's PDF, or `None` when no copy exists (#305).

    ⛔ **One resolution, two halves of #207.** The extractor's prompt asked
    `(PDFS / slug / f"{bib}.pdf").exists()` —only the subject's slug— while the harvester's
    `pdf_on_disk` globbed `**/`, and the harvester's docstring says why its criterion is the right
    one: *"is there a PDF of this bibcode under ANY slug? truth of disk"*. So the prompt told the
    extractor *"there is no PDF, declare `fuente: abstract`"* about a paper that IS on disk under
    another slug, and the harvester accepted it because `abstract` is always a legal value: #207
    inverted — instead of catching a degraded reading, the framework produced one.

    It bites exactly the retro-tagged population, which is by definition the paper that was already
    in the corpus under **another** subject. Measured on a real theme: 7 of 31, the founding core,
    two of them 500+ page books whose `alcance` says to read by index and cite by page — unreadable
    from an abstract.

    Declared precedence, same as `artefacto_en_otro_slug`: the preferred slug first (that is where
    the chain put it), then the lexicographically smallest, so the answer does not depend on ingest
    order."""
    if prefiere and (PDFS / prefiere / f"{stem}.pdf").exists():
        return prefiere
    otros = sorted(PDFS.glob(f"*/{stem}.pdf")) if PDFS.exists() else []
    return otros[0].parent.name if otros else None


def artefacto_en_otro_slug(base: Path, slug: str, stem: str, sufijo: str):
    """El mismo artefacto (`<stem><sufijo>`) ya bajado bajo OTRO slug, o `None` (D-18).

    Un paper relevante para dos sujetos se bajaba dos veces — medido: 33 copias en la instancia
    real. El archivo es idéntico (mismo bibcode), y la red es a la vez el recurso caro y el que
    puede fallar: re-bajarlo no agrega nada y agrega un modo de falla. Se devuelve la ruta para
    que el llamador copie (no symlink: `raw/` viaja en git-lfs y un enlace roto es peor que una
    copia).

    Determinista: si hay varias, gana la primera en orden alfabético de slug.

    ⛔ AUD-161 — un PDF se valida por su **magic `%PDF`** antes de proponerlo. Los dos fetchers
    copiaban lo que hubiera bajo el otro slug sin mirarlo, así que un archivo truncado por un corte
    —el caso exacto que `--force` existe para reparar— se **propagaba** al slug nuevo y encima
    salía de `pendientes`: el paper quedaba "bajado" con un PDF que no se puede abrir, y la verdad
    de disco (que es la regla del framework acá) pasaba a mentir en dos lugares en vez de uno."""
    for candidato in sorted(base.glob(f"*/{stem}{sufijo}")):
        if candidato.parent.name == slug:
            continue
        if sufijo == ".pdf":
            try:
                if not candidato.open("rb").read(5).startswith(b"%PDF"):
                    print_seguro(f"  ⚠ {candidato} no empieza con `%PDF` (¿truncado?) — NO lo copio "
                                 f"a `{slug}`: propagar un PDF roto lo deja 'bajado' y sin abrir",
                                 file=sys.stderr)
                    continue
            except OSError:
                continue
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


def save_barrido(slug: str, barrido: dict) -> None:
    """APPENDEA una corrida del barrido full-text a `barridos: []` (#88).

    `--sweep` era un **preview puro de stdout**: cuando la terminal scrollea no queda nada. Es el
    mismo modo de falla que #55 cerró para el triage —el aviso vivía sólo en la corrida— y acá pesa
    más, porque el barrido es **el único camino** para el punto ciego de la query directa: los
    surveys de muestra grande que TABULAN la estrella sin nombrarla en el abstract y que además no
    están en el grafo de citas. Sin registro no se sabe si esa segunda red se tendió.

    ⚠ Se registra **también cuando no encontró nada**: un barrido vacío dice que la red se tendió y
    volvió sin nada, que no es lo mismo que no haberlo corrido — la distinción de D-43. Acumulativo
    como `busquedas` (D-28), y no toca `decisiones`.

    ⛔ #251 — «acumulativo como `busquedas`» era, hasta 1.97.0, sólo la parte de appendear: la
    entrada se guardaba **tal cual**, sin el `n_nuevos`/`n_ya_estaban` que ES D-28 («traje 40» vs
    «traje 40 y 38 ya estaban»). Medido en `hd_40307`: tres entradas idénticas —misma fecha, misma
    query, los mismos 83 bibcodes— declarando las tres `n_nuevos: 83`, o sea 249 hallazgos donde
    hubo 83. El `n_nuevos` que escribía el llamador era además **redundante con `len(bibcodes)`**,
    así que redefinirlo con la semántica de D-28 no pierde información.

    @inv INV-118"""
    data = load_registro(slug)
    data.setdefault("slug", slug)
    previos = [b for b in as_list(data.get("barridos")) if isinstance(b, dict)]
    conocidos: set = set()
    for b in previos:
        conocidos.update(as_list(b.get("bibcodes")))
    entrada = dict(barrido)
    bibs = as_list(entrada.get("bibcodes"))
    entrada["n_nuevos"] = len([b for b in bibs if b not in conocidos])
    entrada["n_ya_estaban"] = len([b for b in bibs if b in conocidos])
    data["barridos"] = previos + [entrada]
    save_registro(slug, data)


def save_descubrimiento(slug: str, entrada: dict) -> None:
    """APPENDEA una corrida de la cascada multi-backend a `descubrimientos: []` (#77).

    Un tema off-ADS no tenía cómo responder «sobre qué universo afirma esta nota y con qué se
    buscó»: la cascada imprimía y no escribía. Lo que se guarda incluye la **cobertura por
    backend** con sus tres estados —corrió con N, FALLÓ, NO CORRIÓ y por qué—, no un total: un
    backend caído y uno que corrió sin traer nada se leen igual en una suma.

    Acumulativo, y no toca `decisiones` ni `busquedas`.  @inv INV-121"""
    data = load_registro(slug)
    data.setdefault("slug", slug)
    data["descubrimientos"] = [d for d in as_list(data.get("descubrimientos"))
                               if isinstance(d, dict)] + [entrada]
    save_registro(slug, data)


# ── El carril del `aparente` de `find-contradictions` (#63) ──────────────────────────────────────
#
# El fan-out de `find-contradictions` gasta un subagente por par y devuelve tres veredictos. `real`
# tiene carril —se convierte en `disputes[]` de la nota, que el consumidor lee y el lint vigila—;
# `aparente` y `no-concluyente` NO tenían ninguno: el skill los reportaba al chat y ahí morían. La
# consecuencia es doble y las dos son caras: cada auditoría vuelve a pagar el mismo par para
# reconstruir la misma conclusión, y el motivo por el que aquel desacuerdo no era desacuerdo
# —distinto régimen, distinta definición, distinta época— no lo tiene nadie. Es el mismo agujero
# que #51 cerró para el triage (el juicio de descarte vivía en `build/`, gitignored) y #81 para las
# fuentes declaradas: de los cuadrantes de la curación, éste era el que faltaba del lado de la
# REVISIÓN. Por eso vive en el registro versionado, que es el artefacto que viaja.

# Vocabulario CERRADO, por el mismo motivo que `role` (#73) y `status` (D-37): el único consumidor
# de este campo es el filtro del barrido, y un valor fuera de la lista lo deja mudo. `real` NO está
# acá a propósito — ver `save_no_disputa`.
VEREDICTOS_NO_DISPUTA = ("aparente", "no-concluyente")


def par_key(bib_a: str, bib_b: str, eje: str) -> str:
    """Clave SIMÉTRICA del par juzgado: `par_key(A, B, eje) == par_key(B, A, eje)`.

    El barrido no controla en qué orden le tocan A y B —salen del `glob` de notas—, así que una
    clave orientada haría que el mismo par juzgado al revés no matchee: la persistencia quedaría
    decorativa, que es peor que no tenerla (parece que hay red y no la hay).

    Y **distingue el eje**: los mismos dos papers pueden coincidir en `P_rot` y discrepar en `K`.
    Una clave sólo por bibcodes silenciaría el segundo desacuerdo con el juicio del primero — un
    falso «ya lo miramos» sobre algo que nadie miró, que es el falso limpio de D-43.

    ⚠ AUD-180 / INV-125 — las tres partes se **escapan** antes de unirlas. El `eje` es texto libre
    (`b.K`, `existencia de la señal c`), así que un `::` adentro corría el separador y hacía que dos
    pares distintos colapsaran en la misma clave: exactamente el falso «ya lo miramos» que el
    docstring de arriba dice evitar, por la puerta del formato en vez de por la del eje."""
    a, b = sorted((str(bib_a), str(bib_b)))
    return "::".join(_par_esc(x) for x in (a, b, str(eje)))


def _par_esc(x: str) -> str:
    """`x` with no raw `:` or `%`, so that the `::` of `par_key` is a real separator."""
    return x.replace("%", "%25").replace(":", "%3A")


def _par_de(entrada: dict) -> str:
    """La clave de una entrada de `no_disputas`, recalculada desde `bibcodes` + `eje` si hace falta.

    Se re-deriva en vez de confiar en el campo `par` guardado porque el registro es un archivo que
    el framework instruye editar a mano: un `par` escrito a ojo con los bibcodes al revés dejaría
    la entrada fuera del índice sin que nadie se entere. Si la entrada no trae dos bibcodes, se cae
    al `par` textual, que es lo único que hay."""
    bibs = [b for b in as_list(entrada.get("bibcodes")) if b]
    if len(bibs) == 2:
        return par_key(bibs[0], bibs[1], entrada.get("eje") or "")
    return str(entrada.get("par") or "")


def load_no_disputas(slug: str) -> dict:
    """Los pares ya juzgados como NO-disputa, indexados por `par_key` — `{}` si nunca se auditó.

    Devuelve un **índice**, no la lista: el consumidor es el filtro del barrido, que pregunta
    «¿este par ya se juzgó?» una vez por par, dentro de un bucle que ya es O(N²) sobre el corpus.

    Ante el mismo par juzgado dos veces gana **el último** (A6): el registro es historial
    acumulativo —un par puede volver a juzgarse cuando cambió la evidencia— y el juicio viejo no se
    borra, queda en la lista para que la historia sea reconstruible."""
    idx: dict = {}
    malas = 0
    for entrada in as_list(load_registro(slug).get("no_disputas")):
        if not isinstance(entrada, dict) or not (clave := _par_de(entrada)):
            # AUD-180 / INV-125 — esto era un `continue` MUDO. El registro se edita a mano, así que
            # una entrada rota (o sin `bibcodes` ni `par`) es alcanzable, y descartarla en silencio
            # deja el par fuera del índice: el barrido lo vuelve a proponer **sin el motivo** por el
            # que alguien ya lo había juzgado no-disputa. Es el bug de #51 en el otro registro.
            malas += 1
            continue
        idx[clave] = entrada
    if malas:
        print_seguro(f"  ⚠ {malas} entrada(s) de `no_disputas` de `{slug}` con forma inválida (sin "
                     f"`bibcodes`/`par`, o no son un mapa) → no entran al índice y esos pares se "
                     f"van a re-proponer sin su motivo; arreglá {registro_path(slug)}",
                     file=sys.stderr)
    return idx


def save_no_disputa(slug: str, entrada: dict) -> None:
    """APPENDEA un par juzgado NO-disputa a `no_disputas: []`. Acumulativo, atómico, sin pisar nada.

    Dos abortos, y ninguno es formalismo:

    · **`motivo` vacío aborta.** Mismo criterio que el `--reason` obligatorio del triage
      (#51/#111): en seis meses lo que sirve es el motivo, no la categoría. Un `aparente` pelado
      tira la única información no regenerable —por qué el desacuerdo no era desacuerdo— y encima
      **bloquea el par para siempre**: el barrido lo saltea y ya nadie revisa el juicio. Peor que no
      persistirlo, que al menos se vuelve a mirar.
    · **`real` aborta.** Su carril es `disputes[]` de la nota, que es otro artefacto y otro dueño
      (contenido de la bóveda que el usuario aprobó, contra bitácora de la revisión). Dejarlo entrar
      acá lo **entierra**: el barrido siguiente lo saltea por «ya juzgado» y la disputa real nunca
      llega a la bóveda.

    Se valida ANTES de tocar el registro: un abort que igual escribe deja el archivo con la entrada
    que acaba de rechazar. La `fecha` la estampa esta función si el llamador no la trae (A3), como
    `save_sintesis` y `save_extraccion`; si la trae, se respeta.

    No toca `decisiones`, `busquedas`, `barridos` ni `descubrimientos`: el registro tiene dueños
    distintos por sección y es el único artefacto no regenerable de la bóveda (INV-53).

    @inv INV-125"""
    if not isinstance(entrada, dict):
        raise RuntimeError("una entrada de `no_disputas` tiene que ser un mapa")
    veredicto = (entrada.get("veredicto") or "").strip()
    if veredicto not in VEREDICTOS_NO_DISPUTA:
        raise RuntimeError(
            f"veredicto {veredicto!r} fuera del vocabulario de `no_disputas` "
            f"({' | '.join(VEREDICTOS_NO_DISPUTA)}). Un `real` NO va acá: se taguea como "
            "`disputes[]` en la nota, que es el carril que el consumidor lee y el lint vigila.")
    motivo = (entrada.get("motivo") or "").strip()
    if not motivo:
        raise RuntimeError(
            "una entrada de `no_disputas` sin `motivo` no se persiste: bloquearía el par en el "
            "barrido sin dejar por qué (mismo criterio que el `--reason` del triage).")

    nueva = dict(entrada)
    nueva["veredicto"] = veredicto
    nueva["motivo"] = motivo
    nueva["par"] = _par_de(nueva) or nueva.get("par")
    nueva.setdefault("fecha", _dt.date.today().isoformat())

    data = load_registro(slug)
    data.setdefault("slug", slug)
    data["no_disputas"] = [d for d in as_list(data.get("no_disputas"))
                           if isinstance(d, dict)] + [nueva]
    save_registro(slug, data)


def save_captura_web(slug: str, entrada: dict) -> None:
    """APPEND to `capturas_web: []` the capture a re-capture is about to replace.  @inv INV-30

    ⛔ INV-30 — `fetch_web --force` re-fetches the page and **overwrites** the previous snapshot, so
    the earlier capture vanished without a trace, in the one lane of the vault where the source IS
    the capture (there is no PDF behind it to re-extract from). The invariant asks that re-capturing
    «not destroy the previous one without leaving a trace», and what is stored is the **trace**, not
    the file: date, URL and `sha256` of the replaced `.txt`.

    Why the file is not versioned (decided with the user, 2026-08-28): a `<key>.<date>.txt` next to
    it would enter EVERY `grep` over the corpus — `query-corpus`, `test-hypothesis`, the alias
    retro-tag, the hypothesis scope count — and the lint's population, so `verify-citations` could
    end up quoting an obsolete capture. Losing the old text is a real cost and a bounded one: what
    the vault **asserts** about that source stays anchored by hash (D-20), so a pair verified against
    the old capture expires by itself when the file changes."""
    data = load_registro(slug)
    data.setdefault("slug", slug)
    data["capturas_web"] = [c for c in as_list(data.get("capturas_web"))
                            if isinstance(c, dict)] + [entrada]
    save_registro(slug, data)


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
    # D-28: la clave vieja `busqueda:` (mapa, UNA corrida) es el schema pre-1.26. El lector nuevo
    # no la entiende y el lint la bloquea — pero **borrarla destruye la única corrida que ese
    # registro documenta**, y el registro es el único artefacto no regenerable de la bóveda
    # (INV-53: "escribir un registro nuevo no borra el juicio ya registrado, y la historia es
    # reconstruible"). Se PLIEGA al frente de la lista, marcada, en vez de perderse: así la
    # migración no cuesta información y el universo acumulado la puede contar.
    # ⚠ AUD-172 / INV-89 — el plegado va ANTES de computar `conocidos`. Al revés, los bibcodes de la
    # corrida migrada no contaban como conocidos y la primera corrida post-migración reportaba como
    # `n_nuevos` todo lo que ya estaba: justo el número que D-28 introdujo para distinguir «traje
    # 40» de «traje 40 y 38 ya estaban», mintiendo en la única corrida donde importa.
    vieja = data.pop("busqueda", None)
    if isinstance(vieja, dict) and not previas:
        vieja = {**vieja, "schema": "pre-D-28 (plegada al migrar; una sola corrida)"}
        previas = [vieja]
    conocidos: set = set()
    for b in previas:
        conocidos.update(as_list(b.get("bibcodes")))
    entrada = dict(busqueda)
    bibs = as_list(entrada.get("bibcodes"))
    if bibs:
        entrada["n_nuevos"] = len([b for b in bibs if b not in conocidos])
        entrada["n_ya_estaban"] = len([b for b in bibs if b in conocidos])
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
    unknown = [t for t in require if t not in topic_names]
    if unknown:
        raise RuntimeError(
            f"vault/config/objective.yaml: relevance.require nombra facetas ausentes de "
            f"relevance.facets: {unknown}. Una faceta obligatoria que no existe filtraría TODO a "
            f"no-core en silencio."
        )
    # AUD-143 — `min_facets` no se validaba y es la otra mitad exacta del mismo argumento que
    # justifica el chequeo de `require`: un `min_facets: 99` sobre tres facetas deja TODO el corpus
    # no-core **en silencio**, y un `min_facets: 0` (o un string) hace core a todo. Falla ruidoso,
    # igual que arriba. `or 1` tapaba el 0 y el string: los dos son decisiones que alguien escribió.
    raw_min = rel.get("min_facets")
    if raw_min is None:
        min_facets = 1
    elif isinstance(raw_min, bool) or not isinstance(raw_min, int) or raw_min < 1:
        raise RuntimeError(
            f"vault/config/objective.yaml: relevance.min_facets tiene que ser un entero ≥ 1 y es "
            f"{raw_min!r}. Un valor menor a 1 haría core a todo el corpus y uno inválido se leería "
            f"como el default."
        )
    else:
        min_facets = raw_min
    if topic_names and min_facets > len(topic_names):
        raise RuntimeError(
            f"vault/config/objective.yaml: relevance.min_facets = {min_facets} y sólo hay "
            f"{len(topic_names)} faceta(s) declarada(s) — ningún paper puede alcanzar ese mínimo, "
            f"así que TODO el corpus quedaría no-core en silencio."
        )
    # Y la faceta VACÍA es el simétrico: `re.search("", texto)` matchea siempre, así que una regex
    # en blanco (un `rv:` sin valor en el YAML) hace core al corpus entero, también en silencio.
    vacias = sorted(n for n, pat in as_map(rel.get("facets")).items()
                    if not str(pat if pat is not None else "").strip())
    if vacias:
        raise RuntimeError(
            f"vault/config/objective.yaml: relevance.facets con regex vacía: {vacias}. Una regex "
            f"en blanco matchea SIEMPRE — haría core a todo el corpus."
        )
    rotas = []
    for nombre, pat in as_map(rel.get("facets")).items():
        try:
            re.compile(str(pat))
        except re.error as exc:
            rotas.append(f"{nombre} ({exc})")
    if rotas:
        raise RuntimeError(
            f"vault/config/objective.yaml: relevance.facets que no compilan: {'; '.join(rotas)}. "
            f"Una faceta que no compila no matchea nunca, o sea que se lee como «este paper no "
            f"habla del tema» sobre un paper que nadie clasificó."
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


def puerta2_cruces(slug: str) -> tuple[list, list, int]:
    """Quiénes cruzarían el umbral de la puerta 2 si se re-clasificara hoy: `(entran, salen, sin_dato)`.

    POR QUÉ EXISTE (#106). La puerta 2 admite un paper por `citation_count`, que es metadata del
    paper —así que INV-24 se sostiene: el veredicto sigue siendo función de `(metadata, lente)` y el
    conteo vive en el frontmatter, o sea que es re-derivable offline—. Lo que la distingue es que
    esa metadata **cambia sola**: la función es estable y su entrada deriva. Era la única
    dependencia del mundo del framework sin detector; las otras cinco (retracciones, correcciones,
    versiones, snapshot web, ground-truth) tienen el suyo en `sweep_external`, y en ninguna la
    respuesta fue congelar el dato: detectar, reportar, no aplicar solo.

    **Alcance declarado, y es la mitad del problema:** esto compara el umbral VIGENTE de
    `themes.yaml` contra el conteo que la nota tiene guardado, así que ve *"editaste el umbral"* y
    **no** *"el mundo se movió"*. Lo segundo necesita red y vive en `sweep_external.sweep_citas`.
    Devolver `sin_dato` (notas sin `citation_count`) es parte del contrato: un `entran: 0` sobre
    notas que nadie pudo evaluar se lee como "no cambia nada"."""
    # @inv INV-104
    try:
        _, meta = theme_by_slug(slug)
    except (KeyError, RuntimeError):
        return [], [], 0
    # AUD-142: la forma del umbral la decide `gate2_threshold`, la misma que usa el clasificador.
    # Acá se aceptaba `(int, float)` y allá sólo `int`, así que un `30000.0` dejaba la puerta
    # abierta para este detector y cerrada para el que decide qué es core.
    umbral, _mal = gate2_threshold(meta)
    if umbral is None:
        return [], [], 0            # no declarada, o declarada con forma inválida (lo dice el lint)
    guardado = None
    for b in load_busquedas(slug):
        regla = as_map(as_map(b.get("lente")).get("regla_tema"))
        if "umbral" in regla:
            guardado = regla.get("umbral")
    if guardado == umbral:
        return [], [], 0            # el caso normal, y es gratis
    entran, salen, sin_dato = [], [], 0
    for stem, fm, _text in notes_of_subject(slug):
        n = fm.get("citation_count")
        if not isinstance(n, (int, float)):
            sin_dato += 1
            continue
        era = isinstance(guardado, (int, float)) and n >= guardado
        ahora = n >= umbral
        if ahora and not era:
            entran.append((stem, n))
        elif era and not ahora:
            salen.append((stem, n))
    return sorted(entran), sorted(salen), sin_dato


def lens_current(slug: str | None = None) -> dict:
    """La lente VIGENTE en `objective.yaml`, **releída en cada llamada**. El lint corre en un
    proceso que importó `query_ads` antes de saber qué bóveda va a auditar: comparar contra las
    constantes del import haría que toda lente se viera igual a sí misma — el chequeo entero
    devolvería un cero que nadie midió.

    Con `slug` de un TEMA suma su `regla_tema` (#106), y hace falta para que la comparación sea
    entre iguales: el registro de un tema **sí** la guarda, así que sin esto `lens_delta` veía
    "estaba y ya no" y reportaba `facet` cambiada y `fundacional_min_citas → sin declarar` sobre un
    tema que las declara las dos. Medido en una bóveda real, y **los tests unitarios no lo vieron**
    porque cubrían "ninguno de los dos lados la trae", no "sólo uno"."""
    lente = lens_shape(as_map(load_objective().get("relevance")))
    if slug:
        try:
            _, tmeta = theme_by_slug(slug)
        except (KeyError, RuntimeError):
            return lente                      # una estrella no tiene regla de tema: no es un cambio
        regla = {"facet": as_map(tmeta).get("facet")}
        # #295 — espeja `query_ads.lens_used`: el `fq` propio del tema es la mitad MÁS restrictiva
        # de su lente. Se resuelve acá sin importar `query_ads` (arrastraría `requests` al lint):
        # es la misma cascada de tres estados, y el caso "declarado null" no se lee como ausente.
        if "search_fq" in as_map(tmeta):
            v = as_map(tmeta).get("search_fq")
            regla["search_fq"] = None if v in (None, "") else v
        if "fundacional_min_citas" in as_map(tmeta):
            regla["umbral"] = gate2_threshold(tmeta)[0]
        lente["regla_tema"] = regla
    return lente


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
    # Regla del tema (#106): la faceta propia y el umbral de la puerta 2 mueven el corte igual que
    # una faceta global, y hasta ahora no se comparaban — un tema podía quedar clasificado con un
    # umbral que ya nadie usa sin que nada lo dijera. Se comparan sólo si ALGUNA de las dos lentes
    # la trae: un sujeto que es estrella no tiene regla de tema y su ausencia no es un cambio.
    ta, tb = as_map(stored.get("regla_tema")), as_map(current.get("regla_tema"))
    if ta or tb:
        if ta.get("facet") != tb.get("facet"):
            delta.append("`facet` del tema: regex cambiada")
        # `in`, no truthiness: pasar de "sin declarar" (la puerta NO abre) a `0` (abre para todos)
        # es el cambio más grande que este campo admite, y con `or None` los dos se leían igual.
        # #295 — mismo criterio de presencia: pasar de "hereda el global" a `search_fq: null`
        # cambia el universo entero del tema, y con `or None` los dos se leerían igual.
        fa_, fb_ = ("search_fq" in ta, ta.get("search_fq")), ("search_fq" in tb, tb.get("search_fq"))
        if fa_ != fb_:
            def _fmt_fq(par):
                return (str(par[1]) if par[1] is not None else "null (no acota)") if par[0] \
                    else "sin declarar (hereda el objetivo)"
            delta.append(f"`search_fq` del tema {_fmt_fq(fa_)} → {_fmt_fq(fb_)}")
        ua, ub = ("umbral" in ta, ta.get("umbral")), ("umbral" in tb, tb.get("umbral"))
        if ua != ub:
            def _fmt(par):
                return str(par[1]) if par[0] else "sin declarar (puerta 2 cerrada)"
            delta.append(f"fundacional_min_citas {_fmt(ua)} → {_fmt(ub)}")
    return delta


# Prefijos de delta que el diff offline NO puede evaluar re-clasificando notas:
#   · `noise_doctypes` — la nota de paper no guarda `doctype`.
#   · `fundacional_min_citas` — es la puerta 2, y NO es un cambio textual: `lens_diff_offline`
#     re-clasifica con la lente GLOBAL, así que sobre un tema de método devolvía "saldrían los 17
#     papers del tema" —que es cierto de la lente global y no tiene NADA que ver con el umbral que
#     se movió—. Su diff propio es `puerta2_cruces`, que el lint reporta aparte.
_DELTA_NO_TEXTUAL = ("noise_doctypes ", "fundacional_min_citas ")


def lens_textual_changed(delta: list[str]) -> bool:
    """¿El delta toca la mitad que una nota PUEDE evaluar re-clasificando su texto?

    Los cambios que no la tocan tienen que quedar afuera o el reporte **atribuye mal**: dice
    "saldrían N" sobre una comparación que no es la que cambió, y un mapa que atribuye mal es peor
    que uno vacío (regla de método #4)."""
    return any(not d.startswith(_DELTA_NO_TEXTUAL) for d in delta)


_FACETAS_ROTAS: set = set()   # AUD-163: para avisar una sola vez por patrón


def lens_core_text(lens: dict, text: str) -> bool:
    """¿`text` es core bajo `lens`, por la mitad TEXTUAL de la regla? Espeja la precedencia de
    `exclusion_reason` (sin tópico → require → min_facets) salteando el doctype, que no está en la
    nota. Compila las regex de la lente GUARDADA, que puede tener facetas que ya no existen."""
    facets = []
    for name, pat in as_map(lens.get("facets")).items():
        try:
            if re.search(pat, text, re.I):
                facets.append(name)
        except (re.error, TypeError) as exc:
            # AUD-163 — esto era un `continue` mudo, y «no compila» se contaba igual que «no
            # matchea»: el diff de lente devolvía un veredicto sobre una faceta que nadie evaluó.
            # No revienta (la lente GUARDADA puede traer facetas viejas y este chequeo no puede
            # volverse él mismo un falso rojo), pero lo dice — una sola vez por patrón.
            if (name, str(pat)) not in _FACETAS_ROTAS:
                _FACETAS_ROTAS.add((name, str(pat)))
                print_seguro(f"  ⚠ faceta `{name}` de la lente guardada no compila ({exc}) — no "
                             f"clasifica: se cuenta como «no matchea», que NO es lo mismo",
                             file=sys.stderr)
            continue
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
    if abstract == ABSTRACT_PLACEHOLDER:
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
    # AUD-144 — sólo miraba `star_by_slug`, así que en un TEMA el `extra_core` no se excluía y el
    # diff volvía a proponer «saldrían» para siempre lo que el usuario ya decidió meter a mano. Y
    # los temas son justo donde `extra_core` se usa más: en el modo off-ADS y en la mitad ADS de un
    # tema mixto es la vía normal de entrada. Una categoría que repite lo ya resuelto se vuelve
    # ruido y se deja de mirar — el mismo argumento por el que #112 la respeta.
    extra: set = set()
    for lookup in (star_by_slug, theme_by_slug):
        try:
            _, meta = lookup(slug)
        except (KeyError, RuntimeError):
            continue
        extra |= {str(e.get("bibcode") if isinstance(e, dict) else e)
                  for e in listify_curado(as_map(meta).get("extra_core"), "extra_core")}
    lens = lens_current(slug)
    # #112: un paper EXCLUIDO del sujeto por decisión no puede volver a proponerse como "entra" en
    # cada cambio de lente — la decisión ya se tomó, con motivo y fecha. Sin esto, el diff repite
    # para siempre lo que el usuario ya sacó, y la categoría se vuelve ruido que se deja de mirar.
    excluidos = set(dropped_from_subject(slug))
    entran, salen = [], []
    con_nota = set()
    for stem, fm, text in notes_of_subject(slug):
        con_nota.add((fm.get("bibcode") or stem))
        if (fm.get("bibcode") or stem) in excluidos:
            continue
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


CADENA_SIN_TRAZA = "«el registro no tiene `cadena`»"


def cadena_cortada(slug: str, canonica=CADENA_ESTRELLA) -> str | None:
    """First step of `canonica` missing from the registro, or `None` when they all ran.

    It names the step rather than counting them: "it stopped at `fetch_ground_truth`" is
    actionable, "4 steps missing" is not.

    ⛔ **Three states, three values** (AUD-149 / INV-139). A registro with no `cadena` at all — a
    subject older than D-57, or a chain that never stamped anything — used to return `None`, the
    very value that means *«every step ran»*: the degraded case read as the good one and the
    subject left the check through the green door. It now returns `CADENA_SIN_TRAZA`, which the
    lint reports as *no consta* — the D-43 doctrine that keeps «measured, and it is zero» apart
    from «could not measure»."""
    corridos = {p.get("paso") for p in load_cadena(slug)}
    if not corridos:
        return CADENA_SIN_TRAZA
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
