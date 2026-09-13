# Validación en la instancia — qué revisar antes de cerrar cada issue

Para el agente **validador** de una bóveda poblada (`Almagesto-Tesis`): el template implementa y
pushea; la instancia mergea (`docs/migracion-instancia.md` §0), **valida contra su contenido real**,
y **cierra el issue en GitHub con la medición** — o lo devuelve con lo que falló. Acá va, por
issue, qué entró, cómo validarlo y qué cuenta como «devolver».

⛔ **Sin medición no se cierra.** Un issue nació de un caso medido en la instancia; se cierra cuando
ese caso, corrido de nuevo, hace lo que el fix promete. Lo que no se pudo correr se declara.

Acumulativo por tanda; la sección de la guía de migración que corresponde va nombrada.

---

## T4 (resto) · v1.189.0–v1.190.0 — guía §2g

### #361 · anclaje con traceback + `descubrimientos` que nadie leía

**Qué entró.** (a) `_preview_theme` envuelve `anchored_records` como `cascade` a cada backend: fila
`anclaje` en la cobertura (impresa y registrada), y la línea de cierre sale aunque OpenAlex esté
en 429. (b) Categoría backlog `cascada_sin_correr` (población: temas) con tres estados; sólo temas
`source:` ≠ `ads`.

**Validar.**
```bash
python scripts/lint.py | grep -A4 "cascada de descubrimiento"
python scripts/discover.py --theme icasso      # con OpenAlex sin presupuesto: debe terminar en
                                               # «→ todo esto son CANDIDATOS», con «anclaje FALLÓ»
python -c "import yaml;print(yaml.safe_load(open('vault/config/registro/icasso.yaml'))['descubrimientos'][-1]['cobertura'])"
```
Esperado: lint con **2** hallazgos (`icasso`: openalex FALLÓ; `rv-doppler`: nunca corrió), el
comando sin traceback, y la última entrada del registro con la clave `anclaje`.

**Devolver si:** el lint reporta `ica` o `ica-ruido` (sus cascadas corrieron con los tres
backends), o si `discover --theme` sigue muriendo con traceback con OpenAlex caído.

**Al cerrar, dejar:** los dos slugs reportados y el estado de cada uno; la cobertura de la
corrida nueva de `icasso`.

### #358 · el carril ADS no consultaba el resolver OA; Europe PMC

**Qué entró.** `fetch_pdf` recorre `discover.iter_pdf_candidates` (OpenAlex → Unpaywall → Europe
PMC → arXiv por título exacto) al agotar los `esource`; prueba **todos**; el residuo lleva
`estado` (`sin-copia-libre` | `bloqueado`) y `copias_libres`; `pdf_source` sólo cuando el
candidato lo sabe. `download_pdf`/`_curl_pdf` ya validaban `%PDF` (test que lo fija).

**Validar.**
```bash
python scripts/fetch_pdf.py icasso
python scripts/extract_fulltext.py icasso
python scripts/lint.py
```
Esperado: bajados **2** (`2022PLoSO..1770556W` por OpenAlex/PLoS; `2019Bioin..35.4307C` con la
URL de OUP marcada «no entregó PDF» y luego Europe PMC), `pdf:` y `fulltext:` estampados en las
dos notas, `missing_pdf.json` sin entradas (o con `estado` en cada una). Los PDF con `%PDF` al
inicio (`head -c4`). Cerrar el ciclo del tema: extracción de los dos con la lente de `icasso`.

**Devolver si:** alguno de los dos sigue «sin conseguir» con copia libre (mirar `copias_libres`
del residuo y decir cuál URL falló y qué devolvió), o si un `.pdf` escrito no arranca con `%PDF`.

**Al cerrar, dejar:** bibcode → depósito que lo entregó y tamaño; `pdf_source` de cada uno.

⚠ Ninguno de los dos issues toca contenido: no hay prosa que re-verificar. Tras `fetch_pdf`,
los dos papers cambian de estado en el roll-up de `icasso` (`sin extraer` → lo que sigue).

---

## T5 + T6 · v1.191.0–v1.197.0 — guía §2h

### #354 · el `fq` siempre visible con procedencia

**Qué entró.** `query_ads.fq_line`: probe, corrida (tema y estrella) y `--sweep` imprimen
`fq: <valor|null — no acota> (del objetivo | del tema | heredado del objetivo | …)`, antes del conteo.

**Validar.** `python scripts/query_ads.py --probe 'title:"Icasso"' --rows 15` → primera línea
`fq: database:astronomy (del objetivo)` y el 0 se lee con su filtro; `python scripts/query_ads.py
icasso --theme --probe` → `fq: null — no acota (del tema)`. **Devolver si** algún modo con conteo
no lo imprime. **Al cerrar:** pegar las dos líneas.

### #360 · ejes heredados: aviso en probe, backlog del lint, `vista_ejes_faltantes` no evaluable

**Validar.** `python scripts/lint.py | grep -A6 "sin \`ejes:\`"` → un hallazgo por tema con
`facet:` y sin `ejes:`; `vista_ejes_faltantes` dice *no evaluable* para sus vistas. Declarar
`ejes: []` en uno y confirmar que ese tema desaparece de las dos. **Devolver si** un tema sin
`facet:` aparece, o si con `ejes:` declarado sigue apareciendo. **Al cerrar:** N temas reportados y
cuáles quedaron con ejes declarados.

### #384 · corpus declarado con bibcode ADS

**Validar.** Con `rv-doppler` en `source: ads` + `query: null` + `extra_core:`:
`python scripts/ingest_theme.py rv-doppler` → línea «corpus declarado — N bibcode(s) … sub-cadena
`--extra-only`», sin el aviso «tema mixto SIN fuentes», cadena idempotente (0 bajados). Y un tema
`source: ads` sin `query` ni `extra_core` rehúsa nombrando las dos vías. **Devolver si** la cadena
corre `query_ads --theme` sin `--extra-only` o si el aviso de #211 sigue saliendo.

### #382 · `unidad_cita`/`alcance` en `extra_core`

**Validar.** Declarar en la entrada de la tesis `2021PhDT.........6D` `unidad_cita: pagina` y
`alcance: "<lo que entró>"`; `python scripts/make_notes.py --restamp-alcance` → la nota lleva los
dos campos; `python scripts/extraction_prompt.py rv-doppler 2021PhDT.........6D --theme` → el
prompt manda empezar por el índice, pega el alcance, `conclusiones` vacío, cita por página.
`unidad_cita: hoja` o `pagina` sin `alcance` → la cadena rehúsa con el mensaje. **Devolver si** el
prompt no ramifica o el lint no ve los campos en la nota.

### #357 · el contador de la puerta 2

**Validar.** `python scripts/query_ads.py icasso --theme --probe --rows 300` → línea
`puerta 2 (\`fundacional_min_citas: N\`): citation_count de ADS en esta query = min–max sobre K
papers` + el aviso «el contador es el de ADS» (el `fq` es `null`). **Devolver si** falta con el
umbral declarado. **Al cerrar:** pegar el rango; la decisión OpenAlex sigue abierta
(`docs/decisiones-abiertas.md`), no la cierra este issue.

### #353 · lo declarado contra el DOI

**Validar.** Los tres `check_sources.py` de la guía + `lint.py`. Esperado: `fuente_metadata_falsa`
= **1** (`2006VanDerBaan`, Crossref: Vrabie), `fuente_metadata_dudosa` ≈ 24 (3 título · 1 año ±1 ·
6 no-evaluable · 14 primera página). Corregir la entrada de `2006VanDerBaan` (o su DOI), re-correr
`check_sources.py ica` → la bloqueante en 0. Confirmar que `themes.yaml` no cambió por el script.
**Devolver si** una fuente con DOI correcto y autor correcto sale `autor`, o si el script escribe
`themes.yaml`. **Al cerrar:** los conteos por veredicto y qué decidiste con las 14 del carril PDF.
⚠ El cruce reveló además que el `2011Yang` del issue ya fue migrado; el **T5b** (promover una fuente a `extra_core` en un comando)
sigue pendiente en el template y no se valida acá.

### #377 / #376 (T6)

#377 es doc: leer la regla nueva y cerrar. #376: (3) hecho (el test del grafo lee sólo `search`
y nombra el remedio); **(2) se deja a propósito** — el test de existencia de `vault/config/*.yaml`
que la doc nombra pasa en toda instancia que tenga los archivos que la doc promete, y una instancia
sin `themes.yaml` es una instancia a la que le falta un archivo del schema, no un falso positivo.
Comentarlo así en el issue y cerrarlo, o devolverlo si `Almagesto-Tesis` lo ve rojo.

---

## T5b · v1.198.0 — guía §2i

### #353 (comentario 2) · `triage --promote-source`

**Qué entró.** `triage.py <slug> --promote-source <key> --bibcode <bib>`: `rename_paper(fix_key=True)`
+ metadata de catálogo desde ADS (`fetch_bibcodes`) + chequeo de curación antes/después + snippet
de `extra_core`. No edita `themes.yaml`.

**Validar.** Elegir un item de `sources:` con bibcode ADS real (los ApJ de Waldmann), correr el
comando, pegar el `extra_core`, sacar el item, `ingest_theme.py <slug>`, `lint.py`. Esperado: la
nota nueva conserva `no_vista`/`no_sintetizado`/`salvedades`/`vistas`/`methods` byte a byte (diff
del frontmatter contra `git show HEAD:`), `versions` vacío, `first_author`/`citation_count` de ADS,
`## Abstract` verbatim si el stub tenía el placeholder, los wikilinks reescritos, `lint` sin
huérfanas ni wikilinks rotos por el renombre. **Devolver si** se pierde una clave curada sin que
el comando lo grite (rc 1 + «PERDIÓ curación»), o si escribe `themes.yaml`. **Al cerrar:** qué
fuente se promovió y el diff de frontmatter.

---

## Seguimiento de #353 · v1.199.0 — guía §2j

Los seis hallazgos del cierre de #353, en un commit. **Validar:** `check_sources.py ica` de nuevo
→ los cuatro Hyvärinen en `no-evaluable (primera página ilegible …)`, `2007GomezHerrero` (o su
clave actual) en `ok`; `make_notes.py --restamp-sources-meta` → 0 notas (ya corregidas a mano) o
las que difieran de `sources:`; `triage.py ica --promote-source <key> --bibcode <bib>` en
cualquier item → el bloque `extra_core:` impreso pasa por `yaml.safe_load`; `--rename-paper …
--fix-key` → el resumen dice «sin alias». **Devolver si** un apellido compuesto correcto sigue
saliendo `autor` por Crossref, o si el carril PDF sigue acusando sobre una primera página
mojibake. Sin issue nuevo: los seis quedaron en el comentario de cierre de #353.

---

## #392 · v1.200.0 — guía §2k

Regla transversal en `CLAUDE.md` + cláusula con comando en cuatro skills. **Validar:** leer las
cinco piezas y, en la próxima declaración de una fuente, que el paso lleve a la primera página y a
la planilla del usuario antes de escribir. Cierra el issue si la regla cubre los cuatro casos
medidos; **devolver** si falta un skill donde se escriba identidad a mano. Los puntos 3 y 4 del
issue (carril mecánico contra `.bib`/`.csv`; `url:` contra el `<title>`) no entran en esta versión:
decidí si los querés como issue aparte.

---

## #392 (3 y 4) · v1.201.0 — guía §2l

**Validar:** poner un `.bib` (aunque sea de una entrada) en la carpeta de un `pdf:` declarado y
correr `check_sources.py <slug>` → esa fuente sale `[bib]`; una fuente `url:` con snapshot sale
`[web]`. Un `.bib` que contradiga el autor declarado → `fuente_metadata_falsa` (bloquea); el carril
web nunca bloquea. **Devolver si** el parser no lee tu `.bib` real (mandame la entrada que falla).

---

## #430 · v1.250.0 — guía §2m

La prosa del triage de las tres sub-secciones se perdía en silencio al re-escribir el bloque.
**Validar:** `write_verif_sidecar.py --restamp-section --todo --dry-run` primero (declara población
y nombra lo que rehúsa), después sin `--dry-run`; `git diff vault/wiki` → las 2 líneas con
fragmento duplicado quedan con **uno solo** y su prosa intacta, y las sub-secciones adornadas
conservan su texto; segunda corrida = 0 cambios (red 6); `lint.py` rc 0 y sin *«no publica el
conteo»* sobre sub-secciones correctas. **Devolver si** alguna nota pierde prosa, si el comando
rehúsa sobre una línea que a ojo está bien formada, o si el lint sigue reportando la sub-sección en
negrita. **Al cerrar:** cuántas secciones se re-estamparon y sobre cuántas notas con hermano.

---

## #427 · v1.252.0 — guía §2n

**Validar:** `lint.py` → la categoría *Condición sin clasificar* nombra las celdas con la clase
DOS veces (esperado ~41 sobre las notas verificadas, 7 `acota`); correr
`--migrate-condition-prefix` nota por nota → el lint baja a 0 en esa mitad y
`cond_acota_resueltas` de la cabecera **sube** en las 7 que ya estaban resueltas y no se contaban;
segunda corrida = 0 migradas (idempotente); `--resolver <ancla>=<dónde>` sobre un `acota` abierto →
la cabecera de *Condiciones perdidas* cambia el `(N resueltas)` y la fecha del bloque **no se
mueve**. **Devolver si** una celda migrada pierde texto, o si `--resolver` rehúsa sobre un `acota`
legítimo. **Al cerrar:** cuántas celdas se migraron por nota y el delta de `cond_acota_resueltas`.

## #428 · v1.252.0 — guía §2ñ

**Validar:** sobre `build/gj_581/verif/` (las tres rondas que motivaron el issue), un solo comando
con `--from a1 --from a2 --from a3` → el hermano sale igual que el que se armó a mano; y sobre una
ronda con anclas muertas, `--descartar-anclas-muertas` escribe los vivos **nombrando** los
descartados. Sin el flag el mensaje tiene que ofrecer los dos caminos. **Devolver si** el encadenado
no reproduce el resultado serial, o si el mensaje de rehúse no dice cómo salir. **Al cerrar:**
cuántos pares se recuperaron sin re-pagar fan-out.
## #431 · v1.253.0 — guía §2o

**Validar:** `python scripts/lint.py` y comparar la categoría *Verificación stale* contra la
corrida anterior — los cuatro falsos medidos (`ica`, `icasso`, `hd_40307` y la query de blanqueo,
cuya única edición fue dentro de `## Verificación de citas`) tienen que **desaparecer**, y los que
queden tienen que decir qué bloque cambió. Segundo chequeo, barato: editar a mano una sub-sección
del bloque de una nota cualquiera (sin commitear) y re-correr el lint → esa nota **no** aparece;
tocarle un párrafo con cita → aparece, con el extracto del párrafo. **Devolver si** desaparece un
hallazgo cuya edición SÍ tocó la prosa (sub-disparo: es la dirección prohibida), o si una nota
sana empieza a salir con la salvedad «no se pudo aislar la prosa».

## #429 · v1.254.0 — guía §2o

La instancia tiene **dos estrellas cerradas** (`gj_581`, `hd_40307`), que es el corpus donde se midió
el defecto. **Validar:** `python scripts/lint.py` ANTES → *Matriz método × estrella desactualizada*
con 1 hallazgo (la matriz sigue con el texto de bóveda vacía y sin la sección estampada);
`python scripts/make_notes.py --restamp-matrix` → una tabla con **dos columnas** (`[[gj_581]]`,
`[[hd_40307]]`), una fila por `method_key` de los `methods` de sus papers, la línea `> Alcance …`
con el N de papers con `methods` poblado por estrella, y la cola colapsada en un `<details>` que
declara cuántos métodos quedaron adentro; correrlo **dos veces** → la segunda no cambia un byte
(red 6); `lint.py` DESPUÉS → la categoría en 0 y **sin wikilinks rotos nuevos** (el método sin nota
destino tiene que salir como código, no como `[[link]]`). **Devolver si** aparece una fila cuyo
método viene de `methods_applied.literature` y no de la extracción (sería el hueco falso de vuelta),
si un `—` sale sin la línea de alcance que lo acota, o si un concepto que era huérfano deja de
reportarse (la matriz estampada **no** cuenta como link entrante, #249). **Al cerrar:** cuántas filas
y columnas quedaron, y cuántos métodos salieron como código por no tener nota destino.

## #432 · v1.255.0 — sin guía de migración (no cambia ningún artefacto)

Latente al medirlo: la plantilla de #344 escribe las tres sub-secciones del bloque como **párrafos**,
así que hoy la población es cero y no hay nada que migrar. **Validar:** `python scripts/lint.py` tiene
que dar **exactamente el mismo reporte** que antes del merge (si cambia algún conteo, la bóveda tenía
un `###` dentro de una sección estampada y esos pares eran fantasmas: mirar cuáles desaparecieron).
Chequeo positivo, barato: agregarle a una nota un `### Con condición \`acota\`` dentro de
`## Verificación de citas` con un `[[bibcode]]` adentro y correr `python scripts/verify_fanout.py
<nota> --dry-run` (o el `--cierre` del lint) → ese par **no** puede aparecer. **Devolver si** un par
de prosa real deja de contarse (sub-disparo: la dirección prohibida) o si el lint pierde hallazgos de
fuga de implementación en una sección propia titulada con `###`.

## #433 · v1.256.0 — el cruce de segunda mano tiene salida

La instancia es donde se midió: **66 hallazgos leídos uno por uno con un agente por nota**
(`rv-doppler` 21, `hd_40307` 15, `gj_581` 13, `harps-drs` 10, `ica-ruido` 6, `ica` 1), 20 reales, 6
ya atribuidos y 40 coincidencias numéricas, y **48 seguían listados** después de arreglar los 20.
**Validar:** `python scripts/lint.py` ANTES y DESPUÉS del merge, sin tocar ninguna nota → la
categoría *«Valor de SEGUNDA MANO levantado sin la marca»* tiene que **bajar sola** (son los ~8 cuyo
dueño no es «apellido + año»: `compilación PASTEL`, el design review de la ESO, `Dean, Kowalski y
Pell`), y ninguno de los 20 reales ya arreglados puede volver. Después, firmar **una** coincidencia
con el snippet que imprime el hallazgo y volver a correr → sale de la deuda y aparece en *«REVISADO y
rechazado»* con su motivo. **Devolver si** un cruce real desaparece (el crédito sería demasiado
laxo), si una declaración pegada del reporte cae en *«no corresponde a ningún hallazgo»* (el matcheo
por prefijo no estaría funcionando), o si la categoría no baja nada (el crédito nuevo no alcanzaría a
las formas medidas). **Al cerrar:** cuántos bajaron por crédito y cuántos hubo que firmar — ése es el
número que dice si la mitad automática valió.

## #434 · v1.256.0 — la `acota` que comparte ancla con una `contextualiza`

Medido en `harps-drs` al cerrar la ronda ciega del 2026-09-10: 158 filas, 20 `acota`, **5
irresolubles sobre 4 anclas**. **Validar:** en esas 5 (el bloque «Post-procesado en vez de
re-reducción: dónde se engancha» cita `2023A&A...678A...2C` y `2021A&A...653A..43C`),
`write_verif_sidecar.py <nota> --resolver <ancla>=<dónde>` ahora tiene que **resolver la `acota` y
dejar la `contextualiza` intacta**; `lb.verif_counts` sube `cond_acota_resueltas` en 1 por cada una.
Correrlo dos veces → no-op (red 6). **Devolver si** toca la fila de la `contextualiza`, si rehúsa
sobre un ancla con una sola `acota`, o si con dos `acota` no nombra los bibcodes para desambiguar.
**Al cerrar:** cuántas de las 5 quedaron resueltas y si el conteo de la cabecera dejó de mentir.

## #435 · v1.256.0 — la propuesta firmada deja de estar pendiente

Medido acá: **62 propuestas**, 60 permanentes. El caso reproducible es `2012ApJS..200...15A` con
`refuta: ["GJ 581"]`, firmado con `triage.py gj_581 --drop-core … --reason …` y **seguía listado**.
**Validar:** `python scripts/proposals.py` → esa propuesta sale de lo pendiente y aparece como *«ya
FIRMADA»* con el motivo del registro; las 59 de `alcance` siguen pendientes (su firma es texto libre)
pero ahora cada fila trae *«alcance vigente: …»*, que tiene que coincidir con `themes.yaml`.
**Devolver si** una refutación **sin** firmar deja de listarse, si el alcance vigente que imprime no
es el de la config, o si una categoría no declara su estado de firma. **Al cerrar:** cuántas de las
62 quedaron pendientes de verdad.

## #436 · v1.256.0 — el reemplazo de PDF

Medido acá reemplazando **11 preprints** con un script de scratch: 76 pares vencidos en 6 notas.
**Validar** con **uno** de los 70 de prioridad alta y con `--dry-run` primero: el alcance impreso
tiene que coincidir con las filas del hermano que citan ese bibcode, y el dry-run no puede tocar un
byte (red 6 con `find vault -name '*.md' | md5sum`). Después, la corrida real: el PDF queda
reemplazado **en todos los slugs** donde vivía, `pdf_source`/`pdf_sha` coherentes, `eprint_version`
en `null`, **un solo** `.txt` re-extraído, y `lint.py` reporta la extracción en
`extraccion_despaginada` sin que ninguna otra categoría se mueva. **Devolver si** acepta un PDF con
la marca de arXiv como `--source publisher`, si re-extrae el slug entero (mirá cuántos `.txt`
cambiaron con `git status`), si deja una copia vieja en otro slug, o si el alcance impreso no
coincide con lo que después reporta el lint como vencido. **Al cerrar:** cuántos slugs tocó, cuántos
pares quedaron por re-verificar, y si el número del alcance fue exacto.

## #437 · v1.257.0 — la firma y el aviso de páginas

Medido acá: el caso de `2014Sci...345..440R` (7 páginas contra 33, la ficha citando §S1.1) y las 11
notas reemplazadas sin rastro. **Validar:** `python scripts/replace_pdf.py 2014Sci...345..440R
<la copia de Science Express> --source publisher --reason "…" --dry-run` → tiene que imprimir
`⚠ PÁGINAS: … 26 página(s) MENOS … (7 contra 33)` y **no** rehusar; sin `--dry-run` sobre un
reemplazo real → la nota gana `pdf_reemplazo` con `paginas`, `sha_anterior`/`sha` y el `--reason`,
y un segundo reemplazo del mismo paper **apila** una entrada (no pisa). `python scripts/lint.py` →
`extraccion_despaginada` marca *«NO lo declara en `pdf_reemplazo`»* en las 11 viejas y **no** en la
nueva. **Devolver si** el aviso falta o rehúsa, si `pdf_reemplazo` pisa la historia, o si el conteo
de páginas discrepa con `pdfinfo` a mano. **Al cerrar:** cuántas de las 11 quedaron firmadas a
mano y con qué `sha_anterior` (si se perdió, `?`: no se inventa).
**Y el ítem 3 (v1.257.1):** sobre los 23 pares de copyedición que salieron por #389, volver a poner
la redacción publicada en UNA y correr `contrast.py <slug> --validar`: si el `.txt` re-extraído la
tiene verbatim → rc 0 sin hallazgo; si no la encuentra → rc 0 con la marca `⚠verificar en el PDF`
lista para pegar y *«PDF REEMPLAZADO»* en el motivo; y una cita deliberadamente mal contra el PDF
nuevo (arranque igual, cola inventada) → rc 1 nombrando *«`.txt` NUEVO»*. **Devolver si** una cita
correcta contra el PDF nuevo sigue bloqueando, o si una alterada contra el PDF nuevo pasa.

## #440 · v1.258.1 — el backfill de los 15 reemplazos a mano

Medido acá: 15 notas con `pdf_source: publisher` y nada más, `extraccion_despaginada` = `(0)`.
**Validar:** `replace_pdf.py <bibcode> --backfill --source publisher --reason "…" --dry-run` sobre
uno → no cambia un byte; sin `--dry-run` → la nota gana `pdf_reemplazo` con `sha_anterior: "?"`,
`sha` del PDF en disco y `paginas: "? → N"`, y **cada** extracción del bibcode gana `_paginacion`;
repetirlo → rehúsa (*«ya declara `pdf_reemplazo`»*). Sobre los 15: `lint.py` →
`extraccion_despaginada` = **15** (y sin *«NO lo declara»*), y sobre uno de los 23 pares de
copyedición `contrast --validar` deja de acusar con la lectura del preprint (o marca, o bloquea
contra el `.txt` nuevo — #437 ítem 3). **Devolver si** el backfill toca un PDF o un `.txt`, si
inventa un `sha_anterior`, o si después del backfill la categoría sigue en 0. **Al cerrar:**
cuántos de los 15 quedaron con `sha_anterior` real y cuántos con `?`.

## #430 (3ª vuelta) y #435 (devuelto) · v1.258.2

**#430:** el repro del comentario —`lb.subsection_split("Inferencias declaradas — 3 marcas en el
cuerpo: \`(inferencia de [[b1]], [[b2]])\`.", "Inferencias declaradas")`— tiene que devolver la prosa
**con** el backtick de apertura. Después, sobre `ica-ruido.md` (con la línea 665 reparada a mano):
`write_verif_sidecar.py vault/wiki/concepts/methods/ica-ruido.md --restamp-section --dry-run` y la
corrida real → la línea 665 queda byte a byte; segunda corrida → 0 (red 6). **Devolver si** vuelve a
perder el backtick o cualquier otro adorno de apertura de la prosa.

**#435:** `cfg.subject_slug('GJ 581')` → `'gj_581'`; `python scripts/proposals.py` → la refutación
de `2012ApJS..200...15A` sale de lo pendiente y aparece como *«ya FIRMADA»* con el motivo del
registro; el conteo de permanentes baja de 60. **Devolver si** sigue en pendiente, o si una estrella
con alias sólo resuelve por el nombre canónico.

## #441 y #442 · v1.259.0

**#441:** sobre uno de los 15 ya firmados a mano (`9d3083d`), des-firmar en un worktree descartable y
correr `replace_pdf.py <bibcode> --backfill --source publisher --reason "…"` sin `--sha-anterior` →
el `sha_anterior` firmado tiene que coincidir con el que recuperaste con tu script (prefijo del `oid`
del pointer padre). Sobre un PDF agregado ya publicado (sin modificación en git) → rehúsa con *«NO
hubo reemplazo»*. **Devolver si** firma `?` teniendo historia, o si firma un sha que no es el del
padre del último commit que modificó el archivo.

**#442:** `python scripts/lint.py` → las categorías *Ground-truth que cambió* y *apoya en el
PREPRINT* declaran en su línea `> sobre …` cuántos artefactos llevan la marca y cuántos no se
miran; con los dos JSON de ground-truth sin `_cambios` tiene que decir *«sobre 0 … — los 2 sin la
marca NO se miran»*. **Devolver si** la población sigue contando los sin marca como mirados.

## #443 y #444 · v1.259.1

**#443:** repetir el barrido: `make_notes.py --migrate-verif-archivo` sobre la bóveda ya migrada →
**0 filas** y hash de `vault/**` sin moverse; `lint.py` sin el bloqueante #117. **Devolver si**
cambia un byte o si una fila con hash sin prefijo deja de migrarse (la celda del hash tiene que
cambiar, y sólo ésa).

**#444:** `make_notes.py --restamp-headers` ya corrió; `lint.py` → *Verificación stale* sin las 4
notas de paper (`2001LevineDomany`, `2008A&A...479..277B`, `2012embc.conf..101A`,
`2013IJBHI..17..629H`); tocar un párrafo con cita en una de ellas → vuelve a aparecer nombrando el
bloque. **Devolver si** alguna sigue «stale» por la cabecera o si un cambio real deja de verse.

**#444 (devuelto) · v1.259.2:** mismo chequeo que arriba — las 4 notas salen de *Verificación stale*
sin tocar nada; la cabecera se reconoce por el aviso `⚠ Capa LLM` aunque la versión vieja no tenga
la línea del generador. **Devolver si** alguna sigue con *«fuera de los bloques citables»*.


## #446 · v1.260.0

Sobre `2017PhRvE..96d2114K` (o cualquiera de las 9): `python -c "import sys;sys.path.insert(0,'scripts');
import make_notes as mn;print(mn.pdf_source_info('ica-ruido','2017PhRvE..96d2114K'))"` → `('publisher',
None)` con `build/ica-ruido/pdf_source.json` diciendo `eprint`. Después `extract_fulltext.py ica-ruido
--bibcode 2017PhRvE..96d2114K` (sin `--force`) → la nota queda `publisher` y **ninguna otra nota del
slug cambia** (hash de `vault/wiki/papers/` antes/después, red 6). Repetir un reemplazo real con
`replace_pdf.py` → las notas ya firmadas del mismo slug no se mueven. **Devolver si** una firmada
vuelve a `eprint`, o si una nota con `pdf_sha` distinto del PDF en disco toma la firma como válida.

## #448 · v1.260.1

Sobre un bibcode con PDF en un slug y `.txt` en dos (`2015Voss`: PDF en `ica`, `.txt` en `ica` e
`ica-ruido`): `replace_pdf.py 2015Voss <pdf> --source publisher --reason "…" --dry-run` → el reporte
dice *«copiados a 1 slug(s) … ica-ruido»*; la corrida real → `sha` igual en los dos `.txt` y `lint.py`
sin el bloqueante D-18/D-20. **Devolver si** el `.txt` del slug sin PDF queda distinto, o si el
reporte cuenta el copiado como re-extraído.

## #445 · v1.260.2

`lint.py` sobre `harps-drs` con la línea en blanco puesta → sin *Verificación stale*; tocar un párrafo
con cita → vuelve nombrando el bloque; borrar un párrafo con cita → *«N bloque(s) citable(s)
desaparecieron»*. **Devolver si** un cambio de forma (línea en blanco, encabezado renombrado, fence)
sigue disparando, o si un cambio real en un bloque citado deja de verse.

## #447 · v1.260.3

`python scripts/query_ads.py icasso --theme --dry-run` → *«SALEN del core: 0»* (o sólo
`2019AJ....158..161D` si además apretás la faceta); `ica` → sin el canon en «salen». `lint.py` → la
categoría *Lente desincronizada* deja de listar −45/−20 sobre `ica`/`ica-ruido`; el comando que
imprime para el caso no evaluable **corre** tal cual. **Devolver si** un `extra_core` o un paper con
`citation_count` ≥ umbral y la faceta propia sigue saliendo, o si una estrella cambió de veredicto
respecto de v1.259.2 (ahí no cambió nada salvo la exención por bibcode).

## #450 · v1.261.0

Sobre las 6 filas del barrido: `lint.py` → las 5 abiertas salen como **bloqueante** de #91 nombrando
el vigente (`soportada→contradice` (vigente: `contradice`)), y la 6ª (`…→corregida (r9 …)`) no; la
cabecera de `hd_40307` pasa de «3 contradicen (3 resueltas)» a contar la abierta, y
`lint --cierre hd_40307` da **rc ≠ 0** hasta resolverla. **Devolver si** alguna cadena que termina en
`no-soportada`/`contradice` sigue pasando, si una `contradice→corregida` empezó a bloquear, o si la
cabecera de una nota sin cadenas cambió algún número.

## #449 · v1.262.0

Como las 43 ya se reescribieron a mano acá, el chequeo es al revés: `lint.py` → la categoría en
**(0)** sobre la población de papers; revertí UNA a su texto viejo («El PDF en disco es el
PREPRINT …») y tiene que aparecer nombrando los testigos. Un reemplazo nuevo con `replace_pdf.py`
sobre una nota cuya vista diga preprint → *«⚠ PROSA: N línea(s) …»* con el `grep`, y la nota **sin
tocar**. **Devolver si** dispara sobre una nota coherente, sobre una línea que niega (*«— NO el
preprint»*) o sobre una que nombra las dos.

### #449 (2ª vuelta) · v1.262.1 — **devuelto** y re-angostado

**Qué falló.** 5 hallazgos sobre 268 notas, **precisión 0/5**, y 15 líneas marcadas por
`doc_claims_on_disk` de las que 4 lo eran de verdad. `\bdisco\b` decidía la población y en una
bóveda astro *disco* es palabra de dominio; `publicad[oa]` pelado es ubicuo.

**Qué entró.** Cuatro angosturas, todas en `cfg.doc_claims_on_disk` (una sola función, los dos
llamadores le pasan el stem): (a) el ancla es una frase que **predica sobre el archivo** —
`<documento> (que está) en disco`, `<documento> … en disco es …`, `en disco es/hay el/la …`— y no
`disco` suelto; (b) el **frontmatter** y las `SECCIONES_ESTAMPADAS` quedan afuera (#214); (c) la
unidad es el **bloque, no la línea** (#224); (d) el bloque que nombra un `[[bibcode]]` que no es el
de la nota es **ambiguo y se saltea** — habla del PDF de otro paper. ⚠ El apellido **no** se
chequea: no es decidible desde la nota.

**Validar.**
```bash
python scripts/lint.py | grep -A6 "QUÉ DOCUMENTO hay en disco"   # los 5 falsos NO vuelven
# y la recall: revertí UNA nota a su texto viejo («El PDF en disco es el PREPRINT …») → aparece
# nombrando los testigos; las 4 verdaderas de `doc_claims_on_disk` (1999ISPL....6..145H,
# 2000NN.....13..411H, 2011PLoSO...627594P, 2020BAAA...61B..27U) tienen que seguir marcadas.
```

**Devolver si** vuelve alguno de los cinco, si alguna de las 4 verdaderas dejó de marcarse, o si
dispara sobre una nota coherente por otra vía. ⚠ Y sigue abierto el punto 3 del issue original
(`pdf_leido` en `SALVEDAD_TIPOS`): es lo que cierra esto de verdad —una salvedad estructurada lleva
el bibcode adentro y no hay que adivinar de quién habla la oración—, y va como issue propio.

## #451 · v1.263.0

**Qué entró.** La celda `Condición` es una **cadena** (`⟂`) y rige el **último eslabón**
(`lb.current_condition`), como el veredicto de al lado (#450). `chained_condition` compara por
TEXTO, no por clase; `--resolver` reescribe el eslabón vigente y conserva la historia; el armador
reconoce como el MISMO par re-anclado el juicio cuyo ancla es la de la fila previa (igualdad exacta,
nunca cruzando `bibcode`) y ya no lo descarta; el escritor declara la condición que no quedó
vigente.

**Validar.** Sobre las notas donde midieron las 55 (`rv-doppler` 37, `harps-drs` 9, `hd_40307` 4,
`ica-ruido` 3, `ica` 1, `2008A&A...479..277B` 1), re-correr el escritor con los JSON de esa ronda:

```bash
python scripts/write_verif_sidecar.py <nota> --from build/<slug>/verif/<ronda>
# las `acota` nuevas tienen que aparecer ENCADENADAS detrás de la resuelta, y la fila volver a
# contar como pendiente: `lint.py --cierre <slug>` y el `cond_acota_resueltas` de la cabecera.
python scripts/lint.py | grep -A4 "Condición sin clasificar"
```

El caso de `hd_40307` (ancla `4f79992baa`, `2017MNRAS.468.4772S`) es el que hay que ver entrar: la
condición que dice que la nota se contradice consigo misma.

**Devolver si** una condición de la ronda sigue sin llegar a su celda, si re-correr el escritor sobre
el mismo fan-out **colapsa** la cadena (tiene que ser un no-op), si una resolución firmada
desaparece, o si el escritor lista como «no entró» una condición que sí quedó vigente.

## #452 · v1.264.0

**Qué entró.** `pdf_leido` en `SALVEDAD_TIPOS` (`documento` del vocabulario de `pdf_source`, más
`bibcode` opcional), su chequeo determinista contra los tres testigos de `cfg.doc_on_disk`, las dos
líneas del prompt que ahora lo piden estructurado, `looks_decidable` cubriendo la tercera decidible
por el mismo ancla de #449, y `--propose-pdf-leido` (propone, no escribe).

**Validar.** Acá están las 43 salvedades que midieron #449, ya reescritas a mano:

```bash
python scripts/harvest_views.py <slug> --propose-pdf-leido   # las que siguen en prosa, con la
                                                             # entrada lista para pegar
python scripts/lint.py | grep -A6 "salvedad en prosa que un script podría decidir"
# y el chequeo en vivo: poné `{"tipo":"pdf_leido","documento":"eprint"}` en la extracción de un
# paper cuyo PDF sea la copia del editor → el cosechador la GRITA y NO la publica.
```

**Devolver si** una salvedad `pdf_leido` verdadera no se publica verificada, si una falsa se
publica, si `--propose-pdf-leido` propone sobre una salvedad que no habla del documento en disco
(mismo criterio que #449: dispara sobre una nota coherente), si propone un `documento` que la nota
no respalda, o si **escribe** en algún JSON de `raw/extraccion/`.

### #452 (2ª vuelta) · v1.264.1 — el chequeo quedó, el migrador se corrigió

**Qué entró.** Las cuatro correcciones, todas en el lado del proponente/clasificador y **ninguna**
toca `_check_pdf_leido`: (a) la clase la decide la **cláusula** que el ancla matcheó, con el bloque
todavía como unidad de la negación vecina (#224); (b) negación **simétrica** (`_NO_PUBLICADO_RE`);
(c) **`web` es una clase** —manuscrito del autor, versión para la web— y no contradice a ningún
testigo; (d) el proponente **cruza `doc_on_disk`** antes de proponer y **saltea la nota sin PDF**.

**Validar** — sobre las mismas seis, que es la medición que devolvió el issue:

```bash
python scripts/harvest_views.py <slug> --propose-pdf-leido
```

- `2025A&A...696A.141H` → `publisher` y `2011PLoSO...627594P` → `publisher|ads` siguen igual;
- `1999ISPL....6..145H` y `2000NN.....13..411H` tienen que salir **`web`** (no `publisher|ads`);
- `2011A&A...535A..17B` tiene que salir como **«la salvedad quedó VIEJA: en disco está el
  publicado»**, sin entrada para pegar;
- `2020BAAA...61B..27U` **no tiene que aparecer** (`pdf: null`).

Y la cobertura: el conteo de propuestas tiene que acercarse a las **51** notas que el lint lista con
salvedad en prosa sobre el documento en disco, no quedarse en 4 — la forma «es el PREPRINT …, no la
versión publicada en A&A» ya no sale ambigua.

**Devolver si** alguna de las seis vuelve a proponer mal, si el conteo sigue muy por debajo de las 51
(declarando cuántas y por qué quedaron afuera), o si alguna propuesta nueva la rechaza su propio
chequeo.

## #453 · v1.265.0

**Qué entró.** `harvest_views.py <slug> --restamp-salvedades [--paper <bib>] [--dry-run]`: reescribe
sólo el bloque de salvedades desde el JSON, con `check_salvedad` como siempre, **sin tocar
`vistas[]` ni la prosa**. Con `enfasis`, la unidad es `### Lente — <x>`. El bloque con prosa ajena se
rehúsa. Y `evidencia` es campo de la salvedad estructurada.

**Validar** — es justo el paso que quedó trabado al cerrar #452:

```bash
python scripts/harvest_views.py <slug> --restamp-salvedades --dry-run   # qué cambiaría
# pegá una de las 50 propuestas de `--propose-pdf-leido` en su JSON y corré sin --dry-run:
python scripts/harvest_views.py <slug> --restamp-salvedades --paper <bib>
```

- la nota tiene que publicar la salvedad **verificada**, y su `vistas[]` —`fecha` y `lente`—
  quedar **byte a byte igual** (es el defecto que produjo el issue);
- las **32 vistas de `icasso`** que `harvest` rechazaba tienen que re-estamparse igual: este camino
  no compara `lente` ni `fecha`;
- correrlo dos veces no cambia nada (red 6);
- y la categoría del lint tiene que **bajar** a medida que se pegan las propuestas.

**Devolver si** re-estampar cambia `fecha`, `lente` o cualquier campo de `vistas[]`; si pisa prosa
de la vista o del bloque que no escribió el cosechador; si no es idempotente; o si una salvedad
falsa se publica por este camino (el chequeo es el mismo).

### #453 (2ª vuelta) · v1.265.1 — el barrido dejó de revertir correcciones

**Qué falló.** El barrido **sin `--paper`** re-estampó 144 notas y dejó **27 afirmando un documento
que sus testigos desmienten** (`doc_en_disco` 0 → 27) con **50 `⚙ verificada`** desaparecidas: la
guarda miraba la forma del bloque y no su contenido, y el JSON conserva la prosa anterior al
`replace_pdf`.

**Qué entró.** (a) Antes de escribir se cruza `cfg.disk_doc_conflict` sobre el texto **resultante**
y la nota se **rehúsa** nombrándola, distinguiendo *lo INTRODUCE* de *ya estaba*; (b) se **avisa** la
`⚙ verificada` que deja de serlo, con su número; (c) la estructurada **no evaluable** ya no cuenta
como deuda de prosa en el lint.

**Validar** — es el barrido que hubo que revertir:

```bash
git status --short vault/wiki/papers/          # limpio antes
python scripts/harvest_views.py <slug> --restamp-salvedades      # los siete slugs, SIN --paper
python scripts/lint.py | grep -A4 "QUÉ DOCUMENTO hay en disco"   # tiene que seguir en 0
```

- `doc_en_disco` **no puede pasar de 0**, y las 27 tienen que salir como **rehusadas** con su
  motivo;
- ninguna `⚙ verificada` desaparece sin aviso;
- la categoría #234 tiene que bajar también por las 2 estructuradas no evaluables que antes contaba.

**Devolver si** el barrido vuelve a escribir sobre una nota corregida a mano, si `doc_en_disco` sube,
si una `⚙ verificada` se va en silencio, o si la rehusada era en realidad segura (falso positivo
sobre una nota coherente).

### #453 (3ª vuelta) · v1.265.2 — una salvedad en prosa ya escrita no se reescribe

**Qué falló.** Las tres correcciones de 1.265.1 se midieron y andan, pero el barrido **reescribió 28
salvedades**: 22 correcciones del 09-12 (redactadas *«esta vista se leyó del…»*, que **no ancla**,
así que el cruce no las veía y el texto falso quedaba además invisible para `doc_en_disco`), **una
cita textual** cambiada por otra que la fuente no dice —que ninguna capa caza, porque una salvedad no
lleva `[[bibcode]]`— y un escape perdido.

**Qué entró.** La guarda pasa a ser **estructural**, sin depender de ningún ancla: se rehúsa la nota
cuando el re-estampado **reescribiría** una salvedad en prosa ya escrita. Agregar y quitar siguen
pasando. Sólo mira el bloque de prosa (el de `⚙ verificada` lo re-deriva el chequeo).

**Validar** — el mismo barrido completo, sin `--paper`:

```bash
git status --short vault/wiki/papers/
python scripts/harvest_views.py <slug> --restamp-salvedades
git diff --stat vault/wiki/papers/
```

- **cero** salvedades en prosa reescritas: toda línea que sale del diff tiene que ser un `+` o un
  `-`, nunca un par que cambia el texto de la misma;
- las **22** tienen que salir como rehusadas con *«REESCRIBIRÍA N salvedad(es) en prosa»*;
- las **43** que sólo agregan o quitan tienen que seguir pasando (incluidas las 44+2 ya cobradas,
  que son no-op);
- `doc_en_disco` en 0 y `vistas[]` intacto, como en la 2ª vuelta.

**Devolver si** alguna salvedad en prosa cambia de texto, si una nota que sólo agregaba o quitaba
queda rehusada (falso positivo que frenaría el trabajo), o si el conteo de rehusadas no coincide con
las notas que tienen corrección a mano.

