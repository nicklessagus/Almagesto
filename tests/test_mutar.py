"""El gate de mutación (red #1) tiene que ver el código NUEVO.

`--diff` seleccionaba con `git diff --name-only HEAD`, que **no lista untracked**. O sea que un
archivo recién creado en `scripts/` —el caso exacto para el que existe la regla «toda función nueva
de `scripts/` pasa por esto antes de cerrar el issue»— quedaba fuera, y el gate salía en verde sin
haberlo mirado. Medido el 2026-08-25: `extraction_prompt.py` (dos funciones nuevas) no se mutó.
"""
from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import mutar


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "scripts").mkdir(parents=True)
    (r / "scripts" / "viejo.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t"); _git(r, "config", "user.name", "t")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    return r


def test_diff_incluye_el_archivo_nuevo_sin_trackear(repo: Path, monkeypatch):
    """Es el caso que la regla nombra: función nueva de `scripts/`."""
    # @inv INV-101
    (repo / "scripts" / "nuevo.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    monkeypatch.setattr(mutar, "RAIZ", repo)
    nombres = {p.name for p in mutar.archivos_del_diff()}
    assert "nuevo.py" in nombres, "el gate no ve el código nuevo: sale verde sin mirarlo"


def test_diff_sigue_incluyendo_el_archivo_modificado(repo: Path, monkeypatch):
    (repo / "scripts" / "viejo.py").write_text("def f():\n    return 99\n", encoding="utf-8")
    monkeypatch.setattr(mutar, "RAIZ", repo)
    assert {p.name for p in mutar.archivos_del_diff()} == {"viejo.py"}


def test_diff_no_trae_lo_que_esta_fuera_de_scripts_ni_lo_ignorado(repo: Path, monkeypatch):
    # @inv INV-101
    (repo / ".gitignore").write_text("scripts/ignorado.py\n", encoding="utf-8")
    (repo / "scripts" / "ignorado.py").write_text("def h(): return 3\n", encoding="utf-8")
    (repo / "otro.py").write_text("def i(): return 4\n", encoding="utf-8")
    (repo / "scripts" / "notas.md").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(mutar, "RAIZ", repo)
    nombres = {p.name for p in mutar.archivos_del_diff()}
    assert nombres == set(), f"coló algo que no es código nuevo de scripts/: {nombres}"


def test_diff_no_repite_un_archivo_nuevo_ya_stageado(repo: Path, monkeypatch):
    """Un archivo agregado con `git add` aparece en el diff Y en el listado de untracked de
    algunas configuraciones: mutarlo dos veces duplicaría el costo del gate."""
    (repo / "scripts" / "nuevo.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    _git(repo, "add", "scripts/nuevo.py")
    monkeypatch.setattr(mutar, "RAIZ", repo)
    encontrados = [p.name for p in mutar.archivos_del_diff()]
    assert encontrados.count("nuevo.py") == 1


# ── #187 · dos etapas: el costo dominante era buscar el test asesino en el lugar equivocado ────


@pytest.fixture
def repo_con_tests(repo: Path) -> Path:
    """El `repo` base más `tests/`, que es lo que la etapa 1 necesita para existir."""
    (repo / "tests").mkdir()
    (repo / "tests" / "test_viejo.py").write_text("def test_x(): assert True\n", encoding="utf-8")
    return repo


def test_file_for_encuentra_el_test_del_modulo(repo_con_tests: Path, monkeypatch):
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    hallado = mutar.test_file_for(repo_con_tests / "scripts" / "viejo.py")
    assert hallado == repo_con_tests / "tests" / "test_viejo.py"


def test_file_for_devuelve_none_sin_archivo_1_a_1(repo_con_tests: Path, monkeypatch):
    """Sin `tests/test_<módulo>.py` la etapa 1 se SALTEA, no se aproxima: el fallback seguro es
    pagar la suite completa. Aproximar (p. ej. todo test que importe el módulo) rompería la
    propiedad que hace segura la partición — que una muerte en la etapa 1 sea una muerte."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "huerfano.py").write_text("def z(): return 1\n", encoding="utf-8")
    assert mutar.test_file_for(repo_con_tests / "scripts" / "huerfano.py") is None


def test_file_for_ignora_lo_que_no_es_de_scripts(repo_con_tests: Path, monkeypatch):
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "tools").mkdir()
    (repo_con_tests / "tools" / "viejo.py").write_text("def f(): return 1\n", encoding="utf-8")
    assert mutar.test_file_for(repo_con_tests / "tools" / "viejo.py") is None


def _grabando(monkeypatch, veredictos: list[bool]) -> list[str]:
    """Reemplaza `_suite_verde` por un doble que REGISTRA el blanco de cada corrida y devuelve los
    veredictos en orden. Se mide el blanco, no el tiempo: un umbral de segundos mediría la máquina
    (misma lección que #201)."""
    blancos: list[str] = []
    pendientes = list(veredictos)

    def falso(cwd, subset=None):
        blancos.append(str(subset) if subset else "tests/")
        return pendientes.pop(0)

    monkeypatch.setattr(mutar, "_suite_verde", falso)
    return blancos


def test_la_muerte_en_el_test_propio_no_paga_la_suite(repo_con_tests: Path, monkeypatch, tmp_path):
    """El caso COMÚN (el mutante muere) es el que tiene que abaratarse: una sola corrida, y sobre
    el archivo de tests del módulo. Si esto se rompe, el gate vuelve a tardar ~1 h."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    blancos = _grabando(monkeypatch, [False])          # muere en la etapa 1
    copia = tmp_path / "copia"; (copia / "scripts").mkdir(parents=True)
    (copia / "scripts" / "viejo.py").write_text("x", encoding="utf-8")

    vivos = mutar.mutar_archivo(repo_con_tests / "scripts" / "viejo.py", copia, verbose=False)

    assert vivos == []
    assert blancos == ["tests/test_viejo.py"], (
        f"se pagó de más: {blancos} — la etapa 2 sólo la pagan los SOBREVIVIENTES")


def test_el_sobreviviente_de_la_etapa_1_paga_la_suite_entera(repo_con_tests: Path, monkeypatch,
                                                             tmp_path):
    """La exactitud es lo que no se negocia: una muerte cruzada desde OTRO archivo de tests tiene
    que seguir contando. Sin esta segunda etapa, `mutar` reportaría como 'sin test que la mate' una
    función que sí está cubierta, y el ratchet subiría por un artefacto del atajo."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    blancos = _grabando(monkeypatch, [True, False])    # sobrevive a su test, muere en la suite
    copia = tmp_path / "copia"; (copia / "scripts").mkdir(parents=True)
    (copia / "scripts" / "viejo.py").write_text("x", encoding="utf-8")

    vivos = mutar.mutar_archivo(repo_con_tests / "scripts" / "viejo.py", copia, verbose=False)

    assert vivos == [], "muerte cruzada perdida: el atajo cambió el resultado del gate"
    assert blancos == ["tests/test_viejo.py", "tests/"]


def test_sin_test_propio_va_directo_a_la_suite(repo_con_tests: Path, monkeypatch, tmp_path):
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "huerfano.py").write_text("def z():\n    return 1\n",
                                                            encoding="utf-8")
    blancos = _grabando(monkeypatch, [False])
    copia = tmp_path / "copia"; (copia / "scripts").mkdir(parents=True)
    (copia / "scripts" / "huerfano.py").write_text("x", encoding="utf-8")

    mutar.mutar_archivo(repo_con_tests / "scripts" / "huerfano.py", copia, verbose=False)

    assert blancos == ["tests/"], "sin archivo 1:1 la etapa 1 se saltea, no se aproxima"


def test_two_stage_false_conserva_el_barrido_de_una_etapa(repo_con_tests: Path, monkeypatch,
                                                          tmp_path):
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    blancos = _grabando(monkeypatch, [True])
    copia = tmp_path / "copia"; (copia / "scripts").mkdir(parents=True)
    (copia / "scripts" / "viejo.py").write_text("x", encoding="utf-8")

    vivos = mutar.mutar_archivo(repo_con_tests / "scripts" / "viejo.py", copia, verbose=False,
                                two_stage=False)

    assert vivos == ["f"]
    assert blancos == ["tests/"]


# ── #204 · mutación DIRIGIDA: el bucle de escritura, que no es el gate ──────────────────────────


def _args(archivos, solo=""):
    from types import SimpleNamespace
    return SimpleNamespace(archivos=archivos, solo=solo)


def test_dirigida_no_escala_a_la_suite(repo_con_tests: Path, monkeypatch, tmp_path):
    """Lo que la hace barata: el sobreviviente de la etapa 1 NO paga la suite. El canje es que
    sobre-reporta sobrevivientes (otro archivo podría matarlo) — falla hacia el lado seguro, nunca
    da falso limpio."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    blancos = _grabando(monkeypatch, [True])
    copia = tmp_path / "copia"; (copia / "scripts").mkdir(parents=True)
    (copia / "scripts" / "viejo.py").write_text("x", encoding="utf-8")

    vivos = mutar.mutar_archivo(repo_con_tests / "scripts" / "viejo.py", copia, verbose=False,
                                escalate=False)

    assert vivos == ["f"]
    assert blancos == ["tests/test_viejo.py"], "escaló: dejó de ser el modo barato"


def test_dirigida_only_acota_las_funciones(repo_con_tests: Path, monkeypatch, tmp_path):
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "viejo.py").write_text(
        "def f():\n    return 1\n\n\ndef g():\n    return 2\n", encoding="utf-8")
    blancos = _grabando(monkeypatch, [True])
    copia = tmp_path / "copia"; (copia / "scripts").mkdir(parents=True)
    (copia / "scripts" / "viejo.py").write_text("x", encoding="utf-8")

    vivos = mutar.mutar_archivo(repo_con_tests / "scripts" / "viejo.py", copia, verbose=False,
                                escalate=False, only={"g"})

    assert vivos == ["g"]
    assert len(blancos) == 1, "mutó funciones que no se le pidieron"


def test_dirigida_rehusa_sin_test_1_a_1(repo_con_tests: Path, monkeypatch, capsys):
    """Se rehúsa en vez de degradar a la suite completa: el modo se pide **por barato**, y devolver
    en silencio la corrida cara es la clase de promesa incumplida que este repo persigue."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "huerfano.py").write_text("def z():\n    return 1\n",
                                                            encoding="utf-8")
    monkeypatch.setattr(mutar, "_copia_del_repo",
                        lambda d: pytest.fail("degradó a la corrida cara sin avisar"))

    assert mutar._directed(_args(["scripts/huerfano.py"])) == 2
    assert "no hay tests/test_huerfano.py" in capsys.readouterr().out


def test_dirigida_sin_funciones_mutables_no_es_un_verde(repo_con_tests: Path, monkeypatch, capsys):
    """Cero mutaciones NO es "murieron todas" (D-43). Medido sobre el repo real: `ingest_star.py`
    es todo `main`, que está en EXENTAS, así que el modo corría cero mutantes y cerraba con un ✅
    que nadie había medido — un cero inventado leído como veredicto."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "vacio.py").write_text("def main():\n    return 1\n",
                                                          encoding="utf-8")
    (repo_con_tests / "tests" / "test_vacio.py").write_text("def test_y(): assert True\n",
                                                             encoding="utf-8")

    assert mutar._directed(_args(["scripts/vacio.py"])) == 2, "cerró en verde sin medir nada"
    assert "NO es un verde" in capsys.readouterr().out


def test_dirigida_toma_un_solo_modulo(repo_con_tests: Path, monkeypatch):
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    assert mutar._directed(_args(["scripts/viejo.py", "scripts/otro.py"])) == 2


def test_dirigida_rechaza_una_funcion_inexistente(repo_con_tests: Path, monkeypatch, capsys):
    """Un `--solo` con un typo mutaría cero funciones y cerraría en verde: mismo falso limpio."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    assert mutar._directed(_args(["scripts/viejo.py"], solo="noexiste")) == 2
    # #339 — el texto pasó al singular de `_report_unmutable`, que es el que distingue los estados
    assert "no existe en viejo.py" in capsys.readouterr().out


# ── la copia de trabajo tiene que arrancar VERDE (auditoría 2026-08-28) ─────────────────────────


@pytest.mark.poblada
def test_la_copia_del_repo_arranca_con_baseline_verde():
    """⛔ Si la suite está roja **dentro de la copia**, `mutar` se niega a correr entero: la red #1
    queda inoperable y ningún test lo nota.

    Medido el 2026-08-28: `_copia_del_repo` excluye `.git` —a propósito, no hace falta y pesa— y un
    test agregado ese día corría `git ls-files` con `check=True`, así que reventaba en la copia. El
    gate salía con «la suite ya está roja sin mutar» sobre un árbol real perfectamente verde.

    Ninguno de los 17 tests de este archivo podía verlo: **todos doblan `_suite_verde`** y ninguno
    ejerce `_copia_del_repo` contra el árbol real (uno hasta asserta que no se llame). Es la forma
    exacta de INV-101 —*la red que no mira el código nuevo no es una red*— aplicada a la red #1.

    Va en tier 1: copia el repo y corre la suite entera (~20 s), demasiado para el tier de cada
    commit.  @inv INV-101"""
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="almagesto-baseline-"))
    try:
        copia = mutar._copia_del_repo(tmp / "repo")
        assert mutar._suite_verde(copia), (
            "la suite está ROJA dentro de la copia de trabajo: `tools/mutar.py` se niega a correr "
            "y la red #1 queda inoperable. Suele ser un test que necesita algo que la copia no "
            "lleva (`.git`, `build/`, `vault/` con contenido).")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── el ratchet PEDIDO que no puede correr (AUD-138) ──────────────────────────

def _args_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["mutar.py", *argv])
    return mutar.main()


def test_ratchet_sin_archivo_no_sale_verde(repo_con_tests: Path, monkeypatch, capsys):
    """AUD-138 / D-43 — `if args.ratchet and RATCHET.exists()` salteaba el bloque entero y `main`
    devolvía **0 con sobrevivientes**: pedir el gate y no tenerlo se leía igual que pasarlo.

    Es el cero inventado que el lint reporta como *no evaluado*, en la herramienta cuyo trabajo es
    auditar a los tests."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    monkeypatch.setattr(mutar, "RATCHET", repo_con_tests / "no-existe.yaml")
    monkeypatch.setattr(mutar, "mutar_archivo", lambda *a, **k: ["viejo.py::f"])
    monkeypatch.setattr(mutar, "_copia_del_repo", lambda d: repo_con_tests)
    assert _args_main(monkeypatch, ["scripts/viejo.py", "--ratchet"]) == 2
    assert "no evaluado" in capsys.readouterr().out


def test_ratchet_sin_techo_declarado_no_sale_verde(repo_con_tests: Path, monkeypatch, capsys):
    """Un `techo` ausente caía al default `0`: cualquier sobreviviente pasaba a rojo, y un YAML
    vacío se leía como un techo deliberado. No declarar no es declarar cero."""
    ratchet = repo_con_tests / "ratchet.yaml"
    ratchet.write_text("medido_en: '2026-01-01'\n", encoding="utf-8")
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    monkeypatch.setattr(mutar, "RATCHET", ratchet)
    monkeypatch.setattr(mutar, "mutar_archivo", lambda *a, **k: [])
    monkeypatch.setattr(mutar, "_copia_del_repo", lambda d: repo_con_tests)
    assert _args_main(monkeypatch, ["scripts/viejo.py", "--ratchet"]) == 2
    assert "no declara `techo`" in capsys.readouterr().out


def test_el_diff_no_lista_lo_borrado(repo_con_tests: Path, monkeypatch):
    """AUD-191 / INV-101 — `git diff --name-only` lista también lo **borrado**, y sobre un archivo
    que no está en disco `funciones()` revienta con `FileNotFoundError`.

    O sea: el gate no sale en rojo por un hallazgo, se **cae** — sobre el caso más normal de un
    refactor (mover o eliminar un módulo). Un módulo eliminado no tiene funciones que mutar."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    monkeypatch.setattr(mutar.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(
                            returncode=0, stdout="scripts/viejo.py\nscripts/borrado.py\n", stderr=""))
    archivos = mutar.archivos_del_diff()
    assert [f.name for f in archivos] == ["viejo.py"], "un archivo borrado no tiene qué mutar"
    for f in archivos:
        mutar.funciones(f)                # no revienta


# ── AUD-212 · la atribución del mapa de trazabilidad ─────────────────────────

def test_los_pares_de_trazabilidad_salen_de_las_DOS_marcas(monkeypatch):
    """AUD-212 — sólo se audita el invariante que tiene marca en los dos árboles: sin marca de test
    no hay atribución que auditar, y sin marca de implementación no hay qué mutar.

    Y se auditan TODAS las implementaciones marcadas, no la primera: lo que la fila afirma es que
    **esos** símbolos la cumplen, así que cada uno tiene que estar cubierto por alguno de **esos**
    tests. Auditar sólo la primera dejaba pasar la marca puesta de más — fue el primer resultado
    real del gate (11 filas → 20 al mirar todos los símbolos)."""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class M:
        inv: str
        kind: str
        path: str
        line: int
        symbol: str

    import trace_invariants as ti
    monkeypatch.setattr(ti, "load_registro", lambda root: {
        "INV-01": {"estado": "garantizado y medido"},
        "INV-02": {"estado": "garantizado y medido"},
        "INV-03": {"estado": "retirado (#205)"},
    })
    monkeypatch.setattr(ti, "collect_marks", lambda root: [
        M("INV-01", "impl", "scripts/a.py", 1, "f"),
        M("INV-01", "impl", "scripts/a.py", 9, "g"),      # segunda impl: también se audita
        M("INV-01", "test", "tests/test_a.py", 2, "test_x"),
        M("INV-02", "impl", "scripts/b.py", 1, "h"),      # sin marca de test → fuera
        M("INV-03", "impl", "scripts/c.py", 1, "i"),      # retirado → fuera
        M("INV-03", "test", "tests/test_c.py", 1, "test_z"),
    ])
    pares = mutar._traceability_pairs()
    assert [(inv, sym) for inv, _f, sym, _t in pares] == [("INV-01", "f"), ("INV-01", "g")]
    assert pares[0][3] == ["tests/test_a.py::test_x"]


# ── AUD-213 · mutación de GUARDAS: el mutante de función vacía el cuerpo entero ────────────────
#
# Un módulo donde mueren todos los mutantes de función sigue sin decir nada sobre sus condiciones:
# `entity.py` tenía 30 guardas de 84 y `harvest_views.py` 18 de 72 sin test que las distinga. Estos
# tests fijan las tres propiedades que hacen usable el modo: qué se muta, que el código mutado sea
# válido, y que la baseline roja NO devuelva un cero.


_CON_GUARDAS = '''\
def f(x, y):
    if x and y:
        return 1
    if x:
        return 2
    return 3
'''


def test_guardas_muta_la_condicion_entera_y_cada_clausula(tmp_path: Path):
    """La granularidad ES el hallazgo: `if x and y` con tests que sólo dan `x=False` nunca ejercita
    `y`, y sólo el mutante por cláusula lo dice. La cláusula se neutraliza con la identidad de su
    operador (`True` en un `and`), así que la guarda **sigue** firando por la otra."""
    m = tmp_path / "m.py"; m.write_text(_CON_GUARDAS, encoding="utf-8")
    etiquetas = [(g.func, g.label, g.replacement) for g in mutar.guards(m)]
    assert ("f", "if@L2", "False") in etiquetas
    assert ("f", "if@L2/and[0]", "True") in etiquetas
    assert ("f", "if@L2/and[1]", "True") in etiquetas
    assert ("f", "if@L4", "False") in etiquetas
    assert len(etiquetas) == 4


def test_guardas_ignora_lo_que_esta_fuera_de_una_funcion_y_las_constantes(tmp_path: Path):
    """`if __name__ == "__main__":` y `if TYPE_CHECKING:` no son guardas de nadie. Y una condición
    constante se saltea porque reescribir `False` como `False` no cambia nada: se reportaría como
    SOBREVIVE, o sea un hallazgo que la herramienta inventó."""
    m = tmp_path / "m.py"
    m.write_text('import sys\n\nif sys.argv:\n    pass\n\n\ndef f(x):\n    if False:\n'
                 '        return 1\n    if x:\n        return 2\n', encoding="utf-8")
    # ⚠ El `if` de módulo lleva condición NO constante a propósito: con `if True:` la rama de las
    # constantes lo tapaba y la mitad «sólo adentro de una función» quedaba sin cubrir — lo
    # encontró `--guardas` corriéndose sobre sí mismo.
    assert [(g.func, g.label) for g in mutar.guards(m)] == [("f", "if@L10")]


def test_la_clausula_CONSTANTE_de_un_and_tampoco_se_muta(tmp_path: Path):
    """El caso que el propio `--guardas` encontró al correrse sobre este archivo (2026-08-28): la
    guarda que saltea una cláusula constante **sobrevivía**, porque el test de la cláusula usaba
    `if x and y` —dos nombres— y el de las constantes usaba `if False:`, que es un test constante,
    no una cláusula. O sea: ninguno de los dos ejercitaba esta rama. Sin ella, `if x and True`
    emitiría un mutante que reescribe `True` como `True` y saldría SOBREVIVE — una guarda sin test
    que la herramienta se inventó."""
    m = tmp_path / "m.py"; m.write_text("def f(x):\n    if x and True:\n        return 1\n",
                                        encoding="utf-8")
    assert [g.label for g in mutar.guards(m)] == ["if@L2", "if@L2/and[0]"]


def test_el_elif_es_una_guarda_y_el_if_de_una_comprension_no(tmp_path: Path):
    """`elif` es un `ast.If` anidado en `orelse` —una guarda como cualquier otra—; el `if` de una
    comprensión no es un `ast.If` y queda afuera. Si esto se rompe, la cuenta de guardas de un
    módulo cambia sin que cambie el código."""
    m = tmp_path / "m.py"
    m.write_text("def f(x, xs):\n    if x:\n        return 1\n    elif xs:\n        return 2\n"
                 "    return [i for i in xs if i]\n", encoding="utf-8")
    assert [g.label for g in mutar.guards(m)] == ["if@L2", "if@L4"]


def test_toda_guarda_de_scripts_produce_codigo_QUE_PARSEA():
    """La red de la red. `col_offset` es un offset de **bytes UTF-8**, no de caracteres, y este
    repo tiene prosa acentuada en casi toda línea: cortar el `str` en vez de los bytes parte la
    condición al medio y el mutante no compila — con lo cual "muere" por SyntaxError, o sea por el
    motivo equivocado (#202), y el modo devuelve 0 sobrevivientes sobre un módulo que nadie midió.
    """
    import ast as _ast
    scripts = sorted((Path(__file__).resolve().parents[1] / "scripts").glob("*.py"))
    total = 0
    for m in scripts:
        src = m.read_text(encoding="utf-8")
        for g in mutar.guards(m):
            total += 1
            _ast.parse(mutar._replace_span(src, g))     # revienta si el splice cortó mal
    assert total > 500, f"sólo {total} guardas: el recolector dejó de ver la mayoría del corpus"


def test_la_condicion_multilinea_colapsa_en_una_sola(tmp_path: Path):
    """Una condición repartida en varias líneas se reemplaza entera: lo de antes en la primera, el
    literal, lo de después en la última. Sin esto quedan colgando el `and` y el paréntesis."""
    m = tmp_path / "m.py"
    m.write_text("def f(a, b):\n    if (a\n            and b):\n        return 1\n",
                 encoding="utf-8")
    entera = [g for g in mutar.guards(m) if g.label == "if@L2"][0]
    assert mutar._replace_span(m.read_text(encoding="utf-8"), entera) == (
        "def f(a, b):\n    if (False):\n        return 1\n")


def test_guardas_solo_corre_la_etapa_barata(repo_con_tests: Path, monkeypatch, tmp_path):
    """Mismo contrato que `--dirigida`: NO escala a la suite, así que sobre-reporta sobrevivientes
    y nunca da un falso limpio. Si escalara, el modo dejaría de ser el bucle de escritura."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "viejo.py").write_text(_CON_GUARDAS, encoding="utf-8")
    blancos = _grabando(monkeypatch, [True, False, False, False])
    copia = tmp_path / "copia"; (copia / "scripts").mkdir(parents=True)
    (copia / "scripts" / "viejo.py").write_text("x", encoding="utf-8")

    vivos = mutar.mutate_guards(repo_con_tests / "scripts" / "viejo.py", copia,
                                Path("tests/test_viejo.py"), verbose=False)

    assert vivos == ["f::if@L2"]
    assert blancos == ["tests/test_viejo.py"] * 4, f"pagó de más: {blancos}"


def test_guardas_con_la_baseline_ROJA_no_devuelve_cero(repo_con_tests: Path, monkeypatch, capsys):
    """D-43 dentro de la herramienta que audita los tests. Con `tests/test_<mod>.py` ya en rojo,
    TODA guarda 'muere' por el motivo equivocado y el modo imprimiría «murieron todas ✅» sobre un
    módulo que nadie midió. Sale 2 (no evaluado), no 0."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "viejo.py").write_text(_CON_GUARDAS, encoding="utf-8")
    monkeypatch.setattr(mutar, "_copia_del_repo", lambda destino: destino)
    monkeypatch.setattr(mutar, "_suite_verde", lambda cwd, subset=None: False)
    def _no_llamar(*a, **k):
        raise AssertionError("mutó con la baseline en rojo")
    monkeypatch.setattr(mutar, "mutate_guards", _no_llamar)

    rc = mutar._guards(SimpleNamespace(archivos=["scripts/viejo.py"], solo=""))

    assert rc == 2
    assert "no evaluado" in capsys.readouterr().out


def test_guardas_sin_ninguna_guarda_no_es_un_verde(repo_con_tests: Path, monkeypatch, capsys):
    """Cero guardas NO es «murieron todas» — el mismo cero inventado que `--dirigida` ya rechaza."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "viejo.py").write_text("def f():\n    return 1\n",
                                                         encoding="utf-8")
    rc = mutar._guards(SimpleNamespace(archivos=["scripts/viejo.py"], solo=""))
    assert rc == 2
    assert "NO es un verde" in capsys.readouterr().out


def test_guardas_rehusa_sin_test_1_a_1(repo_con_tests: Path, monkeypatch, capsys):
    """Sin la etapa barata no hay modo: se rehúsa en vez de degradar a la corrida cara."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "huerfano.py").write_text(_CON_GUARDAS, encoding="utf-8")
    rc = mutar._guards(SimpleNamespace(archivos=["scripts/huerfano.py"], solo=""))
    assert rc == 2
    assert "no hay tests/test_huerfano.py" in capsys.readouterr().out


def test_guardas_only_acota_a_las_funciones_pedidas(repo_con_tests: Path, monkeypatch, tmp_path):
    """`--solo` tiene que **filtrar**: sin el guard se mutan todas (se paga de más y el reporte
    nombra guardas que nadie pidió), y con el guard invertido no se muta ninguna."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "viejo.py").write_text(
        "def f(x, y):\n    if x and y:\n        return 1\n\n\ndef g(z):\n    if z:\n"
        "        return 2\n", encoding="utf-8")
    blancos = _grabando(monkeypatch, [False] * 3)
    copia = tmp_path / "copia"; (copia / "scripts").mkdir(parents=True)
    (copia / "scripts" / "viejo.py").write_text("x", encoding="utf-8")

    mutar.mutate_guards(repo_con_tests / "scripts" / "viejo.py", copia,
                        Path("tests/test_viejo.py"), only={"f"}, verbose=False)

    assert len(blancos) == 3, f"se mutaron guardas de otra función: {len(blancos)} corridas"


def test_guardas_verbose_dice_lo_que_paso_con_cada_una(repo_con_tests: Path, monkeypatch, tmp_path,
                                                       capsys):
    """La línea por guarda **es** la salida del modo: sin ella el operador ve un total y no sabe
    cuál sobrevivió."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "viejo.py").write_text("def f(x):\n    if x:\n        return 1\n",
                                                         encoding="utf-8")
    _grabando(monkeypatch, [True])
    copia = tmp_path / "copia"; (copia / "scripts").mkdir(parents=True)
    (copia / "scripts" / "viejo.py").write_text("x", encoding="utf-8")

    mutar.mutate_guards(repo_con_tests / "scripts" / "viejo.py", copia,
                        Path("tests/test_viejo.py"))

    assert "SOBREVIVE" in capsys.readouterr().out


def test_guardas_toma_un_solo_modulo(repo_con_tests: Path, monkeypatch):
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    assert mutar._guards(SimpleNamespace(archivos=[], solo="")) == 2
    assert mutar._guards(SimpleNamespace(archivos=["a.py", "b.py"], solo="")) == 2


def test_guardas_rechaza_una_funcion_sin_guardas(repo_con_tests: Path, monkeypatch, capsys):
    """Un `--solo` que no matchea nada mediría **cero** y cerraría en verde. Se nombra y se rehúsa,
    igual que `--dirigida` con una función inexistente."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "viejo.py").write_text(_CON_GUARDAS, encoding="utf-8")
    rc = mutar._guards(SimpleNamespace(archivos=["scripts/viejo.py"], solo="noexiste"))
    assert rc == 2
    assert "noexiste" in capsys.readouterr().out


def test_guardas_con_sobrevivientes_sale_1_y_los_LISTA(repo_con_tests: Path, monkeypatch, capsys):
    """El caso que el modo existe para reportar. Sin este guard imprimiría «murieron todas ✅» y
    devolvería 0 **teniendo sobrevivientes** — el falso limpio adentro del detector de falsos
    limpios."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "viejo.py").write_text(_CON_GUARDAS, encoding="utf-8")
    monkeypatch.setattr(mutar, "_copia_del_repo", lambda destino: destino)
    monkeypatch.setattr(mutar, "_suite_verde", lambda cwd, subset=None: True)
    monkeypatch.setattr(mutar, "mutate_guards", lambda *a, **k: ["f::if@L2"])

    rc = mutar._guards(SimpleNamespace(archivos=["scripts/viejo.py"], solo=""))

    salida = capsys.readouterr().out
    assert rc == 1
    assert "f::if@L2" in salida and "✅" not in salida


# ── #335 · los tres estados de un `--solo` sin nada que mutar ───────────────────────────────────
#
# D-43 aplicado a la RESOLUCIÓN DE SÍMBOLOS, no sólo al conteo de mutaciones: «la función está en
# EXENTAS» y «el símbolo no existe» piden acciones OPUESTAS —mover el condicional a una función
# propia contra corregir el nombre— y salían con el mismo texto. Consecuencia medida: al implementar
# #331 el guard nuevo vivía dentro de `main` y ninguna red de mutación lo miraba; el implementador
# lo movió por criterio propio, no porque la herramienta se lo dijera.

_TRES_ESTADOS = '''\
def main():
    if 1 == 2:
        return 1
    return 0


def sin_condicionales():
    return 42


def con_guarda(x):
    if x:
        return 1
    return 0
'''


@pytest.fixture
def repo_tres_estados(repo_con_tests: Path, monkeypatch) -> Path:
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "scripts" / "viejo.py").write_text(_TRES_ESTADOS, encoding="utf-8")
    return repo_con_tests


def test_la_funcion_EXENTA_se_declara_como_tal_y_nombra_EXENTAS(repo_tres_estados, monkeypatch,
                                                                capsys):
    """`main` EXISTE y tiene condicionales: lo que pasa es que está exenta. El remedio es mover el
    condicional a una función propia — exactamente lo que #331 tuvo que descubrir solo."""
    monkeypatch.setattr(mutar, "_copia_del_repo",
                        lambda d: pytest.fail("mutó sin haber resuelto el símbolo"))
    assert mutar._guards(_args(["scripts/viejo.py"], solo="main")) == 2
    out = capsys.readouterr().out
    assert "EXENTAS" in out, "el mensaje tiene que NOMBRAR la lista que la excluyó"
    assert "función propia" in out, "y decir el remedio, que es mover el condicional"
    assert "no existe" not in out, "existe: decir lo contrario manda a corregir un nombre correcto"


def test_la_funcion_SIN_GUARDAS_no_se_confunde_con_un_typo(repo_tres_estados, monkeypatch, capsys):
    """Existe, no está exenta y no tiene un solo condicional: es un cero por causa legítima. Sigue
    sin ser un verde (no se midió nada), pero el motivo es otro y la acción también: acá no hay
    nada que corregir."""
    monkeypatch.setattr(mutar, "_copia_del_repo",
                        lambda d: pytest.fail("mutó sin haber resuelto el símbolo"))
    assert mutar._guards(_args(["scripts/viejo.py"], solo="sin_condicionales")) == 2
    out = capsys.readouterr().out
    assert "sin_condicionales" in out and "ningún condicional" in out
    assert "EXENTAS" not in out and "no existe" not in out


def test_el_SIMBOLO_INEXISTENTE_se_llama_typo(repo_tres_estados, monkeypatch, capsys):
    """El tercer estado, y el único cuya acción es corregir el `--solo`. El mensaje viejo **ofrecía
    las dos causas juntas** (`o no existen`), que es la conflación: quien lo lee no sabe si buscar
    un typo o mover un condicional."""
    monkeypatch.setattr(mutar, "_copia_del_repo",
                        lambda d: pytest.fail("mutó sin haber resuelto el símbolo"))
    assert mutar._guards(_args(["scripts/viejo.py"], solo="no_existe_jamas")) == 2
    out = capsys.readouterr().out
    assert "no existe" in out and "no_existe_jamas" in out and "typo" in out
    assert "o no existen" not in out, "la disyunción ES la conflación"
    assert "EXENTAS" not in out and "ningún condicional" not in out


def test_los_tres_estados_salen_SEPARADOS_en_la_misma_corrida(repo_tres_estados, monkeypatch,
                                                              capsys):
    """La partición es lo que se rompe primero: con los tres pedidos juntos, un mensaje que los
    junta vuelve a la conflación aunque los textos existan por separado."""
    monkeypatch.setattr(mutar, "_copia_del_repo",
                        lambda d: pytest.fail("mutó sin haber resuelto el símbolo"))
    assert mutar._guards(_args(["scripts/viejo.py"],
                               solo="main,sin_condicionales,no_existe_jamas")) == 2
    lineas = [l for l in capsys.readouterr().out.split("\n") if l.strip()]
    def _linea(nombre):
        return next(l for l in lineas if nombre in l)
    assert _linea("main") != _linea("sin_condicionales") != _linea("no_existe_jamas")
    assert "EXENTAS" in _linea("main")
    assert "ningún condicional" in _linea("sin_condicionales")
    assert "no existe" in _linea("no_existe_jamas")


def test_la_funcion_CON_guardas_sigue_pasando_a_mutar(repo_tres_estados, monkeypatch, tmp_path):
    """La otra mitad: los tres estados nuevos no pueden tragarse el caso normal. Sin esto, «no
    confunde estados» se cumpliría rehusando siempre."""
    monkeypatch.setattr(mutar, "_copia_del_repo", lambda d: tmp_path / "copia")
    monkeypatch.setattr(mutar, "_suite_verde", lambda *a, **k: True)
    llamadas: list = []
    monkeypatch.setattr(mutar, "mutate_guards",
                        lambda *a, **k: llamadas.append(k.get("only")) or [])
    assert mutar._guards(_args(["scripts/viejo.py"], solo="con_guarda")) == 0
    assert llamadas == [{"con_guarda"}]


# ── #339 · la conflación de #335 seguía viva en los otros dos modos ─────────────────────────────
#
# `_report_unmutable` estaba escrito (v1.142.0) y NO estaba cableado en `--dirigida` ni en
# `--trazabilidad`: la misma regla en tres copias es cómo divergió tres veces en este repo
# (#215/#324/#335). Los tres modos cierran por `report_states`.


def test_dirigida_declara_la_funcion_EXENTA_y_no_la_llama_inexistente(repo_tres_estados,
                                                                      monkeypatch, capsys):
    """El defecto medido: `--dirigida --solo main scripts/triage.py` contestaba «⛔ no existen en
    triage.py: ['main']` sobre una función que existe y tiene 56 `if`. Peor que la de `--guardas`,
    que al menos hedgeaba con «o no tienen guardas»: ésta AFIRMA algo falso."""
    monkeypatch.setattr(mutar, "_copia_del_repo",
                        lambda d: pytest.fail("mutó sin haber resuelto el símbolo"))
    assert mutar._directed(_args(["scripts/viejo.py"], solo="main")) == 2
    out = capsys.readouterr().out
    assert "EXENTAS" in out, "el mensaje tiene que NOMBRAR la lista que la excluyó"
    assert "no existe" not in out, "existe: decir lo contrario manda a corregir un nombre correcto"


def test_dirigida_llama_typo_al_simbolo_que_de_veras_no_esta(repo_tres_estados, monkeypatch,
                                                             capsys):
    """La otra mitad de la partición: sin esto, «no dice no-existe» se cumpliría no diciéndolo
    nunca, y el typo real se quedaría sin su única acción posible."""
    monkeypatch.setattr(mutar, "_copia_del_repo",
                        lambda d: pytest.fail("mutó sin haber resuelto el símbolo"))
    assert mutar._directed(_args(["scripts/viejo.py"], solo="no_existe_jamas")) == 2
    out = capsys.readouterr().out
    assert "no existe" in out and "no_existe_jamas" in out and "typo" in out
    assert "EXENTAS" not in out


def test_report_states_no_junta_dos_estados_en_una_linea(capsys):
    """La unidad compartida por los tres modos. La partición es lo primero que se rompe: con los
    textos escritos aparte pero impresos juntos, la conflación vuelve intacta."""
    assert mutar.report_states({"a": ["x"], "b": [], "c": ["y", "z"]},
                               {"a": "A: {nombres}", "b": "B: {nombres}",
                                "c": "C: {nombres}"}) == 2
    lineas = [l for l in capsys.readouterr().out.split("\n") if l.strip()]
    assert lineas == ["A: x", "C: y, z"], ("una línea por estado con nombres, y el estado vacío no "
                                           "imprime nada — «ninguno» no es «no se miró»")
    assert mutar.report_states({"a": [], "b": []}, {}) == 0, "sin nombres no se dice nada"
    assert capsys.readouterr().out == ""


def test_report_states_revienta_si_un_estado_con_nombres_no_tiene_texto():
    """Un estado sin texto se salteaba en silencio sería el mensaje fusionado otra vez, sólo que
    invisible: el lector no ve ni la línea ni el hueco."""
    with pytest.raises(KeyError):
        mutar.report_states({"a": ["x"]}, {})


# ── #339 · `tools/` está FUERA DE ALCANCE, y decirlo no es negar un archivo que existe ──────────


@pytest.fixture
def repo_con_tools(repo_con_tests: Path, monkeypatch) -> Path:
    """`tools/mutar.py` **con** su `tests/test_mutar.py`: el caso exacto que el mensaje negaba."""
    monkeypatch.setattr(mutar, "RAIZ", repo_con_tests)
    (repo_con_tests / "tools").mkdir(exist_ok=True)
    (repo_con_tests / "tools" / "mutar.py").write_text(_TRES_ESTADOS, encoding="utf-8")
    (repo_con_tests / "tests" / "test_mutar.py").write_text("def test_x(): assert True\n",
                                                            encoding="utf-8")
    return repo_con_tests


@pytest.mark.parametrize("modo", ["_directed", "_guards"])
def test_apuntar_a_tools_dice_fuera_de_alcance_y_no_niega_el_test_que_existe(repo_con_tools, modo,
                                                                            monkeypatch, capsys):
    """El alcance (`CLAUDE.md`: «toda función nueva de `scripts/`») es una decisión DECLARADA y se
    queda. El defecto era el mensaje: apuntar cualquiera de los dos modos a `tools/mutar.py`
    contestaba «⛔ no hay tests/test_mutar.py» **con ese archivo en el árbol**, o sea que la
    herramienta que corre la red daba un motivo falso para no recibirla."""
    monkeypatch.setattr(mutar, "_copia_del_repo",
                        lambda d: pytest.fail("mutó algo fuera de alcance"))
    assert getattr(mutar, modo)(_args(["tools/mutar.py"])) == 2
    out = capsys.readouterr().out
    assert "fuera de alcance" in out and "tools/" in out
    assert "⛔ no hay tests/test_mutar.py" not in out, "niega un archivo que existe"


def test_el_modulo_de_scripts_sin_test_propio_sigue_siendo_el_OTRO_estado(repo_con_tools,
                                                                         monkeypatch, capsys):
    """El estado que no se puede tragar: dentro del alcance y sin `tests/test_<mod>.py` sí es un
    hueco real, y su acción —escribir el archivo— es la opuesta a la de «fuera de alcance»."""
    (repo_con_tools / "scripts" / "huerfano.py").write_text("def z(): return 1\n", encoding="utf-8")
    assert mutar._guards(_args(["scripts/huerfano.py"])) == 2
    out = capsys.readouterr().out
    assert "no hay tests/test_huerfano.py" in out and "fuera de alcance" not in out


# ── #339 · `--trazabilidad --solo`: tres estados, no una disyunción ─────────────────────────────


def test_unmarked_reasons_separa_typo_de_retirado_de_sin_marcas():
    """El mensaje viejo era byte-idéntico para `INV-999-NOPE` y para `INV-126`, que existe, es P0 y
    cuya fila dice «hay código sin marcar». Su remedio es AGREGAR la marca `@inv`, no corregir el
    `--solo`: la disyunción («o no tienen las dos marcas») manda a buscar un typo en un nombre
    correcto."""
    fuera = mutar.unmarked_reasons({"INV-01", "INV-02", "INV-03", "INV-04"},
                                   filas={"INV-01", "INV-02", "INV-03"},
                                   retirados={"INV-02"}, auditables={"INV-01"})
    assert fuera == {"no_existe": ["INV-04"], "retirado": ["INV-02"], "sin_marcas": ["INV-03"]}


def test_trazabilidad_rehusa_nombrando_el_estado_y_no_muta_nada(repo_con_tests, monkeypatch,
                                                                capsys):
    """Y rehúsa aunque el resto del `--solo` sí sea auditable: se pidieron N filas y se midieron
    M < N, y publicar el 0 de M como veredicto de N es el falso limpio que D-43 nombra."""
    monkeypatch.setattr(mutar, "_traceability_pairs",
                        lambda: [("INV-01", Path("scripts/x.py"), "f", ["tests/t.py::test_f"])])
    monkeypatch.setattr(mutar, "_contract_rows",
                        lambda: ({"INV-01", "INV-03"}, set()))
    monkeypatch.setattr(mutar, "_copia_del_repo",
                        lambda d: pytest.fail("auditó con un `--solo` sin resolver"))
    assert mutar._trazabilidad(_args([], solo="INV-01,INV-03,INV-99")) == 2
    lineas = [l for l in capsys.readouterr().out.split("\n") if l.strip()]
    def _linea(nombre):
        return next(l for l in lineas if nombre in l)
    assert _linea("INV-99") != _linea("INV-03")
    assert "typo" in _linea("INV-99") and "no existe" in _linea("INV-99")
    assert "AGREGAR" in _linea("INV-03") and "marca" in _linea("INV-03")
    assert "o no tienen las dos marcas" not in "\n".join(lineas), "la disyunción ES la conflación"


def test_contract_rows_lee_el_contrato_real_y_separa_los_retirados():
    """El adaptador que le da a `unmarked_reasons` sus dos sets. Sin test propio sobrevivía a que
    le vaciaran el cuerpo: el resto de los tests de `--trazabilidad` lo monkeypatchean, así que la
    única función que toca el contrato de verdad quedaba sin mirar."""
    filas, retirados = mutar._contract_rows()
    assert len(filas) > 50 and retirados <= filas, "los retirados son filas, no un universo aparte"
    assert "INV-01" in filas and "INV-01" not in retirados
    assert retirados, ("el contrato tiene al menos un invariante retirado; sin ninguno, el estado "
                       "`retirado` de `unmarked_reasons` nunca se ejercita contra datos reales")
