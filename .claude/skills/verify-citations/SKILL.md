---
name: verify-citations
description: Usar para verificar, afirmación por afirmación, que las citas [[bibcode]] de una nota de la wiki (query, hipótesis, ficha, concepto) realmente están respaldadas por el texto completo de la fuente. Se corre como paso de cierre al armar/editar una query o hipótesis, o cuando el usuario pide "rechequeá las citas / ¿esto lo dice el paper?". Implementa el chequeo claim↔evidencia (pipeline tipo CiteAudit) sobre el corpus cerrado de la bóveda. Veredictos: soportada / parcial / no-soportada (la fuente calla) / contradice (la fuente afirma lo contrario → candidata a disputa, no sólo cita rota); en transcripciones de tablas/listas chequea además la completitud (lo que la nota omite).
version: 1.5.0
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
  `CLAUDE.md`), **antes de lint/commit**: `ingest-star` (ficha + papers, paso 5b), `ingest-topic`
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
  **disputas** (`disputes[].alt` y `.note` vs el paper discrepante — p. ej. la Tabla 9 de Díaz+2016),
  los **mecanismos**, la **síntesis**, y cualquier **valor que el prose atribuya a un paper** (si la
  oración cita a Mayor+2009, el número debe ser el de Mayor, no el de NEA → si no, corregir el prose a
  los valores de la fuente y dejar NEA en la tabla).
- Afirmaciones marcadas **`inferencia`** explícitamente → se **saltean** del fan-out y se listan aparte
  como "inferencia declarada" (válidas sin cita; ver frontera/estilo en `CLAUDE.md`).
- Definiciones/derivaciones internas (sanity-checks de unidades, etc.) sin `[[bibcode]]` → no requieren
  fuente, pero si **afirman un hecho del mundo** sí.
- Una afirmación con número/aseveración fáctica y **sin** `[[bibcode]]` ni marca `inferencia` →
  **flag "afirmación sin cita"** (hay que citarla o marcarla inferencia).

### 2. Fan-out: un subagente independiente por par
Para cada par, lanzar un subagente (tipo `Explore`) **en paralelo** (varios en un mismo mensaje).
Cada uno:
- Localiza el fulltext: `vault/raw/fulltext/**/<bibcode>.txt` (el bibcode puede vivir bajo cualquier
  slug/tema — usar glob). **Ojo:** los nombres tienen `&` y puntos → citarlos entre comillas simples
  al leer/grep.
- Lee **sólo ese archivo** (grounding-first; **prohibido** responder de memoria o de otro paper).
- Devuelve, para la afirmación dada:
  - `veredicto`: `soportada` | `parcial` | `no-soportada` | `contradice`. **Distinguir los dos modos
    de falla** (alineado al estándar de 4 categorías tipo CAQA): `no-soportada` = la fuente **calla**
    (no dice nada de eso → error de cita); `contradice` = la fuente **afirma lo contrario** (valor
    incompatible más allá del error, existencia negada, signo opuesto) — también exige cita textual,
    de lo que el paper **sí** dice.
  - `score`: 0–10 (qué tan literal/completo es el respaldo)
  - `evidencia`: **cita textual** del paper + **nº de línea** (contado como `grep -n` — ver la
    convención fija de arriba; nunca `splitlines()` de Python). **Sin cita textual ⇒ `no-soportada`**
    (regla dura: si no puede pegar la frase, no está respaldado). **La regla vale también para
    `parcial`**: exige cita textual que respalde **parte del contenido distintivo** de la
    afirmación (el sujeto/valor/mecanismo que la hace específica); si lo único que matchea es
    terreno común del tema (el fenómeno general, un término suelto, la mera cercanía temática)
    ⇒ `no-soportada`. Ablandar a `parcial` un claim genérico es el modo de falla típico del
    verificador — es exactamente lo que mide el benchmark.
  - `nota`: una línea de por qué (sobre todo en `parcial`/`no-soportada`: qué dice el paper en cambio).
    Si la afirmación es **multi-cláusula**, decir **qué cláusula** respalda el paper y cuáles no.
  - `completitud` (**sólo cuando el par sale de una transcripción** de tabla o lista de la fuente):
    ¿la tabla/lista del paper tiene **más filas/ítems** que los que la nota transcribe? Si sí,
    **listarlos** (con nº de línea). Es un **hallazgo aparte**, no un grado de soporte: no cambia el
    veredicto de la fila que sí está.

> **Claims multi-cláusula (espeja la regla del paso 1).** Una afirmación suele arrastrar varias
> cláusulas: una de encuadre sin cita, la atribuida a *esta* fuente, y a veces las de *otras*
> fuentes citadas al lado. El subagente juzga **la parte que se le atribuye a su paper** — que el
> archivo respalde una cláusula vecina (de otra fuente, o el encuadre genérico) **no** hace
> `soportada` ni `parcial` a la afirmación: es exactamente la mezcla "el dato de A atribuido a B"
> que este chequeo existe para atrapar. Sin esta instrucción el subagente juzga el conjunto y
> hedgea a `parcial`.

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
(soportada/parcial/no-soportada/contradice) + score 0–10 + cita textual con nº de línea (el que da
`grep -n` o la lectura directa del archivo; NO uses `splitlines()` de Python — los form feeds del
`.txt` corren la numeración) + nota. Para localizar: el `.txt` suele entrelazar dos columnas en la
misma línea física, así que si la oración completa no aparece con grep NO concluyas que falta —
acortá a un fragmento distintivo de 3–6 palabras (y reintentá partiendo por guión de corte);
PROHIBIDO normalizar espacios sobre el archivo entero Y también colapsar un hueco de 8+ espacios
dentro de una línea (ambos empalman columnas y fabrican adyacencias falsas); si normalizás, partí
antes la línea en ese hueco y tratá cada segmento por separado. Si no
encontrás respaldo textual, es no-soportada; `parcial` sólo si la cita textual respalda parte del
contenido distintivo de la afirmación — que el paper hable del mismo tema NO alcanza; si el paper
afirma lo CONTRARIO, es contradice (pegá la frase que lo contradice). No uses memoria ni otros
papers."*

**Addendum para transcripciones** (agregar al prompt cuando el par sale de una tabla o lista de la
fuente): *"Esta afirmación es una fila/ítem de una transcripción. La nota transcribe de este paper la
lista completa: «…». Decime APARTE del veredicto: ¿la tabla/lista del paper tiene MÁS filas/ítems que
ésos? Si sí, listá los que faltan con su nº de línea. Ojo con el layout: la tabla puede estar
entrelazada con otra en las mismas líneas físicas — contá las filas de LA tabla que corresponde."*

### 3. Umbral y agregación
- `score ≥ 7` → **soportada**
- `4 ≤ score ≤ 6` → **parcial** (revisar: matiz, rango distinto, atribución cruzada)
- `score < 4` → **no-soportada**
- **Regla del contenido distintivo:** un score 4–6 sólo vale como `parcial` si la evidencia citada
  toca lo que hace **específica** a la afirmación; coincidencia sólo temática ⇒ `no-soportada`
  (bajar el score, no promediarlo con la cercanía del tema).
- **`contradice`** manda sobre el score (no es un grado de soporte sino evidencia **en contra**, con
  cita textual de lo contradicho): se resuelve como corrección o disputa (paso 4), no como cita rota.

### 4. Resolver lo que falla (no dejar pasar)
Cada **parcial / no-soportada / contradice** se resuelve antes de cerrar:
- **Contradicción** (`contradice`) → decidir cuál de dos casos es. (a) **La nota está mal** →
  corregirla a lo que dice la fuente. (b) **Desacuerdo real entre fuentes** → es una **disputa**:
  si es un parámetro planetario de una ficha, taguearla en `planets[].disputes[]`
  (`field`/`ref`/`note`/`alt`; NEA sigue siendo el valor de verdad) y reflejarla en la prosa; si es
  un claim de concepto/query, citar **ambas** fuentes con el desacuerdo explícito (y ajustar el
  `bearing` del paper si aplica). Una contradicción detectada es un **hallazgo**, no un fracaso.
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
Chequeo afirmación↔fulltext (skill `verify-citations`). N pares; X soportadas / Y parciales / Z no-soportadas / W contradicen (resueltas).

| Afirmación (resumen) | Ref | Veredicto | Score | Evidencia |
|---|---|---|---|---|
| YZ CMi κ ≈ −2.6 | [[2018A&A...609A..12Z]] | soportada | 9 | "gradient of −2.6 Np−1 (±21%)" (L966) |
| activas −2.4/−2.6 | [[2025A&A...696A..27J]] | no-soportada→corregida | 2 | el paper da −2.65 a −3.70; el −2.6 es de Zechmeister |
| señal g confirmada | [[2016A&A...585A.134D]] | contradice→disputa | 1 | "is an artifact of... rotation" (L2101) → tagueada en disputes[] |

Inferencias declaradas (sin cita, por diseño): <listar>.

Omisiones en transcripciones: <tabla/lista, qué faltaba, cómo se resolvió> — o "ninguna".
```
Convertir fechas relativas a absolutas. Notación `$...$` en archivos `vault/wiki/` (texto plano en chat).

**La fecha del encabezado es portante** (#56): el lint la compara contra la fecha del último cambio
del archivo (git) y marca **verificación stale** cuando la nota se editó después — el caso de
ampliarla con `append-knowledge` o refrescarla. Un bloque sin fecha se marca igual: sin ella no hay
forma de saber si sigue vigente. Al re-verificar, re-fechar. Si la nota acumuló **varios** bloques
(pasadas sucesivas sobre secciones distintas — pasa en la práctica pese al "reemplazar" de arriba),
la vigencia la marca la fecha **más reciente**.

### 6. Lint + cierre
Correr `python scripts/lint.py` (0 en lo bloqueante; la **fuga de implementación** es WARN a revisar a
mano, y resolvé las **citas no verificables** del corpus que chequeás). Si el usuario pidió archivar/commitear, `git add` de los archivos **específicos**
y commit descriptivo; **preguntar antes de `push`**. Appendear a `vault/wiki/log.md` (resumen del chequeo:
cuántas soportadas/corregidas).

## Reporte (al chat)
Veredicto global honesto: total de pares, cuántas soportadas, **cada corrección hecha** (qué se
bajó/reasignó/marcó inferencia), **cada contradicción con su resolución** (corrección o disputa
tagueada) y **cada omisión** detectada en una transcripción (qué faltaba y si se completó o se
declaró el recorte). No maquillar: una afirmación que se estiró y se corrigió es un hallazgo del
chequeo, no un fracaso. Si algo quedó dudoso, decirlo.

## Límite honesto
El chequeo es **juicio de un LLM** leyendo la fuente — robusto (independiente por par, grounding-first,
cita textual obligatoria) pero **no una prueba**. Reduce drásticamente la mala atribución; no la elimina.
Su tasa de error se mide con el **modo benchmark** (abajo).

## Modo benchmark (auto-test del verificador — a pedido)
¿Cuánto confiar en ese "juicio de LLM"? Este modo le pone un número: **recall sobre errores
plantados** (estilo CiteAudit). Correr **a pedido** (no es paso de cierre), con la bóveda ya
poblada y citada.

1. `python scripts/bench_verify.py seed [--max N]` → arma `build/verify_bench/bench.json`:
   N pares (afirmación, `[[bibcode]]`) **reales** de queries/concepts + un par **falso por
   construcción** por cada uno (misma afirmación, bibcode rotado a otro paper del corpus —
   determinista, y nunca uno que esa afirmación cite de verdad).
2. **Fan-out A CIEGAS** — mismo protocolo del paso 2 normal, con una regla extra **dura**: cada
   subagente recibe SOLO (afirmación, ruta al fulltext). **NUNCA mostrarle `bench.json`, las
   etiquetas real/sembrada, ni decirle que es un benchmark** — sabría qué buscar y el número no
   mediría nada. El orquestador (vos) sí ve las etiquetas: sos el corrector del examen, no el
   examinado.
3. Volcar cada veredicto en el campo `verdict` de su par en el JSON
   (`soportada|parcial|no-soportada|contradice|no verificable por extracción`).
4. `python scripts/bench_verify.py score` → recall de sembradas + reales caídas →
   `outputs/verify-bench-<fecha>.md`.
5. **Reporte honesto al chat:** el recall; cada sembrada que PASÓ (revisar a mano — puede ser
   **soporte casual**: el otro paper de verdad dice lo mismo — antes de culpar al verificador); y
   cada real caída (flaky del verificador **o** error de grounding genuino de la nota: si es lo
   segundo, corregir la nota por el flujo normal de arriba).

**Regla #0:** nada del benchmark entra a `vault/` — pares sembrados y reportes viven en
`build/`/`outputs/` (scratch gitignored). Las citas falsas no son bibliografía.
