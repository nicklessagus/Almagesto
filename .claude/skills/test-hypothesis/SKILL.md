---
name: test-hypothesis
description: Usar cuando el usuario plantea una hipótesis/supuesto y pide evidencia a favor o en contra en el corpus de la bóveda ("hipótesis: ...", "buscá evidencia que apoye o rechace que ...", "¿el corpus sostiene que ...?", "guardá como hipótesis que ..."). Testea contra el texto completo y deja la evidencia archivada.
version: 1.0.0
---

# Test de hipótesis contra el corpus

Operación **query** del patrón LLM Wiki, especializada para supuestos **durables** de la tesis.
Distinción: una hipótesis es un supuesto que se sostiene y acumula evidencia → vive en
`wiki/concepts/hypotheses/`. Una búsqueda de una vez NO es hipótesis (usar `query-corpus`).

## Pasos

1. **Buscar candidatos** en el texto completo local (rápido, offline):
   ```bash
   grep -ril "<términos clave de la hipótesis>" raw/fulltext/        # todas las estrellas
   grep -ril "<términos>" raw/fulltext/<slug>/                        # una estrella
   ```
   Elegir términos que cubran a favor y en contra (sinónimos, mecanismos alternativos).

2. **Leer los hits** (los `.txt`, no el PDF) y clasificar cada paper: **supports / challenges /
   method**. Ser honesto: buscar activamente contraejemplos, no solo confirmación.

3. **Registrar la hipótesis**: crear/actualizar `wiki/concepts/hypotheses/<slug-hipotesis>.md`
   (afirmación, estado, evidencia a favor, evidencia en contra/matices, implicación para el
   pipeline, gap a vigilar). Incluir un bloque Dataview que liste papers con
   `contains(thesis_links, "<slug>")`.

4. **Archivar la consulta**: crear `wiki/queries/<slug>_evidence.md` con la búsqueda usada, el
   veredicto y citas `[[bibcode]]`.

5. **Taggear papers**: en cada `wiki/papers/<bibcode>.md` relevante, poner
   `thesis_links: [<slug-hipotesis>]` y `bearing: supports|challenges|method`. Así la hipótesis
   acumula evidencia automáticamente.

6. **Bookkeeping**: actualizar `wiki/index.md` y appendear a `wiki/log.md`.

7. **Verificar citas**: correr el skill `verify-citations` sobre la nota de evidencia (y, si tocaste
   prosa con citas en la ficha/concepto de la hipótesis, sobre eso también). Chequea afirmación por
   afirmación contra el fulltext (cita textual + nº de línea del `.txt` obligatorios; sin respaldo
   textual ⇒ no-soportada). Resolver cada no-soportada/parcial (bajar, reasignar cita, o marcar
   `inferencia`) y dejar el bloque `## Verificación de citas`. Clave acá: el `bearing`
   (supports/challenges) de cada paper debe reflejar lo que el texto **realmente** dice.

8. **Chequeo de salud**: correr `python scripts/lint.py` antes de commitear. Debe quedar en **0**
   para wikilinks rotos, huérfanas, contradicciones, `thesis_links` sin página destino, fuga-sim y
   citas no verificables (los "campos incompletos" son backlog). Ojo con el tag del nuevo
   `thesis_link`: tiene que matchear el nombre de la página de hipótesis (typo típico: guion vs guion_bajo).

9. **Cierre (commit + push).** Si la operación escribió en `wiki/`, `git add` de los archivos
   **específicos** tocados (no `-A`; ver `CLAUDE.md` global) y commitear con mensaje descriptivo.
   Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Reporte
Veredicto explícito (sostiene / falla / parcial) y **en qué régimen** (tipo espectral, rango de
período, etc.). Declarar agregados (mean/median) según `CLAUDE.md`. No sobreestimar: un mecanismo
físico alternativo que rompa la hipótesis es un hallazgo, no un fracaso.
