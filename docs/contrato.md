# Contrato funcional de la capa determinista de Almagesto

> La evidencia detrás de los invariantes **medidos** —con qué número, sobre qué corpus y con
> qué salvedad— vive en `docs/mediciones.md`.

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
> 0–6. **Medición vigente (2026-08-27, tras la pasada `/auditar` y su tanda de fix, sobre los 135)**:
> 104 *garantizados y medidos* · 4 *garantizados* (sin medición propia) · 13 *sin
> medir* · 8 *parciales* · 5 *HUECO* · 1 *INCUMPLIDO*.
> *(#149: el denominador decía **104** cuando el desglose ya sumaba 126 — se corrigió, y el test
> `test_el_conteo_del_encabezado_es_el_de_las_filas` lo ata a las filas.)* El salto no es trabajo de documentación: son
> las nueve tandas, más tres auditorías que encontraron filas **peor escritas que el código**
> (INV-21, 29, 32, 38, 39, 49, 51, 56, 60 declaraban deuda ya saldada) y dos **mejor escritas que
> el código** (INV-43 e INV-72 afirmaban garantías que no había).
>
> ⚠ **Tres filas evitaban `parcial` con un paréntesis ad-hoc** —INV-49 *"con brecha nombrada"*,
> INV-79 *"mitad determinista"*, INV-17 *"con deuda"*— y una de ellas (INV-49, P0) admitía en su
> propio texto que contradecía el «todos los carriles» de su enunciado. Con el vocabulario que §2
> define, eso es `parcial`: quedaron reclasificadas, y por eso el conteo de medidos **baja** aunque
> la implementación haya avanzado. Un estado inventado por fila es cómo un documento empieza a
> mentir sin decir nada falso.

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

**Instrumentos citados.** `tier 0` = `pytest tests/` (1022 casos, ~5 s — medido 2026-08-24, pasada `/auditar`); `tier 1` = `pytest -m
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
| **INV-04** | La capa determinista no genera material de implementación, y existe un chequeo que lo señala cuando lo escribió otro. | P1 | **garantizado y medido** | `impl_leaks` sembrada: 1 hit en prosa, 0 en blockquote, WARN, exit 0 (8ª F1 #31). D-50 suma la **mitad de auto-referencia** —el modo más frecuente: la nota describiendo a quien la consume— con marcadores genéricos (`nuestro pipeline`, `downstream`, `para el repo`, `supuesto de trabajo`) y los nombres propios de `downstream: []` (`lib_config.load_downstream`), matcheados **sólo en contexto de consumo**: el nombre pelado marcaría cada mención legítima (en esta bóveda `ICA` es además un método real) y un rojo permanente se deja de mirar. Sin `downstream` declarado esa mitad queda apagada, **sin WARN de ausencia**. ⚠ Sigue siendo **no bloqueante** custodiando una regla declarada *no negociable* → decisión de intención §6.3. |
| **INV-05** | La capa determinista sólo escribe punteros externos en campos estructurales del frontmatter; nunca prosa que describa al consumidor. | P2 | garantizado sin medir | `grep` sobre las plantillas de `make_notes.py` buscando mención de consumidores. Nadie lo corrió. *Nota: el riesgo real vive en la capa LLM, no acá — el invariante apunta medio a la capa equivocada, pero el chequeo es trivial y conviene tenerlo.* |

### B. Autoridad de las fuentes: el espejo del ground-truth (#70)

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-06** | Cada campo espejo vale exactamente lo que dice el ground-truth, o `null`. Nunca literatura, nunca redondeo sin registro. | P0 | **garantizado y medido** | 7 violaciones distintas sembradas → exit 1 con **un hallazgo por campo**: `teff_K` inventado, `P_rot` rellenado, `K_ms` rellenado (8ª F1 #2b). `lint.mirror_issues` compara campo por campo en las dos direcciones. Confirmado además contra la instancia real: 13 hallazgos vivos (8ª F5). |
| **INV-07** | Si el ground-truth no trae el campo, el frontmatter lleva la clave presente y en `null`. No se omite ni se completa por otra vía. | P0 | **garantizado y medido** | `make_notes` deja `P_rot_days`/`K_ms`/`e` en `None` cuando NEA calla (8ª F1 #2a). La rama "la ficha tiene valor y el GT no" se reporta con mensaje propio (`lint.mirror_issues`). |
| **INV-08** | Ninguna otra operación modifica un campo espejo. Una re-corrida lo sincroniza con la fuente vigente; nada más lo toca. | P0 | **garantizado y medido** | Probado por operación: `make_notes` sin `--force` (8ª F4 G2.1/G2.2), `--restamp-headers` (G2.3), `--restamp-pdf-links` (G2.4), `--migrate-disputes` (G2.5), `--sync-mirror` add-only (G2.6, 8ª F1 #39), retro-linkeo (F1 #10). Control de cordura: `--force` **sí** destruye (G2.7) — sin él los seis OK serían falsos negativos. |
| **INV-09** | La comparación ficha↔ground-truth es por **identidad** (qué planetas, campo por campo), no por cardinalidad. | P0 | **garantizado y medido** | El caso adversario —dos listas del mismo largo con letras distintas— falla como corresponde (8ª F1 #2b: planeta extra, planeta de NEA ausente, letra repetida, `P_days ≠ GT`). Fue el defecto que cerró #70 y hoy tiene test. |
| **INV-10** | Las derivaciones cruzadas se recalculan y las inconsistencias se **reportan**; nunca se reescribe la fuente para hacerla consistente. | P0 | **garantizado y medido** | `mass_issues` sembrada (8ª F4 §2); el lint re-deriva la m·sini implícita offline (`lint.main` → `fetch_ground_truth.msini_earth`) y no escribe una línea en `vault/` (8ª F4 G1.8). |
| **INV-11** | Ante fuentes en conflicto la capa determinista nunca elige un valor: ofrece la estructura para registrar ambas posiciones y deja el espejo intacto. | P0 | **garantizado y medido** | La regla está escrita (`CLAUDE.md` §2b, *"sin columna valor adoptado ni por qué"*) y el frontmatter no tiene campo para eso. **Falta**: auditar las plantillas generadas por `make_notes` confirmando que ninguna trae esa columna, como test pineado. **Al día 2026-08-24**: el test pineado que esta fila daba por faltante **existe** — `tests/test_make_notes.py::test_inventario_no_tiene_columna_de_valor_adoptado` fija la cabecera exacta y exige que la ausencia esté *dicha*, no sólo omitida. Sigue cubriendo sólo la ficha de estrella, no el concepto. |
| **INV-12** | Una disputa válida tiene `field`, **≥2 posiciones**, y cada posición dice quién la sostiene. Lo que no cumpla bloquea. | P0 | **garantizado y medido** | Batería completa: sin `field`, 1 posición, posición sin `ref`/`source`, `source` fuera de vocabulario → exit 1, 5 hallazgos para 4 notas (8ª F1 #5). |
| **INV-13** | Un schema que el lector ya no interpreta se **detecta y bloquea**, con la migración a la vista. Nunca se ignora en silencio ni se agrega un lector tolerante. | P0 | **garantizado y medido** | `old_disputes` → exit 1 y el reporte contiene `--migrate-disputes` (8ª F1 #6); ciclo completo vintage→migrado→conteo 0→2ª pasada byte idéntica (8ª F4 G5). |
| **INV-14** | Cada campo de cada schema tiene **una sola** autoridad de escritura declarada, y esa declaración es verificable desde afuera de la implementación. | P1 | garantizado sin medir | La declaración existe en prosa (`README.md` §Quién decide cada cosa) y, para el espejo, en forma máquina (`MIRROR_HOST`/`MIRROR_PLANET` en `lint.py`). **Falta** la matriz: corromper cada campo, correr **todas** las operaciones, y confirmar que sólo la autoridad declarada lo restaura. |

### C. No destruir trabajo (síntesis del modelo y juicio del humano)

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-15** | Toda escritura sobre una nota existente es aditiva o quirúrgica sobre regiones derivadas. Destruir prosa exige una acción explícita distinta de la corrida normal. | P0 | **garantizado y medido** | Marcador de prosa sembrado y verificado tras cada comando: 6 confirmaciones + control de cordura (`--force` sí destruye) — 8ª F4 familia 2. Es la garantía mejor probada del repo junto con el espejo. |
| **INV-16** | El merge de campos compartidos es add-only: agrega lo que falta, no borra ni reordena, y si el elemento ya está no hay diff. | P0 | **garantizado y medido** | El retro-linkeo no quita un `stars:` curado a mano; 2ª corrida byte idéntica (8ª F1 #10). |
| **INV-17** | Toda región reescribible por la capa determinista es identificable por una marca estable, y la reescritura no se sale de ella. | P1 | **parcial** (medido, con la deuda nombrada) | Ancla de cabecera: nota con "Capa LLM" preexistente estampada **sin duplicar**, prosa intacta, 2ª pasada byte idéntica (8ª F1 #16); `--force` es la única puerta. **Falta**: texto adversario inmediatamente antes y después del ancla. |
| **INV-18** | Una cirugía que no encuentra su ancla **se reporta**; nunca termina con éxito aparente sin haber hecho nada. | P0 | **garantizado y medido** | `make_notes` imprime `N de M estampadas` y el lint lista las no estampables (`headerless`, sembrada en 8ª F4 §2). Medido en instancia real: 22 de 25 notas sin ancla, hoy exactamente 22/25 (8ª F5). |
| **INV-19** | Después de borrar o renombrar una entidad no queda ninguna referencia colgada **en ninguna capa** ni archivo huérfano en `raw/`. | P0 | **garantizado y medido** (1.35.0) | **Las dos mitades entraron.** Herramienta: `scripts/entity.py` (`plan` / `delete` / `rename`) toca las **siete** capas —YAML, registro, ground-truth, `raw/pdfs`, `raw/fulltext`, nota, `build/`— y es dry-run sin `--yes` porque la capa 2 no se regenera (`tests/test_entity.py`, 12 tests: cada capa un assert, más el paper compartido que **no** se borra, el que queda sin destino que se **avisa**, los wikilinks rotos que **no** se reparan solos y el renombre que **rehúsa** fusionar dos entidades). Red del lint: categoría *Capas colgadas* (registro/`raw`/`build` de un slug que ya no está en `stars.yaml`/`themes.yaml`) — `tests/test_lint.py::test_capas_colgadas_se_reportan`, `::test_la_entidad_viva_no_se_reporta_colgada`, `::test_el_registro_de_red_no_es_una_capa_colgada`. |
| **INV-20** | Ningún artefacto de `vault/raw/` ya existente se modifica ni se borra, salvo mejora declarada o borrado explícito de la entidad. | P0 | garantizado sin medir | Evidencia parcial: `fetch_ground_truth` no refresca un snapshot existente (8ª F1 #40, mensaje *"ya existe — no se pisa"*); `extract_fulltext` no re-extrae sin `--force` (8ª F4 G1.9); los fetchers saltean lo bajado. **Falta**: hashear todo `raw/` antes y después de una re-corrida completa. Y `--force` no deja registro de qué pisó. |
| **INV-21** | Una interrupción deja el vault consistente: o el artefacto no existe, o existe completo. No hay notas truncadas ni textos a medias que pasen el umbral. | P0 | **garantizado y medido** | Ver §4.HUECO-2. Los 5 writers atómicos protegen su destino (8ª F4 familia 3, inyección de fallo agnóstica de ruta), y `extract_fulltext` borra el `.txt` a medias (`:204`). Pero **`make_notes` escribe las notas con `write_text` directo en 15 sitios** — sin tmp+rename— mientras `check_retractions` escribe *la misma clase de archivo* atómicamente. **Cerrado por D-53 (1.24.0)**: `make_notes` escribe por `cfg.write_text_atomic` en sus 14 sitios. Instrumentos: `tests/test_lib_config.py::test_write_text_atomic_publica` (inyección de fallo en `os.replace`), `::test_sin_escrituras_directas_a_vault` (guard estático repo-wide) y `tests/test_make_notes.py::test_corte_publicando_no_deja_la_nota_a_medias`. |
| **INV-22** | Correr dos veces la misma operación con la misma config y las mismas fuentes deja el vault byte-idéntico. | P1 | **garantizado y medido** | 10 comandos ×2 con `hash_tree(ROOT)` sobre corpus de 900 notas: `make_notes` (con y sin `ads.json`), `--restamp-headers`, `--restamp-pdf-links`, `--sync-mirror`, `--migrate-disputes`, `triage --migrate`, `lint`, `extract_fulltext`, `bench_verify seed` (8ª F4 familia 1). |
| **INV-23** | El resultado no depende del orden ni de quién corrió último; sólo cambia si llega algo de mejor calidad declarada. | P1 | **INCUMPLIDO (parcial)** | Ver §4.INC-3. Re-correr no repunta y la precedencia por calidad se respeta (`ocr→pdftotext` mejora, `pdftotext→ocr` no degrada), pero el **primer** estampado de `fulltext` depende del orden: `A,B ≠ B,A` byte a byte (8ª F1 #7 / P-01). |
| **INV-24** | El veredicto core/no-core depende sólo de la metadata del paper y de la lente vigente. | P1 | garantizado sin medir | Lectura de código: `query_ads.classify` / `query_ads.exclusion_reason` son función de `(facets, doctype)` contra constantes de módulo leídas de la config; no hay estado de sujeto ni de corrida. **Falta**: clasificar el mismo paper llegando por dos sujetos y en dos momentos, y re-clasificar el corpus entero reproduciendo los veredictos vigentes. |
| **INV-25** | Borrar el scratch y re-correr reconstruye el estado sin pérdida. Corolario: nada no regenerable vive sólo en scratch. | P1 | garantizado sin medir | El caso histórico que lo violaba (`build/<slug>/triage.json`) está cerrado: migrador idempotente + detector **bloqueante** (8ª F1 #13, F4 G1.7). **Falta**: clonar en limpio sin `build/`, correr y diferenciar contra el vault original. |
| **INV-26** | El texto derivado de un documento es reproducible bit a bit, no pasa por ningún modelo, y la nota registra **cómo** se obtuvo. | P1 | garantizado sin medir | `fulltext_source` y `pdf_source` se estampan por verdad de disco (`extract_fulltext.main` → `cfg.record_pdf_source`); la idempotencia está medida (8ª F4 G1.9). **Falta** la reproducibilidad byte a byte real: en el sandbox `pdftotext` estaba mockeado. Exige la herramienta instalada. |
| **INV-27** | La clave de una fuente es única en la bóveda, estable entre corridas y validable. Dos fuentes distintas nunca comparten clave. | P1 | **HUECO (parcial)** | Ver §4.HUECO-7. La **forma** está validada (`BIBCODE_RE`, 8ª F1 #25) y la estabilidad se sostiene. **No existe** chequeo de colisión: dos fuentes off-ADS distintas con la misma clave sintética se resuelven por "el archivo ya existe, no lo piso" — sin avisar que la URL es otra. |

### D. Trazabilidad y verificabilidad de las citas

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-28** | Lo declarado legible pasa un umbral **determinista**; lo ilegible se marca y no cuenta como fuente disponible. | P1 | **garantizado y medido** | `is_legible` detecta mojibake (0% legible) y el escaneo cuya única capa es la **marca de agua** del bibcode (~19 chars/página) — 8ª F1 #42; categoría `illegible_txt` sembrada (F4 §2). El umbral concreto es decisión de intención §6.7. |
| **INV-29** | Cada fuente registra de qué documento salió, derivado de evidencia en el propio artefacto. La ausencia de evidencia se escribe **desconocido**, nunca *publicado*. | P0 | **garantizado y medido** | El mecanismo existe y es el correcto: `pdf_source` se lee de la marca que arXiv estampa en el `.txt`, por eso el backfill funciona sobre un corpus ya bajado (docstring de `extract_fulltext`). **Falta la prueba crítica**: que un preprint no pueda quedar marcado como publicado. Es un P0 sin ejecutar. **Al día 2026-08-24**: la «prueba crítica» que esta fila daba por no ejecutada **existe** — `tests/test_make_notes.py::test_pdf_source_desconocido_no_afirma_publicado` y `::test_pdf_source_la_marca_gana_sobre_el_registro`, más `::test_pdf_source_detecta_el_eprint_por_la_marca_de_arxiv`. |
| **INV-30** | La captura web es determinista y fechada, y re-capturar no destruye la anterior sin dejar rastro. | P1 | **HUECO (parcial)** | Ver §4.HUECO-9. Fechada y citable sí (`accessed`, snapshot con URL+fecha). Pero `fetch_web --force` **pisa** el snapshot anterior sin versionarlo ni registrarlo: la captura previa desaparece. |
| **INV-31** | El bloque de verificación lleva fecha y existe un chequeo determinista que detecta que la nota se editó **después**. | P0 | **garantizado y medido** | Medido por `git`, no por mtime: commit 2026-08-20 contra bloque 2020-01-01 → `stale=1` con el mensaje correcto (8ª F1 #15); categoría sembrada (F4 §2). |
| **INV-32** | Si la vigencia no se puede computar, el resultado es "no evaluado" **reportado**, nunca "vigente". | P0 | **garantizado y medido** | Ver §4.INC-1. Medido: sin `.git`, `stale=0` y **nada** en el reporte (8ª F1 #15). `CLAUDE.md:593-597` lo documenta como *"degrada a silencio fuera de un repo"* — el sistema hace exactamente lo que este invariante prohíbe, y lo dice. **Cerrado por D-43 (1.24.0)**, las dos puertas: `tests/test_lint.py::test_lint_sin_git_reporta_no_evaluado` y `::test_lint_objective_roto_bloquea`, con `::test_no_evaluado_no_contamina_conteos` como adversario del cero inventado. Ver la deuda de exit anotada en INV-87. |
| **INV-33** | Una fuente retractada citada queda estampada en su nota y el chequeo la surface como **bloqueante**. La detección es por identificador. | P0 | **garantizado y medido** | `retracted` bloquea, incluso con `retraction:` escalar (no crashea) — 8ª F1 #35, F4 §2. Detección vía Crossref por DOI, separada del surfacing offline. El alcance del barrido periódico es decisión §6.9. **Cerrado el hueco de la población sin `doi`** (auditoría 2026-08-24): un paper sin DOI no entraba ni en `checked` ni en `errors` —un tercer estado mudo— y un corpus enteramente off-ADS, que nace sin DOI por construcción, salía 0 con «0 con error al chequear»: se leía como *la bóveda está limpia de retracciones* sobre papers a los que nadie preguntó. Ahora se cuentan y se nombran, y si **nada** se consultó la corrida sale 2 (`tests/test_check_retractions.py::test_corpus_sin_doi_no_sale_limpio`, `::test_corpus_mixto_reporta_los_sin_doi_pero_no_bloquea`). |
| **INV-34** | Erratas y corrigenda se registran y se surface como **backlog** (no bloquean), con información suficiente para revisar los valores extraídos. | P1 | **garantizado y medido** | `corrections` sembrada: 0→1, exit **0** (8ª F4 §2). |
| **INV-35** | Todo contenido prometido vía consulta dinámica tiene un equivalente determinista que devuelve el **mismo** conjunto, con el **mismo** parser, sin plugins no versionados. | P0 | **garantizado y medido** | Los dos estilos de lista (bloque y flow) devueltos por el one-liner oficial; `GJ 71` no trae `GJ 710` (8ª F1 #3/#4). Verificado además **letra por letra contra el corpus real**: one-liner oficial 193 papers, `grep` legacy 2, `awk` legacy 191 (8ª F5) — los dos modos de falla documentados, reproducidos. |
| **INV-36** | Escritor, chequeador y consumidor documentado leen el frontmatter con el mismo parser. No hay dos lecturas que discrepen. | P0 | **garantizado y medido** | `lib_config.split_fm` es el único parser, y el one-liner que `CLAUDE.md` publica lo usa. Un frontmatter que no parsea **bloquea** en vez de evadir en silencio (8ª F1 #34, `fm_broken`). `frontmatter_span` ubica el delimitador por línea, no por subcadena (cierra el `---` dentro de un escalar). |

### E. El veredicto del chequeo de salud (la compuerta)

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-37** | El código de salida distingue apto de no apto: nunca éxito con bloqueantes, nunca error por higiene. | P0 | **garantizado y medido** | **30/30 categorías** sembradas una por una sobre corpus limpio (n0=0 verificado antes de mutar), con delta exacto y exit code (8ª F4 §2). Y sin falsos positivos: corpus limpio de 300 papers → exit 0 (F1 #37). |
| **INV-38** | Un chequeo que no puede correr por falta de insumo reporta que **no evaluó**. Jamás contribuye un cero al total. | P0 | **garantizado y medido** | Ver §4.INC-1. **Honrado** en tres caminos medidos: sin `build/` cae al registro versionado con su fecha; registro ilegible → backlog explícito en vez de "0 pendientes"; ground-truth ilegible → bloqueante. **Violado** en dos: sin historial de `git`, `stale=0` mudo; con `objective.yaml` ilegible, lente vacía y ni una línea de reporte. **Subsumido por INV-87 y cerrado con él (D-43, 1.24.0)**: la categoría *⛔ No evaluado* cuenta para el exit y suprime la categoría normal. Desde 2026-08-24 cubre también `stars.yaml`/`themes.yaml` ilegibles, que antes mataban al lint con traceback. ⚠ **La población creció en #192/#193 (2026-08-27) y ahí la garantía estaba incumplida**: el otro consumidor de esta doctrina es el **prompt del fan-out**, que callaba los dos estados «no se pudo medir» de sus detectores. Medido sobre 167 `.txt` de una bóveda real: `symbols_lost` vuelve **no evaluado en 69 (41 %)** y el prompt no lo decía, así que «el `.txt` conserva sus ecuaciones» y «nadie lo midió» llegaban **iguales** al extractor — en el eje que decide si una fórmula se cita del `.txt` o del PDF; de ahí salió una nota afirmando `tanh⁻¹` donde el PDF dice `tan⁻¹`. Ídem la maqueta: el aviso de dos columnas salía sólo por encima del umbral y por debajo no salía nada, con **12 de 167 (7 %)** en la banda gris y dos errores medidos en direcciones **opuestas**. Hoy el prompt declara los dos estados y publica la fracción medida con su umbral. ⛔ No se movió ningún umbral: con errores en las dos direcciones, correr el corte cambia un error por el otro. (`scripts/extraction_prompt.py::_symbols_note`, `::_layout_note`; `tests/test_extraction_prompt.py::test_el_prompt_declara_que_no_pudo_medir_los_simbolos`, `::test_el_prompt_declara_la_maqueta_medida_en_las_dos_direcciones`) |
| **INV-39** | Un dato de snapshot se reporta como snapshot, con su fecha, aclarando que no es el conteo vigente. | P0 | **garantizado y medido** | El código lo hace (fallback al `busqueda` del registro con fecha). **Falta**: desincronizar deliberadamente registro y estado vivo y leer el reporte. Barato de sembrar. **Al día 2026-08-24**: `tests/test_lint.py::test_registro_versionado_cubre_la_falta_de_build` exige la fecha literal y la frase «no el conteo vigente», y `::test_build_local_gana_sobre_el_registro` fija la precedencia. |
| **INV-40** | Cada chequeo se aplica a **toda** la población que declara cubrir; una nota no evaluable es hallazgo bloqueante, no una nota saltada. | P0 | **HUECO (parcial)** | Ver §4.HUECO-5. La mitad fuerte está: la nota que evadiría (frontmatter roto, lista escrita como escalar) **bloquea** (8ª F1 #34). La que falta: el reporte **no dice sobre qué población corrió cada dimensión**, así que "la diferencia está íntegramente explicada por hallazgos" no es verificable desde la salida. |
| **INV-41** | Cada clase de hallazgo tiene severidad fija, documentada y coherente con el daño. | P1 | **garantizado y medido** | El invariante mejor evidenciado del repo: mapeo **1:1 en ambas direcciones** entre las categorías del reporte y la prosa de `CLAUDE.md`, con la severidad correcta en cada caso (8ª F3(b)), y las bloqueantes del `n_block` coincidiendo con lo declarado (8ª F4 §2). ⚠ **Los números de esa medición caducaron** (eran 30 categorías y 12 bloqueantes) y volvieron a caducar dos veces en el mismo día — que es el punto. **Desde el issue 10.1 no se escriben a mano**: la severidad se declara **una sola vez**, en la tabla de `lint.collect()`, y el exit se **deriva** de ella; antes vivía duplicada (el título decía "(backlog)" y la pertenencia a la tupla de `n_block` decidía el exit), así que agregar una categoría al reporte y olvidarla en `n_block` —o al revés— no rompía ningún test. Lo fijan `tests/test_lint.py::test_la_severidad_se_declara_una_sola_vez`, `::test_las_claves_de_categoria_son_unicas_y_estables` y `::test_el_modo_cierre_solo_cambia_el_exit_de_los_pares`; el conteo vigente (70 categorías, 30 bloqueantes, 32 con `--cierre`) sale del código y lo publica `tests/README.md` atado por `tests/poblada/test_conteos_exactos.py::test_los_numeros_que_la_doc_publica_salen_del_codigo`. |
| **INV-42** | El chequeo no requiere red ni credenciales y no escribe una línea en `vault/`. | P0 | **garantizado y medido** | Corrida ×2 con hash de **todo** `ROOT`: sólo cambia `outputs/`, y el reporte es byte-idéntico (8ª F4 G1.8). La detección que sí necesita red (retracciones) está separada en otro script. |
| **INV-43** | Cada hallazgo nombra su archivo y el reporte es determinista entre corridas sobre el mismo estado. | P1 | **garantizado y medido** | Dos corridas → salida byte-idéntica (8ª F4 G1.8); cada línea del reporte trae el stem/ruta. ⚠ **Corregido el 2026-08-24**: esta fila afirmaba determinismo que no había. `orphans` salía de iterar un `set` de strings (orden dependiente del hash, randomizado por proceso) y el golden **ordenaba las líneas antes de comparar**, o sea que el único no-determinismo medido estaba neutralizado justo en el test que debía verlo. Arreglado en la fuente (`sorted`) + `tests/test_lint.py::test_notas_huerfanas_salen_en_orden_estable`; el golden ya compara orden crudo. |
| **INV-44** | Para cada paso salteable de la cadena existe un chequeo determinista que detecta la omisión. | P0 | **garantizado y medido** (1.35.0) | Ver §4.HUECO-3. Existen las redes de los pasos *que se olvidan*: triage pendiente (#55), verificación stale (#56), cabecera (#69), extraído-no-sintetizado (#75), corpus truncado (#79/#43). **No existe red para los pasos que se saltean con bandera**: `--yes` (guardia de expansión) y `--no-triage` (compuerta) no dejan traza en el registro ni en la nota. **Mitad cerrada por D-48/D-57 (1.26.0)**: `--no-triage` se eliminó (`tests/test_query_ads.py::test_no_triage_ya_no_existe`) y las escotillas quedan en el registro (`::test_escotillas_quedan_en_el_registro`). **La otra mitad entró en 1.35.0**: los orquestadores propagan sus escotillas por entorno (`ALMAGESTO_FLAGS`, mismo canal que `ALMAGESTO_VIA` — tiene que atravesar el `subprocess.run`) y `save_paso` las estampa con prefijo `orquestador:`, distinguibles de los flags del paso: `tests/test_ingest_star.py::test_la_escotilla_del_orquestador_deja_traza` y `::test_save_paso_estampa_la_escotilla_del_orquestador`. La escotilla con más consecuencias —`--yes` saltea la guardia de expansión, o sea que cambia lo que la cadena hizo— era la única sin traza. |
| **INV-45** | Una fuente ya extraída que no aparece citada en ninguna síntesis durable se reporta; el único modo de silenciarla es una declaración **con motivo**. | P1 | **garantizado y medido** | Sin campo → 1 hallazgo; `true`/`""`/`null` → 1 con mensaje *"sin motivo"*; motivo string → 0 (8ª F1 #9). Categoría `unsynthesized` sembrada (F4 §2). |
| **INV-46** | Todo campo con vocabulario cerrado se valida contra él y un valor fuera de vocabulario **bloquea**. | P1 | **garantizado y medido** | `role: [fundacionall]` → exit 1 (8ª F1 #8); `source` de disputa fuera de vocabulario → exit 1 (F1 #5). El vocabulario vive en un solo lugar (`lint.ROLES` y `lint.DISPUTE_SOURCES`). |
| **INV-47** | Donde el diseño declara lista abierta, se avisa y se crea igual, y la lista **nunca** se infiere de lo que hay en disco. | P1 | **garantizado y medido** | Área no declarada: aviso presente, nota creada, WARN=1, bloqueantes=0, exit 0 (8ª F1 #30). La no-inferencia se sostiene por construcción: la lista sale de `objective.yaml`, no del filesystem. |

| **INV-105** | El gate de cierre se acota al **sujeto que la operación tocó**, y acotarlo no esconde la deuda ajena ni debilita un bloqueante. | P1 | **garantizado y medido** | #121. `lint --cierre <slug>` → `entity.notas_del_slug` (nota de la entidad + papers por artefacto + retro-linkeados por `stars`/`thesis_links`/`methods`, D-24) y `LintResult.en_alcance`. El razonamiento de R-1 —«un par sin verificar significa que **no terminaste**»— es sobre lo que esa operación tocó, y aplicado a la bóveda entera **no se podía cumplir**: medido al cerrar un tema real, el único bloqueante eran las 147 citas sin bloque de **otra** estrella, así que el gate arrancaba en rojo y seguía en rojo hiciera lo que hiciera la operación — y hubo que auditar las categorías a ojo, una por una, para verlo. Un gate que se audita a mano dejó de ser un gate. Tres recortes, cada uno contra un modo de falla: el **reporte no se acota** (la deuda ajena se lista entera, marcada «no frena»), el alcance toca **sólo** la severidad de cierre (si no, `--cierre <slug>` sería un gate **más débil** que un `lint` pelado) y un slug inexistente **se rehúsa** (exit 2) en vez de devolver cero hallazgos en alcance sobre una bóveda con deuda. (`tests/test_lint.py::test_el_cierre_acotado_no_cuenta_la_deuda_del_otro_sujeto`, `tests/test_lint.py::test_el_alcance_no_debilita_a_los_bloqueantes`, `tests/test_lint.py::test_un_slug_inexistente_no_da_un_verde_inventado`) |
| **INV-106** | Una señal de **identidad** no se apoya en una extracción fallida: dos `.txt` ilegibles con los mismos bytes son dos fracasos idénticos, no el mismo trabajo. | P0 | **garantizado y medido** | Recorte de la segunda señal de #114 (identidad por bytes del fulltext) al conjunto que pasa `is_legible` — el mismo umbral con el que el lint ya reporta esos `.txt` en su propia categoría, y que dice justamente «esto no sirve para grep ni para verify». **Medido el 2026-08-26** sobre el corpus sintético: los dos `.txt` ilegibles sembrados a propósito producían un **tercer** duplicado que nadie sembró — y la categoría es **bloqueante**, o sea que mandaba a fusionar dos papers ajenos: a **destruir una nota**. Es el modo de falla de un detector nuevo que se estrena sobre el caso feliz. (`tests/poblada/test_conteos_exactos.py::test_todas_las_anomalias_juntas_no_se_pisan`, `tests/poblada/test_golden.py::test_lint_golden_semilla_fija`) |

| **INV-107** | La fila de verificación declara **contra qué archivo** se verificó el par; el lint no lo infiere del frontmatter. | P0 | **garantizado y medido** | #117. La celda `Hash fuente` lleva `txt:<sha10>` o `pdf:<sha10>` (`lib_blocks.split_source_ref`) y el lint hashea **ese** archivo; una celda sin prefijo es *no consta* —no `txt`— y **bloquea**, con su migrador (`make_notes --migrate-verif-archivo`, que deduce el archivo del hash que la fila ya guardaba: identificarlo por su huella, no re-inferirlo). La regla anterior (#113/B-2: `symbols_lost` ⇒ PDF, si no el `.txt`) es **más angosta que la práctica** — una fuente `fulltext_source: ocr` también se verifica contra el PDF cuando el escaneo del editor destruyó los símbolos, y eso pasó con **3 de las 5** fuentes marcadas de un tema real: el lint hasheaba el archivo equivocado y devolvía **17 pares «vencidos por fuente»** sobre fuentes que nadie tocó. La decisión la toma el verificador **par por par**; el frontmatter no puede saberla. **Medido el 2026-08-26**: el migrador identificó las **198** filas de una bóveda real (125 + 73) sin una sola sin resolver — 11 al PDF, 187 al `.txt`. (`tests/test_lint.py::test_ocr_verificado_contra_el_PDF_no_vence_al_re_extraer_el_txt`, `tests/test_lint.py::test_fila_sin_declarar_archivo_no_se_adivina`, `tests/test_make_notes.py::test_migrar_verif_deduce_el_archivo_del_hash_no_del_frontmatter`) |

| **INV-108** | Una fuente que todavía no está en disco declara **por qué**, con vocabulario cerrado y **motivo libre obligatorio**. | P1 | **garantizado y medido** | #80. `cfg.PENDING_OK` = `paywall|scan|unextractable|adquisicion`, validado en `ingest_theme` (aborta) y en el lint (nombra la nota). Dos defectos, uno por mitad: el valor se escribía **verbatim** en la nota —un typo entraba mudo y el lint lo listaba como precondición legítima, la familia de `role` y de `via`— y los tres valores históricos describen un **fallo**, así que un libro que el usuario va a conseguir entraba forzado como `paywall` y se perdía el motivo real. El motivo es obligatorio por el mismo argumento que el `--reason` del triage: en seis meses lo que sirve es el motivo, no la categoría. Sobre notas ya escritas es **backlog**, no bloqueante: el motivo no se puede inventar (a diferencia del archivo de INV-107, que se deduce del hash). (`tests/test_ingest_theme.py::test_pending_fuera_del_vocabulario_aborta`, `tests/test_ingest_theme.py::test_pending_sin_motivo_aborta`, `tests/test_lint.py::test_pending_sin_motivo_se_reporta_pero_no_bloquea`) |
| **INV-109** | Una fuente **larga** declara cómo se la cita y **qué parte entró**; sin eso un recorte deliberado se lee como omisión. | P1 | **garantizado y medido** | #80. `unidad_cita: linea|pagina|seccion` (cerrado, bloquea) + `alcance` (obligatorio cuando la unidad no es la línea; backlog sobre notas ya escritas). Un libro rompe dos supuestos del contrato de `verify-citations`: el fan-out asume un `.txt` que un subagente lee **entero** —700 páginas lo revientan— y «línea 18443» no es una referencia utilizable. Y casi nunca entra entero, lo que choca con el chequeo de **completitud**, que sin `alcance` no distingue el recorte del olvido. Eje **distinto** del `txt:`/`pdf:` de INV-107: aquél dice qué archivo se leyó, éste cómo se apunta adentro — el `.txt` de un libro tampoco se cita por línea. (`tests/test_ingest_theme.py::test_libro_declara_unidad_de_cita_y_alcance`, `tests/test_ingest_theme.py::test_unidad_no_linea_sin_alcance_aborta`, `tests/test_lint.py::test_documento_largo_sin_alcance_se_reporta`) |

| **INV-110** | Un paper que se clasificó **sin abstract** queda marcado, en la nota y en el registro. | P1 | **garantizado y medido** | #86. `to_record` estampa `sin_abstract` y lo espejan los tres backends (la paridad la fija `tests/test_backends_schema.py`); viaja a la nota (sobrevive a `build/`, que es gitignored), al listado del triage —donde se está decidiendo si el paper entra— y al conteo `n_sin_abstract` del registro. ADS no tiene abstract para buena parte de los escaneos viejos, así que esos papers se juzgan con **título + keywords y nada más**, una fracción de la información con la que se juzga a los demás, y el veredicto salía igual de liso; como los no-core **no se bajan**, nunca vuelve a mirarse. Es el espejo exacto de #79, que sesga contra lo reciente. ⛔ Es información, **no** una regla: no mueve el corte core/no-core, porque si lo moviera ser core dejaría de ser función de `(paper, lente)` (INV-24). (`tests/test_query_ads.py::test_registro_sin_abstract_queda_marcado`, `tests/test_query_ads.py::test_sin_abstract_no_cambia_el_veredicto`, `tests/test_triage.py::test_el_candidato_sin_abstract_se_marca_en_el_listado`) |
| **INV-111** | La cola de extracción se ordena por **cuánto del objetivo toca** cada paper, no por lo que apareció primero. | P2 | **garantizado y medido** | #87. `triage.py --prioridad`. `classify()` ya calculaba qué facetas matcheó cada paper y lo persistía, y aguas abajo se usaba **sólo para mostrar**: un paper que toca 4 facetas y uno que toca la mínima para pasar el corte eran indistinguibles para el paso más caro de la cadena. Citas/año mide **atención de la comunidad**; el número de facetas mide **pertinencia a lo que esta bóveda quiere saber**, que es la pregunta que la priorización tiene que responder — y sale gratis, ya está computada. Es además la única señal que no hereda el sesgo de edad de #79, por eso las citas quedan como desempate. ⛔ No filtra ni recalcula `relevant`: es un orden sobre lo que ya es core. (`tests/test_triage.py::test_prioridad_ordena_los_core_por_cuanto_del_objetivo_tocan`) |
| **INV-112** | «No lo leyó nadie» y «nunca se consiguió» son hallazgos **distintos**: son colas con dueños distintos. | P1 | **garantizado y medido** | #90. El lint separa por **verdad de disco** (sin `.txt` y sin PDF ⇒ la fuente no está) en vez de reportar las dos con el mismo mensaje —*«paper relevante sin `methods` (sin extraer)»*—. Una es trabajo del **agente** (leerlo), la otra del **usuario** (conseguir la fuente), y mezcladas no se pueden priorizar ni derivar. El residuo del resolver vivía en `build/<slug>/missing_pdf.json`, gitignored, y la nota quedaba muda. (`tests/test_lint.py::test_core_sin_pdf_no_se_confunde_con_sin_leer`) |
| **INV-113** | El **localizador** de la evidencia y el archivo que la fila vigila no pueden contradecirse. | P1 | **garantizado y medido** | #122. `lib_blocks.locator_kinds` + el cruce en el lint: si `Evidencia` cita `p. 628` y la fila declara `txt:` (o al revés), el hash vigila un archivo del que esa cita no salió — se dispara en falso al re-extraer el `.txt` y no ve que el PDF cambió. Es el modo de falla de INV-107 **sobrevivido a INV-107**: la migración conserva fielmente lo que la fila guardaba, y lo que queda mal anclado es contenido. **Medido el 2026-08-26**: 11 de 114 filas de un concepto real, todas de las tres fuentes con OCR del editor. Backlog: el par puede estar bien verificado; lo que hay que hacer es re-anclarlo. (`tests/test_lint.py::test_localizador_que_contradice_al_archivo_vigilado`) |
| **INV-114** | La suite **no sale a la red**, y eso es un assert, no una convención. | P0 | **garantizado y medido** | #123. Fixture autouse `sin_red` en `conftest.py`. `tests/README.md` prometía *«sin red, sin binarios externos»* en prosa desde siempre y **nadie la sostenía**: medido con `cProfile`, cuatro tests hacían peticiones HTTP reales (OpenAlex, Unpaywall, arXiv, SIMBAD) y pasaban en verde. ⚠ Las dos mitades del fixture hacen falta: levantar la excepción sola no alcanza, porque el código de producción degrada limpio ante un backend caído —conducta correcta allá— y se traga la guardia; por eso el intento se **registra** y se chequea al cerrar el test, la atrape quien la atrape. Efecto colateral medido: el tier 0 pasó de **9,5 s a 6,7 s** (su techo es 10 s). Del mismo hallazgo sale que la cadena no consulte dos APIs por una fuente `pending: adquisicion`, donde no hay copia libre que buscar. (`tests/test_ingest_theme.py::test_adquisicion_no_sale_a_la_red_a_buscar_lo_que_ya_conseguis_vos`) |

| **INV-115** | La ficha dice **de qué trata** cada paper que linkea, no sólo su bibcode. | P2 | **garantizado y medido** | #125. Columna `Título` en el roll-up `## Papers`. Un core `sin extraer` no es basura —su `.txt` participa de todo `grep` del corpus— pero desde la ficha no había forma de saber si servía sin abrir la nota, **una por una**: 25 papers en un caso real. El título se trunca y se escapa el `|`, que es el defecto que INV-99 arregló en el bloque de verificación. (`tests/test_make_notes.py::test_la_tabla_de_papers_lleva_el_titulo`) |
| **INV-116** | En un tema de método consta **por qué puerta** entró cada paper core, no sólo que entró. | P1 | **garantizado y medido** | #126. `query_ads.puertas_abiertas` + el campo `puertas` que estampa `reclassify_for_theme`. Las dos puertas de D-26 se computaban por separado y al entrar el paper se devolvía `(facets, True, None)`: **se perdía cuál abrió**, así que la bóveda podía decir por qué un paper quedó afuera (`why_excluded`) y no por qué está adentro. Es la única metadata que distingue **sin leer el paper** un fundamento de su campo de una aplicación astro — y `role` no sirve, porque lo puebla la extracción, o sea después de leer, y esta decisión se toma antes: es la que dice qué se lee. Habilita curar por **política** (`triage --prioridad` agrupa: «12 sólo fundacionales, 20 sólo astro, 5 por las dos») en vez de paper por paper. Lista vacía = no es core; el campo existe siempre, así que «no consta» y «ninguna puerta» no se confunden. La regla quedó en **un solo lugar** (`_facet_propia` + `_texto_clasificable`, compartidos por los dos caminos): dos copias de la misma regla es donde vive el bug (regla de método nº 2). (`tests/test_query_ads.py::test_la_puerta_que_admitio_al_paper_queda_registrada`, `tests/test_query_ads.py::test_la_puerta_viaja_en_el_registro_del_paper`, `tests/test_triage.py::test_prioridad_agrupa_por_puerta_en_un_tema`) |

| **INV-117** | Un veredicto de verificación que exige acción **no puede quedar registrado y sin resolver**. | P0 | **garantizado y medido** | #91. `lib_blocks.resueltos` + el detector bloqueante del lint. El lint leía el bloque `## Verificación de citas` **sólo por su encabezado** —¿existe (cobertura)? ¿está fresco (stale)?— y nunca su contenido: la columna `Veredicto` no la miraba nadie, así que una fila `no-soportada` pasaba limpia, sentada bajo un encabezado que se lee como garantía. Eso es una afirmación que la bóveda hace y que **su propia fuente no respalda**, que es exactamente lo que la frontera dura prohíbe — mismo trato que citar una fuente retractada. El contrato ya mandaba **resolver** cada falla (bajar la afirmación a lo que dice la fuente, reasignar la cita, marcar `inferencia`, o taguear la disputa); lo que faltaba era el detector. `no verificable por extracción` NO cuenta: es una propiedad de la fuente, no un defecto de la nota; y la anotación de la resolución en la misma celda (`no-soportada→corregida`) tampoco, porque lo que bloquea es el veredicto **pelado**. (`tests/test_lint.py::test_veredicto_sin_resolver_en_el_bloque_bloquea`, `tests/test_lint.py::test_contradice_tambien_cuenta_y_soportada_no`) |

| **INV-118** | El barrido full-text deja **rastro versionado**, se haya encontrado algo o no. | P1 | **garantizado y medido** | #88. `cfg.save_barrido` (acumulativo como `busquedas`, D-28) + el detector de *barrido sin rastro* en el lint. `--sweep` era un **preview puro de stdout**: cuando la terminal scrollea no queda nada. Es el mismo modo de falla que #55 cerró para el triage, y acá pesa más porque el barrido es **el único camino** para el punto ciego de la query directa — los surveys de muestra grande que TABULAN la estrella sin nombrarla en el abstract y que además no están en el grafo de citas. Sin registro no se sabía si esa segunda red se había tendido. ⚠ Se registra **también cuando no encontró nada**: un barrido vacío dice que la red se tendió y volvió sin nada, que no es lo mismo que no haberlo corrido (D-43). (`tests/test_query_ads.py::test_el_sweep_queda_en_el_registro`, `tests/test_query_ads.py::test_el_sweep_sin_hallazgos_tambien_deja_rastro`, `tests/test_lint.py::test_el_barrido_sin_rastro_se_reporta`) |

| **INV-119** | La lente del **buscador** sale del objetivo, no del código. | P1 | **garantizado y medido** | #85. `query_ads.search_fq` lee `relevance.search_fq`. El `fq` de Solr acota el universo **server-side, antes de traer nada**: es la mitad **más restrictiva** del filtro —`relevance.facets` decide qué es core dentro de lo ya traído— y era la única que no salía de `objective.yaml`, con todo el resto de la lente (`facets`, `require`, `min_facets`, `noise_doctypes`, `concept_areas`) sí saliendo de ahí. Bloqueaba el caso que el framework declara soportar: los métodos de otras disciplinas cuya bibliografía canónica ADS no clasifica como astronomía. Tres estados y no dos (D-43): sin declarar → el default astro; con valor → ése; `null` declarado → **no acota**, que es una decisión y no puede leerse como «no lo declaró». Un centinela distingue en `query_ads` «no pasaron `fq`» de «pasaron `None` a propósito» (el universo ya lo fijó el usuario con bibcodes). (`tests/test_query_ads.py::test_el_fq_del_buscador_sale_del_objetivo`, `tests/test_query_ads.py::test_sin_declarar_el_fq_sigue_siendo_astro`, `tests/test_query_ads.py::test_fq_nulo_explicito_no_acota_nada`) |

| **INV-120** | Toda lista rankeada por citas usa la **misma** política, y esa política no sesga contra lo reciente. | P2 | **garantizado y medido** | #79. `lib_config.sort_by_citation_rate` (citas/año, determinista) en los **tres** rankings client-side —barrido `--sweep`, apéndice de excluidos y listado del triage, el último que quedaba con cuenta cruda—, y `RECENT_SORT` para la única fuga server-side (la segunda pasada por fecha bajo truncamiento). La cuenta de citas está sesgada por la **edad** —*ageing bias*: el viejo tuvo más tiempo de acumularlas— y en el triage eso pesa especialmente, porque ahí se decide qué **entra** al corpus. Que fueran tres `sort(key=…)` inline en archivos distintos era la garantía de que cambiar uno dejara los otros viejos sin que nadie lo notara. ⚠ La política se eligió **declarando su límite**: citas/año también sesga, al revés (un paper de dos meses con 1 cita tiene tasa enorme); el estándar bibliométrico normaliza por cohorte de año. Se toma citas/año porque es simple y auditable, no porque sea insesgada. (`tests/test_triage.py::test_el_listado_del_triage_ordena_por_tasa_no_por_citas_crudas`) |

| **INV-121** | El descubrimiento **fuera de ADS** deja registro: qué backends corrieron, cuáles fallaron y cuáles no corrieron. | P1 | **garantizado y medido** | #77. `cfg.save_descubrimiento`, appendeado por la cascada de `discover`. Los backends existían desde 1.45.0 y su resultado **moría en stdout**: un tema off-ADS no podía responder «sobre qué universo afirma esta nota y con qué se buscó», que es lo que D-28/`busquedas` sí garantiza para un tema ADS. ⚠ Lo que se guarda es la **cobertura por backend** con sus tres estados —corrió con N · FALLÓ · NO CORRIÓ y por qué—, no un total: un backend caído (0 por timeout) y uno que corrió y no trajo nada se leen igual en una suma, y esa distinción es la que hace honesta —o no— la frase «los tres miraron y esto es todo lo que hay». (`tests/test_discover.py::test_la_cascada_registra_su_corrida`) |

| **INV-122** | Los alias de una estrella salen de **SIMBAD**, no de la memoria del LLM — en los dos sentidos. | P1 | **garantizado y medido** | #82. `fetch_ground_truth.simbad_identifiers` persiste `_simbad_aliases` en el ground-truth y el lint reporta los que `stars.yaml` no declara. Cierra el lado **de menos**, que es el que el skill nombra —*«un alias que falta es un paper que nunca aparece, en silencio»*— y que degrada los **tres** mecanismos de recall a la vez: query directa, barrido `--sweep` y rescate por glifo. El lado **de más** ya estaba (`unresolved_aliases`, medido: `HR 2102` declarado para HD 40307 es en realidad 36 Dor). La llamada es la misma (`query_objectids`), así que persistir la lista es gratis. ⛔ Persistir **no es adoptar**: SIMBAD devuelve identificadores inútiles para buscar texto (Gaia DR3, 2MASS J…) junto a los que sirven, así que cuáles entran es curación humana y se versiona. `None` ≠ `[]`: una caída de red no puede leerse como «no hay más identificadores». (`tests/test_fetch_ground_truth.py::test_los_identificadores_de_simbad_quedan_en_el_ground_truth`, `tests/test_fetch_ground_truth.py::test_sin_respuesta_de_simbad_es_None_y_no_lista_vacia`, `tests/test_lint.py::test_alias_que_simbad_conoce_y_la_boveda_no`) |

| **INV-123** | Una config que declara bibliografía que el modo elegido **no procesa** frena la cadena; no la descarta con un aviso. | P1 | **garantizado y medido** | #78. `source: ads` con `sources:` poblada avisaba y **seguía**, o sea descartaba bibliografía declarada por el usuario — y el fundamento canónico de un método casi nunca está en ADS, que es justamente lo que esa lista existe para traer. Un aviso que no frena se pierde en el scroll y la cadena cierra «bien» con la mitad de la bibliografía afuera. Hoy aborta nombrando el `source:` que sí la procesa. ⚠ No hacía falta una feature: desde #104 un tema off-ADS con `query:` poblada corre el descubrimiento ADS **completo** (misma lente, mismas puertas de D-26, misma compuerta de triage), así que el tema mixto ya funcionaba — lo que faltaba era que el modo equivocado dejara de tragarse la lista. (`tests/test_ingest_theme.py::test_source_ads_con_sources_declaradas_aborta_diciendo_qué_poner`, `tests/test_ingest_theme.py::test_source_ads_sin_sources_sigue_andando`) |

| **INV-124** | La lente no queda limitada a lo que el usuario supo nombrar: el corpus **propone** las facetas que faltan. | P2 | **garantizado y medido** | #83. `query_ads.propose_facets` (minado en el `--probe`) + el turno de propuesta en el paso 1 del skill `setup`. La asimetría de información estaba al revés: el usuario conoce su foco, pero **el agente es el que tiene el corpus delante** — y el skill sólo preguntaba y traducía. La señal es determinista y ya está en los datos: los términos que se repiten entre los **no-core** y que ninguna faceta matchea, tomados de las `keywords` que ADS devuelve (D-17), o sea el único vocabulario de la bóveda que no sale de una regex nuestra ni de la memoria de un LLM. ⛔ Propone, **no edita**. Y distingue dos arreglos que el skill trataba como el mismo: una **faceta nueva** cambia la ESTRUCTURA de la lente (y con ella el efecto de `require`/`min_facets`); un **sinónimo** sólo mueve el recall de una faceta que ya existe. Un término frecuente que **sí** matchea una faceta no se propone: ese paper cayó por otra razón (doctype, `require`, `min_facets`) y proponerlo mandaría a agregar lo que ya está. Importa porque el costo de una faceta faltante es **asimétrico**: lo que la lente descarta no se baja, así que el falso negativo no deja rastro. (`tests/test_query_ads.py::test_el_probe_propone_facetas_desde_los_no_core`, `tests/test_query_ads.py::test_no_propone_lo_que_una_faceta_ya_cubre`) |

| **INV-125** | Un desacuerdo ya juzgado **como no-disputa** no se vuelve a juzgar: el veredicto se persiste con su motivo. | P2 | **garantizado y medido** | #63. `cfg.par_key` / `save_no_disputa` / `load_no_disputas`, en el registro versionado (`no_disputas: []`). El fan-out de `find-contradictions` es caro —un subagente por par, leyendo **dos** fulltext— y los veredictos `aparente` vivían sólo en el chat de esa corrida: cada auditoría sobre el mismo eje volvía a gastar en los mismos pares y a proponer lo que el usuario ya había rechazado, que es cómo una auditoría repetible se vuelve una que nadie repite. La clave del par es **simétrica** y distingue el **eje**: dos papers pueden coincidir en un eje y no en otro. `motivo` vacío y `veredicto` fuera del vocabulario cerrado —`real` incluido, porque su carril es `disputes`— levantan `RuntimeError` antes de tocar el registro. Re-juzgar el mismo par **appendea** y gana el último: el registro es historial, y borrar el juicio viejo perdería por qué se pensó distinto. (`tests/test_lib_config.py::test_par_key_es_simetrica_y_distingue_el_eje`, `tests/test_lib_config.py::test_no_disputa_sin_motivo_aborta`, `tests/test_lib_config.py::test_un_veredicto_real_no_entra_al_carril_de_no_disputas`) |
| **INV-126** | Ningún test escribe en la bóveda **real**, y eso es un assert. | P0 | **garantizado y medido** | Fixture autouse `sin_tocar_la_boveda_real`, hermana de la de red (INV-114) y por el mismo motivo: `tests/README.md` promete desde siempre que «ningún test lee ni escribe la bóveda real» y **nadie lo sostenía**. **Medido el 2026-08-26**: al cablear #77, tres tests preexistentes de `discover` que no usan `toy_vault` empezaron a crear `vault/config/registro/ica.yaml` en **cada corrida de la suite**. En el repo template se ve; en una instancia appendearía una entrada falsa al **único artefacto no regenerable** de la bóveda (INV-53), sin que nada avise. Es barato porque el repo tiene **un solo writer** (D-53/INV-90): basta interceptarlo. Lo encontró el agente de tests del lote de skills, corriendo un tier que la tanda que introdujo el defecto no había corrido. (`tests/conftest.py::sin_tocar_la_boveda_real`) |
| **INV-127** | Sacar un paper de un sujeto puede borrar sus artefactos de `raw/`, y eso está **declarado**: la decisión queda versionada con motivo y el paper sigue **visible** en el registro. | P1 | **garantizado y medido** | Enunciado el 2026-08-27 (issue #159, AUD-87). INV-20 declara `raw/` inmutable *salvo mejora declarada o borrado explícito de la ENTIDAD*, y `triage.drop_core` (#112) borra PDF y `.txt` con la entidad viva: el código hacía lo contrario de lo que el contrato decía y no había dónde discutir el alcance. La excepción es correcta y por qué: si el artefacto queda, el detector de #108 lo reporta como extracción pagada sin nota **para siempre** y el `.txt` sigue saliendo en los greps del corpus. Lo que la hace admisible es que **el juicio no se borra** — queda en `decisiones` con `origen: sujeto`, motivo obligatorio y fecha— y que el paper sigue apareciendo con `via: manual-drop` en `why_excluded`, así que en tres meses no se lee como «la búsqueda nunca lo encontró». El carril es el PAR `(paper, sujeto)`, no global: lo que se saca de un tema por polisemia puede ser core de otro. Medido por `tests/test_triage.py::test_drop_core_registra_con_carril_sujeto_y_borra_artefactos`, `::test_drop_core_exige_motivo`, `::test_drop_core_no_borra_la_nota_de_otro_sujeto`, y —desde #132— `::test_drop_core_avisa_de_los_wikilinks_que_deja_rotos`. |
| **INV-128** | Una marca en línea que **degrada** un hallazgo está enunciada, se evalúa **por ocurrencia** y nunca borra la afirmación. | P1 | **garantizado y medido** | Enunciado el 2026-08-27 (issue #159, AUD-88). Las tres marcas del sistema —`(inferencia de [[bibcode]])`, `[[bibcode]] ⛔retractada`, `<valor> ⚠desactualizado`— hacen lo mismo: convierten un bloqueante en algo visible en vez de destruir la afirmación (D-47). Dos tenían invariante (INV-86, INV-93) y `⚠desactualizado` **no**, con lo cual una escotilla que apaga un hallazgo no se podía auditar ni ajustar. **Por ocurrencia** es la mitad que faltaba y que #131 midió: el chequeo era `MARK in texto`, a nivel ARCHIVO, así que **una** marca silenciaba todos los `_cambios` de la estrella — un falso limpio sobre prosa que sigue citando un número que NEA retiró. Su gemela `⛔retractada` siempre se evaluó por ocurrencia. `tests/test_lint.py::test_la_marca_de_ground_truth_se_evalua_POR_CAMPO`, `::test_ground_truth_cambiado_pide_la_marca_y_con_la_marca_baja`. |
| **INV-129** | En los **cuatro cuadrantes** de la curación (aceptar/descartar × ADS/off-ADS) queda registrado **quién** y **por qué**, con vocabulario cerrado, y el que falta bloquea. | P1 | **garantizado y medido** | Enunciado el 2026-08-27 (issue #159, AUD-89). `CLAUDE.md` publica la tabla de los cuatro cuadrantes y el contrato sólo cubría el **descarte** (INV-48: motivo y fecha) y el *origen* (INV-60). La categoría bloqueante `bad_sources` exige `via` **y** `motivo` en cada item de `sources:` —el lado **aceptado** del carril off-ADS— y ningún invariante lo pedía: un gate que frena al usuario por un campo que el contrato no declara obligatorio. Ese cuadrante es justamente el que más lo necesita: en off-ADS **no hay query que descubra**, así que todo entra por decisión de alguien y sin el campo la pregunta *«¿qué pidió el usuario, qué propuso el descubrimiento, qué vino de un reporte?»* no tiene respuesta (medido: 40 papers, los 40 a mano, sin forma de saber cuáles). ⚠ Los dos `via` son vocabularios **distintos** (#162): `extra_core` usa `usuario | triage | citado-por-corpus`; `sources:` usa `usuario | descubrimiento | reporte`. `tests/test_lint.py` (categoría `bad_sources`), `lib_config.load_extra_core`. |
| **INV-130** | Un **límite de descubrimiento** —truncamiento, tope, muestreo— se persiste; no vive sólo en el stdout de la corrida. | P1 | **parcial** (ADS medido; la cascada no-ADS, no) | Enunciado el 2026-08-27 (issue #159, AUD-91). INV-52 lo garantiza para la búsqueda ADS (`truncated`/`truncated_glyph` persistidos, el lint los reporta) y **no** para la cascada de `discover.py`: el aviso de `seed_terms` (*«el slice tiene N y se trajeron M»*) sale por `print_seguro` y nada más — no entra en `cobertura` ni en `descubrimientos:` del registro. Es el mismo modo de falla que #55 cerró para el triage y #88 para el barrido: lo que queda en la terminal se pierde al scrollear, y el resultado se lee como *«esto es todo lo que hay»*. El propio docstring de `seed_terms` dice *what is not affordable is a cap that hides its own effect*. **Lo que falta**: persistir el truncamiento por término en `descubrimientos:`. |
| **INV-131** | El **paso salteable que escribe el LLM** —la bitácora `wiki/log.md`— tiene chequeo, igual que los que escribe un script. | P2 | **garantizado y medido** | Enunciado el 2026-08-27 (issue #159, AUD-92). INV-44 da la doctrina (*para cada paso salteable existe un chequeo*) y INV-91 cubre la traza **estructurada** del registro (`cadena`), que es otra población: *lo que escribe un SCRIPT se registra solo; lo que escribe el LLM depende de que se acuerde*. La categoría `log_sin_entrada` (#118) compara `cadena` contra `vault/wiki/log.md` y nombra slugs y fechas, y era el único detector en producción sin nada contra qué validarse (`grep -c 'log\.md' docs/contrato.md` → 0). Backlog, no bloqueante: la nota no es inválida. |
| **INV-132** | Un eje de descubrimiento **documentado y medido** es ejercitable desde alguna entrada de usuario, o su estado se declara. | P2 | **parcial** (declarado, no cerrado) | Enunciado el 2026-08-27 (issue #159, AUD-93). Es la generalización de lo que AUD-33 dejó declarado para `search_arxiv` en INV-96. Hoy `discover.seed_terms` —el eje que la doc mide como el que lleva la recuperación de **7/18 a 13/18**— no tiene bandera: `_preview_theme` llama a `cascade` sin él y `main` no lo expone. `grep -rn 'term_slices' scripts/ tests/ docs/ .claude/` → cero llamadores fuera de tests. Una capacidad medida e inalcanzable se lee como vigente. ⚠ La mitad **documental** del hallazgo se cerró el 2026-08-27 (pasada de coherencia doc↔código): el docstring de `cascade` justificaba el default con *«217 candidates, recovered 1 of 18»*, número que un comentario de **la misma función** retractaba 50 líneas abajo como artefacto de un tope de 15 filas; hoy publica el par vigente (7/18 → 13/18, 776 → 2521) y declara el número retractado como tal. **Lo que falta**: exponer el eje (bandera) o declararlo experimental como se hizo con `search_arxiv`. |
| **INV-133** | El mapa requisito↔código distingue **«no hay implementación»** de **«hay y no está marcada»**. | P2 | **HUECO** (enunciado, sin implementar) | Enunciado el 2026-08-27 (issue #160, AUD-94). La columna `Implementa` usa `—` para las dos cosas y hoy son **24 de 126**, varias con implementación real y localizable: INV-108 se implementa en `ingest_theme.py` (`if _pend not in cfg.PENDING_OK: sys.exit(...)`) y en `lint.py`, sin ninguna marca; ídem INV-109. Un lector que usa esa columna para responder *«¿dónde vive esta garantía?»* recibe `—` sobre código que existe — la regla de método #4 (*un mapa que atribuye mal es peor que uno vacío*) aplicada a la ausencia. Además, el número *«con implementación marcada»* se imprime **sólo dentro del artefacto** y no en el `rc`: no tiene techo ni gate, a diferencia de `sin_marca`/`sin_test`. **Lo que falta**: un estado explícito (`sin marcar` vs `sin implementación`) y su ratchet. No se cierra parcheando el recolector: hace falta decidir cómo se declara la diferencia. |
| **INV-134** | Una extracción declara **desde qué sujeto** se leyó el paper; el silencio de una nota sobre un eje no se puede leer como «se miró y no hay nada». | P1 | **garantizado** (sin corpus migrado que lo mida) | Enunciado el 2026-08-27 (issue #188). El prompt nunca pregunta *«¿qué dice este paper?»* sino *«¿qué dice **sobre {name}**?»*, con los `grep` armados desde los alias de ese sujeto y los bullets ramificados por tipo (#76) — pero la nota es UNA por bibcode con una sola `## Extracción (LLM)` sin scope. Medido en una instancia real: **141 de 908** notas las reclaman 2+ sujetos y **ninguna** tiene una segunda extracción; `ingest-theme` lo produce por diseño en su paso 3b (retro-tag por grep, que corre DESPUÉS de la extracción). Es la misma familia que D-34 en las hipótesis (*«no hay evidencia» no es «no existe evidencia»*) y que la cobertura de `discover` (*corrió con N* vs *NO CORRIÓ*). Hoy: `cfg.load_vistas` / `cfg.load_no_vista` (forma dura, vocabulario cerrado `star|theme`, escotilla con motivo obligatorio) y **cinco** categorías del lint — el schema viejo y la incoherencia `vistas[]`↔cuerpo **bloquean**; el reclamo no leído y la **vista sin `fecha`** (declarada por el stub y nunca hecha) son backlog, y el reclamo declarado con `no_vista` es informativo. La cadena las **escribe**: `make_notes.vista_block` siembra la sección y la vista pendiente (sin `fecha`, que es lo que dice que la lectura ocurrió), `extraction_prompt` pide la vista de un sujeto y `harvest_views` la estampa con `fecha`/`txt`/`lente`. **Medido sobre un corpus real**: la única bóveda que había que migrar (177 notas) quedó migrada y con el lint en verde — la categoría bloqueante pasó de 177 a 0. El migrador era de **un solo uso** y se borró al terminar, que es lo que la regla de schema nuevo dice que es: derivaba `sujeto`/`tipo`/`txt` del `fulltext:` y **marcaba los ambiguos en vez de elegir** — decisión que se pagó sola, porque en las 9 ambiguas el `fulltext:` apuntaba a un slug y **4 eran lecturas de otro sujeto**. El detector **queda**: sin él una nota con el schema viejo se lee como si tuviera vistas, y la salida escrita es declarar la vista a mano o rehacer la bóveda. (`tests/test_lint.py::test_schema_viejo_sin_vistas_es_bloqueante`, `tests/test_lint.py::test_vista_declarada_sin_su_seccion_es_bloqueante`, `tests/test_lint.py::test_reclamo_sin_vista_es_backlog_y_nombra_al_sujeto`, `tests/test_lint.py::test_vista_declarada_sin_fecha_es_backlog`, `tests/test_lib_config.py::test_load_vistas_forma_canonica`) |
| **INV-135** | Dos copias del mismo `.txt` bajo slugs distintos **coinciden byte a byte, o el desacuerdo se reporta**: nunca se elige una en silencio. | P1 | **garantizado** (cero en una bóveda sana, que es la señal de que está bien puesto) | Enunciado el 2026-08-27 (issue #190). D-18 copia el artefacto a cada slug que lo reclama y `raw/` es inmutable, así que las copias no derivan solas — medido: **672 `.txt` para 639 bibcodes, 30 duplicados, los 30 idénticos**. Pero `extract_fulltext` reescribe el `.txt` en **tres** casos (`--force`, el upgrade automático a OCR, el backfill de marcas) y **ninguno propaga a las otras copias**: la divergencia no viene de deriva sino de que alguien re-extrajo bajo un slug y no bajo el otro. Es la premisa que INV-78 da por cierta —*«el `.txt` leído»* supone que hay uno solo—: el ancla hashea **una** copia (`ft_hash.setdefault`, «gana la primera alfabética»), así que los pares verificados contra las demás se comparan contra un archivo que nunca leyeron, y con `vistas[]` (#188) eso deja de ser hipotético porque la vista declara de qué copia salió. `lint.diverged_copies`, **bloqueante** y sin I/O extra: el bucle que ya leía los `.txt` acumula en vez de descartar con `setdefault`. ⛔ Se **compara, no se sincroniza**: copiar la copia «buena» sobre las otras taparía que alguien re-extrajo medio corpus. (`tests/test_lint.py::test_mismo_bibcode_con_txt_distinto_entre_slugs_es_hallazgo`, `::test_dos_copias_identicas_no_son_hallazgo`, `::test_el_chequeo_de_divergencia_no_agrega_ni_una_lectura`) |

### F. El registro: lo que no es regenerable tiene que viajar

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-48** | Los **dos** lados del juicio de curación —aceptado y descartado— persisten en config versionada, cada descarte con motivo y fecha. | P0 | **garantizado y medido** | El descarte sobrevive y se lista con su motivo aun sin `build/` (8ª F1 #43); `--reason` es obligatorio (exit 2 de argparse sin él); el lugar viejo (`build/<slug>/triage.json`) **bloquea** mientras exista (F4 §2). |
| **INV-49** | Una fuente descartada no se descarga, no se convierte en nota y no vuelve a la cola, mientras el descarte esté vigente. Vale para **todos** los carriles. | P0 | **parcial** (medido, con la brecha nombrada) | Ver §4.INC-2. El camino normal lo honra (`query_ads.load_triage` → `cfg.load_decisiones`, *"decisión persistida: no re-proponer"*) y el carril off-ADS avisa por clave **y por url** sin frenar (8ª F1 #12). Pero `--no-triage` ponía `gate=False` → `descartados = set()` (en `query_ads.main`): los descartes persistidos **se resucitan y se bajan**, sin aviso. **Cerrado por D-48 (1.26.0)**: el flag que lo incumplía ya no existe (`tests/test_query_ads.py::test_no_triage_ya_no_existe`, `::test_la_compuerta_no_se_puede_apagar`) y los dos carriles tienen test (`tests/test_ingest_theme.py::test_offads_avisa_si_la_fuente_estaba_descartada`). **Brecha declarada**: en el carril *tema* el gate no aplica (`gate=False` ⇒ `descartados=set()`), así que un descarte de chaining de un tema sí se re-propone — es deliberado y está fijado en `tests/test_query_ads.py::test_main_tema_no_aplica_la_compuerta`, pero contradice el «todos los carriles» del enunciado. |
| **INV-50** | Lo que entra por un camino de baja precisión no se descarga hasta que hay juicio. La compuerta es efectiva, no un aviso. | P0 | **garantizado y medido** | `candidates` es una clave propia de `ads.json` y **todos** los consumidores leen `data["records"]`: `fetch_arxiv:119`, `fetch_pdf:238`, `make_notes:1186` (8ª F1 #11). ⚠ **Actualizado 2026-08-24**: la escotilla `--no-triage` que esta fila describía **se eliminó** en D-48/1.26.0 (`tests/test_query_ads.py::test_no_triage_ya_no_existe` asserta que argparse sale 2), en línea con lo que ya dicen INV-44 e INV-49. Lo que sigue sin test es el lado consumidor: nadie fija que `fetch_pdf`/`fetch_arxiv`/`make_notes` lean sólo `records` y no `candidates`. |
| **INV-51** | Cada corrida de búsqueda cierra registrando consulta efectiva, fecha, límite, conteos del embudo, **la lente vigente con su regla de combinación**, y la versión del framework. | P1 | **garantizado y medido** | Verificado por lectura hoy: `query_ads.main` (el bloque de `cfg.save_busqueda`) escribe `fecha, query, rows, n_found, n_total, n_core, n_candidates, n_dropped, truncated, almagesto_version` y `lente: {facets, require, min_facets, noise_doctypes}`. **Falta** la prueba de uso: cambiar un patrón, re-correr, y comprobar que el registro explica la diferencia de corte sin adivinar. **Al día 2026-08-24**: `tests/test_query_ads.py::test_main_persiste_el_registro_de_busqueda` asserta `query`, `n_found`, `n_core`, `n_dropped`, `almagesto_version` y `lente.{facets,require,min_facets}`. Falta la prueba de **uso** (dos lentes que difieren en un patrón ⇒ el registro explica el delta), que es la de INV-55. |
| **INV-52** | Si la búsqueda no trajo todo lo que el servicio reporta, queda marcado y se surface. Nunca implícito que el universo esté completo. | P0 | **garantizado y medido** | `truncated_corpora` sembrada (8ª F4 §2); la marca se persiste con `num_found`/`rows`/`recent` y la 2ª pasada por fecha corre con la misma `q` y `sort=date desc` (8ª F1 #21, con `requests` mockeado). |
| **INV-53** | Escribir un registro nuevo no borra el juicio ya registrado, y la historia es reconstruible. | P1 | **garantizado y medido** | `save_busqueda` preserva `decisiones` (`lib_config.save_busqueda`) y desde 1.35.0 **pliega** la clave vieja `busqueda:` en vez de borrarla (`tests/test_lib_config.py::test_save_busqueda_pliega_la_clave_vieja_en_vez_de_borrarla`, `::test_save_busqueda_no_pliega_si_ya_hay_historial`): el `data.pop` destruía la única corrida que un registro pre-D-28 documenta, justo en el único artefacto no regenerable. `save_registro` es atómico y **rehúsa escribir** sobre un registro existente que no parsea, con bytes intactos y sin `.tmp` residual (8ª F1 #14, F4 G3.1/G3.2). |
| **INV-54** | Migrar el formato del registro no pierde juicio, resuelve conflictos por regla declarada y es idempotente. Mientras quede juicio en el lugar viejo, bloquea. | P0 | **garantizado y medido** | Ante el mismo bibcode gana lo ya versionado; `triage.json` consumido; 2ª corrida no-op; con la clave `decisiones` ausente **no** borra (exit 1 + mensaje) — 8ª F1 #13, F4 G1.7. |

### G. Configuración: la lente

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-55** | El criterio de relevancia vive enteramente en config versionada. No hay regla de admisión hardcodeada que la contradiga o complemente. | P1 | garantizado sin medir | Verificado por lectura hoy: incluso el filtro de ruido es configurable (`relevance.noise_doctypes` → `query_ads.NOISE_DOCTYPES`), y la regla de combinación es declarativa (`require`/`min_facets`, `:164-191`). **Falta**: dos configs que difieran en un solo patrón produciendo exactamente la diferencia esperada. |
| **INV-56** | Una configuración malformada aborta con error explícito **antes** de tocar el vault. Nunca se degrada a un default silencioso. | P0 | **garantizado y medido** | Ver §4.HUECO-1. Ruidoso donde alguien lo pensó: `require` escalar, faceta obligatoria inexistente, `objective.yaml` **ausente**, slug desconocido (todos con mensaje que nombra el campo). **Silencioso donde más duele**: un `objective.yaml` que no parsea degrada a `{}` (`cfg.load_objective`) → lente vacía, y el único chequeo del lint compara `name` contra el placeholder, así que **no dispara nada**. **Cerrado por D-6 (1.24.0)** y completado el 2026-08-24 con los otros dos YAML: `tests/test_lib_config.py::test_objective_error_distingue_los_tres_estados`, `tests/test_query_ads.py::test_query_ads_rehusa_lente_vacia` y `tests/test_lint.py::test_stars_yaml_roto_reporta_no_evaluado_en_vez_de_reventar`. |
| **INV-57** | Mientras la bóveda conserve el objetivo de ejemplo del template, se reporta. | P1 | **garantizado y medido** | WARN=1, exit 0 (8ª F1 #32, F4 §2). |
| **INV-58** | Es posible determinar sin adivinar si el corpus vigente fue clasificado con la lente actual, y qué papers cambiarían de lado. | P1 | **garantizado y medido** | La lente viaja en el registro (INV-51) y `query_ads --dry-run` es el preview de re-clasificación sobre `build/`: `requests` nunca invocado, árbol byte-idéntico (8ª F1 #27). D-49 agrega el carril **sin `build/`** (que es scratch gitignored: en otra máquina el chequeo no podía correr): `lens_stored` vs `lens_current` por sujeto, y `lens_diff_offline` re-clasifica desde las **notas** (título + abstract + `keywords`, D-17). El lint lo reporta como backlog, nombrando los stems. **Alcance declarado:** evalúa la mitad **textual** (`facets`/`require`/`min_facets`); la nota no guarda `doctype`, así que un cambio que sólo mueve `noise_doctypes` se declara *no evaluable* en vez de devolver `+0/−0`, y los papers del universo sin nota se publican como techo del chequeo. |
| **INV-59** | El preview muestra el corte sin bajar un archivo ni modificar config o vault. | P0 | **garantizado y medido** | `--dry-run` con `requests` que revienta si se lo llama: exit 0, nunca invocado, árbol byte a byte idéntico (8ª F1 #27). `--probe` es la misma familia (sin hash-test propio). |
| **INV-60** | Un forzado manual de relevancia persiste en config y se re-aplica en cada corrida, con su origen marcado. | P1 | **garantizado y medido** | `extra_core` vive en `stars.yaml`/`themes.yaml` y sobrevive: la instancia real conserva los 121 bibcodes del rescate por glifo con su comentario fechado (8ª F5). **Falta** comprobar que el resultado queda **marcado como manual** y no se confunde con un core clasificado. **Al día 2026-08-24**: `tests/test_query_ads.py::test_fetch_bibcodes_marca_manual` asserta `via == "manual"` y `make_notes.papers_universe` lo publica en la columna *Origen* de la tabla estampada. |
| **INV-61** | Una fuente declarada que no se consigue queda pendiente con su puntero, produce andamiaje mínimo, no cuenta como fallo y se surface como precondición. | P1 | **garantizado y medido** | `ingest_theme` avisa —no frena— por clave **y por url** ya descartada, exit 0 y la fuente se procesa igual (8ª F1 #12); `pending_srcs` sembrada como backlog (F4 §2). |

### H. Provenance, versionado y evolución del schema

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-62** | Cada nota declara con qué versión se generó, desde una única fuente de verdad, y una cirugía posterior no la reetiqueta. | P1 | **garantizado y medido** | `generator == ALMAGESTO_VERSION` (8ª F1 #1); `--restamp-headers` **lee** la versión del `generator` del frontmatter: `v1.11.0 → v1.11.0`, `v1.12.3 → v1.12.3`, sin `generator` → `vdesconocida` con el ancla (8ª F1 #16). |
| **INV-63** | Para cada tipo de nota hay un schema explícito y toda nota generada lo cumple; ningún campo se escribe con una forma que el chequeo no pueda recorrer. | P0 | **HUECO (parcial)** | Ver §4.HUECO-6. La mitad de "forma que evade" está cubierta y bloquea (`fm_broken`: YAML inválido, lista escrita como escalar, elementos que no son mapas). **No existe validador de campos requeridos por tipo de nota**: el schema vive en la prosa de `CLAUDE.md` y en chequeos ad-hoc campo por campo. |
| **INV-64** | Un cambio de schema entrega **dos** piezas: migración idempotente y detector bloqueante de la forma vieja. Nunca un lector que acepte ambas. | P0 | **garantizado y medido** (los 5 cambios, 1.35.0) | ⚠ Valía para **3 de 5**: `topics:`→`facets:` y `busqueda:`→`busquedas:` tenían detector bloqueante y **ningún migrador** — los mensajes del lint mandaban a renombrar a mano (medido: 908/908 notas de una instancia) o a re-correr la cadena, que cuesta una pasada de red **y pierde la corrida vieja**. Los dos entraron: `make_notes.py --migrate-facets` y `--migrate-registros` (`tests/test_make_notes.py::test_migrate_facets_renombra_y_es_idempotente`, `::test_migrate_facets_no_pisa_un_facets_existente`, `::test_migrate_registros_pliega_sin_perder_la_corrida`). Ciclo completo medido: vintage 1.11.0 → 4 migradores → los 4 conteos del lint a **exactamente 0** → 2ª pasada byte-idéntica (8ª F4 G5.1-G5.3). Y el detector bloquea, no tolera (F1 #6, #13). |
| **INV-65** | Lo regenerable vive fuera del árbol de la bóveda y fuera del versionado. | P2 | **garantizado y medido** | `git status --porcelain` vacío antes y después de todas las familias (8ª F4); `.obsidian/` en la raíz da WARN (F1 #33); `build/`/`outputs/` gitignored. |
| **INV-66** | Ninguna ruta absoluta de la máquina llega a un archivo versionado; los punteros internos son relativos al repo. | P1 | garantizado sin medir | Medido del lado del código: 0 hits de `/home`/`/Users` en `scripts/`, y `cfg.ROOT` correcto ejecutando desde `/tmp` (8ª F1 #20). **Falta** el lado de los **artefactos**: grep de prefijos absolutos en `wiki/`, `config/registro/` y `themes.yaml` (salvo los campos declarados machine-local, `data_local`). |
| **INV-67** | La credencial no se escribe en ningún artefacto versionado, ni en notas, ni en registros, ni en la salida de ninguna corrida (mensajes de error incluidos). | P0 | garantizado sin medir | La mitad medida: `.gitignore:3` y **historial vacío en todas las ramas** (8ª F1 #17). **Falta la otra mitad**: setear un token reconocible, correr todo incluidos los caminos de error (credencial inválida, servicio caído), y buscar la cadena en el árbol y en toda la salida capturada. Es un P0 a medio medir. |
| **INV-68** | Ninguna corrida modifica archivos de framework en una instancia. | P2 | **garantizado y medido** | Clon efímero + merge sintético: los 7 archivos de instancia listados en `.gitattributes` quedan intactos y `CLAUDE.md` sí avanza (8ª F1 #19). Con la condición que la propia doc pone: **sin** `merge.ours.driver` configurado hay conflicto (no pisa, pero tampoco mergea). |

### I. Robustez frente al mundo exterior

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-69** | Un servicio caído, lento, con error, vacío o inesperado nunca produce metadata inventada, texto vacío válido, ni un registro que declare un universo que no se consultó. | P0 | **parcial** | Mecanismos presentes y leídos: `EmptyResultError` aborta la cadena en vez de persistir un `ads.json` vacío con exit 0 (`query_ads.EmptyResultError`, lanzada desde `query_ads.query_ads` y atajada en `main`); `requests.RequestException` atrapada en el barrido (`:935`); escritura atómica de PDFs con `except OSError` (8ª F4 G3.5/G3.6). **Falta** la matriz de inyección: timeout, 500, respuesta vacía, respuesta con campos faltantes, respuesta truncada — y auditar qué quedó escrito en cada caso. La deuda P0 más grande del contrato. **Muy avanzado respecto de lo que dice esta fila**: hay inyección de fallo por script para 429/retry, 5xx persistente, 403/404, `ConnectionError`, cero espurio, `numFound > rows` y PDF truncado (`tests/test_query_ads.py::test_query_ads_5xx_persistente_lanza`, `tests/test_fetch_ground_truth.py::test_nea_host_error_no_se_escribe_como_campo_muerto`, `tests/test_fetch_pdf.py::test_fetch_pdf_no_deja_pdf_truncado_en_el_destino`). **Falta**: la matriz sistemática (hoy son casos sueltos), el timeout, y auditar el disco tras el aborto. |
| **INV-70** | Si falta una herramienta externa necesaria se reporta explícitamente; nunca se produce un artefacto degradado que pase por "existe". | P1 | garantizado sin medir | Verificado por lectura hoy: `extract_fulltext.main` aborta con `RuntimeError` nombrando el paquete si falta `pdftotext`; el OCR es opt-in por instalación (`shutil.which` de tesseract+pdftoppm). **Falta** correrlo de verdad sin la herramienta. |
| **INV-71** | Metadata, resúmenes y contenido web nunca se interpretan como directivas ni se propagan sin escapar a lugares donde cambien de significado (YAML, nombres de archivo, rutas). | P1 | garantizado sin medir | El frontmatter se serializa con `yaml.safe_dump` (`make_notes.fm`) y las rutas con `safe_name`/`quote`; el caso `---` dentro de un escalar ya está cerrado (`frontmatter_span`). **Falta** el corpus adversario: títulos con dos puntos, comillas, saltos de línea, `../`, caracteres de control, texto que imita YAML. |
| **INV-72** | La resolución de identidades es determinista, documentada, no aumenta falsos positivos entre entidades con prefijo compartido, y su comportamiento está registrado con evidencia. | P1 | **garantizado y medido** | `GJ 71` no arrastra `GJ 710` con el parser oficial, y el `grep` textual sí (8ª F1 #3/#4, reproducido sobre el corpus real en F5). La expansión de espaciado y los lookalikes de letra griega están documentados con su evidencia fechada en `stars.yaml` (121 core recuperados, 2026-08-09). ⚠ **Corregido el 2026-08-24**: el contraejemplo del enunciado estaba **vivo** — `subject_in_title("A close encounter with GJ 710", ["GJ 71"])` devolvía `True` por containment pelado, y como es la auto-aceptación de nivel 0 metía el paper al corpus ajeno sin juicio humano. La evidencia que citaba esta fila era sobre `split_fm`, **otro camino**. Cerrado con frontera de dígito + `tests/test_query_ads.py::test_subject_in_title_no_matchea_por_prefijo_de_catalogo`. |

### J. Medición del propio error

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-73** | El material sintético del auto-benchmark nunca llega a `vault/`, ni transitoriamente ni si la corrida se interrumpe. | P0 | **garantizado y medido** | Hash de `vault/` intacto; único artefacto `build/verify_bench/bench.json` (8ª F1 #26). **Falta** el caso interrumpido a la mitad. |
| **INV-74** | Dada la misma semilla y el mismo corpus la siembra es idéntica; y quién juzga no tiene acceso a qué caso es falso. | P1 | **garantizado** (1.33.0, D-55) | Determinismo medido y ahora fijado por test sobre los **dos** archivos (`test_seed_extrae_siembra_y_es_determinista`). La ceguera pasó de instrucción a construcción: `seed` escribe `exam.json` (id neutro `p###` post-sort, sin `label` ni `n_real`/`n_seeded`) y `key.json` aparte (`test_exam_no_contiene_la_clave`); `score` cruza por id y rehúsa puntuar si no corresponden. **Residuo declarado** en §4.HUECO-8: el `claim` duplicado deja ver que uno de dos es falso —no cuál— a quien lea el examen entero; el fan-out no lo expone. |
| **INV-75** | El resultado de la medición se reporta atado a su condición (corpus, modelo, fecha, tamaño de muestra), nunca como cifra absoluta del framework. | P2 | garantizado sin medir | El `README.md` lo dice explícitamente (*"el número que da es el de **tu** bóveda"*). **Falta** confirmar que la salida de `bench_verify score` lo lleva encima, no sólo la doc. |

---

### K. Invariantes de la revisión con el usuario (2026-08-23)

> Nacen de la revisión de §6 hecha **con el usuario** el 2026-08-23 (57 decisiones, las «D-N» que
> este documento cita). Nacieron todos en **HUECO**: eran decisiones de diseño tomadas, sin
> mecanismo. Cada invariante enuncia acá lo que esa decisión exige; la bitácora de la revisión no se
> publica —es lenguaje interno de sesión— y **no hace falta para leer estas filas**: lo que el
> sistema garantiza está acá, no allá.
>
> **Estado al 2026-08-24** (tras las tandas 0–6, v1.24.0 → v1.30.0, la auditoría que las midió y la
> pasada `/auditar`): **14 garantizados y medidos · 1 garantizado · 2 parciales · 0 HUECO** sobre
> las 17 filas de la sección — §3.K quedó **sin ningún HUECO**. **INV-88 cerró con la Tanda 7** (v1.32.0) e **INV-86 con el issue 8.3**: los dieciséis
> invariantes que nacieron como decisiones de diseño tienen hoy mecanismo y medición. Cada
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
| **INV-79** | Una nota con citas sin verificar, o con pares cuya ancla no coincide, **no cierra** la operación que la tocó. En la pasada periódica, reporta. | P0 | **parcial** (la mitad determinista, medida) | `tests/test_lint.py::test_cierre_bloquea_periodica_reporta` mide las dos severidades del mismo detector y `::test_nota_verificada_no_marca_nada` el control de D-5. La otra mitad —que la operación *no cierre*— depende de que el skill corra `python scripts/lint.py --cierre`: está en los `SKILL.md` de cierre y **no es testeable como código**. Sí sería testeable que los skills lo invoquen (grep sobre `.claude/skills/`); hoy no lo está. |
| **INV-80** | Una config que no parsea **rehúsa** operar: el lint la reporta como bloqueante y el clasificador no corre con lente vacía. | P0 | **garantizado y medido** | `tests/test_lib_config.py::test_objective_error_distingue_los_tres_estados`, `tests/test_lint.py::test_lint_objective_roto_bloquea` y `tests/test_query_ads.py::test_query_ads_rehusa_lente_vacia` (grabador: `classify` no llega a correr). La batería cubre los **tres** YAML de config: `tests/test_lint.py::test_stars_yaml_roto_reporta_no_evaluado_en_vez_de_reventar` y `::test_themes_yaml_roto_tambien_reporta_no_evaluado` — antes `load_stars` propagaba el `ScannerError` y el lint moría con traceback. |
| **INV-81** | La ficha declara, **materializado y por paper**, su universo: origen (`lente`/`manual`), si se extrajo y si se sintetizó. Ningún contenido que el contrato promete depende de un plugin. | P0 | **garantizado y medido** (1.35.0) | La 1ª oración está medida: `tests/test_make_notes.py::test_conteo_del_encabezado_es_el_de_la_tabla` (adversario del «155 arriba de una síntesis de 8»), `::test_tabla_refleja_los_cuatro_estados`, `::test_la_tabla_estampada_no_se_cuenta_a_si_misma`. **La 2ª entró en 1.35.0**: los tres roll-ups de la ficha se estampan. `## Planetas` era el peor de los tres —sus cinco campos son ground-truth de NEA, la capa que el contrato vende como auditable, y el `.md` mostraba el CÓDIGO de la query— y `## Métodos aplicados a esta estrella` se parsea con `split_fm`, no con grep. Tests: `::test_planetas_se_estampa_no_es_dataview`, `::test_planetas_muestra_null_explicito` (un null de NEA es el estado correcto; una celda vacía se leería como «falta el dato»), `::test_metodos_se_estampa_con_el_recorte_correcto`, `::test_stamp_star_rollups_es_idempotente_y_no_toca_la_prosa`. **Efecto lateral que hubo que cerrar en el mismo commit**: las celdas de la tabla satisfacían el proxy «¿cada planeta se discute en prosa?», así que TODO planeta quedaba discutido en una ficha con cero líneas escritas — mismo falso limpio permanente que el bug del `[^*]*`, y esta vez introducido por la propia máquina (`lint.solo_prosa`, `tests/test_lint.py::test_la_tabla_estampada_de_planetas_no_cuenta_como_prosa`). |
| **INV-82** | Las tres fechas de una nota (búsqueda, síntesis, verificación) son distinguibles y pueden divergir sin que ninguna mienta. | P1 | **garantizado y medido** (1.35.0) | `tests/test_make_notes.py::test_refrescar_sin_reverificar_mueve_una_sola_fecha` mide que búsqueda y verificación divergen sin mentir. **La tercera entró en 1.35.0**: la de síntesis **se declara** (`cfg.save_sintesis`, CLI `triage.py --sintesis`) porque no se puede derivar — `git` fecha el ARCHIVO, así que una cirugía de cabecera contaría igual que reescribir el resumen, y fuera de un repo no da nada. `estado_line` la emite entre las otras dos: `::test_la_cabecera_lleva_las_tres_fechas` y `::test_refrescar_no_mueve_la_fecha_de_sintesis` (el efecto que el invariante existe para impedir: refrescar el corpus movía la de búsqueda y la ficha se leía como re-sintetizada). |
| **INV-83** | El ingest lee **todos** los core; lo que no se lea queda **declarado** con su motivo y visible en la lista de papers. | P0 | **parcial** (el canal ya está cableado) | `tests/test_lint.py::test_subconjunto_sin_declarar_reporta` / `::test_subconjunto_declarado_baja_a_backlog` miden el detector sobre `lib_config.save_extraccion`. Dos huecos (el (a) **cerrado** el 2026-08-24: `triage.py --extraccion todos|subconjunto` es el canal, y `--reason` es obligatorio con `subconjunto` porque el criterio es la pieza que más se va a leer — `tests/test_triage.py::test_extraccion_todos_declara_el_default`, `::test_extraccion_subconjunto_exige_criterio`, `::test_extraccion_no_pisa_las_decisiones`; el skill `ingest-star` lo nombra en su paso 3): (b) el criterio vive sólo en `registro/<slug>.yaml` y **la ficha no lo dice**; (c) el hallazgo es backlog, fuera de `n_block`, así que «sin declarar ⇒ no cierra» todavía no rige. |
| **INV-84** | La identidad de un paper es `doi`/`arxiv_id`. Un trabajo tiene **una sola** nota canónica; las demás versiones viven en `versions[]`. | P0 | **garantizado y medido** | `tests/test_make_notes.py::test_ciclo_preprint_publicado` (renombre + `versions[]` + reescritura de wikilinks + artefactos) y `::test_crear_segunda_nota_mismo_trabajo_rehusa` — ⚠ hasta el 2026-08-24 el primero **pasaba sobre una nota destruida**: `_set_lista_de_mapas` filtraba las cadenas vacías estructurales del split y fusionaba el `---` con la primera clave (`---bibcode: …`), así que `cfg.split_fm` devolvía `{}`; lo tapaba el helper `read_fm` de `conftest`, que parseaba con el `split("---")` que `frontmatter_span` prohíbe. Los dos arreglados (el helper delega en `split_fm`: red #3). Se sumó `::test_rename_paper_corre_sin_slug`, porque el guard de `slug` corría antes del despacho y **el comando que la doc publica** moría con exit 2; el bloqueo lo miden `tests/test_lint.py::test_dos_notas_mismo_arxiv_id_bloquean`, `::test_identidad_por_doi_tambien` y `::test_versions_no_cuenta_como_duplicado`. |
| **INV-85** | Una sola pasada de red cubre todo lo que cambia afuera (retracción, corrección, versión nueva, snapshot web, ground-truth, **conteo de citas de la puerta 2**) y **avisa con el diff antes de aplicar**. | P1 | **garantizado** (los 6 detectores; los 5 primeros en 1.35.0, el sexto en 1.46.0) | `scripts/sweep_external.py` unifica retracciones, correcciones, versiones y ground-truth; el «avisa con el diff antes de aplicar» lo mide `tests/test_fetch_ground_truth.py::test_nea_diff_reporta_y_no_aplica` (JSON byte-idéntico). **El quinto entró en 1.35.0**: `fetch_web.refresh` re-baja la URL del header del snapshot y compara el **cuerpo** (el header lleva `retrieved` y la versión del extractor, que cambian en cada corrida), sin escribir — `tests/test_sweep_external.py::test_sweep_web_detecta_el_cambio_y_no_escribe`, `::test_sweep_web_calla_si_la_pagina_no_cambio`, `::test_sweep_web_sin_source_url_es_fallido_no_limpio`, `::test_sweep_web_ignora_lo_que_no_es_snapshot_web`. **El sexto entró en 1.46.0** (#106): la puerta 2 de D-26 admite un paper por `citation_count`, que es metadata del paper —así que INV-24 se sostiene: el conteo vive en el frontmatter y el veredicto sigue siendo re-derivable offline— pero **cambia sola con el tiempo**, o sea que un paper podía volverse core sin que nadie editara ni el paper ni la regla. Era la única dependencia del mundo sin detector, y la respuesta es la misma que para las otras cinco: detectar, reportar, **no aplicar solo** (`sweep_external.sweep_citas`, `tests/test_sweep_external.py::test_pasada_cubre_los_seis_eventos`). Su **gemelo offline** es `lib_config.puerta2_cruces` (INV-98), que ve *«editaste el umbral»* donde éste ve *«el mundo se movió»*; los dos declaran su alcance, y `puerta2_cruces` devuelve además las notas **sin conteo** porque un `entran: 0` sobre notas que nadie pudo evaluar se lee como «no cambia nada». `::test_detector_no_implementado_no_aporta_un_cero` sigue midiendo la conducta *no evaluado* sobre un fallo sembrado. El skill `maintain` ya lo invoca como pasada periódica (sección F, con la tabla de los seis detectores). **Dos ceros inventados cerrados** (auditoría 2026-08-24): `sweep_retracciones` colapsaba el `rc 2` de `check_retractions` («no se miró») contra el `0` («limpio»), y `cubrio.append("versiones")`/`("ground-truth")` se ejecutaban **antes** de llamar al detector, cuyos fallos por ítem se tragan por diseño — con NEA o ADS caídos el registro versionado `_red.yaml` afirmaba haber mirado lo que no miró, y la próxima pasada lo tomaba como línea de base. Ahora los dos detectores devuelven `(hallazgos, fallidos)` y `cubrio` se escribe **después** y sólo si no hubo fallidos (`tests/test_sweep_external.py::test_retracciones_rc2_no_es_limpio`, `::test_ground_truth_con_nea_caida_no_dice_haber_cubierto`, `::test_versiones_con_ads_caido_no_dice_haber_cubierto`). |
| **INV-86** | Toda `inferencia` **nombra sus premisas** (≥1 bibcode). Sin premisas no es inferencia: es afirmación sin respaldo y no entra. | P0 | **garantizado y medido** | `tests/test_lint.py::test_inferencia_pelada_bloquea` (exit 1 y la nota nombrada), `::test_inferencia_con_premisas_pasa`, y el falso positivo obvio en `::test_la_palabra_inferencia_en_prosa_no_es_una_marca` («la inferencia bayesiana permite…» no dispara: la marca es la que va **entre paréntesis** al cierre de una afirmación). Más la regresión dirigida sobre `PROT_CITE` (`::test_prot_documentado_ya_no_acepta_inferencia_pelada`), que aceptaba la palabra suelta como respaldo del P_rot — o sea que una ficha podía declarar un período «documentado» sin una sola fuente. Cierra el sumidero: una afirmación `no-soportada` ya no sobrevive cambiándole la etiqueta. |
| **INV-87** | Un chequeo que no puede correr **reporta error**: nunca contribuye un cero al total. | P0 | **garantizado y medido** | `tests/test_lint.py::test_no_evaluado_no_contamina_conteos` (la categoría normal se **suprime** en vez de mostrar su `(0)` — el adversario del cero inventado) y `::test_lint_objective_roto_bloquea`; mismo contrato de rc 2 en `tests/test_check_retractions.py::test_errores_sin_retractados_exit_2` y `tests/test_sweep_external.py::test_detector_no_implementado_no_aporta_un_cero`. Sacar `not_evaluated` del exit **mata** `tests/test_lint.py::test_stale_sin_git_no_rompe`, que es el test que fija esa rama; `::test_lint_sin_git_reporta_no_evaluado` **sobrevive** a esa mutación porque su `rc != 0` lo sostiene otra categoría, así que mide el reporte y no el exit. La propiedad está medida — por el primero, no por el segundo. |
| **INV-88** | La relevancia de un tema de método es **propia del tema** y entra por tres puertas declaradas (lo cita el corpus / fundacional / lente astro). | P1 | **garantizado y medido** | Las tres puertas, cada una por separado: `tests/test_query_ads.py::test_puerta_2_el_fundacional_entra_sin_lente_astro` (el caso Hyvärinen — entra sin lente astro), `::test_puerta_3_la_lente_astro_global`, y `::test_puerta_1_propone_lo_que_el_corpus_cita_y_no_lo_clasifica`, que fija la resolución §4.3: la puerta 1 **propone y no clasifica**, así que INV-24 queda intacto. El control del otro lado —`::test_faceta_propia_sola_no_alcanza`— cubre los miles de papers de fMRI que la faceta propia sola dejaría entrar. Cableado medido por integración (`::test_main_aplica_la_regla_del_tema_a_la_query_directa`, `::test_main_puerta_1_deja_el_candidato_en_ads_json`), comprobado por mutación: apagando el despacho de `main`, los dos mueren. La capa skill (issue 7.4) entró en v1.32.0. **Falta** y la evaluación por motor, declarada en `vault/STATUS.md`. |
| **INV-89** | Un tema y una estrella acumulan **búsquedas**; el embudo no se suma y cada entrada distingue nuevos de ya existentes. | P1 | **garantizado y medido** | `tests/test_lib_config.py::test_dos_busquedas_con_solapamiento_no_suman` (A={1,2,3}, B={2,3,4} ⇒ universo 4, no 6, con `n_nuevos`/`n_ya_estaban`), `::test_universo_acumulado_sin_bibcodes_cae_al_maximo` y `tests/test_make_notes.py::test_estado_line_se_actualiza_y_no_duplica` (la cabecera dice 120, no 220). Verificado por **mutación**: volver a sumar rompe 3 tests. |
| **INV-90** | Toda escritura en `vault/` es **atómica**. | P1 | **garantizado y medido** | `tests/test_lib_config.py::test_write_text_atomic_publica` (inyección de fallo sobre `os.replace`), `::test_sin_escrituras_directas_a_vault` (barrido estático, auditado por mutación sobre los 14 sitios) y `tests/test_make_notes.py::test_notas_pasan_por_el_helper` + `::test_corte_publicando_no_deja_la_nota_a_medias`. Residuo: la lista de módulos vigilados por el guard estático es explícita —un script nuevo hay que agregarlo a mano, y `sweep_external.py` todavía no está. |
| **INV-91** | La cadena deja **traza estructurada** de qué pasos corrieron, con fecha y versión. | P1 | **garantizado y medido** | `tests/test_lib_config.py::test_save_paso_appendea_con_fecha_version_y_via` y `::test_save_paso_idempotente_el_mismo_dia`; que el lint nombre el paso lo mide `tests/test_lint.py::test_cadena_cortada_nombra_el_paso`. La auditoría del 2026-08-24 encontró que `check_retractions` —último paso de `CADENA_ESTRELLA`— no se estampaba, así que **toda** estrella completa se reportaba como cortada; cerrado con `tests/test_check_retractions.py::test_slug_estampa_su_paso_en_la_cadena`, que estampa los seis pasos previos y corre `check_retractions.main` de verdad: lo que importa es que el paso **bajo prueba** no se estampe a mano, que era el defecto del test viejo. |
| **INV-92** | El veredicto de una hipótesis declara **sobre qué universo** vale, y el universo declarado no puede quedar atrás del corpus real. | P1 | **garantizado y medido** | D-34. Sin el blockquote `> Alcance …`, *«no hay evidencia»* se lee como *«no existe evidencia»* — el mismo *afirmar de más* que el contrato persigue en la prosa, aplicado a la conclusión. Lo implementan `lint.alcance_declarado` (la nota lo trae o es hallazgo) y `lint.corpus_vigente` (los slugs se re-cuentan contra `raw/fulltext/`, así que un alcance que quedó corto se detecta); categoría `alcance_corto`, backlog. **Enunciado el 2026-08-24**: la garantía existía en el código desde D-34 y las dos funciones estaban marcadas `@inv INV-83`, que enuncia otra cosa (el recorte de lectura del ingest) — o sea que el mapa atribuía mal y el conteo «con implementación marcada» estaba inflado (regla de método #4). |
| **INV-93** | Una afirmación sostenida por una fuente **retractada** no pasa desapercibida: o frena la operación, o queda **marcada en línea y visible**. Nunca se borra sola. | P0 | **garantizado y medido** | D-47. La prosa que cita un `[[bibcode]]` con `retracted: true` es **bloqueante** (`tests/test_lint.py::test_cita_a_retractado_sin_marca_bloquea`); con `⛔retractada` pegado a la cita baja a informativa y **se sigue listando** (`::test_cita_marcada_no_bloquea_y_se_lista`). Las dos mitades importan: sin la primera la frontera dura no se sostiene; sin la segunda el único camino sería borrar la afirmación, que puede ser cierta por otra vía y destruye trabajo. El símbolo es deliberado — un `(retractada)` pelado daría falso positivo con cualquier mención del hecho en prosa. **Enunciado el 2026-08-24** (AUD-29): la decisión existía desde D-47 y la escotilla ya degradaba un P0 en producción, pero ningún invariante la admitía: INV-33 se leía incondicional. |
| **INV-94** | Toda nota de paper **pertenece a alguna entidad**: no existe extracción que ninguna síntesis pueda alcanzar. | P0 | **garantizado y medido** | D-23. Un paper sin `stars`, sin `thesis_links` y sin `methods` no entra en ningún roll-up y no lo alcanza ninguna ficha ni concepto — es trabajo pagado que se vuelve invisible, y el detector de huérfanos no lo ve si alguien lo linkea. Bloqueante: `tests/test_lint.py::test_paper_sin_ningun_destino_bloquea` (siembra la nota **con** link entrante, justamente para que el huérfano no lo tape). Es la tercera población, distinta de INV-02 (referencia sin destino) y de INV-45 (extraído pero no sintetizado, que exige `methods` poblado). `entity.py delete` **avisa y no borra** la nota que queda sin destino: `tests/test_entity.py::test_delete_avisa_del_paper_que_queda_sin_destino`. **Enunciado el 2026-08-24** (AUD-31): la categoría frenaba el cierre desde antes y su única justificación —«D-23»— no existía en ningún documento, sólo como referencia en comentarios de código. |
| **INV-95** | El mapa requisito↔código dice la verdad sobre su propia cobertura: una marca `@inv` apunta a un invariante que existe, el conteo de no-marcados sale de comparar el contrato con el árbol real, y el techo **sólo puede bajar**. | P1 | **parcial** (la mitad mecánica, medida) | `scripts/trace_invariants.py` + `docs/trazabilidad-ratchet.yaml`. Medido: la marca huérfana bloquea (`tests/test_trace_invariants.py::test_marca_huerfana_bloquea`), el registro sale del contrato y no de una lista hardcodeada (`::test_registro_sale_del_contrato`), una mención en prosa no cuenta como marca (`::test_mencion_en_prosa_no_es_marca`), el conteo por encima del techo bloquea y por debajo pide bajarlo (`::test_sin_marca_por_encima_del_techo_bloquea`, `::test_sin_marca_por_debajo_del_techo_pasa_y_pide_bajarlo`), y un contrato ilegible sale con código propio en vez de reportar «0 sin marcar» (D-43). **Lo que queda `parcial` y hay que decir**: (a) nada verifica que la marca esté sobre código que **cumple** el invariante — es un comentario, y el mapa mide *que alguien la puso*, no *que sea cierta*: por eso el número «con implementación marcada» es una **cota inferior de atención, no una prueba de cobertura**, y AUD-06/AUD-30 encontraron dos marcas mal atribuidas; (b) *(cerrada en #158)* subir el techo en el mismo commit que rompe la cobertura **ya no pasa**: `trace_invariants.subidas_de_techo` compara el techo del árbol contra el de `HEAD` y sale 1 (#96). Esta fila la seguía declarando faltante, o sea el contrato subestimaba su propio gate — lo inverso de lo que §1 promete. Queda `parcial` **sólo por (a)**, que sigue siendo cierta: esta misma auditoría encontró dos marcas mal atribuidas (#134, #136). **Enunciado el 2026-08-24** (AUD-32): el gate que mide la cobertura del contrato no estaba en el contrato, y es de donde salen los números que gatean cada auditoría. ⚠ **Este invariante no puede llevar marca `@inv`**: `trace_invariants.py` y su test están excluidos del recolector a propósito (`::test_el_recolector_no_se_marca_a_si_mismo`), porque si no se auto-adjudicaría cobertura — ya pasó con INV-87 e INV-90. Es el límite honesto de la herramienta: **lo único que no puede medir es a sí misma**. Por eso figura en `sin_marca` y el techo lo dice. |
| **INV-96** | Los backends de descubrimiento normalizan al **mismo schema de registro**, así que ser *core* es función de `(paper, lente)` y no de qué backend lo trajo. | P1 | **garantizado y medido** | `query_ads.to_record` **define** el schema y `openalex.to_record`/`search_arxiv.to_record` lo espejan; la paridad la fija un test parametrizado, no prosa en tres docstrings (`tests/test_backends_schema.py::test_el_registro_tiene_exactamente_las_claves_del_schema`, `::test_el_veredicto_del_clasificador_tiene_el_tipo_correcto`) — red #2. Importa porque si un backend deja de emitir `facets`/`relevant`/`why_excluded`, `make_notes` escribe todo `relevance: low` y `citation_index.corpus_idents` los excluye de la puerta 1, **en silencio**, y INV-24 deja de valer sin que nada se ponga rojo. **Estado del cableado, declarado** (AUD-33): `openalex` está en producción —`citation_index` lo usa para la mitad OpenAlex del índice de citas—; `search_arxiv` **tiene llamador de producción desde #104** —`discover.cascade` lo corre como uno de los tres backends— pero el orquestador `ingest_theme.py` **no llama a `cascade`**: la cascada es un paso que el skill `ingest-theme` prescribe a mano (`discover.py --theme <slug>`, 0b). #144 separó los dos sentidos de «cableado», que hasta acá convivían sin declararse. Además, desde 1.38.0 tiene CLI de **preview** (`python scripts/search_arxiv.py "<query>"`), que imprime qué trae y qué clasifica como core con la lente vigente **sin escribir nada** — el gemelo de `query_ads --probe`. Que el ORQUESTADOR corra la cascada por su cuenta sigue siendo decisión abierta (#95); lo que se cerró es que la promesa fuera inejercitable. Es deuda declarada, no incumplimiento. |
| **INV-97** | El detector del paso **3b** distingue *«no hay ejes en disputa»* (sección borrada: la escotilla declarada) de *«el contraste no ocurrió»* (sección presente y vacía). | P1 | **garantizado y medido** | #101. `lint.inventario_sin_llenar` + su categoría `contrast_missing`. El paso 3 c del ingest es, según `CLAUDE.md`, *«el paso con más apalancamiento de la cadena y el que más fácil se saltea, porque su producto no se nota si falta»*, y su única red era el backlog *extraído pero no sintetizado* (#75) — que mide si el paper **llegó**, no si el contraste **ocurrió**. Marcado retroactivamente el 2026-08-25: la implementación existía desde 1.41.0 y el invariante nunca se enunció, así que `trace_invariants` lo contaba como **marca huérfana**. |
| **INV-104** | La puerta 2 (core por conteo de citas) está **vigilada por los dos lados**: el umbral que se editó, offline; el conteo que se movió en el mundo, en la pasada de red. Ningún cambio de veredicto es silencioso. | P1 | **garantizado y medido** | #106. La puerta 2 de D-26 no rompe INV-24 —`citation_count` **es** metadata del paper y vive en el frontmatter, así que el veredicto sigue siendo re-derivable offline—, pero es la única metadata que **cambia sola**: la función es estable y su entrada deriva, y un paper podía volverse core sin que nadie editara ni el paper ni la regla. La regla bien enunciada no es *«core no puede cambiar»* (sería falsa: un paper que juntó 5000 citas **debería** volverse core) sino **«todo cambio de veredicto es visible y fechado»** — la misma doctrina que las otras cinco caducidades de INV-85. Dos mitades, con alcance declarado cada una: `lib_config.puerta2_cruces` compara el umbral vigente de `themes.yaml` contra el que el registro guardó en `lente.regla_tema` (offline, sin red, ve *«editaste el umbral»*) y `sweep_external.sweep_citas` re-consulta los conteos (red, ve *«el mundo se movió»*). El umbral se persiste con `query_ads.lens_used(meta)`, y `lens_delta` lo compara con `in` y no por truthiness, porque un umbral en `0` (la puerta abre para todos) es una decisión y no puede leerse igual que «no lo declaró» (la puerta no abre) — la misma distinción que D-26 protege al no ponerle default. (`tests/test_lib_config.py::test_puerta2_umbral_cero_declarado_NO_es_lo_mismo_que_sin_declarar`, `tests/test_sweep_external.py::test_sweep_citas_con_ads_caido_es_fallido_no_limpio`, `tests/test_sweep_external.py::test_pasada_cubre_los_seis_eventos`) |
| **INV-98** | Cortar una sección por su header ancla a **comienzo de línea**: una nota que apunta al lector a su propia sección desde la prosa no se confunde con la sección. | P0 | **garantizado y medido** | `lib_config.section_start`, único para los cinco consumidores (`lint.inventario_sin_llenar`, `lib_blocks.parse_verif_table`, `bench_verify`, `make_notes.stamp_excluded` y `_reemplazar_seccion`) — red #2: cuatro de ellos tenían su propia copia y tres usaban `str.find` pelado. **Medido el 2026-08-25** sobre una ficha real: la prosa decía ``Valores en `## Inventario por eje` ``, el `find` agarraba esa mención, el corte llegaba hasta el header de verdad y la sección volvía vacía — el inventario tenía **36 filas** y el lint lo reportaba como *«el contraste 3b no dejó rastro»*, o sea INV-97 acusando justamente al paso que sí ocurrió. Es el modo de falla de la regla de método #4: **un mapa que atribuye mal es peor que uno vacío**, porque el vacío se ve. (`tests/test_section_anchor.py`) |
| **INV-99** | El bloque de verificación se lee por **celda real**: una barra vertical escapada dentro de una celda no corre las columnas, y una fila que igual no cuadra con el encabezado **no se indexa por posición**. | P0 | **garantizado y medido** | `lib_blocks._split_row` (parte sólo por barras **no** escapadas y deshace el escape) más el guardia de aridad en `parse_verif_table`. El fan-out de `verify-citations` junta varias citas textuales con una barra vertical como separador, y una cita puede traer la suya propia —una fila de tabla del paper—: el generador la escapa como manda markdown y el parser partía por la barra pelada. **Medido el 2026-08-25**: 18 pares de una ficha volvieron *«vencidos por edición»* sin que nadie hubiera editado nada, porque el **ancla** se leía de la celda de al lado. La mitad cara es la silenciosa: sin el guardia de aridad, una fila con una barra sin escapar se lee corrida y el par se cuenta como verificado **contra un ancla ajena**. (`tests/test_section_anchor.py`) |
| **INV-100** | El prompt del fan-out de extracción se **genera** desde lo que la bóveda ya sabe (alias del sujeto, maqueta y provenance del `.txt`), no se escribe a mano por operación. | P1 | **garantizado y medido** | `extraction_prompt.subject_patterns` + `build_prompt`. El paso 3 de `ingest-star` dice «un subagente por paper» (D-14) y deja el prompt al criterio del agente: toda regla que vive en el skill y no en el prompt se cae **en silencio** en esa frontera, y el paso deja de ser reproducible —dos corridas del mismo ingest no comparan nada—. **Medido el 2026-08-25** sobre el ingest de τ Ceti (79 papers, prompt escrito a mano): **54 extractores redescubrieron por su cuenta** el entrelazado de columnas de #44, **23** la grafía del sujeto (`grep "Ceti"` devuelve 1 de 11 hits donde el paper escribe «tau Cet»), y **tres se pisaron el archivo de salida** entre sí —fallo silencioso que devuelve JSON válido del paper equivocado—. Las reglas que sí llegaron al prompt fueron las de 1.42.0, escritas ese mismo día: se transcribe lo fresco. El detector de maqueta marca **62 de 79** `.txt` (78 %) del mismo corpus. ⛔ El prompt pide sólo lo **chequeable** y no suplica exactitud: RSOS 2025 mide que pedirla la **duplica**. (`tests/test_extraction_prompt.py`) |
| **INV-101** | El gate de mutación selecciona también los archivos **sin trackear**: la red que cubre «toda función nueva de `scripts/`» tiene que ver el código nuevo. | P0 | **garantizado y medido** | `mutar.archivos_del_diff` suma `git ls-files --others --exclude-standard` al `git diff --name-only HEAD`, deduplicando (un archivo nuevo ya `git add`-eado sale en los dos). **Medido el 2026-08-25**: el gate corrió sobre el diff de esta misma tanda y listó **sólo** `trace_invariants.py`; `extraction_prompt.py`, con las dos funciones nuevas que el issue venía a cubrir, no se mutó — y el gate habría salido en verde. Es el modo de falla de la regla de método #4 aplicado a la red nº 1: un chequeo que no puede fallar sobre el código que vino a cubrir **se lee como cobertura**. (`tests/test_mutar.py`) |
| **INV-102** | La nota declara la **maqueta** de su `.txt` (`fulltext_layout`), porque en un `.txt` a dos columnas un número de línea **no es un localizador único** y la extracción está hecha de números de línea. | P1 | **garantizado y medido** | `make_notes._txt_layout` + `stamp_fulltext`, sobre `measure_layout.analizar`. Va al **frontmatter y no al `.txt`**: el `.txt` es lo que hashea el ancla de fuente (D-20), así que agregarle un header volvería *vencido por fuente* cada par ya verificado de la bóveda. El hecho vivía sólo en el skill `verify-citations` (#44), y el artefacto que viaja —la nota— no lo llevaba. Se declara también `single-column`: la ausencia del campo significa «no medido», que no es lo mismo (D-43). **Medido el 2026-08-25**: el detector marca **62 de 79** `.txt` del corpus de τ Ceti (78 %), y los extractores del ingest, sin el dato, lo redescubrieron solos en 54 de 79. (`tests/test_make_notes.py::test_stamp_fulltext_declara_la_maqueta`) |
| **INV-103** | La extracción se identifica por su **forma** (`ejes` + `ground_truth`), nunca por traer `bibcode`: la salida de `verify-citations` también lo trae. | P0 | **garantizado y medido** | `extraction_prompt.is_extraction`. **Medido el 2026-08-25**: un cosechador del fan-out que aceptaba cualquier JSON con `bibcode` levantó 13 salidas de verify de OTRA estrella y sobreescribió 13 notas ya terminadas. El JSON era perfectamente válido, así que **nada avisó** — el fallo se descubrió contando bibcodes contra el corpus del slug, no por un error. Es el modo de falla de la regla de método #2 en la frontera del fan-out: dos productos distintos con un campo en común, y el consumidor discriminando por ese campo. ⚠ Hasta 1.68.0 la garantía estaba **escrita y desconectada**: la función existía, sus tests la cubrían y **ningún llamador de producción la invocaba** —el cosechado del fan-out era manual—, así que el defecto medido seguía siendo posible tal cual. Lo cierra `harvest_views.harvest` (#191), que la usa como primera compuerta y **cuenta y nombra** lo rechazado. (`tests/test_extraction_prompt.py`, `tests/test_harvest_views.py::test_un_json_que_NO_es_extraccion_se_rechaza`) |


## 4. Los hallazgos del cruce, ordenados por daño

### 4.1 INCUMPLIDOS (el sistema no cumple algo que debería)

#### INC-1 — La compuerta puede dar limpio sin haber mirado (INV-32, INV-38) · P0

> ✅ **CERRADO (D-43, v1.24.0)** — la degradación muda es hoy la categoría `⛔ No evaluado`, que cuenta para el exit; desde 2026-08-24 suprime además las categorías que dependen de la config ilegible. Se conserva el relato porque explica **por qué** existe el mecanismo.

Dos caminos medidos en los que un chequeo que **no pudo correr** contribuye un cero al total en vez
de decir que no evaluó:

1. **Sin historial de `git`, la verificación stale desaparece.** Medido: sin `.git`, `stale=0`, sin
   crash y sin una línea de reporte (8ª F1 #15). `CLAUDE.md:593-597` lo documenta como *"degrada a
   silencio fuera de un repo"* — o sea que es una decisión consciente, no un descuido. Pero es la
   negación exacta del principio rector *no dar falso limpio*, aplicado justamente a la garantía que
   certifica que las afirmaciones pasaron por el fan-out. Un clon sin historial, un tarball, un
   worktree exportado: en todos, la bóveda se lee como verificada al día.
2. **Un `objective.yaml` que no parsea deja la lente vacía, en silencio.** `load_objective` degrada a
   `{}` a propósito (`cfg.load_objective`, con el argumento correcto: el lint es la compuerta de
   CI y *"ante una bóveda rara reporta, no se muere"*). El problema es que **no reporta**: el único
   chequeo del objetivo compara `name` contra el placeholder (`cfg.DEFAULT_OBJECTIVE_NAME`, en `lint.main`), y con `{}` el `name` no
   es el placeholder, es `None`. Sale WARN=0.

**Arreglo mínimo (no aplicado, es decisión de diseño):** que la degradación deje de ser muda. Un
chequeo *"no evaluado: falta historial de git"* y otro *"no evaluado: objective.yaml no parsea"*,
ambos con la severidad que el usuario decida (§6.4, §6.5). Cuesta dos líneas cada uno; lo caro fue
verlo.

#### INC-2 — `--no-triage` resucita descartes ya juzgados (INV-49, INV-50) · P0

> ✅ **CERRADO (D-48, v1.26.0)** — `--no-triage` **se eliminó** (`tests/test_query_ads.py::test_no_triage_ya_no_existe`). Queda abierta sólo la brecha que INV-49 declara: el carril *tema* no aplica la compuerta.

`query_ads.main` (la rama de `--no-triage`, ya eliminada):

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

> ✅ **CERRADO (D-6, v1.24.0)** — `lib_config.objective_error()`, `query_ads` rehúsa la lente vacía, y la categoría `⛔ No evaluado`. Desde 2026-08-24 cubre también `stars.yaml`/`themes.yaml`.

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

> ✅ **CERRADO (D-53, v1.24.0)** — `lib_config.write_text_atomic` es el writer único y un guard estático lo vigila (`.write_text(` en `make_notes.py`: 0 hits). ⚠ El texto de abajo dice **15** sitios y INV-21 dice **14**: el bueno es 14.

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
- ~~**`--no-triage`** apaga la compuerta entera~~ — ✅ **CERRADO (D-48, v1.26.0): el flag se
  eliminó** (ver INC-2). Queda el resto de este hueco. El `busqueda` del registro guardará
  `n_candidates: 0` — indistinguible de "no había candidatos".
- **`--force`** en cualquier fetcher pisa un artefacto de `raw/` sin registrar qué pisó (ver INV-20).

**Por qué importa.** El registro existe para responder *"sobre qué universo afirma esta ficha, y con
qué lente se filtró"*. Una corrida con `--no-triage` afirma sobre un universo distinto —con el ruido
del grafo adentro y los descartes resucitados— y el registro la describe igual que a una corrida
compuerta-adentro. Un consumidor no puede distinguirlas.

**Cómo se cerraría.** Un campo `overrides: [--yes, --no-triage, ...]` en el `busqueda` del registro,
escrito por la misma corrida que ya escribe `lente`. Es la mitad barata; la otra mitad es documentar
los flags (9 sin documentar según 8ª F3, `--no-triage` el más delicado).

#### HUECO-4 — Borrar y renombrar no tienen ni herramienta ni chequeo fuera de `wiki/` (INV-19) · P0 — ✅ CERRADO (1.35.0)

**Qué faltaba.** No existía script de borrado ni de renombrado de ENTIDAD: los dos eran
procedimientos manuales del skill `maintain` —nueve pasos en orden sobre siete lugares distintos—.
Eso era defendible como diseño ("son operaciones raras y de juicio"); lo que no lo era es que el
**chequeo posterior cubriera una sola capa**. Cubierto estaba: wikilinks rotos y notas huérfanas
(bloqueantes) y `raw/ground_truth/<slug>.json` sin su ficha (backlog). Sin cubrir:
`config/registro/<slug>.yaml`, `raw/fulltext/<slug>/`, `raw/pdfs/<slug>/`, la entrada sobreviviente
del YAML y `build/<slug>/` — un renombrado a medias dejaba la mitad de los artefactos bajo el slug
viejo y el lint salía en 0.

**Nota de honestidad, que se conserva porque explica cómo se llegó acá:** el caso simétrico que
**sí** estaba cubierto (ground-truth sin ficha) se agregó porque alguien lo pisó de verdad — la
instancia real lo tenía (`ds_tuc.json` sin `stars/ds_tuc.md`, 8ª F5). Era evidencia de que el modo
de falla es real y de que la cobertura se estaba construyendo **por accidente, un hermano por vez,
en vez de por barrido**.

**Cómo se cerró.** Las dos mitades, y las dos derivadas de **una sola lista de capas**:
- **Herramienta:** `scripts/entity.py` — `plan` (no escribe), `delete` y `rename`, dry-run sin
  `--yes` (la capa 2 no se regenera). Lo que no hace solo lo **avisa**: no borra el paper
  compartido, no repara los `[[wikilink]]` que quedan rotos (repararlos sería decidir qué decía esa
  frase) y no borra la nota que queda sin destino (extracción ya pagada).
- **Chequeo:** categoría *Capas colgadas* del lint, derivada de la misma lista, con el registro
  marcado aparte por ser el único artefacto no regenerable.

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

**Qué cambió (10.1/10.3, 2026-08-24) — el hueco sigue abierto pero dejó de ser caro.** Dos piezas
que faltaban ya están: (a) `lint.collect()` devuelve el resultado **estructurado**, así que agregar
un `poblacion` por `Categoria` es un campo, no una refactorización; (b) el corpus poblado da **cero
en las 70 categorías** salvo cuatro declaradas
(`tests/poblada/test_conteos_exactos.py::test_el_corpus_limpio_da_cero_en_TODAS_las_categorias`), y
16 de ellas tienen conteo exacto con stems — eso ataca el falso NEGATIVO, que es la mitad que el
"0 significa algo" necesita. Lo que sigue faltando es la mitad declarativa: que el reporte **diga**
cuántas notas evaluó cada dimensión.

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
(`fetch_web.main`, la rama del snapshot ya existente). El resultado es una nota que dice una cosa y un `.txt` que es de otro
documento, sin ningún aviso de que la URL no coincide.

**Por qué es menos grave de lo que suena:** falla del lado seguro (no sobreescribe), y `--force` es
explícito. Pero el estado resultante es exactamente el que la regla #0 prohíbe: una afirmación con un
`[[bibcode]]` que no la respalda.

**Cómo se cerraría.** Que `fetch_web`/`make_notes --web` comparen la `source_url` de la nota existente
con la que se está declarando y fallen ruidosamente si difieren.

#### HUECO-8 — La clave de respuestas del benchmark vive junto al examen (INV-74) · P1 — ✅ CERRADO (1.33.0, D-55)

**Qué faltaba.** `bench_verify.py seed` escribía un solo archivo, `build/verify_bench/bench.json`,
con los pares **y** su etiqueta (`label: real|sembrada`) e ids que la telegrafiaban por prefijo
(`r000`, `s000`). El orden **sí** estaba mezclado de forma determinista por hash del contenido — o
sea que el problema estaba visto a medias. La ceguera la sostenía una instrucción en prosa
(*"NUNCA mostrarle `bench.json`"*): una garantía de la capa LLM sobre un artefacto que la capa
determinista podía hacer imposible de filtrar.

**Cómo se cerró.** `seed` escribe `exam.json` (`id` neutro `p###` asignado **después** del sort, sin
`label` y **sin `n_real`/`n_seeded`** — dos conteos por clase también son clave) y `key.json` (sólo
la lee `score`, que cruza por `id` y **rehúsa puntuar** si el examen trae ids que la clave no tiene).
El `bench.json` viejo no se lee: se detecta y manda a re-sembrar. Tests:
`tests/test_bench_verify.py` · `test_exam_no_contiene_la_clave`, `test_score_cruza_examen_y_clave`,
`test_score_rechaza_examen_y_clave_de_corridas_distintas`,
`test_bench_json_viejo_no_se_lee_se_manda_a_resembrar`.

**Residuo declarado (no lo cierra el archivo, lo cerraría otra siembra):** cada sembrada comparte el
`claim` con su par real, así que quien lea el examen **entero** deduce que uno de esos dos es falso
—no cuál—. El juez real no lo ve: el fan-out le da a cada subagente su par y nada más.

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
| 5 | **Los diez `incomplete`: proxies de síntesis campo por campo.** `P_rot` sin documentar en la prosa, `activity_indicators_expected` vacío, planeta del frontmatter no discutido, paper core sin `methods`, paper extraído sin `role`, `unidad_cita` de documento largo sin `alcance` (#80), paper relevante sin fuente en disco (#90), `.txt` sin nota en `papers/` (#108), ficha sin ground-truth, ground-truth sin ficha. *(`thesis_links` sin `bearing` salió con D-21; el conteo es el de los sitios que pueblan `incomplete` en `lint.py` — decía **siete** con diez en el código, #147.)* | **Necesaria.** (B) derivó INV-45 (el paper llegó o no llegó); el sistema mide además **si la síntesis tocó cada eje**. Es la única red sobre la calidad de la capa LLM que no depende de otra corrida de LLM. |
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
> a punta: 57 decisiones, de las cuales **35 el auditor no había previsto**. Los
> invariantes nuevos entraron como **§3.K (INV-76…91)**, todos en estado HUECO — y el enunciado de
> cada uno es lo que esa revisión decidió, así que la fila **es** el registro. *(El conteo vigente es el
> del encabezado de §3.K, que es el de sus filas. AUD-19: acá vivía un segundo conteo —10 medidos,
> 4 parciales, 2 HUECO— con la misma fecha y el mismo alcance declarado que aquél y distinto de los
> dos; tres números para el mismo hecho.)*
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
22. ~~**¿La ceguera del benchmark la sostiene la construcción o la instrucción?**~~ **Resuelta
    (1.33.0):** la sostiene la **construcción** — examen y clave son dos archivos y el `id` no
    codifica la clase. Queda el residuo del `claim` duplicado, declarado en HUECO-8.

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
chequear", y `ingest_star.main` traducía cualquier 1 al primer mensaje).
