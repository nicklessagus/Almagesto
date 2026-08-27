---
name: setup
description: Usar cuando el usuario quiere definir o reescribir el OBJETIVO de la bóveda — el archivo que orienta qué papers son "core" ("configurá la bóveda", "definí el objetivo", "armá el objective.yaml", "quiero usar Almagesto para el tema X", "ajustá la regla de relevancia", "para qué va a servir esta bóveda"). El agente traduce el foco en lenguaje natural a `objective.yaml` (incluida la regex `relevance.facets`) y la afina contra ADS con un preview, para que el usuario NO escriba regex a mano. NO ingesta nada: después se usan ingest-star / ingest-theme.
version: 1.3.0
---

# Setup: definir el OBJETIVO de la bóveda

Operación de **configuración** del patrón LLM Wiki (ver `CLAUDE.md`). Genera/afina **un solo archivo**:
`vault/config/objective.yaml` — la **lente** de la bóveda. No baja ni escribe contenido; cuando termina,
el usuario carga estrellas/temas y corre `ingest-star` / `ingest-theme`. Trabajar desde la raíz del repo.

**Por qué existe:** la parte difícil de instanciar es redactar `relevance.facets` (la regex que decide
qué paper es "core") y nombrar las `concept_areas`. Una regex a mano sale mal (trae ruido o pierde
papers). Este skill lo hace **el agente**, y lo **valida contra papers reales** antes de cerrar.

**Qué controla el objetivo (tenelo claro al redactar):**
- `relevance.facets` = **clasificador de relevancia**. Un paper es **core** si satisface la **regla de
  combinación** (por default OR: ≥1 bucket; ver `relevance.require`/`min_facets` en el paso 2 — regex
  sobre título+abstract+keywords, case-insensitive) **y** su `doctype` no es ruido. Core →
  se baja el PDF + fulltext + extracción LLM; no-core → solo se cuenta. **No** define la query a ADS
  (para estrellas la query es por nombre; para temas, la Solr cruda de `themes.yaml`).
- `name`/`short`/`description` = **lente de síntesis** (orientan qué destila el LLM y qué es un "hueco").
- `concept_areas` = áreas **abiertas** de `concepts/` (solo referencia para el typo-check; ver `CLAUDE.md`).

## Pasos

1. **Entender el foco (en palabras, sin regex).** Preguntar al usuario:
   - ¿Qué mecanismo / técnica / concepto querés investigar? (puede ser astro o no).
   - ¿Un paper "core" para vos es…? Pedir **1–2 ejemplos ideales** y, si puede, 1 que NO querría — afina
     muchísimo la regla.
   - ¿La bibliografía vive en ADS (astro) o fuera (p. ej. un método de otra disciplina)? Si es **off-ADS**, ver el paso 6.
   - **¿Cuál es la faceta-eje?** — la que, si falta, el paper **no sirve** por más que matchee todo lo
     demás (p. ej. `rv` en una bóveda de velocidades radiales: un paper de actividad estelar que nunca
     toca RV es contexto, no core). Preguntarla explícitamente: define `relevance.require` (paso 2), que
     es la palanca real contra el ruido. Si el usuario no identifica ninguna, se queda en OR.
   No avanzar sin un foco claro.

   ⛔ **Y después de escuchar, PROPONER (#83).** Ofrecer **2–4 facetas adyacentes que el usuario no
   nombró**, cada una con una línea de por qué, para que las acepte o descarte. El usuario sigue
   decidiendo; lo que cambia es que la lente deja de quedar limitada a lo que recordó en una
   conversación corta. La asimetría está al revés de donde debería: el usuario conoce su foco, pero
   **el agente es el que tiene el corpus delante**. Y el costo de que falte una faceta no es
   simétrico — lo que la lente descarta **no se baja**, así que un falso negativo no deja rastro y
   sólo se recupera re-clasificando el corpus entero (sub-modo de `maintain`).

   **Separar dos cosas al escuchar el foco (clave para no equivocar el archivo):**
   - **Facetas** = qué hace a un paper relevante (p. ej. "ciclos de actividad", "períodos de rotación",
     "separación de fuentes") → van a `relevance.facets`. Son **constantes**: la misma lente clasifica
     los papers de una estrella *y* los de un tema (lo que cambia entre ingest-star e ingest-theme es el
     **sujeto/query**, no la lente).
   - **Sujetos** = las estrellas o el tema concretos (p. ej. "HD 152391", "BSS sobre RV") → **NO** van en
     `relevance.facets`; van en la query (`stars.yaml` / la Solr de `themes.yaml`). Nombres de estrella en
     la regex = error típico.
   - **Deliverable** = "hacer un paper / una tesis sobre…" → va en `name`/`description` (lente de
     síntesis), no en la regex.

2. **Redactar `objective.yaml` (lo hace el agente).** Campos:
   - `name`: frase corta y específica del objetivo.
   - `short`: etiqueta de 3–6 palabras.
   - `description`: 2–3 líneas (qué reúne y para qué decidir).
   - `relevance.facets`: **varios buckets nombrados**, cada uno una faceta del tema; regex de Python en
     **comillas simples**, **una línea por patrón** (YAML literal: `\b` y demás llegan intactos). Cubrir
     **sinónimos en inglés** (ADS es inglés), instrumentos y términos técnicos. Recordar que por default es
     un **OR**: basta que matchee 1 bucket. Partir del ejemplo del template como molde de formato.
   - `relevance.require` / `relevance.min_facets`: la **regla de combinación** — parte del objetivo, no
     config avanzada. Por default es OR (≥1 faceta): está calibrado para el pool chico de la query directa
     y **se rompe apenas el pool se amplía** por citation chaining, porque una faceta laxa deja de
     discriminar. Con la faceta-eje del paso 1, proponer `require: [<eje>]` (AND) y/o `min_facets: 2`
     (≥N cualesquiera). Core = (≥ min_facets facetas) Y (todas las de require) Y (doctype no-ruido).
     La palanca contra el ruido es la **obligatoriedad**, no podar regex — medido en una bóveda de RV:
     podar las regex bajó AU Mic de 928 a 762 core (paliativo); declarar `require: [rv]` la llevó a
     **198**. ⚠ Estos números y los del docstring de `query_ads.py` (928→254 para la misma
     operación) salen de corridas distintas y **no reconcilian**: tomalos como orden de magnitud
     y re-medí con `--probe` sobre tu propia lente. Dejar ambas sin declarar = OR histórico. **Cada faceta de `require` debe existir en
     `facets`** (si no, el clasificador aborta).
     **Corolario (decírselo al usuario):** una vez declarada `require` con `min_facets: 1`, afinar las
     **otras** facetas ya **no cambia el corte** (core ⟺ matchea la eje ∧ doctype limpio) — sólo etiqueta.
     Lo que hay que cuidar es el **recall de la faceta-eje**: listar todos sus sinónimos e instrumentos.
     Las demás facetas siguen siendo útiles como etiquetas (y para `min_facets ≥ 2`).
   - `relevance.search_fq`: ⛔ **la lente del BUSCADOR** (#85, #152 — faltaba en este skill). Es el
     `fq` de Solr que acota el universo **server-side, antes de traer nada**: la mitad **más
     restrictiva** del filtro, más que `relevance.facets`, que actúa después sobre lo ya traído.
     Tres estados, y los tres son decisiones distintas:
       · **sin declarar** → `database:astronomy` (el default histórico);
       · **con valor** → ése;
       · **`search_fq: null`** → no acota, todo ADS **a propósito**.
     Un `null` declarado NO se lee igual que no declarar nada, y por eso se escribe.
     **Cuándo cambiarlo:** si la bóveda va a traer **métodos de otras disciplinas** (estadística, ML,
     signal processing) cuya bibliografía canónica ADS no clasifica como astronomía, el default los
     mata antes de que `facets` los vea. Preguntárselo al usuario en el paso 1, no asumirlo.
   - `noise_doctypes`: el default (catalog, proposal, abstract, erratum, bookreview, newsletter,
     pressrelease, circular, software) salvo razón.
   - `concept_areas`: sugerir 3–5 áreas según el foco (`methods`/`hypotheses` reservadas + las que
     tengan sentido). Son abiertas: es un punto de partida, no una jaula.
   - `downstream`: **opcional** (D-50) — los nombres propios de quien va a **consumir** la bóveda (un
     repo, un pipeline). No cambia la clasificación: es el insumo del detector de fuga de la frontera
     dura, que marca la prosa que describe al consumidor (*"los scripts de X lo usan para…"*) — el modo
     de fuga más frecuente y el que no deja rastro estructural. Sólo los nombres se declaran acá; el
     framework nunca los hardcodea (meterlos sería justo lo que la regla #0 prohíbe). **Vacío o ausente
     = esa mitad del detector apagada, sin WARN**: una bóveda sin consumidor nombrado es el caso normal.

3. **Mostrar al usuario en prosa — NUNCA la regex (D-8).** El usuario no valida un patrón: valida una
   **lista de términos**. Decir, bucket por bucket, qué palabras van a buscarse —traducidas al inglés
   (ADS es inglés), con la morfología cubierta a mano (no hay stemmer: `rotation`/`rotational`/`rotating`
   son tres términos, no uno) y los nombres propios de instrumentos y códigos—. Explicar el OR y el
   filtro de ruido. **Leer el patrón no valida nada**: lo que valida es el paso 4, contra papers reales.

   ⚠ **Decirle el costo (D-13).** Con "el ingest lee **todos** los core", la lente no es sólo un filtro
   de ruido: es el **presupuesto del ingest**. Una faceta laxa que deja entrar 900 papers son 900
   extracciones, no sólo ruido en la ficha. `relevance.require` es, además de la palanca contra el
   ruido, la perilla del costo — y ése es el marco en el que conviene elegirla.

4. **Preview contra ADS — afinar la regex con papers reales (el corazón del skill).**
   - Escribir el `objective.yaml` borrador (necesario: `--probe` lee `relevance.facets` de ahí).
   - Armar una **query Solr de prueba amplia** a partir de los términos centrales del foco (p. ej.
     `abs:"radial velocity" OR abs:"stellar activity"`). **Ojo:** la query de prueba **no es** la regex
     — es solo para traer una muestra de papers del área y ver cómo los corta el clasificador.
   - Correr: `python scripts/query_ads.py --probe "<query de prueba>" --rows 50`
   - Leer el corte que imprime: `N CORE / no-core`, el top por citas con marcador `[CORE/—]` + qué
     tópicos matchearon, y el **contraste de la regla de combinación** que cierra el reporte: sin regla
     declarada lista qué cortaría **cada faceta si fuera la obligatoria** (`require: [rv] → 123 CORE
     (−52%)`); con regla declarada, cuánto se está cortando respecto del OR puro. **Ese contraste es el
     que decide `require`** — mostrárselo al usuario en vez de argumentarlo.
   - **Juzgar:** ¿se cuela ruido (marcó CORE algo que no debería)? ¿se pierde algo
     bueno (marcó — un paper claramente relevante)? **Editar `relevance.facets`** (sumar/sacar términos o
     buckets) y **re-correr `--probe`**. Iterar 1–3 veces hasta que el corte cierre.
   - ⛔ **Y mirar el bloque «¿FALTA UNA FACETA?»** que el probe imprime (#83): los términos que se
     repiten entre los **no-core** y que ninguna faceta matchea. No son términos inventados — son
     las `keywords` que ADS devuelve, el único vocabulario de la bóveda que no sale de una regex
     nuestra ni de la memoria de un LLM. Si varios papers pertinentes caen afuera **por la misma
     razón**, eso es una **faceta faltante**, no términos faltantes.
   - ⚠ **Son dos ediciones distintas y el skill no las trataba así.** Una **faceta nueva** cambia la
     *estructura* de la lente, y con ella el efecto de `require` y `min_facets`; un **sinónimo**
     sólo mueve el recall de una faceta que ya existe. Decir cuál de las dos se está proponiendo.
   - Mostrar el corte final al usuario y **confirmar** antes de dar por cerrado.
   - Si **no hay token ADS** cargado (`vault/config/ads_dev_key` o `ADS_DEV_KEY`): saltar el preview,
     dejar el borrador y avisar que la regla se afina sola en el primer `ingest` (que ya previsualiza).

5. **Frontera dura (regla #0, ver `CLAUDE.md`).** El objetivo describe **de qué trata** la bóveda y
   **qué papers son core** — **nunca** a quien la consume, ni parámetros/dials/decisiones de
   implementación. Solo bibliografía citable.

6. **Off-ADS (biblio fuera de ADS — p. ej. métodos de otra disciplina).** El objetivo igual define `name`/`description`/
   `concept_areas`. Pero `relevance.facets` y el preview `--probe` dependen de ADS (astro): si el tema
   es off-ADS, anotarlo y **no** forzar el preview — la ingesta usa PDFs locales + web (ver `ingest-theme`
   modo off-ADS). `relevance.facets` queda como guía mínima, no como filtro automático.

7. **Cierre.** Dejar el `objective.yaml` final. Correr `python scripts/lint.py` (no debería romper nada).
   Actualizar `vault/STATUS.md` (objetivo seteado) y appendear a `vault/wiki/log.md`. **No commitear**
   salvo pedido. Recordar los **próximos pasos**: cargar token ADS si falta, agregar estrellas a
   `vault/config/stars.yaml` / el tema a `vault/config/themes.yaml`, y correr `ingest-star` /
   `ingest-theme`.

   ⛔ **Si la bóveda YA tiene contenido, el cierre no termina acá: hay que re-clasificar.** Cambiar
   `relevance.facets` (o la regla de combinación `require`/`min_facets`) **re-clasifica el corpus
   entero**: papers que dejan de ser core, papers que recién ahora entran, y apéndices "Excluidos por
   el filtro" estampados con el corte viejo. Nada de eso pasa solo — sin este paso el usuario se va
   con el `objective.yaml` nuevo y el corpus clasificado con la regla vieja, **sin ninguna señal**.
   Va por el sub-modo **D de `maintain`**, y empieza por el dry-run (offline, no consulta ADS ni
   escribe): `python scripts/query_ads.py --dry-run` muestra el delta —cuántos salen del core
   separando los que tienen extracción LLM de los stubs, y cuántos entran— antes de tocar nada.
   Decirlo explícitamente al usuario en el cierre, no darlo por sabido.

## Notas

- `objective.yaml` es **archivo de instancia** (`merge=ours`): editarlo es seguro, no se pisa al traer
  updates del framework.
- Este skill **no ingesta**. Es el paso 0; la bibliografía entra después con `ingest-star`/`ingest-theme`.
- Reescribir el objetivo más adelante es válido (afinás la lente): re-correr este skill y
  re-previsualizar — pero sobre una bóveda **poblada** eso arrastra el sub-modo **D de `maintain`**
  (re-clasificar el corpus + re-estampar los apéndices); ver el paso 7.
