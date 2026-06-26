---
name: ingest-topic
description: Usar cuando el usuario pide investigar/ingestar un TEMA en profundidad a la bóveda, como si fuera una estrella pero por tópico ("traé todo sobre actividad y RV", "investigá a fondo el bisector vs actividad", "ingestá el tema de los GP en RV", "armá un concept con la bibliografía de indicadores de actividad"). Dispara una búsqueda ADS por keywords y hace la extracción LLM hacia un concept durable.
version: 1.0.0
---

# Ingest: agregar un TEMA a la wiki

Operación **ingest** del patrón LLM Wiki (ver `CLAUDE.md`), hermana de `ingest-star` pero por **tema**
en vez de por estrella. División idéntica: los scripts bajan, el LLM procesa. Trabajar desde la raíz
del repo.

**Diferencias con `ingest-star`** (mismo dominio RV, distinto sujeto):
- La búsqueda ADS es **por keywords** (query Solr cruda), no por nombre vía SIMBAD.
- El producto durable es un **concept** (`concepts/<area>/<concept>.md`), no una ficha de estrella.
- **No hay ground-truth** (no existe NEA/SIMBAD para un tema) → se **saltea `fetch_ground_truth.py`**.
- **No** se toca la matriz método×estrella.
- Las notas de paper llevan `stars: []` y `thesis_links` pre-sembrado al concept.

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
   - **d. Persistir.** Recién entonces escribir/actualizar la entrada en `config/topics.yaml`:
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
   metodológicos) desde `raw/fulltext/<slug>/` y poblar cada `wiki/papers/<bibcode>.md`: `methods`,
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

6. **Bookkeeping.** Actualizar `wiki/index.md` (agregar el concept si es nuevo), appendear a
   `wiki/log.md`, y `STATUS.md` si cambió el estado. **No** tocar la matriz método×estrella. Correr
   `python scripts/lint.py` y revisar (0 wikilinks rotos / huérfanos / `thesis_links` colgados).

6b. **Verificar citas.** Correr el skill `verify-citations` sobre el **concept** (y las notas de paper
   nuevas). El concept es dual-audiencia e implementation-ready: cada afirmación con `[[bibcode]]`
   —definiciones, ecuaciones, rangos, signos— debe estar respaldada por el fulltext (cita textual +
   nº de línea del `.txt`; sin respaldo ⇒ no-soportada). Resolver cada no-soportada/parcial (bajar a lo
   que dice la fuente, reasignar la cita, o marcar `inferencia`) y dejar el bloque `## Verificación de citas`.

7. **Cierre (commit + push).** Tras la verificación (lint en 0), `git add` de los archivos
   **específicos** que tocó la operación (no `-A`; ver `CLAUDE.md` global) y commitear con mensaje
   descriptivo. Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Notas
- Reglas de notación/reporte y schemas de frontmatter: ver `CLAUDE.md`. Notación matemática en `$...$`,
  filenames kebab-case (papers usan el bibcode), links internos `[[wikilink]]`.
- Distinción concept vs query: el concept es el resultado **durable** del tema (acumula solo). Una
  *query* archivada (`queries/`) es un snapshot complementario — opcional, sólo si vale re-preguntarla.
- **Lectura del fulltext (saltar afiliaciones):** los `.txt` arrancan con autores/afiliaciones que no
  aportan. Saltar al contenido con, p. ej., `awk 'tolower($0)~/abstract/{f=1} f' raw/fulltext/<slug>/<bib>.txt | head -60`
  y `grep -inE "bisector|BIS|FWHM|S-?index|chromatic|correlat|lag" ...` para los números clave. No
  tocar el `.txt` en disco (se usa para grep); el salto es sólo en la lectura.
