# Por qué el vocabulario de veredictos es el que es (y no gradúa)

**Referencia de `verify-citations`.** El `SKILL.md` prescribe el vocabulario cerrado
—`soportada` | `no-soportada` | `contradice`— y el corte de una sola pregunta. Este archivo guarda la
**arqueología**: los dos valores que existieron, por qué se eliminaron y con qué medición. Se lee
cuando alguien propone volver a agregar un grado (pasa: es la tentación natural frente a un par
dudoso), no para verificar.

## Los dos valores eliminados

⚠ **La columna `Score` 0–10 se eliminó en 1.42.0, y es la misma lección que `parcial`.** Un grado
numérico reintroduce por la ventana el eje que 1.39.0 sacó por la puerta: la zona intermedia no se
puede definir porque es de grado, y el umbral (≥7 / <4) nunca se calibró contra nada. **Es además lo
que hace el campo**: los verificadores de referencia etiquetan **binario** (FActScore: *supported* /
*not-supported*) y los que agregan un tercer valor usan un **vocabulario cerrado**, no una escala
(VeriScore: *supported* / *inconclusive* / *contradictory*) — que es exactamente el nuestro. Ningún
sistema comparable gradúa el soporte. La corrida del 2026-08-25 ya devolvió la columna en `—`
porque el fan-out no la había producido: se eliminó en vez de rellenarla con un número que nadie
midió.

⚠ **`parcial` se eliminó en 1.39.0.** Fusionaba dos preguntas ortogonales: «¿la fuente respalda
esto?» (textual, decidible contra el `.txt`) y «¿la afirmación está completa?» (juicio de grado).
Medido el 2026-08-25 sobre una ficha real: **dos corridas independientes de este mismo fan-out**,
jueces nuevos y ciegos, **60 pares comparados → 95 % de coincidencia**, y **las tres divergencias
caían exactamente en el borde `soportada`↔`parcial`**, todas hacia el lado estricto; `contradice`
reprodujo 2/2. El umbral no estaba definido — y no se puede definir, porque es de grado. Todo lo que
era `parcial` se descompone sin pérdida en `soportada` + `condicion`, o en `no-soportada`.

## La regla que sale de las dos

Un eje de **grado** en este bloque siempre reintroduce el mismo problema: el umbral no está definido,
no se puede definir, y las divergencias entre dos jueces independientes caen **exactamente ahí**. Lo
que parece un grado o es una **condición** (→ la columna `Condición`, que es un eje aparte) o es una
cita que no toca el contenido distintivo (→ `no-soportada`). No hay tercer caso.

## Las mediciones detrás de las reglas de `juez.md` (#540)

`juez.md` lo lee cada juez del fan-out, así que lleva la regla y su porqué en presente; lo medido
vive acá.

- **La cita de otro `[[bibcode]]` del mismo bloque** (#316): 12 de 12 hallazgos duros de un hub eran
  esto, y reatribuirlos habría destruido la inferencia declarada.
- **Clasificar la condición** (#221): sobre 96 pares, 86 con condición poblada (89 %) contra 7 % de
  completitud (#198); sin clasificar eran 86 filas de régimen sobre una nota de 413 líneas.
- **Claims multi-cláusula** (2026-08-25): de 14 defectos reales de una ficha, 3 eran un número leído
  en A que A atribuye a B; uno sobrevivió una corrida entera como veredicto tibio.
- **Completitud de transcripciones** (#49): 14 registros transcritos, los 14 correctos, sobre una
  tabla de 21 filas en el paper.
