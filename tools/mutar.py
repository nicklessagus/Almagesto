"""Gate de mutación: por cada función de `scripts/` y `tools/`, romperla y exigir que **algún test
muera**.

POR QUÉ. Un test que pasa no dice nada por sí solo — puede estar pasando por construcción. En una
sola sesión aparecieron cuatro casos: un `assert path.glob(...)` (un generador es siempre truthy),
una guarda de lista vacía cuyo test pasaba aunque se borrara la guarda, un assert de "espera
creciente" que `[2.0, 2.0]` satisface, y un test de determinismo que corría las dos pasadas **en el
mismo proceso**, o sea con el mismo `PYTHONHASHSEED`, incapaz por construcción de ver el
no-determinismo que decía medir.

La mutación es la única forma barata de distinguir "el test pasa" de "el test **podría** fallar".

⚠ **Trabaja sobre una COPIA del repo en un tmpdir, nunca sobre el árbol real.** La primera versión
mutaba en el lugar y restauraba en un `finally`; un `pkill` a mitad de camino dejó
`check_retractions._mailto` con el cuerpo reemplazado por `return None` en el árbol de trabajo —y
la suite siguió en verde, porque esa función es justo una de las que ninguna prueba mata—. Un
harness que puede corromper el código que audita no sirve, por más `finally` que tenga: no
sobrevive a un Ctrl-C, a un timeout ni a que dos corridas se pisen.

CÓMO. Reemplaza el cuerpo de cada función por `return None` (una función que no hace nada es la
mutación más brutal posible: si NINGÚN test se pone rojo, esa función no está probada) y corre la
suite tier 0 en **dos etapas** (#187): primero `tests/test_<módulo>.py`, y sólo los sobrevivientes
pagan la suite completa. Sigue siendo caro —una corrida por función— así que NO va en la suite: se
corre al cerrar un issue, sobre los archivos que ese issue tocó.

    python tools/mutar.py scripts/openalex.py            # un archivo
    python tools/mutar.py --diff                          # lo que cambió vs HEAD
    python tools/mutar.py --todo --ratchet                # barrido completo + techo

⛔ **ALCANCE (#345): `scripts/` Y `tools/`.** Hasta 1.162.0 la red se acotaba a `scripts/`, así que
**la herramienta que ejecuta la red era la única que no la recibía** — medido: 5 guardas de este
archivo sin un solo test que las distinga. La exención que queda es UNA y está declarada con su
motivo en `EXENTOS_MODULO`, no por omisión del alcance.

El **ratchet** (`tools/mutacion-ratchet.yaml`) guarda cuántas funciones sobreviven hoy: el número
sólo puede bajar. Sin techo esto sería un rojo permanente, y un rojo permanente se deja de mirar.
"""
from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

RAIZ = Path(__file__).resolve().parent.parent
RATCHET = Path(__file__).resolve().parent / "mutacion-ratchet.yaml"
# Los directorios que la red de mutación cubre. Hasta #345 era sólo `scripts/`, y la consecuencia
# medida es que **la herramienta que ejecuta la red era la única que no la recibía**: 5 guardas de
# este mismo archivo no tenían un solo test que las distinguiera. `tools/` entra acá.
ALCANCE = ("scripts", "tools")
_ALCANCE_TXT = " / ".join(f"`{d}/`" for d in ALCANCE)
# Módulos DENTRO del alcance que la red igual no mira, cada uno con su motivo. La exención se
# **declara acá**, no queda por omisión del alcance (#345): «no lo mira nadie» y «no lo mira nadie
# POR ESTO» piden acciones opuestas —la primera es un hueco que se cierra, la segunda una decisión
# firmada— y sin este mapa las dos se leen igual desde afuera.
EXENTOS_MODULO = {
    "tools/refresh_issues.py":
        "es un cliente HTTP contra la API de GitHub, y la REGLA DE MÉTODO 1 dice que un cliente de "
        "red se prueba contra el SERVICIO REAL: un test con la red falseada valida que el cliente "
        "funcione, no que el contrato se cumpla. Mutarlo sólo mediría si el doble está bien "
        "escrito, que es el verde que esa regla existe para no comprar.",
}
# Funciones que NO se mutan, con motivo. Sin motivo no se agrega nada acá.
EXENTAS = {
    "main",              # orquestación: su contrato son los sub-pasos, ya mutados por separado
    "__init__",
}


def module_exemption(module: Path) -> str | None:
    """The declared motive for leaving `module` out of the net, or None when there is none.

    Keyed by `<dir>/<file>.py`, which is how `EXENTOS_MODULO` reads and how the diff lists paths --
    not by an absolute path, so a monkeypatched `RAIZ` (every test in this file) resolves the same
    way the real tree does."""
    return EXENTOS_MODULO.get(f"{module.parent.name}/{module.name}")


def split_exempt(modules: list[Path]) -> tuple[list[Path], list[tuple[Path, str]]]:
    """`(what the net actually mutates, [(module, its declared motive)])`.

    It lives OUT of `main` on purpose. `EXENTAS` hides `main` from every mutation net, so a guard
    written in there is invisible to the very tool it belongs to -- that is #331, which CLAUDE.md
    names, and writing the new rule inside `main` would have reproduced it in the same commit that
    brings `tools/` into the net."""
    exentos = [(m, motivo) for m in modules if (motivo := module_exemption(m))]
    return [m for m in modules if not module_exemption(m)], exentos


def funciones(archivo: Path) -> list[tuple[str, int, int]]:
    """(nombre, primera línea del cuerpo, última) de cada función top-level o de clase."""
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name not in EXENTAS:
            cuerpo = n.body[0]
            # Se conserva el docstring: mutar el comportamiento, no la documentación.
            if isinstance(cuerpo, ast.Expr) and isinstance(cuerpo.value, ast.Constant) \
                    and isinstance(cuerpo.value.value, str) and len(n.body) > 1:
                cuerpo = n.body[1]
            out.append((n.name, cuerpo.lineno, n.end_lineno or cuerpo.lineno))
    return out


def _copia_del_repo(destino: Path) -> Path:
    """Copia trabajable del repo. Se excluye lo que no hace falta para correr la suite (y pesa)."""
    shutil.copytree(RAIZ, destino, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "build", "outputs", "__pycache__",
                                                  ".pytest_cache", "*.pyc", "vault"))
    shutil.copytree(RAIZ / "vault", destino / "vault", symlinks=True,
                    ignore=shutil.ignore_patterns("pdfs", "fulltext"))
    return destino


def _suite_verde(cwd: Path, subset: Path | None = None) -> bool:
    blanco = str(subset) if subset else "tests/"
    r = subprocess.run([sys.executable, "-m", "pytest", blanco, "-q", "-x", "--no-header"],
                       cwd=cwd, capture_output=True, text=True, timeout=600)
    return r.returncode == 0


def test_file_for(module: Path) -> Path | None:
    """`<dir of ALCANCE>/foo.py` -> `tests/test_foo.py`, or None when there is no 1:1 file.

    Stage 1 of the two-stage sweep needs a file that is *part of the suite stage 2 would run*; that
    is what makes the split safe (a death there is a death). A wider guess -- every test file that
    imports the module -- would buy little and cost the property.

    `lib_config` is killed by tests all over the repo and `poblada/` is another tier: for those the
    stage is skipped, not approximated.
    """
    if module.parent.name not in ALCANCE:
        return None
    candidato = RAIZ / "tests" / f"test_{module.stem}.py"
    return candidato if candidato.exists() else None


def scope_refusal(module: Path, modo: str, escalar: str = "") -> str | None:
    """Why `modo` cannot run on `module`, or None when it can — THREE states, three actions (#345).

    **Out of scope**: the module lives outside `ALCANCE`. `CLAUDE.md` scopes the mutation net to
    `scripts/` and `tools/`, so this is a declared decision and there is nothing to write here.
    Reporting it as *«no hay tests/test_<stem>.py»* **denied a file that is there** (#339), and the
    two ask for opposite things.

    **Exempt module**: it IS in `ALCANCE` and `EXENTOS_MODULO` names it, with the motive. That
    motive is the whole point of the state: without it, a module nobody mutates reads exactly like a
    module nobody got around to mutating. The action is *«read the motive and decide if it still
    holds»*, never *«write the missing test file»* — for `tools/refresh_issues.py` writing it is
    precisely what method rule 1 forbids.

    **No test file of its own**: in scope, not exempt, and `tests/test_<stem>.py` is missing. That
    one is a real gap, and the answer is to write the file (or, for `--dirigida`, pay the full
    sweep).

    `escalar` is the mode's own way out, appended to the last message only; the other two have none
    by construction.
    """
    if module.parent.name not in ALCANCE:
        return (f"⛔ fuera de alcance: `{module.parent.name}/` no entra en la red de mutación, que "
                f"CLAUDE.md acota a {_ALCANCE_TXT} — {module.name} no se muta por acá. NO es que "
                f"falte tests/test_{module.stem}.py.")
    if (motivo := module_exemption(module)):
        return (f"⛔ EXENTO por decisión declarada (`EXENTOS_MODULO` de tools/mutar.py): "
                f"{module.parent.name}/{module.name} no entra en la red — {motivo}\n"
                f"   NO es que falte tests/test_{module.stem}.py: escribirlo con la red falseada "
                f"es lo que la exención existe para evitar.")
    if test_file_for(module) is None:
        return (f"⛔ no hay tests/test_{module.stem}.py: sin etapa barata no hay modo {modo}."
                + escalar)
    return None


def mutar_archivo(archivo: Path, copia_raiz: Path, verbose=True, two_stage: bool = True,
                  escalate: bool = True, only: set[str] | None = None) -> list[str]:
    """Funciones que **sobreviven** (ningún test se puso rojo al romperlas).

    `archivo` es del árbol REAL (para leerlo); se muta su gemelo dentro de `copia_raiz`.

    ⏱ **DOS ETAPAS (#187).** El costo dominante del barrido no era correr la suite: era **buscar el
    test asesino en el lugar equivocado**. `_suite_verde` ya usa `-x`, así que un mutante que muere
    corta en el primer fallo — pero pytest recorre los archivos en orden alfabético, así que mutar
    algo de `triage.py` paga casi toda la suite antes de llegar a `tests/test_triage.py`, que es
    justo el test que lo va a matar. Por eso:

      1. correr **sólo `tests/test_<módulo>.py`** — si muere ahí, listo;
      2. sólo los **sobrevivientes** pagan la suite completa, para descartar una muerte cruzada
         desde otro archivo.

    **Medido el 2026-08-28**, con el mismo conjunto de sobrevivientes (`[]`) en las dos ramas:

    | módulo | posición alfabética | 1 etapa | 2 etapas | |
    |---|---|---|---|---|
    | `triage.py` (17 fn) | casi al final | **143,6 s** | **8,0 s** | 18× |
    | `apply_fixes.py` (5 fn) | primero | 4,5 s | 1,7 s | 2,6× |

    Los dos extremos confirman el diagnóstico: la ganancia **es** la distancia entre el test asesino
    y el arranque del alfabeto. ⚠ No se extrapola a `--todo` desde dos módulos — el issue estimaba
    ~1 h → ~12 min y eso sigue **sin medir**.

    ⚠ **Qué se conserva y qué no.** El conjunto de sobrevivientes es el mismo: quien sobrevive a la
    etapa 1 igual paga la suite entera, así que no se pierde ninguna muerte cruzada. La única
    divergencia posible con el barrido de una etapa va en la dirección **optimista** —un test que
    pasa dentro de la suite y falla corriendo solo marcaría muerto un mutante que el barrido viejo
    daba vivo—, y eso sería un defecto de aislamiento del test, que conviene ver.

    `escalate=False` corta después de la etapa 1 y `only` acota a un subconjunto de funciones: es la
    **mutación dirigida** de `--dirigida` (#204), que no es el gate sino el bucle de escritura."""
    original = archivo.read_text(encoding="utf-8")
    gemelo = copia_raiz / archivo.relative_to(RAIZ)
    propio = test_file_for(archivo) if two_stage else None
    subset = Path("tests") / propio.name if propio else None
    sobreviven = []
    for nombre, ini, fin in funciones(archivo):
        if only is not None and nombre not in only:
            continue
        lineas = original.split("\n")
        sangria = len(lineas[ini - 1]) - len(lineas[ini - 1].lstrip())
        gemelo.write_text("\n".join(lineas[:ini - 1] + [" " * sangria + "return None"] + lineas[fin:]),
                          encoding="utf-8")
        etapa = ""
        try:
            # Etapa 1: el archivo de tests del propio módulo. Una muerte acá es una muerte.
            vivo = _suite_verde(copia_raiz, subset) if subset else True
            if vivo and subset:
                # ⚠ El texto dice lo que PASÓ, no lo que la etapa 2 haría: con `escalate=False`
                # (modo `--dirigida`) la suite NO se paga, y anunciarlo igual es afirmar un trabajo
                # que no se hizo — sobre el sobreviviente, que es justo donde el operador decide si
                # creerle. Medido: `stamp_accessed` salía «se pagó la suite» y su test vive en otro
                # archivo, así que nadie lo había corrido.
                etapa = (" (sobrevivió a su propio test; se pagó la suite)" if escalate
                         else " (sobrevivió a su propio test; la suite NO se corrió — `--dirigida`)")
            # Etapa 2: sólo los sobrevivientes pagan la suite completa.
            if vivo and escalate:
                vivo = _suite_verde(copia_raiz)
        except subprocess.TimeoutExpired:
            vivo = True
        if vivo:
            sobreviven.append(nombre)
        if verbose:
            print(f"  {'SOBREVIVE' if vivo else 'muere    '}  {archivo.name}::{nombre}{etapa}",
                  flush=True)
    gemelo.write_text(original, encoding="utf-8")   # deja la copia sana para el archivo siguiente
    return sobreviven


def archivos_del_diff() -> list[Path]:
    """Lo que cambió vs HEAD, **incluido lo que todavía no está trackeado**.

    `git diff --name-only HEAD` no lista untracked, así que un archivo recién creado en `scripts/`
    —el caso exacto para el que existe la regla «toda función nueva pasa por el gate antes de cerrar
    el issue»— quedaba afuera y el gate salía en verde **sin haberlo mirado**. Un chequeo que no
    puede fallar sobre el código que vino a cubrir es peor que no tenerlo: se lee como cobertura.
    `--others --exclude-standard` respeta `.gitignore`, así que el scratch no entra.

    Devuelve todo lo que está en `ALCANCE`, **exentos incluidos**: quién los filtra y los NOMBRA con
    su motivo es `main` (#345), en un solo lugar y con la misma salida para `--diff` y `--todo`. Un
    filtro silencioso acá volvería a hacer indistinguible «no se mutó» de «no se mutó por esto».
    """
    #  @inv INV-101
    salida = []
    for args in (["diff", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]):
        r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True)
        salida += r.stdout.split()
    vistos, archivos = set(), []
    for f in salida:                                  # `git add` de un archivo nuevo lo pone en los dos
        en_alcance = any(f.startswith(f"{d}/") for d in ALCANCE)
        if not (en_alcance and f.endswith(".py")) or f in vistos:
            continue
        vistos.add(f)
        # AUD-191 / INV-101 — `git diff --name-only` lista también lo **borrado**, y sobre un
        # archivo que no está en disco `funciones()` revienta con `FileNotFoundError`: el gate no
        # sale en rojo por un hallazgo, se cae. Un módulo eliminado no tiene funciones que mutar,
        # así que no es un hallazgo: se saltea.
        if (ruta := RAIZ / f).is_file():
            archivos.append(ruta)
    return archivos


def _directed(args) -> int:
    """Mutación DIRIGIDA (#204): un módulo, sólo su archivo de tests, sin escalar a la suite.

    NO es el gate y no toca el ratchet. Es el bucle de escritura: cuando escribís una función con
    guardas, rompés cada guarda y mirás si su propio test se pone rojo. Medido: ~10 s por mutación
    contra los ~8 s POR MUTANTE que costaba el barrido de una etapa sobre un módulo del final del
    alfabeto.

    Dirección del error, que es lo que lo hace usable: como no escala, puede marcar **SOBREVIVE**
    algo que otro archivo de tests sí mata — sobre-reporta sobrevivientes, nunca da falso limpio.
    "Murieron todas" acá sí implica que el barrido las daría muertas.

    Sin `tests/test_<módulo>.py` **se rehúsa** en vez de degradar a la suite completa: el modo se
    pide por barato, y devolver en silencio la corrida cara es exactamente la clase de promesa
    incumplida que este repo persigue.
    """
    if len(args.archivos) != 1:
        print("⛔ --dirigida toma UN módulo: python tools/mutar.py --dirigida scripts/foo.py")
        return 2
    a = args.archivos[0]
    blanco = Path(a) if Path(a).is_absolute() else RAIZ / a
    if (rechazo := scope_refusal(blanco, "dirigido",
                                 f"\n   Corré el barrido completo sobre el módulo: "
                                 f"python tools/mutar.py {a}")):
        print(rechazo)
        return 2
    propio = test_file_for(blanco)
    only = {s.strip() for s in args.solo.split(",") if s.strip()} or None
    nombres = {n for n, _, _ in funciones(blanco)}
    # #339 — el mismo `--solo main scripts/triage.py` que #335 arregló en `--guardas` seguía acá
    # diciendo «no existen en triage.py: ['main']» sobre una función que existe y tiene 56 `if`:
    # la conflación, y encima sin el hedge que el mensaje viejo de `--guardas` sí tenía.
    if only and (faltan := only - nombres):
        _report_unmutable(blanco, faltan)
        return 2
    # ⛔ Cero mutaciones NO es "murieron todas" (D-43 aplicado a esta herramienta). `ingest_star.py`
    # es todo `main` —que está en EXENTAS— así que el modo corría cero mutantes y cerraba con un ✅
    # que nadie había medido. Un cero inventado se lee como veredicto.
    a_mutar = nombres & only if only else nombres
    if not a_mutar:
        print(f"⛔ {blanco.name} no tiene ninguna función mutable (¿todo `main`/`__init__`, que "
              f"están exentas?): no hay nada que medir, y eso NO es un verde.")
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="almagesto-dirigida-"))
    try:
        copia = _copia_del_repo(tmp / "repo")
        print(f"copia de trabajo: {copia}  (el árbol real NO se toca)")
        print(f"· {blanco.name} contra tests/{propio.name}")
        sobreviven = mutar_archivo(blanco, copia, escalate=False, only=only)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if sobreviven:
        print(f"\n{len(sobreviven)} sin test propio que las mate: {', '.join(sobreviven)}")
        print("   (dirigida no escala: puede que otro archivo de tests sí las mate — "
              "confirmalo con `python tools/mutar.py " + a + "`)")
        return 1
    print("\nmurieron todas en su propio test ✅")
    return 0


class Guard(NamedTuple):
    """One mutable condition: where its source span is and what literal neutralizes it."""
    func: str
    label: str
    lineno: int
    col: int
    end_lineno: int
    end_col: int
    replacement: str


def _guard_mutants(test: ast.expr, func: str) -> list[Guard]:
    """The mutants of a single `if` condition: the whole test, then each `and`/`or` clause.

    A clause is neutralized with the identity of its operator -- `True` inside an `and`, `False`
    inside an `or` -- so the guard keeps firing on the OTHER clauses. That is what makes this
    finer than emptying the condition: `if a and b` with a test that only ever supplies `a=False`
    never exercises `b`, and only the per-clause mutant says so.

    A constant condition is skipped: rewriting `False` as `False` changes nothing, so it would be
    reported as a survivor -- a finding the tool invented.
    """
    out: list[Guard] = []
    if not isinstance(test, ast.Constant):
        out.append(Guard(func, f"if@L{test.lineno}", test.lineno, test.col_offset,
                         test.end_lineno or test.lineno, test.end_col_offset or 0, "False"))
    if isinstance(test, ast.BoolOp):
        es_and = isinstance(test.op, ast.And)
        neutro, op = ("True", "and") if es_and else ("False", "or")
        for i, clausula in enumerate(test.values):
            if isinstance(clausula, ast.Constant):
                continue
            out.append(Guard(func, f"if@L{test.lineno}/{op}[{i}]",
                             clausula.lineno, clausula.col_offset,
                             clausula.end_lineno or clausula.lineno, clausula.end_col_offset or 0,
                             neutro))
    return out


def guards(archivo: Path) -> list[Guard]:
    """Every `if` condition inside a function, plus each clause of a compound one.

    WHY (AUD-213). The function-level mutant empties the whole body, so a module where every
    mutant dies still says nothing about its **guards**: a subagent reading `entity.py` counted 30
    of 84 and `harvest_views.py` 18 of 72 with no test that distinguishes them. The question here
    is narrower and different -- *does any test exercise the case this guard catches?*

    Only the "never fires" direction is emitted. Forcing a guard to fire ALWAYS is the other
    direction and it dies trivially nearly everywhere -- a `raise`/`return` that runs
    unconditionally breaks every caller -- so it costs one run per guard and reports nothing.

    `elif` is an `If` nested in `orelse`, so it is picked up like any other; a comprehension's `if`
    is not an `ast.If` and stays out. Module-level conditions (`if __name__ == ...`,
    `if TYPE_CHECKING:`) are out too: this walks only inside functions.
    """
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    out: list[Guard] = []

    def _walk(nodo: ast.AST, func: str) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _walk(hijo, hijo.name if hijo.name not in EXENTAS else "")
                continue
            if isinstance(hijo, ast.If) and func:
                out.extend(_guard_mutants(hijo.test, func))
            _walk(hijo, func)

    _walk(arbol, "")
    return out


def defined_functions(archivo: Path) -> set[str]:
    """Every function name the module defines, **exempt ones included** (#335).

    `funciones()` and `guards()` both drop what `EXENTAS` covers, so neither can tell *«the symbol
    is exempt»* from *«the symbol is not there»* -- and those two ask for opposite actions. This is
    the only reader that answers "does this name exist at all?"."""
    return {n.name for n in ast.walk(ast.parse(archivo.read_text(encoding="utf-8")))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def unmutable_reasons(archivo: Path, nombres: set[str]) -> dict[str, list[str]]:
    """Split the requested names that have nothing to mutate into the three states of D-43 (#335).

    `exenta` (it is there, `EXENTAS` excluded it -- move the condition into a function of its own),
    `sin_guardas` (it is there and carries no mutable condition -- a zero with a legitimate cause)
    and `no_existe` (a typo in `--solo`). One message for all three sent the reader looking for a
    typo in a name that was correct: measured on #331, whose new guard lived inside `main` and was
    therefore invisible to every mutation net -- the implementer moved it out on his own judgement,
    not because the tool said so.

    Keys are always present, values sorted: an empty list is «none in this state», never «not
    looked at»."""
    definidas = defined_functions(archivo)
    fuera: dict[str, list[str]] = {"exenta": [], "sin_guardas": [], "no_existe": []}
    for nombre in sorted(nombres):
        if nombre not in definidas:
            fuera["no_existe"].append(nombre)
        elif nombre in EXENTAS:
            fuera["exenta"].append(nombre)
        else:
            fuera["sin_guardas"].append(nombre)
    return fuera


def report_states(fuera: dict[str, list[str]], textos: dict[str, str]) -> int:
    """The ONE implementation of a D-43 split report: one line per non-empty state, never merged.

    Returns how many states it printed, so a caller can tell «nothing to say» from «said it».

    ⛔ One line **per state**: the whole point is that the states ask for different actions, so
    joining them back into a single sentence restores the conflation even with the texts written
    apart. #335 wrote this inline for `--guardas`; #339 found the same conflation still live in
    `--dirigida` and in `--trazabilidad` — that is what a rule kept in three copies does. It lives
    here now, and every mode closes through it.

    `fuera` is a partition: every key present, an empty list reading «none in this state» and never
    «not looked at». A state with names and no text in `textos` raises instead of being skipped —
    a silent skip is the merged message again, only invisible.
    """
    dichos = 0
    for estado, nombres in fuera.items():
        if not nombres:
            continue
        print(textos[estado].format(nombres=", ".join(nombres)))
        dichos += 1
    return dichos


def _report_unmutable(archivo: Path, nombres: set[str]) -> None:
    """Print the three states of `unmutable_reasons` for `--guardas` and `--dirigida` (#335/#339).

    The `exenta` line is worded for BOTH modes on purpose: `--dirigida` empties bodies and
    `--guardas` neutralizes conditions, but `EXENTAS` hides the symbol from either, and the remedy
    is the same one #331 had to find on its own. `sin_guardas` is unreachable from `--dirigida`
    (every defined name that is not exempt is mutable there), so it stays worded for guards."""
    mod = archivo.name
    report_states(unmutable_reasons(archivo, nombres), {
        "exenta": f"⛔ no evaluado: {{nombres}} está(n) en EXENTAS de mutar.py, así que ninguna red "
                  f"de mutación las mira en {mod} — mové el código a una función propia para que "
                  f"alguna red lo mire (es lo que #331 tuvo que descubrir solo).",
        "sin_guardas": f"⛔ no evaluado: {{nombres}} no tiene(n) ningún condicional mutable en "
                       f"{mod}: no hay nada que medir, y eso NO es un verde (D-43).",
        "no_existe": f"⛔ no existe en {mod}: {{nombres}} — ¿typo en `--solo`?",
    })


def _replace_span(source: str, g: Guard) -> str:
    """`source` with the guard's span replaced by its neutral literal.

    ⚠ `col_offset` is a UTF-8 **byte** offset, not a character index, and this repo's source is
    full of accented prose and arrows -- slicing the `str` would cut mid-condition on any line that
    carries a non-ASCII comment. So the slice happens on the encoded line and is decoded back.

    A condition spanning several lines collapses into one: everything before the span on the first
    line, the literal, everything after it on the last. The lines in between go away with it.
    """
    lineas = source.split("\n")
    primera = lineas[g.lineno - 1].encode("utf-8")
    ultima = lineas[g.end_lineno - 1].encode("utf-8")
    fusion = (primera[:g.col] + g.replacement.encode("utf-8") + ultima[g.end_col:]).decode("utf-8")
    return "\n".join(lineas[:g.lineno - 1] + [fusion] + lineas[g.end_lineno:])


def mutate_guards(archivo: Path, copia_raiz: Path, subset: Path, only: set[str] | None = None,
                  verbose: bool = True) -> list[str]:
    """Guards that **survive**: no test in `subset` went red when the guard stopped firing.

    `archivo` is read from the REAL tree; its twin inside `copia_raiz` is what gets mutated -- same
    rule as `mutar_archivo`, and for the same reason (a harness that can corrupt the code it audits
    does not survive a Ctrl-C).
    """
    original = archivo.read_text(encoding="utf-8")
    gemelo = copia_raiz / archivo.relative_to(RAIZ)
    sobreviven = []
    for g in guards(archivo):
        if only is not None and g.func not in only:
            continue
        gemelo.write_text(_replace_span(original, g), encoding="utf-8")
        try:
            vivo = _suite_verde(copia_raiz, subset)
        except subprocess.TimeoutExpired:
            vivo = True
        etiqueta = f"{g.func}::{g.label}"
        if vivo:
            sobreviven.append(etiqueta)
        if verbose:
            # #393 — the mutant applied goes on the line: a clause is neutralised with the IDENTITY
            # of its operator, and reproducing it by hand with `False` measures another mutant.
            print(f"  {'SOBREVIVE' if vivo else 'muere    '}  {archivo.name}::{etiqueta}"
                  f"\u2192{g.replacement}", flush=True)
    gemelo.write_text(original, encoding="utf-8")   # deja la copia sana
    return sobreviven


def _guards(args) -> int:
    """AUD-213 -- guard-level mutation: ONE module against its own test file.

    Same contract as `--dirigida`, for the same reason: it does not escalate to the full suite, so
    it **over-reports survivors and never gives a false clean**, and it does NOT touch the ratchet
    (the ratchet counts functions; mixing two populations into one number would make the ceiling
    mean nothing).

    Unlike `--dirigida` it checks the BASELINE first. If `tests/test_<mod>.py` is already red every
    mutant "dies" for the wrong reason and the mode prints zero survivors -- the zero nobody
    measured (D-43), inside the tool whose job is auditing tests. It is also #202 exactly: a test
    has to die BY THE REASON it tests.
    """
    if len(args.archivos) != 1:
        print("⛔ --guardas toma UN módulo: python tools/mutar.py --guardas scripts/foo.py")
        return 2
    a = args.archivos[0]
    blanco = Path(a) if Path(a).is_absolute() else RAIZ / a
    if (rechazo := scope_refusal(blanco, "de guardas")):
        print(rechazo)
        return 2
    propio = test_file_for(blanco)
    only = {s.strip() for s in args.solo.split(",") if s.strip()} or None
    todas = guards(blanco)
    # #335 — «está en EXENTAS» y «el símbolo no existe» piden acciones OPUESTAS y salían con el
    # mismo texto: es el D-43 que este módulo predica dos líneas más abajo, aplicado al conteo de
    # mutaciones y no a la resolución de símbolos.
    if only and (faltan := only - {g.func for g in todas}):
        _report_unmutable(blanco, faltan)
        return 2
    # ⛔ Cero guardas NO es "murieron todas" (D-43): un módulo sin un solo `if` no se midió.
    a_mutar = [g for g in todas if only is None or g.func in only]
    if not a_mutar:
        print(f"⛔ {blanco.name} no tiene ninguna guarda mutable: no hay nada que medir, y eso NO "
              f"es un verde.")
        return 2

    subset = Path("tests") / propio.name
    tmp = Path(tempfile.mkdtemp(prefix="almagesto-guardas-"))
    try:
        copia = _copia_del_repo(tmp / "repo")
        print(f"copia de trabajo: {copia}  (el árbol real NO se toca)")
        if not _suite_verde(copia, subset):
            print(f"⛔ no evaluado: tests/{propio.name} ya está roja sin mutar — con la baseline "
                  f"en rojo TODA guarda 'muere' por el motivo equivocado y el modo devuelve 0 "
                  f"sobrevivientes (#202).")
            return 2
        print(f"· {blanco.name}: {len(a_mutar)} guarda(s) contra tests/{propio.name}")
        sobreviven = mutate_guards(blanco, copia, subset, only=only)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if sobreviven:
        print(f"\n{len(sobreviven)} de {len(a_mutar)} guarda(s) sin test que las distinga:")
        for s in sobreviven:
            print(f"  - {s}")
        print("   (no escala a la suite: puede que otro archivo de tests sí las mate)")
        print("   (cada cláusula se neutraliza con la IDENTIDAD de su operador —`True` en un `and`, "
              "`False` en un `or`—; para reproducirla a mano usá ESE literal, #393)")
        return 1
    print(f"\nlas {len(a_mutar)} guardas mueren en su propio test ✅")
    return 0


def _traceability_pairs() -> list[tuple[str, Path, str, list[str]]]:
    """`(inv, impl file, impl symbol, [marked tests])` for every invariant marked in BOTH trees.

    Only those: with no test mark there is no attribution to audit. Pytest nodeids are built from
    the symbol that holds the mark (`tests/x.py::test_y`), so a module-level mark cannot be run on
    its own and is dropped."""
    sys.path.insert(0, str(RAIZ / "scripts"))
    import trace_invariants as ti
    registro = ti.load_contract(RAIZ)
    por_inv: dict = {}
    for m in ti.collect_marks(RAIZ):
        por_inv.setdefault(m.inv, []).append(m)
    out = []
    for inv, marcas in sorted(por_inv.items()):
        if inv not in registro or ti.is_retired(registro[inv]):
            continue
        impls = [m for m in marcas if m.kind == "impl" and m.symbol
                 and m.path.startswith("scripts/")]
        tests = sorted({f"{m.path}::{m.symbol}" for m in marcas if m.kind == "test" and m.symbol})
        if not tests:
            continue
        # TODAS las implementaciones marcadas, no la primera: lo que la fila afirma es que **esos**
        # símbolos la cumplen y **esos** tests la prueban, así que cada símbolo tiene que estar
        # cubierto por alguno. Auditar sólo el primero dejaba pasar la marca puesta de más.
        for m in impls:
            out.append((inv, RAIZ / m.path, m.symbol, tests))
    return out


def unmarked_reasons(invs: set[str], filas: set[str], retirados: set[str],
                     auditables: set[str]) -> dict[str, list[str]]:
    """Split the `--solo` invariants that `--trazabilidad` cannot audit into three states (#339).

    `no_existe` (not a row of §3 of `docs/contrato.md` — a typo in `--solo`), `retirado` (the row is
    there and retired **on purpose**, so it carries no mark by design and there is no attribution to
    audit) and `sin_marcas` (the row is live and lacks the `@inv` of the implementation and/or of
    the test — the remedy is to ADD the mark, never to fix the argument).

    One message for the three read *«no existen (o no tienen las dos marcas)»*, byte-identical for
    `INV-999-NOPE` and for `INV-126` — which exists, is P0, and whose own row says «hay código sin
    marcar». Sending the reader to hunt a typo in a correct name is the same defect #335 closed one
    mode over.

    An invariant that IS auditable falls in no bucket: the caller passes everything it was asked
    for, and what comes back is only what could not be measured."""
    fuera: dict[str, list[str]] = {"no_existe": [], "retirado": [], "sin_marcas": []}
    for inv in sorted(invs):
        if inv not in filas:
            fuera["no_existe"].append(inv)
        elif inv in retirados:
            fuera["retirado"].append(inv)
        elif inv not in auditables:
            fuera["sin_marcas"].append(inv)
    return fuera


def _contract_rows() -> tuple[set[str], set[str]]:
    """`(every INV row of §3 of the contract, the retired ones)` — the two sets of `unmarked_reasons`."""
    sys.path.insert(0, str(RAIZ / "scripts"))
    import trace_invariants as ti
    registro = ti.load_contract(RAIZ)
    return set(registro), {inv for inv, meta in registro.items() if ti.is_retired(meta)}


def _trazabilidad(args) -> int:
    """AUD-212 — audit the map's ATTRIBUTION: does the marked test prove the marked symbol?

    `docs/trazabilidad.md` measures **that somebody put the mark**, not that the mark sits on code
    the test covers — the first of the two method lessons of the `/auditar` pass («the defect is
    almost never in the marked function: it is in the caller or in the copy»). Without this, a row
    can claim coverage that does not exist, and *a map that misattributes is worse than an empty
    one* — in the very artifact whose job is not to misattribute.

    The experiment is the minimum that decides: empty the marked implementation and run **only the
    marked test**. If it still passes, that test does not prove that symbol.

    ⚠ **Over-reports, never gives a false clean**, like `--dirigida`, and for two reasons worth
    naming. One test is run, so a symbol another test does cover shows up anyway — but what the row
    claims is that pairing, not the suite. And the mutation writes `return None`, so a predicate
    whose FALSE branch is the one under test survives by coincidence (`ocr_available` is the measured
    case): the answer there is to mark a test that exercises the true branch, not to loosen the gate."""
    pares = _traceability_pairs()
    if not pares:
        print("⛔ no evaluado: ningún invariante tiene marca de implementación Y de test")
        return 2
    solo = {x.strip() for x in args.solo.split(",") if x.strip()}
    if solo:
        filas, retirados = _contract_rows()
        fuera = unmarked_reasons(solo, filas, retirados, {p[0] for p in pares})
        # ⛔ Rehúsa en cuanto UNO de los pedidos no se puede auditar, aunque el resto sí: se pidieron
        # N filas y se midieron M < N, y un 0 sobre M leído como veredicto de N es el falso limpio
        # que D-43 nombra. Antes sólo se rehusaba si NINGUNO quedaba en pie.
        if report_states(fuera, {
            "no_existe": "⛔ no existe en docs/contrato.md §3: {nombres} — ¿typo en `--solo`?",
            "retirado": "⛔ no evaluado: {nombres} está(n) RETIRADO(s) en el contrato, así que no "
                        "lleva(n) marcas a propósito (§2) — no hay atribución que auditar.",
            "sin_marcas": "⛔ no evaluado: {nombres} existe(n) y está(n) vivo(s), pero le(s) falta "
                          "la marca `@inv` de implementación y/o de test — el remedio es AGREGAR "
                          "la marca, no corregir el `--solo`.",
        }):
            return 2
        pares = [p for p in pares if p[0] in solo]
    tmp = Path(tempfile.mkdtemp(prefix="almagesto-traza-"))
    falsas = []
    try:
        copia = _copia_del_repo(tmp / "repo")
        print(f"copia de trabajo: {copia}  (el árbol real NO se toca)")
        for inv, archivo, simbolo, tests in pares:
            gemelo = copia / archivo.relative_to(RAIZ)
            original = gemelo.read_text(encoding="utf-8")
            fn = next((f for f in funciones(gemelo) if f[0] == simbolo), None)
            if fn is None:
                print(f"  ·          {inv}: `{simbolo}` no es una función mutable "
                      f"(clase/constante/EXENTA) — no evaluado")
                continue
            _, ini, fin = fn
            lineas = original.split("\n")
            sangria = len(lineas[ini - 1]) - len(lineas[ini - 1].lstrip())
            gemelo.write_text("\n".join(lineas[:ini - 1] + [" " * sangria + "return None"]
                                        + lineas[fin:]), encoding="utf-8")
            try:
                vivo = all(_suite_verde(copia, Path(t)) for t in tests)
            except subprocess.TimeoutExpired:
                vivo = True
            finally:
                gemelo.write_text(original, encoding="utf-8")
            print(f"  {'ATRIBUCIÓN FALSA' if vivo else 'ok              '}  {inv}: "
                  f"{archivo.name}::{simbolo} ← {', '.join(t.split('::')[-1] for t in tests)}")
            if vivo:
                falsas.append(f"{inv} ({archivo.name}::{simbolo})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(pares)} fila(s) auditadas · {len(falsas)} con atribución FALSA")
    for f in falsas:
        print(f"  - {f}")
    if falsas:
        print("\n  → el test marcado pasa con la implementación marcada VACÍA: o la marca está en "
              "el símbolo equivocado, o ese test prueba otra cosa. Mover la marca o marcar el test "
              "que sí lo cubre — no borrar la fila.")
    return 1 if falsas else 0


def main() -> int:
    # E-13: the docstring is hard-wrapped at 100 columns, so its first PHYSICAL line ends mid-sentence
    # («…exigir que **algún test»). The description is the first PARAGRAPH, reflowed.
    ap = argparse.ArgumentParser(description=" ".join(__doc__.split("\n\n")[0].split()))
    ap.add_argument("archivos", nargs="*", help="archivos de scripts/ o tools/ a mutar")
    ap.add_argument("--diff", action="store_true", help="los que cambiaron vs HEAD")
    ap.add_argument("--todo", action="store_true", help="todo scripts/ + tools/")
    ap.add_argument("--ratchet", action="store_true", help="comparar contra el techo y salir 1 si sube")
    ap.add_argument("--dirigida", action="store_true",
                    help="modo barato: muta UN módulo y corre SÓLO su archivo de tests (no es el gate)")
    ap.add_argument("--guardas", action="store_true",
                    help="AUD-213: muta cada CONDICIÓN (no el cuerpo) de UN módulo contra su "
                         "archivo de tests — mide si algún test ejercita el caso que la guarda "
                         "ataja. No toca el ratchet.")
    ap.add_argument("--solo", default="",
                    help="con --dirigida/--guardas: nombres de función separados por coma; con "
                         "--trazabilidad: ids de invariante (default: todos)")
    ap.add_argument("--trazabilidad", action="store_true",
                    help="AUD-212: audita la ATRIBUCIÓN del mapa — vacía la implementación marcada "
                         "`@inv` y corre SÓLO el test marcado. Si pasa, esa fila afirma una "
                         "cobertura que no existe.")
    args = ap.parse_args()

    if args.trazabilidad:
        return _trazabilidad(args)
    if args.guardas:
        return _guards(args)
    if args.dirigida:
        return _directed(args)

    if args.todo:
        objetivo = sorted(p for d in ALCANCE for p in (RAIZ / d).glob("*.py"))
    elif args.diff:
        objetivo = archivos_del_diff()
    else:
        objetivo = [Path(a) if Path(a).is_absolute() else RAIZ / a for a in args.archivos]
    if not objetivo:
        print(f"nada que mutar (¿`--diff` sin cambios en {_ALCANCE_TXT}?)")
        return 0
    # #345 — el exento se NOMBRA con su motivo antes de sacarlo. Filtrarlo en silencio dejaría al
    # barrido publicando una población de la que faltan módulos sin decir cuáles ni por qué, que es
    # la exención por omisión que este mapa vino a reemplazar.
    objetivo, exentos = split_exempt(objetivo)
    for f, motivo in exentos:
        print(f"· {f.parent.name}/{f.name}: EXENTO de la red por decisión declarada — {motivo}")
    if not objetivo:
        # ⛔ D-43 — todo lo seleccionado era exento: no se midió NADA, y un 0 sobre cero mutantes
        # comparado contra el techo del ratchet sería el falso limpio adentro del detector de falsos
        # limpios. La exención explica el cero; no lo convierte en un verde.
        print("⛔ no evaluado: todo lo seleccionado está EXENTO, así que no se mutó ni una función "
              "— eso NO es un verde.")
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="almagesto-mutacion-"))
    try:
        copia = _copia_del_repo(tmp / "repo")
        print(f"copia de trabajo: {copia}  (el árbol real NO se toca)")
        if not _suite_verde(copia):
            print("⛔ la suite ya está roja sin mutar: arreglá eso antes (si no, todo 'muere' por "
                  "el motivo equivocado)")
            return 2

        total, sobreviven = 0, []
        for f in objetivo:
            print(f"· {f.name}")
            vivos = mutar_archivo(f, copia)
            total += len(funciones(f))
            sobreviven += [f"{f.name}::{n}" for n in vivos]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\nfunciones mutadas: {total} · sobreviven (sin test que las mate): {len(sobreviven)}")
    for s in sobreviven:
        print(f"  - {s}")
    if args.ratchet and not RATCHET.exists():
        # AUD-138 / D-43 — el gate PEDIDO que no puede correr no sale verde. Sin el archivo, el
        # `and RATCHET.exists()` saltaba el bloque entero y `main` devolvía 0 **con
        # sobrevivientes**: pedir el ratchet y no tenerlo se leía igual que pasarlo. Es el mismo
        # cero inventado que el lint reporta como *no evaluado*, en la herramienta que audita a
        # los tests.
        print(f"\n⛔ no evaluado: se pidió `--ratchet` y no existe {RATCHET} — no hay techo contra "
              f"el que comparar los {len(sobreviven)} sobreviviente(s)")
        return 2
    if args.ratchet:
        import yaml
        try:
            datos = yaml.safe_load(RATCHET.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            print(f"\n⛔ no evaluado: {RATCHET} no se pudo leer ({exc})")
            return 2
        if "techo" not in datos:
            print(f"\n⛔ no evaluado: {RATCHET} no declara `techo` — un default 0 convertiría "
                  f"cualquier sobreviviente en rojo y un default alto lo taparía")
            return 2
        techo = datos["techo"]
        print(f"\ntecho del ratchet: {techo}")
        if len(sobreviven) > techo:
            print("⛔ subió: hay funciones nuevas sin test que las mate")
            return 1
        if len(sobreviven) < techo:
            print(f"✅ bajó a {len(sobreviven)} — actualizá `techo` en {RATCHET.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
