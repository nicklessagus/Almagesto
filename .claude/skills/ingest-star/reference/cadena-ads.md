# La cadena mecánica de ADS — descripción canónica (#67)

**Referencia compartida por `ingest-star` e `ingest-theme`.** Los dos skills la describían **cada
uno**, con la misma prosa: dos copias de una prescripción son dos lugares donde corregirla y uno
donde olvidarse. Es el modo de falla que `CLAUDE.md` ya nombra para el orden de la cadena —*"puntero,
no copia: no replicar la lista de scripts en docs/skills"*—, acá aplicado a la mecánica misma. Lo
que cada skill conserva es **lo suyo** (SIMBAD/NEA, glifo, barrido y triage en la estrella; query
Solr co-diseñada, retro-tag y modo off-ADS en el tema); todo lo de abajo es de los dos.

⚠ **El orden canónico de los pasos NO está acá**: vive en el header del orquestador
(`scripts/ingest_star.py` / `scripts/ingest_theme.py`) y en `lib_config.CADENA_ESTRELLA`. Este
archivo describe **qué hace cada pieza y qué falla**, no en qué orden corren — replicar el orden
sería reintroducir la copia que este archivo elimina.

## Guardia de expansión (checkpoint humano)

La **guardia de expansión** es lo primero que puede frenar la cadena, y frena a propósito.

Entre `query_ads` y el primer paso que gasta red y disco, el orquestador compara el core del
`ads.json` fresco contra las notas ya ingestadas del sujeto: si se multiplicó (default ×1.5 y 50 o
más nuevos) **frena** con el conteo, cuántos vinieron por el grafo de citas y el puntero a
`relevance.require`/`min_facets`.

Antes de refrescar un sujeto viejo, mirá ese número: si el pool explotó, revisá la **regla de
combinación** en `objective.yaml` (skill `setup`) antes de bajar nada — podar las regex no alcanza si
la combinación sigue siendo OR. `--yes` continúa a sabiendas.

## Citation chaining

`query_ads` pide a ADS references/citations de los core: trae surveys y catálogos conectados por el
**grafo de citas** aunque no nombren al sujeto en el abstract. Quedan marcados `via: chain:*` en
`build/<slug>/ads.json` y se desactiva con `--no-chain`.

El **anclaje** es lo que cambia entre los dos skills, y es de cada uno: en una estrella va anclado al
sujeto (`full:` sobre nombre+alias); en un tema, a la propia query del tema (recall extra sin traer
los mega-citados genéricos del área).

⚠ Lo que el chaining trae **no es automáticamente pertinente**: la lente clasifica **tema**, no
pertinencia al sujeto. Por eso existe la compuerta de triage — que en `ingest-star` es un paso propio
(2c) y que en cualquier sujeto se resuelve con `python scripts/triage.py <slug>`.

## `fetch_arxiv` — el rate limit

Respeta el rate limit de arXiv (**1 req/3 s**) → con muchos PDFs tarda; conviene correrlo en
background. No es una perilla a subir: es la condición de uso del servicio.

## `fetch_pdf` — la cascada, y su fallback

Los papers **sin arXiv** —y los que tienen arXiv pero cuya bajada falló— los intenta `fetch_pdf`,
que resuelve contra ADS en cascada: `EPRINT_PDF` → `ADS_PDF` (escaneo alojado por ADS, con token) →
`PUB_PDF` (publisher), con **fallback `curl`**.

Esa rama es la que después queda registrada en `pdf_source` (`eprint` | `ads` | `publisher` | `web`
| `null` = desconocido, que **no** es "publicado"), y el consumidor la mira antes de copiar un
número: con `eprint` el `.txt` es el **preprint** y puede traer otros valores que el publicado.

## `build/<slug>/missing_pdf.json` — el residuo

Lo que ni así sale queda en `build/<slug>/missing_pdf.json`: el **residuo completo del ingest, verdad
de disco**. Cada entrada trae su `bibstem` y un `hint` con la rama por donde seguir.

⛔ **"Bajar manual por DOI" no alcanza** — medido en un ingest real: el resolver falló en **5 de 17**
(pre-arXiv de 2000–2015: SPIE, The Messenger, A&A viejo) y **4 de 5 se recuperaron** por las ramas
de la cascada manual. Esa cascada vive en `reference/rescate-pdfs.md` (del skill `ingest-star`,
canónica ahí para los dos).

## `extract_fulltext` — los tres chequeos, y el OCR

Escribe `vault/raw/fulltext/<slug>/<bibcode>.txt` y corre **tres chequeos deterministas e
independientes** sobre el texto, que miden cosas distintas y hacen falta los tres:

| Chequeo | Pregunta | Qué pasa si falla |
|---|---|---|
| `is_legible` | ¿sirve? (chars no-espacio, densidad por página, ASCII imprimible) | cae a **OCR** con `tesseract` |
| `is_garbled` | ¿es correcto? | estampa el header `source: ocr` |
| `symbols_lost` | ¿está completo? | estampa `simbolos NO extraidos` (#113) |

Sin `tesseract` instalado **avisa** y el lint lo lista; no falla en silencio. El `.txt` se reescribe
en **tres casos y nada más** (`--force`, upgrade automático a OCR, backfill de las marcas), y por eso
el hash de fuente de `verify-citations` es una alarma rara: cuando suena, hay algo.

Detalle de los casos raros de extracción (escaneo con marca de agua, quirks de PostScript viejo) en
`reference/rescate-pdfs.md`.

## `check_retractions`

Consulta **Crossref** por DOI y, si el paper fue **retractado**, estampa `retracted: true` en su nota
(el lint lo vuelve bloqueante: una fuente retractada citada rompe la frontera dura) → revisá cada
afirmación que lo cita. En la misma pasada estampa las `corrections` (erratum/corrigendum/EoC), que
**no** invalidan el paper pero envejecen el número que se le extrajo.

En la cadena corre con `--slug` (sólo los papers de **este** ingest); el barrido completo de la
bóveda es la pasada periódica del skill `maintain`.

## `extra_core` — la curación que PERSISTE

Un paper que la lente no marcó core y vos querés igual se agrega **de forma persistente** en la
entrada del sujeto (`vault/config/stars.yaml` o `vault/config/themes.yaml`):

```yaml
extra_core:
  - {bibcode: 2019A&A...624A..49G, via: usuario, fecha: 2026-08-26, motivo: "árbitro de la señal b"}
```

Forma **dura** (D-58): es una **lista de mapas** con `via` (vocabulario cerrado de `extra_core`,
`cfg.EXTRA_CORE_VIA`: `usuario` · `triage` · `citado-por-corpus`), `fecha` y `motivo`. ⛔ **No
confundir con el `via` de una fuente off-ADS** (`sources:`, #111 — `usuario` · `descubrimiento` ·
`reporte`, `triage.VIA_FUENTE`): son dos carriles distintos y `load_extra_core` **aborta** si le
llega un valor del otro. El escalar y la lista de strings **bloquean**, y
`python scripts/triage.py <slug>` imprime el snippet listo para pegar.

Por qué acá y no en `build/`: `build/` es scratch gitignored y se pisa en el próximo run. La entrada
en el YAML **se commitea y viaja**, sobrevive al re-run y a otra máquina — que es la misma razón por
la que el descarte (`triage.py --drop … --reason`) vive en `vault/config/registro/<slug>.yaml`. Los
dos carriles de la curación dejan registro versionado; ninguno cura en silencio.

## Idempotencia

La cadena **no pisa**: re-correrla es seguro y baja sólo lo nuevo. La única excepción es add-only (el
retro-linkeo de `stars` / `thesis_links` en notas que ya existían). En particular,
`fetch_ground_truth` **no** refresca un ground-truth existente salvo `--force`: refrescar desde NEA
es una decisión explícita, no un side-effect de re-correr la cadena.
