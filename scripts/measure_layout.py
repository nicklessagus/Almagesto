#!/usr/bin/env python3
"""Diagnóstico de la maqueta de los `.txt` de `vault/raw/fulltext/` — cuánto del corpus es multi-columna.

Contexto (#44/#45): `extract_fulltext.py` usa `pdftotext -layout`, que **conserva la maqueta física**
del PDF. En un paper a dos columnas cada línea del `.txt` lleva texto de la columna 1, un hueco de
espacios (la "canaleta") y texto de la columna 2. Eso condiciona cómo hay que BUSCAR en el `.txt` —
ver la estrategia de matcheo en el skill `verify-citations`.

Este script NO corrige nada ni toca el corpus: mide, para saber cuánto pesa el fenómeno en una bóveda
concreta y poder calibrar (o justificar) la regla. Las tres métricas:

  · archivos multi-columna     → sobre cuántos papers rige la estrategia de matcheo
  · líneas con canaleta        → dónde un empalme columna1→columna2 es alcanzable (falso positivo)
  · líneas con corte por guión → dónde el de-hifenado hace falta

Salida legible por default; `--json` para consumirlo desde otro script.
Exit 0 siempre: es diagnóstico, no un chequeo que pueda "fallar".
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter

from lib_config import RAW, ROOT

# Una línea "útil" tiene suficiente texto como para que la maqueta se note.
MIN_LINEA = 40
# Canaleta: dos no-espacios separados por un hueco largo DENTRO de la línea. El mínimo de espacios
# es la definición compartida (la importa tests/test_multicolumn_matching.py — single source, #46).
CANALETA_MIN = 8
GUTTER = re.compile(rf"\S {{{CANALETA_MIN},}}\S")
# Corte de palabra por guión al final de línea.
HYPHEN = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]-$")
# Un archivo se considera multi-columna si esta fracción de sus líneas útiles tiene canaleta.
UMBRAL_ARCHIVO = 0.30


def analizar(texto: str) -> dict:
    lineas = [l for l in texto.splitlines() if len(l.strip()) >= MIN_LINEA]
    if not lineas:
        return {"utiles": 0, "canaleta": 0, "guion": 0, "frac": 0.0}
    canaleta = sum(1 for l in lineas if GUTTER.search(l))
    guion = sum(1 for l in lineas if HYPHEN.search(l.rstrip()))
    return {
        "utiles": len(lineas),
        "canaleta": canaleta,
        "guion": guion,
        "frac": canaleta / len(lineas),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Mide cuánto del corpus de fulltext es multi-columna (#44).",
        epilog="Sin argumentos analiza toda la bóveda. Exit 0 siempre: es diagnóstico.",
    )
    ap.add_argument("slug", nargs="?",
                    help="limitar a un slug de vault/raw/fulltext/ (estrella o tema); "
                         "sin esto, toda la bóveda")
    ap.add_argument("--json", action="store_true",
                    help="salida JSON en vez de tabla legible")
    ap.add_argument("--por-slug", action="store_true",
                    help="desglosar por slug además del total")
    ap.add_argument("--listar", metavar="N", type=int, default=0,
                    help="listar los N archivos con mayor fracción de canaleta")
    args = ap.parse_args()

    base = RAW / "fulltext"
    if not base.is_dir():
        print(f"! no existe {base} — ¿bóveda sin fulltext extraído?", file=sys.stderr)
        return 0

    raiz = base / args.slug if args.slug else base
    if args.slug and not raiz.is_dir():
        print(f"! no existe el slug '{args.slug}' en {base}", file=sys.stderr)
        return 0

    archivos = sorted(raiz.rglob("*.txt"))
    if not archivos:
        print(f"! sin .txt bajo {raiz}", file=sys.stderr)
        return 0

    total = Counter()
    multi = 0
    por_slug: dict[str, Counter] = {}
    detalle = []

    for f in archivos:
        m = analizar(f.read_text(errors="replace"))
        if not m["utiles"]:
            continue
        es_multi = m["frac"] > UMBRAL_ARCHIVO
        multi += es_multi
        total["archivos"] += 1
        for k in ("utiles", "canaleta", "guion"):
            total[k] += m[k]
        slug = f.parent.name
        s = por_slug.setdefault(slug, Counter())
        s["archivos"] += 1
        s["multi"] += es_multi
        detalle.append((m["frac"], f"{slug}/{f.stem}"))

    total["multi"] = multi
    pct = lambda a, b: (100 * a / b) if b else 0.0

    if args.json:
        salida = {
            "archivos": total["archivos"],
            "multicolumna": multi,
            "lineas_utiles": total["utiles"],
            "lineas_con_canaleta": total["canaleta"],
            "lineas_con_guion": total["guion"],
            "umbral_archivo": UMBRAL_ARCHIVO,
        }
        if args.por_slug:
            salida["por_slug"] = {s: {"archivos": c["archivos"], "multicolumna": c["multi"]}
                                  for s, c in sorted(por_slug.items())}
        print(json.dumps(salida, indent=2))
        return 0

    print(f"Maqueta del fulltext en {raiz.relative_to(ROOT)}\n")
    print(f"  archivos multi-columna   {multi:>6} / {total['archivos']:<6} "
          f"({pct(multi, total['archivos']):.0f}%)   ← sobre estos rige la estrategia de matcheo")
    print(f"  líneas con canaleta      {total['canaleta']:>6} / {total['utiles']:<6} "
          f"({pct(total['canaleta'], total['utiles']):.0f}%)   ← empalme col.1→col.2 alcanzable")
    print(f"  líneas con corte-guión   {total['guion']:>6} / {total['utiles']:<6} "
          f"({pct(total['guion'], total['utiles']):.0f}%)   ← hace falta de-hifenado")
    print(f"\n  (multi-columna = más del {UMBRAL_ARCHIVO:.0%} de sus líneas útiles con canaleta;"
          f" línea útil = {MIN_LINEA}+ caracteres)")

    if args.por_slug:
        print("\n  por slug:")
        for slug in sorted(por_slug):
            s = por_slug[slug]
            print(f"    {slug:<18} {s['multi']:>4} / {s['archivos']:<4} multi-columna")

    if args.listar:
        print(f"\n  top {args.listar} por fracción de canaleta:")
        for frac, nombre in sorted(detalle, reverse=True)[:args.listar]:
            print(f"    {frac:5.0%}  {nombre}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
