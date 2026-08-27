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
