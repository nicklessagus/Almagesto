"""Los sitios que cortan una sección anclan a comienzo de línea, no a `str.find` pelado.

Red #2 aplicada: cuatro módulos prometen la misma forma —«dame la sección que empieza en este
header»— y cada uno tenía su copia. Tres usaban `text.find(HEADER)` pelado, que agarra la mención
en prosa entre backticks (`` `## Inventario por eje` ``) **antes** que el header real, corta hasta
él y devuelve una sección vacía.

Medido sobre una ficha real (HD 40307, 2026-08-25): el inventario tenía **36 filas** y
`lint.inventario_sin_llenar` lo reportaba como *«el contraste 3b no dejó rastro»* — el detector de
#101 acusando justamente al paso que sí ocurrió. Un mapa que atribuye mal es peor que uno vacío.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

import lib_blocks as lb
import lib_config as cfg
import lint


# La forma que dispara el bug: la prosa apunta al lector a la propia sección, entre backticks.
FICHA = """---
name: X
---
# X

## Resumen
Tres papers no coinciden en $P_\\mathrm{rot}$. Valores en `## Inventario por eje`.

## Inventario por eje

| Eje | Paper | Dice | Método |
|---|---|---|---|
| $P_\\mathrm{rot}$ | [[2016Uno.....1..1D]] | 41,2 d | GLS |
| $P_\\mathrm{rot}$ | [[2017Dos.....2..2S]] | 36,5 d | promedio de proxies |

## Huecos
- Falta fotometría.
"""

NOTA_VERIF = """---
name: X
---
# X

## Resumen
El período es 4,3 d [[2009Tres....3..3M]]. El chequeo vive en `## Verificación de citas`.

## Verificación de citas (2026-08-25)

| # | Afirmación (extracto) | Fuente | Veredicto | Score | Evidencia | Ancla | Hash fuente | Condición |
|---|---|---|---|---|---|---|---|---|
| 1 | El período es 4,3 d | [[2009Tres....3..3M]] | soportada | — | "P = 4.3114 d" (L12) | aaaaaaaaaa | bbbbbbbbbb | — |
"""


@pytest.mark.parametrize("header,texto,esperado_linea", [
    ("## Inventario por eje", FICHA, "## Inventario por eje"),
    ("## Verificación de citas", NOTA_VERIF, "## Verificación de citas (2026-08-25)"),
])
def test_section_start_saltea_la_mencion_en_prosa(header, texto, esperado_linea):
    # @inv INV-98
    i = cfg.section_start(texto, header)
    assert i >= 0
    # arranca en comienzo de línea, y esa línea ES el header (con su sufijo, si tiene)
    assert i == 0 or texto[i - 1] == "\n"
    assert texto[i:].split("\n", 1)[0] == esperado_linea


def test_section_start_devuelve_menos_uno_si_no_esta():
    assert cfg.section_start("# X\n\n## Huecos\nnada\n", "## Inventario por eje") == -1


def test_section_start_no_confunde_una_mencion_suelta_con_la_seccion():
    solo_prosa = "# X\n\nValores en `## Inventario por eje`, que no existe.\n"
    assert cfg.section_start(solo_prosa, "## Inventario por eje") == -1


def test_inventario_lleno_no_se_reporta_como_plantilla():
    """El hallazgo medido: 36 filas reportadas como sección vacía (#101 acusando al paso que ocurrió)."""
    # @inv INV-97
    assert lint.inventario_sin_llenar(FICHA) is False


def test_inventario_vacio_sigue_detectandose():
    """La otra mitad del contrato: presente-y-vacío = saltado (la escotilla es BORRAR la sección)."""
    vacio = ("---\nname: X\n---\n# X\n\n## Resumen\nValores en `## Inventario por eje`.\n\n"
             "## Inventario por eje\n\n| Eje | Paper | Dice | Método |\n|---|---|---|---|\n"
             "|  |  |  |  |\n\n## Huecos\n- Falta todo.\n")
    assert lint.inventario_sin_llenar(vacio) is True


def test_inventario_borrado_es_la_escotilla_declarada_no_un_hallazgo():
    """Ausencia = declarado. Ni siquiera la mención en prosa debe fabricar la sección."""
    sin_seccion = "---\nname: X\n---\n# X\n\n## Resumen\nNo hay ejes en disputa (ver `## Inventario por eje`).\n"
    assert lint.inventario_sin_llenar(sin_seccion) is False


def test_bloque_de_verificacion_se_parsea_pese_a_la_mencion_en_prosa():
    filas = lb.parse_verif_table(NOTA_VERIF)
    assert filas is not None, "la mención en prosa hizo que el bloque real no se encontrara"
    assert len(filas) == 1
    assert filas[0].anchor == "aaaaaaaaaa"
    assert filas[0].source_hash == "bbbbbbbbbb"


# ── El `|` dentro de una celda (bug hermano: el corte de columnas) ────────────
#
# El fan-out de `verify-citations` junta varias citas textuales con ` | `, y una cita puede traer un
# `|` propio (una fila de tabla del paper). El generador lo escapa `\|` como manda markdown y el
# parser partía por `|` pelado: las columnas se corren y el **ancla** se lee de la celda equivocada.
# Medido (2026-08-25): 18 pares reportados «vencidos por edición» sin que nada se hubiera editado.

CAB = ("| # | Afirmación (extracto) | Fuente | Veredicto | Score | Evidencia | Ancla | Hash fuente | Condición |\n"
       "|---|---|---|---|---|---|---|---|---|\n")


def _nota(fila: str) -> str:
    return "---\nname: X\n---\n# X\n\n## Verificación de citas (2026-08-25)\n\n" + CAB + fila + "\n"


def test_pipe_escapado_en_una_celda_no_corre_las_columnas():
    # @inv INV-99
    fila = (r'| 1 | K_b = 1,97 m/s | [[2009Uno.....1..1M]] | soportada | — | '
            r'"K [m s−1] 1.97 ± 0.11 \| Nmeas 135" (L397) | aaaaaaaaaa | bbbbbbbbbb | '
            r'3 circulares \| 128 de 135 medidas |')
    filas = lb.parse_verif_table(_nota(fila))
    assert filas is not None and len(filas) == 1
    assert filas[0].anchor == "aaaaaaaaaa", f"columna corrida: leyó {filas[0].anchor!r} como ancla"
    assert filas[0].source_hash == "bbbbbbbbbb"
    # y el escape se deshace al leer: la celda vuelve con su `|` de verdad
    assert filas[0].condition == "3 circulares | 128 de 135 medidas"


def test_fila_con_mas_celdas_que_el_encabezado_no_se_lee_corrida():
    """Un `|` SIN escapar es una fila malformada: mejor par sin cubrir que ancla de otra columna.

    El fallo silencioso es el caro — el lint la contaba como verificada contra un ancla ajena.
    """
    fila = ('| 1 | claim | [[2009Uno.....1..1M]] | soportada | — | "a | b" (L1) | aaaaaaaaaa | bbbbbbbbbb | — |')
    filas = lb.parse_verif_table(_nota(fila))
    assert filas == [], "una fila con más celdas que el encabezado no se puede indexar por posición"
