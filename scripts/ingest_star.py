"""Orquestador de la cadena mecánica de ingest-star — fuente de verdad ÚNICA del orden.

Uso:
    python scripts/ingest_star.py <slug> [--yes]

Corre, en orden y abortando al primer fallo, la cadena astro completa para una estrella de
vault/config/stars.yaml:

    query_ads → [guardia de expansión] → fetch_arxiv → fetch_pdf → fetch_ground_truth
    → make_notes → extract_fulltext → check_retractions

La **guardia de expansión** (#37) es un checkpoint humano entre la query y el primer paso que
gasta red y disco: si el core del `ads.json` fresco se multiplicó respecto de las notas ya
ingestadas del sujeto (default: ×1.5 y 50 o más nuevos), frena con el conteo, cuántos vinieron por
el grafo de citas y el puntero a `relevance.require`/`min_facets`. `--yes` continúa a sabiendas.

**Este header ES la definición canónica de la cadena de estrellas** (el análogo para temas es
`ingest_theme.py`). Docs y skills apuntan acá en vez de copiar la lista — una copia por doc es
drift asegurado cuando la cadena cambia.

Todo idempotente: re-correr es seguro (nada se re-baja ni se pisa; `fetch_ground_truth` NO
refresca un snapshot existente — refrescar NEA es decisión explícita, no side-effect). Sin
`--force` acá, a propósito: los flags finos (`--rows`, `--all`, `--force` de un paso) se corren
en el script puntual.

`check_retractions --slug` cierra la cadena chequeando SÓLO los papers de este ingest (el
barrido Crossref completo de la bóveda es pasada periódica — skill maintain). Sus tres códigos se
distinguen acá (issue 0.1): **1** = detectó papers retractados (revisar las notas marcadas; el lint
lo surface como bloqueante), NO un fallo de la cadena; **2** = el chequeo **no pudo correr**
(precondición ausente o Crossref caído) — también aborta, porque la cadena no certifica lo que no
miró, pero con el mensaje honesto.

La extracción LLM posterior (leer fulltext, poblar notas, síntesis, matriz) NO es de este
script: la hace el agente siguiendo el skill ingest-star.
"""
from __future__ import annotations

import argparse
import sys

import lib_config as cfg
from ingest_theme import expansion_guard, run

CHAIN = ("query_ads.py", "fetch_arxiv.py", "fetch_pdf.py", "fetch_ground_truth.py",
         "make_notes.py", "extract_fulltext.py")


def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser(
        description="Orquesta la cadena de ingesta de una ESTRELLA (astro-only). El ORDEN CANÓNICO vive en el header de este archivo, que es su fuente de verdad. Idempotente: re-correrlo es seguro.",
        epilog="Exit != 0 aborta la cadena: corregí y volvé a correr (es idempotente).")
    ap.add_argument("slug", help="estrella de vault/config/stars.yaml (por slug)")
    ap.add_argument("--yes", action="store_true",
                    help="continuar a sabiendas si la guardia de expansión frena la cadena (el pool "
                         "core se multiplicó respecto de lo ya ingestado)")
    args = ap.parse_args()
    try:
        name, _ = cfg.star_by_slug(args.slug)
    except KeyError as e:
        sys.exit(str(e))
    print(f"Ingest de {name} ({args.slug}) — cadena mecánica completa")
    escotillas = ["--yes"] if args.yes else []      # INV-44: la escotilla del orquestador deja traza
    for script in CHAIN:
        rc = run(script, args.slug, flags=escotillas)
        if rc:
            sys.exit(f"{script} falló (rc={rc}) — cadena abortada. Es idempotente: corregí y "
                     "re-corré ingest_star.py (lo ya bajado no se re-baja).")
        if script == "query_ads.py":       # checkpoint ANTES del primer paso que gasta red y disco
            expansion_guard(args.slug, args.yes)
    retr_rc = run("check_retractions.py", "--slug", args.slug, flags=escotillas)
    if retr_rc == 1:
        sys.exit("check_retractions detectó papers retractados — revisá las notas marcadas "
                 "(el lint las surface como bloqueante).")
    if retr_rc:
        # rc 2 (issue 0.1) — el chequeo NO corrió: precondición ausente o Crossref caído. Abortar
        # igual, pero sin la frase falsa: mandar al operador a "revisar las notas marcadas" cuando
        # no hay ninguna marcada le hace buscar un problema inexistente Y deja el real —la frontera
        # dura sin verificar— invisible.
        sys.exit(f"check_retractions no pudo chequear (rc={retr_rc}) — la cadena no certifica lo "
                 "que no miró. Revisá el motivo que imprimió arriba y re-corré (es idempotente).")
    # El hand-off nombra los pasos SALTEABLES con su número del skill: son los que no dejan rastro
    # si se omiten. El contraste (3b) entró con #72 y es el de más apalancamiento — sin él la
    # síntesis se escribe sobre un solo paper por eje.
    print("\nCadena mecánica lista. Siguiente (LLM, skill ingest-star): barrido full-text (2b) → "
          "TRIAGE de los candidatos del chaining (2c) → una VISTA por paper (3, #188) + "
          f"`python scripts/harvest_views.py {args.slug}` → CONTRASTE "
          "cross-paper / inventario por eje (3b) → síntesis a la ficha (3c) → verify-citations "
          "(5b) → lint.")
    return 0


if __name__ == "__main__":
    cfg.cli_exit(main)
