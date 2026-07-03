---
name: test-hypothesis
description: Usar cuando el usuario plantea una hipótesis/supuesto y pide evidencia a favor o en contra en el corpus de la bóveda ("hipótesis: ...", "buscá evidencia que apoye o rechace que ...", "¿el corpus sostiene que ...?", "guardá como hipótesis que ..."). Testea contra el texto completo y responde con veredicto citado; archiva la hipótesis y taggea papers SÓLO si el usuario lo pide.
version: 1.1.0
---

# Test de hipótesis contra el corpus

Operación **query** del patrón LLM Wiki, especializada para supuestos **durables** de la tesis.
Distinción: una hipótesis es un supuesto que se sostiene y acumula evidencia → vive en
`vault/wiki/concepts/hypotheses/`. Una búsqueda de una vez NO es hipótesis (usar `query-corpus`).

## Pasos

1. **Buscar candidatos** en el texto completo local (rápido, offline):
   ```bash
   grep -ril "<términos clave de la hipótesis>" vault/raw/fulltext/        # todas las estrellas
   grep -ril "<términos>" vault/raw/fulltext/<slug>/                        # una estrella
   ```
   Elegir términos que cubran a favor y en contra (sinónimos, mecanismos alternativos).

2. **Leer los hits** (los `.txt`, no el PDF) y clasificar cada paper: **supports / challenges /
   method**. Ser honesto: buscar activamente contraejemplos, no solo confirmación.

3. **Reportar en el chat**: veredicto (sostiene / falla / parcial) con la evidencia citada
   `[[bibcode]]` y la búsqueda usada. **No archivar por default** (regla de `CLAUDE.md`: persistir
   una hipótesis es decisión explícita del usuario). Si el supuesto parece durable, **ofrecer**
   archivarlo. Sin pedido ("guardá como hipótesis…", "archivala"), la operación termina acá.

Los pasos 4–9 corren **sólo si el usuario pide archivar**:

4. **Registrar la hipótesis**: crear/actualizar `vault/wiki/concepts/hypotheses/<slug-hipotesis>.md`
   (afirmación, estado, **búsqueda reproducible** —el grep usado—, evidencia a favor, evidencia en
   contra/matices, implicación para el pipeline, gap a vigilar). Incluir un bloque Dataview que liste
   papers con `contains(thesis_links, "<slug>")`. (Una nota aparte `queries/<slug>_evidence.md` es
   opcional — sólo si el usuario quiere además el snapshot de la búsqueda como query archivada.)

5. **Taggear papers**: en cada `vault/wiki/papers/<bibcode>.md` relevante, poner
   `thesis_links: [<slug-hipotesis>]` y `bearing: supports|challenges|method`. Así la hipótesis
   acumula evidencia automáticamente.

6. **Bookkeeping**: actualizar `vault/wiki/index.md` y appendear a `vault/wiki/log.md`.

7. **Verificar citas**: correr el skill `verify-citations` sobre la nota de hipótesis (y, si tocaste
   prosa con citas en otra ficha/concepto, sobre eso también). Chequea afirmación por
   afirmación contra el fulltext (cita textual + nº de línea del `.txt` obligatorios; sin respaldo
   textual ⇒ no-soportada). Resolver cada no-soportada/parcial (bajar, reasignar cita, o marcar
   `inferencia`) y dejar el bloque `## Verificación de citas`. Clave acá: el `bearing`
   (supports/challenges) de cada paper debe reflejar lo que el texto **realmente** dice.

8. **Chequeo de salud**: correr `python scripts/lint.py` antes de commitear. Debe quedar en **0**
   para wikilinks rotos, huérfanas, contradicciones y `thesis_links` sin página destino; la **fuga de
   implementación** y las **citas no verificables** son WARN a revisar a mano (los "campos incompletos" son backlog). Ojo con el tag del nuevo
   `thesis_link`: tiene que matchear el nombre de la página de hipótesis (typo típico: guion vs guion_bajo).

9. **Cierre (commit + push).** Si la operación escribió en `vault/wiki/`, `git add` de los archivos
   **específicos** tocados (no `-A`) y commitear con mensaje descriptivo.
   Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Reporte
Veredicto explícito (sostiene / falla / parcial) y **en qué régimen** (tipo espectral, rango de
período, etc.). Declarar agregados (mean/median) según `CLAUDE.md`. No sobreestimar: un mecanismo
físico alternativo que rompa la hipótesis es un hallazgo, no un fracaso.
