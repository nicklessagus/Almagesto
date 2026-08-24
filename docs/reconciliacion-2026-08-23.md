# Reconciliación previa al plan de implementación (2026-08-23)

Antes de planificar hay que saber **qué del backlog viejo sobrevive** y **si el contrato sigue
diciendo lo que queremos**. Este documento es el resultado de esos dos análisis. No propone plan:
lo habilita.

Fuentes: `vault/STATUS.md` (cola de 7 + 4 backlogs anotados), `docs/contrato.md` (INV-01…91),
`docs/revision-contrato-2026-08-23.md` (D-1…57).

---

## 1. El backlog viejo contra las 57 decisiones

| # de la cola | Estado | Por qué |
|---|---|---|
| 1 · revisar el contrato | ✅ **hecho** | la revisión del 23-08 |
| 2 · deploy a Almagesto-RV | **sigue, y cambió de forma** | ver §1.1 |
| 3 · documentar los 9 flags | **parcialmente contradicho** | ver §1.2 |
| 4 · `check_retractions` exit 1 sobrecargado | **sigue, y subió de prioridad** | ver §1.3 |
| 5 · `.tmp<pid>` huérfano | **absorbido** por D-53 | el helper atómico único lo resuelve de paso |
| 6 · ground-truth NEA+SIMBAD por campo | **absorbido, con una discrepancia** | ver §1.4 |
| 7 · la bóveda en paralelo | **sigue, y gana sentido** | hay mucho más que comparar que antes |

### 1.1 · El deploy: la migración creció, y eso cambia la salida
Cinco decisiones tocan schema —**D-1** (autoridad de `spectral_type`), **D-2** (`DISPUTE_SOURCES`),
**D-17** (`keywords`), **D-21** (`bearing` fuera del paper), **D-37** (`status` cerrado)— más las que
agregan estructura (**D-10** lista materializada, **D-4/D-20** anclas, **D-19** `versions[]`).

El *Criterio TRANSITORIO* de STATUS dice que durante esta fase **la migración no manda**: si el cambio
es correcto y migrar es caro, **re-ingestar es salida legítima**. Con ocho cambios de forma
acumulados, re-ingestar deja de ser la alternativa cara y pasa a ser **probablemente la barata** —
sobre todo porque D-13 (leer todos los core) haría que la ficha re-ingestada **no se parezca** a la
migrada: la migración conserva una síntesis hecha sobre 8 papers de 155.

**Conclusión para el plan:** el deploy no es "migrar 1.11.0 → 1.23.x". Hay que decidir explícitamente
entre **migrar** y **re-ingestar**, y la evidencia hasta acá apunta a re-ingestar. Es decisión del
usuario y no se toma sin conversarla.

### 1.2 · Los 9 flags: uno se elimina, el resto hay que revisarlo
**D-48** elimina `--no-triage` — o sea que el punto 3 de la cola ("documentar los 9, empezando por
`--no-triage` y `--sync-mirror`") **empieza por uno que ya no va a existir**. `--sync-mirror` sigue
vivo y sin documentar. Los otros 7 no se revisaron en la revisión: hay que listarlos y decidir uno por
uno si se documentan, se registran (D-48) o se eliminan.

### 1.3 · `check_retractions` exit 1: subió de prioridad
Era un defecto menor: el exit 1 vale a la vez "detecté retractados" y "no había nada que chequear", y
`ingest_star.py:66-67` traduce cualquier 1 al primer mensaje. **D-45 lo agrava**: esa misma pasada
pasa a cubrir **cinco** eventos (retracciones, correcciones, versiones nuevas, snapshots web,
ground-truth). Un código de salida ambiguo sobre cinco cosas es peor que sobre dos, y ahora está en el
camino de una feature nueva en vez de ser una molestia aislada. **Se arregla antes de D-45, no después.**

### 1.4 · NEA+SIMBAD: absorbido, pero con una discrepancia real que hay que dirimir
El backlog anotado proponía **`spectral_type` y `dist_pc` → SIMBAD**; la revisión decidió **sólo
`spectral_type` → SIMBAD** (D-1). Nadie discutió `dist_pc` en la sesión: se decidió sobre lo que el
código hace hoy (SIMBAD sólo toca `spectral_type`), no sobre la propuesta del backlog.

`dist_pc` sale hoy de `sy_dist` (NEA). El argumento del backlog —la distancia es dominio de SIMBAD/Gaia,
y NEA la copia— **no se evaluó**. Hay que resolverlo antes de implementar D-1, porque es el mismo
cambio de código.

---

## 2. El contrato contra las 57 decisiones

### 2.1 · Contradicción real: **INV-24 deja de ser cierto**

> **INV-24** — *"El veredicto core/no-core depende sólo de la metadata del paper y de la lente
> vigente."* (P1, garantizado sin medir)

**D-26 lo rompe deliberadamente.** La "puerta 1" de la relevancia de un tema de método es *"lo cita tu
corpus"* — un criterio que depende del **estado de la bóveda**, no de la metadata del paper. El mismo
paper, con la misma lente, es core hoy y no lo era el mes pasado, porque entretanto ingestaste una
estrella que lo cita.

Es un cambio querido —la puerta 1 es la señal más útil que tiene un tema off-ADS— pero **tiene un costo
que hay que declarar**: el veredicto deja de ser reproducible desde el paper. Para reproducirlo hace
falta el corpus **en el estado en que estaba**.

Salidas posibles (decisión del usuario):
- **(a)** Reescribir INV-24 como *"depende de la metadata, la lente vigente y el estado del corpus
  declarado en el registro"* — y entonces el registro tiene que guardar **qué versión del índice de
  citas** se usó, o el veredicto no se puede auditar.
- **(b)** Restringir la puerta 1 a los temas de método y dejar INV-24 intacto para estrellas y temas
  astro — dos reglas de relevancia, más complejidad en el lector.
- **(c)** Que la puerta 1 no decida core sino que **proponga al triage** — el veredicto sigue siendo
  puro y la señal de corpus entra como sugerencia, no como clasificación. *(Es la que menos rompe.)*

### 2.2 · Invariantes que cambian de enunciado o de estado

| Invariante | Qué le pasa |
|---|---|
| **INV-06/07** (espejo vale el GT o `null`) | intacto; ratificado por el usuario |
| **INV-11** (nunca elegir un valor ante conflicto) | intacto; D-2 le da la forma que le faltaba |
| **INV-12** (disputa: `field` + ≥2 posiciones) | **se extiende**: el silencio de la autoridad declarada es posición válida (D-2). Hay que reescribir el enunciado o el lint rechazará disputas legítimas |
| **INV-14** (una autoridad de escritura por campo) | pasa de *"garantizado sin medir"* a **verdad**, con D-1 |
| **INV-24** (core depende sólo de metadata+lente) | **contradicho** por D-26 → §2.1 |
| **INV-35** (todo roll-up dinámico tiene equivalente determinista) | **degradado a red**: D-10/D-11 materializan, así que el equivalente deja de ser el mecanismo y pasa a ser el respaldo. Reescribir, no retirar |
| **INV-38** (un chequeo sin insumo reporta que no evaluó) | **se endurece** con D-43 (reporta **error**, exit ≠ 0). Sube de INCUMPLIDO parcial a exigencia |
| **INV-51** (el registro cierra cada búsqueda) | **se extiende**: una entrada **por corrida**, con nuevos vs ya existentes (D-28) |
| **INV-56** (config malformada aborta) | **cerrado** por D-6 |
| **INV-58** (saber si el corpus usa la lente actual) | **se fortalece**: con D-17 el diff se calcula offline (D-49) |
| **INV-60** (forzado manual con origen marcado) | la mitad *"Falta"* la cierra D-24 |

### 2.3 · Lo que **no** es alcanzable como está enunciado

1. **El renombre de D-19 no puede alcanzar fuera de la bóveda.** Si el usuario citó
   `2026arXiv260529946L` en un paper, una tesis o el repo consumidor, la bóveda **no puede** arreglar
   eso. El invariante tiene que decir explícitamente que el alcance es `vault/`, y el alias en
   `versions[]` es lo que le queda al mundo exterior. Sin esa acotación, es una promesa que no se puede
   cumplir.
2. **D-13 (leer todos los core) es alcanzable pero caro y no acotado.** ≈6M tokens de entrada por
   estrella de ~198 core, lineal. Una bóveda de 20 estrellas son ~120M. No es imposible; es un
   presupuesto que hay que declarar (T-3), y probablemente la razón por la que el subconjunto declarado
   va a ser el caso normal y no la excepción.
3. **El umbral de D-51 no se puede fijar sin medir.** Ya está tratado como medición, no como decisión.

### 2.4 · Tensión con un objetivo de largo plazo
El backlog *"¿esto sirve con cualquier agente, no sólo Claude?"* queda **más lejos** después de esta
revisión: **D-14** (un subagente por paper) y **D-39** (`find-contradictions` al cierre) profundizan la
dependencia del **fan-out de subagentes**, que es justo la primitiva que ese backlog identifica como
no-agnóstica. No es motivo para no hacerlas — es información para cuando se retome ese eje: el costo de
volverse agnóstico subió.

---

## 3. Qué hay que decidir antes del plan

1. **Deploy: ¿migrar o re-ingestar?** (§1.1) — la evidencia apunta a re-ingestar.
2. **`dist_pc`: ¿NEA o SIMBAD?** (§1.4) — quedó sin dirimir entre el backlog y D-1.
3. **INV-24: ¿(a), (b) o (c)?** (§2.1) — la puerta 1 rompe la pureza del veredicto de relevancia.
4. **Los 7 flags restantes** (§1.2) — documentar / registrar / eliminar, uno por uno.

Con esas cuatro cerradas, el plan de implementación se puede escribir: **el orden ya está claro**
(`check_retractions` → ancla D-4/D-20 → índice de citas D-27 → el resto de C → los 24 de B → dashboard).

---

## 4. Las cuatro decisiones, resueltas (2026-08-23)

### 4.1 · Deploy: **bóveda nueva**, ni migrar ni re-ingestar la vieja
Decisión del usuario: se arma una **bóveda nueva** con el framework nuevo y **Almagesto-RV queda al
lado como referencia** para comparar. Consecuencias:

- **Se cae la disyuntiva migrar↔re-ingestar** (§1.1): no hay migración de instancia.
- **Se fusiona con el punto 7 de la cola** ("la bóveda en paralelo para medir calidad"): eran dos
  cosas, ahora es una.
- **Los migradores pierden su único consumidor.** `--migrate-disputes`, `--sync-mirror` y
  `triage --migrate` existen para la instancia que ya está; sin migración, **las rutas de migración de
  D-1, D-2, D-17, D-21 y D-37 no se escriben**: el schema nuevo nace de cero. Menos trabajo.
- **Los detectores de schema viejo se quedan**, y el generador `vintage="1.11.0"` de
  `tests/poblada/` también: existen para probar que el detector funciona, no para migrar. Ya estaba
  así en STATUS.

### 4.2 · `dist_pc` se queda en **NEA**
El backlog proponía SIMBAD. El caso **no es simétrico** con `spectral_type`: el `st_spectype` de NEA
viene **copiado de literatura sin criterio uniforme** (por eso SIMBAD es mejor autoridad ahí), mientras
que `sy_dist` sale de **Gaia**, que es la misma fuente que daría SIMBAD. No se gana nada cambiando de
ventanilla y se suma una autoridad más al espejo. **D-1 queda como está**: `spectral_type` ← SIMBAD,
todo lo demás ← NEA.

### 4.3 · INV-24 queda **intacto**: la puerta 1 propone, no clasifica
La contradicción de §2.1 se disuelve con la salida (c). El modelo queda:

| | Qué es | Reproducible |
|---|---|---|
| **core** | lo que clasifica la lente | **sí** — función pura de (paper, lente) |
| **extra_core** | todo lo que entra por **juicio** | no, y no hace falta: está **declarado** |

Y las tres vías que parecían distintas son **la misma**: el usuario pasa un paper, el triage acepta un
candidato del chaining, o la puerta 1 sugiere uno porque el corpus lo cita. Las tres son juicio, las
tres van a `extra_core`, las tres se ven como `manual` en la columna `Origen` (D-24).

Lo que rompía INV-24 era tratar una **señal de juicio** como si fuera **clasificación**.

**Refinamiento (D-58):** `extra_core` guarda de dónde salió el juicio —
`{bibcode, via: usuario|triage|citado-por-corpus, fecha, motivo}` — en vez del comentario suelto de
hoy. Así la ficha dice no sólo *"es manual"* sino *"entró porque lo citan 12 de tus core"*.

### 4.4 · Los flags: son **7**, no 9, y se parten solos
`--no-triage` y `--sync-mirror` ya se documentaron en la 8ª pasada. Los que quedan:

| Flag | Script | Qué se hace |
|---|---|---|
| `--json`, `--listar`, `--por-slug` | `measure_layout.py` | **nada**: herramienta de medición del framework, no de la cadena |
| `--limit` | `fetch_pdf`, `fetch_arxiv` | **documentar** — cae con D-13/D-14 |
| `--paper` | `check_retractions` | **documentar** — cae con D-45 |
| `--pending`, `--accessed` | `make_notes` | **documentar** — modo off-ADS, cae con D-41 |

No son trabajo aparte: los cuatro se documentan **al tocar la feature en la que caen**.
**`--no-triage` se elimina** (D-48) y su documentación se borra.

---

## 5. Vía libre para el plan
Las cuatro decisiones previas están cerradas. El orden ya está determinado por las dependencias:

**`check_retractions` exit 1** (§1.3, bloquea a D-45) → **ancla D-4/D-20** (habilita D-31, D-41, D-45,
D-79…) → **índice de citas D-27** (habilita D-26) → resto de **C** → los 24 de **B** → **dashboard**.

Método obligatorio: **TDD rojo-primero** (`STATUS.md` §Protocolo de fixes), con el cuidado de que el
rojo sea **de comportamiento** y no un `ImportError` — el repo ya se comió ese falso rojo 7 veces.
