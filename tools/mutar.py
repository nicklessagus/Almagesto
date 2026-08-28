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


def mutar_archivo(archivo: Path, copia_raiz: Path, verbose=True, two_stage: bool = True) -> list[str]:
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
    daba vivo—, y eso sería un defecto de aislamiento del test, que conviene ver."""
    original = archivo.read_text(encoding="utf-8")
    gemelo = copia_raiz / archivo.relative_to(RAIZ)
    propio = test_file_for(archivo) if two_stage else None
    subset = Path("tests") / propio.name if propio else None
    sobreviven = []
    for nombre, ini, fin in funciones(archivo):
        lineas = original.split("\n")
        sangria = len(lineas[ini - 1]) - len(lineas[ini - 1].lstrip())
        gemelo.write_text("\n".join(lineas[:ini - 1] + [" " * sangria + "return None"] + lineas[fin:]),
                          encoding="utf-8")
        etapa = ""
        try:
            # Etapa 1: el archivo de tests del propio módulo. Una muerte acá es una muerte.
            vivo = _suite_verde(copia_raiz, subset) if subset else True
            if vivo and subset:
                etapa = " (sobrevivió a su propio test; se pagó la suite)"
            # Etapa 2: sólo los sobrevivientes pagan la suite completa.
            if vivo:
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
        if f.startswith("scripts/") and f.endswith(".py") and f not in vistos:
            vistos.add(f)
            archivos.append(RAIZ / f)
    return archivos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("archivos", nargs="*", help="archivos de scripts/ a mutar")
    ap.add_argument("--diff", action="store_true", help="los que cambiaron vs HEAD")
    ap.add_argument("--todo", action="store_true", help="todo scripts/")
    ap.add_argument("--ratchet", action="store_true", help="comparar contra el techo y salir 1 si sube")
    args = ap.parse_args()

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
    if args.ratchet and RATCHET.exists():
        import yaml
        techo = (yaml.safe_load(RATCHET.read_text(encoding="utf-8")) or {}).get("techo", 0)
        print(f"\ntecho del ratchet: {techo}")
        if len(sobreviven) > techo:
            print("⛔ subió: hay funciones nuevas sin test que las mate")
            return 1
        if len(sobreviven) < techo:
            print(f"✅ bajó a {len(sobreviven)} — actualizá `techo` en {RATCHET.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
