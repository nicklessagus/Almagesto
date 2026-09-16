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


# ── #397b · «qué es una nota» lo decide UNA función, no un glob ──────────────────────────────────

def test_ningun_script_enumera_las_notas_con_un_glob_crudo():
    """INV-148 — un hermano `<nota>.verif.md` **no es una nota**: `cfg.note_paths` lo saca de todo
    enumerador. Un `PAPERS.glob("*.md")` a mano se los lleva puestos.

    Medido en `Almagesto-Tesis` con v1.212.0: `fetch_bibtex` reportó **«192 nota(s) miradas»** sobre
    189 y listó los tres hermanos entre los papers **sin BibTeX** — no los escribe (no tienen
    frontmatter), pero el denominador y la lista mienten, que es lo que INV-40 existe para impedir.
    El mismo glob estaba en `restamp_lens`, donde el síntoma es mudo: el hermano no tiene `vistas`,
    así que se saltea en silencio y nadie lo ve.

    Es un assert y no un ritual porque es decidible: la regla ya tiene una sola casa desde #344, y lo
    único que hace falta es que nadie la reimplemente. Vale para los tres directorios de notas."""
    ofensores = []
    for f in sorted((RAIZ / "scripts").glob("*.py")) + sorted((RAIZ / "tools").glob("*.py")):
        texto = f.read_text(encoding="utf-8")
        for i, linea in enumerate(texto.split("\n"), 1):
            if linea.lstrip().startswith("#"):
                continue
            for dirname in ("PAPERS", "STARS", "CONCEPTS", "QUERIES"):
                if f'{dirname}.glob("*.md")' in linea or f"{dirname}.glob('*.md')" in linea:
                    ofensores.append(f"{f.name}:{i}: {linea.strip()[:90]}")
    assert not ofensores, (
        "enumerar notas con un glob crudo se lleva los hermanos `.verif.md` (INV-148) — usá "
        "`cfg.note_paths(<dir>)`, que es la única definición de «qué es una nota»:\n  "
        + "\n  ".join(ofensores))


# ── #478 · la tabla derivada de un vocabulario cerrado declara su cobertura ────────────────────

#: Las tablas que YA declaran su cobertura, con el test que la cruza. El barrido de abajo exige que
#: toda tabla derivada esté acá: una nueva es un rojo, no un silencio.
#:
#: ⛔ Por qué #478 NO tiene entrada en `tools/portadores.yaml`, y no es un olvido: su «¿quién MÁS
#: lleva esta regla?» (#409) lo contesta **este barrido**, que recorre `scripts/` y `tools/`
#: enteros y es exhaustivo por construcción. Una declaración firmada a mano sería estrictamente
#: peor —hay que acordarse de firmarla, y un portador nuevo que nadie firme queda mudo—, que es el
#: modo de falla que `portadores` existe para cubrir cuando la regla vive en un símbolo. Acá la
#: regla no vive en un símbolo de `scripts/`: vive en la relación entre cada tabla y su vocabulario,
#: y eso se enumera, no se declara.
TABLAS_CON_COBERTURA = {
    ("harvest_views.py", "_DOC_DE_FUENTE"):
        "tests/test_harvest_views.py::test_la_tabla_de_documento_CUBRE_el_vocabulario_o_declara_lo_que_deja_afuera",
    ("make_notes.py", "_FULLTEXT_QUALITY"):
        "tests/test_make_notes.py::test_la_tabla_de_calidad_de_fulltext_CUBRE_su_vocabulario",
}


def _vocabularios_cerrados() -> dict:
    """`{nombre: set(valores)}` — los vocabularios cerrados de `lib_config`, leídos de la constante.

    ⛔ No se copian acá: se importan. Una lista repetida en el test es la misma divergencia que la
    regla de #477 persigue, un nivel más arriba."""
    import sys
    sys.path.insert(0, str(RAIZ / "scripts"))
    import lib_config as cfg
    return {n: set(getattr(cfg, n)) for n in ("PDF_SOURCE_OK", "FULLTEXT_SOURCE_OK",
                                              "PENDING_OK", "UNIDAD_CITA_OK")}


def _tablas_derivadas(fuente: str, vocs: dict) -> list:
    """`[(nombre, vocabulario, claves)]` — los dicts de módulo cuyas claves son un subconjunto
    PROPIO de un vocabulario cerrado (#478).

    El subconjunto **propio** con 2+ claves es la forma que importa: mapea desde el vocabulario y
    **no lo cubre**, así que el valor que falta cae por el `.get()`. Un dict que lo cubre entero
    también entra —su riesgo es el vocabulario que crece—, y por eso la condición es «⊆», no «⊂»."""
    try:
        arbol = ast.parse(fuente)
    except SyntaxError:
        return []
    out = []
    for n in arbol.body:
        if not isinstance(n, ast.Assign) or not isinstance(n.value, ast.Dict):
            continue
        nombre = next((x.id for x in n.targets if isinstance(x, ast.Name)), None)
        claves = {k.value for k in n.value.keys
                  if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if not nombre or len(claves) < 2:
            continue
        for voc, vals in vocs.items():
            if claves <= vals:
                out.append((nombre, voc, claves))
    return out


def test_toda_tabla_derivada_de_un_vocabulario_cerrado_declara_su_cobertura():
    """#478 — una tabla cuyas claves son valores de un vocabulario cerrado tiene que CUBRIRLO o
    nombrar lo que deja afuera; si no, el valor nuevo cae por su `.get()` **en silencio**.

    Medido al abrir el issue: dos tablas, y una (`_DOC_DE_FUENTE`) ya dejaba `web` afuera **a
    propósito** —un snapshot no tiene testigo, D-43— con esa decisión viviendo sólo en un
    comentario. El defecto no era el hueco: era que nada lo cruzaba, así que un quinto valor del
    vocabulario habría sido indistinguible de un olvido.

    ⛔ Este barrido es la mitad que arregla la CLASE y no el caso (#409): las dos tablas de hoy ya
    tienen su test de partición, y lo que este assert cierra es la **tercera**, la que alguien
    escriba mañana. Una tabla nueva es un rojo que manda a escribirle su cruce."""
    sin_declarar = []
    vocs = _vocabularios_cerrados()
    for f in FUENTES:
        for nombre, voc, _claves in _tablas_derivadas(f.read_text(encoding="utf-8"), vocs):
            if (f.name, nombre) not in TABLAS_CON_COBERTURA:
                sin_declarar.append(f"{f.name}::{nombre} (claves de `{voc}`)")
    assert not sin_declarar, (
        "tabla(s) derivadas de un vocabulario cerrado sin test que cruce su cobertura — el valor "
        "nuevo del vocabulario caería por su `.get()` en silencio (#478). Escribile el assert de "
        "partición y agregala a `TABLAS_CON_COBERTURA`:\n  " + "\n  ".join(sin_declarar))


def test_el_barrido_de_cobertura_SIGUE_VIENDO_las_tablas_que_ya_estan(tmp_path):
    """#478 — la red del barrido de arriba: si `_tablas_derivadas` dejara de reconocerlas, el test
    pasaría con **cero** tablas miradas, que es el falso limpio de D-43 dentro del gate que existe
    para no producir uno. Así que se exige que las conocidas sigan apareciendo, y que una tabla
    nueva se detecte."""
    vocs = _vocabularios_cerrados()
    vistas = {(f.name, n) for f in FUENTES
              for n, _v, _c in _tablas_derivadas(f.read_text(encoding="utf-8"), vocs)}
    assert set(TABLAS_CON_COBERTURA) <= vistas, (
        "el barrido dejó de ver una tabla declarada: ¿se renombró, o dejó de derivar del vocabulario?")
    nueva = "_NUEVA = {'eprint': 1, 'ads': 2}\n"
    assert [n for n, _v, _c in _tablas_derivadas(nueva, vocs)] == ["_NUEVA"], "y ve una nueva"
