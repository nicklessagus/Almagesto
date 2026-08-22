# Almagesto — schema de la wiki de conocimiento astro (instrucciones para el agente)

Esta es una **LLM wiki** (patrón Karpathy) sobre literatura astronómica, organizada por **estrella**
y por **concepto**. **El OBJETIVO de la bóveda vive en `vault/config/objective.yaml`** (editable): define de
qué trata esta wiki y —vía `relevance.topics`— **qué papers son "core"**. Leé ese archivo al iniciar
para saber sobre qué estás trabajando. Vos (Claude) **sos el dueño de `vault/wiki/`**: la creás y mantenés.
El usuario cura las fuentes (`vault/raw/`) y hace preguntas.

> Este archivo es el **schema genérico** (forma astro: estrellas, planetas, indicadores de actividad,
> ground-truth de exoplanetas). El eje **tema/concepto** y la capa de calidad (lint, verify,
> retracciones, benchmark) son agnósticos de disciplina: permiten sumar **métodos de otras
> disciplinas** (estadística, ML — modo off-ADS) al servicio del foco astro. Lo único específico de
> cada instancia es `vault/config/objective.yaml` + el
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
    ├── config/  (objective.yaml, stars.yaml, topics.yaml, ads_dev_key, registro/<slug>.yaml)
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
`vault/config/topics.yaml`, `vault/STATUS.md`, `vault/wiki/index.md`, `vault/wiki/log.md`,
`vault/wiki/matrices/method_star.md`). **Si una operación revela una mejora
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
Lo que no es bibliografía no vive acá. Marcalo en el `log`.

**Punteros a otros repos — regla afinada (prosa no, frontmatter estructural sí):** lo prohibido es
el puntero downstream **en prosa / como motivación** ("para qué sirve en <repo consumidor>", "esto
decide X en <pipeline>") — eso es describir al consumidor y rompe el flujo unidireccional. En cambio,
los **campos estructurales del frontmatter** de `stars/` —`data_local`, `methods_applied.ours`—
**sí** pueden apuntar a rutas/experimentos externos: registran *qué datos hay* y *qué se les aplicó*,
son parte del contrato máquina-legible de la ficha, no motivación. **Migración de una instancia con
prosa downstream heredada** (regla vieja → estricta): (a) borrar de notas de método/queries los
comentarios "para qué sirve en <downstream>" y la parte decisión-downstream de las disputas;
(b) `data_local`, `methods_applied.ours` y `log.md` (bitácora histórica) se quedan; (c) los links a
experimentos en la matriz método×estrella quedan a decisión de cada instancia.

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
  activity_indicators_expected, planets[], disputes[], data_local, methods_applied{literature,ours}`. Cada
  `planets[]` lleva `letter, P_days, K_ms, e, mass_earth, status` (de ground-truth NEA; `mass_earth`
  RV-only ≈ $m\sin i$). Los desacuerdos van en `disputes` **a nivel nota** (ver abajo), no dentro de
  `planets[]`.
  ⛔ **Espejo puro de NEA (#70) — los campos de arriba valen lo que dice el ground-truth o NADA.**
  `spectral_type`, `teff_K`, `dist_pc`, `P_rot_days` y los cinco campos de cada `planets[]` los
  copia el script del JSON de `vault/raw/ground_truth/`: si NEA no tiene el valor, el campo queda
  **null** y **no se rellena con literatura**. Los nulls de NEA son el caso **normal**, no la
  excepción (`pl_rvamp` y `pl_orbeccen` faltan seguido). El motivo es el contrato mismo: la cabecera
  promete que el frontmatter es la capa **auditable** frente a la prosa (síntesis LLM a revisar), y
  un número extraído por un LLM ahí queda **indistinguible** del de NEA — se borra la distinción que
  el consumidor usa. Además, adoptar un valor cuando las fuentes discrepan es **decidir por quien
  consume**, contra el flujo unidireccional de la regla #0. El valor de literatura va **al cuerpo,
  citado `[[bibcode]]`** (la autosuficiencia se cumple igual: el dato está, con su fuente); si
  discrepa de NEA es una `disputes[]`; si es lectura propia va marcado **`inferencia`**. Lo vigila el
  lint, campo por campo. El cuerpo trae además **`## Inventario por eje`**
  (el paso de contraste, ver abajo), una sección
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
  ⚠ **El puntero es resoluble sin Obsidian (#60):** los roll-ups `## Papers` y `## Métodos aplicados`
  son bloques ```dataview``` — un agente que abre el `.md` ve el **código de la query, no sus
  resultados**, y el plugin ni siquiera está versionado. Para la audiencia-modelo, que es la que este
  contrato dice servir, el equivalente determinista **parsea el frontmatter con el mismo parser que
  el tooling** (`lib_config.split_fm`), corriendo desde la raíz del repo:
  ```bash
  # papers de una estrella (equivale al roll-up `## Papers`)
  python -c "import sys,glob;sys.path.insert(0,'scripts');import lib_config as c;[print(f) for f in sorted(glob.glob('vault/wiki/papers/*.md')) if '<nombre>' in (c.split_fm(open(f,encoding='utf-8').read()).get('stars') or [])]"
  # métodos aplicados a esa estrella (equivale a `## Métodos aplicados a esta estrella`: los métodos
  # DE los papers de la estrella, no todo paper de la bóveda que use el método)
  python -c "import sys,glob;sys.path.insert(0,'scripts');import lib_config as c;[print(f,'→',fm.get('methods')) for f in sorted(glob.glob('vault/wiki/papers/*.md')) for fm in [c.split_fm(open(f,encoding='utf-8').read())] if '<nombre>' in (fm.get('stars') or []) and fm.get('methods')]"
  ```
  ⛔ **No uses `grep`/`awk` sobre el frontmatter para esto** — es un error medido **dos veces** en
  este mismo documento. (a) `grep -l 'stars:.*<nombre>'` (lo que decía hasta 1.10.1) da **0 hits**
  cuando la lista está en **bloque**, que es como la escribe `make_notes` al crear la nota. (b) El
  `awk` con ámbito de campo que lo reemplazó (1.10.2) da 0 hits cuando la lista está en **flow
  style** (`stars: [tau Cet]`), que es como la deja `merge_frontmatter_list` — o sea **todo paper
  retro-linkeado**, justo la población que el roll-up existe para recuperar. Las dos formas conviven
  en el mismo corpus. Además el matcheo textual confunde `GJ 71` con `GJ 710`, y `split_fm` compara
  por elemento. Si descargás contenido a un roll-up, es porque ese fallback lo recupera; si no, el
  contenido va inlineado en la ficha.
  **Disputas (`disputes`, a NIVEL NOTA, con posiciones explícitas — #71):** cuando dos fuentes
  discrepan sobre el mismo hecho —la **existencia** de una señal o el **valor** de un parámetro— se
  taguea, no se sobreescribe. Cada entrada: `field` (qué se discute: `P_rot` para un campo estelar,
  `<letra>.<param>` para uno planetario — `b.K`, `b.existence`), `posiciones[]` (**al menos dos**;
  con una sola no hay desacuerdo: es una afirmación y va a la prosa citada) y `note` opcional. Cada
  posición dice **quién la sostiene**: `{ref: <bibcode>, value: …}` para un paper (el bibcode
  **debe** existir como nota — lo chequea el lint) o `{source: ground_truth, value: …}` cuando NEA
  arbitra. **Ese marcador es el punto:** distingue *"hay autoridad y dice X"* de *"la bóveda
  genuinamente no sabe"*, que es la diferencia que el consumidor necesita ver. Cuando NEA arbitra
  **sigue siendo el valor de verdad** y el frontmatter no se toca (espejo puro, #70).
  ⚠ **El schema viejo** (`planets[].disputes[]` con `field`/`ref`/`note`/`alt`) tenía el polo de
  verdad **hardcodeado en la forma**: el otro lado era, implícitamente, el valor del frontmatter.
  Servía para paper↔NEA y **no podía expresar paper↔paper** —el caso normal cuando NEA calla (`K` y
  `e` enmascarados, `P_rot` sin `st_rotp`)—, y `P_rot`, que es de la **estrella**, ni siquiera tenía
  dónde colgar. **El lint NO lee el schema viejo** (una sola semántica; mantener las dos sería
  complejidad permanente en el lector): lo **detecta y bloquea**, con el comando de migración —
  `python scripts/make_notes.py --migrate-disputes`—, porque una disputa que el lector ignora en
  silencio es peor que un error.
  Vale igual para **conceptos**, donde la disputa es **simétrica por definición** (no hay valor de
  frontmatter contra el cual poner un `alt`). Sólo taguear discrepancias **materiales** (mayores que
  el error; no diferencias cosméticas dentro de la barra). Reflejar la disputa también en la
  tabla/prosa.
- **papers/**: `bibcode, title, first_author, n_authors, year, arxiv_id, doi, bibstem, stars[], topics[], methods[],
  thesis_links[], bearing(supports|challenges|method), role[], relevance, citation_count, pdf, fulltext,
  fulltext_source(pdftotext|ocr|web), pdf_source(eprint|ads|publisher|web)`. El contrato apunta a **ambos artefactos**: `fulltext` es el
  `.txt` **barato** (grep/lectura — el default de todo consumidor) y `pdf` el respaldo caro (abrir
  sólo para figuras/tablas/ecuaciones o dudas de símbolos); `fulltext_source: ocr` hereda desde el
  frontmatter la salvedad OCR (sin abrir el archivo). Los estampan `make_notes`/`extract_fulltext`
  por verdad de disco (null si no hay extracción). Cuando un paper vive bajo **varios slugs** (relevante
  para más de un sujeto → su `.txt` extraído bajo cada uno, contenido idéntico) el campo es **estable**:
  la copia ya estampada se mantiene salvo que llegue una de **mejor calidad** (`pdftotext`/`web` > `ocr`);
  no se repunta al slug que corrió último (idempotente, sin ruido de diff).
  **`fulltext_source` vs `pdf_source` (#57):** el primero dice **cómo se extrajo** el texto, el
  segundo **de qué documento salió** — `eprint` (arXiv: puede ser un **v1 pre-referato**, con
  `eprint_version` cuando se conoce), `ads` (escaneo alojado por ADS), `publisher`, `web`
  (snapshot), o `null` = **desconocido** (que **no** es "publicado"). Manda la verdad de disco: la
  marca que arXiv estampa en cada página, visible en el `.txt` — por eso se detecta
  retroactivamente en un corpus ya bajado (re-correr `extract_fulltext`, sin re-bajar nada); si no
  hay marca, vale la rama que registró el fetcher. Importa porque `verify-citations` promete que la
  cita textual son "las palabras reales del paper": con `eprint`, una discrepancia numérica contra
  un valor publicado es candidata a **diferencia de versión** y NO se "corrige" la nota hacia el
  preprint (ver el caveat del skill). **`role` (#73) — qué TIPO de aporte es el paper**, distinto de `bearing` (que dice la *postura*
  respecto de una tesis): `fundacional` (introduce el método/mecanismo/formalismo — la fuente de la
  ecuación), `aplicacion` (lo instancia en un caso: una estrella, un dataset) o `arbitro` (reanaliza
  y **resuelve** —o reabre— una tensión previa sobre el mismo hecho). Uno o varios; lo puebla la
  **extracción**, no la selección: `classify()` es regex sobre título+abstract+keywords y clasifica
  **tema**, no rol. Sin él, *"contrastar dos papers" no está definido*, porque no siempre es la misma
  operación: fundacional↔fundacional se comparan supuestos y derivaciones; aplicación↔aplicación se
  pregunta si replica y **en qué régimen**; **fundacional↔aplicación NO es contraste, es
  instanciación** —la aplicación no contradice la ecuación, la pone a prueba— y tratarlo como
  desacuerdo **fabrica disputas falsas**; el `arbitro` pesa distinto (resuelve, no promedia). El
  vocabulario es **cerrado** y el lint lo valida como bloqueante: un typo deja el campo mudo para la
  única operación que existe para consumirlo. Es especialmente agudo en temas de **método**, donde
  fundamentos y aplicaciones astro conviven en el mismo concepto por diseño (tema mixto).
  Opcional `no_sintetizado: <motivo>` (#75): declara que este
  paper **ya extraído** legítimamente no se inlinea en ninguna ficha/concepto —típicamente por la
  **regla de poda**, o porque aporta sólo vía roll-up—. Es una escotilla con **motivo obligatorio**
  (mismo criterio que el `--reason` del triage: no curar en silencio); sin ella, el lint lo reporta
  como *extraído pero no sintetizado*. Opcional
  `retracted: true` + `retraction{type,notice_doi,date,source}` — lo estampa `scripts/check_retractions.py`
  (Crossref) cuando el paper fue **retractado**; el lint lo surface como bloqueante (fuente no válida).
  En notas **off-ADS** el schema suma `source_url` (URL de la fuente web; null si es PDF local),
  `accessed` (fecha del snapshot — es la cita "Retrieved <fecha>") y, si la fuente no se pudo
  conseguir, `pending_source: paywall|scan|unextractable` (el lint la lista como precondición).
  Del mismo origen y opcional, `corrections: [{type,notice_doi,date,source}]` (#52): la corrección
  **no retractante** (`erratum` / `corrigendum` / `expression-of-concern`). **No** invalida el paper
  —sigue siendo citable, por eso el lint la lista como **backlog** y no bloquea— pero es la señal
  que más directamente **envejece un número ya extraído**: un corrigendum corrige justo el valor
  que la ficha destiló (P/K/e/m·sini), y una EoC deja la fuente en duda. Al verla, revisar las
  afirmaciones que citan ese `[[bibcode]]`, no la existencia del paper.
- **concepts/ (áreas **abiertas** — cualquiera según el foco de la bóveda; `concept_areas` en
  `vault/config/objective.yaml` es sólo referencia para el typo-check, con `methods`/`hypotheses` reservadas)**: `name`, **`aliases`** (lista de sinónimos EN+ES —
  p. ej. `[chromatic index, índice cromático, RV-color]` — para que la ficha se encuentre por `grep`
  desde **cualquier término**, no sólo el nombre canónico; espeja la idea de `aliases` de `stars/`),
  **`disputes[]`** (mismo schema de posiciones explícitas que en `stars/`, #71 — acá la disputa es
  simétrica por definición), `tags`, `confidence`. El cuerpo trae `## Síntesis`, `## Inventario por eje`,
  **`## Régimen de validez`**, `## Huecos` y el
  apéndice `## Excluidos por el filtro` (igual que la ficha de estrella).
  **Régimen de validez (#74) — sólo en conceptos.** Acá no hay ground-truth ni árbitro externo, y
  el eje de contraste **no es el mismo que en una estrella**: allá comparás el mismo número medido
  dos veces; en un método, dos papers pueden decir cosas distintas y **estar los dos bien**, porque
  valen bajo condiciones distintas (SNR, muestreo, tamaño de muestra, definición del observable).
  Por eso el modo de falla dominante en un concepto **no** es "dos números no coinciden" sino
  **generalizar de más**: el paper afirma X bajo condiciones C y el concepto afirma X pelado. La
  unidad de síntesis no es `(campo, valor, fuente)` sino **`(afirmación, condiciones bajo las que
  vale, fuente, rol)`**, y esa es la tabla. Es el destino de los veredictos **`aparente`** de
  `find-contradictions` ("distinto régimen, distinta definición, distinta época"): en una estrella
  se descartan como no-disputa; acá **son el hallazgo**. El `## Inventario por eje` queda para el
  desacuerdo **real bajo las mismas condiciones**, que acá es el caso minoritario. De la tabla sale
  además un hueco accionable que antes no tenía forma: **"régimen no cubierto"**. Rige el *Estándar transversal* (autosuficiente + implementation-ready).
  **Convención hub/radios (tema grande → varias notas):** cuando un tema no cabe en una sola nota sin
  perder foco, se estructura como **hub** (la nota central: síntesis del tema completo) + **radios**
  (notas satélite del mismo área que profundizan un sub-aspecto; p. ej. hub `procesos-gaussianos`, radio
  `gp-kernels` para la elección de kernel). El hub referencia cada radio explícitamente ("<sub-aspecto> vive
  en el radio [[...]]") y el radio abre con su "Para qué" apuntando de vuelta al hub. Un radio es una
  nota de concepto normal (mismo frontmatter y estándar de autosuficiencia); "hub/radio" es sólo la
  metáfora organizativa (rueda: centro y rayos).
- **concepts/hypotheses/**: `name, status`; el roll-up de evidencia es por Dataview sobre
  `thesis_links`.

**Estándar transversal de autosuficiencia (toda nota apuntable).** El estándar "autosuficiente" de
`stars/` rige **igual** para `concepts/` (indicadores, métodos, actividad, hipótesis) y para las
`queries/` que se archiven: la nota debe **alcanzar por sí sola**, ser **dual-audiencia (humano y
modelo)** y llevar `[[bibcode]]` en cada afirmación para **citar/trazar** (un agente redactando un
informe saca de la nota las referencias correctas sin abrir el paper). Requisitos extra por tipo:
- **métodos e indicadores** (`concepts/methods`, `concepts/indicators`): además
  **implementation-ready** — ecuaciones, inputs/outputs y pasos suficientes para **codificar el método
  tal como lo detallan los papers, sin abrir la fuente**; el detalle fino vive en los `[[links]]`. Y
  **con el régimen explícito** (#74): una ecuación sin las condiciones bajo las que vale es
  implementable y **equivocada** — quien la codifica no tiene cómo saber que estaba fuera de rango.
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
la query, `stars.yaml`/`topics.yaml`). La **regla de combinación** de facetas es declarativa (no
hardcodeada): por default OR (≥1 faceta cualquiera), pero una instancia puede declarar
`relevance.require: [<faceta>, …]` (AND: obligatorias) y/o `relevance.min_topics: N` (≥N cualesquiera) —
`core = (≥min_topics) Y (todas las de require) Y (doctype no-ruido)`. Es la palanca contra el ruido que
el citation chaining mete al ampliar el pool (podar regex no alcanza si la combinación sigue siendo OR);
sin declarar nada, comportamiento histórico. Cambiar la regla **re-clasifica** el corpus → sub-modo
re-clasificar de `maintain`. No ingesta nada; después se usan `ingest-star`/`ingest-topic`.

### Ingest (una fuente → cascada de páginas)
1. Los **orquestadores** corren la cadena mecánica completa (idempotente, no pisa — con una única
   excepción add-only: el retro-linkeo de abajo): `python scripts/ingest_star.py <slug>` para estrellas,
   `python scripts/ingest_topic.py <slug>` para temas. **El orden canónico de cada cadena vive en el
   header de su orquestador** (fuente de verdad única — puntero, no copia: no replicar la lista de
   scripts en docs/skills).
1b. **Compuerta de triage (estrellas).** El citation chaining amplía el pool con papers del grafo que
   mencionan al sujeto pero no hablan de él (medido: 18% de precisión). Sólo entra solo el que lleva
   el **sujeto en el título**; el resto queda como **candidato** en `build/<slug>/ads.json` —**sin
   bajarse**— y lo juzgás vos por título+abstract (`python scripts/triage.py <slug>`): aceptado →
   `extra_core` en `stars.yaml` + re-correr la cadena; descartado → `triage.py --drop … --reason`
   (persiste: no se re-propone); **dudoso → al usuario**. Detalle en el skill `ingest-star`.
2. **Vos (LLM)** leés el **fulltext `.txt`** (el default: barato y greppable; el PDF se abre sólo
   para figuras/tablas/ecuaciones o ante duda de símbolos si `fulltext_source: ocr`) y hacés la
   cascada. ⚠ **Mirá `pdf_source` antes de copiar un número:** con `eprint` el `.txt` es el
   **preprint** (un `v1` pre-referato puede traer otros valores que el publicado), así que un valor
   que contradice al ground-truth o al abstract de ADS es candidato a **diferencia de versión** —
   abrí el PDF publicado o anotá la salvedad en la nota. El verify lo detecta después; acá es donde
   el valor **entra** a la ficha.
   Cascada: poblás la extracción **de las notas de paper**
   (`methods`, `thesis_links`, `bearing`, `role`, P/K/indicadores). La ficha se escribe **después**
   del contraste (2b) — no saltar de leer a la prosa.
2b. **Contraste cross-paper (#72) — entre leer los papers y escribir la síntesis.** Es el paso con
   más apalancamiento de la cadena y el que más fácil se saltea, porque su producto no se nota si
   falta. Produce el **`## Inventario por eje`** de la nota: una fila por paper para cada **eje**
   —parámetro o hecho— donde los papers **no coinciden** (`Eje | Paper | Dice | Método / baseline`).
   Los ejes con acuerdo unánime **no entran** (misma regla de poda que la prosa).
   ⛔ **Sin columna "valor adoptado" ni "por qué":** eso sería juicio de LLM en un artefacto que se
   lee como bibliografía y **decide por el consumidor** — rompe el flujo unidireccional de la regla
   #0. La bóveda reporta el **estado de la literatura**; la lectura propia va aparte, marcada
   `inferencia`. Sin este paso, tres papers que reportan tres `P_rot` terminan en una frase con un
   solo `[[bibcode]]` y se evapora que los otros dos valores existen, con qué método se midieron y
   cuáles de los core ni se miraron — que es exactamente lo que la ficha promete responder sin abrir
   un paper, y lo que hace que un refresh no tenga que re-derivar la síntesis de cero. El `role`
   (#73) dice qué operación corresponde entre dos filas; la red de que el paso ocurrió es el backlog
   *extraído pero no sintetizado* (#75).
2c. **Síntesis a la nota viva**, apoyada en el inventario de 2b: la ficha de la estrella
   (frontmatter propio —`activity_indicators_expected`, `methods_applied.literature`, `disputes`—,
   prosa y huecos), los conceptos/hipótesis relacionados y la matriz método×estrella. ⛔ Los campos
   de ground-truth **no se tocan**: son espejo de NEA (#70).
3. Actualizás `index.md` y appendeás a `log.md`.

> **Retro-linkeo (papers pre-existentes ↔ entidad nueva) — tres capas:** (a) una **ficha-método**
> (`concepts/methods/`) junta en su tabla Dataview también por `contains(methods, "<concept>")` —
> los papers ya extraídos con ese método aparecen solos, sin re-taguear; (b) `make_notes` mergea
> **add-only** los seeds del ingest (`stars` / `thesis_links`) en notas de paper que **ya existían**
> (nunca pisa la extracción LLM; si ya están, no toca nada); (c) `ingest-topic` incluye un paso de
> **retro-tag por grep**: buscar los `aliases` del tema en el fulltext de **todo** el corpus y
> taguear (add-only, con juicio de LLM: uso real, no mención al pasar) los papers que la query ADS
> no devolvió. Así la entidad nueva ve también lo que ya estaba en el corpus.

> **Tema fuera de ADS (opt-in — sólo a pedido explícito).** Por default un tema se baja por **ADS**
> (ADS/arXiv/NEA — la plomería con **descubrimiento automático**: query → clasificar
> (`relevance.topics`) → bajar). El foco de Almagesto es **astro**; el **modo off-ADS** existe para
> los **métodos de otras disciplinas** que el trabajo astro usa —análisis de datos, estadística,
> machine learning, procesos gaussianos, signal processing— y cuya bibliografía canónica vive
> **fuera de ADS** (el eje tema/concepto y la capa de calidad son agnósticos de disciplina, así que
> la cadena los soporta igual). Diferencia operativa: sin ADS las fuentes se **declaran**, no se
> descubren por query — por eso es opt-in: si el usuario lo pide **explícitamente**, el skill
> `ingest-topic` lo soporta (fuente = PDFs locales + web;
> sin `query_ads`/`fetch_ground_truth`). Formalizado en el tooling: la
> entrada del tema en `topics.yaml` lleva `source: ads | web | local-pdfs [+web]` y (si es off-ADS) la
> lista `sources:`; `scripts/ingest_topic.py <slug>` orquesta la cadena según ese campo — también en
> modo ads. Un tema off-ADS puede ser **mixto**: los papers del tema que **sí** tienen bibcode ADS
> van en `extra_core:` (no en `sources:`) y el orquestador les corre solo la sub-cadena ADS
> (metadata real, sin blockquote off-ADS). Una fuente que **no se consigue** (paywall / escaneo / mojibake) se marca
> `pending: paywall|scan|unextractable` en su item de `sources:` → stub con `pending_source` (url/doi
> como puntero), **derivada al usuario** sin frenar la cadena; el lint la lista como precondición.
> **`ingest-star` no cambia: es astro-only.** Papers sin bibcode ADS → **clave de cita sintética `AAAA+Autor`** (debe empezar con
> `AAAA`+letra para el lint; el `.txt` en `vault/raw/fulltext/` se llama igual). Páginas web → **snapshot
> `.txt` determinista** (URL + fecha; lo genera `scripts/fetch_web.py` vía defuddle y crea además el
> stub de la nota de paper) para que sea citable/verificable. La **frontera dura sigue
> rigiendo**: sólo bibliografía citable.

### Registro de ingesta (`vault/config/registro/<slug>.yaml` — versionado, #51/#64)
Cada sujeto ingestado deja un registro que **se commitea y viaja**, con dos secciones de dueños
distintos: **`busqueda`** (la escribe `query_ads` al cerrar cada corrida: `fecha`, `query` efectiva
—en una estrella la arma `build_query` y antes se tiraba—, `rows`, `n_found`, `n_total`, `n_core`,
`n_candidates`, `n_dropped`, `truncated`, `almagesto_version`) y **`decisiones`** (el juicio de
curación, por clave: `decision`/`motivo`/`fecha`). Las `decisiones` cubren los **dos carriles**:
`triage.py --drop` para el candidato del citation chaining (por bibcode) y `triage.py --drop-source`
para la **fuente declarada** de un tema off-ADS (#81 — clave sintética o url, con `origen:
fuente-declarada` y un `fuente:` que la resuelva; sin `origen` = chaining). El segundo existe porque
en off-ADS `sources:` registra sólo lo aceptado: es la misma asimetría de #51 en el otro carril, y
`ingest_topic` **avisa** —no frena— si un item de `sources:` lleva una clave ya descartada. Regla de
oro: **`build/` guarda lo regenerable, el registro guarda lo que no lo es.** Un `ads.json` se recupera pidiéndoselo de nuevo a
ADS; el juicio de por qué descartaste un candidato, no —y hasta 1.8.x vivía en `build/`, gitignored,
así que en otra máquina el triage lo re-proponía todo sin el motivo (los **aceptados** ya persistían
en `extra_core`: la asimetría era el bug). `busqueda` responde la otra pregunta, la del consumidor:
**sobre qué universo de papers afirma esta ficha, y con qué lente se filtró.** Efectos: (a)
`make_notes` estampa en la cabecera de la ficha/concept **una línea** con fecha, universo→core,
pendientes y la ruta al registro (cirugía idempotente, no toca la prosa LLM); (b) el lint deja de
dar **falso limpio** sin `build/` — *triage pendiente* y *corpus truncado* caen al registro y
reportan el snapshot **con su fecha**, aclarando que no es el conteo vigente. Migración: el
`build/<slug>/triage.json` viejo **ya no se lee** —el framework no lleva capas de compatibilidad,
que son complejidad permanente en el lector— y se consolida con
`python scripts/triage.py <slug> --migrate` (idempotente: ante el mismo bibcode gana lo ya
versionado). Mientras exista, el **lint lo reporta como bloqueante**: que un juicio viejo quede mudo
es justamente el bug que #51 arregló.

### Append (plegar UNA fuente puntual a una entidad existente — skill `append-knowledge`)
El usuario trae **una fuente concreta** (bibcode ADS, PDF local o URL) para una ficha/concepto que
**ya existe**: plomería mínima según el tipo (bibcode → `extra_core` + cadena idempotente; off-ADS →
item en `sources:` + `ingest_topic.py`, o las piezas sueltas `fetch_web`/`make_notes --web`),
extracción enfocada en el eje del destino, síntesis a la nota viva (rige la regla de poda y
`disputes`) y cierre estándar (autosuficiencia + verify-citations + lint + log). **No crea
entidades** (eso es Ingest) **ni barre por query lo nuevo** (eso es Mantenimiento/refrescar); un dato
suelto sin fuente citable no entra (regla #0). Detalle en el skill.

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
ingest-topic (concept + papers), append-knowledge, find-contradictions (las disputas nuevas),
maintain cuando re-sintetiza, query archivada, test de hipótesis — **antes de lint/commit**.
**Qué hace:** descompone la nota en pares (afirmación, `[[bibcode]]`) —incluidas las **filas de tabla
y los ítems de lista**, que **heredan la cita del ámbito que las introduce** (caption / párrafo / encabezado
de sección) en vez de caerse del fan-out por no llevar `[[bibcode]]` propio— y lanza **un subagente
independiente por par** que lee SÓLO ese `vault/raw/fulltext/**/<bibcode>.txt` (grounding-first, prohibido de
memoria) y devuelve `soportada|parcial|no-soportada|contradice` + **cita textual + nº de línea del `.txt`**
(obligatoria; sin cita ⇒ no-soportada — también para `parcial`: la cita debe tocar el **contenido
distintivo** de la afirmación, la mera cercanía temática no alcanza). `no-soportada` = la fuente **calla**; `contradice` = la fuente
**afirma lo contrario** → no es (sólo) cita rota: es corrección de la nota o **disputa** a taguear
(`disputes` con posiciones explícitas, #71). Cada falla se **resuelve** (bajar la afirmación
a lo que dice la fuente, reasignar la cita al bibcode correcto, marcar **`inferencia`**, o taguear la
disputa) y se deja un bloque `## Verificación de citas` en la nota. El subagente contesta además, **en todos los casos**, si el paper
afirma eso **bajo condiciones** que la nota no dice (#74): la afirmación pelada sí está en la fuente,
así que el veredicto es `soportada` y la **sobre-generalización pasaba entera** — la nota no afirma
falso, afirma **de más**. Se reporta como hallazgo aparte y se resuelve agregando la condición (en un
concepto, como fila de `## Régimen de validez`). Cuando el par sale de una
**transcripción** (tabla/lista de la fuente) el subagente contesta además la pregunta de
**completitud** —¿la fuente tiene más filas/ítems que los transcritos?—: una tabla sin un solo error
pero **truncada** vuelve 100% soportada y se lee como completa (la nota no afirma falso, afirma **de
menos**); el faltante se reporta como hallazgo propio y se completa o se declara el recorte. El `.txt` es extracción **determinista** (`pdftotext`), así que
la cita son las palabras reales del paper; si una afirmación no aparece (artefacto de extracción:
ecuación/tabla/escaneo) abrir el PDF o marcar `no verificable por extracción`. Un `.txt` con header
`source: ocr` (rescatado por tesseract cuando la capa de texto era ilegible; la nota del paper lo
espeja en `fulltext_source: ocr`) es **citable con
salvedad**: el OCR puede errar símbolos/notación — la verificación vale para prosa; ante discrepancia
de símbolos, abrir el PDF. Es **juicio de LLM**,
robusto pero no prueba — su tasa de error se mide con el **auto-benchmark** (modo benchmark del
skill, a pedido): `python scripts/bench_verify.py seed` siembra citas falsas deterministas entre pares
reales (misma afirmación, bibcode rotado), el verificador las juzga **a ciegas** y `score`
reporta el recall; nada del benchmark entra al vault (vive en `build/`/`outputs/`).
**Regla dura — todo lo apuntable es chequeable:** toda afirmación fáctica va
**citada `[[bibcode]]` o marcada `inferencia`** — nada sin respaldo. Excepción: los **valores de
ground-truth (NEA)** en `stars/` (P/K/e/m·sini) no se verifican contra papers (su consistencia la
chequea el lint); sólo se verifican disputas y afirmaciones atribuidas a un paper. El lint reporta como
backlog los conceptos/hipótesis **sin ninguna cita** (cobertura: afirman sin fuente → no chequeables).

### Contradicciones (desacuerdo claim↔claim — skill `find-contradictions`)
**Complementa Verify en el eje ortogonal:** Verify chequea claim ↔ **su propia** fuente;
`find-contradictions` chequea claim ↔ claim **entre** fuentes (¿dos papers discrepan sobre el mismo
hecho?). **Cuándo:** auditoría **explícita** (a pedido, o tras un ingest grande) — **no** es paso de
cierre automático. **Qué hace:** barre un eje (estrella/parámetro o concepto), confirma cada desacuerdo
candidato con un subagente por par (lee los **dos** fulltext, `real|aparente|no-concluyente` + cita de
ambos lados) y **propone** disputas —`disputes` a nivel nota con posiciones explícitas (#71); si NEA
arbitra, una posición es `{source: ground_truth}` y sigue siendo la verdad—,
línea citando ambos `[[bibcode]]` para conceptos— que **el usuario aprueba** antes de escribir. Detalle
en el skill.

### Mantenimiento (cuidar lo ya ingestado — skill `maintain`)
**No crea entidades** (eso es Ingest); opera sobre estrellas/conceptos que **ya existen**. Sub-modos:
**refrescar** (papers nuevos → re-sintetizar sólo lo nuevo), **borrar** (nota + PDF/fulltext + reparar
colgados), **renombrar** slug, **re-clasificar** tras cambiar `relevance.topics`, **resolver el
backlog del lint** (P_rot sin documentar, drift PDF↔disco, cobertura — los **huérfanos no**: son
bloqueantes, se arreglan al cierre de la operación que los creó), y la **pasada periódica de
retracciones** (`check_retractions.py` sin `--slug`, toda la bóveda — la cadena de ingest sólo
chequea el slug en curso; **esa misma pasada estampa también `corrections`**, con el mismo valor
que para las retracciones: cazar lo publicado **después** del ingest y cubrir el corpus anterior a
1.8.0. Lo ingestado desde entonces ya trae sus `corrections` estampadas por la cadena). Invariante: la cadena es
idempotente (refrescar es seguro); **nunca** se pisa la extracción LLM ni el ground-truth sin `--force`
explícito. Detalle en el skill.

### Lint (chequeo de salud)
**Cuándo:** como **paso de cierre de toda operación que escriba en `vault/wiki/`** (ingest,
append-knowledge, maintain, find-contradictions, query archivada, test de hipótesis), **antes de
commitear** y **después** del verify (resolver una cita no-soportada cambia la prosa); más una pasada completa periódica. Es barato.
Correr `python scripts/lint.py`: debe quedar en **0** para wikilinks rotos, **frontmatter no
parseable** (nota que empieza con `---` pero cuyo YAML no parsea —p. ej. un `title:` con `:` sin
comillas editado a mano—: evade en silencio los chequeos de su tipo), **papers retractados**
(flag `retracted`; lo detecta `scripts/check_retractions.py` vía Crossref —red; la cadena de ingest
chequea sólo los papers del slug (`--slug`) y el barrido completo de la bóveda es la pasada
periódica del skill `maintain`— y el lint lo surface offline: una fuente retractada citada rompe la
frontera dura),
páginas huérfanas,
contradicciones ground-truth↔ficha —**tanto en el número de planetas como campo por campo**: un
valor que difiere del ground-truth, o que existe en la ficha cuando NEA no lo tiene, rompe el espejo
(#70)—, **masa de ground-truth inconsistente con la m·sini implícita**
(K/P/e/M\* — atrapa best-mass espurias de NEA), **`thesis_links` sin página destino** (tag que no matchea
ninguna nota → no acumula en el roll-up; typo típico `shift-vs-shape` vs `shift_vs_shape`) y
**`disputes` con la `ref` de una posición sin paper destino** (el bibcode que sostiene esa posición
no existe como nota → la disputa no es trazable), **`disputes` mal formadas** (#71: sin `field`, con
menos de dos posiciones —con una sola es una afirmación, no un desacuerdo—, con una posición que no
dice quién la sostiene, o con un `source` fuera del vocabulario), **`disputes` en el schema viejo**
(`planets[].disputes[]`, que el lint ya no lee: migrar) y
**`role` fuera del vocabulario** (`fundacional|aplicacion|arbitro`: un typo deja el rol mudo para el
contraste cross-paper, mismo modo de falla que un `thesis_links` sin destino) y el **juicio de triage
en `build/<slug>/triage.json`** (el lugar pre-1.9.0 que el lector ya no mira: mientras exista, el
triage vuelve a proponer lo ya descartado **sin el motivo** → `triage.py <slug> --migrate`). La
**fuga de implementación** (regla #0 / frontera dura) es **WARN no bloqueante** — heurística de alta
señal (perilla/dial/`w_j`/`peso(`); cada hit se revisa a mano y se saca del vault si es material de
implementación (no es bibliografía). Las **áreas de `concepts/` fuera de `concept_areas`** (subcarpeta no
declarada en `vault/config/objective.yaml`) son **WARN** — las áreas son **abiertas**: la lista es sólo
referencia para distinguir un typo de un área nueva, **nunca se bloquea** (`make_notes` **avisa** pero crea
igual; el lint marca las carpetas fuera de la lista). Si el objetivo **no declara** `concept_areas`,
el typo-check queda **apagado** y el lint reporta eso (una línea, no una por carpeta): la lista no se
infiere de lo que hay en disco, porque eso convertiría un typo ya cometido en "área declarada". El **objetivo sin instanciar** (`objective.name`
sigue siendo el placeholder del template, `<definir con el skill setup>`) es **WARN**: la bóveda estaría
clasificando "core" con la regex del ejemplo — correr el skill `setup`. El **PDF ↔ disco** es **WARN/higiene**: marca un paper
cuyo campo `pdf` no refleja el PDF real — está bajado en `vault/raw/pdfs/<slug>/<bibcode>.pdf` pero el
frontmatter quedó `null` (drift, hay que linkearlo) o apunta a un archivo inexistente (puntero roto).
Su hermano **cuerpo ↔ frontmatter** (mismo bloque, WARN) mira lo que aquél no ve: el link `[📄 PDF]` de la
**línea de cabecera** —metadata derivada, la re-estampa `make_notes`— debe existir sii `pdf` apunta a un PDF
vigente. Distingue "sin link" (lo arregla el backfill `python scripts/make_notes.py --restamp-pdf-links`)
de "cabecera fuera del contrato" (el re-estampado la saltea: hay que normalizar la cabecera primero).
Un **`.obsidian/` en la raíz del repo** es **WARN** (la bóveda se abrió mal: el grafo indexa el
andamiaje — abrir la carpeta `vault/` como vault y borrar ese directorio). Las **citas no verificables** (bibcode citado en query/concepto/hipótesis sin su `.txt` en
`vault/raw/fulltext/`) se listan como precondición de `verify-citations`; ídem las **fuentes
pendientes** (`pending_source` en una nota de paper: fuente no conseguida —paywall/escaneo/mojibake—
derivada al usuario con su puntero doi/url) y el **fulltext ilegible** (un `.txt` que no pasa el
umbral determinista de legibilidad — mojibake, escaneo sin capa de texto, o escaneo cuya única capa
es la **marca de agua** del bibcode repetida por página (lo agarra la densidad por página): existe
pero no sirve para grep ni verify; rescate: PDF sano, OCR, o marcar `pending`). Las **correcciones
publicadas** (`corrections`, #52 — erratum/corrigendum/EoC del mismo barrido de Crossref) son
**backlog, no bloquean**: el paper sigue siendo citable; lo que hay que revisar son los valores que
se le extrajeron (un corrigendum cambia justamente ese número). El **extraído pero no sintetizado** (#75: un paper con `methods` poblado —o sea que ya pagó el paso
más caro de la cadena— cuyo bibcode **no aparece citado en ninguna ficha ni concepto**) es
**backlog**: la extracción nunca llegó a la síntesis. Es el análogo del proxy que ya existe para
planetas (cada planeta del frontmatter discutido en prosa) y mide si el paper **llegó**, no si la
síntesis es buena. Existe porque **todo paso salteable de la cadena tiene red** (#55 triage, #56
verificación stale, #69 cabecera) menos justamente el de síntesis, cuyo modo de falla es **omisión**
—no deja rastro— y que `verify-citations` no puede ver: valida cada afirmación contra su fuente, no
la cobertura del conjunto, así que una ficha sintetizada desde 3 papers de 40 vuelve 100% soportada.
Se cierra sintetizándolo donde corresponda o declarando `no_sintetizado: <motivo>` en la nota del
paper. La **cobertura** (concepto/hipótesis
sin ninguna cita `[[bibcode]]` → afirma sin fuente) es **backlog** que el lint surface para ir citando;
ídem la **cobertura de verificación** (query/concepto **con** citas pero **sin** bloque
`## Verificación de citas` → nunca pasó por `verify-citations`: correr el skill) y la **verificación
stale** (la nota se editó **después** de la fecha de su bloque —lo que pasa al ampliarla con
`append-knowledge` o refrescarla— así que las afirmaciones nuevas nunca pasaron por el fan-out pero
quedan bajo un encabezado que se lee como vigente: es el modo de falla de "afirmar de menos"
aplicado a la garantía misma; el lint lo mide por `git` contra la fecha del encabezado —por eso el
bloque **debe** llevar fecha— y degrada a silencio fuera de un repo).
La **cabecera no estampable** (#69: una ficha o concepto **sin** la línea
`> _Generado con Almagesto v…_`, que es el ancla de **todos** los estampadores de cabecera) es
**backlog**: la nota es válida, pero cualquier cirugía de cabecera —hoy el puntero de búsqueda de
#64— devuelve `False` **en silencio** sobre ella, así que la feature no llega y no queda rastro
(medido en una bóveda real: 22 de 25 notas). Pasa en todo lo creado antes de que la cabecera
existiera; se arregla con `python scripts/make_notes.py --restamp-headers`, que la sintetiza
anclando en el `# H1` y **lee la versión del `generator` del frontmatter** en vez de inventarla.
Regenerar con `--force` también la escribiría, pero pisa la síntesis LLM: por eso es cirugía.
El **triage pendiente** (#55: candidatos del chaining en `build/<slug>/ads.json` que **nadie juzgó**
todavía — la compuerta los deja sin bajar, y el aviso vivía sólo en el stdout de la corrida, que se
pierde al scrollear: un ingest podía cerrarse con lint en 0 y cientos de pendientes) es **backlog**;
se resuelve con `python scripts/triage.py <slug>` (pertinente → `extra_core`; ruido → `--drop …
--reason`). Sin `build/` local **no** da un cero inventado: cae al `busqueda` del registro versionado
y reporta el snapshot con su fecha (no el conteo vigente — si dropeaste sin re-correr la cadena
quedó viejo).
El **corpus truncado** (un `build/<slug>/ads.json` con `truncated` seteado → la query directa trajo
menos papers de los que ADS reporta: al sujeto le falta cola) es **backlog** — `query_ads` persiste la
marca (default `--rows 2000`, ≈ el máximo de una request; re-ingestar con `--rows` mayor para cubrir la
cola); ídem el **rescate por glifo incompleto** (`truncated_glyph`, marca hermana: el superset de la
constelación del rescate #28 se cortó por citas **antes** del filtro client-side, que es donde vive la
señal → pueden faltar papers con lookalike). Los "campos incompletos" (P_rot null, papers sin `methods`, etc.) son **backlog**, no bloquean. Revisar
además a mano: claims stale y conceptos referidos sin página. Si faltan datos, abrir queries para
imputar (web/ADS).

## Token / secretos
El token ADS va en `vault/config/ads_dev_key` (**gitignored** — nunca se commitea) o en la variable de
entorno `ADS_DEV_KEY`. Token gratis en <https://ui.adsabs.harvard.edu/user/settings/token>.
`build/` y `outputs/` gitignored. PDFs por git-lfs (`vault/raw/pdfs/**/*.pdf`). El resto de
`vault/config/` **sí se commitea**, incluido `registro/<slug>.yaml` (es el punto: el juicio de
curación y el registro de búsqueda tienen que viajar).
