"""Genera notas markdown de la bóveda a partir de lo bajado por los otros scripts.

Uso:
    python make_notes.py <slug> [--all] [--force]

- stars/<slug>.md  : ficha índice de la estrella (frontmatter máquina-legible + Dataview).
- papers/<bibcode>.md : una nota por paper relevante (metadata + abstract + placeholders LLM).

Idempotente: NO pisa notas existentes (protege la extracción LLM) salvo --force.
"""
from __future__ import annotations

import argparse
import json
import sys

import yaml

import lib_config as cfg


def fm(d: dict) -> str:
    """Frontmatter YAML entre --- ---."""
    body = yaml.safe_dump(d, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"---\n{body}---\n"


def safe_name(bibcode: str) -> str:
    return bibcode.replace("/", "_")


def write_star_note(slug: str, force: bool) -> None:
    name, meta = cfg.star_by_slug(slug)
    dest = cfg.STARS / f"{slug}.md"
    if dest.exists() and not force:
        print(f"  star: {dest.name} ya existe (usa --force para regenerar)")
        return
    gt_file = cfg.GROUND_TRUTH / f"{slug}.json"
    gt = json.loads(gt_file.read_text()) if gt_file.exists() else {"host": {}, "planets": []}
    host = gt.get("host", {})
    planets = [{"letter": p.get("letter"), "P_days": p.get("P_days"),
                "K_ms": p.get("K_ms"), "e": p.get("e"), "status": p.get("status")}
               for p in gt.get("planets", [])]

    front = {
        "name": name,
        "slug": slug,
        "aliases": meta.get("aliases", []),
        "simbad_id": meta.get("simbad"),
        "spectral_type": host.get("spectral_type"),
        "teff_K": host.get("teff_K"),
        "dist_pc": host.get("dist_pc"),
        "P_rot_days": host.get("st_rotp_days"),      # llenar con literatura si falta
        "activity_indicators_expected": [],           # poblar con extracción LLM
        "planets": planets,
        "data_local": meta.get("data_local"),
        "methods_applied": {"literature": [], "ours": []},
        "confidence": "medium",          # patrón LLM Wiki; subir a high tras síntesis revisada
        "tags": ["star"],
    }
    body = f"""{fm(front)}
# {name}

> Ficha índice. El frontmatter de arriba es la fuente de verdad máquina-legible
> (lo leen Obsidian/Dataview y cualquier consumidor de la bóveda). La prosa y los `[[links]]` son la capa humana.

## Resumen
_(síntesis por LLM: qué se sabe, qué indicadores deberían correlacionar con actividad para este
tipo espectral, planetas confirmados/dudosos, huecos en la bibliografía)._

## Planetas (ground-truth NASA Exoplanet Archive)
```dataviewjs
const p = dv.current().planets ?? [];
dv.table(["letter","P (d)","K (m/s)","e","status"],
  p.map(x => [x.letter, x.P_days, x.K_ms, x.e, x.status]));
```

## Papers
```dataview
TABLE year, topics, relevance, citation_count
FROM "wiki/papers"
WHERE contains(stars, "{name}")
SORT citation_count DESC
```

## Métodos aplicados a esta estrella
```dataview
TABLE WITHOUT ID method, file.link, year
FROM "wiki/papers"
WHERE contains(stars, "{name}") AND methods
FLATTEN methods AS method
SORT method ASC
```

## Datos crudos
`{meta.get('data_local')}`
"""
    dest.write_text(body, encoding="utf-8")
    print(f"  star: {dest.name} escrito")


def write_concept_note(slug: str, force: bool) -> None:
    """Para temas (ingest-topic): stub del concept durable destino. Idempotente: NO pisa la
    síntesis LLM de un concept ya existente (sólo se crea si falta)."""
    _, meta = cfg.topic_by_slug(slug)
    area, concept = meta["area"], meta["concept"]
    # Validar el área contra el contrato (concept_areas en objective.yaml) ANTES de mkdir: un
    # `area` mal tipeado en topics.yaml crearía una carpeta fantasma en silencio. --force la fuerza.
    areas = cfg.load_concept_areas()
    if area not in areas and not force:
        sys.exit(
            f"  ✗ área '{area}' (topic '{slug}') no está en concept_areas (vault/config/objective.yaml).\n"
            f"    Áreas válidas: {', '.join(areas)}.\n"
            f"    ¿Typo en topics.yaml? Corregilo. ¿Área nueva legítima? Declarala en concept_areas\n"
            f"    (no inventes carpetas sueltas). O usá --force para crearla igual."
        )
    dest = cfg.CONCEPTS / area / f"{concept}.md"
    if dest.exists():
        print(f"  concept: {area}/{concept}.md ya existe (no se pisa; los papers enganchan por thesis_links)")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    front = {
        "name": meta.get("title", concept),
        "status": "active",
        "tags": [area, "thesis"],
        "confidence": "medium",
    }
    body = f"""{fm(front)}
# {meta.get('title', concept)}

> Concept durable (tema). Síntesis por LLM: destilar acá lo que aprenden los papers de abajo, de modo
> que el tema se entienda **sin abrir ningún paper**. Trazabilidad por `[[bibcode]]`.

## Síntesis
_(qué se sabe del tema: mecanismos, signos, desfasajes, regímenes, huecos)._

## Papers que tocan este tema (auto)
```dataview
TABLE bearing, year, file.link
FROM "wiki/papers"
WHERE contains(thesis_links, "{concept}")
SORT year ASC
```
"""
    dest.write_text(body, encoding="utf-8")
    print(f"  concept: {area}/{concept}.md escrito (stub)")


def write_paper_notes(slug: str, include_all: bool, force: bool, topic: bool = False) -> None:
    if topic:
        _, tmeta = cfg.topic_by_slug(slug)
        name, link, seed_links = None, tmeta["concept"], [tmeta["concept"]]
    else:
        name, _ = cfg.star_by_slug(slug)
        link, seed_links = slug, []
    adsfile = cfg.ROOT / "build" / slug / "ads.json"
    if not adsfile.exists():
        print(f"  (sin {adsfile}; corré query_ads.py primero)")
        return
    recs = json.loads(adsfile.read_text())["records"]
    if not include_all:
        recs = [r for r in recs if r["relevant"]]
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for r in recs:
        bib = r["bibcode"]
        dest = cfg.PAPERS / f"{safe_name(bib)}.md"
        if dest.exists() and not force:
            skipped += 1
            continue
        authors = r.get("authors", [])
        pdf_rel = f"../../raw/pdfs/{slug}/{safe_name(bib)}.pdf" if r.get("arxiv_id") else None
        front = {
            "bibcode": bib,
            "title": r.get("title"),
            "first_author": authors[0] if authors else None,
            "n_authors": len(authors),
            "year": int(r["year"]) if r.get("year") else None,
            "arxiv_id": r.get("arxiv_id"),
            "doi": r.get("doi"),
            "bibstem": r.get("bibstem"),
            "stars": [name] if name else [],
            "topics": r.get("topics", []),
            "methods": [],                 # poblar con extracción LLM
            "thesis_links": list(seed_links),  # tema: pre-sembrado al concept; estrella: vacío
            "bearing": None,               # supports | challenges | method (respecto a thesis_links)
            "relevance": "high" if r.get("relevant") else "low",
            "citation_count": r.get("citation_count", 0),
            "pdf": pdf_rel,
            "confidence": "medium",      # patrón LLM Wiki
            "tags": ["paper"],
        }
        abstract = (r.get("abstract") or "").strip()
        body = f"""{fm(front)}
# {r.get('title')}

**{', '.join(authors[:6])}{' et al.' if len(authors) > 6 else ''}** ({r.get('year')})
· [[{link}]] · ADS: `{bib}`{' · arXiv: ' + r['arxiv_id'] if r.get('arxiv_id') else ''}

## Abstract
{abstract or '_(no disponible)_'}

## Extracción (LLM)
- **Planetas / parámetros:** _(P, K, e por planeta; comparar contra ground-truth)_
- **Actividad / indicadores:** _(qué indicadores se usaron y qué correlaciones se reportan)_
- **Métodos:** _(llenar `methods:` del frontmatter con `concepts/methods/`)_
- **Para mi objetivo:** _(relevancia para el objetivo de la bóveda / huecos)_
"""
        dest.write_text(body, encoding="utf-8")
        written += 1
    print(f"  papers: {written} escritos, {skipped} ya existían")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--all", action="store_true", help="incluir papers no-relevantes")
    ap.add_argument("--force", action="store_true", help="pisar notas existentes")
    ap.add_argument("--topic", action="store_true",
                    help="el slug es un TEMA de vault/config/topics.yaml: genera concept en vez de ficha de estrella")
    args = ap.parse_args()
    print(f"Generando notas para {args.slug}")
    if args.topic:
        write_concept_note(args.slug, args.force)
    else:
        write_star_note(args.slug, args.force)
    write_paper_notes(args.slug, args.all, args.force, topic=args.topic)
    return 0


if __name__ == "__main__":
    sys.exit(main())
