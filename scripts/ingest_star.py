"""Orquestador de la cadena mecánica de ingest-star — fuente de verdad ÚNICA del orden.

Uso:
    python ingest_star.py <slug>

Corre, en orden y abortando al primer fallo, la cadena astro completa para una estrella de
vault/config/stars.yaml:

    query_ads → fetch_arxiv → fetch_pdf → fetch_ground_truth → make_notes → extract_fulltext
    → check_retractions

**Este header ES la definición canónica de la cadena de estrellas** (el análogo para temas es
`ingest_topic.py`). Docs y skills apuntan acá en vez de copiar la lista — una copia por doc es
drift asegurado cuando la cadena cambia.

Todo idempotente: re-correr es seguro (nada se re-baja ni se pisa; `fetch_ground_truth` NO
refresca un snapshot existente — refrescar NEA es decisión explícita, no side-effect). Sin
`--force` acá, a propósito: los flags finos (`--rows`, `--all`, `--force` de un paso) se corren
en el script puntual.

`check_retractions` cierra la cadena y su exit 1 significa "detectó papers retractados"
(revisar las notas marcadas; el lint lo surface como bloqueante), NO un fallo de la cadena.

La extracción LLM posterior (leer fulltext, poblar notas, síntesis, matriz) NO es de este
script: la hace el agente siguiendo el skill ingest-star.
"""
from __future__ import annotations

import argparse
import sys

import lib_config as cfg
from ingest_topic import run

CHAIN = ("query_ads.py", "fetch_arxiv.py", "fetch_pdf.py", "fetch_ground_truth.py",
         "make_notes.py", "extract_fulltext.py")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="estrella de vault/config/stars.yaml (por slug)")
    args = ap.parse_args()
    try:
        name, _ = cfg.star_by_slug(args.slug)
    except KeyError as e:
        sys.exit(str(e))
    print(f"Ingest de {name} ({args.slug}) — cadena mecánica completa")
    for script in CHAIN:
        rc = run(script, args.slug)
        if rc:
            sys.exit(f"{script} falló (rc={rc}) — cadena abortada. Es idempotente: corregí y "
                     "re-corré ingest_star.py (lo ya bajado no se re-baja).")
    if run("check_retractions.py"):
        sys.exit("check_retractions detectó papers retractados — revisá las notas marcadas "
                 "(el lint las surface como bloqueante).")
    print("\nCadena mecánica lista. Siguiente (LLM, skill ingest-star): barrido full-text (2b) → "
          "extracción por paper → ficha de la estrella → verify-citations → lint.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
