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
- **Node/npm — sólo para el modo off-ADS por web.** `fetch_web.py` toma el snapshot con
  `npx defuddle` y **aborta** si no encuentra `npx`. No hace falta para el flujo ADS (estrellas y
  temas por query); sí para ingestar una fuente declarada por URL.

**Token ADS** gratis en <https://ui.adsabs.harvard.edu/user/settings/token> (~5000 consultas/día);
va en `vault/config/ads_dev_key` (gitignored) o en la variable `ADS_DEV_KEY`.

Nada de esto hace falta para **consultar** una bóveda ya poblada (el fulltext se commitea) — sólo
para ingestar. En Windows, los comandos de shell corren en Git Bash o WSL.

## Layout del repo

| Ruta | Qué hay |
|---|---|
| `vault/config/objective.yaml` | **El objetivo de la bóveda** + clasificador de relevancia (papers core). Editar para instanciar. |
| `vault/raw/pdfs/<slug>/` | PDFs (git-lfs). |
| `vault/raw/fulltext/<slug>/*.txt` | Texto completo (pdftotext; si la capa de texto es ilegible, OCR marcado `source: ocr`, citable con salvedad) para búsqueda local y re-extracción. Ojo: el `.txt` puede venir del **preprint de arXiv** y no de la versión publicada; la nota del paper lo registra en `pdf_source` (ver abajo). |
| `vault/raw/ground_truth/<slug>.json` | Hechos auditables (NASA Exoplanet Archive + SIMBAD). |
| `vault/raw/refs/` | Fuentes de diseño del patrón (gist Karpathy, guía de implementación). |
| `vault/wiki/stars/<slug>.md` | Ficha por estrella (entidad). **Frontmatter = fuente de verdad** (`spectral_type`, `P_rot_days`, planetas, indicadores esperados, métodos). Lo que sale de NEA/SIMBAD es **espejo puro**: si el ground-truth no tiene el valor, el campo queda null y el dato de literatura va al cuerpo, citado. |
| `vault/wiki/papers/<bibcode>.md` | Una nota por paper (metadata ADS + abstract + extracción LLM). |
| `vault/wiki/concepts/<área>/` | Notas transversales. Áreas **abiertas** (cualquiera); `concept_areas` (objective.yaml) es referencia para el typo-check, no restricción — `methods`/`hypotheses` reservadas. |
| `vault/wiki/queries/` | Preguntas contestadas contra el corpus. |
| `vault/wiki/matrices/method_star.md` | Matriz método × estrella = huecos + backlog. |
| `vault/wiki/index.md` | Catálogo de la wiki (se actualiza en cada operación). |
| `vault/wiki/log.md` | Registro append-only de operaciones. |
| `vault/config/stars.yaml` · `vault/config/themes.yaml` | Estrellas / temas de la bóveda (nombres canónicos + alias). |
| `vault/config/ads_dev_key` | Token NASA ADS — **GITIGNORED** (nunca se commitea). |
| `vault/config/registro/_red.yaml` | **Cuándo se miró afuera por última vez** (retracciones, correcciones, versiones, ground-truth, snapshot web). Lo escribe `python scripts/sweep_external.py`, la pasada de red unificada. |
| `vault/config/registro/<slug>.yaml` | **Registro de ingesta por sujeto (se commitea).** `busquedas` (lista, **acumulativa**: una entrada por corrida): qué se le preguntó a ADS, cuándo, con qué límite y con qué corte. `cadena`: qué pasos corrieron, con fecha y versión. `decisiones`: qué descartaste y por qué, en los dos carriles (candidatos del triage y fuentes declaradas de un tema off-ADS). |
| `build/` · `outputs/` | **GITIGNORED** — intermedios de ingesta y reportes de lint. |

## Pipeline de ingesta (scripts/)

> Para el **embudo de selección** (de cuántos papers se parte y cuántos llegan a la ficha), las
> dos ingestas lado a lado y **campo por campo quién llena la ficha**, ver `docs/ingesta.md`.

División de tareas: **scripts** bajan (determinista, rate-limited); **LLM** procesa (criterio).

**La cadena completa la corren los orquestadores** — `python scripts/ingest_star.py <slug>` (estrellas)
y `python scripts/ingest_theme.py <slug>` (temas; despacha por el campo `source`, incluido el modo
off-ADS) —
cuyos headers son la **definición canónica del orden** (docs y skills apuntan ahí, no copian la
lista). Las piezas, para correr sueltas cuando hace falta un flag fino (`--rows`, `--all`,
`--force` de un paso):

```bash
cd scripts     # ← el único bloque con CWD propio (cómodo para el listado); en los skills y en el
               #   resto de los docs los comandos van desde la RAÍZ del repo: python scripts/<x>.py
python query_ads.py        <slug>   # ADS → build/<slug>/ads.json + vault/config/registro/<slug>.yaml
                                    #   (`busquedas`: query efectiva, fecha, límites y conteos — versionado)
                                    #   (metadata + relevancia + citation chaining;
                                    #   --sweep = barrido full-text 2b: core que faltan → candidatos a extra_core)
python triage.py           <slug>   # juzgar los candidatos del chaining: --report deja la tabla en
                                    #   outputs/; --drop <bib> --reason "<motivo>" persiste el descarte
                                    #   en vault/config/registro/<slug>.yaml. NO se bajan hasta decidirlos
                                    #   --drop-source <clave> --reason "…" [--pointer <url|doi>]:
                                    #   el otro carril — fuente DECLARADA de un tema off-ADS que
                                    #   evaluaste y dejaste afuera (no necesita ads.json)
python fetch_arxiv.py      <slug>   # PDFs a vault/raw/pdfs/<slug>/  (rate limit arXiv: 1 req/3 s)
python fetch_pdf.py        <slug>   # PDFs aún sin bajar (sin arXiv + arXiv fallidos) vía resolver ADS
python fetch_ground_truth.py <slug> # NEA + SIMBAD → vault/raw/ground_truth/<slug>.json
python make_notes.py       <slug>   # genera vault/wiki/stars/ y vault/wiki/papers/ (idempotente; --force)
python extract_fulltext.py <slug>   # PDFs → vault/raw/fulltext/<slug>/*.txt
python check_retractions.py         # Crossref → marca `retracted` (bloqueante) y `corrections`
                                    #   (erratum/corrigendum/EoC: backlog) (red); la cadena usa --slug <slug>,
                                    #   sin --slug barre TODA la bóveda (pasada periódica, skill maintain)
python triage.py <slug> --extraccion todos|subconjunto [--reason "<criterio>"]
                                    #   D-13: declarar QUÉ se leyó de los core (con `subconjunto`
                                    #   el criterio es obligatorio: no curar en silencio)
python triage.py <slug> --sintesis [--n-papers N] [--reason "<nota>"]
                                    #   INV-82: declarar CUÁNDO se sintetizó — la tercera fecha de
                                    #   la cabecera. No se puede derivar (git fecha el ARCHIVO)
python lint.py                      # chequeo de salud → outputs/lint-<fecha>.md (exit 1 si hay bloqueantes)
                                    #   --cierre: los pares de verificación vencidos BLOQUEAN
```

**Pasadas globales** (no dependen del sujeto en curso; hermanas entre sí):

```bash
python scripts/sweep_external.py    # la PASADA DE RED: los cinco eventos que caducan afuera
                                    #   (retracciones, correcciones, versiones, snapshot web,
                                    #   ground-truth). Reporta el diff y PREGUNTA antes de aplicar;
                                    #   la caducidad queda en vault/config/registro/_red.yaml
python scripts/entity.py plan   <slug>              # las siete capas de una entidad — no escribe
python scripts/entity.py delete <slug> --yes        # borrar sin dejar nada colgado (INV-19)
python scripts/entity.py rename <viejo> <nuevo> --yes
python scripts/citation_index.py    # índice invertido obra→citadores (caro: ADS + OpenAlex)
python scripts/search_arxiv.py "independent component analysis" --categories stat.ML --rows 25
                                    # preview de un backend no-ADS: qué trae y qué clasifica como
                                    # core con TU lente. No baja ni escribe nada. ⚠ `search_arxiv`
                                    # NO está cableado a la cadena de ingest (issue #95): esto es
                                    # exploración para decidir si vale cablearlo.
```

**Migradores y backfills** (una sola corrida; el framework no lleva capas de retrocompatibilidad,
así que cada cambio de schema entrega migrador **y** detector bloqueante — INV-64):

```bash
python scripts/make_notes.py --migrate-disputes   # #71: planets[].disputes[] → disputes a nivel nota
python scripts/make_notes.py --migrate-bearing    # D-21: `bearing` fuera de la nota de paper
python scripts/make_notes.py --migrate-facets     # R-5: `topics:` → `facets:`
python scripts/make_notes.py --migrate-registros  # D-28: `busqueda:` → `busquedas: []` (pliega, no borra)
python scripts/triage.py <slug> --migrate         # #51: el juicio del build/<slug>/triage.json viejo
python scripts/make_notes.py --restamp-headers    # cabecera a las notas que nacieron sin ella
python scripts/make_notes.py --restamp-keywords   # D-17: `keywords:` desde build/*/ads.json
python scripts/make_notes.py --restamp-pdf-links  # #47: el link [📄 PDF] ↔ frontmatter `pdf`
python scripts/make_notes.py --sync-mirror        # #70: campos espejo de NEA que quedaron en null
python scripts/make_notes.py --rename-paper VIEJO NUEVO   # D-19: ciclo preprint → publicado
```

Entre la query y el primer paso que gasta red y disco hay un **checkpoint humano** (la *guardia de
expansión*): si el core recién clasificado se multiplicó respecto de las notas ya ingestadas del
sujeto (default: ×1.5 y 50 papers nuevos o más), la cadena **frena** y muestra el conteo, cuántos
vinieron por el grafo de citas y el puntero a `relevance.require`/`min_facets` por si el corte quedó
flojo. `--yes` sigue a sabiendas. No es un error: es el punto donde conviene mirar antes de bajar
cientos de PDFs. **Ojo: sólo aplica a re-ingestas.** En el **primer** ingest de un sujeto no hay
notas previas con qué comparar, así que la cadena sigue derecho por más grande que sea el corte —
ahí el control es el `--probe` del skill `setup` (previsualizar la lente antes de bajar nada).

Para TEMAS (en vez de estrellas): definir el tema en `vault/config/themes.yaml` y correr
`python scripts/ingest_theme.py <slug>`: el orquestador despacha según el campo `source` de la entrada:
`ads` (default) corre la cadena de arriba con `--theme` y **sin** `fetch_ground_truth` (no hay
NEA/SIMBAD para un tema); `web` / `local-pdfs` (modo **off-ADS**, opt-in) procesa la bibliografía
declarada en la lista `sources:` de la entrada — snapshots web citables vía `fetch_web.py` (defuddle)
y PDFs locales copiados a la bóveda con clave `AAAA+Autor` (ver skill `ingest-theme`). Luego:
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
`vault/config/objective.yaml`, `vault/config/stars.yaml`, `vault/config/themes.yaml`, `vault/STATUS.md`,
`vault/wiki/index.md`, `vault/wiki/log.md` y `vault/wiki/matrices/method_star.md` están marcados
`merge=ours` en `.gitattributes`, así que un merge del framework **nunca** los pisa (registrá el driver una vez por clon: `git config merge.ours.driver true`).

**Si instanciaste con "Use this template" (recomendado):** tu `origin` es *tu* repo y Almagesto es
`upstream` (lo agregaste al instanciar). Traés mejoras del framework mergeando upstream:

```bash
git fetch upstream && git merge upstream/main   # trae mejoras del framework; tu contenido (merge=ours) queda intacto
```

⚠ **La primera vez ese comando falla** con `fatal: refusing to merge unrelated histories`, y es
esperable: "Use this template" te crea el repo con **historia limpia**, o sea sin ancestro común con
Almagesto. El primer merge se hace con el flag, y una sola vez:

```bash
git merge upstream/main --allow-unrelated-histories
```

Ahí van a aparecer **conflictos add/add en archivos de framework** que tu instancia nunca tocó (git
no tiene con qué compararlos). Se resuelven a favor de upstream — es la regla de oro: en una
instancia no se edita framework —, p. ej. `git checkout --theirs <path>` por archivo, o
`-X theirs` en el merge. Tus archivos de instancia están cubiertos aparte por `merge=ours`. Una vez
commiteado ese merge ya hay ancestro común: **del segundo en adelante alcanza el comando de arriba**.

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
- **El token ADS (`vault/config/ads_dev_key`):** gitignored, nunca se commitea. Es lo primero que
  falta al clonar en otra máquina: ponelo de nuevo ahí (o exportá `ADS_DEV_KEY`).

Lo que **sí** viaja desde 1.9.0 y antes no: el **registro de ingesta** (`vault/config/registro/<slug>.yaml`).
Hasta 1.8.x había dos cosas atrapadas en `build/` que no eran regenerables:

- **el juicio de curación** — qué descartaste y **por qué**: el candidato del citation chaining, y
  también la fuente declarada de un tema off-ADS que evaluaste y dejaste afuera
  (`triage.py <slug> --drop-source <clave> --reason "…"`). Un
  `ads.json` sí se regenera (se le vuelve a pedir a ADS); tu decisión sobre título+abstract, no. En
  otra máquina el triage te re-proponía todo lo descartado, sin el motivo, y había que rehacer el
  trabajo. (Asimetría que lo delataba: los candidatos **aceptados** ya persistían en config
  versionada, vía `extra_core`; los rechazados no.)
- **el registro de la búsqueda** — la query efectiva, la fecha, los límites y los conteos. Sin eso no
  hay forma de saber **sobre qué universo de papers afirma una ficha**, que es lo que cualquier
  revisión sistemática está obligada a dejar asentado.

Consecuencia práctica: el lint ya no da un **falso limpio** en una máquina sin `build/`. Antes los
chequeos de *triage pendiente* y *corpus truncado* recorrían `build/` y, si no estaba, reportaban 0
sin haber mirado nada; ahora caen al registro y reportan el snapshot **con su fecha**, aclarando que
no es el conteo vigente.

**El `.txt` no siempre es la versión publicada.** Cuando el PDF vino de arXiv, el texto completo es
el del **eprint**, que en un `v1` pre-referato puede traer valores y secciones distintos de los del
paper publicado que identifica el bibcode. La nota de cada paper lo registra en `pdf_source`
(`eprint | ads | publisher | web`, más `eprint_version` cuando se conoce), y `null` significa
**desconocido**, no "publicado". Importa al citar: ante una diferencia numérica entre lo que dice la
ficha y lo que dice el `.txt`, con `pdf_source: eprint` lo primero que hay que descartar es que sean
dos versiones del mismo paper. Un corpus bajado antes de la versión 1.10.0 se completa sin re-bajar
nada: `python scripts/extract_fulltext.py <slug>` lee la marca que arXiv estampa en el texto que ya
está en disco.

Sin rutas absolutas hardcodeadas: los scripts resuelven el root del repo desde `__file__`
(`scripts/lib_config.py`), no asumen `cwd` ni `/home/...`.

## Abrir la bóveda en Obsidian

El vault de Obsidian es la carpeta **`vault/`** (no la raíz del repo): así el grafo y el explorador
muestran sólo conocimiento, sin el andamiaje (`scripts/`, `CLAUDE.md`, …). Las consultas Dataview usan
rutas relativas a esa raíz, tipo `FROM "wiki/papers"`. Si abrís la raíz por error, el síntoma es un
grafo lleno de nodos ajenos a la bóveda (reportes de lint de `outputs/`, README, tests) y queda un
`.obsidian/` en la raíz — está gitignored y el lint lo marca WARN: borralo y reabrí `vault/`.

1. Obsidian → **"Open folder as vault"** → elegir la carpeta **`vault/`** del repo.
2. *(Opcional)* Instalar/activar el plugin **Dataview** (Settings → Community plugins → Browse →
   "Dataview" → Install + Enable). **Los roll-ups de las fichas ya no lo necesitan**: desde 1.35.0
   `## Papers`, `## Planetas` y `## Métodos aplicados` son tablas **estampadas** (D-10/D-11), para
   que un agente que abre el `.md` vea los resultados y no el código de una query. El plugin sólo
   hace falta si vos escribís queries propias en tus notas.

La config compartible del vault se commitea (`vault/.obsidian/app.json`, `appearance.json`, etc.); lo volátil
por máquina (`workspace.json`, `cache`) y los plugins de comunidad (`vault/.obsidian/plugins/`) están
gitignored — instalá Dataview desde Obsidian (paso 2 de arriba).
