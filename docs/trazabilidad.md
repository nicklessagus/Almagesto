# Trazabilidad requisito ↔ código

> ⚠ **Archivo generado** por `python scripts/trace_invariants.py`. No editar a mano: se
> regenera. La relación vive en las marcas `@inv INV-nn` del código, al lado de lo que
> cumple el invariante; acá sólo se recolecta. El enunciado de cada invariante y su estado
> son autoridad de `docs/contrato.md` §3.

## Resumen

- Invariantes en el contrato: **99**
- Con implementación marcada: **78**
- Con test marcado: **96** (techo `sin_test`: 3, hoy 3)
- Sin ninguna marca: **3** (techo `sin_marca`: 3)
- Marcas huérfanas: **0**

## El mapa

| ID | Prio | Estado (contrato) | Implementa | Prueba |
|---|---|---|---|---|
| **INV-01** | P0 | garantizado sin medir | `scripts/make_notes.py:1716` · `write_star_note` | `tests/test_make_notes.py:298` · `test_star_note_desde_ground_truth` |
| **INV-02** | P0 | garantizado y medido | `scripts/lint.py:83` | `tests/test_lint.py:64` · `test_wikilink_roto_bloquea` |
| **INV-03** | P1 | garantizado y medido | — | `tests/test_lint.py:1277` · `test_cita_sin_fulltext_no_verificable`<br>`tests/test_lint.py:2738` · `test_cita_sin_fulltext_en_una_ficha_de_estrella_es_precondicion` |
| **INV-04** | P1 | garantizado y medido | `scripts/lib_config.py:442` · `load_downstream`<br>`scripts/lint.py:88`<br>`scripts/lint.py:121` · `downstream_leaks` | `tests/test_lint.py:1108` · `test_fuga_de_implementacion_warn` |
| **INV-05** | P2 | garantizado sin medir | — | — |
| **INV-06** | P0 | garantizado y medido | `scripts/lint.py:645` · `mirror_issues` | `tests/test_lint.py:663` · `test_espejo_valor_que_nea_no_tiene_es_bloqueante` |
| **INV-07** | P0 | garantizado y medido | `scripts/make_notes.py:1716` · `write_star_note` | `tests/test_make_notes.py:325` · `test_star_note_sin_ground_truth` |
| **INV-08** | P0 | garantizado y medido | `scripts/make_notes.py:675` · `sync_mirror` | `tests/test_make_notes.py:1760` · `test_sync_mirror_no_pisa_un_valor_distinto` |
| **INV-09** | P0 | garantizado y medido | `scripts/lint.py:645` · `mirror_issues` | `tests/test_lint.py:723` · `test_espejo_compara_que_planetas_no_cuantos` |
| **INV-10** | P0 | garantizado y medido | `scripts/fetch_ground_truth.py:98` · `msini_earth` | `tests/test_lint.py:1009` · `test_masa_inconsistente` |
| **INV-11** | P0 | garantizado y medido | `scripts/make_notes.py:976` | `tests/test_make_notes.py:596` · `test_inventario_no_tiene_columna_de_valor_adoptado` |
| **INV-12** | P0 | garantizado y medido | `scripts/lint.py:460` · `note_disputes` | `tests/test_lint.py:323` · `test_disputa_con_una_sola_posicion_no_es_disputa` |
| **INV-13** | P0 | garantizado y medido | `scripts/lint.py:523` · `legacy_disputes`<br>`scripts/make_notes.py:589` · `migrate_all_bearing` | `tests/test_lint.py:1073` · `test_schema_viejo_de_disputes_grita_en_vez_de_volverse_mudo`<br>`tests/test_lint.py:1996` · `test_topics_en_nota_de_paper_es_schema_viejo` |
| **INV-14** | P1 | garantizado sin medir | `scripts/lib_config.py:756` | `tests/test_lib_config.py:591` · `test_autoridad_por_campo_declarada` |
| **INV-15** | P0 | garantizado y medido | `scripts/make_notes.py:1396` · `_reemplazar_seccion` | `tests/test_make_notes.py:1791` · `test_sync_mirror_no_toca_la_prosa` |
| **INV-16** | P0 | garantizado y medido | `scripts/make_notes.py:788` · `merge_frontmatter_list` | `tests/test_make_notes.py:168` · `test_merge_preserva_el_resto_byte_a_byte` |
| **INV-17** | P1 | parcial (medido, con la deuda nombrada) | `scripts/make_notes.py:231` · `find_header_line` | `tests/test_make_notes.py:1332` · `test_find_header_line_es_contrato_compartido` |
| **INV-18** | P0 | garantizado y medido | `scripts/make_notes.py:259` · `stamp_pdf_link` | `tests/test_make_notes.py:1265` · `test_stamp_pdf_link_sin_cabecera_no_adivina` |
| **INV-19** | P0 | garantizado y medido (1.35.0) | `scripts/entity.py:76` · `capas`<br>`scripts/entity.py:248` · `delete`<br>`scripts/entity.py:289` · `rename` | `tests/test_entity.py:87` · `test_delete_borra_las_siete_capas`<br>`tests/test_entity.py:144` · `test_rename_mueve_las_capas_y_actualiza_el_slug` |
| **INV-20** | P0 | garantizado sin medir | — | `tests/test_fetch_ground_truth.py:239` · `test_main_no_pisa_sin_force` |
| **INV-21** | P0 | garantizado y medido | — | `tests/test_make_notes.py:1876` · `test_corte_publicando_no_deja_la_nota_a_medias` |
| **INV-22** | P1 | garantizado y medido | — | `tests/poblada/test_upgrade.py:374` · `test_ciclo_completo_cierra_el_lint_y_la_segunda_pasada_es_no_op` |
| **INV-23** | P1 | INCUMPLIDO (parcial) | — | — |
| **INV-24** | P1 | garantizado sin medir | `scripts/query_ads.py:182` · `classify` | `tests/test_make_notes.py:2605` · `test_excluidos_usa_la_politica_unica_de_orden_no_las_citas_crudas`<br>`tests/test_query_ads.py:103` · `test_classify_coherente_con_exclusion_reason` |
| **INV-25** | P1 | garantizado sin medir | `scripts/lib_config.py:608` · `load_registro` | `tests/test_lint.py:1360` · `test_registro_versionado_cubre_la_falta_de_build` |
| **INV-26** | P1 | garantizado sin medir | `scripts/make_notes.py:85` · `_txt_provenance` | `tests/test_make_notes.py:963` · `test_fulltext_info_provenance` |
| **INV-27** | P1 | HUECO (parcial) | `scripts/fetch_web.py:46` | `tests/test_fetch_web.py:60` · `test_citekey_re` |
| **INV-28** | P1 | garantizado y medido | `scripts/extract_fulltext.py:79` · `is_legible` | `tests/test_extract_fulltext.py:49` · `test_legible_umbrales_limite` |
| **INV-29** | P0 | garantizado y medido | `scripts/make_notes.py:109` · `pdf_source_info` | `tests/test_make_notes.py:1441` · `test_pdf_source_desconocido_no_afirma_publicado` |
| **INV-30** | P1 | HUECO (parcial) | `scripts/fetch_web.py:59` · `clean_markdown` | `tests/test_fetch_web.py:119` · `test_main_idempotente_reusa_fecha_del_snapshot` |
| **INV-31** | P0 | garantizado y medido | `scripts/lint.py:180` · `verify_block` | `tests/test_lint.py:1667` · `test_verificacion_stale_por_commit_posterior` |
| **INV-32** | P0 | garantizado y medido | — | `tests/test_lint.py:1784` · `test_no_evaluado_no_contamina_conteos` |
| **INV-33** | P0 | garantizado y medido | `scripts/check_retractions.py:177` · `stamp_retraction` | `tests/test_lint.py:172` · `test_paper_retractado_bloquea` |
| **INV-34** | P1 | garantizado y medido | `scripts/check_retractions.py:184` · `stamp_corrections` | `tests/test_lint.py:183` · `test_paper_con_correccion_es_backlog_no_bloquea` |
| **INV-35** | P0 | garantizado y medido | `scripts/make_notes.py:1292` · `concept_rollup_rows` | `tests/test_make_notes.py:1939` · `test_papers_table_no_depende_del_plugin` |
| **INV-36** | P0 | garantizado y medido | `scripts/lib_config.py:353` · `split_fm` | `tests/test_lib_config.py:259` · `test_split_fm_no_corta_dentro_de_un_valor` |
| **INV-37** | P0 | garantizado y medido | — | `tests/poblada/test_golden.py:138` · `test_golden_exit_code` |
| **INV-38** | P0 | garantizado y medido | — | `tests/test_lint.py:1769` · `test_lint_sin_git_reporta_no_evaluado` |
| **INV-39** | P0 | garantizado y medido | — | `tests/test_lint.py:1360` · `test_registro_versionado_cubre_la_falta_de_build`<br>`tests/test_lint.py:1375` · `test_build_local_gana_sobre_el_registro` |
| **INV-40** | P0 | HUECO (parcial) | `scripts/lint.py:153` · `fm_error` | `tests/test_lint.py:108` · `test_paper_sin_tag_paper_evade_los_chequeos_de_su_tipo` |
| **INV-41** | P1 | garantizado y medido | — | `tests/poblada/test_golden.py:167` · `test_reporte_lista_todas_las_categorias` |
| **INV-42** | P0 | garantizado y medido | — | `tests/poblada/test_escala.py:197` · `test_lint_no_muta_la_boveda` |
| **INV-43** | P1 | garantizado y medido | — | `tests/test_lint.py:1971` · `test_notas_huerfanas_salen_en_orden_estable` |
| **INV-44** | P0 | garantizado y medido (1.35.0) | `scripts/lib_config.py:963` · `flags_usados` | `tests/test_ingest_star.py:151` · `test_la_escotilla_del_orquestador_deja_traza`<br>`tests/test_ingest_star.py:163` · `test_save_paso_estampa_la_escotilla_del_orquestador`<br>`tests/test_lib_config.py:812` · `test_flags_usados_no_reporta_el_posicional_como_flag`<br>`tests/test_query_ads.py:1351` · `test_escotillas_quedan_en_el_registro` |
| **INV-45** | P1 | garantizado y medido | — | `tests/test_lint.py:515` · `test_extraido_sin_llegar_a_ninguna_entidad_es_backlog` |
| **INV-46** | P1 | garantizado y medido | `scripts/lint.py:542`<br>`scripts/lint.py:543` | `tests/test_lint.py:455` · `test_role_fuera_del_vocabulario_es_bloqueante` |
| **INV-47** | P1 | garantizado y medido | `scripts/lib_config.py:459` · `load_concept_areas` | `tests/test_lib_config.py:95` · `test_concept_areas_sin_declarar_apaga_el_chequeo` |
| **INV-48** | P0 | garantizado y medido | `scripts/triage.py:105` · `drop` | `tests/test_triage.py:60` · `test_drop_persiste_con_motivo_en_config_versionada` |
| **INV-49** | P0 | parcial (medido, con la brecha nombrada) | `scripts/query_ads.py:553` · `load_triage` | `tests/test_query_ads.py:1175` · `test_main_triage_no_repropone_descartados` |
| **INV-50** | P0 | garantizado y medido | `scripts/query_ads.py:538` · `subject_in_title` | `tests/test_query_ads.py:1159` · `test_main_chaining_solo_auto_acepta_sujeto_en_titulo` |
| **INV-51** | P1 | garantizado y medido | `scripts/lib_config.py:913` · `save_busqueda` | `tests/test_lib_config.py:796` · `test_load_registro_tolera_un_yaml_en_otra_codificacion`<br>`tests/test_query_ads.py:1309` · `test_main_persiste_el_registro_de_busqueda` |
| **INV-52** | P0 | garantizado y medido | `scripts/query_ads.py:327` · `glyph_rescue` | `tests/test_query_ads.py:648` · `test_main_persiste_truncado` |
| **INV-53** | P1 | garantizado y medido | `scripts/lib_config.py:638` · `save_registro` | `tests/test_lib_config.py:446` · `test_busqueda_preserva_decisiones`<br>`tests/test_lib_config.py:687` · `test_save_busqueda_pliega_la_clave_vieja_en_vez_de_borrarla` |
| **INV-54** | P0 | garantizado y medido | `scripts/triage.py:175` · `migrate` | `tests/test_triage.py:374` · `test_migrate_es_idempotente_y_no_pisa_lo_versionado` |
| **INV-55** | P1 | garantizado sin medir | `scripts/lib_config.py:1010` · `combination_rule` | `tests/test_query_ads.py:58` · `test_classify_require_faceta_obligatoria` |
| **INV-56** | P0 | garantizado y medido | — | `tests/test_lib_config.py:408` · `test_objective_error_distingue_los_tres_estados` |
| **INV-57** | P1 | garantizado y medido | `scripts/lib_config.py:30` | `tests/test_lint.py:1134` · `test_objetivo_default_warn` |
| **INV-58** | P1 | garantizado y medido | `scripts/lib_config.py:1225` · `lens_diff_offline`<br>`scripts/query_ads.py:851` · `reclass_diff` | `tests/test_lint.py:2350` · `test_lente_igual_calla`<br>`tests/test_lint.py:2361` · `test_lente_cambiada_reporta_diff_por_ficha`<br>`tests/test_query_ads.py:952` · `test_reclass_diff_reporta_el_delta` |
| **INV-59** | P0 | garantizado y medido | `scripts/query_ads.py:935` · `print_probe` | `tests/test_query_ads.py:978` · `test_reclass_diff_no_escribe_nada`<br>`tests/test_query_ads.py:1627` · `test_probe_no_escribe_nada` |
| **INV-60** | P1 | garantizado y medido | `scripts/lib_config.py:709` · `load_extra_core` | `tests/test_query_ads.py:563` · `test_fetch_bibcodes_marca_manual` |
| **INV-61** | P1 | garantizado y medido | `scripts/make_notes.py:2061` · `write_web_paper_note` | `tests/test_fetch_web.py:151` · `test_force_rebaja_la_fuente_pero_no_pisa_la_extraccion`<br>`tests/test_ingest_theme.py:253` · `test_offads_pending_deriva_sin_fallar`<br>`tests/test_make_notes.py:2575` · `test_excluded_table_no_lanza_con_un_ads_json_cortado_a_media_letra` |
| **INV-62** | P1 | garantizado y medido | `scripts/make_notes.py:927` | `tests/test_lib_config.py:112` · `test_version_unica_fuente`<br>`tests/test_make_notes.py:2312` · `test_la_nota_declara_su_version`<br>`tests/test_make_notes.py:2326` · `test_restamp_headers_no_reetiqueta_la_nota` |
| **INV-63** | P0 | HUECO (parcial) | `scripts/lint.py:492` · `normalize_lists` | `tests/test_lint.py:149` · `test_campo_de_lista_escrito_como_escalar_se_reporta_una_vez` |
| **INV-64** | P0 | garantizado y medido (los 5 cambios, 1.35.0) | `scripts/make_notes.py:520` · `migrate_all_facets`<br>`scripts/make_notes.py:562` · `migrate_all_registros`<br>`scripts/make_notes.py:609` · `migrate_all_disputes` | `tests/poblada/test_invariantes_instancia.py:334` · `test_papers_declaran_facets_no_topics`<br>`tests/poblada/test_upgrade.py:129` · `test_vintage_bloquea_con_categorias_de_schema_viejo_y_receta_visible`<br>`tests/test_make_notes.py:2356` · `test_migrate_facets_renombra_y_es_idempotente`<br>`tests/test_make_notes.py:2385` · `test_migrate_registros_pliega_sin_perder_la_corrida` |
| **INV-65** | P2 | garantizado y medido | — | `tests/test_lint.py:1168` · `test_obsidian_en_raiz_warn` |
| **INV-66** | P1 | garantizado sin medir | — | `tests/test_mailto_paridad.py:37` · `test_mailto_toma_el_email_de_git_config` |
| **INV-67** | P0 | garantizado sin medir | `scripts/lib_config.py:184` · `get_ads_token` | `tests/test_fetch_pdf.py:160` · `test_download_pdf_token_solo_a_ads`<br>`tests/test_lib_config.py:654` · `test_el_token_no_sale_en_ningun_artefacto_ni_en_la_salida`<br>`tests/test_lib_config.py:678` · `test_el_archivo_del_token_esta_gitignored` |
| **INV-68** | P2 | garantizado y medido | — | `tests/test_lib_config.py:601` · `test_gitattributes_cubre_los_archivos_de_instancia` |
| **INV-69** | P0 | parcial | — | `tests/test_make_notes.py:2551` · `test_stamp_header_no_ancla_en_un_comentario_del_frontmatter`<br>`tests/test_query_ads.py:442` · `test_query_ads_5xx_persistente_lanza` |
| **INV-70** | P1 | garantizado sin medir | `scripts/extract_fulltext.py:94` · `ocr_available` | `tests/test_extract_fulltext.py:210` · `test_flag_ocr_sin_tesseract_aborta` |
| **INV-71** | P1 | garantizado sin medir | `scripts/make_notes.py:72` · `fm` | `tests/test_make_notes.py:191` · `test_excluded_top_n_y_escapes` |
| **INV-72** | P1 | garantizado y medido | `scripts/query_ads.py:521` · `_variant_hit` | `tests/test_query_ads.py:1143` · `test_subject_in_title_no_matchea_por_prefijo_de_catalogo` |
| **INV-73** | P0 | garantizado y medido | — | `tests/test_bench_verify.py:355` · `test_el_benchmark_no_toca_el_vault` |
| **INV-74** | P1 | garantizado (1.33.0, D-55) | `scripts/bench_verify.py:229` · `seed_pairs` | `tests/test_bench_verify.py:52` · `test_seed_extrae_siembra_y_es_determinista`<br>`tests/test_bench_verify.py:296` · `test_exam_no_contiene_la_clave` |
| **INV-75** | P2 | garantizado sin medir | `scripts/bench_verify.py:297` · `cmd_score` | `tests/test_bench_verify.py:259` · `test_score_metricas` |
| **INV-76** | P0 | garantizado y medido | `scripts/lib_config.py:755` | `tests/test_fetch_ground_truth.py:355` · `test_spectral_type_solo_de_simbad` |
| **INV-77** | P1 | garantizado y medido | `scripts/lint.py:441` | `tests/test_lint.py:2089` · `test_disputa_entre_autoridades_es_expresable` |
| **INV-78** | P0 | garantizado y medido | `scripts/lib_blocks.py:3`<br>`scripts/lint.py:1273` · `collect` | `tests/test_lib_blocks.py:47` · `test_reflow_no_mueve_ancla`<br>`tests/test_lint.py:1886` · `test_reemplazo_del_txt_marca_por_fuente` |
| **INV-79** | P0 | parcial (la mitad determinista, medida) | `scripts/lint.py:1273` · `collect` | `tests/test_lint.py:1841` · `test_nota_verificada_no_marca_nada` |
| **INV-80** | P0 | garantizado y medido | `scripts/lib_config.py:268` · `yaml_error`<br>`scripts/lib_config.py:284` · `stars_error`<br>`scripts/lib_config.py:289` · `themes_error`<br>`scripts/lib_config.py:305` · `objective_error`<br>`scripts/query_ads.py:968` · `main` | `tests/test_lib_config.py:408` · `test_objective_error_distingue_los_tres_estados`<br>`tests/test_lint.py:1759` · `test_lint_objective_roto_bloquea`<br>`tests/test_lint.py:1947` · `test_stars_yaml_roto_reporta_no_evaluado_en_vez_de_reventar`<br>`tests/test_lint.py:1960` · `test_themes_yaml_roto_tambien_reporta_no_evaluado`<br>`tests/test_query_ads.py:1338` · `test_query_ads_rehusa_lente_vacia` |
| **INV-81** | P0 | garantizado y medido (1.35.0) | `scripts/make_notes.py:1226` · `papers_universe` | `tests/test_make_notes.py:1931` · `test_conteo_del_encabezado_es_el_de_la_tabla`<br>`tests/test_make_notes.py:2404` · `test_planetas_se_estampa_no_es_dataview`<br>`tests/test_make_notes.py:2428` · `test_metodos_se_estampa_con_el_recorte_correcto`<br>`tests/test_make_notes.py:2586` · `test_una_corrida_limpia_deja_el_rollup_al_dia` |
| **INV-82** | P1 | garantizado y medido (1.35.0) | `scripts/lib_config.py:813` · `save_sintesis`<br>`scripts/make_notes.py:1646` · `estado_line` | `tests/test_make_notes.py:2020` · `test_refrescar_sin_reverificar_mueve_una_sola_fecha`<br>`tests/test_make_notes.py:2481` · `test_la_cabecera_lleva_las_tres_fechas`<br>`tests/test_make_notes.py:2499` · `test_refrescar_no_mueve_la_fecha_de_sintesis`<br>`tests/test_triage.py:487` · `test_sintesis_se_declara_y_no_pisa_lo_demas` |
| **INV-83** | P0 | parcial (el canal ya está cableado) | `scripts/lib_config.py:798` · `save_extraccion`<br>`scripts/lint.py:1439` · `collect` | `tests/test_docs_ejecutables.py:287` · `test_el_alcance_de_hipotesis_tiene_invariante_propio`<br>`tests/test_lint.py:2062` · `test_subconjunto_sin_declarar_reporta`<br>`tests/test_triage.py:442` · `test_extraccion_todos_declara_el_default` |
| **INV-84** | P0 | garantizado y medido | `scripts/make_notes.py:1467` · `rename_paper` | `tests/test_make_notes.py:2141` · `test_ciclo_preprint_publicado` |
| **INV-85** | P1 | garantizado (los 5 detectores, 1.35.0) | `scripts/fetch_ground_truth.py:266` · `nea_diff`<br>`scripts/sweep_external.py:3` | `tests/test_sweep_external.py:123` · `test_detector_no_implementado_no_aporta_un_cero`<br>`tests/test_sweep_external.py:147` · `test_sweep_web_detecta_el_cambio_y_no_escribe`<br>`tests/test_sweep_external.py:208` · `test_retracciones_rc2_no_es_limpio`<br>`tests/test_sweep_external.py:264` · `test_ground_truth_ilegible_cuenta_como_fallido_no_como_sin_cambios`<br>`tests/test_sweep_external.py:279` · `test_aplicar_ground_truth_registra_que_cambio_para_que_el_lint_pida_la_marca` |
| **INV-86** | P0 | garantizado y medido | `scripts/lint.py:605` · `inferencias_sin_premisas` | `tests/test_lint.py:2220` · `test_inferencia_pelada_bloquea`<br>`tests/test_lint.py:2725` · `test_inferencia_con_wikilink_que_no_es_bibcode_no_es_premisa` |
| **INV-87** | P0 | garantizado y medido | `scripts/check_retractions.py:349` · `main` | `tests/test_check_retractions.py:533` · `test_errores_sin_retractados_exit_2`<br>`tests/test_check_retractions.py:610` · `test_corpus_sin_doi_no_sale_limpio`<br>`tests/test_citation_index.py:249` · `test_main_construye_y_reporta_la_cobertura`<br>`tests/test_lint.py:1769` · `test_lint_sin_git_reporta_no_evaluado`<br>`tests/test_lint.py:2192` · `test_config_ilegible_suprime_las_categorias_que_dependen_de_ella` |
| **INV-88** | P1 | garantizado y medido | `scripts/query_ads.py:753` · `reclassify_for_theme`<br>`scripts/query_ads.py:782` · `gate_cited_by_corpus` | `tests/test_query_ads.py:1393` · `test_puerta_2_el_fundacional_entra_sin_lente_astro`<br>`tests/test_query_ads.py:1500` · `test_main_aplica_la_regla_del_tema_a_la_query_directa`<br>`tests/test_query_ads.py:1550` · `test_puerta_1_propone_lo_que_el_corpus_cita_y_no_lo_clasifica`<br>`tests/test_query_ads.py:1585` · `test_main_puerta_1_deja_el_candidato_en_ads_json` |
| **INV-89** | P1 | garantizado y medido | `scripts/lib_config.py:875` · `load_busquedas` | `tests/test_lib_config.py:427` · `test_dos_busquedas_con_solapamiento_no_suman` |
| **INV-90** | P1 | garantizado y medido | `scripts/lib_config.py:526` · `write_text_atomic`<br>`scripts/lib_config.py:550` · `write_bytes_atomic`<br>`scripts/lib_config.py:559` · `copy_file_atomic` | `tests/test_entity.py:205` · `test_quitar_del_frontmatter_preserva_el_cuerpo_byte_a_byte`<br>`tests/test_lib_config.py:380` · `test_sin_escrituras_directas_a_vault`<br>`tests/test_lib_config.py:830` · `test_ninguna_copia_directa_al_destino_final_en_vault`<br>`tests/test_make_notes.py:1826` · `test_notas_pasan_por_el_helper` |
| **INV-91** | P1 | garantizado y medido | `scripts/check_retractions.py:338` · `_estampar`<br>`scripts/lib_config.py:958` · `load_cadena`<br>`scripts/lib_config.py:1250` · `save_paso` | `tests/test_check_retractions.py:579` · `test_slug_estampa_su_paso_en_la_cadena`<br>`tests/test_fetch_ground_truth.py:450` · `test_el_atajo_idempotente_estampa_el_paso`<br>`tests/test_lib_config.py:466` · `test_save_paso_appendea_con_fecha_version_y_via` |
| **INV-92** | P1 | garantizado y medido | `scripts/lint.py:252` · `alcance_declarado`<br>`scripts/lint.py:269` · `corpus_vigente` | `tests/test_lint.py:2480` · `test_alcance_sin_declarar_marca`<br>`tests/test_lint.py:2499` · `test_alcance_quedo_corto_marca` |
| **INV-93** | P0 | garantizado y medido | `scripts/lint.py:1321` · `collect` | `tests/test_lint.py:2168` · `test_cita_marcada_no_bloquea_y_se_lista` |
| **INV-94** | P0 | garantizado y medido | `scripts/lint.py:825` · `collect` | `tests/test_lint.py:2313` · `test_paper_sin_ningun_destino_bloquea` |
| **INV-95** | P1 | parcial (la mitad mecánica, medida) | — | — |
| **INV-96** | P1 | garantizado y medido | `scripts/lint.py:340` · `merge_ours_unprotected`<br>`scripts/query_ads.py:649` · `to_record` | `tests/test_backends_schema.py:57` · `test_el_registro_tiene_exactamente_las_claves_del_schema`<br>`tests/test_search_arxiv.py:142` · `test_main_es_preview_clasifica_con_la_lente_y_no_escribe_nada` |
| **INV-97** | P1 | garantizado y medido | `scripts/lint.py:386` · `inventario_sin_llenar` | `tests/test_section_anchor.py:84` · `test_inventario_lleno_no_se_reporta_como_plantilla` |
| **INV-98** | P0 | garantizado y medido | `scripts/lib_config.py:162` · `section_start` | `tests/test_section_anchor.py:65` · `test_section_start_saltea_la_mencion_en_prosa` |
| **INV-99** | escapado dentro de una celda no corre las columnas, y una fila que igual no cuadra con el encabezado no se indexa por posición. | P0 | `scripts/lib_blocks.py:303` · `_split_row` | `tests/test_section_anchor.py:126` · `test_pipe_escapado_en_una_celda_no_corre_las_columnas` |
