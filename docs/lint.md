# Lint — catálogo de categorías, severidades y cómo se cierra cada una

> Referencia completa del chequeo de salud (`python scripts/lint.py`). El **cuándo** correrlo y las
> reglas de comportamiento del gate viven en `CLAUDE.md` (sección *Lint*); acá está el catálogo
> categoría por categoría, con su severidad y su resolución. Cada regla lleva su `(#N)`/`(D-N)`: el
> issue público tiene el caso que la produjo y la medición.

## Severidades y doctrina del reporte

Tres severidades: **bloqueante** (exit ≠ 0), **WARN** (se revisa a mano, no frena) y **backlog**
(deuda declarada, se trabaja con el skill `maintain`). No existe "informativo" (AUD-207): lo que
distingue a una categoría declarada-y-resuelta no es el nivel sino que se reporta **aparte**, para
que la deuda real no quede mezclada con la que alguien ya cerró declarándola.

- **⛔ No evaluado** (un chequeo que **no pudo correr** — `objective.yaml` ilegible, sin `git` para
  medir la verificación stale): **cuenta para el exit y su categoría normal se suprime del
  reporte**. Un `(0)` que nadie midió se lee como veredicto, y ése es el falso limpio que el lint
  existe para no producir. Es hecho del **entorno**, no de la bóveda. Misma doctrina en `query_ads`:
  **rehúsa clasificar** con una lente ilegible en vez de degradar a `{}` en silencio.
- **Población declarada (INV-40):** cada categoría del reporte dice sobre qué corrió
  (`> sobre 412 notas de vault/wiki/`). Un `(0)` no distingue *«miré todo y no hay nada»* de *«no
  miré nada»*. Lo que no se puede declarar honestamente dice `⚠ población no declarada` — son
  exactamente dos, nombradas y con techo.

## El cierre: `--cierre` y `--cierre <slug>` (R-1, #121)

Un solo detector, dos severidades: sin flag es la **pasada periódica** (los pares vencidos y la
cobertura de verificación reportan como backlog); con `python scripts/lint.py --cierre` cuentan para
el exit — es el paso de cierre de toda operación que tocó la nota, donde un par sin verificar
significa que **no terminaste**. Los skills de cierre lo invocan con el flag; la pasada de higiene de
`maintain`, sin él.

⛔ **El flag toma el SUJETO: `python scripts/lint.py --cierre <slug>` (#121).** El razonamiento de
R-1 es sobre lo que **esa operación tocó**; aplicado a la bóveda entera, una deuda vieja en otro
sujeto deja el gate en rojo antes de empezar, y un gate que se audita a ojo deja de ser un gate. Con
el slug, el **alcance** son las notas del sujeto por las tres vías: su ficha/concepto (que se llama
por `concept`, no por el slug), los papers con artefacto bajo `raw/*/<slug>/`, y los
**retro-linkeados** (visibles sólo por `stars`/`thesis_links`/`methods` del frontmatter).
⚠ Dos recortes deliberados: **el reporte NO se acota** (la deuda ajena se lista entera, marcada
*«no frena»* — esconderla la volvería invisible) y **el alcance acota SÓLO la severidad de cierre**
(un bloqueante cuenta venga de donde venga; si no, `--cierre <slug>` sería más débil que un `lint`
pelado). Un slug inexistente **rehúsa** (exit 2): acotar a una entidad que no existe daría cero
hallazgos sobre una bóveda con deuda. Sin argumento, pasada de cierre global (deliberada).

## Bloqueantes

Deben quedar en **0**:

- **Wikilinks rotos.**
- **Frontmatter no parseable o con forma inválida**: nota que empieza con `---` y cuyo YAML no
  parsea, o un campo que el schema declara **lista** escrito como escalar / con elementos que no son
  mapas (`planets:`, `thesis_links:`). En los dos casos la nota **evade en silencio** los chequeos
  por elemento de su tipo.
- **Papers retractados** (flag `retracted`, lo estampa `scripts/check_retractions.py` vía Crossref;
  la cadena de ingest chequea sólo el slug con `--slug`, el barrido completo es la pasada periódica
  de `maintain`): una fuente retractada citada rompe la frontera dura.
- **Páginas huérfanas.** ⚠ El `index.md` **no** cuenta como link entrante (#249): desde que se
  estampa por verdad de disco lista todo, así que contarlo dejaba el detector en 0 permanente —
  **metadata derivada no es evidencia**. ⚠ La misma decisión vale para el **grafo de Obsidian**
  (#301): `vault/.obsidian/graph.json` viene con `search: -path:wiki/log.md -path:wiki/index.md`,
  porque si esas aristas no son evidencia para el lint tampoco son estructura para el grafo —
  medido, el 7 % de las aristas de una bóveda salía de esos dos archivos, y las 50 del índice
  significan «está en el top 50 por citas». Es un **default**, visible en el panel del grafo y
  reversible en dos clics; en una instancia ya creada entra por el próximo merge del template.
- **Contradicciones ground-truth↔ficha** — **qué planetas (no cuántos) y campo por campo**: planeta
  que la ficha lista y NEA no (típicamente una señal no confirmada escrita en `planets[]` en vez de
  `disputes` como `<letra>.existence`), planeta que NEA confirma y la ficha no lista, letra
  repetida, valor que difiere del ground-truth o que existe cuando NEA no lo tiene. Comparar
  *cuántos* dejaba pasar el caso peor: dos listas del mismo largo que no son los mismos planetas.
  **También bloquea el ground-truth que el espejo no puede leer** (JSON ilegible o no-objeto, `host`
  que no es mapa, `planets` que no es lista, `slug` interno que no matchea el archivo, ficha sin
  frontmatter legible): no es "la garantía no corrió" — el archivo que **es** la autoridad está
  roto, y callarlo deja la ficha sin vigilancia con el lint en verde.
- **Masa de ground-truth inconsistente con la m·sini implícita** (K/P/e/M\* — atrapa best-mass
  espurias de NEA).
- **`thesis_links` sin página destino** (tag que no matchea ninguna nota → no acumula en el
  roll-up; typo típico `shift-vs-shape` vs `shift_vs_shape`). Su hermano `methods` sin destino es
  backlog (ver abajo): la asimetría es real — un `thesis_links` nombra un concepto que
  `ingest-theme` crea en la misma operación que lo siembra.
- **`disputes` con la `ref` de una posición sin paper destino** (la disputa no es trazable),
  **`disputes` mal formadas** (#71: sin `field`, con menos de dos posiciones, con una posición que
  no dice quién la sostiene, o `source` fuera del vocabulario) y **`disputes` en el schema viejo**
  (`planets[].disputes[]` → migrar con `make_notes.py --migrate-disputes`).
- **Nota de paper con `topics:`** (campo pre-R-5 sin lector; el vigente es `facets:`) y **registro
  con `busqueda:`** (mapa, schema pre-D-28; hoy es `busquedas:`, lista).
- **`role` fuera del vocabulario** (`fundacional|aplicacion|arbitro`): un typo deja el rol mudo
  para el contraste cross-paper.
- **`pdf_source` / `fulltext_source` fuera de su vocabulario cerrado** (#296:
  `eprint|ads|publisher|web` y `pdftotext|ocr|web`; `null`/ausente = **desconocido**, que es
  legítimo y no significa «publicado»). No es cosmético: `pdf_source: eprint` es la **exención** que
  apaga el chequeo de cita textual, así que un valor fuera de vocabulario la apaga por el `else` en
  silencio y un `eprint` mal escrito la enciende y produce hallazgos que no lo son. Medido: 2 de 138
  notas llevaban **prosa** en el campo. Migrador: `python scripts/make_notes.py
  --migrate-source-fields` (pasa el valor a `null` y **mueve** la prosa a `pending_motivo` o
  `salvedades`).
- **Extracción que no dice desde qué sujeto se leyó** (#188: `## Extracción (LLM)` sin `vistas[]`)
  e **incoherencia `vistas[]` ↔ cuerpo** en los dos sentidos (vista declarada sin su
  `## Vista — <sujeto>`; sección sin declarar).
- **Juicio de triage en `build/<slug>/triage.json`** (pre-1.9.0: mientras exista, el triage
  re-propone lo descartado sin el motivo → `python scripts/triage.py <slug> --migrate`).
- **Extracciones en `build/*/extraccion/`** (pre-#311): ahí no se versionan ni viajan —medido,
  `git ls-files build/` = 0 sobre 33 extracciones que costaron ~4,9 M tokens de lectura de PDF— y
  una extracción no se regenera sin volver a pagar el paso más caro (#228) → `python
  scripts/make_notes.py --migrate-extracciones`.
- **Fila de tabla con más celdas que su encabezado (#227)**: GFM descarta el excedente, así que el
  contenido queda **invisible para el lector** mientras toda herramienta que parsea el archivo lo
  sigue viendo — y puede estar certificado como par verificado.
- **Registro que no se puede leer** (YAML roto o forma inválida — AUD-131/INV-139): **revierte la
  curación entera** (los `--drop` dejan de aplicarse, los `--drop-core` vuelven a ser core, el
  triage re-propone sin el motivo). `load_decisiones` **rehúsa operar** (doctrina de la lente
  ilegible, INV-80) y `save_registro` **rehúsa escribir** sobre un registro que no parsea — es el
  único artefacto no regenerable de la bóveda.
- **Veredicto que exige acción sin resolver** (#91) y las demás reglas del bloque de verificación —
  ver la sección *Verify* de `CLAUDE.md`: `no-soportada`/`contradice` pelados bloquean; la
  resolución se anota en la celda (`contradice→corregida`), nunca pisa el veredicto (#232).
- **Bloque de verificación con plantilla vieja** (sin las columnas de hash): no es "cero vencidos",
  es un bloque que nadie puede evaluar. **Bloqueante siempre**, con o sin `--cierre`.
- **Celda `Hash fuente` sin prefijo `txt:`/`pdf:`** (#117): *no consta* no es `txt`; se migra con
  `python scripts/make_notes.py --migrate-verif-archivo`. Excepción nombrada (#223): la fila
  `no verificable por extracción` no declara archivo, porque no hay ninguno.
- **`symbols_lost`/`fulltext_layout` presentes** (retirados en 1.71.0, #205 →
  `python scripts/make_notes.py --migrate-txt-fields`) y **`bearing` en nota de paper** (D-21 →
  `make_notes.py --migrate-bearing`).
- **Duplicado por identidad** (D-19: mismo `doi`/`arxiv_id` en dos notas) y **bibcode en
  `versions[]` con nota propia** (#229).
- **Marca `inferencia` sin premisas** (D-42: sin al menos un `[[bibcode]]` no hay nada que
  auditar). El énfasis markdown alrededor de la palabra no cambia nada (#276).
- **Fuente retractada citada en prosa sin la marca `⛔retractada`** (D-47): con la marca baja a
  informativa (visible, no destruida).

## WARN (se revisa a mano, no frena)

- **Fuga de implementación** (regla #0): heurística de alta señal (perilla/dial/`w_j`/`peso(`);
  cada hit se revisa y se saca del vault si es material de implementación. **No mira las
  `SECCIONES_ESTAMPADAS`** (#214): una traducción no es una afirmación de la bóveda, y el «nuestro
  código» del castellano es el *our code* **del paper**. La exención **no** alcanza a
  `## Vista — <sujeto>`: esa prosa la escribe el extractor y ahí una fuga sería real.
- **Áreas de `concepts/` fuera de `concept_areas`**: las áreas son abiertas, la lista es referencia
  para el typo-check, **nunca se bloquea** (`make_notes` avisa pero crea igual). Si el objetivo no
  declara `concept_areas`, el typo-check queda **apagado** y el lint lo dice (una línea): la lista
  no se infiere del disco, porque eso convertiría un typo ya cometido en "área declarada".
- **Objetivo sin instanciar** (`objective.name` sigue en el placeholder del template): la bóveda
  clasifica "core" con la regex del ejemplo — correr el skill `setup`.
- **PDF ↔ disco** (higiene): el campo `pdf` no refleja el PDF real (bajado y `null`, o puntero
  roto). Su hermano **cuerpo ↔ frontmatter**: el link `[📄 PDF]` de la cabecera —metadata derivada—
  debe existir sii `pdf` apunta a un PDF vigente. Las dos las cierra
  `python scripts/make_notes.py --restamp-pdf-links`, que desde #304 estampa **primero el campo**
  por verdad de disco (`stamp_pdf`, el gemelo de `stamp_fulltext`) y después el link: hasta
  entonces el lint imprimía la ruta exacta y **ningún comando la aplicaba** —`pdf:` se escribía sólo
  al crear el stub, así que el PDF que aparece después (rescate manual, cierre de un `pending`) no
  se linkeaba nunca; medido, 4 de 4—. "Cabecera fuera del contrato" pide normalizar la cabecera
  primero.
- **`.obsidian/` en la raíz del repo**: la bóveda se abrió mal (el grafo indexa el andamiaje);
  abrir `vault/` como vault y borrar ese directorio.
- **Alias de más** (declarado en `stars.yaml` y que resuelve a otro objeto).

## Precondiciones de `verify-citations`

Se listan para que el fan-out no corra sobre aire: **citas no verificables** (bibcode citado sin su
`.txt` en `vault/raw/fulltext/`), **fuentes pendientes** (`pending_source`: paywall/escaneo/mojibake,
derivada al usuario con su puntero) y **fulltext ilegible** (mojibake, escaneo sin capa de texto, o
marca de agua repetida por página — existe pero no sirve para grep ni verify; rescate: PDF sano,
OCR, o marcar `pending`).

## Backlog — verificación y garantías

- **Pares de verificación vencidos** (D-4/D-20), por **par** y no por archivo: *sin verificar*,
  *vencido por edición* (el ancla no coincide), *vencido por fuente* (el archivo leído cambió),
  *fila huérfana* (la afirmación se borró). Bloquean con `--cierre` (R-1).
- **Cobertura de verificación**: nota con citas **en prosa** (los `[[bibcode]]` de secciones
  estampadas no son citas) y sin bloque `## Verificación de citas` → nunca pasó por el skill. D-5
  dice que la nota **nace 100% verificada**, así que no es deuda vieja: es la operación que la tocó
  sin terminar (INV-79). Bloquea con `--cierre`.
- **Verificación stale**: la nota se editó después de la fecha de su bloque; red para notas con
  bloque y sin tabla parseable (las anclas son el mecanismo principal). Se mide por `git`; fuera de
  un repo cae a **⛔ No evaluado**, nunca a silencio (D-43). La rama "bloque sin fecha" corre
  siempre.
- **Celda truncada que no puede truncarse** (#226): sólo `Afirmación (extracto)` admite `…`;
  `Evidencia` (con su localizador al final, completo) y `Condición` no. Y la fila donde el cruce de
  localizadores **no se pudo evaluar** se reporta como *no evaluable*, no como ok.
- **Sub-sección del bloque con un conteo que su propia tabla desmiente** (#280): INV-81 mecanizó la
  cabecera y dejó las tres sub-secciones como prosa libre, y derivaron igual — medido, «las 20
  marcadas `acota`» sobre una tabla con **3**. Los fragmentos los genera
  `lib_blocks.verif_subsection_lines`, el mismo código que lee la tabla; *Omisiones* no lleva número
  (es juicio, no está en la tabla). Sólo se reporta la sub-sección **presente**: la ausente ya la
  reporta el chequeo de #232.
- **Cabecera publicada ≠ la que el estampador daría hoy** (#233): nadie cruzaba lo publicado con lo
  producible — una nota puede publicar dos de las tres fechas obligatorias y pasar el gate.
- **Nota de paper sin `## Abstract`** (#124/#277, **bloqueante**): es la única capa **auditable**
  del cuerpo —copia de catálogo, no síntesis— y `classify_offline` la lee para re-clasificar sin
  `build/` (D-49). Medido: **39 de 138** notas de una bóveda real ya no la tenían, con el lint en
  rc 0, porque el stub off-ADS nunca la escribía y nadie chequeaba. Se cierra con
  `python scripts/make_notes.py --restamp-abstracts` (escribe la SECCIÓN con `_(no disponible)_`;
  el contenido lo completa la próxima extracción, que no pisa un verbatim ya puesto).
- **Nota de paper sin `## Conclusiones`** (#124/#277, backlog): son lo que el paper afirma **sin
  lente**, o sea lo que hace barata una segunda vista cuando otro sujeto reclama el mismo paper.
  Tres exenciones, las tres estructurales: `unidad_cita: pagina` (un libro no tiene esa sección),
  sin PDF en disco o con la vista construida del abstract (#207: no las tiene por construcción), y
  la escotilla declarada **`sin_conclusiones: <motivo>`** — motivo obligatorio, como toda escotilla
  de curación acá; la declarada se reporta aparte, en «visible, no es deuda».
- **Nota de paper sin el aviso de capa LLM** (#247/#277, backlog): es la clase de nota con más
  contenido generado y era la única sin el aviso que nombra sus tres capas. La marca se busca en el
  **cuerpo** (un `pending_motivo` que la mencione daría falso negativo, AUD-135) y la repara
  `--restamp-headers`, que desde #277 también arregla la nota que tiene la línea del generador y
  perdió el blockquote — antes esa nota no se reparaba nunca y la categoría era incerrable.
- ⛔ **Cita textual que la EXTRACCIÓN desmiente** (#318/#321, `--cierre`): bloquea sólo con
  **evidencia positiva** de que la cita se movió o se completó — la frase está verbatim en la
  extracción de **otro** bibcode de la nota (atribución), o coincide un prefijo largo del mismo
  bibcode y **diverge la cola** (el patrón de #314, la cita completada al copiar). Sube a bloqueante
  con `--cierre <slug>`: una operación que altera una cita textual no puede cerrar en verde.
  ⛔ **El silencio de la extracción NO cuenta** (#321): es una transcripción **selectiva y lenteada**
  (#188) y el framework manda citar del PDF (#205), así que «no está en el JSON» no prueba
  fabricación — medido, entre los 20 hits de esa clase había citas legítimas, una usada por #315
  como ejemplo de cita **correcta**. Ese caso queda en backlog, junto con la fuente **sin extracción
  en disco** (no evaluable) y la cita **ambigua** (#316). Es la doctrina de siempre: **evidencia
  positiva bloquea, el silencio se declara** (D-43).
  ⚠ Y para clasificar un hit hay que volver a la **nota**, no al reporte: el extracto va truncado a
  70 caracteres (#226), así que decidir desde el reporte da un resultado falso.
- **Cita textual entre comillas que su fuente no contiene** (#220): «esta cadena está en este
  archivo» es un `grep`, no un LLM. ⛔ **Se decide contra la EXTRACCIÓN antes que contra el `.txt`**
  (#315/#317): la extracción es la transcripción hecha **leyendo el PDF**, así que una cita que está
  ahí y no en el `.txt` dice que el índice está degradado y **la nota está bien** (cae en la
  categoría de #288), mientras que una que no está en ninguno de los dos la **inventó el
  sintetizador**. Con el `.txt` como único juez la señal era **2 de 17** en un concepto y **0 de
  35** en otro — un detector que delega 54 confirmaciones manuales al PDF se deja de leer.
  ⛔ **Y la cita se prueba contra SU fuente, no contra todas las del bloque** (#316): el dueño es el
  `[[bibcode]]` adyacente (la convención `«…» [[bib]]`), y una **lista** de fuentes pegada a la cita
  (`[[A]], [[B]]`) no tiene dueño — ahí se prueba contra todas y **el mensaje declara que el
  hallazgo es más débil**. Medido: 12 de 12 hallazgos duros de un hub eran párrafos de contraste que
  atribuían bien en prosa, y «resolverlos» —reatribuir la cita al bibcode contra el que se testeó—
  habría **destruido la inferencia** que la nota declara. Tres estados: está → nada; no está en ninguna → hallazgo
  (no-verbatim o de otra fuente, se distingue a mano); **no evaluable** (sin `.txt` o
  `fulltext_source: ocr`) → categoría propia, porque contarlo en contra sería inventar deuda.
  ⛔ `pdf_source: eprint` **salió de la exención en #275**: cubría 45 de 49 papers de una ficha real
  y dejaba el chequeo con población **cero** (66 citas, 0 evaluadas), o sea un `(0)` que se lee
  verde. Desde #205 el `.txt` se deriva del mismo PDF eprint que el extractor abrió, y este chequeo
  no pregunta si el valor coincide con el publicado —ahí `eprint` sigue siendo salvedad, para
  `verify-citations`— sino si la cadena está en el archivo que se leyó. Y el comparador resuelve
  dos mañas del formato que producían falsos positivos en masa: el **guión de corte** (se borra de
  los dos lados) y el **de-entrelazado por canaleta** de un `.txt` a dos columnas — se busca por
  columna, nunca en el texto plano, porque ahí vive el empalme col.1→col.2 que nadie escribió (#46).
  La población declarada son **las citas evaluables**, no las notas.
  ⚠ **Un hallazgo de esta categoría NO se resuelve editando la nota contra el `.txt`** (#288):
  desde #205 el `.txt` es el **índice**, no la fuente, y en un paper a dos columnas empalma texto
  vecino en medio de la frase — una cita correcta aparece rota. Se confirma en el **PDF**; si el PDF
  la dice, el defecto es de la extracción y la cita **no se toca**. Cuando eso se puede decidir
  mecánicamente —números de línea metidos entre las palabras— el hallazgo cae en su propia
  categoría, *«la fuente SÍ la dice y el `.txt` la parte»*, que no pide corregir nada de la nota.
  Medido abriendo cinco hallazgos uno por uno: **cuatro eran el artefacto, uno era la nota**.
  ⛔ Y desde #267 se chequean también las citas del **frontmatter**: `disputes[].posiciones[].value`
  contra **su propia** `ref` —juntar los refs de la nota fabricaría una atribución cruzada— y
  `disputes[].note` contra cualquiera de las fuentes de esa disputa (misma regla que el cuerpo).
  Quedaban fuera de todo, porque `pairs_of` opera sobre el cuerpo: medido, 23 posiciones con `ref:`
  y 6 citas textuales sin mirar en una ficha real, y una corrección de la verificación que aterrizó
  sólo en la prosa y dejó el frontmatter —la capa que el contrato llama auditable— con el número
  viejo. Sólo cuenta si **ninguna** fuente del bloque la tiene; la cita elidida
  (`«A … B»`) se chequea por fragmentos; la **página** no se puede chequear así y se dice (media red
  declarada vale más que ninguna). Existe porque el eje *¿la fuente dice esto?* es **ortogonal** a
  *¿la cita es verbatim?*: seis citas no-verbatim volvieron `soportada`, correctamente.
- **`methods` sin página destino, resuelto también por `aliases`** (#245): el nombre canónico de
  un método es el **stem** de su nota y `aliases` es la tabla de sinónimos que el schema ya pide —
  y nadie la leía, así que `bisector span` y `bis` contaban como dos deudas donde hay una. Medido
  en una bóveda real: cierra 7 de 121. Chico, y del tipo correcto: lo que vacía ese backlog es que
  el **extractor vea la lista** antes de inventar una grafía, que es la otra mitad del arreglo (el
  prompt ahora la pega, con tope declarado y sin cerrar el vocabulario).
- **Markup crudo de catálogo en `## Abstract`** (#271): ADS devuelve `<SUB>`, `<ASTROBJ>`,
  `<A href>`, `<P />` y eso **es HTML válido** para cualquier renderer — medido, 249 ocurrencias en
  42 notas. `<ASTROBJ>HD 40307</ASTROBJ>` deja el nombre del objeto **invisible**, `<A href>` vuelve
  un link vivo una copia que se promete verbatim, y el resultado **depende del parser**. La limpieza
  corre en los tres backends al ingestar; lo ya publicado se cierra con
  `python scripts/make_notes.py --clean-catalog-markup`. ⚠ Ese backfill cambia bytes que leen el
  detector de duplicados (#216) y el diff de lente offline (D-49): re-medirlos después.
- **Indicador de actividad esperado sin nota de concepto** (#250, backlog): era el **único**
  campo-lista de `stars/` sin destino chequeado ni link —`thesis_links` bloquea, `methods` es
  backlog, y éste no tenía ninguno de los dos—, así que la ficha nombra cinco indicadores y el
  lector no puede llegar al concepto que explica ninguno. Se compara con `cfg.indicator_key`, que
  saca la **glosa final entre paréntesis**: el campo es prosa para un humano (`BIS (bisector de la
  CCF)`) y comparar crudo haría dangling al 100 % — un backlog que nace todo falso es uno que nadie
  vuelve a mirar. El puente visible es la sección estampada `## Indicadores de actividad esperados`.
- **Dos conceptos declaran el mismo alias** (#245, backlog): el roll-up resuelve al primero en
  orden alfabético y **lo dice**. Cuál concepto denota un nombre es curación: elegir en silencio
  decide por el usuario (regla de método 5).
- **La vista no contesta los ejes de su propia lente** (#254/#270, backlog): el prompt deriva sus
  ejes de `relevance.facets` desde #254 y nada comparaba lo **contestado** contra lo **declarado**
  en `vistas[].lente` — y el silencio de una vista sobre una faceta se lee como «se miró y no hay
  nada». Medido: 257 huecos sobre 79 vistas con lente declarada. Se reporta **nombrando los ejes**;
  no se reporta la vista sin `lente` (no hay contra qué comparar) ni la que no tiene `fecha` (la
  lectura no ocurrió). Del lado del origen, el cosechador estampa el eje contestado en vacío como
  `_(sin datos)_`: sin eso la deuda es permanente, porque «se preguntó y no hay nada» no se
  distingue de «nunca se preguntó».
- **`no_vista` se consulta en las cuatro redes** (#268): la escotilla que #256 hizo alcanzable
  decidía sobre **una** categoría, y las otras tres contaban la misma nota como deuda — medido, una
  nota con `no_vista` declarado y motivo seguía recibiendo *«conseguir el PDF»* sobre una tabla
  VizieR, que no es un paper y para la que ninguno de los cuatro valores de `pending` sirve. Hoy el
  sujeto declarado no entra al detector de *sin fuente en disco*, no cuenta en el recorte de lectura
  (`extraccion: todos los core` dejaba de cerrar por su culpa) y el roll-up lo publica con estado
  propio, `sin vista (declarado)`, en vez de `sin extraer`. ⚠ La forma **inválida** del campo sigue
  siendo bloqueante: el parseo temprano guarda el error y lo re-levanta donde se reporta.
- **La prosa afirma sobre la autoridad algo que su ground-truth desmiente** (#278, backlog): el
  espejo #70 vigila el **frontmatter** campo por campo y nunca el cuerpo. Medido: una ficha publica
  *«NEA publica las dos como `confirmed`»* sobre un planeta que NEA no lista — falso contra cuatro
  lugares del mismo archivo, con el lint en verde. Ninguna otra capa lo ve: `verify-citations` exime
  por contrato los valores de ground-truth y `find-contradictions` compara claim↔claim **entre
  fuentes**. Heurística deliberadamente angosta (la oración tiene que nombrar la autoridad, un verbo
  de listar y la letra **introducida** como planeta/señal), y se reporta **la frase** (#236). Punto
  ciego declarado: la letra escrita sin introductor y la oración de polaridad mixta.
- **Valor de segunda mano levantado sin la marca** (#103/#279, backlog): la extracción marca el
  valor que la fuente atribuye a **otro** trabajo —es el mecanismo de error nº 1 medido— y la
  síntesis lo tira. Medido: 4 casos en una ficha real, uno usado como **falsa corroboración
  independiente** («otras dos fuentes dan 7,15» era una sola medición ajena contada dos veces). Se
  mira por bloque citante (las secciones estampadas quedan fuera) y el hallazgo se apaga cuando el
  bloque ya nombra la segunda mano — sin esa escotilla la deuda sería inextinguible.
- **Cita textual de `log.md` que su fuente no dice** (#238): la bitácora es append-only y no podía
  corregirse; la entrada refutada se marca `⚠ corregido <fecha> → <entrada nueva>`, no se edita.
- **Entradas de `## Verificación de citas` sin las tres sub-secciones** o con cabecera derivada a
  mano (INV-81): los conteos los genera `lib_blocks.verif_summary`, el mismo código que lee la
  tabla.

## Backlog — notas y schema

- **`methods` sin página destino**: la versión no bloqueante de `thesis_links` (la nota destino la
  crea otra operación, `ingest-theme`).
- **Reclamo sin vista** (#188): un sujeto reclama el paper y nadie lo leyó desde ahí. Se cierra
  haciendo la vista o declarando `no_vista: [{sujeto, motivo}]`; el **declarado pasa a su propia
  categoría** (*«visible, no es deuda»*). Su hermana, la **vista sin `fecha`** (sembrada por el stub
  y nunca leída), es backlog propio. ⛔ La escotilla decide sobre la vista **sin fecha** (#256), que
  es donde vive el reclamo pendiente; `no_vista` **no borra** la entrada de `vistas[]` — declara por
  qué no se leyó.
- **La vista REFUTA un reclamo que sigue en el frontmatter** (#212): se leyó y el resultado dice
  que el reclamo es falso; la salida es el `--drop-core` que el cosechador imprime, no aflojar el
  add-only.
- **Extraído pero no sintetizado** (#75): paper con `methods` poblado cuyo bibcode no aparece
  citado en ninguna ficha ni concepto — la extracción nunca llegó a la síntesis, y es el único paso
  salteable sin otro rastro (su modo de falla es omisión; `verify-citations` no lo ve: valida cada
  afirmación, no la cobertura del conjunto). Se cierra sintetizando o declarando
  `no_sintetizado: <motivo>`. Dos recortes de población: la cita debe estar en nota de **entidad**
  (una `queries/` es respuesta puntual) y la nota no-core (`relevance: low`) no entra.
- **Vista fechada sin fuente en disco** (#217): la lectura ocurrió y ya no hay contra qué
  re-verificarla (los artefactos los borró `--drop-core`). Ninguna otra red lo ve: el ancla de
  fuente no se entera de un archivo que **desapareció**.
- **Corrección publicada** (`corrections`, #52 — erratum/corrigendum/EoC): el paper sigue citable;
  lo que hay que revisar son los valores extraídos (un corrigendum corrige justo ese número).
- **Salvedad en prosa que un script podría decidir, y salvedad sin la marca de #213** (#234):
  se reescribe estructurada (`SALVEDAD_TIPOS`). Mira **sólo** el bloque de las NO verificadas
  (#253): un detector no audita lo que la máquina escribe; el `**Salvedades:**` pelado (schema
  pre-#213) sí se mira.
- **Nota sin los campos del schema de su tipo** (INV-63, `lib_config.SCHEMA_NOTA` — la lista que
  escriben los writers de `make_notes`, no una copia de la prosa): se exige la **clave**, no el
  valor (`null` es el caso normal del espejo #70).
- **Duplicado sin `doi` ni `arxiv_id`** (#216): comparación por el arranque del `## Abstract`
  verbatim; **reporta, no fusiona** (la distinción «mismo trabajo en dos congresos» vs «dos etapas
  del mismo programa» es real). Salida: `--rename-paper` + `versions[]`, o `--drop-core` con motivo.
- **`fulltext: null` + `fulltext_source: <valor>`** (#230): afirma cómo se extrajo un texto que no
  existe. El par `pdf: null` + `pdf_source: <valor>` **no** es hallazgo (la procedencia de la
  lectura que ocurrió sobrevive al archivo).
- **Cabecera no estampable** (#69: sin la línea `> _Generado con Almagesto v…_`, ancla de todos los
  estampadores): las cirugías de cabecera devuelven `False` en silencio sobre ella. Se arregla con
  `python scripts/make_notes.py --restamp-headers` (lee la versión del `generator`, no la inventa).
- **Roll-up estampado desactualizado** (D-10): se reporta **nombrando los stems**; re-correr
  `python scripts/make_notes.py <slug>` (o `--theme`).
- **Hub que menciona un radio existente sin `[[wikilink]]`**: sin el link el radio no está en el
  grafo y el hub se lee como si el sub-aspecto no existiera.
- **Concepto/hipótesis sin ninguna cita** (cobertura): afirma sin fuente → no chequeable.
- **Alcance de hipótesis sin declarar o vencido** (D-34): sin el blockquote `> Alcance …` un
  veredicto negativo se lee como universal; los slugs son directorios de `raw/fulltext/`, así que el
  universo se re-cuenta y el lint marca la hipótesis que quedó corta.
- **Marcador sin cerrar** (`` ` ``/`$`) y **párrafo duplicado** en la misma nota (#227): se cuentan
  por **párrafo**, no por línea (las notas van hard-wrapped y contar por línea grita en falso). ⚠ Un
  marcador **escapado** (`\$`, ``\` ``) no abre ni cierra (#309): ése es el arreglo correcto de un
  literal —Obsidian lo renderiza— y contarlo dejaba al operador eligiendo entre un bug de
  renderizado, un backlog permanente o borrar el carácter de una transcripción verbatim, que el
  framework justamente pide. El hallazgo nombra **las dos líneas**: la del párrafo abierto y la del
  impar.
- **`## ` pegado a una fila de tabla, sin línea en blanco** (#260): GFM corta bien, pero
  Python-Markdown absorbe el encabezado como fila de la tabla de arriba y el `##` desaparece del
  outline. Backlog y no bloqueante a propósito: el daño depende del renderer. Sólo cuenta una
  **fila de tabla** como línea previa.
- **Faceta con token alfabético corto sin `\b`** (#236): matchea **dentro** de otra palabra
  (`expres` → *expressed*) y el falso positivo de una faceta no deja rastro — el paper entra, se
  baja y se sintetiza. El hallazgo nombra la palabra que lo disparó cuando hay corpus en `build/`.
- **`alcance`/`unidad_cita` de la nota ≠ el declarado en `sources[]`** (#312): los dos campos viajan
  de `themes.yaml` al stub **al crearlo** y ahí se congelan, así que ampliar el alcance de un libro
  deja la nota afirmando que ese material *no entra* mientras lo publica en su vista (medido: 2
  libros, 37 valores nuevos). El chequeo de completitud compara contra el de la **nota**, así que un
  alcance viejo no lo deja sin información: lo deja con información **falsa**. Se cierra con
  `python scripts/make_notes.py --restamp-alcance` (acá la autoridad es la **config**, al revés que
  `pdf:`/`fulltext:`, donde es el disco).
- **`STATUS.md` apilado como bitácora** (#302): el estado tiene **una** lista de próximos pasos y
  no se appendea — lo histórico y el handoff por corte de contexto van a `wiki/log.md`, que es
  append-only por contrato. Tres señales, las tres offline: más de una sección de *próximos pasos*
  (la que produce el daño: medido, cuatro listas y una contradiciendo un estado posterior del mismo
  archivo, en el primer archivo que un agente lee al iniciar sesión), más de
  `lint.STATUS_MAX_FECHADOS` encabezados fechados apilados, y el techo de tamaño
  `lint.STATUS_MAX_LINEAS`. Los números viven en `lint.py` y no en `tools/doc-size-ratchet.yaml`
  porque el STATUS es de la **instancia** (`merge=ours`): un ratchet del template no lo describiría.
- **La nota se apoya en el PREPRINT habiendo versión publicada** (#298): dos señales en una
  categoría. (a) `versions_disponible: <bibcode>` — el hallazgo del detector de versiones, que desde
  #298 se **estampa** para sobrevivir a la corrida (antes era una línea en stdout: correr la pasada
  y no actuar en el momento borraba el hallazgo, y la siguiente lo redescubría); se cierra con
  `--rename-paper` o declarándolo en `versions[]`. (b) `pdf_source: eprint` con bibcode **publicado**
  — no hay problema de identidad, así que `discover_versions` no la mira por contrato (D-19 es sobre
  identidad), y es justo donde el framework avisa que una discrepancia numérica es diferencia de
  versión **y** donde el `eprint` exime del chequeo de cita textual. Medido: 82 de 138 notas.
- **Artefacto reusado entre slugs sin chequear su versión, y pasada de red que nunca corrió**
  (#297): el reuso D-18 (copiar el PDF que ya estaba bajo otro slug) es correcto y se conserva, pero
  importa a un sujeto nuevo un archivo cuya **antigüedad nadie chequeó**; y la salida natural —«si
  hubiera versión nueva la búsqueda habría traído otro bibcode y D-19 los une»— es falsa justo en el
  caso frecuente, porque el DOI del preprint identifica el **depósito** y #216 garantiza que
  preprint y publicado no colisionen. Se detecta por verdad de disco (mismo bibcode con PDF bajo ≥2
  slugs) con `pdf_source: eprint` y sin `versions[]`, y el hallazgo trae el comando acotado
  (`sweep_external.py --bibcodes <b>`). En la misma categoría, *«`_red.yaml` no existe»*: una bóveda
  donde `sweep_external` nunca corrió no tiene **ninguna** de las seis caducidades chequeadas.
- **Alternativa de faceta con POBLACIÓN CERO, o duplicada** (#291): la dirección **simétrica** de
  #236 y la más silenciosa — una alternativa muerta no se ve nunca: la faceta compila, el corte da
  un número plausible, el registro guarda la lente como vigente y el término no participa,
  indistinguible de *«ese término no aparece en la literatura»*. Medido: `non-?gaussianity matrix`
  (un `|` perdido) exigía una frase que **0** archivos tienen mientras 29 tenían `non-gaussianity`,
  o sea que el término central del tema nunca clasificó a nadie. Se corre por alternativa contra el
  texto que lee la LENTE (título + abstract + keywords de las notas del sujeto), sobre las facetas
  de `themes.yaml` **y** las de `relevance.facets`. ⚠ La partición es por alternación de **nivel 0**
  (`cfg.facet_alternatives`): partir con `split('|')` corta adentro de los grupos y deduplicar sobre
  eso **rompe la lente** (medido: −1 paper del core). Con 0 notas sale *no evaluable*, nunca «todas
  muertas».
- **Lente desincronizada** (D-49): la `lente` del registro ya no es la vigente de `objective.yaml`.
  El diff corre sólo cuando difieren y es **offline** (título + abstract + `keywords`); nombra los
  stems que entrarían y saldrían. Alcance declarado: evalúa la mitad textual; un cambio que sólo
  mueve `noise_doctypes` se declara *no evaluable*; sin `lente` en el registro: *no evaluado*, nunca
  cero.

## Backlog — curación, registro y búsqueda

- **Triage pendiente** (#55): candidatos del chaining sin juzgar → `python scripts/triage.py <slug>`
  (pertinente → `extra_core`; ruido → `--drop … --reason`). Sin `build/` local no inventa un cero:
  cae al registro versionado y reporta el snapshot **con su fecha**.
- **Decisión con forma inválida** (entrada de `decisiones` que no es un mapa): `load_decisiones` la
  descarta, y sin el aviso el triage re-propone lo descartado sin el motivo (#51).
- **Alias que SIMBAD conoce y `stars.yaml` no declara** (#82): un alias que falta es un paper que
  nunca aparece, y degrada los tres mecanismos de recall (query directa, `--sweep`, rescate por
  glifo). Se persisten en `_simbad_aliases` del ground-truth; **persistir no es adoptar** (cuáles
  entran es curación y se versiona). El **considerado y rechazado** se declara en
  `aliases_descartados: [{id, motivo}]` (#252, forma dura D-58) y tiene **categoría propia**
  (*«visible, no es deuda»*): era el único carril de curación sin escotilla del NO, y el mensaje del
  hallazgo instruía descartar mientras lo reportaba como deuda para siempre.
- **Barrido full-text sin rastro** (#88): `query_ads.py <slug> --sweep` appendea a `barridos: []`
  **también cuando no encontró nada** (la red se tendió y volvió vacía ≠ no se corrió). El barrido
  **resta las decisiones ya persistidas** (#251), igual que el chaining, y computa
  `n_nuevos`/`n_ya_estaban` contra los barridos previos (D-28); el descarte va por
  `triage.py <slug> --drop … --reason` — el juicio es sobre el par `(paper, sujeto)`, no sobre el
  mecanismo que lo propuso.
- **Corpus truncado** (`truncated` en `build/<slug>/ads.json`): re-ingestar con `--rows` mayor. Lo
  que falta es **el medio**, no la cola: al truncar corre una segunda pasada ordenada por fecha
  (#79, `truncated.recent`). Ídem el **rescate por glifo incompleto** (`truncated_glyph`).
- **Recorte de lectura sin declarar** (core sin extraer y sin `extraccion:` en el registro): se
  cierra con `python scripts/triage.py <slug> --extraccion todos|subconjunto`.
- **Capas colgadas de un slug que ya no existe** (INV-19, tras un `entity.py delete|rename` a
  medias).

## Backlog — campos incompletos

No bloquean; el conteo vigente es el de los sitios que pueblan `incomplete` en `lint.py`, no una
lista en prosa (#147). Hoy: `P_rot` sin documentar en la prosa (el frontmatter nulo no es hallazgo,
#70); `activity_indicators_expected` vacío; planeta del frontmatter no discutido en la prosa; paper
core sin `methods` (sin extraer); paper extraído sin `role`; `unidad_cita` de documento largo sin
`alcance` (#80); paper relevante sin fuente en disco (#90: es core y no hay qué leer); ficha sin su
`raw/ground_truth/<slug>.json` (el barrido del espejo #70 lo maneja el JSON: sin archivo, nadie
vigila la ficha — es "la garantía no corrió acá", no "hay una violación"); un
`raw/fulltext/<slug>/<clave>.txt` sin su nota en `papers/` (#108: extracción pagada que no alcanza
ningún roll-up — pasa al angostar la `query` de un tema; se cierra re-corriendo
`make_notes.py --theme <slug>` o borrando el artefacto colgado); y su hermano simétrico, un
`raw/ground_truth/<slug>.json` sin su `stars/<slug>.md` (renombre a medias o ficha borrada sin
limpiar).

Revisar además a mano: claims stale y conceptos referidos sin página. Si faltan datos, abrir
queries para imputar (web/ADS).
