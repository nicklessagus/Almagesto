---
name: auditar
description: Usar cuando el usuario pide una pasada de verificación profunda del FRAMEWORK (no de la bóveda) — "auditá el repo", "buscá errores en el código y la doc", "revisá que los invariantes estén cubiertos", "verificá que la doc sea coherente con el código", "revisá los tests que no testean nada". Corre primero los gates deterministas, después manda subagentes a los frentes que ningún script decide, verifica cada hallazgo de forma adversaria, y deja un artefacto acumulativo con IDs estables. NO arregla y NO borra tests: termina en el hallazgo con su test rojo.
version: 1.36.0
---

# Auditar — pasada de verificación profunda del framework

Operación de **auditoría del andamiaje** (`scripts/`, `tests/`, `tools/`, `docs/`, `.claude/skills/`,
`README.md`, `CLAUDE.md`). **No audita la bóveda** — para eso están `lint.py`, `verify-citations` y
`find-contradictions`. Trabajar desde la raíz del repo.

> ⛔ **Sólo en el repo template.** Auditar el framework desde una instancia no tiene sentido: ahí el
> framework no se edita (regla de oro de `CLAUDE.md`). Si `git remote -v` muestra un `upstream`
> apuntando a Almagesto, esto no es el template — decirlo y parar.

> **Dónde vive.** Versionado en `tools/auditar/`: viaja a las instancias, pero ahí es inerte (las
> skills se descubren en `.claude/skills/`). En el template, symlink local excluido en
> `.git/info/exclude`: `ln -s ../../tools/auditar .claude/skills/auditar`. La bitácora no se versiona.

---

## 1. Qué es y qué no es

**Qué es.** Una pasada **repetible y comparable entre corridas** que busca, en este orden:
discrepancias doc↔doc, doc↔código, docstring↔comportamiento, invariantes sin cobertura, código sin
invariante, ayuda desactualizada y tests que no prueban nada.

**Qué no es.**
- **No arregla.** Cada corrida termina en el hallazgo verificado, y —si es de código— en un **test
  rojo reproducible**. El fix es una pasada aparte, de a un issue y con aprobación.
- **No borra tests.** Los propone para borrar, con evidencia de mutación. El borrado lo decide el usuario.
- **No re-deriva lo que un gate ya decide.** Un número de cobertura opinado por un modelo que
  contradice al ratchet es ruido, no hallazgo.
- **No sube un techo de ratchet.** Nunca, y menos para poner verde un rojo.

**Regla de oro:** *los gates deciden, el modelo juzga lo que ningún gate puede decidir.* La Fase 1 es
barata y autoritativa; la Fase 2 es cara y es juicio. Si las dos discrepan sobre el mismo hecho, gana
el gate y la discrepancia **se anota como hallazgo sobre el gate**.

---

## 2. Fase 0 — Alcance declarado

Sin alcance fijo, cada corrida barre distinto y las corridas no se comparan. Antes de nada, contar el
universo y **anotarlo en el encabezado del artefacto**:

```bash
git rev-parse --short HEAD; git describe --tags --abbrev=0 2>/dev/null
ls scripts/*.py | wc -l; ls tests/test_*.py | wc -l; ls .claude/skills/*/SKILL.md | wc -l
ls docs/*.md; grep -c 'INV-' docs/trazabilidad-ratchet.yaml >/dev/null 2>&1
```

El encabezado declara: commit, tag, **N scripts · M tests · K skills · docs auditados**, y la fecha.
Al cerrar, declarar también **qué quedó fuera del barrido y por qué** — la cobertura del barrido es
parte del resultado, no un detalle.

No olvidar en el alcance lo que no es `.py` ni `.md`: **`pytest.ini`, `.github/workflows/`, los siete
ratchets (`tools/mutacion-ratchet.yaml`, `tools/cobertura-ratchet.yaml`,
`tools/idioma-ratchet.yaml`, `tools/tests-ratchet.yaml`, `tools/doc-size-ratchet.yaml`,
`docs/trazabilidad-ratchet.yaml`, `tests/poblada/ratchet_instancia.yaml`)
y los hooks de `scripts/hooks/`**. ⚠ El conteo quedó viejo dos veces (tres→cinco→siete, AUD-395):
contalos con `find . -name '*ratchet*.yaml'`, no de memoria.

---

## 3. Fase 1 — Gates deterministas (primero, siempre)

Correr en este orden y **copiar los números crudos** al artefacto. No interpretarlos todavía.

| # | Comando | Qué decide |
|---|---|---|
| 1 | `python -m pytest tests/ -q` | la suite pasa |
| 2 | `python scripts/trace_invariants.py` | invariantes sin marca / sin test / marcas huérfanas, contra `docs/trazabilidad-ratchet.yaml` |
| 3 | `python tools/mutar.py --diff` — a pedido, recomendado al cerrar tanda (cadencia en `docs/desarrollo.md`, AUD-396). Si no corre, **⛔ no evaluado** con motivo, NO 0 | qué funciones sobreviven a la mutación (= tests que no prueban nada), contra `tools/mutacion-ratchet.yaml` |
| 4 | `python -m pytest tests/poblada/test_cobertura.py -m poblada` | funciones que la suite nunca ejecuta, contra `tools/cobertura-ratchet.yaml` |
| 5 | `python -m pytest tests/test_docs_ejecutables.py -q` | la doc nombra tests/scripts/configs que existen |

**Tres reglas al leerlos:**

1. **Un gate que no pudo correr se declara `⛔ no evaluado`, con el motivo, y NO cuenta como 0.** Un
   cero que nadie midió se lee como veredicto — es la regla D-43 aplicada a la auditoría misma.
2. **El criterio es el techo, no el cero.** `sobreviven ≤ techo` pasa. Exigir cero sería rojo
   permanente, y un rojo permanente se deja de mirar.
3. **Un conteo por debajo del techo es un hallazgo**: hay que bajar el techo. Un techo viejo que
   nadie ajusta deja de ser ratchet y se vuelve decorativo.
4. **Antes de leer un techo, mirá sobre qué POBLACIÓN se midió.** Un gate que "sube" puede no ser
   una regresión sino la primera medición honesta de un universo más grande: en la corrida
   2026-08-24 el techo de mutación pasó de 7 a 10 y **ninguna función había empeorado** — el 7 se
   había medido sobre 268 de 328. Dos mediciones de universos distintos no se comparan: se declara
   la discrepancia (regla de método #5) y se fija el alcance para que de ahí en más sólo baje.
   ⛔ No es permiso para subir un techo — la única justificación admisible es que la población
   cambió, dicha explícitamente, con el antes y el después.

Si un gate sale por encima del techo, **eso ya es un hallazgo** (`AUD-nn`, frente `gate`) y va al
artefacto sin pasar por la Fase 2.

---

## 4. Fase 2 — Fan-out por frente

Siete carriles, **un subagente por carril**. Cada uno recibe el alcance de la Fase 0 y **los números
de la Fase 1** (para que no los re-derive).

⚠ **Escalonar, no lanzar los siete de una.** Medido en la corrida 2026-08-24: seis carriles en
paralelo agotaron el límite de sesión y **dos murieron a mitad** (se recuperaron reanudándolos desde
su transcripción, pero eso fue suerte, no diseño). Lanzar en dos tandas —primero A/B/D, después
C/E/F/G— y no arrancar la segunda hasta que la primera devolvió.

| Frente | Pregunta | Dónde mira |
|---|---|---|
| **A · doc↔doc** | ¿dos documentos afirman cosas distintas del mismo hecho? | `CLAUDE.md`, `README.md`, `docs/contrato.md`, `docs/operacion.md`, `docs/ingesta.md`, `tests/README.md`, los 11 `SKILL.md` (`ls .claude/skills/*/SKILL.md \| wc -l`, contalos en la corrida) |
| **B · invariante↔código** | ¿la función marcada `@inv INV-nn` hace lo que el invariante **enuncia**? | `docs/contrato.md` §3 + las marcas de `docs/trazabilidad.md` |
| **C · docstring↔comportamiento** | ¿el docstring promete una garantía que el código no da? | `scripts/*.py` |
| **D · código sin invariante** | ¿qué hace el código que **ningún** invariante exige? | `scripts/*.py` contra `docs/contrato.md` |
| **E · ayuda al día** | ¿`README.md` y la ayuda de CLI reflejan los últimos cambios? | `git log <último tag>..HEAD`, `--help` de cada script |
| **F · tests** | ¿hay tests vacíos, tautológicos, redundantes o que prueban al doble y no al real? | `tests/` + la salida del gate 3 |
| **G · promesa sin implementación** | ¿la doc promete algo que **ningún** código hace? (el inverso de C) | `README.md`, `CLAUDE.md`, `docs/`, los `SKILL.md` → `scripts/` |

**El frente D es el que ningún gate cubre.** `trace_invariants` detecta marcas huérfanas
(marca → invariante inexistente) pero **no la dirección inversa**: una función que nadie exige es
alcance que se coló sin contrato. Es el carril con más señal y el más fácil de saltear.

**El frente F tiene una trampa declarada:** *redundante* no es motivo de borrado. Dos tests del mismo
comportamiento por **caminos distintos** son legítimos. Un test es candidato a borrar sólo si
(a) sobrevive a la mutación de la función que dice probar, o (b) su assert no puede fallar.

**Contrato de salida de cada subagente** — una fila por hallazgo, y **prohibido de memoria**: todo se
lee del archivo.

```
| Frente | Archivo:línea | Enunciado FALSABLE del defecto | Evidencia | Tipo | Por qué es defecto |
```

Sin `archivo:línea` **y** evidencia, el hallazgo **no entra**. Es la misma regla que
`verify-citations` le aplica a la bóveda: una afirmación sin evidencia citable no se propaga.

**La cita del código es el PISO de la evidencia, no el techo.** Si el defecto es de
**comportamiento**, hay que **reproducirlo** —correr la función, mutarla, armar el escenario— y
pegar la salida real. En la corrida 2026-08-24 los carriles C y F lo hicieron por su cuenta y fueron
los que produjeron los hallazgos más fuertes (una pérdida de datos y cuatro tests tautológicos
confirmados por mutación); los que sólo citaron código quedaron un escalón abajo. Escala de
evidencia, de más fuerte a más débil:

1. **reproducido** — se ejecutó y pasó lo que el hallazgo dice (o murió la mutación).
2. **mecánico** — un `grep`/conteo lo decide sin juicio.
3. **citado** — dos textos que no pueden ser ciertos a la vez.

**Tipo** (columna obligatoria, decide qué se hace después):
- **`defecto`** — el código o la doc está mal. Va a Fase 4 (test rojo) si es de código.
- **`hueco de contrato`** — el código hace algo que **ningún invariante exige**. NO admite test
  rojo y **no se "arregla" sola**: se cierra enunciando un invariante nuevo, que es decisión del
  usuario (§7.1 del contrato: entra ahí primero, con ID correlativo). Mezclarlo con `defecto` hace
  que la corrida prometa arreglos que no puede hacer.

**Si un carril recorta** (top-N, muestreo, "no llegué a leer X"), lo **declara**. La regla
*no silent caps* rige para este skill igual que para lo que audita.

⛔ **No generalizar desde una medición.** Si mediste `X` y el hallazgo afirma sobre `X e Y`, medí
también `Y` o acotá el enunciado a `X`. Ocurrió en la corrida 2026-08-24: un carril grepeó
`search_arxiv`, no encontró llamador, y reportó *"ninguna de las dos tiene llamador en producción"*
— `openalex` **sí** lo tenía (`citation_index` lo usa). Un hallazgo mitad cierto es la forma más
cara de estar equivocado: sobrevive a la verificación superficial y manda a arreglar lo que no está
roto. Es el mismo *afirmar de más* que la bóveda persigue en la prosa.

---

## 5. Fase 3 — Verificación

**Primero mecánica, y sólo lo que sobra va a un adversario.** La regla de oro del skill se aplica
también acá: si el hallazgo se decide con un `grep`, un conteo o una ejecución, **decidilo así** —
es más fuerte y más barato que un verificador LLM. Medido: en la corrida 2026-08-24, de 55
hallazgos, ~45 eran decidibles mecánicamente; mandarlos a un subagente cada uno habría sido puro
gasto. Un veredicto mecánico se anota `confirmado (mecánico)` y no necesita nada más.

**Al adversario van sólo los de juicio**: los que dependen de qué *debería* prometer un documento,
de si dos afirmaciones son realmente incompatibles, o de si algo cuenta como omisión. Un subagente
**por hallazgo**, con la consigna invertida: *"intentá REFUTAR esto; ante duda, refutado"*. Lee sólo
los archivos que el hallazgo nombra. Devuelve:

- `confirmado` — reprodujo el defecto y trae su propia cita.
- `refutado` — el hallazgo lee mal el archivo, o el comportamiento es el correcto.
- `no-concluyente` — hace falta correr algo que no puede.

**Sólo los `confirmado` sobreviven al artefacto** como hallazgos; los otros dos se registran con su
veredicto y motivo (no se borran: sin eso, la próxima corrida los vuelve a proponer). Esto existe
porque *"encontrá errores"* a un modelo devuelve **plausibles-pero-falsos** — el mismo modo de falla
que `find-contradictions` maneja con un subagente por par.

---

## 6. Fase 4 — Test rojo primero (sólo hallazgos de código)

Para cada hallazgo `confirmado` cuyo defecto esté en `scripts/` o `tools/`:

1. Escribir el test que **falla como el hallazgo supone**, en el `tests/test_<módulo>.py` que corresponda.
2. **Correrlo y verlo morir — leyendo el MENSAJE del fallo, no el rojo.** Pegar la salida real en
   el artefacto.
3. **Parar ahí.** No arreglar.

⚠ El paso 2 no es ceremonia: *un test verde recién escrito no cuenta hasta que lo viste morir, **por
la razón que prueba*** (regla de método #3). Un test que pasa a la primera puede estar probando otra
cosa — y uno que falla, también: **el fallo por el motivo equivocado se lee igual de tranquilizador
que el bueno**. **Pasó en la corrida 2026-08-24**: el test de un hallazgo real pasó en verde porque
su assert aceptaba una frase que matcheaba OTRO invariante. Y en la tanda #196/#197, un test murió
porque su setup no creaba ninguna nota de paper —universo vacío, no el defecto—: arreglado el setup,
**pasaba sin el fix**. Por eso hay que pegar el mensaje, no el veredicto. Si un test rojo nace verde,
el bug está en el test —apretalo hasta que muera— o el hallazgo es falso; las dos salidas se anotan,
ninguna se ignora.

Los hallazgos de tipo **`hueco de contrato`** no pasan por esta fase: no hay test que escribir
contra una garantía que nadie enunció. Van al artefacto y se discuten con el usuario.

Si el hallazgo es de doc, no hay test: el "rojo" es la cita textual de los dos lados que discrepan.

---

## 7. Fase 5 — El artefacto acumulativo

Todo va a **`docs/internal/auditoria.md`** (gitignored, como el resto de la bitácora interna).
**Acumulativo con IDs estables `AUD-nn`** — sin eso, la segunda corrida re-reporta lo mismo y no hay
con qué diffear.

```markdown
## Corrida AAAA-MM-DD — commit <sha> (<tag>)

Alcance: N scripts · M tests · K skills · <docs>. Fuera del barrido: <…>.
Gates: pytest <r> · trazabilidad <sin marca>/<techo> · mutación <sobreviven>/<techo> ·
cobertura <sin ejecutar>/<techo> · docs-ejecutables <r>. No evaluado: <…>.

| ID | Frente | Archivo:línea | Defecto | Evidencia | Veredicto | Estado |
|---|---|---|---|---|---|---|
| AUD-01 | D | scripts/x.py:120 | … | "…" | confirmado | test-rojo |
```

**Estados:** `abierto` · `test-rojo` (test escrito y falla) · `cerrado` (arreglado y el test pasa —
lo estampa la pasada de fix, no ésta) · `descartado` (**con motivo obligatorio**, mismo criterio que
`triage.py --reason`: no se cura en silencio).

**Dedup contra corridas previas:** antes de asignar IDs nuevos, leer las corridas anteriores del
archivo. Un defecto ya listado **conserva su ID**; lo nuevo es lo que cambia de estado. Cerrar la
corrida con el **diff contra la anterior**: cuántos nuevos, cuántos cerrados, cuántos siguen abiertos.

---

## 8. Reglas duras (las que hacen que esto sirva la segunda vez)

1. **No arregla.** Termina en el hallazgo + su test rojo.
2. **No borra tests.** Propone, con la evidencia de mutación.
3. **No sube techos de ratchet.** Si un conteo quedó por debajo, el hallazgo es *bajar el techo*.
4. **Un gate que no corrió se declara `⛔ no evaluado`**, nunca 0.
5. **Un hallazgo sin `archivo:línea` + cita textual no entra.**
6. **Los IDs son estables entre corridas.** Un hallazgo re-descubierto no estrena ID.
7. **Si al auditar se rompe una promesa declarada** (un techo, una cobertura, un 1:1), se anota
   aunque no se arregle en el momento.

## 8b. Si después se arregla (la pasada de fix)

La auditoría no arregla, pero lo que viene después tiene sus propias trampas, todas medidas en la
primera corrida:

- **Cada fix cierra con la suite entera, no con su test.** Tres arreglos rompieron un test ajeno que
  fijaba el texto viejo de una categoría del lint. Eso es señal, no ruido: el guard hizo su trabajo.
- **Re-verificá el hallazgo antes de arreglarlo**, sobre todo si afirma sobre varias cosas a la vez.
  Si resulta refutado se anota `descartado` con motivo — no se borra.
- **Arreglar destapa vecinos.** Al reescribir un test duplicado apareció que el camino real —el
  fallback al registro versionado— no tenía ningún test. Esos hallazgos estrenan `AUD-nn` como
  cualquier otro.
- **El código del fix también se audita.** Un `main()` nuevo escrito durante la pasada traía
  `parse_args(list(argv) or None)`, que bajo pytest parsea los argumentos del runner; lo cazó su
  propio test al primer intento.
- **Cuando el archivo de tests rojos queda verde, su docstring miente.** Decía *"estos tests FALLAN a
  propósito"*. Actualizalo — es exactamente el drift que este skill persigue.

## 9. Correr de nuevo

Es el caso normal — para eso existe el artefacto. La corrida N+1 repite las Fases 0–5 completas y
**empieza leyendo `docs/internal/auditoria.md`**: los `descartado` con motivo no se re-proponen, los
`abierto`/`test-rojo` se re-chequean (¿sigue vivo el defecto?) y sólo lo genuinamente nuevo estrena
`AUD-nn`. Si dos corridas miden lo mismo y no reconcilian, **se declara la discrepancia** en vez de
elegir un número (regla de método #5).

**Cómo se matchea un hallazgo con su `AUD-nn` viejo.** `archivo:línea` NO sirve de clave: cualquier
edición lo mueve, y arreglar un hallazgo mueve los de abajo. La clave es **`(archivo, enunciado)`**,
donde el enunciado se compara por sentido y no por texto — o sea que **el match es juicio, no
`diff`**. Procedimiento: por cada hallazgo nuevo, buscar en el artefacto los `abierto`/`test-rojo`
del mismo archivo y decidir si es el mismo defecto. Ante duda, **reusar el ID viejo** y anotar la
duda: un ID duplicado infla el conteo y hace parecer que la deuda creció.

⚠ **Decisión abierta** (2026-08-24, sin resolver): si el volumen crece, esto no escala a mano y hay
que darle una clave estable de verdad —un hash del enunciado normalizado, o un ancla como las de
`verify-citations`—. Todavía no se decidió; mientras tanto, el match es manual y se declara.
