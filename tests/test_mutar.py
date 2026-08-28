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
    assert "no existen en viejo.py" in capsys.readouterr().out


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
