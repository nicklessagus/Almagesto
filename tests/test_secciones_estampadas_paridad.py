"""Los TRES consumidores del recorte «prosa vs metadata estampada» usan la MISMA declaración.

Red #2 aplicada: si N módulos prometen la misma forma, se prueba **una vez parametrizada**, no con
prosa en N docstrings. Hasta 1.38.1 cada módulo tenía su propia copia y las copias **diferían**:
`make_notes.SECCIONES_MAQUINA` no incluía `## Planetas` ni `## Verificación de citas`, y
`lib_blocks` no tenía ninguna — por eso `pairs_of` devolvía 178 pares donde había 68.

El modo de falla que esto cierra no es estético: un artefacto que se mide a sí mismo siempre da el
resultado que su propia existencia produce.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

import lib_blocks as lb
import lib_config as cfg
import lint
import make_notes as mn

NOTA = """---
name: X
---
# X

## Resumen
El período es 4.3 d [[2020Prosa....1..1P]].

## Papers (1 · 0 sintetizados en esta ficha)

| Bibcode | Año |
|---|---|
| [[2020Estampado.1..1E]] | 2020 |

## Métodos aplicados a esta estrella (1 método(s) · 1 aplicación(es))

| Método | Paper | Año |
|---|---|---|
| `gp` | [[2020Estampado.1..1E]] | 2020 |
"""


@pytest.mark.parametrize("modulo, attr", [(lint, "SECCIONES_ESTAMPADAS"),
                                          (mn, "SECCIONES_MAQUINA")])
def test_la_lista_es_la_misma_en_todos_los_consumidores(modulo, attr):
    assert getattr(modulo, attr) is cfg.SECCIONES_ESTAMPADAS, (
        f"{modulo.__name__}.{attr} tiene su propia copia: es exactamente la divergencia que "
        "produjo el bug (dos listas distintas para el mismo recorte)")


@pytest.mark.parametrize("recorte", [lint.solo_prosa, mn._prosa, cfg.solo_prosa])
def test_el_recorte_saca_las_secciones_estampadas_y_deja_la_prosa(recorte):
    prosa = recorte(NOTA)
    assert "2020Prosa....1..1P" in prosa, "la afirmación escrita a mano tiene que sobrevivir"
    assert "2020Estampado.1..1E" not in prosa, "una fila estampada no es prosa"


def test_pairs_of_no_fabrica_pares_desde_las_secciones_estampadas():
    """El fan-out de `verify-citations` es el consumidor donde esto más cuesta: cada par de más es
    un subagente leyendo un `.txt` para verificar una fila de tabla que nadie escribió — y para un
    paper sin extraer, un `.txt` que ni existe."""
    bibs = {p.bibcode for p in lb.pairs_of(NOTA)}
    assert bibs == {"2020Prosa....1..1P"}, bibs
