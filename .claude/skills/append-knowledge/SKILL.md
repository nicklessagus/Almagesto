---
name: append-knowledge
description: Usar cuando el usuario quiere plegar UNA fuente puntual (paper por bibcode, PDF local, URL) a una entidad YA existente de la wiki — ficha de estrella o concepto — sin re-correr el ingest completo ("agregale este paper a la ficha de tau Ceti", "sumá este PDF al concept de procesos gaussianos", "este bibcode va a GJ 581", "encontré un paper nuevo para el tema X, agregalo"). Plomería mínima + extracción enfocada + síntesis a la nota viva + cierre estándar. NO crea entidades (eso es ingest-star/ingest-theme) ni barre por query lo nuevo (eso es maintain/refrescar).
version: 1.6.0
---

# Append — plegar una fuente puntual a una ficha o concepto existente

Operación **incremental** del patrón LLM Wiki (ver `CLAUDE.md`): el usuario trae **una fuente
concreta** (bibcode ADS, PDF, URL) y una **entidad destino que ya existe**. Encapsula lo que antes
se hacía a mano (p. ej. ampliar un radio de un concepto con 2 papers — copiar PDF, extract, stub,
extracción, síntesis, verify, lint). Trabajar desde la raíz del repo.

**Fronteras:** la entidad destino **debe existir** (ficha en `vault/wiki/stars/` o concept en
`vault/wiki/concepts/`) — si no existe, esto es un `ingest-star`/`ingest-theme`. Si el pedido es
"traé lo NUEVO de X" (barrido por query), es `maintain` (sub-modo A, refrescar). Un **dato suelto
sin fuente citable no entra** (frontera dura, regla #0): pedir la fuente; si es conclusión derivada
de fuentes ya citadas, entra marcada como tal.

## Pasos

**Copiá este checklist al chat al arrancar y andá tildándolo** — el cierre (5) concentra los pasos
salteables, y ampliar una nota ya verificada deja su bloque stale si no se re-corre el verify:

```
Progreso del append de <fuente> → <destino>:
- [ ] 1 destino confirmado + tipo de fuente clasificado
- [ ] 2 plomería mínima (extra_core / sources: / piezas sueltas) — fulltext extraído
- [ ] 3 extracción LLM enfocada en el eje del destino (= la VISTA del destino, #188)
- [ ] 4 síntesis a la nota viva (regla de poda; disputes con posiciones / régimen si es concepto)
- [ ] 5 cierre: autosuficiencia → `contrast.py <slug> --validar-todo` (#323) → verify-citations (re-fechar el bloque) → lint 0 → log → commit
```

1. **Resolver destino y tipo de fuente.** Confirmar que la nota destino existe y clasificar la
   fuente: (i) **bibcode ADS** (con o sin PDF propio), (ii) **PDF sin bibcode ADS** (off-ADS →
   clave sintética `AAAA+Autor`), (iii) **URL** (off-ADS → snapshot web). El slug es el de la
   entidad destino (`stars.yaml`/`themes.yaml`).

2. **Plomería mínima** (por tipo; todo idempotente — con el retro-linkeo de `make_notes`, si la
   nota del paper ya existía en el corpus los seeds `stars`/`thesis_links` se mergean add-only
   solos, sin pisar su extracción):
   - **(i) bibcode ADS** → agregarlo a `extra_core:` (lista de mapas `{bibcode, via, motivo[, fecha]}` — D-58, `fecha` opcional; el `triage` imprime el snippet listo para pegar) en la entrada de la entidad
     (`vault/config/stars.yaml` o `themes.yaml` — curación **persistente**, sobrevive re-runs) y
     correr la cadena: estrella → los scripts del paso 2 de `ingest-star`; tema →
     `python scripts/ingest_theme.py <slug>`. `query_ads` lo trae por bibcode con el `via`
     declarado en la config y `puertas: [manual]` (#303; `via: manual` ya no se escribe).
     ⚠ La cadena re-corre también la query → puede traer **otros** papers nuevos (refresh
     implícito): si aparecen stubs extra, hacé su extracción (maintain A) o anotalos como backlog
     en `vault/STATUS.md` — no los dejes mudos. Dos compuertas que ese refresh puede disparar y
     conviene esperar: (a) la **guardia de expansión** (#37) **aborta** la cadena si el core se
     multiplicó (×1.5 y 50 o más nuevos) — mirá el conteo antes de continuar con `--yes`, no lo
     pases de taquito; (b) el chaining deja **candidatos sin juzgar** en `candidates`, que el lint
     surface como *Triage pendiente* (#55): resolvelos con `python scripts/triage.py <slug>` o dejá
     el conteo en el `log`, para no cerrar el append con juicio pendiente mudo.
     Si el paper no tiene arXiv (paywall/viejo) y el resolver de ADS tampoco lo entrega (queda en
     `build/<slug>/missing_pdf.json`, con `bibstem` y `hint`), seguí la **cascada manual de rescate**
     de `## Notas` del skill `ingest-star` antes de pedirlo. Con el PDF en mano (rescatado o provisto
     por el usuario): copiarlo a `vault/raw/pdfs/<slug>/<bibcode>.pdf` y correr
     `python scripts/extract_fulltext.py <slug>`.
   - **(ii) PDF off-ADS** a un tema con `source` off-ADS → agregar el item a `sources:` de la
     entrada del tema (`key` + `pdf` + metadata) y `python scripts/ingest_theme.py <slug>` (sólo
     procesa lo nuevo; deja nota con `pdf` linkeado y fulltext extraído).
     ⛔ **La metadata (`key`, `author`, `title`, `year`, `doi`) sale del documento, no de memoria
     (#392):** `pdftotext -f 1 -l 1 <pdf> -` antes de escribir el item, y el `.bib`/`.xlsx` que
     haya al lado del PDF se lee primero. Si tiene DOI, `python scripts/check_sources.py <slug>`
     lo cruza al ingestar; una `url:` se declara con el `<title>` del snapshot, no con lo que uno
     recuerda del sitio.
   - **(iii) URL** a un tema off-ADS → ídem con `url` en `sources:` + `ingest_theme.py`.
   - **(ii)/(iii) puntual a un tema ADS o a una estrella** (fuente off-ADS aislada, sin cambiar el
     `source` de la entidad) → usar las piezas sueltas: `python scripts/fetch_web.py <slug> <key>
     <url> --concept <concept> …` (URL), o copiar el PDF a `vault/raw/pdfs/<slug>/<key>.pdf` +
     `extract_fulltext.py <slug>` + `python scripts/make_notes.py --web <key> --slug-hint <slug>
     [--concept <concept>] --title … --author … --year …` (PDF). Para una **estrella** no hay seed
     automático: completar `stars: [<nombre>]` en el frontmatter de la nota durante la extracción.

3. **Extracción LLM enfocada en el eje del destino.** Leer SÓLO la fuente nueva — **el PDF**
   (`vault/raw/pdfs/<slug>/<clave>.pdf`, #205), ubicando con `grep -n` sobre su `.txt` en qué parte
   mirar y citando **página** — y poblar la
   nota del paper: `methods`, `role` (#73: `fundacional` introduce el método/mecanismo · `aplicacion` lo instancia en un caso · `arbitro` reanaliza y resuelve una tensión previa — sale de leer el paper, la regex del clasificador no puede inferirlo, y sin él contrastarlo contra otro no está definido), `thesis_links`/`stars`, y **la vista del destino** (#188): la entrada en `vistas[]`
   (`{sujeto, tipo, fecha, txt, lente, fuente}` — el `sujeto` es la entidad destino; `fuente: pdf|abstract`, #207) y su sección
   `## Vista — <sujeto>`, orientada a **lo que aporta a la entidad destino** (una señal RV, un mecanismo, una ecuación del
   método), no un resumen genérico.

4. **Síntesis a la nota viva — INTEGRAR EN SU LUGAR (D-31).** Plegar a la ficha/concept **sólo lo
   que cambia la lectura**, reescribiendo **los bloques afectados donde están**. Los dos extremos
   están descartados:
   - ⛔ **Sección nueva: no.** `## Resumen` + `## Actualización 2026-09` + `## Actualización 2026-11`
     deja de ser un snapshot, y una contradicción queda **sentada al lado de lo viejo sin resolver**
     — justo lo que la ficha existe para evitar.
   - ⛔ **Re-validar todo: no.** Un paper que habla del `P_rot` no justifica re-verificar las 40
     citas del inventario de señales.

   **Procedimiento:** extraer → identificar **qué ejes toca** → por cada eje comparar contra lo que
   la nota ya dice (*coincide* → nada, o fila en el inventario · *agrega* → prosa citada ·
   *contradice* → fila en `## Inventario por eje` + `disputes[]`) → reescribir esos bloques en su
   lugar.

   **La contabilidad la hace sola la maquinaria de anclas:** los bloques que tocaste cambian de
   hash, así que esos pares quedan marcados como vencidos y se re-verifican **sólo ésos**. No hay
   que decidir "¿todo o nada?" — el hash dice qué se movió.
   ⚠ **Antes de la prosa, mirá el `## Inventario por eje` (#72):** si la fuente nueva reporta un eje
   que ya está inventariado, **agregá su fila** —es lo que evita re-derivar la síntesis desde cero—;
   si aporta un valor que **discrepa** de otro paper sobre un eje que todavía no está, ése es el
   momento de abrir el eje. Si la nota no tiene inventario, armalo con los papers en juego. Rige el
   ⛔ de siempre: **sin columna "valor adoptado"**, y `role` (#73) antes de leer dos filas como
   desacuerdo (fundacional↔aplicación es instanciación, no contraste).
   - **Ficha de estrella:** rige la **regla de poda** de `CLAUDE.md` (un paper tangencial entra a
     la prosa únicamente si cambia cómo se lee una señal RV). Si discrepa del ground-truth NEA →
     `disputes` a nivel nota con posiciones explícitas (#71; no sobreescribir). Actualizar `## Huecos` y la
     matriz método×estrella si el paper aplica un método nuevo a la estrella.
   - **Concept:** integrar al eje del tema (mecanismo, rango, paso del método) citando
     `[[clave]]`; actualizar `## Huecos`. Si es un radio de un hub, tocar el radio que corresponda
     (y el hub sólo si cambia la síntesis global). **Si la fuente afirma bajo condiciones**, la fila
     va al **`## Régimen de validez`** (#74) —no a la prosa pelada—: agregar una fuente es
     exactamente cuando se generaliza de más, y ése es el modo de falla que `verify-citations`
     devuelve `soportada` (la afirmación sin condiciones sí está en el paper). Si discrepa de otra
     fuente **sólo por el régimen**, es una fila de esa tabla y **no** una `disputes`.

4b. **Contradicciones en los ejes tocados (D-39).** Antes del cierre, correr `find-contradictions`
   **acotado a los ejes que la fuente nueva tocó** — no al corpus entero. El paso 4 compara la fuente
   nueva contra **lo que la nota dice**; esto compara **paper contra paper**, y agarra el caso que
   aquél no ve: dos papers que discrepan sobre un eje que la nota nunca mencionó (porque la poda lo
   descartó, o porque nadie lo notó). Es barato: el embudo corre sobre las extracciones.

5. **Cierre estándar** (idéntico a ingest): **auto-revisión de autosuficiencia** de la nota destino
   (¿se entiende sin abrir el paper nuevo?) → **`python scripts/contrast.py <slug> --validar-todo`**
   (#323: el chequeo barato antes del caro — bloquea la cita que aparece verbatim bajo otro bibcode
   o cuya cola diverge; el silencio de la extracción no es hallazgo, #321) → **`verify-citations`** sobre la prosa tocada y la
   nota de paper nueva —si la nota destino ya traía bloque `## Verificación de citas`, **re-fechar
   el encabezado**: el lint compara esa fecha contra la del último cambio del archivo y marca
   **verificación stale** si quedó atrás (#56)— → `python scripts/lint.py --cierre <slug>` en 0 (R-1: en el cierre de una operación, un par de verificación vencido frena; sin el flag sólo reportaría. #121: con el slug de la entidad destino, la deuda de otro sujeto se reporta pero no frena) → bookkeeping (`vault/wiki/log.md` SIEMPRE —
   entrada `append: <fuente> → <destino>`; `vault/wiki/index.md` y `vault/STATUS.md` sólo si cambió
   algo catalogable/de estado) → `git add` de archivos específicos + commit → **preguntar antes de
   `push`**.

## Notas
- Distinción de operaciones: `query-corpus` responde sin persistir; `test-hypothesis` persiste sólo
  hipótesis; `maintain A` barre por query lo nuevo; **append** pliega una fuente que el usuario ya
  identificó. Si durante un append aparecen más papers que valdría traer, proponerlo como refresh —
  no colarlos en silencio.
- Reglas de notación, schemas de frontmatter, clave sintética `AAAA+Autor` y frontera dura: ver
  `CLAUDE.md` y el Modo off-ADS de `ingest-theme`.
