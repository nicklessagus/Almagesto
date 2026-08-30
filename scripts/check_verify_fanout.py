#!/usr/bin/env python3
"""Valida la salida del fan-out de `verify-citations` ANTES de derivar trabajo de ella (#259).

    python scripts/check_verify_fanout.py <dir> [--esperados N]

POR QUÉ EXISTE. El skill fijaba **qué campos** devolver y no **la forma del archivo**. Medido al
cerrar `hd_40307` (2026-08-29, 8 rondas y ~60 subagentes, el mismo prompt salvo el bibcode): la
clave de la lista llegó en **tres** formas (`pares`, `veredictos`, `resultados`) y el identificador
del par en **dos** (`ancla`, `n`); el consumidor reventó **dos veces con `KeyError`** con 60
lecturas de PDF ya pagadas, y terminó en un lector tolerante
(`data.get('pares') or data.get('veredictos') or …`) que este repo prohíbe: el productor nunca se
entera y la forma sigue derivando. ⛔ Y el `KeyError` es el modo **benigno**: un consumidor menos
paranoico lee **0 veredictos de un archivo que sí los tiene** y sigue —el falso limpio, sobre la
capa que existe para no producirlos—.

Este comando es la barrera de §2b del skill hecha máquina. Dos chequeos, los dos baratos:

  · **forma** — cada `*.json` contra `lib_blocks.VERIF_FANOUT_SCHEMA`, **nombrando el archivo y la
    clave**. Con un directorio de sesenta archivos, «salida malformada» no dice cuál re-correr.
  · **conteo** (`--esperados N`) — los pares del directorio contra los pares que se mandaron a
    juzgar; si no coinciden, **aborta**. Es la red barata de #222 (contar antes y después, como la
    guarda «los pares no bajaron» de `apply_fixes`) aplicada al otro extremo de la cadena: un
    subagente que devolvió la mitad de sus pares produce un archivo perfectamente válido.

⛔ **No repara nada y no escribe nada** (misma doctrina que `--drop-core` y `reverify_subset`):
reporta y rehúsa. Un directorio inexistente sale con **rc 2** en vez de un cero limpio (D-43): «0
archivos malformados» sobre un directorio que nadie miró se lee como veredicto.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_blocks as lb  # noqa: E402


def check_dir(directory: Path) -> tuple[dict, list[str]]:
    """Every `*.json` of `directory` against the schema. `(pairs per file, errors)`.

    A file that does not even parse is a violation like any other and is named as such: the fan-out
    writes JSON by hand, and a truncated one is the same class of defect as a renamed key.

    Files are read in sorted order so that two runs over the same directory report in the same
    order — a report whose lines move around gets diffed by nobody.
    """
    pairs, errors = {}, []
    for f in sorted(directory.glob("*.json")):
        name = f.name
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{name}: no parsea como JSON — {exc}")
            continue
        errs = lb.fanout_errors(data, entry=name)
        errors += errs
        if not errs:
            pairs[name] = len(data["pares"])
    return pairs, errors


def pair_count_errors(pairs: dict, expected: int) -> list[str]:
    """Does the directory hold the pairs that were sent out to be judged? (#222)

    Only files that passed the schema check are counted, and the message says so: a malformed file
    contributes an unknown number of pairs, so folding it in as zero would turn one loud finding
    into a quieter, wrong one.
    """
    total = sum(pairs.values())
    if total == expected:
        return []
    falta = expected - total
    detalle = (f"faltan {falta}" if falta > 0 else f"sobran {-falta}")
    return [f"⛔ pares devueltos: {total}, esperados {expected} ({detalle}). Un subagente que "
            f"devolvió de menos escribe un archivo VÁLIDO: la forma no lo ve, el conteo sí. "
            f"Contado sobre los {len(pairs)} archivo(s) que cumplen el schema."]


def main() -> int:
    """CLI. rc 0 si el directorio cumple, 1 si hay hallazgos, 2 si no se pudo mirar."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", help="directorio de la ronda (p. ej. build/<slug>/verif/r3)")
    ap.add_argument("--esperados", type=int, default=None,
                    help="cuántos pares se mandaron a juzgar; si el directorio no los tiene, aborta")
    args = ap.parse_args()

    directory = Path(args.dir)
    if not directory.is_dir():
        # D-43: rehusar, no reportar un cero limpio. «0 archivos con problemas» sobre un directorio
        # que no existe es exactamente el veredicto que nadie midió.
        print(f"⛔ no es un directorio: {directory}", file=sys.stderr)
        return 2

    pairs, errors = check_dir(directory)
    archivos = len(list(directory.glob("*.json")))
    print(f"{directory}: {archivos} archivo(s) `*.json` · {sum(pairs.values())} par(es) en los "
          f"{len(pairs)} que cumplen el schema")
    if archivos == 0:
        # Tampoco es un verde: la barrera del skill contó «0 de 30» más de una vez, y sin decirlo.
        print("⛔ el directorio no tiene ningún `*.json`: eso NO es «cumple», es que el fan-out no "
              "escribió nada (¿subagentes de sólo lectura, o el tope de 20 concurrentes?).",
              file=sys.stderr)
        return 1

    if args.esperados is not None:
        errors += pair_count_errors(pairs, args.esperados)

    if errors:
        print(f"\n⛔ {len(errors)} hallazgo(s) — el consumidor NO puede derivar trabajo de esto:")
        for e in errors:
            print(f"  {e}")
        print("\n  La forma canónica es la del fence que el skill pega en el prompt "
              "(`lib_blocks.verify_fanout_json_block`). Se re-corre la fuente que no cumple; no se "
              "escribe un lector tolerante.")
        return 1
    print("✅ todos cumplen el schema" + ("" if args.esperados is None else
                                          f" y los pares dan {args.esperados}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
