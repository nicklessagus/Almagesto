---
name: ingest-star
description: Usar cuando el usuario pide bajar/agregar/ingestar una estrella a la bóveda ("bajá GJ 581", "ingest tau ceti", "agregá la estrella X", "traé la bibliografía de AU Mic"). Corre la cadena de ingesta y hace la extracción LLM.
version: 1.19.0
---

# Ingest: agregar una estrella a la wiki

Operación **ingest** del patrón LLM Wiki (ver `CLAUDE.md`). División: los scripts bajan, el LLM
procesa. Trabajar desde la raíz del repo.

## Pasos

**Copiá este checklist al chat al arrancar y andá tildándolo** — tres pasos (2b, 2c, 5b) son
fáciles de saltear y **ninguno deja rastro si se omite**. El lint tiene red para **2c** (*triage
pendiente*, #55), para **5b** (*sin verificar* / *verificación stale*, #56) y para lo que la
síntesis del paso **3c** dejó afuera (*extraído pero no sintetizado*, #75 — que es también la red
del contraste de **3b**); para **2b** no hay red todavía:

```
Progreso del ingest de <estrella>:
- [ ] 1  slug resuelto + alias mostrados al usuario y aprobados ANTES de buscar
- [ ] 2  cadena mecánica (orquestador) — sin abortos
- [ ] 2b barrido full-text (--sweep) revisado
- [ ] 2c triage de candidatos resuelto (aceptado / --drop con motivo / al usuario)
- [ ] 3  extracción LLM de TODOS los core (o recorte declarado en el registro)
- [ ] 3b contraste cross-paper (inventario por eje)
- [ ] 3c síntesis a la ficha (frontmatter propio + prosa + disputes)
- [ ] 4  auto-revisión de autosuficiencia
- [ ] 5  bookkeeping (index, log, matriz, STATUS) + `triage.py <slug> --sintesis`
- [ ] 5b verify-citations sobre la ficha + notas nuevas
- [ ] 6  `lint.py --cierre` en 0 → commit → preguntar push
```

1. **Resolver el slug y ACORDAR LOS ALIAS antes de buscar (D-7).** Buscar la estrella en
   `vault/config/stars.yaml`. Si no está, agregarla con `slug`, `simbad`, `ads_object`, `aliases` y
   (si aplica) `data_local`.

   ⚠ **El recall de toda la búsqueda cuelga de `aliases`, y un alias que falta es un paper que
   nunca aparece — en silencio.** Es el mismo modo de falla que el glifo griego, pero **sin
   rescate**: el glifo tiene su pasada de recuperación, un alias faltante no tiene ninguna. Por eso
   no se escriben a ojo:
   - Resolver identificadores en **SIMBAD** (`python scripts/fetch_ground_truth.py <slug>` los trae,
     o consultá SIMBAD directo si la estrella todavía no está en el YAML).
   - **Mostrarle al usuario la lista candidata en prosa** —con las variantes de espaciado y de glifo
     ya expandidas (`GJ 581` / `GJ581` / `Gliese 581` / `HO Lib` / `BD-07 4003`)— y decir cuáles
     venís a agregar y por qué.
   - **No correr la query hasta que apruebe.** Recién ahí persistir lo aprobado en `stars.yaml`.

   Es el mismo patrón que `setup` (los términos del objetivo, D-8) e `ingest-theme` (los términos
   del tema, D-29): el agente **propone**, el usuario **valida**, y lo aprobado queda escrito.

2. **Cadena mecánica** (orquestador — desde la raíz del repo):
   ```bash
   python scripts/ingest_star.py <slug>
   ```
   Corre la cadena completa (ADS → PDFs arXiv y no-arXiv → ground-truth NEA/SIMBAD → stubs →
   fulltext → retracciones), abortando al primer fallo. **El orden canónico vive en el header de
   `scripts/ingest_star.py`** — puntero, no copia: no lo repliques acá ni en otros docs. Para un
   flag fino (`--rows`, `--all`, `--force` de un paso) corré el script puntual.
   `fetch_arxiv` respeta el rate limit de arXiv (1 req/3 s) → puede tardar; correr en background si
   son muchos PDFs. Los papers sin arXiv —y los con arXiv cuya bajada falló— los intenta
   `fetch_pdf` (escaneo ADS con token → PDF del publisher, con fallback `curl`); lo que ni así
   sale queda en `build/<slug>/missing_pdf.json` (residuo completo del ingest, verdad de disco) —
   cada entrada trae su `bibstem` y un `hint` con la rama por donde seguir: la **cascada manual de
   rescate** está en `## Notas` de este skill (Messenger / página del instrumento / mirrors / tablas
   del CDN / derivar al usuario), y "bajar manual por DOI" **no alcanza**.
   La cadena es idempotente (no pisa): en un re-ingest, `fetch_ground_truth` **no** refresca un
   ground-truth existente salvo `--force` (refrescar desde NEA es decisión explícita, no side-effect).
   `check_retractions` consulta **Crossref** por DOI y, si un paper fue **retractado**, estampa
   `retracted: true` en su nota (el lint lo vuelve bloqueante) → revisá cada afirmación que lo cita.
   En la cadena corre con `--slug` (sólo los papers de **este** ingest); el barrido completo de la
   bóveda es la pasada periódica del skill `maintain`.
   `query_ads` hace además **citation chaining**: pide a ADS references/citations de los core,
   **ancladas al sujeto** con `full:` sobre nombre+alias — trae surveys/catálogos conectados por el
   grafo de citas aunque no nombren la estrella en el abstract (quedan marcados `via: chain:*` en
   `ads.json`; se desactiva con `--no-chain`).
   **Guardia de expansión (checkpoint humano).** Entre `query_ads` y el primer paso que gasta red
   y disco, el orquestador compara el core del `ads.json` fresco contra las notas ya ingestadas del
   sujeto: si se multiplicó (default ×1.5 y 50 o más nuevos) **frena** con el conteo, cuántos vinieron
   por el grafo de citas y el puntero a `relevance.require`/`min_facets`. Antes de refrescar un
   sujeto viejo, mirá ese número: si el pool explotó, revisá la **regla de combinación** en
   `objective.yaml` (skill `setup`) antes de bajar nada — podar las regex no alcanza si la
   combinación sigue siendo OR. `--yes` continúa a sabiendas.
   Si el nombre es **Bayer** (letra griega + constelación) corre antes el **rescate por glifo**
   (`via: glyph`, se desactiva con `--no-glyph`): ADS unifica `epsilon`/`eps`/`ε` pero **descarta**
   los lookalikes `ϵ` (U+03F5) y `∊` (U+220A, el glifo de ApJ/AJ/MNRAS), así que esos papers quedan
   indexados sólo por la constelación e **invisibles** a la query canónica (medido en ε Eri: 121
   core perdidos, incluido el descubrimiento). No hace falta listar las grafías en `aliases`: el
   carácter se descarta, no falta la variante — el rescate trae el superset de la constelación y
   filtra client-side por el glifo.

2b. **Barrido full-text (NO perder surveys de muestra grande).** La query directa de `query_ads.py`
   busca en **título+abstract** → punto ciego sistemático: los **surveys de muestra grande**
   (Mount Wilson HK, catálogos de actividad) **tabulan la estrella sin nombrarla en el abstract**. El
   **chaining del paso 2 ya trae** los que están conectados por citas a los core encontrados; este
   barrido caza los que quedan **fuera del grafo** (o cuyos core-vecinos no entraron). Correr:
   ```bash
   python scripts/query_ads.py <slug> --sweep
   ```
   Corre `full:` sobre nombre+aliases expandiendo solo **todas las grafías** (`HD 152391` ↔
   `HD152391` — ADS tokeniza distinto y los papers usan ambas; antes esto eran probes manuales por
   grafía, fáciles de olvidar) y lista **sólo los core que el ingest NO trajo** — la lista corta de
   candidatos, ordenada por **citas/año** y no por citas crudas (#79: el barrido existe para
   recuperar casos tipo Garg+2019 / Willamo+2020, core poco citados que caen al fondo del ranking;
   rankearlo por citas repetía el sesgo de edad del mecanismo que le falló). Revisarla y agregar los que correspondan **de forma persistente** con
   `extra_core:` (lista de mapas `{bibcode, via, fecha, motivo}` — D-58; el `triage` imprime el snippet listo para pegar) en la entrada de la estrella en `vault/config/stars.yaml` (el
   `query_ads` los trae por bibcode, `via: manual`, y sobreviven al re-run — a diferencia de editar
   `build/`, que es scratch y se pisa); después re-correr la cadena (idempotente). Si el barrido
   devuelve muchos y no bajás todos, **listá cuántos quedan sin bajar** en el `log` — no cures en
   silencio. (Un resultado vacío **no prueba ausencia** en papers pre-digitales — ver Notas: el OCR
   del escaneo pierde filas de tabla.)

2c. **Compuerta de triage del chaining (juicio, antes de bajar nada).** El chaining trae papers
   conectados por citas que **mencionan** al sujeto sin hablar de él: la lente clasifica **tema**, no
   **pertinencia al sujeto** (medido: de 378 core nuevos, 368 del grafo y sólo 18% pertinentes —
   incluyendo una tesis de física de partículas como "core" de AU Mic). Y no se aproxima con una
   regla sintáctica: la densidad de mención sale **invertida** (los ruidosos nombran al sujeto 27
   veces de mediana; los valiosos, 2). Por eso el juicio es tuyo. `query_ads` ya auto-aceptó los que
   llevan **el sujeto en el título** (1 falso positivo en 310) y dejó el resto como **candidatos**
   —no bajados—:
   ```bash
   python scripts/triage.py <slug>            # listar (agregá --report para la tabla en outputs/)
   ```
   (En una bóveda ingestada antes de 1.9.0, `--migrate` consolida de una vez el juicio que haya
   quedado en el `build/<slug>/triage.json` viejo; ver `maintain E`.)
   Los marcados `◆` **ya tienen nota en la bóveda** (entraron por otro slug): ya están bajados y
   extraídos — la decisión sigue siendo por-slug (¿pertinente a ESTE sujeto?), pero se despachan
   rápido (el `stars:` que falte lo cubre el retro-linkeo add-only de `make_notes`).
   Clasificá cada candidato **sólo por título+abstract** (no bajes nada para decidir):
   - **pertinente** → pegá el snippet que imprime `triage.py` en `extra_core:` de `vault/config/stars.yaml` y re-corré
     la cadena (idempotente: baja sólo los nuevos; `extra_core` es override del clasificador).
   - **ruido** → `python scripts/triage.py <slug> --drop <bib> … --reason "<motivo>"` (persiste en
     `decisiones` de `vault/config/registro/<slug>.yaml` — **versionado: se commitea y viaja**, como
     `extra_core`; el próximo refresh no lo re-propone, tampoco en otra máquina). Agrupá por
     categoría y descartá por lote, con el motivo real: el motivo es lo que hace que la decisión
     sirva dentro de seis meses.
   - **dudoso** → **al usuario**, junto con (a) los papers que salen del core y ya tienen extracción
     LLM y (b) el resumen de volumen (core nuevo vs notas actuales). `--report` deja la tabla en
     `outputs/triage-<slug>.md` para decidir por lote.
   No curar en silencio: lo descartado queda con motivo, y lo que quede sin decidir se anota en el `log`.
   **El lint tiene red (#55):** lo que quede en `candidates` sale como backlog *Triage pendiente* —
   antes el aviso vivía sólo en este stdout y el ingest podía cerrarse "en 0" con cientos sin
   juzgar. Sin `build/` local, el lint cae al `busqueda` del registro versionado y reporta el
   snapshot con su fecha (#51/#64), así que la red ya no depende de la máquina — pero el conteo del
   snapshot es el de la última corrida de la cadena, no el vigente.

3. **Extracción LLM — se leen TODOS los core (D-13).** *"Leer los papers clave"* no es un criterio:
   no dice cuántos, ni en qué orden, ni deja registro de qué se leyó. Es lo que produjo el número
   medido en una bóveda real: **42 papers `relevance: high` que nadie abrió**, en una ficha que se
   presenta como el snapshot del conocimiento de la estrella. Si la lente marca 193 como core y la
   extracción lee 40, "core" deja de ser la unidad de trabajo y el consumidor no sabe cuál de los
   dos números lo describe.

   - **Default: se leen todos los core.**
   - Si no se leen todos, **se avisa al usuario** y el motivo queda **registrado**:
     ```bash
     python scripts/triage.py <slug> --extraccion subconjunto --reason "<el criterio>"
     python scripts/triage.py <slug> --extraccion todos          # el default del contrato
     ```

   ⚠ **Cómo anotar cada valor (#103) — la regla que evita cuatro de los seis mecanismos de error
   medidos.** El fan-out de `verify-citations` sobre una ficha real (2026-08-25, HD 40307: 68 pares,
   16 fuentes) devolvió **54 soportada / 11 parcial / 3 contradice / 0 no-soportada**. Cero
   `no-soportada` significa que **no se inventó nada**; los 14 defectos fueron de otro tipo:

   | Mecanismo | Casos | Ejemplo real |
   |---|---:|---|
   | **Cita de segunda mano** — se lee A, que cita a B, y el número se guarda como de B | 3 | «≈12,1 m/s/dex» atribuido a Lovis: está en Díaz **citando** a Lovis, y no aparece en el `.txt` de Lovis |
   | **Fila/columna equivocada** de una tabla multi-objeto | 2 | `log R'HK = −5,02` es de HD 1461, no de HD 40307 — misma tabla |
   | **Inferencia con voz de cita** | 3 | «las dos familias de P_rot no se solapan»: ninguna fuente lo dice |
   | **Cantidades parecidas** confundidas | 3 | error formal (0,77→0,64) vs dispersión (3,53→2,59) |
   | **Epígrafe que el cuerpo del paper contradice** | 1 | activa/inactiva invertidas: la Fig. 9 de Díaz dice al revés que su §6 |
   | **Régimen omitido** (los 11 `parcial`) | 11 | la Tabla 4 de Tuomi es la **mitad roja** (490–680 nm), no el espectro completo |

   Por eso, al copiar un valor a la nota de paper:
   - **el nº de línea del `.txt`** al lado (`grep -n`, nunca `splitlines()` — form feeds);
   - **el régimen** en el que la fuente lo afirma: muestra, época, corte de datos, modelo ajustado;
   - si la fuente **atribuye el valor a otro trabajo** (*«according to X»*, *«(X et al.)»*), marcarlo
     **segunda mano** y citar a X — el número **no es de esta fuente**;
   - ⛔ **nada de prosa comparativa en la nota de paper.** Comparar dos papers es `inferencia` y su
     lugar es el `## Inventario por eje` de la ficha (paso 3b). Escribirla acá es lo que produjo los
     3 casos de «inferencia con voz de cita».

   El stub de `## Extracción (LLM)` que genera `make_notes` ya trae esta regla como último bullet.
     El lint lo reporta como *recorte de lectura sin declarar* mientras no esté. El criterio se
     **declara**, no se aplica implícito — y `--reason` es obligatorio con `subconjunto` por el
     mismo motivo que en `--drop`: es la pieza que más se va a leer dentro de seis meses.
   - **Sea cual sea la decisión, la tabla `## Papers` de la ficha declara cuál entró y cuál no** — el
     estado nunca es implícito. Se re-estampa con `python scripts/make_notes.py <slug>`.

   **Escala: un subagente por paper (D-14).** 193 fulltexts no entran en una lectura. Se paga como
   ya se paga `verify-citations`: **un subagente por paper**, cada uno lee un solo
   `vault/raw/fulltext/<slug>/<bibcode>.txt` y devuelve la extracción estructurada. Caro pero
   acotado, y hace el paso **auditable**: cada extracción tiene su corrida. Lanzalos en tandas
   paralelas; el orquestador (vos) mergea y escribe las notas.

   Poblar **las notas de paper** (la ficha se escribe en 3c, después del contraste — no saltear
   directo a la prosa):
   - en `vault/wiki/papers/<bibcode>.md`: `methods`, `thesis_links`, `role` (#73: `fundacional`
     introduce el método/mecanismo · `aplicacion` lo instancia en un caso · `arbitro` reanaliza y
     resuelve una tensión previa — sale de leer el paper, la regex del clasificador no puede
     inferirlo, y sin él contrastarlo contra otro no está definido), y la sección
     "Extracción" — sus bullets ya vienen ramificados por tipo de sujeto (#76): ground-truth
     (P/K/e por planeta), los **ejes de `relevance.facets`** del objetivo de esta bóveda, métodos y
     aporte al objetivo. Llenar los que el stub trae, no una lista fija de memoria.
   ⚠ **`pdf_source` antes de copiar un número** (#57): con `eprint` el `.txt` es el **preprint**
   (un `v1` pre-referato puede traer otros valores que el publicado que identifica el bibcode), y con
   `null` no se sabe —que **no** es "publicado"—. Un valor que choca con el ground-truth o con el
   abstract de ADS es candidato a **diferencia de versión**: abrí el PDF publicado o dejá la
   salvedad en la nota. `verify-citations` lo detecta después; **acá es donde el número entra a la
   bóveda**.

3b. **Contraste cross-paper (#72) — antes de escribir la síntesis.** Entre "leí los papers" y
   "escribo el resumen" hay una operación, y es la de más apalancamiento de la cadena: armar el
   **`## Inventario por eje`** de la nota. Una fila por paper para cada **eje** —parámetro o hecho—
   donde los papers **no coinciden** (`Eje | Paper | Dice | Método / baseline`). Los ejes con acuerdo
   unánime **no entran**: misma regla de poda que la prosa.
   ⛔ **Sin columna "valor adoptado" ni "por qué".** Adoptar un valor es **decidir por el
   consumidor** y rompe el flujo unidireccional de la regla #0: la bóveda reporta el **estado de la
   literatura**. La lectura propia —"11.5 d es el armónico de 34 d"— va aparte y marcada
   `inferencia`.
   ⚠ **Mirá el `role` (#73) antes de leer dos filas como desacuerdo:** fundacional↔aplicación **no
   es contraste, es instanciación**. Y el `arbitro` no es una fila más: es el que resuelve.
   Sin esto, tres papers con tres `P_rot` terminan en una frase con un solo `[[bibcode]]` y se
   evapora que los otros dos valores existen — que es exactamente lo que la ficha promete responder
   sin abrir un paper. La red de que el contraste ocurrió es #75 (*extraído pero no sintetizado*):
   un paper que pagó la extracción y no aparece en la nota sale como backlog.

3c. **Síntesis a la ficha** (`vault/wiki/stars/<slug>.md`), apoyada en el inventario de 3b.
   Completar el frontmatter que es **tuyo** (`activity_indicators_expected`,
   `methods_applied.literature`, `disputes` —a nivel nota, #71—) y escribir la prosa: qué se sabe, qué
   indicador debería trazar actividad para ese tipo espectral, huecos.
   ⛔ **No toques los campos de ground-truth** (`spectral_type`, `teff_K`, `dist_pc`, `P_rot_days` y
   los cinco de cada `planets[]`): son **espejo de NEA** (#70). Si NEA no tiene el valor —pasa
   seguido con `K_ms` y `e`— el campo queda **null** y el valor de literatura va **al cuerpo, citado
   `[[bibcode]]`**; si discrepa de NEA es una `disputes[]`; si es lectura tuya va marcado
   `inferencia`. Rellenarlos vuelve el número indistinguible del auditable y el lint lo marca como
   **bloqueante**.
   - **Contrastar contra `vault/raw/ground_truth/<slug>.json`**: si un paper discrepa del archivo
     (p. ej. planeta dudoso), taguearlo en `disputes` **a nivel nota** con posiciones explícitas
     (#71) —`field: b.existence`, una posición `{ref, value}` por el paper y otra
     `{source: ground_truth, value}` por NEA—; ver *Disputas* en `CLAUDE.md`. No celebrar.
     (⛔ **`bearing` no va en la nota del paper** — D-21: la postura vive en la tabla de evidencia de
     la hipótesis, y en el paper el lint la bloquea como schema viejo.)
     Si el desacuerdo es **paper↔paper** sobre algo que NEA no arbitra (`P_rot`, la naturaleza de
     una señal), va en la MISMA estructura con dos posiciones `{ref, value}`: eso es lo que antes
     terminaba en prosa suelta.

4. **Auto-revisión de autosuficiencia (semántica).** Releer la ficha **como un agente externo que
   sólo tiene ese archivo**: ¿se entiende la estrella sin abrir ningún paper? Checklist: parámetros
   estelares clave, inventario de señales RV (tabla $P/K/e/m\sin i$ + estado), señales
   disputadas/descartadas, indicadores de actividad esperados, métodos aplicados y huecos. Si para
   responder algo hay que abrir un paper, falta en la ficha → agregarlo. (`lint.py` chequea dos
   proxies estructurales — cada planeta del frontmatter discutido en prosa, y cada paper **extraído**
   citado en alguna ficha o concepto (#75) — pero la suficiencia la juzgás vos.)
   ⚠ **El backlog *extraído pero no sintetizado* es el que cierra este paso:** un paper que pagó la
   extracción y no aparece citado en ninguna entidad es extracción perdida. O lo sintetizás donde
   corresponda, o declarás por qué no va: `no_sintetizado: <motivo>` en su nota (la **regla de poda**
   es motivo válido; la marca sin motivo se sigue reportando).

5. **Bookkeeping.** Actualizar `vault/wiki/index.md` (agregar la estrella), appendear a `vault/wiki/log.md`,
   tocar `vault/wiki/matrices/method_star.md` (qué métodos se aplicaron en la literatura) y `vault/STATUS.md`
   si cambió el estado. Y **declarar la fecha de síntesis** —la tercera de la cabecera (INV-82)—:
   ```bash
   python scripts/triage.py <slug> --sintesis --n-papers <N>
   python scripts/make_notes.py <slug>          # la estampa en la ficha (cirugía, no toca la prosa)
   ```
   No se puede derivar: `git` fecha el **archivo**, así que una cirugía de cabecera contaría igual
   que reescribir el resumen. Sin ella, refrescar el corpus mueve la fecha de búsqueda y la ficha se
   lee como re-sintetizada cuando la prosa es la de tres meses atrás. (El `lint` va **después** del verify del paso 5b: `CLAUDE.md` lo pide
   "antes de lint/commit", porque resolver una cita no-soportada suele cambiar la prosa.)

5b. **Verificar citas.** Correr el skill `verify-citations` sobre la **ficha de la estrella** (y sobre
   las notas de paper nuevas con extracción). La ficha es el artefacto **más reusado** (se arma un
   informe desde ahí), así que su prosa con `[[bibcode]]` —parámetros estelares, señales RV, disputas—
   debe estar respaldada por el fulltext (cita textual + nº de línea del `.txt`; sin respaldo ⇒
   no-soportada). Prioridad: las afirmaciones que **cambian cómo se lee una señal RV** y las
   `disputes` (cada `posiciones[].value` y el `note` vs el paper que la sostiene; la posición
   `{source: ground_truth}` no se verifica contra papers). Resolver cada no-soportada/parcial (corregir el valor,
   reasignar la cita, o marcar `inferencia`) y dejar el bloque `## Verificación de citas`.

6. **Cierre (commit + push).** Tras la verificación (lint en 0), `git add` de los archivos
   **específicos** que tocó la operación (no `-A`) y commitear con mensaje
   descriptivo. Después **preguntar al usuario si hace `push`** — no pushear sin confirmación.

## Notas
- Reglas de notación/reporte y schemas de frontmatter: ver `CLAUDE.md`.
- No copiar FITS a la bóveda: la ficha apunta a los datos vía `data_local`.
- **Lectura del fulltext (saltar afiliaciones):** los `.txt` arrancan con autores/afiliaciones que no
  aportan a la extracción. NO leer las primeras páginas enteras: saltar al contenido con, p. ej.,
  `awk 'tolower($0)~/abstract/{f=1} f' vault/raw/fulltext/<slug>/<bib>.txt | head -60` para el abstract, y
  `grep -inE "P_?rot|K ?=|mass|chromatic|GP|activity indicator" ...` para los números clave. No tocar
  el `.txt` en disco (se usa para grep); el salto es sólo en la lectura. **Patrones cortos, siempre**
  (#44, convención canónica en `verify-citations`): el `.txt` entrelaza las dos columnas en la misma
  línea física (73% del corpus), así que un patrón largo da falso negativo — y acá el falso negativo
  se lee como "el paper no reporta ese parámetro", que es exactamente lo que la extracción decide.
- **Mirá las TABLAS, no sólo el texto.** En papers viejos las tablas suelen ser **imágenes** (en el
  escaneo de ADS y a veces hasta en el HTML del publisher). El dato de la estrella (P_cyc, P_rot, rama…)
  vive ahí → **invisible a cualquier búsqueda de texto**. Para confirmar si una estrella está en un paper
  y para extraer sus valores, **abrí la tabla** (imagen o PDF), no te fíes del grep.
- **Un `full:"HD X" → 0` NO prueba ausencia** en papers pre-digitales: el **OCR del escaneo de ADS pierde
  ~½ de las filas** (medido: 12/26 estrellas en Saar & Brandenburg 1999; faltaba hasta HD 81809). Nunca
  afirmar "la estrella no está en ese paper" desde un hit full-text negativo — **corroborar** (papers que
  lo citan y le atribuyen datos) o **abrir el PDF/tabla**. Reportar honesto: es inconcluso, no ausencia.
- **Cascada de adquisición de PDFs no-arXiv (canónica — `ingest-theme` y `append-knowledge` apuntan
  acá; ver también backlog en `vault/STATUS.md`).** Lo que quedó en `build/<slug>/missing_pdf.json`
  **ya falló** en `fetch_pdf.py` (resolver ADS: `EPRINT_PDF` → `ADS_PDF` con token → `PUB_PDF`, con
  fallback `curl`), y "bajar manual por DOI" **no alcanza** (medido en un ingest real: el resolver
  falló en **5 de 17** — pre-arXiv de 2000–2015: SPIE, The Messenger, A&A viejo; **4 de 5 se
  recuperaron** por estas ramas). `fetch_pdf` imprime el **bibstem** de cada fallo con la rama
  sugerida y la deja en el `hint` de cada entrada del residuo. En orden de rendimiento:
  1. **Archivo de The Messenger** (`Msngr`) — **todo el Messenger es abierto**:
     `eso.org/sci/publications/messenger/archive/no.<N>-<mes><aa>/messenger-no<N>-<pp>-<pp>.pdf`.
  2. **Página de papers del instrumento** (`SPIE` y proceedings en general) — p. ej.
     `eso.org/sci/facilities/lasilla/instruments/<inst>/science/papers/<vol>-<pp>.pdf`: tiene **en
     abierto** SPIE que de otro modo son paywall.
  3. **Mirrors académicos** por búsqueda web (páginas personales, repositorios institucionales).
  4. **Imágenes de tabla del CDN del publisher** (p. ej. IOP
     `content.cld.iop.org/journals/.../tbN.gif`) — **funcionan aunque el PDF esté tras paywall** y
     suelen tener el dato que se busca; ídem el HTML legacy del publisher (frameset `…/fulltext/`).
  5. **Pedir el PDF al usuario** (tiene acceso institucional; anduvo con Frick 2004 y Saar 1999) —
     mientras tanto, estampá `pending_source: paywall` en el frontmatter de la nota del paper (el
     lint la lista como precondición hasta que la fuente llegue).
  Guardá el artefacto citable (PDF o imagen de tabla) en `vault/raw/`.
  ⛔ **No gastar intentos en `aanda.org`:** está detrás de **DataDome** — cualquier `curl` (con UA de
  navegador, con `Referer`, siguiendo redirects) recibe un challenge JS (`Please enable JS…`,
  `ct.captcha-delivery.com`). Para un **A&A pre-arXiv** que el resolver no entrega no hay preprint y
  Semantic Scholar lo da `openAccessPdf: CLOSED` → **derivar al usuario de una** (se resuelve en una
  vuelta con acceso institucional).
- **OCR: lo maneja solo `extract_fulltext.py`.** Chequea si el PDF trae **capa de texto** legible
  (umbral determinista: chars no-espacio, **densidad por página** y fracción de ASCII imprimible) y,
  si no (escaneos-imagen puros, p. ej. Baliunas 1995, o fuentes sin
  ToUnicode), **cae solo a OCR** cuando hay `tesseract` instalado — el `.txt` queda con header
  `source: ocr`, **citable con salvedad** (ver docs/operacion.md); sin tesseract AVISA y el lint lo lista. Ojo
  con quirks de PostScript viejo en la extracción (p. ej. el signo `-` y `>` pueden salir ambos como
  `[`): los datos están, sólo hay que desambiguar por contexto.
  - ⚠ **Síntoma "escaneo con marca de agua"**: un `.txt` de unos **cientos de bytes** con el
    **bibcode repetido** una vez por página **no es un fallo de descarga** — el `ADS_PDF` bajó bien,
    pero es un escaneo **sin capa de texto** cuya única capa es la marca de agua de ADS. Lo agarra la
    **densidad por página** del umbral (#50; antes pasaba como "extraído" porque el poco texto que
    hay *es* legible) → dispara el OCR como cualquier escaneo. Si te topás con un `.txt` viejo así,
    re-extraé con `python scripts/extract_fulltext.py <slug> --ocr --force`. Caso medido:
    Baranne+1996, 378 bytes → 77 KB por OCR (`fulltext_source: ocr`).
