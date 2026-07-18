---
name: append-knowledge
description: Usar cuando el usuario quiere plegar UNA fuente puntual (paper por bibcode, PDF local, URL) a una entidad YA existente de la wiki — ficha de estrella o concepto — sin re-correr el ingest completo ("agregale este paper a la ficha de tau Ceti", "sumá este PDF al concept de procesos gaussianos", "este bibcode va a GJ 581", "encontré un paper nuevo para el tema X, agregalo"). Plomería mínima + extracción enfocada + síntesis a la nota viva + cierre estándar. NO crea entidades (eso es ingest-star/ingest-topic) ni barre por query lo nuevo (eso es maintain/refrescar).
version: 1.0.1
---

# Append — plegar una fuente puntual a una ficha o concepto existente

Operación **incremental** del patrón LLM Wiki (ver `CLAUDE.md`): el usuario trae **una fuente
concreta** (bibcode ADS, PDF, URL) y una **entidad destino que ya existe**. Encapsula lo que antes
se hacía a mano (p. ej. ampliar un radio de un concepto con 2 papers — copiar PDF, extract, stub,
extracción, síntesis, verify, lint). Trabajar desde la raíz del repo.

**Fronteras:** la entidad destino **debe existir** (ficha en `vault/wiki/stars/` o concept en
`vault/wiki/concepts/`) — si no existe, esto es un `ingest-star`/`ingest-topic`. Si el pedido es
"traé lo NUEVO de X" (barrido por query), es `maintain` (sub-modo A, refrescar). Un **dato suelto
sin fuente citable no entra** (frontera dura, regla #0): pedir la fuente; si es conclusión derivada
de fuentes ya citadas, entra marcada como tal.

## Pasos

1. **Resolver destino y tipo de fuente.** Confirmar que la nota destino existe y clasificar la
   fuente: (i) **bibcode ADS** (con o sin PDF propio), (ii) **PDF sin bibcode ADS** (off-ADS →
   clave sintética `AAAA+Autor`), (iii) **URL** (off-ADS → snapshot web). El slug es el de la
   entidad destino (`stars.yaml`/`topics.yaml`).

2. **Plomería mínima** (por tipo; todo idempotente — con el retro-linkeo de `make_notes`, si la
   nota del paper ya existía en el corpus los seeds `stars`/`thesis_links` se mergean add-only
   solos, sin pisar su extracción):
   - **(i) bibcode ADS** → agregarlo a `extra_core: [<bibcode>, …]` en la entrada de la entidad
     (`vault/config/stars.yaml` o `topics.yaml` — curación **persistente**, sobrevive re-runs) y
     correr la cadena: estrella → los scripts del paso 2 de `ingest-star`; tema →
     `python scripts/ingest_topic.py <slug>`. `query_ads` lo trae por bibcode (`via: manual`).
     ⚠ La cadena re-corre también la query → puede traer **otros** papers nuevos (refresh
     implícito): si aparecen stubs extra, hacé su extracción (maintain A) o anotalos como backlog
     en `vault/STATUS.md` — no los dejes mudos.
     Si el paper no tiene arXiv (paywall/viejo) y el usuario provee el PDF: copiarlo a
     `vault/raw/pdfs/<slug>/<bibcode>.pdf` y correr `python scripts/extract_fulltext.py <slug>`.
   - **(ii) PDF off-ADS** a un tema con `source` off-ADS → agregar el item a `sources:` de la
     entrada del tema (`key` + `pdf` + metadata) y `python scripts/ingest_topic.py <slug>` (sólo
     procesa lo nuevo; deja nota con `pdf` linkeado y fulltext extraído).
   - **(iii) URL** a un tema off-ADS → ídem con `url` en `sources:` + `ingest_topic.py`.
   - **(ii)/(iii) puntual a un tema ADS o a una estrella** (fuente off-ADS aislada, sin cambiar el
     `source` de la entidad) → usar las piezas sueltas: `python scripts/fetch_web.py <slug> <key>
     <url> --concept <concept> …` (URL), o copiar el PDF a `vault/raw/pdfs/<slug>/<key>.pdf` +
     `extract_fulltext.py <slug>` + `python scripts/make_notes.py --web <key> --slug-hint <slug>
     [--concept <concept>] --title … --author … --year …` (PDF). Para una **estrella** no hay seed
     automático: completar `stars: [<nombre>]` en el frontmatter de la nota durante la extracción.

3. **Extracción LLM enfocada en el eje del destino.** Leer SÓLO el fulltext nuevo
   (`vault/raw/fulltext/<slug>/<clave>.txt`; saltar afiliaciones como en `ingest-star`) y poblar la
   nota del paper: `methods`, `bearing`, `thesis_links`/`stars`, y la sección "Extracción"
   orientada a **lo que aporta a la entidad destino** (una señal RV, un mecanismo, una ecuación del
   método), no un resumen genérico.

4. **Síntesis a la nota viva.** Plegar a la ficha/concept **sólo lo que cambia la lectura**:
   - **Ficha de estrella:** rige la **regla de poda** de `CLAUDE.md` (un paper tangencial entra a
     la prosa únicamente si cambia cómo se lee una señal RV). Si discrepa del ground-truth NEA →
     `planets[].disputes[]` (no sobreescribir) + `bearing: challenges`. Actualizar `## Huecos` y la
     matriz método×estrella si el paper aplica un método nuevo a la estrella.
   - **Concept:** integrar al eje del tema (mecanismo, rango, régimen, paso del método) citando
     `[[clave]]`; actualizar `## Huecos`. Si es un radio de un hub, tocar el radio que corresponda
     (y el hub sólo si cambia la síntesis global).

5. **Cierre estándar** (idéntico a ingest): **auto-revisión de autosuficiencia** de la nota destino
   (¿se entiende sin abrir el paper nuevo?) → **`verify-citations`** sobre la prosa tocada y la
   nota de paper nueva → `python scripts/lint.py` en 0 → bookkeeping (`vault/wiki/log.md` SIEMPRE —
   entrada `append: <fuente> → <destino>`; `vault/wiki/index.md` y `vault/STATUS.md` sólo si cambió
   algo catalogable/de estado) → `git add` de archivos específicos + commit → **preguntar antes de
   `push`**.

## Notas
- Distinción de operaciones: `query-corpus` responde sin persistir; `test-hypothesis` persiste sólo
  hipótesis; `maintain A` barre por query lo nuevo; **append** pliega una fuente que el usuario ya
  identificó. Si durante un append aparecen más papers que valdría traer, proponerlo como refresh —
  no colarlos en silencio.
- Reglas de notación, schemas de frontmatter, clave sintética `AAAA+Autor` y frontera dura: ver
  `CLAUDE.md` y el Modo off-ADS de `ingest-topic`.
