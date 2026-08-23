"""Conteos EXACTOS del lint sobre corpus poblado (§3.2 del plan de la 7ª auditoría) — la capa que
cierra el agujero de la bóveda vacía: ahí TODA categoría da `(0)` tanto si el chequeo funciona como
si dejó de mirar, y un test que sólo afirma `(1)` con una nota sembrada a mano no distingue "pasa"
de "ni miró" (ver el bug real que motiva esto: el espejo #70 comparaba `len(planets)` — un doble
conteo invisible con una sola nota).

**La forma canónica**: `sembrar_corpus(anomalias={cat: K})` entre notas limpias ⇒ el lint reporta
EXACTAMENTE `(K)`, y los stems listados son EXACTAMENTE los del `Censo` — ni uno de más (doble
conteo / falso positivo) ni uno de menos (early-exit / filtro que se comió uno). Cubre las 7
categorías que el generador soporta hoy (`generador.SOPORTADAS`): huérfanas, thesis_links
colgantes, disputes con `ref` colgante, extraído-pero-no-sintetizado, cobertura de citas, cabecera
no estampable y fulltext ilegible.

Cada test de una sola categoría hace además el assert que el plan marca como "de los más valiosos y
más fáciles de olvidar": que sembrar ESA categoría no mueve el conteo de las OTRAS 6 soportadas
(`_assert_otras_categorias_en_cero`) — contaminación entre categorías. Y `_categoria` (abajo) exige
que ningún stem se repita DENTRO de una categoría — la firma de un doble conteo (dos caminos de
código reportando la misma nota), que un test que sólo mira el número `(K)` no vería si, por
casualidad, un duplicado compensa un faltante.

El test grande (`test_siete_anomalias_juntas...`) siembra las 7 a la vez entre ~900 notas —la
escala real que el plan pide como forma canónica— y cierra el trío que sólo aparece combinado y a
escala: contaminación cruzada, doble conteo, y exit code MIXTO (bloqueante + backlog conviviendo en
el mismo corpus tiene que dar exit 1, no promediarse).

No se tocan `generador.py`/`conftest.py`/`test_generador.py` (otra gente depende de esas firmas);
los helpers de lectura del reporte se reimplementan acá (mismos que `test_generador.py`, que no es
un módulo pensado para importarse desde otro archivo de test).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

import lib_config as cfg
import lint

pytestmark = pytest.mark.poblada


# ── lectura del reporte (NO stdout — la última línea es la RUTA del reporte, que vive bajo el
# tmpdir de pytest cuyo nombre incluye el del test: un assert de substring contra stdout puede
# matchear el PATH en vez del contenido; ver tests/README.md). ──────────────────────────────────

def _run_lint_reporte() -> tuple[int, str]:
    rc = lint.main()
    reporte = (cfg.ROOT / "outputs" / f"lint-{dt.date.today().isoformat()}.md").read_text(
        encoding="utf-8")
    return rc, reporte


def _categoria(reporte: str, contiene: str) -> tuple[int, list[str]]:
    """(conteo, stems) de la categoría cuyo título contiene `contiene`. Además de exigir que el
    título declare tantas líneas como hay listadas, exige que NINGÚN stem se repita dentro de la
    categoría: un duplicado es la firma de un doble conteo (dos caminos de código reportando la
    misma nota), y a la escala de este archivo (K de hasta 26, corpus de hasta 900 notas) un
    duplicado que compensa un faltante pasaría desapercibido si sólo se mirara el número `(K)`."""
    lines = reporte.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## ") and contiene in l), None)
    assert start is not None, f"categoría no encontrada en el reporte: {contiene!r}"
    m = re.search(r"\((\d+)\)\s*$", lines[start])
    assert m, f"título sin conteo: {lines[start]!r}"
    n = int(m.group(1))
    stems = []
    for l in lines[start + 1:]:
        if l.startswith("## "):
            break
        if l.startswith("- "):
            stems.append(l[2:].split(" → ", 1)[0].strip())
    assert len(stems) == n, f"{contiene!r}: título dice {n} pero hay {len(stems)} líneas listadas"
    assert len(stems) == len(set(stems)), (
        f"{contiene!r}: hay un stem repetido dentro de la categoría → doble conteo: {stems}")
    return n, stems


# Categoría del censo (`generador.SOPORTADAS`) → substring distintivo del título en el reporte del
# lint (los mismos substrings que ya usa `test_generador.py`, validados contra el reporte real).
_CATEGORIAS_SOPORTADAS = {
    "huerfanas": "Notas huérfanas",
    "thesis_colgantes": "thesis_links sin página destino",
    "disputes_colgantes": "disputes: ref de una posición",
    "no_sintetizado": "Extraído pero no sintetizado",
    "cobertura_citas": "Cobertura:",
    "cabecera_no_estampable": "Cabecera no estampable",
    "fulltext_ilegible": "Fulltext ilegible",
}

# huérfanas / thesis_colgantes / disputes_colgantes están en `n_block` de lint.py (bloqueantes →
# exit 1); las otras cuatro son backlog (no bloquean, exit 0 si no hay nada más bloqueante).
_BLOQUEANTES_SOPORTADAS = {"huerfanas", "thesis_colgantes", "disputes_colgantes"}


def _assert_otras_categorias_en_cero(reporte: str, excepto: str) -> None:
    """Contaminación entre categorías: sembrar SÓLO `excepto` no debe mover el conteo de ninguna
    de las otras 6 categorías soportadas. Es el assert que el plan de la 7ª auditoría marca como
    "de los más valiosos y más fáciles de olvidar" — sin él, un `continue` faltante que hace caer
    una nota anómala en el balde equivocado pasaría con el conteo de LA categoría sembrada igual
    de exacto (el bug aparece en la categoría VECINA, que nadie miraba)."""
    for cat, titulo in _CATEGORIAS_SOPORTADAS.items():
        if cat == excepto:
            continue
        n, _ = _categoria(reporte, titulo)
        assert n == 0, (
            f"sembrar sólo {excepto!r} movió también {cat!r} ({titulo!r}): {n} hallazgo(s) — "
            "contaminación entre categorías")


# ── el corpus de SESIÓN (900 notas, sin anomalías) también tiene que dar cero en las 4 backlog ──
# `test_generador.py::test_corpus_limpio_da_lint_exit_0` sólo recorre las 12 BLOQUEANTES; deja sin
# ejercitar, en el caso LIMPIO, las 4 categorías backlog que este archivo sí prueba con anomalías
# (no_sintetizado/cobertura_citas/cabecera_no_estampable/fulltext_ilegible). Sin este test, una
# regresión que hace aparecer falsos positivos ahí sobre un corpus sano no la vería nadie: los tests
# de anomalía de este archivo esperan `n == K > 0`, así que un `K+1` no se distinguiría de un +1
# perdido entre el ruido — hace falta el caso SIN anomalías para que "cero" signifique cero.
def test_corpus_limpio_de_sesion_da_cero_tambien_en_las_backlog_no_bloqueantes(boveda_poblada):
    """Caza falsos positivos de las 4 categorías backlog soportadas sobre un corpus SANO (900
    notas, sin anomalías) — el complemento del smoke test de `test_generador.py`, que sólo mira las
    12 bloqueantes. Reusa el árbol de sesión (no siembra de nuevo): sólo corre el lint una vez más
    sobre lo que `arbol_poblado` ya construyó."""
    assert boveda_poblada.censo.anomalias == {}          # el árbol de sesión no lleva anomalías
    rc, reporte = _run_lint_reporte()
    assert rc == 0, reporte[:4000]
    for cat, titulo in _CATEGORIAS_SOPORTADAS.items():
        n, _ = _categoria(reporte, titulo)
        assert n == 0, f"{cat!r} ({titulo!r}): corpus limpio de 900 notas con hallazgos: {n}"


# ── una categoría por test: conteo exacto + stems exactos + no contamina a las otras 6 ─────────

def test_huerfanas_exacto_no_contamina_otras_categorias(sembrar):
    """Caza un huérfano de más (doble conteo) o de menos (early-exit/filtro que se come uno) entre
    500 papers/40 conceptos, y que sembrar huérfanas no le suma/resta nada a las otras 6 categorías.
    `n_concepts` deliberadamente chico frente a `n_papers`: el reparto de citas paper→concepto
    (`concept_citations`) da UNA cita por concepto citable en una sola pasada sobre los papers
    extraídos (~24% de `n_papers`) y para en cuanto se queda sin papers — con más conceptos que
    papers-para-citar de sobra, concepts SIN anomalía quedan sin cita y contaminan `cobertura_citas`
    (medido al calibrar este archivo: reproducible con `n_concepts=275, n_papers=250`)."""
    _, censo = sembrar(n_papers=500, n_stars=3, n_concepts=15, seed=101,
                       anomalias={"huerfanas": 25})
    rc, reporte = _run_lint_reporte()
    assert rc == 1
    n, stems = _categoria(reporte, "Notas huérfanas")
    assert n == 25
    assert sorted(stems) == sorted(censo.anomalias["huerfanas"])
    _assert_otras_categorias_en_cero(reporte, "huerfanas")


def test_thesis_colgantes_exacto_no_contamina_otras_categorias(sembrar):
    """Caza un `thesis_links` colgante mal contado (típico: el barrido agrupa por tag y pierde uno
    al mergear duplicados) entre 300 papers, y contaminación hacia las otras 6 categorías."""
    _, censo = sembrar(n_papers=300, n_stars=3, n_concepts=15, seed=106,
                       anomalias={"thesis_colgantes": 16})
    rc, reporte = _run_lint_reporte()
    assert rc == 1
    n, stems = _categoria(reporte, "thesis_links sin página destino")
    assert n == 16
    assert sorted(stems) == sorted(censo.anomalias["thesis_colgantes"])
    _assert_otras_categorias_en_cero(reporte, "thesis_colgantes")


def test_disputes_colgantes_exacto_no_contamina_otras_categorias(sembrar):
    """Caza una `ref` de disputa colgante mal contada entre 34 conceptos + 450 papers, y que
    sembrar disputas colgantes no dispara "disputes mal formadas" ni "schema viejo" (categorías
    hermanas de disputas que NO están en `_CATEGORIAS_SOPORTADAS` pero sí en BLOQUEANTES) — se
    verifica indirectamente: si alguna se encendiera, `rc == 1` seguiría siendo cierto pero el
    conteo bloqueante total ya no sería atribuible sólo a esta categoría, así que se chequea
    también que el título de las hermanas exista con conteo 0."""
    _, censo = sembrar(n_papers=450, n_stars=3, n_concepts=15, seed=107,
                       anomalias={"disputes_colgantes": 19})
    rc, reporte = _run_lint_reporte()
    assert rc == 1
    n, stems = _categoria(reporte, "disputes: ref de una posición")
    assert n == 19
    assert sorted(stems) == sorted(censo.anomalias["disputes_colgantes"])
    _assert_otras_categorias_en_cero(reporte, "disputes_colgantes")
    n_mal, _ = _categoria(reporte, "disputes mal formadas")
    assert n_mal == 0
    n_viejo, _ = _categoria(reporte, "disputes en el schema viejo")
    assert n_viejo == 0


def test_no_sintetizado_exacto_no_contamina_otras_categorias(sembrar):
    """Caza un "extraído pero no sintetizado" mal contado entre 350 papers (backlog, NO bloqueante:
    confirma que el conteo no se cuela a `n_block` y voltea el exit code), y contaminación hacia
    las otras 6 — en particular hacia `cobertura_citas`, que también depende de qué cita qué."""
    _, censo = sembrar(n_papers=350, n_stars=3, n_concepts=15, seed=102,
                       anomalias={"no_sintetizado": 22})
    rc, reporte = _run_lint_reporte()
    assert rc == 0
    n, stems = _categoria(reporte, "Extraído pero no sintetizado")
    assert n == 22
    assert sorted(stems) == sorted(censo.anomalias["no_sintetizado"])
    _assert_otras_categorias_en_cero(reporte, "no_sintetizado")


def test_cobertura_citas_exacto_no_contamina_otras_categorias(sembrar):
    """Caza una "cobertura de citas" mal contada entre 33 conceptos (backlog), y que excluir los
    conceptos anómalos del reparto de citas (`citable_concepts`) no deja a ningún paper extraído
    sin dónde citarse — lo que dispararía `no_sintetizado` como efecto colateral: el assert de
    contaminación es el que lo cazaría."""
    _, censo = sembrar(n_papers=260, n_stars=3, n_concepts=15, seed=103,
                       anomalias={"cobertura_citas": 18})
    rc, reporte = _run_lint_reporte()
    assert rc == 0
    n, stems = _categoria(reporte, "Cobertura:")
    assert n == 18
    assert sorted(stems) == sorted(censo.anomalias["cobertura_citas"])
    _assert_otras_categorias_en_cero(reporte, "cobertura_citas")


def test_cabecera_no_estampable_exacto_no_contamina_otras_categorias(sembrar):
    """Caza una "cabecera no estampable" mal contada cuando la anomalía MEZCLA estrellas y
    conceptos en el mismo censo (`K_header_stars = min(K, n_stars)` primero, el resto a conceptos)
    — un test que sólo sembrara conceptos no vería un bug que sólo afecta la rama de estrellas.
    Backlog, no bloqueante."""
    _, censo = sembrar(n_papers=250, n_stars=4, n_concepts=15, seed=104,
                       anomalias={"cabecera_no_estampable": 14})
    rc, reporte = _run_lint_reporte()
    assert rc == 0
    n, stems = _categoria(reporte, "Cabecera no estampable")
    assert n == 14
    assert sorted(stems) == sorted(censo.anomalias["cabecera_no_estampable"])
    n_estrellas = sum(1 for s in censo.anomalias["cabecera_no_estampable"] if s.startswith("star"))
    assert n_estrellas == 4                      # min(14, n_stars=4): las 4 estrellas + 10 conceptos
    assert n - n_estrellas == 10
    _assert_otras_categorias_en_cero(reporte, "cabecera_no_estampable")


def test_fulltext_ilegible_exacto_no_contamina_otras_categorias(sembrar):
    """Caza un fulltext ilegible mal contado entre 300 papers (74% legibles por diseño del
    generador — el caso normal, no el ilegible, es la mayoría), y contaminación hacia las otras 6.
    Backlog, no bloqueante."""
    _, censo = sembrar(n_papers=300, n_stars=3, n_concepts=15, seed=105,
                       anomalias={"fulltext_ilegible": 20})
    rc, reporte = _run_lint_reporte()
    assert rc == 0
    n, stems = _categoria(reporte, "Fulltext ilegible")
    assert n == 20
    # el reporte lista "raw/fulltext/<slug>/<stem>.txt", no el stem pelado — comparar por sufijo
    assert sorted(Path(s).stem for s in stems) == sorted(censo.anomalias["fulltext_ilegible"])
    _assert_otras_categorias_en_cero(reporte, "fulltext_ilegible")


# ── las 7 juntas, ~900 notas: la forma canónica del plan, con el trío que sólo aparece a escala ─

def test_siete_anomalias_juntas_a_900_notas_sin_contaminacion_ni_duplicados_y_exit_code_mixto(
        sembrar):
    """La forma canónica de este archivo: K anomalías sembradas entre ~900 notas limpias ⇒ el lint
    reporta EXACTAMENTE esas K, con los stems EXACTOS del censo — para las 7 categorías SOPORTADAS
    A LA VEZ, no una por una como en los tests de arriba. Caza tres modos de falla que sólo
    aparecen combinados y a escala real:

    (a) **contaminación cruzada**: sembrar 7 categorías a la vez (no 1) multiplica las chances de
        que un `continue`/`break` mal puesto haga caer una nota anómala en el balde equivocado —
        cada categoría exige tanto el conteo como el conjunto de stems EXACTOS, así que un stem
        que se filtró de una categoría a otra rompe la igualdad en AMBAS, no sólo en el número.
    (b) **doble conteo**: `_categoria` exige que ningún stem se repita dentro de su categoría — acá
        hay 7 categorías × cientos de notas candidatas, la superficie donde un doble conteo real
        (dos caminos de código reportando la misma nota) tiene más chances de aparecer que en un
        test de 3-5 notas.
    (c) **exit code MIXTO**: bloqueantes (huérfanas/thesis/disputes) y backlog (no_sintetizado/
        cobertura/cabecera/fulltext) conviviendo en el MISMO corpus deben dar exit 1 — manda el
        bloqueante, no se promedia con el backlog ni un bloqueante "diluido" entre más ruido de
        backlog pasa desapercibido.
    """
    # n_concepts deliberadamente chico frente a n_papers (ver el docstring de
    # `test_huerfanas_exacto_...`): el reparto de citas paper→concepto agota los papers extraídos
    # (~24% de 900 ≈ 216) antes de cubrir un total_concepts mayor a eso, y CUALQUIER concepto sin
    # anomalía que se quede sin cita ensucia `cobertura_citas` por encima de la K sembrada.
    n_papers, n_stars, n_concepts = 900, 4, 60
    anomalias = {
        "huerfanas": 24, "thesis_colgantes": 17, "disputes_colgantes": 21,
        "no_sintetizado": 26, "cobertura_citas": 19, "cabecera_no_estampable": 12,
        "fulltext_ilegible": 23,
    }
    _, censo = sembrar(n_papers=n_papers, n_stars=n_stars, n_concepts=n_concepts, seed=200,
                       anomalias=anomalias)
    rc, reporte = _run_lint_reporte()
    assert rc == 1, "hay bloqueantes (huérfanas/thesis/disputes) sembrados: el exit code debe ser 1"

    for cat, titulo in _CATEGORIAS_SOPORTADAS.items():
        n, stems = _categoria(reporte, titulo)
        esperado = censo.anomalias[cat]
        obtenido = sorted(Path(s).stem for s in stems) if cat == "fulltext_ilegible" \
            else sorted(stems)
        assert n == len(esperado) == anomalias[cat], (
            f"{cat}: se sembraron {len(esperado)}, el lint reportó {n}")
        assert obtenido == sorted(esperado), (
            f"{cat}: los stems reportados no coinciden con los sembrados — "
            f"de más: {sorted(set(obtenido) - set(esperado))}, "
            f"de menos: {sorted(set(esperado) - set(obtenido))}")

    # el bloqueante suma exactamente lo esperado dentro de `n_block` (huérfanas+thesis+disputes);
    # el resto de las categorías bloqueantes de lint.py (no sembradas acá) tienen que seguir en 0 —
    # si no, hay contaminación hacia una categoría bloqueante que este archivo no siembra.
    for titulo_hermano in ("Wikilinks rotos", "Frontmatter no parseable", "Papers RETRACTADOS",
                           "Contradicciones ground-truth", "masa inconsistente con m",
                           "disputes mal formadas", "disputes en el schema viejo",
                           "Juicio de triage en build", "`role` fuera del vocabulario"):
        n_hermano, _ = _categoria(reporte, titulo_hermano)
        assert n_hermano == 0, f"{titulo_hermano!r}: {n_hermano} — contaminación inesperada"
