---
name: verify-citations
description: Usar para verificar, afirmación por afirmación, que las citas [[bibcode]] de una nota de la wiki (query, hipótesis, ficha, concepto) realmente están respaldadas por el texto completo de la fuente. Se corre como paso de cierre al armar/editar una query o hipótesis, o cuando el usuario pide "rechequeá las citas / ¿esto lo dice el paper?". Implementa el chequeo claim↔evidencia (pipeline tipo CiteAudit) sobre el corpus cerrado de la bóveda. Veredictos: soportada / no-soportada (la fuente calla) / contradice (la fuente afirma lo contrario → candidata a disputa, no sólo cita rota), en un EJE SEPARADO de la `condición` bajo la que la fuente lo afirma; en transcripciones de tablas/listas chequea además la completitud (lo que la nota omite).
version: 1.11.0
---

# Verify-citations — chequeo claim↔evidencia contra el fulltext

Operación de **verificación** del patrón LLM Wiki (extensión propia de esta wiki; el lint canónico de
Karpathy sólo hace chequeos de salud estructurales, **no** valida que la fuente respalde la afirmación).
Tapa el *grounding gap* / *epistemic drift*: el LLM puede escribir una cita correcta junto a una
afirmación que el paper **no dice** (estudios: 50–90% de citas en texto largo de LLM no están
plenamente respaldadas). Acá cada afirmación se contrasta contra el texto real de su fuente.

> **Ventaja del corpus cerrado:** hay un `.txt` por bibcode en `vault/raw/fulltext/`, así que se
> saltea el *retrieval* —la parte que mete errores en los verificadores generales—: ya sabemos qué
> archivo leer. El chequeo es passage-matching directo, y el `.txt` es una extracción **determinista**
> (`pdftotext -layout`, sin LLM), así que **la cita textual son las palabras reales del paper**.

⛔ **Las reglas duras de lectura del `.txt`, en una línea cada una.** El **por qué** de cada una, con
su medición, está en `reference/convenciones-fulltext.md` — leelo la primera vez y cuando una regla
parezca arbitraria o un par no cierre:

| Regla | En una línea |
|---|---|
| **nº de línea** (#29) | con `grep -n` o leyendo el archivo; **nunca** `splitlines()` de Python (los form feeds corren la numeración +1 por página). `split("\n")` numera igual que `grep -n`. |
| **patrones cortos** (#44) | escalera de acortamiento: oración completa → fragmento distintivo de 3–6 palabras contenido en **una línea física** → reintento partiendo por el guión de corte. Un `.txt` a dos columnas entrelaza ambas en la misma línea. |
| ⛔ **no normalizar espacios** (#46) | ni sobre el archivo entero ni por línea: empalma el final de la columna 1 con el principio de la columna 2 y **fabrica adyacencias** (falso positivo). Si hace falta, partí antes cada línea en la canaleta (run de 8+ espacios, `measure_layout.CANALETA_MIN`) y normalizá por segmento. |
| **`symbols_lost: true`** (#113) | las ecuaciones **no están** en el `.txt`: citar por **página del PDF**, no por línea. ⛔ No declares `no-soportada` una ecuación ausente de una fuente marcada así. |
| **`fulltext_source: ocr`** | citable **con salvedad**: el OCR puede errar símbolos y notación. Ante discrepancia de símbolos, abrir el PDF en vez de declarar `no-soportada`/`contradice`. |
| **`pdf_source: eprint`** (#57) | el `.txt` es el **preprint**: una discrepancia numérica contra un valor publicado es candidata a **diferencia de versión**, no a cita rota. ⛔ Nunca "corregir" la nota hacia el eprint. `null` = desconocido, que **no** es "publicado". |
| **agotar antes de concluir** | sólo agotadas la escalera y el de-hifenado corresponde considerar artefacto de extracción → abrir el PDF o marcar `no verificable por extracción` (distinto de `no-soportada`). |

## Cuándo correrlo
- **Paso de cierre obligatorio de toda operación que escriba prosa con `[[bibcode]]`** (regla de
  `CLAUDE.md`), **antes de lint/commit**: `ingest-star` (ficha + papers, paso 5b), `ingest-theme`
  (concept + papers, paso 6b), `append-knowledge` (paso 5), `find-contradictions` (paso 5, las
  disputas nuevas), `maintain` (sub-modo A cuando re-sintetiza, y E cuando resuelve una verificación
  stale), y `query-corpus` / `test-hypothesis` cuando archivan.
- A pedido: "rechequeá las citas", "¿esto lo dice el paper?", al editar una nota con citas.

## Entrada
La **ruta de la nota** a verificar (p. ej. `vault/wiki/queries/crx-slope-values.md`). Si no se da, usar la
última nota tocada en la operación en curso.

## Pasos

### 1. Extraer los pares (afirmación, referencia)
Leer el cuerpo de la nota (no el frontmatter) y descomponerlo en **afirmaciones atómicas**: cada
fila de tabla con un valor, cada bullet o frase que asevera un hecho. Para cada afirmación, listar
**cada `[[bibcode]]` que la acompaña por separado** (si una afirmación cita `[[A]]` y `[[B]]`, son
**dos pares** — cada fuente debe respaldar la parte que se le atribuye; así se atrapan las mezclas
"el dato de A atribuido a B").

> **Herencia de cita en tablas y listas (#49).** Una fila de tabla casi nunca lleva su propio
> `[[bibcode]]`: la cita vive en el **caption**, en el **párrafo que introduce la tabla** o en el
> **encabezado de la sección** (p. ej. `**Keywords QC de la receta científica** ([[X]], §9.7.4):`).
> Emparejar sólo "lo que acompaña" a la afirmación deja esas filas **fuera del fan-out** y la tabla
> entera se cierra sin chequear (medido en una ficha real: **46 de 64 filas, 72%** — y no era
> material accesorio: eran las tablas de keywords con su significado y unidad, las extensiones FITS
> y los defaults de la receta, o sea lo que el consumidor de la bóveda efectivamente lee).
> **Regla:** cada fila/ítem **hereda el `[[bibcode]]` del ámbito que la introduce** — el más cercano
> hacia arriba: caption → párrafo introductorio → encabezado de sección — y **entra al fan-out como
> par propio** con esa atribución. Si **ningún** ámbito hacia arriba cita una fuente, la tabla/lista
> cae en el flag **"afirmación sin cita"** del final de este paso (no se saltea en silencio). Las
> filas de la **tabla de inventario** marcadas NEA siguen bajo la excepción de ground-truth de abajo.

**Excepciones (no se verifican, pero se chequea la marca):**
- **Valores de ground-truth (NEA) en fichas de estrella** → los parámetros planetarios (P/K/e/m·sin i,
  status, nº de planetas) del **frontmatter** y de la **tabla de inventario** vienen de **NEA**
  (`vault/raw/ground_truth/<slug>.json`), **no** de un paper. **NO se verifican contra el fulltext** — de su
  consistencia se ocupa el **lint** (contradicción GT↔ficha + masa implícita por K/P/e/M\*). Verificar
  un valor NEA contra un paper es un **error de categoría** (el paper de descubrimiento suele dar un
  valor algo distinto al best-value combinado de NEA, y eso NO es una cita rota). Regla: si el número
  está en la tabla de inventario / frontmatter y la fila dice "NEA", se **saltea**.
- **Sí se verifican** (van al fan-out) las afirmaciones atribuidas a un `[[bibcode]]`: las
  **disputas** (cada `posiciones[].value` y el `note` vs el paper que la sostiene — p. ej. la Tabla 9
  de Díaz+2016; la posición `{source: ground_truth}` NO se verifica contra papers, es ground-truth),
  los **mecanismos**, la **síntesis**, y cualquier **valor que el prose atribuya a un paper** (si la
  oración cita a Mayor+2009, el número debe ser el de Mayor, no el de NEA → si no, corregir el prose a
  los valores de la fuente y dejar NEA en la tabla).
- Afirmaciones marcadas **`inferencia`** explícitamente → se **saltean** del fan-out y se listan aparte
  como "inferencia declarada" (válidas sin cita; ver frontera/estilo en `CLAUDE.md`).
- Definiciones/derivaciones internas (sanity-checks de unidades, etc.) sin `[[bibcode]]` → no requieren
  fuente, pero si **afirman un hecho del mundo** sí.
- Una afirmación con número/aseveración fáctica y **sin** `[[bibcode]]` ni marca `inferencia` →
  **flag "afirmación sin cita"** (hay que citarla o marcarla inferencia).

### 2. Fan-out: un subagente independiente por FUENTE
Agrupar los pares **por bibcode** y lanzar un subagente (tipo `Explore`) por fuente, **en paralelo**
(varios en un mismo mensaje). Cada uno juzga **todos los pares que citan su fuente**.

> ⚠ **Por fuente, no por par (#100).** Lo que hace fuerte al chequeo es el **aislamiento** —cada
> verificador ve un solo `.txt`, sin memoria, sin otros papers— y agrupar por fuente lo conserva
> intacto: el subagente sigue leyendo un único archivo. Lo que se evita es pagar la lectura N veces.
> Medido el 2026-08-25 sobre una ficha real: **68 pares sobre 16 fuentes → 52 re-lecturas**, con 18
> subagentes abriendo los mismos 300 KB.

Cada uno:
- Localiza el fulltext: `vault/raw/fulltext/**/<bibcode>.txt` (el bibcode puede vivir bajo cualquier
  slug/tema — usar glob). **Ojo:** los nombres tienen `&` y puntos → citarlos entre comillas simples
  al leer/grep.
- Lee **sólo ese archivo** (grounding-first; **prohibido** responder de memoria o de otro paper).
- Devuelve, para la afirmación dada:
  - `veredicto`: `soportada` | `no-soportada` | `contradice` — **vocabulario cerrado**, y el eje es
    **sólo el respaldo textual**: ¿la fuente dice esto? La pregunta «¿está completa la afirmación?»
    vive en `condicion`, que es una columna aparte. **Distinguir los dos modos
    de falla** (alineado al estándar de 4 categorías tipo CAQA): `no-soportada` = la fuente **calla**
    (no dice nada de eso → error de cita); `contradice` = la fuente **afirma lo contrario** (valor
    incompatible más allá del error, existencia negada, signo opuesto) — también exige cita textual,
    de lo que el paper **sí** dice.
  - `evidencia`: **cita textual** del paper + **nº de línea** (contado como `grep -n` — ver la
    convención fija de arriba; nunca `splitlines()` de Python). **Sin cita textual ⇒ `no-soportada`**
    (regla dura: si no puede pegar la frase, no está respaldado). La cita tiene que tocar el
    **contenido distintivo** de la afirmación (el sujeto/valor/mecanismo que la hace específica); si
    lo único que matchea es terreno común del tema (el fenómeno general, un término suelto, la mera
    cercanía temática) ⇒ `no-soportada`. **Sin punto medio**: ablandar un claim genérico a un
    veredicto tibio es el modo de falla típico del verificador — es exactamente lo que mide el
    benchmark, y por eso `parcial` salió del vocabulario en 1.39.0 (ver abajo).
  - `nota`: una línea de por qué (sobre todo en `no-soportada`: qué dice el paper en cambio).
    Si la afirmación es **multi-cláusula**, decir **qué cláusula** respalda el paper y cuáles no.
  - `condicion` (**siempre; el hallazgo que ninguna capa veía, #74**): ¿el paper afirma esto **bajo
    condiciones** que la nota no dice? (SNR, muestreo, tamaño de muestra, definición del observable,
    época, rango de parámetros). Si sí, **citarlas**. Es un **hallazgo aparte**, no un grado de
    soporte: la afirmación pelada **sí está** en el paper, así que el veredicto sigue siendo
    `soportada` — por eso la sobre-generalización pasaba entera por este chequeo. Es el "afirmar de
    menos" de las tablas truncadas, en versión conceptual: la nota no afirma falso, afirma **de
    más**. En una nota de **concepto** la resolución tiene lugar propio: la condición va a
    `## Régimen de validez`; en una ficha, se agrega a la afirmación.
  - `completitud` (**sólo cuando el par sale de una transcripción** de tabla o lista de la fuente):
    ¿la tabla/lista del paper tiene **más filas/ítems** que los que la nota transcribe? Si sí,
    **listarlos** (con nº de línea). Es un **hallazgo aparte**, no un grado de soporte: no cambia el
    veredicto de la fila que sí está.

> **Claims multi-cláusula (espeja la regla del paso 1).** Una afirmación suele arrastrar varias
> cláusulas: una de encuadre sin cita, la atribuida a *esta* fuente, y a veces las de *otras*
> fuentes citadas al lado. El subagente juzga **la parte que se le atribuye a su paper** — que el
> archivo respalde una cláusula vecina (de otra fuente, o el encuadre genérico) **no** hace
> `soportada` a la afirmación: es exactamente la mezcla "el dato de A atribuido a B" que este
> chequeo existe para atrapar. Sin esta instrucción el subagente juzga el conjunto y **hedgea**.
> Medido el 2026-08-25: de 14 defectos reales encontrados en una ficha, **3 eran justamente eso**
> —un número leído en A que A atribuye a B— y uno sobrevivió una corrida entera como veredicto tibio
> antes de que la segunda lo llamara `no-soportada` tras grepear el archivo y no encontrarlo.

> **Transcripciones: chequear también lo que la nota OMITE (#49).** El fan-out valida lo que la nota
> **afirma**; una tabla transcrita **sin un solo error** pero a la que le faltan filas vuelve
> **100% soportada** — cada par verificado era verdadero (medido: 14 registros transcritos, los 14
> correctos pese a un `.txt` que entrelaza tres columnas… sobre una tabla de **21 filas** en el
> paper). Es un modo de falla **distinto** del *grounding gap*: la nota no afirma nada falso,
> **afirma de menos**, y una tabla truncada se lee como completa. Por eso, cuando el par sale de una
> **transcripción** (tabla o lista de la fuente), el subagente recibe además la pregunta de
> **completitud** (arriba) y el faltante se reporta como **hallazgo propio**, distinto del veredicto
> de soporte. Vale para cualquier enumeración que la nota presente como cerrada (una lista de
> máscaras, de extensiones, de keywords), no sólo para tablas con pipes.
>
> El caso más frecuente de esto en una bóveda es el **`## Inventario por eje`** (#72), que es
> transcripción por construcción: cada fila dice qué reporta un paper sobre un eje en disputa. Ahí
> la pregunta de completitud no es "¿la fuente tiene más filas?" sino **"¿hay más papers del corpus
> que reportan este eje y no están en la tabla?"** — un inventario sin errores pero **incompleto**
> vuelve 100% soportado y se lee como el estado de la literatura.

Prompt sugerido por agente: *"Leé SOLO `<ruta fulltext>`. ¿El paper respalda esta afirmación: «…»?
Si la afirmación tiene varias cláusulas atribuidas a distintas fuentes, juzgá si el archivo respalda
**la cláusula que le toca** y decí cuál en la nota — que respalde una cláusula vecina de otra fuente,
o el encuadre genérico, no cuenta. Respondé veredicto
(soportada/no-soportada/contradice) + cita textual con nº de línea (el que da
`grep -n` o la lectura directa del archivo; NO uses `splitlines()` de Python — los form feeds del
`.txt` corren la numeración) + nota. Para localizar: el `.txt` suele entrelazar dos columnas en la
misma línea física, así que si la oración completa no aparece con grep NO concluyas que falta —
acortá a un fragmento distintivo de 3–6 palabras (y reintentá partiendo por guión de corte);
PROHIBIDO normalizar espacios sobre el archivo entero Y también colapsar un hueco de 8+ espacios
dentro de una línea (ambos empalman columnas y fabrican adyacencias falsas); si normalizás, partí
antes la línea en ese hueco y tratá cada segmento por separado. Si no
encontrás respaldo textual, es no-soportada; y es no-soportada TAMBIÉN si la cita sólo toca terreno
común del tema — que el paper hable de lo mismo NO alcanza, tiene que tocar el contenido distintivo; si el paper
afirma lo CONTRARIO, es contradice (pegá la frase que lo contradice). Decime APARTE del veredicto:
¿el paper afirma esto bajo CONDICIONES que la afirmación no menciona (SNR, muestreo, tamaño de
muestra, definición del observable, época, rango)? Si sí, citalas con su nº de línea — la afirmación
puede estar bien y aun así estar sobre-generalizada. No uses memoria ni otros
papers."*

⛔ **La pregunta de completitud es la del contrato, y se ensancha sin que nada avise (#198).**
Es *«¿la **tabla o lista de la fuente** tiene más filas/ítems que los transcritos?»*. Al armar el
prompt es fácil escribirla como *«¿el paper dice **más sobre este eje**?»*, que suena equivalente y
**no lo es**: sobre una fila que resume lo que un paper aporta a un eje, la respuesta es **sí casi
siempre** —un paper siempre tiene más que una fila—. Medido: **201 avisos sobre 179 filas**, de los
que **66** eran reales al triarlos. Los 66 no son ruido (incluían tres teoremas transcritos sin una
premisa, cuatro «huecos» que la fuente citada cierra dos líneas después, y una enumeración de cuatro
propiedades de la que la nota transcribía una y después invocaba «las cuatro»); lo que falla es la
**tasa de disparo**, y un reporte donde 2 de 3 avisos no son accionables se deja de mirar.

> Es la misma clase de error que `parcial` (1.39.0) y la escala `Score` (1.42.0) —**una pregunta mal
> calibrada**—, con una diferencia: aquéllas se eliminaron por fusionar ejes; ésta **no se elimina**
> (la completitud es un hallazgo real, #49): se **acota al enunciado del contrato**.
>
> Al resolver rige la **regla de poda**: en una nota de concepto, *«el paper tiene más detalle»* NO
> es una omisión — es el recorte que la nota debe hacer. Y si el reporte de completitud vuelve
> poblado en **casi todos** los pares, eso es señal de que la pregunta se ensanchó, no de que la
> nota esté rota.

**Addendum para transcripciones** (agregar al prompt cuando el par sale de una tabla o lista de la
fuente): *"Esta afirmación es una fila/ítem de una transcripción. La nota transcribe de este paper la
lista completa: «…». Decime APARTE del veredicto: ¿la tabla/lista del paper tiene MÁS filas/ítems que
ésos? Si sí, listá los que faltan con su nº de línea. Ojo con el layout: la tabla puede estar
entrelazada con otra en las mismas líneas físicas — contá las filas de LA tabla que corresponde."*

### 2b. Barrera: el trabajo derivado se arma cuando el fan-out CERRÓ

⛔ **Antes de triar, resolver o escribir el bloque, contá cuántas fuentes devolvieron contra cuántas
lanzaste, y declaralo.** Si no cerraron todas, o esperás, o decís sobre cuántas estás afirmando.

Medido (#199): armar los lotes de triage con **53 de 57** verificadores todavía corriendo dejó **4
hallazgos que no miró nadie**, dos de ellos defectos reales —una fila que transcribía una de cuatro
propiedades y después invocaba «las cuatro», y una no-convergencia presentada como general que el
paper condiciona al S/N de su dataset—. Se detectaron por casualidad, al recontar para el log; sin
ese recuento el reporte habría dicho *«201 avisos triados»* sobre 197.

Es exactamente el **falso limpio** que el framework persigue en todos lados —`discover` distingue
*corrió con N* / *FALLÓ* / *NO CORRIÓ*; la categoría **⛔ No evaluado** del lint cuenta para el exit;
D-43 devuelve *no evaluado* y no `ok`— y nunca se había enunciado para el **consumidor** de un
fan-out, que es donde este skill manda derivar trabajo. Es barato de mecanizar: `len(out/*.json)`
contra el nº de fuentes.

### 3. El corte: contenido distintivo, sin grado

**No hay score.** El veredicto sale de **una** pregunta, y es de sí o no: ¿la evidencia citada toca
el **contenido distintivo** de la afirmación —el sujeto/valor/mecanismo que la hace específica—?
→ `soportada`, y lo que falte va a `condicion`. ¿La coincidencia es sólo temática (el fenómeno
general, un término suelto, la mera cercanía)? → `no-soportada`.

⚠ **No agregues un grado, y no es cuestión de gusto.** `parcial` se eliminó en 1.39.0 y la columna
`Score` 0–10 en 1.42.0, las dos por la misma razón: fusionaban el eje **textual** (¿la fuente dice
esto?, decidible contra el `.txt`) con uno de **grado** cuyo umbral nunca se calibró. Medido: dos
corridas ciegas del mismo fan-out coincidieron en **57 de 60 pares**, y **las tres divergencias
caían exactamente en el borde `soportada`↔`parcial`**. Lo que parece un grado o es una **condición**
(columna aparte) o es una cita que no toca el contenido distintivo (`no-soportada`). La arqueología
completa, con la medición y los sistemas de referencia que etiquetan binario, está en
`reference/historia-veredictos.md`.

- **`contradice`** manda sobre los otros dos (no es un grado de soporte sino evidencia **en contra**,
  con cita textual de lo contradicho): se resuelve como corrección o disputa (paso 4), no como cita rota.

### 4. Resolver lo que falla (no dejar pasar)

⛔ **Un hallazgo dice DÓNDE mirar, no QUÉ escribir.** La corrección se redacta **volviendo a la
fuente**, no copiando el encuadre del reporte del verificador. Medido: en una sola sesión, dos
correcciones hechas desde el reporte **introdujeron un error nuevo** — un resultado atribuido a
`N=2` cuando el paper lo reporta para `N=10`, y «este pipeline corrige actividad con regresión
multilineal» cuando el paper dice que **no corrige actividad en absoluto**. El verificador acierta
al señalar el problema y su nota es un resumen, no la redacción final.

⛔ **A escala, las correcciones NO se aplican a mano ni con un `replace` ingenuo: usá
`python scripts/apply_fixes.py <nota.md> <dir-de-fixes> [--write]`** (#197). El fan-out es para
**leer**; la escritura es de **un solo aplicador serial**. Cada corrector devuelve su corrección
como JSON —`{bibcode, fixes:[{n, viejo, nuevo, por_que, confirmado_en}], rechazados:[…]}`— y el
aplicador la pone. Los dos modos de falla están medidos sobre una corrida de 75 correcciones:

- **Colisión.** Un ítem de `## Huecos` que cita varias fuentes le toca a **cada** corrector de esas
  fuentes, así que llegan dos o tres fixes con el **mismo `viejo`** (medido: 5 sobre 2 ítems).
  Aplicados en cadena, el segundo se ancla sobre lo que dejó el primero y el ítem queda con un
  fragmento del anterior colgando — prosa corrupta **bajo un encabezado que se lee como verificado**.
  El aplicador la detecta **antes de tocar nada** y no escribe: la fusión se hace a mano y se declara
  en un JSON con `"bibcode": "_fusionados"`, que gana y saltea los originales. Fusionar dos
  correcciones es **juicio, no mecánica**, y por eso ningún script la hace solo.
- **Bloque multilínea.** El `viejo` que redacta el corrector sale del texto **normalizado** de
  `lib_blocks` (líneas unidas con un espacio) y en el archivo el bloque vive envuelto: un `replace`
  da **0 ocurrencias** (medido: 14 de 75 — todos los ítems y párrafos; las filas de tabla, de una
  línea, aplican bien). El aplicador lo localiza por su forma normalizada y lo reescribe re-envuelto,
  conservando la sangría.

**Todo o nada**: si un solo `viejo` no resuelve —no aparece, aparece dos veces, o hay una colisión
sin fusionar— no se escribe **ninguno**. Un reemplazo que adivina es peor que uno que falla, y una
nota a medio corregir es indistinguible de una corregida.

⚠ **Después de aplicar, las anclas cambian y hay que regenerar el bloque** — y si la corrección
agregó `[[bibcode]]` nuevos, esos pares **son pares nuevos** y hay que verificarlos también (medido:
dos, al resolver una contradicción interna de la nota).

Cada **no-soportada / contradice**, y cada `condicion` no vacía, se resuelve antes de cerrar:
- **Contradicción** (`contradice`) → decidir cuál de dos casos es. (a) **La nota está mal** →
  corregirla a lo que dice la fuente. (b) **Desacuerdo real entre fuentes** → es una **disputa**:
  si es un parámetro de una ficha, taguearla en `disputes` (posiciones explícitas, #71)
  (schema #71: `field` + `posiciones[]` de `{ref|source, value}` + `note` opcional — ⚠ `alt` y el `ref` a nivel de disputa son pre-#71 y el lint los **bloquea**; si NEA arbitra, una posición es `{source: ground_truth}` y sigue siendo el valor de verdad) y reflejarla en la prosa; si es
  un claim de concepto/query, citar **ambas** fuentes con el desacuerdo explícito (si toca una
  hipótesis, la postura se ajusta en **su tabla de evidencia**, D-21 — nunca en la nota del paper).
  Una contradicción detectada es un **hallazgo**, no un fracaso.
- **Atribución cruzada** (el hecho está, pero en otro de los papers citados) → reasignar la cita al
  bibcode correcto.
- **Afirmación estirada** (el paper dice menos/distinto) → **bajar** la afirmación a lo que la fuente
  sí dice (corregir el número/rango/alcance).
- **Sin respaldo en ninguna fuente** pero físicamente razonable → re-etiquetar **`inferencia`**
  (y quitar la cita que no corresponde).
- **Cita rota / fuente equivocada** → corregir o eliminar.
- **Omisión en una transcripción** (el `completitud` del par devolvió filas/ítems faltantes) → no es
  cita rota, es la nota afirmando **de menos**: **completar** la tabla/lista con lo que falta (las
  filas nuevas se verifican como cualquier par) o, si el recorte es deliberado, **declararlo
  explícito** en la nota ("los N casos de <tipo>; la Tabla 3 de la fuente lista M"). Nunca dejar una
  transcripción parcial que se lea como completa. Ídem si la fuente introduce la enumeración con
  "e.g." y la nota la presenta cerrada → abrir la lista en la nota.

### 5. Escribir el bloque de veredicto en la nota
Agregar/refrescar al final de la nota (idempotente — si ya existe, reemplazar):

```markdown
## Verificación de citas (YYYY-MM-DD)
Chequeo afirmación↔fulltext (skill `verify-citations`). N pares; X soportadas / Z no-soportadas / W contradicen (resueltas) / C con condición declarada.

| # | Afirmación (extracto) | Fuente | Veredicto | Evidencia | Ancla | Hash fuente | Condición |
|---|---|---|---|---|---|---|---|
| 1 | YZ CMi κ ≈ −2.6 | [[2018A&A...609A..12Z]] | soportada | "gradient of −2.6 Np−1 (±21%)" (L966) | 3f9c1e2ab4 | txt:7b40d8aa11 | — |
| 2 | activas −2.4/−2.6 | [[2025A&A...696A..27J]] | no-soportada→corregida | el paper da −2.65 a −3.70; el −2.6 es de Zechmeister | c17e0a9b22 | txt:55aa10ffe3 | — |
| 3 | señal g confirmada | [[2016A&A...585A.134D]] | contradice→disputa | "is an artifact of... rotation" (L2101) → tagueada en disputes[] | 90bb4c1de7 | txt:0ab77e2c41 | — |
| 4 | P_rot = 36,5 d | [[2017MNRAS.468.4772S]] | soportada | "36.5 ± 2.3" (L320) | 5c1de790bb | txt:41c0ab772e | promedio pesado de 4 proxies; el K de 0,50 m/s es de la señal a 35,0 d, no a 36,5 |

Inferencias declaradas (sin cita, por diseño): <listar>.

Omisiones en transcripciones: <tabla/lista, qué faltaba, cómo se resolvió> — o "ninguna".

Condiciones perdidas (afirmaciones sobre-generalizadas): <afirmación, condición que el paper le pone,
cómo se resolvió — en un concepto, fila de `## Régimen de validez`> — o "ninguna".
```
Convertir fechas relativas a absolutas. Notación `$...$` en archivos `vault/wiki/` (texto plano en chat).

⛔ **La barra vertical dentro de una celda va escapada `\|`** (INV-99). Es el caso normal, no el
raro: el fan-out junta varias citas textuales con ` | ` de separador, y una cita puede traer la suya
—una fila de tabla del paper—. Sin escapar, la celda se parte en dos y **todas las columnas a su
derecha se corren**: el `Ancla` se lee de la celda de al lado y el par vuelve *«vencido por
edición»* sin que nadie haya editado nada (medido: 18 pares de una ficha, 2026-08-25). Desde 1.41.1
el parser honra el escape y, si la fila igual no cuadra con el encabezado, **no la indexa por
posición** — la deja como par sin cubrir, que es el fallo ruidoso en vez del silencioso. Si generás
el bloque con un script, **sustituir** o escapar; nunca dejar la barra cruda.

### El ancla: una fila por par, con sus dos hashes (D-4/D-20)

⛔ **Una fila por par, sin excepción.** La tentación es colapsar las soportadas en un párrafo de
prosa y dejar en la tabla sólo las que fallaron (así estaba una ficha real). **No**: sin fila no hay
dónde colgar el ancla, y el lint no puede distinguir "verificada" de "nunca se miró".

Las dos columnas nuevas las calcula el **mismo** código que después las chequea, así que no se
escriben a ojo:

```bash
# ancla del bloque que contiene la cita, y hash del .txt que leíste
python -c "import sys;sys.path.insert(0,'scripts');import lib_blocks as lb;\
[print(p.bibcode, p.anchor) for p in lb.pairs_of(open('vault/wiki/<nota>.md',encoding='utf-8').read())]"
python -c "import sys;sys.path.insert(0,'scripts');import lib_blocks as lb;\
print(lb.source_hash('vault/raw/fulltext/<slug>/<bibcode>.txt'))"
# …salvo que la fuente esté marcada `symbols_lost` (#113): ahí la evidencia salió del PDF, así que
# el hash es el del PDF — `bytes_hash`, no `source_hash` (un PDF no es texto, y decodificarlo con
# errors=replace hace colisionar dos escaneos distintos).
python -c "import sys;sys.path.insert(0,'scripts');import lib_blocks as lb;\
print(lb.bytes_hash('vault/raw/pdfs/<slug>/<bibcode>.pdf'))"
```

### Documentos largos: un libro no se verifica como un paper (#80)

Cuando la nota de la fuente declara **`unidad_cita: pagina`** o **`seccion`** —un libro, un
handbook—, tres cosas cambian y las tres son del contrato, no del gusto:

1. **No mandes a leer el `.txt` entero.** El fan-out asume un documento que un subagente lee
   completo; 700 páginas lo revientan. El subagente recibe **el capítulo o el rango de páginas** de
   la afirmación, no el archivo.
2. **La evidencia se cita por `p. N` o `§ N.M`, nunca por línea.** «Línea 18443» no es una
   referencia que alguien pueda seguir, y el `.txt` de un libro tampoco se cita por línea (es un eje
   distinto del `txt:`/`pdf:` de #117, que dice qué **archivo** se leyó).
3. **La completitud se pregunta contra el `alcance` declarado, no contra el documento.** La nota
   declara qué parte entró (`alcance: caps. 6 y 15`); lo que está fuera de esa parte **no** es una
   omisión. Sin `alcance` no hay forma de distinguir el recorte deliberado del olvido, y por eso el
   lint lo reporta.

- **`Ancla`** — sha256 (10 hex) del bloque markdown normalizado que contiene la afirmación.
  Reflowear la nota **no** la mueve; cambiar un número **sí**. Una fila/ítem sin `[[bibcode]]`
  propio hereda el del caption y hashea **los dos** bloques.
- **`Hash fuente`** — `txt:<sha10>` o `pdf:<sha10>`: **qué archivo leíste** y su hash. Es lo que
  detecta que la fuente ya no dice lo mismo **sin que la nota se haya tocado** — ninguna medida
  basada en fechas de la nota puede ver eso.
  ⛔ **El prefijo es obligatorio y lo decidís vos, par por par (#117).** Antes el lint lo inferían
  del frontmatter (`symbols_lost` ⇒ PDF, si no el `.txt`), y esa regla es **más angosta que la
  práctica**: una fuente `fulltext_source: ocr` también se verifica contra el PDF cuando el escaneo
  del editor destruyó los símbolos — es lo que se hizo con **3 de las 5** fuentes marcadas de un
  tema real, y ahí el lint hasheaba el archivo equivocado y devolvía **17 pares «vencidos por
  fuente»** sobre fuentes que nadie tocó. El frontmatter no sabe qué abriste; la fila sí.
  Que el prefijo case con el localizador de `Evidencia`: `pdf:` va con `p. 628`, `txt:` con `L320`.
  ⛔ **Documento largo leído del `.txt`: van los DOS localizadores (#200).** Una fuente
  `unidad_cita: pagina` se cita por **página** (#80: *«línea 18443» no es una referencia
  utilizable*) pero se lee del `.txt`, que es lo barato y lo que el contrato manda por defecto. Las
  dos reglas son correctas y chocan: la fila queda con `txt:` y una evidencia que dice `p. 271`. Las
  dos salidas obvias **empeoran** la fila — poner `pdf:` **miente** sobre qué archivo se abrió y hace
  que el ancla vigile un archivo que nadie leyó; citar por línea rompe #80. La salida es escribir
  **los dos**: `«…» (p. 271 / \u0060.txt\u0060 L13931)`. Deja las dos verdades escritas —la
  referencia utilizable para un humano y el ancla del archivo que se hasheó— y el detector queda en
  0 sin ablandarse. Medido: **6 de 8** filas marcadas de un concepto real eran este caso, todas
  correctas.
  Anclar al `.txt` una cita que salió del PDF la marca vencida cada vez que ese `.txt` se re-extrae
  —cosa que el propio framework provoca (`--force`, upgrade a OCR, backfill de marcas)— mientras la
  fuente real no se movió, y **no ve** que el PDF sí cambió. Una celda **sin** prefijo es la
  plantilla vieja: el lint la bloquea y se migra con
  `python scripts/make_notes.py --migrate-verif-archivo`.

**Cerrá con `python scripts/lint.py --cierre <slug>`** (R-1): ahí un par vencido **frena la operación**,
porque significa que no terminaste. Sin el flag es la pasada periódica y sólo reporta; sin el
**slug** (#121) cuenta la bóveda entera, así que la deuda de otro sujeto frena un cierre que no la
causó — pasale el sujeto que tocaste.

**La fecha del encabezado sigue siendo portante**, pero ya **no** es el mecanismo principal (#56):
las anclas la reemplazan con granularidad de par. Queda como **red** para notas con bloque y sin
tabla parseable, y porque el lint la usa para el chequeo stale por git. Al re-verificar, re-fechar.
Si la nota acumuló **varios** bloques (pasadas sucesivas sobre secciones distintas), la vigencia la
marca la fecha **más reciente**.

### D-5 — la nota nace 100% verificada

Al armar una ficha o un concepto se verifica **todo**, y el bloque sale con una fila por par. El
estado *"sin verificar"* sólo puede aparecer **después**, por una edición. Eso es lo que hace
viable el chequeo: el caso normal es que nada cambió y el lint calla, así que cuando habla hay algo
real. Una nota que nace con pares sin fila arranca con deuda que nadie va a distinguir de la deuda
legítima.

### 6. Lint + cierre
Correr `python scripts/lint.py --cierre` (0 en lo bloqueante; la **fuga de implementación** es WARN a revisar a
mano, y resolvé las **citas no verificables** del corpus que chequeás). Si el usuario pidió archivar/commitear, `git add` de los archivos **específicos**
y commit descriptivo; **preguntar antes de `push`**. Appendear a `vault/wiki/log.md` (resumen del chequeo:
cuántas soportadas/corregidas).

## Reporte (al chat)
Veredicto global honesto: total de pares, cuántas soportadas, **cada corrección hecha** (qué se
bajó/reasignó/marcó inferencia), **cada contradicción con su resolución** (corrección o disputa
tagueada), **cada omisión** detectada en una transcripción (qué faltaba y si se completó o se
declaró el recorte) y **cada condición perdida** (#74: la afirmación estaba respaldada pero el paper
la condiciona — qué condición, y si se agregó a la prosa o como fila de `## Régimen de validez`).
No maquillar: una afirmación que se estiró y se corrigió es un hallazgo del chequeo, no un fracaso. Si algo quedó dudoso, decirlo.

## Límite honesto
El chequeo es **juicio de un LLM** leyendo la fuente — robusto (independiente por par, grounding-first,
cita textual obligatoria) pero **no una prueba**. Reduce drásticamente la mala atribución; no la elimina.
Su tasa de error frente a errores **plantados** se mide con el **modo benchmark** (abajo); su
**reproducibilidad sobre contenido real**, con el **modo revalidación**.

## Los dos modos a pedido (revalidación y benchmark)

Ninguno es paso de cierre: se corren **a pedido**, y por eso viven en
`reference/modos-a-pedido.md` en vez de acá.

- **Revalidación** — re-corre el fan-out sobre pares **ya verdes**, con jueces nuevos y ciegos, y
  compara. Cierra el supuesto que las anclas (D-4/D-20) dan por hecho y nunca se midió: que el
  veredicto es una **función** de (afirmación, fuente). Sin esto, un error del juez es **permanente y
  silencioso**.
- **Benchmark** — `python scripts/bench_verify.py seed` siembra citas **falsas deterministas** entre
  pares reales, el verificador las juzga a ciegas y `score` reporta el **recall**. Le pone un número
  al "juicio de LLM". **Regla #0: nada del benchmark entra a `vault/`** (vive en `build/`/`outputs/`;
  las citas falsas no son bibliografía).

Los dos miden cosas distintas —reproducibilidad sobre contenido real vs detección de un error
plantado— y ninguno sustituye al otro.
