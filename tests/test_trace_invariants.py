"""Tests del recolector de trazabilidad requisito ↔ código (`scripts/trace_invariants.py`).

Qué garantiza este archivo, en el orden en que importa:

1. El **registro canónico** de invariantes sale de `docs/contrato.md` §3 — nunca de una lista
   hardcodeada en el recolector (una segunda lista se desincroniza en silencio, que es el modo de
   falla que la matriz manual tenía y por el que se eligió el recolector).
2. Una **marca** es explícita (`@inv INV-nn`). Mencionar `INV-nn` en prosa NO es una marca: el
   caso adversario está sembrado, porque `docs/` y los docstrings de este repo nombran invariantes
   todo el tiempo y una marca por substring recolectaría ruido y afirmaría cobertura falsa.
3. Una marca que apunta a un invariante **inexistente** bloquea. Es el mismo modo de falla que
   `thesis_links` sin página destino: la marca queda muda y nadie se entera.
4. Un contrato **ilegible** sale con código propio (2, *no evaluado*) y NO reporta "0 sin marcar":
   el cero inventado que D-43 prohíbe.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import trace_invariants as ti     # noqa: E402


CONTRATO_MINI = """\
# Contrato

## 3. Los invariantes

### A. Área de ejemplo

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-01** | Un enunciado cualquiera. | P0 | garantizado sin medir | falta el test |
| **INV-02** | Otro enunciado. | P1 | **garantizado y medido** | sembrado en la suite |

### B. Otra área

| ID | Enunciado falsable | Prio | Estado | Cómo se verifica |
|---|---|---|---|---|
| **INV-90** | Toda escritura en `vault/` es atómica. | P1 | **HUECO** (D-53) | inyección de fallo |

## 4. Otra sección

Acá se menciona INV-01 en prosa y no debería contar como nada.
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Repo de juguete: contrato + `scripts/` + `tests/` + ratchet."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs" / "contrato.md").write_text(CONTRATO_MINI, encoding="utf-8")
    (tmp_path / "docs" / "trazabilidad-ratchet.yaml").write_text(
        yaml.safe_dump({"medido_en": "2026-08-24", "techos": {"sin_marca": 3, "sin_test": 3}}),
        encoding="utf-8")
    return tmp_path


def _run(repo: Path, *argv: str) -> tuple[int, str]:
    """Corre `main()` sobre el repo de juguete y devuelve (rc, texto del artefacto)."""
    rc = ti.main([*argv, "--root", str(repo)])
    art = repo / "docs" / "trazabilidad.md"
    return rc, art.read_text(encoding="utf-8") if art.exists() else ""


# ── 1. registro canónico ─────────────────────────────────────────────────────────────────────────

def test_registro_sale_del_contrato(repo: Path):
    """Los invariantes se leen de las tablas de §3 con su prio y su estado; la mención en prosa
    de §4 no agrega una entrada fantasma."""
    reg = ti.parse_contrato((repo / "docs" / "contrato.md").read_text(encoding="utf-8"))
    assert list(reg) == ["INV-01", "INV-02", "INV-90"]
    assert reg["INV-01"]["prio"] == "P0"
    assert reg["INV-02"]["estado"] == "garantizado y medido"
    assert reg["INV-90"]["area"].startswith("B.")


def test_registro_real_cubre_los_136():
    """Contra el contrato REAL del repo: el parser tiene que leer los 136 invariantes vivos. Es la
    prueba de que la forma de la tabla que el parser asume es la que el documento tiene.

    El número es un **canario deliberado**: agregar una fila al contrato tiene que romper acá, para
    que nadie sume un invariante sin pasar por el ratchet de trazabilidad."""
    reg = ti.parse_contrato(ti.CONTRATO.read_text(encoding="utf-8"))
    assert len(reg) == 136
    assert "INV-01" in reg and "INV-126" in reg


# ── 2. la marca ──────────────────────────────────────────────────────────────────────────────────

def test_marca_en_scripts_se_recolecta_con_su_simbolo(repo: Path):
    (repo / "scripts" / "lib_x.py").write_text(
        'def write_text_atomic(path, text):\n'
        '    """Escritura atómica. @inv INV-90"""\n'
        '    pass\n', encoding="utf-8")
    marcas = ti.collect_marks(repo)
    assert [(m.inv, m.kind, m.symbol) for m in marcas] == [("INV-90", "impl", "write_text_atomic")]
    assert marcas[0].line == 2


def test_marca_en_tests_se_recolecta_como_test(repo: Path):
    (repo / "tests" / "test_x.py").write_text(
        "def test_fallo_en_replace_no_corrompe():  # @inv INV-90\n    pass\n", encoding="utf-8")
    marcas = ti.collect_marks(repo)
    assert [(m.inv, m.kind) for m in marcas] == [("INV-90", "test")]


def test_una_marca_puede_nombrar_varios_invariantes(repo: Path):
    (repo / "scripts" / "lib_x.py").write_text(
        "def f():  # @inv INV-01, INV-02\n    pass\n", encoding="utf-8")
    assert sorted(m.inv for m in ti.collect_marks(repo)) == ["INV-01", "INV-02"]


def test_marca_en_string_literal_no_cuenta(repo: Path):
    """Adversario medido en la primera corrida real: este mismo archivo de tests escribe código de
    juguete con `@inv` DENTRO de string literals, y un escaneo por línea los recolectaba como si
    fueran marcas del repo — 7 "pruebas" de INV-01 que no lo tocan. Una marca sólo cuenta en un
    **comentario** o en un **docstring**: son los dos lugares donde alguien está declarando algo
    sobre el código de al lado, no citando texto."""
    (repo / "scripts" / "lib_x.py").write_text(
        'PLANTILLA = """\n'
        'def f():  # @inv INV-90\n'
        '"""\n'
        'OTRA = "# @inv INV-01"\n', encoding="utf-8")
    assert ti.collect_marks(repo) == []


def test_el_recolector_no_se_marca_a_si_mismo():
    """Contra el repo REAL: los ejemplos de sintaxis que el propio `trace_invariants.py` y su test
    muestran en la doc no pueden contar como cobertura (se auto-adjudicaba INV-87 e INV-90)."""
    # Se arma un árbol con SÓLO los dos archivos, en vez de barrer el repo entero y filtrar: la
    # pregunta es sobre esos dos, y el barrido completo costaba **2,6 s del presupuesto de tier 0**
    # (el test más caro de la suite, por lejos) para tirar el 95% de lo que leía.
    import shutil, tempfile
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        (raiz / "scripts").mkdir()
        (raiz / "tests").mkdir()
        shutil.copy(ti.ROOT / "scripts" / "trace_invariants.py", raiz / "scripts")
        shutil.copy(ti.ROOT / "tests" / "test_trace_invariants.py", raiz / "tests")
        assert ti.collect_marks(raiz) == []


def test_mencion_en_prosa_no_es_marca(repo: Path):
    """Adversario directo: sin `@inv`, nombrar el invariante es documentación, no cobertura."""
    (repo / "scripts" / "lib_x.py").write_text(
        'def f():\n'
        '    """Esto se relaciona con INV-90 y con INV-01 (ver contrato)."""\n'
        '    pass\n', encoding="utf-8")
    assert ti.collect_marks(repo) == []


# ── 3. marca huérfana ────────────────────────────────────────────────────────────────────────────

def test_marca_huerfana_bloquea(repo: Path):
    """Una marca a INV-99, que el contrato no declara, queda muda: exit 1 y el artefacto la nombra
    con archivo y línea (mismo modo de falla que `thesis_links` sin página destino).

    (La sintaxis de la marca se escribe con placeholders en las docstrings a propósito — un id real
    acá haría que este archivo se auto-adjudicara cobertura. Ver `trace_invariants.lineas_declarativas`.)"""
    (repo / "scripts" / "lib_x.py").write_text("# @inv INV-99\n", encoding="utf-8")
    rc, txt = _run(repo)
    assert rc == 1
    assert "INV-99" in txt and "lib_x.py" in txt


# ── 4. el ratchet ────────────────────────────────────────────────────────────────────────────────

def test_sin_marca_por_encima_del_techo_bloquea(repo: Path):
    """Techo 0 con 3 invariantes sin marca → exit 1. El techo sólo puede bajar."""
    (repo / "docs" / "trazabilidad-ratchet.yaml").write_text(
        yaml.safe_dump({"techos": {"sin_marca": 0, "sin_test": 0}}), encoding="utf-8")
    rc, _ = _run(repo)
    assert rc == 1


def test_sin_marca_por_debajo_del_techo_pasa_y_pide_bajarlo(repo: Path):
    (repo / "scripts" / "lib_x.py").write_text("# @inv INV-01\n", encoding="utf-8")
    (repo / "tests" / "test_x.py").write_text("# @inv INV-01\n", encoding="utf-8")
    rc, txt = _run(repo)
    assert rc == 0
    assert "bajá el techo" in txt


def test_invariante_con_impl_y_test_no_cuenta_como_descubierto(repo: Path):
    (repo / "scripts" / "lib_x.py").write_text("# @inv INV-01\n", encoding="utf-8")
    (repo / "tests" / "test_x.py").write_text("# @inv INV-01\n", encoding="utf-8")
    rc, txt = _run(repo)
    assert rc == 0
    fila = [l for l in txt.splitlines() if l.startswith("| **INV-01**")][0]
    assert "lib_x.py" in fila and "test_x.py" in fila


# ── 5. "no evaluado" (D-43): nunca un cero inventado ─────────────────────────────────────────────

def test_contrato_ausente_es_no_evaluado(repo: Path):
    (repo / "docs" / "contrato.md").unlink()
    rc = ti.main(["--root", str(repo)])
    assert rc == 2


def test_contrato_sin_tablas_es_no_evaluado_y_no_reporta_cero(repo: Path, capsys):
    """El contrato existe pero §3 no trae ninguna tabla parseable: rc 2 y el reporte NO afirma
    "0 invariantes sin marca" — no se puede afirmar nada sobre un registro que no se leyó."""
    (repo / "docs" / "contrato.md").write_text("# Contrato\n\nsin tablas\n", encoding="utf-8")
    rc = ti.main(["--root", str(repo)])
    out = capsys.readouterr().out
    assert rc == 2
    assert "no evaluado" in out.lower()
    assert "sin marca: 0" not in out.lower()


# ── 6. el artefacto ──────────────────────────────────────────────────────────────────────────────

def test_artefacto_es_idempotente(repo: Path):
    (repo / "scripts" / "lib_x.py").write_text("# @inv INV-01\n", encoding="utf-8")
    _, primero = _run(repo)
    _, segundo = _run(repo)
    assert primero == segundo


def test_check_detecta_artefacto_desactualizado(repo: Path):
    """`--check` no escribe: falla si lo commiteado no es lo que el código de hoy genera (un mapa
    viejo commiteado se lee como vigente — el mismo modo de falla que la matriz manual)."""
    _run(repo)
    (repo / "scripts" / "lib_x.py").write_text("# @inv INV-01\n", encoding="utf-8")
    antes = (repo / "docs" / "trazabilidad.md").read_text(encoding="utf-8")
    rc = ti.main(["--check", "--root", str(repo)])
    assert rc == 1
    assert (repo / "docs" / "trazabilidad.md").read_text(encoding="utf-8") == antes


def test_marca_a_nivel_de_modulo_no_se_atribuye_a_la_funcion_anterior(tmp_path):
    """El artefacto existe para que el mapa NO mienta, así que atribuir mal es su peor defecto.

    `_simbolo_de` caminaba hacia arriba hasta el `def` más cercano **sin chequear si la línea sigue
    adentro de esa función**: una marca sobre una constante de módulo se le colgaba a la función que
    quedó arriba. Medido en el artefacto real: `INV-76` (autoridad por campo del ground-truth, que
    marca `AUTORIDAD_CAMPO`) aparecía implementado por `_extra_core_error`, e `INV-77`
    (`DISPUTE_SOURCES`) por `note_files`."""
    src = (tmp_path / "m.py")
    src.write_text(
        "def anterior():\n"
        "    return 1\n"
        "\n"
        "# @inv INV-01\n"
        "CONSTANTE = 3\n"
        "\n"
        "def posterior():\n"
        "    # @inv INV-02\n"
        "    return 2\n", encoding="utf-8")
    lineas = src.read_text(encoding="utf-8").split("\n")
    assert ti._simbolo_de(lineas, 4) != "anterior", (
        "la marca está FUERA de `anterior`: no puede atribuírsele")
    assert ti._simbolo_de(lineas, 8) == "posterior", "la marca de adentro sí se atribuye"


# ── el símbolo se decide por AST cuando el archivo parsea ────────────────────

MARCA = "@" + "inv " + "INV-01"   # ver el docstring del módulo: un id real en un
                                 # ejemplo de sintaxis hace que el recolector se
                                 # auto-marque. Se arma en runtime a propósito.


def _sim(tmp_path, codigo, aguja=None):
    """`_simbolo_de` sobre la línea que contiene `aguja`."""
    codigo = codigo.replace("<MARCA>", MARCA)
    lineas = codigo.split("\n")
    n = next(i for i, l in enumerate(lineas, 1) if MARCA in l)
    return ti._simbolo_de(lineas, n)


def test_marca_dentro_de_un_docstring_con_codigo_de_ejemplo(tmp_path):
    """El peor caso: un docstring que muestra código de ejemplo. Decidiendo por indentación, la
    marca se atribuía a la función **de juguete** que vive dentro del texto — una atribución
    inventada, que es el defecto que este artefacto existe para no tener."""
    codigo = ('def real():\n'
              '    """Ejemplo::\n'
              '\n'
              '        def falsa():\n'
              '            # <MARCA>\n'
              '            pass\n'
              '    """\n'
              '    return 1\n')
    assert _sim(tmp_path, codigo) == "real"


def test_marca_en_bloques_anidados_conserva_la_funcion(tmp_path):
    """Cuatro formas normales de escribir código donde la indentación no alcanza: la marca queda
    más adentro que el `def`, y antes degradaba a "" — que el artefacto muestra igual que «a nivel
    de módulo», así que el lector no puede distinguir «es de módulo» de «se perdió»."""
    assert _sim(tmp_path, 'def f():\n    if True:\n        # <MARCA>\n        return 1\n') == "f"
    assert _sim(tmp_path, 'def g():\n    d = {\n        # <MARCA>\n        "a": 1,\n    }\n    return d\n') == "g"
    assert _sim(tmp_path,
                'def h(\n    x: int,\n) -> dict:\n    # <MARCA>\n    return {}\n') == "h"


def test_la_atribucion_no_depende_de_la_indentacion(tmp_path):
    """La fragilidad medida por la auditoría: 23 de 77 marcas conservaban su símbolo **sólo**
    porque estaban mal indentadas. Re-indentarlas —un `black`, un reindent, o alguien acomodándolas
    a mano— rompía el 30% del mapa en silencio: sin marca huérfana, sin cambio de conteo y sin
    `--check` en rojo, porque el artefacto se regenera con el símbolo perdido."""
    base = 'def f():\n    if True:\n{marca}        return 1\n'
    mal = base.format(marca="    # <MARCA>\n")      # sangría 4 delante de un bloque a 8
    bien = base.format(marca="        # <MARCA>\n")  # la natural
    assert _sim(tmp_path, mal) == _sim(tmp_path, bien) == "f"


def test_archivo_que_no_parsea_cae_al_heuristico(tmp_path):
    """El recolector tiene que seguir corriendo sobre un archivo roto — que es justo cuando uno
    quiere saber qué invariante toca. Sin AST posible, vuelve a decidir por indentación."""
    roto = 'def f():\n    # <MARCA>\n    return (\n'      # paréntesis sin cerrar
    import ast as _ast
    with pytest.raises(SyntaxError):
        _ast.parse(roto)
    assert _sim(tmp_path, roto) == "f"


def test_inv_de_tres_digitos_no_se_recolecta_como_de_dos():
    """La frontera `(?!\\d)` existe para que un `INV-100` no se recolecte **como INV-10**: la marca
    quedaría atribuida al invariante equivocado y el mapa afirmaría que INV-10 está cubierto por un
    test que prueba otra cosa — atribución falsa en el artefacto cuyo trabajo es no atribuir mal.

    Lo que este test NO debe pedir es que `INV-100` se ignore: eso era el tope de dos dígitos, que
    hacía la fila 100 invisible. La cobertura de tres dígitos vive en el test de abajo."""
    marca = "@" + "inv "          # partido: escribir la marca literal la haría recolectable
    assert ti.INV_RE.findall("INV-1000") == [], "cuatro dígitos siguen fuera del vocabulario"
    assert ti.INV_RE.findall("INV-10") == ["INV-10"]
    assert ti.MARCA_RE.findall("# " + marca + "INV-10, INV-42") == ["INV-10, INV-42"]
    assert ti.FILA_RE.match("| **INV-1000** | x |") is None
    assert ti.FILA_RE.match("| **INV-10** | x |").group(1) == "INV-10"


# ── 5. el techo sólo baja (#96) ───────────────────────────────────────────────────────────────

def _ratchet(repo: Path, sin_marca: int, extra: str = "") -> None:
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "trazabilidad-ratchet.yaml").write_text(
        f"{extra}techos:\n  sin_marca: {sin_marca}\n  sin_test: {sin_marca}\n", encoding="utf-8")


def _git_repo_con_techo(repo: Path, sin_marca: int) -> None:
    """Repo git real con el ratchet ya commiteado: `subidas_de_techo` compara contra `HEAD`."""
    import subprocess
    _ratchet(repo, sin_marca)
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"]):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)


def test_subir_el_techo_sin_justificar_es_hallazgo(repo: Path):
    """El techo del ratchet **sólo puede bajar**. Hasta 1.37.0 la regla vivía sólo en el encabezado
    del YAML y la sostenía la revisión humana: `load_techos` devolvía lo que el archivo dijera, así
    que nada impedía subirlo en el mismo commit que rompía la cobertura (#96)."""
    _git_repo_con_techo(repo, 2)
    _ratchet(repo, 3)                                    # sube sin decir por qué
    assert ti.subidas_de_techo(repo) == [("sin_marca", 2, 3), ("sin_test", 2, 3)]


def test_la_escotilla_exige_la_transicion_concreta_no_un_motivo_generico(repo: Path):
    """La justificación se ata a `<campo> <antes>→<ahora>`, no es un comentario suelto.

    Una escotilla genérica quedaría en el archivo para siempre y desactivaría el chequeo de ahí en
    más: la subida SIGUIENTE pasaría gratis amparada por el motivo de la anterior. Atada a la
    transición, la justificación **caduca sola**."""
    _git_repo_con_techo(repo, 2)
    _ratchet(repo, 3, extra="# ratchet-sube: porque sí\n")
    assert ti.subidas_de_techo(repo), "un motivo genérico no puede justificar cualquier subida"

    _ratchet(repo, 3, extra="# ratchet-sube: sin_marca 2→3 — INV-95 no es marcable\n")
    assert [c for c, *_ in ti.subidas_de_techo(repo)] == ["sin_test"], \
        "la justificación vale para el campo y la transición que nombra, y sólo para esa"


def test_bajar_el_techo_nunca_es_hallazgo(repo: Path):
    _git_repo_con_techo(repo, 5)
    _ratchet(repo, 1)
    assert ti.subidas_de_techo(repo) == []


def test_sin_git_la_subida_no_se_evalua_y_no_se_inventa_un_cero(repo: Path):
    """D-43: un chequeo que no pudo correr se declara, no devuelve «no subió»."""
    _ratchet(repo, 9)
    assert ti.techos_previos(repo) is None
    assert ti.subidas_de_techo(repo) == []               # el llamador imprime «no evaluada»


def test_el_registro_admite_invariantes_de_tres_digitos():
    """El tope de dos dígitos era invisible: con 99 filas nada avisa, y la fila 100 **no se
    recolecta** — ni en el contrato ni en las marcas `@inv` del código. La frontera `(?!\\d)` se
    puso para que `INV-100` no se leyera como `INV-10`; el efecto colateral fue que no se lee.
    Medido el 2026-08-25 al agregar INV-100: `grep` contaba 100 filas y el parser devolvía 99."""
    doc = "\n".join([
        "## 3. Invariantes",
        "### A. area de prueba",
        "| **INV-10** | Dos digitos. | P0 | garantizado y medido | `m.f` |",
        "| **INV-100** | Tres digitos. | P1 | garantizado y medido | `m.g` |",
    ])
    reg = ti.parse_contrato(doc)
    assert "INV-100" in reg, "el parser del contrato se queda en dos dígitos"
    assert reg["INV-10"]["prio"] == "P0", "y no debe degradar INV-100 a INV-10"
    assert reg["INV-100"]["prio"] == "P1"
    assert ti.MARCA_RE.search("#  @inv INV-100").group(1) == "INV-100"
    assert ti.INV_RE.findall("INV-100 y INV-07") == ["INV-100", "INV-07"]


@pytest.mark.poblada
def test_el_mapa_commiteado_esta_al_dia_en_el_repo_REAL():
    """Issue #138 — el gate que faltaba. `docs/trazabilidad.md` es un artefacto GENERADO, y en
    `69b49d5` el commiteado estaba desactualizado: dos marcas de INV-125 agregadas en `e8aa5b9`
    no figuraban, así que el mapa **sub-reportaba** su propia cobertura.

    Nadie lo detectaba: `--check` existía y no lo corría ni CI ni la suite, y
    `tests/test_docs_ejecutables.py` **exime** a este archivo de su chequeo de punteros con la
    premisa *"se re-derivan del AST y no pueden envejecer"* — premisa que sólo vale si alguien
    regenera. INV-95 enuncia *"el mapa dice la verdad sobre su propia cobertura"*: esto lo mide.

    Es el mismo argumento que `test_docs_ejecutables`: barato, corre en tier 0, y falla exactamente
    cuando alguien agrega o mueve una marca sin regenerar. Se arregla con
    `python scripts/trace_invariants.py`.

    ⚠ **Tier 1, no tier 0.** `collect_marks` parsea el AST de todo `scripts/` + `tests/` y cuesta
    ~4,9 s (in-process; por subprocess es lo mismo más el arranque del intérprete). Meterlo en tier 0
    llevaba la suite de 7 s a 11,8 s y **rompía el presupuesto declarado** (≤ 8 ms/test **y** ≤ 10 s,
    `tests/README.md`) — una promesa que el repo mide con su propio test. El gate de cada push vive
    en CI (`.github/workflows/ci.yml`), que corre el `--check` real; acá queda la red de tier 1.

    Compara in-process con las mismas piezas que usa `--check`, así que la paridad es por
    construcción y no por un doble."""
    esperado = ti.render(ti.load_registro(ti.ROOT), ti.collect_marks(ti.ROOT), ti.load_techos(ti.ROOT))
    vigente = (ti.ROOT / "docs" / "trazabilidad.md").read_text(encoding="utf-8")
    assert vigente == esperado, (
        "`docs/trazabilidad.md` está desactualizado respecto de las marcas del árbol — "
        "regeneralo con `python scripts/trace_invariants.py`.")
