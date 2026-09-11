"""Los números del lint que la doc publica, atados al código en TIER 0 (#438).

POR QUÉ ACÁ Y NO EN `poblada`. Los dos artefactos que **toda categoría nueva del lint mueve** —el
golden del reporte y los conteos que publican `tests/README.md` y `docs/contrato.md`— sólo los
miraba el tier deseleccionado, y `pytest.ini` lo deselecciona a propósito (`-m "not poblada"`:
convierte `pytest tests/` de 8 min en 2 s de selección). Resultado medido en la tanda #433-#436:
tier 0 **2890 passed** en verde y el job `poblada` del CI en **failure a los 11 min 5 s**, por tres
categorías nuevas que el golden no tenía y un `132` que ya era `135`. Cada tanda que agrega una
categoría rompía el CI hasta que alguien se acordaba de regenerar dos archivos.

⛔ **Y el costo era evitable, no inherente:** la lista de categorías es **independiente del corpus**
(el reporte emite todas, aunque estén en 0). Medido: `lint.collect()` da **135 · 41 · 4** sobre el
vault del template, sobre un `toy_vault` y sobre el corpus sembrado — los tres idénticos. Así que lo
que se puede decidir sin sembrar nada se decide en 2 s, antes del commit.

⛔ **El chequeo se MOVIÓ, no se copió** (red 10): en `tests/poblada/test_conteos_exactos.py` quedan
sólo los números que dependen de módulos de ese tier (las anomalías que el generador sabe sembrar y
el ruido declarado del corpus limpio). Acá viven los que salen de `scripts/` solo.

Lo que **sigue** en `poblada` es el golden COMPLETO: mensajes, conteos por categoría y poblaciones
dependen del corpus sembrado, y ésa es la mitad que caza una regresión de comportamiento. Acá sólo
se chequea que **el título de cada categoría esté** en el golden, que es la mitad decidible.
"""
from __future__ import annotations

import re
from pathlib import Path

import lint

RAIZ = Path(__file__).resolve().parent.parent
GOLDEN = RAIZ / "tests" / "poblada" / "golden" / "lint_seed42.md"


def _conteos() -> tuple:
    """`(categorías, bloqueantes, bloqueantes+cierre)` — los tres números, del código."""
    cats = lint.collect().categorias
    n_bloq = sum(1 for c in cats if c.severidad == lint.SEV_BLOQUEANTE)
    n_cierre = sum(1 for c in cats if c.severidad == lint.SEV_CIERRE)
    return len(cats), n_bloq, n_bloq + n_cierre


def test_los_conteos_de_categorias_que_la_doc_publica_salen_del_codigo(toy_vault):
    """#438 — los tres números del lint publicados en la doc, en tier 0.

    `docs/contrato.md` (INV-41) afirma estar atado a un test y hasta #145 no lo estaba: publicaba
    «48 categorías, 22 bloqueantes, 23 con --cierre» con 64/27/29 en el código. Una fila que dice
    salir del código y no sale es **peor** que una sin número: se lee como verificada. Lo que agrega
    #438 es sólo *cuándo* se entera el operador — antes del commit en vez de 11 min después del
    push."""
    n_cat, n_bloq, n_con_cierre = _conteos()
    readme = (RAIZ / "tests" / "README.md").read_text(encoding="utf-8")
    assert f"**{n_cat} categorías**" in readme, \
        f"el lint tiene {n_cat} categorías y `tests/README.md` dice otra cosa"
    # el denominador del desbalance (`**cero en las N**`, con la negrita abarcando la frase)
    assert f"cero en las {n_cat}**" in readme, \
        f"`tests/README.md` publica el denominador viejo: hoy el lint tiene {n_cat} categorías"
    # ⚠ del triple se chequea ACÁ la primera cifra —la única que sale de `scripts/`—; las otras dos
    # (anomalías del generador, ruido declarado) las sigue chequeando `poblada`, que es quien las
    # conoce. Partido en la coma, así cada número lo afirma UN solo test.
    m = re.search(r"\((\d+) categorías, (\d+) anomalías, (\d+) de ruido declarado\)", readme)
    assert m, "`tests/README.md` ya no publica el triple `(N categorías, M anomalías, K de ruido …)`"
    assert int(m.group(1)) == n_cat, \
        f"el triple de `tests/README.md` publica {m.group(1)} categorías y el código tiene {n_cat}"
    contrato = (RAIZ / "docs" / "contrato.md").read_text(encoding="utf-8")
    assert f"({n_cat} categorías, {n_bloq} bloqueantes, {n_con_cierre} con `--cierre`)" in contrato, (
        f"INV-41 publica un conteo que ya no es el del código: hoy son {n_cat} categorías, "
        f"{n_bloq} bloqueantes y {n_con_cierre} con `--cierre`")


def test_el_golden_del_lint_TIENE_todas_las_categorias(toy_vault):
    """#438 — la mitad del golden que se puede decidir sin sembrar el corpus: que esté cada TÍTULO.

    El golden es el reporte completo sobre el corpus congelado, y el reporte emite **todas** las
    categorías (las vacías con `(0)`), así que una categoría nueva es una línea nueva ahí — y eso se
    ve leyendo el archivo. Medido: de las 135 categorías, las que NO aparecían en el golden después
    de regenerarlo son **0**.

    ⚠ Lo que este test NO puede ver, y por eso el golden completo sigue en `poblada`: un mensaje
    reescrito, un conteo corrido por un doble-conteo, una población mal declarada. Esas dependen del
    corpus sembrado. Acá sólo se caza «agregué una categoría y no regeneré el golden», que es el
    modo de falla medido."""
    assert GOLDEN.exists(), f"falta {GOLDEN}"
    golden = GOLDEN.read_text(encoding="utf-8")
    faltan = [c.titulo for c in lint.collect().categorias if c.titulo not in golden]
    assert faltan == [], (
        f"{len(faltan)} categoría(s) del lint NO están en el golden — regeneralo con "
        f"`UPDATE_GOLDEN=1 python -m pytest tests/poblada/test_golden.py -m poblada -q` y actualizá "
        f"los conteos que publica la doc:\n  " + "\n  ".join(faltan))
