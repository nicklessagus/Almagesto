# Estado de la bóveda

Punto de entrada: dónde está el proyecto y qué sigue. Vive en el repo (sincroniza entre máquinas).
Para *cómo* operar ver `CLAUDE.md`; para el historial ver `vault/wiki/log.md`; catálogo en `vault/wiki/index.md`.

## Estado actual

- Bóveda **recién instanciada** desde el template **Almagesto** (patrón LLM Wiki).
- **Objetivo:** ver `vault/config/objective.yaml` ← **editar este archivo primero** (define de qué trata la
  bóveda y qué papers son "core").
- Sin estrellas/temas ingestados todavía.

## Próximos pasos

1. Definir el objetivo con el skill `setup` (se lo pedís al agente en palabras; genera/afina
   `vault/config/objective.yaml` con su `relevance.topics` — editable a mano si preferís).
2. Poner el token ADS en `vault/config/ads_dev_key` (o `ADS_DEV_KEY`).
3. Agregar tu primera estrella a `vault/config/stars.yaml` (o tema a `vault/config/topics.yaml`) y correr
   `ingest-star` / `ingest-topic`.

## ✅ Framework 1.23.0 (2026-08-23) — séptima pasada: el código que ninguna auditoría había mirado

> **La tesis, verificada antes de empezar:** las seis pasadas previas apuntaron **todas al diff del
> 22-08. Ocho scripts —1.754 líneas— eran byte-idénticos a `v1.11.0`** (`git diff v1.11.0..HEAD`
> sobre ellos: cero archivos) y **ningún instrumento los había tocado**. El alcance de esta pasada no
> es un diff: es el código acumulado. Minor porque el fix de `lint.py:805` hace que un `planets: 0`
> del ground-truth pase a **reportarse**, así que una bóveda existente puede cambiar de veredicto.

**Nota de método que vale más que varios hallazgos:** ninguna de las 21 hipótesis confirmadas
necesitó una línea sin cubrir. Esos scripts están en **83–99% de cobertura** y **todo pasa por
líneas que los tests ejecutan**. Es la lección de la 3ª —la cobertura no es assertion— reconfirmada
sobre un corpus nuevo. (Lo que **no** está demostrado, y conviene no sobrevender: que los tests
fijen el statu quo en vez del contrato. Eso lo decide una pasada de mutación sobre esos 122 tests,
que no se corrió.)

### Pérdida y corrupción silenciosa de lo que el código dice preservar
- **`check_retractions.stamp_fields` destruía la extracción LLM.** Reescribía notas de
  `wiki/papers/` sin tmp+rename. Medido con `ulimit -f`: 16.071 B → **8.192 B**, 198 de 400
  ocurrencias perdidas — sobre lo MENOS regenerable de la bóveda. Es la misma clase que la 6ª
  arregló en `save_registro`; el barrido nunca se había hecho. **14 writers, cero atómicos.**
- **El drop de la clave vieja corrompía el frontmatter en silencio**: con una línea en blanco el
  YAML parsea igual y el ítem huérfano se absorbe en la clave anterior
  (`tags: ['paper', {...}]`) — y **ninguna categoría del lint lo veía**.
- **`fetch_ground_truth --force`** pisaba el snapshot de NEA sin atomicidad: 162 B → 1.024 B de JSON
  inválido, irrecuperable, sobre un archivo que su propio docstring dice que no es regenerable.

### Un `---` en el frontmatter bloqueaba notas válidas (el más urgente, y fuera de los ocho)
`split_fm` y `fm_error` delimitaban el frontmatter buscando la **subcadena** `---`, así que un guion
triple dentro de un escalar entrecomillado cortaba a la mitad del valor: el lint reportaba **"YAML
inválido"** —categoría **bloqueante**— sobre YAML **válido**, mandando a arreglar lo que no estaba
roto. La misma clase en `check_retractions.split_note` **salteaba el paper** del chequeo de
retracciones: falso limpio en la frontera dura. Ahora hay `lib_config.frontmatter_span`, que delimita
por **líneas** que son sólo `---`.

### Compuertas y filtros que mentían en vez de fallar
- **El filtro de ruido, apagado por un escalar.** `noise_doctypes: erratum` ⇒ `set('erratum')` =
  `{'t','u','a','e','m','r'}`: ningún doctype real matchea y un erratum entra como core.
- **La curación manual, evaporada.** `extra_core: 1988old.....1O` ⇒ a ADS se le piden catorce
  caracteres sueltos y **el bibcode nunca se pide**. Es el único lugar donde sobrevive una
  *aceptación* del triage.
- **Una fecha fabricada en la capa auditable:** `date-parts: "2021"` ⇒ `retraction.date = "2"`.
- **El barrido de retracciones cerraba en verde sin haber consultado nada**, y un solo registro raro
  de Crossref lo mataba entero (sin `try/except` por paper).
- **`measure_layout` publicaba `0 / 0 (0%)` sobre 5 archivos reales** — el "(0) que significa no
  miré" — y prometía *"Exit 0 siempre"* mientras salía con 1. Era el **único script sin un solo
  test**: pasó de 0 a 11.
- **11 CLIs salían con exit 1 en consola no-UTF8.** El fix de la 6ª vivía sólo en `lint.py`. Ahora
  `print_seguro` cubre los `print` propios y `stdout_tolerante()` —llamado desde cada `main()`, no al
  importar, para no romper `capsys`— cubre lo que **argparse** escribe directo a stdout.
- **`fetch_pdf --limit` borraba el residuo de `fetch_arxiv`**, y un PDF truncado quedaba congelado
  para siempre (ninguno validaba magic ni tamaño en disco, ninguno tenía `--force`).
- **`is_ads_host('https://xadsabs.harvard.edu/x')` daba `True`** — el `endswith` aceptaba hosts que
  no son subdominios, contra la promesa de que el token no sale de `*.adsabs.harvard.edu`.

### El hallazgo transversal: la clase NO viaja uniformemente
Era la hipótesis de partida —"si el defecto es de clase, hay que barrer los 46 sitios"— y la
clasificación la **corrigió**: **19 garantizados · 8 inalcanzables · 19 alcanzables**. `lint.py` está
**11 de 12 garantizado** porque tiene `normalize_lists` antes de todo lector; `check_retractions`
está **0 de 6** porque no tiene nada. La clase se concentra donde falta ese saneo, no se esparce
parejo — migrar los 12 de `lint.py` habría sido casi todo ruido. Y hay **dos sitios donde migrar
mecánicamente empeora**: en `make_notes.py:333` el `or []` es correcto y `as_list` apagaría un aviso;
en `lint.py:805` el fix era **borrar** el `or []`, no migrarlo.

### Dos lecciones de método, para la próxima
- **Un test puede empujar a la implementación equivocada.** El rojo de la escritura atómica inyectaba
  el fallo **sólo en la ruta destino**, así que con tmp+rename no disparaba: premiaba escribir
  directo y "restaurar" desde un backup — que **no sobrevive a un `SIGKILL`**, porque ahí no corre
  ningún `except`. Un test que fija el **mecanismo** en vez del **contrato** conduce el diseño a
  donde no querés.
- **Lo que salió limpio, medido:** `bench_verify` cumple sus cuatro garantías (determinismo byte a
  byte, `vault/` intacto, "nunca el original", sin `ZeroDivisionError`); idempotencia confirmada por
  corrida en cinco scripts; y la higiene del token verificada extremo a extremo con una cadena real
  de redirects ADS→doi.org→publisher usando el `should_strip_auth` de `requests`.

## ✅ Framework 1.23.1 (2026-08-23) — octava pasada: la documentación como oráculo

> **El instrumento:** el oráculo deja de ser el código y pasa a ser la **documentación**. La pregunta
> no es "¿esto tiene bugs?" sino **"¿el sistema hace lo que la doc dice que hace?"**. Cada *siempre /
> nunca / idempotente / atómico / bloquea / avisa sin frenar* se extrajo como afirmación falsable y
> se **midió ejecutando**. La 1ª pasada leyó doc contra código; ésta la ejecuta, sobre el sistema
> entero, y cubre superficies que ninguna había tocado: los **9 skills**, `docs/`, `README.md` y el
> **libro mayor de este mismo archivo**.

**Lo medido:** 139 líneas-garantía → 46 afirmaciones falsables → **41 ejecutadas** (34 confirmadas,
5 refutadas, 2 parciales); 30 garantías dinámicas a escala; las 30 categorías del lint sembradas
**una por una**; los 9 skills con sus 45 invocaciones; el ledger de versiones por worktree.

### Lo que salió bien, y es la mayor parte
Las garantías caras se sostienen **ejecutadas, no leídas**: el espejo #70 bloquea campo por campo; el
ciclo de upgrade completo (vintage 1.11.0 → migradores → el **conteo** del lint a 0 → 2ª pasada byte
a byte idéntica); `save_registro` no pisa un registro roto; los **45 comandos** que nombran los
skills existen y parsean, y **todas** las referencias cruzadas entre pasos resuelven —cero punteros
podridos, a diferencia de pasadas anteriores—; las **30 categorías** mapean 1:1 contra `CLAUDE.md`
con la severidad correcta; y los **siete números** que la doc usa como justificación siguen ciertos
(*22 de 25 cabeceras* da hoy exactamente 22/25; *73% multi-columna* pasó de 472/644 a 489/672).

### Lo refutado
- **`lint.py --help` corría el lint entero** y pisaba `outputs/lint-<fecha>.md`: era el único CLI
  **sin argparse**, así que cualquier flag se ignoraba en silencio y salía 0. Un CLI que acepta lo
  que no entiende y actúa igual es la misma familia que todo lo demás de esta auditoría. Ahora
  `--help` documenta y sale 0, un flag inexistente sale **2 sin correr nada**.
- **El presupuesto del tier 0 estaba vencido al doble** (5,0 s contra ≤2,5 s documentado). Causa: un
  solo test sin el fixture `no_sleep` dormía **3 s reales** por cortesía con arXiv, violando el
  principio 1 del propio `tests/README.md`. Vuelto a **2,03 s**. El presupuesto tenía razón; el que
  estaba mal era el test.
- **Off-by-one en la frontera de la guardia de expansión.** El código frena con **exactamente 50**
  papers nuevos (dirimido sembrando 49/50/51, no discutiendo la redacción). `docs/operacion.md`
  decía bien "50 o más"; el header de `ingest_star.py` —que **se autodeclara "la definición canónica
  de la cadena"**— decía `>50`, y los tres skills copiaron esa versión. **La fuente que se proclama
  canónica era la equivocada y ganó por repetición.** Corregidos los cinco.
- **`CLAUDE.md` decía "siete" campos incompletos y el lint tiene ocho** — faltaba el hermano
  simétrico (ground-truth sin ficha) que agregó la propia tanda anterior.
- **`check_retractions` sobrecarga el exit 1**: vale "detecté retractados" y "no había nada que
  chequear", y `ingest_star.py` traduce cualquier 1 al primer mensaje. **Pendiente.**

### El libro mayor: el mismo error por TERCERA vez
La entrada 1.22.1 declaraba **+21 tests**; el delta real es **+30**, medido node-id por node-id con
`comm`. Ya había pasado en 1.9.0 (+6 vs +9) y en 1.12.0 (+13 vs +15). Y decía *"Siete"* defectos
enumerando seis. Tres veces deja de ser distracción: **los deltas se miden, no se recuerdan.**

### Nueve flags operativos sin documentar
El más delicado no es el que se esperaba: **`--no-triage`** apaga en silencio la compuerta de triage
del chaining, que los propios skills describen como el paso de más juicio del ingest. Le siguen
**`--sync-mirror`** (implementado el 23-08, cierra el drift del espejo, y ni la doc lo nombra ni el
lint tiene categoría que reclame cuándo correrlo), `--pending` y `--limit`.

### Nace `docs/contrato.md`
Los invariantes vivían **dentro de los docstrings**, que son a la vez la especificación y el
comentario de la implementación, escritos por la misma mano: nada los contrastaba. Por eso la 7ª
encontró docstrings afirmando garantías falsas. Ahora hay un contrato **separado del código**,
construido cruzando dos documentos independientes: lo que el sistema **hace** (medido) contra lo que
**debería garantizar** — esto último derivado sólo del propósito por un agente **ciego**, que no vio
`scripts/`, `tests/`, `STATUS.md` ni los informes. De ese cruce salen los **huecos**: garantías que
deberían existir y que nadie sabía que faltaban.

## ✅ Revisión del contrato con el usuario (2026-08-23) — cierra el punto 1 de la cola

> **Las 22 decisiones de intención de `docs/contrato.md` §6 quedaron resueltas.** La revisión no fue
> ítem por ítem: se recorrió el sistema **de punta a punta con el usuario** (setup → búsqueda → triage →
> extracción → contraste → síntesis → verificación → cierre; estrellas, conceptos/métodos, temas
> off-ADS, hipótesis, contradicciones). De ahí salieron **57 decisiones** — las 22 previstas más **35
> que el auditor no había visto**, porque sólo aparecen al recorrer el flujo como usuario.

**Dónde quedó todo:** `docs/revision-contrato-2026-08-23.md` (razones, mediciones y clasificación por
esfuerzo). `docs/contrato.md` §6 marca las 22 con su resolución; los invariantes nuevos entraron como
**§3.K, INV-76…91**, todos en estado HUECO (decisión tomada, mecanismo por escribir).

### Lo que se midió sobre la instancia real durante la revisión
Ninguno de estos números existía antes; todos salieron de mirar Almagesto-RV mientras se discutía:
- **155 papers en el roll-up de `tau_ceti`, 8 citados en la prosa.** De los 147 restantes: 67
  `relevance: low`, **42 `high` sin extraer**, **38 `high` extraídos y no sintetizados**. La ficha se
  lee como si sintetizara 155.
- **2 trabajos con dos notas cada uno** (mismo `arxiv_id`, dos bibcodes: preprint y publicado), sobre 29
  notas con bibcode arXiv. La dedup por bibcode no ve el par.
- **30 bibcodes con `.txt` bajo más de un slug**, 33 copias extra en disco (se re-baja el PDF).
- **Los 18 conceptos usan tres llaves distintas** para el mismo roll-up (`thesis_links` 12,
  `methods` 4, las dos con `OR` 4). Nadie lo decidió: lo improvisó el LLM al crear cada nota.
- **376 papers con `thesis_links`, 67 con más de uno** y un `bearing` escalar para todos.
- **Costo del ingest:** 672 fulltexts, mediana 92 KB ≈ 24k tokens → una estrella de ~198 core sale
  ≈ **6M tokens de entrada**, lineal. La lente pasa a ser **presupuesto**, no sólo filtro.
- **Dos fugas de implementación vivas** que el WARN no detecta porque busca perillas, no punteros
  downstream: *"lo leen los scripts de ICA"* (`tau_ceti`) y *"supuesto de trabajo del pipeline ICA por
  canal"* (`achromaticity`).

### Las decisiones que más cambian el sistema
1. **El ancla (D-4/D-20)** — cada par verificado guarda dos hashes: el del bloque markdown que lleva la
   cita y el del `.txt` leído. Convierte "re-verificar" de todo-o-nada por archivo a **por par**, y con
   el segundo hash cubre de una sola forma el preprint que se publica, el `v1→v3` y el snapshot web que
   cambió. **Es la pieza de la que cuelga casi todo lo demás.**
2. **La ficha declara su universo (D-10/D-13)** — lista materializada, paper por paper, con origen
   (`lente`/`manual`), si se extrajo y si se sintetizó. El default pasa a ser **leer todos los core**; lo
   que no se lea, declarado.
3. **Identidad por `doi`/`arxiv_id` (D-19)** — una nota canónica por trabajo, versiones en `versions[]`,
   renombre con reescritura de wikilinks.
4. **Descubrimiento fuera de ADS (D-25/26/27)** — arXiv + OpenAlex como backends, relevancia **propia del
   tema** con tres puertas, y un **índice de citas local** que habilita la mejor de ellas: *"lo cita tu
   corpus"*. Sin esto, los métodos de otras disciplinas dependen de que el usuario ya sepa la respuesta.
5. **`inferencia` nombra sus premisas (D-42)** — cierra el sumidero por donde una afirmación
   `no-soportada` sobrevivía cambiándole la etiqueta.
6. **`bearing` sale del paper (D-21)** — la postura frente a una tesis es una **afirmación**, no un
   puntero: va a la tabla de evidencia de la hipótesis, con cita y verificada.
7. **La bóveda es read-only desde afuera (D-50)** — ataca el vector de la contaminación downstream, no
   el síntoma. Hoy no está escrito en ningún lado.

### Tamaño del trabajo (57 decisiones)
| | | |
|---|---|---|
| **A** · ya funciona, sólo documentar | 7 | |
| **B** · cambio chico (campo, categoría de lint, ajuste de skill) | 24 | el grueso |
| **C** · feature nueva | 11 | **el camino crítico** |

Dentro de C, dos piezas habilitan al resto: **el ancla (D-4/D-20)** y **el índice de citas (D-27)**. El
**dashboard** (T-4) muestra el estado que todo lo anterior produce, así que va último.

### Temas anotados para después
**T-1** cómo se linkea la bóveda consigo misma al crecer · **T-2** frontmatter de papers (cubierto en la
revisión) · **T-3** el setup tiene que mostrar el **costo** de la lente, no sólo su ruido · **T-4**
dashboard de Obsidian con el estado de la bóveda.

### Efecto sobre el deploy
Varias decisiones cambian el schema (D-1, D-2, D-17, D-21, D-37), y **cada una suma una migración**.
Sigue valiendo el criterio: **el deploy a Almagesto-RV se hace cuando cierren los issues, no antes.**

## 📌 Dónde retomar (sesión del 2026-08-23)

**Lo hecho hoy, en tres documentos** (los tres commiteados **sin push** — ver la advertencia de abajo):

| Documento | Qué es |
|---|---|
| `docs/revision-contrato-2026-08-23.md` | las **58 decisiones** (D-1…D-58) con razones y mediciones sobre la instancia real |
| `docs/reconciliacion-2026-08-23.md` | qué del backlog viejo sobrevive, qué invariantes cambian, y las **4 decisiones previas** resueltas |
| `docs/plan-implementacion-2026-08-23.md` | el **plan en 11 tandas**, con funciones, firmas, tests rojos y el INV que cierra cada issue |

Más `docs/contrato.md` §6 (**RESUELTA**, con el mapeo #→D) y §3.K (**INV-76…91**, todos en HUECO).

**El plan lo escribió Fable** validando el orden contra el código, y **corrigió cuatro cosas** del
esqueleto propuesto: D-53 (helper atómico) sube al principio porque cada tanda posterior agrega
writers; el registro (D-28/D-57) va **antes** del bloque de estado D-12 porque `search_line()` lee
`busqueda` y D-28 le cambia el schema; D-1/D-2 van antes de la pasada de red porque `nea_diff` diffea
el mismo JSON que D-1 re-organiza; y el índice de citas D-27 no bloquea a nada fuera de su carril.

### ⚠ Sin push — decidir antes si esto va público
El repo `Almagesto` es **público** (`github.com/nicklessagus/Almagesto`). Los commits de hoy están
**locales**: `0f0dcef` (revisión) y `c922263` (reconciliación), más el del plan. **No pushear sin que
el usuario decida** si los tres documentos —que citan números, rutas y decisiones de su instancia
privada Almagesto-RV— van al repo público, a un repo privado, o quedan fuera de git.

### Requisito nuevo: trazabilidad requisito ↔ código
Pedido del usuario al cerrar: **va a querer una matriz que ate cada invariante / requisito a la
función que lo implementa.** Hoy no existe: `docs/contrato.md` nombra archivos y líneas sueltas en la
columna "cómo se verifica", pero no hay un mapa. Era el paso 3 del análisis previo al plan y se
saltó; vuelve como **requisito del plan**, no como opcional.

Implica: cada issue del plan declara **qué invariante cierra** (eso el plan ya lo trae) **y** deja la
relación registrada en un artefacto consultable —matriz en `docs/`, o marcas en el código que un
script recolecte—. Decidir la forma antes de arrancar la Tanda 0, porque si se agrega después hay que
reconstruirla de memoria, que es exactamente el modo de falla que este repo ya registró tres veces.

### ✅ Decidido el 2026-08-24 (sesión siguiente)

| Punto | Decisión |
|---|---|
| **Forma de la trazabilidad** | **marcas en el código + recolector**. Cada función que implementa un invariante lleva la marca `INV-nn` y cada test declara el INV que cubre; `scripts/trace_invariants.py` recolecta y genera `docs/trazabilidad.md`, y **falla** si un INV de `contrato.md` §3.K no tiene implementación NI test. El mapa se regenera, no se edita a mano — el modo de falla de la matriz manual (desincronizarse en silencio) es justo el que este repo ya registró tres veces. |
| **Push de los tres documentos** | **no pushear todavía**. Los commits siguen locales; se trabaja y se commitea local hasta que el usuario decida si van al repo público, a uno privado, o fuera de git. |
| **R-1 · las dos severidades de D-4** | **`lint.py --cierre`**. Sin el flag, los pares vencidos reportan como backlog (exit 0 — la pasada periódica); con el flag cuentan para el exit ≠ 0. Los skills de cierre lo invocan con el flag. La distinción vive en **un** punto testeable, no en prosa de skill. D-44 intacto: el commit nunca se frena. |

**Siguen abiertos** R-2…R-11 (§14 del plan); los que bloquean antes son **R-5** (colisión de nombres
`topics`, antes del issue 7.3) y **R-6** (quién estampa `cadena`, en el issue 2.2).

### ✅ Issue 0.0 — el recolector de trazabilidad (2026-08-24)

`scripts/trace_invariants.py` + `tests/test_trace_invariants.py` (16 tests) +
`docs/trazabilidad-ratchet.yaml`. Genera `docs/trazabilidad.md`, el mapa consultable que el usuario
pidió al cerrar la sesión anterior.

**La marca:** `@inv INV-nn` (varios separados por coma) en un **comentario** o **docstring**, en
`scripts/` (implementación) o `tests/` (prueba). Se asocia al `def`/`class` más cercano hacia
arriba, así el mapa nombra el símbolo y no sólo el archivo.

**Las tres puertas:** `0` limpio · `1` bloqueante (marca **huérfana** —apunta a un `INV-nn` que el
contrato no declara, mismo modo de falla que un `thesis_links` sin destino—, techo del ratchet
superado, o `--check` con el artefacto commiteado viejo) · `2` **no evaluado** (el contrato no se
pudo leer → no se reporta "0 sin marcar": el cero inventado que D-43 prohíbe).

**Dos bugs reales encontrados en la primera corrida**, los dos de la misma familia —afirmar
cobertura que nadie escribió— y los dos ahora con test:
1. Marcas dentro de **string literals** (el código de juguete que los tests escriben a disco) se
   recolectaban: 7 "pruebas" de INV-01 que no lo tocan. Fix: `lineas_declarativas()` (tokenize para
   comentarios + AST para docstrings) restringe dónde cuenta una marca.
2. Los **ejemplos de sintaxis** de la propia doc se auto-marcaban (el recolector se adjudicaba
   INV-87 e INV-90). Convención: en docs y docstrings la sintaxis se escribe con placeholders
   `nn`/`mm`, nunca con un id real.

**Ratchet arrancado en 91/91** (`sin_marca` y `sin_test`), medido, sólo puede bajar. ⚠ Ese número
**no** significa que el sistema no esté probado: buena parte de los 91 ya están *garantizado y
medido* en el contrato, pero la relación vive en prosa (la columna "cómo se verifica" nombra los
experimentos de la 8ª auditoría, no símbolos ni tests). **La pasada retroactiva de marcado es
trabajo aparte y no se hizo** — cada tanda del plan baja el techo con lo que cierra.

Suite tier 0: **667 verdes en 2,4 s** (presupuesto ≤ 2,5 s).

### Lo que sigue
**Tanda 0** — issues 0.1 (`check_retractions` exit 0/1/2), 0.2 (helper atómico `write_text_atomic`),
0.3 ("no evaluado" + lente vacía), 0.4 (medición del umbral de legibilidad sobre los 672 fulltexts
reales). Cada uno declara su `@inv` y baja el techo del ratchet.

## 🔜 Cola de pendientes (al 2026-08-23)

> Explícita para que no dependa de la memoria de una sesión.

1. ~~**Revisar `docs/contrato.md` con el usuario**~~ — ✅ **hecho el 2026-08-23** (ver arriba). Lo que
   queda de ahí: **implementar las 57 decisiones**, empezando por el ancla (D-4/D-20) y el índice de
   citas (D-27). Y una **medición** pendiente que no es decisión: el umbral de legibilidad del fulltext
   (D-51), a sacar corriendo el detector sobre los 672 fulltexts reales.
2. **Deploy a la instancia real** (Almagesto-RV, 1.11.0 → 1.23.x). Ensayado completo sobre copia:
   16 bloqueantes → 1, y ese 1 (el `P_rot` de literatura de hd40307) ya tiene resolución escrita.
   **Se hace cuando cierren los issues**, no antes: cada cambio de schema le agrega una migración.
3. **Documentar los 9 flags**, empezando por `--no-triage` y `--sync-mirror`.
4. **`check_retractions` exit 1 sobrecargado** (refutado en la 8ª, sin arreglar).
5. **`.tmp<pid>` huérfano** en `save_registro`/`write_ground_truth` si el fallo ocurre mientras se
   escribe el temporal (S3 de F4: el archivo real nunca se corrompe, es basura de disco).
6. **Ground-truth NEA+SIMBAD con autoridad por campo** (backlog anotado).
7. **La bóveda en paralelo** para medir calidad — espera a que esté todo implementado.

## Criterio de auditoría — una pasada, un instrumento (2026-08-22)

> Sale de las tres auditorías seguidas de las tandas 1-4. Cada una encontró una **clase distinta**
> de error, y no por leer con más cuidado sino por **cambiar de instrumento**.

| Pasada | Instrumento | Qué encontró |
|---|---|---|
| 1ª (1.20.1) | leer la doc contra el código | doc que contradecía al código (el orden síntesis↔contraste en `CLAUDE.md`, listas de bloqueantes viejas) |
| 2ª (1.20.2) | **medir**: worktree por commit, greps de referencias cruzadas | números escritos de memoria (un delta de tests inventado), punteros podridos (`archivo.py:NN`) |
| 3ª (1.20.3) | **diff de código completo + cobertura AST + mutación** | defectos de código (un detector con agujero, una heurística ciega a la notación del propio schema, una rama inalcanzable) |
| 4ª (1.20.4) | **mutación sobre las FEATURES + corrida real de la cadena + mirar los assets** | tests que pasaban por el motivo equivocado, contratos de schema sin test, features no propagadas a los skills, una captura que ya no es el schema |
| 5ª (1.21.0) | **invariantes cross-artefacto medidos + recorrer la cadena de punta a punta** | agujeros de lógica (el espejo comparaba `len(planets)`), un crash del lint, chequeos hermanos asimétricos, el hand-off de los orquestadores sin el paso nuevo |
| 8ª (1.23.1) | **la documentación como oráculo ejecutable** (todo el sistema, no un diff) + libro mayor por worktree | un CLI sin argparse que corría el lint con `--help`, el presupuesto del tier 0 vencido al doble por un test sin `no_sleep`, un off-by-one donde la fuente "canónica" era la equivocada, y el mismo delta mal medido por tercera vez |
| 7ª (1.23.0) | **el código que ninguna pasada había mirado** (8 scripts congelados desde v1.11.0) + barrido del defecto de clase | pérdida de datos en el writer de notas, un `---` que bloqueaba notas válidas, filtros que mentían en vez de fallar, el único script sin tests |
| 6ª (1.22.0) | **diferencial HEAD↔working tree + fuzzing por propiedades + contratos de datos + las afirmaciones del diff ejecutadas + idempotencia/atomicidad + cobertura por mensaje y por flag** | dos pérdidas silenciosas de datos versionados, seis crashes de la compuerta de CI, tres falsos limpios, un test que rompía CI en un clone limpio, garantías afirmadas que no existían |

**Regla:** releer más despacio no encuentra nada nuevo. Si una pasada tiene que agregar valor sobre
la anterior, tiene que **cambiar de instrumento**, y conviene planificarla así desde el principio:
(1) doc↔código, (2) medir lo declarado, (3) leer el diff entero y medir cobertura, (4) atacar los
tests y correr la cosa de verdad, (5) medir invariantes cross-artefacto, (6) **generar entradas en
vez de elegirlas** (fuzzing) y **ejecutar lo que la doc afirma** en vez de leerlo.
La 6ª agregó un corolario propio: **la clase de defecto viaja más lejos que el sitio**. Su tanda
previa diagnosticó bien (`X.get(k) or {}` sobre forma no garantizada) y arregló **cuatro sitios**;
el fuzz mostró los cuatro verdes y el mismo idioma vivo en **59 líneas** más. Cuando una pasada
identifica un defecto de clase, lo que sigue no es el guard: es el **barrido** (helper único +
fuzz permanente).
El instrumento que **todavía falta** —y que estas seis no pueden dar— es correr sobre un **corpus
poblado**: tres hallazgos de la 6ª salieron de ahí (el deadlock de #69 con 22 de 25 notas reales) y
ninguna pasada sobre bóveda vacía podía verlos, porque en vacío toda categoría da `(0)` y el test no
distingue "pasa" de "ni miró". Corolarios: un fix **cuyo test nunca se vio fallar** no está
verificado, está supuesto (ver el protocolo de abajo) — y la **cobertura no es assertion**: la 3ª
midió 100% de sentencias nuevas ejecutadas y la 4ª encontró siete mutantes vivos justo ahí. Un test
verde no dice por qué está verde.

## Protocolo de fixes — test rojo primero (2026-08-23)

**Regla dura: ningún fix entra sin que su test se haya visto FALLAR contra el código con el
defecto vivo.** Un test que nunca estuvo rojo no es evidencia de nada: no distingue la presencia de
la ausencia del fix. El orden es **test → rojo → fix → verde**, en ese orden y verificando el rojo,
no al revés.

Esto **reemplaza** a la mutación post-hoc (arreglar, revertir el fix, ver que el test falla,
restaurar) como camino por defecto. Las dos prueban lo mismo; el rojo-primero es mejor por tres
motivos medidos en la auditoría del 2026-08-23:

1. **La mutación post-hoc mide una reconstrucción, no el bug.** Al revertir "el fix" estás
   adivinando cómo era el código sin él. Medido: de los tests de la 6ª pasada, **7 fallaban contra
   el código viejo sólo por símbolo ausente** (`ImportError` de una función que todavía no
   existía) — lo que **no** prueba que el test ejercite el comportamiento. Hubo que escribir
   mutantes dirigidos para saberlo. El rojo-primero corre contra el defecto real.
2. **Cuesta una corrida en vez de tres**, y no se puede saltear en silencio: la mutación post-hoc
   es un paso separado que se olvida, y este repo ya registró que se olvidaba.
3. **Caza el verde-falso antes de que se fosilice.** Escribiendo los tests rojos de esta tanda, uno
   pasó en verde desde el principio y sólo se notó porque *se esperaba rojo*: asertaba un substring
   contra **stdout**, y el lint imprime al final la ruta del reporte, que vive bajo el tmpdir de
   pytest —cuyo nombre es el del test—. Con mutación post-hoc ese test habría entrado a la suite
   como cobertura falsa. Corolario operativo: **los asserts de contenido del lint van contra el
   archivo de reporte, nunca contra stdout.**

**La mutación sigue siendo obligatoria en un caso**, porque el rojo-primero no puede cubrirlo: para
**auditar tests que ya existen** (no hay un "antes"), que es justo lo que hacen las pasadas de
auditoría. Ahí sí: revertir la línea del fix y verificar que su test cae.

⚠ **Al mutar hay que borrar `__pycache__` y correr `python -B`.** Una mutación que conserva el
tamaño del archivo dentro del mismo segundo revalida el `.pyc` y da un falso *"ningún test muere"* —
pasó en la primera tanda de mutación de esta auditoría.

**Forma de trabajo cuando la tanda es grande** (probada en esta auditoría, 12 hallazgos):
escribir **todos** los tests rojos primero en un archivo `tests/test_zz_fix_*.py` con un test por
defecto y el *por qué* en el docstring; verificar que **todos** fallan; recién ahí repartir los
fixes **por archivo dueño** (un ejecutor por script, sin solapamiento, y **prohibido tocar
`tests/`**: los tests son el criterio de aceptación, no material del ejecutor); al cerrar, migrar
los casos a los archivos de test definitivos y borrar el temporal.

## ✅ Framework 1.22.1 (2026-08-23) — los S3 de la sexta pasada: siete defectos menores y la cobertura que faltaba

> Segunda tanda de la auditoría del 23-08. **592 tests verdes** (**+30** sobre 1.22.0 — la
> entrada decía +21; el delta real, medido node-id por node-id con `comm` en la 8ª pasada,
> es 30 nuevos y 0 borrados. Tercera vez que un delta escrito de memoria sale mal en este
> repo: pasó en 1.9.0 (+6 vs +9) y en 1.12.0 (+13 vs +15). **Medirlo, no recordarlo**), lint 0. Patch:
> todos los hallazgos nuevos del lint son **backlog**, así que ninguna bóveda que hoy pasa empieza a
> fallar.

Los S3 eran de **dos naturalezas** que piden instrumentos distintos, y mezclarlos es lo que hace que
una tanda de "arreglar lo menor" no arregle nada:

**(a) Defectos reales → test rojo primero** (protocolo de arriba). Seis (la entrada decía
"siete" y enumeraba seis — error de conteo, corregido en la 8ª pasada):
- **`PROT_NEG` producía un falso NEGATIVO.** El negador se buscaba en la oración entera, así que
  *"El período de rotación es 34 d [[bib]] y no hay señal en el bisector"* apagaba el backlog: la
  ficha perdía el hueco marcado justo cuando el dato SÍ está. Ahora el negador sólo cuenta hasta
  donde cerraron la mención y la cita. Verificado con los ocho casos, incluidos los que motivaron el
  negador (`## Huecos`), el wrap a 100 columnas y la cita antes de la mención.
- **El lint moría al imprimir en consolas no-UTF8** (`ascii`, `cp1252`): `UnicodeEncodeError` en el
  `print` final → exit 1 indistinguible de "hay bloqueantes", con el `.md` en disco perfecto. La
  compuerta vive del exit code, no de la letra bonita.
- **`n_dropped` contaba decisiones que no son descartes** → la cabecera de la ficha publicaba un
  descarte que nadie hizo. Extraído a `n_dropped_chaining()`, que además ahora es testeable.
- **`drop()` pisaba el juicio previo sin avisar** mientras su hermano `drop_source` sí avisa: los dos
  carriles comparten espacio de claves, así que se perdía el motivo y el `origen`.
- **`--migrate` borraba un `triage.json` del que no consolidó nada**, diciendo "ya consolidado".
- **Ground-truth sin ficha no lo miraba nadie** — hermano simétrico de "ficha sin ground-truth".

**(b) Cobertura → el test ES el entregable, y el mutante se especifica de antemano.** Acá el código
ya estaba bien: un test escrito contra código correcto **nace verde y no prueba nada**, que es el
modo de falla que esta misma auditoría encontró siete veces. Por eso el criterio no fue "rojo →
verde" sino **"pasa sobre el código actual y muere con ESTE mutante"**, con los mutantes fijados
línea por línea en un catálogo *antes* de escribir un solo test — si el ejecutor elige el mutante,
elige el que su propio test ya mata. **22 mutantes, 22 muertos**:
- **4 sitios de hallazgo BLOQUEANTE que ningún test ejecutaba** (medidos con `coverage`, no
  estimados): paper sin `tags:[paper]`, `pdf` no-str, ground-truth no-objeto, `planets` del GT
  no-lista. Cero sitios de backlog/WARN sin cubrir.
- **9 fixes que estaban *supuestos, no verificados*** (su mutante sobrevivía la suite entera):
  `relevance` case-insensitive, `show_decisions` con el registro, `cited_in_entity`, `in_dir` vs
  `startswith` (#33), marca `no_sintetizado` no-`str`, `normalize_lists` en `mirror_issues`, la
  coletilla del truncado, y **los dos consumidores de `es_del_carril`** — el predicado tenía test,
  pero ningún test sembraba `origen: fuente-declarada` para verificar que el consumidor lo excluya.
- **La superficie de CLI**: `triage.py` ya tenía sus 6 flags cubiertos; en `make_notes.py` **16
  flags** pasaban por sus funciones pero **nunca por argparse**, y en `query_ads.py` faltaba el
  despacho de `--probe` en `main()`. Ahí el mutante es romper el cableado (`dest` renombrado): es el
  modo de falla real, un `dest` mal escrito pasa la suite y falla en la primera corrida de verdad
  —ya pasó con `--migrate-disputes`—.

## ✅ Framework 1.22.0 (2026-08-23) — sexta pasada: fuzzing, contratos y el registro que se perdía

> Pedida por el usuario ("auditoría de todo lo que se hizo ayer, en profundidad ... buscar errores de
> implementación y documentación"), planificada con Fable y ejecutada con Opus en cuatro subagentes.
> **Cubre dos cosas**: la tanda del 22-08 (#70–#81 + cinco pasadas de auditoría) y —sobre todo— la
> **sexta pasada que había quedado sin commitear, sin entrada de STATUS y sin tag** (+832/−119,
> 22:11–22:32 del 22-08), que era el material menos revisado de todo.
> **562 tests verdes** (540 baseline + 22 casos nuevos), lint 0, **30 categorías** de reporte
> (una nueva), 12 bloqueantes. 1.21.0 → **1.22.0** — es **minor, medido**: sobre la misma bóveda de
> juguete HEAD daba exit 0 y el working tree da exit 1 con 6 bloqueantes (`normalize_lists` llevó el
> chequeo de forma de 1 campo a 10), así que **una bóveda existente que hoy pasa puede empezar a
> fallar**: la instancia tiene que mirarlo.

**Instrumentos nuevos** (las cinco pasadas previas ya habían usado doc↔código, medir lo declarado,
diff+cobertura+mutación, mutación de features + correr la cadena, e invariantes cross-artefacto):
**ejecución diferencial HEAD↔working tree** (el propio HEAD como mutante natural de todos los fixes
a la vez), **fuzzing por propiedades con semilla** (~5000 casos), **contratos de datos campo por
campo** entre productores y consumidores, **las afirmaciones del propio diff ejecutadas como
hipótesis**, **idempotencia/orden/atomicidad**, y **cobertura a nivel mensaje de hallazgo y flag de
CLI** (45 mutaciones dirigidas). Informe completo: `outputs/auditoria-sexta-pasada-2026-08-23.md`.

**El diagnóstico de fondo: la 6ª pasada acertó la tesis y falló el alcance.** Su tesis —un lector que
hace `X.get(k) or {}` sobre un `X` de forma no garantizada revienta o miente— es correcta, y los
cuatro lugares donde la aplicó salieron **verdes en el fuzz** (`normalize_lists` 960/960,
`load_registro`/`load_decisiones` 343/343, `objective_lens` 344/344, round-trip de decisiones
320/320 con claves hostiles a YAML). Lo que faltó fue el **barrido**: el mismo idioma vive en **59
líneas** de los 5 scripts que tocó. De ahí el helper único `as_map`/`as_list` en `lib_config`.

- **⛔ Pérdida de datos I — `--migrate-disputes` borraba la disputa que su propio mensaje decía no
  haber migrado.** El `pop("disputes")` corría **antes** de las guardas de forma, así que los dos
  `continue` "cobardes" saltaban la migración con el dato ya fuera del dict y el `write_text` final
  lo borraba del disco: se perdían el `ref` (bibcode) y el `alt` (valor discrepante), y después el
  lint quedaba **en verde afirmando que no hay desacuerdos** — lo que #71 existe para impedir.
  Contradecía el comentario de cabecera de la propia función ("NO toca el archivo"). Lo encontraron
  los cuatro subagentes por caminos distintos.
- **⛔ Pérdida de datos II — el registro versionado se perdía en silencio.** Registro corrupto →
  `load_registro` devuelve `{}` (tolerancia **nueva** de la 6ª) → el siguiente `save_decisiones`
  reescribe el archivo dejándolo en 4 líneas, con `busqueda` entera y 2 de 3 juicios borrados,
  `exit 0`, **imprimiendo** *"los dos lados de la decisión sobreviven al clon"* justo cuando los
  destruyó. Tres vectores medidos: write truncado; un `:` sin comillas en un motivo en español —**la
  edición a mano que el propio framework instruye**—; y concurrencia (registro de 111 KB: **17 de 46
  lecturas** vieron el archivo torn; dos `--drop` en paralelo ×20: **19 de 40 decisiones perdidas**).
  `save_registro` ahora es atómico (tmp+rename) y **rehúsa pisar** un registro que no parsea.
- **⛔ Seis clases de traceback tumbaban la compuerta de CI** (`retraction:` escalar, `objective.yaml`
  inválido —reachability máxima: el skill `setup` hace que el agente escriba **regex dentro de
  YAML**—, registro no-mapa, `ads.json` no-objeto, `triage.json` con `decisiones: 3`, ground-truth
  con `K_ms` no numérico). Doblemente malo: el proceso sale con **exit 1**, indistinguible de "hay
  bloqueantes", y como el reporte se escribe al final **no se reescribe** → queda el de una corrida
  previa leyéndose como vigente.
- **⛔ Un test nuevo rompía la suite en un clone limpio.** `test_segunda_pasada_vacia_...` no era
  hermético: leía el `vault/config/ads_dev_key` **real**, que está gitignored, así que en CI o en una
  máquina nueva moría con `RuntimeError` antes de ejercitar nada. Verificado en un worktree sin
  archivos gitignored.
- **Tres falsos limpios más.** El **registro ilegible** devolvía "Triage pendiente (0)" sobre un
  registro que declaraba 3 candidatos sin juzgar (el cero inventado de #64, por otra puerta), y la
  docstring nueva de `load_registro` **afirmaba lo contrario** ("el lint lo reporta"). El **`host`
  del ground-truth no-mapa** dejaba de vigilar los cuatro campos estelares sin reportar nada, y
  encima producía hallazgos fantasma. Y `planets[].disputes` escalar dejaba el lint **mudo** —se
  cambió un crash por silencio— mientras un string contaba **una disputa por carácter**.
- **Un chequeo prometido que no existía:** el comentario de `load_decisiones` afirmaba que el lint
  reporta una entrada de `decisiones` que no es un mapa. No existía → el triage volvía a proponer lo
  ya descartado **sin el motivo**, el bug que #51 cerró. Es la categoría 30 del reporte.
- **Deadlock de #69:** el lint marcaba la nota sin `GENERATOR_LINE` y recetaba `--restamp-headers`,
  que la salteaba si tenía `"Capa LLM"` — o sea **justo las notas marcadas**: 22 de 25 en el corpus
  real de Almagesto-RV, estampando **0 de 25**. El backlog no se podía cerrar con la herramienta
  documentada, y el modo de falla era el no-op silencioso que #69 existe para detectar.
- **`es_del_carril` no había llegado al tercer consumidor** (`ingest_topic`), y **ninguno de los dos
  que sí filtran tenía test**: los mutantes que les sacan el filtro sobrevivían la suite entera.
- **Lo que salió bien, medido:** **cero tests decorativos** (39/39 node-ids nuevos fallan en
  `v1.21.0`), cadena **idempotente** (`lint` ×2, `make_notes` ×2, `--migrate-disputes` ×2,
  `--drop-source` ×2), cero código muerto, hallazgos acotados (un `tags:` de 10 000 caracteres da 3
  hallazgos, no 10 000).
- **Doc:** `CLAUDE.md` decía *"hoy son seis"* campos incompletos y eran **siete**; los seis hallazgos
  de robustez del ground-truth **bloqueaban sin estar documentados**; la categoría renombrada
  ("frontmatter no parseable **o con forma inválida**") no se había propagado a los docstrings de
  `lint.py`. Corregidos.
- ~~**Sigue abierto:** el remoto está en **v1.13.0**…~~ **CERRADO el 2026-08-23**: se pushearon los
  commits y los 14 tags; el remoto quedó en v1.23.0 y el badge publica la versión real. (La línea
  quedó desactualizada por una semana en horas: la 8ª pasada la encontró midiendo
  `git ls-remote --tags` en vez de leer el texto.)

## ✅ Framework 1.21.0 (2026-08-22) — quinta pasada: recorrer la cadena entera, issue por issue

> Pedida por el usuario antes del push ("revisión completa del código, y del código nuevo contra la
> documentación; después mirá los issues de hoy uno por uno y seguí el camino de una estrella y de un
> método hasta el final"). Instrumentos nuevos otra vez: **invariantes cross-artefacto medidos**
> (no leídos), **correr la cadena de punta a punta** sobre una bóveda sintética, y **recorrer cada
> issue de hoy contra su código y su doc**. 501 tests verdes (**+8** sobre la pasada 4, medidos con `--collect-only` en los dos commits), lint 0.
> 1.20.4 → **1.21.0** (minor: el espejo de #70 detecta casos que antes pasaban, así que una bóveda
> existente puede pasar a exit 1 — la instancia tiene que mirarlo).

- **El agujero grande, en #70: el espejo comparaba `len(planets)`, no QUÉ planetas.** Una ficha con
  **b** y **d** contra un ground-truth con **b** y **c** —mismo largo, planetas distintos— volvía
  **limpia**. Y no es un caso raro: es exactamente cómo una señal no confirmada termina escrita en
  `planets[]`, donde se lee como ground-truth, en vez de en `disputes` como `d.existence`. O sea que
  el modo de falla que #70 existe para impedir —un número que no es de NEA en la capa auditable— era
  invisible en su versión más grave, un planeta entero. Ahora se comparan las **letras** en los dos
  sentidos (la ficha inventa uno / NEA confirma uno que la ficha no lista) y se reporta la **letra
  repetida**, que es lo único que el conteo veía y el conjunto no.
- **Un crash del lint (#75).** `sorted(extracted)` comparaba la tupla entera: dos notas con el mismo
  stem —una copia de trabajo de una nota de paper en otra carpeta— comparaban `no_sintetizado` (str
  contra `None`) y **volteaban el lint con un TypeError**. El lint es la compuerta de CI: ante una
  bóveda rara reporta, no se muere. Reproducido corriendo la cadena, no leyendo.
- **Chequeos hermanos asimétricos (#71).** Una **posición** que no es un mapa se reportaba; una
  **disputa** que no es un mapa se filtraba **en silencio** en `note_disputes` — y `disputes:` como
  escalar dejaba la nota como si no tuviera disputas. Es el mismo modo de falla que #71 vino a
  cerrar (lo que el lector ignora sin decir nada). Ahora hay un chequeo de forma, y reporta **una
  vez**, no una por carácter.
- **El hand-off de los dos orquestadores no nombraba el paso de #72.** El último `print` de
  `ingest_star.py` / `ingest_topic.py` es lo que el operador lee al terminar la cadena mecánica, y
  saltaba de "extracción por paper" a "síntesis": justo el orden que el contraste existe para
  impedir. Los dos ahora nombran los pasos **salteables** con su número del skill (2b/2c/3/3b/3c/5b
  y 3/3b/3c/4/6b), y el del tema nombra además el régimen (#74).
- **#81 tenía media feature muerta:** `--drop-source` acepta la **url** como clave, pero el consumidor
  (`ingest_topic`) sólo miraba la `key` del item — y un item de `sources:` **siempre** trae una clave
  con forma de citekey, así que un descarte registrado por url no se cruzaba nunca con la mitad que
  lo consume. Ahora se busca por clave **y** por url, y el aviso dice por cuál matcheó.
- **`write_star_note` era el único writer sin `mkdir`**: git no versiona directorios vacíos, así que
  una bóveda sin `vault/wiki/stars/` moría con un traceback de `FileNotFound` en el primer ingest.
- **Doc contra código, issue por issue** (los nueve de hoy): `CLAUDE.md` decía *"tanto en el número
  de planetas"* (#70), listaba *"P_rot null"* como campo incompleto —criterio **pre**-#70, donde el
  frontmatter nulo dejó de ser hallazgo—, enumeraba los campos incompletos con un "etc." que ocultaba
  dos de los seis, mandaba re-ingestar "para cubrir la cola" cuando desde #79 lo que falta es **el
  medio**, y no decía los dos recortes de la población de #75 (nota de entidad, y no-core afuera).
- **Invariantes medidos, no leídos:** las **29 categorías** del reporte del lint tienen su caso
  sembrado en la suite (instrumentando el lint y corriendo los tests, no grepeando), las 29 están
  documentadas en `CLAUDE.md` y las **12 bloqueantes** también; las **claves de frontmatter** que
  generan los cuatro tipos de nota coinciden **exactamente** con los schemas documentados; las **475
  funciones** `test_*` no tienen nombres duplicados (en pytest uno tapa al otro) ni ninguna sin
  `assert`; y de los **103 casos** de `test_lint.py`, los 43 que sobreviven a un "lint ciego"
  (mutante que reporta 0 en todo) son **31 funciones**, todas negativas o unitarias legítimas.
- **Mutación de los seis arreglos** (diez mutantes, uno por rama): cada uno revertido, cada test
  correspondiente falla.

## ✅ Framework 1.20.4 (2026-08-22) — cuarta pasada: los tests que pasaban por el motivo equivocado

> Pedida por el usuario ("auditá todo lo que se hizo hoy, en profundidad"). Instrumentos **nuevos**
> —la 3ª ya había leído el diff entero—: **mutación sobre las features** (47 mutantes escritos, 46
> aplicados —uno no matcheó—, y no sólo sobre los cuatro fixes), **correr la cadena de verdad** en una bóveda sintética, y **mirar los assets**.
> 493 tests verdes (+3), lint 0. 1.20.3 → **1.20.4** (patch: tests, doc de skills y textos).
> *(Tres números de esta entrada se corrigieron en la 5ª pasada —mutantes aplicados, comandos
> documentados, versiones sin tag—; el mensaje del commit conserva los viejos, como en
> 1.20.2: el registro durable es STATUS.)*

- **El hallazgo de fondo: cobertura ≠ assertion.** La 3ª pasada midió *"226 líneas ejecutables
  nuevas, 0 sin ejercitar"* y era cierto — pero **siete mutantes sobrevivieron** en ese mismo
  código. Ejecutar una línea no es afirmar nada sobre ella.
- **Tres tests verde-falso** (pasaban sin la cosa que decían testear):
  - `test_drop_y_drop_source_no_se_mezclan` — el `SystemExit` que esperaba venía de `load_ads`
    ("corré primero la cadena"), no de la guarda del argparse. Sin `ads.json` en la bóveda de
    juguete, la guarda podía borrarse entera. Ahora siembra el `ads.json` y exige además que el
    registro quede **intacto**.
  - `test_citado_solo_en_una_query_no_alcanza` (#75) — afirmaba `"Extraído pero no sintetizado" in
    out`, y ese **encabezado se imprime con (0) hits igual**; el bibcode que también buscaba salía
    de otra categoría del mismo paper (`role` sin llenar). Ahora va contra el **conteo** `(1)`.
  - `test_disputa_en_un_concepto` (#71) — sólo tenía el caso feliz, que da 0 hits tanto si el lint
    valida los conceptos como si **ni los mira**. Se le sumó el hermano con las dos fallas (una
    posición sola, `ref` sin nota) que un lint restringido a `stars/` dejaría pasar.
- **Cuatro contratos sin ningún test**, todos del tipo "no rompe, sale mal" (#69):
  - **el `sort` que viaja en la request** — el más caro: los tests de `recent_pass` mockean
    `query_ads`, o sea el lado de acá del parámetro. Hardcodear el orden dejaba la segunda pasada de
    #79 re-pidiendo la MISMA página —el rescate entero mudo— con la suite en verde.
  - los **seeds** `disputes: []` (ficha) y `role: []` (nota de paper): son el contrato de schema que
    la extracción viene a llenar; se podían borrar sin que fallara nada.
  - la **ubicación** de `disputes` justo después de `planets` en el migrador de #71.
- **Rollout incompleto de #71/#74 en los skills que escriben conceptos.** `ingest-topic` no
  nombraba `disputes` **ni una vez** aunque `write_concept_note` siembra el campo desde 1.19.0, y ni
  él ni `maintain` ni `append-knowledge` nombraban el **`## Régimen de validez`** que el template
  genera desde 1.18.0. Es la sección cuyo modo de falla (*generalizar de más*) `verify-citations`
  devuelve `soportada`: si el skill no la nombra, la condición se pierde sin dejar rastro. Agregada
  a los tres, con la distinción que la hace usable — **desacuerdo por régimen → fila; desacuerdo
  real bajo las mismas condiciones → `disputes`**.
- **El checklist de `append-knowledge` seguía en el modelo pre-#71** ("disputes[] si discrepa de
  NEA"): el polo de verdad hardcodeado que #71 vino a sacar, en el artefacto que el agente **copia
  al chat**, o sea el que efectivamente conduce. Mismo bug que la 2ª pasada encontró en el checklist
  de `maintain`: la prosa se actualiza y el checklist queda.
- **La captura `obsidian-ficha.png` ya no es el schema** — y el backlog de capturas afirmaba lo
  contrario ("sigue siendo correcto"), escrito el 21 y cierto hasta 1.13.0. No tiene `disputes`, sus
  `planets[]` traen `msini_earth`. Encima el README **enumeraba `disputes` como si se viera en la
  captura** (texto agregado hoy mismo). Corregidos los dos.
- **Tags de git faltantes:** `ALMAGESTO_VERSION` iba por 1.20.3 y el último tag era `v1.13.0` —
  **diez** versiones sin tag (1.14.0 … 1.20.3). No es cosmético: el badge del README lee
  `github/v/tag`, así que **publicaba 1.13.0**. Tageados 1.14.0–1.20.4 (once tags).
- **Menor:** `maintain` mandaba grepear `disputes[].ref`, una ruta que ya no existe
  (`disputes[].posiciones[].ref`).
- **Verificado corriendo, no leyendo:** en una bóveda sintética con el schema viejo, la cadena
  completa —lint detecta y bloquea → `--migrate-disputes` migra materializando el polo
  `ground_truth` → lint 0 → segunda corrida idempotente—; el espejo #70 y el backlog #75 disparan y
  se apagan con el caso sembrado; los **dos one-liners de roll-up** de `CLAUDE.md` corren y devuelven
  lo que prometen; y las **21 invocaciones** distintas de `python scripts/*.py` que aparecen en docs
  y skills (10 scripts) usan sólo flags que existen.
- Skills: `append-knowledge` 1.4.0 → **1.5.0**, `ingest-topic` 1.14.0 → **1.15.0**, `maintain`
  1.16.1 → **1.17.0**.

## ✅ Framework 1.20.3 (2026-08-22) — tercera pasada: el código, línea por línea

> Pedida por el usuario ("de nuevo, en detalle y con cuidado, **no de memoria**"). Las dos primeras
> pasadas auditaron **doc contra código** y **números y referencias**; ésta leyó el **diff de código
> completo** (`v1.11.0..HEAD`, 6 scripts) hunk por hunk y midió lo que no se puede leer: cobertura
> AST de cada línea nueva y **mutación** de cada fix. Siete hallazgos, **cuatro de ellos defectos
> reales de código**, no de doc. 490 tests verdes (+10), lint 0.

- **⛔ El detector de `triage.json` viejo (1.20.0) tenía un agujero, y justo en su caso de uso.**
  Colgaba del barrido de `build/*/ads.json`, así que un `build/` limpiado a medias —o una bóveda
  vieja sin `ads.json`— lo evadía por completo: el archivo quedaba **mudo**, que es exactamente lo
  que ese chequeo existe para impedir. **Reproducido con un test antes de tocar nada** (lint en 0 con
  el archivo presente). Ahora tiene barrido propio sobre `build/*/triage.json`.
- **La heurística de `P_rot` (#70) no reconocía la notación que el propio `CLAUDE.md` exige.** En
  `vault/wiki/` la regla es `$...$`, o sea `$P_{\rm rot}$` / `$P_\mathrm{rot}$` / `P$_{\rm rot}$`
  — y el regex sólo cubría `P_rot` y `$P_{rot}$`. Resultado: le habría dicho *"el cuerpo no documenta
  un P_rot citado"* a notas que **sí** lo documentan, que es el falso positivo más molesto posible.
  Ampliado y probado contra las cinco formas más un control (`Protostellar` ya no cuenta como
  mención).
- **`recent_pass` (#79) disparaba su request a ADS sin la pausa de cortesía** que el resto del
  módulo respeta (chaining, rescate por glifo y `fetch_bibcodes` duermen 1 s entre requests). Una
  incoherencia con la convención del propio archivo, en el único lugar que agrega una request.
- **Rama inalcanzable en el migrador de #71:** el `else` del reordenamiento no podía ejecutarse nunca
  (si la función llegó ahí, `planets` existe sí o sí). Código muerto que nació con la feature.
- **Dos incoherencias entre chequeos hermanos:** el backlog de `role` (#73) no excluía las notas
  **no-core** aunque su hermano de #75 sí lo hace, y `same_value` (#70) guardaba contra `bool` sólo
  de un lado de la comparación. Alineados.
- **El cableado CLI del migrador no lo tocaba ningún test.** `--migrate-disputes` sólo existe por
  línea de comandos, así que un `dest` mal escrito habría pasado los 480 tests y fallado en la
  primera corrida real. `test_make_notes.py` no tenía siquiera un helper para invocar `main()`; ahora
  lo tiene, y cubre los tres modos sin slug.
- **Un wrap destruido:** una edición de la segunda pasada dejó dos oraciones en una línea de 156
  caracteres en el docstring de `triage.py`. (Chequeado además que las líneas largas **no** son una
  violación de convención: el resto del repo también las tiene.)
- **Lo medido, no estimado:** **226 líneas ejecutables nuevas** en `scripts/`, **0 sin ejercitar**
  (cobertura por AST, no por heurística de texto: se cuentan sentencias, no docstrings ni
  continuaciones). Y los cuatro fixes de esta pasada pasaron **mutación** — se revirtió cada uno y se
  verificó que su test falla; ninguno es vacuo.
- **Verificado y limpio:** ningún import muerto en los 15 scripts; `json` sigue en uso en
  `lib_config` tras vaciar `load_decisiones`; las 12 assertions negativas de `test_lint.py` no caen
  en la trampa del path temporal (que ya mordió una vez en esta tanda).

## ✅ Framework 1.20.2 (2026-08-22) — segunda pasada: lo que la primera no miró

> Pedida por el usuario ("revisá de nuevo, en detalle y con cuidado"). La primera pasada auditó la
> **doc contra el código**; ésta miró lo que aquélla no tocó: los **números que declaré**, las
> **referencias cruzadas** entre skills tras renumerar pasos, y el **código muerto** de las
> remociones. Cinco hallazgos. 480 tests verdes, lint 0. Patch.

- **⛔ Un delta de tests estaba inventado.** La entrada 1.12.0 decía "416 tests (+13)"; el total era
  correcto pero el delta real es **+15**. Lo medí en serio esta vez: un `git worktree` detached,
  `pytest --collect-only` en cada uno de los 12 commits. **Los otros diez deltas y los doce totales
  dan exactos**, y `ALMAGESTO_VERSION` coincide con la entrada en cada commit. Es el mismo error que
  la auditoría de 1.10.3 encontró en la entrada 1.9.0 (+6 declarado, +9 real): un delta que se
  escribe de memoria en vez de medirse. El mensaje del commit `68264e2` conserva el número viejo
  —corregirlo pediría reescribir diez commits, y el registro durable es éste—.
- **El checklist de `maintain A` no tenía los dos pasos que más se saltean.** La prosa tiene 2b
  (contraste, #72) y 3b (auto-revisión, de 1.10.3); el checklist saltaba de 2 a 3 y de 3 a 4.
  Justamente el checklist existe (#66) para los pasos que **no dejan rastro si se omiten** — y esos
  dos son de ésos. Agregados.
- **El reporte al chat de `verify-citations` no mencionaba las condiciones perdidas.** El bloque que
  va *en la nota* sí las lleva (#74), pero el reporte enumeraba correcciones, contradicciones y
  omisiones — y el campo `condicion` es de la misma familia: un hallazgo que no cambia el veredicto.
  Media feature entregada.
- **Dos números de línea podridos en el embudo de `docs/ingesta.md`.** `make_notes.py:702` ahora
  apunta a `stamp_search_line`, no al filtro de core (mis propias tandas movieron ~100 líneas);
  `fetch_arxiv.py:93` seguía bien de casualidad. Reemplazados por **nombres de función**, que no se
  pudren. Eran los dos únicos `archivo.py:NN` de toda la doc.
- **El embudo había quedado mal anidado** al insertar la segunda pasada por fecha (#79) y los dos
  escalones de síntesis (#72/#75): la 2ª pasada colgaba como hermana de `classify()` cuando en
  realidad la alimenta. Reescrito el árbol completo.
- Skills: `maintain` 1.16.0 → **1.16.1** (el checklist con 2b y 3b), `verify-citations` 1.7.0 →
  **1.7.1** (el reporte al chat menciona las condiciones perdidas).
- **Verificado y limpio:** las 26 referencias cruzadas a pasos numerados entre skills siguen
  resolviendo (renumeré `ingest-star` 3→3/3b/3c y agregué 3c a `ingest-topic`, y nadie apuntaba a
  esos números); no quedó **ningún símbolo muerto** tras sacar las capas de compatibilidad
  (`LEGACY_DISPUTE_FIELDS` desapareció, `LEGACY_FIELD_TO_GT` sigue en uso por el migrador); y el
  `[[bibcode]]` literal de los bloques nuevos **no** contamina `bench_verify` (exige
  `BIBCODE_RE` + fulltext, así que el placeholder no puede sembrarse como par).

## Backlog — ground-truth NEA+SIMBAD con autoridad POR CAMPO (anotado 2026-08-23)

> Pregunta del usuario: *"¿SIMBAD se puede usar como NEA? ¿qué pasaría si hay discrepancia?"*

**Hoy la discrepancia no puede existir, y eso es el problema:** `fetch_ground_truth` consulta SIMBAD
sólo como **fallback de `spectral_type`** cuando NEA viene nulo (`:163`). Si los dos catálogos
difieren, gana NEA **por orden de consulta, en silencio** — nadie se entera.

**Salida propuesta: autoridad por CAMPO, no por catálogo.** Planetas (P/K/e/masa) → NEA, que es el
único que los tiene; `spectral_type` y `dist_pc` → SIMBAD, que es su dominio (el `st_spectype` de
NEA suele venir copiado de literatura); `teff_K` → NEA. Así cada campo sigue teniendo **una** fuente,
el espejo #70 queda intacto y no hay nada que decidir en runtime. Para cuando igual difieran: el JSON
guarda **los dos valores** con cuál es el autoritativo, el frontmatter espeja ése, y el lint reporta
la discrepancia como **backlog** — el desacuerdo se ve en vez de taparse por orden de consulta.

Costo: el vocabulario de `disputes[].posiciones[].source` tiene un solo valor de catálogo
(`ground_truth`); habría que abrirlo a `nea`/`simbad` o la disputa no puede decir quién la sostiene.

**No hacer antes de la capa de bóveda poblada:** son esos tests los que van a decir cuántos campos
cambian en un corpus real. Y ver la entrada de abajo: si el camino es re-ingestar, este cambio deja
de costar casi nada.

## Criterio TRANSITORIO — re-ingestar es la escotilla de esta fase, no la política (anotado 2026-08-23)

> Del usuario, cerrando la discusión de NEA+SIMBAD: *"no sé si la re-ingesta va a ser lo estándar,
> es porque acá hicimos muchos cambios; lo ideal sería que ya esté lo suficientemente estable como
> para que los updates que sigan no tengan que tocar cosas que requieran mucha migración — estoy
> pensando en estos saltos grandes que estamos dando ahora, lo que está ahora más los issues que
> faltan"*.

**El objetivo es la estabilidad del schema, no la re-ingesta.** La re-ingesta es la **escotilla**
mientras dure la fase de saltos grandes (lo de esta tanda + los issues que quedan): sirve para que
el costo de migrar **no sea** el factor que decide un cambio correcto. No es el modo normal de
actualizar, y proponerla como tal sería convertir una salida de emergencia en un procedimiento.

Consecuencias prácticas:
- Al evaluar un cambio de schema **durante esta fase**, la migración no manda: si el cambio es
  correcto y migrar es caro, re-ingestar es una salida legítima (ver la entrada de arriba —
  NEA+SIMBAD era caro *sólo* por la migración).
- **Después** de esta fase el criterio se invierte: un schema que todavía obliga a migrar seguido es
  señal de que no está estable, y eso es lo que hay que arreglar, no la migración.
- Los migradores (`--migrate-disputes`, `--sync-mirror`, `triage --migrate`) son herramientas de una
  sola vez para la instancia que ya existe, no contrato permanente.
- El `vintage="1.11.0"` del generador (`tests/poblada/`) queda justificado por **testear los
  detectores** de schema viejo — ésa es la parte de la retrocompatibilidad que sí importa siempre.

## Backlog — los DOS ejes de prueba con bóveda poblada (anotado 2026-08-23)

> Pedido del usuario durante la auditoría del 23-08. Son **dos pruebas distintas**, con sujeto y
> variable de control distintos; confundirlas hace que ninguna mida lo que promete.

**(1) Prueba del CÓDIGO — se hace sobre lo que YA está.** Sujeto: el framework. Se corre contra el
corpus existente de la instancia (**Almagesto-RV**: 908 papers, 4 estrellas, 5 conceptos, 5
ground-truth, framework en 1.11.0) o contra el `ads.json` congelado de sus corridas. Variable de
control: **sólo cambia el código**. Es lo que caza los bugs que una bóveda vacía no puede revelar —
escala (medido: `is_legible` es el **77%** de los 5,6 s del lint sobre 908 notas, con doble parseo
YAML, 941 → 1882 `safe_load`), cross-referencias, roll-ups, invariantes globales, y el **upgrade
1.11.0 → 1.22.0**, que es el deploy real. Plan detallado y ensayado: `PLAN_TESTS_BOVEDA_POBLADA.md`
(generador sintético determinista + la instancia real como tier opt-in; tres tiers de pytest).

**(2) Prueba de CALIDAD — la bóveda en paralelo.** Sujeto: el resultado bibliográfico. Re-ingestar
lo que tiene Almagesto-RV en una bóveda paralela y comparar las dos síntesis, para ver cómo quedaron
las mejoras. Mide **calidad del producto**, no corrección del código. **Se espera a que esté todo
implementado — no empezar sin conversarlo.**

⚠ **Salvedad para (2):** re-ingestar contra ADS hoy **no aísla la variable framework** — las queries
traen papers nuevos y los conteos de citas cambiaron desde la ingesta original, así que un diff
crudo mezcla "mejora del framework" con "pasó el tiempo". Para que mida lo que se quiere, la corrida
nueva tiene que partir del **`ads.json` congelado** de la instancia vieja (o de un snapshot de la
respuesta de ADS) y variar sólo el código. Eso además la vuelve reproducible y barata de repetir en
cada versión.

## Backlog — ¿esto sirve con cualquier agente, no sólo Claude? (anotado 2026-08-22)

> Pedido del usuario mientras corría la segunda auditoría: *"si todo esto es compatible con cualquier
> agente no sólo Claude, analicemos cómo se puede hacer eso, pero más adelante"*. Se analiza cuando
> cierre la tanda en curso — **no** empezar sin conversarlo.

Lo que ya es agnóstico: `scripts/` (Python puro), el schema de frontmatter, `lint.py` (el "test suite"
del contenido), el registro versionado y `vault/` entero. Un agente cualquiera puede correr la cadena
y el lint sin saber nada de Claude.

Lo que **no** lo es: la capa de instrucciones. `.claude/skills/*/SKILL.md` es formato de Claude Code
(frontmatter `name`/`description`/`version` + invocación por slash), `CLAUDE.md` es el archivo que
Claude carga solo, y varias operaciones asumen primitivas concretas —el **fan-out de subagentes** de
`verify-citations` y `find-contradictions`, y las herramientas de lectura/grep—.

Ejes a evaluar cuando se retome (sin decidir nada todavía): (a) si el contenido de los skills puede
vivir en un directorio neutral (`docs/operaciones/`) con `CLAUDE.md` y los `SKILL.md` como punteros
finos, para que otro agente lea lo mismo; (b) qué reemplaza al fan-out donde no hay subagentes —¿un
script que orquesta llamadas?—, y si el skill puede declarar ese requisito en vez de asumirlo; (c) si
conviene un `AGENTS.md` (la convención que están adoptando otros agentes) que apunte al mismo
contenido; (d) el costo real: hoy la doc está en **un** lugar por operación, y partirla en
contenido+puntero es exactamente el tipo de duplicación que ya nos mordió dos veces (las listas de
bloqueantes copiadas a mano). Medir eso antes de mover nada.

## ✅ Framework 1.20.1 (2026-08-22) — auditoría de coherencia de las tandas 1-4

> Pedida por el usuario antes de limpiar contexto: revisar en profundidad todo lo hecho (1.13.0 →
> 1.20.0, nueve issues) y que la **doc de implementación** sea acorde. **Doce hallazgos, cada uno
> verificado contra el código antes de tocar nada** — la lección de las auditorías de 1.10.2/1.10.3.
> 480 tests verdes, lint 0. Patch: sólo doc y textos.

- **⛔ El grande: `CLAUDE.md` tenía el mismo bug de orden que corregí en `ingest-star`.** Su paso 2
  de *Ingest* decía "poblás la extracción del paper … **actualizás la ficha** (síntesis, huecos)" y
  recién después venía el 2b del contraste. O sea: el documento canónico mandaba **sintetizar antes
  de contrastar**, que es exactamente lo que #72 existe para evitar. Partido igual que el skill:
  **2 (notas de paper) → 2b (contraste) → 2c (síntesis a la nota viva)**. De paso al paso 2 le
  faltaba `role` (#73) en la lista de lo que puebla la extracción.
- **Un bloqueante del lint no estaba en la lista canónica.** *Juicio de triage en
  `build/<slug>/triage.json`* (1.20.0) bloquea en el código pero `CLAUDE.md` no lo enumeraba.
  Verificado ahora **mecánicamente**: los 12 símbolos del `n_block` del lint tienen su marca en el
  párrafo. (Y quedó un typo mío de #73: *"El* fuga de implementación" por *"La"*.)
- **`query-corpus` mandaba responder con el frontmatter, que después de #70 miente por omisión.**
  Decía que la ficha "suele tener la respuesta directa (P_rot, planetas…)"; con el espejo puro, un
  `null` significa **"NEA no lo tiene"**, no "no se sabe" — el valor de literatura está en el cuerpo,
  citado. Un agente siguiendo ese paso contestaba "no hay dato" con el dato en la nota. Corregido, y
  apuntando al `## Inventario por eje` cuando el eje está en disputa.
- **Las dos listas de bloqueantes copiadas a mano** (`query-corpus`, `test-hypothesis`) estaban
  viejas otra vez — el mismo drift que la auditoría de 1.10.2 ya había arreglado una vez. Esta vez no
  se re-sincronizaron: se **borraron**, apuntando al `exit code` del lint y a `CLAUDE.md`. Copiar una
  lista que cambia es el bug; mantenerla al día no lo arregla, sólo lo pospone.
- **Restos del schema viejo de disputas** en tres lugares que el barrido de 1.19.0 no tocó:
  `ingest-star` (el frontmatter propio de la ficha, y el foco del verify) y `maintain` (la reparación
  de colgados, que ahora es `disputes[].posiciones[].ref`).
- **El header de `make_notes` afirmaba de más:** "las excepciones son **quirúrgicas**". Desde 1.19.0
  hay una que no lo es (`--migrate-disputes` re-serializa el frontmatter). Acotado, y sumada como
  excepción (e) con su porqué.
- **Menores:** `docs/operacion.md` no listaba `--migrate-disputes`; `docs/ingesta.md` no tenía #92 en
  el backlog (ni en el escalón 3, que es donde las keywords se apelmazan) y no decía que dos de las
  cuatro ocurrencias de #79 ya están hechas; el README no mencionaba el paso de contraste (que es un
  diferencial: *sin* columna de valor adoptado); el checklist de `ingest-topic` no nombraba el paso
  nuevo; el orden de claves del schema de `concepts/` en `CLAUDE.md` no era el que genera el código.
- Skills: `query-corpus` 1.3.0 → **1.4.0**, `test-hypothesis` 1.3.0 → **1.4.0** (los dos
  reportan valores al chat, y los dos cambios son sobre qué leer y qué copiar).
- **Verificado y NO tocado** (para que no se re-abra): las versiones de los 9 skills coinciden con lo
  que declara cada entrada de STATUS; `tests/README.md` cubre los 15 archivos de test; las secciones
  y claves de frontmatter que genera `make_notes` coinciden con los schemas documentados; los
  `[[bibcode]]` de los bloques nuevos **no** generan wikilinks rotos (`bibcode` está en `LINK_SKIP`);
  y el "fallback (json viejo sin flag)" del recompute de masa **no** era una capa de compatibilidad
  (ya corregido el comentario en 1.20.0).

## ✅ Framework 1.20.0 (2026-08-22) — sin capas de compatibilidad: la misma regla, aplicada a todo

> Pedido del usuario al ver la de #71: *"sí, quiero el mismo tratamiento para todo, simplifiquemos"*.
> 480 tests verdes (+3), lint 0. 1.19.0 → **1.20.0** (minor: dos categorías de lint nuevas; el
> lector queda **más chico** que antes).

- **La regla, ya explícita:** el framework **no lleva capas de compatibilidad**. Una tolerancia en el
  lector es complejidad **permanente** (dos semánticas que mantener y testear para siempre) a cambio
  de una compatibilidad que hoy no le sirve a nadie —una sola persona lo usa— y que además suele
  **mentir**, porque la forma vieja no sabe expresar lo que la nueva agrega. Reemplazo: **migrador de
  un solo uso + detector**. Lo único que no se negocia es que lo viejo **no quede mudo**: un lector
  que lo ignora en silencio es peor que un error (criterio de #69).
- **Barrido de lo que quedaba** (grep por `legacy|pre-1\.|tolerante|json viejo`), tres candidatos y
  un falso positivo:
  - **`load_decisiones` mergeaba `build/<slug>/triage.json`** (pre-1.9.0, #51). Sacado. El camino es
    `triage.py <slug> --migrate`, que ya existía, y el lint reporta el archivo como **bloqueante**
    mientras exista — si quedara mudo, el triage volvería a proponer lo ya descartado **sin el
    motivo**, que es exactamente el bug que #51 arregló.
  - **`load_concept_areas` infería la lista de las carpetas en disco** cuando `objective.yaml` no la
    declaraba ("instancia vieja, pre-feature"). Sacado, y de paso era **peor que inútil**: inferir la
    lista convierte cualquier typo **ya cometido** en "área declarada", o sea lo contrario del
    chequeo. Ahora sin declarar = typo-check **apagado**, y el lint lo dice **una vez** (WARN) en vez
    de marcar cada carpeta.
  - **`planets[].disputes[]`** ya se había resuelto así en 1.19.0 (mismo pedido).
  - **Falso positivo:** el recompute de masa del lint (`# fallback (json viejo sin flag)`) **no** es
    compatibilidad — corre sobre todo planeta que el fetch no marcó, que son casi todos: es el
    chequeo **independiente** del lint, que es su trabajo. Sólo se corrigió el comentario, que
    llevaba a leerlo como un resto.
  - **Fuera de alcance por criterio:** las claves ausentes en `build/` (p. ej. `truncated.recent`).
    `build/` es scratch **regenerable**: no hay juicio que perder ni migración que correr, así que
    ahí "el dato puede no estar" no es una capa de compatibilidad sino un desconocido honesto.
- **Tests (+3):** el `triage.json` viejo bloquea (y un JSON **ilegible** también se reporta, sin
  inventar un conteo de 0), y `concept_areas` sin declarar se reporta **una vez** y no por carpeta.
  Más los tres tests existentes reescritos: el lector ya no mergea, `--migrate` sí recupera el motivo,
  y el modo tolerante de áreas devuelve `[]`.
- Skill `maintain` 1.15.0 → **1.16.0** (los dos hallazgos nuevos y cómo se resuelven). `CLAUDE.md`,
  `triage.py`, el docstring del lint, `objective.yaml` y `tests/README.md` (principio de diseño nuevo)
  sincronizados.

## ✅ Framework 1.19.0 (2026-08-22) — #71: las disputas dejan de tener el polo de verdad hardcodeado

> **Tanda 4** — el ítem más caro del lote: el único que toca instancias ya ingestadas con cambio de
> schema. 477 tests verdes (+16), lint 0. 1.18.0 → **1.19.0** (minor: estructura nueva + migrador de
> un solo uso; **sin** capa de compatibilidad — ver la decisión de abajo).

- **El defecto era de FORMA, no de contenido.** `planets[].disputes[]` (`field`/`ref`/`note`/`alt`)
  tenía el polo de verdad **hardcodeado**: el otro lado del desacuerdo era, implícitamente, el valor
  del frontmatter. Servía para paper↔NEA y **no podía expresar paper↔paper** — sin NEA no hay contra
  qué poner `alt`.
- **Y ese caso no es raro, es el normal.** NEA calla seguido (`K` y `e` enmascarados, `P_rot` sin
  `st_rotp`), que es justo lo que #70 dejó explícito. Encima `P_rot` es de la **estrella**, no de un
  planeta: ni siquiera tenía dónde colgar. El propio `find-contradictions` ya lo había identificado y
  lo mandaba a **prosa** — o sea: no acumulable, no chequeable por el lint, invisible al consumidor
  máquina, que es exactamente lo que la estructura existía para evitar.
- **`disputes` a nivel nota, con posiciones explícitas.** `field` nombra el eje (`P_rot`, `b.K`,
  `b.existence`) y cada posición dice **quién la sostiene**: `{ref, value}` por paper, o
  `{source: ground_truth, value}` cuando NEA arbitra. **Ese marcador es el punto del issue:**
  distingue *"hay autoridad y dice X"* de *"la bóveda genuinamente no sabe"*. Vale igual para
  **conceptos**, donde la disputa es simétrica por definición.
- **Chequeos nuevos (bloqueantes):** `ref` de una posición sin nota de paper (el de antes, ahora por
  posición), **disputas en el schema viejo** (que el lint ya no lee: migrar), y **disputa mal formada** — sin `field`, con **menos de dos posiciones** (con una sola
  no hay desacuerdo: es una afirmación y va a la prosa citada), con una posición que no dice quién la
  sostiene, o con un `source` fuera del vocabulario.
- **Migración: `python scripts/make_notes.py --migrate-disputes`.** Materializa el lado implícito
  como `{source: ground_truth, value: <el valor que la ficha tiene hoy>}` — y **no lo inventa**: si
  NEA no tiene el valor (el caso de #70), la posición queda sin `value`, que es "hay autoridad y
  calla". Es el único miembro de la familia `--restamp-*` que **no** es cirugía por línea: cambia la
  estructura del frontmatter, así que re-serializa. Por eso toca **sólo** las fichas con disputas
  viejas —una bóveda sin disputas no se reescribe— y **nunca** el cuerpo.
- **⛔ El lint NO lee el schema viejo — decisión del usuario, y es la correcta.** La primera versión
  traía tolerancia de lectura (los dos schemas a la vez, como #51 con el `triage.json`). El usuario
  la bajó: *"no compliques esto para mantener la retrocompatibilidad, sólo yo lo estoy usando por
  ahora"*. Tenía razón — esa tolerancia es **complejidad permanente en el lector** a cambio de una
  compatibilidad que nadie necesita, y encima el schema viejo no sabe expresar la mitad de los casos.
  Lo que **sí** hacía falta salvar de esa idea es que las disputas viejas no queden **mudas**: al
  sacar la lectura, el lint las **detecta y bloquea** con el comando de migración. Un lector que
  ignora en silencio es peor que un error — el mismo criterio de #69.
- **Tests (+16):** paper↔paper sobre un campo estelar (el caso que antes no se podía escribir), la
  posición `ground_truth`, disputa en un **concepto**, las cuatro formas mal formadas, y que el
  schema viejo **grita en vez de volverse mudo**; del
  migrador: materialización del polo implícito, `existence` → `status`, **no inventar** el valor que
  NEA no tiene, idempotencia, preservación de las ya migradas y del orden de claves, prosa byte a
  byte, y —lo que el coverage destapó— los **caminos defensivos**: archivo inexistente, nota sin
  frontmatter, frontmatter sin cerrar y **YAML roto** (ahí reescribir sería destruir la nota).
  Cobertura de sentencias del código nuevo: **100%**.
- Skills: `find-contradictions` 1.4.0 → **1.5.0** (cambia la forma de su propuesta, que es su
  salida principal), `verify-citations` 1.6.0 → **1.7.0** (verifica cada `posiciones[].value` contra
  el paper que la sostiene; la posición de ground-truth **no** se verifica contra papers),
  `maintain` 1.14.0 → **1.15.0** (la migración, con el aviso de revisar el diff), `ingest-star` y
  `append-knowledge` (la instrucción de taguear). `CLAUDE.md`, `README` y `docs/ingesta.md`
  sincronizados.

## ✅ Framework 1.18.0 (2026-08-22) — #74: el régimen de validez, y la sobre-generalización que el verify daba por buena

> Cierra la **tanda 3** (síntesis: #72 → #74). 461 tests verdes (+3), lint 0. 1.17.0 → **1.18.0**
> (minor: sección nueva en el stub de concept + campo nuevo en el contrato del fan-out de
> `verify-citations`).

- **El eje de contraste de un concepto no es el de una estrella.** En una estrella comparás el mismo
  número medido dos veces. En un método, dos papers pueden decir cosas distintas y **estar los dos
  bien**, porque valen bajo condiciones distintas (SNR, muestreo, tamaño de muestra, definición del
  observable). Nada obligaba a registrar esas condiciones: la nota pedía `## Síntesis` y `## Huecos`,
  y el estándar *implementation-ready* pedía ecuaciones e inputs/outputs — no régimen.
- **El modo de falla dominante acá no es "dos números no coinciden" sino GENERALIZAR DE MÁS:** el
  paper afirma X bajo condiciones C y el concepto afirma X pelado.
- **Y `verify-citations` lo daba por bueno.** La afirmación pelada **sí está** en el paper, así que
  el fan-out devolvía `soportada` y la condición perdida no la veía **ninguna capa**. Es el
  "afirmar de menos" de las tablas truncadas en versión conceptual — sólo que acá la nota no afirma
  de menos: afirma **de más**.
- **`## Régimen de validez`** en el stub de concept (no en la ficha de estrella: allá hay
  ground-truth y el eje es otro), con la unidad que pide el issue:
  `Afirmación | Vale bajo (régimen) | Fuente | Rol`. El `Rol` es el `role` de #73 — **una aplicación
  acota el régimen de una fundacional, no la contradice**, que es el mismo encastre de la tanda 2.
- **Los `aparente` de un concepto dejan de tirarse** (`find-contradictions`). Hasta ahora se
  listaban aparte "para no re-flaggearlos": en una estrella está bien, en un concepto **es el
  hallazgo**. Ahora cada `aparente` de un concepto se propone como **fila de régimen**, y el
  contrato del subagente cambió para que devuelva **cuál es la condición** que separa a los dos
  papers, con cita: un "aparente" sin la condición explícita no sirve para escribir la fila.
- **El fan-out del verify gana un campo `condicion`**, y va **siempre**, no sólo en transcripciones:
  *"¿el paper afirma esto bajo condiciones que la nota no dice?"*. Hallazgo aparte, **no** cambia el
  veredicto (la afirmación está respaldada) — se resuelve agregando la condición, o como fila de
  régimen si es un concepto. El bloque de la nota suma la línea *Condiciones perdidas*.
- **`## Huecos` gana la entrada accionable que no tenía forma:** *régimen no cubierto* — las
  condiciones que la tabla deja fuera, o sea en qué régimen **nadie lo midió**.
- **Sin categoría de lint nueva, a propósito.** La red de este paso es la operación que ya corre al
  cierre: el verify pregunta por la condición en cada par. Una categoría "concepto sin tabla de
  régimen" encendería toda bóveda existente sin distinguir el concepto que legítimamente no tiene
  afirmaciones condicionadas.
- **Tests (+3):** la tabla está en el concept y **no** en la ficha, el orden
  Síntesis → Inventario → Régimen → Huecos, y la cabecera con la unidad del issue + el cierre en
  `## Huecos`.
- Skills: `find-contradictions` 1.3.0 → **1.4.0**, `verify-citations` 1.5.0 → **1.6.0**.
  `CLAUDE.md` (schema de concepts, estándar *implementation-ready* y la sección de Verify) y
  `docs/ingesta.md` sincronizados.

## ✅ Framework 1.17.0 (2026-08-22) — #72: el paso que estaba entre leer los papers y escribir la síntesis

> Primero de la **tanda 3** (síntesis): #72 → **#74** (queda). 458 tests verdes (+3), lint 0.
> 1.16.0 → **1.17.0** (minor: sección nueva en el stub de ficha/concept; las notas ya escritas no se
> tocan).

- **El defecto.** Entre *"leí N papers"* y *"escribo el `## Resumen`"* no había **ninguna operación
  descrita**: `ingest-star` decía "actualizás la ficha (síntesis, huecos)" y el stub dejaba
  `_(síntesis por LLM: qué se sabe…)_`. El paso con más apalancamiento de la cadena era el menos
  especificado.
- **Consecuencia medible:** cuando tres papers reportan tres `P_rot` distintos, la ficha termina con
  **una frase y un `[[bibcode]]`**. Se evapora que los otros dos valores existen, con qué método y
  qué baseline se midieron, y cuáles de los core ni se miraron.
- **`## Inventario por eje`**, entre la síntesis y los huecos, en la ficha **y** en el concept
  (bloque único compartido, criterio de `LLM_DISCLAIMER`): `Eje | Paper | Dice | Método / baseline`.
  Sólo los ejes **en disputa** — los de acuerdo unánime no entran, misma regla de poda que la prosa.
- **⛔ La columna que NO está es el punto.** "Valor adoptado" / "por qué" sería juicio de LLM en un
  artefacto que se lee como bibliografía, y sobre todo **decide por el consumidor**: rompe el flujo
  unidireccional de la regla #0. El inventario reporta el **estado de la literatura**; la lectura
  propia va aparte y marcada `inferencia`. Es la misma decisión que ya se había tomado al descartar
  las reglas de precedencia declarativas en `objective.yaml`.
- **Dónde paga:** (a) **autosuficiencia** — *"¿por qué el corpus dice 34 y no 11.5?"* es justo lo que
  la ficha promete responder sin abrir un paper; (b) **refresh** — `maintain A` ya no re-deriva la
  síntesis de cero: el inventario dice qué la sostenía, y un paper nuevo **agrega una fila**;
  (c) **verify** — cada fila es una transcripción citada, así que hereda el chequeo de
  **completitud** (¿hay más papers del corpus que reportan este eje?).
- **Encastra con la tanda 2, como decía el backlog.** El `role` (#73) dice **qué operación**
  corresponde entre dos filas (fundacional↔aplicación no es contraste, es instanciación), y la red
  de que el paso ocurrió **ya existe**: es el backlog *extraído pero no sintetizado* (#75). Por eso
  el orden era #73 → #75 → #72 y no al revés; no hizo falta categoría de lint nueva.
- **Los dos ingests quedaron con el paso explícito y en el orden correcto.** En `ingest-star` el
  paso 3 escribía la ficha, así que un "3b después de 3" habría quedado **después** de la síntesis:
  se partió en **3 (extracción a las notas de paper) → 3b (contraste) → 3c (síntesis a la ficha)**.
  En `ingest-topic` el contraste entró como **3c**, antes del paso 4 (síntesis del concept).
- **Tests (+3):** el bloque está en los dos tipos de entidad y es el mismo objeto, el orden
  Resumen → Inventario → Huecos, y la cabecera de la tabla **sin** columna de valor adoptado (más la
  prohibición dicha, no sólo omitida: quien llena la tabla tiene que saber por qué falta).
- Skills: `ingest-star` 1.16.0 → **1.17.0**, `ingest-topic` 1.13.0 → **1.14.0**, `maintain` 1.13.0 →
  **1.14.0** (el refresh se apoya en el inventario), `append-knowledge` 1.3.0 → **1.4.0** (una fuente
  nueva agrega una fila o abre un eje), `verify-citations` 1.4.1 → **1.5.0** (el inventario es el
  caso más frecuente de transcripción, y su pregunta de completitud es *"¿faltan papers?"*, no
  *"¿faltan filas de la fuente?"*).

## ✅ Framework 1.16.0 (2026-08-22) — #73: sin el rol del paper, "contrastar" no está definido

> Cierra la **tanda 2** (procedencia: #70 → #75 → #73). 455 tests verdes (+7), lint 0.
> 1.15.0 → **1.16.0** (minor: campo nuevo `role` en `papers/` + categoría de lint bloqueante que
> **no puede encenderse** en un corpus viejo —ninguna nota tiene el campo todavía— y un backlog que
> sí).

- **El defecto.** La nota registraba `bearing` (la **postura** respecto de una tesis) pero no **qué
  tipo de aporte** es el paper. Y el clasificador no puede darlo: `classify()` es regex sobre
  título+abstract+keywords, o sea clasifica **tema**, no rol.
- **Por qué es fundacional para la tanda 3.** Sin rol, *"contrastar dos papers"* no está bien
  definido, porque **no siempre es la misma operación**: fundacional↔fundacional se comparan
  supuestos y derivaciones; aplicación↔aplicación se pregunta si replica y **en qué régimen**;
  **fundacional↔aplicación NO es contraste, es instanciación** —la aplicación no contradice la
  ecuación, la pone a prueba—; y el `arbitro` (reanálisis que resuelve una tensión previa) **pesa
  distinto**, no se promedia. Por eso el backlog lo pone antes de #72 y #74.
- **Dónde hace daño hoy, no en el futuro:** `find-contradictions` es de donde salen las
  `disputes[]`. Mandar un par fundacional↔aplicación al fan-out **fabrica disputas falsas**, que es
  el error más caro de esa operación. El skill ahora descarta ese par en el paso 1 (andamiaje), que
  es donde puede leer el frontmatter — el subagente del fan-out sólo ve los dos `.txt`.
- **Vocabulario cerrado y bloqueante.** `fundacional | aplicacion | arbitro`, uno o varios (escalar o
  lista). Un typo dejaría el campo **mudo** para la única operación que existe para consumirlo:
  mismo modo de falla que un `thesis_links` que no matchea ninguna nota, y por eso el mismo trato.
  **No enciende ninguna bóveda existente**: ninguna nota tiene el campo todavía.
- **La red para que no nazca muerto** (backlog, sí enciende): paper **extraído** (`methods` poblado)
  sin `role`. Es el patrón de #87 —"se computa/guarda y nunca se usa"— atajado antes de que pase:
  un campo que sólo puebla la extracción, sin red, queda null para siempre.
- **Se apoya en #76**, como decía la dependencia: el bullet del rol entra en la **cola compartida**
  del stub (`_BULLET_ROLE`, junto a Métodos), porque el rol es del **paper**, no del tipo de sujeto.
- **Tests (+7):** valor fuera del vocabulario (bloqueante), las tres formas válidas × escalar y
  lista, validación elemento por elemento en un rol múltiple, el backlog del extraído sin rol y el
  caso de control (al no extraído no se le pide, sería el mismo hallazgo dos veces). Cobertura de
  sentencias del código nuevo: **100%**.
- Skills: `find-contradictions` 1.2.0 → **1.3.0** (la regla de contraste por rol, con la nota de que
  un corpus sin `role` no habilita el descarte), `ingest-star` 1.15.0 → **1.16.0**, `ingest-topic`
  1.12.0 → **1.13.0** (donde más pega: en temas de método, fundamentos y aplicaciones astro conviven
  en el mismo concepto por diseño), `append-knowledge` 1.2.0 → **1.3.0**.

## ✅ Framework 1.15.0 (2026-08-22) — #75: la red que le faltaba al paso más caro de la cadena

> Segundo de la **tanda 2** (procedencia): #70 → #75 → **#73** (queda). 448 tests verdes (+8),
> lint 0. 1.14.0 → **1.15.0** (minor: categoría de lint nueva —backlog, no bloquea— y campo
> opcional `no_sintetizado` en `papers/`).

- **El hallazgo de fondo de la sesión de diseño, hecho red.** Todo paso salteable de la cadena tiene
  una: #55 el triage, #56 la verificación stale, #69 la cabecera. El de **síntesis** —el más caro y
  el que define la calidad de la ficha— no tenía ninguna. Y su modo de falla es **omisión**, que no
  deja rastro: nada queda mal escrito, el paper simplemente nunca llegó.
- **`verify-citations` no puede verlo, por diseño.** Valida cada afirmación contra su fuente, no la
  **cobertura del conjunto**: una ficha sintetizada desde 3 papers de 40 vuelve **100% soportada**.
  Es el mismo modo de falla de "afirmar de menos" que ya apareció en las tablas truncadas (#29) y en
  la garantía vencida (#56), ahora en el eslabón que produce la ficha.
- **La regla:** paper con `methods` poblado —o sea que **ya pagó** la extracción— cuyo bibcode **no
  aparece citado en ninguna ficha ni concepto** → backlog *extraído pero no sintetizado*. Mide si el
  paper **llegó**, no si la síntesis es buena: es el análogo exacto del proxy que ya existía para
  planetas (cada planeta del frontmatter discutido en prosa).
- **Por qué la población son los YA extraídos y no todo el core.** La **regla de poda** manda dejar
  lo tangencial fuera de la prosa, así que exigirle a cada core aterrizar sería ruido puro. Pero lo
  tangencial normalmente **ni se extrae**: `methods` poblado significa que alguien decidió que ese
  paper importaba. El core sin extraer ya tiene su propia categoría, y reportarlo en las dos sería
  el mismo hallazgo dos veces.
- **La escotilla lleva motivo obligatorio.** `no_sintetizado: <motivo>` en la nota del paper cierra
  el hallazgo (regla de poda, aporta sólo vía roll-up, …); la marca **pelada** —`true`, o vacía— se
  sigue reportando. Mismo criterio que el `--reason` del triage: no curar en silencio, porque el
  motivo es lo único no regenerable.
- **"Llegó" es a una nota de ENTIDAD** (`stars/`, `concepts/`), no a cualquier nota: una `queries/`
  es una respuesta puntual, no la síntesis durable de un sujeto.
- **Tests (+8):** el hallazgo y sus tres formas de cerrarse (citado en ficha, citado en concepto,
  `no_sintetizado` con motivo), los tres casos que NO deben entrar (citado sólo en una query, paper
  sin extraer, paper no-core) y la marca sin motivo. Cobertura de sentencias del código nuevo:
  **100%**.
- Skills: `ingest-star` 1.14.0 → **1.15.0** (el checklist decía que el lint sólo tenía red para el
  último paso; ahora dice cuál cubre a cuál, y el paso 4 cierra con este backlog), `ingest-topic`
  1.11.0 → **1.12.0** (decía que no había proxy estructural para concepts: ahora hay uno),
  `maintain` 1.12.0 → **1.13.0** (cómo se resuelve). `CLAUDE.md` y `docs/ingesta.md` sincronizados.

## ✅ Framework 1.14.0 (2026-08-22) — #70: el frontmatter de `stars/` es espejo puro de NEA

> Primero de la **tanda 2** (procedencia): #70 → #75 → #73. 440 tests verdes (+15), lint 0.
> 1.13.0 → **1.14.0** (minor: chequeo nuevo del lint, **bloqueante**, que puede encender una bóveda
> ya ingestada — ver *Migración*).

- **El defecto.** `make_notes` copiaba `P_rot_days` del ground-truth con el comentario *"llenar con
  literatura si falta"* — o sea que el propio código **instruía** romper el contrato. Y los nulls de
  NEA no son excepcionales: `pl_rvamp` (K) y `pl_orbeccen` (e) faltan seguido, así que el caso es el
  **normal**. Resultado: un mismo campo podía traer un valor auditable de NEA o un número extraído
  por un LLM, con **idéntico aspecto y ninguna marca**.
- **Por qué importa más de lo que parece.** La cabecera de la ficha promete que *"el ground-truth del
  frontmatter es auditable"* mientras la prosa es síntesis a revisar. Rellenar el campo **borra esa
  distinción**, que es el contrato máquina-legible con el consumidor. Y adoptar un valor cuando las
  fuentes discrepan es **decidir por quien consume**: rompe el flujo unidireccional de la regla #0.
- **Nada lo detectaba.** El único chequeo ficha↔ground-truth comparaba el **número de planetas**,
  nunca los valores. La promesa no tenía quién la sostuviera — el mismo patrón C de la sesión (la
  garantía existe, el rastro de que se cumplió no).
- **El fix es de detección, no de generación** (el script ya copiaba bien; lo que fallaba era la
  instrucción y la ausencia de red): el lint compara ahora **campo por campo** los cuatro del host
  (`spectral_type`, `teff_K`, `dist_pc`, `P_rot_days`) y los cinco de cada `planets[]`. Dos formas
  con **mensajes distintos porque el arreglo es distinto**: *difiere de NEA* → si sale de un paper es
  una `disputes[]`, no una sobreescritura; *NEA no lo tiene y la ficha sí* → al cuerpo, citado.
- **`P_rot_days` nulo deja de ser "campo incompleto"** (punto 4 del issue). No era accionable: NEA no
  lo tiene y "completarlo" era exactamente lo prohibido, así que se reportaba **para siempre**. Ahora
  lo accionable es lo correcto: *"NEA no lo trae **y** el cuerpo no documenta un P_rot citado"* — si
  la prosa lo documenta con su `[[bibcode]]` (o marcado `inferencia`), no hay hallazgo. Heurística
  deliberada, de la familia de la fuga de implementación: mención + respaldo en la misma línea.
- **⚠ Migración (instancias ya ingestadas).** El chequeo es **bloqueante** y una bóveda que rellenó
  campos a mano va a encenderse al mergear. Es el punto: son valores que hoy se leen como auditables
  sin serlo. Arreglo por hallazgo: mover el número al cuerpo con su cita y dejar el campo `null`
  (o taguear `disputes[]` si contradice a NEA); `python scripts/ingest_star.py <slug>` restaura el
  valor de NEA sin tocar la prosa.
- **Tests (+15):** las dos formas del hallazgo con su mensaje, nulls espejados y `34` vs `34.0` como
  no-hallazgo, los parámetros de cada planeta, el planeta que no está en NEA (no se duplica sobre el
  chequeo de cantidad), P_rot documentado vs no documentado, la regex de P_rot citado
  (6 variantes, con casos de control) y unitarios de `same_value`/`mirror_issues`. Cobertura de
  sentencias del código nuevo: **100%**.
- Skills: `ingest-star` 1.13.2 → **1.14.0** (su paso 3 mandaba completar `P_rot_days`), `maintain`
  1.11.1 → **1.12.0** (su backlog E mandaba completar el frontmatter). `CLAUDE.md`, `README`,
  `docs/ingesta.md` y `docs/operacion.md` sincronizados.

## ✅ Framework 1.13.0 (2026-08-22) — #81: el rechazo de una fuente declarada no quedaba en ningún lado

> Cierra la **tanda 1** del backlog del 2026-08-22 (#76, #79 puntos 1-2, #81). 425 tests verdes
> (+9), lint 0. 1.12.0 → **1.13.0** (minor: flag nuevo + dos claves opcionales en `decisiones`,
> aditivas — un registro viejo se lee igual y el descarte del chaining no cambia de forma).

- **La asimetría de #51, en el otro carril.** La compuerta de triage tiene las dos mitades del
  juicio persistidas: el aceptado va a `extra_core`, el descartado a `decisiones` con su motivo. Las
  fuentes **declaradas** de un tema off-ADS no: `sources:` registra lo aceptado y *"miré este libro /
  esta URL y decidí que no es core"* no quedaba escrito. En un modo donde el usuario **define** qué
  es core (que es el diseño del off-ADS), ese juicio es tan **no regenerable** como el del triage —
  y se perdía igual al cambiar de máquina o al volver seis meses después.
- **`triage.py --drop-source <clave> --reason "…" [--pointer <url|doi>]`.** Escribe en las **mismas**
  `decisiones` del registro versionado (reusa el mecanismo, no inventa otro). Dos diferencias que
  salen del carril: no valida contra una lista de pendientes ni necesita `build/<slug>/ads.json`
  —un off-ADS puro nunca lo tuvo, no hubo query— y guarda `fuente:`, porque una clave sintética
  (`2006RasmussenWilliams`) sin url/doi es irresoluble seis meses después. `origen:
  fuente-declarada` distingue el carril; **sin `origen` = chaining**, así que los registros
  existentes se leen igual.
- **Que el juicio HAGA algo, no sólo quede anotado.** En el carril del chaining la persistencia sirve
  para *no re-proponer*; acá no hay descubrimiento que filtrar —la fuente la declara el usuario—,
  así que el equivalente es que `ingest_topic` **avise** con la fecha y el motivo si un item de
  `sources:` lleva una clave ya descartada. **Avisa, no frena:** volver a declararla puede ser un
  cambio de opinión deliberado.
- **`triage.py <slug>` sin `ads.json` ya no muere.** Moría con *"corré primero la cadena"*, que para
  un tema off-ADS puro es un consejo **imposible** (nunca va a haber `ads.json`). Ahora, si hay
  juicio registrado, lo lista con carril, fecha, motivo y puntero; sin juicio, el diagnóstico viejo
  sigue siendo el correcto (una estrella a la que le falta el ingest) y se mantiene.
- **`--drop` y `--drop-source` no se mezclan en una corrida:** son dos juicios distintos que
  comparten `--reason`, y mezclarlos escribiría el mismo motivo para los dos.
- **Tests (+9):** persistencia sin `ads.json`, motivo obligatorio, puntero ausente no se inventa,
  los dos carriles conviviendo sin pisarse ni tocar `busqueda`, carriles mutuamente excluyentes,
  listado sin `ads.json` (con y sin decisiones registradas), aviso de `ingest_topic` con su caso de
  control (otra clave / `aceptado` no disparan). Cobertura de sentencias del código nuevo: **100%**.
- Skill `ingest-topic` 1.10.1 → **1.11.0**; `CLAUDE.md`, `README.md` y `docs/operacion.md`
  actualizados (el registro ya no describe `decisiones` como "sólo triage").

## ✅ Framework 1.12.0 (2026-08-22) — #79 (puntos 1-2): el orden por citas dejaba afuera lo reciente

> Segundo issue de la tanda 1 del backlog del 2026-08-22 (queda #81). 416 tests verdes (+15), lint 0.
> 1.11.1 → **1.12.0** (minor: la cadena hace una request más al truncar, `ads.json` suma la clave
> `truncated.recent` y el valor `via: query:recent` — aditivos, un `ads.json` viejo se lee igual).

- **El defecto.** La cadena decide **relevancia** sin mirar citas (`classify()` es regex sobre el
  contenido), pero **ordena** por citas crudas — y la cuenta de citas está sesgada por la **edad**
  (*ageing bias*): los viejos tuvieron más tiempo de acumularlas. Donde el orden decide qué
  sobrevive a un corte, eso manda lo reciente al fondo.
- **Punto 2, el que borraba papers (server-side).** El `sort` viaja en la **request** a ADS: con
  `numFound > rows`, ADS devuelve el top por citas y **corta el resto**, así que lo truncado es
  sistemáticamente lo nuevo. Ningún re-ordenamiento local lo arregla — hay que **volver a
  preguntar**: `recent_pass` re-corre la MISMA query con `sort: date desc` y mergea lo que la
  primera no trajo, con `via: query:recent`. Corre **antes** de extra_core/glifo/chaining, así que
  lo recuperado siembra también el grafo de citas (mismo criterio que #42).
- **La marca NO se levanta.** Sigue faltando **el medio** del universo, así que `truncated` queda y
  se le agrega `recent`: cuántos rescató la pasada. El lint lo dice —"la cola RECIENTE ya está
  cubierta; falta el medio"— y **sólo** cuando el dato está: un `ads.json` anterior a 1.12.0 no
  trae `recent` y el mensaje no afirma nada sobre él (afirmar de más justo acá sería peor que no
  saber, criterio de #57).
- **Punto 1, el `--sweep` (client-side).** El barrido existe para rescatar "core poco citados que
  caen al fondo del ranking" (Garg+2019 / Willamo+2020) y **rankeaba por citas crudas**: repetía el
  sesgo del mecanismo que le falló. Ahora ordena por **citas/año**.
- **La política vive en un solo lugar** (`lib_config.citation_rate` / `sort_by_citation_rate`),
  que es lo que pide el **patrón B**: hay varias listas que ordenar en archivos distintos y, si se
  cambia una, las otras quedan viejas sin que nadie lo note. Cuidado registrado en el docstring:
  citas/año **también** sesga, al revés — por eso la edad cuenta el año de publicación y nunca baja
  de 1 (lo publicado este año se compara a 1 año, no a una fracción), en vez de la tasa cruda que
  le daría 6/año a un paper de dos meses con 1 cita.
- **Tests (+13):** unitarios de la política (edad, año ausente/no numérico/futuro, `citation_count`
  null, desempate determinista, no muta la entrada, default al año en curso), unitarios de
  `recent_pass` (orden pedido, `quiet_truncate`, dedup in situ, marca `via`, no-core incluidos),
  regresión de punta a punta (la segunda pasada corre **sólo** al truncar, lo rescatado siembra el
  chaining, `truncated.recent` persistido) y del lint (mensaje con y sin `recent`). Cobertura de
  sentencias del código nuevo: **100%** (medida con el `trace` de la stdlib).
- **Sigue abierto #79:** el punto **2b** (apéndice de excluidos — ahí el issue pide **dos bloques**,
  top citas + top reciente, no citas/año, y cambia el formato de la nota) y el **listado del
  triage**, que son las otras dos ocurrencias client-side del patrón B; el punto **3** (señales de
  ADS que no son citas: `read_count`, `trending()`, `useful()`); y el punto **4** (documentar la
  neutralidad a citas), que el backlog manda hacer **después** de #77/#78.
- Skills: `ingest-star` 1.13.1 → **1.13.2** (el ranking del sweep), `maintain` 1.11.0 → **1.11.1**
  (cómo leer el backlog de corpus truncado ahora).

## ✅ Framework 1.11.1 (2026-08-22) — #76: el stub de paper ramifica por tipo de sujeto

> Primer issue de la tanda 1 del backlog del 2026-08-22 (quedan #79 puntos 1-2 y #81). 401 tests
> verdes (+11), lint 0. 1.11.0 → **1.11.1** (patch: cambia el texto que genera el stub; sin campos,
> sin flags, sin categoría de lint nueva — las notas ya escritas no se tocan).

- **El defecto:** `make_notes` ramificaba por tipo de sujeto **sólo en el frontmatter** (`stars` vs
  `thesis_links`); el **cuerpo** era el mismo para los dos. O sea que un **tema** ingestado por ADS
  nacía pidiendo *"Planetas / parámetros"* y *"Actividad / indicadores"* — justo lo que `CLAUDE.md`
  declara que el eje tema/concepto **no** presupone ("agnóstico de disciplina"). La única variante
  con eje de tema vivía en la rama **off-ADS**, que es el modo opt-in y el que menos se usa.
- **Por qué no lo agarraba nada:** el lint sólo mira `methods` vacío, así que una plantilla mal
  orientada se propaga en silencio. Mismo patrón que #69: no falla, sale mal.
- **Fix:** `extraction_block(topic)` — un solo lugar de verdad para los bullets, por el mismo motivo
  que `LLM_DISCLAIMER` (lo escriben la rama ADS y la off-ADS; inline divergirían). Tema → *aporte al
  tema* (definición, mecanismo/ecuación, método, signo) + *régimen de validez*. Estrella → el
  ground-truth (P/K/e por planeta) **y los ejes de la lente**.
- **Lo que hace al bullet de estrella distinto del que reemplaza:** los ejes ya no están
  hardcodeados a actividad/planetas, salen de `relevance.topics` de `objective.yaml` — que es lo
  único que sabe de qué trata *esta* instancia — y el bullet de objetivo cita el `short` textual
  (`«actividad estelar vs RV planetaria»`). El ground-truth se queda porque **no** es lente: es
  schema de `stars/` (NEA + `planets[]`), y ahí el eje estrella sí es astro por diseño.
- **Sin `objective.yaml` degrada a genérico** (make_notes corrido suelto, fuera de la cadena): el
  stub sale sin facetas y con el texto de siempre, nunca inventado. Criterio de #48.
- **Lo que este issue NO hizo, a propósito:** el bullet *rol del paper* que su fix proponía es el
  punto 3 del fix de **#73**, que es donde se define el campo y el vocabulario
  (fundacional/aplicación/árbitro). Meterlo acá sería pedirle al LLM que llene algo sin lugar donde
  ponerlo. La dependencia declarada va en ese sentido: #73 se apoya en este stub, no al revés.
- Skills: `ingest-star` 1.13.0 → **1.13.1**, `ingest-topic` 1.10.0 → **1.10.1** (los dos repetían de
  memoria una lista de bullets que ahora la genera el stub; ahora apuntan a él).
- **Tests (+11):** unitarios de las dos funciones nuevas (`objective_lens` con objetivo completo,
  a medias y ausente; forma del bloque —encabezado, 4 bullets, newline final— que es el contrato que
  asumen los dos templates al interpolarlo) **más** la matriz de ramas `topic × facetas × short`, y
  regresión de punta a punta por `write_paper_notes` (estrella, tema, off-ADS comparte bloque).
  Cobertura de sentencias del bloque nuevo: **100%**, medida con el `trace` de la stdlib (no hay
  `coverage`/`pytest-cov` en el entorno y no se agregó dependencia).

## ✅ Framework 1.10.3 (2026-08-21) — segunda pasada de auditoría: lo que la primera introdujo

> Pedida por el usuario: repetir la revisión profunda de doc técnica y de uso. Tres frentes en
> paralelo, incluido uno que la primera pasada no miró (la doc **embebida en config y en los
> docstrings**, que los skills declaran fuente de verdad canónica). **Cada hallazgo re-verificado a
> mano**; dos de los reportados resultaron falsos. 382 tests verdes, lint 0. 1.10.2 → **1.10.3**.

- **⛔ La corrección de #60 de 1.10.2 estaba mal, y por el mismo motivo que la original.** El `awk`
  con ámbito de campo que reemplazó al `grep` roto pierde las listas en **flow style**
  (`stars: [tau Cet]`) — y ésa es exactamente la forma que deja `merge_frontmatter_list`, o sea
  **todo paper retro-linkeado**, que es la población que el roll-up existe para recuperar. Las dos
  formas conviven en el mismo corpus (bloque al crear la nota, flow al retro-linkear). Verificado
  llamando a las funciones reales, no a una imitación. **Tercera versión, ahora probada contra los
  cuatro casos** (bloque, flow, mención sólo en prosa, `stars:` como último campo del frontmatter):
  la receta parsea el frontmatter con `lib_config.split_fm`, **el mismo parser que el tooling**, en
  vez de matchear texto. Beneficio lateral verificado: compara por elemento, así que `GJ 71` ya no
  matchea a `GJ 710`. Lección anotada: una receta prescrita se prueba **antes** de documentarla; van
  dos iteraciones perdidas por no hacerlo.
- **El segundo `awk` contestaba otra pregunta.** El roll-up `## Métodos aplicados a esta estrella`
  es *los métodos de los papers de esta estrella*; el awk devolvía *todo paper de la bóveda que use
  el método*. Corregido a la intersección real.
- **El caveat que agregué a `find-contradictions` era inaplicable:** lo puse dentro del contrato del
  veredicto, es decir dentro de lo que decide el subagente del fan-out — que tiene prohibido leer
  otra cosa que los dos `.txt`, y el frontmatter no está ahí. Movido al **paso 1** (andamiaje), donde
  el orquestador ya lee notas. De paso: un paper `retracted` no es un desacuerdo "aparente", **sale
  del corpus** (frontera dura).
- **Afirmación causal falsa que escribí sobre `corrections`:** "sin correr la pasada periódica figura
  en 0 porque el dato nunca se pidió". Falso: la cadena de ingest cierra con
  `check_retractions --slug`, así que todo lo ingestado desde 1.8.0 ya trae sus `corrections`. El
  valor del barrido completo es el mismo que para retracciones: cazar lo publicado **después** del
  ingest y cubrir el corpus viejo.
- **El caveat de preprint (#57) no había llegado al paso donde los números entran a la bóveda.**
  Estaba en `verify-citations` (que lo detecta *después*) pero no en la extracción LLM de los dos
  ingests, ni en `query-corpus`/`test-hypothesis`, que reportan valores al chat. Agregado en los
  cuatro y en el paso 2 de la sección Ingest de `CLAUDE.md`.
- **`maintain B` prescribía un borrado que la cadena deshace:** `make_notes` re-escribe el stub de
  todo registro `relevant` sin nota, y los fetchers re-bajan el PDF; las `decisiones` del registro
  sólo cubren candidatos del chaining, no el core de la query. Ahora B obliga a decidir la
  durabilidad (sacar de `extra_core`, re-clasificar, o asumirlo) y dejarlo en el `log`.
- **`maintain A` no releía la nota como agente externo** (el estándar de autosuficiencia que sí
  tienen los tres skills de escritura). Agregar cinco papers sin releer el conjunto es cómo una
  ficha deja de alcanzar sola sin que nadie lo note.
- **La promesa del registro ahora es cierta.** El README decía que `busqueda` permite saber "con qué
  versión del clasificador se filtró", pero `almagesto_version` es la del **framework**: cambiar una
  regex de `relevance.topics` mueve el corte sin mover la versión. En vez de bajar la afirmación, se
  agregó al registro el campo **`lente`** (facetas con sus regex + `require`/`min_topics` +
  `noise_doctypes`), que es lo que PRISMA-S llama los límites aplicados.
- **La doc de uso mandaba un comando que falla en el camino recomendado.** `git merge upstream/main`
  sobre un repo creado con "Use this template" devuelve `fatal: refusing to merge unrelated
  histories` (reproducido con un fixture): la historia limpia del template no tiene ancestro común.
  Documentado el primer merge con `--allow-unrelated-histories`, cómo resolver los conflictos add/add
  a favor de upstream, y que del segundo en adelante vale el comando simple.
- **La guardia de expansión no protege el primer ingest** —`if not conocidos: return`—, que es justo
  el caso con el que yo la había justificado en la pasada anterior. Corregido en `docs/operacion.md`
  y en la entrada 1.10.2 de este archivo. Umbral real: `>= 50` nuevos, no `> 50`.
- **Otros:** el registro de un tema off-ADS **mixto** sí existe (el README decía que no);
  `python triage.py` generado por `query_ads` era el último resto de #59 (falla desde la raíz);
  Node/npx faltaba en las dos listas de dependencias (es dura para el modo web); `stars.yaml`
  documentaba sólo la mitad aceptada de la curación; los headers de `make_notes`, `extract_fulltext`,
  los dos fetchers, `query_ads`, `lint` y `triage` describían versiones anteriores de sus módulos; el
  ejemplo de `--probe` omitía el bloque de la regla de combinación que el programa siempre imprime;
  pathfinder son **385k** papers de ADS, no 300k (verificado contra la versión publicada que el
  README enlaza); y el conteo de tests de la entrada 1.9.0 decía +6 cuando fueron +9.
- **Dos hallazgos reportados que resultaron FALSOS** (y por eso se verifica todo): "faltan los tags
  v1.10.x" — están, `git tag -l` los ordena lexicográficamente y `v1.10.0` cae antes de `v1.7.2`; y
  "el corpus de pathfinder es ADS + arXiv" — la versión publicada dice que es sólo ADS.
- Skills: `find-contradictions` 1.1.0 → **1.2.0**, `ingest-star` 1.12.2 → **1.13.0**, `ingest-topic`
  1.9.4 → **1.10.0**, `maintain` 1.9.0 → **1.10.0**, `query-corpus` y `test-hypothesis` 1.2.0 →
  **1.3.0**, `verify-citations` 1.4.0 → **1.4.1** (de la pasada anterior), `append-knowledge`
  1.1.0 → **1.2.0** (ídem).

## ✅ Framework 1.10.2 (2026-08-21) — auditoría de coherencia de la documentación

> Pedida por el usuario al cerrar las tandas 1-5: revisión profunda de la doc **técnica** (CLAUDE.md
> + los 9 skills) y **de uso** (README + docs/), cruzando cada afirmación contra el código. Dos
> auditorías en paralelo; **cada hallazgo se re-verificó a mano antes de aplicarlo**. 382 tests
> verdes, lint 0. 1.10.1 (`triage --migrate`) → **1.10.2** (patch: docs + textos de usuario).

- **⛔ El hallazgo grande: el fallback determinista de #60 no funcionaba.** `CLAUDE.md` mandaba a
  resolver los roll-ups Dataview con `grep -l 'stars:.*<nombre>' vault/wiki/papers/*.md`, pero
  `make_notes.fm()` serializa con `default_flow_style=False` → las listas van **en bloque** (`stars:`
  y abajo `- tau Cet`) y `grep` es orientado a líneas: **0 hits sobre un corpus donde el paper sí
  está**. El mecanismo que existe para que la audiencia-modelo no dependa de Obsidian **fabricaba
  una ausencia** — el modo de falla de #54 dentro del documento que lo prescribe. Reemplazado por un
  matcher con ámbito de campo (`awk`), **probado contra un fixture** con caso de control (un paper
  que menciona la estrella sólo en prosa y no debe matchear). Anotado en el issue #60, que sigue
  abierto por la variante cara.
- **`find-contradictions` era el único skill que usaba la tabla Dataview como mecanismo de
  recuperación** (los demás sólo dicen que "acumula sola") → ahora usa el matcher. Y le faltaba el
  caveat de la tanda 5: antes de declarar `real` un desacuerdo hay que mirar `pdf_source` (una
  diferencia numérica puede ser **de versión**, no entre fuentes), `corrections` (un corrigendum la
  explica) y `retracted` (no se disputa: se saca). Es el skill donde ese error hace más daño, porque
  de ahí salen las `disputes[]`. `find-contradictions` 1.0.2 → **1.1.0**.
- **Un bullet mío de la tanda 5 tenía el bug de #53:** "Papers sin `pdf_source`" colgaba de
  `maintain E`, declarada como "backlog **del lint**", pero el lint no emite esa categoría. Se marcó
  como migración one-shot en vez de agregar la categoría: `null` es un estado **legítimo** (fuente
  desconocida), así que una categoría permanente sería ruido puro.
- **Listas desalineadas:** las operaciones que cierran con `verify-citations` diferían entre
  `CLAUDE.md` (omitía append-knowledge y find-contradictions) y el skill (omitía `maintain`, cuyo
  invariante lo exige). `maintain E` no cubría 4 categorías que el lint sí emite (corpus truncado,
  correcciones, sin verificar, citas no verificables). El schema de `papers/` no documentaba
  `source_url`, `accessed` ni `pending_source`, que el código estampa.
- **Contradicción de orden dentro del mismo skill:** el paso de bookkeeping de los dos ingests
  mandaba a correr `lint` **antes** del verify, mientras su propio checklist y `CLAUDE.md` piden
  verify primero ("antes de lint/commit") — resolver una cita no-soportada cambia la prosa.
- **Doc de uso:** el README afirmaba que "cada ingest" deja registro (falso para off-ADS, que no
  corre `query_ads`); listaba conteos que no existen (**no hay `n_downloaded`**: `query_ads` corre
  antes que los fetchers y no puede saberlo); y su ejemplo de `--probe` decía "top por citas" del
  core justo donde el código garantiza listarlo **completo**. `docs/operacion.md` no nombraba
  `triage.py` (el único paso con juicio humano), ni la guardia de expansión y `--yes` (un primer
  ingest grande **re**-ingestado termina en un abort inexplicado — ojo: la guardia compara contra
  las notas ya ingestadas, así que en el **primer** ingest de un sujeto no dispara; eso se corrigió
  en la pasada siguiente), ni el token ADS entre lo que no viaja.
- **CWD (#59) completado:** los 13 headers `Uso:` de `scripts/` seguían en la convención vieja
  aunque los skills los declaran "fuente de verdad canónica", y `triage.py` **generaba** texto de
  usuario con ella. A pedido del usuario, el README además quedó **sin guiones largos** (reescribiendo
  cada frase; se conservan los del ejemplo de salida del programa, que es texto literal).
- **Pendiente conversado:** un disclaimer explícito sobre qué partes son capa LLM y cuánto se puede
  afirmar. Es decisión de fondo sobre lo que el proyecto promete → se define con el usuario.

## ✅ Framework 1.10.0 (2026-08-21) — tanda 5: #57, el `.txt` que puede ser otra versión del paper

> 379 tests verdes (+6), lint 0. `ALMAGESTO_VERSION` 1.9.0 → **1.10.0** (minor: campos nuevos de
> frontmatter, retrocompatibles — una nota sin `pdf_source` se comporta como antes).

- **#57** — `fetch_arxiv` baja de `export.arxiv.org` y guarda el PDF con el bibcode **publicado**;
  `make_notes` estampaba `fulltext_source` (`pdftotext|ocr|web`), que es el **método de extracción**
  y nunca el **documento de origen**; `fetch_pdf` sabía qué rama usó (`EPRINT_PDF`/`ADS_PDF`/
  `PUB_PDF`) y no lo persistía. Resultado: nada distinguía un `.txt` sacado del **eprint** de uno
  sacado de la versión publicada, y la palabra "preprint" no aparecía en ningún skill.
- **Por qué es el caveat que faltaba:** `verify-citations` promete que la cita textual son "las
  palabras reales del paper". Si el `.txt` salió de un **v1 pre-referato**, son las palabras de otra
  versión. Y el daño va en la dirección **menos obvia**: ante una discrepancia entre la nota (valor
  publicado, típicamente de NEA o del abstract de ADS) y el `.txt` (eprint), el protocolo manda
  *"bajar la afirmación a lo que dice la fuente"* → **se corrompe el valor publicado con el del
  preprint, y queda registrado como un hallazgo del chequeo**.
- **Señal primaria = verdad de disco:** la marca que arXiv estampa en cada página
  (`arXiv:2201.01234v3 [astro-ph.EP] …`), detectada en el `.txt`. No depende de que el fetcher haya
  dejado registro, así que **funciona retroactivamente sobre un corpus ya bajado** — el backfill es
  `python scripts/extract_fulltext.py <slug>`, sin re-bajar un solo PDF (`maintain E` lo documenta).
  Los fetchers además registran su rama (`build/<slug>/pdf_source.json`) para lo que la marca no
  distingue (`ads` vs `publisher`). La marca **gana** sobre el registro: un ADS_PDF que sirve el
  eprint *es* el eprint.
- **Campos nuevos:** `pdf_source: eprint|ads|publisher|web` + `eprint_version` (cuando se conoce).
  `null` significa **desconocido**, explícitamente **no** "publicado": afirmar de más justo acá
  sería peor que no saber. Van junto a `fulltext`/`fulltext_source` en el mismo estampado
  quirúrgico, que ya era idempotente.
- `verify-citations` 1.3.7 → **1.4.0** (caveat propio, hermano del de OCR: con `eprint`, una
  discrepancia **numérica** contra un valor publicado es candidata a **diferencia de versión**, no
  a cita rota → abrir el PDF publicado o marcarla; **no** "corregir" la nota). `maintain` 1.8.0 →
  **1.8.1** (backfill).
- **Sigue:** quedan #60 (materializar los roll-ups Dataview), #61/#62/#63 (método) y #65/#67
  (reestructura de skills, que el backlog manda hacer **después** de las tandas de contenido).

## ✅ Framework 1.9.0 (2026-08-21) — tanda 4: #51 + #64, el registro de ingesta sale de `build/`

> El grande de la revisión: la primera tanda que cambia dónde vive un dato. 373 tests verdes (+9),
> lint 0. `ALMAGESTO_VERSION` 1.8.1 → **1.9.0** (minor: archivo de config nuevo + línea nueva en la
> cabecera de fichas/concepts, retrocompatible y con migración transparente).

- **Diseño (elegido con el usuario):** un archivo por sujeto, `vault/config/registro/<slug>.yaml`,
  **versionado**, con dos secciones de dueños distintos — **`busqueda`** (la escribe `query_ads` al
  cerrar cada corrida) y **`decisiones`** (las escribe `triage.py --drop`). Regla que ordena todo:
  **`build/` guarda lo regenerable; el registro, lo que no lo es.**
- **#51** — los descartes del triage vivían en `build/<slug>/triage.json`, gitignored y documentado
  como "intermedio regenerable". No lo es: un `ads.json` se recupera pidiéndoselo de nuevo a ADS, el
  juicio sobre título+abstract no. En otra máquina (o tras limpiar `build/`) el triage **re-proponía
  todo lo descartado, sin el motivo**. La asimetría lo delataba: los candidatos **aceptados** ya
  persistían en config versionada (`extra_core`), los rechazados no. Ahora los dos lados de la
  decisión viajan en git.
- **#64** — no quedaba **registro de búsqueda**: la query de una estrella se armaba en `build_query`
  y se tiraba, los conteos vivían en `build/` y la fecha sólo como prosa en el `log`. Un consumidor
  de la ficha —el caso de uso central— no tenía cómo saber **sobre qué universo de papers afirma**,
  ni con qué lente se filtró. El registro guarda `fecha`, `query` efectiva, `rows`, `n_found`,
  `n_total`, `n_core`, `n_candidates`, `n_dropped`, `truncated` y `almagesto_version` (los ítems de
  PRISMA-S llevados a lo que esta cadena hace).
- **Puntero en la cabecera, no el bloque entero.** El registro completo queda en config y la
  ficha/concept lleva **una línea** estampada por `make_notes` (`> _Búsqueda 2026-08-21: 1837 → 198
  core · 42 sin juzgar · registro en config/registro/tau_ceti.yaml._`): el que abre la nota sabe
  fecha y universo sin abrir nada, y el detalle es resoluble. Cirugía idempotente de la familia
  `stamp_excluded`: nunca toca la prosa LLM, y si la cabecera está fuera del contrato no inventa
  nada (criterio de #48).
- **Muere el falso limpio del lint.** *Triage pendiente* y *corpus truncado* recorrían `build/*` y,
  sin `build/`, reportaban 0 **sin haber mirado nada**. Ahora caen al registro versionado y reportan
  el snapshot **con su fecha**, diciendo explícitamente que no es el conteo vigente. Es la
  dependencia dura que el backlog anotó (#55 y #64 después de #51) — queda saldada.
- **Migración transparente:** `cfg.load_decisiones` lee el registro **mergeado** con el
  `build/<slug>/triage.json` viejo (el registro gana ante el mismo bibcode), así una bóveda pre-1.9
  no re-propone lo ya descartado antes de su primer `--drop`, que es el que consolida. No hay paso
  manual.
- **Bug del harness encontrado en el camino:** el fixture `toy_vault` monkeypatchea una lista
  **explícita** de rutas, así que la constante nueva (`REGISTRO`) no estaba aislada y dos tests
  escribieron en el repo **real** (`vault/config/registro/*.yaml` aparecieron en `git status`).
  Se limpió y se agregó un test invariante: **toda constante de `lib_config` que cuelgue de `VAULT`
  tiene que estar en el `paths` del fixture**. Sin eso, el próximo que agregue una ruta repite la
  falla en silencio.
- Docs a los dos públicos (pedido del usuario: el template instruye agentes **y** personas):
  `CLAUDE.md` (layout, sección propia en Operaciones, Lint, secretos), `README.md` (qué deja un
  ingest), `docs/operacion.md` (tabla de archivos + **Portabilidad**, que es lo que este cambio
  cambia), y los skills `ingest-star` 1.11.2 → **1.12.0** y `maintain` 1.7.3 → **1.8.0** (sub-modos
  B/C/E: el registro se borra, se renombra y se resuelve con el sujeto).
- **Sigue la tanda 5:** **#57** (`pdf_source: eprint|ads|publisher` — verify puede "corregir" una
  nota hacia un preprint).

## ✅ Framework 1.8.1 (2026-08-21) — tanda 3: #55, el triage que se cerraba sin red

> 364 tests verdes (+2), lint 0. `ALMAGESTO_VERSION` 1.8.0 → **1.8.1** (patch: categoría de backlog
> nueva, sin schema ni cadena nuevos).

- **#55** — la compuerta de triage (#38) existe porque el chaining mete papers que **mencionan** al
  sujeto sin hablar de él (18% de precisión medida), y deja los dudosos en `candidates` de
  `build/<slug>/ads.json` **sin bajar**, esperando juicio. Pero el chequeo que gatea el commit no
  sabía que esa clave existía (`grep candidates scripts/lint.py` → nada): el único recordatorio era
  el stdout de `query_ads` y el mensaje final del orquestador, y los dos se pierden apenas scrollea
  la terminal. **El paso con más juicio de la operación era el único sin red de seguridad** — se
  podía cerrar un ingest con lint en 0, commit hecho y cientos de candidatos sin decidir.
- **Categoría nueva en el lint: backlog** (`Triage pendiente`), en el mismo barrido de
  `build/*/ads.json` que ya hacía el corpus truncado. `candidates` viene **neto** de decisiones —los
  descartados de `triage.json` no se re-proponen y los aceptados pasaron a `extra_core`, o sea que
  son core—, así que alcanza con contarlos; el hallazgo lleva los 3 primeros bibcodes y el comando
  exacto. Documentado en `maintain E`, en el paso 2c de `ingest-star` (1.11.1 → **1.11.2**) y en
  `CLAUDE.md`; `maintain` 1.7.2 → **1.7.3**.
- **⚠ Hueco residual declarado, no tapado:** `build/` es scratch **gitignored**, así que la
  categoría hereda el **falso limpio** — en una máquina que no corrió el ingest da 0 aunque haya
  candidatos sin juzgar. Es exactamente la dependencia que el backlog anotó (#55 después de #51) y
  la razón de que el skill siga mandando a dejar el conteo en el `log`, que es lo único que viaja.
  **"0 pendientes" hoy significa "0 acá".** Lo cierra **#51** (registro de curación en config
  versionada), que pasa a ser la próxima tanda.
- **Sigue la tanda 4:** **#51 + #64** — el grande: curación (descartes de triage) y búsqueda
  (provenance por sujeto) fuera de `build/`.

## ✅ Framework 1.8.0 (2026-08-21) — tanda 2: #52, la corrección que envejece un número ya extraído

> Tanda 2 del orden sugerido y **primera con scripts + tests**. 362 tests verdes (+3), lint 0.
> `ALMAGESTO_VERSION` 1.7.4 → **1.8.0** (minor: clave nueva de frontmatter + categoría nueva de
> lint, retrocompatible — una nota sin `corrections` se comporta igual que antes).

- **#52** — `check_retractions.py` ya **detectaba** las correcciones no-retractantes
  (`erratum` / `corrigendum` / `expression-of-concern`: la constante `SOFT` existe desde el
  principio) pero las **imprimía y las tiraba**: sin campo en el frontmatter, sin categoría en el
  lint, sin nada en el `log`. En un ingest de cientos de papers eso es stdout que nadie lee. El
  docstring incluso prometía que se "anotaba".
- **Por qué importa más que una retracción para esta bóveda:** una retracción invalida el paper
  entero (ya cubierto, bloqueante). Un **corrigendum corrige justo el valor que se destiló** a la
  ficha (P/K/e/m·sini) — el paper sigue siendo perfectamente citable y el número que le sacaste ya
  no es el suyo. Es el modo de falla más traicionero para una wiki cuyo contrato es
  "todo lo que afirma está respaldado por una fuente citable". Una EoC es literalmente el estado
  "esta fuente está en duda".
- **Cómo quedó** (mismo mecanismo quirúrgico que `retracted`, sin re-serializar el YAML):
  `crossref_retraction` devuelve las **entradas completas** de las correcciones (antes sólo el
  tipo, que era lo que forzaba a perderlas); `stamp_retraction` se generalizó a **`stamp_fields`**
  —ahora también borra los ítems `-` de una lista vieja, que es lo que necesita `corrections`— y
  `stamp_corrections` estampa `corrections: [{type, notice_doi, date, source}]`. Idempotente:
  re-estampa sólo si la lista cambió (una EoC posterior a un corrigendum reemplaza la lista entera,
  sin duplicar). Las dos señales **conviven** en el mismo frontmatter y la retracción sigue siendo
  la que gatea el exit 1.
- **Categoría nueva en el lint: backlog, NO bloqueante** — el paper sigue siendo citable; lo que hay
  que revisar son **los valores que se le extrajeron**. `maintain F` documenta la resolución (abrir
  el `notice_doi`, ver qué corrigió, comparar contra lo que la nota afirma citando ese `[[bibcode]]`;
  si toca un parámetro planetario puede terminar en una `disputes[]`). `maintain` 1.7.1 → **1.7.2**.
- **Al mergear en una instancia poblada:** el barrido completo (`python scripts/check_retractions.py`
  sin `--slug`, pasada periódica de `maintain F`) es el que estampa retroactivamente — hasta
  correrlo, el backlog figura en 0 porque el dato nunca se guardó.
- **Sigue la tanda 3:** **#55** (candidatos de triage sin juzgar, invisibles al lint — la otra
  categoría del mismo archivo).

## ✅ Framework 1.7.4 (2026-08-21) — tanda 1 del backlog #51–#67: coherencia barata (#53/#54/#58/#59)

> La tanda 1 del orden sugerido: **sólo docs/skills, sin tocar scripts**. Cuatro contradicciones o
> huecos entre documentos que ya se habían medido. 359 tests verdes, lint 0. `ALMAGESTO_VERSION`
> 1.7.3 → **1.7.4** (patch: ningún cambio de comportamiento en la cadena).

- **#53** — **los huérfanos bloquean, no son backlog.** `lint.py` los suma a `n_block` (exit 1)
  mientras `maintain E` los listaba como "no bloqueante, pero se acumula": un agente que seguía el
  skill dejaba el huérfano para después y se le trababa el cierre de la operación siguiente.
  Resuelto por la opción (a) del issue —un concepto sin links entrantes es **inalcanzable** desde la
  bóveda, así que bloquear es la intención correcta— alineando los docs al lint, no al revés: fuera
  el bullet de `maintain E`, en su lugar un aviso ⛔ de dónde se arregla (**en el cierre de la
  operación que lo creó**, citándolo desde la ficha/`index.md`/el hub si es un radio) y la
  `description` del skill + `CLAUDE.md` corregidas. `maintain` 1.7.0 → **1.7.1**.
- **#54** — la **convención de matcheo multi-columna** (#44/#46) blindaba la verificación pero no la
  **búsqueda**: vivía sólo en `verify-citations` y `find-contradictions`. Ahora está —como puntero,
  sin copiar la canónica— en los cuatro skills que greppean el `.txt` para decidir. **El modo de
  falla es peor acá:** en verify un falso negativo de matcheo degrada un veredicto visible; en
  `query-corpus`/`test-hypothesis` **fabrica una ausencia** ("el corpus no dice nada de X") que sale
  al chat como conclusión y no deja rastro de que fue un artefacto de grep. Regla operativa mínima:
  patrones cortos (3–6 palabras) o términos sueltos, reintento partiendo por guión de corte, y **un
  `grep` en 0 no es ausencia** hasta agotar la escalera (se suma al caveat pre-digital: el OCR pierde
  ~½ de las filas de tabla). En los ingests el mismo hueco tiene otra cara: en `ingest-star` el falso
  negativo se lee como "el paper no reporta ese parámetro" (que es lo que la extracción decide) y en
  el retro-tag 3b de `ingest-topic` un alias multi-palabra que no matchea es un paper que **queda sin
  conectar** al tema. `query-corpus` 1.1.1 → **1.2.0**, `test-hypothesis` 1.1.1 → **1.2.0**,
  `ingest-star` 1.11.0 → **1.11.1**, `ingest-topic` 1.9.1 → **1.9.2**.
- **#58** — `setup` invitaba a reescribir el objetivo más adelante ("afinás la lente") y **nunca
  nombraba** que sobre una bóveda poblada eso **re-clasifica el corpus entero**: el usuario se iba
  con el `objective.yaml` nuevo y el corte viejo, sin ninguna señal. El paso 7 y las §Notas ahora
  mandan al sub-modo **D de `maintain`**, empezando por el dry-run offline
  (`python scripts/query_ads.py --dry-run`), que es el que separa stubs de notas con extracción LLM.
  `setup` 1.1.0 → **1.2.0**.
- **#59** — **una sola convención de CWD: la raíz del repo** (la de `CLAUDE.md`). Los skills mezclaban
  "correr desde `scripts/`" + `python ingest_star.py` con `python scripts/lint.py` y greps a
  `vault/raw/…` en el **mismo archivo**: no rompía nada (los scripts resuelven el root por `__file__`)
  pero le costaba un turno a quien hacía `cd scripts` y seguía leyendo. Normalizadas 18 invocaciones
  en `maintain`/`ingest-star`/`ingest-topic`. `docs/operacion.md` conserva su bloque `cd scripts` para
  el listado de piezas sueltas, ahora con el comentario de que es el único con CWD propio.
- **Sigue la tanda 2:** **#52** (erratum/corrigendum/EoC — primer ítem con scripts + tests).

## ✅ Framework 1.7.3 (2026-08-21) — #68: el override manual que igual pasaba por la lente astro

> Reportado desde la instancia Almagesto-RV (tema `fastica`) con la verificación contra la API ya
> hecha. 359 tests verdes (+2), lint 0. `ALMAGESTO_VERSION` 1.7.2 → **1.7.3** (patch: el default de
> toda query de descubrimiento no cambia).

- **#68** — `extra_core` es **override del clasificador**, pero sólo esquivaba **un** filtro (la
  regex de `relevance.topics`). Arriba quedaba el `fq: database:astronomy` que `query_ads` aplicaba
  a **toda** query, incluida la de `fetch_bibcodes`: un bibcode **real** pero indexado fuera de
  `astronomy` (eprints de `math.ST` / `eess.SP`) no volvía, y la cadena lo reportaba como *"¿typo?"*.
  Ahora la lente es un **parámetro** (`query_ads(fq=ASTRO_FQ)`) y `fetch_bibcodes` pasa `fq=None`:
  donde el universo lo fijó el usuario con una lista de bibcodes no hay ruido que filtrar, el `fq`
  sólo puede **sacar de más**. Los demás callers son de descubrimiento y conservan la lente.
- **Dónde pegaba:** justo en el caso que la feature existe para cubrir — el **tema MIXTO** (#11),
  cuyo `extra_core` es textualmente "los papers del tema que sí tienen bibcode ADS", o sea métodos
  de otra disciplina al servicio del foco astro. En RV hubo que meter Zhang & Mondelli 2024
  (NeurIPS, `math.ST`) y SHASTA-PCA (`eess.SP`) por `sources:` con clave sintética, **perdiendo el
  bibcode ADS real como identidad de la nota** — la migración inversa de la que el propio
  `topics.yaml` había dejado constancia en julio.
- **El aviso mentía** y mandaba a buscar un typo inexistente. Con la búsqueda por bibcode ya sin
  `fq`, un faltante sí es bibcode mal escrito o registro renombrado, y el mensaje lo dice.
- `ingest-topic` 1.9.0 → **1.9.1**: el tema mixto documenta que un bibcode fuera de
  `database:astronomy` entra por `extra_core` y ya no hay que degradarlo a `sources:`.

## ✅ Framework 1.7.2 (2026-08-20) — #66 + #60(b): lo que faltaba para ampliar una ficha

> Segunda mitad de la misma tanda, elegida por el mismo criterio que #56: **qué protege la operación
> de ampliar una ficha**. Sólo docs/skills (sin scripts). 357 tests verdes, lint 0.
> `ALMAGESTO_VERSION` 1.7.1 → **1.7.2** (patch).

- **#66** — **checklist copiable** al inicio de `ingest-star` (9 pasos), `ingest-topic` (7),
  `append-knowledge` (5) y `maintain A`. Los pasos salteables —barrido full-text, triage,
  retro-tag, verify— no dejan rastro si se omiten, y el lint sólo tiene red para el último: la
  categoría "Sin verificar" **existe porque el paso se saltea**. El checklist ataca la causa.
  Skills: `ingest-star` 1.10.0 → **1.11.0**, `ingest-topic` 1.8.1 → **1.9.0**, `append-knowledge`
  1.0.3 → **1.1.0**, `maintain` 1.6.1 → **1.7.0**.
- **#60 (variante barata, issue ABIERTO)** — la **regla de poda** manda lo no-inlineado a la tabla
  `## Papers`, que es un bloque ```dataview```: el consumidor-modelo ve el **código de la query, no
  sus resultados**, y el plugin no está versionado — el mecanismo que justifica mantener la ficha
  compacta no era resoluble por quien la lee. Queda documentado el **fallback determinista**
  (`grep -l 'stars:.*<nombre>' vault/wiki/papers/*.md`) y el criterio: se descarga a un roll-up sólo
  si el fallback lo recupera. **#60 sigue abierto** por la variante (a) —materializar la tabla como
  markdown plano vía `make_notes --stamp-rollups`, con el mecanismo ya probado de `stamp_excluded`—
  que es la que lo resuelve de verdad.
- **Sigue pendiente y toca este flujo:** **#57** (`pdf_source: eprint` — verify puede "corregir" una
  nota hacia un preprint; necesita scripts+tests) y, de la cola vieja del pipeline, el **verify
  incremental (diff-mode)**, que es el que haría barato re-verificar sólo lo agregado.

## ✅ Framework 1.7.1 (2026-08-20) — #56: la verificación que quedó vieja y se lee como vigente

> Primera tanda del backlog #51–#67 (orden sugerido: era el ítem 3, adelantado porque protege la
> operación de **ampliar una ficha**). 357 tests verdes (+6), lint 0. `ALMAGESTO_VERSION` 1.7.0 →
> **1.7.1** (patch: categoría de backlog nueva en el lint, sin cambio de schema ni de cadena).

- **#56** — **detector de verificación stale** en `lint.py`. El bloque `## Verificación de citas`
  lleva fecha pero nada chequeaba que siguiera vigente: ampliar una nota (`append-knowledge`) o
  refrescarla (`maintain A`) deja la prosa nueva bajo un encabezado que **se lee como verificado**.
  Mismo modo de falla que #49/#50 —la nota no afirma falso, **afirma de menos**— aplicado a la
  garantía misma. La fecha del encabezado se compara contra la del último cambio del archivo por
  git; **un archivo sucio cuenta como cambiado hoy** (el lint corre ANTES del commit: mirar sólo
  `git log` no vería la edición que acaba de dejar el bloque atrasado). Un bloque **sin fecha** se
  marca igual. Fuera de un repo o sin git, el chequeo degrada a silencio. Aplica a **toda** nota con
  bloque, también fichas de estrella (la cobertura de verificación existente sólo mira
  queries/concepts). Cierra el ítem que `maintain E` sólo nombraba ("claims stale").
- **Hallazgo del sondeo a Almagesto-RV** (antes de dar el fix por bueno): 28 notas con bloque pero
  **39 encabezados fechados** — en la práctica las pasadas sucesivas se **appendean** en vez de
  reemplazar (`concepts/methods/ica-noise.md` tiene **11 bloques**), pese al "idempotente:
  reemplazar" del skill. Quedarse con la fecha del primer bloque las dejaba stale para siempre por
  más que se re-verificara → la vigencia la marca la fecha **máxima**. Documentado en el skill en
  vez de fingir que el reemplazo se cumple.
- Skills: `maintain` 1.6.0 → **1.6.1** (definición operativa del ítem), `verify-citations` 1.3.6 →
  **1.3.7** (la fecha del encabezado es portante + la regla de multi-bloque), `append-knowledge`
  1.0.2 → **1.0.3** (el paso 5 manda a re-fechar).
- **Al mergear en una instancia poblada**, esperar backlog retroactivo: toda nota editada después de
  su último verify aparece listada de una. Es deuda real, no ruido — se resuelve por `maintain E`.

## ✅ Framework 1.7.0 (2026-08-19) — tanda #49/#50: lo que el verify no miraba y el rescate de PDFs

> Disparada por la primera corrida real sobre una ficha grande (17 fuentes, ~110 pares) en
> Almagesto-RV. 351 tests verdes (+5), lint 0. `ALMAGESTO_VERSION` 1.6.3 → **1.6.4** (#49, patch:
> sólo skills) → **1.7.0** (#50, minor: claves nuevas en `missing_pdf.json` + umbral de legibilidad
> por página, retrocompatible).

- **#49** — `verify-citations` 1.3.5 → 1.3.6, dos agujeros medidos: (a) **herencia de cita en tablas
  y listas** — la fila hereda el `[[bibcode]]` del ámbito que la introduce (caption → párrafo →
  encabezado) y entra al fan-out como par propio; antes no se formaba el par y la tabla entera se
  cerraba sin chequear (medido: **46 de 64 filas, 72%**). (b) **Completitud de transcripciones** —
  campo `completitud` + addendum de prompt: una tabla transcrita sin un solo error pero **truncada**
  volvía 100% soportada (medido: 14 registros correctos sobre una tabla de **21 filas**). Es un modo
  de falla distinto del *grounding gap*: la nota no afirma falso, **afirma de menos**.
- **#50** — **cascada de rescate de PDFs** escrita y canónica en `## Notas` de `ingest-star`
  (Messenger abierto → página de papers del instrumento → mirrors → tablas del CDN → derivar al
  usuario), con la excepción **aanda.org / DataDome** (no gastar intentos). El resolver de ADS falló
  en **5 de 17** en un ingest real; 4 se recuperaron por esas ramas. `fetch_pdf` imprime el
  **bibstem** de cada fallo con la rama sugerida (`rescue_hint`) y la persiste en el residuo.
  Además `extract_fulltext.is_legible` suma **densidad por página** (`LEGIBLE_MIN_CHARS_PAGE=200`):
  el escaneo cuya única capa de texto es la **marca de agua** del bibcode pasaba el mínimo global y
  se contaba como extraído (medido: Baranne+1996, 378 bytes en ~20 páginas) — ahora cae al OCR y el
  lint lo surface retroactivamente en cualquier bóveda ya ingestada.
- Hueco conocido del historial: las tandas **1.6.2** (#46/#47) y **1.6.3** (#48) nunca dejaron
  entrada acá (sólo commit de fix + bump). Backfillear si se quiere el registro completo.

## ✅ Framework 1.11.0 (2026-08-21) — #69: la cabecera que nunca se backfilleó y el no-op silencioso

> Disparado por una medición de la instancia Almagesto-RV al actualizar. 390 tests verdes (+8),
> lint 0. `ALMAGESTO_VERSION` 1.10.3 → **1.11.0** (minor: flag nuevo + categoría de lint nueva).

- **Lo que se midió** (25 fichas + conceptos de una bóveda real): **21 sin** el blockquote ⚠ "Capa
  LLM — revisar antes de citar" (84%) y **22 sin** la línea `> _Generado con Almagesto v…_`, con
  **correlación perfecta** entre ambas ausencias. El aviso se escribe **sólo al crear la nota** y
  nada lo backfilleaba.
- **El defecto que importaba no era el aviso, era el silencio.** Esa línea del generador es el ancla
  de **todos** los estampadores de cabecera, que se niegan a actuar sin ella (criterio de #48, "no
  inventamos") y devuelven `False` sin decir nada. Consecuencia medida: el puntero de búsqueda de
  **#64, entregado horas antes, no aterrizaba en 22 de 25 notas de esa bóveda** y no había ninguna
  señal. Un no-op silencioso se lee como éxito: es "afirmar de menos" del lado del tooling.
- **Por qué no alcanzaba con lo que ya había:** `make_notes` sin `--force` no toca el cuerpo (así que
  re-correr la cadena no cambia nada) y con `--force` reescribe la nota entera, **pisando la síntesis
  LLM**, que es el trabajo caro. Las dos opciones eran "no pasa nada" o "perdés la ficha".
- **`stamp_header` + `--restamp-headers`:** ancla en el `# H1` (que toda nota tiene) en vez de en la
  línea que falta, inserta el aviso y la línea del generador, y **no toca una línea de la prosa** (el
  blockquote que esas notas ya tienen es texto del LLM y sobrevive debajo). **La versión no se
  inventa: sale del `generator` del propio frontmatter**, que registra con qué versión se creó la
  nota; si ni eso hay, la línea va sin versión. Aporte del usuario: fue quien señaló que la versión
  ya estaba en el frontmatter, lo que eliminó la única objeción de diseño que quedaba.
- **Categoría de lint nueva** (backlog): ficha/concepto sin el ancla → "los estampadores de cabecera
  no pueden actuar". Es lo que vuelve visible el estado y lo que evita que el **próximo** estampador
  de cabecera repita el silencio. Va primero por diseño: el backfill tapa el agujero de hoy, la
  categoría protege de los de mañana.
- **El texto del aviso pasó a ser constante única** (`LLM_DISCLAIMER`), porque ahora lo escriben dos
  caminos (creación y backfill) y si divergen el backfill estampa algo distinto de lo que el README
  promete. Mismo criterio que viene fallando toda la jornada cuando algo se escribe dos veces.
- **Contexto:** el README afirmaba "la cabecera de cada ficha avisa que la prosa es capa LLM" y una
  bóveda real lo contradecía en el 84% de sus notas; se acotó en `d5713cd` mientras esto no existía.
  Con el backfill corrido, la afirmación general vuelve a ser cierta para esa bóveda.

## Backlog — keywords del paper como capa de linkeo (2026-08-22, issue #92)

> Sale de una pregunta del usuario mientras corría la tanda 2: *"¿esas keywords las suponés vos? ¿no
> deberían usarse primero las del paper?"*. Tenía razón, y el hallazgo se verificó en el código antes
> de abrir el issue.

**El estado real:** las keywords propias de cada paper **ya llegan** en toda request a ADS
(`query_ads.py:108`), `classify()` las usa **apelmazadas** con título+abstract en un blob lowercased
para la regex (`:183` — se leen como *más texto*, no como vocabulario), quedan en
`build/<slug>/ads.json` (`:447`) y **`make_notes` no las menciona**: no entran a la nota y mueren con
el scratch.

**Por qué importa más de lo que parece.** Todo lo que hoy relaciona notas es **supuesto**: `topics`
sale de la regex de *esta* instancia (dos bóvedas no son comparables), y `methods`/`thesis_links`/
`aliases` los escribe el LLM. Las keywords son el **único vocabulario que no inventamos** y caerían
del lado **auditable** de la línea que el README promete, junto a `doi` y `bibstem`. El uso primario
que marcó el usuario es **linkear conceptos**: dos papers que comparten una keyword asignada al
publicar tienen una relación *declarada por la fuente*, no una que el LLM decidió escribir.

**Y destraba, por la puerta de atrás, lo que estaba bloqueado por licencia.** El vocabulario de
AstroMLab 5 (backlog de la revisión 2026-07-03, ítem 5) sigue sin `LICENSE` — re-chequeado
**2026-08-22**: GitHub API `license: null`, último push 2025-11-15. Las keywords que la revista
asigna al publicar están estandarizadas y llegan por la API que ya usamos: sin dependencia nueva ni
problema de licencia.

**Decidido en la conversación:** la **capa LLM encima** (normalizar variantes, agrupar, mapear a los
conceptos de la bóveda) queda **fuera del primer issue**, a propósito. Primero la capa determinista;
sin ella la capa LLM no tiene de dónde partir y volvemos a un vocabulario supuesto.

**A verificar antes de implementar** (en el issue): si ADS expone el **esquema** de cada keyword
(autor vs revista/UAT — es lo que permitiría separar la parte controlada de la libre); la cobertura
real del corpus (los pre-digitales probablemente no traen, mismo sesgo que #86); y si el campo nuevo
pide backfill quirúrgico o vale sólo para notas nuevas.

## Backlog de framework — sesión de diseño 2026-08-22 (issues #70–#81)

> Sesión pedida por el usuario: cómo se extrae la información de un paper y cómo se sintetiza entre
> papers para armar la ficha. Doce hallazgos, abiertos como **#70–#81**. La referencia narrativa del
> flujo quedó en `docs/ingesta.md` (embudo de selección, las dos ingestas, campo por campo de la
> ficha). Acá queda lo que GitHub no guarda: **orden, dependencias e ideas descartadas**.

### El hallazgo de fondo
La cadena tiene red para casi todo paso salteable (#55 triage, #56 verify stale, #69 cabecera), pero
**el paso de síntesis —el más caro y el que define la calidad de la ficha— no tiene ninguna**, y su
modo de falla es **omisión**, que no deja rastro. `verify-citations` valida cada afirmación contra su
fuente, no que la síntesis represente al conjunto: una ficha sintetizada desde 3 papers de 40 vuelve
100% soportada. De ahí salen #72 (el paso de contraste que falta), #75 (la red) y #73 (el rol del
paper, sin el cual "contrastar" no está definido).

### Orden sugerido de tandas
1. **Barato y sin dependencias — TANDA CERRADA (1.11.1–1.13.0):** ~~**#76**~~ ✅ (el stub de paper no
   ramifica por sujeto — el cuerpo, los seeds ya ramifican), ~~**#79** puntos 1-2~~ ✅ (ranking del
   `--sweep` por citas/año; segunda pasada por fecha al truncar), ~~**#81**~~ ✅ (registrar el rechazo
   de una fuente declarada).
2. **Procedencia — TANDA CERRADA (1.14.0–1.16.0):** ~~**#70**~~ ✅ (frontmatter = espejo puro de NEA;
   corregido el comentario que instruía lo contrario y re-apuntado el backlog de `P_rot`) →
   ~~**#75**~~ ✅ (la red "extraído pero no sintetizado") → ~~**#73**~~ ✅ (campo `role`, apoyado en
   el stub de #76).
3. **Síntesis — TANDA CERRADA (1.17.0–1.18.0):** ~~**#72**~~ ✅ (inventario por eje, **sin** columna
   "valor adoptado") y ~~**#74**~~ ✅ (régimen explícito en conceptos — quedó cableado al destino de
   los `aparente`, que **#63** todavía tiene que persistir del lado del barrido).
4. **Caro — migración de corpus — TANDA CERRADA (1.19.0):** ~~**#71**~~ ✅ (`disputes[]` con
   posiciones explícitas y a nivel nota). Era el único que toca instancias ya ingestadas: se
   resolvió con `--migrate-disputes` (un solo uso) **más** un chequeo bloqueante que detecta el
   schema viejo — sin capa de compatibilidad, por decisión explícita del usuario.
5. **Descubrimiento:** **#77** (OpenAlex escribiendo el mismo `ads.json`) + **#78** (el tema mixto
   deja de ser off-ADS-first: el eje pasa a ser *motor de descubrimiento × fuentes declaradas*).
   Recién con eso cerrado tiene sentido **#79** punto 4 (documentar la neutralidad a citas).
6. **Libros:** **#80** (`pending` no distingue fallo de adquisición; la unidad de cita del verify no
   escala a un documento largo; declarar el recorte de un fragmento).

### Dependencias duras
- **#73 antes de #72 y #74**: sin rol (fundacional / aplicación / árbitro) la operación de contraste
  no está definida — fundacional↔aplicación **no es contraste, es instanciación**, y tratarlo como
  desacuerdo fabrica disputas falsas.
- **#75 junto con #72**: un paso más en el checklist se saltea igual que 2b/2c/5b; sin la red, se
  evapora.
- **#70 antes de #71**: primero se decide que el frontmatter es espejo de NEA, después se generaliza
  la estructura de disputas.

### Recorrido paso a paso del embudo (2026-08-22, issues #82–#91)
Segunda mitad de la sesión: se recorrió la ingesta escalón por escalón, de la resolución del sujeto
al cierre del lint. Diez issues más, y **dos patrones transversales** que valen más que los issues
sueltos.

**Patrón A — el motivo se registra en unos escalones y no en otros (#86, #88, #89).** Mecánicamente
son tres cosas distintas, pero las tres escriben al mismo archivo:
`vault/config/registro/<slug>.yaml`. Hoy responde *"con qué query y qué lente se buscó"*; le faltan
cuatro hechos: si se corrió el barrido full-text (#88), qué se aceptó y por qué (#89), cuántos
registros se juzgaron sin abstract (#86) y qué core quedaron sin PDF y por qué rama se abandonó
(#90 — que además pide estampar `pending_source` en la nota, para que el lint deje de confundir
"falta leerlo" con "falta la fuente"). **Hacerlos por separado son cuatro migraciones del mismo
archivo**, cada una con su compatibilidad hacia atrás; como tanda es un solo cambio de schema. El
criterio que los unifica es el de #51: *`build/` guarda lo regenerable, el registro guarda lo que no
lo es* — y los tres hechos que faltan son irrecuperables.

**Patrón B — el orden por citas, cuatro ocurrencias (#79).** Truncamiento, ranking del `--sweep`,
apéndice de excluidos y listado del triage. Se parte en dos: el truncamiento es **server-side** (el
`sort` va en la request a ADS → sólo lo arregla la segunda pasada por fecha); las otras tres son
`sort(key=…)` inline en archivos distintos y piden **una sola función de orden compartida**, para que
la política no diverja. *(1.12.0: hechas la server-side y el `--sweep`; la función compartida ya vive
en `lib_config.sort_by_citation_rate` y faltan migrar el apéndice —que quiere dos bloques, no
citas/año— y el listado del triage.)* Cuidado con el reemplazo: citas/año también sesga (un paper de dos meses con
1 cita tiene tasa enorme); el estándar normaliza contra la cohorte del año. Donde la lista es corta,
dos bloques (top citas + top reciente) en vez de un score compuesto.

**Patrón C — la garantía existe, el rastro de que se cumplió no.** Es el mismo patrón de #55 (triage)
y #56 (verify stale), y reapareció cuatro veces más: el sweep corre y no queda registro (#88), se
acepta un paper y no queda el motivo (#89), no se consigue un PDF y la nota no lo dice (#90), y
—el más grave— `verify-citations` deja una falla **sin resolver** bajo un encabezado que certifica lo
contrario, porque el lint mira que el bloque exista y esté fresco pero **nunca qué dice** (#91). Ese
último es frontera dura: una afirmación que la bóveda hace y su propia fuente no respalda. El fix es
barato porque la convención del skill ya codifica la resolución con flecha (`no-soportada→corregida`),
así que "sin resolver" es greppable.

**Decisión de schema (2026-08-22): sacar `relevance` de las notas de paper.** Siempre vale `high`
(la rama ADS lo pone así para todo core y `make_notes` sin `--all` sólo escribe core; la rama off-ADS
lo hardcodea). La existencia de la nota ya significa core; el caso raro de `--all` lleva
`core: false` explícito. Cambia el disparador de `lint.py:346` y necesita tolerancia hacia atrás +
backfill quirúrgico. Queda dentro de #87, que es donde va la señal que sí informa.

**Lo que el recorrido confirmó del diseño (no son defectos):** la lente es configurable y se valida
contra papers reales; el chaining corre en las dos direcciones, así que tiene camino de recencia; el
`--drop` **exige** motivo; el apéndice de excluidos linkea a ADS con el motivo real de exclusión.

### Ideas evaluadas y NO abiertas como issue
- **Google Scholar como motor de descubrimiento** — descartado **por reproducibilidad, no por
  precio**: sin API pública, sin IDs estables y con resultados no deterministas, el `busqueda` del
  registro no podría persistir una query re-corrible. OpenAlex y Semantic Scholar sí.
- **Regla de precedencia declarativa en `objective.yaml`** (tie-breakers tipo recencia > tamaño de
  muestra) — descartada dos veces: el criterio correcto depende del parámetro, no de la bóveda; y
  sobre todo **adoptar un valor es decidir por el consumidor**, que rompe el flujo unidireccional de
  la regla #0. Lo correcto es no adoptar: reportar el estado de la literatura con sus fuentes.
- **Acotar la lente a un sujeto** (`facetas: [activity, rv]` en `stars.yaml`) — abierto como #84 y
  **cerrado en la misma sesión**: la necesidad ya está cubierta instanciando **otra bóveda** (es lo
  que hay en la práctica: dos instancias con `objective.yaml` propios, independientes por
  `merge=ours`), y esa vía **preserva** la propiedad de la que dependen la comparabilidad entre
  fichas y la matriz método×estrella —"core" significa una sola cosa dentro de una bóveda— en vez de
  agujerearla con excepciones por sujeto. El volumen, que era el otro argumento, ya lo corta
  `relevance.require` de forma global y más fuerte (850 → 198 core en AU Mic, contra 928 → 762
  podando regex). Lo reabriría: querer, *dentro de un mismo foco*, una estrella bajo un recorte más
  angosto, con `extra_core`/`--drop` volviéndose tediosos para sostenerlo.
- **Un tercer tipo de sujeto, "aplicación de método a astro"** — descartado: colapsa con el método.
  El destino es la misma nota con el mismo contrato *implementation-ready*, y si crece hay hub/radio.
  La distinción fundacional/aplicación es **rol del paper**, no tipo de sujeto (#73).

## Backlog — longitud y estructura del README (anotado 2026-08-21)

Pedido del usuario: revisarlo la próxima sesión, probablemente está largo. Medido hoy: **336 líneas,
3409 palabras**, repartidas así (líneas por sección, de mayor a menor):

| Sección | Líneas |
|---|---:|
| La capa LLM | 81 |
| Instanciar (crear tu bóveda) | 46 |
| De un objetivo a una ficha | 40 |
| La bóveda en Obsidian | 32 |
| Dónde encaja (related work) | 20 |
| Skills del agente | 16 |
| Verify: todo claim tiene fuente | 10 |
| Para seguir | 10 |

Lo que conviene mirar cuando se retome, sin decidirlo ahora:
- **La capa LLM** es hoy la sección más larga del README, más del doble que la que explica qué hace
  el proyecto. Se escribió de una y no se podó. Candidata natural a quedar más corta arriba (tabla de
  quién decide cada cosa + el párrafo del límite) y mandar el detalle de mitigaciones a `docs/`, que
  es donde ya vive lo operativo. **Cuidado al podar:** la sección existe para no sobrevender, así que
  recortarla hasta que quede sólo el título y una promesa sería justamente lo contrario de su punto.
- **Instanciar** (46) mezcla el camino recomendado con dos variantes; parte podría ir a
  `docs/operacion.md`, que ya tiene la sección de portabilidad y upstream.
- **Verify** (10) quedó chica y ahora se solapa con "La capa LLM", que la explica mejor y más largo.
  O se fusionan, o Verify queda como puntero.
- Chequear si sigue habiendo una lectura de 2 minutos posible: alguien que entra al repo debería
  entender qué es esto antes de la primera sección larga.

## Backlog — capturas y assets del README (anotado 2026-08-21)

Las tres capturas de Obsidian son del **2026-07-25** y el framework cambió bastante desde entonces.
Revisadas una por una; qué le falta a cada una, en orden de urgencia:

1. **`docs/assets/obsidian-concepto.png` — la más urgente, porque contradice al propio README.** El
   blockquote de cabecera de esa nota es prosa del LLM y **no** trae el disclaimer
   ⚠ *"Capa LLM — revisar antes de citar"* que `make_notes` estampa hoy. La sección nueva
   *La capa LLM* afirma que "la cabecera de cada ficha avisa que la prosa es capa LLM": quien mire
   la captura ve lo contrario. Re-sacarla de una nota generada con el template actual.
2. **`docs/assets/obsidian-ficha.png` — el panel de propiedades ya NO es el schema vigente**
   (revisado 2026-08-22, contra la captura misma; la nota de arriba decía que "seguía siendo
   correcto" y era cierto hasta 1.13.0). Le falta `disputes` a nivel nota (#71 — el README enumeraba
   ese campo como si se viera) y sus `planets[]` traen `msini_earth`, no `mass_earth`; muestra
   además campos que no son del schema (`feh`, `mass_msun`, `logrhk`), legítimos como extras de
   instancia pero confusos en la captura de referencia del template. Y sigue faltando lo que ya
   faltaba: el cuerpo queda fuera de cuadro, así que no se ve la línea `> _Búsqueda …_` que estampa
   `make_notes` desde 1.9.0. Al re-sacarla, encuadrar para que entre esa línea y elegir una ficha
   **con una disputa tagueada**: es lo que el texto de al lado promete.
3. **`docs/assets/obsidian-graph.png`** — nada factualmente falso, pero es una foto de un corpus de
   3 estrellas; la instancia creció desde julio.
4. **`docs/assets/demo-animated.svg`** (regenerable con `make_demo.py`) — el guion no muestra la
   **compuerta de triage (2c)**, que hoy es el paso con más juicio de la operación y que el propio
   mensaje de cierre del orquestador nombra; tampoco el registro de búsqueda. Los comandos que
   muestra ya están en la convención de CWD correcta.

Al re-sacarlas: son de instancias del usuario, así que conviene elegir notas que no expongan nada que
no quiera publicar, y encuadrar para que se vea lo que el texto de al lado promete.

## Confirmación empírica desde una instancia (2026-08-21) — por qué el bug del roll-up importaba

Reporte del update de Almagesto-RV a 1.10.3, que **mide** lo que la corrección de 1.10.3 argumentaba:
en esa bóveda hay **2 `stars`, 116 `methods` y 65 `thesis_links` en flow style**. O sea que el `awk`
de 1.10.2 —el que perdía flow style— habría dejado invisible la mayor parte de los métodos del
corpus. La receta con `split_fm` no era una preferencia de estilo.

Hallazgo propio de esa instancia con lectura de framework: al rehacer los roll-ups bien, la
procedencia de fuentes de dos conceptos **estaba subestimada** (13 de 21 `eprint` donde se había
reportado 9 de 17; 13 de 24 donde se había reportado 6 de 17), porque la medición se había hecho
sobre lo **citado** y el roll-up por `thesis_links` es más grande. Es "afirmar de menos" otra vez, y
sugiere una regla que hoy no está escrita en ningún skill: **cuando se reporta una medición sobre las
fuentes de una nota, hay que declarar la población** (¿lo citado? ¿el roll-up completo?). Candidato a
issue si vuelve a aparecer.

## Backlog de framework — revisión profunda de skills 2026-08-19 (issues #51–#67)

> Revisión pedida por el usuario: lectura completa de los 9 skills + cross-check contra
> `scripts/`/`lint.py`/`CLAUDE.md`/`docs/` + búsqueda de sistemas similares (guía oficial de
> authoring de skills, PaperQA2/OpenScholar, DeepSciVerify, MiniCheck, PRISMA-S). Informe con la
> evidencia archivo:línea de cada hallazgo: `outputs/revision-skills-2026-08-19.md` (**gitignored y
> regenerable** — lo durable es esta sección). Los 17 hallazgos están abiertos como issues #51–#67;
> acá queda lo que GitHub no guarda: **orden, dependencias e ideas descartadas como issue**.

### Orden sugerido de tandas
1. **Coherencia barata** (docs/skills, sin scripts): **#53** (huérfanos: backlog en `maintain` vs
   bloqueantes en el lint), **#54** (la convención de matcheo multi-columna no llega a
   `query-corpus`/`test-hypothesis` — ahí un falso negativo **fabrica una ausencia**), **#58**
   (`setup` no manda a `maintain D`), **#59** (CWD mezclado en el mismo skill).
2. **#52** — correcciones no-retractantes (erratum/corrigendum/EoC) hoy se imprimen y se tiran:
   `corrections:` en frontmatter + categoría de lint + `maintain F`. Patrón ya existente
   (`retracted`), scripts + tests.
3. ~~**#56**~~ ✅ **hecho en 1.7.1** (ver arriba) + **#55** — la otra categoría de lint del mismo
   archivo: **triage pendiente** sin resolver.
4. **#51 + #64** — el grande: registro de **curación** (descartes de triage → config versionada) y
   de **búsqueda** (bloque de provenance por sujeto: fecha/query/conteos/rows/truncated/versión).
   Destraba el **falso limpio** del lint en una máquina sin `build/`.
5. **#57** — provenance del PDF (`pdf_source: eprint|ads|publisher`) + caveat de versión en
   `verify-citations`.
6. **#65 + ~~#66~~ ✅ (hecho en 1.7.2) + #67** — reestructura de skills: `reference/` (progressive
   disclosure) y deduplicar la cadena ADS entre `ingest-star` e `ingest-topic`.
7. **#60** — roll-ups Dataview invisibles al consumidor-modelo: la variante barata (documentar el
   fallback `grep`) se hizo en 1.7.2; **queda la cara**: materializar la tabla con
   `make_notes --stamp-rollups`.
8. **#62, #61, #63** — método: presupuesto de extracción cuando el core es enorme, veredicto
   "el corpus calla" + declaración de sesgo en `test-hypothesis`, persistencia de los `aparente` de
   `find-contradictions`.

**Dependencias duras:** #55 y #64 heredan el falso limpio mientras el registro viva en `build/` →
después de #51. #65/#67 **después** de las tandas de contenido (si no, se reescriben los skills dos
veces).

### Ideas evaluadas y NO abiertas como issue (mejoras, no defectos)
- **Localizador determinista de la cita** — escalado de evidencia estilo *DeepSciVerify*
  (arXiv:2605.27710: resuelven **67%** de los casos sin recuperar full-text). Un script correría la
  escalera #44/#46 y devolvería las líneas candidatas; el subagente sólo **juzga**. Ataca el costo
  del fan-out, que #49 multiplicó al meter las filas de tabla. ⚠ **Choca con la decisión de #44**
  ("la escalera NO se re-implementa en `scripts/`: viviría en dos lugares que pueden divergir") —
  se resolvería invirtiendo la autoridad: el script pasa a ser **la** implementación (ya tiene
  invariantes en `tests/test_multicolumn_matching.py`) y el skill queda como puntero. Gate
  obligatorio: el auto-benchmark antes/después.
- **Verificador barato como pre-filtro** — *MiniCheck* (EMNLP 2024): nivel GPT-4 en fact-checking
  contra documento de anclaje a **400× menos costo** (74.7% balanced accuracy en LLM-AggreFact). No
  reemplaza el veredicto (no produce cita textual + nº de línea, que es el contrato), pero sirve
  para **ordenar** los pares por probabilidad de error o como **segunda opinión** contra el modo de
  falla ya medido (ablandar a `parcial` un claim genérico). Costo real: dependencia de inferencia
  local (torch/HF), hoy ajena a `requirements.txt` → experimento medido, no parte de la cadena.
- **Descubrimiento para el modo off-ADS** — OpenAlex / Semantic Scholar / Crossref exponen abstract,
  grafo de citas y links de acceso abierto para la bibliografía no-astro. Un `query_openalex.py` que
  escriba el mismo `ads.json` (mismo clasificador `relevance.topics`) le daría a los temas de método
  el **descubrimiento automático** que hoy sólo tienen los astro, en vez de fuentes declaradas a
  mano. Verificar términos y límites vigentes de cada API antes de codificar.
- **Priorizar la extracción con metadata de calidad** — *PaperQA2* adjunta a cada fragmento citas,
  venue y estado de retracción. Insumo directo de #62 (ordenar qué se extrae cuando hay 850 core).
- **Subirle el perfil a `find-contradictions`** — la literatura de RAG con fuentes en conflicto
  reporta que ~25% de las preguntas abiertas recuperan evidencia contradictoria y que los LLM la
  **ignoran con exceso de confianza**. Hoy la auditoría es opt-in y nada la dispara; podría
  proponerse sola al cerrar un ingest grande.

### Lo que la revisión NO tocaría
División scripts/LLM, frontera dura (regla #0), diseño de la compuerta de triage, dry-run de
`maintain D` y el auto-benchmark del verificador. Comparado con lo que hay afuera (PaperQA2,
OpenScholar, Elicit y compañía), ninguno persiste un artefacto curado con verificación
afirmación-por-afirmación **y un número medido de su propia tasa de error**.

## ✅ Framework 1.6.1 (2026-08-17) — tanda #44/#45: estrategia de matcheo en `.txt` multi-columna

> Tanda **de docs/skills** (sin cambio de scripts), hermana de #29: el `.txt` de `pdftotext -layout`
> no es un stream de texto plano y los skills que greppean citas tenían el caveat pero no el "cómo
> buscar". Medido en Almagesto-RV: 472/644 `.txt` (73%) multi-columna. 328 tests verdes.
> `ALMAGESTO_VERSION` 1.6.0 → **1.6.1** (patch: sólo prescripción en skills, retrocompatible).

- **#44** — **`verify-citations` prescribe CÓMO buscar** (1.3.3 → 1.3.4): escalera de acortamiento
  (oración completa → fragmento distintivo contenido en una línea física; el largo útil depende del
  ancho de columna, se acorta hasta encontrar — un paper a una columna sigue matcheando la frase
  entera), de-hifenado en el corte de línea, y recién agotado eso se considera artefacto de
  extracción. **Prohibido normalizar espacios sobre el archivo entero** (empalma columna 1 con
  columna 2 → puede hacer pasar como soportada una afirmación inventada — el modo peligroso, hasta
  ahora sin documentar). Medido: 9/24 pares (~38%) de falso negativo con la oración completa, 24/24
  con fragmento corto; 33/68 citas de bloques existentes no localizables con 6 palabras y 7/7
  muestreadas aparecen con 3–5 → el corpus está sano, fallaba el patrón. La regla viaja también en
  el prompt sugerido del subagente.
- **#45** — **`find-contradictions` arrastra las convenciones** (1.0.0 → 1.0.1): puntero explícito
  a #29/#44 (la convención canónica queda en verify-citations, sin copia), regla condensada en el
  prompt del subagente aplicada a CADA archivo, y `no-concluyente` sólo agotada la escalera en
  ambos lados. Acá el riesgo se amplifica: el par exige cita de dos fulltexts (~94% de chance de
  que al menos uno sea multi-columna) y un falso negativo colapsaba el veredicto a `no-concluyente`
  sobre una disputa real.
- Addendum (2026-08-17): la medición de prevalencia quedó como **diagnóstico**, no test de regresión
  — el template no trae corpus, un test así no podría correr acá. `scripts/measure_layout.py`
  (aportado por el usuario) mide cualquier bóveda: archivos multi-columna (heurística: >30% de líneas
  útiles con hueco interno de 8+ espacios), líneas con canaleta (donde el empalme col.1→col.2 es
  alcanzable) y cortes por guión; `--json`, `--por-slug`, `--listar N`. Medido en Almagesto-RV: 73%
  de archivos multi-columna global y 46% de líneas útiles con canaleta, pero el peso depende del
  origen de la bibliografía — slugs astro 62–86%, el off-ADS de estadística/ML (fastica) 38%: una
  bóveda de puros métodos necesita menos la regla. La escalera NO se re-implementa en `scripts/`
  (viviría en dos lugares que pueden divergir).

## ✅ Framework 1.6.0 (2026-08-15) — tanda #29/#42/#43: follow-ups de la primera corrida real

> Tanda **correctiva**, disparada por la primera corrida real de v1.5.0 (Almagesto-RV, ε Eri): dos
> promesas de la cadena que no se cumplían (la persistencia de la compuerta de triage y la marca de
> truncamiento del rescate por glifo) y una ambigüedad del verify que fabricaba citas rotas. 328
> tests verdes, lint 0. `ALMAGESTO_VERSION` 1.5.0 → **1.6.0** (minor: clave `truncated_glyph` nueva
> en `ads.json` + marcador ◆ en triage, retrocompatible).

- **#42** — **`extra_core` se mergea ANTES del chaining**: el bloque corría después, así que los
  bibcodes curados no estaban en `recs` al armar el dedup y la cola de triage **re-proponía papers
  ya aceptados** (medido: 14 de 50 `extra_core` de ε Eri de vuelta como candidatos — core y
  candidato a la vez). La persistencia de la compuerta ahora vale para los dos lados de la decisión
  y los curados siembran el grafo. Además `triage.py` marca `◆` los candidatos que **ya tienen
  nota** en la bóveda (entraron por otro slug): no se filtran, se despachan rápido.
- **#43** — **el truncamiento del superset del rescate por glifo se marca** (antes el warning decía
  "queda marcado en ads.json" y no marcaba nada: la marca `truncated` es de la query directa). El
  corte top-por-citas pasa **antes** del filtro por glifo —donde vive la señal—, así que ahora cada
  superset truncado queda en la clave hermana `truncated_glyph` ({letter, constellations,
  num_found, rows}), main avisa con mensaje propio y el lint lo surface como rescate incompleto,
  distinguible del truncamiento de la query directa.
- **#29** — **convención fija de conteo de líneas en `verify-citations`**: los `.txt` de
  `pdftotext` traen un form feed por página (532/535 del corpus RV) que `splitlines()` de Python
  cuenta como salto extra → +1 línea por página, y una revisión posterior marcaba como rotas citas
  correctas (11/24 en un verificador ad-hoc). El skill fija `grep -n`/lectura directa (nunca
  `splitlines()`), documenta que en papers a dos columnas el nº de línea es puntero, no extracto
  contiguo, y el scan de fuga del lint numera con `split("\n")` por consistencia.

## ✅ Framework 1.5.0 (2026-08-15) — tanda #27/#28/#37–#41: la cadena de ingesta

> Tanda de la **cadena de ingesta**, disparada por la aplicación de v1.4.0 en la instancia
> Almagesto-RV: dos bugs de recall/silencio de `query_ads` y cuatro huecos de control (el pool se
> ampliaba sin checkpoint ni juicio). 322 tests verdes, lint 0. `ALMAGESTO_VERSION` 1.4.0 →
> **1.5.0** (minor: modos y clave `candidates` nuevos, retrocompatible).

- **#27** — **cero espurio de ADS**: `numFound: 0` con HTTP 200 (~2/6 corridas de la misma query)
  hacía que la cadena corriera entera sobre un corpus vacío y saliera con exit 0 (y en un re-ingest
  pisara el `ads.json` bueno). La query directa corre con `expect_hits`: reintenta con el backoff
  existente y, si persiste, `EmptyResultError` → exit ≠ 0. Los ceros legítimos (chaining, `--sweep`,
  `--probe`, `--extra-only`) intactos.
- **#28** — **agujero de recall por glifo**: ADS unifica `epsilon`/`eps`/`ε` pero **descarta** los
  lookalikes `ϵ` (U+03F5) y `∊` (U+220A, el glifo de ApJ/AJ/MNRAS) → esos papers quedan indexados
  sólo por la constelación (ε Eri: **121 core perdidos**, incluido el descubrimiento). Rescate por
  glifo: superset de la constelación + filtro client-side letra-específico, `via: glyph`, antes del
  chaining (lo recuperado siembra el grafo). Sólo letras con lookalike; `--no-glyph` lo apaga.
- **#39** — **`extra_core` es override**, no "sumá lo ausente": el paper que ADS sí devuelve y la
  lente descarta ahora se rescata en el lugar (`via: manual`). Contador que distingue traídos de
  rescatados + aviso de bibcodes declarados que ADS no devuelve.
- **#37** — **guardia de expansión** en los orquestadores: entre `query_ads` y el primer paso que
  gasta red y disco, frena si el core se multiplicó respecto de lo ya ingestado (×1.5 y >50 nuevos)
  con el puntero a `relevance.require`/`min_topics`; `--yes` continúa a sabiendas. No aplica al
  primer ingest.
- **#38** — **compuerta de triage del chaining** (el grafo **propone**, no promueve): entra solo el
  candidato con el **sujeto en el título** (1 FP en 310); el resto queda en la clave `candidates` de
  `ads.json` **sin bajarse** para el juicio del LLM (`scripts/triage.py` + paso 2c de `ingest-star`).
  Decisiones persistentes: aceptado → `extra_core`; descartado → `build/<slug>/triage.json` (no se
  re-propone). Medido: 18% de precisión en los core nuevos del grafo. `--no-triage` lo apaga; en
  temas no aplica.
- **#40** — **`query_ads --dry-run`**: delta de re-clasificación offline (core antes/después, los
  que salen separando extracción LLM de stubs, los que entran sin nota por vía). Paso 0 del
  sub-modo D de `maintain`; antes era arqueología con scripts descartables.
- **#41** — **`setup` guía la regla de combinación**: pregunta por la **faceta-eje**, propone
  `relevance.require`, y `--probe` cierra con el **contraste** (qué cortaría cada faceta si fuera
  obligatoria / cuánto se corta vs OR puro). Corolario documentado: con `require` declarada, afinar
  las otras facetas ya no cambia el corte — lo que importa es el **recall de la eje**.
- Skills: `ingest-star` 1.6.1 → **1.9.0**, `ingest-topic` 1.7.2 → **1.8.0**, `maintain` 1.3.2 →
  **1.5.0**, `setup` 1.0.0 → **1.1.0**. `split_fm` centralizado en `lib_config`.

## ✅ Framework 1.4.0 (2026-08-14) — tanda #30–#36: auditoría de framework

> Registrada acá a posteriori (el release commit `0a83e7d` sólo bumpeó la versión). Aditiva:
> `why_excluded` por registro en `ads.json` (#30), consulta `pscomppars` única (#31), residuo
> completo de PDFs por verdad de disco (#32), lint portable por `Path.parts` (#33),
> `accessed` = `retrieved` del snapshot + `--accessed` (#34), `stamp_excluded` quirúrgico (#35),
> sync de docs/labels (#36).

## ✅ Framework 1.3.0 (2026-08-05) — tanda #24–#26: eficiencia del pipeline de ingesta

> Primera tanda de la **revisión del pipeline de ingesta** (2026-08-05: tiempos / tokens /
> metodología + relevamiento de sistemas de discovery; el resto de la cola quedó como backlog —
> ver la sección nueva de abajo). 263 tests verdes, lint 0. `ALMAGESTO_VERSION` 1.2.2 → **1.3.0**
> (minor: modos nuevos, retrocompatible).

- **#24** — `check_retractions --slug` en la cadena: los orquestadores chequean Crossref **sólo**
  sobre los papers del ingest en curso (bibcodes relevantes de `build/<slug>/ads.json` +
  `sources[].key`/`extra_core` del tema) en vez de barrer toda la bóveda en cada corrida (minutos,
  lineal con el corpus). El barrido completo pasa a **pasada periódica**: sub-modo F nuevo del
  skill `maintain` (1.2.0 → 1.3.0); `ingest-star` 1.5.0 → 1.5.1 (doc).
- **#25** — `query_ads --sweep`: el barrido full-text 2b de `ingest-star` deja de ser manual — la
  query `full:` expande sola nombre+aliases con **todas las grafías** (antes: una `--probe` a mano
  por grafía, fácil de olvidar) y lista **sólo** los core que el ingest no trajo (la lista corta de
  candidatos a `extra_core`; el diff contra el corpus ya no se hace a ojo). Preview puro: no baja,
  no encadena, no escribe `build/`. Skill `ingest-star` 1.5.1 → 1.6.0.
- **#26** — guard `or {}` en `load_stars()` (espejo del que ya tenía `load_topics`): con
  `stars.yaml` vacío (instancia recién creada) cualquier lookup de slug moría con `AttributeError`
  en vez del `KeyError` amigable. Destapado por el smoke de #25 en el template.

## Backlog de framework — revisión del pipeline de ingesta 2026-08-05 (cola pendiente)

> De la revisión completa del pipeline (tiempos/tokens/metodología; informe local en
> `outputs/revision-pipeline-ingesta-2026-08-05.md`, gitignored — lo esencial está acá). La tanda
> #24–#26 cerró los ítems "check_retractions --slug" y "--sweep". Pendientes, por valor:

1. **Verify batcheado por fuente** (el mayor ahorro de tokens, ×3–5): un subagente por **bibcode**
   que juzga TODOS los claims atribuidos a esa fuente (hoy: uno por par → el mismo `.txt` se relee
   hasta 5×; el ahorro es pares ÷ fuentes distintas). Riesgo: anclaje/hedging dentro del lote.
   **Gate: A/B contra `bench_verify` en una instancia poblada (RV)** — recall no puede caer.
   Aparte y con el mismo gate: **modelo barato (Haiku) en el fan-out** — medir por separado.
2. **Pata `similar()` en `query_ads`** (recall por CONTENIDO — papers fuera del grafo de citas, el
   único hueco estructural del chaining): operadores de segundo orden de ADS
   (`similar()`/`useful()`/`reviews()`, verificados en vivo 2026-08-05 — misma API, mismo token,
   bibcodes nativos; `trending()` inestable, fuera). Implementar opt-in y **medir contra baseline
   en RV** antes de hacerlo default (estilo defuddle).
3. **Exhaustividad con número**: log del yield por ronda de chaining (Wohlin 2014: la ronda 2
   aporta poco — disparo condicional), capture-recapture query↔chaining (Lincoln–Petersen,
   N ≈ n1·n2/m) → "capturamos ~X de ~Y core estimados" al log/Huecos (le da número al backlog de
   corpus truncado); opcional el fit de saturación f = 1 − e^(−n/τ) (whitepaper de Undermind).
4. **Verify incremental (diff-mode)**: clave estable por par (hash del claim + bibcode) en el
   bloque `## Verificación de citas` → un re-run sólo fan-outea claims nuevos/editados (`raw/` es
   inmutable; invalidar si cambió `fulltext_source`). Gran ahorro en maintain/append.
5. **`triage.md` determinista** por slug (una línea por core: citas/via/topics/¿pdf?/¿fulltext?)
   para elegir deep-reads sin cargar los abstracts de `ads.json`; si se hace el **ranking del
   pool** (Adamic/Adar sobre bibliographic coupling — algoritmo documentado de Inciteful — y/o
   TF-IDF+NaiveBayes estilo ASReview con las etiquetas de la regex), sus scores entran como
   columnas y el LLM sólo juzga el borde (patrón RCS de PaperQA2).
6. **Menores**: fan-out de extracción por paper en ingests grandes (texto de skill — la síntesis
   se arma desde las notas, no desde fulltexts); `fetch_arxiv` ∥ `fetch_pdf` (hosts distintos;
   desacoplar `missing_pdf.json`); fusionar `references()`/`citations()` por chunk; adelgazar
   `CLAUDE.md` (~30–40% de tokens recurrentes por sesión — quirúrgico, con revisión del usuario).
7. **Pasada de retracciones automática** (surgió al cerrar #24): opciones — cron de GitHub Actions
   por instancia (no sirve para instancias local-only), cron local, o que `maintain` la dispare
   si hace >N semanas que no corre (fecha del último barrido en un scratch). Sin decidir.

## ✅ Framework 1.2.2 (2026-07-31) — issues #22–#23: el residuo multi-cláusula

> Segunda vuelta del mismo run: de las 4 sembradas que sobrevivieron a 1.2.1, **3 venían de que el
> claim era un bloque multi-cláusula** (el paper rotado respaldaba, con razón, una cláusula vecina
> —de encuadre o de otra cita—, así que la sembrada "pasaba" como `parcial` sin que nadie se
> equivocara). 254 tests verdes, lint 0. `ALMAGESTO_VERSION` 1.2.1 → **1.2.2**.

- **#22** — `bench_verify` recorta el claim a la **cláusula que porta esa cita** (partido por
  oraciones, con la etiqueta del bullet de sujeto; fallback al bloque si no hay corte). El corte
  exige mayúscula tras el punto → no parte decimales ni `p. ej.`. La veda falso-falso **no** se
  relaja. De paso: `lstrip("-* ")` mutilaba los `**` de las etiquetas en negrita → `BULLET_RE`.
- **#23** — skill `verify-citations` 1.3.0 → **1.3.1**: el **prompt sugerido** ahora transmite la
  regla de claims multi-cláusula que el paso 1 ya exigía (juzgar *la parte que se le atribuye*, y
  decir qué cláusula) — sin ella el subagente juzga el conjunto y hedgea a `parcial`.

## ✅ Framework 1.2.1 (2026-07-31) — tanda de issues #18–#21: validez del benchmark verify

> Salida del **primer run real de `bench_verify`** (instancia Almagesto-RV, 40 pares): recall bruto
> 13/20 (65%); la revisión a mano mostró que 5 "pasadas" eran **soporte casual genuino** (la rotación
> cayó en un paper que de verdad dice lo mismo) y 2 eran misses reales (`parcial`-blando) → recall
> efectivo ≈87% sobre las genuinamente falsas; reales 20/20, sin errores de grounding en las notas.
> El run midió más al *examen* que al examinado → esta tanda arregla el examen (3 fixes al seeder) y
> al examinado (1 regla al skill). 250 tests verdes, lint 0. `ALMAGESTO_VERSION` 1.2.0 → **1.2.1**
> (patch: fixes de validez). **El número NO se publica** hasta re-correr con el seeder arreglado.

- **#18** — el claim se guarda **cegado** (sin `[[wikilinks]]` inline): con el bibcode original
  adentro, una sembrada se caza por mismatch de strings sin leer el paper.
- **#19** — claims por **bloque lógico** (bullet con continuaciones hard-wrapped unidas, o párrafo;
  filas de tabla siguen atómicas): el claim-por-línea producía fragmentos que mezclaban cláusulas de
  citas vecinas (falsas alarmas) y sembradas genéricas fáciles. La protección falso-falso de la
  rotación pasa a operar sobre el bloque completo.
- **#20** — rotación con preferencia **cross-nota**: el cruce se busca primero entre bibcodes que la
  nota de origen no cita en ningún bloque (contra el 25% de soporte casual); fallback histórico si
  la nota cita todo el pool.
- **#21** — skill `verify-citations` 1.2.1 → **1.3.0**: regla del **contenido distintivo** para
  `parcial` (cita textual que toque lo que hace específica a la afirmación; coincidencia sólo
  temática ⇒ `no-soportada`) — en el contrato del subagente, el prompt sugerido y el umbral;
  espejo en `CLAUDE.md`.

## ✅ Framework 1.2.0 (2026-07-19) — tanda de issues #15–#17 resuelta

> Los 3 issues abiertos desde la instancia Almagesto-RV, resueltos en el template (un commit por
> issue, `closes #N`). 246 tests verdes, lint 0 bloqueantes. `ALMAGESTO_VERSION` 1.1.0 → **1.2.0**
> (minor: cambios aditivos/retrocompatibles). Al mergear en las instancias: el nuevo default
> `--rows 2000` y la regla de combinación aplican en el próximo ingest; cambiar la regla re-clasifica
> (sub-modo `maintain`).

- **#16** — `fulltext:` **determinista** para papers que viven bajo varios slugs (relevantes para más
  de un sujeto). `stamp_fulltext` dejó de repuntar al slug que corrió último: precedencia declarada
  (primer escritor gana en empate) + preferencia por calidad (`pdftotext`/`web` > `ocr`) → sin ruido
  de diff y `fulltext_source` estable. Repara punteros colgados.
- **#17** — el **truncamiento** de la query directa (`numFound > --rows`) se **persiste** en
  `build/<slug>/ads.json` (`truncated: {num_found, rows}`) y el **lint lo surface** como backlog:
  un fallo silencioso pasa a visible. Default `--rows` 400 → **2000** (≈ el máximo de una request ADS).
  El truncado del chaining sigue sin registrarse (por diseño). Deferido: `--audit` (censo de bóvedas
  pre-registro), paginación, ordenar el corte por relevancia.
- **#15** — la **regla de combinación** de `relevance.topics` es **declarativa**, no hardcodeada:
  `relevance.require: [faceta,…]` (AND) y/o `relevance.min_topics: N`. `core = (≥min_topics) Y (todas
  las de require) Y (doctype no-ruido)`. Sin declarar nada = OR histórico (retrocompatible). Es la
  palanca contra el ruido que el citation chaining mete al ampliar el pool (medido en Almagesto-RV:
  exigir el eje recorta 928→254). Documentado en `objective.yaml`/`setup`/`maintain`/`CLAUDE.md`.
  Deferido: aplicar la restricción también server-side en la sub-query del chaining.

## ✅ Framework 1.1.0 (2026-07-18) — tanda de issues #9–#14 resuelta

> Los 6 issues abiertos desde la instancia Almagesto-RV, resueltos en el template (un commit por
> issue, `closes #N`). 233 tests verdes, lint 0 bloqueantes. `ALMAGESTO_VERSION` 1.0.0 → **1.1.0**
> (minor: cambios aditivos de schema/cadena). Al mergear en las instancias: re-correr la cadena
> idempotente estampa el contrato nuevo en las notas viejas (ver #14).

- **#9** — guard "objetivo sin instanciar" compara contra un **placeholder explícito**
  (`<definir con el skill setup>`), no contra un nombre real: mata el falso positivo permanente
  de Almagesto-RV.
- **#10** — guard contra abrir la **raíz** del repo como vault de Obsidian: `/.obsidian/` (raíz) al
  `.gitignore`, WARN del lint si existe, filtro vestigial de `graph.json` limpiado, síntoma+remedio
  en `docs/operacion.md`.
- **#11** — tema off-ADS **MIXTO**: `extra_core:` con bibcodes ADS reales dispara la sub-cadena ADS
  (`query_ads --extra-only` nuevo → fetch → make_notes) — antes se ignoraba en silencio. Skill
  `ingest-topic` 1.6.3→1.7.0.
- **#12** — `strictLineBreaks: true` persistido en `vault/.obsidian/app.json` (las notas
  hard-wrapped se reflowean en modo lectura).
- **#13** — stub de paper con **link markdown clickeable al PDF** en el cuerpo (`· [📄 PDF](…)`;
  markdown, no wikilink — el lint rompería).
- **#14** — contrato de `papers/` extendido: **`fulltext:`** (ruta al `.txt` barato) +
  **`fulltext_source:`** (`pdftotext|ocr|web` — la salvedad OCR visible desde el frontmatter).
  Estampado por verdad de disco (stubs) + cirugía `stamp_fulltext` desde `extract_fulltext`
  (migra notas viejas al re-correr). `CLAUDE.md` desambiguado: el default de lectura es el `.txt`.
  Skill `verify-citations` 1.2.0→1.2.1. Los `.txt` OCR'd a mano sin header (caso Almagesto-RV) se
  rescatan con `extract_fulltext.py <slug> --force`.

## Backlog de framework — eye candy del README (EN CURSO, sesión 2026-07-18)

> Estado hasta `9221352` **commiteado y pusheado**; 218 tests verdes, lint 0. Lo de la
> sub-tanda **logo + About (2026-07-18)** de abajo está en el working tree, **sin commitear** aún.

**Hecho tandas previas:** README adelgazado a pantallazo de presentación (lo operativo →
`docs/operacion.md`); portabilidad OS-agnóstica (pathlib, TemporaryDirectory, encoding utf-8 en
subprocesos); generador determinista `docs/assets/make_logo.py` → `logo-animated.svg`
(header del README, 180 px) + `logo.svg` (emblema estático de reserva).

**✅ RESUELTO (2026-07-18) — logo rediseñado: la rosa de Venus.** El usuario descartó el
epiciclo (estático y animado). Rediseño desde cero: `make_logo.py` ahora dibuja la **trayectoria
geocéntrica real de Venus en 8 años** (pentagrama de 5 pétalos, `posición(Venus) − posición(Tierra)`
con órbitas circulares). Se le ofrecieron 4 direcciones (rosa de Venus / lámina Mercurio+Venus /
retrogradación / esfera armilar) y eligió **A (rosa de Venus)**. El animado **dibuja su propia traza**
(`stroke-dashoffset`) mientras Venus —estrella ámbar— recorre la punta (`animateMotion` sobre la
misma curva, 20 s en loop) → conserva el concepto "el mecanismo dibuja su curva" que sí gustaba.
`alt` del README actualizado. **Decisiones técnicas conservadas** (siguen validadas): una sola tinta
neutra `#7d8590` sobre transparente (evita el truco frágil `<picture>`+`prefers-color-scheme`, que
sigue el tema del OS y no el de GitHub); acento ámbar `#d4a017`; sin wordmark; SMIL anima en READMEs
de GitHub (camo proxy) y congela con la rosa completa donde no; camo/browser cachean ~5 min (un "no
se ve" tras push suele ser caché).

**✅ HECHO (2026-07-18) — About del repo.** Estaba vacío. Descripción seteada vía `gh repo edit`:
"Wiki de conocimiento astronómico mantenida por un LLM (patrón LLM Wiki de Karpathy): literatura por
estrella y concepto, verificable claim↔fuente." El usuario optó por **no** poner topics por ahora
(los agrega a mano si quiere).

**✅ HECHO (2026-07-18) — diagrama Mermaid del pipeline.** Bloque ```mermaid en el README (sección
intro, tras el párrafo del flujo raw→LLM→wiki): `ADS/arXiv + NEA/SIMBAD → vault/raw (inmutable) →
LLM-compilador → vault/wiki`, con `objective.yaml` clasificando core/no-core y `lint`/`verify-citations`
como checks (verify retro-alimenta disputas). Incluye la rama **off-ADS** (nodo punteado "PDFs locales ·
web", opt-in) que entra a `vault/raw` sin ADS/NEA — a pedido del usuario, que notó que la v1 del
diagrama la omitía; abajo del bloque va un blockquote explicando el modo off-ADS (`source: web|local-pdfs`
+ `sources:` en `topics.yaml`). **Framing del off-ADS afinado (mismo pedido):** README + CLAUDE.md +
skill `ingest-topic` ahora **lideran con la intención** —es para *métodos que no son exclusivamente
astronómicos* (análisis de datos, machine learning, procesos gaussianos, signal processing) cuya
bibliografía vive fuera de ADS— en vez de con el mecanismo. **Ejemplo canónico de método off-ADS unificado
a procesos gaussianos** en TODO el framework (era demasiado específico del usuario): README, CLAUDE.md
(off-ADS + ejemplo hub/radio → `procesos-gaussianos`/`gp-kernels`), `ingest-topic` (framing + grep de
retro-tag + clave de cita de ejemplo `2006RasmussenWilliams`), `append-knowledge`, el ejemplo comentado de
`topics.yaml`, un comentario de `fetch_ground_truth.py` y los fixtures de tests (`gp`/`gaussian-processes`;
218 tests siguen verdes). Skills bumpeados: `append-knowledge` 1.0.0→1.0.1, `ingest-topic` 1.6.2→1.6.3. Trazos: gris neutro `#7d8590` (fuentes/almacenes/checks), ámbar `#d4a017`
(LLM). GitHub re-renderiza el bloque con su tema claro/oscuro (verificado en ambos con mermaid-cli; los
strokes leen en los dos). Nota de tooling: `mmdc` necesita `--no-sandbox` (config puppeteer) en este
entorno.

**✅ HECHO (2026-07-18) — social preview + favicon (make_logo.py).** `make_logo.py` ahora genera 4
assets: `logo-animated.svg`, `logo.svg`, **`favicon.svg`** (marca reducida: anillo/órbita neutro +
Venus ámbar + centro — la rosa completa se emborrona a 16-32 px, así que el favicon es su reducción
legible; elección del usuario) y **`social-preview.svg`** (tarjeta 1280×640 estilo lámina papel-antiguo:
rosa sepia a la izquierda, `ALMAGESTO` en GFS Didot + el etimón griego `ἡ Μεγίστη` + tagline en EB
Garamond, dentro de un marco de lámina; fondo pergamino `#efe6d3`). El PNG del social preview
(`docs/assets/social-preview.png`) se **rasteriza aparte** (necesita las fuentes GFS Didot + EB Garamond
y un rasterizador; en esta sesión, el Chromium de puppeteer con `--no-sandbox`) y **se sube a mano** en
Settings → General → Social preview. El social preview arrancó con fondo oscuro (se veía "muy IA") →
iterado a papel-antiguo + tipografía griega a pedido del usuario.

**Pendientes menores de eye candy (menú ofrecido, sin decidir):** captura de Obsidian (demo con estrella
famosa), GIF de terminal (vhs) del `--probe`.

## ✅ Backlog de framework (RELEVADO 2026-08-05) — buscadores IA de literatura (Undermind & co.)

> **Relevamiento hecho 2026-08-05** (3 agentes de research con fuentes verificadas; APIs de
> S2/OpenAlex/ADS probadas en vivo). **Veredicto: opción (b) — copiar metodología, no consumir
> APIs.** (1) Ninguno corre sobre ADS (todos S2/OpenAlex/arXiv) y las APIs son pagas/cerradas
> (Undermind: enterprise-only; Elicit: self-serve pero atada a suscripción; Consensus: por
> aplicación; SciSpace: sin API) → para astro no aportan sobre la query ADS directa. (2) **Undermind
> publicó su metodología** (whitepaper Hartke & Ramette 2024, undermind.ai/whitepaper.pdf): lo
> copiable es el criterio de parada (fit de saturación f = 1 − e^(−n/τ)) y el estimador de
> exhaustividad tipo capture-recapture → ítem 3 de la cola del pipeline (arriba). (3) Hallazgo de
> menor fricción, no previsto en el encuadre: **ADS mismo trae operadores de descubrimiento**
> (`similar()`/`useful()`/`reviews()`, verificados en vivo con el token de la bóveda) → ítem 2 de
> la cola. (4) Abiertas: S2 Recommendations sigue gratis pero su pool astro es "últimos 60 días"
> (sólo serviría como modo alertas de `maintain`); OpenAlex pasó a pricing por uso (key gratuita,
> crédito diario) y su grafo es redundante con ADS; SPECTER2 es Apache-2.0 y corre en CPU → opt-in
> de ranking si hiciera falta. **Pendiente del entregable original:** medir lo adoptable contra
> baseline en RV antes de mergear (estilo defuddle). El encuadre original queda abajo como registro.

**Pregunta.** Existen herramientas que hacen búsqueda bibliográfica con IA (**Undermind**, y en la
misma familia Elicit / Consensus / SciSpace / semantic-search sobre Semantic Scholar u OpenAlex).
¿Conviene (a) **consumir alguna API** desde la cadena de ingest, o (b) **copiar la metodología** y
reimplementarla sobre nuestra plomería (ADS + chaining + `objective.yaml`)?

**Por qué importa acá.** El descubrimiento de papers hoy es: query ADS por keywords → filtro core con
la regex de `relevance.topics` → citation chaining anclado. Es determinista y barato, pero es
**matching léxico**: un paper relevante que no usa nuestras palabras no aparece. Ese es exactamente el
hueco que estas herramientas dicen cubrir (búsqueda semántica + exploración iterativa del grafo de
citas, en vez de una sola query).

**A verificar antes de opinar (nada de esto está chequeado):**
- ¿Undermind expone **API pública** y con qué licencia/costo? ¿Los resultados vienen con identificador
  estable (DOI/bibcode) para que encajen con `vault/raw/` y las claves de cita?
- ¿Cubre **astro-ph**/ADS o está sesgado a bio/CS? Si no trae bibcode, hay que resolver DOI→bibcode.
- **Metodología publicada:** ¿hay paper/whitepaper describiendo el algoritmo (búsqueda iterativa,
  criterio de relevancia, criterio de parada)? Eso es lo copiable y lo que no ata a un proveedor.
- Alternativas **abiertas** que sirvan de sustituto barato: API de **Semantic Scholar** (recomendaciones
  + embeddings SPECTER2) y **OpenAlex** (gratis, sin key) — probablemente el camino menos comprometido.

**Criterios de decisión (los de siempre acá).** (1) Lo determinista va en `scripts/`, sin gastar tokens;
(2) el template es MIT y portable → una dependencia de servicio pago/cerrado no puede ser obligatoria,
a lo sumo opt-in como el modo off-ADS; (3) todo lo que entre al vault sigue necesitando fuente citable
(regla #0) — un buscador IA aporta **candidatos**, nunca prosa.

**Entregable esperado del relevamiento:** una nota corta comparando (API vs metodología vs no-hacer-nada)
con números, al estilo de la evaluación de `defuddle` — no adoptar nada sin medir contra el baseline
actual (query ADS + chaining) sobre una estrella/tema ya ingestado.

## Backlog de framework — validación de áreas de `vault/wiki/concepts/` + config a mano

> Rescatado del scratch `DESIGN-NOTES.md` (discusión 2026-06-27) al borrarlo el 2026-06-28. El escape
> **off-ADS** de esa nota **ya se implementó** (commit `a005257`); lo que sigue **no**. Son cambios de
> **framework** → aplicar en el template, no en una instancia (Regla de oro, ver `CLAUDE.md`).

**Problema raíz.** El set de áreas `vault/wiki/concepts/{indicators, methods, activity, hypotheses}` es **folklore,
no contrato**: no existe como dato declarado; está implícito y repartido en 5 lugares (`CLAUDE.md`,
`README.md`, `ingest-topic/SKILL.md`, comentario de `vault/config/topics.yaml`, y las carpetas reales).
`make_notes.py` hace `dest.parent.mkdir(...)` con el `area` que venga **sin validar** → un typo
(`indicator`, `metods`) crea una **carpeta fantasma en silencio**. Las áreas son **abiertas** (no un set
cerrado de 4): sólo `hypotheses` (estructural: schema `name,status` + roll-up Dataview) y `methods`
(universal) son fijas; el resto depende del foco de la instancia.

**Tres mejoras — son CAPAS, no alternativas.** Orden recomendado: **1 → 2 → 3** (el skill sin la
nomenclatura no tiene a qué adaptarse; el check sin la nomenclatura no tiene contra qué chequear).

1. ✅ **HECHO** — **nomenclatura de áreas a config**. `concept_areas` declarado en
   `vault/config/objective.yaml`; `methods`/`hypotheses` reservadas; loader `lib_config.load_concept_areas()`
   (modo tolerante si una instancia vieja no lo declara). Las 5 menciones de "folklore" ahora defieren al
   contrato (CLAUDE.md, README.md, topics.yaml, ingest-topic/SKILL.md).
2. ✅ **HECHO (alcance: objetivo)** — **skill `setup` interactivo**. El agente traduce el foco del
   usuario (en palabras) a `objective.yaml` —`name`/`description` + la regex `relevance.topics` + sugerencia
   de `concept_areas`— y la **afina contra ADS** con `query_ads.py --probe "<query>"` (preview del corte
   core/no-core sin bajar nada), iterando hasta que cierre. Distingue **facetas** (→ relevance.topics,
   constantes) de **sujetos** (→ stars/topics) y respeta la frontera dura. **Descopeado** (a pedido): sembrar
   `stars.yaml`/`topics.yaml` queda fuera — eso entra por `ingest-star`/`ingest-topic`. **Pendiente** (capa
   2 extendida, opcional): un setup que además proponga las estrellas/temas iniciales.
3. ✅ **HECHO (completado 2026-07-17)** — **check de config (lint, WARN blando)**. ✅ Áreas (abiertas,
   nunca se bloquea): `make_notes` **avisa** si el `area` no está en `concept_areas` pero crea igual;
   `lint.py` marca **WARN** las carpetas de `concepts/` fuera de la lista (atrapa typos sin restringir).
   ✅ (2026-07-17) el resto de los guards: `lib_config.require_field()` da error amigable (entrada +
   campo + archivo) en los índices duros — `ads_object`/`simbad` en stars, `query` en topics (con
   pista "es off-ADS → ingest_topic"), `area`/`concept` en `make_notes --topic` — en vez de un
   KeyError crudo; y el lint marca **WARN si `objective.name` sigue siendo el default** del template
   (olvido de instanciar; en el repo template ese WARN es esperable y no bloquea).

**Preguntas abiertas — resueltas al implementar capas 1+3-áreas:**
- Nomenclatura → vive en `vault/config/objective.yaml` (instance-owned), con la prosa del schema en
  `CLAUDE.md` deferiendo a ella. ✅
- `methods` → **reservada** igual que `hypotheses` (universal). ✅
- El check → vive en `lint.py` (encaja con su filosofía WARN/backlog), no en un script aparte. ✅
- Pendiente de decidir (al hacer la capa 2): ¿el skill de setup **reemplaza** el flujo "editá
  `objective.yaml`" del README o lo **complementa**? (lean: complementa).

## ✅ Backlog de framework (RESUELTO 2026-07-17) — obtención de PDFs (papers viejos / no-arXiv)

> Surgido al usar la bóveda (2026-06-29): papers **pre-arXiv / viejos** no están en arXiv, así que
> `fetch_arxiv.py` no los baja; hubo que recurrir a workarounds manuales para conseguir el PDF.

> **Update 2026-07-16 (issues #7/#8, HECHO):** la parte "derivar al usuario" y el rescate de
> escaneos ya están en el framework — fuentes no-conseguibles se marcan `pending`
> (`pending_source` en la nota, aviso del orquestador, precondición en el lint, des-pendeo
> automático al llegar la fuente) y `extract_fulltext.py` cae solo a **OCR** (tesseract) cuando la
> capa de texto es ilegible (`.txt` con `source: ocr`, citable con salvedad).

> **Update 2026-07-17: fetcher HECHO — `scripts/fetch_pdf.py` cierra la sección.** Corre en la
> cadena (`ingest-star` / `ingest_topic --ads`, tras `fetch_arxiv`) para los papers SIN arXiv:
> resolver `esource` → `EPRINT_PDF`/`ADS_PDF` (con token) → `PUB_PDF` (sin token; fallback al
> mismo pedido con `curl` del sistema — los WAF tipo Radware/IOP desafían el fingerprint de
> python-requests pero aceptan curl). Valida magic `%PDF`, retry/backoff, deja el residuo en
> `missing_pdf.json`. Smoke real 3/3: Wilson 78 y Noyes 84 por ADS_PDF, Saar 99 por PUB_PDF
> vía curl. Bonus: `make_notes` ahora estampa `pdf:` por **verdad de disco** (antes adivinaba
> por `arxiv_id` y dejaba punteros rotos si la bajada fallaba).

**Problema.** `fetch_arxiv.py` sólo baja de arXiv (usa el campo `arxiv_id`). Papers sin arXiv (revistas
viejas, escaneados) quedan sin PDF → sin fulltext → sin extracción LLM ni `verify-citations`. Hoy se
resuelve a mano, fuera del pipeline.

**Principio que rige (pedido del usuario).** Meter en **scripts** todo lo determinista posible, que **no
dependa de gastar tokens** del LLM. Alinea con la división del patrón (`scripts bajan determinista; LLM
procesa criterio`): empujar la frontera hacia los scripts.

**Dirección concreta a evaluar (inferencia mía — falta verificar la API):** la ADS API expone los
`esources`/`links_data` de cada paper (`PUB_PDF`, `ADS_PDF`, `ADS_SCAN`, `EPRINT_PDF`…), y ADS **aloja
escaneos** de artículos viejos (`ADS_SCAN`). Un fetcher más general (extender `fetch_arxiv` o un
`fetch_pdf.py` nuevo) podría, para un paper sin `arxiv_id`, intentar en orden `EPRINT → ADS_PDF/ADS_SCAN
→ PUB_PDF` vía la API de links/resolver de ADS, y/o resolver por DOI al publisher — todo determinista, sin
tokens. Los que ni así se consigan, **reportarlos** (caso residual a mano).

**A verificar antes de codificar:** qué devuelve realmente la ADS API (`/v1/resolver` o el campo
`esources`), y si `ADS_SCAN`/`PUB_PDF` se bajan con el mismo token (algunos requieren acceso
institucional).

> **✅ Probe del resolver corrido (2026-07-17) — `fetch_pdf.py` es VIABLE.** Testeado con el token
> ADS sobre 3 clásicos pre-arXiv (Wilson 1978, Noyes 1984, Saar & Brandenburg 1999):
> - `GET /v1/resolver/<bibcode>/esource` (Bearer token) lista las fuentes por tipo
>   (`ADS_PDF`, `ADS_SCAN`, `PUB_PDF`, `EPRINT_*`).
> - **`ADS_PDF` (`articles.adsabs.harvard.edu/pdf/<bibcode>`) BAJA con el token** en el header
>   (200, PDF real con capa OCR de ADS, greppable): el 403 del episodio Saar era por pedirlo
>   **sin** el Bearer. Sin token sigue fallando.
> - El host **throttlea ráfagas** (una bajada dio `000` y salió al retry) → mismo patrón
>   retry/backoff + sleep que `fetch_arxiv.py`.
> - `PUB_PDF` (IOP `stacks.iop.org`) entregó el PDF a un GET pelado con UA de navegador —
>   variable por publisher/red (el episodio previo reportó captcha): intentar y degradar.
> - Orden sugerido para `fetch_pdf.py`: `EPRINT_PDF → ADS_PDF/ADS_SCAN (con token) → PUB_PDF
>   (sin token, UA normal)`; lo que no salga → `pending` (fallback ya existente).

**Hallazgos testeados (2026-07-01, episodio Saar & Brandenburg 1999 en la instancia Actividad).** Reglas
concretas para el futuro `fetch_pdf.py` y para la guía del skill (ya reflejadas en `ingest-star/SKILL.md`):
- El **escaneo ADS** directo (`articles.adsabs.harvard.edu/pdf/<bibcode>`) devolvió **403** sin sesión; el
  gateway `.../link_gateway/<bibcode>/{ADS_PDF,PUB_PDF}` y el `/pdf` del publisher devuelven **HTML/captcha**
  a un fetch automático (necesitan sesión institucional del navegador). → la parte determinista tiene techo:
  para paywall/captcha el fallback real es **pedir el PDF al usuario**.
- **Gana el dato sin el PDF:** en artículos viejos las **tablas son imágenes** servidas por el CDN del
  publisher (IOP: `content.cld.iop.org/journals/<...>/<vol>/<pag>/revision1/tbN.gif`) y **se bajan sin
  paywall**. Para papers de survey donde sólo interesa la fila de una estrella, bajar el `tbN.gif` alcanza.
  También existe el **HTML legacy** (`iopscience.iop.org/article/<doi>/fulltext/NNNNN.text.html`) con el
  cuerpo (no las tablas).
- **El índice full-text de ADS de escaneos viejos es incompleto:** su OCR **pierde ~½ de las filas** de
  tabla (12/26 estrellas en Saar 1999) → un `full:"HD X" → 0` es **inconcluso, no ausencia**. Implicación
  para código: no marcar "no está" desde un full-text negativo; y el barrido full-text por estrella (paso 2b
  del skill) debe listar **todo** el core, no top-N por citas.
- **No todo PDF necesita OCR:** el de Saar 1999 traía **capa de texto** (`pdftotext` lo sacó entero, tablas
  incluidas), con quirks de PostScript viejo (`-` y `>` → `[`). Chequear capa de texto antes de OCR.

## ✅ Backlog de framework (RESUELTO 2026-07-01) — `defuddle` para el modo off-ADS de `ingest-topic`

> Surgido de una discusión (2026-07-01) sobre si conviene adoptar los **skills oficiales de Obsidian**
> (`kepano/obsidian-skills`, de Steph Ango). Conclusión: para el flujo de Almagesto la ventaja es
> marginal-a-negativa y **una sola pieza del pack encaja** — la anoto acá; el resto se descarta abajo.

**Contexto.** El pack oficial trae 5 skills: `obsidian-markdown`, `obsidian-bases`, `json-canvas`,
`obsidian-cli`, `defuddle`. Hay además una ruta **MCP** (plugin Local REST API + `mcp-obsidian`) que
expone read/search/write del vault por HTTP con Obsidian abierto.

**Por qué se descartan casi todos (para no re-discutirlo).**
- `obsidian-markdown` → redundante y potencialmente en conflicto: el contrato de frontmatter + convenciones
  (`$...$`, kebab-case, disclaimers) ya están codificados y son **más estrictos** que la sintaxis OFM genérica.
- `obsidian-bases` → el vault usa **Dataview** (`FROM "papers"`), no Bases; migrar sería un cambio de todo el
  esquema, no un win gratis.
- `json-canvas` → artefacto visual/humano; Almagesto es machine-first (frontmatter+lint+git) y el grafo ya
  lo da Obsidian nativo. No es bibliografía citable.
- `obsidian-cli` **y la ruta MCP** → **exigen Obsidian corriendo** (app + plugin/CLI, cert self-signed,
  bearer token). Chocan con el principio de **headless/portabilidad** (memoria in-repo, scripts desde raíz,
  que viaje entre máquinas) y no aportan nada que no cubra ya el acceso directo a FS + grep.

**Lo único a evaluar — `defuddle`.** Extrae markdown limpio de páginas web quitando clutter (menos tokens)
[documentado: `kepano/defuddle`]. Encaja con el **modo off-ADS** de `ingest-topic`, que guarda snapshots web
como `.txt` **deterministas** (URL + fecha) para citabilidad. Hoy esa extracción va por `WebFetch`.

**Evaluado 2026-07-01 (rama `exp/defuddle-offads`) → conviene.** Números (una página de Wikipedia,
ejemplo off-ADS): defuddle 60 KB vs pandoc 235 KB vs HTML crudo 480 KB (~4×/~8× menos);
**determinista** (dos corridas byte-idénticas); 0 hits de clutter (vs 34 en pandoc); conserva cuerpo,
referencias (DOI/arXiv/bibcode) y matemática. Supera a `WebFetch` para este uso porque WebFetch es
model-based (no determinista, no es snapshot verbatim) y el snapshot citable **exige** determinismo.
Caveats: dependencia **Node/npm** (off-ADS es opt-in y raro → aceptable) y algún artefacto HTML suelto
(un bloque `<video>` quedó sin limpiar). Es una **utilidad general**, no Obsidian-específica: se adopta
sola, sin el resto del pack ni la ruta MCP.

**Implementado (mergeado a `main`: commits `70fc899` / `d21f70c` / `c59fa52`):**
- `scripts/fetch_web.py` — `npx defuddle parse <url> --markdown` → `vault/raw/fulltext/<slug>/<clave>.txt`
  con encabezado URL+fecha; valida la clave contra `BIBCODE_RE`, idempotente salvo `--force`, error
  amigable si falta Node. **Post-clean determinista** (`clean_markdown`) que saca los bloques HTML de
  media/embed sueltos (`<video>/<audio>/<iframe>/<svg>/<picture>` + `<source>/<track>`) → resuelve el
  artefacto `<video>` (probado: 0 residuales).
- **Creación automática de la nota de paper:** `make_notes.write_web_paper_note()` + modo CLI
  `make_notes.py --web` (reusa el template de frontmatter de las notas ADS → un solo lugar de verdad);
  `fetch_web.py` la llama tras el snapshot (salvo `--no-note`). Stub con `pdf: null`, `arxiv_id/doi: null`,
  `source_url` + `accessed` (la **fecha del snapshot**, tomada del `.txt` → coinciden), `bibstem` = venue o
  dominio de la URL, `thesis_links` al concept, `tags: [paper, web]`, `generator` estampado. El modo
  standalone cubre también fuentes **PDF** off-ADS (sin URL → `source_url`/`accessed` null).
- Wiring en `ingest-topic/SKILL.md` (v1.0.0→1.1.0): el bullet **Web** y el ex-"notas a mano" reflejan el
  flujo automatizado, con WebFetch + `make_notes --web` como fallback sin Node.
**Resuelto:** mergeado a `main`; nada pendiente.

## Backlog de framework — revisión profunda 2026-07-03 (tanda 3 pendiente)

> De la revisión completa del proyecto (code review de `scripts/` + consistencia docs↔skills +
> relevamiento de proyectos similares; informe local en `outputs/revision-2026-07-03.md`, gitignored).
> **Aplicado:** tanda 1 (bugs de scripts: Range/200 en fetch_arxiv, idempotencia envenenada, gate
> `--force` en ground-truth, exit code del lint, retry/truncado en query_ads, encoding utf-8) y
> tanda 2 (matriz método×estrella seed, política de archivado alineada, paso 1c→`--probe`,
> `git lfs install` en README, `lit_caveat`→`disputes[]`, formato de log). Queda la **tanda 3**,
> por valor:

1. ✅ **HECHO (estrellas, 2026-07-03)** — **Citation chaining en el ingest**: `query_ads.py` pide
   `references()`/`citations()` de los core, **ancladas server-side** con `full:` de nombre+alias
   (sin ancla el grafo devuelve los mega-citados genéricos del área — medido: 31/31 falsos positivos
   en tau Ceti; con ancla trae exactamente los surveys/catálogos que el barrido 2b cazaba a mano,
   p. ej. Wilson 1978 / Mount Wilson). Provenance `via: chain:*` en `ads.json`; `--no-chain`
   desactiva. **Abierto:** nada — el chaining de temas se resolvió en el ítem 7(c) y el fetch de
   PDFs viejos en `fetch_pdf.py` (2026-07-17, sección arriba).
2. ✅ **HECHO (completado 2026-07-17)** — ✅ **Veredicto `contradice` en `verify-citations`** (4
   categorías estilo CAQA; `contradice` manda sobre el score y se resuelve como corrección o disputa
   `planets[].disputes[]`, no como cita rota; CLAUDE.md/README). ✅ (2026-07-17) **auto-benchmark
   del verificador** (CiteAudit): `scripts/bench_verify.py seed` siembra citas falsas deterministas
   entre pares reales de queries/concepts (misma afirmación, bibcode rotado — excluyendo los que la
   afirmación cita de verdad, para no plantar falsos-falsos); el skill (modo benchmark, v1.2.0) las
   verifica **a ciegas** (el subagente nunca ve etiquetas) y `score` reporta recall de sembradas +
   reales caídas en `outputs/verify-bench-*.md`. Nada del benchmark toca `vault/`. La citation
   precision por nota (ALCE) se descartó por frágil (ítem 7); la cobertura del lint cubre lo accionable.
3. ✅ **HECHO (2026-07-03)** — **Detección batch de contradicciones**: skill `find-contradictions`
   (v1.0.0). Barre un eje (estrella/parámetro o concepto), confirma cada desacuerdo claim↔claim con un
   subagente por par que lee los **dos** fulltext (`real|aparente|no-concluyente` + cita de ambos
   lados) y **propone** disputas (`planets[].disputes[]` con NEA como verdad; línea citando ambos
   `[[bibcode]]` para conceptos) que el usuario aprueba antes de escribir. Ortogonal a
   `verify-citations` (claim↔su fuente vs claim↔claim entre fuentes).
4. ✅ **HECHO (2026-07-03)** — **Chequeo de retracciones**: `scripts/check_retractions.py` consulta
   **Crossref** por DOI (señal determinista: `updated-by` con `type: retraction|removal|withdrawal`;
   ADS no expone `property:retracted` — sólo prefijo de título, que se usa de fallback para papers sin
   DOI), estampa `retracted: true` + `retraction{...}` en la nota (idempotente, viaja en git) y el
   `lint.py` la surface **offline como categoría bloqueante**. En la cadena de `ingest-star`/`-topic`
   y a correr periódicamente. Errata/EoC → aviso blando (no retracta).
5. **Vocabulario AstroMLab 5** (arXiv:2511.12353) como diccionario de referencia para
   `topics`/`methods`/`aliases` (anti drift taxonómico). **Recurso verificado 2026-07-03** — existe y
   sirve: repo `github.com/tingyuansen/astro-ph_knowledge_graph`, poblado, con
   `concepts_vocabulary.csv.gz` (9.999 conceptos: label/class/nombre/descripción) + embeddings
   `.npz` (9999×3072, `text-embedding-3-large`). **Bloqueante para adoptar: SIN licencia declarada**
   (README dice "enfoque conservador" pero no MIT/CC) → NO se puede vendorear en un template MIT; el
   camino limpio sería `fetch_vocab.py` que **el usuario** baja el CSV a ruta gitignoreada + WARN del
   lint sugiriendo el concepto canónico más cercano por **string/fuzzy match** contra los nombres del
   CSV (ignorar los embeddings → evita la dependencia de OpenAI). **Prioridad baja / EN OBSERVACIÓN**:
   payoff sólo con la bóveda ya grande. **Re-evaluar cuando** (a) el repo declare una licencia
   permisiva (hoy el bloqueante) — chequear `github.com/tingyuansen/astro-ph_knowledge_graph/LICENSE
   periódicamente — o (b) la bóveda alcance volumen y el drift taxonómico se vuelva medible. Hasta
   entonces no se implementa. **Re-chequeado 2026-07-17: sigue sin licencia** — GitHub API
   `license: null` (sin archivo LICENSE); el `## License` del README sólo lista las licencias de las
   FUENTES agregadas (arXiv non-exclusive, ADS) y pide respetarlas, **sin grant propio del dataset**;
   último push del repo 2025-11-15 (nada cambió desde la evaluación de 2026-07-03).
   **Re-chequeado 2026-08-22: sigue igual** (`license: null`, sin archivo `LICENSE` —404 en la API—,
   mismo último push). Novedad del mismo día: parte de lo que este vocabulario venía a resolver
   —anti-drift taxonómico y linkeo entre notas— se cubre **sin licencia** con las **keywords del
   propio paper**, que ADS ya devuelve y la cadena tira (**#92**). Eso baja todavía más la prioridad
   de adoptar este recurso: primero agotar lo que llega gratis por la fuente.
6. ✅ **HECHO (2026-07-03)** — **Skill de mantenimiento** `maintain` (v1.0.0): opera sobre entidades
   **ya ingestadas** — refrescar (papers nuevos → re-sintetizar sólo lo nuevo), borrar (nota + PDF +
   reparar colgados), renombrar slug, re-clasificar tras cambiar `relevance.topics`, y resolver el
   backlog del lint. Invariante: cadena idempotente; extracción LLM y ground-truth no se pisan sin
   `--force`.
7. ✅ **HECHO (2026-07-03)** — **Menores**: (a) `--probe` ahora lista **todo el core** (no top-25);
   (b) **curación persistente** `extra_core: [bibcode]` en stars/topics.yaml (`via: manual`, sobrevive
   al re-run); (c) **chaining para TEMAS** anclado a la propia query del tema (verificado: +9 core en
   un tema de prueba); (d) **cobertura de verificación** en el lint (query/concepto con citas pero sin
   bloque `verify-citations` → backlog ALCE-adjacent); (e) **pre-commit hook** `scripts/hooks/pre-commit`
   (corre el lint, bloquea si hay bloqueantes; activar con `git config core.hooksPath scripts/hooks`).
   Todo verificado contra ADS/lint. **Queda sólo:** el vocabulario AstroMLab (ítem 5, en observación
   por licencia) — el fetch de PDFs viejos vía `esources` se resolvió el 2026-07-17 (`fetch_pdf.py`,
   sección arriba). La citation precision "dura" (parsear X/N del bloque de verify) se
   descartó por frágil; la **cobertura** de (d) cubre la parte accionable.
