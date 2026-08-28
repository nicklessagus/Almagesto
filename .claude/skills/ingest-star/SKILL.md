---
name: ingest-star
description: Usar cuando el usuario pide bajar/agregar/ingestar una estrella a la bóveda ("bajá GJ 581", "ingest tau ceti", "agregá la estrella X", "traé la bibliografía de AU Mic"). Corre la cadena de ingesta y hace la extracción LLM.
version: 1.20.0
---

# Ingest: agregar una estrella a la wiki

Operación **ingest** del patrón LLM Wiki (ver `CLAUDE.md`). División: los scripts bajan, el LLM
procesa. Trabajar desde la raíz del repo.

## Pasos

**Copiá este checklist al chat al arrancar y andá tildándolo** — tres pasos (2b, 2c, 5b) son
fáciles de saltear y **ninguno deja rastro si se omite**. El lint tiene red para **2c** (*triage
pendiente*, #55), para **5b** (*sin verificar* / *verificación stale*, #56) y para lo que la
síntesis del paso **3c** dejó afuera (*extraído pero no sintetizado*, #75 — que es también la red
del contraste de **3b**) y para **2b** (*barrido full-text sin rastro*, #88 — el registro del
sujeto no tiene `barridos`):

```
Progreso del ingest de <estrella>:
- [ ] 1  slug resuelto + alias mostrados al usuario y aprobados ANTES de buscar
- [ ] 2  cadena mecánica (orquestador) — sin abortos
- [ ] 2b barrido full-text (--sweep) revisado
- [ ] 2c triage de candidatos resuelto (aceptado / --drop con motivo / al usuario)
- [ ] 3  extracción LLM (una VISTA por sujeto) de TODOS los core (o recorte declarado en el registro) + `harvest_views.py`
- [ ] 3b contraste cross-paper (inventario por eje)
- [ ] 3c síntesis a la ficha (frontmatter propio + prosa + disputes)
- [ ] 4  auto-revisión de autosuficiencia
- [ ] 5  bookkeeping (index, log, matriz, STATUS) + `triage.py <slug> --sintesis`
- [ ] 5b verify-citations sobre la ficha + notas nuevas
- [ ] 6  `lint.py --cierre <slug>` en 0 → commit → preguntar push
```

1. **Resolver el slug y ACORDAR LOS ALIAS antes de buscar (D-7).** Buscar la estrella en
   `vault/config/stars.yaml`. Si no está, agregarla con `slug`, `simbad`, `ads_object`, `aliases` y
   (si aplica) `data_local`.

   ⚠ **El recall de toda la búsqueda cuelga de `aliases`, y un alias que falta es un paper que
   nunca aparece — en silencio.** Es el mismo modo de falla que el glifo griego, pero **sin
   rescate**: el glifo tiene su pasada de recuperación, un alias faltante no tiene ninguna. Por eso
   no se escriben a ojo:
   - Resolver identificadores en **SIMBAD** (`python scripts/fetch_ground_truth.py <slug>` los trae,
     o consultá SIMBAD directo si la estrella todavía no está en el YAML).
   - **Mostrarle al usuario la lista candidata en prosa** —con las variantes de espaciado y de glifo
     ya expandidas (`GJ 581` / `GJ581` / `Gliese 581` / `HO Lib` / `BD-07 4003`)— y decir cuáles
     venís a agregar y por qué.
   - **No correr la query hasta que apruebe.** Recién ahí persistir lo aprobado en `stars.yaml`.

   Es el mismo patrón que `setup` (los términos del objetivo, D-8) e `ingest-theme` (los términos
   del tema, D-29): el agente **propone**, el usuario **valida**, y lo aprobado queda escrito.

2. **Cadena mecánica** (orquestador — desde la raíz del repo):
   ```bash
   python scripts/ingest_star.py <slug>
   ```
   Corre la cadena completa (ADS → PDFs arXiv y no-arXiv → ground-truth NEA/SIMBAD → stubs →
   fulltext → retracciones), abortando al primer fallo. **El orden canónico vive en el header de
   `scripts/ingest_star.py`** — puntero, no copia: no lo repliques acá ni en otros docs. Para un
   flag fino (`--rows`, `--all`, `--force` de un paso) corré el script puntual.

   ⛔ **La mecánica de la cadena se describe en UN solo lugar (#67):**
   `.claude/skills/ingest-star/reference/cadena-ads.md`, que `ingest-theme` apunta también. Ahí
   están la **guardia de expansión** (el checkpoint humano que frena si el pool se multiplicó), el
   citation chaining, el rate limit de `fetch_arxiv`, la cascada de `fetch_pdf` y su residuo
   `build/<slug>/missing_pdf.json`, los dos chequeos de `extract_fulltext`, `check_retractions` y
   `extra_core` como **curación persistente y versionada**. Leelo la primera vez y ante cualquier
   aborto; lo que sigue acá es sólo lo que es **de una estrella**.
   Si el residuo quedó con entradas, la cascada manual de rescate está en
   `reference/rescate-pdfs.md` — y **"bajar manual por DOI" no alcanza**.

   **`fetch_ground_truth` (SIMBAD + NEA) — sólo en estrellas.** Trae `spectral_type` de SIMBAD y
   `teff_K`/`dist_pc`/`P_rot_days` + los planetas de NEA (pscomppars) a
   `vault/raw/ground_truth/<slug>.json`, con `_autoridad` por campo. En un re-ingest **no** lo
   refresca salvo `--force`: refrescar desde NEA es decisión explícita, no side-effect.

   **Rescate por glifo — sólo en nombres Bayer.** Si el nombre es letra griega + constelación corre
   antes el rescate (`via: glyph`, se desactiva con `--no-glyph`): ADS unifica `epsilon`/`eps`/`ε`
   pero **descarta** los lookalikes `ϵ` (U+03F5) y `∊` (U+220A, el glifo de ApJ/AJ/MNRAS), así que
   esos papers quedan indexados sólo por la constelación e **invisibles** a la query canónica
   (medido en ε Eri: 121 core perdidos, incluido el descubrimiento). No hace falta listar las
   grafías en `aliases`: el carácter se descarta, no falta la variante — el rescate trae el superset
   de la constelación y filtra client-side por el glifo.

   **El chaining va anclado AL SUJETO** (`full:` sobre nombre+alias), que es lo que lo distingue del
   de un tema: trae surveys y catálogos conectados por el grafo aunque no nombren la estrella en el
   abstract. Lo que trae **no es automáticamente pertinente** → compuerta de triage, paso 2c.

2b. **Barrido full-text (NO perder surveys de muestra grande).** La query directa de `query_ads.py`
   busca en **título+abstract** → punto ciego sistemático: los **surveys de muestra grande**
   (Mount Wilson HK, catálogos de actividad) **tabulan la estrella sin nombrarla en el abstract**. El
   **chaining del paso 2 ya trae** los que están conectados por citas a los core encontrados; este
   barrido caza los que quedan **fuera del grafo** (o cuyos core-vecinos no entraron). Correr:
   ```bash
   python scripts/query_ads.py <slug> --sweep
   ```
   Corre `full:` sobre nombre+aliases expandiendo solo **todas las grafías** (`HD 152391` ↔
   `HD152391` — ADS tokeniza distinto y los papers usan ambas; antes esto eran probes manuales por
   grafía, fáciles de olvidar) y lista **sólo los core que el ingest NO trajo** — la lista corta de
   candidatos, ordenada por **citas/año** y no por citas crudas (#79: el barrido existe para
   recuperar casos tipo Garg+2019 / Willamo+2020, core poco citados que caen al fondo del ranking;
   rankearlo por citas repetía el sesgo de edad del mecanismo que le falló). Revisarla y agregar los que correspondan **de forma persistente** con
   `extra_core:` (lista de mapas `{bibcode, via, fecha, motivo}` — D-58; el `triage` imprime el snippet listo para pegar) en la entrada de la estrella en `vault/config/stars.yaml` (el
   `query_ads` los trae por bibcode, `via: manual`, y sobreviven al re-run — a diferencia de editar
   `build/`, que es scratch y se pisa); después re-correr la cadena (idempotente). Si el barrido
   devuelve muchos y no bajás todos, **listá cuántos quedan sin bajar** en el `log` — no cures en
   silencio. (Un resultado vacío **no prueba ausencia** en papers pre-digitales — ver Notas: el OCR
   del escaneo pierde filas de tabla.)

2c. **Compuerta de triage del chaining (juicio, antes de bajar nada).** El chaining trae papers
   conectados por citas que **mencionan** al sujeto sin hablar de él: la lente clasifica **tema**, no
   **pertinencia al sujeto** (medido: de 378 core nuevos, 368 del grafo y sólo 18% pertinentes —
   incluyendo una tesis de física de partículas como "core" de AU Mic). Y no se aproxima con una
   regla sintáctica: la densidad de mención sale **invertida** (los ruidosos nombran al sujeto 27
   veces de mediana; los valiosos, 2). Por eso el juicio es tuyo. `query_ads` ya auto-aceptó los que
   llevan **el sujeto en el título** (1 falso positivo en 310) y dejó el resto como **candidatos**
   —no bajados—:
   ```bash
   python scripts/triage.py <slug>            # listar (agregá --report para la tabla en outputs/)
   ```
   (En una bóveda ingestada antes de 1.9.0, `--migrate` consolida de una vez el juicio que haya
   quedado en el `build/<slug>/triage.json` viejo; ver `maintain E`.)
   Los marcados `◆` **ya tienen nota en la bóveda** (entraron por otro slug): ya están bajados y
   extraídos — la decisión sigue siendo por-slug (¿pertinente a ESTE sujeto?), pero se despachan
   rápido (el `stars:` que falte lo cubre el retro-linkeo add-only de `make_notes`).
   Clasificá cada candidato **sólo por título+abstract** (no bajes nada para decidir):
   - **pertinente** → pegá el snippet que imprime `triage.py` en `extra_core:` de `vault/config/stars.yaml` y re-corré
     la cadena (idempotente: baja sólo los nuevos; `extra_core` es override del clasificador).
   - **ruido** → `python scripts/triage.py <slug> --drop <bib> … --reason "<motivo>"` (persiste en
     `decisiones` de `vault/config/registro/<slug>.yaml` — **versionado: se commitea y viaja**, como
     `extra_core`; el próximo refresh no lo re-propone, tampoco en otra máquina). Agrupá por
     categoría y descartá por lote, con el motivo real: el motivo es lo que hace que la decisión
     sirva dentro de seis meses.
   - **dudoso** → **al usuario**, junto con (a) los papers que salen del core y ya tienen extracción
     LLM y (b) el resumen de volumen (core nuevo vs notas actuales). `--report` deja la tabla en
     `outputs/triage-<slug>.md` para decidir por lote.
   No curar en silencio: lo descartado queda con motivo, y lo que quede sin decidir se anota en el `log`.
   **El lint tiene red (#55):** lo que quede en `candidates` sale como backlog *Triage pendiente* —
   antes el aviso vivía sólo en este stdout y el ingest podía cerrarse "en 0" con cientos sin
   juzgar. Sin `build/` local, el lint cae a `busquedas` del registro versionado y reporta el
   snapshot con su fecha (#51/#64), así que la red ya no depende de la máquina — pero el conteo del
   snapshot es el de la última corrida de la cadena, no el vigente.

3. **Extracción LLM — se leen TODOS los core (D-13).** *"Leer los papers clave"* no es un criterio:
   no dice cuántos, ni en qué orden, ni deja registro de qué se leyó. Es lo que produjo el número
   medido en una bóveda real: **42 papers `relevance: high` que nadie abrió**, en una ficha que se
   presenta como el snapshot del conocimiento de la estrella. Si la lente marca 193 como core y la
   extracción lee 40, "core" deja de ser la unidad de trabajo y el consumidor no sabe cuál de los
   dos números lo describe.

   - **Default: se leen todos los core.**
   - **En qué ORDEN se leen** — si son muchos, el orden decide qué queda afuera, así que no lo decide
     el `glob`:
     ```bash
     python scripts/triage.py <slug> --prioridad
     ```
     Lista los core ordenados por **cuántas facetas del objetivo toca cada uno** (citas como
     desempate). El criterio es deliberado: citas/año mide atención de la comunidad, facetas mide
     **pertinencia a lo que esta bóveda quiere saber**, que es la pregunta que la priorización tiene
     que responder — y sale gratis, porque `classify()` ya la computó. ⛔ **No es un filtro y no toca
     la lente**: es un orden sobre los que **ya** son core.
   - Si no se leen todos, **se avisa al usuario** y el motivo queda **registrado**:
     ```bash
     python scripts/triage.py <slug> --extraccion subconjunto --reason "<el criterio>"
     python scripts/triage.py <slug> --extraccion todos          # el default del contrato
     ```
     El `--reason` es obligatorio por el mismo motivo que en `--drop`: dentro de seis meses lo que
     sirve es el criterio (*"los 12 de más facetas"*, *"sólo los que arbitran la señal b"*), no el
     rótulo `subconjunto`. Sin la declaración, el lint lo reporta como *recorte de lectura sin
     declarar* — la red existe y este comando es el que la cierra.

   ⚠ **Cómo anotar cada valor (#103).** Al copiar un número a la nota de paper: **la página del
   PDF** (#205: la fuente es el PDF), **el régimen** en que la fuente lo
   afirma (muestra, época, corte de datos, modelo), la marca **segunda mano** con su cita si la
   fuente se lo atribuye a otro trabajo, y **el tiempo verbal y el cuantificador de la fuente, tal
   cual** (*«was associated»* no se vuelve *«is associated»*; *«el 75 % de la muestra»* no se vuelve
   *«la muestra»*). ⛔ **Nada de prosa comparativa en la nota de paper:** comparar dos papers es
   `inferencia` y va al `## Inventario por eje` (paso 3b).

   Los seis mecanismos de error que esa regla ataca —medidos sobre una ficha real: 68 pares, 14
   defectos, **cero inventados**— y por qué la contramedida es estructural y no un «prestá atención»
   (incluido el hallazgo de que **pedir exactitud en el prompt la empeora**) están en
   `reference/anotar-valores.md`.

   - **Sea cual sea la decisión, la tabla `## Papers` de la ficha declara cuál entró y cuál no** — el
     estado nunca es implícito. Se re-estampa con `python scripts/make_notes.py <slug>`.

   **Escala: un subagente por paper (D-14).** 193 papers no entran en una lectura. Se paga como
   ya se paga `verify-citations`: **un subagente por paper**, cada uno lee un solo
   `vault/raw/pdfs/<slug>/<bibcode>.pdf` y devuelve la extracción estructurada. Caro pero
   acotado, y hace el paso **auditable**: cada extracción tiene su corrida. Lanzalos en tandas
   paralelas; el orquestador (vos) mergea y escribe las notas.

   ⛔ **El prompt de cada subagente se GENERA, no se escribe a mano (INV-100):**
   ```bash
   python scripts/extraction_prompt.py <slug> <bibcode>      # --theme si el slug es un tema
   ```
   Lo arma desde lo que la bóveda ya sabe: los `aliases` del sujeto → patrones de `grep` **cortos**
   (#44) para **ubicar** en el `.txt` en qué parte del PDF mirar, las rutas del PDF y del `.txt`, y
   una **ruta de salida por bibcode**. El motivo es
   medido: en el ingest de τ Ceti (79 papers, prompt a mano) **54 extractores redescubrieron por su
   cuenta** el entrelazado de columnas, **23** la grafía del sujeto y **tres se pisaron el archivo de
   salida** entre sí. Toda regla que vive acá y no en el prompt se cae **en silencio** en esa
   frontera — y mientras el prompt sea memoria del agente, el paso **no es reproducible**, así que
   dos corridas del mismo ingest no comparan nada.

   ⛔ **Lo que produce cada subagente es UNA VISTA, no «la extracción del paper» (#188).** El
   prompt pregunta *«¿qué dice sobre {sujeto}?»*, con los `grep` armados desde **sus** alias: el
   mismo paper leído desde otro sujeto da otra vista. Por eso la sección de la nota es
   `## Vista — <sujeto>` y el JSON trae `vista{sujeto,tipo,txt,fuente}` (#207). Sin el scope, el silencio de la
   nota sobre un eje es indistinguible de *«se miró y no hay nada»* — medido: 141 de 908 notas de
   una bóveda real las reclaman 2+ sujetos y **ninguna** tiene una segunda extracción.

   **Cosechá con el script, no a mano:**
   ```bash
   python scripts/harvest_views.py <slug>                    # --theme si el slug es un tema
   ```
   Estampa la vista con `fecha`/`txt`/`lente`, mergea `methods`/`thesis_links`/`role` **add-only**
   y escribe la sección **mientras siga siendo la plantilla del stub** (prosa ya redactada no se
   pisa sin `--force`). Y es la única compuerta que corre `is_extraction` (INV-103): un JSON de
   `verify-citations` también trae `bibcode` y también es válido — cosechar a mano pisó 13 notas
   terminadas **en silencio**.

   Poblar **las notas de paper** (la ficha se escribe en 3c, después del contraste — no saltear
   directo a la prosa):
   - en `vault/wiki/papers/<bibcode>.md`: `methods`, `thesis_links`, `role` (#73: `fundacional`
     introduce el método/mecanismo · `aplicacion` lo instancia en un caso · `arbitro` reanaliza y
     resuelve una tensión previa — sale de leer el paper, la regex del clasificador no puede
     inferirlo, y sin él contrastarlo contra otro no está definido), y la sección
     `## Vista — <sujeto>` — sus bullets ya vienen ramificados por tipo de sujeto (#76):
     ground-truth (P/K/e por planeta), los **ejes de `relevance.facets`** del objetivo de esta
     bóveda, métodos y aporte al objetivo. Llenar los que el stub trae, no una lista fija de memoria.
   - un paper que este sujeto **reclama** (`stars`/`thesis_links`) y que legítimamente no vas a leer
     desde acá —aporta sólo al roll-up— se **declara**: `no_vista: [{sujeto, motivo}]`. El lint lo
     baja de backlog a informativo. Mismo criterio que `no_sintetizado` y que el `--reason` del
     triage: no curar en silencio.
   ⚠ **`pdf_source` antes de copiar un número** (#57): con `eprint` el `.txt` es el **preprint**
   (un `v1` pre-referato puede traer otros valores que el publicado que identifica el bibcode), y con
   `null` no se sabe —que **no** es "publicado"—. Un valor que choca con el ground-truth o con el
   abstract de ADS es candidato a **diferencia de versión**: abrí el PDF publicado o dejá la
   salvedad en la nota. `verify-citations` lo detecta después; **acá es donde el número entra a la
   bóveda**.

3b. **Contraste cross-paper (#72) — antes de escribir la síntesis.** Entre "leí los papers" y
   "escribo el resumen" hay una operación, y es la de más apalancamiento de la cadena: armar el
   **`## Inventario por eje`** de la nota. Una fila por paper para cada **eje** —parámetro o hecho—
   donde los papers **no coinciden** (`Eje | Paper | Dice | Método / baseline`). Los ejes con acuerdo
   unánime **no entran**: misma regla de poda que la prosa.
   ⛔ **Sin columna "valor adoptado" ni "por qué".** Adoptar un valor es **decidir por el
   consumidor** y rompe el flujo unidireccional de la regla #0: la bóveda reporta el **estado de la
   literatura**. La lectura propia —"11.5 d es el armónico de 34 d"— va aparte y marcada
   `inferencia`.
   ⚠ **Mirá el `role` (#73) antes de leer dos filas como desacuerdo:** fundacional↔aplicación **no
   es contraste, es instanciación**. Y el `arbitro` no es una fila más: es el que resuelve.
   Sin esto, tres papers con tres `P_rot` terminan en una frase con un solo `[[bibcode]]` y se
   evapora que los otros dos valores existen — que es exactamente lo que la ficha promete responder
   sin abrir un paper. La red de que el contraste ocurrió es #75 (*extraído pero no sintetizado*):
   un paper que pagó la extracción y no aparece en la nota sale como backlog.

   ⛔ **Todo valor que va a la nota viaja con su página del PDF (#205).** Desde que la extracción
   lee el PDF esto es lo normal, no una excepción para ecuaciones. Si la vista del paper ya trae el
   dato **con su página**, se copia con esa procedencia; si llega **sin** página —una vista vieja,
   escrita cuando se leía el `.txt`— nadie lo verificó contra la fuente: abrí el PDF acá. Vale
   especialmente para fórmulas y valores de tabla, que son los que el `.txt` pierde o **cambia** sin
   dejar marca: medido, `si = 1` donde el paper dice `si = ±1` (el supuesto binario **es** el ±1) y
   «model (8)» donde dice «model (3)».

3c. > ⚠ **Un ítem de linaje = un BULLET propio, no una oración con seis citas.** Cuando enumeres
> quién hizo qué —«PCA vía SVD [[A]], [[B]]; Wapiti [[C]], [[D]]; YARARA [[E]]»— dale a cada fuente
> su propio bullet. Medido sobre cuatro rondas de verificación de un concepto real: **los 7
> `no-soportada`/`contradice` fueron TODOS de atribución**, ninguno de invención, y todos vivían en
> párrafos así — el párrafo pone cláusulas de fuentes distintas en **adyacencia sintáctica**, y la
> adyacencia se lee como pertenencia. Las transcripciones de ecuaciones, en cambio, salieron
> perfectas (18/18, 12/12, 6/6). Además abarata las correcciones: el radio de daño de un arreglo
> —cuántos pares de verificación invalida— bajó de **5,0 a 1,8**.
>
> ⚠ **Pero no es gratis y por eso no es regla dura:** el ancla compartida del párrafo también era
> una **red** —obligaba a re-mirar el vecindario donde justamente vivían esos errores— y
> granularizar la apaga. Si el tema es chico, el párrafo sigue siendo defendible.

**Síntesis a la ficha** (`vault/wiki/stars/<slug>.md`), apoyada en el inventario de 3b.
   Completar el frontmatter que es **tuyo** (`activity_indicators_expected`,
   `methods_applied.literature`, `disputes` —a nivel nota, #71—) y escribir la prosa: qué se sabe, qué
   indicador debería trazar actividad para ese tipo espectral, huecos.
   ⛔ **No toques los campos de ground-truth** (`spectral_type`, `teff_K`, `dist_pc`, `P_rot_days` y
   los cinco de cada `planets[]`): son **espejo de NEA** (#70). Si NEA no tiene el valor —pasa
   seguido con `K_ms` y `e`— el campo queda **null** y el valor de literatura va **al cuerpo, citado
   `[[bibcode]]`**; si discrepa de NEA es una `disputes[]`; si es lectura tuya va marcado
   `inferencia`. Rellenarlos vuelve el número indistinguible del auditable y el lint lo marca como
   **bloqueante**.
   - **Contrastar contra `vault/raw/ground_truth/<slug>.json`**: si un paper discrepa del archivo
     (p. ej. planeta dudoso), taguearlo en `disputes` **a nivel nota** con posiciones explícitas
     (#71) —`field: b.existence`, una posición `{ref, value}` por el paper y otra
     `{source: ground_truth, value}` por NEA—; ver *Disputas* en `CLAUDE.md`. No celebrar.
     (⛔ **`bearing` no va en la nota del paper** — D-21: la postura vive en la tabla de evidencia de
     la hipótesis, y en el paper el lint la bloquea como schema viejo.)
     Si el desacuerdo es **paper↔paper** sobre algo que NEA no arbitra (`P_rot`, la naturaleza de
     una señal), va en la MISMA estructura con dos posiciones `{ref, value}`: eso es lo que antes
     terminaba en prosa suelta.

4. **Auto-revisión de autosuficiencia (semántica).** Releer la ficha **como un agente externo que
   sólo tiene ese archivo**: ¿se entiende la estrella sin abrir ningún paper? Checklist: parámetros
   estelares clave, inventario de señales RV (tabla $P/K/e/m\sin i$ + estado), señales
   disputadas/descartadas, indicadores de actividad esperados, métodos aplicados y huecos. Si para
   responder algo hay que abrir un paper, falta en la ficha → agregarlo. (`lint.py` chequea dos
   proxies estructurales — cada planeta del frontmatter discutido en prosa, y cada paper **extraído**
   citado en alguna ficha o concepto (#75) — pero la suficiencia la juzgás vos.)
   ⚠ **El backlog *extraído pero no sintetizado* es el que cierra este paso:** un paper que pagó la
   extracción y no aparece citado en ninguna entidad es extracción perdida. O lo sintetizás donde
   corresponda, o declarás por qué no va: `no_sintetizado: <motivo>` en su nota (la **regla de poda**
   es motivo válido; la marca sin motivo se sigue reportando).

5. **Bookkeeping.** Actualizar `vault/wiki/index.md` (agregar la estrella), appendear a `vault/wiki/log.md`,
   tocar `vault/wiki/matrices/method_star.md` (qué métodos se aplicaron en la literatura) y `vault/STATUS.md`
   si cambió el estado. Y **declarar la fecha de síntesis** —la tercera de la cabecera (INV-82)—:
   ```bash
   python scripts/triage.py <slug> --sintesis --n-papers <N>
   python scripts/make_notes.py <slug>          # la estampa en la ficha (cirugía, no toca la prosa)
   ```
   No se puede derivar: `git` fecha el **archivo**, así que una cirugía de cabecera contaría igual
   que reescribir el resumen. Sin ella, refrescar el corpus mueve la fecha de búsqueda y la ficha se
   lee como re-sintetizada cuando la prosa es la de tres meses atrás. (El `lint` va **después** del verify del paso 5b: `CLAUDE.md` lo pide
   "antes de lint/commit", porque resolver una cita no-soportada suele cambiar la prosa.)

5b. **Verificar citas.** Correr el skill `verify-citations` sobre la **ficha de la estrella** (y sobre
   las notas de paper nuevas con extracción). La ficha es el artefacto **más reusado** (se arma un
   informe desde ahí), así que su prosa con `[[bibcode]]` —parámetros estelares, señales RV, disputas—
   debe estar respaldada por la fuente (cita textual + página del PDF; sin respaldo ⇒
   no-soportada). Prioridad: las afirmaciones que **cambian cómo se lee una señal RV** y las
   `disputes` (cada `posiciones[].value` y el `note` vs el paper que la sostiene; la posición
   `{source: ground_truth}` no se verifica contra papers). Resolver cada no-soportada/contradice (corregir el valor,
   reasignar la cita, o marcar `inferencia`) y dejar el bloque `## Verificación de citas`.

6. **Cierre (commit + push).** Tras la verificación (lint en 0), `git add` de los archivos
   **específicos** que tocó la operación (no `-A`) y commitear con mensaje
   descriptivo. Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Notas
- Reglas de notación/reporte y schemas de frontmatter: ver `CLAUDE.md`.
- No copiar FITS a la bóveda: la ficha apunta a los datos vía `data_local`.
- **Ubicar con el índice (saltar afiliaciones):** el `.txt` es el índice para saber **en qué parte
  del PDF** mirar; los papers arrancan con autores/afiliaciones que no aportan. Para ubicar rápido,
  p. ej.,
  `awk 'tolower($0)~/abstract/{f=1} f' vault/raw/fulltext/<slug>/<bib>.txt | head -60` para el abstract, y
  `grep -inE "P_?rot|K ?=|mass|chromatic|GP|activity indicator" ...` para los números clave. No tocar
  el `.txt` en disco (se usa para grep); el salto es sólo en la lectura. **Patrones cortos, siempre**
  (#44, convención canónica en `verify-citations`): el `.txt` entrelaza las dos columnas en la misma
  línea física (73% del corpus), así que un patrón largo da falso negativo — y acá el falso negativo
  se lee como "el paper no reporta ese parámetro", que es exactamente lo que la extracción decide.
- **Mirá las TABLAS, no sólo el texto**, y recordá que **un `full:"HD X" → 0` NO prueba ausencia**
  en papers pre-digitales: en los dos casos el dato puede estar en una imagen que ninguna búsqueda
  de texto ve. Las mediciones y qué hacer en cada caso están en `reference/rescate-pdfs.md`.
- **PDFs que la cadena no pudo bajar, y OCR:** todo lo que quedó en `build/<slug>/missing_pdf.json`
  se resuelve por la **cascada manual** —Messenger / página del instrumento / mirrors / tablas del
  CDN / derivar al usuario, y ⛔ **nunca** gastar intentos en `aanda.org` (DataDome)—, canónica en
  `reference/rescate-pdfs.md` (`ingest-theme` y `append-knowledge` apuntan al mismo archivo). Ahí
  también está el OCR de `extract_fulltext` y el síntoma del "escaneo con marca de agua".
