---
name: ingest-star
description: Usar cuando el usuario pide bajar/agregar/ingestar una estrella a la bóveda ("bajá GJ 581", "ingest tau ceti", "agregá la estrella X", "traé la bibliografía de AU Mic"). Corre la cadena de ingesta y hace la extracción LLM.
version: 1.3.0
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
   python check_retractions.py            # Crossref: marca `retracted` si algún paper fue retractado
   ```
   `fetch_arxiv` respeta el rate limit de arXiv (1 req/3 s) → puede tardar; correr en background si
   son muchos PDFs. Papers sin arXiv quedan en `build/<slug>/missing_pdf.json`.
   La cadena es idempotente (no pisa): en un re-ingest, `fetch_ground_truth` **no** refresca un
   ground-truth existente salvo `--force` (refrescar desde NEA es decisión explícita, no side-effect).
   `check_retractions` consulta **Crossref** por DOI y, si un paper fue **retractado**, estampa
   `retracted: true` en su nota (el lint lo vuelve bloqueante) → revisá cada afirmación que lo cita.
   `query_ads` hace además **citation chaining**: pide a ADS references/citations de los core,
   **ancladas al sujeto** con `full:` sobre nombre+alias — trae surveys/catálogos conectados por el
   grafo de citas aunque no nombren la estrella en el abstract (quedan marcados `via: chain:*` en
   `ads.json`; se desactiva con `--no-chain`).

2b. **Barrido full-text (NO perder surveys de muestra grande).** La query directa de `query_ads.py`
   busca en **título+abstract** → punto ciego sistemático: los **surveys de muestra grande**
   (Mount Wilson HK, catálogos de actividad) **tabulan la estrella sin nombrarla en el abstract**. El
   **chaining del paso 2 ya trae** los que están conectados por citas a los core encontrados; este
   barrido caza los que quedan **fuera del grafo** (o cuyos core-vecinos no entraron). Correr:
   ```bash
   # query Solr cruda: papers con la estrella en el CUERPO (no sólo título/abstract)
   python query_ads.py --probe 'full:"HD 152391"'      # repetir por alias
   python query_ads.py --probe 'full:"HD152391"'       # …y por la grafía SIN espacio
   ```
   **Probá ambas grafías** (`HD 152391` y `HD152391`): ADS tokeniza distinto cada forma y los papers usan
   las dos → una sola se pierde la otra. (El ingest automático ya expande las variantes de espaciado en
   `build_query`; este barrido `full:` es manual, así que acá lo hacés a mano.)
   Clasificá el resultado con `relevance.topics` (igual que el ingest) y **revisá TODO el core, no sólo el
   top-N por citas**: los papers recientes/poco citados caen al fondo del ranking aunque sean core (así se
   perdieron Garg+2019 y Willamo+2020, con 21c/9c). Los core que falten se agregan a mano (inyectar el
   registro en `build/<slug>/ads.json` y correr `make_notes`, como con los curados). Si el barrido devuelve
   muchos, **listá cuántos quedan sin bajar** en el `log` — no cures en silencio.

3. **Extracción LLM (criterio).** Leer los papers **clave** (discovery / actividad / métodos) desde
   `vault/raw/fulltext/<slug>/` y poblar:
   - en `vault/wiki/papers/<bibcode>.md`: `methods`, `thesis_links`, `bearing`, y la sección "Extracción"
     (P/K por planeta, indicadores, relevancia para la tesis).
   - en `vault/wiki/stars/<slug>.md`: completar frontmatter (`P_rot_days`,
     `activity_indicators_expected`, caveats por planeta) y escribir la **síntesis** (qué se sabe,
     qué indicador debería trazar actividad para ese tipo espectral, huecos).
   - **Contrastar contra `vault/raw/ground_truth/<slug>.json`**: si un paper discrepa del archivo
     (p. ej. planeta dudoso), taguearlo en `planets[].disputes[]` de la ficha (`field`/`ref`/`note`/`alt`;
     ver *Disputas* en `CLAUDE.md`) y `bearing: challenges` en la nota del paper — no celebrar.

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
   **específicos** que tocó la operación (no `-A`) y commitear con mensaje
   descriptivo. Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Notas
- Reglas de notación/reporte y schemas de frontmatter: ver `CLAUDE.md`.
- No copiar FITS a la bóveda: la ficha apunta a los datos vía `data_local`.
- **Lectura del fulltext (saltar afiliaciones):** los `.txt` arrancan con autores/afiliaciones que no
  aportan a la extracción. NO leer las primeras páginas enteras: saltar al contenido con, p. ej.,
  `awk 'tolower($0)~/abstract/{f=1} f' vault/raw/fulltext/<slug>/<bib>.txt | head -60` para el abstract, y
  `grep -inE "P_?rot|K ?=|mass|chromatic|GP|activity indicator" ...` para los números clave. No tocar
  el `.txt` en disco (se usa para grep); el salto es sólo en la lectura.
- **Mirá las TABLAS, no sólo el texto.** En papers viejos las tablas suelen ser **imágenes** (en el
  escaneo de ADS y a veces hasta en el HTML del publisher). El dato de la estrella (P_cyc, P_rot, rama…)
  vive ahí → **invisible a cualquier búsqueda de texto**. Para confirmar si una estrella está en un paper
  y para extraer sus valores, **abrí la tabla** (imagen o PDF), no te fíes del grep.
- **Un `full:"HD X" → 0` NO prueba ausencia** en papers pre-digitales: el **OCR del escaneo de ADS pierde
  ~½ de las filas** (medido: 12/26 estrellas en Saar & Brandenburg 1999; faltaba hasta HD 81809). Nunca
  afirmar "la estrella no está en ese paper" desde un hit full-text negativo — **corroborar** (papers que
  lo citan y le atribuyen datos) o **abrir el PDF/tabla**. Reportar honesto: es inconcluso, no ausencia.
- **Cascada de adquisición de PDFs no-arXiv** (antes de rendirse; ver también backlog en `vault/STATUS.md`):
  (a) escaneo ADS `articles.adsabs.harvard.edu/pdf/<bibcode>`; (b) **imágenes de tabla del CDN del
  publisher** (p. ej. IOP `content.cld.iop.org/journals/.../tbN.gif`) — **funcionan aunque el PDF esté tras
  paywall**, y suelen tener el dato que se busca; (c) HTML legacy del publisher (frameset `…/fulltext/`);
  (d) si nada funciona, **pedir el PDF al usuario** (tiene acceso institucional; anduvo con Frick 2004 y
  Saar 1999). Guardá el artefacto citable (PDF o imagen de tabla) en `vault/raw/`.
- **No asumir OCR.** Chequeá primero si el PDF trae **capa de texto** (`pdftotext` da texto real, no vacío);
  sólo los **escaneos-imagen** puros (p. ej. Baliunas 1995) necesitan OCR. Ojo con quirks de PostScript
  viejo en la extracción (p. ej. el signo `-` y `>` pueden salir ambos como `[`): los datos están, sólo hay
  que desambiguar por contexto.
