# Almagesto — schema de la wiki de conocimiento astro (instrucciones para el agente)

Esta es una **LLM wiki** (patrón Karpathy) sobre literatura astronómica, organizada por **estrella**
y por **concepto**. **El OBJETIVO de la bóveda vive en `vault/config/objective.yaml`** (editable): define de
qué trata esta wiki y —vía `relevance.facets`— **qué papers son "core"**. Leé ese archivo al iniciar
para saber sobre qué estás trabajando. Vos (Claude) **sos el dueño de `vault/wiki/`**: la creás y mantenés.
El usuario cura las fuentes (`vault/raw/`) y hace preguntas.

> Este archivo es el **schema genérico** (forma astro: estrellas, planetas, indicadores de actividad,
> ground-truth de exoplanetas). El eje **tema/concepto** y la capa de calidad (lint, verify,
> retracciones, benchmark) son agnósticos de disciplina: permiten sumar **métodos de otras
> disciplinas** (estadística, ML — modo off-ADS) al servicio del foco astro. Lo único específico de
> cada instancia es `vault/config/objective.yaml` + el
> contenido de `vault/wiki/`/`vault/raw/`. Para instanciar una bóveda nueva ver `README.md` (sección *Instanciar*).

> **La cabecera de una ficha/concepto lleva una línea `> _Estado — …_`** con **dos fechas**
> (la de **síntesis** está decidida y **no implementada** todavía — INV-82 figura `parcial` en
> `docs/contrato.md`) que avanzan por separado y pueden divergir sin que ninguna mienta (D-12): **búsqueda** (última
> corrida + universo acumulado + escotillas), y **verificación** (fecha del bloque, con la salvedad
> fija *"vigencia por par: la dicen las anclas"* — sin ella, la fecha se lee como "todo verificado
> a esta fecha", que es justo la lectura que el ancla corrige). Con una sola fecha por nota,
> refrescar el corpus hacía parecer re-verificado lo que nadie volvió a chequear.

> **Al iniciar sesión, leé `vault/STATUS.md` (estado + próximos pasos) y `vault/wiki/log.md` (historial
> reciente) para orientarte.** *(Si estás en el repo **template** `Almagesto` —donde esos dos son la
> **semilla** que una instancia nueva clona, no un estado— el handoff del desarrollo del framework
> vive en `docs/internal/HANDOFF.md`, que no se versiona.)* La "memoria" del proyecto es in-repo: este `CLAUDE.md` + `vault/STATUS.md`
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
    ├── config/  (objective.yaml, stars.yaml, themes.yaml, ads_dev_key, registro/<slug>.yaml)
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
— este `CLAUDE.md`, `scripts/`, `tests/`, `tools/`, `docs/`, `.claude/skills/`,
`vault/.obsidian/`, `README.md`, `requirements.txt`. El
framework es **una sola implementación**: los cambios se hacen en el repo template `Almagesto` (issue/PR
o parche), se pushean, y se traen por `git pull` / `git merge upstream/main`. Editarlos en la instancia
**da conflictos** en el próximo merge. En la instancia sólo se edita **contenido** (`vault/wiki/`, `vault/raw/`) y los
**archivos de instancia** protegidos por `merge=ours` (`vault/config/objective.yaml`, `vault/config/stars.yaml`,
`vault/config/themes.yaml`, `vault/STATUS.md`, `vault/wiki/index.md`, `vault/wiki/log.md`,
`vault/wiki/matrices/method_star.md`). **Si una operación revela una mejora
de framework** (skill nuevo, fix de script, regla), anotala como backlog en `vault/STATUS.md`/`vault/wiki/log.md` y
aplicala en el template — no la inlines acá. *(Si estás trabajando en el repo template `Almagesto` mismo,
editar framework **es** la tarea; esta regla rige para las instancias.)*

## ⛔ Frontera dura — la bóveda es SÓLO bibliografía (regla #0, no negociable)

**Esta wiki es una referencia bibliográfica. Punto.** Almagesto recopila información bibliográfica y
**todo lo que afirma está respaldado por una fuente citable (`[[bibcode]]`).** El flujo es
**unidireccional y de sólo lectura hacia afuera**: alguien lee de la bóveda; **la bóveda nunca
describe, parametriza ni se acomoda a quien la consume.**

> **La bóveda es READ-ONLY desde afuera.** Si estás leyendo esto como agente de otro repo: acá se
> **lee**, no se escribe. Podés sacar un valor, un mecanismo o una ecuación —siempre arrastrando su
> `[[bibcode]]`— y **nada de tu lado entra**: ni cómo lo vas a usar, ni qué decide en tu pipeline,
> ni qué parámetros elegiste a partir de esto. Escribir eso acá no es "documentar el contexto": es
> convertir una referencia bibliográfica en documentación de tu implementación, y a partir de ahí
> el próximo lector ya no puede distinguir qué dice la literatura de qué decidió un repo. El detector
> de fuga del lint (`downstream: []` en `objective.yaml`) marca esa prosa; la marca es una red, no
> un permiso.

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
  ⛔ **Espejo con AUTORIDAD POR CAMPO (#70 + D-1) — cada campo vale lo que dice SU autoridad o NADA.**
  `spectral_type` ← **SIMBAD**; `teff_K`, `dist_pc`, `P_rot_days` y los cinco campos de cada
  `planets[]` ← **NEA** (pscomppars). Si **la autoridad declarada** calla, el campo queda `null`
  **aunque la otra tenga el dato**: un valor cuya procedencia depende de quién contestó primero no
  es auditable — el consumidor no puede distinguirlo de uno con una sola fuente. El JSON registra
  en `_autoridad` **quién contestó cada campo**, y en `_otras_autoridades` lo que la otra decía y
  no se adoptó (D-2: sin eso, el desacuerdo entre autoridades desaparece; se expresa como
  `disputes` con `source: nea` / `source: simbad`).
  **La ficha lo publica arriba**, en el blockquote de cabecera: una línea `> _Ground-truth — …_`
  con qué autoridad respondió cada campo, la fecha del snapshot, **qué campos volvieron vacíos**
  (distinto de "nadie preguntó", que en el frontmatter se ve igual: `null` en los dos) y el puntero
  al JSON. Se estampa sola (`make_notes.py <slug>`, idempotente). Está ahí porque el **artefacto es
  lo que viaja**: una ficha copiada, exportada o leída por un agente llega sin la doc al lado.
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
  ⚠ **`## Papers` se ESTAMPA, no es Dataview (D-10/D-11).** ⚠ **No todos** los roll-ups todavía:
  `## Planetas` sigue siendo ```dataviewjs``` y `## Métodos aplicados a esta estrella`
  ```dataview``` (INV-81 `parcial`). `## Papers` es una tabla
  materializada —`Bibcode | Año | Relevancia | Origen | Estado`— cuyo encabezado lleva los **dos**
  números (universo · sintetizados en esta ficha), porque el defecto medido era prometer 155 arriba
  de una síntesis de 8. El **estado** dice cuán lejos llegó cada paper en el embudo: `fuera del
  filtro` → `sin extraer` → `extraído, no sintetizado` → `sintetizado`. La regenera
  `python scripts/make_notes.py <slug>` (idempotente, cirugía: no toca la prosa) y el lint reporta
  como backlog la tabla desactualizada, **nombrando los stems**. En un concepto el roll-up es la
  **unión** de `methods` y `thesis_links`, con la columna *Entró por* (D-24: esas dos llaves viven
  en papers distintos, y quedarse con una pierde la mitad).
  El motivo de fondo (#60): un bloque ```dataview``` le muestra a un agente que abre el `.md` el
  **código de la query, no sus resultados**, y el plugin ni siquiera está versionado. Para la audiencia-modelo, que es la que este
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
- **papers/**: ⛔ **la identidad de un trabajo es su `doi`/`arxiv_id`, no su bibcode (D-19).** El
  preprint y el publicado son bibcodes distintos del **mismo** paper: dos notas ahí son doble conteo
  en todo lo que cuenta papers, dos fuentes donde hay una, y un falso positivo permanente de #75
  (la ficha cita una de las dos). Hay **una sola nota canónica** y los bibcodes viejos viven en
  `versions[]`; el lint bloquea el duplicado y `make_notes` **rehúsa crear** la segunda nota. El
  ciclo se resuelve con `python scripts/make_notes.py --rename-paper VIEJO NUEVO`, que mueve la nota
  y sus artefactos (`raw/pdfs/`, `raw/fulltext/`), agrega el alias y **reescribe los wikilinks de
  toda la bóveda** — sin eso el renombre deja links rotos, que es la mitad del trabajo. Alcance
  declarado: `vault/`; lo que vive afuera se resuelve por el alias. Campos:
  `bibcode, title, first_author, n_authors, year, arxiv_id, doi, bibstem, stars[], facets[], keywords[],
  methods[], thesis_links[], role[], relevance, citation_count, pdf, fulltext,
  fulltext_source(pdftotext|ocr|web), pdf_source(eprint|ads|publisher|web)`. El contrato apunta a **ambos artefactos**: `fulltext` es el
  `.txt` **barato** (grep/lectura — el default de todo consumidor) y `pdf` el respaldo caro (abrir
  sólo para figuras/tablas/ecuaciones o dudas de símbolos); `fulltext_source: ocr` hereda desde el
  frontmatter la salvedad OCR (sin abrir el archivo). Los estampan `make_notes`/`extract_fulltext`
  por verdad de disco (null si no hay extracción). Cuando un paper vive bajo **varios slugs** (relevante
  para más de un sujeto → su `.txt` extraído bajo cada uno, contenido idéntico) el campo es **estable**:
  la copia ya estampada se mantiene salvo que llegue una de **mejor calidad** (`pdftotext`/`web` > `ocr`);
  no se repunta al slug que corrió último (idempotente, sin ruido de diff).
  **`keywords` (D-17)** son las del catálogo (ADS ya las devuelve y `ads.json` ya las persistía; la
  nota las tiraba). No son decorativas: la lente matchea sobre **título + abstract + keywords**, así
  que sin ellas re-clasificar desde la nota daría un veredicto distinto del que dio el ingest — un
  diff inventado. Son lo que hace posible el **diff de lente offline** (D-49), o sea auditar si el
  corpus sigue clasificado con la regla vigente **sin `build/`**, que es scratch gitignored y no
  viaja. Backfill para notas viejas con `build/` vivo: `make_notes.py --restamp-keywords`.
  **`fulltext_source` vs `pdf_source` (#57):** el primero dice **cómo se extrajo** el texto, el
  segundo **de qué documento salió** — `eprint` (arXiv: puede ser un **v1 pre-referato**, con
  `eprint_version` cuando se conoce), `ads` (escaneo alojado por ADS), `publisher`, `web`
  (snapshot), o `null` = **desconocido** (que **no** es "publicado"). Manda la verdad de disco: la
  marca que arXiv estampa en cada página, visible en el `.txt` — por eso se detecta
  retroactivamente en un corpus ya bajado (re-correr `extract_fulltext`, sin re-bajar nada); si no
  hay marca, vale la rama que registró el fetcher. Importa porque `verify-citations` promete que la
  cita textual son "las palabras reales del paper": con `eprint`, una discrepancia numérica contra
  un valor publicado es candidata a **diferencia de versión** y NO se "corrige" la nota hacia el
  preprint (ver el caveat del skill). **`role` (#73) — qué TIPO de aporte es el paper**, distinto de la **postura** respecto de una tesis (que desde D-21 **no vive en el paper**: vive en
  la tabla de evidencia de la hipótesis, porque depende de la tesis y un paper puede tocar varias): `fundacional` (introduce el método/mecanismo/formalismo — la fuente de la
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
- **concepts/hypotheses/**: `name`, `status` (**vocabulario CERRADO**, D-37 —
  `abierta | sostenida | disputada | refutada`—: el lint bloquea lo que no esté en la lista, porque
  un consumidor lee ese campo para decidir si se apoya en la hipótesis y la prosa libre lo deja
  mudo; se **deriva de la tabla de evidencia**, y si hay filas `desafía` con `status: sostenida` el
  lint lo marca).
  El cuerpo lleva **tres cosas propias**:
  1. **El blockquote de alcance** (D-34) — `> Alcance <fecha> · temas: […] + estrellas: […] · N
     papers · M con hits`. **Define qué significa el veredicto**: *"no hay evidencia"* no es *"no
     existe evidencia"*, es *"no hay evidencia en estos temas, con estos N papers, a esta fecha"*;
     sin él, un veredicto negativo se lee como **universal** — el mismo *afirmar de más* aplicado a
     una conclusión. Los slugs son directorios de `raw/fulltext/` (que es sobre lo que corre el
     grep), así que el universo se puede **re-contar**: el lint compara lo declarado contra lo que
     hay hoy y marca la hipótesis **si quedó corta** (el alcance crece igual que el corpus).
  2. **La tabla de evidencia** (D-21) — una fila por paper: `Paper | Postura | Qué dice (cita
     textual) | L | Régimen`. Acá vive la **postura** (`apoya`/`desafía`/`método`), **no** en la
     nota del paper: depende de la tesis —un paper puede tocar varias— y como escalar suelto en el
     paper es un veredicto sin evidencia que `verify-citations` **no puede chequear**. En la tabla
     hay una fila por par, con cita: es verificable. ⛔ `bearing` en una nota de paper es schema
     viejo y **el lint lo bloquea** (`make_notes.py --migrate-bearing`).
  3. **El veredicto global marcado `inferencia`** (D-36), con sus premisas: agregar N filas en una
     conclusión es juicio del agente, no algo que una fuente diga.

  Una hipótesis **no es un radio** (D-35): cruza varias entidades, así que se linkea con
  `[[wikilink]]` en los dos sentidos, sin la relación padre-hijo de un hub. El roll-up mecánico de
  qué papers la tocan sigue saliendo de `thesis_links`.

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
  for/against con su **postura declarada en la tabla de evidencia de la hipótesis** (D-21: no en el
  paper), y veredicto.
Si para implementar o citar algo hace falta abrir el paper, eso que falta **debe agregarse a la nota**.

Convenciones: filenames kebab-case (papers usan el bibcode); links internos `[[wikilink]]` por
nombre de nota (sobreviven a mover carpetas); reportar agregados declarando mean vs median.
**Notación matemática según destino:** en archivos de `vault/wiki/` SIEMPRE `$...$` (Obsidian lo renderiza);
en **respuestas de consola/chat** usar **texto plano** (`P_rot`, `m·sini`, `K=2.5 m/s`), porque la
terminal no renderiza LaTeX y `$...$` se ve crudo.

## Operaciones

### Setup (definir el objetivo — paso 0, skill `setup`)
Genera/afina `vault/config/objective.yaml` (la **lente**: `name`/`description` + `relevance.facets`, el
clasificador de papers core). El agente traduce el foco del usuario (en palabras) a la regex — el usuario
**no** escribe regex — y la valida contra papers reales con `python scripts/query_ads.py --probe "<query>"`
(muestra el corte core/no-core sin bajar nada) iterando hasta que cierre. `relevance.facets` son **facetas**
(constantes; clasifican los papers de estrella, y los de tema **salvo que el tema declare su
lente propia** — ver *Relevancia de un tema de método*), **no** sujetos (las estrellas/temas van en
la query, `stars.yaml`/`themes.yaml`). La **regla de combinación** de facetas es declarativa (no
hardcodeada): por default OR (≥1 faceta cualquiera), pero una instancia puede declarar
`relevance.require: [<faceta>, …]` (AND: obligatorias) y/o `relevance.min_facets: N` (≥N cualesquiera) —
`core = (≥min_facets) Y (todas las de require) Y (doctype no-ruido)`. Es la palanca contra el ruido que
el citation chaining mete al ampliar el pool (podar regex no alcanza si la combinación sigue siendo OR);
sin declarar nada, comportamiento histórico. Cambiar la regla **re-clasifica** el corpus → sub-modo
re-clasificar de `maintain`. No ingesta nada; después se usan `ingest-star`/`ingest-theme`.

### Relevancia de un TEMA DE MÉTODO — la lente propia y las tres puertas (D-26 / INV-88)

Para un tema de método (estadística, ML, signal processing) la lente global **no sirve, y es
activamente dañina**: con `require: [rv]` mata al paper **fundacional** (Hyvärinen no menciona RV ni
una vez), y sin filtro *"independent component analysis"* devuelve miles de papers de fMRI, EEG y
finanzas. Por eso la entrada del tema en `themes.yaml` lleva su **`facet:` propia** (regex) y la
regla pasa a ser `core = facet propia Y (puerta 2 OR puerta 3)`:

| Puerta | Criterio | Dónde vive |
|---|---|---|
| **2 · fundacional en su campo** | `citation_count >= fundacional_min_citas` | `query_ads.classify_theme` |
| **3 · lente astro global** | pasa `relevance.facets` de `objective.yaml` | ídem |

⚠ **`fundacional_min_citas` no tiene default**: el número depende del campo (30k citas es normal en
ML y muchísimo en astro) y esconderlo sería decidir por el usuario. Sin declararlo la puerta 2 **no
abre** y el motivo queda en `why_excluded`. *(Anotado en `vault/STATUS.md` como **decisión abierta**
si la puerta 2 debería existir: mete una propiedad del mundo —cuántos te citan— en una regla que
era sólo sobre el texto del paper.)*

⛔ **La puerta 1 («lo cita tu corpus») PROPONE, no clasifica** (§4.3 del plan): alimenta los
candidatos del triage con `via: citado-por-corpus`, nunca marca core. Si clasificara, ser core
dejaría de ser función de `(paper, lente)` y se rompería INV-24. La sostiene
`scripts/citation_index.py` (índice invertido obra→citadores, lookup **offline**, vive en `build/`),
que se construye aparte porque es caro. Los backends de descubrimiento fuera de ADS son
`scripts/search_arxiv.py` y `scripts/openalex.py`; los tres normalizan al **mismo schema de
registro** que `query_ads.to_record`, y esa paridad la fija un test
(`tests/test_backends_schema.py`), no la prosa.


### Ingest (una fuente → cascada de páginas)
1. Los **orquestadores** corren la cadena mecánica completa (idempotente, no pisa — con una única
   excepción add-only: el retro-linkeo de abajo): `python scripts/ingest_star.py <slug>` para estrellas,
   `python scripts/ingest_theme.py <slug>` para temas. **El orden canónico de cada cadena vive en el
   header de su orquestador** (fuente de verdad única — puntero, no copia: no replicar la lista de
   scripts en docs/skills).
1b. **Compuerta de triage (estrellas).** El citation chaining amplía el pool con papers del grafo que
   mencionan al sujeto pero no hablan de él (medido: 18% de precisión). Sólo entra solo el que lleva
   el **sujeto en el título**; el resto queda como **candidato** en `build/<slug>/ads.json` —**sin
   bajarse**— y lo juzgás vos por título+abstract (`python scripts/triage.py <slug>`): aceptado →
   `extra_core` en `stars.yaml` —**lista de mapas** `{bibcode, via, fecha, motivo}`, forma dura: el
   escalar y la lista de strings **bloquean** con el snippet correcto, y `triage.py` lo imprime
   listo para pegar (D-58). El motivo de la asimetría: el carril del **descarte** ya registraba
   quién y por qué (#51), y el de la **aceptación** no— + re-correr la cadena; descartado → `triage.py --drop … --reason`
   (persiste: no se re-propone); **dudoso → al usuario**. Detalle en el skill `ingest-star`.
2. **Vos (LLM)** leés el **fulltext `.txt`** (el default: barato y greppable; el PDF se abre sólo
   para figuras/tablas/ecuaciones o ante duda de símbolos si `fulltext_source: ocr`) y hacés la
   cascada. ⚠ **Mirá `pdf_source` antes de copiar un número:** con `eprint` el `.txt` es el
   **preprint** (un `v1` pre-referato puede traer otros valores que el publicado), así que un valor
   que contradice al ground-truth o al abstract de ADS es candidato a **diferencia de versión** —
   abrí el PDF publicado o anotá la salvedad en la nota. El verify lo detecta después; acá es donde
   el valor **entra** a la ficha.
   Cascada: poblás la extracción **de las notas de paper**
   (`methods`, `thesis_links`, `role`, P/K/indicadores). La ficha se escribe **después**
   del contraste (2b) — no saltar de leer a la prosa.
2b. **Contraste cross-paper (#72)** ⚠ *(el skill `ingest-star` numera este paso como **3b**: su `2b` es el barrido full-text `query_ads --sweep`, que esta cascada no menciona)*. **(cont.) — entre leer los papers y escribir la síntesis.** Es el paso con
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
> (nunca pisa la extracción LLM; si ya están, no toca nada); (c) `ingest-theme` incluye un paso de
> **retro-tag por grep**: buscar los `aliases` del tema en el fulltext de **todo** el corpus y
> taguear (add-only, con juicio de LLM: uso real, no mención al pasar) los papers que la query ADS
> no devolvió. Así la entidad nueva ve también lo que ya estaba en el corpus.

> **Tema fuera de ADS (opt-in — sólo a pedido explícito).** Por default un tema se baja por **ADS**
> (ADS/arXiv/NEA — la plomería con **descubrimiento automático**: query → clasificar
> (`relevance.facets`) → bajar). El foco de Almagesto es **astro**; el **modo off-ADS** existe para
> los **métodos de otras disciplinas** que el trabajo astro usa —análisis de datos, estadística,
> machine learning, procesos gaussianos, signal processing— y cuya bibliografía canónica vive
> **fuera de ADS** (el eje tema/concepto y la capa de calidad son agnósticos de disciplina, así que
> la cadena los soporta igual). Diferencia operativa: sin ADS las fuentes se **declaran**, no se
> descubren por query — por eso es opt-in: si el usuario lo pide **explícitamente**, el skill
> `ingest-theme` lo soporta (fuente = PDFs locales + web;
> sin `query_ads`/`fetch_ground_truth`). Formalizado en el tooling: la
> entrada del tema en `themes.yaml` lleva `source: ads | web | local-pdfs [+web]` y (si es off-ADS) la
> lista `sources:`; `scripts/ingest_theme.py <slug>` orquesta la cadena según ese campo — también en
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
Cada sujeto ingestado deja un registro que **se commitea y viaja**, con tres secciones de dueños
distintos: **`busquedas`** (lista, una entrada por corrida — **acumulativo**, D-28: antes pisaba, y
la cabecera de la ficha publicaba el embudo de la última corrida como si fuera el universo entero;
el universo del sujeto es la **unión**, no la suma, y cada entrada distingue `n_nuevos` de
`n_ya_estaban`), **`cadena`** (qué pasos corrieron, con fecha, versión, `via: orquestador|suelto` y
las **escotillas** usadas — D-57: **cada script se estampa a sí mismo**, así que un paso corrido a
mano deja rastro en vez de leerse como un corte; el lint compara contra el orden canónico y
**nombra el paso** donde se cortó) y **`decisiones`**. Un descarte que se **revierte** (el bibcode
pasa a `extra_core`, la fuente se vuelve a declarar) no queda contradiciendo lo hecho: se **anula**
explícito, con el motivo viejo preservado en `previa` (D-52). Y la compuerta de triage **ya no se
puede apagar por flag** (D-48: `--no-triage` se eliminó — permitía que un candidato ya descartado
volviera a entrar en silencio). La sección `busquedas` la escribe `query_ads` al cerrar cada corrida: `fecha`, `query` efectiva
—en una estrella la arma `build_query` y antes se tiraba—, `rows`, `n_found`, `n_total`, `n_core`,
`n_candidates`, `n_dropped`, `truncated`, `almagesto_version`, **`bibcodes`** —lo que hace posible
la unión de D-28— y **`lente`** —facetas/`require`/`min_facets` vigentes al correr, contra lo que
se detecta la lente desincronizada—) y **`decisiones`** (el juicio de
curación, por clave: `decision`/`motivo`/`fecha`). Las `decisiones` cubren los **dos carriles**:
`triage.py --drop` para el candidato del citation chaining (por bibcode) y `triage.py --drop-source`
para la **fuente declarada** de un tema off-ADS (#81 — clave sintética o url, con `origen:
fuente-declarada` y un `fuente:` que la resuelva; sin `origen` = chaining). El segundo existe porque
en off-ADS `sources:` registra sólo lo aceptado: es la misma asimetría de #51 en el otro carril, y
`ingest_theme` **avisa** —no frena— si un item de `sources:` lleva una clave (o una url) ya descartada. Regla de
oro: **`build/` guarda lo regenerable, el registro guarda lo que no lo es.** Un `ads.json` se recupera pidiéndoselo de nuevo a
ADS; el juicio de por qué descartaste un candidato, no —y hasta 1.8.x vivía en `build/`, gitignored,
así que en otra máquina el triage lo re-proponía todo sin el motivo (los **aceptados** ya persistían
en `extra_core`: la asimetría era el bug). `busquedas` responde la otra pregunta, la del consumidor:
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
item en `sources:` + `ingest_theme.py`, o las piezas sueltas `fetch_web`/`make_notes --web`),
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
   Si es test de hipótesis, taggeá los papers con `thesis_links` para el roll-up y declará la
   **postura de cada uno en la tabla de evidencia de la hipótesis** (D-21).
4. Distinción: **hipótesis** (supuesto durable que sostenés) → `concepts/hypotheses/`; **búsqueda
   general** → `queries/`. No toda query es hipótesis.

### Verify (chequeo claim↔fuente — skill `verify-citations`)
**Extensión propia de esta wiki** (el lint canónico de Karpathy NO valida que la fuente respalde la
afirmación — sólo salud estructural; tapa el *grounding gap* / *epistemic drift*). **Cuándo:** paso de
cierre de **toda operación que escriba prosa con `[[bibcode]]`** — ingest-star (ficha + papers),
ingest-theme (concept + papers), append-knowledge, find-contradictions (las disputas nuevas),
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
disputa) y se deja un bloque `## Verificación de citas` en la nota — **una fila por par**, con dos
columnas de hash (**el ancla**, D-4/D-20):
`| # | Afirmación (extracto) | Fuente | Veredicto | Score | Evidencia | Ancla | Hash fuente |`.
El **ancla** es el sha256 (10 hex) del **bloque markdown normalizado** que contiene la cita
—párrafo / fila / ítem / blockquote—: reflowear la nota **no** la mueve, cambiar un número **sí**, y
una fila sin `[[bibcode]]` propio hereda el del caption hasheando **los dos** bloques. El **hash de
fuente** es el del `.txt` que se leyó, y es lo único que detecta que el PDF se **re-extrajo** y la
fuente ya no dice lo mismo **sin que la nota se haya tocado**. Los dos los calcula
`scripts/lib_blocks.py` (`pairs_of`, `source_hash`), el mismo código que después los chequea: no se
escriben a ojo. ⛔ **Sin fila no hay dónde colgar el ancla** — colapsar las soportadas en un párrafo
de prosa y dejar en la tabla sólo las que fallaron deja al lint sin poder distinguir "verificada" de
"nunca se miró".
**La nota nace 100% verificada (D-5):** al armar una ficha o un concepto se verifica **todo**; el
estado *"sin verificar"* sólo puede aparecer **después**, por una edición. Eso es lo que hace viable
el chequeo — el caso normal es que nada cambió y el lint calla, así que cuando habla hay algo real. El subagente contesta además, **en todos los casos**, si el paper
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
**Qué es una `inferencia` y cómo se escribe (D-42).** Es una afirmación que la bóveda sostiene y
que **ninguna fuente dice**: sale de combinar dos o más que sí lo dicen ("11,5 d es el armónico de
34 d"; "el veredicto de esta hipótesis, agregando doce filas de evidencia"). No es una excusa para
lo no verificado: es la **declaración explícita** de que el respaldo es un razonamiento y no una
cita, para que el consumidor la pese distinto.

Se escribe **nombrando sus premisas**: `(inferencia de [[b1]], [[b2]])`. Sin al menos un
`[[bibcode]]` la marca es una afirmación sin respaldo disfrazada de marca —no hay de qué se dedujo,
así que no hay nada que auditar— y **el lint la bloquea**. La palabra en prosa normal ("la
inferencia bayesiana permite…") no es una marca y no dispara nada.

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

### Pasada de red (lo que cambia AFUERA — `scripts/sweep_external.py`)
Una bóveda afirma cosas sobre el mundo y el mundo cambia después del ingest. **Cinco** cosas
caducan y se miran en **una sola pasada** —las cinco desde 1.35.0—: retracciones, correcciones, **versiones**
(el preprint salió publicado → otro bibcode para el mismo trabajo, D-19), **snapshot web** (una
fuente web no tiene ni DOI ni bibcode: nada avisa que cambió, y como el archivo local **no** se
toca, el ancla de fuente tampoco se entera — es el modo de caducidad más silencioso de los cinco) y
**ground-truth** (NEA cambia valores entre releases, y el snapshot era un JSON congelado que
**nada** comparaba — el caso más silencioso). Si están repartidas, se corren cuatro y la quinta
nunca.
⛔ **Reporta, no aplica solo**: el diff se muestra y se pregunta antes de tocar nada — un snapshot
que se actualiza solo cambia valores **bajo los pies de la prosa que ya los citó**. Lo que sí es
automático es la consecuencia offline: al cambiar un `.txt`, el **ancla de fuente** (D-20) marca
sola los pares verificados contra él. El renombre preprint→publicado **nunca** es automático
(reescribe wikilinks de toda la bóveda): se propone el comando.
La caducidad se registra **versionada** en `vault/config/registro/_red.yaml` — "cuándo se miró
afuera" es información de la bóveda, no de la máquina. Un detector que **no pudo correr** se
declara y **no** entra en `cubrio`: el registro no puede afirmar haber mirado lo que no miró.

**Fuente retractada citada en prosa (D-47):** la afirmación **no se borra** —puede ser cierta por
otra vía y borrarla destruye trabajo—: se **marca en línea** con `[[bibcode]] ⛔retractada`. Sin la
marca, el lint la localiza y **bloquea**; con la marca baja a informativa (visible, no destruida).
El símbolo es deliberado: un `(retractada)` pelado daría falso positivo con cualquier mención del
hecho en prosa. Junto con `(inferencia de [[bibcode]])` son las **dos únicas marcas en línea** del
sistema.

### Mantenimiento (cuidar lo ya ingestado — skill `maintain`)
**No crea entidades** (eso es Ingest); opera sobre estrellas/conceptos que **ya existen**. Sub-modos:
**refrescar** (papers nuevos → re-sintetizar sólo lo nuevo), **borrar** y **renombrar** una entidad
—`python scripts/entity.py delete|rename` (INV-19): las **siete** capas (clave del YAML, registro,
ground-truth, `raw/pdfs`, `raw/fulltext`, nota, `build/`), dry-run sin `--yes` porque el registro es
el único artefacto no regenerable. Lo que no hace solo lo **avisa**: no borra el paper compartido, no
repara los `[[wikilink]]` que quedan rotos ni la nota que queda sin destino. Del otro lado, el lint
reporta las **capas colgadas** de un slug que ya no existe—, **re-clasificar** tras cambiar
`relevance.facets`, **resolver el
backlog del lint** (P_rot sin documentar, drift PDF↔disco, cobertura — los **huérfanos no**: son
bloqueantes, se arreglan al cierre de la operación que los creó), y la **pasada periódica de red**
(`python scripts/sweep_external.py`, toda la bóveda — la cadena de ingest sólo chequea el slug en
curso; **esa misma pasada estampa también `corrections`**, con el mismo valor
que para las retracciones: cazar lo publicado **después** del ingest y cubrir el corpus anterior a
1.8.0. Lo ingestado desde entonces ya trae sus `corrections` estampadas por la cadena). Invariante: la cadena es
idempotente (refrescar es seguro); **nunca** se pisa la extracción LLM ni el ground-truth sin `--force`
explícito. Detalle en el skill.

### Lint (chequeo de salud)
**Cuándo:** como **paso de cierre de toda operación que escriba en `vault/wiki/`** (ingest,
append-knowledge, maintain, find-contradictions, query archivada, test de hipótesis), **antes de
commitear** y **después** del verify (resolver una cita no-soportada cambia la prosa); más una pasada completa periódica. Es barato.
Correr `python scripts/lint.py`: la categoría **⛔ No evaluado** (un chequeo que **no pudo correr**
—`objective.yaml` ilegible, sin `git` para medir la verificación stale—) **cuenta para el exit y su
categoría normal se suprime del reporte**: un `(0)` que nadie midió se lee como veredicto, y ése es
el falso limpio que el lint existe para no producir. Es hecho del **entorno**, no de la bóveda. En
la misma línea, `query_ads` **rehúsa clasificar** con una lente ilegible en vez de degradar a `{}`
en silencio (clasificar con una regla que nadie escribió marcaría el corpus entero, y el registro
guardaría esa lente vacía como si fuera la vigente). Además debe quedar en **0** para wikilinks rotos, **frontmatter no
parseable o con forma inválida** (nota que empieza con `---` pero cuyo YAML no parsea —p. ej. un
`title:` con `:` sin comillas editado a mano—, o un campo que el schema declara **lista** escrito
como escalar / con elementos que no son mapas —`planets:`, `thesis_links:`—: en los dos casos la
nota **evade en silencio** los chequeos por elemento de su tipo), **papers retractados**
(flag `retracted`; lo detecta `scripts/check_retractions.py` vía Crossref —red; la cadena de ingest
chequea sólo los papers del slug (`--slug`) y el barrido completo de la bóveda es la pasada
periódica del skill `maintain`— y el lint lo surface offline: una fuente retractada citada rompe la
frontera dura),
páginas huérfanas,
contradicciones ground-truth↔ficha —**qué planetas (no cuántos) y campo por campo**: un planeta
que la ficha lista y NEA no (típicamente una señal no confirmada escrita en `planets[]` en vez de
`disputes` como `<letra>.existence`), uno que NEA confirma y la ficha no lista, una letra repetida, y
un valor que difiere del ground-truth o que existe en la ficha cuando NEA no lo tiene: todos rompen
el espejo (#70), y comparar **cuántos** dejaba pasar el caso peor, dos listas del mismo largo que no
son los mismos planetas—; **también bloquea el ground-truth que el espejo no puede leer** (JSON
ilegible o no-objeto, `host` que no es un mapa, `planets` que no es una lista, `slug` interno que no
matchea el nombre del archivo, ficha sin frontmatter legible): no es "la garantía no corrió" sino
que el archivo que **es** la autoridad está roto, y callarlo deja la ficha sin vigilancia mientras
el lint afirma que está limpia —el `host` no-mapa, además, silenciaba los cuatro campos estelares y
encima producía hallazgos fantasma apuntando al síntoma equivocado—, **masa de ground-truth inconsistente con la m·sini implícita**
(K/P/e/M\* — atrapa best-mass espurias de NEA), **`thesis_links` sin página destino** (tag que no matchea
ninguna nota → no acumula en el roll-up; typo típico `shift-vs-shape` vs `shift_vs_shape`) y
**`disputes` con la `ref` de una posición sin paper destino** (el bibcode que sostiene esa posición
no existe como nota → la disputa no es trazable), **`disputes` mal formadas** (#71: sin `field`, con
menos de dos posiciones —con una sola es una afirmación, no un desacuerdo—, con una posición que no
dice quién la sostiene, o con un `source` fuera del vocabulario), **`disputes` en el schema viejo**
(`planets[].disputes[]`, que el lint ya no lee: migrar), **nota de paper con `topics:`**
(el campo pre-R-5 que quedó sin lector — el vigente es `facets:`), **registro con
`busqueda:`** (mapa, schema pre-D-28: hoy es `busquedas:`, lista) y
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
paper. Dos recortes de la población, los mismos que usa el backlog hermano de `role`: la cita tiene
que estar en una nota de **entidad** (`stars/` o `concepts/`) —una `queries/` es una respuesta
puntual, no la síntesis durable de un sujeto— y la nota **no-core** (`relevance: low`, escrita con
`--all`) no entra: no se le pide aterrizar en ninguna síntesis. La **lente desincronizada** (D-49) es **backlog**: la `lente` que el registro guardó en la última
búsqueda del sujeto ya no es la vigente de `objective.yaml` —editar una regex mueve el corte
core/no-core **sin mover `almagesto_version`**—, así que el corpus quedó clasificado con una regla
que nadie usa. El diff corre **sólo** cuando las lentes difieren (el caso normal es igual y es
gratis) y es **offline**: re-clasifica desde las notas (título + abstract + `keywords`), no desde
`build/`. Nombra los stems que entrarían y saldrían. **Alcance declarado:** evalúa la mitad
**textual** (`facets`/`require`/`min_facets`); la nota no guarda `doctype`, así que un cambio que
sólo mueve `noise_doctypes` se declara *no evaluable* en vez de devolver `+0/−0`, y los papers del
universo sin nota se publican como techo. Sin `lente` en el registro: *no evaluado*, nunca cero.
El **alcance de hipótesis sin declarar o vencido** (D-34) es **backlog**: o la nota no trae el
blockquote `> Alcance …` (y su veredicto negativo se lee como universal), o lo trae y los slugs que
nombra tienen hoy más papers de los declarados (el veredicto se testeó contra un universo que ya no
es el suyo). La **cobertura** (concepto/hipótesis
sin ninguna cita `[[bibcode]]` → afirma sin fuente) es **backlog** que el lint surface para ir citando;
ídem la **cobertura de verificación** (query/concepto **con** citas pero **sin** bloque
`## Verificación de citas` → nunca pasó por `verify-citations`: correr el skill).
Los **pares de verificación vencidos** (D-4/D-20) son la medida fina de lo mismo, por **par** y no
por archivo: *sin verificar* (hay una afirmación citada sin fila), *vencido por edición* (el ancla
ya no coincide), *vencido por fuente* (el `.txt` cambió), *fila huérfana* (la afirmación se borró).
**Dos severidades, un solo detector (R-1):** sin flag es la **pasada periódica** y reporta como
backlog; con **`python scripts/lint.py --cierre`** cuentan para el exit — es el paso de cierre de
toda operación que tocó la nota, donde un par sin verificar significa que **no terminaste**. Los
skills de cierre lo invocan con el flag; la pasada de higiene de `maintain`, sin él. Aparte y
**bloqueante siempre**, el **bloque con plantilla vieja** (sin las columnas de hash): no es "cero
vencidos", es un bloque que nadie puede evaluar. Sigue existiendo la **verificación
stale** (la nota se editó **después** de la fecha de su bloque —lo que pasa al ampliarla con
`append-knowledge` o refrescarla— así que las afirmaciones nuevas nunca pasaron por el fan-out pero
quedan bajo un encabezado que se lee como vigente: es el modo de falla de "afirmar de menos"
aplicado a la garantía misma; el lint lo mide por `git` contra la fecha del encabezado —por eso el
bloque **debe** llevar fecha—. **Ya no es el mecanismo principal**: las anclas lo reemplazan con
granularidad de par, y esto queda como **red** para notas con bloque y sin tabla parseable; **fuera de un repo no degrada a silencio**: el chequeo cae en la
categoría **⛔ No evaluado** y cuenta para el exit, porque un `stale (0)` que nadie midió se lee
como "todo al día" (D-43). La rama "bloque sin fecha" no necesita git y sigue corriendo siempre).
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
--reason`). Sin `build/` local **no** da un cero inventado: cae a `busquedas` del registro versionado
y reporta el snapshot con su fecha (no el conteo vigente — si dropeaste sin re-correr la cadena
quedó viejo). Y si ese registro **no se puede leer** (YAML roto o con forma inválida) se reporta
**ahí mismo**, nombrando el archivo: saltearlo en silencio devolvía un `(0)` sobre un registro que
declaraba candidatos sin juzgar — el mismo cero inventado que #64 cerró, por otra puerta. El
registro es además el **único** artefacto de la bóveda que no es regenerable, así que la lectura
tolerante que evita tumbar al lint **no** habilita pisarlo: `save_registro` es atómico (tmp+rename)
y **rehúsa escribir** sobre un registro existente que no parsea, en vez de perder `busquedas` y los
juicios de curación en silencio. Su hermana, la **decisión con forma inválida** (una entrada de
`decisiones` que no es un mapa — `2006Rasmussen: descartado` a secas), es **backlog** propio:
`load_decisiones` la descarta y sin el aviso el triage vuelve a proponer lo ya descartado **sin el
motivo**, que es exactamente el bug que #51 cerró.
El **corpus truncado** (un `build/<slug>/ads.json` con `truncated` seteado → la query directa trajo
menos papers de los que ADS reporta) es **backlog** — `query_ads` persiste la marca (default
`--rows 2000`, ≈ el máximo de una request; re-ingestar con `--rows` mayor para cubrir el resto). Lo
que falta ahí es **el medio**, no la cola: al truncar, `query_ads` corre una **segunda pasada con la
misma query ordenada por fecha** (#79) y la marca guarda en `truncated.recent` cuántos rescató, así
que lo reciente —lo que el orden por citas esconde por construcción— ya está cubierto; ídem el
**rescate por glifo incompleto** (`truncated_glyph`, marca hermana: el superset de la constelación
del rescate #28 se cortó por citas **antes** del filtro client-side, que es donde vive la señal →
pueden faltar papers con lookalike). Los **campos incompletos** son **backlog** y no bloquean; hoy son ocho:
`P_rot` sin documentar en la prosa (el frontmatter nulo **no** es hallazgo desde #70),
`activity_indicators_expected` vacío, planeta del frontmatter no discutido en la prosa, paper core
sin `methods` (sin extraer), paper extraído sin `role`, ~~`thesis_links` sin `bearing`~~ (retirado por D-21), y **ficha sin
su `raw/ground_truth/<slug>.json`** (el barrido del espejo #70 lo maneja el JSON, así que una ficha
sin archivo no la mira **nadie**: se le pueden inventar `teff_K`/`P_rot_days`/planetas enteros con
el lint en verde — es backlog y no bloqueante porque es "la garantía no corrió acá", no "hay una
violación"), y su **hermano simétrico**: un `raw/ground_truth/<slug>.json` **sin** su
`stars/<slug>.md`, que es un renombre a medias o una ficha borrada sin limpiar — el espejo no tiene
con qué comparar y nadie avisa que ese ground-truth quedó colgado. Revisar
El **recorte de lectura sin declarar** (core sin extraer y sin `extraccion:` en el registro)
es **backlog**; ⚠ hoy **ningún script ni skill llama a `save_extraccion`**, así que ese canal
está sin cablear y el hallazgo no tiene cómo cerrarse (INV-83 `parcial`). Revisar
además a mano: claims stale y conceptos referidos sin página. Si faltan datos, abrir queries para
imputar (web/ADS).

## Cinco reglas de método (por qué existen las redes de abajo)

Salieron de medir una sesión entera donde **los defectos los encontraron agentes leyendo el código,
no la suite**. No son consejos: cada una nombra un modo de falla que ya ocurrió acá, y las redes de
la sección siguiente son su mecanización.

1. **Un test con la red falseada valida que el CLIENTE funcione, no que el CONTRATO se cumpla.**
   Los tres bugs serios de la Tanda 7 los encontraron el smoke test contra la API real, el corpus
   real y una auditoría adversaria — ninguno la suite, que estaba verde. Si escribís un cliente de
   red, **probalo una vez contra el servicio de verdad** antes de darlo por hecho.
2. **Un doble de test con distinto contrato que la función real esconde el bug en la diferencia.**
   Medido: el doble de `refs_of` indexaba por el input verbatim y el real por `_bare_doi`; el
   consumidor buscaba con la clave cruda, pasaba los tests y en producción reportaba **cobertura
   mal atribuida**. Un doble o deriva de la función real, o tiene un test de paridad.
3. **Un test verde recién escrito no cuenta hasta que lo viste morir.** Pasó dos veces en un día:
   el test se escribió, pasó a la primera, y sólo la mutación mostró si servía. Por eso el gate de
   mutación es la red #1 y no un extra.
4. **Un mapa que atribuye mal es peor que uno vacío**: el vacío se ve, la atribución falsa se lee
   como verdad. Vale para `docs/trazabilidad.md`, para las filas de `docs/contrato.md` y para
   cualquier tabla que este repo estampe.
5. **Cuando dos mediciones no reconcilian y no se puede re-medir, se DECLARA la discrepancia** en
   vez de elegir un número. Elegir en silencio es cómo un documento empieza a mentir.

Corolario que las cruza a todas: **una promesa que el sistema dejó de cumplir en silencio es peor
que una que nunca hizo.** Si al tocar algo se rompe una promesa declarada —un presupuesto de
tiempo, una cobertura, un 1:1—, eso **se anota**, aunque no se arregle en el momento.

## Al escribir código: las cinco redes (regla permanente)

Toda función nueva de `scripts/` pasa por esto **antes de cerrar el issue**. Detalle y ratchets en
`tests/README.md`; el resumen operativo:

1. **Mutación** — `python tools/mutar.py --diff`: romper cada función y exigir que **algún test
   muera**. Es lo único que distingue "el test pasa" de "el test **podría** fallar". Trabaja sobre
   una copia del repo, nunca sobre el árbol real.
2. **Schema compartido** — si N módulos prometen la misma forma, se prueba **una vez parametrizada**
   (`tests/test_backends_schema.py`), no con prosa en N docstrings.
3. **Doble vs real** — un doble de test no se escribe a ojo: o deriva de la función real, o hay un
   test que fija que coinciden. El bug más caro de la Tanda 7 vivió exactamente en esa diferencia.
4. **Nadie sin ejecutar** — `pytest tests/poblada/test_cobertura.py -m poblada` (~11 s): una función
   que la suite nunca corre no está "mal probada", está **sin mirar**.
5. **La doc es ejecutable** — `tests/test_docs_ejecutables.py`: todo test, script y
   archivo de config que la documentación nombra tiene que existir, y todo
   comando que invoca un skill tiene que compilar.

Las 2 y 5 corren solas en tier 0. El motivo de la regla: en la sesión que la produjo, **los bugs
los encontraron agentes leyendo el código, no la suite** — y cada hallazgo era decidible, o sea que
podría haber sido un assert.

## Token / secretos
El token ADS va en `vault/config/ads_dev_key` (**gitignored** — nunca se commitea) o en la variable de
entorno `ADS_DEV_KEY`. Token gratis en <https://ui.adsabs.harvard.edu/user/settings/token>.
`build/` y `outputs/` gitignored. PDFs por git-lfs (`vault/raw/pdfs/**/*.pdf`). El resto de
`vault/config/` **sí se commitea**, incluido `registro/<slug>.yaml` (es el punto: el juicio de
curación y el registro de búsqueda tienen que viajar).
