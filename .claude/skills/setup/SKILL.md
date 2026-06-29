---
name: setup
description: Usar cuando el usuario quiere definir o reescribir el OBJETIVO de la bóveda — el archivo que orienta qué papers son "core" ("configurá la bóveda", "definí el objetivo", "armá el objective.yaml", "quiero usar Almagesto para el tema X", "ajustá la regla de relevancia", "para qué va a servir esta bóveda"). El agente traduce el foco en lenguaje natural a `objective.yaml` (incluida la regex `relevance.topics`) y la afina contra ADS con un preview, para que el usuario NO escriba regex a mano. NO ingesta nada: después se usan ingest-star / ingest-topic.
version: 1.0.0
---

# Setup: definir el OBJETIVO de la bóveda

Operación de **configuración** del patrón LLM Wiki (ver `CLAUDE.md`). Genera/afina **un solo archivo**:
`vault/config/objective.yaml` — la **lente** de la bóveda. No baja ni escribe contenido; cuando termina,
el usuario carga estrellas/temas y corre `ingest-star` / `ingest-topic`. Trabajar desde la raíz del repo.

**Por qué existe:** la parte difícil de instanciar es redactar `relevance.topics` (la regex que decide
qué paper es "core") y nombrar las `concept_areas`. Una regex a mano sale mal (trae ruido o pierde
papers). Este skill lo hace **el agente**, y lo **valida contra papers reales** antes de cerrar.

**Qué controla el objetivo (tenelo claro al redactar):**
- `relevance.topics` = **clasificador de relevancia**. Un paper es **core** si matchea **≥1** bucket
  (OR; regex sobre título+abstract+keywords, case-insensitive) **y** su `doctype` no es ruido. Core →
  se baja el PDF + fulltext + extracción LLM; no-core → solo se cuenta. **No** define la query a ADS
  (para estrellas la query es por nombre; para temas, la Solr cruda de `topics.yaml`).
- `name`/`short`/`description` = **lente de síntesis** (orientan qué destila el LLM y qué es un "hueco").
- `concept_areas` = áreas **abiertas** de `concepts/` (solo referencia para el typo-check; ver `CLAUDE.md`).

## Pasos

1. **Entender el foco (en palabras, sin regex).** Preguntar al usuario:
   - ¿Qué mecanismo / técnica / concepto querés investigar? (puede ser astro o no).
   - ¿Un paper "core" para vos es…? Pedir **1–2 ejemplos ideales** y, si puede, 1 que NO querría — afina
     muchísimo la regla.
   - ¿La bibliografía vive en ADS (astro) o fuera (tema no-astro)? Si es **off-ADS**, ver el paso 6.
   No avanzar sin un foco claro.

   **Separar dos cosas al escuchar el foco (clave para no equivocar el archivo):**
   - **Facetas** = qué hace a un paper relevante (p. ej. "ciclos de actividad", "períodos de rotación",
     "separación de fuentes") → van a `relevance.topics`. Son **constantes**: la misma lente clasifica
     los papers de una estrella *y* los de un tema (lo que cambia entre ingest-star e ingest-topic es el
     **sujeto/query**, no la lente).
   - **Sujetos** = las estrellas o el tema concretos (p. ej. "HD 152391", "BSS sobre RV") → **NO** van en
     `relevance.topics`; van en la query (`stars.yaml` / la Solr de `topics.yaml`). Nombres de estrella en
     la regex = error típico.
   - **Deliverable** = "hacer un paper / una tesis sobre…" → va en `name`/`description` (lente de
     síntesis), no en la regex.

2. **Redactar `objective.yaml` (lo hace el agente).** Campos:
   - `name`: frase corta y específica del objetivo.
   - `short`: etiqueta de 3–6 palabras.
   - `description`: 2–3 líneas (qué reúne y para qué decidir).
   - `relevance.topics`: **varios buckets nombrados**, cada uno una faceta del tema; regex de Python en
     **comillas simples**, **una línea por patrón** (YAML literal: `\b` y demás llegan intactos). Cubrir
     **sinónimos en inglés** (ADS es inglés), instrumentos y términos técnicos. Recordar que es un **OR**:
     basta que matchee 1 bucket. Partir del ejemplo del template como molde de formato.
   - `noise_doctypes`: el default (catalog, proposal, abstract, erratum, bookreview, newsletter,
     pressrelease, circular, software) salvo razón.
   - `concept_areas`: sugerir 3–5 áreas según el foco (`methods`/`hypotheses` reservadas + las que
     tengan sentido). Son abiertas: es un punto de partida, no una jaula.

3. **Mostrar al usuario en prosa** ("con lo que me dijiste, estas son las cosas de la query"): listar los
   buckets con sus términos en lenguaje claro + el YAML propuesto. Explicar el OR + el filtro de ruido.

4. **Preview contra ADS — afinar la regex con papers reales (el corazón del skill).**
   - Escribir el `objective.yaml` borrador (necesario: `--probe` lee `relevance.topics` de ahí).
   - Armar una **query Solr de prueba amplia** a partir de los términos centrales del foco (p. ej.
     `abs:"radial velocity" OR abs:"stellar activity"`). **Ojo:** la query de prueba **no es** la regex
     — es solo para traer una muestra de papers del área y ver cómo los corta el clasificador.
   - Correr: `python scripts/query_ads.py --probe "<query de prueba>" --rows 50`
   - Leer el corte que imprime: `N CORE / no-core`, y el top por citas con marcador `[CORE/—]` + qué
     tópicos matchearon. **Juzgar:** ¿se cuela ruido (marcó CORE algo que no debería)? ¿se pierde algo
     bueno (marcó — un paper claramente relevante)? **Editar `relevance.topics`** (sumar/sacar términos o
     buckets) y **re-correr `--probe`**. Iterar 1–3 veces hasta que el corte cierre.
   - Mostrar el corte final al usuario y **confirmar** antes de dar por cerrado.
   - Si **no hay token ADS** cargado (`vault/config/ads_dev_key` o `ADS_DEV_KEY`): saltar el preview,
     dejar el borrador y avisar que la regla se afina sola en el primer `ingest` (que ya previsualiza).

5. **Frontera dura (regla #0, ver `CLAUDE.md`).** El objetivo describe **de qué trata** la bóveda y
   **qué papers son core** — **nunca** a quien la consume, ni parámetros/dials/decisiones de
   implementación. Solo bibliografía citable.

6. **Off-ADS (tema no-astro / biblio fuera de ADS).** El objetivo igual define `name`/`description`/
   `concept_areas`. Pero `relevance.topics` y el preview `--probe` dependen de ADS (astro): si el tema
   es off-ADS, anotarlo y **no** forzar el preview — la ingesta usa PDFs locales + web (ver `ingest-topic`
   modo off-ADS). `relevance.topics` queda como guía mínima, no como filtro automático.

7. **Cierre.** Dejar el `objective.yaml` final. Correr `python scripts/lint.py` (no debería romper nada).
   Actualizar `vault/STATUS.md` (objetivo seteado) y appendear a `vault/wiki/log.md`. **No commitear**
   salvo pedido. Recordar los **próximos pasos**: cargar token ADS si falta, agregar estrellas a
   `vault/config/stars.yaml` / el tema a `vault/config/topics.yaml`, y correr `ingest-star` /
   `ingest-topic`.

## Notas

- `objective.yaml` es **archivo de instancia** (`merge=ours`): editarlo es seguro, no se pisa al traer
  updates del framework.
- Este skill **no ingesta**. Es el paso 0; la bibliografía entra después con `ingest-star`/`ingest-topic`.
- Reescribir el objetivo más adelante es válido (afinás la lente): re-correr este skill y re-previsualizar.
