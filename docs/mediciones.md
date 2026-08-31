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

## 2026-08-31 · #331 · el «próximo paso» que dos scripts imprimen no corría en un tema

**Qué era.** `triage.py --sintesis` y `harvest_views` cierran nombrando el paso siguiente con el
slug interpolado y **sin `--theme`**. En un tema, ese comando muere con un `KeyError` sin manejar
(rc 1) **después** de imprimir «Generando notas para …», y el mensaje manda definir en
`stars.yaml` un slug que está bien definido en `themes.yaml`: un operador que sigue la instrucción
agrega una estrella falsa a la config.

**Cómo re-medirlo.** Sobre una bóveda con temas declarados:

```bash
python -c "import sys;sys.path.insert(0,'scripts');import lib_config as c;\
print({k: c.subject_kinds(k) for k in list(c.load_themes()) + [m['slug'] for m in c.load_stars().values()]})"
```

Cada slug que responde `('theme',)` era un sujeto en el que los dos mensajes proponían un comando
que aborta.

| Qué se midió | Número | Salvedad |
|---|---|---|
| Sujetos de `Almagesto-Tesis` (2026-08-31, framework v1.137.0) | 3 (`HD 40307`, `ica`, `ica-ruido`) | — |
| Sujetos donde el remedio impreso **no corre** | **2 de 3** | los dos temas; la estrella nunca vio el defecto |
| Sitios del framework que interpolan el slug sin resolver el flag | 4 | `triage.main`, `harvest_views.harvest` (arreglados); `lint.collect` (el remedio de la cabecera desfasada de un CONCEPTO) y `extraction_prompt.main`, fuera del alcance de #331 |

**Por qué duele más que un mensaje feo.** `triage.py --sintesis` es el **único** canal de la tercera
fecha de la cabecera (INV-82): el detector del lint existía y el hallazgo sólo se podía cerrar si el
operador sabía agregar el flag a mano — el mismo modo de falla que el propio comentario del código
cita como motivo de que ese canal exista.

**Qué cambió.** Una sola implementación de «¿este slug es estrella o tema?»
(`lib_config.subject_kinds`, con su constructor de comando `make_notes_cmd`), usada por los tres
puntos: copiarla habría sido el molde de #215/#324, donde la misma regla escrita dos veces ya había
divergido. `subject_kinds` devuelve una **tupla** y no un ganador: con las dos configs definiendo el
slug no hay precedencia que inventar, y el que pregunta pregunta por la clase que necesita. Y
`subject_refusal` rehúsa **antes** de la línea de arranque, nombrando las **dos** configs
y —cuando el slug está en la otra— el comando que sí corre (D-43: un paso que no puede correr se
declara; no degrada ni revienta).

⚠ **Lo que NO se hizo, y es medible:** el `--theme` no se adivina por el operador. Generar un
concepto es otra operación, no un flag olvidado.


## 2026-08-31 · #334 · la cola de #331: los otros dos sitios

**Qué era.** #331 arregló **2 de 4** sitios que interpolan el slug pelado en un «próximo paso». Los
otros dos son `lint.collect` (el remedio de la categoría *«cabecera `> _Estado — …_` desfasada»*) y
`extraction_prompt.main` (el aviso *«no hay nada que leer»*). El helper que los cierra ya existía:
`lib_config.make_notes_cmd` (INV-141, v1.140.0).

**Cómo re-medirlo.** Sobre una bóveda con conceptos, el slug que el lint le adjudica a cada nota:

```bash
python -c "import sys;sys.path.insert(0,'scripts');import lint;from pathlib import Path;\
print({p.name: lint._entity_slug(str(p)) for p in sorted(Path('vault/wiki/concepts').rglob('*.md'))})"
```

| Qué se midió | Número | Salvedad |
|---|---|---|
| Notas de `concepts/` cuyo `_entity_slug` es el slug de un **tema** | 100 % | por construcción: `_entity_slug` resuelve un concepto **a través de `themes.yaml`**, lo dice su propio docstring. Confirmado en `Almagesto-Tesis` (2026-08-31): `ica.md → 'ica'`, `ica-ruido.md → 'ica-ruido'` |
| Población de la categoría en esa bóveda, hoy | 0 | un remedio roto **esperando su primer caso**, no un daño en curso |
| Sitios que interpolan el slug sin resolver el flag, tras #334 | 0 de 4 | `grep -nE 'make_notes\.py \{' scripts/*.py` deja 7 líneas, y ninguna es un «próximo paso» sin resolver: 5 son el literal `{slug}` de las secciones estampadas de `make_notes` (texto de la nota, no un comando; el del roll-up de tema ya trae `--theme`) y 2 son remedios del lint cuyos loops recorren **sólo `load_stars()`** |

**Qué NO cambió, y por qué importa.** La primera mitad del aviso de `extraction_prompt` —
`fetch_pdf.py <slug>`— es correcta: `fetch_pdf` toma el slug pelado y **no tiene** `--theme`.
Arreglar «a ojo» las dos mitades de la misma línea es exactamente cómo se rompe; hoy hay un assert
propio que lo fija.


## 2026-08-31 · #335 · `mutar.py --guardas` daba el mismo mensaje para dos causas opuestas

**Qué era.** Un `--solo` sin nada que mutar salía siempre como *«no tienen guardas en `<mod>` (o no
existen)»*. Las dos causas piden acciones **opuestas**: si la función está en `EXENTAS` hay que
**mover el condicional a una función propia** (es lo único que hace que alguna red lo mire); si el
símbolo no existe hay que **corregir el nombre**. Es el D-43 que el propio módulo predica dos líneas
más abajo (*«cero mutaciones no es murieron todas»*), aplicado al conteo de mutaciones y **no** a la
resolución de símbolos.

**Cómo re-medirlo.**

```bash
grep -c '^\s*if ' scripts/triage.py                                          # 56
python tools/mutar.py --guardas scripts/triage.py --solo main                # existe, EXENTA
python tools/mutar.py --guardas scripts/lib_config.py --solo make_notes_cmd  # existe, sin condicionales
python tools/mutar.py --guardas scripts/triage.py --solo no_existe_jamas     # typo
```

| Qué se midió | Número | Salvedad |
|---|---|---|
| `if` de `scripts/triage.py` (2026-08-31, v1.141.0) | **56** | `triage.main` los tiene, y el modo contestaba «no tienen guardas» |
| Mensajes distintos que producían los tres casos, **antes** | **1** | texto idéntico salvo el nombre pedido |
| Mensajes distintos, **después** | **3**, uno por estado | los tres siguen siendo `no evaluado` (rc 2): nada se midió, y eso no cambia |

**Consecuencia medida, en vivo.** Al implementar #331 el guard nuevo vivía dentro de `main`, así que
**ninguna red de mutación lo miraba**. El implementador lo movió a una función propia
(`subject_refusal`) *«porque `main` está en `EXENTAS`»* — criterio suyo, no algo que la herramienta
le dijera; el mensaje que sí recibió no distinguía «tu función está exenta» de «te equivocaste de
nombre».

⚠ **Lo que quedó afuera, y es el mismo defecto:** `--dirigida` conflaciona los **dos** casos con un
texto **peor** —`⛔ no existen en triage.py: ['main']`, que afirma algo falso sobre una función que
sí existe—. Reproducible con `python tools/mutar.py --dirigida --solo main scripts/triage.py`.

## 2026-08-31 · El `✅` que se apoyaba en un solo testigo (#341, parte 1)

`contrast.py --validar` / `--validar-todo` cerraba con `0 cita(s) con evidencia POSITIVA de
alteración ✅` sobre **toda** la población que había mirado, sin distinguir que dentro de las que
aprobó hay un subconjunto cuyo respaldo es **una sola lectura del PDF**: la del LLM que hizo la
extracción. Es el paso 2 de `lib_config.quote_verdict` (`txt_degradado`) — la cita está en la
extracción de su fuente y **no** en el `.txt` de esa misma fuente.

⛔ **La discrepancia no es «PDF vs `.txt`»**: el PDF es la fuente y siempre tiene razón. Lo que
cambia es **quién lo leyó** — `pdftotext` (determinista, pero pierde fórmulas, tablas-imagen y
columnas) contra un LLM (ve todo, a veces transcribe mal). Aprobar por el segundo es **el veredicto
correcto** (#205 declara al `.txt` índice degradado, no mal testigo), y aun así es un testigo solo.

**Medido el 2026-08-31 sobre `Almagesto-Tesis`** (163 notas, 3099 citas textuales): **2857 no
evaluables** y, de las **242** restantes que el comando aprobaba, **45 se apoyan en un solo
testigo** — el 19 % de lo aprobado, invisible detrás del `0 ✅`. (El issue reportaba 40 de 169 sobre
un corte anterior de la misma bóveda; el orden de magnitud y la proporción se sostienen.)

La parte 1 no agrega mecanismo: cuenta el veredicto que `quote_verdict` ya emitía y lo nombra en la
línea de población (INV-40), en los **dos** modos. ⛔ **El rc no se mueve** — si lo moviera, el paso
de cierre obligatorio de #323 se frenaría en 45 citas correctas, que es exactamente cómo un gate se
vuelve ruido que se deja de mirar.

⚠ **Lo que NO entra acá:** la parte 2 del issue (emitir la marca `⚠verificar en el PDF` cuando la
cola diverge) sigue **bloqueada por #332 y #336** — medido, sus 6 candidatos de hoy son 6 artefactos
del cortador de columnas, así que emitiría 6 marcas falsas. *(Re-medido con el cortador arreglado en
la entrada de abajo: la señal pasó de **0 de 6** a **3 de 3**.)*

## 2026-08-31 · RE-MEDICIÓN con el cortador arreglado: el `.txt` puede acusar (#333)

**Por qué se re-midió.** Los números de #333 y de #341 parte 2 se tomaron con `deinterleave_columns`
partiendo un párrafo continuo (#332) y con el `$…$` borrado del texto FUENTE (#336). Los dos están
cerrados (1.143.0 / 1.144.0), así que el conteo anterior estaba contaminado por construcción — y su
propio issue lo declaraba.

**Cómo.** Mismo procedimiento y misma bóveda (`Almagesto-Tesis`, 163 notas), corriendo
`lib_config.quote_verdict` de esta versión sobre cada cita `«…»` de ≥ 40 caracteres y clasificando
la población que el paso 2 aprueba (`txt_degradado`, el único testigo). Reproducible con
`python scripts/contrast.py --validar-todo` desde la raíz de esa bóveda.

| Población | Antes (#332 sin cerrar) | Hoy |
|---|---|---|
| Citas miradas | 3099 | 3321 |
| Aprobadas con **un solo testigo** | 45 | **25** |
| ⛔ cola divergente en prosa → *el `.txt` acusa* | 6 | **3** |
| ~ divergencia sobre `$…$` → *el `.txt` no opina* | 0 | 3 |
| · ausencia limpia → no evaluable | 80 | 11 (+ 8 elididas, cortas o sin `.txt`) |
| **Verdaderos positivos entre las acusaciones** | **0 de 6** | **3 de 3** |

Las 20 citas que salieron de «un solo testigo» las recuperó el cortador: hoy están en el `.txt` y las
absuelve el paso 1. Los 3 verdaderos positivos, abiertos uno por uno contra el `.txt` de su fuente:

- `2026A&A...705A.234O` (dos veces en `ica.md`) — la fuente dice «real-world systematics **that are
  not orthogonal** might become entangled» y la extracción transcribió «**do not become orthogonal
  and** might become entangled»: **invierte el sentido**, y es la misma frase que #220 usa de
  ejemplo. La nota copió la extracción, fielmente, y el gate daba `0 ✅` porque su juez **es** la
  extracción;
- `2017MNRAS.468.4772S` (`hd_40307.md`) — la fuente dice «an effective temperature of 4800 K» y la
  extracción le agregó un **«about»** adentro de una cita textual.

**El discriminador, y es el hallazgo de método.** La regla del issue (prefijo largo + cola divergente
en prosa sin matemática) daba **7** candidatas, con 4 falsas. Las 4 divergen **dentro de una
palabra** y las 3 verdaderas en un **borde de palabra**:

| Candidata | Dónde corta el prefijo común | Qué era |
|---|---|---|
| `2017PhRvE..96d2114K` | `…breaks th` + «ereby overcomes» | empalme del `.txt` |
| `2018IEEEA...625336F` | `…implies non` + « identifiability» | guión de corte sin guión |
| `2011Naik` | `…simple and ef` + «ﬁcient» | **ligadura** `ﬁ` (U+FB01) |
| `1998Cardoso` | `…convolutive mix` + « tures» | palabra partida por un espacio pelado |

Es la asimetría que el issue nombra, afilada: **`pdftotext` rompe PALABRAS; un LLM que transcribe mal
cambia PALABRAS.** Con esa guarda la señal es 3/3 y sin ella 3/7 — o sea que el detector nacería con
4 falsos positivos en un gate que desde #323 frena operaciones.

**Qué cambió.** `lib_config.txt_accuses` + el veredicto `txt_acusa`, **no bloqueante**, reportado por
`contrast --validar` y por el lint (`cita_txt_discrepa`, backlog).

**Y con eso desbloqueada, la parte 2 de #341: la marca.** Cuando la divergencia es decidible,
`contrast --validar` **emite** `⚠verificar en el PDF (<las dos colas>, <fecha>)` lista para pegar —la
cuarta de las cinco marcas en línea, que ya existía— y **no la aplica**: cuál de las dos lecturas gana
lo decide quien abra la página. No hacía falta mecanismo nuevo; lo que faltaba era que alguna
herramienta pudiera producirla. El string pasó de `lint.py` a `lib_config.VERIFICAR_PDF_MARK`, y el
test que cierra el circuito pega la marca emitida en una nota y comprueba que la **levanta el lint**:
con dos copias, una herramienta podía proponer una marca que ningún detector levanta.

⚠ **Nota de método sobre esta medición.** El primer barrido de mutación ad-hoc dio dos falsos rojos
al restaurar los archivos: `cp` deja el `.pyc` y el fuente **dentro del mismo segundo**, y la
invalidación de bytecode de CPython compara mtimes con granularidad de segundo, así que el intérprete
siguió corriendo el módulo **mutado** después de restaurarlo. `tools/mutar.py` no tiene el problema
(copia el repo entero a un directorio nuevo). Los números de arriba son los de la re-corrida con
`__pycache__` borrado entre pasos.

⚠ **Salvedades del número.** (a) La bóveda se editó entre las dos mediciones —el caso de `ica.md` que
originó el issue ya está corregido allá—, así que las dos columnas no son un A/B congelado: miden la
bóveda de su día. (b) 3047 de las 3321 citas salen `no_evaluable` porque su bloque **no tiene ningún
`[[bibcode]]`** — son las `«…»` del cuerpo de las notas de paper, donde el bibcode del sujeto vive en
el nombre del archivo y nunca como wikilink: la población efectiva del gate es **272 de 3321
(8,2 %)**, y eso no lo declara nadie (backlog, no arreglado acá).

sí existe—. Reproducible con `python tools/mutar.py --dirigida scripts/triage.py --solo main`.
**Cerrado en #339**, junto con el tercer sitio (`--trazabilidad`) que esta medición no había mirado.


## 2026-08-31 · #339 · la conflación de #335 vivía en tres sitios, y `tools/` no recibía sus redes

**Qué era.** Cuatro defectos del mismo barrido, los cuatro en `tools/`.

**1 · La regla en tres copias, otra vez.** `_report_unmutable` se escribió en #335 (v1.142.0) y quedó
cableado en **un solo** modo. Los otros dos seguían con el texto fusionado, y en `--dirigida` sin
siquiera el hedge que `--guardas` sí tenía: el mensaje **afirma algo falso**.

| Comando | Antes | Qué es en realidad |
|---|---|---|
| `--dirigida --solo main scripts/triage.py` | `⛔ no existen en triage.py: ['main']` | `triage.main` existe y tiene **56** `if`; está en `EXENTAS` |
| `--trazabilidad --solo INV-126` | `⛔ no existen (o no tienen las dos marcas): INV-126` | fila viva y P0 de `docs/contrato.md`, cuyo propio texto dice *«hay código sin marcar»* — el remedio es **agregar el `@inv`** |
| `--trazabilidad --solo INV-999-NOPE` | idéntico, byte a byte | typo: el remedio es corregir el argumento |

Es el molde de #215/#324/#335: **la misma regla en varios lugares ya divergió tres veces en este
repo.** Desde v1.147.0 los tres modos cierran por `tools/mutar.py::report_states`, que imprime **una
línea por estado no vacío** y **revienta** si un estado con nombres no tiene texto — un salteo en
silencio sería el mensaje fusionado otra vez, sólo que invisible.

| Qué se midió | Número | Salvedad |
|---|---|---|
| Sitios con la conflación, tras #335 | **2 de 3** | `--guardas` era el único cableado |
| Implementaciones del reporte de tres estados, después | **1** (`report_states`) | los estados los clasifica cada dominio (`unmutable_reasons` para símbolos, `unmarked_reasons` para invariantes); lo que estaba duplicado —y es lo que divergía— era el **impreso** |
| Estados de `--trazabilidad --solo`, antes → después | **1 → 3** | `no_existe` · `retirado` · `sin_marcas`; los tres siguen siendo rc 2 |

⛔ Y `--trazabilidad` ahora rehúsa **en cuanto uno** de los pedidos no se puede auditar, aunque el
resto sí: antes sólo rehusaba si **ninguno** quedaba en pie, así que `--solo INV-01,INV-BOGUS`
auditaba uno y publicaba su veredicto como si fueran dos. Se pidieron N y se midieron M < N: es el
falso limpio que D-43 nombra.

**2 · `tools/` está fuera de las redes 1 y 4 — y el mensaje que lo decía MENTÍA.**
`test_file_for` exige `parent.name == "scripts"`, así que apuntar cualquiera de los dos modos a
`tools/mutar.py` contestaba *«⛔ no hay tests/test_mutar.py»* **con ese archivo en el árbol**: la
herramienta que corre la red de mutación daba un motivo **falso** para no recibirla, y el
implementador de #335 tuvo que escribir un driver aparte sin que nada se lo dijera.

⚠ **El alcance NO se tocó**: `CLAUDE.md` acotaba la red a *«toda función nueva de `scripts/`»* y eso
era una decisión declarada. Lo que cambió acá es el mensaje — vive en `tools/mutar.py::scope_refusal`,
que separa *«fuera de alcance»* (nada que escribir; hace falta un driver propio) de *«no hay
`tests/test_<mod>.py`»* (hueco real: escribí el archivo). Las dos acciones son opuestas.

⛔ **Superado el 2026-08-31 por #345**, que es la otra mitad: el usuario decidió meter `tools/` en
las redes 1 y 4, así que hoy `python tools/mutar.py --dirigida tools/mutar.py` **corre** y el driver
aparte ya no hace falta. Ver la entrada de #345 al final de este documento.

**3 y 4 · Ningún flag de `tools/` se validaba, y el barrido atribuía mal.** El universo de
`tests/test_docs_ejecutables.py` se armaba con `scripts/*.py` sola, así que los siete flags de
`tools/mutar.py` estaban en `FLAGS_AJENOS` — que los **exime**, no los chequea: un typo en
`--guardas` dentro de cualquier doc no lo cazaba nadie, y la lista se leía como si estuvieran
validados. Y el patrón ``scripts/(\w+)\.py([^\n`]*)`` se llevaba **todo lo que siguiera a cualquier
ruta hasta el fin de la línea**:

```
python tools/mutar.py --guardas scripts/triage.py --solo main
→ antes: «scripts/triage.py `--solo`»   (un flag de mutar, atribuido a triage)
```

Un mapa que atribuye mal es peor que uno vacío (regla de método nº 4), y acá el mapa decide si un
flag que la doc promete existe. Se había **esquivado reordenando** los comandos de este mismo
documento (el flag antes de la ruta); con `comandos_de_la_linea` el orden natural volvió a las dos
recetas de #335, que es la prueba en vivo.

| Qué se midió | Número | Salvedad |
|---|---|---|
| Pares `(script, flag)` que el barrido chequeaba, antes → después | **74 → 80** | ninguno perdido; los 6 nuevos son los de `tools/mutar.py` |
| Flags de `tools/` exentos en `FLAGS_AJENOS`, antes → después | **7 → 0** | el test exige además que **ningún** flag declarado por un argparse esté en la lista de exentos |
| Rutas `.py` que el barrido trata como comando en `python tools/mutar.py --guardas scripts/triage.py --solo main` | **2 → 1** | `scripts/triage.py` es un **argumento**; una ruta encabeza comando propio sólo si abre el tramo o viene detrás de `python` |

**Cómo re-medirlo.**

```bash
python tools/mutar.py --dirigida scripts/triage.py --solo main   # existe, EXENTA — no «no existe»
python tools/mutar.py --dirigida tools/mutar.py                  # fuera de alcance — no «no hay tests»
python tools/mutar.py --trazabilidad --solo INV-102,INV-126,INV-999-NOPE   # tres líneas, tres estados
python -m pytest tests/test_docs_ejecutables.py tests/test_mutar.py -q
```

**Lo que el driver midió, y lo que queda abierto.** Como `tools/` está fuera del alcance, la
mutación de `tools/mutar.py` se corrió con un driver que mueve `ALCANCE` para la corrida
(`tests/test_mutar.py` es su archivo de tests: el mapeo ya resolvía).

| Qué se midió | Número | Salvedad |
|---|---|---|
| Funciones nuevas de #339 que mueren en `tests/test_mutar.py` | **5 de 5** | `report_states`, `scope_refusal`, `unmarked_reasons`, `_contract_rows`, `_report_unmutable` — `_contract_rows` sobrevivió a la primera corrida y por eso tiene test propio |
| Guardas de los módulos tocados que mueren | **22 de 27** | los 5 sobrevivientes son **anteriores** a #339 |
| Sobrevivientes, uno por uno | `_directed::if sobreviven` · `_trazabilidad::if not pares` · `if fn is None` · `if vivo` · `if falsas` | ramas de **reporte** de `tools/`, que ninguna red mira porque el alcance las excluye. **No** se tocaron acá: bajar deuda vieja dentro del issue que arregla el mensaje mezclaría dos cosas |


## 2026-08-31 · #343 · la otra cola de #331: los dos scripts que seguían reventando

**Qué era.** #331 (v1.140.0) le dio a `make_notes.py` una negativa limpia cuando el slug es un tema
y falta `--theme`, y #334 cerró los dos sitios que **imprimían** el comando mal armado. Quedaba una
población distinta y sin tocar: los scripts que **resuelven el sujeto ellos mismos** y por lo tanto
morían con el `KeyError` crudo. Medido en vivo sobre la bóveda real, corriendo
`extraction_prompt.py ica <bib>` para leer los papers que cierran los huecos declarados de `ica`:

```
$ python scripts/extraction_prompt.py ica 1995BellSejnowski
KeyError: "slug desconocido: 'ica'. Definilo en vault/config/stars.yaml"

$ python scripts/fetch_ground_truth.py ica
KeyError: "slug desconocido: 'ica'. Definilo en vault/config/stars.yaml"
```

| Qué se midió | Número | Salvedad |
|---|---|---|
| Scripts con `subject_refusal` antes de #343 | **1** | `grep -l subject_refusal scripts/*.py` → sólo `make_notes.py` |
| Scripts que reventaban con el `KeyError` crudo | **2** | `extraction_prompt.py`, `fetch_ground_truth.py` |
| Scripts con la misma forma que **no** estaban rotos | **3** | `harvest_views.py` rechaza por la guarda add-only (correcto); `query_ads.py` y `triage.py` dan error de `argparse`, no traceback |

**Por qué el `KeyError` es peor que feo.** No dice sólo «no sé qué es esto»: **manda definir en
`stars.yaml` un slug que está bien definido en `themes.yaml`**. El operador que sigue la instrucción
agrega una estrella falsa a la config — el error de operador se convierte en corrupción de la
curación.

**Qué cambió.** `subject_refusal` subió a `lib_config` y la usan los **tres**. Copiarla habría sido
el molde de #215/#324/#335, la misma regla escrita dos veces y ya divergida tres veces en este repo.
Lo que cada llamador aporta es sólo lo que él sabe: la **consecuencia** y el **remedio**.

⛔ **Y el remedio NO es el mismo, que es el punto que un copy-paste habría perdido:** en
`extraction_prompt` lo que falta es el flag, y el comando va **completo con el bibcode**
(`extraction_prompt.py <slug> <bib> --theme`) porque un remedio que no se copia y pega no es un
remedio. En `fetch_ground_truth` **no hay flag que ofrecer**: NEA y SIMBAD son autoridades sobre
**objetos, no sobre conceptos**, así que un tema no tiene ground-truth y el script ni siquiera tiene
`--theme` — un «te faltó `--theme`» mandaría a correr algo que no existe.

⚠ **Lo que sigue afuera, y es el hallazgo de #334 otra vez:** las dos negativas viven en `main`,
que está en `EXENTAS` de `mutar.py`, así que **ninguna red de mutación mira el call site**. Lo que
sí se mutó es la regla (`lib_config.subject_refusal`: dirigida ✅, las 2 guardas ✅); el call site lo
cubren los tests de integración, vistos morir con el `KeyError` exacto de arriba.

## 2026-08-31 · Los seis huecos falsos, cazados de casualidad (#342)

**Qué era.** Una afirmación **negativa** de una ficha o de un concepto —*«nadie da un criterio para
elegir $n$»*, *«ICASSO no aparece en ninguna fuente»*— **no tiene fuente que la respalde por
construcción**, así que ninguna capa de la bóveda la mira: `verify-citations` chequea claim ↔ **su
propia** fuente y `find-contradictions` claim ↔ claim **entre** fuentes, y las dos parten de un
`[[bibcode]]`.

| Qué se midió | Número | Salvedad |
|---|---|---|
| Huecos falsos en `ica` | **2** | afirmaban que la bóveda no puede responder algo que sí responde |
| Huecos falsos en `ica-ruido` | **4** | ídem |
| De esos seis, cuántos los cazó un detector | **0** | los seis salieron de verificadores que **contradijeron la afirmación desde su propia fuente** sin habérselo propuesto |
| Cuántos habrían sido correctos con el alcance declarado | **2 de 2** en `ica` | *«no lo dice ninguno de los N papers de este tema, a esta fecha»* en vez de *«no existe en la literatura»* |

**Por qué pasó, y no fue descuido.** Los seis salieron de **agregar los campos `hueco` de las
extracciones**. Un `hueco` de extracción es **por lente** —lo que *esa* fuente no da— y agregarlos lo
convierte en una afirmación universal. Es una operación que parece correcta y no lo es.

**Qué cambió (1.148.0).** El `## Huecos` con bullets declara su **alcance**, el mismo blockquote que
las hipótesis ya llevaban (D-34), **dentro de la sección**; el lint lo cruza contra el disco con la
misma escalera (`lint.scope_state`, una sola implementación para los dos consumidores: sin declarar ·
sin slugs · sin `· N papers` · slug fantasma · quedó corto). El blockquote de **nivel de nota** de
una hipótesis no cuenta: declara el alcance del *veredicto*, que es otra afirmación.

⚠ **Lo que NO entra acá, declarado:** verificar la negativa de verdad —preguntarle a cada fuente del
alcance *«¿tu paper dice algo de X?»*— es un **fan-out por hueco** y queda como issue aparte. Esto es
la red barata: **declarar el alcance y chequearlo contra el disco**, que es lo que convierte una
universal falsa en una acotada verdadera.

## 2026-08-31 · La canaleta era de la línea y no de la página (#332)

**Qué era.** `lib_config.deinterleave_columns` partía **cada línea** por cada run de ≥ 8 espacios y
mandaba el segmento `i` al stream `i`. En una página real ese índice **deriva renglón a renglón**
—una ecuación con su número, una canaleta que se angosta a 7 espacios, un enunciado a todo el
ancho—, así que una oración continua de **una** columna física caía en dos lecturas distintas y
`source_texts` no podía encontrar una cita que **sí está verbatim en el `.txt`**. El paso 1 de
`quote_verdict` (`en_su_txt`, #324) es justamente el que evita el falso «mal atribuido», y desde
#323 ese gate frena operaciones.

**Corpus.** Bóveda `Almagesto-Tesis`, 2026-08-31: **155 `.txt`** bajo `vault/raw/fulltext/` y
**251 pares únicos (cita, bibcode con `.txt` en disco)** — los que arma `contrast.validar`
(`split_blocks` + `quotes_in` + `quote_owner`), quedándose con el primer candidato que tiene `.txt` y
resolviendo el bibcode duplicado entre slugs como lo hace `fulltext_readings` (`sorted(...)[0]`).
⚠ **Es un A/B congelado**: la misma población, medida contra las dos versiones del módulo en la
misma corrida (`git show a243977:scripts/lib_config.py` contra `HEAD`), porque la bóveda es una
instancia viva y se estaba editando mientras se medía — dos corridas separadas no habrían sido
comparables.

| | antes (a243977) | después |
|---|---:|---:|
| `.txt` que devuelven **más de 2** lecturas | **148 / 155** (95 %), máximo **19** | **0 / 155** |
| lecturas por `.txt` | 2 a 19 | **2 en los 155** |
| citas encontradas por `source_texts` | 176 / 251 (70,1 %) | **196 / 251 (78,1 %)** |
| de ésas, las que perdía **el corte de columnas** (están en el texto aplanado y en ninguna lectura) | 6 | **0** |

Delta por par: **+25 recuperadas, −5**.

⚠ **Discrepancia declarada (regla de método #5).** El issue #332 reportó *«5 de 318»* y *«168
encontradas»*: contó **toda** cita ≥ 40 caracteres cuya fuente tenga `.txt`, sin resolver dueño y
sin deduplicar el par. Los dos números miden poblaciones distintas y **no se mezclan**; las cuatro
filas de arriba salen todas de la misma, antes y después.

**Cómo se arregló, y por qué NO aplanando.** El texto aplanado contiene el empalme
columna1→columna2, o sea frases que no escribió nadie (#46/#275): sirve como **cota superior de lo
recuperable**, nunca como fuente. La canaleta pasa a ser de la **página**: se parte por `\f`, cada
página elige **un** borde (`column_boundary` — el fin de canaleta más votado por sus líneas, que es
donde arranca la columna derecha) y cada línea se corta ahí, en su propia canaleta más cercana, o
queda entera a la izquierda si cruza el ancho.

**El umbral que sí decide** (`BOUNDARY_SPACES_MIN`): cuántos espacios alcanzan para leer el borde de
la página en una línea sin canaleta propia. Sobre los mismos 251 pares — **1**: 189 · **2**: 198 ·
**3**: 198 · **4**: 196 · **8**: 187. Con 1 se acepta la separación normal entre palabras y se corta
por el medio una línea a todo el ancho; de 2 en adelante no. La guarda decide; su valor exacto por
encima de 2, no.

**Las 5 que el corte nuevo pierde y el viejo encontraba** son la clase opuesta, y son legítimas
(#205): un fragmento corto e indentado —un exponente, un `−2`, el `1 1` de dos superíndices— que
pertenece **de verdad** a esa columna y que el cortador viejo mandaba por accidente al stream de al
lado, dejando la prosa limpia. Hoy quedan donde están, la cita cae al paso 2 de `quote_verdict` (la
extracción) y el `.txt` queda declarado como lo que es: un índice degradado.

## 2026-08-31 · Los otros tres agujeros de la misma lectura del `.txt` (#336)

Hermanos de #332 (que es el cuarto), con la misma consecuencia: una cita **verbatim en la fuente**
sale como «no está», y lo que eso cuesta es el paso 1 de `quote_verdict` (`en_su_txt`, #324) — el que
evita el falso `alterada`, y desde #323 un gate que frena operaciones. Mismo corpus congelado que
#332: `Almagesto-Tesis`, 2026-08-31, **155 `.txt`**, **251 pares únicos** (cita, bibcode con `.txt`).

### 1 · el borrado de `$…$` se aplicaba al TEXTO FUENTE

`normalize_source_text` delegaba entero en `normalize_quote`, cuya `_QUOTE_MARKUP_RE` borra
`\$[^$]*\$`. Eso es correcto **sobre la cita** —la nota re-marcó una fórmula que el `.txt` no puede
tener igual (#287/#326)— y no sobre el `.txt`, donde el `$` es un carácter del documento: dos `$`
literales borran **todo lo que hay en el medio**.

| `.txt` | qué se comía | de una columna de |
|---|---:|---:|
| `1998Cichocki` (copyright de Elsevier `0925-2312/98/$ — see front matter`, más otro `$`) | 16 434 caracteres (**37,9 %**) | 43 401 |
| `2011ApJ...730...95B` | 8 457 (**26,1 %**) | 32 441 |
| `2010ApJ...718..543M` | 6 961 (**22,5 %**) | 30 935 |

Población: **10 de 155** `.txt` (6 %) perdían texto. ⚠ El issue reportó **9** y un peor caso de
36 %: la diferencia es que acá se mide sobre las columnas que produce el cortador de #332 y sobre la
bóveda del día, con `1998Cichocki` presente bajo dos slugs. Se declara en vez de elegir uno (regla de
método #5).

**El arreglo es una regex, no una excepción:** `_SOURCE_MARKUP_RE` es `_QUOTE_MARKUP_RE` **menos** el
span de matemática, y lo compartido (sustituciones tipográficas, guión, espacios, `casefold`) vive en
**una** función, `_normalize_text` — una diferencia entre los dos lados que nadie decidió es un match
que nadie decidió (regla de método #2).

### 2 · el join del guión de corte no absorbía la sangría

`t.replace("-\n", "")`. En un `.txt` de `pdftotext -layout` la continuación viene **indentada**
—es la columna física—, así que `homoscedas-\n     tic` quedaba `homoscedas tic` y la palabra
partida no volvía a unirse nunca. Medido: **141 de 155** archivos y **4232** ocurrencias de
`[A-Za-z]-\n[ \t]+[a-z]` sobre el `.txt` crudo (**140 / 3126** sobre las columnas ya cortadas, que es
donde el join corre de verdad). ⚠ El issue reportó 102 / 1860 sobre la bóveda de ese momento; misma
salvedad que arriba. Hoy el join es `_HYPHEN_BREAK_RE = -\n[ \t]*`.

### 3 · los fragmentos de una cita elidida en lecturas distintas — **desapareció solo con #332**

`quote_found` exige todos los fragmentos de una cita elidida en la **misma** lectura. El caso del
issue (`2010ComonJutten`, la coherencia espacial, líneas 813-816 del `.txt`) fallaba porque el
cortador viejo mandaba dos líneas **consecutivas de la misma columna** a lecturas distintas. Con la
canaleta de página los dos fragmentos vuelven a la lectura 0 y `quote_found` devuelve `True`:

```
variante «$G$» borrada:      ['if the noise spatial coherence is known' → []      , 'one can build an unbiased estimate…' → [0]]
variante «$G$» desenvuelta:  ['if the noise spatial coherence g is known' → [0]   , 'one can build an unbiased estimate…' → [0]]
variante «$G$» como elisión: ['if the noise spatial coherence' → [0]              , 'one can build an unbiased estimate…' → [0]]
```

**Se confirmó antes de tocar nada y `quote_found` NO se tocó.** Aflojar ahí habría sido exactamente
lo contrario de lo que hace falta: exigir los fragmentos en la misma lectura es lo que impide que una
cita se arme cruzando la canaleta (#46/#275).

### El efecto de 1 y 2, sobre la misma población

Citas encontradas: **196 / 251 con #332 → 198 / 251 con #332 + #336** (+2 sobre las +25 de #332).
El número es chico porque los dos defectos golpean donde ya golpeaba el corte de columnas; lo que
cambia es que dejan de golpear **en silencio**, y el 37,9 % de una columna que el borrado de `$…$`
se comía era una porción del índice de búsqueda que simplemente no existía para nadie.

### Cómo se movió la población de `quote_verdict` (#332 + #336, mismo corpus)

Ninguno de los dos issues toca `quote_verdict`, pero los dos cambian **su insumo**, así que la
población de cada paso se mide antes y después. Sobre los **3082 casos únicos** `(cita, fuentes,
nota)` de la bóveda —el universo completo, no sólo los que tienen `.txt`—:

| veredicto | antes | después | qué significa |
|---|---:|---:|---|
| `no_evaluable` | 2825 | 2825 | sin `.txt` ni extracción — el fix no puede tocarlo (D-43) |
| **`en_su_txt`** (paso 1) | 195 | **218** | la cadena está en el `.txt` de SU fuente: nada que decir |
| `txt_degradado` (paso 2) | 42 | 24 | ya no hace falta la extracción para rescatarlas |
| `no_verbatim` (paso 5, backlog) | 19 | 12 | — |
| `txt_parte` (paso 3, #288) | 1 | 2 | — |
| **`alterada`** (paso 4, BLOQUEA) | 0 | **1** | ⚠ ver abajo |

⛔ **El `alterada` que aparece es un VERDADERO positivo, y su historia es el argumento entero de
#332.** La nota cita *«Reaching such a high $S/N_{cont}$ is not achievable for any star and
telescope that put strong constraints on the observational **method**»* y el paper
([[2022A&A...659A..68C]], p. 13, columna derecha) dice *«…constraints on the observational
**strategies needed to correct for stellar activity with the present** method»*. La cita se comió 63
caracteres del medio y pegó las dos puntas.

Lo decisivo es **por qué nadie lo veía**: con el cortador viejo la línea del medio caía en otra
«columna», así que el `.txt` **parecía** decir «observational method» seguido — la adyacencia
fabricada que #46/#275 existe para impedir— y el paso 1 devolvía `en_su_txt`. Peor: el `log.md` de
esa bóveda registra una corrección previa que **recortó la nota hacia esa cadena inventada**
(*«la fuente cierra en “constraints on the observational method” y la nota continuaba 90 caracteres
inventados»*), y la cola falsa se propagó a la columna *Evidencia* del bloque de verificación. O sea:
el cortador roto no sólo escondió un defecto, **dictó una corrección equivocada y la dejó en verde**.

El caso simétrico —una cita que el corte viejo encontraba y el nuevo no (`en_su_txt` →
`no_verbatim`, 1 caso)— es el `.txt` que intercala un superíndice en medio de la prosa
(`…which are simply inverse` / `−2` / `variances wij = σij`): el corte viejo mandaba ese fragmento a
otro stream **por accidente** y dejaba la prosa limpia. Es la misma mecánica que fabricó el falso
`en_su_txt` de arriba, así que se va con ella; cae en `no_verbatim`, que es **backlog** y nunca
bloquea.

## 2026-08-31 · El mismo error de forma, tercera copia: el slug de un tema es la CLAVE (#346)

**Qué era.** `lint.extraccion_no_declarada` (INV-83) barre estrellas **y** temas y le pedía
`meta.get("slug")` al mapa de los dos. En `stars.yaml` el slug es un **campo** de la entrada; en
`themes.yaml` es la **clave del YAML** (lo dice el docstring de `cfg.theme_by_slug`). Para todo
tema salía `None` y el loop hacía `continue`: el detector del recorte de lectura silencioso —lo que
D-13/D-15 existen para cazar— estaba **apagado para todos los temas**.

| Qué se midió | Antes | Después |
|---|---|---|
| «Recorte de lectura sin declarar» sobre la bóveda de `Almagesto-Prueba` | **(0)** | **(1)** — `ica`, 26 core sin extraer y sin criterio declarado |
| Hallazgos bloqueantes en la misma corrida | 154 | 154 (sin cambio: la categoría es backlog) |
| Sujetos que el detector miraba | 2 de 3 (las estrellas) | 3 de 3 |

**Por qué importa el `(0)`.** El reporte imprime la categoría siempre, con su conteo, y un `(0)` que
nadie midió se lee como veredicto — es el falso limpio que D-43 persigue, acá producido no por un
chequeo que no pudo correr sino por uno que se saltea la mitad de su población **en silencio**.

**Por qué es la misma clase que #338.** #338 encontró exactamente este `None` en el detector de
roll-up y lo resolvió **en línea**, construyendo su lista de sujetos a mano. La regla quedó escrita
dos veces en el mismo archivo y la segunda copia estaba mal: es el molde de #215/#324/#331/#335/#339.
El arreglo no es corregir la segunda copia sino que haya **una**: `cfg.all_subjects()` devuelve
`(kind, slug, name, meta)` y la usan los dos detectores.

⚠ **Lo que sigue afuera, declarado:** los dos call sites viven en `lint.main`, que está en `EXENTAS`
de `mutar.py`, así que ninguna red de mutación los mira — es el hallazgo de #334/#343 otra vez. Lo
que sí se muta es la regla extraída (`cfg.all_subjects`: dirigida ✅, las 3 guardas ✅); el call site
lo cubre `test_recorte_sin_declarar_de_un_TEMA_tambien_se_reporta`, visto morir con `assert 0 == 1`
al devolverle el `meta.get("slug")` a la rama del tema.

## 2026-08-31 · El comentario que prometía delegar, y no delegaba (#347)

**Qué era.** `make_notes._papers_del_sujeto` decía, en su propio comentario, que la pertenencia de un
paper a un tema es *«la misma unión que `concept_rollup_rows` (D-24), y por eso se delega ahí: dos
predicados de pertenencia distintos para el mismo tema es cómo la tabla y el roll-up terminan
discrepando»* — y **no delegaba**: comparaba `methods` y `thesis_links` por **string exacto**
mientras `concept_rollup_rows` usaba `cfg.method_matches` (clave normalizada, #243). Es el defecto
que #243 arregló, vivo en el camino hermano, bajo un comentario que afirmaba lo contrario.

| Qué se midió | Resultado |
|---|---|
| Repro (tema `pca`, paper con `methods: [PCA]`) | `papers_universe('pca','theme')` → `set()` · `concept_rollup_rows('pca')` → el paper |
| Reporte del lint sobre `Almagesto-Prueba` (201 notas de paper) | **sin cambio** — los 90 papers de `ica` escriben el concepto igual, así que ahí las dos formas coincidían |
| Grafías que colapsan bajo `method_key` en ese corpus | 2 de 702 claves (`log-rhk`/`log_rhk`, `s-index`/`s_index`) — ninguna es un tema declarado |
| Ídem en `Almagesto-RV` (908 notas de paper) | 3 de 139 claves; esa instancia no declara temas |

⚠ **Declarado, porque el número es incómodo:** en las dos bóvedas que se pudieron medir el arreglo
**no mueve el reporte**. Lo que cierra es un defecto **latente**, y la población donde muerde ya está
medida: es la de #243 —un concepto `pca` alcanzando **21 papers de 24** y no diciendo nada de los 3
que escribieron `PCA`—. Lo que cambió desde entonces es que ese universo dejó de ser sólo cosmético:
desde #338 el detector de tabla desactualizada compara el `## Papers` estilo ficha de un concepto
**contra él**, así que un falso negativo del predicado se volvía un falso limpio del lint.

**Qué cambió (1.157.0).** El predicado es **uno**: `mn.theme_membership(concept, fm)` devuelve
`(por methods, por thesis_links)` y lo usan los dos. Devuelve el **par** y no un `bool` porque el
roll-up publica por cuál llave entró el paper (`Entró por`, D-24) y colapsarlo le sacaría esa columna
a la única función que puede calcularla. El comentario de `_papers_del_sujeto` ahora describe lo que
el código hace — regla de método 4: un comentario que afirma una cobertura que el código no da es
peor que no tenerlo.

## 2026-08-31 · Tres veces más #243 por string crudo, y una de ellas BLOQUEA (#348)

**Qué era.** Derivado de #347: la pregunta *«¿este nombre denota un concepto/tema declarado?»* estaba
re-implementada **por string crudo** tres veces en `lint.py`, mientras `make_notes.theme_membership`
—desde #347— la contesta por clave normalizada (#243). Las tres, con su repro en bóveda de juguete
(tema `pca`, `concept: pca`, nota `concepts/methods/pca.md`):

| # | Detector | Con `PCA` | Con `pca` | Severidad |
|---|---|---|---|---|
| G1 | `thesis_links` sin página destino | **1 hallazgo** (falso) | 0 | ⛔ **bloqueante** |
| G2 | `sin_extraer_por_sujeto` → «Recorte de lectura sin declarar» | 0 | 1 | backlog |
| G3 | `reclamo_sin_vista` («reclamado y nunca leído») | 0 | 1 | backlog |

G1 es el peor porque **bloquea**: obligaba a "arreglar" trabajo correcto, y desde #347 el framework se
contradecía —el roll-up acumulaba el paper en el concepto y el lint decía que el destino no existe—.
G2 traía además la regla de método 4: su comentario afirmaba *«mismo predicado que
`make_notes._papers_del_sujeto`»* y era falso por **dos** ejes (indexaba crudo, y no miraba
`methods`).

**Población latente en las bóvedas reales** (4 medidas, `method_key` contra el valor crudo):

| Bóveda | Papers | Temas | G1 | G2 | G3 |
|---|---|---|---|---|---|
| `Almagesto-Prueba` | 201 | 3 | 0 | 0 | 0 |
| `Almagesto-RV` | 908 | 0 | 0 | 0 | 0 |
| `Almagesto-Tesis` | 157 | 2 | 0 | 0 | **1** (`ICA` ↔ tema `ica`) |
| `Almagesto-Actividad` | 26 | 0 | 0 | 0 | 0 |

**Diff del reporte del lint, medido antes de dar el arreglo por bueno:**

| Corrida | Bloqueantes antes → después | Qué se movió |
|---|---|---|
| `Almagesto-Prueba` (tal cual) | 154 → 154 | reporte **byte-idéntico** |
| `Almagesto-Tesis` (tal cual) | 1 → 1 | *«Reclamado por un sujeto y nunca leído desde ahí»* **1 → 6**: cinco papers cuyo `methods: [ICA]` reclama el tema declarado `ica` y sólo tienen vista de `ica-ruido` (verificado paper por paper: `2000Ikeda`, `2009Bonhomme`, `2017PhRvE..96d2114K`, `2018IEEEA...625336F`, `2019Pfister`) |
| `Almagesto-Prueba` con G1 forzado (`2025sklearn`: `thesis_links: ica` → `ICA`) | **155 → 154** | desaparece el único hallazgo `ICA → sin página destino`; `methods` sin destino queda en 698, igual |

⚠ **Ningún hallazgo desaparece que no fuera falso positivo**: el único que se va es el G1 forzado.
Lo que aparece —los 5 de `Almagesto-Tesis`— es la subdeclaración que #348 describe, no ruido nuevo.
⛔ **No evaluable, declarado:** `Almagesto-RV` no llega a producir reporte —su `extra_core` está en el
schema pre-D-58 y el loader **rehúsa operar**—, así que ahí sólo se midió la población latente.

**Qué cambió (1.160.0).** Una sola implementación: `cfg.name_index(nombres)` construye el universo
declarado indexado por `method_key` y `cfg.declared_name(nombre, index)` lo consulta —`method_target`
pasa a delegar en ella—. En `lint.py`, `_is_dangling` es **un** predicado para las dos categorías
colgantes (difieren en severidad, nunca en qué cuenta como destino), el índice de sujetos sin extraer
se llena y se consulta por clave, y el reclamo por `methods` entra al set con el **nombre declarado
del tema**, no con la grafía del extractor. Los comentarios quedaron descriptivos: el de G2 dice
ahora que `methods` no se recorre **porque la rama exige `not fm.get("methods")`** —recorrerlo sería
un condicional que no decide nada (red 8)—, en vez de prometer una equivalencia que no existía.


## 2026-08-31 · El `fq` que un tema de método hereda en silencio (#351)

Un tema que declara **`facet:` propia** es, por D-26, un tema de **método**. Si además no declara
`search_fq`, hereda el del objetivo —`database:astronomy` en una bóveda astro—, que acota el
universo **server-side, antes de traer nada**, y ninguna `facet:` puede recuperar lo que ese `fq`
dejó afuera: la faceta clasifica lo ya traído.

**Medido sobre `ica`** (misma query, misma faceta, `fundacional_min_citas: 2000` declarado):

| `search_fq` | universo | core | **por la puerta FUNDACIONAL** |
|---|---:|---:|---|
| `database:astronomy` (el heredado) | 947 | 30 | **0** |
| `database:(astronomy OR physics OR general)` | 2000 | 27 | 1 |
| **`null`** | 2000 | **31** | **2 — incluido `1994SigPr..36..287C`** (Comon 1994, 2297 citas) |

⛔ Con el `fq` heredado la puerta 2 **no abre nunca**: el tema tiene el umbral puesto y la puerta
cerrada por otro lado, sin decirlo. ⚠ Y ensancharlo no alcanza: la literatura de ICA vive en *Signal
Processing*, *Neural Networks* e *IEEE TNN*, que no están en `astronomy OR physics OR general`.

**El costo, ya pagado:** `ica` se ingestó, se sintetizó y se **cerró** sin su canon; los 8
fundacionales entraron a mano después y obligaron a **re-sintetizar el tema entero** al día
siguiente. Nada en el reporte decía que faltaran — el tema traía 900 papers de aplicación astro y la
síntesis se leía completa.

**Qué cambió (1.166.0).** Un **aviso**, no un default nuevo: los tres estados de `search_fq` quedan
intactos (sin declarar → hereda · con valor → ése · `null` → no acota). `query_ads.py <slug>
--theme --probe` lo emite **antes del corte** —la pantalla donde la decisión se toma antes de pagar
descargas (#208)— y el lint lo reporta como **backlog** con su población (`temas`). La cascada de
tres estados se movió a `lib_config` (`ASTRO_FQ`, `fq_value`, `objective_search_fq`) porque el lint
la necesita y no puede importar `query_ads` (arrastraría `requests`): dos implementaciones de esta
regla es cómo un `null` termina significando cosas distintas según quién lo lea.
`cfg.theme_inherited_fq` calla en los **tres** casos que no son hallazgo: sin `facet:` propia,
con `search_fq` declarado —**`null` incluido**, que es una decisión— y con un objetivo que ya no
acota nada (nombrar una exclusión inexistente sería la atribución falsa de la regla de método nº 4).

## 2026-08-31 · La herramienta que ejecuta las redes era la única que no las recibía (#345)

**Qué era.** `CLAUDE.md` acotaba las redes 1 (mutación) y 4 (cobertura) a *«toda función nueva de
`scripts/`»*. Eso dejaba a `tools/mutar.py` —782 líneas, 23 funciones, 70 guardas— **auditando a
todo `scripts/` sin que nadie lo auditara a él**, y a `tests/poblada/test_cobertura.py` corriendo
`coverage run --source=scripts`, o sea sin contar una sola función de `tools/` como ejecutada. #339
había arreglado el **mensaje** (decir «fuera de alcance» en vez de negar un `tests/test_mutar.py`
que existe) y dejó la decisión a la vista; la decisión la tomó el usuario.

| Qué se midió | Número | Salvedad |
|---|---|---|
| Guardas de `tools/mutar.py` sin un test que las distinga (antes) | **5 de 70** | `_directed::if sobreviven`, `_trazabilidad::if not pares` / `if fn is None` / `if vivo` / `if falsas`. Medidas con un driver aparte que movía `ALCANCE`, porque el modo rehusaba. |
| Ídem, después (`--guardas tools/mutar.py`, con la herramienta misma) | **0 de 70** | las cinco se cerraron con test, no con techo |
| Guardas que el splice parsea (`test_toda_guarda_del_ALCANCE_…`) | **2204** = 2134 (`scripts/`) + 70 (`tools/`) | el 1503 anterior se midió sobre `scripts/` solo y un corpus más chico: dos poblaciones, se declara el cambio (regla de método 5) |
| Guardas de `tools/mutar.py` sin test, **medidas sobre las 70** | **9**, no 5 | el conteo del issue era PARCIAL (lo hizo un driver que movía `ALCANCE`): además de las 5, `funciones::if@L102` + 3 cláusulas, `mutar_archivo::if vivo and subset` + 2 cláusulas + `if verbose`, y `_traceability_pairs::or[0]` |
| Población del barrido `--todo`, antes → después | **631 → 655** | +24 (`tools/mutar.py`); `tools/refresh_issues.py` sale por exención declarada |
| Costo del barrido `--todo`, antes → después | **1737 s (28,9 min) → 1951 s (32,5 min)** | +214 s = **+12,3 %**; misma máquina, mismo día, árbol quieto |
| Sobrevivientes del barrido, antes → después | **6 → los mismos 6** | `tools/` no aporta ninguno |
| Funciones sin ejecutar (red 4), al ampliar el alcance | **3 → 4 → 3** | apareció `mutar.py::_copia_del_repo` y se **cerró con test**, no con techo |

⛔ **La exención se DECLARA, no queda por omisión del alcance.** `tools/refresh_issues.py` (59
líneas) es un cliente HTTP contra la API de GitHub, y la **regla de método 1** dice que un cliente
de red se prueba **contra el servicio real**: un test con la red falseada validaría que el cliente
funciona, no que el contrato se cumpla, así que mutarlo sólo mediría si el doble está bien escrito.
Vive en `tools/mutar.py::EXENTOS_MODULO`, con su motivo textual, y de ahí la leen **las dos** redes
—la 4 importa `mutar.ALCANCE` y `mutar.module_exemption` en vez de repetirlos, que es el molde de
#215/#324/#335: la misma regla en dos copias ya divergió tres veces acá—.

El estado nuevo se ve desde afuera: `scope_refusal` tiene hoy **tres** estados con tres acciones
opuestas —*fuera de alcance* (`docs/`, la raíz: nada que escribir) · *exento* (leé el motivo y
decidí si sigue valiendo) · *sin `tests/test_<mod>.py`* (hueco real: escribí el archivo)—, el
barrido **nombra** al exento con su motivo antes de sacarlo de la población, y una selección **toda**
exenta sale *no evaluado* (rc 2): un 0 sobre cero mutantes comparado contra el techo del ratchet
sería el falso limpio adentro del detector de falsos limpios.

⚠ **Se muerde la cola y no pasa nada, por construcción.** `mutar` copia el repo a un tmpdir y muta
**el gemelo**; el proceso que decide corre desde el árbol real, sin mutar. Lo que la mutación de
`tools/mutar.py` afecta es sólo lo que los tests de la copia importen —`tests/test_mutar.py` hace
`sys.path.insert(0, .../tools)` relativo a su propio archivo, así que importa la copia mutada—. O
sea: el auditor es el árbol real y el auditado es la copia, y la herramienta se audita a sí misma
sin ninguna capa nueva.

⛔ **Lo que el barrido dejó a la vista y NO es de este issue: el gate de mutación ya salía rojo en
`main`.** La corrida «antes» —sobre `scripts/` solo, sin una línea de este cambio— midió **6
sobrevivientes contra un techo de 3**. Tres son las fronteras de red conocidas y declaradas; los
otros tres entraron en tandas anteriores sin que nadie corriera el barrido:
`fetch_web.py::content_type`, `lint.py::_alias_idx_cached`, `make_notes.py::_celda_idx`. El techo
**no se movió** —subirlo para poner verde un rojo es lo que `tools/mutacion-ratchet.yaml` prohíbe
explícitamente—, así que queda declarado y con dueño: se cierra con test, en su propia tanda.

⚠ **Y el costo documentado estaba vencido**: 11,3 min / 464 funciones (2026-08-28) contra 28,9 min /
631 hoy sobre el mismo `scripts/`. Lo que cambió no es la herramienta sino la suite — el tier 0 pasó
a **63 s** y cada sobreviviente de la etapa 1 la paga entera. Se declaran las tres mediciones en vez
de elegir una (regla de método 5).

⛔ **La red 4 se angostaba sin ponerse roja.** Mutando `--source={','.join(mutar.ALCANCE)}` de vuelta
a `--source=scripts`, `tests/poblada/test_cobertura.py` seguía **en verde**: el conteo bajaba y el
ratchet pasaba igual, así que la red podía perder `tools/` entero sin que nada avisara. Es INV-40
adentro de la red que mide cobertura. Se cerró haciendo que `_sin_ejecutar` **declare su población**
—si un directorio de `ALCANCE` no aparece en el reporte de `coverage`, aborta con D-43 en vez de
publicar un cero sobre una población más chica—.
## 2026-08-31 · El detector de párrafo duplicado marcaba lo que estampa el framework (#349)

**Qué era.** *«Forma del artefacto: marcador sin cerrar o párrafo duplicado»* comparaba el arranque
de cada párrafo contra **toda la nota**. En una nota de paper con varias vistas (#239), cada vista
estampa su propia línea estructural —el bloque `**Ejes:**` con los ejes que la lente preguntó y la
fuente calló, y las salvedades chequeadas de #213—, y esas líneas son idénticas **por
construcción**.

**Medido** sobre `Almagesto-Tesis` (2026-08-31, 165 notas), con el `lint.py` de 1.164.0 corrido
contra esa bóveda:

| Nota | Vistas | Hallazgos | Qué línea |
|---|---|---|---|
| `2001HyvarinenKarhunenOja` | 3 | 2 | `- ⚙ verificada: el PDF tiene 503 página(s)…` · `- **rv:** _(sin datos)_` |
| `2010ComonJutten` | 4 | 4 | `- **rv:** _(sin datos)_` ×3 · `- ⚙ verificada: … 824 página(s)` |
| `2026A&A...705A.234O` | 2 | 1 | `- PREPRINT: el PDF lleva la marca de agua 'arXiv:…v1'` |

**7 hallazgos, los 7 falsos positivos** — el 100 % de la categoría en esa bóveda.

**Por qué el corte es por ámbito y no por prefijo exento.** El issue ofrecía las dos vías. La lista
de prefijos que proponía (`- **<eje>:**` y `- ⚙ verificada:`) **ya estaba incompleta sobre el corpus
que la motivó**: el hallazgo de `2026A&A...705A.234O` es `- PREPRINT: …`, una salvedad no
estructurada que no matchea ninguno de los dos. Una lista de excepciones hay que mantenerla y falla
en silencio cuando el estampador gana una forma nueva; el ámbito no.

**Diff medido, `Almagesto-Tesis`:**

| Categoría | Antes (1.164.0) | Después (1.167.0) |
|---|---|---|
| Forma del artefacto: marcador sin cerrar o párrafo duplicado | 7 | **0** |

⚠ **Precisión antes/después:** 0/7 accionables → 0 hallazgos. No se perdió ningún verdadero
positivo porque en esa bóveda no había ninguno; lo que la red prueba es que el caso real sobrevive
—el párrafo repetido **dentro** de la misma vista sigue reportándose, y el ámbito de la prosa normal
no cambió—.

**Qué cambió (1.167.0).** `cfg.duplicate_paragraphs` indexa por `(ámbito, arranque)`: el ámbito es
`""` para el cuerpo de la nota, la línea del `## Vista — <sujeto>` dentro de una vista, y
`vista + ### Lente — <énfasis>` dentro de una segunda lectura (#239). El `###` sólo corta **dentro**
de una vista: fuera, es prosa normal y no parte nada.

## 2026-08-31 · «Segunda mano sin marca» preguntaba por el PAPER, no por el valor (#350)

**Qué era.** El aviso se emitía por par (bloque citante, bibcode) cuando **la vista de ese bibcode
tenía ALGÚN valor de segunda mano**, en cualquier parte. O sea que contestaba *«¿este paper tiene
alguna segunda mano?»* en vez de *«¿el valor que ESTA línea toma es una de ellas?»*. Con la mayoría
de las fuentes fundacionales llenas de atribuciones a terceros —lo normal en un survey o un
handbook—, casi toda línea que citara una de ellas disparaba.

**Medido** sobre `Almagesto-Tesis` (2026-08-31), con el `lint.py` de 1.164.0:

```
hallazgos                : 399        (el issue midió 398; el corpus creció en una nota)
líneas distintas de prosa: 307
bibcodes distintos       :  82
por nota                 : ica-ruido 155 · ica 137 · hd_40307 107
pares (afirmación, bibcode) en esas 3 notas: 463   → 86 % de disparo
```

**Diff medido, misma bóveda, mismos pares:**

| | 1.164.0 | 1.168.0 |
|---|---|---|
| Hallazgos | **399** | **16** |
| Tasa de disparo sobre los 463 pares | 86 % | 3,5 % |
| Población declarada | «sobre 8 notas de entidad» | «sobre **399 pares** (bloque citante, bibcode)» |

**Precisión antes/después, clasificada a mano abriendo la nota y la vista** (es juicio, y se declara
como tal): de los 7 hallazgos que el issue revisó, **1 accionable** (≈14 %); de los 16 de hoy,
**≈10 accionables** (≈63 %) —el `⚠verificar` que faltaba en una edad tomada de Bonfanti, un $T_{eff}$
de PASTEL, la zona habitable calculada con las recetas de Selsis, tres apariciones del período de
Tuomi, el $\log R'_{HK}$ de Noyes—, **4 falsos** (colisión numérica: el mismo número significando
otra cosa en las dos puntas) y **2 dudosos**.

**Qué se descartó y por qué, todo medido sobre el mismo corpus:**

| Recorte | Hallazgos | Motivo |
|---|---|---|
| cruce crudo de cifras | 110 | los años de cita (`2009`, `2013`) cruzan con cualquier bloque |
| sin años | 78 | quedan las referencias `[27]`, los tags `(6.18)` y los localizadores `Sect. 2.3` |
| sin referencias/tags/localizadores | 47 | queda `Gl 725` — una designación de catálogo es un **nombre** |
| sin designaciones | 26 | quedan las cifras de una o dos significativas (`0,1`, `4,5`) |
| + una específica **o** dos de la misma fila | **16** | lo que se publica |

⛔ **Y el decimal castellano vive DENTRO de la matemática:** la bóveda escribe `$P = 4{,}3115$` —las
llaves son lo que evita que LaTeX espacie la coma—, así que leído crudo son dos números y **ningún
valor de una ficha real cruzaba**. Es la cuarta forma de la ceguera al markdown que persigue la
regla de método 4 (#168/#276/#283/#309); deshacerla es lo que hizo aparecer los hallazgos reales
(26 contra 11 sin ella).

**Qué cambió (1.168.0).** `lib_blocks.second_hand_lifted(bloque, filas, atribuido=…)` devuelve las
filas cuyo **valor** el bloque parece levantar, con el literal que cruzó; `quantities` limpia lo que
no es una cantidad afirmada y `cited_names` extrae apellidos **en posición de cita** (anclados a un
año o a un «et al.», para no necesitar una lista de palabras capitalizadas). El lint pasa además los
primeros autores de los `[[bibcode]]` que el bloque cita: la prosa que dice *«reclamadas por
[[2013A&A...549A..48T]]»* nombra a Tuomi sin escribirlo. La categoría declara su población en
**pares**.

## 2026-08-31 · El gate de mutación salía rojo en `main` y nadie leía el resultado (#352)

**Qué era.** La corrida «antes» de #345 —sobre `scripts/` solo, con el cambio stasheado— midió **6
sobrevivientes contra un techo de 3**. Tres son las fronteras de red declaradas; **tres eran nuevos
y de tandas anteriores**: `fetch_web.py::content_type`, `lint.py::_alias_idx_cached`,
`make_notes.py::_celda_idx`. O sea tres funciones que se podían **vaciar enteras** sin que ningún
test muriera. El ratchet hacía su trabajo —el rojo era real desde hacía varias tandas— y el defecto
no era el techo sino que **nadie corría el barrido**: la misma forma que el tier `poblada`, *una red
que nadie corre no es una red*.

**Las tres sobrevivían por motivos DISTINTOS, y conviene no mezclarlos** (regla de método 5):

| Función | Por qué ningún test la mataba | Qué la mata ahora |
|---|---|---|
| `fetch_web.content_type` | los **dos** tests de #242 la **monkeypatchean** (`lambda url: "application/pdf"`), así que la suite nunca la ejecutó: entraba en la población de la red 1 sin estar de veras en la de la red 4 | `test_content_type_normaliza_lo_que_anuncia_el_servidor` + 2: `urlopen` falso que anuncia `Application/PDF; charset=binary `, y se exige `application/pdf`, el método `HEAD` y el `""` de «no se sabe» |
| `lint._alias_idx_cached` | **la mutación no cambia el veredicto del lint**: `method_target(nombre, None)` re-construye el índice solo, así que vaciarla deja el reporte idéntico —sólo más lento—. Lo único que la función promete es lo que ningún assert miraba | `test_el_indice_de_alias_se_construye_una_sola_vez_por_corrida` + `test_el_indice_vacio_igual_se_cachea`: cuentan las construcciones |
| `make_notes._celda_idx` | nada en la suite miraba `index_tables`/`_index_stars`: `restamp_index` se ejerce de refilón en un test de `lint` que no lee las celdas | `test_la_celda_del_indice_marca_el_valor_ausente` + 2 (incluye la fila estampada entera) |

⛔ **La del medio es la que enseña algo, y es la que el issue avisó de antemano: dos garantías, y la
mutación mata una sola.** `_alias_idx_cached` promete (a) devolver el índice bueno y (b)
construirlo **una** vez por corrida. Un test que hubiera chequeado sólo el veredicto —el reflejo
natural— habría quedado **verde con el cuerpo vaciado**: exactamente el test que pasa por
construcción que esta red existe para cazar. El assert que hace al test significar algo es el
**conteo**.

| Qué se midió | Número | Salvedad |
|---|---|---|
| Construcciones de `concept_alias_index` en una corrida de `lint.collect()`, con caché → vaciada | **1 → 9** | corpus sembrado: 3 fichas × 3 `activity_indicators_expected`. El 9 es 3×3: escala con la bóveda, no es constante |
| Ídem con la bóveda **sin un solo concepto** (el centinela `or {"__vacio__": ""}`) | **1 → 9** | sin el centinela, `not _alias_idx` sigue siendo verdadero para siempre: la caché no cachea **nunca** justo en la bóveda joven |
| Guardas de las tres funciones sin test que las distinga (`--guardas`) | **0 de 1** | `_celda_idx` y `content_type` salen **no evaluado** (rc 2): no tienen condicional mutable, y eso NO es un verde (D-43) |
| Sobrevivientes del barrido completo, antes → después | **6 → 3** | = el techo. Los 3 que quedan son las fronteras de red conocidas y declaradas: `citation_index._fetch_ads_default`, `_fetch_oa_default`, `fetch_web.fetch` |
| Población del barrido, `alcance` declarado → real | **464 → 672** | 648 (`scripts/`) + 24 (`tools/`), exento declarado aparte. El campo `alcance` del ratchet estaba vencido desde el 2026-08-28: **AUD-35 por tercera vez, en el archivo que lo documenta** |
| Costo del barrido `--todo`, 2026-08-28 → hoy | **11,3 min / 464 → 29,9 min / 672** | = 1,47 → **2,67 s por mutante**. No comparables: cambió la población **y** el costo unitario (el tier 0 pasó a ~63 s y cada sobreviviente de la etapa 1 la paga entera). ⚠ La máquina no estuvo ociosa (el tier `poblada`, 203 s, compartió CPU): 1794 s es un **techo** del costo limpio |

⚠ **Las tres se vieron morir por su propia línea antes de contarlas** (regla de método 3), con el
mensaje del fallo a la vista: `AssertionError: el índice se re-construyó 9 veces: la caché no está
cacheando` · `assert None == '—'` · `assert None == 'application/pdf'`. `tools/mutar.py --dirigida`
sobre los tres módulos confirma después: *«murieron todas en su propio test»*.

⛔ **Lo que este issue NO cerró y queda declarado: la cadencia.** `CLAUDE.md` dice *«a pedido, y
recomendado al cerrar una tanda»*, y en la práctica *a pedido* fue *nunca* durante varias tandas —
que es cómo se acumularon estos tres. El techo no era el problema: el problema es que ningún momento
del flujo **obliga** a mirar el resultado. Sigue siendo decisión abierta.

⚠ **Y el `alcance` del ratchet no lo chequea nada.** El número vive en un string de prosa
(`alcance: "TODO scripts/ — 464 funciones…"`) mientras `mutar.funciones` sabe contar la población
real; nada cruza los dos, así que la única forma de detectar el desfasaje es que alguien lo lea. Es
el mismo hueco que AUD-35 y el que #345 volvió a encontrar. No se cerró acá (sería otro frente):
queda anotado con su mecanismo.
