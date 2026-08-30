#!/usr/bin/env python3
"""Emit the re-verification subset of a note, and the re-anchoring proposal for the rest (#257, #282).

⛔ **Nothing here writes the note.** It reports and proposes; the writing is a separate, serial step.
Same doctrine as `--drop-core` and `triage --accept-source`: a script that edits curated content on
its own turns a decision into a side effect (#212).

Why it exists. `verify-citations` leaves a block of one row per (claim, `[[bibcode]]`) pair, anchored
to the **normalised markdown block**. Correcting a claim therefore expires **every pair of its
paragraph**, so the cycle of #203 —correct → re-verify— produces a new subset the size of the last
one. Measured on a real star note during a full `audit-note`: **63 → 76 → 78**. Nobody emitted that
subset either: it had to be scripted by hand each time (#257).

The fix is not another round. It is telling apart two things that expire identically today:

  · the correction that **changes what the claim says** → the verdict is void, it must be re-verified;
  · the correction **derived from the verification itself** —the new wording is the verifier's own
    quote, with its page— → the text ended up *more* anchored to the source than before, and asking
    the judge to confirm its own ruling is not verification.

Measured in the same pass: of 78 expired pairs, **72 were of the second kind**.

⚠ The split is a **proposal**, not a verdict: `match_rows_to_pairs` compares how much of the row's
(truncated, #226) extract survives in the current block. A high score means the claim is still
recognisably the same one; it does **not** prove the correction was faithful. Whoever accepts it
says so in the block — the round it came from, and that the text is post-correction.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_blocks as lb          # noqa: E402
import lib_config as cfg         # noqa: E402


def classify(text: str, umbral: float) -> dict:
    """The three buckets, from the note's own text. No I/O beyond the note.

    A note with no evaluable block sends **every** pair to the subset and says so: that is not
    "zero expired pairs", it is a block nobody can evaluate, and reporting it as clean would be the
    invented zero D-43 exists to forbid."""
    pares = lb.pairs_of(text)
    filas = lb.parse_verif_table(text)
    if filas is None:
        # D-43: a note with no block (or with the pre-1.54.0 template) is NOT "zero expired pairs".
        # It is a note nobody can evaluate, and saying otherwise is the invented zero the lint exists
        # not to produce. Every pair goes to the subset, and the caller is told why.
        return {"sin_bloque": True, "pares": pares, "asignado": {}, "sin_fila": pares, "huerfanas": []}
    asignado, sin_fila, huerfanas = lb.match_rows_to_pairs(pares, filas, umbral=umbral)
    return {"sin_bloque": False, "pares": pares, "asignado": asignado,
            "sin_fila": sin_fila, "huerfanas": huerfanas}


def _by_source(pares: list) -> dict:
    """Group pairs by bibcode, preserving order. The fan-out is one agent per source (#100)."""
    out: dict = {}
    for p in pares:
        out.setdefault(p.bibcode, []).append(p)
    return out


def main() -> int:
    """CLI. Reports the three buckets; `--json` writes the subset to re-verify, grouped by source.

    Exit 0 always when the note exists: this is a **report**, not a gate. The gate is
    `lint --cierre <slug>`, which is where an un-verified pair has to stop the close."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nota", help="ruta de la nota (p. ej. vault/wiki/stars/hd_40307.md)")
    ap.add_argument("--umbral", type=float, default=0.60,
                    help="cobertura mínima del extracto para proponer re-anclaje (default 0.60)")
    ap.add_argument("--json", dest="salida",
                    help="escribe el subconjunto a re-verificar, agrupado por fuente")
    args = ap.parse_args()

    nota = Path(args.nota)
    if not nota.exists():
        # Rehusar, no degradar: un subconjunto vacío sobre una nota inexistente se lee como «no hay
        # nada que re-verificar», que es el falso limpio de D-43.
        print(f"⛔ no existe: {nota}", file=sys.stderr)
        return 2
    text = nota.read_text(encoding="utf-8")
    r = classify(text, args.umbral)

    print(f"{nota}: {len(r['pares'])} pares en el cuerpo")
    if r["sin_bloque"]:
        print("⛔ sin bloque `## Verificación de citas` evaluable (ausente o plantilla anterior a "
              "1.54.0): NO es «cero vencidos», es un bloque que nadie puede evaluar (D-43).")
    else:
        print(f"  ✅ re-anclables (el veredicto se lleva, el ancla se recalcula) … {len(r['asignado']):4}")
        print(f"  ⛔ A RE-VERIFICAR (sin fila que llevar) ……………………………… {len(r['sin_fila']):4}")
        print(f"  ⚠ filas huérfanas (la afirmación ya no está en el cuerpo) … {len(r['huerfanas']):4}")

    if r["sin_fila"]:
        print("\n  a re-verificar, por fuente:")
        for bib, ps in sorted(_by_source(r["sin_fila"]).items(), key=lambda kv: -len(kv[1])):
            print(f"    {bib:28} {len(ps):3} par(es)")
    for row in r["huerfanas"]:
        print(f"  ⚠ huérfana · {row.bibcode} · {(row.claim or '')[:70]}…")

    if args.salida:
        datos = {bib: [{"ancla": p.anchor, "texto": p.block.text} for p in ps]
                 for bib, ps in _by_source(r["sin_fila"]).items()}
        Path(args.salida).write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n→ {args.salida}")

    if not r["sin_bloque"]:
        print("\n⚠ El re-anclaje es una PROPUESTA: dice que la afirmación sigue siendo reconociblemente\n"
              "  la misma, no que la corrección haya sido fiel. Quien lo acepte lo declara en el bloque\n"
              "  (de qué ronda viene el veredicto, y que el texto es posterior a la corrección).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
