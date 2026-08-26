---
name: verify-citations
description: Usar para verificar, afirmación por afirmación, que las citas [[bibcode]] de una nota de la wiki (query, hipótesis, ficha, concepto) realmente están respaldadas por el texto completo de la fuente. Se corre como paso de cierre al armar/editar una query o hipótesis, o cuando el usuario pide "rechequeá las citas / ¿esto lo dice el paper?". Implementa el chequeo claim↔evidencia (pipeline tipo CiteAudit) sobre el corpus cerrado de la bóveda. Veredictos: soportada / no-soportada (la fuente calla) / contradice (la fuente afirma lo contrario → candidata a disputa, no sólo cita rota), en un EJE SEPARADO de la `condición` bajo la que la fuente lo afirma; en transcripciones de tablas/listas chequea además la completitud (lo que la nota omite).
version: 1.9.0
---

# Verify-citations — chequeo claim↔evidencia contra el fulltext

Operación de **verificación** del patrón LLM Wiki (extensión propia de esta wiki; el lint canónico de
Karpathy sólo hace chequeos de salud estructurales, **no** valida que la fuente respalde la afirmación).
Tapa el *grounding gap* / *epistemic drift*: el LLM puede escribir una cita correcta junto a una
afirmación que el paper **no dice** (estudios: 50–90% de citas en texto largo de LLM no están
plenamente respaldadas). Acá cada afirmación se contrasta contra el texto real de su fuente.

> **Ventaja del corpus cerrado:** corpus **cerrado** — hay un `.txt` por bibcode en `vault/raw/fulltext/`. Se
> saltea el *retrieval* (la parte que mete errores en los verificadores generales): ya sabemos qué
> archivo leer. El chequeo es directo passage-matching.
>
> **El fulltext es una extracción DETERMINISTA** de la capa de texto del PDF (`pdftotext -layout`,
> sin LLM). Por eso la **cita textual que encuentra el verificador son las palabras reales del
> paper** y el nº de línea es un localizador greppable estable. **Caveats:** `pdftotext` puede
> desordenar doble-columna, ecuaciones, tablas, ligaduras y guionado; y un PDF **escaneado sin capa de
> texto** da `.txt` vacío/basura. Por eso: si una afirmación **no** aparece textual en el `.txt` —
> **tras agotar la estrategia de matcheo de abajo (#44)** — antes
> de declararla `no-soportada` considerar que puede ser un **artefacto de extracción** (ecuación/tabla)
> → en ese caso abrir el **PDF** (`vault/raw/pdfs/<slug>/<bibcode>.pdf`) para esa afirmación puntual, o
> marcarla **`no verificable por extracción`** (distinto de `no-soportada`).
>
> **Cómo se cuentan las líneas (convención fija, #29):** el nº de línea de la evidencia se obtiene
> con **`grep -n`** o leyendo el archivo directamente (Read) — **no** con `splitlines()` de Python:
> los `.txt` de `pdftotext` traen un **form feed** (`\x0c`) por página que Python cuenta como salto
> de línea extra → la numeración se corre **+1 por página** y el error CRECE a lo largo del archivo
> (medido: 532/535 `.txt` del corpus con form feeds; en un paper de 12 páginas la última cita queda
> ~10 líneas afuera — suficiente para que una revisión posterior no encuentre la frase y la marque
> como rota). Si hace falta Python, `split("\n")` numera igual que `grep -n`.
> Relacionado: en papers a **dos columnas** `pdftotext -layout` entrelaza ambas columnas en la misma
> línea física — un rango de líneas **no** es un rango de lectura contigua (una oración puede
> arrancar en la columna izquierda de L229 y seguir en la derecha de L204). Los números de línea
> son **punteros greppables**, no extractos para leer de corrido.
>
> **Cómo buscar en el `.txt` (estrategia de matcheo, #44).** El entrelazado de arriba obliga a
> buscar distinto: `grep` es orientado a líneas, y en un `.txt` multi-columna (medido: 472/644 del
> corpus, 73%) una oración cruza el salto de línea física — buscarla entera da **falso negativo**
> aunque el texto esté y sea legible (medido: 9/24 pares ~38% no encontrados con la oración
> completa; 24/24 localizados con fragmentos cortos).
> 1. **Escalera de acortamiento:** empezar por la oración completa y, si no aparece, acortar a un
>    **fragmento distintivo contenido en una sola línea física** (típicamente 3–6 palabras; el largo
>    útil depende del ancho de columna del PDF, por eso se **acorta hasta encontrar** en vez de fijar
>    un largo — así un paper a una columna sigue matcheando la frase entera sin perder precisión).
> 2. **De-hifenado:** si el fragmento corto tampoco aparece, el corte de línea puede partir una
>    palabra con guión (`mag-` / `nitude`): reintentar partiendo el patrón por el guión, o buscar
>    un fragmento que lo esquive.
> 3. Sólo **agotados 1 y 2** corresponde considerar artefacto de extracción (ecuación/tabla/escaneo)
>    → abrir el PDF o marcar `no verificable por extracción`.
>
> ⛔ **Prohibido normalizar espacios sobre el archivo entero** (`re.sub(r"\s+", " ", texto)` o
> equivalente): en una línea física a dos columnas eso **empalma el final de la columna 1 con el
> principio de la columna 2**, fabricando adyacencias que el paper no tiene — puede hacer pasar como
> `soportada` una afirmación **inventada** (falso positivo: el modo peligroso, peor que el falso
> negativo de arriba). Y normalizar **por línea** tampoco alcanza (#46): colapsar la **canaleta** de
> la misma línea física fabrica la misma adyacencia col.1→col.2, sólo que dentro de la línea. La
> forma segura, si hace falta normalizar: **partir antes cada línea física en la canaleta** (un run
> de 8+ espacios es separador de columnas, no espacio — el umbral vive en
> `measure_layout.CANALETA_MIN`) y normalizar **por segmento de columna**. Los invariantes están
> pineados en `tests/test_multicolumn_matching.py`; la prevalencia en una bóveda concreta la mide
> `scripts/measure_layout.py`.
>
> ⚠ **`symbols_lost: true` — las ECUACIONES no están en el `.txt` (#113).** Si la nota del paper
> trae ese campo (o el `.txt` abre con `# Almagesto — simbolos NO extraidos`), `pdftotext` dejó el
> marcador `(3)` y **vació su cuerpo**: el archivo parece tener la fórmula y no la tiene. Para esos
> pares, **la evidencia se cita por PÁGINA del PDF**, no por nº de línea, y se lee
> `vault/raw/pdfs/<slug>/<bibcode>.pdf` con el parámetro `pages` (que **rasteriza** la página, así
> que el verificador *ve* la fórmula). ⛔ **No declares `no-soportada` una ecuación que no aparece
> en el `.txt` de una fuente marcada así** — es el falso negativo que empuja a debilitar una
> afirmación correcta, y es exactamente el caso que este campo existe para señalar. La **prosa** de
> esas fuentes sí es citable por línea, como siempre.
>
> **Excepción OCR — citable con salvedad:** si la nota del paper trae `fulltext_source: ocr` (el
> contrato del frontmatter lo espeja — no hace falta abrir el `.txt` para saberlo) o el `.txt` abre
> con el header `# Almagesto — fulltext por OCR` (`source: ocr`), vino de tesseract (PDF escaneado
> o con fuentes sin ToUnicode que
> `pdftotext` no pudo leer; lo estampa `extract_fulltext.py`). Sigue siendo determinista y citable,
> pero el OCR puede errar **símbolos, ligaduras y notación matemática**: la verificación vale para
> **prosa**; ante una discrepancia puntual de símbolos/números en una ecuación, abrir el **PDF** para
> esa afirmación en vez de declararla `no-soportada`/`contradice`.
>
> ⚠ **Excepción preprint — el `.txt` puede ser OTRA VERSIÓN del paper (#57).** Si la nota trae
> `pdf_source: eprint` (y, cuando se conoce, `eprint_version: v1`), el texto salió de **arXiv**, no
> de la versión publicada que identifica el `[[bibcode]]`. Un **v1 pre-referato** puede traer
> valores, secciones y hasta conclusiones distintas. El daño va en la dirección **menos obvia**:
> ante una discrepancia entre la nota (valor **publicado** — típicamente de NEA o del abstract de
> ADS) y el `.txt` (eprint), el protocolo de acá manda "bajar la afirmación a lo que dice la
> fuente" → **se corrompería el valor publicado con el del preprint, y quedaría registrado como un
> hallazgo del chequeo**. Regla: con `pdf_source: eprint`, una discrepancia **numérica** contra un
> valor publicado es candidata a **diferencia de versión**, no a cita rota → abrir el PDF publicado
> para esa afirmación, o marcarla como diferencia de versión; **no** "corregir" la nota hacia el
> eprint. Con `pdf_source: null` (desconocido: ni marca de arXiv ni registro del fetcher) aplicá el
> mismo cuidado ante una discrepancia numérica — desconocido **no** es "publicado". La prosa y los
> mecanismos se verifican igual.

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

**Addendum para transcripciones** (agregar al prompt cuando el par sale de una tabla o lista de la
fuente): *"Esta afirmación es una fila/ítem de una transcripción. La nota transcribe de este paper la
lista completa: «…». Decime APARTE del veredicto: ¿la tabla/lista del paper tiene MÁS filas/ítems que
ésos? Si sí, listá los que faltan con su nº de línea. Ojo con el layout: la tabla puede estar
entrelazada con otra en las mismas líneas físicas — contá las filas de LA tabla que corresponde."*

### 3. El corte: contenido distintivo, sin grado

**No hay score.** El veredicto sale de **una** pregunta, y es de sí o no: ¿la evidencia citada toca
el **contenido distintivo** de la afirmación —el sujeto/valor/mecanismo que la hace específica—?
→ `soportada`, y lo que falte va a `condicion`. ¿La coincidencia es sólo temática (el fenómeno
general, un término suelto, la mera cercanía)? → `no-soportada`.

⚠ **La columna `Score` 0–10 se eliminó en 1.42.0, y es la misma lección que `parcial`.** Un grado
numérico reintroduce por la ventana el eje que 1.39.0 sacó por la puerta: la zona intermedia no se
puede definir porque es de grado, y el umbral (≥7 / <4) nunca se calibró contra nada. **Es además lo
que hace el campo**: los verificadores de referencia etiquetan **binario** (FActScore: *supported* /
*not-supported*) y los que agregan un tercer valor usan un **vocabulario cerrado**, no una escala
(VeriScore: *supported* / *inconclusive* / *contradictory*) — que es exactamente el nuestro. Ningún
sistema comparable gradúa el soporte. La corrida del 2026-08-25 ya devolvió la columna en `—`
porque el fan-out no la había producido: se eliminó en vez de rellenarla con un número que nadie
midió.

⚠ **`parcial` se eliminó en 1.39.0.** Fusionaba dos preguntas ortogonales: «¿la fuente respalda
esto?» (textual, decidible contra el `.txt`) y «¿la afirmación está completa?» (juicio de grado).
Medido el 2026-08-25 sobre una ficha real: **dos corridas independientes de este mismo fan-out**,
jueces nuevos y ciegos, **60 pares comparados → 95 % de coincidencia**, y **las tres divergencias
caían exactamente en el borde `soportada`↔`parcial`**, todas hacia el lado estricto; `contradice`
reprodujo 2/2. El umbral no estaba definido — y no se puede definir, porque es de grado. Todo lo que
era `parcial` se descompone sin pérdida en `soportada` + `condicion`, o en `no-soportada`.
- **`contradice`** manda sobre los otros dos (no es un grado de soporte sino evidencia **en contra**,
  con cita textual de lo contradicho): se resuelve como corrección o disputa (paso 4), no como cita rota.

### 4. Resolver lo que falla (no dejar pasar)
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
| 1 | YZ CMi κ ≈ −2.6 | [[2018A&A...609A..12Z]] | soportada | "gradient of −2.6 Np−1 (±21%)" (L966) | 3f9c1e2ab4 | 7b40d8aa11 | — |
| 2 | activas −2.4/−2.6 | [[2025A&A...696A..27J]] | no-soportada→corregida | el paper da −2.65 a −3.70; el −2.6 es de Zechmeister | c17e0a9b22 | 55aa10ffe3 | — |
| 3 | señal g confirmada | [[2016A&A...585A.134D]] | contradice→disputa | "is an artifact of... rotation" (L2101) → tagueada en disputes[] | 90bb4c1de7 | 0ab77e2c41 | — |
| 4 | P_rot = 36,5 d | [[2017MNRAS.468.4772S]] | soportada | "36.5 ± 2.3" (L320) | 5c1de790bb | 41c0ab772e | promedio pesado de 4 proxies; el K de 0,50 m/s es de la señal a 35,0 d, no a 36,5 |

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
```

- **`Ancla`** — sha256 (10 hex) del bloque markdown normalizado que contiene la afirmación.
  Reflowear la nota **no** la mueve; cambiar un número **sí**. Una fila/ítem sin `[[bibcode]]`
  propio hereda el del caption y hashea **los dos** bloques.
- **`Hash fuente`** — sha256 (10 hex) del `.txt` que leíste. Es lo que detecta que el PDF se
  re-extrajo y la fuente ya no dice lo mismo, **sin que la nota se haya tocado** — ninguna medida
  basada en fechas de la nota puede ver eso.

**Cerrá con `python scripts/lint.py --cierre`** (R-1): ahí un par vencido **frena la operación**,
porque significa que no terminaste. Sin el flag es la pasada periódica y sólo reporta.

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
