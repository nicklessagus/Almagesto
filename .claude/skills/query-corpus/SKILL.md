---
name: query-corpus
description: Usar cuando el usuario hace una búsqueda o pregunta general contra el corpus de la bóveda que NO es un test de hipótesis ("buscá en el corpus ...", "qué se sabe del P_rot de GJ 581", "qué papers usan ESPRESSO", "qué métodos se aplicaron a tau Ceti", "qué celdas de la matriz están vacías").
version: 1.0.0
---

# Query: búsqueda/pregunta general contra el corpus

Operación **query** del patrón LLM Wiki para preguntas generales (no supuestos durables; para eso
usar `test-hypothesis`).

## Pasos

1. **Mirar el índice y el frontmatter** primero: `vault/wiki/index.md`, las fichas `vault/wiki/stars/*.md`
   (frontmatter máquina-legible) y `vault/raw/ground_truth/*.json` suelen tener la respuesta directa
   (P_rot, planetas, indicadores, métodos aplicados).

2. **Si hace falta el texto**, grep sobre el texto completo local:
   ```bash
   grep -ril "<términos>" vault/raw/fulltext/                # qué papers
   grep -in  "<términos>" vault/raw/fulltext/<slug>/<bib>.txt # contexto en uno
   ```
   Leer los `.txt` relevantes (no los PDFs).

3. **Sintetizar** con citas `[[bibcode]]` y, cuando aplique, links a `[[slug]]` y conceptos.

4. **Archivar si vale la pena re-preguntarlo** (sobre todo si el pipeline va a cambiar): guardar en
   `vault/wiki/queries/<slug>.md`. Si es descartable, basta la respuesta en el chat. Actualizar
   `vault/wiki/log.md` si se archivó.

5. **Verificar citas (si se archivó en `vault/wiki/`)**: correr el skill `verify-citations` sobre la nota
   archivada — chequea afirmación por afirmación contra el fulltext (cita textual + nº de línea del
   `.txt` obligatorios; sin respaldo textual ⇒ no-soportada). Resolver cada no-soportada/parcial
   (bajar la afirmación a lo que dice la fuente, reasignar la cita al bibcode correcto, o marcar
   `inferencia`) y dejar el bloque `## Verificación de citas` en la nota.

6. **Chequeo de salud (si se escribió en `vault/wiki/`)**: correr `python scripts/lint.py` antes de
   commitear. Debe quedar en **0** para wikilinks rotos, huérfanas, contradicciones y
   `thesis_links` sin página destino; la **fuga de implementación** y las **citas no verificables** son
   WARN/precondición a revisar a mano (los "campos incompletos" son backlog, no bloquean). Si creaste un `thesis_link`/concepto nuevo, verificá que el tag matchee el
   nombre de la página (typo típico: `shift-vs-shape` vs `shift_vs_shape`).

7. **Cierre (commit + push).** **Solo si se archivó algo en `vault/wiki/`** (si la respuesta quedó solo en
   el chat, no hay cierre): `git add` de los archivos **específicos** tocados (no `-A`; ver `CLAUDE.md`
   global) y commitear con mensaje descriptivo. Después **preguntar al usuario si hace `push`** — no
   pushear sin confirmación.

## Salida
Por defecto responder en el chat. Si el usuario quiere, generar un `.md` (o tabla, o figura) y
"filearlo" de vuelta en `vault/wiki/` para que la exploración sume. Declarar agregados (mean/median)
según `CLAUDE.md`. Cuidado con outliers antes de afirmar correlaciones.
