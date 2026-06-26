---
name: verify-citations
description: Usar para verificar, afirmación por afirmación, que las citas [[bibcode]] de una nota de la wiki (query, hipótesis, ficha, concepto) realmente están respaldadas por el texto completo de la fuente. Se corre como paso de cierre al armar/editar una query o hipótesis, o cuando el usuario pide "rechequeá las citas / ¿esto lo dice el paper?". Implementa el chequeo claim↔evidencia (pipeline tipo CiteAudit) sobre el corpus cerrado de la bóveda.
version: 1.0.0
---

# Verify-citations — chequeo claim↔evidencia contra el fulltext

Operación de **verificación** del patrón LLM Wiki (extensión propia de esta wiki; el lint canónico de
Karpathy sólo hace chequeos de salud estructurales, **no** valida que la fuente respalde la afirmación).
Tapa el *grounding gap* / *epistemic drift*: el LLM puede escribir una cita correcta junto a una
afirmación que el paper **no dice** (estudios: 50–90% de citas en texto largo de LLM no están
plenamente respaldadas). Acá cada afirmación se contrasta contra el texto real de su fuente.

> **Ventaja del corpus cerrado:** corpus **cerrado** — hay un `.txt` por bibcode en `raw/fulltext/`. Se
> saltea el *retrieval* (la parte que mete errores en los verificadores generales): ya sabemos qué
> archivo leer. El chequeo es directo passage-matching.
>
> **El fulltext es una extracción DETERMINISTA** de la capa de texto del PDF (`pdftotext -layout`,
> sin LLM ni OCR). Por eso la **cita textual que encuentra el verificador son las palabras reales del
> paper** y el nº de línea es un localizador greppable estable. **Caveats:** `pdftotext` puede
> desordenar doble-columna, ecuaciones, tablas, ligaduras y guionado; y un PDF **escaneado sin capa de
> texto** da `.txt` vacío/basura. Por eso: si una afirmación **no** aparece textual en el `.txt`, antes
> de declararla `no-soportada` considerar que puede ser un **artefacto de extracción** (ecuación/tabla)
> → en ese caso abrir el **PDF** (`raw/pdfs/<slug>/<bibcode>.pdf`) para esa afirmación puntual, o
> marcarla **`no verificable por extracción`** (distinto de `no-soportada`).

## Cuándo correrlo
- **Paso de cierre obligatorio** de `query-corpus` y `test-hypothesis`, **antes de archivar/commitear**.
- A pedido: "rechequeá las citas", "¿esto lo dice el paper?", al editar una nota con citas.

## Entrada
La **ruta de la nota** a verificar (p. ej. `wiki/queries/crx-slope-values.md`). Si no se da, usar la
última nota tocada en la operación en curso.

## Pasos

### 1. Extraer los pares (afirmación, referencia)
Leer el cuerpo de la nota (no el frontmatter) y descomponerlo en **afirmaciones atómicas**: cada
fila de tabla con un valor, cada bullet o frase que asevera un hecho. Para cada afirmación, listar
**cada `[[bibcode]]` que la acompaña por separado** (si una afirmación cita `[[A]]` y `[[B]]`, son
**dos pares** — cada fuente debe respaldar la parte que se le atribuye; así se atrapan las mezclas
"el dato de A atribuido a B").

**Excepciones (no se verifican, pero se chequea la marca):**
- **Valores de ground-truth (NEA) en fichas de estrella** → los parámetros planetarios (P/K/e/m·sin i,
  status, nº de planetas) del **frontmatter** y de la **tabla de inventario** vienen de **NEA**
  (`raw/ground_truth/<slug>.json`), **no** de un paper. **NO se verifican contra el fulltext** — de su
  consistencia se ocupa el **lint** (contradicción GT↔ficha + masa implícita por K/P/e/M\*). Verificar
  un valor NEA contra un paper es un **error de categoría** (el paper de descubrimiento suele dar un
  valor algo distinto al best-value combinado de NEA, y eso NO es una cita rota). Regla: si el número
  está en la tabla de inventario / frontmatter y la fila dice "NEA", se **saltea**.
- **Sí se verifican** (van al fan-out) las afirmaciones atribuidas a un `[[bibcode]]`: las
  **disputas** (`disputes[].alt` y `.note` vs el paper discrepante — p. ej. la Tabla 9 de Díaz+2016),
  los **mecanismos**, la **síntesis**, y cualquier **valor que el prose atribuya a un paper** (si la
  oración cita a Mayor+2009, el número debe ser el de Mayor, no el de NEA → si no, corregir el prose a
  los valores de la fuente y dejar NEA en la tabla).
- Afirmaciones marcadas **`inferencia`** explícitamente → se **saltean** del fan-out y se listan aparte
  como "inferencia declarada" (válidas sin cita; ver frontera/estilo en `CLAUDE.md`).
- Definiciones/derivaciones internas (sanity-checks de unidades, etc.) sin `[[bibcode]]` → no requieren
  fuente, pero si **afirman un hecho del mundo** sí.
- Una afirmación con número/aseveración fáctica y **sin** `[[bibcode]]` ni marca `inferencia` →
  **flag "afirmación sin cita"** (hay que citarla o marcarla inferencia).

### 2. Fan-out: un subagente independiente por par
Para cada par, lanzar un subagente (tipo `Explore`) **en paralelo** (varios en un mismo mensaje).
Cada uno:
- Localiza el fulltext: `raw/fulltext/**/<bibcode>.txt` (el bibcode puede vivir bajo cualquier
  slug/tema — usar glob). **Ojo:** los nombres tienen `&` y puntos → citarlos entre comillas simples
  al leer/grep.
- Lee **sólo ese archivo** (grounding-first; **prohibido** responder de memoria o de otro paper).
- Devuelve, para la afirmación dada:
  - `veredicto`: `soportada` | `parcial` | `no-soportada`
  - `score`: 0–10 (qué tan literal/completo es el respaldo)
  - `evidencia`: **cita textual** del paper + **nº de línea**. **Sin cita textual ⇒ `no-soportada`**
    (regla dura: si no puede pegar la frase, no está respaldado).
  - `nota`: una línea de por qué (sobre todo en `parcial`/`no-soportada`: qué dice el paper en cambio).

Prompt sugerido por agente: *"Leé SOLO `<ruta fulltext>`. ¿El paper respalda esta afirmación: «…»?
Respondé veredicto (soportada/parcial/no-soportada) + score 0–10 + cita textual con nº de línea + nota.
Si no encontrás respaldo textual, es no-soportada. No uses memoria ni otros papers."*

### 3. Umbral y agregación
- `score ≥ 7` → **soportada**
- `4 ≤ score ≤ 6` → **parcial** (revisar: matiz, rango distinto, atribución cruzada)
- `score < 4` → **no-soportada**

### 4. Resolver lo que falla (no dejar pasar)
Cada **parcial / no-soportada** se resuelve antes de cerrar:
- **Atribución cruzada** (el hecho está, pero en otro de los papers citados) → reasignar la cita al
  bibcode correcto.
- **Afirmación estirada** (el paper dice menos/distinto) → **bajar** la afirmación a lo que la fuente
  sí dice (corregir el número/rango/alcance).
- **Sin respaldo en ninguna fuente** pero físicamente razonable → re-etiquetar **`inferencia`**
  (y quitar la cita que no corresponde).
- **Cita rota / fuente equivocada** → corregir o eliminar.

### 5. Escribir el bloque de veredicto en la nota
Agregar/refrescar al final de la nota (idempotente — si ya existe, reemplazar):

```markdown
## Verificación de citas (YYYY-MM-DD)
Chequeo afirmación↔fulltext (skill `verify-citations`). N pares; X soportadas / Y parciales / Z no-soportadas (resueltas).

| Afirmación (resumen) | Ref | Veredicto | Score | Evidencia |
|---|---|---|---|---|
| YZ CMi κ ≈ −2.6 | [[2018A&A...609A..12Z]] | soportada | 9 | "gradient of −2.6 Np−1 (±21%)" (L966) |
| activas −2.4/−2.6 | [[2025A&A...696A..27J]] | no-soportada→corregida | 2 | el paper da −2.65 a −3.70; el −2.6 es de Zechmeister |

Inferencias declaradas (sin cita, por diseño): <listar>.
```
Convertir fechas relativas a absolutas. Notación `$...$` en archivos `wiki/` (texto plano en chat).

### 6. Lint + cierre
Correr `python scripts/lint.py` (debe quedar 0 en lo bloqueante, incl. **0 fuga-sim** y **0 citas
no verificables**). Si el usuario pidió archivar/commitear, `git add` de los archivos **específicos**
y commit descriptivo; **preguntar antes de `push`**. Appendear a `wiki/log.md` (resumen del chequeo:
cuántas soportadas/corregidas).

## Reporte (al chat)
Veredicto global honesto: total de pares, cuántas soportadas, y **cada corrección hecha** (qué se
bajó/reasignó/marcó inferencia). No maquillar: una afirmación que se estiró y se corrigió es un
hallazgo del chequeo, no un fracaso. Si algo quedó dudoso, decirlo.

## Límite honesto
El chequeo es **juicio de un LLM** leyendo la fuente — robusto (independiente por par, grounding-first,
cita textual obligatoria) pero **no una prueba**. Reduce drásticamente la mala atribución; no la elimina.
