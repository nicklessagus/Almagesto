---
name: ingest-topic
description: Usar cuando el usuario pide investigar/ingestar un TEMA en profundidad a la bóveda, como si fuera una estrella pero por tópico ("traé todo sobre actividad y RV", "investigá a fondo el bisector vs actividad", "ingestá el tema de los GP en RV", "armá un concept con la bibliografía de indicadores de actividad"). Dispara una búsqueda ADS por keywords y hace la extracción LLM hacia un concept durable. Soporta además, sólo a pedido explícito, un tema no-astro / fuera de ADS (desde PDFs locales + web; ver Modo off-ADS).
version: 1.6.0
---

# Ingest: agregar un TEMA a la wiki

Operación **ingest** del patrón LLM Wiki (ver `CLAUDE.md`), hermana de `ingest-star` pero por **tema**
en vez de por estrella. División idéntica: los scripts bajan, el LLM procesa. Trabajar desde la raíz
del repo.

**Diferencias con `ingest-star`** (mismo patrón, distinto sujeto: un tema en vez de una estrella):
- La búsqueda ADS es **por keywords** (query Solr cruda), no por nombre vía SIMBAD.
- El producto durable es un **concept** (`concepts/<area>/<concept>.md`), no una ficha de estrella.
- **No hay ground-truth** (no existe NEA/SIMBAD para un tema) → se **saltea `fetch_ground_truth.py`**.
- **No** se toca la matriz método×estrella.
- Las notas de paper llevan `stars: []` y `thesis_links` pre-sembrado al concept.

> **Default = astro vía ADS** (los **Pasos** de abajo). Si el usuario pide **explícitamente** un tema
> **no-astro** o cuya bibliografía vive **fuera de ADS**, usar el **Modo off-ADS** (al final de los
> Pasos). `ingest-star` no tiene este modo: es astro-only.

## Pasos

1. **Co-diseñar la consulta con el usuario (NO traducir en silencio).** El usuario da el tema en
   lenguaje natural ("actividad y RV", "bisector vs actividad"); el valor del skill está en **pulir
   esa intención antes de gastar la búsqueda**. Secuencia:
   - **a. Interpretar y proponer.** Convertir la intención en una **query Solr cruda candidata** y
     **mostrársela explicada** (qué término exige como AND, qué grupo va en OR). Señalar el sesgo:
     p. ej. exigir `abs:"bisector"` como AND deja afuera papers de S-index/FWHM puros.
   - **b. Ofrecer variantes de alcance** (amplia ↔ acotada) y/o **sugerir términos que faltan** según
     lo que entendiste, en castellano (vos traducís a `abs:"..."`). Usar `AskUserQuestion` si la
     elección cambia qué se trae.
   - **c. Validar con un conteo barato** antes de bajar nada (y antes de persistir el slug):
     `python query_ads.py --probe '<query candidata>' --rows 50` y mirar el corte CORE/no-core +
     los títulos top (ordenados por citas). Si trae cientos con ruido o muy pocos, reajustar la
     query y reconfirmar. **No** bajar PDFs hasta que el usuario apruebe la query final. (`--probe`
     recibe la query cruda, así que corre sin que el tema exista todavía en `topics.yaml` —
     `--topic <slug>` recién funciona después del paso d.)
   - **d. Persistir.** Recién entonces escribir/actualizar la entrada en `vault/config/topics.yaml`:
     `title`, `area` (abierta: cualquiera; idealmente una de `concept_areas` de `objective.yaml` —
     ej. `indicators|methods|activity|hypotheses` — para que el typo-check la reconozca; si es un área
     nueva real, agregala a esa lista), `concept` (nota destino, existente o
     a stubbear), `query` (la Solr cruda aprobada) y `aliases` opcional. Si el tema ya existía en el
     YAML, ofrecer reusar la query guardada o re-pulirla.

2. **Cadena mecánica** — un solo comando (correr desde `scripts/`):
   ```bash
   python ingest_topic.py <slug>
   ```
   El orquestador despacha según el campo `source` de la entrada del tema (`ads` si falta) y en
   modo ADS equivale a correr, en orden y **sin `fetch_ground_truth`** (todo idempotente — si algo
   falla se re-corre, o se corre por partes):
   ```bash
   python query_ads.py   --topic <slug>
   python fetch_arxiv.py         <slug>
   python make_notes.py  --topic <slug>
   python extract_fulltext.py    <slug>
   python check_retractions.py            # Crossref: marca `retracted` si algún paper fue retractado
   ```
   `query_ads --topic` escribe el mismo `build/<slug>/ads.json` (con `kind: topic`), así que
   `fetch_arxiv` y `extract_fulltext` corren sin cambios. Hace **citation chaining anclado a la query
   del tema** (references/citations de los core filtrados por la propia query → recall extra sin traer
   los mega-citados genéricos del área). `fetch_arxiv` respeta el rate limit de arXiv
   (1 req/3 s) → correr en background si son muchos PDFs. Papers sin arXiv (A&A viejos) quedan en
   `build/<slug>/missing_pdf.json` → bajar manual por DOI si son clave. Curación persistente con
   `extra_core: [<bibcode>, …]` en la entrada del tema en `topics.yaml` (igual que en estrellas).

3. **Extracción LLM (criterio).** Leer los papers **clave del tema** (fundacionales / árbitros /
   metodológicos) desde `vault/raw/fulltext/<slug>/` y poblar cada `vault/wiki/papers/<bibcode>.md`: `methods`,
   `bearing`, `thesis_links` (ya pre-sembrado al concept; agregar otros si toca) y la sección
   "Extracción" enfocada **en el eje del tema** (qué aporta al tópico: signo, lag, mecanismo, método),
   no en una estrella concreta.

3b. **Retro-tag del corpus pre-existente (grep por aliases).** Los papers que la query ADS devolvió
   pero **ya estaban** en el corpus quedan conectados solos (`make_notes` mergea add-only el seed
   `thesis_links` en la nota existente, sin pisar su extracción). Lo que la query **no** devolvió se
   caza por grep: buscar los `aliases` del tema sobre el fulltext de **todo** el corpus (los otros
   slugs), p. ej. `grep -rilE --include="*.txt" "fastica|icasso" vault/raw/fulltext/`, y para cada
   hit sin taguear leer el contexto y decidir si el paper **usa/aporta** al tema (no mención al
   pasar) → agregar add-only `thesis_links` (y `methods` si aplica) a su nota. La tabla Dataview del
   concept acumula sola; una ficha-método junta además por `methods:` sin re-taguear.

4. **Síntesis del concept durable** (`concepts/<area>/<concept>.md`). Destilar lo aprendido a la
   página viva: mecanismos, signos, desfasajes, regímenes, huecos. El roll-up Dataview (papers con
   `thesis_links: <concept>`) acumula solo. **Citar los papers clave por `[[bibcode]]`** en la prosa
   (además de trazabilidad, da links entrantes → no quedan huérfanos).

5. **Auto-revisión de autosuficiencia (semántica).** Releer el concept como un agente externo que
   **sólo tiene ese archivo**: ¿se entiende el tema sin abrir ningún paper? Si para responder algo hay
   que abrir un paper, falta en el concept → agregarlo. (No hay proxy estructural en `lint.py` para
   concepts — la suficiencia la juzgás vos, igual que en la ficha de estrella.)

6. **Bookkeeping.** Actualizar `vault/wiki/index.md` (agregar el concept si es nuevo), appendear a
   `vault/wiki/log.md`, y `vault/STATUS.md` si cambió el estado. **No** tocar la matriz método×estrella. Correr
   `python scripts/lint.py` y revisar (0 wikilinks rotos / huérfanos / `thesis_links` colgados).

6b. **Verificar citas.** Correr el skill `verify-citations` sobre el **concept** (y las notas de paper
   nuevas). El concept es dual-audiencia e implementation-ready: cada afirmación con `[[bibcode]]`
   —definiciones, ecuaciones, rangos, signos— debe estar respaldada por el fulltext (cita textual +
   nº de línea del `.txt`; sin respaldo ⇒ no-soportada). Resolver cada no-soportada/parcial (bajar a lo
   que dice la fuente, reasignar la cita, o marcar `inferencia`) y dejar el bloque `## Verificación de citas`.

7. **Cierre (commit + push).** Tras la verificación (lint en 0), `git add` de los archivos
   **específicos** que tocó la operación (no `-A`) y commitear con mensaje
   descriptivo. Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Modo off-ADS / tema no-astro (opt-in — **sólo a pedido explícito**)

Almagesto es astro **por estructura** (la plomería de adquisición —ADS, arXiv, NEA/SIMBAD— es de
astronomía); por eso un tema, por **default**, se baja por ADS (los **Pasos** de arriba). **Pero** si el
usuario pide **explícitamente** ingerir un tema **no-astro** o cuya bibliografía canónica vive **fuera de
ADS** (p. ej. un método matemático general: ICA/FastICA, signal processing, estadística), se permite en
este modo. **`ingest-star` no cambia: sigue siendo astro-only.**

Qué cambia respecto del flujo ADS de arriba:
- **Sin ADS:** se saltean `query_ads.py`, `fetch_arxiv.py` y `fetch_ground_truth.py`. En
  `vault/config/topics.yaml` la entrada lleva `query: null`, el switch **`source: web | local-pdfs |
  local-pdfs+web`** y la bibliografía **declarada** en la lista `sources:` (cada item: `key`
  AAAA+Autor + `url` o `pdf` + `title/author/year/venue/n_authors/doi` opcionales; ver header del YAML); el resto
  del schema igual (`title`, `area`, `concept`, `aliases`). Con eso, **el mismo comando del paso 2**
  (`python ingest_topic.py <slug>`) orquesta todo: stub del concept, `fetch_web.py` por cada `url`,
  copia de cada `pdf` a `vault/raw/pdfs/<slug>/<key>.pdf` (nota con el campo `pdf` ya linkeado) y
  `extract_fulltext.py`. `--force` re-baja/re-copia **fuentes**, nunca pisa notas. Los bullets de
  abajo documentan las piezas por si hay que correr algo a mano.
- **Fuente = PDFs locales y/o web:**
  - **PDFs** que provee el usuario → copiarlos a `vault/raw/pdfs/<slug>/` (git-lfs) renombrados a la **clave de
    cita** (abajo); `python extract_fulltext.py <slug>` los pasa a `vault/raw/fulltext/<slug>/` (es
    source-agnostic: sólo corre `pdftotext`).
  - **Web** (rellenar fundacionales / huecos) → **preferido:** `python fetch_web.py <slug> <clave> <url>
    [--concept <concept> --title … --author … --year …]`. Baja la página con **defuddle** (quita
    nav/menús/clutter → markdown limpio, ~8× menos bytes que el HTML crudo, ~4× menos que pandoc), le pasa
    un **post-clean** determinista (saca bloques HTML de media/embed sueltos) y escribe el **snapshot**
    `vault/raw/fulltext/<slug>/<clave>.txt` con el encabezado **URL + fecha de acceso** ya puesto (citable y
    verificable por `verify-citations`). **Además crea el stub `vault/wiki/papers/<clave>.md`** (salvo
    `--no-note`). Requiere Node/npm (`npx defuddle`, JS-only; valida `<clave>` contra `BIBCODE_RE`,
    idempotente salvo `--force`). **Sin Node:** traer con `WebFetch`/`deep-research`, guardar el snapshot a
    mano (mismo encabezado) y stubbear la nota con `python make_notes.py --web <clave> --url … --concept …`.
- **Fuente no-conseguible (fallback — paywall / escaneo / mojibake):** si una fuente no se puede
  obtener (sin copia libre) o su PDF no rinde texto usable (escaneo sin capa de texto, fuentes sin
  ToUnicode → `extract_fulltext` avisa "ILEGIBLE"), **no frenar el ingest ni dejarla muda**: marcá el
  item de `sources:` con `pending: paywall|scan|unextractable` (dejando `url`/`doi` conocidos como
  puntero). La cadena stubbea la nota con `pending_source`, la **deriva al usuario** en el aviso
  final y el lint la lista como precondición. El resto del tema se arma igual con las fuentes
  limpias; la pendiente queda como hueco citado. Cuando el usuario provea el PDF/fuente: reemplazar
  `pending` por `pdf:`/`url:`, re-correr la cadena (idempotente) y completar la extracción.
- **Clave de cita sintética (papers sin bibcode ADS):** `AAAA+Autor` (p. ej. `2000HyvarinenOja`,
  `2006Tichavsky`, `2025sklearn`). Debe **empezar con `AAAA`+letra** (lo exige `BIBCODE_RE` del lint) y
  coincidir con el nombre del `.txt`. Donde **sí** exista un bibcode ADS real, usarlo.
- **Notas de paper (automatizado):** `fetch_web.py` ya crea el stub `vault/wiki/papers/<clave>.md`; para
  fuentes **PDF** off-ADS (sin URL) usá `python make_notes.py --web <clave> --concept <concept>
  --slug-hint <slug> [--title … --author … --year … --n-authors … --doi … --venue …]`. El stub lleva el
  **mismo frontmatter** que
  una nota ADS más la provenance web: `bibcode` = clave sintética; `arxiv_id` null; `n_authors`/`doi` los
  del item de `sources:` si se declararon (un PDF con DOI sigue siendo off-ADS; con `doi`,
  `ingest_topic.py` corre además `check_retractions.py`); `source_url` +
  `accessed` (la **fecha del snapshot** — el "Retrieved <fecha>" de una cita web, la toma del `.txt`);
  `bibstem` = venue o dominio; `pdf: null` (el respaldo es el snapshot `.txt`); `stars: []`; `thesis_links`
  al concept; `tags: [paper, web]` (snapshot de URL) o `[paper, local-pdf]` (PDF provisto).
  Completar la extracción LLM a mano.
- **Todo lo demás igual:** extracción enfocada en el eje del tema, síntesis al concept durable,
  auto-revisión de autosuficiencia, **`verify-citations`** (la clave sintética y el snapshot `.txt` la
  hacen chequeable), **`lint`** (0 bloqueante) y bookkeeping. **La frontera dura (regla #0) sigue
  rigiendo:** sólo bibliografía citable; nada de implementación de quien consume la bóveda.

## Notas
- Reglas de notación/reporte y schemas de frontmatter: ver `CLAUDE.md`. Notación matemática en `$...$`,
  filenames kebab-case (papers usan el bibcode), links internos `[[wikilink]]`.
- Distinción concept vs query: el concept es el resultado **durable** del tema (acumula solo). Una
  *query* archivada (`queries/`) es un snapshot complementario — opcional, sólo si vale re-preguntarla.
- **Lectura del fulltext (saltar afiliaciones):** los `.txt` arrancan con autores/afiliaciones que no
  aportan. Saltar al contenido con, p. ej., `awk 'tolower($0)~/abstract/{f=1} f' vault/raw/fulltext/<slug>/<bib>.txt | head -60`
  y `grep -inE "bisector|BIS|FWHM|S-?index|chromatic|correlat|lag" ...` para los números clave. No
  tocar el `.txt` en disco (se usa para grep); el salto es sólo en la lectura.
