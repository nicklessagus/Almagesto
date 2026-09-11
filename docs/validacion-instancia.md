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

