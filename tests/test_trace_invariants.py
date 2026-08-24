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


def test_registro_real_cubre_los_91():
    """Contra el contrato REAL del repo: el parser tiene que leer los 91 invariantes vivos. Es la
    prueba de que la forma de la tabla que el parser asume es la que el documento tiene."""
    reg = ti.parse_contrato(ti.CONTRATO.read_text(encoding="utf-8"))
    assert len(reg) == 91
    assert "INV-01" in reg and "INV-91" in reg


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
    marcas = [m for m in ti.collect_marks(ti.ROOT)
              if m.path.endswith(("trace_invariants.py", "test_trace_invariants.py"))]
    assert marcas == []


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
