# Operación de la bóveda — referencia

> La contracara del `README.md` (que es presentación + quickstart): el manual del **día a día** —
> dependencias completas, layout del repo, scripts sueltos, cómo traer mejoras del framework, qué
> viaja entre máquinas y el setup fino de Obsidian. Para el *schema* con el que opera el agente
> (frontmatter, reglas, operaciones LLM) ver `CLAUDE.md`.

## Dependencias

**Python** (pip): `pip install -r requirements.txt` (pyyaml, requests, astroquery).

**Sistema:**
- **`pdftotext`** (paquete *poppler*) — extracción de fulltext al ingestar. Debian/Ubuntu
  `sudo apt install poppler-utils` · macOS `brew install poppler` · Fedora
  `sudo dnf install poppler-utils` · Windows `conda install -c conda-forge poppler`.
- **git-lfs** — PDFs versionados. `sudo apt install git-lfs` · `brew install git-lfs`; luego
  `git lfs install` **una vez por máquina** (sin esto se commitean binarios crudos).
- **Opcional `tesseract-ocr`** (`sudo apt install tesseract-ocr` · `brew install tesseract`) —
  rescate por **OCR** de PDFs escaneados o con fuentes rotas (mojibake): con tesseract instalado,
  `extract_fulltext.py` cae solo a OCR cuando la capa de texto no es legible y el `.txt` queda
  marcado `source: ocr` (**citable con salvedad**: símbolos/notación pueden diferir).
- **Opcional `curl`** (estándar en Linux/macOS) — `fetch_pdf.py` lo usa de fallback para
  publishers cuyo WAF rechaza a python-requests.

**Token ADS** gratis en <https://ui.adsabs.harvard.edu/user/settings/token> (~5000 consultas/día);
va en `vault/config/ads_dev_key` (gitignored) o en la variable `ADS_DEV_KEY`.

Nada de esto hace falta para **consultar** una bóveda ya poblada (el fulltext se commitea) — sólo
para ingestar. En Windows, los comandos de shell corren en Git Bash o WSL.

## Layout del repo

| Ruta | Qué hay |
|---|---|
| `vault/config/objective.yaml` | **El objetivo de la bóveda** + clasificador de relevancia (papers core). Editar para instanciar. |
| `vault/raw/pdfs/<slug>/` | PDFs (git-lfs). |
| `vault/raw/fulltext/<slug>/*.txt` | Texto completo (pdftotext; si la capa de texto es ilegible, OCR marcado `source: ocr` — citable con salvedad) para búsqueda local y re-extracción. |
| `vault/raw/ground_truth/<slug>.json` | Hechos auditables (NASA Exoplanet Archive + SIMBAD). |
| `vault/raw/refs/` | Fuentes de diseño del patrón (gist Karpathy, guía de implementación). |
| `vault/wiki/stars/<slug>.md` | Ficha por estrella (entidad). **Frontmatter = fuente de verdad** (sp_type, P_rot, planetas, indicadores esperados, métodos). |
| `vault/wiki/papers/<bibcode>.md` | Una nota por paper (metadata ADS + abstract + extracción LLM). |
| `vault/wiki/concepts/<área>/` | Notas transversales. Áreas **abiertas** (cualquiera); `concept_areas` (objective.yaml) es referencia para el typo-check, no restricción — `methods`/`hypotheses` reservadas. |
| `vault/wiki/queries/` | Preguntas contestadas contra el corpus. |
| `vault/wiki/matrices/method_star.md` | Matriz método × estrella = huecos + backlog. |
| `vault/wiki/index.md` | Catálogo de la wiki (se actualiza en cada operación). |
| `vault/wiki/log.md` | Registro append-only de operaciones. |
| `vault/config/stars.yaml` · `vault/config/topics.yaml` | Estrellas / temas de la bóveda (nombres canónicos + alias). |
| `vault/config/ads_dev_key` | Token NASA ADS — **GITIGNORED** (nunca se commitea). |
| `build/` · `outputs/` | **GITIGNORED** — intermedios de ingesta y reportes de lint. |

## Pipeline de ingesta (scripts/)

División de tareas: **scripts** bajan (determinista, rate-limited); **LLM** procesa (criterio).

**La cadena completa la corren los orquestadores** — `python ingest_star.py <slug>` (estrellas) y
`python ingest_topic.py <slug>` (temas; despacha por el campo `source`, incluido el modo off-ADS) —
cuyos headers son la **definición canónica del orden** (docs y skills apuntan ahí, no copian la
lista). Las piezas, para correr sueltas cuando hace falta un flag fino (`--rows`, `--all`,
`--force` de un paso):

```bash
cd scripts
python query_ads.py        <slug>   # ADS → build/<slug>/ads.json (metadata + relevancia + citation chaining)
python fetch_arxiv.py      <slug>   # PDFs a vault/raw/pdfs/<slug>/  (rate limit arXiv: 1 req/3 s)
python fetch_pdf.py        <slug>   # PDFs SIN arXiv vía resolver ADS (escaneos ADS c/token + publisher)
python fetch_ground_truth.py <slug> # NEA + SIMBAD → vault/raw/ground_truth/<slug>.json
python make_notes.py       <slug>   # genera vault/wiki/stars/ y vault/wiki/papers/ (idempotente; --force)
python extract_fulltext.py <slug>   # PDFs → vault/raw/fulltext/<slug>/*.txt
python check_retractions.py         # Crossref → marca `retracted` en papers retractados (red)
python lint.py                      # chequeo de salud → outputs/lint-<fecha>.md (exit 1 si hay bloqueantes)
```

Para TEMAS (en vez de estrellas): definir el tema en `vault/config/topics.yaml` y correr
`python ingest_topic.py <slug>` — el orquestador despacha según el campo `source` de la entrada:
`ads` (default) corre la cadena de arriba con `--topic` y **sin** `fetch_ground_truth` (no hay
NEA/SIMBAD para un tema); `web` / `local-pdfs` (modo **off-ADS**, opt-in) procesa la bibliografía
declarada en la lista `sources:` de la entrada — snapshots web citables vía `fetch_web.py` (defuddle)
y PDFs locales copiados a la bóveda con clave `AAAA+Autor` (ver skill `ingest-topic`). Luego:
extracción LLM (leer PDFs/fulltext → poblar `methods`, indicadores, P/K, síntesis), actualizar
`index.md` y appendear a `log.md`. Ver `CLAUDE.md` para las operaciones en detalle.

Los scripts tienen su **suite de tests** en `tests/` (pytest; sin red ni binarios externos —
todo mockeado; corre en CI junto al lint). Diseño y alcance en `tests/README.md`; correr con
`python -m pytest tests/ -q` desde la raíz. El **auto-benchmark** del verificador de citas
(`scripts/bench_verify.py`, modo benchmark del skill `verify-citations`) se corre a pedido con la
bóveda ya poblada.

## Mantener tu bóveda actualizada (traer mejoras del framework)

Tu bóveda es **una sola implementación**: el framework (scripts, skills, `CLAUDE.md`, `vault/.obsidian/`)
vive en Almagesto; vos le agregás contenido. Tu contenido no corre riesgo al mergear:
`vault/config/objective.yaml`, `vault/config/stars.yaml`, `vault/config/topics.yaml`, `vault/STATUS.md`,
`vault/wiki/index.md` y `vault/wiki/log.md` están marcados `merge=ours` en `.gitattributes` — un merge del
framework **nunca** los pisa (registrá el driver una vez por clon: `git config merge.ours.driver true`).

**Si instanciaste con "Use this template" (recomendado):** tu `origin` es *tu* repo y Almagesto es
`upstream` (lo agregaste al instanciar). Traés mejoras del framework mergeando upstream:

```bash
git fetch upstream && git merge upstream/main   # trae mejoras del framework; tu contenido (merge=ours) queda intacto
```

**Si clonaste directo** (`origin` = Almagesto): traés updates con `git pull`. Para pasarte a tu **propio**
repo, creá uno vacío, convertí Almagesto en `upstream` y poné el tuyo como `origin`:

```bash
git remote rename origin upstream            # Almagesto = de dónde vienen los updates
git remote add origin <URL-de-tu-repo>       # tu repo (crealo vacío primero)
git push -u origin main
# desde ahora, para actualizar:  git fetch upstream && git merge upstream/main
```

**Regla de oro:** no edites archivos de framework (scripts, skills, `CLAUDE.md`, `vault/.obsidian/`) en tu
bóveda — así los merges quedan limpios y sin conflictos. Todo tu trabajo vive en
`vault/config/objective.yaml` + tu contenido (`vault/wiki/`, `vault/raw/`), protegido por `merge=ours`. ¿Te falta una
funcionalidad del framework? Abrí un *issue* o *pull request* en Almagesto, o mantené un parche local
— no la metas inline en tu instancia, o el próximo merge te dará conflictos.

## Portabilidad (usar el repo en varias máquinas vía git)

El núcleo del flujo es portable: el texto completo (`vault/raw/fulltext/**/*.txt`) se commitea, así que
`grep`/lectura/escritura de `vault/wiki/` (las operaciones *query*, *test-hypothesis*, *verify*, *lint* y la
extracción LLM) funcionan **sin dependencias externas ni LFS**. Qué **no** viaja por diseño:

- **PDFs (`vault/raw/pdfs/**`, git-lfs):** sin `git lfs pull` quedan como punteros. No hace falta para
  re-consultar el corpus (el fulltext ya está commiteado); sólo para re-extraer texto o ingestar nuevo.
- **Datos crudos (FITS/PKL):** gitignored (`*.fits`, `*.pkl`). Cada ficha apunta a ellos con
  `data_local` (ruta local a los datos crudos de la estrella). Ese puntero es **machine-local**.
- **`build/`, `outputs/`:** gitignored (intermedios regenerables). Los scripts los recrean solos.

Sin rutas absolutas hardcodeadas: los scripts resuelven el root del repo desde `__file__`
(`scripts/lib_config.py`), no asumen `cwd` ni `/home/...`.

## Abrir la bóveda en Obsidian

El vault de Obsidian es la carpeta **`vault/`** (no la raíz del repo): así el grafo y el explorador
muestran sólo conocimiento, sin el andamiaje (`scripts/`, `CLAUDE.md`, …). Las consultas Dataview usan
rutas relativas a esa raíz, tipo `FROM "wiki/papers"`. Si abrís la raíz por error, el síntoma es un
grafo lleno de nodos ajenos a la bóveda (reportes de lint de `outputs/`, README, tests) y queda un
`.obsidian/` en la raíz — está gitignored y el lint lo marca WARN: borralo y reabrí `vault/`.

1. Obsidian → **"Open folder as vault"** → elegir la carpeta **`vault/`** del repo.
2. Instalar/activar el plugin **Dataview** (Settings → Community plugins → Browse → "Dataview" →
   Install + Enable). Sin él, los roll-ups de las fichas se ven como bloques de código.
3. En las opciones de Dataview, activar **"Enable JavaScript queries"** (la tabla de planetas de las
   fichas es `dataviewjs`).

La config compartible del vault se commitea (`vault/.obsidian/app.json`, `appearance.json`, etc.); lo volátil
por máquina (`workspace.json`, `cache`) y los plugins de comunidad (`vault/.obsidian/plugins/`) están
gitignored — instalá Dataview desde Obsidian (paso 2 de arriba).
