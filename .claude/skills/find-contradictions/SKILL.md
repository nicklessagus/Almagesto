---
name: find-contradictions
description: Usar cuando el usuario quiere detectar desacuerdos entre papers del corpus sobre el mismo hecho ("buscá contradicciones en el corpus", "qué papers se contradicen sobre tau Ceti", "revisá disputas de P_rot", "detectá desacuerdos sobre la señal b de GJ 581", "¿hay papers que discrepen sobre X?"). Barre el corpus por eje (estrella/parámetro o concepto), confirma cada desacuerdo contra el fulltext y PROPONE entradas disputes[] / notas de disputa para que el usuario apruebe.
version: 1.7.0
---

# Find-contradictions — desacuerdos entre papers (claim↔claim)

Operación de **revisión** del patrón LLM Wiki. Complementa `verify-citations` en el eje ortogonal:
`verify-citations` chequea **claim ↔ su propia fuente** (¿el paper dice lo que la nota le atribuye?);
`find-contradictions` chequea **claim ↔ claim** entre fuentes distintas (¿dos papers discrepan sobre
el mismo hecho?). Su salida son **disputas propuestas** — no las escribe sola: el usuario aprueba.

**Por qué existe:** hoy las disputas se detectan **a mano durante el ingest** (leés un paper que
discrepa y lo tagueás). A escala se escapan (la literatura tiene ~2 claims en tensión por paper). Este
skill hace la pasada batch que las caza sistemáticamente.

**Frontera dura / ground-truth:** para estrellas, **NEA (ground-truth) es siempre el valor de verdad**
— una discrepancia paper↔NEA se taguea en `disputes` (con una posición `{source: ground_truth}`),
**no** se sobreescribe NEA. Un
desacuerdo paper↔paper sobre algo que NEA no arbitra (P_rot, mecanismo de actividad, naturaleza de una
señal) se refleja en la prosa de la ficha/concepto citando **ambas** fuentes. Sólo desacuerdos
**materiales** (mayores que el error reportado; no diferencias cosméticas dentro de la barra).

## Cuándo correrlo — TRES modos (D-39)

Hermana de `verify-citations` en el eje ortogonal, y con la misma estructura de modos. Aporta algo
que el contraste del ingest **no** cubre: ése compara el paper nuevo contra **lo que la ficha dice**;
esto compara **paper contra paper**. Dos papers pueden discrepar sobre un eje que la ficha nunca
mencionó —porque la poda lo descartó, o porque nadie lo notó—: eso sólo se ve así.

| Modo | Cuándo | Alcance |
|---|---|---|
| **cierre de operación** | entraron papers nuevos (ingest, append, refresh) | el paper nuevo contra el corpus ya extraído, **sólo en los ejes que toca** |
| **auditoría explícita** | a pedido: *"buscá contradicciones en el corpus"* | todos los pares, todos los ejes |
| **puntual** | *"contradicciones entre estos dos papers, anotalas en tal ficha"* | los papers que el usuario nombra |

Es viable en el cierre porque el **embudo corre sobre las extracciones, no sobre los fulltexts**:
comparar campos de N notas es instantáneo y sólo los candidatos confirmados gastan un subagente. Sin
el embudo sería N² lecturas.

**No cambia la compuerta de aprobación:** sigue **proponiendo**, no escribiendo. Lo que cambia es que
aparece en el cierre en vez de esperar a que alguien se acuerde de auditar. Junto con los pares sin
verificar y los papers sin sintetizar, el cierre deja **tres cosas a la vista**.

## Entrada
El **eje** a barrer: una estrella (`slug`), un concepto, o "todo el corpus". Si no se da, preguntar o
tomar la última entidad tocada.

⛔ **Toda contradicción declara su entidad DESTINO (D-40).** Análogo de "no hay papers sueltos": una
contradicción es siempre **sobre algo**, y ese algo es una entidad de la bóveda.

| Sobre qué discrepan | Dónde va |
|---|---|
| parámetro o señal de una estrella | `disputes[]` de la ficha + fila en `## Inventario por eje` |
| algo de un método/indicador, **bajo las mismas condiciones** | `disputes[]` del concepto + fila en `## Inventario por eje` |
| algo que difiere **porque el régimen es distinto** (veredicto `aparente`) | fila en `## Régimen de validez` del concepto |

En el modo **puntual** el destino es **mandatorio**: si el usuario no lo dice, preguntar. Caso raro
—los dos papers discrepan sobre algo que no corresponde a ninguna entidad existente—: o es una
entidad que hay que crear, o está fuera del foco y **no entra** (mismo test de admisión de la regla
#0). Una disputa suelta no la encuentra nadie.

## Pasos

### 1. Reunir los claims comparables (andamiaje)
Juntar, para el eje elegido, qué afirma **cada** paper sobre **cada** hecho:
- **Estrella:** los papers con la estrella en `stars:` + su
  `vault/raw/ground_truth/<slug>.json` (NEA). Ejes típicos: existencia de cada señal RV, y sus
  valores `P/K/e/m·sini`; `P_rot`; indicadores de actividad; naturaleza de una señal (planeta vs
  actividad). Grep barato para juntar candidatos:
  ```bash
  grep -inE "P_?rot|K ?=|=\s*[0-9].*(d|day|m/s)|period|eccentric|activity|rotation" \
       vault/raw/fulltext/<slug>/*.txt
  ```
- **Concepto:** los papers del concepto = la **unión** `methods ∪ thesis_links` (D-24). ⚠ Juntar
  sólo por `thesis_links` pierde la mitad del eje: las dos llaves viven en papers distintos. Ejes: signo de una correlación, magnitud de
  un lag/desfasaje, mecanismo propuesto, régimen de validez.

> **Cómo juntar esos papers sin Obsidian.** La tabla `## Papers` de la ficha es **estampada**
> desde 1.35.0 (D-10/D-11, `make_notes.stamp_papers_table`) y refleja el universo de la última
> corrida de `make_notes.py <slug>`, así que puede estar vieja (el lint lo reporta como backlog).
> Para recalcularla ahora, el equivalente determinista (canónico en `CLAUDE.md`) **parsea el
> frontmatter con el parser del tooling** — `grep`/`awk` fallan acá porque las listas conviven en dos formas (bloque al crear la
> nota, flow style `stars: [x]` tras el retro-linkeo add-only) y además confunden `GJ 71` con
> `GJ 710`:
> ```bash
> python -c "import sys,glob;sys.path.insert(0,'scripts');import lib_config as c;[print(f) for f in sorted(glob.glob('vault/wiki/papers/*.md')) if '<nombre>' in (c.split_fm(open(f,encoding='utf-8').read()).get('stars') or [])]"
> ```
> (para un concepto, la población es la **unión** `methods ∪ thesis_links` (D-24): la misma línea
> dos veces, una por llave, y se unen los resultados — quedarse con una sola pierde la mitad).
>
> ⚠ **Mirá el estado de cada fuente ACÁ, en el andamiaje** (no en el fan-out: el subagente del paso 2
> tiene prohibido leer otra cosa que los dos `.txt`, y esto vive en el frontmatter de la nota):
> `retracted: true` → el paper **sale del corpus**, no se disputa (frontera dura; el lint ya lo
> bloquea). `corrections:` (corrigendum) → puede explicar una diferencia de valor sin que haya
> desacuerdo: leé el aviso antes de comparar. `pdf_source: eprint` → ese `.txt` es el **preprint**,
> así que una diferencia numérica puede ser **de versión y no entre fuentes** (#57). Un par con
> alguna de esas marcas se anota y se excluye del fan-out, o entra con la salvedad explícita.
>
> ⛔ **Mirá también el `role` de cada nota (#73): no todo par se contrasta igual, y uno de los cuatro
> casos NO es contraste.** El rol lo pobló la extracción (`fundacional` introduce el
> método/mecanismo · `aplicacion` lo instancia en un caso · `arbitro` reanaliza y resuelve una
> tensión previa):
> - **fundacional ↔ fundacional** → comparar supuestos y derivaciones.
> - **aplicación ↔ aplicación** → ¿replica?, ¿en qué **régimen**?
> - **fundacional ↔ aplicación** → **NO es contraste, es instanciación.** La aplicación no
>   contradice la ecuación: la pone a prueba. Mandarlo al fan-out **fabrica disputas falsas**, que es
>   el daño más caro de esta operación (de acá salen las `disputes[]`). Excluir del par.
> - **árbitro** → pesa distinto: es el que **resuelve** la tensión, no un paper más. Su valor no se
>   promedia con los otros; se reporta como resolución.
>
> Una nota **sin `role`** (corpus anterior a 1.16.0, o extracción incompleta) no habilita este
> descarte: contrastá con cuidado y anotá el hueco — el lint lo lista como backlog.
Armar una tabla mental `(hecho, papel A dice …, papel B dice …, NEA dice …)`. Los que coinciden se
descartan; los que difieren pasan al fan-out.

#### 1b. Excluir los pares YA JUZGADOS — el barrido no re-litiga (#63)

Antes de armar la lista de candidatos, sacar los pares sobre los que **ya hay un juicio escrito**.
Son dos carriles y hay que mirar los dos:

- los persistidos como `aparente` / `no-concluyente` en el registro versionado del sujeto
  (`vault/config/registro/<slug>.yaml`, sección `no_disputas:`) — se leen con **`load_no_disputas`**;
- los ya tagueados en las `disputes[]` de la ficha o del concepto (ésos son los `real`, que ya
  tienen su carril y su entrada aprobada).

```bash
# los pares ya juzgados como NO-disputa, indexados por la clave simétrica del par
python -c "import sys;sys.path.insert(0,'scripts');import lib_config as c;[print(k,'→',v['veredicto'],'·',v['motivo']) for k,v in c.load_no_disputas('<slug>').items()]"
```

La clave se arma con `c.par_key(bib_a, bib_b, eje)` y es **simétrica**: el par juzgado en cualquier
orden da la misma clave, y **cambia con el eje** (los mismos dos papers pueden coincidir en `P_rot`
y discrepar en `K`, así que juzgar uno no saltea el otro).

**Por qué:** cada par cuesta un subagente, y sin esto cada auditoría vuelve a pagar el mismo par
para reconstruir la misma conclusión — y el motivo por el que aquel desacuerdo no era desacuerdo no
lo tiene nadie, porque hasta #63 el `aparente` se reportaba al chat y ahí moría. Es el mismo agujero
que #51 cerró para el triage (el juicio de descarte vivía en `build/`, gitignored). **Contar cuántos
pares se saltearon por esta vía**: va al reporte de cierre.

⚠ Un par juzgado se saltea, **no** se borra ni se re-abre solo. Si cambió la evidencia (entró un
paper árbitro, se re-extrajo un `.txt`, apareció un corrigendum) el par se vuelve a juzgar a mano y
`save_no_disputa` **appendea** el juicio nuevo sin borrar el viejo: el registro es historial, y
`load_no_disputas` devuelve el último.

### 2. Fan-out: confirmar cada desacuerdo candidato (un subagente por par)
Para cada par en tensión, lanzar un subagente (tipo `Explore`: acá el resultado vuelve al padre, no
va a un directorio — ver #219) **en paralelo**, **en lotes de ≤ 15** (hay un tope de 20 concurrentes
y pasarlo corta en silencio, #218: contá *lanzados vs pares* antes de creer que el barrido cerró, y
re-lanzá sólo los que faltan en vez del lote entero). Cada uno lee **sólo
los dos PDF** en juego (`vault/raw/pdfs/**/<bibcode>.pdf`, #205; los `.txt` de
`vault/raw/fulltext/**/` sirven para **ubicar** con `grep -n`, no para citar — y en una fuente
**web** el `.txt` es la fuente, citada por línea) (grounding-first; prohibido de memoria) y devuelve:
- `desacuerdo`: `real` | `aparente` | `no-concluyente`
  - **real** = ambos papers afirman valores/hechos incompatibles **más allá del error** (o uno afirma
    existencia y el otro la niega). Con **cita textual + nº de página de cada uno** (#205).
    (El estado de las fuentes —`retracted`, `corrections`, `pdf_source: eprint`— se filtró en el
    paso 1: el subagente sólo ve las dos fuentes, así que no puede juzgarlo.)
  - **aparente** = distinto régimen, distinta definición, distinta época, o dentro de la barra de
    error → **no** es disputa. Devolver **cuál es la condición** que los separa, con su cita: en un
    **concepto** eso no se tira, es la fila de `## Régimen de validez` (#74), y un "aparente" sin la
    condición explícita no sirve para escribirla.
  - `no-concluyente` = artefacto de extracción (tabla/ecuación) o el texto no alcanza → abrir PDF o
    marcar. **Sólo agotada la estrategia de matcheo en AMBOS archivos** (puntero abajo): que la frase
    entera no aparezca con `grep` no alcanza — degradar por falso negativo de matcheo entierra una
    contradicción que sí existe.
- `eje`: qué hecho (`existence` | `P` | `K` | `e` | `msini` | `P_rot` | `mecanismo` | …).
- `resumen`: una línea de la discrepancia (qué dice cada uno).

> **Convenciones de lectura del `.txt` — rigen las de `verify-citations` (canónicas allá, acá sólo
> el puntero):** conteo de líneas con `grep -n`, no `splitlines()` de Python (#29: los form feeds
> corren la numeración), y **estrategia de matcheo** en `.txt` multi-columna (#44): escalera de
> acortamiento (oración completa → fragmento distintivo contenido en una línea física),
> de-hifenado, y **prohibido normalizar espacios sin partir antes cada línea en la canaleta**
> (colapsar el hueco de 8+ espacios — sea sobre el archivo entero o por línea, #46 — empalma
> columnas → falso positivo). Acá el riesgo se **amplifica**: el par exige cita textual de **dos** fulltexts
> (con ~73% de prevalencia multi-columna por archivo, ~93% de chance de que al menos uno esté
> afectado) y un falso negativo de matcheo en cualquiera de los dos colapsa el veredicto a
> `no-concluyente` sobre una disputa real.

Prompt sugerido: *"Leé SOLO estas dos fuentes: `<A.pdf>` y `<B.pdf>` (sus índices `<A.txt>` y
`<B.txt>` sólo para ubicar con `grep -n`; si una fuente es web —`pdf: null`, `source_url`— su `.txt`
ES la fuente y se cita por línea). ¿Se contradicen sobre «<hecho>»?
Respondé real/aparente/no-concluyente + el eje + cita textual con nº de PÁGINA del PDF de CADA
paper (#205; la cita son las palabras del PDF, no las del `.txt`) + una línea
de resumen. Para localizar, en CADA índice: el `.txt` suele entrelazar dos columnas en la misma
línea física, así que si la oración completa no aparece con grep NO concluyas que falta — acortá a
un fragmento distintivo de 3–6 palabras (y reintentá partiendo por guión de corte); PROHIBIDO
normalizar espacios sobre el archivo entero Y también colapsar un hueco de 8+ espacios dentro de
una línea (ambos empalman columnas y fabrican adyacencias falsas); si normalizás, partí antes la
línea en ese hueco y tratá cada segmento por separado; ubicada la página, abrí el PDF ahí.
'no-concluyente' sólo si agotaste eso en las dos fuentes. 'real' sólo si los valores son
incompatibles más allá del error, o uno afirma y el otro
niega. Si es 'aparente', decí EXACTAMENTE bajo qué condiciones vale cada uno (SNR, muestreo, tamaño
de muestra, definición del observable, época) con su cita — no alcanza el rótulo. No uses memoria ni
otros papers."*

### 3. Proponer las disputas (NO escribir todavía)
Presentar al usuario la lista de desacuerdos **reales** como tabla, con la entrada `disputes[]` (o nota
de concepto) que se agregaría en cada caso, y **pedir aprobación**. Formato de la propuesta:
- **Estrella (parámetro/existencia):** `disputes` **a nivel nota**, con **posiciones explícitas**
  (#71). `field` nombra el eje: `P_rot` para un campo estelar, `<letra>.<param>` para uno planetario
  (`b.K`, `b.existence`). `posiciones[]` lleva **una por cada lado**: `{ref: <bibcode>, value: …}`
  por paper (el bibcode **debe** existir como nota, lo chequea el lint) y, **si NEA arbitra**,
  `{source: ground_truth, value: …}` — NEA queda como verdad y el frontmatter no se toca.
  ⛔ **Cada `value` se copia de la cita textual que el subagente devolvió con su página (#392)**,
  nunca del recuerdo de «lo que ese paper suele decir»: la posición de una disputa es un campo que
  identifica una afirmación, y un valor puesto de memoria fabrica el desacuerdo que el skill
  existe para detectar.
  ```yaml
  disputes:
    - field: P_rot
      posiciones:
        - {ref: 2018Autor..., value: 33}
        - {ref: 2021Autor..., value: 11.5}
      note: 11.5 d podría ser el armónico
  ```
  **Esto es lo que antes no se podía escribir:** el schema viejo tenía el polo de verdad hardcodeado
  (el otro lado era el frontmatter), así que un desacuerdo **paper↔paper** —el caso normal cuando NEA
  calla— terminaba en prosa: no acumulable, no chequeable por el lint, invisible al consumidor
  máquina. Y `P_rot`, que es de la estrella, no tenía dónde colgar. El lint **no lee** el schema
  viejo: si la bóveda todavía lo tiene, lo reporta como bloqueante y hay que migrar
  (`make_notes.py --migrate-disputes`) antes de taguear nada nuevo.
- **Concepto (mecanismo/signo/lag):** `disputes` a nivel nota **igual que en una ficha** (#71) —
  acá la disputa es **simétrica por definición**, no hay valor de frontmatter contra el cual poner un
  `alt`, así que las dos posiciones son `{ref: …, value: …}`. Más una línea en la prosa citando
  **ambos** `[[bibcode]]`. Si el desacuerdo toca una hipótesis, la postura se ajusta en **su tabla de
  evidencia** (D-21), no en la nota del paper. Si el concepto
  tiene `## Inventario por eje` (#72), el desacuerdo real va **además** como filas de ese eje.
Los **no-concluyentes** se listan aparte (no se tocan; sirven para no re-flaggearlos).

⛔ **Los `aparente` de un CONCEPTO no se descartan (#74).** En una estrella, "distinto régimen,
distinta definición, distinta época" es un no-hallazgo y se tira. En un concepto **es el hallazgo**:
dos papers dicen cosas distintas y **los dos tienen razón** porque valen bajo condiciones distintas
(SNR, muestreo, tamaño de muestra, definición del observable). Cada `aparente` de un concepto se
propone como **fila de `## Régimen de validez`** (`Afirmación | Vale bajo (régimen) | Fuente | Rol`),
con la condición que el subagente identificó y el `role` (#73) de cada paper — recordando que una
**aplicación** acota el régimen de una **fundacional**, no la contradice. Y si de ahí sale una
condición que **nadie midió**, eso es un *régimen no cubierto* → `## Huecos`. Descartarlos es
perder justamente lo que el barrido encontró.

### 4. Aplicar lo aprobado — y PERSISTIR los que no son disputa (#63)
Sólo lo que el usuario aprobó: taguear `disputes` a nivel nota en la ficha (y reflejar la disputa en la
tabla/prosa), o escribir la línea de desacuerdo en el concepto. Nada de sobreescribir NEA.

Y el otro carril, que antes se perdía: cada par que volvió **`aparente`** o **`no-concluyente`** se
escribe en `no_disputas:` del registro versionado, con su **motivo** —la condición que los separa,
o por qué el texto no alcanzó—:

```bash
python -c "import sys;sys.path.insert(0,'scripts');import lib_config as c;c.save_no_disputa('<slug>', {'bibcodes':['<A>','<B>'],'eje':'P_rot','veredicto':'aparente','motivo':'<la condición que los separa, con su cita>'})"
```

Reglas del carril, que el propio `save_no_disputa` hace cumplir:
- **`motivo` obligatorio** (aborta si está vacío): mismo criterio que el `--reason` del triage — en
  seis meses lo que sirve es el motivo, no la categoría. Y un par persistido sin motivo queda
  bloqueado en el barrido sin que nadie pueda revisar el juicio, que es peor que no persistirlo.
- **Un `real` NO va acá** (aborta): su carril es `disputes[]`, que es contenido aprobado de la
  bóveda. Enterrarlo en `no_disputas` haría que el barrido siguiente lo saltee por «ya juzgado» y la
  disputa real nunca llegue a la nota.
- Persistir un par **no toca nada más**: no borra, no reabre y no modifica las `disputes[]` ya
  tagueadas. Los dos carriles conviven — `disputes` es contenido de la bóveda que el usuario aprobó,
  `no_disputas` es bitácora de la revisión.

⚠ En un **concepto**, persistir el `aparente` **no reemplaza** su fila de `## Régimen de validez`
(#74): ahí el aparente es el hallazgo y va a la nota. El registro sólo evita re-juzgar el par.

### 5. Verificar, lint, cierre
- **verify-citations** sobre las disputas nuevas (cada `note` y cada `value` de una posición debe
  estar respaldada por el
  fulltext del `ref` — es prosa con `[[bibcode]]` nueva).
- `python scripts/lint.py --cierre` (0 bloqueante — atención a *ref de una posición sin paper destino* y a
  *disputes mal formadas*: una disputa con **una sola** posición no es un desacuerdo, es una
  afirmación, y va a la prosa citada; el bibcode
  discrepante tiene que existir como nota).
- Appendear a `vault/wiki/log.md` (cuántos desacuerdos reales, cuántos tagueados). `git add` de los
  archivos **específicos**; **preguntar antes de `push`**.

## Reporte (al chat)
Cuántos pares en tensión se evaluaron, **cuántos se saltearon por estar ya juzgados** (los de
`load_no_disputas` y los ya tagueados en `disputes`), cuántos **reales** vs aparentes, y cada disputa
propuesta con su resolución. El salteado se reporta porque si no, un barrido que no gastó ningún
subagente se lee igual que uno que no encontró nada — la distinción de D-43 aplicada a esta pasada. Honesto: un "aparente" bien resuelto (mismo valor, distinto régimen) es tan valioso como
una disputa real — evita tagueos espurios. En un **concepto**, además, cada aparente que sobrevive
es una **fila de régimen** propuesta (#74): reportar cuántas, porque ahí el aparente no es un
descarte sino el producto.

## Límite honesto
Es **juicio de LLM** claim↔claim, robusto (par independiente, grounding-first, cita de ambos lados) pero
no prueba. No detecta lo que ningún paper del corpus contradice (un error compartido por todas las
fuentes pasa). Cubre el corpus **cerrado**: si falta el paper árbitro, la disputa queda abierta.
