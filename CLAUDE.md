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

> **La cabecera de una ficha/concepto lleva una línea `> _Estado — …_`** con **tres fechas** que
> avanzan por separado y pueden divergir sin que ninguna mienta (D-12): **búsqueda** (última corrida
> + universo acumulado + escotillas), **síntesis** (cuándo se destiló el sujeto a la prosa — se
> **declara**, `cfg.save_sintesis` / `triage.py --sintesis`, porque no se puede derivar: `git` fecha
> el ARCHIVO, así que una cirugía de cabecera contaría igual que reescribir el resumen) y
> **verificación** (fecha del bloque, con la salvedad fija *"vigencia por par: la dicen las anclas"*
> — sin ella la fecha se lee como "todo verificado a esta fecha", que es lo que el ancla corrige).
> Con una sola fecha, refrescar el corpus hacía parecer re-verificado lo que nadie volvió a chequear
> —y re-sintetizado lo que nadie volvió a escribir (INV-82).

> **Al iniciar sesión, leé `vault/STATUS.md` (estado + próximos pasos) y `vault/wiki/log.md` (historial
> reciente) para orientarte.** *(Si estás en el repo **template** `Almagesto` —donde esos dos son la
> **semilla** que una instancia nueva clona, no un estado— el handoff del desarrollo del framework
> vive en `docs/internal/HANDOFF.md`, que no se versiona.)* ⛔ **`index.md` se ESTAMPA
> (`python scripts/make_notes.py --restamp-index`, #237), no se edita a mano.** Era el único
> artefacto **100 % Dataview** —lo que #60 prohibió para los roll-ups, y con más fuerza acá: el
> catálogo es lo primero que un agente abre, y un bloque ```dataview``` le muestra **la query, no
> sus resultados**, con el plugin sin versionar—. El efecto medido: el bookkeeping de los skills
> mandaba *«agregar la estrella a `index.md`»* sobre un archivo **sin una sola línea estática**, así
> que no se podía cumplir. Hoy las tres tablas se materializan por verdad de frontmatter, el
> Dataview queda **debajo** como comodidad, y el lint reporta el índice desactualizado **nombrando los
> stems** (mismo criterio que D-10 para `## Papers`). La "memoria" del proyecto es in-repo: este `CLAUDE.md` + `vault/STATUS.md`
> + `vault/wiki/log.md` + `vault/wiki/index.md`. No depender de la memoria local de Claude (`~/.claude/...`),
> que no viaja entre máquinas. Tras cada operación, actualizá `index.md`, appendeá a `log.md`
> (entrada `## AAAA-MM-DD — <op>: <título>` + bullets — greppable por fecha) y, si cambió el estado,
> `vault/STATUS.md`. ⛔ **El `STATUS.md` se REESCRIBE, no se appendea (#302)** —lo histórico y el
> handoff por corte de contexto van al `log`, con su fecha—: es la pieza de memoria que no tenía
> política declarada y se volvió bitácora (medido: 537 líneas, 12 encabezados fechados y **cuatro**
> listas de próximos pasos, una contradiciendo un estado posterior del mismo archivo). Queda el
> estado vigente + **una** lista de próximos pasos; el lint levanta el apilamiento y su techo.

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
`vault/.obsidian/`, `README.md`, `requirements.txt`. El
framework es **una sola implementación**: los cambios se hacen en el repo template `Almagesto`
(issue/PR o parche), se pushean, y se traen con el merge de abajo. Editarlos en la instancia
**da conflictos** en el próximo merge. En la instancia sólo se edita **contenido** (`vault/wiki/`, `vault/raw/`) y los
**archivos de instancia** protegidos por `merge=ours` (`vault/config/objective.yaml`, `vault/config/stars.yaml`,
`vault/config/themes.yaml`, `vault/STATUS.md`, `vault/wiki/index.md`, `vault/wiki/log.md`,
`vault/wiki/matrices/method_star.md`). ⛔ **El driver de `merge=ours` se pasa POR COMANDO y NO se registra en el
clon (#390):** `git -c merge.ours.driver=true merge upstream/main`. Es una regla por **path** y git
no puede condicionarla por remoto, así que el driver que protege contra `upstream` **descarta en
silencio** lo que traiga `origin` —la otra máquina—; sin registrarlo, ese merge conflictúa y las dos
versiones quedan visibles. El lint **bloquea** al clon que lo tiene puesto.
**Si una operación revela una mejora
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

**Por qué, y no es paranoia — está medido.** La prosa de una ficha es **capa LLM** y
`verify-citations` es **juicio de LLM, no prueba**. Sobre un concepto ya extraído y sintetizado el
fan-out encontró **13 defectos**, y **siete eran de atribución** —el dato de un paper adjudicado a
otro—: ninguno visible desde la ficha, se ven **sólo** abriendo la fuente.

**Cómo (#205):** abrí el **PDF** (`vault/raw/pdfs/**/<bibcode>.pdf`) y citá **página**. El `.txt`
sirve para *ubicar* con `grep -n`, no para citar: es el índice de búsqueda y pierde fórmulas,
tablas-imagen y figuras **sin avisar** —medido, incluso en papers con todos los chequeos en verde—,
así que un `grep` vacío **no** significa que la ficha esté mal. Con `pdf_source: eprint` el PDF es
el preprint: una discrepancia numérica es candidata a diferencia de versión, no a error de la ficha.

Si al validar encontrás una discrepancia, **no la arregles en silencio de tu lado**: es un hallazgo
de la bóveda — reportalo, o el próximo consumidor tropieza con lo mismo.

**Test de admisión (aplicá a TODA línea de `vault/wiki/`):** *¿esto sale de una fuente
(`vault/raw/`) y lo puedo respaldar con un `[[bibcode]]`, o es una conclusión derivada de fuentes
citadas?* Si la respuesta es **no → no entra al vault**, sin excepciones — ni por útil ni por obvio.

**Prohibido inlinear en `vault/wiki/` (no es bibliografía):** parámetros, perillas o **dials** de un
generador/pipeline; nombres de variables o estructura de código; reparametrizaciones y **decisiones de
diseño** de una implementación; recetas operativas de "cómo correr" que no sean un hecho citable.
**Sí es citable (entra):** resultados publicados —**incluidos papers de simulación**: rangos
medidos, mecanismos, signos, escalas temporales, fórmulas de la fuente. La distinción es
**publicado-y-citable vs implementación de código**, no "simulación sí/no". **Si detectás
contaminación**, sacala de `vault/wiki/` y marcalo en el `log`.

**Punteros a otros repos (prosa no, frontmatter estructural sí):** lo prohibido es el puntero
downstream **en prosa / como motivación** ("para qué sirve en <repo consumidor>") — eso describe al
consumidor y rompe el flujo unidireccional. Los **campos estructurales** de `stars/` —`data_local`,
`methods_applied.ours`— **sí** pueden apuntar afuera: son contrato máquina-legible, no motivación. **Migrando una instancia heredada**:
borrar de notas de método/queries los comentarios "para qué sirve en <downstream>" y la parte
decisión-downstream de las disputas; `data_local`, `methods_applied.ours` y `log.md` se quedan.

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

> **Dónde está el "por qué".** Cada regla de acá lleva su `(#N)` o `(D-N)`: el issue público
> (`github.com/nicklessagus/Almagesto/issues`) tiene el caso que la produjo y la medición;
> `docs/contrato.md` tiene el invariante; `docs/mediciones.md`, la evidencia con su corpus y su
> fecha. Este archivo lleva **la regla y su consecuencia**, que es lo que hay que saber antes de
> escribir una nota. ⛔ **El issue se CREA antes de escribir su número (#292):** el `(#N)` escrito
> antes de que el issue exista se lo lleva el issue siguiente, y la trazabilidad pasa de vacía a
> **mal atribuida** —el caso que la regla de método nº 4 llama peor—; pasó en vivo. La red es
> `tests/test_docs_ejecutables.py::test_todo_numero_de_issue_que_el_repo_cita_existe` contra la
> caché versionada `tools/issues.json` (`python tools/refresh_issues.py` al cerrar cada tanda).

### stars/

Campos: `name, slug, aliases, aliases_descartados, simbad_id, spectral_type, teff_K, dist_pc,
P_rot_days, mass_msun, activity_indicators_expected, planets[], disputes[], data_local,
methods_applied{literature,ours}`. Cada `planets[]` lleva `letter, P_days, K_ms, e, mass_earth,
status` (de ground-truth NEA; `mass_earth` RV-only ≈ $m\sin i$). Los desacuerdos van en `disputes` a
**nivel nota**, no dentro de `planets[]`.

⛔ **Espejo con AUTORIDAD POR CAMPO (#70 + D-1) — cada campo vale lo que dice SU autoridad o NADA.**
`spectral_type` ← **SIMBAD**; `teff_K`, `dist_pc`, `P_rot_days`, `mass_msun` (#272 — es el
factor que convierte $K$ en $m\sin i$, así que sin él la ficha declara un hueco de arbitraje sobre
un valor que su propia autoridad ya tiene) y los cinco campos de cada `planets[]` ← **NEA**
(pscomppars). La cabecera nombra *(sólo en el JSON)* el campo que el frontmatter no publica. Si la autoridad declarada calla, el campo queda `null` **aunque
la otra tenga el dato**: un valor cuya procedencia depende de quién contestó primero no es
auditable. El JSON registra en `_autoridad` quién contestó cada campo y en `_otras_autoridades` lo
que la otra decía y no se adoptó (D-2); el desacuerdo se expresa como `disputes` con `source: nea` /
`source: simbad`. Los `null` de NEA son el caso **normal** (`pl_rvamp` y `pl_orbeccen` faltan
seguido), **no se rellenan con literatura**: un número extraído por un LLM ahí queda indistinguible
del de NEA y borra la distinción auditable↔síntesis que el consumidor usa; además, adoptar un valor
cuando las fuentes discrepan es decidir por quien consume (regla #0). El valor de literatura va **al
cuerpo, citado `[[bibcode]]`**; si discrepa de NEA es una `disputes[]`; si es lectura propia va
marcado **`inferencia`**. Lo vigila el lint, campo por campo.

**La ficha lo publica arriba**, en el blockquote de cabecera: una línea `> _Ground-truth — …_` con
qué autoridad respondió cada campo, la fecha del snapshot, **qué campos volvieron vacíos** (distinto
de "nadie preguntó", que en el frontmatter se ve igual) y el puntero al JSON. Se estampa sola
(`make_notes.py <slug>`, idempotente) porque **el artefacto es lo que viaja**: una ficha copiada o
leída por un agente llega sin la doc al lado. El blockquote lleva además un **disclaimer ⚠ de
capa-LLM** (la prosa es síntesis a revisar; el frontmatter es auditable) — va en blockquote, así el
lint lo exime del scan de fuga.

El cuerpo trae **`## Inventario por eje`** (el paso de contraste), **`## Huecos`** (qué falta para
que la ficha alcance sola), la sección estampada **`## Indicadores de actividad esperados`** —el
puente al concepto que explica cada uno, resuelto por alias y sin la glosa entre paréntesis (#250)—
y el apéndice **`## Excluidos por el filtro`** (los no-core, top por citas con link a ADS).

⛔ **Un `## Huecos` —de ficha o de concepto— declara su ALCANCE, igual que una hipótesis (D-34,
#342):** `> Alcance <fecha> · temas: […] + estrellas: […] · N papers`, **dentro de la sección**. Un
hueco es una afirmación **negativa** y por construcción no lleva `[[bibcode]]`, así que no la mira
ninguna capa —`verify-citations` va claim↔su fuente y `find-contradictions` claim↔claim, y las dos
parten de una cita—: medido, **6 huecos falsos** en dos temas, los seis cazados de casualidad. El
alcance vuelve *acotada verdadera* una universal falsa, y el lint lo cruza contra el disco.

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

#### Los tres roll-ups se ESTAMPAN, no son Dataview (D-10/D-11)

`## Papers`, `## Planetas` y `## Métodos aplicados a esta estrella` los regenera
`python scripts/make_notes.py <slug>` (idempotente, cirugía: no toca la prosa); el lint reporta como
backlog la tabla desactualizada **nombrando los stems**. `## Métodos aplicados a esta estrella` lleva **una fila por MÉTODO** (agrupado por clave
normalizada, con las variantes al lado) y colapsa la cola en un `<details>` que **declara cuántos
quedan adentro** (#273: por par eran 369 filas sobre 291 métodos, el 30 % de una ficha real).
`## Papers` es una tabla materializada —`Bibcode | Año | Relevancia | Origen | Estado`— cuyo
encabezado lleva **los dos números** (universo · sintetizados acá): evita prometer 155 arriba de una
síntesis de 8. El **estado** dice cuán lejos llegó cada paper (`fuera del filtro` → `sin extraer` →
`extraído, no sintetizado` → `sintetizado`). En un concepto el roll-up es la **unión** de `methods` y
`thesis_links`, con la columna *Entró por* (D-24: esas dos llaves viven en papers distintos), y
lleva **las mismas dos garantías** (#300): se habían aplicado sólo a `stars/` y el defecto seguía
vivo acá (un concepto cerrado prometía 89 arriba de una síntesis de 30, 57 reclamados sin leer).

El motivo (#60): un bloque ```dataview``` le muestra a un agente que abre el `.md` **la query, no
sus resultados**, y el plugin ni está versionado. El equivalente determinista parsea el frontmatter
con el mismo parser que el tooling (`lib_config.split_fm`), desde la raíz del repo:

```bash
# papers de una estrella (equivale al roll-up `## Papers`); con `fm.get('methods')` en el print,
# los métodos DE esos papers (no todo paper que use el método)
python -c "import sys,glob;sys.path.insert(0,'scripts');import lib_config as c;[print(f) for f in sorted(glob.glob('vault/wiki/papers/*.md')) if '<nombre>' in (c.split_fm(open(f,encoding='utf-8').read()).get('stars') or [])]"
```

⛔ **No uses `grep`/`awk` sobre el frontmatter para esto.** La lista puede estar en **bloque** (como
la escribe `make_notes` al crear la nota) o en **flow style** (`stars: [tau Cet]`, como la deja
`merge_frontmatter_list` en todo paper retro-linkeado): las dos formas conviven en el mismo corpus y
cualquier patrón textual pierde una de las dos. Además el matcheo textual confunde `GJ 71` con
`GJ 710`, y `split_fm` compara por elemento.

⛔ **El roll-up compara `methods` por CLAVE NORMALIZADA, no por string exacto (#243).** El campo lo
puebla la **extracción** —un LLM por paper, vocabulario abierto—, así que el mismo método llega
escrito de varias maneras (`PCA`/`pca`, `SysRem`/`sysrem`). Comparando el string crudo, un roll-up
**subdeclara su propio universo en silencio**, que es justo lo que D-10 existe para evitar. La clave
es `casefold` + NFKD + `[^a-z0-9]+ → -` (`lib_config.method_key`), compartida por el roll-up y por
el detector del lint —sin ella, `PCA` y `pca` se reportaban como dos deudas distintas—. ⛔ Se
normaliza al **comparar**, nunca al escribir: la grafía que eligió el extractor es información sobre
cómo lo nombra el paper. Los **sinónimos** (`gls` / `periodograma-gls`) **no** se juntan solos: eso
es juicio, a veces son cosas distintas, y va a un backlog que propone y no aplica.

⚠ **El roll-up de métodos linkea `[[método]]` sólo si la nota existe —por stem **o por
`aliases`** del concepto (#245), con la grafía del extractor al lado— y si no, lo estampa como
código.** `methods` lo puebla la extracción (paso 3 de `ingest-star`) y las notas de
`concepts/methods/` las crea **`ingest-theme`**, que es otra operación: con el link incondicional,
seguir `ingest-star` al pie de la letra dejaba decenas de *wikilinks rotos* —bloqueantes— que no se
podían cerrar dentro de la operación que los creó. La señal no se pierde: el lint la reporta como
backlog *«`methods` sin página destino»*, la versión no bloqueante de lo que `thesis_links` sí
bloquea (asimetría real: un `thesis_links` nombra un concepto que `ingest-theme` crea en la misma
operación que lo siembra).

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

⚠ **El schema viejo** (`planets[].disputes[]` con `field`/`ref`/`note`/`alt`) tenía el polo de
verdad hardcodeado en la forma: servía para paper↔NEA y **no podía expresar paper↔paper** —el caso
normal cuando NEA calla—, y `P_rot`, que es de la estrella, no tenía dónde colgar. **El lint no lo
lee: lo detecta y bloquea** (`python scripts/make_notes.py --migrate-disputes`) — una disputa que el
lector ignora en silencio es peor que un error.

### papers/

Campos: `bibcode, title, first_author, n_authors, year, arxiv_id, doi, bibstem, stars[], facets[],
keywords[], methods[], thesis_links[], role[], relevance, citation_count, pdf, fulltext,
fulltext_source(pdftotext|ocr|web), pdf_source(eprint|ads|publisher|web), vistas[], versions[]`.

⛔ **Toda nota de paper pertenece a alguna ENTIDAD (D-23).** Al menos uno de `stars`,
`thesis_links` o `methods` tiene que estar poblado. Sin ninguno de los tres el paper no entra en
ningún roll-up y no lo alcanza ninguna ficha ni concepto: es extracción ya pagada que se vuelve
invisible — y no es lo mismo que una nota **huérfana**, donde basta un link entrante para tapar el
hueco. Es **bloqueante** (INV-94), y la salida es poblar el campo, no borrar la nota. ⚠ Cuando
`entity.py delete` deja un paper sin destino **avisa y no borra**: la decisión sobre una extracción
cara es del usuario.

#### La extracción es una lectura CON LENTE, y la nota declara cuál se hizo: `vistas[]` (#188)

El prompt del fan-out nunca pregunta *«¿qué dice este paper?»* sino *«¿qué dice **sobre
{sujeto}**?»* — pero la nota es **una por bibcode**. Con una sola sección sin scope, **el silencio
de la nota sobre un eje es indistinguible de «se miró y no hay nada»**. Cada entrada de `vistas[]`:
`sujeto` (el mismo nombre que usan `stars[]`/`thesis_links[]` — es lo que hace comparables reclamo y
lectura), `tipo` (vocabulario **cerrado** `star | theme`, declarado y no derivado, para que el lint
cace el typo), `fecha`, `txt` (de qué copia del `.txt` salió), `lente` (las facetas vigentes al
leer) y `fuente`. La sección del cuerpo es `## Vista — <sujeto>` y **no** es estampada: es
exactamente lo que `verify-citations` contrasta contra la fuente. El lint **bloquea** la
incoherencia en los dos sentidos (vista declarada sin su sección; sección sin declarar) y el schema
viejo (`## Extracción (LLM)` sin `vistas[]`). **Forma dura como `extra_core`** (D-58): el escalar y
la lista de strings bloquean.

⛔ **`txt` se cruza contra el DISCO al estamparse (#230).** Un ancla que apunta a la nada no ancla.
La asimetría con `fuente: pdf` es deliberada: aquélla **rechaza** la extracción, ésta **degrada
declarando** — si el `.txt` vive bajo otro slug se apunta ahí; si no existe **la clave no se
escribe** (*no consta*, nunca un puntero falso): desde #205 una vista puede legítimamente no tener
`.txt`.

⛔ **`fuente` dice DE QUÉ se construyó: `pdf` | `abstract` (#207).** Un paper sin PDF **no es
inextraíble** —ADS, OpenAlex y arXiv devuelven el abstract—; lo que no puede pasar es que una
lectura de ocho líneas quede indistinguible de haber leído el paper, y encima el abstract es donde
la fuente afirma **de más**. Lo **declara el extractor** y el **cosechador lo cruza contra el
disco**: `fuente: pdf` sin PDF **rechaza la extracción entera**. Ausente = *no consta*, backlog;
`fuente: abstract` también, pero ahí el pedido es **conseguir el PDF**.

⛔ **La `fecha` es lo que dice que la lectura OCURRIÓ.** El stub nace con la vista de su sujeto y
**sin** fecha (*no consta*), así la nota es coherente desde el minuto cero y el lint reporta la vista
sin fecha como backlog. La estampa el **cosechador** (`harvest_views.py <slug> [--theme]`), que
además mergea `methods`/`thesis_links`/`role` add-only, escribe la sección mientras siga siendo la
plantilla del stub —prosa redactada no se pisa sin `--force`— y **trae el `.txt` al slug del sujeto**
(D-18), sin lo cual la vista de un paper retro-tagueado no es ejecutable.

⛔ **Las `salvedades` sobre el ARTEFACTO se chequean con un script, o se publican marcadas NO
VERIFICADAS (#213).** *«El `.txt` perdió este símbolo»* no lleva `[[bibcode]]` —es sobre el archivo,
no sobre el paper—, así que `verify-citations` la deja afuera **por construcción**. Dos mitades:

- La salvedad **decidible sobre un archivo** se emite **estructurada**, con vocabulario cerrado
  (`lib_config.SALVEDAD_TIPOS`: `txt_pierde` + `cadena`, `pdf_paginas` + `n`), y la chequea el
  **cosechador** con `grep` o `pdfinfo` — máquina, no LLM. La **falsa NO se publica** y el cosechador
  la grita con su archivo; ⚠ pero **no tira la extracción** (a diferencia de #207: aquello es una
  contradicción sobre *qué se abrió*). El chequeo que **no pudo correr** sale **no evaluable con su
  motivo**, nunca «verificada» (D-43).
- Todo lo demás se publica en su **propio bloque**, marcado *«⚠ NO VERIFICADAS — juicio del
  extractor»*: publicarlo al mismo nivel visual que una fila chequeada es lo que dejó leer un
  defecto inventado como un hecho medido.

⛔ **La lectura puede RETRACTAR el reclamo que la trajo: `refuta: [<sujeto>]` (#212).** Es el único
canal en esa dirección: `stars`/`thesis_links` se siembran **antes** de leer y `harvest_views` mergea
**add-only**, así que un reclamo falso era **infalsificable por la lectura** (el caso típico es la
**polisemia**). ⛔ El cosechador **registra y propone, no aplica**: deja el `refuta` en la vista e
imprime el `--drop-core` con su motivo, porque borrar el reclamo sería un LLM editando curación en
silencio y porque la decisión es del **par (paper, sujeto)**. El lint lo reporta como **backlog**; el
add-only **no se afloja**.

⛔ **Una SEGUNDA lectura del mismo sujeto con otra lente CONVIVE: `enfasis` (#239), y se PIDE con
`extraction_prompt.py … --enfasis "<lente>" [--ejes a,b]` (#308)** —el prompt manda leer primero la
vista anterior para no re-narrarla, y **rehúsa** si `(sujeto, enfasis)` ya tiene lectura—. La
identidad de una vista es el par `(sujeto, enfasis)` y su sección es `### Lente — <énfasis>` **dentro** de la
`## Vista` del sujeto —partir el encabezado no serviría: `section_start` recorta el sufijo que
arranca con puntuación (AUD-178) y las dos colapsarían—. El cosechador **rehúsa** cambiar un valor
ya escrito bajo la misma clave: completa lo que falta, o manda declarar la lente. ⛔ **Y su extracción va a
`<bibcode>__<lente>.json` (#371):** al canónico pisaba, en silencio, un artefacto versionado y **no
regenerable** (#311).

⛔ **`vistas[]` la escribe SÓLO la lectura, nunca el retro-link.** Es lo que mantiene a
`stars`/`thesis_links`/`methods` como **reclamos** (`make_notes` los mergea add-only sin leer nada) y
a `vistas[]` como **lecturas**. Un reclamo sin vista es backlog y se cierra de dos maneras: haciendo
la vista, o declarándola `no_vista: [{sujeto, motivo}]` cuando ese sujeto sólo aporta al roll-up —
vale en **las cuatro** redes que cuentan la nota (#268), con estado propio: `sin vista (declarado)`,
que no es `sin extraer`. **Motivo obligatorio y por sujeto**: un paper que tres sujetos reclaman se
saltea por motivos distintos en cada uno. Qué cuenta como reclamo: `stars` y `thesis_links` siempre;
`methods` **sólo si ese nombre es un tema declarado** —lo puebla la extracción, así que es producto
de la lectura—.

⛔ **Sacar `pending_source` no puede romper el frontmatter (#244).** El borrado de una clave es
**una sola función**: filtrar por `startswith` se lleva la primera línea de un escalar multilínea y
deja huérfanas las de continuación, el YAML deja de parsear y la nota evade **todos** los chequeos de
su tipo (y no es raro: `pending_motivo` es texto libre). La red es la de #222: se re-parsea y **no se
escribe** si dejó de parsear.

#### Identidad: el `doi`/`arxiv_id`, no el bibcode (D-19)

El preprint y el publicado son bibcodes distintos del **mismo** paper: dos notas ahí son doble
conteo, dos fuentes donde hay una, y un falso positivo permanente de #75. Hay **una sola nota
canónica** y los bibcodes viejos viven en `versions[]`; el lint bloquea el duplicado y `make_notes`
**rehúsa crear** la segunda nota.

⛔ **Un bibcode listado en `versions[]` que TIENE su propia nota BLOQUEA (#229).** La exención por
alias es incondicional: listarlo ahí lo saca de los **dos** chequeos de identidad. O es un alias (y
**no debe haber nota**) o es otro trabajo (y **no va en `versions[]`**); *«mismo programa,
resultados distintos»* se declara en **prosa o en `salvedades`**.

⚠ **Y el bibcode que `versions[]` declara como alias NO se vuelve a bajar** (D-19): es el mismo
trabajo, ya está en disco bajo el canónico. Sin esa guarda, la corrida siguiente a un renombre lo
re-baja y el par PDF+`.txt` queda como artefacto colgado **para siempre** —no tiene nota, y #229
impide que la tenga—. Lo filtran los dos fetchers, junto con los descartes de curación.

El ciclo se resuelve con `python scripts/make_notes.py --rename-paper VIEJO NUEVO`, que mueve la
nota y sus artefactos (`raw/pdfs/`, `raw/fulltext/` **y la extracción de `raw/extraccion/<slug>/`**
— #228/#374: la identidad de una extracción es el `bibcode` **de adentro**, con UNA función para
sus tres lectores, así que dejarla bajo el bibcode viejo hace que el cosechador saltee la nota
**para siempre**, y una extracción no se regenera sin re-pagar el paso más caro), **re-estampa la cabecera**, deja `bibstem` en `null`
—es verdad de catálogo y el renombre no tiene catálogo—, agrega el alias y **reescribe los wikilinks
de toda la bóveda**. Alcance declarado: `vault/`.

⛔ **El duplicado SIN `doi` ni `arxiv_id` lo reporta otra categoría (#216, backlog).** La clase de
fuentes donde el problema es **más** probable es la que no tiene identificador —resúmenes de
congreso, tesis, material pre-DOI—, así que `identidad()` devuelve claves distintas y el detector
bloqueante no lo ve. La señal es el **`## Abstract` verbatim** normalizado y comparado por su
**arranque**. ⛔ **NO se deduplica por título** (medido en `openalex.py`: peor que el problema), y
**reporta, no fusiona**: *«mismo trabajo en dos congresos»* vs *«dos etapas con resultados
distintos»* es una distinción real. La salida es `--rename-paper` + `versions[]`, o `--drop-core`.

#### Los dos artefactos y sus dos `*_source`

`pdf` es **lo que se lee** (extracción y verificación) y `fulltext` el **índice de búsqueda** del
corpus (`grep`), con los roles que fijó #205. Los estampan por **verdad de disco** —`fulltext` lo
cierra `extract_fulltext` (`stamp_fulltext`) y `pdf` su gemelo `stamp_pdf` desde `fetch_pdf` y
`--restamp-pdf-links` (#304: el campo se escribía sólo al crear el stub, así que el PDF que aparece
después —el rescate manual, cerrar un `pending`— no se linkeaba **nunca**)—, con `null` si no hay
archivo.

⛔ **Los dos `*_source` NO se comportan igual cuando el archivo desaparece (#230).**
`fulltext_source` describe **cómo se extrajo un archivo**, así que se limpia con él (el lint marca
como backlog el par `fulltext: null` + `fulltext_source: <valor>`). **`pdf_source` sobrevive**, a
propósito: no describe el archivo sino la **procedencia de la lectura que ocurrió** —una nota cuelga
su salvedad de `pdf_source: eprint` para decir que sus citas son contra el preprint—, así que
borrarlo destruiría la salvedad junto con el archivo. El par `pdf: null` + `pdf_source: <valor>`
**no es hallazgo**.

Cuando un paper vive bajo **varios slugs** el campo es **estable**: la copia ya estampada se mantiene
salvo que llegue una de **mejor calidad** (`pdftotext`/`web` > `ocr`); no se repunta al slug que
corrió último (idempotente, sin ruido de diff). Un puntero que **ya no resuelve** sí se repunta: una
nota que apunta a un archivo que no está afirma algo falso sobre el disco (#217/#304).

⛔ **Los dos son vocabulario CERRADO y el lint los BLOQUEA (#296)** —`pdf_source: eprint|ads|
publisher|web`, `fulltext_source: pdftotext|ocr|web`, con `null`/ausente = **desconocido**—: no es
cosmético, porque el campo **decide lecturas** —`eprint` dice que las citas son contra el
preprint— y un valor fuera de vocabulario cae por el `else` de todo `== "eprint"` **en silencio**.
⚠ Ese `else` **ya no exime** del chequeo de cita textual (#275/#363). Medido: 2 de 138 notas llevaban **prosa** en el campo
—una, información de adquisición legítima que terminó ahí porque el schema no tenía dónde ponerla—.
Migrador: `python scripts/make_notes.py --migrate-source-fields`, que pasa el valor a `null` y
**mueve** la prosa (a `pending_motivo` o a `salvedades`), no la tira.

**`fulltext_source` vs `pdf_source` (#57):** el primero dice **cómo se extrajo** el texto, el segundo
**de qué documento salió** — `eprint` (arXiv: puede ser un **v1 pre-referato**, con `eprint_version`
cuando se conoce), `ads` (escaneo alojado por ADS), `publisher`, `web` (snapshot), o `null` =
**desconocido** (que **no** es "publicado"). Manda la verdad de disco: la marca que arXiv estampa en
cada página es visible en el `.txt`, por eso se detecta retroactivamente re-corriendo
`extract_fulltext` sin re-bajar nada; si no hay marca, vale la rama que registró el fetcher. Esa
misma re-corrida es el **backfill de la marca de garble**: el chequeo que estampa `fulltext_source:
ocr` sobre un PDF **ya OCReado por el editor** sólo corría al extraer. Importa porque
`verify-citations` promete que la cita textual son las palabras reales del paper: con `eprint`, una
discrepancia numérica contra un valor publicado es candidata a **diferencia de versión** y NO se
"corrige" la nota hacia el preprint.

⚠ **`symbols_lost` y `fulltext_layout` se RETIRARON en 1.71.0 (#205).** Existían para decidir si el
extractor leía el `.txt` o el PDF, y esa decisión ya no se toma: la fuente es el PDF. Ninguno de los
dos discriminaba (#193, #194). Migrador `--migrate-txt-fields`; el lint **bloquea** la nota que los
lleve. Lo que sobrevive es un hecho: **`Read` rasteriza el PDF, así que el
modelo *ve* la fórmula** — es cuestión de **modalidad, no de modelo**.

#### `keywords` (D-17)

Son las del catálogo (ADS ya las devuelve). No son decorativas: la lente matchea sobre **título +
abstract + keywords**, así que sin ellas re-clasificar desde la nota daría un veredicto distinto del
que dio el ingest — un diff inventado. Son lo que hace posible el **diff de lente offline** (D-49),
o sea auditar si el corpus sigue clasificado con la regla vigente **sin `build/`**, que es scratch
gitignored y no viaja. Backfill: `make_notes.py --restamp-keywords`.

#### `role` — qué TIPO de aporte es el paper (#73)

`fundacional` (introduce el método, mecanismo o formalismo — la fuente de la ecuación), `aplicacion`
(lo instancia en un caso: una estrella, un dataset) o `arbitro` (reanaliza y **resuelve** —o
reabre— una tensión previa sobre el mismo hecho). Uno o varios; lo puebla la **extracción**, no la
selección (`classify()` es regex sobre título+abstract+keywords y clasifica **tema**, no rol).

Es distinto de la **postura** respecto de una tesis, que desde D-21 **no vive en el paper**: vive en
la tabla de evidencia de la hipótesis, porque depende de la tesis y un paper puede tocar varias.

Sin `role`, *"contrastar dos papers" no está definido*: fundacional↔fundacional compara supuestos
y derivaciones; aplicación↔aplicación pregunta si replica y **en qué régimen**;
**fundacional↔aplicación NO es contraste, es instanciación** —tratarlo como desacuerdo **fabrica
disputas falsas**—; el `arbitro` resuelve, no promedia. Vocabulario **cerrado** y bloqueante: un
typo deja el campo mudo para la única operación que existe para consumirlo. Es agudo en temas de
**método**, donde fundamentos y aplicaciones conviven en el mismo concepto por diseño.

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

⛔ **La nota de paper lleva el AVISO DE CAPA LLM (#247), y nombra las tres capas por separado:** lo
**auditable** (`## Abstract` verbatim + frontmatter de catálogo), la **traducción** (ayuda de
lectura, **nunca fuente de la que citar**: si citás, citás el original con su página) y la
**síntesis lenteada** (la vista). Era la única de las tres clases de nota sin él y es justamente la
que más contenido generado tiene. Backfill: `--restamp-headers`.

⛔ **`## Abstract` va en TODA nota de paper, verbatim (#124).** Es la capa **auditable** del cuerpo
—copia de catálogo, no síntesis— y `classify_offline` la lee para re-clasificar sin `build/` (D-49).
Los tres backends la devuelven: ADS en `abstract`, arXiv en el `summary`, OpenAlex como índice
invertido que `openalex._abstract` rearma. Pesa más desde #205: con el PDF como única fuente de
lectura, en un `pending_source` el abstract es **todo** lo que la nota tiene, y puede alcanzar. ⚠ Y
es justo donde la fuente afirma **de más**: una vista construida desde ahí se declara
`fuente: abstract` (#207).

⛔ **Y la nota lleva tres AYUDAS DE LECTURA (#124): `## Traducción del abstract`, `## Conclusiones` y
`## Traducción de las conclusiones`.** La **vista** es lenteada —dice qué aporta el paper *a ese
sujeto*—; las conclusiones son lo que el paper afirma **sin lente**, así que no son redundantes: son
lo que hace barata una **segunda vista** cuando otro sujeto reclama el mismo paper, y desde #205
abrir el PDF es lo caro. Las estampa el cosechador desde el JSON de extracción, van **antes** de la
vista, y **la traducción va al lado del original, nunca en su lugar**.

⚠ **Las traducciones se llaman `## Traducción …`, con el nombre COMPLETO — no `## Abstract (es)`.**
Ese nombre volvía a `## Abstract` un **prefijo** del suyo, y `section_start` tolera a propósito un
sufijo que arranca con puntuación (lo necesita para `## Vista — X (2026-08-27)`): con sólo la
traducción en la nota, el guard del verbatim la daba por el original y **no lo estampaba nunca**. Es
la trampa de prefijo de #176 en el vocabulario propio del framework — se saca renombrando, no
aflojando el cortador.

⚠ La **sección** la escriben los dos raíles al crear —con `_(no disponible)_` si no hay copia de
catálogo— y el cosechador la **completa** sin pisar un verbatim ya puesto (#124/#277; el stub off-ADS
no la escribía **nunca**: 39 de 138 notas de una bóveda real sin ella). Backfill:
`make_notes.py --restamp-abstracts`; el lint la **bloquea**.

⚠ **Documento largo (`unidad_cita: pagina`): sin conclusiones** — igual que la fuente leída sólo del
abstract (#207), y la que no tiene esa sección se declara `sin_conclusiones: <motivo>` (#277): un
libro no la tiene, y transcribir algo que no existe fabrica contenido. Exclusión **estructural**, no
umbral de largo.

⚠ **Cómo se leen las conclusiones, y por qué es un método:** el extractor empieza por ahí, saca los
**ejes** que el trabajo dice aportar y los **chequea contra el cuerpo** — es donde vive el *afirmar
de más*. Si el cuerpo dice menos, es un hallazgo sobre la **fuente** y va a `salvedades`.

⛔ Las cuatro secciones están en `SECCIONES_ESTAMPADAS`, así que `verify-citations` **no las mira**:
una traducción no es una afirmación de la bóveda. La red está aguas abajo —lo que de acá llegue a una
**ficha** sí se verifica contra el PDF—: **son ayuda de lectura, nunca fuente de la que citar.**

#### Notas off-ADS y fuentes largas

En notas **off-ADS** el schema suma `source_url` (URL de la fuente web; `null` si es PDF local),
`accessed` (la cita "Retrieved <fecha>") y, si la fuente no se pudo conseguir, `pending_source:
paywall|scan|unextractable|adquisicion` (el lint la lista como precondición).

⛔ **`pending` es vocabulario CERRADO y lleva `pending_motivo` obligatorio (#80).** Los tres valores
históricos describen **por qué falló** la adquisición o la extracción; **`adquisicion`** describe
otra cosa —un libro que el usuario va a conseguir **no falló**, tiene otra latencia— y entraba
forzado como `paywall`, perdiendo el motivo real. El motivo es obligatorio por el mismo argumento
que el `--reason` del triage: en seis meses sirve el motivo, no la categoría. Un typo entraba mudo:
hoy la cadena aborta y el lint lo nombra.

⛔ **Una fuente LARGA declara cómo se la cita y qué parte entró (#80):** `unidad_cita:
linea|pagina|seccion` (default `linea`) y **`alcance`** (qué capítulos entraron), obligatorio cuando
la unidad no es la línea. Un libro rompe dos supuestos de `verify-citations`: el fan-out asume un
`.txt` que se lee **entero** —700 páginas lo revientan— y «línea 18443» no es una referencia
utilizable; y casi nunca entra el libro entero, lo que choca con el chequeo de **completitud**, que
sin `alcance` no distingue un recorte deliberado de una omisión. Eje **distinto** del `txt:`/`pdf:`
de #117: aquél dice qué **archivo** se leyó, éste **cómo se apunta adentro**.

⛔ **Y se RE-SINCRONIZAN: la autoridad es la config (#312).** Viajan al stub al crearlo y se
congelaban ahí, así que ampliar el `alcance` dejaba la nota afirmando que ese material *no entra*
mientras lo publicaba en su vista (medido: 2 libros, 37 valores). El chequeo de completitud compara
contra el de la nota, o sea que un alcance viejo lo deja con información **falsa**, no sin
información: `make_notes.py --restamp-alcance`, y el lint reporta el desfasaje.

⛔ **Y los dos campos LLEGAN AL EXTRACTOR (#241).** `extraction_prompt` **ramifica por
`unidad_cita`**: para una fuente larga manda empezar por el **índice**, pega el **`alcance` declarado
textual** —sin ampliarlo solo: si lo que el sujeto necesita está afuera, se extrae lo que hay dentro
y **se declara en `salvedades`**—, recuerda que `conclusiones` va **vacío** y que se cita **por
página**. Sin `alcance` el prompt lo **dice** (*«NO DECLARADO»*) en vez de callar.

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

**Régimen de validez (#74) — sólo en conceptos.** Acá no hay ground-truth ni árbitro externo, y el
eje de contraste **no es el mismo que en una estrella**: allá comparás el mismo número medido dos
veces; en un método, dos papers pueden decir cosas distintas y **estar los dos bien**, porque valen
bajo condiciones distintas (SNR, muestreo, tamaño de muestra, definición del observable). Por eso el
modo de falla dominante en un concepto **no** es "dos números no coinciden" sino **generalizar de
más**: el paper afirma X bajo condiciones C y el concepto afirma X pelado. La unidad de síntesis no
es `(campo, valor, fuente)` sino **`(afirmación, condiciones bajo las que vale, fuente, rol)`**, y
ésa es la tabla. Es el destino de los veredictos **`aparente`** de `find-contradictions` ("distinto
régimen, distinta definición, distinta época"): en una estrella se descartan como no-disputa; acá
**son el hallazgo**. El `## Inventario por eje` queda para el desacuerdo **real bajo las mismas
condiciones**, que acá es el caso minoritario. De la tabla sale además un hueco accionable que antes
no tenía forma: **"régimen no cubierto"**.

**Convención hub/radios (tema grande → varias notas).** Cuando un tema no cabe en una sola nota sin
perder foco, se estructura como **hub** (la síntesis del tema completo) + **radios** (notas satélite
del mismo área que profundizan un sub-aspecto; p. ej. hub `procesos-gaussianos`, radio `gp-kernels`).
El hub referencia cada radio explícitamente y el radio abre con su "Para qué" apuntando de vuelta al
hub. Un radio es una nota de concepto normal (mismo frontmatter y estándar de autosuficiencia);
"hub/radio" es sólo la metáfora organizativa.

⛔ **El ALCANCE de un tema es su `query` + su `facet` (#127).** *«Cuando no cabe en una nota»* es
editorial y no se puede chequear; lo que de hecho decide la partición es que cada tema necesite **su
propia query y su propia faceta**, o sea que **la terminología no se solape** — si se solapa, la
misma query trae las dos cosas y no hay nada que partir. Un radio es entonces un **tema propio**
(slug, query, faceta, registro y corpus propios) cuya nota apunta de vuelta al hub. Ejemplo: *noisy
ICA* es radio porque su vocabulario (*gaussian moments, quasi-whitening, HeteroPCA*) no lo trae una
query de «independent component»; *PCA* queda **dentro** del hub —es el baseline contra el que se
mide— y *PCA heterocedástico* **corresponde al radio**: «PCA» se parte **por régimen**, el mismo eje
que separa radio de hub.

⛔ **El hub nombra cada radio con `[[wikilink]]`, no con el slug entre backticks.** Sin el link el
radio no aparece en el grafo, no cuenta como link entrante y el hub se lee como si el sub-aspecto no
existiera. El lint lo reporta como backlog.

### concepts/hypotheses/

Campos: `name`, `status` (**vocabulario CERRADO**, D-37 — `abierta | sostenida | disputada |
refutada`: el lint bloquea lo que no esté en la lista, porque un consumidor lee ese campo para
decidir si se apoya en la hipótesis y la prosa libre lo deja mudo; se **deriva de la tabla de
evidencia**, y si hay filas `desafía` con `status: sostenida` el lint lo marca).

El cuerpo lleva **tres cosas propias**:

1. **El blockquote de alcance** (D-34) — `> Alcance <fecha> · temas: […] + estrellas: […] · N
   papers · M con hits`. **Define qué significa el veredicto**: *"no hay evidencia"* no es *"no
   existe evidencia"*, es *"no hay evidencia en estos temas, con estos N papers, a esta fecha"*; sin
   él, un veredicto negativo se lee como **universal**. Los slugs son directorios de
   `raw/fulltext/`, así que el universo se puede **re-contar**: el lint compara lo declarado contra
   lo que hay hoy y marca la hipótesis si quedó corta.
2. **La tabla de evidencia** (D-21) — una fila por paper: `Paper | Postura | Qué dice (cita textual)
   | L | Régimen`. Acá vive la **postura** (`apoya`/`desafía`/`método`), **no** en la nota del paper:
   depende de la tesis —un paper puede tocar varias— y como escalar suelto en el paper es un
   veredicto sin evidencia que `verify-citations` **no puede chequear**. En la tabla hay una fila por
   par, con cita: es verificable. ⛔ `bearing` en una nota de paper es schema viejo y **el lint lo
   bloquea** (`make_notes.py --migrate-bearing`).
3. **El veredicto global marcado `inferencia`** (D-36), con sus premisas: agregar N filas en una
   conclusión es juicio del agente, no algo que una fuente diga.

Una hipótesis **no es un radio** (D-35): cruza varias entidades, así que se linkea con
`[[wikilink]]` en los dos sentidos, sin la relación padre-hijo de un hub. El roll-up mecánico de qué
papers la tocan sigue saliendo de `thesis_links`.

### Estándar transversal de autosuficiencia

El estándar de `stars/` rige **igual** para `concepts/` y para las `queries/` que se archiven: la
nota debe **alcanzar por sí sola**, ser **dual-audiencia (humano y modelo)** y llevar `[[bibcode]]`
en cada afirmación para **citar y trazar**. Requisitos extra por tipo:

- **métodos e indicadores** (`concepts/methods`; un indicador —BIS, S-index, FWHM— es
  operativamente un procedimiento que produce un número, o sea un método chico, y por eso la semilla
  ya no trae un área aparte, #246): además **implementation-ready** — ecuaciones, inputs/outputs y
  pasos suficientes para **codificar el método tal como lo detallan los papers, sin abrir la
  fuente**; el detalle fino vive en los `[[links]]`. Y **con el régimen explícito** (#74): una
  ecuación sin las condiciones bajo las que vale es implementable y **equivocada** — quien la
  codifica no tiene cómo saber que estaba fuera de rango.
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
**server-side, antes de traer nada**, o sea la mitad **más restrictiva** del filtro (`facets` actúa
después, sobre lo ya traído). Hardcodearlo bloqueaba el caso que este framework declara soportar:
los **métodos de otras disciplinas** cuya bibliografía ADS no clasifica como astronomía. Tres
estados: sin declarar → `database:astronomy`; con valor → ése; **`search_fq: null`** → no acota, a
propósito (un `null` declarado es una decisión y no se lee igual que no declarar nada).
`relevance.facets` son **facetas** (constantes; clasifican los papers de estrella, y los de tema
**salvo que el tema declare su lente propia**), **no** sujetos (las estrellas/temas van en la query,
`stars.yaml`/`themes.yaml`). La **regla de combinación** de facetas es declarativa (no
hardcodeada): por default OR (≥1 faceta cualquiera), pero una instancia puede declarar
`relevance.require: [<faceta>, …]` (AND) y/o `relevance.min_facets: N` (≥N cualesquiera) —
`core = (≥min_facets) Y (todas las de require) Y (doctype no-ruido)`. Es la palanca contra el ruido
que el chaining mete al ampliar el pool; sin declarar nada, comportamiento histórico. Cambiar la
regla **re-clasifica** el corpus → sub-modo re-clasificar de `maintain`. No ingesta nada; después se
usan `ingest-star`/`ingest-theme`.

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

⛔ **Y los EJES DE LECTURA también son del tema (#307): `ejes:` en `themes.yaml`.** #254 los
derivó de la lente… global, así que a un tema de método se le preguntan los ejes de una bóveda astro
(medido: 4 de 8 vacíos en 25 de 32 papers, y los que el tema necesitaba no se preguntaron nunca —
volvieron desparramados en `aporte`, sin clave con la que compararlos). Mismos tres estados; la
`lente` de la vista guarda **los ejes que se preguntaron**, o el diff de D-49 describiría otra
lectura.
⛔ **Y el `search_fq` también es del tema (#295), porque es la mitad MÁS restrictiva.** D-26 hizo
propia la lente y dejó global el `fq`, que acota **server-side, antes de traer nada**: un tema de
otra disciplina se buscaba sobre un universo que **excluye su literatura por construcción**, y
ninguna `facet:` propia puede recuperarla (la faceta clasifica lo ya traído). Medido: 306
resultados con `database:astronomy` contra 6946 sin él, y `title:"noisy ICA"` —el término que da
nombre al tema— devolviendo **cero**. La salida **no** es sacar el `fq` (sin él el top por citas es
genómica y cardiología): es `search_fq:` en la entrada del tema, con los **mismos tres estados**
(sin declarar → hereda el objetivo · con valor → ése · `null` → no acota). El registro guarda el
**resuelto** y entra en la lente, porque cambiarlo re-clasifica el universo igual que la faceta.
⛔ **Y el tema de método que NO lo declara recibe un AVISO (#351)** —en el probe, antes del corte, y
como backlog del lint—: sin `search_fq` hereda `database:astronomy` y ahí la puerta fundacional **no
abre nunca** (medido en `ica`: 0 papers con el `fq` heredado teniendo `fundacional_min_citas: 2000`,
2 sin él —Comon 1994—; el tema se cerró sin su canon y hubo que re-sintetizarlo entero). Es **sólo
un aviso**: los tres estados no se tocan y un `null` **declarado** lo hace callar.

⛔ **Y el PREVIEW de un tema se corre con esa lente, no con la global (#208):**
`python scripts/query_ads.py <slug> --theme --probe` (la query sale de `query:` del tema).
Clasificar ahí con `relevance.facets` no es «menos preciso» sobre la población que el tema existe
para capturar: es el **veredicto opuesto** (medido en `ica`). Importa porque el preview es el
**único** lugar donde ese corte se decide **antes** de pagar descargas y extracción. En ese modo
cada fila lleva **por qué puerta entró**, el desglose por política reemplaza al contraste de
combinación —que habla de la lente global— y la línea de cierre manda a `themes.yaml`. Sin `--theme`, comportamiento
histórico; con `--theme` y un slug que no existe o que no declara `facet:`, **rehúsa** en vez de
degradar a la global. ⛔ **Y el probe dice POR QUÉ quedó afuera cada no-core (#289):** las dos
poblaciones piden acciones **opuestas** —*sin la faceta propia* (apretala) vs *pasa la faceta y
muere en la puerta* (`extra_core` o `fundacional_min_citas`)— y se mostraban idénticas sobre la
pantalla que existe para decidir eso; medido, 261 contra 32, con los dos papers que el tema existía
para capturar entre los 32. El segundo bloque lista los que **pasan la faceta**: es de donde sale
`extra_core`.
⛔ **Y para una ESTRELLA la query también se DERIVA (#248): `python scripts/query_ads.py <slug>
--probe`.** La tipeada a mano **no es la que corre el ingest** —la real expande las variantes de
espaciado (`HD 40307` ↔ `HD40307`) y suma los alias—, así que se previsualizaba un universo y se
ingestaba otro. Peor que #208: acá el veredicto sale plausible, porque los papers que faltan no
aparecen por ningún lado del reporte.

⛔ **Y queda registrado POR CUÁL puerta entró cada paper (#126): `puertas: [fundacional|astro|manual]` en
el registro.** El `why_excluded` explicaba el **no** y nada explicaba el **sí**. Es la única
metadata que distingue **sin leer el paper** un fundamento de su campo (muy citado, puede no
mencionar astro) de una aplicación astro (tres citas, pero es lo que la bóveda busca) — `role` no
sirve: lo puebla la **extracción**, o sea después de leer. Con la puerta registrada,
`triage.py <slug> --prioridad` agrupa los core por política y el recorte de lectura se decide **una
vez**, declarado con `--extraccion subconjunto --reason`. Lista vacía = no es core; el campo existe
siempre, así que «no consta» y «ninguna puerta» no se confunden. ⛔ **`manual` es la procedencia
de la CURACIÓN y la escriben las dos ramas del merge de `extra_core` (#303)** —la rescatada del
corte y la traída por bibcode—: cuál toca lo decide un accidente de la query, no una diferencia
real, y el `via` que va al registro es siempre el **declarado** en la config.

⚠ **`fundacional_min_citas` no tiene default**: el número depende del campo (30k citas es normal en
ML y muchísimo en astro) y esconderlo sería decidir por el usuario. Sin declararlo la puerta 2 **no
abre** y el motivo queda en `why_excluded`. *(Decisión abierta en `vault/STATUS.md`.)*

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
  fuera de astro. ⛔ **Y `topic:` acepta una LISTA (#293)**: un tema de método que cruza disciplinas
  tiene su literatura repartida —medido, una sola familia en cinco topics, y el mismo trabajo en
  topics distintos según sea preprint o publicado—, así que obligarlo a elegir uno es pedirle que
  elija qué mitad perder. Se buscan en OR (`topics.id:T1|T2`). ⚠ Lo que **no** pasa —decisión
  abierta, no defecto— es que `ingest_theme.py` corra la cascada por su cuenta: es un paso que el
  skill prescribe a mano (0b).
- **La cobertura distingue tres estados, no dos** (`print_cobertura`): corrió con N, **FALLÓ** (0
  por caída, que no es «no tiene nada») y **NO CORRIÓ** con el motivo. Saltear un backend en
  silencio deja una cascada de tres que corrió una, leída como "los tres miraron". Ídem el conteo de
  citas: arXiv no lo publica, así que la columna muestra **`?`, no `0`** — un `0` afirma "no lo cita
  nadie" sobre un dato que nadie miró, y con esa columna se decide qué mandar a triage. ⛔ **Y `--topics` —el PRIMER comando del paso 0b— declara sus dos
  ceros (#290)**: «la taxonomía no tiene nada parecido» (probá una frase más general) y **FALLÓ**
  (volvé a correrlo) piden lo contrario, y salían idénticos.
- **Dedup por DOI, nunca por título** (`ident`/`dedup`): el matcheo por título resolvió 18 de 25 y
  **2 apuntaban a otro trabajo**. Lo que no tiene DOI ni arXiv id se devuelve **aparte, como
  no-deduplicable**. Cada registro acumula `found_in`: la procedencia **enruta**, la lente
  **decide**.
- **Rankear sin filtro estructural amplifica, no filtra** (`topics` antes de `seed`): una frase
  genérica ordenada por citas devuelve 143.450 works con **2 de 30** en tema en el top 30; con
  `filter=topics.id:` primero, el canon entra al top 25. ⚠ El filtro es más laxo que su nombre:
  T11447 declara 55.210 works y devuelve 169.977 (matchea temas secundarios).
- **Descubrimiento ANCLADO** (`anchored_records`) — el de más apalancamiento: las **referencias de
  la mitad astro del propio tema**, rankeadas por cuántos de esos papers las citan (la puerta 1
  aplicada a un tema **nuevo**, donde el `citation_index` no existe todavía). Medido sobre 19 papers:
  devolvió los **ocho** del canon sin declarar nada, y alcanza lo que ninguna keyword del tema
  alcanza — los papers del **paso de blanqueo**.
- **La cola especialista SÍ se alcanza, con el eje correcto — y el costo es triage (#107, medido).**
  Esos papers viven entre **11 y 72 citas** dentro de un topic de 169.977 works, así que ningún
  corte por citas los toca; el eje que sí los alcanza es `seed_terms` (**slice de texto por término
  dentro del topic**). Medido: recuperación **7/18 → 13/18**, universo de candidatos **776 → 2521**.
  Ése es el canje —cobertura contra costo de triage—, se decide por tema, y por eso es **opt-in**.
  ⚠ **Lección de método:** la primera medición (*"217 candidatos, límite estructural"*) era
  artefacto de un tope de 15 filas puesto por el propio agente. Hoy `seed_terms` **avisa por
  término**.
  ⛔ **El aviso manda subir una perilla que EXISTE, y el slice se PAGINA (#294):**
  `rows_por_termino` es campo del tema y flag (`--rows-por-termino`); el backend topea en 200 por
  request, así que sin paginar el remedio era un no-op (medido: 2 papers perdidos sólo por el
  techo). ⛔ **Y el filtro por topic se decide POR TÉRMINO, con el conteo, y se declara (#293):** su
  valor escala con la **ambigüedad** del término — `HeteroPCA` tiene 9 works en todo OpenAlex (ahí
  el topic sólo puede sacar señal), `gaussian moments` 13.396 (ahí hace usable el ranking).
  Lo que queda fuera del alcance automático es chico y de una forma sola: **capítulos y actas** y
  papers cuyo título/abstract no usa ninguno de los términos del tema. Ahí manda la curación a
  mano, y el framework pide que cada entrada registre **por qué** entró (`extra_core` con
  `via`/`motivo`, o `sources`).
- **Encontrar ≠ conseguir** (`resolve_pdf`): OpenAlex identificó 8/8 de los canónicos y devolvió
  `pdf_url = None` **8/8**. La cascada del archivo es **OpenAlex → Unpaywall → arXiv por título
  EXACTO** (#313: el carril off-ADS no miraba el depósito que el carril ADS prueba primero — medido,
  las 2 fuentes `pending: paywall` de una bóveda eran obtenibles y una estaba en arXiv) y **propone
  una URL y para**: no reescribe un `pending:` declarado ni edita `sources:`. ⛔ Nunca por título
  **aproximado**, y el motivo enumera **lo que se consultó**: un `pending` es una declaración que
  congela la fuente como inconseguible, así que un falso «no hay copia libre» dura hasta que alguien
  se acuerde.


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
                         ⚠ Sin PDF en disco el prompt NO manda leerlo (#255): nombra el
                         `## Abstract` de la nota como fuente y manda declarar
                         `fuente: abstract`. ⛔ «En disco» = bajo CUALQUIER slug (#305),
                         la misma resolución que el cosechador: buscarlo sólo bajo el
                         del sujeto producía la lectura degradada que #207 caza. Sus EJES salen de `relevance.facets` de ESTA
                         bóveda (#254): una faceta que el prompt no nombra no se pregunta,
                         y su silencio se lee como «se miró y no hay nada».
                         Devuelve UNA VISTA (#188): «qué dice sobre {sujeto}», con
                         `vista{sujeto,tipo,txt,fuente}` en el JSON (#207).

5. harvest_views      →  la única compuerta que corre `is_extraction` (INV-103).
                         Estampa la vista (fecha · txt · lente) y la sección de la nota.

6. verify-citations   →  un subagente por fuente, misma regla del paso 4: lee el PDF.
                         Cada par verificado deja una fila con DOS hashes.
```

⛔ **La fuente es el PDF; el `.txt` es el ÍNDICE (#205).** La rama vieja —leer el `.txt` y escalar
al PDF si un detector lo decía— se eliminó: los detectores no discriminaban y el A/B medido dio al
PDF ganando en tokens, tiempo y tools **también en el paper de capa "limpia"**, cuyo `.txt` había
perdido `√`, primas y superíndices con los tres chequeos en verde. **Qué le queda al `.txt`:** el
`grep` sobre el corpus busca **prosa**, que es lo que `pdftotext` extrae bien; y en un **documento
largo** (#80) es imprescindible —700 páginas no se rasterizan: se grepea, se saca la página y se
abren **esas**—. ⛔ **El `.txt` NO se genera con el modelo**: tiene que ser determinista, o las citas
por línea serían inventadas y verificar sería contrastar un modelo contra otro. ⚠ **Consecuencia:**
un `pending_source` es **bloqueo real** — sin PDF no hay de dónde extraer.

⚠ **Excepción nombrada: la fuente WEB.** Un snapshot de `fetch_web` (`source_url` poblado, `pdf:
null`) no tiene PDF **por diseño**: ahí el `.txt` **es la captura** (defuddle, URL + fecha, citada
con `accessed`). Se lee, se cita por **línea**, y su fila de verificación lleva `txt:<sha10>`.

De los tres chequeos de calidad quedan **dos**: `is_legible` dispara el OCR (un escaneo sin capa de
texto deja un `.txt` vacío y el paper invisible al corpus) e `is_garbled` sigue porque la prosa
garbleada degrada el índice. `symbols_lost` y `fulltext_layout` se retiraron (#193/#194);
`measure_layout` **no** (`CANALETA_MIN` es el contrato para grepear un `.txt` entrelazado).

⛔ **Los tres miden el TEXTO, así que ninguno ve el dato que vive en una IMAGEN (#195)** — casi la
mitad del corpus (medido: 29/65 vistas). El prompt (`extraction_prompt._media_note`) trata los tres
casos:

- **tabla extraída como texto** → se cita por línea, declarando **cómo se verificó la fila** (en una
  tabla multi-objeto la fila equivocada es el modo de falla);
- **tabla-imagen** → el `.txt` no la tiene y el grep vacío **no prueba ausencia**: si el dato
  sostiene algo, se abre el PDF y se cita **página**;
- **figura** → el número existe sólo como curva: **se permite leerla** y el valor viaja con la
  **figura y su página** (`Fig. 3, p. 7`), el **`≈`** y la palabra **lectura de gráfico** en el
  régimen — doctrina de `inferencia`. Es un **permiso, no una obligación**: si la curva no se deja
  leer con confianza, queda como **hueco declarado**;
- **figura que es un CAMPO** (contornos, mapa de color, densidad) → el valor **no existe sin el
  nivel**: se cita `Fig. N, p. M, contorno del X %`. Dos lecturas que no reconcilian son figura
  **subespecificada** antes que dato ilegible (#281).

Por eso la columna de la vista se llama **`Localizador`** y no `Línea`: lleva `L1234`, `p. 271` o
`Fig. 3, p. 7` según de dónde salga el dato (la clave del JSON sigue siendo `linea`).

⛔ **La prosa que va a una CELDA se escapa: `\|` fuera de la matemática, `\vert` adentro (#240).**
Un `|` crudo parte la fila y una afirmación citada y verificada queda **invisible para el lector**
mientras el lint cuenta su fila. ⚠ Dentro de `$…$` el escape es `\vert` (en LaTeX `\|` es ‖):
escapar a ciegas cambia filas invisibles por fórmulas equivocadas. Lo hace `escape_cell` en el
cosechador, el único punto de escritura.

**Los DOS hashes del paso 6** responden preguntas distintas: el **ancla** hashea el bloque de la
**ficha** (se dispara si editás la nota) y el **hash de fuente**, el archivo **leído** (desde #205,
el PDF). Las filas viejas con `txt:` siguen válidas y se re-verifican al vencer, no se migran en
masa. ⚠ El PDF es inmutable: esa alarma es rarísima, y la fila anclada al PDF no se vence al
re-extraer el `.txt`.

**La cascada, paso a paso:**

1. Los **orquestadores** corren la cadena mecánica completa (idempotente, no pisa — única excepción
   add-only: el retro-linkeo de abajo): `python scripts/ingest_star.py <slug>` para estrellas,
   `python scripts/ingest_theme.py <slug>` para temas. **El orden canónico vive en el header de su
   orquestador** (fuente de verdad única — puntero, no copia).

1b. **Compuerta de triage (estrellas).** El citation chaining amplía el pool con papers que
   mencionan al sujeto sin hablar de él (medido: 18 % de precisión). Sólo entra solo el que lleva el
   **sujeto en el título**; el resto queda como **candidato** en `build/<slug>/ads.json` —sin
   bajarse— y lo juzgás por título+abstract (`triage.py <slug>`): aceptado → `extra_core` (mapas
   `{bibcode, via, fecha, motivo}`, forma dura D-58; `triage.py` imprime el snippet) + re-correr la
   cadena; descartado → `--drop … --reason` (persiste); **dudoso → al usuario**.

2. **Vos (LLM)** leés el **PDF** y poblás la extracción **de las notas de paper** (`methods`,
   `thesis_links`, `role`, P/K/indicadores). La ficha se escribe **después** del contraste (2b) — no
   saltar de leer a la prosa. ⚠ **Mirá `pdf_source` antes de copiar un número:** con `eprint` el
   documento es el preprint, así que un valor que contradice al ground-truth es candidato a
   **diferencia de versión**. **Cómo anotar cada valor (#103):** con **la página del PDF**, **el
   régimen** en que la fuente lo afirma y —si la fuente lo atribuye a otro trabajo— la marca
   **segunda mano** con la cita a X, porque el número **no es de esta fuente** (el mecanismo de
   error nº 1 medido). ⛔ **Nada de prosa comparativa en la nota de paper**: comparar dos papers es
   `inferencia` y va al `## Inventario por eje` (2b).

2b. **Contraste cross-paper (#72)** ⚠ *(el skill `ingest-star` lo numera **3b**)* — **entre leer los
   papers y escribir la síntesis.** Es el paso con más apalancamiento y el que más fácil se saltea,
   porque su producto no se nota si falta. Produce el **`## Inventario por eje`**: una fila por paper
   para cada **eje** donde los papers **no coinciden** (`Eje | Paper | Dice | Método / baseline`);
   los ejes con acuerdo unánime no entran. ⛔ **Sin columna "valor adoptado" ni "por qué"**: sería
   decidir por el consumidor (regla #0). Sin este paso, tres `P_rot` terminan en una frase con un
   solo `[[bibcode]]` y se evapora que los otros dos existen; el `role` (#73) dice qué operación
   corresponde entre dos filas. **La red de que ocurrió (#101):** el lint reporta la ficha con la
   **fila vacía de la plantilla** y ≥2 papers extraídos citados — ausencia = declarado,
   presente-y-vacío = saltado.
   ⛔ **Y tiene herramienta: `python scripts/contrast.py <slug>` (#314/#317).** Sin ella se improvisa
   un digest, el recorte cae **dentro de la cita** y el modelo la completa (2 fabricadas sobre 139
   pares). Nunca trunca una cita, agrupa por campo, arrastra `linea`/`segunda_mano` y ⛔ **no le
   sirve al 3b lo que `--drop-core` sacó del sujeto (#329)** —declara cuántas excluyó, y
   `--incluir-dropeados` las muestra—. Propone: el inventario lo escribís vos.
   ⛔ **La fila de `--filas` sale CON EL VALOR ADENTRO y NO SE RE-TIPEA (#322):** los 12 verdaderos
   positivos medidos eran de **copiado** —6 de atribución, 6 de cola alterada—, y mover una cadena
   entre archivos lo hace perfecto un script y mal un LLM. Vos escribís **la glosa**; **una fila,
   una fuente** (agrupar bibcodes bajo una glosa compartida fabrica atribuciones). ⛔ **Y las
   comillas son las del EXTRACTOR: el script no pone ninguna (#330)** —`valor` llega entre «», con
   «» adentro (glosa) o sin «»—; lo que sale sin comillas NO es verbatim y no se entrecomilla.
   ⛔ **La cita se verifica contra la EXTRACCIÓN, no contra el `.txt`** (#315/#317): es la
   transcripción hecha leyendo el PDF, y con el `.txt` de juez la señal era 2 de 17 y 0 de 35.
   Bloquea con **evidencia positiva** (#318/#321) —la frase bajo **otro** bibcode (atribución), o un
   prefijo largo con la cola divergente—; el **silencio** no, que la extracción es selectiva (#188)
   y se cita del PDF (#205). ⛔ **Pero PRIMERO se prueba contra el `.txt` de SU fuente, y la regla es
   UNA implementación (`lib_config.quote_verdict`, #324):** el `.txt` es índice degradado, no mal
   testigo, así que la cadena que está ahí prueba que la frase es de ese paper — sin ese paso, el
   *boilerplate* que la extracción no transcribió salía «mal atribuido». Duplicada, la regla ya
   divergía (13 contra 12), y desde #323 un falso positivo **frena operaciones**.
   ⛔ **Y el `.txt` también puede ACUSAR, en un dominio acotado (#333):** una cita alterada que nace
   **en la extracción** es invisible para un juez que **es** la extracción, así que si el `.txt` de
   esa misma fuente trae un **prefijo largo** de la cita y **sigue distinto** —en prosa, arrancando
   en un **borde de palabra**, sin tocar `$…$` ni una celda— gana el determinista sobre el LLM. Ese
   borde es la guarda que lo hace usable: `pdftotext` rompe **palabras** (ligadura `ﬁ`, `mix tures`,
   empalme) y un LLM que transcribe mal cambia **palabras** — medido con el cortador de #332 ya
   arreglado, 7 candidatas → **3 acusaciones, las 3 verdaderas**. ⛔ **No bloquea** (el `.txt` es
   índice degradado) y la salida es la **marca `⚠verificar en el PDF`**, que `contrast --validar`
   deja **lista para pegar** y no aplica (#341): cuál lectura gana lo decide quien abra la página, y
   corregir solo iría en la dirección equivocada — medido, un `.txt` partido ya hizo recortar una
   nota **hacia** la cadena inventada.
   ⛔ **Y alcanza `## Vista` sumando el bibcode de la NOTA a los adyacentes (#373):** ahí el bibcode es
la nota y no un link, así que 3838 transcripciones del PDF no las miraba nadie.
⛔ **Y ese cruce es PASO DE CIERRE de toda operación que sintetice, ANTES del verify (#323):**
   `python scripts/contrast.py [<slug>] --validar-todo` (sin slug, toda la bóveda; exit ≠ 0, declara
   población y no evaluables). Un `grep` de segundos contra N subagentes leyendo PDFs: verificar con
   LLM lo que el `grep` ya sabe alterado es pagar el caro por lo que el barato sabía. La capacidad
   existía y **no la corría nadie** — la nota que produjo la serie cerró con verify y `lint --cierre`
   en 0 **con 12 citas alteradas adentro**. ⛔ **Y sin slug es además pasada periódica de
   `maintain` (#386)**, registrada en `_citas.yaml` como la de red: el cierre lo corre CON slug y
   eso mira un rincón — medido, 0 acotado contra 1 global.

#### El CICLO DE LA LENTE — cómo se encadenan las piezas (#310)

Las seis piezas estaban documentadas por separado y su encadenamiento no, así que el ciclo se
reconstruía hablando en vez de leyendo. En orden, con su consecuencia:

1. **La lente de SUJETO es lo que hace que una vista no sea un resumen** (#188): se pregunta *«qué
   dice sobre {sujeto}»* con los alias pegados. ⚠ En la primera pasada **no puede ser angosta**: lo
   bastante amplia como para que entren las dos mitades del campo, lo bastante enfocada como para
   que ninguna vista sea un resumen.
2. ⛔ **Los EJES no se declaran antes de leer: se DESCUBREN al contrastar.** Un tema se ingesta
   normalmente **porque no se lo conoce**, así que pedir los ejes antes es pedir la respuesta que la
   operación existe para producir — y encima **cierra hallazgos**: los dos más valiosos de una
   ingesta medida salieron de extractores libres de contestar algo que nadie preguntó.
3. **El paso 3b/2b es el PRODUCTOR de ejes, no un resumen**: un eje sólo existe al poner las vistas
   una al lado de la otra. Ahí nace el vocabulario del tema (medido: el mismo término nombrando
   cinco objetos distintos, y el alias central significando dos operaciones según la escuela).
4. **El eje descubierto tiene tres destinos**: la **config** del tema (`ejes:`, #307), la
   **re-lectura** con esos ejes (`--enfasis`, #308) y la **próxima búsqueda** (una celda vacía del
   inventario *es* una query). Sin ellos el ciclo queda abierto justo donde el aprendizaje debería
   realimentar.
5. **Los ejes son DEL USUARIO**: viven en `themes.yaml` (versionado, editable), el paso 3b los
   **propone y no los escribe** (misma doctrina que `--drop-core` y AUD-160), y sin declarar rigen
   los de `relevance.facets` — los tres estados de D-43.
6. ⛔ **Qué se propaga solo y qué no**: la vista nueva → nota del paper (#239) y el roll-up del
   concepto, **sí**; la vista → **prosa de la ficha**, **NO**, y es deliberado: reescribir un bloque
   **vence las anclas** de los pares que vivían ahí (D-4/D-20) y obliga a re-verificar lo tocado
   (#203), con el agravante de #282 —ese ciclo no converge solo—. Propagar automático convertiría
   cada re-lectura en una cascada de re-verificación.

**El invariante (INV-146):** toda vista declara **los ejes vigentes al leerla** (`vistas[].lente`; con
`enfasis`, los de ESA lente, #372), y
cambiar los ejes de un tema produce un **diff computable**, nunca una re-interpretación silenciosa. Una vista leída bajo los ejes A sigue siendo válida bajo los B: lo que cambia es su
**cobertura**, y el detector de #270 pasa de ruido a señal.

2c. **Síntesis a la nota viva**, apoyada en el inventario: la ficha (frontmatter propio, prosa,
   huecos), los conceptos e hipótesis relacionados y la matriz método×estrella. ⛔ Los campos de
   ground-truth **no se tocan** (espejo de NEA, #70).

3. Actualizás `index.md` y appendeás a `log.md`.

> **Retro-linkeo (papers pre-existentes ↔ entidad nueva) — tres capas:** (a) el roll-up de una
> ficha-método junta también por `methods`, pero **no acumula solo**: re-correr `make_notes.py <slug>
> --theme` (el lint reporta la tabla desactualizada); (b) `make_notes` mergea **add-only** los seeds
> del ingest (nunca pisa la extracción LLM); (c) `ingest-theme` incluye el **retro-tag por grep** de
> los `aliases` sobre todo el corpus, con juicio de LLM (uso real, no mención al pasar).

> **Tema fuera de ADS (opt-in — sólo a pedido explícito).** Por default un tema se baja por **ADS**;
> el modo off-ADS existe para los **métodos de otras disciplinas** cuya bibliografía vive fuera de
> ADS: las fuentes se **declaran**, no se descubren por query. La entrada lleva `source: ads | web |
> local-pdfs [+web]` — ⚠ **el nombre engaña (#209): no dice «dónde se busca», dice QUÉ CADENA CORRE
> el orquestador**; el descubrimiento multi-backend es `discover.py --theme <slug>`, un paso aparte
> (0b) que `ingest_theme.py` no llama. Un tema off-ADS puede ser **mixto**, y su mitad astro entra
> por **`query:` poblada** → descubrimiento ADS completo (misma lente, mismas puertas, misma
> compuerta de triage), o **sólo `extra_core:`** → sub-cadena acotada a esos bibcodes; los papers con
> bibcode ADS van siempre en `extra_core:`, nunca en `sources:`. Una fuente que no se consigue se
> marca `pending: …` → stub con `pending_source`, derivada al usuario sin frenar. **`ingest-star` no
> cambia: es astro-only.** Papers sin bibcode ADS → clave sintética `AAAA+Autor`; páginas web →
> **snapshot `.txt` determinista** (`fetch_web.py` vía defuddle, que crea además el stub).
> ⛔ **Una `url:` que sirve un PDF NO se snapshotea: se BAJA como PDF (#242)** — `fetch_web` mira el
> `Content-Type`, porque `resolve_pdf` devuelve `pdf_url` por construcción y el framework proponía
> una entrada que su propia cadena rechazaba. La **frontera dura sigue rigiendo**: sólo bibliografía
> citable.

### Registro de ingesta (`vault/config/registro/<slug>.yaml` — versionado, #51/#64)
Cada sujeto ingestado deja un registro que **se commitea y viaja**, con tres secciones de dueños
distintos: **`descubrimientos`** (lo que la cascada de `discover` trajo, **con sus identificadores**
—#231: sin ellos el registro contaba 391 registros y no podía **nombrar ninguno**, así que
declararlos en `sources:` obligaba a re-correr la cascada. Es el simétrico de `busquedas[].bibcodes`
y lo que vuelve **accionable** un descubrimiento en vez de sólo contable—),
**`busquedas`** (lista, una entrada por corrida — **acumulativo**, D-28: antes pisaba, y
la cabecera de la ficha publicaba el embudo de la última corrida como si fuera el universo entero;
el universo del sujeto es la **unión**, no la suma, y cada entrada distingue `n_nuevos` de
`n_ya_estaban`), **`cadena`** (qué pasos corrieron, con fecha, versión, `via: orquestador|suelto` y
las **escotillas** usadas — D-57: **cada script se estampa a sí mismo**, así que un paso corrido a
mano deja rastro en vez de leerse como un corte; el lint compara contra el orden canónico y
**nombra el paso** donde se cortó — ⚠ **sólo para ESTRELLAS** (AUD-209): el orden de un tema depende
de su `source`, y un tema off-ADS no corre `query_ads` ni `fetch_ground_truth`, así que compararlo
contra el orden astro inventaría cortes que no existen. El `cadena` de un tema **se escribe igual**
—la traza vale— pero nadie la contrasta contra un orden canónico, porque no hay uno solo) y **`decisiones`**. Un descarte que se **revierte** (el bibcode
pasa a `extra_core`, la fuente se vuelve a declarar) no queda contradiciendo lo hecho: se **anula**
explícito, con el motivo viejo preservado en `previa` (D-52). Y la compuerta de triage **ya no se
puede apagar por flag** (D-48: `--no-triage` se eliminó — permitía que un candidato ya descartado
volviera a entrar en silencio). La sección `busquedas` la escribe `query_ads` al cerrar cada corrida: `fecha`, `query` efectiva
—en una estrella la arma `build_query` y antes se tiraba—, **`fq`** (#238/#295: el **resuelto**, o
sea el del tema si lo declara — es la mitad más restrictiva del filtro, y sin él un «0 encontrados»
**no es una medición reproducible**, aunque se use como premisa de decisiones de curación),
`rows`, `n_found`, `n_total`, `n_core`,
`n_candidates`, `n_dropped`, `truncated`, `almagesto_version`, **`bibcodes`** —lo que hace posible
la unión de D-28— y **`lente`** —facetas/`require`/`min_facets` vigentes al correr, contra lo que
se detecta la lente desincronizada—) y **`decisiones`** (el juicio de
curación, por clave: `decision`/`motivo`/`fecha`). Las `decisiones` cubren los **dos carriles**:
`triage.py --drop` para el candidato del citation chaining (por bibcode) y `triage.py --drop-source`
para la **fuente declarada** de un tema off-ADS (#81 — clave sintética o url, con `origen:
fuente-declarada` y un `fuente:` que la resuelva; sin `origen` = chaining), que existe porque en
off-ADS `sources:` registra sólo lo aceptado. `ingest_theme` **avisa** —no frena— si un item de
`sources:` lleva una clave ya descartada. Regla de
oro: **`build/` guarda lo regenerable, el registro guarda lo que no lo es.** Un `ads.json` se
recupera pidiéndoselo de nuevo a ADS; el juicio de por qué descartaste un candidato, no.
`busquedas` responde la otra pregunta, la del consumidor: **sobre qué universo de papers afirma esta
ficha, y con qué lente se filtró.** Efectos: (a) `make_notes` estampa en la cabecera **una línea**
con fecha, universo→core, pendientes y la ruta al registro (cirugía idempotente); (b) el lint deja de
dar **falso limpio** sin `build/` — *triage pendiente* y *corpus truncado* caen al registro y
reportan el snapshot **con su fecha**. Migración: el `build/<slug>/triage.json` viejo **ya no se
lee** (el framework no lleva capas de compatibilidad) y se consolida con `triage.py <slug>
--migrate`; mientras exista, el **lint lo bloquea** — que un juicio viejo quede mudo es el bug que
#51 arregló.

### Los cuatro cuadrantes de la curación — quién decidió y por qué (#111)

Toda decisión de curación deja registro **versionado**, en los cuatro casos, y desde #111 no queda
ninguno mudo:

| | Aceptar | Descartar |
|---|---|---|
| **con bibcode ADS** | `extra_core: {bibcode, via, fecha, motivo}` (D-58) | candidato del chaining: `triage --drop … --reason` (#51) · **core del sujeto: `triage --drop-core … --reason` (#112)** |
| **fuente off-ADS** | `sources: {…, via, fecha, motivo}` (#111) | `triage --drop-source … --reason` (#81) |

⛔ **`extra_core` fuerza la ENTRADA; `--drop-core` es su simétrico y faltaba (#112).** Un paper que
la lente dice core **no se podía sacar** (medido: 7 papers off-topic descartados con motivo seguían
siendo core corrida tras corrida). Una decisión de curación que el clasificador ignora en silencio es
peor que no tomarla: queda escrita, se lee como aplicada, y no lo está. Tres propiedades del carril,
cada una cerrando un modo de falla:
- **El carril es `sujeto`, no global.** La exclusión es del par `(paper, sujeto)`: lo que se saca de
  un tema de método por polisemia —"componentes independientes" de un tensor— puede ser legítimamente
  core de otro. Un descarte global decidiría por bóvedas que no son ésta.
- **El paper excluido queda VISIBLE**, con `via: manual-drop` y el motivo en `why_excluded`. Si
  desapareciera del registro, dentro de tres meses se leería como *«la búsqueda nunca lo encontró»*.
- **Los artefactos se borran** (PDF y `.txt`): si quedan, #108 los reporta como extracción pagada
  sin nota **para siempre**; la decisión queda versionada, así que borrar el artefacto no borra el
  juicio. ⛔ **En la nota que SE CONSERVA, `drop_core` re-apunta `pdf:`/`fulltext:` por verdad de
  disco (#217)** —a la copia que sobreviva, o a `null`—: dejarlos apuntando a un archivo que este
  mismo comando borró afirma algo falso sobre el disco. **La vista y la extracción no se tocan**: la
  lectura ocurrió; lo que cambió es que ya no hay contra qué re-verificarla, y **eso el lint lo
  dice** (backlog). La **nota** se borra **sólo si el paper no pertenece a otro sujeto Y no tiene
  extracción**; si no, se avisa por qué. Los `[[wikilink]]` que quedan rotos **no se reparan**:
  sería decidir por el usuario qué decía esa frase (#132).
- **El diff de re-clasificación lo respeta** (`lens_diff_offline`, `reclass_diff`): sin eso, cada
  cambio de lente vuelve a proponer lo que el usuario ya sacó, y la categoría se vuelve ruido que se
  deja de mirar.

INV-24 sigue en pie por la misma razón que con `extra_core`: core es `f(paper, lente)` **módulo
curación declarada**, y la curación es auditable —motivo obligatorio, fechada, versionada, viaja—.
Lo que no sería auditable es que el veredicto cambiara sin que nadie firme. El cuadrante que
faltaba —la fuente off-ADS **aceptada**— es el que más lo necesita: ahí **todo** entra por decisión
de alguien.

⛔ **`via` son DOS vocabularios, uno por carril (#266).** El párrafo que sigue describe el de
**`sources:`** (off-ADS); el de **`extra_core`** (ADS) vive en `lib_config.EXTRA_CORE_VIA`:
`usuario` · `triage` · `citado-por-corpus`. Miden ejes distintos — en off-ADS el eje es *quién
decidió*; en el carril ADS, **por qué mecanismo** entró un paper que la lente no marcó core.
Escribir el valor del otro carril hace que el loader **rechace duro**; lo vigila un test de paridad
doc↔código.

En `sources:`, `via` es **vocabulario cerrado y BINARIO** (#206): `usuario` (lo trajo una persona) ·
`descubrimiento` (lo propuso la cascada de `discover`). Mide **quién decidió**, y eso no tiene
tercer valor. De qué documento salió lo lleva **`motivo`**, obligatorio. El lint **bloquea** la
entrada sin `via` o sin `motivo`, el `via` fuera del vocabulario (typo) y el valor **retirado** (con
mensaje propio: un typo se corrige, un retiro se traduce). ⚠ El PDF que el usuario aporta para
cerrar un `pending_source` **no** necesita valor propio: ese paper ya entró con su `via`.

⛔ **El carril off-ADS tiene salida hacia la ingesta** (#111): `python scripts/triage.py <slug>
--accept-source <doi> --via <via> --reason "<motivo>"` arma la entrada completa —metadata real de
OpenAlex, archivo resuelto por `resolve_pdf` o `pending: paywall`, y la procedencia— **lista para
pegar**. No escribe `themes.yaml`: la config es curada y versionada, y un script que la edita solo
convierte una decisión en un efecto colateral.

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

**Extensión propia de esta wiki** (el lint canónico de Karpathy no valida que la fuente respalde la
afirmación — sólo salud estructural). **Cuándo:** paso de cierre de **toda operación que escriba
prosa con `[[bibcode]]`** — antes de lint/commit. **La nota nace 100% verificada (D-5):** *"sin
verificar"* sólo puede aparecer después, por una edición; por eso el caso normal es que el lint
calle, y cuando habla hay algo real. El procedimiento (fan-out, prompts, barrera, resolución) vive
en el skill; acá va el contrato del artefacto.

**Qué hace:** descompone la nota en pares (afirmación, `[[bibcode]]`) —las filas de tabla y los
ítems de lista **heredan la cita del ámbito que los introduce**; las `SECCIONES_ESTAMPADAS` quedan
afuera— y lanza **un subagente independiente por par** que lee SÓLO esa fuente (grounding-first,
prohibido de memoria) y devuelve **dos ejes separados** (D-59): un `veredicto` de RESPALDO
—`soportada|no-soportada|contradice`— y, aparte, la `condición` bajo la que la fuente lo afirma. Más
**cita textual + nº de PÁGINA del PDF** (obligatoria; sin cita ⇒ no-soportada: tiene que tocar el
**contenido distintivo**, la cercanía temática no alcanza). `no-soportada` = la fuente **calla**;
`contradice` = **afirma lo contrario** → corrección o **disputa** (#71). Cada falla se **resuelve**
(bajar la afirmación a lo que dice la fuente, reasignar la cita, marcar `inferencia`, o taguearla).

⚠ Dos ejes de **grado** se eliminaron y no vuelven: **`parcial`** (1.39.0 — se descompone sin
pérdida en `soportada`+`condición` o `no-soportada`) y la **columna `Score` 0–10** (1.42.0).

⛔ **La condición se CLASIFICA, con vocabulario cerrado: `acota` | `contextualiza` (#221).** El
fan-out la puebla en casi todos los pares, así que *«resolvé cada condición»* sería la nota entera.
Test operativo: ***¿la afirmación queda falsa si se saca la condición?*** → **`acota`** (se resuelve
sí o sí: fila de `## Régimen de validez`) / **`contextualiza`** (va al reporte). Y es **columna, no
prosa**: el juez es estable en el eje textual y no exhaustivo en el de régimen, así que absorberla
sin rastro borra lo que hay que poder re-auditar.

El subagente contesta además la **sobre-generalización** (#74: la fuente afirma bajo condiciones
que la nota no dice — no afirma falso, afirma **de más**) y, en transcripciones, la **completitud**
(una tabla truncada sin un solo error vuelve 100% soportada: afirma **de menos**).

⛔ **La TABLA vive en el HERMANO `<nota>.verif.md`, no en la nota (#344).** Medido: una nota de
entidad pesa ~72-75 k tokens y el **71-77 %** de esos bytes es esa tabla —que no es para el lector:
es para el lint y para re-auditar—, contra 16-21 k de contenido. En la nota quedan **la línea de
cabecera** (la afirmación, y lo único que le sirve a quien copia la nota), **las tres
sub-secciones** de hallazgos y un **puntero**. ⚠ Hermano en el mismo directorio, **no** un `.verif/`
con punto: con punto Obsidian lo esconde y el par deja de ser obvio. Las **anclas no cambian**:
hashean bloques **de la nota**. El par es un **iff** (INV-148) y el lint lo vigila con cuatro
categorías: tabla todavía adentro (schema viejo → `make_notes.py --migrate-verif-sidecar`), cabecera
sin hermano, hermano huérfano —las tres bloqueantes— y cabecera desincronizada de su tabla (INV-81
cruzando archivos: R-1, la escribe el paso de cierre). ⛔ **Una sola función resuelve dónde vive**
(`lib_blocks.verif_rows`) para los cuatro consumidores —lint, `make_notes`, `reverify_subset`,
`contrast`—. Un hermano **no es una nota** (`cfg.note_paths` lo saca de todo enumerador), pero sus
`[[bibcode]]` cuentan para los wikilinks rotos y los reescribe todo renombre; es la **octava capa**
de `entity.py`.

**El bloque `## Verificación de citas`** — una fila por par, en el hermano:
`| # | Afirmación (extracto) | Fuente | Veredicto | Evidencia | Ancla | Hash fuente | Condición |`
- ⛔ **Sin fila no hay dónde colgar el ancla**: colapsar las soportadas en prosa deja al lint sin
  distinguir "verificada" de "nunca se miró".
- ⛔ **Sólo `Afirmación (extracto)` se trunca (#226)**; `Evidencia` y `Condición` no, y `Evidencia`
  lleva su localizador **al final y completo** — el corte se lo lleva y apaga el cruce de #122, que
  sin él devuelve un 0 que se lee verde. ⛔ **El corte no cae dentro de `$…$`, `` ` `` ni `[[ ]]`**
  (#274b/#257c: `lib_blocks.truncate_claim` retrocede al límite del bloque). ⛔ **La celda lleva
  PROSA, nunca un `repr()`** (#274a).
- ⛔ **`Hash fuente` declara CONTRA QUÉ ARCHIVO se verificó: `txt:<sha10>` o `pdf:<sha10>` (#117).**
  La decisión la toma el verificador par por par, así que la declara la **fila**. En filas nuevas:
  `pdf:`. Sin prefijo = *no consta* y el lint **bloquea** (`make_notes.py
  --migrate-verif-archivo`). Excepción (#223): la fila `no verificable por extracción` **no declara
  archivo**, porque no hay ninguno.
- ⛔ **Documento largo leído del `.txt`: los DOS localizadores (#200)** — `pdf:` mentiría sobre qué
  se abrió y la línea sola rompe #80. ⚠ Desde #205 no se produce en filas nuevas.
- ⛔ **Un veredicto que exige acción NO queda registrado y sin resolver (#91):** `no-soportada` /
  `contradice` **pelados bloquean**. No cuentan `no verificable por extracción` ni la resolución
  anotada en la celda.
- ⛔ **Con DOS RONDAS, la segunda ANOTA, no pisa (#232):** `contradice→corregida`. Si pisara, el
  bloque final publicaría 0 donde hubo 3 `contradice`. Con más rondas la celda encadena (#274c): la
  partición de la cabecera es por el **primer** veredicto y la cadena se publica aparte.
- ⛔ **La cabecera la genera el mismo código que lee la tabla** (`lib_blocks.verif_summary`,
  INV-81): los **cuatro** veredictos —que particionan— y, tras un **`—`**, `con_condicion` (eje
  ortogonal). Las **tres sub-secciones** van **aunque digan «ninguna»**: son el único rastro del
  triage de la corrida.

**Los dos hashes (el ancla, D-4/D-20)** responden preguntas distintas: el **ancla** hashea el
**bloque markdown normalizado** que contiene la cita —reflowear no la mueve, cambiar un número sí; un
blockquote hard-wrapped es UN bloque (#224: por línea se podía reescribir el medio de una cita sin
vencer el par, y el sub-disparo es la única dirección prohibida); una fila sin `[[bibcode]]` propio
hereda el del caption— y el **hash de fuente** hashea el archivo que se **leyó** (desde #205, el
PDF), lo único que detecta que la fuente cambió sin que nadie tocara la nota. Los calcula
`lib_blocks.py`, el mismo código que después los chequea: **no se escriben a ojo**. ⛔ **Y el bloque escrito se re-parsea antes de publicarse (#284):** `lib_blocks.render_verif_table` escapa cada celda y **rehúsa** devolver un bloque cuya lectura no reproduce lo que se le escribió — sin esa puerta, reescribir una fila leída parte la fila y el ancla se lee de la columna equivocada.

**Salvedades de fuente:** `.txt` con header `source: ocr` → citable con salvedad (ante discrepancia
de símbolos, abrir el PDF). `pdf_source: eprint` → una discrepancia numérica contra un valor
publicado es candidata a **diferencia de versión**, no se "corrige" la nota hacia el preprint. Si
una afirmación no aparece en el `.txt` (ecuación, tabla, escaneo): abrir el PDF o marcar `no
verificable por extracción`. Es **juicio de LLM**, robusto pero no prueba: su tasa de error se mide
con el **auto-benchmark** (`python scripts/bench_verify.py seed` siembra citas falsas deterministas,
el verificador las juzga a ciegas y `score` reporta el recall; nada de eso entra al vault).

**Qué es una `inferencia` y cómo se escribe (D-42).** Una afirmación que la bóveda sostiene y que
**ninguna fuente dice**: sale de combinar dos o más que sí. No es excusa para lo no verificado: es
la declaración de que el respaldo es un razonamiento, para que el consumidor la pese distinto. Se
escribe **nombrando sus premisas** —`(inferencia de [[b1]], [[b2]])`—: sin al menos un `[[bibcode]]`
**el lint la bloquea**. ⚠ El énfasis markdown alrededor no cambia nada (#276); lo que no cuenta es
otra palabra que empiece igual (`inferencial`).

**Regla dura — todo lo apuntable es chequeable:** toda afirmación fáctica va **citada `[[bibcode]]`
o marcada `inferencia`** — nada sin respaldo. ⛔ **Y la cita textual lleva su `[[bibcode]]` PEGADO
(#316/#325):** `«…» [[bib]]`, `«…» (p. 4) [[bib]]`, o en una fila la celda *Fuente*; con prosa en el
medio se declara ambigua — una **mención** posterior le robaba la atribución (6 de 12 bloqueantes).
⚠ La matemática **parte** el chequeo como la elipsis (#326). Excepción: los valores de ground-truth (NEA) en
`stars/` no se verifican contra papers (su consistencia la chequea el lint); sólo se verifican
disputas y afirmaciones atribuidas a un paper. El lint reporta como backlog los conceptos e
hipótesis sin ninguna cita.

### Auditoría de una FICHA (skill `audit-note`)
**El eje que ninguna otra capa mira: ¿esta ficha dice la verdad y se sostiene sola?** El lint chequea
salud estructural, `verify-citations` claim ↔ **su propia** fuente par por par, `find-contradictions`
claim ↔ claim **entre** fuentes, y `auditar` el **framework**. Falta el artefacto **completo**, y no
es teórico: sobre un concepto cerrado —`lint --cierre` en 0, 99 pares `soportada`— una pasada ad-hoc
encontró **más de 40 defectos**: la nota no era implementation-ready (y **cuatro de los cinco huecos
estaban en un `.txt` que la bóveda ya tenía**), dos filas **fusionadas** que hacían invisible una
afirmación verificada, una sección que se contradecía con otra 100 líneas después, y una afirmación
**falsa sobre el propio repo**.
**Cuándo:** a pedido explícito, **nunca** como paso de cierre — es caro por diseño y su valor está
en **garantizar** una ficha antes de apoyarse en ella. **Qué hace:** siete frentes en paralelo
—estándar de la nota (con la prueba operativa de *escribir el pseudocódigo desde la nota y anotar
dónde se traba*), la nota contra sí misma, integridad del artefacto, aritmética, cadena de verdad,
coherencia con el mundo declarado, y la nota contra su cadena—, cada uno declarando **su
población**; barrera; corrección **serial** volviendo a la fuente; y **re-verificación de lo
tocado** (#203). ⛔ **Lo que no se pudo cerrar sale
marcado en la nota** con la cuarta marca en línea (arriba), no en un reporte que se pierde.

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
⛔ **El hallazgo de VERSIONES sobrevive a la corrida (#298): `versions_disponible: <bibcode>`
estampado en la nota** (metadata, no un valor que la prosa citó) + backlog del lint con el
`--rename-paper`. Era la única de las seis que no dejaba nada en la bóveda, y **declara su
población** (3 de 138), porque *«cubrió: versiones»* sin denominador se lee como «se miraron todas».
⚠ Su hueco simétrico es backlog aparte: la nota con **bibcode publicado** que igual lee el preprint
(82 de 138) no tiene problema de identidad, así que ningún detector la ve.
⛔ **Y el REUSO entre slugs (D-18) deja una pregunta hecha, no una respuesta (#297).** Copiar el
artefacto que ya estaba bajo otro slug es correcto, pero importa a un sujeto nuevo un archivo cuya
**antigüedad nadie chequeó** — y la salida natural («si hubiera versión nueva la búsqueda habría
traído otro bibcode y D-19 los une») es falsa en el caso frecuente: el DOI del preprint identifica el
**depósito**, así que preprint y publicado **no** colisionan (#216). La línea del reuso declara `pdf_source` y fecha y dice que **no se chequeó**; el
detector se puede correr acotado (`sweep_external.py --bibcodes b1,b2` — unidades, no el corpus, y
**no** registra la pasada); y el lint lo levanta como backlog, junto con *«`_red.yaml` no existe»*
—una bóveda donde `sweep_external` nunca corrió no tiene **ninguna** de las seis caducidades
chequeadas, y eso no se veía en ningún lado—.
⛔ **Reporta, no aplica solo — con UNA excepción nombrada** (AUD-206): el diff se muestra y se
pregunta antes de tocar nada, porque un snapshot que se actualiza solo cambia valores **bajo los
pies de la prosa que ya los citó**. La excepción es **`retracciones`**: `check_retractions` estampa
`retracted:` / `corrections:` en las notas **sin preguntar**, a propósito — una fuente retractada
citada rompe la frontera dura, así que enterarse tarde es peor que el ruido de diff, y lo que
escribe es una **marca de metadata**, no un valor que la prosa haya citado. Los otros cinco no
escriben: versiones y web proponen el comando, ground-truth pregunta, citas-puerta2 reporta el
cruce. Lo automático es la consecuencia offline: al cambiar un `.txt`, el **ancla de fuente** (D-20)
marca sola los pares verificados contra él. El ground-truth **no** lo cubre esa ancla (no es un
`.txt`): al aplicar se registra `_cambios` en el JSON y el lint pide la marca `⚠desactualizado`. El
renombre preprint→publicado **nunca** es automático (reescribe wikilinks de toda la bóveda): se
propone el comando.
La caducidad se registra **versionada** en `vault/config/registro/_red.yaml` — "cuándo se miró
afuera" es información de la bóveda, no de la máquina. Un detector que **no pudo correr** se
declara y **no** entra en `cubrio`: el registro no puede afirmar haber mirado lo que no miró.

**Fuente retractada citada en prosa (D-47):** la afirmación **no se borra** —puede ser cierta por
otra vía—: se **marca en línea** con `[[bibcode]] ⛔retractada`. Sin la marca el lint **bloquea**. Un
`(retractada)` pelado daría falso positivo con cualquier mención en prosa.

**Ground-truth que cambió bajo la prosa (AUD-42):** el ancla de fuente (D-20) hashea
`raw/fulltext/**/*.txt` y **nunca** `raw/ground_truth/<slug>.json`, así que cuando NEA corrige un
valor la frase que ya lo citaba queda verde y **ninguna fila se entera**. Al aplicar un diff,
`sweep_external` deja `_cambios` en el JSON y el lint **pide la marca** `⚠desactualizado` pegada al
valor: no se borra, se hace visible.

**El conteo de citas que mueve la puerta 2 (#106 / INV-104).** La puerta 2 admite un paper como core
por `citation_count`: metadata del paper —INV-24 sigue en pie, el veredicto es re-derivable offline—
y la única que **cambia sola**: un paper puede volverse core sin que nadie edite nada. ⛔ La regla no es *"core no puede cambiar"* —sería falsa— sino **"todo
cambio de veredicto es visible y fechado"**. Se vigila por los dos lados, cada uno con su alcance:
**`lib_config.puerta2_cruces`** (offline, lo reporta el lint) compara el umbral vigente contra el
que guardó el registro —*"editaste el umbral"*— y **`sweep_external.sweep_citas`** re-consulta los
conteos —*"el mundo se movió"*—. Ninguno aplica nada. El umbral se persiste con
`query_ads.lens_used(meta)` y se compara con `in`, no por truthiness: un `fundacional_min_citas: 0`
(abre para todos) es una decisión y no se lee igual que no declararlo (no abre).

**Lo que no se pudo verificar queda MARCADO en la ficha (#225): `<afirmación> ⚠verificar en el PDF
(<qué se dudó>, <fecha>)`.** La producen `audit-note` y `contrast --validar` (#341) —una sola
definición, `lib_config.verificar_pdf_mark`— y tiene las propiedades de las otras: **no
destruye** la afirmación, es **visible**, **la levanta el lint** y **se saca cuando alguien la
verifica**, con la evidencia. El criterio es amplio a propósito: **ante la menor duda se marca** —
una marca de más cuesta abrir un PDF; una de menos deja a la bóveda afirmando algo falso con cara de
verificado. ⚠ No es excusa para no verificar: si
la fuente está en disco, se abre.

**Una entrada de `log.md` que quedó REFUTADA se MARCA, no se edita (#238): `⚠ corregido <fecha> →
<entrada nueva>`.** La bitácora es append-only por contrato y eso la dejaba sin forma de corregirse:
medido, una entrada publica como cita textual **con página** una frase que **invierte el sentido**
de lo que dice el paper. Misma doctrina que las otras marcas —hacer visible, no borrar—: el lint
chequea las citas textuales del `log.md` contra el `.txt` de su bibcode, salvo que lleven la marca.
⛔ **La exención la decide UNA función (`lib_config.log_quote_exempt`) y la llaman los dos chequeos
(#386):** una convención en prosa **no compone**, y ya divergía —el lint la honraba, `contrast
--validar` no la conocía—, así que la entrada marcada bloqueaba el gate de #323 para siempre. ⛔ **Y
la entrada que CITA una cita defectuosa para explicarla la pone en un blockquote (#387): ahí es
mención, no afirmación** — sin eso el caso reflexivo no tiene salida. Las dos valen **sólo en
`log.md`**: en una nota la corrección se hace editando.

Éstas son las **cinco únicas marcas en línea** del sistema: `(inferencia de [[bibcode]])`,
`[[bibcode]] ⛔retractada`, `<valor> ⚠desactualizado`, `<afirmación> ⚠verificar en el PDF` y
`⚠ corregido <fecha> → <entrada nueva>` (sólo en `log.md`).

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

⛔ **Una PROPUESTA no es deuda, y por eso tiene su propia superficie (#328).** La deuda falta y se
**agenda** —la reporta el lint—; una propuesta el sistema la sugiere y necesita que alguien **firme**.
Envejecen distinto: la deuda persiste hasta que se cierra, la propuesta **se pierde si nadie la lee
cuando aparece** (medido: el pedido de ampliar el `alcance` de un libro quedó en el `hueco` de uno de
43 JSON y lo vio alguien de casualidad). `python scripts/proposals.py [<slug>]` las junta con **su
motivo textual** —no una categoría: en seis meses sirve el motivo—, declara su población y declara
**lo que no puede barrer** (un eje descubierto en 3b vive en la conversación). Reporta y no aplica.

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
**aparte** (*«visible, no es deuda»*), nunca mezclado con la deuda real. Dos reglas del reporte:

- **⛔ No evaluado cuenta para el exit** (D-43): un chequeo que no pudo correr (`objective.yaml`
  ilegible, sin `git`) suprime su categoría normal — un `(0)` que nadie midió se lee como veredicto,
  y ése es el falso limpio que el lint existe para no producir. Misma doctrina en `query_ads`:
  rehúsa clasificar con una lente ilegible en vez de degradar a `{}`.
- **Cada categoría declara su población** (INV-40): `> sobre 412 notas de vault/wiki/`. Un `(0)` no
  distingue *«miré todo y no hay nada»* de *«no miré nada»*.

**Bloqueantes** (0 para cerrar; detalle y migradores en `docs/lint.md`): wikilinks rotos ·
frontmatter no parseable o con forma inválida (la nota evade en silencio los chequeos de su tipo) ·
papers retractados · páginas huérfanas (el `index.md` estampado NO cuenta como link entrante, #249)
· contradicciones ground-truth↔ficha, campo por campo (#70) · masa inconsistente con la m·sini
implícita · `thesis_links` sin página destino · `disputes` mal formadas, con `ref` sin destino o en
schema viejo (#71) · schemas retirados (`topics:`, `busqueda:`, `bearing`, `symbols_lost`/
`fulltext_layout`, `## Extracción (LLM)` sin `vistas[]`) · `role` fuera del vocabulario ·
incoherencia `vistas[]` ↔ cuerpo · juicio de triage en `build/` (pre-1.9.0) · fila de tabla con más
celdas que su encabezado (#227: GFM la vuelve invisible) · registro ilegible (AUD-131: revierte la
curación entera — `load_decisiones` rehúsa operar y `save_registro` rehúsa pisar) · veredicto
`no-soportada`/`contradice` sin resolver (#91) · bloque de verificación con plantilla vieja ·
`Hash fuente` sin prefijo (#117) · duplicado por identidad (D-19/#229) · `inferencia` sin premisas
(D-42) · fuente retractada citada sin la marca `⛔retractada` (D-47).

**La fuga de implementación** (regla #0) es **WARN**: heurística de alta señal, cada hit se revisa
a mano. No mira las `SECCIONES_ESTAMPADAS` (#214), y la exención no alcanza a `## Vista — <sujeto>`.

**El cierre toma el SUJETO: `python scripts/lint.py --cierre <slug>` (R-1, #121).** Un solo detector,
dos severidades: sin flag, los pares de verificación vencidos (D-4/D-20) y la cobertura de
verificación reportan como **backlog** (pasada periódica); con `--cierre` **bloquean** — un par sin
verificar significa que no terminaste (D-5: la nota nace 100% verificada, así que "citas sin bloque"
no es deuda vieja). Con el slug, el alcance son las notas del sujeto (ficha/concepto + papers,
incluidos los retro-linkeados); ⚠ dos recortes deliberados: **el reporte no se acota** (la deuda
ajena se lista, marcada *«no frena»*) y **el alcance acota sólo la severidad de cierre** (un
bloqueante cuenta venga de donde venga). Slug inexistente → rehúsa (exit 2). Sin argumento, pasada
de cierre global. Los skills de cierre lo invocan con el flag; la higiene de `maintain`, sin él.

## Seis reglas de método (por qué existen las redes de abajo)

Salieron de medir una sesión entera donde **los defectos los encontraron agentes leyendo el código,
no la suite**. No son consejos: cada una nombra un modo de falla que ya ocurrió acá (la medición
vive en su issue y en `docs/mediciones.md`), y las redes de la sección siguiente son su
mecanización.

1. **Un test con la red falseada valida que el CLIENTE funcione, no que el CONTRATO se cumpla.** Si
   escribís un cliente de red, **probalo una vez contra el servicio de verdad** antes de darlo por
   hecho — los tres bugs serios de la Tanda 7 los encontraron el smoke test real y una auditoría
   adversaria; ninguno la suite, que estaba verde.
2. **Un doble de test con distinto contrato que la función real esconde el bug en la diferencia**
   (medido en `refs_of`: el doble indexaba por el input verbatim y el real por `_bare_doi`). Un
   doble o deriva de la función real, o tiene un test de paridad.
3. **Un test verde recién escrito no cuenta hasta que lo viste morir — POR LA RAZÓN QUE PRUEBA.**
   La pregunta no es *«¿falló?»* sino ***«¿murió por la línea que estoy probando?»***, y se contesta
   mirando **el mensaje del fallo**, no el rojo (#196/#197: un test que fallaba por el setup pasaba
   sin el fix; dos tests sobrevivieron a mutar la guarda que decían proteger). La forma barata de
   contestarla es la **mutación dirigida** (#204): `python tools/mutar.py --dirigida
   scripts/<módulo>.py`.
4. **Un mapa que atribuye mal es peor que uno vacío**: el vacío se ve, la atribución falsa se lee
   como verdad. Vale para `docs/trazabilidad.md`, `docs/contrato.md` y cualquier tabla estampada.
   ⛔ **Todo chequeo que mire texto de una nota NORMALIZA EL MARKDOWN primero** (#168, #276, #283,
   #309): cuatro veces la misma ceguera —el adorno, el énfasis, el escape— y la cuarta dejaba al
   operador eligiendo entre un bug de renderizado y un backlog permanente.
5. **Cuando dos mediciones no reconcilian y no se puede re-medir, se DECLARA la discrepancia**; elegir en silencio es cómo un documento empieza a mentir.
6. **Fan-out para LEER, aplicador serial para ESCRIBIR, barrera antes de CONSUMIR — y lo escrito se
   RE-VERIFICA.** El aislamiento del fan-out no se toca; lo que no escala es la **escritura**: dos
   correctores sobre el mismo bloque lo corrompen en cadena (#197) y derivar trabajo de una etapa
   que todavía corre deja hallazgos que no mira nadie (#199). **Un solo escritor, y una barrera
   antes de que algo consuma resultados.**
   - ⛔ **El aplicador comparte la definición de «bloque» con quien produce los pares (#222)**: dos
     implementaciones de la misma regla ya costaron pares desaparecidos sin señal — la red barata es
     **contar los pares antes y después y abortar si bajaron**.
   - ⛔ **La cuarta cláusula (#203): el ciclo cierra en *corregir → re-verificar lo tocado*.** Un
     corrector que abrió la fuente escribió igual un valor falso nuevo, y lo cazó el ancla de
     rebote: un aplicador no valida lo que aplica.
   - ⚠ **Y ese ciclo NO CONVERGE solo (#282):** el ancla es de **bloque**, así que cada ronda vence
     los pares vecinos y produce trabajo del tamaño de la anterior. La salida **no es aflojar el
     ancla** (#224: el sub-disparo es la única dirección prohibida): es distinguir la corrección que
     **cambia lo que la afirmación dice** (se re-verifica) de la **derivada de la propia
     verificación** (se re-ancla, no se re-pregunta). Lo emite `python scripts/reverify_subset.py
     <nota>` (#257): re-anclables / a re-verificar / filas huérfanas. ⛔ **Propone y no escribe**;
     empareja por **cobertura del extracto** (#226) y **nunca cruza `bibcode`** — llevar un
     veredicto de una fuente a otra sería fabricar la atribución que este framework más persigue.

Corolario que las cruza a todas: **una promesa que el sistema dejó de cumplir en silencio es peor
que una que nunca hizo.** Si al tocar algo se rompe una promesa declarada, eso **se anota**, aunque
no se arregle en el momento.

## Convención de idioma del código (desde 2026-08-24)

**Archivos, nombres de funciones, docstrings y comentarios NUEVOS en inglés.** La prosa de la
documentación (`CLAUDE.md`, `README.md`, `docs/`, los `SKILL.md`) y la de la bóveda siguen en
castellano. **Sin retrofit**: lo que ya está escrito no se renombra.

La red es `tests/test_idioma_codigo.py` con ratchet en `tools/idioma-ratchet.yaml` (#156: la regla
existió sin casa ni gate y el resultado fueron 30 funciones nuevas en castellano — *o la regla tiene
casa y red, o no es una regla*). Vigila las tres mitades: `simbolos` (nombres castellanos),
`docstrings_castellano` (heurística declarada, mide el **delta**) y `sin_docstring` (acá el
docstring **es** el contrato de la función — el frente C de `/auditar` audita que se cumpla). Los
tres techos **sólo bajan** y ninguno es un rojo: son deuda anterior a la convención; un nombre nuevo
fuera de la lista `conocidos` pone el test en rojo aunque el total no suba (impide que la deuda
rote). Los números los dan las funciones del test, no esta prosa.

## Al escribir código: las nueve redes (regla permanente)

Toda función nueva de `scripts/` **y de `tools/`** pasa por esto **antes de cerrar el issue**; la 6
rige también para los scripts de una sola operación. ⛔ **Las redes 1 y 4 cubren `tools/` desde
#345** (`mutar.ALCANCE`, que la red 4 **importa** en vez de repetir, para que no diverjan): acotarlas
a `scripts/` dejaba sin red a **la herramienta que las ejecuta**, medido en 5 guardas de
`tools/mutar.py` sin un test que las distinga. La **única exención es `tools/refresh_issues.py`** y
se **declara con su motivo** en `mutar.EXENTOS_MODULO`, nunca por omisión del alcance: es un cliente
HTTP contra la API de GitHub y la **regla de método 1** manda probarlo contra el servicio real, así
que mutarlo sólo mediría el doble. Los tres estados de `scope_refusal` —fuera de alcance · exento ·
sin `tests/test_<mod>.py`— piden acciones opuestas, y una selección **toda** exenta sale *no
evaluado*, no verde. Detalle y ratchets en `tests/README.md`; el resumen operativo:

1. **Mutación** — romper cada función y exigir que **algún test muera**: es lo único que distingue
   "el test pasa" de "el test **podría** fallar". Trabaja sobre una copia del repo. Tres modos:
   - **Dirigida** (`python tools/mutar.py --dirigida <scripts|tools>/<mód>.py [--solo f,g]`) — **es un
     paso al escribir una función con guardas** (#204): un módulo, sólo su archivo de tests, ~0,44 s
     por mutación. Sobre-reporta sobrevivientes y nunca da falso limpio (la dirección segura); no
     toca el ratchet. **Rehúsa** si el módulo no tiene `tests/test_<módulo>.py` o nada mutable —
     cero mutaciones no es «murieron todas» (D-43).
   - **Guardas** (`python tools/mutar.py --guardas <scripts|tools>/<mód>.py [--solo f,g]`, AUD-213) —
     vaciar el cuerpo no mide las **condiciones**: muta cada `if` interno a `False` y, en un
     `and`/`or`, **cada cláusula por separado** (sólo eso revela la cláusula que ningún test
     ejercita). Mismo contrato que la dirigida; una condición constante se saltea (el hallazgo sería
     inventado). ⚠ Es el único modo que chequea la **baseline**: con el archivo de tests en rojo,
     toda guarda «muere» por el motivo equivocado (#202) → sale **no evaluado** (rc 2), no un verde.
   - **Barrido** (`--diff` / `--todo --ratchet`) — corre en **dos etapas** (#187: primero
     `tests/test_<módulo>.py`, sólo los sobrevivientes pagan la suite). Medido 2026-08-31: `--todo`
     = **32,5 min / 655 funciones** (#345). **Cadencia: a pedido, y recomendado al cerrar una tanda**, con el árbol
     **quieto** (#199: el barrido copia el repo al arrancar; si seguís editando, su resultado
     describe un árbol que ya no existe).
2. **Schema compartido** — si N módulos prometen la misma forma, se prueba **una vez parametrizada**
   (`tests/test_backends_schema.py`), no con prosa en N docstrings.
3. **Doble vs real** — un doble de test no se escribe a ojo: o deriva de la función real, o hay un
   test de paridad (regla de método 2).
4. **Nadie sin ejecutar** — `pytest tests/poblada/test_cobertura.py -m poblada` (~11 s): una función
   que la suite nunca corre no está "mal probada", está **sin mirar**. Mismo alcance que la 1.
5. **La doc es ejecutable** — `tests/test_docs_ejecutables.py`: todo test, script y config que la
   documentación nombra existe, y todo comando de skill compila.
6. **Corré dos veces y hasheá** — para **todo script que escriba en `vault/`**, versionado o de una
   sola operación (la idempotencia es invariante del framework):
   ```bash
   H=$(find vault -name '*.md' -exec md5sum {} + | sort | md5sum); <el comando>; \
     [ "$H" = "$(find vault -name '*.md' -exec md5sum {} + | sort | md5sum)" ] && echo IDEMPOTENTE
   ```
   ⚠ **La idempotencia es sobre CONTENIDO, no sobre la bitácora (#105):** el chequeo hashea
   `vault/**/*.md` y **no** `vault/config/registro/`, a propósito — D-28 hace que el registro
   **crezca** en cada corrida. Las dos reglas conviven: **la nota no puede cambiar si no cambió lo
   que afirma; el registro tiene que crecer aunque no cambie nada.** El bloque propio va entre
   centinelas (`<!-- almagesto:… -->`) y lo de afuera no se toca (`make_notes._reemplazar_seccion`
   ya lo hace).
7. **Idioma** — `pytest tests/test_idioma_codigo.py` (ver arriba).
8. **Condicional que no decide nada** — `tests/test_codigo_muerto.py` (#319): el ternario cuyas dos
   ramas valen lo mismo es una regla escrita a medias y **ningún otro gate la ve** (no cambia
   comportamiento: no hay test que matar). Se encontró leyendo un commit; ahora es un assert.
9. **Atribución del mapa** — `python tools/mutar.py --trazabilidad` (AUD-212, ~20 min): vacía cada
   implementación marcada `@inv` y corre **sólo el test marcado**; si pasa, esa fila de
   `docs/trazabilidad.md` afirma una cobertura que no existe (20 atribuciones falsas sobre 143 en la
   primera corrida). ⚠ Sobre-reporta y nunca da falso limpio: ante un sobreviviente por
   coincidencia se marca un test que ejerza la rama verdadera, no se afloja el gate.

Las 2, 5, 7 y 8 corren solas en tier 0; la 1 y la 9 son a pedido (cuestan minutos). El motivo de la
regla: en la sesión que la produjo, los bugs los encontraron agentes leyendo el código, no la suite
— y cada hallazgo era decidible, o sea que podría haber sido un assert.

⚠ **La red que no mira el código nuevo no es una red (INV-101):** el gate de mutación seleccionaba
con `git diff --name-only HEAD`, que no lista untracked, así que un archivo recién creado salía en
verde sin mutarse. Antes de creer un gate, confirmá **sobre qué corrió**.

## Token / secretos
El token ADS va en `vault/config/ads_dev_key` (**gitignored** — nunca se commitea) o en la variable de
entorno `ADS_DEV_KEY`.
⛔ **El `mailto` del polite pool es OPT-IN y no sale de `git config user.email`.** OpenAlex, Crossref
y Unpaywall dan un tier de rate-limit más rápido a quien declara un email de contacto. Se declara en
`vault/config/mailto` (gitignored) o en `ALMAGESTO_MAILTO`; **sin declararlo no sale ninguna
dirección** y las tres APIs funcionan igual, en el pool público. Hasta 1.73.0 se tomaba el email de
git —dato personal entregado para autoría, no para egress a tres terceros—: medido el 2026-08-28,
doce llamadas lo llevaron embebido en la URL, y por lo tanto en cualquier `raise_for_status` y en
cualquier log de proxy. Token gratis en <https://ui.adsabs.harvard.edu/user/settings/token>.
`build/` y `outputs/` gitignored. PDFs por git-lfs (`vault/raw/pdfs/**/*.pdf`). El resto de
`vault/config/` **sí se commitea**, incluido `registro/<slug>.yaml` (es el punto: el juicio de
curación y el registro de búsqueda tienen que viajar).
