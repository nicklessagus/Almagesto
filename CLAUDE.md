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

> **Dónde está el porqué largo (AUD-475).** Este archivo lleva **regla + consecuencia + ancla**. El
> caso, la medición y la mecánica fina de cada sección viven en `docs/operacion.md` § *Apéndice A*,
> **con los mismos encabezados que acá**; el catálogo del lint en `docs/lint.md`; la evidencia por
> issue en `docs/mediciones.md`.

> **La cabecera de una ficha/concepto lleva una línea `> _Estado — …_`** con **tres fechas** que
> avanzan por separado (D-12): **búsqueda** (última corrida + universo acumulado + escotillas),
> **síntesis** (se **declara**, `cfg.save_sintesis` / `triage.py --sintesis`: `git` fecha el archivo,
> no la reescritura) y **verificación** (fecha del bloque, con la salvedad fija *"vigencia por par: la
> dicen las anclas"*). ⛔ **El ARRASTRE del re-anclaje se declara al lado (#499)**: `· re-anclado
> AAAA-MM-DD` en el encabezado del bloque, `, re-anclado AAAA-MM-DD` en esta línea — `--reanclar`
> conserva la fecha (nada se verificó, #395) y el lint compara contra ésa. Con una sola fecha,
> refrescar hacía parecer re-verificado lo que nadie volvió a chequear (INV-82).

> **Al iniciar sesión, leé `vault/STATUS.md` (estado + próximos pasos) y `vault/wiki/log.md` (historial
> reciente) para orientarte.** *(En el repo **template** esos dos son la **semilla**; el handoff del
> framework vive en `docs/internal/HANDOFF.md`, no versionado.)* ⛔ **`index.md` se ESTAMPA
> (`python scripts/make_notes.py --restamp-index`, #237), no se edita a mano**: las tablas se
> materializan por verdad de frontmatter (Dataview queda debajo como comodidad, #60) y el lint
> reporta el índice desactualizado nombrando los stems. La "memoria" del proyecto es in-repo: este
> `CLAUDE.md` + `vault/STATUS.md` + `vault/wiki/log.md` + `vault/wiki/index.md` — no la memoria local
> de Claude (`~/.claude/...`), que no viaja. Tras cada operación, re-estampá `index.md`, appendeá a
> `log.md` (entrada `## AAAA-MM-DD — <op>: <título>` + bullets) y, si cambió el estado,
> `vault/STATUS.md`. ⛔ **El `STATUS.md` se REESCRIBE, no se appendea (#302)**: estado vigente + **una**
> lista de próximos pasos; lo histórico va al `log`, con fecha. El lint levanta el apilamiento.

## Layout del repo — la bóveda vive en `vault/`

El repo separa **andamiaje** (raíz) de **bóveda** (`vault/`):

```
Almagesto/
├── CLAUDE.md  README.md  requirements.txt  scripts/  .claude/skills/   ← andamiaje (framework)
├── build/  outputs/                                                    ← scratch del tooling (gitignored)
└── vault/                                                              ← la bóveda — Obsidian abre ACÁ
    ├── config/  (objective.yaml, stars.yaml, themes.yaml, ads_dev_key, registro/<slug>.yaml)
    ├── wiki/    (stars, papers, concepts, queries, matrices, index.md, log.md
    │             + <nota>.verif.md — el hermano de auditoría de cada nota verificada, #344)
    ├── raw/     (pdfs, fulltext, extraccion, ground_truth, refs)
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
`vault/.obsidian/`, `README.md`, `requirements.txt` —: los cambios se hacen en el template y se traen
por merge; editarlos en la instancia **da conflictos**. En la instancia sólo se edita **contenido**
(`vault/wiki/`, `vault/raw/`) y los **archivos de instancia** protegidos por `merge=ours`
(`vault/config/objective.yaml`, `vault/config/stars.yaml`, `vault/config/themes.yaml`,
`vault/STATUS.md`, `vault/wiki/index.md`, `vault/wiki/log.md`, `vault/wiki/matrices/method_star.md`).
⛔ **El driver de `merge=ours` se pasa POR COMANDO y NO se registra en el clon (#390):**
`git -c merge.ours.driver=true merge upstream/main` — registrado, descarta en silencio lo que traiga
`origin` (la otra máquina). El lint **bloquea** al clon que lo tiene puesto.
**Si una operación revela una mejora de framework**, **abrí el issue en el template y pará ahí
(#377)**: anotá el nº en `vault/STATUS.md`/`log.md` y seguí; la instancia **no commitea framework**.
*(En el repo template mismo, editar framework **es** la tarea.)*

⛔ **Y todo issue —al REPORTARLO y al CERRARLO— contesta «¿quién MÁS lleva esta regla?» (#409).** El
issue nombra **la regla**, no sólo el síntoma (el fix contra el caso es la familia de defectos más
grande del repo), y antes de cerrarlo se enumeran los portadores con
`python tools/carriers.py --propose <mod>.<simbolo> --patron '<re>'` — `--check` en 0 **no alcanza**
si nadie enumeró. Firmarlos en `tools/portadores.yaml` es **framework**: desde una instancia el
hallazgo va al issue del template con la salida pegada.

## ⛔ Frontera dura — la bóveda es SÓLO bibliografía (regla #0, no negociable)

**Esta wiki es una referencia bibliográfica. Punto.** Almagesto recopila información bibliográfica y
**todo lo que afirma está respaldado por una fuente citable (`[[bibcode]]`).** El flujo es
**unidireccional y de sólo lectura hacia afuera**: alguien lee de la bóveda; **la bóveda nunca
describe, parametriza ni se acomoda a quien la consume.**

> **La bóveda es READ-ONLY desde afuera.** Si estás leyendo esto como agente de otro repo: acá se
> **lee**, no se escribe. Podés sacar un valor, un mecanismo o una ecuación —siempre arrastrando su
> `[[bibcode]]`— y **nada de tu lado entra**: ni cómo lo vas a usar, ni qué decide en tu pipeline,
> ni qué parámetros elegiste a partir de esto. Escribir eso acá convierte una referencia
> bibliográfica en documentación de tu implementación. El detector de fuga del lint (`downstream: []`
> en `objective.yaml`) marca esa prosa; la marca es una red, no un permiso.

**Contrato con quien consume la bóveda (instrucción para vos y para cualquier agente/humano externo
que lea esto):** lo que sacás de acá viaja con su `[[bibcode]]`. Si usás la bóveda para **escribir
código**, dejá la cita de la fuente en un comentario junto al valor o decisión que tomaste de ella; si
la usás para un **informe o paper**, citá la fuente correspondiente. Nunca propagar un número o una
afirmación de la bóveda sin arrastrar su respaldo bibliográfico — ese es el punto de que esto exista.

⛔ **Y antes de usar una afirmación, VALIDALA CONTRA LA FUENTE. No sintetices desde la ficha sola.**
Al sacar un valor, una ecuación o un mecanismo de una nota para llevarlo a código, a un informe o a
otra síntesis, confirmá que la fuente dice eso **antes** de propagarlo — chequeo por par, no
re-lectura del paper. La prosa de una ficha es **capa LLM** y `verify-citations` es **juicio de LLM,
no prueba** (medido: 7 de 13 defectos eran de atribución, invisibles desde la ficha).

**Cómo (#205):** abrí el **PDF** (`vault/raw/pdfs/**/<bibcode>.pdf`) y citá **página**. El `.txt`
(`vault/raw/fulltext/**/<bibcode>.txt`) sirve para *ubicar* con `grep -n`, no para citar: pierde
fórmulas, tablas-imagen y figuras **sin avisar**, así que un `grep` vacío **no** significa que la
ficha esté mal. Con `pdf_source: eprint` el PDF es el preprint: una discrepancia numérica es
candidata a diferencia de versión, no a error de la ficha.

Si al validar encontrás una discrepancia, **no la arregles en silencio de tu lado**: es un hallazgo
de la bóveda — reportalo, o el próximo consumidor tropieza con lo mismo.

**Test de admisión (aplicá a TODA línea de `vault/wiki/`):** *¿esto sale de una fuente
(`vault/raw/`) y lo puedo respaldar con un `[[bibcode]]`, o es una conclusión derivada de fuentes
citadas?* Si la respuesta es **no → no entra al vault**, sin excepciones — ni por útil ni por obvio.

**Prohibido inlinear en `vault/wiki/` (no es bibliografía):** parámetros, perillas o **dials** de un
generador/pipeline; nombres de variables o estructura de código; reparametrizaciones y **decisiones
de diseño** de una implementación; recetas operativas de "cómo correr" que no sean un hecho citable.
**Sí es citable (entra):** resultados publicados —**incluidos papers de simulación**: rangos
medidos, mecanismos, signos, escalas temporales, fórmulas de la fuente. La distinción es
**publicado-y-citable vs implementación de código**, no "simulación sí/no". **Si detectás
contaminación**, sacala de `vault/wiki/` y marcalo en el `log`.

**Punteros a otros repos (prosa no, frontmatter estructural sí):** lo prohibido es el puntero
downstream **en prosa / como motivación** ("para qué sirve en <repo consumidor>"). Los **campos
estructurales** de `stars/` —`data_local`, `methods_applied.ours`— **sí** pueden apuntar afuera: son
contrato máquina-legible. **Migrando una instancia heredada**: borrar de notas de método/queries los
comentarios "para qué sirve en <downstream>" y la parte decisión-downstream de las disputas;
`data_local`, `methods_applied.ours` y `log.md` se quedan.

## Arquitectura (analogía de compilador)

- **`vault/raw/`** = lo que se leyó, **inmutable una vez escrito**: `pdfs/<slug>/` (git-lfs),
  `fulltext/<slug>/*.txt` (índice de búsqueda), `extraccion/<slug>/*.json` (#311: las vistas del
  fan-out, **versionadas** — no se regeneran sin volver a leer el PDF) y `ground_truth/<slug>.json`.
- **el LLM** = compilador.
- **`vault/wiki/`** = ejecutable. `.md` que escribís vos: `stars/` (entidades), `papers/` (resúmenes de
  fuente), `concepts/{methods,hypotheses}/` (⚠ las áreas son **abiertas**: ésas son las dos que el
  framework distingue de verdad, cualquier otra que declares es **archivado** — ningún chequeo se
  ramifica por el área, #246), `queries/`, `matrices/`,
  `index.md` (catálogo) y `log.md` (registro append-only).
- **lint** = tests. **queries** = runtime.
- **este `CLAUDE.md`** = schema (cómo te comportás).

Divergencia deliberada respecto del patrón Karpathy (mantener): el frontmatter de `stars/` y
`papers/` es **máquina-legible** y sirve de **contrato para cualquier consumidor** que arme código,
un informe o un paper a partir de la bóveda, no sólo para Q&A humano. No romper esos campos.

## Frontmatter obligatorio

Toda nota de `vault/wiki/` lleva frontmatter YAML. Campos comunes: `tags`, `generator`
(`Almagesto v<x>`, provenance — lo estampa `make_notes` desde `lib_config.ALMAGESTO_VERSION`), y
cuando aplique `confidence: high|medium|low`.

⛔ **PROHIBIDO DE MEMORIA, en todo campo que IDENTIFICA algo (#392):** clave sintética, `author`,
`title`, `year`, `doi`, `aliases`, el `value` de una `disputes[].posiciones[]` y el `motivo` que
afirma qué es el paper salen de una fuente **abierta en ese momento** —primera página del PDF
(`pdftotext -f 1 -l 1 <pdf> -`), registro ADS/Crossref por DOI, o el `.bib`/`.xlsx`/`.csv` del
usuario al lado del PDF, que se lee **antes**—, nunca por asociación con el tema. Un campo vacío es
backlog; uno inventado se lee como verdad.

> **Anclas.** Cada regla lleva su `(#N)` o `(D-N)`: el issue público
> (`github.com/nicklessagus/Almagesto/issues`) tiene el caso y la medición; `docs/contrato.md`, el
> invariante; `docs/mediciones.md`, la evidencia. ⛔ **El issue se CREA antes de escribir su número
> (#292):** el `(#N)` escrito antes se lo lleva el issue siguiente y la trazabilidad queda **mal
> atribuida**. La red es
> `tests/test_docs_ejecutables.py::test_todo_numero_de_issue_que_el_repo_cita_existe` contra la
> caché versionada `tools/issues.json` (`python tools/refresh_issues.py` al cerrar cada tanda).

⛔ **Criterio de admisión a ESTE archivo (#465): entra la regla que un agente necesita ANTES de
escribir o correr algo en cualquier sesión de una instancia.** Lo que sólo hace falta al escribir
código del framework va a `docs/desarrollo.md`; el catálogo por categoría, a `docs/lint.md`; la
mecánica de una operación, a su skill; el porqué largo, al *Apéndice A* de `docs/operacion.md`. Se
inyecta entero en cada sesión, así que el ratchet (`tools/doc-size-ratchet.yaml`) exige que **toda
suba declare qué sale, o por qué nada puede salir** (`sale:`).

### stars/

Campos: `name, slug, aliases, aliases_descartados, simbad_id, spectral_type, teff_K, dist_pc,
P_rot_days, mass_msun, activity_indicators_expected, planets[], disputes[], data_local,
methods_applied{literature,ours}`. Cada `planets[]` lleva `letter, P_days, K_ms, e, mass_earth,
status` (de ground-truth NEA; `mass_earth` RV-only ≈ $m\sin i$). Los desacuerdos van en `disputes` a
**nivel nota**, no dentro de `planets[]`.

⛔ **Espejo con AUTORIDAD POR CAMPO (#70 + D-1) — cada campo vale lo que dice SU autoridad o NADA.**
`spectral_type` ← **SIMBAD**; `teff_K`, `dist_pc`, `P_rot_days`, `mass_msun` (#272) y los cinco
campos de cada `planets[]` ← **NEA** (pscomppars). Si la autoridad declarada calla, el campo queda
`null` **aunque la otra tenga el dato**. El JSON registra `_autoridad` (quién contestó) y
`_otras_autoridades` (lo no adoptado, D-2); el desacuerdo se expresa como `disputes` con
`source: nea` / `source: simbad`. Los `null` de NEA son el caso **normal** y **no se rellenan con
literatura** (sería indistinguible del dato auditable, y adoptar un valor cuando las fuentes
discrepan es decidir por quien consume, regla #0): el valor de literatura va **al cuerpo, citado
`[[bibcode]]`**; si discrepa de NEA es una `disputes[]`; si es lectura propia va marcado
**`inferencia`**. Lo vigila el lint, campo por campo.

**La ficha lo publica arriba**, en el blockquote de cabecera: una línea `> _Ground-truth — …_` con
qué autoridad respondió cada campo, la fecha del snapshot, **qué campos volvieron vacíos**, los
*(sólo en el JSON)* y el puntero al JSON. Se estampa sola (`make_notes.py <slug>`, idempotente)
porque **el artefacto es lo que viaja**. El blockquote lleva además un **disclaimer ⚠ de capa-LLM**
(la prosa es síntesis a revisar; el frontmatter es auditable), exento del scan de fuga.

El cuerpo trae **`## Inventario por eje`** (el paso de contraste), **`## Huecos`** (qué falta para
que la ficha alcance sola), la sección estampada **`## Indicadores de actividad esperados`** —el
puente al concepto que explica cada uno, resuelto por alias y sin la glosa entre paréntesis (#250)—
y el apéndice **`## Excluidos por el filtro`** (los no-core, top por citas con link a ADS).

⛔ **Un `## Huecos` —de ficha o de concepto— declara su ALCANCE, igual que una hipótesis (D-34,
#342):** `> Alcance <fecha> · temas: […] + estrellas: […] · N papers`, **dentro de la sección**. Un
hueco es una afirmación **negativa** sin `[[bibcode]]`, así que no la mira ninguna capa de
verificación; el alcance la vuelve *acotada verdadera*, y el lint lo cruza contra el disco.

**Estándar: autosuficiente.** La ficha debe alcanzar por sí sola — un agente que la lee queda
servido **sin abrir ningún paper**: parámetros estelares, inventario de señales RV con $P/K/e/m\sin
i$ y estado, señales disputadas, indicadores esperados, métodos aplicados y huecos. Los
`[[bibcode]]` son **trazabilidad**: si para responder hace falta abrir el paper, eso va a la ficha.

**Regla de poda (paper secundario → ficha sólo si cambia una señal RV).** Un hecho de un paper
tangencial (no discovery, no árbitro, no actividad-$P_{rot}$) entra a la prosa **únicamente si cambia
cómo se lee una señal RV**. Todo lo demás —era instrumental, metodología RV
genérica, dinámica, ausencia de tránsito, debris, astrosismología, habitabilidad— vive en su nota de
paper y se consulta por la tabla `## Papers`. No re-narrar en la ficha lo que ya está en la
extracción.

#### Los cuatro roll-ups se ESTAMPAN, no son Dataview (D-10/D-11)

`## Papers`, `## Planetas` y `## Métodos aplicados a esta estrella` los regenera
`python scripts/make_notes.py <slug>` (idempotente, cirugía: no toca la prosa); el lint reporta como
backlog la tabla desactualizada **nombrando los stems**. `## Métodos aplicados…` lleva **una fila
por MÉTODO** (clave normalizada, variantes al lado) y colapsa la cola en un `<details>` que
**declara cuántos quedan adentro** (#273). `## Papers` —`Bibcode | Año | Relevancia | Origen |
Estado`— lleva en el encabezado **los dos números** (universo · sintetizados acá), y el **estado**
dice cuán lejos llegó cada paper (`fuera del filtro` → `sin extraer` → `extraído, no sintetizado` →
`sintetizado`). En un concepto el roll-up es la **unión** de `methods` y `thesis_links`, con la
columna *Entró por* (D-24), y **las mismas dos garantías** (#300).

⛔ **El cuarto es la MATRIZ método × estrella** (`--restamp-matrix`, #429): fila = método por clave
normalizada, columna = ficha, celda = los `[[bibcode]]` de los papers **de esa estrella** que lo
declaran en `methods`; `—` = *ninguno en este corpus lo declara*, afirmación **negativa**, así que la
sección declara su alcance (D-34). ⚠ **No** espeja `methods_applied.literature` (sin clave de join):
llenarla a mano publicaba **huecos falsos**.

El motivo (#60): un bloque ```dataview``` le muestra a un agente **la query, no sus resultados**. El
equivalente determinista parsea el frontmatter con el mismo parser que el tooling
(`lib_config.split_fm`), desde la raíz del repo:

```bash
# papers de una estrella (equivale al roll-up `## Papers`); con `fm.get('methods')` en el print,
# los métodos DE esos papers (no todo paper que use el método)
python -c "import sys,glob;sys.path.insert(0,'scripts');import lib_config as c;[print(f) for f in sorted(glob.glob('vault/wiki/papers/*.md')) if '<nombre>' in (c.split_fm(open(f,encoding='utf-8').read()).get('stars') or [])]"
```

⛔ **No uses `grep`/`awk` sobre el frontmatter para esto.** Las listas conviven en **bloque** y en
**flow style** (`stars: [tau Cet]`, como la deja `merge_frontmatter_list`), y el matcheo textual
confunde `GJ 71` con `GJ 710`; `split_fm` compara por elemento.

⛔ **El roll-up compara `methods` por CLAVE NORMALIZADA, no por string exacto (#243):** `casefold` +
NFKD + `[^a-z0-9]+ → -` (`lib_config.method_key`), compartida por roll-up y lint — el campo lo puebla
un LLM con vocabulario abierto (`PCA`/`pca`) y el string crudo subdeclara el universo. ⛔ Se
normaliza al **comparar**, nunca al escribir (la grafía del extractor es información). Los
**sinónimos** (`gls` / `periodograma-gls`) **no** se juntan solos: es juicio, va a un backlog que
propone y no aplica.

⚠ **El roll-up de métodos linkea `[[método]]` sólo si la nota existe —por stem **o por `aliases`**
del concepto (#245)— y si no, lo estampa como código**: las notas de `concepts/methods/` las crea
`ingest-theme`, otra operación, y el link incondicional dejaba wikilinks rotos bloqueantes. El lint
lo reporta como backlog *«`methods` sin página destino»* (a diferencia de `thesis_links`, que
bloquea: ése lo crea la misma operación que lo siembra).

#### Disputas (`disputes`, a nivel nota, con posiciones explícitas — #71)

Cuando dos fuentes discrepan sobre el mismo hecho —la **existencia** de una señal o el **valor** de
un parámetro— se taguea, no se sobreescribe. Cada entrada: `field` (`P_rot` para un campo estelar,
`<letra>.<param>` para uno planetario — `b.K`, `b.existence`), `posiciones[]` (**al menos dos**; con
una sola no hay desacuerdo: es una afirmación y va a la prosa citada) y `note` opcional. Cada
posición dice **quién la sostiene**: `{ref: <bibcode>, value: …}` para un paper (el bibcode debe
existir como nota — lo chequea el lint) o `{source: ground_truth, value: …}` cuando NEA arbitra. Ese
marcador distingue *"hay autoridad y dice X"* de *"la bóveda genuinamente no sabe"*. Cuando NEA
arbitra **sigue siendo el valor de verdad** y el frontmatter no se toca (espejo puro, #70).

Vale igual para **conceptos**, donde la disputa es simétrica por definición. Sólo taguear
discrepancias **materiales** (mayores que el error). Reflejar la disputa también en la tabla/prosa.

⚠ **El schema viejo** (`planets[].disputes[]` con `field`/`ref`/`note`/`alt`) no podía expresar
paper↔paper ni colgar `P_rot`. **El lint no lo lee: lo detecta y bloquea**
(`python scripts/make_notes.py --migrate-disputes`).

### papers/

Campos: `bibcode, title, first_author, n_authors, year, arxiv_id, doi, bibstem, stars[], facets[],
keywords[], methods[], thesis_links[], role[], relevance, citation_count, pdf, fulltext,
fulltext_source(pdftotext|ocr|web), pdf_source(eprint|ads|publisher|web), pdf_sha, vistas[], versions[],
bibtex, bibtex_source(ads|crossref|datacite|doi|arxiv|venue|institucional), bibtex_url, bibtex_accessed`.

⛔ **El `bibtex` se TRAE de una exportación oficial, nunca se redacta (#397).** Lo baja
`fetch_bibtex.py` (cierra la cadena) por la cascada **ADS → `doi.org` → arXiv**; un libro o manual
sin exportación deja el campo **VACÍO** — un hueco es correcto, una cita inventada no. ⛔ **`venue` es
la exportación del SITIO del venue (JMLR, NeurIPS, PMLR) (#484): la pega una persona, así que exige
`bibtex_url`** y no se re-baja. El lint **bloquea** el `bibtex` sin `bibtex_source` y reporta el
drift frontmatter ↔ exportación.
⛔ **Y el HUECO se declara: `sin_bibtex: <motivo>` + `bibtex_accessed` del intento (#467)**; lo estampa
`fetch_bibtex` y **lo borra** al cerrarse. ⚠ Antes de declararlo pregunta si el DOI existe, en **dos
etapas** (#466), y a **HAL**, que propone el bloque y no lo escribe (#505).
⛔ **Y se pide en la forma en que se PEGA: un bloque que NO SE PEGA no está cerrado (#471/#473).** ADS
se pide con `journalformat: 3` (sin macros AASTeX). ⛔ **NO se post-procesa** (sería redactar la
cita), y **cada forma de no pegarse declara su consecuencia** (`cfg.BIBTEX_NO_PEGABLE`, #473):
`pendiente` se re-baja · **`descartable` NO se guarda** y la cascada sigue (el cascarón sin
`author`/`editor`/`title` imprime una cita **VACÍA**) · `residuo` se **nombra** y no se re-baja. ⚠ La
**clave de cita repetida** entre dos notas se **nombra y no se toca** (backlog): `bibtex` saltea la
segunda **en silencio**.

⛔ **Toda nota de paper pertenece a alguna ENTIDAD (D-23).** Al menos uno de `stars`,
`thesis_links` o `methods` poblado; sin ninguno la extracción pagada queda invisible para todo
roll-up. Es **bloqueante** (INV-94) y la salida es poblar el campo, no borrar la nota. ⚠ Cuando
`entity.py delete` deja un paper sin destino **avisa y no borra**.

#### La extracción es una lectura CON LENTE, y la nota declara cuál se hizo: `vistas[]` (#188)

El fan-out pregunta *«¿qué dice **sobre {sujeto}**?»* y la nota es **una por bibcode**: sin scope,
**el silencio de la nota sobre un eje es indistinguible de «se miró y no hay nada»**. Cada entrada de
`vistas[]`: `sujeto` (el mismo nombre que `stars[]`/`thesis_links[]`), `tipo` (vocabulario
**cerrado** `star | theme`, declarado), `fecha`, `txt` (de qué copia del `.txt` salió), `lente` (las
facetas vigentes al leer) y `fuente`. La sección del cuerpo es `## Vista — <sujeto>` y **no** es
estampada: es lo que `verify-citations` contrasta. El lint **bloquea** la incoherencia en los dos
sentidos (vista sin sección; sección sin declarar) y el schema viejo (`## Extracción (LLM)` sin
`vistas[]`). **Forma dura como `extra_core`** (D-58): el escalar y la lista de strings bloquean.

⛔ **`txt` se cruza contra el DISCO al estamparse (#230):** si el `.txt` vive bajo otro slug se apunta
ahí; si no existe **la clave no se escribe** (*no consta*, nunca un puntero falso).

⛔ **`fuente` dice DE QUÉ se construyó: `pdf` | `abstract` (#207).** Lo **declara el extractor** y
el **cosechador lo cruza contra el disco**: `fuente: pdf` sin PDF **rechaza la extracción entera**.
Ausente = *no consta*, backlog; `fuente: abstract` también, y ahí el pedido es **conseguir el PDF**.

⛔ **La `fecha` es lo que dice que la lectura OCURRIÓ.** El stub nace con la vista **sin** fecha
(backlog). La estampa el **cosechador** (`harvest_views.py <slug> [--theme]`), que además mergea
`methods`/`thesis_links`/`role` add-only, escribe la sección mientras siga siendo la plantilla del
stub —prosa redactada no se pisa sin `--force`— y **trae el `.txt` al slug del sujeto** (D-18).

⛔ **Las `salvedades` sobre el ARTEFACTO se chequean con un script, o se publican marcadas NO
VERIFICADAS (#213)** — no llevan `[[bibcode]]`, así que `verify-citations` no las mira:

- La **decidible sobre un archivo** se emite **estructurada**, con vocabulario cerrado
  (`lib_config.SALVEDAD_TIPOS`: `txt_pierde` + `cadena`, `pdf_paginas` + `n`, **`pdf_leido` +
  `documento`** —#452, con `bibcode` opcional si habla del PDF de OTRA fuente— y **`nota_estado` +
  `literal` + `presente`**, la que predica sobre LA NOTA —#497—), y la chequea el **cosechador** con
  `grep` o `pdfinfo`. La **falsa NO se publica** (se grita con su archivo; ⚠ la extracción no se
  tira). El chequeo que **no pudo correr** sale **no evaluable con su motivo** (D-43).
- Todo lo demás va en su **propio bloque**, marcado *«⚠ NO VERIFICADAS — juicio del extractor»*.

⛔ **`pdf_leido` son DOS EJES (#456): `documento` = qué hay en disco (lo verifican los tres
testigos) y `leido` = de qué se construyó la VISTA** (opcional; su testigo es la firma
`pdf_reemplazo`, #441). En un PDF **reemplazado** divergen: la vista es anterior al reemplazo y sus
localizadores son del documento viejo (como marca `_paginacion`, #436).

⛔ **Y la que dice QUÉ DOCUMENTO hay en disco se cruza contra el disco (#449):** marca de arXiv del
`.txt`, firma `pdf_reemplazo` y `pdf_source` son tres testigos. Lo levanta el lint (backlog: cuál
mitad está mal lo decide quien lee) y `replace_pdf` **avisa al firmar** cuántas líneas quedaron
diciendo preprint; avisa y **no reescribe**. ⛔ **El ancla es el DOCUMENTO, no la palabra** (frases
que predican sobre el archivo; frontmatter, `SECCIONES_ESTAMPADAS` (#214) y bloques que nombran otro
`[[bibcode]]` quedan afuera; unidad = **bloque**, #224). ⛔ **La salida es emitirla ESTRUCTURADA
(`pdf_leido`, #452)**; la categoría del lint queda como **residuo**. Propuesta lista para pegar:
`harvest_views.py <slug> --propose-pdf-leido` — **propone y no escribe** (#311), entre `publisher` y
`ads` **no elige** (#296), decide por la **cláusula** que el ancla matcheó, con negación simétrica,
`web` como clase, y **cruza el disco** y saltea la nota sin PDF antes de proponer.
⛔ **Cobrarla NO re-cosecha la vista:
`harvest_views.py <slug> --restamp-salvedades [--paper <bib>] [--dry-run]` (#453)** — `--force`
**re-fecha la lectura** (#395). No toca `vistas[]` ni la prosa; rehúsa el bloque con prosa ajena. ⚠ La
salvedad estructurada lleva **`evidencia`** (lo que el lector vio; el JSON es su registro, #311).
⛔ **Y CRUZA EL DISCO antes de escribir** (el JSON puede ser más viejo que la nota): rehúsa la nota
nombrándola, avisa la chequeada que dejó de serlo y **migra** el bloque pre-#213. ⛔ **Regla
ESTRUCTURAL y SIMÉTRICA: una salvedad en prosa ya escrita NO SE PIERDE** —agregar pasa; reescribirla
y **borrarla** se rehúsan; borrar una `⚙ verificada` pasa avisando; el bullet que se **estructuró**
no es un borrado (su texto sigue en `evidencia`).

⛔ **La lectura puede RETRACTAR el reclamo que la trajo: `refuta: [<sujeto>]` (#212)** —único canal
en esa dirección (típico: **polisemia**)—. ⛔ El cosechador **registra y propone, no aplica**: deja
el `refuta` en la vista e imprime el `--drop-core` con su motivo (la decisión es del **par (paper,
sujeto)**). El lint lo reporta como **backlog**; el add-only **no se afloja**.

⛔ **Una SEGUNDA lectura del mismo sujeto con otra lente CONVIVE: `enfasis` (#239), y se PIDE con
`extraction_prompt.py … --enfasis "<lente>" [--ejes a,b]` (#308)** —el prompt manda leer la vista
anterior y **rehúsa** si `(sujeto, enfasis)` ya tiene lectura—. Identidad = `(sujeto, enfasis)`;
sección `### Lente — <énfasis>` **dentro** de la `## Vista` del sujeto (AUD-178). El cosechador
**rehúsa** cambiar un valor ya escrito bajo la misma clave. ⛔ **Su extracción va a
`<bibcode>__<lente>.json` (#371)**: al canónico pisaba un artefacto no regenerable (#311).

⛔ **La sección de una vista SIN LEER es una LÍNEA DE ESTADO, no un prompt (#398):** *«reclamado, sin
leer»* o *«no leído desde X (fecha): motivo»*. Backfill: `make_notes.py --restamp-vista-stub`.

⛔ **`vistas[]` la escribe SÓLO la lectura, nunca el retro-link.** `stars`/`thesis_links`/`methods`
son **reclamos** (add-only sin leer); `vistas[]`, **lecturas**. Un reclamo sin vista es backlog y se
cierra haciendo la vista o declarándola `no_vista: [{sujeto, motivo}]` —vale en **las cuatro** redes
que cuentan la nota (#268), estado `sin vista (declarado)`—. **Motivo obligatorio y por sujeto**.
Cuenta como reclamo: `stars` y `thesis_links` siempre; `methods` **sólo si es un tema declarado**.

⛔ **Sacar `pending_source` no puede romper el frontmatter (#244):** el borrado de una clave es **una
sola función** (un `startswith` deja huérfanas las líneas de continuación); se re-parsea y **no se
escribe** si dejó de parsear (#222).

#### Identidad: el `doi`/`arxiv_id`, no el bibcode (D-19)

El preprint y el publicado son bibcodes distintos del **mismo** paper: dos notas ahí son doble
conteo, dos fuentes donde hay una, y un falso positivo permanente de #75. Hay **una sola nota
canónica** y los bibcodes viejos viven en `versions[]`; el lint bloquea el duplicado y `make_notes`
**rehúsa crear** la segunda nota.

⛔ **Un bibcode listado en `versions[]` que TIENE su propia nota BLOQUEA (#229):** o es un alias (y
**no debe haber nota**) o es otro trabajo (y **no va en `versions[]`**); *«mismo programa,
resultados distintos»* se declara en **prosa o en `salvedades`**. ⚠ **El alias de `versions[]` NO
se vuelve a bajar** (D-19): lo filtran los dos fetchers, junto con los descartes de curación.

El ciclo se resuelve con `python scripts/make_notes.py --rename-paper VIEJO NUEVO`: mueve la nota y
sus artefactos (`raw/pdfs/`, `raw/fulltext/` **y la extracción** — #228/#374: la identidad de una
extracción es el `bibcode` **de adentro**), **re-estampa la cabecera y re-apunta `pdf:`/`fulltext:`
por verdad de disco (#356)**, deja `bibstem` en `null`, agrega el alias —con `--fix-key` no: la clave
vieja era ERRÓNEA y el rastro va al `log` (#355)— y **reescribe los wikilinks de toda la bóveda**.
Alcance declarado: `vault/`.

⛔ **El duplicado SIN `doi` ni `arxiv_id` lo reporta otra categoría (#216, backlog)**, por el
**arranque del `## Abstract` verbatim** normalizado. ⛔ **NO se deduplica por título**, y **reporta,
no fusiona**. La salida es `--rename-paper` + `versions[]`, o `--drop-core`.

#### `data_availability` — dónde están los DATOS del paper (#424)

⛔ **El puntero público a los datos que publicó un paper vive en SU nota**, como
`data_availability: [{doi|url, que, localizador}]`, y la ficha lo agrega en la sección estampada
`## Datos públicos`. Es un hecho **que el paper afirma**, citable con página y verificable; el lint
reporta como backlog la entrada incompleta. ⚠ Es lo **contrario** de `data_local` (ruta
machine-local, no viaja). ⛔ La bóveda **no baja ni guarda** los datos (regla #0): entra el puntero
citado.

#### Los dos artefactos y sus dos `*_source`

`pdf` es **lo que se lee** (extracción y verificación) y `fulltext` el **índice de búsqueda** del
corpus (`grep`) (#205). Los estampan por **verdad de disco** —`fulltext` `extract_fulltext`
(`stamp_fulltext`), `pdf` su gemelo `stamp_pdf` desde `fetch_pdf` y `--restamp-pdf-links` (#304)—,
con `null` si no hay archivo.

⛔ **Los dos `*_source` NO se comportan igual cuando el archivo desaparece (#230).**
`fulltext_source` se limpia con el archivo (backlog el par `fulltext: null` + valor). **`pdf_source`
sobrevive**: es la **procedencia de la lectura que ocurrió**; el par `pdf: null` + `pdf_source`
**no es hallazgo**. ⛔ **El REEMPLAZO del PDF sí (#383):** `stamp_pdf` guarda `pdf_sha`, y si el
archivo cambió deja `pdf_source`/`eprint_version` en `null`; editor + `eprint_version` bloquea.
⛔ **Lo que `replace_pdf` FIRMA no lo revierte `build/` (#446):** precedencia de `pdf_source` = marca
de arXiv → **`pdf_reemplazo`** (si su `pdf_sha` es el del disco) → `sources:` → `build/`. Y
`extract_fulltext --bibcode` re-estampa **sólo** las notas cuyo `.txt` tocó.

Cuando un paper vive bajo **varios slugs** el campo es **estable**: se mantiene salvo que llegue una
copia de **mejor calidad** (`pdftotext`/`web` > `ocr`); un puntero que **ya no resuelve** sí se
repunta (#217/#304).

⛔ **Los dos son vocabulario CERRADO y el lint los BLOQUEA (#296)** —`pdf_source: eprint|ads|
publisher|web`, `fulltext_source: pdftotext|ocr|web`, con `null`/ausente = **desconocido**—: el
campo **decide lecturas** y un valor fuera de vocabulario cae por el `else` en silencio. ⚠ Ese `else`
**ya no exime** del chequeo de cita textual (#275/#363). Migrador:
`python scripts/make_notes.py --migrate-source-fields` (pasa el valor a `null` y **mueve** la prosa
a `pending_motivo` o `salvedades`).

**`fulltext_source` vs `pdf_source` (#57):** el primero dice **cómo se extrajo** el texto, el segundo
**de qué documento salió** — `eprint` (arXiv: puede ser un **v1 pre-referato**, con `eprint_version`
cuando se conoce), `ads` (escaneo alojado por ADS), `publisher`, `web` (snapshot), o `null` =
**desconocido** (que **no** es "publicado"). Manda la verdad de disco: la marca de arXiv es visible
en el `.txt` y se detecta re-corriendo `extract_fulltext` sin re-bajar (misma re-corrida = backfill
de la marca de garble). Con `eprint`, una discrepancia numérica contra un valor publicado es
candidata a **diferencia de versión** y NO se "corrige" la nota hacia el preprint.

⚠ **`symbols_lost` y `fulltext_layout` se RETIRARON (#205, #193, #194):** migrador
`--migrate-txt-fields`; el lint **bloquea** la nota que los lleve. **`Read` rasteriza el PDF, así que
el modelo *ve* la fórmula**.

#### `keywords` (D-17)

Son las del catálogo (ADS ya las devuelve). La lente matchea sobre **título + abstract + keywords**,
así que sin ellas re-clasificar desde la nota daría un diff inventado; son lo que hace posible el
**diff de lente offline** (D-49) sin `build/`. Backfill: `make_notes.py --restamp-keywords`.

#### `role` — qué TIPO de aporte es el paper (#73)

`fundacional` (introduce el método, mecanismo o formalismo — la fuente de la ecuación), `aplicacion`
(lo instancia en un caso: una estrella, un dataset) o `arbitro` (reanaliza y **resuelve** —o
reabre— una tensión previa sobre el mismo hecho). Uno o varios; lo puebla la **extracción**, no la
selección (`classify()` clasifica **tema**, no rol). Es distinto de la **postura** respecto de una
tesis, que vive en la tabla de evidencia de la hipótesis (D-21).

`role` define qué es *contrastar dos papers*: fundacional↔fundacional compara supuestos;
aplicación↔aplicación pregunta si replica y **en qué régimen**; **fundacional↔aplicación NO es
contraste, es instanciación** (tratarlo como desacuerdo **fabrica disputas falsas**); el `arbitro`
resuelve, no promedia. Vocabulario **cerrado** y bloqueante.

#### Escotillas y metadata de estado

- `no_sintetizado: <motivo>` (#75): declara que este paper **ya extraído** legítimamente no se
  inlinea en ninguna ficha ni concepto —típicamente por la **regla de poda**—. Motivo
  **obligatorio** (mismo criterio que el `--reason` del triage: no curar en silencio); sin ella, el
  lint lo reporta como *extraído pero no sintetizado*.
- `retracted: true` + `retraction{type,notice_doi,date,source}`: lo estampa
  `scripts/check_retractions.py` (Crossref) y el lint lo surface como **bloqueante** (fuente no
  válida).
- `corrections: [{type,notice_doi,date,source}]` (#52): la corrección **no retractante** (`erratum` /
  `corrigendum` / `expression-of-concern`). **No** invalida el paper —sigue citable, por eso es
  **backlog**— pero es la señal que más directamente **envejece un número ya extraído**: al verla,
  revisar las afirmaciones que citan ese `[[bibcode]]`, no la existencia del paper.

#### El aviso de capa LLM y las cuatro secciones de lectura (#124, #247)

⛔ **La nota de paper lleva el AVISO DE CAPA LLM (#247)**, que nombra las tres capas: lo
**auditable** (`## Abstract` verbatim + frontmatter de catálogo), la **traducción** (ayuda de
lectura, **nunca fuente de la que citar**) y la **síntesis lenteada** (la vista). Backfill:
`--restamp-headers`.

⛔ **`## Abstract` va en TODA nota de paper, verbatim (#124)** —capa auditable; `classify_offline` la
lee (D-49)—. Una vista construida desde ahí se declara `fuente: abstract` (#207). ⛔ **Se llena desde
el CATÁLOGO, no sólo desde el PDF (#413):** `make_notes.py --fill-abstracts` (OpenAlex por `doi`),
único camino para un `pending_source`. ⛔ Reemplaza **el placeholder, nunca el encabezado** (#417), y
respeta **`sin_abstract_motivo`** (un capítulo sin abstract). La sección la escriben los dos raíles
al crear —`_(no disponible)_` si no hay copia— y el cosechador la completa sin pisar un verbatim
(#124/#277). Backfill: `make_notes.py --restamp-abstracts`; el lint la **bloquea**.

⛔ **Y la nota lleva tres AYUDAS DE LECTURA (#124): `## Traducción del abstract`, `## Conclusiones` y
`## Traducción de las conclusiones`** —las conclusiones son lo que el paper afirma **sin lente**, lo
que abarata una segunda vista—. Las estampa el cosechador desde el JSON, van **antes** de la vista, y
**la traducción va al lado del original, nunca en su lugar**. ⚠ Se llaman `## Traducción …` con el
nombre COMPLETO, nunca `## Abstract (es)` (trampa de prefijo de `section_start`, #176).

⚠ **Documento largo (`unidad_cita: pagina`): sin conclusiones** — igual que la fuente leída sólo del
abstract (#207); la que no tiene esa sección se declara `sin_conclusiones: <motivo>` (#277).
Exclusión **estructural**, no umbral de largo.

⚠ **Las conclusiones se leen primero**: el extractor saca los **ejes** que el trabajo dice aportar y
los **chequea contra el cuerpo**; si el cuerpo dice menos, es un hallazgo sobre la **fuente** y va a
`salvedades`.

⛔ Las cuatro secciones están en `SECCIONES_ESTAMPADAS`, así que `verify-citations` **no las mira**:
lo que de acá llegue a una **ficha** sí se verifica contra el PDF — **son ayuda de lectura, nunca
fuente de la que citar.**

#### Notas off-ADS y fuentes largas

⛔ **El item de `sources:` —y el de `extra_core` (#479)— declara `pdf_source` (#415)**: sin fetcher
ni marca de arXiv el campo quedaba `null` para siempre. Precedencia: marca de arXiv → **lo
declarado** → `build/`. Vocabulario cerrado (#296): el valor fuera de lista se avisa y **no se
escribe**; el lint lista el `null` por carril.

En notas **off-ADS** el schema suma `source_url` (URL de la fuente web; `null` si es PDF local),
`accessed` (la cita "Retrieved <fecha>") y, si la fuente no se pudo conseguir, `pending_source:
paywall|scan|unextractable|adquisicion` (el lint la lista como precondición).

⛔ **`pending` es vocabulario CERRADO y lleva `pending_motivo` obligatorio (#80).** `adquisicion` es
lo que el usuario va a conseguir (no falló, tiene otra latencia); los otros tres, por qué falló. Un
typo aborta la cadena y el lint lo nombra.

⛔ **Una fuente LARGA declara cómo se la cita y qué parte entró (#80):** `unidad_cita:
linea|pagina|seccion` (default `linea`) y **`alcance`** (qué entró; obligatorio si la unidad no es
la línea), **en `sources:` o en `extra_core` (#382)** — sin `alcance`, el chequeo de completitud no
distingue un recorte deliberado de una omisión. Eje distinto del `txt:`/`pdf:` de #117.
⛔ **Se RE-SINCRONIZAN: la autoridad es la config (#312):** `make_notes.py --restamp-alcance`; el lint
reporta el desfasaje. ⛔ **Y LLEGAN AL EXTRACTOR (#241):** `extraction_prompt` ramifica por
`unidad_cita` (índice primero, `alcance` pegado textual sin ampliarlo —lo de afuera se declara en
`salvedades`—, `conclusiones` vacío, cita **por página**; sin `alcance` dice *«NO DECLARADO»*).

### concepts/

Las áreas son **abiertas** — cualquiera según el foco de la bóveda; `concept_areas` en
`vault/config/objective.yaml` es sólo referencia para el typo-check, con `methods`/`hypotheses`
reservadas. Ésas son las dos que el framework distingue de verdad; cualquier otra que declares es
**archivado**: ningún chequeo se ramifica por el área (#246).

Campos: `name`, **`aliases`** (sinónimos EN+ES — p. ej. `[chromatic index, índice cromático,
RV-color]` — para que la ficha se encuentre por `grep` desde **cualquier término**, no sólo el
canónico; espeja `aliases` de `stars/`), **`disputes[]`** (mismo schema de posiciones explícitas que
en `stars/`, #71 — acá la disputa es simétrica por definición), `tags`, `confidence`. El cuerpo trae
`## Síntesis`, `## Inventario por eje`, **`## Régimen de validez`**, `## Huecos` y el apéndice
`## Excluidos por el filtro`.

**Régimen de validez (#74) — sólo en conceptos.** En un método, dos papers pueden decir cosas
distintas y **estar los dos bien**, porque valen bajo condiciones distintas (SNR, muestreo, tamaño de
muestra, definición del observable); el modo de falla dominante es **generalizar de más** (el paper
afirma X bajo C y el concepto afirma X pelado). La unidad de síntesis es **`(afirmación, condiciones
bajo las que vale, fuente, rol)`**, y ésa es la tabla. Es el destino de los veredictos **`aparente`**
de `find-contradictions` (acá **son el hallazgo**); el `## Inventario por eje` queda para el
desacuerdo **real bajo las mismas condiciones**. De la tabla sale el hueco **"régimen no cubierto"**.

**Convención hub/radios (tema grande → varias notas).** Cuando un tema no cabe en una sola nota sin
perder foco, se estructura como **hub** (la síntesis del tema completo) + **radios** (notas satélite
del mismo área que profundizan un sub-aspecto; p. ej. hub `procesos-gaussianos`, radio `gp-kernels`).
El hub referencia cada radio explícitamente y el radio abre con su "Para qué" apuntando de vuelta al
hub. Un radio es una nota de concepto normal (mismo frontmatter y estándar de autosuficiencia);
"hub/radio" es sólo la metáfora organizativa.

⛔ **El ALCANCE de un tema es su `query` + su `facet` (#127):** se parte en radio cuando cada parte
necesita **su propia query y su propia faceta** (terminología que no se solapa). Un radio es un
**tema propio** (slug, query, faceta, registro y corpus propios) cuya nota apunta al hub. Ejemplo:
*noisy ICA* es radio (su vocabulario no lo trae una query de «independent component»); *PCA* queda en
el hub y *PCA heterocedástico* va al radio — se parte **por régimen**.

⛔ **El hub nombra cada radio con `[[wikilink]]`, no con el slug entre backticks** (sin link no hay
grafo ni link entrante). El lint lo reporta como backlog.

### concepts/hypotheses/

Campos: `name`, `status` (**vocabulario CERRADO**, D-37 — `abierta | sostenida | disputada |
refutada`: el lint bloquea lo que no esté en la lista; se **deriva de la tabla de evidencia**, y si
hay filas `desafía` con `status: sostenida` el lint lo marca).

El cuerpo lleva **tres cosas propias**:

1. **El blockquote de alcance** (D-34) — `> Alcance <fecha> · temas: […] + estrellas: […] · N
   papers · M con hits`. **Define qué significa el veredicto**: *"no hay evidencia"* es *"no hay
   evidencia en estos temas, con estos N papers, a esta fecha"*; sin él, un veredicto negativo se lee
   como **universal**. Los slugs son directorios de `raw/fulltext/`: el lint re-cuenta y marca la
   hipótesis si quedó corta.
2. **La tabla de evidencia** (D-21) — una fila por paper: `Paper | Postura | Qué dice (cita textual)
   | L | Régimen`. Acá vive la **postura** (`apoya`/`desafía`/`método`), **no** en la nota del paper
   (depende de la tesis, y en la tabla es verificable). ⛔ `bearing` en una nota de paper es schema
   viejo y **el lint lo bloquea** (`make_notes.py --migrate-bearing`).
3. **El veredicto global marcado `inferencia`** (D-36), con sus premisas: agregar N filas en una
   conclusión es juicio del agente, no algo que una fuente diga.

Una hipótesis **no es un radio** (D-35): cruza varias entidades, así que se linkea con
`[[wikilink]]` en los dos sentidos, sin la relación padre-hijo de un hub. El roll-up mecánico de qué
papers la tocan sigue saliendo de `thesis_links`.

### Estándar transversal de autosuficiencia

El estándar de `stars/` rige **igual** para `concepts/` y para las `queries/` que se archiven: la
nota debe **alcanzar por sí sola**, ser **dual-audiencia (humano y modelo)** y llevar `[[bibcode]]`
en cada afirmación para **citar y trazar**. Requisitos extra por tipo:

- **métodos e indicadores** (`concepts/methods`; un indicador —BIS, S-index, FWHM— es un método
  chico, #246): además **implementation-ready** — ecuaciones, inputs/outputs y pasos suficientes para
  **codificar el método tal como lo detallan los papers, sin abrir la fuente**; el detalle fino vive
  en los `[[links]]`. Y **con el régimen explícito** (#74): una ecuación sin las condiciones bajo las
  que vale es implementable y **equivocada**.
- **queries/hypotheses**: pregunta, **búsqueda reproducible** (el `grep` usado), evidencia citada
  for/against con su **postura declarada en la tabla de evidencia de la hipótesis** (D-21), y
  veredicto.

Si para implementar o citar algo hace falta abrir el paper, eso que falta **debe agregarse a la
nota**.

### Convenciones

Filenames kebab-case (los papers usan el bibcode); links internos `[[wikilink]]` por nombre de nota
(sobreviven a mover carpetas); reportar agregados declarando mean vs median. **Notación matemática
según destino:** en `vault/wiki/` SIEMPRE `$...$` (Obsidian lo renderiza); en **consola o chat**,
**texto plano** (`P_rot`, `m·sini`, `K=2.5 m/s`) — la terminal no renderiza LaTeX.

## Operaciones

### Setup (definir el objetivo — paso 0, skill `setup`)
Genera/afina `vault/config/objective.yaml` (la **lente**: `name`/`description` + `relevance.facets`,
el clasificador de papers core). El agente traduce el foco del usuario a la regex —el usuario **no**
escribe regex— y la valida contra papers reales con `python scripts/query_ads.py --probe "<query>"`
(muestra el corte core/no-core sin bajar nada) iterando hasta que cierre. ⛔ **La lente del BUSCADOR
también sale del objetivo (#85): `relevance.search_fq`** — el `fq` de Solr que acota el universo
**server-side, antes de traer nada** (la mitad **más restrictiva** del filtro). Tres estados: sin
declarar → `database:astronomy`; con valor → ése; **`search_fq: null`** → no acota, a propósito.
`relevance.facets` son **facetas** (clasifican los papers de estrella, y los de tema **salvo que el
tema declare su lente propia**), **no** sujetos (las estrellas/temas van en `stars.yaml`/`themes.yaml`).
La **regla de combinación** es declarativa: por default OR (≥1 faceta), o `relevance.require:
[<faceta>, …]` (AND) y/o `relevance.min_facets: N` — `core = (≥min_facets) Y (todas las de require) Y
(doctype no-ruido)`. Cambiar la regla **re-clasifica** el corpus → sub-modo re-clasificar de
`maintain`. No ingesta nada; después se usan `ingest-star`/`ingest-theme`.

### Relevancia de un TEMA DE MÉTODO — la lente propia y las tres puertas (D-26 / INV-88)

Para un tema de método (estadística, ML, signal processing) la lente global **no sirve, y es
activamente dañina** (mata al fundacional, que no menciona astro; sin filtro trae fMRI y finanzas).
Por eso la entrada del tema en `themes.yaml` lleva su **`facet:` propia** (regex) y la regla pasa a
ser `core = facet propia Y (puerta 2 OR puerta 3)`:

| Puerta | Criterio | Dónde vive |
|---|---|---|
| **2 · fundacional en su campo** | `citation_count >= fundacional_min_citas` | `query_ads.classify_theme` |
| **3 · lente astro global** | pasa `relevance.facets` de `objective.yaml` | ídem |

⛔ **Los EJES DE LECTURA también son del tema (#307): `ejes:` en `themes.yaml`.** Mismos tres estados;
sin declararlos el probe y el lint avisan (#360); la `lente` de la vista guarda **los ejes que se
preguntaron** (D-49).
⛔ **El `search_fq` también es del tema (#295)** —es la mitad más restrictiva y ninguna `facet:`
recupera lo que el `fq` excluyó—, con los **mismos tres estados** (sin declarar → hereda el objetivo ·
con valor → ése · `null` → no acota). El registro guarda el **resuelto** y entra en la lente.
⛔ **El tema de método que NO lo declara recibe un AVISO (#351)** —probe y backlog del lint—: con
`database:astronomy` heredado la puerta fundacional **no abre nunca**. Sólo aviso: un `null`
**declarado** lo calla.
⛔ **La re-clasificación del tema va sobre el corpus COMPLETO, no sólo sobre la query directa
(#455)** —la segunda pasada por fecha (#79) y el chaining clasifican con la lente global—: corre
después de todo lo que suma registros y **antes** de la exclusión declarada (#112); **`relevant:
True` con `puertas: []` es un estado IMPOSIBLE** para un tema con faceta propia y se reporta.
⛔ **El PREVIEW de un tema se corre con esa lente (#208):**
`python scripts/query_ads.py <slug> --theme --probe` —con la global el veredicto es el opuesto—.
Cada fila lleva **por qué puerta entró**; con un slug inexistente o sin `facet:`, **rehúsa**.
⛔ **El probe dice POR QUÉ quedó afuera cada no-core (#289):** *sin la faceta propia* (apretala) vs
*pasa la faceta y muere en la puerta* (`extra_core` o `fundacional_min_citas`); el segundo bloque es
de donde sale `extra_core`.
⛔ **El DELTA de re-clasificación de un tema también (#447):** `query_ads.py <slug> --theme
--dry-run` y la *Lente desincronizada* del lint aplican la regla del tema (`cfg.theme_core`) y
eximen la curación **por bibcode**.
⛔ **Para una ESTRELLA la query también se DERIVA (#248): `python scripts/query_ads.py <slug>
--probe`** — la tipeada a mano no expande variantes de espaciado ni alias, y el universo
previsualizado no es el ingestado.

⛔ **Queda registrado POR CUÁL puerta entró cada paper (#126): `puertas: [fundacional|astro|manual]`
en el registro** —lo único que distingue **sin leer** un fundamento de una aplicación astro—. Con eso
`triage.py <slug> --prioridad` agrupa los core por política y el recorte de lectura se decide **una
vez** (`--extraccion subconjunto --reason`). Lista vacía = no es core; el campo existe siempre.
⛔ **`manual` es la procedencia de la CURACIÓN y la escriben las dos ramas del merge de `extra_core`
(#303)**; el `via` del registro es siempre el **declarado** en la config.

⚠ **`fundacional_min_citas` no tiene default** (depende del campo): sin declararlo la puerta 2 **no
abre** y el motivo va a `why_excluded`. ⛔ **Compara contra el contador de ADS (#357)**, que en otra
disciplina mide cuánto lo cita astro; el probe muestra el rango y avisa. *(Abierta en
`docs/decisiones-abiertas.md`.)*

⛔ **La puerta 1 («lo cita tu corpus») PROPONE, no clasifica**: alimenta los candidatos del triage
con `via: citado-por-corpus`, nunca marca core (INV-24). La sostiene `scripts/citation_index.py`
(índice invertido obra→citadores, lookup **offline**, vive en `build/`), que se construye aparte. Los
backends fuera de ADS son `scripts/search_arxiv.py` (⚠ `ingest_theme.py` no lo corre solo: lo alcanza
`discover.cascade`, paso manual del skill —`discover.py --theme <slug>`—, #144) y
`scripts/openalex.py` (lo usa `citation_index`); los tres normalizan al **mismo schema de registro**
que `query_ads.to_record`, fijado por `tests/test_backends_schema.py`.

### Descubrimiento multi-backend y anclado (`scripts/discover.py`, #104)

**Un tema de método no se descubre con un solo buscador** (medido: el canon de ICA/BSS está en ADS
0/8, arXiv 0/8, OpenAlex 8/8). `discover.py` corre la cascada y **propone**; nunca clasifica.

- **La cascada** (`cascade`, CLI `discover.py --theme <slug>`) corre **los tres** y mergea; cada
  backend recibe la query **en su idioma**: ADS el Solr de `query:`, arXiv los términos de
  `aliases:`, OpenAlex el `topic:`. ⛔ **Declará `topic:` en `themes.yaml`** (inferido del `title`
  en castellano no matchea la taxonomía inglesa). ⛔ **`topic:` acepta una LISTA (#293)**, buscada en
  OR (`topics.id:T1|T2`). ⚠ `ingest_theme.py` no corre la cascada solo: es el paso 0b del skill.
- **La cobertura distingue tres estados** (`print_cobertura`): corrió con N, **FALLÓ** y **NO
  CORRIÓ** con motivo. ⛔ **El anclaje también, con fila `anclaje` en el registro; y el lint reporta
  el tema off-ADS/mixto cuya cascada nunca corrió, corrió vacía o con backends caídos (#361).** Citas
  que el backend no publica se muestran **`?`, no `0`**. ⛔ **`--topics` declara sus dos ceros
  (#290)**: «la taxonomía no tiene nada parecido» vs **FALLÓ**.
- **Dedup por DOI, nunca por título** (`ident`/`dedup`); lo que no tiene DOI ni arXiv id se devuelve
  **aparte, como no-deduplicable**. Cada registro acumula `found_in`: la procedencia **enruta**, la
  lente **decide**.
- **Rankear sin filtro estructural amplifica, no filtra**: `topics` antes de `seed`.
- **Descubrimiento ANCLADO** (`anchored_records`) — el de más apalancamiento: las **referencias de
  la mitad astro del propio tema**, rankeadas por cuántos papers las citan (la puerta 1 para un tema
  **nuevo**).
- **La cola especialista se alcanza con `seed_terms`** (slice de texto por término dentro del topic,
  #107): canje cobertura ↔ costo de triage, **opt-in** por tema; avisa por término. ⛔ **El aviso manda
  subir una perilla que EXISTE y el slice se PAGINA (#294):** `rows_por_termino` (campo del tema y
  flag `--rows-por-termino`). ⛔ **El filtro por topic se decide POR TÉRMINO, con el conteo, y se
  declara (#293).** Capítulos, actas y papers sin los términos del tema van por curación a mano,
  registrando **por qué** (`extra_core` con `via`/`motivo`, o `sources`).
- **Encontrar ≠ conseguir** (`resolve_pdf`): la cascada del archivo es **OpenAlex → Unpaywall →
  Europe PMC → HAL → arXiv por título EXACTO** (#313/#358/#505) y **propone una URL y para** (no reescribe un
  `pending:` ni edita `sources:`). ⛔ **El carril ADS de `fetch_pdf` la recorre ENTERA al agotar los
  `esource` (#358)** y el residuo distingue «sin copia libre» de «bloqueada» (`estado`). ⛔ Nunca por
  título **aproximado**; el motivo enumera **lo consultado**.

### Ingest (una fuente → cascada de páginas)

**El camino del texto, de punta a punta** — el mapa canónico de cómo un PDF se vuelve una cita
verificable:

```
1. fetch_pdf          →  raw/pdfs/<slug>/<bib>.pdf     (inmutable, y es LO QUE SE LEE)

2. extract_fulltext   →  pdftotext; si no pasa `is_legible`, OCR con tesseract.
                         Escribe raw/fulltext/<slug>/<bib>.txt — el ÍNDICE DE BÚSQUEDA
                         del corpus, no material de lectura. Una sola vez.

3. make_notes         →  stub de la nota + frontmatter mecánico + `## Abstract` (de ADS).

4. extractor (LLM)    →  lee EL PDF (`Read` lo rasteriza: ve ecuaciones, tablas y
                         figuras) y cita PÁGINA. El `.txt` sólo para ubicar con grep.
                         ⚠ Sin PDF en disco (bajo CUALQUIER slug, #305) el prompt NO manda
                         leerlo (#255): nombra el `## Abstract` y manda `fuente: abstract`.
                         Sus EJES salen de `relevance.facets` de ESTA bóveda (#254).
                         Devuelve UNA VISTA (#188): «qué dice sobre {sujeto}», con
                         `vista{sujeto,tipo,txt,fuente}` en el JSON (#207).

5. harvest_views      →  la única compuerta que corre `is_extraction` (INV-103).
                         Estampa la vista (fecha · txt · lente) y la sección de la nota.
                         ⛔ Y cruza cada cita del JSON contra el `.txt` (#359): avisa.

6. verify-citations   →  un subagente por fuente (`verify_fanout.py`, #369) lee el PDF; DOS hashes
                         por par; el hermano lo escribe `write_verif_sidecar.py` (#403 — `--from`
                         repetible, y el ancla muerta se descarta sólo DECLARADA, #428).
```

⛔ **La fuente es el PDF; el `.txt` es el ÍNDICE (#205).** El `.txt` sirve para el `grep` de
**prosa** sobre el corpus y, en un **documento largo** (#80), para ubicar la página a abrir. ⛔ **El
`.txt` NO se genera con el modelo**: tiene que ser determinista. ⚠ **Consecuencia:** un
`pending_source` es **bloqueo real** — sin PDF no hay de dónde extraer.

⚠ **Excepción nombrada: la fuente WEB.** Un snapshot de `fetch_web` (`source_url` poblado, `pdf:
null`) no tiene PDF **por diseño**: ahí el `.txt` **es la captura** (defuddle, URL + fecha, citada
con `accessed`). Se lee, se cita por **línea**, y su fila de verificación lleva `txt:<sha10>`.

De los chequeos de calidad del `.txt` quedan `is_legible` (dispara el OCR) e `is_garbled` (la prosa
garbleada degrada el índice); `measure_layout` sigue (`CANALETA_MIN` es el contrato para grepear un
`.txt` entrelazado).

⛔ **Esos chequeos miden el TEXTO, así que ninguno ve el dato que vive en una IMAGEN (#195).** El
prompt (`extraction_prompt._media_note`) trata los casos:

- **tabla extraída como texto** → se cita por línea, declarando **cómo se verificó la fila**;
- **tabla-imagen** → el grep vacío **no prueba ausencia**: se abre el PDF y se cita **página**;
- **figura** → **se permite leerla**: el valor viaja con **figura y página** (`Fig. 3, p. 7`), el
  **`≈`** y **lectura de gráfico** en el régimen; si no se deja leer con confianza, **hueco
  declarado**;
- **figura que es un CAMPO** (contornos, mapa de color) → se cita `Fig. N, p. M, contorno del X %`;
  dos lecturas que no reconcilian son figura **subespecificada** (#281).

Por eso la columna de la vista se llama **`Localizador`** y no `Línea`: lleva `L1234`, `p. 271` o
`Fig. 3, p. 7` según de dónde salga el dato (la clave del JSON sigue siendo `linea`).

⛔ **La prosa que va a una CELDA se escapa: `\|` fuera de la matemática, `\vert` adentro (#240); y el
`$` suelto de cualquier prosa que va a una nota, también (`escape_dollars`, #457)** — el span `$…$`
bien formado **no se toca**. Un `|` crudo parte la fila y la vuelve invisible. Lo hace `escape_cell`
en el cosechador, el único punto de escritura.

**Los DOS hashes del paso 6**: el **ancla** hashea el bloque de la **ficha** (se dispara si editás
la nota) y el **hash de fuente**, el archivo **leído** (desde #205, el PDF). Las filas viejas con
`txt:` siguen válidas y se re-verifican al vencer; la fila anclada al PDF no se vence al re-extraer
el `.txt`.

**La cascada, paso a paso:**

1. Los **orquestadores** corren la cadena mecánica completa (idempotente, no pisa — única excepción
   add-only: el retro-linkeo de abajo): `python scripts/ingest_star.py <slug>` para estrellas,
   `python scripts/ingest_theme.py <slug>` para temas. **El orden canónico vive en el header de su
   orquestador** (fuente de verdad única — puntero, no copia).

1b. **Compuerta de triage (estrellas).** El citation chaining amplía el pool con papers que
   mencionan al sujeto sin hablar de él. Sólo entra solo el que lleva el **sujeto en el título**
   (`relevance.chain_autoaccept: titulo`, el default; `never` manda TODO a triage, INV-55); el resto
   queda como **candidato** en `build/<slug>/ads.json` —sin bajarse— y lo juzgás por
   título+abstract (`triage.py <slug>`): aceptado → `extra_core` (mapas
   `{bibcode, via, motivo[, fecha]}`, forma dura D-58; `triage.py` imprime el snippet) + re-correr la
   cadena; descartado → `--drop … --reason` (persiste); **dudoso → al usuario**.

2. **Vos (LLM)** leés el **PDF** y poblás la extracción **de las notas de paper** (`methods`,
   `thesis_links`, `role`, P/K/indicadores). La ficha se escribe **después** del contraste (2b).
   ⚠ **Mirá `pdf_source` antes de copiar un número** (con `eprint`, contradecir al ground-truth es
   candidato a **diferencia de versión**). **Cada valor (#103)** va con su **localizador** (sección,
   figura, tabla o ecuación primero; la página como pista, en la numeración que sea, #500), **el
   régimen** en que la fuente lo afirma y —si la fuente lo atribuye a otro trabajo— la marca
   **segunda mano** con la cita a X. ⛔ **El cruce que la síntesis levanta se acredita NOMBRANDO al
   dueño —o se FIRMA revisado (#433)** en `segunda_mano_revisada: [{ref, que, motivo}]` del
   frontmatter de la ficha o el concepto. ⛔ **Nada de prosa comparativa en la nota de paper**:
   comparar dos papers es `inferencia` y va al `## Inventario por eje` (2b).

2b. **Contraste cross-paper (#72)** ⚠ *(**3b** en `ingest-star`, **3c** en `ingest-theme`)* — **entre
   leer los papers y escribir la síntesis**; el paso con más apalancamiento y el que más fácil se
   saltea. Produce el **`## Inventario por eje`**: una fila por paper para cada **eje** donde los
   papers **no coinciden** (`Eje | Paper | Dice | Método / baseline`). ⛔ **Sin columna "valor
   adoptado" ni "por qué"** (regla #0). El `role` (#73) dice qué operación corresponde entre dos
   filas. **La red (#101):** el lint reporta la ficha con la **fila vacía de la plantilla** y ≥2
   papers extraídos citados.
   ⛔ **Herramienta: `python scripts/contrast.py <slug>` (#314/#317)** — nunca trunca una cita,
   agrupa por campo, arrastra `linea`/`segunda_mano` y ⛔ **no sirve lo que `--drop-core` sacó
   (#329)** (`--incluir-dropeados` lo muestra). Propone: el inventario lo escribís vos.
   ⛔ **Para la PROSA, `--cita --grep <re>` (#385):** emite «valor» (loc) [[bibcode]] pegable.
   ⛔ **Agrupar N fuentes bajo un MECANISMO común exige haberlo visto en las N (#370).**
   ⛔ **Al corregir, la primera opción es SACAR la parte equivocada, no reescribirla (#389)**
   (`apply_fixes` avisa el material AGREGADO por bloque).
   ⛔ **La fila de `--filas` sale CON EL VALOR ADENTRO y NO SE RE-TIPEA (#322):** vos escribís **la
   glosa**; **una fila, una fuente**. ⛔ **Las comillas son las del EXTRACTOR: el script no pone
   ninguna (#330)**; lo que sale sin comillas NO es verbatim y no se entrecomilla.
   ⛔ **La extracción es testigo de lo que el SINTETIZADOR re-tipeó, nunca de lo que la MÁQUINA copió
   de ella (#454):** en el bloque de salvedades de una `## Vista` el único testigo independiente es
   el `.txt`; si calla, sale **no evaluable** con la marca `⚠verificar en el PDF`.
   ⛔ **La cita se verifica contra la EXTRACCIÓN, no contra el `.txt`** (#315/#317) y bloquea sólo con
   **evidencia positiva** (#318/#321): la frase bajo **otro** bibcode, o prefijo largo con cola
   divergente; el **silencio** no. ⛔ **Pero PRIMERO se prueba contra el `.txt` de SU fuente, con UNA
   implementación (`lib_quotes.quote_verdict`, #324).**
   ⛔ **El `.txt` también puede ACUSAR, en un dominio acotado (#333):** prefijo largo presente y cola
   distinta, en prosa, desde un **borde de palabra**, sin `$…$` ni celda. ⛔ **El EMPALME DE COLUMNAS
   no acusa si la cita REANUDA (#364/#388).** ⛔ **No bloquea**: la salida es la **marca `⚠verificar en
   el PDF`**, que `contrast --validar` deja **lista para pegar** y no aplica (#341).
   ⛔ **La extracción de un PDF REEMPLAZADO no acusa sola (#437):** se mide contra el `.txt` nuevo.
   ⛔ **Alcanza `## Vista` sumando el bibcode de la NOTA a los adyacentes (#373); el LINT usa esa regla
   y esa función (#394), y el bibcode propio SUMA, nunca reemplaza** (`cfg.with_own_bibcode`).
   ⛔ **Ese cruce es PASO DE CIERRE de toda operación que sintetice, ANTES del verify (#323):**
   `python scripts/contrast.py [<slug>] --validar-todo` (sin slug, toda la bóveda; exit ≠ 0, declara
   población y no evaluables) — un `grep` de segundos antes que N subagentes. ⛔ **Sin slug es además
   pasada periódica de `maintain` (#386)**, registrada en `_citas.yaml`.

#### El CICLO DE LA LENTE — cómo se encadenan las piezas (#310)

En orden, con su consecuencia:

1. **La lente de SUJETO es lo que hace que una vista no sea un resumen** (#188): se pregunta *«qué
   dice sobre {sujeto}»* con los alias pegados. ⚠ En la primera pasada **no puede ser angosta**.
2. ⛔ **Los EJES no se declaran antes de leer: se DESCUBREN al contrastar** — pedirlos antes es pedir
   la respuesta que la operación existe para producir, y **cierra hallazgos**.
3. **El contraste (2b) es el PRODUCTOR de ejes, no un resumen**: ahí nace el vocabulario del tema.
4. **El eje descubierto tiene tres destinos**: la **config** del tema (`ejes:`, #307), la
   **re-lectura** con esos ejes (`--enfasis`, #308) y la **próxima búsqueda** (una celda vacía del
   inventario *es* una query).
5. **Los ejes son DEL USUARIO**: viven en `themes.yaml`, el contraste los **propone y no los escribe**
   (misma doctrina que `--drop-core` y AUD-160), y sin declarar rigen los de `relevance.facets` (D-43).
6. ⛔ **Qué se propaga solo y qué no**: la vista nueva → nota del paper (#239) y el roll-up del
   concepto, **sí**; la vista → **prosa de la ficha**, **NO**: reescribir un bloque **vence las
   anclas** (D-4/D-20), obliga a re-verificar (#203) y ese ciclo no converge solo (#282).

**El invariante (INV-146):** toda vista declara **los ejes vigentes al leerla** (`vistas[].lente`; con
`enfasis`, los de ESA lente, #372). ⛔ **La LENTE PREGUNTADA la escribe el PROMPT (#395)**, no el
cosechador, y no se deriva de las claves de `ejes` (ésas son lo **contestado**, #270). Migrador:
`make_notes.py --restamp-lente`. Cambiar los ejes de un tema produce un **diff computable**, nunca
una re-interpretación silenciosa: la vista vieja sigue válida, cambia su **cobertura**.

2c. **Síntesis a la nota viva**, apoyada en el inventario: la ficha (frontmatter propio, prosa,
   huecos) y los conceptos e hipótesis relacionados; la matriz se re-estampa (`--restamp-matrix`). ⛔ Los campos de
   ground-truth **no se tocan** (espejo de NEA, #70).

3. Re-estampás `index.md` (`--restamp-index`) y appendeás a `log.md`.

> **Retro-linkeo (papers pre-existentes ↔ entidad nueva) — tres capas:** (a) el roll-up de una
> ficha-método junta también por `methods`, pero **no acumula solo**: re-correr `make_notes.py <slug>
> --theme` (el lint reporta la tabla desactualizada); (b) `make_notes` mergea **add-only** los seeds
> del ingest (nunca pisa la extracción LLM); (c) `ingest-theme` incluye el **retro-tag por grep** de
> los `aliases` sobre todo el corpus, con juicio de LLM (uso real, no mención al pasar).

> **Tema fuera de ADS (opt-in — sólo a pedido explícito).** Para **métodos de otras disciplinas**
> cuya bibliografía vive fuera de ADS: las fuentes se **declaran**, no se descubren por query. La
> entrada lleva `source: ads | web | local-pdfs [+web]` — ⚠ **(#209) no dice «dónde se busca», dice
> QUÉ CADENA CORRE el orquestador**; el descubrimiento multi-backend es `discover.py --theme <slug>`
> (paso 0b). Un tema off-ADS puede ser **mixto**: su mitad astro entra por **`query:` poblada** →
> descubrimiento ADS completo (⚠ **sin compuerta**: en un tema el core del chaining entra solo salvo
> `chain_autoaccept: never`, INV-49), o **sólo `extra_core:`** → sub-cadena acotada; los papers con
> bibcode ADS van siempre en `extra_core:`, nunca en `sources:`; **`source: ads` + `query: null` +
> `extra_core:` = corpus declarado (#384)**. Lo inconseguible → `pending: …` (stub `pending_source`),
> sin frenar. **`ingest-star` sigue astro-only.** Papers sin bibcode ADS → clave sintética
> `AAAA+Autor`; páginas web → **snapshot `.txt` determinista** (`fetch_web.py` vía defuddle, que crea
> además el stub). ⛔ **Una `url:` que sirve un PDF NO se snapshotea: se BAJA como PDF (#242)**
> (`fetch_web` mira el `Content-Type`). La **frontera dura sigue rigiendo**: sólo bibliografía citable.

### Registro de ingesta (`vault/config/registro/<slug>.yaml` — versionado, #51/#64)
Cada sujeto ingestado deja un registro que **se commitea y viaja**. Regla de oro: **`build/` guarda
lo regenerable, el registro guarda lo que no lo es.** Secciones:

- **`descubrimientos`** — lo que trajo la cascada de `discover`, **con sus identificadores** (#231).
- **`busquedas`** — una entrada por corrida, **acumulativo** (D-28: el universo es la **unión**; cada
  entrada distingue `n_nuevos` de `n_ya_estaban`). La escribe `query_ads`: `fecha`, `query` efectiva,
  **`fq`** resuelto (#238/#295; la pantalla lo imprime SIEMPRE con procedencia, #354), `rows` y
  **`traidos`** (#458: ADS topea en 2000 por request y `query_ads` **pagina**), `n_found`, `n_total`,
  `n_core`, `n_candidates`, `n_dropped`, `truncated`, `almagesto_version`, **`bibcodes`** y
  **`lente`** (contra lo que se detecta la lente desincronizada).
- **`cadena`** — qué pasos corrieron, con fecha, versión, `via: orquestador|suelto` y escotillas;
  **cada script se estampa a sí mismo** (D-57) y el lint **nombra el paso** donde se cortó — ⚠ **sólo
  para ESTRELLAS** (AUD-209): el orden de un tema depende de su `source`.
- **`decisiones`** — el juicio de curación, por clave (`decision`/`motivo`/`fecha`), en los **dos
  carriles**: `triage.py --drop` (candidato del chaining) y `triage.py --drop-source` (fuente
  declarada off-ADS, #81, con `origen: fuente-declarada`). Un descarte que se **revierte** se
  **anula** explícito, con el motivo viejo en `previa` (D-52). `ingest_theme` **avisa** si un item de
  `sources:` lleva una clave ya descartada.

La compuerta de triage **no se apaga por flag** (D-48: `--no-triage` se eliminó; su política es
`chain_autoaccept`). Efectos: `make_notes` estampa en la cabecera **una línea** con fecha,
universo→core, pendientes y la ruta al registro; el lint deja de dar **falso limpio** sin `build/`
(*triage pendiente* y *corpus truncado* caen al registro, con fecha). El `build/<slug>/triage.json`
viejo **ya no se lee**: se consolida con `triage.py <slug> --migrate` y, mientras exista, el **lint
lo bloquea**.

### Los cuatro cuadrantes de la curación — quién decidió y por qué (#111)

Toda decisión de curación deja registro **versionado**, en los cuatro casos:

| | Aceptar | Descartar |
|---|---|---|
| **con bibcode ADS** | `extra_core: {bibcode, via, motivo[, fecha]}` (D-58) | candidato del chaining: `triage --drop … --reason` (#51) · **core del sujeto: `triage --drop-core … --reason` (#112)** |
| **fuente off-ADS** | `sources: {…, via, fecha, motivo}` (#111) | `triage --drop-source … --reason` (#81) |

⛔ **`extra_core` fuerza la ENTRADA; `--drop-core` es su simétrico (#112).** Una decisión de curación
que el clasificador ignora en silencio es peor que no tomarla. Propiedades del carril:
- **El carril es `sujeto`, no global**: la exclusión es del par `(paper, sujeto)`.
- **El paper excluido queda VISIBLE**, con `via: manual-drop` y el motivo en `why_excluded`.
- **Los artefactos se borran** (PDF y `.txt`; si quedan, #108 los reporta para siempre). ⛔ **En la nota que SE CONSERVA, `drop_core` re-apunta
  `pdf:`/`fulltext:` por verdad de disco (#217).** **La vista y la extracción no se tocan** (el lint
  dice que ya no hay contra qué re-verificar). La **nota** se borra **sólo si el paper no pertenece a
  otro sujeto Y no tiene extracción**. Los `[[wikilink]]` rotos **no se reparan** (#132).
- **El diff de re-clasificación lo respeta** (`lens_diff_offline`, `reclass_diff`).

INV-24: core es `f(paper, lente)` **módulo curación declarada** —motivo obligatorio, fechada,
versionada, viaja—.

⛔ **`via` son DOS vocabularios, uno por carril (#266).** El de **`extra_core`** (ADS) vive en
`lib_config.EXTRA_CORE_VIA`: `usuario` · `triage` · `citado-por-corpus` (**por qué mecanismo**
entró). En **`sources:`** es **cerrado y BINARIO** (#206): `usuario` (lo trajo una persona) ·
`descubrimiento` (lo propuso la cascada de `discover`) — **quién decidió**. Escribir el valor del otro
carril hace que el loader **rechace duro**. En `sources:`, **`motivo`** es obligatorio; el lint
**bloquea** la entrada sin `via` o sin `motivo`, fuera del vocabulario o con valor **retirado**. ⚠ El
PDF que cierra un `pending_source` no necesita `via` propio.
⛔ **Lo declarado se CRUZA contra su `doi` o la primera página del PDF al ingestar (`check_sources`,
#353):** autor/año desmentidos por Crossref **bloquean**, el resto es backlog; no reescribe `sources:`.
⛔ **Cuando el equivocado es el CATÁLOGO se FIRMA, no se corrige el dato correcto (#463):
`metadata_revisada: [{campo, declarado, catalogo, motivo, fecha}]`**, que
`check_sources.py <slug> --firmar <key> --campo <c> --motivo "<por qué>"` imprime listo para pegar.
⛔ **El drift `bibtex` ↔ frontmatter (#397) lleva la MISMA firma, en la nota** (#483), vía
`fetch_bibtex.py --paper <bib> --firmar --campo <c> --motivo`. ⛔ **Cubre un ESTADO, no un campo:** si
`declarado` o `catalogo` cambian, vuelve; la firma vieja o rota **no se ignora** (D-4, #71).

⛔ **El carril off-ADS tiene salida hacia la ingesta** (#111): `python scripts/triage.py <slug>
--accept-source <doi> --via <via> --reason "<motivo>"` arma la entrada completa **lista para pegar**;
**`--promote-source <key> --bibcode <bib>`** migra a `extra_core` la fuente con bibcode ADS (#353).
Ninguno escribe `themes.yaml`.

### Append (plegar UNA fuente puntual a una entidad existente — skill `append-knowledge`)
El usuario trae **una fuente concreta** (bibcode ADS, PDF local o URL) para una ficha/concepto que
**ya existe**: plomería mínima según el tipo (bibcode → `extra_core` + cadena idempotente; off-ADS →
item en `sources:` + `ingest_theme.py`, o `fetch_web`/`make_notes --web`), extracción enfocada en el
eje del destino, síntesis a la nota viva (rige la regla de poda y `disputes`) y cierre estándar
(autosuficiencia + verify-citations + lint + log). **No crea entidades** (eso es Ingest) **ni barre
por query lo nuevo** (eso es Mantenimiento/refrescar); un dato suelto sin fuente citable no entra
(regla #0). Detalle en el skill.

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

**Cuándo:** paso de cierre de **toda operación que escriba prosa con `[[bibcode]]`** — antes de
lint/commit. **La nota nace 100% verificada (D-5):** *"sin verificar"* sólo puede aparecer después,
por una edición. El procedimiento (fan-out, prompts, barrera, resolución) vive en el skill; acá va
el contrato del artefacto.

**Qué hace:** descompone la nota en pares (afirmación, `[[bibcode]]`) —filas de tabla e ítems de
lista **heredan la cita del ámbito que los introduce**; las `SECCIONES_ESTAMPADAS` quedan afuera— y
lanza **un subagente por FUENTE (#100)** que lee SÓLO ese PDF (grounding-first, prohibido de memoria)
y devuelve **dos ejes separados** (D-59): un `veredicto` de RESPALDO —`soportada|no-soportada|
contradice`— y la `condición` bajo la que la fuente lo afirma, más **cita textual + nº de PÁGINA del
PDF** (obligatoria; sin cita ⇒ no-soportada: tiene que tocar el **contenido distintivo**).
`no-soportada` = la fuente **calla**; `contradice` = **afirma lo contrario** → corrección o
**disputa** (#71). Cada falla se **resuelve** (bajar la afirmación, reasignar la cita, marcar
`inferencia`, o taguearla). ⚠ Los ejes de **grado** (`parcial`, columna `Score`) se eliminaron y no
vuelven.

⛔ **La condición se CLASIFICA, con vocabulario cerrado: `acota` | `contextualiza` (#221).** Test:
***¿la afirmación queda falsa si se saca la condición?*** → **`acota`** (se resuelve sí o sí: fila de
`## Régimen de validez`) / **`contextualiza`** (va al reporte). Es **columna, no prosa**.
⛔ **Clase UNA vez; la resolución la escribe `write_verif_sidecar --resolver
<ancla>[:<bibcode>]=<dónde>` (#427)** — migrador `--migrate-condition-prefix`. ⛔ **Se direcciona por
el PAR, no por el ancla (#434).** ⛔ **La condición de una ronda posterior no se pierde (#451):** rige
el **último eslabón** (#450); la condición **distinta** se encadena —`acota→resuelta: <dónde> · <vieja>
⟂ acota: <nueva>`— y la fila vuelve a contar como pendiente; el escritor **declara** la que no quedó
vigente.

El subagente contesta además la **sobre-generalización** (#74: afirma **de más**) y, en
transcripciones, la **completitud** (afirma **de menos**).

⛔ **La TABLA vive en el HERMANO `<nota>.verif.md`, no en la nota (#344).** En la nota quedan **la
línea de cabecera**, **las tres sub-secciones** de hallazgos y un **puntero**. ⚠ Hermano en el mismo
directorio, **no** un `.verif/` con punto (Obsidian lo esconde). Las **anclas** hashean bloques **de
la nota**. El par es un **iff** (INV-148): tabla todavía adentro (→ `make_notes.py
--migrate-verif-sidecar`), cabecera sin hermano y hermano huérfano **bloquean**; cabecera
desincronizada de su tabla es R-1. ⛔ **Una sola función resuelve dónde vive**
(`lib_blocks.verif_rows`). Un hermano **no es una nota** (`cfg.note_paths` lo saca de todo
enumerador), pero sus `[[bibcode]]` cuentan para los wikilinks rotos y los reescribe todo renombre;
es la **octava capa** de `entity.py`.

**El bloque `## Verificación de citas`** — una fila por par, en el hermano:
`| # | Afirmación (extracto) | Fuente | Veredicto | Evidencia | Ancla | Hash fuente | Condición |`
- ⛔ **Sin fila no hay dónde colgar el ancla**: no colapsar las soportadas en prosa.
- ⛔ **Sólo `Afirmación (extracto)` se trunca (#226)**; `Evidencia` lleva su localizador **al final y
  completo** (#122). ⛔ **El corte no cae dentro de `$…$`, `` ` `` ni `[[ ]]`** (#274b/#257c:
  `lib_blocks.truncate_claim`). ⛔ **La celda lleva PROSA, nunca un `repr()`** (#274a).
- ⛔ **`Hash fuente` declara CONTRA QUÉ ARCHIVO se verificó: `txt:<sha10>` o `pdf:<sha10>` (#117).**
  En filas nuevas: `pdf:`. Sin prefijo el lint **bloquea** (`make_notes.py --migrate-verif-archivo`).
  Excepción (#223): la fila `no verificable por extracción` **no declara archivo**.
- ⛔ **Documento largo leído del `.txt`: los DOS localizadores (#200)**; desde #205 no se produce en
  filas nuevas.
- ⛔ **Un veredicto que exige acción NO queda registrado y sin resolver (#91):** `no-soportada` /
  `contradice` **pelados bloquean**.
- ⛔ **Con DOS RONDAS, la segunda ANOTA, no pisa (#232):** `contradice→corregida`; con más rondas la
  celda encadena (#274c). ⛔ **El veredicto VIGENTE es el ÚLTIMO eslabón, y la resolución va DESPUÉS
  de él (#450):** `soportada→contradice` es una contradicción **abierta**. Partición, `(N resueltas)`
  y re-anclaje (#366) van por el vigente; lo que eso oculta se declara (`revertidas`). ⚠ La anotación
  es **texto libre** (#316).
- ⛔ **La cabecera la genera el mismo código que lee la tabla** (`lib_blocks.verif_summary`, INV-81):
  los **cuatro** veredictos y, tras un **`—`**, `con_condicion`. Las **tres sub-secciones** van
  **aunque digan «ninguna»**. ⛔ Su línea se lee **normalizada** y el fragmento, por la **plantilla que
  lo escribe** (#430); red **por SECCIÓN**. Migrador `--restamp-section`.

**Los dos hashes (el ancla, D-4/D-20)**: el **ancla** hashea el **bloque markdown normalizado** que
contiene la cita —reflowear no la mueve, cambiar un número sí; un blockquote hard-wrapped es UN
bloque (#224); una fila sin `[[bibcode]]` propio hereda el del caption— y el **hash de fuente**, el
archivo **leído**. Los calcula `lib_blocks.py`: **no se escriben a ojo**. ⛔ **El bloque escrito se
re-parsea antes de publicarse (#284):** `lib_blocks.render_verif_table` escapa cada celda y
**rehúsa** un bloque cuya lectura no reproduce lo escrito.

**Salvedades de fuente:** `.txt` con header `source: ocr` → citable con salvedad (ante discrepancia
de símbolos, abrir el PDF). `pdf_source: eprint` → una discrepancia numérica contra un valor
publicado es candidata a **diferencia de versión**, no se "corrige" la nota hacia el preprint. Si
una afirmación no aparece en el `.txt` (ecuación, tabla, escaneo): abrir el PDF o marcar `no
verificable por extracción`. Es **juicio de LLM**, no prueba: su tasa de error se mide con el
**auto-benchmark** (`python scripts/bench_verify.py seed`; nada de eso entra al vault).

**Qué es una `inferencia` y cómo se escribe (D-42).** Una afirmación que la bóveda sostiene y que
**ninguna fuente dice**: sale de combinar dos o más que sí. Se escribe **nombrando sus premisas**
—`(inferencia de [[b1]], [[b2]])`—: sin al menos un `[[bibcode]]` **el lint la bloquea**. ⚠ El
énfasis markdown alrededor no cambia nada (#276); `inferencial` no cuenta.

**Regla dura — todo lo apuntable es chequeable:** toda afirmación fáctica va **citada `[[bibcode]]`
o marcada `inferencia`** — nada sin respaldo. ⛔ **Y la cita textual lleva su `[[bibcode]]` PEGADO
(#316/#325):** `«…» [[bib]]`, `«…» (p. 4) [[bib]]`, `«…» ([[bib]], p. 4)` (#488) o, en una fila,
la celda *Fuente*; con prosa en el medio la **mención** posterior roba la cita. ⚠ La matemática
**parte** el chequeo como la elipsis (#326). Excepción: los valores de ground-truth (NEA) en `stars/`
no se verifican contra papers (su consistencia la chequea el lint). El lint reporta como backlog los
conceptos e hipótesis sin ninguna cita.

### Auditoría de una FICHA (skill `audit-note`)
**El eje que ninguna otra capa mira: ¿esta ficha dice la verdad y se sostiene sola?** (el lint mira
estructura, `verify-citations` claim ↔ su fuente, `find-contradictions` claim ↔ claim, `auditar` el
framework). **Cuándo:** a pedido explícito, **nunca** como paso de cierre — es caro por diseño.
**Qué hace:** siete frentes en paralelo —estándar de la nota (con la prueba de *escribir el
pseudocódigo desde la nota y anotar dónde se traba*), la nota contra sí misma, integridad del
artefacto, aritmética, cadena de verdad, coherencia con el mundo declarado, y la nota contra su
cadena—, cada uno declarando **su población**; barrera; corrección **serial** volviendo a la fuente;
y **re-verificación de lo tocado** (#203). ⛔ **Lo que no se pudo cerrar sale marcado en la nota** con
la cuarta marca en línea (abajo), no en un reporte que se pierde.

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
**Seis** caducidades se miran en **una sola pasada**: retracciones, correcciones, **versiones** (el
preprint salió publicado, D-19), **snapshot web** (el modo más silencioso: ni DOI ni bibcode),
**ground-truth** (NEA cambia valores entre releases) y el **conteo de citas de la puerta 2** (#106).
⛔ **El hallazgo de VERSIONES sobrevive a la corrida (#298): `versions_disponible: <bibcode>`
estampado en la nota** + backlog del lint con el `--rename-paper`; declara su población. ⚠ La nota
con bibcode publicado que igual lee el preprint es backlog aparte.
⛔ **Ese backlog se CIERRA con un comando (#436): `python scripts/replace_pdf.py <bibcode>
<ruta.pdf> --source publisher --reason "<motivo>"`.** Copia a **todos** los slugs, re-extrae **sólo
ese** `.txt` (`extract_fulltext --bibcode`), anula `eprint_version` y **emite el alcance de la
re-verificación**. ⛔ La extracción queda **marcada** `_paginacion` y se **re-pagina RELEYENDO el PDF**
(`repaginate.py`, #494), nunca con la página que el `.txt` deduce. ⛔ **Firma `pdf_reemplazo` en la
nota, add-only, y AVISA si el entrante tiene menos páginas (#437)** — avisa, no rehúsa.
⛔ **Los slugs son la UNIÓN de PDF y `.txt` (#448).**
⛔ **El REUSO entre slugs (D-18) deja una pregunta hecha, no una respuesta (#297):** la línea del
reuso declara `pdf_source`, fecha y que la antigüedad **no se chequeó** (preprint y publicado no
colisionan por DOI, #216); el detector se corre acotado con `sweep_external.py --bibcodes b1,b2` (no
registra la pasada), y el lint lo levanta como backlog, junto con *«`_red.yaml` no existe»*.
⛔ **Reporta, no aplica solo — con UNA excepción nombrada** (AUD-206): **`retracciones`**
(`check_retractions` estampa `retracted:` / `corrections:` **sin preguntar**: una fuente retractada
citada rompe la frontera dura, y lo que escribe es metadata). Versiones y web proponen el comando,
ground-truth pregunta, citas-puerta2 reporta. El renombre preprint→publicado **nunca** es automático.
La caducidad se registra **versionada** en `vault/config/registro/_red.yaml`; un detector que **no
pudo correr** se declara y **no** entra en `cubrio`.

**Fuente retractada citada en prosa (D-47):** la afirmación **no se borra** —puede ser cierta por
otra vía—: se **marca en línea** con `[[bibcode]] ⛔retractada`. Sin la marca el lint **bloquea**. Un
`(retractada)` pelado daría falso positivo con cualquier mención en prosa.

**Ground-truth que cambió bajo la prosa (AUD-42):** el ancla de fuente (D-20) **nunca** hashea
`raw/ground_truth/<slug>.json`; al aplicar un diff, `sweep_external` deja `_cambios` en el JSON y el
lint **pide la marca** `⚠desactualizado` pegada al valor: no se borra, se hace visible.

**El conteo de citas que mueve la puerta 2 (#106 / INV-104).** Es la única metadata que **cambia
sola**. ⛔ La regla es **"todo cambio de veredicto es visible y fechado"**: **`lib_config.puerta2_cruces`**
(offline, lint) compara el umbral vigente con el del registro —*"editaste el umbral"*— y
**`sweep_external.sweep_citas`** re-consulta los conteos —*"el mundo se movió"*—. Ninguno aplica. El
umbral se persiste con `query_ads.lens_used(meta)` y se compara con `in`, no por truthiness
(`fundacional_min_citas: 0` es una decisión).

**Lo que no se pudo verificar queda MARCADO en la ficha (#225): `<afirmación> ⚠verificar en el PDF
(<qué se dudó>, <fecha>)`.** La producen `audit-note` y `contrast --validar` (#341) —una sola
definición, `lib_quotes.verificar_pdf_mark`—: **no destruye**, es **visible**, **la levanta el lint**
y **se saca cuando alguien la verifica**, con la evidencia. **Ante la menor duda se marca**. ⚠ No es
excusa para no verificar: si la fuente está en disco, se abre.

⛔ **El `log.md` NO afirma citas textuales (#391)** —ninguna capa de verificación lo audita—: la cita
va **a su nota**; si una entrada necesita mostrarla, va en un **blockquote** (mención, no afirmación,
#387). La exención es **estructural** (`Block.kind`) y la decide UNA función
(`lib_quotes.log_quote_exempt`, #386, INV-141). Vale **sólo en `log.md`**. La vieja marca
`⚠ corregido` en el `log` ya no exime nada: es prosa (`make_notes --fix-key` imprime la nota de
corrección lista para pegar, #355).

Éstas son las **cuatro únicas marcas en línea** del sistema: `(inferencia de [[bibcode]])`,
`[[bibcode]] ⛔retractada`, `<valor> ⚠desactualizado` y `<afirmación> ⚠verificar en el PDF`.

### Mantenimiento (cuidar lo ya ingestado — skill `maintain`)
**No crea entidades** (eso es Ingest); opera sobre estrellas/conceptos que **ya existen**. Sub-modos:
**refrescar** (papers nuevos → re-sintetizar sólo lo nuevo), **borrar** y **renombrar** una entidad
—`python scripts/entity.py delete|rename` (INV-19): las **ocho** capas (clave del YAML, registro,
ground-truth, `raw/pdfs`, `raw/fulltext`, extracción, nota + su hermano `.verif.md` (#344),
`build/`), dry-run sin `--yes` porque el registro es
el único artefacto no regenerable. Lo que no hace solo lo **avisa**: no borra el paper compartido, no
repara los `[[wikilink]]` rotos ni la nota que queda sin destino; del otro lado, el lint reporta las
**capas colgadas** de un slug que ya no existe—, **re-clasificar** tras cambiar `relevance.facets`,
**resolver el backlog del lint** (P_rot sin documentar, drift PDF↔disco, cobertura — los
**huérfanos no**: son bloqueantes, se arreglan al cierre de la operación que los creó), y la
**pasada periódica de red** (`python scripts/sweep_external.py`, toda la bóveda — la cadena de
ingest sólo chequea el slug en curso; esa misma pasada estampa también `corrections`). Invariante:
la cadena es idempotente (refrescar es seguro); **nunca** se pisa la extracción LLM ni el
ground-truth sin `--force` explícito. Detalle en el skill.

### Propuestas (lo que el sistema sugiere y espera una firma — `scripts/proposals.py`)

⛔ **Una PROPUESTA no es deuda, y por eso tiene su propia superficie (#328):** la deuda se **agenda**
(la reporta el lint); la propuesta necesita que alguien **firme** y se pierde si nadie la lee.
`python scripts/proposals.py [<slug>]` las junta con **su motivo textual**, declara su población y
**lo que no puede barrer** (un eje descubierto en 3b vive en la conversación). Reporta y no aplica.
⛔ **Cada categoría declara DÓNDE aterriza su firma y si el barrido la cruza (#435):** *cruzada*,
*no cruzable* (la fila trae el valor vigente al lado) o *se cierra sola*. Lo firmado se lista
**aparte** (AUD-207), nunca silenciado.

### Lint (chequeo de salud)

**Cuándo:** paso de cierre de **toda operación que escriba en `vault/wiki/`** (ingest,
append-knowledge, maintain, find-contradictions, query archivada, test de hipótesis), **antes de
commitear** y **después** del verify (resolver una cita no-soportada cambia la prosa); más una
pasada completa periódica. Es barato. Correr `python scripts/lint.py`.

⛔ **El catálogo completo —cada categoría, su severidad y cómo se cierra— vive en `docs/lint.md`.**
El reporte del lint es autodescriptivo (cada categoría nombra su resolución); esta sección fija las
reglas del gate que hay que saber antes de correrlo.

**Tres severidades** — bloqueante (exit ≠ 0), WARN (se revisa a mano) y backlog (deuda declarada;
se trabaja con `maintain`). No existe "informativo" (AUD-207): lo declarado-y-resuelto se reporta
**aparte**, nunca mezclado con la deuda real. Dos reglas del reporte:

- **⛔ No evaluado cuenta para el exit** (D-43): un chequeo que no pudo correr (`objective.yaml`
  ilegible, sin `git`) suprime su categoría normal — un `(0)` que nadie midió se lee como veredicto.
  Misma doctrina en `query_ads`: rehúsa clasificar con una lente ilegible.
- **Cada categoría declara su población** (INV-40): `> sobre 412 notas de vault/wiki/`.

**Bloqueantes** (0 para cerrar; la lista viva es `SEV_BLOQUEANTE` de `scripts/lint.py`, AUD-237, y
el detalle con sus migradores está en `docs/lint.md` § *Bloqueantes*; la enumeración completa
que había acá, en el *Apéndice A*): wikilinks rotos, frontmatter inválido, fuentes retractadas (y citadas sin
`⛔retractada`), huérfanas (el `index.md` estampado NO cuenta como link entrante, #249), contradicciones con ground-truth, schemas retirados, vocabularios
cerrados violados, veredictos sin resolver, identidad duplicada, `inferencia` sin premisas, paper sin
`## Abstract` o sin destino, par nota↔`.verif.md` roto, driver `merge=ours` registrado (#390) y
`bibtex` sin `bibtex_source` (#397) o a la vez con `sin_bibtex` (#475). Si agregás una, va a esa
lista.

**La fuga de implementación** (regla #0) es **WARN**: heurística de alta señal, cada hit se revisa
a mano. No mira las `SECCIONES_ESTAMPADAS` (#214), y la exención no alcanza a `## Vista — <sujeto>`.

**El cierre toma el SUJETO: `python scripts/lint.py --cierre <slug>` (R-1, #121).** Sin flag, los
pares de verificación vencidos (D-4/D-20) y la cobertura de verificación reportan como **backlog**
(la nota «stale» lo es por el **conjunto de anclas** de sus bloques citables, #445); con `--cierre`
**bloquean** — un par sin verificar significa que no terminaste (D-5). Con el slug, el alcance son
las notas del sujeto (ficha/concepto + papers, incluidos los retro-linkeados); ⚠ **el reporte no se
acota** (la deuda ajena se lista, marcada *«no frena»*) y **el alcance acota sólo la severidad de
cierre**. Slug inexistente → rehúsa (exit 2). Sin argumento, pasada de cierre global. Los skills de
cierre lo invocan con el flag; la higiene de `maintain`, sin él.

## Reglas de método 4-6 (las de operar la bóveda)

⛔ **Las reglas 1-3 (tests, dobles, mutación), la convención de idioma del código y las diez redes
viven en `docs/desarrollo.md` (#465):** se leen al escribir código del framework, que es operación
explícita del template; una instancia no edita framework (#377). La numeración no cambia. Las tres
que siguen rigen **operaciones de bóveda** y por eso se quedan:

4. **Un mapa que atribuye mal es peor que uno vacío**: el vacío se ve, la atribución falsa se lee
   como verdad. Vale para `docs/trazabilidad.md`, `docs/contrato.md` y cualquier tabla estampada.
   ⛔ **Todo chequeo que mire texto de una nota NORMALIZA EL MARKDOWN primero** (#168, #276, #283,
   #309).
5. **Cuando dos mediciones no reconcilian y no se puede re-medir, se DECLARA la discrepancia**; elegir en silencio es cómo un documento empieza a mentir.
6. **Fan-out para LEER, aplicador serial para ESCRIBIR, barrera antes de CONSUMIR — y lo escrito se
   RE-VERIFICA.** Dos correctores sobre el mismo bloque lo corrompen en cadena (#197) y derivar
   trabajo de una etapa que todavía corre deja hallazgos que no mira nadie (#199). **Un solo
   escritor, y una barrera antes de que algo consuma resultados.**
   - ⛔ **El aplicador comparte la definición de «bloque» con quien produce los pares (#222)**: la red
     barata es **contar los pares antes y después y abortar si bajaron**.
   - ⛔ **La cuarta cláusula (#203): el ciclo cierra en *corregir → re-verificar lo tocado*** — un
     aplicador no valida lo que aplica.
   - ⚠ **Y ese ciclo NO CONVERGE solo (#282):** la salida **no es aflojar el ancla** (#224): es
     distinguir la corrección que **cambia lo que la afirmación dice** (se re-verifica) de la
     **derivada de la propia verificación** (se re-ancla). Lo emite `python scripts/reverify_subset.py
     <nota>` (#257): re-anclables / a re-verificar / filas huérfanas. ⛔ **Propone y no escribe**;
     empareja por **cobertura del extracto** (#226) y **nunca cruza `bibcode`**.

Corolario que las cruza a todas: **una promesa que el sistema dejó de cumplir en silencio es peor
que una que nunca hizo.** Si al tocar algo se rompe una promesa declarada, eso **se anota**, aunque
no se arregle en el momento.

## Token / secretos
El token ADS va en `vault/config/ads_dev_key` (**gitignored** — nunca se commitea) o en la variable de
entorno `ADS_DEV_KEY`. Token gratis en <https://ui.adsabs.harvard.edu/user/settings/token>.
⛔ **El `mailto` del polite pool (OpenAlex, Crossref, Unpaywall) es OPT-IN y no sale de `git config
user.email`:** se declara en `vault/config/mailto` (gitignored) o en `ALMAGESTO_MAILTO`; **sin
declararlo no sale ninguna dirección** y las tres APIs funcionan igual, en el pool público.
`build/` y `outputs/` gitignored. PDFs por git-lfs (`vault/raw/pdfs/**/*.pdf`). El resto de
`vault/config/` **sí se commitea**, incluido `registro/<slug>.yaml` (es el punto: el juicio de
curación y el registro de búsqueda tienen que viajar).
