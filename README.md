# Almagesto — template de wiki de conocimiento astro (patrón LLM Wiki)

[![CI](https://github.com/nicklessagus/Almagesto/actions/workflows/ci.yml/badge.svg)](https://github.com/nicklessagus/Almagesto/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Use this template](https://img.shields.io/badge/Use%20this-template-2ea44f?logo=github)](https://github.com/nicklessagus/Almagesto/generate)

Base de conocimiento mantenida por un LLM (patrón [LLM Wiki](vault/raw/refs/karpathy-llm-wiki.md) de
Karpathy) sobre **literatura astronómica**, organizada por **estrella** y por **concepto**. Reúne todo
lo publicado relevante (planetas, actividad, indicadores, métodos), en formato a la vez **legible**
(notas + grafo Obsidian + síntesis de huecos) y **máquina-legible** (frontmatter YAML que puede
consumir un agente o humano para armar código, un informe o un paper — siempre arrastrando las citas
`[[bibcode]]` correspondientes).

Es un **template**: el objetivo de cada bóveda (de qué trata, **qué papers son "core"**) se setea en
un solo archivo, `vault/config/objective.yaml`. El resto del repo es framework reusable.

## Instanciar (crear tu bóveda)

**Recomendado — botón "Use this template":** en la [página del repo](https://github.com/nicklessagus/Almagesto)
apretá **"Use this template" → Create a new repository**. GitHub te crea un repo **propio** con esta
estructura y **historia limpia** (un commit inicial, sin el historial de desarrollo del framework) y sin
quedar ligado como fork. Después cloná *tu* repo nuevo y configurálo:

```bash
git clone git@github.com:TU_USUARIO/mi-boveda.git && cd mi-boveda
git config core.hooksPath scripts/hooks     # (opcional) pre-commit que corre el lint y bloquea si falla
git lfs install                             # PDFs por git-lfs — sin esto se commitean binarios crudos
                                            #   (sus hooks caen en scripts/hooks/, ya gitignorados)
git config merge.ours.driver true           # protege tus archivos de instancia en futuros merges
git remote add upstream https://github.com/nicklessagus/Almagesto.git  # de acá traés mejoras del framework
pip install -r requirements.txt             # pyyaml, requests, astroquery
echo "TU_TOKEN" > vault/config/ads_dev_key  # token ADS (gratis, gitignored) — o export ADS_DEV_KEY
```

> **Alternativa — `git clone` directo** (probar sin crear tu repo en GitHub): `git clone <este-repo>
> mi-boveda`. Tu `origin` queda apuntando a Almagesto (traés updates con `git pull`), pero no tenés
> remoto propio donde pushear tu contenido. Ver *Mantener tu bóveda actualizada* para pasarte a tu repo.

> **Token ADS** gratis en <https://ui.adsabs.harvard.edu/user/settings/token> (~5000 consultas/día); va
> en `vault/config/ads_dev_key` (gitignored) o en la variable `ADS_DEV_KEY`. Para **ingestar PDFs nuevos**
> necesitás `pdftotext` (paquete *poppler*), según tu OS: Debian/Ubuntu `sudo apt install poppler-utils` ·
> macOS `brew install poppler` · Fedora `sudo dnf install poppler-utils` · Windows
> `conda install -c conda-forge poppler` — y **git-lfs** (`sudo apt install git-lfs` · `brew install
> git-lfs`; luego el `git lfs install` de arriba, una vez por máquina). **Opcional:** `tesseract-ocr`
> (`sudo apt install tesseract-ocr` · `brew install tesseract`) para rescatar por **OCR** PDFs
> escaneados o con fuentes rotas (mojibake) — con tesseract instalado, `extract_fulltext.py` cae solo
> a OCR cuando la capa de texto no es legible, y el `.txt` queda marcado `source: ocr` (citable con
> salvedad: símbolos/notación pueden diferir). Ninguno de estos hace falta
> para consultar una bóveda ya poblada (el fulltext se commitea). En Windows, los comandos de shell de
> acá corren en Git Bash o WSL.

Después **definí el objetivo pidiéndoselo al agente** — no hace falta escribir YAML ni regex a mano. El
skill `setup` traduce tu foco (en palabras) a `relevance.topics` (los buckets que deciden qué paper es
*core*), lo **prueba contra ADS** y te muestra el corte para que lo apruebes:

> **Vos:** *"configurá la bóveda: quiero separar actividad estelar de señales planetarias en RV."*
>
> **Agente (skill `setup`):** arma los buckets (`rv`, `activity`, `method`…) y corre el preview
> (`query_ads.py --probe`, no baja nada):
> ```
> 41/50 CORE · top por citas  [CORE/—  · tópicos que matchearon]:
> [CORE]  812  Stellar activity and radial-velocity jitter in...    «rv,activity»
> [CORE]  333  Gaussian-process modelling to disentangle planets...  «rv,activity,method»
> [—   ]  210  A catalogue of nearby M dwarfs                        «(ninguno)»
> ```
> Afina la regex e itera hasta que el corte cierre → te deja `vault/config/objective.yaml` listo.

Con el objetivo definido, sumás estrellas/temas y los ingestás, también pidiéndoselo al agente:
*"bajá HD 152391"* (`ingest-star`) o *"investigá BSS sobre RV"* (`ingest-topic`).

**El objetivo es lo único específico de tu instancia** (`vault/config/objective.yaml`; editable a mano si
preferís: `name`/`description` + `relevance.topics`). Lo demás —forma astro: estrellas, planetas,
indicadores, ground-truth— es framework genérico y no se toca. Viene con un ejemplo (actividad estelar vs
RV) que sirve de formato y default funcional.

## De un objetivo a una ficha (qué hace un ingest)

Cuando le pedís ingestar una estrella o un tema, el agente:

1. **Busca en ADS** (por estrella: nombre + alias; por tema: keywords) y **clasifica** cada paper con tu
   `relevance.topics`: **core** = matchea ≥1 faceta y no es ruido; el resto queda **no-core**.
2. Los **core** se bajan (PDF + fulltext) y el LLM los **lee y destila** en la ficha: métodos, P/K/e,
   indicadores y por qué es relevante — cada dato con su cita `[[bibcode]]` (trazable hasta el PDF).
3. Los **no-core** no se bajan: quedan sólo listados (top por citas, con link a ADS) en un apéndice
   *"excluidos, por las dudas"* — por si alguno debería haber entrado.

El resultado es una **ficha autosuficiente** (resumen + tablas auto + huecos) que se entiende **sin abrir
ningún paper**, con todo lo que afirma trazable a su fuente.

## Skills del agente (`.claude/skills/`)

Las operaciones del patrón están empaquetadas como skills invocables (Claude las dispara solo por la
descripción, o el usuario con `/<nombre>`). Encapsulan la cadena mecánica + el criterio LLM:

| Skill | Cuándo | Qué hace |
|---|---|---|
| `setup` | "configurá la bóveda", "definí el objetivo" | Paso 0: traduce tu foco en palabras a `objective.yaml` (incluida la regex `relevance.topics`) y la **afina contra ADS con un preview** (`query_ads --probe`), para que NO escribas regex a mano. No ingesta. |
| `ingest-star` | "bajá/ingestá/agregá la estrella X" | Corre la cadena (`query_ads → fetch_arxiv → fetch_ground_truth → make_notes → extract_fulltext`) y hace la extracción LLM de los papers clave + síntesis + bookkeeping. |
| `ingest-topic` | "investigá a fondo el tema X" | Como ingest-star pero por TEMA: query ADS por keywords → concept durable en `concepts/`. Soporta temas off-ADS (opt-in) vía `source: web\|local-pdfs` + `sources:` en `topics.yaml`. |
| `append-knowledge` | "agregale este paper a la ficha X", "sumá este PDF al concept Y" | Pliega **una fuente puntual** (bibcode / PDF / URL) a una ficha/concepto **existente**: plomería mínima + extracción enfocada + síntesis a la nota viva. No crea entidades ni barre por query. |
| `test-hypothesis` | "hipótesis: …", "evidencia a favor/contra de …" | Testea un supuesto **durable** contra el fulltext y responde con veredicto citado; **a pedido del usuario** lo archiva en `concepts/hypotheses/` y taggea papers (`thesis_links`/`bearing`). |
| `query-corpus` | búsqueda/pregunta general (no hipótesis) | Responde contra índice + frontmatter + fulltext; archiva en `vault/wiki/queries/` **sólo si el usuario lo pide**. |
| `verify-citations` | cierre de toda operación con prosa `[[bibcode]]` | Chequea, afirmación por afirmación, que la fuente respalde el claim (1 subagente/par lee el fulltext). |
| `find-contradictions` | "buscá contradicciones", "¿qué papers discrepan sobre X?" | Barre un eje (estrella/parámetro o concepto) y confirma desacuerdos claim↔claim **entre** papers → propone `disputes[]` para que apruebes. |
| `maintain` | "actualizá X", "borrá el paper Y", "renombrá el slug", "re-clasificá" | Mantiene entidades **ya ingestadas**: refrescar con papers nuevos, borrar/renombrar limpio, re-clasificar tras cambiar `relevance.topics`, resolver backlog del lint. |

## Arquitectura (patrón LLM Wiki)

> El **schema de operación del agente** está en `CLAUDE.md` (raíz); el **estado** en `vault/STATUS.md`; el
> **catálogo** en `vault/wiki/index.md`. Diseño basado en
> [karpathy-llm-wiki](vault/raw/refs/karpathy-llm-wiki.md) +
> [starmorph-implementation-guide](vault/raw/refs/starmorph-implementation-guide.md).

**`vault/raw/`** (fuentes inmutables, las cura el humano) → **LLM** (compilador) → **`vault/wiki/`** (.md que el
LLM escribe y mantiene). Operaciones: **ingest / query / verify / lint**.

| Ruta | Qué hay |
|---|---|
| `vault/config/objective.yaml` | **El objetivo de la bóveda** + clasificador de relevancia (papers core). Editar para instanciar. |
| `vault/raw/pdfs/<slug>/` | PDFs (git-lfs). |
| `vault/raw/fulltext/<slug>/*.txt` | Texto completo (pdftotext; si la capa de texto es ilegible, OCR marcado `source: ocr` — citable con salvedad) para búsqueda local y re-extracción. |
| `vault/raw/ground_truth/<slug>.json` | Hechos auditables (NASA Exoplanet Archive + SIMBAD). |
| `vault/raw/refs/` | Fuentes de diseño del patrón (gist Karpathy, guía de implementación). |
| `vault/wiki/stars/<slug>.md` | Ficha por estrella (entidad). **Frontmatter = fuente de verdad** (sp_type, P_rot, planetas, indicadores esperados, métodos). |
| `vault/wiki/papers/<bibcode>.md` | Una nota por paper (metadata ADS + abstract + extracción LLM). |
| `vault/wiki/concepts/<área>/` | Notas transversales. Áreas **abiertas** (cualquiera); `concept_areas` (objective.yaml; ej. indicators/methods/activity/hypotheses) es referencia para el typo-check, no restricción — `methods`/`hypotheses` reservadas. |
| `vault/wiki/queries/` | Preguntas contestadas contra el corpus. |
| `vault/wiki/matrices/method_star.md` | Matriz método × estrella = huecos + backlog. |
| `vault/wiki/index.md` | Catálogo de la wiki (se actualiza en cada operación). |
| `vault/wiki/log.md` | Registro append-only de operaciones. |
| `vault/config/stars.yaml` · `vault/config/topics.yaml` | Estrellas / temas de la bóveda (nombres canónicos + alias). |
| `vault/config/ads_dev_key` | Token NASA ADS — **GITIGNORED** (nunca se commitea). |
| `build/` · `outputs/` | **GITIGNORED** — intermedios de ingesta y reportes de lint. |

## Pipeline de ingesta (scripts/)

División de tareas: **scripts** bajan (determinista, rate-limited); **LLM** procesa (criterio).

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
`python -m pytest tests/ -q` desde la raíz.

## Verify — chequeo claim↔fuente

Extensión propia de este template (el lint de Karpathy sólo valida salud estructural, no que la fuente
respalde la afirmación). Toda afirmación fáctica va **citada `[[bibcode]]` o marcada `inferencia`**. El
skill `verify-citations` descompone cada nota en pares (afirmación, bibcode) y lanza un subagente por
par que lee SÓLO ese `.txt` y devuelve `soportada|parcial|no-soportada|contradice` + cita textual
(una contradicción es candidata a disputa, no sólo cita rota). Ver `CLAUDE.md`.

## Mantener tu bóveda actualizada (traer mejoras del framework)

Tu bóveda es **una sola implementación**: el framework (scripts, skills, `CLAUDE.md`, `vault/.obsidian/`)
vive en Almagesto; vos le agregás contenido. Tu contenido no corre riesgo al mergear:
`vault/config/objective.yaml`, `vault/config/stars.yaml`, `vault/config/topics.yaml`, `vault/STATUS.md`,
`vault/wiki/index.md` y `vault/wiki/log.md` están marcados `merge=ours` en `.gitattributes` — un merge del
framework **nunca** los pisa (registrá el driver una vez por clon: `git config merge.ours.driver true`).

**Si instanciaste con "Use this template" (recomendado):** tu `origin` es *tu* repo y Almagesto es
`upstream` (lo agregaste en el paso *Instanciar*). Traés mejoras del framework mergeando upstream:

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
rutas relativas a esa raíz, tipo `FROM "wiki/papers"`.

1. Obsidian → **"Open folder as vault"** → elegir la carpeta **`vault/`** del repo.
2. Instalar/activar el plugin **Dataview** (Settings → Community plugins → Browse → "Dataview" →
   Install + Enable). Sin él, los roll-ups de las fichas se ven como bloques de código.
3. En las opciones de Dataview, activar **"Enable JavaScript queries"** (la tabla de planetas de las
   fichas es `dataviewjs`).

La config compartible del vault se commitea (`vault/.obsidian/app.json`, `appearance.json`, etc.); lo volátil
por máquina (`workspace.json`, `cache`) y los plugins de comunidad (`vault/.obsidian/plugins/`) están
gitignored — instalá Dataview desde Obsidian (paso 2 de arriba).

## Licencia

MIT — ver [`LICENSE`](LICENSE).
