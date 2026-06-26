---
type: source-ref
author: Starmorph (blog)
title: "How to Build Karpathy's LLM Wiki — implementation guide"
url: https://blog.starmorph.com/blog/karpathy-llm-wiki-knowledge-base-guide
accessed: 2026-06-05
tags: [source-ref]
---
# Fuente: guía de implementación concreta de la LLM Wiki

De acá salieron los **formatos concretos** que el gist abstracto no especifica. Resumen.

## Layout recomendado
`raw/` (articles, papers, repos, data, images) · `wiki/` (index.md, log.md, overview.md,
concepts/, entities/, sources/, comparisons/) · `outputs/` · `CLAUDE.md` (schema).

## Frontmatter de página (su template)
`title, type(concept|entity|source-summary|comparison), sources[], related[[..]], created,
updated, confidence(high|medium|low)`.

## index.md
Catálogo por secciones (## Concepts / ## Entities / ## Source Summaries / ## Comparisons /
## Recent Updates), con `[[wikilink]] — descripción corta`.

## log.md (append-only)
`## YYYY-MM-DD HH:MM UTC — <Op>: <título>` seguido de bullets (Created/Updated/New pages/Index
entries/…).

## Operaciones (workflow)
- Ingest: leer fuente → `sources/<x>.md` → actualizar concept/entity → index → log.
- Query: leer index → leer páginas → sintetizar con `[[..]]` → opcional guardar página.
- Lint: contradicciones, huérfanos, conceptos faltantes, claims stale → `outputs/lint-DATE.md`.

## Cómo lo adaptó este template (divergencias)
Ver [[karpathy-llm-wiki]]. En síntesis: usamos `stars/`=entidades, `papers/`=source-summaries,
`matrices/` y `queries/` propios; sumamos frontmatter **máquina-legible** (contrato para el código
aguas abajo) y `ground_truth/` por API, que esta guía no contempla.
