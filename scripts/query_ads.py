"""Consulta NASA ADS por estrella → metadata de papers + clasificación de relevancia.

Uso:
    python query_ads.py <slug> [--all] [--rows N]

Escribe build/<slug>/ads.json con la lista de registros (bibcode, título, autores,
año, abstract, arxiv_id, doctype, citation_count, topics, relevant).

Usa la API REST de ADS directamente (control total de campos y filas). Rate: ~5000/día.
ADS resuelve `object:` vía SIMBAD, así que trae todo lo que menciona la estrella.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

import requests

import lib_config as cfg

API = "https://api.adsabs.harvard.edu/v1/search/query"
FIELDS = ("bibcode,title,author,year,pubdate,abstract,identifier,doctype,"
          "citation_count,bibstem,doi,keyword")

# Clasificación de relevancia: se LEE de vault/config/objective.yaml (el archivo que define
# el objetivo de la bóveda → qué paper es "core"). No hardcodear acá: editar el YAML.
_OBJ = cfg.load_objective()
_REL = (_OBJ.get("relevance") or {})
TOPIC_PATTERNS = {
    name: re.compile(pat, re.I)
    for name, pat in (_REL.get("topics") or {}).items()
}
NOISE_DOCTYPES = set(_REL.get("noise_doctypes") or [])
if not TOPIC_PATTERNS:
    raise RuntimeError(
        "vault/config/objective.yaml no define relevance.topics (el clasificador de papers core). "
        "Completalo antes de consultar ADS."
    )


def classify(rec: dict) -> tuple[list[str], bool]:
    """Devuelve (topics, relevant). Relevante si matchea ≥1 topic y no es doctype ruido."""
    text = " ".join(filter(None, [
        " ".join(rec.get("title", []) or []),
        rec.get("abstract", "") or "",
        " ".join(rec.get("keyword", []) or []),
    ])).lower()
    topics = [t for t, pat in TOPIC_PATTERNS.items() if pat.search(text)]
    doctype = rec.get("doctype", "")
    relevant = bool(topics) and doctype not in NOISE_DOCTYPES
    return topics, relevant


def extract_arxiv(identifiers: list[str]) -> str | None:
    for ident in identifiers or []:
        m = re.match(r"arXiv:(\S+)", ident, re.I)
        if m:
            return m.group(1)
    return None


def build_query(names: list[str]) -> str:
    """OR del nombre y alias sobre título y abstract (papers que discuten la estrella,
    no que la citan de pasada). `object:` no es campo válido en la API Solr de ADS."""
    clauses = []
    for n in names:
        clauses.append(f'title:"{n}"')
        clauses.append(f'abs:"{n}"')
    return " OR ".join(clauses)


def query_ads(q: str, rows: int = 400) -> list[dict]:
    """Corre una query Solr `q` ya armada contra ADS y devuelve registros clasificados.
    Para estrellas, armar `q` con build_query(names); para temas, usar la query cruda del topic."""
    token = cfg.get_ads_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": q, "fl": FIELDS, "rows": rows,
              "sort": "citation_count desc", "fq": "database:astronomy"}
    resp = requests.get(API, headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    docs = resp.json()["response"]["docs"]
    out = []
    for d in docs:
        topics, relevant = classify(d)
        out.append({
            "bibcode": d.get("bibcode"),
            "title": (d.get("title") or [""])[0],
            "authors": d.get("author", []),
            "year": d.get("year"),
            "pubdate": d.get("pubdate"),
            "abstract": d.get("abstract", ""),
            "arxiv_id": extract_arxiv(d.get("identifier", [])),
            "doi": (d.get("doi") or [None])[0],
            "doctype": d.get("doctype"),
            "bibstem": (d.get("bibstem") or [None])[0],
            "citation_count": d.get("citation_count", 0),
            "keyword": d.get("keyword", []),
            "topics": topics,
            "relevant": relevant,
        })
    return out


def print_probe(q: str, recs: list) -> int:
    """Modo preview del skill `setup`: muestra el corte core/no-core de una query sin bajar nada,
    para afinar la regla de relevancia (relevance.topics) contra papers reales."""
    rel = [r for r in recs if r["relevant"]]
    print(f"Probe (no baja PDFs ni escribe build/). q: {q}")
    print(f"  {len(recs)} papers · {len(rel)} CORE · {len(recs) - len(rel)} no-core\n")
    print("  Top por citas  [CORE/—  ·  tópicos que matchearon]:")
    for r in recs[:25]:
        mark = "CORE" if r["relevant"] else "—   "
        tp = ",".join(r["topics"]) or "(ninguno)"
        cites = r.get("citation_count") or 0          # ADS puede devolver citation_count null
        title = " ".join((r.get("title") or "").split())[:68]
        print(f"  [{mark}] {cites:>5}  {title}  «{tp}»")
    print("\n  → ajustá relevance.topics en objective.yaml y re-corré --probe hasta que el corte cierre.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?",
                    help="slug de estrella (o tema con --topic). Se omite con --probe.")
    ap.add_argument("--rows", type=int, default=400)
    ap.add_argument("--all", action="store_true",
                    help="guardar todos (default: solo relevantes en el resumen)")
    ap.add_argument("--topic", action="store_true",
                    help="el slug es un TEMA de vault/config/topics.yaml (query Solr cruda), no una estrella")
    ap.add_argument("--probe", metavar="QUERY",
                    help="PREVIEW (skill setup): corre una query Solr CRUDA y muestra el corte "
                         "core/no-core con títulos, clasificando con relevance.topics de objective.yaml. "
                         "No baja PDFs ni escribe build/ — sólo para afinar la regla de relevancia.")
    args = ap.parse_args()

    if args.probe:
        return print_probe(args.probe, query_ads(args.probe, rows=args.rows))

    if not args.slug:
        ap.error('falta el slug (o usá --probe "<query>" para previsualizar la regla de relevancia)')

    if args.topic:
        _, meta = cfg.topic_by_slug(args.slug)
        q = meta["query"]
        print(f"Consultando ADS (tema): {meta.get('title', args.slug)}\n  q: {q}")
        head = {"kind": "topic", "slug": args.slug, "title": meta.get("title"),
                "concept": meta.get("concept"), "area": meta.get("area"), "query": q}
    else:
        name, meta = cfg.star_by_slug(args.slug)
        names = [meta["ads_object"]] + meta.get("aliases", [])
        q = build_query(names)
        print(f"Consultando ADS: {name}  (nombres: {', '.join(names)})")
        head = {"kind": "star", "star": name, "slug": args.slug, "ads_object": meta["ads_object"]}

    recs = query_ads(q, rows=args.rows)
    rel = [r for r in recs if r["relevant"]]
    print(f"  {len(recs)} registros, {len(rel)} relevantes")

    outdir = cfg.ROOT / "build" / args.slug
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {**head, "n_total": len(recs), "n_relevant": len(rel), "records": recs}
    (outdir / "ads.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"  → {outdir / 'ads.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
