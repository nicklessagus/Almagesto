"""proposals.py — la cola de PROPUESTAS, separada de la deuda (#328).

Qué protege este archivo, en una línea: **una propuesta que nadie lee se pierde**, y ésa es la
asimetría con la deuda —que persiste en el reporte hasta que se cierra—. El caso medido: el extractor
de un libro de 824 páginas pidió ampliar el `alcance` («el cap. 3 es Contrasts y el cap. 6 es
FastICA/negentropía, los dos fuera»), el pedido quedó en el campo `hueco` de uno de 43 JSON, y lo vio
alguien de casualidad.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import proposals as pr  # noqa: E402
import lib_config as cfg  # noqa: E402


def _extraccion(slug: str, bib: str, **campos):
    (cfg.EXTRACCION / slug).mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / slug / f"{bib}.json").write_text(
        json.dumps({"bibcode": bib, **campos}), encoding="utf-8")


def test_el_pedido_de_ampliar_el_alcance_sale_CON_SU_MOTIVO(toy_vault):
    """#241/#328 — el framework prohíbe ampliar el alcance solo, así que el pedido no tiene otro
    lugar donde ir que el `hueco`. ⛔ La fila lleva el motivo **textual**: en seis meses sirve «el
    cap. 3 es Contrasts y el tema lo necesita», no «ampliación de alcance» (mismo argumento que el
    `--reason` obligatorio del triage)."""
    motivo = ("el capítulo de contrastes es el cap. 3 y FastICA/negentropía el cap. 6, los dos "
              "fuera del alcance declarado")
    _extraccion("ica", "2010CJ", hueco=[motivo])
    _extraccion("ica", "2001HKO")
    filas, poblacion = pr.scope_requests()
    assert poblacion == 2, "declara sobre cuántas extracciones miró (INV-40)"
    assert filas == [("2010CJ", "ica", motivo)]


def test_la_refutacion_se_PROPONE_con_el_comando_que_la_aplicaria(toy_vault):
    """#212 — el único canal que corre hacia atrás: la lectura retracta el reclamo que la trajo.
    El cosechador registra y **no aplica**, porque borrar curación en silencio sería un LLM editando
    lo que el usuario firmó."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2010CJ.md").write_text(
        "---\nbibcode: 2010CJ\nvistas:\n  - sujeto: ica\n    tipo: theme\n    refuta: [ica]\n"
        "    motivo: habla de componentes de un tensor, no de ICA\n---\n\n## Abstract\n\nx\n",
        encoding="utf-8")
    # ⚠ `vistas` en forma inválida (una lista de strings, D-58) no puede leerse como mapa: el lint
    # la bloquea, y acá se saltea en vez de reventar el barrido entero.
    (cfg.PAPERS / "2001HKO.md").write_text(
        "---\nbibcode: 2001HKO\nvistas:\n  - ica\n---\n\n## Abstract\n\nx\n",
        encoding="utf-8")
    filas, poblacion = pr.refutations()
    assert poblacion == 2
    assert filas == [("2010CJ", "ica", "habla de componentes de un tensor, no de ICA")]
    assert pr.refutations("ica")[0] == filas, "acotar al sujeto que refuta lo conserva"
    assert pr.refutations("otro") == ([], 2), "acotar por sujeto no cambia la población mirada"


def test_la_celda_vacia_del_inventario_ES_la_proxima_query(toy_vault):
    """#310 §4 — el inventario tiene una fila por paper para cada eje donde los papers NO coinciden,
    así que una celda vacía no es un defecto de formato: dice que a esa fuente no se le preguntó ese
    eje. El separador de encabezado y la fila de títulos no cuentan."""
    d = cfg.CONCEPTS / "methods"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ica.md").write_text(
        "---\ntags: [concept]\n---\n\n## Inventario por eje\n\n"
        "| Eje | Paper | Dice | Método |\n|---|---|---|---|\n"
        "| blanqueo | [[2010CJ]] | hace falta | SVD |\n"
        "| ruido | [[2001HKO]] | — | |\n\n## Huecos\n\nx\n", encoding="utf-8")
    filas, poblacion = pr.empty_axis_cells()
    assert poblacion == 1
    assert filas == [("ica", "ruido", "[[2001HKO]]")]

    # el corte es hasta el próximo `## `: lo que viene después no es el inventario
    (d / "otro.md").write_text(
        "---\ntags: [concept]\n---\n\n## Inventario por eje\n\n"
        "| Eje | Paper | Dice | Método |\n|---|---|---|---|\n"
        "| ruido | [[2001HKO]] | dice algo | GLS |\n\n## Huecos\n\n"
        "| falta | [[2010CJ]] | | |\n", encoding="utf-8")
    filas, poblacion = pr.empty_axis_cells("otro")
    assert (filas, poblacion) == ([], 1), "la tabla de otra sección no entra"

    # la prosa y las filas sin celdas suficientes no son propuestas
    (d / "prosa.md").write_text(
        "---\ntags: [concept]\n---\n\n## Inventario por eje\n\n"
        "Sin desacuerdos todavía.\n\n| Eje | Paper |\n|---|---|\n| ruido | |\n",
        encoding="utf-8")
    assert pr.empty_axis_cells("prosa") == ([], 1)

    # una nota SIN inventario no entra en la población: es lo que hace legible el «0»
    (d / "sin-inventario.md").write_text("---\ntags: [concept]\n---\n\n## Síntesis\n\nx\n",
                                         encoding="utf-8")
    assert pr.empty_axis_cells()[1] == 3, "las tres CON inventario, no las cuatro notas"

    # el ENCABEZADO con una columna sin título no es una celda vacía del inventario
    (d / "cabecera.md").write_text(
        "---\ntags: [concept]\n---\n\n## Inventario por eje\n\n"
        "| Eje | Paper | Dice | |\n|---|---|---|---|\n"
        "| ruido | [[2001HKO]] | dice algo | GLS |\n", encoding="utf-8")
    assert pr.empty_axis_cells("cabecera") == ([], 1)

    # y la PROSA con barras tampoco: sin el filtro de fila, un renglón así se leía como tabla
    (d / "barras.md").write_text(
        "---\ntags: [concept]\n---\n\n## Inventario por eje\n\n"
        "Falta el eje ruido | en [[2001HKO]] |  | y en otras\n", encoding="utf-8")
    assert pr.empty_axis_cells("barras") == ([], 1)


def test_el_reporte_declara_lo_que_NO_puede_barrer(toy_vault, capsys):
    """D-43 — un eje descubierto en el paso 3b vive en la conversación y no toca el disco. Decir «0
    propuestas» sin nombrar esa ausencia convertiría un hueco conocido en un veredicto."""
    #  @inv INV-147
    assert pr.main([]) == 0
    salida = capsys.readouterr().out
    assert "NO BARRIBLE" in salida and "ejes descubiertos" in salida
    assert "NO es la deuda del lint" in salida, "propuesta y deuda son dos colas distintas"
