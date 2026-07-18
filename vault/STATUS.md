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

**Pendientes menores de eye candy (menú ofrecido, sin decidir):** social preview PNG 1280×640
(se sube a mano en Settings → Social preview), captura de Obsidian (demo con estrella famosa), GIF de
terminal (vhs) del `--probe`.

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
