---
name: audit-note
description: >-
  Usar cuando el usuario quiere auditar EN DETALLE una ficha de la bóveda — una estrella, un concepto/método, una hipótesis o una query — para garantizar que lo que la nota dice es verdad y que se sostiene sola ("auditá la ficha de tau Ceti", "revisá en detalle el concepto de ICA", "¿esta ficha es confiable?", "chequeá la coherencia de esta nota"). Es CARO por diseño (abre PDFs, recuenta, re-renderiza) y se corre a pedido, nunca como paso de cierre. Cubre el eje que ninguna otra capa mira: la nota contra sí misma, contra su cadena y contra el mundo declarado. Lo que no se pueda verificar queda MARCADO en la propia ficha para ir al PDF.
version: 1.0.0
---

# Audit-note — ¿esta ficha dice la verdad y se sostiene sola?

**La regla de oro, y todo lo demás se deriva de ella: lo que la ficha dice tiene que ser verdad.**
Todo lo que se presenta como dato tiene que estar verificado, y **ante la menor duda la afirmación
queda marcada para ir al PDF**. Barato en falsos positivos no es el objetivo. El objetivo es que
nada pase.

## Por qué existe: el hueco que las otras capas no cubren

| capa | qué chequea | qué NO |
|---|---|---|
| `lint` | salud **estructural** (links, schema, forma del frontmatter, forma del artefacto) | si lo que la nota afirma es cierto |
| `verify-citations` | claim ↔ **su propia** fuente, par por par | la nota **como conjunto** |
| `find-contradictions` | claim ↔ claim **entre** fuentes | la nota contra **sí misma** |
| `auditar` | el **framework** (código, tests, invariantes) | la bóveda |

Falta el eje del **artefacto completo**, y no es teórico. Una pasada ad-hoc sobre un concepto ya
cerrado —`lint --cierre` en 0, 99 pares en `soportada`— encontró **más de 40 defectos**:

- la nota **no era implementation-ready**, que es el estándar que el contrato le exige a
  `concepts/methods`: faltaba el puente `g = G'` (la fórmula usaba `g` y `g` no se definía en
  ninguna parte), el criterio de convergencia, la deflación entre filas —sin la cual el bucle
  devuelve *n* copias de la misma componente— y el algoritmo real del método de estabilidad que la
  nota prescribía como obligatorio. **Cuatro de los cinco estaban en un `.txt` que la bóveda ya
  tenía bajado**: omisión de la síntesis, no hueco del corpus;
- **dos filas de una tabla fusionadas** en una línea física → una afirmación entera invisible al
  renderizar… y era un par **verificado**;
- un **párrafo duplicado**, un **backtick abierto durante 268 líneas**, y el preámbulo de una
  sección huérfano **190 líneas antes**, dentro de otra;
- la nota **se contradecía a sí misma**: una sección afirmaba lo que otra, 100 líneas después,
  declaraba incorrecto;
- **afirmaba un estado del repo que era falso** («el radio X, ya declarado en `themes.yaml`»);
- **prosa corrompida** justo en el párrafo con las reglas operativas;
- afirmaciones fácticas **sin cita y sin marca**;
- la cabecera publicaba **2 de las 3 fechas** obligatorias;
- **condiciones acotantes** que `verify-citations` había levantado y que quedaron **sólo en la
  tabla**, sin llegar nunca a la prosa ni a `## Régimen de validez`.

Ninguno lo veía nadie. De ahí este skill.

## Cuándo

**A pedido explícito.** No es paso de cierre de ninguna operación: es caro (abre PDFs, recuenta,
re-renderiza, lanza subagentes) y su valor está en correrlo cuando se quiere **garantizar** una
ficha — antes de apoyarse en ella para escribir, antes de publicarla, o cuando algo huele mal.

## Entrada

La ruta de la nota. Si el usuario nombra la entidad («el concepto de ICA», «tau Ceti»), resolver la
ruta y confirmarla antes de empezar.

---

## Los siete frentes

Se lanzan **en paralelo**, un subagente por frente (⚠ ver *Concurrencia*), cada uno con su
población declarada. Ninguno edita: **todos reportan**. La escritura la hace el paso 3, serial.

### Frente 1 — Estándar de la nota

Contra el *Estándar transversal* de `CLAUDE.md`: **autosuficiente**, **dual-audiencia**, y para
`concepts/methods` además **implementation-ready con el régimen explícito** (los indicadores viven ahí: son métodos chicos, #246).

⛔ **La prueba operativa, que es lo que hace este frente medible:** *escribir el pseudocódigo (o la
receta de uso) desde la nota y anotar dónde se traba.* Cada punto donde haya que abrir la fuente es
un hallazgo. Y por cada uno, decir **cuál de las tres cosas es**:

- lo que falta **está en un `.txt`/PDF que la bóveda ya tiene** → **omisión de la síntesis**, se
  cierra copiando de la fuente;
- lo que falta es un valor que la nota declaró **ilegible en una figura** → antes de aceptar el
  hueco, chequeá si la figura es un **campo** (contornos, mapa de color, densidad): ahí «el valor a
  x» **no existe sin el nivel**, y las lecturas que «no reconcilian» son **niveles distintos**, no
  ruido. Un hueco declarado de más es peor que uno de menos: dice *«el corpus no puede responder
  esto»* y el consumidor deja de buscar. Medido (#281): el corpus **sí** tenía la respuesta;
- lo que falta **no está en el corpus** → **hueco real**, va a `## Huecos` declarado.

La distinción es el producto principal del frente: sin ella, «falta X» no es accionable.

Y el régimen: una ecuación sin las condiciones bajo las que vale es **implementable y equivocada**.
¿`## Régimen de validez` cubre lo que el resto de la nota afirma?

### Frente 2 — La nota contra sí misma

- **Contradicciones internas**: dos secciones que afirman cosas incompatibles.
- **Contenido en la sección equivocada**: el contrato define `## Inventario por eje` (desacuerdo
  real **bajo las mismas condiciones**) y `## Régimen de validez` (la misma afirmación bajo
  condiciones distintas) como **disjuntas**. Una fila cuyo preámbulo dice «no coinciden» pero cuyas
  fuentes ni siquiera hablan del mismo eje está en la sección equivocada.
- **Duplicación**: la misma cita en tres secciones que el contrato define disjuntas no es
  particionar, es triplicar.
- **Preámbulos huérfanos**: una sección que arranca `##` → `###` → tabla, sin la prosa que dice
  para qué está.

### Frente 3 — Integridad del artefacto

**Lo que el consumidor ve.** Buena parte ya la cubre el lint desde #227 (fila de tabla que no
renderiza, marcador sin cerrar, párrafo duplicado): **correr el lint primero y no re-derivarlo**.
Lo que queda para el frente:

- que las tablas **digan lo que muestran**: encabezado ↔ contenido de las celdas;
- headings repetidos, numeración de listas rota, `[[wikilink]]` partidos por un truncado;
- que la nota **abra bien en Obsidian**: `$...$` (no `\(...\)`), rutas relativas al vault.

### Frente 4 — Aritmética y snapshots

**Cada número que la nota publica, recontado contra la fuente que lo produce**: los conteos de la
cabecera, los del roll-up, los del bloque de verificación, los del apéndice de excluidos, y todo «N
papers» / «M de K» de la prosa.

⚠ Y la distinción que hace justo el reporte: un número puede ser un **snapshot fechado** legítimo.
Lo que no puede es estar en una sección redactada **en presente** sin decir a qué fecha corresponde.

### Frente 5 — Cadena de verdad

Por cada afirmación fáctica de la prosa: ¿**citada** `[[bibcode]]`, **marcada** `inferencia` con sus
premisas, o **sin respaldo**?

Y el eslabón que se pierde siempre: las **condiciones** que `verify-citations` levantó, ¿aterrizaron
en la prosa o en `## Régimen de validez`, o quedaron **sólo en la tabla**? La tabla no es donde el
consumidor las lee. Triarlas con la regla de dos valores:

- **`acota`** — la afirmación es **falsa** fuera de esa condición → tiene que estar en la prosa o en
  el régimen;
- **`contextualiza`** — la afirmación sigue siendo cierta y la condición agrega procedencia → rige
  la regla de poda, no se edita.

### Frente 6 — Coherencia con el mundo declarado

Lo que la nota afirma **sobre el repo**, contrastado contra los archivos: que un tema esté declarado
en `themes.yaml`, que un radio exista, que un paper esté en el corpus, que un slug se llame así.
Medido: una nota afirmaba «el radio X, **ya declarado en `themes.yaml`**» sobre un archivo que
declara un solo tema — y lo afirmaba en el bullet de `## Huecos` que un consumidor lee justamente
para saber si el hueco tiene dueño.

### Frente 7 — La nota contra su cadena

La ficha no vive sola: sus papers, sus artefactos y su registro tienen que decir lo mismo.

- lo que la ficha atribuye a un paper, ¿lo dice la **nota de ese paper**?
- los papers que el roll-up lista, ¿están todos sintetizados, o hay `no_sintetizado` mezclados sin
  marca?
- lo que el registro dice del universo, ¿coincide con lo que la ficha publica?

---

## ⛔ La marca: `⚠verificar en el PDF`

**Es la cuarta marca en línea del sistema**, y la razón de que este skill escriba en la nota en vez
de dejar un reporte que se pierde.

    <afirmación> ⚠verificar en el PDF (<qué se dudó>, <fecha>)

Propiedades, las mismas que `⛔retractada` y `⚠desactualizado`:

- **no destruye**: la afirmación puede ser cierta, y borrarla destruiría trabajo;
- **es visible para el consumidor**, que es quien tiene que saber que ahí hay una duda;
- **la levanta el lint** como backlog, así que la deuda no se olvida;
- **se saca cuando alguien la verifica**, con la evidencia.

⛔ **Cuándo marcar, y el criterio es amplio a propósito:** todo lo que el frente correspondiente no
pudo cerrar. Un valor cuya página no se pudo confirmar. Una cita cuya fuente no está en disco. Una
afirmación cuya condición no se pudo triar. Un número que no reconcilia. **Ante la menor duda, se
marca** — el costo de una marca de más es que alguien abra un PDF; el de una de menos es que la
bóveda afirme algo falso con cara de verificado.

⚠ **Lo que la marca NO es:** una excusa para no verificar. Si la fuente está en disco y se puede
abrir, se abre. La marca es para lo que **no se puede** cerrar en esta pasada.

---

## Pasos

### 0. Precondiciones (baratas, y acotan todo lo demás)

```bash
python scripts/lint.py --cierre <slug>          # la salud estructural, ya resuelta
```

Correrlo **primero**: lo que el lint ya reporta no se re-deriva, se **cita**. Si hay bloqueantes,
decirlo y seguir — la auditoría vale igual, pero el reporte tiene que declarar sobre qué corrió.

Y el inventario de la cadena, que es la población de los frentes 5 y 7:

```bash
# los pares de la nota, con su ancla, y las fuentes que cita
python -c "import sys;sys.path.insert(0,'scripts');import lib_blocks as lb;\
p=lb.pairs_of(open('<nota>',encoding='utf-8').read());print(len(p),'pares',len({x.bibcode for x in p}),'fuentes')"
```

### 1. Fan-out: un subagente por frente

Cada uno recibe **su frente, la ruta de la nota y la regla de reporte**, y devuelve **hallazgos con
evidencia**, clasificados:

- **`NOTA`** — defecto del contenido de esta ficha; se arregla acá.
- **`CADENA`** — el defecto está en un paper, un artefacto o el registro; se arregla ahí.
- **`FRAMEWORK`** — el contrato o el tooling permite/produce esto; va como issue al template.
- **`DECLARADO`** — ya está anotado como pendiente; confirmarlo, no re-reportarlo.

⛔ **Ningún frente edita.** Y un frente que vuelve limpio **declara su población**: qué miró, sobre
cuántos archivos, y por qué eso alcanza. Un «todo bien» sin población no sirve — es el falso limpio
que todo este framework existe para no producir.

### 2. Barrera

**Antes de derivar cualquier trabajo, contá cuántos frentes devolvieron contra cuántos lanzaste, y
declaralo.** Está medido en este repo (#199): armar los lotes con etapas todavía corriendo dejó
hallazgos que no miró nadie.

### 3. Resolver — serial, un solo escritor

⛔ **Un hallazgo dice DÓNDE mirar, no QUÉ escribir.** Medido dos veces: correcciones redactadas
copiando el encuadre del reporte **introdujeron errores nuevos**. Antes de escribir, **re-abrir la
fuente**.

Orden, y es el del daño:

1. **Lo que hace que la nota diga algo falso** — contradicciones internas, afirmaciones sobre el
   repo que no son ciertas, números que no dan, prosa corrompida.
2. **Lo que la hace no sostenerse sola** — lo que falta para implementar/usar, con la distinción del
   frente 1 (si está en el corpus se copia; si no, va a `## Huecos`).
3. **Lo que rompe el artefacto** — la forma.
4. **Las condiciones `acota`** que quedaron fuera de la prosa.
5. **Lo que no se pudo cerrar** → `⚠verificar en el PDF`.

A escala, las correcciones **no se aplican a mano**: `python scripts/apply_fixes.py <nota.md>
<dir-de-fixes> [--write]`. ⚠ El `viejo` de cada fix tiene que ser **un bloque entero** tal como
`lib_blocks` lo parte, y el aplicador es **todo o nada**.

### 4. Re-verificar lo tocado

**Corregir es escribir, y lo escrito se verifica** (#203). Todo par cuya afirmación se editó queda
sin verificar —el ancla se movió— y toda cita que la corrección haya agregado es un **par nuevo**:
correr `verify-citations` sobre **ese subconjunto**. No sobre la nota entera: sobre lo que cambió.

⛔ **El subconjunto lo emite un comando, no se arma a ojo:**

```bash
python scripts/reverify_subset.py <nota> --json build/<slug>/reverif.json
```

Reparte los pares en tres: **re-anclables**, **a re-verificar** y **filas huérfanas**, y el JSON
emite **las tres listas** (#285) — el subconjunto por fuente, el **emparejamiento propuesto con su
`score`** y las huérfanas.

⛔ **Mirá la banda de revisión antes de aceptar el re-anclaje.** Lo que cae por debajo de `--banda`
(0,85) sale listado en el stdout con las dos puntas del emparejamiento: es donde un error **transfiere
el veredicto al par equivocado** y publica una cita real, verificada, bajo la afirmación que no es.
Medido: de 86 propuestas, **2 iban a la fila equivocada** —scores 0,60 y 0,67— y las dos eran **del
mismo bibcode**, o sea justo donde la guarda de «nunca cruza `bibcode`» no ve nada. ⚠ La salida **no**
es subir `--umbral`: eso manda al fan-out re-anclajes buenos, que es el costo que #282 bajó.

⚠ **Y esperá que sea grande.** El ancla es de **bloque**, así que tocar una cláusula vence **todos**
los pares de su párrafo: medido en un `audit-note` real, el 55–60 % de la nota. Peor, el ciclo **no
converge solo** — 63 → 76 → 78 en tres rondas (#282). Por eso el comando separa dos correcciones que
vencen igual y no son lo mismo:

- la que **cambia lo que la afirmación dice** → el veredicto no vale, va al fan-out;
- la **derivada de la propia verificación** —el texto nuevo son las palabras que el verificador sacó
  de la fuente, con su página— → el texto quedó **más** anclado, y re-preguntarle al juez si confirma
  su propio dictamen no es verificación. Se **re-ancla**: el veredicto se lleva, el ancla se
  recalcula. Medido: de 78 vencidos, **72 de este tipo**.

⛔ **El prompt de la re-verificación va CIEGO, y la regla no se copia acá: vive en
`verify-citations` (#258).** Lo que se lanza al fan-out es `verify-citations` sobre el subconjunto,
así que rige su forma de prompt — se manda el par (la afirmación tal como está hoy y su fuente), no
la historia de qué marcó la ronda anterior ni qué se corrigió, con la excepción del par marcado
`inferencia`. Del JSON de arriba, al verificador le va **`re_verificar[<bibcode>][].texto`** y nada
más: `re_anclaje` es la historia. El detalle, con la medición que lo motiva, en el paso *Resolver lo
que falla* de `.claude/skills/verify-citations/SKILL.md`.

⛔ El re-anclaje es una **propuesta**: dice que la afirmación sigue siendo reconociblemente la misma,
**no** que la corrección haya sido fiel. Quien lo acepta **lo declara en el bloque** — de qué ronda
viene el veredicto, y que el texto es posterior a la corrección. Sin esa línea, el bloque afirma una
frescura que no tiene.

### 5. Cerrar

```bash
python scripts/lint.py --cierre <slug>
```

Y dejar el registro donde vive el resto: entrada en `vault/wiki/log.md` (`## AAAA-MM-DD —
audit-note: <nota>`) con **qué se miró, qué se encontró, qué se arregló y qué quedó marcado**, y
`vault/STATUS.md` si el estado cambió.

Los hallazgos `FRAMEWORK` se anotan como backlog y **se abren como issue en el template** — no se
arreglan en la instancia (regla de oro).

---

## Concurrencia

⛔ El harness corta en **20 subagentes concurrentes** y el error llega mezclado con los lanzamientos
exitosos del mismo mensaje. Con siete frentes no hay problema; **con un fan-out por fuente (paso 4)
sí**. Lotear, y contar lanzados contra existentes **antes** de contar devueltos contra lanzados.

⚠ Y **no re-lanzar el lote entero ante ese error**: en este repo, reintentos ciegos produjeron
extracciones duplicadas.

## Límite honesto

Esto es **juicio de LLM leyendo la nota y sus fuentes**. Es fuerte —siete miradas independientes,
cada una con su población declarada, sobre un corpus cerrado— y **no es prueba**. Lo que sí garantiza
es que **nada quede afirmado como verificado sin estarlo**: lo que no se pudo cerrar sale marcado, y
esa marca es visible para el consumidor y la levanta el lint.
