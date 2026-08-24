# Plan de implementación de las 58 decisiones (2026-08-23)

Traduce a tandas e issues las decisiones de `docs/revision-contrato-2026-08-23.md` (D-1…D-58),
con las cuatro previas ya resueltas en `docs/reconciliacion-2026-08-23.md` §4. No implementa nada:
es el plan. Cada issue se trabaja **de a uno, con resultado a la vista y aprobación del usuario**
antes del siguiente (protocolo de `vault/STATUS.md`).

**Reglas que gobiernan todo el plan (no se repiten en cada issue):**

- **TDD rojo-primero.** Test → verificar rojo → implementar → verde. Para features nuevas el rojo
  es **de comportamiento**: primero el stub que devuelve algo trivial (la tabla vacía, el hash sin
  normalizar, el exit code viejo) y el test cae por lo que la función *hace*, nunca por
  `ImportError` — el repo ya se comió ese falso rojo 7 veces (STATUS, *Protocolo de fixes*).
- **Sin migración de instancia** (reconciliación §4.1): se arma bóveda nueva, Almagesto-RV queda de
  referencia. Las rutas de migración de D-1, D-2, D-17, D-21 y D-37 **no se escriben**. Los
  **detectores** de schema viejo sí se escriben (y el generador `vintage` de `tests/poblada/` los
  prueba): schema nuevo = detector bloqueante, nunca lector tolerante.
- **Tests completos verdes antes de cada commit** (tier 0 siempre; tier 1 al cerrar cada tanda que
  toque el lint o el generador). Bump de `ALMAGESTO_VERSION` + tag al cerrar cada tanda; release de
  GitHub sólo en minor/major.
- Los tests nuevos respetan el presupuesto: tier 0 ≤ 2,5 s (nada que duerma, nada que siembre
  cientos de notas — eso va a `tests/poblada/` con marker `poblada`).
- Cada issue nombra el invariante de `docs/contrato.md` §3.K que cierra (o dice que no cierra
  ninguno). Al cerrar el issue, la fila del invariante pasa de HUECO a *garantizado y medido* con
  el instrumento nombrado (contrato §7).

---

> ⚠ **LEER ANTES DE SEGUIR (agregado 2026-08-24).** Este documento está **fechado** y se conserva
> como está: es el registro de lo que se planificó. Pero las tandas **0 a 6 ya se ejecutaron** y en
> el camino se resolvió **R-5**, que renombró un concepto. Las tandas 7–10 de abajo usan los nombres
> **viejos**; traducí al leer:
>
> | El plan dice | Hoy se llama |
> |---|---|
> | `relevance.topics` · campo `topics:` de las notas | `relevance.facets` · `facets:` |
> | `topics.yaml` | `themes.yaml` |
> | `ingest_topic.py` · `--topic` · skill `ingest-topic` | `ingest_theme.py` · `--theme` · `/ingest-theme` |
> | `load_topics` · `topic_by_slug` | `load_themes` · `theme_by_slug` |
>
> El estado real y el próximo paso están en **`vault/STATUS.md`, sección *DÓNDE RETOMAR***, que es
> la fuente de verdad — no este documento.


## 1. Orden global por dependencias

El esqueleto de la reconciliación §5 era:
`check_retractions` exit 1 → ancla D-4/D-20 → índice de citas D-27 → resto de C → los 24 de B →
dashboard. **Validado contra el código, se corrige en cuatro puntos:**

1. **D-53 (helper atómico) sube al principio, junto al fix de exit codes.** El esqueleto lo dejaba
   entre "los 24 de B", pero casi todas las tandas posteriores **agregan writers** (tabla de papers,
   bloque de estado, columna de anclas, `versions[]`, estampado de pasos). Hacer el helper último
   significa retrofitear cada writer nuevo; hacerlo primero significa que nacen atómicos. Además
   `save_registro` (`lib_config.py:379`) y `check_retractions._write_atomic` ya son dos
   implementaciones paralelas del mismo tmp+`os.replace`: el barrido de clase (STATUS, corolario de
   la 6ª pasada) pide helper único, no un tercer clon.
2. **El registro acumulativo (D-28/D-57) va ANTES del bloque de estado (D-12) y de la
   materialización (D-10).** `make_notes.search_line()` lee `busqueda` del registro para la
   cabecera; D-28 convierte `busqueda` (mapa único, `save_busqueda` lo **pisa** en cada corrida) en
   `busquedas: []` (lista con nuevos/ya-estaban). Si D-12 se escribe primero contra el schema viejo
   del registro, hay que reescribir la cabecera dos veces. Mismo argumento para D-58 (la forma
   estructurada de `extra_core` alimenta la columna `Origen` de D-10).
3. **D-1/D-2 (autoridad del ground-truth) van ANTES de la pasada de red (D-45).** El `nea_diff` de
   D-45 compara contra el snapshot campo por campo; si la autoridad de `spectral_type` cambia
   después, el diff se escribe dos veces y sobre un JSON cuyo layout cambió (campo de auditoría
   nuevo). Son el mismo archivo (`fetch_ground_truth.py`): tocarlo una vez con la precedencia final.
4. **El índice de citas (D-27) NO bloquea a nada fuera de su carril.** La única dependiente es la
   puerta 1 de D-26 (y el chaining mejorado). El esqueleto lo ponía segundo por prioridad, no por
   dependencia: leído el código, nada del carril de notas/registro/lint lo necesita. Se mueve
   detrás de la pasada de red para que las tandas que comparten archivos queden contiguas. Si el
   usuario prefiere el carril de descubrimiento antes, se puede adelantar la tanda 7 completa sin
   invalidar nada (es ortogonal a 2–6).

**Orden final** (validado leyendo `lint.py`, `make_notes.py`, `query_ads.py`,
`fetch_ground_truth.py`, `check_retractions.py`, `lib_config.py`, `triage.py`, `ingest_star.py`,
`ingest_topic.py`):

| Tanda | Qué | Tamaño |
|---|---|---|
| 0 | Preliminares: exit codes, helper atómico, "no evaluado", lente vacía · + medición D-51 | media |
| 1 | **El ancla** (D-4/D-20/D-5) — la pieza central | grande |
| 2 | Registro acumulativo y escotillas (D-28, D-57, D-48, D-52, D-58-config) | media |
| 3 | Materialización y estado de la ficha (D-10, D-24, D-22, D-12, D-54, D-13/D-15-lint, T-3) | grande |
| 4 | Autoridad por campo del ground-truth (D-1, D-2) | chica |
| 5 | Identidad y artefactos (D-19, D-18) | media |
| 6 | Pasada de red unificada (D-41, D-45, D-46, D-47) | grande |
| 7 | Descubrimiento (D-25, D-27, D-26+D-58-via, D-29, D-30) | grande |
| 8 | Los B de lint/schema restantes (D-17, D-49, D-42, D-37, D-21-detector, D-50, D-56, D-23, D-32, D-55) | media-grande |
| 9 | Skills y doc (los 7 de A + los B de skill: D-7, D-8, D-13/D-14, D-15, D-21, D-29, D-31, D-33–D-40, D-42-doc, D-50-doctrina) | media |
| 10 | Dashboard (T-4) + cierre de la suite poblada | media |

---

## 2. Tanda 0 — Preliminares

**Cubre:** cola #4 y #5 de STATUS, D-53, D-43, D-6. **Cierra:** INV-90, INV-87, INV-80.
**Toca:** `check_retractions.py`, `ingest_star.py`, `lib_config.py`, `lint.py`, `query_ads.py`,
`make_notes.py`, `fetch_ground_truth.py`.
**Por qué acá:** los tres son infraestructura de la que cuelga el resto — el exit code bloquea a
D-45 (reconciliación §1.3), el helper atómico a todo writer nuevo, y "no evaluado" + lente vacía
definen el patrón de severidad que las ~10 categorías nuevas de lint van a seguir.

### Issue 0.1 · `check_retractions`: el exit 1 deja de estar sobrecargado

Hoy `slug_notes()` hace `sys.exit(str)` (exit 1) cuando no hay nada que chequear, y
`main()` devuelve 1 sólo con retractados — pero `ingest_star.py:66-67` traduce **cualquier** rc≠0 a
"detectó papers retractados". Con D-45 esa misma pasada cubre cinco eventos: el código ambiguo se
arregla **antes** de apoyarle una feature encima.

- **Contrato nuevo de salida:** `0` = corrió y limpio · `1` = corrió y detectó retractados ·
  `2` = **no pudo chequear** (precondición ausente: sin `ads.json` del slug, sin notas; o errores
  que dejaron papers sin chequear y ningún retractado). Retractados mandan: si hay retractados Y
  errores, sale 1 con los errores en el reporte.
- **Funciones:** `check_retractions.main() -> int` (ramas de salida); `slug_notes(slug) -> list`
  deja de matar el proceso: levanta una excepción propia (`NothingToCheck(RuntimeError)`) que
  `main()` traduce a exit 2 con el mensaje actual. `ingest_star.main()` distingue rc 1 ("retractados
  — revisá las notas") de rc 2 ("el chequeo no pudo correr — la cadena no certifica lo que no miró",
  aborta igual pero con el mensaje honesto).
- **Tests (antes, rojos):**
  - `test_exit_2_sin_nada_que_chequear` — slug sin `ads.json` ni entrada en topics → **hoy sale 1**:
    el test espera 2. Adversario directo del overload.
  - `test_exit_1_solo_con_retractados` — retractado sembrado → 1; sin retractados y sin errores → 0.
  - `test_errores_sin_retractados_exit_2` — Crossref que revienta en el único paper → hoy 0 ("no
    encontré retractados") con el chequeo sin correr: el falso limpio que D-43 prohíbe.
  - `test_ingest_star_distingue_rc2` — con `run` grabador devolviendo 2, el mensaje NO dice
    "detectó papers retractados" (hoy lo dice: rojo).
- **Aceptación:** los cuatro verdes; `test_check_retractions.py` e `test_ingest_star.py` existentes
  siguen verdes. No cierra INV de §3.K (habilita INV-85).

### Issue 0.2 · D-53: helper atómico único (`INV-90`)

- **Funciones:** `lib_config.write_text_atomic(path: Path, text: str, *, encoding="utf-8") -> None`
  — tmp en el **mismo** directorio + `os.replace`, con `try/finally` que borra el temporal si el
  fallo ocurre **antes** de publicar (cierra la cola #5, el `.tmp<pid>` huérfano). Migrar los
  writers a él: `save_registro` (conserva su guardia de no-pisar-ilegible), `write_ground_truth`,
  `check_retractions._write_atomic` (se borra, queda el helper), y **todas** las escrituras de notas
  de `make_notes.py` (`dest.write_text(...)` en stubs, stampers, migradores) — el writer que más
  escribe y el único no atómico. `fetch_arxiv.write_pdf_atomic`/`fetch_pdf.write_pdf_atomic`
  (binarios) se unifican en `lib_config.write_bytes_atomic(path, data) -> None`.
- **Tests (antes, rojos):**
  - `test_fallo_en_replace_no_corrompe` — monkeypatch de `os.replace` que revienta: el archivo
    original queda byte-idéntico y **no queda `*.tmp*`** en el directorio (hoy `save_registro` deja
    el original sano pero el issue es el temporal: verificar limpieza).
  - `test_fallo_escribiendo_el_temporal_no_deja_basura` — `write_text` del tmp revienta → sin
    huérfanos. **Rojo hoy** contra `save_registro` (escribe el tmp sin try/finally alrededor).
  - `test_notas_pasan_por_el_helper` — monkeypatch de `write_text_atomic` con grabador: crear un
    stub de estrella + estampar cabecera → **todas** las escrituras a `vault/wiki/` pasaron por el
    helper (rojo por construcción: el helper no existe, el stub trivial escribe directo).
  - Inyección de fallo por comando (patrón de la 8ª F4) para `make_notes <slug>`: matar en medio →
    la nota previa intacta. Va a `tests/poblada/test_upgrade.py`-style si no entra en el tier 0.
- **Aceptación:** INV-90 pasa a *garantizado y medido*; `grep` de `write_text(` sobre `scripts/`
  no encuentra escrituras directas a `vault/` fuera del helper.

### Issue 0.3 · D-43 + D-6: "no evaluado" reporta error; la lente vacía rehúsa

Los dos juntos porque comparten el mecanismo: una categoría de lint que dice *"esto no se miró"* con
exit ≠ 0, en vez de un cero inventado.

- **Funciones:**
  - `lib_config.objective_error() -> str | None` — distingue tres estados que hoy `load_objective`
    colapsa: archivo ausente (ya es `RuntimeError`), **YAML que no parsea / no-mapa → devuelve el
    motivo** (hoy `lib_config.py:185-187` degrada a `{}` mudo), sano → `None`. `load_objective`
    no cambia de firma (sus llamadores tolerantes siguen); los estrictos consultan el error.
  - `query_ads`: al armar la lente (`_OBJ`/`_REL` a nivel módulo — mover a lazy o chequear en
    `main()`), si `objective_error()` → `sys.exit` nombrando archivo y motivo. **Nunca clasifica
    con `{}`.**
  - `lint.main()`: lista `not_evaluated: list[tuple[str, str]]` + categoría
    `⛔ No evaluado: el chequeo no pudo correr` que **cuenta para el exit ≠ 0**. Pobladores
    iniciales: (a) `objective_error()` (D-6); (b) `git_out()` devolviendo `None` con
    `verif_blocks` no vacío (hoy `last_change_dates` → `{}` y `stale=0` en silencio); (c) el
    registro ilegible ya reportado se re-etiqueta bajo esta semántica donde corresponda.
- **Tests (antes, rojos):**
  - `test_lint_objective_roto_bloquea` — `objective.yaml` con `topics: {rv: foo:bar}` (el `:` sin
    comillas, el error más probable) → **hoy exit 0**: esperar exit ≠ 0 y la línea en el **archivo
    de reporte** (nunca stdout — corolario del protocolo).
  - `test_query_ads_rehusa_lente_vacia` — misma config: `main()` sale con mensaje que nombra
    `objective.yaml`; `classify` no llegó a correr (grabador).
  - `test_lint_sin_git_reporta_no_evaluado` — nota con bloque de verificación + `git_out`
    parcheado a `None` → hoy 0 hallazgos stale y silencio: esperar categoría "no evaluado" y
    exit ≠ 0.
  - `test_no_evaluado_no_contamina_conteos` — el chequeo que no corrió NO aparece como "(0)" en su
    categoría normal (adversario: el cero inventado).
- **Aceptación:** INV-80 e INV-87 medidos. Documentar en el reporte del lint que "no evaluado" es
  hecho del **entorno** (`outputs/`, no versionado — D-43).

### Issue 0.4 · D-51: medir el umbral de legibilidad (tarea de **medición**, no de implementación)

Correr `extract_fulltext.is_legible` (umbral actual: ratio 0,85 / 200 chars / 200 por página) sobre
los **672 fulltexts reales** de `/home/agus/…/Almagesto-RV/vault/raw/fulltext/` (read-only),
tabular ratio y densidad por archivo, revisar a mano los que caen cerca del corte (falsos positivos
y negativos) y **sacar el número**. Herramienta descartable en el scratchpad, resultado (tabla +
número propuesto) a STATUS. Si la medición justifica mover el umbral, ESO es un issue aparte con su
test rojo (`test_is_legible` fija los umbrales hoy). Puede correr en paralelo con cualquier tanda:
no toca código. Cierra §6 #7 del contrato como estaba previsto.

---

## 3. Tanda 1 — El ancla (D-4 + D-20 + D-5)

**Cubre:** D-4, D-20, D-5, el hallazgo §3.3 de la revisión (plantilla del bloque ≠ instancia).
**Cierra:** INV-78 (P0, pieza central), INV-79 (la mitad detectable en frío).
**Toca:** módulo nuevo `scripts/lib_blocks.py`, `lint.py`, skill `verify-citations`, `CLAUDE.md`.
**Por qué acá:** de ella dependen D-31 (refresh dirigido), D-41/D-45 (marcar pares al cambiar la
fuente), D-12 (la fecha de verificación con su salvedad "por par") y D-39. Es el camino crítico.

### Issue 1.1 · Partición en bloques + los dos hashes (`lib_blocks.py`)

Módulo nuevo, importable por lint, bench y el equivalente determinista del skill (no inline en
`lint.py`: lo consumen al menos tres lectores).

- **Funciones:**
  - `split_blocks(body: str) -> list[Block]` — `Block = (kind, first_line, text, intro)`;
    `kind ∈ {parrafo, fila, item, blockquote}`; `intro` = el bloque que introduce una fila/ítem sin
    cita propia (caption / párrafo / encabezado — la herencia ya definida en `CLAUDE.md`). El bloque
    `## Verificación de citas` **se excluye** de la partición (se excluye de su propio hasheo).
  - `normalize_ws(text: str) -> str` — colapsa runs de whitespace (reflowear no mueve el hash;
    cambiar un número sí).
  - `block_anchor(text: str, intro: str | None = None) -> str` — sha256 sobre el texto normalizado
    (con herencia: los **dos** bloques), truncado a 10 hex.
  - `source_hash(path: Path) -> str` — sha256 del `.txt` leído, 10 hex.
  - `pairs_of(body: str) -> list[Pair]` — `(bibcode, block, anchor)` por cada cita `[[bibcode]]`;
    un párrafo con 3 citas da 3 pares con la misma ancla (sobre-disparar es correcto).
- **Tests (antes; el stub trivial hashea el texto SIN normalizar y sin herencia, para que caigan
  por comportamiento):**
  - `test_reflow_no_mueve_ancla` — el mismo párrafo hard-wrapped a 80 y a 100 columnas → mismo
    hash. **Es EL caso adversario de la granularidad elegida** (por línea fue descartada por esto).
  - `test_cambiar_numero_mueve_ancla` — `K=2.5` → `K=2.6` en el párrafo → hash distinto.
  - `test_fila_hereda_el_caption` — editar el caption de una tabla cambia el ancla de sus filas
    sin cita propia; editar una fila NO cambia el ancla de las otras.
  - `test_tres_citas_un_bloque_tres_pares_misma_ancla` — sobre-disparo, nunca sub-disparo.
  - `test_bloque_de_verificacion_no_genera_pares` — sus filas llevan `[[bibcode]]` y NO son pares.
  - `test_source_hash_estable_ante_bytes_identicos` + cambia con un byte.

### Issue 1.2 · El bloque de verificación: un par por fila, con las dos columnas de hash

- **Forma** (plantilla del skill + parser): tabla
  `| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente |`, encabezado
  `## Verificación de citas (AAAA-MM-DD)` (la fecha ya la exige el lint). La instancia real hoy
  colapsa las soportadas en prosa (`tau_ceti.md:133`): la plantilla del skill pasa a exigir fila
  por par — sin filas no hay dónde colgar el ancla.
- **Funciones:**
  - `lib_blocks.parse_verif_table(text: str) -> list[Row] | None` — `None` si el bloque existe
    pero no tiene las columnas de hash (**detector de plantilla vieja**; sin migrador: bóveda
    nueva. La "migración gratis" descrita en D-4 no se escribe — no hay instancia que migrar).
  - `lint.py`: categoría nueva **"Pares de verificación vencidos"** — por nota con bloque:
    recalcular `pairs_of(body)` y comparar contra la tabla. Sub-casos con mensaje propio:
    (a) par del cuerpo sin fila → *sin verificar*; (b) fila cuya `Ancla` ≠ recálculo → *vencido
    por edición*; (c) fila cuyo `Hash fuente` ≠ `source_hash` del `.txt` vigente → *vencido por
    fuente*; (d) fila sin par en el cuerpo → *fila huérfana* (la afirmación se borró); (e) bloque
    sin columnas → *plantilla vieja* (detector, bloqueante).
  - **Costo:** `source_hash` exige leer cada `.txt` — el lint **ya los lee todos** para
    `is_legible` (77% de los 5,6 s): una sola lectura alimenta los dos chequeos (pasar el texto ya
    leído, no el path). Cero lecturas extra; el hashing (~66 MB de corpus) es marginal frente al
    parseo YAML. Anclar en `tests/poblada/test_escala.py` (ver tanda 10).
  - **Severidad, dos momentos:** propuesta `lint.py --cierre` (flag nuevo: los "pares vencidos"
    cuentan para el exit; sin el flag, reportan como backlog — la pasada periódica de D-4). Los
    skills de cierre corren `lint.py --cierre`. ⚠ Esto es **propuesta del plan, no decisión del
    usuario** — ver §Riesgos R-1. D-44 queda intacto: el commit nunca se frena.
- **Tests (antes, rojos):**
  - `test_par_nuevo_sin_fila_marca` — agregar una frase citada a una nota verificada → 1 hallazgo,
    ese par.
  - `test_edicion_marca_solo_sus_pares` — nota con 3 bloques citados, editar uno → sólo sus pares
    en el reporte (adversario: invalidación por sección, descartada en D-4).
  - `test_reflow_no_marca_nada` — re-wrapear la nota entera → 0 hallazgos.
  - `test_reemplazo_del_txt_marca_por_fuente` — tocar el `.txt` sin tocar la nota → los pares de
    ese bibcode, y sólo esos, marcados *por fuente* (INV-78, la mitad D-20).
  - `test_bloque_sin_columnas_de_hash_detectado` — plantilla vieja → bloqueante con mensaje.
  - `test_cierre_bloquea_periodica_reporta` — mismo sembrado, exit distinto con/sin `--cierre`.
- **Aceptación:** INV-78 medido con los cuatro experimentos que el contrato nombra. INV-79 queda
  medido en su mitad determinista (la mitad "la operación no se declara cerrada" es conducta de
  skill, tanda 9).

### Issue 1.3 · D-5 + plantilla: la ficha nace 100% verificada

Capa skill/doc (sin test de código; la red determinista es 1.2): `verify-citations` escribe el
bloque completo con anclas al crear la nota; `CLAUDE.md` y el skill documentan que "sin verificar"
sólo puede aparecer después, por edición. La verificación stale por fecha de git (#56) **se
retira** como mecanismo principal (las anclas la reemplazan con granularidad de par) pero queda
como red para notas con bloque y sin tabla parseable. Actualizar la fila de #56 en la doc.

---

## 4. Tanda 2 — Registro acumulativo y escotillas

**Cubre:** D-28, D-57, D-48, D-52, D-58 (parte config). **Cierra:** INV-89, INV-91; extiende
INV-51. **Toca:** `lib_config.py`, `query_ads.py`, `triage.py`, `ingest_topic.py`,
`ingest_star.py`, `make_notes.py` (search_line), `lint.py`.
**Por qué acá:** el schema del registro tiene que quedar quieto **antes** de que la tanda 3 escriba
la cabecera/bloque de estado que lo lee (corrección 2 del orden).

### Issue 2.1 · D-28: `busquedas` es una lista; el embudo no se suma

- **Funciones:** `lib_config.save_busqueda(slug, busqueda)` pasa a **appendear** a
  `busquedas: []` (una entrada por corrida). `query_ads.main()` calcula y agrega a la entrada
  `n_nuevos` / `n_ya_estaban` (bibcodes de esta corrida contra el conjunto ya conocido del sujeto:
  notas de paper existentes con ese slug/tema + entradas previas del registro).
  `make_notes.search_line(slug)` pasa a resumir: fecha de la última corrida, universo **acumulado**
  (unión, no suma), `N búsquedas`. Lector nuevo `lib_config.load_busquedas(slug) -> list[dict]`.
- **Detector:** clave vieja `busqueda:` (mapa) en un registro → categoría bloqueante del lint
  ("registro en schema pre-D-28"), sin migrador. El generador `vintage` de `tests/poblada/` gana el
  caso.
- **Tests (antes, rojos):**
  - `test_dos_busquedas_con_solapamiento_no_suman` — corrida A trae {1,2,3}, corrida B {2,3,4} →
    la cabecera dice universo 4, no 6; la entrada B dice `n_nuevos: 1`, `n_ya_estaban: 2`
    (INV-89; rojo: hoy `save_busqueda` **pisa** y no hay nuevos/ya-estaban).
  - `test_segunda_corrida_no_pisa_la_primera` — las dos entradas conviven con sus fechas.
  - `test_registro_schema_viejo_detectado` — `busqueda:` mapa → bloqueante.
- **Aceptación:** INV-89 medido con el experimento del contrato (dos búsquedas con solapamiento).

### Issue 2.2 · D-57: cada paso estampa su paso (`cadena:` en el registro)

- **Funciones:** `lib_config.save_paso(slug: str, paso: str, flags: list[str] = ()) -> None` —
  appendea `{paso, fecha, version, flags}` a `cadena:` (congelando: si la última entrada del mismo
  paso es idéntica salvo fecha y nada sustantivo cambió, no se re-escribe — D-54 aplicado acá).
  Se llama desde `ingest_topic.run()` tras rc == 0 — **un solo punto**: `run()` ya centraliza la
  ejecución de la cadena para los dos orquestadores (`ingest_star` lo importa). `lint.py`: categoría
  backlog **"cadena incompleta"** — compara `cadena` del registro contra el orden canónico
  (`ingest_star.CHAIN` + `check_retractions`; para temas, el orden que despacha `ingest_topic`) y
  **nombra el paso donde se cortó**.
- **Tests (antes, rojos):**
  - `test_cadena_cortada_nombra_el_paso` — registro con query_ads+fetch_arxiv+fetch_pdf → el
    reporte dice "se cortó en `fetch_ground_truth`" (INV-91; rojo: la categoría no existe).
  - `test_run_estampa_tras_exito_y_no_tras_fallo` — `run()` con rc 1 no estampa.
  - `test_estampa_idempotente` — dos corridas el mismo día → una entrada, registro byte-igual.
  - `test_pasos_sueltos_tambien_estampan` — correr `fetch_pdf.py` a mano (fuera del orquestador)
    ¿estampa? **No** en esta forma (sólo `run()`): el lint lo reporta como corte, que es la verdad
    — documentar la limitación en el docstring. (Alternativa —que cada script se estampe a sí
    mismo— anotada en R-6.)
- **Aceptación:** INV-91 medido (cortar la cadena a la mitad → el lint nombra el paso).

### Issue 2.3 · D-48: `--no-triage` se elimina; `--force`/`--yes` quedan registradas

- **Funciones:** borrar el flag de `query_ads.main()` (argparse + `gate = bool(star_names)` a
  secas) y su doc; `run()`/los scripts pasan los flags usados a `save_paso(..., flags=[...])`, y
  `query_ads` agrega `escotillas: [--yes, ...]` a su entrada de `busquedas` (con eso llegan a la
  cabecera vía `search_line` — D-12 en tanda 3 las muestra).
- **Tests (antes, rojos):**
  - `test_no_triage_ya_no_existe` — `query_ads.py --no-triage` → SystemExit 2 de argparse (rojo:
    hoy corre). Y el gate del triage no puede apagarse por flag (grabador sobre `load_triage`).
  - `test_yes_queda_en_el_registro` — `ingest_topic --yes` → la entrada de cadena/búsqueda lo
    lista.
  - `test_force_de_ground_truth_registrado` — `fetch_ground_truth <slug> --force` deja rastro en
    `cadena` (vía `save_paso` propio o del orquestador; ver R-6).
- **Aceptación:** el descarte persistido ya no puede pisarse en silencio (INC-2 cerrado de raíz).

### Issue 2.4 · D-52: el descarte viejo queda anulado explícito

- **Funciones:** `lib_config.anular_decision(slug: str, clave: str, por: str) -> bool` — reescribe
  la entrada a `{decision: anulada, fecha, anulada_por: <por>, previa: {…}}` preservando el juicio
  viejo adentro. La llaman los dos carriles al re-aceptar: `query_ads` cuando un bibcode de
  `extra_core` está en los descartados del chaining (hoy sólo lo saltea), `ingest_topic` cuando una
  fuente declarada figura descartada (hoy sólo avisa).
- **Tests (antes, rojos):** `test_descartado_luego_declarado_queda_anulado` (rojo: hoy la decisión
  vieja queda contradiciendo lo hecho); `test_anulacion_preserva_el_juicio_previo` (el motivo viejo
  sigue legible en `previa`); `test_carriles_no_se_cruzan` (anular un descarte de fuente-declarada
  no toca uno de chaining con clave parecida — `es_del_carril`).

### Issue 2.5 · D-58 (config): `extra_core` estructurado

- **Forma canónica:** lista de mapas `{bibcode, via: usuario|triage|citado-por-corpus, fecha,
  motivo}` en `stars.yaml`/`topics.yaml`. Lector nuevo `lib_config.load_extra_core(meta) ->
  list[dict]`; el escalar/lista-de-strings viejo → **detector** (mensaje con la forma nueva), no
  lector tolerante. `triage.py` al aceptar imprime el snippet ya estructurado.
- ⚠ Punto de decisión R-2: si el usuario quiere conservar el atajo `extra_core: [bibcode]` a mano
  (con `via: usuario` implícito) estaríamos escribiendo un lector tolerante — contra la regla. El
  plan asume la forma dura; confirmar.
- **Tests (antes, rojos):** `test_extra_core_escalar_detectado` (rojo: hoy `_listify_curado` lo
  acepta); `test_via_llega_a_query_ads` (el `via` del mapa reemplaza al `"manual"` hardcodeado de
  `query_ads`, y de ahí a la columna Origen en tanda 3).

---

## 5. Tanda 3 — Materialización y estado de la ficha

**Cubre:** D-10, D-24, D-22, D-12, D-54, la mitad-lint de D-13/D-15, T-3. **Cierra:** INV-81,
INV-82; INV-83 en su mitad determinista. **Toca:** `make_notes.py`, `lint.py`, `query_ads.py`
(probe), skills `ingest-star`/`ingest-topic` (referencias), `CLAUDE.md`.
**Por qué acá:** necesita el registro quieto (tanda 2) y la fecha de verificación del ancla
(tanda 1) para el bloque de estado.

### Issue 3.1 · D-10 + D-24 + D-22: la lista de papers se materializa, con estado y origen

- **Funciones (todas en `make_notes.py`, familia `stamp_excluded`):**
  - `papers_universe(slug: str, kind: str) -> list[dict]` — por paper del sujeto:
    `{stem, year, relevance, origen, via, estado}`. Estado: `sintetizado` (el stem aparece citado
    en el cuerpo de **esta** ficha — mismo criterio que `cited_in_entity` del lint, pero local a la
    nota), `extraído, no sintetizado` (`methods` poblado), `sin extraer`, `fuera del filtro`
    (`relevance: low`). Origen: `lente` / `manual` con el `via` de D-58. Fuentes: notas de
    `papers/` (frontmatter `stars:`/`topics:` — parseado con `split_fm`, nunca grep: la lección
    medida dos veces de `CLAUDE.md`), más `ads.json`/registro para el universo no bajado.
  - `papers_table(rows: list[dict]) -> str` — encabezado
    `## Papers (N · M sintetizados en esta ficha)` + tabla con columnas
    `Bibcode | Año | Relevancia | Origen | Estado`.
  - `stamp_papers_table(slug: str, dest: Path) -> bool` — cirugía idempotente anclada (reemplaza
    el bloque ```dataview``` de `## Papers`); ídem `stamp_methods_table(slug, dest)`.
  - Conceptos (D-22): `concept_rollup_rows(slug: str) -> list[dict]` — **unión** de
    `contains(methods, X)` y `contains(thesis_links, X)` con columna `Entró por`
    (`methods`/`thesis_links`/`ambos`); misma tabla estampada. Los bloques Dataview de las
    plantillas de `write_star_note`/`write_concept_note` se reemplazan por el estampado (D-11:
    ninguna promesa del contrato depende del plugin — INV-35 pasa de mecanismo a red).
  - `lint.py`: categoría **"lista de papers desactualizada"** — recomputa `papers_universe` y
    compara contra la tabla estampada (filas y conteo del encabezado). Severidad: backlog (es
    "re-estampar", no una violación); la ausencia total de la tabla en una ficha nueva → mismo
    detector.
- **Tests (antes; stub trivial = tabla vacía, rojo por contenido):**
  - `test_tabla_refleja_los_cuatro_estados` — sembrar 6 papers (2 sintetizados, 1 extraído-no,
    2 sin extraer, 1 low) → filas exactas con stems (patrón Censo: stems, no conteos).
  - `test_conteo_del_encabezado_es_el_de_la_tabla` — adversario directo del "155 arriba de un
    Resumen de 8" medido en D-10.
  - `test_origen_manual_gana_al_de_lente` — paper que entró por query Y por extra_core → `manual`
    (el juicio pisa a la lente, #68).
  - `test_estampado_idempotente_byte_a_byte` — dos corridas → idéntico (D-54).
  - `test_lint_detecta_tabla_desactualizada` — agregar una nota de paper sin re-estampar →
    categoría con el stem.
  - `test_rollup_de_concepto_es_union_y_declara_llave` — paper sólo-`methods` y paper
    sólo-`thesis_links` aparecen ambos, con su columna (adversario: las tres llaves distintas
    medidas en la instancia).
- **Aceptación:** INV-81 medido con el test del contrato (tabla estampada == cálculo determinista;
  encabezado == tabla).

### Issue 3.2 · D-12 + D-54: el bloque de estado con las tres fechas

- **Funciones:** `make_notes.estado_line(slug: str, dest: Path) -> str` +
  `stamp_estado(slug, dest) -> bool` — reemplaza/absorbe `search_line`/`stamp_search_line`: UNA
  línea/bloque de cabecera con **búsqueda** (última corrida + acumulado, de `busquedas`),
  **síntesis** (fecha del último estampado de la tabla D-10), **verificación** (fecha del bloque
  `## Verificación de citas`, con la salvedad fija "vigencia por par: la dicen las anclas"), y las
  escotillas registradas (D-48). D-54 transversal: todo stamper compara el contenido **sin la
  fecha**; si nada sustantivo cambió, no re-escribe (diffs limpios).
- **Tests (antes, rojos):**
  - `test_refrescar_sin_reverificar_mueve_una_sola_fecha` — re-estampar la tabla tras una búsqueda
    nueva → cambia búsqueda+síntesis, la de verificación queda (INV-82, el experimento del
    contrato).
  - `test_fecha_congelada_si_nada_cambio` — segunda corrida idéntica → nota byte-igual (D-54;
    rojo: un stamper naive re-fecha).
  - `test_cabecera_sin_ancla_reporta` — cabecera fuera de contrato → `False` + el lint #69 ya lo
    surface (regresión, no rojo nuevo).
- **Aceptación:** INV-82 medido.

### Issue 3.3 · D-13/D-15 (mitad determinista) + T-3: el pendiente es visible y el costo también

- **Funciones:** el "core sin extraer" ya existe como campo incompleto (`paper relevante sin
  methods`); lo nuevo: (a) el registro gana `extraccion: {subconjunto: bool, criterio: str,
  fecha}` — lo escribe el agente al declarar un subconjunto (D-14: criterio declarado y
  registrado); (b) `lint.py`: si hay core sin extraer **y** no hay `extraccion.criterio` declarado
  → hallazgo con más señal ("el ingest no leyó todo y no declaró por qué" — INV-83); con criterio
  declarado → backlog normal (la cola visible de D-15, que `maintain` consume); (c)
  `query_ads.print_probe` reporta junto al conteo core el **costo proyectado** (n_core × mediana
  24k tokens, T-3) — la lente como presupuesto.
- **Tests (antes, rojos):** `test_subconjunto_sin_declarar_reporta` (rojo);
  `test_subconjunto_declarado_baja_a_backlog`; `test_probe_reporta_costo` (assert contra la salida
  del probe con n_core conocido).
- **Aceptación:** INV-83 medido en su mitad "subconjunto declarado ⇒ la ficha lo dice; sin declarar
  ⇒ hallazgo". La mitad "leer todos por default" es conducta del skill (tanda 9).

---

## 6. Tanda 4 — Autoridad por campo del ground-truth (D-1, D-2)

**Cubre:** D-1, D-2 (con la resolución §4.2: `dist_pc` queda en NEA). **Cierra:** INV-76, INV-77;
INV-14 pasa a verdad. **Toca:** `fetch_ground_truth.py`, `lint.py`. **Tamaño:** chica.
**Por qué acá:** antes de la pasada de red (corrección 3): `nea_diff` diffea el JSON cuyo layout
esta tanda cambia.

### Issue 4.1 · D-1: `spectral_type` ← SIMBAD, sin fallback, con auditoría

- **Funciones:** `fetch_ground_truth.fetch_host(host, tab=None) -> dict` — invertir: el bloque NEA
  deja de escribir `spectral_type` (su valor va a `nea_spectral_type`, campo de auditoría no
  autoritativo, análogo a `bmass_earth`/`mass_source`); el bloque SIMBAD escribe `spectral_type`
  **siempre que SIMBAD lo tenga**, y si no, queda `null` aunque NEA tenga (hoy `:174` toma NEA y
  `:204-211` rellena — exactamente al revés). El payload gana la constancia de qué autoridad
  escribió (`spectral_type_source: simbad` o el campo de auditoría alcanza — decidir la forma
  mínima en el issue). `lint.mirror_issues` no cambia de firma: sigue comparando
  `spectral_type` ficha ↔ JSON.
- **Tests (antes, rojos — los cuatro casos del contrato):**
  - `test_ambas_tienen_gana_simbad` — NEA `G8V`, SIMBAD `G8.5V` → el JSON dice `G8.5V` (**rojo:
    hoy gana NEA**).
  - `test_solo_nea_queda_null` — SIMBAD sin dato → `spectral_type: null` y `nea_spectral_type`
    preservado (**rojo: hoy rellena**).
  - `test_solo_simbad` y `test_ninguna` — valor de SIMBAD / null limpio.
- **Aceptación:** INV-76 medido; INV-14 se re-estampa en el contrato como verdad.

### Issue 4.2 · D-2: la discrepancia es expresable (`DISPUTE_SOURCES` abre)

- **Funciones:** `lint.DISPUTE_SOURCES = ("ground_truth", "nea", "simbad")`; documentar en
  `CLAUDE.md` que `{source: simbad, value: null}` (el silencio de la autoridad declarada) es
  posición válida — el schema ya lo permite, es vocabulario + doc.
- **Tests (antes, rojos):** `test_disputa_nea_simbad_pasa` (rojo: hoy `nea` está fuera del
  vocabulario y bloquea); `test_source_inventado_sigue_bloqueando` (`{source: gaia}` → hallazgo);
  `test_posicion_silencio_value_null_valida` (dos posiciones, una con `value: null` → 0 hallazgos).
- **Aceptación:** INV-77 medido con el par de tests del contrato.

---

## 7. Tanda 5 — Identidad y artefactos (D-19, D-18)

**Cubre:** D-19, D-18. **Cierra:** INV-84. **Toca:** `make_notes.py` (o script nuevo),
`query_ads.py`, `fetch_pdf.py`, `fetch_arxiv.py`, `extract_fulltext.py`, `lint.py`.
**Por qué acá:** la pasada de red (tanda 6) descubre el evento preprint→publicado; el mecanismo de
renombre tiene que existir antes.

### Issue 5.1 · D-19: identidad por `doi`/`arxiv_id`, `versions[]`, renombre con reescritura

- **Funciones:**
  - `lint.py`: categoría **"identidad duplicada"** — dos notas de paper con el mismo `arxiv_id` (o
    `doi`) → bloqueante, con el comando de resolución (medido: 2 casos en la instancia).
  - `make_notes.rename_paper(old_stem: str, new_bibcode: str) -> None` (sub-comando
    `python scripts/make_notes.py --rename-paper VIEJO NUEVO`): renombra nota y artefactos
    (`raw/pdfs/*/VIEJO.pdf`, `raw/fulltext/*/VIEJO.txt`), agrega el viejo a
    `versions: [{bibcode, pdf_source, eprint_version, fulltext}]` del frontmatter, y **reescribe
    los `[[wikilinks]]` de toda la bóveda** en Python (atómico por nota, helper de 0.2). Alcance
    declarado: `vault/` — el enunciado de INV-84 en el contrato ya se acota así (reconciliación
    §2.3.1); lo que el mundo exterior conserva es el alias en `versions[]`.
  - `query_ads`/`make_notes.write_paper_notes`: al crear una nota, si ya existe otra con el mismo
    `arxiv_id`/`doi`, **no crear** — reportar el candidato a renombre (evita el conteo doble y el
    falso positivo de #75 desde el vamos).
- **Tests (antes, rojos):**
  - `test_ciclo_preprint_publicado` — el experimento del contrato: nota arXiv citada desde una
    ficha → `--rename-paper` → una sola nota canónica, alias en `versions`, wikilinks reescritos,
    `lint` exit 0 (rojo por comportamiento: el stub renombra la nota y NO reescribe los links → el
    propio lint del test lo delata con `broken`).
  - `test_dos_notas_mismo_arxiv_id_bloquean` — sembrado directo → categoría (rojo: hoy nada).
  - `test_renombre_no_toca_menciones_en_prosa` — un bibcode citado **textualmente** (no wikilink,
    p. ej. dentro de una cita transcripta) queda intacto — adversario: un replace ciego.
  - `test_crear_segunda_nota_mismo_trabajo_rehusa`.
- **Aceptación:** INV-84 medido.

### Issue 5.2 · D-18: reusar el artefacto que ya está bajo otro slug

- **Funciones:** en `fetch_pdf.main` y `fetch_arxiv.main`, antes de ir a la red: buscar
  `<stem>.pdf` bajo `raw/pdfs/*/` (el mismo lookup que el lint arma en `pdf_on_disk`) y copiar/
  hardlinkear al slug actual; ídem `extract_fulltext` con el `.txt` (ya tiene la noción de calidad
  `_FULLTEXT_QUALITY` — reusar la copia de mejor calidad).
- **Tests (antes, rojos):** `test_pdf_bajo_otro_slug_no_va_a_la_red` — sembrar el PDF bajo slug A,
  correr para slug B con `requests` que **revienta si lo llaman** → verde sólo si reusó (rojo hoy:
  vuelve a bajar); `test_txt_reusa_la_de_mejor_calidad` (pdftotext > ocr).
- **Aceptación:** no cierra INV propio; reduce las 33 copias medidas a política declarada.

---

## 8. Tanda 6 — La pasada de red unificada (D-41, D-45, D-46, D-47)

**Cubre:** D-41, D-45, D-46, D-47. **Cierra:** INV-85. **Toca:** script nuevo
`scripts/sweep_external.py` (nombre a confirmar), `check_retractions.py`, `fetch_ground_truth.py`,
`fetch_web.py`, `lint.py`, skill `maintain`.
**Por qué acá:** necesita el exit code sano (0.1), el ancla (1.x: los pares vencidos por fuente son
la propagación offline), D-1 (el JSON final) y D-19 (el renombre que el descubrimiento de versiones
dispara).

### Issue 6.1 · Los detectores nuevos, cada uno en su script

- **Funciones:**
  - `fetch_ground_truth.nea_diff(slug: str) -> list[tuple[str, object, object]]` — baja pscomppars
    **en memoria**, diffea contra el snapshot campo a campo (incluidos planetas por letra) y
    devuelve `(campo, viejo, nuevo)`. **No escribe nada.** Aplicar sigue siendo `--force` (y al
    aplicar, el valor retirado va a `null` — decisión del usuario en D-45; la prosa afectada la
    marca sola el ancla).
  - `fetch_web.refresh(citekey: str) -> str` — re-baja la URL de la nota, hashea
    (`lib_blocks.source_hash` sobre el snapshot determinista), devuelve `igual|distinto`; con
    `distinto`, el snapshot nuevo se escribe como vigente, el viejo **se conserva en disco** y baja
    a `versions[]` (mismo mecanismo que 5.1); con `igual`, sólo se actualiza la fecha de último
    chequeo (que con D-54 no ensucia el diff si nada cambió — resolver la tensión guardando esa
    fecha en el registro, no en la nota).
  - Descubrimiento de versiones: `sweep_external.discover_versions() -> list[tuple[str, str]]` —
    por nota con bibcode arXiv / `pdf_source: eprint`, consultar ADS por `arxiv_id` → si existe
    bibcode publicado, proponer `--rename-paper` (no renombra solo).
- **Tests (antes, rojos):**
  - `test_nea_diff_reporta_y_no_aplica` — el experimento del contrato: cambiar la respuesta mock
    de NEA → el diff se reporta (`P_rot_days 34.5 → (ausente)`) y el JSON en disco queda
    **byte-idéntico** (rojo con stub que aplica).
  - `test_web_resnap_igual_no_toca_nada` / `test_web_resnap_distinto_versiona_y_conserva` — el
    snapshot viejo sigue en disco; los pares verificados contra él quedan marcados **vía el ancla
    de fuente** (integración con 1.2: assert sobre el lint).
  - `test_version_nueva_se_propone_no_se_renombra_sola`.

### Issue 6.2 · El orquestador de red + la caducidad visible (D-46)

- **Funciones:** `sweep_external.main() -> int` — corre en una pasada: retracciones+correcciones
  (`check_retractions` sin `--slug`), versiones (6.1), re-snapshots web, `nea_diff` por slug con
  ground-truth. **Avisa siempre con el diff y pregunta antes de aplicar** (`--yes` para no
  interactivo, registrado por D-48). Registra `ultima_pasada_red: {fecha, cubrió: [...]}` —
  propuesta: `vault/config/registro/_red.yaml` (ver R-4). El dashboard (tanda 10) la muestra; el
  lint **no** la reporta (decisión D-46: es hecho del entorno/tiempo, no inconsistencia de la
  bóveda).
- **Tests (antes, rojos):** `test_pasada_cubre_los_cinco_eventos` (grabadores: los cinco
  detectores llamados); `test_pregunta_antes_de_aplicar` (sin `--yes` y sin TTY → no aplica nada);
  `test_registra_fecha_de_pasada`; exit codes heredan el contrato de 0.1.
- **Aceptación:** INV-85 medido.

### Issue 6.3 · D-47: la prosa que cita un retractado se marca, no se borra

- **Funciones:** definir el marcador en línea (propuesta: `[[bibcode]] ⛔retractada` pegado a la
  cita; sintaxis exacta = R-3) y en `lint.py`: la afirmación que cita un paper `retracted` **sin**
  marca sigue bloqueante (hoy la categoría es por nota de paper; se agrega el barrido por cita en
  prosa); **con** marca, esa cita baja a una categoría informativa ("sostenida por fuente
  retractada — visible, no destruida"). El caso fácil (otra fuente sostiene lo mismo) es conducta
  de skill.
- **Tests (antes, rojos):** `test_cita_a_retractado_sin_marca_bloquea` (rojo: hoy sólo bloquea la
  nota del paper, no localiza la prosa); `test_cita_marcada_no_bloquea_y_se_lista`;
  `test_marca_no_se_confunde_con_prosa` (la palabra "retractada" suelta en una oración no cuenta).

---

## 9. Tanda 7 — Descubrimiento (D-25, D-27, D-26, D-29, D-30)

**Cubre:** D-25, D-27, D-26 (con la resolución §4.3: la puerta 1 **propone**, no clasifica),
D-58 (via `citado-por-corpus`), D-29, D-30. **Cierra:** INV-88; INV-24 queda intacto por
construcción. **Toca:** scripts nuevos `search_arxiv.py`, `openalex.py`, `citation_index.py`;
`query_ads.py`, `ingest_topic.py`, `triage.py`, `topics.yaml` (schema), skills.

### Issue 7.1 · D-25: backends arXiv y OpenAlex

- **Funciones:** `search_arxiv.search(query: str, categories: list[str], rows: int) -> list[dict]`
  (API Atom, sin key; normaliza al schema de registro de `ads.json`, `via: arxiv`);
  `openalex.works(filter: str, per_page: int) -> Iterator[dict]` y
  `openalex.refs_of(idents: list[str]) -> dict[str, list[str]]` (referencias por lote, sin key,
  `mailto` cortés como Crossref). Despacho: `ingest_topic` gana `source: arxiv|openalex` (además de
  los actuales).
- **Tests (antes, rojos; `requests` falso):** `test_parseo_atom_arxiv` (adversario: entrada sin
  DOI, id con `v3`, categorías múltiples); `test_openalex_pagina_por_cursor` (dos páginas, dedup);
  `test_normalizacion_comparte_schema` (un registro de cada backend pasa por `classify` sin
  tocarlo).

### Issue 7.2 · D-27: el índice de citas local

- **Funciones:** `citation_index.build(out: Path = build/citation_index.json) -> Path` — para cada
  paper core de la bóveda (por `doi`/`arxiv_id`/bibcode), pedir sus referencias (OpenAlex por lote;
  ADS `reference` de respaldo) y armar el **índice invertido** obra-citada → [papers míos que la
  citan]. `citation_index.cited_by_corpus(ident: str) -> list[str]` — lookup offline. Regenerable →
  `build/` (regla de oro del registro).
- **Tests (antes, rojos):** `test_indice_invertido_correcto` — 3 papers con referencias solapadas
  → el índice exacto (stems, no conteos); `test_lookup_es_offline` — `requests` que revienta si lo
  llaman; `test_determinista` — dos corridas sobre el mismo insumo → byte-igual.

### Issue 7.3 · D-26 + D-58: la relevancia del tema de método — tres puertas, la 1 propone

- **Funciones:** la entrada del tema en `topics.yaml` gana su **faceta propia** (nombre del campo:
  ver R-5, la colisión `topics`). `query_ads`/`ingest_topic` para temas de método:
  core = faceta propia AND (puerta 2 `fundacional en su campo` —citas altas + faceta— OR puerta 3
  —lente astro global—). La **puerta 1** (`cited_by_corpus`) **no clasifica**: alimenta
  `candidates` del triage con `via: citado-por-corpus` y el conteo de quiénes lo citan; aceptar →
  `extra_core` con `{via: citado-por-corpus, motivo: "lo citan N core"}` (D-58 completo). INV-24
  queda puro: core sigue siendo función de (paper, lente).
- **Tests (antes, rojos):**
  - `test_puerta_1_propone_no_clasifica` — paper citado por 12 core y sin faceta astro → aparece
    como **candidato**, jamás como core (rojo con stub que lo mete a core; es el test que fija la
    resolución §4.3).
  - `test_fundacional_sin_lente_astro_entra` — el caso Hyvärinen: sin "rv", con faceta propia +
    citas → core por puerta 2 (rojo: hoy `require: [rv]` lo mata).
  - `test_las_tres_puertas_por_separado` — corpus fijo, una puerta por vez (INV-88, el experimento
    del contrato).
- **Aceptación:** INV-88 medido; el contrato re-estampa INV-24 como intacto.

### Issue 7.4 · D-29 + D-30: capa skill

D-29 (términos propuestos en prosa, aprobados antes de buscar) va al skill `ingest-topic` — sin
test de código. D-30: la estructura (`## Régimen de validez`, unidad `(afirmación, condiciones,
fuente, rol)`) **ya existe** en `make_notes.REGIMEN` (1.18.0/#74) — verificado en el código; lo que
falta es conducta de skill (`find-contradictions`: el veredicto `aparente` → fila del régimen) y ya
está documentada en la plantilla. Este issue es revisión/ajuste de los dos skills + `CLAUDE.md`,
con el chequeo estilo F2 (toda invocación nombrada existe y parsea) como aceptación.

---

## 10. Tanda 8 — Los B de lint y schema restantes

**Cubre:** D-17, D-49, D-42, D-37, D-21 (detector + lint), D-50, D-56, D-23, D-32, D-55.
**Cierra:** INV-86; fortalece INV-58/60. **Toca:** `make_notes.py`, `lint.py`, `query_ads.py`,
`bench_verify.py`, `objective.yaml`/`topics.yaml` (schema).
**Por qué acá:** son independientes entre sí (cada uno un issue chico); van después de las C para
que los detectores nazcan contra el schema final. Orden interno: D-17 antes de D-49 (dependencia
real: el diff offline necesita las keywords en la nota).

### Issue 8.1 · D-17: `keywords` al frontmatter de la nota de paper

- **Funciones:** `make_notes.write_paper_notes` estampa `keywords:` desde el registro de
  `ads.json` (ya viene en `FIELDS`, `query_ads.py:107`); backfill `--restamp-keywords` para notas
  con `build/` vivo (la bóveda nueva nace con ellas; sin `build/`, es un fetch de metadata por
  bibcode que queda para `maintain`, documentado).
- **Tests (rojos):** `test_keywords_llegan_al_frontmatter` (rojo hoy);
  `test_keywords_no_pisa_extraccion` (add-only, nota preexistente).

### Issue 8.2 · D-49: lente desincronizada, por ficha y con diff, offline

- **Funciones:** `query_ads.lens_diff_offline(slug: str) -> tuple[list[str], list[str]]` —
  re-clasifica desde las **notas** (título del frontmatter + abstract del cuerpo + `keywords` de
  8.1) con la lente vigente y devuelve (entrarían, saldrían). `lint.py`: categoría **backlog**
  "lente desincronizada" — compara la `lente` guardada en la última entrada de `busquedas` contra
  la vigente; si difieren, corre el diff y reporta `+N entrarían / −M saldrían` por ficha. Registro
  sin `lente` → **"no evaluado"** (D-43), nunca cero.
- **Tests (rojos):** `test_lente_cambiada_reporta_diff_por_ficha` (cambiar una regex → la ficha
  lista los stems del delta; rojo); `test_lente_igual_calla`;
  `test_registro_sin_lente_no_evaluado` (adversario del cero inventado).
- **Costo lint:** N_papers × regex de la lente — medir en tier 1; correr el diff **sólo** cuando
  la lente difiere (el caso normal es hash-igual y gratis).

### Issue 8.3 · D-42: `inferencia` nombra sus premisas (INV-86)

- **Funciones:** fijar la sintaxis canónica de la marca — propuesta `(inferencia de [[b1]], [[b2]])`
  tal como la escribe la revisión — y en `lint.py` el detector: la palabra `inferencia` usada como
  marca (dentro de paréntesis/subrayado al cierre de una afirmación) **sin** ≥1 `[[bibcode]]` →
  **bloqueante** (P0: "no entra"). Ajustar `PROT_CITE` (`lint.py:354`), que hoy acepta la palabra
  pelada como respaldo del P_rot.
- **Tests (rojos):** `test_inferencia_pelada_bloquea` (rojo: hoy pasa);
  `test_inferencia_con_premisas_pasa`; `test_la_palabra_en_prosa_no_es_marca` ("la inferencia
  bayesiana permite…" → 0 hallazgos — el falso positivo obvio);
  `test_prot_documentado_ya_no_acepta_inferencia_pelada` (regresión dirigida sobre `PROT_CITE`).
- **Aceptación:** INV-86 medido con el par del contrato.

### Issue 8.4 · D-37 + D-21 (detector): hipótesis con `status` cerrado y sin `bearing` en el paper

- **Funciones:** `lint.py`: (a) `HYP_STATUS = ("abierta", "sostenida", "disputada", "refutada")` —
  `status` fuera del vocabulario en `concepts/hypotheses/` → bloqueante (mismo patrón que `ROLES`);
  (b) consistencia status↔evidencia: si la tabla de evidencia de la hipótesis tiene filas
  `desafía` y el status es `sostenida` → hallazgo (familia staleness); (c) **detector D-21**:
  `bearing` presente en una nota de paper → bloqueante schema viejo ("la postura vive en la tabla
  de la hipótesis"); (d) **retirar** el campo incompleto "thesis_links sin bearing" (su población
  desaparece con el schema).
- **Tests (rojos):** `test_status_prosa_libre_bloquea` (el caso medido: `supuesto operativo con
  caveat conocido` → hallazgo; rojo hoy); `test_status_contradicho_por_evidencia_marca`;
  `test_bearing_en_paper_es_schema_viejo` (rojo); `test_thesis_links_sin_bearing_ya_no_reporta`.

### Issue 8.5 · D-50: el detector de fuga ampliado + `downstream: []`

- **Funciones:** ampliar `IMPL_LEAK_RE` (`lint.py:84`) con la mitad de auto-referencia
  (`nuestro pipeline`, `nuestro código`, `para el repo`, `downstream`, `supuesto de trabajo de`);
  `lib_config.load_downstream() -> list[str]` lee `downstream: []` de `objective.yaml`
  (vacío/ausente = mitad declarada apagada, sin WARN de ausencia); el lint matchea los nombres
  propios declarados. Severidad WARN (como hoy). La doctrina "la bóveda es read-only desde afuera"
  va a `CLAUDE.md`/`README` en tanda 9.
- **Tests (rojos):** `test_autoreferencia_detectada` — los dos casos reales medidos
  (`"…los scripts de ICA"` con `downstream: [ICA]`; `"Supuesto de trabajo del pipeline"`) → hit
  (rojo); `test_downstream_vacio_apagado`; `test_blockquote_sigue_exento` (regresión).

### Issue 8.6 · D-56 + D-23 + D-32: tres categorías chicas

- **D-56:** `data_local` → categoría informativa "no verificable en esta máquina" (no valida
  existencia, nunca bloquea). Test: `test_data_local_no_bloquea_ni_toca_disco`.
- **D-23:** nota de paper sin **ningún** destino (`stars`/`topics`/`thesis_links`/`methods` todos
  vacíos) → bloqueante. Test rojo: `test_paper_sin_destino_bloquea` (hoy sólo caería como huérfano
  si además nadie lo linkea — sembrar el caso con link entrante para probar que la categoría nueva
  lo agarra igual).
- **D-32:** `parent: <hub>` en `topics.yaml`; lint bidireccional: radio cuyo `parent` no existe
  como concepto → bloqueante (familia dangling); hub cuya nota no menciona `[[radio]]` → hallazgo.
  Tests rojos: `test_radio_sin_hub_bloquea`; `test_hub_que_no_nombra_su_radio_marca`.

### Issue 8.7 · D-55: partir `bench.json` en examen y clave

- **Funciones:** `bench_verify.cmd_seed` escribe `build/verify_bench/exam.json` (pares SIN marca
  de sembrado) y `key.json` (qué pares son falsos); `cmd_score` cruza los dos. El skill lee sólo
  `exam.json`.
- **Tests (rojos):** `test_exam_no_contiene_la_clave` — ningún campo del examen delata el
  sembrado (rojo: hoy conviven en `bench.json`); `test_score_cruza_examen_y_clave`;
  `test_determinismo_byte_a_byte` (regresión del contrato actual del bench).
- Recordatorio de MEMORY: el benchmark es el **gate** de cualquier cambio futuro al fan-out de
  verify — esta partición no cambia el recall medido, sólo la ceguera.

---

## 11. Tanda 9 — Skills y documentación (los A + los B de skill)

**Cubre:** D-3, D-5, D-9, D-11, D-44, D-52-doc (los 7 de A: documentar/ratificar), y los B de
skill: D-7, D-8 (setup/ingest-star: alias y términos validados **antes** de buscar, con la
consecuencia de costo de T-3), D-13/D-14 (ingest-star: leer **todos** los core, un subagente por
paper, subconjunto sólo declarado y registrado — la mitad conductual de INV-83), D-15 (maintain:
completar = backlog), D-21 (test-hypothesis/verify: la tabla de evidencia con postura+cita en la
hipótesis), D-29, D-31 (append-knowledge: integrar en su lugar, contraste dirigido por eje,
apoyado en las anclas), D-33–D-36 y D-38 (test-hypothesis: alcance declarado y creciente,
fulltexts no ficha, veredicto `inferencia`, los 4 ajustes), D-39/D-40 (find-contradictions al
cierre acotado a los ejes tocados; destino mandatorio), D-42-doc (qué es una inferencia, en la
capa que enseña a navegar), D-46-doc, D-50-doctrina (**"la bóveda es read-only desde afuera"**,
escrita donde el agente externo la lea: cabecera del `CLAUDE.md`, sección del contrato con el
consumidor), D-47 (procedimiento de marcado).

**Método:** un issue por skill (setup, ingest-star, ingest-topic, append-knowledge,
test-hypothesis, find-contradictions, verify-citations, maintain) + un issue final de `CLAUDE.md`
(schema acumulado: `keywords`, `versions[]`, sin `bearing`, `DISPUTE_SOURCES`, `status`,
`extra_core` estructurado, el bloque de verificación nuevo, la lista materializada, la marca de
retractado, la marca de inferencia). **Criterio de aceptación por issue:** la pasada estilo F2 de
la 8ª (toda invocación de comando que el skill nombra existe y parsea; toda referencia cruzada
resuelve) + lint verde sobre la bóveda seed del template. D-34 trae además una pieza de lint que
se implementa acá (quedó para esta tanda porque su schema depende del formato de alcance que
defina el skill): **alcance declarado vs corpus vigente** — la nota de hipótesis declara
`temas+estrellas+N papers+fecha` y el lint marca si el corpus de esos directorios creció
(`test_alcance_quedo_corto_marca`, rojo).

**Nota sobre D-34/D-37/D-38:** el orden interno es skill primero (define formato), lint después
(lo vigila) — la excepción al patrón general, y por eso D-37 (vocabulario, que no depende del
formato) fue a la tanda 8 y la vigilancia de alcance quedó acá.

---

## 12. Tanda 10 — Dashboard (T-4) y cierre de la suite

### Issue 10.1 · Refactor previo: el lint expone su resultado estructurado

- **Funciones:** extraer de `lint.main()` una `collect() -> LintResult` (dict categoría →
  lista de hallazgos + severidad) que `main()` renderiza — hoy las ~33 listas viven sueltas en el
  cuerpo de `main` (1191 líneas). Sin cambio de comportamiento: el golden de
  `tests/poblada/test_golden.py` es el instrumento (byte-igual antes/después).
- **Tests:** el golden existente + `test_collect_y_main_coinciden`.

### Issue 10.2 · El tablero

- **Funciones:** `scripts/make_dashboard.py` → `vault/wiki/dashboard.md` — artefacto de
  **navegación** (familia `index.md`, no bibliografía: acá Dataview está permitido, pero los
  números del contrato salen de `collect()` y de los censos deterministas): cobertura de síntesis
  por ficha (D-10: N/M), pares vencidos por ancla y por fuente (D-20), triage pendiente, backlog
  del lint, retracciones/correcciones, fuentes pendientes, lente desincronizada (agregado),
  **última pasada de red** (D-46). Estampado idempotente (D-54).
  **Agregado el 2026-08-24 (pedido del usuario):** también la **salud de la extracción de
  fulltext** — el resultado de `is_legible` sobre el corpus, con el margen al corte, no sólo el
  conteo de ilegibles. La medición del issue 0.4 mostró que ese conteo es engañoso: dio 0/672 y el
  dato útil era el **margen** (×1,05 en el ratio contra ×9,8 y ×3,6 de los otros dos) y la forma
  del casi-falla (14 archivos con un glifo de figura dominando sus no-ASCII). Un tablero que sólo
  dijera "0 ilegibles" ocultaría exactamente eso. Va como distribución/percentiles + los N más
  cerca del corte.
- **Tests (rojos):** `test_dashboard_refleja_el_censo` — sembrar K anomalías conocidas → los
  conteos exactos (patrón de `test_conteos_exactos`); `test_dashboard_idempotente`;
  `test_dashboard_no_es_huerfano_ni_bibliografia` (excluido del scan de fuga y de huérfanas, como
  `index`).

### Issue 10.3 · Cierre de la suite poblada y del presupuesto

- `tests/poblada/generador.py`: el corpus sintético emite el **schema nuevo** (bloque de
  verificación con anclas, tabla materializada, registro con `busquedas`/`cadena`) y gana
  anomalías sembradas para las categorías nuevas (par vencido, tabla desactualizada, identidad
  duplicada, inferencia pelada, status inválido, bearing viejo, registro viejo); `vintage="1.11.0"`
  se conserva para los detectores. Regenerar el golden (`UPDATE_GOLDEN=1`).
- `test_escala.py` gana **anclas de hotspot** para las pasadas nuevas: partición+hash de bloques y
  `source_hash` (verificando que comparte la lectura con `is_legible` — una regresión que las
  separe duplica el 77% del costo). Presupuestos: tier 0 ≤ 2,5 s y tier 1 ≤ 90 s **se re-miden y
  se mantienen**; si el acumulado los rompe, el primer candidato es cachear
  `is_legible`/`source_hash` por `(mtime, size)` en `build/` (scratch regenerable) — se decide con
  la medición en la mano, no antes.
- Actualizar `tests/README.md` y la tabla de categorías del lint en la doc (el mapeo 1:1 en ambas
  direcciones que midió la 8ª F3).

---

## 13. El costo acumulado del lint (transversal)

Punto de partida medido: **5,6 s sobre 908 notas, 77% en `is_legible`** (con doble parseo YAML ya
anclado en `test_escala`). Lo que este plan le agrega, con su costo esperado:

| Pasada nueva | Costo | Mitigación |
|---|---|---|
| partición en bloques + sha256 por nota con citas (T1) | regex + hash, ≪ parseo YAML | — |
| `source_hash` de cada `.txt` (T1) | **cero lecturas extra**: comparte la única lectura de `is_legible` | test de regresión en 10.3 |
| comparación tabla materializada vs censo (T3) | lookups sobre frontmatter ya parseado | — |
| `lens_diff_offline` (T8) | N_papers × regex | sólo corre si el hash de la lente difiere |
| identidad duplicada, status, bearing, destino, hub/radio, inferencia (T5/T8) | O(N) sobre datos ya en memoria | — |

Regla operativa: **cada tanda que toque el lint cierra corriendo tier 1 y anota el tiempo en el
issue**; el lint no puede salirse de los presupuestos declarados sin que eso sea un hallazgo propio.

---

## 14. Riesgos y puntos de decisión

Lo que el plan **asume** y el usuario todavía no dijo (nada de esto se resuelve solo: se pregunta
al llegar al issue):

- **R-1 · Cómo se distinguen los dos momentos de D-4.** ✅ **RESUELTA (2026-08-24): `lint.py
  --cierre`.** Sin el flag, los pares vencidos reportan como backlog (exit 0 — la pasada
  periódica); con el flag cuentan para el exit ≠ 0, y los skills de cierre lo invocan así. Se
  eligió sobre "sólo en los skills" porque deja la severidad en **un** punto testeable en vez de
  en prosa de skill (un skill que se olvida no deja rastro), y sobre "siempre bloqueante" porque
  esa opción deja la bóveda en rojo durante un ingest en curso. D-44 intacto: el commit nunca se
  frena. Vale para el issue 1.2.
- **R-2 · La forma dura de `extra_core` (D-58).** ✅ **RESUELTA (2026-08-24): forma dura con
  detector.** Sólo lista de mapas `{bibcode, via, fecha, motivo}`; el escalar y la lista de strings
  se detectan y bloquean, con el snippet correcto en el mensaje. Es la regla del repo (sin lectores
  tolerantes), y el costo de UX resultó acotado: `triage.py` ya imprime el snippet para pegar, así
  que sólo se siente al agregar un bibcode 100% a mano.
- **R-3 · Sintaxis de la marca en línea de fuente retractada (D-47).** ✅ **RESUELTA
  (2026-08-24): sufijo `⛔retractada` pegado a la cita** — `[[bibcode]] ⛔retractada`. El símbolo
  hace imposible confundirla con la palabra "retractada" suelta en una oración (el falso positivo
  que el paréntesis pelado sí tendría). Junto con `(inferencia de [[b]])` de D-42, son las dos
  únicas marcas en línea del sistema.
- **R-4 · Dónde vive `ultima_pasada_red` (D-46).** ✅ **RESUELTA (2026-08-24):
  `vault/config/registro/_red.yaml`, versionado.** La caducidad —cuándo se miró afuera por última
  vez— es información sobre **la bóveda**, no sobre la máquina que corrió la pasada: sin
  versionarla, otro clon reporta "nunca se corrió", que es falso.
- **R-5 · La colisión de nombres `topics` (revisión §7.2, sin resolver) se AGRAVA con D-26**: la
  faceta propia del tema viviría en `topics.yaml`, que ya colisiona con `relevance.topics` y con
  el campo `topics` de las notas. Decidir el renombre (o el nombre del campo nuevo) **antes** del
  issue 7.3, o la confusión queda fosilizada en un schema más.
- **R-6 · Quién estampa `cadena` cuando un script corre suelto (D-57).** ✅ **RESUELTA
  (2026-08-24): cada script se estampa a sí mismo** al salir 0, con una implementación compartida
  (`cfg.save_paso`) y N call sites. Se descartó estampar sólo desde `run()` porque un paso corrido
  a mano quedaría invisible y el lint reportaría "se cortó en `fetch_pdf`" sobre un paso que **sí
  corrió** — un falso positivo que erosiona la categoría entera. El registro distingue
  `via: orquestador` de `via: suelto`.
- **R-7 · Los tres abiertos de la revisión §7 que este plan NO cubre** (no hay decisión): la
  **lista blanca del frontmatter** (el `logrhk` medido viviendo sin custodia en la capa
  auditable), la **tabla de lookalikes griegos afirmada sin medir**, y la **cobertura de
  sinónimos sin medición**. Quedan como backlog explícito; si el usuario quiere la lista blanca,
  es una categoría de lint más (chica) pero con decisión de vocabulario previa.
- **R-8 · Registro del "motivo por el que no se leyó todo" (D-13/D-14).** El plan propone
  `extraccion: {subconjunto, criterio, fecha}` en el registro; el formato exacto no está decidido.
  La reconciliación §2.3.2 anticipa que el subconjunto va a ser el caso normal (≈6M tokens por
  estrella si no): el criterio declarado es la pieza que más se va a leer.
- **R-9 · Fuente primaria del índice de citas (D-27).** OpenAlex por lote (sin key, cubre todo)
  con ADS de respaldo es la propuesta; cuotas y cobertura real de `referenced_works` para astro
  vieja no están medidas — el issue 7.2 empieza midiendo sobre 20 bibcodes reales antes de fijar
  el diseño.
- **R-10 · Tandas que pueden invalidarse entre sí.** Las conocidas están resueltas por orden
  (registro antes que cabecera; D-1 antes que `nea_diff`; ancla antes que pasada de red). Quedan
  dos genuinas: (a) el formato del bloque de verificación (1.2) lo consumen bench (8.7), skills
  (9) y dashboard (10) — si el usuario pide cambiarlo tarde, se re-tocan los cuatro; congelarlo al
  cerrar la tanda 1. (b) El refactor `collect()` (10.1) toca todo `lint.py`: por eso va **último**
  y con el golden como red — hacerlo antes obligaría a re-validar cada categoría nueva dos veces.
- **R-11 · D-31/D-39 dependen de conducta de skill sobre mecanismo nuevo.** El refresh dirigido
  por eje y el find-contradictions de cierre usan las anclas como contabilidad; si el uso real en
  la bóveda nueva muestra que la granularidad de bloque marca de más (párrafos largos con muchas
  citas), la decisión D-4 ya lo acepta ("el error cae del lado caro") — pero conviene medirlo en
  el primer ingest real y anotarlo.

---

## 15. Versionado

Cada tanda cierra con tests completos verdes (tier 0 + tier 1 si tocó lint/generador; tier 2
cuando haya instancia nueva), bump de `ALMAGESTO_VERSION` y tag. Propuesta: tandas 0–10 son
minors consecutivos (1.24.0 … 1.34.0) — cada una agrega mecanismo, ninguna es patch. Release de
GitHub en cada minor, como está pactado. Los issues intermedios de una tanda no bumpean: el bump
es el cierre de tanda, con su entrada en STATUS (qué cerró, contra qué invariantes, con qué
números).
