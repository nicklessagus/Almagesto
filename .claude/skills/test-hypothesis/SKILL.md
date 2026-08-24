---
name: test-hypothesis
description: Usar cuando el usuario plantea una hipótesis/supuesto y pide evidencia a favor o en contra en el corpus de la bóveda ("hipótesis: ...", "buscá evidencia que apoye o rechace que ...", "¿el corpus sostiene que ...?", "guardá como hipótesis que ..."). Testea contra el texto completo y responde con veredicto citado; archiva la hipótesis y taggea papers SÓLO si el usuario lo pide.
version: 1.5.0
---

# Test de hipótesis contra el corpus

Operación **query** del patrón LLM Wiki, especializada para supuestos **durables** de la tesis.
Distinción: una hipótesis es un supuesto que se sostiene y acumula evidencia → vive en
`vault/wiki/concepts/hypotheses/`. Una búsqueda de una vez NO es hipótesis (usar `query-corpus`).

⛔ **El test corre sobre los FULLTEXTS, no sobre la ficha (D-33).** Testear contra la ficha es
testear contra la **síntesis anterior del propio agente**, no contra las fuentes — y la ficha está
**podada a propósito** (la regla de poda tira lo que no cambia cómo se lee una señal RV), así que la
hipótesis puede ser exactamente sobre algo que la poda descartó. La ficha se usa como **mapa** (qué
papers hay, qué se dijo ya), nunca como fuente.

**Los no-core no son una decisión: no tienen fulltext.** Nunca se bajaron; de ellos existe sólo la
metadata de ADS en `## Excluidos por el filtro`. Para incluir uno hay que hacerlo core primero
(`extra_core` en `stars.yaml`/`themes.yaml`) y bajarlo — y eso **cambia el alcance** (paso 0).

**Una hipótesis NO es un radio (D-35).** Un radio tiene exactamente un hub; una hipótesis cruza
varias entidades (`achromaticity` toca `crx`, `shift_vs_shape` y además estrellas). `hypotheses` es
área reservada aparte: los papers apuntan con `thesis_links`, la nota acumula la tabla de evidencia,
y los conceptos que toca se linkean con `[[wikilink]]` **en los dos sentidos** — sin la relación
padre-hijo de un hub/radio.

## Pasos

0. **Declarar el ALCANCE antes de buscar (D-34).** Una hipótesis es **transversal**: se plantea
   sobre un conjunto de entidades. Como los fulltexts viven por slug, acotar a entidades es acotar a
   **directorios de `vault/raw/fulltext/`** — así que el alcance es a la vez la definición del
   universo y el comando de búsqueda.

   Va **escrito en la nota**, porque **define qué significa el veredicto**: *"no hay evidencia"* no
   es *"no existe evidencia"*, es *"no hay evidencia en estos temas, con estos 190 papers, a esta
   fecha"*. Sin el alcance escrito, un veredicto negativo se lee como **universal** — el mismo
   *afirmar de más* que la bóveda persigue en todos lados. Formato (blockquote, arriba de la nota):

   ```
   > Alcance 2026-08-23 · temas: [ica, crx, shift_vs_shape] + estrellas: [tau_ceti, au_mic]
   >                    · 190 papers · 47 con hits
   ```

   Los conteos salen del propio universo, no a ojo:
   ```bash
   ls vault/raw/fulltext/<slug>/*.txt | wc -l        # papers del slug (repetir por slug del alcance)
   ```

   **Y el alcance CRECE.** Sumar un tema deja el veredicto testeado contra un universo que ya no es
   el vigente — misma familia de staleness que los pares de verificación. El lint compara el alcance
   declarado contra el corpus de esos directorios y marca la hipótesis si quedó corta; cerrarlo es
   re-correr el test sobre lo nuevo y re-estampar la línea.

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

2. **Leer los hits** (los `.txt`, no el PDF) y clasificar cada paper: **apoya / desafía / método**.
   Ser honesto: buscar activamente contraejemplos, no solo confirmación. La postura **de cada
   paper** se anota junto con **la cita textual que la sostiene** (frase + nº de línea del `.txt`):
   sin cita no es evidencia, es opinión — y es lo que hace que la tabla del paso 4 sea verificable.

> ⚠ **Si vas a reportar un número, mirá `pdf_source` de la nota del paper** (#57): con `eprint` el
> `.txt` es el **preprint** y el valor puede no ser el de la versión publicada; con `null` no se
> sabe. Decilo al reportar ("según el eprint de X") en vez de presentarlo como el valor publicado.

3. **Reportar en el chat**: veredicto (sostiene / falla / parcial) con la evidencia citada
   `[[bibcode]]` y la búsqueda usada. **No archivar por default** (regla de `CLAUDE.md`: persistir
   una hipótesis es decisión explícita del usuario). Si el supuesto parece durable, **ofrecer**
   archivarlo. Sin pedido ("guardá como hipótesis…", "archivala"), la operación termina acá.

Los pasos 4–9 corren **sólo si el usuario pide archivar**:

4. **Registrar la hipótesis**: crear/actualizar `vault/wiki/concepts/hypotheses/<slug-hipotesis>.md`
   con la afirmación, el **blockquote de alcance** del paso 0, la **búsqueda reproducible** (el grep
   usado, tal cual), la **tabla de evidencia**, el gap a vigilar, y los `[[wikilink]]` a los
   conceptos que toca (en los dos sentidos, D-35).

   **La tabla de evidencia es el cuerpo de la nota (D-21).** Una fila por paper, con la postura y su
   respaldo:

   | Paper | Postura | Qué dice (cita textual) | L | Régimen |
   |---|---|---|---|---|
   | `[[2019Zechmeister]]` | apoya | "the chromatic index correlates with…" | 412 | HARPS, M enanas |

   Por qué acá y no en el paper: la postura **depende de la tesis** —un paper puede tocar varias— y
   como escalar suelto en la nota del paper es **un veredicto sin evidencia que `verify-citations`
   no puede chequear** (no hay nada que un subagente pueda ir a mirar). En la tabla hay
   naturalmente una fila por par, con cita: es verificable. ⛔ El campo `bearing` en una nota de
   paper es **schema viejo y el lint lo bloquea** (migrador: `make_notes.py --migrate-bearing`).

   **`status` con vocabulario CERRADO (D-37)** — el lint lo valida y bloquea lo que no esté en la
   lista (`status: supuesto operativo con caveat conocido` era prosa libre que nadie validaba):

   | `status` | Significa |
   |---|---|
   | `abierta` | planteada, sin evidencia suficiente |
   | `sostenida` | la evidencia del corpus la apoya |
   | `disputada` | hay evidencia en los dos sentidos |
   | `refutada` | la evidencia la contradice |

   Se **deriva de la tabla**: si hay filas `desafía` y el status sigue en `sostenida`, el lint lo
   marca. No es un campo que se elige: es un resumen de lo que la tabla ya dice.

   **Qué es grounded y qué es inferencia (D-36).** No es "todo inferencia del agente":

   | Qué | Es | ¿Verificable? |
   |---|---|---|
   | cada **fila de evidencia** | cita textual + nº de línea del `.txt` | **sí**, pasa por `verify-citations` |
   | el **veredicto global** | agregar N filas en una conclusión → juicio del agente | **no** → va marcado `(inferencia de [[b1]], [[b2]])` |

   La primera es la mayor parte del contenido y es transcripción con respaldo; el segundo es una
   línea y va marcada como lo que es — **con sus premisas nombradas**: una `inferencia` pelada la
   bloquea el lint, porque sin premisas no se puede auditar de qué se dedujo.

   (Una nota aparte `queries/<slug>_evidence.md` es opcional — sólo si el usuario quiere además el
   snapshot de la búsqueda como query archivada.)

5. **Taggear papers — sólo el puntero**: en cada `vault/wiki/papers/<bibcode>.md` relevante, agregar
   `thesis_links: [<slug-hipotesis>]`. Es un puntero **mecánico y add-only**, como `stars:`: dice
   *"este paper toca esa tesis"*, no qué opina de ella. La opinión ya vive en la tabla del paso 4.

6. **Bookkeeping**: actualizar `vault/wiki/index.md` y appendear a `vault/wiki/log.md`.

7. **Verificar citas**: correr el skill `verify-citations` sobre la nota de hipótesis (y, si tocaste
   prosa con citas en otra ficha/concepto, sobre eso también). Chequea afirmación por
   afirmación contra el fulltext (cita textual + nº de línea del `.txt` obligatorios; sin respaldo
   textual ⇒ no-soportada). Resolver cada no-soportada/parcial (bajar, reasignar cita, o marcar
   `inferencia`) y dejar el bloque `## Verificación de citas`. **Las filas de la tabla de evidencia
   son pares como cualquier otro** y entran al fan-out: la postura de cada paper tiene que reflejar
   lo que el texto **realmente** dice, y ahí es donde se comprueba. El veredicto global no entra —
   está marcado `inferencia`, que es justamente la declaración de que no hay fuente que lo diga.

8. **Chequeo de salud**: correr `python scripts/lint.py --cierre` antes de commitear. Debe quedar en **0**
   en las **categorías bloqueantes**: cuáles son lo decide el `exit code` del lint (1 si hay), y la
   lista canónica vive en `CLAUDE.md` — **no la copies acá**, que es cómo se desincronizó antes. La
   **fuga de implementación** y las **citas no verificables** son WARN a revisar a mano (los "campos
   incompletos" son backlog). Ojo con el tag del nuevo
   `thesis_link`: tiene que matchear el nombre de la página de hipótesis (typo típico: guion vs guion_bajo).

8b. **Contradicciones en los ejes tocados (D-39).** Si la hipótesis puso a dos papers a hablar del
   mismo hecho, correr `find-contradictions` **acotado a esos ejes** (no a todo el corpus): el
   embudo corre sobre las extracciones, así que es barato, y agarra el caso que la tabla de
   evidencia no ve — dos papers que discrepan sobre un eje que ninguna ficha mencionó.

9. **Cierre (commit + push).** Si la operación escribió en `vault/wiki/`, `git add` de los archivos
   **específicos** tocados (no `-A`) y commitear con mensaje descriptivo.
   Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Reporte
Veredicto explícito (sostiene / falla / parcial) y **en qué régimen** (tipo espectral, rango de
período, etc.). Declarar agregados (mean/median) según `CLAUDE.md`. No sobreestimar: un mecanismo
físico alternativo que rompa la hipótesis es un hallazgo, no un fracaso.
