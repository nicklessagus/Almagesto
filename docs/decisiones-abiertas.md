# Decisiones abiertas del framework

Lo que el template **no decide** y deja escrito, con el issue donde vive la medición. Una decisión
abierta no es deuda: es una perilla cuyo valor depende del campo o de un costo que el usuario tiene
que aceptar, y esconderla sería decidir por él. Cada instancia decide lo suyo en su `STATUS.md`.

| Decisión | Estado | Por qué está abierta |
|---|---|---|
| **`fundacional_min_citas` sin default** (D-26) | abierta, deliberada | 30k citas es normal en ML y muchísimo en astro; un default escondería la elección. Sin declararlo la puerta 2 no abre y `why_excluded` lo dice. |
| **`fundacional_fuente: ads \| openalex`** (#357) | abierta | La puerta 2 promete «fundacional en SU campo» y compara contra el `citation_count` de **ADS**, que en un tema de otra disciplina mide *cuánto lo cita astro*. Medido en `icasso` (ADS / OpenAlex): ICASSO 2004 **no está** / 1295 · ICASSO 2003 **9** / 284 · split-half **no está** / 227 · RELICA **no está** / 99 · RAICAR **no está** / 95 · MSTD **no está** / 79 · Cantini 2019 4 / 28 · RAICAR-N 1 / 23 · Wei 2022 1 / 23 · CoCA **no está** / 10. Ningún umbral separa el canon con ADS. Leer OpenAlex es barato (el endpoint de entidad única cuesta 0, #362) pero **rompe INV-24**: el veredicto deja de ser re-derivable offline. Hoy el probe muestra el rango y avisa (v1.195.0); el canon entra por `extra_core`. |
| **Supersesión estructurada del `log`** (#387 B → #391) | abierta | ids + `supersede:` en vez de la marca en prosa. La marca alcanza mientras el `log` se lea de arriba a abajo. |
| **Fan-out de verify sobre `## Vista`** (#373, 2) | abierta por costo | 3838 pares en una bóveda real. El barrido determinista sí las cubre (#373); el juicio de LLM no. |
| **Driver de unión ordenada para `log.md`** (#390, opción 3) | innecesaria mientras la receta `-c merge.ours.driver=true` mida bien | Medido en repos sintéticos (`tests/test_merge_ours_driver.py`). |
| **Presupuesto de OpenAlex por operación** (#362, 3) | abierta | Hoy hay orden de gasto documentado (`docs/operacion.md`) y el 429 por presupuesto es no reintentable; un presupuesto por corrida sería el paso siguiente. |
