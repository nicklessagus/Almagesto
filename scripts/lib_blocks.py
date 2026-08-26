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

LINK_RE = re.compile(r"\[\[([^\]\|#]+)")
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
                intro_actual = texto                  # este párrafo pasa a ser el ámbito vigente
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
            en_verificacion = any(s.startswith(h) for h in cfg.SECCIONES_ESTAMPADAS)
            intro_actual = None if en_verificacion else s.lstrip("# ").strip()
            continue
        if en_verificacion or not s:
            flush()
            continue
        if s.startswith(">"):
            flush()
            out.append(Block("blockquote", i, s.lstrip("> ").strip()))
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

# Columnas que hacen evaluable al bloque. Sin `ancla`/`hash` no hay dónde colgar los hashes (la
# plantilla pre-D-20 colapsaba las soportadas en prosa y dejaba una sola fila, la que falló). Sin
# `condición` el bloque es pre-1.39.0: registraba el veredicto y **tiraba** lo que la corrida había
# encontrado sobre el régimen —el output más valioso del fan-out, y el que las dos corridas del
# experimento producían distinto aun cuando el veredicto coincidía—.
_COLS_HASH = ("ancla", "hash", "condici")


def _split_row(line: str) -> list[str]:
    """Cells of a markdown table row, splitting only on **unescaped** pipes.

    A verbatim quote can carry a `|` of its own (a table row of the paper), and the generator
    escapes it `\\|` as markdown mandates. Splitting on a bare `|` turns that one cell into two and
    shifts every column to its right — including the anchor, which is then read from the wrong cell
    and makes the pair look stale against a source nobody touched.
    """
    #  @inv INV-99
    return [c.replace("\\|", "|").strip() for c in _CELL_SPLIT_RE.split(line.strip().strip("|"))]


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
        celdas = _split_row(ln)
        if len(celdas) <= max(i_n, i_claim, i_fuente, i_verd, i_ancla, i_hash, i_cond):
            continue                     # fila malformada: la reporta el lint como par sin cubrir
        if len(celdas) != len(cols):
            # Más celdas que el encabezado ⇒ hay un `|` sin escapar en alguna celda y las columnas
            # de la DERECHA (ancla, hash, condición) están corridas. Indexar por posición leería el
            # ancla de otra celda y el par volvería "vencido por edición" sin que nadie editara nada
            # (medido: 18 pares, 2026-08-25). Mejor par sin cubrir que ancla ajena.
            continue
        bibs = _bibcodes(celdas[i_fuente]) or [celdas[i_fuente].strip("[]")]
        kind, h = split_source_ref(celdas[i_hash])
        evid = celdas[i_evid] if i_evid is not None and i_evid < len(celdas) else ""
        out.append(Row(celdas[i_n], celdas[i_claim], bibs[0], celdas[i_verd],
                       celdas[i_ancla], h, celdas[i_cond], kind, evid))
    return out
