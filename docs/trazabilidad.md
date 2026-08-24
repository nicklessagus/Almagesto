# Trazabilidad requisito ↔ código

> ⚠ **Archivo generado** por `python scripts/trace_invariants.py`. No editar a mano: se
> regenera. La relación vive en las marcas `@inv INV-nn` del código, al lado de lo que
> cumple el invariante; acá sólo se recolecta. El enunciado de cada invariante y su estado
> son autoridad de `docs/contrato.md` §3.

## Resumen

- Invariantes en el contrato: **91**
- Con implementación marcada: **14**
- Con test marcado: **14** (techo `sin_test`: 77, hoy 77)
- Sin ninguna marca: **77** (techo `sin_marca`: 77)
- Marcas huérfanas: **0**

## El mapa

| ID | Prio | Estado (contrato) | Implementa | Prueba |
|---|---|---|---|---|
| **INV-01** | P0 | garantizado sin medir | — | — |
| **INV-02** | P0 | garantizado y medido | — | — |
| **INV-03** | P1 | garantizado y medido | — | — |
| **INV-04** | P1 | garantizado y medido | — | — |
| **INV-05** | P2 | garantizado sin medir | — | — |
| **INV-06** | P0 | garantizado y medido | — | — |
| **INV-07** | P0 | garantizado y medido | — | — |
| **INV-08** | P0 | garantizado y medido | — | — |
| **INV-09** | P0 | garantizado y medido | — | — |
| **INV-10** | P0 | garantizado y medido | — | — |
| **INV-11** | P0 | garantizado sin medir | — | — |
| **INV-12** | P0 | garantizado y medido | — | — |
| **INV-13** | P0 | garantizado y medido | — | — |
| **INV-14** | P1 | garantizado sin medir | — | — |
| **INV-15** | P0 | garantizado y medido | — | — |
| **INV-16** | P0 | garantizado y medido | — | — |
| **INV-17** | P1 | garantizado y medido (con deuda) | — | — |
| **INV-18** | P0 | garantizado y medido | — | — |
| **INV-19** | P0 | HUECO (parcial) | — | — |
| **INV-20** | P0 | garantizado sin medir | — | — |
| **INV-21** | P0 | HUECO (parcial) | — | — |
| **INV-22** | P1 | garantizado y medido | — | — |
| **INV-23** | P1 | INCUMPLIDO (parcial) | — | — |
| **INV-24** | P1 | garantizado sin medir | — | — |
| **INV-25** | P1 | garantizado sin medir | — | — |
| **INV-26** | P1 | garantizado sin medir | — | — |
| **INV-27** | P1 | HUECO (parcial) | — | — |
| **INV-28** | P1 | garantizado y medido | — | — |
| **INV-29** | P0 | garantizado sin medir | — | — |
| **INV-30** | P1 | HUECO (parcial) | — | — |
| **INV-31** | P0 | garantizado y medido | — | — |
| **INV-32** | P0 | INCUMPLIDO | — | — |
| **INV-33** | P0 | garantizado y medido | — | — |
| **INV-34** | P1 | garantizado y medido | — | — |
| **INV-35** | P0 | garantizado y medido | — | — |
| **INV-36** | P0 | garantizado y medido | — | — |
| **INV-37** | P0 | garantizado y medido | — | — |
| **INV-38** | P0 | INCUMPLIDO (parcial) | — | — |
| **INV-39** | P0 | garantizado sin medir | — | — |
| **INV-40** | P0 | HUECO (parcial) | — | — |
| **INV-41** | P1 | garantizado y medido | — | — |
| **INV-42** | P0 | garantizado y medido | — | — |
| **INV-43** | P1 | garantizado y medido | — | — |
| **INV-44** | P0 | HUECO (parcial) | — | — |
| **INV-45** | P1 | garantizado y medido | — | — |
| **INV-46** | P1 | garantizado y medido | — | — |
| **INV-47** | P1 | garantizado y medido | — | — |
| **INV-48** | P0 | garantizado y medido | — | — |
| **INV-49** | P0 | INCUMPLIDO (parcial) | — | — |
| **INV-50** | P0 | garantizado y medido (con escotilla) | — | — |
| **INV-51** | P1 | garantizado sin medir | — | — |
| **INV-52** | P0 | garantizado y medido | — | — |
| **INV-53** | P1 | garantizado y medido | — | — |
| **INV-54** | P0 | garantizado y medido | — | — |
| **INV-55** | P1 | garantizado sin medir | — | — |
| **INV-56** | P0 | HUECO (parcial) | — | — |
| **INV-57** | P1 | garantizado y medido | — | — |
| **INV-58** | P1 | garantizado y medido | — | — |
| **INV-59** | P0 | garantizado y medido | — | — |
| **INV-60** | P1 | garantizado sin medir | — | — |
| **INV-61** | P1 | garantizado y medido | — | — |
| **INV-62** | P1 | garantizado y medido | — | — |
| **INV-63** | P0 | HUECO (parcial) | — | — |
| **INV-64** | P0 | garantizado y medido | — | — |
| **INV-65** | P2 | garantizado y medido | — | — |
| **INV-66** | P1 | garantizado sin medir | — | — |
| **INV-67** | P0 | garantizado sin medir | — | — |
| **INV-68** | P2 | garantizado y medido | — | — |
| **INV-69** | P0 | garantizado sin medir | — | — |
| **INV-70** | P1 | garantizado sin medir | — | — |
| **INV-71** | P1 | garantizado sin medir | — | — |
| **INV-72** | P1 | garantizado y medido | — | — |
| **INV-73** | P0 | garantizado y medido | — | — |
| **INV-74** | P1 | HUECO (parcial) | — | — |
| **INV-75** | P2 | garantizado sin medir | — | — |
| **INV-76** | P0 | HUECO (D-1) | `scripts/lib_config.py:599` · `_extra_core_error` | `tests/test_fetch_ground_truth.py:341` · `test_spectral_type_solo_de_simbad` |
| **INV-77** | P1 | HUECO (D-2) | `scripts/lint.py:239` · `note_files` | `tests/test_lint.py:1999` · `test_disputa_entre_autoridades_es_expresable` |
| **INV-78** | P0 | HUECO (D-4, D-20) | `scripts/lib_blocks.py:3`<br>`scripts/lint.py:865` · `main` | `tests/test_lib_blocks.py:47` · `test_reflow_no_mueve_ancla`<br>`tests/test_lint.py:1864` · `test_reemplazo_del_txt_marca_por_fuente` |
| **INV-79** | P0 | HUECO (D-4, D-5) | `scripts/lint.py:865` · `main` | `tests/test_lint.py:1819` · `test_nota_verificada_no_marca_nada` |
| **INV-80** | P0 | HUECO (D-6) | `scripts/lib_config.py:203` · `objective_error`<br>`scripts/query_ads.py:838` · `main` | `tests/test_lib_config.py:399` · `test_objective_error_distingue_los_tres_estados`<br>`tests/test_lint.py:1737` · `test_lint_objective_roto_bloquea`<br>`tests/test_query_ads.py:1320` · `test_query_ads_rehusa_lente_vacia` |
| **INV-81** | P0 | HUECO (D-10, D-11, D-24) | `scripts/make_notes.py:1017` · `papers_universe` | `tests/test_make_notes.py:1911` · `test_conteo_del_encabezado_es_el_de_la_tabla` |
| **INV-82** | P1 | HUECO (D-12) | `scripts/make_notes.py:1329` · `estado_line` | `tests/test_make_notes.py:2000` · `test_refrescar_sin_reverificar_mueve_una_sola_fecha` |
| **INV-83** | P0 | HUECO (D-13, D-14) | `scripts/lib_config.py:641` · `save_extraccion` | `tests/test_lint.py:1972` · `test_subconjunto_sin_declarar_reporta` |
| **INV-84** | P0 | HUECO (D-19) | `scripts/make_notes.py:1166` · `rename_paper` | `tests/test_make_notes.py:2121` · `test_ciclo_preprint_publicado` |
| **INV-85** | P1 | HUECO (D-41, D-45, D-46) | `scripts/fetch_ground_truth.py:228` · `nea_diff`<br>`scripts/sweep_external.py:3` | `tests/test_sweep_external.py:110` · `test_detector_no_implementado_no_aporta_un_cero` |
| **INV-86** | P0 | HUECO (D-42) | — | — |
| **INV-87** | P0 | HUECO (D-43) | `scripts/check_retractions.py:326` · `main` | `tests/test_check_retractions.py:525` · `test_errores_sin_retractados_exit_2`<br>`tests/test_lint.py:1747` · `test_lint_sin_git_reporta_no_evaluado` |
| **INV-88** | P1 | HUECO (D-25, D-26, D-27) | — | — |
| **INV-89** | P1 | HUECO (D-28) | `scripts/lib_config.py:694` · `load_busquedas` | `tests/test_lib_config.py:418` · `test_dos_busquedas_con_solapamiento_no_suman` |
| **INV-90** | P1 | HUECO (D-53) | `scripts/lib_config.py:385` · `write_text_atomic`<br>`scripts/lib_config.py:409` · `write_bytes_atomic` | `tests/test_lib_config.py:371` · `test_sin_escrituras_directas_a_vault`<br>`tests/test_make_notes.py:1806` · `test_notas_pasan_por_el_helper` |
| **INV-91** | P1 | HUECO (D-57) | `scripts/lib_config.py:760` · `load_cadena`<br>`scripts/lib_config.py:765` · `save_paso` | `tests/test_lib_config.py:457` · `test_save_paso_appendea_con_fecha_version_y_via` |
