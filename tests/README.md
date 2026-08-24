# Tests de `scripts/` — diseño de la suite

Tests unitarios/integración de la **capa determinista** del framework (los scripts de
`scripts/`). No testean la capa LLM (skills, extracción, síntesis) ni el contenido de una
bóveda real — para eso está `lint.py`, que es el "test suite" del *contenido*.

**Correr** (desde la raíz del repo):

```bash
python -m pytest tests/ -q
```

## Los tres tiers

La suite está partida en tiers por `pytest.ini`, cuyo `addopts` deja fuera por default lo caro. Esa
línea es lo que hace viable la capa de bóveda poblada: ~900 notas convertirían el default de 2 s en
minutos, **y una suite que tarda es una suite que se deja de correr antes de commitear** — que es
justo cuando más sirve.

| Tier | Qué corre | Comando | Presupuesto |
|---|---|---|---|
| **0** — siempre (default, CI en cada push) | todo `tests/*.py` | `python -m pytest tests/ -q` | ≤ 8 ms/test **y** ≤ 10 s |
| **1** — `poblada` (nightly / pre-release) | `tests/poblada/` sobre corpus sintético (~900 notas) | `python -m pytest tests/ -m poblada -q` | ≤ 120 s |
| **2** — `instancia` (sólo en la máquina del usuario; gate del deploy) | invariantes sobre una instancia REAL | `ALMAGESTO_INSTANCIA=/ruta/a/la/instancia python -m pytest tests/ -m instancia -q` | ≤ 60 s |
| todos | los tres | `ALMAGESTO_INSTANCIA=... python -m pytest tests/ -m "" -q` | ≤ 3 min |

`instancia` **sin** la env var **skipea con motivo visible**, nunca pasa en silencio: un tier que se
saltea sin decirlo es el mismo modo de falla que el "0 que no miró" (ver abajo).

> **El presupuesto de tier 0 es una TASA, no un absoluto — y esa es la corrección de 10.3.** El
> techo original (≤ 2,5 s) se escribió con ~400 tests y se fue a **7,3 s** a lo largo de nueve
> tandas, una decena de tests por vez, **sin que nada fallara nunca**: ninguna corrida se pone roja
> por lenta. Es el caso de manual de *"una promesa que el sistema dejó de cumplir en silencio"*.
>
> Lo que la medición mostró (2026-08-24), que es lo que el issue pedía decidir **con la medición en
> la mano** y no antes:
> - el hotspot **no** era `is_legible` —tier 0 no tiene corpus grande—: era **un solo test** que
>   barría el repo entero con AST para mirar dos archivos, **2,6 s de los 7,3**. Acotarlo bajó el
>   tier a **4,75 s** sin tocar nada más;
> - el resto es piso por test (~4 ms de tmpdir por `toy_vault`) × ~1000 tests;
> - o sea que **el costo por test BAJÓ** desde que se escribió el techo (2,5 s / 400 ≈ 6 ms/test
>   entonces, 4,7 ms/test hoy). Lo que creció es la cantidad.
>
> **Tier 1 pasó de ≤ 90 s a ≤ 120 s, y es una decisión, no un trámite.** Medido: 55 s → 91 s en la
> misma sesión, y el crecimiento es **cobertura real**, no grasa — el generador pasó de sembrar 7
> anomalías a 16 (nueve siembras parametrizadas nuevas), entraron tres anclas (`source_hash`
> compartiendo lectura, corpus limpio en las 48 categorías, los números de la doc) y una de ellas
> es **una corrida entera de tier 0** (5,1 s: es el instrumento que mide el otro presupuesto).
> Lo que NO puede pasar es que el techo suba solo: lo fija
> `test_escala.py::test_presupuesto_de_tier_1`, con el mismo criterio que su hermano.

> Por eso el presupuesto es **≤ 8 ms/test y ≤ 10 s absolutos**: la tasa protege la propiedad real
> —*una suite que tarda se deja de correr antes de commitear*— y el techo absoluto impide que la
> cantidad crezca sin límite amparada en la tasa. Los dos los mide
> `tests/poblada/test_escala.py::test_presupuesto_de_tier_0`, que corre el tier 0 como subproceso
> **desde tier 1**: un tier no puede medirse a sí mismo sin sumar su propio costo al que reporta.
> Un techo sin test es exactamente cómo éste llegó a 7,3 s.

Requiere `pytest` (dev-only, no está en `requirements.txt`; los scripts no lo necesitan).

## Principios de diseño

1. **Sin red, sin binarios externos.** Todo lo que toca afuera se mockea: ADS/arXiv/Crossref/NEA
   (`requests` / `astroquery`), y los subprocesos (`pdftotext`, `tesseract`, `defuddle`). Cada
   módulo recibe un namespace falso (`SimpleNamespace(run=...)`) en lugar del módulo real, así el
   parche no se filtra a otras libs. `time.sleep` se anula (los retries corren instantáneos).
2. **Bóveda de juguete aislada.** `lib_config` resuelve rutas por constantes de módulo derivadas
   de `__file__`; la fixture `toy_vault` (en `conftest.py`) re-apunta **todas** esas constantes a
   un árbol temporal (`tmp_path`), incluidos los alias que otros módulos toman al importar
   (`extract_fulltext.FULLTEXT`). Ningún test lee ni escribe la bóveda real.
3. **Sin capas de compatibilidad.** El framework no tolera schemas viejos en el lector: cada vez
   que uno cambia, hay un **migrador de un solo uso** y un **detector** en el lint. Los tests fijan
   las dos mitades — que el lector NO lea lo viejo, y que lo viejo **grite** en vez de volverse mudo.
4. **Testear el contrato documentado.** Las expectativas salen de los docstrings, `CLAUDE.md` y
   `README.md` — no de "lo que el código hace hoy". Si un test falla, primero se triagea:
   ¿bug del script o expectativa mal leída?
5. **Los invariantes críticos primero.** Lo más cubierto es lo que más duele si se rompe:
   - **Idempotencia / no pisar extracción LLM** (`make_notes`, `unpend_note`,
     `merge_frontmatter_list` byte-a-byte, `--force` sólo donde está prometido).
   - **Cada categoría del lint** detecta su caso sembrado y el exit code separa
     bloqueante / WARN / backlog.
   - **Física del ground-truth** (`msini_earth` contra valores conocidos: Tierra, 51 Peg b)
     y la selección de masa NEA (msini vs best-mass, flags).
   - **Espejo ficha ↔ ground-truth** (#70): el frontmatter de `stars/` vale lo que dice NEA o nada;
     un valor rellenado con literatura es indistinguible del auditable si nadie lo compara.
   - **Validaciones de entrada** que abortan la cadena (`ingest_theme`, citekeys, sources).
6. **Un test de fix se escribe ANTES del fix y se lo ve fallar.** El orden es
   **test → rojo → fix → verde**, verificando el rojo. Un test que nunca estuvo rojo no distingue
   la presencia de la ausencia del fix: no es evidencia. Reemplaza a la mutación post-hoc como
   camino por defecto (la mutación queda para auditar tests **que ya existen**, donde no hay un
   "antes"). El protocolo completo —incluidos el porqué medido, la trampa del `.pyc` al mutar y la
   forma de repartir una tanda grande— está en `vault/STATUS.md`, *Protocolo de fixes*.
   ⚠ Corolario que ya mordió dos veces: **los asserts de contenido del lint van contra el archivo
   de reporte, no contra stdout** — la última línea de stdout es la ruta del reporte, que vive bajo
   el tmpdir de pytest, **cuyo nombre es el del test**, así que cualquier substring del nombre del
   test matchea sin que el lint haya reportado nada.

## Layout

| Archivo | Cubre | Estrategia |
|---|---|---|
| `conftest.py` | fixtures compartidas | `toy_vault` + helpers `write_yaml`/`mk_note` |
| `test_lib_config.py` | token ADS, loaders YAML, `load_concept_areas` (declarado/tolerante) | puro FS |
| `test_query_ads.py` | `classify`, variantes de designación, `build_query`, retry/truncado, chaining (dedup, `via`), `extra_core`, `main()` | `requests` falso + subfunciones mockeadas |
| `test_fetch_arxiv.py` | `download_pdf` (resume por Range, 200-ignora-Range, 429, magic `%PDF`), `main()` (skip/limit/missing) | respuestas streaming falsas |
| `test_fetch_pdf.py` | resolver `esource` (formas múltiple/link-único, placeholders, DOI pelado), higiene del token (sólo hosts ADS), fallback `curl` sólo a publishers, residuo `missing_pdf` | `requests` y `curl` falsos |
| `test_fetch_ground_truth.py` | `msini_earth` (física), `_val`, selección de masa y flags en `fetch_planets`, idempotencia de `main()` | `astroquery` falso vía `sys.modules` |
| `test_extract_fulltext.py` | `is_legible` (umbrales), flujo pdftotext→OCR (fallback, upgrade automático, ya-OCR no reintenta), degradación limpia | `subprocess`/`shutil` falsos |
| `test_fetch_web.py` | `clean_markdown` (determinista), `snapshot_date_of`, header del snapshot, reuso de fecha, `CITEKEY_RE` | `defuddle` mockeado |
| `test_make_notes.py` | stubs (star/concept/paper/web), migración de `disputes` a posiciones explícitas (#71: materializa el polo implícito, degrada sin destruir), `extraction_block` ramificado por tipo de sujeto (unitario + matriz de ramas), retro-linkeo add-only, `unpend_note`, `excluded_table` (escapes), puntero de búsqueda en la cabecera, `pdf_source` (eprint vs publicado), idempotencia | puro FS |
| `test_triage.py` | carga y persistencia de decisiones en el registro versionado (sin mergear el `triage.json` viejo), `--drop` y `--drop-source` (motivo obligatorio, carriles que no se pisan), listado sin `ads.json`, `--migrate` del `triage.json` legacy, contrato con `query_ads.load_triage` | puro FS |
| `test_multicolumn_matching.py` | invariantes de la estrategia de matcheo en `.txt` a dos columnas (#44/#46): escalera de acortamiento, canaleta, normalización que empalma columnas | fixtures sintéticos |
| `test_lint.py` | cada categoría con su caso sembrado + exit codes; espejo ficha↔ground-truth (#70: qué planetas —no cuántos— y campo por campo), extraído pero no sintetizado (#75), vocabulario cerrado de `role` (#73), disputas con posiciones explícitas (#71), detectores de los schemas viejos que el lector ya no mira | bóvedas mínimas por escenario |
| `test_check_retractions.py` | parseo Crossref (`updated-by`, fechas), fallback por título, estampado idempotente de `retracted` y `corrections`, exit codes | `requests` falso |
| `test_ingest_theme.py` | despacho por `source`, validaciones de `sources:`, flujo `pending`, aviso de fuente ya descartada, copia de PDFs, orden de la cadena ads | `run()` y `make_notes.*` grabadores |
| `test_ingest_star.py` | orden canónico de la cadena de estrellas, aborto al primer fallo, retracción ≠ fallo, hand-off que nombra los pasos salteables | `run()` grabador |
| `test_trace_invariants.py` | recolector de trazabilidad `@inv`: registro canónico desde `docs/contrato.md` §3, la marca sólo en comentario/docstring (adversarios: mención en prosa, `@inv` dentro de un string literal, auto-marcado del propio recolector), marca huérfana bloqueante, ratchet, contrato ilegible ⇒ rc 2 sin cero inventado | repo de juguete |
| `test_bench_verify.py` | extracción de pares (excluye blockquotes/fences/bloque de verificación), siembra por rotación (sin falsos-falsos), determinismo byte a byte, puntaje | puro FS |

### `tests/poblada/` — la capa de corpus (tiers 1 y 2)

Existe porque **la bóveda vacía no puede revelar una clase entera de bugs**: en vacío toda categoría
del lint da `(0)` y un test **no distingue "pasa" de "ni miró"**. No es teórico — tres hallazgos de la
auditoría del 2026-08-23 salieron de mirar corpus real y ninguna de las seis pasadas previas podía
verlos. El caso claro es el deadlock #69: con una nota de juguete el fix pasaba; con 25 notas reales,
21 caían en la rama rota.

| Archivo | Cubre | Estrategia |
|---|---|---|
| `generador.py` | `sembrar_corpus(...) -> Censo` | **fabrica** el corpus (no baja nada, no copia la instancia) con la distribución medida en una instancia real; determinista por `seed`; `vintage="1.11.0"` emite el schema viejo |
| `conftest.py` | `arbol_poblado` (siembra 1× por sesión), `boveda_poblada[_mutable]`, `instancia_real` | `instancia_real` copia lo liviano y **symlinkea** lo pesado; jamás escribe en la instancia |
| `test_generador.py` | la red del propio generador: determinismo por hash, censo == disco, corpus limpio ⇒ lint exit 0 | — |
| `test_conteos_exactos.py` | **la forma canónica**: K anomalías entre ~900 notas ⇒ el lint reporta exactamente esas K y los **stems** coinciden con el censo; sin doble conteo ni contaminación cruzada | — |
| `test_escala.py` | comportamiento cuadrático por **ratio** `t(800)/t(200)` (no tiempos absolutos, frágiles entre máquinas) + el hotspot del doble parseo YAML anclado para que no empeore | — |
| `test_golden.py` | salida del lint congelada con seed fija; normalizador justificado midiendo (5 `PYTHONHASHSEED`) | regenerar: `UPDATE_GOLDEN=1 python -m pytest tests/poblada/test_golden.py -m poblada -q` |
| `test_upgrade.py` | el **ciclo completo**: vintage bloquea → migradores → el lint **cierra el hallazgo** → 2ª pasada byte a byte idéntica | — |

⚠ **El `Censo` es lo que hace útil al corpus grande**: devuelve los *stems* exactos de lo sembrado,
no un conteo. Sin eso, más notas sólo agregan ruido.
⚠ **En `test_upgrade.py`, verificar que el migrador "corrió sin error" NO alcanza**: hay que verificar
que el conteo del lint **baja a 0**. El deadlock #69 informaba éxito en cada corrida mientras el lint
seguía contando — dos veces.
⚠ `tests/poblada/__init__.py` **no es opcional**: sin él, pytest importa `tests/conftest.py` y
`tests/poblada/conftest.py` los dos como módulo `conftest` y el segundo pisa al primero, rompiendo
los `from conftest import ...` de la suite vieja. Sólo se ve corriendo la suite **completa**.

## Cuánto del lint vigila el corpus poblado (10.3)

El lint tiene **48 categorías**; el generador sintético sabe sembrar **16 anomalías**, y
`test_conteos_exactos` puede afirmar *"reporta exactamente estos K, ni uno más"* sólo sobre esas.
El resto queda cubierto de otra forma —el corpus limpio tiene que dar **cero en las 48** salvo tres
declaradas (`test_el_corpus_limpio_da_cero_en_TODAS_las_categorias`)—, que detecta el falso positivo
pero no el falso negativo.

⚠ **Ese desbalance era el hallazgo de 10.3, y era peor**: el generador sembraba **7** de 48, o sea
que el test más fuerte de la suite vigilaba **un séptimo** del lint. Todo lo agregado después de la
primera pasada (par vencido, identidad duplicada, `inferencia` pelada, `status` inválido, registro
viejo, lente desincronizada, alcance de hipótesis, capas colgadas) no tenía corpus grande que lo
probara. Y había una segunda mitad: el corpus "limpio" **no lo estaba** —cinco hipótesis sin
alcance, tres fichas con la tabla `## Papers` desactualizada, tres registros sin `extraccion`—
porque el generador no emitía el schema vigente, y sobre ese ruido de fondo **ninguna anomalía
sembrada era distinguible**.

Los tres números (48 categorías, 16 anomalías, 3 de ruido declarado) **salen del código, no de acá**:
los cruza `test_conteos_exactos`, así que agregar una categoría al lint sin sembrarla deja el
desbalance a la vista en vez de esconderlo.

Emitir el schema vigente destapó además un bug real del lint: la tabla `## Papers` materializada
lista **todo** paper del sujeto con su `[[stem]]`, así que satisfacía sola el proxy de *extraído
pero no sintetizado* — la máquina "citaba" por su cuenta cada paper que el humano no había
sintetizado, y la categoría no podía disparar nunca (medido: 4 → 0).

## Fuera de alcance (deliberado)

- Respuestas reales de ADS/NEA/Crossref (cambian; lo que se fija acá es el **parseo y la
  lógica**, no el schema remoto — si ADS cambia el schema lo detecta el uso, no esta suite).
- La calidad de extracción de `pdftotext`/`tesseract`/`defuddle` (binarios de terceros).
- Los skills (`.claude/skills/`) y todo lo que ejecuta el LLM.
- Dataview/Obsidian (los bloques generados se chequean como texto, no se ejecutan).

---

## Las cinco redes que corren al escribir código (regla permanente, 2026-08-24)

Salieron de una sesión en la que **los bugs los encontraron agentes leyendo, no la suite**. Cada una
ataca una clase de defecto que se repitió, y las cinco son deterministas: nada acá depende del
juicio de un modelo.

| # | Qué caza | Cómo se corre |
|---|---|---|
| 1 | Tests que **pasan por construcción** | `python tools/mutar.py --diff` (o `<archivo>`) |
| 2 | Promesas de **schema compartido** que son sólo prosa | `tests/test_backends_schema.py` (tier 0) |
| 3 | Un **doble** con distinto contrato que la función real | test de paridad al lado del doble |
| 4 | Funciones que **nadie ejecuta** | `pytest tests/poblada/test_cobertura.py -m poblada` (~11 s) |
| 5 | La **doc afirmando cosas del código** | `tests/test_docs_ejecutables.py` (tier 0) |

**La red 5 creció el 2026-08-24, porque tenía el mismo agujero que perseguía**: validaba que el
*script* existiera, no que el *flag* existiera — y `CLAUDE.md` mandaba a correr
`make_notes.py --restamp-keywords`, un flag que el issue que lo prometió nunca implementó. Hoy son
**nueve** chequeos (cuatro nuevos):

| Chequea | Qué agujero cerró |
|---|---|
| los `tests/x.py::test_y` que nombra la doc existen | referencias a tests borrados |
| los `scripts/x.py` que invoca un skill existen y compilan | un skill que llama a un script muerto |
| los `scripts/x.py` que nombra la doc existen | scripts renombrados o borrados |
| los archivos de config que nombra la doc existen | rutas de `vault/config/` renombradas |
| los `--flag` que nombra la doc existen — en bloque de comandos **y en prosa** | `--restamp-keywords` inventado; `--topic` sobrevivió a R-5 dentro de una frase |
| los flags declarados **retirados** siguen retirados | la lista de excepciones convirtiéndose en colador |
| ningún estado del contrato se inventa por fila | tres filas evadían `parcial` con un paréntesis ad-hoc |
| los conteos del encabezado son los de las filas | un resumen escrito a mano que envejece solo |
| la doc no apunta al código **por número de línea** | los siete punteros de `contrato.md` apuntaban al renglón equivocado, uno a otro invariante |

**Cuándo**: 2 y 5 corren solas en tier 0. La 4, al cerrar un issue. **La 1, al escribir cada función
nueva** — es la única que cuesta (una corrida de suite por función) y la única que distingue "el
test pasa" de "el test **podría** fallar".

**Cómo se leen los ratchets** (`tools/mutacion-ratchet.yaml`, `tools/cobertura-ratchet.yaml`): son
**deuda medida**, no objetivos. El número sólo baja; subirlo hay que justificarlo en el commit. Un
techo en 0 sería rojo permanente, y un rojo permanente se deja de mirar.

### Lo que estas redes NO reemplazan

El juicio: *¿el código hace lo que su prosa promete?* Eso lo encontró un agente tres veces en un
día y ningún assert lo habría visto. La forma correcta de institucionalizarlo es que **el agente
emita tests, no veredictos** — un veredicto de modelo no es reproducible y no sirve de red de
regresión; un test que él propuso, sí. (Sin decidir todavía; anotado.)

> Las **cinco reglas de método** de las que salen estas redes están en `CLAUDE.md`,
> sección *Cinco reglas de método*. Acá va sólo la mecánica.

### Dos trampas ya pisadas, para no repetirlas

- **`tools/mutar.py` trabaja sobre una COPIA del repo.** La primera versión mutaba en el lugar y
  restauraba en un `finally`; un `pkill` a mitad de camino dejó `check_retractions._mailto` con el
  cuerpo en `return None` en el árbol de trabajo — y la suite siguió en verde, porque esa función
  es justo una de las que ninguna prueba mata. Un harness que puede corromper lo que audita no
  sirve por más `finally` que tenga.
- **Un test verde recién escrito no cuenta hasta que lo viste morir.** Pasó dos veces el mismo día:
  el test se escribió, pasó a la primera, y sólo la mutación mostró si servía.
