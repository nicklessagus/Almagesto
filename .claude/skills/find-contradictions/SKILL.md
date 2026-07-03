---
name: find-contradictions
description: Usar cuando el usuario quiere detectar desacuerdos entre papers del corpus sobre el mismo hecho ("buscá contradicciones en el corpus", "qué papers se contradicen sobre tau Ceti", "revisá disputas de P_rot", "detectá desacuerdos sobre la señal b de GJ 581", "¿hay papers que discrepen sobre X?"). Barre el corpus por eje (estrella/parámetro o concepto), confirma cada desacuerdo contra el fulltext y PROPONE entradas disputes[] / notas de disputa para que el usuario apruebe.
version: 1.0.0
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
— una discrepancia paper↔NEA se taguea en `planets[].disputes[]`, **no** se sobreescribe NEA. Un
desacuerdo paper↔paper sobre algo que NEA no arbitra (P_rot, mecanismo de actividad, naturaleza de una
señal) se refleja en la prosa de la ficha/concepto citando **ambas** fuentes. Sólo desacuerdos
**materiales** (mayores que el error reportado; no diferencias cosméticas dentro de la barra).

## Cuándo correrlo
- A pedido: "buscá contradicciones", "qué se contradice sobre X", "revisá disputas del corpus".
- Recomendado tras un `ingest-star`/`ingest-topic` grande, o al cerrar una estrella con muchos papers.
- **No** es paso de cierre automático (a diferencia de verify-citations): es una auditoría explícita.

## Entrada
El **eje** a barrer: una estrella (`slug`), un concepto, o "todo el corpus". Si no se da, preguntar o
tomar la última entidad tocada.

## Pasos

### 1. Reunir los claims comparables (andamiaje)
Juntar, para el eje elegido, qué afirma **cada** paper sobre **cada** hecho:
- **Estrella:** los papers con la estrella en `stars:` (tabla `## Papers` de la ficha) + su
  `vault/raw/ground_truth/<slug>.json` (NEA). Ejes típicos: existencia de cada señal RV, y sus
  valores `P/K/e/m·sini`; `P_rot`; indicadores de actividad; naturaleza de una señal (planeta vs
  actividad). Grep barato para juntar candidatos:
  ```bash
  grep -inE "P_?rot|K ?=|=\s*[0-9].*(d|day|m/s)|period|eccentric|activity|rotation" \
       vault/raw/fulltext/<slug>/*.txt
  ```
- **Concepto:** los papers con `thesis_links: <concept>`. Ejes: signo de una correlación, magnitud de
  un lag/desfasaje, mecanismo propuesto, régimen de validez.
Armar una tabla mental `(hecho, papel A dice …, papel B dice …, NEA dice …)`. Los que coinciden se
descartan; los que difieren pasan al fan-out.

### 2. Fan-out: confirmar cada desacuerdo candidato (un subagente por par)
Para cada par en tensión, lanzar un subagente (tipo `Explore`) **en paralelo**. Cada uno lee **sólo
los dos** `vault/raw/fulltext/**/<bibcode>.txt` en juego (grounding-first; prohibido de memoria) y devuelve:
- `desacuerdo`: `real` | `aparente` | `no-concluyente`
  - **real** = ambos papers afirman valores/hechos incompatibles **más allá del error** (o uno afirma
    existencia y el otro la niega). Con **cita textual + nº de línea de cada uno**.
  - **aparente** = distinto régimen, distinta definición, distinta época, o dentro de la barra de
    error → **no** es disputa (anotar por qué).
  - `no-concluyente` = artefacto de extracción (tabla/ecuación) o el texto no alcanza → abrir PDF o marcar.
- `eje`: qué hecho (`existence` | `P` | `K` | `e` | `msini` | `P_rot` | `mecanismo` | …).
- `resumen`: una línea de la discrepancia (qué dice cada uno).

Prompt sugerido: *"Leé SOLO estos dos archivos: `<A.txt>` y `<B.txt>`. ¿Se contradicen sobre «<hecho>»?
Respondé real/aparente/no-concluyente + el eje + cita textual con nº de línea de CADA paper + una línea
de resumen. 'real' sólo si los valores son incompatibles más allá del error, o uno afirma y el otro
niega. No uses memoria ni otros papers."*

### 3. Proponer las disputas (NO escribir todavía)
Presentar al usuario la lista de desacuerdos **reales** como tabla, con la entrada `disputes[]` (o nota
de concepto) que se agregaría en cada caso, y **pedir aprobación**. Formato de la propuesta:
- **Estrella (parámetro/existencia):** `planets[].disputes[]` con `field` (`existence`|`P`|`K`|`e`|`msini`),
  `ref` (el bibcode discrepante — **debe** existir como nota de paper, lo chequea el lint), `note` (qué
  dice ese paper), y `alt` (el valor según ese paper, para disputas de valor). NEA queda como verdad.
- **Concepto (mecanismo/signo/lag):** una línea en la prosa citando **ambos** `[[bibcode]]` con el
  desacuerdo explícito, y ajustar el `bearing` del paper discrepante si aplica.
Los **aparentes**/**no-concluyentes** se listan aparte (no se tocan; sirven para no re-flaggearlos).

### 4. Aplicar lo aprobado
Sólo lo que el usuario aprobó: taguear `planets[].disputes[]` en la ficha (y reflejar la disputa en la
tabla/prosa), o escribir la línea de desacuerdo en el concepto. Nada de sobreescribir NEA.

### 5. Verificar, lint, cierre
- **verify-citations** sobre las disputas nuevas (cada `note`/`alt` debe estar respaldada por el
  fulltext del `ref` — es prosa con `[[bibcode]]` nueva).
- `python scripts/lint.py` (0 bloqueante — atención a `disputes[].ref sin paper destino`: el bibcode
  discrepante tiene que existir como nota).
- Appendear a `vault/wiki/log.md` (cuántos desacuerdos reales, cuántos tagueados). `git add` de los
  archivos **específicos**; **preguntar antes de `push`**.

## Reporte (al chat)
Cuántos pares en tensión se evaluaron, cuántos **reales** vs aparentes, y cada disputa propuesta con su
resolución. Honesto: un "aparente" bien descartado (mismo valor, distinto régimen) es tan valioso como
una disputa real — evita tagged espurios.

## Límite honesto
Es **juicio de LLM** claim↔claim, robusto (par independiente, grounding-first, cita de ambos lados) pero
no prueba. No detecta lo que ningún paper del corpus contradice (un error compartido por todas las
fuentes pasa). Cubre el corpus **cerrado**: si falta el paper árbitro, la disputa queda abierta.
