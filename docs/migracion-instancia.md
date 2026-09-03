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
  for f in vault/wiki/log.md vault/STATUS.md vault/wiki/index.md \
           vault/config/objective.yaml vault/config/stars.yaml vault/config/themes.yaml \
           vault/wiki/matrices/method_star.md; do
    if git diff --quiet "$m" "$m^1" -- "$f" && ! git diff --quiet "$m^1" "$p2" -- "$f"; then
      echo "⛔ $(git log -1 --format='%h %ad' --date=short $m)  $f"
    fi
  done
done
```

Dice: *el merge conservó tu versión byte a byte y la del remoto era distinta* — o sea, lo del otro
clon se descartó. El filtro por `upstream` es el que evita el falso positivo: contra el template,
descartar lo suyo **es** lo que `merge=ours` promete.

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
> descarte real (2026-09-02, el incidente que produjo #390), sobre 4 archivos. Resultado del
> triage: el `log` se había recuperado a mano (0 líneas faltantes), y `STATUS.md` e `index.md`
> figuraban con líneas «faltantes» que eran **estado superado por contenido más nuevo** — 0 daño
> vivo. Sin la clasificación por artefacto, esas 87 líneas se leían como pérdida.

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

## 3 · Cierre

```bash
python scripts/lint.py                       # rc 0
python scripts/contrast.py --validar-todo    # rc 0
git add vault/ && git commit
```

Y dejá la entrada en `vault/wiki/log.md` (`## AAAA-MM-DD — migración: v<X> → v<Y>`) con qué
chequeaste y qué encontraste. Si un chequeo **no pudo** correr, escribí eso: un cero que nadie midió
se lee como veredicto.
