# Almagesto — schema de la wiki de conocimiento astro (instrucciones para el agente)

Esta es una **LLM wiki** (patrón Karpathy) sobre literatura astronómica, organizada por **estrella**
y por **concepto**. **El OBJETIVO de la bóveda vive en `vault/config/objective.yaml`** (editable): define de
qué trata esta wiki y —vía `relevance.topics`— **qué papers son "core"**. Leé ese archivo al iniciar
para saber sobre qué estás trabajando. Vos (Claude) **sos el dueño de `vault/wiki/`**: la creás y mantenés.
El usuario cura las fuentes (`vault/raw/`) y hace preguntas.

> Este archivo es el **schema genérico** (forma astro: estrellas, planetas, indicadores de actividad,
> ground-truth de exoplanetas). Lo único específico de cada instancia es `vault/config/objective.yaml` + el
> contenido de `vault/wiki/`/`vault/raw/`. Para instanciar una bóveda nueva ver `README.md` (sección *Instanciar*).

> **Al iniciar sesión, leé `vault/STATUS.md` (estado + próximos pasos) y `vault/wiki/log.md` (historial
> reciente) para orientarte.** La "memoria" del proyecto es in-repo: este `CLAUDE.md` + `vault/STATUS.md`
> + `vault/wiki/log.md` + `vault/wiki/index.md`. No depender de la memoria local de Claude (`~/.claude/...`),
> que no viaja entre máquinas. Tras cada operación, actualizá `index.md`, appendeá a `log.md`
> (entrada `## AAAA-MM-DD — <op>: <título>` + bullets — greppable por fecha) y, si cambió el estado,
> `vault/STATUS.md`.

## Layout del repo — la bóveda vive en `vault/`

El repo separa **andamiaje** (raíz) de **bóveda** (`vault/`):

```
Almagesto/
├── CLAUDE.md  README.md  requirements.txt  scripts/  .claude/skills/   ← andamiaje (framework)
├── build/  outputs/                                                    ← scratch del tooling (gitignored)
└── vault/                                                              ← la bóveda — Obsidian abre ACÁ
    ├── config/  (objective.yaml, stars.yaml, topics.yaml, ads_dev_key)
    ├── wiki/    (stars, papers, concepts, queries, matrices, index.md, log.md)
    ├── raw/     (pdfs, fulltext, ground_truth, refs)
    ├── STATUS.md
    └── .obsidian/
```

**Reglas de ruta (no romper):**
- **Todo el contenido cuelga de `vault/`.** En este documento y en los skills las rutas de contenido
  se escriben **repo-root-relative** con prefijo `vault/` (p. ej. `vault/raw/fulltext/…`), porque los
  scripts y greps se corren **desde la raíz del repo**.
- **Excepción Obsidian-space:** dentro de notas `.md` de `vault/`, los `[[wikilink]]`, las queries
  Dataview (`FROM "wiki/papers"`) y los links relativos (`../../raw/pdfs/…`) son
  **relativos a la raíz del vault** (`vault/`) — **no** llevan el prefijo `vault/`.
- Los scripts resuelven solos vía `scripts/lib_config.py` (`VAULT = ROOT/"vault"`); no hardcodear rutas.
- `build/` y `outputs/` son scratch regenerable: viven en la **raíz**, FUERA de `vault/`, para no
  contaminar la bóveda de Obsidian.

## Framework vs instancia — Regla de oro (no editar framework en la instancia)

Esta bóveda puede estar corriendo como **instancia** del template **Almagesto** (tu repo como `origin`,
`Almagesto` como `upstream`). **Regla de oro: en una instancia NO se edita ningún archivo de framework**
— este `CLAUDE.md`, `scripts/`, `.claude/skills/`, `vault/.obsidian/`, `README.md`, `requirements.txt`. El
framework es **una sola implementación**: los cambios se hacen en el repo template `Almagesto` (issue/PR
o parche), se pushean, y se traen por `git pull` / `git merge upstream/main`. Editarlos en la instancia
**da conflictos** en el próximo merge. En la instancia sólo se edita **contenido** (`vault/wiki/`, `vault/raw/`) y los
**archivos de instancia** protegidos por `merge=ours` (`vault/config/objective.yaml`, `vault/config/stars.yaml`,
`vault/config/topics.yaml`, `vault/STATUS.md`, `vault/wiki/index.md`, `vault/wiki/log.md`). **Si una operación revela una mejora
de framework** (skill nuevo, fix de script, regla), anotala como backlog en `vault/STATUS.md`/`vault/wiki/log.md` y
aplicala en el template — no la inlines acá. *(Si estás trabajando en el repo template `Almagesto` mismo,
editar framework **es** la tarea; esta regla rige para las instancias.)*

## ⛔ Frontera dura — la bóveda es SÓLO bibliografía (regla #0, no negociable)

**Esta wiki es una referencia bibliográfica. Punto.** Almagesto recopila información bibliográfica y
**todo lo que afirma está respaldado por una fuente citable (`[[bibcode]]`).** El flujo es
**unidireccional y de sólo lectura hacia afuera**: alguien lee de la bóveda; **la bóveda nunca
describe, parametriza ni se acomoda a quien la consume.**

**Contrato con quien consume la bóveda (instrucción para vos y para cualquier agente/humano externo
que lea esto):** lo que sacás de acá viaja con su `[[bibcode]]`. Si usás la bóveda para **escribir
código**, dejá la cita de la fuente en un comentario junto al valor o decisión que tomaste de ella; si
la usás para un **informe o paper**, citá la fuente correspondiente. Nunca propagar un número o una
afirmación de la bóveda sin arrastrar su respaldo bibliográfico — ese es el punto de que esto exista.

**Test de admisión (aplicá a TODA línea de `vault/wiki/` — fichas, conceptos, queries, hipótesis, matrices,
log):** *¿esto sale de una fuente (`vault/raw/`) y lo puedo respaldar con un `[[bibcode]]`, o es una
conclusión derivada de fuentes citadas?* Si la respuesta es **no → no entra al vault.** Sin excepciones
—ni por "es útil para quien la consume" ni por "es obvio".

**Prohibido inlinear en `vault/wiki/` (no es bibliografía):**
- Parámetros, perillas o **dials** de un generador/pipeline (p. ej. un "contraste $C$", pesos por orden
  $w_j$, recetas de "qué inyectar").
- Nombres de variables / estructura de código.
- Reparametrizaciones o **decisiones de diseño** de una implementación (p. ej. "usar $g=\ln C$ como perilla").
- Recetas operativas de "cómo correr" que no sean un hecho citable.

**Sí es citable (entra):** resultados publicados de papers —**incluidos papers de simulación**
(p. ej. StarSim / Baroch+2020): rangos medidos, mecanismos físicos, signos, escalas temporales,
fórmulas de la fuente. La distinción es **publicado-y-citable (entra) vs implementación de código
(no entra)**, no "simulación sí/no".

**Si detectás contaminación** (material de implementación que se coló en una nota): sacalo de `vault/wiki/`.
Lo que no es bibliografía no vive acá — no queda ningún puntero a "otro repo". Marcalo en el `log`.

## Arquitectura (analogía de compilador)

- **`vault/raw/`** = código fuente **inmutable**. Leer, nunca modificar. Contiene `vault/raw/pdfs/<slug>/`
  (git-lfs), `vault/raw/fulltext/<slug>/*.txt` (texto para grep/lectura barata) y
  `vault/raw/ground_truth/<slug>.json` (hechos de NASA Exoplanet Archive + SIMBAD, fuente de verdad dura).
- **el LLM** = compilador.
- **`vault/wiki/`** = ejecutable. `.md` que escribís vos: `stars/` (entidades), `papers/` (resúmenes de
  fuente), `concepts/{indicators,methods,activity,hypotheses}/`, `queries/`, `matrices/`,
  `index.md` (catálogo) y `log.md` (registro append-only).
- **lint** = tests. **queries** = runtime.
- **este `CLAUDE.md`** = schema (cómo te comportás).

Divergencia deliberada respecto del patrón Karpathy (mantener): el frontmatter de `stars/` y
`papers/` es **máquina-legible** y sirve de **contrato para cualquier consumidor** (un agente o humano
que arme código, un informe o un paper a partir de la bóveda), no es sólo para Q&A humano. No romper
esos campos.

## Frontmatter obligatorio

Toda nota de `vault/wiki/` lleva frontmatter YAML. Campos comunes: `tags`, `generator`
(`Almagesto v<x>`, provenance — lo estampa `make_notes` desde `lib_config.ALMAGESTO_VERSION`), y
cuando aplique `confidence: high|medium|low`. Schemas específicos:
- **stars/**: `name, slug, aliases, simbad_id, spectral_type, teff_K, dist_pc, P_rot_days,
  activity_indicators_expected, planets[], data_local, methods_applied{literature,ours}`. Cada
  `planets[]` lleva `letter, P_days, K_ms, e, mass_earth, status` (de ground-truth NEA; `mass_earth`
  RV-only ≈ $m\sin i$) + `disputes[]` cuando un paper discrepa. El cuerpo trae además una sección
  **`## Huecos`** (qué falta para que la ficha alcance sola: parámetros sin valor, señales sin árbitro,
  métodos no aplicados) y un apéndice **`## Excluidos por el filtro`** (snapshot de los no-core, top por
  citas con link a ADS — puntero por las dudas, no se bajan). El blockquote de cabecera lleva un
  **disclaimer ⚠ de capa-LLM** (la prosa es síntesis LLM a revisar; el ground-truth del frontmatter es
  auditable) — va en blockquote, así el lint lo exime del scan de fuga.
  **Estándar de la ficha: autosuficiente.** La ficha de estrella debe alcanzar por sí sola —
  un agente (o humano) que la lee queda servido **sin abrir ningún paper**. Es una ficha
  bibliográfica: **corta y suficiente**, con todos los datos importantes destilados (parámetros
  estelares, inventario de señales RV con $P/K/e/m\sin i$ y estado, señales disputadas/descartadas,
  indicadores de actividad esperados, métodos aplicados y huecos). Los `[[bibcode]]` son
  **referencia/trazabilidad** (de qué paper salió cada afirmación), **no** lectura obligatoria para
  entender la estrella. Si para responder algo hace falta abrir el paper, eso que falta debería
  estar en la ficha → agregarlo.
  **Regla de poda (paper secundario → ficha sólo si cambia una señal RV):** un hecho de un paper
  tangencial (no discovery / no árbitro de planetas / no actividad-P_rot) entra a la prosa de la
  ficha **únicamente si cambia cómo se lee una señal RV** (p. ej. un mecanismo que produce falsos
  positivos en el régimen de período de un planeta dudoso). Todo lo demás (era instrumental,
  metodología RV genérica, dinámica/estabilidad, ausencia de tránsito/compañera, debris,
  astrosismología, habitabilidad) **no se inlinea**: vive en su nota de paper y se consulta por la
  tabla Dataview `## Papers` de la ficha (que lista todo paper con la estrella en `stars:`). No
  re-narrar en la ficha lo que ya está en la extracción del paper. Esto mantiene la ficha **compacta**
  (rápida de ingestar, sin perder contexto) sin perder trazabilidad.
  **Disputas (`planets[].disputes`):** NEA (ground-truth) es **siempre el valor de verdad**; cuando
  un paper discrepa —sea sobre la **existencia** de la señal o sobre el **valor** de un parámetro—
  se taguea, no se sobreescribe. Cada entrada: `field` (`existence` o el parámetro: `P|K|e|msini`),
  `ref` (bibcode discrepante, **debe** existir como nota de paper — lo chequea el lint), `note`
  (qué dice ese paper) y, para disputas de valor, `alt` (el valor según ese paper). Convención
  **simétrica** existencia↔valor. Sólo taguear discrepancias **materiales** (mayores que el error;
  no diferencias cosméticas dentro de la barra). Reflejar la disputa también en la tabla/prosa.
- **papers/**: `bibcode, title, first_author, n_authors, year, arxiv_id, doi, bibstem, stars[], topics[], methods[],
  thesis_links[], bearing(supports|challenges|method), relevance, citation_count, pdf`.
- **concepts/ (áreas **abiertas** — cualquiera según el foco de la bóveda; `concept_areas` en
  `vault/config/objective.yaml` es sólo referencia para el typo-check, con `methods`/`hypotheses` reservadas)**: `name`, **`aliases`** (lista de sinónimos EN+ES —
  p. ej. `[chromatic index, índice cromático, RV-color]` — para que la ficha se encuentre por `grep`
  desde **cualquier término**, no sólo el nombre canónico; espeja la idea de `aliases` de `stars/`),
  `tags`, `confidence`. El cuerpo trae `## Síntesis`, `## Huecos` y el apéndice `## Excluidos por el
  filtro` (igual que la ficha de estrella). Rige el *Estándar transversal* (autosuficiente + implementation-ready).
- **concepts/hypotheses/**: `name, status`; el roll-up de evidencia es por Dataview sobre
  `thesis_links`.

**Estándar transversal de autosuficiencia (toda nota apuntable).** El estándar "autosuficiente" de
`stars/` rige **igual** para `concepts/` (indicadores, métodos, actividad, hipótesis) y para las
`queries/` que se archiven: la nota debe **alcanzar por sí sola**, ser **dual-audiencia (humano y
modelo)** y llevar `[[bibcode]]` en cada afirmación para **citar/trazar** (un agente redactando un
informe saca de la nota las referencias correctas sin abrir el paper). Requisitos extra por tipo:
- **métodos e indicadores** (`concepts/methods`, `concepts/indicators`): además
  **implementation-ready** — ecuaciones, inputs/outputs y pasos suficientes para **codificar el método
  tal como lo detallan los papers, sin abrir la fuente**; el detalle fino vive en los `[[links]]`.
- **queries/hypotheses**: pregunta, **búsqueda reproducible** (el `grep` usado), evidencia citada
  for/against con `bearing`, y veredicto.
Si para implementar o citar algo hace falta abrir el paper, eso que falta **debe agregarse a la nota**.

Convenciones: filenames kebab-case (papers usan el bibcode); links internos `[[wikilink]]` por
nombre de nota (sobreviven a mover carpetas); reportar agregados declarando mean vs median.
**Notación matemática según destino:** en archivos de `vault/wiki/` SIEMPRE `$...$` (Obsidian lo renderiza);
en **respuestas de consola/chat** usar **texto plano** (`P_rot`, `m·sini`, `K=2.5 m/s`), porque la
terminal no renderiza LaTeX y `$...$` se ve crudo.

## Operaciones

### Setup (definir el objetivo — paso 0, skill `setup`)
Genera/afina `vault/config/objective.yaml` (la **lente**: `name`/`description` + `relevance.topics`, el
clasificador de papers core). El agente traduce el foco del usuario (en palabras) a la regex — el usuario
**no** escribe regex — y la valida contra papers reales con `python scripts/query_ads.py --probe "<query>"`
(muestra el corte core/no-core sin bajar nada) iterando hasta que cierre. `relevance.topics` son **facetas**
(constantes; clasifican tanto papers de estrella como de tema), **no** sujetos (las estrellas/temas van en
la query, `stars.yaml`/`topics.yaml`). No ingesta nada; después se usan `ingest-star`/`ingest-topic`.

### Ingest (una fuente → cascada de páginas)
1. Scripts de `scripts/` bajan: `query_ads.py` → `fetch_arxiv.py` → `fetch_ground_truth.py` →
   `make_notes.py` → `extract_fulltext.py` (stubs mecánicos; idempotente, no pisa).
2. **Vos (LLM)** leés el PDF/fulltext y hacés la cascada: poblás la extracción del paper
   (`methods`, `thesis_links`, `bearing`, P/K/indicadores), actualizás la ficha de la estrella
   (síntesis, huecos), tocás conceptos/hipótesis relacionados y la matriz método×estrella.
3. Actualizás `index.md` y appendeás a `log.md`.

> **Tema no-astro / fuera de ADS (opt-in — sólo a pedido explícito).** Por default un tema se baja por
> **ADS** (plomería astro: ADS/arXiv/NEA). Almagesto es astro por estructura, pero si el usuario pide
> **explícitamente** un tema **no-astro** o cuya bibliografía vive **fuera de ADS** (p. ej. un método
> matemático general: ICA, signal processing), el skill `ingest-topic` lo soporta en su **modo off-ADS**
> (fuente = PDFs locales + web; sin `query_ads`/`fetch_ground_truth`). **`ingest-star` no cambia: es
> astro-only.** Papers sin bibcode ADS → **clave de cita sintética `AAAA+Autor`** (debe empezar con
> `AAAA`+letra para el lint; el `.txt` en `vault/raw/fulltext/` se llama igual). Páginas web → **snapshot
> `.txt` determinista** (URL + fecha; lo genera `scripts/fetch_web.py` vía defuddle y crea además el
> stub de la nota de paper) para que sea citable/verificable. La **frontera dura sigue
> rigiendo**: sólo bibliografía citable.

### Query / hipótesis (pregunta → respuesta; archivar SÓLO si el usuario lo pide)
1. Para búsqueda general o test de hipótesis: `grep` sobre `vault/raw/fulltext/`, leé los hits, sintetizá
   con citas `[[bibcode]]` y **respondé en el chat**.
2. **No archivar por default.** Persistir una query (`queries/<x>.md`) o una hipótesis
   (`concepts/hypotheses/`) es **decisión explícita del usuario** — sin pedido, la respuesta vive
   sólo en la conversación. (Las estrellas y conceptos sí se persisten porque el **ingest es de por sí
   una operación explícita**; las consultas/hipótesis no, para no llenar la wiki de notas no deseadas.)
3. Cuando el usuario **pide** guardarla, la nota debe cumplir el **mismo estándar que una ficha**
   (autosuficiente + dual-audiencia + citas `[[bibcode]]` + links; ver *Estándar transversal* arriba).
   Si es test de hipótesis, taggeá los papers (`thesis_links`, `bearing`) para el roll-up.
4. Distinción: **hipótesis** (supuesto durable que sostenés) → `concepts/hypotheses/`; **búsqueda
   general** → `queries/`. No toda query es hipótesis.

### Verify (chequeo claim↔fuente — skill `verify-citations`)
**Extensión propia de esta wiki** (el lint canónico de Karpathy NO valida que la fuente respalde la
afirmación — sólo salud estructural; tapa el *grounding gap* / *epistemic drift*). **Cuándo:** paso de
cierre de **toda operación que escriba prosa con `[[bibcode]]`** — ingest-star (ficha + papers),
ingest-topic (concept + papers), query archivada, test de hipótesis — **antes de lint/commit**.
**Qué hace:** descompone la nota en pares (afirmación, `[[bibcode]]`) y lanza **un subagente
independiente por par** que lee SÓLO ese `vault/raw/fulltext/**/<bibcode>.txt` (grounding-first, prohibido de
memoria) y devuelve `soportada|parcial|no-soportada|contradice` + **cita textual + nº de línea del `.txt`**
(obligatoria; sin cita ⇒ no-soportada). `no-soportada` = la fuente **calla**; `contradice` = la fuente
**afirma lo contrario** → no es (sólo) cita rota: es corrección de la nota o **disputa** a taguear
(`planets[].disputes[]` si es parámetro planetario). Cada falla se **resuelve** (bajar la afirmación
a lo que dice la fuente, reasignar la cita al bibcode correcto, marcar **`inferencia`**, o taguear la
disputa) y se deja un bloque `## Verificación de citas` en la nota. El `.txt` es extracción **determinista** (`pdftotext`), así que
la cita son las palabras reales del paper; si una afirmación no aparece (artefacto de extracción:
ecuación/tabla/escaneo) abrir el PDF o marcar `no verificable por extracción`. Es **juicio de LLM**,
robusto pero no prueba. **Regla dura — todo lo apuntable es chequeable:** toda afirmación fáctica va
**citada `[[bibcode]]` o marcada `inferencia`** — nada sin respaldo. Excepción: los **valores de
ground-truth (NEA)** en `stars/` (P/K/e/m·sini) no se verifican contra papers (su consistencia la
chequea el lint); sólo se verifican disputas y afirmaciones atribuidas a un paper. El lint reporta como
backlog los conceptos/hipótesis **sin ninguna cita** (cobertura: afirman sin fuente → no chequeables).

### Lint (chequeo de salud)
**Cuándo:** como **paso de cierre de toda operación que escriba en `vault/wiki/`** (ingest / query archivada
/ test de hipótesis), **antes de commitear**; más una pasada completa periódica. Es barato.
Correr `python scripts/lint.py`: debe quedar en **0** para wikilinks rotos, páginas huérfanas,
contradicciones ground-truth↔ficha, **masa de ground-truth inconsistente con la m·sini implícita**
(K/P/e/M\* — atrapa best-mass espurias de NEA), **`thesis_links` sin página destino** (tag que no matchea
ninguna nota → no acumula en el roll-up; typo típico `shift-vs-shape` vs `shift_vs_shape`) y
**`planets[].disputes[].ref` sin paper destino** (bibcode discrepante que no existe como nota). La
**fuga de implementación** (regla #0 / frontera dura) es **WARN no bloqueante** — heurística de alta
señal (perilla/dial/`w_j`/`peso(`); cada hit se revisa a mano y se saca del vault si es material de
implementación (no es bibliografía). Las **áreas de `concepts/` fuera de `concept_areas`** (subcarpeta no
declarada en `vault/config/objective.yaml`) son **WARN** — las áreas son **abiertas**: la lista es sólo
referencia para distinguir un typo de un área nueva, **nunca se bloquea** (`make_notes` **avisa** pero crea
igual; el lint marca las carpetas fuera de la lista). El **PDF ↔ disco** es **WARN/higiene**: marca un paper
cuyo campo `pdf` no refleja el PDF real — está bajado en `vault/raw/pdfs/<slug>/<bibcode>.pdf` pero el
frontmatter quedó `null` (drift, hay que linkearlo) o apunta a un archivo inexistente (puntero roto). Las **citas no verificables** (bibcode citado en query/concepto/hipótesis sin su `.txt` en
`vault/raw/fulltext/`) se listan como precondición de `verify-citations`. La **cobertura** (concepto/hipótesis
sin ninguna cita `[[bibcode]]` → afirma sin fuente) es **backlog** que el lint surface para ir citando.
Los "campos incompletos" (P_rot null, papers sin `methods`, etc.) son **backlog**, no bloquean. Revisar
además a mano: claims stale y conceptos referidos sin página. Si faltan datos, abrir queries para
imputar (web/ADS).

## Token / secretos
El token ADS va en `vault/config/ads_dev_key` (**gitignored** — nunca se commitea) o en la variable de
entorno `ADS_DEV_KEY`. Token gratis en <https://ui.adsabs.harvard.edu/user/settings/token>.
`build/` y `outputs/` gitignored. PDFs por git-lfs (`vault/raw/pdfs/**/*.pdf`).
