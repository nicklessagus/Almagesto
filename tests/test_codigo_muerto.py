"""Expresiones que no deciden nada — la clase de defecto que ningún otro gate ve (#319).

⛔ POR QUÉ EXISTE, medido. `_solo_separadores` llevaba `s[:12] if len(s) <= 12 else s`, cuyas dos
ramas dan **el mismo string**: el tope de 12 que la expresión insinuaba no estaba aplicado. No
rompía ningún test —no cambiaba el comportamiento—, la mutación dirigida mataba la función igual, y
la suite entera pasaba en verde. Lo encontró una persona **leyendo el commit**.

Es la forma más barata de mentira en el código: una regla escrita a medias, que el próximo lector
toma por una decisión deliberada. Y es **decidible**, así que es un assert y no un ritual (la misma
doctrina con la que `tests/test_docs_ejecutables.py` cierra las afirmaciones de la doc).

⚠ Alcance declarado, en dos formas: el condicional cuyas ramas son **sintácticamente idénticas**, y
el patrón `X[:N] if len(X) <= N else X` —el de #319, donde las ramas se escriben distinto y **valen
lo mismo**—. No caza la condición siempre verdadera por otro motivo (eso es `mutar.py --guardas`,
que muta cada `if` y cada cláusula de un `and`/`or`) ni el código inalcanzable.
"""
from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = sorted(list((RAIZ / "scripts").glob("*.py")) + list((RAIZ / "tools").glob("*.py")))


def _corte_bajo_su_propia_guarda(n: ast.IfExp) -> bool:
    """`E[:N] if len(E) <= N else E` — el patrón EXACTO de #319, y el que más engaña.

    Las dos ramas no son idénticas escritas, pero **valen lo mismo**: si `len(E) <= N`, entonces
    `E[:N]` es `E`. O sea que el tope `N` que la expresión insinúa no está aplicado en ninguna rama.
    Se reconoce por su forma, que es la única manera de cazarlo sin ejecutar nada."""
    t = n.test
    if not (isinstance(t, ast.Compare) and len(t.ops) == 1
            and isinstance(t.ops[0], (ast.LtE, ast.Lt))
            and isinstance(t.left, ast.Call) and isinstance(t.left.func, ast.Name)
            and t.left.func.id == "len" and len(t.left.args) == 1):
        return False
    sujeto, tope = ast.dump(t.left.args[0]), t.comparators[0]
    if not (isinstance(n.body, ast.Subscript) and isinstance(n.body.slice, ast.Slice)
            and n.body.slice.lower is None and n.body.slice.upper is not None
            and n.body.slice.step is None):
        return False
    # el sujeto del `len(...)`, el del corte y el de la otra rama tienen que ser el MISMO
    if not (ast.dump(n.body.value) == sujeto == ast.dump(n.orelse)):
        return False
    # y el tope del corte, el mismo que el de la comparación (con `<`, el corte sería N-1: no aplica)
    return isinstance(n.test.ops[0], ast.LtE) and ast.dump(n.body.slice.upper) == ast.dump(tope)


def _ramas_identicas(arbol: ast.AST, archivo: str) -> list:
    """`[archivo:línea: forma]` de los condicionales que no deciden nada."""
    fuera = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.IfExp):
            if ast.dump(n.body) == ast.dump(n.orelse):
                fuera.append(f"{archivo}:{n.lineno}: ternario cuyas dos ramas son idénticas")
            elif _corte_bajo_su_propia_guarda(n):
                fuera.append(f"{archivo}:{n.lineno}: `X[:N] if len(X) <= N else X` — las dos ramas "
                             f"valen lo mismo, así que el tope N NO está aplicado (#319)")
        if isinstance(n, ast.If) and n.orelse and \
                [ast.dump(x) for x in n.body] == [ast.dump(x) for x in n.orelse]:
            fuera.append(f"{archivo}:{n.lineno}: `if`/`else` con el mismo cuerpo")
    return fuera


def test_ningun_condicional_da_lo_mismo_en_las_dos_ramas():
    """El caso de #319, mecanizado: si las dos ramas son la misma expresión, el condicional no
    decide nada — o falta la mitad de la regla, o sobra la escritura entera. Las dos salidas son
    ediciones distintas y hay que elegir una; lo que no puede quedar es la insinuación."""
    hallazgos = []
    for f in FUENTES:
        hallazgos += _ramas_identicas(ast.parse(f.read_text(encoding="utf-8")), f.name)
    assert hallazgos == [], (
        "condicionales que no deciden nada (una regla a medio escribir se lee como una decisión "
        "deliberada):\n  " + "\n  ".join(hallazgos))


def test_el_detector_ve_el_caso_de_319():
    """La regla de método nº 3 aplicada al propio gate: un test verde no cuenta hasta que lo viste
    morir por la línea que prueba. Acá se le da el código exacto que motivó #319."""
    codigo = ("def _solo_separadores(gap):\n"
              "    return bool(RX.match(gap.strip()[:12] if len(gap.strip()) <= 12 else gap.strip()))\n")
    assert _ramas_identicas(ast.parse(codigo), "x.py"), "el gate no ve su propio caso"
    for sano in ("def f(s):\n    return s[:12] if len(s) <= 12 else s[:8]\n",
                 "def f(s):\n    return s[:12] if len(s) > 12 else s\n",       # ESTE sí trunca
                 "def f(s, n):\n    return s[:n] if len(t) <= n else s\n"):    # otro sujeto
        assert _ramas_identicas(ast.parse(sano), "x.py") == [], sano
