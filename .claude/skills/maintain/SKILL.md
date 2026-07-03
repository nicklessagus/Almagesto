---
name: maintain
description: Usar para MANTENER entidades ya ingestadas (estrellas y conceptos), no para crear nuevas. Cubre refrescar una estrella/concepto con papers nuevos ("actualizá GJ 581", "traé lo nuevo de tau Ceti"), borrar un paper/estrella/tema ("borrá el paper X", "sacá esta estrella"), renombrar un slug ("renombrá el slug de …"), re-clasificar tras cambiar relevance.topics ("cambié el objetivo, re-clasificá el corpus"), y resolver el backlog del lint (huérfanos, P_rot faltante, drift PDF↔disco, claims stale).
version: 1.0.0
---

# Maintain — mantenimiento de estrellas y conceptos ya ingestados

Operación de **mantenimiento** del patrón LLM Wiki (las "operaciones de lint" de Karpathy: la wiki es
viva y hay que cuidarla, no sólo poblarla). **No crea entidades** (para eso `ingest-star`/`ingest-topic`);
opera sobre lo que **ya existe**. Elegir el sub-modo según el pedido. Trabajar desde la raíz del repo.

**Invariante que rige todo:** la cadena de scripts es **idempotente** (no pisa). Refrescar es seguro;
lo que **nunca** se pisa sin decisión explícita es la **extracción LLM** (`make_notes --force` la
regenera → sólo con confirmación) y el **ground-truth** (`fetch_ground_truth --force`). Todo cambio
cierra con **verify-citations** (si tocó prosa con `[[bibcode]]`) + **lint en 0** + `log`, y se
**pregunta antes de `push`**.

---

## A. Refrescar una estrella / concepto (papers nuevos desde el último ingest)
1. Re-correr la cadena (idempotente — sólo agrega lo nuevo, no re-baja ni pisa):
   ```bash
   python query_ads.py <slug>            # trae papers nuevos + citation chaining (estrella)
   python fetch_arxiv.py <slug>          # baja sólo los PDF que faltan
   python make_notes.py <slug>           # crea SÓLO stubs nuevos (no pisa notas con extracción)
   python extract_fulltext.py <slug>
   python check_retractions.py           # re-chequea retracciones (papers viejos pueden retractarse)
   ```
   (Para conceptos: `--topic <slug>`, sin `fetch_ground_truth`.) **No** correr `fetch_ground_truth`
   salvo que quieras refrescar NEA a propósito (`--force`) — NEA cambia entre releases y refrescarlo es
   una decisión, no un side-effect.
2. **Identificar lo nuevo:** `git status` sobre `vault/wiki/papers/` muestra los stubs recién creados. Leer
   **sólo esos** fulltext y hacer su extracción (methods/bearing/thesis_links/P·K/indicadores).
3. **Re-sintetizar incorporando sólo lo nuevo:** releer la ficha/concepto y **actualizar** la síntesis y
   los huecos con lo que aportan los papers nuevos — no reescribir de cero lo ya destilado. Si un paper
   nuevo discrepa, taguear `disputes[]` (o correr `find-contradictions`). Actualizar la matriz
   método×estrella si hay métodos nuevos.
4. Cierre: verify-citations sobre la prosa cambiada → lint → `log` → commit → preguntar push.

## B. Borrar un paper / estrella / tema
1. **Antes de borrar, mapear lo que cuelga** (el lint los detectaría, pero resolvelos vos limpio):
   ```bash
   grep -rn "<bibcode-o-slug>" vault/wiki/                    # wikilinks, thesis_links, disputes[].ref, matriz
   ```
2. Borrar el/los archivo(s): la nota (`papers/<bib>.md` o `stars/<slug>.md`), su PDF
   (`vault/raw/pdfs/<slug>/…`) y fulltext (`vault/raw/fulltext/<slug>/…`). Si es una estrella/tema entero,
   también su entrada en `stars.yaml`/`topics.yaml` y su `ground_truth/<slug>.json`.
3. **Reparar los colgados:** quitar/re-apuntar cada `[[wikilink]]`, `thesis_links`, `disputes[].ref` y
   celda de matriz que apuntaba al borrado. (La tabla `## Papers` de las fichas es Dataview → se
   actualiza sola.) Sacar la estrella de la matriz método×estrella.
4. Cierre: **lint en 0** (0 wikilinks rotos / thesis_links colgados / disputes.ref sin destino) → `log`
   (qué se borró y por qué) → commit → preguntar push.

## C. Renombrar un slug
1. Renombrar en orden: la clave en `stars.yaml`/`topics.yaml`, los directorios
   `vault/raw/{pdfs,fulltext}/<slug>/` y `ground_truth/<slug>.json`, la nota `stars/<slug>.md` (o el
   concepto), y **todos** los `[[wikilink]]` al nombre viejo:
   ```bash
   grep -rln "<slug-viejo>" vault/                            # dónde aparece
   ```
2. Ajustar `data_local` si cambió y el nombre en la matriz. Los wikilinks internos son por **nombre de
   nota** (sobreviven a mover carpeta pero **no** a renombrar el archivo) → actualizarlos todos.
3. Cierre: lint en 0 → `log` → commit → preguntar push.

## D. Re-clasificar tras cambiar `relevance.topics`
Cuando editaste `objective.yaml` (vía `setup`) y el corte core/no-core cambió:
1. Re-correr `python query_ads.py <slug>` para cada estrella/tema afectado → re-clasifica con la regla
   nueva (regenera `build/<slug>/ads.json`).
2. **Papers que dejaron de ser core:** decidir con el usuario — dejar la nota marcada (`relevance: low`)
   o borrarla (sub-modo B). No borrar en silencio.
3. **Papers que ahora sí son core:** ingestarlos (extracción LLM) como en un refresh (sub-modo A).
4. **Regenerar el apéndice "Excluidos por el filtro"** de las fichas (cambió el corte) — `make_notes`
   lo re-estampa; revisá que refleje la regla nueva.
5. Cierre: verify (si tocaste prosa) → lint → `log` (qué se re-clasificó) → commit → preguntar push.

## E. Resolver el backlog del lint
Pasada de higiene sobre lo que `lint.py` marca como backlog/WARN (no bloqueante, pero se acumula):
- **Huérfanos** (concepto sin links entrantes) → citarlo desde donde corresponda, o borrarlo si sobra.
- **P_rot / campos nulos** → abrir una `query-corpus` para imputar desde la literatura (web/ADS) y
  completar el frontmatter con su `[[bibcode]]`.
- **PDF ↔ disco** (drift del campo `pdf`) → linkear el PDF bajado o corregir el puntero roto.
- **Cobertura** (concepto/hipótesis sin ninguna cita) → agregar las citas que faltan.
- **Fuga de implementación** (WARN) → revisar el hit; si es material de código no bibliográfico,
  sacarlo del vault (frontera dura).
- **Claims stale** → re-verificar contra la fuente los que quedaron dudosos.
Cierre: lint (idealmente bajando el conteo de backlog) → `log` → commit → preguntar push.

## Notas
- **No es ingest:** si la entidad no existe todavía, esto no aplica → `ingest-star`/`ingest-topic`.
- **No es query:** una pregunta puntual va por `query-corpus`; acá se **modifica** la bóveda.
- Schemas de frontmatter, reglas de ruta y disputas: ver `CLAUDE.md`. `git add` **específico** (no `-A`).
