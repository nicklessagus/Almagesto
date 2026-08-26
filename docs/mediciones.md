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
| Haiku · canónico | 10 | 100 % | 100 % | 30 % |
| Haiku · sin reglas | 10 | 100 % | 100 % | 10 % |
| Sonnet · canónico | 22 | 100 % | 100 % | 36 % |
| Sonnet · sin reglas | 19 | 100 % | 95 % | 42 % |

**Veredicto: nulo — no se toca `extraction_prompt.py`.** Sacar los cuatro bullets no cambió línea ni
régimen (100 % en las cuatro celdas), **porque el schema ya nombra esos campos y eso alcanza**. La
única diferencia es segunda mano (Haiku 30 % → 10 %), pero son 3 valores contra 1 sobre 10 y **Sonnet
fue en la dirección contraria** (36 % → 42 %): es ruido, no señal.

**La consecuencia es de método:** para una anotación que el schema puede nombrar como campo, más prosa
en el prompt no agrega nada. La palanca es la misma que ya funciona para línea y régimen — **hacer el
campo obligatorio y chequearlo**, o sea un detector, no una instrucción. Coincide con lo ya medido
(RSOS 2025): pedir precisión en el prompt no mejora, y a veces empeora.

*Cobertura declarada:* subconjunto **común a las cuatro celdas = 4 papers**; la celda Sonnet-canónico
de Jofré no cerró antes de terminar la sesión, así que ese paper queda fuera del agregado (con él,
Sonnet-sin-reglas sube a 46 valores, pero compararlo contra 22 sería atribución falsa). Una sola
corrida por celda.

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
- **La población del ratchet de mutación son 338 medidas + 5 contadas sin barrer**: el `--todo` no se
  re-corrió.
- **La corrida de τ Ceti no prueba el framework** sino la paráfrasis que el agente hizo de él. Desde
  INV-100 el paso 3 es reproducible; antes no lo era, así que no hay línea de base con la que
  comparar. Los bloques (b) y (c) del 2026-08-25 **sí** usan el prompt canónico en las dos ramas, así
  que esa deuda queda saldada para esas dos mediciones y sigue abierta para el baseline Opus original.
