---
name: ingest-star
description: Usar cuando el usuario pide bajar/agregar/ingestar una estrella a la bóveda ("bajá GJ 581", "ingest tau ceti", "agregá la estrella X", "traé la bibliografía de AU Mic"). Corre la cadena de ingesta y hace la extracción LLM.
version: 1.0.0
---

# Ingest: agregar una estrella a la wiki

Operación **ingest** del patrón LLM Wiki (ver `CLAUDE.md`). División: los scripts bajan, el LLM
procesa. Trabajar desde la raíz del repo.

## Pasos

1. **Resolver el slug.** Buscar la estrella en `vault/config/stars.yaml`. Si no está, agregarla con
   `slug`, `simbad`, `ads_object`, `aliases` y (si aplica) `data_local`. Verificar el nombre en
   SIMBAD si hay duda.

2. **Cadena mecánica** (correr desde `scripts/`, en orden):
   ```bash
   python query_ads.py        <slug>
   python fetch_arxiv.py      <slug>
   python fetch_ground_truth.py <slug>
   python make_notes.py       <slug>
   python extract_fulltext.py <slug>
   ```
   `fetch_arxiv` respeta el rate limit de arXiv (1 req/3 s) → puede tardar; correr en background si
   son muchos PDFs. Papers sin arXiv quedan en `build/<slug>/missing_pdf.json`.

3. **Extracción LLM (criterio).** Leer los papers **clave** (discovery / actividad / métodos) desde
   `vault/raw/fulltext/<slug>/` y poblar:
   - en `vault/wiki/papers/<bibcode>.md`: `methods`, `thesis_links`, `bearing`, y la sección "Extracción"
     (P/K por planeta, indicadores, relevancia para la tesis).
   - en `vault/wiki/stars/<slug>.md`: completar frontmatter (`P_rot_days`,
     `activity_indicators_expected`, caveats por planeta) y escribir la **síntesis** (qué se sabe,
     qué indicador debería trazar actividad para ese tipo espectral, huecos).
   - **Contrastar contra `vault/raw/ground_truth/<slug>.json`**: si un paper discrepa del archivo
     (p. ej. planeta dudoso), marcarlo con `lit_caveat`/`bearing: challenges`, no celebrar.

4. **Auto-revisión de autosuficiencia (semántica).** Releer la ficha **como un agente externo que
   sólo tiene ese archivo**: ¿se entiende la estrella sin abrir ningún paper? Checklist: parámetros
   estelares clave, inventario de señales RV (tabla $P/K/e/m\sin i$ + estado), señales
   disputadas/descartadas, indicadores de actividad esperados, métodos aplicados y huecos. Si para
   responder algo hay que abrir un paper, falta en la ficha → agregarlo. (`lint.py` chequea el proxy
   estructural — cada planeta del frontmatter discutido en prosa — pero la suficiencia la juzgás vos.)

5. **Bookkeeping.** Actualizar `vault/wiki/index.md` (agregar la estrella), appendear a `vault/wiki/log.md`,
   tocar `vault/wiki/matrices/method_star.md` (qué métodos se aplicaron en la literatura) y `vault/STATUS.md`
   si cambió el estado. Correr `python scripts/lint.py` y revisar.

5b. **Verificar citas.** Correr el skill `verify-citations` sobre la **ficha de la estrella** (y sobre
   las notas de paper nuevas con extracción). La ficha es el artefacto **más reusado** (se arma un
   informe desde ahí), así que su prosa con `[[bibcode]]` —parámetros estelares, señales RV, disputas—
   debe estar respaldada por el fulltext (cita textual + nº de línea del `.txt`; sin respaldo ⇒
   no-soportada). Prioridad: las afirmaciones que **cambian cómo se lee una señal RV** y las
   `planets[].disputes` (alt/note vs el paper). Resolver cada no-soportada/parcial (corregir el valor,
   reasignar la cita, o marcar `inferencia`) y dejar el bloque `## Verificación de citas`.

6. **Cierre (commit + push).** Tras la verificación (lint en 0), `git add` de los archivos
   **específicos** que tocó la operación (no `-A`; ver `CLAUDE.md` global) y commitear con mensaje
   descriptivo. Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Notas
- Reglas de notación/reporte y schemas de frontmatter: ver `CLAUDE.md`.
- No copiar FITS a la bóveda: la ficha apunta a los datos vía `data_local`.
- **Lectura del fulltext (saltar afiliaciones):** los `.txt` arrancan con autores/afiliaciones que no
  aportan a la extracción. NO leer las primeras páginas enteras: saltar al contenido con, p. ej.,
  `awk 'tolower($0)~/abstract/{f=1} f' vault/raw/fulltext/<slug>/<bib>.txt | head -60` para el abstract, y
  `grep -inE "P_?rot|K ?=|mass|chromatic|GP|activity indicator" ...` para los números clave. No tocar
  el `.txt` en disco (se usa para grep); el salto es sólo en la lectura.
