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
> bajen no los declara falsos.

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

## 3 · Cierre

```bash
python scripts/lint.py                       # rc 0
python scripts/contrast.py --validar-todo    # rc 0
git add vault/ && git commit
```

Y dejá la entrada en `vault/wiki/log.md` (`## AAAA-MM-DD — migración: v<X> → v<Y>`) con qué
chequeaste y qué encontraste. Si un chequeo **no pudo** correr, escribí eso: un cero que nadie midió
se lee como veredicto.
