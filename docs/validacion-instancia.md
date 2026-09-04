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
