---
name: maintain
description: Usar para MANTENER entidades ya ingestadas (estrellas y conceptos), no para crear nuevas. Cubre refrescar una estrella/concepto con papers nuevos ("actualizá GJ 581", "traé lo nuevo de tau Ceti"), borrar un paper/estrella/tema ("borrá el paper X", "sacá esta estrella"), renombrar un slug ("renombrá el slug de …"), re-clasificar tras cambiar relevance.topics ("cambié el objetivo, re-clasificá el corpus"), resolver el backlog del lint (P_rot sin documentar, drift PDF↔disco, cobertura, claims stale), y la pasada periódica de retracciones sobre toda la bóveda ("chequeá retracciones").
version: 1.12.0
---

# Maintain — mantenimiento de estrellas y conceptos ya ingestados

Operación de **mantenimiento** del patrón LLM Wiki (las "operaciones de lint" de Karpathy: la wiki es
viva y hay que cuidarla, no sólo poblarla). **No crea entidades** (para eso `ingest-star`/`ingest-topic`);
opera sobre lo que **ya existe**. Elegir el sub-modo según el pedido. Trabajar desde la raíz del repo.
(Si el pedido es plegar **una fuente puntual ya identificada** —un bibcode, un PDF, una URL— a una
ficha/concepto, eso es `append-knowledge`, no un refresh: A barre por query lo nuevo.)

**Invariante que rige todo:** la cadena de scripts es **idempotente** (no pisa). Refrescar es seguro;
lo que **nunca** se pisa sin decisión explícita es la **extracción LLM** (`make_notes --force` la
regenera → sólo con confirmación) y el **ground-truth** (`fetch_ground_truth --force`). Todo cambio
cierra con **verify-citations** (si tocó prosa con `[[bibcode]]`) + **lint en 0** + `log`, y se
**pregunta antes de `push`**.

---

## A. Refrescar una estrella / concepto (papers nuevos desde el último ingest)

**Copiá este checklist al chat al arrancar y andá tildándolo** (el triage y el verify se saltean sin
dejar rastro):

```
Progreso del refresh de <entidad>:
- [ ] 1  orquestador re-corrido — guardia de expansión revisada
- [ ] 1b triage de los candidatos nuevos del chaining
- [ ] 2  stubs nuevos identificados (git status) y extraídos
- [ ] 3  síntesis actualizada con SÓLO lo nuevo (+ disputes[] / matriz)
- [ ] 4  verify-citations sobre la prosa cambiada (re-fechar el bloque) → lint 0 → log → commit
```

1. Re-correr el **orquestador** (idempotente — sólo agrega lo nuevo, no re-baja ni pisa; el orden
   canónico de la cadena vive en el header del orquestador, no lo copies acá):
   ```bash
   python scripts/ingest_star.py <slug>          # estrella (temas: ingest_topic.py <slug>, despacha por `source`)
   ```
   Un refresh de un tema **off-ADS** procesa su `sources:` en vez de pegarle a ADS. La cadena
   re-chequea retracciones (papers viejos pueden retractarse) y **no pisa el ground-truth**:
   `fetch_ground_truth` saltea un snapshot existente — para refrescar NEA a propósito, correrlo
   suelto con `--force` (NEA cambia entre releases y refrescarlo es una decisión, no un side-effect).
   **Ojo con la expansión:** un refresh no sólo agrega lo publicado desde el último ingest — si la
   regla de relevancia quedó laxa, el citation chaining puede multiplicar el pool. La guardia de
   expansión del orquestador frena antes de bajar nada y te manda a revisar
   `relevance.require`/`min_topics` (`--yes` para continuar a sabiendas).
1b. **Triage de los candidatos del chaining** (estrellas): el refresh deja los candidatos nuevos en
   `candidates` de `build/<slug>/ads.json`, **sin bajar** — correr `python scripts/triage.py <slug>` y
   juzgarlos por título+abstract (aceptado → `extra_core` + re-correr; descartado → `--drop` con
   motivo; dudoso → al usuario). Ver paso 2c del skill `ingest-star`.
2. **Identificar lo nuevo:** `git status` sobre `vault/wiki/papers/` muestra los stubs recién creados. Leer
   **sólo esos** fulltext y hacer su extracción (methods/bearing/thesis_links/P·K/indicadores).
3. **Re-sintetizar incorporando sólo lo nuevo:** releer la ficha/concepto y **actualizar** la síntesis y
   los huecos con lo que aportan los papers nuevos — no reescribir de cero lo ya destilado. Si un paper
   nuevo discrepa, taguear `disputes[]` (o correr `find-contradictions`). Actualizar la matriz
   método×estrella si hay métodos nuevos.
3b. **Auto-revisión de autosuficiencia** (igual que el paso 4 de `ingest-star` / 5 de
   `ingest-topic`, que un refresh también tiene que cumplir): releer la nota **completa** como un
   agente externo que no vio los papers. ¿Alcanza sola? ¿Los papers nuevos abrieron **huecos** que
   la sección `## Huecos` no lista (un parámetro que ahora tiene dos valores, un método aplicado sin
   registrar)? Agregar cinco papers sin releer el conjunto es cómo una ficha deja de alcanzar sola
   sin que nadie lo note.
4. Cierre: verify-citations sobre la prosa cambiada → lint → `log` → commit → preguntar push.

## B. Borrar un paper / estrella / tema
1. **Antes de borrar, mapear lo que cuelga** (el lint los detectaría, pero resolvelos vos limpio):
   ```bash
   grep -rn "<bibcode-o-slug>" vault/wiki/                    # wikilinks, thesis_links, disputes[].ref, matriz
   ```
2. Borrar el/los archivo(s): la nota (`papers/<bib>.md` o `stars/<slug>.md`), su PDF
   (`vault/raw/pdfs/<slug>/…`) y fulltext (`vault/raw/fulltext/<slug>/…`). Si es una estrella/tema entero,
   también su entrada en `stars.yaml`/`topics.yaml`, su `ground_truth/<slug>.json` y su
   `vault/config/registro/<slug>.yaml` (registro de búsqueda + decisiones de triage del sujeto).
3. **Reparar los colgados:** quitar/re-apuntar cada `[[wikilink]]`, `thesis_links`, `disputes[].ref` y
   celda de matriz que apuntaba al borrado. (La tabla `## Papers` de las fichas es Dataview → se
   actualiza sola.) Sacar la estrella de la matriz método×estrella.
4. **Hacer durable el borrado de un paper** (si no, el próximo refresh lo resucita: `make_notes`
   re-escribe el stub de **todo** registro `relevant` sin nota en disco, y los fetchers re-bajan el
   PDF). Las `decisiones` del registro **no** cubren esto: sólo se aplican a candidatos del
   chaining, no al core de la query directa ni a `extra_core`. Según por qué entró:
   - entró por **`extra_core`** → sacarlo de esa lista en `stars.yaml`/`topics.yaml`;
   - entró por la **query** y la lente lo clasifica core → o ajustás la lente y re-clasificás
     (sub-modo D), o lo dejás con `relevance: low` en vez de borrarlo, o asumís que va a volver.
   Decidilo explícitamente y dejalo en el `log`: "borrado y no durable" es un estado, no un olvido.
5. Cierre: **lint en 0** (0 wikilinks rotos / thesis_links colgados / disputes.ref sin destino) → `log`
   (qué se borró y por qué) → commit → preguntar push.

## C. Renombrar un slug
1. Renombrar en orden: la clave en `stars.yaml`/`topics.yaml`, los directorios
   `vault/raw/{pdfs,fulltext}/<slug>/`, `ground_truth/<slug>.json`,
   `vault/config/registro/<slug>.yaml` (si no, el juicio de triage queda huérfano y se re-propone
   todo), la nota `stars/<slug>.md` (o el concepto), y **todos** los `[[wikilink]]` al nombre viejo:
   ```bash
   grep -rln "<slug-viejo>" vault/                            # dónde aparece
   ```
2. Ajustar `data_local` si cambió y el nombre en la matriz. Los wikilinks internos son por **nombre de
   nota** (sobreviven a mover carpeta pero **no** a renombrar el archivo) → actualizarlos todos.
3. Cierre: lint en 0 → `log` → commit → preguntar push.

## D. Re-clasificar tras cambiar la regla de relevancia
Cuando editaste `objective.yaml` (vía `setup`) y el corte core/no-core cambió — sea porque tocaste
`relevance.topics` (las regex) **o** la **regla de combinación** (`relevance.require` / `min_topics`;
p. ej. volviste obligatoria la faceta del eje para frenar el ruido del chaining):
0. **Mirar el delta ANTES de tocar nada** (dry-run, offline — no consulta ADS ni escribe):
   ```bash
   python scripts/query_ads.py --dry-run              # todos los sujetos ya ingestados
   python scripts/query_ads.py <slug> --dry-run       # uno solo
   ```
   Re-clasifica en memoria los `build/<slug>/ads.json` con la regla vigente y reporta core
   antes/después, los papers que **salen** del core —separando los que tienen **extracción LLM**
   (la lista completa: son pocos y son la decisión real) de los **stubs** (sólo el conteo)— y los
   que **entran** sin nota, por vía. Sin esto la decisión es a ciegas: "342 notas salen del core"
   suena catastrófico hasta ver que 338 son stubs del chaining y sólo 4 tenían trabajo encima.
1. Re-correr `python scripts/query_ads.py <slug>` (temas: `python scripts/query_ads.py <slug> --topic`) para cada
   estrella/tema afectado → re-clasifica con la regla nueva (regenera `build/<slug>/ads.json`).
2. **Papers que dejaron de ser core:** decidir con el usuario a partir del dry-run del paso 0 —
   dejar la nota marcada (`relevance: low`) o borrarla (sub-modo B). No borrar en silencio.
3. **Papers que ahora sí son core:** ingestarlos (extracción LLM) como en un refresh (sub-modo A).
4. **Regenerar el apéndice "Excluidos por el filtro"** de las fichas (cambió el corte): re-correr
   `python scripts/make_notes.py <slug>` (temas: `--topic <slug>`) **sin `--force`** — re-estampa
   quirúrgicamente sólo el apéndice máquina con el `ads.json` nuevo (motivo real de exclusión
   incluido; la síntesis LLM no se toca). Revisá que refleje la regla nueva.
5. Cierre: verify (si tocaste prosa) → lint → `log` (qué se re-clasificó) → commit → preguntar push.

## E. Resolver el backlog del lint
Pasada de higiene sobre lo que `lint.py` marca como backlog/WARN (no bloqueante, pero se acumula).

> ⛔ **Los huérfanos NO entran acá: bloquean.** Una nota-concepto sin links entrantes es
> **inalcanzable** desde la bóveda, y `lint.py` la cuenta en `n_block` (exit 1, igual que un wikilink
> roto) — dejarla "para la próxima pasada" traba el cierre de la operación siguiente. Se arregla
> **en el cierre de la operación que la creó, antes de commitear**: citarla desde donde corresponda
> (la ficha/concepto que la motivó, `index.md`, el hub si es un radio) o borrarla si sobra. Si
> aparece en una pasada periódica, resolvela en el momento.

- **Triage pendiente** (#55 — candidatos del chaining que nadie juzgó) → `python scripts/triage.py
  <slug>` y decidir cada uno por título+abstract: pertinente → `extra_core` en `stars.yaml` +
  re-correr la cadena; ruido → `--drop … --reason`; dudoso → al usuario. Es el paso con más juicio
  de un ingest y el que más fácil queda a medias. Los descartes van a `decisiones` de
  `vault/config/registro/<slug>.yaml` (versionado: viajan). Si el hallazgo salió del **registro** y
  no de `build/` (lo dice el texto: "según el registro del <fecha>"), es un **snapshot** de la
  última corrida: re-corré la cadena antes de decidir, porque el conteo puede estar viejo.
- **Sin P_rot / campos nulos** → abrir una `query-corpus` para imputar desde la literatura
  (web/ADS) y dejar el valor **en el cuerpo con su `[[bibcode]]`** (o marcado `inferencia` si es
  lectura propia). ⛔ **No completar el frontmatter:** los campos de ground-truth son **espejo de
  NEA** (#70) y un null ahí es el estado correcto, no un hueco a tapar. El hallazgo del lint es
  justamente "NEA no lo trae **y** el cuerpo no documenta uno citado": lo que se completa es la
  prosa. Rellenar el campo lo convierte en un hallazgo **bloqueante** (espejo roto).
- **PDF ↔ disco / cuerpo** (drift del campo `pdf` o del link de cabecera) → linkear el PDF bajado o
  corregir el puntero roto; después `python scripts/make_notes.py --restamp-pdf-links` para que el link
  `[📄 PDF]` de la cabecera siga al frontmatter (#47 — barre todas las notas de papers:
  agrega/corrige/quita, cirugía sin tocar la extracción LLM; también es el backfill del corpus pre-#13,
  donde el link no existía). Si el hallazgo dice **"cabecera fuera del contrato"** (#48), el backfill
  **no** la va a tocar: normalizá primero esa línea a la forma canónica (`· … · ADS: \`<bibcode>\``, o
  `· … fuente off-ADS · \`<citekey>\``) y recién ahí re-corré el backfill.
- **Juicio de triage todavía en `build/`** (bóveda ingestada antes de 1.9.0, migración one-shot: el
  lint **no** la surface) → consolidarlo en el
  registro versionado, **sin esperar al próximo `--drop`**:
  `python scripts/triage.py <slug> --migrate` (idempotente; ante el mismo bibcode gana lo ya
  versionado). Después commitear `vault/config/registro/<slug>.yaml`: recién ahí el juicio viaja.
- **Cabecera no estampable** (#69 — ficha/concepto sin la línea `> _Generado con Almagesto v…_`:
  los estampadores de cabecera no-opean en silencio sobre ella, así que el puntero de búsqueda de
  #64 nunca aterriza) → `python scripts/make_notes.py --restamp-headers` (barre todas, idempotente,
  la versión sale del `generator` de cada nota). Después re-correr `make_notes` del sujeto para que
  el puntero de búsqueda se estampe ahora que hay dónde.
- **Papers sin `pdf_source`** (#57 — corpus ingestado antes de 1.10.0: no se sabe si el `.txt`
  salió del eprint o del publicado, y ese caveat es el que evita que `verify-citations` "corrija"
  una nota hacia un v1 pre-referato). Migración one-shot: **el lint tampoco la surface** —`null` es
  un estado legítimo (fuente desconocida), así que una categoría permanente sería ruido— →
  **backfill sin re-bajar nada**:
  `python scripts/extract_fulltext.py <slug>` re-estampa el campo leyendo la marca de arXiv del
  `.txt` que ya está en disco. Lo que quede en `null` es **desconocido**, no "publicado".
- **Cobertura** (concepto/hipótesis sin ninguna cita) → agregar las citas que faltan.
- **Fuentes pendientes** (`pending_source`) → conseguir el PDF/fuente (el lint lista el puntero
  doi/url), reemplazar `pending` por `pdf:`/`url:` en `sources:` y re-correr la cadena.
- **Fulltext ilegible** (mojibake/escaneo) → instalar `tesseract-ocr` y re-correr
  `extract_fulltext.py <slug>` (upgradea solo el .txt ilegible vía OCR), o reemplazar el PDF por
  uno con capa de texto sana; si no se consigue, marcar la fuente `pending`.
- **Fuga de implementación** (WARN) → revisar el hit; si es material de código no bibliográfico,
  sacarlo del vault (frontera dura).
- **Verificación stale** (#56 — la nota se editó **después** de la fecha de su bloque
  `## Verificación de citas`: típico de una ampliación por `append-knowledge` o un refresh de A) →
  correr `verify-citations` **sobre lo agregado** y re-fechar el bloque. La prosa nueva vive bajo un
  encabezado que se lee como vigente: la nota no afirma falso, afirma **de menos** sobre lo que
  chequeó. Si el hallazgo es "bloque sin fecha en el encabezado", re-fechalo
  (`## Verificación de citas (AAAA-MM-DD)`): sin fecha el chequeo no puede saber si sigue vigente.
- **Corpus truncado** (y su hermano `truncated_glyph`) → a la query directa le faltó cola. El
  orquestador **no** acepta `--rows`: se corre la pieza suelta y después la cadena —
  `python scripts/query_ads.py <slug> --rows 5000` y luego `python scripts/ingest_star.py <slug>`. Mientras tanto, la ficha afirma sobre un universo recortado.
  Leer el `+ N de la segunda pasada por fecha` del mensaje: lo que falta es el **medio** del
  universo, no la cola reciente (#79 — esa la cubre la segunda pasada al truncar). Un corpus viejo
  (ads.json anterior a 1.12.0) no trae el dato y el mensaje no lo afirma: ahí falta también la cola.
- **Papers con corrección publicada** (`corrections`) → se resuelve como dice **F** (abrir el
  `notice_doi`, comparar contra lo que la nota afirma citando ese `[[bibcode]]`).
- **Sin verificar** (query/concepto con citas pero sin bloque `## Verificación de citas`) → correr
  `verify-citations` sobre esa nota y dejar el bloque **fechado**.
- **Citas no verificables** (bibcode citado sin su `.txt` en `vault/raw/fulltext/`) → es
  **precondición**, no backlog opcional: sin fulltext no hay con qué chequear. Conseguir la fuente
  (cascada de rescate de PDFs en `ingest-star`) o marcarla `pending`.
- **Claims stale** → re-verificar contra la fuente los que quedaron dudosos.
Cierre: lint (idealmente bajando el conteo de backlog) → `log` → commit → preguntar push.

## F. Pasada periódica de retracciones (bóveda completa)
La cadena de ingest chequea retracciones **sólo sobre los papers del slug en curso**
(`check_retractions.py --slug`); un paper puede retractarse **años después** de ingestado, así que
el barrido completo es tarea periódica (p. ej. mensual, o al cerrar una tanda de ingests):
```bash
python scripts/check_retractions.py            # toda la bóveda vía Crossref (red)
```
Si marca alguno (`retracted: true` en la nota; el lint lo vuelve **bloqueante**): revisar cada
afirmación que cita ese paper (quitar la cita o reflejar la retracción), `log`, commit.

La misma pasada estampa las **correcciones no-retractantes** (#52): `corrections: [{type,
notice_doi, date, source}]` para cada `erratum` / `corrigendum` / `expression-of-concern` que
Crossref reporte. **No bloquean** —el paper sigue siendo citable— y el lint las lista como
**backlog**, pero son la señal que más directamente **envejece un número ya extraído**: no se
revisa la existencia del paper sino los **valores que se le sacaron**. Al resolver el backlog,
por cada paper con `corrections`: abrir el aviso (`notice_doi`), ver qué corrigió, y comparar
contra lo que la ficha/concepto afirma citando ese `[[bibcode]]` —si el valor cambió, es una
edición de la nota (y, si toca un parámetro planetario, puede ser una `disputes[]`)—. Una
`expression-of-concern` no cambia ningún número: baja la confianza de lo que se apoya sólo en esa
fuente. Dejar en el `log` qué se revisó.

## Notas
- **No es ingest:** si la entidad no existe todavía, esto no aplica → `ingest-star`/`ingest-topic`.
- **No es query:** una pregunta puntual va por `query-corpus`; acá se **modifica** la bóveda.
- Schemas de frontmatter, reglas de ruta y disputas: ver `CLAUDE.md`. `git add` **específico** (no `-A`).
