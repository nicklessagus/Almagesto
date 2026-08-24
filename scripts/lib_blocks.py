"""Partición de una nota en bloques citables + los dos hashes del ancla (D-4 / D-20, INV-78).

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

Medido con ESTE módulo sobre Almagesto-RV (25 notas de entidad, papers excluidos): **1.205 pares**
— 756 en ítems, 264 en párrafos, 176 en filas, 9 en blockquotes. De esos, **1.070 citan por su
cuenta y 135 heredan**: la herencia agrega 11%, no es el caso dominante. El derrame máximo de un
ámbito es de 30 hijos (una tabla de keywords bajo un caption con una sola fuente) — legítimo, y el
tipo de caso para el que la herencia existe. (El plan de implementación citaba 761/560/141/54/6
para este corpus; esos números cuentan sólo los `[[bibcode]]` explícitos de otra población de
notas, no esta partición con herencia. Vale el número medido acá, que es el que produce el código
que corre.)

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

# Encabezado del bloque de auditoría. Se excluye de la partición: sus filas llevan `[[bibcode]]`
# pero son el REGISTRO de la verificación, no afirmaciones. Si entraran, el bloque se hashearía a
# sí mismo y cada re-verificación lo vencería sola — un lazo que nunca converge.
VERIFY_HEADER = "## Verificación de citas"

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


def sha10(text: str) -> str:
    """sha256 truncado a 10 hex. Puerta pública para que el llamador pase texto **ya leído**: el
    lint lee cada `.txt` para `is_legible` (77% de sus 5,6 s sobre 908 notas) y esa misma lectura
    alimenta el hash de fuente. Sin esto, agregar el hash duplicaría la parte más cara del lint."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def source_hash(path: Path) -> str:
    """Hash del `.txt` de fuente. Cuando el texto ya está en memoria, usar `sha10` directo."""
    return sha10(Path(path).read_text(encoding="utf-8", errors="replace"))


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
    if len(delims) < 2:
        return text, 0
    fin = delims[1].end()
    return text[fin:], text[:fin].count("\n")


def split_blocks(body: str) -> list[Block]:
    """Los bloques citables de una nota, en orden de aparición.

    Se excluyen, por no ser afirmaciones: el frontmatter (`thesis_links`, `disputes[].ref` — son
    contrato máquina, no prosa), los code fences (```dataview``` trae wikilinks dentro de la
    query), el bloque `## Verificación de citas` entero, los separadores `|---|---|` y la fila de
    **encabezado** de cada tabla. Los dos últimos heredarían la cita del caption y ensuciarían el
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
            # el bloque de verificación se saltea hasta el próximo encabezado
            en_verificacion = s.startswith(VERIFY_HEADER)
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
