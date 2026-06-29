---
type: source-ref
author: Andrej Karpathy
title: "LLM Wiki (idea file / gist)"
url: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
date: 2026-04-04
accessed: 2026-06-05
tags: [source-ref]
---
# Fuente: Karpathy — "LLM Wiki"

Ficha de fuente (no copia verbatim — el gist es material de terceros). Es la **base de verdad**
del diseño de este template. Resumen fiel + citas cortas.

## Idea
En vez de RAG (recuperar documentos crudos en cada pregunta), *"the LLM incrementally builds and
maintains a persistent wiki — a structured, interlinked collection of markdown files."* El
conocimiento se sintetiza una vez y se mantiene al día; **compone** con cada fuente.

## Arquitectura de 3 capas
- **raw/** — fuentes inmutables que cura el humano (el LLM lee, no modifica).
- **wiki/** — `.md` que el LLM escribe y mantiene **enteramente** (*"The LLM owns this layer
  entirely"*).
- **schema** (`CLAUDE.md`) — configura cómo el LLM mantiene la wiki.

Analogía de compilador (de la discusión asociada): raw = código fuente, LLM = compilador,
wiki = ejecutable, lint = tests, queries = runtime.

## Operaciones
- **Ingest**: una fuente nueva → el LLM la lee, resume, actualiza páginas relacionadas y appendea al log.
- **Query**: preguntar contra la wiki; sintetiza con citas; opcionalmente archiva la respuesta como
  página nueva.
- **Lint**: chequeo de salud periódico (contradicciones, claims stale, páginas huérfanas,
  cross-refs faltantes; imputar datos faltantes con web search).

## Archivos especiales
- `index.md` — catálogo de contenido por categoría, actualizado en cada operación.
- `log.md` — registro append-only cronológico con timestamps greppables.

## Filosofía
*"The tedious part of maintaining a knowledge base is not the reading or the thinking — it's the
bookkeeping."* El LLM hace el bookkeeping (cross-refs, consistencia) que los humanos abandonan.
Linaje: el Memex de Vannevar Bush (1945), pero resolviendo el problema de mantenimiento.

> El gist es **intencionalmente abstracto**: no trae estructura de directorios ni schema concreto;
> hay que instanciarlo por dominio. Por eso los formatos concretos de este template vienen de una guía
> de la comunidad ([[starmorph-implementation-guide]]) adaptada a nuestro caso.

Ver también: el tweet de Karpathy ("LLM Knowledge Bases") con el flujo práctico (Obsidian Web
Clipper para ingestar web, Obsidian como IDE, outputs Marp/matplotlib filed-back, un search-engine
CLI vibe-coded, y la idea futura de fine-tuning sobre la wiki).
