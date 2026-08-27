# Cómo se lee y se cita el `.txt` — las convenciones, con su medición

**Referencia de `verify-citations`.** El `SKILL.md` deja las **reglas duras en una línea** (contar
con `grep -n`, patrones cortos, prohibido normalizar espacios, `symbols_lost` ⇒ página del PDF, OCR y
`eprint` con su salvedad). Acá está **por qué** cada una existe y qué se midió — que es lo que hay
que leer la primera vez, cuando una regla parece arbitraria, o cuando un par no cierra y hay que
decidir si es artefacto de extracción o cita rota.

Estas convenciones son **canónicas para toda la bóveda**: `ingest-star`, `ingest-theme`,
`test-hypothesis`, `query-corpus` y `find-contradictions` apuntan acá en vez de repetirlas.

**Ventaja del corpus cerrado:** corpus **cerrado** — hay un `.txt` por bibcode en `vault/raw/fulltext/`. Se
saltea el *retrieval* (la parte que mete errores en los verificadores generales): ya sabemos qué
archivo leer. El chequeo es directo passage-matching.

**El fulltext es una extracción DETERMINISTA** de la capa de texto del PDF (`pdftotext -layout`,
sin LLM). Por eso la **cita textual que encuentra el verificador son las palabras reales del
paper** y el nº de línea es un localizador greppable estable. **Caveats:** `pdftotext` puede
desordenar doble-columna, ecuaciones, tablas, ligaduras y guionado; y un PDF **escaneado sin capa de
texto** da `.txt` vacío/basura. Por eso: si una afirmación **no** aparece textual en el `.txt` —
**tras agotar la estrategia de matcheo de abajo (#44)** — antes
de declararla `no-soportada` considerar que puede ser un **artefacto de extracción** (ecuación/tabla)
→ en ese caso abrir el **PDF** (`vault/raw/pdfs/<slug>/<bibcode>.pdf`) para esa afirmación puntual, o
marcarla **`no verificable por extracción`** (distinto de `no-soportada`).

**Cómo se cuentan las líneas (convención fija, #29):** el nº de línea de la evidencia se obtiene
con **`grep -n`** o leyendo el archivo directamente (Read) — **no** con `splitlines()` de Python:
los `.txt` de `pdftotext` traen un **form feed** (`\x0c`) por página que Python cuenta como salto
de línea extra → la numeración se corre **+1 por página** y el error CRECE a lo largo del archivo
(medido: 532/535 `.txt` del corpus con form feeds; en un paper de 12 páginas la última cita queda
~10 líneas afuera — suficiente para que una revisión posterior no encuentre la frase y la marque
como rota). Si hace falta Python, `split("\n")` numera igual que `grep -n`.
Relacionado: en papers a **dos columnas** `pdftotext -layout` entrelaza ambas columnas en la misma
línea física — un rango de líneas **no** es un rango de lectura contigua (una oración puede
arrancar en la columna izquierda de L229 y seguir en la derecha de L204). Los números de línea
son **punteros greppables**, no extractos para leer de corrido.

**Cómo buscar en el `.txt` (estrategia de matcheo, #44).** El entrelazado de arriba obliga a
buscar distinto: `grep` es orientado a líneas, y en un `.txt` multi-columna (medido: 472/644 del
corpus, 73%) una oración cruza el salto de línea física — buscarla entera da **falso negativo**
aunque el texto esté y sea legible (medido: 9/24 pares ~38% no encontrados con la oración
completa; 24/24 localizados con fragmentos cortos).
1. **Escalera de acortamiento:** empezar por la oración completa y, si no aparece, acortar a un
   **fragmento distintivo contenido en una sola línea física** (típicamente 3–6 palabras; el largo
   útil depende del ancho de columna del PDF, por eso se **acorta hasta encontrar** en vez de fijar
   un largo — así un paper a una columna sigue matcheando la frase entera sin perder precisión).
2. **De-hifenado:** si el fragmento corto tampoco aparece, el corte de línea puede partir una
   palabra con guión (`mag-` / `nitude`): reintentar partiendo el patrón por el guión, o buscar
   un fragmento que lo esquive.
3. Sólo **agotados 1 y 2** corresponde considerar artefacto de extracción (ecuación/tabla/escaneo)
   → abrir el PDF o marcar `no verificable por extracción`.

⛔ **Prohibido normalizar espacios sobre el archivo entero** (`re.sub(r"\s+", " ", texto)` o
equivalente): en una línea física a dos columnas eso **empalma el final de la columna 1 con el
principio de la columna 2**, fabricando adyacencias que el paper no tiene — puede hacer pasar como
`soportada` una afirmación **inventada** (falso positivo: el modo peligroso, peor que el falso
negativo de arriba). Y normalizar **por línea** tampoco alcanza (#46): colapsar la **canaleta** de
la misma línea física fabrica la misma adyacencia col.1→col.2, sólo que dentro de la línea. La
forma segura, si hace falta normalizar: **partir antes cada línea física en la canaleta** (un run
de 8+ espacios es separador de columnas, no espacio — el umbral vive en
`measure_layout.CANALETA_MIN`) y normalizar **por segmento de columna**. Los invariantes están
pineados en `tests/test_multicolumn_matching.py`; la prevalencia en una bóveda concreta la mide
`scripts/measure_layout.py`.

⚠ **`symbols_lost: true` — las ECUACIONES no están en el `.txt` (#113).** Si la nota del paper
trae ese campo (o el `.txt` abre con `# Almagesto — simbolos NO extraidos`), `pdftotext` dejó el
marcador `(3)` y **vació su cuerpo**: el archivo parece tener la fórmula y no la tiene. Para esos
pares, **la evidencia se cita por PÁGINA del PDF**, no por nº de línea, y se lee
`vault/raw/pdfs/<slug>/<bibcode>.pdf` con el parámetro `pages` (que **rasteriza** la página, así
que el verificador *ve* la fórmula). ⛔ **No declares `no-soportada` una ecuación que no aparece
en el `.txt` de una fuente marcada así** — es el falso negativo que empuja a debilitar una
afirmación correcta, y es exactamente el caso que este campo existe para señalar. La **prosa** de
esas fuentes sí es citable por línea, como siempre.

**Excepción OCR — citable con salvedad:** si la nota del paper trae `fulltext_source: ocr` (el
contrato del frontmatter lo espeja — no hace falta abrir el `.txt` para saberlo) o el `.txt` abre
con el header `# Almagesto — fulltext por OCR` (`source: ocr`), vino de tesseract (PDF escaneado
o con fuentes sin ToUnicode que
`pdftotext` no pudo leer; lo estampa `extract_fulltext.py`). Sigue siendo determinista y citable,
pero el OCR puede errar **símbolos, ligaduras y notación matemática**: la verificación vale para
**prosa**; ante una discrepancia puntual de símbolos/números en una ecuación, abrir el **PDF** para
esa afirmación en vez de declararla `no-soportada`/`contradice`.

⚠ **Excepción preprint — el `.txt` puede ser OTRA VERSIÓN del paper (#57).** Si la nota trae
`pdf_source: eprint` (y, cuando se conoce, `eprint_version: v1`), el texto salió de **arXiv**, no
de la versión publicada que identifica el `[[bibcode]]`. Un **v1 pre-referato** puede traer
valores, secciones y hasta conclusiones distintas. El daño va en la dirección **menos obvia**:
ante una discrepancia entre la nota (valor **publicado** — típicamente de NEA o del abstract de
ADS) y el `.txt` (eprint), el protocolo de acá manda "bajar la afirmación a lo que dice la
fuente" → **se corrompería el valor publicado con el del preprint, y quedaría registrado como un
hallazgo del chequeo**. Regla: con `pdf_source: eprint`, una discrepancia **numérica** contra un
valor publicado es candidata a **diferencia de versión**, no a cita rota → abrir el PDF publicado
para esa afirmación, o marcarla como diferencia de versión; **no** "corregir" la nota hacia el
eprint. Con `pdf_source: null` (desconocido: ni marca de arXiv ni registro del fetcher) aplicá el
mismo cuidado ante una discrepancia numérica — desconocido **no** es "publicado". La prosa y los
mecanismos se verifican igual.
