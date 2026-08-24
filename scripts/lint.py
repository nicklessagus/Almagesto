"""Lint de la wiki — chequeo de salud (operación del patrón LLM Wiki).

Uso:
    python scripts/lint.py            # imprime resumen y escribe outputs/lint-<fecha>.md

Detecta: wikilinks rotos (página faltante), **frontmatter no parseable o con forma inválida**
(nota que empieza con `---` pero cuyo YAML no parsea, o un campo que el schema declara lista escrito
como escalar → evade en silencio los chequeos por elemento de su tipo; bloqueante),
**papers retractados** (flag `retracted` que estampa
`check_retractions.py` vía Crossref → acá se surface offline; bloqueante), **papers con corrección
publicada** (`corrections`: erratum/corrigendum/expression-of-concern, mismo origen — NO bloquea,
el paper sigue citable, pero un corrigendum cambia justo el valor extraído; backlog),
notas huérfanas (sin links entrantes),
contradicciones ground-truth ↔ ficha, **masa de ground-truth inconsistente** con la
m·sini implícita por K/P/e/M* (atrapa best-mass espurias de NEA), `thesis_links` sin
página destino (tag que no matchea ninguna nota concepto/hipótesis → no acumula),
**fuga de implementación** (material de implementación/código no bibliográfico que se
filtró al vault; frontera dura, regla #0 de CLAUDE.md; WARN no bloqueante), **objetivo sin
instanciar** (objective.name sigue siendo el default del template → la bóveda clasifica "core"
con la regex del ejemplo; WARN), **áreas de concepts/ fuera
de `concept_areas`** (subcarpeta de concepts/ no declarada en objective.yaml → posible typo/carpeta
fantasma; WARN), **PDF ↔ disco** (drift: el campo `pdf` de un paper no refleja el PDF bajado — sin linkear
o puntero a archivo inexistente; WARN) y su hermano **cuerpo ↔ frontmatter** (#48: el link `[📄 PDF]`
de la cabecera no refleja el `pdf` del frontmatter —falta, sobra, o la cabecera está fuera del
contrato de `stamp_pdf_link` y el re-estampado la saltea en silencio—; WARN), **fuentes pendientes** (`pending_source` en una nota de
paper: la fuente no se pudo obtener —paywall/escaneo/mojibake— y está derivada al usuario;
precondición como las citas no verificables), **fulltext ilegible** (un `.txt` de `vault/raw/fulltext/`
que no pasa el umbral determinista de legibilidad de `extract_fulltext.is_legible` → mojibake,
escaneo cuya única capa de texto es la marca de agua del bibcode (#50) o
escaneo sin capa de texto: existe pero no sirve para grep ni verify), **citas no verificables** (bibcode
citado en query/concepto/hipótesis sin su `.txt` en `vault/raw/fulltext/` → no se puede chequear claim↔fuente
con el skill `verify-citations`), **cobertura** (concepto/hipótesis sin ninguna cita `[[bibcode]]` →
afirmaciones no chequeables; backlog), **cobertura de verificación** (query/concepto CON citas pero
SIN bloque `## Verificación de citas` → nunca pasó por verify-citations; backlog ALCE-adjacent),
**extraído pero no sintetizado** (#75: paper con `methods` poblado cuyo bibcode no aparece citado en
ninguna ficha/concepto → la extracción, que es el paso más caro, nunca llegó a la síntesis; se cierra
sintetizándolo o marcando `no_sintetizado: <motivo>` en la nota del paper; backlog),
**verificación stale** (la nota se editó DESPUÉS de la fecha de su bloque de verificación → las
afirmaciones nuevas nunca pasaron por el fan-out pero quedan bajo un encabezado que se lee como
vigente; backlog),
**triage pendiente** (candidatos del chaining en `build/<slug>/ads.json` que nadie juzgó todavía —
la compuerta #38 los deja sin bajar y el aviso vivía sólo en el stdout de la corrida; backlog),
**corpus truncado** (un `build/<slug>/ads.json` con `truncated` seteado → la query directa trajo
menos papers de los que ADS reporta: al sujeto le falta cola; ídem `truncated_glyph`, el superset
del rescate por glifo (#28/#43) cortado por citas ANTES del filtro; backlog). Esas dos categorías
NO dependen de `build/`: si el scratch no está (post-clone, otra máquina), caen al registro
VERSIONADO del sujeto (`vault/config/registro/<slug>.yaml`, #51/#64) y reportan ese snapshot **con
su fecha** — antes devolvían 0 sin mirar nada, un "limpio" que no significaba limpio. Y campos clave
incompletos (P_rot null, papers relevantes sin `methods`, `thesis_links` sin `bearing`).
No modifica nada: reporta para que el agente/usuario decida.

Exit code: 1 si alguna categoría BLOQUEANTE tiene hits (wikilinks rotos, frontmatter no parseable
o con forma inválida,
papers retractados, huérfanas, contradicciones
GT↔ficha, masa inconsistente, thesis_links/disputes colgantes, y los **restos de schemas viejos**
—`planets[].disputes[]`, `build/<slug>/triage.json`— que el lector ya no mira: el framework no lleva
capas de compatibilidad, así que lo viejo se detecta y se migra en vez de tolerarse — las que
CLAUDE.md exige "en 0");
0 si sólo hay WARN/backlog. Gateable en pre-commit/CI.
"""
from __future__ import annotations

import datetime as dt
import argparse
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

import lib_config as cfg
from extract_fulltext import is_legible      # umbral determinista de legibilidad (mismo que extract)
from fetch_ground_truth import msini_earth   # verificación de masa (m·sini implícita)
from make_notes import find_header_line      # contrato de la cabecera (mismo que stamp_pdf_link, #48)
from make_notes import GENERATOR_LINE        # ancla de la cabecera de fichas/concepts (#69)

LINK_RE = re.compile(r"\[\[([^\]\|#]+)")
# Frontera dura (regla #0 de CLAUDE.md): la bóveda es SÓLO bibliografía. Detecta material de
# implementación/código no bibliográfico que se filtró a una nota. WARN, no bloquea: son heurísticas de
# alta señal/bajo ruido; se saltan los blockquotes meta (frontera/alcance). Revisar a mano cada hit.
IMPL_LEAK_RE = [
    (re.compile(r"\bperilla\b", re.I), "perilla (dial de implementación)"),
    (re.compile(r"\bdial\b", re.I), "dial de implementación"),
    (re.compile(r"w_\{?j"), "pesos por orden w_j (parámetro de código)"),
    (re.compile(r"=\s*peso\("), "vector de mezcla peso(azul)/peso(rojo)"),
]
# targets que son texto de ejemplo/placeholder, no links reales
LINK_SKIP = {"..", "...", "link", "links", "wikilinks", "bibcode", "related-concept",
             "attention-mechanism", "rag"}
NON_ORPHAN = {"index", "log", "README"}  # navegación, no son huérfanos


split_fm = cfg.split_fm      # implementación única en lib_config (la comparte el dry-run de #40)


def fm_error(text: str) -> str | None:
    """Nota que EMPIEZA con `---` pero cuyo frontmatter no parsea (YAML roto — p. ej. un
    `title: RETRACTED: x` editado a mano sin comillas — o sin cierre `---`). split_fm devuelve
    {} y la nota EVADE en silencio todos los chequeos de su tipo (paper/star/concept), y
    check_retractions la saltea: peor que fallar. Devuelve el motivo, o None si está sana
    o no tiene frontmatter (index/log son prosa plana, legítimo).

    Delimita el frontmatter con `cfg.frontmatter_span` (por LÍNEA `---`, no por texto crudo,
    H-11): un `---` dentro de un escalar entrecomillado (`title: "... --- ..."`) es YAML válido y
    no puede cortar el bloque, o esta función reporta "YAML inválido" —categoría BLOQUEANTE—
    sobre un frontmatter que no tiene nada roto."""
    if not text.startswith("---"):
        return None
    span = cfg.frontmatter_span(text)
    if span is None:
        return "frontmatter sin cierre `---`"
    yaml_block, _body = span
    try:
        yaml.safe_load(yaml_block)
    except Exception as e:
        first = (str(e).splitlines() or [e.__class__.__name__])[0]
        return f"YAML inválido: {first[:80]}"
    return None


VERIF_HEAD_RE = re.compile(r"^##\s+Verificaci[oó]n de citas\b(.*)$", re.M)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def verify_block(text: str) -> tuple[bool, str | None]:
    """(¿la nota tiene bloque `## Verificación de citas`?, fecha de la verificación más reciente).

    La fecha vive en el encabezado por convención del skill (`## Verificación de citas
    (AAAA-MM-DD)`): es lo único que permite saber si lo verificado sigue vigente o quedó atrás de
    una edición posterior. Una nota puede acumular **varios** bloques (medido en una bóveda real:
    hasta 11 — pasadas sucesivas sobre secciones distintas), así que la vigencia la marca la fecha
    **máxima**, no la del primero: quedarse con el primero dejaría la nota stale para siempre por
    más que se re-verifique."""
    heads = VERIF_HEAD_RE.findall(text)
    if not heads:
        return False, None
    dates = [m.group(0) for m in (DATE_RE.search(h) for h in heads) if m]
    return True, max(dates) if dates else None


def git_out(*args: str) -> str | None:
    """stdout de un `git` corrido en la raíz del repo; None si no hay git, no es repo o falló.
    Fuera de un repo el chequeo de verificación stale **no se puede evaluar**. Desde el issue 0.3
    eso NO degrada a silencio (reportaba `stale (0)`, indistinguible de "todo al día"): cae en la
    categoría *no evaluado*, que cuenta para el exit (D-43 / INV-87). El resto del lint sigue
    corriendo — una bóveda puede vivir sin git —, pero no puede afirmar que las verificaciones
    están al día."""
    try:
        r = subprocess.run(["git", "-C", str(cfg.ROOT), "-c", "core.quotePath=false", *args],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def last_change_dates(paths: list[str]) -> dict[str, str]:
    """Fecha (AAAA-MM-DD) del último cambio de cada archivo, por git.

    Con ediciones **sin commitear** devuelve HOY: ese es el caso que importa —el lint corre como
    paso de cierre, ANTES del commit, así que comparar sólo contra `git log` no vería la edición
    que acaba de dejar el bloque atrasado. Si el archivo está limpio, la fecha del último commit
    que lo tocó. `{}` si no hay git (chequeo desactivado)."""
    if not paths or git_out("rev-parse", "--git-dir") is None:
        return {}
    root = cfg.ROOT.resolve()
    rel = {}
    for f in paths:
        try:
            rel[f] = Path(f).resolve().relative_to(root).as_posix()
        except ValueError:
            continue                       # fuera del repo → sin fecha, no se reporta
    dirty = set()
    for line in (git_out("status", "--porcelain", "--", *rel.values()) or "").splitlines():
        p = line[3:].strip()
        if " -> " in p:                    # rename: interesa el destino
            p = p.split(" -> ", 1)[1]
        dirty.add(p.strip('"'))
    today = dt.date.today().isoformat()
    dates = {}
    for f, r in rel.items():
        if r in dirty:                     # editado y sin commitear → cambió hoy
            dates[f] = today
            continue
        d = (git_out("log", "-1", "--format=%cs", "--", r) or "").strip()
        if d:                              # sin commits (archivo nuevo y limpio): sin fecha
            dates[f] = d
    return dates


def basename(p: str) -> str:
    return Path(p).name          # no splitear "/" a mano: glob devuelve separador nativo del OS


def in_dir(path: str, name: str) -> bool:
    """¿`name` es un componente de directorio del path? Por `Path.parts` (separador nativo, #33):
    los literales `"/queries/" in f` no matchean nunca en Windows (glob devuelve `\\`) y los
    chequeos de verificabilidad/cobertura desaparecían en silencio."""
    return name in Path(path).parts


def note_files() -> list:
    # incluye index.md/log.md (aportan links entrantes); se excluyen de orfandad por nombre.
    files = glob.glob(str(cfg.WIKI / "**" / "*.md"), recursive=True)
    files += glob.glob(str(cfg.RAW / "refs" / "*.md"))
    return files


BIBCODE_RE = re.compile(r"^\d{4}[A-Za-z]")   # heurística: target de link que parece bibcode

# Centinela para distinguir "el campo no está" de "está y no sirve" (#75): `fm.get(campo)` colapsa
# `ausente`, `null`, `""` y `false` en `None`, y esas cuatro exigen mensajes distintos.
_SIN_MARCA = object()

# ── disputas con posiciones explícitas (#71) ─────────────────────────────────
# El schema VIEJO (`planets[].disputes[]` con `field`/`ref`/`note`/`alt`) tenía el polo de verdad
# **hardcodeado en la forma**: el otro lado del desacuerdo era, implícitamente, el valor del
# frontmatter (NEA). Servía para paper↔NEA y **no podía expresar paper↔paper** — que es el caso
# NORMAL cuando NEA calla (K y e enmascarados, `P_rot` sin `st_rotp`), y encima `P_rot` es de la
# ESTRELLA, así que ni siquiera tenía dónde colgar. El schema nuevo sube `disputes` a nivel nota y
# hace explícitas las posiciones; la posición `{source: ground_truth}` es lo que distingue "hay
# autoridad" de "la bóveda genuinamente no sabe", que es la diferencia que el consumidor necesita ver.
# El schema viejo NO se lee: mantener las dos formas sería complejidad permanente en el lector para
# una compatibilidad que nadie necesita (decisión del usuario, 2026-08-22 — la bóveda que existe se
# migra con `python scripts/make_notes.py --migrate-disputes`, o se re-ingesta). Lo que sí se hace es
# **detectarlo y bloquear**: una disputa vieja que el lector ignora en silencio es peor que un error.
DISPUTE_SOURCES = ("ground_truth",)


def note_disputes(fm: dict) -> list:
    """Disputas de una nota como `(field, posiciones)`. **Un solo schema**: leer también el viejo
    sería cargar el lint con dos semánticas para siempre, y el schema viejo no sabe expresar la
    mitad de los casos. Lo que sí hace falta es que la presencia del viejo **grite** en vez de
    volverse invisible — eso lo reporta `legacy_disputes` como bloqueante, con el comando.

    Devuelve `(field, posiciones, motivos_de_forma)`. Dos detalles que costaron un bug cada uno:
    `field` se lee con `or ""` y **no** con el default de `.get` —la clave presente y **nula**
    (`field:` a secas, la forma normal de dejarla sin llenar) devuelve `None`, y `str(None)` es
    `"None"`, truthy: el chequeo bloqueante "disputa sin `field`" no disparaba—; y `posiciones`
    escalar se reporta en vez de llegar a un `len()` que voltea el lint (o a un string que se
    recorre carácter por carácter, un hallazgo por letra). `normalize_lists` no llega acá: sanea
    el primer nivel del frontmatter, y esto está anidado."""
    out = []
    for d in (fm.get("disputes") or []):
        if not isinstance(d, dict):
            continue                       # la forma de la lista ya la reportó normalize_lists
        campo = str(d.get("field") or "").strip()
        pos, motivos = d.get("posiciones"), []
        if pos is not None and not isinstance(pos, list):
            motivos.append(f"disputa `{campo or '?'}`: `posiciones` no es una lista (es "
                           f"{type(pos).__name__}) → no se puede leer ninguna posición")
            pos = []
        out.append((campo, pos or [], motivos))
    return out


# Campos que el schema declara **lista** (CLAUDE.md). `True` = lista de MAPAS.
# `role` no está: su contrato admite escalar o lista, y se valida aparte.
LIST_FIELDS = {"tags": False, "aliases": False, "stars": False, "topics": False, "methods": False,
               "thesis_links": False, "activity_indicators_expected": False,
               "planets": True, "disputes": True, "corrections": True}


def normalize_lists(fm: dict) -> list:
    """Deja una LISTA en cada campo que el schema declara lista y devuelve los motivos de las formas
    inválidas. Normalizar **una vez, al parsear** es lo que evita que cada lector tenga que
    defenderse por su cuenta: el lint es la compuerta de CI y ante un frontmatter raro tiene que
    **reportar**, no morirse — un escalar donde va una lista lo volteaba con un `TypeError`, y un
    escalar iterable (un string) se recorría **carácter por carácter**, inventando un hallazgo por
    letra. Medido con un fuzz de tipos sobre los campos documentados: 32 combinaciones lo volteaban.

    La nota no se "arregla": los elementos inservibles se sacan de la vista del lint y se reportan,
    que es la misma política que el resto de los chequeos de forma (#71)."""
    motivos = []
    for campo, de_mapas in LIST_FIELDS.items():
        v = fm.get(campo)
        if v is None or v == "" or v == []:
            continue
        if not isinstance(v, list):
            motivos.append(f"`{campo}` no es una lista (es {type(v).__name__}) → los chequeos por "
                           f"elemento de esta nota no corren")
            fm[campo] = []
            continue
        ok = [x for x in v if isinstance(x, dict)] if de_mapas else \
             [x for x in v if isinstance(x, (str, int, float, bool))]
        if len(ok) != len(v):
            que = "un mapa" if de_mapas else "un valor simple"
            motivos.append(f"{len(v) - len(ok)} entrada(s) de `{campo}` que no son {que} → esas "
                           f"quedan fuera de todo chequeo por elemento")
            fm[campo] = ok
    return motivos


def legacy_disputes(fm: dict) -> tuple[int, list]:
    """`(n_disputas, motivos_forma)` del schema PRE-1.19.0 (`planets[].disputes[]`). Sin este
    chequeo, al sacar la tolerancia de lectura esas disputas quedarían **mudas**: el lint no las
    vería y la bóveda seguiría en verde afirmando que no hay desacuerdos tagueados.

    Sólo una LISTA es la forma real del schema viejo (una entrada por disputa): se cuenta con
    `len()`. Cualquier otra forma —`disputes: 5` (escalar: `len()` revienta con `TypeError` y
    volteaba el lint entero) o `disputes: "abcdefg"` (string: `len()` no revienta pero cuenta 7
    disputas, UNA POR CARÁCTER)— no es N disputas, es `disputes` corrupto: se reporta como motivo
    de forma inválida en vez de inflar (o voltear) el conteo."""
    n, motivos = 0, []
    for pl in (fm.get("planets") or []):
        if not isinstance(pl, dict):
            continue
        d = pl.get("disputes")
        if d is None:
            continue
        if isinstance(d, list):
            n += len(d)
        else:
            letra = pl.get("letter", "?")
            motivos.append(f"planeta `{letra}`: `disputes` no es una lista (es {type(d).__name__}) "
                           f"→ schema viejo con forma inválida, no se puede leer ni migrar")
    return n, motivos


# Vocabulario CERRADO de `role` (#73). Es chico y cerrado a propósito: el rol define QUÉ OPERACIÓN
# de contraste corresponde entre dos papers, y un valor libre no la determina. Un typo deja el campo
# mudo para esa operación sin que nadie se entere — el mismo modo de falla de `thesis_links` que no
# matchea ninguna nota, y por eso se trata igual (bloqueante).
ROLES = ("fundacional", "aplicacion", "arbitro")


# ── espejo puro de NEA (#70) ─────────────────────────────────────────────────
# Campos de `stars/` que los scripts copian del ground-truth: (campo en la ficha, clave en el JSON).
# El contrato es que valen lo que dice NEA/SIMBAD **o nada** — la cabecera promete que el
# frontmatter es la capa auditable, y un número extraído por un LLM ahí es indistinguible del de
# NEA. Los nulls de NEA son el caso NORMAL (pl_rvamp y pl_orbeccen faltan seguido): rellenarlos con
# literatura borra la distinción. Hasta 1.13.0 nada lo detectaba —el único chequeo comparaba el
# NÚMERO de planetas, nunca los valores—, así que la promesa no tenía quién la sostuviera.
MIRROR_HOST = (("spectral_type", "spectral_type"), ("teff_K", "teff_K"),
               ("dist_pc", "dist_pc"), ("P_rot_days", "st_rotp_days"))
MIRROR_PLANET = ("P_days", "K_ms", "e", "mass_earth", "status")
# P_rot documentado en la PROSA (que es donde va cuando NEA no lo tiene). Heurística deliberada,
# como la de fuga de implementación: barata y de alta señal. Tres decisiones, cada una por un modo
# de falla medido:
#   · la clase entre `P` y `rot` cubre la notación que el propio CLAUDE.md pide en `vault/wiki/`
#     (`$P_{\rm rot}$`, `P$_{\rm rot}$`, `$P_\mathrm{rot}$`); `(?![a-z])` evita que "Protostellar"
#     cuente como mención;
#   · el ámbito es la ORACIÓN, no la línea: el repo envuelve la prosa a ~100 columnas, así que
#     "El período de rotación es\n34 d [[bib]]" quedaba sin respaldo, y la cita puede ir **antes**
#     de la mención ("[[bib]] mide un período de rotación de 34 d");
#   · un negador descarta la oración — pero SÓLO si niega la mención de `P_rot` y no otra cosa que
#     conviva en la misma oración ("...34 d [[bib]] y no hay señal en el bisector."): "no se conoce
#     el período de rotación [[bib]]" es literalmente lo que un LLM escribe en `## Huecos`, y
#     apagaba el único backlog que existe para ese hueco, pero un "no hay"/"no se conoce" que
#     aparece DESPUÉS de que la mención y la cita ya cerraron es un comentario aparte, no una
#     negación del `P_rot`. Por eso el negador se busca sólo hasta donde termina la mención o la
#     cita, la que venga después (`limite` abajo) — no en la oración entera.
PROT_MENTION = re.compile(r"(?i)P[\s_${}\\]*(?:(?:rm|mathrm|text)[\s{]*)?rot(?![a-z])"
                          r"|per[ií]odo de rotaci[óo]n|rotation period")
PROT_CITE = re.compile(r"\[\[[^\]]+\]\]|inferencia")
PROT_NEG = re.compile(r"(?i)no se conoce|no se sabe|sin medir|desconocid|no hay |ausen"
                      r"|falta[ns]? |sin determinar|nunca se|no\s+(?:est[áa]|fue|ha sido)?"
                      r"\s*(?:medid|determinad|conocid|publicad)")


def prot_documentado(body: str) -> bool:
    """¿El cuerpo documenta un `P_rot` con respaldo? Por ORACIÓN: mención + cita (en cualquier
    orden) y sin negador que niegue esa mención en particular. Ver el comentario de arriba para el
    porqué de cada parte."""
    for oracion in re.split(r"(?<=[.;])\s+|\n\s*\n", body):
        m_mencion = PROT_MENTION.search(oracion)
        m_cita = PROT_CITE.search(oracion)
        if not (m_mencion and m_cita):
            continue
        # el negador sólo cuenta hasta acá: lo que viene después de que la mención Y la cita ya
        # cerraron es, en la práctica medida, una cláusula distinta ("y no hay señal en el
        # bisector.", "aunque no se conoce la inclinación.") que niega otra cosa.
        limite = max(m_mencion.end(), m_cita.end())
        if not PROT_NEG.search(oracion[:limite]):
            return True
    return False


def same_value(a, b) -> bool:
    """¿El valor de la ficha es el del ground-truth? Los números viajan por YAML y JSON, así que se
    comparan con tolerancia relativa (un 34.0 vs 34 no es una discrepancia); el resto, textual."""
    if a is None or b is None:
        return a is None and b is None
    if (isinstance(a, (int, float)) and isinstance(b, (int, float))
            and not isinstance(a, bool) and not isinstance(b, bool)):
        return abs(a - b) <= 1e-6 * max(1.0, abs(b))
    return str(a).strip() == str(b).strip()


def mirror_issues(slug: str, fm: dict, gt: dict) -> list:
    """Campos de la ficha que NO son espejo del ground-truth (#70). Dos formas, y la distinción
    importa porque el arreglo es distinto: **difiere** (la ficha dice otra cosa que NEA → si viene
    de un paper es una `disputes[]`, no una sobreescritura) y **sin respaldo** (NEA no tiene el
    valor y la ficha sí → el número salió de la literatura y va al cuerpo, citado)."""
    host = gt.get("host") or {}
    out = []

    def check(campo: str, val_ficha, val_gt):
        if same_value(val_ficha, val_gt):
            return
        if val_gt is None:
            out.append((slug, f"`{campo}: {val_ficha}` pero el ground-truth no tiene el valor → el "
                              f"frontmatter es espejo de NEA (#70): dejalo null y poné el valor de "
                              f"literatura en el cuerpo con su `[[bibcode]]`"))
        else:
            out.append((slug, f"`{campo}: {val_ficha}` contradice el ground-truth "
                              f"({val_gt!r}) → si sale de un paper es una `disputes[]`, no una "
                              f"sobreescritura; restauralo a mano (`make_notes` NO pisa una ficha "
                              f"existente: `--force` la regenera entera y borra la prosa)"))

    for campo, key in MIRROR_HOST:
        check(campo, fm.get(campo), host.get(key))
    gt_planets = {str(p.get("letter")): p for p in (gt.get("planets") or [])}
    normalize_lists(fm)        # la forma ya la reportó el barrido de notas; acá sólo hace falta
    usables = fm.get("planets") or []                                  # que no rompa el espejo
    letras = [str(pl.get("letter")) for pl in usables]
    # QUÉ planetas, no CUÁNTOS. Comparar los largos deja pasar el caso que más importa: dos listas
    # del mismo tamaño que no son los mismos planetas —una señal no confirmada escrita en
    # `planets[]` mientras falta uno que NEA sí confirma—. Ese es justo el modo de falla que el
    # espejo existe para impedir, y con `len()` volvía limpio: un planeta entero inventado en la
    # capa auditable, indistinguible de NEA, que es la distinción que la cabecera promete.
    for letra in [l for l in letras if l not in gt_planets]:
        out.append((slug, f"planeta `{letra}` en la ficha y NO en el ground-truth → si es una señal "
                          f"no confirmada va a `disputes` (`{letra}.existence`), no a `planets[]`: "
                          f"el frontmatter es espejo de NEA (#70)"))
    for letra in [l for l in gt_planets if l not in letras]:
        out.append((slug, f"el ground-truth trae el planeta `{letra}` y la ficha no lo lista → "
                          f"re-corré la cadena (`make_notes` no pisa una ficha existente: la lista "
                          f"se actualiza a mano o con `--force`)"))
    for letra in sorted({l for l in letras if letras.count(l) > 1}):
        out.append((slug, f"planeta `{letra}` repetido en `planets[]` ({letras.count(letra)} veces)"))
    for pl in usables:
        letra = str(pl.get("letter"))
        ref = gt_planets.get(letra)
        if ref is None:
            continue          # el planeta de más ya se reportó entero: campo por campo sería ruido
        for campo in MIRROR_PLANET:
            check(f"{letra}.{campo}", pl.get(campo), ref.get(campo))
    return out


# Impresión tolerante a consolas no-UTF8 (6ª pasada de auditoría) — implementación única en
# lib_config (la comparten los otros scripts que mueren por el mismo motivo, ver su docstring).
_print_seguro = cfg.print_seguro


def main(argv=()) -> int:
    # `argv` por defecto VACÍO, no `sys.argv`: los tests llaman `lint.main()` directo y con el
    # default de argparse leerían los argumentos de **pytest**. El `__main__` de abajo pasa los
    # reales. (Si esto se olvida, 125 tests caen de golpe — pasó al escribir este fix.)
    # `lint.py` no toma argumentos, pero SÍ necesita el parser: sin él, `lint.py --help` —o
    # cualquier flag tipeado de más— corría el lint entero **ignorando el argumento en silencio** y
    # pisando `outputs/lint-<fecha>.md`. Un CLI que acepta lo que no entiende y actúa igual es la
    # misma familia que el resto de esta auditoría: hace algo distinto de lo que le pediste y no
    # avisa. Con el parser, `--help` documenta y sale 0, y un flag inexistente sale 2 sin correr nada.
    cfg.stdout_tolerante()   # ANTES de parse_args: el texto del parser lleva acentos y `--help`
                             # sale por SystemExit sin volver acá — si no, muere en consola ascii.
    argparse.ArgumentParser(
        description="Chequeo de salud de la bóveda. No toma argumentos: analiza `vault/` entera, "
                    "imprime el resumen y escribe `outputs/lint-<fecha>.md`.",
        epilog="Exit 1 si alguna categoría BLOQUEANTE tiene hits; los WARN y el backlog no bloquean."
    ).parse_args(list(argv))
    files = note_files()
    # fulltext disponible (un .txt por bibcode, bajo cualquier slug/tema) → precondición de
    # verificabilidad: una cita en query/hipótesis sin su .txt no se puede chequear claim↔fuente.
    fulltext_files = sorted(glob.glob(str(cfg.RAW / "fulltext" / "**" / "*.txt"), recursive=True))
    fulltext = {basename(p)[:-4] for p in fulltext_files}
    # Fulltext ILEGIBLE (precondición): el .txt existe pero es mojibake (fuentes sin ToUnicode) o
    # casi vacío (escaneo sin capa de texto) → no sirve para grep ni para verify-citations. Mismo
    # umbral determinista que extract_fulltext. Rescate: reemplazar el PDF por uno con capa de texto
    # sana, extraer por OCR, o marcar la fuente `pending` en sources: para derivarla al usuario.
    illegible_txt = []
    for p in fulltext_files:
        ok, why = is_legible(open(p, encoding="utf-8", errors="replace").read())
        if not ok:
            illegible_txt.append((Path(p).relative_to(cfg.RAW).as_posix(), why))
    # PDFs en disco (un <bibcode>.pdf por slug en vault/raw/pdfs/) → chequear drift `pdf` ↔ archivo.
    # stem = safe_name(bibcode), igual que el nombre de la nota del paper.
    pdf_on_disk = {}
    for _p in glob.glob(str(cfg.PDFS / "**" / "*.pdf"), recursive=True):
        pdf_on_disk.setdefault(basename(_p)[:-4], _p)
    unverifiable: list = []            # (stem, "cita <bibcode> sin fulltext")
    coverage: list = []                # concept/hipótesis sin citas [[bibcode]] → no chequeable
    unverified: list = []              # query/concept CON citas pero SIN bloque de verify-citations
    # ── "no evaluado" (D-43 / INV-87) ────────────────────────────────────────────────────────────
    # Un chequeo que NO PUDO correr no aporta un cero: reporta error. La diferencia no es
    # cosmética — un "(0)" se lee como veredicto ("miré y no hay"), y ese cero inventado hacía que
    # el lint afirmara salud sobre lo que nunca miró. Cada poblador agrega (qué chequeo, por qué),
    # la categoría CUENTA para el exit ≠ 0, y la categoría normal correspondiente se SUPRIME del
    # reporte en vez de mostrar su cero. Se declara acá arriba porque los pobladores están
    # repartidos por todo `main()`.
    not_evaluated: list = []
    verif_blocks: list = []            # (archivo, fecha del bloque|None) — notas CON bloque de verify
    names = {basename(p)[:-3] for p in files}  # stems referenciables por [[..]]
    incoming: dict[str, int] = {n: 0 for n in names}
    kinds: dict[str, list] = {}
    broken, incomplete, contradictions = [], [], []
    fm_broken: list = []               # (stem, motivo) — frontmatter no parseable o con forma
                                       # inválida (evade los chequeos por elemento de su tipo)
    retracted: list = []               # (stem, "<tipo> <fecha>") — papers marcados retracted (check_retractions)
    corrections: list = []             # (stem, "<tipo> (<fecha>)") — corrección no-retractante (#52)
    pending_srcs: list = []            # (stem, "<motivo> — puntero") — fuentes derivadas al usuario
    impl_leaks: list = []              # (stem, "línea N: marcador → texto") — fuga de implementación
    pdf_issues: list = []              # (stem, ...) — drift frontmatter `pdf` ↔ PDF en disco
    headerless: list = []              # (stem, motivo) — ficha/concepto sin cabecera estampable (#69)
    thesis_refs: dict[str, list] = {}  # valor de thesis_link -> notas que lo usan
    dispute_refs: list = []            # (nota, field, ref) de las posiciones de cada disputa (#71)
    bad_disputes: list = []            # (nota, motivo) — disputa mal formada (#71)
    old_disputes: list = []            # (nota, motivo) — disputas en el schema pre-1.19.0 (#71)
    bad_roles: list = []               # (stem, valor) — `role` fuera del vocabulario cerrado (#73)
    cited_in_entity: set = set()       # bibcodes citados desde una ficha/concepto (#75)
    extracted: list = []               # (stem, marca `no_sintetizado`) de papers YA extraídos (#75)
    bad_decisions: list = []           # (slug, clave) — decisión del registro que no es un mapa

    refs_dir = str(cfg.RAW / "refs")
    refs_stems = {basename(f)[:-3] for f in files if f.startswith(refs_dir)}  # docs de diseño, no fichas
    for f in files:
        text = open(f, encoding="utf-8").read()
        fm = split_fm(text)
        stem = basename(f)[:-3]
        for motivo in normalize_lists(fm):     # ANTES de cualquier lector (ver normalize_lists)
            fm_broken.append((stem, motivo))
        kinds[stem] = fm.get("tags", []) or []
        err = fm_error(text)
        if err:
            fm_broken.append((stem, err))
        # links salientes (las refs de diseño tienen links-ejemplo: no contar sus salientes)
        if f.startswith(refs_dir):
            continue
        # precondición de verificabilidad: en queries/concepts/hipótesis, toda cita-bibcode necesita
        # su fulltext para poder correr verify-citations (chequeo claim↔fuente).
        in_verifiable_note = in_dir(f, "queries") or in_dir(f, "concepts")   # concepts/ incluye hypotheses/
        # notas de ENTIDAD (#75): son las que sintetizan un sujeto. Una cita que sólo aparece en una
        # query no es "el paper llegó a la bóveda": la query es una respuesta puntual, no la síntesis.
        in_entity_note = in_dir(f, "stars") or in_dir(f, "concepts")   # #33: no comparar paths
                                                                       # como texto (stars-borradores)
        nbib = 0                              # citas [[bibcode]] en esta nota
        for tgt in LINK_RE.findall(text):
            tgt = tgt.strip()
            if "/" in tgt or tgt in LINK_SKIP:
                continue                       # placeholder/ejemplo, no link real
            if tgt in incoming:
                incoming[tgt] += 1
            elif tgt not in names:
                broken.append((stem, tgt))
            # #75: "citado" se mide contra el STEM de la nota de paper, así que se registra todo
            # target de una nota de entidad — no sólo los que parecen bibcode. Una clave sintética
            # off-ADS (`2006RasmussenWilliams`, y peor: cualquiera que no empiece con AAAA+letra)
            # sí matchea BIBCODE_RE… pero un citekey inválido no, y el paper quedaba reportado como
            # "no sintetizado" para siempre AUNQUE la ficha lo citara, sin forma de cerrarlo.
            if in_entity_note:
                cited_in_entity.add(tgt)
            if BIBCODE_RE.match(tgt):
                nbib += 1
                if in_verifiable_note and tgt not in fulltext:
                    unverifiable.append((stem, f"cita {tgt} sin fulltext (no chequeable claim↔fuente)"))
        # cobertura: un concepto/hipótesis que afirma sin ninguna cita [[bibcode]] no es chequeable
        # (todo lo apuntable debe ser citable o marcado `inferencia`; ver Verify en CLAUDE.md). Backlog.
        if in_dir(f, "concepts") and nbib == 0:
            coverage.append((stem, "sin citas [[bibcode]] → afirmaciones no chequeables (cobertura)"))
        # cobertura de VERIFICACIÓN (ALCE-adjacent): una nota apuntable con citas pero sin el bloque
        # `## Verificación de citas` nunca pasó por verify-citations → sus claims no fueron chequeados
        # claim↔fuente. Backlog (no bloquea): correr el skill. Sólo queries/concepts (las fichas de
        # estrella mezclan valores NEA que no se verifican contra papers).
        has_verif, verif_date = verify_block(text)
        if in_verifiable_note and nbib > 0 and not has_verif:
            unverified.append((stem, f"{nbib} cita(s) sin bloque de verify-citations → correr el skill"))
        # la vigencia del bloque se evalúa después del loop (necesita git; ver `stale_verif`). Vale
        # para TODA nota con bloque —también fichas de estrella—, no sólo las de la cobertura de
        # arriba: ampliar una ficha es justo cuando el bloque queda atrás.
        if has_verif and stem not in NON_ORPHAN:
            verif_blocks.append((f, verif_date))
        # frontera dura: fuga de implementación (código no bibliográfico) al vault (WARN, no bloquea).
        body_full = text.split("---", 2)[-1] if text.startswith("---") else text
        scan_leaks = stem not in NON_ORPHAN    # log/index/README son historia/navegación, no fichas
        # split("\n"), no splitlines(): un form feed colado no debe correr la numeración (la
        # convención de conteo es la de `grep -n` — ver skill verify-citations, #29)
        for i, line in enumerate(body_full.split("\n"), 1) if scan_leaks else []:
            if line.lstrip().startswith(">"):
                continue                       # blockquote meta (frontera/alcance)
            for rx, label in IMPL_LEAK_RE:
                if rx.search(line):
                    impl_leaks.append((stem, f"L{i} [{label}]: {line.strip()[:80]}"))
                    break
        # Cabecera no estampable (#69, backlog): una ficha/concepto sin la línea
        # `> _Generado con Almagesto v…_` deja SIN EFECTO a todos los estampadores de cabecera
        # —hoy el puntero de búsqueda de #64—, que anclan ahí y devuelven False en silencio. Sin
        # esta categoría el no-op no deja rastro: la feature no llega a la nota y nadie se entera
        # (medido en una bóveda real: 22 de 25). Se arregla con `make_notes.py --restamp-headers`.
        if f.startswith((str(cfg.STARS), str(cfg.CONCEPTS))) and GENERATOR_LINE not in text:
            headerless.append((stem, "sin la línea `_Generado con Almagesto v…_`: los estampadores "
                                     "de cabecera no pueden actuar → `python scripts/make_notes.py "
                                     "--restamp-headers`"))

        # Disputas (#71): a nivel NOTA y con posiciones explícitas — vale para estrellas y para
        # conceptos, donde la disputa es simétrica por definición (no hay valor de frontmatter
        # contra el cual poner un `alt`). Las del schema viejo NO se leen: se detectan y bloquean.
        n_viejas, motivos_viejas = legacy_disputes(fm)
        if n_viejas:
            old_disputes.append((stem, f"{n_viejas} disputa(s) en `planets[].disputes[]`, el schema "
                                       f"pre-1.19.0 que el lint ya no lee → migralas con "
                                       f"`python scripts/make_notes.py --migrate-disputes` (#71)"))
        for motivo in motivos_viejas:
            old_disputes.append((stem, motivo))
        for campo, posiciones, motivos_forma in note_disputes(fm):
            for motivo in motivos_forma:
                bad_disputes.append((stem, motivo))
            if not campo:
                bad_disputes.append((stem, "disputa sin `field`: no se sabe sobre QUÉ es el desacuerdo"))
            if len(posiciones) < 2:
                bad_disputes.append((stem, f"disputa `{campo or '?'}` con {len(posiciones)} "
                                           f"posición(es): un desacuerdo necesita al menos dos — con "
                                           f"una sola es una afirmación, y va a la prosa citada"))
            for pos in posiciones:
                if not isinstance(pos, dict):
                    bad_disputes.append((stem, f"disputa `{campo or '?'}`: posición que no es un mapa "
                                               f"(`ref`/`source` + `value`)"))
                    continue
                ref, src = str(pos.get("ref") or "").strip(), str(pos.get("source") or "").strip()
                # `source` se valida SIEMPRE que esté, no sólo cuando falta `ref`: una posición con
                # los dos declara dos dueños distintos y esquivaba el vocabulario cerrado entero.
                if src and src not in DISPUTE_SOURCES:
                    bad_disputes.append((stem, f"disputa `{campo}`: `source: {src}` fuera del "
                                               f"vocabulario ({'/'.join(DISPUTE_SOURCES)})"))
                if ref and src:
                    bad_disputes.append((stem, f"disputa `{campo}`: posición con `ref` Y `source` "
                                               f"→ una posición la sostiene UNA fuente"))
                if ref:
                    dispute_refs.append((stem, campo, ref))
                elif not src:
                    bad_disputes.append((stem, f"disputa `{campo}`: posición sin `ref` ni `source` "
                                               f"→ no se sabe quién la sostiene"))

        # chequeos de completitud por tipo
        tags = fm.get("tags", []) or []
        # Una nota en `papers/` sin `tags: [paper]` queda invisible para TODOS los chequeos de su
        # tipo —incluido `retracted`, que es frontera dura— y basta un link entrante para que
        # tampoco salga como huérfana: muda del todo. Es el hermano del frontmatter no parseable
        # ("la nota evade los chequeos de su tipo"), que ya es bloqueante por el mismo motivo.
        if in_dir(f, "papers") and "paper" not in tags and not err:   # con YAML roto ya se reportó
            fm_broken.append((stem, "nota en `papers/` sin `tags: [paper]` → evade TODOS los "
                                    "chequeos de su tipo (retracción, PDF, role, citas)"))
        if "star" in tags:
            body = text.split("---", 2)[-1] if text.startswith("---") else text
            # `P_rot_days` nulo NO es de por sí un campo incompleto (#70): el frontmatter es espejo
            # de NEA y NEA muchas veces no lo tiene — pedir que se "complete" ahí es pedir que se
            # rellene con literatura, justo lo que rompe la capa auditable. Lo accionable es otra
            # cosa: que el P_rot esté DOCUMENTADO en la prosa, con su cita (o marcado `inferencia`
            # si es lectura propia). Antes esto se reportaba para siempre, sin arreglo posible.
            if fm.get("P_rot_days") in (None, "") and not prot_documentado(body):
                incomplete.append((stem, "sin P_rot: NEA no lo trae y el cuerpo no documenta uno "
                                         "citado → buscarlo en la literatura y dejarlo en la prosa "
                                         "con su `[[bibcode]]` (el frontmatter NO se rellena)"))
            if not fm.get("activity_indicators_expected"):
                incomplete.append((stem, "activity_indicators_expected vacío"))
            # autosuficiencia (proxy estructural): cada planeta del frontmatter debe discutirse en
            # la prosa (la ficha tiene que alcanzar sola; ver "estándar de la ficha" en CLAUDE.md).
            for pl in fm.get("planets") or []:
                l = str(pl.get("letter", "")).strip()
                if not l:
                    continue
                # `[^*\n]*`, no `[^*]*`: sin el `\n` el patrón no matchea UNA negrita sino todo
                # el texto ENTRE dos negritas cualesquiera. Con el texto que #72 agregó al template
                # ("11.5 d es el armónico de 34 d", entre dos negritas), el planeta **d** —de las
                # letras más frecuentes del corpus— quedaba "discutido" en una ficha con CERO
                # líneas de prosa: falso limpio permanente en el único proxy estructural de
                # autosuficiencia que la doc publicita.
                pats = [rf"\*\*[^*\n]*\b{re.escape(l)}\b[^*\n]*\*\*",  # negrita (incl. **b/c/d**)
                        rf"\|\s*{re.escape(l)}\s*\|",               # celda de tabla
                        rf"_{re.escape(l)}\b",                       # subíndice $M_b$/$K_b$
                        rf"\b{re.escape(l)}\s*\("]                   # "b (P=...)"
                if not any(re.search(p, body) for p in pats):
                    incomplete.append((stem, f"planeta {l} en frontmatter pero no discutido en prosa"))
        if "paper" in tags:
            # retracción (bloqueante): el flag lo estampa check_retractions.py (red); acá se surface
            # offline. Una fuente retractada citada viola el contrato de la bóveda (todo respaldado
            # por fuente citable válida) → revisar cada afirmación que la cita.
            if fm.get("retracted"):
                # `or {}` no alcanza si `retraction` es un ESCALAR (edición a mano, p. ej.
                # `retraction: "retractado en 2021"`): un string es truthy, no cae en el `or`, y
                # `.get` revienta con AttributeError — la compuerta de CI muerta por el mismo
                # frontmatter raro que este chequeo existe para reportar (#h03).
                rt = cfg.as_map(fm.get("retraction"))
                retracted.append((stem, f"{rt.get('type', 'retraction')} ({rt.get('date') or 's/f'})"))
            # corrección no-retractante (#52, backlog): erratum/corrigendum/expression-of-concern.
            # NO bloquea —el paper sigue siendo citable—, pero un corrigendum cambia justamente el
            # valor que se extrajo y una EoC deja la fuente en duda → revisar lo que la cita.
            for c in (fm.get("corrections") or []):
                if not isinstance(c, dict):
                    continue
                notice = c.get("notice_doi") or "sin DOI del aviso"
                corrections.append((stem, f"{c.get('type', 'corrección')} "
                                          f"({c.get('date') or 's/f'}) → {notice}"))
            # fuente pendiente (issue #7): derivada al usuario — precondición, como las citas no
            # verificables: sin la fuente no hay fulltext ni verify. Se estampa en el ingest
            # (ingest_topic/make_notes --web con `pending`) o a mano en la nota.
            if fm.get("pending_source"):
                ptr = fm.get("doi") or fm.get("source_url") or "(sin puntero conocido)"
                pending_srcs.append((stem, f"{fm['pending_source']} — proveer la fuente; puntero: {ptr}"))
            # el tooling escribe siempre `high`/`low`; el `.lower()` cubre la edición a mano,
            # donde un `Low` entraba a la población que el recorte quería dejar afuera.
            relevancia = str(fm.get("relevance") or "").strip().lower()
            if relevancia == "high" and not fm.get("methods"):
                incomplete.append((stem, "paper relevante sin methods (sin extraer)"))
            # El eslabón SIGUIENTE (#75): el paper que SÍ se extrajo. `methods` poblado significa
            # que alguien gastó en él el paso más caro de la cadena; si su contenido nunca llegó a
            # una ficha ni a un concepto, la extracción se perdió. Se recolecta acá y se resuelve
            # después del barrido, cuando ya se sabe qué citó cada nota de entidad.
            if fm.get("methods") and relevancia != "low":
                # centinela: `no_sintetizado: ""` / `null` / `false` / `0` son marca PRESENTE pero
                # sin motivo — con `.get(campo)` a secas colapsaban con "no hay marca" y el lint
                # respondía "poné `no_sintetizado`" sobre una nota que ya lo tenía puesto.
                extracted.append((stem, fm.get("no_sintetizado", _SIN_MARCA)))
            if fm.get("thesis_links") and not fm.get("bearing"):
                incomplete.append((stem, "thesis_links sin bearing"))
            # ROL del paper (#73). `bearing` dice la POSTURA respecto de una tesis; `role` dice qué
            # tipo de aporte es, que es lo que determina la operación de contraste: fundacional ↔
            # aplicación NO es contraste sino instanciación, y leerlo como desacuerdo fabrica
            # disputas falsas. Se puebla en la extracción (la regex del clasificador no puede
            # inferirlo) — por eso el aviso cuelga de `methods`, la marca de "ya se extrajo".
            rol = fm.get("role")
            roles = rol if isinstance(rol, list) else ([rol] if rol else [])
            for r in roles:
                if str(r).strip() not in ROLES:
                    bad_roles.append((stem, f"`role: {r}` no está en el vocabulario "
                                            f"({'/'.join(ROLES)}) → typo: el rol queda mudo para el "
                                            f"contraste cross-paper"))
            # Mismo recorte que el de #75 tres líneas arriba: a una nota no-core (escrita con
            # `--all`) no se le pide rol, igual que no se le pide que aterrice en una síntesis.
            if fm.get("methods") and not roles and relevancia != "low":
                incomplete.append((stem, "paper extraído sin `role` (fundacional/aplicacion/arbitro) "
                                         "→ sin rol, contrastarlo contra otro no está definido"))
            for tl in fm.get("thesis_links") or []:
                thesis_refs.setdefault(str(tl), []).append(stem)
            # PDF ↔ disco (higiene; WARN): el campo `pdf` debe reflejar el PDF real bajado.
            pdf, on_disk = fm.get("pdf"), pdf_on_disk.get(stem)
            if pdf is not None and not isinstance(pdf, str):
                fm_broken.append((stem, f"`pdf` no es una ruta (es {type(pdf).__name__}) → el "
                                        f"chequeo PDF ↔ disco de esta nota no corre"))
                pdf = None
            pdf_ok = False
            if pdf:
                pdf_ok = (cfg.WIKI / "papers" / pdf).resolve().exists()
                if not pdf_ok:
                    pdf_issues.append((stem, f"`pdf` apunta a archivo inexistente: {pdf}"))
            elif on_disk:                      # pdf null/vacío pero el PDF está bajado → drift
                slug_dir = Path(on_disk).parent.name
                pdf_issues.append((stem, f"PDF en disco sin linkear → poné `pdf: ../../raw/pdfs/{slug_dir}/{stem}.pdf`"))
            # CUERPO ↔ frontmatter (higiene; WARN, #48): el chequeo de arriba mira frontmatter vs
            # disco y no ve el cuerpo — en Almagesto-RV el frontmatter estaba sano mientras 351/621
            # notas no tenían el link `[📄 PDF]`, y el modo de falla sobrevivió invisible hasta que
            # un humano abrió una nota. La cabecera es metadata DERIVADA: debe llevar el link sii
            # `pdf` apunta a un PDF que existe. Se distingue "sin link" (lo arregla el backfill
            # `make_notes.py --restamp-pdf-links`) de "cabecera fuera del contrato" (hay que
            # normalizarla a mano primero: el re-estampado la saltea, por eso quedaba muda).
            has_link = "[📄 PDF](" in text
            if find_header_line(text) is None:
                if pdf_ok and not has_link:
                    pdf_issues.append((stem, "cabecera fuera del contrato de stamp_pdf_link "
                                             "(sin línea `· ` con la clave en backticks) → normalizarla "
                                             "y correr make_notes.py --restamp-pdf-links"))
            elif pdf_ok and not has_link:
                pdf_issues.append((stem, "PDF linkeado en el frontmatter pero sin `[📄 PDF]` en el "
                                         "cuerpo → correr make_notes.py --restamp-pdf-links"))
            elif has_link and not pdf_ok:      # drift inverso: link a un PDF que ya no está
                pdf_issues.append((stem, "link `[📄 PDF]` en el cuerpo sin PDF vigente en `pdf` → "
                                         "correr make_notes.py --restamp-pdf-links"))

    # verificación STALE (backlog, #56): el bloque `## Verificación de citas` lleva fecha; si la nota
    # se editó DESPUÉS —un refresh de `maintain A`, un `append-knowledge`, una síntesis nueva—, las
    # afirmaciones nuevas nunca pasaron por el fan-out y quedan bajo un encabezado que se lee como
    # vigente. Es el modo de falla de #49/#50 aplicado a la garantía misma: la nota no afirma falso,
    # afirma **de menos** sobre lo que chequeó. La comparación es a nivel día (granularidad del
    # bloque): re-verificar y re-fechar el mismo día no se marca.
    stale_verif = []
    # Sin git no hay con qué comparar la fecha del bloque contra la del último cambio:
    # `last_change_dates` devolvía `{}` y el chequeo reportaba `stale=0` en silencio —
    # indistinguible de "todo al día". Es "no evaluado", no "limpio" (D-43 / INV-87).
    #
    # El gate es FINO a propósito: la rama "bloque sin fecha" no necesita git (se lee del propio
    # encabezado) y sigue corriendo siempre. Sólo las notas CON fecha quedan sin evaluar, y son
    # exactamente esas las que se cuentan en el aviso — un gate grueso apagaba un chequeo que sí
    # se podía hacer, que es el mismo error en el otro sentido.
    fechados = [f for f, d in verif_blocks if d is not None]
    stale_evaluable = not fechados or git_out("rev-parse", "--git-dir") is not None
    if not stale_evaluable:
        not_evaluated.append(
            (f"verificación stale ({len(fechados)} nota(s) con bloque fechado)",
             "no hay git (o la bóveda no es un repo): sin historial no hay con qué comparar la "
             "fecha del bloque contra la del último cambio de la nota — el chequeo queda "
             "desactivado, no en cero")) 
    changed = last_change_dates(fechados) if stale_evaluable else {}
    for f, d in sorted(verif_blocks):
        stem = basename(f)[:-3]
        if d is None:
            stale_verif.append((stem, "bloque de verificación sin fecha en el encabezado → re-fechalo "
                                      "(`## Verificación de citas (AAAA-MM-DD)`): sin fecha no hay "
                                      "forma de saber si sigue vigente"))
        elif (c := changed.get(f)) and c > d:
            stale_verif.append((stem, f"la nota se editó el {c} y su último verify es del {d} → "
                                      f"correr `verify-citations` sobre lo agregado"))

    # contradicción ground-truth ↔ ficha (qué planetas + campo por campo) + masa sospechosa
    mass_issues = []
    vistos_gt = set()
    for gtf in sorted(glob.glob(str(cfg.GROUND_TRUTH / "*.json"))):
        # El NOMBRE DEL ARCHIVO manda, no el campo `slug` de adentro: el archivo lo escribe
        # `fetch_ground_truth --slug <slug>` con el mismo slug que nombra a `stars/<slug>.md`, así
        # que es el que aparea el espejo con su ficha. Cuando el campo interno decía otra cosa
        # —renombre a medias: el skill `maintain` C nombra el archivo, la nota y el registro, pero
        # no el campo— el espejo buscaba una ficha inexistente y quedaba MUDO en silencio, que es
        # justo lo que #70 existe para impedir.
        slug = basename(gtf)[:-5]
        vistos_gt.add(slug)
        try:
            gt = json.loads(open(gtf, encoding="utf-8").read())
        except (ValueError, OSError) as e:
            # El lint es la compuerta de CI: un ground-truth ilegible se REPORTA (y su ficha queda
            # sin vigilancia), no voltea el barrido entero.
            contradictions.append((slug, f"`raw/ground_truth/{slug}.json` no se pudo leer "
                                         f"({type(e).__name__}) → el espejo #70 no puede vigilar "
                                         f"esa ficha; re-corré `fetch_ground_truth.py {slug}`"))
            continue
        if not isinstance(gt, dict):
            contradictions.append((slug, f"`raw/ground_truth/{slug}.json` no es un objeto JSON "
                                         f"(es {type(gt).__name__}) → el espejo no puede leerlo"))
            continue
        if (interno := gt.get("slug")) and str(interno) != slug:
            contradictions.append((slug, f"el JSON declara `slug: {interno}` y el archivo es "
                                         f"{slug}.json → renombre a medias; corregí el campo (el "
                                         f"archivo es el que aparea con `stars/{slug}.md`)"))
        host = gt.get("host")
        if host is not None and not isinstance(host, dict):
            # Hermano del `planets` no-lista de abajo: sin este chequeo un `host` malformado se
            # reemplazaba por `{}` MÁS ABAJO en silencio y el espejo #70 dejaba de vigilar los
            # cuatro campos estelares (spectral_type/teff_K/dist_pc/P_rot_days) sin reportar nada
            # — y de paso disparaba hallazgos FALSOS ("P_rot_days: 1.0 contradice el ground-truth")
            # que apuntan al síntoma equivocado (host vacío, no el valor de la ficha).
            contradictions.append((slug, f"`host` del ground-truth no es un mapa (es "
                                         f"{type(host).__name__}) → el espejo #70 no puede vigilar "
                                         f"spectral_type/teff_K/dist_pc/P_rot_days de esta ficha"))
        mstar = host.get("mass_msun") if isinstance(host, dict) else None
        # SIN `or []`: el `isinstance` de abajo ya neutraliza el caso None/ausente (cae al mismo
        # `else []`), pero un `or []` acá tapaba el caso falsy-no-None — `planets: 0` (int) — que
        # es justo lo que el chequeo existe para atrapar: se degradaba a `[]` en silencio (0 or []
        # → []) y el espejo #70 dejaba de vigilar la ficha sin reportar nada.
        planetas_gt = gt.get("planets")
        if not isinstance(planetas_gt, list):
            contradictions.append((slug, f"`planets` del ground-truth no es una lista (es "
                                         f"{type(planetas_gt).__name__})"))
            planetas_gt = []
        malformados = [x for x in planetas_gt if not isinstance(x, dict)]
        if malformados:
            contradictions.append((slug, f"{len(malformados)} entrada(s) de `planets` del "
                                         f"ground-truth que no son un mapa → quedan fuera del espejo"))
        planetas_gt = [x for x in planetas_gt if isinstance(x, dict)]
        gt = {**gt, "planets": planetas_gt, "host": host if isinstance(host, dict) else {}}
        for p in planetas_gt:
            if p.get("mass_flag"):                       # ya marcado por el fetch
                mass_issues.append((slug, f"{p.get('letter')}: {p['mass_flag']}"))
                continue
            # Ground-truth corrupto (K_ms/P_days/e/mass_msun editado a mano como texto): alimentar
            # eso a `msini_earth` revienta comparando un string con 0 (`K_ms <= 0`) — se detecta
            # ANTES de llamarlo y se reporta como ground-truth corrupto en vez de tumbar el barrido
            # con un TypeError (#h03).
            no_numericos = [c for c, v in (("K_ms", p.get("K_ms")), ("P_days", p.get("P_days")),
                                           ("e", p.get("e")), ("mass_msun", mstar))
                            if v is not None and (isinstance(v, bool)
                                                   or not isinstance(v, (int, float)))]
            if no_numericos:
                mass_issues.append((slug, f"{p.get('letter')}: ground-truth con valor no numérico "
                                          f"en {', '.join(no_numericos)} → no se puede calcular la "
                                          f"m·sini implícita; revisá `raw/ground_truth/{slug}.json`"))
                continue
            chk = msini_earth(p.get("K_ms"), p.get("P_days"), p.get("e"), mstar)
            m = p.get("mass_earth")
            # NO es un fallback de compatibilidad: es el chequeo INDEPENDIENTE del lint sobre todo
            # planeta que el fetch no marcó (que son casi todos). `mass_flag` es la marca del fetch;
            # esto la re-deriva offline, que es el trabajo del lint.
            if chk and m and not (1 / 3 < m / chk < 3):
                mass_issues.append((slug, f"{p.get('letter')}: mass_earth={m:.3g} M⊕ "
                                          f"≠ m·sini implícita {chk:.3g} M⊕"))
        sf = cfg.STARS / f"{slug}.md"
        if sf.exists():
            texto_ficha = sf.read_text(encoding="utf-8")
            fm_ficha = split_fm(texto_ficha)
            if not fm_ficha:
                # Sin frontmatter legible, comparar campo por campo produciría un hallazgo fantasma
                # por cada valor de NEA ("teff_K: None contradice…") apuntando al síntoma
                # equivocado: el hallazgo real es que la ficha no tiene contrato.
                contradictions.append((slug, "la ficha no tiene frontmatter legible → el espejo #70 "
                                             "no puede compararla con el ground-truth"))
            else:
                contradictions += mirror_issues(slug, fm_ficha, gt)
        else:
            # Hermano simétrico de "ficha sin ground-truth" (más abajo): un ground-truth sin su
            # ficha es un renombre a medias (el skill `maintain` renombra el JSON pero no llegó a
            # crear/renombrar `stars/<slug>.md`) o una ficha borrada sin limpiar el JSON que la
            # acompañaba. El espejo #70 no tiene con qué comparar → nadie lo mira. Backlog, no
            # bloqueante: es "la garantía no corrió acá" (no hay ficha con la que contradecir),
            # no "hay una violación" — misma severidad que el hermano.
            incomplete.append((slug, f"`raw/ground_truth/{slug}.json` sin su `stars/{slug}.md` → "
                                     "el espejo #70 no tiene ficha con la que comparar (renombre a "
                                     "medias o ficha borrada sin limpiar); recreá la ficha "
                                     f"(`make_notes.py {slug}`) o borrá el ground-truth colgado"))

    # Ficha SIN su ground-truth: el barrido de arriba lo maneja el JSON, así que una ficha sin
    # archivo no la miraba NADIE — se le podía inventar `teff_K`/`P_rot_days`/planetas enteros con
    # el lint en verde. Es alcanzable sin salirse de lo documentado (`make_notes.py <slug>` corre
    # solo, y el sub-modo *borrar* de `maintain` saca el JSON), y anula la garantía entera de #70
    # justo donde promete vigilar.
    # Backlog, no bloqueante: la distinción del framework es "hay una violación" (bloquea) vs "la
    # garantía no corrió acá" (backlog, como #55 triage pendiente y #56 verificación stale).
    for sf in sorted(cfg.STARS.glob("*.md")) if cfg.STARS.exists() else []:
        if sf.stem not in vistos_gt:
            incomplete.append((sf.stem, "ficha sin `raw/ground_truth/<slug>.json` → el espejo #70 "
                                        "no la vigila: los campos de NEA quedan sin nadie que los "
                                        f"compare (corré `fetch_ground_truth.py {sf.stem}`)"))

    # huérfanos: notas-concepto sin links entrantes. Papers/estrellas se acceden por
    # Dataview/index, no por wikilink → no son huérfanos genuinos. README tampoco. Las **matrices**
    # son estructurales (se navegan desde index.md, que es merge=ours → puede no linkearlas en una
    # instancia): tampoco son huérfanas genuinas.
    def is_orphan_candidate(n: str) -> bool:
        tags = kinds.get(n, [])
        return (not ({"paper", "star", "matrix"} & set(tags))
                and n not in NON_ORPHAN and n not in refs_stems)
    orphans = [n for n, c in incoming.items() if c == 0 and is_orphan_candidate(n)]

    # Extraído pero no sintetizado (#75, backlog): el análogo del proxy que ya existe para planetas
    # (cada planeta del frontmatter discutido en prosa). Mide si el paper LLEGÓ, no si la síntesis
    # es buena. Es el único paso salteable de la cadena que no tenía red —y su modo de falla es
    # OMISIÓN, que no deja rastro: `verify-citations` valida cada afirmación contra su fuente, no la
    # cobertura del conjunto, así que una ficha sintetizada desde 3 papers de 40 vuelve 100%
    # soportada. La población son los papers YA extraídos, no todo el core: la regla de poda manda
    # dejar fuera de la prosa lo tangencial, pero eso normalmente ni se extrae. Escotilla explícita
    # para el que sí se extrajo y legítimamente no se inlinea: `no_sintetizado: <motivo>` en la nota
    # del paper — con motivo, como el `--reason` del triage: no curar en silencio.
    unsynthesized = []
    # ordenar por STEM, no por la tupla: dos notas con el mismo stem (una copia de trabajo
    # de una nota de paper en otra carpeta) comparaban `no_sintetizado` —str contra None—
    # y volteaban el lint entero con un TypeError. El lint es la compuerta de CI: tiene que
    # reportar una bóveda rara, no morirse con ella.
    for stem, marca in sorted(extracted, key=lambda t: t[0]):
        if stem in cited_in_entity:
            continue
        if marca is not _SIN_MARCA:
            # Un motivo es TEXTO con contenido. Cualquier otra cosa (número, lista, mapa, `true`,
            # vacío) es la marca pelada que la doc dice seguir reportando: cerraba el hallazgo en
            # silencio, que es exactamente lo que "motivo obligatorio" existe para impedir.
            if (not isinstance(marca, str) or not marca.strip()
                    or marca.strip().lower() in ("true", "sí", "si", "yes")):
                unsynthesized.append((stem, "`no_sintetizado` sin motivo → poné POR QUÉ no se "
                                            "inlinea (regla de poda, aporta sólo vía roll-up, …)"))
            continue
        unsynthesized.append((stem, "extraído (`methods` poblado) pero su bibcode no está citado en "
                                    "ninguna ficha ni concepto → sintetizarlo donde corresponda, o "
                                    "marcar `no_sintetizado: <motivo>` en la nota del paper"))

    # thesis_links sin página destino: el tag no matchea ninguna nota → no acumula en el roll-up
    # Dataview de ninguna hipótesis/concepto (típico typo: shift-vs-shape vs shift_vs_shape).
    dangling_thesis = sorted(
        (tl, f"usado en {len(refs)} paper(s): {', '.join(sorted(refs)[:3])}"
             + (" …" if len(refs) > 3 else ""))
        for tl, refs in thesis_refs.items() if tl not in names)

    # `ref` de una posición sin paper destino: el bibcode que sostiene esa posición no existe como
    # nota → la disputa no es trazable (typo en el bibcode o paper sin ingestar).
    dangling_disputes = sorted(
        (nota, f"disputa `{campo}`: ref `{ref}` sin nota de paper")
        for nota, campo, ref in dispute_refs if ref not in names or "paper" not in kinds.get(ref, []))

    # objetivo sin instanciar (WARN): el template trae objective.yaml con `name` placeholder;
    # si sigue así, la bóveda clasifica "core" con la regex del ejemplo, no con TU tema — típico
    # olvido post-instanciación. Se compara contra el placeholder, no contra un nombre de ejemplo
    # plausible (un objetivo real coincidente daría WARN permanente sin forma de apagarlo).
    # (En el repo template este WARN es esperable: la bóveda seed no está instanciada.)
    # ── "no evaluado" (D-43 / INV-87) ────────────────────────────────────────────────────────────
    # Un chequeo que NO PUDO correr no aporta un cero: reporta error. La diferencia no es
    # cosmética — un "(0)" se lee como veredicto ("miré y no hay"), y ese cero inventado hacía que
    # el lint afirmara salud sobre lo que nunca miró. Cada poblador agrega (qué chequeo, por qué),
    # la categoría CUENTA para el exit ≠ 0, y la categoría normal correspondiente se SUPRIME del
    # reporte en vez de mostrar su cero.
    if (obj_err := cfg.objective_error()):
        not_evaluated.append(("clasificación de relevancia (la lente)", obj_err))

    objective_warn = []
    if not obj_err and cfg.load_objective().get("name") == cfg.DEFAULT_OBJECTIVE_NAME:
        objective_warn.append(
            ("vault/config/objective.yaml",
             "objective.name sigue siendo el placeholder del template — corré el skill `setup` "
             "(o editá el YAML) para definir el objetivo de TU bóveda"))

    # áreas de concepts/ no declaradas en concept_areas (objective.yaml) → posible typo / carpeta
    # fantasma: un `area` mal tipeado en topics.yaml crea carpeta en silencio (ver make_notes). WARN
    # blando (un typo y un área nueva legítima se ven igual → no se bloquea, se marca para revisar).
    # Sin `concept_areas` declarado el typo-check está APAGADO (no se infiere de las carpetas que
    # hay en disco: eso convertiría un typo ya cometido en "área declarada"). Se reporta la ausencia
    # una vez, en vez de marcar todas las carpetas como no declaradas.
    declared_areas = set(cfg.load_concept_areas())
    undeclared_areas = []
    if not declared_areas:
        undeclared_areas.append(
            ("vault/config/objective.yaml",
             "no declara `concept_areas` → el typo-check de áreas de concepts/ está APAGADO; "
             "declarala (aunque sea con las que ya usás) para que un `indicatorz` no pase mudo"))
    elif cfg.CONCEPTS.exists():
        for d in sorted(cfg.CONCEPTS.iterdir()):
            if d.is_dir() and d.name not in declared_areas:
                n = len(list(d.glob("*.md")))
                undeclared_areas.append(
                    (f"concepts/{d.name}/",
                     f"área fuera de concept_areas; {n} nota(s) — ¿typo o área nueva sin declarar?"))

    # Obsidian abierto en la raíz del repo (WARN): la bóveda es vault/ por diseño — un .obsidian/
    # en la raíz significa que el repo entero se abrió como vault y el grafo indexa el andamiaje
    # (outputs/, build/, scripts/, README, tests/). Error de operación silencioso: sólo se nota
    # mirando el grafo, y sin este check nadie lo mira.
    root_obsidian = []
    if (cfg.ROOT / ".obsidian").exists():
        root_obsidian.append(
            (".obsidian/ (raíz del repo)",
             "Obsidian fue abierto en la raíz en vez de `vault/` — el grafo indexa andamiaje "
             "(outputs/, build/, scripts/); abrí la carpeta `vault/` como vault y borrá este directorio"))

    # corpus truncado (backlog): un build/<slug>/ads.json con `truncated` seteado significa que la
    # query directa devolvió menos papers de los que ADS reporta (numFound > --rows) → al sujeto le
    # falta cola. El aviso vivía sólo en el stdout de la corrida (que nadie guarda); persistirlo en
    # ads.json y surfacearlo acá convierte un fallo silencioso en backlog visible (#17). build/ es
    # scratch: si no está, no hay nada que reportar (el censo de bóvedas pre-registro es otro modo).
    # `truncated_glyph` (#43) es la marca hermana pero del RESCATE POR GLIFO (#28): ahí el corte
    # top-por-citas pasa ANTES del filtro client-side — la cola puede esconder papers del sujeto
    # (los que escriben `∊ Eri` no son los más citados) → cobertura incompleta del rescate.
    #
    # Candidatos de triage sin juzgar (#55, backlog): la compuerta (#38) deja en `candidates` los
    # papers que el chaining trajo y NADIE decidió todavía (no se bajan: 18% de precisión medida).
    # El único recordatorio era el stdout de query_ads y el mensaje final del orquestador — los dos
    # se pierden apenas scrollea la terminal, así que un ingest podía cerrarse con lint en 0 y
    # cientos de candidatos pendientes: el paso con más juicio de la operación era el único sin red.
    # `candidates` ya viene NETO de decisiones (los descartados de triage.json no se re-proponen y
    # los aceptados pasaron a extra_core → son core), así que basta con contarlos.
    triage_pending = []
    truncated_corpora = []
    legacy_triage = []                 # (slug, motivo) — juicio en el build/<slug>/triage.json viejo
    vistos = set()
    for aj in sorted(glob.glob(str(cfg.ROOT / "build" / "*" / "ads.json"))):
        try:
            # JSON válido pero no-objeto (`[]`, `null` — un ads.json cortado por un Ctrl-C a mitad
            # de escritura) llegaba tal cual a `.get` y volteaba el barrido con AttributeError:
            # build/ es scratch regenerable, no motivo para tumbar la compuerta de CI (#h03).
            data = cfg.as_map(json.loads(open(aj, encoding="utf-8").read()))
        except (ValueError, OSError):
            continue
        slug = data.get("slug") or Path(aj).parent.name
        vistos.add(slug)
        t = data.get("truncated")
        if t:
            # `recent` (#79) = cuántos rescató la segunda pasada por fecha. Sólo lo traen los
            # ads.json de 1.12.0 en adelante; sin la clave, el mensaje es el de antes (la marca de
            # un corpus viejo no puede afirmar que la cola reciente se cubrió).
            rec_n = t.get("recent")
            pasada = ("" if rec_n is None else
                      f" + {rec_n} de la segunda pasada por fecha (la cola RECIENTE ya está "
                      f"cubierta; falta el medio)")
            truncated_corpora.append(
                (slug, f"ADS reporta {t.get('num_found')} y se trajeron {t.get('rows')}{pasada} → "
                       f"corpus incompleto; re-ingestá con --rows mayor (o paginá) para cubrir el resto"))
        # elementos de `candidates` que no son mapas (edición a mano / artefacto de red) se sacan
        # de la vista en vez de reventar en `c.get('bibcode', ...)` — misma política que
        # `normalize_lists` sobre el frontmatter (#h03).
        cands = [c for c in cfg.as_list(data.get("candidates")) if isinstance(c, dict)]
        if cands:
            top = ", ".join(c.get("bibcode", "?") for c in cands[:3])
            triage_pending.append(
                (slug, f"{len(cands)} candidato(s) del chaining sin juzgar (p. ej. {top}"
                       f"{' …' if len(cands) > 3 else ''}) → `python scripts/triage.py {slug}`: "
                       f"pertinente → `extra_core` en stars.yaml; ruido → `--drop … --reason`"))
        # `truncated_glyph` no iterable (escalar en vez de lista) revienta el `for`; `as_list` lo
        # degrada a `[]` en vez de tumbar el barrido (#h03).
        for tg in cfg.as_list(data.get("truncated_glyph")):
            if not isinstance(tg, dict):
                continue
            consts = "/".join(cfg.as_list(tg.get("constellations"))) or tg.get("letter") or "?"
            truncated_corpora.append(
                (slug, f"rescate por glifo incompleto: el superset de {consts} reporta "
                       f"{tg.get('num_found')} y se escanearon {tg.get('rows')} (top por citas, "
                       f"antes del filtro) → re-ingestá con --rows mayor"))

    # Juicio de triage en el lugar pre-1.9.0 (bloqueante): barrido PROPIO, no colgado del de
    # ads.json — un `build/` limpiado a medias (o una bóveda vieja sin ads.json) tendría el
    # triage.json igual, y colgarlo del otro loop lo volvía indetectable justo en el caso que este
    # chequeo existe para cubrir.
    for lt in sorted(glob.glob(str(cfg.ROOT / "build" / "*" / "triage.json"))):
        slug = Path(lt).parent.name
        try:
            data_lt = json.loads(open(lt, encoding="utf-8").read())
            # El guard `isinstance(data_lt, dict)` sólo cubría data_lt mismo: un
            # `{"decisiones": 3}` (JSON válido, forma inválida un nivel más abajo) lo pasaba igual
            # y `len(3)` volteaba el reporte ENTERO — el modo de falla equivocado para el chequeo
            # que existe para no quedar mudo. `as_map` + el `isinstance` sobre `dec` mueven el
            # guard al nivel donde de verdad se usa (#h03).
            dec = cfg.as_map(data_lt).get("decisiones")
            n_viejas = len(dec) if isinstance(dec, (dict, list)) else -1
        except (ValueError, OSError):
            n_viejas = -1
        legacy_triage.append(
            (slug, f"{'?' if n_viejas < 0 else n_viejas} decisión(es) en "
                   f"build/{slug}/triage.json, el lugar pre-1.9.0 que el lector ya no mira → "
                   f"`python scripts/triage.py {slug} --migrate` (si no, el triage vuelve a "
                   f"proponer lo que ya descartaste, sin el motivo)"))

    # Fallback al registro VERSIONADO (#51/#64) para los sujetos SIN build/ local: post-clone, otra
    # máquina, o después de limpiar el scratch, los dos chequeos de arriba reportaban 0 sin haber
    # mirado nada — un "limpio" que no significaba limpio. El snapshot no es la verdad viva (si
    # dropeaste sin re-correr la cadena, el conteo quedó viejo), así que se reporta CON su fecha y
    # diciendo que falta el scratch: mejor un dato fechado que un cero inventado.
    for rf in sorted(glob.glob(str(cfg.REGISTRO / "*.yaml"))):
        slug = Path(rf).stem
        raw = Path(rf).read_text(encoding="utf-8")
        # Lector BLINDADO (#h05): antes esto reimplementaba `yaml.safe_load` a mano acá mismo —
        # el único de seis lectores del registro que lo hacía— y por eso se saltaba el blindaje
        # que `cfg.load_registro` ya tiene (YAML roto / forma inválida → `{}`, no una excepción).
        reg = cfg.load_registro(slug)
        if not reg and raw.strip():
            # `load_registro` es TOLERANTE a propósito (el framework instruye editar el registro a
            # mano): un YAML roto o con forma inválida vuelve `{}` en vez de tumbar a sus lectores.
            # Pero saltearlo MUDO acá es el "cero inventado" que #64 cerró, por otra puerta: un
            # registro con 3 candidatos sin juzgar volvía "Triage pendiente (0)" y exit 0. Se
            # reporta como backlog —"la garantía no corrió acá", no una violación del vault— para
            # que quede a la vista sin bloquear (misma distinción que #55/#56).
            triage_pending.append(
                (slug, f"`vault/config/registro/{slug}.yaml` no se pudo leer (YAML roto o con "
                       f"forma inválida) → no se puede saber si hay triage pendiente / corpus "
                       f"truncado para este sujeto; arreglalo a mano y volvé a correr el lint"))
            continue
        # Decisión que no es un mapa (#h12): `2006Rasmussen: descartado`, sin `motivo`/`fecha`/
        # `decision`. `load_decisiones` la filtra en silencio (documentado en su docstring, que
        # promete que EL LINT la reporta) — sin este chequeo el triage vuelve a proponer lo ya
        # descartado sin el motivo, el mismo bug que #51 cerró. Corre para TODO registro, tenga o
        # no `build/` local: es independiente del fallback de triage-pendiente/corpus-truncado de
        # abajo.
        dec = reg.get("decisiones")
        if isinstance(dec, dict):
            for clave, v in dec.items():
                if not isinstance(v, dict):
                    bad_decisions.append(
                        (slug, f"decisión `{clave}` no es un mapa (es {type(v).__name__}, falta "
                               f"`decision`/`motivo`/`fecha`) → `load_decisiones` la descarta en "
                               f"silencio y el triage vuelve a proponerla sin el motivo"))
        if slug in vistos:
            continue                                  # build/ presente: ya se reportó la verdad viva
        b = cfg.as_map(reg.get("busqueda"))
        fecha = b.get("fecha") or "s/f"
        if b.get("n_candidates"):
            triage_pending.append(
                (slug, f"{b['n_candidates']} candidato(s) sin juzgar según el registro del {fecha} "
                       f"(sin build/{slug}/ local: es el snapshot de esa corrida, no el conteo "
                       f"vigente) → re-corré la cadena y después `python scripts/triage.py {slug}`"))
        if b.get("truncated"):
            truncated_corpora.append(
                (slug, f"corpus truncado según el registro del {fecha} (ADS reporta "
                       f"{b.get('n_found')} y se pidieron {b.get('rows')}) → re-ingestá con --rows "
                       f"mayor para cubrir la cola"))

    # reporte
    lines = [f"# Lint de la bóveda — {dt.date.today().isoformat()}", ""]
    # categorías que NO se pudieron evaluar: se omiten del reporte en vez de mostrar un "(0)" que
    # se leería como veredicto (el adversario que D-43 nombra: el cero inventado).
    suprimidas = set()
    if not stale_evaluable:
        suprimidas.add("Verificación stale")
    for title, items in [("⛔ No evaluado: el chequeo no pudo correr (hecho del ENTORNO, no de la "
                          "bóveda — cuenta para el exit)", not_evaluated),
                         ("Wikilinks rotos (página faltante)", broken),
                         ("⛔ Frontmatter no parseable o con forma inválida (la nota evade los chequeos de su tipo)", fm_broken),
                         ("⛔ Papers RETRACTADOS citados (frontera dura: fuente no válida)", retracted),
                         ("Notas huérfanas (sin links entrantes)", [(o, "") for o in orphans]),
                         ("Papers con corrección publicada (erratum/corrigendum/EoC) — revisar los "
                          "valores extraídos de ellos (backlog, el paper sigue siendo citable)", corrections),
                         ("Contradicciones ground-truth ↔ ficha", contradictions),
                         ("Ground-truth: masa inconsistente con m·sini (K,P,e,M*)", mass_issues),
                         ("thesis_links sin página destino", dangling_thesis),
                         ("disputes: ref de una posición sin paper destino", dangling_disputes),
                         ("disputes mal formadas (posiciones explícitas, #71)", bad_disputes),
                         ("disputes en el schema viejo (planets[].disputes[]) — el lint ya no las lee", old_disputes),
                         ("Juicio de triage en build/<slug>/triage.json (pre-1.9.0) — el lector ya no lo mira", legacy_triage),
                         ("`role` fuera del vocabulario (fundacional/aplicacion/arbitro)", bad_roles),
                         ("⚠ Fuga de implementación (código no bibliográfico) → frontera dura (WARN, revisar a mano)", impl_leaks),
                         ("Objetivo sin instanciar (WARN — objective.yaml sigue en el placeholder del template)", objective_warn),
                         ("Áreas de concepts/ no declaradas en objective.yaml (WARN, posible typo)", undeclared_areas),
                         ("Obsidian en la raíz del repo (WARN — la bóveda se abre en vault/)", root_obsidian),
                         ("PDF ↔ disco / cuerpo (WARN — higiene: frontmatter `pdf` vs PDF bajado vs link de cabecera)", pdf_issues),
                         ("⏳ Fuentes pendientes (pending_source — el usuario debe proveer la fuente)", pending_srcs),
                         ("Fulltext ilegible (mojibake/escaneo — existe pero no sirve para grep/verify)", illegible_txt),
                         ("Citas no verificables en query/concepto/hipótesis (sin fulltext)", unverifiable),
                         ("Sin verificar: query/concepto con citas pero sin bloque verify-citations (backlog)", unverified),
                         ("Verificación stale: la nota se editó después de su último verify-citations (backlog)", stale_verif),
                         ("Cobertura: concepto/hipótesis sin citas [[bibcode]] (backlog)", coverage),
                         ("Extraído pero no sintetizado: el paper se extrajo y su contenido nunca "
                          "llegó a una ficha/concepto (backlog)", unsynthesized),
                         ("Cabecera no estampable: ficha/concepto sin la línea del generador — los "
                          "estampadores de cabecera no-opean en silencio (backlog)", headerless),
                         ("Triage pendiente: candidatos del chaining sin juzgar (backlog)", triage_pending),
                         ("Corpus truncado: la query directa trajo menos de lo que ADS reporta (backlog)", truncated_corpora),
                         ("Decisión del registro con forma inválida — load_decisiones la descarta "
                          "en silencio, el triage la vuelve a proponer sin el motivo (backlog)", bad_decisions),
                         ("Campos incompletos", incomplete)]:
        if any(title.startswith(s) for s in suprimidas):
            continue
        lines.append(f"## {title} ({len(items)})")
        for a, b in items:
            lines.append(f"- {a}" + (f" → {b}" if b else ""))
        lines.append("")
    report = "\n".join(lines)

    outdir = cfg.ROOT / "outputs"
    outdir.mkdir(exist_ok=True)
    out = outdir / f"lint-{dt.date.today().isoformat()}.md"
    out.write_text(report, encoding="utf-8")
    _print_seguro(report)
    _print_seguro(f"→ {out}")
    # Exit code gateable: las categorías que CLAUDE.md exige "en 0" bloquean; WARN (fuga de
    # implementación, áreas, PDF↔disco) y backlog (verificabilidad, cobertura, incompletos) no.
    n_block = sum(len(x) for x in (not_evaluated, broken, fm_broken, retracted, orphans,
                                   contradictions, mass_issues, dangling_thesis, dangling_disputes,
                                   bad_roles, bad_disputes, old_disputes, legacy_triage))
    if n_block:
        _print_seguro(f"✗ {n_block} hallazgo(s) en categorías bloqueantes → exit 1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
