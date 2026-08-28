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

**Multi-line block.** The corrector redacts from the text `lib_blocks.split_blocks` hands it, which
**normalises** the block by joining its lines with a space; in the file that same block is wrapped
at column 100. `replace` finds 0 occurrences. Measured: 14 of 75 — every list item and paragraph;
table rows, being one line, applied fine. So a block is located by its *normalised* form and
rewritten re-wrapped, keeping the item's indentation.

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
            fixes.append((bib, fx["n"], fx["viejo"], fx["nuevo"]))
    return fixes, rejected


def find_block(lines: list, old: str) -> tuple | None:
    """The half-open line range whose joined, normalised text is `old`; `None` if 0 or >1 match."""
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
        if len(hits) > 1:
            return None
    return hits[0] if len(hits) == 1 else None


def rewrap(new: str, first_line: str) -> list:
    """Re-wrap keeping the block's indentation: a list item's continuations stay indented.

    ⛔ AUD-141 — **a table row is never wrapped.** Wrapping one at column 100 splits it across
    several lines and the table stops being a table: the `## Verificación de citas` block, whose
    rows carry the anchors, would be destroyed by the very step that exists to keep it honest. A
    row applies as ONE line, however long. Blockquotes keep their `>` markers, which the matcher
    strips to compare and this puts back."""
    quote = quote_prefix(first_line)
    bare = _bare(first_line)
    indent = re.match(r"\s*", bare).group(0)
    stripped = bare.lstrip()
    if stripped.startswith("|"):
        return [quote + indent + normalise(new)]        # una fila de tabla es UNA línea
    bullet = bool(re.match(r"([-*+]|\d+\.)\s", stripped))
    cont = indent + ("  " if bullet else "")
    envuelto = textwrap.wrap(normalise(new), width=WIDTH - len(quote), initial_indent=indent,
                             subsequent_indent=cont, break_long_words=False, break_on_hyphens=False)
    return [quote + ln for ln in envuelto] if quote else envuelto


def apply(note: Path, fix_dir: Path, *, write: bool = False) -> Result:
    """Apply every fix, or none. See the module docstring for the two failure modes this guards."""
    #  @inv INV-137
    res = Result()
    pending, res.rejected = load_fixes(fix_dir)

    # A hand-merged fix wins over the originals it replaces — they targeted the same block.
    merged = {normalise(v) for bib, _, v, _ in pending if bib == MERGED}
    res.skipped = [(b, n) for b, n, v, _ in pending if b != MERGED and normalise(v) in merged]
    pending = [x for x in pending if x[0] == MERGED or normalise(x[2]) not in merged]

    claims: dict = {}
    for bib, n, old, _ in pending:
        claims.setdefault(normalise(old), []).append((bib, n))
    res.collisions = [(who, key) for key, who in claims.items() if len(who) > 1]
    if res.collisions:
        return res

    lines = note.read_text(encoding="utf-8").split("\n")

    # 1) Exact, single-line matches first: they do not move anyone else's line indices.
    done = set()
    for bib, n, old, new in pending:
        idx = [k for k, l in enumerate(lines) if l == old]
        if len(idx) == 1:
            lines[idx[0]] = new
            done.add((bib, n))
            res.exact += 1

    # 2) The rest by block, applied back-to-front so the ranges computed above stay valid.
    located = []
    for bib, n, old, new in pending:
        if (bib, n) in done:
            continue
        span = find_block(lines, old)
        if span is None:
            res.failed.append((bib, n, "el bloque no se pudo localizar (0 o >1 candidatos)"))
        else:
            located.append((span, bib, n, new))
    for (i, j), bib, n, new in sorted(located, key=lambda x: -x[0][0]):
        lines[i:j] = rewrap(new, lines[i])
        res.by_block += 1

    res.applied = res.exact + res.by_block
    if res.failed:
        res.applied = 0
        return res
    if write:
        # AUD-140 — `note.write_text` escribía en `vault/` sin pasar por el único writer del repo:
        # sin tmp+rename un corte deja la nota a medias (INV-90, medido con `ulimit -f`: 16.071 B
        # → 8.192 B sobre una nota con extracción LLM), y la fixture `sin_tocar_la_boveda_real`
        # —que intercepta a `lib_config`— no lo veía pasar.
        cfg.write_text_atomic(note, "\n".join(lines))
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
    print(f"exactos: {res.exact}   por bloque: {res.by_block}   fallan: {len(res.failed)}")
    for bib, n, motivo in res.failed:
        print(f"  ⛔ {bib} par {n}: {motivo}")
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
