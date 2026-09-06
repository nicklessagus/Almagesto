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
    _nota_larga("2010CJ"); _nota_larga("2001HKO")
    # ⛔ #402 — `hueco` es un STRING en el schema que recibe todo extractor (`"hueco":""` en el
    # bloque de salida del prompt). El doble de este test lo escribía como LISTA, y el productor
    # real escribe un string: `as_list` sobre un escalar devuelve `[]`, el bucle nunca corría, y
    # la pantalla publicaba `0 · sobre N extracciones` — un falso limpio con población declarada
    # (D-43), sobre 206 extracciones de una bóveda real. Regla de método 2, textual: el doble con
    # distinto contrato que la función real escondía el bug en la diferencia.
    _extraccion("ica", "2010CJ", hueco=motivo)
    _extraccion("ica", "2001HKO", hueco="")
    filas, poblacion = pr.scope_requests()
    assert poblacion == 2, "declara sobre cuántas extracciones miró (INV-40)"
    assert filas == [("2010CJ", "ica", motivo)]
    # la lista se TOLERA al leer (nunca se normaliza al escribir): mismo resultado
    _extraccion("ica", "2010CJ", hueco=[motivo])
    assert pr.scope_requests()[0] == [("2010CJ", "ica", motivo)]


def _nota_larga(bib: str, unidad: str = "pagina") -> None:
    """La nota de paper que declara una fuente LARGA (#80): es lo que define la población."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / f"{bib}.md").write_text(
        f"---\nbibcode: {bib}\nunidad_cita: {unidad}\nalcance: caps. 1-3\n---\n\n## Abstract\n\nx\n",
        encoding="utf-8")


def test_el_pedido_de_alcance_lo_hace_el_extractor_donde_el_PROMPT_le_dice(toy_vault):
    """#402 — el prompt manda «extraé lo que hay dentro y decilo en `salvedades`», y la herramienta
    leía SÓLO `hueco`. Se leen los dos: el `hueco` (string o lista) y toda salvedad en PROSA — una
    estructurada (`tipo` de `SALVEDAD_TIPOS`) es un hecho decidible sobre el artefacto que chequea
    el cosechador, no un pedido a una persona."""
    _nota_larga("2010CJ")
    _extraccion("ica", "2010CJ", hueco="", salvedades=[
        "el §11.2 del manual queda fuera del alcance y el tema lo necesita",
        {"tipo": "pdf_paginas", "n": 300},
        {"nota": "ampliar a §3", "motivo": "sin tipo: es prosa"}])
    filas, _p = pr.scope_requests()
    textos = [m for _b, _s, m in filas]
    assert "el §11.2 del manual queda fuera del alcance y el tema lo necesita" in textos
    assert "ampliar a §3" in textos, "el mapa SIN `tipo` es prosa, y se lee su `nota`"
    assert not any("pdf_paginas" in m or "300" in m for m in textos), \
        "la salvedad ESTRUCTURADA es un hecho chequeable, no un pedido"
    # las dos guardas de forma: el mapa CON `tipo` no cuenta aunque traiga `nota` (es estructurado),
    # y el mapa sin `tipo` pero con `nota` vacía tampoco (no hay texto que proponer)
    _extraccion("ica", "2010CJ", hueco="", salvedades=[
        {"tipo": "txt_pierde", "cadena": "√", "nota": "esto NO es un pedido"},
        {"nota": "   "}, {"motivo": "sin nota no hay texto"}])
    assert pr.scope_requests()[0] == [], pr.scope_requests()[0]


def test_el_hueco_de_una_fuente_CORTA_no_es_un_pedido_de_alcance(toy_vault):
    """#402 — la categoría es «ampliar el `alcance` de una fuente LARGA»: el `hueco` de un paper de
    once páginas es un campo de propósito general que el prompt pide llenar siempre, no un pedido
    de ampliar nada. Contarlo listaría todas las extracciones de la bóveda como propuestas — el
    ruido que hace que una categoría se deje de leer. Población = notas con `unidad_cita` ≠ línea."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020Corto.md").write_text(
        "---\nbibcode: 2020Corto\n---\n\n## Abstract\n\nx\n", encoding="utf-8")
    _extraccion("ica", "2020Corto", hueco="no pude confirmar el valor de la Tabla 3")
    _extraccion("ica", "2021SinNota", hueco="tampoco")
    _nota_larga("2010CJ", unidad="linea")
    _extraccion("ica", "2010CJ", hueco="una fuente que se cita por línea no es larga")
    filas, poblacion = pr.scope_requests()
    assert (filas, poblacion) == ([], 0), "sin fuentes largas la población es CERO, y se dice"
    assert pr.is_long_source("2020Corto") is False and pr.is_long_source("2021SinNota") is False
    _nota_larga("2010CJ", unidad="seccion")
    assert pr.is_long_source("2010CJ") and pr.scope_requests()[1] == 1


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
