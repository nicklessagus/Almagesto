"""La convención de idioma del código tiene una red, no sólo un párrafo (#156).

`CLAUDE.md` fija desde el 2026-08-24: **archivos, nombres de funciones, docstrings y comentarios
NUEVOS en inglés**; la prosa de la doc sigue en castellano; **sin retrofit**.

Hasta este archivo la regla no vivía en ningún documento versionado —sólo en la bitácora interna,
que está gitignored— y no la vigilaba nadie. Medido en la pasada `/auditar` del 2026-08-27: de 237
funciones nuevas desde que se decidió, **30** tienen nombre en castellano. *Una promesa que el
sistema dejó de cumplir en silencio es peor que una que nunca hizo.*

El ratchet es la forma correcta acá y no un barrido de renombres: renombrar 30 símbolos rompería
marcas `@inv`, punteros de `docs/trazabilidad.md` y llamadores por nada, mientras que un techo que
sólo baja impide que la deuda **crezca**, que es el único daño que sigue ocurriendo.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
RATCHET = RAIZ / "tools" / "idioma-ratchet.yaml"

# Marcadores de castellano en un identificador. Deliberadamente CORTOS y de alta señal: la lista
# larga daría falsos positivos con palabras que son iguales en los dos idiomas (`total`, `error`,
# `version`). Se comparan contra los segmentos separados por `_`, no como substring: `paper` no
# puede matchear `pa`, y `de` no puede matchear `dedup`.
SEGMENTOS_ES = {
    "de", "del", "que", "por", "para", "con", "sin", "los", "las", "una", "uno",
    "campo", "campos", "nota", "notas", "linea", "lineas", "archivo", "archivos",
    "buscar", "resolver", "guardar", "cargar", "borrar", "contar", "leer", "escribir",
    "cuenta", "cuentas", "prioridad", "puerta", "puertas", "alcance", "excluidos",
    "inventario", "evidencia", "simbolo", "anclado", "copia", "repo", "diff",
    "aplicar", "reescribir", "consolidar", "diverge", "upstream", "curado",
    "resueltos", "barrido", "descubrimiento", "sujeto", "wikilinks", "frontmatter",
    "declarativas", "posturas", "desafia", "mejor", "merge", "cambios", "citan",
    "verdict", "pelado", "marcado", "modulos", "escriben", "vault",
}
# Segmentos que son inglés o neutrales aunque figuren arriba por convivencia (`merge`, `diff`,
# `repo`, `upstream`, `vault`, `verdict`, `frontmatter` son términos del dominio en inglés).
NEUTRALES = {"merge", "diff", "repo", "upstream", "vault", "verdict", "frontmatter", "wikilinks"}


def _es_castellano(nombre: str) -> bool:
    segs = [s for s in nombre.strip("_").lower().split("_") if s]
    return any(s in SEGMENTOS_ES and s not in NEUTRALES for s in segs)


# Marcadores de castellano en PROSA (docstrings y comentarios). Palabras funcionales que el inglés
# no tiene: se exigen **tres** para no marcar un docstring inglés que cite un término del dominio.
# ⚠ Es heurística declarada, no prueba — el techo la absorbe: lo que este ratchet mide es el DELTA.
PROSA_ES = re.compile(
    r"\b(que|para|con|los|las|una|del|por|como|cuando|pero|porque|desde|entre|sobre|esto|esta|"
    r"hace|dice|sin|más|así|cada|todo|toda|ningún|ninguna|acá|allá|arriba|abajo)\b", re.I)
MIN_MARCADORES = 3


def docstrings_en_castellano() -> list[str]:
    """`archivo.py::nombre` de cada `def`/`class` de `scripts/` + `tools/` con docstring en
    castellano.

    La convención de `CLAUDE.md` dice **«archivos, nombres de funciones, docstrings y comentarios
    NUEVOS en inglés»** y hasta el 2026-08-28 el ratchet miraba **sólo los nombres**: dos tercios de
    la regla no los vigilaba nadie. Medido ese día: **299 de 407** docstrings en castellano (73 %).

    Ese 73 % es deuda **anterior** a la convención y la regla dice *sin retrofit*, así que el techo
    nace ahí. Lo que este ratchet impide es que **crezca**, que es el único daño que sigue
    ocurriendo — mismo argumento que el de nombres."""
    out = []
    for arbol in ("scripts", "tools"):
        for p in sorted((RAIZ / arbol).glob("*.py")):
            arbol_ast = ast.parse(p.read_text(encoding="utf-8"))
            for n in ast.walk(arbol_ast):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    d = ast.get_docstring(n)
                    if d and len(PROSA_ES.findall(d)) >= MIN_MARCADORES:
                        out.append(f"{p.name}::{n.name}")
    return sorted(out)


def sin_docstring() -> list[str]:
    """`archivo.py::nombre` de cada `def`/`class` de `scripts/` + `tools/` **sin docstring**.

    Este repo escribe docstrings largos y razonados: son un contrato de facto, y el frente C de la
    pasada `/auditar` audita justamente que se cumplan. Una función sin docstring queda fuera de esa
    auditoría por construcción. Medido el 2026-08-28: **69 de 476** (14 %)."""
    out = []
    for arbol in ("scripts", "tools"):
        for p in sorted((RAIZ / arbol).glob("*.py")):
            arbol_ast = ast.parse(p.read_text(encoding="utf-8"))
            for n in ast.walk(arbol_ast):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if not ast.get_docstring(n):
                        out.append(f"{p.name}::{n.name}")
    return sorted(out)


def simbolos_en_castellano() -> list[str]:
    """`archivo.py::nombre` de cada `def`/`class` de `scripts/` + `tools/` con nombre en castellano."""
    out = []
    for arbol in ("scripts", "tools"):
        for p in sorted((RAIZ / arbol).glob("*.py")):
            arbol_ast = ast.parse(p.read_text(encoding="utf-8"))
            for n in ast.walk(arbol_ast):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                        and _es_castellano(n.name):
                    out.append(f"{p.name}::{n.name}")
    return sorted(out)


def test_el_marcador_de_castellano_no_es_un_substring_ciego():
    """El detector compara SEGMENTOS, no substrings. Con `in nombre` a secas, `de` marcaría `dedup`
    y `nota` marcaría `annotate`: un detector con falsos positivos a esa escala se apaga en la
    primera corrida, y entonces la regla vuelve a no tener red."""
    assert _es_castellano("notas_del_slug") and _es_castellano("puertas_abiertas")
    assert not _es_castellano("dedup"), "`de` es un segmento, no un substring"
    assert not _es_castellano("annotate") and not _es_castellano("render")
    assert not _es_castellano("to_record") and not _es_castellano("source_hash")


def test_no_crecen_los_simbolos_en_castellano():
    """Ratchet: sólo puede bajar. Un símbolo NUEVO en castellano pone esto en rojo; los 30 heredados
    son deuda declarada y no se renombran (sin retrofit — renombrarlos rompería marcas `@inv` y los
    punteros de `docs/trazabilidad.md` por nada)."""
    hallados = simbolos_en_castellano()
    ratchet = yaml.safe_load(RATCHET.read_text(encoding="utf-8")) or {}
    techo = ratchet.get("techo", 0)
    nuevos = [s for s in hallados if s.split("::")[1] not in set(ratchet.get("conocidos") or [])]
    assert not nuevos, (
        "símbolos NUEVOS con nombre en castellano (la convención pide inglés para lo nuevo; "
        f"`CLAUDE.md` § Convención de idioma):\n  " + "\n  ".join(nuevos))
    assert len(hallados) <= techo, (
        f"{len(hallados)} símbolos en castellano (techo {techo}):\n  " + "\n  ".join(hallados))
    if len(hallados) < techo:
        import warnings
        warnings.warn(f"idioma bajó a {len(hallados)} (techo {techo}): actualizá `techo` en "
                      f"{RATCHET.name}", stacklevel=2)


# ── las otras dos mitades de la convención (AUD-193/194) ────────────────────────────────────────


def _techo(campo: str) -> int:
    return int((yaml.safe_load(RATCHET.read_text(encoding="utf-8")) or {})[campo])


def test_no_crecen_los_docstrings_en_castellano():
    """La convención nombra **«docstrings y comentarios»** y hasta hoy sólo se vigilaban los nombres.

    El techo es deuda anterior al 2026-08-24 y la regla dice *sin retrofit*: lo que este ratchet
    impide es que crezca. ⚠ Es heurística declarada —≥3 palabras funcionales del castellano—, así
    que puede tener falsos positivos; lo que mide es el **delta**."""
    hoy = docstrings_en_castellano()
    techo = _techo("docstrings_castellano")
    assert len(hoy) <= techo, (
        f"{len(hoy)} docstrings en castellano > techo {techo}: la convención dice que los NUEVOS van "
        f"en inglés. Si el crecimiento es legítimo (renombre, refactor), bajá el techo y decilo en "
        f"el commit.\n  " + "\n  ".join(hoy[-8:]))
    if len(hoy) < techo:
        print(f"✅ bajó a {len(hoy)} — actualizá `docstrings_castellano` en {RATCHET.name}")


def test_ninguna_funcion_nueva_sin_docstring():
    """Este repo escribe docstrings largos y razonados: son un contrato de facto, y el frente C de
    `/auditar` audita justamente que se cumplan. Una función sin docstring queda **fuera de esa
    auditoría por construcción**."""
    hoy = sin_docstring()
    techo = _techo("sin_docstring")
    assert len(hoy) <= techo, (
        f"{len(hoy)} funciones/clases sin docstring > techo {techo}: en este repo el docstring es "
        f"el contrato de la función, y sin él nadie puede auditar que se cumpla.\n  "
        + "\n  ".join(hoy[-8:]))
    if len(hoy) < techo:
        print(f"✅ bajó a {len(hoy)} — actualizá `sin_docstring` en {RATCHET.name}")
