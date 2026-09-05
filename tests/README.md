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
| **0** — siempre (default, CI en cada push) | todo `tests/*.py` | `python -m pytest tests/ -q` | ~11 s (referencia, sin gate — ver abajo) |
| **1** — `poblada` (nightly / pre-release) | `tests/poblada/` sobre corpus sintético (~900 notas) | `python -m pytest tests/ -m poblada -q` | ~91 s (referencia, sin gate) |
| **2** — `instancia` (sólo en la máquina del usuario; gate del deploy) | invariantes sobre una instancia REAL | `ALMAGESTO_INSTANCIA=/ruta/a/la/instancia python -m pytest tests/ -m instancia -q` | ≤ 60 s |
| todos | los tres | `ALMAGESTO_INSTANCIA=... python -m pytest tests/ -m "" -q` | ≤ 3 min |

`instancia` **sin** la env var **skipea con motivo visible**, nunca pasa en silencio: un tier que se
saltea sin decirlo es el mismo modo de falla que el "0 que no miró" (ver abajo).

**Agregá `-n auto` para correr en paralelo** (`pytest-xdist`, en `requirements.txt`). Medido el
2026-08-28 sobre 8 núcleos: tier 0 **20 s → 10 s**, tier 1 **126 s → 46 s**. ⚠ Los tests que
comparan **stdout** o dependen del orden no son seguros bajo xdist; hoy la suite entera pasa en
paralelo, y si alguno empieza a fallar sólo con `-n`, el defecto es del test (estado compartido), no
del paralelismo.

> **Los presupuestos de tiempo se BORRARON el 2026-08-28 (#201), no se recalibraron.** Los números
> de la tabla son referencia, no gate. El techo original de tier 0 (≤ 2,5 s) se fue a 7,3 s a lo largo
> de nueve tandas sin que nada fallara nunca, y la respuesta de entonces fue medirlo con
> `test_presupuesto_de_tier_0` —una tasa (ms/test) más un techo absoluto, corriendo el tier 0 como
> subproceso desde tier 1—. Ese gate midió **wall-clock sobre una máquina sin especificar**, con un
> margen del 15 %, y su único rojo en toda su vida fue **falso**: al cerrar la tanda #196/#197 dio
> 8,5 ms/test contra un techo de 8,0, y correrlo contra el commit anterior —sin un solo test
> agregado— dio rojo también. Se resolvió subiendo el techo, que es el trámite que el propio mensaje
> de error pedía no hacer. Su hermano `test_presupuesto_de_tier_1` tenía margen 1,6× y la misma falla
> esperando.
>
> **Qué queda en su lugar, y por qué alcanza.** La propiedad que protegían —*una suite que tarda se
> deja de correr antes de commitear*— no necesita gate: **pytest imprime la duración en cada
> corrida**, así que una suite que se pone lenta se ve todos los días. Lo que el ojo no ve
> —complejidad peor que lineal— lo cazan los **ratios** de `test_escala.py`, que son independientes
> de la máquina (`lint(800)/lint(200)` ≈ 4 contra ≈16 de un barrido cuadrático). Y el presupuesto
> absoluto que sobrevive, `test_lint_presupuesto_absoluto` (lint(N=900) < 10 s sobre 1,7-1,8 s
> medidos), tiene **5,5× de margen**: sólo se pone rojo ante una regresión grosera, no ante una
> máquina cargada.
>
> ⛔ **El corte es ese margen.** Un presupuesto de wall-clock con menos de ~5× de margen mide la
> máquina, no el repo, y su rojo manda a buscar una regresión que no existe — o peor, enseña a subir
> el techo como trámite. Misma doctrina que la categoría **⛔ No evaluado** del lint: un veredicto que
> el instrumento no puede sostener no sale como veredicto.

Requiere `pytest` (dev-only, no está en `requirements.txt`; los scripts no lo necesitan).

## Principios de diseño

1. **Sin red, sin binarios externos — y ahora es un ASSERT, no una convención.** La fixture autouse
   `sin_red` (en `conftest.py`) intercepta toda petición HTTP, la **registra** y falla el test al
   cerrarlo. Las dos mitades hacen falta: levantar la excepción sola no alcanza, porque el código de
   producción degrada limpio ante un backend caído —conducta correcta allá— y se traga la guardia.
   Esto vivía en prosa desde siempre y nadie la sostenía: medido con `cProfile` (#123), **cuatro
   tests hacían peticiones reales** (OpenAlex, Unpaywall, arXiv, SIMBAD) y pasaban en verde. Cerrar
   ese agujero bajó el tier 0 de **9,5 s a 6,7 s**.
   Todo lo que toca afuera se mockea: ADS/arXiv/Crossref/NEA
   (`requests` / `astroquery`), y los subprocesos (`pdftotext`, `tesseract`, `defuddle`). Cada
   módulo recibe un namespace falso (`SimpleNamespace(run=...)`) en lugar del módulo real, así el
   parche no se filtra a otras libs. `time.sleep` se anula (los retries corren instantáneos).
2. **Bóveda de juguete aislada — y también es un ASSERT.** La fixture autouse
   `sin_tocar_la_boveda_real` intercepta el **único writer** del repo (D-53) y explota si un test
   escribe bajo el `vault/` real. Hermana de `sin_red`, y por el mismo motivo: esta promesa vivía en
   prosa y **nadie la sostenía** — medido el 2026-08-26, tres tests de `discover` creaban
   `vault/config/registro/ica.yaml` en cada corrida. En una instancia eso appendearía una entrada
   falsa al único artefacto no regenerable de la bóveda. `lib_config` resuelve rutas por constantes de módulo derivadas
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
   "antes").
   ⛔ **Y el rojo tiene que ser por la AUSENCIA DEL COMPORTAMIENTO, no por el andamiaje.** Un
   `ImportError` porque el símbolo todavía no existe sirve; una falla **en la aserción** sirve; una
   falla armando el escenario —mock con la firma equivocada, fixture incompleta— **no especifica
   nada** y encima va a seguir fallando después de implementado, haciendo perder horas persiguiendo
   un fantasma que era el mock. Medido acá el 2026-08-26: dos tests de la misma tanda fallaron con
   `TypeError: list indices must be integers` y `KeyError: 'facets'` — se vio rojo y no significaba
   nada. Un test de comportamiento nuevo nace con `@pytest.mark.xfail(strict=True)`, para que el
   runner sostenga la disciplina en vez de la memoria de quien lo escribe.
   Para **lotes** de ≥3 ítems que tocan el mismo código, el ciclo se hace con roles separados
   (spec → tests → implementación, agentes distintos): ver `docs/playbook-spec-tests.md`. Un lote
   hecho así **no necesita el gate de mutación en su tanda**.
   ⛔ Y la cobertura contra la spec se audita **dos veces**, requisito por requisito: la audita el
   agente de tests (paso 2) y **la vuelve a auditar el árbitro** (paso 5), sin confiar en el
   reporte. Un requisito que ningún test verifica es un deseo, no un contrato. Medido en el primer
   lote: 26 tests y **tres requisitos sin cubrir** — y el peor lo había **reportado por escrito el
   implementador** sin que el árbitro actuara. El protocolo completo —incluidos el porqué medido, la trampa del `.pyc` al mutar y la
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
| `test_make_notes.py` | stubs (star/concept/paper/web), migración de `disputes` a posiciones explícitas (#71: materializa el polo implícito, degrada sin destruir), `vista_block` ramificado por tipo de sujeto (#188 lo renombró desde `extraction_block`: la sección es `## Vista — <sujeto>`; unitario + matriz de ramas), retro-linkeo add-only, `unpend_note`, `excluded_table` (escapes), puntero de búsqueda en la cabecera, `pdf_source` (eprint vs publicado), idempotencia | puro FS |
| `test_triage.py` | carga y persistencia de decisiones en el registro versionado (sin mergear el `triage.json` viejo), `--drop` y `--drop-source` (motivo obligatorio, carriles que no se pisan), listado sin `ads.json`, `--migrate` del `triage.json` legacy, contrato con `query_ads.load_triage` | puro FS |
| `test_extraction_prompt.py` | INV-100: el prompt del fan-out de extracción se **genera**, no se escribe a mano. Patrones de búsqueda por tipo de sujeto (abreviatura astronómica vs sigla de tema), caveat de dos columnas y salvedad de OCR **sólo cuando aplican**, ruta de salida por bibcode, y que el prompt **no suplique exactitud** (RSOS 2025: pedirla la duplica) | fixtures sintéticos |
| `test_multicolumn_matching.py` | invariantes de la estrategia de matcheo en `.txt` a dos columnas (#44/#46): escalera de acortamiento, canaleta, normalización que empalma columnas | fixtures sintéticos |
| `test_lint.py` | cada categoría con su caso sembrado + exit codes; espejo ficha↔ground-truth (#70: qué planetas —no cuántos— y campo por campo), extraído pero no sintetizado (#75), vocabulario cerrado de `role` (#73), disputas con posiciones explícitas (#71), detectores de los schemas viejos que el lector ya no mira | bóvedas mínimas por escenario |
| `test_check_retractions.py` | parseo Crossref (`updated-by`, fechas), fallback por título, estampado idempotente de `retracted` y `corrections`, exit codes | `requests` falso |
| `test_ingest_theme.py` | despacho por `source`, validaciones de `sources:`, flujo `pending`, aviso de fuente ya descartada, copia de PDFs, orden de la cadena ads | `run()` y `make_notes.*` grabadores |
| `test_ingest_star.py` | orden canónico de la cadena de estrellas, aborto al primer fallo, retracción ≠ fallo, hand-off que nombra los pasos salteables | `run()` grabador |
| `test_trace_invariants.py` | recolector de trazabilidad `@inv`: registro canónico desde `docs/contrato.md` §3, la marca sólo en comentario/docstring (adversarios: mención en prosa, `@inv` dentro de un string literal, auto-marcado del propio recolector), marca huérfana bloqueante, ratchet, contrato ilegible ⇒ rc 2 sin cero inventado | repo de juguete |
| `test_apply_fixes.py` | el aplicador de correcciones del fan-out (#197): reemplazo exacto de una fila, localización del bloque **multilínea** por su forma normalizada, colisión de dos correctores sobre el mismo bloque detectada **antes** de tocar nada, fusión explícita `_fusionados` que gana, todo-o-nada, sangría preservada, dry-run por default | puro FS |
| `test_harvest_views.py` | el cosechador del fan-out (#188/#191): `is_extraction` como primera compuerta (INV-103), estampado de la vista con `fecha`/`txt`/`lente`, merge add-only de `methods`/`thesis_links`/`role`, la sección sólo mientras sea la plantilla del stub | puro FS |
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

El lint tiene **125 categorías**; el generador sintético sabe sembrar **16 anomalías**, y
`test_conteos_exactos` puede afirmar *"reporta exactamente estos K, ni uno más"* sólo sobre esas.
El resto queda cubierto de otra forma —el corpus limpio tiene que dar **cero en las 125** salvo cuatro
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

Los tres números (125 categorías, 16 anomalías, 4 de ruido declarado) **salen del código, no de acá**:
los cruza `test_conteos_exactos`, así que agregar una categoría al lint sin sembrarla deja el
desbalance a la vista en vez de esconderlo.

Emitir el schema vigente destapó además un bug real del lint: la tabla `## Papers` materializada
lista **todo** paper del sujeto con su `[[stem]]`, así que satisfacía sola el proxy de *extraído
pero no sintetizado* — la máquina "citaba" por su cuenta cada paper que el humano no había
sintetizado, y la categoría no podía disparar nunca (medido: 4 → 0).

## Lo que CI tiene y esta máquina no (2026-08-24)

La suite promete *"sin red ni binarios externos — todo mockeado"*, y **el push de v1.36.0 rompió los
dos jobs de CI** aunque acá estaba todo verde. Las dos causas son la misma clase de error —**probar
en un entorno más rico que el de producción**— y valen como advertencia permanente:

1. **Un test dependía de `pdftotext` real.** `test_txt_bajo_otro_slug_se_reusa` (D-18) se olvidó de
   mockear `shutil.which`, cosa que su test hermano de al lado sí hace. Pasaba en cualquier máquina
   con poppler instalado y moría en CI, que no lo tiene. Llevaba varias tandas escrito: **nunca
   había corrido en CI** porque esos commits no se habían pusheado.
2. **El lint pasó a depender de `requests`.** Su job instala **sólo `pyyaml`** —el propio workflow lo
   promete: *"Sólo necesita pyyaml + stdlib"*— y al mover la comparación de lentes (D-49) `lint.py`
   empezó a importar `query_ads`, que importa `requests`. En CI el import fallaba, el fallo caía en
   *no evaluado* —que cuenta para el exit— y **el lint salía 1 sobre una bóveda sana**: el chequeo
   que existe para no producir falsos limpios se volvió un falso rojo.

Las dos quedaron con red. La segunda además movió código: la comparación de lentes vive ahora en
`lib_config` (es config y regex, sin una línea de red) y sólo `lens_used` quedó en `query_ads`.

**Cómo reproducir el entorno de CI acá**, que es lo que hubiera evitado las dos:

```bash
python -m venv /tmp/cienv && /tmp/cienv/bin/pip install pyyaml requests numpy pytest
mkdir -p /tmp/binmin && for b in sh bash git env ls cat; do ln -sf "$(command -v $b)" /tmp/binmin/$b; done
env PATH=/tmp/binmin /tmp/cienv/bin/python -m pytest tests/ -q      # sin pdftotext/tesseract/npx
```

## Fuera de alcance (deliberado)

- Respuestas reales de ADS/NEA/Crossref (cambian; lo que se fija acá es el **parseo y la
  lógica**, no el schema remoto — si ADS cambia el schema lo detecta el uso, no esta suite).
- La calidad de extracción de `pdftotext`/`tesseract`/`defuddle` (binarios de terceros).
- Los skills (`.claude/skills/`) y todo lo que ejecuta el LLM.
- Dataview/Obsidian (los bloques generados se chequean como texto, no se ejecutan).

---

## Las nueve redes que corren al escribir código (regla permanente, 2026-08-24)

Salieron de una sesión en la que **los bugs los encontraron agentes leyendo, no la suite**. Cada una
ataca una clase de defecto que se repitió, y las nueve son deterministas: nada acá depende del
juicio de un modelo.

⚠ **La 9 se agregó el 2026-08-28 (AUD-212); la numeración es la de `CLAUDE.md` §*las nueve redes*,
que manda (AUD-228: los dos docs tenían la 8 y la 9 cruzadas).** El mapa de `docs/trazabilidad.md` mide *que alguien
puso la marca*, no que la marca esté sobre código que el test cubre — que es la primera de las dos
lecciones de método de la pasada `/auditar`. El gate vacía cada implementación marcada `@inv` y
corre **sólo el test marcado**: si pasa, esa fila afirma una cobertura que no existe. Primera
corrida sobre 143 filas: **20 atribuciones falsas**, todas cerradas moviendo la marca al test que sí
cubre el símbolo (ninguna se cerró borrando una fila). Sobre-reporta y nunca da falso limpio, por
dos motivos que conviene saber: corre **un** test, así que un símbolo que otro test sí cubre aparece
igual; y muta a `return None`, así que un predicado cuya rama FALSE es la que el test ejercita
sobrevive por coincidencia (`ocr_available` fue el caso medido) — la salida ahí es marcar un test
que ejerza la rama verdadera, no aflojar el gate.

| # | Qué caza | Cómo se corre |
|---|---|---|
| 1 | Tests que **pasan por construcción** | `python tools/mutar.py --diff` (o `<archivo>`) |
| 2 | Promesas de **schema compartido** que son sólo prosa | `tests/test_backends_schema.py` (tier 0) |
| 3 | Un **doble** con distinto contrato que la función real | test de paridad al lado del doble |
| 4 | Funciones que **nadie ejecuta** | `pytest tests/poblada/test_cobertura.py -m poblada` (~11 s) |
| 5 | La **doc afirmando cosas del código** | `tests/test_docs_ejecutables.py` (tier 0) |
| 6 | Un script que **pisa lo que ya escribió** | correr dos veces y hashear `vault/**/*.md` (ver abajo) |
| 7 | Un símbolo **nuevo con nombre en castellano** | `tests/test_idioma_codigo.py` (tier 0) |
| 8 | Un condicional que **no decide nada** (una regla escrita a medias, #319) | `tests/test_codigo_muerto.py` (tier 0) |
| 9 | Una fila del mapa que **atribuye cobertura que no existe** (AUD-212) | `python tools/mutar.py --trazabilidad` (~20 min) |

⚠ **La 6 faltaba acá y estaba en `CLAUDE.md`** (#148). El doc normativo titulaba *"las **seis** redes"* (hoy son nueve)
y delega el detalle en este archivo, que publicaba cinco — así que la regla de idempotencia se caía
exactamente en la frontera entre los dos. Vale para **todo script que escriba en `vault/`**, no sólo
para los de `scripts/`: la idempotencia es invariante del framework («la cadena es idempotente:
refrescar es seguro») y un script de una sola operación escribe en la bóveda igual que uno
versionado. El chequeo cuesta una línea:

```bash
H=$(find vault -name '*.md' -exec md5sum {} + | sort | md5sum); <el comando>; \
  [ "$H" = "$(find vault -name '*.md' -exec md5sum {} + | sort | md5sum)" ] && echo IDEMPOTENTE
```

Es sobre **contenido**, no sobre la bitácora: hashea `vault/**/*.md` y **no** el registro, que por
D-28 tiene que CRECER en cada corrida. Las dos reglas conviven porque miden cosas distintas — la
nota no puede cambiar si no cambió lo que afirma; el registro tiene que crecer aunque no cambie nada.

**La red 5 creció el 2026-08-24, porque tenía el mismo agujero que perseguía**: validaba que el
*script* existiera, no que el *flag* existiera — y `CLAUDE.md` mandaba a correr
`make_notes.py --restamp-keywords`, un flag que el issue que lo prometió nunca implementó. Hoy son
**catorce** chequeos (`grep -c '^def test_' tests/test_docs_ejecutables.py`):

| Chequea | Qué agujero cerró |
|---|---|
| los `tests/x.py::test_y` que nombra la doc existen | referencias a tests borrados |
| los `scripts/x.py` que invoca un skill existen y compilan | un skill que llama a un script muerto |
| los `scripts/x.py` que nombra la doc existen | scripts renombrados o borrados |
| los `--flag` que la doc nombra los declara el argparse de **`scripts/` o `tools/`** | un flag inventado, o el typo en un flag de `tools/` que nadie chequeaba (#339) |
| los archivos de config que nombra la doc existen | rutas de `vault/config/` renombradas |
| los `--flag` que nombra la doc existen — en bloque de comandos **y en prosa** | `--restamp-keywords` inventado; `--topic` sobrevivió a R-5 dentro de una frase |
| los flags declarados **retirados** siguen retirados | la lista de excepciones convirtiéndose en colador |
| ningún estado del contrato se inventa por fila | tres filas evadían `parcial` con un paréntesis ad-hoc |
| los conteos del encabezado son los de las filas | un resumen escrito a mano que envejece solo |
| la doc no apunta al código **por número de línea** | los siete punteros de `contrato.md` apuntaban al renglón equivocado, uno a otro invariante |
| el diagrama de la cadena de `docs/ingesta.md` respeta el orden canónico | el diagrama ponía `extract_fulltext` antes de `make_notes` y omitía `check_retractions` |
| todo script que la doc invoca como comando tiene `main()` | `citation_index.py` corría, no imprimía nada y salía 0 sin construir el índice |
| el alcance de hipótesis (D-34) tiene invariante propio, no el prestado | el mapa atribuía mal e inflaba «con implementación marcada» |
| la plantilla del bloque de verificación no tiene columna de **grado** | `Score` 0–10 reintroducía el eje que `parcial` había dejado |
| la plantilla que publica la doc la parsea el mismo código que la chequea | ocho columnas en la doc, posiciones fijas 4 y 5 en el parser → `--cierre` en rojo permanente |

**Cuándo**: 2, 5, 7 y 8 corren solas en tier 0. La 4, al cerrar un issue; la 9, a pedido (~20 min).
**La 1 (barrido de mutación) NO se corre salvo pedido explícito** (decidido 2026-08-27; ver la cadencia en
`CLAUDE.md`) — es la única que cuesta y la única que distingue "el test pasa" de "el test
**podría** fallar", y por eso su suspensión está fechada y declarada en vez de ser un olvido.
⚠ Hasta esa corrección la misma frase decía las dos cosas: «NO se corre salvo pedido» y «al
escribir cada función nueva».

> **El barrido corre en DOS ETAPAS desde #187** (2026-08-28). El costo dominante no era correr la
> suite: era **buscar el test asesino en el lugar equivocado**. `_suite_verde` ya usaba `-x`, así
> que un mutante que muere corta en el primer fallo — pero pytest recorre los archivos en orden
> alfabético, y mutar algo de `triage.py` pagaba casi toda la suite antes de llegar a
> `tests/test_triage.py`, que es justo el test que lo mata. Ahora: (1) se corre sólo
> `tests/test_<módulo>.py`; (2) **sólo los sobrevivientes** pagan la suite completa. Una muerte en
> la etapa 1 es una muerte, así que **el conjunto de sobrevivientes no cambia**; sin archivo 1:1 la
> etapa se saltea (no se aproxima).
>
> Medido el 2026-08-28, mismos sobrevivientes (`[]`) en las dos ramas: `triage.py` (17 funciones,
> casi al final del alfabeto) **143,6 s → 8,0 s**; `apply_fixes.py` (5 funciones, la primera)
> 4,5 s → 1,7 s. Los dos extremos confirman el diagnóstico: la ganancia **es** la distancia entre
> el test asesino y el arranque del alfabeto.
>
> ✅ **`--todo` RE-MEDIDO el 2026-08-31 (v1.163.0): 32,5 min (1951 s) sobre 655 funciones = 2,98 s
> por mutante** — `scripts/` (631) **más `tools/`** (24), que entró al alcance con #345. La corrida
> gemela sobre `scripts/` solo, ese mismo día y esa misma máquina, dio **28,9 min (1737 s) sobre
> 631**: o sea que `tools/` cuesta **+214 s (+12,3 %)** y aporta **cero** sobrevivientes. ⚠ El
> número viejo —11,3 min sobre 464, del 2026-08-28— no es comparable con ninguno de los dos: cambió
> la población y cambió el costo unitario, porque la suite tier 0 pasó a **63 s** y cada
> sobreviviente de la etapa 1 la paga entera (regla de método 5: se declara, no se elige uno).
> El `~1 h` que motivó la prohibición es de antes de la partición y tampoco es comparable. Con
> ese número el barrido pasa a ser **recomendado al cerrar una tanda**, no sólo a pedido — esa
> corrida encontró tres sobrevivientes que la revisión no había visto, dos de ellos tests escritos
> ese mismo día que pasaban por construcción. ⚠ Correlo con el **árbol quieto**: copia el repo al
> arrancar, así que si seguís editando su resultado describe un árbol que ya no existe (#199).

> **La mutación DIRIGIDA es otra operación, y la prohibición no la cubre (#204, 2026-08-28).** El
> barrido no se corre salvo pedido explícito; la dirigida **sí**, y es un paso al escribir una
> función con guardas: rompé cada guarda que el módulo promete y corré su archivo de tests.
>
> ```bash
> python tools/mutar.py --dirigida scripts/apply_fixes.py            # todas las funciones
> python tools/mutar.py --dirigida scripts/apply_fixes.py --solo find_block
> ```
>
> Muta **un** módulo, corre **sólo `tests/test_<módulo>.py`** y **no escala**: ~0,44 s por mutación
> (medido, copia del repo incluida: 17 mutaciones de `triage.py` en 7,4 s). En la tanda #196/#197,
> hecha a mano, tres mutaciones sobre las tres guardas de `apply_fixes.py` dejaron **dos tests
> falsos** al descubierto.
>
> ⚠ **No es el gate y no toca el ratchet.** Como no escala, puede marcar SOBREVIVE algo que otro
> archivo de tests sí mata: **sobre-reporta sobrevivientes y nunca da falso limpio** — la dirección
> segura. Y **rehúsa** en vez de degradar a la corrida cara cuando el módulo no tiene archivo de
> tests 1:1 o no tiene ninguna función mutable: cero mutaciones **no** es "murieron todas" (el bug
> estaba en la primera versión de este modo — `ingest_star.py` es todo `main`, que está exento, y
> cerraba con un ✅ sin haber medido nada).

> **Y un TERCER modo: la mutación de GUARDAS (AUD-213, 2026-08-28).** Vaciar el cuerpo de una
> función no mide sus condiciones, así que un módulo donde **mueren todos** los mutantes sigue sin
> decir nada sobre sus guardas — medido por un subagente leyendo el código: `entity.py` **30 de 84**
> y `harvest_views.py` **18 de 72** sin test que las distinga. Las tres guardas de `apply_fixes.py`
> de la tanda #196/#197 hubo que romperlas **a mano** justamente porque el gate no sabía hacerlo.
>
> ```bash
> python tools/mutar.py --guardas scripts/entity.py                # las 55 guardas del módulo
> python tools/mutar.py --guardas scripts/entity.py --solo delete  # sólo las de una función
> ```
>
> Contesta otra pregunta: ***¿algún test ejercita el caso que esta guarda ataja?*** Muta cada `if`
> de adentro de una función a `False` —la guarda nunca dispara— y, en un `and`/`or`, **cada cláusula
> por separado**, neutralizada con la identidad de su operador (`True` dentro de un `and`, `False`
> dentro de un `or`), de modo que la guarda **sigue** disparando por las otras: `if a and b` con
> tests que sólo dan `a=False` nunca ejercita `b`, y sólo el mutante por cláusula lo dice. Un `elif`
> es un `If` anidado y entra; el `if` de una comprensión no es un `ast.If` y queda afuera; una
> condición **constante** se saltea, porque reescribir `False` como `False` no cambia nada y saldría
> SOBREVIVE — un hallazgo que la herramienta inventó.
>
> ⚠ **Mismo contrato que la dirigida** (un módulo, su archivo de tests, no escala, sobre-reporta
> sobrevivientes, **no toca el ratchet** — que cuenta funciones, y mezclar dos poblaciones en un
> número dejaría al techo sin significado), **con una diferencia**: es el único de los tres modos
> que **chequea la baseline**. Con `tests/test_<módulo>.py` ya en rojo toda guarda «muere» por el
> motivo equivocado y el modo cerraría en verde sobre un módulo que nadie midió — #202 dentro de la
> herramienta que audita los tests. Sale **no evaluado** (rc 2), no 0.
>
> ⛔ **Y un `--solo` sin nada que mutar sale en TRES estados, no en uno (#335).** Hasta 1.141.0 el
> mensaje era *«no tienen guardas en `<mod>` (o no existen)»* para las dos causas, que piden
> acciones **opuestas**: **exenta** (existe y está en `EXENTAS` → *mové el condicional a una función
> propia*, que es lo único que hace que alguna red lo mire), **sin guardas** (existe, no exenta, sin
> un solo condicional mutable → cero por causa legítima) y **no existe** (typo en `--solo`). Los
> tres siguen siendo **no evaluado** (rc 2) —nada se midió—, pero con su motivo, que es lo que D-43
> pide. Costó caro una vez: el guard nuevo de #331 vivía dentro de `main` y **ninguna red de
> mutación lo miraba**; lo movió el implementador por criterio propio, no porque la herramienta se
> lo dijera.
>
> ⛔ **Y los TRES modos cierran por la misma función (#339): `tools/mutar.py::report_states`.**
> #335 escribió el reporte de tres estados y lo cableó en **uno solo**; `--dirigida` y
> `--trazabilidad` siguieron con el texto fusionado —y `--dirigida` sin siquiera el hedge:
> `--solo main scripts/triage.py` contestaba *«no existen en triage.py: ['main']»* sobre una función
> que existe y tiene **56** `if`—. Es el molde de #215/#324/#335: la misma regla en varios lugares
> ya divergió tres veces acá. En `--trazabilidad` los estados son otros —`no_existe` (no es fila de
> §3 del contrato) · `retirado` (lo es y está retirado a propósito, así que no lleva marcas) ·
> `sin_marcas` (fila viva a la que le falta el `@inv`: el remedio es **agregarlo**, no corregir el
> argumento)— y rehúsa **en cuanto uno** de los pedidos no se puede auditar, aunque el resto sí: se
> pidieron N y se midieron M < N.
>
> ⛔ **`tools/` ENTRÓ al alcance de las redes 1 y 4 (#345).** `ALCANCE` es hoy `("scripts",
> "tools")` y la red 4 (`tests/poblada/test_cobertura.py`) **importa esa constante** en vez de
> repetirla, así que las dos redes no pueden divergir en silencio. El argumento: acotarlas a
> `scripts/` dejaba sin red a **la herramienta que las ejecuta** —medido, 5 guardas de
> `tools/mutar.py` sin un solo test que las distinga: `_directed::if sobreviven` y las cuatro de
> `_trazabilidad`—. #339 ya había arreglado el **mensaje** (decir «fuera de alcance» en vez de negar
> un `tests/test_mutar.py` que existe); lo que quedaba era la decisión, y el usuario la tomó.
>
> ⛔ **La única exención es `tools/refresh_issues.py`, y se DECLARA con su motivo** —
> `mutar.EXENTOS_MODULO`, no por omisión del alcance. Son 59 líneas de cliente HTTP contra la API de
> GitHub y la **regla de método 1** manda probar un cliente de red contra el **servicio real**: un
> test con la red falseada validaría que el cliente funciona, no que el contrato se cumpla, así que
> mutarlo sólo mediría si el doble está bien escrito. Sin el mapa, *«no lo mira nadie»* y *«no lo
> mira nadie POR ESTO»* se leen igual desde afuera — y el remedio que la herramienta sugeriría
> (escribir el archivo de tests) sería justo lo que la regla prohíbe.
>
> Con eso `scope_refusal` tiene **tres** estados con tres acciones opuestas: *fuera de alcance*
> (`docs/`, la raíz: nada que escribir) · *exento* (leé el motivo y decidí si sigue valiendo) · *no
> hay `tests/test_<mod>.py>`* (hueco real: escribí el archivo). El barrido **nombra** al exento con
> su motivo antes de sacarlo, y una selección **toda** exenta sale `no evaluado` (rc 2): un 0 sobre
> cero mutantes comparado contra el techo sería el falso limpio adentro del detector de falsos
> limpios.
>
> ⚠ El splice corta por **offset de bytes UTF-8**, no de caracteres: `ast` reporta `col_offset` en
> bytes y este repo tiene prosa acentuada en casi toda línea. Cortar el `str` partiría la condición
> al medio y el mutante moriría por `SyntaxError`, o sea por el motivo equivocado otra vez. Lo fija
> `test_toda_guarda_del_ALCANCE_produce_codigo_QUE_PARSEA`, que parsea los **2204** mutantes de
> `scripts/` + `tools/` (2134 + 70, medidos el 2026-08-31). El **1503** que decía acá se midió sobre
> `scripts/` solo y sobre un corpus más chico: son dos poblaciones distintas y se declara el cambio
> en vez de comparar los números (regla de método 5).

**Cómo se leen los ratchets** (`tools/mutacion-ratchet.yaml`, `tools/cobertura-ratchet.yaml`): son
**deuda medida**, no objetivos. El número sólo baja; subirlo hay que justificarlo en el commit. Un
techo en 0 sería rojo permanente, y un rojo permanente se deja de mirar.

### Lo que estas redes NO reemplazan

El juicio: *¿el código hace lo que su prosa promete?* Eso lo encontró un agente tres veces en un
día y ningún assert lo habría visto. La forma correcta de institucionalizarlo es que **el agente
emita tests, no veredictos** — un veredicto de modelo no es reproducible y no sirve de red de
regresión; un test que él propuso, sí. (Sin decidir todavía; anotado.)

> Las **seis reglas de método** de las que salen estas redes están en `CLAUDE.md`,
> sección *Seis reglas de método*. Acá va sólo la mecánica.

### Dos trampas ya pisadas, para no repetirlas

- **`tools/mutar.py` trabaja sobre una COPIA del repo.** La primera versión mutaba en el lugar y
  restauraba en un `finally`; un `pkill` a mitad de camino dejó `check_retractions._mailto` con el
  cuerpo en `return None` en el árbol de trabajo — y la suite siguió en verde, porque esa función
  es justo una de las que ninguna prueba mata. Un harness que puede corromper lo que audita no
  sirve por más `finally` que tenga.
- **Un test verde recién escrito no cuenta hasta que lo viste morir — por la RAZÓN que prueba.**
  Pasó dos veces el mismo día: el test se escribió, pasó a la primera, y sólo la mutación mostró si
  servía. Y la mitad que faltaba enunciar (#202): **ver el rojo no alcanza, hay que leer el mensaje
  del fallo**. Medido en la tanda #196/#197 — un test murió porque su setup no creaba ninguna nota
  de paper (universo vacío), no por el defecto, y arreglado el setup **pasaba sin el fix**; y dos de
  los tres tests de `apply_fixes.py` sobrevivieron a mutar la guarda que decían proteger, porque el
  flujo caía en otra guarda que también abortaba la escritura. La pregunta es *¿murió por la línea
  que estoy probando?* y se contesta con `python tools/mutar.py --dirigida scripts/<módulo>.py`.
