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

> **La cabecera de una ficha/concepto lleva una línea `> _Estado — …_`** con **tres fechas**
> que avanzan por separado y pueden divergir sin que ninguna mienta (D-12): **búsqueda** (última
> corrida + universo acumulado + escotillas), **síntesis** (cuándo se destiló el sujeto a la prosa —
> se **declara**, `cfg.save_sintesis` / `triage.py --sintesis`, porque no se puede derivar: `git`
> fecha el ARCHIVO, así que una cirugía de cabecera contaría igual que reescribir el resumen) y
> **verificación** (fecha del bloque, con la salvedad fija *"vigencia por par: la dicen las anclas"*
> — sin ella, la fecha se lee como "todo verificado a esta fecha", que es justo la lectura que el
> ancla corrige). Con una sola fecha por nota, refrescar el corpus hacía parecer re-verificado lo
> que nadie volvió a chequear —y re-sintetizado lo que nadie volvió a escribir (INV-82; hasta #150
> este párrafo prometía tres y enumeraba dos, así que la de síntesis no la estampaba nadie que
> siguiera sólo este documento).

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

⛔ **Y antes de usar una afirmación, VALIDALA CONTRA LA FUENTE. No sintetices desde la ficha sola.**
Al sacar un valor, una ecuación o un mecanismo de una nota para llevarlo a código, a un informe o a
otra síntesis: abrí el `.txt` de su `[[bibcode]]` (`vault/raw/fulltext/**/<bibcode>.txt`) y confirmá
que la fuente dice eso, **antes** de propagarlo. Es un chequeo por par, no una re-lectura del paper:
grepeá la afirmación, mirá la línea, seguí.

**Por qué, y no es paranoia — está medido.** La prosa de una ficha es **capa LLM** (lo dice su propia
cabecera) y `verify-citations` es **juicio de LLM, no prueba**. En una sola operación de esta bóveda,
sobre un concepto ya extraído y sintetizado, el fan-out encontró **13 defectos**: cuatro
`no-soportada`, tres `contradice` y varias sobre-generalizaciones. **Siete eran de atribución** — el
dato de un paper adjudicado a otro: Newton al paper de 1997 en vez del de 1999, una detección de
agua al método en vez de a quien la reportó, «PCA vía SVD» a un paper que nunca dice SVD. Ninguno de
esos errores es visible desde la ficha: se ven **sólo** abriendo la fuente.

**Cómo, según lo que diga la nota del paper:**
- por defecto → `.txt`, y citás **línea**;
- `fulltext_source: ocr` → citable con salvedad; ante duda de **símbolos**, abrí el PDF;
- `symbols_lost: true` (#113) → las ecuaciones **no están** en el `.txt`; abrí el PDF y citá
  **página**. Grepear el `.txt` por esa fórmula no la va a encontrar, y su ausencia **no** significa
  que la ficha esté mal.

Si al validar encontrás una discrepancia, **no la arregles en silencio de tu lado**: es un hallazgo
de la bóveda. Reportalo para que se corrija acá, o el próximo consumidor tropieza con lo mismo.

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
  tabla `## Papers` de la ficha (que lista todo paper con la estrella en `stars:`). No
  re-narrar en la ficha lo que ya está en la extracción del paper. Esto mantiene la ficha **compacta**
  (rápida de ingestar, sin perder contexto) sin perder trazabilidad.
  ⚠ **Los tres roll-ups de la ficha se ESTAMPAN, no son Dataview (D-10/D-11; los tres desde
  1.35.0 — `## Papers`, `## Planetas` y `## Métodos aplicados a esta estrella`).** `## Papers` es una tabla
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
    ⚠ **El roll-up de métodos linkea `[[método]]` sólo si la nota existe; si no, lo estampa como
  código.** `methods` lo puebla la **extracción** (paso 3 de `ingest-star`) y las notas de
  `concepts/methods/` las crea **`ingest-theme`**, que es otra operación: con el link incondicional,
  seguir `ingest-star` al pie de la letra dejaba el lint en decenas de *wikilinks rotos*
  —bloqueantes— que **no se podían cerrar dentro de la operación que los creó**. La señal no se
  pierde: el lint la reporta como backlog *«`methods` sin página destino»*, la versión no bloqueante
  de lo que `thesis_links` sí bloquea (y la asimetría es real: un `thesis_links` nombra un concepto
  que `ingest-theme` crea en la misma operación que lo siembra).

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
- **papers/**: ⛔ **toda nota de paper pertenece a alguna ENTIDAD (D-23).** Al menos uno de
  `stars`, `thesis_links` o `methods` tiene que estar poblado. Sin ninguno de los tres el paper no
  entra en ningún roll-up y no lo alcanza ninguna ficha ni concepto: es extracción ya pagada que se
  vuelve invisible, y no es lo mismo que una nota **huérfana** —el detector de huérfanos mira los
  links entrantes, así que basta que algo la linkee para que el hueco quede tapado—. Es
  **bloqueante** (INV-94), y la salida es poblar el campo que corresponda, no borrar la nota.
  ⚠ Cuando `entity.py delete` deja un paper sin destino **avisa y no borra**: la decisión de qué
  hacer con una extracción cara es del usuario, no del script.
- **papers/**: ⛔ **la extracción es una lectura CON LENTE, y la nota declara cuál se hizo:
  `vistas[]` (#188).** El prompt del fan-out nunca pregunta *«¿qué dice este paper?»* sino *«¿qué
  dice **sobre {sujeto}**?»*, con los `grep` armados desde los alias de ese sujeto y los bullets
  ramificados por su tipo (#76) — pero la nota es **una por bibcode**. Con una sola sección sin
  scope, **el silencio de la nota sobre un eje es indistinguible de «se miró y no hay nada»**: el
  mismo falso limpio que D-34 persigue en las hipótesis (*«no hay evidencia» no es «no existe
  evidencia»*) y que la cobertura de `discover` resuelve distinguiendo *corrió con N* de *NO
  CORRIÓ*. Medido en una bóveda real: **141 de 908** notas las reclaman 2+ sujetos y **ninguna**
  tiene una segunda extracción — y `ingest-theme` lo produce **por diseño** en su paso 3b, porque
  el retro-tag corre después de la extracción.
  Cada entrada: `sujeto` (el mismo nombre que usan `stars[]`/`thesis_links[]` — es lo que hace
  comparables reclamo y lectura), `tipo` (vocabulario **cerrado** `star | theme`, **declarado** y
  no derivado, para que el lint cace el typo), y tres campos que dicen **cuándo** y **contra qué**
  se leyó: `fecha`, `txt` (de qué copia del `.txt` salió — el ancla de fuente cuando el mismo
  bibcode vive bajo varios slugs) y `lente` (las facetas vigentes al leer, que es el diff de lente
  de D-49 **a nivel de lectura**). **Forma dura como `extra_core`** (D-58): el escalar y la lista
  de strings **bloquean**; `vistas: [eps Eridani]` sería la misma conflación con otro nombre.
  ⛔ **La `fecha` es lo que dice que la lectura OCURRIÓ.** El stub nace con la vista de su sujeto y
  **sin** fecha (la ausencia es *no consta*): así la nota es coherente desde el minuto cero —no
  nace en rojo a mitad de cadena, la lección del `methods`→wikilink— y el lint reporta la **vista
  sin fecha** como backlog. La estampa el **cosechador** (`python scripts/harvest_views.py <slug>
  [--theme]`), que además mergea `methods`/`thesis_links`/`role` add-only, escribe la sección
  mientras siga siendo la plantilla del stub —prosa redactada no se pisa sin `--force`: puede tener
  anclas de verificación colgando del texto exacto— y **trae el `.txt` al slug del sujeto** (D-18),
  sin lo cual la vista de un paper retro-tagueado no es ejecutable.
  ⛔ **La escribe SÓLO la lectura, nunca el retro-link.** Es lo que mantiene a
  `stars`/`thesis_links`/`methods` como **reclamos** —`make_notes` los mergea add-only **sin leer
  nada**— y a `vistas[]` como **lecturas**. Un reclamo sin vista es backlog *(«lo reclama X y nadie
  lo leyó desde ahí»)*, y se cierra de dos maneras: haciendo la vista, o **declarándola**
  `no_vista: [{sujeto, motivo}]` cuando ese sujeto sólo aporta al roll-up. **Motivo obligatorio y
  por sujeto** (mismo criterio que `no_sintetizado` y que el `--reason` del triage): un paper que
  tres sujetos reclaman se saltea por motivos distintos en cada uno, y una escotilla sin sujeto los
  eximiría a los tres. Qué cuenta como reclamo: `stars` y `thesis_links` siempre; `methods` **sólo
  si ese nombre es un tema declarado** —lo puebla la extracción, así que es producto de la lectura
  («este paper usa un periodograma») y no un sujeto que la pidió; contarlo entero pediría una vista
  por método nombrado y el backlog nacería con centenares.
  La sección del cuerpo es `## Vista — <sujeto>` y **no** es sección estampada: es exactamente lo
  que `verify-citations` tiene que contrastar contra el `.txt`. El lint **bloquea** la incoherencia
  en los dos sentidos (vista declarada sin su sección; sección sin declarar) y el **schema viejo**
  (`## Extracción (LLM)` sin `vistas[]`), que es una extracción que no dice desde dónde se leyó.
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
  hay marca, vale la rama que registró el fetcher.
  **`symbols_lost` (#113) — el `.txt` está limpio y las ECUACIONES no están.** Tercer eje,
  **independiente** de los otros dos: `is_legible` mide *extraíble*, la marca de garble mide
  *correcto*, y éste mide **completo**. El modo de falla es silencioso en el peor lugar —
  `pdftotext` deja el marcador `(3)` y vacía su cuerpo, así que el `.txt` **parece** tener la
  fórmula—, y los dos casos medidos dan garble **0.00**: sin este eje no los ve nadie. Rompe dos
  promesas a la vez: el estándar **implementation-ready** de `concepts/methods/` (la ecuación es
  justamente lo que la nota promete que no hace falta ir a buscar) y la de `verify-citations` («las
  palabras reales del paper»), que leyendo ese mismo `.txt` devolvería **`no-soportada` sobre una
  afirmación correcta**. Cuando el campo está en `true`: la extracción se hace **del PDF** (`Read`
  lo rasteriza, así que el modelo *ve* la fórmula — es cuestión de **modalidad, no de modelo**:
  medido, un modelo chico leyendo el PDF recupera lo mismo que uno grande) y las citas de fórmulas
  van **por página del PDF**, no por línea del `.txt`. Calibrado sobre 813 `.txt` de dos bóvedas:
  de los 343 con ≥4 marcadores, p95 = 0.33 y después un salto al grupo de rotos (0.98–1.00); el
  umbral (60 %) cae en ese hueco y marca 13. ⚠ Con menos de 4 marcadores devuelve **no evaluado**,
  no `ok` — son **275 de 813 (34 %)**, así que un `False` ahí sería un falso limpio a gran escala
  (D-43). ⚠ **Los denominadores publicados NO reconcilian, y se declara la discrepancia en vez de
  elegir uno** (regla de método #5, #155): acá dice *13 de 343* y `extract_fulltext.py` dice *«marca
  13 de 295 (4.4 %)»*; y 343 (≥4 marcadores) + 275 (<4) = 618, no 813. Lo que **no** depende de cuál
  denominador sea el bueno son los dos números que el código usa —umbral 0.60 y mínimo 4
  marcadores—; lo que no se puede afirmar con esto es la tasa de marcado. Re-medir con un corpus a
  mano. El lint lo lista como **backlog, nunca bloqueante**: no es un defecto de la bóveda sino
  una propiedad de la fuente que el consumidor tiene que ver.
  Esa misma re-corrida es el **backfill de la marca de garble**: el chequeo que estampa `fulltext_source: ocr` sobre un PDF **que ya venía
  OCReado por el editor** sólo corría al extraer, así que un `.txt` escrito antes se quedaba
  `pdftotext` para siempre — el camino de skip lo re-leía sólo para preguntarle si era **ilegible**,
  y un escaneo del editor es perfectamente legible. Medido: 2 de 42 `.txt` de un tema real, uno de
  ellos un paper cuya ecuación la nota había transcrito con un subíndice equivocado por el OCR. No
  re-extrae: para ese caso la capa del PDF ya es el mejor texto que hay, así que es un estampado de
  header (idempotente). Importa porque `verify-citations` promete que la
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
⛔ **`pending` es vocabulario CERRADO y lleva `pending_motivo` obligatorio (#80).** Los tres valores
históricos describen **por qué falló** la adquisición o la extracción; **`adquisicion`** es el
cuarto y describe otra cosa: un libro que el usuario va a conseguir **no falló**, tiene otra
latencia — entraba forzado como `paywall` y se perdía el motivo real. El motivo es libre y
obligatorio por el mismo argumento que el `--reason` del triage: en seis meses lo que sirve es el
motivo, no la categoría (¿alguien la está consiguiendo, o nadie la miró nunca?). El valor se
escribía **verbatim** en la nota, así que un typo entraba mudo: hoy la cadena aborta y el lint lo
nombra.
⛔ **Una fuente LARGA declara cómo se la cita y qué parte entró (#80):** `unidad_cita:
linea|pagina|seccion` (default `linea`, no se estampa) y **`alcance`** (qué capítulos/secciones
entraron), obligatorio cuando la unidad no es la línea. Un libro rompe dos supuestos del contrato de
`verify-citations`: el fan-out asume un `.txt` que un subagente lee **entero** —700 páginas lo
revientan— y «línea 18443» no es una referencia utilizable. Y casi nunca entra el libro entero, lo
que choca con el chequeo de **completitud**, que sin `alcance` no puede distinguir un recorte
deliberado de una omisión. Es un eje **distinto** del `txt:`/`pdf:` de #117: aquél dice qué
**archivo** se leyó, éste **cómo se apunta adentro** — el `.txt` de un libro tampoco se cita por
línea.
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
(muestra el corte core/no-core sin bajar nada) iterando hasta que cierre. ⛔ **La lente del BUSCADOR también sale del objetivo (#85): `relevance.search_fq`.** Es el `fq` de
Solr que acota el universo **server-side, antes de traer nada** — o sea la mitad **más restrictiva**
del filtro, más que `relevance.facets`, que actúa después sobre lo ya traído. Estaba hardcodeada en
`query_ads` como `database:astronomy`, lo que era incoherente con el resto de la lente (todo lo demás
sale del objetivo) y bloqueaba el caso que este framework declara soportar: los **métodos de otras
disciplinas** cuya bibliografía canónica ADS no clasifica como astronomía. Tres estados: sin declarar
→ `database:astronomy`; con valor → ése; **`search_fq: null`** → no acota (todo ADS, a propósito). Un
`null` declarado es una decisión y no se lee igual que no declarar nada.
`relevance.facets` son **facetas**
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

⛔ **Y queda registrado POR CUÁL puerta entró cada paper (#126): `puertas: [fundacional|astro]` en
el registro.** Antes las dos se calculaban por separado y, al entrar el paper, se devolvía sólo
`core=True`: el `why_excluded` explicaba el **no** y nada explicaba el **sí**. Es la única metadata
que distingue **sin leer el paper** un fundamento de su campo (muy citado, puede no mencionar astro
ni una vez) de una aplicación astro (tres citas, pero es lo que la bóveda busca) — y `role` no sirve
para eso, porque lo puebla la **extracción**, o sea después de leer, y esta decisión se toma antes.
Con la puerta registrada, `triage.py <slug> --prioridad` agrupa los core por política —*«12 sólo
fundacionales, 20 sólo astro, 5 por las dos»*— y el recorte de lectura se decide **una vez** y se
declara con `--extraccion subconjunto --reason`, en vez de reconstruirse a ojo cada corrida. Lista
vacía = no es core; el campo existe siempre, así que «no consta» y «ninguna puerta» no se confunden.

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
`scripts/search_arxiv.py` (⚠ **el orquestador `ingest_theme.py` no lo corre solo**: lo alcanza
`discover.cascade`, que es un paso manual del skill —`discover.py --theme <slug>`—, más su CLI de
preview propia. #144: acá decía *«no cableado»* y 19 líneas abajo *«#95 queda cerrado: está
cableado»*; las dos frases usaban «cableado» en sentidos distintos y ninguna lo decía) y
`scripts/openalex.py` (en producción: lo usa `citation_index`); los tres normalizan al **mismo schema de
registro** que `query_ads.to_record`, y esa paridad la fija un test
(`tests/test_backends_schema.py`), no la prosa.

### Descubrimiento multi-backend y anclado (`scripts/discover.py`, #104)

**Un tema de método no se descubre con un solo buscador, y esto es medición, no preferencia.** Los
ocho trabajos canónicos de ICA/BSS están en **ADS 0/8, arXiv 0/8, OpenAlex 8/8** (`author:"Hyvarinen, A"`
en ADS devuelve dos papers sobre gotas de ácido sulfúrico: es otro Hyvärinen). `discover.py` corre
la cascada y **propone**; nunca clasifica.

- **La cascada** (`cascade`, CLI `discover.py --theme <slug>`) corre **los tres** y mergea. Cada
  backend recibe la query **en su propio idioma**, y por eso toma tres argumentos y no uno: ADS el
  Solr crudo de `query:`, arXiv la familia de términos de `aliases:` (su sintaxis no es la de ADS),
  OpenAlex el `topic:` (que no filtra por texto en absoluto). Un solo string querría decir tres
  cosas distintas. ⛔ **Declará `topic:` en `themes.yaml`**: sin él `discover` lo infiere del
  `title`, y si tu bóveda escribe los títulos en castellano la taxonomía inglesa de OpenAlex no
  matchea — no falla en silencio (lo dice en la cobertura), pero perdés el backend que más aporta
  fuera de astro. Con esto **#95 queda cerrado en el sentido que faltaba**: `search_arxiv` tiene
  llamador de producción (`discover.cascade`) y se ejerce desde `discover.py --theme`. Lo que sigue
  sin pasar —decisión abierta, no defecto— es que `ingest_theme.py` corra la cascada por su cuenta:
  hoy es un paso que el skill prescribe a mano (0b).
- **La cobertura distingue tres estados, no dos** (`print_cobertura`): corrió con N registros,
  **FALLÓ** (0 por caída — que no significa que el backend no tenga nada), y **NO CORRIÓ** con el
  motivo (`query:` sin declarar, `topic:` sin declarar). Saltear un backend en silencio deja una
  cascada de tres que corrió una, y el resultado se lee como "los tres miraron y esto es todo lo
  que hay". Ídem el conteo de citas: arXiv no lo publica, así que la columna muestra **`?`, no
  `0`** — un `0` afirma "no lo cita nadie" sobre un dato que nadie miró, y es la columna con la que
  se decide qué mandar a triage.
- **Dedup por DOI, nunca por título** (`ident`/`dedup`): lo fija la medición de `openalex.py` —el
  matcheo por título resolvió 18 de 25 casos y **2 apuntaban a otro trabajo**—. Lo que no tiene DOI
  ni arXiv id se devuelve **aparte, como no-deduplicable**; no se adivina. Cada registro acumula
  `found_in` con todos los backends que lo trajeron: la procedencia **enruta** (qué puerta se
  pregunta), la lente **decide**.
- **Rankear sin filtro estructural amplifica, no filtra** (`topics` antes de `seed`): OpenAlex
  `search:"independent component analysis blind source separation"` ordenado por citas devuelve
  143.450 works cuyo top 30 es AlphaFold, guías de cardiología y carcinoma hepatocelular —**2 de
  30** en tema—. Con `filter=topics.id:` primero, el canon entra al top 25. ⚠ El filtro es más laxo
  que su nombre: T11447 declara 55.210 works y devuelve 169.977 (matchea temas secundarios).
- **Descubrimiento ANCLADO** (`anchored_records`) — el de más apalancamiento: las **referencias de
  la mitad astro del propio tema**, rankeadas por cuántos de esos papers las citan. Es la puerta 1
  aplicada a un tema **nuevo**, donde el `citation_index` todavía no existe porque se construye
  desde el corpus ya ingestado. Medido sobre 19 papers astro de ICA: devolvió los **ocho** del
  canon sin declarar nada a mano (Hyvärinen&Oja 2000 citado por 9, Comon 1994 por 8, Jutten&Hérault
  por 6), y el consenso ordena mejor que las citas globales —*"Cocktail Parties"* tiene 67 citas y
  lo citan 7 de los 19—. Es además lo único que alcanza lo que ninguna keyword del tema alcanza: los
  papers de **PCA con ruido** (el paso de blanqueo) que la bóveda vieja tenía y el barrido por
  keyword nunca vio.
- **La cola especialista SÍ se alcanza, con el eje correcto — y el costo es triage (#107, medido).**
  Los papers de noisy-ICA que una bóveda real había curado a mano viven entre **11 y 72 citas**
  dentro de un topic de 169.977 works, así que **ningún corte por citas sobre el topic entero** los
  toca. El eje que sí los alcanza es `seed_terms`: **slice de texto por término dentro del topic**,
  que colapsa el pajar —*noisy ICA* ∩ T11447 da **579** works, no 169.977— y ahí caen en los
  puestos 28, 44, 110 y 121, o sea perfectamente al alcance. Medido sobre el corpus real: la
  recuperación pasa de **7/18 a 13/18** al activarlo, y el universo de candidatos de **776 a 2521**.
  Ése es el canje —cobertura contra costo de triage— y se decide por tema, por eso el eje es
  **opt-in** (`cascade(..., term_slices=[…])`), no porque no sirva.
  ⚠ **Y es una lección de método, no un detalle:** la primera medición dijo *"217 candidatos, 1
  recuperación, límite estructural"* — y era **artefacto de un tope de 15 filas por término que
  había puesto el propio agente**. Sacar una conclusión estructural de la salida de un truncamiento
  silencioso es el modo de falla que la regla *«no silent caps»* existe para evitar. Hoy
  `seed_terms` **avisa por término** cuántos tiene el slice contra cuántos trajo.
  Lo que queda fuera del alcance automático es chico y de una forma sola: **capítulos y actas**
  (ICANN, handbooks) y papers cuyo título/abstract no usa ninguno de los términos del tema. Ahí sí
  manda la curación a mano, y el aporte del framework es que cada entrada registre **por qué**
  entró (`extra_core` con `via`/`motivo`, o `sources`).
- **Encontrar ≠ conseguir** (`resolve_pdf`): OpenAlex identificó 8/8 y devolvió
  `best_oa_location.pdf_url = None` **8/8**. La cascada del archivo (OpenAlex → Unpaywall) **propone
  una URL y para**: no reescribe un `pending:` que declaró el usuario ni edita `sources:` —cambiar
  en silencio una fuente declarada por una que adivinó un script es cómo una cita termina apuntando
  a un documento que nadie abrió—.


### Ingest (una fuente → cascada de páginas)

**El camino del texto, de punta a punta.** Es el mapa canónico de cómo un PDF se vuelve una cita
verificable, y dónde se decide qué archivo lee cada capa:

```
1. fetch_pdf          →  raw/pdfs/<slug>/<bib>.pdf        (inmutable)

2. extract_fulltext   →  pdftotext, y TRES chequeos deterministas sobre el texto:
                           is_legible   ¿sirve?     no → OCR con tesseract
                           is_garbled   ¿correcto?  sí → header «source: ocr»
                           symbols_lost ¿completo?  sí → header «simbolos NO extraidos»
                         escribe raw/fulltext/<slug>/<bib>.txt CON el header adelante.
                         Una sola vez. Después nadie lo toca.

3. make_notes         →  lee la 1ª línea del .txt y estampa en la nota del paper:
                           fulltext_source: pdftotext | ocr | web
                           symbols_lost: true         (sólo si es cierto)

4. extractor (LLM)    →  lee el FRONTMATTER, no el .txt, para saber qué hacer:
                           ocr o symbols_lost  →  abre el PDF y cita PÁGINA
                           si no                →  lee el .txt y cita LÍNEA
                         Devuelve UNA VISTA (#188): «qué dice sobre {sujeto}», no
                         «qué dice el paper» — con `vista{sujeto,tipo,txt}` en el JSON.

5. harvest_views      →  la única compuerta que corre `is_extraction` (INV-103):
                         un JSON de verify también trae `bibcode` y también es válido.
                         Estampa la vista (fecha · txt · lente) y la sección de la nota.

6. verify-citations   →  un subagente por fuente, misma regla del paso 4.
                         Cada par verificado deja una fila con DOS hashes.
```

**Los tres chequeos del paso 2 son ejes independientes** y hacen falta los tres: `is_legible` mide
**extraíble**, `is_garbled` mide **correcto**, `symbols_lost` mide **completo**. Los dos casos que
motivaron el tercero dan garble **0.00** y pasan `is_legible` sin ruido.

**Los DOS hashes del paso 6 responden preguntas distintas** — el **ancla** hashea el bloque de la
**ficha** (se dispara si editás la nota) y el **hash de fuente** hashea el archivo que se **leyó**
(se dispara si cambia la fuente sin que nadie toque la nota). El segundo apunta al `.txt`, o al
**PDF** cuando la fuente está marcada `symbols_lost` — que es de donde salió la cita.

⚠ **El `.txt` se reescribe en TRES casos y nada más**: `--force`, upgrade automático a OCR cuando
aparece `tesseract`, y el backfill de las marcas. Por eso el hash de fuente es una alarma **rara**:
cuando suena, hay algo. Y por eso una fila anclada al PDF **no** se vence cuando su `.txt` se
re-extrae — su fuente real no se movió.

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
   ⚠ **Cómo anotar cada valor (#103).** Medido sobre una ficha real (68 pares, 16 fuentes: 54
   soportada / 11 parcial / 3 contradice / **0 no-soportada** — o sea, nada inventado), los 14
   defectos caen en seis mecanismos, y cuatro se vuelven **chequeo mecánico** si cada valor viaja con
   su línea. Por eso, al copiar un número: **el nº de línea del `.txt`** (`grep -n`), **el régimen**
   en que la fuente lo afirma (muestra, época, corte de datos, modelo), y —si la fuente lo atribuye a
   otro trabajo (*«according to X»*)— la marca **segunda mano** con la cita a X, porque el número
   **no es de esta fuente**. ⛔ **Nada de prosa comparativa en la nota de paper:** comparar dos
   papers es `inferencia` y va al `## Inventario por eje` (2b). El stub que genera `make_notes` ya
   trae la regla.
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
   (#73) dice qué operación corresponde entre dos filas.
   **La red de que el paso ocurrió (#101):** el lint reporta como backlog la ficha/concepto cuyo
   `## Inventario por eje` quedó con la **fila vacía de la plantilla** teniendo **≥2 papers
   extraídos citados** — con uno solo no hay contra qué contrastar. Usa la escotilla que la plantilla
   ya declara: *«si no hay ningún eje en disputa, borrar la sección y decirlo en el log»*, o sea
   **ausencia = declarado**, **presente-y-vacío = saltado**. Es distinto del backlog *extraído pero
   no sintetizado* (#75), que mide si el paper **llegó**, no si el contraste **ocurrió**.
2c. **Síntesis a la nota viva**, apoyada en el inventario de 2b: la ficha de la estrella
   (frontmatter propio —`activity_indicators_expected`, `methods_applied.literature`, `disputes`—,
   prosa y huecos), los conceptos/hipótesis relacionados y la matriz método×estrella. ⛔ Los campos
   de ground-truth **no se tocan**: son espejo de NEA (#70).
3. Actualizás `index.md` y appendeás a `log.md`.

> **Retro-linkeo (papers pre-existentes ↔ entidad nueva) — tres capas:** (a) una **ficha-método**
> (`concepts/methods/`) junta en su roll-up estampado (`stamp_concept_rollup`) también por
> `methods`, así que los papers ya extraídos con ese método entran sin re-taguear — pero la tabla
> **no acumula sola**: hay que re-correr `python scripts/make_notes.py <slug> --theme` (el lint
> reporta como backlog la tabla desactualizada); (b) `make_notes` mergea
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
> modo ads. Un tema off-ADS puede ser **mixto**, y su mitad astro entra por una de dos vías (la
> primera con prioridad): **`query:` poblada** → descubrimiento ADS **completo** (misma lente,
> mismas puertas de D-26, misma compuerta de triage), o **sólo `extra_core:`** → sub-cadena acotada
> a esos bibcodes. Los papers con bibcode ADS van siempre en `extra_core:`, nunca en `sources:`
> (metadata real, sin blockquote off-ADS). ⚠ Hasta #104 `query:` se ignoraba en off-ADS: el modo le
> quitaba el descubrimiento automático a la mitad del tema que ADS **sí** indexa, y la única salida
> era enumerar bibcodes a mano — medido en el ingest de ICA, la enumeración manual trajo 11 papers
> y dejó familias enteras afuera. Una fuente que **no se consigue** (paywall / escaneo / mojibake) se marca
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

### Los cuatro cuadrantes de la curación — quién decidió y por qué (#111)

Toda decisión de curación deja registro **versionado**, en los cuatro casos, y desde #111 no queda
ninguno mudo:

| | Aceptar | Descartar |
|---|---|---|
| **con bibcode ADS** | `extra_core: {bibcode, via, fecha, motivo}` (D-58) | candidato del chaining: `triage --drop … --reason` (#51) · **core del sujeto: `triage --drop-core … --reason` (#112)** |
| **fuente off-ADS** | `sources: {…, via, fecha, motivo}` (#111) | `triage --drop-source … --reason` (#81) |

⛔ **`extra_core` fuerza la ENTRADA; `--drop-core` es su simétrico y faltaba (#112).** Un paper que
la lente dice core **no se podía sacar**: `--drop` se consultaba sólo para no re-proponer candidatos
del chaining, así que sobre un core la decisión quedaba escrita y **no se aplicaba** — medido en un
tema real, 7 papers off-topic descartados con motivo seguían siendo core corrida tras corrida. Una
decisión de curación que el clasificador ignora en silencio es peor que no tomarla: queda escrita, se
lee como aplicada, y no lo está. Tres propiedades del carril, y cada una cierra un modo de falla:
- **El carril es `sujeto`, no global.** La exclusión es del par `(paper, sujeto)`: lo que se saca de
  un tema de método por polisemia —"componentes independientes" de un tensor— puede ser legítimamente
  core de otro. Un descarte global decidiría por bóvedas que no son ésta.
- **El paper excluido queda VISIBLE**, con `via: manual-drop` y el motivo en `why_excluded`. Si
  desapareciera del registro, dentro de tres meses se leería como *«la búsqueda nunca lo encontró»*.
- **Los artefactos se borran** (PDF y `.txt`): si quedan, el detector de #108 los reporta como
  extracción pagada sin nota **para siempre**, y el `.txt` sigue saliendo en los greps del corpus. La
  decisión queda igual —versionada, con motivo— así que borrar el artefacto no borra el juicio. La
  **nota** no se borra sola: puede pertenecer a otro sujeto, así que se avisa.
- **El diff de re-clasificación lo respeta** (`lens_diff_offline`, `reclass_diff`): sin eso, cada
  cambio de lente vuelve a proponer lo que el usuario ya sacó, y la categoría se vuelve ruido que se
  deja de mirar.

INV-24 sigue en pie por la misma razón que con `extra_core`: core es `f(paper, lente)` **módulo
curación declarada**, y la curación es auditable —motivo obligatorio, fechada, versionada, viaja—.
Lo que no sería auditable es que el veredicto cambiara sin que nadie firme.

El cuadrante que faltaba —la fuente off-ADS **aceptada**— es justamente el que más lo necesita: ahí
**no hay query que descubra**, así que **todo** entra por decisión de alguien, y sin el campo la
pregunta *«¿qué entró porque lo pidió el usuario, qué lo propuso el descubrimiento y qué salió de un
reporte externo?»* no tiene respuesta. Medido sobre una bóveda real: los 40 papers que tenía y una
bóveda nueva no, **entraron los 40 a mano**, y su config no permite saber cuáles pidió el usuario.

`via` es **vocabulario cerrado**: `usuario` (lo pidió) · `descubrimiento` (lo propuso la cascada de
`discover`) · `reporte` (vino de un documento externo). El lint **bloquea** la entrada sin `via` o
sin `motivo`, y el `via` fuera del vocabulario — un campo opcional no se llena.

⛔ **El carril off-ADS tiene salida hacia la ingesta** (#111): `python scripts/triage.py <slug>
--accept-source <doi> --via <via> --reason "<motivo>"` arma la entrada completa —metadata real de
OpenAlex, archivo resuelto por `resolve_pdf` o `pending: paywall`, y la procedencia— **lista para
pegar**. Sin esto el descubrimiento se cortaba en el hallazgo: proponía el paper y bajarlo quedaba
como trabajo manual, que es exactamente por qué una bóveda con búsqueda peor puede tener más papers
que una con búsqueda mejor. No escribe `themes.yaml`: la config es curada y versionada, y un script
que la edita solo convierte una decisión en un efecto colateral.

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
de sección) en vez de caerse del fan-out por no llevar `[[bibcode]]` propio, y **excluidas las secciones
que estampa la máquina** (`lib_config.SECCIONES_ESTAMPADAS`: los tres roll-ups, el apéndice de excluidos
y el propio bloque de verificación), porque una fila de `## Papers` no es una afirmación sino metadata
derivada y no hay nada que contrastar contra la fuente— y lanza **un subagente
independiente por par** que lee SÓLO ese `vault/raw/fulltext/**/<bibcode>.txt` (grounding-first, prohibido de
memoria) y devuelve **dos ejes separados** (D-59): un `veredicto` de RESPALDO —vocabulario cerrado
`soportada|no-soportada|contradice`— y, aparte, la `condición` bajo la que la fuente lo afirma.
Más **cita textual + nº de línea del `.txt`** (obligatoria; sin cita ⇒ no-soportada: la cita debe
tocar el **contenido distintivo** de la afirmación, la mera cercanía temática no alcanza).

⚠ **`parcial` se eliminó en 1.39.0 y no es cosmética.** Ese valor fusionaba dos preguntas
ortogonales —«¿la fuente respalda esto?», textual y decidible contra el `.txt`, y «¿la afirmación
está completa?», juicio de grado— y la fusión hacía que la parte dura arrastrara a la blanda.
Medido el 2026-08-25 sobre una ficha real: **dos corridas independientes del fan-out**, jueces
nuevos y ciegos, **60 pares comparados → 95 % de coincidencia (57/60)**, y **las tres divergencias
caían exactamente en el borde `soportada`↔`parcial`**, todas en la misma dirección; `contradice`
reprodujo 2/2. El umbral nunca estuvo definido, y no se puede definir: es de grado. Lo que era
`parcial` se descompone **sin pérdida** — o la fuente respalda la afirmación bajo condiciones que la
nota no dice (→ `soportada` con la `condición` poblada), o la cita no toca el contenido distintivo
(→ `no-soportada`, como el contrato ya mandaba).

El mismo experimento mostró **por qué la condición tiene que ser columna y no prosa**: pares que las
dos corridas dieron `soportada` idéntica traían condiciones **distintas** entre corridas. El juez es
estable en el eje textual y **no exhaustivo** en el de régimen, así que absorber la condición en la
prosa y no dejar rastro borra justo lo que hay que poder auditar y volver a mirar. `no-soportada` = la fuente **calla**; `contradice` = la fuente
**afirma lo contrario** → no es (sólo) cita rota: es corrección de la nota o **disputa** a taguear
(`disputes` con posiciones explícitas, #71). Cada falla se **resuelve** (bajar la afirmación
a lo que dice la fuente, reasignar la cita al bibcode correcto, marcar **`inferencia`**, o taguear la
disputa) y se deja un bloque `## Verificación de citas` en la nota — **una fila por par**, con dos
columnas de hash (**el ancla**, D-4/D-20):
`| # | Afirmación (extracto) | Fuente | Veredicto | Evidencia | Ancla | Hash fuente | Condición |`
(la celda `Hash fuente` va prefijada `txt:` / `pdf:` — ver abajo).
⚠ **La columna `Score` 0–10 se eliminó en 1.42.0**, por la misma razón que `parcial` en 1.39.0:
reintroducía un eje de **grado** cuyo umbral nunca se calibró. El campo tampoco gradúa —
FActScore etiqueta binario y los que suman un tercer valor usan vocabulario cerrado, no una
escala—, y el vocabulario de acá ya es ese ternario.
⛔ **La celda `Hash fuente` declara CONTRA QUÉ ARCHIVO se verificó ese par: `txt:<sha10>` o
`pdf:<sha10>` (#117).** Hasta 1.53.0 lo inferían el lint y el generador desde el frontmatter
—`symbols_lost` ⇒ PDF, si no el `.txt`—, y esa regla es **más angosta que la práctica**: una fuente
`fulltext_source: ocr` también se verifica contra el PDF cuando el escaneo del editor destruyó los
símbolos, y eso pasó con **3 de las 5** fuentes marcadas de un tema real → el lint hasheaba el
archivo equivocado y devolvía **17 pares «vencidos por fuente»** sobre fuentes que nadie tocó. La
decisión la toma **el verificador, par por par**, así que la declara la **fila**; el frontmatter no
puede saberlo. Una celda sin prefijo es *no consta* —que no es `txt`— y el lint la **bloquea** en
vez de adivinar: se migra con `python scripts/make_notes.py --migrate-verif-archivo`, que deduce el
archivo del **hash que la fila ya guardaba** (identificarlo por su huella, no re-inferirlo).
⛔ **Documento largo leído del `.txt`: van los DOS localizadores (#200).** Una fuente
`unidad_cita: pagina` se cita por **página** (#80) pero se lee del `.txt`, que es lo barato y lo que
el contrato manda por defecto. Las dos reglas son correctas y chocan: la fila queda con `txt:` y una
evidencia que dice `p. 271`. Las dos salidas obvias **empeoran** la fila —poner `pdf:` **miente**
sobre qué archivo se abrió y hace que el ancla vigile un archivo que nadie leyó; citar por línea
rompe #80—. La salida es escribir **los dos**: `(p. 271 / `.txt` L13931)`, que deja las dos verdades
escritas —la referencia utilizable para un humano y el ancla del archivo que se hasheó— y el
detector queda en 0 sin ablandarse. Medido: **6 de 8** filas marcadas de un concepto real eran este
caso, todas correctas.
El **ancla** es el sha256 (10 hex) del **bloque markdown normalizado** que contiene la cita
—párrafo / fila / ítem / blockquote—: reflowear la nota **no** la mueve, cambiar un número **sí**, y
una fila sin `[[bibcode]]` propio hereda el del caption hasheando **los dos** bloques. El **hash de
fuente** es el del archivo que se **leyó**, y es lo único que detecta que la fuente ya no dice lo
mismo **sin que la nota se haya tocado**: normalmente el `.txt`, y el **PDF** cuando la fuente está
marcada `symbols_lost` (#113) —porque de ahí salió la cita—. Anclar esas filas al `.txt` las marcaría
vencidas cada vez que se re-extrae, cosa que el propio framework provoca (`--force`, upgrade a OCR,
backfill de marcas), mientras la fuente real no se movió; y no vería que el PDF **sí** cambió. Los
calcula `scripts/lib_blocks.py` (`pairs_of`, `source_hash` para el `.txt`, `bytes_hash` para el PDF —
un PDF no es texto, y decodificarlo con `errors=replace` hace **colisionar** dos escaneos distintos),
el mismo código que después los chequea: no se escriben a ojo. ⛔ **Y un veredicto que exige acción NO puede quedar registrado y sin resolver (#91).** El lint leía
el bloque **sólo por su encabezado** —¿existe? ¿está fresco?— y nunca su contenido: la columna
`Veredicto` no la miraba nadie, así que una fila `no-soportada` pasaba limpia, **sentada bajo un
encabezado que se lee como garantía**. Eso es una afirmación que la bóveda hace y que su propia
fuente no respalda, o sea justo lo que la frontera dura prohíbe: hoy **bloquea**, con el mismo trato
que citar una fuente retractada. No cuentan `no verificable por extracción` (es propiedad de la
fuente, no defecto de la nota) ni la resolución anotada en la misma celda (`no-soportada→corregida`):
lo que bloquea es el veredicto **pelado**.
⛔ **Sin fila no hay dónde colgar el ancla** — colapsar las soportadas en un párrafo
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
Una bóveda afirma cosas sobre el mundo y el mundo cambia después del ingest. **Seis** cosas
caducan y se miran en **una sola pasada** —cinco desde 1.35.0, la sexta desde 1.46.0—: retracciones,
correcciones, **versiones**
(el preprint salió publicado → otro bibcode para el mismo trabajo, D-19), **snapshot web** (una
fuente web no tiene ni DOI ni bibcode: nada avisa que cambió, y como el archivo local **no** se
toca, el ancla de fuente tampoco se entera — es el modo de caducidad más silencioso),
**ground-truth** (NEA cambia valores entre releases, y el snapshot era un JSON congelado que
**nada** comparaba) y el **conteo de citas de la puerta 2** (#106, ver abajo). Si están repartidas,
se corren cinco y la sexta nunca.
⛔ **Reporta, no aplica solo**: el diff se muestra y se pregunta antes de tocar nada — un snapshot
que se actualiza solo cambia valores **bajo los pies de la prosa que ya los citó**. Lo que sí es
automático es la consecuencia offline: al cambiar un `.txt`, el **ancla de fuente** (D-20) marca
sola los pares verificados contra él. El ground-truth **no** lo cubre esa ancla (no es un `.txt`):
al aplicar, se registra `_cambios` en el JSON y el lint pide la marca `⚠desactualizado` (ver abajo). El renombre preprint→publicado **nunca** es automático
(reescribe wikilinks de toda la bóveda): se propone el comando.
La caducidad se registra **versionada** en `vault/config/registro/_red.yaml` — "cuándo se miró
afuera" es información de la bóveda, no de la máquina. Un detector que **no pudo correr** se
declara y **no** entra en `cubrio`: el registro no puede afirmar haber mirado lo que no miró.

**Fuente retractada citada en prosa (D-47):** la afirmación **no se borra** —puede ser cierta por
otra vía y borrarla destruye trabajo—: se **marca en línea** con `[[bibcode]] ⛔retractada`. Sin la
marca, el lint la localiza y **bloquea**; con la marca baja a informativa (visible, no destruida).
El símbolo es deliberado: un `(retractada)` pelado daría falso positivo con cualquier mención del
hecho en prosa.

**Ground-truth que cambió bajo la prosa (AUD-42):** el ancla de fuente (D-20) hashea
`raw/fulltext/**/*.txt` y **nunca** `raw/ground_truth/<slug>.json`, así que cuando NEA corrige un
valor entre releases, la frase que ya lo citaba queda igual de verde que antes y **ninguna fila de
verificación se entera** — es el modo de caducidad más silencioso, dentro del detector que el propio
módulo llama "el más silencioso de los cinco". Al aplicar un diff, `sweep_external` deja `_cambios`
en el JSON (qué campo, de qué a qué, cuándo) y el lint **pide la marca**: `⚠desactualizado` pegado
al valor. Mismo criterio que con una fuente retractada — la afirmación **no se borra** (puede seguir
siendo correcta), se hace visible; con la marca el hallazgo baja a informativo. Cuando actualizás la
frase de verdad, sacás la marca.

**El conteo de citas que mueve la puerta 2 (#106 / INV-104).** La puerta 2 de D-26 admite un paper
como core por `citation_count`. Ese número **es** metadata del paper —vive en el frontmatter, así
que INV-24 se sostiene y el veredicto sigue siendo re-derivable offline—, pero es la única metadata
que **cambia sola**: la función es estable y su entrada deriva, de modo que un paper puede volverse
core sin que nadie edite ni el paper ni la regla. Era la única dependencia del mundo sin detector.
⛔ La regla bien enunciada **no** es *"core no puede cambiar"* —sería falsa: un paper que juntó 5000
citas desde que lo miraste **debería** volverse core— sino **"todo cambio de veredicto es visible y
fechado"**, que es la misma doctrina de las otras cinco caducidades. Se vigila por los dos lados,
cada uno con su alcance declarado: **`lib_config.puerta2_cruces`** (offline, lo reporta el lint)
compara el umbral vigente de `themes.yaml` contra el que el registro guardó en `lente.regla_tema`
—ve *"editaste el umbral"*— y **`sweep_external.sweep_citas`** re-consulta los conteos —ve *"el
mundo se movió"*—. Ninguno aplica nada. El umbral se persiste con `query_ads.lens_used(meta)`, y se
compara con `in` y no por truthiness: un `fundacional_min_citas: 0` (la puerta abre para todos) es
una decisión y no puede leerse igual que no declararlo (la puerta **no** abre), que es la misma
distinción que D-26 protege al no ponerle default.

Éstas son las **tres únicas marcas en línea** del sistema: `(inferencia de [[bibcode]])`,
`[[bibcode]] ⛔retractada` y `<valor> ⚠desactualizado`.

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
ninguna nota → no acumula en el roll-up; typo típico `shift-vs-shape` vs `shift_vs_shape`) —su hermano **`methods` sin página destino** es
**backlog**, no bloqueante: ver arriba— y
**`disputes` con la `ref` de una posición sin paper destino** (el bibcode que sostiene esa posición
no existe como nota → la disputa no es trazable), **`disputes` mal formadas** (#71: sin `field`, con
menos de dos posiciones —con una sola es una afirmación, no un desacuerdo—, con una posición que no
dice quién la sostiene, o con un `source` fuera del vocabulario), **`disputes` en el schema viejo**
(`planets[].disputes[]`, que el lint ya no lee: migrar), **nota de paper con `topics:`**
(el campo pre-R-5 que quedó sin lector — el vigente es `facets:`), **registro con
`busqueda:`** (mapa, schema pre-D-28: hoy es `busquedas:`, lista) y
**`role` fuera del vocabulario** (`fundacional|aplicacion|arbitro`: un typo deja el rol mudo para el
contraste cross-paper, mismo modo de falla que un `thesis_links` sin destino), **la extracción que no
dice desde qué sujeto se leyó** (#188: `## Extracción (LLM)` sin `vistas[]` — schema viejo) y la
**incoherencia `vistas[]` ↔ cuerpo** en los dos sentidos (vista declarada sin su `## Vista — <sujeto>`,
que afirma una lectura que no está; y sección sin declarar, que no dice de qué `.txt` ni con qué lente
salió) y el **juicio de triage
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
se le extrajeron (un corrigendum cambia justamente ese número). El **reclamo sin vista** (#188: un sujeto que reclama el paper y desde el cual nadie lo leyó) es **backlog** —la vista del sujeto que sólo aporta al roll-up es opcional, el silencio no—, y baja a **informativo** cuando está declarado con `no_vista` y su motivo; su hermana, la **vista sin `fecha`** (declarada por el stub y nunca leída), también. Sin esas dos, sembrar la vista al crear el stub apagaría el hallazgo del sujeto que la sembró y el silencio volvería a leerse como «se miró y no hay nada». El **extraído pero no sintetizado** (#75: un paper con `methods` poblado —o sea que ya pagó el paso
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
la **cobertura de verificación** (una nota —ficha, query o concepto— **con** citas
**en prosa** —los `[[bibcode]]` de las secciones estampadas **no** son citas: son metadata
derivada, y `verify-citations` no tiene qué contrastar contra la fuente— y **sin**
bloque `## Verificación de citas` → nunca pasó por `verify-citations`: correr el skill) tiene desde
1.36.0 las **dos severidades de R-1**, igual que los pares vencidos: backlog en la pasada periódica,
**bloqueante con `--cierre`**. D-5 dice que la nota **nace 100% verificada**, así que "tiene citas y
ningún bloque" no es deuda vieja: es la operación que la tocó sin terminar — y el detector que sí
contaba para el exit (`stale_pairs`) sólo se puebla con notas que **ya** tienen bloque, así que la
nota nunca verificada se escapaba por abajo (INV-79).
Los **pares de verificación vencidos** (D-4/D-20) son la medida fina de lo mismo, por **par** y no
por archivo: *sin verificar* (hay una afirmación citada sin fila), *vencido por edición* (el ancla
ya no coincide), *vencido por fuente* (el `.txt` cambió), *fila huérfana* (la afirmación se borró).
**Dos severidades, un solo detector (R-1):** sin flag es la **pasada periódica** y reporta como
backlog; con **`python scripts/lint.py --cierre`** cuentan para el exit — es el paso de cierre de
toda operación que tocó la nota, donde un par sin verificar significa que **no terminaste**. Los
skills de cierre lo invocan con el flag; la pasada de higiene de `maintain`, sin él.
⛔ **Y el flag toma el SUJETO: `python scripts/lint.py --cierre <slug>` (#121).** El razonamiento de
R-1 es sobre lo que **esa operación tocó**, y aplicado a la bóveda entera no se podía cumplir: una
deuda vieja en **otro** sujeto —147 citas sin bloque en una estrella que este ingest no miró— dejaba
el gate en rojo antes de empezar y en rojo al terminar. Medido al cerrar un tema real: hubo que
revisar las categorías **a ojo, una por una**, para confirmar que lo del slug nuevo estaba en cero y
que el único bloqueante era ajeno — un gate que se audita a mano dejó de ser un gate. Con el slug,
el **alcance** son las notas del sujeto: su ficha/concepto y sus papers, por las tres vías (la nota
se llama por `concept`, que no es el slug; los papers con artefacto bajo `raw/*/<slug>/`; y los
**retro-linkeados**, que sólo se ven por `stars`/`thesis_links`/`methods` en el frontmatter).
⚠ Dos recortes deliberados, cada uno contra un modo de falla: **el reporte NO se acota** (la deuda
ajena se lista entera, marcada *«no frena»* — si se escondiera, acotar el exit la volvería
invisible), y **el alcance acota SÓLO la severidad de cierre**: un bloqueante sigue contando venga
de donde venga, porque si no `--cierre <slug>` sería un gate **más débil** que un `lint` pelado. Un
slug inexistente **no** da un verde: se rehúsa (exit 2), porque acotar a una entidad que no existe
daría cero hallazgos en alcance sobre una bóveda con deuda. Sin argumento, el comportamiento
histórico (pasada de cierre global, deliberada). Aparte y
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
Los **alias que SIMBAD conoce y `stars.yaml` no declara** (#82) son **backlog**: un alias que falta
es un paper que nunca aparece **en silencio**, y degrada los **tres** mecanismos de recall a la vez
—query directa, barrido `--sweep` y rescate por glifo—. Se persisten en `_simbad_aliases` del
ground-truth con la misma llamada que ya se hace, así que la propuesta sale de **una fuente** y no de
la memoria del LLM. ⛔ Persistir **no es adoptar**: SIMBAD devuelve identificadores inútiles para
buscar texto (`Gaia DR3 …`, `2MASS J…`) junto a los que sirven (`HD`, `HIP`, `GJ`), así que cuáles
entran es curación y se versiona. Su hermano de siempre, el alias **de más** (declarado y que resuelve
a otro objeto), sigue siendo WARN.
El **barrido full-text sin rastro** (#88: el registro del sujeto no tiene `barridos`) es **backlog**:
`--sweep` era un preview de stdout y, cuando la terminal scrollea, no quedaba nada — el mismo modo de
falla que #55 cerró para el triage. Pesa porque el barrido es **el único camino** para el punto ciego
de la query directa: los surveys de muestra grande que **tabulan** la estrella sin nombrarla en el
abstract y que tampoco están en el grafo de citas. Hoy `query_ads.py <slug> --sweep` appendea a
`barridos: []` (acumulativo como `busquedas`) **también cuando no encontró nada** — un barrido vacío
dice que la red se tendió y volvió sin nada, que no es lo mismo que no haberlo corrido.
El **corpus truncado** (un `build/<slug>/ads.json` con `truncated` seteado → la query directa trajo
menos papers de los que ADS reporta) es **backlog** — `query_ads` persiste la marca (default
`--rows 2000`, ≈ el máximo de una request; re-ingestar con `--rows` mayor para cubrir el resto). Lo
que falta ahí es **el medio**, no la cola: al truncar, `query_ads` corre una **segunda pasada con la
misma query ordenada por fecha** (#79) y la marca guarda en `truncated.recent` cuántos rescató, así
que lo reciente —lo que el orden por citas esconde por construcción— ya está cubierto; ídem el
**rescate por glifo incompleto** (`truncated_glyph`, marca hermana: el superset de la constelación
del rescate #28 se cortó por citas **antes** del filtro client-side, que es donde vive la señal →
pueden faltar papers con lookalike). Los **campos incompletos** son **backlog** y no bloquean; hoy son **diez** (el conteo es el de
los sitios que pueblan `incomplete` en `lint.py` — no el de la lista histórica; ⚠ decía *siete* y
enumeraba ocho mientras el código tenía diez: tres valores para un hecho que decide un `grep`, #147):
`P_rot` sin documentar en la prosa (el frontmatter nulo **no** es hallazgo desde #70),
`activity_indicators_expected` vacío, planeta del frontmatter no discutido en la prosa, paper core
sin `methods` (sin extraer), paper extraído sin `role`, **`unidad_cita` de documento largo sin
`alcance`** (#80: sin él un recorte deliberado se lee como omisión), **paper relevante sin fuente en
disco** (ni `.txt` ni PDF, #90: es core y no hay qué leer), y **ficha sin
su `raw/ground_truth/<slug>.json`** (el barrido del espejo #70 lo maneja el JSON, así que una ficha
sin archivo no la mira **nadie**: se le pueden inventar `teff_K`/`P_rot_days`/planetas enteros con
el lint en verde — es backlog y no bloqueante porque es "la garantía no corrió acá", no "hay una
violación"), un **`raw/fulltext/<slug>/<clave>.txt` sin su nota en `papers/`** (#108: extracción ya
pagada —descarga, PDF, `pdftotext`— que **no alcanza ningún roll-up ni ninguna síntesis**, porque
ni siquiera hay nota. Es la misma familia que INV-94 un escalón más abajo: allá la nota existe y no
la alcanza nadie, acá no hay nota. El mecanismo es alcanzable sin salirse de lo documentado:
**angostar la `query` de un tema** saca esos registros de `build/<slug>/ads.json`, `make_notes` deja
de escribirles nota y el PDF y el `.txt` quedan en disco — medido en una bóveda real, 10 de 30 `.txt`
de un tema. Se cierra re-corriendo `make_notes.py --theme <slug>` o borrando el artefacto colgado),
y su **hermano simétrico**: un `raw/ground_truth/<slug>.json` **sin** su
`stars/<slug>.md`, que es un renombre a medias o una ficha borrada sin limpiar — el espejo no tiene
con qué comparar y nadie avisa que ese ground-truth quedó colgado. Revisar
El **recorte de lectura sin declarar** (core sin extraer y sin `extraccion:` en el registro)
es **backlog**; se cierra con `python scripts/triage.py <slug> --extraccion todos|subconjunto`
(el canal quedó cableado el 2026-08-24: `triage.py` → `cfg.save_extraccion`, y el skill
`ingest-star` lo nombra en su paso 3). Revisar
además a mano: claims stale y conceptos referidos sin página. Si faltan datos, abrir queries para
imputar (web/ADS).

## Seis reglas de método (por qué existen las redes de abajo)

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
3. **Un test verde recién escrito no cuenta hasta que lo viste morir — POR LA RAZÓN QUE PRUEBA.**
   La primera mitad es necesaria y **no alcanza** (#202): un test puede fallar por algo que no tiene
   nada que ver con lo que prueba, y ese fallo se lee igual de tranquilizador que el bueno. La
   pregunta no es *«¿falló?»* sino ***«¿murió por la línea que estoy probando?»***, y se contesta
   mirando **el mensaje del fallo**, no el rojo.
   Medido dos veces en la misma tanda (2026-08-27, #196/#197), una por cada mitad del modo de falla:
   - **murió por el motivo equivocado**: el test de #196 fallaba porque el setup no había creado
     ninguna nota de paper —universo vacío—, no por el defecto. Arreglado el setup, **pasaba sin el
     fix**: nunca había probado nada.
   - **verde y atravesable**: dos de los tres tests de `apply_fixes.py` sobrevivieron a mutar la
     guarda que decían proteger. El de colisión afirmaba `collisions no vacío` + `applied == 0` +
     archivo intacto — pero sin la guarda el flujo cae igual en «un `viejo` no resuelve», que
     **también** aborta la escritura. Lo que distingue a la guarda es que detecta **antes de
     intentar**: faltaba `not r.failed`. El de todo-o-nada usaba un caso con **un solo** fix
     fallando, donde no hay nada aplicado que perder.
   La forma barata de contestar la pregunta es la **mutación dirigida** (#204, ~0,44 s por
   mutación): romper cada guarda que el módulo promete y correr su archivo de tests —
   `python tools/mutar.py --dirigida scripts/<módulo>.py`. Un test que sobrevive a eso no prueba lo
   que dice su nombre. Por eso el gate de mutación es la red #1 y no un extra.
4. **Un mapa que atribuye mal es peor que uno vacío**: el vacío se ve, la atribución falsa se lee
   como verdad. Vale para `docs/trazabilidad.md`, para las filas de `docs/contrato.md` y para
   cualquier tabla que este repo estampe.
5. **Cuando dos mediciones no reconcilian y no se puede re-medir, se DECLARA la discrepancia** en
   vez de elegir un número. Elegir en silencio es cómo un documento empieza a mentir.

6. **Fan-out para LEER, aplicador serial para ESCRIBIR, barrera antes de CONSUMIR.** El
   aislamiento de un fan-out es lo que hace fuerte a un chequeo —57 verificadores que ven un solo
   `.txt`, sin memoria y sin los otros papers— y no se toca; lo que no escala es el lado de
   **escritura**. Medido en una sola corrida de 75 correcciones: dos correctores que redactan el
   **mismo bloque** lo corrompen al aplicarse en cadena (#197), y derivar trabajo de una etapa que
   **todavía corre** deja hallazgos que no mira nadie (#199: 4 de 201, dos de ellos defectos reales).
   Del otro lado, la redundancia paga: las capas independientes se corrigieron entre sí —un triage
   afirmó que dos cifras reconciliaban por tamaño de bin y el corrector, al abrir la fuente, encontró
   que **las dos** lo traían—. La regla no es «paralelizar menos»: es **un solo escritor, y una
   barrera antes de que algo consuma resultados**.

Corolario que las cruza a todas: **una promesa que el sistema dejó de cumplir en silencio es peor
que una que nunca hizo.** Si al tocar algo se rompe una promesa declarada —un presupuesto de
tiempo, una cobertura, un 1:1—, eso **se anota**, aunque no se arregle en el momento.

## Convención de idioma del código (desde 2026-08-24)

**Archivos, nombres de funciones, docstrings y comentarios NUEVOS en inglés.** La prosa de la
documentación (`CLAUDE.md`, `README.md`, `docs/`, los `SKILL.md`) y la de la bóveda siguen en
castellano. **Sin retrofit**: lo que ya está escrito no se renombra — la regla es sobre lo nuevo.

⚠ **Hasta #156 esta convención no vivía en ningún documento versionado** (sólo en la bitácora
interna, que está gitignored) **y no la vigilaba ningún gate**. El resultado, medido: de 237
funciones nuevas desde el 2026-08-24, **30** tienen nombre en castellano, y `scripts/discover.py`
—creado el 2026-08-26— nació con 6 docstrings en castellano de 17. *Una promesa que el sistema dejó
de cumplir en silencio es peor que una que nunca hizo* (corolario de las seis reglas de método): o
la regla tiene casa y red, o no es una regla.

La red es `tests/test_idioma_codigo.py` con ratchet en `tools/idioma-ratchet.yaml`: cuenta los
símbolos en castellano de `scripts/` + `tools/` (hoy **45** sobre el árbol entero — el número lo da
`simbolos_en_castellano()`, no esta prosa) y **sólo puede
bajar**; además, un nombre que no esté en la lista `conocidos` pone el test en rojo **aunque el
total no suba**, que es lo que impide que la deuda rote. Los 45 son deuda declarada, no un rojo —
exigir cero sería rojo permanente, y un rojo permanente se deja de mirar. Renombrarlos rompería
marcas `@inv` y los punteros de `docs/trazabilidad.md` sin arreglar nada.

## Al escribir código: las siete redes (regla permanente)

Toda función nueva de `scripts/` pasa por esto **antes de cerrar el issue**; la 6 rige
también para los scripts de una sola operación. Detalle y ratchets en
`tests/README.md`; el resumen operativo:

1. **Mutación** — `python tools/mutar.py --diff`: romper cada función y exigir que **algún test
   muera**. Es lo único que distingue "el test pasa" de "el test **podría** fallar". Trabaja sobre
   una copia del repo, nunca sobre el árbol real.
   ⛔ **Cadencia (decidida con el usuario, 2026-08-27): el BARRIDO no se corre salvo pedido
   EXPLÍCITO. La mutación DIRIGIDA sí, y es un paso al escribir una función con guardas (#204).**
   Son dos operaciones con el mismo nombre y otro costo, y hasta el 2026-08-28 la prohibición no
   las distinguía. La dirigida —`python tools/mutar.py --dirigida scripts/<módulo>.py
   [--solo f,g]`— muta **un** módulo y corre **sólo su archivo de tests**, sin escalar: **~0,44 s
   por mutación** (medido el 2026-08-28, copia del repo incluida: 17 mutaciones de `triage.py` en
   7,4 s; 4 de `apply_fixes.py` en 1,8 s) contra los ~8 s por mutante que costaba el barrido de una
   etapa sobre un módulo del final del alfabeto. En la tanda #196/#197 pagó de inmediato: tres mutaciones sobre las tres
   guardas de `apply_fixes.py` dejaron **dos tests falsos** al descubierto.
   ⚠ Como no escala, puede marcar SOBREVIVE algo que otro archivo de tests sí mata:
   **sobre-reporta sobrevivientes y nunca da falso limpio**, que es la dirección segura. No toca el
   ratchet y no reemplaza al barrido. Y **rehúsa** —no degrada a la corrida cara— si el módulo no
   tiene `tests/test_<módulo>.py` o no tiene ninguna función mutable: cero mutaciones no es
   «murieron todas» (D-43; el bug estaba en la primera versión de este modo, con `ingest_star.py`).
   Motivo de la prohibición del barrido: tardaba **~1 h** (416 funciones × la suite entera, secuencial), y con
   `-x` el orden alfabético de pytest hace que mutar `triage.py` pague casi toda la suite antes de
   llegar al test que lo mata. El costo dominante es buscar el test asesino en el lugar equivocado.
   **El gate no corre solo** — ni al cerrar un issue, ni al cerrar una tanda.
   ✅ **Desde #187 el barrido corre en DOS ETAPAS** (2026-08-28): primero `tests/test_<módulo>.py`;
   **sólo los sobrevivientes** pagan la suite completa. Una muerte en la etapa 1 es una muerte, así
   que el conjunto de sobrevivientes **no cambia**; sin archivo 1:1 la etapa se saltea (no se
   aproxima). Medido, con los mismos sobrevivientes en las dos ramas: `triage.py` (17 funciones)
   **143,6 s → 8,0 s**; `apply_fixes.py` (5, la primera del alfabeto) 4,5 s → 1,7 s — la ganancia
   **es** la distancia al arranque del alfabeto. ⚠ El `~1 h → ~12 min` sobre `--todo` sigue **sin
   medir**: no se extrapola desde dos módulos, así que la cadencia de arriba **no cambia** todavía.
   ⚠ **Cadencia anterior (2026-08-26), que la de arriba suspende:** un **lote** hecho con roles separados
   —spec → tests → implementación, agentes distintos, `docs/playbook-spec-tests.md`— **no necesita
   este gate en su tanda**: ahí el defecto se previene en vez de detectarse, que es lo que la
   mutación audita. Queda obligatorio para los lotes que **no** usaron separación de roles, para
   toda función nueva escrita sin spec, y como pasada periódica completa (`--todo --ratchet`). El
   canje es real: la mutación tardó ~40 min sobre un diff que tocaba `make_notes.py`.
2. **Schema compartido** — si N módulos prometen la misma forma, se prueba **una vez parametrizada**
   (`tests/test_backends_schema.py`), no con prosa en N docstrings.
3. **Doble vs real** — un doble de test no se escribe a ojo: o deriva de la función real, o hay un
   test que fija que coinciden. El bug más caro de la Tanda 7 vivió exactamente en esa diferencia.
4. **Nadie sin ejecutar** — `pytest tests/poblada/test_cobertura.py -m poblada` (~11 s): una función
   que la suite nunca corre no está "mal probada", está **sin mirar**.
5. **La doc es ejecutable** — `tests/test_docs_ejecutables.py`: todo test, script y
   archivo de config que la documentación nombra tiene que existir, y todo
   comando que invoca un skill tiene que compilar.

6. **Corré dos veces y hasheá** — la regla vale para **todo script que escriba en `vault/`**, no
   sólo para los de `scripts/`: la idempotencia es invariante del framework («la cadena es
   idempotente: refrescar es seguro»), y un script de una sola operación escribe en la bóveda
   exactamente igual que uno versionado. El chequeo cuesta una línea:
   ```bash
   H=$(find vault -name '*.md' -exec md5sum {} + | sort | md5sum); <el comando>; \
     [ "$H" = "$(find vault -name '*.md' -exec md5sum {} + | sort | md5sum)" ] && echo IDEMPOTENTE
   ```
   ⚠ **La idempotencia es sobre CONTENIDO, no sobre la bitácora (#105).** El chequeo hashea
   `vault/**/*.md` y **no** `vault/config/registro/`, y eso es deliberado: D-28 hace que
   `busquedas` **crezca** en cada corrida —una entrada por vez que miraste, con `n_nuevos` vs
   `n_ya_estaban`—, igual que `_red.yaml` registra cuándo se miró afuera. Un registro que no
   creciera perdería justamente la información que D-28 vino a guardar. Las dos reglas conviven
   porque miden cosas distintas: **la nota no puede cambiar si no cambió lo que afirma; el registro
   tiene que crecer aunque no cambie nada.** Si alguna vez el chequeo da rojo por una línea
   estampada, el defecto está en la línea —estaba publicando bitácora como si fuera contenido, que
   es lo que pasaba con el contador de búsquedas— y no en la regla.
   Medido el 2026-08-25: un generador de notas de una sola operación pisó, en su **segunda**
   corrida, la prosa escrita a mano de un paper compartido entre dos estrellas. El bloque propio va
   entre centinelas (`<!-- almagesto:… -->`) y lo de afuera no se toca — que es lo que
   `make_notes._reemplazar_seccion` ya hacía y no se usó.

7. **Idioma** — `pytest tests/test_idioma_codigo.py`: un símbolo **nuevo** con nombre en castellano
   pone el test en rojo, aunque el total no suba. Ver *Convención de idioma del código* arriba: la
   regla existía desde el 2026-08-24 y **nadie la vigilaba**, con 46 símbolos de resultado (hoy 45).

Las 2, 5 y 7 corren solas en tier 0. El motivo de la regla: en la sesión que la produjo, **los bugs
los encontraron agentes leyendo el código, no la suite** — y cada hallazgo era decidible, o sea que
podría haber sido un assert.

⚠ **La red que no mira el código nuevo no es una red (INV-101).** El gate de mutación seleccionaba
con `git diff --name-only HEAD`, que **no lista untracked**, así que un archivo recién creado en
`scripts/` —el caso exacto que la regla nombra— salía en verde sin haberse mutado. Vale como
recordatorio general: antes de creer un gate, confirmá **sobre qué corrió**.

## Token / secretos
El token ADS va en `vault/config/ads_dev_key` (**gitignored** — nunca se commitea) o en la variable de
entorno `ADS_DEV_KEY`. Token gratis en <https://ui.adsabs.harvard.edu/user/settings/token>.
`build/` y `outputs/` gitignored. PDFs por git-lfs (`vault/raw/pdfs/**/*.pdf`). El resto de
`vault/config/` **sí se commitea**, incluido `registro/<slug>.yaml` (es el punto: el juicio de
curación y el registro de búsqueda tienen que viajar).
