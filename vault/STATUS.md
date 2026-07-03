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
3. 🟡 **PARCIAL** — **check de config (lint, WARN blando)**. ✅ Áreas (abiertas, nunca se bloquea):
   `make_notes` **avisa** si el `area` no está en `concept_areas` pero crea igual; `lint.py` marca **WARN**
   las carpetas de `concepts/` fuera de la lista (atrapa typos sin restringir). ⏳ Falta el resto de los guards de config: `KeyError`
   amigable en los índices duros (`ads_object`/`simbad` en stars, `query`/`concept` en topics) y **WARN si
   `objective.name` sigue siendo el default** (olvido de instanciar).

**Preguntas abiertas — resueltas al implementar capas 1+3-áreas:**
- Nomenclatura → vive en `vault/config/objective.yaml` (instance-owned), con la prosa del schema en
  `CLAUDE.md` deferiendo a ella. ✅
- `methods` → **reservada** igual que `hypotheses` (universal). ✅
- El check → vive en `lint.py` (encaja con su filosofía WARN/backlog), no en un script aparte. ✅
- Pendiente de decidir (al hacer la capa 2): ¿el skill de setup **reemplaza** el flujo "editá
  `objective.yaml`" del README o lo **complementa**? (lean: complementa).

## Backlog de framework — obtención de PDFs (papers viejos / no-arXiv)

> Surgido al usar la bóveda (2026-06-29): papers **pre-arXiv / viejos** no están en arXiv, así que
> `fetch_arxiv.py` no los baja; hubo que recurrir a workarounds manuales para conseguir el PDF.

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

**Evaluado 2026-07-01 (rama `exp/defuddle-offads`) → conviene.** Números (página ICA de Wikipedia,
ejemplo off-ADS de `CLAUDE.md`): defuddle 60 KB vs pandoc 235 KB vs HTML crudo 480 KB (~4×/~8× menos);
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

1. **Citation chaining en el ingest** (`references()`/`citations()` de la API de ADS por paper core;
   ataca la brecha de recall — una sola query por keywords pierde papers, cf. episodio Saar 1999 — y
   resuelve parte del backlog "PDFs viejos" vía `esources`).
2. **Veredicto `contradice` en `verify-citations`** (hoy `no-soportada` mezcla "la fuente calla" con
   "la fuente contradice" — clave para `disputes[]`) + citation precision por nota como métrica del
   lint (estándares CAQA / ALCE; auto-benchmark sembrando citas falsas, CiteAudit).
3. **Detección batch de contradicciones entre papers** sobre la misma estrella/parámetro → proponer
   entradas `disputes[]` (estilo ContraCrow de PaperQA2; hoy se detectan a mano en el ingest).
4. **Chequeo de retracciones** (Crossref/ADS) en el lint — una fuente retractada silenciosa viola el
   contrato de la bóveda.
5. **Vocabulario AstroMLab 5** (arXiv:2511.12353; ~10k conceptos astro con descripciones/embeddings)
   como diccionario de referencia para `topics`/`methods`/`aliases` (anti drift taxonómico).
6. Menores: `--probe` imprime top-25 pero el barrido 2b de `ingest-star` pide "todo el core" (dar
   salida completa); los papers curados a mano en `build/<slug>/ads.json` se pierden al re-correr
   `query_ads` (persistir la curación); skill de mantenimiento (actualizar estrella ya ingestada,
   borrar/renombrar, re-clasificar tras cambiar `relevance.topics`); lint como hook pre-commit
   (ya es gateable por exit code).
