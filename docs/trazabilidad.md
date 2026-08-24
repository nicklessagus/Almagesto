# Trazabilidad requisito ↔ código

> ⚠ **Archivo generado** por `python scripts/trace_invariants.py`. No editar a mano: se
> regenera. La relación vive en las marcas `@inv INV-nn` del código, al lado de lo que
> cumple el invariante; acá sólo se recolecta. El enunciado de cada invariante y su estado
> son autoridad de `docs/contrato.md` §3.

## Resumen

- Invariantes en el contrato: **91**
- Con implementación marcada: **6**
- Con test marcado: **6** (techo `sin_test`: 85, hoy 85)
- Sin ninguna marca: **85** (techo `sin_marca`: 85)
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
| **INV-76** | P0 | HUECO (D-1) | — | — |
| **INV-77** | P1 | HUECO (D-2) | — | — |
| **INV-78** | P0 | HUECO (D-4, D-20) | `scripts/lib_blocks.py:3`<br>`scripts/lint.py:838` · `main` | `tests/test_lib_blocks.py:47` · `test_reflow_no_mueve_ancla`<br>`tests/test_lint.py:1862` · `test_reemplazo_del_txt_marca_por_fuente` |
| **INV-79** | P0 | HUECO (D-4, D-5) | `scripts/lint.py:838` · `main` | `tests/test_lint.py:1817` · `test_nota_verificada_no_marca_nada` |
| **INV-80** | P0 | HUECO (D-6) | `scripts/lib_config.py:203` · `objective_error`<br>`scripts/query_ads.py:822` · `main` | `tests/test_lib_config.py:399` · `test_objective_error_distingue_los_tres_estados`<br>`tests/test_lint.py:1735` · `test_lint_objective_roto_bloquea`<br>`tests/test_query_ads.py:1301` · `test_query_ads_rehusa_lente_vacia` |
| **INV-81** | P0 | HUECO (D-10, D-11, D-24) | — | — |
| **INV-82** | P1 | HUECO (D-12) | — | — |
| **INV-83** | P0 | HUECO (D-13, D-14) | — | — |
| **INV-84** | P0 | HUECO (D-19) | — | — |
| **INV-85** | P1 | HUECO (D-41, D-45, D-46) | — | — |
| **INV-86** | P0 | HUECO (D-42) | — | — |
| **INV-87** | P0 | HUECO (D-43) | `scripts/check_retractions.py:326` · `main` | `tests/test_check_retractions.py:525` · `test_errores_sin_retractados_exit_2`<br>`tests/test_lint.py:1745` · `test_lint_sin_git_reporta_no_evaluado` |
| **INV-88** | P1 | HUECO (D-25, D-26, D-27) | — | — |
| **INV-89** | P1 | HUECO (D-28) | `scripts/lib_config.py:537` · `load_busquedas` | `tests/test_lib_config.py:418` · `test_dos_busquedas_con_solapamiento_no_suman` |
| **INV-90** | P1 | HUECO (D-53) | `scripts/lib_config.py:385` · `write_text_atomic`<br>`scripts/lib_config.py:409` · `write_bytes_atomic` | `tests/test_lib_config.py:371` · `test_sin_escrituras_directas_a_vault`<br>`tests/test_make_notes.py:1802` · `test_notas_pasan_por_el_helper` |
| **INV-91** | P1 | HUECO (D-57) | — | — |
