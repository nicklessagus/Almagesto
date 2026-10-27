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
    filas, poblacion, _f = pr.scope_requests()
    assert poblacion == 2, "declara sobre cuántas extracciones miró (INV-40)"
    # ⛔ #435 — el motivo va VERBATIM y el alcance vigente viaja en su propia columna: la firma de
    # esta categoría es el `alcance` de `themes.yaml` (texto libre), así que el cruce NO es decidible
    # y lo único honesto es poner el alcance al lado para que se decida de un vistazo.
    assert filas == [("2010CJ", "ica", motivo, "alcance vigente: NO DECLARADO")]
    # la lista se TOLERA al leer (nunca se normaliza al escribir): mismo resultado
    _extraccion("ica", "2010CJ", hueco=[motivo])
    assert pr.scope_requests()[0] == [("2010CJ", "ica", motivo,
                                       "alcance vigente: NO DECLARADO")]


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
    filas, _p, _f = pr.scope_requests()
    textos = [m for _b, _s, m, _c in filas]
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
    filas, poblacion, _f = pr.scope_requests()
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
    filas, poblacion, _f = pr.refutations()
    assert poblacion == 2
    assert filas == [("2010CJ", "ica", "habla de componentes de un tensor, no de ICA", "")]
    assert pr.refutations("ica")[0] == filas, "acotar al sujeto que refuta lo conserva"
    assert pr.refutations("otro") == ([], 2, []), "acotar por sujeto no cambia la población mirada"


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
    filas, poblacion, _f = pr.empty_axis_cells()
    assert poblacion == 1
    assert filas == [("ica", "ruido", "[[2001HKO]]", "")]

    # el corte es hasta el próximo `## `: lo que viene después no es el inventario
    (d / "otro.md").write_text(
        "---\ntags: [concept]\n---\n\n## Inventario por eje\n\n"
        "| Eje | Paper | Dice | Método |\n|---|---|---|---|\n"
        "| ruido | [[2001HKO]] | dice algo | GLS |\n\n## Huecos\n\n"
        "| falta | [[2010CJ]] | | |\n", encoding="utf-8")
    filas, poblacion, _f = pr.empty_axis_cells("otro")
    assert (filas, poblacion) == ([], 1), "la tabla de otra sección no entra"
    assert _f == [], ("#435 — esta categoría se cierra SOLA: lee la nota, así que la celda llena "
                      "desaparece. Es el contraejemplo de qué forma tiene una propuesta cerrable")

    # la prosa y las filas sin celdas suficientes no son propuestas
    (d / "prosa.md").write_text(
        "---\ntags: [concept]\n---\n\n## Inventario por eje\n\n"
        "Sin desacuerdos todavía.\n\n| Eje | Paper |\n|---|---|\n| ruido | |\n",
        encoding="utf-8")
    assert pr.empty_axis_cells("prosa") == ([], 1, [])

    # una nota SIN inventario no entra en la población: es lo que hace legible el «0»
    (d / "sin-inventario.md").write_text("---\ntags: [concept]\n---\n\n## Síntesis\n\nx\n",
                                         encoding="utf-8")
    assert pr.empty_axis_cells()[1] == 3, "las tres CON inventario, no las cuatro notas"

    # el ENCABEZADO con una columna sin título no es una celda vacía del inventario
    (d / "cabecera.md").write_text(
        "---\ntags: [concept]\n---\n\n## Inventario por eje\n\n"
        "| Eje | Paper | Dice | |\n|---|---|---|---|\n"
        "| ruido | [[2001HKO]] | dice algo | GLS |\n", encoding="utf-8")
    assert pr.empty_axis_cells("cabecera") == ([], 1, [])

    # y la PROSA con barras tampoco: sin el filtro de fila, un renglón así se leía como tabla
    (d / "barras.md").write_text(
        "---\ntags: [concept]\n---\n\n## Inventario por eje\n\n"
        "Falta el eje ruido | en [[2001HKO]] |  | y en otras\n", encoding="utf-8")
    assert pr.empty_axis_cells("barras") == ([], 1, [])


# ── #435 · una propuesta FIRMADA tiene que dejar de estar pendiente ──────────────────────────────

def _refuta(bib: str, sujeto: str, motivo: str = "polisemia — no habla de ese sujeto") -> None:
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / f"{bib}.md").write_text(
        f"---\nbibcode: {bib}\nvistas:\n  - sujeto: {sujeto}\n    tipo: star\n"
        f"    refuta: [{sujeto}]\n    motivo: {motivo}\n---\n\n## Abstract\n\nx\n",
        encoding="utf-8")


def _firmar_drop_core(slug: str, bib: str, motivo: str) -> None:
    """Lo que escribe `triage.py <slug> --drop-core <bibcode> --reason` (carril `sujeto`, #112)."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path(slug).write_text(
        f"decisiones:\n  {bib}:\n    decision: descartado\n    origen: sujeto\n"
        f"    motivo: {motivo}\n    fecha: 2026-09-10\n", encoding="utf-8")


def test_la_refutacion_FIRMADA_deja_de_estar_pendiente(toy_vault, capsys):
    """⛔ #435 — la firma de esta categoría aterriza en `decisiones` del registro del sujeto y el
    barrido no la consultaba: `grep -nE "load_registro|decisiones" scripts/proposals.py` daba CERO.
    Como el artefacto que lee es versionado y por #311 **no regenerable** (`refuta` no se saca sin
    re-pagar la lectura, y `harvest_views` mergea add-only), la propuesta no tenía NINGUNA salida:
    medido en una bóveda real, 60 de 62 eran permanentes.

    El caso reproducible: se firmó el `--drop-core` que la propia propuesta imprime como `→`, el
    comando hizo lo suyo, y `proposals.py` seguía listando la misma propuesta con el mismo `→`."""
    _refuta("2012ApJS", "GJ 581")
    (cfg.CONFIG).mkdir(parents=True, exist_ok=True)
    (cfg.CONFIG / "stars.yaml").write_text("GJ 581:\n  slug: gj_581\n", encoding="utf-8")   # forma real (#435)
    cfg.load_stars.cache_clear() if hasattr(cfg.load_stars, "cache_clear") else None
    filas, poblacion, firmadas = pr.refutations()
    assert poblacion == 1 and len(filas) == 1 and firmadas == [], "sin firmar, está pendiente"
    _firmar_drop_core("gj_581", "2012ApJS", "la estrella aparece una sola vez, de segunda mano")
    filas, _p, firmadas = pr.refutations()
    assert filas == [], "firmada: sale de la cola de lo pendiente"
    assert len(firmadas) == 1 and "gj_581" in firmadas[0][2] and "segunda mano" in firmadas[0][2]
    # AUD-207 — queda VISIBLE y aparte, con el motivo; no se silencia
    pr.report()
    salida = capsys.readouterr().out
    assert "ya FIRMADA" in salida and "segunda mano" in salida
    assert "firma: cruzada" in salida, "la categoría declara que su firma SÍ se cruza"


def test_acotar_por_slug_resuelve_el_NOMBRE_del_reclamo(toy_vault):
    """El reclamo lleva el NOMBRE y el `--slug` del CLI es un slug: sin resolver el nombre, acotar a
    `gj_581` no encontraba la refutación de `GJ 581` —la misma brecha nombre↔slug que hacía que la
    firma no se cruzara— y el reporte acotado salía en cero sobre una propuesta que existe."""
    _refuta("2012ApJS", "GJ 581")
    (cfg.CONFIG).mkdir(parents=True, exist_ok=True)
    (cfg.CONFIG / "stars.yaml").write_text("GJ 581:\n  slug: gj_581\n", encoding="utf-8")   # forma real (#435)
    assert len(pr.refutations("gj_581")[0]) == 1, "por slug"
    assert len(pr.refutations("GJ 581")[0]) == 1, "y por nombre, como lo escribe la vista"
    assert pr.refutations("otra_estrella")[0] == []


def test_el_reclamo_cuyo_SUJETO_no_resuelve_sigue_pendiente(toy_vault):
    """El cruce necesita `cfg.subject_slug` porque el reclamo lleva el NOMBRE (`refuta: ["GJ 581"]`)
    y el registro va por slug (`gj_581`): ese salto es el que hacía que la firma no se encontrara.
    ⛔ Un nombre que no resuelve a ningún sujeto queda **pendiente**: un reclamo irresoluble no es
    un reclamo firmado, y darlo por firmado silenciaría la propuesta sin que nadie decidiera."""
    _refuta("2012ApJS", "Sujeto Que No Existe")
    filas, _p, firmadas = pr.refutations()
    assert len(filas) == 1 and firmadas == []


def test_el_reporte_declara_LOS_TRES_estados_de_la_firma(toy_vault, capsys):
    """D-43 aplicado a la superficie de propuestas: las dos formas de no poder cerrarse piden cosas
    OPUESTAS —una se arregla cruzando, la otra sólo se puede declarar— y mostrarlas iguales es lo
    que dejó 60 de 62 propuestas permanentes."""
    assert pr.main([]) == 0
    salida = capsys.readouterr().out
    for estado in (pr.FIRMA_CRUZADA, pr.FIRMA_NO_CRUZABLE, pr.FIRMA_SE_CIERRA_SOLA):
        assert f"firma: {estado}" in salida, estado
    assert "TEXTO LIBRE" in salida, "el porqué del no-cruzable, no sólo la etiqueta"


def test_el_reporte_declara_lo_que_NO_puede_barrer(toy_vault, capsys):
    """D-43 — un eje descubierto en el paso 3b vive en la conversación y no toca el disco. Decir «0
    propuestas» sin nombrar esa ausencia convertiría un hueco conocido en un veredicto."""
    #  @inv INV-147
    assert pr.main([]) == 0
    salida = capsys.readouterr().out
    assert "NO BARRIBLE" in salida and "ejes descubiertos" in salida
    assert "NO es la deuda del lint" in salida, "propuesta y deuda son dos colas distintas"


def _nota_con_segunda_mano(bib: str, autor: str, anio: int, duenos: list,
                           stars: str = "[GJ 1]") -> None:
    """Una nota de paper cuya vista marca valores de SEGUNDA MANO, uno por dueño (#590)."""
    filas = "\n".join(f"| P_rot | 4{i}.3 d | L{i} | — | {d} |" for i, d in enumerate(duenos))
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / f"{bib}.md").write_text(
        f"---\nbibcode: {bib}\nfirst_author: {autor}\nyear: {anio}\nstars: {stars}\n---\n\n## Abstract\n\nx\n\n"
        f"## Vista — GJ 1\n\n| Qué | Valor | Localizador | Régimen | Segunda mano |\n"
        f"|---|---|---|---|---|\n{filas}\n", encoding="utf-8")


def test_el_dueno_ausente_de_un_valor_de_segunda_mano_se_propone_rankeado(toy_vault):
    """#590 — la vista dice «el número es de B» y nadie mira si B está en la bóveda. El dueño
    ausente se propone, rankeado por cuántos valores dependen de él; el presente no; la celda que
    no nombra a nadie es NO EVALUABLE (D-43), no un dueño faltante."""
    _nota_con_segunda_mano("2020A", "Díaz, R. F.", 2020,
                           ["van Leeuwen (2007)", "van Leeuwen (2007)", "Lovis et al. 2011",
                            "Tabla 1 compila de la literatura", "—"])
    _nota_con_segunda_mano("2011L", "Lovis, C.", 2011, ["Sousa et al. (2008)"])
    # «van Leeuwen» con nota: la clave es el ÚLTIMO token del apellido, de los dos lados
    filas, poblacion, firmadas, no_eval = pr.missing_owners()
    assert poblacion == 5 and no_eval == 1 and firmadas == []
    assert [(a, b) for a, b, _m, _c in filas] == [
        ("van Leeuwen (2007)", "2 valor(es) en 1 paper(s)"),
        ("Sousa et al. (2008)", "1 valor(es) en 1 paper(s)")], "Lovis 2011 está: no se propone"
    _nota_con_segunda_mano("2007VL", "van Leeuwen, F.", 2007, [])
    assert [a for a, *_ in pr.missing_owners()[0]] == ["Sousa et al. (2008)"], \
        "se cierra sola cuando la nota del dueño existe"


def test_el_dueno_por_BIBCODE_el_slug_y_la_cola_DECLARADA(toy_vault, monkeypatch):
    """#590 — la celda que linkea `[[bibcode]]` se resuelve por la NOTA (no por apellido); `<slug>`
    acota a los papers que reclaman el sujeto; y lo que queda fuera del tope se DECLARA en una fila
    final, nunca se calla."""
    (cfg.CONFIG / "stars.yaml").write_text("GJ 1:\n  slug: gj_1\nGJ 2:\n  slug: gj_2\n",
                                           encoding="utf-8")
    _nota_con_segunda_mano("2020A", "Díaz, R. F.", 2020,
                           ["[[2011A&A...999A...1X]]", "[[2020A]] (la propia)", "Udry et al. 2007"])
    _nota_con_segunda_mano("2021B", "Pepe, F.", 2021, ["Mayor et al. 2009"], stars="[GJ 2]")
    filas = pr.missing_owners()[0]
    assert {a for a, *_ in filas} == {"[[2011A&A...999A...1X]]", "Udry et al. 2007",
                                      "Mayor et al. 2009"}, "el bibcode con nota no se propone"
    assert {a for a, *_ in pr.missing_owners("gj_2")[0]} == {"Mayor et al. 2009"}
    monkeypatch.setattr(pr, "MISSING_OWNERS_TOP", 1)
    filas = pr.missing_owners()[0]
    assert len(filas) == 2 and filas[-1][:2] == ("… y 2 dueño(s) más", "2 valor(es)")


def test_el_preprint_citado_casa_con_el_publicado_SOLO_si_la_celda_lo_marca(toy_vault):
    """#590 — «Bonfils et al. (2011, submitted)» es 2013A&A...549A.109B: con la marca de preprint
    se acepta el año +1/+2, y el año de un alias de `versions[]` identifica la nota. Sin marca no:
    `Bonfils 2012` pelado sigue ausente (límite declarado), no se esconde detrás del 2013."""
    _nota_con_segunda_mano("2013B", "Bonfils, X.", 2013, [])
    _nota_con_segunda_mano("2009M", "Mayor, M.", 2009, [])
    (cfg.PAPERS / "2009M.md").write_text((cfg.PAPERS / "2009M.md").read_text(encoding="utf-8")
                                         .replace("stars:", "versions: [2008arXiv0810.2045M]\nstars:"),
                                         encoding="utf-8")
    _nota_con_segunda_mano("2014T", "Tuomi, M.", 2014,
                           ["Bonfils et al. (2011, submitted)", "Bonfils et al. (2012)",
                            "Mayor et al. (2008)"])
    assert [a for a, *_ in pr.missing_owners()[0]] == ["Bonfils et al. (2012)"]


def _txt(bib: str, texto: str) -> None:
    (cfg.FULLTEXT / "gj_1").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "gj_1" / f"{bib}.txt").write_text(texto, encoding="utf-8")


def test_el_valor_que_el_texto_del_dueno_no_muestra_se_propone_REDONDEO_tolerado(toy_vault):
    """#590 mitad 2 — el dueño B está en la bóveda: el número de A se busca en el `.txt` de B,
    redondeado a la precisión con que A lo cita (3.24 por 3.2357 no es hallazgo). Lo que no aparece
    se PROPONE —abrí el PDF—, nunca se acusa (#318). Sin cantidad específica, sin `.txt` de B o con
    B == A: no evaluable."""
    _nota_con_segunda_mano("2012D", "Dumusque, X.", 2012, [])
    _nota_con_segunda_mano("2007U", "Udry, S.", 2007, [])
    _txt("2012D", "We find P = 3.2357 d and a semi-amplitude of 0.51 m/s.")
    cfg.PAPERS.joinpath("2015P.md").write_text(
        "---\nbibcode: 2015P\nfirst_author: Pepe, F.\nyear: 2015\nstars: [GJ 1]\n---\n\n## Vista — GJ 1\n\n"
        "| Qué | Valor | Localizador | Régimen | Segunda mano |\n|---|---|---|---|---|\n"
        "| P | 3.24 d | L1 | — | Dumusque et al. 2012 |\n"
        "| K | 0.77 m/s | L2 | — | Dumusque et al. 2012 |\n"
        "| edad | vieja | L3 | — | Dumusque et al. 2012 |\n"
        "| e | 0.19 | L4 | — | Udry et al. (2007) |\n"
        "| Teff | 5172.5 K | L5 | — | Pepe et al. (2015) |\n"
        "| M | 0.83 Msun | L6 | — | Mayor et al. 2009 |\n", encoding="utf-8")
    filas, poblacion, firmadas, no_eval = pr.unconfirmed_second_hand()
    assert (poblacion, no_eval, firmadas) == (4, 2, []), "el dueño AUSENTE es de la otra categoría"
    assert [(b, a, v) for b, a, v, _q in filas] == [("2012D", "2015P", "0.77 m/s")]


def test_la_cola_de_valores_sin_confirmar_se_DECLARA(toy_vault, monkeypatch):
    """#590 — pasado el tope, lo que queda afuera se cuenta en una fila final, nunca se calla."""
    test_el_valor_que_el_texto_del_dueno_no_muestra_se_propone_REDONDEO_tolerado(toy_vault)
    monkeypatch.setattr(pr, "MISSING_OWNERS_TOP", 0)
    assert pr.unconfirmed_second_hand()[0] == [("… y 1 valor(es) más", "", "", "")]


def test_el_numero_de_B_se_encuentra_con_5_decimales_TRUNCADO_y_entre_corchetes(toy_vault):
    """#590 (devuelto por la instancia) — tres falsos avisos con el número literal en B: el redondeo
    topeaba en 4 decimales (`8.46321`), `quantities` aplicado a B borraba `[0.67, 2.97]` como
    referencia y el `5.366` de `P [days] 5.366`, y A puede TRUNCAR (5.36 por 5.366)."""
    _nota_con_segunda_mano("2020P", "Plavchan, P.", 2020, [])
    _txt("2020P", "P [days] 5.366 and P = 8.46321 d; the interval is [0.67, 2.97].")
    cfg.PAPERS.joinpath("2021A.md").write_text(
        "---\nbibcode: 2021A\nfirst_author: Martioli, E.\nyear: 2021\nstars: [GJ 1]\n---\n\n"
        "## Vista — GJ 1\n\n| Qué | Valor | Localizador | Régimen | Segunda mano |\n|---|---|---|---|---|\n"
        "| P | 8.46321 d | L1 | — | Plavchan et al. 2020 |\n| P2 | 5.36 d | L2 | — | Plavchan et al. 2020 |\n"
        "| e | 2.97 | L3 | — | Plavchan et al. 2020 |\n| K | 5.38 m/s | L4 | — | Plavchan et al. 2020 |\n",
        encoding="utf-8")
    filas, poblacion, _f, _n = pr.unconfirmed_second_hand()
    assert poblacion == 4 and [v for _b, _a, v, _q in filas] == ["5.38 m/s"], \
        "5.38 no es redondeo ni truncado de 5.366: ése sí se propone"
