---
name: ingest-theme
description: Usar cuando el usuario pide investigar/ingestar un TEMA en profundidad a la bóveda, como si fuera una estrella pero por tópico ("traé todo sobre actividad y RV", "investigá a fondo el bisector vs actividad", "ingestá el tema de los GP en RV", "armá un concept con la bibliografía de indicadores de actividad"). Dispara una búsqueda ADS por keywords y hace la extracción LLM hacia un concept durable. Soporta además, sólo a pedido explícito, un tema off-ADS — típicamente un método de otra disciplina (estadística, ML) al servicio del foco astro — desde PDFs locales + web (ver Modo off-ADS).
version: 1.17.0
---

# Ingest: agregar un TEMA a la wiki

Operación **ingest** del patrón LLM Wiki (ver `CLAUDE.md`), hermana de `ingest-star` pero por **tema**
en vez de por estrella. División idéntica: los scripts bajan, el LLM procesa. Trabajar desde la raíz
del repo.

**Diferencias con `ingest-star`** (mismo patrón, distinto sujeto: un tema en vez de una estrella):
- La búsqueda ADS es **por keywords** (query Solr cruda), no por nombre vía SIMBAD.
- El producto durable es un **concept** (`concepts/<area>/<concept>.md`), no una ficha de estrella.
- **No hay ground-truth** (no existe NEA/SIMBAD para un tema) → se **saltea `fetch_ground_truth.py`**.
- **No** se toca la matriz método×estrella.
- Las notas de paper llevan `stars: []` y `thesis_links` pre-sembrado al concept.

> **Default = vía ADS** (los **Pasos** de abajo — la plomería con descubrimiento automático). Si el
> usuario pide **explícitamente** un tema cuya bibliografía vive **fuera de ADS** (típicamente un
> método de otra disciplina), usar el **Modo off-ADS** (al final de los Pasos). `ingest-star` no
> tiene este modo: es astro-only.

## Pasos

**Copiá este checklist al chat al arrancar y andá tildándolo** — el retro-tag (3b), el contraste
(3c) y la verificación (6b) se saltean sin dejar rastro. El lint tiene red para **6b** (*sin
verificar* / *verificación stale*, #56) y para lo que la síntesis dejó afuera (*extraído pero no
sintetizado*, #75 — que es también la red del contraste de 3c) y para lo que **3b** deja
reclamado y sin leer (*reclamado sin vista*, #188 — backlog, se cierra con la vista o con
`no_vista` + motivo):

```
Progreso del ingest del tema <tema>:
- [ ] 0b (tema off-ADS) barrido de los TRES backends antes de declarar fuentes a mano (`discover.py`)
- [ ] 1  consulta co-diseñada con el usuario (o `sources:` si es off-ADS)
- [ ] 1b (tema de MÉTODO) `facet:` propia acordada — y `fundacional_min_citas` si va
- [ ] 2  cadena mecánica (ingest_theme.py) — sin abortos
- [ ] 3  extracción LLM (una VISTA por paper) de TODOS los core (o recorte declarado en el registro) + `harvest_views.py --theme`
- [ ] 3b retro-tag por grep de aliases sobre el corpus pre-existente
- [ ] 3c contraste cross-paper (inventario por eje)
- [ ] 4  síntesis del concept durable (+ régimen de validez / disputes)
- [ ] 5  auto-revisión de autosuficiencia
- [ ] 6  bookkeeping (index, log, STATUS)
- [ ] 6a `contrast.py <slug> --validar-todo` en 0 — **antes** del verify (#323)
- [ ] 6b verify-citations sobre el concept + notas nuevas
- [ ] 7  `lint.py --cierre <slug>` en 0 → commit → preguntar push
```

1. **Co-diseñar la consulta con el usuario (NO traducir en silencio).** El usuario da el tema en
   lenguaje natural ("actividad y RV", "bisector vs actividad"); el valor del skill está en **pulir
   esa intención antes de gastar la búsqueda**. Secuencia:
   - **a. Interpretar y proponer.** Convertir la intención en una **query Solr cruda candidata** y
     **mostrársela explicada** (qué término exige como AND, qué grupo va en OR). Señalar el sesgo:
     p. ej. exigir `abs:"bisector"` como AND deja afuera papers de S-index/FWHM puros.
   - **b. Proponer la FAMILIA de términos, en prosa (D-29).** Mismo patrón que los alias de una
     estrella (`ingest-star` paso 1) y las facetas del objetivo (`setup` paso 3): el usuario dice
     *"separación ciega de fuentes"* y vos proponés la familia completa —fastICA, JADE, Infomax,
     cocktail party, non-gaussianity, mixing matrix…— **en castellano y sin regex** (vos traducís a
     `abs:"..."`). Ofrecer además variantes de alcance (amplia ↔ acotada). Usar `AskUserQuestion` si
     la elección cambia qué se trae. **No buscar hasta que apruebe.**
   - **c. Validar con un conteo barato** antes de bajar nada (y antes de persistir el slug):
     `python scripts/query_ads.py --probe '<query candidata>' --rows 50` y mirar el corte CORE/no-core +
     los títulos top (ordenados por citas). Si trae cientos con ruido o muy pocos, reajustar la
     query y reconfirmar. **No** bajar PDFs hasta que el usuario apruebe la query final. (`--probe`
     recibe la query cruda, así que corre sin que el tema exista todavía en `themes.yaml` —
     `--theme <slug>` recién funciona después del paso d.)
   - ⛔ **c1. Para un tema de MÉTODO, re-corré el probe CON la lente del tema, después del paso d:**
     `python scripts/query_ads.py <slug> --theme --probe` (la query sale de `query:`; se puede pasar
     otra como argumento). Sin `--theme`, el preview clasifica con la lente **global**, que D-26
     declara *activamente dañina* para un tema de método — y no es «menos preciso»: es el veredicto
     **opuesto** sobre la población que el tema existe para capturar. Medido en `ica` (951
     registros): los tres papers de separación de componentes más citados caían en el **no-core** y
     el core se llenaba de binarias eclipsantes que matchean `rv`. En este modo cada core lleva
     además **por qué puerta entró** (`fundacional` / `astro`, #126), que es lo que decide el
     recorte de lectura, y la línea de cierre manda a `themes.yaml` (`facet:`,
     `fundacional_min_citas`), que es el archivo que decide este corte.
     ⛔ **Leé el desglose del NO-CORE (#289) antes de tocar nada:** distingue *sin la faceta propia*
     (la faceta está bien / apretala más) de *pasa la faceta y ninguna puerta abre* (la faceta
     acertó y el problema es la puerta) — piden acciones **opuestas** y antes se mostraban
     idénticas. Medido: 261 contra 32, con los dos papers que el tema existía para capturar entre
     los 32; aflojar la faceta —el movimiento que sugería la pantalla— deja entrar los otros 261.
     El bloque *«no-core que PASAN la faceta»* es de donde sale `extra_core`.
     ⛔ **Y si el tema es de otra disciplina, mirá el `search_fq` (#295).** Es la mitad **más
     restrictiva** del filtro (acota server-side, antes de traer nada) y sale del **objetivo** salvo
     que el tema declare el suyo: en una bóveda astro, un tema de estadística o signal processing se
     busca sobre un universo que excluye su literatura **por construcción**, y ninguna `facet:`
     puede recuperarla. Medido: 306 resultados con `database:astronomy` contra 6946 sin él, y
     `title:"noisy ICA"` en **cero** bajo el fq. Se declara `search_fq:` en la entrada del tema
     (`null` = no acotar, a propósito). ⚠ No es un permiso para sacarlo en `objective.yaml`: sin fq
     el top por citas de esa misma query es software de genómica y guías de cardiología.
   - **c2. Sugerir ramas no pedidas.** Con lo que vuelve del `--probe`, si aparece consistentemente
     una familia vecina que el usuario no nombró, **preguntarla** (*"apareció mucho NMF — ¿entra en
     este tema o es otro?"*). Es información que sólo existe después de mirar papers reales, y
     callarla deja el tema recortado por un término que nadie decidió.
   - **d. Persistir.** Recién entonces escribir/actualizar la entrada en `vault/config/themes.yaml`:
     `title`, `area` (abierta: cualquiera; idealmente una de `concept_areas` de `objective.yaml` —
     ej. `methods|hypotheses`, o la que tu bóveda declare — para que el typo-check la reconozca; si es un área
     nueva real, agregala a esa lista), `concept` (nota destino, existente o
     a stubbear), `query` (la Solr cruda aprobada) y `aliases` opcional. Si el tema ya existía en el
     YAML, ofrecer reusar la query guardada o re-pulirla.

1b. **Tema de MÉTODO: acordar la faceta propia (D-26).** Un tema de método —estadística, ML,
   signal processing— **no se clasifica con la lente global**, y no por falta de ajuste: con
   `require: [rv]` la lente mata al paper **fundacional** (Hyvärinen no menciona RV ni una vez), y
   sin filtro *"independent component analysis"* devuelve miles de papers de fMRI, EEG y finanzas.

   La entrada del tema en `themes.yaml` lleva entonces su propia regex, y la regla pasa a ser
   `core = facet propia Y (puerta 2 OR puerta 3)`:

   | Puerta | Qué mira | Para qué sirve |
   |---|---|---|
   | 2 · fundacional | `citation_count >= fundacional_min_citas` | el paper que funda el método, aunque no toque astro |
   | 3 · lente astro | `relevance.facets` de `objective.yaml` | la aplicación del método en astro, aunque tenga 3 citas |

   **Proponé la `facet:` en prosa y mostrala antes de buscar**, igual que la query: es la otra
   mitad de lo que decide el corte. Y **`fundacional_min_citas` se acuerda con el usuario o no se
   pone**: el número depende del campo (30k citas es normal en ML y muchísimo en astro) y el
   framework **no tiene default** — sin declararlo la puerta 2 no abre y el motivo queda en
   `why_excluded`, visible en el apéndice "Excluidos por el filtro". ⚠ Está anotado en
   `vault/STATUS.md` como **decisión abierta** si la puerta 2 debe existir: usala sólo si el
   usuario la pide.

   Tras la corrida, la cadena imprime el delta (`regla del tema (D-26): +N core / -M`). **Miralo**:
   si sacó papers que esperabas, la `facet:` está muy angosta.

1c. **La puerta 1 (`lo cita tu corpus`) llega como CANDIDATOS, no como core.** Si existe
   `build/citation_index.json`, los papers que la regla del tema dejó afuera pero que **tu corpus
   cita** aparecen en `candidates` con `via: citado-por-corpus` y la lista de quiénes los citan.
   Es la señal que ninguna regex puede expresar —Hyvärinen tiene ~30k citas casi todas de fMRI, y
   lo que lo vuelve *tuyo* es que tu gente lo cita— y por eso **la juzgás vos** con
   `python scripts/triage.py <slug>`, como cualquier candidato. El índice se construye aparte
   (`python -c "import sys; sys.path.insert(0,'scripts'); import citation_index; citation_index.build()"`),
   es caro (red sobre todo el corpus) y vive en `build/`; sin él, la puerta simplemente no aporta.

2. **Cadena mecánica** — un solo comando (desde la raíz del repo):
   ```bash
   python scripts/ingest_theme.py <slug>
   ```
   El orquestador despacha según el campo `source` de la entrada del tema (`ads` si falta). En modo
   ADS corre la cadena de estrellas **sin `fetch_ground_truth`** (no hay NEA para un tema) y con
   `--theme` donde aplica; **el orden canónico vive en el header de `scripts/ingest_theme.py`** —
   puntero, no copia: no lo repliques acá ni en otros docs. Todo idempotente (si algo falla se
   re-corre, o se corre el script puntual con sus flags finos).

   ⛔ **La mecánica de la cadena se describe en UN solo lugar (#67):**
   `.claude/skills/ingest-star/reference/cadena-ads.md` — el mismo archivo que apunta `ingest-star`,
   porque es **la misma cadena**: la **guardia de expansión**, el citation chaining, el rate limit de
   `fetch_arxiv`, la cascada de `fetch_pdf` con su fallback, el residuo `build/<slug>/missing_pdf.json`
   (y su rescate manual, en `.claude/skills/ingest-star/reference/rescate-pdfs.md` — "bajar por DOI"
   solo **no** alcanza), los dos chequeos de `extract_fulltext`, `check_retractions` y `extra_core`
   como curación persistente. Antes había una copia acá y otra en `ingest-star`: dos lugares donde
   corregirla y uno donde olvidarse.

   Lo que es **del tema** y no está allá: `query_ads --theme` escribe el mismo
   `build/<slug>/ads.json` (con `kind: theme`), así que `fetch_arxiv`, `fetch_pdf` y
   `extract_fulltext` corren sin cambios; y el **citation chaining va anclado a la query del tema**
   (references/citations de los core filtrados por la propia query → recall extra sin traer los
   mega-citados genéricos del área), no al sujeto como en una estrella. El `extra_core:` del tema va
   en su entrada de `vault/config/themes.yaml`, con la misma forma dura (`{bibcode, via, fecha,
   motivo}`, D-58) que en estrellas.

3. **Extracción LLM — se leen TODOS los core, y el recorte se DECLARA (D-13).** *"Leer los papers
   clave del tema"* no es un criterio: no dice cuántos, ni en qué orden, ni deja registro de qué se
   leyó. Un tema tiene el mismo problema que una estrella —la lente marca N core y la extracción lee
   unos cuantos— y encima **la misma red ya construida**, así que rige igual acá:

   - **Default: se leen todos los core.**
   - **En qué ORDEN se leen** — si son muchos, el orden decide qué queda afuera, así que no lo decide
     el `glob`:
     ```bash
     python scripts/triage.py <slug> --prioridad
     ```
     Lista los core ordenados por **cuántas facetas del objetivo toca cada uno** (citas como
     desempate). Acá el orden importa más que en una estrella: en un tema de método conviven
     fundamentos y aplicaciones astro por diseño, y el `citation_count` solo ordena por campo (30k
     citas es normal en ML y muchísimo en astro), no por pertinencia a esta bóveda. ⛔ No filtra ni
     toca la lente: ordena lo que **ya** es core.
   - Si no se leen todos, **se avisa al usuario** y el motivo queda **registrado**:
     ```bash
     python scripts/triage.py <slug> --extraccion subconjunto --reason "<el criterio>"
     python scripts/triage.py <slug> --extraccion todos          # el default del contrato
     ```
     El `--reason` es obligatorio por el mismo motivo que en `--drop`: en seis meses lo que sirve es
     el criterio, no el rótulo `subconjunto`. Sin la declaración, el lint lo reporta como *recorte de
     lectura sin declarar*.

   Con eso resuelto, la lectura —y si el recorte es inevitable, los que primero entran son los
   **fundacionales / árbitros / metodológicos**—: desde `vault/raw/pdfs/<slug>/` (#205: se lee el PDF; el `.txt` de `vault/raw/fulltext/<slug>/` es el índice para ubicar), poblando cada `vault/wiki/papers/<bibcode>.md`: `methods`,
   `role` (#73: `fundacional` introduce el método/mecanismo · `aplicacion` lo instancia en un caso · `arbitro` reanaliza y resuelve una tensión previa — sale de leer el paper, la regex del clasificador no puede inferirlo, y sin él contrastarlo contra otro no está definido) —especialmente agudo en temas de método, donde fundamentos y
   aplicaciones astro conviven en el mismo concepto por diseño—, `thesis_links` (ya pre-sembrado al
   concept; agregar otros si toca) y la sección
   `## Vista — <concept>` enfocada **en el eje del tema** — el stub la trae ya ramificada por tipo
   de sujeto (#76): *aporte al tema* (definición, mecanismo/ecuación, método, signo) y *régimen de
   validez*, no planetas ni actividad de una estrella concreta.
   ⛔ **Es UNA VISTA, no «la extracción del paper» (#188)**: el mismo paper leído desde una estrella
   da otra. El sujeto de la vista es el **`concept`** (lo que el paper declara en `thesis_links`),
   no el slug del tema. Cosechá con `python scripts/harvest_views.py <slug> --theme`, que estampa
   `fecha`/`txt`/`lente`, mergea add-only y corre `is_extraction` (INV-103) — cosechar a mano pisó
   13 notas terminadas con salidas de `verify-citations`, que también traen `bibcode`.
   ⚠ **`pdf_source` antes de copiar un número** (#57): con `eprint` el `.txt` es el **preprint**
   (un `v1` pre-referato puede traer otros valores que el publicado que identifica el bibcode), y con
   `null` no se sabe —que **no** es "publicado"—. Un valor que choca con el ground-truth o con el
   abstract de ADS es candidato a **diferencia de versión**: abrí el PDF publicado o dejá la
   salvedad en la nota. `verify-citations` lo detecta después; **acá es donde el número entra a la
   bóveda**.

3b. **Retro-tag del corpus pre-existente (grep por aliases).** Los papers que la query ADS devolvió
   pero **ya estaban** en el corpus quedan conectados solos (`make_notes` mergea add-only el seed
   `thesis_links` en la nota existente, sin pisar su extracción). Lo que la query **no** devolvió se
   caza por grep: buscar los `aliases` del tema sobre el fulltext de **todo** el corpus (los otros
   slugs), p. ej. `grep -rilE --include="*.txt" "gaussian.process|gpr" vault/raw/fulltext/`, y para cada
   hit sin taguear leer el contexto y decidir si el paper **usa/aporta** al tema (no mención al
   pasar) → agregar add-only `thesis_links` (y `methods` si aplica) a su nota. El roll-up del concept es una tabla
   **estampada**: junta también por `methods:` sin re-taguear, pero **no acumula sola** — al
   terminar el retro-tag hay que re-correr `python scripts/make_notes.py <slug> --theme`.
   ⛔ **El retro-tag NO escribe vistas, y es a propósito (#188).** Tagear es declarar un
   **reclamo**: nadie leyó ese paper desde este tema todavía. El lint lo reporta como *reclamado sin
   vista* (backlog) — hacé la vista (`extraction_prompt.py <slug> <bibcode> --theme` + cosecha) o
   declarala con `no_vista: [{sujeto, motivo}]` si el paper sólo aporta al roll-up. Es justo la
   población medida: **141 de 908** notas retro-linkeadas sin una segunda lectura.
   **Alias sueltos y cortos, nunca frases** (#44, convención canónica en `verify-citations`): el
   `.txt` entrelaza dos columnas en la misma línea física (73% del corpus) → un alias multi-palabra
   (`"gaussian process regression"`) puede no matchear aunque el paper lo use. Probar la raíz corta
   y el guión de corte antes de dar por no-taguable un paper; un 0 acá **no** es "el tema no está",
   es un retro-tag que no se hizo.

3c. **Contraste cross-paper (#72) — antes de escribir la síntesis.**
   ⛔ **Usá `python scripts/contrast.py <slug>` — no improvises un digest (#314/#317).** Es el único
   eslabón de la cadena que no tenía herramienta, y su modo de falla está medido: leer 32 JSON de
   ~25 KB lleva a imprimir un resumen recortado, el recorte cae **dentro de la cita textual** y el
   modelo la completa con lo plausible. **2 citas fabricadas sobre 139 pares**, las dos en el
   carácter exacto del corte, y una invirtiendo el alcance de la afirmación. La herramienta agrupa
   por campo (`--campo`, `--grep`, `--eje`, `--paper`), arrastra `linea` y `segunda_mano`, emite
   filas de **una fuente cada una** (`--filas`) y **nunca trunca una cita**: si no entra, filtrá
   menos filas.
   ⛔ **La fila sale de `--filas` CON EL VALOR ADENTRO: no lo re-tipees (#322).** Los 12 verdaderos
   positivos medidos son errores de **copiado** —6 de atribución (la frase de un paper bajo otro), 6
   de cola alterada—, **ninguno** de comprensión: o sea, de mover una cadena de un archivo a otro,
   que es lo que un script hace perfecto y un LLM mal. Vos escribís **la glosa** y elegís qué filas
   entran; la cadena y su `[[bibcode]]` vienen de la máquina. Si la cita no entra en la
   celda, se **parafrasea SIN comillas** — nunca se recorta entre comillas. Y **una fila, una
   fuente**: agrupar bibcodes bajo una glosa compartida es cómo se fabrican atribuciones.
   ⛔ **Las comillas de la celda son las del EXTRACTOR: el script no pone ninguna (#330).** `valor`
   no es «la cita»: es lo que escribió el extractor, y llega en tres formas — **entre «»** (es cita
   textual), **con «» adentro** (glosa del extractor **con** la cita adentro: la glosa NO es del
   paper) y **sin «»** (dato de tabla o prosa: **no es verbatim, y no se entrecomilla al pegarlo**).
   Envolver las tres publicaba como palabras del paper 1262 de 1948 valores medidos —315 de ellos la
   glosa en castellano de un LLM— y doblaba 686 en `««…»»`, que además se caen de la población del
   gate de #323. El banner de `--filas` dice cuántas de cada forma emitió la corrida.
   Entre "leí los papers" y
   "escribo la síntesis" hay una operación, y es la de más apalancamiento de la cadena: armar el
   **`## Inventario por eje`** del concept. Una fila por paper para cada **eje** —parámetro, efecto o
   hecho— donde los papers **no coinciden** (`Eje | Paper | Dice | Método / baseline`). Los ejes con
   acuerdo unánime **no entran**: misma regla de poda que la prosa.
   ⛔ **Sin columna "valor adoptado" ni "por qué".** Adoptar un valor es **decidir por el
   consumidor** y rompe el flujo unidireccional de la regla #0: la bóveda reporta el **estado de la
   literatura**. La lectura propia va aparte y marcada `inferencia`.
   ⚠ **Mirá el `role` (#73) antes de leer dos filas como desacuerdo:** fundacional↔aplicación **no
   es contraste, es instanciación** — y en un tema de método eso es el caso NORMAL, porque
   fundamentos y aplicaciones astro conviven en el mismo concept por diseño. El `arbitro` no es una
   fila más: es el que resuelve.
   Sin esto, tres papers con tres valores del mismo efecto terminan en una frase con un solo
   `[[bibcode]]` y se evapora que los otros dos existen — que es exactamente lo que el concept
   promete responder sin abrir un paper. La red de que el contraste ocurrió es #75 (*extraído pero
   no sintetizado*).
   ⛔ **Y este paso es el PRODUCTOR de los ejes del tema (#310), no un resumen.** Un eje sólo existe
   al poner las vistas una al lado de la otra: acá nace el vocabulario del tema (medido en una
   ingesta real: 6 ejes y 43 filas, ninguno declarado antes de leer; el mismo término nombrando
   **cinco objetos distintos** y el alias central significando dos operaciones según la escuela).
   ⚠ **Por eso los ejes NO se declaran antes de leer**: un tema se ingesta normalmente porque no se
   lo conoce, y pedirlos antes es pedir la respuesta que la operación existe para producir — encima
   **cierra hallazgos**, porque los dos más valiosos de esa ingesta salieron de extractores libres de
   contestar algo que nadie preguntó.
   **Cerrá el paso PROPONIENDO los `ejes:` del tema** para que el usuario los apruebe y los edite en
   `themes.yaml` (#307) — proponer, no escribir: la config es curada, y un script (o un agente) que
   la edita solo convierte una decisión en un efecto colateral. Con ellos declarados, la lectura
   siguiente pregunta lo que el tema necesita, y una segunda pasada sobre el mismo corpus es un
   **modo** (`--enfasis`, #308), no una re-ingesta.
   ⚠ **Lo que NO se propaga solo, y es deliberado:** la vista nueva va sola a la nota del paper y al
   roll-up, pero **no** a la prosa de la ficha — reescribir un bloque **vence las anclas** de los
   pares que vivían ahí (D-4/D-20) y obliga a re-verificar lo tocado (#203), que con #282 no
   converge solo. La síntesis se re-escribe leyendo, como siempre.
4. > ⚠ **Un ítem de linaje = un BULLET propio, no una oración con seis citas.** ⚠ Y su simétrico
> (#316): un párrafo que **contrasta** dos fuentes legítimamente las cita a las dos — lo que no
> puede pasar es que una **cita entrecomillada** quede sin su `[[bibcode]]` al lado, porque ahí el
> chequeo no sabe de quién es y la prueba contra todas (la convención es `«…» [[bibcode]]`).
> ⛔ **«Al lado» es literal (#325):** entre la cita y su link sólo puntuación y, si va, el paréntesis
> del localizador — con prosa en el medio el chequeo declara ambigüedad, y una **mención** posterior
> («…atribuyendo eso a [[X]]») ya no se lleva la atribución. En una fila manda la columna *Fuente*. Cuando enumeres
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

**Síntesis del concept durable** (`concepts/<area>/<concept>.md`). Destilar lo aprendido a la
   página viva: mecanismos, signos, desfasajes, regímenes, huecos. El roll-up estampado (papers con `thesis_links:
   <concept>` **o** `methods: <concept>`) se regenera con `python scripts/make_notes.py <slug> --theme`
   — no acumula solo. **Citar los papers clave por `[[bibcode]]`** en la prosa
   (además de trazabilidad, da links entrantes → no quedan huérfanos).
   ⛔ **Una ECUACIÓN que va a la nota se levanta del PDF, no del `.txt`, y viaja con su página.**
   El `.txt` puede haber vaciado la fórmula, haberla dejado con el cuerpo **cambiado** o no haberse
   podido medir — y **dos de los cuatro casos medidos se veían perfectos**: `si = 1` donde el paper
   dice `si = ±1` (el supuesto binario **es** el ±1) y «model (8)» donde dice «model (3)». Una
   borradura no se ve, así que la regla no puede ser *«si se ve bien, copiala»*. Sí se acota por
   **carga**: la ecuación del método, la del contraste o la condición de identificabilidad van al
   PDF; una constante auxiliar citada al pasar, no.
   Si la vista del paper ya trae la fórmula **con su página**, el chequeo está hecho y se copia con
   esa procedencia. Si llega **sin** página, nadie la verificó: abrí el PDF acá.

   Dos secciones del template que **son de un concepto** y hay que llenar acá, no dejarlas vacías:
   - **`## Régimen de validez` (#74).** El modo de falla dominante de un concepto **no** es "dos
     números no coinciden" sino **generalizar de más**: el paper afirma X bajo condiciones C (SNR,
     muestreo, tamaño de muestra, definición del observable) y el concepto termina afirmando X
     pelado. `verify-citations` **no** lo agarra —la afirmación pelada sí está en el paper, así que
     vuelve `soportada`—, por eso la condición se escribe acá: una fila por afirmación
     condicionada (`Afirmación | Vale bajo | Fuente | Rol`). Es el destino de los desacuerdos que
     resultan **`aparente`** (distinto régimen, distinta definición, distinta época): en una
     estrella eso se descarta como no-disputa, en un concepto **es el hallazgo**. De la tabla sale
     un hueco accionable propio: **"régimen no cubierto"** → a `## Huecos`.
   - **`disputes` (#71), sólo para el desacuerdo REAL bajo las mismas condiciones.** Acá la disputa
     es **simétrica por definición** (no hay ground-truth que arbitre, así que ninguna posición es
     "la verdad"): `field` nombra el eje y cada posición dice quién la sostiene (`{ref, value}`).
     Si el desacuerdo se explica por el régimen, **no** es una disputa: es una fila de la tabla de
     arriba. Una posición sola no es desacuerdo — es una afirmación, y va a la prosa citada (el
     lint bloquea las disputas con menos de dos posiciones).

5. **Auto-revisión de autosuficiencia (semántica).** Releer el concept como un agente externo que
   **sólo tiene ese archivo**: ¿se entiende el tema sin abrir ningún paper? Si para responder algo hay
   que abrir un paper, falta en el concept → agregarlo. (El único proxy estructural de `lint.py` acá
   es *extraído pero no sintetizado* (#75): cada paper con `methods` poblado tiene que estar citado
   en alguna ficha o concepto. La suficiencia la juzgás vos, igual que en la ficha de estrella.)
   ⚠ Ese backlog es el que cierra este paso: un paper que pagó la extracción y no aparece citado en
   ninguna entidad es extracción perdida. O lo sintetizás donde corresponda, o declarás por qué no
   va: `no_sintetizado: <motivo>` en su nota (la marca sin motivo se sigue reportando).

6. **Bookkeeping.** Re-estampar el índice —`python scripts/make_notes.py --restamp-index`, #237:
   `index.md` era 100 % Dataview, o sea que no había dónde «agregar el concepto» y el paso no se
   podía cumplir como estaba escrito—, appendear a
   `vault/wiki/log.md`, y `vault/STATUS.md` si cambió el estado. **No** tocar la matriz método×estrella.
   (El `lint` va **después** del verify del paso 6b: `CLAUDE.md` lo pide "antes de lint/commit",
   porque resolver una cita no-soportada suele cambiar la prosa.)

6a. **Cruzar la nota contra las extracciones — `python scripts/contrast.py <slug> --validar-todo`
   (#323).** Obligatorio, con vos todavía en contexto, y **antes** del fan-out: es un `grep` exacto
   que cuesta segundos, mientras el verify son N subagentes leyendo PDFs — mandar a verificar con
   LLM una cita que un `grep` ya sabe alterada es pagar el paso caro para llegar a lo que el barato
   sabía (#315: 32 subagentes y ~4 M tokens para llegar a lo que el lint sabía en segundos).
   Bloquea con **evidencia positiva** (la frase aparece bajo otro bibcode, o el arranque coincide y
   la cola diverge); el silencio de la extracción se declara **no evaluable** y no es hallazgo
   (#321). Medido: la nota que produjo esta serie cerró con verify completo y `lint --cierre` en 0
   con **12 citas alteradas adentro** — la comparación que las cazaba estaba escrita y nadie la
   corría, porque nada decía que había que correrla.

6b. **Verificar citas.** Correr el skill `verify-citations` sobre el **concept** (y las notas de paper
   nuevas). El concept es dual-audiencia e implementation-ready: cada afirmación con `[[bibcode]]`
   —definiciones, ecuaciones, rangos, signos— debe estar respaldada por el fulltext (cita textual +
   página del PDF; sin respaldo ⇒ no-soportada). Resolver cada no-soportada/contradice (bajar a lo
   que dice la fuente, reasignar la cita, o marcar `inferencia`) y dejar el bloque `## Verificación de citas`.

7. **Cierre (commit + push).** Tras la verificación (`python scripts/lint.py --cierre <slug>` en 0 — #121: el
   alcance del exit es **este** sujeto; la deuda de otro se lista pero no frena esta operación), `git add` de los archivos
   **específicos** que tocó la operación (no `-A`) y commitear con mensaje
   descriptivo. Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Modo off-ADS / biblio fuera de ADS (opt-in — **sólo a pedido explícito**)

El foco de Almagesto es **astro**, y su única plomería de **descubrimiento automático** (query →
clasificar → bajar) es de astronomía —ADS, arXiv, NEA/SIMBAD—; por eso un tema, por **default**, se
baja por ADS (los **Pasos** de arriba). Este modo existe para los **métodos de otras disciplinas**
que el trabajo astro usa —análisis de datos, estadística, machine learning, procesos gaussianos,
signal processing— y cuya bibliografía canónica vive **fuera de ADS** (el eje tema/concepto y la
capa de calidad son agnósticos de disciplina, así que la cadena los soporta igual), con la
diferencia operativa de que las fuentes se **declaran**, no se descubren por query. Se permite
**sólo si el usuario lo pide explícitamente** (porque exige esa curación manual de fuentes).
**`ingest-star` no cambia: sigue siendo astro-only.**

### 0b. ANTES de declarar nada a mano: barré los tres backends (#104)

⚠ **`source:` no significa «dónde se busca» (#209).** Es una pregunta que el usuario hace con razón
—*«si busca en todos lados al mismo tiempo, ¿para qué le pongo `source: ads`?»*— y la respuesta es
que el campo nombra **qué cadena corre el orquestador**, no la búsqueda:

| | qué decide | quién lo corre |
|---|---|---|
| `discover.cascade` | **dónde se busca**: ADS + arXiv + OpenAlex a la vez, merge por DOI | paso **a mano** de este skill (`discover.py --theme`) |
| `source:` de `themes.yaml` | **qué ramas de plomería se ejecutan**: `query_ads` + ground-truth, o sólo las `sources:` declaradas | `ingest_theme.py` |

`ingest_theme.py` usa `discover.resolve_pdf` y **nunca** `discover.cascade`, así que la cascada es
este paso 0b y no algo que el orquestador haga solo (#95 sigue abierto como **decisión**, no como
defecto). Lo único que `source:` decide de fondo es una propiedad del **corpus**: *«este tema tiene
papers sin bibcode ADS, así que además de la query hay una lista declarada»*.

⛔ **Este paso tiene red desde #361:** el lint reporta como backlog (`cascada_sin_correr`) el tema
off-ADS o mixto cuyo registro no tiene `descubrimientos`, los tiene vacíos o con un backend que
FALLÓ en todas las corridas. Medido: un tema se cerró con todos los gates en verde sin este paso, y
lo detectó el usuario preguntando «¿falta algo?». Y el anclaje ya no muere con traceback: deja su
fila `anclaje` en la cobertura, con los tres estados.

⛔ **No le digas al usuario "no tengo los fundacionales" habiendo mirado un solo buscador.** Fue un
defecto medido: ADS devuelve **0 de 8** del canon de ICA/BSS y `author:"Hyvarinen, A"` trae dos
papers sobre gotas de ácido sulfúrico (es otro Hyvärinen) — pero OpenAlex los tiene **8 de 8**, con
DOI y conteo de citas. La lista declarada a mano es el **último** recurso, no el primero:

```bash
python scripts/discover.py --topics "<tema en inglés>"      # subtema de OpenAlex (id T…) → `topic:`
python scripts/discover.py --theme <slug>                   # ADS + arXiv + OpenAlex + anclaje
python scripts/discover.py --theme <slug> --seed-terms "noisy ICA,quasi-whitening"   # + la cola especialista
python scripts/discover.py --theme <slug> --rows-por-termino 600   # el slice se pagina: destapa lo que el aviso corta (#294)
python scripts/discover.py --resolve 10.1016/…              # ¿hay copia libre de ese DOI?
```

⛔ **Para un tema de método, preguntá por `seed_terms` (#210).** Los cuatro ejes de arriba rankean
por citas, y eso tiene un **piso**: los papers especialistas de un tema viven entre **11 y 72
citas** dentro de un topic de 169.988 works, o sea que **ningún corte por citas los toca**. El eje
que sí los alcanza es el **slice de texto por término dentro del topic**, y está medido: la
recuperación pasa de **7/18 a 13/18** con el universo de candidatos de **776 a 2521**. Ése es el
canje —cobertura contra costo de triage— y **se decide por tema**, por eso es opt-in. Los términos
son **curación**: el vocabulario especialista que la query general no trae (para ICA: *noisy ICA*,
*quasi-whitening*, *identifiability*). Se declaran en `seed_terms:` de la entrada del tema
(`themes.yaml`) y el flag los pisa para probar. Medido en una ingesta real: sin este eje se
perdieron exactamente esos 10 papers, y la cobertura ahora lo declara *NO CORRIÓ* en vez de callarlo.

**Leé la cobertura que imprime**, no sólo la lista: distingue *corrió con N*, *FALLÓ* (0 por caída,
que **no** es "no tiene nada del tema") y *NO CORRIÓ* con el motivo. Vale también para `--topics`,
que declara sus dos ceros (#290): *«la taxonomía de OpenAlex no tiene nada que matchee esa frase»*
(probá una más general, o dejá `topic:` sin declarar) y *FALLÓ* (volvé a correrlo) piden lo
contrario. Y declará `topic:` en la entrada del tema: sin él, la mitad OpenAlex se infiere del
`title` y con títulos en castellano no matchea la taxonomía inglesa.

⛔ **Declará los EJES DE LECTURA del tema si no son los de la bóveda: `ejes:` (#307).** El extractor
pregunta por los ejes de `relevance.facets` salvo que el tema declare los suyos — y para un tema de
método eso es preguntar los ejes de una bóveda astro: medido, 4 de 8 ejes vacíos en 25 de 32 papers,
y los ejes que el tema necesitaba (identificabilidad, heterocedasticidad por época y por canal)
**no se preguntaron nunca**, así que volvieron desparramados en `aporte` y sin clave con la que
compararlos entre papers. Preguntale al usuario qué quiere saber de este tema **antes** de la
extracción: eso es la lista. Tres estados: sin declarar hereda las facetas globales, declarado son
ésos, `ejes: []` es la decisión explícita de no preguntar ejes.

⚠ **Y una SEGUNDA lectura del mismo corpus con otra lente se pide, no se escribe a mano (#239/#308):**
`python scripts/extraction_prompt.py <slug> <bibcode> --theme --enfasis "<lente>" --ejes a,b`. Es el
flujo de una bóveda viva —lo que se aprende define qué había que haber preguntado—: la vista anterior
**no se pisa** (conviven como sub-secciones de la misma `## Vista`), el prompt manda leerla primero
para no re-narrarla, y rehúsa si `(sujeto, enfasis)` ya tiene lectura.

⛔ **`topic:` acepta una LISTA, y para un tema que cruza disciplinas hay que usarla (#293).**
Medido: la familia del blanqueo heterocedástico está repartida en **cinco** topics, y el mismo
trabajo cae en topics distintos según sea preprint o publicado — con un solo topic, cuatro quintos
son inalcanzables hagas los `seed_terms` que hagas. `--topics` te muestra los candidatos; declarálos
todos los que correspondan (`topic: [T11447, T10500]`, se buscan en OR). ⚠ Y el slice **decide por
término** si el topic aporta: con el conteo sin filtro a la vista, un término específico
(`HeteroPCA`: 9 works en todo OpenAlex) corre **sin** topic —el filtro ahí sólo puede sacar señal—
y uno ambiguo (`gaussian moments`: 13.396) lo mantiene. La pantalla lo declara término por término.

⚠ **Si el aviso dice que el slice tiene más de lo que trajo, se puede destapar (#294):**
`rows_por_termino:` en la entrada del tema (o `--rows-por-termino`), que ahora **pagina** — el
backend topea en 200 por request. Medido: dos papers del gold standard se perdían sólo por ese
techo, los dos exactamente de la cola especialista que este eje existe para alcanzar.

⚠ **El orden importa y está medido:** `search` + orden por citas sobre OpenAlex devuelve 143.450
works cuyo top 30 es AlphaFold y guías de cardiología (**2 de 30** en tema). Filtrando por
`topics.id` **primero**, el canon entra al top 25. Rankear sin filtro estructural amplifica.

**Y lo que más rinde: anclar en la mitad astro del propio tema.** Una vez que la cadena bajó los
papers ADS del tema, sus **listas de referencias** traen el canon rankeado por cuántos de ellos lo
citan (`discover.anchored_records`). Medido sobre 19 papers astro de ICA: devolvió los **ocho**
canónicos sin declarar nada, y ordena mejor que las citas globales. Es además lo único que alcanza
lo que ninguna keyword del tema alcanza — en ICA, la familia de **PCA con ruido** (el blanqueo), que
un barrido por "independent component analysis" nunca ve.

⛔ Todo esto **propone**; no clasifica. Lo no-astro va al **triage** como candidato (INV-24: core
sigue siendo función de `(paper, lente)`), y `--resolve` propone una URL sin tocar `sources:`.

Qué cambia respecto del flujo ADS de arriba:
- **La mitad astro puede seguir descubriéndose:** si el tema es **mixto**, poblá `query:` **además**
  de `sources:` y el orquestador corre el descubrimiento ADS **completo** para esa mitad (misma
  lente, mismas puertas, misma compuerta de triage). Sin `query:`, la mitad astro entra sólo por los
  bibcodes que enumeres en `extra_core:` — medido en ICA: 11 papers a mano contra familias enteras
  que la query encuentra sola.
- ⛔ **Y `sources:` puede quedar VACÍA en la primera corrida (#211).** Es el orden que este mismo
  skill prescribe: el paso 0b manda barrer los tres backends **antes** de declarar nada a mano, y el
  **anclaje** —lo que más rinde— necesita la mitad ADS ya bajada. Así que la primera corrida de un
  tema mixto es `query:` poblada + `sources: []`, se declaran las fuentes off-ADS después, y se
  vuelve a correr (la cadena es idempotente). El orquestador aborta sólo si el tema no tiene
  **ninguna** vía de papers (ni `sources:`, ni `query:`, ni `extra_core:`) y **avisa** cuando corre
  sólo la mitad ADS, para que no se lea como que corrió todo. Hasta 1.76.2 el guard abortaba con
  `sources:` vacía, o sea medía la premisa que #104 rompió, y el orden de arriba era un **deadlock**.
- **Sin ADS (si `query:` queda en null):** se saltean `query_ads.py`, `fetch_arxiv.py`, `fetch_pdf.py` y `fetch_ground_truth.py`. En
  `vault/config/themes.yaml` la entrada lleva `query: null`, el switch **`source: web | local-pdfs |
  local-pdfs+web`** y la bibliografía **declarada** en la lista `sources:` (cada item: `key`
  AAAA+Autor + `url` o `pdf` + `title/author/year/venue/n_authors/doi` opcionales; ver header del YAML); el resto
  del schema igual (`title`, `area`, `concept`, `aliases`). Con eso, **el mismo comando del paso 2**
  (`python scripts/ingest_theme.py <slug>`) orquesta todo: stub del concept, `fetch_web.py` por cada `url`,
  copia de cada `pdf` a `vault/raw/pdfs/<slug>/<key>.pdf` (nota con el campo `pdf` ya linkeado) y
  `extract_fulltext.py`. `--force` re-baja/re-copia **fuentes**, nunca pisa notas. Los bullets de
  abajo documentan las piezas por si hay que correr algo a mano.
- **Fuente = PDFs locales y/o web:**
  - **PDFs** que provee el usuario → copiarlos a `vault/raw/pdfs/<slug>/` (git-lfs) renombrados a la **clave de
    cita** (abajo); `python scripts/extract_fulltext.py <slug>` los pasa a `vault/raw/fulltext/<slug>/` (es
    source-agnostic: sólo corre `pdftotext`).
  - **Web** (rellenar fundacionales / huecos) → **preferido:** `python scripts/fetch_web.py <slug> <clave> <url>
    [--concept <concept> --title … --author … --year …]`. Baja la página con **defuddle** (quita
    nav/menús/clutter → markdown limpio, ~8× menos bytes que el HTML crudo, ~4× menos que pandoc), le pasa
    un **post-clean** determinista (saca bloques HTML de media/embed sueltos) y escribe el **snapshot**
    `vault/raw/fulltext/<slug>/<clave>.txt` con el encabezado **URL + fecha de acceso** ya puesto (citable y
    verificable por `verify-citations`). **Además crea el stub `vault/wiki/papers/<clave>.md`** (salvo
    `--no-note`). Requiere Node/npm (`npx defuddle`, JS-only; valida `<clave>` contra `BIBCODE_RE`,
    idempotente salvo `--force`). **Sin Node:** traer con `WebFetch`/`deep-research`, guardar el snapshot a
    mano (mismo encabezado) y stubbear la nota con `python scripts/make_notes.py --web <clave> --url … --concept …`.
- **Fuente no-conseguible (fallback — paywall / escaneo / mojibake):** si una fuente no se puede
  obtener (sin copia libre) o su PDF no rinde texto usable (escaneo sin capa de texto, fuentes sin
  ToUnicode → `extract_fulltext` avisa "ILEGIBLE"; con `tesseract` instalado **cae solo a OCR** y el
  `.txt` queda `source: ocr`, citable con salvedad — ver docs/operacion.md), **no frenar el ingest ni dejarla
  muda**: marcá el
  item de `sources:` con `pending: paywall|scan|unextractable` (dejando `url`/`doi` conocidos como
  puntero). La cadena stubbea la nota con `pending_source`, la **deriva al usuario** en el aviso
  final y el lint la lista como precondición. El resto del tema se arma igual con las fuentes
  limpias; la pendiente queda como hueco citado. Cuando el usuario provea el PDF/fuente: reemplazar
  `pending` por `pdf:`/`url:`, re-correr la cadena (idempotente) y completar la extracción.
- **Fuente evaluada y RECHAZADA (#81):** `sources:` registra lo que **aceptaste**; "miré este libro
  / esta URL y decidí que no es core" no queda en ningún lado si no lo escribís. Es el mismo juicio
  no regenerable que el del triage, en el otro carril — se pierde igual al cambiar de máquina o al
  volver seis meses después. Registralo en las **mismas `decisiones`** del registro versionado:
  ```bash
  python scripts/triage.py <slug> --drop-source <clave> --reason "<motivo>" --pointer <url|doi>
  ```
  No necesita `ads.json` (un off-ADS puro no lo tiene). Queda con `origen: fuente-declarada`, y si
  más adelante volvés a declarar esa clave en `sources:` la cadena **avisa** con el motivo antes de
  bajarla (avisa, no frena: quizá cambiaste de opinión a propósito). `python scripts/triage.py
  <slug>` sin `ads.json` lista lo registrado. **No cures en silencio:** el `--reason` es obligatorio.
- **Clave de cita sintética (papers sin bibcode ADS):** `AAAA+Autor` (p. ej. `2006RasmussenWilliams`,
  `2006Tichavsky`, `2025sklearn`). Debe **empezar con `AAAA`+letra** (lo exige `BIBCODE_RE` del lint) y
  coincidir con el nombre del `.txt`.
- **Tema MIXTO — papers del tema que SÍ tienen bibcode ADS** (un método no-astro casi siempre tiene
  aplicaciones/variantes publicadas en revista astro): van en **`extra_core:` (lista de mapas `{bibcode, via, fecha, motivo}` — D-58; el `triage` imprime el snippet listo para pegar)** de la
  entrada del tema, **no** en `sources:` con el bibcode como `key` (eso degrada el stub: metadata a
  mano, `citation_count: 0`, blockquote off-ADS factualmente falso). `ingest_theme.py` les corre solo
  la **sub-cadena ADS** (`query_ads --extra-only` → `fetch_arxiv` → `fetch_pdf` → `make_notes
  --theme`): stub con metadata ADS real, PDF por arXiv/resolver y chequeo de retracciones por la vía
  ADS. El tema queda mixto: `sources:` para lo off-ADS + `extra_core:` para lo que está en ADS.
  **Incluye los que ADS indexa fuera de `database:astronomy`** (eprints de `math.ST`, `eess.SP`,
  `stat.ML`…): la búsqueda por bibcode de `extra_core` corre **sin la lente astro** (#68), así que un
  paper de estadística/ML con bibcode ADS real entra por acá con su identidad ADS. Si un bibcode
  igual no vuelve, ahí sí es typo o registro renombrado — no hace falta degradarlo a `sources:`.
- **Notas de paper (automatizado):** `fetch_web.py` ya crea el stub `vault/wiki/papers/<clave>.md`; para
  fuentes **PDF** off-ADS (sin URL) usá `python scripts/make_notes.py --web <clave> --concept <concept>
  --slug-hint <slug> [--title … --author … --year … --n-authors … --doi … --venue …]`. El stub lleva el
  **mismo frontmatter** que
  una nota ADS más la provenance web: `bibcode` = clave sintética; `arxiv_id` null; `n_authors`/`doi` los
  del item de `sources:` si se declararon (un PDF con DOI sigue siendo off-ADS; con `doi`,
  `ingest_theme.py` corre además `check_retractions.py`); `source_url` +
  `accessed` (la **fecha del snapshot** — el "Retrieved <fecha>" de una cita web, la toma del `.txt`);
  `bibstem` = venue o dominio; `pdf`: null para un snapshot web (el respaldo es el `.txt`), pero
  **linkeado** si el PDF ya se copió a `vault/raw/pdfs/<slug>/` (fuente `local-pdfs`: verdad de
  disco, y así el chequeo PDF↔disco del lint no marca drift); `stars: []`; `thesis_links`
  al concept; `tags: [paper, web]` (snapshot de URL) o `[paper, local-pdf]` (PDF provisto).
  Completar la extracción LLM a mano.
- **Todo lo demás igual:** extracción enfocada en el eje del tema, síntesis al concept durable,
  auto-revisión de autosuficiencia, **`verify-citations`** (la clave sintética y el snapshot `.txt` la
  hacen chequeable), **`lint`** (0 bloqueante) y bookkeeping. **La frontera dura (regla #0) sigue
  rigiendo:** sólo bibliografía citable; nada de implementación de quien consume la bóveda.

## Notas
- Reglas de notación/reporte y schemas de frontmatter: ver `CLAUDE.md`. Notación matemática en `$...$`,
  filenames kebab-case (papers usan el bibcode), links internos `[[wikilink]]`.
- Distinción concept vs query: el concept es el resultado **durable** del tema (acumula solo). Una
  *query* archivada (`queries/`) es un snapshot complementario — opcional, sólo si vale re-preguntarla.
- **Lectura del fulltext (saltar afiliaciones):** los `.txt` arrancan con autores/afiliaciones que no
  aportan. Ubicar el contenido en el índice con, p. ej., `awk 'tolower($0)~/abstract/{f=1} f' vault/raw/fulltext/<slug>/<bib>.txt | head -60`
  y `grep -inE "bisector|BIS|FWHM|S-?index|chromatic|correlat|lag" ...` para los números clave. No
  tocar el `.txt` en disco (se usa para grep); el salto es sólo en la lectura.
