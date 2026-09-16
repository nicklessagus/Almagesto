"""¿Quién MÁS lleva esta regla? — el gate que cierra la familia «fix a la instancia, no a la clase».

    python tools/carriers.py --check                 # gatea: la declaración contra el código
    python tools/carriers.py --propose lib_config.txt_slug --patron 'FULLTEXT\\s*/'

POR QUÉ EXISTE. Cuatro lectores independientes clasificaron los ~400 issues del repo por mecanismo,
sin verse entre ellos, y tres nombraron el mismo tema dominante (el cuarto, su causa): **el fix se
escribe contra el caso medido y no contra la relación estructural que lo contiene**. Medido: 45 de
100 issues en un tramo, ~50 en otro, 32 en el último; y casi la mitad se presenta a sí mismo con la
fórmula literal «#N lo cerró para X y dejó Y igual» — #405 es #305 para el `.txt`, #406 es #389 con
prosa, #395 es #372 en la primera lente, #325 es #316 dentro de su propio fix.

El repo ya tenía la comprensión (regla de método 2: «un doble o deriva de la función real, o tiene
un test de paridad») y no la tenía como gate: rige tests, no código de producción. Y el barrido «por
el patrón» se hacía a ojo, así que paraba donde el agente dejaba de mirar — los propios issues lo
dicen: «2 de 4», «dos más», «del mismo barrido».

QUÉ CHEQUEA. Cada entrada de `tools/portadores.yaml` declara una regla, la ÚNICA función que la
implementa, y el patrón por el que se reconoce a un portador en el código. El chequeo es
**bidireccional**, como el de `trace_invariants`:

  1. la función existe;
  2. todo módulo que la LLAMA está declarado (si no: portador sin declarar);
  3. todo módulo declarado `usa` la llama de verdad — ésta es la que caza el caso medido en #347,
     donde un comentario «delega en X» sustituía a delegar;
  4. todo módulo que matchea el `patron` está declarado `usa` **o** `fuera-de-alcance`;
  5. todo `fuera-de-alcance` lleva `motivo` (mismo argumento que el `--reason` del triage: en seis
     meses sirve el motivo, no la categoría).

⛔ **Declara y compara; no aplica nada.** Cuál módulo debe usar la función es juicio, y elegir en
silencio decide por el usuario (regla de método 5). Lo que este gate impide es cerrar sin haber
mirado: el `patron` es la relación estructural escrita, y el que no la escribe no puede pasar.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DECLARACION = ROOT / "tools" / "portadores.yaml"
ARBOLES = ("scripts", "tools")
ESTADOS = ("usa", "fuera-de-alcance")


class DeclaracionIlegible(Exception):
    """`portadores.yaml` no se pudo leer: sin él no se afirma nada (D-43)."""


def source_modules(root: Path = ROOT) -> dict:
    """`{ruta relativa: fuente}` de todo `.py` de `scripts/` y `tools/`, en orden estable."""
    out: dict = {}
    for arbol in ARBOLES:
        base = root / arbol
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            out[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return out


def calls(fuente: str, modulo: str, simbolo: str) -> bool:
    """Does this module CALL `modulo.simbolo`? By AST, never by `in` over the text.

    Both call shapes count: an attribute of the imported module (`cfg.txt_slug(...)`, under whatever
    alias that file gave it) and an imported name (`from lib_config import txt_slug`). A `grep`
    would count the mention in a comment or a docstring — which is exactly what #347 measured: the
    comment said «delegates to X» and did not delegate."""
    try:
        arbol = ast.parse(fuente)
    except SyntaxError:
        return False
    alias, directo = set(), False
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name == modulo:
                    alias.add(a.asname or a.name)
        elif isinstance(n, ast.ImportFrom) and n.module == modulo:
            directo = directo or any(a.name == simbolo for a in n.names)
    for n in ast.walk(arbol):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute) and f.attr == simbolo \
                and isinstance(f.value, ast.Name) and f.value.id in alias:
            return True
        if directo and isinstance(f, ast.Name) and f.id == simbolo:
            return True
    return False


def es_callable(fuente: str, simbolo: str) -> bool:
    """Is that top-level symbol a function or a class, as opposed to a constant? (#476)

    It decides HOW a consumer carries the rule: a function is carried by CALLING it, a table or a
    closed vocabulary by READING it. A re-export (`from lib_quotes import …`, AUD-306) is treated
    as callable, which is the historical behaviour: the facade exists so consumers call through it.
    """
    try:
        arbol = ast.parse(fuente)
    except SyntaxError:
        return True                       # no se pudo decidir: el criterio de siempre
    for n in arbol.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and n.name == simbolo:
            return True
        if isinstance(n, ast.Assign) and any(getattr(x, "id", None) == simbolo
                                             for x in n.targets):
            return False                  # asignación a nivel módulo: una constante
    return True


def reads(fuente: str, modulo: str, simbolo: str) -> bool:
    """Does this module READ `modulo.simbolo`? By AST, like `calls` (#476).

    ⛔ The gate asks «does this module carry the rule?», and until #476 it could only see one of the
    two ways of carrying one. `calls` looks at `ast.Call`, so a rule whose shared carrier is a
    **constant** —a table, a closed vocabulary, a regex— was **impossible to declare**: read as an
    attribute (`cfg.BIBTEX_NO_PEGABLE`) it is never a call, and the gate answered «declared `usa`
    and does NOT call». Both remaining options were bad: calling a real carrier `fuera-de-alcance`
    (a false attribution, which method rule nº 4 calls worse than a blank) or leaving the rule
    undeclared. Measured on the template: `lib_config` exposes 86 public constants, **32 read by two
    or more modules** —32 candidates to be the shared carrier of a rule— and **zero** declared.

    ⚠ Deliberately NOT used for a callable symbol (see `carries`): counting a mere mention of a
    function name would undo #347, where the comment said «delegates to X» and did not delegate.
    """
    try:
        arbol = ast.parse(fuente)
    except SyntaxError:
        return False
    alias, directo = set(), False
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name == modulo:
                    alias.add(a.asname or a.name)
        elif isinstance(n, ast.ImportFrom) and n.module == modulo:
            directo = directo or any(a.name == simbolo for a in n.names)
    for n in ast.walk(arbol):
        if isinstance(n, ast.Attribute) and n.attr == simbolo \
                and isinstance(n.value, ast.Name) and n.value.id in alias:
            return True
        if directo and isinstance(n, ast.Name) and n.id == simbolo:
            return True
    return False


def carries(fuente: str, modulo: str, simbolo: str, dueño_src: str) -> bool:
    """Does this module CARRY the rule that lives in `modulo.simbolo`? (#476)

    ⛔ ONE question with two shapes, and which one applies is decided by what the symbol IS, not by
    the consumer: a function is carried by **calling** it, a constant by **reading** it. Branching
    here rather than counting both for everything is what keeps the veredict of the 52 rules that
    already close at 0 unchanged — `ROOT` and `PAPERS` are touched by half the repo, so counting
    attribute reads for a callable rule would drown the signal."""
    if es_callable(dueño_src, simbolo):
        return calls(fuente, modulo, simbolo)
    return reads(fuente, modulo, simbolo)


def existe(fuente: str, simbolo: str) -> bool:
    """Does this module EXPOSE that symbol at top level? Half (1) of the check.

    ⛔ A **re-export counts** (#454). `lib_config` re-exports every public name of `lib_quotes` on
    purpose (AUD-306) so `cfg.quote_verdict(...)` keeps working for callers, tests and the `@inv`
    map — so consumers import `lib_config as cfg` and call through it, which is what `calls`
    detects. Without counting the `ImportFrom`, a rule implemented in `lib_quotes` **could not be
    declared at all**: named by its real module the gate said «does not call» (nobody imports
    `lib_quotes`), and by its facade, «does not exist». A gate that refuses both forms of the same
    truth leaves the rule undeclared, which is exactly what this tool exists to prevent."""
    try:
        arbol = ast.parse(fuente)
    except SyntaxError:
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
               and n.name == simbolo for n in arbol.body) or any(
        isinstance(n, ast.Assign) and any(getattr(t, "id", None) == simbolo for t in n.targets)
        for n in arbol.body) or any(
        isinstance(n, ast.ImportFrom) and any(
            (a.asname or a.name) == simbolo for a in n.names) for n in ast.walk(arbol))


def load(path: Path = DECLARACION) -> list:
    """Las entradas declaradas. Levanta si el archivo no se puede leer o no tiene la forma."""
    if not path.exists():
        raise DeclaracionIlegible(f"{path} no existe")
    try:
        datos = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DeclaracionIlegible(f"{path}: no parsea — {exc}") from exc
    entradas = (datos or {}).get("portadores")
    if not isinstance(entradas, list):
        raise DeclaracionIlegible(f"{path}: falta la lista `portadores:`")
    return entradas


def entry_errors(entrada: dict, fuentes: dict) -> list:
    """The findings of ONE entry, in the order of the five checks listed in the module docstring."""
    out: list = []
    issue = entrada.get("issue")
    quien = f"#{issue}" if issue else "(entrada sin issue)"
    for campo in ("issue", "regla", "funcion", "patron"):
        if not str(entrada.get(campo) or "").strip():
            out.append(f"{quien}: falta `{campo}` — sin él la entrada no dice qué se cerró ni cómo "
                       f"se reconoce a un portador")
    if out:
        return out

    ref = str(entrada["funcion"])
    if "." not in ref:
        return [f"{quien}: `funcion: {ref}` no es `modulo.simbolo`"]
    modulo, simbolo = ref.rsplit(".", 1)
    dueño = next((r for r in fuentes if Path(r).stem == modulo), None)
    if dueño is None or not existe(fuentes[dueño], simbolo):
        return [f"{quien}: `{ref}` no existe — ¿se renombró la implementación única de la regla?"]

    try:
        patron = re.compile(str(entrada["patron"]))
    except re.error as exc:
        return [f"{quien}: `patron` no compila — {exc}"]

    declarados: dict = {}
    for c in entrada.get("consumidores") or []:
        if not isinstance(c, dict):
            out.append(f"{quien}: un consumidor que no es un mapa ({c!r})")
            continue
        mod, estado = str(c.get("modulo") or ""), str(c.get("estado") or "")
        if estado not in ESTADOS:
            # ⚠ Se registra igual como declarado (con estado inválido): si no, el segundo bucle lo
            # vuelve a reportar como «sin declarar» y el operador ve DOS hallazgos de una sola
            # causa — duplicar el hallazgo manda a hacer dos veces el mismo trabajo.
            out.append(f"{quien}/{mod}: `estado: {estado or '(vacío)'}` fuera del vocabulario "
                       f"({' | '.join(ESTADOS)})")
            declarados[mod] = None
            continue
        if mod not in fuentes:
            out.append(f"{quien}/{mod}: el módulo declarado no existe")
            continue
        if estado == "fuera-de-alcance" and not str(c.get("motivo") or "").strip():
            out.append(f"{quien}/{mod}: `fuera-de-alcance` sin `motivo` — en seis meses sirve el "
                       f"motivo, no la categoría")
        declarados[mod] = estado

    for mod, fuente in fuentes.items():
        if mod == dueño:
            continue
        usa = carries(fuente, modulo, simbolo, fuentes[dueño])     # #476
        matchea = bool(patron.search(fuente))
        if mod in declarados and declarados[mod] is None:
            continue                      # estado inválido: ya se reportó, no se reporta dos veces
        estado = declarados.get(mod)
        if usa and estado is None:
            out.append(f"{quien}/{mod}: LLAMA a `{ref}` y no está declarado como portador")
        elif usa and estado == "fuera-de-alcance":
            out.append(f"{quien}/{mod}: declarado `fuera-de-alcance` y sin embargo llama a `{ref}`")
        elif not usa and estado == "usa":
            out.append(f"{quien}/{mod}: declarado `usa` y NO llama a `{ref}` — un comentario que "
                       f"dice «delega en X» no delega (#347)")
        elif matchea and estado is None:
            out.append(f"{quien}/{mod}: matchea el patrón `{entrada['patron']}` de esta regla y no "
                       f"está declarado: ¿es el gemelo que quedó igual? Declaralo `usa` (y hacelo "
                       f"llamar) o `fuera-de-alcance` con su motivo")
    return out


def check(root: Path = ROOT, path: Path = DECLARACION) -> tuple:
    """`(entradas, hallazgos)` — the whole declaration checked against the code.

    Both directions, which is what makes this a gate and not a list: a module that CALLS the
    function without being declared, a declared `usa` that does NOT call it (the comment that says
    it delegates and does not — #347), and a module the `patron` matches that nobody said anything
    about.

    @inv INV-154"""
    entradas = load(path)
    fuentes = source_modules(root)
    hallazgos: list = []
    for e in entradas:
        hallazgos += entry_errors(e if isinstance(e, dict) else {}, fuentes)
    return entradas, hallazgos


def signed_out_of_scope(ref: str, path: Path = DECLARACION) -> dict:
    """`{modulo: motivo}` — the consumers already signed `fuera-de-alcance` for `ref`.

    #482: the block that gets pasted into every issue showed them under the same heading as the
    consumer nobody looked at, so the reader could not tell which ones were debt. An unreadable
    declaration yields `{}`: `--check` is the gate for that, this is a report."""
    try:
        entradas = load(path)
    except DeclaracionIlegible:
        return {}
    out: dict = {}
    for e in entradas:
        if not isinstance(e, dict) or str(e.get("funcion")) != ref:
            continue
        for c in e.get("consumidores") or []:
            if isinstance(c, dict) and c.get("estado") == "fuera-de-alcance":
                out[str(c.get("modulo"))] = str(c.get("motivo") or "").strip()
    return out


def propose(ref: str, patron: str | None, root: Path = ROOT, path: Path = DECLARACION) -> tuple:
    """`(callers, signed, undeclared)` — the enumeration the entry has to declare.

    It exists so the list is NOT written from memory, the failure mode this repo chases everywhere:
    `callers` comes from the AST and the other two from the pattern it is given. `signed` is
    `{modulo: motivo}` for the matches already declared `fuera-de-alcance` (#482); `undeclared`
    is the only list that asks for action."""
    modulo, simbolo = ref.rsplit(".", 1)
    fuentes = source_modules(root)
    dueño = next((r for r in fuentes if Path(r).stem == modulo), None)
    rx = re.compile(patron) if patron else None
    firmados = signed_out_of_scope(ref, path)
    llaman, sin_declarar, firmados_matchean = [], [], {}
    for mod, fuente in fuentes.items():
        if mod == dueño:
            continue
        if carries(fuente, modulo, simbolo, fuentes[dueño] if dueño else ""):   # #476
            llaman.append(mod)
        elif rx and rx.search(fuente):
            if mod in firmados:
                firmados_matchean[mod] = firmados[mod]
            else:
                sin_declarar.append(mod)
    return llaman, firmados_matchean, sin_declarar


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="gatea la declaración contra el código")
    ap.add_argument("--propose", metavar="MODULO.SIMBOLO", default=None,
                    help="enumera quién llama y quién matchea el patrón, para escribir la entrada")
    ap.add_argument("--patron", default=None, help="con --propose: cómo se reconoce a un portador")
    args = ap.parse_args(argv)

    if args.propose:
        llaman, firmados, sin_declarar = propose(args.propose, args.patron)
        # #476 — el reporte dice por QUÉ VÍA se lleva la regla, porque son dos y piden acciones
        # distintas: a una función hay que hacerla llamar, a una constante hay que leerla. Decir
        # «LLAMAN» sobre la lectura de una tabla sería el mapa que atribuye mal (regla nº 4).
        fuentes = source_modules(ROOT)
        _mod, _sim = str(args.propose).rsplit(".", 1)
        _dueño = next((r for r in fuentes if Path(r).stem == _mod), None)
        verbo = "LLAMAN a" if (_dueño and es_callable(fuentes[_dueño], _sim)) else "LEEN"
        print(f"{verbo} `{args.propose}` ({len(llaman)}) — van declarados `usa`:")
        for m in llaman:
            print(f"  {m}")
        if args.patron:
            # #482 — tres bloques: el firmado ya tiene motivo y no es deuda; el tercero es el
            # único que pide acción, y vacío lo DICE en vez de desaparecer (D-43).
            print(f"\nMATCHEAN `{args.patron}` y están firmados `fuera-de-alcance` "
                  f"({len(firmados)}, con motivo):")
            for m, motivo in firmados.items():
                print(f"  {m} — {motivo}")
            print(f"\nMATCHEAN `{args.patron}` y NADIE declaró ({len(sin_declarar)} sin declarar) "
                  f"— cada uno se declara `usa` (y se hace llevar) o `fuera-de-alcance` CON motivo:")
            for m in sin_declarar:
                print(f"  {m}")
        else:
            print("\n⚠ sin `--patron` no se enumeran los sospechosos: sólo se ve quién YA llama, "
                  "que es la mitad que nunca fue el problema (D-43)")
        return 0

    try:
        entradas, hallazgos = check()
    except DeclaracionIlegible as exc:
        print(f"⛔ no evaluado: {exc}", file=sys.stderr)
        return 2
    print(f"portadores: {len(entradas)} regla(s) declarada(s) sobre "
          f"{len(source_modules())} módulo(s) de {'/'.join(ARBOLES)}")
    for h in hallazgos:
        print(f"  ⛔ {h}")
    if hallazgos:
        print(f"⛔ {len(hallazgos)} hallazgo(s): una regla con un portador sin declarar es la "
              f"familia «fix a la instancia, no a la clase» — la más grande del repo.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
