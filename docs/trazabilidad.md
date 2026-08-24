# Trazabilidad requisito ↔ código

> ⚠ **Archivo generado** por `python scripts/trace_invariants.py`. No editar a mano: se
> regenera. La relación vive en las marcas `@inv INV-nn` del código, al lado de lo que
> cumple el invariante; acá sólo se recolecta. El enunciado de cada invariante y su estado
> son autoridad de `docs/contrato.md` §3.

## Resumen

- Invariantes en el contrato: **91**
- Con implementación marcada: **68**
- Con test marcado: **85** (techo `sin_test`: 6, hoy 6)
- Sin ninguna marca: **6** (techo `sin_marca`: 6)
- Marcas huérfanas: **0**

## El mapa

| ID | Prio | Estado (contrato) | Implementa | Prueba |
|---|---|---|---|---|
| **INV-01** | P0 | garantizado sin medir | `scripts/make_notes.py:1400` · `write_star_note` | `tests/test_make_notes.py:293` · `test_star_note_desde_ground_truth` |
| **INV-02** | P0 | garantizado y medido | `scripts/lint.py:82` | `tests/test_lint.py:64` · `test_wikilink_roto_bloquea` |
| **INV-03** | P1 | garantizado y medido | — | `tests/test_lint.py:1276` · `test_cita_sin_fulltext_no_verificable` |
| **INV-04** | P1 | garantizado y medido | `scripts/lint.py:87` | `tests/test_lint.py:1107` · `test_fuga_de_implementacion_warn` |
| **INV-05** | P2 | garantizado sin medir | — | — |
| **INV-06** | P0 | garantizado y medido | `scripts/lint.py:416` · `mirror_issues` | `tests/test_lint.py:663` · `test_espejo_valor_que_nea_no_tiene_es_bloqueante` |
| **INV-07** | P0 | garantizado y medido | `scripts/make_notes.py:1400` · `write_star_note` | `tests/test_make_notes.py:320` · `test_star_note_sin_ground_truth` |
| **INV-08** | P0 | garantizado y medido | `scripts/make_notes.py:496` · `sync_mirror` | `tests/test_make_notes.py:1743` · `test_sync_mirror_no_pisa_un_valor_distinto` |
| **INV-09** | P0 | garantizado y medido | `scripts/lint.py:416` · `mirror_issues` | `tests/test_lint.py:723` · `test_espejo_compara_que_planetas_no_cuantos` |
| **INV-10** | P0 | garantizado y medido | `scripts/fetch_ground_truth.py:60` · `msini_earth` | `tests/test_lint.py:1008` · `test_masa_inconsistente` |
| **INV-11** | P0 | garantizado y medido | `scripts/make_notes.py:790` | `tests/test_make_notes.py:584` · `test_inventario_no_tiene_columna_de_valor_adoptado` |
| **INV-12** | P0 | garantizado y medido | `scripts/lint.py:262` · `note_disputes` | `tests/test_lint.py:323` · `test_disputa_con_una_sola_posicion_no_es_disputa` |
| **INV-13** | P0 | garantizado y medido | `scripts/lint.py:325` · `legacy_disputes` | `tests/test_lint.py:1072` · `test_schema_viejo_de_disputes_grita_en_vez_de_volverse_mudo`<br>`tests/test_lint.py:1979` · `test_topics_en_nota_de_paper_es_schema_viejo` |
| **INV-14** | P1 | garantizado sin medir | `scripts/lib_config.py:639` | `tests/test_lib_config.py:582` · `test_autoridad_por_campo_declarada` |
| **INV-15** | P0 | garantizado y medido | `scripts/make_notes.py:1123` · `_reemplazar_seccion` | `tests/test_make_notes.py:1774` · `test_sync_mirror_no_toca_la_prosa` |
| **INV-16** | P0 | garantizado y medido | `scripts/make_notes.py:609` · `merge_frontmatter_list` | `tests/test_make_notes.py:163` · `test_merge_preserva_el_resto_byte_a_byte` |
| **INV-17** | P1 | garantizado y medido (con deuda) | `scripts/make_notes.py:231` · `find_header_line` | `tests/test_make_notes.py:1317` · `test_find_header_line_es_contrato_compartido` |
| **INV-18** | P0 | garantizado y medido | `scripts/make_notes.py:259` · `stamp_pdf_link` | `tests/test_make_notes.py:1250` · `test_stamp_pdf_link_sin_cabecera_no_adivina` |
| **INV-19** | P0 | HUECO (parcial) | — | — |
| **INV-20** | P0 | garantizado sin medir | — | `tests/test_fetch_ground_truth.py:226` · `test_main_no_pisa_sin_force` |
| **INV-21** | P0 | garantizado y medido | — | `tests/test_make_notes.py:1859` · `test_corte_publicando_no_deja_la_nota_a_medias` |
| **INV-22** | P1 | garantizado y medido | — | `tests/poblada/test_upgrade.py:373` · `test_ciclo_completo_cierra_el_lint_y_la_segunda_pasada_es_no_op` |
| **INV-23** | P1 | INCUMPLIDO (parcial) | — | — |
| **INV-24** | P1 | garantizado sin medir | `scripts/query_ads.py:226` · `classify` | `tests/test_query_ads.py:103` · `test_classify_coherente_con_exclusion_reason` |
| **INV-25** | P1 | garantizado sin medir | `scripts/lib_config.py:491` · `load_registro` | `tests/test_lint.py:1351` · `test_registro_versionado_cubre_la_falta_de_build` |
| **INV-26** | P1 | garantizado sin medir | `scripts/make_notes.py:85` · `_txt_provenance` | `tests/test_make_notes.py:948` · `test_fulltext_info_provenance` |
| **INV-27** | P1 | HUECO (parcial) | `scripts/fetch_web.py:38` | `tests/test_fetch_web.py:54` · `test_citekey_re` |
| **INV-28** | P1 | garantizado y medido | `scripts/extract_fulltext.py:79` · `is_legible` | `tests/test_extract_fulltext.py:49` · `test_legible_umbrales_limite` |
| **INV-29** | P0 | garantizado y medido | `scripts/make_notes.py:109` · `pdf_source_info` | `tests/test_make_notes.py:1424` · `test_pdf_source_desconocido_no_afirma_publicado` |
| **INV-30** | P1 | HUECO (parcial) | `scripts/fetch_web.py:51` · `clean_markdown` | `tests/test_fetch_web.py:113` · `test_main_idempotente_reusa_fecha_del_snapshot` |
| **INV-31** | P0 | garantizado y medido | `scripts/lint.py:142` · `verify_block` | `tests/test_lint.py:1650` · `test_verificacion_stale_por_commit_posterior` |
| **INV-32** | P0 | garantizado y medido | — | `tests/test_lint.py:1767` · `test_no_evaluado_no_contamina_conteos` |
| **INV-33** | P0 | garantizado y medido | `scripts/check_retractions.py:177` · `stamp_retraction` | `tests/test_lint.py:172` · `test_paper_retractado_bloquea` |
| **INV-34** | P1 | garantizado y medido | `scripts/check_retractions.py:184` · `stamp_corrections` | `tests/test_lint.py:183` · `test_paper_con_correccion_es_backlog_no_bloquea` |
| **INV-35** | P0 | garantizado y medido | `scripts/make_notes.py:1093` · `concept_rollup_rows` | `tests/test_make_notes.py:1922` · `test_papers_table_no_depende_del_plugin` |
| **INV-36** | P0 | garantizado y medido | `scripts/lib_config.py:285` · `split_fm` | `tests/test_lib_config.py:254` · `test_split_fm_no_corta_dentro_de_un_valor` |
| **INV-37** | P0 | garantizado y medido | — | `tests/poblada/test_golden.py:138` · `test_golden_exit_code` |
| **INV-38** | P0 | garantizado y medido | — | `tests/test_lint.py:1752` · `test_lint_sin_git_reporta_no_evaluado` |
| **INV-39** | P0 | garantizado y medido | — | `tests/test_lint.py:1364` · `test_build_local_gana_sobre_el_registro` |
| **INV-40** | P0 | HUECO (parcial) | `scripts/lint.py:115` · `fm_error` | `tests/test_lint.py:108` · `test_paper_sin_tag_paper_evade_los_chequeos_de_su_tipo` |
| **INV-41** | P1 | garantizado y medido | — | `tests/poblada/test_golden.py:167` · `test_reporte_lista_todas_las_categorias` |
| **INV-42** | P0 | garantizado y medido | — | `tests/poblada/test_escala.py:194` · `test_lint_no_muta_la_boveda` |
| **INV-43** | P1 | garantizado y medido | — | `tests/test_lint.py:1954` · `test_notas_huerfanas_salen_en_orden_estable` |
| **INV-44** | P0 | parcial | — | `tests/test_query_ads.py:1350` · `test_escotillas_quedan_en_el_registro` |
| **INV-45** | P1 | garantizado y medido | — | `tests/test_lint.py:515` · `test_extraido_sin_llegar_a_ninguna_entidad_es_backlog` |
| **INV-46** | P1 | garantizado y medido | `scripts/lint.py:344` | `tests/test_lint.py:455` · `test_role_fuera_del_vocabulario_es_bloqueante` |
| **INV-47** | P1 | garantizado y medido | `scripts/lib_config.py:368` · `load_concept_areas` | `tests/test_lib_config.py:95` · `test_concept_areas_sin_declarar_apaga_el_chequeo` |
| **INV-48** | P0 | garantizado y medido | `scripts/triage.py:105` · `drop` | `tests/test_triage.py:60` · `test_drop_persiste_con_motivo_en_config_versionada` |
| **INV-49** | P0 | garantizado y medido (con brecha nombrada) | `scripts/query_ads.py:618` · `load_triage` | `tests/test_query_ads.py:1174` · `test_main_triage_no_repropone_descartados` |
| **INV-50** | P0 | garantizado y medido | `scripts/query_ads.py:603` · `subject_in_title` | `tests/test_query_ads.py:1158` · `test_main_chaining_solo_auto_acepta_sujeto_en_titulo` |
| **INV-51** | P1 | garantizado y medido | `scripts/lib_config.py:772` · `save_busqueda` | `tests/test_query_ads.py:1308` · `test_main_persiste_el_registro_de_busqueda` |
| **INV-52** | P0 | garantizado y medido | `scripts/query_ads.py:371` · `glyph_rescue` | `tests/test_query_ads.py:648` · `test_main_persiste_truncado` |
| **INV-53** | P1 | garantizado y medido | `scripts/lib_config.py:521` · `save_registro` | `tests/test_lib_config.py:437` · `test_busqueda_preserva_decisiones` |
| **INV-54** | P0 | garantizado y medido | `scripts/triage.py:175` · `migrate` | `tests/test_triage.py:365` · `test_migrate_es_idempotente_y_no_pisa_lo_versionado` |
| **INV-55** | P1 | garantizado sin medir | `scripts/query_ads.py:174` · `combination_rule` | `tests/test_query_ads.py:58` · `test_classify_require_faceta_obligatoria` |
| **INV-56** | P0 | garantizado y medido | — | `tests/test_lib_config.py:399` · `test_objective_error_distingue_los_tres_estados` |
| **INV-57** | P1 | garantizado y medido | `scripts/lib_config.py:30` | `tests/test_lint.py:1133` · `test_objetivo_default_warn` |
| **INV-58** | P1 | garantizado y medido | `scripts/query_ads.py:868` · `reclass_diff` | `tests/test_query_ads.py:952` · `test_reclass_diff_reporta_el_delta` |
| **INV-59** | P0 | garantizado y medido | `scripts/query_ads.py:952` · `print_probe` | `tests/test_query_ads.py:977` · `test_reclass_diff_no_escribe_nada` |
| **INV-60** | P1 | garantizado y medido | `scripts/lib_config.py:592` · `load_extra_core` | `tests/test_query_ads.py:563` · `test_fetch_bibcodes_marca_manual` |
| **INV-61** | P1 | garantizado y medido | `scripts/make_notes.py:1753` · `write_web_paper_note` | `tests/test_ingest_theme.py:238` · `test_offads_pending_deriva_sin_fallar` |
| **INV-62** | P1 | garantizado y medido | `scripts/make_notes.py:741` | `tests/test_lib_config.py:106` · `test_version_unica_fuente` |
| **INV-63** | P0 | HUECO (parcial) | `scripts/lint.py:294` · `normalize_lists` | `tests/test_lint.py:149` · `test_campo_de_lista_escrito_como_escalar_se_reporta_una_vez` |
| **INV-64** | P0 | garantizado y medido | `scripts/make_notes.py:430` · `migrate_all_disputes` | `tests/poblada/test_invariantes_instancia.py:334` · `test_papers_declaran_facets_no_topics`<br>`tests/poblada/test_upgrade.py:129` · `test_vintage_bloquea_con_categorias_de_schema_viejo_y_receta_visible` |
| **INV-65** | P2 | garantizado y medido | — | `tests/test_lint.py:1167` · `test_obsidian_en_raiz_warn` |
| **INV-66** | P1 | garantizado sin medir | — | — |
| **INV-67** | P0 | garantizado sin medir | `scripts/lib_config.py:116` · `get_ads_token` | `tests/test_fetch_pdf.py:159` · `test_download_pdf_token_solo_a_ads` |
| **INV-68** | P2 | garantizado y medido | — | `tests/test_lib_config.py:592` · `test_gitattributes_cubre_los_archivos_de_instancia` |
| **INV-69** | P0 | parcial | — | `tests/test_query_ads.py:442` · `test_query_ads_5xx_persistente_lanza` |
| **INV-70** | P1 | garantizado sin medir | `scripts/extract_fulltext.py:94` · `ocr_available` | `tests/test_extract_fulltext.py:210` · `test_flag_ocr_sin_tesseract_aborta` |
| **INV-71** | P1 | garantizado sin medir | `scripts/make_notes.py:72` · `fm` | `tests/test_make_notes.py:186` · `test_excluded_top_n_y_escapes` |
| **INV-72** | P1 | garantizado y medido | `scripts/query_ads.py:586` · `_variant_hit` | `tests/test_query_ads.py:1142` · `test_subject_in_title_no_matchea_por_prefijo_de_catalogo` |
| **INV-73** | P0 | garantizado y medido | — | — |
| **INV-74** | P1 | HUECO (parcial) | `scripts/bench_verify.py:196` · `seed_pairs` | `tests/test_bench_verify.py:42` · `test_seed_extrae_siembra_y_es_determinista` |
| **INV-75** | P2 | garantizado sin medir | `scripts/bench_verify.py:248` · `cmd_score` | `tests/test_bench_verify.py:245` · `test_score_metricas` |
| **INV-76** | P0 | garantizado y medido | `scripts/lib_config.py:638` | `tests/test_fetch_ground_truth.py:342` · `test_spectral_type_solo_de_simbad` |
| **INV-77** | P1 | garantizado y medido | `scripts/lint.py:243` | `tests/test_lint.py:2072` · `test_disputa_entre_autoridades_es_expresable` |
| **INV-78** | P0 | garantizado y medido | `scripts/lib_blocks.py:3`<br>`scripts/lint.py:888` · `main` | `tests/test_lib_blocks.py:47` · `test_reflow_no_mueve_ancla`<br>`tests/test_lint.py:1869` · `test_reemplazo_del_txt_marca_por_fuente` |
| **INV-79** | P0 | garantizado y medido (mitad determinista) | `scripts/lint.py:888` · `main` | `tests/test_lint.py:1824` · `test_nota_verificada_no_marca_nada` |
| **INV-80** | P0 | garantizado y medido | `scripts/lib_config.py:200` · `yaml_error`<br>`scripts/lib_config.py:216` · `stars_error`<br>`scripts/lib_config.py:221` · `themes_error`<br>`scripts/lib_config.py:237` · `objective_error`<br>`scripts/query_ads.py:986` · `main` | `tests/test_lib_config.py:399` · `test_objective_error_distingue_los_tres_estados`<br>`tests/test_lint.py:1742` · `test_lint_objective_roto_bloquea`<br>`tests/test_lint.py:1930` · `test_stars_yaml_roto_reporta_no_evaluado_en_vez_de_reventar`<br>`tests/test_lint.py:1943` · `test_themes_yaml_roto_tambien_reporta_no_evaluado`<br>`tests/test_query_ads.py:1337` · `test_query_ads_rehusa_lente_vacia` |
| **INV-81** | P0 | parcial | `scripts/make_notes.py:1027` · `papers_universe` | `tests/test_make_notes.py:1914` · `test_conteo_del_encabezado_es_el_de_la_tabla` |
| **INV-82** | P1 | parcial | `scripts/make_notes.py:1341` · `estado_line` | `tests/test_make_notes.py:2003` · `test_refrescar_sin_reverificar_mueve_una_sola_fecha` |
| **INV-83** | P0 | parcial | `scripts/lib_config.py:681` · `save_extraccion` | `tests/test_lint.py:2045` · `test_subconjunto_sin_declarar_reporta` |
| **INV-84** | P0 | garantizado y medido | `scripts/make_notes.py:1178` · `rename_paper` | `tests/test_make_notes.py:2124` · `test_ciclo_preprint_publicado` |
| **INV-85** | P1 | parcial (4 de 5 detectores) | `scripts/fetch_ground_truth.py:228` · `nea_diff`<br>`scripts/sweep_external.py:3` | `tests/test_sweep_external.py:110` · `test_detector_no_implementado_no_aporta_un_cero` |
| **INV-86** | P0 | HUECO (D-42) | — | — |
| **INV-87** | P0 | garantizado y medido | `scripts/check_retractions.py:343` · `main` | `tests/test_check_retractions.py:525` · `test_errores_sin_retractados_exit_2`<br>`tests/test_lint.py:1752` · `test_lint_sin_git_reporta_no_evaluado` |
| **INV-88** | P1 | garantizado y medido | `scripts/query_ads.py:788` · `reclassify_for_theme`<br>`scripts/query_ads.py:817` · `gate_cited_by_corpus` | `tests/test_query_ads.py:1392` · `test_puerta_2_el_fundacional_entra_sin_lente_astro`<br>`tests/test_query_ads.py:1499` · `test_main_aplica_la_regla_del_tema_a_la_query_directa`<br>`tests/test_query_ads.py:1549` · `test_puerta_1_propone_lo_que_el_corpus_cita_y_no_lo_clasifica`<br>`tests/test_query_ads.py:1584` · `test_main_puerta_1_deja_el_candidato_en_ads_json` |
| **INV-89** | P1 | garantizado y medido | `scripts/lib_config.py:734` · `load_busquedas` | `tests/test_lib_config.py:418` · `test_dos_busquedas_con_solapamiento_no_suman` |
| **INV-90** | P1 | garantizado y medido | `scripts/lib_config.py:421` · `write_text_atomic`<br>`scripts/lib_config.py:445` · `write_bytes_atomic` | `tests/test_lib_config.py:371` · `test_sin_escrituras_directas_a_vault`<br>`tests/test_make_notes.py:1809` · `test_notas_pasan_por_el_helper` |
| **INV-91** | P1 | garantizado y medido | `scripts/check_retractions.py:332` · `_estampar`<br>`scripts/lib_config.py:801` · `load_cadena`<br>`scripts/lib_config.py:806` · `save_paso` | `tests/test_check_retractions.py:571` · `test_slug_estampa_su_paso_en_la_cadena`<br>`tests/test_lib_config.py:457` · `test_save_paso_appendea_con_fecha_version_y_via` |
