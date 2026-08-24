# Revisión del contrato con el usuario — sesión 2026-08-23

Registro vivo de la revisión de `docs/contrato.md` §6 (decisiones de intención) hecha **con el
usuario**, recorriendo el sistema de punta a punta. Se escribe acá mientras dura la revisión y se
pliega a `docs/contrato.md` (§3 invariantes nuevos, §6 decisiones resueltas) y a `vault/STATUS.md`
al cerrar.

**Método:** recorrer la cadena en el orden en que se usa (setup → ingest → extracción → síntesis →
cierre), y en cada paso sacar a la superficie las decisiones que el contrato dejó abiertas. Al final:
barrer las 22 decisiones y ver cuáles quedaron sin tocar.

---

## 1. Decisiones cerradas

### D-1 · Autoridad del ground-truth: una sola por campo (cierra §6 #2)
- `spectral_type` ← **SIMBAD**. Todos los demás campos espejo ← **NEA** (`pscomppars`).
- **Sin fallback.** Si la autoridad declarada del campo no tiene el dato, el frontmatter va `null`
  aunque la otra autoridad sí lo tenga.
- El valor de la autoridad no declarada **se preserva en el JSON como campo de auditoría, no
  autoritativo** (análogo a `bmass_earth`/`mass_source` en planetas) — hace falta para que el cuerpo
  pueda mencionarlo.

**Cambia el código.** Hoy es al revés: `fetch_ground_truth.py:174` toma `st_spectype` de NEA como
primario y `:204-211` usa SIMBAD sólo como relleno, **sin registrar cuál autoridad ganó** — el
consumidor no puede distinguirlas ni auditarlo. Hay que invertir la precedencia, borrar el fallback y
agregar el campo de auditoría.

**Toca INV-14** (P1, *garantizado sin medir*: "cada campo tiene una sola autoridad de escritura
declarada"). Hoy `spectral_type` tiene dos; con D-1 el invariante pasa a ser verdad para todo el
espejo.

### D-2 · La discrepancia entre autoridades va a `disputes[]` (deriva de D-1)
- Posiciones `{source: nea}` / `{source: simbad}`. `DISPUTE_SOURCES` (`lint.py:226`) hoy tiene **una
  sola entrada** (`ground_truth`): con dos autoridades una discrepancia es inexpresable — ambas
  posiciones dirían lo mismo y quedarían indistinguibles. Hay que abrirlo.
- **El silencio es una posición válida**: `{source: simbad, value: null}` cuando la autoridad
  declarada no tiene el dato y la otra sí. Encaja con el mínimo de ≥2 posiciones (INV-12, P0) sin
  romperlo, pero hay que decirlo explícito: la lectura natural de "posición" es *alguien afirma
  algo*, y acá una posición es *la autoridad no tiene el dato*.
- Alcance acotado por construcción: `spectral_type` es el único campo con dos autoridades.

### D-3 · Toda afirmación del texto lleva referencia **verificada** (inamovible del usuario)
Ratifica y endurece la regla dura de `CLAUDE.md`: citada `[[bibcode]]` o marcada `inferencia`. La
palabra nueva es **verificada** — no alcanza con que sea verificable.

### D-4 · Cobertura de verificación: bloqueante, con granularidad de bloque (cierra §6 #5)
Hoy "nota con citas sin verificar" y "verificación stale" son **backlog** (no bloquean), y el stale se
mide por fecha de git contra la fecha del bloque: **todo o nada por archivo**.

- **Bloquea** el cierre de la operación que tocó la nota.
- **Ancla por par**: `sha256` (10 hex) del **bloque markdown normalizado** que contiene la cita.
  Normalizar = colapsar runs de whitespace (reflowear no mueve el hash; cambiar un número sí).
- **Unidad = el bloque más chico que contiene la cita**: párrafo / **fila** de tabla / **ítem** de
  lista / blockquote. Medido en Almagesto-RV (761 citas): 560 en párrafos (186 bloques), 141 en
  listas (24), 54 en tablas (8), 6 en blockquotes (3).
- **Citas heredadas** (fila/ítem sin cita propia que la hereda del caption o párrafo que la
  introduce, ya en `CLAUDE.md`): el ancla es el hash de **los dos** bloques — editar el caption cambia
  lo que las filas afirman.
- **Sobre-disparar es correcto, sub-disparar no.** Un párrafo con 3 citas da 3 pares con el mismo
  ancla: tocás una frase y se re-verifican los tres. El error tiene que caer siempre del lado caro
  (verificar de más), nunca del lado mentiroso (decir "verificado" sobre texto que nadie miró.)
- **Descartadas** las otras dos granularidades: por **línea** (las notas van hard-wrapped a ~100
  columnas → reflowear corre todos los cortes y da falsos "vencido" en masa) y por **sección**
  (invalida doce citas por editar una frase).

**Dónde vive el ancla: dentro de la ficha**, columna nueva en la tabla del bloque
`## Verificación de citas`. Contra el sidecar (`vault/config/…`) pesa que **el lint lo corre el
operador y el bloque lo lee el consumidor**: un agente que abre la ficha ve ahí el estado de
verificación y nunca va a correr el lint. Un sidecar se lo saca y encima puede desincronizarse. Costo
aceptado: ruido de diff, acotado a las filas cuyo texto cambió. El bloque se excluye de su propio
hasheo.

**El bloque pasa a un par por fila.** La plantilla del skill ya lo dice, pero la instancia real lo
incumple: en `tau_ceti.md:133` la tabla tiene **una sola fila** (la que falló) y las 18 soportadas
están colapsadas en un párrafo de prosa. Sin filas no hay dónde colgar el ancla.

**Dos severidades, mismo detector** (según haya o no una operación que frenar):

| Momento | Severidad |
|---|---|
| Cierre de una operación que tocó la nota (ingest, `append-knowledge`, refresh) | **bloquea** |
| Pasada periódica sobre la bóveda (mantenimiento) | **reporta** — la lista y el usuario elige |

**Migración gratis y bien definida** para las notas con bloque sin ancla: si la nota **no** se editó
desde la fecha del bloque, el texto de hoy *es* el verificado → se hashea tal cual; si se editó, ya
está vencida y hay que re-verificarla igual. No hay que reconstruir nada.

**El comando ya existe**: `python scripts/lint.py` (determinista, offline, sin red, segundos). La
revalidación cara —los subagentes— la dispara el usuario con `verify-citations`, sólo sobre lo
marcado. Vecino directo del sub-modo *"resolver el backlog del lint"* de `maintain`.

### D-5 · La ficha nace 100% verificada (inamovible del usuario)
Al armar la ficha se verifica **todo**. El estado "sin verificar" sólo puede aparecer **después**, por
una edición. Es lo que hace viable D-4: el caso normal es que nada cambió y el lint calla.

### D-6 · Lente vacía: rehusar operar (cierra HUECO-1 / INV-56, P0)
Un `objective.yaml` que no parsea hoy degrada a `{}` **en silencio** (`lib_config.py:185-187`): el
clasificador sigue corriendo con una regla que nadie escribió, el registro guarda esa lente vacía
como si fuera la vigente, y el lint no dice nada (su único chequeo compara `name` contra el
placeholder). Dos mecanismos:
- categoría de lint *"objective.yaml no parsea → lente vacía"*, **bloqueante**;
- `query_ads` **rehúsa** clasificar con lente vacía en vez de correr con `{}`.

Razón del usuario: *"de acá tiene que salir todo lo que sirve para catalogar como core o no"* — una
lente vacía no es un default, es un error.

### D-7 · Alias propuestos y validados antes de la búsqueda (hueco nuevo)
Hoy los `aliases` están escritos **a mano** en `stars.yaml` y la cadena los usa sin preguntar. El
recall de toda la búsqueda cuelga de esa lista: un alias que falta es un paper que nunca aparece, en
silencio — el mismo modo de falla que el glifo griego, pero **sin rescate**.

`ingest-star` pasa a: resolver identificadores en SIMBAD → mostrar la lista candidata (con las
variantes de espaciado y glifo ya expandidas) → **no correr la query hasta que el usuario apruebe** →
persistir lo aprobado en `stars.yaml`.

### D-8 · El setup se cierra validando contra papers reales
El usuario da el concepto en sus palabras; el agente propone la lista de términos en inglés (traduce,
expande el concepto, cubre morfología a mano —no hay stemmer—, incluye nombres propios de
herramientas) y **la muestra en prosa, nunca en regex**. Recién después se escribe el archivo y se
valida con `--probe` contra papers reales, mirando **qué quedó de cada lado del corte**. Leer el
patrón no valida nada. Iterar hasta que cierre.

---

## 2. Invariantes existentes que el usuario ratificó

| Invariante | Estado hoy | Qué dijo el usuario |
|---|---|---|
| **INV-06/07** (P0, medido) — cada campo espejo vale lo que dice el ground-truth o `null`; nunca literatura | garantizado y medido | *"el invariante acá es que todo lo del frontmatter sale directo de esos sitios, no hay LLM acá"* — inamovible |
| Regla dura de `CLAUDE.md` — toda afirmación citada o marcada `inferencia` | vigente | inamovible, **y endurecida** a *verificada* → D-3/D-4 |
| **INV-24/INV-55** — el veredicto core/no-core depende sólo de metadata + lente | garantizado sin medir | ratificado: el agente **no decide** core en la query directa |

---

## 3. Hallazgos nuevos de esta revisión (sin decisión todavía)

1. **Tabla de lookalikes griegos: ausencia afirmada sin medir.** `_GREEK` (`query_ads.py:285`)
   declara "no tiene lookalike" para 8 letras (ζ η ι λ ν ξ ο τ) y por eso **no corre el rescate** para
   ellas. Eso está medido **sólo para ε** (donde el agujero costaba 121 core, incluido el paper de
   descubrimiento); del resto es suposición. Falla en silencio.
2. **No hay medición de cobertura de sinónimos.** Un término faltante en `relevance.topics` no da
   error: da papers no-core y nadie se entera. Las dos redes son **manuales** — `--probe` en el setup
   y el apéndice `## Excluidos por el filtro` de cada ficha (top no-core por citas, con link a ADS).
   Ninguna mide nada.
3. **El bloque de verificación real diverge de la plantilla** (ver D-4): las soportadas colapsadas en
   prosa en vez de una fila por par.

---

## 4. Recorrido: dónde vamos

- [x] Setup / el objetivo (§6 #2 abierto por otra vía, D-6, D-8)
- [x] Búsqueda ADS: query directa, alias, glifos, core/no-core, triaje del chaining (D-7)
- [x] El espejo del ground-truth (D-1, D-2)
- [x] Verificación de citas (D-3, D-4, D-5)
- [ ] **Extracción y formato de la ficha** ← sigue acá
- [ ] Contraste cross-paper (#72) y síntesis
- [ ] `append-knowledge` y refresh
- [ ] Barrido final de las 22 decisiones de §6

**Decisiones de §6 cerradas hasta acá:** #2 (→ D-1, D-2), #5 (→ D-4).
**Sin tocar:** #1, #3, #4, #6-#22.

---

## 5. Temas tangenciales, anotados para después

### T-1 · Cómo se linkean las cosas dentro de la misma bóveda (anotado por el usuario)
A medida que la bóveda crece hay que **relacionar lo nuevo con lo que ya está**, y hoy eso descansa
en tres mecanismos que conviene revisar juntos:

- **Retro-linkeo (3 capas, ya en `CLAUDE.md`):** (a) la ficha-método junta por
  `contains(methods, …)`; (b) `make_notes` mergea **add-only** los seeds del ingest en notas de paper
  preexistentes; (c) `ingest-topic` retro-taguea por grep de los `aliases` del tema sobre **todo** el
  corpus.
- **Roll-ups Dataview y el problema #60:** los bloques ```dataview``` son la promesa de "esto se
  relaciona solo", pero un agente que abre el `.md` ve **el código de la query, no sus resultados**, y
  el plugin ni está versionado. El equivalente determinista existe (one-liner con `split_fm`) pero es
  un fallback que hay que conocer.
- **Convención hub/radios** para temas que no caben en una nota.

Preguntas abiertas: ¿quién dispara el retro-linkeo cuando entra una entidad nueva —la cadena o una
pasada de mantenimiento?; ¿hay forma de **detectar** relaciones que deberían existir y no existen
(el análogo de "extraído pero no sintetizado", pero para links)?; ¿los `aliases` de conceptos
alcanzan como llave de cruce?

### D-9 · La ficha es un **snapshot destilado**, no una revisión cronológica
Evaluadas dos formas contra el mismo material real (τ Ceti):

- **A — destilada** (la del contrato): se organiza por **objeto** (parámetros, inventario de señales
  RV, indicadores, métodos, huecos). Un paper aporta a varias secciones o a ninguna. Tamaño
  **constante**: no crece con el corpus.
- **B — por faceta, cronológica**: una entrada por paper, ordenada por año, dentro de cada faceta.
  Tamaño **lineal** en el corpus (40 papers core → 40 entradas).

**Elegida A.** El criterio que decide: preguntarle a cada una *"¿cuántos planetas tiene y cuál está en
duda?"*. A lo contesta; B devuelve nueve entradas y deja la síntesis al lector — que es justo el
trabajo que la ficha existe para haber hecho. Es la promesa de autosuficiencia (*un agente la lee y
queda servido sin abrir ningún paper*) y la razón del *"no re-narrar en la ficha lo que ya está en la
extracción del paper"* de `CLAUDE.md`.

Lo que B aporta —**cómo evolucionó el conocimiento**— A ya lo captura donde importa: el
`## Inventario por eje` (#72) es B restringido a los ejes donde los papers **no coinciden**. Donde hay
acuerdo, un número con su cita alcanza.

**Palabra del usuario, que conviene conservar: la ficha es un "snapshot".** Tiene consecuencia: un
snapshot tiene fecha y envejece. Es lo que le da sentido al sub-modo *refrescar* y a la línea de
búsqueda de la cabecera (sobre qué universo de papers afirma esta ficha, y con qué lente).

**Sobre combinar A+B:** B queda como **consulta, no como artefacto**. La cronología se responde a
pedido (skill `query-corpus`, citada, en el chat) y no se persiste por default — igual que cualquier
query. Razón: la parte valiosa de B no es la lista por año (eso es derivable de los `year` de las
notas de paper) sino el relato de qué cambió, y eso es **síntesis nueva**; persistirla generada
crearía prosa que nadie verificó, contra D-3/D-4.

### T-2 · Revisar el frontmatter de las notas de paper (anotado por el usuario)
Qué es y para qué sirve cada campo de curación, en particular `thesis_links` y sus vecinos:
`bearing` (postura respecto de una tesis), `role` (#73: `fundacional|aplicacion|arbitro` — qué **tipo**
de aporte), `topics` (las facetas que matcheó), `methods`. Y los de verdad de disco
(`fulltext_source`, `pdf_source`) con sus salvedades OCR / preprint.

### D-10 · Los roll-ups se **materializan**, con estado de síntesis por paper (cierra #60 en `stars/`)
Dos defectos del roll-up Dataview, uno ya conocido y otro que sacó el usuario en esta sesión:

1. **Invisible para la audiencia-modelo (#60).** Un agente que abre el `.md` ve el **código de la
   query**, no sus resultados, y el plugin no está versionado. La lista de papers core, para el
   consumidor que la ficha promete servir, **no está en la ficha**. Choca con D-9: un *snapshot*
   contiene su propio universo, no una instrucción para ir a buscarlo.
2. **Muestra una población que la síntesis nunca evaluó.** El roll-up filtra por el **tag**
   (`contains(stars, …)`), que se puebla también por **retro-linkeo add-only** — feature deliberada
   (que la entidad nueva vea lo que ya estaba). Resultado: la población de la tabla y la de la prosa
   están **desacopladas**, y la ficha no las distingue. Un lector ve "155 papers" arriba de un
   Resumen y concluye que el Resumen sale de esos 155.

**Medido en `tau_ceti.md`** (vintage 1.11.0, ficha a medio hacer — el número es de un caso feo, pero
el mecanismo no depende de la instancia): **155 en el roll-up, 8 citados en la prosa**. De los 147
restantes: 67 `relevance: low` sin extraer, **42 `high` sin extraer**, **38 `high` extraídos y no
sintetizados**. La red existente (#75, *extraído pero no sintetizado*) cubre sólo los 38: los 42 no
tienen `methods` que los delate y los 67 están excluidos de la población por diseño.

Es *afirmar de más*: la ficha no dice nada falso, **se lee como** afirmando que sintetizó 155.

**Forma:** tabla escrita en la ficha, estampada por el script como cirugía idempotente (como la
cabecera), con encabezado de conteo y una columna de estado por paper.

```markdown
## Papers (155 · 8 sintetizados en esta ficha)
| Bibcode | Año | Relevancia | Estado |
| [[2017AJ....154..135F]] | 2017 | high | **sintetizado** |
| [[2019MNRAS.483.1159I]] | 2019 | high | extraído, no sintetizado |
| [[1984ESASP.218..139M]] | 1984 | high | sin extraer |
| [[1975JBIS...28..399F]] | 1975 | low | fuera del filtro |
```

`sintetizado` = el bibcode aparece citado en el cuerpo de **esta** ficha. Determinista y offline.
Ídem `## Métodos aplicados`, que tiene el mismo defecto. El conteo del encabezado es el indicador de
cuán completa está la ficha.

### D-11 · La ficha es **completamente autocontenida**
Consecuencia de D-9 + D-10, elevada a regla por el usuario: nada de lo que la ficha promete puede
depender de un plugin, de otra nota, ni de que el lector sepa correr un fallback. Todo roll-up
dinámico que sostenga una promesa del contrato se materializa.

### D-12 · Timestamps: tres fechas distintas, un solo bloque de estado
La ficha pasa a tener **tres** fechas que responden preguntas distintas y **pueden divergir**:

| Fecha | Responde |
|---|---|
| **búsqueda** (cabecera #64) | sobre qué universo de papers afirma esta ficha, y con qué lente se filtró |
| **verificación** (bloque `## Verificación de citas`, D-4) | cuándo se chequearon las citas contra las fuentes |
| **síntesis / roll-up** (D-10) | cuándo se estampó la lista y el conteo de sintetizados |

Confundirlas es un bug esperable, así que van **juntas en un solo bloque de estado** en la cabecera,
no desperdigadas. Salvedad importante: con las anclas de D-4 el estado "verificado" es **por par**;
el timestamp dice *cuándo fue la última pasada*, no *que todo siga vigente* — lo vigente lo dicen las
anclas.

### D-13 · El ingest lee **todos** los core; lo que no se lea, se declara
Hoy el skill dice *"leer los papers **clave** (discovery / actividad / métodos)"* — que no es un
criterio: no dice cuántos, ni en qué orden, ni deja registro de qué se leyó. Es lo que produce el
número medido en D-10 (**42 papers `relevance: high` que nadie leyó**, en una ficha que se presenta
como el snapshot del conocimiento de la estrella).

Tensión de fondo: si la lente marca 193 papers como **core** y la extracción lee 40, "core" deja de
ser la unidad de trabajo y pasa a ser una etiqueta de la búsqueda que nadie honra — y el consumidor
no sabe cuál de los dos números lo describe.

- **Default: se leen todos los core.**
- Si por algún motivo no se leen todos, **se avisa** y el motivo queda registrado.
- **Sea cual sea la decisión, la lista de papers de la ficha (D-10) declara cuál entró y cuál no.**
  Es el requisito duro: el estado nunca es implícito.

**Consecuencia que cierra el círculo con D-8:** con este default, la lente tiene **costo operativo
directo**. Una faceta laxa que deja entrar 900 papers ya no es sólo ruido en la ficha: son 900
extracciones. `relevance.require` deja de ser "la palanca contra el ruido" y pasa a ser también el
presupuesto del ingest. Hay que decirlo en el setup.

### D-14 · Escala: un subagente por paper
193 fulltexts no entran en una lectura. Se paga como ya se paga `verify-citations`: **un subagente
por paper**, cada uno lee un solo `.txt` y devuelve la extracción estructurada. Caro pero acotado, y
hace el paso 1 **auditable** (cada extracción tiene su corrida).

Cuando el volumen lo justifique, el agente puede **proponer un subconjunto** — pero el criterio de
selección tiene que ser **declarado y quedar registrado**, no implícito como hoy.

### D-15 · Completar una ficha después es el backlog, no una operación nueva
Terminar de ingestar los papers pendientes usa **los mismos pasos 1→4** que el ingest. La diferencia
está sólo en la **plomería de entrada**:

| | Qué falta | Dónde vive |
|---|---|---|
| `append-knowledge` | la fuente **no está** en la bóveda: hay que bajarla (bibcode → `extra_core`; PDF/URL → `sources`) | skill `append-knowledge` |
| completar pendientes | la fuente **ya está** (bajada, con fulltext y stub); falta extracción + síntesis | sub-modo *backlog* de `maintain` |

Con D-10 el pendiente es **estado visible de la ficha** y el lint lo reporta (la categoría #75
*extraído pero no sintetizado* más una nueva, *core sin extraer*). Resolverlo es exactamente el
sub-modo "resolver el backlog del lint" que `maintain` ya tiene → **no hace falta una operación
nueva**.

### T-3 · Revisar la interacción del setup a la luz del costo (anotado por el usuario)
D-13 convierte a la lente en **presupuesto**. Con los tamaños reales de la instancia (672 fulltexts:
mediana **92 KB ≈ 24k tokens**, media 30k), una estrella de ~198 core cuesta del orden de **6M tokens
de entrada** sólo en el paso de extracción, y escala lineal.

Eso cambia lo que el setup tiene que conversar: no alcanza con *"¿esto trae basura?"* — hay que
mostrar *"esta lente cuesta N lecturas por estrella"*. Ideas a evaluar: que `--probe` reporte el
**conteo proyectado de core** (ya lo tiene) **y su costo**; que el ingest **avise y proponga** el
subconjunto antes de gastar; que el apéndice de la ficha deje la cola declarada para apendear después
(D-15).

---

## 6. Mapa: qué invariantes del contrato tocamos

| Invariante / decisión de `contrato.md` | Qué le pasó |
|---|---|
| **§6 #2** — alcance del espejo (¿una autoridad por campo o compuesto?) | **cerrada** → D-1, D-2 |
| **§6 #5** — cobertura de verificación (¿backlog o bloqueo?) | **cerrada** → D-4 (bloqueo, con ancla por bloque) |
| **INV-56 / HUECO-1** (P0) — config malformada aborta, nunca default silencioso | **cerrado** → D-6 |
| **INV-14** (P1) — cada campo tiene una sola autoridad de escritura declarada | **pasa a ser verdad** con D-1 (hoy `spectral_type` tiene dos) |
| **INV-12** (P0) — disputa válida: `field` + ≥2 posiciones + quién la sostiene | **extendido** por D-2: el silencio de la autoridad declarada es una posición (`value: null`) |
| **INV-35** (P0) — todo contenido prometido por query dinámica tiene equivalente determinista | **superado** por D-10/D-11: en `stars/` no hay query dinámica, se materializa |
| **INV-06/07** (P0) — el espejo vale lo que dice el ground-truth o `null` | **ratificado sin cambios** (inamovible del usuario) |
| **INV-24 / INV-55** — core/no-core depende sólo de metadata + lente | **ratificado**; D-13 le agrega la consecuencia de costo |

**Invariantes nuevos que el contrato no tenía** (nacen de esta revisión): D-4 (ancla por bloque),
D-5 (la ficha nace 100% verificada), D-7 (alias validados antes de la búsqueda), D-9 (forma de la
ficha), D-10 (estado de síntesis por paper), D-12 (los tres timestamps), D-13 (todos los core),
D-14 (un subagente por paper), D-15 (completar = backlog de `maintain`).

## 7. Decisiones abiertas de esta sesión (sin resolver)

1. **¿El frontmatter tiene lista cerrada de campos?** El espejo vigila una **lista fija de 9 campos**
   (`MIRROR_HOST` 4 + `MIRROR_PLANET` 5). Un campo agregado fuera de esa lista **no lo mira nadie** —
   medido: `logrhk: -4.93` en `tau_ceti.md`, valor de literatura extraído por LLM viviendo en la capa
   auditable. La garantía "no hay LLM en el frontmatter" hoy cubre 9 campos, no el frontmatter.
   ¿Lista blanca del schema completo (campo no declarado = error bloqueante) o campos libres sin
   custodia?
2. **Colisión de nombres `topics`** — significa *faceta de la lente* (`objective.yaml`,
   frontmatter de papers) y *tema-sujeto a ingestar* (`topics.yaml`). Candidato a renombrar.
3. Los tres hallazgos de §3 (lookalikes griegos sin medir, cobertura de sinónimos sin medición,
   plantilla del bloque de verificación).

### D-16 · Un `bearing` por `thesis_link`
Hoy `thesis_links` es una **lista** y `bearing` un **escalar**: el schema afirma que el paper tiene la
misma postura frente a todas sus tesis. Un paper puede **apoyar** una y **desafiar** otra —el caso
normal en un `arbitro`— y ese desacuerdo se pierde sin que nadie lo note: el lint sólo chequea que
`bearing` **exista**, no que haya uno por link.

Nueva forma: `thesis_links: [{link: <slug>, bearing: supports|challenges|method}]`.

**Migración** (sin capa de compatibilidad: migrador de un solo uso + detector bloqueante). Medido en
la instancia real: **376 papers con `thesis_links`, 309 con uno solo y 67 con más de uno**
(47 con 2, 17 con 3, 3 con 4).

- Los **309 de un solo link** migran **exactos**: el `bearing` viejo era inequívoco.
- Los **67 multi-link** heredan el `bearing` viejo en todos sus links, pero quedan **marcados para
  revisión**: la migración preserva fielmente lo que el schema viejo afirmaba, y lo que el schema
  viejo afirmaba puede ser falso. Fosilizarlo sin marca sería convertir una limitación de forma en un
  dato.

### D-17 · Las keywords de ADS van al frontmatter de la nota de paper
`query_ads` **ya las pide** (`keyword` está en `FIELDS`, `query_ads.py:108`) y las usa para
clasificar, pero terminan sólo en `build/<slug>/ads.json`, que es **gitignored**. A la nota no
llegan.

Consecuencia: el clasificador decide con **título + abstract + keywords**, y la nota conserva dos de
los tres insumos (título en el frontmatter, abstract en el cuerpo). Desde la nota **no se puede
reproducir por qué ese paper quedó core** — sólo se ve el veredicto (`topics`). Choca con **INV-58**
(*determinar sin adivinar si el corpus vigente fue clasificado con la lente actual*), que hoy se
sostiene mientras exista `build/`; borrado el scratch, hay que volver a pedírselo a ADS.

Segundo uso que se recupera: son **vocabulario controlado**, mucho mejor que un grep de fulltext para
cruzar la bóveda por tema (el grep trae menciones al pasar).

```yaml
keywords: [Stellar activity, Radial velocity, Exoplanet detection methods]
```

Backfill posible sin re-bajar nada para el corpus con `build/` vivo; para el resto, una consulta de
metadata a ADS por bibcode.

### D-18 · Dedup de artefactos: si el bibcode ya tiene `.txt`/PDF bajo cualquier slug, se reusa
La **nota** ya es única (`papers/<bibcode>.md`, namespace plano) y la extracción no se rehace. Lo que
se duplica son los artefactos de disco, guardados por slug. Medido: **30 bibcodes bajo más de un
slug, 33 copias extra**. No es grave (contenido idéntico, y el campo `fulltext` es estable) pero se
**vuelve a bajar** el PDF cada vez.

### D-19 · La identidad de un paper es `doi` / `arxiv_id`, no el bibcode
El bibcode codifica **dónde se publicó** (`2026arXiv260529946L` → `2026ApJ..1005L..25L`), así que por
construcción cambia al publicarse. Dedup por bibcode **no ve** el par preprint/publicado. Medido en
la instancia: **2 trabajos con dos notas cada uno** (mismo `arxiv_id`, dos bibcodes), sobre 29 notas
con bibcode arXiv.

- **Una sola nota canónica por trabajo**, la del publicado. Dos notas darían dos entradas en el
  roll-up, dos extracciones, conteo doble y un falso positivo de #75.
- Las demás versiones viven en `versions: [{bibcode, pdf_source, eprint_version, fulltext}]`.
- Al publicarse: **renombre** (nuevo bibcode), el viejo baja a `versions` como alias, y se
  **reescriben los wikilinks** de toda la bóveda. Red: el lint bloquea wikilinks rotos. Es el mismo
  procedimiento que el sub-modo *renombrar* de `maintain`, aplicado a un bibcode. **No es un grep
  manual ni depende del SO**: lo hace el script en Python.
- Sólo le pasa a los papers ingestados **en la ventana** entre preprint y publicación.
- **Off-ADS**: la clave sintética `AAAA+Autor` es el mismo principio (usar el identificador citable
  que exista). La maquinaria de versiones no depende del bibcode, así que funciona igual vía
  `doi`/`arxiv_id`.

### D-20 · Cada par verificado guarda **dos hashes**: ancla (nota) y fuente (`.txt`)
El bibcode solo no alcanza: arXiv **v1→v3 conserva el mismo bibcode**, y un re-snapshot web conserva
la misma URL. Con el hash del `.txt` un solo mecanismo cubre los tres casos.

| Hash | Qué mide | Cambia cuando |
|---|---|---|
| **ancla** | qué dice la nota | editás la prosa |
| **fuente** | qué dice el paper | llega otra versión / otro `v` / se re-fetcheó una web |

Ortogonales; cualquiera de los dos que no coincida marca el par. El **descubrimiento** de versiones
nuevas es una pasada de red (junto con retracciones y `corrections`); la **propagación** es lookup
offline del lint.

**Media decisión #13 del contrato queda cerrada** (preprint vs publicado → gana el publicado, el
viejo de alias). La otra media —**dos snapshots web del mismo URL**— sigue abierta; recomendación:
**conviven**, porque el snapshot viejo es la fuente real de lo que la nota afirmó y borrarlo dejaría
afirmaciones sin respaldo.

### T-4 · Dashboard de Obsidian con el estado de la bóveda (anotado por el usuario)
Una nota-tablero con el resumen: cobertura de síntesis por ficha (D-10), pares vencidos por ancla y
por fuente (D-20), triage pendiente, backlog del lint, retracciones y correcciones, fuentes
pendientes.

Dos notas de diseño:
- Es un artefacto de **navegación**, misma familia que `index.md` — no es bibliografía, así que no
  choca con la regla #0, pero **no puede sostener ninguna promesa del contrato** (eso lo cubren la
  ficha materializada y el lint).
- Por eso **acá sí** vale Dataview: la audiencia es humana y el artefacto es derivado. La regla de
  D-11 (materializar) aplica a lo que el contrato promete, no al tablero.

### D-21 · `bearing` sale del paper y pasa a la tabla de la hipótesis (**reemplaza D-16**)
Simetría con estrellas: el paper dice `stars: [tau Ceti]` — eso es un **puntero**; lo que el paper
aporta sobre τ Ceti se escribe en la ficha. Pero `bearing: supports` **no es un puntero, es un
veredicto**: una afirmación de la bóveda guardada como escalar suelto, sin cita, sin evidencia, que
**no puede pasar por `verify-citations`** — no hay nada que un subagente pueda ir a mirar. Evade D-3.

| Dónde | Qué |
|---|---|
| nota del paper | `thesis_links: [achromaticity, crx]` — puntero puro, mecánico, add-only |
| nota de la hipótesis | tabla de evidencia, fila por paper, **con postura, cita textual y verificada** |

Efectos:
- **D-16 se disuelve.** El problema del `bearing` escalar contra `thesis_links` 1:N desaparece solo:
  la postura vive en una tabla que tiene naturalmente una fila por par.
- La nota del paper queda **más estable**, no menos: `thesis_links` sólo crece, mientras que `bearing`
  era el campo que más cambiaba (releer y matizar la postura tocaba la nota del paper).
- Encaja con D-10/D-11: la tabla de evidencia se materializa en la nota igual que el roll-up de papers.
- **`relevance` NO se toca**: no es juicio, es el veredicto determinístico de la lente, y desde D-17 es
  reproducible desde la propia nota.

**Consecuencia:** la nota de paper queda **uniforme** — metadata + verdad de disco + extracción +
punteros + veredicto de la lente. No depende de si el paper entró por una estrella, un método o un
tema de otra disciplina.

### D-22 · Unificar la llave de roll-up de los conceptos
Medido en la instancia: los 18 conceptos usan **tres llaves distintas** para la misma pregunta —
`contains(thesis_links, X)` (12 notas), `contains(methods, X)` (4: bis, contrast, fwhm, s_index),
o las dos con `OR` (4: line_by_line, pca_actividad, scalpels, yarara). Nadie lo decidió: lo improvisó
el LLM al crear cada nota. Un paper tagueado `methods: [bis]` aparece en `bis.md`; el mismo paper
tagueado `thesis_links: [bis]` no.

Los dos campos **se quedan** (significan cosas distintas: `methods` = el paper **usa** eso;
`thesis_links` = el paper **aporta evidencia** sobre eso). Lo que se unifica es **cómo se preguntan**:
una sola regla, aplicada por el script (D-11), lista = **unión**, con una columna que declara por cuál
campo entró.

### D-23 · No hay papers sueltos: todo paper declara al menos un destino
Dos niveles, con severidades distintas:

| Nivel | Qué exige | Severidad |
|---|---|---|
| **destino declarado** | ≥1 puntero a una entidad (`stars`, `thesis_links`, `methods`, `topics` del tema) | **bloqueante** al crear |
| **sintetizado** | el bibcode aparece citado en la prosa de esa entidad | backlog (#75), o `no_sintetizado: <motivo>` |

### D-24 · La lista de papers declara el **origen**: `lente` vs `manual`
Un paper que el usuario pasa explícitamente **es core** — su juicio pisa a la lente y no se
re-filtra (ya resuelto en el framework, #68). Pero la ficha debe distinguir *"core porque la lente lo
clasificó"* de *"core porque lo puso el usuario"*: son cosas distintas para quien lee, y el segundo no
dice nada sobre si la lente lo habría agarrado.

Columna `Origen` en la lista materializada de D-10. Cierra la mitad sin medir de **INV-60**
(*"…con su origen marcado"* — el contrato marca **Falta** comprobar que no se confunde con un core
clasificado). Uso diagnóstico: muchos `manual` = señal de que a la lente le falta un sinónimo, igual
que el apéndice de excluidos.

## 8. Conceptos y métodos

### D-25 · Backends de descubrimiento: ADS + arXiv + OpenAlex
Hoy off-ADS es **declarar**, no **descubrir**: para un tema astro la query encuentra los papers; para
un método de otra disciplina hay que saber de antemano cuáles son. No escala, y rompe el caso de uso
central (métodos de estadística/ML al servicio del foco astro).

Estado real medido: **arXiv no está como búsqueda** — sólo se usa para *bajar* PDFs
(`fetch_arxiv.py` → `export.arxiv.org/pdf/<id>`). Los dos backends son nuevos.

| Backend | Cubre | Da |
|---|---|---|
| ADS | astro | lo de hoy |
| arXiv API | cs.*, stat.*, físicas | título, abstract, categorías. Sin key |
| OpenAlex | todo | metadata + **referencias y citas** + conteo. Sin key |

### D-26 · Relevancia de un tema de método: faceta propia + tres puertas
La lente global **no aplica** y encima es activamente dañina: `require: [rv]` mata justo al paper
fundacional (Hyvärinen no menciona RV ni una vez). Sin filtro tampoco sirve: *"independent component
analysis"* devuelve miles de papers de fMRI, EEG, finanzas y quimiometría.

`topics.yaml` gana una **faceta propia por tema**. Core = matchea esa faceta **Y** entra por ≥1 puerta,
y las tres puertas **son los tres `role`**:

| Puerta | Criterio | Rol |
|---|---|---|
| **lo cita tu corpus** | ≥1 core de la bóveda lo cita | conectado — el que ya te está sirviendo |
| **fundacional en su campo** | muy citado + matchea la faceta | `fundacional` |
| **lente astro** | pasa `relevance.topics` global | `aplicacion` |

Cubre los tres regímenes: **ICA** entra por las tres; **método usado en astro sin fundacional en ADS**
lo rescata la puerta 1; **U-Net sin uso astro** entra sólo por la 2 — y ahí **el hueco es el
producto** (*"esto promete X y nadie lo probó en astro"*).

La puerta 1 es la que más sirve y hoy no existe: *"citado por N core de mi bóveda"* es una señal que
ninguna regex puede expresar. Y es más limpia que las citas globales: Hyvärinen tiene ~30k citas, casi
todas de fMRI y finanzas; lo que lo hace **tuyo** es que **tu** gente lo cita.

### D-27 · Índice de citas local (lo que hace posible la puerta 1)
No se leen bibliografías: es **metadata**. ADS y OpenAlex devuelven la lista de referencias por paper
(`referenced_works`, pedible en lote). Con eso se arma un **índice invertido local**: *obra citada →
qué papers míos la citan*. Después la puerta 1 es un lookup offline.

Es **regenerable** → vive en `build/`. Y no es infraestructura de un solo uso: es el mismo grafo que
alimenta el citation chaining.

### D-28 · Un tema (y una estrella) acumulan **búsquedas**, no una sola
Hoy `topics.yaml` tiene **una** query por tema. Pasa a ser una **lista acumulativa**: `ica.md` puede
nacer de *"independent component analysis"*, sumar *"blind source separation + noise"* un mes después,
y aplicaciones astro más adelante. **Vale igual para estrellas** — no hay nada que lo impida y no es
otro pipeline: es el mismo, con el usuario agregando términos.

Consecuencia de contabilidad: el registro guarda **una entrada `busqueda` por corrida**, y el embudo
**no se puede sumar** — cada entrada distingue **nuevos** de **ya estaban**. Si no, la cabecera (D-12)
mentiría sobre el universo, que es justo el número que promete decir sobre qué afirma la ficha.

### D-29 · Términos del tema: propuestos por el agente, validados por el usuario
Mismo patrón que D-7 (alias de estrella) y D-8 (facetas del objetivo). El usuario dice *"separación
ciega de fuentes"*; el agente propone la familia (fastICA, JADE, Infomax, cocktail party,
non-gaussianity, mixing matrix…), la muestra **en prosa**, y no busca hasta que se aprueba. Con lo que
vuelve, el agente puede sugerir ramas no pedidas (*"apareció mucho NMF, ¿entra o es otro tema?"*).

### D-30 · Estructura de la nota de concepto: el eje es el **régimen**, no el valor
En una estrella hay ground-truth y el desacuerdo es *"dos midieron lo mismo y les dio distinto"*. En un
método **no hay árbitro ni valor verdadero**, y dos papers pueden decir cosas distintas y **tener los
dos razón** — valen bajo condiciones distintas. El modo de falla dominante no es contradecirse: es
**generalizar de más** (el paper afirma X bajo condiciones C, el concepto afirma X pelado). La nota no
dice falso: dice **de más**.

| | Estrella | Concepto |
|---|---|---|
| Unidad de síntesis | `(campo, valor, fuente)` | `(afirmación, condiciones, fuente, rol)` |
| Sección | `## Inventario por eje` | `## Régimen de validez` |

Los veredictos **`aparente`** de `find-contradictions` ("distinto régimen, distinta definición") en una
estrella se descartan; **acá son el hallazgo**. Y sale un hueco que antes no tenía forma: **"régimen no
cubierto"** — la pregunta real del usuario antes de gastar tres meses implementando algo.

**Tema mixto por diseño:** fundacionales (no-astro) y aplicaciones astro conviven en la misma nota;
`role` las distingue, y por eso no se contrastan entre sí (fundacional↔aplicación **es
instanciación**, no desacuerdo).

Estándar extra que las fichas de estrella no tienen: **implementation-ready** — ecuaciones,
inputs/outputs y pasos para codificarlo sin abrir el paper. Con el régimen explícito, porque **una
ecuación sin sus condiciones es implementable y equivocada**.

### D-31 · Ampliar una ficha **integra en su lugar**; el contraste es dirigido por eje
Ratifica D-9 (la ficha es un snapshot) contra los dos extremos:

- **Sección nueva: no.** `## Resumen` + `## Actualización 2026-09` + `## Actualización 2026-11` deja de
  ser un snapshot, y una contradicción queda sentada al lado de lo viejo sin resolver — justo lo que
  la ficha existe para evitar.
- **Re-validar todo: no.** Un paper que habla del `P_rot` no justifica re-verificar las 40 citas del
  inventario de señales.

**Procedimiento:** extraer → identificar **qué ejes toca** → por cada eje comparar contra lo que la
ficha ya dice (*coincide* → nada o fila en el inventario; *agrega* → prosa citada; *contradice* →
`## Inventario por eje` + `disputes[]`) → reescribir **los bloques afectados en su lugar**.

La contabilidad la hace sola la maquinaria de D-4/D-20: esos bloques cambian de ancla → esos pares
quedan marcados → se re-verifican **sólo esos**. No hay que decidir "¿todo o nada?": el hash dice qué
se movió.

**Límite honesto:** detecta contradicciones en los ejes que el paper nuevo toca; **no** re-audita la
ficha entera buscando tensiones viejas. Para eso está `find-contradictions`, operación **explícita**
que barre un eje comparando papers de a pares. Son dos operaciones distintas: **integrar bien lo
nuevo** vs **auditar lo acumulado**.

### D-32 · Hub/radio: relación **declarada**, sin radios sueltos
Un tema que no entra en una nota se parte en **hub** (síntesis del tema completo) + **radios**
(satélites de un sub-aspecto). Ejemplo del usuario: `ica` (hub) / `ica-ruido` (radio).

**Tensión con D-11 (nota autocontenida), y su resolución:** la autosuficiencia es **relativa al
alcance que la nota declara**, no absoluta. El hub contesta solo las preguntas del **tema**; el radio,
las del **sub-tema**. Lo que el hub no puede hacer es prometer algo y mandar a buscarlo afuera: o lo
contesta, o declara explícitamente que ese nivel de detalle vive en el radio.

**Cómo se declara: las dos vías.**
- **El usuario lo decide** explícitamente. Cierra el tema.
- **El agente lo sugiere**, con señal medible — no intuición. La principal usa las `keywords` de D-17:
  un cluster de core que comparte vocabulario controlado que la faceta del hub no cubre
  (*"de los 140 core, 30 forman un cluster sobre elección de kernel: ¿radio aparte?"*). Señales
  secundarias: la nota crece más allá de una lectura, o el `## Régimen de validez` acumula filas que
  sólo aplican a un sub-caso.

**Plomería:** la relación va **declarada en `topics.yaml`** (`parent: <hub>`), no sólo en la prosa. Si
vive sólo en el texto, se rompe con el primer renombre y nadie se entera. Declarada, el lint chequea
los dos sentidos: **no hay radios sueltos** (todo radio tiene su hub) y **todo hub nombra sus radios**.

## 9. Hipótesis

### D-33 · El test corre sobre los **fulltexts**, no sobre la ficha
Testear contra la ficha es testear contra la **síntesis anterior del propio agente**, no contra las
fuentes — y la ficha está **podada** a propósito (la regla de poda tira lo que no cambia cómo se lee
una señal RV), así que la hipótesis puede ser exactamente sobre algo que la poda descartó. El test
corre sobre `vault/raw/fulltext/`; la ficha se usa como **mapa** (qué papers hay, qué dice ya), no
como fuente.

**Los no-core no son una decisión: no tienen fulltext.** Nunca se bajaron; de ellos sólo existe la
metadata de ADS en `## Excluidos por el filtro`. Para incluir uno hay que hacerlo core primero
(`extra_core`) y bajarlo.

### D-34 · La hipótesis declara su **alcance**, y el alcance crece
Una hipótesis es **transversal**: se plantea sobre un conjunto de entidades (temas y/o estrellas). Como
los fulltexts viven por slug, acotar a entidades es acotar a directorios.

El alcance va **declarado en la nota**, porque define qué significa el veredicto: *"no hay
evidencia"* no es *"no existe evidencia"*, es *"no hay evidencia en estos temas, con estos 190 papers,
a esta fecha"*. Sin el alcance escrito, un veredicto negativo se lee como universal — el mismo
**afirmar de más** de D-10.

```
> Alcance 2026-08-23 · temas: [ica, crx, shift_vs_shape] + estrellas: [tau_ceti, au_mic]
>                    · 190 papers · 47 con hits
```

Y **crece** (igual que D-28): sumar un tema deja el veredicto testeado contra un universo que ya no es
el vigente. El lint compara alcance declarado vs corpus vigente y marca si quedó corto — misma familia
de staleness que D-4/D-20.

### D-35 · La hipótesis **no es un radio**
Un radio tiene **exactamente un hub**; una hipótesis cruza varias entidades (`achromaticity` toca
`crx`, `shift_vs_shape`, `fastica_icasso` y además estrellas). `hypotheses` es área reservada aparte:
los papers apuntan con `thesis_links`, la nota acumula la tabla de evidencia (D-21), y los conceptos
que toca se linkean con `[[wikilink]]` en ambos sentidos — **sin** la relación padre-hijo de D-32.

### D-36 · Qué es grounded y qué es inferencia en una nota de hipótesis
No es "100% inferencia del agente". La división es la de siempre:

| Qué | Es | Verificable |
|---|---|---|
| cada **fila de evidencia** (este paper dice X, apoya/desafía) | cita textual + nº de línea del `.txt` | **sí**, pasa por verify-citations |
| el **veredicto global** | agregar N filas en una conclusión → juicio del agente | no → va marcado **`inferencia`** |

La primera es la mayor parte del contenido y es transcripción con respaldo; la segunda es una línea y
va marcada como lo que es. La organización del cuerpo (qué apoya, qué parece ir en contra, dónde no
alcanza la evidencia) es **criterio del agente**, apoyado en la tabla.

### D-37 · `status` con vocabulario cerrado y derivado de la evidencia
Medido en la instancia: `status: supuesto operativo con caveat conocido` — **prosa libre**, y el lint
**no la valida**. Mismo modo de falla que `role` antes de #73: el campo existe, un consumidor lo lee
para decidir si se apoya en la hipótesis, y cada nota dice lo que quiere.

| Status | Significa |
|---|---|
| `abierta` | planteada, sin evidencia suficiente |
| `sostenida` | la evidencia del corpus la apoya |
| `disputada` | hay evidencia en los dos sentidos |
| `refutada` | la evidencia la contradice |

Se **deriva de la tabla de evidencia**: si entra un paper que desafía y el status sigue en `sostenida`,
el lint lo marca (misma familia de staleness).

### D-38 · Cambios concretos al skill `test-hypothesis` (9 pasos hoy)
El procedimiento existe y está definido; estos son ajustes, no rediseño:
1. **Declarar el alcance** (temas + estrellas + corpus + fecha) — hoy no está (D-34).
2. **`bearing` sale del frontmatter del paper** y pasa a la tabla de evidencia con cita — hoy el paso 5
   lo taguea en la nota del paper (D-21).
3. **`status` con vocabulario cerrado**, validado por el lint y derivado de la tabla (D-37).
4. **El veredicto global marcado `inferencia`**, explícito (D-36).

## 10. Contradicciones

### D-39 · `find-contradictions` corre también al cierre, acotado a los ejes que tocó lo nuevo
Es hermana de `verify-citations` en el eje ortogonal (verify: claim ↔ **su propia** fuente;
contradictions: claim ↔ claim **entre** fuentes), y pasa a tener la misma estructura de dos modos.

**Aporta algo que D-31 no cubre:** D-31 compara el paper nuevo contra **lo que la ficha dice**; esto
compara **paper contra paper**. Dos papers pueden discrepar sobre un eje que la ficha nunca mencionó
—porque la poda lo descartó, o porque nadie lo notó— y eso D-31 no lo ve.

| Momento | Alcance |
|---|---|
| **cierre de operación** (entraron papers nuevos) | el paper nuevo contra el corpus ya extraído, **sólo en los ejes que toca** |
| **auditoría explícita** | todos los pares, todos los ejes |
| **a pedido puntual** | *"contradicciones entre estos dos papers, anotalas en tal ficha"* |

Es viable porque el **embudo corre sobre las extracciones, no sobre los fulltexts**: comparar campos
de N notas es instantáneo, y sólo los candidatos confirmados gastan un subagente (que lee **los dos**
fulltexts y devuelve `real | aparente | no-concluyente` con cita de ambos lados). Sin el embudo sería
N² lecturas.

**No cambia la compuerta de aprobación:** sigue **proponiendo**, no escribiendo. Lo que cambia es que
aparece en el cierre de la operación en vez de esperar a que alguien se acuerde de auditar. Junto con
D-4 (pares sin verificar) y D-10 (papers sin sintetizar), el cierre deja **tres cosas a la vista**.

**El veredicto `aparente`** ("distinto régimen, distinta definición, distinta época") se descarta en
una estrella y **es el hallazgo** en un concepto → fila del `## Régimen de validez` (D-30).

### D-40 · No hay disputas sueltas: toda contradicción declara su entidad destino
Análogo de D-23 (no hay papers sueltos). Una contradicción es siempre **sobre algo**, y ese algo es una
entidad de la bóveda — ficha de estrella, concepto, hub o radio, da igual cuál.

| Sobre qué discrepan | Dónde va |
|---|---|
| parámetro o señal de una estrella | `disputes[]` de la ficha + fila en `## Inventario por eje` |
| algo de un método/indicador, **bajo las mismas condiciones** | `disputes[]` del concepto + fila en `## Inventario por eje` |
| algo que difiere **porque el régimen es distinto** (`aparente`) | fila en `## Régimen de validez` del concepto |

En el modo *a pedido puntual* el destino es **mandatorio**: si el usuario no lo dice, el agente
pregunta. Caso raro —los dos papers discrepan sobre algo que no corresponde a ninguna entidad
existente—: o es una entidad que hay que crear, o está fuera del foco y no entra (mismo test de
admisión de la regla #0).

## 11. Barrido de las decisiones de §6

### D-41 · Snapshots web: mismo mecanismo que preprint→publicado (**cierra §6 #13 entera**)
Las fuentes web del modo off-ADS (`fetch_web.py` → `.txt` determinista + `source_url` + `accessed`)
existen para **documentación técnica**: docs de una librería o método, especificación de instrumento,
material de conferencia que nunca salió como paper. **Wikipedia no** — es terciaria y lo que dice
sale de otro lado que es lo que habría que citar; el mecanismo la soporta, la regla #0 no.

Al re-visitar la misma URL: re-bajar → hashear → comparar con el vigente.

- **Igual** → sólo se actualiza la fecha del último chequeo.
- **Distinto** → el nuevo entra a `versions` y pasa a vigente; el viejo **se conserva en disco**
  (es el respaldo real de lo que la nota afirmó cuando lo afirmó). Los pares verificados contra el
  viejo quedan marcados (D-20) y se re-verifican.

La respuesta a *"¿conviven o gana el nuevo?"* es **las dos**: **conviven en disco, hay una sola
vigente** — idéntico al preprint, cuyo `.txt` tampoco se borra.

**Disparadores:** la pasada periódica de red (junto con retracciones, correcciones y versiones
nuevas — **cierra también §6 #9**), a pedido explícito, o al tocar esa fuente en una operación.

**Diferencia con un paper:** una web cambia **sin dejar rastro**, así que `accessed` no alcanza —dos
snapshots del mismo día pueden diferir—. **El hash es la verdad.**

### Estado del barrido de §6 (22 decisiones del contrato)

**Cerradas por esta revisión (6):**

| # | Cómo |
|---|---|
| **#2** alcance del espejo | D-1, D-2 |
| **#5** cobertura de verificación | D-4 |
| **#9** alcance del barrido de retracciones | D-20 + D-41 (una sola pasada de red: retracciones, correcciones, versiones, snapshots) |
| **#11** conteos del registro tras un descarte | D-28 (snapshot por búsqueda, nuevos vs ya estaban) |
| **#13** "mejor calidad" entre artefactos | D-19 (preprint→publicado) + D-41 (web) |

**Respondida de rebote, falta ratificar (1):** **#4** (¿lint gate duro o consejo?) — D-4/D-39 hacen que
la verificación **bloquee** al cerrar una operación, lo que en la práctica es gate duro.

**Abiertas (15):**
- *Ground-truth:* **#1** (NEA deja de reportar: ¿borrar a null o conservar marcado?), **#16** (`data_local`).
- *Severidad:* **#3** (fuga de implementación WARN vs bloqueante), **#7** (umbral de legibilidad),
  **#18** (**la grande**: "no evaluado" ¿bloqueante, backlog o WARN? hoy el repo usa las tres sin regla),
  **#21** (atomicidad: ¿contrato o detalle?).
- *Fuentes problemáticas:* **#8** (prosa que cita un retractado), **#12** (descartada por un carril,
  reaparece por el otro).
- *Operaciones y escotillas:* **#10** (cambiar la lente: ¿negarse a operar o avisar?), **#17** (fuerza
  del pedido explícito, y en CI), **#19** (¿escotillas registradas?), **#20** (¿un juicio persistido se
  pisa con un flag?).
- *Del propio contrato:* **#6** (timestamps vs idempotencia byte-exacta), **#14** (**la otra grande**:
  ¿`inferencia` debe nombrar sus fuentes?), **#22** (ceguera del benchmark).
- *Medio contestada por D-12/D-28:* **#15** (¿verificar que la cadena corrió completa y en orden?).

### D-42 · `inferencia` debe **nombrar sus premisas** (cierra §6 #14)
La regla dura dice: toda afirmación va **citada `[[bibcode]]` o marcada `inferencia`**. Hoy
`inferencia` es **sólo una marca**: no dice de qué deriva, y una inferencia sin fuentes es
indistinguible de una invención con etiqueta.

**Dónde surge** (cuatro momentos):
1. al sintetizar la ficha (conclusión que ningún paper enuncia);
2. en el contraste cross-paper (la tabla tiene prohibida la columna "valor adoptado", así que la
   lectura propia va aparte y marcada);
3. en el veredicto global de una hipótesis (D-36);
4. como resolución de una verificación fallida — **acá estaba el agujero**.

**El agujero, precisado por el usuario.** Hay que separar dos casos que el diseño confundía:

| | Qué pasó | Resolución correcta |
|---|---|---|
| **A** | la afirmación **siempre fue** una inferencia, mal vestida de cita | corregir la etiqueta: legítimo |
| **B** | la fuente calla **y** la afirmación no deriva de nada | **no es inferencia**: es afirmación sin respaldo → **sale de la nota** |

*"No se pudo verificar" ≠ "es inferencia".* Sin exigir premisas, A y B son **indistinguibles** —las dos
terminan como la palabra "inferencia" al final de una frase— y B se cuela. La escotilla se vuelve un
**sumidero**: todo lo que no se pudo respaldar termina ahí, con una etiqueta que se lee como honestidad,
y una vez marcada ya no la mira nadie (`inferencia` está exenta del fan-out por definición).

**Regla:** `(inferencia de [[bib1]], [[bib2]])`. El lint exige **≥1 bibcode**. Poder nombrar las
premisas **es el test que separa A de B**.

Queda **medio verificable**: el subagente no puede chequear la conclusión (es un razonamiento, no un
hecho) pero **sí que las premisas digan lo que se les atribuye** — que es donde en la práctica se
rompen las inferencias.

**Además, documentarlo en la capa que enseña a los agentes a navegar la bóveda** (`CLAUDE.md` /
`README.md` / cabecera de las notas): que quede **doblemente claro** que una inferencia es una lectura
del agente, **no** algo textual de la fuente. Es la audiencia que más fácil la toma como dato.

### D-43 · Un chequeo que no puede correr **reporta error** (cierra §6 #18)
Nunca contribuye un cero al total, nunca calla. Categoría propia *"no evaluado: falta X"* y salida
distinta de 0. Cierra los dos casos mudos vivos: sin historial de `git` el chequeo de verificación
vencida devolvía `stale=0` en silencio; con la lente rota no decía una línea (ya cerrado por D-6).

**Dónde se registra:** en el **reporte del lint** (`outputs/lint-<fecha>.md`), no versionado — *"en esta
máquina falta git"* es un hecho del **entorno**, no de la bóveda, y no hay nada que arrastrar. A
`vault/wiki/log.md` va sólo si afectó una operación (*"no se pudo cerrar el ingest de X: chequeo de
verificación stale no evaluado"*). No hace falta un log nuevo.

### D-44 · El lint **avisa, no bloquea el commit** (cierra §6 #4)
Decisión del usuario: el lint reporta y el humano resuelve después. No hay gate de git.

**No contradice a D-4/D-39** — son dos cosas distintas:

| | Quién frena | Qué frena |
|---|---|---|
| **D-4 / D-39** | el agente | no declara **cerrada la operación** con pares sin verificar o contradicciones sin resolver |
| **D-44** | nadie | `git commit` nunca se impide: el repo es del usuario |

O sea: el agente es estricto con **su propio trabajo**; el commit es decisión del humano.

### D-45 · Una sola pasada de red para todo lo que cambia afuera (cierra §6 #1)
Cuatro eventos de la **misma familia**: algo fuera de la bóveda cambió después del ingest y eso
**envejece lo ya extraído**.

| Qué cambia | Detección |
|---|---|
| paper retractado / corregido | **ya existe** — `check_retractions.py` (Crossref) |
| preprint → publicado | nueva (D-19) |
| snapshot web cambió | nueva (D-41) |
| **NEA cambió un valor** | nueva (ésta) |

**Estado del ground-truth hoy:** es un **snapshot congelado**. `fetch_ground_truth.py` **no pisa** el
JSON salvo `--force` (*"NEA cambia valores entre releases — refrescar es una decisión, no un
side-effect"*), y **nada avisa** de que hay diferencia. Un `P_rot` retirado por NEA no llega nunca a la
bóveda.

**Regla:** la pasada compara contra el snapshot y **avisa siempre, mostrando el diff**:

```
tau_ceti: NEA cambió desde el snapshot del 2026-06-12
  · P_rot_days   34.5 → (ausente)
  · h.K_ms       0.39 → 0.41
```

**Y pregunta antes de aplicar**, porque una desaparición puede ser un error de ellos, un cambio de
release o un dato genuinamente retirado, y las tres se ven igual desde afuera.

**Al refrescar, se borra** (decisión del usuario): el campo va a `null`. Conservarlo "marcado como
stale" rompería INV-06/07 — en el frontmatter sólo vive lo que la autoridad dice **hoy**. Si la prosa
mencionaba ese valor, el refresh toca el bloque, cambia el ancla (D-20) y esos pares quedan marcados
para revisar.

### D-46 · Caducidad del barrido externo: estado visible en el dashboard (cierra §6 #9 de verdad)
D-45 unificó **qué** cubre la pasada de red; faltaba **cuándo** corre. Hoy: la cadena de ingest chequea
retracciones **sólo del slug en curso**, el barrido completo es **manual** (skill `maintain`), y el lint
sólo surface flags **ya estampados**. O sea: la **detección** depende de que el usuario se acuerde; el
**reporte** es automático pero sólo de lo ya detectado. Un paper retractado hace seis meses sigue
respaldando prosa con el lint en verde.

La bóveda registra **cuándo fue la última pasada de red**, y eso se muestra en el **dashboard** (T-4)
— no como bloqueante ni como backlog ruidoso del lint. El usuario lo consideró de baja gravedad; lo
que importa es que la opción de barrer exista y que el estado sea **visible** en vez de depender de la
memoria.

```
última pasada de red: hace 47 días  (retracciones · correcciones · versiones · webs · NEA)
```

No corre nada solo — no hace falta cron ni demonios.

### D-47 · Prosa que cita un paper retractado: se **marca**, no se borra (cierra §6 #8)
El lint ya **bloquea** al detectar `retracted: true` (fuente retractada citada rompe la frontera dura),
pero no decía qué hacer con lo ya escrito.

- **Caso fácil:** si otro paper **no retractado** sostiene lo mismo → se reasigna la cita y listo.
- **Caso real** (la retractada es la **única** fuente): la afirmación **se marca en línea** como
  sostenida por fuente retractada. No se borra.

Descartadas: **borrar** (destruye información — a los seis meses nadie sabe que ese hecho estuvo ahí ni
por qué se fue) y **disputa histórica** (una retractación no es un desacuerdo entre pares: es una
fuente invalidada).

Condición: la marca tiene que ser **visible en la línea**, no una nota al pie. Cumple los dos
principios a la vez — no mentir y no destruir.

### D-48 · `--no-triage` se elimina; las otras escotillas quedan registradas (cierra §6 #19 y #20)
**Contexto que hace la decisión no-burocrática:** estas banderas **no las tipea el usuario, las tipea el
agente** al correr la cadena. Son escotillas del agente, no del usuario. La pregunta real es: *¿puede el
agente tomar decisiones que cambian lo que la bóveda afirma sin dejar rastro?*

- **`--no-triage` se elimina.** Apaga la compuerta de triage — el paso de más juicio del ingest — así
  que los candidatos del citation chaining (**18% de precisión medida**) entran **todos, sin que nadie
  los mire**. Encima hoy **pisa los descartes ya persistidos** (INC-2): papers que el usuario rechazó
  con motivo vuelven a entrar en silencio. No está documentada en ningún lado. La auditoría la marcó
  como la más delicada de las nueve sin documentar. Más simple que regularla: que no exista.
- **`--force` y `--yes` se quedan** (tienen uso legítimo: re-bajar un ground-truth viejo, correr una
  re-clasificación esperada sin prompts) **y quedan registradas** en el `busqueda` del registro, y por
  lo tanto en la cabecera de la nota (D-12).

Recordatorio de qué es el triage: aplica **sólo a los candidatos del citation chaining** (los de la
query directa los decide la lente, sin juicio). Tres montones: **van** → `extra_core`; **no van** →
descartados **con motivo persistido**, nunca re-propuestos; **dudosos** → al usuario.

### D-49 · Lente desincronizada: **avisa por ficha con el diff**, backlog del lint (cierra §6 #10)
Cambiar `relevance.topics` deja los veredictos core/no-core ya escritos **calculados con una regla que
ya no existe**: la ficha dice "193 core" y con la lente de hoy serían otros.

**No se niega a operar** — bloquear dejaría la bóveda inutilizable por editar una regex, y
re-clasificar es caro y no siempre urgente. **Avisa, pero por ficha y con el diff a mano**, para que la
decisión sea informada:

```
⚠ lente desincronizada (backlog, no bloquea)
   tau_ceti  · clasificado con lente del 2026-06-12 · +12 entrarían / −3 saldrían
   au_mic    · clasificado con lente del 2026-08-15 · sin cambios
```

**Va al lint, no al dashboard** (a diferencia de D-46): la pasada de red vencida es un hecho del
**entorno**; la lente desincronizada es una **inconsistencia interna de la bóveda** —la ficha declara un
universo que no corresponde a su propia configuración—, misma familia que "la ficha contradice al
ground-truth". El dashboard muestra sólo el agregado.

**Rédito no previsto de D-17:** el lint puede calcular el diff **offline y sin red**, porque la nota de
cada paper guarda los tres insumos de la clasificación (título, abstract, `keywords`). Hasta ahora eso
requería `build/` vivo o volver a pedirle todo a ADS.

### D-50 · Fuga de implementación: WARN de mínima, detector ampliado, y **la bóveda es read-only desde afuera** (cierra §6 #3)
**El problema medido:** la regla más fuerte del sistema (frontera dura, "no negociable") está
custodiada por el chequeo más débil (WARN heurístico) — y encima **mirando el lugar equivocado**. La
heurística busca *perillas* (parámetros de ajuste de un pipeline propio: un contraste `C`, pesos `w_j`,
"cuánto inyectar"). Los dos casos reales encontrados hoy en la instancia tienen **otra forma**: nombrar
al repo consumidor.

- `tau_ceti.md`: *"…lo leen Obsidian/Dataview y **los scripts de ICA**"*
- `achromaticity.md`: *"**Supuesto de trabajo del pipeline ICA por canal:** …"* — define la hipótesis por
  lo que el código asume, en vez de por lo que dice la literatura. Un lector externo entiende que la
  acromaticidad es una convención del usuario, no un hecho publicado.

(Los dos son herencia de la regla vieja; la migración está escrita en `CLAUDE.md` y esa instancia nunca
se migró.)

**Detector ampliado, en dos mitades** — respetando la división framework/instancia que ya existe
(el template trae el mecanismo, la instancia el contenido, igual que `concept_areas`):

| Mitad | Qué detecta | Dónde vive |
|---|---|---|
| **genérica** (viaja con el template) | perillas (como hoy) + frases de auto-referencia al consumidor: *"nuestro pipeline"*, *"nuestro código"*, *"para el repo"*, *"downstream"*, *"supuesto de trabajo de…"* | framework |
| **declarada** (por instancia) | menciones a los nombres propios de los repos consumidores | `downstream: []` en `objective.yaml`, **vacío = chequeo apagado** |

Severidad: **WARN** — la mitad heurística tiene falsos positivos. La mitad declarada casi no los tiene y
podría bloquear más adelante sin costo. Va también al **dashboard** (T-4).

**Y lo que ataca el vector, no el síntoma (aporte del usuario):** la contaminación entra cuando un
agente que trabaja en el **repo consumidor** abre la bóveda y "ayuda" anotando por qué algo importa
downstream. Entonces:

> **La bóveda es de sólo lectura desde afuera.** Sólo escriben sus propias operaciones (ingest, append,
> maintain, verify). Quien viene del lado consumidor **lee y se va**; si encuentra algo que corregir, se
> lo dice al usuario.

Hoy **no está escrito**: `CLAUDE.md` tiene un "contrato con quien consume la bóveda" pero dice otra cosa
(que lo que saques viaje con su `[[bibcode]]`); no dice que no puedas escribir. Hay que agregarlo **donde
un agente externo lo va a leer**, no enterrado en el `CLAUDE.md` del framework. Con eso el WARN pasa a ser
lo que debe ser: **una red por si la regla se saltea**, no el mecanismo principal.

### D-51 · Umbral de legibilidad: **no es decisión de intención, es una medición** (cierra §6 #7)
La pregunta del contrato (*"¿quién fija el umbral y con qué evidencia? laxo deja entrar basura citable;
estricto manda a pendiente fuentes que sirven"*) no se resuelve decidiendo: se resuelve **midiendo**.

A la cola de trabajo: correr el detector sobre el corpus real (**672 fulltexts** de la instancia),
mirar falsos positivos y negativos, y **sacar un número**. El usuario aclara que lo ya ingestado
tampoco se curó con criterio, así que la medición sirve además para saber en qué estado está el corpus
existente.

### D-52 · Descartado por un carril y declarado por el otro: **avisa y procesa** (cierra §6 #12)
Comportamiento actual (medido): avisa y sigue. **Se ratifica**, con la misma razón de D-24: si el
usuario lo pasa explícitamente, **es core** — su juicio nuevo pisa al viejo. El aviso le da el dato para
arrepentirse (*"ojo, esto lo descartaste el 15-08 porque decía X"*).

**Se agrega:** el descarte viejo queda **anulado explícitamente** en el registro, con fecha, en vez de
quedar ahí contradiciendo lo que efectivamente se hizo.

### D-53 · Atomicidad: es **contrato**, no detalle (cierra §6 #21)
Hoy 5 writers son atómicos (tmp + rename) y **el que más escribe no**: las notas. Se declara el
invariante *"toda escritura en `vault/` es atómica"* — obliga a un helper único y a un test por comando.
Razón: es barato, y git **no** protege de un archivo corrupto (protege del archivo anterior, que es otra
cosa).

Pendiente relacionado, ya en la cola de STATUS: el `.tmp<pid>` huérfano si el fallo ocurre mientras se
escribe el temporal.

### D-54 · Idempotencia y tiempo: la fecha **se congela** si nada sustantivo cambió (cierra §6 #6)
Correr la cadena dos veces da el mismo árbol byte a byte. Si una nota registra *cuándo* corrió algo, la
segunda corrida movería la fecha sin que haya cambiado nada. Se congela: **diffs limpios**, al precio de
que la fecha diga "cuándo cambió esto" y no "cuándo se miró". Es la lectura útil de las dos.

### D-55 · Ceguera del benchmark: **por construcción, no por instrucción** (cierra §6 #22)
El auto-benchmark siembra citas falsas para medir la tasa de error del verificador. Hoy la clave vive en
el **mismo archivo** que el examen y lo único que impide mirarla es que el skill diga que no. Se parte
`bench.json` en **examen** y **clave**. Cuesta poco, y una medición del propio error que depende de que
el agente se porte bien **no mide nada**.

### D-56 · `data_local`: se marca **no verificable en esta máquina**, nunca bloquea (cierra §6 #16)
El campo apunta a datos crudos fuera del repo (`../ICA_Solar/.../TAU_CETI`). Validar que exista volvería
la bóveda **no portable de hecho** (falla en cualquier otra máquina); ignorarlo pierde la señal. Se
reporta como *no verificable acá*, sin bloquear.

---

## 12. Cierre del barrido de §6

**Las 22 decisiones del contrato quedan resueltas**, salvo la parcial:

| # | Resuelta por |
|---|---|
| #1 | D-45 | #2 | D-1, D-2 | #3 | D-50 | #4 | D-44 |
| #5 | D-4 | #6 | D-54 | #7 | D-51 (a medir) | #8 | D-47 |
| #9 | D-45 + D-46 | #10 | D-49 | #11 | D-28 | #12 | D-52 |
| #13 | D-19 + D-41 | #14 | D-42 | #15 | **parcial** (D-12, D-28) | #16 | D-56 |
| #17 | D-48 (parcial: `--force`/`--yes` registradas) | #18 | D-43 | #19 | D-48 | #20 | D-48 |
| #21 | D-53 | #22 | D-55 | | |

### D-57 · Cada paso de la cadena estampa su paso por el registro (cierra §6 #15)
Hoy sólo el **paso de búsqueda** deja rastro estructurado (`busqueda`, escrito por `query_ads`). Lo
demás depende de que el agente escriba prosa en `vault/wiki/log.md` al cerrar — y si la cadena se corta
a la mitad, o alguien corre los scripts sueltos y saltea uno, puede no quedar nada. La pregunta
*"¿esta ficha se armó con la cadena completa?"* **hoy no se puede contestar**: se infiere de que la
ficha tiene buena pinta.

```yaml
cadena:
  - {paso: query_ads,          fecha: 2026-08-23, version: 1.23.1}
  - {paso: fetch_ground_truth, fecha: 2026-08-23, version: 1.23.1}
  - {paso: fetch_pdf,          fecha: 2026-08-23, version: 1.23.1}
  - {paso: extract_fulltext,   fecha: 2026-08-23, version: 1.23.1}
  - {paso: make_notes,         fecha: 2026-08-23, version: 1.23.1}
```

El orquestador ya sabe el orden — sólo hay que anotarlo. El lint puede entonces decir *"tau Ceti: la
cadena se cortó en `fetch_pdf`"* en vez de que se descubra por casualidad. No es un mecanismo nuevo: es
D-12 y D-28 extendidos a los pasos.

**Con esto, las 22 decisiones de §6 quedan cerradas.** (#7 resuelta como *medición pendiente*, no como
decisión.)

---

## 13. Tamaño del trabajo: las 57 decisiones por esfuerzo

### A · Ya funciona así — sólo documentar o ratificar (7)
| | |
|---|---|
| D-3, D-5 | ratifican la regla dura y el estándar de la ficha |
| D-9, D-11 | ratifican el snapshot destilado y la autosuficiencia |
| D-23 | el destino ya se exige en la práctica; falta el bloqueo explícito |
| D-44 | el lint ya avisa sin bloquear el commit |
| D-52 | avisa y procesa: comportamiento actual, ratificado (+ anular el descarte viejo) |

### B · Cambio chico — un campo, una categoría de lint, un ajuste de skill (24)
| | |
|---|---|
| **Schema de notas** | D-1 (invertir autoridad de `spectral_type` + campo de auditoría), D-2 (`DISPUTE_SOURCES` abre a `nea`/`simbad`), D-17 (`keywords` al frontmatter), D-21 (`bearing` sale del paper), D-22 (llave de roll-up unificada), D-24 (columna `origen`), D-37 (`status` vocabulario cerrado), D-56 (`data_local` no verificable) |
| **Lint** | D-6 (lente vacía bloquea), D-43 (categoría *no evaluado*), D-47 (marca de retractado), D-49 (lente desincronizada con diff), D-50 (detector ampliado + `downstream: []`), D-32 (hub/radio bidireccional) |
| **Scripts** | D-18 (reusar artefacto por bibcode), D-48 (eliminar `--no-triage`, registrar `--force`/`--yes`), D-53 (helper atómico único), D-54 (congelar fecha), D-55 (partir `bench.json`), D-57 (estampar pasos de la cadena) |
| **Skills** | D-7 (alias validados), D-8 (validar con papers reales), D-29 (términos propuestos), D-33 (test sobre fulltexts), D-35 (hipótesis no es radio), D-36 (grounded vs inferencia), D-38 (los 4 ajustes a `test-hypothesis`), D-40 (destino mandatorio), D-42 (`inferencia` con premisas) |

### C · Feature nueva — mecanismo que no existe (11)
| | Qué hay que construir |
|---|---|
| **D-4 + D-20** | **el ancla**: hash por bloque markdown + hash de fuente, columna en el bloque de verificación, chequeo offline, migración. **Es la pieza central** — de ella dependen D-31, D-41, D-45 |
| **D-10** | lista de papers materializada con estado de síntesis por paper, estampada como cirugía idempotente |
| **D-12** | bloque de estado con las tres fechas y sus conteos |
| **D-13 + D-14** | leer todos los core con un subagente por paper, y declarar lo que no se lea |
| **D-19** | identidad por `doi`/`arxiv_id`, `versions[]`, renombre + reescritura de wikilinks |
| **D-25** | backends arXiv + OpenAlex |
| **D-26** | relevancia por tema con las tres puertas |
| **D-27** | índice de citas local invertido |
| **D-28** | búsquedas acumulativas + contabilidad nuevos/ya estaban |
| **D-30** | `## Régimen de validez` en conceptos |
| **D-41 + D-45 + D-46** | pasada de red unificada (retracciones, correcciones, versiones, webs, NEA) + caducidad |

### Fuera de esta clasificación
- **D-15, D-16, D-31, D-34, D-39, D-51** — consecuencias o reubicaciones de lo anterior; D-16 queda
  **reemplazada** por D-21; D-51 es una **medición** a correr, no código.
- **T-1** (linkeo interno), **T-2** (frontmatter de papers, ya cubierto), **T-3** (setup con costo),
  **T-4** (dashboard) — temas anotados.

### Lectura
**El grueso es B** (24 cambios chicos, mayormente schema + lint), pero **el camino crítico es C**, y
dentro de C hay dos piezas que habilitan al resto:

1. **El ancla (D-4/D-20)** — sin ella no funcionan la verificación incremental, la detección de
   versiones ni el refresh dirigido.
2. **El índice de citas (D-27)** — sin él no funcionan la puerta 1 de D-26 ni el chaining mejorado.

**El dashboard (T-4)** es el único entregable visible para el usuario y depende de casi todo lo demás,
así que va último.
