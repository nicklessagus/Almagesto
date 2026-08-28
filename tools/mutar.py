"""Gate de mutación: por cada función de `scripts/`, romperla y exigir que **algún test muera**.

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

RAIZ = Path(__file__).resolve().parent.parent
RATCHET = Path(__file__).resolve().parent / "mutacion-ratchet.yaml"
# Funciones que NO se mutan, con motivo. Sin motivo no se agrega nada acá.
EXENTAS = {
    "main",              # orquestación: su contrato son los sub-pasos, ya mutados por separado
    "__init__",
}


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
    """`scripts/foo.py` -> `tests/test_foo.py`, or None when there is no 1:1 file.

    Stage 1 of the two-stage sweep needs a file that is *part of the suite stage 2 would run*; that
    is what makes the split safe (a death there is a death). A wider guess -- every test file that
    imports the module -- would buy little and cost the property.

    `lib_config` is killed by tests all over the repo and `poblada/` is another tier: for those the
    stage is skipped, not approximated.
    """
    if module.parent.name != "scripts":
        return None
    candidato = RAIZ / "tests" / f"test_{module.stem}.py"
    return candidato if candidato.exists() else None


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
    """
    #  @inv INV-101
    salida = []
    for args in (["diff", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]):
        r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True)
        salida += r.stdout.split()
    vistos, archivos = set(), []
    for f in salida:                                  # `git add` de un archivo nuevo lo pone en los dos
        if not (f.startswith("scripts/") and f.endswith(".py")) or f in vistos:
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
    propio = test_file_for(blanco)
    if propio is None:
        print(f"⛔ no hay tests/test_{blanco.stem}.py: sin etapa barata no hay modo dirigido.\n"
              f"   Corré el barrido completo sobre el módulo: python tools/mutar.py {a}")
        return 2
    only = {s.strip() for s in args.solo.split(",") if s.strip()} or None
    nombres = {n for n, _, _ in funciones(blanco)}
    if only and (faltan := only - nombres):
        print(f"⛔ no existen en {blanco.name}: {sorted(faltan)}")
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


def _traceability_pairs() -> list[tuple[str, Path, str, list[str]]]:
    """`(inv, impl file, impl symbol, [marked tests])` for every invariant marked in BOTH trees.

    Only those: with no test mark there is no attribution to audit. Pytest nodeids are built from
    the symbol that holds the mark (`tests/x.py::test_y`), so a module-level mark cannot be run on
    its own and is dropped."""
    sys.path.insert(0, str(RAIZ / "scripts"))
    import trace_invariants as ti
    registro = ti.load_registro(RAIZ)
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
        pares = [p for p in pares if p[0] in solo]
        if not pares:
            print(f"⛔ no existen (o no tienen las dos marcas): {', '.join(sorted(solo))}")
            return 2
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
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("archivos", nargs="*", help="archivos de scripts/ a mutar")
    ap.add_argument("--diff", action="store_true", help="los que cambiaron vs HEAD")
    ap.add_argument("--todo", action="store_true", help="todo scripts/")
    ap.add_argument("--ratchet", action="store_true", help="comparar contra el techo y salir 1 si sube")
    ap.add_argument("--dirigida", action="store_true",
                    help="modo barato: muta UN módulo y corre SÓLO su archivo de tests (no es el gate)")
    ap.add_argument("--solo", default="",
                    help="con --dirigida: nombres de función separados por coma; con "
                         "--trazabilidad: ids de invariante (default: todos)")
    ap.add_argument("--trazabilidad", action="store_true",
                    help="AUD-212: audita la ATRIBUCIÓN del mapa — vacía la implementación marcada "
                         "`@inv` y corre SÓLO el test marcado. Si pasa, esa fila afirma una "
                         "cobertura que no existe.")
    args = ap.parse_args()

    if args.trazabilidad:
        return _trazabilidad(args)
    if args.dirigida:
        return _directed(args)

    if args.todo:
        objetivo = sorted((RAIZ / "scripts").glob("*.py"))
    elif args.diff:
        objetivo = archivos_del_diff()
    else:
        objetivo = [Path(a) if Path(a).is_absolute() else RAIZ / a for a in args.archivos]
    if not objetivo:
        print("nada que mutar (¿`--diff` sin cambios en scripts/?)")
        return 0

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
