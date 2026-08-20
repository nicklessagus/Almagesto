# Estado de la bóveda

Punto de entrada: dónde está el proyecto y qué sigue. Vive en el repo (sincroniza entre máquinas).
Para *cómo* operar ver `CLAUDE.md`; para el historial ver `vault/wiki/log.md`; catálogo en `vault/wiki/index.md`.

## Estado actual

- Bóveda **recién instanciada** desde el template **Almagesto** (patrón LLM Wiki).
- **Objetivo:** ver `vault/config/objective.yaml` ← **editar este archivo primero** (define de qué trata la
  bóveda y qué papers son "core").
- Sin estrellas/temas ingestados todavía.

## Próximos pasos

1. Definir el objetivo con el skill `setup` (se lo pedís al agente en palabras; genera/afina
   `vault/config/objective.yaml` con su `relevance.topics` — editable a mano si preferís).
2. Poner el token ADS en `vault/config/ads_dev_key` (o `ADS_DEV_KEY`).
3. Agregar tu primera estrella a `vault/config/stars.yaml` (o tema a `vault/config/topics.yaml`) y correr
   `ingest-star` / `ingest-topic`.

## ✅ Framework 1.7.0 (2026-08-19) — tanda #49/#50: lo que el verify no miraba y el rescate de PDFs

> Disparada por la primera corrida real sobre una ficha grande (17 fuentes, ~110 pares) en
> Almagesto-RV. 351 tests verdes (+5), lint 0. `ALMAGESTO_VERSION` 1.6.3 → **1.6.4** (#49, patch:
> sólo skills) → **1.7.0** (#50, minor: claves nuevas en `missing_pdf.json` + umbral de legibilidad
> por página, retrocompatible).

- **#49** — `verify-citations` 1.3.5 → 1.3.6, dos agujeros medidos: (a) **herencia de cita en tablas
  y listas** — la fila hereda el `[[bibcode]]` del ámbito que la introduce (caption → párrafo →
  encabezado) y entra al fan-out como par propio; antes no se formaba el par y la tabla entera se
  cerraba sin chequear (medido: **46 de 64 filas, 72%**). (b) **Completitud de transcripciones** —
  campo `completitud` + addendum de prompt: una tabla transcrita sin un solo error pero **truncada**
  volvía 100% soportada (medido: 14 registros correctos sobre una tabla de **21 filas**). Es un modo
  de falla distinto del *grounding gap*: la nota no afirma falso, **afirma de menos**.
- **#50** — **cascada de rescate de PDFs** escrita y canónica en `## Notas` de `ingest-star`
  (Messenger abierto → página de papers del instrumento → mirrors → tablas del CDN → derivar al
  usuario), con la excepción **aanda.org / DataDome** (no gastar intentos). El resolver de ADS falló
  en **5 de 17** en un ingest real; 4 se recuperaron por esas ramas. `fetch_pdf` imprime el
  **bibstem** de cada fallo con la rama sugerida (`rescue_hint`) y la persiste en el residuo.
  Además `extract_fulltext.is_legible` suma **densidad por página** (`LEGIBLE_MIN_CHARS_PAGE=200`):
  el escaneo cuya única capa de texto es la **marca de agua** del bibcode pasaba el mínimo global y
  se contaba como extraído (medido: Baranne+1996, 378 bytes en ~20 páginas) — ahora cae al OCR y el
  lint lo surface retroactivamente en cualquier bóveda ya ingestada.
- Hueco conocido del historial: las tandas **1.6.2** (#46/#47) y **1.6.3** (#48) nunca dejaron
  entrada acá (sólo commit de fix + bump). Backfillear si se quiere el registro completo.

## Backlog de framework — revisión profunda de skills 2026-08-19 (issues #51–#67)

> Revisión pedida por el usuario: lectura completa de los 9 skills + cross-check contra
> `scripts/`/`lint.py`/`CLAUDE.md`/`docs/` + búsqueda de sistemas similares (guía oficial de
> authoring de skills, PaperQA2/OpenScholar, DeepSciVerify, MiniCheck, PRISMA-S). Informe con la
> evidencia archivo:línea de cada hallazgo: `outputs/revision-skills-2026-08-19.md` (**gitignored y
> regenerable** — lo durable es esta sección). Los 17 hallazgos están abiertos como issues #51–#67;
> acá queda lo que GitHub no guarda: **orden, dependencias e ideas descartadas como issue**.

### Orden sugerido de tandas
1. **Coherencia barata** (docs/skills, sin scripts): **#53** (huérfanos: backlog en `maintain` vs
   bloqueantes en el lint), **#54** (la convención de matcheo multi-columna no llega a
   `query-corpus`/`test-hypothesis` — ahí un falso negativo **fabrica una ausencia**), **#58**
   (`setup` no manda a `maintain D`), **#59** (CWD mezclado en el mismo skill).
2. **#52** — correcciones no-retractantes (erratum/corrigendum/EoC) hoy se imprimen y se tiran:
   `corrections:` en frontmatter + categoría de lint + `maintain F`. Patrón ya existente
   (`retracted`), scripts + tests.
3. **#56 + #55** — dos categorías nuevas de lint en el mismo archivo: verificación **stale** (fecha
   del bloque vs `git log -1 --format=%cs`) y **triage pendiente** sin resolver.
4. **#51 + #64** — el grande: registro de **curación** (descartes de triage → config versionada) y
   de **búsqueda** (bloque de provenance por sujeto: fecha/query/conteos/rows/truncated/versión).
   Destraba el **falso limpio** del lint en una máquina sin `build/`.
5. **#57** — provenance del PDF (`pdf_source: eprint|ads|publisher`) + caveat de versión en
   `verify-citations`.
6. **#65 + #66 + #67** — reestructura de skills: `reference/` (progressive disclosure), checklists
   copiables, deduplicar la cadena ADS entre `ingest-star` e `ingest-topic`.
7. **#60** — roll-ups Dataview invisibles al consumidor-modelo: materializar la tabla (variante
   cara) o documentar el fallback `grep` (variante barata).
8. **#62, #61, #63** — método: presupuesto de extracción cuando el core es enorme, veredicto
   "el corpus calla" + declaración de sesgo en `test-hypothesis`, persistencia de los `aparente` de
   `find-contradictions`.

**Dependencias duras:** #55 y #64 heredan el falso limpio mientras el registro viva en `build/` →
después de #51. #65/#67 **después** de las tandas de contenido (si no, se reescriben los skills dos
veces).

### Ideas evaluadas y NO abiertas como issue (mejoras, no defectos)
- **Localizador determinista de la cita** — escalado de evidencia estilo *DeepSciVerify*
  (arXiv:2605.27710: resuelven **67%** de los casos sin recuperar full-text). Un script correría la
  escalera #44/#46 y devolvería las líneas candidatas; el subagente sólo **juzga**. Ataca el costo
  del fan-out, que #49 multiplicó al meter las filas de tabla. ⚠ **Choca con la decisión de #44**
  ("la escalera NO se re-implementa en `scripts/`: viviría en dos lugares que pueden divergir") —
  se resolvería invirtiendo la autoridad: el script pasa a ser **la** implementación (ya tiene
  invariantes en `tests/test_multicolumn_matching.py`) y el skill queda como puntero. Gate
  obligatorio: el auto-benchmark antes/después.
- **Verificador barato como pre-filtro** — *MiniCheck* (EMNLP 2024): nivel GPT-4 en fact-checking
  contra documento de anclaje a **400× menos costo** (74.7% balanced accuracy en LLM-AggreFact). No
  reemplaza el veredicto (no produce cita textual + nº de línea, que es el contrato), pero sirve
  para **ordenar** los pares por probabilidad de error o como **segunda opinión** contra el modo de
  falla ya medido (ablandar a `parcial` un claim genérico). Costo real: dependencia de inferencia
  local (torch/HF), hoy ajena a `requirements.txt` → experimento medido, no parte de la cadena.
- **Descubrimiento para el modo off-ADS** — OpenAlex / Semantic Scholar / Crossref exponen abstract,
  grafo de citas y links de acceso abierto para la bibliografía no-astro. Un `query_openalex.py` que
  escriba el mismo `ads.json` (mismo clasificador `relevance.topics`) le daría a los temas de método
  el **descubrimiento automático** que hoy sólo tienen los astro, en vez de fuentes declaradas a
  mano. Verificar términos y límites vigentes de cada API antes de codificar.
- **Priorizar la extracción con metadata de calidad** — *PaperQA2* adjunta a cada fragmento citas,
  venue y estado de retracción. Insumo directo de #62 (ordenar qué se extrae cuando hay 850 core).
- **Subirle el perfil a `find-contradictions`** — la literatura de RAG con fuentes en conflicto
  reporta que ~25% de las preguntas abiertas recuperan evidencia contradictoria y que los LLM la
  **ignoran con exceso de confianza**. Hoy la auditoría es opt-in y nada la dispara; podría
  proponerse sola al cerrar un ingest grande.

### Lo que la revisión NO tocaría
División scripts/LLM, frontera dura (regla #0), diseño de la compuerta de triage, dry-run de
`maintain D` y el auto-benchmark del verificador. Comparado con lo que hay afuera (PaperQA2,
OpenScholar, Elicit y compañía), ninguno persiste un artefacto curado con verificación
afirmación-por-afirmación **y un número medido de su propia tasa de error**.

## ✅ Framework 1.6.1 (2026-08-17) — tanda #44/#45: estrategia de matcheo en `.txt` multi-columna

> Tanda **de docs/skills** (sin cambio de scripts), hermana de #29: el `.txt` de `pdftotext -layout`
> no es un stream de texto plano y los skills que greppean citas tenían el caveat pero no el "cómo
> buscar". Medido en Almagesto-RV: 472/644 `.txt` (73%) multi-columna. 328 tests verdes.
> `ALMAGESTO_VERSION` 1.6.0 → **1.6.1** (patch: sólo prescripción en skills, retrocompatible).

- **#44** — **`verify-citations` prescribe CÓMO buscar** (1.3.3 → 1.3.4): escalera de acortamiento
  (oración completa → fragmento distintivo contenido en una línea física; el largo útil depende del
  ancho de columna, se acorta hasta encontrar — un paper a una columna sigue matcheando la frase
  entera), de-hifenado en el corte de línea, y recién agotado eso se considera artefacto de
  extracción. **Prohibido normalizar espacios sobre el archivo entero** (empalma columna 1 con
  columna 2 → puede hacer pasar como soportada una afirmación inventada — el modo peligroso, hasta
  ahora sin documentar). Medido: 9/24 pares (~38%) de falso negativo con la oración completa, 24/24
  con fragmento corto; 33/68 citas de bloques existentes no localizables con 6 palabras y 7/7
  muestreadas aparecen con 3–5 → el corpus está sano, fallaba el patrón. La regla viaja también en
  el prompt sugerido del subagente.
- **#45** — **`find-contradictions` arrastra las convenciones** (1.0.0 → 1.0.1): puntero explícito
  a #29/#44 (la convención canónica queda en verify-citations, sin copia), regla condensada en el
  prompt del subagente aplicada a CADA archivo, y `no-concluyente` sólo agotada la escalera en
  ambos lados. Acá el riesgo se amplifica: el par exige cita de dos fulltexts (~94% de chance de
  que al menos uno sea multi-columna) y un falso negativo colapsaba el veredicto a `no-concluyente`
  sobre una disputa real.
- Addendum (2026-08-17): la medición de prevalencia quedó como **diagnóstico**, no test de regresión
  — el template no trae corpus, un test así no podría correr acá. `scripts/measure_layout.py`
  (aportado por el usuario) mide cualquier bóveda: archivos multi-columna (heurística: >30% de líneas
  útiles con hueco interno de 8+ espacios), líneas con canaleta (donde el empalme col.1→col.2 es
  alcanzable) y cortes por guión; `--json`, `--por-slug`, `--listar N`. Medido en Almagesto-RV: 73%
  de archivos multi-columna global y 46% de líneas útiles con canaleta, pero el peso depende del
  origen de la bibliografía — slugs astro 62–86%, el off-ADS de estadística/ML (fastica) 38%: una
  bóveda de puros métodos necesita menos la regla. La escalera NO se re-implementa en `scripts/`
  (viviría en dos lugares que pueden divergir).

## ✅ Framework 1.6.0 (2026-08-15) — tanda #29/#42/#43: follow-ups de la primera corrida real

> Tanda **correctiva**, disparada por la primera corrida real de v1.5.0 (Almagesto-RV, ε Eri): dos
> promesas de la cadena que no se cumplían (la persistencia de la compuerta de triage y la marca de
> truncamiento del rescate por glifo) y una ambigüedad del verify que fabricaba citas rotas. 328
> tests verdes, lint 0. `ALMAGESTO_VERSION` 1.5.0 → **1.6.0** (minor: clave `truncated_glyph` nueva
> en `ads.json` + marcador ◆ en triage, retrocompatible).

- **#42** — **`extra_core` se mergea ANTES del chaining**: el bloque corría después, así que los
  bibcodes curados no estaban en `recs` al armar el dedup y la cola de triage **re-proponía papers
  ya aceptados** (medido: 14 de 50 `extra_core` de ε Eri de vuelta como candidatos — core y
  candidato a la vez). La persistencia de la compuerta ahora vale para los dos lados de la decisión
  y los curados siembran el grafo. Además `triage.py` marca `◆` los candidatos que **ya tienen
  nota** en la bóveda (entraron por otro slug): no se filtran, se despachan rápido.
- **#43** — **el truncamiento del superset del rescate por glifo se marca** (antes el warning decía
  "queda marcado en ads.json" y no marcaba nada: la marca `truncated` es de la query directa). El
  corte top-por-citas pasa **antes** del filtro por glifo —donde vive la señal—, así que ahora cada
  superset truncado queda en la clave hermana `truncated_glyph` ({letter, constellations,
  num_found, rows}), main avisa con mensaje propio y el lint lo surface como rescate incompleto,
  distinguible del truncamiento de la query directa.
- **#29** — **convención fija de conteo de líneas en `verify-citations`**: los `.txt` de
  `pdftotext` traen un form feed por página (532/535 del corpus RV) que `splitlines()` de Python
  cuenta como salto extra → +1 línea por página, y una revisión posterior marcaba como rotas citas
  correctas (11/24 en un verificador ad-hoc). El skill fija `grep -n`/lectura directa (nunca
  `splitlines()`), documenta que en papers a dos columnas el nº de línea es puntero, no extracto
  contiguo, y el scan de fuga del lint numera con `split("\n")` por consistencia.

## ✅ Framework 1.5.0 (2026-08-15) — tanda #27/#28/#37–#41: la cadena de ingesta

> Tanda de la **cadena de ingesta**, disparada por la aplicación de v1.4.0 en la instancia
> Almagesto-RV: dos bugs de recall/silencio de `query_ads` y cuatro huecos de control (el pool se
> ampliaba sin checkpoint ni juicio). 322 tests verdes, lint 0. `ALMAGESTO_VERSION` 1.4.0 →
> **1.5.0** (minor: modos y clave `candidates` nuevos, retrocompatible).

- **#27** — **cero espurio de ADS**: `numFound: 0` con HTTP 200 (~2/6 corridas de la misma query)
  hacía que la cadena corriera entera sobre un corpus vacío y saliera con exit 0 (y en un re-ingest
  pisara el `ads.json` bueno). La query directa corre con `expect_hits`: reintenta con el backoff
  existente y, si persiste, `EmptyResultError` → exit ≠ 0. Los ceros legítimos (chaining, `--sweep`,
  `--probe`, `--extra-only`) intactos.
- **#28** — **agujero de recall por glifo**: ADS unifica `epsilon`/`eps`/`ε` pero **descarta** los
  lookalikes `ϵ` (U+03F5) y `∊` (U+220A, el glifo de ApJ/AJ/MNRAS) → esos papers quedan indexados
  sólo por la constelación (ε Eri: **121 core perdidos**, incluido el descubrimiento). Rescate por
  glifo: superset de la constelación + filtro client-side letra-específico, `via: glyph`, antes del
  chaining (lo recuperado siembra el grafo). Sólo letras con lookalike; `--no-glyph` lo apaga.
- **#39** — **`extra_core` es override**, no "sumá lo ausente": el paper que ADS sí devuelve y la
  lente descarta ahora se rescata en el lugar (`via: manual`). Contador que distingue traídos de
  rescatados + aviso de bibcodes declarados que ADS no devuelve.
- **#37** — **guardia de expansión** en los orquestadores: entre `query_ads` y el primer paso que
  gasta red y disco, frena si el core se multiplicó respecto de lo ya ingestado (×1.5 y >50 nuevos)
  con el puntero a `relevance.require`/`min_topics`; `--yes` continúa a sabiendas. No aplica al
  primer ingest.
- **#38** — **compuerta de triage del chaining** (el grafo **propone**, no promueve): entra solo el
  candidato con el **sujeto en el título** (1 FP en 310); el resto queda en la clave `candidates` de
  `ads.json` **sin bajarse** para el juicio del LLM (`scripts/triage.py` + paso 2c de `ingest-star`).
  Decisiones persistentes: aceptado → `extra_core`; descartado → `build/<slug>/triage.json` (no se
  re-propone). Medido: 18% de precisión en los core nuevos del grafo. `--no-triage` lo apaga; en
  temas no aplica.
- **#40** — **`query_ads --dry-run`**: delta de re-clasificación offline (core antes/después, los
  que salen separando extracción LLM de stubs, los que entran sin nota por vía). Paso 0 del
  sub-modo D de `maintain`; antes era arqueología con scripts descartables.
- **#41** — **`setup` guía la regla de combinación**: pregunta por la **faceta-eje**, propone
  `relevance.require`, y `--probe` cierra con el **contraste** (qué cortaría cada faceta si fuera
  obligatoria / cuánto se corta vs OR puro). Corolario documentado: con `require` declarada, afinar
  las otras facetas ya no cambia el corte — lo que importa es el **recall de la eje**.
- Skills: `ingest-star` 1.6.1 → **1.9.0**, `ingest-topic` 1.7.2 → **1.8.0**, `maintain` 1.3.2 →
  **1.5.0**, `setup` 1.0.0 → **1.1.0**. `split_fm` centralizado en `lib_config`.

## ✅ Framework 1.4.0 (2026-08-14) — tanda #30–#36: auditoría de framework

> Registrada acá a posteriori (el release commit `0a83e7d` sólo bumpeó la versión). Aditiva:
> `why_excluded` por registro en `ads.json` (#30), consulta `pscomppars` única (#31), residuo
> completo de PDFs por verdad de disco (#32), lint portable por `Path.parts` (#33),
> `accessed` = `retrieved` del snapshot + `--accessed` (#34), `stamp_excluded` quirúrgico (#35),
> sync de docs/labels (#36).

## ✅ Framework 1.3.0 (2026-08-05) — tanda #24–#26: eficiencia del pipeline de ingesta

> Primera tanda de la **revisión del pipeline de ingesta** (2026-08-05: tiempos / tokens /
> metodología + relevamiento de sistemas de discovery; el resto de la cola quedó como backlog —
> ver la sección nueva de abajo). 263 tests verdes, lint 0. `ALMAGESTO_VERSION` 1.2.2 → **1.3.0**
> (minor: modos nuevos, retrocompatible).

- **#24** — `check_retractions --slug` en la cadena: los orquestadores chequean Crossref **sólo**
  sobre los papers del ingest en curso (bibcodes relevantes de `build/<slug>/ads.json` +
  `sources[].key`/`extra_core` del tema) en vez de barrer toda la bóveda en cada corrida (minutos,
  lineal con el corpus). El barrido completo pasa a **pasada periódica**: sub-modo F nuevo del
  skill `maintain` (1.2.0 → 1.3.0); `ingest-star` 1.5.0 → 1.5.1 (doc).
- **#25** — `query_ads --sweep`: el barrido full-text 2b de `ingest-star` deja de ser manual — la
  query `full:` expande sola nombre+aliases con **todas las grafías** (antes: una `--probe` a mano
  por grafía, fácil de olvidar) y lista **sólo** los core que el ingest no trajo (la lista corta de
  candidatos a `extra_core`; el diff contra el corpus ya no se hace a ojo). Preview puro: no baja,
  no encadena, no escribe `build/`. Skill `ingest-star` 1.5.1 → 1.6.0.
- **#26** — guard `or {}` en `load_stars()` (espejo del que ya tenía `load_topics`): con
  `stars.yaml` vacío (instancia recién creada) cualquier lookup de slug moría con `AttributeError`
  en vez del `KeyError` amigable. Destapado por el smoke de #25 en el template.

## Backlog de framework — revisión del pipeline de ingesta 2026-08-05 (cola pendiente)

> De la revisión completa del pipeline (tiempos/tokens/metodología; informe local en
> `outputs/revision-pipeline-ingesta-2026-08-05.md`, gitignored — lo esencial está acá). La tanda
> #24–#26 cerró los ítems "check_retractions --slug" y "--sweep". Pendientes, por valor:

1. **Verify batcheado por fuente** (el mayor ahorro de tokens, ×3–5): un subagente por **bibcode**
   que juzga TODOS los claims atribuidos a esa fuente (hoy: uno por par → el mismo `.txt` se relee
   hasta 5×; el ahorro es pares ÷ fuentes distintas). Riesgo: anclaje/hedging dentro del lote.
   **Gate: A/B contra `bench_verify` en una instancia poblada (RV)** — recall no puede caer.
   Aparte y con el mismo gate: **modelo barato (Haiku) en el fan-out** — medir por separado.
2. **Pata `similar()` en `query_ads`** (recall por CONTENIDO — papers fuera del grafo de citas, el
   único hueco estructural del chaining): operadores de segundo orden de ADS
   (`similar()`/`useful()`/`reviews()`, verificados en vivo 2026-08-05 — misma API, mismo token,
   bibcodes nativos; `trending()` inestable, fuera). Implementar opt-in y **medir contra baseline
   en RV** antes de hacerlo default (estilo defuddle).
3. **Exhaustividad con número**: log del yield por ronda de chaining (Wohlin 2014: la ronda 2
   aporta poco — disparo condicional), capture-recapture query↔chaining (Lincoln–Petersen,
   N ≈ n1·n2/m) → "capturamos ~X de ~Y core estimados" al log/Huecos (le da número al backlog de
   corpus truncado); opcional el fit de saturación f = 1 − e^(−n/τ) (whitepaper de Undermind).
4. **Verify incremental (diff-mode)**: clave estable por par (hash del claim + bibcode) en el
   bloque `## Verificación de citas` → un re-run sólo fan-outea claims nuevos/editados (`raw/` es
   inmutable; invalidar si cambió `fulltext_source`). Gran ahorro en maintain/append.
5. **`triage.md` determinista** por slug (una línea por core: citas/via/topics/¿pdf?/¿fulltext?)
   para elegir deep-reads sin cargar los abstracts de `ads.json`; si se hace el **ranking del
   pool** (Adamic/Adar sobre bibliographic coupling — algoritmo documentado de Inciteful — y/o
   TF-IDF+NaiveBayes estilo ASReview con las etiquetas de la regex), sus scores entran como
   columnas y el LLM sólo juzga el borde (patrón RCS de PaperQA2).
6. **Menores**: fan-out de extracción por paper en ingests grandes (texto de skill — la síntesis
   se arma desde las notas, no desde fulltexts); `fetch_arxiv` ∥ `fetch_pdf` (hosts distintos;
   desacoplar `missing_pdf.json`); fusionar `references()`/`citations()` por chunk; adelgazar
   `CLAUDE.md` (~30–40% de tokens recurrentes por sesión — quirúrgico, con revisión del usuario).
7. **Pasada de retracciones automática** (surgió al cerrar #24): opciones — cron de GitHub Actions
   por instancia (no sirve para instancias local-only), cron local, o que `maintain` la dispare
   si hace >N semanas que no corre (fecha del último barrido en un scratch). Sin decidir.

## ✅ Framework 1.2.2 (2026-07-31) — issues #22–#23: el residuo multi-cláusula

> Segunda vuelta del mismo run: de las 4 sembradas que sobrevivieron a 1.2.1, **3 venían de que el
> claim era un bloque multi-cláusula** (el paper rotado respaldaba, con razón, una cláusula vecina
> —de encuadre o de otra cita—, así que la sembrada "pasaba" como `parcial` sin que nadie se
> equivocara). 254 tests verdes, lint 0. `ALMAGESTO_VERSION` 1.2.1 → **1.2.2**.

- **#22** — `bench_verify` recorta el claim a la **cláusula que porta esa cita** (partido por
  oraciones, con la etiqueta del bullet de sujeto; fallback al bloque si no hay corte). El corte
  exige mayúscula tras el punto → no parte decimales ni `p. ej.`. La veda falso-falso **no** se
  relaja. De paso: `lstrip("-* ")` mutilaba los `**` de las etiquetas en negrita → `BULLET_RE`.
- **#23** — skill `verify-citations` 1.3.0 → **1.3.1**: el **prompt sugerido** ahora transmite la
  regla de claims multi-cláusula que el paso 1 ya exigía (juzgar *la parte que se le atribuye*, y
  decir qué cláusula) — sin ella el subagente juzga el conjunto y hedgea a `parcial`.

## ✅ Framework 1.2.1 (2026-07-31) — tanda de issues #18–#21: validez del benchmark verify

> Salida del **primer run real de `bench_verify`** (instancia Almagesto-RV, 40 pares): recall bruto
> 13/20 (65%); la revisión a mano mostró que 5 "pasadas" eran **soporte casual genuino** (la rotación
> cayó en un paper que de verdad dice lo mismo) y 2 eran misses reales (`parcial`-blando) → recall
> efectivo ≈87% sobre las genuinamente falsas; reales 20/20, sin errores de grounding en las notas.
> El run midió más al *examen* que al examinado → esta tanda arregla el examen (3 fixes al seeder) y
> al examinado (1 regla al skill). 250 tests verdes, lint 0. `ALMAGESTO_VERSION` 1.2.0 → **1.2.1**
> (patch: fixes de validez). **El número NO se publica** hasta re-correr con el seeder arreglado.

- **#18** — el claim se guarda **cegado** (sin `[[wikilinks]]` inline): con el bibcode original
  adentro, una sembrada se caza por mismatch de strings sin leer el paper.
- **#19** — claims por **bloque lógico** (bullet con continuaciones hard-wrapped unidas, o párrafo;
  filas de tabla siguen atómicas): el claim-por-línea producía fragmentos que mezclaban cláusulas de
  citas vecinas (falsas alarmas) y sembradas genéricas fáciles. La protección falso-falso de la
  rotación pasa a operar sobre el bloque completo.
- **#20** — rotación con preferencia **cross-nota**: el cruce se busca primero entre bibcodes que la
  nota de origen no cita en ningún bloque (contra el 25% de soporte casual); fallback histórico si
  la nota cita todo el pool.
- **#21** — skill `verify-citations` 1.2.1 → **1.3.0**: regla del **contenido distintivo** para
  `parcial` (cita textual que toque lo que hace específica a la afirmación; coincidencia sólo
  temática ⇒ `no-soportada`) — en el contrato del subagente, el prompt sugerido y el umbral;
  espejo en `CLAUDE.md`.

## ✅ Framework 1.2.0 (2026-07-19) — tanda de issues #15–#17 resuelta

> Los 3 issues abiertos desde la instancia Almagesto-RV, resueltos en el template (un commit por
> issue, `closes #N`). 246 tests verdes, lint 0 bloqueantes. `ALMAGESTO_VERSION` 1.1.0 → **1.2.0**
> (minor: cambios aditivos/retrocompatibles). Al mergear en las instancias: el nuevo default
> `--rows 2000` y la regla de combinación aplican en el próximo ingest; cambiar la regla re-clasifica
> (sub-modo `maintain`).

- **#16** — `fulltext:` **determinista** para papers que viven bajo varios slugs (relevantes para más
  de un sujeto). `stamp_fulltext` dejó de repuntar al slug que corrió último: precedencia declarada
  (primer escritor gana en empate) + preferencia por calidad (`pdftotext`/`web` > `ocr`) → sin ruido
  de diff y `fulltext_source` estable. Repara punteros colgados.
- **#17** — el **truncamiento** de la query directa (`numFound > --rows`) se **persiste** en
  `build/<slug>/ads.json` (`truncated: {num_found, rows}`) y el **lint lo surface** como backlog:
  un fallo silencioso pasa a visible. Default `--rows` 400 → **2000** (≈ el máximo de una request ADS).
  El truncado del chaining sigue sin registrarse (por diseño). Deferido: `--audit` (censo de bóvedas
  pre-registro), paginación, ordenar el corte por relevancia.
- **#15** — la **regla de combinación** de `relevance.topics` es **declarativa**, no hardcodeada:
  `relevance.require: [faceta,…]` (AND) y/o `relevance.min_topics: N`. `core = (≥min_topics) Y (todas
  las de require) Y (doctype no-ruido)`. Sin declarar nada = OR histórico (retrocompatible). Es la
  palanca contra el ruido que el citation chaining mete al ampliar el pool (medido en Almagesto-RV:
  exigir el eje recorta 928→254). Documentado en `objective.yaml`/`setup`/`maintain`/`CLAUDE.md`.
  Deferido: aplicar la restricción también server-side en la sub-query del chaining.

## ✅ Framework 1.1.0 (2026-07-18) — tanda de issues #9–#14 resuelta

> Los 6 issues abiertos desde la instancia Almagesto-RV, resueltos en el template (un commit por
> issue, `closes #N`). 233 tests verdes, lint 0 bloqueantes. `ALMAGESTO_VERSION` 1.0.0 → **1.1.0**
> (minor: cambios aditivos de schema/cadena). Al mergear en las instancias: re-correr la cadena
> idempotente estampa el contrato nuevo en las notas viejas (ver #14).

- **#9** — guard "objetivo sin instanciar" compara contra un **placeholder explícito**
  (`<definir con el skill setup>`), no contra un nombre real: mata el falso positivo permanente
  de Almagesto-RV.
- **#10** — guard contra abrir la **raíz** del repo como vault de Obsidian: `/.obsidian/` (raíz) al
  `.gitignore`, WARN del lint si existe, filtro vestigial de `graph.json` limpiado, síntoma+remedio
  en `docs/operacion.md`.
- **#11** — tema off-ADS **MIXTO**: `extra_core:` con bibcodes ADS reales dispara la sub-cadena ADS
  (`query_ads --extra-only` nuevo → fetch → make_notes) — antes se ignoraba en silencio. Skill
  `ingest-topic` 1.6.3→1.7.0.
- **#12** — `strictLineBreaks: true` persistido en `vault/.obsidian/app.json` (las notas
  hard-wrapped se reflowean en modo lectura).
- **#13** — stub de paper con **link markdown clickeable al PDF** en el cuerpo (`· [📄 PDF](…)`;
  markdown, no wikilink — el lint rompería).
- **#14** — contrato de `papers/` extendido: **`fulltext:`** (ruta al `.txt` barato) +
  **`fulltext_source:`** (`pdftotext|ocr|web` — la salvedad OCR visible desde el frontmatter).
  Estampado por verdad de disco (stubs) + cirugía `stamp_fulltext` desde `extract_fulltext`
  (migra notas viejas al re-correr). `CLAUDE.md` desambiguado: el default de lectura es el `.txt`.
  Skill `verify-citations` 1.2.0→1.2.1. Los `.txt` OCR'd a mano sin header (caso Almagesto-RV) se
  rescatan con `extract_fulltext.py <slug> --force`.

## Backlog de framework — eye candy del README (EN CURSO, sesión 2026-07-18)

> Estado hasta `9221352` **commiteado y pusheado**; 218 tests verdes, lint 0. Lo de la
> sub-tanda **logo + About (2026-07-18)** de abajo está en el working tree, **sin commitear** aún.

**Hecho tandas previas:** README adelgazado a pantallazo de presentación (lo operativo →
`docs/operacion.md`); portabilidad OS-agnóstica (pathlib, TemporaryDirectory, encoding utf-8 en
subprocesos); generador determinista `docs/assets/make_logo.py` → `logo-animated.svg`
(header del README, 180 px) + `logo.svg` (emblema estático de reserva).

**✅ RESUELTO (2026-07-18) — logo rediseñado: la rosa de Venus.** El usuario descartó el
epiciclo (estático y animado). Rediseño desde cero: `make_logo.py` ahora dibuja la **trayectoria
geocéntrica real de Venus en 8 años** (pentagrama de 5 pétalos, `posición(Venus) − posición(Tierra)`
con órbitas circulares). Se le ofrecieron 4 direcciones (rosa de Venus / lámina Mercurio+Venus /
retrogradación / esfera armilar) y eligió **A (rosa de Venus)**. El animado **dibuja su propia traza**
(`stroke-dashoffset`) mientras Venus —estrella ámbar— recorre la punta (`animateMotion` sobre la
misma curva, 20 s en loop) → conserva el concepto "el mecanismo dibuja su curva" que sí gustaba.
`alt` del README actualizado. **Decisiones técnicas conservadas** (siguen validadas): una sola tinta
neutra `#7d8590` sobre transparente (evita el truco frágil `<picture>`+`prefers-color-scheme`, que
sigue el tema del OS y no el de GitHub); acento ámbar `#d4a017`; sin wordmark; SMIL anima en READMEs
de GitHub (camo proxy) y congela con la rosa completa donde no; camo/browser cachean ~5 min (un "no
se ve" tras push suele ser caché).

**✅ HECHO (2026-07-18) — About del repo.** Estaba vacío. Descripción seteada vía `gh repo edit`:
"Wiki de conocimiento astronómico mantenida por un LLM (patrón LLM Wiki de Karpathy): literatura por
estrella y concepto, verificable claim↔fuente." El usuario optó por **no** poner topics por ahora
(los agrega a mano si quiere).

**✅ HECHO (2026-07-18) — diagrama Mermaid del pipeline.** Bloque ```mermaid en el README (sección
intro, tras el párrafo del flujo raw→LLM→wiki): `ADS/arXiv + NEA/SIMBAD → vault/raw (inmutable) →
LLM-compilador → vault/wiki`, con `objective.yaml` clasificando core/no-core y `lint`/`verify-citations`
como checks (verify retro-alimenta disputas). Incluye la rama **off-ADS** (nodo punteado "PDFs locales ·
web", opt-in) que entra a `vault/raw` sin ADS/NEA — a pedido del usuario, que notó que la v1 del
diagrama la omitía; abajo del bloque va un blockquote explicando el modo off-ADS (`source: web|local-pdfs`
+ `sources:` en `topics.yaml`). **Framing del off-ADS afinado (mismo pedido):** README + CLAUDE.md +
skill `ingest-topic` ahora **lideran con la intención** —es para *métodos que no son exclusivamente
astronómicos* (análisis de datos, machine learning, procesos gaussianos, signal processing) cuya
bibliografía vive fuera de ADS— en vez de con el mecanismo. **Ejemplo canónico de método off-ADS unificado
a procesos gaussianos** en TODO el framework (era demasiado específico del usuario): README, CLAUDE.md
(off-ADS + ejemplo hub/radio → `procesos-gaussianos`/`gp-kernels`), `ingest-topic` (framing + grep de
retro-tag + clave de cita de ejemplo `2006RasmussenWilliams`), `append-knowledge`, el ejemplo comentado de
`topics.yaml`, un comentario de `fetch_ground_truth.py` y los fixtures de tests (`gp`/`gaussian-processes`;
218 tests siguen verdes). Skills bumpeados: `append-knowledge` 1.0.0→1.0.1, `ingest-topic` 1.6.2→1.6.3. Trazos: gris neutro `#7d8590` (fuentes/almacenes/checks), ámbar `#d4a017`
(LLM). GitHub re-renderiza el bloque con su tema claro/oscuro (verificado en ambos con mermaid-cli; los
strokes leen en los dos). Nota de tooling: `mmdc` necesita `--no-sandbox` (config puppeteer) en este
entorno.

**✅ HECHO (2026-07-18) — social preview + favicon (make_logo.py).** `make_logo.py` ahora genera 4
assets: `logo-animated.svg`, `logo.svg`, **`favicon.svg`** (marca reducida: anillo/órbita neutro +
Venus ámbar + centro — la rosa completa se emborrona a 16-32 px, así que el favicon es su reducción
legible; elección del usuario) y **`social-preview.svg`** (tarjeta 1280×640 estilo lámina papel-antiguo:
rosa sepia a la izquierda, `ALMAGESTO` en GFS Didot + el etimón griego `ἡ Μεγίστη` + tagline en EB
Garamond, dentro de un marco de lámina; fondo pergamino `#efe6d3`). El PNG del social preview
(`docs/assets/social-preview.png`) se **rasteriza aparte** (necesita las fuentes GFS Didot + EB Garamond
y un rasterizador; en esta sesión, el Chromium de puppeteer con `--no-sandbox`) y **se sube a mano** en
Settings → General → Social preview. El social preview arrancó con fondo oscuro (se veía "muy IA") →
iterado a papel-antiguo + tipografía griega a pedido del usuario.

**Pendientes menores de eye candy (menú ofrecido, sin decidir):** captura de Obsidian (demo con estrella
famosa), GIF de terminal (vhs) del `--probe`.

## ✅ Backlog de framework (RELEVADO 2026-08-05) — buscadores IA de literatura (Undermind & co.)

> **Relevamiento hecho 2026-08-05** (3 agentes de research con fuentes verificadas; APIs de
> S2/OpenAlex/ADS probadas en vivo). **Veredicto: opción (b) — copiar metodología, no consumir
> APIs.** (1) Ninguno corre sobre ADS (todos S2/OpenAlex/arXiv) y las APIs son pagas/cerradas
> (Undermind: enterprise-only; Elicit: self-serve pero atada a suscripción; Consensus: por
> aplicación; SciSpace: sin API) → para astro no aportan sobre la query ADS directa. (2) **Undermind
> publicó su metodología** (whitepaper Hartke & Ramette 2024, undermind.ai/whitepaper.pdf): lo
> copiable es el criterio de parada (fit de saturación f = 1 − e^(−n/τ)) y el estimador de
> exhaustividad tipo capture-recapture → ítem 3 de la cola del pipeline (arriba). (3) Hallazgo de
> menor fricción, no previsto en el encuadre: **ADS mismo trae operadores de descubrimiento**
> (`similar()`/`useful()`/`reviews()`, verificados en vivo con el token de la bóveda) → ítem 2 de
> la cola. (4) Abiertas: S2 Recommendations sigue gratis pero su pool astro es "últimos 60 días"
> (sólo serviría como modo alertas de `maintain`); OpenAlex pasó a pricing por uso (key gratuita,
> crédito diario) y su grafo es redundante con ADS; SPECTER2 es Apache-2.0 y corre en CPU → opt-in
> de ranking si hiciera falta. **Pendiente del entregable original:** medir lo adoptable contra
> baseline en RV antes de mergear (estilo defuddle). El encuadre original queda abajo como registro.

**Pregunta.** Existen herramientas que hacen búsqueda bibliográfica con IA (**Undermind**, y en la
misma familia Elicit / Consensus / SciSpace / semantic-search sobre Semantic Scholar u OpenAlex).
¿Conviene (a) **consumir alguna API** desde la cadena de ingest, o (b) **copiar la metodología** y
reimplementarla sobre nuestra plomería (ADS + chaining + `objective.yaml`)?

**Por qué importa acá.** El descubrimiento de papers hoy es: query ADS por keywords → filtro core con
la regex de `relevance.topics` → citation chaining anclado. Es determinista y barato, pero es
**matching léxico**: un paper relevante que no usa nuestras palabras no aparece. Ese es exactamente el
hueco que estas herramientas dicen cubrir (búsqueda semántica + exploración iterativa del grafo de
citas, en vez de una sola query).

**A verificar antes de opinar (nada de esto está chequeado):**
- ¿Undermind expone **API pública** y con qué licencia/costo? ¿Los resultados vienen con identificador
  estable (DOI/bibcode) para que encajen con `vault/raw/` y las claves de cita?
- ¿Cubre **astro-ph**/ADS o está sesgado a bio/CS? Si no trae bibcode, hay que resolver DOI→bibcode.
- **Metodología publicada:** ¿hay paper/whitepaper describiendo el algoritmo (búsqueda iterativa,
  criterio de relevancia, criterio de parada)? Eso es lo copiable y lo que no ata a un proveedor.
- Alternativas **abiertas** que sirvan de sustituto barato: API de **Semantic Scholar** (recomendaciones
  + embeddings SPECTER2) y **OpenAlex** (gratis, sin key) — probablemente el camino menos comprometido.

**Criterios de decisión (los de siempre acá).** (1) Lo determinista va en `scripts/`, sin gastar tokens;
(2) el template es MIT y portable → una dependencia de servicio pago/cerrado no puede ser obligatoria,
a lo sumo opt-in como el modo off-ADS; (3) todo lo que entre al vault sigue necesitando fuente citable
(regla #0) — un buscador IA aporta **candidatos**, nunca prosa.

**Entregable esperado del relevamiento:** una nota corta comparando (API vs metodología vs no-hacer-nada)
con números, al estilo de la evaluación de `defuddle` — no adoptar nada sin medir contra el baseline
actual (query ADS + chaining) sobre una estrella/tema ya ingestado.

## Backlog de framework — validación de áreas de `vault/wiki/concepts/` + config a mano

> Rescatado del scratch `DESIGN-NOTES.md` (discusión 2026-06-27) al borrarlo el 2026-06-28. El escape
> **off-ADS** de esa nota **ya se implementó** (commit `a005257`); lo que sigue **no**. Son cambios de
> **framework** → aplicar en el template, no en una instancia (Regla de oro, ver `CLAUDE.md`).

**Problema raíz.** El set de áreas `vault/wiki/concepts/{indicators, methods, activity, hypotheses}` es **folklore,
no contrato**: no existe como dato declarado; está implícito y repartido en 5 lugares (`CLAUDE.md`,
`README.md`, `ingest-topic/SKILL.md`, comentario de `vault/config/topics.yaml`, y las carpetas reales).
`make_notes.py` hace `dest.parent.mkdir(...)` con el `area` que venga **sin validar** → un typo
(`indicator`, `metods`) crea una **carpeta fantasma en silencio**. Las áreas son **abiertas** (no un set
cerrado de 4): sólo `hypotheses` (estructural: schema `name,status` + roll-up Dataview) y `methods`
(universal) son fijas; el resto depende del foco de la instancia.

**Tres mejoras — son CAPAS, no alternativas.** Orden recomendado: **1 → 2 → 3** (el skill sin la
nomenclatura no tiene a qué adaptarse; el check sin la nomenclatura no tiene contra qué chequear).

1. ✅ **HECHO** — **nomenclatura de áreas a config**. `concept_areas` declarado en
   `vault/config/objective.yaml`; `methods`/`hypotheses` reservadas; loader `lib_config.load_concept_areas()`
   (modo tolerante si una instancia vieja no lo declara). Las 5 menciones de "folklore" ahora defieren al
   contrato (CLAUDE.md, README.md, topics.yaml, ingest-topic/SKILL.md).
2. ✅ **HECHO (alcance: objetivo)** — **skill `setup` interactivo**. El agente traduce el foco del
   usuario (en palabras) a `objective.yaml` —`name`/`description` + la regex `relevance.topics` + sugerencia
   de `concept_areas`— y la **afina contra ADS** con `query_ads.py --probe "<query>"` (preview del corte
   core/no-core sin bajar nada), iterando hasta que cierre. Distingue **facetas** (→ relevance.topics,
   constantes) de **sujetos** (→ stars/topics) y respeta la frontera dura. **Descopeado** (a pedido): sembrar
   `stars.yaml`/`topics.yaml` queda fuera — eso entra por `ingest-star`/`ingest-topic`. **Pendiente** (capa
   2 extendida, opcional): un setup que además proponga las estrellas/temas iniciales.
3. ✅ **HECHO (completado 2026-07-17)** — **check de config (lint, WARN blando)**. ✅ Áreas (abiertas,
   nunca se bloquea): `make_notes` **avisa** si el `area` no está en `concept_areas` pero crea igual;
   `lint.py` marca **WARN** las carpetas de `concepts/` fuera de la lista (atrapa typos sin restringir).
   ✅ (2026-07-17) el resto de los guards: `lib_config.require_field()` da error amigable (entrada +
   campo + archivo) en los índices duros — `ads_object`/`simbad` en stars, `query` en topics (con
   pista "es off-ADS → ingest_topic"), `area`/`concept` en `make_notes --topic` — en vez de un
   KeyError crudo; y el lint marca **WARN si `objective.name` sigue siendo el default** del template
   (olvido de instanciar; en el repo template ese WARN es esperable y no bloquea).

**Preguntas abiertas — resueltas al implementar capas 1+3-áreas:**
- Nomenclatura → vive en `vault/config/objective.yaml` (instance-owned), con la prosa del schema en
  `CLAUDE.md` deferiendo a ella. ✅
- `methods` → **reservada** igual que `hypotheses` (universal). ✅
- El check → vive en `lint.py` (encaja con su filosofía WARN/backlog), no en un script aparte. ✅
- Pendiente de decidir (al hacer la capa 2): ¿el skill de setup **reemplaza** el flujo "editá
  `objective.yaml`" del README o lo **complementa**? (lean: complementa).

## ✅ Backlog de framework (RESUELTO 2026-07-17) — obtención de PDFs (papers viejos / no-arXiv)

> Surgido al usar la bóveda (2026-06-29): papers **pre-arXiv / viejos** no están en arXiv, así que
> `fetch_arxiv.py` no los baja; hubo que recurrir a workarounds manuales para conseguir el PDF.

> **Update 2026-07-16 (issues #7/#8, HECHO):** la parte "derivar al usuario" y el rescate de
> escaneos ya están en el framework — fuentes no-conseguibles se marcan `pending`
> (`pending_source` en la nota, aviso del orquestador, precondición en el lint, des-pendeo
> automático al llegar la fuente) y `extract_fulltext.py` cae solo a **OCR** (tesseract) cuando la
> capa de texto es ilegible (`.txt` con `source: ocr`, citable con salvedad).

> **Update 2026-07-17: fetcher HECHO — `scripts/fetch_pdf.py` cierra la sección.** Corre en la
> cadena (`ingest-star` / `ingest_topic --ads`, tras `fetch_arxiv`) para los papers SIN arXiv:
> resolver `esource` → `EPRINT_PDF`/`ADS_PDF` (con token) → `PUB_PDF` (sin token; fallback al
> mismo pedido con `curl` del sistema — los WAF tipo Radware/IOP desafían el fingerprint de
> python-requests pero aceptan curl). Valida magic `%PDF`, retry/backoff, deja el residuo en
> `missing_pdf.json`. Smoke real 3/3: Wilson 78 y Noyes 84 por ADS_PDF, Saar 99 por PUB_PDF
> vía curl. Bonus: `make_notes` ahora estampa `pdf:` por **verdad de disco** (antes adivinaba
> por `arxiv_id` y dejaba punteros rotos si la bajada fallaba).

**Problema.** `fetch_arxiv.py` sólo baja de arXiv (usa el campo `arxiv_id`). Papers sin arXiv (revistas
viejas, escaneados) quedan sin PDF → sin fulltext → sin extracción LLM ni `verify-citations`. Hoy se
resuelve a mano, fuera del pipeline.

**Principio que rige (pedido del usuario).** Meter en **scripts** todo lo determinista posible, que **no
dependa de gastar tokens** del LLM. Alinea con la división del patrón (`scripts bajan determinista; LLM
procesa criterio`): empujar la frontera hacia los scripts.

**Dirección concreta a evaluar (inferencia mía — falta verificar la API):** la ADS API expone los
`esources`/`links_data` de cada paper (`PUB_PDF`, `ADS_PDF`, `ADS_SCAN`, `EPRINT_PDF`…), y ADS **aloja
escaneos** de artículos viejos (`ADS_SCAN`). Un fetcher más general (extender `fetch_arxiv` o un
`fetch_pdf.py` nuevo) podría, para un paper sin `arxiv_id`, intentar en orden `EPRINT → ADS_PDF/ADS_SCAN
→ PUB_PDF` vía la API de links/resolver de ADS, y/o resolver por DOI al publisher — todo determinista, sin
tokens. Los que ni así se consigan, **reportarlos** (caso residual a mano).

**A verificar antes de codificar:** qué devuelve realmente la ADS API (`/v1/resolver` o el campo
`esources`), y si `ADS_SCAN`/`PUB_PDF` se bajan con el mismo token (algunos requieren acceso
institucional).

> **✅ Probe del resolver corrido (2026-07-17) — `fetch_pdf.py` es VIABLE.** Testeado con el token
> ADS sobre 3 clásicos pre-arXiv (Wilson 1978, Noyes 1984, Saar & Brandenburg 1999):
> - `GET /v1/resolver/<bibcode>/esource` (Bearer token) lista las fuentes por tipo
>   (`ADS_PDF`, `ADS_SCAN`, `PUB_PDF`, `EPRINT_*`).
> - **`ADS_PDF` (`articles.adsabs.harvard.edu/pdf/<bibcode>`) BAJA con el token** en el header
>   (200, PDF real con capa OCR de ADS, greppable): el 403 del episodio Saar era por pedirlo
>   **sin** el Bearer. Sin token sigue fallando.
> - El host **throttlea ráfagas** (una bajada dio `000` y salió al retry) → mismo patrón
>   retry/backoff + sleep que `fetch_arxiv.py`.
> - `PUB_PDF` (IOP `stacks.iop.org`) entregó el PDF a un GET pelado con UA de navegador —
>   variable por publisher/red (el episodio previo reportó captcha): intentar y degradar.
> - Orden sugerido para `fetch_pdf.py`: `EPRINT_PDF → ADS_PDF/ADS_SCAN (con token) → PUB_PDF
>   (sin token, UA normal)`; lo que no salga → `pending` (fallback ya existente).

**Hallazgos testeados (2026-07-01, episodio Saar & Brandenburg 1999 en la instancia Actividad).** Reglas
concretas para el futuro `fetch_pdf.py` y para la guía del skill (ya reflejadas en `ingest-star/SKILL.md`):
- El **escaneo ADS** directo (`articles.adsabs.harvard.edu/pdf/<bibcode>`) devolvió **403** sin sesión; el
  gateway `.../link_gateway/<bibcode>/{ADS_PDF,PUB_PDF}` y el `/pdf` del publisher devuelven **HTML/captcha**
  a un fetch automático (necesitan sesión institucional del navegador). → la parte determinista tiene techo:
  para paywall/captcha el fallback real es **pedir el PDF al usuario**.
- **Gana el dato sin el PDF:** en artículos viejos las **tablas son imágenes** servidas por el CDN del
  publisher (IOP: `content.cld.iop.org/journals/<...>/<vol>/<pag>/revision1/tbN.gif`) y **se bajan sin
  paywall**. Para papers de survey donde sólo interesa la fila de una estrella, bajar el `tbN.gif` alcanza.
  También existe el **HTML legacy** (`iopscience.iop.org/article/<doi>/fulltext/NNNNN.text.html`) con el
  cuerpo (no las tablas).
- **El índice full-text de ADS de escaneos viejos es incompleto:** su OCR **pierde ~½ de las filas** de
  tabla (12/26 estrellas en Saar 1999) → un `full:"HD X" → 0` es **inconcluso, no ausencia**. Implicación
  para código: no marcar "no está" desde un full-text negativo; y el barrido full-text por estrella (paso 2b
  del skill) debe listar **todo** el core, no top-N por citas.
- **No todo PDF necesita OCR:** el de Saar 1999 traía **capa de texto** (`pdftotext` lo sacó entero, tablas
  incluidas), con quirks de PostScript viejo (`-` y `>` → `[`). Chequear capa de texto antes de OCR.

## ✅ Backlog de framework (RESUELTO 2026-07-01) — `defuddle` para el modo off-ADS de `ingest-topic`

> Surgido de una discusión (2026-07-01) sobre si conviene adoptar los **skills oficiales de Obsidian**
> (`kepano/obsidian-skills`, de Steph Ango). Conclusión: para el flujo de Almagesto la ventaja es
> marginal-a-negativa y **una sola pieza del pack encaja** — la anoto acá; el resto se descarta abajo.

**Contexto.** El pack oficial trae 5 skills: `obsidian-markdown`, `obsidian-bases`, `json-canvas`,
`obsidian-cli`, `defuddle`. Hay además una ruta **MCP** (plugin Local REST API + `mcp-obsidian`) que
expone read/search/write del vault por HTTP con Obsidian abierto.

**Por qué se descartan casi todos (para no re-discutirlo).**
- `obsidian-markdown` → redundante y potencialmente en conflicto: el contrato de frontmatter + convenciones
  (`$...$`, kebab-case, disclaimers) ya están codificados y son **más estrictos** que la sintaxis OFM genérica.
- `obsidian-bases` → el vault usa **Dataview** (`FROM "papers"`), no Bases; migrar sería un cambio de todo el
  esquema, no un win gratis.
- `json-canvas` → artefacto visual/humano; Almagesto es machine-first (frontmatter+lint+git) y el grafo ya
  lo da Obsidian nativo. No es bibliografía citable.
- `obsidian-cli` **y la ruta MCP** → **exigen Obsidian corriendo** (app + plugin/CLI, cert self-signed,
  bearer token). Chocan con el principio de **headless/portabilidad** (memoria in-repo, scripts desde raíz,
  que viaje entre máquinas) y no aportan nada que no cubra ya el acceso directo a FS + grep.

**Lo único a evaluar — `defuddle`.** Extrae markdown limpio de páginas web quitando clutter (menos tokens)
[documentado: `kepano/defuddle`]. Encaja con el **modo off-ADS** de `ingest-topic`, que guarda snapshots web
como `.txt` **deterministas** (URL + fecha) para citabilidad. Hoy esa extracción va por `WebFetch`.

**Evaluado 2026-07-01 (rama `exp/defuddle-offads`) → conviene.** Números (una página de Wikipedia,
ejemplo off-ADS): defuddle 60 KB vs pandoc 235 KB vs HTML crudo 480 KB (~4×/~8× menos);
**determinista** (dos corridas byte-idénticas); 0 hits de clutter (vs 34 en pandoc); conserva cuerpo,
referencias (DOI/arXiv/bibcode) y matemática. Supera a `WebFetch` para este uso porque WebFetch es
model-based (no determinista, no es snapshot verbatim) y el snapshot citable **exige** determinismo.
Caveats: dependencia **Node/npm** (off-ADS es opt-in y raro → aceptable) y algún artefacto HTML suelto
(un bloque `<video>` quedó sin limpiar). Es una **utilidad general**, no Obsidian-específica: se adopta
sola, sin el resto del pack ni la ruta MCP.

**Implementado (mergeado a `main`: commits `70fc899` / `d21f70c` / `c59fa52`):**
- `scripts/fetch_web.py` — `npx defuddle parse <url> --markdown` → `vault/raw/fulltext/<slug>/<clave>.txt`
  con encabezado URL+fecha; valida la clave contra `BIBCODE_RE`, idempotente salvo `--force`, error
  amigable si falta Node. **Post-clean determinista** (`clean_markdown`) que saca los bloques HTML de
  media/embed sueltos (`<video>/<audio>/<iframe>/<svg>/<picture>` + `<source>/<track>`) → resuelve el
  artefacto `<video>` (probado: 0 residuales).
- **Creación automática de la nota de paper:** `make_notes.write_web_paper_note()` + modo CLI
  `make_notes.py --web` (reusa el template de frontmatter de las notas ADS → un solo lugar de verdad);
  `fetch_web.py` la llama tras el snapshot (salvo `--no-note`). Stub con `pdf: null`, `arxiv_id/doi: null`,
  `source_url` + `accessed` (la **fecha del snapshot**, tomada del `.txt` → coinciden), `bibstem` = venue o
  dominio de la URL, `thesis_links` al concept, `tags: [paper, web]`, `generator` estampado. El modo
  standalone cubre también fuentes **PDF** off-ADS (sin URL → `source_url`/`accessed` null).
- Wiring en `ingest-topic/SKILL.md` (v1.0.0→1.1.0): el bullet **Web** y el ex-"notas a mano" reflejan el
  flujo automatizado, con WebFetch + `make_notes --web` como fallback sin Node.
**Resuelto:** mergeado a `main`; nada pendiente.

## Backlog de framework — revisión profunda 2026-07-03 (tanda 3 pendiente)

> De la revisión completa del proyecto (code review de `scripts/` + consistencia docs↔skills +
> relevamiento de proyectos similares; informe local en `outputs/revision-2026-07-03.md`, gitignored).
> **Aplicado:** tanda 1 (bugs de scripts: Range/200 en fetch_arxiv, idempotencia envenenada, gate
> `--force` en ground-truth, exit code del lint, retry/truncado en query_ads, encoding utf-8) y
> tanda 2 (matriz método×estrella seed, política de archivado alineada, paso 1c→`--probe`,
> `git lfs install` en README, `lit_caveat`→`disputes[]`, formato de log). Queda la **tanda 3**,
> por valor:

1. ✅ **HECHO (estrellas, 2026-07-03)** — **Citation chaining en el ingest**: `query_ads.py` pide
   `references()`/`citations()` de los core, **ancladas server-side** con `full:` de nombre+alias
   (sin ancla el grafo devuelve los mega-citados genéricos del área — medido: 31/31 falsos positivos
   en tau Ceti; con ancla trae exactamente los surveys/catálogos que el barrido 2b cazaba a mano,
   p. ej. Wilson 1978 / Mount Wilson). Provenance `via: chain:*` en `ads.json`; `--no-chain`
   desactiva. **Abierto:** nada — el chaining de temas se resolvió en el ítem 7(c) y el fetch de
   PDFs viejos en `fetch_pdf.py` (2026-07-17, sección arriba).
2. ✅ **HECHO (completado 2026-07-17)** — ✅ **Veredicto `contradice` en `verify-citations`** (4
   categorías estilo CAQA; `contradice` manda sobre el score y se resuelve como corrección o disputa
   `planets[].disputes[]`, no como cita rota; CLAUDE.md/README). ✅ (2026-07-17) **auto-benchmark
   del verificador** (CiteAudit): `scripts/bench_verify.py seed` siembra citas falsas deterministas
   entre pares reales de queries/concepts (misma afirmación, bibcode rotado — excluyendo los que la
   afirmación cita de verdad, para no plantar falsos-falsos); el skill (modo benchmark, v1.2.0) las
   verifica **a ciegas** (el subagente nunca ve etiquetas) y `score` reporta recall de sembradas +
   reales caídas en `outputs/verify-bench-*.md`. Nada del benchmark toca `vault/`. La citation
   precision por nota (ALCE) se descartó por frágil (ítem 7); la cobertura del lint cubre lo accionable.
3. ✅ **HECHO (2026-07-03)** — **Detección batch de contradicciones**: skill `find-contradictions`
   (v1.0.0). Barre un eje (estrella/parámetro o concepto), confirma cada desacuerdo claim↔claim con un
   subagente por par que lee los **dos** fulltext (`real|aparente|no-concluyente` + cita de ambos
   lados) y **propone** disputas (`planets[].disputes[]` con NEA como verdad; línea citando ambos
   `[[bibcode]]` para conceptos) que el usuario aprueba antes de escribir. Ortogonal a
   `verify-citations` (claim↔su fuente vs claim↔claim entre fuentes).
4. ✅ **HECHO (2026-07-03)** — **Chequeo de retracciones**: `scripts/check_retractions.py` consulta
   **Crossref** por DOI (señal determinista: `updated-by` con `type: retraction|removal|withdrawal`;
   ADS no expone `property:retracted` — sólo prefijo de título, que se usa de fallback para papers sin
   DOI), estampa `retracted: true` + `retraction{...}` en la nota (idempotente, viaja en git) y el
   `lint.py` la surface **offline como categoría bloqueante**. En la cadena de `ingest-star`/`-topic`
   y a correr periódicamente. Errata/EoC → aviso blando (no retracta).
5. **Vocabulario AstroMLab 5** (arXiv:2511.12353) como diccionario de referencia para
   `topics`/`methods`/`aliases` (anti drift taxonómico). **Recurso verificado 2026-07-03** — existe y
   sirve: repo `github.com/tingyuansen/astro-ph_knowledge_graph`, poblado, con
   `concepts_vocabulary.csv.gz` (9.999 conceptos: label/class/nombre/descripción) + embeddings
   `.npz` (9999×3072, `text-embedding-3-large`). **Bloqueante para adoptar: SIN licencia declarada**
   (README dice "enfoque conservador" pero no MIT/CC) → NO se puede vendorear en un template MIT; el
   camino limpio sería `fetch_vocab.py` que **el usuario** baja el CSV a ruta gitignoreada + WARN del
   lint sugiriendo el concepto canónico más cercano por **string/fuzzy match** contra los nombres del
   CSV (ignorar los embeddings → evita la dependencia de OpenAI). **Prioridad baja / EN OBSERVACIÓN**:
   payoff sólo con la bóveda ya grande. **Re-evaluar cuando** (a) el repo declare una licencia
   permisiva (hoy el bloqueante) — chequear `github.com/tingyuansen/astro-ph_knowledge_graph/LICENSE
   periódicamente — o (b) la bóveda alcance volumen y el drift taxonómico se vuelva medible. Hasta
   entonces no se implementa. **Re-chequeado 2026-07-17: sigue sin licencia** — GitHub API
   `license: null` (sin archivo LICENSE); el `## License` del README sólo lista las licencias de las
   FUENTES agregadas (arXiv non-exclusive, ADS) y pide respetarlas, **sin grant propio del dataset**;
   último push del repo 2025-11-15 (nada cambió desde la evaluación de 2026-07-03).
6. ✅ **HECHO (2026-07-03)** — **Skill de mantenimiento** `maintain` (v1.0.0): opera sobre entidades
   **ya ingestadas** — refrescar (papers nuevos → re-sintetizar sólo lo nuevo), borrar (nota + PDF +
   reparar colgados), renombrar slug, re-clasificar tras cambiar `relevance.topics`, y resolver el
   backlog del lint. Invariante: cadena idempotente; extracción LLM y ground-truth no se pisan sin
   `--force`.
7. ✅ **HECHO (2026-07-03)** — **Menores**: (a) `--probe` ahora lista **todo el core** (no top-25);
   (b) **curación persistente** `extra_core: [bibcode]` en stars/topics.yaml (`via: manual`, sobrevive
   al re-run); (c) **chaining para TEMAS** anclado a la propia query del tema (verificado: +9 core en
   un tema de prueba); (d) **cobertura de verificación** en el lint (query/concepto con citas pero sin
   bloque `verify-citations` → backlog ALCE-adjacent); (e) **pre-commit hook** `scripts/hooks/pre-commit`
   (corre el lint, bloquea si hay bloqueantes; activar con `git config core.hooksPath scripts/hooks`).
   Todo verificado contra ADS/lint. **Queda sólo:** el vocabulario AstroMLab (ítem 5, en observación
   por licencia) — el fetch de PDFs viejos vía `esources` se resolvió el 2026-07-17 (`fetch_pdf.py`,
   sección arriba). La citation precision "dura" (parsear X/N del bloque de verify) se
   descartó por frágil; la **cobertura** de (d) cubre la parte accionable.
