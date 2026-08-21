---
name: test-hypothesis
description: Usar cuando el usuario plantea una hipótesis/supuesto y pide evidencia a favor o en contra en el corpus de la bóveda ("hipótesis: ...", "buscá evidencia que apoye o rechace que ...", "¿el corpus sostiene que ...?", "guardá como hipótesis que ..."). Testea contra el texto completo y responde con veredicto citado; archiva la hipótesis y taggea papers SÓLO si el usuario lo pide.
version: 1.3.0
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

> **Cómo grepear el `.txt` — rigen las convenciones de `verify-citations` (canónicas allá, acá sólo
> el puntero):** el `.txt` de `pdftotext -layout` **entrelaza las dos columnas en la misma línea
> física** (medido: 472/644 del corpus, 73%), y `grep` es orientado a líneas → buscar la oración
> entera da **falso negativo** aunque el texto esté y sea legible (medido: 9/24 pares, ~38%).
> Patrones **cortos** (un fragmento distintivo de 3–6 palabras, o términos sueltos), nunca la frase
> completa; si tampoco aparece, reintentar **partiendo por el guión de corte** (`mag-`/`nitude`); y
> **prohibido normalizar espacios** sin partir antes cada línea física en la canaleta (empalma el
> final de una columna con el principio de la otra y fabrica adyacencias que el paper no tiene).
>
> ⛔ **Un `grep` en 0 NO es una ausencia** hasta agotar esa escalera. Acá el modo de falla es **peor**
> que en `verify-citations`: allá un falso negativo degrada un veredicto visible; acá **fabrica una
> ausencia** —"el corpus no dice nada de X"— que sale al chat como conclusión, se usa para decidir y
> no deja ningún rastro de que fue un artefacto de grep. Se suma al caveat de los papers
> **pre-digitales** (el OCR del escaneo de ADS pierde ~½ de las filas de tabla, y las tablas viejas
> suelen ser imágenes): ante un 0, o se **corrobora** por otra vía (papers que lo citan, PDF/tabla
> abiertos) o se reporta **inconcluso**, no ausencia.

2. **Leer los hits** (los `.txt`, no el PDF) y clasificar cada paper: **supports / challenges /
   method**. Ser honesto: buscar activamente contraejemplos, no solo confirmación.

> ⚠ **Si vas a reportar un número, mirá `pdf_source` de la nota del paper** (#57): con `eprint` el
> `.txt` es el **preprint** y el valor puede no ser el de la versión publicada; con `null` no se
> sabe. Decilo al reportar ("según el eprint de X") en vez de presentarlo como el valor publicado.

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
   en las categorías bloqueantes (wikilinks rotos, frontmatter no parseable, papers retractados,
   huérfanas, contradicciones GT↔ficha, masa inconsistente, `thesis_links`/`disputes[].ref`
   colgantes — el exit code las separa solo); la **fuga de
   implementación** y las **citas no verificables** son WARN a revisar a mano (los "campos incompletos" son backlog). Ojo con el tag del nuevo
   `thesis_link`: tiene que matchear el nombre de la página de hipótesis (typo típico: guion vs guion_bajo).

9. **Cierre (commit + push).** Si la operación escribió en `vault/wiki/`, `git add` de los archivos
   **específicos** tocados (no `-A`) y commitear con mensaje descriptivo.
   Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Reporte
Veredicto explícito (sostiene / falla / parcial) y **en qué régimen** (tipo espectral, rango de
período, etc.). Declarar agregados (mean/median) según `CLAUDE.md`. No sobreestimar: un mecanismo
físico alternativo que rompa la hipótesis es un hallazgo, no un fracaso.
