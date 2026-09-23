# Desarrollo del framework — reglas de método 1-3, idioma y las diez redes

> Sale de `CLAUDE.md` en #465 (2026-09-14): es lo que se lee **al escribir código del framework**,
> operación explícita del **template**; una **instancia** no edita framework (#377) y lo pagaba en
> cada sesión. Las reglas de método **4, 5 y 6** se quedan en `CLAUDE.md` porque rigen operaciones
> de bóveda (normalizar markdown, declarar la discrepancia, fan-out/serial/barrera/re-verificar).
> La numeración es la original — «regla de método nº 4» sigue nombrando la misma regla.

## Reglas de método 1-3 (por qué existen las redes de abajo)


Salieron de medir una sesión entera donde **los defectos los encontraron agentes leyendo el código,
no la suite**. No son consejos: cada una nombra un modo de falla que ya ocurrió acá (la medición
vive en su issue y en `docs/mediciones.md`), y las redes de la sección siguiente son su
mecanización.

1. **Un test con la red falseada valida que el CLIENTE funcione, no que el CONTRATO se cumpla.** Si
   escribís un cliente de red, **probalo una vez contra el servicio de verdad** antes de darlo por
   hecho — los tres bugs serios de la Tanda 7 los encontraron el smoke test real y una auditoría
   adversaria; ninguno la suite, que estaba verde.
2. **Un doble de test con distinto contrato que la función real esconde el bug en la diferencia**
   (medido en `refs_of`: el doble indexaba por el input verbatim y el real por `_bare_doi`). Un
   doble o deriva de la función real, o tiene un test de paridad.
3. **Un test verde recién escrito no cuenta hasta que lo viste morir — POR LA RAZÓN QUE PRUEBA.**
   La pregunta no es *«¿falló?»* sino ***«¿murió por la línea que estoy probando?»***, y se contesta
   mirando **el mensaje del fallo**, no el rojo (#196/#197: un test que fallaba por el setup pasaba
   sin el fix; dos tests sobrevivieron a mutar la guarda que decían proteger). La forma barata de
   contestarla es la **mutación dirigida** (#204): `python tools/mutar.py --dirigida
   scripts/<módulo>.py`.
## Convención de idioma del código (desde 2026-08-24)

**Archivos, nombres de funciones, docstrings y comentarios NUEVOS en inglés.** La prosa de la
documentación (`CLAUDE.md`, `README.md`, `docs/`, los `SKILL.md`) y la de la bóveda siguen en
castellano. **Sin retrofit**: lo que ya está escrito no se renombra.

La red es `tests/test_idioma_codigo.py` con ratchet en `tools/idioma-ratchet.yaml` (#156: la regla
existió sin casa ni gate y el resultado fueron 30 funciones nuevas en castellano — *o la regla tiene
casa y red, o no es una regla*). Vigila las tres mitades: `simbolos` (nombres castellanos),
`docstrings_castellano` (heurística declarada, mide el **delta**) y `sin_docstring` (acá el
docstring **es** el contrato de la función — el frente C de `/auditar` audita que se cumpla). Los
tres techos **sólo bajan** y ninguno es un rojo: son deuda anterior a la convención; un nombre nuevo
fuera de la lista `conocidos` pone el test en rojo aunque el total no suba (impide que la deuda
rote). Los números los dan las funciones del test, no esta prosa.

## Al escribir código: las diez redes (regla permanente)

Toda función nueva de `scripts/` **y de `tools/`** pasa por esto **antes de cerrar el issue**; la 6
rige también para los scripts de una sola operación. ⛔ **Las redes 1 y 4 cubren `tools/` (#345,
`mutar.ALCANCE`, que la red 4 importa para que no diverjan)**: acotarlas a `scripts/` dejaba sin red
a la herramienta que las ejecuta. La **única exención, `tools/refresh_issues.py`, se declara con su
motivo** en `mutar.EXENTOS_MODULO` (cliente HTTP: la regla de método 1 manda probarlo contra el
servicio real). Los tres estados de `scope_refusal` —fuera de alcance · exento · sin
`tests/test_<mod>.py`— piden acciones opuestas, y una selección **toda** exenta sale *no evaluado*,
no verde. Detalle y ratchets en `tests/README.md`; el resumen operativo:

1. **Mutación** — romper cada función y exigir que **algún test muera**: es lo único que distingue
   "el test pasa" de "el test **podría** fallar". Trabaja sobre una copia del repo. Tres modos:
   - **Dirigida** (`python tools/mutar.py --dirigida <scripts|tools>/<mód>.py [--solo f,g]`) — **es un
     paso al escribir una función con guardas** (#204): un módulo, sólo su archivo de tests, ~0,44 s
     por mutación. Sobre-reporta y nunca da falso limpio; no toca el ratchet. **Rehúsa** si el módulo
     no tiene `tests/test_<módulo>.py` o nada mutable — cero mutaciones no es «murieron todas» (D-43).
   - **Guardas** (`python tools/mutar.py --guardas <scripts|tools>/<mód>.py [--solo f,g]`, AUD-213) —
     vaciar el cuerpo no mide las **condiciones**: muta cada `if` interno a `False` y, en un
     `and`/`or`, **cada cláusula por separado, a la identidad del operador** (`True` en `and`,
     `False` en `or`; reproducila a mano con ESE literal, #393). Mismo contrato que la dirigida;
     una condición constante se saltea (el hallazgo sería inventado). ⚠ Es el único modo que chequea la **baseline**: con el archivo de tests en rojo,
     toda guarda «muere» por el motivo equivocado (#202) → sale **no evaluado** (rc 2), no un verde.
   - **Barrido** (`--diff` / `--todo --ratchet`) — corre en **dos etapas** (#187: primero
     `tests/test_<módulo>.py`, sólo los sobrevivientes pagan la suite; `--todo` ≈ 32 min, #345).
     **Cadencia: a pedido, y recomendado al cerrar una tanda**, con el árbol **quieto** (#199: copia
     el repo al arrancar).
   - **Atribución del mapa** (`python tools/mutar.py --trazabilidad --diff`, #491) — **es un paso
     al escribir o mover una marca `@inv`**: audita sólo los invariantes cuyas marcas toca el diff
     (por **línea**, no por archivo: `lib_config.py` sola lleva marcas de ~120, y por archivo el
     paso costaría 120 corridas en vez de segundos). Vacía el símbolo marcado y corre **sólo** su
     test marcado; si el test pasa igual, la fila del mapa afirma una cobertura que no existe.
     Un diff que no toca marcas sale **no evaluado** (D-43), nunca verde. El barrido completo
     (`--trazabilidad` sin flags, ~20 min sobre las 223 filas) sigue siendo cadencia de cierre —y
     hasta #491 era la única: las 7 atribuciones falsas de #489 aparecieron **14 días después**,
     todas juntas. ⚠ Detecta la marca **nueva o movida**; la vieja que se vuelve falsa porque
     alguien reescribió el test que la sostenía la sigue viendo sólo el barrido.
2. **Schema compartido** — si N módulos prometen la misma forma, se prueba **una vez parametrizada**
   (`tests/test_backends_schema.py`), no con prosa en N docstrings.
3. **Doble vs real** — un doble de test no se escribe a ojo: o deriva de la función real, o hay un
   test de paridad (regla de método 2).
4. **Nadie sin ejecutar** — `pytest tests/poblada/test_cobertura.py -m poblada` (~11 s): una función
   que la suite nunca corre no está "mal probada", está **sin mirar**. Mismo alcance que la 1.
5. **La doc es ejecutable** — `tests/test_docs_ejecutables.py`: todo test, script y config que la
   documentación nombra existe, y todo comando de skill compila.
6. **Corré dos veces y hasheá** — para **todo script que escriba en `vault/`**, versionado o de una
   sola operación (la idempotencia es invariante del framework):
   ```bash
   H=$(find vault -name '*.md' -exec md5sum {} + | sort | md5sum); <el comando>; \
     [ "$H" = "$(find vault -name '*.md' -exec md5sum {} + | sort | md5sum)" ] && echo IDEMPOTENTE
   ```
   ⚠ **La idempotencia es sobre CONTENIDO, no sobre la bitácora (#105):** el chequeo hashea
   `vault/**/*.md` y **no** `vault/config/registro/`, a propósito — D-28 hace que el registro
   **crezca** en cada corrida. Las dos reglas conviven: **la nota no puede cambiar si no cambió lo
   que afirma; el registro tiene que crecer aunque no cambie nada.** El bloque propio va entre
   centinelas (`<!-- almagesto:… -->`) y lo de afuera no se toca (`make_notes._reemplazar_seccion`
   ya lo hace).
   ⛔ **Y un `--dry-run` no escribe en NINGÚN modo del script que lo declara (#507):** o el modo lo
   hila hasta cada escritor, o rehúsa con `cfg.refuse_dry_run` (exit 2) — nunca lo ignora. La red
   es un test por script que corre el modo con el flag y compara `conftest.tree_digest` antes y
   después; los portadores (todo `add_argument("--dry-run"`) están firmados en `portadores.yaml`.
7. **Idioma** — `pytest tests/test_idioma_codigo.py` (ver arriba).
8. **Condicional que no decide nada** — `tests/test_codigo_muerto.py` (#319): el ternario cuyas dos
   ramas valen lo mismo es una regla escrita a medias y **ningún otro gate la ve** (no cambia
   comportamiento: no hay test que matar). Se encontró leyendo un commit; ahora es un assert.
9. **Atribución del mapa** — `python tools/mutar.py --trazabilidad` (AUD-212, ~20 min): vacía cada
   implementación marcada `@inv` y corre **sólo el test marcado**; si pasa, esa fila de
   `docs/trazabilidad.md` afirma una cobertura que no existe. ⚠ Sobre-reporta: ante un
   sobreviviente por coincidencia se marca un test que ejerza la rama verdadera.

10. **¿Quién MÁS lleva esta regla?** — `python tools/carriers.py --check` (tier 0). ⛔ **Un issue
    cuyo fix tiene portadores no se cierra sin su entrada en `tools/portadores.yaml`**: la regla, la
    ÚNICA función que la implementa, y el `patron` por el que se reconoce a un portador. El gate
    compara las dos direcciones y rehúsa si alguien llama sin estar declarado, si un declarado `usa`
    **no** llama (el comentario que dice «delega» y no delega), o si un módulo matchea el patrón y
    nadie dijo nada de él; `fuera-de-alcance` lleva motivo. La lista no se escribe de memoria:
    `--propose <modulo.simbolo> --patron <re>` la enumera en **tres** bloques —llaman · firmados
    `fuera-de-alcance` con su motivo · **sin declarar**—, y sólo el tercero es deuda (#482: con dos
    bloques, el firmado y el que nadie miró salían iguales en lo que se pega en cada issue). Motivo: cuatro lectores clasificaron los
    ~400 issues del repo por mecanismo sin verse entre ellos y tres nombraron el mismo tema
    dominante — **el fix se escribe contra el caso medido y no contra la relación que lo contiene**
    (45 de 100 en un tramo, ~50 en otro, 32 en el último). Su primer hallazgo fue una segunda
    implementación de `txt_slug`, idéntica línea por línea.

Las 2, 5, 7, 8 y 10 corren solas en tier 0; la 1 y la 9 son a pedido (cuestan minutos). El motivo de la
regla: en la sesión que la produjo, los bugs los encontraron agentes leyendo el código, no la suite
— y cada hallazgo era decidible, o sea que podría haber sido un assert.

⚠ **La red que no mira el código nuevo no es una red (INV-101):** el gate de mutación seleccionaba
con `git diff --name-only HEAD`, que no lista untracked, así que un archivo recién creado salía en
verde sin mutarse. Antes de creer un gate, confirmá **sobre qué corrió**.

⛔ **Y un test del framework mide el CÓDIGO, nunca el CONTENIDO de la bóveda (#469).** Si su
veredicto depende de lo que la bóveda tenga adentro —o de algo que la copia de trabajo no lleva—, la
población se **declara** y se skipea **con motivo visible** (`pytest.skip`, el precedente que
`pytest.ini` bendice para el tier `instancia`), o se corre contra `toy_vault`, que es población
declarada. Medido: `test_lint_no_muere_en_una_consola_no_utf8` asserteaba `returncode == 0` —o sea
*«esta bóveda no tiene bloqueantes»*— cuando `exit 1` es el **trabajo** del lint. Un solo assert
hacía dos daños: en el árbol real se ponía rojo por deuda de contenido **sin que
`UnicodeEncodeError` apareciera por ningún lado** (regla de método 4), y dentro de la copia de
`mutar` —que excluye `vault/raw/pdfs`— fallaba **siempre**, así que `mutar.py <archivo>` devolvía 2
para cualquier archivo y **la red #1 quedaba inoperable** («1 failed, 3008 passed»). ⚠ Y la red que
lo caza —`test_mutar.py::test_la_copia_del_repo_arranca_con_baseline_verde`, tier `poblada`— **sólo
dispara donde la bóveda tiene deuda**: en el repo template, cuya semilla está limpia, el test pasaba.
El gate funcionó donde había población; lo que faltaba era no depender de ella.
