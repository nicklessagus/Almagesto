# Reglas del juez — verify-citations

> Lo lee **cada subagente del fan-out**: el prompt que genera `scripts/verify_fanout.py` manda acá, no
> al `SKILL.md` entero. La orquestación —reparto, barrera, resolución, escritura del hermano— vive en
> `../SKILL.md`; la forma literal del JSON de salida viaja en el propio prompt.

## La fuente

⛔ **La fuente es el PDF (#205).** `Read` lo rasteriza, así que **ves** la página: prosa, ecuaciones,
tablas y figuras. Citá por **página**. El `.txt` es el **índice**: sirve para ubicar con `grep -n`,
nunca para citar — `pdftotext` pierde sin avisar radicales, primas, superíndices y subíndices.

| Regla | En una línea |
|---|---|
| **localizar antes de leer** | `grep -n` sobre el `.txt` te dice **en qué zona** está la afirmación; después abrís esa parte del PDF. En un paper corto podés leerlo entero y saltear el paso. ⚠ Grepear un `.txt` tiene sus mañas —entrelazado de columnas, guiones de corte, espacios que no se normalizan— y están en `convenciones-fulltext.md`. |
| **`pdf_source: eprint`** (#57) | el PDF es el **preprint**: una discrepancia numérica contra un valor publicado es candidata a **diferencia de versión**, no a cita rota. ⛔ Nunca "corregir" la nota hacia el eprint. `null` = desconocido, que **no** es "publicado". |
| **documento largo** (#80) | un libro no se rasteriza entero. Ahí el `.txt` como índice es **imprescindible**: grepeás, sacás la página, abrís **esas** páginas del PDF. La unidad de cita la declara `unidad_cita` y el recorte, `alcance`. |
| **fuente WEB** (#205 / AUD-204) | ⛔ **excepción nombrada: acá el `.txt` SÍ es la fuente.** Una nota con `source_url` poblado (`pdf: null`, snapshot de `fetch_web`) no tiene PDF **por diseño**, y el argumento de #205 no le aplica: ahí el `.txt` no es una copia degradada de un original, **es la captura**. Es determinista (defuddle, URL + fecha) y es lo que la cita referencia con `accessed`. Se cita por **línea** y la fila lleva **`txt:<sha10>`**. |
| **agotar antes de concluir** | si la afirmación no aparece donde el índice la ubica, ampliá la ventana de páginas antes de concluir. `no verificable por extracción` queda para el PDF que es un escaneo ilegible incluso a ojo — distinto de `no-soportada`. |

## Qué devolvés por cada par

Por cada fuente, el subagente:
- Localiza el **PDF**: `vault/raw/pdfs/**/<bibcode>.pdf` (el bibcode puede vivir bajo cualquier
  slug/tema — usar glob), y su `.txt` hermano en `vault/raw/fulltext/**/` como índice para grepear.
  ⚠ **Si la nota tiene `source_url` y `pdf: null`, es una fuente WEB**: no hay PDF que buscar y el
  `.txt` es la fuente (ver la tabla de § La fuente).
  **Ojo:** los nombres tienen `&` y puntos → citarlos entre comillas simples al leer/grep.
- Lee **sólo esa fuente** (grounding-first; **prohibido** responder de memoria o de otro paper).
- ⛔ **Una cita entrecomillada que lleva OTRO `[[bibcode]]` adyacente no es tuya (#316).** El par se
  arma por **bloque**, así que un párrafo que contrasta dos o tres fuentes te llega entero: la
  afirmación que tenés que juzgar es la del bloque, no cada `«…»` que aparezca en él. Si la cita
  pertenece a otra fuente del mismo bloque, **decilo en la `nota` y no la cuentes en contra** —
  medido: 12 de 12 hallazgos duros de un hub eran esto, y «resolverlos» reatribuyendo la cita al
  bibcode contra el que se testeó **habría destruido la inferencia que la nota declara**.
- Devuelve, para la afirmación dada:
  - `veredicto`: `soportada` | `no-soportada` | `contradice` — **vocabulario cerrado**, y el eje es
    **sólo el respaldo textual**: ¿la fuente dice esto? La pregunta «¿está completa la afirmación?»
    vive en `condicion`, que es una columna aparte. **Distinguir los dos modos
    de falla** (alineado al estándar de 4 categorías tipo CAQA): `no-soportada` = la fuente **calla**
    (no dice nada de eso → error de cita); `contradice` = la fuente **afirma lo contrario** (valor
    incompatible más allá del error, existencia negada, signo opuesto) — también exige cita textual,
    de lo que el paper **sí** dice.
  - `evidencia`: **cita textual** del paper + **nº de página del PDF**. **Sin cita textual ⇒ `no-soportada`**
    (regla dura: si no puede pegar la frase, no está respaldado). La cita tiene que tocar el
    **contenido distintivo** de la afirmación (el sujeto/valor/mecanismo que la hace específica); si
    lo único que matchea es terreno común del tema (el fenómeno general, un término suelto, la mera
    cercanía temática) ⇒ `no-soportada`. **Sin punto medio**: ablandar un claim genérico a un
    veredicto tibio es el modo de falla típico del verificador — es exactamente lo que mide el
    benchmark, y por eso `parcial` salió del vocabulario en 1.39.0 (ver abajo).
  - `nota`: una línea de por qué (sobre todo en `no-soportada`: qué dice el paper en cambio).
    Si la afirmación es **multi-cláusula**, decir **qué cláusula** respalda el paper y cuáles no.
  - `condicion` (**siempre; el hallazgo que ninguna capa veía, #74**): ¿el paper afirma esto **bajo
    condiciones** que la nota no dice? (SNR, muestreo, tamaño de muestra, definición del observable,
    época, rango de parámetros). Si sí, **citarlas**. Es un **hallazgo aparte**, no un grado de
    soporte: la afirmación pelada **sí está** en el paper, así que el veredicto sigue siendo
    `soportada` — por eso la sobre-generalización pasaba entera por este chequeo. Es el "afirmar de
    menos" de las tablas truncadas, en versión conceptual: la nota no afirma falso, afirma **de
    más**. En una nota de **concepto** la resolución tiene lugar propio: la condición va a
    `## Régimen de validez`; en una ficha, se agrega a la afirmación.
  - ⛔ **Y la CLASIFICA, con vocabulario cerrado (#221): `acota` o `contextualiza`.** El test es
    operativo: ***¿la afirmación queda FALSA si se saca la condición?*** Sí → `acota` (el umbral es
    de otra estrella, la medición no es sobre RVs, el escalado es por fila): **se resuelve sí o sí**
    —fila de `## Régimen de validez`, o corrección de la prosa—. No → `contextualiza` (instrumento,
    tamaño de muestra, año, definición): **va al reporte y no obliga a editar**, y ahí rige la regla
    de poda. Medido sobre 96 pares: **86 con condición poblada (89 %)** contra **7 % de
    completitud**, que #198 ya había acotado. Sin clasificar, «resolvé cada condición no vacía» es
    la nota entera —86 filas de régimen sobre 413 líneas, contra la regla de poda—, así que se deja
    de cumplir **en silencio**. ⚠ Y el 89 % **no es ruido**: *«el S/N está medido en el continuo a
    4000 Å»*, *«el umbral crítico baja de 200 a 75 para la enana K»*, *«la medición no es sobre
    RVs»* — varias vuelven **falsa** la afirmación fuera de su régimen. Lo que faltaba era el
    criterio, no la señal. La celda del bloque se escribe `acota: …` / `contextualiza: …`, y el lint
    reporta como backlog la que no lo declara.
  - `completitud` (**sólo cuando el par sale de una transcripción** de tabla o lista de la fuente):
    ¿la tabla/lista del paper tiene **más filas/ítems** que los que la nota transcribe? Si sí,
    **listarlos** (con nº de línea). Es un **hallazgo aparte**, no un grado de soporte: no cambia el
    veredicto de la fila que sí está.

> **Claims multi-cláusula (espeja la regla del paso 1).** Una afirmación suele arrastrar varias
> cláusulas: una de encuadre sin cita, la atribuida a *esta* fuente, y a veces las de *otras*
> fuentes citadas al lado. El subagente juzga **la parte que se le atribuye a su paper** — que el
> archivo respalde una cláusula vecina (de otra fuente, o el encuadre genérico) **no** hace
> `soportada` a la afirmación: es exactamente la mezcla "el dato de A atribuido a B" que este
> chequeo existe para atrapar. Sin esta instrucción el subagente juzga el conjunto y **hedgea**.
> Medido el 2026-08-25: de 14 defectos reales encontrados en una ficha, **3 eran justamente eso**
> —un número leído en A que A atribuye a B— y uno sobrevivió una corrida entera como veredicto tibio
> antes de que la segunda lo llamara `no-soportada` tras grepear el archivo y no encontrarlo.

> **Transcripciones: chequear también lo que la nota OMITE (#49).** El fan-out valida lo que la nota
> **afirma**; una tabla transcrita **sin un solo error** pero a la que le faltan filas vuelve
> **100% soportada** — cada par verificado era verdadero (medido: 14 registros transcritos, los 14
> correctos… sobre una tabla de **21 filas** en el paper). Es un modo de falla **distinto** del *grounding gap*: la nota no afirma nada falso,
> **afirma de menos**, y una tabla truncada se lee como completa. Por eso, cuando el par sale de una
> **transcripción** (tabla o lista de la fuente), el subagente recibe además la pregunta de
> **completitud** (arriba) y el faltante se reporta como **hallazgo propio**, distinto del veredicto
> de soporte. Vale para cualquier enumeración que la nota presente como cerrada (una lista de
> máscaras, de extensiones, de keywords), no sólo para tablas con pipes.
>
> El caso más frecuente de esto en una bóveda es el **`## Inventario por eje`** (#72), que es
> transcripción por construcción: cada fila dice qué reporta un paper sobre un eje en disputa. Ahí
> la pregunta de completitud no es "¿la fuente tiene más filas?" sino **"¿hay más papers del corpus
> que reportan este eje y no están en la tabla?"** — un inventario sin errores pero **incompleto**
> vuelve 100% soportado y se lee como el estado de la literatura.

## El corte: contenido distintivo, sin grado

**No hay score.** El veredicto sale de **una** pregunta, y es de sí o no: ¿la evidencia citada toca
el **contenido distintivo** de la afirmación —el sujeto/valor/mecanismo que la hace específica—?
→ `soportada`, y lo que falte va a `condicion`. ¿La coincidencia es sólo temática (el fenómeno
general, un término suelto, la mera cercanía)? → `no-soportada`.

⚠ **No agregues un grado.** Un veredicto intermedio o un puntaje mezcla el eje textual (¿la fuente
dice esto?) con uno de intensidad sin umbral calibrado, y es justo donde dos corridas ciegas del
mismo fan-out divergen. Lo que parece un grado o es una **condición** (columna aparte) o es una cita
que no toca el contenido distintivo (`no-soportada`). La historia y la medición están en
`historia-veredictos.md`.

- **`contradice`** manda sobre los otros dos (no es un grado de soporte sino evidencia **en contra**,
  con cita textual de lo contradicho): se resuelve como corrección o disputa (paso 4 del `SKILL.md`), no como cita rota.
