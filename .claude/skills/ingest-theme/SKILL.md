---
name: ingest-theme
description: Usar cuando el usuario pide investigar/ingestar un TEMA en profundidad a la bóveda, como si fuera una estrella pero por tópico ("traé todo sobre actividad y RV", "investigá a fondo el bisector vs actividad", "ingestá el tema de los GP en RV", "armá un concept con la bibliografía de indicadores de actividad"). Dispara una búsqueda ADS por keywords y hace la extracción LLM hacia un concept durable. Soporta además, sólo a pedido explícito, un tema off-ADS — típicamente un método de otra disciplina (estadística, ML) al servicio del foco astro — desde PDFs locales + web (ver Modo off-ADS).
version: 1.16.0
---

# Ingest: agregar un TEMA a la wiki

Operación **ingest** del patrón LLM Wiki (ver `CLAUDE.md`), hermana de `ingest-star` pero por **tema**
en vez de por estrella. División idéntica: los scripts bajan, el LLM procesa. Trabajar desde la raíz
del repo.

**Diferencias con `ingest-star`** (mismo patrón, distinto sujeto: un tema en vez de una estrella):
- La búsqueda ADS es **por keywords** (query Solr cruda), no por nombre vía SIMBAD.
- El producto durable es un **concept** (`concepts/<area>/<concept>.md`), no una ficha de estrella.
- **No hay ground-truth** (no existe NEA/SIMBAD para un tema) → se **saltea `fetch_ground_truth.py`**.
- **No** se toca la matriz método×estrella.
- Las notas de paper llevan `stars: []` y `thesis_links` pre-sembrado al concept.

> **Default = vía ADS** (los **Pasos** de abajo — la plomería con descubrimiento automático). Si el
> usuario pide **explícitamente** un tema cuya bibliografía vive **fuera de ADS** (típicamente un
> método de otra disciplina), usar el **Modo off-ADS** (al final de los Pasos). `ingest-star` no
> tiene este modo: es astro-only.

## Pasos

**Copiá este checklist al chat al arrancar y andá tildándolo** — el retro-tag (3b), el contraste
(3c) y la verificación (6b) se saltean sin dejar rastro. El lint tiene red para **6b** (*sin
verificar* / *verificación stale*, #56) y para lo que la síntesis dejó afuera (*extraído pero no
sintetizado*, #75 — que es también la red del contraste de 3c); para **3b** no hay red:

```
Progreso del ingest del tema <tema>:
- [ ] 0b (tema off-ADS) barrido de los TRES backends antes de declarar fuentes a mano (`discover.py`)
- [ ] 1  consulta co-diseñada con el usuario (o `sources:` si es off-ADS)
- [ ] 1b (tema de MÉTODO) `facet:` propia acordada — y `fundacional_min_citas` si va
- [ ] 2  cadena mecánica (ingest_theme.py) — sin abortos
- [ ] 3  extracción LLM de los papers clave del tema
- [ ] 3b retro-tag por grep de aliases sobre el corpus pre-existente
- [ ] 3c contraste cross-paper (inventario por eje)
- [ ] 4  síntesis del concept durable (+ régimen de validez / disputes)
- [ ] 5  auto-revisión de autosuficiencia
- [ ] 6  bookkeeping (index, log, STATUS)
- [ ] 6b verify-citations sobre el concept + notas nuevas
- [ ] 7  `lint.py --cierre` en 0 → commit → preguntar push
```

1. **Co-diseñar la consulta con el usuario (NO traducir en silencio).** El usuario da el tema en
   lenguaje natural ("actividad y RV", "bisector vs actividad"); el valor del skill está en **pulir
   esa intención antes de gastar la búsqueda**. Secuencia:
   - **a. Interpretar y proponer.** Convertir la intención en una **query Solr cruda candidata** y
     **mostrársela explicada** (qué término exige como AND, qué grupo va en OR). Señalar el sesgo:
     p. ej. exigir `abs:"bisector"` como AND deja afuera papers de S-index/FWHM puros.
   - **b. Proponer la FAMILIA de términos, en prosa (D-29).** Mismo patrón que los alias de una
     estrella (`ingest-star` paso 1) y las facetas del objetivo (`setup` paso 3): el usuario dice
     *"separación ciega de fuentes"* y vos proponés la familia completa —fastICA, JADE, Infomax,
     cocktail party, non-gaussianity, mixing matrix…— **en castellano y sin regex** (vos traducís a
     `abs:"..."`). Ofrecer además variantes de alcance (amplia ↔ acotada). Usar `AskUserQuestion` si
     la elección cambia qué se trae. **No buscar hasta que apruebe.**
   - **c. Validar con un conteo barato** antes de bajar nada (y antes de persistir el slug):
     `python scripts/query_ads.py --probe '<query candidata>' --rows 50` y mirar el corte CORE/no-core +
     los títulos top (ordenados por citas). Si trae cientos con ruido o muy pocos, reajustar la
     query y reconfirmar. **No** bajar PDFs hasta que el usuario apruebe la query final. (`--probe`
     recibe la query cruda, así que corre sin que el tema exista todavía en `themes.yaml` —
     `--theme <slug>` recién funciona después del paso d.)
   - **c2. Sugerir ramas no pedidas.** Con lo que vuelve del `--probe`, si aparece consistentemente
     una familia vecina que el usuario no nombró, **preguntarla** (*"apareció mucho NMF — ¿entra en
     este tema o es otro?"*). Es información que sólo existe después de mirar papers reales, y
     callarla deja el tema recortado por un término que nadie decidió.
   - **d. Persistir.** Recién entonces escribir/actualizar la entrada en `vault/config/themes.yaml`:
     `title`, `area` (abierta: cualquiera; idealmente una de `concept_areas` de `objective.yaml` —
     ej. `indicators|methods|activity|hypotheses` — para que el typo-check la reconozca; si es un área
     nueva real, agregala a esa lista), `concept` (nota destino, existente o
     a stubbear), `query` (la Solr cruda aprobada) y `aliases` opcional. Si el tema ya existía en el
     YAML, ofrecer reusar la query guardada o re-pulirla.

1b. **Tema de MÉTODO: acordar la faceta propia (D-26).** Un tema de método —estadística, ML,
   signal processing— **no se clasifica con la lente global**, y no por falta de ajuste: con
   `require: [rv]` la lente mata al paper **fundacional** (Hyvärinen no menciona RV ni una vez), y
   sin filtro *"independent component analysis"* devuelve miles de papers de fMRI, EEG y finanzas.

   La entrada del tema en `themes.yaml` lleva entonces su propia regex, y la regla pasa a ser
   `core = facet propia Y (puerta 2 OR puerta 3)`:

   | Puerta | Qué mira | Para qué sirve |
   |---|---|---|
   | 2 · fundacional | `citation_count >= fundacional_min_citas` | el paper que funda el método, aunque no toque astro |
   | 3 · lente astro | `relevance.facets` de `objective.yaml` | la aplicación del método en astro, aunque tenga 3 citas |

   **Proponé la `facet:` en prosa y mostrala antes de buscar**, igual que la query: es la otra
   mitad de lo que decide el corte. Y **`fundacional_min_citas` se acuerda con el usuario o no se
   pone**: el número depende del campo (30k citas es normal en ML y muchísimo en astro) y el
   framework **no tiene default** — sin declararlo la puerta 2 no abre y el motivo queda en
   `why_excluded`, visible en el apéndice "Excluidos por el filtro". ⚠ Está anotado en
   `vault/STATUS.md` como **decisión abierta** si la puerta 2 debe existir: usala sólo si el
   usuario la pide.

   Tras la corrida, la cadena imprime el delta (`regla del tema (D-26): +N core / -M`). **Miralo**:
   si sacó papers que esperabas, la `facet:` está muy angosta.

1c. **La puerta 1 (`lo cita tu corpus`) llega como CANDIDATOS, no como core.** Si existe
   `build/citation_index.json`, los papers que la regla del tema dejó afuera pero que **tu corpus
   cita** aparecen en `candidates` con `via: citado-por-corpus` y la lista de quiénes los citan.
   Es la señal que ninguna regex puede expresar —Hyvärinen tiene ~30k citas casi todas de fMRI, y
   lo que lo vuelve *tuyo* es que tu gente lo cita— y por eso **la juzgás vos** con
   `python scripts/triage.py <slug>`, como cualquier candidato. El índice se construye aparte
   (`python -c "import sys; sys.path.insert(0,'scripts'); import citation_index; citation_index.build()"`),
   es caro (red sobre todo el corpus) y vive en `build/`; sin él, la puerta simplemente no aporta.

2. **Cadena mecánica** — un solo comando (desde la raíz del repo):
   ```bash
   python scripts/ingest_theme.py <slug>
   ```
   El orquestador despacha según el campo `source` de la entrada del tema (`ads` si falta). En modo
   ADS corre la cadena de estrellas **sin `fetch_ground_truth`** (no hay NEA para un tema) y con
   `--theme` donde aplica; **el orden canónico vive en el header de `scripts/ingest_theme.py`** —
   puntero, no copia: no lo repliques acá ni en otros docs. Todo idempotente (si algo falla se
   re-corre, o se corre el script puntual con sus flags finos).
   `query_ads --theme` escribe el mismo `build/<slug>/ads.json` (con `kind: theme`), así que
   `fetch_arxiv`, `fetch_pdf` y `extract_fulltext` corren sin cambios. Hace **citation chaining anclado a la query
   del tema** (references/citations de los core filtrados por la propia query → recall extra sin traer
   los mega-citados genéricos del área). `fetch_arxiv` respeta el rate limit de arXiv
   (1 req/3 s) → correr en background si son muchos PDFs. Los papers sin arXiv (A&A viejos) —y
   los con arXiv cuya bajada falló— los intenta `fetch_pdf` (escaneo ADS con token → publisher,
   fallback `curl`); lo que ni así sale queda en `build/<slug>/missing_pdf.json` (residuo
   completo del ingest), con el `bibstem` y un `hint` por entrada → seguir la **cascada manual de
   rescate**, que vive en `## Notas` del skill `ingest-star` (canónica allá, sin copia: Messenger /
   página del instrumento / mirrors académicos / tablas del CDN / derivar al usuario — y **no**
   gastar intentos en `aanda.org`, que está tras DataDome). "Bajar por DOI" solo no alcanza. Curación persistente con
   `extra_core:` (lista de mapas `{bibcode, via, fecha, motivo}` — D-58; el `triage` imprime el snippet listo para pegar) en la entrada del tema en `themes.yaml` (igual que en estrellas).
   **Guardia de expansión (checkpoint humano).** Entre `query_ads` y el primer paso que gasta red
   y disco, el orquestador compara el core del `ads.json` fresco contra las notas ya ingestadas del
   sujeto: si se multiplicó (default ×1.5 y 50 o más nuevos) **frena** con el conteo, cuántos vinieron
   por el grafo de citas y el puntero a `relevance.require`/`min_facets`. Antes de refrescar un
   sujeto viejo, mirá ese número: si el pool explotó, revisá la **regla de combinación** en
   `objective.yaml` (skill `setup`) antes de bajar nada — podar las regex no alcanza si la
   combinación sigue siendo OR. `--yes` continúa a sabiendas.

3. **Extracción LLM (criterio).** Leer los papers **clave del tema** (fundacionales / árbitros /
   metodológicos) desde `vault/raw/fulltext/<slug>/` y poblar cada `vault/wiki/papers/<bibcode>.md`: `methods`,
   `role` (#73: `fundacional` introduce el método/mecanismo · `aplicacion` lo instancia en un caso · `arbitro` reanaliza y resuelve una tensión previa — sale de leer el paper, la regex del clasificador no puede inferirlo, y sin él contrastarlo contra otro no está definido) —especialmente agudo en temas de método, donde fundamentos y
   aplicaciones astro conviven en el mismo concepto por diseño—, `thesis_links` (ya pre-sembrado al
   concept; agregar otros si toca) y la sección
   "Extracción" enfocada **en el eje del tema** — el stub la trae ya ramificada por tipo de sujeto
   (#76): *aporte al tema* (definición, mecanismo/ecuación, método, signo) y *régimen de validez*,
   no planetas ni actividad de una estrella concreta.
   ⚠ **`pdf_source` antes de copiar un número** (#57): con `eprint` el `.txt` es el **preprint**
   (un `v1` pre-referato puede traer otros valores que el publicado que identifica el bibcode), y con
   `null` no se sabe —que **no** es "publicado"—. Un valor que choca con el ground-truth o con el
   abstract de ADS es candidato a **diferencia de versión**: abrí el PDF publicado o dejá la
   salvedad en la nota. `verify-citations` lo detecta después; **acá es donde el número entra a la
   bóveda**.

3b. **Retro-tag del corpus pre-existente (grep por aliases).** Los papers que la query ADS devolvió
   pero **ya estaban** en el corpus quedan conectados solos (`make_notes` mergea add-only el seed
   `thesis_links` en la nota existente, sin pisar su extracción). Lo que la query **no** devolvió se
   caza por grep: buscar los `aliases` del tema sobre el fulltext de **todo** el corpus (los otros
   slugs), p. ej. `grep -rilE --include="*.txt" "gaussian.process|gpr" vault/raw/fulltext/`, y para cada
   hit sin taguear leer el contexto y decidir si el paper **usa/aporta** al tema (no mención al
   pasar) → agregar add-only `thesis_links` (y `methods` si aplica) a su nota. El roll-up del concept es una tabla
   **estampada**: junta también por `methods:` sin re-taguear, pero **no acumula sola** — al
   terminar el retro-tag hay que re-correr `python scripts/make_notes.py <slug> --theme`.
   **Alias sueltos y cortos, nunca frases** (#44, convención canónica en `verify-citations`): el
   `.txt` entrelaza dos columnas en la misma línea física (73% del corpus) → un alias multi-palabra
   (`"gaussian process regression"`) puede no matchear aunque el paper lo use. Probar la raíz corta
   y el guión de corte antes de dar por no-taguable un paper; un 0 acá **no** es "el tema no está",
   es un retro-tag que no se hizo.

3c. **Contraste cross-paper (#72) — antes de escribir la síntesis.** Entre "leí los papers" y
   "escribo la síntesis" hay una operación, y es la de más apalancamiento de la cadena: armar el
   **`## Inventario por eje`** del concept. Una fila por paper para cada **eje** —parámetro, efecto o
   hecho— donde los papers **no coinciden** (`Eje | Paper | Dice | Método / baseline`). Los ejes con
   acuerdo unánime **no entran**: misma regla de poda que la prosa.
   ⛔ **Sin columna "valor adoptado" ni "por qué".** Adoptar un valor es **decidir por el
   consumidor** y rompe el flujo unidireccional de la regla #0: la bóveda reporta el **estado de la
   literatura**. La lectura propia va aparte y marcada `inferencia`.
   ⚠ **Mirá el `role` (#73) antes de leer dos filas como desacuerdo:** fundacional↔aplicación **no
   es contraste, es instanciación** — y en un tema de método eso es el caso NORMAL, porque
   fundamentos y aplicaciones astro conviven en el mismo concept por diseño. El `arbitro` no es una
   fila más: es el que resuelve.
   Sin esto, tres papers con tres valores del mismo efecto terminan en una frase con un solo
   `[[bibcode]]` y se evapora que los otros dos existen — que es exactamente lo que el concept
   promete responder sin abrir un paper. La red de que el contraste ocurrió es #75 (*extraído pero
   no sintetizado*).
4. **Síntesis del concept durable** (`concepts/<area>/<concept>.md`). Destilar lo aprendido a la
   página viva: mecanismos, signos, desfasajes, regímenes, huecos. El roll-up estampado (papers con `thesis_links:
   <concept>` **o** `methods: <concept>`) se regenera con `python scripts/make_notes.py <slug> --theme`
   — no acumula solo. **Citar los papers clave por `[[bibcode]]`** en la prosa
   (además de trazabilidad, da links entrantes → no quedan huérfanos).
   Dos secciones del template que **son de un concepto** y hay que llenar acá, no dejarlas vacías:
   - **`## Régimen de validez` (#74).** El modo de falla dominante de un concepto **no** es "dos
     números no coinciden" sino **generalizar de más**: el paper afirma X bajo condiciones C (SNR,
     muestreo, tamaño de muestra, definición del observable) y el concepto termina afirmando X
     pelado. `verify-citations` **no** lo agarra —la afirmación pelada sí está en el paper, así que
     vuelve `soportada`—, por eso la condición se escribe acá: una fila por afirmación
     condicionada (`Afirmación | Vale bajo | Fuente | Rol`). Es el destino de los desacuerdos que
     resultan **`aparente`** (distinto régimen, distinta definición, distinta época): en una
     estrella eso se descarta como no-disputa, en un concepto **es el hallazgo**. De la tabla sale
     un hueco accionable propio: **"régimen no cubierto"** → a `## Huecos`.
   - **`disputes` (#71), sólo para el desacuerdo REAL bajo las mismas condiciones.** Acá la disputa
     es **simétrica por definición** (no hay ground-truth que arbitre, así que ninguna posición es
     "la verdad"): `field` nombra el eje y cada posición dice quién la sostiene (`{ref, value}`).
     Si el desacuerdo se explica por el régimen, **no** es una disputa: es una fila de la tabla de
     arriba. Una posición sola no es desacuerdo — es una afirmación, y va a la prosa citada (el
     lint bloquea las disputas con menos de dos posiciones).

5. **Auto-revisión de autosuficiencia (semántica).** Releer el concept como un agente externo que
   **sólo tiene ese archivo**: ¿se entiende el tema sin abrir ningún paper? Si para responder algo hay
   que abrir un paper, falta en el concept → agregarlo. (El único proxy estructural de `lint.py` acá
   es *extraído pero no sintetizado* (#75): cada paper con `methods` poblado tiene que estar citado
   en alguna ficha o concepto. La suficiencia la juzgás vos, igual que en la ficha de estrella.)
   ⚠ Ese backlog es el que cierra este paso: un paper que pagó la extracción y no aparece citado en
   ninguna entidad es extracción perdida. O lo sintetizás donde corresponda, o declarás por qué no
   va: `no_sintetizado: <motivo>` en su nota (la marca sin motivo se sigue reportando).

6. **Bookkeeping.** Actualizar `vault/wiki/index.md` (agregar el concept si es nuevo), appendear a
   `vault/wiki/log.md`, y `vault/STATUS.md` si cambió el estado. **No** tocar la matriz método×estrella.
   (El `lint` va **después** del verify del paso 6b: `CLAUDE.md` lo pide "antes de lint/commit",
   porque resolver una cita no-soportada suele cambiar la prosa.)

6b. **Verificar citas.** Correr el skill `verify-citations` sobre el **concept** (y las notas de paper
   nuevas). El concept es dual-audiencia e implementation-ready: cada afirmación con `[[bibcode]]`
   —definiciones, ecuaciones, rangos, signos— debe estar respaldada por el fulltext (cita textual +
   nº de línea del `.txt`; sin respaldo ⇒ no-soportada). Resolver cada no-soportada/parcial (bajar a lo
   que dice la fuente, reasignar la cita, o marcar `inferencia`) y dejar el bloque `## Verificación de citas`.

7. **Cierre (commit + push).** Tras la verificación (`python scripts/lint.py --cierre` en 0), `git add` de los archivos
   **específicos** que tocó la operación (no `-A`) y commitear con mensaje
   descriptivo. Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Modo off-ADS / biblio fuera de ADS (opt-in — **sólo a pedido explícito**)

El foco de Almagesto es **astro**, y su única plomería de **descubrimiento automático** (query →
clasificar → bajar) es de astronomía —ADS, arXiv, NEA/SIMBAD—; por eso un tema, por **default**, se
baja por ADS (los **Pasos** de arriba). Este modo existe para los **métodos de otras disciplinas**
que el trabajo astro usa —análisis de datos, estadística, machine learning, procesos gaussianos,
signal processing— y cuya bibliografía canónica vive **fuera de ADS** (el eje tema/concepto y la
capa de calidad son agnósticos de disciplina, así que la cadena los soporta igual), con la
diferencia operativa de que las fuentes se **declaran**, no se descubren por query. Se permite
**sólo si el usuario lo pide explícitamente** (porque exige esa curación manual de fuentes).
**`ingest-star` no cambia: sigue siendo astro-only.**

### 0b. ANTES de declarar nada a mano: barré los tres backends (#104)

⛔ **No le digas al usuario "no tengo los fundacionales" habiendo mirado un solo buscador.** Fue un
defecto medido: ADS devuelve **0 de 8** del canon de ICA/BSS y `author:"Hyvarinen, A"` trae dos
papers sobre gotas de ácido sulfúrico (es otro Hyvärinen) — pero OpenAlex los tiene **8 de 8**, con
DOI y conteo de citas. La lista declarada a mano es el **último** recurso, no el primero:

```bash
python scripts/discover.py --topics "<tema en inglés>"      # subtema de OpenAlex (id T…) → `topic:`
python scripts/discover.py --theme <slug>                   # ADS + arXiv + OpenAlex + anclaje
python scripts/discover.py --resolve 10.1016/…              # ¿hay copia libre de ese DOI?
```

**Leé la cobertura que imprime**, no sólo la lista: distingue *corrió con N*, *FALLÓ* (0 por caída,
que **no** es "no tiene nada del tema") y *NO CORRIÓ* con el motivo. Y declará `topic:` en la
entrada del tema: sin él, la mitad OpenAlex se infiere del `title` y con títulos en castellano no
matchea la taxonomía inglesa.

⚠ **El orden importa y está medido:** `search` + orden por citas sobre OpenAlex devuelve 143.450
works cuyo top 30 es AlphaFold y guías de cardiología (**2 de 30** en tema). Filtrando por
`topics.id` **primero**, el canon entra al top 25. Rankear sin filtro estructural amplifica.

**Y lo que más rinde: anclar en la mitad astro del propio tema.** Una vez que la cadena bajó los
papers ADS del tema, sus **listas de referencias** traen el canon rankeado por cuántos de ellos lo
citan (`discover.anchored_records`). Medido sobre 19 papers astro de ICA: devolvió los **ocho**
canónicos sin declarar nada, y ordena mejor que las citas globales. Es además lo único que alcanza
lo que ninguna keyword del tema alcanza — en ICA, la familia de **PCA con ruido** (el blanqueo), que
un barrido por "independent component analysis" nunca ve.

⛔ Todo esto **propone**; no clasifica. Lo no-astro va al **triage** como candidato (INV-24: core
sigue siendo función de `(paper, lente)`), y `--resolve` propone una URL sin tocar `sources:`.

Qué cambia respecto del flujo ADS de arriba:
- **La mitad astro puede seguir descubriéndose:** si el tema es **mixto**, poblá `query:` **además**
  de `sources:` y el orquestador corre el descubrimiento ADS **completo** para esa mitad (misma
  lente, mismas puertas, misma compuerta de triage). Sin `query:`, la mitad astro entra sólo por los
  bibcodes que enumeres en `extra_core:` — medido en ICA: 11 papers a mano contra familias enteras
  que la query encuentra sola.
- **Sin ADS (si `query:` queda en null):** se saltean `query_ads.py`, `fetch_arxiv.py`, `fetch_pdf.py` y `fetch_ground_truth.py`. En
  `vault/config/themes.yaml` la entrada lleva `query: null`, el switch **`source: web | local-pdfs |
  local-pdfs+web`** y la bibliografía **declarada** en la lista `sources:` (cada item: `key`
  AAAA+Autor + `url` o `pdf` + `title/author/year/venue/n_authors/doi` opcionales; ver header del YAML); el resto
  del schema igual (`title`, `area`, `concept`, `aliases`). Con eso, **el mismo comando del paso 2**
  (`python scripts/ingest_theme.py <slug>`) orquesta todo: stub del concept, `fetch_web.py` por cada `url`,
  copia de cada `pdf` a `vault/raw/pdfs/<slug>/<key>.pdf` (nota con el campo `pdf` ya linkeado) y
  `extract_fulltext.py`. `--force` re-baja/re-copia **fuentes**, nunca pisa notas. Los bullets de
  abajo documentan las piezas por si hay que correr algo a mano.
- **Fuente = PDFs locales y/o web:**
  - **PDFs** que provee el usuario → copiarlos a `vault/raw/pdfs/<slug>/` (git-lfs) renombrados a la **clave de
    cita** (abajo); `python scripts/extract_fulltext.py <slug>` los pasa a `vault/raw/fulltext/<slug>/` (es
    source-agnostic: sólo corre `pdftotext`).
  - **Web** (rellenar fundacionales / huecos) → **preferido:** `python scripts/fetch_web.py <slug> <clave> <url>
    [--concept <concept> --title … --author … --year …]`. Baja la página con **defuddle** (quita
    nav/menús/clutter → markdown limpio, ~8× menos bytes que el HTML crudo, ~4× menos que pandoc), le pasa
    un **post-clean** determinista (saca bloques HTML de media/embed sueltos) y escribe el **snapshot**
    `vault/raw/fulltext/<slug>/<clave>.txt` con el encabezado **URL + fecha de acceso** ya puesto (citable y
    verificable por `verify-citations`). **Además crea el stub `vault/wiki/papers/<clave>.md`** (salvo
    `--no-note`). Requiere Node/npm (`npx defuddle`, JS-only; valida `<clave>` contra `BIBCODE_RE`,
    idempotente salvo `--force`). **Sin Node:** traer con `WebFetch`/`deep-research`, guardar el snapshot a
    mano (mismo encabezado) y stubbear la nota con `python scripts/make_notes.py --web <clave> --url … --concept …`.
- **Fuente no-conseguible (fallback — paywall / escaneo / mojibake):** si una fuente no se puede
  obtener (sin copia libre) o su PDF no rinde texto usable (escaneo sin capa de texto, fuentes sin
  ToUnicode → `extract_fulltext` avisa "ILEGIBLE"; con `tesseract` instalado **cae solo a OCR** y el
  `.txt` queda `source: ocr`, citable con salvedad — ver docs/operacion.md), **no frenar el ingest ni dejarla
  muda**: marcá el
  item de `sources:` con `pending: paywall|scan|unextractable` (dejando `url`/`doi` conocidos como
  puntero). La cadena stubbea la nota con `pending_source`, la **deriva al usuario** en el aviso
  final y el lint la lista como precondición. El resto del tema se arma igual con las fuentes
  limpias; la pendiente queda como hueco citado. Cuando el usuario provea el PDF/fuente: reemplazar
  `pending` por `pdf:`/`url:`, re-correr la cadena (idempotente) y completar la extracción.
- **Fuente evaluada y RECHAZADA (#81):** `sources:` registra lo que **aceptaste**; "miré este libro
  / esta URL y decidí que no es core" no queda en ningún lado si no lo escribís. Es el mismo juicio
  no regenerable que el del triage, en el otro carril — se pierde igual al cambiar de máquina o al
  volver seis meses después. Registralo en las **mismas `decisiones`** del registro versionado:
  ```bash
  python scripts/triage.py <slug> --drop-source <clave> --reason "<motivo>" --pointer <url|doi>
  ```
  No necesita `ads.json` (un off-ADS puro no lo tiene). Queda con `origen: fuente-declarada`, y si
  más adelante volvés a declarar esa clave en `sources:` la cadena **avisa** con el motivo antes de
  bajarla (avisa, no frena: quizá cambiaste de opinión a propósito). `python scripts/triage.py
  <slug>` sin `ads.json` lista lo registrado. **No cures en silencio:** el `--reason` es obligatorio.
- **Clave de cita sintética (papers sin bibcode ADS):** `AAAA+Autor` (p. ej. `2006RasmussenWilliams`,
  `2006Tichavsky`, `2025sklearn`). Debe **empezar con `AAAA`+letra** (lo exige `BIBCODE_RE` del lint) y
  coincidir con el nombre del `.txt`.
- **Tema MIXTO — papers del tema que SÍ tienen bibcode ADS** (un método no-astro casi siempre tiene
  aplicaciones/variantes publicadas en revista astro): van en **`extra_core:` (lista de mapas `{bibcode, via, fecha, motivo}` — D-58; el `triage` imprime el snippet listo para pegar)** de la
  entrada del tema, **no** en `sources:` con el bibcode como `key` (eso degrada el stub: metadata a
  mano, `citation_count: 0`, blockquote off-ADS factualmente falso). `ingest_theme.py` les corre solo
  la **sub-cadena ADS** (`query_ads --extra-only` → `fetch_arxiv` → `fetch_pdf` → `make_notes
  --theme`): stub con metadata ADS real, PDF por arXiv/resolver y chequeo de retracciones por la vía
  ADS. El tema queda mixto: `sources:` para lo off-ADS + `extra_core:` para lo que está en ADS.
  **Incluye los que ADS indexa fuera de `database:astronomy`** (eprints de `math.ST`, `eess.SP`,
  `stat.ML`…): la búsqueda por bibcode de `extra_core` corre **sin la lente astro** (#68), así que un
  paper de estadística/ML con bibcode ADS real entra por acá con su identidad ADS. Si un bibcode
  igual no vuelve, ahí sí es typo o registro renombrado — no hace falta degradarlo a `sources:`.
- **Notas de paper (automatizado):** `fetch_web.py` ya crea el stub `vault/wiki/papers/<clave>.md`; para
  fuentes **PDF** off-ADS (sin URL) usá `python scripts/make_notes.py --web <clave> --concept <concept>
  --slug-hint <slug> [--title … --author … --year … --n-authors … --doi … --venue …]`. El stub lleva el
  **mismo frontmatter** que
  una nota ADS más la provenance web: `bibcode` = clave sintética; `arxiv_id` null; `n_authors`/`doi` los
  del item de `sources:` si se declararon (un PDF con DOI sigue siendo off-ADS; con `doi`,
  `ingest_theme.py` corre además `check_retractions.py`); `source_url` +
  `accessed` (la **fecha del snapshot** — el "Retrieved <fecha>" de una cita web, la toma del `.txt`);
  `bibstem` = venue o dominio; `pdf`: null para un snapshot web (el respaldo es el `.txt`), pero
  **linkeado** si el PDF ya se copió a `vault/raw/pdfs/<slug>/` (fuente `local-pdfs`: verdad de
  disco, y así el chequeo PDF↔disco del lint no marca drift); `stars: []`; `thesis_links`
  al concept; `tags: [paper, web]` (snapshot de URL) o `[paper, local-pdf]` (PDF provisto).
  Completar la extracción LLM a mano.
- **Todo lo demás igual:** extracción enfocada en el eje del tema, síntesis al concept durable,
  auto-revisión de autosuficiencia, **`verify-citations`** (la clave sintética y el snapshot `.txt` la
  hacen chequeable), **`lint`** (0 bloqueante) y bookkeeping. **La frontera dura (regla #0) sigue
  rigiendo:** sólo bibliografía citable; nada de implementación de quien consume la bóveda.

## Notas
- Reglas de notación/reporte y schemas de frontmatter: ver `CLAUDE.md`. Notación matemática en `$...$`,
  filenames kebab-case (papers usan el bibcode), links internos `[[wikilink]]`.
- Distinción concept vs query: el concept es el resultado **durable** del tema (acumula solo). Una
  *query* archivada (`queries/`) es un snapshot complementario — opcional, sólo si vale re-preguntarla.
- **Lectura del fulltext (saltar afiliaciones):** los `.txt` arrancan con autores/afiliaciones que no
  aportan. Saltar al contenido con, p. ej., `awk 'tolower($0)~/abstract/{f=1} f' vault/raw/fulltext/<slug>/<bib>.txt | head -60`
  y `grep -inE "bisector|BIS|FWHM|S-?index|chromatic|correlat|lag" ...` para los números clave. No
  tocar el `.txt` en disco (se usa para grep); el salto es sólo en la lectura.
