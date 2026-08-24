# Lint de la bóveda — <FECHA>

## ⛔ No evaluado: el chequeo no pudo correr (hecho del ENTORNO, no de la bóveda — cuenta para el exit) (0)

## Wikilinks rotos (página faltante) (0)

## ⛔ Frontmatter no parseable o con forma inválida (la nota evade los chequeos de su tipo) (0)

## ⛔ Papers RETRACTADOS citados (frontera dura: fuente no válida) (0)

## Notas huérfanas (sin links entrantes) (2)
- concepto-activity-017
- concepto-methods-018

## Papers con corrección publicada (erratum/corrigendum/EoC) — revisar los valores extraídos de ellos (backlog, el paper sigue siendo citable) (0)

## Contradicciones ground-truth ↔ ficha (0)

## Ground-truth: masa inconsistente con m·sini (K,P,e,M*) (0)

## thesis_links sin página destino (2)
- tema-fantasma-0054 → usado en 1 paper(s): 2021Alm00054A
- tema-fantasma-0055 → usado en 1 paper(s): 2019Alm00055A

## disputes: ref de una posición sin paper destino (2)
- concepto-hypotheses-015 → disputa `eje-sintetico`: ref `__nota_inexistente_0015__` sin nota de paper
- concepto-indicators-016 → disputa `eje-sintetico`: ref `__nota_inexistente_0016__` sin nota de paper

## disputes mal formadas (posiciones explícitas, #71) (0)

## disputes en el schema viejo (planets[].disputes[]) — el lint ya no las lee (0)

## Juicio de triage en build/<slug>/triage.json (pre-1.9.0) — el lector ya no lo mira (0)

## ⛔ Registro con `busqueda:` (schema viejo pre-D-28) — el lector ya no lo lee (0)

## `role` fuera del vocabulario (fundacional/aplicacion/arbitro) (0)

## ⚠ Fuga de implementación (código no bibliográfico) → frontera dura (WARN, revisar a mano) (0)

## Objetivo sin instanciar (WARN — objective.yaml sigue en el placeholder del template) (0)

## Áreas de concepts/ no declaradas en objective.yaml (WARN, posible typo) (0)

## Obsidian en la raíz del repo (WARN — la bóveda se abre en vault/) (0)

## PDF ↔ disco / cuerpo (WARN — higiene: frontmatter `pdf` vs PDF bajado vs link de cabecera) (0)

## ⏳ Fuentes pendientes (pending_source — el usuario debe proveer la fuente) (0)

## Fulltext ilegible (mojibake/escaneo — existe pero no sirve para grep/verify) (2)
- fulltext/star01/2002Alm00058A.txt → casi sin texto (1 chars no-espacio) — ¿escaneo sin capa de texto?
- fulltext/star02/2021Alm00059A.txt → casi sin texto (1 chars no-espacio) — ¿escaneo sin capa de texto?

## Citas no verificables en query/concepto/hipótesis (sin fulltext) (6)
- concepto-activity-005 → cita 1997Alm00015A sin fulltext (no chequeable claim↔fuente)
- concepto-activity-013 → cita 2002Alm00051A sin fulltext (no chequeable claim↔fuente)
- concepto-indicators-000 → cita 2021Alm00000A sin fulltext (no chequeable claim↔fuente)
- concepto-indicators-004 → cita 2004Alm00014A sin fulltext (no chequeable claim↔fuente)
- query-000 → cita 2021Alm00000A sin fulltext (no chequeable claim↔fuente)
- query-001 → cita 2015Alm00001A sin fulltext (no chequeable claim↔fuente)

## Sin verificar: query/concepto con citas pero sin bloque verify-citations (backlog) (16)
- concepto-activity-001 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-activity-005 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-activity-009 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-activity-013 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-hypotheses-003 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-hypotheses-007 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-hypotheses-011 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-indicators-000 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-indicators-004 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-indicators-008 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-indicators-012 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-methods-002 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-methods-006 → 1 cita(s) sin bloque de verify-citations → correr el skill
- concepto-methods-010 → 1 cita(s) sin bloque de verify-citations → correr el skill
- query-000 → 1 cita(s) sin bloque de verify-citations → correr el skill
- query-001 → 1 cita(s) sin bloque de verify-citations → correr el skill

## ⛔ Bloque de verificación con plantilla vieja (sin columnas de hash — no evaluable) (0)

## Pares de verificación vencidos (backlog: pasada periódica; con `--cierre` bloquea) (0)

## Verificación stale: la nota se editó después de su último verify-citations (backlog) (0)

## Cobertura: concepto/hipótesis sin citas [[bibcode]] (backlog) (7)
- concepto-activity-017 → sin citas [[bibcode]] → afirmaciones no chequeables (cobertura)
- concepto-hypotheses-015 → sin citas [[bibcode]] → afirmaciones no chequeables (cobertura)
- concepto-hypotheses-019 → sin citas [[bibcode]] → afirmaciones no chequeables (cobertura)
- concepto-indicators-016 → sin citas [[bibcode]] → afirmaciones no chequeables (cobertura)
- concepto-indicators-020 → sin citas [[bibcode]] → afirmaciones no chequeables (cobertura)
- concepto-methods-014 → sin citas [[bibcode]] → afirmaciones no chequeables (cobertura)
- concepto-methods-018 → sin citas [[bibcode]] → afirmaciones no chequeables (cobertura)

## Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog) (2)
- 1996Alm00057A → extraído (`methods` poblado) pero su bibcode no está citado en ninguna ficha ni concepto → sintetizarlo donde corresponda, o marcar `no_sintetizado: <motivo>` en la nota del paper
- 2019Alm00056A → extraído (`methods` poblado) pero su bibcode no está citado en ninguna ficha ni concepto → sintetizarlo donde corresponda, o marcar `no_sintetizado: <motivo>` en la nota del paper

## Cabecera no estampable: ficha/concepto sin la línea del generador — los estampadores de cabecera no-opean en silencio (backlog) (2)
- star01 → sin la línea `_Generado con Almagesto v…_`: los estampadores de cabecera no pueden actuar → `python scripts/make_notes.py --restamp-headers`
- star02 → sin la línea `_Generado con Almagesto v…_`: los estampadores de cabecera no pueden actuar → `python scripts/make_notes.py --restamp-headers`

## Triage pendiente: candidatos del chaining sin juzgar (backlog) (0)

## Corpus truncado: la query directa trajo menos de lo que ADS reporta (backlog) (0)

## Decisión del registro con forma inválida — load_decisiones la descarta en silencio, el triage la vuelve a proponer sin el motivo (backlog) (0)

## Campos incompletos (33)
- 1996Alm00057A → paper extraído sin `role` (fundacional/aplicacion/arbitro) → sin rol, contrastarlo contra otro no está definido
- 1997Alm00015A → paper extraído sin `role` (fundacional/aplicacion/arbitro) → sin rol, contrastarlo contra otro no está definido
- 1997Alm00036A → paper relevante sin methods (sin extraer)
- 2000Alm00026A → paper relevante sin methods (sin extraer)
- 2000Alm00039A → paper relevante sin methods (sin extraer)
- 2002Alm00012A → paper relevante sin methods (sin extraer)
- 2002Alm00017A → paper extraído sin `role` (fundacional/aplicacion/arbitro) → sin rol, contrastarlo contra otro no está definido
- 2002Alm00058A → paper relevante sin methods (sin extraer)
- 2003Alm00021A → paper relevante sin methods (sin extraer)
- 2003Alm00046A → paper extraído sin `role` (fundacional/aplicacion/arbitro) → sin rol, contrastarlo contra otro no está definido
- 2004Alm00014A → paper extraído sin `role` (fundacional/aplicacion/arbitro) → sin rol, contrastarlo contra otro no está definido
- 2006Alm00027A → paper relevante sin methods (sin extraer)
- 2006Alm00028A → paper relevante sin methods (sin extraer)
- 2009Alm00044A → paper relevante sin methods (sin extraer)
- 2012Alm00040A → paper relevante sin methods (sin extraer)
- 2013Alm00006A → paper relevante sin methods (sin extraer)
- 2014Alm00002A → paper relevante sin methods (sin extraer)
- 2014Alm00037A → paper relevante sin methods (sin extraer)
- 2015Alm00001A → paper relevante sin methods (sin extraer)
- 2015Alm00023A → paper relevante sin methods (sin extraer)
- 2016Alm00011A → paper relevante sin methods (sin extraer)
- 2016Alm00030A → paper relevante sin methods (sin extraer)
- 2016Alm00052A → paper relevante sin methods (sin extraer)
- 2017Alm00008A → paper relevante sin methods (sin extraer)
- 2017Alm00049A → paper relevante sin methods (sin extraer)
- 2018Alm00041A → paper relevante sin methods (sin extraer)
- 2019Alm00013A → paper extraído sin `role` (fundacional/aplicacion/arbitro) → sin rol, contrastarlo contra otro no está definido
- 2021Alm00054A → paper relevante sin methods (sin extraer)
- 2021Alm00059A → paper relevante sin methods (sin extraer)
- 2022Alm00018A → paper extraído sin `role` (fundacional/aplicacion/arbitro) → sin rol, contrastarlo contra otro no está definido
- 2024Alm00033A → paper extraído sin `role` (fundacional/aplicacion/arbitro) → sin rol, contrastarlo contra otro no está definido
- star01 → sin P_rot: NEA no lo trae y el cuerpo no documenta uno citado → buscarlo en la literatura y dejarlo en la prosa con su `[[bibcode]]` (el frontmatter NO se rellena)
- star02 → sin P_rot: NEA no lo trae y el cuerpo no documenta uno citado → buscarlo en la literatura y dejarlo en la prosa con su `[[bibcode]]` (el frontmatter NO se rellena)
