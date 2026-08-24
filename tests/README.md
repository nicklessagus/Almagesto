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
| **0** — siempre (default, CI en cada push) | todo `tests/*.py` | `python -m pytest tests/ -q` | ≤ 2,5 s |
| **1** — `poblada` (nightly / pre-release) | `tests/poblada/` sobre corpus sintético (~900 notas) | `python -m pytest tests/ -m poblada -q` | ≤ 90 s |
| **2** — `instancia` (sólo en la máquina del usuario; gate del deploy) | invariantes sobre una instancia REAL | `ALMAGESTO_INSTANCIA=/ruta/a/la/instancia python -m pytest tests/ -m instancia -q` | ≤ 60 s |
| todos | los tres | `ALMAGESTO_INSTANCIA=... python -m pytest tests/ -m "" -q` | ≤ 3 min |

`instancia` **sin** la env var **skipea con motivo visible**, nunca pasa en silencio: un tier que se
saltea sin decirlo es el mismo modo de falla que el "0 que no miró" (ver abajo).

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
   - **Validaciones de entrada** que abortan la cadena (`ingest_topic`, citekeys, sources).
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
| `test_ingest_topic.py` | despacho por `source`, validaciones de `sources:`, flujo `pending`, aviso de fuente ya descartada, copia de PDFs, orden de la cadena ads | `run()` y `make_notes.*` grabadores |
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

## Fuera de alcance (deliberado)

- Respuestas reales de ADS/NEA/Crossref (cambian; lo que se fija acá es el **parseo y la
  lógica**, no el schema remoto — si ADS cambia el schema lo detecta el uso, no esta suite).
- La calidad de extracción de `pdftotext`/`tesseract`/`defuddle` (binarios de terceros).
- Los skills (`.claude/skills/`) y todo lo que ejecuta el LLM.
- Dataview/Obsidian (los bloques generados se chequean como texto, no se ejecutan).
