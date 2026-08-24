# Contrato funcional de la capa determinista de Almagesto

> **Versión del framework al escribirlo:** 1.23.1 (working tree de la 8ª pasada; HEAD `20148d0` = v1.23.0).
> **Fecha:** 2026-08-23.

---

## 1. Qué es y qué no es este documento

**Qué es.** El enunciado, con ID estable, de **lo que la capa determinista de Almagesto tiene que
garantizar** para que las promesas del `README.md` y de `CLAUDE.md` se sostengan — esté implementado
o no. Cada invariante viene con: enunciado **falsable**, **estado** (medido / sin medir / incumplido
/ hueco) y **cómo se verifica** (el comando o test que lo fija hoy, o el que habría que escribir).

**Qué no es.**
- **No es documentación de la implementación.** No describe cómo funciona un script; describe qué se
  le exige. Si el código cambia y el invariante sigue valiendo, este archivo no se toca.
- **No es el schema de la bóveda.** Ese vive en `CLAUDE.md` (frontmatter, operaciones, severidades) y
  este documento lo da por sentado.
- **No cubre la capa LLM.** Extracción y síntesis son juicio de modelo. Sí cubre **todo lo que las
  rodea y las protege**: lo que las alimenta, lo que no las pisa, y lo que detecta que no ocurrieron.
- **No resuelve las decisiones de intención.** La sección 6 las enuncia como disyuntiva y las deja
  abiertas: son del usuario.

**Por qué está separado del código.** Hasta hoy los invariantes vivían **dentro de los docstrings**,
que son a la vez la especificación y el comentario de la implementación, escritos por la misma mano y
en el mismo commit. Nada los contrastaba, y por eso la 7ª pasada encontró docstrings afirmando
garantías falsas (*"Exit 0 siempre"* mientras salía 1; *"preserva byte a byte"* mientras corrompía).
Un contrato que vive dentro de lo que debe verificar no verifica nada. Este archivo es el **oráculo
externo**: cuando el código y el contrato discrepan, discrepan **a la vista**.

**Cómo se construyó.** Cruzando dos documentos escritos por separado y sin verse:

- **(A) Lo que el sistema dice y hace hoy** — la 8ª pasada de verificación: 139 líneas-garantía →
  46 afirmaciones falsables → **41 ejecutadas** (34 confirmadas, 5 refutadas, 2 parciales); 30
  garantías dinámicas medidas a escala sobre corpus poblado; las **30 categorías del lint sembradas
  una por una** con delta y exit code; los 9 skills con sus 45 invocaciones; el libro mayor de
  versiones por worktree; y los números de la doc re-medidos contra una instancia real de 908 papers.
- **(B) Lo que el sistema debería garantizar** — **75 invariantes derivados sólo del propósito**, por
  un agente que trabajó **a ciegas**: no leyó `scripts/`, ni `tests/`, ni `vault/STATUS.md`, ni
  ningún informe de auditoría. Sólo `README.md`, las partes de contrato de `CLAUDE.md`, los `.yaml`
  de config y los encabezados de los skills.

La ceguera fue deliberada: si (B) hubiera visto (A), reproduciría sus conclusiones y el contraste no
mediría nada. **El valor está en el cruce**, no en ninguno de los dos lados.

### Resultado del cruce

| Categoría | Qué significa | Cuenta |
|---|---|---|
| **garantizado y medido** | está en (B) y (A) lo midió verdadero, ejecutando | **43** |
| **garantizado sin medir** | está en (B), el sistema parece garantizarlo (código leído o mecanismo presente), pero nadie lo ejecutó como prueba | **19** |
| **INCUMPLIDO** | está en (B) y se midió falso | **4** |
| **HUECO** | está en (B) y el sistema **ni siquiera intenta** garantizarlo | **9** |
| | **total** | **75** |

Los 19 *sin medir* son **deuda de verificación**, no hallazgos: la diferencia entre "creemos que sí"
y "lo vimos". Nueve de ellos son P0 según la escala de (B), y ese es el número que importa.

> ⚠ **Esa tabla es el resultado del cruce del 2026-08-23 sobre los 75 invariantes de entonces**, y se
> conserva como registro de ese ejercicio. Después entraron los 16 de §3.K y corrieron las tandas
> 0–6. **Medición vigente (2026-08-24, sobre los 91)**: 63 *garantizados y medidos* · 13 *sin medir*
> · 6 *parciales* · 8 *HUECO* · 1 *INCUMPLIDO*. El salto no es trabajo de documentación: son las
> siete tandas, más una auditoría que encontró que varias filas estaban **peor escritas que el
> código** (INV-21, 29, 32, 38, 39, 49, 51, 56, 60 declaraban deuda ya saldada) y dos que estaban
> **mejor escritas que el código** (INV-43 e INV-72 afirmaban garantías que no había).

---

## 2. Cómo leer el estado

**Los cuatro estados.**

- `garantizado y medido` — hay una corrida que lo puso a prueba y pasó. Se nombra el instrumento.
- `garantizado sin medir` — el mecanismo existe y se leyó en el código, pero **no se ejecutó** una
  prueba que pudiera fallar. Es la fila donde hay que ser más desconfiado: es exactamente el estado
  en el que estaban los docstrings que la 7ª pasada refutó.
- `INCUMPLIDO` — medido falso. Con el número, el comando y el alcance.
- `parcial` — el enunciado tiene dos mitades y **una sola** se cumple. Sólo vale si la fila
  **nombra qué mitad falta**: un "parcial" sin eso es un "medido" con excusa. Nació el 2026-08-24,
  al medir §3.K: cinco de esos invariantes prometen dos cosas (una pasada de red que cubre *cinco*
  eventos, *tres* fechas, materializar *todos* los roll-ups) y el sistema hace una.
- `HUECO` — no hay mecanismo. No es que falle: es que nadie lo intentó.

**Escala de prioridad (heredada de (B)).**

| Prio | Consecuencia si se viola |
|---|---|
| **P0** | La bóveda afirma algo falso, o se destruye trabajo humano/LLM no regenerable. Daño irreversible o indetectable. |
| **P1** | Se pierde una **garantía** prometida (trazabilidad, reproducibilidad, cobertura). La bóveda no miente, pero deja de ser confiable como artefacto. |
| **P2** | Higiene, fricción, ruido de diff. Molesta, no engaña. |

**Los cuatro principios de los que cuelga todo** (del `README.md` §El límite y §La capa LLM):
1. **No mentir** — nunca producir un artefacto que afirme, o se lea como afirmando, algo que la
   fuente no respalda; incluido *afirmar de menos* (omitir sin marcar).
2. **No destruir** — nunca perder trabajo caro y no regenerable (síntesis del modelo, juicio del humano).
3. **No confundir capas** — mantener distinguible lo auditable (ground-truth, disco, config) de lo
   opinable (prosa del modelo, inferencia).
4. **No dar falso limpio** — cuando no puede garantizar algo, decirlo; jamás callarlo.

**Instrumentos citados.** `tier 0` = `pytest tests/` (850 casos, ~4 s — medido 2026-08-24); `tier 1` = `pytest -m
poblada` (corpus sintético de 900 notas vía `tests/poblada/generador.py::sembrar_corpus`); `tier 2` =
`pytest -m instancia` (contra una bóveda real, opt-in por env var); `8ª F1/F4/…` = los harnesses de
la octava pasada de verificación.

---

## 3. Los invariantes

### A. Frontera dura y admisión (regla #0)

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-01** | Toda línea que la capa determinista escribe en `vault/wiki/` es copia verbatim de una fuente auditable, metadata derivada de ella, o andamiaje vacío. Nunca un valor fáctico de origen indeterminado. | P0 | garantizado sin medir | Parcialmente cubierto: el espejo deja `null` donde NEA calla (8ª F1 #2a). **Falta**: correr la cadena entera en un vault vacío sin intervención del modelo y auditar cada valor no vacío contra `raw/`, `config/` o la respuesta cruda de ADS. Hacible offline (`requests` mockeado, como 8ª F1 #21). |
| **INV-02** | Al cerrar cualquier operación no queda en `vault/wiki/` un `[[wikilink]]`, un `thesis_links` ni una `ref` de disputa sin nota destino. | P0 | **garantizado y medido** | Cuatro categorías bloqueantes sembradas una por una con delta 0→1 y exit 1: `broken`, `dangling_thesis`, `dangling_disputes` (8ª F4 §2). Prueba negativa incluida: borrar el destino lo reporta. |
| **INV-03** | Para cada clave de cita hay fulltext local **o** la nota declara por qué no. No hay tercer estado silencioso. | P1 | **garantizado y medido** | Categorías `unverifiable` (cita sin `.txt`) y `pending_srcs` (`pending_source` declarado) sembradas (8ª F4 §2). Falta la prueba de conjunto (citas − disco − pendientes = ∅) como test propio. |
| **INV-04** | La capa determinista no genera material de implementación, y existe un chequeo que lo señala cuando lo escribió otro. | P1 | **garantizado y medido** | `impl_leaks` sembrada: 1 hit en prosa, 0 en blockquote, WARN, exit 0 (8ª F1 #31). ⚠ Es **no bloqueante** custodiando una regla declarada *no negociable* → decisión de intención §6.3. |
| **INV-05** | La capa determinista sólo escribe punteros externos en campos estructurales del frontmatter; nunca prosa que describa al consumidor. | P2 | garantizado sin medir | `grep` sobre las plantillas de `make_notes.py` buscando mención de consumidores. Nadie lo corrió. *Nota: el riesgo real vive en la capa LLM, no acá — el invariante apunta medio a la capa equivocada, pero el chequeo es trivial y conviene tenerlo.* |

### B. Autoridad de las fuentes: el espejo del ground-truth (#70)

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-06** | Cada campo espejo vale exactamente lo que dice el ground-truth, o `null`. Nunca literatura, nunca redondeo sin registro. | P0 | **garantizado y medido** | 7 violaciones distintas sembradas → exit 1 con **un hallazgo por campo**: `teff_K` inventado, `P_rot` rellenado, `K_ms` rellenado (8ª F1 #2b). `mirror_issues()` (`lint.py:389`) compara campo por campo en las dos direcciones. Confirmado además contra la instancia real: 13 hallazgos vivos (8ª F5). |
| **INV-07** | Si el ground-truth no trae el campo, el frontmatter lleva la clave presente y en `null`. No se omite ni se completa por otra vía. | P0 | **garantizado y medido** | `make_notes` deja `P_rot_days`/`K_ms`/`e` en `None` cuando NEA calla (8ª F1 #2a). La rama "la ficha tiene valor y el GT no" se reporta con mensaje propio (`lint.py:400-403`). |
| **INV-08** | Ninguna otra operación modifica un campo espejo. Una re-corrida lo sincroniza con la fuente vigente; nada más lo toca. | P0 | **garantizado y medido** | Probado por operación: `make_notes` sin `--force` (8ª F4 G2.1/G2.2), `--restamp-headers` (G2.3), `--restamp-pdf-links` (G2.4), `--migrate-disputes` (G2.5), `--sync-mirror` add-only (G2.6, 8ª F1 #39), retro-linkeo (F1 #10). Control de cordura: `--force` **sí** destruye (G2.7) — sin él los seis OK serían falsos negativos. |
| **INV-09** | La comparación ficha↔ground-truth es por **identidad** (qué planetas, campo por campo), no por cardinalidad. | P0 | **garantizado y medido** | El caso adversario —dos listas del mismo largo con letras distintas— falla como corresponde (8ª F1 #2b: planeta extra, planeta de NEA ausente, letra repetida, `P_days ≠ GT`). Fue el defecto que cerró #70 y hoy tiene test. |
| **INV-10** | Las derivaciones cruzadas se recalculan y las inconsistencias se **reportan**; nunca se reescribe la fuente para hacerla consistente. | P0 | **garantizado y medido** | `mass_issues` sembrada (8ª F4 §2); el lint re-deriva la m·sini implícita offline (`lint.py:850`) y no escribe una línea en `vault/` (8ª F4 G1.8). |
| **INV-11** | Ante fuentes en conflicto la capa determinista nunca elige un valor: ofrece la estructura para registrar ambas posiciones y deja el espejo intacto. | P0 | **garantizado y medido** | La regla está escrita (`CLAUDE.md` §2b, *"sin columna valor adoptado ni por qué"*) y el frontmatter no tiene campo para eso. **Falta**: auditar las plantillas generadas por `make_notes` confirmando que ninguna trae esa columna, como test pineado. **Al día 2026-08-24**: el test pineado que esta fila daba por faltante **existe** — `tests/test_make_notes.py::test_inventario_no_tiene_columna_de_valor_adoptado` fija la cabecera exacta y exige que la ausencia esté *dicha*, no sólo omitida. Sigue cubriendo sólo la ficha de estrella, no el concepto. |
| **INV-12** | Una disputa válida tiene `field`, **≥2 posiciones**, y cada posición dice quién la sostiene. Lo que no cumpla bloquea. | P0 | **garantizado y medido** | Batería completa: sin `field`, 1 posición, posición sin `ref`/`source`, `source` fuera de vocabulario → exit 1, 5 hallazgos para 4 notas (8ª F1 #5). |
| **INV-13** | Un schema que el lector ya no interpreta se **detecta y bloquea**, con la migración a la vista. Nunca se ignora en silencio ni se agrega un lector tolerante. | P0 | **garantizado y medido** | `old_disputes` → exit 1 y el reporte contiene `--migrate-disputes` (8ª F1 #6); ciclo completo vintage→migrado→conteo 0→2ª pasada byte idéntica (8ª F4 G5). |
| **INV-14** | Cada campo de cada schema tiene **una sola** autoridad de escritura declarada, y esa declaración es verificable desde afuera de la implementación. | P1 | garantizado sin medir | La declaración existe en prosa (`README.md` §Quién decide cada cosa) y, para el espejo, en forma máquina (`MIRROR_HOST`/`MIRROR_PLANET` en `lint.py`). **Falta** la matriz: corromper cada campo, correr **todas** las operaciones, y confirmar que sólo la autoridad declarada lo restaura. |

### C. No destruir trabajo (síntesis del modelo y juicio del humano)

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-15** | Toda escritura sobre una nota existente es aditiva o quirúrgica sobre regiones derivadas. Destruir prosa exige una acción explícita distinta de la corrida normal. | P0 | **garantizado y medido** | Marcador de prosa sembrado y verificado tras cada comando: 6 confirmaciones + control de cordura (`--force` sí destruye) — 8ª F4 familia 2. Es la garantía mejor probada del repo junto con el espejo. |
| **INV-16** | El merge de campos compartidos es add-only: agrega lo que falta, no borra ni reordena, y si el elemento ya está no hay diff. | P0 | **garantizado y medido** | El retro-linkeo no quita un `stars:` curado a mano; 2ª corrida byte idéntica (8ª F1 #10). |
| **INV-17** | Toda región reescribible por la capa determinista es identificable por una marca estable, y la reescritura no se sale de ella. | P1 | **garantizado y medido** (con deuda) | Ancla de cabecera: nota con "Capa LLM" preexistente estampada **sin duplicar**, prosa intacta, 2ª pasada byte idéntica (8ª F1 #16); `--force` es la única puerta. **Falta**: texto adversario inmediatamente antes y después del ancla. |
| **INV-18** | Una cirugía que no encuentra su ancla **se reporta**; nunca termina con éxito aparente sin haber hecho nada. | P0 | **garantizado y medido** | `make_notes` imprime `N de M estampadas` y el lint lista las no estampables (`headerless`, sembrada en 8ª F4 §2). Medido en instancia real: 22 de 25 notas sin ancla, hoy exactamente 22/25 (8ª F5). |
| **INV-19** | Después de borrar o renombrar una entidad no queda ninguna referencia colgada **en ninguna capa** ni archivo huérfano en `raw/`. | P0 | **HUECO (parcial)** | Ver §4.HUECO-4. Hay red para `wiki/` (wikilinks rotos, huérfanos: bloqueantes) y para el ground-truth colgado (backlog). **No hay red** para `config/registro/<slug>.yaml`, `raw/fulltext/<slug>/`, `raw/pdfs/<slug>/`, la entrada en `stars.yaml`/`themes.yaml`, ni `build/<slug>/`. Y no existe herramienta: borrar y renombrar son procedimientos manuales del skill `maintain`. |
| **INV-20** | Ningún artefacto de `vault/raw/` ya existente se modifica ni se borra, salvo mejora declarada o borrado explícito de la entidad. | P0 | garantizado sin medir | Evidencia parcial: `fetch_ground_truth` no refresca un snapshot existente (8ª F1 #40, mensaje *"ya existe — no se pisa"*); `extract_fulltext` no re-extrae sin `--force` (8ª F4 G1.9); los fetchers saltean lo bajado. **Falta**: hashear todo `raw/` antes y después de una re-corrida completa. Y `--force` no deja registro de qué pisó. |
| **INV-21** | Una interrupción deja el vault consistente: o el artefacto no existe, o existe completo. No hay notas truncadas ni textos a medias que pasen el umbral. | P0 | **garantizado y medido** | Ver §4.HUECO-2. Los 5 writers atómicos protegen su destino (8ª F4 familia 3, inyección de fallo agnóstica de ruta), y `extract_fulltext` borra el `.txt` a medias (`:204`). Pero **`make_notes` escribe las notas con `write_text` directo en 15 sitios** — sin tmp+rename— mientras `check_retractions` escribe *la misma clase de archivo* atómicamente. **Cerrado por D-53 (1.24.0)**: `make_notes` escribe por `cfg.write_text_atomic` en sus 14 sitios. Instrumentos: `tests/test_lib_config.py::test_write_text_atomic_publica` (inyección de fallo en `os.replace`), `::test_sin_escrituras_directas_a_vault` (guard estático repo-wide) y `tests/test_make_notes.py::test_corte_publicando_no_deja_la_nota_a_medias`. |
| **INV-22** | Correr dos veces la misma operación con la misma config y las mismas fuentes deja el vault byte-idéntico. | P1 | **garantizado y medido** | 10 comandos ×2 con `hash_tree(ROOT)` sobre corpus de 900 notas: `make_notes` (con y sin `ads.json`), `--restamp-headers`, `--restamp-pdf-links`, `--sync-mirror`, `--migrate-disputes`, `triage --migrate`, `lint`, `extract_fulltext`, `bench_verify seed` (8ª F4 familia 1). |
| **INV-23** | El resultado no depende del orden ni de quién corrió último; sólo cambia si llega algo de mejor calidad declarada. | P1 | **INCUMPLIDO (parcial)** | Ver §4.INC-3. Re-correr no repunta y la precedencia por calidad se respeta (`ocr→pdftotext` mejora, `pdftotext→ocr` no degrada), pero el **primer** estampado de `fulltext` depende del orden: `A,B ≠ B,A` byte a byte (8ª F1 #7 / P-01). |
| **INV-24** | El veredicto core/no-core depende sólo de la metadata del paper y de la lente vigente. | P1 | garantizado sin medir | Lectura de código: `classify()`/`exclusion_reason()` (`query_ads.py:194-224`) son función de `(topics, doctype)` contra constantes de módulo leídas de la config; no hay estado de sujeto ni de corrida. **Falta**: clasificar el mismo paper llegando por dos sujetos y en dos momentos, y re-clasificar el corpus entero reproduciendo los veredictos vigentes. |
| **INV-25** | Borrar el scratch y re-correr reconstruye el estado sin pérdida. Corolario: nada no regenerable vive sólo en scratch. | P1 | garantizado sin medir | El caso histórico que lo violaba (`build/<slug>/triage.json`) está cerrado: migrador idempotente + detector **bloqueante** (8ª F1 #13, F4 G1.7). **Falta**: clonar en limpio sin `build/`, correr y diferenciar contra el vault original. |
| **INV-26** | El texto derivado de un documento es reproducible bit a bit, no pasa por ningún modelo, y la nota registra **cómo** se obtuvo. | P1 | garantizado sin medir | `fulltext_source` y `pdf_source` se estampan por verdad de disco (`extract_fulltext.py:250-259`); la idempotencia está medida (8ª F4 G1.9). **Falta** la reproducibilidad byte a byte real: en el sandbox `pdftotext` estaba mockeado. Exige la herramienta instalada. |
| **INV-27** | La clave de una fuente es única en la bóveda, estable entre corridas y validable. Dos fuentes distintas nunca comparten clave. | P1 | **HUECO (parcial)** | Ver §4.HUECO-7. La **forma** está validada (`BIBCODE_RE`, 8ª F1 #25) y la estabilidad se sostiene. **No existe** chequeo de colisión: dos fuentes off-ADS distintas con la misma clave sintética se resuelven por "el archivo ya existe, no lo piso" — sin avisar que la URL es otra. |

### D. Trazabilidad y verificabilidad de las citas

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-28** | Lo declarado legible pasa un umbral **determinista**; lo ilegible se marca y no cuenta como fuente disponible. | P1 | **garantizado y medido** | `is_legible` detecta mojibake (0% legible) y el escaneo cuya única capa es la **marca de agua** del bibcode (~19 chars/página) — 8ª F1 #42; categoría `illegible_txt` sembrada (F4 §2). El umbral concreto es decisión de intención §6.7. |
| **INV-29** | Cada fuente registra de qué documento salió, derivado de evidencia en el propio artefacto. La ausencia de evidencia se escribe **desconocido**, nunca *publicado*. | P0 | **garantizado y medido** | El mecanismo existe y es el correcto: `pdf_source` se lee de la marca que arXiv estampa en el `.txt`, por eso el backfill funciona sobre un corpus ya bajado (`extract_fulltext.py:9-11`). **Falta la prueba crítica**: que un preprint no pueda quedar marcado como publicado. Es un P0 sin ejecutar. **Al día 2026-08-24**: la «prueba crítica» que esta fila daba por no ejecutada **existe** — `tests/test_make_notes.py::test_pdf_source_desconocido_no_afirma_publicado` y `::test_pdf_source_la_marca_gana_sobre_el_registro`, más `::test_pdf_source_detecta_el_eprint_por_la_marca_de_arxiv`. |
| **INV-30** | La captura web es determinista y fechada, y re-capturar no destruye la anterior sin dejar rastro. | P1 | **HUECO (parcial)** | Ver §4.HUECO-9. Fechada y citable sí (`accessed`, snapshot con URL+fecha). Pero `fetch_web --force` **pisa** el snapshot anterior sin versionarlo ni registrarlo: la captura previa desaparece. |
| **INV-31** | El bloque de verificación lleva fecha y existe un chequeo determinista que detecta que la nota se editó **después**. | P0 | **garantizado y medido** | Medido por `git`, no por mtime: commit 2026-08-20 contra bloque 2020-01-01 → `stale=1` con el mensaje correcto (8ª F1 #15); categoría sembrada (F4 §2). |
| **INV-32** | Si la vigencia no se puede computar, el resultado es "no evaluado" **reportado**, nunca "vigente". | P0 | **garantizado y medido** | Ver §4.INC-1. Medido: sin `.git`, `stale=0` y **nada** en el reporte (8ª F1 #15). `CLAUDE.md:593-597` lo documenta como *"degrada a silencio fuera de un repo"* — el sistema hace exactamente lo que este invariante prohíbe, y lo dice. **Cerrado por D-43 (1.24.0)**, las dos puertas: `tests/test_lint.py::test_lint_sin_git_reporta_no_evaluado` y `::test_lint_objective_roto_bloquea`, con `::test_no_evaluado_no_contamina_conteos` como adversario del cero inventado. Ver la deuda de exit anotada en INV-87. |
| **INV-33** | Una fuente retractada citada queda estampada en su nota y el chequeo la surface como **bloqueante**. La detección es por identificador. | P0 | **garantizado y medido** | `retracted` bloquea, incluso con `retraction:` escalar (no crashea) — 8ª F1 #35, F4 §2. Detección vía Crossref por DOI, separada del surfacing offline. El alcance del barrido periódico es decisión §6.9. |
| **INV-34** | Erratas y corrigenda se registran y se surface como **backlog** (no bloquean), con información suficiente para revisar los valores extraídos. | P1 | **garantizado y medido** | `corrections` sembrada: 0→1, exit **0** (8ª F4 §2). |
| **INV-35** | Todo contenido prometido vía consulta dinámica tiene un equivalente determinista que devuelve el **mismo** conjunto, con el **mismo** parser, sin plugins no versionados. | P0 | **garantizado y medido** | Los dos estilos de lista (bloque y flow) devueltos por el one-liner oficial; `GJ 71` no trae `GJ 710` (8ª F1 #3/#4). Verificado además **letra por letra contra el corpus real**: one-liner oficial 193 papers, `grep` legacy 2, `awk` legacy 191 (8ª F5) — los dos modos de falla documentados, reproducidos. |
| **INV-36** | Escritor, chequeador y consumidor documentado leen el frontmatter con el mismo parser. No hay dos lecturas que discrepen. | P0 | **garantizado y medido** | `lib_config.split_fm` es el único parser, y el one-liner que `CLAUDE.md` publica lo usa. Un frontmatter que no parsea **bloquea** en vez de evadir en silencio (8ª F1 #34, `fm_broken`). `frontmatter_span` ubica el delimitador por línea, no por subcadena (cierra el `---` dentro de un escalar). |

### E. El veredicto del chequeo de salud (la compuerta)

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-37** | El código de salida distingue apto de no apto: nunca éxito con bloqueantes, nunca error por higiene. | P0 | **garantizado y medido** | **30/30 categorías** sembradas una por una sobre corpus limpio (n0=0 verificado antes de mutar), con delta exacto y exit code (8ª F4 §2). Y sin falsos positivos: corpus limpio de 300 papers → exit 0 (F1 #37). |
| **INV-38** | Un chequeo que no puede correr por falta de insumo reporta que **no evaluó**. Jamás contribuye un cero al total. | P0 | **garantizado y medido** | Ver §4.INC-1. **Honrado** en tres caminos medidos: sin `build/` cae al registro versionado con su fecha; registro ilegible → backlog explícito en vez de "0 pendientes"; ground-truth ilegible → bloqueante. **Violado** en dos: sin historial de `git`, `stale=0` mudo; con `objective.yaml` ilegible, lente vacía y ni una línea de reporte. **Subsumido por INV-87 y cerrado con él (D-43, 1.24.0)**: la categoría *⛔ No evaluado* cuenta para el exit y suprime la categoría normal. Desde 2026-08-24 cubre también `stars.yaml`/`themes.yaml` ilegibles, que antes mataban al lint con traceback. |
| **INV-39** | Un dato de snapshot se reporta como snapshot, con su fecha, aclarando que no es el conteo vigente. | P0 | **garantizado y medido** | El código lo hace (fallback al `busqueda` del registro con fecha). **Falta**: desincronizar deliberadamente registro y estado vivo y leer el reporte. Barato de sembrar. **Al día 2026-08-24**: `tests/test_lint.py::test_registro_versionado_cubre_la_falta_de_build` exige la fecha literal y la frase «no el conteo vigente», y `::test_build_local_gana_sobre_el_registro` fija la precedencia. |
| **INV-40** | Cada chequeo se aplica a **toda** la población que declara cubrir; una nota no evaluable es hallazgo bloqueante, no una nota saltada. | P0 | **HUECO (parcial)** | Ver §4.HUECO-5. La mitad fuerte está: la nota que evadiría (frontmatter roto, lista escrita como escalar) **bloquea** (8ª F1 #34). La que falta: el reporte **no dice sobre qué población corrió cada dimensión**, así que "la diferencia está íntegramente explicada por hallazgos" no es verificable desde la salida. |
| **INV-41** | Cada clase de hallazgo tiene severidad fija, documentada y coherente con el daño. | P1 | **garantizado y medido** | El invariante mejor evidenciado del repo: mapeo **1:1 en ambas direcciones** entre las 30 categorías del reporte y la prosa de `CLAUDE.md`, con la severidad correcta en los 30 casos (8ª F3(b)), y las 12 bloqueantes del `n_block` coincidiendo exactamente con lo declarado (8ª F4 §2). Ninguna categoría de la prosa nombra algo que ya no exista. |
| **INV-42** | El chequeo no requiere red ni credenciales y no escribe una línea en `vault/`. | P0 | **garantizado y medido** | Corrida ×2 con hash de **todo** `ROOT`: sólo cambia `outputs/`, y el reporte es byte-idéntico (8ª F4 G1.8). La detección que sí necesita red (retracciones) está separada en otro script. |
| **INV-43** | Cada hallazgo nombra su archivo y el reporte es determinista entre corridas sobre el mismo estado. | P1 | **garantizado y medido** | Dos corridas → salida byte-idéntica (8ª F4 G1.8); cada línea del reporte trae el stem/ruta. ⚠ **Corregido el 2026-08-24**: esta fila afirmaba determinismo que no había. `orphans` salía de iterar un `set` de strings (orden dependiente del hash, randomizado por proceso) y el golden **ordenaba las líneas antes de comparar**, o sea que el único no-determinismo medido estaba neutralizado justo en el test que debía verlo. Arreglado en la fuente (`sorted`) + `tests/test_lint.py::test_notas_huerfanas_salen_en_orden_estable`; el golden ya compara orden crudo. |
| **INV-44** | Para cada paso salteable de la cadena existe un chequeo determinista que detecta la omisión. | P0 | **parcial** | Ver §4.HUECO-3. Existen las redes de los pasos *que se olvidan*: triage pendiente (#55), verificación stale (#56), cabecera (#69), extraído-no-sintetizado (#75), corpus truncado (#79/#43). **No existe red para los pasos que se saltean con bandera**: `--yes` (guardia de expansión) y `--no-triage` (compuerta) no dejan traza en el registro ni en la nota. **Mitad cerrada por D-48/D-57 (1.26.0)**: `--no-triage` se eliminó (`tests/test_query_ads.py::test_no_triage_ya_no_existe`) y las escotillas quedan en el registro (`::test_escotillas_quedan_en_el_registro`). **Mitad viva**: `ingest_star`/`ingest_theme` no propagan sus propios flags (`--yes`) a `save_paso`, así que la escotilla del orquestador sigue sin traza. |
| **INV-45** | Una fuente ya extraída que no aparece citada en ninguna síntesis durable se reporta; el único modo de silenciarla es una declaración **con motivo**. | P1 | **garantizado y medido** | Sin campo → 1 hallazgo; `true`/`""`/`null` → 1 con mensaje *"sin motivo"*; motivo string → 0 (8ª F1 #9). Categoría `unsynthesized` sembrada (F4 §2). |
| **INV-46** | Todo campo con vocabulario cerrado se valida contra él y un valor fuera de vocabulario **bloquea**. | P1 | **garantizado y medido** | `role: [fundacionall]` → exit 1 (8ª F1 #8); `source` de disputa fuera de vocabulario → exit 1 (F1 #5). El vocabulario vive en un solo lugar (`lint.py:323`). |
| **INV-47** | Donde el diseño declara lista abierta, se avisa y se crea igual, y la lista **nunca** se infiere de lo que hay en disco. | P1 | **garantizado y medido** | Área no declarada: aviso presente, nota creada, WARN=1, bloqueantes=0, exit 0 (8ª F1 #30). La no-inferencia se sostiene por construcción: la lista sale de `objective.yaml`, no del filesystem. |

### F. El registro: lo que no es regenerable tiene que viajar

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-48** | Los **dos** lados del juicio de curación —aceptado y descartado— persisten en config versionada, cada descarte con motivo y fecha. | P0 | **garantizado y medido** | El descarte sobrevive y se lista con su motivo aun sin `build/` (8ª F1 #43); `--reason` es obligatorio (exit 2 de argparse sin él); el lugar viejo (`build/<slug>/triage.json`) **bloquea** mientras exista (F4 §2). |
| **INV-49** | Una fuente descartada no se descarga, no se convierte en nota y no vuelve a la cola, mientras el descarte esté vigente. Vale para **todos** los carriles. | P0 | **garantizado y medido** (con brecha nombrada) | Ver §4.INC-2. El camino normal lo honra (`query_ads.py:1028`, *"decisión persistida: no re-proponer"*) y el carril off-ADS avisa por clave **y por url** sin frenar (8ª F1 #12). Pero `--no-triage` pone `gate=False` → `descartados = set()` (`query_ads.py:1018-1019`): los descartes persistidos **se resucitan y se bajan**, sin aviso. **Cerrado por D-48 (1.26.0)**: el flag que lo incumplía ya no existe (`tests/test_query_ads.py::test_no_triage_ya_no_existe`, `::test_la_compuerta_no_se_puede_apagar`) y los dos carriles tienen test (`tests/test_ingest_theme.py::test_offads_avisa_si_la_fuente_estaba_descartada`). **Brecha declarada**: en el carril *tema* el gate no aplica (`gate=False` ⇒ `descartados=set()`), así que un descarte de chaining de un tema sí se re-propone — es deliberado y está fijado en `tests/test_query_ads.py::test_main_tema_no_aplica_la_compuerta`, pero contradice el «todos los carriles» del enunciado. |
| **INV-50** | Lo que entra por un camino de baja precisión no se descarga hasta que hay juicio. La compuerta es efectiva, no un aviso. | P0 | **garantizado y medido** | `candidates` es una clave propia de `ads.json` y **todos** los consumidores leen `data["records"]`: `fetch_arxiv:119`, `fetch_pdf:238`, `make_notes:1186` (8ª F1 #11). ⚠ **Actualizado 2026-08-24**: la escotilla `--no-triage` que esta fila describía **se eliminó** en D-48/1.26.0 (`tests/test_query_ads.py::test_no_triage_ya_no_existe` asserta que argparse sale 2), en línea con lo que ya dicen INV-44 e INV-49. Lo que sigue sin test es el lado consumidor: nadie fija que `fetch_pdf`/`fetch_arxiv`/`make_notes` lean sólo `records` y no `candidates`. |
| **INV-51** | Cada corrida de búsqueda cierra registrando consulta efectiva, fecha, límite, conteos del embudo, **la lente vigente con su regla de combinación**, y la versión del framework. | P1 | **garantizado y medido** | Verificado por lectura hoy: `query_ads.py:1080-1103` escribe `fecha, query, rows, n_found, n_total, n_core, n_candidates, n_dropped, truncated, almagesto_version` y `lente: {facets, require, min_topics, noise_doctypes}`. **Falta** la prueba de uso: cambiar un patrón, re-correr, y comprobar que el registro explica la diferencia de corte sin adivinar. **Al día 2026-08-24**: `tests/test_query_ads.py::test_main_persiste_el_registro_de_busqueda` asserta `query`, `n_found`, `n_core`, `n_dropped`, `almagesto_version` y `lente.{facets,require,min_facets}`. Falta la prueba de **uso** (dos lentes que difieren en un patrón ⇒ el registro explica el delta), que es la de INV-55. |
| **INV-52** | Si la búsqueda no trajo todo lo que el servicio reporta, queda marcado y se surface. Nunca implícito que el universo esté completo. | P0 | **garantizado y medido** | `truncated_corpora` sembrada (8ª F4 §2); la marca se persiste con `num_found`/`rows`/`recent` y la 2ª pasada por fecha corre con la misma `q` y `sort=date desc` (8ª F1 #21, con `requests` mockeado). |
| **INV-53** | Escribir un registro nuevo no borra el juicio ya registrado, y la historia es reconstruible. | P1 | **garantizado y medido** | `save_busqueda` preserva `decisiones` (`query_ads.py:1079`); `save_registro` es atómico y **rehúsa escribir** sobre un registro existente que no parsea, con bytes intactos y sin `.tmp` residual (8ª F1 #14, F4 G3.1/G3.2). |
| **INV-54** | Migrar el formato del registro no pierde juicio, resuelve conflictos por regla declarada y es idempotente. Mientras quede juicio en el lugar viejo, bloquea. | P0 | **garantizado y medido** | Ante el mismo bibcode gana lo ya versionado; `triage.json` consumido; 2ª corrida no-op; con la clave `decisiones` ausente **no** borra (exit 1 + mensaje) — 8ª F1 #13, F4 G1.7. |

### G. Configuración: la lente

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-55** | El criterio de relevancia vive enteramente en config versionada. No hay regla de admisión hardcodeada que la contradiga o complemente. | P1 | garantizado sin medir | Verificado por lectura hoy: incluso el filtro de ruido es configurable (`relevance.noise_doctypes` → `NOISE_DOCTYPES`, `query_ads.py:148`), y la regla de combinación es declarativa (`require`/`min_facets`, `:164-191`). **Falta**: dos configs que difieran en un solo patrón produciendo exactamente la diferencia esperada. |
| **INV-56** | Una configuración malformada aborta con error explícito **antes** de tocar el vault. Nunca se degrada a un default silencioso. | P0 | **garantizado y medido** | Ver §4.HUECO-1. Ruidoso donde alguien lo pensó: `require` escalar, faceta obligatoria inexistente, `objective.yaml` **ausente**, slug desconocido (todos con mensaje que nombra el campo). **Silencioso donde más duele**: un `objective.yaml` que no parsea degrada a `{}` (`lib_config.py:185-187`) → lente vacía, y el único chequeo del lint compara `name` contra el placeholder, así que **no dispara nada**. **Cerrado por D-6 (1.24.0)** y completado el 2026-08-24 con los otros dos YAML: `tests/test_lib_config.py::test_objective_error_distingue_los_tres_estados`, `tests/test_query_ads.py::test_query_ads_rehusa_lente_vacia` y `tests/test_lint.py::test_stars_yaml_roto_reporta_no_evaluado_en_vez_de_reventar`. |
| **INV-57** | Mientras la bóveda conserve el objetivo de ejemplo del template, se reporta. | P1 | **garantizado y medido** | WARN=1, exit 0 (8ª F1 #32, F4 §2). |
| **INV-58** | Es posible determinar sin adivinar si el corpus vigente fue clasificado con la lente actual, y qué papers cambiarían de lado. | P1 | **garantizado y medido** | La lente viaja en el registro (INV-51) y `query_ads --dry-run` es el preview offline de re-clasificación: `requests` nunca invocado, árbol byte-idéntico (8ª F1 #27). |
| **INV-59** | El preview muestra el corte sin bajar un archivo ni modificar config o vault. | P0 | **garantizado y medido** | `--dry-run` con `requests` que revienta si se lo llama: exit 0, nunca invocado, árbol byte a byte idéntico (8ª F1 #27). `--probe` es la misma familia (sin hash-test propio). |
| **INV-60** | Un forzado manual de relevancia persiste en config y se re-aplica en cada corrida, con su origen marcado. | P1 | **garantizado y medido** | `extra_core` vive en `stars.yaml`/`themes.yaml` y sobrevive: la instancia real conserva los 121 bibcodes del rescate por glifo con su comentario fechado (8ª F5). **Falta** comprobar que el resultado queda **marcado como manual** y no se confunde con un core clasificado. **Al día 2026-08-24**: `tests/test_query_ads.py::test_fetch_bibcodes_marca_manual` asserta `via == "manual"` y `make_notes.papers_universe` lo publica en la columna *Origen* de la tabla estampada. |
| **INV-61** | Una fuente declarada que no se consigue queda pendiente con su puntero, produce andamiaje mínimo, no cuenta como fallo y se surface como precondición. | P1 | **garantizado y medido** | `ingest_theme` avisa —no frena— por clave **y por url** ya descartada, exit 0 y la fuente se procesa igual (8ª F1 #12); `pending_srcs` sembrada como backlog (F4 §2). |

### H. Provenance, versionado y evolución del schema

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-62** | Cada nota declara con qué versión se generó, desde una única fuente de verdad, y una cirugía posterior no la reetiqueta. | P1 | **garantizado y medido** | `generator == ALMAGESTO_VERSION` (8ª F1 #1); `--restamp-headers` **lee** la versión del `generator` del frontmatter: `v1.11.0 → v1.11.0`, `v1.12.3 → v1.12.3`, sin `generator` → `vdesconocida` con el ancla (8ª F1 #16). |
| **INV-63** | Para cada tipo de nota hay un schema explícito y toda nota generada lo cumple; ningún campo se escribe con una forma que el chequeo no pueda recorrer. | P0 | **HUECO (parcial)** | Ver §4.HUECO-6. La mitad de "forma que evade" está cubierta y bloquea (`fm_broken`: YAML inválido, lista escrita como escalar, elementos que no son mapas). **No existe validador de campos requeridos por tipo de nota**: el schema vive en la prosa de `CLAUDE.md` y en chequeos ad-hoc campo por campo. |
| **INV-64** | Un cambio de schema entrega **dos** piezas: migración idempotente y detector bloqueante de la forma vieja. Nunca un lector que acepte ambas. | P0 | **garantizado y medido** | Ciclo completo medido: vintage 1.11.0 → 4 migradores → los 4 conteos del lint a **exactamente 0** → 2ª pasada byte-idéntica (8ª F4 G5.1-G5.3). Y el detector bloquea, no tolera (F1 #6, #13). |
| **INV-65** | Lo regenerable vive fuera del árbol de la bóveda y fuera del versionado. | P2 | **garantizado y medido** | `git status --porcelain` vacío antes y después de todas las familias (8ª F4); `.obsidian/` en la raíz da WARN (F1 #33); `build/`/`outputs/` gitignored. |
| **INV-66** | Ninguna ruta absoluta de la máquina llega a un archivo versionado; los punteros internos son relativos al repo. | P1 | garantizado sin medir | Medido del lado del código: 0 hits de `/home`/`/Users` en `scripts/`, y `cfg.ROOT` correcto ejecutando desde `/tmp` (8ª F1 #20). **Falta** el lado de los **artefactos**: grep de prefijos absolutos en `wiki/`, `config/registro/` y `themes.yaml` (salvo los campos declarados machine-local, `data_local`). |
| **INV-67** | La credencial no se escribe en ningún artefacto versionado, ni en notas, ni en registros, ni en la salida de ninguna corrida (mensajes de error incluidos). | P0 | garantizado sin medir | La mitad medida: `.gitignore:3` y **historial vacío en todas las ramas** (8ª F1 #17). **Falta la otra mitad**: setear un token reconocible, correr todo incluidos los caminos de error (credencial inválida, servicio caído), y buscar la cadena en el árbol y en toda la salida capturada. Es un P0 a medio medir. |
| **INV-68** | Ninguna corrida modifica archivos de framework en una instancia. | P2 | **garantizado y medido** | Clon efímero + merge sintético: los 7 archivos de instancia listados en `.gitattributes` quedan intactos y `CLAUDE.md` sí avanza (8ª F1 #19). Con la condición que la propia doc pone: **sin** `merge.ours.driver` configurado hay conflicto (no pisa, pero tampoco mergea). |

### I. Robustez frente al mundo exterior

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-69** | Un servicio caído, lento, con error, vacío o inesperado nunca produce metadata inventada, texto vacío válido, ni un registro que declare un universo que no se consultó. | P0 | **parcial** | Mecanismos presentes y leídos: `EmptyResultError` aborta la cadena en vez de persistir un `ads.json` vacío con exit 0 (`query_ads.py:389,457,1111`); `requests.RequestException` atrapada en el barrido (`:935`); escritura atómica de PDFs con `except OSError` (8ª F4 G3.5/G3.6). **Falta** la matriz de inyección: timeout, 500, respuesta vacía, respuesta con campos faltantes, respuesta truncada — y auditar qué quedó escrito en cada caso. La deuda P0 más grande del contrato. **Muy avanzado respecto de lo que dice esta fila**: hay inyección de fallo por script para 429/retry, 5xx persistente, 403/404, `ConnectionError`, cero espurio, `numFound > rows` y PDF truncado (`tests/test_query_ads.py::test_query_ads_5xx_persistente_lanza`, `tests/test_fetch_ground_truth.py::test_nea_host_error_no_se_escribe_como_campo_muerto`, `tests/test_fetch_pdf.py::test_fetch_pdf_no_deja_pdf_truncado_en_el_destino`). **Falta**: la matriz sistemática (hoy son casos sueltos), el timeout, y auditar el disco tras el aborto. |
| **INV-70** | Si falta una herramienta externa necesaria se reporta explícitamente; nunca se produce un artefacto degradado que pase por "existe". | P1 | garantizado sin medir | Verificado por lectura hoy: `extract_fulltext.py:160-162` aborta con `RuntimeError` nombrando el paquete si falta `pdftotext`; el OCR es opt-in por instalación (`shutil.which` de tesseract+pdftoppm). **Falta** correrlo de verdad sin la herramienta. |
| **INV-71** | Metadata, resúmenes y contenido web nunca se interpretan como directivas ni se propagan sin escapar a lugares donde cambien de significado (YAML, nombres de archivo, rutas). | P1 | garantizado sin medir | El frontmatter se serializa con `yaml.safe_dump` (`make_notes.py:72`) y las rutas con `safe_name`/`quote`; el caso `---` dentro de un escalar ya está cerrado (`frontmatter_span`). **Falta** el corpus adversario: títulos con dos puntos, comillas, saltos de línea, `../`, caracteres de control, texto que imita YAML. |
| **INV-72** | La resolución de identidades es determinista, documentada, no aumenta falsos positivos entre entidades con prefijo compartido, y su comportamiento está registrado con evidencia. | P1 | **garantizado y medido** | `GJ 71` no arrastra `GJ 710` con el parser oficial, y el `grep` textual sí (8ª F1 #3/#4, reproducido sobre el corpus real en F5). La expansión de espaciado y los lookalikes de letra griega están documentados con su evidencia fechada en `stars.yaml` (121 core recuperados, 2026-08-09). ⚠ **Corregido el 2026-08-24**: el contraejemplo del enunciado estaba **vivo** — `subject_in_title("A close encounter with GJ 710", ["GJ 71"])` devolvía `True` por containment pelado, y como es la auto-aceptación de nivel 0 metía el paper al corpus ajeno sin juicio humano. La evidencia que citaba esta fila era sobre `split_fm`, **otro camino**. Cerrado con frontera de dígito + `tests/test_query_ads.py::test_subject_in_title_no_matchea_por_prefijo_de_catalogo`. |

### J. Medición del propio error

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-73** | El material sintético del auto-benchmark nunca llega a `vault/`, ni transitoriamente ni si la corrida se interrumpe. | P0 | **garantizado y medido** | Hash de `vault/` intacto; único artefacto `build/verify_bench/bench.json` (8ª F1 #26). **Falta** el caso interrumpido a la mitad. |
| **INV-74** | Dada la misma semilla y el mismo corpus la siembra es idéntica; y quién juzga no tiene acceso a qué caso es falso. | P1 | **HUECO (parcial)** | Ver §4.HUECO-8. El determinismo está medido (`bench.json` byte-idéntico, 10.981 B — 8ª F1 #26, F4 G1.10) y el orden se mezcla con un hash del contenido para que no telegrafíe la etiqueta. Pero **la clave de respuestas vive en el mismo archivo que el examen** (`label: real|sembrada`, ids con prefijo `r`/`s`): la ceguera la sostiene una instrucción del skill, no la construcción. |
| **INV-75** | El resultado de la medición se reporta atado a su condición (corpus, modelo, fecha, tamaño de muestra), nunca como cifra absoluta del framework. | P2 | garantizado sin medir | El `README.md` lo dice explícitamente (*"el número que da es el de **tu** bóveda"*). **Falta** confirmar que la salida de `bench_verify score` lo lleva encima, no sólo la doc. |

---

### K. Invariantes de la revisión con el usuario (2026-08-23)

> Nacen de la revisión de §6 hecha **con el usuario** (`docs/revision-contrato-2026-08-23.md`, 57
> decisiones). Nacieron todos en **HUECO**: eran decisiones de diseño tomadas, sin mecanismo.
>
> **Estado al 2026-08-24** (tras las tandas 0–6, v1.24.0 → v1.30.0, y la auditoría que las midió):
> **10 garantizados y medidos · 4 parciales · 2 HUECO**. Los dos que siguen en HUECO —INV-86 e
> INV-88— lo están **legítimamente**: son las tandas 8 y 7 del plan, todavía no empezadas. Cada
> fila parcial nombra qué mitad falta, que es la única forma de que "parcial" signifique algo.
>
> El estado se midió con **dos pasadas ciegas e independientes** cruzadas después (el método de §7,
> "su valor está en la ceguera"): acordaron en 13 de 16 y las tres discrepancias se adjudicaron
> corriendo el código. Dos de ellas destaparon defectos vivos —el falso positivo permanente de
> INV-91 y el traceback de INV-80— que una sola pasada había dado por cerrados.

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-76** | Cada campo del espejo tiene **una sola** autoridad (`spectral_type` ← SIMBAD, el resto ← NEA). Si esa autoridad calla, el campo es `null` aunque la otra tenga el dato. | P0 | **garantizado y medido** | `tests/test_fetch_ground_truth.py::test_spectral_type_solo_de_simbad` (NEA trae `st_spectype`, SIMBAD calla ⇒ el campo queda `null`), `::test_autoridad_registrada_en_el_json` y `tests/test_make_notes.py::test_cabecera_declara_la_procedencia_del_ground_truth`. La autoridad se declara en `lib_config.AUTORIDAD_CAMPO` y la aplica `fetch_ground_truth.fetch_host`. Los dos casos degenerados (sólo SIMBAD / ninguna) quedan por construcción: `out` nace con todos los campos en `None`. |
| **INV-77** | Una discrepancia entre autoridades es expresable: `{source: nea}` / `{source: simbad}`, y el **silencio** de la autoridad declarada es una posición válida (`value: null`). | P1 | **garantizado y medido** | `tests/test_lint.py::test_disputa_entre_autoridades_es_expresable` (nea↔simbad pasa) y `::test_source_inventado_sigue_bloqueando`, contra `lint.DISPUTE_SOURCES = ("ground_truth", "nea", "simbad")`. Sin test propio: una posición con `value: null` — hoy pasa porque el lint no valida `value`. |
| **INV-78** | Cada par verificado lleva **dos hashes** —el del bloque markdown que contiene la cita, y el del `.txt` leído— y un par cuyo hash no coincide se reporta como no verificado. | P0 | **garantizado y medido** | Los cuatro experimentos, en `tests/test_lint.py`: `::test_edicion_marca_solo_sus_pares`, `::test_reflow_no_marca_nada`, `::test_reemplazo_del_txt_marca_por_fuente`, `::test_fila_huerfana_se_marca`; más `tests/test_lib_blocks.py` (24 casos sobre `block_anchor`/`source_hash`). Verificado por **mutación**: con `block_anchor` constante caen 5 tests —los 4 de `test_lib_blocks.py` más `::test_edicion_marca_solo_sus_pares`—. No leerlo al revés: de los cuatro nombrados acá, esa mutación mata **uno**; `::test_reflow_no_marca_nada` pasa bajo ella *porque* con ancla constante nunca se marca nada, así que su falsabilidad la da otra mutación (cambiar un número del bloque). |
| **INV-79** | Una nota con citas sin verificar, o con pares cuya ancla no coincide, **no cierra** la operación que la tocó. En la pasada periódica, reporta. | P0 | **garantizado y medido** (mitad determinista) | `tests/test_lint.py::test_cierre_bloquea_periodica_reporta` mide las dos severidades del mismo detector y `::test_nota_verificada_no_marca_nada` el control de D-5. La otra mitad —que la operación *no cierre*— depende de que el skill corra `python scripts/lint.py --cierre`: está en los `SKILL.md` de cierre y **no es testeable como código**. Sí sería testeable que los skills lo invoquen (grep sobre `.claude/skills/`); hoy no lo está. |
| **INV-80** | Una config que no parsea **rehúsa** operar: el lint la reporta como bloqueante y el clasificador no corre con lente vacía. | P0 | **garantizado y medido** | `tests/test_lib_config.py::test_objective_error_distingue_los_tres_estados`, `tests/test_lint.py::test_lint_objective_roto_bloquea` y `tests/test_query_ads.py::test_query_ads_rehusa_lente_vacia` (grabador: `classify` no llega a correr). La batería cubre los **tres** YAML de config: `tests/test_lint.py::test_stars_yaml_roto_reporta_no_evaluado_en_vez_de_reventar` y `::test_themes_yaml_roto_tambien_reporta_no_evaluado` — antes `load_stars` propagaba el `ScannerError` y el lint moría con traceback. |
| **INV-81** | La ficha declara, **materializado y por paper**, su universo: origen (`lente`/`manual`), si se extrajo y si se sintetizó. Ningún contenido que el contrato promete depende de un plugin. | P0 | **parcial** | La 1ª oración está medida: `tests/test_make_notes.py::test_conteo_del_encabezado_es_el_de_la_tabla` (adversario del «155 arriba de una síntesis de 8»), `::test_tabla_refleja_los_cuatro_estados`, `::test_la_tabla_estampada_no_se_cuenta_a_si_misma`. **La 2ª no**: sólo `## Papers` se materializó — `## Planetas` sigue emitiendo ```dataviewjs``` y `## Métodos aplicados a esta estrella` ```dataview``` (`make_notes.write_star_note`), sin test ni chequeo que lo prohíba. |
| **INV-82** | Las tres fechas de una nota (búsqueda, síntesis, verificación) son distinguibles y pueden divergir sin que ninguna mienta. | P1 | **parcial** | `tests/test_make_notes.py::test_refrescar_sin_reverificar_mueve_una_sola_fecha` mide que búsqueda y verificación divergen sin mentir. **Son dos fechas, no tres**: `make_notes.estado_line` no emite ninguna de **síntesis**. Hay que implementarla o bajar el enunciado (y `CLAUDE.md`, que dice «las tres» y enumera dos). |
| **INV-83** | El ingest lee **todos** los core; lo que no se lea queda **declarado** con su motivo y visible en la lista de papers. | P0 | **parcial** | `tests/test_lint.py::test_subconjunto_sin_declarar_reporta` / `::test_subconjunto_declarado_baja_a_backlog` miden el detector sobre `lib_config.save_extraccion`. Tres huecos: (a) **nadie llama `save_extraccion`** —ningún script ni skill—, así que el canal de declaración no está cableado; (b) el criterio vive sólo en `registro/<slug>.yaml` y **la ficha no lo dice**; (c) el hallazgo es backlog, fuera de `n_block`, así que «sin declarar ⇒ no cierra» todavía no rige. |
| **INV-84** | La identidad de un paper es `doi`/`arxiv_id`. Un trabajo tiene **una sola** nota canónica; las demás versiones viven en `versions[]`. | P0 | **garantizado y medido** | `tests/test_make_notes.py::test_ciclo_preprint_publicado` (renombre + `versions[]` + reescritura de wikilinks + artefactos) y `::test_crear_segunda_nota_mismo_trabajo_rehusa`; el bloqueo lo miden `tests/test_lint.py::test_dos_notas_mismo_arxiv_id_bloquean`, `::test_identidad_por_doi_tambien` y `::test_versions_no_cuenta_como_duplicado`. |
| **INV-85** | Una sola pasada de red cubre todo lo que cambia afuera (retracción, corrección, versión nueva, snapshot web, ground-truth) y **avisa con el diff antes de aplicar**. | P1 | **parcial** (4 de 5 detectores) | `scripts/sweep_external.py` unifica retracciones, correcciones, versiones y ground-truth; el «avisa con el diff antes de aplicar» lo mide `tests/test_fetch_ground_truth.py::test_nea_diff_reporta_y_no_aplica` (JSON byte-idéntico). **Falta el quinto**: `sweep_web` levanta `NotImplementedError` (falta `fetch_web.refresh`), y `tests/test_sweep_external.py::test_detector_no_implementado_no_aporta_un_cero` mide que eso se declare *no evaluado*, no entre en `cubrio` y la pasada salga 2. Pendiente además cablearlo al skill `maintain`, que sigue corriendo `check_retractions.py` solo. |
| **INV-86** | Toda `inferencia` **nombra sus premisas** (≥1 bibcode). Sin premisas no es inferencia: es afirmación sin respaldo y no entra. | P0 | **HUECO** (D-42) | Sin cambio: `lint.PROT_CITE` sigue aceptando la palabra `inferencia` **pelada** como respaldo, así que una afirmación `no-soportada` sobrevive cambiándole la etiqueta. Test a escribir: `(inferencia)` pelada bloquea; `(inferencia de [[bib]])` pasa; «la inferencia bayesiana…» en prosa no dispara. Es el issue 8.3 del plan. |
| **INV-87** | Un chequeo que no puede correr **reporta error**: nunca contribuye un cero al total. | P0 | **garantizado y medido** | `tests/test_lint.py::test_no_evaluado_no_contamina_conteos` (la categoría normal se **suprime** en vez de mostrar su `(0)` — el adversario del cero inventado) y `::test_lint_objective_roto_bloquea`; mismo contrato de rc 2 en `tests/test_check_retractions.py::test_errores_sin_retractados_exit_2` y `tests/test_sweep_external.py::test_detector_no_implementado_no_aporta_un_cero`. Sacar `not_evaluated` del exit **mata** `tests/test_lint.py::test_stale_sin_git_no_rompe`, que es el test que fija esa rama; `::test_lint_sin_git_reporta_no_evaluado` **sobrevive** a esa mutación porque su `rc != 0` lo sostiene otra categoría, así que mide el reporte y no el exit. La propiedad está medida — por el primero, no por el segundo. |
| **INV-88** | La relevancia de un tema de método es **propia del tema** y entra por tres puertas declaradas (lo cita el corpus / fundacional / lente astro). | P1 | **HUECO** (D-25, D-26, D-27) | Sin cambio, y sigue vigente la evidencia: la lente global mata al fundacional (`require: [rv]` vs Hyvärinen). Es la **Tanda 7** del plan. Medido de paso (2026-08-24) para el issue 7.2: sobre el corpus real, ADS cubre referencias del 80% y OpenAlex del 68% —pero en pre-2000 es 65% vs 16%, y de los papers off-ADS 14 sólo los tiene OpenAlex y 3 sólo ADS—, así que el índice consulta **las dos** y declara su techo (83%). |
| **INV-89** | Un tema y una estrella acumulan **búsquedas**; el embudo no se suma y cada entrada distingue nuevos de ya existentes. | P1 | **garantizado y medido** | `tests/test_lib_config.py::test_dos_busquedas_con_solapamiento_no_suman` (A={1,2,3}, B={2,3,4} ⇒ universo 4, no 6, con `n_nuevos`/`n_ya_estaban`), `::test_universo_acumulado_sin_bibcodes_cae_al_maximo` y `tests/test_make_notes.py::test_estado_line_se_actualiza_y_no_duplica` (la cabecera dice 120, no 220). Verificado por **mutación**: volver a sumar rompe 3 tests. |
| **INV-90** | Toda escritura en `vault/` es **atómica**. | P1 | **garantizado y medido** | `tests/test_lib_config.py::test_write_text_atomic_publica` (inyección de fallo sobre `os.replace`), `::test_sin_escrituras_directas_a_vault` (barrido estático, auditado por mutación sobre los 14 sitios) y `tests/test_make_notes.py::test_notas_pasan_por_el_helper` + `::test_corte_publicando_no_deja_la_nota_a_medias`. Residuo: la lista de módulos vigilados por el guard estático es explícita —un script nuevo hay que agregarlo a mano, y `sweep_external.py` todavía no está. |
| **INV-91** | La cadena deja **traza estructurada** de qué pasos corrieron, con fecha y versión. | P1 | **garantizado y medido** | `tests/test_lib_config.py::test_save_paso_appendea_con_fecha_version_y_via` y `::test_save_paso_idempotente_el_mismo_dia`; que el lint nombre el paso lo mide `tests/test_lint.py::test_cadena_cortada_nombra_el_paso`. La auditoría del 2026-08-24 encontró que `check_retractions` —último paso de `CADENA_ESTRELLA`— no se estampaba, así que **toda** estrella completa se reportaba como cortada; cerrado con `tests/test_check_retractions.py::test_slug_estampa_su_paso_en_la_cadena`, que estampa los seis pasos previos y corre `check_retractions.main` de verdad: lo que importa es que el paso **bajo prueba** no se estampe a mano, que era el defecto del test viejo. |

## 4. Los hallazgos del cruce, ordenados por daño

### 4.1 INCUMPLIDOS (el sistema no cumple algo que debería)

#### INC-1 — La compuerta puede dar limpio sin haber mirado (INV-32, INV-38) · P0

Dos caminos medidos en los que un chequeo que **no pudo correr** contribuye un cero al total en vez
de decir que no evaluó:

1. **Sin historial de `git`, la verificación stale desaparece.** Medido: sin `.git`, `stale=0`, sin
   crash y sin una línea de reporte (8ª F1 #15). `CLAUDE.md:593-597` lo documenta como *"degrada a
   silencio fuera de un repo"* — o sea que es una decisión consciente, no un descuido. Pero es la
   negación exacta del principio rector *no dar falso limpio*, aplicado justamente a la garantía que
   certifica que las afirmaciones pasaron por el fan-out. Un clon sin historial, un tarball, un
   worktree exportado: en todos, la bóveda se lee como verificada al día.
2. **Un `objective.yaml` que no parsea deja la lente vacía, en silencio.** `load_objective` degrada a
   `{}` a propósito (`lib_config.py:172-186`, con el argumento correcto: el lint es la compuerta de
   CI y *"ante una bóveda rara reporta, no se muere"*). El problema es que **no reporta**: el único
   chequeo del objetivo compara `name` contra el placeholder (`lint.py:954`), y con `{}` el `name` no
   es el placeholder, es `None`. Sale WARN=0.

**Arreglo mínimo (no aplicado, es decisión de diseño):** que la degradación deje de ser muda. Un
chequeo *"no evaluado: falta historial de git"* y otro *"no evaluado: objective.yaml no parsea"*,
ambos con la severidad que el usuario decida (§6.4, §6.5). Cuesta dos líneas cada uno; lo caro fue
verlo.

#### INC-2 — `--no-triage` resucita descartes ya juzgados (INV-49, INV-50) · P0

`query_ads.py:1018-1019`:

```python
gate = bool(star_names) and not args.no_triage
descartados = load_triage(args.slug) if gate else set()
```

Con `--no-triage` el conjunto de descartados queda **vacío**, así que los candidatos que alguien
juzgó y descartó —con motivo y fecha, versionados en `config/registro/<slug>.yaml`, que es la parte
cara y no regenerable de un ingest— vuelven a entrar **como core**, se bajan y se convierten en nota.
Sin aviso de que se está pisando un juicio persistido.

Es doblemente delicado porque el flag **no está documentado en ningún skill ni doc** (8ª F3, S2/S3):
apaga la compuerta que `ingest-star` describe como el paso de más juicio del ingest (18% de precisión
sin ella, medido sobre AU Mic). Un flag que desactiva una protección y no figura en ningún lado es
exactamente el que se usa sin saber qué hace.

**Alcance honesto:** es una escotilla explícita, y un opt-out declarado no es lo mismo que un bug
silencioso. Lo que lo hace incumplimiento es que INV-49 dice *"mientras el descarte esté vigente"*,
sin excepción de bandera, y que el override no deja rastro.

#### INC-3 — El primer estampado de `fulltext` depende del orden (INV-23) · P1

Medido (8ª F1 #7 / P-01): para un paper que vive bajo varios slugs, correr `A,B` y `B,A` da un
`fulltext:` distinto (mismo contenido, distinto slug). Todo lo demás que `CLAUDE.md:220-223` promete
**sí** se cumple: re-correr no repunta al slug que corrió último, y la precedencia por calidad se
respeta en las dos direcciones (`ocr→pdftotext` mejora, `pdftotext→ocr` no degrada). El docstring del
código lo declara (*"en empate gana el primer escritor"*); la frase *"idempotente, sin ruido de
diff"* de `CLAUDE.md` se lee como más fuerte de lo que el código garantiza.

**Daño real:** bajo. No pierde información ni miente sobre el contenido; produce un diff distinto
según el orden de ingesta, que es ruido, no engaño. Se cierra desempatando por una regla declarada
(p. ej. orden lexicográfico del slug) o bajando la promesa de `CLAUDE.md` a lo que el código hace.

---

### 4.2 HUECOS (garantías que deberían existir y nadie sabía que faltaban)

> Ordenados por daño. Los cinco primeros son P0.

#### HUECO-1 — Config ilegible = lente vacía, sin una línea de reporte (INV-56) · P0

**Qué falta.** No hay chequeo de que la configuración que define **qué es core** sea legible.

**Por qué es el peor.** La lente es la definición operativa de todo lo que la bóveda afirma: decide
qué papers entran, y por lo tanto sobre qué universo habla cada ficha. Un `:` sin comillas dentro de
una regex —el error más probable de toda la config, y el propio docstring de `load_objective` lo
dice— convierte la lente en `{}`. A partir de ahí el clasificador sigue corriendo con una regla que
nadie escribió, el registro guarda esa lente vacía como si fuera la vigente, y el lint no dice nada
porque su único chequeo del objetivo pregunta por el placeholder.

**Lo que sí está** (y por eso el hueco es parcial): la validación *semántica* es ruidosa y buena —
`require` escalar, faceta obligatoria inexistente, `objective.yaml` ausente y slug desconocido
abortan con mensaje que nombra el campo. Lo que falta es el escalón de abajo: **el archivo parsea o
no**.

**Cómo se cerraría.** Una categoría de lint *"objective.yaml no parsea → la lente está vacía"* y/o
que `query_ads` rehúse clasificar con lente vacía. Test: batería de configs rotas, cada una debe
producir el hallazgo, y el hash del vault antes/después debe ser idéntico.

#### HUECO-2 — Las notas se escriben sin atomicidad; la misma clase de archivo tiene dos disciplinas (INV-21) · P0

**Qué falta.** `make_notes.py` escribe las notas de `vault/wiki/` con `write_text` directo sobre el
destino, en **15 sitios** (`:210, 278, 418, 561, 638, 729, 960, 967, 989, 1096, 1170, 1261, 1293,
1410`). No hay tmp+rename. Un corte durante la escritura —disco lleno, permisos, Ctrl-C en el
milisegundo equivocado— deja la nota **truncada**.

**Por qué duele.** La nota es el artefacto que contiene la prosa del modelo: el trabajo más caro y el
único genuinamente no regenerable de la bóveda (el `ads.json` se vuelve a pedir; la síntesis no).
El principio *no destruir* existe para protegerla, y toda la familia 2 de la 8ª pasada se dedicó a
demostrar que ninguna operación la pisa **lógicamente** — pero nadie miró el modo de falla
**físico**. Y los migradores son barridos masivos: `--restamp-headers` sobre una bóveda real toca 22
notas de una sentada, `--sync-mirror` y `--migrate-disputes` recorren todas las fichas.

**Lo que hace que el hueco sea nítido, y no una queja teórica:** el patrón atómico **ya existe en el
repo, aplicado a las mismas notas, por otro script**. `check_retractions._write_atomic`
(`:95-120`) escribe una nota de paper con tmp+rename y `except BaseException`, y fue confirmado sin
residuo bajo inyección de fallo (8ª F4 G3.4). Cinco writers del repo son atómicos
(`save_registro`, `write_ground_truth`, `check_retractions`, `fetch_pdf`, `fetch_arxiv`); el que más
escribe, y sobre lo más valioso, no.

**Deuda hermana ya medida (S3, no bloquea):** `save_registro` y `write_ground_truth` llaman
`tmp.write_text(...)` **fuera** del `try`, así que un fallo durante la escritura del temporal deja un
`<archivo>.tmp<pid>` huérfano (8ª F4 H-F4-1). El destino nunca se corrompe — eso está confirmado en
los cinco writers— pero la limpieza no es pareja.

**Cómo se cerraría.** Un único helper de escritura atómica en `lib_config` y que **todo** escritor de
`vault/` lo use. Test: inyección de fallo agnóstica de ruta (el harness de F4 ya existe) sobre cada
comando de `make_notes`, verificando destino intacto y cero residuo.

#### HUECO-3 — Los pasos que se saltean *con bandera* no tienen red (INV-44) · P0

**Qué falta.** `CLAUDE.md` declara un principio explícito: *"todo paso salteable de la cadena tiene
red"*, y lo cumple para los pasos que se saltean **por olvido** — triage pendiente (#55),
verificación stale (#56), cabecera (#69), extraído-no-sintetizado (#75), corpus truncado (#79/#43).
Cada uno tiene su categoría de lint.

Pero los pasos que se saltean **a propósito, con un flag**, no dejan traza en ningún artefacto que
viaje:

- **`--yes`** salta la guardia de expansión — el checkpoint humano que frena la cadena cuando el pool
  se multiplica (×1.5 y 50 o más nuevos). Nada en el registro dice que ese día alguien decidió seguir
  de largo.
- **`--no-triage`** apaga la compuerta entera (ver INC-2). El `busqueda` del registro guardará
  `n_candidates: 0` — indistinguible de "no había candidatos".
- **`--force`** en cualquier fetcher pisa un artefacto de `raw/` sin registrar qué pisó (ver INV-20).

**Por qué importa.** El registro existe para responder *"sobre qué universo afirma esta ficha, y con
qué lente se filtró"*. Una corrida con `--no-triage` afirma sobre un universo distinto —con el ruido
del grafo adentro y los descartes resucitados— y el registro la describe igual que a una corrida
compuerta-adentro. Un consumidor no puede distinguirlas.

**Cómo se cerraría.** Un campo `overrides: [--yes, --no-triage, ...]` en el `busqueda` del registro,
escrito por la misma corrida que ya escribe `lente`. Es la mitad barata; la otra mitad es documentar
los flags (9 sin documentar según 8ª F3, `--no-triage` el más delicado).

#### HUECO-4 — Borrar y renombrar no tienen ni herramienta ni chequeo fuera de `wiki/` (INV-19) · P0

**Qué falta.** No existe script de borrado ni de renombrado: ambos son procedimientos manuales del
skill `maintain` (el modelo corre `rm`/`mv` y actualiza referencias a mano). Eso es defendible como
diseño — son operaciones raras y de juicio. Lo que no es defendible es que **el chequeo posterior
sólo cubra una capa**.

Cubierto hoy: wikilinks rotos y notas huérfanas (bloqueantes), y `raw/ground_truth/<slug>.json` sin
su ficha (backlog, agregado en 1.22.1 — y su ausencia en `CLAUDE.md` fue uno de los hallazgos de la
8ª pasada, ya corregido).

**Sin cubrir:** `config/registro/<slug>.yaml` de una entidad borrada; `raw/fulltext/<slug>/` y
`raw/pdfs/<slug>/` colgados; la entrada sobreviviente en `stars.yaml`/`themes.yaml`; `build/<slug>/`.
Ninguno se reporta. Un renombrado a medias deja la mitad de los artefactos bajo el slug viejo y el
lint sale en 0.

**Nota de honestidad:** el caso simétrico que **sí** está cubierto (ground-truth sin ficha) se agregó
porque alguien lo pisó de verdad — la instancia real lo tiene hoy (`ds_tuc.json` sin `stars/ds_tuc.md`,
8ª F5). Es evidencia de que el modo de falla es real y de que la cobertura se construyó por
accidente, un hermano por vez, en vez de por barrido.

**Cómo se cerraría.** Un chequeo simétrico *"artefacto de `<capa>` sin su entidad"* para las cinco
capas, derivado de una sola lista de capas. Y, si se quiere cerrar del todo, un `maintain --borrar
<slug>` determinista.

#### HUECO-5 — El chequeo no dice sobre qué población corrió (INV-40) · P0

**Qué falta.** El reporte del lint dice cuántos **hallazgos** hay por categoría. No dice cuántas
**notas evaluó** cada dimensión. Así que la propiedad que hace que un "0" signifique algo —*cada
chequeo se aplicó a toda la población que declara cubrir*— no es verificable desde la salida.

La mitad fuerte sí está: una nota que evadiría los chequeos por elemento (frontmatter no parseable,
lista escrita como escalar) **bloquea** en vez de saltarse en silencio, y eso está medido (8ª F1 #34).
Lo que falta es la instrumentación: `evaluadas + reportadas = total`, por dimensión, sin resto.

**Por qué importa más de lo que parece.** Este es el mismo modo de falla que el repo ya persiguió tres
veces con nombre propio: el falso limpio de #64 (sin `build/`, "0 pendientes"), el de #h05 (registro
ilegible saltado mudo) y el de INC-1 (sin git, `stale=0`). Cada vez se cerró **un** camino. La
instrumentación de cobertura los cerraría como clase.

#### HUECO-6 — No hay validador de schema por tipo de nota (INV-63) · P1

**Qué falta.** El schema de `stars/`, `papers/` y `concepts/` vive en la prosa de `CLAUDE.md` y en
chequeos ad-hoc campo por campo dentro del lint. No hay una validación de **campos requeridos por
tipo**: una nota de paper sin `bibcode` o sin `year`, una ficha sin `slug`, un concepto sin `aliases`
no producen hallazgo propio.

Está parcialmente compensado: el espejo detecta la mayoría de los problemas de `stars/` por otra vía
(si falta `planets`, el ground-truth reclama cada planeta que la ficha no lista), y `fm_broken` cubre
las formas inválidas. Es un hueco de **completitud**, no de mentira.

**Cómo se cerraría.** Declarar los tres schemas como datos (un dict por tipo de nota, campos
requeridos + tipo esperado) y validar todas las notas contra eso; el mismo dict sirve de fuente única
para `make_notes` y para el lint, que es lo que INV-14 pide.

#### HUECO-7 — Ninguna verificación de colisión de claves de cita (INV-27) · P1

**Qué falta.** La **forma** de la clave está validada (`BIBCODE_RE = ^\d{4}[A-Za-z]`, medido en 8ª F1
#25) y la estabilidad se sostiene. Lo que no existe es un chequeo de **unicidad semántica**: dos
fuentes off-ADS distintas declaradas con la misma clave sintética `AAAA+Autor` —perfectamente
posible: dos papers del mismo año y autor— se resuelven por *"el archivo ya existe, no lo piso"*
(`fetch_web.py:119-123`). El resultado es una nota que dice una cosa y un `.txt` que es de otro
documento, sin ningún aviso de que la URL no coincide.

**Por qué es menos grave de lo que suena:** falla del lado seguro (no sobreescribe), y `--force` es
explícito. Pero el estado resultante es exactamente el que la regla #0 prohíbe: una afirmación con un
`[[bibcode]]` que no la respalda.

**Cómo se cerraría.** Que `fetch_web`/`make_notes --web` comparen la `source_url` de la nota existente
con la que se está declarando y fallen ruidosamente si difieren.

#### HUECO-8 — La clave de respuestas del benchmark vive junto al examen (INV-74) · P1

**Qué falta.** `bench_verify.py seed` escribe un solo archivo, `build/verify_bench/bench.json`, que
contiene los pares **y** su etiqueta (`label: real|sembrada`), con ids que la telegrafían por prefijo
(`r000`, `s000`). El orden **sí** está mezclado de forma determinista por hash del contenido para no
delatarla — o sea que el problema estaba visto a medias.

La ceguera del juicio la sostiene una instrucción en prosa (`verify-citations` §modo benchmark:
*"NUNCA mostrarle `bench.json`"*, repetida por el propio `stdout` del script). Es una garantía de la
capa LLM sobre un artefacto que la capa determinista podría haber hecho imposible de filtrar.

**Cómo se cerraría.** Partir en dos: `bench_pairs.json` (lo que ve el juez: id opaco + afirmación +
ruta al fulltext) y `bench_key.json` (la clave, que sólo lee `score`). Un id opaco —hash— en vez de
`r`/`s`.

#### HUECO-9 — Re-capturar una página web destruye el snapshot anterior (INV-30) · P2

**Qué falta.** `fetch_web --force` re-baja y **pisa** el `.txt` (`:119-123`). La captura anterior —con
su fecha, que es literalmente la cita *"Retrieved <fecha>"*— desaparece. Si la página cambió, la nota
sigue citando una afirmación que ya no está en el snapshot vigente, y no queda rastro de que hubo
otro.

Es P2 porque exige `--force` explícito y porque el repo es git: la captura vieja sobrevive en el
historial si estaba commiteada. Se cruza con la decisión de intención §6.13 (qué es "mejor calidad"
entre dos artefactos del mismo método).

---

### 4.3 Invariantes de (B) que están mal derivados

Sólo dos, y ninguno se contabiliza como hueco:

- **INV-05** (puntero downstream en prosa) apunta a la capa equivocada. La capa determinista escribe
  plantillas fijas: el riesgo de escribir prosa que describa al consumidor es **enteramente** de la
  capa LLM, donde ya lo cubre la regla #0 y el WARN de fuga de implementación. Se deja como chequeo
  trivial (auditar las plantillas una vez), no como garantía a construir.
- **INV-75** (reportar la medición atada a su condición) es una obligación de redacción del skill y
  del README, no un invariante de la capa determinista. Se mantiene por completitud, con prioridad P2.

---

## 5. Lo que el sistema garantiza y (B) no pidió

Lo que está en (A) y no en (B). Cada uno con veredicto: **necesario** (falta justificarlo en la doc)
o **complejidad de más**.

| # | Garantía que el sistema da sin que nadie la pidiera | Veredicto |
|---|---|---|
| 1 | **Guardia de expansión (#37).** Entre la query y el primer paso que gasta red y disco, la cadena **frena** si el core se multiplicó (×1.5 y 50 o más nuevos) y exige `--yes`. | **Necesaria.** (B) derivó invariantes de *corrección* pero ninguno de *radio de daño*: nada impide que un cambio de lente dispare 800 descargas antes de que nadie lo note. Es el único freno económico de la cadena. Falta enunciarla como invariante propio — y su frontera exacta ya se equivocó una vez en 5 documentos (`>50` vs `50 o más`, corregido en 1.23.1). |
| 2 | **Rescate activo del corpus truncado (#79 y #28).** Al truncar, no sólo se marca: se corre una **segunda pasada con la misma query ordenada por fecha**, y hay una expansión por lookalikes de glifo que recuperó 121 core en una instancia real. | **Necesaria.** INV-52 sólo pide *marcar* la incompletitud; el sistema además la **repara parcialmente**, y de forma dirigida al sesgo que el orden por citas introduce por construcción (lo reciente). Merece ser contrato: si mañana alguien "simplifica" la segunda pasada, ningún invariante lo detiene. |
| 3 | **`EmptyResultError`.** Una query que devuelve 0 **aborta la cadena** en vez de persistir un `ads.json` vacío con exit 0. | **Necesaria.** Es la instancia concreta de INV-38 en el borde más peligroso (un vault que se construye sobre la nada, en silencio). Debería estar enunciada, no sólo implementada. |
| 4 | **El chequeo se blinda contra la bóveda rara.** El lint reporta y sigue ante ground-truth con valores no numéricos, `retraction:` escalar, registro ilegible, dos notas con el mismo stem — casos que antes lo tumbaban con `TypeError`. | **Necesaria.** Es un invariante de la **compuerta sobre sí misma**: *un chequeo que muere no es un chequeo*. (B) no lo derivó porque razonó sobre lo que el lint mira, no sobre el lint como artefacto. |
| 5 | **Los ocho `incomplete`: proxies de síntesis campo por campo.** `P_rot` sin documentar en la prosa, `activity_indicators_expected` vacío, planeta del frontmatter no discutido, paper core sin `methods`, paper extraído sin `role`, `thesis_links` sin `bearing`, ficha sin ground-truth, ground-truth sin ficha. | **Necesaria.** (B) derivó INV-45 (el paper llegó o no llegó); el sistema mide además **si la síntesis tocó cada eje**. Es la única red sobre la calidad de la capa LLM que no depende de otra corrida de LLM. |
| 6 | **El embudo se publica en la cabecera de la nota**, no sólo en el registro: fecha, universo→core, pendientes, y la ruta al registro, estampado quirúrgicamente sin tocar la prosa. Y `n_dropped` cuenta **sólo el carril del chaining** (#81), para no publicar un descarte que nadie hizo en la búsqueda. | **Necesaria.** INV-51 cubre el registro; esto cubre al **lector de la ficha**, que es la audiencia real. La precisión de #81 es exactamente el tipo de cuidado que el contrato debería premiar. |
| 7 | **Tolerancia de salida a consolas no-UTF8** (`stdout_tolerante`/`print_seguro`), implementación única compartida. | **Necesaria pero invisible.** Un script que muere imprimiendo su propio hallazgo es un falso limpio por otra puerta. Vive hoy sólo en docstrings. |
| 8 | **Garantías sobre el aparato de verificación**: presupuesto de tiempo del tier 0, "cero tests decorativos", mutantes muertos, corpus sintético reproducible por semilla, ratchet de instancia. | **Necesaria, y de otra naturaleza.** No son invariantes del producto sino del **verificador**. Merecen su propio lugar (`tests/README.md` ya los enuncia); se listan acá para que no se confundan con contrato de producto. Nota: el presupuesto documentado estaba vencido al doble y se arregló bajando el test culpable, no el número (1.23.1). |
| 9 | **PDFs por git-lfs y `.gitattributes` con `merge=ours` para los 7 archivos de instancia.** | **Necesario** (INV-68 lo roza), con la condición documentada: sin el driver configurado hay conflicto, no pisada. |

**Ninguno se juzga complejidad de más.** El candidato más plausible sería el rescate por glifo (#28),
que es maquinaria fina para un caso raro — pero tiene 121 core perdidos medidos en una instancia real
como justificación, incluido el paper del descubrimiento. Eso es exactamente lo que este repo pide
antes de aceptar una feature.

---

## 6. Decisiones de intención — **RESUELTAS** (2026-08-23)

> **Las 22 quedaron cerradas** en una revisión hecha **con el usuario**, recorriendo el sistema de punta
> a punta. El detalle —razones, mediciones y las 57 decisiones que salieron del recorrido, incluidas las
> 35 que el auditor no había previsto— está en **`docs/revision-contrato-2026-08-23.md`**. Los
> invariantes nuevos entraron como **§3.K (INV-76…91)**, todos en estado HUECO. *(Al 2026-08-24,
> tras las tandas 0–6: 10 medidos, 4 parciales, 2 HUECO — ver el encabezado de §3.K.)*
>
> | # | Resuelta por | # | Resuelta por |
> |---|---|---|---|
> | #1 | D-45 | #12 | D-52 |
> | #2 | D-1, D-2 | #13 | D-19 + D-41 |
> | #3 | D-50 | #14 | D-42 |
> | #4 | D-44 | #15 | D-57 |
> | #5 | D-4 | #16 | D-56 |
> | #6 | D-54 | #17 | D-48 |
> | #7 | D-51 (*medición pendiente*, no decisión) | #18 | D-43 |
> | #8 | D-47 | #19 | D-48 |
> | #9 | D-45 + D-46 | #20 | D-48 |
> | #10 | D-49 | #21 | D-53 |
> | #11 | D-28 | #22 | D-55 |

Las preguntas originales se conservan abajo: son el **enunciado** de cada disyuntiva, y sin ellas la
resolución no se entiende.

1. **Regresión del ground-truth.** Si NEA **deja de reportar** un valor que antes traía, ¿el espejo lo
   borra a `null` (fidelidad total, pero se pierde un dato que la ficha citaba) o lo conserva marcado
   como stale? El espejo puro dice borrar; *no destruir* dice conservar con marca.
2. **Alcance exacto del espejo.** El contrato nombra campos que vienen de **dos** autoridades (NEA y
   SIMBAD). ¿"Espejo puro" es una sola autoridad por campo, o un espejo compuesto? Y si discrepan
   sobre el mismo campo, ¿es disputa a nivel nota o precedencia declarada?
3. **Severidad de la fuga de implementación.** Hoy es WARN porque la heurística tiene falsos
   positivos. Pero la frontera dura se declara **no negociable**. ¿Se acepta que la regla #0 quede
   custodiada por un chequeo no bloqueante, o debería bloquear con lista de excepciones explícitas?
4. **La compuerta: ¿gate duro o consejo?** El lint es "paso de cierre antes de commitear" y el hook
   es **opcional**. ¿Debe ser imposible commitear con bloqueantes, o la decisión final es del humano?
   Un gate duro obliga a una vía de escape documentada.
5. **Cobertura de verificación: ¿backlog o bloqueo?** Una nota con citas que **nunca** pasó por
   `verify-citations` afirma sin haber sido chequeada. Hoy es backlog. ¿Es aceptable que conviva
   indefinidamente con contenido verificado?
6. **Idempotencia y tiempo.** ¿Los campos que registran *cuándo* corrió algo rompen la idempotencia
   byte-exacta, o se congelan cuando nada sustantivo cambió? Lo segundo da diffs limpios y hace que
   una fecha mienta levemente.
7. **Umbral de legibilidad.** ¿Quién lo fija y con qué evidencia? Laxo deja entrar basura citable;
   estricto manda a "pendiente" fuentes que sirven. ¿Global o por tipo de documento?
8. **Prosa que cita una fuente retractada.** El lint bloquea, pero no dice qué hacer con lo ya
   escrito: ¿se elimina la afirmación, se marca como sostenida por fuente retractada, o se convierte
   en disputa histórica? Las tres dan bóvedas distintas.
9. **Alcance del barrido de retracciones.** La cadena chequea el sujeto en curso; el barrido completo
   es una pasada **manual**. ¿Es aceptable que una retractación de hace seis meses siga respaldando
   prosa hasta que alguien se acuerde? Si no, hace falta una noción de caducidad del chequeo.
10. **Re-clasificación automática vs explícita.** Cambiar la lente invalida los veredictos vigentes.
    ¿La capa determinista debe **detectar** la desincronización y negarse a operar, o alcanza con
    avisar? Lo primero es más honesto y más molesto.
11. **Conteos del registro tras un descarte.** Si se descarta sin re-correr la cadena, el embudo queda
    viejo. ¿Se actualizan los conteos derivables, o se congela el snapshot por fidelidad a "esto fue
    lo que se corrió ese día"?
12. **Descarte por un carril, reaparición por el otro.** Una fuente descartada como candidato del
    grafo que después se declara explícitamente: ¿entra (el juicio nuevo es más fuerte), se bloquea
    (vale el viejo), o se deriva a una persona? Hoy: **avisa y procesa igual** (medido).
13. **Qué es "mejor calidad" en un artefacto compartido.** El orden entre métodos de extracción está
    declarado; no qué pasa entre dos artefactos del **mismo** método y contenido distinto (dos
    capturas web en fechas distintas, preprint vs publicado). ¿Gana el más nuevo, el publicado, o
    conviven? (Se cruza con HUECO-9.)
14. **Dónde termina "inferencia" y empieza contaminación.** ¿La capa determinista debe exigir que una
    inferencia **nombre las fuentes** de las que deriva (verificable), o alcanza con la marca (no
    verificable)? Sin lo primero, `inferencia` es una escotilla que vacía la regla #0.
15. **La cadena como fuente de verdad de su propio orden.** ¿Debe el chequeo poder verificar que la
    cadena se corrió **completa y en orden** para un sujeto —lo que exige que la corrida deje una traza
    estructurada— o se confía en que correr el orquestador alcanza?
16. **Qué se hace con `data_local`.** ¿Validar que existe (útil, pero vuelve el vault no-portable de
    hecho), ignorarlo, o marcarlo como no verificable en esta máquina?
17. **Fuerza del pedido explícito.** ¿Confirmación interactiva, bandera, o ambas? Y en entorno no
    interactivo (CI, agente automatizado), ¿la operación destructiva simplemente no existe?

**Agregadas por este cruce:**

18. **Severidad de "no evaluado".** Cuando un chequeo no puede correr (sin `git`, config ilegible,
    sin `build/`), ¿el hallazgo es **bloqueante** (la compuerta no certifica lo que no miró),
    **backlog** (coherente con "la garantía no corrió acá") o WARN? Hoy el repo usa las tres según el
    caso, sin regla declarada — y en dos casos usa **silencio** (INC-1). Esta decisión gobierna
    HUECO-1 y HUECO-5, y probablemente merece ser el invariante que las unifique.
19. **¿Las escotillas de bandera deben quedar registradas?** `--yes`, `--no-triage` y `--force`
    cambian qué universo describe una ficha. ¿La corrida debe estamparlo en el `busqueda` del registro
    (y por lo tanto en la cabecera de la nota), o alcanza con que el operador sepa lo que hizo?
    (HUECO-3.)
20. **¿Un juicio persistido puede pisarse con un flag?** `--no-triage` hoy lo hace en silencio. Las
    opciones: que respete siempre los descartes (el flag apaga la compuerta, no el registro), que
    avise y siga, o que exija un flag propio para pisarlos. (INC-2.)
21. **¿La atomicidad de escritura es contrato o detalle de implementación?** Cinco writers son
    atómicos y el que más escribe no. ¿Se declara *"toda escritura en `vault/` es atómica"* como
    invariante —lo que obliga a un helper único y a un test por comando— o se acepta que las notas
    son best-effort porque el repo es git? (HUECO-2.)
22. **¿La ceguera del benchmark la sostiene la construcción o la instrucción?** Partir `bench.json`
    en examen y clave cuesta poco; dejarlo como está hace que la medición del propio error dependa de
    que un skill se obedezca. (HUECO-8.)

---

## 7. Cómo se mantiene este documento

**Cuando se agrega una garantía nueva** (una categoría de lint, un invariante de un script, una
promesa nueva en `CLAUDE.md` o en un skill):

1. **Entra acá primero, con ID nuevo y correlativo.** Los IDs son **estables y no se reciclan**: si
   un invariante se retira, su fila queda con estado `retirado` y el motivo. Un ID que cambia de
   significado rompe toda referencia externa.
2. **Se enuncia falsable.** Si no se puede describir el experimento que lo refutaría, todavía no es
   un invariante: es una intención. Escribirlo igual, con estado `HUECO`, es correcto — lo que no
   sirve es enunciarlo de forma que no pueda fallar.
3. **Nace en `garantizado sin medir`.** Sólo pasa a `garantizado y medido` cuando existe un test o un
   harness que **podría haber fallado** y no falló. Un test que pasa por construcción no mueve el
   estado: la 4ª pasada de auditoría de este repo está entera dedicada a tests que pasaban por el
   motivo equivocado.
4. **La columna "cómo se verifica" nombra el instrumento real** (archivo de test, comando, harness),
   no una descripción. Si el instrumento no existe, dice **qué habría que escribir** — eso es la cola
   de trabajo.

**Cuando un invariante se mide y falla**, no se ajusta el enunciado para que pase. Se pone
`INCUMPLIDO` con el número, el comando y el alcance, y se decide aparte si se arregla el código o se
baja la promesa. Bajar la promesa es una decisión legítima **y visible**; ajustar el enunciado en
silencio es cómo se llega a docstrings que afirman garantías falsas.

**Cuando cambia el código**, este archivo no se toca salvo que cambie **lo exigido**. Es la mitad del
punto de que esté separado: si cada refactor obliga a editarlo, volvió a ser un comentario.

**Revisión periódica.** El cruce que produjo este documento (medir el sistema por un lado, derivar del
propósito a ciegas por el otro) es repetible y **debería repetirse cuando el contrato se mueva**, no
en cada tanda. Su valor está en la ceguera: si quien deriva ya vio este archivo, sólo va a confirmarlo.

---

## Apéndice — Trazabilidad de la evidencia

| Fase de la 8ª pasada | Qué midió | Citada en |
|---|---|---|
| **F1** — invariantes documentados, ejecutados | 46 afirmaciones curadas → 41 ejecutadas (34 confirmadas, 5 refutadas, 2 parciales) | INV-01…14, 16, 17, 19…21, 25, 30…35, 37, 39…47, 52, 57, 59, 62, 68, 72, 73 |
| **F2** — los 9 skills | 45 invocaciones + ~15 flags; 100% existen y parsean; 100% de las referencias cruzadas resuelven | §5, superficie de comandos |
| **F3** — superficie inversa código→doc | 42 flags (9 sin documentar), 30 categorías del lint mapeadas 1:1 en ambas direcciones | INV-41, INC-2, HUECO-3 |
| **F4** — garantías dinámicas a escala | 5 familias sobre corpus de 900 notas: idempotencia (10 comandos ×2), no-destrucción (6+control), atomicidad (5 writers con inyección de fallo), **30/30 categorías sembradas**, ciclo vintage→migrado | INV-02, 03, 08, 10, 15, 22, 28, 31, 33, 34, 37, 42, 43, 45, 52, 64, 65; HUECO-2 |
| **F5** — números re-medidos contra instancia real (908 papers) | 7 números re-medibles, todos vigentes y ciertos; dos con coincidencia exacta (22/25 cabeceras; one-liners letra por letra) | INV-06, 18, 35, 60, 72; HUECO-4 |
| **F6** — libro mayor y release | Ledger por worktree; el delta de tests de 1.22.1 (+21 declarado vs +30 real) es el mismo error por tercera vez | §7 (los deltas se miden, no se recuerdan) |
| **Lectura de código para este cruce** | `query_ads.py` (lente en el registro, gate, doctype), `lint.py` (`mirror_issues`, objetivo, barridos), `lib_config.py` (degradación de config), `make_notes.py` (escrituras), `bench_verify.py` (siembra), `fetch_web.py`, `extract_fulltext.py` | INV-24, 51, 55, 56, 70; INC-2; HUECO-1, 2, 7, 8, 9 |

**Estado de los 5 refutados de (A) al escribir esto (1.23.1):** cerrados `lint.py --help` (ahora con
`argparse`: `--help` documenta y sale 0, flag inexistente sale 2 sin correr nada), la frontera de la
guardia de expansión (5 sitios corregidos a "50 o más"), los 8 campos incompletos en `CLAUDE.md`, y el
presupuesto del tier 0 (2,03 s — se arregló el test que dormía 3 s, no el número). **Pendiente:** el
exit 1 sobrecargado de `check_retractions` (vale "detecté retractados" y "no había nada que
chequear", y `ingest_star.py:66-67` traduce cualquier 1 al primer mensaje).
