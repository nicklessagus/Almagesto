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
escaneo sin capa de texto: existe pero no sirve para grep ni verify), **mismo bibcode con `.txt`
distinto entre slugs** (#190: D-18 copia el artefacto a cada slug que lo reclama y `raw/` es
inmutable, así que dos copias con bytes distintos son una re-extracción que corrió bajo un slug y
no bajo el otro; el ancla de fuente (D-20) hashea UNA sola copia, así que los pares verificados
contra las demás se comparan contra un archivo que nunca leyeron; bloqueante — se compara, NO se
sincroniza), **citas no verificables** (bibcode
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
incompletos (P_rot sin documentar en la prosa, papers relevantes sin `methods`, paper extraído
sin `role`).
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
from dataclasses import dataclass, field, replace
import argparse
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

import lib_config as cfg
import lib_blocks as lb
import make_notes as mn
import entity                                # alcance por slug de `--cierre` (#121)
from extract_fulltext import is_legible      # umbral determinista de legibilidad (mismo que extract)
from fetch_ground_truth import msini_earth   # verificación de masa (m·sini implícita)
from make_notes import find_header_line      # contrato de la cabecera (mismo que stamp_pdf_link, #48)
from make_notes import GENERATOR_LINE        # ancla de la cabecera de fichas/concepts (#69)

#: Prefijo de la línea de estado de la cabecera (#233). Vive acá y no en un literal suelto porque lo
#: comparan dos lados: el que la escribe (`make_notes.estado_line`) y el que verifica que se haya
#: escrito. Es el mismo criterio que `GENERATOR_LINE`.
ESTADO_PREFIJO = "> _Estado — "


def _lines_with_section(body: str) -> list:
    """`[(line, section header)]` — each line paired with the `## ` section it lives in.

    Lets a form check exempt the stamped sections without re-implementing «where does a section
    start», which is the rule this repo has already grown a second copy of twice.
    """
    out, sec = [], ""
    for ln in body.split("\n"):
        if ln.startswith("## "):
            sec = ln.strip()
        out.append((ln, sec))
    return out


def _entity_slug(path: str) -> str | None:
    """The subject slug this entity note belongs to, or `None` if it is not one (#233).

    A star note is named after its slug; a concept is named after the `concept` its theme declares,
    which is **not** the slug — hence the lookup through `themes.yaml` instead of the filename.
    Returns `None` for papers, queries and matrices: those carry no state line."""
    nombre = Path(path).stem
    if path.startswith(str(cfg.STARS)):
        return nombre
    if not path.startswith(str(cfg.CONCEPTS)):
        return None
    if cfg.themes_error():
        return None
    for slug_t, meta in (cfg.load_themes() or {}).items():
        if str(cfg.as_map(meta).get("concept") or slug_t) == nombre:
            return slug_t
    return None
# @inv INV-02
# ⛔ Exige que después del target venga un delimitador (`]`, `|` o `#`) y **corta en el salto de
# línea**. Sin eso, un `[[` sin cerrar se tragaba el link SIGUIENTE: medido el 2026-08-28,
# `"[[ y sigo.\nEl radio vive en [[gp-kernels]]"` devolvía UN solo target multilínea, así que un
# wikilink real dejaba de contar como entrante y su destino se reportaba **huérfano** — categoría
# BLOQUEANTE — con un mensaje que nombraba un target inservible.
LINK_RE = re.compile(r"\[\[([^\]\|#\n]+)(?=[\]\|#])")
# Frontera dura (regla #0 de CLAUDE.md): la bóveda es SÓLO bibliografía. Detecta material de
# implementación/código no bibliográfico que se filtró a una nota. WARN, no bloquea: son heurísticas de
# alta señal/bajo ruido; se saltan los blockquotes meta (frontera/alcance). Revisar a mano cada hit.
# @inv INV-04
IMPL_LEAK_RE = [
    (re.compile(r"\bperilla\b", re.I), "perilla (dial de implementación)"),
    (re.compile(r"\bdial\b", re.I), "dial de implementación"),
    (re.compile(r"w_\{?j"), "pesos por orden w_j (parámetro de código)"),
    (re.compile(r"=\s*peso\("), "vector de mezcla peso(azul)/peso(rojo)"),
    # D-50 — la mitad de AUTO-REFERENCIA. Los cuatro de arriba cazan el parámetro de código que se
    # coló; esta mitad caza el otro modo, más frecuente y más difícil de ver: la nota describiendo
    # a QUIEN LA CONSUME ("nuestro pipeline usa esto para…"). Rompe el flujo unidireccional de la
    # regla #0 — la bóveda no se acomoda a quien la lee— y no deja rastro estructural: es prosa
    # normal, bien escrita, que sólo se nota preguntando "¿esto sale de una fuente citable?".
    # La frontera fina la fija CLAUDE.md: los campos ESTRUCTURALES del frontmatter (`data_local`,
    # `methods_applied.ours`) sí pueden apuntar afuera; lo prohibido es el puntero EN PROSA. Por
    # eso el scan es por línea del cuerpo y el frontmatter no entra.
    (re.compile(r"\bnuestr[oa]s?\s+(pipeline|c[óo]digo|scripts?|repo|implementaci[óo]n|"
                r"generador|modelo)\b", re.I), "auto-referencia al consumidor (nuestro …)"),
    (re.compile(r"\bdownstream\b", re.I), "auto-referencia al consumidor (downstream)"),
    (re.compile(r"\bpara\s+el\s+repo\b", re.I), "auto-referencia al consumidor (para el repo)"),
    (re.compile(r"\bsupuesto\s+de\s+trabajo\b", re.I),
     "supuesto de trabajo (decisión de implementación, no bibliografía)"),
]
# CONTEXTO de consumo: las formas en las que una nota nombra a quien la lee. El nombre propio del
# repo consumidor NO se matchea pelado a propósito — en esta bóveda `ICA` es además el nombre de un
# método real (está en `relevance.facets`), así que un `\bICA\b` suelto marcaría cada mención
# legítima y la categoría se volvería un rojo permanente, que es un rojo que se deja de mirar. Lo
# que delata la fuga no es el nombre: es el nombre en posición de CONSUMIDOR.
_CONSUMIDOR_ANTES = r"(?:scripts?|pipeline|c[óo]digo|repo|implementaci[óo]n|generador|m[óo]dulo)\s+de\s+"
_CONSUMIDOR_DESPUES = r"\s+(?:usa|usan|consume|consumen|necesita|necesitan|espera|esperan|toma|toman|lee|leen)\b"


def downstream_leaks(names: list) -> list:
    """Un patrón por consumidor declarado (`downstream: []`, D-50), en contexto de consumo.
    Lista vacía si no hay nada declarado: esa mitad del detector queda apagada, sin WARN."""
    # @inv INV-04
    out = []
    for n in names:
        esc = re.escape(str(n).strip())
        if not esc:
            continue
        out.append((re.compile(rf"{_CONSUMIDOR_ANTES}{esc}\b|\b{esc}{_CONSUMIDOR_DESPUES}", re.I),
                    f"auto-referencia al consumidor declarado ({n})"))
    return out


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
    #  El BOM no puede volver invisible el frontmatter: sin este `lstrip`, una nota con U+FEFF
    #  evadía todos los chequeos de su tipo y `fm_error` ni la miraba (#36/#40, 2026-08-28).
    if not text.lstrip(cfg.BOM).startswith("---"):
    #  @inv INV-40
        return None
    span = cfg.frontmatter_span(text)
    if span is None:
        return "frontmatter sin cierre `---`"
    yaml_block, _body = span
    try:
        fm = yaml.safe_load(yaml_block)
    except Exception as e:
        first = (str(e).splitlines() or [e.__class__.__name__])[0]
        return f"YAML inválido: {first[:80]}"
    # YAML **válido pero no-mapa**: `split_fm` lo devuelve como `{}` (honra su firma), así que sin
    # este renglón la nota evade en silencio todos los chequeos de su tipo — que es exactamente el
    # modo de falla que esta función existe para cerrar. Medido el 2026-08-28.
    if fm is not None and not isinstance(fm, dict):
        return (f"el frontmatter parsea pero NO es un mapa (es {type(fm).__name__}): sin pares "
                f"`clave: valor` la nota evade todos los chequeos de su tipo")
    return None


# AUD-136: la regla de la fecha de verificación vive UNA sola vez, en `lib_config`.
VERIF_HEAD_RE = cfg.VERIF_HEAD_RE


def verify_block(text: str) -> tuple[bool, str | None]:
    """(¿la nota tiene bloque `## Verificación de citas`?, fecha de la verificación más reciente).

    La fecha vive en el encabezado por convención del skill (`## Verificación de citas
    (AAAA-MM-DD)`): es lo único que permite saber si lo verificado sigue vigente o quedó atrás de
    una edición posterior. Una nota puede acumular **varios** bloques (medido en una bóveda real:
    hasta 11 — pasadas sucesivas sobre secciones distintas), así que la vigencia la marca la fecha
    **máxima**, no la del primero: quedarse con el primero dejaría la nota stale para siempre por
    más que se re-verifique."""
    # @inv INV-31
    # AUD-136: la regla vive UNA sola vez, en `lib_config` — `make_notes.estado_line` la
    # reimplementaba tomando el PRIMER bloque, así que la cabecera de la nota y el veredicto del
    # lint sobre esa misma nota podían nombrar fechas distintas.
    return cfg.verification_date(text)


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


# D-34 — el ALCANCE declarado de una nota de hipótesis. Formato del skill `test-hypothesis`:
#   > Alcance 2026-08-23 · temas: [ica, crx] + estrellas: [tau_ceti] · 190 papers · 47 con hits
# Se parsea con tolerancia (el bloque lo escribe un LLM): basta la fecha, los slugs y el conteo. Los
# slugs son directorios de `raw/fulltext/`, así que el universo declarado se puede volver a contar.
ALCANCE_RE = re.compile(r"^>\s*Alcance\s+(\d{4}-\d{2}-\d{2})\b", re.M)
ALCANCE_SLUGS_RE = re.compile(r"(?:temas|estrellas|entidades)\s*:\s*\[([^\]]*)\]", re.I)
ALCANCE_N_RE = re.compile(r"·\s*(\d+)\s+papers?\b", re.I)


def alcance_declarado(text: str) -> dict | None:
    """`{fecha, slugs, n_papers}` del blockquote de alcance, o `None` si la nota no lo trae.

    `None` ≠ alcance vacío: una hipótesis SIN alcance declarado es el hallazgo de D-34 —un veredicto
    negativo sin alcance se lee como universal ("no existe evidencia" en vez de "no hay evidencia en
    estos 190 papers")—, y es distinto de una cuyo alcance quedó corto."""
    # @inv INV-92
    m = ALCANCE_RE.search(text)
    if not m:
        return None
    linea_fin = text.find("\n\n", m.start())
    bloque = text[m.start():linea_fin if linea_fin > 0 else len(text)]
    slugs = []
    for grupo in ALCANCE_SLUGS_RE.findall(bloque):
        slugs += [x.strip() for x in grupo.split(",") if x.strip()]
    n = ALCANCE_N_RE.search(bloque)
    return {"fecha": m.group(1), "slugs": slugs,
            "n_papers": int(n.group(1)) if n else None}


def corpus_vigente(slugs: list) -> tuple[int, list]:
    """(papers con fulltext hoy en esos slugs, slugs cuyo directorio no existe). El universo de una
    hipótesis son directorios de `raw/fulltext/` porque es exactamente sobre lo que corre el grep."""
    # @inv INV-92
    total, faltan = 0, []
    for sl in slugs:
        d = cfg.FULLTEXT / sl
        if not d.is_dir():
            faltan.append(sl)
            continue
        total += len(list(d.glob("*.txt")))
    return total, faltan


# Secciones que la máquina ESTAMPA en una ficha: son metadata materializada, no prosa. El proxy de
# autosuficiencia ("¿cada planeta se discute?") las tiene que descontar — desde que `## Planetas` y
# `## Métodos aplicados` dejaron de ser bloques ```dataview``` y pasaron a tabla (D-11/INV-81), sus
# celdas satisfacían el patrón `|\s*b\s*|` y **todo planeta quedaba "discutido"** en una ficha con
# cero líneas escritas: el mismo falso limpio permanente que el bug del `[^*]*`, por otra puerta.
# La lista y el recorte viven en `lib_config` (una sola declaración para los tres consumidores);
# acá quedan los alias por los que este módulo y sus tests ya los nombraban.
SECCIONES_ESTAMPADAS = cfg.SECCIONES_ESTAMPADAS
solo_prosa = cfg.solo_prosa


def _muestra(xs: list, n: int = 5) -> str:
    """Los primeros `n` elementos, con `…` si hay más. Un hallazgo tiene que NOMBRAR (los stems del
    delta), no contar; y una lista de 300 tampoco se lee: se nombra una muestra y se dice que hay más."""
    return ", ".join(xs[:n]) + (" …" if len(xs) > n else "")


def merge_ours_unprotected() -> tuple[list[str], str | None]:
    """Patrones `merge=ours` de `.gitattributes` que el clon NO está protegiendo, y por qué (#99).

    `merge=ours` sólo hace algo si el clon registró el driver — `git config merge.ours.driver true`,
    que `.gitattributes` pide "una vez por clon". No lo hace ningún script, ningún hook y ningún
    paso de la cadena, así que la protección de los archivos de instancia (`objective.yaml`,
    `stars.yaml`, …) **falla en silencio**: el próximo `git pull` los pisa con la versión del
    template. Medido el 2026-08-25 sobre tres clones reales: dos de los tres sin el driver.

    Es la misma familia que #93 —un mecanismo de protección cuya precondición nadie chequea— y por
    eso el resultado se reporta en dos canales distintos: los patrones en riesgo son un hallazgo de
    la BÓVEDA, y no poder mirarlo (sin git) es un hecho del ENTORNO que va a *no evaluado*: un `(0)`
    que nadie midió se lee como veredicto.

    ⚠ **Sólo cuenta el archivo que tiene ALGO QUE PERDER**: uno que no difiere de su upstream se
    re-escribe idéntico y el driver es indiferente. Sin ese recorte el chequeo marcaba los 7
    patrones en un clon recién hecho —el template, y cualquier corrida de CI— donde no hay riesgo
    ninguno, y un hallazgo que aparece siempre se deja de mirar. El riesgo aparece justo cuando la
    instancia **personalizó** su config, que es el caso que #99 vino a cubrir.

    Sin git el chequeo **no aplica** (no hay `pull` posible), igual que sin `.gitattributes`. El
    segundo valor del retorno queda para un motivo de *no evaluado* futuro; hoy siempre es `None`.

    Devuelve `(patrones_en_riesgo, motivo_de_no_evaluado)`."""
    ga = cfg.ROOT / ".gitattributes"
    if not ga.exists():
        return [], None       # nada declara `merge=ours`: el chequeo NO APLICA, que no es
                              # "no se pudo evaluar" — esa distinción es justo la de D-43
    try:
        lineas = ga.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return [], f"`.gitattributes` ilegible ({e})"
    patrones = [ln.split()[0] for ln in lineas
                if not ln.lstrip().startswith("#") and "merge=ours" in ln and ln.split()]
    if not patrones:
        return [], None                       # nada que proteger: el chequeo no aplica
    if git_out("rev-parse", "--git-dir") is None:
        return [], None       # `merge=ours` es un mecanismo de git: sin git no hay `pull` que pueda
                              # pisar nada, así que NO APLICA. Mandarlo a *no evaluado* ponía en
                              # rojo toda copia sin `.git` — incluida la que usa el gate de mutación,
                              # que fue donde se detectó. Distinto del caso de la verificación
                              # stale (D-43), donde sin git queda algo real sin medir.
    #  @inv INV-68
    if (git_out("config", "--get", "merge.ours.driver") or "").strip():
        return [], None                       # protegido: no hay riesgo
    return [pat for pat in patrones if _diverge_del_upstream(pat)], None


#  @inv INV-128
GT_STALE_MARK = "⚠desactualizado"

# #302 · techos del `STATUS.md`. Es **estado**, no bitácora: lo histórico va a `wiki/log.md`, que es
# append-only por contrato y lo cumple. Los dos números son el umbral por encima del cual el archivo
# dejó de ser un estado — están declarados acá (y no en `tools/doc-size-ratchet.yaml`) porque el
# STATUS es de la INSTANCIA (`merge=ours`), así que un ratchet versionado del template no lo
# describiría. Medido en una bóveda real: 537 líneas con 12 encabezados fechados.
STATUS_MAX_FECHADOS = 3
STATUS_MAX_LINEAS = 300

#: #225 · la cuarta marca en línea: lo que una auditoría de ficha (`audit-note`) NO pudo verificar.
#: No destruye la afirmación —puede ser cierta— y es visible para el consumidor; el lint la levanta
#: como backlog para que la deuda no se olvide, y se saca cuando alguien la verifica con evidencia.
VERIFICAR_PDF_MARK = "⚠verificar en el PDF"

#: #238 · la quinta marca: una entrada de `log.md` que quedó REFUTADA. La bitácora es append-only
#: por contrato —y está bien—, pero eso la dejaba sin forma de corregirse: medido, una entrada
#: publica como cita textual con página una frase que invierte el sentido de lo que dice el paper,
#: y el propio log lo reconoce 268 líneas después, en la entrada de la verificación. La cita
#: fabricada sigue ahí, sin marca y sin puntero a su corrección. Misma doctrina que las otras:
#: hacer visible, no borrar.
LOG_SUPERSEDED_MARK = "⚠ corregido"

#: #235 · «… el radio `slug` …» — un radio nombrado como código en vez de linkeado.
_RADIO_RE = re.compile(r"radio[s]?\s+(?:[^`\n]{0,40}?)`([a-z0-9][a-z0-9-]{2,})`", re.I)


def _field_is_marked(lineas_marcadas: list[str], campo: str, viejo) -> bool:
    """¿Alguna línea con `⚠desactualizado` está marcando ESTE campo? (#131)

    La marca va pegada al valor, así que la línea que la lleva tiene que nombrar el valor viejo —que
    es lo que la prosa cita— o el campo. Se acepta el nombre corto (`teff_K` de `host.teff_K`)
    porque la prosa no escribe la ruta del JSON.

    ⛔ **Por OCURRENCIA, no por substring.** El `in` pelado hacía que cualquier línea marcada tapara
    cualquier campo: el nombre corto de `<letra>.e` es `"e"`, y **"desactualizado" contiene una `e`**
    — así que una sola marca en cualquier lado silenciaba toda excentricidad que NEA hubiera
    cambiado. Ídem el valor: `mass_earth = 4` quedaba "marcado" por una línea que dice `Teff = 5344`.
    Los tres casos están medidos (2026-08-28) y son falsos limpios sobre prosa que sigue citando un
    valor retirado — justo lo que INV-128 existe para que **no** pase, y su enunciado ya decía «se
    evalúa por ocurrencia»."""
    corto = str(campo).rsplit(".", 1)[-1]
    val = "" if viejo is None else str(viejo)
    #  El valor va con lookaround de palabra-o-punto: `4` no puede matchear dentro de `5344` ni de
    #  `1.04`, y un valor con signo (`-5`) tampoco rompe un `\b`.
    pat_campo = re.compile(rf"\b{re.escape(corto)}\b")
    pat_val = re.compile(rf"(?<![\w.]){re.escape(val)}(?![\w.])") if val else None
    #  La marca vale para lo que la PRECEDE —«va pegada al valor», dice la regla—, no para la línea
    #  entera: en `$P=20.0$ d ⚠desactualizado y $K=1.0$ m/s` sólo P está marcado. Cada segmento
    #  anterior a una ocurrencia de la marca es un ámbito; lo que va después de la última, no.
    for ln in lineas_marcadas:
        for seg in ln.split(GT_STALE_MARK)[:-1]:
            if pat_campo.search(seg) or (pat_val and pat_val.search(seg)):
                return True
    return False


def _diverge_del_upstream(pattern: str) -> bool:
    """¿El archivo tiene cambios propios que un `git pull` podría pisar?

    Dos formas de tenerlos: sin commitear (working tree) o commiteados por encima del upstream.
    Sin upstream configurado sólo se mira el working tree — es lo único decidible."""
    if (git_out("status", "--porcelain", "--", pattern) or "").strip():
        return True
    diff = git_out("diff", "--name-only", "@{u}...HEAD", "--", pattern)
    return bool((diff or "").strip())


_SEP_ROW = re.compile(r"^\|[\s\-:|]+\|?$")   # `|---|---|`: estructura, no contenido

INVENTARIO_HEADER = "## Inventario por eje"


# #188 · las dos marcas del cuerpo de una nota de paper. `## Extracción (LLM)` es el schema VIEJO
# (una sola sección, sin scope) y `## Vista — <sujeto>` el nuevo (una por lente). El guion se acepta
# en sus tres formas: la escribe `make_notes` con el largo, pero una nota editada a mano con `-`
# tendría la vista hecha y el detector la reportaría como ausente — un falso positivo sobre trabajo
# real, que es la peor moneda de un gate bloqueante.
EXTRACCION_VIEJA_RE = re.compile(r"^##\s+Extracci[oó]n\s*\(LLM\)\s*$", re.M)
VISTA_RE = re.compile(r"^##\s+Vista\s*[—–-]\s*(.+?)\s*$", re.M)
#: #239 · la sub-sección de una lente dentro de una vista.
_LENTE_RE = re.compile(r"^###\s+Lente\s*[—–-]\s*(.+?)\s*$", re.M)


def vistas_en_cuerpo(text: str) -> set:
    """Los sujetos que tienen su sección `## Vista — <sujeto>` en el cuerpo de la nota.

    La sección NO va a `SECCIONES_ESTAMPADAS`: es exactamente lo que `verify-citations` tiene que
    contrastar contra el `.txt` — la extracción es el paso más caro de la cadena y hoy es el menos
    chequeado (6 de 908 notas de paper con bloque de verificación).

    ⛔ AUD-178 / INV-134 — dos recortes que faltaban, y los dos producían **hallazgos bloqueantes
    sobre una nota bien leída**, que es el peor tipo de falso positivo (obliga a "arreglar" trabajo
    correcto). (a) Un encabezado dentro de un ```code fence``` es un EJEMPLO, no una sección: la
    doc del repo está llena de bloques así, y `section_start` ya lo descuenta desde #198. (b) El
    sujeto se recorta en el sufijo que arranca con puntuación —`## Vista — X (2026-08-27)`, la
    forma que el propio framework documenta— porque si no `X (2026-08-27)` no matchea `X` y la nota
    dispara LAS DOS incoherencias a la vez: «vista declarada sin su sección» y «sección sin
    declarar»."""
    dentro = cfg._offsets_en_fence(text)
    out = set()
    for m in VISTA_RE.finditer(text):
        if m.start() in dentro:
            continue
        sujeto = m.group(1).strip()
        # mismo criterio que `section_start`: el sufijo que arranca con puntuación no es del nombre
        if (corte := re.search(r"\s+[^\w\s]", sujeto)):
            sujeto = sujeto[:corte.start()].strip()
        out.add(sujeto)
    return out


def challenging_rows(text: str) -> int:
    """Cuántas filas de la tabla de evidencia (D-21) declaran postura `desafía` (#177).

    Se lee la COLUMNA, no el texto suelto: la palabra aparece en la prosa explicativa de la propia
    plantilla, así que un `in text` daría un falso positivo en toda hipótesis recién generada."""
    n = 0
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln.startswith("|") or ln.startswith("|--"):
            continue
        celdas = [c.strip().strip("*`_ ").lower() for c in ln.strip("|").split("|")]
        # la postura es una celda ENTERA, no una mención: la fila de plantilla lista las tres
        # opciones separadas por `\|` escapado y no cuenta.
        if any(c == "desafía" or c == "desafia" for c in celdas):
            n += 1
    return n


def inventario_sin_llenar(text: str) -> bool:
    """La sección `## Inventario por eje` está, pero con la fila vacía de la plantilla (#101).

    Es la red que le faltaba al paso **3b** (contraste cross-paper). `CLAUDE.md` lo llama *«el paso
    con más apalancamiento de la cadena y el que más fácil se saltea, porque su producto no se nota
    si falta»*, y su única red era el backlog *extraído pero no sintetizado* (#75) — que mide si el
    paper **llegó**, no si el contraste **ocurrió**.

    El detector usa la escotilla que la propia plantilla ya define: *«si no hay ningún eje en
    disputa, borrar la sección y decirlo en el log»*. O sea que **ausencia = declarado** y
    **presente-y-vacío = saltado**. No hace falta un campo nuevo, ni adivinar qué ejes existían.

    Por qué importa (medido, 2026-08-25): el contraste cazó un `K_d` copiado de la Tabla 2 de
    Mayor+2009 que la **prosa del mismo paper** contradice, y `verify-citations` **no lo puede ver**
    —«la Tabla 2 dice 4,55» es literalmente cierto—. La pasada encontró cinco inconsistencias
    internas de fuentes por esta vía, ninguna visible para el chequeo claim↔fuente."""
    i = cfg.section_start(text, INVENTARIO_HEADER)
    if i < 0:
        return False                      # sección borrada: la escotilla declarada, no un hallazgo
    seccion = text[i:]
    corte = seccion.find("\n## ", 1)
    if corte > 0:
        seccion = seccion[:corte]
    filas = [ln.strip() for ln in seccion.split("\n")
             if ln.strip().startswith("|") and not _SEP_ROW.match(ln.strip())]
    #  @inv INV-97
    return not any(c.strip() for f in filas[1:] for c in f.strip("|").split("|"))


#: #216 — un abstract más corto que esto no identifica a nadie: es un placeholder
#: (`_(no disponible)_`), un título repetido o un resumen de dos líneas que dos trabajos distintos
#: del mismo grupo pueden compartir. El piso convierte la señal en «coincide el texto largo».
ABSTRACT_MIN = 200
#: Se compara el ARRANQUE, no el texto entero: el caso medido es «el mismo texto palabra por
#: palabra, en otro congreso, y TRUNCADO», así que exigir igualdad exacta lo perdería justo donde
#: el duplicado es más probable.
ABSTRACT_CLAVE = 300


def _abstract_norm(text: str) -> str:
    """A paper note's verbatim `## Abstract`, normalized for comparison (#216).

    Lowercased with collapsed whitespace: it is a catalogue copy, so two notes of the same work
    carry it identically except for wrapping. The TITLE is deliberately not compared (measured in
    `openalex.py`: title matching resolved 18 of 25 cases and **2 pointed at a different work**) —
    the verbatim abstract is guaranteed in every note since #124 and is far more specific."""
    span = cfg.section_span(text, "## Abstract")
    if span is None:
        return ""
    cuerpo = text[span[0]:span[1]].split("\n", 1)[-1]
    return " ".join(cuerpo.lower().split())


def basename(p: str) -> str:
    return Path(p).name          # no splitear "/" a mano: glob devuelve separador nativo del OS


def in_dir(path: str, name: str) -> bool:
    """¿`name` es un componente de directorio del path? Por `Path.parts` (separador nativo, #33):
    los literales `"/queries/" in f` no matchean nunca en Windows (glob devuelve `\\`) y los
    chequeos de verificabilidad/cobertura desaparecían en silencio."""
    return name in Path(path).parts


def note_files() -> list:
    """The notes the lint sweeps, in a STABLE order.

    ⛔ `glob` returns **filesystem** order, which differs between machines: since every category
    accumulates its findings in sweep order, the same corpus produced reports with the same lines in
    a different order. Measured: the golden (`test_lint_golden_semilla_fija`) passed locally and
    failed in CI with a diff where **not one finding changed**, only its position — a gate that
    cannot tell a regression from a filesystem. And without this, diffing two lint reports is noise.

    Includes `index.md`/`log.md` (they contribute incoming links); orphanhood excludes them by name."""
    files = glob.glob(str(cfg.WIKI / "**" / "*.md"), recursive=True)
    files += glob.glob(str(cfg.RAW / "refs" / "*.md"))
    return sorted(files)


def _norm_alias(x: str) -> str:
    """Alias comparable: sin espacios ni mayúsculas, sin el `*` de SIMBAD. `GJ 71` == `gj71`."""
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


BIBCODE_RE = re.compile(r"^\d{4}[A-Za-z]")   # heurística: target de link que parece bibcode
# R-3 (decidida con el usuario, 2026-08-24): la marca en línea de una cita a fuente retractada. El
# símbolo es lo que la hace inconfundible con la palabra suelta en prosa; es la hermana de
# `(inferencia de [[b]])` (D-42), y son las dos únicas marcas en línea del sistema.
RETRACTED_MARK = "⛔retractada"
# TERCERA marca en línea del sistema (AUD-42). Las otras dos son `(inferencia de [[b]])` y
# `[[b]] ⛔retractada`. Ésta dice: *el valor de ground-truth que esta frase usó ya no es el que NEA
# publica*. Hace falta porque el ancla de fuente (D-20) hashea `raw/fulltext/**/*.txt` y NUNCA
# `raw/ground_truth/<slug>.json`, así que un valor corregido por NEA cambia **bajo los pies de la
# prosa que lo citó** sin que ninguna fila de verificación se entere — el modo de caducidad más
# silencioso de los cinco, dentro del detector que ya se llamaba "el más silencioso".

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
# Vocabulario de `posiciones[].source` en una disputa. D-2 / INV-77: con una sola entrada las dos
# posiciones de una disputa nea↔simbad decían lo mismo, así que el desacuerdo ENTRE AUTORIDADES no
# era expresable — y desde D-1 es un caso real: NEA y SIMBAD pueden traer `spectral_type` distinto,
# y el que no gana no se tira. `ground_truth` se conserva por las disputas paper↔ground-truth.
# @inv INV-77
DISPUTE_SOURCES = ("ground_truth", "nea", "simbad")


def note_disputes(fm: dict) -> list:
    """Disputas de una nota como `(field, posiciones)`. **Un solo schema**: leer también el viejo
    sería cargar el lint con dos semánticas para siempre, y el schema viejo no sabe expresar la
    mitad de los casos. Lo que sí hace falta es que la presencia del viejo **grite** en vez de
    volverse invisible — eso lo reporta `legacy_disputes` como bloqueante, con el comando.

    Devuelve `(field, posiciones, motivos_de_forma, note)`. Dos detalles que costaron un bug cada uno:
    `field` se lee con `or ""` y **no** con el default de `.get` —la clave presente y **nula**
    (`field:` a secas, la forma normal de dejarla sin llenar) devuelve `None`, y `str(None)` es
    `"None"`, truthy: el chequeo bloqueante "disputa sin `field`" no disparaba—; y `posiciones`
    escalar se reporta en vez de llegar a un `len()` que voltea el lint (o a un string que se
    recorre carácter por carácter, un hallazgo por letra). `normalize_lists` no llega acá: sanea
    el primer nivel del frontmatter, y esto está anidado."""
    out = []
    for d in (fm.get("disputes") or []):
    #  @inv INV-12
        if not isinstance(d, dict):
            continue                       # la forma de la lista ya la reportó normalize_lists
        campo = str(d.get("field") or "").strip()
        pos, motivos = d.get("posiciones"), []
        if pos is not None and not isinstance(pos, list):
            motivos.append(f"disputa `{campo or '?'}`: `posiciones` no es una lista (es "
                           f"{type(pos).__name__}) → no se puede leer ninguna posición")
            pos = []
        # #267 · la `note` viaja con la disputa: sus citas textuales se chequean como las del cuerpo
        # (una fuente de la disputa alcanza), y hasta 1.113.x nadie las miraba.
        out.append((campo, pos or [], motivos, str(d.get("note") or "")))
    return out


# Campos que el schema declara **lista** (CLAUDE.md). `True` = lista de MAPAS.
# `role` no está: su contrato admite escalar o lista, y se valida aparte.
# ⚠ AUD-167 / INV-63 — era un subconjunto A MANO y se le habían quedado afuera campos que el
# schema declara lista igual: `keywords` (D-17: es lo que hace posible el diff de lente offline),
# `versions` (D-19: los bibcodes viejos del mismo trabajo) y `no_vista`/`vistas`/`sources`. Un campo
# que no está acá no se normaliza **ni se reporta**, así que un escalar ahí evade en silencio los
# chequeos por elemento de su tipo — que es exactamente el defecto que esta función existe para
# cerrar, con la lista de campos como único punto de fuga.
LIST_FIELDS = {"tags": False, "aliases": False, "stars": False, "facets": False, "methods": False,
               "thesis_links": False, "activity_indicators_expected": False,
               "keywords": False,
               "planets": True, "disputes": True, "corrections": True,
               "versions": True, "vistas": True, "no_vista": True}


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
    #  @inv INV-63
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
    #  @inv INV-13
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


# Los dos vocabularios cerrados que este lint valida como bloqueantes. Se LEEN de `lib_config`, no se
# re-declaran: hasta #175 `HYP_STATUS` vivía sólo acá y el generador de notas escribía `active`, o
# sea que la máquina producía su propia violación. Un typo en cualquiera de los dos deja el campo
# mudo para la operación que lo consume —el contraste cross-paper en `role`, la decisión de apoyarse
# en la hipótesis en `status`—, el mismo modo de falla de un `thesis_links` sin destino.
#  @inv INV-46
HYP_STATUS = cfg.HYP_STATUS
#  @inv INV-46
ROLES = cfg.ROLES


# ── espejo puro de NEA (#70) ─────────────────────────────────────────────────
# Campos de `stars/` que los scripts copian del ground-truth: (campo en la ficha, clave en el JSON).
# El contrato es que valen lo que dice NEA/SIMBAD **o nada** — la cabecera promete que el
# frontmatter es la capa auditable, y un número extraído por un LLM ahí es indistinguible del de
# NEA. Los nulls de NEA son el caso NORMAL (pl_rvamp y pl_orbeccen faltan seguido): rellenarlos con
# literatura borra la distinción. Hasta 1.13.0 nada lo detectaba —el único chequeo comparaba el
# NÚMERO de planetas, nunca los valores—, así que la promesa no tenía quién la sostuviera.
MIRROR_HOST = (("spectral_type", "spectral_type"), ("teff_K", "teff_K"),
               ("dist_pc", "dist_pc"), ("P_rot_days", "st_rotp_days"),
               ("mass_msun", "mass_msun"))   # #272
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
# Respaldo válido de un P_rot: un wikilink, o una marca de inferencia **con premisas**. La
# palabra `inferencia` pelada NO cuenta (D-42/INV-86): aceptarla dejaba declarar un período
# "documentado" sin una sola fuente, que es el sumidero por donde una afirmación `no-soportada`
# sobrevive cambiándole la etiqueta.
PROT_CITE = re.compile(r"\[\[[^\]]+\]\]")
PROT_NEG = re.compile(r"(?i)no se conoce|no se sabe|sin medir|desconocid|no hay |ausen"
                      r"|falta[ns]? |sin determinar|nunca se|no\s+(?:est[áa]|fue|ha sido)?"
                      r"\s*(?:medid|determinad|conocid|publicad)")


# D-42 / INV-86. La marca de inferencia es la que va **entre paréntesis** al cierre de una
# afirmación —`(inferencia de [[b1]], [[b2]])`—, y es una de las dos únicas marcas en línea del
# sistema (la otra es `⛔retractada`). Se busca así, y no por la palabra suelta, para no disparar
# con el sustantivo común: "la inferencia bayesiana permite…" no es una marca.
#
# ⛔ Ancla al **PRINCIPIO del paréntesis**, no en la palabra suelta en cualquier posición. La marca
# abre con `inferencia`; la prosa del dominio la lleva precedida de artículo («la inferencia…»).
# La forma vieja tenía los dos errores a la vez, medidos el 2026-08-28 en una bóveda cuyo dominio
# **incluye** inferencia bayesiana y procesos gaussianos:
#   · falso POSITIVO bloqueante — `"Usamos GP (la inferencia bayesiana es cara) para el ajuste."`
#     y `"(inferencia de hiperparámetros por MCMC)"` se reportaban como marca pelada;
#   · falso NEGATIVO — `"X (inferencia (mi lectura))."` no matcheaba, porque `[^()]*` no cruza un
#     paréntesis interno: el mismo texto disparaba o no según un paréntesis anidado.
# ⚠ La `(inferencia)` **pelada** tiene que seguir cazándose: es el abuso central que INV-86 persigue
# —una afirmación sin respaldo disfrazada de marca—, así que el `de` NO puede ser obligatorio.
# Y se admite **un nivel de anidado** (`(inferencia (mi lectura))`), que `[^()]*` no cruzaba.
# `(inferencia de hiperparámetros…)` queda como falso positivo aceptado: es prosa que abre igual que
# la marca, y ahí el aviso es barato de resolver.
# #276 — el `[`*_~]*` NO es cosmético: sin él el bloqueante es ciego al énfasis markdown, y
# `CLAUDE.md` **induce** la forma que no ve (escribe `(inferencia de [[b1]])` en la sección de
# las cinco marcas y ``marcado **`inferencia`**`` en la cascada de ingest y en el espejo #70).
# Medido sobre una ficha real: de sus 5 marcas de prosa, 3 llevan backticks y el detector veía
# **2 de 5** — un ⛔ que existe para que ninguna afirmación sin respaldo se disfrace de
# inferencia, sin mirar el 60 % de su población. Es #168 otra vez: `lib_blocks._ADORNO` existe
# exactamente por esto («no cambian NADA de lo que la fila dice, pero con la comparación
# literal cualquiera de los tres apagaba el bloqueante») y la comprensión no había llegado acá.
INFER_MARK = lb.INFER_MARK      # #280: una sola definición, en `lib_blocks` (la cuentan dos consumidores)


def inferencias_sin_premisas(body: str) -> list[str]:
    """Marcas `(inferencia …)` que no nombran **ninguna** premisa `[[bibcode]]`.

    Sin premisas no es una inferencia: es una afirmación sin respaldo con otra etiqueta, y encima
    una que ni el verify ni el lint pueden chequear —el verify necesita un bibcode que leer—. Por
    eso bloquea: es el mismo criterio de la frontera dura (regla #0), no un backlog.

    ⚠ La premisa tiene que ser un **bibcode**, no cualquier `[[wikilink]]`. Hasta 1.36.0 el filtro
    era `"[[" not in ...`, así que `(inferencia de [[gp-kernels]])` —un link a una nota de
    concepto— pasaba limpia: el verify no tiene ahí ningún `.txt` que leer, que es justo lo que la
    marca promete. `BIBCODE_RE` es la misma heurística que usa el barrido de citas.  @inv INV-86"""
    return [m for m in lb.inference_marks(body)
            if not any(BIBCODE_RE.match(t.split("|")[0].split("#")[0].strip())
                       for t in re.findall(r"\[\[([^\]]+)\]\]", m))]


# #278 — la prosa que afirma algo sobre la AUTORIDAD y su ground-truth desmiente. El espejo #70
# vigila el frontmatter campo por campo y **nunca el cuerpo**, así que una ficha podía publicar
# «NEA publica las dos como confirmed» sobre un planeta que NEA no lista — falso contra cuatro
# lugares del mismo archivo, con el lint en verde. `verify-citations` no lo cubre (los valores de
# ground-truth están exentos por contrato) y `find-contradictions` compara claim↔claim entre
# fuentes, no contra la autoridad.
GT_AUTHORITY = re.compile(r"\bNEA\b|NASA Exoplanet Archive|ground[-\s]truth", re.I)
GT_VERB = re.compile(r"\b(publica|lista|trae|confirma|reporta|da)\b|\bconfirmed\b", re.I)
GT_NEG = re.compile(r"\b(no|tampoco|sin)\b", re.I)
# La letra sólo cuenta si la oración la INTRODUCE como planeta/señal: un `` `e` `` suelto es la
# excentricidad y `` `b.K` `` es un campo de disputa. Sobre-restringir acá es correcto: el falso
# positivo erosiona la categoría, y el punto ciego queda declarado.
GT_INTRO = re.compile(r"\b(planetas?|se[ñn]al(?:es)?|candidatas?)\b", re.I)
GT_LETTER = re.compile(r"`([b-z])`")
GT_ANAPHORA = re.compile(r"\b(?:la[s]?\s+(dos|tres|cuatro)|ambas|ambos)\b", re.I)
_ARIDAD = {"dos": 2, "tres": 3, "cuatro": 4, "ambas": 2, "ambos": 2}


def gt_prose_conflicts(prose: str, gt_letters: set) -> list:
    """Prose sentences stating what the ground-truth authority lists, denied by the JSON (#278).

    `[(sentence, reason)]`. The sentence is reported whole (#236: the wording is the evidence).

    Deliberately narrow, because a false positive erodes the category: the sentence must name the
    authority AND a verb of listing, and the letter must be introduced as a planet/signal. An
    anaphora («las dos») resolves backwards **within the same sentence block** and only if it finds
    exactly that many letters — otherwise the sentence is dropped as not evaluable, never guessed."""
    out: list = []
    letras_previas: list = []
    for oracion in re.split(r"(?<=[.;])\s+|\n\s*\n", prose or ""):
        propias = GT_LETTER.findall(oracion) if GT_INTRO.search(oracion) else []
        if not (GT_AUTHORITY.search(oracion) and GT_VERB.search(oracion)):
            if propias:
                letras_previas = propias
            continue
        letras = propias
        if not letras and (m := GT_ANAPHORA.search(oracion)):
            n = _ARIDAD.get((m.group(1) or m.group(0)).lower().strip())
            letras = letras_previas if n and len(letras_previas) == n else []
        negada = bool(GT_NEG.search(oracion[:GT_VERB.search(oracion).end()]))
        for letra in letras:
            if not negada and letra not in gt_letters:
                out.append((oracion.strip(),
                            f"afirma que la autoridad lista `{letra}` y el ground-truth no lo trae"))
            elif negada and letra in gt_letters:
                out.append((oracion.strip(),
                            f"afirma que la autoridad NO lista `{letra}` y el ground-truth sí lo trae"))
        if propias:
            letras_previas = propias
    return out


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


# AUD-198 — los dos umbrales que deciden categorías BLOQUEANTES viven acá, con nombre y motivo, en
# vez de como literales sueltos adentro de un `if`. No cambian de valor: lo que cambia es que ahora
# se pueden citar, testear y discutir. Un número mágico dentro de una guarda es una decisión que
# nadie firmó — el mismo argumento por el que `fundacional_min_citas` se declara en la config.
ESPEJO_TOL_REL = 1e-6
"""Tolerancia RELATIVA del espejo #70. Los números viajan por YAML y por JSON: `34.0` y `34` son el
mismo valor, y `0.1 + 0.2 != 0.3` en binario. No es una tolerancia física —no admite «casi igual»—
sino de representación: cualquier discrepancia real es órdenes de magnitud mayor."""

MASA_FACTOR_SOSPECHA = 3.0
"""Cuántas veces puede diferir `mass_earth` de la m·sini implícita (K/P/e/M*) antes de reportarlo.

El factor NO es una barra de error: la m·sini implícita se deriva de cuatro valores que NEA publica
por separado y que pueden venir de análisis distintos, así que un factor 2 entre ellas es ruido de
procedencia y no un error. El 3 es el corte donde deja de ser explicable así — típicamente una
best-mass espuria (una masa verdadera de un ajuste dinámico mezclada con la K de otro). Es
deliberadamente flojo: el detector existe para cazar el disparate, no para auditar la astrofísica."""


def same_value(a, b) -> bool:
    """¿El valor de la ficha es el del ground-truth? Los números viajan por YAML y JSON, así que se
    comparan con tolerancia relativa (un 34.0 vs 34 no es una discrepancia); el resto, textual."""
    if a is None or b is None:
        return a is None and b is None
    if (isinstance(a, (int, float)) and isinstance(b, (int, float))
            and not isinstance(a, bool) and not isinstance(b, bool)):
        return abs(a - b) <= ESPEJO_TOL_REL * max(1.0, abs(b))
    return str(a).strip() == str(b).strip()


def mirror_issues(slug: str, fm: dict, gt: dict) -> list:
    """Campos de la ficha que NO son espejo del ground-truth (#70). Dos formas, y la distinción
    importa porque el arreglo es distinto: **difiere** (la ficha dice otra cosa que NEA → si viene
    de un paper es una `disputes[]`, no una sobreescritura) y **sin respaldo** (NEA no tiene el
    valor y la ficha sí → el número salió de la literatura y va al cuerpo, citado)."""
    # @inv INV-06, INV-09
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



# ── el resultado del lint, estructurado (10.1) ───────────────────────────────────────────────────
#
# `main()` tenía 1.100 líneas y las ~48 listas de hallazgos vivían sueltas en su cuerpo, así que el
# único consumidor posible del lint era **leer su texto**. Peor: la severidad de cada categoría
# estaba declarada DOS veces —el título decía "(backlog)" o llevaba "⚠ WARN", y la pertenencia a
# `n_block` decidía el exit— sin nada que las atara. Agregar una categoría al reporte y olvidarla en
# `n_block` (o al revés) no rompía ningún test: es la familia del mapa que atribuye mal, en el
# artefacto que mide a la bóveda. Acá la severidad se declara **una vez**, en la tabla, y el exit se
# deriva de ella.

VIA_FUENTE_OK = {"usuario", "descubrimiento"}   # procedencia de una fuente off-ADS (#111, #206)
VIA_FUENTE_RETIRADO = {"reporte": "`via: usuario` + el documento nombrado en `motivo`"}

SEV_BLOQUEANTE = "bloqueante"      # viola el contrato: exit 1 siempre
SEV_CIERRE = "cierre"              # bloquea SÓLO con `--cierre` (R-1: pares vencidos)
SEV_WARN = "warn"                  # heurística de alta señal: se revisa a mano, no frena
SEV_BACKLOG = "backlog"            # deuda visible: no invalida lo que hay


@dataclass(frozen=True)
class Categoria:
    """Una categoría del reporte: su clave estable, su título, su severidad y sus hallazgos.

    `clave` es el nombre de la lista en `collect` y es lo **estable**: el título es prosa que se
    reescribe (y de hecho se reescribió muchas veces), así que un consumidor que matchee por texto
    se rompe con cada mejora de redacción."""
    clave: str
    titulo: str
    severidad: str
    items: tuple
    suprimida: bool = False
    # INV-40 — la clave de la POBLACIÓN sobre la que corrió este chequeo (ver `POBLACIONES`). Un
    # `(0)` no dice si el chequeo miró 412 notas o ninguna, así que «cada chequeo se aplica a toda
    # la población que declara cubrir» no era verificable desde la salida: es la mitad que le
    # faltaba al invariante. Vacío = **no declarada**, que el reporte dice en vez de inventar un
    # denominador — un denominador equivocado es peor que ninguno (regla de método #4).
    poblacion: str = ""

    def __len__(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class LintResult:
    """Lo que el lint **encontró**, sin renderizar. `render()` lo convierte en el reporte y
    `main()` decide el exit; un consumidor (el tablero, un test, otro script) lo lee directo.

    `alcance` es #121: los stems de nota del sujeto que la operación tocó. **Acota SÓLO la
    severidad `cierre`**, que es la que el flag promueve — un `bloqueante` sigue contando venga de
    donde venga, porque si no `--cierre <slug>` sería un gate MÁS DÉBIL que un `lint` pelado, que es
    lo contrario de para qué existe."""
    categorias: tuple
    cierre: bool = False
    slug: str | None = None
    alcance: frozenset = frozenset()
    poblaciones: dict = field(default_factory=dict)   # INV-40: clave → (n, qué se contó)

    def por_clave(self, clave: str) -> Categoria | None:
        return next((c for c in self.categorias if c.clave == clave), None)

    def en_alcance(self, c: Categoria) -> tuple:
        """Los ítems de `c` que cuentan para el exit. Sin `slug`, todos.  @inv INV-105"""
        if self.slug is None or c.severidad != SEV_CIERRE:
            return c.items
        return tuple(it for it in c.items if it[0] in self.alcance)

    def bloquean(self) -> tuple:
        """Las categorías que cuentan para el exit ≠ 0, con la severidad como única fuente."""
        sevs = {SEV_BLOQUEANTE} | ({SEV_CIERRE} if self.cierre else set())
        return tuple(c for c in self.categorias
                     if c.severidad in sevs and self.en_alcance(c))

    def n_block(self) -> int:
        return sum(len(self.en_alcance(c)) for c in self.bloquean())


def diverged_copies(copies: dict) -> list:
    """Bibcodes whose `.txt` copies do NOT agree byte for byte across slugs (#190).

    `copies` maps bibcode -> content hash -> the `raw/`-relative paths carrying that hash, and is
    built by `collect` inside the loop that already reads every fulltext file, so this check costs
    no extra I/O — the point of the issue. One hash per bibcode (the normal state: D-18 copies the
    artefact, `raw/` is immutable) yields nothing.

    Two hashes mean somebody re-extracted under one slug and not under the other: `extract_fulltext`
    rewrites the `.txt` in three cases (`--force`, the automatic OCR upgrade, the mark backfill) and
    none of them propagates to the other copies. It is reported, never repaired here: copying the
    "good" one over the others would hide the fact that half a corpus was re-extracted.

    @inv INV-135"""
    out = []
    for bib in sorted(copies):
        by_hash = copies[bib]
        if len(by_hash) < 2:
            continue
        detail = " · ".join(f"`{h}` ← {', '.join(paths)}"
                            for h, paths in sorted(by_hash.items()))
        out.append((bib, f"{len(by_hash)} versiones distintas del mismo `.txt` entre slugs: "
                         f"{detail}. `raw/` es inmutable, así que esto no es deriva: alguien "
                         f"re-extrajo bajo un slug y no bajo el otro (`--force`, upgrade a OCR o "
                         f"backfill de marcas — ninguno propaga a las otras copias). El ancla de "
                         f"fuente (D-20) hashea UNA sola copia, así que los pares verificados "
                         f"contra las demás se comparan contra un archivo que nunca leyeron. "
                         f"Decidí cuál es la buena y re-extraé la otra "
                         f"(`python scripts/extract_fulltext.py <slug> --force`); NO copies a "
                         f"ciegas, taparía que alguien re-extrajo medio corpus"))
    return out


def collect(cierre: bool = False, slug: str | None = None) -> LintResult:
    """Barre la bóveda entera y devuelve lo que encontró, **sin renderizar nada**.

    `cierre` es R-1: el MISMO detector de pares vencidos con dos severidades según el
    momento. Va acá y no en `render` porque cambia el exit, no el texto.

    `slug` es #121: acota el EXIT a las notas de ese sujeto (el barrido sigue siendo de la bóveda
    entera — la deuda ajena se reporta igual, sólo que no frena una operación que no la causó).
    `ValueError` si el slug no existe: acotar a una entidad inexistente daría 0 hallazgos en
    alcance, o sea un verde inventado, que es el falso limpio que este lint existe para no
    producir."""
    # ⚠ `slug` se REBINDEA más abajo (el barrido lo usa como variable de loop en cuatro lugares),
    # así que el alcance se captura ACÁ. Sin esta línea el resultado se etiquetaba con el último
    # slug que tocó el barrido — un alcance inventado, y encima plausible.
    alcance_slug, alcance = slug, frozenset()
    if slug is not None:
        stems = entity.notas_del_slug(slug)
        if stems is None:
            raise ValueError(f"entidad desconocida: {slug!r} — no está en stars.yaml ni en "
                             f"themes.yaml, así que `--cierre {slug}` no acota nada")
        alcance = frozenset(stems)
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
    # Hash de fuente (D-20) por bibcode, calculado sobre la MISMA lectura que ya hace `is_legible`
    # —el 77% de los 5,6 s del lint sobre 908 notas—: cero lecturas extra. El hashing de ~66 MB es
    # marginal frente al parseo YAML. Si un bibcode vive bajo varios slugs con contenido idéntico,
    # el hash coincide; si difieren, gana el primero en orden alfabético (determinista).
    ft_hash: dict[str, str] = {}
    # #190: el `setdefault` de arriba se queda con UNA copia y descarta el resto — determinista,
    # y con `vistas[]` (#188) insuficiente: la vista de un sujeto se escribe leyendo el `.txt` de
    # SU slug y el ancla la compararía contra el de otro. Se acumulan las copias por bibcode
    # (mismo bucle, misma lectura: cero I/O extra) y `diverged_copies` las compara después.
    ft_copies: dict[str, dict[str, list]] = {}
    for p in fulltext_files:
        contenido = open(p, encoding="utf-8", errors="replace").read()
        _bib, _h = basename(p)[:-4], lb.sha10(contenido)
        ft_hash.setdefault(_bib, _h)
        ft_copies.setdefault(_bib, {}).setdefault(_h, []).append(
            Path(p).relative_to(cfg.RAW).as_posix())
        ok, why = is_legible(contenido)
        if not ok:
            illegible_txt.append((Path(p).relative_to(cfg.RAW).as_posix(), why))
    divergent_txt = diverged_copies(ft_copies)
    # PDFs en disco (un <bibcode>.pdf por slug en vault/raw/pdfs/) → chequear drift `pdf` ↔ archivo.
    # stem = safe_name(bibcode), igual que el nombre de la nota del paper.
    pdf_on_disk = {}
    for _p in glob.glob(str(cfg.PDFS / "**" / "*.pdf"), recursive=True):
        pdf_on_disk.setdefault(basename(_p)[:-4], _p)
    unverifiable: list = []            # (stem, "cita <bibcode> sin fulltext")
    coverage: list = []                # concept/hipótesis sin citas [[bibcode]] → no chequeable
    unverified: list = []              # query/concept CON citas pero SIN bloque de verify-citations
    # Alias que SIMBAD no reconoce (#82): el lado "de más" del recall. `_unresolved_aliases` lo
    # persiste `fetch_ground_truth`; acá se surface OFFLINE, que es donde se mira. `null` significa
    # "SIMBAD no contestó" y NO es lo mismo que `[]`: se reporta como sin verificar, no como limpio.
    alias_ajenos: list = []
    alias_faltantes: list = []         # (slug, motivo) — #82: SIMBAD los conoce y la bóveda no
    alias_rechazados: list = []        # (slug, motivo) — #252: considerado y rechazado, no es deuda
    for gt in sorted(cfg.GROUND_TRUTH.glob("*.json")) if cfg.GROUND_TRUTH.exists() else []:
        try:
            data = json.loads(gt.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue                      # el JSON roto ya lo reporta el barrido del espejo (#70)
        if not isinstance(data, dict) or "_unresolved_aliases" not in data:
            continue                      # snapshot anterior a #82: nada que decir
        # #82, lado de MENOS: identificadores que SIMBAD lista y `stars.yaml` no declara. Cada uno
        # que falta degrada los TRES mecanismos de recall a la vez —query directa, `--sweep` y
        # rescate por glifo— y el modo de falla es silencioso: un paper que nunca aparece. Es
        # PROPUESTA, no adopción: SIMBAD devuelve identificadores que no sirven para buscar texto
        # (Gaia DR3, 2MASS J…) junto a los que sí, así que cuáles entran es curación humana.
        _decl, _rechazados = set(), {}
        if not cfg.stars_error():
            for _n, _m in cfg.load_stars().items():
                if isinstance(_m, dict) and _m.get("slug") == gt.stem:
                    _decl = {_norm_alias(x) for x in
                             [_n, _m.get("simbad"), _m.get("ads_object"), *cfg.as_list(_m.get("aliases"))]
                             if x}
                    # #252 — el identificador CONSIDERADO Y RECHAZADO no es deuda. Era el único
                    # carril de curación sin escotilla del NO, y el propio mensaje del hallazgo
                    # manda dejar afuera el catálogo-máquina: instruía descartar y reportaba el
                    # descarte para siempre. Va a su PROPIA categoría, como `no_vista`.
                    _rechazados = {_norm_alias(x["id"]): x["motivo"]
                                   for x in cfg.load_discarded_aliases(_m, entry=str(_n))}
        # ⛔ `None` (SIMBAD no contestó) ≠ `[]` (contestó y no hay más). `as_list` los aplana a los
        # dos en `[]`, y ahí «cero alias faltantes» se lee como «está todo declarado» sobre una
        # consulta que nunca volvió — el falso limpio de D-43 en el chequeo que INV-122 sostiene.
        _crudo = data.get("_simbad_aliases", "__ausente__")
        if _crudo is None:
            alias_faltantes.append(
                (gt.stem, "⛔ NO EVALUADO: `_simbad_aliases` es `null` — SIMBAD no contestó cuando "
                          "se bajó este ground-truth, así que no consta qué identificadores conoce. "
                          "Re-corré `fetch_ground_truth.py` para saberlo (no es «están todos "
                          "declarados»)"))
        _conocidos = cfg.as_list(_crudo if _crudo != "__ausente__" else None)
        _faltan = [a for a in _conocidos
                   if _norm_alias(a) not in _decl and _norm_alias(a) not in _rechazados]
        for a in _conocidos:
            if _norm_alias(a) in _rechazados:
                alias_rechazados.append(
                    (gt.stem, f"`{a}` — considerado y rechazado: {_rechazados[_norm_alias(a)]}"))
        if _faltan:
            alias_faltantes.append(
                (gt.stem, f"SIMBAD conoce {len(_faltan)} identificador(es) que `stars.yaml` no "
                          f"declara: {', '.join(_faltan[:8])}"
                          + (" …" if len(_faltan) > 8 else "")
                          + " → elegí los que sirvan para buscar (los `Gaia DR3`/`2MASS J` no) y "
                            "agregalos a `aliases:`"))
        for alias in cfg.as_list(data.get("_unresolved_aliases")):
            alias_ajenos.append((gt.stem, f"alias `{alias}` declarado en stars.yaml pero SIMBAD no lo "
                                          "lista como identificador de esta estrella → puede resolver "
                                          "a OTRO objeto y meter sus papers al corpus"))

    # merge=ours sin driver registrado (#99): la protección de los archivos de instancia no existe.
    sin_driver, driver_err = merge_ours_unprotected()
    if driver_err:
        not_evaluated.append(("driver de `merge=ours`", driver_err))
    merge_ours = [(pat, "tiene cambios propios y está declarado `merge=ours`, pero el clon NO "
                        "registró el driver → el próximo `git pull` los pisa con la versión del "
                        "template. Arreglo: `git config merge.ours.driver true` (una vez por clon)")
                  for pat in sin_driver]

    # ── "no evaluado" (D-43 / INV-87) ────────────────────────────────────────────────────────────
    # Un chequeo que NO PUDO correr no aporta un cero: reporta error. La diferencia no es
    # cosmética — un "(0)" se lee como veredicto ("miré y no hay"), y ese cero inventado hacía que
    # el lint afirmara salud sobre lo que nunca miró. Cada poblador agrega (qué chequeo, por qué),
    # la categoría CUENTA para el exit ≠ 0, y la categoría normal correspondiente se SUPRIME del
    # reporte en vez de mostrar su cero. Se declara acá arriba porque los pobladores están
    # repartidos por todo `main()`.
    not_evaluated: list = []
    anchor_bodies: dict = {}           # {archivo: texto} de TODA nota de entidad/query — D-47
    old_registro: list = []            # registros con la clave `busqueda:` (schema pre-D-28)
    registro_ilegible: list = []       # registro que no parsea → la curación queda sin aplicar (AUD-131)
    schema_incompleto: list = []       # (stem, claves) — INV-63: el tipo de nota declara campos que la nota no trae
    old_facets: list = []              # notas de paper con `topics:` (schema pre-R-5)
    infer_sin_premisas: list = []      # marcas `(inferencia …)` sin ningún [[bibcode]] (D-42)
    bad_status: list = []              # `status` de hipótesis fuera del vocabulario (D-37)
    status_vs_evidencia: list = []     # `sostenida` con filas `desafía` (D-37 / #177)
    alcance_corto: list = []           # (stem, motivo) — alcance de hipótesis sin declarar o vencido (D-34)
    old_bearing: list = []             # `bearing` en nota de paper: schema pre-D-21
    sin_destino: list = []             # paper sin stars/thesis_links/methods (D-23)  @inv INV-94
    cadena_incompleta: list = []       # (slug, "se cortó en <paso>") — D-57
    # `stars.yaml`/`themes.yaml` ilegibles no pueden tumbar el lint: se declaran NO EVALUADO y los
    # chequeos que dependen de ellos se saltean con población vacía (INV-80/INV-87).
    subj_err = [e for e in (cfg.stars_error(), cfg.themes_error()) if e]
    for e in subj_err:
        not_evaluated.append(("config de sujetos", e))
    stars_slugs = (set() if cfg.stars_error() else
                   {m.get("slug") for m in cfg.load_stars().values() if isinstance(m, dict)})
    verif_blocks: list = []            # (archivo, fecha del bloque|None) — notas CON bloque de verify
    anchor_notes: list = []            # (stem, texto) de esas mismas notas — insumo del ancla (D-4)
    names = {basename(p)[:-3] for p in files}  # stems referenciables por [[..]]
    incoming: dict[str, int] = {n: 0 for n in names}
    kinds: dict[str, list] = {}
    broken, incomplete, contradictions = [], [], []
    fm_broken: list = []               # (stem, motivo) — frontmatter no parseable o con forma
                                       # inválida (evade los chequeos por elemento de su tipo)
    retracted: list = []               # (stem, "<tipo> <fecha>") — papers marcados retracted (check_retractions)
    corrections: list = []             # (stem, "<tipo> (<fecha>)") — corrección no-retractante (#52)
    pending_srcs: list = []            # (stem, "<motivo> — puntero") — fuentes derivadas al usuario
    campos_txt_viejos: list = []       # (stem, motivo) — #205: `symbols_lost`/`fulltext_layout`
    log_sin_entrada: list = []         # (slug, motivo) — #118: la cadena corrió y el log no lo dice
    sweep_pendiente: list = []         # (slug, motivo) — #88: el barrido 2b no consta en el registro
    impl_leaks: list = []              # (stem, "línea N: marcador → texto") — fuga de implementación
    cond_sin_clasificar: list = []     # (stem, motivo) — #221: condición sin `acota:`/`contextualiza:`
    verif_truncada: list = []          # (stem, motivo) — #226: `Evidencia`/`Condición` cortada
    verif_sin_localizador: list = []   # (stem, motivo) — #226: #122 no evaluable en esa fila
    indice_viejo: list = []            # (stem, motivo) — #237: index.md contra la verdad de disco
    radio_sin_link: list = []          # (stem, motivo) — #235: hub que nombra un radio sin wikilink
    sin_abstract: list = []            # (stem, motivo) — #277: nota de paper sin `## Abstract`
    sin_conclusiones: list = []        # (stem, motivo) — #277: sin `## Conclusiones` ni exención
    sin_conclusiones_ok: list = []     # (stem, motivo) — #277: declarado con motivo (visible, no es deuda)
    sin_aviso_llm: list = []           # (stem, motivo) — #247/#277: nota de paper sin el aviso de capa LLM
    indicador_sin_destino: list = []   # (stem, motivo) — #250: indicador sin nota de concepto
    vista_ejes_faltantes: list = []    # (stem, motivo) — #270: la vista no cubre su propia lente
    segunda_mano: dict = {}            # {bibcode: [(qué, valor, de quién)]} — #279
    segunda_mano_perdida: list = []    # (stem, motivo) — #279: la ficha se apoya y no lo dice
    cita_log: list = []                # (stem, motivo) — #238: cita del `log.md` que su fuente no dice
    cita_no_verbatim: list = []        # (stem, motivo) — #220: la cadena no está en el `.txt`
    cita_inventada: list = []          # (stem, motivo) — #318: ni en el `.txt` NI en la extracción
    cita_txt_degradado: list = []      # (stem, motivo) — #288: la fuente la dice, el `.txt` la parte
    cita_opaca: list = []              # (stem, motivo) — #220: no evaluable (sin `.txt` / ocr; #275)
    verificar_pdf: list = []           # (stem, motivo) — #225: marcada para chequear contra el PDF
    forma_rota: list = []              # (stem, motivo) — #227: fila de tabla que NO renderiza
    forma_sospechosa: list = []        # (stem, motivo) — #227: backtick abierto, párrafo duplicado
    # D-50: los genéricos + un patrón por consumidor declarado. Se arma UNA vez por corrida, no por
    # línea: el scan recorre el cuerpo de toda nota de la bóveda.
    leak_patterns = IMPL_LEAK_RE + downstream_leaks(cfg.load_downstream())
    pdf_issues: list = []              # (stem, ...) — drift frontmatter `pdf` ↔ PDF en disco
    headerless: list = []              # (stem, motivo) — ficha/concepto sin cabecera estampable (#69)
    estado_desfasado: list = []        # (stem, motivo) — #233: la cabecera no es la que el estampador da
    salv_sin_marca: list = []          # (stem, motivo) — #234: salvedades sin la marca de #213
    salv_decidible: list = []          # (stem, motivo) — #234: salvedad en prosa que parece chequeable
    faceta_sin_frontera: list = []     # (faceta, motivo) — #236: token corto que matchea dentro de palabra
    faceta_muerta: list = []           # (faceta, motivo) — #291: alternativa con POBLACIÓN CERO
    reuso_sin_chequear: list = []      # (stem, motivo) — #297: artefacto reusado, antigüedad no mirada
    version_publicada: list = []       # (stem, motivo) — #298: el preprint citado teniendo publicado
    status_apilado: list = []          # (archivo, motivo) — #302: el STATUS se volvió bitácora
    alcance_desfasado: list = []       # (stem, motivo) — #312: la nota y `sources[]` no coinciden
    thesis_refs: dict[str, list] = {}  # valor de thesis_link -> notas que lo usan
    method_refs: dict[str, list] = {}  # valor de methods -> notas de paper que lo declaran
    dispute_refs: list = []            # (nota, field, ref) de las posiciones de cada disputa (#71)
    bad_disputes: list = []            # (nota, motivo) — disputa mal formada (#71)
    old_disputes: list = []            # (nota, motivo) — disputas en el schema pre-1.19.0 (#71)
    bad_roles: list = []               # (stem, valor) — `role` fuera del vocabulario cerrado (#73)
    cited_in_entity: set = set()       # bibcodes citados desde una ficha/concepto (#75)
    extracted: list = []               # (stem, marca `no_sintetizado`) de papers YA extraídos (#75)
    bad_decisions: list = []           # (slug, clave) — decisión del registro que no es un mapa
    lente_desync: list = []            # (slug, delta) — la lente cambió desde la última corrida (D-49)
    bad_sources: list = []             # `sources:` sin via/motivo o con via inválida (#111)
    artefactos_colgados: list = []     # (capa, motivo) — capa de una entidad que ya no existe (INV-19)
    # #188 · `vistas[]`: la extracción es una lectura CON LENTE y la nota tiene que decir cuál.
    vistas_schema_viejo: list = []     # (stem, motivo) — `## Extracción (LLM)` sin `vistas[]`
    vistas_vs_cuerpo: list = []        # (stem, motivo) — vista sin sección, o sección sin vista
    reclamo_sin_vista: list = []       # (stem, sujeto) — lo reclama y nadie lo leyó desde ahí
    reclamo_sin_vista_declarado: list = []   # ídem, con la escotilla `no_vista` y su motivo
    vista_sin_fecha: list = []         # (stem, sujeto) — vista declarada y sin fecha: sin leer
    vista_sin_fuente: list = []        # (stem, sujeto) — #207: no consta de qué se construyó
    vista_solo_abstract: list = []     # (stem, sujeto) — #207: se leyó el abstract, falta el PDF
    vista_sin_fuente_en_disco: list = []   # (stem, sujeto) — #217: leída y ya no re-verificable
    reclamo_refutado: list = []        # (stem, sujeto) — #212: la vista lo refuta y sigue reclamado

    # Los temas DECLARADOS (su `concept`, que es el nombre con el que un paper los nombra en
    # `thesis_links`/`methods`). Una lectura del YAML por corrida, no por nota.
    # `themes_error()` primero, el idioma del resto del archivo: con el YAML roto, `load_themes`
    # LEVANTA y se llevaba puesto al lint entero — justo el "⛔ No evaluado" que INV-80 exige que se
    # reporte en vez de morirse. El caso ya está declarado arriba (`subj_err`), así que acá alcanza
    # con no contar reclamos por `methods`.
    conceptos_de_temas = {str(m.get("concept") or slug_t)
                          for slug_t, m in ({} if cfg.themes_error() else cfg.load_themes()).items()
                          if isinstance(m, dict)}
    refs_dir = str(cfg.RAW / "refs")
    refs_stems = {basename(f)[:-3] for f in files if f.startswith(refs_dir)}  # docs de diseño, no fichas
    #: #235 — los slugs de `concepts/`, para reconocer un radio nombrado como código.
    _CONCEPT_SLUGS = {p_.stem for p_ in cfg.CONCEPTS.glob("*/*.md")} if cfg.CONCEPTS.exists() else set()

    _fm_cache: dict = {}

    def paper_fm(bib: str) -> dict:
        """Frontmatter of a paper note, read on demand.

        Deliberately NOT `paper_fms`: that one is filled by the main loop, so mid-loop it holds
        whatever happened to be parsed first — a checker that reads it from inside the loop would
        answer differently depending on filename order.
        """
        # El loop principal ya parsea cada nota y guarda el resultado en `paper_fms`: reusarlo es
        # gratis. El re-parseo queda sólo para el paper que todavía no llegó en el recorrido —sin
        # eso, esta función duplicaba el parseo de TODO el corpus de papers (medido: el ratio de
        # `yaml.safe_load` por nota saltó de 2,0x a 3,2x sobre 900 notas, y el tier `poblada` lo
        # reporta como regresión de escala).
        if bib in paper_fms:
            return paper_fms[bib]
        if bib not in _fm_cache:
            _f = cfg.PAPERS / f"{bib}.md"
            try:
                _fm_cache[bib] = split_fm(_f.read_text(encoding="utf-8")) if _f.exists() else {}
            except Exception:
                _fm_cache[bib] = {}
        return _fm_cache[bib]

    _alias_idx: dict = {}

    def _alias_idx_cached() -> dict:
        """The concept alias index (#245), built once per run.

        `concept_alias_index` reads every note of `concepts/`: calling it per indicator turns a
        cheap check into an O(notas × conceptos) sweep."""
        if not _alias_idx:
            _alias_idx.update(cfg.concept_alias_index() or {"__vacio__": ""})
        return _alias_idx

    _src_cache: dict = {}
    #: #275 · cuántas citas «…» se pudieron EVALUAR de verdad. La categoría declaraba su población
    #: en notas, así que un `(0)` sobre población efectiva CERO —45 de 49 papers exentos— se leía
    #: como «miré y está limpio». Se cuenta acá, donde el chequeo ocurre.
    _n_citas_evaluadas = [0]

    def _source_readings(txt_path) -> list:
        """Normalized readings of a `.txt`, one per physical column, memoised (#275).

        Memoised because the check runs per citing BLOCK: a note with 88 blocks citing 49 papers
        would otherwise de-interleave and normalise the same file dozens of times."""
        clave = str(txt_path)
        if clave not in _src_cache:
            _src_cache[clave] = cfg.source_texts(
                txt_path.read_text(encoding="utf-8", errors="replace"))
        return _src_cache[clave]

    def _sources_for(bibs) -> tuple:
        """`({bibcode: [texts]}, [(bibcode, reason)])` — the checkable sources and the ones that are not.

        ⛔ The only exemptions are «no `.txt` on disk» and `fulltext_source: ocr`. `pdf_source:
        eprint` was one until 1.110.x and covered 45 of 49 papers of a real star, leaving the check
        with population **zero**: since #205 the `.txt` is derived from the very PDF the extractor
        read, and #220 does not ask «does this value match the published one?» (where `eprint` IS a
        caveat, and still is for `verify-citations`) but «is this string in the file that was
        read?», which is just as decidable over a preprint."""
        fuentes, opacas = {}, []
        for b in bibs:
            motivo = ("`fulltext_source: ocr`" if paper_fm(b).get("fulltext_source") == "ocr"
                      else "")
            txts = list(cfg.FULLTEXT.glob(f"*/{b}.txt")) if cfg.FULLTEXT.exists() else []
            if not txts:
                opacas.append((b, "sin `.txt` en disco"))
            elif motivo:
                opacas.append((b, motivo))
            else:
                fuentes[b] = _source_readings(txts[0])
        return fuentes, opacas

    todos_fm: dict = {}                # {stem: frontmatter} de TODA nota — lo llena el loop, y lo
    #                                    consume `index_tables` para no re-parsear la bóveda (#237)
    paper_fms: dict = {}               # {stem: frontmatter} de papers/ — para D-10, sin re-parsear
    paper_abstracts: dict = {}         # {stem: abstract normalizado} — #216, duplicado sin doi/arxiv
    paper_lens_text: dict = {}         # {stem: título+abstract+keywords} — #291, el texto que lee la lente
    sin_extraer_por_sujeto: dict = {}  # nombre de sujeto → {stems core sin extraer} (D-13)
    for f in files:
        try:
            text = open(f, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError) as exc:
            # AUD-153 — un `.md` que no decodifica tumbaba `collect()` entero, y `main` salía 2
            # **sin nombrar el archivo y sin escribir el reporte**: el operador queda con un
            # traceback y sin saber cuál de mil notas es. Una nota ilegible es un hallazgo de la
            # bóveda —evade TODOS los chequeos por tipo, igual que un frontmatter no parseable— y
            # se reporta como tal, con su ruta, mientras el resto del lint sigue corriendo.
            fm_broken.append((basename(f)[:-3],
                              f"el archivo no se pudo leer como UTF-8 ({exc.__class__.__name__}) → "
                              f"evade TODOS los chequeos de su tipo; `{f}`"))
            continue
        fm = split_fm(text)
        todos_fm[basename(f)[:-3]] = fm or {}
        if in_dir(f, "papers"):
            paper_fms[basename(f)[:-3]] = fm
            # #216 — el `## Abstract` verbatim, normalizado, para el detector de duplicados SIN
            # identificador. Se guarda acá porque el loop ya tiene el texto: re-leer 900 notas para
            # una categoría de backlog sería pagar el corpus dos veces.
            paper_abstracts[basename(f)[:-3]] = _abstract_norm(text)
            # #291 — el MISMO texto que lee la lente (título + abstract + keywords), no el
            # fulltext: el veredicto tiene que ser el de la lente, y el loop ya tiene el texto.
            paper_lens_text[basename(f)[:-3]] = cfg.note_lens_text(fm or {}, text)
        else:
            anchor_bodies[f] = text
        stem = basename(f)[:-3]
        for motivo in normalize_lists(fm):     # ANTES de cualquier lector (ver normalize_lists)
            fm_broken.append((stem, motivo))
        # INV-63 — ¿la nota trae los campos que el schema de SU TIPO declara? Presencia, no valor:
        # un `null` es el caso normal (el espejo #70 deja en `null` lo que la autoridad no trae, y
        # rellenarlo con literatura está prohibido). El tipo sale de los `tags`, que es lo que el
        # resto del lint ya usa. Backlog: el corpus viejo tiene notas anteriores al campo.
        if fm and stem not in refs_stems:
            _tags = [str(t) for t in cfg.as_list(fm.get("tags"))]
            _tipo = ("hypothesis" if "hypothesis" in _tags else
                     "paper" if "paper" in _tags else
                     "star" if "star" in _tags else
                     "concept" if in_dir(f, "concepts") else "")
            if _tipo and (_faltan := cfg.missing_schema_fields(_tipo, fm)):
                schema_incompleto.append(
                    (stem, f"nota de tipo `{_tipo}` sin {len(_faltan)} campo(s) del schema: "
                           f"{', '.join('`%s`' % k for k in _faltan)} → re-corré "
                           f"`make_notes.py <slug>` (los escribe en `null` si no hay valor; el "
                           f"campo ausente y el campo vacío NO se leen igual)"))
        kinds[stem] = fm.get("tags", []) or []
        err = fm_error(text)
        if err:
            fm_broken.append((stem, err))
        # links salientes (las refs de diseño tienen links-ejemplo: no contar sus salientes)
        if f.startswith(refs_dir):
            continue
        # precondición de verificabilidad: toda cita-bibcode de una nota que AFIRMA necesita su
        # fulltext para poder correr verify-citations (chequeo claim↔fuente).
        # ⚠ `stars/` entró en 1.36.0. Antes la población era sólo `queries` + `concepts`, así que una
        # cita sin `.txt` en una ficha de estrella no producía NINGÚN hallazgo — justo el "tercer
        # estado silencioso" que INV-03 prohíbe, y encima en la nota donde el contrato pone el
        # estándar de autosuficiencia y donde más `[[bibcode]]` se acumulan.
        # AUD-176 — `papers/` faltaba, y la prosa de una nota de paper cita otros bibcodes: la
        # atribución de **segunda mano** (#103) es exactamente eso, «este paper reporta un valor que
        # es de X». Sin `.txt` de X esa cita no es chequeable, y no producía NINGÚN hallazgo — el
        # mismo tercer estado silencioso que INV-03 prohíbe, en la nota donde vive la extracción.
        in_verifiable_note = (in_dir(f, "queries") or in_dir(f, "concepts")   # concepts/ incluye hypotheses/
                              or in_dir(f, "stars") or in_dir(f, "papers"))
        # notas de ENTIDAD (#75): son las que sintetizan un sujeto. Una cita que sólo aparece en una
        # query no es "el paper llegó a la bóveda": la query es una respuesta puntual, no la síntesis.
        in_entity_note = in_dir(f, "stars") or in_dir(f, "concepts")   # #33: no comparar paths
                                                                       # como texto (stars-borradores)
        # ⚠ Los links de las secciones ESTAMPADAS no cuentan como "citado" (#75) — el mismo defecto
        # que la tabla de planetas satisfaciendo el proxy de prosa, por otra puerta. La tabla
        # `## Papers` (D-10/D-11) lista **todo** paper del sujeto con su `[[stem]]`, así que desde
        # que se materializó, *extraído pero no sintetizado* no podía disparar nunca: la máquina
        # "citaba" por su cuenta cada paper que el humano no había sintetizado. Medido sobre el
        # corpus sintético al emitir el schema vigente: 4 → 0.
        # Los links SÍ cuentan para `incoming`/`broken`: ahí la pregunta es si la nota es
        # alcanzable y si el destino existe, y una tabla estampada la alcanza igual.
        # ⚠ Las citas se cuentan SÓLO sobre la prosa. Un `[[bibcode]]` de la tabla `## Papers` no es
        # una cita: es metadata que estampó `make_notes`, y `verify-citations` no puede chequearla
        # —no hay afirmación que contrastar contra la fuente, hay una fila—. Contándolos, una ficha
        # recién creada, con la prosa todavía en plantilla, nacía pidiendo verificación de decenas
        # de pares imposibles (medido en el clean-room del 2026-08-25: 117 "citas" en tau_ceti, 0 de
        # ellas en prosa) y encima reportando como "no verificable" cada paper del universo sin
        # fulltext. Es el mismo lazo que ya cierra `solo_prosa` para los otros proxies: un artefacto
        # que se mide a sí mismo siempre da el resultado que su propia existencia produce.
        links_prosa = [t.strip() for t in LINK_RE.findall(solo_prosa(text))]
        prosa_links = set(links_prosa) if in_entity_note else set()
        nbib = 0                              # citas [[bibcode]] EN PROSA de esta nota
        for tgt in links_prosa:
            if "/" in tgt or tgt in LINK_SKIP:
                continue                       # placeholder/ejemplo, no link real
            if BIBCODE_RE.match(tgt):
                nbib += 1
                if in_verifiable_note and tgt not in fulltext:
                    unverifiable.append((stem, f"cita {tgt} sin fulltext (no chequeable claim↔fuente)"))
        for tgt in LINK_RE.findall(text):
            tgt = tgt.strip()
            if "/" in tgt or tgt in LINK_SKIP:
                continue                       # placeholder/ejemplo, no link real
            # #249 — el ÍNDICE no cuenta como link entrante. Antes de #237 era prosa a mano y un
            # link desde ahí era evidencia de que alguien catalogó la nota; desde que se ESTAMPA
            # por verdad de disco lista todo, así que ninguna estrella ni concepto podía volver a
            # ser huérfano y el detector —que BLOQUEA— quedaba en 0 permanente. Mismo criterio con
            # que las secciones estampadas quedan fuera del fan-out y del detector de fuga (#214):
            # metadata derivada no es evidencia. Lo cazó el corpus sintético al mover el golden.
            if tgt in incoming and stem != "index":
                incoming[tgt] += 1
            elif tgt not in names:
                broken.append((stem, tgt))
            # #75: "citado" se mide contra el STEM de la nota de paper, así que se registra todo
            # target de una nota de entidad — no sólo los que parecen bibcode. Una clave sintética
            # off-ADS (`2006RasmussenWilliams`, y peor: cualquiera que no empiece con AAAA+letra)
            # sí matchea BIBCODE_RE… pero un citekey inválido no, y el paper quedaba reportado como
            # "no sintetizado" para siempre AUNQUE la ficha lo citara, sin forma de cerrarlo.
            if in_entity_note and tgt in prosa_links:
                cited_in_entity.add(tgt)
        # cobertura: un concepto/hipótesis que afirma sin ninguna cita [[bibcode]] no es chequeable
        # (todo lo apuntable debe ser citable o marcado `inferencia`; ver Verify en CLAUDE.md). Backlog.
        if in_dir(f, "concepts") and nbib == 0:
            coverage.append((stem, "sin citas [[bibcode]] → afirmaciones no chequeables (cobertura)"))
        # cobertura de VERIFICACIÓN (ALCE-adjacent): una nota apuntable con citas pero sin el bloque
        # `## Verificación de citas` nunca pasó por verify-citations → sus claims no fueron chequeados
        # claim↔fuente.
        # ⚠ Severidad R-1 desde 1.36.0 (antes: backlog siempre). D-5 dice que la nota **nace 100%
        # verificada**, así que "tiene citas y ningún bloque" no es deuda vieja: es la operación que
        # la tocó sin terminar. INV-79 —«una nota con citas sin verificar no cierra»— lo pedía ya, y
        # el detector que sí contaba para el exit (`stale_pairs`) sólo se puebla con notas que YA
        # tienen bloque: la nota nunca verificada se escapaba por abajo. Las fichas de estrella
        # entran: los valores NEA no se verifican contra papers, pero sus disputas y todo lo
        # atribuido a un `[[bibcode]]`, sí.
        has_verif, verif_date = verify_block(text)
        if in_verifiable_note and nbib > 0 and not has_verif:
            unverified.append((stem, f"{nbib} cita(s) sin bloque de verify-citations → correr el skill"))
        # la vigencia del bloque se evalúa después del loop (necesita git; ver `stale_verif`). Vale
        # para TODA nota con bloque —también fichas de estrella—, no sólo las de la cobertura de
        # arriba: ampliar una ficha es justo cuando el bloque queda atrás.
        if has_verif and stem not in NON_ORPHAN:
            verif_blocks.append((f, verif_date))
            anchor_notes.append((stem, text))
        # frontera dura: fuga de implementación (código no bibliográfico) al vault (WARN, no bloquea).
        # AUD-190 / INV-4 — el número de línea se contaba desde el CUERPO y el hallazgo se publica
        # como `L{i}`, que por convención de este repo es la de `grep -n` sobre el ARCHIVO (skill
        # verify-citations, #29). En una ficha de estrella el frontmatter tiene decenas de líneas,
        # así que el puntero mandaba al operador a otra parte de la nota — un mapa que atribuye mal.
        # Y el cortador es `frontmatter_span`, no `split("---", 2)`: éste corta dentro de un escalar
        # entrecomillado que lleve `---` (H-11), y ahí el offset quedaba peor todavía.
        _partes = cfg.frontmatter_span(text)
        body_full = _partes[1] if _partes else text
        _offset = len(text[:len(text) - len(body_full)].split("\n")) - 1 if _partes else 0
        scan_leaks = stem not in NON_ORPHAN    # log/index/README son historia/navegación, no fichas
        # split("\n"), no splitlines(): un form feed colado no debe correr la numeración (la
        # convención de conteo es la de `grep -n` — ver skill verify-citations, #29)
        # #214 — las SECCIONES ESTAMPADAS quedan fuera del scan, igual que en `lib_blocks.pairs_of`.
        # `verify-citations` ya las exime con el argumento correcto —una traducción «no es una
        # afirmación de la bóveda y no hay qué contrastar»— y este detector no: la misma prosa era
        # «no es una afirmación» para una red y «candidata a fuga» para la otra. El caso medido son
        # las traducciones de #124: el castellano dice «nuestro código» donde el paper dice *our
        # code*, y el patrón `_CONSUMIDOR_*` busca exactamente eso, así que TODO abstract en primera
        # persona del plural —o sea la mayoría— disparaba el WARN al traducirse. Importa porque el
        # valor de esta categoría es ser de alta señal: cada hit se revisa a mano, y un WARN que
        # crece linealmente con el número de papers traducidos, falso positivo en todos, es cómo una
        # categoría se vuelve ruido y se deja de mirar.
        # ⛔ El recorte: `## Vista — <sujeto>` NO es estampada (no está en `SECCIONES_ESTAMPADAS`),
        # y ahí una fuga sí sería una fuga real — la escribe el extractor, no la máquina.
        _en_estampada = False
        for i, line in enumerate(body_full.split("\n"), 1 + _offset) if scan_leaks else []:
            if line.startswith("## "):
                _en_estampada = cfg.is_stamped_section(line)
            if _en_estampada:
                continue
            if line.lstrip().startswith(">"):
                continue                       # blockquote meta (frontera/alcance)
            for rx, label in leak_patterns:
                if rx.search(line):
                    impl_leaks.append((stem, f"L{i} [{label}]: {line.strip()[:80]}"))
                    break
        # #234 — las salvedades de una nota de paper. #213 le dio a la afirmación decidible una
        # forma estructurada y un `grep`; lo que no le dio es nada que haga que el extractor la
        # USE. Medido sobre una bóveda real: 0 de 43 extracciones emitieron una salvedad
        # estructurada, ninguna nota llevaba la marca de #213, y una salvedad FALSA volvió a
        # colarse — publicada bajo `**Salvedades:**` pelado, al mismo nivel visual que tendría una
        # chequeada. Los dos hallazgos son backlog: son deuda de re-corrida, no violación.
        if in_dir(f, "papers") and "**Salvedades" in text:
            if "NO VERIFICADAS" not in text and "verificadas contra el archivo" not in text:
                salv_sin_marca.append(
                    (stem, "publica `**Salvedades:**` sin la marca de #213: no se distingue la "
                           "chequeada contra el archivo de la que es juicio del extractor → "
                           "re-correr `harvest_views.py <slug>`"))
            # ⛔ #253 — el barrido va SÓLO sobre el bloque de las NO verificadas, que es la
            # población que #234 describe: juicio del extractor que podría haberse mecanizado. El
            # bloque «verificadas contra el archivo» lo escribe el COSECHADOR, y sus líneas dicen,
            # literalmente, que la salvedad se emitió estructurada y se chequeó — marcarlas es
            # pedir que se estructure lo que ya está estructurado. Medido en `hd_40307` tras una
            # tanda de extracción bien hecha: 12 de 17 hallazgos eran líneas del propio cosechador,
            # y el número CRECE con cada salvedad correctamente estructurada. Misma exención y
            # mismo argumento que #214 para las `SECCIONES_ESTAMPADAS`: un detector no mira lo que
            # la máquina escribe, porque si no la categoría de alta señal se vuelve ruido.
            _en_juicio = False
            for _ln in text.split("\n"):
                _b = _ln.strip()
                if _b.startswith("**Salvedades"):
                    # ⚠ El bloque PELADO (`**Salvedades:**`, schema anterior a #213) SÍ entra: es
                    # justo donde se coló la salvedad falsa que #213 midió. Lo único exento es el
                    # bloque que escribe el cosechador.
                    _en_juicio = "verificadas contra el archivo" not in _b
                    continue
                if _b.startswith("## "):
                    _en_juicio = False
                if _en_juicio and _b.startswith(("- ", "* ")) and cfg.looks_decidable(_b):
                    salv_decidible.append(
                        (stem, f"salvedad en prosa que un script podría decidir: «{_b[2:82]}…» → "
                               f"emitila estructurada (`SALVEDAD_TIPOS`) y el cosechador la chequea"))

        # #225 — la cuarta marca en línea. Una afirmación marcada para ir al PDF es deuda ABIERTA:
        # se reporta hasta que alguien la verifique y la saque. Backlog, nunca bloqueante — la
        # afirmación puede ser cierta, y la marca existe justamente para hacerla visible sin
        # destruirla, igual que `⛔retractada` y `⚠desactualizado`.
        if stem not in NON_ORPHAN:
            for _i, _l in enumerate(body_full.split("\n"), 1 + _offset):
                if VERIFICAR_PDF_MARK in _l:
                    verificar_pdf.append(
                        (stem, f"L{_i}: una afirmación quedó marcada para chequear contra el PDF — "
                               f"«{_l.strip()[:90]}»"))

        # #220 — la cita textual, que es una afirmación DECIDIBLE SOBRE UN ARCHIVO. «esta cadena
        # está en este `.txt`» lo contesta un `grep`, y hoy lo único que las mira es el fan-out de
        # `verify-citations`: un subagente por fuente leyendo el PDF, la parte más cara de la
        # cadena, para algo que se decide en milisegundos. Y como es juicio de LLM, la cita alterada
        # PASA: medido en una nota real, seis citas no verbatim volvieron `soportada` —correctamente,
        # porque el CONTENIDO estaba respaldado: el eje que el contrato mide es ortogonal al que
        # falla, igual que `condicion` (#74)—. Una de ellas invertía el sentido de la oración
        # («do not become orthogonal» por «that are not orthogonal»).
        #
        # Se marca sólo si NINGUNA de las fuentes citadas en el bloque la tiene: un bloque que cita
        # dos papers puede legítimamente entrecomillar a uno solo. Y hay tercer estado: sin `.txt`,
        # con `fulltext_source: ocr` o con `pdf_source: eprint` el fallo es esperable y se DECLARA
        # (el OCR erra símbolos y el preprint no dice lo mismo que el publicado), en vez de contarse
        # en contra. ⛔ La PÁGINA no se puede chequear así —el `.txt` no tiene páginas— y eso se
        # dice: media red declarada vale más que ninguna.
        # #238 — la bitácora también entrecomilla, y ahí la cita fabricada es PERMANENTE (append-only).
        # El chequeo es el mismo de #220 y la salida es distinta: no se edita la entrada vieja, se la
        # MARCA (`⚠ corregido <fecha> → <entrada nueva>`) y se appendea la corrección.
        if stem == "log":
            for _b in lb.split_blocks(body_full):
                if LOG_SUPERSEDED_MARK in _b.text:
                    continue           # ya marcada: visible, no es deuda
                for _bib in lb._bibcodes(_b.text):
                    _txts = list(cfg.FULLTEXT.glob(f"*/{_bib}.txt")) if cfg.FULLTEXT.exists() else []
                    if not _txts:
                        continue
                    _srcs = _source_readings(_txts[0])
                    for _c in cfg.quotes_in(_b.text):
                        if not any(cfg.quote_found(_c, _s) for _s in _srcs):
                            cita_log.append(
                                (stem, f"L{_b.first_line}: la bitácora entrecomilla «"
                                       f"{_c[:70]}{'…' if len(_c) > 70 else ''}» y esa cadena no "
                                       f"está en el `.txt` de {_bib} — la entrada NO se edita "
                                       f"(append-only): se marca `{LOG_SUPERSEDED_MARK} <fecha> → "
                                       f"<entrada nueva>` y se appendea la corrección"))
                            break

        if stem not in NON_ORPHAN:
            _por_bloque: dict = {}
            for _par in lb.pairs_of(text):
                _por_bloque.setdefault((_par.block.first_line, _par.block.text), []).append(_par.bibcode)
            for (_ln, _btxt), _bibs in _por_bloque.items():
                _citas = cfg.quotes_in(_btxt)
                if not _citas:
                    continue
                for _c in _citas:
                    # #316 — la cita se prueba contra SU fuente, no contra todas las del bloque. Un
                    # párrafo que contrasta dos o tres papers es la forma normal de la prosa que
                    # este framework pide, y probar cada cita contra cada bibcode marca la nota
                    # **por decir la verdad** (medido: 12 de 12 hallazgos duros de un hub, en cuatro
                    # líneas que atribuyen bien en prosa). Peor: el arreglo aparente —reatribuir la
                    # cita al bibcode contra el que se testeó— **destruye la inferencia** que la
                    # nota declara. Sin dueño adyacente la ambigüedad se DECLARA en el mensaje.
                    _duenio = lb.quote_owner(_btxt, _c, _bibs)
                    _bibs_c = [_duenio] if _duenio else _bibs
                    _fuentes, _opacas = _sources_for(_bibs_c)
                    _n_citas_evaluadas[0] += 1 if _fuentes else 0
                    _amb = "" if _duenio or len(_bibs) == 1 else (
                        f" ⚠ el bloque cita {', '.join(sorted(_bibs))} y la cita no lleva "
                        f"`[[bibcode]]` adyacente: se probó contra TODAS, así que el hallazgo es "
                        f"más débil — poné la cita al lado de su fuente (#316)")
                    if any(cfg.quote_found(_c, _t) for _ts in _fuentes.values() for _t in _ts):
                        continue
                    # #315/#317 — la comparación DECIDIBLE que faltaba: la EXTRACCIÓN es la
                    # transcripción hecha leyendo el PDF, así que si la cita está ahí, la nota es
                    # fiel y lo que falló es el `.txt` (#205 lo declara índice degradado). Medido:
                    # con el `.txt` como único juez la señal era 2 de 17 en un concepto y 0 de 35 en
                    # otro — un detector que delega 54 confirmaciones manuales al PDF es un detector
                    # que se deja de leer. Lo que la extracción NO tiene y el `.txt` tampoco es
                    # justamente lo que el sintetizador inventó, y eso no admite excusa.
                    _extracciones = {b: cfg.extraction_texts(b) for b in (_bibs_c or [])}
                    # #318 — «no está en la extracción» sólo significa algo si la extracción EXISTE:
                    # una fuente off-ADS sin extraer, o una bóveda pre-#311 sin migrar, no es una
                    # cita inventada, es un chequeo que no se pudo correr.
                    _con_extraccion = any(_extracciones.get(b) for b in _fuentes)
                    _en_extraccion = [b for b, _ts in _extracciones.items()
                                      if any(cfg.quote_found(_c, _t) for _t in _ts)]
                    if _en_extraccion:
                        cita_txt_degradado.append(
                            (stem, f"L{_ln}: «{_c[:70]}{'…' if len(_c) > 70 else ''}» está en la "
                                   f"EXTRACCIÓN de {', '.join(sorted(_en_extraccion))} (que se hizo "
                                   f"leyendo el PDF) y no en su `.txt`: la nota está bien y el "
                                   f"defecto es del índice — re-extraé el `.txt` si molesta (#315)"))
                        continue
                    _corte = _c if len(_c) <= 70 else _c[:70] + "…"
                    if _fuentes and any(cfg.quote_found_degraded(_c, _t)
                                        for _ts in _fuentes.values() for _t in _ts):
                        # #288 — la fuente SÍ la dice: lo que la rompió es la EXTRACCIÓN (números
                        # de línea de un preprint a dos columnas metidos en medio de la frase, una
                        # columna vecina empalmada). Es otro trabajo y otra severidad: acá no hay
                        # nada que corregir en la nota. Medido sobre cinco hallazgos abiertos uno
                        # por uno, CUATRO eran esto y uno era la nota.
                        cita_txt_degradado.append(
                            (stem, f"L{_ln}: «{_corte}» está en la fuente pero el `.txt` la parte "
                                   f"({', '.join(sorted(_fuentes))}): números de línea o columnas "
                                   f"empalmadas. La cita no se toca — confirmala en el PDF y, si "
                                   f"hace falta, re-extraé el `.txt`{_amb}"))
                    elif _fuentes and _con_extraccion and not _amb:
                        # #318 — el GATE que #315/#317 pidieron. Después de #315/#316 un hit acá
                        # significa: la cita no está en el `.txt` **ni en la extracción** —la
                        # transcripción hecha leyendo el PDF— y se probó contra SU fuente. O sea que
                        # la fabricó el sintetizador, y una operación que fabrica una cita textual
                        # no puede cerrar en verde. ⚠ La partición es en TRES: sin extracción en
                        # disco el caso es **no evaluable** (backlog, abajo) y no un bloqueante
                        # inventado —la simétrica del falso limpio que D-43 prohíbe—, y la cita
                        # ambigua (bloque con lista de fuentes) tampoco sube: su propio mensaje ya
                        # declara que el hallazgo es más débil (#316).
                        cita_inventada.append(
                            (stem, f"L{_ln}: «{_corte}» no está en el `.txt` **ni en la "
                                   f"extracción** de {', '.join(sorted(_fuentes))} — la extracción "
                                   f"se hizo leyendo el PDF, así que no es un `.txt` degradado: la "
                                   f"cita se alteró al sintetizar. Copiala del JSON de extracción "
                                   f"(`contrast.py {stem} --grep …`) o parafraseá SIN comillas"))
                    elif _fuentes:
                        cita_no_verbatim.append(
                            (stem, f"L{_ln}: «{_corte}» no está en el `.txt` de "
                                   f"{', '.join(sorted(_fuentes))} → ⚠ **confirmala en el PDF antes "
                                   f"de tocar la nota**: desde #205 el `.txt` es el ÍNDICE, no la "
                                   f"fuente, y un `.txt` a dos columnas empalma texto vecino en "
                                   f"medio de la frase. Si el PDF la dice, el defecto es de la "
                                   f"extracción; si no, la cita no es verbatim{_amb}"))
                    elif _opacas:
                        cita_opaca.append(
                            (stem, f"L{_ln}: «{_corte}» no se puede chequear — "
                                   + "; ".join(f"{b}: {m}" for b, m in _opacas)))

        # #235 — el hub que nombra un radio SIN `[[wikilink]]`. La convención hub/radio pide que el
        # hub «referencie cada radio explícitamente», y sin red el radio aparecía como slug entre
        # backticks dentro de un bullet: no entra al grafo, no cuenta como link entrante para el
        # detector de huérfanos, y el hub se lee como si el sub-aspecto no existiera.
        if _CONCEPT_SLUGS and str(f).startswith(str(cfg.CONCEPTS)):
            for _m in _RADIO_RE.finditer(body_full):
                _slug = _m.group(1)
                if _slug != stem and _slug in _CONCEPT_SLUGS and f"[[{_slug}]]" not in body_full:
                    radio_sin_link.append(
                        (stem, f"nombra el radio `{_slug}` entre backticks y no lo linkea "
                               f"`[[{_slug}]]` — sin el link no entra al grafo ni cuenta como link "
                               f"entrante, y el hub se lee como si el sub-aspecto no existiera"))

        # #227 — la FORMA del artefacto. El artefacto es lo que viaja, y hasta 1.82.3 nadie miraba
        # si renderiza. Medido en una nota real con `lint --cierre` en 0: una fila de tabla con 9
        # celdas en una tabla de 4 (dos filas fusionadas por un empalme) que **no se renderiza** —y
        # que el bloque de verificación certificaba como par verificado—, un backtick abierto
        # durante 268 líneas, y un párrafo duplicado con dos finales distintos.
        # La fila mal formada BLOQUEA: no es «se ve feo», es contenido que el lector no ve mientras
        # toda herramienta que parsea el archivo sí lo ve — y puede estar certificado como
        # verificado. Las otras dos son backlog: molestan, no ocultan.
        if stem not in NON_ORPHAN:
            for _ln, _got, _want in cfg.table_shape_issues(body_full):
                forma_rota.append(
                    (stem, f"L{_ln + _offset}: fila de tabla con {_got} celda(s) y su encabezado "
                           f"tiene {_want} → las de más NO se renderizan (¿dos filas empalmadas en "
                           f"una línea?)"))
            # AUD-227 — las SECCIONES ESTAMPADAS quedan fuera del chequeo de marcadores, mismo
            # criterio que el detector de fuga (#214): `## Abstract` es copia **verbatim** de
            # catálogo, y ADS devuelve comillas tipo LaTeX (``cleaning'`` con un solo backtick) que
            # la bóveda **no puede editar** —el verbatim es la capa auditable—. Reportarlo era pedir
            # que se arregle algo que el contrato prohíbe tocar: backlog permanente sobre una nota
            # correcta, que es el falso positivo que erosiona la categoría entera.
            _cuerpo_forma = "\n".join(
                ln if not cfg.is_stamped_section(_sec) else ""
                for ln, _sec in _lines_with_section(body_full))
            for _ln, _marca, _impar in cfg.unclosed_markers(_cuerpo_forma):
                # #309 — las DOS líneas: el párrafo que queda abierto y aquella donde el conteo se
                # vuelve impar. Con párrafos de seis bullets, mandar al arranque es hacerle buscar
                # a mano al operador lo que el detector ya sabe.
                _donde = (f"L{_ln + _offset}" if _impar == _ln else
                          f"L{_ln + _offset} (el impar cae en L{_impar + _offset})")
                forma_sospechosa.append(
                    (stem, f"{_donde}: el párrafo deja un `{_marca}` sin cerrar — se traga el "
                           f"texto que sigue. Un literal se escribe escapado (`\\{_marca}`), y así "
                           f"escrito ya no cuenta (#309)"))
            for _ln, _txt in cfg.duplicate_paragraphs(body_full):
                forma_sospechosa.append(
                    (stem, f"L{_ln + _offset}: párrafo repetido en la misma nota — «{_txt}…»"))
            # #260 — el encabezado pegado a una fila de tabla. Mismo eje que la fila mal formada,
            # otro mecanismo: GFM corta bien y Obsidian no lo muestra, pero Python-Markdown lo
            # absorbe COMO UNA CELDA y el `##` desaparece del outline junto con la población que
            # D-10/INV-81 obligan a publicar en el título. Lo producía `_reemplazar_seccion`
            # (arreglado en el mismo cambio); esto es la red para el próximo call site.
            for _ln, _head in cfg.headings_glued_to_table(body_full):
                forma_sospechosa.append(
                    (stem, f"L{_ln + _offset}: «{_head[:60]}» arranca pegado a una fila de tabla, "
                           f"sin línea en blanco → Python-Markdown lo absorbe como una celda más y "
                           f"el encabezado desaparece (GFM/Obsidian lo tolera, por eso no se ve)"))

        # Cabecera no estampable (#69, backlog): una ficha/concepto sin la línea
        # `> _Generado con Almagesto v…_` deja SIN EFECTO a todos los estampadores de cabecera
        # —hoy el puntero de búsqueda de #64—, que anclan ahí y devuelven False en silencio. Sin
        # esta categoría el no-op no deja rastro: la feature no llega a la nota y nadie se entera
        # (medido en una bóveda real: 22 de 25). Se arregla con `make_notes.py --restamp-headers`.
        # #233 — la cabecera que la nota PUBLICA contra la que el estampador daría hoy. Nadie las
        # compara: `estado_line` y el lint comparten la regla de la fecha (AUD-136) pero ningún
        # chequeo cruza «lo que se publicó» con «lo que se produciría». Medido: una nota publicaba
        # DOS de las tres fechas obligatorias —le faltaba la de verificación— habiendo pasado el
        # gate de cierre, y el estampador del framework producía la línea correcta: nadie lo había
        # re-corrido. Es el defecto que AUD-136 arregló entre lint y estampador, un nivel más
        # arriba: allá eran dos implementaciones que discrepaban, acá una que nadie verifica que se
        # haya corrido. Backlog: la nota es válida, lo que falta es re-estampar.
        _slug_ent = _entity_slug(f)
        if _slug_ent and GENERATOR_LINE in text:
            try:
                _quiere = mn.estado_line(_slug_ent, Path(f))
            except Exception:                             # noqa: BLE001 — un registro roto ya se reporta
                _quiere = ""
            _hay = next((l for l in text.split("\n") if l.startswith(ESTADO_PREFIJO)), "")
            # ⚠ Sólo la nota que YA publica una línea de estado: el hallazgo es el DESFASE, no la
            # ausencia. Una nota que nunca la tuvo es el caso de #69 (cabecera no estampable) y
            # marcarla acá duplicaría ese hallazgo en dos categorías con severidades distintas —
            # que es cómo una de las dos se deja de mirar. Medido: sin este recorte el corpus
            # sintético limpio reportaba 4 fichas que nunca habían pasado por el estampador.
            if _quiere and _hay:
                if _hay.strip() != _quiere.strip():
                    estado_desfasado.append(
                        (stem, "la cabecera `> _Estado — …_` no es la que el estampador da hoy "
                               "(¿faltó re-correr después del último paso?) → `python "
                               f"scripts/make_notes.py {_slug_ent}`"))

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
        # #267 — las citas textuales de `disputes[]` quedaban fuera de TODO: `pairs_of` opera sobre
        # el cuerpo y el frontmatter no es prosa, así que ni el fan-out ni #220 las miraban. Medido
        # en una ficha real: 23 posiciones con `ref:` y 6 citas «…», cero chequeadas — y una
        # corrección de la verificación aterrizó sólo en la prosa, dejando el frontmatter (la capa
        # que el contrato llama auditable) con el número que la verificación había corregido.
        _refs_disputa: list = []
        for campo, posiciones, motivos_forma, _nota_disputa in note_disputes(fm):
            for motivo in motivos_forma:
                bad_disputes.append((stem, motivo))
            if not campo:
                bad_disputes.append((stem, "disputa sin `field`: no se sabe sobre QUÉ es el desacuerdo"))
            if len(posiciones) < 2:
                bad_disputes.append((stem, f"disputa `{campo or '?'}` con {len(posiciones)} "
                                           f"posición(es): un desacuerdo necesita al menos dos — con "
                                           f"una sola es una afirmación, y va a la prosa citada"))
            _refs_campo: list = []
            for pos in posiciones:
                if isinstance(pos, dict) and str(pos.get("ref") or "").strip():
                    _refs_campo.append(str(pos["ref"]).strip())
            for _c in cfg.quotes_in(_nota_disputa):
                _f, _o = _sources_for(_refs_campo)
                _corte = _c if len(_c) <= 70 else _c[:70] + "…"
                if any(cfg.quote_found(_c, _t) for _ts in _f.values() for _t in _ts):
                    continue
                if _f:
                    cita_no_verbatim.append(
                        (stem, f"frontmatter `disputes[{campo}].note`: «{_corte}» no está en el "
                               f"`.txt` de {', '.join(sorted(_f))} — misma regla que el cuerpo: "
                               f"alcanza con que UNA de las fuentes de la disputa la tenga"))
                elif _o:
                    cita_opaca.append(
                        (stem, f"frontmatter `disputes[{campo}].note`: «{_corte}» no se puede "
                               f"chequear — " + "; ".join(f"{b}: {m}" for b, m in _o)))
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
                    _refs_disputa.append(ref)
                    # El `value` se chequea contra SU PROPIA `ref`: juntar los refs de la nota
                    # fabricaría la atribución cruzada que este framework persigue como modo de
                    # falla dominante. `str()` defensivo: `value` puede ser numérico.
                    _citas_pos = cfg.quotes_in(str(pos.get("value") or ""))
                    if _citas_pos:
                        _f, _o = _sources_for([ref])
                        for _c in _citas_pos:
                            _corte = _c if len(_c) <= 70 else _c[:70] + "…"
                            if any(cfg.quote_found(_c, _t) for _t in _f.get(ref, [])):
                                continue
                            if _f:
                                cita_no_verbatim.append(
                                    (stem, f"frontmatter `disputes[{campo}].posiciones[].value`: "
                                           f"«{_corte}» no está en el `.txt` de {ref}"))
                            elif _o:
                                cita_opaca.append(
                                    (stem, f"frontmatter `disputes[{campo}].posiciones[].value`: "
                                           f"«{_corte}» no se puede chequear — "
                                           + "; ".join(f"{b}: {m}" for b, m in _o)))
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
        # R-5: `topics:` era a la vez la faceta de la lente y el tema-sujeto. El renombre lo
        # partió en `facets:` y `themes.yaml`, y el campo viejo quedó SIN LECTOR: la nota
        # conserva el dato y el sistema no lo ve. Mismo trato que `busqueda:` pre-D-28 —
        # detector bloqueante, nunca lector tolerante.
        if in_dir(f, "papers") and "topics" in fm and not err:
            old_facets.append((stem, "usa `topics:` (schema pre-R-5) — el campo vigente es "
                                     "`facets:` y el lector ya no mira `topics` → "
                                     "`python scripts/make_notes.py --migrate-facets`"))
        if in_dir(f, "papers") and not err:
            # D-21: la POSTURA de un paper depende de la TESIS, y un paper puede tocar varias.
            # Dejarla en el paper obligaba a elegir una sola para todas; vive en la tabla de
            # evidencia de la hipótesis.
            if fm.get("bearing") is not None:
                old_bearing.append((stem, "usa `bearing:` (schema pre-D-21) — la postura respecto de "
                                          "una tesis vive en la tabla de evidencia de la hipótesis, "
                                          "no en el paper: depende de la tesis, y un paper puede "
                                          "tocar varias"))
            # D-23: sin ninguno de los tres, el paper no pertenece a nada — no entra en ningún
            # roll-up y ninguna síntesis lo alcanza. Que además esté linkeado no lo salva.
            if not any(fm.get(k) for k in ("stars", "thesis_links", "methods")):
                sin_destino.append((stem, "sin destino: ni `stars`, ni `thesis_links`, ni `methods` "
                                          "— no entra en ningún roll-up ni lo alcanza ninguna síntesis"))
        if in_dir(f, "hypotheses") and not err:
            st = fm.get("status")
            if st is not None and st not in HYP_STATUS:
                bad_status.append((stem, f"`status: {st}` fuera del vocabulario "
                                         f"({' | '.join(HYP_STATUS)})"))
            # D-37 · #177: `status` se DERIVA de la tabla de evidencia. `CLAUDE.md` promete que una
            # `sostenida` con filas `desafía` se marca, y no lo hacía nadie: el único chequeo era la
            # pertenencia al vocabulario, así que la contradicción tabla↔status pasaba muda. Es lo
            # único que impide que `status` sea un campo que el agente elige — y el consumidor lo lee
            # justamente para decidir si se apoya en la hipótesis.
            if (n_desafia := challenging_rows(text)) and st == "sostenida":
                status_vs_evidencia.append(
                    (stem, f"`status: sostenida` con {n_desafia} fila(s) `desafía` en la tabla de "
                           f"evidencia: el status se DERIVA de la tabla (D-37). Si la evidencia está "
                           f"repartida, el status es `disputada`"))
            # D-34 — el ALCANCE define qué significa el veredicto. Sin él, "no hay evidencia" se lee
            # como "no existe evidencia": el mismo *afirmar de más* que la bóveda persigue en todos
            # lados, pero aplicado a una conclusión. Y con él, el alcance CRECE: sumar un tema (o
            # refrescar uno) deja el veredicto testeado contra un universo que ya no es el vigente —
            # misma familia de staleness que los pares de verificación. Backlog: la nota no es
            # inválida, quedó atrás. Se cierra re-corriendo el test y re-estampando la línea.
            alc = alcance_declarado(text)
            if alc is None:
                alcance_corto.append(
                    (stem, "sin blockquote `> Alcance <fecha> · …`: un veredicto negativo sin "
                           "alcance declarado se lee como universal → declararlo (skill "
                           "`test-hypothesis`, paso 0)"))
            elif not alc["slugs"]:
                # AUD-171 / INV-92 — un blockquote SIN slugs apagaba el chequeo entero en silencio:
                # la nota tiene la línea, así que pasa el primer caso, y el `elif` no entra. El
                # veredicto sigue leyéndose como universal y encima ahora parece declarado.
                alcance_corto.append(
                    (stem, f"el alcance del {alc['fecha']} no nombra ningún slug "
                           f"(`temas: [...]` / `estrellas: [...]`) → no se puede re-contar el "
                           f"universo, así que el veredicto no se puede pesar: declaralos"))
            elif alc["n_papers"] is None:
                # AUD-171, la otra puerta: con slugs pero sin `· N papers` no hay contra qué
                # comparar el conteo de hoy, y el detector de «quedó corto» queda mudo.
                vigente, faltan = corpus_vigente(alc["slugs"])
                alcance_corto.append(
                    (stem, f"el alcance del {alc['fecha']} no declara `· N papers` → no hay contra "
                           f"qué comparar (hoy esos slugs tienen {vigente}); completá la línea"))
            else:
                vigente, faltan = corpus_vigente(alc["slugs"])
                if faltan:
                    # No se puede contar lo que no existe: se DICE cuál falta en vez de comparar
                    # contra un universo recortado en silencio (que daría "quedó corto" al revés).
                    alcance_corto.append(
                        (stem, f"el alcance nombra slug(s) sin fulltext en disco "
                               f"({', '.join(faltan)}) → ¿typo, o entidad borrada/renombrada?"))
                elif vigente > alc["n_papers"]:
                    alcance_corto.append(
                        (stem, f"alcance del {alc['fecha']} declarado sobre {alc['n_papers']} "
                               f"papers y hoy esos slugs tienen {vigente} (+"
                               f"{vigente - alc['n_papers']}) → el veredicto se testeó contra un "
                               f"universo que ya no es el vigente: re-correr el test sobre lo nuevo "
                               f"y re-estampar la línea de alcance"))
        cuerpo_nota = text.split("---", 2)[-1] if text.startswith("---") else text
        for marca in inferencias_sin_premisas(cuerpo_nota):
            infer_sin_premisas.append(
                (stem, f"`{marca}` sin premisas — una inferencia nombra al menos un `[[bibcode]]`: "
                       "`(inferencia de [[bibcode]])`. Sin eso es una afirmación sin respaldo"))
        if "star" in tags:
            # `solo_prosa`: los proxies de autosuficiencia miden lo que alguien ESCRIBIÓ. Las
            # tablas estampadas (planetas, papers, métodos, excluidos, verificación) son metadata
            # materializada y satisfacen los patrones por construcción.
            body = solo_prosa(text.split("---", 2)[-1] if text.startswith("---") else text)
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
            # #250 — el ÚNICO campo-lista de `stars/` sin destino chequeado ni link: `thesis_links`
            # bloquea, `methods` es backlog, y éste no tenía ninguno de los dos, así que la ficha
            # nombra cinco indicadores y el lector no tiene cómo llegar al concepto que explica
            # ninguno. Backlog por la misma asimetría que `methods`: la nota del indicador la crea
            # `ingest-theme`, que es otra operación. ⚠ Se compara con `indicator_key`, que saca la
            # glosa final entre paréntesis: el campo es prosa para un humano (`BIS (bisector de la
            # CCF)`), y comparar crudo haría dangling al 100 % — un backlog que nace todo falso es
            # uno que nadie vuelve a mirar.
            for _ind in cfg.as_list(fm.get("activity_indicators_expected")):
                _clave = cfg.indicator_key(_ind)
                # ⛔ El índice se construye UNA vez por corrida (`_alias_idx_cached`): llamar
                # `method_target` sin índice re-lee TODAS las notas de `concepts/` por cada
                # indicador de cada ficha, y el tier `poblada` lo cazó como salto de 2,0x a 2,4x en
                # parseos de YAML por nota.
                if _clave and not cfg.method_target(_clave, _alias_idx_cached()) and _clave not in {
                        cfg.method_key(n) for n in names}:
                    indicador_sin_destino.append(
                        (stem, f"`{_ind}` no tiene nota en `concepts/` (ni por `aliases`): ingerí "
                               f"el tema, o declaralo como alias del concepto que lo denota"))
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
            # (ingest_theme/make_notes --web con `pending`) o a mano en la nota.
            # #205 · schema viejo: los dos campos existían para UNA decisión —¿el extractor lee el
            # `.txt` o el PDF?— y esa decisión ya no se toma (la fuente es el PDF, siempre). Un
            # campo sin lector no se deja «por las dudas»: se lee como un gate vivo. Bloquea, como
            # todo schema retirado en este framework —nada de lectores tolerantes—, y la salida es
            # el migrador, no editar a mano.
            # #277 — los tres ⛔ del schema de nota de paper que no tenía ningún detector. Medido
            # sobre 138 notas reales con el lint en rc 0: **39 sin `## Abstract`** y 69 sin
            # `## Conclusiones`. Las tres secciones se podían borrar sin que nada las extrañara, y
            # una de ellas es la única capa AUDITABLE del cuerpo.
            if cfg.section_start(text, "## Abstract") < 0:
                sin_abstract.append(
                    (stem, "sin `## Abstract`: es la única capa AUDITABLE del cuerpo (copia de "
                           "catálogo, no síntesis) y `classify_offline` la lee para re-clasificar "
                           "sin `build/` (D-49) → `python scripts/make_notes.py --restamp-abstracts`"))
            # `## Conclusiones` es lo que el paper afirma SIN lente (#124): lo que hace barata una
            # segunda vista cuando otro sujeto reclama el mismo paper. Tres exenciones, las tres
            # estructurales y machine-readable — un documento largo no tiene esa sección, y un paper
            # leído sólo del abstract no la tiene POR CONSTRUCCIÓN (#207).
            _marca_sc = fm.get("sin_conclusiones", _SIN_MARCA)
            _solo_abstract = bool(fm.get("vistas")) and all(
                str((v_ or {}).get("fuente") or "") == "abstract"
                for v_ in cfg.as_list(fm.get("vistas")) if isinstance(v_, dict))
            if _marca_sc is not _SIN_MARCA:
                # Escotilla declarada: motivo OBLIGATORIO, mismo criterio que `no_vista` /
                # `no_sintetizado` / el `--reason` del triage. Sin motivo sigue siendo deuda.
                if str(_marca_sc or "").strip():
                    sin_conclusiones_ok.append((stem, f"`sin_conclusiones: {_marca_sc}`"))
                else:
                    sin_conclusiones.append(
                        (stem, "`sin_conclusiones` sin motivo: la escotilla lo exige (en seis meses "
                               "sirve el motivo, no la categoría)"))
            elif (str(fm.get("unidad_cita") or "") != "pagina" and stem in pdf_on_disk
                    and not _solo_abstract and cfg.section_start(text, "## Conclusiones") < 0):
                sin_conclusiones.append(
                    (stem, "sin `## Conclusiones`: es lo que el paper afirma SIN lente, y lo que "
                           "hace barata una segunda vista (#124) → transcribilas, o declará "
                           "`sin_conclusiones: <motivo>` si la fuente no tiene esa sección"))
            # #247 — el aviso de capa LLM. Se busca en el CUERPO, no en el texto entero: un
            # `pending_motivo` que mencione esas dos palabras daría falso negativo (AUD-135).
            if mn.AVISO_LLM_MARCA not in body_full:
                sin_aviso_llm.append(
                    (stem, "sin el aviso de **capa LLM**: la nota de paper es la que más contenido "
                           "generado tiene y no dice cuál de sus tres capas es auditable → "
                           "`python scripts/make_notes.py --restamp-headers`"))
            # #279 — los valores que la vista marcó de SEGUNDA MANO. La marca la pide #103 (el
            # número no es de esta fuente: es el mecanismo de error nº 1 medido) y nadie chequeaba
            # que llegara a la ficha. Medido: 4 casos en una ficha real, uno usado como falsa
            # corroboración independiente —«otras dos fuentes dan 7,15» era una sola medición ajena
            # contada dos veces—.
            if (_sm := lb.second_hand_rows(body_full)):
                segunda_mano[stem] = _sm
            _viejos = [k for k in ("symbols_lost", "fulltext_layout") if k in fm]
            if _viejos:
                campos_txt_viejos.append(
                    (stem, f"`{'`, `'.join(_viejos)}` — schema pre-#205, ya no lo lee nadie: "
                           "`python scripts/make_notes.py --migrate-txt-fields`"))
            # #80: la unidad de cita de una fuente larga y el recorte que entró. Vocabulario
            # cerrado (bloquea, como `role`); el `alcance` faltante es backlog porque no se puede
            # inventar — pero sin él un recorte deliberado se lee como omisión.
            if (_u := str(fm.get("unidad_cita") or "").strip()):
                if _u not in cfg.UNIDAD_CITA_OK:
                    bad_roles.append((stem, f"`unidad_cita: {_u}` fuera del vocabulario "
                                            f"({' | '.join(cfg.UNIDAD_CITA_OK)}) — el verificador "
                                            f"no sabe cómo citar esta fuente"))
                elif _u != "linea" and not str(fm.get("alcance") or "").strip():
                    incomplete.append((stem, f"`unidad_cita: {_u}` (documento largo) sin `alcance`: "
                                             f"no consta qué parte entró, así que un recorte "
                                             f"deliberado se lee como omisión"))
            # #296 — los otros dos vocabularios CERRADOS del schema de paper, que `CLAUDE.md`
            # declaraba cerrados y nadie validaba. `pdf_source: eprint` es la exención que apaga el
            # chequeo de cita textual: un valor fuera de vocabulario la apaga por el `else` en
            # silencio, y un `eprint` mal escrito la enciende y produce hallazgos que no lo son.
            for _campo, _ok in (("pdf_source", cfg.PDF_SOURCE_OK),
                                ("fulltext_source", cfg.FULLTEXT_SOURCE_OK)):
                _v = fm.get(_campo)
                if _v in (None, ""):
                    continue          # ausente/`null` = DESCONOCIDO, que es un valor legítimo (#57)
                if str(_v).strip() not in _ok:
                    bad_roles.append((stem, f"`{_campo}: {str(_v)[:60]}` fuera del vocabulario "
                                            f"({' | '.join(_ok)}) — `null`/ausente es el valor de "
                                            f"«desconocido»; si querías escribir una nota, va a "
                                            f"`pending_motivo` o a `salvedades`. Migrador: "
                                            f"`python scripts/make_notes.py --migrate-source-fields`"))
            # #298 — las dos señales de «la bóveda se apoya en el preprint». (a) El hallazgo del
            # detector de versiones, estampado para que SOBREVIVA a la corrida: sin él, correr la
            # pasada y no actuar en el momento borraba el hallazgo y la siguiente lo redescubría.
            # (b) La nota que ya tiene bibcode PUBLICADO y sigue leyendo el eprint: no tiene
            # problema de identidad, así que ningún detector la toca — y es justo donde el contrato
            # avisa que una discrepancia numérica es diferencia de versión, y donde `pdf_source:
            # eprint` EXIME del chequeo de cita textual (medido: 82 de 138 notas).
            if (_vd := str(fm.get("versions_disponible") or "").strip()):
                version_publicada.append(
                    (stem, f"`versions_disponible: {_vd}`: el preprint salió publicado y nadie "
                           f"renombró nada → `python scripts/make_notes.py --rename-paper {stem} "
                           f"{_vd}` (o declaralo en `versions[]` si ya lo revisaste)"))
            elif (str(fm.get("pdf_source") or "") == "eprint"
                    and "arxiv" not in str(fm.get("bibcode") or stem).lower()):
                version_publicada.append(
                    (stem, "`pdf_source: eprint` con bibcode PUBLICADO: la nota se apoya en el "
                           "preprint teniendo versión publicada, y esa marca además exime del "
                           "chequeo de cita textual → conseguí el PDF publicado "
                           "(`python scripts/fetch_pdf.py <slug> --force`) o dejá la salvedad"))
            if fm.get("pending_source"):
                ptr = fm.get("doi") or fm.get("source_url") or "(sin puntero conocido)"
                _p = str(fm["pending_source"])
                # #80: la categoría sola no dice si alguien está consiguiendo la fuente o si nadie
                # la miró nunca, y `adquisicion` (un libro en camino) no es un fallo como los otros
                # tres. El motivo no se puede inventar, así que esto es backlog y no bloqueante:
                # nombra la nota para que alguien lo escriba.
                _falta = ("" if str(fm.get("pending_motivo") or "").strip() else
                          " — ⚠ sin `pending_motivo`: escribí qué pasa con esta fuente y quién la consigue")
                if _p not in cfg.PENDING_OK:
                    # #129: el TYPO de vocabulario es bloqueante, como en `role` y `unidad_cita`.
                    # Estaba acá, en backlog, y con eso INV-46 —*"un valor fuera de vocabulario
                    # bloquea"*, universal y `garantizado y medido`— era falso para uno de los
                    # cuatro vocabularios cerrados del schema. El argumento de INV-108 (*"el motivo
                    # no se puede inventar"*) justifica el backlog del `pending_motivo` FALTANTE,
                    # que sigue abajo; no el de un valor que nadie declaró.
                    bad_roles.append((stem, f"`pending_source: {_p}` fuera del vocabulario "
                                            f"({' | '.join(cfg.PENDING_OK)})"))
                pending_srcs.append(
                    (stem, f"{_p}{' · ' + str(fm['pending_motivo']) if fm.get('pending_motivo') else ''}"
                           f" — proveer la fuente; puntero: {ptr}{_falta}"))
            # el tooling escribe siempre `high`/`low`; el `.lower()` cubre la edición a mano,
            # donde un `Low` entraba a la población que el recorte quería dejar afuera.
            relevancia = str(fm.get("relevance") or "").strip().lower()
            # #268 — `no_vista` se parsea ACÁ porque tres redes que corren antes lo necesitaban y
            # ninguna lo miraba: la escotilla que #256 hizo alcanzable decidía sobre UNA sola
            # categoría, y las otras contaban la misma nota como deuda. Medido: una nota con
            # `no_vista` declarado y motivo seguía recibiendo *«conseguir el PDF»* sobre una tabla
            # VizieR, que no es un paper. La forma inválida se reporta más abajo, en su bloque.
            try:
                _no_vista, _nv_error = (
                    {v["sujeto"]: v["motivo"] for v in cfg.load_no_vista(fm, entry=stem)}, None)
            except cfg.VistasError as _e:
                # La forma inválida NO se pierde: se guarda y se re-levanta en el bloque de vistas,
                # que es el que la reporta como `fm_broken`. Tragarla acá dejaría la nota evadiendo
                # el chequeo de su propio campo, que es el bug que ese bloqueante existe para cerrar.
                _no_vista, _nv_error = {}, _e
            if relevancia == "high" and not fm.get("methods") and not _no_vista:
                # #90: dos situaciones OPUESTAS salían con el mismo mensaje — «bajado y nadie lo
                # leyó» (trabajo del agente) y «nunca se pudo bajar» (trabajo del usuario: conseguir
                # la fuente). Son colas distintas con dueños distintos, así que mezclarlas hace
                # imposible priorizar o derivar. El residuo del resolver vivía en
                # `build/<slug>/missing_pdf.json`, gitignored, y la nota quedaba muda.
                # La verdad de disco alcanza y no hay que estampar nada: sin `.txt` y sin PDF, la
                # fuente no está. Un `pending_source` declarado ya se reporta arriba, así que no se
                # cuenta dos veces.
                # @inv INV-112
                if stem in fulltext or stem in pdf_on_disk or fm.get("pending_source"):
                    incomplete.append((stem, "paper relevante sin methods (sin extraer)"))
                else:
                    incomplete.append(
                        (stem, "paper relevante **sin fuente en disco** (ni `.txt` ni PDF): no es "
                               "que falte leerlo, es que nunca se consiguió → conseguir el PDF, o "
                               "declararlo con `pending`/`pending_motivo` para derivarlo"))
                # D-13/INV-83: el sujeto de ese paper queda anotado; después del barrido se
                # contrasta contra lo que el registro DECLARÓ haber leído.
                # `stars` para estrellas y `thesis_links` para temas: la pertenencia de un paper
                # a un tema NO vive en las facetas (otro eje) — mismo predicado que
                # `make_notes._papers_del_sujeto`.
                for campo in ("stars", "thesis_links"):
                    for sujeto in cfg.as_list(fm.get(campo)):
                        # #268 — el sujeto DECLARADO no cuenta como «sin extraer» para el recorte:
                        # con él adentro, el detector afirmaba *«quedan N sin extraer»* sobre un
                        # `criterio: todos los core` que sí se había cumplido.
                        if str(sujeto) in _no_vista:
                            continue
                        sin_extraer_por_sujeto.setdefault(str(sujeto), set()).add(stem)
            # El eslabón SIGUIENTE (#75): el paper que SÍ se extrajo. `methods` poblado significa
            # que alguien gastó en él el paso más caro de la cadena; si su contenido nunca llegó a
            # una ficha ni a un concepto, la extracción se perdió. Se recolecta acá y se resuelve
            # después del barrido, cuando ya se sabe qué citó cada nota de entidad.
            if fm.get("methods") and relevancia != "low":
                # centinela: `no_sintetizado: ""` / `null` / `false` / `0` son marca PRESENTE pero
                # sin motivo — con `.get(campo)` a secas colapsaban con "no hay marca" y el lint
                # respondía "poné `no_sintetizado`" sobre una nota que ya lo tenía puesto.
                extracted.append((stem, fm.get("no_sintetizado", _SIN_MARCA)))
            # (D-21 retiró `bearing` del paper: el campo incompleto "thesis_links sin bearing"
            #  quedó sin población y se eliminó. La postura vive en la hipótesis.)
            # ROL del paper (#73). `bearing` dice la POSTURA respecto de una tesis; `role` dice qué
            # tipo de aporte es, que es lo que determina la operación de contraste: fundacional ↔
            # aplicación NO es contraste sino instanciación, y leerlo como desacuerdo fabrica
            # disputas falsas. Se puebla en la extracción (la regex del clasificador no puede
            # inferirlo) — por eso el aviso cuelga de `methods`, la marca de "ya se extrajo".
            # #188 · qué LECTURA se hizo. `stars`/`thesis_links`/`methods` son RECLAMOS (el
            # retro-link los mergea add-only sin leer nada); `vistas[]` son lecturas. Sin la
            # distinción, el silencio de la nota sobre un eje es indistinguible de «se miró y no
            # hay nada» — el mismo falso limpio que D-34 persigue en las hipótesis.
            try:
                vistas = cfg.load_vistas(fm, entry=stem)
                if _nv_error is not None:
                    raise _nv_error
                no_vista = _no_vista          # #268: ya parseado arriba, misma fuente
            except cfg.VistasError as e:
                # Se REPORTA, no tumba el barrido: es la razón de que el loader levante en vez de
                # salir. Cae en `fm_broken` porque es literalmente eso — un campo con forma
                # inválida hace que la nota evada los chequeos de su tipo (los cuatro de abajo).
                fm_broken.append((stem, str(e).replace("\n", " ")))
                vistas, no_vista = [], {}
            else:
                # #270 — #254 hizo que el prompt derive sus ejes de `relevance.facets` y no dejó
                # red: nada compara los ejes que la vista CONTESTA contra la `lente` que DECLARA, y
                # una faceta que la vista no menciona se lee como «se miró y no hay nada». Medido:
                # 257 huecos sobre 79 vistas con lente declarada. Backlog: una vista puede
                # legítimamente no tener nada que decir sobre un eje — lo que no puede es callarlo.
                _ejes_por_sujeto = cfg.view_axes(text)
                for _v in vistas:
                    _lente = [str(x).strip() for x in (_v.get("lente") or []) if str(x).strip()]
                    if not _lente or not _v.get("fecha"):
                        continue          # sin lente declarada o sin lectura, no hay qué comparar
                    _faltan = [e for e in _lente if e not in _ejes_por_sujeto.get(_v["sujeto"], set())]
                    if _faltan:
                        vista_ejes_faltantes.append(
                            (stem, f"la vista de «{_v['sujeto']}» declara la lente "
                                   f"`{', '.join(_lente)}` y no contesta `{', '.join(_faltan)}`: el "
                                   f"silencio sobre un eje se lee como «se miró y no hay nada»"))
                # #239 — la coherencia de las SUB-secciones por lente, en los dos sentidos: una
                # lente declarada sin su `### Lente — …` y una sub-sección sin declarar. Es el mismo
                # chequeo de #188 un nivel abajo, y hace falta porque la lente es lo que distingue
                # dos lecturas del mismo sujeto: sin él, la segunda vuelve a ser invisible.
                _lentes_cuerpo = {m.group(1).strip() for m in _LENTE_RE.finditer(text)}
                _lentes_decl = {str(v.get("enfasis") or "").strip() for v in vistas
                                if str(v.get("enfasis") or "").strip()}
                for _falta in sorted(_lentes_decl - _lentes_cuerpo):
                    vistas_vs_cuerpo.append(
                        (stem, f"declara la lente «{_falta}» en `vistas[]` y el cuerpo no tiene su "
                               f"`### Lente — {_falta}`"))
                for _sobra in sorted(_lentes_cuerpo - _lentes_decl):
                    vistas_vs_cuerpo.append(
                        (stem, f"tiene `### Lente — {_sobra}` en el cuerpo y ninguna entrada de "
                               f"`vistas[]` la declara"))
                secciones = vistas_en_cuerpo(text)
                declaradas = {v["sujeto"] for v in vistas}
                #  @inv INV-134
                if not vistas and EXTRACCION_VIEJA_RE.search(text):
                    vistas_schema_viejo.append(
                        (stem, "`## Extracción (LLM)` sin `vistas[]`: no consta desde qué sujeto se "
                               "leyó este paper, así que su silencio sobre un eje no se distingue "
                               "de «se miró y no hay nada» → `python scripts/make_notes.py "
                               "--migrate-vistas` (AUD-175)"))
                # Declarada y sin hacer. El stub nace con la vista de su sujeto y SIN `fecha`
                # (la ausencia es «no consta», paso 1): la fecha es lo que dice que la lectura
                # ocurrió. Sin este renglón, declarar la vista al crear el stub apagaría
                # `reclamo_sin_vista` para el sujeto que la sembró y el silencio volvería a leerse
                # como «se miró y no hay nada» — el defecto que #188 cierra, por otra puerta.
                # ⛔ #256 — la escotilla `no_vista` decide ACÁ, sobre la vista sin fecha, y no
                # sobre `reclamos - declaradas`, que el propio sembrado de arriba deja SIEMPRE
                # vacío: `make_notes` pone una entrada de `vistas[]` por cada reclamo, así que ni
                # la deuda ni la escotilla podían dispararse desde esa rama. Medido: **0 de 138**
                # notas de una bóveda real la alcanzaban, o sea que `load_no_vista` se parseaba y
                # su resultado no lo consumía nadie. Sin esto, «falta leerlo» y «no hay nada que
                # leer, y está dicho por qué» caen en el mismo bolsón — que es justo lo que la
                # categoría DECLARADA existe para separar. ⚠ `no_vista` NO borra la entrada de
                # `vistas[]`: la nota sigue diciendo que ese sujeto la reclama; lo que declara es
                # por qué no se leyó.
                for v in vistas:
                    if not str(v.get("fecha") or "").strip() and v["sujeto"] in no_vista:
                        reclamo_sin_vista_declarado.append(
                            (stem, f"**{v['sujeto']}** — {no_vista[v['sujeto']]}"))
                    elif not str(v.get("fecha") or "").strip():
                        vista_sin_fecha.append(
                            (stem, f"la vista de **{v['sujeto']}** está declarada y sin `fecha`: no "
                                   f"consta que se haya leído desde ahí"))
                    # #207 · de QUÉ se construyó. Sin el campo, una vista escrita desde ocho líneas
                    # de abstract es indistinguible de una escrita leyendo el paper — el falso
                    # limpio de D-34 aplicado a la lectura. Ausente = no consta, así que backlog:
                    # el dato no se inventa, se pide.
                    elif not (_f := str(v.get("fuente") or "").strip()):
                        vista_sin_fuente.append(
                            (stem, f"la vista de **{v['sujeto']}** no dice de qué se construyó "
                                   f"(`fuente: pdf|abstract`): una lectura del abstract se lee "
                                   f"igual que una del paper"))
                    elif _f == "abstract":
                        # NO es un error: la vista es legítima y está declarada. El hallazgo pide
                        # el PDF — mismo carril que `pending_source`, visto desde la lectura.
                        vista_solo_abstract.append(
                            (stem, f"la vista de **{v['sujeto']}** se construyó SÓLO del abstract: "
                                   f"conseguir el PDF para leer el paper (y ojo, el abstract es "
                                   f"donde la fuente afirma de más)"))
                # #217 — la vista OCURRIÓ (tiene fecha) y su fuente ya no está en disco: sus citas
                # no se pueden contrastar nunca más. Pasa cuando `--drop-core` borra los artefactos
                # y conserva la nota, y es peor en la rama «se conserva porque pertenece a OTRO
                # sujeto»: ahí el paper puede estar citado en la ficha de esa entidad, con pares ya
                # verificados. El ancla de fuente (D-20) no lo ve —el archivo no cambió,
                # DESAPARECIÓ— y `## Citas no verificables` mira los bibcodes citados desde
                # conceptos/queries, no los pares ya verificados de una ficha. Sin esta categoría,
                # la vista se lee igual de firme que cualquier otra.
                if any(str(v.get("fecha") or "").strip() for v in vistas) and not (
                        list(cfg.PDFS.glob(f"*/{stem}.pdf")) if cfg.PDFS.exists() else []) and not (
                        list(cfg.FULLTEXT.glob(f"*/{stem}.txt")) if cfg.FULLTEXT.exists() else []):
                    vista_sin_fuente_en_disco.append(
                        (stem, "tiene vista FECHADA y ya no hay fuente en disco (ni PDF ni `.txt`): "
                               "la lectura ocurrió y sus localizadores siguen siendo válidos, pero "
                               "`verify-citations` no puede contrastarla nunca más — conseguir de "
                               "nuevo la fuente, o declarar la pérdida en `salvedades` de la vista"))
                # #212 — la lectura REFUTÓ el reclamo y el reclamo sigue en el frontmatter. Es el
                # simétrico del «reclamado sin vista» de #188: allá nadie leyó, acá se leyó y el
                # resultado dice que el reclamo es falso. El lint no lo veía porque mira la
                # coherencia `vistas[] ↔ sección`, no `reclamo ↔ contenido de la vista`, y el
                # merge de `harvest_views` es add-only a propósito, así que el reclamo sembrado es
                # infalsificable por la lectura. Backlog: sacar el paper del sujeto es decisión del
                # usuario —puede ser core de OTRO— y el roll-up del concepto lo sigue listando
                # mientras tanto.
                _reclamados = {str(x).strip() for x in
                               cfg.as_list(fm.get("stars")) + cfg.as_list(fm.get("thesis_links"))}
                for v in vistas:
                    for suj in cfg.as_list(v.get("refuta")):
                        if str(suj).strip() in _reclamados:
                            reclamo_refutado.append(
                                (stem, f"la vista de **{v.get('sujeto')}** REFUTA el reclamo de "
                                       f"**{suj}**, que sigue en el frontmatter: el roll-up lo va a "
                                       f"seguir listando → `triage.py <slug> --drop-core {stem} "
                                       f"--reason \"…\"`, o quitá el reclamo a mano si el paper "
                                       f"pertenece a otro sujeto"))
                for falta in sorted(declaradas - secciones):
                    vistas_vs_cuerpo.append(
                        (stem, f"`vistas[]` declara la lectura de **{falta}** y el cuerpo no tiene "
                               f"su `## Vista — {falta}`: afirma una lectura que no está"))
                for falta in sorted(secciones - declaradas):
                    vistas_vs_cuerpo.append(
                        (stem, f"`## Vista — {falta}` sin entrada en `vistas[]`: no consta de qué "
                               f"`.txt` salió ni con qué lente se leyó"))
                # Reclamado y no leído. Sólo si la nota YA tiene alguna vista: a una del schema
                # viejo la reporta la categoría de arriba, y pedirle además una vista por sujeto
                # duplicaría el hallazgo en cada nota del corpus — así nace un backlog de 900 que
                # nadie mira.
                if vistas:
                    # Qué cuenta como RECLAMO, y por qué `methods` no entra entero: `stars` y
                    # `thesis_links` los siembra el ingest —son «este sujeto pidió que se leyera
                    # este paper»—, mientras que `methods` lo puebla la EXTRACCIÓN, o sea que es un
                    # producto de la lectura («este paper usa un periodograma») y no un sujeto que
                    # la pidió. Contarlo entero le exigiría una vista propia a cada método
                    # nombrado, y así nace un backlog de centenares que nadie mira. Cuenta sólo
                    # cuando ese nombre ES un tema declarado, que es cuando su roll-up alcanza al
                    # paper — el mismo predicado de pertenencia que `_papers_del_sujeto` (D-24).
                    reclamos = {str(x).strip()
                                for campo in ("stars", "thesis_links")
                                for x in cfg.as_list(fm.get(campo)) if str(x).strip()}
                    reclamos |= {str(x).strip() for x in cfg.as_list(fm.get("methods"))
                                 if str(x).strip() in conceptos_de_temas}
                    for sujeto in sorted(reclamos - declaradas):
                        if sujeto in no_vista:
                            reclamo_sin_vista_declarado.append(
                                (stem, f"**{sujeto}** — {no_vista[sujeto]}"))
                        else:
                            reclamo_sin_vista.append(
                                (stem, f"lo reclama **{sujeto}** y nadie lo leyó desde ahí → hacer "
                                       f"la vista, o declararla con `no_vista` y su motivo"))
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
            for mt in fm.get("methods") or []:
                method_refs.setdefault(str(mt), []).append(stem)
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
            # disco y no ve el cuerpo — en una instancia real el frontmatter estaba sano mientras 351/621
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

    # ── pares de verificación vencidos (D-4 / D-20 / INV-78) ─────────────────────────────────────
    # El bloque `## Verificación de citas` se lee como "esta nota está verificada". Acá eso se mide
    # por PAR —qué afirmación exacta se chequeó, contra qué bytes de qué fuente— y no por archivo.
    # Cinco sub-casos, cada uno con su mensaje:
    #   (a) par del cuerpo sin fila            → sin verificar     (se agregó una afirmación)
    #   (b) fila con ancla ≠ recálculo         → vencido por edición
    #   (c) fila con hash de fuente ≠ el .txt  → vencido por fuente (se re-extrajo el PDF)
    #   (d) fila sin par en el cuerpo          → fila huérfana     (se borró la afirmación)
    #   (e) bloque sin columnas de hash        → plantilla vieja   (BLOQUEANTE siempre)
    # (e) va aparte y bloquea sin `--cierre`: no es un par vencido, es un bloque que nadie puede
    # evaluar — reportarlo como "0 vencidos" sería el cero inventado que D-43 prohíbe.
    # @inv INV-78, INV-79
    # #117: el archivo que vigila cada fila lo declara LA FILA (`txt:` / `pdf:` en `Hash fuente`),
    # no el frontmatter. La regla inferida de #113/B-2 —`symbols_lost` ⇒ PDF, si no el `.txt`— es
    # más angosta que la práctica: una fuente `ocr` también se verifica contra el PDF cuando el
    # escaneo del editor destruyó los símbolos, y ahí el lint hasheaba el archivo equivocado (17
    # pares «vencidos por fuente» sobre fuentes que nadie tocó). El hash del PDF se calcula **a
    # demanda**: hashear todos los PDFs de la bóveda por si acaso costaría más que el resto del lint
    # junto.
    _pdf_hash_cache: dict = {}

    def evidencia_hash_de(bib: str, kind: str) -> str | None:
        """Hash VIGENTE del archivo que la fila dice haber leído. `None` si ese archivo no está."""
        if kind == "pdf":
            if bib not in _pdf_hash_cache:
                _p = pdf_on_disk.get(bib)
                _pdf_hash_cache[bib] = lb.bytes_hash(Path(_p)) if _p else None
            return _pdf_hash_cache[bib]
        return ft_hash.get(bib)

    # ── #118 · la bitácora no tiene red ──────────────────────────────────────────────────────────
    # Lo que escribe un SCRIPT se registra solo (`cadena` del registro versionado: qué corrió y
    # cuándo); lo que escribe el LLM depende de que se acuerde. `CLAUDE.md` manda appendear a
    # `log.md` tras cada operación y es el único paso salteable SIN red — #55, #56, #69 y #75 ya la
    # tienen. Medido sobre un tema real: 22 pasos de cadena registrados, 0 entradas en el log.
    # Los dos lados de la comparación ya viajan dentro de la bóveda, así que es offline y sin
    # dependencias. BACKLOG, nunca bloqueante: una bitácora incompleta no invalida ninguna
    # afirmación —a diferencia de una cita rota—, y frenar el cierre por esto vuelve trámite al lint.
    try:
        log_txt = cfg.LOG.read_text(encoding="utf-8") if cfg.LOG.exists() else ""
    except OSError:
        log_txt = ""
    for _reg in sorted(cfg.REGISTRO.glob("*.yaml")) if cfg.REGISTRO.exists() else []:
        _slug = _reg.stem
        if _slug.startswith("_"):
            continue                      # `_red.yaml` no es un sujeto
        try:
            _d = cfg.load_registro(_slug) or {}
        except Exception:
            continue                      # registro ilegible: lo reporta su propio detector
        # #88: ¿se tendió la segunda red? El barrido full-text es el ÚNICO camino para el punto
        # ciego de la query directa —surveys que TABULAN la estrella sin nombrarla en el abstract y
        # que además no están en el grafo de citas— y hasta ahora era un preview de stdout: no se
        # podía saber si se había corrido. Backlog: no invalida nada de lo que la ficha afirma.
        _barridos = [b for b in cfg.as_list(_d.get("barridos")) if isinstance(b, dict)]
        if _slug in stars_slugs and not _barridos:
            sweep_pendiente.append(
                (_slug, "el barrido full-text (2b) no consta en el registro: es el único camino "
                        "para los surveys que TABULAN la estrella sin nombrarla en el abstract → "
                        f"`python scripts/query_ads.py {_slug} --sweep`"))
        # AUD-181 / INV-118 — un barrido TRUNCADO se leía igual que uno completo: «la red se tendió
        # y esto es todo lo que hay», sobre una cola que nadie miró. Es la segunda red del sujeto,
        # así que su cola importa tanto como la de la query directa.
        elif _barridos and _barridos[-1].get("truncated"):
            sweep_pendiente.append(
                (_slug, f"el barrido full-text del {_barridos[-1].get('fecha') or 's/f'} quedó "
                        f"TRUNCADO (ADS reporta {_barridos[-1].get('n_found')} y se pidieron "
                        f"{_barridos[-1].get('rows')}) → "
                        f"la cola no se miró; re-corré con `--rows` mayor"))
        _fechas = {str(p.get("fecha")) for p in cfg.as_list(_d.get("cadena"))
                   if isinstance(p, dict) and p.get("fecha")}
        # AUD-177 / INV-131 — se exigía el SLUG en el encabezado y la convención documentada usa el
        # título de la operación, que es el **nombre** («## 2026-08-28 — ingest: tau Ceti», no
        # `tau_ceti`). El detector reportaba entonces backlog permanente sobre bitácora correcta —
        # un falso positivo así erosiona la categoría entera: la primera vez que alguien la ve
        # mentir, deja de mirarla. Se acepta cualquiera de los nombres con los que el sujeto se
        # nombra: slug, nombre canónico, `concept` y alias.
        _nombres = {_slug, _slug.replace("_", " ")}
        _meta_s = cfg.as_map(({} if cfg.stars_error() else cfg.load_stars()).get(
            next((n for n, m in ({} if cfg.stars_error() else cfg.load_stars()).items()
                  if isinstance(m, dict) and m.get("slug") == _slug), None)))
        _meta_t = cfg.as_map(({} if cfg.themes_error() else cfg.load_themes()).get(_slug))
        for _n, _m in ((None, _meta_s), (None, _meta_t)):
            _nombres |= {str(x) for x in cfg.as_list(_m.get("aliases")) if str(x).strip()}
            if _m.get("concept"):
                _nombres.add(str(_m["concept"]))
        _nombres |= {n for n, m in ({} if cfg.stars_error() else cfg.load_stars()).items()
                     if isinstance(m, dict) and m.get("slug") == _slug}
        _sin = sorted(f for f in _fechas
                      if f and not any(f in ln and any(x in ln for x in _nombres)
                                       for ln in log_txt.splitlines() if ln.startswith("## ")))
        if _sin:
            #  @inv INV-131
            log_sin_entrada.append(
                (_slug, f"la cadena corrió el {', '.join(_sin)} y `log.md` no tiene una entrada "
                        f"`## <fecha> — …` que nombre a `{_slug}` → appendear lo que se hizo"))

    stale_pairs: list = []
    old_verif_template: list = []
    verif_sin_archivo: list = []       # (stem, motivo) — #117: la fila no dice qué archivo leyó
    verif_localizador: list = []       # (stem, motivo) — #122: el localizador contradice al prefijo
    verif_sin_resolver: list = []      # (stem, motivo) — #91: veredicto que exige acción y no la tuvo
    verif_estructura: list = []        # (stem, motivo) — #232: sub-secciones o cabecera del bloque
    for stem, texto in sorted(anchor_notes):
        filas = lb.parse_verif_table(texto)
        if filas is None:
            old_verif_template.append(
                (stem, "el bloque de verificación no tiene las columnas `Ancla` / `Hash fuente` "
                       "(plantilla vieja) → no se puede evaluar qué par sigue vigente; re-correr "
                       "`verify-citations` para que lo reescriba con un par por fila"))
            continue
        # #232 — la ESTRUCTURA del bloque, que nadie miraba más allá de la tabla. Las tres
        # sub-secciones que la plantilla cierra son el único lugar donde queda escrito el triage de
        # la corrida: medido, de 91 condiciones pobladas 28 declaraban una omisión de la nota y
        # nada decía cuáles se juzgaron no vinculantes — el razonamiento se hizo, vivió en `build/`
        # (scratch) y no llegó al artefacto que viaja. Se exigen aunque digan «ninguna»: la
        # diferencia entre «no hubo» y «nadie miró» es exactamente lo que este framework persigue.
        _falt = [x for x in lb.VERIF_SUBSECCIONES if x not in texto]
        if _falt:
            verif_estructura.append(
                (stem, f"el bloque no trae {len(_falt)} de las tres sub-secciones que la plantilla "
                       f"cierra ({', '.join(_falt)}) — van aunque digan «ninguna»: es el único "
                       f"lugar donde queda escrito el triage de la corrida"))
        # #232 — y los conteos de la cabecera los da el MISMO código que lee la tabla (INV-81). A
        # mano derivan: la cabecera de un bloque real describía la ronda 1 sobre 96 pares mientras
        # su tabla tenía 99, y omitía las condiciones (91/99) y las contradicciones resueltas.
        _resumen = lb.verif_summary(filas)
        if f"{len(filas)} pares" not in texto:
            verif_estructura.append(
                (stem, f"la cabecera del bloque no publica «{len(filas)} pares» (la tabla tiene "
                       f"{len(filas)} filas) → línea canónica: «{_resumen}»"))

        # #280 — y el conteo de cada SUB-SECCIÓN, por el mismo argumento (INV-81) un nivel abajo.
        # Se compara por FRAGMENTO verbatim, como el `N pares` de arriba: parsear el primer entero
        # de la prosa erraría justo en el caso medido, donde la frase tiene dos números y el malo es
        # el segundo. Sólo se chequea la sub-sección PRESENTE: la ausente ya la reporta `_falt`, y
        # duplicar el hallazgo manda a hacer dos veces el mismo trabajo.
        _frags = lb.verif_subsection_lines(filas, cfg.solo_prosa(body_full))
        for _sub, _frag in _frags.items():
            if _frag and _sub in texto and _frag not in texto:
                verif_estructura.append(
                    (stem, f"la sub-sección «{_sub}» no publica el conteo que su propia tabla da → "
                           f"línea canónica: «{_sub} {_frag}: …»"))

        pendientes = lb.pairs_of(texto)
        for fila in filas:
            # #91: el lint miraba el bloque SÓLO por su encabezado (¿existe? ¿está fresco?) y nunca
            # su contenido, así que una fila `no-soportada` pasaba limpia — sentada bajo un
            # encabezado que se lee como garantía. El contrato manda RESOLVER cada falla, no
            # registrarla: es la frontera dura, igual que citar una fuente retractada.
            if not lb.verdict_valido(fila.verdict):
                # Typo o celda vacía: se arregla distinto que un `no-soportada` sin resolver, así
                # que el mensaje no puede ser el mismo. Y hasta 2026-08-28 esto pasaba **limpio**:
                # `resueltos('contradise')` devolvía True y apagaba el bloqueante de INV-117.
                verif_sin_resolver.append(
                    (stem, f"[[{fila.bibcode}]] tiene `{fila.verdict or '(vacío)'}` en la columna "
                           f"`Veredicto`, que no está en el vocabulario cerrado "
                           f"({' | '.join(lb.VERDICTS)}): la celda no se puede leer, así que no "
                           f"certifica nada — corregí el veredicto"))
            elif not lb.resueltos(fila.verdict):
                verif_sin_resolver.append(
                    (stem, f"[[{fila.bibcode}]] quedó `{fila.verdict}` en el bloque: la nota afirma "
                           f"algo que su propia fuente no respalda → bajala a lo que dice la fuente, "
                           f"reasigná la cita, marcala `inferencia`, o tagueá la disputa"))
            exacto = next((p for p in pendientes
                           if p.bibcode == fila.bibcode and p.anchor == fila.anchor), None)
            if exacto is not None:
                pendientes.remove(exacto)
                # #113/B-2: si la fuente perdió el cuerpo de sus ecuaciones, la evidencia de sus
                # pares es una PÁGINA del PDF y el archivo a vigilar es el PDF. Hashear el `.txt`
                # ahí se dispara en falso al re-extraerlo (la fuente real no se movió) y no vigila
                # el archivo del que sale la cita.
                if fila.source_kind is None and lb.has_no_source_file(fila.verdict):
                    # #223: `no verificable por extracción` es propiedad de la FUENTE —no hay PDF ni
                    # `.txt` en disco— así que la fila NO PUEDE declarar un archivo: no hay qué
                    # hashear. Exigírselo era pedirle que nombrara un archivo justo a la fila que
                    # existe para decir que no lo hay. Mismo criterio con que ese veredicto ya está
                    # fuera de `VERDICTS_SIN_RESOLVER`.
                    continue
                if fila.source_kind is None:
                    # #117: sin declaración no hay contra qué comparar. Inferirlo del frontmatter es
                    # justamente lo que fabricaba pares vencidos, así que acá se declara NO
                    # EVALUABLE y se migra — no se adivina.
                    verif_sin_archivo.append(
                        (stem, f"la fila de [[{fila.bibcode}]] no declara contra qué archivo se "
                               f"verificó (`Hash fuente` sin prefijo `txt:`/`pdf:`) → "
                               f"`python scripts/make_notes.py --migrate-verif-archivo`"))
                    continue
                # #122: el localizador de `Evidencia` y el prefijo dicen lo mismo desde ángulos
                # distintos. Si discrepan, el hash vigila un archivo del que la cita no salió —
                # se dispara en falso al re-extraer el `.txt` y no ve que el PDF cambió.
                # #200: una fila con los DOS localizadores no es hallazgo (`len(_locs) == 1`), y ésa
                # es la salida que el mensaje tiene que nombrar. Una fuente `unidad_cita: pagina`
                # leída del `.txt` cae acá **siempre** —#80 manda citar por página, #117 que el
                # prefijo case— y las dos salidas obvias empeoran la fila: poner `pdf:` miente sobre
                # qué archivo se abrió, y citar por línea rompe #80. Medido: 6 de 8 filas marcadas
                # de un concepto real eran ese caso, todas correctas.
                # #226 — la celda TRUNCADA. Medido sobre las 99 filas de una nota real: 81
                # `Evidencia` y 79 `Condición` cortadas con `…` a exactamente 191 caracteres. El
                # docstring de `lib_blocks` dice que sin `condición` el bloque «tiraba lo que la
                # corrida había encontrado sobre el régimen — el output más valioso del fan-out»;
                # truncar hace la mitad de eso, y lo cortado NO se recupera desde la nota (una fila
                # corta en «(a) la calibración sintética…» y nunca llega a (b)). El `Afirmación` sí
                # se puede truncar: es un extracto por definición, y lo dice su encabezado.
                for _col, _val in (("Evidencia", fila.evidence), ("Condición", fila.condition)):
                    if str(_val).rstrip().endswith("…"):
                        verif_truncada.append(
                            (stem, f"[[{fila.bibcode}]] par {fila.n}: `{_col}` quedó cortada con "
                                   f"`…` — lo que el fan-out encontró y no entró no se recupera "
                                   f"desde la nota; sólo `Afirmación (extracto)` es truncable"))
                # #221 — la condición sin CLASIFICAR. El fan-out la puebla al 89 % de los pares,
                # así que la instrucción «resolvé cada condición no vacía» es inaplicable tal cual
                # —86 filas de `## Régimen de validez` sobre una nota de 413 líneas, contra la regla
                # de poda— y se deja de cumplir en silencio. El vocabulario cerrado separa la que
                # obliga a editar (`acota`: la afirmación es FALSA fuera de esa condición) de la que
                # sólo agrega procedencia (`contextualiza`). Es el diagnóstico de #198 un eje más
                # allá: acotar la pregunta, no eliminarla.
                _cond = str(fila.condition or "").strip()
                if _cond and _cond not in ("—", "-", "–") and lb.condition_kind(_cond) is None:
                    cond_sin_clasificar.append(
                        (stem, f"[[{fila.bibcode}]] par {fila.n}: la condición no declara si "
                               f"`acota:` (la afirmación es falsa fuera de ella → hay que resolverla) "
                               f"o `contextualiza:` (agrega procedencia → va al reporte)"))
                _locs = lb.locator_kinds(fila.evidence)
                # #226 — `_locs` vacío NO puede ser silencio: es NO EVALUABLE, y acá eso se declara
                # (D-43) en vez de resolverse a favor. Medido: al truncar `Evidencia` se va el `p. N`
                # del final, así que 62 de 90 filas con `pdf:` no tenían localizador legible y el
                # chequeo de #122 devolvía 0 — un cero que se lee como verde sobre el 69 % de la
                # nota. Sub-disparo silencioso, la dirección de error que `lib_blocks` prohíbe.
                if not _locs:
                    verif_sin_localizador.append(
                        (stem, f"[[{fila.bibcode}]] par {fila.n}: la evidencia no trae localizador "
                               f"(`p. N` o `L…`), así que el cruce de #122 contra `{fila.source_kind}:` "
                               f"NO se pudo evaluar en esta fila"))
                if _locs and _locs != {fila.source_kind} and len(_locs) == 1:
                    _l = next(iter(_locs))
                    verif_localizador.append(
                        (stem, f"[[{fila.bibcode}]]: la evidencia cita "
                               f"{'una PÁGINA' if _l == 'pdf' else 'una LÍNEA'} y la fila vigila "
                               f"{'el `.txt`' if fila.source_kind == 'txt' else 'el PDF'} → si la "
                               f"cita salió de ese archivo, re-anclar a `{_l}:`; si la fuente es "
                               f"larga (`unidad_cita: pagina`) y se leyó del `.txt`, poné los DOS "
                               f"localizadores (`p. 271 / \u0060.txt\u0060 L13931`) — las dos cosas "
                               f"son ciertas y ninguna se ablanda"))
                vigente = evidencia_hash_de(fila.bibcode, fila.source_kind)
                que = "el PDF" if fila.source_kind == "pdf" else "el `.txt`"
                if vigente is None:
                    verif_sin_archivo.append(
                        (stem, f"la fila de [[{fila.bibcode}]] dice haberse verificado contra "
                               f"{que} y ese archivo no está en la bóveda → no se puede evaluar "
                               f"si la fuente cambió"))
                elif fila.source_hash != vigente:
                    stale_pairs.append(
                        (stem, f"[[{fila.bibcode}]] vencido **por fuente**: {que} cambió desde "
                               f"la verificación ({fila.source_hash} → {vigente}) — re-verificar"))
                continue
            # sin coincidencia exacta: ¿la nota sigue citando esa fuente en algún bloque? Entonces
            # la afirmación se EDITÓ. Si ya no la cita, la fila quedó huérfana. Se consume el par
            # para no reportar el mismo evento dos veces (como edición Y como sin-verificar).
            movido = next((p for p in pendientes if p.bibcode == fila.bibcode), None)
            if movido is not None:
                pendientes.remove(movido)
                stale_pairs.append(
                    (stem, f"[[{fila.bibcode}]] vencido **por edición**: el bloque que lo cita "
                           f"cambió desde la verificación ({fila.anchor} → {movido.anchor})"))
            else:
                stale_pairs.append(
                    (stem, f"fila **huérfana**: la tabla verifica [[{fila.bibcode}]] pero el cuerpo "
                           "ya no lo cita — se borró la afirmación y la fila quedó afirmando de más"))
        for p in pendientes:
            stale_pairs.append(
                (stem, f"[[{p.bibcode}]] **sin verificar**: hay una afirmación que lo cita y no "
                       f"tiene fila en el bloque (ancla {p.anchor})"))

    # ── D-47: la prosa que cita una fuente RETRACTADA se marca, no se borra ──────────────────────
    # El lint ya bloquea la NOTA del paper retractado, pero no localiza QUÉ afirmación lo cita —
    # que es lo que hay que revisar. Borrar la afirmación tampoco sirve: destruye trabajo y puede
    # ser cierta por otra vía. Se marca en línea (R-3: `[[bib]] ⛔retractada`), y ahí baja a
    # informativa: visible, no destruida. El símbolo es deliberado — un `(retractada)` pelado daría
    # falso positivo con cualquier mención del hecho en prosa ("la señal fue retractada más tarde").
    # #279 — la ficha que se apoya en un paper cuya vista marcó valores de SEGUNDA MANO y no lo
    # dice. Se mira por BLOQUE citante (`pairs_of`, que ya excluye las secciones estampadas: la
    # tabla `## Papers` cita todos los bibcodes y haría estallar la categoría), y el hallazgo se
    # apaga si el bloque ya nombra la segunda mano — sin esa escotilla la deuda es inextinguible y
    # una categoría que no se puede cerrar se deja de mirar.
    for f, texto_n in anchor_bodies.items():
        if not (in_dir(f, "stars") or in_dir(f, "concepts")):
            continue
        for _par in lb.pairs_of(texto_n):
            _filas = segunda_mano.get(_par.bibcode)
            if not _filas or "segunda mano" in _par.block.text.lower():
                continue
            _quien = "; ".join(f"{q} → {de}" for q, _v, de in _filas[:3])
            segunda_mano_perdida.append(
                (basename(f)[:-3],
                 f"L{_par.block.first_line}: la prosa se apoya en [[{_par.bibcode}]] y su vista "
                 f"marca {len(_filas)} valor(es) de SEGUNDA MANO ({_quien}) → si el valor es uno de "
                 f"ésos, la ficha tiene que decir de quién es (#103): el número no es de esta fuente"))

    retracted_stems = {stem for stem, fm_p in paper_fms.items() if fm_p.get("retracted")}
    gt_prosa: list = []                # (slug, motivo) — #278: la prosa desmiente su ground-truth
    prosa_retractada: list = []        # @inv INV-93
    prosa_retractada_marcada: list = []
    for f, texto_n in anchor_bodies.items():
        stem_n = basename(f)[:-3]
        # AUD-154 — esto escaneaba el TEXTO CRUDO, o sea también las secciones que estampa la
        # máquina y `log.md`. Las dos hacen el bloqueante **irresoluble**: la marca `⛔retractada`
        # puesta en una fila de `## Papers` la borra el próximo `make_notes` (es metadata derivada,
        # se regenera), y `log.md` es la bitácora append-only —marcar una entrada histórica sería
        # reescribir lo que pasó—. La cita que hay que revisar es la de la PROSA, que es donde la
        # bóveda afirma algo apoyándose en esa fuente.
        if stem_n in ("log", "index"):
            continue
        partes_n = cfg.frontmatter_span(texto_n)
        texto_n = cfg.solo_prosa(partes_n[1] if partes_n else texto_n)
        for stem_r in sorted(retracted_stems):
            for m in re.finditer(r"\[\[" + re.escape(stem_r) + r"(?:\|[^\]]*)?\]\]([^\n]*)", texto_n):
                destino = (prosa_retractada_marcada if m.group(1).lstrip().startswith(RETRACTED_MARK)
                           else prosa_retractada)
                destino.append(
                    (stem_n, f"cita [[{stem_r}]] (RETRACTADO) — "
                             + ("marcada: visible y no destruida; revisá si otra fuente la sostiene"
                                if destino is prosa_retractada_marcada else
                                f"marcala con `{RETRACTED_MARK}` pegado a la cita, o bajá la "
                                f"afirmación a lo que otra fuente sostenga. No la borres: puede ser "
                                f"cierta por otra vía")))

    # ── ground-truth que se movió bajo la prosa (AUD-42) ─────────────────────────────────────────
    # `_cambios` lo estampa `sweep_external.aplicar_ground_truth` al aplicar un diff de NEA. Mientras
    # exista, la prosa de esa ficha se escribió contra valores que ya no son los publicados. No
    # bloquea —la frase puede seguir siendo correcta, y borrarla destruiría trabajo—: se pide la
    # marca, igual que con una fuente retractada (D-47). Con la marca puesta baja a informativo.
    gt_cambiado: list = []
    gt_cambiado_marcado: list = []
    for gt in sorted(glob.glob(str(cfg.GROUND_TRUTH / "*.json"))):
        slug_gt = basename(gt)[:-5]
        try:
            datos_gt = json.loads(open(gt, encoding="utf-8").read())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue                      # el JSON ilegible ya tiene su propia categoría bloqueante
        cambios_gt = datos_gt.get("_cambios") if isinstance(datos_gt, dict) else None
        if not isinstance(cambios_gt, list) or not cambios_gt:
            continue
        nota_gt = cfg.STARS / f"{slug_gt}.md"
        if not nota_gt.exists():
            continue                      # ficha faltante: ya la reporta el hermano simétrico
        # ⛔ #131: acá había `GT_STALE_MARK in nota_gt.read_text(...)`, o sea a nivel ARCHIVO — una
        # sola marca en cualquier parte de la ficha silenciaba TODOS los `_cambios` de la estrella.
        # `CLAUDE.md` dice la marca **pegada al valor**, y su gemelo `⛔retractada` sí se evalúa por
        # ocurrencia. Se decide por campo, sobre las líneas que llevan la marca.
        marcadas = [ln for ln in nota_gt.read_text(encoding="utf-8").splitlines()
                    if GT_STALE_MARK in ln]
        for c in cambios_gt:
            if not isinstance(c, dict):
                continue
            campo = c.get("campo", "?")
            marcada = _field_is_marked(marcadas, campo, c.get("viejo"))
            detalle = f"NEA cambió {campo} ({c.get('viejo')!r} → {c.get('nuevo')!r}) el {c.get('fecha', 's/f')}"
            (gt_cambiado_marcado if marcada else gt_cambiado).append(
                (slug_gt, detalle + ("; la prosa está marcada: revisá si ya la actualizaste y sacá "
                                     "la marca cuando lo hagas"
                                     if marcada else
                                     f"; la prosa que lo citaba NO se actualizó sola — actualizala "
                                     f"o marcala con `{GT_STALE_MARK}`")))

    # ── identidad duplicada (D-19 / INV-84) ──────────────────────────────────────────────────────
    # La identidad de un trabajo es su `doi`/`arxiv_id`, no su bibcode: el preprint y el publicado
    # son bibcodes distintos del MISMO paper. Medido en la instancia real: 2 trabajos con dos notas.
    # Bloqueante porque el daño es silencioso y se acumula: doble conteo en todo lo que cuenta
    # papers, dos fuentes donde hay una, y un falso positivo permanente de #75 (la ficha cita una).
    # Un alias en `versions[]` NO es un duplicado: es el registro de que el trabajo tuvo otro
    # bibcode, y por eso no entra en la población.
    identidad_dup: list = []
    alias_con_nota: list = []          # #229: listado como alias Y con nota propia — contradicción
    por_identidad: dict = {}
    alias = {str(v.get("bibcode")) for fm_p in paper_fms.values()
             for v in cfg.as_list(fm_p.get("versions")) if isinstance(v, dict) and v.get("bibcode")}
    # #229 — la exención por alias es incondicional, y eso APAGA los dos detectores de identidad
    # sobre una nota viva. Medido: una nota usó `versions[]` para decir «no son duplicados, se
    # conservan los dos» —lo contrario de lo que el campo significa en D-19— y con eso dejó a una
    # de las 4 notas SIN `doi` ni `arxiv_id` (justo la población que #216 existe para cubrir) fuera
    # de los dos chequeos, para siempre. El lint seguía declarando «sobre 32 notas» mirando 31.
    # O es un alias (y entonces NO debe haber nota) o es un trabajo distinto (y entonces NO va en
    # `versions[]`): la contradicción de schema es lo que bloquea, no la exención.
    for _a in sorted(alias & set(paper_fms)):
        _quien = sorted(st for st, fm_p in paper_fms.items()
                        if any(isinstance(v, dict) and str(v.get("bibcode")) == _a
                               for v in cfg.as_list(fm_p.get("versions"))))
        alias_con_nota.append(
            (_a, f"está listado en `versions[]` de {', '.join(_quien)} Y tiene su propia nota: o es "
                 f"un alias (y la nota no debería existir) o es otro trabajo (y no va en "
                 f"`versions[]`). Mientras tanto queda fuera de los DOS chequeos de identidad "
                 f"(D-19 y #216), que es donde más falta hace"))
    # #230 — la contradicción sobre el disco que nadie cruzaba: `fulltext: null` con
    # `fulltext_source` poblado afirma CÓMO se extrajo un texto que no existe. `retarget_artifacts`
    # (#217) limpia los tres campos del `.txt`, así que el par lo produce una edición a mano o una
    # nota anterior a esa versión.
    #
    # ⛔ Y la asimetría con `pdf_source` es DELIBERADA y va declarada: ése NO se limpia, porque no
    # describe un archivo sino la PROCEDENCIA de la lectura que ocurrió — una nota cuelga su
    # salvedad de `pdf_source: eprint` para decir que sus citas son contra el preprint, y borrarlo
    # al borrar el archivo destruiría la salvedad junto con el PDF. El contrato lo dice, y por eso
    # el par `pdf: null` + `pdf_source: <valor>` NO es hallazgo.
    for stem_p, fm_p in sorted(paper_fms.items()):
        if fm_p.get("fulltext_source") and not fm_p.get("fulltext"):
            incomplete.append(
                (stem_p, f"`fulltext_source: {fm_p['fulltext_source']}` sin `fulltext` — afirma "
                         f"CÓMO se extrajo un texto que no está en disco → "
                         f"`python scripts/make_notes.py <slug>` re-estampa por verdad de disco "
                         f"(⚠ `pdf_source` sí sobrevive al borrado, a propósito: es la procedencia "
                         f"de la lectura, no del archivo)"))

    for stem_p, fm_p in sorted(paper_fms.items()):
        if stem_p in alias:
            continue
        if (ident := mn.identidad(fm_p)):
            por_identidad.setdefault(ident, []).append(stem_p)
    for (clave, valor), stems in sorted(por_identidad.items()):
        if len(stems) > 1:
            identidad_dup.append(
                (", ".join(stems), f"comparten {clave} `{valor}` → es el MISMO trabajo con dos "
                                   f"notas; dejá una canónica: `python scripts/make_notes.py "
                                   f"--rename-paper {stems[0]} {stems[1]}`"))
    # #114 · segunda señal, y la que caza el caso REAL: dos notas cuyo `.txt` tiene los MISMOS BYTES
    # son el mismo trabajo — eso no es heurística, es certeza. Hace falta porque la metadata a veces
    # no los liga en absoluto: medido, el registro publicado traía `arxiv_id: null` y el del preprint
    # el DOI DataCite, así que NINGÚN campo coincidía y el detector callaba sobre un duplicado real.
    # ⚠ Sólo sobre `.txt` **legibles**. Dos extracciones FALLIDAS (escaneo sin capa de texto,
    # mojibake, `.txt` casi vacío) tienen los mismos bytes y no son el mismo trabajo: son dos
    # fracasos idénticos. Sin este recorte, la señal de bytes convierte a cada par de extracciones
    # rotas en un hallazgo BLOQUEANTE que manda a fusionar dos papers ajenos — o sea a destruir una
    # nota. Medido sobre el corpus sintético: dos `.txt` ilegibles sembrados a propósito daban un
    # tercer duplicado que nadie sembró. El umbral no es nuevo: es el mismo `is_legible` con el que
    # el lint ya reporta esos `.txt` en su propia categoría, y que dice justamente «esto no sirve
    # para grep ni para verify» — un texto que no sirve para leerlo tampoco identifica a nadie.
    # @inv INV-106
    ya_reportados = {st for fila in identidad_dup for st in fila[0].split(", ")}
    ft_ilegible = {basename(p_ft)[:-4] for p_ft, _ in illegible_txt}
    por_texto: dict = {}
    for stem_p in sorted(paper_fms):
        if stem_p in alias or stem_p in ya_reportados or stem_p in ft_ilegible:
            continue
        if (h := ft_hash.get(stem_p)):
            por_texto.setdefault(h, []).append(stem_p)
    for h, stems in sorted(por_texto.items()):
        if len(stems) > 1:
            identidad_dup.append(
                (", ".join(stems), f"su fulltext tiene los MISMOS bytes (`{h}`) → es el mismo "
                                   f"trabajo con dos notas, aunque su metadata no lo diga; "
                                   f"consolidá: `python scripts/make_notes.py --rename-paper "
                                   f"{stems[0]} {stems[1]}`"))

    # ── #216 · duplicado SIN doi ni arxiv_id (backlog, REPORTA y no fusiona) ─────────────────────
    # D-19 identifica un trabajo por `doi`/`arxiv_id`, y la clase de fuentes donde el duplicado es
    # MÁS probable es justamente la que no tiene ninguno de los dos: resúmenes de congreso (el mismo
    # trabajo presentado en EAS, COSPAR y SPIE), tesis, material pre-DOI. Medido en `ica`: de 52
    # core, 6 sin ningún identificador —el 12 % del corpus invisible para el chequeo— y ahí apareció
    # un duplicado real, con el mismo texto palabra por palabra. Y a diferencia del par
    # preprint↔publicado, éste NO tiene señal alternativa: el bibcode no comparte prefijo, los años
    # difieren y los autores se abrevian distinto.
    # ⛔ REPORTA, no fusiona, y por eso es BACKLOG: la distinción «mismo trabajo en dos congresos»
    # vs «dos etapas del mismo programa con resultados distintos» es real y estuvo presente en el
    # mismo corpus (un registro de 2022 reporta NO-detección y el de 2023 detección tentativa: no
    # son duplicados y se conservaron los dos). Sólo quien conoce el trabajo puede decidirlo, y un
    # dedup automático que fusiona dos trabajos distintos destruye más de lo que arregla.
    # ⛔ Y NO se compara por TÍTULO: está medido en `openalex.py` y es peor que el problema (18 de
    # 25 resueltos, **2 apuntando a otro trabajo**). El `## Abstract` verbatim está garantizado en
    # toda nota desde #124, así que el dato está y es mucho más específico.
    abstract_dup: list = []
    por_abstract: dict = {}
    for stem_p in sorted(paper_fms):
        fm_p = paper_fms[stem_p]
        if stem_p in alias or stem_p in ya_reportados:
            continue
        if fm_p.get("doi") or fm_p.get("arxiv_id"):
            continue                    # con identificador ya lo mira el detector bloqueante
        ab = paper_abstracts.get(stem_p) or ""
        if len(ab) < ABSTRACT_MIN:
            continue
        por_abstract.setdefault(ab[:ABSTRACT_CLAVE], []).append(stem_p)
    for _clave, stems in sorted(por_abstract.items()):
        if len(stems) > 1:
            abstract_dup.append(
                (", ".join(stems), "ninguna tiene `doi` ni `arxiv_id` y su `## Abstract` coincide "
                                   "palabra por palabra → ¿el MISMO trabajo en dos congresos, o dos "
                                   "etapas del mismo programa con resultados distintos? Decidilo "
                                   f"vos: si es lo primero, consolidá (`--rename-paper {stems[0]} "
                                   f"{stems[1]}` + `versions[]`) o sacá el registro sobrante "
                                   "(`triage.py <slug> --drop-core … --reason`); si es lo segundo, "
                                   "no hay nada que hacer"))

    # ── lista de papers desactualizada (D-10) ────────────────────────────────────────────────────
    # La tabla materializada de `## Papers` es un snapshot, y un snapshot que nadie re-estampa
    # miente igual que el roll-up Dataview que reemplazó (medido: 155 prometidos, 8 discutidos).
    # Backlog —es "re-estampar", no una violación del vault— pero NOMBRA los stems que faltan o
    # sobran, no la diferencia de conteos: dos listas del mismo largo pueden no ser los mismos
    # papers (la lección de #70).
    papers_table_stale: list = []
    # UNA sola pasada de parseo de `papers/`, compartida por todas las estrellas: sin esto el lint
    # saltaba de ~2,0 a 5,9 parseos YAML por nota (medido por `tests/poblada/test_escala.py`, techo
    # 2,3) — el costo crece con el producto notas × estrellas.
    # `paper_fms` se llena en el LOOP principal (ver más arriba), que ya parsea cada nota: una
    # pasada extra acá subía el ratio a ~3,0 (el techo del test de escala es 2,3), y el hotspot
    # conocido —el doble parseo de split_fm+fm_error— ya se come 2,0.
    for nombre, meta_s in ({} if cfg.stars_error() else cfg.load_stars()).items():
        slug_s = meta_s.get("slug") if isinstance(meta_s, dict) else None
        dest_s = cfg.STARS / f"{slug_s}.md" if slug_s else None
        if not dest_s or not dest_s.exists():
            continue
        try:
            esperados = {r["stem"] for r in mn.papers_universe(slug_s, "star", paper_fms)}
        except Exception:
            continue                      # config rota: ya lo reporta otra categoría
        texto_s = dest_s.read_text(encoding="utf-8")
        seccion = texto_s.split("\n" + mn.PAPERS_HEADER, 1)
        listados = set()
        if len(seccion) > 1:
            cuerpo_s = seccion[1].split("\n## ", 1)[0]
            listados = {m for m in LINK_RE.findall(cuerpo_s)}
        faltan, sobran = esperados - listados, listados - esperados
        if faltan or sobran:
            detalle = []
            if faltan:
                detalle.append("faltan " + ", ".join(sorted(faltan)))
            if sobran:
                detalle.append("sobran " + ", ".join(sorted(sobran)))
            papers_table_stale.append(
                (slug_s, "la lista de papers estampada no refleja el universo: " +
                         "; ".join(detalle) + f" → `python scripts/make_notes.py {slug_s}`"))

    # ── el recorte de lectura no declarado (D-13/D-15 · INV-83) ──────────────────────────────────
    # El contrato dice que el ingest lee TODOS los core. La reconciliación anticipa que el
    # subconjunto va a ser el caso normal (≈6M tokens por estrella si no), así que el problema no es
    # recortar: es recortar **en silencio**. Una ficha se presenta como snapshot de su universo, y
    # un lector no tiene forma de saber que la síntesis salió de 8 de 42 papers.
    # Dos severidades sobre el mismo hecho: sin `extraccion.criterio` declarado, hallazgo con señal
    # (el ingest no leyó todo y no dijo por qué); con criterio, backlog normal — la cola visible de
    # D-15, que el skill `maintain` consume.
    extraccion_no_declarada: list = []      # @inv INV-83
    for nombre_s, meta_s in (list(({} if cfg.stars_error() else cfg.load_stars()).items())
                             + list(({} if cfg.themes_error() else cfg.load_themes()).items())):
        if not isinstance(meta_s, dict):
            continue
        slug_s = meta_s.get("slug")
        pendientes = sin_extraer_por_sujeto.get(str(nombre_s), set()) | \
            sin_extraer_por_sujeto.get(str(meta_s.get("concept") or ""), set())
        if not slug_s or not pendientes:
            continue
        decl = cfg.load_extraccion(slug_s)
        if not decl.get("criterio"):
            extraccion_no_declarada.append(
                (slug_s, f"{len(pendientes)} paper(s) core sin extraer y el registro **no declaró** "
                         f"el recorte ({', '.join(sorted(pendientes)[:3])}…) → o se leen, o se "
                         f"declara el criterio (`extraccion:` en el registro): la ficha se presenta "
                         f"como snapshot del universo y hoy no lo es"))
        elif not decl.get("subconjunto"):
            # AUD-157 — `--extraccion todos` silenciaba el detector **aunque quedara core sin
            # extraer**: la declaración dice «se leyeron todos» y el corpus dice que no. Una
            # declaración que no se cumple es peor que no declarar nada, porque apaga el chequeo
            # que la habría desmentido. `subconjunto: true` sí silencia, que es su función.
            extraccion_no_declarada.append(
                (slug_s, f"el registro declara `extraccion: todos los core` ({decl.get('fecha')}) y "
                         f"quedan {len(pendientes)} sin extraer "
                         f"({', '.join(sorted(pendientes)[:3])}…) → o se leen, o se re-declara con "
                         f"`python scripts/triage.py {slug_s} --extraccion subconjunto --reason "
                         f"\"<motivo>\"`"))

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
            # AUD-155 / INV-10 — sin `host.mass_msun` (o sin `K_ms`/`P_days`) `msini_earth` devuelve
            # `None` y el chequeo **no corre**, sin que nada lo diga: la ficha se lee como vigilada
            # cuando nadie la miró. Es el cero inventado de D-43 dentro del detector de masas
            # espurias. No bloquea —el dato falta en NEA, no es un error de la bóveda— pero se
            # declara, con el campo que falta nombrado.
            if chk is None and m:
                faltan = [c for c, v in (("host.mass_msun", mstar), ("K_ms", p.get("K_ms")),
                                         ("P_days", p.get("P_days"))) if v is None]
                if faltan:
                    incomplete.append(
                        (slug, f"{p.get('letter')}: la m·sini implícita **no se pudo calcular** "
                               f"(falta {', '.join(faltan)} en el ground-truth) → `mass_earth` "
                               f"queda sin vigilancia; NO es que el chequeo haya dado limpio"))
            # NO es un fallback de compatibilidad: es el chequeo INDEPENDIENTE del lint sobre todo
            # planeta que el fetch no marcó (que son casi todos). `mass_flag` es la marca del fetch;
            # esto la re-deriva offline, que es el trabajo del lint.
            if chk and m and not (1 / MASA_FACTOR_SOSPECHA < m / chk < MASA_FACTOR_SOSPECHA):
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
                # #278 — la otra mitad: la PROSA. `solo_prosa` saca las secciones estampadas, que
                # nombran la autoridad en su propio encabezado y listan todas las letras (`##
                # Planetas`): sin ese recorte el detector se dispara contra la tabla que el
                # estampador escribe — mismo argumento que #214 con el detector de fuga.
                _partes_f = cfg.frontmatter_span(texto_ficha)
                _prosa_f = cfg.solo_prosa(_partes_f[1] if _partes_f else texto_ficha)
                _letras_gt = {str(pl.get("letter")) for pl in planetas_gt if isinstance(pl, dict)}
                for _frase, _motivo in gt_prose_conflicts(_prosa_f, _letras_gt):
                    gt_prosa.append((slug, f"{_motivo} → «{_frase[:160]}»"))
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
    # `sorted`: `incoming` se construye sobre un `set` de strings, cuyo orden depende del hash
    # que Python randomiza POR PROCESO — sin esto la sección sale en orden distinto en cada
    # corrida y el reporte deja de ser comparable consigo mismo (INV-43).
    orphans = sorted(n for n, c in incoming.items() if c == 0 and is_orphan_candidate(n))

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

    # `methods` sin página destino: el slug no matchea ninguna nota, así que el roll-up de la ficha
    # lo estampa como código en vez de `[[link]]` (ver `make_notes.metodos_table`) y el tema no tiene
    # dónde acumular. Es BACKLOG y no bloqueante, al revés que su hermano `thesis_links`, y la
    # asimetría es real: un `thesis_links` nombra un concepto que `ingest-theme` **crea** en la misma
    # operación que lo siembra, mientras que `methods` lo puebla la extracción de `ingest-star`, que
    # no crea conceptos. Bloquear acá le pediría a `ingest-star` cerrar algo que no está en su
    # cadena. Se cierra ingiriendo el tema (o corrigiendo el typo).
    # Contraste cross-paper (3b) sin rastro (#101): la sección está con la fila de la plantilla.
    # Sólo se pide donde el contraste es POSIBLE — hacen falta al menos dos papers extraídos del
    # sujeto; con uno solo no hay contra qué contrastar y el hallazgo sería ruido fijo.
    contraste_pendiente: list = []
    for f in sorted(glob.glob(str(cfg.STARS / "*.md"))) + sorted(glob.glob(str(cfg.CONCEPTS / "*" / "*.md"))):
        stem = basename(f)[:-3]
        try:
            texto = Path(f).read_text(encoding="utf-8")
        except OSError:
            continue
        if not inventario_sin_llenar(texto):
            continue
        extraidos = {s for s, _ in extracted}
        n_extraidos = len({b.strip() for b in LINK_RE.findall(texto)} & extraidos)
        if n_extraidos >= 2:
            contraste_pendiente.append(
                (stem, f"`## Inventario por eje` con la fila vacía de la plantilla y {n_extraidos} "
                       "paper(s) extraídos citados → el contraste cross-paper (3b) no dejó rastro. "
                       "Si de verdad no hay ningún eje en disputa, **borrá la sección** y decilo en "
                       "el `log` (es la escotilla que la plantilla declara)"))

    # #243 — el destino se busca por CLAVE NORMALIZADA, la misma que usa el roll-up
    # (`cfg.method_matches`): comparando el string exacto, `PCA` y `pca` se reportaban como dos
    # deudas distintas y la nota `concepts/methods/pca.md` no contaba como destino de `PCA`.
    _stems_norm = {cfg.method_key(n): n for n in names}
    # #245 — el destino se resuelve también por los `aliases` del concepto: el nombre canónico de un
    # método es el stem de su nota y `aliases` es la tabla de sinónimos que el schema ya pide. Nadie
    # la leía, así que `bisector span` y `bis` eran dos métodos distintos y el backlog contaba dos
    # deudas donde hay una. Medido en una bóveda real: cierra 7 de 121 — chico, y del tipo correcto:
    # lo que vacía el backlog es que el extractor VEA la lista antes de inventar la grafía.
    _alias_idx = cfg.concept_alias_index()
    dangling_methods = sorted(
        (mt, f"usado en {len(refs)} paper(s): {', '.join(sorted(refs)[:3])}"
             + (" …" if len(refs) > 3 else "") + " → sin nota en `concepts/` (ni por `aliases`): "
             "ingerí el tema, corregí el slug, o declaralo como alias del concepto que lo denota")
        for mt, refs in method_refs.items()
        if cfg.method_key(mt) not in _stems_norm and not cfg.method_target(mt, _alias_idx))
    # #245 — y el alias reclamado por DOS conceptos: se reporta, no se resuelve. Cuál concepto
    # denota un nombre es curación, y elegir en silencio decide por el usuario (regla de método 5).
    alias_colision = [(", ".join(sorted(set(stems))),
                       f"declaran el mismo alias `{alias}` → el roll-up resuelve al primero en orden "
                       f"alfabético; decidí cuál lo denota y sacalo del otro")
                      for alias, stems in cfg.alias_collisions()]

    # #243 — y las COLISIONES de grafía, que son el otro lado del mismo defecto: el mismo método
    # escrito de dos maneras no es una deuda de ingesta, es ruido que infla el backlog y que hasta
    # 1.95.0 partía el universo del roll-up. Se reportan NOMBRANDO las grafías (no el conteo), y se
    # cierran unificando la grafía en las notas o dejando que el roll-up las junte —que es lo que
    # ahora hace—. ⛔ Lo que NO se junta solo son los SINÓNIMOS (`gls` / `periodograma-gls`,
    # `lbl` / `line-by-line-rv`): eso es juicio, y a veces son cosas distintas.
    _por_clave: dict = {}
    for mt in method_refs:
        _por_clave.setdefault(cfg.method_key(mt), set()).add(str(mt))
    methods_colision = sorted(
        (sorted(v)[0], f"el mismo método con {len(v)} grafías: {', '.join(sorted(v))} — el roll-up "
                       f"ya las junta (#243); unificá la grafía en las notas para sacarlo del backlog")
        for v in _por_clave.values() if len(v) > 1)

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

    # ── LENTE VACÍA: el objetivo parsea, tiene nombre propio, y no clasifica NADA (AUD-56) ────────
    # Medido en un clon limpio con el `objective.yaml` de una instancia en 1.11.0: `relevance` usa
    # `topics:` (schema pre-R-5, hoy `facets:`), así que `lens_current()` da `facets: {}` mientras
    # `require: [rv]` exige una faceta que no existe — ninguna cosa podría ser core. `objective_error`
    # dice `None` (el YAML está sano), el WARN del placeholder no dispara (el nombre es real), el
    # detector de `topics:` mira NOTAS DE PAPER y no el objetivo, y el lint cerraba en **exit 0**.
    # O sea: el falso limpio exacto que esta herramienta existe para no producir, en el archivo del
    # que depende la definición de "core". Lo agarra `query_ads` recién al correr, pero para entonces
    # ya migraste la bóveda. Bloqueante: sin lente no hay corpus, y con `require` colgando de una
    # faceta inexistente el corte no es "todo core" sino "nada core", que se ve igual que "no hay
    # papers".
    lente_rota = []
    if not obj_err:
        _rel = cfg.as_map(cfg.load_objective().get("relevance"))
        _lente = cfg.lens_current()
        if not _lente.get("facets"):
            _viejo = " (usa `topics:`, el schema pre-R-5 — el campo vigente es `facets:`)" if _rel.get("topics") else ""
            lente_rota.append(
                ("vault/config/objective.yaml",
                 f"`relevance.facets` está vacío{_viejo}: ningún paper puede clasificar como core. "
                 f"Migrá `topics:` → `facets:` o corré el skill `setup`"))
        elif (_faltan := [f for f in (_lente.get("require") or []) if f not in _lente["facets"]]):
            lente_rota.append(
                ("vault/config/objective.yaml",
                 f"`relevance.require` exige faceta(s) que no existen en `facets`: {_faltan} — "
                 f"nada puede ser core, y eso se ve igual que «no hay papers»"))

    # áreas de concepts/ no declaradas en concept_areas (objective.yaml) → posible typo / carpeta
    # fantasma: un `area` mal tipeado en themes.yaml crea carpeta en silencio (ver make_notes). WARN
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
        # #297 — `_red.yaml` (la pasada de red, D-46) es de la BÓVEDA entera, no de un sujeto: no
        # tiene `busquedas`, así que este bloque lo reportaba como *lente desincronizada: no
        # evaluado* y mandaba a «re-correr la cadena del sujeto» sobre un slug que no existe. El
        # otro loop sobre `REGISTRO/*.yaml` ya lo saltea con este mismo criterio; éste no.
        if slug.startswith("_"):
            continue
        # Lector BLINDADO (#h05): antes esto reimplementaba `yaml.safe_load` a mano acá mismo —
        # el único de seis lectores del registro que lo hacía— y por eso se saltaba el blindaje
        # que `cfg.load_registro` ya tiene (YAML roto / forma inválida → `{}`, no una excepción).
        reg = cfg.load_registro(slug)
        if (err_reg := cfg.registro_error(slug)):
            # AUD-131 — esto era BACKLOG, con un mensaje que describía el daño chico ("no se puede
            # saber si hay triage pendiente"). El daño real es otro y es el peor de la bóveda: el
            # registro es el ÚNICO artefacto no regenerable, y mientras no parsee la curación entera
            # queda **revertida en silencio** — los `--drop` dejan de aplicarse, los `--drop-core`
            # vuelven a ser core, `fetch_pdf` los baja de nuevo y el triage los re-propone SIN el
            # motivo. O sea el bug de #51 más el de #112, disparados por un `:` sin comillas. Es la
            # misma familia que el `triage.json` viejo, que ya bloquea: un juicio que queda mudo.
            # `load_decisiones` además rehúsa operar (INV-139), así que la cadena no puede correr
            # con la curación apagada; acá se reporta para que el lint no muera y lo nombre.
            registro_ilegible.append(
                (slug, f"{err_reg} → mientras no parsee, TODA la curación de `{slug}` queda sin "
                       f"aplicar (los descartes vuelven a ser core y el triage los re-propone sin "
                       f"su motivo); arreglá el YAML a mano y volvé a correr el lint"))
            continue
        # Decisión que no es un mapa (#h12): `2006Rasmussen: descartado`, sin `motivo`/`fecha`/
        # `decision`. `load_decisiones` la filtra en silencio (documentado en su docstring, que
        # promete que EL LINT la reporta) — sin este chequeo el triage vuelve a proponer lo ya
        # descartado sin el motivo, el mismo bug que #51 cerró. Corre para TODO registro, tenga o
        # no `build/` local: es independiente del fallback de triage-pendiente/corpus-truncado de
        # abajo.
        # D-28: la clave vieja `busqueda:` (mapa, UNA corrida) es el schema pre-1.26. El lector
        # nuevo no la entiende y no se le agrega un lector tolerante (regla del repo): se detecta y
        # bloquea, porque un registro mudo deja la ficha afirmando sobre un universo que nadie puede
        # reconstruir. Se cierra re-corriendo la cadena (la corrida nueva reescribe `busquedas`).
        if reg.get("busqueda") is not None:
            old_registro.append(
                (slug, "el registro usa la clave `busqueda:` (schema pre-D-28, una sola corrida) — "
                       "el lector ya no la lee → `python scripts/make_notes.py "
                       "--migrate-registros` (pliega la corrida vieja en `busquedas: []` sin "
                       "perderla; re-correr la cadena también sirve, pero cuesta una pasada de red)"))
        # D-57 / INV-91: la cadena deja traza estructurada de qué pasos corrieron. Si el registro
        # tiene `cadena` y le falta un paso del orden canónico, se NOMBRA el paso donde se cortó —
        # "faltan 4 pasos" no es accionable, "se cortó en `fetch_ground_truth`" sí. Backlog: una
        # cadena a medias no invalida lo que hay, pero deja la bóveda con notas a medio hacer y
        # nadie lo diría. Sólo se evalúa para ESTRELLAS: el orden de un tema depende de su `source`
        # (off-ADS no corre query_ads ni fetch_ground_truth) y compararlo contra el orden astro
        # inventaría cortes que no existen.
        if slug in stars_slugs and (corte := cfg.cadena_cortada(slug)):
            if corte == cfg.CADENA_SIN_TRAZA:
                # AUD-149: esto devolvía `None` —el valor de "corrió entera"—, así que el sujeto sin
                # traza salía del chequeo por la puerta del verde. No consta ≠ está completa.
                cadena_incompleta.append(
                    (slug, "no consta: el registro no tiene `cadena` (sujeto anterior a D-57, o "
                           "ninguna corrida estampó su paso) → no se puede saber dónde se cortó; "
                           f"re-corré `python scripts/ingest_star.py {slug}` (es idempotente)"))
            else:
                corridos = [p.get("paso") for p in cfg.load_cadena(slug)]
                cadena_incompleta.append(
                    (slug, f"la cadena se cortó en `{corte}` (corrieron: {', '.join(corridos)}) → "
                           f"re-corré `python scripts/ingest_star.py {slug}` (es idempotente)"))
        dec = reg.get("decisiones")
        if isinstance(dec, dict):
            for clave, v in dec.items():
                if not isinstance(v, dict):
                    bad_decisions.append(
                        (slug, f"decisión `{clave}` no es un mapa (es {type(v).__name__}, falta "
                               f"`decision`/`motivo`/`fecha`) → `load_decisiones` la descarta en "
                               f"silencio y el triage vuelve a proponerla sin el motivo"))
        # D-49 — LENTE DESINCRONIZADA (backlog). `busquedas[].lente` guarda la regla con la que se
        # clasificó esa corrida; `relevance.facets` se edita después y el corte core/no-core se
        # mueve **sin mover `almagesto_version`**, así que el corpus queda clasificado con una
        # regla que ya no es la vigente y nada lo dice. El caso NORMAL es lente-igual y es gratis:
        # el diff (N notas × las regex) sólo se corre cuando `lens_delta` encuentra diferencias.
        # Offline a propósito: el insumo son las notas (título + abstract + `keywords`, D-17), que
        # viajan — `reclass_diff` mide lo mismo pero necesita `build/`, que es scratch gitignored.
        if not cfg.objective_error():
            stored = cfg.lens_stored(slug)
            if stored is None:
                # D-43: no hay con qué comparar → se DICE, no se cuenta como "lente al día". Un
                # registro sin `lente` es pre-1.10.3 (o una corrida que no la guardó).
                lente_desync.append(
                    (slug, "no evaluado: la última búsqueda del registro no guarda `lente`, así "
                           "que no hay contra qué comparar la vigente → re-corré la cadena del "
                           "sujeto para que la estampe"))
            elif (delta := cfg.lens_delta(stored, cfg.lens_current(slug))):
                detalle = "; ".join(delta)
                if not cfg.lens_textual_changed(delta):
                    # El cambio es real y el diff offline NO lo puede ver re-clasificando texto. El
                    # motivo se NOMBRA, no se asume: hasta #106 el mensaje decía siempre "la nota no
                    # guarda `doctype`", que sobre un cambio de umbral es una explicación de otro
                    # caso — atribuir mal es peor que no decir nada (regla de método #4). Se declara
                    # en vez de devolver "0 entran, 0 salen", que se leería como "no movió nada".
                    if all(d.startswith("fundacional_min_citas ") for d in delta):
                        porque = ("es la puerta 2, no un cambio textual — el diff por umbral se "
                                  "reporta en la línea de abajo")
                    elif all(d.startswith("noise_doctypes ") for d in delta):
                        porque = "la nota de paper no guarda `doctype`"
                    else:
                        porque = ("mezcla cambios no evaluables offline (`doctype` no vive en la "
                                  "nota; el umbral es la puerta 2)")
                    lente_desync.append(
                        (slug, f"la lente cambió ({detalle}) pero el diff offline no lo puede "
                               f"evaluar: {porque} → "
                               f"`python scripts/query_ads.py --dry-run --slug {slug}` con build/ presente"))
                else:
                    entran, salen, sin_nota = cfg.lens_diff_offline(slug)
                    techo = (f"; {len(sin_nota)} paper(s) del universo sin nota → no evaluables "
                             f"offline" if sin_nota else "")
                    lente_desync.append(
                        (slug, f"la lente cambió desde la última corrida ({detalle}) → "
                               f"+{len(entran)} entrarían" + (f" ({_muestra(entran)})" if entran else "")
                               + f" / −{len(salen)} saldrían" + (f" ({_muestra(salen)})" if salen else "")
                               + techo + "; re-corré la cadena del sujeto para re-clasificar"))
        # Puerta 2 (#106): va FUERA del `if delta`, porque el umbral puede haberse editado sin que
        # la lente TEXTUAL cambie — son dos ejes distintos del mismo corte, y colgarlo del delta
        # textual lo dejaba mudo justo en el caso que existe para ver.
        p2_entran, p2_salen, p2_sin = cfg.puerta2_cruces(slug)
        if p2_entran or p2_salen or p2_sin:
            techo2 = (f"; {p2_sin} nota(s) sin `citation_count` → no evaluables" if p2_sin else "")
            lente_desync.append(
                (slug, f"el umbral de la puerta 2 (`fundacional_min_citas`) cambió desde la última "
                       f"corrida → +{len(p2_entran)} entrarían"
                       + (f" ({_muestra([b for b, _n in p2_entran])})" if p2_entran else "")
                       + f" / −{len(p2_salen)} saldrían"
                       + (f" ({_muestra([b for b, _n in p2_salen])})" if p2_salen else "")
                       + techo2 + "; el conteo que se movió SOLO lo ve "
                                  "`python scripts/sweep_external.py`"))
        if slug in vistos:
            continue                                  # build/ presente: ya se reportó la verdad viva
        bs = [x for x in cfg.as_list(reg.get("busquedas")) if isinstance(x, dict)]
        b = bs[-1] if bs else {}
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
        # AUD-148: la marca hermana también cae al registro sin `build/`. Antes vivía SÓLO en
        # scratch gitignored, así que post-clone el rescate por glifo incompleto desaparecía y la
        # bóveda se leía como si hubiera visto todo el superset de la constelación.
        if b.get("truncated_glyph"):
            truncated_corpora.append(
                (slug, f"rescate por glifo incompleto en {b['truncated_glyph']} letra(s) según el "
                       f"registro del {fecha} (sin build/{slug}/ local: es el snapshot de esa "
                       f"corrida) → re-ingestá con --rows mayor; pueden faltar papers con lookalike"))

    # INV-19 — capas COLGADAS de una entidad que ya no existe. La otra mitad del invariante ("ni
    # archivo huérfano en `raw/`") no tenía red: había chequeo para `wiki/` (wikilinks rotos,
    # huérfanas) y para el ground-truth, y **ninguno** para el registro, `raw/{pdfs,fulltext}/` ni
    # `build/`. Borrar una entidad a mano —que hasta hoy era el único modo: nueve pasos en prosa—
    # dejaba esos directorios ahí, y el `registro/<slug>.yaml` colgado es el peor de los cuatro: es
    # el único artefacto no regenerable y su juicio de curación queda mudo, apuntando a un sujeto
    # que no existe. Backlog: no invalida nada de lo que hay, pero nadie lo diría.
    if not (cfg.stars_error() or cfg.themes_error()):
        vivos = {m.get("slug") for m in cfg.load_stars().values()
                 if isinstance(m, dict) and m.get("slug")} | set(cfg.load_themes())
        for etiqueta, base, patron in (("registro", cfg.REGISTRO, "*.yaml"),
                                       ("raw/pdfs", cfg.PDFS, "*"),
                                       ("raw/fulltext", cfg.FULLTEXT, "*"),
                                       ("build", cfg.ROOT / "build", "*")):
            if not base.exists():
                continue
            for p_ in sorted(base.glob(patron)):
                # #230 — `build/` es, por `.gitignore`, «scratch del tooling», así que tratar TODO
                # subdirectorio suyo como capa de entidad garantiza el falso positivo: el
                # directorio de trabajo de una auditoría (`build/auditoria/`) se reportaba como
                # defecto de la bóveda. Capa de entidad es la que trae lo que la cadena escribe.
                if etiqueta == "build" and not (
                        (p_ / "ads.json").exists() or (p_ / "extraccion").exists()):
                    continue
                slug_ = p_.stem if patron == "*.yaml" else p_.name
                # `_red.yaml` es de la bóveda entera, no de un sujeto (pasada de red, D-46).
                if slug_.startswith("_") or slug_ in vivos:
                    continue
                if patron == "*" and not p_.is_dir():
                    continue
                extra = (" — es el ÚNICO artefacto no regenerable: su juicio de curación queda "
                         "mudo, apuntando a un sujeto que no existe"
                         if etiqueta == "registro" else "")
                artefactos_colgados.append(
                    (f"{etiqueta}/{slug_}", f"no hay ninguna entidad con slug `{slug_}` en "
                                            f"stars.yaml/themes.yaml{extra} → "
                                            f"`python scripts/entity.py plan {slug_}` no lo va a "
                                            f"encontrar: borralo a mano, o recreá la entidad"))

    # #297 — el reuso D-18 importa a un sujeto nuevo un artefacto cuya antigüedad nadie chequeó, y
    # el detector de versiones vive SÓLO en la pasada periódica. La respuesta natural («si hubiera
    # versión nueva, la búsqueda habría traído otro bibcode y D-19 los une») es falsa justo en el
    # caso frecuente: el DOI del preprint identifica el DEPÓSITO, así que #216 garantiza que
    # preprint y publicado no colisionen — queda el detector de abstract verbatim, que es backlog.
    # Medido en una bóveda real: 62 % del corpus es `eprint` y `_red.yaml` NO EXISTÍA.
    # Se detecta por verdad de disco: el mismo bibcode con PDF bajo ≥2 slugs.
    # #302 — `STATUS.md` se volvió APPEND-ONLY, que es el trabajo del `log`. Es la única de las
    # cuatro piezas de memoria in-repo cuya política de escritura no estaba declarada (del `log` se
    # dice que es append-only, del `index.md` que se estampa, de `CLAUDE.md` que lleva regla +
    # ancla con techo), y el resultado medido: 537 líneas, 12 encabezados fechados apilados y
    # **cuatro** listas de próximos pasos, una de las cuales contradice un estado posterior del
    # mismo archivo. El daño no es cosmético: es el primer archivo que un agente lee al iniciar
    # sesión, y arranca por la lista equivocada.
    if cfg.STATUS.exists():
        try:
            _st = cfg.STATUS.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            _st = ""
        _pasos = re.findall(r"^#{1,4}\s+.*(?:pr[oó]ximos?\s+pasos?|lo que sigue).*$", _st,
                            re.M | re.I)
        _fechados = re.findall(r"^#{1,4}\s+.*\d{4}-\d{2}-\d{2}.*$", _st, re.M)
        if len(_pasos) > 1:
            status_apilado.append(
                ("STATUS.md", f"{len(_pasos)} secciones de próximos pasos ("
                              + " · ".join(p.strip()[:40] for p in _pasos[:4]) +
                              ") — el estado tiene UNA: las viejas contradicen a la vigente y el "
                              "agente arranca por la primera. Lo histórico va a `wiki/log.md`"))
        if len(_fechados) > STATUS_MAX_FECHADOS:
            status_apilado.append(
                ("STATUS.md", f"{len(_fechados)} encabezados fechados apilados (techo declarado: "
                              f"{STATUS_MAX_FECHADOS}) — eso es una bitácora, y la bitácora es "
                              f"`wiki/log.md`: el STATUS **se reescribe**, no se appendea"))
        if len(_st.splitlines()) > STATUS_MAX_LINEAS:
            status_apilado.append(
                ("STATUS.md", f"{len(_st.splitlines())} líneas (techo declarado: "
                              f"{STATUS_MAX_LINEAS}) — si es estado, no crece sin techo"))
    # #312 — `alcance`/`unidad_cita` viajan de `sources[]` al stub y se congelan ahí: ampliar el
    # alcance de un libro dejaba la nota **afirmando que ese material no entra mientras lo publica
    # en su vista** (medido: 2 libros, 37 valores nuevos). Y no deja al chequeo de completitud sin
    # información: lo deja con información FALSA, que es peor.
    if not cfg.themes_error():
        for _slug, _tmeta in (cfg.load_themes() or {}).items():
            for _item in cfg.as_list(cfg.as_map(_tmeta).get("sources")):
                if not isinstance(_item, dict) or not str(_item.get("key") or "").strip():
                    continue
                _key = str(_item["key"]).strip()
                _fm = paper_fms.get(_key)
                if _fm is None:
                    continue
                for _campo in ("alcance", "unidad_cita"):
                    _cfgv = str(_item.get(_campo) or "").strip()
                    _notav = str(_fm.get(_campo) or "").strip()
                    if _cfgv and _cfgv != _notav:
                        alcance_desfasado.append(
                            (_key, f"`{_campo}` de la nota («{_notav or 'sin declarar'}») ≠ el "
                                   f"declarado en `sources[]` de `{_slug}` («{_cfgv}») → el chequeo "
                                   f"de completitud compara contra el equivocado; "
                                   f"`python scripts/make_notes.py --restamp-alcance`"))

    # #311 — la extracción en `build/` es schema viejo: ese directorio es scratch por `.gitignore`,
    # así que ahí las extracciones NO viajan (medido: `git ls-files build/` = 0 sobre 33 extracciones
    # que costaron ~4,9 M tokens de lectura de PDF). Bloqueante y con migrador, como el
    # `triage.json` pre-1.9.0: un artefacto caro en un directorio declarado descartable es una
    # trampa puesta, no una convención.
    for _ext in sorted(cfg.ROOT.glob("build/*/extraccion/*.json"))[:1]:
        _n = len(list(cfg.ROOT.glob("build/*/extraccion/*.json")))
        old_registro.append(
            ("build/", f"{_n} extracción(es) en `build/*/extraccion/` (schema pre-#311): ahí NO se "
                       f"versionan ni viajan, y una extracción no se regenera sin volver a leer el "
                       f"PDF → `python scripts/make_notes.py --migrate-extracciones`"))
    _pasada_red = cfg.REGISTRO / "_red.yaml"
    if not _pasada_red.exists() and any(cfg.PAPERS.glob("*.md")):
        reuso_sin_chequear.append(
            ("(la bóveda)", "`vault/config/registro/_red.yaml` no existe: `sweep_external` nunca "
                            "corrió acá, así que NINGUNA de las seis caducidades está chequeada "
                            "(retracciones, correcciones, versiones, snapshot web, ground-truth, "
                            "citas de la puerta 2) → `python scripts/sweep_external.py`"))
    _por_stem: dict = {}
    for _pdf in cfg.PDFS.glob("*/*.pdf"):
        _por_stem.setdefault(_pdf.stem, []).append(_pdf.parent.name)
    for _stem, _slugs in sorted(_por_stem.items()):
        if len(_slugs) < 2:
            continue
        _fm = paper_fms.get(_stem)
        if not _fm or str(_fm.get("pdf_source") or "") != "eprint" or cfg.as_list(_fm.get("versions")):
            continue
        reuso_sin_chequear.append(
            (_stem, f"reusado entre slugs ({', '.join(sorted(_slugs))}) con `pdf_source: eprint` y "
                    f"sin `versions[]`: el artefacto entró a otro sujeto sin que nadie chequeara si "
                    f"salió publicado (D-18/#216) → `python scripts/sweep_external.py --bibcodes "
                    f"{_stem}`"))

    # Fulltext SIN nota de paper (#108). Hermano simétrico de la «cita no verificable» (bibcode
    # citado sin `.txt`) y del `ground_truth` sin ficha: acá el `.txt` **existe** y la nota no, así
    # que es extracción ya pagada —descarga, PDF, pdftotext— que **no la alcanza ningún roll-up ni
    # ninguna síntesis**, y ningún detector la miraba. Medido en una bóveda real: 10 de 30 `.txt`
    # de un tema quedaron así. El mecanismo es alcanzable sin salirse de lo documentado: al
    # **angostar la `query` de un tema**, sus registros salen de `build/<slug>/ads.json`,
    # `make_notes` deja de escribirles nota, y el PDF y el `.txt` quedan en disco. Es la misma
    # familia que INV-94 (paper sin entidad) un escalón más abajo: allá la nota existe y no la
    # alcanza nadie; acá ni siquiera hay nota. Backlog: el artefacto es válido, lo que falta es la
    # nota — o borrarlo si el sujeto ya no lo quiere.
    for _dir in sorted(cfg.FULLTEXT.glob("*")) if cfg.FULLTEXT.exists() else []:
        if not _dir.is_dir():
            continue
        for _txt in sorted(_dir.glob("*.txt")):
            if not (cfg.PAPERS / f"{_txt.stem.replace('/', '_')}.md").exists():
                incomplete.append(
                    (_txt.stem, f"`raw/fulltext/{_dir.name}/{_txt.stem}.txt` sin su nota en "
                                f"`papers/` → extracción ya pagada que no alcanza ninguna síntesis "
                                f"(típico: se angostó la `query` del tema y el registro salió de "
                                f"`ads.json`). Re-corré `make_notes.py --theme {_dir.name}` o "
                                f"borrá el artefacto colgado"))

    # #230 — el GEMELO PDF de #108, que no existía. El barrido de arriba mira sólo
    # `raw/fulltext/*/*.txt`: un `raw/pdfs/<slug>/<bib>.pdf` sin nota no lo veía **nadie** —el glob
    # de PDFs es sólo para el drift nota→archivo, y INV-19 mira directorios de primer nivel—. Es
    # exactamente el mismo defecto (descarga ya pagada que no alcanza ninguna síntesis) y desde
    # #205 pesa MÁS que su hermano, porque el PDF es la fuente de lectura y el `.txt` sólo el
    # índice: un PDF colgado es la mitad cara de la cadena tirada.
    for _dir in sorted(cfg.PDFS.glob("*")) if cfg.PDFS.exists() else []:
        if not _dir.is_dir():
            continue
        for _pdf in sorted(_dir.glob("*.pdf")):
            if not (cfg.PAPERS / f"{_pdf.stem.replace('/', '_')}.md").exists():
                incomplete.append(
                    (_pdf.stem, f"`raw/pdfs/{_dir.name}/{_pdf.stem}.pdf` sin su nota en `papers/` → "
                                f"descarga ya pagada que no alcanza ninguna síntesis, y desde #205 "
                                f"es la fuente de lectura, no el índice. Re-corré `make_notes.py` "
                                f"sobre `{_dir.name}` o borrá el artefacto colgado"))

    # #237 — el ÍNDICE desactualizado, análogo al detector de `## Papers` (D-10) y por el mismo
    # motivo: `index.md` es lo primero que un agente abre para orientarse y una de las cuatro piezas
    # de la memoria in-repo, y era el único artefacto que quedó 100 % Dataview — o sea que le muestra
    # al que abre el `.md` la query, no sus resultados, con el plugin sin versionar. Medido en una
    # bóveda real: los tres commits de su `index.md` son anteriores a la instanciación, y no tenía
    # cómo actualizarse (el paso de bookkeeping manda «agregar el concepto» a un archivo sin una
    # sola línea estática). Nombra los stems, no la diferencia de conteos.
    _idx = cfg.WIKI / "index.md"
    if _idx.exists():
        _txt_idx = _idx.read_text(encoding="utf-8")
        for _h, _cuerpo in mn.index_tables(fms=todos_fm).items():
            _span = cfg.section_span(_txt_idx, _h)
            _visto = set() if _span is None else set(
                lb.LINK_RE.findall(_txt_idx[_span[0]:_span[1]]))
            _esperado = set(lb.LINK_RE.findall(_cuerpo))
            _faltan, _sobran = sorted(_esperado - _visto), sorted(_visto - _esperado)
            if _faltan or _sobran:
                indice_viejo.append(
                    ("index", f"`{_h}` desactualizada"
                              + (f" — faltan: {', '.join(_faltan[:8])}" if _faltan else "")
                              + (f" — sobran: {', '.join(_sobran[:8])}" if _sobran else "")
                              + " → `python scripts/make_notes.py --restamp-index`"))

    # `sources:` sin procedencia (#111). Era el ÚNICO de los cuatro cuadrantes de curación sin
    # registro: `extra_core` dice quién y por qué desde D-58, el descarte de un candidato desde #51
    # y el de una fuente declarada desde #81 — pero una fuente off-ADS ACEPTADA no decía nada. Y es
    # el cuadrante que más lo necesita: en off-ADS **todo** entra por decisión de alguien (no hay
    # query que descubra), así que sin el campo la pregunta «¿qué entró porque lo pediste vos, qué
    # lo propuso el descubrimiento y qué salió de un reporte externo?» no tiene respuesta. Medido
    # sobre una bóveda real: los 40 papers que tenía y la nueva no entraron los 40 a mano, y no hay
    # forma de saber cuáles pidió el usuario. BLOQUEANTE, como la forma dura de `extra_core`: un
    # campo opcional no se llena. El snippet lo arma `triage.py --accept-source`.
    # `themes_error()` primero: con el YAML roto, `load_themes` levanta y tumbaría el lint entero —
    # el chequeo no puede volverse él mismo un falso rojo (misma doctrina que INV-80).
    # INV-27 — COLISIÓN de clave. Una clave sintética (`AAAA+Autor`) la elige una persona, y dos
    # trabajos del mismo autor y año la comparten sin esfuerzo. Toda la cadena resuelve el choque
    # por «el archivo ya existe, no lo piso», así que la segunda fuente se queda con el `.txt` y la
    # nota de la PRIMERA: la cita apunta a un documento que nadie abrió. `fetch_web` ya lo frena al
    # capturar (compara la url del snapshot en disco), pero eso sólo ve las que llegaron a bajarse y
    # sólo dentro de un slug — acá se ve la colisión **declarada**, incluso entre temas distintos y
    # antes de gastar red. La forma de la clave ya la valida `BIBCODE_RE`; lo que faltaba es la
    # unicidad, que es la otra mitad del invariante.
    _por_clave: dict = {}
    for _slug, _meta in ({} if cfg.themes_error() else (cfg.load_themes() or {})).items():
        for _it in cfg.as_list(cfg.as_map(_meta).get("sources")):
            if not isinstance(_it, dict) or not (_k := str(_it.get("key") or "").strip()):
                continue
            _punt = str(_it.get("url") or _it.get("pdf") or "").strip()
            _por_clave.setdefault(_k, []).append((_slug, _punt))
    for _k, _usos in sorted(_por_clave.items()):
        _punteros = {p for _s, p in _usos if p}
        if len(_punteros) > 1:
            bad_sources.append(
                (_k, f"la MISMA clave declara {len(_punteros)} fuentes distintas "
                     f"({'; '.join(f'{s}: {p}' for s, p in sorted(_usos))}) → las dos escriben "
                     f"`papers/{_k}.md` y comparten `.txt`: la segunda se queda con el documento de "
                     f"la primera y la cita apunta a algo que nadie abrió. Desambiguá con un sufijo "
                     f"(`{_k}b`)"))

    for _slug, _meta in ({} if cfg.themes_error() else (cfg.load_themes() or {})).items():
        # AUD-179 / INV-129 — `as_list` devuelve `[]` para un escalar Y para un mapa, así que un
        # `sources:` con forma inválida daba **cero hallazgos**: el bucle no entraba y el tema salía
        # limpio. Es el mismo modo de falla que `normalize_lists` cierra para el frontmatter (un
        # campo que el schema declara lista y llega escalar evade los chequeos por elemento), acá en
        # la config — y encima en el cuadrante donde TODO entra por decisión de alguien.
        _src = cfg.as_map(_meta).get("sources")
        if _src not in (None, [], "") and not isinstance(_src, list):
            bad_sources.append(
                (_slug, f"`sources:` no es una lista (es {type(_src).__name__}) → ninguna de sus "
                        f"entradas se chequea: tiene que ser una lista de mapas "
                        f"`- {{key, url|pdf, via, motivo}}`"))
            continue
        for _it in cfg.as_list(_src):
            if not isinstance(_it, dict):
                bad_sources.append(
                    (_slug, f"entrada de `sources:` que no es un mapa ({_it!r}) → evade los "
                            f"chequeos de procedencia; escribila como `- {{key: …, url: …, "
                            f"via: …, motivo: …}}`"))
                continue
            _falta = [k for k in ("via", "motivo") if not _it.get(k)]
            if _falta:
                bad_sources.append(
                    (f"{_slug}/{_it.get('key') or '?'}",
                     f"entrada de `sources:` sin {' ni '.join('`%s`' % k for k in _falta)} → no "
                     f"consta quién la declaró ni por qué (en off-ADS TODO entra por decisión de "
                     f"alguien). Armá la entrada con `python scripts/triage.py {_slug} "
                     f"--accept-source <doi> --via usuario --reason \"<motivo>\"`"))
            elif (_v := _it.get("via")) in VIA_FUENTE_RETIRADO:
                # #206: valor retirado, no typo. `reporte` y `usuario` eran la misma decisión —el
                # usuario trajo el paper— y partirla hacía que `via` dejara de contestar su propia
                # pregunta: había que sumar dos casilleros para saber cuántos entraron por decisión
                # humana. El documento de origen lo lleva `motivo`, que es obligatorio y dice CUÁL.
                bad_sources.append(
                    (f"{_slug}/{_it.get('key') or '?'}",
                     f"`via: {_v}` es vocabulario RETIRADO (#206) — usá {VIA_FUENTE_RETIRADO[_v]}"))
            elif _v not in VIA_FUENTE_OK:
                bad_sources.append(
                    (f"{_slug}/{_it.get('key') or '?'}",
                     f"`via: {_v}` fuera del vocabulario cerrado "
                     f"({' | '.join(sorted(VIA_FUENTE_OK))}) — un typo deja el campo mudo para la "
                     f"única pregunta que existe para consumirlo"))

    # categorías que NO se pudieron evaluar: se omiten del reporte en vez de mostrar un "(0)" que
    # se leería como veredicto (el adversario que D-43 nombra: el cero inventado).
    suprimidas = set()
    if not stale_evaluable:
        suprimidas.add("Verificación stale")
    # Una categoría que se calcula a partir de una config ILEGIBLE no vale 0: nadie la midió. Antes
    # sólo se suprimía "Verificación stale", así que con `stars.yaml` roto cinco categorías seguían
    # imprimiendo su cero — cinco veredictos inventados sobre datos que el lint no pudo leer, que es
    # exactamente lo que la categoría *No evaluado* existe para no producir (INV-87). Peor con
    # `objective.yaml`: *Áreas de concepts/* afirmaba "no declara `concept_areas`" sobre un archivo
    # que sí la declara.
    if cfg.stars_error() or cfg.themes_error():
        suprimidas |= {"Triage pendiente", "Recorte de lectura sin declarar",
                       "Lista de papers desactualizada", "Cadena incompleta", "Corpus truncado",
                       "Capas colgadas"}
    if cfg.objective_error():
        suprimidas |= {"Objetivo sin instanciar", "Áreas de `concepts/` no declaradas",
                       "Áreas de concepts", "Lente desincronizada"}


    # ── la tabla: clave, título, severidad, hallazgos. **Una sola declaración** de cada cosa.
    # #236 — un token alfabético corto SIN `\b` en una faceta matchea DENTRO de otra palabra.
    # Medido: `expres` (por el espectrógrafo EXPRES) entraba por «Venus Express», «Mars Express» y
    # «expressed», y `neid` por el apellido «Schneider»; 19 de 193 registros tenían esa faceta sólo
    # por ahí, y como la bóveda declaraba `require: [rv]` eso la volvía la única puerta: **4 de 32
    # papers vivos eran core por accidente**. El falso positivo de una faceta NO DEJA RASTRO —el
    # paper entra, se baja, se lee y se sintetiza—, así que sólo se ve corriendo la regex contra el
    # corpus y mirando QUÉ matcheó. Con `build/<slug>/ads.json` a mano se nombran las palabras.
    if not cfg.objective_error():
        _textos = []
        for _aj in sorted(glob.glob(str(cfg.ROOT / "build" / "*" / "ads.json"))):
            try:
                for _r in (json.load(open(_aj, encoding="utf-8")) or {}).get("records", []):
                    _t = _r.get("title")
                    _textos.append(" ".join([_t if isinstance(_t, str) else " ".join(_t or []),
                                             _r.get("abstract") or ""]))
            except (OSError, ValueError):
                continue
        for _nombre, _pat in (cfg.load_objective().get("relevance", {}).get("facets", {}) or {}).items():
            for _tok in cfg.facet_tokens_without_boundary(_pat):
                _leaks = cfg.facet_token_leaks(_tok, _textos) if _textos else []
                _ev = (" — matchea dentro de " + ", ".join(f"«{w}»" for w in _leaks)) if _leaks else \
                      " (sin corpus en `build/` para medir dentro de qué palabras cae)"
                faceta_sin_frontera.append(
                    (str(_nombre), f"el token `{_tok}` no lleva `\\b` y matchea DENTRO de otra "
                                   f"palabra{_ev} → escribilo `\\b{_tok}\\b`"))

    # #291 — la dirección SIMÉTRICA de #236: la alternativa que no matchea nada. Una alternativa
    # muerta no se ve nunca —la faceta compila, el corte da un número plausible, el registro guarda
    # la lente como vigente— y el término simplemente no participa, indistinguible de «ese término
    # no aparece en la literatura». Medido: `non-?gaussianity matrix` (un `|` perdido) exigía una
    # frase que 0 archivos tienen, mientras 29 tienen `non-gaussianity`: el tema clasificaba por su
    # vocabulario MENOS su término central. Se corre contra el texto que lee la LENTE (título +
    # abstract + keywords de las notas), no contra el fulltext, para que el veredicto sea el de la
    # lente. Backlog, nunca bloqueante: una alternativa puede ser legítimamente rara, o estar
    # puesta para lo que todavía no se ingestó.
    if not cfg.themes_error():
        for _slug, _tmeta in (cfg.load_themes() or {}).items():
            _facet = cfg.as_map(_tmeta).get("facet")
            if not _facet:
                continue
            _stems = {st for st, _f, _t in cfg.notes_of_subject(_slug)}
            _textos = [paper_lens_text[st] for st in sorted(_stems) if st in paper_lens_text]
            for _alt in cfg.facet_duplicated_alternatives(str(_facet)):
                faceta_muerta.append((f"tema `{_slug}`",
                                      f"alternativa DUPLICADA `{_alt}` — inofensiva, pero es la "
                                      f"señal barata de que la cadena se editó a mano y a ciegas"))
            if not _textos:
                # D-43 — sobre un tema recién declarado el chequeo NO es evaluable, y decir «todas
                # muertas» sería el veredicto inventado que esta categoría existe para no producir.
                faceta_muerta.append((f"tema `{_slug}`",
                                      "no evaluable: el tema todavía no tiene notas de paper "
                                      "(población 0) — no es que sus alternativas estén muertas"))
                continue
            for _alt, _motivo in cfg.facet_dead_alternatives(str(_facet), _textos):
                faceta_muerta.append((f"tema `{_slug}`",
                                      f"alternativa `{_alt}`: {_motivo} (sobre {len(_textos)} "
                                      f"notas del tema) → ¿un `|` perdido, o un término que "
                                      f"todavía no se ingestó?"))
    if not cfg.objective_error():
        _todos = [paper_lens_text[st] for st in sorted(paper_lens_text)]
        for _nombre, _pat in (cfg.load_objective().get("relevance", {}).get("facets", {}) or {}).items():
            for _alt in cfg.facet_duplicated_alternatives(str(_pat)):
                faceta_muerta.append((f"faceta `{_nombre}`", f"alternativa DUPLICADA `{_alt}`"))
            if not _todos:
                faceta_muerta.append((f"faceta `{_nombre}`",
                                      "no evaluable: la bóveda no tiene notas de paper (población 0)"))
                continue
            for _alt, _motivo in cfg.facet_dead_alternatives(str(_pat), _todos):
                faceta_muerta.append((f"faceta `{_nombre}`",
                                      f"alternativa `{_alt}`: {_motivo} (sobre {len(_todos)} "
                                      f"notas de paper)"))

    categorias = [
        Categoria('not_evaluated', '⛔ No evaluado: el chequeo no pudo correr (hecho del ENTORNO, no de la bóveda — cuenta para el exit)', SEV_BLOQUEANTE, tuple(not_evaluated)),
        Categoria('broken', 'Wikilinks rotos (página faltante)', SEV_BLOQUEANTE, tuple(broken), poblacion='notas'),
        Categoria('fm_broken', '⛔ Frontmatter no parseable o con forma inválida (la nota evade los chequeos de su tipo)', SEV_BLOQUEANTE, tuple(fm_broken), poblacion='notas'),
        Categoria('retracted', '⛔ Papers RETRACTADOS citados (frontera dura: fuente no válida)', SEV_BLOQUEANTE, tuple(retracted), poblacion='papers'),
        Categoria('gt_cambiado', 'Ground-truth que cambió bajo la prosa, sin marcar (backlog)', SEV_BACKLOG, tuple(gt_cambiado), poblacion='ground_truth'),
        Categoria('gt_cambiado_marcado', f'Ground-truth cambiado, prosa marcada con `{GT_STALE_MARK}` (visible, no destruida)', SEV_BACKLOG, tuple(gt_cambiado_marcado), poblacion='ground_truth'),
        Categoria('prosa_retractada', '⛔ Prosa que cita una fuente RETRACTADA sin marcar', SEV_BLOQUEANTE, tuple(prosa_retractada), poblacion='entidades'),
        Categoria('prosa_retractada_marcada', 'Prosa sostenida por fuente retractada, marcada (visible, no destruida)', SEV_BACKLOG, tuple(prosa_retractada_marcada), poblacion='entidades'),
        Categoria('orphans', 'Notas huérfanas (sin links entrantes)', SEV_BLOQUEANTE, tuple([(o, '') for o in orphans]), poblacion='notas'),
        Categoria('corrections', 'Papers con corrección publicada (erratum/corrigendum/EoC) — revisar los valores extraídos de ellos (backlog, el paper sigue siendo citable)', SEV_BACKLOG, tuple(corrections), poblacion='notas'),
        Categoria('contradictions', 'Contradicciones ground-truth ↔ ficha', SEV_BLOQUEANTE, tuple(contradictions), poblacion='papers'),
        Categoria('mass_issues', 'Ground-truth: masa inconsistente con m·sini (K,P,e,M*)', SEV_BLOQUEANTE, tuple(mass_issues), poblacion='ground_truth'),
        Categoria('contrast_missing', 'Contraste cross-paper (3b) sin rastro: el inventario por eje quedó en la plantilla (backlog)',
                  SEV_BACKLOG, tuple(contraste_pendiente), poblacion='entidades'),
        Categoria('alias_faltante', 'Identificadores que SIMBAD conoce y `stars.yaml` no declara: '
                  'un alias que falta es un paper que nunca aparece, en silencio (backlog — la '
                  'elección es curación)', SEV_BACKLOG, tuple(alias_faltantes), poblacion='ground_truth'),
        Categoria('alias_rechazado', 'Identificador de SIMBAD DECLARADO como no-alias con motivo '
                  '(#252: visible, no es deuda)', SEV_BACKLOG, tuple(alias_rechazados), poblacion='ground_truth'),
        Categoria('foreign_alias', '⚠ Alias que SIMBAD no reconoce para esta estrella (WARN — puede meter papers de otro objeto)',
                  SEV_WARN, tuple(alias_ajenos), poblacion='ground_truth'),
        Categoria('merge_ours', '⛔ `merge=ours` declarado pero sin driver registrado en este clon: la protección no existe',
                  SEV_BLOQUEANTE, tuple(merge_ours), poblacion='ground_truth'),
        Categoria('dangling_thesis', 'thesis_links sin página destino', SEV_BLOQUEANTE, tuple(dangling_thesis), poblacion='entidades'),
        Categoria('dangling_methods', '`methods` sin página destino: el roll-up no puede linkearlo (backlog)',
                  SEV_BACKLOG, tuple(dangling_methods), poblacion='entidades'),
        Categoria('indicador_sin_destino', '🌡 Indicador de actividad esperado sin nota de concepto: la ficha lo nombra y el lector no puede llegar (#250, backlog)',
                  SEV_BACKLOG, tuple(indicador_sin_destino), poblacion='entidades'),
        Categoria('alias_colision', '🔤 Dos conceptos declaran el mismo alias: el roll-up resuelve al primero y nadie lo decidió (#245, backlog)',
                  SEV_BACKLOG, tuple(alias_colision), poblacion='entidades'),
        Categoria('methods_colision', '🔤 `methods` con varias grafías del mismo método: infla el backlog y partía el roll-up (#243, backlog)',
                  SEV_BACKLOG, tuple(methods_colision), poblacion='papers'),
        Categoria('dangling_disputes', 'disputes: ref de una posición sin paper destino', SEV_BLOQUEANTE, tuple(dangling_disputes), poblacion='entidades'),
        Categoria('bad_disputes', 'disputes mal formadas (posiciones explícitas, #71)', SEV_BLOQUEANTE, tuple(bad_disputes), poblacion='entidades'),
        Categoria('old_disputes', 'disputes en el schema viejo (planets[].disputes[]) — el lint ya no las lee', SEV_BLOQUEANTE, tuple(old_disputes), poblacion='entidades'),
        Categoria('legacy_triage', 'Juicio de triage en build/<slug>/triage.json (pre-1.9.0) — el lector ya no lo mira', SEV_BLOQUEANTE, tuple(legacy_triage), poblacion='registros'),
        Categoria('old_registro', '⛔ Registro con `busqueda:` (schema viejo pre-D-28) — el lector ya no lo lee', SEV_BLOQUEANTE, tuple(old_registro), poblacion='registros'),
        Categoria('registro_ilegible', '⛔ Registro del sujeto ilegible — la curación (`decisiones`) queda SIN APLICAR: los descartes vuelven a ser core', SEV_BLOQUEANTE, tuple(registro_ilegible), poblacion='registros'),
        Categoria('old_facets', '⛔ Nota de paper con `topics:` (schema viejo pre-R-5) — el campo vigente es `facets:`', SEV_BLOQUEANTE, tuple(old_facets), poblacion='papers'),
        Categoria('infer_sin_premisas', '⛔ `inferencia` sin premisas (D-42): la marca no nombra ningún `[[bibcode]]`', SEV_BLOQUEANTE, tuple(infer_sin_premisas), poblacion='notas'),
        Categoria('bad_status', '⛔ `status` de hipótesis fuera del vocabulario cerrado (D-37)', SEV_BLOQUEANTE, tuple(bad_status), poblacion='entidades'),
        Categoria('status_vs_evidencia', '`status: sostenida` contra su propia tabla de evidencia (D-37, #177)', SEV_BACKLOG, tuple(status_vs_evidencia), poblacion='entidades'),
        Categoria('old_bearing', '⛔ `bearing` en una nota de paper (schema pre-D-21) — la postura vive en la hipótesis', SEV_BLOQUEANTE, tuple(old_bearing), poblacion='papers'),
        Categoria('sin_destino', '⛔ Nota de paper sin destino (D-23): no pertenece a ninguna entidad', SEV_BLOQUEANTE, tuple(sin_destino), poblacion='papers'),
        Categoria('identidad_dup', '⛔ Identidad duplicada: dos notas del mismo trabajo (mismo doi/arxiv_id)', SEV_BLOQUEANTE, tuple(identidad_dup), poblacion='papers'),
        Categoria('alias_con_nota', '⛔ Bibcode listado en `versions[]` que TIENE su propia nota: apaga los dos chequeos de identidad (#229)', SEV_BLOQUEANTE, tuple(alias_con_nota), poblacion='papers'),
        Categoria('abstract_dup', '👯 Posible duplicado SIN doi ni arxiv_id: mismo abstract verbatim (backlog — decidís vos)', SEV_BACKLOG, tuple(abstract_dup), poblacion='papers'),
        Categoria('bad_sources', '⛔ `sources:` sin procedencia (#111): no consta quién declaró la fuente ni por qué', SEV_BLOQUEANTE, tuple(bad_sources), poblacion='temas'),
        Categoria('bad_roles', '⛔ `role` fuera del vocabulario — y todo campo con vocabulario CERRADO (`unidad_cita`, `pending_source`)', SEV_BLOQUEANTE, tuple(bad_roles), poblacion='papers'),
        Categoria('impl_leaks', '⚠ Fuga de implementación (código no bibliográfico) → frontera dura (WARN, revisar a mano)', SEV_WARN, tuple(impl_leaks), poblacion='notas'),
        Categoria('cond_sin_clasificar', '⚖ Condición sin clasificar: no dice si acota la afirmación o sólo la contextualiza (#221, backlog)', SEV_BACKLOG, tuple(cond_sin_clasificar), poblacion='entidades'),
        Categoria('verif_estructura', '🧾 Bloque de verificación incompleto: faltan sub-secciones o la cabecera no cuadra (#232, backlog)', SEV_BACKLOG, tuple(verif_estructura), poblacion='entidades'),
        Categoria('verif_truncada', '✂ Celda del bloque de verificación truncada: se tiró lo que el fan-out encontró (#226, backlog)', SEV_BACKLOG, tuple(verif_truncada), poblacion='entidades'),
        Categoria('verif_sin_localizador', '✂ Evidencia sin localizador: el cruce de #122 NO se pudo evaluar en esa fila (#226, backlog)', SEV_BACKLOG, tuple(verif_sin_localizador), poblacion='entidades'),
        Categoria('indice_viejo', '🗂 `index.md` desactualizado contra la verdad de disco (#237, backlog)', SEV_BACKLOG, tuple(indice_viejo), poblacion='notas'),
        Categoria('radio_sin_link', '🛞 Hub que nombra un radio sin `[[wikilink]]`: el radio no entra al grafo (#235, backlog)', SEV_BACKLOG, tuple(radio_sin_link), poblacion='entidades'),
        Categoria('cita_log', '❝ Cita de `log.md` que su fuente no dice: la bitácora es append-only, se MARCA (#238, backlog)', SEV_BACKLOG, tuple(cita_log), poblacion='notas'),
        Categoria('cita_inventada', '❝ Cita textual que NO está ni en el `.txt` ni en la EXTRACCIÓN: la fabricó el sintetizador (#318, BLOQUEA con `--cierre`)', SEV_CIERRE, tuple(cita_inventada), poblacion='citas'),
        Categoria('cita_no_verbatim', '❝ Cita textual que no está en su fuente: no es verbatim, o es de otra (#220, backlog)', SEV_BACKLOG, tuple(cita_no_verbatim), poblacion='citas'),
        Categoria('cita_txt_degradado', '❝ Cita que la fuente SÍ dice y el `.txt` parte: el defecto es de la EXTRACCIÓN, no de la nota (#288, backlog)', SEV_BACKLOG, tuple(cita_txt_degradado), poblacion='citas'),
        Categoria('cita_opaca', '❝ Cita textual NO EVALUABLE: sin `.txt` o con OCR (#220, se declara, no cuenta en contra)', SEV_BACKLOG, tuple(cita_opaca), poblacion='citas'),
        Categoria('verificar_pdf', '🔎 Marcada para chequear contra el PDF: una auditoría no pudo cerrarla (#225, backlog)', SEV_BACKLOG, tuple(verificar_pdf), poblacion='notas'),
        Categoria('forma_rota', '⛔ Forma del artefacto: fila de tabla que NO renderiza (contenido invisible para el lector)', SEV_BLOQUEANTE, tuple(forma_rota), poblacion='notas'),
        Categoria('forma_sospechosa', '⚠ Forma del artefacto: marcador sin cerrar o párrafo duplicado (backlog)', SEV_BACKLOG, tuple(forma_sospechosa), poblacion='notas'),
        Categoria('objective_warn', 'Objetivo sin instanciar (WARN — objective.yaml sigue en el placeholder del template)', SEV_WARN, tuple(objective_warn), poblacion='config'),
        Categoria('lente_rota', '⛔ Lente vacía o incoherente: ningún paper puede ser core', SEV_BLOQUEANTE, tuple(lente_rota), poblacion='config'),
        Categoria('undeclared_areas', 'Áreas de concepts/ no declaradas en objective.yaml (WARN, posible typo)', SEV_WARN, tuple(undeclared_areas), poblacion='notas'),
        Categoria('root_obsidian', 'Obsidian en la raíz del repo (WARN — la bóveda se abre en vault/)', SEV_WARN, tuple(root_obsidian), poblacion='config'),
        Categoria('pdf_issues', 'PDF ↔ disco / cuerpo (WARN — higiene: frontmatter `pdf` vs PDF bajado vs link de cabecera)', SEV_WARN, tuple(pdf_issues), poblacion='papers'),
        Categoria('pending_srcs', '⏳ Fuentes pendientes (pending_source — el usuario debe proveer la fuente)', SEV_BACKLOG, tuple(pending_srcs), poblacion='papers'),
        Categoria('campos_txt_viejos', '⛔ Notas con `symbols_lost`/`fulltext_layout` (schema pre-#205 sin lector — migrar)', SEV_BLOQUEANTE, tuple(campos_txt_viejos), poblacion='papers'),
        Categoria('log_sin_entrada', '📓 Operación sin entrada en `log.md` (la cadena corrió y la bitácora no lo dice)', SEV_BACKLOG, tuple(log_sin_entrada), poblacion='registros'),
        Categoria('illegible_txt', 'Fulltext ilegible (mojibake/escaneo — existe pero no sirve para grep/verify)', SEV_BACKLOG, tuple(illegible_txt), poblacion='fulltext'),
        Categoria('divergent_txt', '⛔ Mismo bibcode con `.txt` DISTINTO entre slugs: las copias de '
                  'D-18 divergieron y el ancla de fuente (D-20) vigila una sola', SEV_BLOQUEANTE,
                  tuple(divergent_txt), poblacion='fulltext'),
        Categoria('unverifiable', 'Citas no verificables en ficha/query/concepto/hipótesis (sin fulltext)', SEV_BACKLOG, tuple(unverifiable), poblacion='entidades'),
        Categoria('unverified', 'Sin verificar: nota con citas y sin bloque verify-citations'
                  + (' (BLOQUEA: modo --cierre)' if cierre else ' (backlog: pasada periódica; con `--cierre` bloquea)'), SEV_CIERRE, tuple(unverified), poblacion='entidades'),
        Categoria('old_verif_template', '⛔ Bloque de verificación con plantilla vieja (sin columnas de hash — no evaluable)', SEV_BLOQUEANTE, tuple(old_verif_template), poblacion='entidades'),
        Categoria('verif_sin_archivo', '⛔ Fila de verificación que no declara contra qué archivo se '
                  'verificó (#117): el hash no se puede comparar', SEV_BLOQUEANTE,
                  tuple(verif_sin_archivo), poblacion='entidades'),
        Categoria('verif_sin_resolver', '⛔ Veredicto de verificación SIN RESOLVER (`no-soportada` / '
                  '`contradice`): la nota afirma algo que su fuente no respalda', SEV_BLOQUEANTE,
                  tuple(verif_sin_resolver), poblacion='entidades'),
        Categoria('verif_localizador', 'Localizador que contradice al archivo vigilado: la evidencia '
                  'cita una página y la fila vigila el `.txt` (o al revés) (backlog)',
                  SEV_BACKLOG, tuple(verif_localizador), poblacion='entidades'),
        Categoria('stale_pairs', 'Pares de verificación vencidos' + (' (BLOQUEA: modo --cierre)' if cierre else ' (backlog: pasada periódica; con `--cierre` bloquea)'), SEV_CIERRE, tuple(stale_pairs), poblacion='entidades'),
        Categoria('stale_verif', 'Verificación stale: la nota se editó después de su último verify-citations (backlog)', SEV_BACKLOG, tuple(stale_verif), poblacion='entidades'),
        Categoria('artefactos_colgados', 'Capas colgadas: registro/raw/build de una entidad que ya no existe (INV-19, backlog)', SEV_BACKLOG, tuple(artefactos_colgados), poblacion='registros'),
        Categoria('alcance_corto', 'Alcance de hipótesis sin declarar o vencido: el veredicto se lee sobre un universo que ya no es el suyo (backlog)', SEV_BACKLOG, tuple(alcance_corto), poblacion='entidades'),
        Categoria('coverage', 'Cobertura: concepto/hipótesis sin citas [[bibcode]] (backlog)', SEV_BACKLOG, tuple(coverage), poblacion='entidades'),
        Categoria('unsynthesized', 'Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog)', SEV_BACKLOG, tuple(unsynthesized), poblacion='papers'),
        Categoria('headerless', 'Cabecera no estampable: ficha/concepto sin la línea del generador — los estampadores de cabecera no-opean en silencio (backlog)', SEV_BACKLOG, tuple(headerless), poblacion='entidades'),
        Categoria('sin_abstract', '⛔ Nota de paper sin `## Abstract`: se pierde la única capa AUDITABLE del cuerpo (#124/#277)', SEV_BLOQUEANTE, tuple(sin_abstract), poblacion='papers'),
        Categoria('sin_conclusiones', '📄 Nota de paper sin `## Conclusiones` ni exención declarada (#124/#277, backlog)', SEV_BACKLOG, tuple(sin_conclusiones), poblacion='papers'),
        Categoria('sin_aviso_llm', '⚠ Nota de paper sin el aviso de capa LLM: no dice cuál de sus tres capas es auditable (#247/#277, backlog)', SEV_BACKLOG, tuple(sin_aviso_llm), poblacion='papers'),
        Categoria('estado_desfasado', '🗓 Cabecera `> _Estado —_` desfasada: no es la que el estampador da hoy (backlog)', SEV_BACKLOG, tuple(estado_desfasado), poblacion='entidades'),
        Categoria('salv_sin_marca', '🏷 Salvedades sin la marca de #213 (no se distingue chequeada de juicio) (backlog)', SEV_BACKLOG, tuple(salv_sin_marca), poblacion='papers'),
        Categoria('salv_decidible', '⚙ Salvedad en prosa que un script podría decidir: emitila estructurada (#234, backlog)', SEV_BACKLOG, tuple(salv_decidible), poblacion='papers'),
        Categoria('faceta_sin_frontera', '🕳 Faceta con token corto sin `\\b`: matchea DENTRO de otra palabra (#236, backlog)', SEV_BACKLOG, tuple(faceta_sin_frontera), poblacion='config'),
        Categoria('faceta_muerta', '🕳 Alternativa de faceta con POBLACIÓN CERO o duplicada (#291, backlog)', SEV_BACKLOG, tuple(faceta_muerta), poblacion='config'),
        Categoria('reuso_sin_chequear', '🕳 Artefacto reusado entre slugs sin chequear su versión, y pasada de red que nunca corrió (#297, backlog)', SEV_BACKLOG, tuple(reuso_sin_chequear), poblacion='papers'),
        Categoria('version_publicada', '🕳 La nota se apoya en el PREPRINT habiendo versión publicada (#298, backlog)', SEV_BACKLOG, tuple(version_publicada), poblacion='papers'),
        Categoria('status_apilado', '🕳 `STATUS.md` apilado como bitácora: es ESTADO, se reescribe (#302, backlog)', SEV_BACKLOG, tuple(status_apilado), poblacion='config'),
        Categoria('alcance_desfasado', '🕳 `alcance`/`unidad_cita` de la nota ≠ el declarado en `sources[]` (#312, backlog)', SEV_BACKLOG, tuple(alcance_desfasado), poblacion='papers'),
        Categoria('sweep_pendiente', 'Barrido full-text (2b) sin rastro o truncado: no consta que la '
                  'segunda red para el punto ciego de la query se haya tendido entera (backlog)',
                  SEV_BACKLOG, tuple(sweep_pendiente), poblacion='registros'),
        Categoria('triage_pending', 'Triage pendiente: candidatos del chaining sin juzgar (backlog)', SEV_BACKLOG, tuple(triage_pending), poblacion='registros'),
        Categoria('vistas_schema_viejo', '⛔ Extracción sin declarar la LENTE: `## Extracción (LLM)` sin `vistas[]` (schema viejo, #188)', SEV_BLOQUEANTE, tuple(vistas_schema_viejo), poblacion='papers'),
        Categoria('vistas_vs_cuerpo', '⛔ `vistas[]` ↔ cuerpo: vista declarada sin su sección, o sección sin declarar', SEV_BLOQUEANTE, tuple(vistas_vs_cuerpo), poblacion='papers'),
        Categoria('reclamo_sin_vista', 'Reclamado por un sujeto y nunca leído desde ahí (backlog: la vista es opcional, el silencio no)', SEV_BACKLOG, tuple(reclamo_sin_vista), poblacion='papers'),
        Categoria('vista_sin_fecha', 'Vista declarada y sin `fecha`: el stub la sembró y nadie leyó desde ahí (backlog)', SEV_BACKLOG, tuple(vista_sin_fecha), poblacion='papers'),
        Categoria('vista_sin_fuente', 'Vista sin `fuente`: no consta si salió del PDF o sólo del abstract (backlog)', SEV_BACKLOG, tuple(vista_sin_fuente), poblacion='papers'),
        Categoria('vista_solo_abstract', '📄 Vista construida SÓLO del abstract — falta el PDF (backlog)', SEV_BACKLOG, tuple(vista_solo_abstract), poblacion='papers'),
        Categoria('vista_sin_fuente_en_disco', '🔒 Vista fechada SIN fuente en disco: ya no es re-verificable (backlog)', SEV_BACKLOG, tuple(vista_sin_fuente_en_disco), poblacion='papers'),
        Categoria('reclamo_refutado', '↩ La vista REFUTA un reclamo que sigue en el frontmatter (backlog)', SEV_BACKLOG, tuple(reclamo_refutado), poblacion='papers'),
        Categoria('reclamo_sin_vista_declarado', 'Reclamo sin vista DECLARADO con `no_vista` + motivo (visible, no es deuda)', SEV_BACKLOG, tuple(reclamo_sin_vista_declarado), poblacion='papers'),
        Categoria('vista_ejes_faltantes', '🎯 La vista no contesta los ejes de su propia lente: el silencio se lee como «se miró y no hay nada» (#254/#270, backlog)', SEV_BACKLOG, tuple(vista_ejes_faltantes), poblacion='papers'),
        Categoria('gt_prosa', '🪞 La prosa afirma sobre la autoridad algo que su ground-truth desmiente (#278, backlog)', SEV_BACKLOG, tuple(gt_prosa), poblacion='ground_truth'),
        Categoria('segunda_mano', '🔁 Valor de SEGUNDA MANO levantado sin la marca: la atribución se pierde en la síntesis (#103/#279, backlog)', SEV_BACKLOG, tuple(segunda_mano_perdida), poblacion='entidades'),
        Categoria('sin_conclusiones_ok', 'Fuente sin `## Conclusiones` DECLARADA con motivo (#277: visible, no es deuda)', SEV_BACKLOG, tuple(sin_conclusiones_ok), poblacion='papers'),
        Categoria('extraccion_no_declarada', 'Recorte de lectura sin declarar: hay core sin extraer y el registro no dice por qué (backlog)', SEV_BACKLOG, tuple(extraccion_no_declarada), poblacion='registros'),
        Categoria('papers_table_stale', 'Lista de papers desactualizada: la tabla estampada no refleja el universo (backlog)', SEV_BACKLOG, tuple(papers_table_stale), poblacion='registros'),
        Categoria('cadena_incompleta', 'Cadena incompleta: falta un paso del orden canónico (backlog)', SEV_BACKLOG, tuple(cadena_incompleta), poblacion='estrellas'),
        Categoria('truncated_corpora', 'Corpus truncado: la query directa trajo menos de lo que ADS reporta (backlog)', SEV_BACKLOG, tuple(truncated_corpora), poblacion='registros'),
        Categoria('lente_desync', 'Lente desincronizada: el corpus se clasificó con una regla que ya no es la vigente (backlog)', SEV_BACKLOG, tuple(lente_desync), poblacion='registros'),
        Categoria('bad_decisions', 'Decisión del registro con forma inválida — load_decisiones la descarta en silencio, el triage la vuelve a proponer sin el motivo (backlog)', SEV_BACKLOG, tuple(bad_decisions), poblacion='registros'),
        Categoria('schema_incompleto', 'Nota sin campos del schema de su tipo (INV-63: el campo ausente no se lee igual que el vacío)', SEV_BACKLOG, tuple(schema_incompleto), poblacion='notas'),
        Categoria('incomplete', 'Campos incompletos', SEV_BACKLOG, tuple(incomplete)),
    ]
    for i, c in enumerate(categorias):
        if any(c.titulo.startswith(s) for s in suprimidas):
            categorias[i] = replace(c, suprimida=True)
    # INV-40 — los denominadores, contados sobre lo que el barrido realmente miró (no re-derivados
    # después, que es donde una población se despega del chequeo que dice describir).
    poblaciones = {
        "notas": (len(files), "notas de `vault/wiki/`"),
        "papers": (len(paper_fms), "notas de `papers/`"),
        "entidades": (len(anchor_bodies), "notas de entidad (fichas, conceptos, queries)"),
        "fulltext": (len(fulltext_files), "`.txt` de `raw/fulltext/`"),
        "ground_truth": (len(vistos_gt), "ground-truth de `raw/ground_truth/`"),
        # #297 — `_red.yaml` es de la bóveda entera (D-46), no de un sujeto: contarlo infla el
        # denominador de las siete categorías que declaran esta población, y un denominador que
        # incluye lo que el barrido no mira es exactamente lo que INV-40 existe para evitar.
        "registros": (len([f for f in cfg.REGISTRO.glob("*.yaml") if not f.name.startswith("_")])
                      if cfg.REGISTRO.exists() else 0, "registros de sujeto"),
        "citas": (_n_citas_evaluadas[0], "citas «…» de ≥40 caracteres con fuente chequeable"),
        "temas": (0 if cfg.themes_error() else len(cfg.load_themes() or {}), "temas de `themes.yaml`"),
        "estrellas": (len(stars_slugs), "estrellas de `stars.yaml`"),
        # Los chequeos de config miran UN archivo cada uno (el objetivo, el `.obsidian/` de la
        # raíz): la población es 1 y decirlo es más honesto que dejarla sin declarar — «miré el
        # único que hay» no es lo mismo que «no sé sobre qué miré».
        "config": (1, "archivo de configuración"),
    }
    return LintResult(tuple(categorias), cierre=cierre, slug=alcance_slug, alcance=alcance,
                      poblaciones=poblaciones)


def render(res: LintResult) -> str:
    """El reporte markdown. Separado de `collect` para que el golden mida **comportamiento** y no
    formato, y para que un consumidor no tenga que parsear texto para saber qué encontró el lint.

    Con `--cierre <slug>` (#121) el reporte NO se recorta: la deuda ajena se sigue listando entera
    y sólo se marca cuál cuenta para el exit. Acotar el reporte haría invisible lo de al lado, que
    es el modo de falla obvio de la idea."""
    lines = [f"# Lint de la bóveda — {dt.date.today().isoformat()}", ""]
    if res.slug is not None:
        lines += [f"> **Alcance del exit: `{res.slug}`** ({len(res.alcance)} nota(s): su "
                  f"ficha/concepto y sus papers). El barrido es de la bóveda entera y todo lo de "
                  f"abajo se reporta igual; lo ajeno al sujeto está marcado y **no frena** esta "
                  f"operación. Los bloqueantes cuentan siempre, vengan de donde vengan.", ""]
    for c in res.categorias:
        if c.suprimida:
            continue
        en_alcance = res.en_alcance(c)
        acotada = res.slug is not None and c.severidad == SEV_CIERRE
        cuenta = f"{len(c)}" + (f"; {len(en_alcance)} de `{res.slug}`" if acotada else "")
        # INV-40 — el denominador. Un `(0)` no dice si el chequeo miró 412 notas o ninguna, así que
        # «el chequeo cubrió todo lo que dice cubrir» no se podía verificar desde la salida. Lo que
        # no está declarado se DICE, no se inventa.
        lines.append(f"## {c.titulo} ({cuenta})")
        # ⚠ El denominador va en su PROPIA línea, debajo del encabezado. El encabezado es un
        # contrato de facto: el golden, una treintena de tests y cualquier consumidor lo leen como
        # `"<título> (N)"` —con `rsplit("(", 1)[1].rstrip(")")`— así que meter texto adentro o
        # después lo rompe. Es formato, no comportamiento, y no hay razón para pagarlo.
        _pob = res.poblaciones.get(c.poblacion) if c.poblacion else None
        lines.append(f"> sobre {_pob[0]} {_pob[1]}" if _pob
                     else "> ⚠ población no declarada")
        for it in c.items:
            a, b = it
            ajeno = " — ⟨ajeno a `%s`: se reporta, no frena⟩" % res.slug if acotada and it not in en_alcance else ""
            lines.append(f"- {a}" + (f" → {b}" if b else "") + ajeno)
        lines.append("")
    return "\n".join(lines)


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
    ap = argparse.ArgumentParser(
        description="Chequeo de salud de la bóveda: analiza `vault/` entera, imprime el resumen y "
                    "escribe `outputs/lint-<fecha>.md`.",
        epilog="Exit 1 si alguna categoría BLOQUEANTE tiene hits; los WARN y el backlog no bloquean."
    )
    # R-1 (decidida con el usuario, 2026-08-24): el MISMO detector de pares vencidos, dos
    # severidades según el momento. Sin flag = pasada periódica → backlog (frenar una bóveda con
    # deuda vieja un martes cualquiera no frena nada útil). Con flag = paso de cierre de una
    # operación que TOCÓ la nota → bloquea, porque un par sin verificar ahí significa que la
    # operación no terminó. La distinción vive acá, en un punto testeable, y no en prosa de skill:
    # un skill que se olvida de tratarlo como gate no deja rastro. D-44 intacto: el commit no se
    # frena — esto gatea la operación, no el commit.
    # #121: el flag toma un SLUG opcional. Sin él, alcance global (una pasada de cierre
    # deliberada sobre toda la bóveda). Con él, sólo los hallazgos de cierre de ESE sujeto cuentan
    # para el exit — el razonamiento de R-1 («un par sin verificar significa que no terminaste»)
    # es sobre lo que la operación TOCÓ, y aplicado a la bóveda entera hacía que una deuda vieja en
    # otro sujeto dejara el gate en rojo permanente. Medido al cerrar un tema: el único bloqueante
    # era de otra estrella, y hubo que auditar las categorías a ojo, una por una, para verlo. Un
    # gate que se audita a mano dejó de ser un gate.
    ap.add_argument("--cierre", nargs="?", const="", default=None, metavar="SLUG",
                    help="modo cierre de operación: los pares de verificación vencidos cuentan "
                         "para el exit (sin el flag son backlog, la pasada periódica). Con un SLUG, "
                         "sólo cuentan los de ese sujeto; la deuda ajena se reporta igual pero no "
                         "frena una operación que no la causó")
    args = ap.parse_args(list(argv))
    try:
        res = collect(cierre=args.cierre is not None, slug=args.cierre or None)
    except ValueError as e:
        _print_seguro(f"✗ {e}")
        return 2
    report = render(res)

    outdir = cfg.ROOT / "outputs"
    outdir.mkdir(exist_ok=True)
    out = outdir / f"lint-{dt.date.today().isoformat()}.md"
    out.write_text(report, encoding="utf-8")  # noqa: vault-write — destino `outputs/`, scratch regenerable (#137)
    _print_seguro(report)
    _print_seguro(f"→ {out}")
    # El exit sale de la SEVERIDAD declarada en la tabla, no de una tupla paralela que
    # había que acordarse de actualizar: agregar una categoría bloqueante y olvidarla en
    # `n_block` no rompía ningún test.
    if (n := res.n_block()):
        # ⚠ Con alcance, el mensaje dice «frenan el cierre de X», NO «hallazgos de X»: entre ellos
        # puede haber un bloqueante global (una fuente retractada, un hecho del entorno) que frena
        # igual y **no** es del sujeto. Atribuirlo a X sería un mapa que atribuye mal.
        que = f" frenan el cierre de `{res.slug}`" if res.slug else " en categorías bloqueantes"
        _print_seguro(f"✗ {n} hallazgo(s){que} → exit 1")
        return 1
    if res.slug:
        _print_seguro(f"✓ nada frena el cierre de `{res.slug}` — la deuda ajena queda listada arriba")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
