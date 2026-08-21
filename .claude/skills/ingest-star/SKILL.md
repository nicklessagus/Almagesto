---
name: ingest-star
description: Usar cuando el usuario pide bajar/agregar/ingestar una estrella a la bóveda ("bajá GJ 581", "ingest tau ceti", "agregá la estrella X", "traé la bibliografía de AU Mic"). Corre la cadena de ingesta y hace la extracción LLM.
version: 1.11.2
---

# Ingest: agregar una estrella a la wiki

Operación **ingest** del patrón LLM Wiki (ver `CLAUDE.md`). División: los scripts bajan, el LLM
procesa. Trabajar desde la raíz del repo.

## Pasos

**Copiá este checklist al chat al arrancar y andá tildándolo** — tres pasos (2b, 2c, 5b) son
fáciles de saltear y **ninguno deja rastro si se omite**; el lint sólo tiene red para el último:

```
Progreso del ingest de <estrella>:
- [ ] 1  slug resuelto en stars.yaml
- [ ] 2  cadena mecánica (orquestador) — sin abortos
- [ ] 2b barrido full-text (--sweep) revisado
- [ ] 2c triage de candidatos resuelto (aceptado / --drop con motivo / al usuario)
- [ ] 3  extracción LLM de los papers clave
- [ ] 4  auto-revisión de autosuficiencia
- [ ] 5  bookkeeping (index, log, matriz, STATUS)
- [ ] 5b verify-citations sobre la ficha + notas nuevas
- [ ] 6  lint en 0 → commit → preguntar push
```

1. **Resolver el slug.** Buscar la estrella en `vault/config/stars.yaml`. Si no está, agregarla con
   `slug`, `simbad`, `ads_object`, `aliases` y (si aplica) `data_local`. Verificar el nombre en
   SIMBAD si hay duda.

2. **Cadena mecánica** (orquestador — desde la raíz del repo):
   ```bash
   python scripts/ingest_star.py <slug>
   ```
   Corre la cadena completa (ADS → PDFs arXiv y no-arXiv → ground-truth NEA/SIMBAD → stubs →
   fulltext → retracciones), abortando al primer fallo. **El orden canónico vive en el header de
   `scripts/ingest_star.py`** — puntero, no copia: no lo repliques acá ni en otros docs. Para un
   flag fino (`--rows`, `--all`, `--force` de un paso) corré el script puntual.
   `fetch_arxiv` respeta el rate limit de arXiv (1 req/3 s) → puede tardar; correr en background si
   son muchos PDFs. Los papers sin arXiv —y los con arXiv cuya bajada falló— los intenta
   `fetch_pdf` (escaneo ADS con token → PDF del publisher, con fallback `curl`); lo que ni así
   sale queda en `build/<slug>/missing_pdf.json` (residuo completo del ingest, verdad de disco) —
   cada entrada trae su `bibstem` y un `hint` con la rama por donde seguir: la **cascada manual de
   rescate** está en `## Notas` de este skill (Messenger / página del instrumento / mirrors / tablas
   del CDN / derivar al usuario), y "bajar manual por DOI" **no alcanza**.
   La cadena es idempotente (no pisa): en un re-ingest, `fetch_ground_truth` **no** refresca un
   ground-truth existente salvo `--force` (refrescar desde NEA es decisión explícita, no side-effect).
   `check_retractions` consulta **Crossref** por DOI y, si un paper fue **retractado**, estampa
   `retracted: true` en su nota (el lint lo vuelve bloqueante) → revisá cada afirmación que lo cita.
   En la cadena corre con `--slug` (sólo los papers de **este** ingest); el barrido completo de la
   bóveda es la pasada periódica del skill `maintain`.
   `query_ads` hace además **citation chaining**: pide a ADS references/citations de los core,
   **ancladas al sujeto** con `full:` sobre nombre+alias — trae surveys/catálogos conectados por el
   grafo de citas aunque no nombren la estrella en el abstract (quedan marcados `via: chain:*` en
   `ads.json`; se desactiva con `--no-chain`).
   **Guardia de expansión (checkpoint humano).** Entre `query_ads` y el primer paso que gasta red
   y disco, el orquestador compara el core del `ads.json` fresco contra las notas ya ingestadas del
   sujeto: si se multiplicó (default ×1.5 y >50 nuevos) **frena** con el conteo, cuántos vinieron
   por el grafo de citas y el puntero a `relevance.require`/`min_topics`. Antes de refrescar un
   sujeto viejo, mirá ese número: si el pool explotó, revisá la **regla de combinación** en
   `objective.yaml` (skill `setup`) antes de bajar nada — podar las regex no alcanza si la
   combinación sigue siendo OR. `--yes` continúa a sabiendas.
   Si el nombre es **Bayer** (letra griega + constelación) corre antes el **rescate por glifo**
   (`via: glyph`, se desactiva con `--no-glyph`): ADS unifica `epsilon`/`eps`/`ε` pero **descarta**
   los lookalikes `ϵ` (U+03F5) y `∊` (U+220A, el glifo de ApJ/AJ/MNRAS), así que esos papers quedan
   indexados sólo por la constelación e **invisibles** a la query canónica (medido en ε Eri: 121
   core perdidos, incluido el descubrimiento). No hace falta listar las grafías en `aliases`: el
   carácter se descarta, no falta la variante — el rescate trae el superset de la constelación y
   filtra client-side por el glifo.

2b. **Barrido full-text (NO perder surveys de muestra grande).** La query directa de `query_ads.py`
   busca en **título+abstract** → punto ciego sistemático: los **surveys de muestra grande**
   (Mount Wilson HK, catálogos de actividad) **tabulan la estrella sin nombrarla en el abstract**. El
   **chaining del paso 2 ya trae** los que están conectados por citas a los core encontrados; este
   barrido caza los que quedan **fuera del grafo** (o cuyos core-vecinos no entraron). Correr:
   ```bash
   python scripts/query_ads.py <slug> --sweep
   ```
   Corre `full:` sobre nombre+aliases expandiendo solo **todas las grafías** (`HD 152391` ↔
   `HD152391` — ADS tokeniza distinto y los papers usan ambas; antes esto eran probes manuales por
   grafía, fáciles de olvidar) y lista **sólo los core que el ingest NO trajo** — la lista corta de
   candidatos (así se recuperan casos tipo Garg+2019 / Willamo+2020, core poco citados que caen al
   fondo del ranking). Revisarla y agregar los que correspondan **de forma persistente** con
   `extra_core: [<bibcode>, …]` en la entrada de la estrella en `vault/config/stars.yaml` (el
   `query_ads` los trae por bibcode, `via: manual`, y sobreviven al re-run — a diferencia de editar
   `build/`, que es scratch y se pisa); después re-correr la cadena (idempotente). Si el barrido
   devuelve muchos y no bajás todos, **listá cuántos quedan sin bajar** en el `log` — no cures en
   silencio. (Un resultado vacío **no prueba ausencia** en papers pre-digitales — ver Notas: el OCR
   del escaneo pierde filas de tabla.)

2c. **Compuerta de triage del chaining (juicio, antes de bajar nada).** El chaining trae papers
   conectados por citas que **mencionan** al sujeto sin hablar de él: la lente clasifica **tema**, no
   **pertinencia al sujeto** (medido: de 378 core nuevos, 368 del grafo y sólo 18% pertinentes —
   incluyendo una tesis de física de partículas como "core" de AU Mic). Y no se aproxima con una
   regla sintáctica: la densidad de mención sale **invertida** (los ruidosos nombran al sujeto 27
   veces de mediana; los valiosos, 2). Por eso el juicio es tuyo. `query_ads` ya auto-aceptó los que
   llevan **el sujeto en el título** (1 falso positivo en 310) y dejó el resto como **candidatos**
   —no bajados—:
   ```bash
   python scripts/triage.py <slug>            # listar (agregá --report para la tabla en outputs/)
   ```
   Los marcados `◆` **ya tienen nota en la bóveda** (entraron por otro slug): ya están bajados y
   extraídos — la decisión sigue siendo por-slug (¿pertinente a ESTE sujeto?), pero se despachan
   rápido (el `stars:` que falte lo cubre el retro-linkeo add-only de `make_notes`).
   Clasificá cada candidato **sólo por título+abstract** (no bajes nada para decidir):
   - **pertinente** → agregalo a `extra_core: [<bibcode>, …]` en `vault/config/stars.yaml` y re-corré
     la cadena (idempotente: baja sólo los nuevos; `extra_core` es override del clasificador).
   - **ruido** → `python scripts/triage.py <slug> --drop <bib> … --reason "<motivo>"` (persiste en
     `build/<slug>/triage.json`: el próximo refresh no lo re-propone). Agrupá por categoría y
     descartá por lote, con el motivo real.
   - **dudoso** → **al usuario**, junto con (a) los papers que salen del core y ya tienen extracción
     LLM y (b) el resumen de volumen (core nuevo vs notas actuales). `--report` deja la tabla en
     `outputs/triage-<slug>.md` para decidir por lote.
   No curar en silencio: lo descartado queda con motivo, y lo que quede sin decidir se anota en el `log`.
   **El lint ahora tiene red (#55):** lo que quede en `candidates` sale como backlog *Triage
   pendiente* — antes el aviso vivía sólo en este stdout y el ingest podía cerrarse "en 0" con
   cientos sin juzgar. Ojo: `build/` es scratch **gitignored**, así que esa red sólo existe en la
   máquina que corrió la cadena; dejar el conteo en el `log` sigue siendo lo único que viaja.

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
  el `.txt` en disco (se usa para grep); el salto es sólo en la lectura. **Patrones cortos, siempre**
  (#44, convención canónica en `verify-citations`): el `.txt` entrelaza las dos columnas en la misma
  línea física (73% del corpus), así que un patrón largo da falso negativo — y acá el falso negativo
  se lee como "el paper no reporta ese parámetro", que es exactamente lo que la extracción decide.
- **Mirá las TABLAS, no sólo el texto.** En papers viejos las tablas suelen ser **imágenes** (en el
  escaneo de ADS y a veces hasta en el HTML del publisher). El dato de la estrella (P_cyc, P_rot, rama…)
  vive ahí → **invisible a cualquier búsqueda de texto**. Para confirmar si una estrella está en un paper
  y para extraer sus valores, **abrí la tabla** (imagen o PDF), no te fíes del grep.
- **Un `full:"HD X" → 0` NO prueba ausencia** en papers pre-digitales: el **OCR del escaneo de ADS pierde
  ~½ de las filas** (medido: 12/26 estrellas en Saar & Brandenburg 1999; faltaba hasta HD 81809). Nunca
  afirmar "la estrella no está en ese paper" desde un hit full-text negativo — **corroborar** (papers que
  lo citan y le atribuyen datos) o **abrir el PDF/tabla**. Reportar honesto: es inconcluso, no ausencia.
- **Cascada de adquisición de PDFs no-arXiv (canónica — `ingest-topic` y `append-knowledge` apuntan
  acá; ver también backlog en `vault/STATUS.md`).** Lo que quedó en `build/<slug>/missing_pdf.json`
  **ya falló** en `fetch_pdf.py` (resolver ADS: `EPRINT_PDF` → `ADS_PDF` con token → `PUB_PDF`, con
  fallback `curl`), y "bajar manual por DOI" **no alcanza** (medido en un ingest real: el resolver
  falló en **5 de 17** — pre-arXiv de 2000–2015: SPIE, The Messenger, A&A viejo; **4 de 5 se
  recuperaron** por estas ramas). `fetch_pdf` imprime el **bibstem** de cada fallo con la rama
  sugerida y la deja en el `hint` de cada entrada del residuo. En orden de rendimiento:
  1. **Archivo de The Messenger** (`Msngr`) — **todo el Messenger es abierto**:
     `eso.org/sci/publications/messenger/archive/no.<N>-<mes><aa>/messenger-no<N>-<pp>-<pp>.pdf`.
  2. **Página de papers del instrumento** (`SPIE` y proceedings en general) — p. ej.
     `eso.org/sci/facilities/lasilla/instruments/<inst>/science/papers/<vol>-<pp>.pdf`: tiene **en
     abierto** SPIE que de otro modo son paywall.
  3. **Mirrors académicos** por búsqueda web (páginas personales, repositorios institucionales).
  4. **Imágenes de tabla del CDN del publisher** (p. ej. IOP
     `content.cld.iop.org/journals/.../tbN.gif`) — **funcionan aunque el PDF esté tras paywall** y
     suelen tener el dato que se busca; ídem el HTML legacy del publisher (frameset `…/fulltext/`).
  5. **Pedir el PDF al usuario** (tiene acceso institucional; anduvo con Frick 2004 y Saar 1999) —
     mientras tanto, estampá `pending_source: paywall` en el frontmatter de la nota del paper (el
     lint la lista como precondición hasta que la fuente llegue).
  Guardá el artefacto citable (PDF o imagen de tabla) en `vault/raw/`.
  ⛔ **No gastar intentos en `aanda.org`:** está detrás de **DataDome** — cualquier `curl` (con UA de
  navegador, con `Referer`, siguiendo redirects) recibe un challenge JS (`Please enable JS…`,
  `ct.captcha-delivery.com`). Para un **A&A pre-arXiv** que el resolver no entrega no hay preprint y
  Semantic Scholar lo da `openAccessPdf: CLOSED` → **derivar al usuario de una** (se resuelve en una
  vuelta con acceso institucional).
- **OCR: lo maneja solo `extract_fulltext.py`.** Chequea si el PDF trae **capa de texto** legible
  (umbral determinista: chars no-espacio, **densidad por página** y fracción de ASCII imprimible) y,
  si no (escaneos-imagen puros, p. ej. Baliunas 1995, o fuentes sin
  ToUnicode), **cae solo a OCR** cuando hay `tesseract` instalado — el `.txt` queda con header
  `source: ocr`, **citable con salvedad** (ver docs/operacion.md); sin tesseract AVISA y el lint lo lista. Ojo
  con quirks de PostScript viejo en la extracción (p. ej. el signo `-` y `>` pueden salir ambos como
  `[`): los datos están, sólo hay que desambiguar por contexto.
  - ⚠ **Síntoma "escaneo con marca de agua"**: un `.txt` de unos **cientos de bytes** con el
    **bibcode repetido** una vez por página **no es un fallo de descarga** — el `ADS_PDF` bajó bien,
    pero es un escaneo **sin capa de texto** cuya única capa es la marca de agua de ADS. Lo agarra la
    **densidad por página** del umbral (#50; antes pasaba como "extraído" porque el poco texto que
    hay *es* legible) → dispara el OCR como cualquier escaneo. Si te topás con un `.txt` viejo así,
    re-extraé con `python scripts/extract_fulltext.py <slug> --ocr --force`. Caso medido:
    Baranne+1996, 378 bytes → 77 KB por OCR (`fulltext_source: ocr`).
