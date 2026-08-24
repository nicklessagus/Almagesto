"""Golden/snapshot del lint sobre un corpus SINTÉTICO CONGELADO (seed fija, N chico) — plan §3.5.

Un golden fija el COMPORTAMIENTO COMPLETO del lint (títulos, conteos, mensajes) en un solo diff en
vez de veintipico asserts sueltos: un cambio no intencional entre versiones del framework —un
mensaje reescrito, una categoría que deja de imprimirse, un conteo que se corre por un
doble-conteo o un early-exit— se ve en el diff del commit; un cambio INTENCIONAL se regenera con
`UPDATE_GOLDEN=1` y el diff del golden viaja como changelog medido (ver el comando abajo).

Normalización (plan §3.5, requisito (a) — "sacar lo que legítimamente varía"): la salida cruda del
lint tiene DOS fuentes de variación que NO son comportamiento:

  1. **La fecha del encabezado** (`# Lint de la bóveda — {dt.date.today()}`).
  2. ~~El orden de las líneas de "Notas huérfanas"~~ — **ya no**. Era el único orden no
     determinista medido (se sembró el mismo corpus y se corrió `lint.main()` en 5 subprocesos con
     `PYTHONHASHSEED` distinto: sólo esa sección cambiaba de orden). La causa estaba en `lint.py`:
     `orphans` iteraba un `dict` construido sobre un `set` de strings (`names = {basename(p)[:-3]
     for p in files}`), y el orden de un `set` de `str` depende del hash que Python randomiza por
     proceso. Se **arregló en la fuente** (`orphans` sale `sorted`) en vez de seguir normalizándolo
     acá: ordenar las líneas antes de comparar dejaba al golden ciego para el único defecto que
     había que ver — el test tapaba su propio hallazgo. Hoy el golden compara el orden CRUDO.

El resto de las secciones sale de recorrer `files = glob.glob(...)` — sin `sorted()` en
`note_files()`, pero estable DENTRO de una corrida porque el árbol no se re-siembra entre la
escritura del golden y su lectura.

**Regenerar** (requisito (b) del plan — un golden que se edita a mano no se mantiene):

    UPDATE_GOLDEN=1 python -m pytest tests/poblada/test_golden.py -m poblada -q
    python -m pytest tests/poblada/test_golden.py -m poblada -q     # confirma que compara en verde
"""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

import pytest

import lib_config as cfg
import lint

pytestmark = pytest.mark.poblada

THIS_DIR = Path(__file__).resolve().parent
GOLDEN_DIR = THIS_DIR / "golden"
GOLDEN_FILE = GOLDEN_DIR / "lint_seed42.md"

_FECHA_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Corpus congelado del golden: chico (siembra+lint ≈0.28s medido — rápido a propósito, un golden
# lento no se corre) + una anomalía de CADA categoría que el generador soporta (`SOPORTADAS` en
# generador.py) — así el golden ejercita bloqueantes (huerfanas, thesis_colgantes,
# disputes_colgantes) y backlog (no_sintetizado, cobertura_citas, cabecera_no_estampable,
# fulltext_ilegible) en una sola corrida, no sólo el caso limpio.
GOLDEN_KWARGS: dict = dict(
    n_papers=60, n_stars=3, n_concepts=15, seed=42,
    anomalias={"huerfanas": 2, "thesis_colgantes": 2, "disputes_colgantes": 2,
               "no_sintetizado": 2, "cobertura_citas": 2,
               "cabecera_no_estampable": 2, "fulltext_ilegible": 2},
)

# Las 12 categorías BLOQUEANTES (mismo criterio que `n_block` en lint.py), por un substring
# distintivo de su título — duplicado localmente (no importado de test_generador.py, que otra ola
# está escribiendo) a propósito: este archivo no depende de la forma interna de otro.
BLOQUEANTES = (
    "Wikilinks rotos", "Frontmatter no parseable", "Papers RETRACTADOS", "Notas huérfanas",
    "Contradicciones ground-truth", "masa inconsistente con m", "thesis_links sin página destino",
    "disputes: ref de una posición", "disputes mal formadas", "disputes en el schema viejo",
    "Juicio de triage en build", "`role` fuera del vocabulario",
)


def _normalizar(reporte: str) -> str:
    """Ver docstring del módulo: sólo la fecha → `<FECHA>`.

    Antes esto además **ordenaba** las líneas de cada sección, para neutralizar el orden inestable
    de "Notas huérfanas". Eso dejaba al golden ciego justamente para el único no-determinismo
    medido: el test que tenía que ver el problema lo estaba tapando. La causa se arregló en
    `lint.py` (`orphans` sale `sorted`), así que el golden ya compara el orden CRUDO y cualquier
    no-determinismo nuevo lo rompe, que es lo que un golden existe para hacer (INV-43)."""
    return _FECHA_RE.sub("<FECHA>", reporte)


def _correr_golden(sembrar) -> tuple[int, str, str]:
    """(rc, reporte_crudo, reporte_normalizado) — siembra el corpus congelado y corre el lint."""
    sembrar(**GOLDEN_KWARGS)
    rc = lint.main()
    crudo = (cfg.ROOT / "outputs" / f"lint-{dt.date.today().isoformat()}.md").read_text(
        encoding="utf-8")
    return rc, crudo, _normalizar(crudo)


def _conteo(reporte: str, contiene: str) -> int:
    """Conteo `(N)` de la primera sección `## ...` cuyo título contiene `contiene`."""
    for line in reporte.splitlines():
        if line.startswith("## ") and contiene in line:
            m = re.search(r"\((\d+)\)\s*$", line)
            assert m, f"título sin conteo: {line!r}"
            return int(m.group(1))
    raise AssertionError(f"categoría no encontrada en el reporte: {contiene!r}")


def test_lint_golden_semilla_fija(sembrar):
    """Fija el reporte COMPLETO (títulos + conteos + mensajes) del lint sobre el corpus congelado
    contra `golden/lint_seed42.md`. Caza cualquier cambio de comportamiento no anunciado entre
    versiones del lint que un assert puntual por categoría no ve porque no lo está mirando: un
    mensaje reescrito, una categoría que cambia de bloqueante a WARN, un conteo que se corre por
    un doble-conteo o un early-exit, una categoría que desaparece calladamente. Regenerar:
    `UPDATE_GOLDEN=1 python -m pytest tests/poblada/test_golden.py -m poblada -q`."""
    _, _, normalizado = _correr_golden(sembrar)

    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        GOLDEN_FILE.write_text(normalizado, encoding="utf-8")
        pytest.skip(
            f"UPDATE_GOLDEN=1: {GOLDEN_FILE} regenerado — correlo de nuevo SIN la env var para "
            "confirmar que compara en verde, y commiteá el diff del golden como changelog medido")

    assert GOLDEN_FILE.exists(), (
        f"falta {GOLDEN_FILE} — generalo con `UPDATE_GOLDEN=1 python -m pytest "
        "tests/poblada/test_golden.py -m poblada -q`")
    esperado = GOLDEN_FILE.read_text(encoding="utf-8")
    assert normalizado == esperado, (
        "el lint cambió de comportamiento sobre el corpus congelado (seed=42) respecto del golden "
        "commiteado — si el cambio es INTENCIONAL, regenerar con `UPDATE_GOLDEN=1 python -m "
        "pytest tests/poblada/test_golden.py -m poblada -q` y commitear el diff del golden como "
        "changelog medido; si no, es una regresión de comportamiento")


def test_golden_exit_code(sembrar):
    """El corpus congelado da SIEMPRE exit 1 con exactamente 6 hallazgos bloqueantes: 2
    `huerfanas` (→ Notas huérfanas) + 2 `thesis_colgantes` (→ thesis_links sin página destino) + 2
    `disputes_colgantes` (→ disputes: ref de una posición sin paper destino). Las otras cuatro
    anomalías sembradas (no_sintetizado, cobertura_citas, cabecera_no_estampable,
    fulltext_ilegible) son backlog, no bloqueante — si alguna se filtrara a una categoría
    bloqueante (o viceversa), este test lo separa del golden de contenido: un exit code que
    coincide "por casualidad" con un reporte que cambió de forma no debería poder pasar.  @inv INV-37"""
    rc, crudo, _ = _correr_golden(sembrar)
    assert rc == 1
    n_block = sum(_conteo(crudo, titulo) for titulo in BLOQUEANTES)
    assert n_block == 6, f"n_block={n_block}, esperado 6 (2 huerfanas+2 thesis+2 disputes)"
    assert _conteo(crudo, "Notas huérfanas") == 2
    assert _conteo(crudo, "thesis_links sin página destino") == 2
    assert _conteo(crudo, "disputes: ref de una posición") == 2


def test_reporte_lista_todas_las_categorias(sembrar):
    """El reporte SIEMPRE imprime TODAS las categorías, con `(0)` incluido cuando no hay
    hallazgos — que una desaparezca silenciosamente (por un `return` temprano, una excepción
    tragada, un `if items:` agregado por error alrededor del `## título`) es el bug "dejó de
    mirar", indistinguible de "no hay nada que reportar" salvo por esto. Medido en esta sesión:
    el reporte trae 30 secciones `## ...` (no 29 — el conteo que documenta el CLAUDE.md de este
    repo, `lint.py:986-1017`, quedó desactualizado respecto del código actual; este test cuenta
    directo del reporte generado, no de esa cifra). Corre sobre el corpus congelado para no
    sembrar un corpus aparte.

    Desde el issue 0.3 son **31** (entró `⛔ No evaluado`) desde el 1.2, **33** (los dos
    carriles del ancla: `plantilla vieja`, bloqueante, y `pares vencidos`, cuya severidad depende
    de `--cierre`), desde el 2.1, **34** (el detector del registro pre-D-28) desde el 2.2, **35** (cadena incompleta)
    desde el 3.1/3.3, **37** (lista de papers
    desactualizada, recorte de lectura sin declarar) desde el 5.1, **38** (identidad duplicada)
    y desde el 6.3, **40** (prosa que cita una fuente retractada, con y sin marcar). Esa categoría es además la ÚNICA
    excepción legítima a la regla de arriba — cuando un chequeo no se puede evaluar, su sección se
    suprime en vez de mostrar un `(0)` que se leería como veredicto, y la supresión queda
    **nombrada** ahí. O sea que la sección no desaparece en silencio, que es lo que este test
    protege; el `(0)` inventado y la desaparición muda son el mismo bug visto de los dos lados.  @inv INV-41"""
    _, crudo, _ = _correr_golden(sembrar)
    titulos = [l for l in crudo.splitlines() if l.startswith("## ")]
    assert len(titulos) == 47, (
        f"el reporte trae {len(titulos)} categorías, se esperaban 47 — alguna sección dejó de "
        "imprimirse (o se agregó una nueva sin actualizar este test)")
    no_eval = [t for t in titulos if "No evaluado" in t]
    assert no_eval and no_eval[0].endswith("(0)"), (
        "sobre el corpus congelado (con git y objective sano) nada debería quedar sin evaluar")
    con_cero = [t for t in titulos if re.search(r"\(0\)\s*$", t)]
    assert con_cero, "ninguna categoría con (0) — el corpus congelado debería tener varias limpias"
