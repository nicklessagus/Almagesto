# Validación en la instancia — qué revisar antes de cerrar cada issue

Para el agente **validador** de una bóveda poblada (`Almagesto-Tesis`): el template implementa y
pushea; la instancia mergea (`docs/migracion-instancia.md` §0), **valida contra su contenido real**,
y **cierra el issue en GitHub con la medición** — o lo devuelve con lo que falló. Acá va, por
issue, qué entró, cómo validarlo y qué cuenta como «devolver».

⛔ **Sin medición no se cierra.** Un issue nació de un caso medido en la instancia; se cierra cuando
ese caso, corrido de nuevo, hace lo que el fix promete. Lo que no se pudo correr se declara.

Acumulativo por tanda; la sección de la guía de migración que corresponde va nombrada.

---

## T4 (resto) · v1.189.0–v1.190.0 — guía §2g

### #361 · anclaje con traceback + `descubrimientos` que nadie leía

**Qué entró.** (a) `_preview_theme` envuelve `anchored_records` como `cascade` a cada backend: fila
`anclaje` en la cobertura (impresa y registrada), y la línea de cierre sale aunque OpenAlex esté
en 429. (b) Categoría backlog `cascada_sin_correr` (población: temas) con tres estados; sólo temas
`source:` ≠ `ads`.

**Validar.**
```bash
python scripts/lint.py | grep -A4 "cascada de descubrimiento"
python scripts/discover.py --theme icasso      # con OpenAlex sin presupuesto: debe terminar en
                                               # «→ todo esto son CANDIDATOS», con «anclaje FALLÓ»
python -c "import yaml;print(yaml.safe_load(open('vault/config/registro/icasso.yaml'))['descubrimientos'][-1]['cobertura'])"
```
Esperado: lint con **2** hallazgos (`icasso`: openalex FALLÓ; `rv-doppler`: nunca corrió), el
comando sin traceback, y la última entrada del registro con la clave `anclaje`.

**Devolver si:** el lint reporta `ica` o `ica-ruido` (sus cascadas corrieron con los tres
backends), o si `discover --theme` sigue muriendo con traceback con OpenAlex caído.

**Al cerrar, dejar:** los dos slugs reportados y el estado de cada uno; la cobertura de la
corrida nueva de `icasso`.

### #358 · el carril ADS no consultaba el resolver OA; Europe PMC

**Qué entró.** `fetch_pdf` recorre `discover.iter_pdf_candidates` (OpenAlex → Unpaywall → Europe
PMC → arXiv por título exacto) al agotar los `esource`; prueba **todos**; el residuo lleva
`estado` (`sin-copia-libre` | `bloqueado`) y `copias_libres`; `pdf_source` sólo cuando el
candidato lo sabe. `download_pdf`/`_curl_pdf` ya validaban `%PDF` (test que lo fija).

**Validar.**
```bash
python scripts/fetch_pdf.py icasso
python scripts/extract_fulltext.py icasso
python scripts/lint.py
```
Esperado: bajados **2** (`2022PLoSO..1770556W` por OpenAlex/PLoS; `2019Bioin..35.4307C` con la
URL de OUP marcada «no entregó PDF» y luego Europe PMC), `pdf:` y `fulltext:` estampados en las
dos notas, `missing_pdf.json` sin entradas (o con `estado` en cada una). Los PDF con `%PDF` al
inicio (`head -c4`). Cerrar el ciclo del tema: extracción de los dos con la lente de `icasso`.

**Devolver si:** alguno de los dos sigue «sin conseguir» con copia libre (mirar `copias_libres`
del residuo y decir cuál URL falló y qué devolvió), o si un `.pdf` escrito no arranca con `%PDF`.

**Al cerrar, dejar:** bibcode → depósito que lo entregó y tamaño; `pdf_source` de cada uno.

⚠ Ninguno de los dos issues toca contenido: no hay prosa que re-verificar. Tras `fetch_pdf`,
los dos papers cambian de estado en el roll-up de `icasso` (`sin extraer` → lo que sigue).
