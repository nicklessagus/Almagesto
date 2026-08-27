---
name: maintain
description: Usar para MANTENER entidades ya ingestadas (estrellas y conceptos), no para crear nuevas. Cubre refrescar una estrella/concepto con papers nuevos ("actualizá GJ 581", "traé lo nuevo de tau Ceti"), borrar un paper/estrella/tema ("borrá el paper X", "sacá esta estrella"), renombrar un slug ("renombrá el slug de …"), re-clasificar tras cambiar relevance.facets ("cambié el objetivo, re-clasificá el corpus"), resolver el backlog del lint (P_rot sin documentar, drift PDF↔disco, cobertura, claims stale), y la pasada periódica de retracciones sobre toda la bóveda ("chequeá retracciones").
version: 1.20.0
---

# Maintain — mantenimiento de estrellas y conceptos ya ingestados

Operación de **mantenimiento** del patrón LLM Wiki (las "operaciones de lint" de Karpathy: la wiki es
viva y hay que cuidarla, no sólo poblarla). **No crea entidades** (para eso `ingest-star`/`ingest-theme`);
opera sobre lo que **ya existe**. Elegir el sub-modo según el pedido. Trabajar desde la raíz del repo.
(Si el pedido es plegar **una fuente puntual ya identificada** —un bibcode, un PDF, una URL— a una
ficha/concepto, eso es `append-knowledge`, no un refresh: A barre por query lo nuevo.)

**Invariante que rige todo:** la cadena de scripts es **idempotente** (no pisa). Refrescar es seguro;
lo que **nunca** se pisa sin decisión explícita es la **extracción LLM** (`make_notes --force` la
regenera → sólo con confirmación) y el **ground-truth** (`fetch_ground_truth --force`). Todo cambio
cierra con **verify-citations** (si tocó prosa con `[[bibcode]]`) + **`lint.py --cierre <slug>` en 0** + `log`, y se
**pregunta antes de `push`**.

---

## A. Refrescar una estrella / concepto (papers nuevos desde el último ingest)

**Copiá este checklist al chat al arrancar y andá tildándolo** (el triage, el contraste, la
auto-revisión y el verify se saltean sin dejar rastro):

```
Progreso del refresh de <entidad>:
- [ ] 1  orquestador re-corrido — guardia de expansión revisada
- [ ] 1b triage de los candidatos nuevos del chaining
- [ ] 2  stubs nuevos identificados (git status) y extraídos
- [ ] 2b inventario por eje actualizado con lo nuevo (fila nueva / eje nuevo)
- [ ] 3  síntesis actualizada con SÓLO lo nuevo (+ disputes / régimen si es concepto / matriz)
- [ ] 3b auto-revisión de autosuficiencia sobre la nota COMPLETA
- [ ] 4  verify-citations sobre la prosa cambiada (re-fechar el bloque) → lint 0 → log → commit
```

1. Re-correr el **orquestador** (idempotente — sólo agrega lo nuevo, no re-baja ni pisa; el orden
   canónico de la cadena vive en el header del orquestador, no lo copies acá):
   ```bash
   python scripts/ingest_star.py <slug>          # estrella (temas: ingest_theme.py <slug>, despacha por `source`)
   ```
   Un refresh de un tema **off-ADS** procesa su `sources:` en vez de pegarle a ADS. La cadena
   re-chequea retracciones (papers viejos pueden retractarse) y **no pisa el ground-truth**:
   `fetch_ground_truth` saltea un snapshot existente — para refrescar NEA a propósito, correrlo
   suelto con `--force` (NEA cambia entre releases y refrescarlo es una decisión, no un side-effect).
   **Ojo con la expansión:** un refresh no sólo agrega lo publicado desde el último ingest — si la
   regla de relevancia quedó laxa, el citation chaining puede multiplicar el pool. La guardia de
   expansión del orquestador frena antes de bajar nada y te manda a revisar
   `relevance.require`/`min_facets` (`--yes` para continuar a sabiendas).
1b. **Triage de los candidatos del chaining** (estrellas): el refresh deja los candidatos nuevos en
   `candidates` de `build/<slug>/ads.json`, **sin bajar** — correr `python scripts/triage.py <slug>` y
   juzgarlos por título+abstract (aceptado → `extra_core` + re-correr; descartado → `--drop` con
   motivo; dudoso → al usuario). Ver paso 2c del skill `ingest-star`.
2. **Identificar lo nuevo:** `git status` sobre `vault/wiki/papers/` muestra los stubs recién creados. Leer
   **sólo esos** fulltext y hacer su extracción (methods/`role`/thesis_links/P·K/indicadores).
   ⛔ **Es UNA VISTA del sujeto que se está refrescando (#188)**, no «la extracción del paper»:
   la nota declara `vistas: [{sujeto, tipo, fecha, txt, lente}]` y lleva su `## Vista — <sujeto>`.
   Armá el prompt con `python scripts/extraction_prompt.py <slug> <bibcode> [--theme]` y cosechá
   con `python scripts/harvest_views.py <slug> [--theme]`, que estampa `fecha`/`txt`/`lente` y
   mergea add-only. La incoherencia `vistas[]` ↔ cuerpo es **bloqueante** en el lint.
   ⚠ **`bearing` NO va en la nota del paper** (D-21): la postura respecto de una tesis depende de la
   tesis —un paper puede tocar varias— y vive en la **tabla de evidencia de la hipótesis**, con cita
   textual, donde `verify-citations` la puede chequear. En el paper es un veredicto sin evidencia y
   el lint lo **bloquea** como schema viejo (migrador: `make_notes.py --migrate-bearing`).
2b. **Contraste con lo que ya estaba (#72):** el `## Inventario por eje` de la nota es **lo que
   evita re-derivar la síntesis desde cero** — dice qué papers sostienen cada eje en disputa, con qué
   método y qué baseline. Para cada paper nuevo: si toca un eje ya inventariado, **agregar su fila**;
   si abre una discrepancia sobre un eje que no estaba, **abrir el eje**. Si la nota es anterior a
   1.17.0 y no tiene inventario, éste es el momento de armarlo con los papers en juego. Rige el ⛔:
   **sin columna "valor adoptado"** (adoptar decide por el consumidor, regla #0), y mirar el `role`
   (#73) antes de leer dos filas como desacuerdo — fundacional↔aplicación es instanciación.
3. **Re-sintetizar incorporando sólo lo nuevo:** releer la ficha/concepto y **actualizar** la síntesis y
   los huecos con lo que aportan los papers nuevos, apoyándose en el inventario de 2b — no reescribir
   de cero lo ya destilado. Si un paper
   nuevo discrepa, taguear `disputes` a nivel nota con posiciones explícitas (#71) —o correr
   `find-contradictions`—. Actualizar la matriz método×estrella si hay métodos nuevos.
   **Si la entidad es un concepto**, el paper nuevo entra además por la puerta del **`## Régimen de
   validez`** (#74): si afirma bajo condiciones (SNR, muestreo, tamaño de muestra, definición del
   observable), la fila va ahí — y si contradice a uno viejo **sólo porque el régimen es otro**, eso
   **no** es una `disputes`, es una fila nueva de esa tabla. Es el modo de falla propio de un
   concepto (**generalizar de más**) y el que `verify-citations` devuelve `soportada`: si nadie lo
   escribe en el refresh, la condición se pierde sin dejar rastro. Un régimen que ningún paper cubre
   es un hueco → `## Huecos`.
3b. **Auto-revisión de autosuficiencia** (igual que el paso 4 de `ingest-star` / 5 de
   `ingest-theme`, que un refresh también tiene que cumplir): releer la nota **completa** como un
   agente externo que no vio los papers. ¿Alcanza sola? ¿Los papers nuevos abrieron **huecos** que
   la sección `## Huecos` no lista (un parámetro que ahora tiene dos valores, un método aplicado sin
   registrar)? Agregar cinco papers sin releer el conjunto es cómo una ficha deja de alcanzar sola
   sin que nadie lo note.
4. Cierre: verify-citations sobre la prosa cambiada → lint → `log` → commit → preguntar push.

## B. Borrar un paper / estrella / tema

### B0. Borrar una ENTIDAD entera (estrella o tema) → `entity.py` (INV-19)

Una entidad vive en **siete capas** y el procedimiento a mano de abajo era nueve pasos en orden
sobre siete lugares distintos — o sea una lista de cosas que se pueden saltear, y las salteadas no
dejaban rastro (el lint tenía red para `wiki/` y **ninguna** para el registro, `raw/` ni `build/`).
Hay herramienta:

```bash
python scripts/entity.py plan   <slug>              # qué toca — no escribe nada
python scripts/entity.py delete <slug> --yes        # aplica
python scripts/entity.py rename <viejo> <nuevo> --yes
```

⛔ **Sin `--yes` es dry-run**, a propósito: la capa 2 (`config/registro/<slug>.yaml`) es el **único
artefacto no regenerable** de la bóveda. Lo que la herramienta **no** hace sola, y avisa:
- **no borra los papers compartidos**: a una nota con `stars: [A, B]` le saca A y la deja;
- **no repara los `[[wikilink]]` rotos** — apuntan a una nota que ya no existe y el lint los da
  bloqueantes. Repararlos automáticamente sería decidir qué decía esa frase;
- **no borra la nota que queda sin destino** (D-23): es extracción ya pagada.
Todo eso sale listado al aplicar, y el cierre es `lint.py --cierre <slug>` en 0.

Y el lint tiene la red del otro lado: **capas colgadas** (registro / `raw/pdfs` / `raw/fulltext` /
`build` de un slug que no está en `stars.yaml`/`themes.yaml`) es backlog propio.

### B1. Borrar un PAPER suelto (o hacerlo a mano)
1. **Antes de borrar, mapear lo que cuelga** (el lint los detectaría, pero resolvelos vos limpio):
   ```bash
   grep -rn "<bibcode-o-slug>" vault/wiki/                    # wikilinks, thesis_links, disputes[].posiciones[].ref, matriz
   ```
2. Borrar el/los archivo(s): la nota (`papers/<bib>.md` o `stars/<slug>.md`), su PDF
   (`vault/raw/pdfs/<slug>/…`) y fulltext (`vault/raw/fulltext/<slug>/…`). Si es una estrella/tema entero,
   también su entrada en `stars.yaml`/`themes.yaml`, su `ground_truth/<slug>.json` y su
   `vault/config/registro/<slug>.yaml` (registro de búsqueda + decisiones de triage del sujeto).
3. **Reparar los colgados:** quitar/re-apuntar cada `[[wikilink]]`, `thesis_links`,
   `disputes[].posiciones[].ref` y
   celda de matriz que apuntaba al borrado. (⚠ La tabla `## Papers` **NO** es Dataview: es una tabla **estampada** (D-10/D-11), así que la
   fila del paper borrado queda y produce un **wikilink roto** —categoría bloqueante—. Re-estampar
   con `python scripts/make_notes.py <slug>` en cada ficha afectada. Lo que sí se
   actualiza sola.) Sacar la estrella de la matriz método×estrella.
4. **Hacer durable el borrado de un paper** (si no, el próximo refresh lo resucita: `make_notes`
   re-escribe el stub de **todo** registro `relevant` sin nota en disco, y los fetchers re-bajan el
   PDF). Las `decisiones` del registro **no** cubren esto: sólo se aplican a candidatos del
   chaining, no al core de la query directa ni a `extra_core`. Según por qué entró:
   - entró por **`extra_core`** → sacarlo de esa lista en `stars.yaml`/`themes.yaml`;
   - entró por la **query** y la lente lo clasifica core → o ajustás la lente y re-clasificás
     (sub-modo D), o lo dejás con `relevance: low` en vez de borrarlo, o asumís que va a volver.
   Decidilo explícitamente y dejalo en el `log`: "borrado y no durable" es un estado, no un olvido.
5. Cierre: **`lint.py --cierre <slug>` en 0** (0 wikilinks rotos / thesis_links colgados / disputes.ref sin destino) → `log`
   (qué se borró y por qué) → commit → preguntar push.

## C. Renombrar un slug

**Usá `python scripts/entity.py rename <viejo> <nuevo>`** (dry-run sin `--yes`): mueve las siete
capas, preserva el registro —si queda atrás, el triage re-propone todo lo descartado **sin el
motivo**, que es el bug que #51 cerró— y **rehúsa** renombrar encima de artefactos existentes, que
fusionaría dos entidades en silencio. En un **tema** reescribe además `thesis_links` y los
`[[wikilink]]`; en una **estrella** no hace falta: lo que se referencia es el NOMBRE, que el
renombre de slug no toca.

El procedimiento manual, por si hay que hacerlo a mano:
1. Renombrar en orden: la clave en `stars.yaml`/`themes.yaml`, los directorios
   `vault/raw/{pdfs,fulltext}/<slug>/`, `ground_truth/<slug>.json`,
   `vault/config/registro/<slug>.yaml` (si no, el juicio de triage queda huérfano y se re-propone
   todo), la nota `stars/<slug>.md` (o el concepto), y **todos** los `[[wikilink]]` al nombre viejo:
   ```bash
   grep -rln "<slug-viejo>" vault/                            # dónde aparece
   ```
2. Ajustar `data_local` si cambió y el nombre en la matriz. Los wikilinks internos son por **nombre de
   nota** (sobreviven a mover carpeta pero **no** a renombrar el archivo) → actualizarlos todos.
3. Cierre: `lint.py --cierre <slug>` en 0 (con el slug **nuevo**) → `log` → commit → preguntar push.

## D. Re-clasificar tras cambiar la regla de relevancia
Cuando editaste `objective.yaml` (vía `setup`) y el corte core/no-core cambió — sea porque tocaste
`relevance.facets` (las regex) **o** la **regla de combinación** (`relevance.require` / `min_facets`;
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
1. Re-correr `python scripts/query_ads.py <slug>` (temas: `python scripts/query_ads.py <slug> --theme`) para cada
   estrella/tema afectado → re-clasifica con la regla nueva (regenera `build/<slug>/ads.json`).
2. **Papers que dejaron de ser core:** decidir con el usuario a partir del dry-run del paso 0 —
   dejar la nota marcada (`relevance: low`) o borrarla (sub-modo B). No borrar en silencio.
3. **Papers que ahora sí son core:** ingestarlos (extracción LLM) como en un refresh (sub-modo A).
4. **Regenerar el apéndice "Excluidos por el filtro"** de las fichas (cambió el corte): re-correr
   `python scripts/make_notes.py <slug>` (temas: `--theme <slug>`) **sin `--force`** — re-estampa
   quirúrgicamente sólo el apéndice máquina con el `ads.json` nuevo (motivo real de exclusión
   incluido; la síntesis LLM no se toca). Revisá que refleje la regla nueva.
5. Cierre: verify (si tocaste prosa) → lint → `log` (qué se re-clasificó) → commit → preguntar push.

## E. Resolver el backlog del lint
Pasada de higiene sobre lo que `lint.py` marca como backlog/WARN (no bloqueante, pero se acumula).
**Esta pasada corre SIN `--cierre`** — es el otro lado de R-1: acá los pares de verificación
vencidos son una lista para ir resolviendo, no un gate. Frenar una bóveda con deuda vieja un
martes cualquiera no frena nada útil; el gate es el cierre de la operación que tocó la nota.

> ⛔ **Los huérfanos NO entran acá: bloquean.** Una nota-concepto sin links entrantes es
> **inalcanzable** desde la bóveda, y `lint.py` la cuenta en `n_block` (exit 1, igual que un wikilink
> roto) — dejarla "para la próxima pasada" traba el cierre de la operación siguiente. Se arregla
> **en el cierre de la operación que la creó, antes de commitear**: citarla desde donde corresponda
> (la ficha/concepto que la motivó, `index.md`, el hub si es un radio) o borrarla si sobra. Si
> aparece en una pasada periódica, resolvela en el momento.

- **Core sin extraer / extraído pero no sintetizado (D-15) — el backlog del ingest a medias.**
  Terminar de ingestar los papers pendientes usa **los mismos pasos 1→4 del ingest**; lo único
  distinto es la plomería de entrada, y acá **ya no hay ninguna**: la fuente está bajada, con
  fulltext y stub. Por eso **no hace falta una operación nueva** — es este sub-modo.

  | Qué falta | Dónde se resuelve |
  |---|---|
  | la fuente **no está** en la bóveda (hay que bajarla) | skill `append-knowledge` |
  | la fuente **ya está**; falta extracción + síntesis | **acá** |

  Procedimiento: leer el `.txt` (un subagente por paper, como en `ingest-star` — el prompt lo arma
  `extraction_prompt.py` y la cosecha la hace `harvest_views.py`), poblar `methods`/`role`/
  `thesis_links` y **la vista del sujeto** (`vistas[]` + `## Vista — <sujeto>`, #188), contrastar contra el `## Inventario por eje` de la nota destino, sintetizar
  **en su lugar** (no una sección nueva), y re-estampar la tabla `## Papers` con
  `python scripts/make_notes.py <slug>` para que el estado de cada paper deje de mentir. Si un paper
  legítimamente no se inlinea, declarar `no_sintetizado: <motivo>` en su nota — con motivo, como
  todo descarte. Al cerrar, **re-declarar la fecha de síntesis**
  (`python scripts/triage.py <slug> --sintesis --n-papers <N>` + `make_notes.py <slug>`): si no, la
  ficha sigue diciendo que se sintetizó cuando se sintetizó la vez pasada.
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
- **Juicio de triage en `build/<slug>/triage.json`** → **bloqueante**: el lector dejó de mergear ese
  archivo pre-1.9.0 (el framework no lleva capas de compatibilidad). Mientras exista, el triage
  vuelve a proponer lo ya descartado **sin el motivo**, que es el bug que #51 arregló. Una sola
  corrida: `python scripts/triage.py <slug> --migrate`.
- **`concept_areas` sin declarar** (WARN) → el typo-check de áreas de `concepts/` está **apagado**.
  Declarar la lista en `vault/config/objective.yaml` —aunque sea con las áreas que ya usás—: no se
  infiere de las carpetas en disco porque eso convertiría un typo ya cometido en área legítima.
- **disputes en el schema viejo** (#71) → **bloqueante**: el lint dejó de leer
  `planets[].disputes[]` a propósito (una sola semántica), así que esas disputas están **mudas**
  hasta migrarlas. Correr la migración una vez:
  `python scripts/make_notes.py --migrate-disputes`. Pasa `planets[].disputes[]` (que tenía el polo
  de verdad hardcodeado) a `disputes` a nivel nota con posiciones explícitas, materializando el lado
  implícito como `{source: ground_truth, value: <el valor que la ficha tiene hoy>}`. Toca **sólo**
  las fichas con disputas viejas y **no** el cuerpo, pero re-serializa el frontmatter: **revisá el
  diff antes de commitear**. (La otra vía válida es **re-ingestar** el sujeto y rehacer las disputas
  con la extracción, que de paso compara.)
- **disputes mal formadas / ref de una posición sin paper** (#71) → resolver a mano: una disputa con
  **una sola** posición no es un desacuerdo (va a la prosa citada), y una `ref` colgante es un typo
  de bibcode o un paper sin ingestar.
- **Extraído pero no sintetizado** (#75) → el paper pagó el paso más caro y su contenido nunca llegó
  a una ficha ni a un concepto. Releer su `## Vista — <sujeto>` (schema #188; en una nota sin migrar, su `## Extracción (LLM)`) y decidir: si aporta algo al sujeto,
  **sintetizarlo** en la nota viva (rige la regla de poda) y cerrar con `verify-citations`; si
  legítimamente no se inlinea —tangencial, o aporta sólo vía roll-up—, declararlo en la nota del
  paper con `no_sintetizado: <motivo>`. La marca **sin motivo** vuelve a reportarse: mismo criterio
  que el `--reason` del triage, no curar en silencio.
- **PDF ↔ disco / cuerpo** (drift del campo `pdf` o del link de cabecera) → linkear el PDF bajado o
  corregir el puntero roto; después `python scripts/make_notes.py --restamp-pdf-links` para que el link
  `[📄 PDF]` de la cabecera siga al frontmatter (#47 — barre todas las notas de papers:
  agrega/corrige/quita, cirugía sin tocar la extracción LLM; también es el backfill del corpus pre-#13,
  donde el link no existía). Si el hallazgo dice **"cabecera fuera del contrato"** (#48), el backfill
  **no** la va a tocar: normalizá primero esa línea a la forma canónica (`· … · ADS: \`<bibcode>\``, o
  `· … fuente off-ADS · \`<citekey>\``) y recién ahí re-corré el backfill.
- **Juicio de triage todavía en `build/`** (bóveda ingestada antes de 1.9.0, migración one-shot;
  el lint **sí** lo surface y **bloquea** —`legacy_triage`, ver el bullet de arriba—) → consolidarlo en el
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
  `python scripts/query_ads.py <slug> --rows 2000  # ⚠ el cliente NO pagina: 2000 es ≈ el máximo de una request ADS, pedir más no trae más` y luego `python scripts/ingest_star.py <slug>`. Mientras tanto, la ficha afirma sobre un universo recortado.
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

## F. Pasada periódica de RED (bóveda completa) — `sweep_external.py`

⚠ **El comando es `python scripts/sweep_external.py`**, no `check_retractions.py` solo. **Seis** cosas
caducan después de un ingest —cinco desde 1.35.0, la sexta desde 1.46.0— y la pasada unificada
existe justamente porque, repartidas, se corren cinco y la sexta nunca:

| Detector | Qué caza | Estado |
|---|---|---|
| retracciones | fuente retractada (Crossref) | ✅ |
| correcciones | erratum / corrigendum / EoC | ✅ |
| versiones | el preprint salió publicado → otro bibcode del mismo trabajo (D-19) | ✅ |
| ground-truth | NEA cambió valores entre releases | ✅ |
| snapshot web | la URL citada cambió | ✅ (1.35.0) — el **más silencioso**: una fuente web no tiene DOI ni bibcode, y como el `.txt` local **no** se toca, el ancla de fuente tampoco se entera |
| citas-puerta2 | un paper cruzó el `fundacional_min_citas` del tema → sería core (o dejaría de serlo) sin que nadie editara nada | ✅ (1.46.0) — la única metadata que **cambia sola** y admite core. Su gemelo **offline** lo reporta el lint (`puerta2_cruces`): ése ve *«editaste el umbral»*, éste ve *«el mundo se movió»* |

⛔ **Reporta, no aplica sola**: muestra el diff y pregunta. Un snapshot que se actualiza solo cambia
valores **bajo los pies de la prosa que ya los citó**. El renombre preprint→publicado **nunca** es
automático (reescribe wikilinks de toda la bóveda): se propone el comando.

La caducidad queda **versionada** en `vault/config/registro/_red.yaml` — cuándo se miró afuera es
información de la bóveda, no de la máquina. Un detector que no pudo correr **no** entra en `cubrio`.

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

## G. Pasada periódica de REVALIDACIÓN (a pedido) — modo revalidación de `verify-citations`

Complementa la pasada F. Aquélla mira lo que cambió **afuera** (retracciones, correcciones,
versiones, snapshot web, ground-truth); ésta mira lo que puede haber estado mal **desde el
principio** sin que nada cambiara.

**Por qué hace falta.** El ancla de bloque y el hash de fuente detectan que un par **cambió**. Si
nada cambió, el par no se vuelve a mirar **nunca** — así que un error del verificador queda
**permanente y silencioso**, que es el modo de falla que esa capa existe para no producir. El
supuesto implícito («el veredicto es función de la afirmación y la fuente») nunca se midió, y lo
produce un LLM.

Se pide en prosa —«revalidá una muestra de las citas»— y corre el **modo revalidación** del skill
`verify-citations`, sobre una muestra (no todo el corpus: el punto es que sea barato y periódico).

Re-corre el fan-out sobre pares **ya verdes**, con verificadores ciegos a la tabla vigente, y
reporta la **divergencia**. Los pares que cambian de veredicto se resuelven como cualquier hallazgo;
el bloque **no se reescribe en silencio**.

Medido el 2026-08-25 (HD 40307, 60 pares, dos corridas): **95 % de coincidencia**, con un confound
declarado en el skill. El dato que más importa: pares con **veredicto idéntico** trajeron
**condiciones distintas** — el juez es estable en el eje textual y **no exhaustivo** en el de
régimen.

## Notas
- **No es ingest:** si la entidad no existe todavía, esto no aplica → `ingest-star`/`ingest-theme`.
- **No es query:** una pregunta puntual va por `query-corpus`; acá se **modifica** la bóveda.
- Schemas de frontmatter, reglas de ruta y disputas: ver `CLAUDE.md`. `git add` **específico** (no `-A`).
