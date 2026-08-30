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
> vive en `docs/internal/HANDOFF.md`, que no se versiona.)* ⛔ **`index.md` se ESTAMPA
> (`python scripts/make_notes.py --restamp-index`, #237), no se edita a mano.** Era el único
> artefacto que quedó **100 % Dataview** —exactamente lo que #60 prohibió para los roll-ups, y con
> más fuerza acá: el catálogo es lo primero que un agente abre para orientarse, y un bloque
> ```dataview``` le muestra **la query, no sus resultados**, con el plugin sin versionar
> (`.obsidian/plugins/` está gitignored mientras `community-plugins.json` declara `dataview`)—. El
> efecto medido: el paso de bookkeeping de los skills mandaba *«agregar la estrella/el concepto a
> `index.md`»* sobre un archivo **sin una sola línea estática**, así que el paso no se podía cumplir
> como estaba escrito, y los tres commits del `index.md` de una bóveda real son anteriores a su
> instanciación. Hoy las tres tablas se materializan por verdad de frontmatter, el Dataview queda
> **debajo** como comodidad de Obsidian, y el lint reporta el índice desactualizado **nombrando los
> stems** (mismo criterio que D-10 para `## Papers`). La "memoria" del proyecto es in-repo: este `CLAUDE.md` + `vault/STATUS.md`
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

**Cómo (#205):** abrí el **PDF** (`vault/raw/pdfs/**/<bibcode>.pdf`) y citá **página**. El `.txt`
sirve para *ubicar* con `grep -n` en qué parte mirar, no para citar: es el índice de búsqueda, y
pierde fórmulas, tablas-imagen y figuras **sin avisar** — medido, incluso en papers donde todos los
chequeos de calidad dan verde. Un `grep` vacío sobre el `.txt` **no** significa que la ficha esté
mal. Si la nota declara `pdf_source: eprint`, el PDF es el preprint: una discrepancia numérica
contra un valor publicado es candidata a diferencia de versión, no a error de la ficha.

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
  fuente), `concepts/{methods,hypotheses}/` (⚠ las áreas son **abiertas**: ésas son las dos que el
  framework distingue de verdad, cualquier otra que declares es **archivado** — ningún chequeo se
  ramifica por el área, #246), `queries/`, `matrices/`,
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
cuando aplique `confidence: high|medium|low`.

> **Dónde está el "por qué".** Cada regla de acá lleva su `(#N)` o `(D-N)`: el issue público
> (`github.com/nicklessagus/Almagesto/issues`) tiene el caso que la produjo y la medición;
> `docs/contrato.md` tiene el invariante; `docs/mediciones.md`, la evidencia con su corpus y su
> fecha. Este archivo lleva **la regla y su consecuencia**, que es lo que hay que saber antes de
> escribir una nota.

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
que la ficha alcance sola) y el apéndice **`## Excluidos por el filtro`** (los no-core, top por
citas con link a ADS — puntero, no se bajan).

**Estándar: autosuficiente.** La ficha debe alcanzar por sí sola — un agente que la lee queda
servido **sin abrir ningún paper**: parámetros estelares, inventario de señales RV con $P/K/e/m\sin
i$ y estado, señales disputadas o descartadas, indicadores de actividad esperados, métodos aplicados
y huecos. Corta y suficiente. Los `[[bibcode]]` son **trazabilidad**, no lectura obligatoria. Si
para responder algo hace falta abrir el paper, eso que falta va a la ficha.

**Regla de poda (paper secundario → ficha sólo si cambia una señal RV).** Un hecho de un paper
tangencial (no discovery, no árbitro de planetas, no actividad-$P_{rot}$) entra a la prosa
**únicamente si cambia cómo se lee una señal RV** (p. ej. un mecanismo que produce falsos positivos
en el régimen de período de un planeta dudoso). Todo lo demás —era instrumental, metodología RV
genérica, dinámica, ausencia de tránsito, debris, astrosismología, habitabilidad— vive en su nota de
paper y se consulta por la tabla `## Papers`. No re-narrar en la ficha lo que ya está en la
extracción.

#### Los tres roll-ups se ESTAMPAN, no son Dataview (D-10/D-11)

`## Papers`, `## Planetas` y `## Métodos aplicados a esta estrella` los regenera
`python scripts/make_notes.py <slug>` (idempotente, cirugía: no toca la prosa); el lint reporta como
backlog la tabla desactualizada **nombrando los stems**. `## Papers` es una tabla materializada
—`Bibcode | Año | Relevancia | Origen | Estado`— cuyo encabezado lleva **los dos números** (universo
· sintetizados en esta ficha): el defecto que evita es prometer 155 arriba de una síntesis de 8. El
**estado** dice cuán lejos llegó cada paper: `fuera del filtro` → `sin extraer` → `extraído, no
sintetizado` → `sintetizado`. En un concepto el roll-up es la **unión** de `methods` y
`thesis_links`, con la columna *Entró por* (D-24: esas dos llaves viven en papers distintos).

El motivo (#60): un bloque ```dataview``` le muestra a un agente que abre el `.md` **la query, no
sus resultados**, y el plugin ni siquiera está versionado. El equivalente determinista parsea el
frontmatter con el mismo parser que el tooling (`lib_config.split_fm`), desde la raíz del repo:

```bash
# papers de una estrella (equivale al roll-up `## Papers`)
python -c "import sys,glob;sys.path.insert(0,'scripts');import lib_config as c;[print(f) for f in sorted(glob.glob('vault/wiki/papers/*.md')) if '<nombre>' in (c.split_fm(open(f,encoding='utf-8').read()).get('stars') or [])]"
# métodos aplicados a esa estrella (los métodos DE los papers de la estrella, no todo paper que use el método)
python -c "import sys,glob;sys.path.insert(0,'scripts');import lib_config as c;[print(f,'→',fm.get('methods')) for f in sorted(glob.glob('vault/wiki/papers/*.md')) for fm in [c.split_fm(open(f,encoding='utf-8').read())] if '<nombre>' in (fm.get('stars') or []) and fm.get('methods')]"
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

⚠ **El roll-up de métodos linkea `[[método]]` sólo si la nota existe; si no, lo estampa como
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
lee: lo detecta y bloquea**, con el comando de migración
(`python scripts/make_notes.py --migrate-disputes`) — una disputa que el lector ignora en silencio
es peor que un error.

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
de la nota sobre un eje es indistinguible de «se miró y no hay nada»**.

Cada entrada de `vistas[]`: `sujeto` (el mismo nombre que usan `stars[]`/`thesis_links[]` — es lo
que hace comparables reclamo y lectura), `tipo` (vocabulario **cerrado** `star | theme`, declarado y
no derivado, para que el lint cace el typo), `fecha`, `txt` (de qué copia del `.txt` salió — el
ancla de fuente cuando el mismo bibcode vive bajo varios slugs), `lente` (las facetas vigentes al
leer) y `fuente`. La sección del cuerpo es `## Vista — <sujeto>` y **no** es sección estampada: es
exactamente lo que `verify-citations` contrasta contra la fuente. El lint **bloquea** la
incoherencia en los dos sentidos (vista declarada sin su sección; sección sin declarar) y el schema
viejo (`## Extracción (LLM)` sin `vistas[]`). **Forma dura como `extra_core`** (D-58): el escalar y
la lista de strings bloquean.

⛔ **`txt` se cruza contra el DISCO al estamparse (#230).** Un ancla que apunta a la nada no ancla.
La asimetría con `fuente: pdf` es deliberada: aquélla **rechaza** la extracción, ésta **degrada
declarando** — si el `.txt` vive bajo otro slug se apunta ahí; si no existe en ningún lado **la
clave no se escribe** (*no consta*, nunca un puntero falso), porque desde #205 una vista puede
legítimamente no tener `.txt` y rechazarla tiraría una lectura buena.

⛔ **`fuente` dice DE QUÉ se construyó: `pdf` | `abstract` (#207).** Un paper sin PDF **no es
inextraíble**: ADS, OpenAlex y arXiv devuelven el abstract, y ése puede traer lo que la ficha
necesita. Lo que no puede pasar es que una lectura de ocho líneas quede indistinguible de haber
leído el paper —y encima el abstract es justo donde la fuente afirma **de más** (*generalization
bias*)—. Lo **declara el extractor** (el único que sabe qué abrió) y el **cosechador lo cruza contra
el disco**: `fuente: pdf` sin PDF **rechaza la extracción entera**, porque adivinar cuál de las dos
mitades miente es lo que el campo existe para evitar. Ausente = *no consta*, backlog;
`fuente: abstract` también, pero ahí el pedido es **conseguir el PDF**.

⛔ **La `fecha` es lo que dice que la lectura OCURRIÓ.** El stub nace con la vista de su sujeto y
**sin** fecha (la ausencia es *no consta*), así la nota es coherente desde el minuto cero y el lint
reporta la vista sin fecha como backlog. La estampa el **cosechador**
(`python scripts/harvest_views.py <slug> [--theme]`), que además mergea `methods`/`thesis_links`/
`role` add-only, escribe la sección mientras siga siendo la plantilla del stub —prosa redactada no
se pisa sin `--force`: puede tener anclas de verificación colgando del texto exacto— y **trae el
`.txt` al slug del sujeto** (D-18), sin lo cual la vista de un paper retro-tagueado no es ejecutable.

⛔ **Las `salvedades` sobre el ARTEFACTO se chequean con un script, o se publican marcadas NO
VERIFICADAS (#213).** Una salvedad del tipo *«el `.txt` perdió este símbolo»* no lleva `[[bibcode]]`
—es una afirmación sobre el archivo, no sobre el paper— así que `verify-citations` la deja afuera
**por construcción**. Dos mitades:

- La salvedad que hace una afirmación **decidible sobre un archivo** se emite **estructurada**, con
  vocabulario cerrado (`lib_config.SALVEDAD_TIPOS`: `txt_pierde` con su `cadena`, `pdf_paginas` con
  su `n`), y la chequea el **cosechador** con `grep` o `pdfinfo` — máquina, no LLM. La que resulta
  **falsa NO se publica** y el cosechador la grita con su archivo; ⚠ pero **no tira la extracción**
  (a diferencia de #207: aquello es una contradicción sobre *qué se abrió*; esto es un campo
  secundario que se descarta sin perder la mitad más cara de la cadena). El chequeo que **no pudo
  correr** —sin `.txt`, sin PDF, sin `pdfinfo`, `tipo` con typo— sale **no evaluable con su motivo**,
  nunca «verificada» (D-43).
- Todo lo demás se publica en su **propio bloque**, marcado *«⚠ NO VERIFICADAS — juicio del
  extractor»*: publicarlo al mismo nivel visual que una fila chequeada es lo que dejó leer un
  defecto inventado como un hecho medido.

⛔ **La lectura puede RETRACTAR el reclamo que la trajo: `refuta: [<sujeto>]` (#212).** Es el único
canal en esa dirección: `stars`/`thesis_links` se siembran **antes** de leer y `harvest_views`
mergea **add-only** —lo cual protege la extracción de que un re-seed la pise—, así que un reclamo
falso era **infalsificable por la lectura**. El caso típico es la **polisemia** (un paper entra a un
tema por un término que usa en otro sentido). ⛔ El cosechador **registra y propone, no aplica**:
deja el `refuta` en la vista e imprime el `--drop-core` con su motivo listo para pegar, porque
borrar el reclamo sería un LLM editando curación en silencio y porque la decisión es del **par
(paper, sujeto)** — el paper puede ser core de otro. El lint lo reporta como **backlog**. El
add-only **no se afloja**.

⛔ **`vistas[]` la escribe SÓLO la lectura, nunca el retro-link.** Es lo que mantiene a
`stars`/`thesis_links`/`methods` como **reclamos** (`make_notes` los mergea add-only sin leer nada)
y a `vistas[]` como **lecturas**. Un reclamo sin vista es backlog, y se cierra de dos maneras:
haciendo la vista, o declarándola `no_vista: [{sujeto, motivo}]` cuando ese sujeto sólo aporta al
roll-up. **Motivo obligatorio y por sujeto**: un paper que tres sujetos reclaman se saltea por
motivos distintos en cada uno, y una escotilla sin sujeto los eximiría a los tres. Qué cuenta como
reclamo: `stars` y `thesis_links` siempre; `methods` **sólo si ese nombre es un tema declarado** —lo
puebla la extracción, así que es producto de la lectura, y contarlo entero haría nacer el backlog
con centenares.

⛔ **Sacar `pending_source` no puede romper el frontmatter (#244).** El borrado de una clave es **una
sola función**: filtrar por `startswith` se lleva la primera línea de un escalar multilínea y deja
huérfanas las de continuación, con lo que el YAML deja de parsear y la nota pasa a evadir **todos**
los chequeos de su tipo. No es raro: `pending_motivo` es de texto libre, así que cualquier motivo
largo se serializa multilínea. La red es la de #222: se re-parsea el frontmatter y **no se escribe**
si dejó de parsear — una operación no puede dejar la nota peor de lo que la encontró.

#### Identidad: el `doi`/`arxiv_id`, no el bibcode (D-19)

El preprint y el publicado son bibcodes distintos del **mismo** paper: dos notas ahí son doble
conteo, dos fuentes donde hay una, y un falso positivo permanente de #75. Hay **una sola nota
canónica** y los bibcodes viejos viven en `versions[]`; el lint bloquea el duplicado y `make_notes`
**rehúsa crear** la segunda nota.

⛔ **Un bibcode listado en `versions[]` que TIENE su propia nota BLOQUEA (#229).** La exención por
alias es incondicional: listar un bibcode ahí lo saca de los **dos** chequeos de identidad, tenga
nota o no. O es un alias (y entonces **no debe haber nota**) o es otro trabajo (y entonces **no va
en `versions[]`**); la relación *«mismo programa, resultados distintos»* se declara en **prosa o en
`salvedades`**.

El ciclo se resuelve con `python scripts/make_notes.py --rename-paper VIEJO NUEVO`, que mueve la
nota y sus artefactos (`raw/pdfs/`, `raw/fulltext/` **y la extracción de `build/<slug>/extraccion/`**
— #228: `harvest_views` mapea JSON→nota por `data["bibcode"]`, así que una extracción dejada bajo el
bibcode viejo hace que el cosechador saltee la nota **para siempre**, y una extracción no se
regenera sin volver a pagar el paso más caro), **re-estampa la cabecera**, deja `bibstem` en `null`
—es verdad de catálogo y el renombre no tiene catálogo—, agrega el alias y **reescribe los wikilinks
de toda la bóveda**. Alcance declarado: `vault/`.

⛔ **El duplicado SIN `doi` ni `arxiv_id` lo reporta otra categoría (#216, backlog).** La clase de
fuentes donde el problema es **más** probable es justamente la que no tiene identificador —resúmenes
de congreso, tesis, material pre-DOI—, así que `identidad()` devuelve claves distintas y el detector
bloqueante no puede verlo. La señal es el **`## Abstract` verbatim** normalizado y comparado por su
**arranque** (el caso típico viene truncado en una de las dos copias). ⛔ **NO se deduplica por
título**: está medido en `openalex.py` y es peor que el problema. Y **reporta, no fusiona**: la
distinción *«mismo trabajo en dos congresos»* vs *«dos etapas del mismo programa con resultados
distintos»* es real. La salida es `--rename-paper` + `versions[]`, o `--drop-core` con motivo.

#### Los dos artefactos y sus dos `*_source`

`pdf` es **lo que se lee** (extracción y verificación) y `fulltext` el **índice de búsqueda** del
corpus (`grep`), con los roles que fijó #205. Los estampan `make_notes`/`extract_fulltext` por
verdad de disco (`null` si no hay extracción).

⛔ **Los dos `*_source` NO se comportan igual cuando el archivo desaparece (#230).**
`fulltext_source` describe **cómo se extrajo un archivo**, así que se limpia con él (el lint marca
como backlog el par `fulltext: null` + `fulltext_source: <valor>`). **`pdf_source` sobrevive**, a
propósito: no describe el archivo sino la **procedencia de la lectura que ocurrió** —una nota cuelga
su salvedad de `pdf_source: eprint` para decir que sus citas son contra el preprint—, así que
borrarlo destruiría la salvedad junto con el archivo. El par `pdf: null` + `pdf_source: <valor>`
**no es hallazgo**.

Cuando un paper vive bajo **varios slugs** el campo es **estable**: la copia ya estampada se mantiene
salvo que llegue una de **mejor calidad** (`pdftotext`/`web` > `ocr`); no se repunta al slug que
corrió último (idempotente, sin ruido de diff).

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
dos discriminaba (#193, #194). Migrador `python scripts/make_notes.py --migrate-txt-fields`; el lint
**bloquea** la nota que los lleve. Lo que sobrevive de todo eso es un hecho: **`Read` rasteriza el
PDF, así que el modelo *ve* la fórmula** — es cuestión de **modalidad, no de modelo**.

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

Sin `role`, *"contrastar dos papers" no está definido*: fundacional↔fundacional se comparan
supuestos y derivaciones; aplicación↔aplicación se pregunta si replica y **en qué régimen**;
**fundacional↔aplicación NO es contraste, es instanciación** —la aplicación no contradice la
ecuación, la pone a prueba— y tratarlo como desacuerdo **fabrica disputas falsas**; el `arbitro`
pesa distinto (resuelve, no promedia). El vocabulario es **cerrado** y el lint lo valida como
bloqueante: un typo deja el campo mudo para la única operación que existe para consumirlo. Es
especialmente agudo en temas de **método**, donde fundamentos y aplicaciones astro conviven en el
mismo concepto por diseño.

#### Escotillas y metadata de estado

- `no_sintetizado: <motivo>` (#75): declara que este paper **ya extraído** legítimamente no se
  inlinea en ninguna ficha ni concepto —típicamente por la **regla de poda**, o porque aporta sólo
  vía roll-up—. Motivo **obligatorio** (mismo criterio que el `--reason` del triage: no curar en
  silencio); sin ella, el lint lo reporta como *extraído pero no sintetizado*.
- `retracted: true` + `retraction{type,notice_doi,date,source}`: lo estampa
  `scripts/check_retractions.py` (Crossref) y el lint lo surface como **bloqueante** (fuente no
  válida).
- `corrections: [{type,notice_doi,date,source}]` (#52): la corrección **no retractante** (`erratum`
  / `corrigendum` / `expression-of-concern`). **No** invalida el paper —sigue siendo citable, por eso
  es **backlog**— pero es la señal que más directamente **envejece un número ya extraído**: un
  corrigendum corrige justo el valor que la ficha destiló. Al verla, revisar las afirmaciones que
  citan ese `[[bibcode]]`, no la existencia del paper.

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

⚠ El `## Abstract` **verbatim** lo escribe el cosechador **sólo si la nota no lo tiene**: el del
catálogo es copia de máquina y no se pisa con una transcripción del modelo. Existe porque una nota
off-ADS creada antes de #124 no tiene la sección en absoluto y `write_web_paper_note` sólo la
escribe al **crear**, así que el hueco se cierra en la próxima extracción sin re-ingestar nada.

⚠ **Documento largo (`unidad_cita: pagina`): sin conclusiones.** Un libro no tiene esa sección y
transcribir algo que no existe fabrica contenido. Es una exclusión **estructural**, no un umbral de
largo.

⚠ **Cómo se leen las conclusiones, y por qué es un método:** el extractor empieza por ahí, saca los
**ejes** que el trabajo dice aportar, y los **chequea contra el cuerpo** — porque es justo donde
vive el *afirmar de más*. Si el cuerpo dice menos, eso es un hallazgo sobre la **fuente** y va a
`salvedades`.

⛔ Las cuatro secciones están en `SECCIONES_ESTAMPADAS`, así que `verify-citations` **no las mira**:
una traducción no es una afirmación de la bóveda. La red está aguas abajo —lo que de acá llegue a
una **ficha** sí se verifica contra el PDF—, y de ahí la regla de uso: **son ayuda de lectura, nunca
fuente de la que citar.**

#### Notas off-ADS y fuentes largas

En notas **off-ADS** el schema suma `source_url` (URL de la fuente web; `null` si es PDF local),
`accessed` (fecha del snapshot — es la cita "Retrieved <fecha>") y, si la fuente no se pudo
conseguir, `pending_source: paywall|scan|unextractable|adquisicion` (el lint la lista como
precondición).

⛔ **`pending` es vocabulario CERRADO y lleva `pending_motivo` obligatorio (#80).** Los tres valores
históricos describen **por qué falló** la adquisición o la extracción; **`adquisicion`** describe
otra cosa: un libro que el usuario va a conseguir **no falló**, tiene otra latencia — entraba
forzado como `paywall` y se perdía el motivo real. El motivo es libre y obligatorio por el mismo
argumento que el `--reason` del triage: en seis meses lo que sirve es el motivo, no la categoría. El
valor se escribía **verbatim** en la nota, así que un typo entraba mudo: hoy la cadena aborta y el
lint lo nombra.

⛔ **Una fuente LARGA declara cómo se la cita y qué parte entró (#80):** `unidad_cita:
linea|pagina|seccion` (default `linea`, no se estampa) y **`alcance`** (qué capítulos o secciones
entraron), obligatorio cuando la unidad no es la línea. Un libro rompe dos supuestos del contrato de
`verify-citations`: el fan-out asume un `.txt` que un subagente lee **entero** —700 páginas lo
revientan— y «línea 18443» no es una referencia utilizable. Y casi nunca entra el libro entero, lo
que choca con el chequeo de **completitud**, que sin `alcance` no puede distinguir un recorte
deliberado de una omisión. Es un eje **distinto** del `txt:`/`pdf:` de #117: aquél dice qué
**archivo** se leyó, éste **cómo se apunta adentro**.

⛔ **Y los dos campos LLEGAN AL EXTRACTOR (#241).** `extraction_prompt` **ramifica por
`unidad_cita`**: para una fuente larga manda empezar por el **índice**, pega el **`alcance`
declarado textual** —con la instrucción de no ampliarlo solo: si lo que el sujeto necesita está
afuera, se extrae lo que hay dentro y **se declara en `salvedades`**, porque ampliarlo en silencio
deja el `alcance` de la nota afirmando algo falso—, recuerda que `conclusiones` va **vacío** y que se
cita **por página**. Sin `alcance` el prompt lo **dice** (*«NO DECLARADO»*) en vez de callar.

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
(slug, query, faceta, registro y corpus propios) cuya nota apunta de vuelta al hub. Ejemplo en
`ica`: *noisy ICA* es radio porque su vocabulario (*gaussian moments, quasi-whitening, HeteroPCA*)
no lo trae una query de «independent component»; *PCA* queda **dentro** del hub —es el baseline
contra el que se mide ICA— y *PCA heterocedástico* **corresponde al radio**, o sea que «PCA» se
parte **por régimen**, que es el mismo eje que separa radio de hub. ⚠ Es el criterio **aplicado**,
no una descripción de ninguna nota: en la instancia que motivó el ejemplo la partición está
**decidida y no aplicada** (#235).

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
según destino:** en archivos de `vault/wiki/` SIEMPRE `$...$` (Obsidian lo renderiza); en
**respuestas de consola o chat** usar **texto plano** (`P_rot`, `m·sini`, `K=2.5 m/s`), porque la
terminal no renderiza LaTeX.

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

⛔ **Y el PREVIEW de un tema se corre con esa lente, no con la global (#208):**
`python scripts/query_ads.py <slug> --theme --probe` (la query sale de `query:` del tema). Hasta
1.76.3 `--probe` clasificaba siempre con `relevance.facets`, o sea con la lente que esta misma
sección declara inservible acá — y sobre la población que el tema existe para capturar el resultado
no es «menos preciso», es el **veredicto opuesto**: medido en `ica`, los tres papers de separación
de componentes más citados caían en el no-core y el core se llenaba de binarias eclipsantes que
matchean `rv`. Importa porque el preview es el **único** lugar donde ese corte se decide **antes**
de pagar descargas y extracción. En ese modo cada fila lleva **por qué puerta entró** (abajo), el
desglose por política reemplaza al contraste de combinación —que habla de la lente global— y la
línea de cierre manda a `themes.yaml`, no a `objective.yaml`. Sin `--theme`, comportamiento
histórico; con `--theme` y un slug que no existe o que no declara `facet:`, **rehúsa** en vez de
degradar a la global.
⛔ **Y para una ESTRELLA la query también se DERIVA (#248): `python scripts/query_ads.py <slug>
--probe`.** Había que tipearla a mano, y la tipeada **no es la que corre el ingest**: la real
expande las variantes de espaciado (`HD 40307` ↔ `HD40307`) y suma los alias de `stars.yaml`, que es
justo la parte que un humano no escribe. O sea que se previsualizaba un universo y se ingestaba
otro — el mismo falso limpio que #208 cerró del lado de los temas, sobreviviendo en el carril de
estrellas, y **peor**: acá el veredicto sale plausible, porque la diferencia son los papers con la
grafía sin espacio y ésos no aparecen por ningún lado del reporte.

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
                         `fuente: abstract`. Sus EJES salen de `relevance.facets` de ESTA
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
al PDF si un detector lo decía— se eliminó: los detectores no discriminaban, y el A/B medido
(`docs/mediciones.md`, 2026-08-28) dio al PDF ganando en tokens, tiempo y tools **también en el
paper de capa "limpia"**, cuyo `.txt` había perdido `√`, primas y superíndices con los tres chequeos
en verde. **Qué le queda al `.txt`, y por qué se sigue generando:** el `grep` sobre el corpus
(`query-corpus`, `test-hypothesis`, el retro-tag por alias, el conteo del alcance de hipótesis
D-34) busca **prosa**, que es lo que `pdftotext` extrae bien; y en un **documento largo** (#80) es
imprescindible: 700 páginas no se rasterizan — se grepea, se saca la página y se abren **esas**
páginas del PDF. ⛔ **El `.txt` NO se genera con el modelo**: tiene que ser determinista, o las
citas por línea serían inventadas y verificar sería contrastar un modelo contra otro.
⚠ **Consecuencia:** un `pending_source` deja de ser salvedad y es **bloqueo real** — sin PDF no hay
de dónde extraer; la cadena lo deriva al usuario sin frenar.

⚠ **Excepción nombrada: la fuente WEB.** Un snapshot de `fetch_web` (`source_url` poblado,
`pdf: null`) no tiene PDF **por diseño**: ahí el `.txt` no es copia degradada, **es la captura**
(determinista: defuddle, URL + fecha, citada con `accessed`). Se lee, se cita por **línea** y su
fila de verificación lleva `txt:<sha10>`.

De los tres chequeos de calidad quedan **dos**, con otro trabajo: `is_legible` dispara el OCR (un
escaneo sin capa de texto da un `.txt` vacío y el paper se vuelve invisible al corpus) e
`is_garbled` sigue porque la prosa garbleada degrada el índice. `symbols_lost` y `fulltext_layout`
se retiraron (#193/#194); `measure_layout` **no** (`CANALETA_MIN` es el contrato para grepear un
`.txt` entrelazado).

⛔ **Los tres miden el TEXTO, así que ninguno ve el dato que vive en una IMAGEN (#195)** — y es casi
la mitad del corpus (medido: 29/65 vistas; `docs/mediciones.md`). El prompt
(`extraction_prompt._media_note`) trata los tres casos:

- **tabla extraída como texto** → se cita por línea, declarando **cómo se verificó la fila** (el
  entrelazado la parte; en una tabla multi-objeto la fila equivocada es el modo de falla);
- **tabla-imagen** → el `.txt` no la tiene y el grep vacío **no prueba ausencia**: si el dato
  sostiene algo, se abre el PDF y se cita **página** (misma regla que una ecuación);
- **figura** → el número existe sólo como curva: **se permite leerla** (decisión del usuario,
  2026-08-27) y el valor viaja con la **figura y su página** (`Fig. 3, p. 7`), el **`≈`** y la
  palabra **lectura de gráfico** en el régimen — doctrina de `inferencia`: declarar de dónde salió.
  Es un **permiso, no una obligación**: si la curva no se deja leer con confianza, queda como
  **hueco declarado** (forzar un número de una curva ilegible es peor que el hueco);
- **figura que es un CAMPO** (contornos, mapa de color, densidad) → el valor **no existe sin el
  nivel**: se cita `Fig. N, p. M, contorno del X %`, y todos los niveles si el dato los necesita.
  Dos lecturas que no reconcilian son figura **subespecificada** antes que dato ilegible (#281) — un
  hueco declarado de más dice *«el corpus no puede responder esto»* y el consumidor deja de buscar.

Por eso la columna de la vista se llama **`Localizador`** y no `Línea`: lleva `L1234`, `p. 271` o
`Fig. 3, p. 7` según de dónde salga el dato (la clave del JSON sigue siendo `linea`: vive en
`build/`, scratch).

⛔ **La prosa que va a una CELDA se escapa: `\|` fuera de la matemática, `\vert` adentro (#240).**
Un `|` crudo parte la fila y una afirmación citada y verificada queda **invisible para el lector**
mientras el lint cuenta su fila. ⚠ Dentro de `$…$` el escape es `\vert` y no `\|` (en LaTeX es ‖):
escapar a ciegas cambia filas invisibles por fórmulas equivocadas, que es peor. Lo hace
`lib_config.escape_cell` en el cosechador, el único punto de escritura.

**Los DOS hashes del paso 6** responden preguntas distintas: el **ancla** hashea el bloque de la
**ficha** (se dispara si editás la nota) y el **hash de fuente** hashea el archivo **leído** —desde
#205, el PDF—. Las filas viejas con `txt:` siguen siendo válidas y se re-verifican cuando vencen, no
se migran en masa. ⚠ El PDF es inmutable: esa alarma es rarísima (alguien reemplazó el archivo), y
una fila anclada al PDF no se vence cuando el `.txt` se re-extrae.

**La cascada, paso a paso:**

1. Los **orquestadores** corren la cadena mecánica completa (idempotente, no pisa — única excepción
   add-only: el retro-linkeo de abajo): `python scripts/ingest_star.py <slug>` para estrellas,
   `python scripts/ingest_theme.py <slug>` para temas. **El orden canónico vive en el header de su
   orquestador** (fuente de verdad única — puntero, no copia).

1b. **Compuerta de triage (estrellas).** El citation chaining amplía el pool con papers del grafo
   que mencionan al sujeto sin hablar de él (medido: 18 % de precisión). Sólo entra solo el que
   lleva el **sujeto en el título**; el resto queda como **candidato** en `build/<slug>/ads.json`
   —sin bajarse— y lo juzgás vos por título+abstract (`python scripts/triage.py <slug>`): aceptado →
   `extra_core` en `stars.yaml` (lista de mapas `{bibcode, via, fecha, motivo}`, forma dura D-58:
   el escalar y la lista de strings bloquean; `triage.py` imprime el snippet listo) + re-correr la
   cadena; descartado → `triage.py --drop … --reason` (persiste: no se re-propone); **dudoso → al
   usuario**. Detalle en el skill `ingest-star`.

2. **Vos (LLM)** leés el **PDF** y hacés la cascada: poblás la extracción **de las notas de paper**
   (`methods`, `thesis_links`, `role`, P/K/indicadores). La ficha se escribe **después** del
   contraste (2b) — no saltar de leer a la prosa. ⚠ **Mirá `pdf_source` antes de copiar un número:**
   con `eprint` el documento es el preprint — un valor que contradice al ground-truth o al abstract
   de ADS es candidato a **diferencia de versión** (abrí el PDF publicado o anotá la salvedad).
   **Cómo anotar cada valor (#103):** con **la página del PDF**, **el régimen** en que la fuente lo
   afirma (muestra, época, corte de datos, modelo) y —si la fuente lo atribuye a otro trabajo— la
   marca **segunda mano** con la cita a X, porque el número **no es de esta fuente** (es el
   mecanismo de error nº 1 medido en #103). ⛔ **Nada de prosa comparativa en la nota de paper**:
   comparar dos papers es `inferencia` y va al `## Inventario por eje` (2b).

2b. **Contraste cross-paper (#72)** ⚠ *(el skill `ingest-star` lo numera **3b**; su `2b` es el
   barrido full-text)* — **entre leer los papers y escribir la síntesis.** Es el paso con más
   apalancamiento y el que más fácil se saltea, porque su producto no se nota si falta. Produce el
   **`## Inventario por eje`**: una fila por paper para cada **eje** donde los papers **no
   coinciden** (`Eje | Paper | Dice | Método / baseline`); los ejes con acuerdo unánime no entran.
   ⛔ **Sin columna "valor adoptado" ni "por qué"**: sería decidir por el consumidor (regla #0) — la
   bóveda reporta el **estado de la literatura**; la lectura propia va aparte, marcada `inferencia`.
   Sin este paso, tres `P_rot` terminan en una frase con un solo `[[bibcode]]` y se evapora que los
   otros dos valores existen. El `role` (#73) dice qué operación corresponde entre dos filas.
   **La red de que ocurrió (#101):** el lint reporta la ficha con la **fila vacía de la plantilla**
   y ≥2 papers extraídos citados — ausencia = declarado (la plantilla dice borrar la sección y
   decirlo en el log), presente-y-vacío = saltado.

2c. **Síntesis a la nota viva**, apoyada en el inventario: la ficha (frontmatter propio, prosa,
   huecos), los conceptos e hipótesis relacionados y la matriz método×estrella. ⛔ Los campos de
   ground-truth **no se tocan** (espejo de NEA, #70).

3. Actualizás `index.md` y appendeás a `log.md`.

> **Retro-linkeo (papers pre-existentes ↔ entidad nueva) — tres capas:** (a) una ficha-método junta
> en su roll-up estampado también por `methods` — pero la tabla **no acumula sola**: re-correr
> `python scripts/make_notes.py <slug> --theme` (el lint reporta la tabla desactualizada);
> (b) `make_notes` mergea **add-only** los seeds del ingest (`stars`/`thesis_links`) en notas que ya
> existían (nunca pisa la extracción LLM); (c) `ingest-theme` incluye el **retro-tag por grep**:
> buscar los `aliases` del tema en el fulltext de **todo** el corpus y taguear (add-only, con juicio
> de LLM: uso real, no mención al pasar) lo que la query ADS no devolvió.

> **Tema fuera de ADS (opt-in — sólo a pedido explícito).** Por default un tema se baja por **ADS**;
> el modo off-ADS existe para los **métodos de otras disciplinas** cuya bibliografía canónica vive
> fuera de ADS: las fuentes se **declaran**, no se descubren por query. La entrada del tema en
> `themes.yaml` lleva `source: ads | web | local-pdfs [+web]` — ⚠ **el nombre engaña (#209):
> `source:` no dice «dónde se busca», dice QUÉ CADENA CORRE el orquestador**; el descubrimiento
> multi-backend es `discover.py --theme <slug>`, un paso aparte que el skill prescribe a mano (0b) y
> que `ingest_theme.py` no llama — y (si es off-ADS) la lista `sources:`. Un tema off-ADS puede ser
> **mixto**, y su mitad astro entra por una de dos vías (la primera con prioridad): **`query:`
> poblada** → descubrimiento ADS completo (misma lente, mismas puertas D-26, misma compuerta de
> triage), o **sólo `extra_core:`** → sub-cadena acotada a esos bibcodes. Los papers con bibcode ADS
> van siempre en `extra_core:`, nunca en `sources:`. Una fuente que no se consigue se marca
> `pending: paywall|scan|unextractable` en su item de `sources:` → stub con `pending_source`,
> derivada al usuario sin frenar la cadena. **`ingest-star` no cambia: es astro-only.** Papers sin
> bibcode ADS → clave sintética `AAAA+Autor` (debe empezar con `AAAA`+letra); páginas web →
> **snapshot `.txt` determinista** (`scripts/fetch_web.py` vía defuddle, que crea además el stub).
> ⛔ **Una `url:` que sirve un PDF NO se snapshotea: se BAJA como PDF (#242)** — `fetch_web` mira el
> `Content-Type`, porque `resolve_pdf` devuelve `pdf_url` por construcción y el framework proponía
> una entrada que su propia cadena rechazaba. La **frontera dura sigue rigiendo**: sólo bibliografía
> citable.

### Registro de ingesta (`vault/config/registro/<slug>.yaml` — versionado, #51/#64)
Cada sujeto ingestado deja un registro que **se commitea y viaja**, con tres secciones de dueños
distintos: **`descubrimientos`** (lo que la cascada de `discover` trajo, **con sus identificadores**
—#231: sin ellos el registro contaba 391 registros y no podía **nombrar ninguno**, mientras el
`STATUS.md` de la bóveda afirmaba que la cascada había encontrado los ocho trabajos del canon;
encontrados, y en ningún carril versionado, así que declararlos en `sources:` obligaba a re-correr
la cascada o a tipear las referencias a mano. Es el simétrico de `busquedas[].bibcodes`, y es lo que
vuelve **accionable** un descubrimiento en vez de sólo contable—), **`busquedas`** (lista, una entrada por corrida — **acumulativo**, D-28: antes pisaba, y
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
—en una estrella la arma `build_query` y antes se tiraba—, **`fq`** (#238: la mitad **más
restrictiva** del filtro, que acota server-side **antes** que la lente — sin él un «0 encontrados»
**no es una medición reproducible**, y esa clase de medición negativa se usa como premisa de
decisiones de curación: medido, una bóveda afirma *«ningún paper del canon está en ADS: 0/8»* sobre
un canon de procesamiento de señales, con `database:astronomy` aplicado y sin registrarlo), `rows`, `n_found`, `n_total`, `n_core`,
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
  extracción pagada sin nota **para siempre**. La decisión queda versionada, así que borrar el
  artefacto no borra el juicio. ⛔ **Y en la nota que SE CONSERVA, `drop_core` re-apunta
  `pdf:`/`fulltext:` por verdad de disco (#217):** a la copia que sobreviva bajo otro slug, o a
  `null`, con el link `[📄 PDF]` de la cabecera cayéndose detrás — dejarlos apuntando a un archivo
  que este mismo comando borró es afirmar algo falso sobre el disco. **La vista y la extracción no
  se tocan**: la lectura ocurrió y sus localizadores siguen siendo válidos; lo que cambió es que ya
  no hay contra qué re-verificarla, y **eso el lint lo dice** (*«vista fechada sin fuente en disco:
  ya no es re-verificable»*, backlog — ninguna otra red lo ve: el ancla de fuente no se entera de un
  archivo que **desapareció**). La **nota** se borra **sólo si el paper no pertenece a otro sujeto Y
  no tiene extracción**; en cualquier otro caso NO se borra y se avisa por qué. Cuando sí se borra,
  los `[[wikilink]]` que la citaban quedan **rotos y visibles**: no se reparan solos, porque sería
  decidir por el usuario qué decía esa frase (#132, mismo criterio que `entity.py delete`).
- **El diff de re-clasificación lo respeta** (`lens_diff_offline`, `reclass_diff`): sin eso, cada
  cambio de lente vuelve a proponer lo que el usuario ya sacó, y la categoría se vuelve ruido que se
  deja de mirar.

INV-24 sigue en pie por la misma razón que con `extra_core`: core es `f(paper, lente)` **módulo
curación declarada**, y la curación es auditable —motivo obligatorio, fechada, versionada, viaja—.
Lo que no sería auditable es que el veredicto cambiara sin que nadie firme.

El cuadrante que faltaba —la fuente off-ADS **aceptada**— es el que más lo necesita: ahí **todo**
entra por decisión de alguien, y sin el campo *«¿qué pidió el usuario y qué propuso el
descubrimiento?»* no tiene respuesta.

⛔ **`via` son DOS vocabularios, uno por carril (#266).** El párrafo que sigue describe el de
**`sources:`** (off-ADS); el de **`extra_core`** (ADS) es otro y vive en
`lib_config.EXTRA_CORE_VIA`: `usuario` · `triage` · `citado-por-corpus`. Miden ejes distintos — en
off-ADS no hay query que descubra, así que el eje es *quién decidió*; en el carril ADS lo que
distingue es **por qué mecanismo** entró un paper que la lente no marcó core. Escribir el valor del
otro carril hace que el loader **rechace duro**. Lo vigila un test de paridad doc↔código.

En `sources:`, `via` es **vocabulario cerrado y BINARIO** (#206): `usuario` (lo trajo una persona) ·
`descubrimiento` (lo propuso la cascada de `discover`). El eje que mide es **quién decidió**, y eso
no tiene tercer valor: que el usuario traiga una lista de papers o los PDFs no cambia quién decidió.
De qué documento salió lo lleva **`motivo`**, obligatorio. El lint **bloquea** la entrada sin `via`
o sin `motivo`, el `via` fuera del vocabulario (typo) y el valor **retirado** (con mensaje propio:
un typo se corrige, un retiro se traduce). ⚠ El PDF que el usuario aporta para cerrar un
`pending_source` **no** necesita valor propio: ese paper ya entró con su `via` y su `motivo`.

⛔ **El carril off-ADS tiene salida hacia la ingesta** (#111): `python scripts/triage.py <slug>
--accept-source <doi> --via <via> --reason "<motivo>"` arma la entrada completa —metadata real de
OpenAlex, archivo resuelto por `resolve_pdf` o `pending: paywall`, y la procedencia— **lista para
pegar**. No escribe `themes.yaml`: la config es curada y versionada, y un script que la edita solo
convierte una decisión en un efecto colateral.

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

**Extensión propia de esta wiki** (el lint canónico de Karpathy no valida que la fuente respalde la
afirmación — sólo salud estructural). **Cuándo:** paso de cierre de **toda operación que escriba
prosa con `[[bibcode]]`** — antes de lint/commit. **La nota nace 100% verificada (D-5):** el estado
*"sin verificar"* sólo puede aparecer después, por una edición; por eso el caso normal es que el
lint calle, y cuando habla hay algo real. El procedimiento completo (fan-out, prompts, barrera,
resolución) vive en el skill; acá va el contrato del artefacto.

**Qué hace:** descompone la nota en pares (afirmación, `[[bibcode]]`) —las filas de tabla y los
ítems de lista **heredan la cita del ámbito que los introduce**; las `SECCIONES_ESTAMPADAS` quedan
afuera (metadata derivada, no hay qué contrastar)— y lanza **un subagente independiente por par**
que lee SÓLO esa fuente (grounding-first, prohibido de memoria) y devuelve **dos ejes separados**
(D-59): un `veredicto` de RESPALDO —vocabulario cerrado `soportada|no-soportada|contradice`— y,
aparte, la `condición` bajo la que la fuente lo afirma. Más **cita textual + nº de PÁGINA del PDF**
(obligatoria; sin cita ⇒ no-soportada: la cita debe tocar el **contenido distintivo**, la cercanía
temática no alcanza). `no-soportada` = la fuente **calla**; `contradice` = **afirma lo contrario** →
corrección de la nota o **disputa** (#71). Cada falla se **resuelve** (bajar la afirmación a lo que
dice la fuente, reasignar la cita, marcar `inferencia`, o taguear la disputa).

⚠ Dos ejes de **grado** se eliminaron y no vuelven: **`parcial`** (1.39.0 — fusionaba lo decidible
con lo de grado; se descompone sin pérdida en `soportada`+`condición` o `no-soportada`) y la
**columna `Score` 0–10** (1.42.0 — el campo no gradúa: el vocabulario ternario ya es el estándar).

⛔ **La condición se CLASIFICA, con vocabulario cerrado: `acota` | `contextualiza` (#221).** El
fan-out la puebla en la gran mayoría de los pares, así que *«resolvé cada condición»* sería la nota
entera. Test operativo: ***¿la afirmación queda falsa si se saca la condición?*** → **`acota`** (se
resuelve sí o sí: en un concepto, fila de `## Régimen de validez`) / **`contextualiza`** (va al
reporte, no obliga a editar). Y la condición es **columna, no prosa**: el juez es estable en el eje
textual y no exhaustivo en el de régimen, así que absorberla sin rastro borra lo que hay que poder
re-auditar.

El subagente contesta además, en todos los casos, la **sobre-generalización** (#74: la fuente
afirma bajo condiciones que la nota no dice — la nota no afirma falso, afirma **de más**) y, en
transcripciones de tablas/listas, la **completitud** (una tabla truncada sin un solo error vuelve
100% soportada — afirma **de menos**; se completa o se declara el recorte).

**El bloque `## Verificación de citas`** — una fila por par:
`| # | Afirmación (extracto) | Fuente | Veredicto | Evidencia | Ancla | Hash fuente | Condición |`

- ⛔ **Sin fila no hay dónde colgar el ancla**: colapsar las soportadas en prosa deja al lint sin
  distinguir "verificada" de "nunca se miró".
- ⛔ **Sólo `Afirmación (extracto)` se trunca (#226)**; `Evidencia` y `Condición` no, y `Evidencia`
  lleva su localizador (`p. N`, `L…`, `Fig. 3, p. 7`) **al final y completo** — el corte se lleva el
  localizador y apaga el cruce de #122, que sin él devuelve un 0 que se lee verde. ⛔ **Y el corte
  no cae dentro de `$…$`, `` ` `` ni `[[ ]]` (#274b/#257c):** retrocede al límite del bloque —
  `lib_blocks.truncate_claim`—, porque un `$` huérfano se traga texto en Obsidian y un `[[` partido
  es bloqueante. ⛔ **La celda lleva PROSA, nunca un `repr()`** de la salida del fan-out (#274a).
- ⛔ **`Hash fuente` declara CONTRA QUÉ ARCHIVO se verificó: `txt:<sha10>` o `pdf:<sha10>` (#117).**
  La decisión la toma el verificador par por par, así que la declara la **fila** (ningún campo del
  frontmatter puede saberlo). En filas nuevas: `pdf:`. Sin prefijo = *no consta* y el lint
  **bloquea** (migrar con `python scripts/make_notes.py --migrate-verif-archivo`, que deduce del
  hash). Excepción nombrada (#223): la fila `no verificable por extracción` **no declara archivo**,
  porque no hay ninguno (fuente sin PDF ni `.txt` en disco).
- ⛔ **Documento largo leído del `.txt`: los DOS localizadores (#200)** — `(p. 271 / `.txt` L13931)`:
  `pdf:` mentiría sobre qué se abrió y la línea sola rompe #80. ⚠ Desde #205 el caso no se produce
  en filas nuevas; las viejas son correctas y no se tocan.
- ⛔ **Un veredicto que exige acción NO queda registrado y sin resolver (#91):** `no-soportada` /
  `contradice` **pelados bloquean** (mismo trato que citar una retractada). No cuentan
  `no verificable por extracción` ni la resolución anotada en la celda.
- ⛔ **Con DOS RONDAS, la segunda ANOTA, no pisa (#232):** `contradice→corregida` — es lo que lee
  `lib_blocks.resueltos()`. Si pisara, el bloque final publicaría 0 donde hubo 3 `contradice` y
  nadie podría saberlo desde la nota. Con **más** rondas la celda encadena
  (`no-soportada→contradice→corregida`, #274c): la partición de la cabecera sigue siendo por el
  **primer** veredicto y la cadena se publica aparte.
- ⛔ **La cabecera la genera el mismo código que lee la tabla** (`lib_blocks.verif_summary`,
  INV-81): los **cuatro** veredictos —que particionan: `soportada`, `no-soportada`, `contradice`,
  `no verificable por extracción`— y, tras un **`—`**, `con_condicion` (eje ortogonal). Las **tres
  sub-secciones** (*Inferencias declaradas*, *Omisiones en transcripciones*, *Condiciones perdidas*)
  van **aunque digan «ninguna»**: son el único rastro del triage de la corrida.

**Los dos hashes (el ancla, D-4/D-20)** responden preguntas distintas: el **ancla** hashea el
**bloque markdown normalizado** que contiene la cita —reflowear no la mueve, cambiar un número sí; un
blockquote hard-wrapped es UN bloque (#224: por línea se podía reescribir el medio de una cita sin
vencer el par, y el sub-disparo es la única dirección prohibida); una fila sin `[[bibcode]]` propio
hereda el del caption hasheando los dos bloques— y el **hash de fuente** hashea el archivo que se
**leyó** (desde #205, el PDF: `bytes_hash`, no `source_hash`) — lo único que detecta que la fuente
cambió sin que nadie tocara la nota. El PDF es inmutable, así que esa alarma es rarísima: cuando
suena, alguien reemplazó el archivo; y una fila anclada al PDF **no** se vence cuando el `.txt` se
re-extrae. Los calcula `scripts/lib_blocks.py` (`pairs_of`, `source_hash`, `bytes_hash`), el mismo
código que después los chequea: **no se escriben a ojo**. ⛔ **Y el bloque escrito se re-parsea antes de publicarse (#284):** `lib_blocks.render_verif_table` escapa cada celda y **rehúsa** devolver un bloque cuya lectura no reproduce lo que se le escribió — sin esa puerta, reescribir una fila leída parte la fila y el ancla se lee de la columna equivocada.

**Salvedades de fuente:** `.txt` con header `source: ocr` → citable con salvedad (la verificación
vale para prosa; ante discrepancia de símbolos, abrir el PDF). `pdf_source: eprint` → una
discrepancia numérica contra un valor publicado es candidata a **diferencia de versión**, no se
"corrige" la nota hacia el preprint. Si una afirmación no aparece en el `.txt` (ecuación, tabla,
escaneo): abrir el PDF o marcar `no verificable por extracción`.

Es **juicio de LLM**, robusto pero no prueba: su tasa de error se mide con el **auto-benchmark**
(a pedido): `python scripts/bench_verify.py seed` siembra citas falsas deterministas, el verificador
las juzga a ciegas y `score` reporta el recall; nada del benchmark entra al vault.

**Qué es una `inferencia` y cómo se escribe (D-42).** Una afirmación que la bóveda sostiene y que
**ninguna fuente dice**: sale de combinar dos o más que sí lo dicen. No es excusa para lo no
verificado: es la declaración explícita de que el respaldo es un razonamiento, para que el
consumidor la pese distinto. Se escribe **nombrando sus premisas**: `(inferencia de [[b1]], [[b2]])`
— sin al menos un `[[bibcode]]` **el lint la bloquea** (no hay nada que auditar). La palabra en
prosa normal no es una marca. ⚠ El énfasis markdown alrededor no cambia nada (#276):
`` (`inferencia` de …) ``, `(**inferencia** de …)` y `(_inferencia_ de …)` son la misma marca; lo que
no cuenta es otra palabra que empiece igual (`inferencial`).

**Regla dura — todo lo apuntable es chequeable:** toda afirmación fáctica va **citada `[[bibcode]]`
o marcada `inferencia`** — nada sin respaldo. Excepción: los valores de ground-truth (NEA) en
`stars/` no se verifican contra papers (su consistencia la chequea el lint); sólo se verifican
disputas y afirmaciones atribuidas a un paper. El lint reporta como backlog los conceptos e
hipótesis sin ninguna cita.

### Auditoría de una FICHA (skill `audit-note`)
**El eje que ninguna otra capa mira: ¿esta ficha dice la verdad y se sostiene sola?** El lint chequea
salud estructural, `verify-citations` claim ↔ **su propia** fuente par por par, `find-contradictions`
claim ↔ claim **entre** fuentes, y `auditar` el **framework**. Falta el artefacto **completo**, y no
es teórico: una pasada ad-hoc sobre un concepto cerrado —`lint --cierre` en 0, 99 pares en
`soportada`— encontró **más de 40 defectos**, entre ellos que la nota **no era implementation-ready**
(faltaba el puente `g = G'`, el criterio de convergencia y la deflación, y **cuatro de los cinco
huecos estaban en un `.txt` que la bóveda ya tenía bajado**), dos filas de tabla **fusionadas** que
hacían invisible una afirmación **verificada**, una sección que **se contradecía** con otra 100
líneas después, y una afirmación **falsa sobre el propio repo**.
**Cuándo:** a pedido explícito, **nunca** como paso de cierre — es caro por diseño (abre PDFs,
recuenta, re-renderiza, lanza un subagente por frente) y su valor está en **garantizar** una ficha
antes de apoyarse en ella. **Qué hace:** siete frentes en paralelo —estándar de la nota (con la
prueba operativa de *escribir el pseudocódigo desde la nota y anotar dónde se traba*), la nota contra
sí misma, integridad del artefacto, aritmética, cadena de verdad, coherencia con el mundo declarado,
y la nota contra su cadena—, cada uno declarando **su población**; barrera; corrección **serial**
volviendo a la fuente; y **re-verificación de lo tocado** (#203). ⛔ **Lo que no se pudo cerrar sale
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
⛔ **Reporta, no aplica solo — con UNA excepción nombrada** (AUD-206): el diff se muestra y se
pregunta antes de tocar nada, porque un snapshot que se actualiza solo cambia valores **bajo los
pies de la prosa que ya los citó**. La excepción es **`retracciones`**: `check_retractions` estampa
`retracted:` / `corrections:` en las notas **sin preguntar**, a propósito — una fuente retractada
citada rompe la frontera dura, así que enterarse tarde es peor que el ruido de diff, y lo que
escribe es una **marca de metadata**, no un valor que la prosa haya citado. Los otros cinco no
escriben: versiones y web proponen el comando, ground-truth pregunta, y citas-puerta2 sólo reporta
el cruce. Lo que sí es
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

**Lo que no se pudo verificar queda MARCADO en la ficha (#225): `<afirmación> ⚠verificar en el PDF
(<qué se dudó>, <fecha>)`.** Es la marca que produce el skill `audit-note` y tiene las propiedades de
las otras: **no destruye** la afirmación (puede ser cierta), es **visible para el consumidor** —que
es quien tiene que saber que ahí hay una duda—, **la levanta el lint** como backlog para que la
deuda no se olvide, y **se saca cuando alguien la verifica**, con la evidencia. El criterio para
ponerla es amplio a propósito: un valor cuya página no se pudo confirmar, una cita cuya fuente no
está en disco, un número que no reconcilia. **Ante la menor duda se marca** — el costo de una marca
de más es que alguien abra un PDF; el de una de menos es que la bóveda afirme algo falso con cara de
verificado. ⚠ Lo que **no** es: una excusa para no verificar. Si la fuente está en disco, se abre.

**Una entrada de `log.md` que quedó REFUTADA se MARCA, no se edita (#238): `⚠ corregido <fecha> →
<entrada nueva>`.** La bitácora es append-only por contrato —y está bien—, pero eso la dejaba sin
forma de corregirse: medido, una entrada publica como cita textual **con página** una frase que
**invierte el sentido** de lo que dice el paper (*«do not become orthogonal»* por *«that are not
orthogonal»*), y **el propio log lo reconoce 268 líneas después**, en la entrada de la verificación.
La corrección se aplicó al concepto y a la nota del paper; la bitácora conserva la cita fabricada
**permanentemente**, sin marca y sin puntero. Es la misma doctrina que las otras marcas —hacer
visible, no borrar— y el lint la levanta: chequea las citas textuales del `log.md` contra el `.txt`
de su bibcode y reporta la que su fuente no dice, salvo que ya lleve la marca.

Éstas son las **cinco únicas marcas en línea** del sistema: `(inferencia de [[bibcode]])`,
`[[bibcode]] ⛔retractada`, `<valor> ⚠desactualizado`, `<afirmación> ⚠verificar en el PDF` y
`⚠ corregido <fecha> → <entrada nueva>` (sólo en `log.md`).

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

**Cuándo:** paso de cierre de **toda operación que escriba en `vault/wiki/`** (ingest,
append-knowledge, maintain, find-contradictions, query archivada, test de hipótesis), **antes de
commitear** y **después** del verify (resolver una cita no-soportada cambia la prosa); más una
pasada completa periódica. Es barato. Correr `python scripts/lint.py`.

⛔ **El catálogo completo —cada categoría, su severidad y cómo se cierra— vive en `docs/lint.md`.**
El reporte del lint es autodescriptivo (cada categoría nombra su resolución); esta sección fija las
reglas del gate que hay que saber antes de correrlo.

**Tres severidades** — bloqueante (exit ≠ 0), WARN (se revisa a mano, no frena) y backlog (deuda
declarada; se trabaja con `maintain`). No existe "informativo" (AUD-207): lo declarado-y-resuelto
(`no_vista` con motivo, `aliases_descartados`) se reporta **aparte** (*«visible, no es deuda»*),
nunca mezclado con la deuda real. Y dos reglas del reporte mismo:

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

**La fuga de implementación** (regla #0) es **WARN**: heurística de alta señal, cada hit se revisa a
mano. No mira las `SECCIONES_ESTAMPADAS` (#214) — la exención no alcanza a `## Vista — <sujeto>`,
donde una fuga sería real.

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
5. **Cuando dos mediciones no reconcilian y no se puede re-medir, se DECLARA la discrepancia** en
   vez de elegir un número. Elegir en silencio es cómo un documento empieza a mentir.
6. **Fan-out para LEER, aplicador serial para ESCRIBIR, barrera antes de CONSUMIR — y lo escrito se
   RE-VERIFICA.** El aislamiento del fan-out no se toca; lo que no escala es la **escritura**: dos
   correctores sobre el mismo bloque lo corrompen en cadena (#197) y derivar trabajo de una etapa
   que todavía corre deja hallazgos que no mira nadie (#199). La regla no es «paralelizar menos»:
   es **un solo escritor, y una barrera antes de que algo consuma resultados**.
   - ⛔ **El aplicador comparte la definición de «bloque» con quien produce los pares (#222)** — dos
     implementaciones de la misma regla ya costaron pares desaparecidos sin señal; la red barata:
     **contar los pares antes y después y abortar si bajaron**.
   - ⛔ **La cuarta cláusula (#203): el ciclo no cierra en *corregir* sino en *corregir →
     re-verificar lo tocado*.** Un corrector que abrió la fuente escribió igual un valor falso
     nuevo; lo cazó el ancla, de rebote. Un aplicador no valida lo que aplica.
   - ⚠ **Y ese ciclo NO CONVERGE solo (#282):** el ancla es de **bloque**, así que cada ronda vence
     los pares vecinos y produce trabajo del tamaño de la anterior. La salida **no es aflojar el
     ancla** (#224: el sub-disparo es la única dirección prohibida): es distinguir la corrección que
     **cambia lo que la afirmación dice** (se re-verifica) de la **derivada de la propia
     verificación** (el texto nuevo son las palabras que el juez sacó de la fuente: se re-ancla, no
     se re-pregunta). Lo emite `python scripts/reverify_subset.py <nota>` (#257): re-anclables / a
     re-verificar / filas huérfanas, `--json` agrupado por fuente. ⛔ **Propone y no escribe**
     (doctrina `--drop-core`); empareja por **cobertura del extracto** (la celda está truncada por
     contrato, #226) y **nunca cruza `bibcode`** — llevar un veredicto de una fuente a otra sería
     fabricar la atribución que este framework más persigue.

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

## Al escribir código: las ocho redes (regla permanente)

Toda función nueva de `scripts/` pasa por esto **antes de cerrar el issue**; la 6 rige también para
los scripts de una sola operación. Detalle y ratchets en `tests/README.md`; el resumen operativo:

1. **Mutación** — romper cada función y exigir que **algún test muera**: es lo único que distingue
   "el test pasa" de "el test **podría** fallar". Trabaja sobre una copia del repo. Tres modos:
   - **Dirigida** (`python tools/mutar.py --dirigida scripts/<módulo>.py [--solo f,g]`) — **es un
     paso al escribir una función con guardas** (#204): un módulo, sólo su archivo de tests, ~0,44 s
     por mutación. Sobre-reporta sobrevivientes y nunca da falso limpio (la dirección segura); no
     toca el ratchet. **Rehúsa** si el módulo no tiene `tests/test_<módulo>.py` o nada mutable —
     cero mutaciones no es «murieron todas» (D-43).
   - **Guardas** (`python tools/mutar.py --guardas scripts/<módulo>.py [--solo f,g]`, AUD-213) —
     vaciar el cuerpo no mide las **condiciones**: muta cada `if` interno a `False` y, en un
     `and`/`or`, **cada cláusula por separado** (sólo eso revela la cláusula que ningún test
     ejercita). Mismo contrato que la dirigida; una condición constante se saltea (el hallazgo sería
     inventado). ⚠ Es el único modo que chequea la **baseline**: con el archivo de tests en rojo,
     toda guarda «muere» por el motivo equivocado (#202) → sale **no evaluado** (rc 2), no un verde.
   - **Barrido** (`--diff` / `--todo --ratchet`) — corre en **dos etapas** (#187: primero
     `tests/test_<módulo>.py`, sólo los sobrevivientes pagan la suite; el conjunto de sobrevivientes
     no cambia). Medido en v1.75.0: `--todo` = **11,3 min / 464 funciones** — con ese número la
     prohibición histórica perdió su motivo. **Cadencia: a pedido, y recomendado al cerrar una
     tanda**, con el árbol **quieto** (#199: el barrido copia el repo al arrancar; si seguís
     editando, su resultado describe un árbol que ya no existe). Un lote con roles separados
     (spec → tests → implementación, `docs/playbook-spec-tests.md`) no necesita el gate en su tanda:
     ahí el defecto se previene, no se detecta.
2. **Schema compartido** — si N módulos prometen la misma forma, se prueba **una vez parametrizada**
   (`tests/test_backends_schema.py`), no con prosa en N docstrings.
3. **Doble vs real** — un doble de test no se escribe a ojo: o deriva de la función real, o hay un
   test de paridad (regla de método 2).
4. **Nadie sin ejecutar** — `pytest tests/poblada/test_cobertura.py -m poblada` (~11 s): una función
   que la suite nunca corre no está "mal probada", está **sin mirar**.
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
8. **Atribución del mapa** — `python tools/mutar.py --trazabilidad` (AUD-212, ~20 min): vacía cada
   implementación marcada `@inv` y corre **sólo el test marcado**; si pasa, esa fila de
   `docs/trazabilidad.md` afirma una cobertura que no existe (primera corrida: 20 atribuciones
   falsas sobre 143 filas). ⚠ Sobre-reporta y nunca da falso limpio; la salida ante un
   sobreviviente por coincidencia es marcar un test que ejerza la rama verdadera, no aflojar el
   gate.

Las 2, 5 y 7 corren solas en tier 0; la 1 y la 8 son a pedido (cuestan minutos). El motivo de la
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
dirección** y las tres APIs funcionan igual, sólo que en el pool público. Hasta 1.73.0 se tomaba el
email de git —dato personal entregado para autoría, no para egress a tres terceros en cada corrida,
sin opt-in y sin forma de apagarlo—: medido en vivo el 2026-08-28, doce llamadas lo llevaron
embebido en la URL, y por lo tanto en cualquier mensaje de `raise_for_status` y en cualquier log de
proxy intermedio. Token gratis en <https://ui.adsabs.harvard.edu/user/settings/token>.
`build/` y `outputs/` gitignored. PDFs por git-lfs (`vault/raw/pdfs/**/*.pdf`). El resto de
`vault/config/` **sí se commitea**, incluido `registro/<slug>.yaml` (es el punto: el juicio de
curación y el registro de búsqueda tienen que viajar).
