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
  `ingest-theme` crea en la misma operación que lo siembra. ⛔ **El destino se busca por clave
  normalizada y por `aliases`, el mismo predicado que el hermano backlog (#243/#245/#348):** con el
  string crudo, `thesis_links: [PCA]` contra `concepts/methods/pca.md` en disco salía colgante —un
  falso positivo **bloqueante**— mientras `make_notes.theme_membership` decía que es el mismo
  concepto y lo acumulaba en el roll-up.
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
  legítimo y no significa «publicado»). No es cosmético: el campo **decide lecturas** —`eprint` dice
  que las citas son contra el preprint— y un valor fuera de vocabulario cae por el `else` de todo
  `== "eprint"` en silencio (#363: ese `else` eximía además del chequeo de cita textual hasta
  1.111.0, y la doc lo siguió afirmando 59 versiones menores). Medido: 2 de 138
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
- **El par nota ↔ hermano de auditoría** (#344/INV-148) — tres categorías, las tres bloqueantes.
  Desde 1.165.0 la **tabla** del bloque vive en `<nota>.verif.md` (hermano, mismo directorio) y en la
  nota quedan la línea de cabecera, las tres sub-secciones y un puntero:
  - **Tabla DENTRO de la nota** (schema anterior a 1.165.0): detector, nunca lector tolerante —
    leerla de los dos lados dejaría dos casas para una tabla. Se cierra con
    `python scripts/make_notes.py --migrate-verif-sidecar` (mueve la tabla **verbatim**: no
    re-renderiza, así que anclas y hashes quedan intactos; idempotente).
  - **Nota con cabecera de verificación y SIN su hermano**: la nota publica una línea que afirma N
    pares y la tabla que la respalda no está en ningún lado — no es «cero vencidos», es una
    afirmación que nadie puede evaluar (D-43).
  - **Hermano `.verif.md` HUÉRFANO** (su nota ya no existe): un rastro de auditoría que no se puede
    cerrar contra nada. Lo llevan solos `entity.py delete|rename` (octava capa, INV-19) y
    `--rename-paper`; aparece cuando algo movió la nota a mano.
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
- **`pdf_source` de editor (`publisher|ads|web`) con `eprint_version`** (#383): contradicción
  interna del frontmatter —el PDF es del editor y la nota dice que leyó un preprint—, y manda a
  re-verificar contra el documento equivocado. Nace del REEMPLAZO de un PDF por otro de distinta
  procedencia, que #230 no cubría (cubre el borrado); hoy `stamp_pdf` lo detecta por `pdf_sha`.
- **Driver `merge=ours` REGISTRADO en un clon que tiene `origin`** (#390, invierte #99):
  `merge=ours` es una regla por **path** y git no puede condicionarla por remoto, así que el mismo
  driver que protege contra `upstream` **descarta en silencio** lo que traiga `origin` — la otra
  máquina del mismo usuario, sin conflicto y sin aviso. Arreglo:
  `git config --unset merge.ours.driver`, y traer el template con
  `git -c merge.ours.driver=true merge upstream/main`, que conserva la protección sin dejarla
  puesta contra `origin`. ⚠ Sin `origin` el chequeo **no aplica**: ahí el driver es pura
  protección. Se reporta **una vez** —es una decisión del clon, no de cada patrón— nombrando
  cuántos patrones abarca.

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
- **Cabecera del bloque desincronizada de la tabla de su hermano** (#344/INV-148, **R-1**: backlog
  en la pasada periódica, **bloquea con `--cierre`**). INV-81 cruzando archivos: los conteos los da
  `lib_blocks.verif_summary`, el mismo código que lee la tabla, y desde #344 la tabla vive en OTRO
  archivo — la cabecera es lo único del rastro que viaja con la nota, así que si deriva el
  consumidor no tiene con qué notarlo. Se exige la **línea canónica entera** (hasta 1.164.0 se
  comparaba sólo el fragmento «N pares», con la tabla ahí al lado para desmentirla), comparada con
  el markdown normalizado. Bloquea con `--cierre` porque la cabecera la escribe `verify-citations`,
  que es paso de cierre.
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
  hallazgo es más débil**. ⛔ **La adyacencia se EXIGE (#325):** entre la cita y su link sólo puede
  haber puntuación, markup de cierre y el paréntesis del localizador (`»* (p. 4) [[bib]]`); antes de
  la cita se admite la cláusula que la introduce (`[[bib]] dice: «…»`) pero no cruzar otra cita, un
  fin de línea, un punto y seguido o un borde de celda; y **en una fila de tabla manda la columna
  *Fuente*** (la celda que contiene sólo un `[[bibcode]]`). Hasta 1.135.0 la convención estaba
  documentada y no exigida —tomaba el primer link posterior a **cualquier** distancia: 131, 247, 436
  y 657 caracteres medidos—, así que una **mención** («…atribuyendo ese paso a [[X]]») le ganaba a la
  fuente declarada: **6 de 12 hallazgos bloqueantes** de una bóveda real eran notas que atribuyen
  bien. Con prosa en el medio no hay dueño → ambigüedad → no bloquea. Medido: 12 de 12 hallazgos duros de un hub eran párrafos de contraste que
  atribuían bien en prosa, y «resolverlos» —reatribuir la cita al bibcode contra el que se testeó—
  habría **destruido la inferencia** que la nota declara. Tres estados: está → nada; no está en ninguna → hallazgo
  (no-verbatim o de otra fuente, se distingue a mano); **no evaluable** (sin `.txt` o
  `fulltext_source: ocr`) → categoría propia, porque contarlo en contra sería inventar deuda.
  ⛔ **La matemática PARTE la cita, no se borra (#326):** `$…$` se eliminaba y las dos mitades se
  **pegaban**, produciendo una cadena que no existe en ningún `.txt` — el mismo argumento por el que
  la elipsis parte, aplicado al marcador equivocado. Con `CLAUDE.md` mandando `$...$` en la bóveda,
  la población afectada era toda cita que toque una fórmula (**412 de 3036** medidas), y ninguna
  podía pasar el primer paso del veredicto: el detector mandaba a corregir lo ya correcto y no había
  corrección que lo apagara.
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
- **Las DOS lecturas del mismo PDF no coinciden** (#333, backlog): la extracción aprueba la cita
  —o sea que el detector de arriba dice `✅`— y el `.txt` de **esa misma fuente** trae un prefijo
  largo de la cita y **sigue distinto**. ⛔ La discrepancia **no** es «PDF vs `.txt`»: el PDF es la
  fuente y siempre tiene razón; lo que difiere es **quién lo leyó** —`pdftotext`, determinista, y un
  LLM—, así que lo único cierto es *andá a mirar esta página*. Existe porque una cita alterada que
  nace **en la extracción** es invisible para `contrast --validar` por construcción: su juez **es**
  la extracción (#315/#317), y hasta 1.161.0 el `.txt` sólo podía absolver.
  Lo que vuelve admisible la acusación es una asimetría medida: **cuando el `.txt` falla la cadena
  está AUSENTE, no distinta** (matemática, corte de columnas, salto de línea). De ahí las tres
  guardas, y la del medio es la que compró la re-medición: la divergencia arranca en un **borde de
  palabra** —`pdftotext` rompe PALABRAS (ligadura `ﬁ`, `mix tures`, empalme) y un LLM que transcribe
  mal cambia PALABRAS—, no toca `$…$` ni un borde de celda, y el `.txt` sigue al menos
  `CITA_COLA_MIN` caracteres (una lectura que se corta calla, no contradice). Medido sobre una
  bóveda real el 2026-08-31, con el cortador de #332/#336 ya arreglado: de 25 citas aprobadas con un
  solo testigo, **7 candidatas → 3 acusaciones, las 3 verdaderas** (los 4 descartes eran artefactos
  del `.txt`, cazados por el borde de palabra). **Backlog, nunca bloqueante**: el `.txt` es un índice
  degradado y desde #323 este gate frena operaciones. ⛔ **La salida es la marca, no la corrección**
  (#341): cuál de las dos lecturas gana lo decide quien abra la página — medido en contra, el
  `log.md` de esa bóveda registra una corrección previa que recortó la nota **hacia** la cadena
  inventada porque el `.txt` partido parecía decirla. Por eso `contrast --validar` **emite**
  `⚠verificar en el PDF (<las dos colas>, <fecha>)` lista para pegar y **no escribe** en `vault/`;
  una vez pegada, la levanta la categoría de abajo. Desde 1.162.0 el string vive en
  `lib_config.VERIFICAR_PDF_MARK`: con dos copias, una herramienta podía proponer una marca que
  ningún detector levanta — deuda escrita que se lee como agendada y no lo está.
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
  ⛔ **Se cruza el VALOR, no el paper (#350).** El aviso preguntaba *«¿este paper tiene ALGUNA
  segunda mano?»*, que sobre un survey o un handbook —llenos de atribuciones a terceros por
  construcción— se contesta que sí siempre: medido, **398 de 462 pares, el 86 %**, la forma de #198
  con 6 de cada 7 avisos no accionables. Hoy se pide que el bloque y el valor marcado compartan un
  **literal** —una cantidad afirmada o un fragmento entrecomillado—, y el hallazgo lo **nombra**
  (`la línea toma 34.6 …`), que es lo que lo vuelve triage en vez de relectura.
  ⚠ Tres recortes, todos medidos: no cuentan los números que no son valores (la referencia `[27]`,
  el tag `(6.18)`, el localizador `Sect. 2.3`, el año, la designación de catálogo `Gl 725`); una
  sola cifra de menos de tres dígitos significativos tampoco (colisiona: *«4,5 años»* de baseline
  contra *«4,5 Gyr»* de edad), salvo que la fila comparta **dos**; y el bloque que ya nombra al
  tercero —en prosa, o citando **su** paper— no dispara. ⛔ El decimal castellano se lee **dentro de
  la matemática** (`$P = 4{,}3115$`): sin deshacer las llaves no cruza ni un valor de una ficha
  real. Población: el **par** (bloque citante, bibcode), no la nota — con 8 de denominador, 398
  hallazgos no se pueden leer (INV-40 cumplido en la letra y no en el espíritu).
- **Cita textual de `log.md` que su fuente no dice** (#238): la bitácora es append-only y no podía
  corregirse; la entrada refutada se marca `⚠ corregido <fecha> → <entrada nueva>`, no se edita.
- **Entradas de `## Verificación de citas` sin las tres sub-secciones** o con cabecera derivada a
  mano (INV-81): los conteos los genera `lib_blocks.verif_summary`, el mismo código que lee la
  tabla.

## Backlog — notas y schema

- **`methods` sin página destino**: la versión no bloqueante de `thesis_links` (la nota destino la
  crea otra operación, `ingest-theme`).
- **Reclamo sin vista** (#188): un sujeto reclama el paper y nadie lo leyó desde ahí. Un
  `methods` cuenta como reclamo **sólo si ese nombre denota un tema declarado**, y eso se evalúa por
  clave normalizada (#348): con el string crudo, `methods: [PCA]` no era el tema `pca` y la categoría
  quedaba vacía según la grafía que eligió el extractor. Se cierra
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
- **Wikilink en el blockquote de ALCANCE** (#368): el alcance de `## Huecos` o de una hipótesis
  (D-34) es contabilidad del corpus —qué temas, cuántos papers, a qué fecha— y un `[[bibcode]]` ahí
  entra al fan-out como par que **ningún PDF puede respaldar**: medido, 3 links → 2 `no-soportada`
  bloqueantes y dos lecturas de PDF completas para descubrir que la pregunta no tenía sentido. La
  regla es *no pongas un link ahí*, no *no mires ahí*: se reemplaza por el nombre del paper.
- **Cabecera DESPLAZADA o AUSENTE** (#380, dentro de *PDF ↔ disco / cuerpo*): son **tres** estados y
  el detector modelaba dos. *Desplazada* = la línea existe fuera del contrato (típicamente adentro
  de `## Abstract`, por el orden invertido de #378) → **mover**, con `--fix-header-order` si la
  corrió un backfill. *Ausente* = ya se perdió (la borró el cosechador, #379) → **reconstruir**, del
  historial de git; `--restamp-pdf-links` **no** puede, porque necesita la cabecera que falta.
  ⚠ El reporte ya **no** está condicionado a que falte el link `[📄 PDF]`: `has_link` mira el texto
  entero, así que una cabecera desplazada lo lleva igual y la conjunción apagaba el detector —
  medido, 7 reportadas de 10, y las 3 mudas eran los tres libros del corpus.
- **Roll-up estampado desactualizado** (D-10): se reporta **nombrando los stems** y el comando lo
  arma `cfg.make_notes_cmd` (INV-141), así que sale con `--theme` cuando corresponde.
  ⛔ **Cubre los DOS tipos de sujeto desde #338**: #300 llevó las dos garantías de D-10 al
  estampador de un concepto y el detector se había quedado en `stars/` —medido, 2 de 3 sujetos de
  una bóveda real son temas, y un paper que reclama una estrella y un tema con las dos tablas
  vacías se reportaba 1 de 2—. Un tema estampa su roll-up bajo **uno** de los dos encabezados
  (`## Papers` estilo ficha → `papers_universe`, o `## Papers que tocan este tema (auto)` →
  `concept_rollup_rows`, D-24) y **cada uno se compara contra SU universo**: exigir el ausente
  inventaría un hueco en la nota que eligió el otro. La nota que no trae **ninguno** de los dos es
  su propio hallazgo — no puede recibir la cirugía nunca, y eso sólo lo decía un `print` de
  `make_notes` al pasar. ⚠ El corte es `cfg.section_span`: `## Papers` es **prefijo** de
  `## Papers que tocan este tema (auto)` (la trampa de #176).
- **Hub que menciona un radio existente sin `[[wikilink]]`**: sin el link el radio no está en el
  grafo y el hub se lee como si el sub-aspecto no existiera.
- **Concepto/hipótesis sin ninguna cita** (cobertura): afirma sin fuente → no chequeable.
- **Alcance de hipótesis sin declarar o vencido** (D-34): sin el blockquote `> Alcance …` un
  veredicto negativo se lee como universal; los slugs son directorios de `raw/fulltext/`, así que el
  universo se re-cuenta y el lint marca la hipótesis que quedó corta.
- **Hueco sin ALCANCE declarado** (#342): un hueco es una afirmación **negativa** —*«nadie da un
  criterio para elegir $n$»*, *«ICASSO no aparece en ninguna fuente»*— y **por construcción no tiene
  `[[bibcode]]` que la respalde**, así que no la mira ninguna otra capa: `verify-citations` va
  claim↔su propia fuente y `find-contradictions` claim↔claim, y las dos parten de una cita. Medido
  el 2026-08-31: **2 huecos falsos en `ica` y 4 en `ica-ruido`**, los seis afirmando que la bóveda
  no puede responder algo que **sí** responde, y los seis cazados **de casualidad** (verificadores
  que contradijeron la afirmación desde su propia fuente sin habérselo propuesto). El origen no fue
  descuido: los seis salieron de **agregar los campos `hueco` de las extracciones**, que son **por
  lente** —lo que *esa* fuente no da— y agregarlos los convierte en una afirmación universal.
  ⛔ La red es la misma forma que D-34: el `## Huecos` con bullets declara
  `> Alcance <fecha> · temas: [...] / estrellas: [...] · N papers` **dentro de la sección**, y el
  lint lo cruza contra el disco (sin declarar · sin slugs · sin `· N papers` · slug fantasma ·
  quedó corto). El blockquote de **nivel de nota** de una hipótesis no cuenta: declara el alcance
  del *veredicto*, que es otra afirmación. La escalera es una sola implementación
  (`lint.scope_state`) para los dos consumidores. Población: las notas de `stars/` y `concepts/`
  con `## Huecos` **escrito** — la sección con la glosa del stub y sin un solo bullet no afirma
  nada y no entra. ⛔ **Lo que esto NO hace** es verificar la negativa: preguntarle a cada fuente
  del alcance *«¿tu paper dice algo de X?»* es un fan-out por hueco, y queda aparte. Ésta es la red
  barata: declarar el alcance y chequearlo contra el disco.
- **Marcador sin cerrar** (`` ` ``/`$`) y **párrafo duplicado** en la misma nota (#227): se cuentan
  por **párrafo**, no por línea (las notas van hard-wrapped y contar por línea grita en falso). ⚠ Un
  marcador **escapado** (`\$`, ``\` ``) no abre ni cierra (#309): ése es el arreglo correcto de un
  literal —Obsidian lo renderiza— y contarlo dejaba al operador eligiendo entre un bug de
  renderizado, un backlog permanente o borrar el carácter de una transcripción verbatim, que el
  framework justamente pide. El hallazgo nombra **las dos líneas**: la del párrafo abierto y la del
  impar. ⛔ El duplicado se cuenta **dentro de su vista** (#349): con varias vistas (#239) cada una
  estampa su propia línea estructural —el eje que la lente preguntó y la fuente calló, la salvedad
  chequeada— y son idénticas **por construcción** (medido: 7 hallazgos, los 7 falsos). Cada
  `## Vista — <sujeto>` y cada `### Lente — <énfasis>` es un ámbito; el resto de la nota sigue
  siendo uno solo, que es lo que mantiene vivo el caso de #227. Se cortó por ámbito y **no** eximiendo
  prefijos: esa lista habría que mantenerla, y el corpus medido ya traía una tercera forma
  estampada (`- PREPRINT: …`) que no estaba en ella.
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
  versión. Medido: 82 de 138 notas. ⚠ Y **no** hay agujero de verificación asociado: la exención
  del chequeo de cita textual salió en 1.111.0 (#275/#363).
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
- **Recorte de lectura sin declarar** (core sin extraer y sin `extraccion:` en el registro; el
  sujeto del paper se indexa y se busca por clave normalizada, #348): se
  cierra con `python scripts/triage.py <slug> --extraccion todos|subconjunto`.
  ⛔ **Cubre los DOS tipos de sujeto desde #346**, por el mismo defecto de forma que #338 y con el
  mismo remedio: recorría estrellas y temas y le pedía `slug` al **mapa** de los dos, pero en
  `themes.yaml` el slug es la **clave** del YAML, así que para todo tema salía `None` y el sujeto
  se salteaba en silencio (medido sobre una bóveda real: la categoría pasa de `(0)` a `(1)`, un
  tema con **26** core sin extraer y sin criterio declarado). El barrido es hoy **una sola
  implementación**, `cfg.all_subjects()`, compartida con el detector de roll-up.
- **Tema de MÉTODO sin `search_fq`** (#351): un tema que declara `facet:` propia es, por D-26, un
  tema de método; si no declara `search_fq` hereda el del objetivo —`database:astronomy` en una
  bóveda astro—, que acota el universo **server-side, antes de traer nada**, y ninguna `facet:`
  puede recuperar lo que ese `fq` dejó afuera. Medido en `ica`: **cero** papers entran por la
  puerta fundacional con el fq heredado (teniendo `fundacional_min_citas: 2000` declarado) y dos
  sin él, Comon 1994 incluido — el tema se ingestó, se sintetizó y se **cerró** sin su canon.
  Backlog y no bloqueante (heredar puede ser correcto); se cierra declarando `search_fq:` en la
  entrada del tema, **aunque sea `null`**. El aviso simétrico sale en
  `query_ads.py <slug> --theme --probe`, que es donde el corte se decide antes de pagar
  descargas (#208).
- **Cascada de descubrimiento (paso 0b) sin correr, vacía o coja** (#361, `cascada_sin_correr`):
  el paso 0b —`discover.py --theme <slug>`, los tres backends— es **manual** por diseño (#95/#209)
  y el registro versionado guarda si corrió (`descubrimientos`), pero nadie lo leía. Medido: un
  tema cerrado entero —12 papers, 107 pares verificados, `lint --cierre` en 0— sin haber corrido la
  cascada, y ningún gate lo dijo. Sólo para el tema **off-ADS o mixto** (`source:` declarado y
  distinto de `ads`), que es donde el skill prescribe el paso. **Tres estados** (D-43), porque
  piden acciones distintas: *nunca corrió* (correrla) · *corrió y no trajo nada* (revisar
  `query`/`aliases`/`topic`) · *corrió con backends caídos*, nombrando cuál (volver a correr —
  un 0 por caída no es «no tiene nada del tema»). Las corridas se **unen**: un backend caído en una
  y sano en otra no es deuda, y las filas `NO CORRIÓ: …` son decisiones declaradas, no caídas.
  Desde #361 la cobertura del registro lleva también la fila **`anclaje`**, con los mismos tres
  estados: antes el anclaje moría con traceback y no dejaba rastro. Backlog.
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
el comando que `cfg.make_notes_cmd` arma para ese slug, o borrando el artefacto colgado — #338: el
remedio traía `--theme` hardcodeado sobre un directorio que puede ser una **estrella**, la imagen
especular de #334); su **gemelo PDF** (#230/#338: mismo defecto y desde #205 la mitad cara de la
cadena, y hasta 1.146.0 emitía prosa en vez de un comando ejecutable); y su hermano simétrico, un
`raw/ground_truth/<slug>.json` sin su `stars/<slug>.md` (renombre a medias o ficha borrada sin
limpiar).

Revisar además a mano: claims stale y conceptos referidos sin página. Si faltan datos, abrir
queries para imputar (web/ADS).
