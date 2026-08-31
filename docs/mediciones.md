# Mediciones — qué se midió, con qué número, y qué cambió por eso

> El **contrato** (`docs/contrato.md`) dice qué promete el framework; este archivo dice **sobre qué
> evidencia**. Existe porque una medición que vive sólo en el chat de la sesión se pierde, y sin ella
> los mismos errores se vuelven a cometer y las mismas reglas se vuelven a descubrir.
>
> Regla de la casa: **lo medido y lo derivado van separados**, y una salvedad que invalida un número
> se escribe al lado del número, no en otro lado (regla de método #5).

## 2026-08-25 · Extracción de τ Ceti (79 papers) — el fan-out con prompt escrito a mano

**Qué era.** Ingest completo de τ Ceti con `ingest-star`: 79 fulltexts, un subagente por paper. El
prompt de cada subagente lo escribió el agente orquestador **a mano**, que es lo que el skill
permitía en ese momento.

**Cómo re-medirlo.** Los 79 JSON de extracción quedaron fuera del repo (scratch). Lo reproducible es
el detector de maqueta (`scripts/measure_layout.py`) y el conteo de campos sobre las notas de paper.

| Qué se midió | Número | Salvedad |
|---|---|---|
| Valores extraídos en total | 1367 sobre 79 papers | — |
| Valores marcados **segunda mano** | 400 (29 %) | el mecanismo de error nº 1 de #103 (HD 40307: 3 casos), cazado en el origen |
| `.txt` que son **preprint** de arXiv | 71/79 (89 %) | el caveat de #57 es la **norma** del corpus, no la excepción |
| Extractores que redescubrieron solos el entrelazado de columnas (#44) | 54/79 (68 %) | auto-reportado; el detector marca 62/79 (78 %) |
| Extractores que redescubrieron el problema de grafía del sujeto | 23/79 (29 %) | el paper escribe «tau Cet» o sólo «HD 10700»; medido en un caso: `grep "Ceti"` da 1 de 11 hits |
| `.txt` con OCR o texto degradado | 25/79 (31 %) | — |
| Extracciones que declararon una discrepancia **interna** de la fuente | 13/79 (16 %) | el paper se contradice consigo mismo |
| Extracciones que declararon riesgo de fila/sujeto equivocado | 10/79 (12 %) | tablas multi-objeto |

**Qué cambió.** Las dos primeras filas de redescubrimiento son la evidencia de **INV-100**: las
reglas vivían en el skill y no en el prompt, y se caían en silencio en esa frontera. El prompt ahora
se genera (`scripts/extraction_prompt.py`).

⚠ **Esta corrida NO es una prueba del framework.** Prueba el framework *tal como lo recuerda el
agente*, que es otra cosa. Cualquier número de arriba mide la paráfrasis, no el skill.

## 2026-08-25 · ¿Los números de línea declarados apuntan a donde dicen?

**Cómo.** Para cada valor con nº de línea y con un token numérico distintivo, se busca ese token en
una ventana de ±2 líneas del `.txt`. Decidible sin ground truth.

| Celda | papers | valores chequeables | línea correcta |
|---|---:|---:|---:|
| A · prompt a mano, Opus | 8 | 52 | 42 (**80 %**) |
| B · prompt generado, Opus | 8 | 4 | 4 (100 %) |
| C · prompt generado, Haiku | 7 | 14 | 14 (100 %) |

⛔ **B y C no comparan con A.** La muestra (stride determinista sobre los 79) cayó casi entera en
papers instrumentales donde τ Ceti es estrella de calibración y casi no hay números propios: 4 y 14
valores chequeables contra 52. Con esa n no se distingue nada. Para que el A/B signifique algo hay
que re-correrlo sobre los papers con 15-25 valores.

⚠ **El primer medidor daba 36 % y estaba mal**: usaba `splitlines()`, que parte también en los form
feeds que `pdftotext` mete por página, así que sus números no eran los de `grep -n`. Es **la regla
que el propio prompt generado exige** («de `grep -n`, nunca de `splitlines()`»), violada en el código
que iba a juzgar si los demás la cumplían. Corregido a `split("\n")`: 36 % → 80 %.

## 2026-08-25 · A/B del prompt: ¿abre el PDF cuando el texto no alcanza?

El prompt generado dice «mirá las TABLAS, no sólo el texto» y «un `grep` vacío no prueba ausencia».
Eso es decidible: ¿el extractor abrió el PDF, o declaró el dato no verificable y siguió?

| Celda | papers | abrió el PDF / la imagen | declaró algo no verificable **sin** abrirlo |
|---|---:|---:|---:|
| A · a mano, Opus | 8 | 1 | 5 |
| B · generado, Opus | 8 | 2 | 2 |
| C · generado, Haiku | 7 | 0 | 0 |

**n = 8: es dirección, no significancia.** Lo que sí es concreto es la instancia: sobre
`1992PASP..104.1152B` (escaneo de ADS, OCR que perdió columnas de tabla), la celda A declaró
explícitamente que no se podía saber de qué referencia sale la Teff adoptada ni a qué estrella
corresponden los bloques de la Tabla 3; la celda B renderizó las páginas con `pdftoppm`, resolvió
**las dos** cosas, y encontró además un error de OCR material (el `.txt` dice «β Peg» donde el
impreso dice «ε Peg» — dos estrellas distintas de la misma tabla).

C no abrió ningún PDF y tampoco declaró nada como no verificable: no es que resolviera, es que no se
lo planteó.

## 2026-08-25 · Haiku en el fan-out de **extracción**

| | Opus | Haiku |
|---|---|---|
| Tiempo por paper | ~200–600 s | ~55–85 s |
| Salida | 5–25 valores, `regimen` largo, salvedades detalladas | 2–7 valores, `regimen` de una línea |
| Abrió PDFs cuando el texto falló | 2/8 | 0/7 |

⛔ **No hay ground truth para extracción**, así que esto NO dice quién tiene razón: sólo que Haiku
extrae menos y más corto. Un error de atribución concreto encontrado a mano: sobre
`2011A&A...525A.140D`, Haiku marcó los parámetros estelares de τ Ceti como «medido de asterosismología
HARPS» cuando el propio paper los atribuye a Sousa et al. (2008) — o sea, perdió la marca de segunda
mano que es el mecanismo de error nº 1 de #103.

**Pendiente y distinto:** Haiku en el fan-out de **`verify-citations`**, que sí tiene gate
(`bench_verify`: siembra citas falsas y mide el recall contra el 80 % medido con el modelo actual).
Ese experimento es decidible; éste no.

## 2026-08-25 · Quién encontró los bugs de esta tanda

Cuatro bugs de framework, **ninguno lo encontró la suite**:

| Bug | Lo encontró |
|---|---|
| El prompt del fan-out no era artefacto (INV-100) | medir la corrida de τ Ceti |
| El parser del contrato topaba en dos dígitos | el canario de trazabilidad, al agregar INV-100 |
| `mutar.py --diff` no ve archivos nuevos (INV-101) | leer la salida del gate y preguntar **sobre qué corrió** |
| Los patrones de tema perdían las siglas | ejercitar el camino `--theme`, que nadie usaba |

Más dos que salieron de correr contra el corpus real y no contra dobles (regla de método #1):
`Cet` matcheaba «Prin**cet**on» (verificado: la frontera saca el falso positivo y conserva los dos
hits buenos), y `tools/` estaba fuera del mapa de trazabilidad, así que una marca `@inv` en el propio
gate de mutación era invisible.

## 2026-08-25 · ¿Se puede cribar barato antes de extraer? — 2 modelos × 2 reglas

**Idea probada.** La extracción cuesta ~110k tokens por paper y 27 de 79 (τ Ceti) terminaron en
`no_sintetizado`. ¿Un agente barato, con sólo título, abstract y las líneas donde aparece el sujeto,
puede decidir cuáles no vale la pena leer entero?

**Etiqueta.** `no_sintetizado` en la nota del paper, escrita al cerrar cada ficha. Población: 96
papers extraídos (τ Ceti + HD 40307); 94 en el subconjunto común a las tres celdas.

| celda | caza tangenciales | **tira buenos** | acuerdo |
|---|---:|---:|---:|
| Haiku · «¿de qué trata el paper?» | 19/30 | 14/64 (21 %) | 73 % |
| Sonnet · «¿de qué trata el paper?» | 24/30 | **28/64 (43 %)** | 63 % |
| Haiku · «¿le atribuye algún valor medido?» | 12/30 | **1/64 (1 %)** | 79 % |

**Veredicto: no se adopta.** La versión segura (1 % de error caro) sólo caza 12 de 30 tangenciales,
o sea manda 81 de 94 al extractor igual, y los que ahorra son los papers más cortos — el ahorro real
es menor que el 14 % de conteo. No paga el riesgo de un paso que puede descartar una fuente **en
silencio**.

**El hallazgo que sí vale, y es transferible.** La regla pesa más que el modelo, y **el modelo más
capaz amplificó el error de la instrucción**: Sonnet aplicó la regla mala con más rigor que Haiku
—cazó más tangenciales— y por eso mismo descartó el doble de papers útiles (43 % contra 21 %). La
regla decía «si el sujeto es banco de prueba de un instrumento, es al pasar», y la premisa era falsa:
Coffinet 2019 usa τ Ceti para calibrar HARPS **y en el camino le mide diez señales**. Ser banco de
prueba y aportar dato propio no son excluyentes.

**Consecuencia operativa:** cuando un fan-out falla, la primera pregunta es si la regla está bien
planteada, no si el modelo alcanza. Subir de modelo con la pregunta equivocada empeora el resultado.

*Cobertura declarada:* tres agentes murieron por límite de gasto (Sonnet lote 00, regla B lotes 08 y
09) y no se relanzaron; los conteos salen del subconjunto común de 94, así que la comparación entre
celdas es pareja.

## 2026-08-25 (b) · Modelo chico como EXTRACTOR — 27 papers tangenciales de tau Ceti

**Idea probada.** La prueba pendiente n.º 1 de este mismo documento: que el modelo barato **extraiga**
los papers tangenciales en vez de decidir si se leen. Se corrió Haiku con el prompt canónico
(`extraction_prompt.py`, o sea reproducible) sobre los 27 papers con `no_sintetizado` de tau Ceti, y un
juez Sonnet por paper comparó contra la extracción Opus ya existente, arbitrando cada valor contra el
`.txt`.

| | Haiku vs Opus, 27 papers |
|---|---|
| Cobertura de valores | **108 / 344 = 31 %** |
| Suficiencia por paper | 2 suficiente · 15 parcial · **10 insuficiente** |
| Pérdidas juzgadas materiales | **85** |
| Valores que Haiku trajo y Opus no | 5 reales · **6 falsos** |
| Errores de anotación | 64 (9 línea, 9 segunda mano, 4 columna cruzada, 4 valor erróneo) |

**Veredicto: no se adopta, y la premisa que lo justificaba era falsa.** La prueba se anotó diciendo que
«el riesgo queda acotado por construcción, porque si extrae de menos en un paper tangencial es que
había poco que extraer». No: extrajo el 31 % y 85 de las pérdidas son materiales. **«Tangencial a la
estrella» no es «pobre»** — casi todos estos papers son `fundacional` de un método, y ahí vive su
aporte. Haiku conserva el dato trivial sobre la estrella y tira el método entero (`role: []`,
`methods: []`, ecuaciones, umbrales, régimen de validez).

**Y fabrica.** Seis valores falsos verificados contra la fuente: atribuyó a tau Ceti una propiedad de
HD 166620, inventó un jitter de 2,3 m/s multiplicando por un factor que el paper **divide**, inventó
barras de error que la tabla no trae, y llamó «α enhancement» a la microturbulencia. Para una bóveda
bibliográfica eso es peor que perder: un valor falso **con línea citada** pasa el lint.

*A favor, y medido:* en 5 casos Haiku fue **mejor** que Opus (decimales de una figura que Opus
redondeó, un rango de S/N que Opus leyó mal). El modelo chico no es ciego: es incompleto y a veces
inventivo.

### Lo que sí paga: Sonnet como extractor

Mismo prompt canónico, mismos papers, brazo de control Opus corrido en paralelo para separar el efecto
del modelo del efecto del prompt (el baseline viejo de tau Ceti es anterior a INV-100, o sea una
paráfrasis).

| | valores | 2.ª mano marcada | tokens | ×precio | **costo rel.** | wall-clock |
|---|---:|---:|---:|---:|---:|---:|
| Haiku | 18 (**33 %**) | 9 / 16 | 55 % | ÷5 | **11 %** | 19 % |
| **Sonnet** | 42 (**78 %**) | **16 / 16** | 88 % | ÷2,5 | **35 %** | 76 % |
| Opus (ref.) | 54 | 16 | 100 % | — | 100 % | 100 % |

Subconjunto común de 5 papers. Sonnet recupera **16 de 16** atribuciones de segunda mano, el mismo
número que Opus — la anotación que más caro sale perder, porque distingue «este paper lo midió» de
«lo copió de otro». En el paper más denso del lote (Jofré 2015, 4947 líneas) Sonnet sacó **27 valores
contra los 31 de Opus**; Haiku, 5, dos de ellos con columnas cruzadas.

**Los tokens no bajan** (88 % de los de Opus): el `.txt` a leer es el mismo. El ahorro es precio
unitario, no menos trabajo. En **tiempo** el ahorro es chico (76 %): si el cuello es la espera, la
palanca es paralelizar (#104), no cambiar de modelo.

*Cobertura declarada:* n = 5 papers, una sola corrida por celda, todos de una misma estrella. Alcanza
para decidir probar, no para publicar el número.

## 2026-08-25 (c) · A/B de prompts: las reglas de anotación de #103 no mueven la aguja

**Idea probada.** La prueba pendiente n.º 4: el prompt canónico contra el mismo **sin los cuatro
bullets de #103** (n.º de línea, régimen, tiempo verbal literal, segunda mano). El schema JSON queda
**idéntico** en las dos ramas, así que mide exactamente lo que #103 agregó sobre lo que el schema ya
nombra. 2 modelos × 2 prompts × 5 papers, esta vez sobre los papers **con contenido** (14-31 valores),
que es el recorte que la prueba n.º 4 pedía.

| celda | valores | c/línea | c/régimen | c/2.ª mano |
|---|---:|---:|---:|---:|
| Haiku · canónico | 15 | 100 % | 100 % | 20 % |
| Haiku · sin reglas | 15 | 100 % | 100 % | 7 % |
| Sonnet · canónico | 49 | 100 % | 100 % | 49 % |
| Sonnet · sin reglas | 46 | 100 % | 98 % | 54 % |

**Veredicto: nulo — no se toca `extraction_prompt.py`.** Sacar los cuatro bullets no cambió línea ni
régimen (100 % en las cuatro celdas, salvo un 98 % en una), **porque el schema ya nombra esos campos y
eso alcanza**. La única diferencia es segunda mano (Haiku 20 % → 7 %), pero **Sonnet fue en la
dirección contraria** (49 % → 54 %): es ruido, no señal. El caso más nítido es el paper más denso
(Jofré, 4947 líneas): Sonnet sacó **27 valores con las reglas y 27 sin ellas** — idéntico.

**La consecuencia es de método:** para una anotación que el schema puede nombrar como campo, más prosa
en el prompt no agrega nada. La palanca es la misma que ya funciona para línea y régimen — **hacer el
campo obligatorio y chequearlo**, o sea un detector, no una instrucción. Coincide con lo ya medido
(RSOS 2025): pedir precisión en el prompt no mejora, y a veces empeora.

*Cobertura declarada:* grilla **completa**, 5 papers × 4 celdas, una sola corrida por celda. La columna
Opus de esa tabla existe sólo para Jofré (el brazo de control se corrió sobre otros 6 papers, y Jofré es
el único solapado): ahí Opus sacó 31, Sonnet 27 (**87 %**) y Haiku 5 (**16 %**). No comparar el total de
49 de Sonnet contra ese 31 — son poblaciones distintas.

## 2026-08-28 · `.txt` vs PDF como fuente de extracción (#205)

**Qué era.** Dos papers extraídos dos veces por subagentes independientes, uno leyendo sólo el
`.txt` y el otro sólo el PDF (`Read` lo rasteriza). Decidió retirar la rama "leer el `.txt` y
escalar al PDF si un detector lo dice" y hacer del PDF la única fuente de lectura.

| paper | vía | tokens | tiempo | tools |
|---|---|---|---|---|
| `1998Cichocki` (17 pg, capa rota) | `.txt` | 107.459 | 187 s | 8 |
| | **PDF** | **98.415** | **125 s** | **3** |
| `2005Hyvarinen` (11 pg, capa limpia) | `.txt` | 96.967 | 146 s | 6 |
| | **PDF** | **94.574** | **92 s** | **2** |

El PDF gana en los cuatro ejes en los dos casos — el costo lo domina el razonamiento y la salida,
no el input. Y el paper "limpio" tampoco estaba limpio: con los tres chequeos de calidad en verde,
su `.txt` había perdido el radical `√` (sale como una `r` suelta), la prima de `p′` (como `p0`),
superíndices de transpuesta y un subíndice que hace leer una autocovarianza como una inversa (#194).

⚠ **n = 2, y los dos densos en matemática.** Lo defendible en costo es *«comparable, no 10× más
caro»*; lo grande y consistente es el **tiempo** (−34 % y −37 %). Consecuencias: #205 (la fuente es
el PDF, el `.txt` es el índice), retiro de `symbols_lost`/`fulltext_layout` (#193/#194 — los
detectores no discriminaban), y la regla de modalidad: un modelo chico leyendo el PDF recupera lo
mismo que uno grande leyendo el `.txt` roto — es cuestión de **modalidad, no de modelo**.

## 2026-08-27/28 · El dato que vive en una imagen (#195) y el `|` que parte la fila (#240)

Dos mediciones sobre el mismo tema real (65 vistas), las dos movieron reglas — más una tercera
(#281, 2026-08-30) sobre otra bóveda, que extiende la primera:

- **29 de 65 vistas (45 %)** declaran datos que existen sólo en figuras o tablas-imagen: casi la
  mitad del corpus tiene información que ninguna búsqueda sobre el `.txt` puede encontrar. La regla
  dura cubría sólo ecuaciones → desde 1.71.0 `extraction_prompt._media_note` trata los tres casos
  (tabla extraída como texto / tabla-imagen / figura como lectura de gráfico con `≈`, figura y
  página).
- **Tres lecturas «irreconciliables» eran tres contornos de la MISMA figura (#281).** La Fig. H.2
  de `2023A&A...680A..64D` es un mapa de contornos de probabilidad de detección (0 / 10 / 50 / 68 /
  90 / 100 %); la banda de 30-50 M_J se leyó como 2-3 UA, 1,8-4 UA y 3,5-6 UA — los contornos del
  **10, 50 y 90 %**. #195 asume que una figura es una **curva**, donde «el valor a x» está
  definido; en un **campo** (contornos, mapa de color, densidad) no lo está sin nombrar el nivel, y
  dos lectores honestos devuelven números distintos sin que ninguno se equivoque. El costo no fue
  un número mal copiado: fue **declarar un hueco que no existía** — la ficha dijo «el corpus no
  puede responder esto» y el corpus sí podía, con más precisión que la que la ficha pedía. La regla
  (extensión de #195, no reemplazo) vive en `extraction_prompt._media_note` —el nivel es parte del
  localizador (`Fig. N, p. M, contorno del X %`) y dos lecturas que no reconcilian apuntan **primero
  a figura subespecificada**, no a dato ilegible— y en el frente 1 de `audit-note`, donde la
  bifurcación *omisión de la síntesis / hueco real* pasó a tener tres ramas.
- **19 filas en 13 notas** tenían un `|` crudo en la prosa que va a una celda: la fila se parte, las
  celdas de más no se renderizan y una afirmación citada **y verificada** queda invisible mientras
  el lint sigue contando su fila. La regla (INV-99) existía y vivía sólo en el skill
  `verify-citations`, para la otra tabla → hoy escapa `lib_config.escape_cell` en el cosechador
  (único punto de escritura): `\|` fuera de la matemática, `\vert` adentro — escapar a ciegas
  convierte 19 filas invisibles en 19 fórmulas equivocadas, que es peor (la fila invisible se nota,
  la fórmula alterada no).

## Próximas pruebas (anotadas, no corridas)

Salen de lo medido arriba y están ordenadas por lo que cuestan. Las pruebas 1 y 4 de la lista anterior
**ya se corrieron** el 2026-08-25 (ver los bloques (b) y (c)); las dos dieron negativo, y lo que salió
a favor —Sonnet como extractor— quedó medido pero con n = 5.

1. **`verify-citations` acotado sobre τ Ceti.** La ficha tiene 145 pares en 52 fuentes; las 6 fuentes
   que sostienen las disputas y el inventario concentran 61 pares — ~1/8 del fan-out completo. Es lo
   único que le falta a τ Ceti para cerrar (`lint --cierre` está en 1 sólo por eso).
2. **Haiku en el fan-out de `verify-citations`.** Éste **sí** tiene gate: `bench_verify seed` +
   `score` siembra citas falsas deterministas y mide el recall contra el 80 % medido con el modelo
   actual. Es el único experimento de modelo de esta lista que es decidible sin juez.
3. **Confirmar Sonnet como extractor sin pagar otro barrido.** El bloque (b) mide n = 5 sobre una sola
   estrella. El gate barato **no** es repetir el experimento: es correr el **próximo ingest real** con
   Sonnet en el paso 3 y comparar su salida de `lint` y de `verify-citations` contra los números ya
   pagados de HD 40307 (72 pares / 16 fuentes → 70 soportada, 2 no-soportada, 0 contradice). Si el
   perfil de fallas no se mueve, el cambio se sostiene; si aparecen no-soportadas nuevas, se revierte.
   Costo incremental: cero — ese ingest hay que correrlo igual.
4. **Dos pasadas sobre el paper denso.** Idea del usuario, sin medir: si el modo de falla de Sonnet es
   cobertura y no invención (que es lo que mostró el bloque (b): 0 valores falsos en los papers donde
   hubo juez), entonces en un `.txt` grande dos corridas de Sonnet podrían cubrir más que una de Opus
   y seguir costando menos (2 × 35 % = 70 %). **No probado**, y con un supuesto fuerte: que las dos
   corridas se pierdan cosas **distintas**. Si se pierden las mismas, la segunda pasada no compra nada.
5. **Auditoría adversaria del diff de esta sesión.** Toca dos redes del propio framework (el gate de
   mutación y el mapa de trazabilidad), o sea código que después juzga a todo lo demás.

### Deuda declarada, no resuelta

- ⛔ **Falso negativo del `grep` que genera `extraction_prompt.py`.** El patrón `\bCet` **no matchea
  `tauCet` pegado**, que es como los PDFs escriben el nombre en las filas de tabla — no hay borde de
  palabra entre `tau` y `Cet`. Medido en Jofré 2015: las 21 filas de τ Cet de las Tablas A.1-A.10 y
  B.1-B.10 son invisibles a los siete patrones que el contrato manda correr, y ahí vive **todo** el
  contenido cuantitativo del paper. Lo detectaron por su cuenta dos extractores (Opus y Sonnet)
  re-corriendo el grep sin `\b`. Es un defecto de `_anclado()` y aplica a cualquier estrella cuyo
  nombre se pegue al prefijo en una tabla. La frontera existe por INV-100 (sin ella `Cet` matchea
  «Princeton»), así que el arreglo no es sacarla: es emitir **las dos** variantes, anclada y pegada.
- **`tools/mutar.py` nunca se muta a sí mismo**: `archivos_del_diff` filtra por `scripts/`. El código
  que decide qué se muta es el único que no se muta.
- ~~**La población del ratchet de mutación son 338 medidas + 5 contadas sin barrer**: el `--todo` no
  se re-corrió.~~ **Saldada**: `tools/mutacion-ratchet.yaml` declara hoy `medido_en: 2026-08-27`,
  alcance *«TODO `scripts/` — 416 funciones, barrido completo (`--todo --ratchet`)»* y `techo: 3`.
  ⚠ Lo que **no** se puede re-medir es si 338+5 y 416 son el mismo universo contado distinto o dos
  universos: son mediciones de árboles distintos y la regla es declarar la discrepancia (método #5).
  ⚠ Y desde el 2026-08-27 el gate **no corre solo** (ver la cadencia en `CLAUDE.md`), así que el
  ratchet envejece por decisión declarada, no por olvido.
- **La corrida de τ Ceti no prueba el framework** sino la paráfrasis que el agente hizo de él. Desde
  INV-100 el paso 3 es reproducible; antes no lo era, así que no hay línea de base con la que
  comparar. Los bloques (b) y (c) del 2026-08-25 **sí** usan el prompt canónico en las dos ramas, así
  que esa deuda queda saldada para esas dos mediciones y sigue abierta para el baseline Opus original.

## Recorte de `CLAUDE.md`, pasada 2 (2026-08-30) — el postmortem que salió de la sección de curación

Movido acá al aplicar la regla de escritura del ratchet (`tools/doc-size-ratchet.yaml`): la regla y
su ancla quedan en `CLAUDE.md`; el caso medido vive donde se lo puede consultar.

- **#217 / #215 — por qué `drop_core` re-apunta `pdf:`/`fulltext:` él mismo.** Antes de #215 el
  drift ficha↔disco se curaba solo en el próximo `make_notes`. El fix de #215 filtra los dropeados
  **antes** de escribir notas —correcto: no queremos resucitar el dropeado— así que esas notas ya no
  vuelven a pasar por el re-estampado y el drift pasó de transitorio a **permanente**. No es un
  argumento contra #215: la limpieza la tiene que hacer quien borró, que es el único que sabe qué
  borró. La categoría *«vista fechada sin fuente en disco»* existe porque ninguna otra red lo ve: el
  ancla de fuente (D-20) no se entera —el archivo no cambió, **desapareció**— y `## Citas no
  verificables` mira los bibcodes citados desde conceptos/queries, no los pares ya verificados de
  una ficha. Es agudo en la rama «la nota se conserva porque el paper pertenece a **otro sujeto**»,
  donde el paper sí puede estar citado en la ficha de esa entidad.
  ⚠ Hasta 1.73.0 `CLAUDE.md` decía sólo *«la nota no se borra sola»*, que describe **una** de las
  dos ramas: la doc callaba un borrado irreversible.
- **#266 — el `via` equivocado en la doc.** Hasta 1.103.x `CLAUDE.md` enunciaba **un solo**
  vocabulario debajo de una tabla que muestra los dos, así que mandaba escribir
  `via: descubrimiento` en `extra_core` — que el loader rechaza duro. Es exactamente el defecto que
  #162 cerró en el `help=` de la CLI, sobreviviendo en la fuente que un agente lee **antes** de
  editar `stars.yaml` a mano.
- **#206 — por qué `via` en `sources:` es binario.** Hasta 1.72.0 existió `reporte` para el caso de
  la lista de papers traída por el usuario, y partir esa categoría hacía que el campo dejara de
  contestar su propia pregunta: había que **sumar dos casilleros** para saber cuántos papers
  entraron por decisión humana.
- **#111 — el cuadrante mudo, medido.** Sobre una bóveda real: los 40 papers que tenía y una bóveda
  nueva no, **entraron los 40 a mano**, y su config no permitía saber cuáles había pedido el
  usuario. Y sin la salida hacia la ingesta (`triage --accept-source`) el descubrimiento se cortaba
  en el hallazgo: proponía el paper y bajarlo quedaba como trabajo manual — que es exactamente por
  qué una bóveda con búsqueda peor puede terminar con más papers que una con búsqueda mejor.

## 2026-08-30 · Descubrimiento de un tema de método que cruza disciplinas (#290/#293/#294)

**Qué era.** Primera cascada de un tema nuevo (`ica-ruido`: ICA ruidosa + blanqueo heterocedástico)
en una bóveda real, contra un **gold standard de 25 papers** curados a mano en otra bóveda.

| Qué se midió | Número | Salvedad |
|---|---|---|
| Recuperación de la cascada con `topic:` escalar y 8 `seed_terms` | **15/25** | 1141 registros tras dedup |
| De los 15 recuperados, por backend | openalex 11 · arxiv 2 · ads 2 | consistente con el 8/8 de #104 |
| De los 10 perdidos, misma familia (blanqueo heterocedástico) | **6** | repartida en **5 topics** de OpenAlex |
| Perdidos **sólo** por el techo de 200 del slice | **2** | están en OpenAlex, con el topic correcto, fuera del top 200 por citas |
| `heteropca` / `heteroskedastic` / `dyson` / `alpcah` en los 1242 registros | **0 hits** | no es ranking ni truncamiento: no entran al universo |

**El eje que decide.** El valor del filtro por topic **escala con la ambigüedad del término**: en
`meta.count` sin filtro, `HeteroPCA` tiene **9** works en todo OpenAlex (∩ topic: 4), `heteroskedastic
PCA` **79** (8), `quasi-whitening` **103** (15) — ahí el filtro sólo puede sacar señal —, mientras
`matrix denoising` tiene **4823**, `weighted PCA` **6790** y `gaussian moments` **13.396**, donde es
lo que hace usable el ranking. De ahí que se **mida por término** en vez de aplicarlo a ciegas.

⚠ **Salvedad de la primera fila:** el mismo trabajo cae en topics distintos según sea preprint o
publicado, así que «5 topics para una familia» describe la taxonomía tal como está, no un error de
declaración.

**Qué cambió.** `topic:` acepta lista (OR); el slice pagina hasta `rows_por_termino`, que pasa a ser
campo del tema y flag; el filtro por término se decide con el conteo y se declara; `--topics`
distingue su vacío de su fallo.

## 2026-08-30 · Tanda del carril de lente y schema (#289/#291/#292/#295/#296/#297)

| Qué se midió | Número | Salvedad |
|---|---|---|
| Universo de la query de un tema de método, con y sin `fq=database:astronomy` | **306 → 6946** (22,7×) | `title:"noisy ICA"` da **0** con el fq y 12 sin él (#295) |
| Gold standard del tema alcanzable por la mitad ADS, con fq / sin fq | **4/10 → 10/10** | verificado término por término: no es problema de la query |
| No-core del probe de un tema, por motivo | **261** sin la faceta propia · **32** pasan la faceta y mueren en la puerta · 10 doctype | los dos primeros piden acciones **opuestas** (#289) |
| Papers que el tema existía para capturar, dentro de esos 32 | **2** | `2012PASP..124.1015B`, `2015MNRAS.446.3545D` |
| Alternativas de la faceta de un tema real | **27**, una con población **cero** y una duplicada | `non-?gaussianity matrix`: 0 archivos con la frase, **29** con `non-gaussianity` (#291) |
| `#N` del repo contrastados contra los issues de GitHub | **247** distintas, **1** colgada | la colisión de #288 ocurrió **en vivo** (#292) |
| `pdf_source` sobre las notas de paper de una bóveda | 85 `eprint` · 50 ausente · 1 `ads` · **2 con prosa** | el `eprint` es la exención que apaga el chequeo de cita textual (#296) |
| Notas `eprint` y pasadas de red registradas | **85/138 (62 %)** · `_red.yaml` **no existe** | ninguna de las seis caducidades estaba chequeada (#297) |

⚠ **Salvedad transversal:** todas salen de **una** bóveda (`Almagesto-Tesis`, 2026-08-30) y de un
solo tema de método. Lo que sostienen es que el modo de falla **existe y es alcanzable**, no una
frecuencia poblacional.

## 2026-08-30 · Segunda tanda de la auditoría (#298–#304)

| Qué se midió | Número | Salvedad |
|---|---|---|
| Población real del detector de versiones | **3 de 138 notas** (2 %) | 79 tienen `arxiv_id`; sólo 3 tienen bibcode **de eprint**, que es su filtro correcto por contrato (D-19 es sobre identidad) |
| Notas con `pdf_source: eprint` | 85 de 138 (62 %) | de ésas, **82 con bibcode publicado**: leen el preprint sin problema de identidad, o sea invisibles para D-19 |
| Fuentes off-ADS con `pdf:` repuntado tras una ingesta real | **0 de 8** | la conducta (proponer y parar) es correcta; la doc prometía lo contrario en dos lugares |
| PDFs rescatados a mano que quedaron linkeados en la nota | **0 de 4** | `pdf:` se escribía sólo al crear el stub; el lint imprimía la ruta exacta y ningún comando la aplicaba |
| Core de un tema **sin puerta registrada** | **12 de 15** | 8 con `via: manual` (hardcodeado) y 4 con `via: usuario` (de la config), reparto decidido por si ADS devolvió el bibcode |
| Roll-up de un concepto cerrado: promesa vs síntesis | **89 papers · 30 citados** | 32 con vista fechada → **57 reclamados y sin leer**, indistinguibles entre sí sin la columna `Estado` |
| Aristas del grafo que salen de `index.md` + `log.md` | **7 %** (65 de ~1000) | 50 de las 54 del índice apuntan a papers, y su sentido es «está en el top 50 por citas» |
| `STATUS.md` de una bóveda real | **537 líneas**, 12 encabezados fechados, **4** listas de próximos pasos | una de las cuatro contradice un estado posterior del mismo archivo |

⚠ **Salvedad transversal:** todo sale de la misma bóveda (`Almagesto-Tesis`, 2026-08-30). Sostienen
que el modo de falla existe y es alcanzable, no una frecuencia poblacional.

## 2026-08-30 · Tercera tanda: la lente de lectura y las dos resoluciones (#305–#308)

| Qué se midió | Número | Salvedad |
|---|---|---|
| Papers de un tema con el PDF **sólo bajo otro slug** | **7 de 31** | el prompt mandaba `fuente: abstract` sobre los 7; son el núcleo fundacional del tema y dos libros de 500+ páginas |
| Cosechas donde `merge_frontmatter_list` rechazó una lista flow **multilínea** | **1 de 31** | lo perdido fue `weighted PCA`, alias del tema: el único `methods` con destino en el roll-up |
| Ejes globales contestados en un tema de método (32 extracciones) | `method` 32 · `ml` 30 · `simulation` 28 · `detection` 16 · `rv`/`activity`/`planet`/`discovery` **7** | los mismos 7: las únicas fuentes astro del corpus |
| Ejes que el tema necesitaba y se preguntaron | **0** | aparecieron igual en `aporte`, desordenados y sin clave con la que compararlos |

⚠ Dos de los 7 del primer caso los detectaron **subagentes que desobedecieron el prompt** y fueron a
buscar el PDF igual, verificándolo con las funciones del propio framework. Que acertaran es suerte,
no red: un extractor obediente habría entregado 7 vistas `fuente: abstract` sobre papers con el PDF
en disco, y ninguna capa aguas abajo lo habría marcado.

## 2026-08-30 · El ciclo de la lente, medido sobre una ingesta completa (#310)

**Qué era.** Ingesta del tema `ica-ruido` (ICA con ruido + blanqueo heterocedástico) en
`Almagesto-Tesis`: 32 extracciones, corpus mixto estadística/signal-processing con minoría astro.

| Qué se midió | Número | Salvedad |
|---|---|---|
| Alias pegados a la lente de sujeto en la primera pasada | **14** | amplia para que entren las dos mitades del campo, enfocada para que ninguna vista sea un resumen |
| Papers que **no mencionan ICA ni una vez** | **10 de 32** | las dos mitades del tema no se citan entre sí: el puente lo hace el lector, así que toda afirmación que lo cruce es `inferencia` |
| Ejes producidos por el contraste cross-paper | **6 ejes · 43 filas** | **ninguno** declarado antes de leer |
| Posturas incompatibles sobre el supuesto más básico del modelo | **4** | Σ conocida / desconocida-se-evita / desconocida-se-estima / conocida por dato |
| Objetos distintos nombrados por el mismo término del tema | **5** | por muestra, por coordenada, por dato, doble, y ARCH en el tiempo |
| Ejes globales que 25 de 32 papers no podían contestar | **4 de 8** | `rv`, `activity`, `planet`, `discovery`: poblados sólo en los 7 papers astro |

**Los dos hallazgos que la lente libre habilitó** —y que con ejes declarados de antemano se habrían
perdido, porque las celdas habrían vuelto contestadas—: (a) que las dos mitades del campo no se
citan entre sí; (b) que la *«heteroscedasticity»* de uno de los papers es varianza condicional
**ARCH en el tiempo**, no ruido entre canales — polisemia **dentro** del propio tema.

**Qué cambió.** Los ejes pasan a ser del tema (#307), la segunda lectura se puede pedir (#308), y el
ciclo completo queda escrito con su invariante de procedencia (INV-146): toda vista declara los ejes
vigentes al leerla, así que cambiar los ejes produce un **diff computable** y no una
re-interpretación silenciosa.

## 2026-08-30 · Los dos artefactos que el framework declaraba descartables (#311, #312)

| Qué se midió | Número | Salvedad |
|---|---|---|
| Extracciones de un tema, en `build/` | **33** · 988 KB · ~680 valores con localizador | costaron ~**4,9 M tokens** de subagente leyendo PDFs |
| De ésas, versionadas (`git ls-files build/`) | **0** | `build/` es scratch por `.gitignore`: no viajaban a ninguna otra máquina |
| Libros cuyo `alcance` se amplió en `themes.yaml` | **2** | la nota siguió declarando el alcance viejo: ningún backfill lo re-estampa |
| Valores nuevos que la re-lectura extrajo de capítulos «fuera de alcance» | **37** | la nota los publicaba en su vista mientras afirmaba que no entraban |

**Qué cambió.** Las extracciones pasan a `vault/raw/extraccion/<slug>/` (versionadas, con migrador y
detector bloqueante); `alcance`/`unidad_cita` se re-estampan desde la config
(`--restamp-alcance`) y el lint reporta el desfasaje. ⚠ Lo que **no** se hizo, anotado en #312: que
`vistas[]` registre bajo qué **alcance** se leyó, que es lo que haría computable el delta *«esta
vista es incompleta respecto del alcance vigente»* — hoy `lente` guarda los ejes y no el alcance.

## 2026-08-30 · La cascada de adquisición sin arXiv (#313)

| Qué se midió | Número | Salvedad |
|---|---|---|
| Fuentes `pending: paywall` de la bóveda | **2** | es la **población entera** de pendientes, no una muestra |
| De ésas, obtenibles | **2 de 2** | una en la biblioteca del usuario; la otra en arXiv (`2303.16535v2`, mismo título y mismos tres autores, verificado abriendo el PDF) |
| `grep -ci arxiv` sobre `resolve_pdf` | **0** | en un repo con `search_arxiv.py`, `fetch_arxiv.py`, y `fetch_pdf` probando `EPRINT_PDF` **primero** en el carril ADS |

⚠ **n=2 es chico y el 2 de 2 no es estadística**: lo que sostiene es que el modo de falla es
**sistemático** —hay un depósito entero que la cascada no miraba— y que el motivo escrito en el
registro (*«OpenAlex/Unpaywall no resolvió copia libre»*) era cierto y engañoso a la vez: describía
lo que se consultó, no lo que hay.

**Qué cambió.** Tercera rama (arXiv por **título exacto**, nunca aproximado), la procedencia en el
motivo —un eprint no es la versión publicada, y eso decide cómo se citan sus números (#57)— y el
mensaje de cierre enumerando lo consultado. Se mantiene la doctrina: **propone y para**.

## 2026-08-30 · El paso sin herramienta, y contra qué se decide una cita (#314–#317)

**Qué era.** Síntesis del concepto de un tema de 32 papers, escrita desde un digest ad-hoc de las
extracciones (`valor[:200]`, `regimen[:150]`), y su verificación posterior.

| Qué se midió | Número | Salvedad |
|---|---|---|
| Pares verificados | 139 | `soportada` 115 · `contradice` 12 · `no-soportada` 8 · sobregeneraliza 40 |
| **Citas fabricadas** | **2** | las dos en el **carácter exacto** donde el digest cortó; los JSON tenían la frase entera (354 y 326 caracteres) |
| **Atribuciones colectivas falsas** | **6** | de agrupar varios bibcodes bajo una glosa compartida |
| Filas del inventario con cita, y con ≥2 bibcodes | 61 · 8 | contra 11 · 0 en el hub escrito paper por paper |
| Señal del chequeo de cita verbatim contra el `.txt` | **2 de 17** (11 %) en un concepto · **0 de 35** en otro | los otros son citas correctas que el `.txt` degradado no contiene |
| De los 35 del hub, por causa | 21 `.txt` degradado · **12 atribución por bloque** · 2 limpias | las 12 en **cuatro líneas** que atribuyen bien en prosa |
| Control: nota escrita paper por paper | **0 defectos reales** sobre 35 citas re-verificadas contra el PDF | |

⚠ **El defecto vivía sólo en la nota del concepto**: el PDF, el JSON de extracción y las 32 notas de
paper estaban bien. Es decir, falló **el único eslabón de la cadena sin herramienta**.

**Qué cambió.** `scripts/contrast.py` (nunca trunca una cita, agrupa por campo, arrastra la
procedencia, una fila = una fuente, y `--validar` cruza la nota contra las extracciones); el chequeo
del lint decide contra la extracción antes que contra el `.txt` y prueba cada cita contra **su**
fuente; y la regla queda escrita: *la cita se copia entera o se parafrasea sin comillas*.

## 2026-08-30 · Revisión de cierre de la propia tanda (#318–#320)

La otra instancia auditó el commit `789a49c` (v1.130.0) y encontró tres cosas **en el trabajo recién
hecho**, que es exactamente para lo que sirve una revisión de cierre:

| hallazgo | qué era |
|---|---|
| **#318** | el **gate** que #315 §2 y #317 §6 pedían con las mismas palabras quedó sin implementar: la categoría limpia seguía en backlog, así que una operación que fabricó una cita textual cerraba en verde |
| **#319** | `s[:12] if len(s) <= 12 else s` — las dos ramas dan lo mismo: una regla a medio escribir que **ningún test podía matar**, porque no decidía nada |
| **#320** | `extraction_texts` sin memoizar, en un chequeo que corre **por cita**: la misma asimetría que #275 arregló en la función de al lado, agravada porque esta tanda movió `_sources_for` al loop |

⚠ Los tres son de la clase que el barrido de mutación **no** ve: un gate que falta, una expresión
que no decide, y un costo. Ninguno rompe un test — y por eso hacía falta que alguien leyera el
commit.

## 2026-08-30 · El gate de #318, aplicado a una bóveda real (#321)

Corrida de v1.132.0 sobre `Almagesto-Tesis` tras `--migrate-extracciones`: 122 extracciones, 135
citas con fuente chequeable, **32 hits** de `cita_inventada`. Clasificados volviendo a la nota (no al
reporte):

| clase | n | veredicto |
|---|---|---|
| la frase está verbatim en la extracción de **otro** bibcode | **6** | verdadero — error de atribución |
| coincide el arranque y **diverge la cola** | **6** | verdadero — el patrón de #314 |
| no está en ninguna extracción | **20** | **mezclado**: paráfrasis entrecomilladas (verdadero) y citas legítimas leídas del PDF (falso) |

⛔ Entre los 20 estaba una cita que **#315 usa como ejemplo de cita correcta**, confirmada verbatim
contra el PDF por el fan-out. La premisa del gate —*«si no está en el JSON, la fabricó el
sintetizador»*— sólo valdría si la extracción contuviera toda frase citable del paper, y es una
transcripción **selectiva y lenteada** (#188) sobre un corpus que se cita **del PDF** (#205).

⚠ **Nota de método**: el reporte trunca el extracto a 70 caracteres (#226), así que clasificar desde
el reporte da un resultado falso — la primera pasada de esta medición se equivocó por eso.

**Qué cambió.** El gate bloquea sólo con **evidencia positiva** (la frase bajo otro bibcode, o el
prefijo largo con la cola divergente); el silencio de la extracción baja a backlog con su propio
mensaje. Doctrina: **evidencia positiva bloquea, el silencio se declara** (D-43).

## 2026-08-30 · Las 12 verdaderas eran de COPIADO, y el control no tenía momento (#322/#323)

Misma corrida que arriba, releída por su **causa** en vez de por su clase. Los 12 verdaderos
positivos se reparten en dos, y las dos son la misma operación:

| causa | n | qué pasó materialmente |
|---|---|---|
| atribución movida | 6 | la frase de un paper quedó bajo el `[[bibcode]]` de otro |
| cola alterada | 6 | el arranque coincide y el final no: se completó al re-escribir |

⛔ **Ninguno es un error de comprensión.** Los 12 son errores de **mover una cadena de un archivo a
otro** — la clase de tarea que un script hace perfecto y un LLM mal. El paso que los produce estaba
en el propio diseño: `--filas` emitía un **esqueleto** y el sintetizador tipeaba la cita adentro.
**Qué cambió (#322):** la fila sale con la cita ya adentro (cadena del JSON, su `[[bibcode]]`, su
localizador, escapada con `escape_cell`); el sintetizador escribe **la glosa** y elige qué filas
entran.

**Y el control existía sin momento (#323).** `--validar` hacía exactamente la comparación decisiva,
pero tomaba una nota por vez y **ningún skill lo nombraba**: la nota que produjo toda esta serie
cerró con `verify-citations` completo y `lint --cierre` en 0 **con las 12 citas adentro**. La
comparación que las cazaba en segundos estaba escrita y no se corrió, porque nada decía que había
que correrla — *una capacidad sin momento de ejecución no es un control*. Hoy hay barrido
(`--validar-todo`, con población declarada, no-evaluables declarados y exit ≠ 0) y los cuatro skills
que escriben prosa citada lo corren **antes** del fan-out: el `grep` cuesta segundos y el verify son
N subagentes leyendo PDFs (#315).

## 2026-08-30 · La misma regla, dos implementaciones, y ya divergían (#324)

Verificación de #321–#323 sobre `Almagesto-Tesis` (v1.134.0, 163 notas, 2232 citas). El fix de #321
queda confirmado: **32 → 12 hallazgos**, y los 12 coinciden con la clasificación independiente. Lo
que apareció es que `lint.collect` y `contrast.validar` decidían lo mismo con código separado y
daban **12 y 13** sobre el mismo corpus el mismo día.

El de más era un falso positivo:

```
hd_40307 L602: «only available in electronic form at the CDS» está verbatim en la extracción de
2009A&A...497..563N, no en la de 2016A&A...585A.134D: atribuida a la fuente equivocada
```

| | en su `.txt` | en su extracción |
|---|---|---|
| `2016A&A...585A.134D` (el que la nota cita) | **True** | False |
| `2009A&A...497..563N` (el que `contrast` proponía) | False | True |

**La cita es correcta**: está verbatim en el `.txt` del paper que la nota cita. Lo que pasa es que la
extracción —selectiva y lenteada (#188)— no la transcribió, y la frase es *boilerplate* de A&A que
aparece en varios papers del corpus. El lint no la marcaba porque prueba contra el `.txt` de la
fuente citada **primero**; `contrast` iba derecho a comparar extracciones.

⛔ Es **la misma forma de error que #321 acababa de arreglar** —juzgar contra un artefacto que no
contiene lo que se le pregunta— desplazada del lint a la herramienta, y pega más fuerte ahí: desde
#323 `--validar-todo` es paso de cierre obligatorio con exit ≠ 0, así que un falso positivo **frena
operaciones**. El boilerplate compartido (CDS, agradecimientos, descripción de instrumento) es
justo donde más iba a pasar.

**Qué cambió.** Una sola implementación (`lib_config.quote_verdict`) con el orden explícito —el
`.txt` de su fuente, la extracción, el `.txt` que parte la cita, la evidencia positiva— y un solo
`CITA_PREFIJO`. El número estaba duplicado con un comentario que **declaraba** que tenían que
coincidir y nada que lo chequeara (`grep CITA_PREFIJO tests/` no devolvía nada): regla de método
nº 2, y el test de paridad compara **las dos salidas sobre el mismo insumo**, no las dos constantes
—comparar constantes no habría cazado esta divergencia, que era de **orden**—.

⚠ Dos guardas del código nuevo salieron **redundantes** en la mutación de guardas (`fuentes and …`
implicado por el `any(...)` de al lado): se sacaron en el momento, que es la regla de #319.

## 2026-08-31 · El dueño de la cita, y la matemática que se pegaba (#325/#326)

Corrigiendo los 12 hallazgos de `cita_inventada` en `Almagesto-Tesis` con v1.135.0: **6 son defectos
reales** y **6 son artefactos de `quote_owner`**.

### #325 · la adyacencia estaba documentada y no exigida

El docstring declaraba la convención `«…» [[bibcode]]`; el código tomaba el primer link posterior a
**cualquier** distancia:

| nota | dueño asignado | distancia al link |
|---|---|---|
| `ica-ruido` L282 | `2013Voss` | **131** caracteres |
| `ica-ruido` L362 | `1998Cichocki` | 12 |
| `ica` L163 | `2024MNRAS.535.2562C` | **247** |
| `hd_40307` L274 | `2016A&A...585A.134D` | **436** |
| `hd_40307` L315 | `2017MNRAS.468.4772S` | **100** |
| `hd_40307` L368 | `2015MNRAS.452.2745S` | **657** |

El caso claro es una fila cuya celda *Fuente* es `[[2015Voss]]` y cuya celda de prosa termina
*«…atribuyendo ese paso a [[2013Voss]]»*: la nota atribuye **bien**, y la mención 131 caracteres
después ganaba. Es el defecto que #316 se abrió para arreglar —*«un párrafo que contrasta dos
fuentes queda marcado por decir la verdad»*— sobreviviendo dentro del mecanismo que lo arregló, y
ahora con más peso: la categoría bloquea `--cierre` (#318) y `--validar-todo` es paso obligatorio de
cuatro skills (#323). ⚠ Y el arreglo aparente —reatribuir la cita al bibcode que el reporte nombra—
**rompe la nota**: en L282 movería la cita al revés de lo que dice la fuente.

Las otras 6 son alteraciones reales, cada una distinta (un régimen comido *«in the noiseless case»*,
un *«do not become orthogonal and»* → *«that are not orthogonal»* que **invierte el sentido**, un
*«a priori»*, un enumerador, una cola continuada 90 caracteres). O sea: el detector de #321
**funciona**; lo que fallaba era a quién le preguntaba.

### #326 · la matemática se borraba y las mitades se pegaban

`quote_fragments` parte en la elipsis con un argumento explícito —«A … B» no está verbatim en
ninguna parte, así que se chequea por piezas—. El `$…$` recibía el trato **opuesto**:

```
cita:      «Reaching such a high $S/N_{cont}$ is not achievable for any star and telescope …»
fragmento: 'reaching such a high is not achievable for any star and telescope …'   ← UNA pieza
```

Esa cadena no está en ningún `.txt`, porque el archivo tiene `s/ncont` en el medio — y no puede
estarlo nunca. **412 de 3036 citas** de una bóveda real llevan `$…$` (14 %), y no por estilo:
`CLAUDE.md` **manda** esa notación en `vault/wiki/`. Consecuencia: el paso 1 de `quote_verdict`
(*¿está en el `.txt` de su fuente?*) **nunca** podía dar True para esas citas, así que caían siempre
a la comparación contra la extracción y podían salir `alterada`.

⚠ **Nota de método:** este bug es **invisible mientras la cita esté mal** —el hallazgo se explica por
el defecto real— y **sólo aparece al corregirla**, porque el detector no se apaga. Un gate
verificado únicamente sobre corpus defectuoso no lo caza: hay que verificar también el camino de
salida.

## 2026-08-31 · El re-estampado que no podía escribir, y las propuestas sin superficie (#327/#328)

### #327 · 5 de 5, o sea el 100 % de la población

`stamp_scope.upsert` reemplazaba **la primera línea** de la clave. El valor real es un escalar
multilínea:

```yaml
alcance: caps. 2-3 (formulacion del problema y metodos de separacion); 161 paginas,
  el resto es aplicacion a audio y no entra      ← queda huérfana bajo la clave siguiente
```

El frontmatter dejaba de parsear y la guarda de #244 —bien— rehusaba escribir. Medido: **5 notas
tienen `alcance` y las 5 son multilínea**, y no por accidente de formato: un `alcance` dice qué
capítulos de un libro entran, así que es largo **por definición**. O sea, #312 no funcionaba en
ningún caso real, y lo que #312 arregla no es un hueco sino una **afirmación falsa** — la nota seguía
declarando que ese material no entra mientras la vista lo publicaba.

⚠ **Nota de método:** el gate de #312 no lo cazó porque sus tests usan un `alcance` **corto**, que
cabe en una línea. La forma que hace fallar a la función es justamente la que la función existe para
manejar — un caso de test que no representa a su población.

**Auditoría de los otros re-estampadores** (lo pedía el issue): `stamp_keywords` es **add-only**, así
que cuando llega a reemplazar el campo está vacío (una línea); `_set_campo` sólo escribe `bibcode` y
`bibstem`, que son cortos; `stamp_fulltext`/`restamp_pdf_links` escriben rutas, que no se envuelven
porque no pasan por el serializador. **Ninguno tenía defecto vivo**: se les pasó la definición
compartida por #222/#324, no porque estuvieran rotos.

### #328 · las propuestas eran cinco lugares que nadie miraba junto

| propuesta | dónde vivía | quién la veía |
|---|---|---|
| ampliar el `alcance` de una fuente larga | `hueco` del JSON de extracción | nadie |
| `refuta:` (#212) | `vistas[].refuta` + backlog del lint | el lint, mezclado |
| eje descubierto en 3b (#307/#310) | la conversación | nadie |
| celda vacía del inventario (#310) | la nota | quien la lea |

`scripts/proposals.py` junta las tres que están en disco, con el motivo **textual** de quien las
escribió, y **declara** la que no puede barrer. La distinción que hace falta y el lint no puede
hacer: la deuda se **agenda** y persiste en el reporte hasta cerrarse; la propuesta necesita que
alguien **firme** y, si nadie la lee cuando aparece, **se pierde**.


## 2026-08-31 · El cuarto consumidor de la curación, otra vez (#329)

`contrast.extracciones` juntaba el material del **paso 3b** con un `glob` sobre
`vault/raw/extraccion/<slug>/*.json` y nunca lo cruzaba contra `lib_config.dropped_from_subject`.
Mismo molde que #215: la comprensión de *«qué papers son de este sujeto»* vive en **una** función y
el cuarto consumidor no recibió copia.

| consumidor | ¿cruza `dropped_from_subject`? |
|---|---|
| `make_notes.papers_universe` · `concept_rollup_rows` · `write_paper_notes` | ✅ |
| `query_ads.excluidos_del_sujeto` | ✅ |
| `contrast.extracciones` (paso 3b) | ⛔ **no** |

**Medición** (bóveda `Almagesto-Tesis`, 2026-08-31, framework v1.137.0):

| tema | extracciones en disco | dropeados | extracciones de dropeados servidas al 3b |
|---|---|---|---|
| `ica` | 51 | 21 | **13 (25 %)** |
| `ica-ruido` | 32 | 0 | 0 |
| `hd_40307` | 47 | 0 | 0 |

Los trece no son ruido neutro: son **falsos positivos de polisemia declarados**, y las propias
extracciones lo dicen —*«homonimia de vocabulario, no del dominio de la bóveda»*
(`1982MNRAS.200..361B`, cuyas *independent components* son $\sigma_r$ y $\sigma_\theta$ de un
tensor)—. Servirlos al paso que **produce los ejes** es ofrecerle al agente exactamente el material
que fabrica un eje falso. El contraste que lo vuelve inequívoco: en la misma bóveda
`make_notes.py ica --theme` imprime *«21 paper(s) excluidos del sujeto por `--drop-core`»* y estampa
`Estado: excluido a mano` — la curación era visible en **todas** las superficies menos en la del 3b.

**Los dos carriles no se tratan igual.** El de LECTURA (`--campo`/`--eje`/`--filas`/`--grep`/
`--paper`) filtra; el de VALIDACIÓN (`--validar`, `--validar-todo`) **no**: un paper dropeado sigue
siendo testigo válido de a quién pertenece una frase, y filtrarlo bajaría la población del detector
de #323 fabricando falsos *«mal atribuido»* — la clase de falso positivo que #324/#325 acababan de
sacar de un paso de cierre que **bloquea**. El test que lo fija muere con el arreglo equivocado: al
filtrar el carril de validación, un hallazgo bloqueante real pasa a *«no evaluable»* y el barrido
devuelve `0 ✅`.

Y se **marca**, no se borra en silencio (INV-40/D-43): la línea de población declara cuántas excluyó
—incluido el cero, porque sin ella *«no hay dropeados»* y *«este comando no mira la curación»* salen
idénticos por pantalla— y `--incluir-dropeados` las muestra, cada una detrás de su banner con el
**motivo** del descarte.


## 2026-08-31 · El script ponía las comillas que el extractor no puso (#330)

`--filas` (#322) envolvía **todo** `ground_truth[].valor` en guillemets, y cerraba con un banner que
afirmaba *«la cadena entre «» ya es correcta por construcción: no la re-tipees»*. El campo `valor`
**no** es «la cita»: es lo que escribió el extractor, y llega en tres formas.

**Medición** (bóveda `Almagesto-Tesis`, 2026-08-31, v1.137.0 · 1948 valores no vacíos):

| forma | n | % | qué producía `--filas` |
|---|---:|---:|---|
| **A** · el valor ya abre con `«` | 686 | 35 % | `««…»»` |
| **B** · glosa del extractor **con** la cita adentro | 315 | 16 % | la prosa del LLM publicada como palabras del paper |
| **C** · valor pelado, sin comillas | 947 | 49 % | un dato de tabla presentado como cita |

**1262 de 1948 (65 %)** salían presentando como verbatim algo que no lo era. La clase B es la grave:
*«promedio de las dos líneas»*, *«límite superior; Li no detectado»* no están en el paper — las
escribió el extractor, y con los guillemets del script la nota afirmaba que sí. O sea que **seguir el
procedimiento documentado al pie de la letra inyectaba el defecto**, y lo que inyectaba en la clase B
es exactamente el mecanismo que #322 existe para impedir.

**Y la clase A tocaba el gate de cierre.** `_QUOTE_RE` (`«([^»]+)»`) sobre `««X»»` captura `«X`, con
un guillemet colgado que no existe en ninguna fuente: la cita pasa de verificada contra el `.txt` a
**no evaluable** y el barrido sigue diciendo `0 ✅` — el molde de **#275**, población efectiva que
cae sin que el veredicto lo diga. Medido punta a punta sobre una fuente con `.txt` y sin extracción:

```
cita simple  → 0 alteración · 0 no evaluable · 1 mirada  ✅
cita ««…»»   → 0 alteración · 1 NO EVALUABLE · 1 mirada  ✅
```

En esa bóveda ya hay **2850 de 2984 citas no evaluables (95,5 %)**: margen para perder más no había.
Y no era deuda vieja —hoy tiene **0** ocurrencias de `««`, porque los inventarios vigentes se
escribieron antes de que `--filas` existiera—: lo que estaba por entrar eran 402 filas dobladas en
`ica`, 232 en `ica-ruido` y 52 en `hd_40307`.

**El arreglo es lo decidible sobre el string, y nada más.** El script **no puede saber** si un
`valor` es verbatim —eso lo sabe el extractor—, así que ya no agrega ni un guillemet: la celda sale
tal cual, `contrast.quote_form` clasifica las tres formas y el banner declara **cuántas de cada una
emitió la corrida**, con la instrucción que faltaba: *lo que sale sin comillas no se entrecomilla al
pegarlo*.

⚠ **Lo que NO se hizo, y por qué se declara acá:** la mitad estructural —que el extractor emita un
campo `cita` separado de `valor`, la única forma de que el script sepa qué parte es verbatim— cambia
el schema de la extracción, y #311 dice que una extracción no se regenera sin volver a pagar el PDF.
Queda como propuesta con su evidencia, no aplicada.
