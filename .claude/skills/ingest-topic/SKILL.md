---
name: ingest-topic
description: Usar cuando el usuario pide investigar/ingestar un TEMA en profundidad a la bóveda, como si fuera una estrella pero por tópico ("traé todo sobre actividad y RV", "investigá a fondo el bisector vs actividad", "ingestá el tema de los GP en RV", "armá un concept con la bibliografía de indicadores de actividad"). Dispara una búsqueda ADS por keywords y hace la extracción LLM hacia un concept durable. Soporta además, sólo a pedido explícito, un tema no-astro / fuera de ADS (desde PDFs locales + web; ver Modo off-ADS).
version: 1.0.0
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
   - **c. Validar con un conteo barato** antes de bajar nada: `python query_ads.py --topic <slug>
     --rows 50` y mirar `n_relevant` + los títulos top (ordenados por citas). Si trae cientos con
     ruido o muy pocos, reajustar la query y reconfirmar. **No** bajar PDFs hasta que el usuario
     apruebe la query final.
   - **d. Persistir.** Recién entonces escribir/actualizar la entrada en `vault/config/topics.yaml`:
     `title`, `area` (`indicators|methods|activity|hypotheses`), `concept` (nota destino, existente o
     a stubbear), `query` (la Solr cruda aprobada) y `aliases` opcional. Si el tema ya existía en el
     YAML, ofrecer reusar la query guardada o re-pulirla.

2. **Cadena mecánica** (correr desde `scripts/`, en orden; **sin `fetch_ground_truth`**):
   ```bash
   python query_ads.py   --topic <slug>
   python fetch_arxiv.py         <slug>
   python make_notes.py  --topic <slug>
   python extract_fulltext.py    <slug>
   ```
   `query_ads --topic` escribe el mismo `build/<slug>/ads.json` (con `kind: topic`), así que
   `fetch_arxiv` y `extract_fulltext` corren sin cambios. `fetch_arxiv` respeta el rate limit de arXiv
   (1 req/3 s) → correr en background si son muchos PDFs. Papers sin arXiv (A&A viejos) quedan en
   `build/<slug>/missing_pdf.json` → bajar manual por DOI si son clave.

3. **Extracción LLM (criterio).** Leer los papers **clave del tema** (fundacionales / árbitros /
   metodológicos) desde `vault/raw/fulltext/<slug>/` y poblar cada `vault/wiki/papers/<bibcode>.md`: `methods`,
   `bearing`, `thesis_links` (ya pre-sembrado al concept; agregar otros si toca) y la sección
   "Extracción" enfocada **en el eje del tema** (qué aporta al tópico: signo, lag, mecanismo, método),
   no en una estrella concreta.

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
   **específicos** que tocó la operación (no `-A`; ver `CLAUDE.md` global) y commitear con mensaje
   descriptivo. Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Modo off-ADS / tema no-astro (opt-in — **sólo a pedido explícito**)

Almagesto es astro **por estructura** (la plomería de adquisición —ADS, arXiv, NEA/SIMBAD— es de
astronomía); por eso un tema, por **default**, se baja por ADS (los **Pasos** de arriba). **Pero** si el
usuario pide **explícitamente** ingerir un tema **no-astro** o cuya bibliografía canónica vive **fuera de
ADS** (p. ej. un método matemático general: ICA/FastICA, signal processing, estadística), se permite en
este modo. **`ingest-star` no cambia: sigue siendo astro-only.**

Qué cambia respecto del flujo ADS de arriba:
- **Sin ADS:** se saltean `query_ads.py`, `fetch_arxiv.py` y `fetch_ground_truth.py`. En
  `vault/config/topics.yaml` la entrada lleva `query: null` y un campo `source: local-pdfs+web` (marcador); el
  resto del schema del tema igual (`title`, `area`, `concept`, `aliases`).
- **Fuente = PDFs locales y/o web:**
  - **PDFs** que provee el usuario → copiarlos a `vault/raw/pdfs/<slug>/` (git-lfs) renombrados a la **clave de
    cita** (abajo); `python extract_fulltext.py <slug>` los pasa a `vault/raw/fulltext/<slug>/` (es
    source-agnostic: sólo corre `pdftotext`).
  - **Web** (rellenar fundacionales / huecos) → traer con `WebFetch`/`deep-research` y **guardar un
    snapshot determinista** como `vault/raw/fulltext/<slug>/<clave>.txt`, con **URL + fecha de acceso** al
    inicio del archivo, para que la afirmación sea **citable y verificable** por `verify-citations`.
- **Clave de cita sintética (papers sin bibcode ADS):** `AAAA+Autor` (p. ej. `2000HyvarinenOja`,
  `2006Tichavsky`, `2025sklearn`). Debe **empezar con `AAAA`+letra** (lo exige `BIBCODE_RE` del lint) y
  coincidir con el nombre del `.txt`. Donde **sí** exista un bibcode ADS real, usarlo.
- **Notas de paper a mano:** `make_notes.py` asume ADS → en este modo se crean a mano
  `vault/wiki/papers/<clave>.md` con el mismo frontmatter (`bibcode` = clave sintética; `arxiv_id`/`doi` si
  hay; `bibstem` = venue; `stars: []`; `thesis_links` al concept).
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
