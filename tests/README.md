# Tests de `scripts/` — diseño de la suite

Tests unitarios/integración de la **capa determinista** del framework (los 12 scripts de
`scripts/`). No testean la capa LLM (skills, extracción, síntesis) ni el contenido de una
bóveda real — para eso está `lint.py`, que es el "test suite" del *contenido*.

**Correr** (desde la raíz del repo):

```bash
python -m pytest tests/ -q
```

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
3. **Testear el contrato documentado.** Las expectativas salen de los docstrings, `CLAUDE.md` y
   `README.md` — no de "lo que el código hace hoy". Si un test falla, primero se triagea:
   ¿bug del script o expectativa mal leída?
4. **Los invariantes críticos primero.** Lo más cubierto es lo que más duele si se rompe:
   - **Idempotencia / no pisar extracción LLM** (`make_notes`, `unpend_note`,
     `merge_frontmatter_list` byte-a-byte, `--force` sólo donde está prometido).
   - **Cada categoría del lint** detecta su caso sembrado y el exit code separa
     bloqueante / WARN / backlog.
   - **Física del ground-truth** (`msini_earth` contra valores conocidos: Tierra, 51 Peg b)
     y la selección de masa NEA (msini vs best-mass, flags).
   - **Validaciones de entrada** que abortan la cadena (`ingest_topic`, citekeys, sources).

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
| `test_make_notes.py` | stubs (star/concept/paper/web), retro-linkeo add-only, `unpend_note`, `excluded_table` (escapes), idempotencia | puro FS |
| `test_lint.py` | cada categoría con su caso sembrado + exit codes | bóvedas mínimas por escenario |
| `test_check_retractions.py` | parseo Crossref (`updated-by`, fechas), fallback por título, estampado idempotente, exit codes | `requests` falso |
| `test_ingest_topic.py` | despacho por `source`, validaciones de `sources:`, flujo `pending`, copia de PDFs, orden de la cadena ads | `run()` y `make_notes.*` grabadores |
| `test_bench_verify.py` | extracción de pares (excluye blockquotes/fences/bloque de verificación), siembra por rotación (sin falsos-falsos), determinismo byte a byte, puntaje | puro FS |

## Fuera de alcance (deliberado)

- Respuestas reales de ADS/NEA/Crossref (cambian; lo que se fija acá es el **parseo y la
  lógica**, no el schema remoto — si ADS cambia el schema lo detecta el uso, no esta suite).
- La calidad de extracción de `pdftotext`/`tesseract`/`defuddle` (binarios de terceros).
- Los skills (`.claude/skills/`) y todo lo que ejecuta el LLM.
- Dataview/Obsidian (los bloques generados se chequean como texto, no se ejecutan).
