"""Partición de una nota en bloques citables + los dos hashes del ancla (D-4 / D-20).

@inv INV-78

QUÉ PROBLEMA RESUELVE. El bloque `## Verificación de citas (AAAA-MM-DD)` de una nota se lee como
"esta nota está verificada", pero una edición posterior —una frase nueva con su `[[bibcode]]`, un
número corregido, una re-extracción del `.txt`— deja afirmaciones que nadie chequeó bajo ese mismo
encabezado. Hasta 1.24.0 el lint lo medía por fecha de git contra la fecha del bloque: **todo o
nada por archivo**. Acá la unidad pasa a ser el **par** (afirmación, cita), con dos hashes:

- **ancla de bloque** — sha256 (10 hex) del bloque markdown **normalizado** que contiene la cita.
- **hash de fuente** — sha256 (10 hex) del `.txt` que se leyó para verificarla.

LA GRANULARIDAD ES EL BLOQUE, y las otras dos se descartaron midiendo:

- por **línea**: las notas van hard-wrapped a ~100 columnas; reflowear corre todos los cortes y
  marca la nota entera como vencida — falsos positivos en masa, y un mecanismo que grita siempre
  se apaga.
- por **sección**: editar una frase invalida las doce citas de la sección.

Unidad = el bloque más chico que contiene la cita: **párrafo / fila de tabla / ítem de lista /
blockquote**.

Medido con ESTE módulo sobre una instancia real, población **notas de entidad** (28 archivos:
`stars/` + `concepts/` + `queries/`; se excluyen `papers/`, y `log.md`/`index.md`, que son bitácora
y navegación —no afirman, y `log.md` solo aporta 361 pares espurios—): **840 pares** — 395 en
ítems, 260 en párrafos, 176 en filas, 9 en blockquotes. De esos, **745 citan por su cuenta y 95
heredan** (11%): la herencia no es el caso dominante. El derrame máximo de un ámbito es de 30 hijos
(una tabla de keywords bajo un caption con una sola fuente): legítimo, y el caso para el que la
herencia existe.

⚠ El plan de implementación cita **761 / 560 párrafos / 141 listas / 54 tablas / 6 blockquotes**
para este mismo corpus. El **total** es compatible (761 citas crudas ↔ 840 pares: la diferencia la
explican la herencia, +95, y la deduplicación dentro de un bloque). Lo que **no** se reproduce es el
**reparto por tipo**: ahí las listas dominan (395) y los párrafos quedan segundos (260), al revés de
lo que dice el plan. La causa más probable es que aquella medición contara una lista entera como un
bloque (dice "141 en listas (24 bloques)"). Vale el número de acá, que es el que produce el código
que corre; el del plan queda como referencia histórica.

**SOBRE-DISPARAR ES CORRECTO, SUB-DISPARAR NO.** Un párrafo con 3 citas da 3 pares con la misma
ancla: tocás una frase y se re-verifican las tres. El error tiene que caer siempre del lado caro
(verificar de más), nunca del lado mentiroso (decir "verificado" sobre texto que nadie miró).

**HERENCIA.** Una fila o un ítem sin `[[bibcode]]` propio hereda la cita del ámbito que lo
introduce (caption / párrafo / encabezado), como ya define `CLAUDE.md`. Su ancla hashea **los dos**
bloques: editar el caption cambia lo que la fila afirma, así que tiene que vencerla. Una fila que
trae su propia cita NO hereda — el caption no forma parte de lo que afirma.

Módulo aparte y no inline en `lint.py` porque lo consumen al menos tres lectores: el lint, el
benchmark, y el equivalente determinista del skill `verify-citations`.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import lib_config as cfg

# Encabezado del bloque de auditoría. Se excluye de la partición: sus filas llevan `[[bibcode]]`
# pero son el REGISTRO de la verificación, no afirmaciones. Si entraran, el bloque se hashearía a
# sí mismo y cada re-verificación lo vencería sola — un lazo que nunca converge.
VERIFY_HEADER = "## Verificación de citas"
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")   # un `|` que no venga escapado

# ⛔ Exige que después del target venga un delimitador (`]`, `|` o `#`) y **corta en el salto de
# línea**. Sin eso, un `[[` sin cerrar se tragaba el link SIGUIENTE: medido el 2026-08-28,
# `"[[ y sigo.\nEl radio vive en [[gp-kernels]]"` devolvía UN solo target multilínea, así que un
# wikilink real dejaba de contar como entrante y su destino se reportaba **huérfano** — categoría
# BLOQUEANTE — con un mensaje que nombraba un target inservible.
LINK_RE = re.compile(r"\[\[([^\]\|#\n]+)(?=[\]\|#])")
BIBCODE_RE = re.compile(r"^\d{4}[A-Za-z]")      # misma heurística que lint/bench_verify/fetch_web
_WS_RE = re.compile(r"\s+")
_BULLET_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")
_SEP_ROW_RE = re.compile(r"^\|[\s\-:|]+\|?$")   # `|---|---|` — estructura, no contenido
_FM_DELIM_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class Block:
    """Un bloque citable. `intro` es el ámbito heredado (None si el bloque cita por su cuenta)."""
    kind: str            # "parrafo" | "fila" | "item" | "blockquote"
    first_line: int      # 1-indexada sobre el texto completo de la nota
    text: str
    intro: str | None = None


@dataclass(frozen=True)
class Row:
    """Una fila del bloque `## Verificación de citas`: un par ya verificado, con sus dos hashes.

    ⚠ `verdict` y `condition` son EJES DISTINTOS desde 1.39.0 (ver `VERDICTS`)."""
    n: str
    claim: str
    bibcode: str
    verdict: str
    anchor: str
    source_hash: str
    condition: str = ""
    # #117: contra QUÉ archivo se verificó este par — `txt` o `pdf`. `None` = la fila no lo declara
    # (plantilla anterior a 1.54.0), que **no** es lo mismo que `txt`: es «no consta», y el lint lo
    # trata como no evaluable en vez de asumir. Ver `split_source_ref`.
    source_kind: str | None = None
    # #122: el texto de `Evidencia`. Lleva el LOCALIZADOR (`(L320)` / `(p. 628)`), que dice desde
    # otro ángulo lo mismo que `source_kind` — y los dos pueden discrepar.
    evidence: str = ""


@dataclass(frozen=True)
class Pair:
    """Un par (afirmación, cita) con su ancla. Varias citas en un bloque → varios pares, misma ancla."""
    bibcode: str
    block: Block
    anchor: str


# ── hashes ───────────────────────────────────────────────────────────────────────────────────────

def normalize_ws(text: str) -> str:
    """Colapsa runs de whitespace. Es lo que hace que **reflowear no mueva el hash** y que cambiar
    un número sí — la propiedad de la que depende toda la granularidad de bloque."""
    return _WS_RE.sub(" ", text).strip()


def sha10(text: str | bytes) -> str:
    """sha256 truncado a 10 hex. Puerta pública para que el llamador pase texto **ya leído**: el
    lint lee cada `.txt` para `is_legible` (77% de sus 5,6 s sobre 908 notas) y esa misma lectura
    alimenta el hash de fuente. Sin esto, agregar el hash duplicaría la parte más cara del lint.

    Acepta `bytes` para el caso del PDF (#113/B-2): el mismo espacio de hashes para los dos tipos de
    evidencia, así una fila no puede confundir un hash de `.txt` con uno de PDF."""
    return hashlib.sha256(text if isinstance(text, bytes) else text.encode("utf-8")).hexdigest()[:10]


def source_hash(path: Path) -> str:
    """Hash del `.txt` de fuente. Cuando el texto ya está en memoria, usar `sha10` directo."""
    return sha10(Path(path).read_text(encoding="utf-8", errors="replace"))


SOURCE_KINDS = ("txt", "pdf")


def split_source_ref(cell: str) -> tuple[str | None, str]:
    """`(kind, hash)` de una celda `Hash fuente`: `txt:ab12cd34ef` → `("txt", "ab12cd34ef")`.

    #117 — **la fila declara contra qué archivo se verificó, en vez de que el lint lo infiera del
    frontmatter.** La regla inferida (`symbols_lost` ⇒ PDF, si no el `.txt`) es más angosta que la
    práctica: una fuente `fulltext_source: ocr` **también** se verifica contra el PDF cuando el OCR
    del editor destruyó los símbolos — es lo que se hizo con 3 de las 5 fuentes marcadas de un tema
    real, y ahí el lint hasheaba el archivo equivocado y devolvía **17 pares «vencidos por fuente»**
    sobre fuentes que nadie tocó. La decisión la toma el verificador **par por par**; el frontmatter
    no la sabe. Una celda sin prefijo devuelve `(None, hash)`: *no consta*, distinto de `txt`.

    @inv INV-107"""
    cell = (cell or "").strip()
    kind, _, resto = cell.partition(":")
    if resto and kind.strip().lower() in SOURCE_KINDS:
        return kind.strip().lower(), resto.strip()
    return None, cell


_LOC_PAGINA = re.compile(r"\bp{1,2}\.\s*\d+", re.I)     # `p. 628`, `pp. 12-14`
_LOC_LINEA = re.compile(r"\bL\s?\d+\b")                  # `L320`, `L 320`


#: #221 · vocabulario CERRADO de la condición. El fan-out la puebla al 89 % de los pares (medido
#: sobre 96), así que «resolvé cada condición» no es una lista de trabajo: es la nota entera. Lo que
#: faltaba no era señal —ninguna de las condiciones medidas era descartable— sino el criterio para
#: separar la que cambia lo que el consumidor haría de la que sólo agrega procedencia.
#:
#: `acota`         — la afirmación es FALSA fuera de esa condición (el umbral es de otra estrella;
#:                   la medición no es sobre RVs). Se resuelve sí o sí: fila de `## Régimen de
#:                   validez`, o corrección de la prosa.
#: `contextualiza` — la afirmación sigue siendo cierta y la condición agrega procedencia
#:                   (instrumento, tamaño de muestra, año). Va al reporte y NO obliga a editar;
#:                   rige la regla de poda.
#:
#: ⚠ Salvedad honesta: la clasificación es en sí misma un juicio, así que hereda parte del problema
#: que la eliminación de `parcial` atacó (1.39.0). La diferencia es que acá el juicio tiene un test
#: operativo —**¿la afirmación queda falsa si se saca la condición?**— que `parcial` nunca tuvo.
#: #276/#280 · la marca `(inferencia de [[b1]], [[b2]])` en prosa. Vive acá porque la cuentan DOS
#: consumidores: el bloqueante del lint (`inferencias_sin_premisas`, INV-86) y el conteo que la
#: sub-sección del bloque publica. El `[`*_~]*` no es cosmético: sin él la marca es ciega al énfasis
#: markdown y el detector veía 2 de 5 (#276).
INFER_MARK = re.compile(r"\(\s*[`*_~]*\s*inferencia(?![^\W_])(?:[^()]|\([^()]*\))*\)", re.I)


def inference_marks(prose: str) -> list:
    """Every `(inferencia …)` mark in the prose, adornment and all (#280)."""
    return [m.group(0) for m in INFER_MARK.finditer(prose or "")]


CONDITION_KINDS = ("acota", "contextualiza")

#: #280 · la resolución de una condición `acota`, anotada en la MISMA celda y con la misma notación
#: que el veredicto de al lado (#232: la segunda ronda ANOTA, no pisa): `acota→resuelta: <dónde>`.
CONDITION_RESOLUTIONS = ("resuelta",)

# Lo que separa la clase de la condición de su prosa. Mismo problema que `_RESOLUCION_SEP` en la
# columna de al lado, más el guión suelto: la celda se escribe `acota: …` en la plantilla y
# `**contextualiza** — …` cuando la escribe un fan-out que pone negrita en toda la tabla (#283).
_COND_SEP = re.compile(r"\s*(?:→|->|—|–|--|-|:)\s*")


def condition_kind(condicion: str) -> str | None:
    """The declared kind of a condition cell (`acota` / `contextualiza` head), or `None`.

    `None` covers both «the cell is empty» (nothing to classify) and «it has prose but no kind» —
    the caller separates them, because only the second is a finding.

    #283 — the head is read **normalised**: markdown emphasis and the separator that follows it are
    dropped, the same way `_bare_verdict` reads the cell next door. Comparing the raw string made
    `**contextualiza** — …` unclassifiable: measured on a real note, 74 of 88 cells were reported as
    «condition without a kind» purely because of the adornment, i.e. 84 % false positives in a
    category whose whole job is to separate the condition that forces an edit (`acota`) from the one
    that only goes to the report. Third time this repo pays for adornment blindness (cf. #168, #276).
    """
    # (#221 no tiene invariante propio: la clase de la condición es una categoría de backlog del
    # lint, no una promesa P0/P1 del contrato — la red es el test de paridad con `verdict_valido`.)
    cabeza = _COND_SEP.split(str(condicion or "").strip().lower(), maxsplit=1)[0].strip(_ADORNO).strip()
    return cabeza if cabeza in CONDITION_KINDS else None


def condition_resolved(condicion: str) -> bool:
    """Does this condition cell record that its `acota` was already resolved? (#280)

    ⛔ It does NOT reuse `resueltos()`: there, anything after the separator means «resolved», and in
    a condition cell what follows the separator is **the condition's own prose** — every cell would
    come back resolved. The token right after the first separator must be one of
    `CONDITION_RESOLUTIONS`, whole (the lesson of #276: `resueltamente` is not `resuelta`)."""
    partes = _COND_SEP.split(str(condicion or "").strip().lower(), maxsplit=2)
    if len(partes) < 2:
        return False
    return partes[1].strip(_ADORNO).strip() in CONDITION_RESOLUTIONS


def locator_kinds(evidencia: str) -> set:
    """Qué tipo de localizador usa la celda `Evidencia`: `{"pdf"}`, `{"txt"}`, los dos, o vacío.

    #122 — `Evidencia` y `Hash fuente` dicen lo mismo desde ángulos distintos: uno cita `p. 628` o
    `L320`, el otro declara `pdf:` o `txt:`. Nada los cruzaba, así que una fila podía citar una
    PÁGINA y vigilar el `.txt`: el hash cuida un archivo del que esa cita no salió. Es el modo de
    falla de #117 sobrevivido a #117 — medido, **11 de 114** filas de un concepto real.

    ⚠ El falso positivo obvio: una cita textual puede contener `p. 12` como parte de la prosa del
    paper. Por eso esto **no** decide nada solo — el lint lo reporta como backlog para mirar, no
    como veredicto."""
    # @inv INV-113
    out = set()
    if _LOC_PAGINA.search(evidencia or ""):
        out.add("pdf")
    if _LOC_LINEA.search(evidencia or ""):
        out.add("txt")
    return out


def bytes_hash(path: Path) -> str:
    """Hash del archivo como BYTES. Para el PDF, que no es texto.

    #113/B-2: cuando el `.txt` de una fuente perdio el cuerpo de sus ecuaciones, la evidencia de esos
    pares es una PAGINA del PDF, no una linea del `.txt`. Hashear el `.txt` ahi hace dos cosas malas
    y ninguna buena: se dispara en falso si el `.txt` se re-extrae (la fuente real no se movio) y no
    vigila el archivo del que sale la cita.
    """
    return sha10(Path(path).read_bytes())


def block_anchor(text: str, intro: str | None = None) -> str:
    """Ancla de un bloque, con su ámbito heredado si lo tiene (los DOS bloques entran al hash)."""
    base = normalize_ws(text) if intro is None else f"{normalize_ws(intro)}\n{normalize_ws(text)}"
    return sha10(base)


# ── partición ────────────────────────────────────────────────────────────────────────────────────

def _cuerpo(text: str) -> tuple[str, int]:
    """(cuerpo sin frontmatter, líneas que consumió el frontmatter). Se delimita por LÍNEA `---`,
    no por búsqueda textual (mismo motivo que `cfg.frontmatter_span`, H-11: un `---` dentro de un
    escalar entrecomillado parte el split a la mitad)."""
    if not text.startswith("---"):
        return text, 0
    delims = list(_FM_DELIM_RE.finditer(text))
    # `delims[0].start() != 0` es el guard que `cfg.frontmatter_span` sí tiene y acá faltaba: sin
    # él, una nota que arranca con `---algo` (no un delimitador: la línea tiene más contenido) pasa
    # el `startswith` y se toman como frontmatter los DOS primeros `---` sueltos del cuerpo — dos
    # reglas horizontales, por ejemplo. El cuerpo queda recortado desde la segunda y los pares que
    # vivían antes desaparecen del fan-out: **sub-dispara**, que es justo el error que el módulo
    # documenta prohibir.
    if len(delims) < 2 or delims[0].start() != 0:
        return text, 0
    fin = delims[1].end()
    return text[fin:], text[:fin].count("\n")


def split_blocks(body: str) -> list[Block]:
    """Los bloques citables de una nota, en orden de aparición.

    Se excluyen, por no ser afirmaciones: el frontmatter (`thesis_links`, `disputes[].ref` — son
    contrato máquina, no prosa), los code fences (```dataview``` trae wikilinks dentro de la
    query), **todas las secciones que estampa la máquina** (`cfg.SECCIONES_ESTAMPADAS`: los tres
    roll-ups, el apéndice de excluidos y el propio bloque `## Verificación de citas`), los
    separadores `|---|---|` y la fila de **encabezado** de cada tabla.

    ⚠ Lo de los roll-ups llegó en 1.38.2 y no es cosmético: una fila de `## Papers` **no es una
    afirmación**, es metadata que estampó `make_notes`, y no hay nada que contrastar contra la
    fuente. Medido sobre la ficha de HD 40307 recién sintetizada: 178 pares contra **68** reales
    —110 de metadata—, con nueve bibcodes que no aparecen en ninguna afirmación, cuatro de ellos
    **sin `.txt`**. El fan-out habría lanzado 110 subagentes a verificar filas de tabla. Los dos últimos heredarían la cita del caption y ensuciarían el
    bloque de verificación con pares permanentes que nadie puede resolver — sobre-disparar es
    correcto cuando hay algo que verificar, no cuando no lo hay.
    """
    body, offset = _cuerpo(body)
    lineas = body.split("\n")
    out: list[Block] = []
    cur: list[str] = []
    cur_line = 0
    cur_kind = "parrafo"
    fenced = False
    en_verificacion = False
    # Último ámbito visto —párrafo (caption) o encabezado de sección—: del que hereda una fila o un
    # ítem SIN cita propia. Se lleva en una sola pasada: el ámbito de una fila es siempre algo que
    # ya se vio, así que no hace falta una segunda vuelta (y una segunda vuelta sobre `out` no
    # podría usar encabezados, porque no son bloques citables y no están ahí).
    intro_actual: str | None = None

    def flush():
        nonlocal cur, cur_kind, intro_actual
        if cur:
            texto = " ".join(cur)
            if cur_kind == "item":
                emitir("item", cur_line, texto)       # un ítem hereda, igual que una fila
            else:
                out.append(Block(cur_kind, cur_line, texto))
                if cur_kind != "blockquote":
                    # ⛔ #224 — un blockquote NO pasa a ser el ámbito vigente. Antes se emitía
                    # directo, sin pasar por acá, así que nunca lo era; al acumularlo como párrafo
                    # heredaría, y una fila que sigue a la cabecera `> _Estado —_` empezaría a
                    # colgar de ella. El cambio es sobre el ancla, no sobre la herencia.
                    intro_actual = texto              # este párrafo pasa a ser el ámbito vigente
        cur, cur_kind = [], "parrafo"

    def emitir(kind: str, linea_n: int, texto: str):
        """Una fila/ítem hereda sólo si NO cita por su cuenta (si cita, el caption no forma parte
        de lo que afirma y editarlo no debe vencerla)."""
        out.append(Block(kind, linea_n, texto,
                         None if _bibcodes(texto) else intro_actual))

    for i, linea in enumerate(lineas, 1 + offset):
        s = linea.strip()
        if s.startswith("```"):
            fenced = not fenced
            flush()
            continue
        if fenced:
            continue
        if s.startswith("#"):
            flush()
            # las secciones estampadas se saltean hasta el próximo encabezado
            # #214 — `cfg.is_stamped_section`, no un `startswith` pelado: éste era la regla VIEJA
            # que INV-98 arregló dentro de `_es_estampada` y que nunca llegó acá, así que
            # `## Papers relevantes para el método` —una sección PROPIA— se saltaba entera y sus
            # pares no se verificaban nunca. Una sola implementación.
            en_verificacion = cfg.is_stamped_section(s)
            intro_actual = None if en_verificacion else s.lstrip("# ").strip()
            continue
        if en_verificacion or not s:
            flush()
            continue
        if s.startswith(">"):
            # ⛔ #224 — un blockquote se ACUMULA como un párrafo, no se emite por línea. Las notas
            # van hard-wrapped a ~100 columnas, así que una cita textual larga vive partida en
            # varias líneas y **sólo la última lleva el `[[bibcode]]`**: emitiendo por línea, el
            # único par que nace ancla la última línea y las demás no las cubre nadie. Medido: una
            # cita de 5 líneas donde invertir el sentido de la línea 67 (`uncorrelatedness is
            # equivalent` → `is NOT equivalent`) dejaba el ancla IDÉNTICA — o sea que se podía
            # reescribir el contenido de una cita sin que el par se venciera.
            # Es sub-disparo, la única dirección de error que el docstring de este módulo declara
            # prohibida, y por el motivo exacto que ahí se usa para descartar la granularidad por
            # línea. El `Afirmación (extracto)` de esas filas lo delataba: era el fragmento sin
            # sentido con el que cierra la cita.
            if cur_kind == "blockquote" and cur:
                cur.append(s.lstrip("> ").strip())
            else:
                flush()
                cur, cur_line, cur_kind = [s.lstrip("> ").strip()], i, "blockquote"
            continue
        if s.startswith("|"):
            flush()
            if _SEP_ROW_RE.match(s):
                # el separador marca que la fila ANTERIOR era el encabezado de la tabla
                if out and out[-1].kind == "fila":
                    out.pop()
                continue
            emitir("fila", i, s)
            continue
        if _BULLET_RE.match(s):
            flush()
            cur, cur_line, cur_kind = [s], i, "item"
            continue
        if cur:
            cur.append(s)                    # continuación hard-wrapped del bloque en curso
        else:
            cur, cur_line, cur_kind = [s], i, "parrafo"
    flush()
    return out


def _bibcodes(text: str) -> list[str]:
    """Los `[[targets]]` del texto que parecen clave de cita, en orden y sin repetir."""
    vistos, out = set(), []
    for t in LINK_RE.findall(text):
        t = t.strip()
        if BIBCODE_RE.match(t) and t not in vistos:
            vistos.add(t)
            out.append(t)
    return out


def pairs_of(body: str) -> list[Pair]:
    """Un par por cada (cita, bloque). Un bloque con 3 citas da 3 pares con la MISMA ancla.

    Un bloque que hereda aporta los bibcodes de su ámbito: es la fila de tabla que dice "34 d" bajo
    un caption que dice quién lo midió — sin la herencia, esa fila se caía del fan-out por no
    llevar `[[bibcode]]` propio, que es justo la afirmación que hay que verificar.
    """
    out: list[Pair] = []
    for b in split_blocks(body):
        fuente = b.text if _bibcodes(b.text) else (b.intro or "")
        for bib in _bibcodes(fuente):
            out.append(Pair(bib, b, block_anchor(b.text, b.intro)))
    return out


# ── el bloque de verificación ────────────────────────────────────────────────────────────────────

# Vocabulario CERRADO del veredicto. `parcial` se ELIMINÓ en 1.39.0 y no es un recorte cosmético:
# ese valor fusionaba dos preguntas ortogonales —«¿la fuente respalda esto?» (textual, decidible
# contra el `.txt`) y «¿la afirmación está completa?» (juicio de grado)— y la fusión hacía que la
# parte dura arrastrara a la blanda.
#
# Medido el 2026-08-25 sobre la ficha de HD 40307: dos corridas independientes del fan-out, jueces
# nuevos y ciegos, 60 pares comparados → **95 % de coincidencia (57/60)**, y las TRES divergencias
# vivían exactamente en el borde `soportada`↔`parcial`, todas en la misma dirección. `contradice`
# reprodujo 2/2. O sea: el eje textual es estable y el de grado no lo es — y el skill nunca definió
# ese umbral.
#
# Lo que era `parcial` se descompone sin pérdida: o la fuente respalda la afirmación pero bajo
# condiciones que la nota no dice (→ `soportada` + `condicion` poblada), o la cita NO toca el
# contenido distintivo de la afirmación (→ `no-soportada`, como ya mandaba el contrato).
VERDICTS = ("soportada", "no-soportada", "contradice", "no verificable por extracción")
# #91 · los que EXIGEN acción antes de cerrar. `no-soportada` = la fuente calla; `contradice` = la
# fuente afirma lo contrario. Los dos son, tal cual quedan escritos, una afirmación que la bóveda
# hace y su propia fuente no respalda: el contrato manda RESOLVERLOS (bajar la afirmación a lo que
# dice la fuente, reasignar la cita al bibcode correcto, marcar `inferencia`, o taguear la disputa),
# no registrarlos y seguir. `no verificable por extracción` NO entra: es una propiedad de la fuente
# (ecuación, tabla, escaneo), no un defecto de la nota.
VERDICTS_SIN_RESOLVER = ("no-soportada", "contradice")

#: #223 · el veredicto que NO PUEDE declarar un archivo, porque no hay ninguno. `no verificable por
#: extracción` es propiedad de la FUENTE —la nota de paper no tiene PDF ni `.txt` en disco, típico
#: de un `fuente: abstract` (#207) o de un paper cuyos artefactos borró `--drop-core`—, así que su
#: fila no puede llevar `txt:`/`pdf:` en `Hash fuente`: no hay qué hashear. El chequeo de #117
#: bloqueaba igual, o sea que el contrato exigía declarar un archivo justo en las filas que existen
#: para decir que no lo hay. Medido: 9 filas de un concepto real, todas correctas, bloqueando el
#: cierre. Es el mismo criterio con que este veredicto ya está fuera de `VERDICTS_SIN_RESOLVER`.
VERDICTS_WITHOUT_SOURCE = ("no verificable por extracción",)


def has_no_source_file(verdict: str) -> bool:
    """Is this verdict one that cannot name a source file? (#223)

    Same normalisation as `resueltos`: a verdict may carry its resolution in the same cell and be
    dressed in markdown emphasis, and comparing the raw string lets any of those slip through."""
    pelado = _RESOLUCION_SEP.split(str(verdict or "").strip(), 1)[0].strip(_ADORNO).lower()
    return pelado in VERDICTS_WITHOUT_SOURCE


# Lo que separa el veredicto de su resolución anotada en la misma celda. `→` es lo que la plantilla
# del skill usa; `->` y el paréntesis son cómo se escribe a mano. El espaciado NO es parte del
# separador: `startswith(mal + " ")` daba por SIN RESOLVER a `no-soportada → corregida` (#168).
_RESOLUCION_SEP = re.compile(r"\s*(?:→|->|—|--|:|\()\s*")

# Énfasis markdown y puntuación final: no cambian NADA de lo que la fila dice, pero con la
# comparación literal cualquiera de los tres apagaba el bloqueante de INV-117 (#168).
_ADORNO = "*`_~ .,;)"


def _bare_verdict(verdict: str) -> str:
    """El veredicto de la celda, sin formato markdown y sin la resolución anotada.

    Se usa para decidir SI la celda registra una falla; que además esté resuelta lo decide
    `resueltos` mirando el otro lado del separador."""
    return _RESOLUCION_SEP.split((verdict or "").strip().lower(), maxsplit=1)[0].strip(_ADORNO).strip()


def resueltos(verdict: str) -> bool:
    """`False` si esta fila deja una afirmación sin respaldo. Tolera la anotación de la resolución
    en la misma celda —`no-soportada→corregida`, que es como la plantilla del skill muestra el caso
    resuelto, con o sin espacios alrededor de la flecha—: lo que bloquea es el veredicto **pelado**.

    Dos correcciones de #168, una por dirección. El veredicto se compara **normalizado**, así que el
    énfasis markdown no es una resolución (`**no-soportada**` seguía siendo una afirmación sin
    respaldo y pasaba limpia). Y la resolución se detecta por el **separador**, no por
    `startswith(mal + " ")`, así que el espaciado de la flecha no inventa un veredicto nuevo
    (`no-soportada → corregida`, que es como se escribe a mano, bloqueaba estando resuelta)."""
    # @inv INV-117
    v = (verdict or "").strip().lower()
    partes = _RESOLUCION_SEP.split(v, maxsplit=1)
    if len(partes) > 1 and partes[1].strip(_ADORNO).strip():
        return True                     # hay resolución anotada: la celda dice qué se hizo
    pelado = partes[0].strip(_ADORNO).strip()
    # ⛔ Un veredicto FUERA del vocabulario cerrado no puede contar como resuelto. Medido el
    # 2026-08-28: `'contradise'`, `''` y `'no soportada'` (con espacio) devolvían `True`, o sea que
    # el bloqueante que INV-117 sostiene **se apagaba con una letra** — y la fila quedaba bajo un
    # encabezado que se lee como garantía. Una celda que no se puede leer no certifica nada; el
    # lint la reporta aparte con el motivo correcto (typo, no «sin resolver»).
    if pelado not in VERDICTS:
        return False
    return pelado not in VERDICTS_SIN_RESOLVER


def verdict_valido(verdict: str) -> bool:
    """¿El veredicto pelado está en el vocabulario cerrado? Distingue el TYPO del «sin resolver».

    Se arreglan distinto: un typo se corrige en la celda, un `no-soportada` se resuelve volviendo a
    la fuente. Mandar el mensaje equivocado manda a hacer el trabajo equivocado."""
    # @inv INV-117
    v = (verdict or "").strip().lower()
    pelado = _RESOLUCION_SEP.split(v, maxsplit=1)[0].strip(_ADORNO).strip()
    return pelado in VERDICTS

# Columnas que hacen evaluable al bloque. Sin `ancla`/`hash` no hay dónde colgar los hashes (la
# plantilla pre-D-20 colapsaba las soportadas en prosa y dejaba una sola fila, la que falló). Sin
# `condición` el bloque es pre-1.39.0: registraba el veredicto y **tiraba** lo que la corrida había
# encontrado sobre el régimen —el output más valioso del fan-out, y el que las dos corridas del
# experimento producían distinto aun cuando el veredicto coincidía—.
_COLS_HASH = ("ancla", "hash", "condici")


def split_row(line: str) -> list[str]:
    """Cells of a markdown table row, splitting only on **unescaped** pipes.

    A verbatim quote can carry a `|` of its own (a table row of the paper), and the generator
    escapes it `\\|` as markdown mandates. Splitting on a bare `|` turns that one cell into two and
    shifts every column to its right — including the anchor, which is then read from the wrong cell
    and makes the pair look stale against a source nobody touched.
    """
    #  @inv INV-99
    return [c.replace("\\|", "|").strip() for c in _CELL_SPLIT_RE.split(line.strip().strip("|"))]


#: #232 · las tres sub-secciones que la plantilla del bloque cierra, obligatorias aunque digan
#: «ninguna». Es el ÚNICO lugar donde queda escrito el triage de la corrida: medido, de 91
#: condiciones pobladas 28 declaraban una omisión de la nota, y nada en la nota decía cuáles se
#: juzgaron no vinculantes — el razonamiento se hizo, vivió en `build/` (scratch) y no llegó al
#: artefacto que viaja.
VERIF_SUBSECCIONES = ("Inferencias declaradas", "Omisiones en transcripciones",
                      "Condiciones perdidas")


def verif_counts(rows: list) -> dict:
    """The four numbers the block's header must publish, computed from the rows themselves (#232).

    Written by hand they drift: the header of a real block described round 1 over 96 pairs while its
    table had 99, and omitted both the condition count (91/99) and the resolved contradictions. It is
    the lesson of INV-81 —the roll-up header and its rows come from the same code— applied to the
    verification block.

    `contradicen` counts every row whose verdict mentions `contradice`, resolved or not: the point of
    the number is that the note DID contradict its source, and the second round must not blank it.
    """
    vs = [str(r.verdict or "").strip().lower() for r in rows]
    return {"pares": len(rows),
            "soportadas": sum(1 for v in vs if v.startswith("soportada")),
            "no_soportadas": sum(1 for v in vs if v.startswith("no-soportada")),
            "contradicen": sum(1 for v in vs if v.startswith("contradice")),
            # #263 — el cuarto veredicto del vocabulario. Sin él los conteos NO PARTICIONAN: medido
            # en una ficha real, 73 + 6 + 5 = 84 sobre 88 pares, y las 4 que faltaban eran
            # `no verificable por extracción` correctas (#223: la fuente no está en disco). El
            # lector que suma queda con filas sin explicar, y las dos lecturas naturales —«la tabla
            # está cortada», «el conteo está mal»— son las dos falsas. Es D-43 sin aplicar a la
            # cabecera del propio bloque: lo no evaluable se declara, no se omite — y acá es lo que
            # dice que N afirmaciones de la nota no se pudieron contrastar contra nada.
            "no_verificables": sum(1 for v in vs if v.startswith("no verificable")),
            # #286 — cuántas de esas dos ya no están abiertas. ⛔ Sin RESTARLAS del total: el punto
            # de #232 es que el número no se blanquea —la nota SÍ contradijo a su fuente— y lo que
            # faltaba era decir cuántas se resolvieron. Sin el desglose, «9 no-soportadas» tiene dos
            # lecturas —«hay 9 afirmaciones sin respaldo» (falsa y grave) y «las tuvo y se
            # corrigieron» (verdadera)— y la cabecera existe para no tener que bajar a la tabla.
            "no_soportadas_resueltas": sum(1 for r in rows
                                           if str(r.verdict or "").strip().lower().startswith("no-soportada")
                                           and resueltos(r.verdict)),
            "contradicen_resueltas": sum(1 for r in rows
                                         if str(r.verdict or "").strip().lower().startswith("contradice")
                                         and resueltos(r.verdict)),
            # #274c — filas cuya celda registra MÁS DE UNA ronda (`no-soportada→contradice→
            # corregida`). La partición sigue siendo por el PRIMER veredicto —el que dice qué hizo
            # mal la nota—; esto dice cuántas filas pelearon más de una vuelta, que es lo que la
            # notación de una sola flecha no podía registrar. Medido: una nota de 8 rondas emitió 13
            # veredictos malos y publicó 11.
            "cadenas": sum(1 for r in rows if len(verdict_chain(r.verdict)) > 1),
            # #280 — la condición, desglosada por CLASE. Los tres particionan `con_condicion`, que
            # es lo que hace chequeable el conteo que la sub-sección publica: escrito a mano deriva
            # (medido: «las 20 marcadas `acota`» sobre una tabla que tenía 3).
            "cond_acota": sum(1 for r in rows if condition_kind(r.condition) == "acota"),
            "cond_acota_resueltas": sum(1 for r in rows if condition_kind(r.condition) == "acota"
                                        and condition_resolved(r.condition)),
            "cond_contextualiza": sum(1 for r in rows
                                      if condition_kind(r.condition) == "contextualiza"),
            "con_condicion": (_cc := sum(1 for r in rows
                                         if str(r.condition or "").strip() not in ("", "—", "-", "–"))),
            "cond_sin_clase": _cc - sum(1 for r in rows if condition_kind(r.condition))}


def verif_summary(rows: list) -> str:
    """The canonical header line for a verification block, from `verif_counts`."""
    c = verif_counts(rows)
    # El `—` separa los dos EJES: los cuatro primeros particionan las filas por veredicto y suman
    # `pares`; `con_condicion` es ortogonal (una fila `soportada` puede tener condición). Juntarlos
    # con `/` es lo que hacía leer el resumen como una partición de cinco que no cerraba.
    # #286 — los dos veredictos con resolución publican cuántas de las suyas están resueltas. El
    # `(resueltas)` fijo del texto viejo lo decía de uno solo y sin número, justo en la categoría
    # donde un valor PELADO bloquea el cierre (#91): el número más alarmante de la línea era el peor
    # etiquetado. Medido: «9 no-soportadas» con las 9 resueltas y `lint --cierre` en 0.
    return (f"{c['pares']} pares; {c['soportadas']} soportadas "
            f"/ {c['no_soportadas']} no-soportadas ({c['no_soportadas_resueltas']} resueltas) "
            f"/ {c['contradicen']} contradicen ({c['contradicen_resueltas']} resueltas) "
            f"/ {c['no_verificables']} no verificables "
            f"— {c['con_condicion']} con condición declarada"
            + (f" · {c['cadenas']} con más de una ronda" if c["cadenas"] else ""))


def verif_subsection_lines(rows: list, prose: str) -> dict:
    """The generated count fragment for each of the three sub-sections, or `None` (#280).

    INV-81 one level down: the header's numbers come from the same code that reads the table, and
    the three sub-sections were left as free prose — so they drifted. Measured on a real note:
    «las 20 marcadas `acota`» over a table holding **3**, and «cinco inferencias» over **six** marks
    in the body, with one item too many and one missing.

    ⛔ `Omisiones en transcripciones` maps to `None` on purpose: completeness is the judgement half
    of the fan-out and nothing in the table encodes it. Emitting a number there would be the
    invented zero D-43 forbids.

    ⚠ `prose` must be the note's prose **without stamped sections** (`cfg.solo_prosa`): the
    sub-section itself enumerates the marks, and counting them there counts them twice."""
    c = verif_counts(rows)
    return {"Inferencias declaradas": f"— {len(inference_marks(prose))} marcas en el cuerpo",
            "Omisiones en transcripciones": None,
            "Condiciones perdidas": (f"— {c['con_condicion']} con condición: {c['cond_acota']} "
                                     f"`acota` ({c['cond_acota_resueltas']} resueltas) / "
                                     f"{c['cond_contextualiza']} `contextualiza` / "
                                     f"{c['cond_sin_clase']} sin clasificar")}


def parse_verif_table(text: str) -> list[Row] | None:
    """Las filas del bloque `## Verificación de citas`, o `None` si el bloque **no se puede
    evaluar** — porque no existe, o porque es de la plantilla vieja (sin las columnas de hash).

    La distinción importa: un bloque sin columnas de hash NO es "cero pares vencidos". Es un bloque
    que nadie puede chequear, y leerlo como limpio sería el mismo cero inventado que D-43 prohíbe.
    El lint lo reporta como *plantilla vieja*, bloqueante. Sin migrador: la bóveda es nueva.

    Un bloque bien formado y **sin filas** devuelve `[]` — eso sí es evaluable, y deja todo par del
    cuerpo como *sin verificar*.
    """
    i = cfg.section_start(text, VERIFY_HEADER)
    if i < 0:
        return None
    seccion = text[i:]
    corte = seccion.find("\n## ", 1)
    if corte > 0:
        seccion = seccion[:corte]
    filas = [ln.strip() for ln in seccion.split("\n") if ln.strip().startswith("|")]
    if not filas:
        return None
    cols = [c.strip().lower() for c in filas[0].strip("|").split("|")]
    if not all(any(c in col for col in cols) for c in _COLS_HASH):
        return None                      # plantilla vieja: no hay dónde colgar los hashes

    def _idx(*claves, default=None):
        """Posición de la primera columna cuyo encabezado contiene alguna clave."""
        for k in claves:
            for j, col in enumerate(cols):
                if k in col:
                    return j
        return default

    # ⚠ Se lee por NOMBRE de columna, no por posición. La plantilla que publican `CLAUDE.md` y el
    # skill `verify-citations` tiene OCHO columnas (con `Score` y `Evidencia`) y el parser leía las
    # posiciones 4 y 5 — o sea, tomaba el Score como ancla y la Evidencia como hash, **en silencio**:
    # el detector de plantilla vieja no lo agarra porque ese encabezado sí contiene "ancla" y "hash".
    # Efecto medido: toda nota escrita según la documentación dejaba `lint.py --cierre` en rojo
    # permanente, y el cierre de una operación es justamente lo que ese flag decide.
    i_n, i_claim = _idx("#", default=0), _idx("afirmaci", default=1)
    i_fuente, i_verd = _idx("fuente", default=2), _idx("veredicto", default=3)
    i_ancla = _idx("ancla", default=4)
    i_hash = _idx("hash fuente", "hash", default=5)
    i_cond = _idx("condici", default=6)
    i_evid = _idx("evidencia")            # opcional: la plantilla de 7 columnas no la trae
    out: list[Row] = []
    for ln in filas[1:]:
        if _SEP_ROW_RE.match(ln):
            continue
        celdas = split_row(ln)
        # ⚠ Una fila con MENOS celdas que el encabezado —típico: la `Condición` vacía omitida— caía
        # acá con un `continue` y se perdía ENTERA, y con ella el `Veredicto`: un `no-soportada`
        # dejaba de disparar el bloqueante de INV-117 y quedaba registrado bajo un encabezado que
        # se lee como garantía. Es **el mismo defecto que #128 arregló para la dirección opuesta**
        # (más celdas ⇒ se recupera por contenido) y con el mismo argumento escrito abajo:
        # descartar la fila es peor que leerla a medias. Medido el 2026-08-28.
        corrida = len(celdas) != len(cols)
        if corrida:
            # Celdas de MÁS ⇒ hay un `|` sin escapar y las columnas de la DERECHA (ancla, hash,
            # condición) están corridas. Celdas de MENOS ⇒ falta alguna de la derecha. En los dos
            # casos lo que no se puede leer son las posicionales, no la fila. Indexar por posición leería el
            # ancla de otra celda y el par volvería "vencido por edición" sin que nadie editara nada
            # (medido: 18 pares, 2026-08-25).
            #
            # ⚠ Hasta #128 esto era un `continue` y la fila se perdía ENTERA — con ella el
            # `Veredicto`, así que un `no-soportada` dejaba de disparar el bloqueante de INV-117 y
            # quedaba invisible. El skill `verify-citations` dice que la barra sin escapar «es el
            # caso normal, no el raro». Descartar la fila es peor que leerla a medias: lo que no se
            # puede leer son las columnas corridas, no la fila.
            #
            # Se recupera lo decidible POR CONTENIDO —el veredicto contra su vocabulario cerrado y
            # el bibcode por su `[[…]]`— y se declaran **vacías** las posicionales. No se adivina:
            # sin ancla el par cae en «sin verificar», que es lo que corresponde.
            verd = next((c for c in celdas if _bare_verdict(c) in VERDICTS), "")
            bibs = next((b for c in celdas for b in [_bibcodes(c)] if b), [""])
            out.append(Row(celdas[i_n], celdas[i_claim], bibs[0], verd, "", "", "", None, ""))
            continue
        bibs = _bibcodes(celdas[i_fuente]) or [celdas[i_fuente].strip("[]")]
        kind, h = split_source_ref(celdas[i_hash])
        evid = celdas[i_evid] if i_evid is not None and i_evid < len(celdas) else ""
        out.append(Row(celdas[i_n], celdas[i_claim], bibs[0], celdas[i_verd],
                       celdas[i_ancla], h, celdas[i_cond], kind, evid))
    return out


# ── #284 · la puerta de ESCRITURA del bloque, simétrica de `_split_row` ──────────────────────────
#
# `_split_row` **des-escapa** los `\|` al leer, y hasta 1.106.x no había ninguna puerta del lado de
# la escritura. Quien lee filas para reescribirlas —el flujo que #282 creó— recibía pipes crudos y,
# al escribirlos, **partía la fila**: la fila queda con más celdas que el encabezado, `Ancla` se lee
# de la columna equivocada y el par se cuenta vencido contra una fuente que nadie tocó. Medido en la
# reconstrucción de una ficha real: **73 de 131** filas volvieron con `anchor == ""`, todas ellas
# filas acarreadas cuya `Evidencia` transcribe una tabla del paper — el caso normal, no el raro.
#
# Es la cuarta vez que este repo paga por tener la regla de escape en un solo lado (#240, #214,
# INV-98, #222). La salida es la de #222: **re-parsear lo escrito y exigir que devuelva lo que se le
# escribió**; un bloque cuya lectura no reproduce lo que se escribió NO SE PUBLICA.

#: Las ocho columnas de la plantilla vigente, en orden. La escritura las produce; la lectura
#: (`parse_verif_table`) indexa por NOMBRE, así que el orden de acá no es un contrato para leer.
VERIF_COLS = ("#", "Afirmación (extracto)", "Fuente", "Veredicto", "Evidencia", "Ancla",
              "Hash fuente", "Condición")


def _hash_cell(row) -> str:
    """The `Hash fuente` cell, restoring the prefix `split_source_ref` stripped when reading.

    `source_kind is None` means *not stated* (#117) and is written back verbatim: inventing a prefix
    would guess which file the pair was verified against, which is the very thing the field exists
    to avoid."""
    h = str(row.source_hash or "")
    return f"{row.source_kind}:{h}" if row.source_kind and ":" not in h else h


#: #226 · el largo con que se trunca `Afirmación (extracto)`, la ÚNICA columna truncable.
TRUNCADO_CLAIM = 180

# Aperturas que un corte no puede dejar sin cerrar. `$…$` es el caso medido (10 de 88 filas de una
# ficha real cortadas a media fórmula, las únicas 10 con `$` impar de toda la nota: en Obsidian un
# `$` huérfano se traga texto hasta el próximo `$`); `[[…]]` es peor todavía, porque un wikilink
# partido es un **bloqueante** del lint (#257c).
_SPANS_ABIERTOS = (("$", "$"), ("`", "`"), ("[[", "]]"))


def _cut_is_safe(texto: str, i: int) -> bool:
    """Does cutting at `i` leave every delimited span closed? (#274b)"""
    prefijo = texto[:i]
    for abre, cierra in _SPANS_ABIERTOS:
        if abre == cierra:
            if prefijo.count(abre) % 2:
                return False
        elif prefijo.count(abre) != prefijo.count(cierra):
            return False
    return True


def truncate_claim(texto: str, limite: int = TRUNCADO_CLAIM) -> str:
    """The `Afirmación (extracto)` cell, cut at a **safe** boundary (#274b, #257c).

    Truncating is legal here and only here (#226: the extract's anchor lives in the note, not in the
    cell), but the cut must not fall inside `$…$`, a backtick span or a `[[wikilink]]`: measured on a
    real note, 10 of 88 rows were cut mid-formula and left an odd `$`, and a split `[[` is a lint
    blocker. The cut retreats to the last safe word boundary; if there is none —the whole prefix is
    one long span— the text is returned **whole**, because a broken cell is worse than a long one."""
    t = str(texto or "").strip()
    if len(t) <= limite:
        return t
    corte = next((i for i in range(limite, 0, -1)
                  if _cut_is_safe(t, i) and t[i - 1].isspace()), 0)
    if not corte:
        return t
    return t[:corte].rstrip() + "…"


def verdict_chain(verdict: str) -> list:
    """The verdicts a cell records, in order — `no-soportada→contradice→corregida` gives two (#274c).

    The notation carries one arrow per round. With a single arrow the cell cannot tell «one round
    corrected it» from «three rounds fought over it»: measured on a note that ran **eight** rounds,
    13 bad verdicts were issued and 11 reached the block. Reading the chain is what lets a consumer
    count rounds; the partition of `verif_counts` still keys on the **first** verdict, which is the
    one that says what the note actually did wrong."""
    partes = [x.strip(_ADORNO).strip() for x in _RESOLUCION_SEP.split(str(verdict or "").lower())]
    return [x for x in partes if x in VERDICTS]


#: Las cinco columnas de la tabla de una vista. Las escribe `harvest_views.render_view` y las lee
#: `second_hand_rows`: una sola definición, o el lector y el escritor divergen (regla de método 2).
VISTA_COLS = ("Qué", "Valor", "Localizador", "Régimen", "Segunda mano")

_VISTA_HEAD_RE = re.compile(r"^## Vista\b", re.M)


def second_hand_rows(text: str) -> list:
    """`(qué, valor, a quién)` for every view row whose *Segunda mano* cell is populated (#279).

    #103 asks the extraction to mark a value the source attributes to someone else — it is the #1
    measured error mechanism — and nothing checked the mark survived into the star note. Measured on
    a real note: 4 values lost it, one of them used as **independent corroboration** of itself.

    Indexed by column NAME, never by position: an older note may carry the pre-#195 `Línea` header,
    and a row with an unescaped pipe shifts every column to its right."""
    out: list = []
    dentro, cols = False, None
    for linea in str(text or "").split("\n"):
        if linea.startswith("## "):
            dentro, cols = bool(_VISTA_HEAD_RE.match(linea)), None
            continue
        if not dentro or not linea.strip().startswith("|"):
            if not linea.strip().startswith("|"):
                cols = None
            continue
        celdas = split_row(linea)
        if cols is None:
            cols = [c.strip().lower() for c in celdas]
            continue
        if _SEP_ROW_RE.match(linea.strip()) or len(celdas) != len(cols):
            continue
        try:
            i_q, i_v, i_s = (cols.index("qué"), cols.index("valor"),
                             next(j for j, c in enumerate(cols) if "segunda mano" in c))
        except (ValueError, StopIteration):
            continue
        if (de := celdas[i_s].strip()) and de not in ("—", "-", "–"):
            out.append((celdas[i_q], celdas[i_v], de))
    return out


def render_verif_row(row) -> str:
    r"""The canonical markdown line for one `Row`, with **every cell escaped** (#240/#284).

    The `Fuente` cell is written as the `[[wikilink]]` the parser reads back, and the hash cell
    recomposes its prefix. Escaping is `cfg.escape_cell`, the same one the view harvester uses:
    inside `$…$` a bar is `\vert`, outside it is `\|`."""
    celdas = (str(row.n), truncate_claim(row.claim), f"[[{row.bibcode}]]" if row.bibcode else "",
              row.verdict, row.evidence, row.anchor, _hash_cell(row), row.condition or "—")
    for c in celdas:
        # #274a — la salida estructurada del fan-out serializada con `repr()` en vez de convertida a
        # prosa: al lector le llegan los corchetes, los `', '` y los apóstrofos escapados. Medido en
        # dos filas de una ficha real, y el daño no es sólo estético: `\'` NO es un escape de
        # markdown, así que Python-Markdown imprime la barra y markdown-it se la come — la misma
        # celda se lee distinto según el parser. La red es la de #240: un `assert` en el punto que
        # arma la fila, que es el único lugar por donde pasa toda celda.
        if str(c or "").lstrip().startswith(("['", '["')):
            raise ValueError(f"celda con un `repr()` de lista de Python: «{str(c)[:60]}…» — la "
                             f"salida del fan-out se convierte a PROSA, no se vuelca")
    return "| " + " | ".join(cfg.escape_cell(str(c or "").strip()) or "—" for c in celdas) + " |"


def verif_roundtrip_errors(rows: list, tabla: str) -> list:
    """What a written table loses when read back. `[]` means the round trip is faithful.

    The cheap net of #222 applied to #284: **count and compare, do not trust the writer**. It checks
    the row count and, per row, the four cells a broken row silently shifts —anchor, source hash,
    verdict and bibcode—, which is exactly what the measured defect corrupted while leaving the row
    visibly present."""
    leidas = parse_verif_table(f"{VERIFY_HEADER}\n\n{tabla}\n")
    if leidas is None:
        return ["el bloque escrito no se puede parsear (¿faltan las columnas de hash?)"]
    if len(leidas) != len(rows):
        return [f"se escribieron {len(rows)} filas y se leen {len(leidas)}"]
    errores = []
    for esperada, leida in zip(rows, leidas):
        for campo in ("anchor", "verdict", "bibcode"):
            if str(getattr(leida, campo) or "") != str(getattr(esperada, campo) or ""):
                errores.append(f"fila {esperada.n}: `{campo}` se escribió "
                               f"«{getattr(esperada, campo)}» y se lee «{getattr(leida, campo)}» "
                               f"— ¿una barra sin escapar corrió las columnas?")
        if _hash_cell(leida) != _hash_cell(esperada):
            errores.append(f"fila {esperada.n}: `Hash fuente` se escribió «{_hash_cell(esperada)}» "
                           f"y se lee «{_hash_cell(leida)}»")
    return errores


def render_verif_table(rows: list) -> str:
    """The whole table —header, separator and rows— escaped, **round-trip checked** (#284).

    ⛔ Raises `ValueError` if reading it back does not reproduce what was written. Returning a
    corrupted block would reproduce the measured defect: the row stays visible, the lint keeps
    counting it, and what breaks is the anchor — the silent direction."""
    lineas = ["| " + " | ".join(VERIF_COLS) + " |",
              "|" + "---|" * len(VERIF_COLS)]
    lineas += [render_verif_row(r) for r in rows]
    tabla = "\n".join(lineas)
    errores = verif_roundtrip_errors(rows, tabla)
    if errores:
        raise ValueError("el bloque escrito no se lee como se escribió — no se publica:\n  "
                         + "\n  ".join(errores))
    return tabla


# ── #282 · re-anclaje: qué se re-verifica y qué sólo cambió de ancla ─────────────────────────────
#
# El ciclo de #203 —corregir → re-verificar— **no converge** con el ancla a nivel de bloque: tocar
# una cláusula vence TODOS los pares de su párrafo, así que cada ronda produce un subconjunto del
# tamaño de la anterior. Medido sobre una ficha real en un `audit-note` completo: **63 → 76 → 78**.
#
# Lo que faltaba no era otra ronda: era distinguir dos cosas que hoy vencen igual.
#   · la corrección que **cambia lo que la afirmación dice** → el veredicto no vale más, se re-verifica;
#   · la corrección **derivada de la propia verificación** —el texto nuevo son las palabras que el
#     verificador sacó de la fuente, con su página— → el texto quedó MÁS anclado que antes, y
#     re-preguntarle al juez si confirma su propio dictamen no es verificación.
# Medido en la misma pasada: de 78 pares vencidos, **72 eran del segundo tipo**.
#
# ⛔ Esto NO afloja el ancla (#224: emitir por línea deja reescribir el medio de una cita sin que el
# par se venza, y el sub-disparo es la única dirección de error que el módulo prohíbe). El ancla
# sigue siendo de bloque; lo que se agrega es **saber a qué fila corresponde cada par después de
# editar**, para poder llevar el veredicto en vez de tirarlo.

_LINK_FULL_RE = re.compile(r"\[\[[^\]]*\]\]")   # el wikilink ENTERO: acá se borra, no se captura
_PALABRA_RE = re.compile(r"[^\W\d_]{4,}|\d+[\d.,]*", re.UNICODE)


def claim_tokens(text: str) -> set:
    """Comparable tokens of a claim: words of 4+ letters, plus numbers.

    `[[wikilink]]`s are dropped —they do not discriminate, every pair of the same source carries
    them— and markup is ignored by construction (the regex only takes letters and digits), so
    **emphasis and punctuation cannot move the result**: the lesson of #168 and #276, where two
    detectors turned out blind to the adornment."""
    return set(_PALABRA_RE.findall(_LINK_FULL_RE.sub(" ", text or "").casefold()))


def match_rows_to_pairs(pairs: list, rows: list, umbral: float = 0.60) -> tuple:
    """Match the body's pairs against the block's rows. `(assigned, unmatched, orphans)`.

    Two routes, in order: **identical anchor** (the pair was not touched) and, failing that,
    **coverage of the row's extract by the current block** — what fraction of what the row claims to
    have verified is still in the text. Coverage rather than Jaccard, deliberately: the `Afirmación`
    cell is truncated by contract (#226 allows cutting **only** that column), so the current block
    almost always holds MORE text than the extract, and Jaccard would penalise precisely the pair
    that survived best.

    ⛔ Matching happens **within one `bibcode` only**: a pair is (claim, source), and carrying a
    verdict across sources would fabricate the very misattribution this framework measures as its
    dominant failure mode. Each row is consumed once.

    ⚠ **It decides nothing**: it returns the pairing. Who writes it, and with what declaration, is
    the caller's business — same doctrine as `--drop-core`, which records and proposes (#212).
    """
    por_bib: dict = {}
    for r in rows:
        por_bib.setdefault(r.bibcode, []).append(r)
    usadas, asignado, sin_fila = set(), {}, []
    # primero las anclas intactas, para que un par sin tocar no se quede sin su propia fila
    pendientes = []
    for p in pairs:
        exacta = next((r for r in por_bib.get(p.bibcode, [])
                       if r.anchor == p.anchor and id(r) not in usadas), None)
        if exacta is not None:
            asignado[p] = (exacta, 1.0); usadas.add(id(exacta))
        else:
            pendientes.append(p)
    for p in pendientes:
        cur = claim_tokens(p.block.text)
        mejor, score = None, 0.0
        for r in por_bib.get(p.bibcode, []):
            if id(r) in usadas:
                continue
            q = claim_tokens(r.claim)
            s = len(cur & q) / len(q) if q else 0.0
            if s > score:
                mejor, score = r, s
        if mejor is not None and score >= umbral:
            asignado[p] = (mejor, score); usadas.add(id(mejor))
        else:
            sin_fila.append(p)
    return asignado, sin_fila, [r for r in rows if id(r) not in usadas]
