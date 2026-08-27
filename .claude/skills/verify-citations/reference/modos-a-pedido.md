# Los dos modos a pedido: revalidación y benchmark

**Referencia de `verify-citations`.** Ninguno de los dos es paso de cierre —se corren **a pedido**—,
así que no tienen por qué ocupar el cuerpo del skill que se lee en cada verificación. Miden cosas
distintas y **ninguno sustituye al otro**: la revalidación mide si dos jueces independientes
coinciden sobre **contenido real**; el benchmark mide la detección de un error **plantado y
conocido**.

## Modo revalidación (a pedido) — volver a preguntar sobre lo que ya está verde

**Qué problema cierra.** El ancla de bloque y el hash de fuente (D-4/D-20) detectan que un par
**cambió**. Pero implican un supuesto que nunca se midió: que el veredicto es una **función** de
(afirmación, fuente) — si ninguno cambió, el resultado tampoco cambiaría. Lo produce un LLM. Hoy un
par verificado **no se vuelve a mirar nunca** mientras la nota y el `.txt` estén quietos, así que un
error del juez es **permanente y silencioso**: exactamente el modo de falla que toda la capa de
anclas existe para no producir.

**Qué hace.** Re-corre el fan-out sobre pares **ya verdes** —sin que nada haya cambiado— con
verificadores nuevos y **ciegos a los veredictos anteriores**, y compara.

```
1. Elegir la muestra: todos los pares de una nota, o N al azar del corpus (el usuario dice
   cuántos; no hay CLI — este skill es un modo de trabajo, como el benchmark de abajo).
2. Lanzar el fan-out normal (paso 2), un subagente por FUENTE, SIN pasarle la tabla vigente.
3. Comparar contra el bloque: por par, ¿mismo veredicto? ¿misma condición?
4. Reportar la DIVERGENCIA. No reescribir el bloque en silencio: los pares que cambian de veredicto
   se resuelven como cualquier hallazgo (paso 4).
```

**Cómo leer el resultado.** Medido el 2026-08-25 sobre HD 40307, dos corridas, 60 pares comparados:
**95 % de coincidencia (57/60)**, y las 3 divergencias caían todas en el borde `soportada`↔`parcial`
—valor que por eso se eliminó en 1.39.0—. `contradice` reprodujo 2/2.

⚠ **Confound de esa medición, declarado:** los prompts de la segunda corrida llevaban pistas
(«ojo con las citas de segunda mano, con las filas de otra estrella, con las frases que la fuente
desactiva después») que la primera no tenía. Así que ese 95 % **no es** una medición limpia de
varianza del juez. Para medirla hace falta correr con el prompt **idéntico**.

**Y el hallazgo que no depende del confound:** pares con **veredicto idéntico** trajeron
**condiciones distintas** entre corridas. El juez es estable en el eje textual y **no exhaustivo**
en el de régimen — así que «verde» garantiza menos de lo que parece, y ésa es la razón principal
para tener este modo.

**Distinto del benchmark de abajo:** aquél siembra citas **falsas deterministas** y mide detección
de un error **plantado y conocido**; esto mide si dos jueces independientes coinciden sobre
**contenido real**. Son preguntas distintas y ninguno sustituye al otro.

**Cuándo:** a pedido, o en la pasada periódica de `maintain` sobre una muestra. **No** es paso de
cierre: en el cierre nada cambió desde que se verificó, que es justo el caso que este modo explora.

## Modo benchmark (auto-test del verificador — a pedido)
¿Cuánto confiar en ese "juicio de LLM"? Este modo le pone un número: **recall sobre errores
plantados** (estilo CiteAudit). Correr **a pedido** (no es paso de cierre), con la bóveda ya
poblada y citada.

1. `python scripts/bench_verify.py seed [--max N]` → arma **dos** archivos (D-55):
   `build/verify_bench/exam.json` (el examen: N pares (afirmación, `[[bibcode]]`) **reales** de
   queries/concepts + un par **falso por construcción** por cada uno —misma afirmación, bibcode
   rotado a otro paper del corpus, determinista y nunca uno que esa afirmación cite de verdad—,
   con `id` neutro y **sin etiquetas ni conteos por clase**) y `build/verify_bench/key.json`
   (la clave). **Vos leés `exam.json` y nada más**: la ceguera dejó de depender de una instrucción
   y la sostiene la construcción, pero abrir la clave la rompe igual.
2. **Fan-out A CIEGAS** — mismo protocolo del paso 2 normal, con una regla extra **dura**: cada
   subagente recibe SOLO (afirmación, ruta al fulltext). **Nunca mostrarle `key.json`, el examen
   entero, ni decirle que es un benchmark** — sabría qué buscar y el número no mediría nada. (El
   examen entero tampoco: cada sembrada comparte el `claim` con su par real, así que quien lo lee
   completo deduce que uno de esos dos es falso —no cuál—. Con un par por subagente eso no se ve.)
3. Volcar cada veredicto en el campo `verdict` de su par en `exam.json`
   (`soportada|no-soportada|contradice|no verificable por extracción`).
4. `python scripts/bench_verify.py score` → recall de sembradas + reales caídas →
   `outputs/verify-bench-<fecha>.md`.
5. **Reporte honesto al chat:** el recall; cada sembrada que PASÓ (revisar a mano — puede ser
   **soporte casual**: el otro paper de verdad dice lo mismo — antes de culpar al verificador); y
   cada real caída (flaky del verificador **o** error de grounding genuino de la nota: si es lo
   segundo, corregir la nota por el flujo normal de arriba).

**Regla #0:** nada del benchmark entra a `vault/` — pares sembrados y reportes viven en
`build/`/`outputs/` (scratch gitignored). Las citas falsas no son bibliografía.
