# Almagesto — template de wiki de conocimiento astro (patrón LLM Wiki)

Base de conocimiento mantenida por un LLM (patrón [LLM Wiki](vault/raw/refs/karpathy-llm-wiki.md) de
Karpathy) sobre **literatura astronómica**, organizada por **estrella** y por **concepto**. Reúne todo
lo publicado relevante (planetas, actividad, indicadores, métodos), en formato a la vez **legible**
(notas + grafo Obsidian + síntesis de huecos) y **máquina-legible** (frontmatter YAML que puede
consumir un agente o humano para armar código, un informe o un paper — siempre arrastrando las citas
`[[bibcode]]` correspondientes).

Es un **template**: el objetivo de cada bóveda (de qué trata, **qué papers son "core"**) se setea en
un solo archivo, `vault/config/objective.yaml`. El resto del repo es framework reusable.

> El **schema de operación del agente** está en `CLAUDE.md` (raíz); el **estado** en `vault/STATUS.md`; el
> **catálogo** en `vault/wiki/index.md`. Diseño basado en
> [karpathy-llm-wiki](vault/raw/refs/karpathy-llm-wiki.md) +
> [starmorph-implementation-guide](vault/raw/refs/starmorph-implementation-guide.md).

## Instanciar (crear tu bóveda)

```bash
git clone <este-repo> mi-boveda && cd mi-boveda
pip install -r requirements.txt                  # pyyaml, requests
sudo apt install poppler-utils                   # pdftotext (extract_fulltext.py)

# 1) Definí TU objetivo — es lo único específico de tu instancia:
$EDITOR vault/config/objective.yaml                    # name/short/description + relevance.topics (papers core)

# 2) Poné tu token ADS (gratis, NO se commitea — está gitignored):
echo "TU_TOKEN" > vault/config/ads_dev_key             # o export ADS_DEV_KEY=...

# 3) Agregá tu primera estrella a vault/config/stars.yaml y ingestala (o pedíselo al agente):
cd scripts && python query_ads.py <tu_slug>      # <tu_slug> = la clave 'slug' que definiste
```

**`vault/config/objective.yaml` es el corazón.** Controla el encuadre que lee el agente y, sobre todo, el
clasificador de relevancia (`relevance.topics`: regex que deciden qué paper de ADS es core). Viene
pre-cargado con un ejemplo (actividad estelar vs RV planetaria) que sirve de documentación del formato
y de default funcional — reescribilo para tu tema. Lo demás (forma astro: estrellas, planetas,
indicadores, ground-truth de exoplanetas) es genérico y no se toca.

## Mantener tu bóveda actualizada (traer mejoras del framework)

Tu bóveda es **una sola implementación**: el framework (scripts, skills, `CLAUDE.md`, `vault/.obsidian/`)
vive acá; vos le agregás contenido. Al clonar, tu `origin` apunta a Almagesto, así que traés mejoras
del framework con un simple `git pull`. Tu contenido no corre riesgo: `vault/config/objective.yaml`,
`vault/config/stars.yaml`, `vault/config/topics.yaml`, `vault/STATUS.md`, `vault/wiki/index.md` y `vault/wiki/log.md` están marcados
`merge=ours` en `.gitattributes` — un merge del framework **nunca** los pisa. Registrá el driver una
sola vez por clon:

```bash
git config merge.ours.driver true   # respeta los archivos 'merge=ours' (.gitattributes)
git pull                            # trae mejoras del framework; tu contenido queda intacto
```

¿Querés versionar tu bóveda en tu **propio** repo (recomendado) y seguir recibiendo updates? Creá un
repo vacío tuyo, convertí Almagesto en `upstream` y poné el tuyo como `origin`:

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

## Arquitectura (patrón LLM Wiki)

**`vault/raw/`** (fuentes inmutables, las cura el humano) → **LLM** (compilador) → **`vault/wiki/`** (.md que el
LLM escribe y mantiene). Operaciones: **ingest / query / verify / lint**.

| Ruta | Qué hay |
|---|---|
| `vault/config/objective.yaml` | **El objetivo de la bóveda** + clasificador de relevancia (papers core). Editar para instanciar. |
| `vault/raw/pdfs/<slug>/` | PDFs (git-lfs). |
| `vault/raw/fulltext/<slug>/*.txt` | Texto completo (pdftotext) para búsqueda local y re-extracción. |
| `vault/raw/ground_truth/<slug>.json` | Hechos auditables (NASA Exoplanet Archive + SIMBAD). |
| `vault/raw/refs/` | Fuentes de diseño del patrón (gist Karpathy, guía de implementación). |
| `vault/wiki/stars/<slug>.md` | Ficha por estrella (entidad). **Frontmatter = fuente de verdad** (sp_type, P_rot, planetas, indicadores esperados, métodos). |
| `vault/wiki/papers/<bibcode>.md` | Una nota por paper (metadata ADS + abstract + extracción LLM). |
| `vault/wiki/concepts/<área>/` | Notas transversales. Áreas declaradas en `concept_areas` (objective.yaml; ej. indicators/methods/activity/hypotheses); `methods`/`hypotheses` reservadas. |
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
python query_ads.py        <slug>   # ADS → build/<slug>/ads.json (metadata + relevancia desde objective.yaml)
python fetch_arxiv.py      <slug>   # PDFs a vault/raw/pdfs/<slug>/  (rate limit arXiv: 1 req/3 s)
python fetch_ground_truth.py <slug> # NEA + SIMBAD → vault/raw/ground_truth/<slug>.json
python make_notes.py       <slug>   # genera vault/wiki/stars/ y vault/wiki/papers/ (idempotente; --force)
python extract_fulltext.py <slug>   # PDFs → vault/raw/fulltext/<slug>/*.txt
python lint.py                      # chequeo de salud → outputs/lint-<fecha>.md
```

Para TEMAS (en vez de estrellas) agregar `--topic` y definir el tema en `vault/config/topics.yaml`.
Luego: extracción LLM (leer PDFs/fulltext → poblar `methods`, indicadores, P/K, síntesis), actualizar
`index.md` y appendear a `log.md`. Ver `CLAUDE.md` para las operaciones en detalle.

## Skills del agente (`.claude/skills/`)

Las operaciones del patrón están empaquetadas como skills invocables (Claude las dispara solo por la
descripción, o el usuario con `/<nombre>`). Encapsulan la cadena mecánica + el criterio LLM:

| Skill | Cuándo | Qué hace |
|---|---|---|
| `ingest-star` | "bajá/ingestá/agregá la estrella X" | Corre la cadena (`query_ads → fetch_arxiv → fetch_ground_truth → make_notes → extract_fulltext`) y hace la extracción LLM de los papers clave + síntesis + bookkeeping. |
| `ingest-topic` | "investigá a fondo el tema X" | Como ingest-star pero por TEMA: query ADS por keywords → concept durable en `concepts/`. |
| `test-hypothesis` | "hipótesis: …", "evidencia a favor/contra de …" | Testea un supuesto **durable** contra el fulltext, lo archiva en `concepts/hypotheses/` y taggea papers (`thesis_links`/`bearing`). |
| `query-corpus` | búsqueda/pregunta general (no hipótesis) | Responde contra índice + frontmatter + fulltext; archiva en `vault/wiki/queries/` si vale re-preguntarlo. |
| `verify-citations` | cierre de toda operación con prosa `[[bibcode]]` | Chequea, afirmación por afirmación, que la fuente respalde el claim (1 subagente/par lee el fulltext). |

## Verify — chequeo claim↔fuente

Extensión propia de este template (el lint de Karpathy sólo valida salud estructural, no que la fuente
respalde la afirmación). Toda afirmación fáctica va **citada `[[bibcode]]` o marcada `inferencia`**. El
skill `verify-citations` descompone cada nota en pares (afirmación, bibcode) y lanza un subagente por
par que lee SÓLO ese `.txt` y devuelve `soportada|parcial|no-soportada` + cita textual. Ver `CLAUDE.md`.

## Token NASA ADS

Gratis en <https://ui.adsabs.harvard.edu/user/settings/token>. En `vault/config/ads_dev_key` (**gitignored**)
o en la variable `ADS_DEV_KEY`. Límite ~5000 consultas/día.

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
