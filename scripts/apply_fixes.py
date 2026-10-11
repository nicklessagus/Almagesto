#!/usr/bin/env python3
"""Apply the corrections a `verify-citations` fan-out produced, to the note they belong to (#197).

    python scripts/apply_fixes.py <nota.md> <dir-de-fixes> [--write]

Until 1.70.0 this step **did not exist**. The skill says how to *redact* a correction — «a finding
tells you WHERE to look, not WHAT to write» — and nothing about how to *apply* seventy-five of them.
Doing it by hand does not scale, and a naive `text.replace` corrupts the note. Both failure modes
are measured on a real run (concept `ica`, 75 corrections):

**Collision.** An item of `## Huecos` citing several sources is handed to *each* of those sources'
correctors, so two or three fixes arrive carrying the SAME `viejo`. Chained, the second anchors on
what the first left behind and the item ends up with a fragment of the previous one dangling — that
is corrupt prose under a heading that reads as verified, which is exactly what the verification
layer exists not to produce. Measured: 5 fixes over 2 items. Merging two corrections is **judgment,
not mechanics**, so this refuses to do it: it names the collision and asks for an explicit merge,
declared under the `_fusionados` bibcode, which wins and skips the originals.

**Fused blocks (#222).** `find_block` used to call a block «a run of contiguous non-empty lines»
while `lib_blocks.split_blocks` —which produces the pairs, the anchors and the very text the
corrector saw— splits a list or a table into one block per item/row. A `viejo` spanning several
items resolved anyway and came back as a single paragraph (or a single row). Measured: pairs fell
from 96 to 89, bullets of `## Huecos` fused, rows of two tables collapsed into each other, and
**nothing said so**. Today a `viejo` covering more than one `lib_blocks` block is refused, every fix
is located against the ORIGINAL text before anything is mutated (so a row fix and a table fix on the
same table no longer break each other), overlapping spans are refused, and the run aborts if
`pairs_of` came out lower than it went in — a correction cannot make a cited claim disappear.

**Multi-line block.** The corrector redacts from the text `lib_blocks.split_blocks` hands it, which
**normalises** the block by joining its lines with a space; in the file that same block is wrapped
at column 100. `replace` finds 0 occurrences. Measured: 14 of 75 — every list item and paragraph;
table rows, being one line, applied fine. So a block is located by its *normalised* form and
rewritten re-wrapped, keeping the item's indentation.

**Deleting a block (#568)** is `nuevo: null` with `retira` equal to ALL the block's bibcodes: the
block leaves with its separating blank line and pairs drop by exactly `|retira|`. `""` and `[]` do
not delete (the first fails the block count, the second is refused in favour of `null`).

**Inserting and moving (#578)** are the two verbs a replacement cannot express, so they used to
happen by hand, outside the pair net. Both locate their anchor the way `viejo` is located (a whole
`lib_blocks` block, a table row, or a heading line):

- `{"n", "despues_de": <ancla>, "nuevo": [bloques]}` INSERTS after the anchor. After a table row
  (or its header) every element must be ONE row with as many cells as the header, written verbatim;
  after anything else they are blocks, separated by a blank line. Pairs must rise by AT LEAST the
  pairs of the inserted blocks themselves, and what enters is reported (#389/#406).
- `{"n", "mover": <bloque>, "despues_de": <ancla>}` MOVES a block byte for byte (a row goes after a
  row of a table with the same column count). Pairs may not drop, and a block whose inherited
  citation scope changed — a row under another caption, a list item under another paragraph — is
  reported, as is any untouched block whose scope an insertion changed.

Nothing is written unless every fix resolves: a replacement that guesses is worse than one that
fails. Application runs back-to-front so earlier line indices stay valid.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_config as cfg  # noqa: E402
import lib_blocks as lb  # noqa: E402

MERGED = "_fusionados"
"""Bibcode reserved for hand-merged fixes: they win, and the originals they replace are skipped."""

WIDTH = 100
LOOKAHEAD = 60
"""How many lines a single block may span. Beyond that it is not a block, it is a section."""


@dataclass
class Result:
    applied: int = 0
    exact: int = 0
    by_block: int = 0
    failed: list = field(default_factory=list)
    collisions: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    pairs_before: int = 0
    pairs_after: int = 0
    added: list = field(default_factory=list)      # #389 · (bib, n, [bibcodes que el fix AGREGÓ])
    grown: list = field(default_factory=list)      # #406 · (bib, n, +chars) — creció SIN citas nuevas
    split: list = field(default_factory=list)      # #408 · (bib, n, k) — un bloque partido en k
    retired: list = field(default_factory=list)    # #527 · (bib, n, [bibcodes retirados, declarados])
    deleted: list = field(default_factory=list)    # #568 · (bib, n) — bloque borrado (`nuevo: null`)
    inserted: list = field(default_factory=list)   # #578 · (bib, n, bloques, +pares, [bibcodes])
    moved: list = field(default_factory=list)      # #578 · (bib, n, línea destino)
    rescoped: list = field(default_factory=list)   # #578 · (extracto, [bibcodes que heredaba])


#: #406 · a partir de cuántos caracteres NETOS un fix «agrega material» aunque no gane citas.
#: Medido: el empalme que #406 midió agregó ~90 caracteres de prosa y cero `[[bibcode]]`, y el
#: aviso de #389 —que sólo mira citas— quedó mudo. Cuarenta es la mitad de eso y más que cualquier
#: corrección de un número o una palabra; NO bloquea, igual que #389: a veces agregar es el arreglo.
CRECE_MIN_CHARS = 40

#: #527 · lo que en `lib_blocks.split_blocks` abre un bloque si queda al INICIO de una línea.
OPENS_BLOCK_RE = re.compile(r"(?:[-*+]|\d+\.)\s|[|>#]|```")
MATH_RE = re.compile(r"\$[^$\n]+\$")
PARA_BREAK_RE = re.compile(r"\n[ \t]*\n")


def normalise(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


QUOTE_RE = re.compile(r"^(\s*(?:>\s?)+)")


def quote_prefix(line: str) -> str:
    """The blockquote marker(s) a line opens with (`"> "`, `"> > "`), or `""`.

    AUD-141 — `lib_blocks.split_blocks` hands the corrector the block **without** its markers, so
    the `viejo` it sends back has none either, while the file lines still carry them. Matching the
    raw lines meant a blockquote could never be located: the fix always landed in `failed`, and
    since `failed` aborts the whole run, ONE quoted claim blocked all seventy-five corrections."""
    m = QUOTE_RE.match(line)
    return m.group(1) if m else ""


def _bare(line: str) -> str:
    """The line's text without its blockquote markers — what the corrector actually saw."""
    return line[len(quote_prefix(line)):]


def load_fixes(fix_dir: Path) -> tuple[list, list]:
    """Every fix in the directory plus what the correctors explicitly refused to correct.

    A rejection is a first-class outcome, not an absence: it means someone opened the source and
    found the finding wrong. Losing it would make the next run re-propose the same thing.
    """
    fixes, rejected = [], []
    for f in sorted(fix_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        bib = data.get("bibcode") or f.stem
        for r in data.get("rechazados", []):
            rejected.append((bib, r.get("n"), r.get("motivo")))
        for fx in data.get("fixes", []):
            # #578 — three verbs: replace (`viejo`), insert (`despues_de` alone), move (`mover`).
            if "mover" in fx:
                verb, old, new = "move", fx["mover"], fx.get("nuevo", MOVE)
            elif "viejo" not in fx and "despues_de" in fx:
                verb, old, new = "insert", None, fx["nuevo"]
            else:
                verb, old, new = "replace", fx["viejo"], fx["nuevo"]
            fixes.append((bib, fx["n"], old, new, fx.get("retira") or [], fx.get("despues_de"),
                          verb))
    return fixes, rejected


MOVE = object()
"""`nuevo` of a move fix: a move carries no new text, it re-emits the block's own lines."""


def claim_key(old, after, verb) -> str:
    """What a fix claims, for the collision check: the block it rewrites or moves, or the point
    after which it inserts (#578: two insertions after one anchor go in ONE list)."""
    return normalise(old) if verb != "insert" else "+ " + normalise(after)


def locate(lines: list, blocks: list, text: str, field_name: str = "viejo"):
    """`(span, exact, error)` for a whole block given as text: one identical line, else a
    `block_hits` match covering exactly one `lib_blocks` block (#222/#547)."""
    idx = [k for k, l in enumerate(lines) if l == text]
    if len(idx) == 1:
        return (idx[0], idx[0] + 1), True, None
    hits = block_hits(lines, text)
    if len(hits) > 1:
        # #547 — dos bloques idénticos comparten ancla: no es un fragmento mal cortado, es que
        # el texto no alcanza para decir cuál. Adivinar sería peor que rehusar.
        donde = ", ".join(f"L{a + 1}" for a, _ in hits)
        return None, False, (f"`{field_name}` aparece {len(hits)} veces idéntico ({donde}): "
                             "bloques idénticos comparten ancla y no se sabe cuál "
                             "corregir — hacelos distintos (la celda o frase que los "
                             "diferencia) y re-verificá")
    if not hits:
        return None, False, (f"el bloque no se pudo localizar (0 candidatos) — `{field_name}` "
                             "debe ser un bloque ENTERO tal como lo parte "
                             "`lib_blocks.split_blocks`, no un fragmento sub-línea")
    cubiertos = blocks_within(blocks, hits[0])
    if len(cubiertos) > 1:
        return None, False, (f"`{field_name}` abarca {len(cubiertos)} bloques de "
                             f"`lib_blocks` (ítems de lista o filas de tabla): "
                             f"aplicarlo los FUNDE en uno y se pierden "
                             f"{len(cubiertos) - 1} par(es) verificable(s). Mandá un "
                             f"fix por bloque.")
    return hits[0], False, None


def is_row(line: str) -> bool:
    """Is `line` a table row (blockquote markers aside)? (#578)"""
    return _bare(line).lstrip().startswith("|")


def insertion_point(lines: list, span: tuple) -> tuple:
    """`(line index to insert at, header cell count or None)` after the anchor `span` (#578).

    After a table row the insertion stays inside the table, with no blank line; after the header
    (or the separator) it goes below the separator, never between the two. After anything else it
    goes right after the block."""
    a, j = span
    if not is_row(lines[a]):
        return j, None
    h = a
    while h > 0 and is_row(lines[h - 1]):
        h -= 1
    return (max(j, h + 2) if a <= h + 1 else j), cfg._n_cells(_bare(lines[h]))


def row_errors(rows: list, cells) -> str | None:
    """Why `rows` cannot go into a table whose header has `cells` cells, or None (#578)."""
    if cells is None:
        if any(is_row(r) and "\n" not in str(r).strip() for r in rows):
            return ("una fila suelta se inserta DESPUÉS de una fila (o del encabezado) de su "
                    "tabla: fuera de una tabla es una tabla sin encabezado, que no renderiza")
        return None
    for r in rows:
        r = str(r).strip()
        if "\n" in r or not r.startswith("|") or lb._SEP_ROW_RE.match(r):
            return f"dentro de una tabla cada elemento es UNA fila de datos: {r[:60]!r}"
        if cfg._n_cells(r) != cells:
            return (f"la fila tiene {cfg._n_cells(r)} celdas y el encabezado {cells}: un `|` sin "
                    f"escapar (`\\|`, o `\\vert` dentro de `$…$`) parte la celda — {r[:60]!r}")
    return None


def with_separator(lines: list, span: tuple) -> tuple:
    """`span` plus the blank line that separated the block, when the block leaves (#568/#578):
    without it two blank lines are left in a row. A row inside its table has none to take."""
    if (span[1] < len(lines) and not lines[span[1]].strip()
            and (span[0] == 0 or not lines[span[0] - 1].strip())):
        return span[0], span[1] + 1
    return span


def heir_scopes(text: str, skip: list) -> dict:
    """`{(normalised block, inherited bibcodes): count}` for blocks that inherit their citation,
    leaving out those that start inside a `skip` span (#578: blocks whose text a fix rewrites)."""
    out: dict = {}
    for b in lb.split_blocks(text):
        if b.intro is None or any(i <= b.first_line - 1 < j for i, j in skip):
            continue
        k = (normalise(b.text), tuple(lb._bibcodes(b.intro)))
        out[k] = out.get(k, 0) + 1
    return out


def block_hits(lines: list, old: str) -> list:
    """Every half-open line range whose joined, normalised text is `old` (#547: 0 and >1 differ).

    ⚠ Skipping a blank start line is an **atajo, not behaviour**, and `--guardas` reports it as a
    survivor on purpose: the inner `break` already covers it.
    """
    target = normalise(old)
    hits = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        acc = []
        for j in range(i, min(i + LOOKAHEAD, len(lines))):
            s = _bare(lines[j]).strip()        # AUD-141: sin los `>` del blockquote
            if not s:
                break
            acc.append(s)
            if normalise(" ".join(acc)) == target:
                hits.append((i, j + 1))
                break
    return hits


def verbatim(block: str) -> bool:
    """#537 — `block` is structure, not prose: its lines are written as they come, never re-wrapped.

    A table, a blockquote, a code fence or `$$…$$`: joining their lines with a space is not a
    reflow, it destroys them (a table in ONE line does not render; a blockquote loses its inner
    `>`). The kind is `lib_blocks.split_blocks`'s own (`Block.kind`); a fence yields no block at all
    and `$$` reads as a paragraph there, so those two are named here."""
    s = str(block).strip()
    return (s.startswith(("```", "$$"))
            or any(b.kind in ("fila", "blockquote") for b in lb.split_blocks(s)))


def rewrap(new, first_line: str) -> list:
    """Re-wrap keeping the block's indentation: a list item's continuations stay indented.

    ⛔ #408 — `new` may be a LIST of blocks: the fix that PARTS one block into several («un bloque,
    un hecho»). Each is re-wrapped on its own with a blank line between, so `split_blocks` reads
    them back as separate blocks and every one keeps its own pair. A single string is one block, as
    before; a string with a blank line inside is NOT a split: `apply` REFUSES it (#527 —
    it used to be collapsed here in silence), because a corrector that meant two blocks says so
    with a list. ⛔ #527 — it never breaks inside `$…$` nor before a token that opens a block.

    ⛔ AUD-141 — **a table row is never wrapped.** Wrapping one at column 100 splits it across
    several lines and the table stops being a table: the `## Verificación de citas` block, whose
    rows carry the anchors, would be destroyed by the very step that exists to keep it honest. A
    row applies as ONE line, however long. Blockquotes keep their `>` markers, which the matcher
    strips to compare and this puts back.

    ⛔ #537 — the re-wrap is for PROSE only: a `verbatim` block (table, blockquote, fence, `$$`)
    is written as it comes, line by line, with the block's own `>`/indentation put back. A table
    row is the one-line case of the same rule."""
    if isinstance(new, list):
        out: list = []
        for i, bloque in enumerate(new):
            if i:
                out.append("")                            # línea en blanco: dos bloques, no uno
            out += rewrap(bloque, first_line)
        return out
    quote = quote_prefix(first_line)
    bare = _bare(first_line)
    indent = re.match(r"\s*", bare).group(0)
    stripped = bare.lstrip()
    if verbatim(new):                               # #537: estructura, no prosa (una fila, UNA línea)
        return [quote + indent + ln.rstrip() for ln in str(new).strip("\n").split("\n")]
    bullet = bool(re.match(r"([-*+]|\d+\.)\s", stripped))
    cont = indent + ("  " if bullet else "")
    # #527 — `$…$` viaja con sus espacios como NUL durante el wrap; una línea que abriría un
    # bloque se pega a la anterior, aunque pase del ancho.
    texto = MATH_RE.sub(lambda m: m.group(0).replace(" ", "\0"), normalise(new))
    envuelto: list = []
    for ln in textwrap.wrap(texto, width=WIDTH - len(quote), initial_indent=indent,
                            subsequent_indent=cont, break_long_words=False, break_on_hyphens=False):
        if envuelto and OPENS_BLOCK_RE.match(ln.lstrip()):
            envuelto[-1] += " " + ln.lstrip()
        else:
            envuelto.append(ln)
    envuelto = [ln.replace("\0", " ") for ln in envuelto]
    return [quote + ln for ln in envuelto] if quote else envuelto


def blocks_within(blocks: list, span: tuple) -> list:
    """The `lib_blocks` blocks that start inside a half-open line span (0-indexed).

    #222 — the guard that was missing. `find_block` (now `block_hits`) called a block «a run of contiguous non-empty
    lines»; `lib_blocks.split_blocks` —which is what produces the PAIRS, the ANCHORS and the text
    the corrector actually saw— splits a list or a table into one block per item/row. So a `viejo`
    spanning several items resolved fine and `rewrap` rewrote them as a SINGLE paragraph (or, if it
    started with `|`, a single row). Measured on a real note: pairs fell from 96 to 89 — seven
    cited claims stopped existing as verifiable pairs, bullets of `## Huecos` were fused, and rows
    of two tables collapsed into each other. That is exactly the corruption this module exists to
    prevent, produced by this module.
    """
    return [b for b in blocks if span[0] <= b.first_line - 1 < span[1]]


def apply(note: Path, fix_dir: Path, *, write: bool = False) -> Result:
    """Apply every fix, or none. See the module docstring for the failure modes this guards."""
    #  @inv INV-137
    res = Result()
    pending, res.rejected = load_fixes(fix_dir)

    # A hand-merged fix wins over the originals it replaces — they targeted the same block.
    def key(x):
        return claim_key(x[2], x[5], x[6])
    merged = {key(x) for x in pending if x[0] == MERGED}
    res.skipped = [(x[0], x[1]) for x in pending if x[0] != MERGED and key(x) in merged]
    pending = [x for x in pending if x[0] == MERGED or key(x) not in merged]

    claims: dict = {}
    for x in pending:
        claims.setdefault(key(x), []).append((x[0], x[1]))
    res.collisions = [(who, k) for k, who in claims.items() if len(who) > 1]
    if res.collisions:
        return res

    text = note.read_text(encoding="utf-8")
    lines = text.split("\n")
    blocks = lb.split_blocks(text)
    res.pairs_before = len(lb.pairs_of(text))

    # #222 — EVERYTHING is located against the ORIGINAL text, and nothing is mutated until every
    # fix has a span. Until 1.87.0 step 1 replaced exact single-line matches by mutating `lines`
    # and step 2 ran `find_block` over the already-mutated text: a block containing a line step 1
    # had touched stopped resolving. It happened whenever a table got one ROW fix (exact) and one
    # TABLE fix (block) — no collision was declared, it simply failed and aborted all of them.
    planned = []                      # (span, bib, n, new, kind, retira)
    pares = lb.pairs_of(text)
    # #572 — rows deleted by this same batch do not count as orphaned by their caption's deletion.
    borradas = {k + 1 for _, _, o, nw, *_ in pending if nw is None
                for k, l in enumerate(lines) if l == o}
    for bib, n, old, new, retira, after, verb in pending:
        if verb == "replace" and after is not None:
            res.failed.append((bib, n, "`viejo` y `despues_de` juntos: reemplazar es `viejo` + "
                                       "`nuevo`; insertar, `despues_de` + `nuevo` (#578)"))
            continue
        if verb == "move" and (new is not MOVE or after is None or retira):
            res.failed.append((bib, n, "mover es `mover` + `despues_de`, sin `nuevo` ni `retira`: "
                                       "el bloque viaja byte a byte (#578)"))
            continue
        if verb != "replace":
            # ⛔ #578 — insertar y mover: los dos verbos que un reemplazo no expresa, y que por eso
            # se hacían a mano, fuera de la red de pares (#222) y del aviso de material (#389).
            anc, _, err = locate(lines, blocks, after, "despues_de")
            if err:
                res.failed.append((bib, n, err))
                continue
            punto, celdas = insertion_point(lines, anc)
            if verb == "move":
                span, _, err = locate(lines, blocks, old, "mover")
                if err:
                    res.failed.append((bib, n, err))
                    continue
                mueve = lines[span[0]:span[1]]                # byte a byte, sin re-envolver
                if is_row(mueve[0]) != (celdas is not None):
                    res.failed.append((bib, n, "una fila se mueve después de una fila de tabla, y "
                                               "un bloque de prosa fuera de una tabla (#578)"))
                    continue
                err = row_errors(mueve, celdas) if celdas is not None else None
                if err:
                    res.failed.append((bib, n, err))
                    continue
                planned.append((with_separator(lines, span), bib, n, None, "move_out", []))
                planned.append(((punto, punto), bib, n,
                                mueve if celdas is not None else [""] + mueve, "move_in", []))
                continue
            elementos = new if isinstance(new, list) else [new]
            if not elementos or any(e is None for e in elementos) or retira:
                res.failed.append((bib, n, "insertar es `despues_de` + `nuevo` (un bloque o una "
                                           "lista), sin `retira`: no sale nada (#578)"))
                continue
            err = row_errors(elementos, celdas)
            if err:
                res.failed.append((bib, n, err))
                continue
            planned.append(((punto, punto), bib, n, elementos,
                            "insert_row" if celdas is not None else "insert", []))
            continue
        if new == []:
            # #568 — una lista vacía «partía» el bloque en cero: sobre prosa borraba (sin decirlo
            # en ningún lado, con línea en blanco doble) y sobre una fila se rehusaba. Una forma.
            res.failed.append((bib, n, "`nuevo: []` no es una forma: para BORRAR el bloque usá "
                                       "`nuevo: null` con `retira` = sus bibcodes (#568)"))
            continue
        # ⛔ #527 — un párrafo nuevo dentro de un `str` se FUNDÍA en silencio: `rewrap` colapsa el
        # blanco, y ni #222 (los pares no bajan) ni #389/#406 lo veían. Dos bloques se piden con
        # una lista (#408); acá se rehúsa en las dos ramas.
        if new is not None and any(PARA_BREAK_RE.search(str(b))
                                   for b in (new if isinstance(new, list) else [new])):
            res.failed.append((bib, n, "`nuevo` trae una línea en blanco adentro: son DOS bloques "
                                       "y aplicarlo como texto los funde en uno. Usá una lista, "
                                       "un elemento por bloque (#408)"))
            continue
        span, exact, err = locate(lines, blocks, old)
        if err:
            res.failed.append((bib, n, err))
            continue
        if exact and new is not None:
            if isinstance(new, list):
                # #408 — partir vale para PROSA. Una fila de tabla partida en dos deja de ser una
                # fila; el corrector que quiere dos filas manda dos fixes con dos `viejo`. Un
                # párrafo de UNA línea sí se parte: va por la rama de bloque, que re-envuelve.
                if is_row(lines[span[0]]):
                    res.failed.append((bib, n, "`nuevo` es una lista (partir el bloque) sobre una "
                                               "FILA de tabla: partir vale para prosa; una fila se "
                                               "reemplaza por una fila (o dos fixes, dos `viejo`)"))
                    continue
                planned.append((span, bib, n, new, "block", retira))
                continue
            planned.append((span, bib, n, new, "exact", retira))
            continue
        if new is None:
            # ⛔ #568 — BORRAR un bloque es la otra cara de `retira` (#527): lo que sale se declara
            # entero. Sin esta forma, vaciar un `## Inventario por eje` se hacía por fuera del
            # escritor y sin la red de pares (medido: 30 filas citadas en tres conceptos).
            salen_bibs = {p.bibcode for p in pares if span[0] <= p.block.first_line - 1 < span[1]}
            if set(retira) != salen_bibs:
                res.failed.append((bib, n, f"`nuevo: null` borra el bloque: `retira` tiene que ser "
                                           f"EXACTAMENTE sus bibcodes {sorted(salen_bibs)}, no "
                                           f"{sorted(set(retira))} (#568)"))
                continue
            # #572 — a caption is the citation SCOPE of the rows below it: deleting it leaves them
            # unsourced. The pair net (#222) already refuses, but its generic message hid the cause.
            borrado = normalise("\n".join(lines[span[0]:span[1]]))
            herederos = [p for p in pares if p.block.intro is not None
                         and not span[0] <= p.block.first_line - 1 < span[1]
                         and p.block.first_line not in borradas
                         and normalise(p.block.intro) == borrado]
            if herederos:
                res.failed.append((bib, n, f"`nuevo: null` borra el ámbito de cita de "
                                           f"{len(herederos)} bloque(s) que heredan su `[[bibcode]]` "
                                           f"(desde L{herederos[0].block.first_line}): quedarían sin "
                                           f"fuente. Borralos también o dales su cita (#572)"))
                continue
            planned.append((with_separator(lines, span), bib, n, new, "delete", retira))
            continue
        planned.append((span, bib, n, new, "block", retira))

    # Dos fixes que tocan las mismas líneas no se pueden aplicar en cadena: el segundo anclaría en
    # lo que dejó el primero. Es la colisión de siempre vista desde el otro lado —acá los `viejo`
    # difieren, lo que se pisa son las LÍNEAS— y también se rehúsa en vez de adivinar.
    for a in range(len(planned)):
        for b in range(a + 1, len(planned)):
            (i1, j1), (i2, j2) = planned[a][0], planned[b][0]
            # #578 — two insertions at the same point have no order: one list, one fix.
            if (i1 < j2 and i2 < j1) or i1 == j1 == i2 == j2:
                res.failed.append((planned[b][1], planned[b][2],
                                   f"se solapa en las líneas {max(i1, i2) + 1}–{min(j1, j2)} con el "
                                   f"fix {planned[a][1]} par {planned[a][2]}"))

    # ⛔ #527 — un escritor que re-emite prosa devuelve la MISMA cantidad de bloques que se quiso
    # escribir: los del `viejo` por un `str`, uno por elemento de una lista. Medido: un corte de
    # `rewrap` que dejó `- CS^2$ [[bib]].` al inicio de línea abrió un ÍTEM que se llevó la cita,
    # y el párrafo quedó con la fórmula sin cita y un `$` suelto — los pares, 212 → 212.
    reemplazos = {}
    for span, bib, n, new, kind, _ in planned:
        if kind in ("delete", "move_out", "move_in", "insert_row"):
            # #578 — una fila insertada se escribe tal cual (ya validada contra el encabezado) y lo
            # movido viaja byte a byte: no hay re-emisión que pueda partir o fundir bloques.
            reemplazos[span] = {"delete": [], "move_out": [], "move_in": new,
                                "insert_row": [str(e).strip() for e in new or []]}[kind]
            continue
        repl = ([new] if kind == "exact" else [""] + rewrap(new, "") if kind == "insert"
                else rewrap(new, lines[span[0]]))
        # #537 — un elemento `verbatim` pide los bloques que él mismo es (una tabla, uno por fila).
        pedidos = (sum(len(lb.split_blocks(e)) if verbatim(e) else 1 for e in new)
                   if isinstance(new, list)
                   else len(lb.split_blocks("\n".join(lines[span[0]:span[1]]))))
        salen = len(lb.split_blocks("\n".join(repl)))
        if salen != pedidos:
            res.failed.append((bib, n, f"el texto re-emitido son {salen} bloque(s) de `lib_blocks` "
                                       f"donde se pidieron {pedidos}: un salto de línea abre un "
                                       f"bloque (`- `, `N. `, `|`, `>`, `#` al inicio) o funde dos"))
        reemplazos[span] = repl

    if res.failed:
        return res

    # #389 — el contador SIMÉTRICO de #222. Aquél rehúsa si los pares BAJARON; éste AVISA si un
    # bloque GANÓ citas: medido sobre 15 defectos de un concepto, 3 nacieron al corregir y los 3
    # entraron con material agregado (una cita de otra fuente al final del párrafo, una narración
    # sobre el segundo objeto, una atribución fabricada con cita verbatim y referente equivocado).
    # No bloquea: a veces agregar una cita ES el arreglo (una `inferencia` que pasa a hecho citado).
    retirables = 0
    for span, bib, n, new, kind, retira in planned:
        if kind in ("move_out", "move_in", "insert", "insert_row"):
            continue                       # #578: se reportan con sus pares, después de aplicar
        viejo_txt = "\n".join(lines[span[0]:span[1]])
        nuevo_txt = "\n".join(new) if isinstance(new, list) else (new or "")
        antes = set(lb._bibcodes(viejo_txt))
        # ⛔ #527 — SACAR una cláusula citada es la primera opción que manda #389, y la red de #222
        # lo rehusaba («fundió bloques»): no distinguía una fusión de un retiro. La fusión la caza
        # ahora el conteo de bloques; el retiro se DECLARA (`retira: [bibcode]`) y tiene que ser
        # verdad: sólo lo declarado puede bajar pares.
        falsos = ([] if kind == "delete"              # #568: ya cotejado contra los pares
                  else sorted(set(retira) - (antes - set(lb._bibcodes(nuevo_txt)))))
        if falsos:
            res.failed.append((bib, n, f"`retira` declara {falsos}, que no estaban en `viejo` o "
                                       f"siguen en `nuevo`"))
        elif retira:
            res.retired.append((bib, n, sorted(set(retira))))
            retirables += len(set(retira))
        # AUD-220 — en la rama «block» `new` es un `str`: `"\n".join(str)` une carácter por
        # carácter y ningún `[[…]]` sobrevive, así que el aviso callaba justo en la rama medida.
        entran = sorted(set(lb._bibcodes(nuevo_txt)) - antes)
        if entran:
            res.added.append((bib, n, entran))
        # #406 — el aviso de #389 sólo veía `[[bibcode]]` AGREGADOS, y la regla que la prosa
        # enuncia («llegan con material agregado») es más ancha: un empalme que agrega ~90
        # caracteres de prosa y cero citas pasaba mudo por acá, por `contrast --validar-todo` y por
        # `lint --cierre`. Se mide el crecimiento NETO en texto normalizado; no bloquea.
        delta = len(normalise(nuevo_txt)) - len(normalise(viejo_txt))
        if delta >= CRECE_MIN_CHARS and not entran:
            res.grown.append((bib, n, delta))
        if kind == "block" and isinstance(new, list) and len(new) > 1:
            res.split.append((bib, n, len(new)))
    if res.failed:
        return res
    # #578 — at one start line the block that leaves goes before the insertion that arrives there.
    for span, bib, n, new, kind, _ in sorted(planned, key=lambda x: (-x[0][0], x[0][0] == x[0][1])):
        lines[span[0]:span[1]] = reemplazos[span]
        if kind == "delete":
            res.deleted.append((bib, n))
        if kind == "exact":
            res.exact += 1
        elif kind != "move_out":                    # un movimiento cuenta una vez
            res.by_block += 1
    res.applied = res.exact + res.by_block

    # #222 — la red decisiva: una corrección NO puede hacer desaparecer una afirmación citada.
    # Es el mismo principio que el ancla —lo que la nota afirma tiene que seguir siendo contable—
    # y es lo único que habría cazado los siete pares perdidos sin que nadie los contara a mano.
    nuevo_texto = "\n".join(lines)
    pares_despues = lb.pairs_of(nuevo_texto)
    res.pairs_after = len(pares_despues)
    # ⛔ #578 — una inserción declarada SUBE los pares de los bloques que agrega (una fila sin cita
    # propia, los que hereda de su caption): ésos se suman al piso, así que la inserción no puede
    # tapar un par perdido en otro lado. Su posición final se corre por lo que cambió antes.
    insertados = 0
    for span, bib, n, new, kind, _ in planned:
        if kind not in ("insert", "insert_row", "move_in"):
            continue
        ini = span[0] + sum(len(reemplazos[o]) - (o[1] - o[0]) for o, *_ in planned
                            if o[1] <= span[0] and o != span)
        fin = ini + len(reemplazos[span])
        if kind == "move_in":
            res.moved.append((bib, n, ini + 1 + (reemplazos[span][0] == "")))
            continue
        dentro = [p for p in pares_despues if ini <= p.block.first_line - 1 < fin]
        insertados += len(dentro)
        res.inserted.append((bib, n, len(blocks_within(lb.split_blocks(nuevo_texto), (ini, fin))),
                             len(dentro), sorted({p.bibcode for p in dentro})))
    # #578 — un bloque intacto (o movido) que hereda su cita y cambió de ámbito: avisa, no bloquea.
    tocados = [sp for sp, *_, kind, _ in planned if kind in ("exact", "block", "delete")]
    antes_h, despues_h = heir_scopes(text, tocados), heir_scopes(nuevo_texto, [])
    res.rescoped = [(k[0][:80], list(k[1])) for k, c in antes_h.items()
                    if despues_h.get(k, 0) < c]
    if res.pairs_after < res.pairs_before - retirables + insertados:
        res.failed.append(("_pares", 0, f"la aplicación deja {res.pairs_after} pares donde había "
                                        f"{res.pairs_before} ({retirables} retirado(s) declarado(s), "
                                        f"{insertados} insertado(s)): "
                                        f"alguna corrección fundió bloques o sacó una cita sin "
                                        f"declararla en `retira` (#527). NO se escribe."))
        res.applied = 0
        return res

    if write:
        # AUD-140 — `note.write_text` escribía en `vault/` sin pasar por el único writer del repo:
        # sin tmp+rename un corte deja la nota a medias (INV-90, medido con `ulimit -f`: 16.071 B
        # → 8.192 B sobre una nota con extracción LLM), y la fixture `sin_tocar_la_boveda_real`
        # —que intercepta a `lib_config`— no lo veía pasar.
        cfg.write_text_atomic(note, nuevo_texto)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("nota", type=Path)
    ap.add_argument("fixes", type=Path, help="directorio con los JSON del fan-out de correctores")
    ap.add_argument("--write", action="store_true",
                    help="escribir; sin esto es un dry-run (el default, deliberado)")
    args = ap.parse_args(argv)

    res = apply(args.nota, args.fixes, write=args.write)
    for bib, n, motivo in res.rejected:
        print(f"  ⊘ {bib} par {n}: {motivo}")
    if res.skipped:
        print(f"  fusionados a mano — se saltean los originales: {res.skipped}")
    if res.collisions:
        print(f"⛔ {len(res.collisions)} bloque(s) con más de un fix. Fusionalos a mano en un JSON con "
              f"`\"bibcode\": \"{MERGED}\"` y volvé a correr. NO se escribió nada:")
        for who, key in res.collisions:
            print(f"   {who}\n     {key[:120]}…")
        return 1
    print(f"exactos: {res.exact}   por bloque: {res.by_block}   fallan: {len(res.failed)}"
          + (f"   pares: {res.pairs_before} → {res.pairs_after}" if res.pairs_before else ""))
    for bib, n, motivo in res.failed:
        print(f"  ⛔ {bib} par {n}: {motivo}")
    for bib, n, entran in res.added:
        print(f"  ⚠ {bib} par {n}: el fix AGREGA {', '.join(f'[[{b}]]' for b in entran)} al bloque "
              f"que repara. Los defectos nacidos al corregir llegan con material agregado (#389): "
              f"¿es portante? La primera opción es SACAR la parte equivocada, no reescribirla.")
    for bib, n, delta in res.grown:
        print(f"  ⚠ {bib} par {n}: el bloque CRECE {delta} caracteres sin ganar citas (#406) — un "
              f"empalme que agrega prosa es exactamente lo que ninguna otra capa ve: releé el "
              f"bloque entero antes de escribir (¿el mismo hecho dos veces? ¿una unidad separada "
              f"de su número?).")
    for bib, n, bibs in res.retired:
        print(f"  ✂ {bib} par {n}: RETIRA {', '.join(f'[[{b}]]' for b in bibs)} del bloque "
              f"(declarado, #527) — esos pares salen; los que quedan en el bloque se re-verifican.")
    for bib, n in res.deleted:
        print(f"  ✂ {bib} par {n}: BORRA el bloque entero (`nuevo: null`, #568).")
    for bib, n, k, sube, bibs in res.inserted:
        print(f"  ✚ {bib} par {n}: INSERTA {k} bloque(s), +{sube} par(es)"
              + (f" ({', '.join(f'[[{b}]]' for b in bibs)})" if bibs else " SIN cita")
              + " (#578) — todo es material agregado (#389): ¿es portante? Los pares nuevos se "
                "verifican.")
    for bib, n, linea in res.moved:
        print(f"  ↪ {bib} par {n}: MUEVE el bloque, byte a byte, a la L{linea} (#578).")
    for extracto, bibs in res.rescoped:
        print(f"  ⚠ el bloque «{extracto}…» heredaba "
              + (", ".join(f"[[{b}]]" for b in bibs) or "un ámbito sin cita")
              + " y quedó bajo otro ámbito (#578): su par cambió de fuente — re-verificalo.")
    for bib, n, k in res.split:
        print(f"  ✂ {bib} par {n}: el bloque se PARTE en {k} (#408) — cada uno queda con su par; "
              f"los pares suben, nunca bajan.")
    if res.failed:
        print("⛔ NO se escribió nada: resolvé los que fallan primero.")
        return 1
    if args.write:
        print(f"✓ escrito {args.nota}")
    else:
        print("(dry-run — agregá --write para escribir)")
    return 0


if __name__ == "__main__":
    cfg.cli_exit(main)
