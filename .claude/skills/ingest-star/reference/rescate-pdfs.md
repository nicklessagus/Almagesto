# Rescate de PDFs que la cadena no pudo bajar (canónico)

**Referencia de `ingest-star`, compartida.** `ingest-theme` y `append-knowledge` apuntan acá por
`.claude/skills/ingest-star/reference/rescate-pdfs.md` — canónica en un solo lugar, sin copia. Ver
también el backlog en `vault/STATUS.md`.

Esto se lee **cuando `build/<slug>/missing_pdf.json` quedó con entradas**, no antes: es casuística
—qué editorial cede el PDF por qué puerta, con qué medición— y no prescripción de la cadena. La
mecánica de `fetch_pdf` y del residuo está en `reference/cadena-ads.md`.

## Cascada manual de adquisición (PDFs no-arXiv)

Lo que quedó en `build/<slug>/missing_pdf.json` **ya falló** en `fetch_pdf.py` (resolver ADS:
`EPRINT_PDF` → `ADS_PDF` con token → `PUB_PDF`, con fallback `curl`), y "bajar manual por DOI" **no
alcanza** (medido en un ingest real: el resolver falló en **5 de 17** — pre-arXiv de 2000–2015:
SPIE, The Messenger, A&A viejo; **4 de 5 se recuperaron** por estas ramas). `fetch_pdf` imprime el
**bibstem** de cada fallo con la rama sugerida y la deja en el `hint` de cada entrada del residuo.

⛔ **Mirá primero el `estado` de cada entrada (#358).** Desde 1.190.0 `fetch_pdf` recorre además la
cascada de acceso abierto (OpenAlex → Unpaywall → Europe PMC → arXiv por título exacto) antes de
rendirse, y el residuo lo dice: `estado: sin-copia-libre` (no hay copia libre en ninguno: rescate
manual o `pending`) o `estado: bloqueado` con `copias_libres: [url…]` (la hubo y el host no entregó
un PDF —típico: desafío de Cloudflare con 200—: probá bajarla a mano desde esa URL antes de
cualquier otra cosa). Medido: 2 de 6 «sin conseguir» de un tema eran open access.

En orden de rendimiento:

1. **Archivo de The Messenger** (`Msngr`) — **todo el Messenger es abierto**:
   `eso.org/sci/publications/messenger/archive/no.<N>-<mes><aa>/messenger-no<N>-<pp>-<pp>.pdf`.
2. **Página de papers del instrumento** (`SPIE` y proceedings en general) — p. ej.
   `eso.org/sci/facilities/lasilla/instruments/<inst>/science/papers/<vol>-<pp>.pdf`: tiene **en
   abierto** SPIE que de otro modo son paywall.
3. **Mirrors académicos** por búsqueda web (páginas personales, repositorios institucionales).
4. **Imágenes de tabla del CDN del publisher** (p. ej. IOP
   `content.cld.iop.org/journals/.../tbN.gif`) — **funcionan aunque el PDF esté tras paywall** y
   suelen tener el dato que se busca; ídem el HTML legacy del publisher (frameset `…/fulltext/`).
5. **Pedir el PDF al usuario** (tiene acceso institucional; anduvo con Frick 2004 y Saar 1999) —
   mientras tanto, estampá `pending_source: paywall` en el frontmatter de la nota del paper (el
   lint la lista como precondición hasta que la fuente llegue).

Guardá el artefacto citable (PDF o imagen de tabla) en `vault/raw/`.

⛔ **No gastar intentos en `aanda.org`:** está detrás de **DataDome** — cualquier `curl` (con UA de
navegador, con `Referer`, siguiendo redirects) recibe un challenge JS (`Please enable JS…`,
`ct.captcha-delivery.com`). Para un **A&A pre-arXiv** que el resolver no entrega no hay preprint y
Semantic Scholar lo da `openAccessPdf: CLOSED` → **derivar al usuario de una** (se resuelve en una
vuelta con acceso institucional).

## OCR y quirks de extracción

**Lo maneja solo `extract_fulltext.py`.** Chequea si el PDF trae **capa de texto** legible (umbral
determinista: chars no-espacio, **densidad por página** y fracción de ASCII imprimible) y, si no
(escaneos-imagen puros, p. ej. Baliunas 1995, o fuentes sin ToUnicode), **cae solo a OCR** cuando hay
`tesseract` instalado — el `.txt` queda con header `source: ocr`, **citable con salvedad** (ver
`docs/operacion.md`); sin tesseract AVISA y el lint lo lista. Ojo con quirks de PostScript viejo en
la extracción (p. ej. el signo `-` y `>` pueden salir ambos como `[`): los datos están, sólo hay que
desambiguar por contexto.

⚠ **Síntoma "escaneo con marca de agua"**: un `.txt` de unos **cientos de bytes** con el **bibcode
repetido** una vez por página **no es un fallo de descarga** — el `ADS_PDF` bajó bien, pero es un
escaneo **sin capa de texto** cuya única capa es la marca de agua de ADS. Lo agarra la **densidad por
página** del umbral (#50; antes pasaba como "extraído" porque el poco texto que hay *es* legible) →
dispara el OCR como cualquier escaneo. Si te topás con un `.txt` viejo así, re-extraé con
`python scripts/extract_fulltext.py <slug> --ocr --force`. Caso medido: Baranne+1996, 378 bytes →
77 KB por OCR (`fulltext_source: ocr`).

## Cuándo NO insistir: un 0 no prueba ausencia

Un `full:"HD X" → 0` **no prueba ausencia** en papers pre-digitales: el **OCR del escaneo de ADS
pierde ~½ de las filas** (medido: 12/26 estrellas en Saar & Brandenburg 1999; faltaba hasta
HD 81809). Nunca afirmar "la estrella no está en ese paper" desde un hit full-text negativo —
**corroborar** (papers que lo citan y le atribuyen datos) o **abrir el PDF/tabla**. Reportar honesto:
es inconcluso, no ausencia.

Y en la misma línea: **mirá las TABLAS, no sólo el texto.** En papers viejos las tablas suelen ser
**imágenes** (en el escaneo de ADS y a veces hasta en el HTML del publisher). El dato de la estrella
(P_cyc, P_rot, rama…) vive ahí → **invisible a cualquier búsqueda de texto**. Para confirmar si una
estrella está en un paper y para extraer sus valores, **abrí la tabla** (imagen o PDF), no te fíes
del grep.
