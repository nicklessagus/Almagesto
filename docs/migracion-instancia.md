# Guía de migración para una bóveda instanciada

Qué revisar **en tu bóveda** cuando traés una versión nueva del framework. Un fix del template puede
dejar en la instancia tres cosas distintas, y sólo la primera se arregla sola al mergear:

| | qué es | quién lo arregla |
|---|---|---|
| **código** | el script se comporta distinto | el merge |
| **artefacto** | una nota, un registro o el `log` quedaron con el defecto ya escrito adentro | **vos, con esta guía** |
| **hábito** | el comando que venías corriendo ya no es el correcto | vos, leyendo la sección |

⛔ **Esta guía es acumulativa y va por versión.** Corré sólo las secciones **posteriores** a la
versión que tenías. La versión de tu bóveda está en `scripts/lib_config.py`
(`ALMAGESTO_VERSION`) — la del framework que tenés, no la del contenido.

⚠ Cada sección declara **qué mide** y **qué NO**: un chequeo que no puede correr sale *no evaluable*
con su motivo, nunca en verde (D-43).

---

## 0 · Cómo traer esta versión (cambió, #390)

```bash
git fetch upstream
git -c merge.ours.driver=true merge upstream/main
```

⛔ **No registres el driver en el clon.** Hasta 1.171.0 el `README` mandaba
`git config merge.ours.driver true` «una vez por clon» y el lint lo **exigía**. Es una regla por
**path**, y git no puede condicionarla por remoto: contra `upstream` protege tus archivos de
instancia, y contra `origin` —tu otra máquina— **descarta en silencio lo que traiga el remoto**, sin
conflicto y sin aviso. Pasándolo por comando tenés la protección donde la querés y el conflicto
—visible, con las dos versiones— donde lo necesitás. Medido en repos sintéticos, los cuatro
escenarios están en `tests/test_merge_ours_driver.py`.

**Chequeo (una vez):**

```bash
git config --get merge.ours.driver        # no debe imprimir nada
git config --unset merge.ours.driver      # si imprimió `true`
```

Desde 1.172.0 el lint **bloquea** el clon que lo tenga registrado y tenga `origin`.

### 0.1 · Auditar si algún merge anterior te comió contenido

Si alguna vez tuviste el driver registrado **y** mergeaste `origin` (trabajo entre dos máquinas),
puede haber pérdida silenciosa en el historial. Esto la encuentra:

```bash
git fetch upstream
git log --merges --format=%H | while read m; do
  p2=$(git rev-parse -q --verify "$m^2") || continue
  git merge-base --is-ancestor "$p2" upstream/main && continue   # merge del TEMPLATE: descartar lo suyo es lo correcto
  mb=$(git merge-base "$m^1" "$p2")
  for f in vault/wiki/log.md vault/STATUS.md vault/wiki/index.md \
           vault/config/objective.yaml vault/config/stars.yaml vault/config/themes.yaml \
           vault/wiki/matrices/method_star.md; do
    git diff --quiet "$mb" "$p2" -- "$f" && continue   # el remoto no lo cambió: no hay nada que descartar
    if git diff --quiet "$m" "$m^1" -- "$f"; then
      echo "⛔ $(git log -1 --format='%h %ad' --date=short $m)  $f"
    fi
  done
done
```

Dice: *el remoto cambió ese archivo respecto del ancestro común y el merge conservó tu versión byte
a byte* — o sea, lo del otro clon se descartó. Dos filtros, y los dos hacen falta:

- **contra `upstream`**: descartar lo del template **es** lo que `merge=ours` promete, así que ahí
  no hay hallazgo;
- **contra el `merge-base`**, no contra tu propio padre: comparar las dos ramas entre sí marca todo
  archivo donde **sólo avanzó tu máquina**, que es el caso normal y no una pérdida. Sin este filtro
  el auditor sobre-reportaba, medido: 2 de 4 hits eran de esa clase.

⛔ **Un hallazgo NO es pérdida por sí solo: depende del artefacto.** Los tres se comportan distinto
y confundirlos hace perder tiempo o, peor, restaurar estado viejo encima del vigente:

| artefacto | contrato | qué significa un hallazgo |
|---|---|---|
| `vault/wiki/log.md` | **append-only** | **pérdida real**: lo appendeado por la otra máquina no está. Recuperar del historial |
| `vault/STATUS.md` | **se reescribe** (#302) | casi seguro **estado superado**: mirá la FECHA del STATUS actual, no las líneas |
| `vault/wiki/index.md` | **se estampa** | **regenerable**: `python scripts/make_notes.py --restamp-index` |
| `vault/config/*.yaml`, `matrices/method_star.md` | curación | **pérdida real**: recuperar del historial |

Para recuperar lo appendeado de un `log` (el único caso donde el diff se lee derecho):

```bash
git diff <merge>^1 <merge>^2 -- vault/wiki/log.md    # lo que traía el remoto
```

y appendear a mano lo que falte, en su fecha. **No** `git checkout` del archivo entero: te llevás
puesto lo tuyo.

> **Medido en una bóveda real** (`Almagesto-Tesis`, 2026-09-03): 58 merges revisados, **1** con
> descarte (2026-09-02, el incidente que produjo #390), sobre **2** archivos —`log.md` y
> `STATUS.md`—. Resultado del triage: el `log` se había recuperado a mano (0 líneas faltantes) y el
> `STATUS.md` era **estado superado por contenido más nuevo** — 0 daño vivo.
>
> ⚠ La primera versión de este auditor reportaba **4**: `index.md` y `themes.yaml` entraban sin que
> el remoto los hubiera tocado, y la tabla de abajo los clasificaba como «regenerable» y «pérdida
> real» — o sea que mandaba a buscar en el historial algo que nunca se perdió. Lo cazó el revisor
> de la instancia; el filtro por `merge-base` es lo que lo cierra.

---

## 1 · v1.173.0 (#386/#387) — el barrido global de citas

**Qué cambió.** `contrast.py --validar-todo` ahora conoce las dos formas en que el `log` se corrige
sin editarse: la marca `⚠ corregido <fecha> → <entrada nueva>` (#238) y la cita dentro de un
**blockquote**, que es *mención* y no afirmación de la bóveda (#387). Antes las ignoraba, así que una
entrada corregida **exactamente como el framework manda** bloqueaba el gate para siempre.

**Y es pasada periódica declarada**, no sólo paso de cierre:

```bash
python scripts/contrast.py --validar-todo        # SIN slug: toda la bóveda
```

⚠ **Sin slug.** El paso de cierre de cada operación lo corre **con** el slug del sujeto, que mira
sólo sus notas: medido, el acotado daba `0` mientras el global daba `1`, con cuatro sujetos cerrados
en verde sobre un gate que nunca lo estuvo. Si nunca corriste el global, corrélo ahora.

**Qué esperar.** Las citas del `log` ya marcadas dejan de contar, declaradas en la línea de
población como *declarada(s) y resuelta(s)*. Medido en `Almagesto-Tesis`: de **70** citas del `log`,
**7** quedan exentas por la marca y **3** por blockquote.

**Qué hacer con lo que quede:**

- Una cita alterada se corrige **copiándola del JSON de extracción**
  (`python scripts/contrast.py <slug> --grep "<re>"`), nunca re-tipeándola (#322) y nunca contra el
  `.txt`, que es índice degradado.
- Una entrada vieja del `log` que quedó refutada: **marcala**, no la edites, y poné la marca
  **pegada a la afirmación** (misma línea o continuación del mismo bullet) — una marca en el
  encabezado `##` exime el encabezado, no un bullet cuatro líneas abajo.
- Una entrada que **cita** una cita defectuosa para explicarla: ponela en **blockquote**.

**Artefacto nuevo, commitealo:** `vault/config/registro/_citas.yaml` — cuándo se miró la coherencia
de citas, igual que `_red.yaml` para la caducidad de red. Sólo lo escribe la pasada **global**.

---

## 2 · v1.174.0 (#363) — cambió un mensaje del lint, no tu bóveda

**Qué cambió.** El backlog *«la nota se apoya en el PREPRINT habiendo versión publicada»* (#298) ya
no arrastra una premisa que el código había retirado en 1.111.0: el `else` de `pdf_source: eprint`
dejó de apagar el chequeo de cita textual y nueve lugares seguían diciendo que sí, uno de ellos el
texto que el lint imprime.

**Qué hacer en tu bóveda: nada.** El hallazgo sigue siendo válido por su otra mitad —la nota lee el
preprint teniendo publicado— y la acción sigue siendo la misma (`fetch_pdf.py <slug> --force`, o
dejar la salvedad). Lo que cambia es el costo/beneficio que venías calculando: **no** hay agujero de
verificación asociado.

**Chequeo, por si la premisa se copió a contenido tuyo:**

```bash
grep -rn "exime del chequeo\|exención que apaga" vault/
```

Sin salida = no se propagó. Si aparece en una nota o en `STATUS.md`, corregí esa frase (en el `log`
se **marca**, no se edita).

> Medido en `Almagesto-Tesis`: 0 hits en `vault/`, sobre 117 notas con `pdf_source: eprint`.

---

## 2b · v1.175.0-v1.177.0 (#374 · #371 · #372) — la cadena de la segunda lente

Los tres arreglan el mismo ciclo: el **archivo** donde escribe una segunda lectura, la **identidad**
con que se la lee, y los **ejes** que su vista declara. Sólo el primero deja algo que revisar en el
contenido, y es el que más importa.

### #374 — el gate ahora VE las citas de las segundas lentes

`contrast` identificaba una extracción por el nombre del archivo y `harvest_views` por el `bibcode`
de adentro. Mientras el nombre **es** el bibcode las dos coinciden; con una segunda lente
(`<bib>__<lente>.json`) divergen, y todas las citas de esa lectura caían en *no evaluable* con el
gate devolviendo `rc 0` — sobre citas que no había mirado.

⛔ **Lo que esto significa para vos: el barrido puede reportar HOY cosas que ayer callaba.** No es
una regresión: es población que entra por primera vez.

```bash
python scripts/contrast.py --validar-todo
```

Si aparecen hallazgos nuevos, se corrigen como siempre: **copiando la cadena del JSON de
extracción** (`python scripts/contrast.py <slug> --grep "<re>"`), nunca re-tipeándola (#322).

> Medido en `Almagesto-Tesis` (2026-09-03): **187** extracciones, **13** con nombre distinto de su
> bibcode. Ésas son las que entran a la población del gate por primera vez.

### #371 — dónde escribe la próxima segunda lectura

`extraction_prompt … --enfasis` mandaba escribir en `<bibcode>.json`, o sea **el archivo de la
primera lente**, que es un artefacto versionado y no regenerable (#311). Ahora deriva el nombre de
la lente.

**Nada que reparar hacia atrás si usaste el workaround** de repuntar los prompts a mano: los
archivos ya tienen el nombre correcto. Lo que cambia es que la próxima corrida no necesita el
workaround, y que el cosechador **avisa** si dos archivos declaran el mismo `(bibcode, sujeto,
lente)`.

### #372 — la lente que declara cada vista

`harvest_views` estampaba los ejes del **tema** en toda vista, así que una segunda lente con
`--ejes` propios quedaba declarando ejes que nunca preguntó (rompe INV-146 y el diff de D-49).

**Chequeo:** una vista con `enfasis` cuya `lente` no sean las claves de `ejes` de **su** JSON.

```bash
python - <<'EOF'
import json, pathlib, sys
sys.path.insert(0, "scripts"); import lib_config as cfg
ejes = {}
for f in sorted(cfg.EXTRACCION.glob("*/*.json")):
    try: d = json.loads(f.read_text(encoding="utf-8"))
    except Exception: continue
    v = d.get("vista") or {}
    if v.get("enfasis"):
        ejes[(str(d.get("bibcode") or "").strip(), v.get("sujeto"), v["enfasis"])] = list(d.get("ejes") or {})
mal = 0
for nota in sorted(cfg.PAPERS.glob("*.md")):
    fm = cfg.split_fm(nota.read_text(encoding="utf-8"))
    for v in (fm.get("vistas") or []):
        k = (fm.get("bibcode"), v.get("sujeto"), v.get("enfasis")) if isinstance(v, dict) else None
        if k and k[2] and k in ejes and list(v.get("lente") or []) != ejes[k]:
            print("⛔", nota.name, k[2]); mal += 1
print(f"vistas con lente desalineada: {mal}")
EOF
```

Se corrige a mano en el frontmatter de la nota (la `lente` de esa vista pasa a ser las claves de
`ejes` de su JSON): el cosechador **no pisa** una vista ya escrita, así que re-correrlo no la
repara.

> Medido en `Almagesto-Tesis`: **16** vistas con `enfasis`, **0** desalineadas — ya se habían
> corregido a mano cuando se abrió el issue.

## 2c · v1.178.0-v1.180.0 (#373 · #364/#388 · #359) — las citas que nadie miraba, y su ruido

### #373 — el barrido ahora entra en `## Vista`

En una nota de paper el bibcode es la nota, no un link, así que sus citas no tenían par para el
fan-out ni candidato para el gate. Ahora el bibcode de la nota se **suma** a los adyacentes.

⛔ **Es la sección con más citas de tu bóveda y entra entera a la superficie de chequeo.** Corré:

⚠ Y esperá que suba mucho **«sólo respaldada por la extracción»** (#341): son las citas que su
propia extracción dice y su `.txt` no. Es el veredicto correcto —el `.txt` es índice degradado— y
**no** es un hallazgo: viaja en la línea de población para que no se lea como verde limpio.

```bash
python scripts/contrast.py --validar-todo
```

> Medido en `Almagesto-Tesis` (2026-09-03): de **3** citas miradas se pasa a **5482**, y los
> hallazgos bloqueantes quedan en **0**. Los 13 que aparecían en el camino eran los dos defectos que
> este mismo cambio destapó, ya corregidos: una mención en la celda vecina que robaba la atribución
> (5) y una asimetría de #326 en la matemática (7).

### #364/#388 — baja el ruido del carril `.txt`

Los avisos «el `.txt` dice otra cosa» sobre-reportaban por tres mecanismos que no rompen ninguna
palabra: empalme de columnas, comillas TeX y ligaduras. **No hay nada que arreglar en tu contenido**:
el reporte se acorta solo.

> Medido en la misma bóveda: **231 → 155** avisos, y `icasso.md` —donde los cuatro casos se habían
> verificado abriendo el PDF— pasa de **4 a 0**. ⚠ Los 155 restantes no están clasificados: que
> bajen no los declara falsos. ⛔ Y esa medición mide **ruido, no sensibilidad**: el verdadero
> positivo de #364 ya estaba corregido en la nota y en el JSON, así que no está en el corpus — quien
> sostiene que el detector sigue cazando lo que debe es su test unitario, no este número.

### #359 — el cosechador avisa sobre la extracción, no sólo sobre la nota

`harvest_views` cruza ahora cada cita del JSON contra el `.txt` del paper. Vas a ver líneas nuevas
al cosechar. **Avisa y no rechaza**: la extracción entra igual.

Qué hacer con una: **abrir el PDF en esa página**. Si el `.txt` tiene razón, se corrige el JSON de
extracción **y** la vista que ya se estampó — el cosechador no pisa prosa escrita, así que
re-correrlo no la repara.

> Medido: **129** avisos potenciales sobre 3117 citas de extracción de toda la bóveda (4 %), que por
> corrida de cosecha son unas pocas. ⚠ El aviso por AUSENCIA no existe a propósito: el 36 % de esas
> citas no está en su `.txt` y casi todo es degradación del índice.

## 2d · v1.181.0-v1.182.0 (#378 · #379 · #380) — la cabecera de las notas de paper

Los tres son **una sola cascada**, y conviene leerla entera antes de tocar nada:

1. **#378** inserta el aviso de capa LLM ENTRE el H1 y la línea de cabecera (orden invertido).
2. Con ese orden, `--restamp-abstracts` mete `## Abstract` **arriba** de la cabecera y la cabecera
   queda **dentro** de esa sección.
3. **#379**: el cosechador reemplaza `## Abstract` entera y **se lleva la cabecera puesta**, sin
   aviso y con el lint en 0.
4. **#380**: el detector que debía verlo callaba sobre justo las notas que tenían link.

⚠ **La precondición del daño es la nota SIN `## Abstract`** (el stub off-ADS de #124/#277), así que
buscá ahí primero: #378 sólo hace daño donde #277 ya había fallado.

**Chequeo (los tres estados, que piden acciones distintas):**

```bash
python - <<'EOF'
import sys; sys.path.insert(0, "scripts")
import lib_config as cfg, make_notes as mn
ok = desp = aus = 0
for f in sorted(cfg.PAPERS.glob("*.md")):
    if f.name.endswith(".verif.md"): continue
    t = f.read_text(encoding="utf-8")
    if mn.find_header_line(t) is not None: ok += 1
    elif mn.header_line_anywhere(t) is not None: desp += 1; print("MOVER      ", f.name)
    else: aus += 1; print("RECONSTRUIR", f.name)
print(f"en contrato: {ok} · desplazadas: {desp} · ausentes: {aus}")
EOF
```

| estado | qué pasó | qué hacer |
|---|---|---|
| **desplazada** | está, en el lugar equivocado | `python scripts/make_notes.py --fix-header-order` |
| **ausente** | ya se perdió | **reconstruir del historial de git** — `--restamp-pdf-links` NO puede: necesita la cabecera que falta |

Y una tercera, sin daño pero con riesgo: la nota con el **orden invertido** que todavía tiene su
`## Abstract`. No se rompe hoy; si alguna vez pierde la sección, el backfill corre encima y la
cascada arranca. Las normaliza el mismo `--fix-header-order`, que **no toca** las que ya están en
orden canónico.

> Medido en `Almagesto-Tesis` (2026-09-03): **188 notas de paper, 188 en contrato, 0 y 0** — las 10
> dañadas ya se habían reparado a mano cuando se abrieron los issues. En la instancia donde se
> midieron: 60 de 169 con orden invertido, 10 avanzadas, 6 con la cabecera borrada.

## 2e · v1.184.0-v1.186.0 (T3: #365 · #368 · #366 · #369 · #389 · #370 · #385) — el flujo de verify

**Nada que reparar en el contenido.** Lo que cambia es **cómo se corre** el fan-out y cómo se
escribe prosa citada. Tres hábitos nuevos y un chequeo:

| hábito | antes | ahora |
|---|---|---|
| repartir el fan-out | prompts armados a mano, `--esperados` contado a ojo | `python scripts/verify_fanout.py <nota> --out build/<slug>/verif/<ronda>` escribe un prompt por fuente y el manifiesto; la barrera se corre **sin** `--esperados` y nombra la fuente que falta (#369) |
| copiar una cita a la PROSA | transcribir a mano | `python scripts/contrast.py <slug> --cita --grep "<re>"` emite `«valor» (loc) [[bibcode]]` pegable (#385) |
| reconstruir el bloque tras re-anclar | la cadena se perdía con el ancla | pasar las filas por `lib_blocks.chain_from_reanchor(filas, re_anclaje)` con el JSON de `reverify_subset` (#366) |
| corregir | reescribir con más cuidado | **sacar** la parte equivocada primero; `apply_fixes` avisa si un fix agrega citas (#389) |

**Chequeo nuevo del lint (backlog):** un `[[bibcode]]` dentro del blockquote de alcance de
`## Huecos` o de una hipótesis (#368). Es contabilidad del corpus, no una cita, y el fan-out lo toma
como par que ningún PDF puede respaldar. Se reemplaza por el nombre del paper.

> Medido en `Almagesto-Tesis`: el caso que abrió #368 ya estaba corregido a mano (tres links →
> «Meinecke 2002, Remes 2011 y Du 2014»).

## 2f · v1.183.0-v1.188.0 (#359 · #367 · #356 · #355 · #383 · #362) — artefactos y adquisición

**Nada que reparar en el contenido.** Tres cosas que vas a ver, y conviene saber de antemano:

- **El cosechador imprime de golpe muchos avisos (#359, v1.183.0).** Antes el cruce contra el
  `.txt` corría después del estampado, y sobre una bóveda ya cosechada el rechazo de la vista lo
  cortaba antes: **nunca** se veían. Ahora corre antes de tocar la nota, sobre toda extracción
  admisible. No es regresión: es la población que estaba y no se mostraba. Cada aviso pide **abrir
  el PDF** en esa página; si el `.txt` tiene razón, se corrige el JSON **y** la vista estampada.
- **`pdf_sha` sólo aparece en lo que se estampe desde ahora (#383).** `stamp_pdf` guarda el hash
  al escribir `pdf:`, y con él detecta el REEMPLAZO del archivo por otro de distinta procedencia
  (deja `pdf_source`/`eprint_version` en `null` y avisa). Las notas existentes **no** llevan hash y
  no se tocan —registrarlo en todas sería el diff de 169 archivos que #378 evitó—, así que en ellas
  el reemplazo no se detecta. Chequeo que sí corre en todas: el par `pdf_source` de editor +
  `eprint_version` es **bloqueante**.
- **`--rename-paper VIEJO NUEVO --fix-key` para una clave EQUIVOCADA (#355).** Sin el flag, el
  renombre escribe `versions[]`, que es el alias de D-19 y exime de los chequeos de identidad;
  para una clave que no identifica a nada eso es una afirmación falsa blindada. Con el flag no se
  escribe y el comando imprime la entrada del `log` con la marca de #238, lista para pegar. Y el
  renombre re-apunta `pdf:`/`fulltext:` por verdad de disco (#356), que antes quedaban al viejo.

Lo demás no deja rastro visible: cerrar un `pending` off-ADS estampa `pdf:` en la nota que ya
existía (#367), y con la cuota de OpenAlex en cero `refs_of` sigue andando por la entidad única, que
cuesta 0 (#362) — el orden de gasto está en `docs/operacion.md`.

> Medido en `Almagesto-Tesis` (v1.188.0, validado por su instancia): **129** avisos de #359 sobre
> los cinco sujetos, uno a uno los mismos de la medición a mano del 03 · `pdf_sha` en **0** notas ·
> categoría #383 en **0** sobre 188 notas de paper · `refs_of` contra OpenAlex real, 79 referencias
> sobre un DOI. La deuda declarada en su STATUS: esos 129 y los 155 avisos del `.txt`, que piden
> PDFs de a uno y son operación de `maintain` aparte.

## 2g · v1.189.0-v1.190.0 (#361 · #358) — la cascada que nadie miraba, y el PDF que sí había

**Nada que reparar en contenido; dos cosas para correr.**

- **Categoría nueva del lint, backlog: `cascada_sin_correr` (#361).** Sólo mira temas **off-ADS o
  mixtos** (`source:` declarado y distinto de `ads`) y lee `descubrimientos` del registro, con
  tres estados: *nunca corrió* · *corrió y no trajo nada* · *corrió con backends caídos* (nombra
  cuál; un backend caído en una corrida y sano en otra **no** es deuda, y `NO CORRIÓ: …` es
  decisión, no caída). Esperado en `Almagesto-Tesis`: **2** hallazgos — `icasso` (OpenAlex FALLÓ
  en sus dos corridas del 08-31) y `rv-doppler` (sin `descubrimientos`). `ica` e `ica-ruido` corrieron
  con los tres backends y no salen. Se cierra corriendo `python scripts/discover.py --theme <slug>`
  cuando OpenAlex tenga presupuesto (#362: el aviso lo dice). ⚠ `rv-doppler` es corpus declarado
  con `source: local-pdfs` porque #384 todavía no existía; cuando entre #384 y pase a `source: ads`
  + `query: null`, sale solo de esta categoría.
- **El anclaje ya no muere con traceback (#361 a).** Deja fila `anclaje` en la cobertura del
  registro, con los tres estados. Sólo en corridas nuevas: las entradas viejas de `descubrimientos`
  no la tienen y no se tocan.
- **`fetch_pdf` cae al resolver de acceso abierto antes de rendirse (#358).** Cascada completa,
  OpenAlex → Unpaywall → Europe PMC → arXiv por título exacto, **todos** los candidatos. En
  `icasso` los dos «sin conseguir» eran open access: re-corré

  ```bash
  python scripts/fetch_pdf.py icasso          # esperado: 2022PLoSO..1770556W (OpenAlex → PLoS) y
                                              # 2019Bioin..35.4307C (OUP bloqueado → Europe PMC)
  python scripts/extract_fulltext.py icasso   # el .txt de los dos
  python scripts/lint.py
  ```

  `fetch_pdf` estampa `pdf:` en la nota que ya existía (#304) y `extract_fulltext` el `fulltext:`.
  `pdf_source` queda `publisher` para PLoS (`publishedVersion` según OpenAlex) y **desconocido**
  (`null`) para la copia de Europe PMC — es honesto: no se sabe si es la versión del editor. El
  residuo `build/<slug>/missing_pdf.json` trae ahora `estado: sin-copia-libre | bloqueado` y
  `copias_libres`; la referencia `rescate-pdfs.md` dice qué hacer con cada uno.

> Medido en el template (2026-09-04): smoke real con los dos DOI del issue, 874 KB y 750 KB, el
> segundo sólo por Europe PMC. La instancia mide lo suyo y lo deja en el `log`.

## 2h · v1.191.0-v1.197.0 (T5: #354 · #360 · #384 · #382 · #357 · #353 · T6: #377 · #376) — temas de método y config

**Dos cosas para correr, una para decidir, y un hallazgo real que el lint va a bloquear.**

- **`check_sources.py` (#353): correlo sobre cada tema con `sources:` y mirá el bloqueante.**
  Nuevo script; cruza lo que cada item de `sources:` declara (`author`/`year`/`title`) contra
  Crossref por `doi` o, sin registro (los `10.48550/arXiv.*`) o sin `doi`, contra la primera
  página del PDF. Registra el veredicto en `registro/<slug>.yaml` (`fuentes_chequeadas`) y no toca
  `themes.yaml`. Hasta que corra, el lint reporta cada fuente como *nunca cruzada* (backlog):

  ```bash
  for t in ica ica-ruido icasso; do python scripts/check_sources.py $t; done
  python scripts/lint.py
  ```

  Medido en dry-run sobre tus 52 fuentes (2026-09-04): **1 bloqueante** — `2006VanDerBaan` declara
  «VanDerBaan» y Crossref dice **Vrabie** para ese DOI (es la atribución falsa de #353, repetida);
  se corrige la entrada (autor, clave si corresponde vía `--rename-paper … --fix-key`, #355) o el
  DOI. Backlog esperado: 3 títulos con variantes (`2013Waldmann`, `2006Tichavsky`, `2010ComonJutten`),
  `2008Yang` año 2008 vs 2007 (online-first: no bloquea), 6 `no-evaluable` (5 arXiv sin PDF legible
  + `2001LevineDomany` sin registro) y **14 primeras páginas** que no confirman apellido o año
  (capítulos, preprints): ésas se cierran abriendo el PDF; si la declaración es correcta, quedan
  como backlog declarado — el carril PDF nunca bloquea.
- **`fetch_pdf` ya corrió para #358; nada nuevo acá.** `--restamp-alcance` ahora también lee
  `extra_core` (#382): corré `python scripts/make_notes.py --restamp-alcance` (esperado: 0 notas
  si ninguna entrada de `extra_core` declara `unidad_cita`; la tesis `2021PhDT.........6D` de
  `rv-doppler` es la candidata — declarale `unidad_cita: pagina` + `alcance:` en su entrada y
  re-corré; el prompt de extracción va a ramificar).
- **`rv-doppler` deja de mentir en `source:` (#384):** ponele `source: ads` (o borrá `source`) y
  dejá `query: null` + `extra_core:`; sacá `sources: []`. `ingest_theme.py rv-doppler` corre la
  sub-cadena `--extra-only` sin el aviso de tema mixto, y el tema sale de `cascada_sin_correr`
  (#361) porque ya no es off-ADS.
- **Dos categorías de backlog nuevas que van a aparecer:** `tema_ejes_heredados` (#360) para todo
  tema con `facet:` y sin `ejes:` (esperado: `ica`, `ica-ruido`, `icasso` si no los declararon), y
  `vista_ejes_faltantes` pasa a decir *no evaluable* para las vistas de esos temas. Se cierra
  declarando `ejes:` (los del contraste 3b), aunque sea `ejes: []`.
- **Cambia una pantalla, no un artefacto:** el probe y la corrida imprimen SIEMPRE `fq: … (del
  objetivo | del tema | heredado | null — no acota)` (#354), y el probe del tema con
  `fundacional_min_citas` muestra el rango de citas de ADS y avisa si el `fq` no es astro (#357).
  La decisión `fundacional_fuente: openalex` queda abierta en `docs/decisiones-abiertas.md`.
- **Regla de oro (#377):** desde una instancia se abre el issue y se para ahí. Sin efecto en
  contenido.

> Medido en el template (2026-09-04): las 52 fuentes de `Almagesto-Tesis` en dry-run (sin escribir
> nada en la instancia); la instancia mide con el registro escrito y lo deja en el `log`.

## 2i · v1.198.0 (T5b: `--promote-source`) — la fuente declarada que tenía bibcode ADS

**Una operación para correr si `check_sources` (o vos) encontró una fuente de `sources:` con
bibcode ADS.** El caso de #353 (`2011Yang` → `2011PLoSO...627594P`) ya lo migraste a mano y perdió
el `no_vista` en el camino; para las que queden:

```bash
python scripts/triage.py ica --promote-source <key> --bibcode <bibcode ADS>
# pegá el `extra_core` que imprime, sacá el item de `sources:`, pegá la marca ⚠ corregido en log.md
python scripts/ingest_theme.py ica          # idempotente
python scripts/lint.py
```

Mueve nota, hermano `.verif.md`, PDF/`.txt` bajo todos los slugs, extracción y wikilinks; **no**
escribe `versions[]` (la clave era errónea, #355); re-estampa título/autor/año/doi/bibstem/citas/
keywords/abstract desde ADS; y compara la curación de la nota antes y después — si algo se perdió
lo grita con el `git show` para recuperarlo (rc 1). Candidatos en tu bóveda: los items de
`sources:` cuyo DOI resuelva a un bibcode ADS (`2012Waldmann`/`2013Waldmann` son ApJ: casi seguro
lo tienen; verificá con `python scripts/query_ads.py --probe 'doi:"<doi>"'`).

## 2j · v1.199.0 — seguimiento de #353 (los seis hallazgos del validador)

**Una cosa para correr:** `python scripts/make_notes.py --restamp-sources-meta` — desde ahora,
corregir `author`/`title`/`year`/`doi`/`n_authors` en `sources:` llega al stub off-ADS (antes
había que editar la nota a mano; la curación no se toca). Esperado en `Almagesto-Tesis`: 0 notas
si ya arreglaste las cuatro a mano; si alguna difiere de la config, la lista.

Y **re-corré `check_sources.py` sobre `ica`**: cambia el carril PDF —primera página ilegible
(mojibake) sale *no-evaluable*, no «falta el apellido»; `Herrero1` ya no es falso; y un apellido
compuesto (`Le Bihan`, `van der Baan`) ya no bloquea contra Crossref. Esperado: los cuatro
Hyvärinen pasan de `autor` a `no-evaluable (primera página ilegible)`, y `2007GomezHerrero` a
`ok`. Lo demás es cosmético: el `extra_core` de `--promote-source` parsea como YAML y el resumen
de `--fix-key` ya no promete un alias que no escribe.

## 3 · Cierre

```bash
python scripts/lint.py                       # rc 0
python scripts/contrast.py --validar-todo    # rc 0
git add vault/ && git commit
```

Y dejá la entrada en `vault/wiki/log.md` (`## AAAA-MM-DD — migración: v<X> → v<Y>`) con qué
chequeaste y qué encontraste. Si un chequeo **no pudo** correr, escribí eso: un cero que nadie midió
se lee como veredicto.
