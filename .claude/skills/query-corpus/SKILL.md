---
name: query-corpus
description: Usar cuando el usuario hace una búsqueda o pregunta general contra el corpus de la bóveda que NO es un test de hipótesis ("buscá en el corpus ...", "qué se sabe del P_rot de GJ 581", "qué papers usan ESPRESSO", "qué métodos se aplicaron a tau Ceti", "qué celdas de la matriz están vacías").
version: 1.4.0
---

# Query: búsqueda/pregunta general contra el corpus

Operación **query** del patrón LLM Wiki para preguntas generales (no supuestos durables; para eso
usar `test-hypothesis`).

## Pasos

1. **Mirar el índice y el frontmatter** primero: `vault/wiki/index.md`, las fichas `vault/wiki/stars/*.md`
   (frontmatter máquina-legible) y `vault/raw/ground_truth/*.json` suelen tener la respuesta directa
   (P_rot, planetas, indicadores, métodos aplicados).
   ⚠ **Un campo de ground-truth en `null` NO significa "no se sabe" (#70):** el frontmatter es
   **espejo puro de NEA**, y NEA calla seguido (`K`, `e`, `P_rot`). El valor de la literatura vive
   en el **cuerpo, citado** — leelo antes de responder "no hay dato". Y si el eje está en disputa, la
   respuesta completa está en el **`## Inventario por eje`** (#72): ahí figura qué dice cada paper,
   con su método. La bóveda **no adopta** un valor; reportá el estado de la literatura igual.

2. **Si hace falta el texto**, grep sobre el texto completo local:
   ```bash
   grep -ril "<términos>" vault/raw/fulltext/                # qué papers
   grep -in  "<términos>" vault/raw/fulltext/<slug>/<bib>.txt # contexto en uno
   ```
   Leer los `.txt` relevantes (no los PDFs).

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

> ⚠ **Si vas a reportar un número, mirá `pdf_source` de la nota del paper** (#57): con `eprint` el
> `.txt` es el **preprint** y el valor puede no ser el de la versión publicada; con `null` no se
> sabe. Decilo al reportar ("según el eprint de X") en vez de presentarlo como el valor publicado.

3. **Sintetizar** con citas `[[bibcode]]` y, cuando aplique, links a `[[slug]]` y conceptos.

4. **Archivar SÓLO si el usuario lo pide** (regla de `CLAUDE.md`: por default la respuesta vive en
   el chat; persistir una query es decisión explícita del usuario, para no llenar la wiki de notas
   no deseadas). Si la pregunta parece valer re-preguntarla (p. ej. el pipeline va a cambiar),
   **ofrecer** archivarla. Si el usuario acepta: guardar en `vault/wiki/queries/<slug>.md` cumpliendo
   el estándar de ficha (autosuficiente, búsqueda reproducible —el grep usado—, citas `[[bibcode]]`)
   y actualizar `vault/wiki/log.md`.

5. **Verificar citas (si se archivó en `vault/wiki/`)**: correr el skill `verify-citations` sobre la nota
   archivada — chequea afirmación por afirmación contra la fuente (#205: el **PDF**, con cita
   textual + nº de **página** obligatorios y la fila anclada `pdf:<sha10>`; el `.txt` sólo ubica con
   `grep`, y queda como fuente citada por línea únicamente en la fuente **web**; sin respaldo
   textual ⇒ no-soportada). Resolver cada no-soportada/contradice
   (bajar la afirmación a lo que dice la fuente, reasignar la cita al bibcode correcto, o marcar
   `inferencia`) y dejar el bloque `## Verificación de citas` en la nota.

6. **Chequeo de salud (si se escribió en `vault/wiki/`)**: correr `python scripts/lint.py --cierre` antes de
   commitear. Debe quedar en **0** en las **categorías bloqueantes**: cuáles son lo decide el
   `exit code` del lint (1 si hay), y la lista canónica vive en `CLAUDE.md` — **no la copies acá**,
   que es cómo se desincronizó antes. La **fuga de implementación** es WARN a revisar a mano; las
   **citas no verificables** (`unverifiable`) y los "campos incompletos" son backlog, no bloquean. Si creaste un `thesis_link`/concepto nuevo, verificá que el tag matchee el
   nombre de la página (typo típico: `shift-vs-shape` vs `shift_vs_shape`).

7. **Cierre (commit + push).** **Solo si se archivó algo en `vault/wiki/`** (si la respuesta quedó solo en
   el chat, no hay cierre): `git add` de los archivos **específicos** tocados (no `-A`) y commitear
   con mensaje descriptivo. Después **preguntar al usuario si hace `push`** — no
   pushear sin confirmación.

## Salida
Por defecto responder en el chat. Si el usuario lo pide, generar un `.md` (o tabla, o figura) y
"filearlo" de vuelta en `vault/wiki/` para que la exploración sume. Declarar agregados (mean/median)
según `CLAUDE.md`. Cuidado con outliers antes de afirmar correlaciones.
