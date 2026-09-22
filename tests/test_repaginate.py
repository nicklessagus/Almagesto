"""repaginate.py — el paquete de relectura y su escritor serial (#494).

Qué protege este archivo, en una línea: **la página del `.txt` es GUÍA de dónde abrir, no respuesta**
—regla decidida por el usuario el 2026-09-20—, y eso se impone por FORMA y no pidiéndolo: el
paquete y el resultado son schemas distintos, el escritor recomputa los items desde la extracción y
nunca lee el paquete, y la página confirmada viaja con un testigo local de la hoja.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import repaginate as rp  # noqa: E402
import lib_config as cfg  # noqa: E402

CITA = ("which requires the latent signals to be whitened before the model can be identified, "
        "and that condition is not the same as knowing the noise covariance")
OTRA = "the whitening step is described only in the appendix and not in the main text"
BIB = "2013Voss"


def _pdf(slug: str = "ica_ruido", bib: str = BIB) -> Path:
    (cfg.PDFS / slug).mkdir(parents=True, exist_ok=True)
    p = cfg.PDFS / slug / f"{bib}.pdf"
    p.write_bytes(b"%PDF-1.4\n" + bib.encode())
    return p


def _txt_paginado(slug: str = "ica_ruido", bib: str = BIB, cae_en: int = 2):
    """`.txt` con un form feed por página y el número IMPRESO en el pie (AUD-165)."""
    (cfg.FULLTEXT / slug).mkdir(parents=True, exist_ok=True)
    pags = [f"A&A proofs\n\n" + (f"prosa. {CITA}. fin" if i == cae_en else
                                  f"relleno propio de la hoja {i} con una frase larga y distinta") +
            f"\n\n{2008 + i}" for i in range(1, 5)]
    (cfg.FULLTEXT / slug / f"{bib}.txt").write_text("\f".join(pags), encoding="utf-8")


def _extraccion(slug: str = "ica_ruido", bib: str = BIB, marca: str = "_paginacion", **extra):
    d = {"bibcode": bib,
         "ground_truth": [{"que": "blanqueo", "valor": CITA, "linea": "p. 4"}],
         "salvedades": [f"Al leer, «{CITA}» (p. 3) quedó sin contrastar; y «{OTRA}» (p. 9)."],
         "ejes": {"identificabilidad": f"el paper lo afirma: «{CITA}» (pp. 3-4)"}}
    d.update(extra)
    if marca:
        d[marca] = {"reemplazo": "2026-09-11", "motivo": "versión del editor",
                    "pdf_sha": _sha(_pdf(slug, bib))}
    (cfg.EXTRACCION / slug).mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / slug / f"{bib}.json").write_text(json.dumps(d, ensure_ascii=False),
                                                       encoding="utf-8")
    return d


def _sha(pdf: Path) -> str:
    import lib_blocks as lb
    return lb.sha10(pdf.read_bytes())


def test_494_la_deuda_abierta_se_enumera_con_su_poblacion(toy_vault, capsys):
    """⛔ #494 — `--list` declara su población (INV-40): un `0` no distingue «miré todo y no hay
    deuda» de «no miré nada». Y `_repaginado` NO está: ahí la relectura ya cerró."""
    assert rp.main(["--list"]) == 0
    vacio = capsys.readouterr().out
    assert "0 extracción(es)" in vacio and "ninguna" in vacio, vacio
    _extraccion()
    _txt_paginado()
    assert rp.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "1 extracción(es)" in out and "repaginate.py 2013Voss" in out, out
    assert len(rp.pending()) == 1


def test_494_los_items_son_las_DOS_formas_con_su_ruta_exacta(toy_vault):
    """Las dos formas, porque los 64 de 75 localizadores que NO se pueden arreglar en la nota viven
    en la segunda: el `linea` de una fila de `ground_truth`, y el `(p. N)` adyacente a una cita
    dentro de cualquier campo de texto libre. ⚠ Un item por OCURRENCIA: una salvedad que cita dos
    páginas debe dos respuestas, y colapsarlas cerraría una en silencio."""
    d = _extraccion()
    ids = [it["id"] for it in rp.items(d)]
    assert ids == ["ground_truth[0].linea", "ejes.identificabilidad#1", "salvedades[0]#1",
                   "salvedades[0]#2"], ids
    porid = {it["id"]: it for it in rp.items(d)}
    assert porid["ground_truth[0].linea"]["linea"] == "p. 4"
    assert porid["salvedades[0]#1"]["linea"] == "p. 3"
    assert porid["salvedades[0]#2"]["linea"] == "p. 9"
    assert porid["ejes.identificabilidad#1"]["linea"] == "pp. 3-4"


def test_494_la_guia_sale_del_txt_y_declara_cuando_no_puede(toy_vault):
    """⛔ La guía dice dónde ABRIR y sale de `quote_pages`, la MISMA función con la que #492 juzga
    el localizador: si divergieran, la guía mandaría a una página que el chequeo no reconoce
    (#324). Y cuando no hay guía, el motivo lo dice (D-43): *no se pudo ubicar* no es *el
    localizador está mal*."""
    _extraccion()
    _txt_paginado()
    g = rp.guide({"cita": CITA, "valor": ""}, BIB)
    assert g["pagina"] == "2010" and g["indice"] == 2 and g["motivo"] is None, g
    sin = rp.guide({"cita": "una frase que el `.txt` no dice", "valor": ""}, BIB)
    assert sin["pagina"] is None and "índice degradado" in sin["motivo"]
    vacio = rp.guide({"cita": "", "valor": ""}, BIB)
    assert vacio["pagina"] is None and "no trae cita ni valor" in vacio["motivo"]
    # ⛔ y de una fila de `ground_truth` se busca la «cita» que el valor lleve ADENTRO: el valor
    # suele ser una paráfrasis del extractor —castellano, o LaTeX— que el `.txt` no puede ubicar
    # por construcción (medido: 26 de 33 filas de una fuente real no traen nada buscable)
    fila = {"cita": "", "valor": f"lo dice explícitamente: «{CITA}», y de ahí sale el supuesto"}
    assert rp.guide(fila, BIB)["pagina"] == "2010"
    assert rp.guide({"cita": "", "valor": "$M_\\star = 0.31 M_\\odot$"}, BIB)["pagina"] is None


def test_494_el_paquete_manda_abrir_el_PDF_y_la_guia_va_DECLARADA(toy_vault, tmp_path):
    """El prompt nombra el PDF, pega la convención del localizador y dice, item por item, que la
    guía es para abrir. El `_paquete.json` la lleva en su propia clave (`guia`), separada de lo que
    el lector tiene que devolver — que es la mitad estructural de la regla."""
    _extraccion()
    _txt_paginado()
    paquete = rp.write_round(BIB, tmp_path)
    assert paquete["items"][0]["guia"]["pagina"] == "2010"
    prompt = (tmp_path / "prompt.md").read_text(encoding="utf-8")
    assert f"pdfs/ica_ruido/{BIB}.pdf" in prompt
    assert "dice dónde ABRIR, no qué escribir" in prompt
    # #500 — la convención viaja, y desde 1.303.0 lo que pide es la página EN LA QUE ESTÁ, por
    # cualquiera de las dos numeraciones: el gate ya no dictamina cuál
    assert "la que muestra la hoja o el índice del PDF" in prompt, "la regla viaja al lector"
    assert "IMPRESA" not in prompt, "#500: la convención de numeración se retiró"
    assert "evidencia" in prompt and "pagina" in prompt
    # y el fence pide ESAS claves y ninguna otra: devolver el paquete tiene que rebotar
    assert '"guia"' not in json.dumps(rp.RESULT_SCHEMA)
    assert set(rp.RESULT_SCHEMA["items"][0]) == {"id", "pagina", "evidencia", "motivo"}


@pytest.mark.parametrize("caso", ["sin_deuda", "sin_pdf", "otro_sha"])
def test_494_el_paquete_REHUSA_en_vez_de_describir_otro_documento(toy_vault, tmp_path, caso):
    """Tres rehúses, cada uno cerrando una forma de releer el documento equivocado: sin deuda
    abierta no hay qué cerrar; sin PDF no hay qué leer (la relectura es del PDF, #205); y con un
    `pdf_sha` que no es el que registró la marca, el PDF se reemplazó OTRA VEZ y el paquete
    describiría un tercer documento. Nada se escribe."""
    _txt_paginado()
    if caso == "sin_deuda":
        _extraccion(marca="_repaginado")
    elif caso == "sin_pdf":
        _extraccion()
        (cfg.PDFS / "ica_ruido" / f"{BIB}.pdf").unlink()
    else:
        _extraccion()
        (cfg.PDFS / "ica_ruido" / f"{BIB}.pdf").write_bytes(b"%PDF-1.4\notro documento")
    with pytest.raises(rp.RoundError):
        rp.write_round(BIB, tmp_path)
    assert not (tmp_path / "_paquete.json").exists(), "un rehúse no deja artefacto a medias"


def _resultado(tmp_path: Path, filas: list, sha: str | None = None, bib: str = BIB,
               extraccion: str | None = None) -> Path:
    r = tmp_path / f"{bib}.json"
    r.write_text(json.dumps({"bibcode": bib, "extraccion": extraccion or f"ica_ruido/{bib}",
                             "items": filas,
                             "pdf_sha": sha if sha is not None
                             else _sha(cfg.PDFS / "ica_ruido" / f"{bib}.pdf")},
                            ensure_ascii=False), encoding="utf-8")
    return r


def _todos(tmp_path: Path, pagina="2010", evidencia="Received 3 March 2013; accepted") -> Path:
    d = _extraccion()
    _txt_paginado()
    filas = [{"id": it["id"], "pagina": pagina, "evidencia": evidencia, "motivo": ""}
             for it in rp.items(d)]
    return _resultado(tmp_path, filas)


def test_494_apply_escribe_la_pagina_RELEIDA_y_cierra_la_deuda(toy_vault, tmp_path):
    """⛔ #494 — la deuda se cierra escribiendo lo que el lector vio, y sólo cuando la extracción
    entera quedó releída: ahí `_paginacion` sale y entra `_repaginado` con su fecha y el `pdf_sha`
    del documento que se leyó."""
    res = _todos(tmp_path)
    r = rp.apply(BIB, res)
    assert r["cerrada"] and not r["rehusados"], r
    d = json.loads(r["extraccion"].read_text(encoding="utf-8"))
    assert d["ground_truth"][0]["linea"] == "p. 2010"
    assert "(p. 2010)" in d["salvedades"][0] and "_paginacion" not in d
    assert d["_repaginado"]["n"] == 4 and d["_repaginado"]["fuente"].startswith("relectura")


def test_494_la_ronda_incompleta_deja_la_deuda_ABIERTA_con_sus_pendientes(toy_vault, tmp_path):
    """Una deuda a medio cerrar es deuda: los ítems rehusados quedan nombrados en `pendientes` y la
    extracción pasa a `_repaginado_parcial`, que el lint sigue contando."""
    d = _extraccion()
    _txt_paginado()
    filas = [{"id": it["id"], "pagina": "2010", "evidencia": "Received 3 March 2013", "motivo": ""}
             for it in rp.items(d)]
    filas[0] = {"id": filas[0]["id"], "pagina": "2010", "evidencia": "", "motivo": ""}
    r = rp.apply(BIB, _resultado(tmp_path, filas))
    assert not r["cerrada"] and len(r["rehusados"]) == 1
    assert "sin `evidencia`" in r["rehusados"][0][1], r["rehusados"]
    nuevo = json.loads(r["extraccion"].read_text(encoding="utf-8"))
    assert nuevo["_repaginado_parcial"]["pendientes"] == ["ground_truth[0].linea"]
    assert nuevo["ground_truth"][0]["linea"] == "p. 4", "el ítem rehusado NO se escribe"


def test_494_el_hueco_se_DECLARA_y_NUNCA_se_rellena_con_la_guia(toy_vault, tmp_path):
    """⛔ La regla del issue, del lado del escritor: `pagina: null` se escribe `no hallado`, con la
    fecha de la relectura — aunque la guía tenga una página para ofrecer. Un hueco declarado es
    correcto; copiar la guía sin abrir el PDF es lo que la regla prohíbe."""
    d = _extraccion()
    _txt_paginado()
    assert rp.guide(rp.items(d)[0], BIB)["pagina"] == "2010", "la guía SÍ tenía una página"
    filas = [{"id": it["id"], "pagina": None, "evidencia": "",
              "motivo": "no encontré la frase en el PDF nuevo"} for it in rp.items(d)]
    r = rp.apply(BIB, _resultado(tmp_path, filas))
    nuevo = json.loads(r["extraccion"].read_text(encoding="utf-8"))
    assert nuevo["ground_truth"][0]["linea"].startswith("no hallado (relectura ")
    assert "2010" not in nuevo["ground_truth"][0]["linea"]
    assert r["cerrada"] and len(r["no_hallados"]) == 4


def test_494_la_GUIA_no_puede_llegar_al_linea_por_ningun_camino(toy_vault, tmp_path):
    """⛔ La mitad estructural de la regla: `apply` **no lee el paquete** —recomputa los ítems desde
    la extracción—, así que no existe camino de código por el que `guia` llegue a `linea`. La
    prueba es borrar el paquete y aplicar igual."""
    res = _todos(tmp_path)
    rp.write_round(BIB, tmp_path / "paq")
    (tmp_path / "paq" / "_paquete.json").unlink()
    r = rp.apply(BIB, res)
    assert r["cerrada"] and json.loads(
        r["extraccion"].read_text(encoding="utf-8"))["ground_truth"][0]["linea"] == "p. 2010"


@pytest.mark.parametrize("caso", ["otro_bibcode", "paquete_en_vez_de_resultado", "sha_distinto",
                                  "ids_de_otra_corrida", "items_no_es_lista_de_mapas",
                                  "items_no_es_lista", "no_es_un_mapa"])
def test_494_apply_REHUSA_el_archivo_entero_y_no_escribe_nada(toy_vault, tmp_path, caso):
    """Cuatro rehúses de archivo, cada uno cerrando una forma de escribir la respuesta equivocada.
    En los cuatro la extracción queda byte-idéntica: un rehúse no deja una escritura a medias, que
    sobre un artefacto versionado y no regenerable (#311) sería el peor resultado posible."""
    d = _extraccion()
    _txt_paginado()
    antes = (cfg.EXTRACCION / "ica_ruido" / f"{BIB}.json").read_bytes()
    filas = [{"id": it["id"], "pagina": "2010", "evidencia": "Received", "motivo": ""}
             for it in rp.items(d)]
    if caso == "otro_bibcode":
        res = tmp_path / "r.json"
        # ⚠ con el `pdf_sha` CORRECTO a propósito: si no, la guarda del sha lo frena igual y la
        # del bibcode no decide nada (#319)
        res.write_text(json.dumps({"bibcode": "2011Otro", "items": filas,
                                   "pdf_sha": _sha(cfg.PDFS / "ica_ruido" / f"{BIB}.pdf")}),
                       encoding="utf-8")
    elif caso == "paquete_en_vez_de_resultado":
        paq = rp.write_round(BIB, tmp_path / "paq")
        res = tmp_path / "r.json"
        res.write_text(json.dumps(paq, ensure_ascii=False), encoding="utf-8")
    elif caso == "sha_distinto":
        res = _resultado(tmp_path, filas, sha="0" * 10)
    elif caso == "ids_de_otra_corrida":
        res = _resultado(tmp_path, filas[:-1])
    else:
        res = _resultado(tmp_path, [123])   # ni siquiera es un mapa: sin la guarda revienta feo
    if caso == "no_es_un_mapa":
        res = tmp_path / "r.json"
        res.write_text(json.dumps([{"bibcode": BIB}]), encoding="utf-8")
    if caso == "items_no_es_lista":
        res = tmp_path / "r.json"
        res.write_text(json.dumps({"bibcode": BIB, "items": 5,
                                   "pdf_sha": _sha(cfg.PDFS / "ica_ruido" / f"{BIB}.pdf")}),
                       encoding="utf-8")
    with pytest.raises(rp.ApplyError):
        rp.apply(BIB, res)
    assert (cfg.EXTRACCION / "ica_ruido" / f"{BIB}.json").read_bytes() == antes


def test_494_la_evidencia_tiene_que_ser_TESTIGO_de_la_hoja(toy_vault, tmp_path):
    """⛔ El testigo es lo que hace verificable «abrí el PDF»: una `evidencia` contenida en el valor
    del propio ítem no prueba nada (se copia del paquete), y una que el `.txt` ubica en OTRA página
    contradice la respuesta. Las dos rehúsan el ítem y lo nombran."""
    d = _extraccion()
    _txt_paginado()
    filas = [{"id": it["id"], "pagina": "2010", "evidencia": "Received 3 March", "motivo": ""}
             for it in rp.items(d)]
    filas[0]["evidencia"] = CITA[:40]                      # está DENTRO del valor del ítem
    # una evidencia que el `.txt` ubica en OTRA hoja (la 3 imprime 2011, no 2010)
    filas[1]["evidencia"] = "relleno propio de la hoja 3 con una frase larga y distinta"
    r = rp.apply(BIB, _resultado(tmp_path, filas))
    motivos = dict(r["rehusados"])
    assert "contenida en el valor" in motivos["ground_truth[0].linea"]
    assert "otra página" in motivos["ejes.identificabilidad#1"], motivos


def test_494_el_CLI_reescribe_la_vista_acotado_y_avisa_lo_que_no_toca(toy_vault, tmp_path, capsys):
    """⛔ La celda *Localizador* de la `## Vista` la copió la máquina del JSON (#454), así que tiene
    re-estampa ACOTADA — la misma doctrina de #453. Las otras dos opciones eran peores: `--force`
    re-fecha la lectura (#395), y no tocarla deja el JSON bien y la tabla apuntando al documento
    reemplazado (~1653 celdas a mano, que es lo que #494 existe para no hacer).

    ⚠ Y sólo la celda cuyo token sigue siendo el que el paquete leyó: la corregida a mano no
    matchea, se **lista** y se deja como está."""
    _extraccion(vista={"sujeto": "tema", "tipo": "theme"})
    _txt_paginado()
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / f"{BIB}.md").write_text(
        "---\nbibcode: 2013Voss\ntags: [paper]\n---\n\n## Abstract\n\nx\n\n"
        "## Vista — tema\n\n| Qué | Valor | Localizador |\n|---|---|---|\n"
        f"| blanqueo | «{CITA}» | p. 4 |\n", encoding="utf-8")
    d = json.loads((cfg.EXTRACCION / "ica_ruido" / f"{BIB}.json").read_text(encoding="utf-8"))
    filas = [{"id": it["id"], "pagina": "2010", "evidencia": "Received 3 March 2013", "motivo": ""}
             for it in rp.items(d)]
    assert rp.main([BIB, "--apply", str(_resultado(tmp_path, filas))]) == 0
    nota = (cfg.PAPERS / f"{BIB}.md").read_text(encoding="utf-8")
    assert "| p. 2010 |" in nota and "| p. 4 |" not in nota, nota
    out = capsys.readouterr().out
    assert "deuda CERRADA" in out and "reverify_subset" in out, out
    assert "1 celda(s) re-estampada(s)" in out, "la vista se re-estampa acotado"


def test_494_el_swap_se_ancla_en_la_CITA_y_no_pisa_lo_corregido_a_mano(toy_vault):
    """⛔ El reemplazo se ancla en la CITA y no en el token, porque dos citas de un mismo string
    pueden nombrar la misma página: contando `p. 3` se cambiaría la otra. Y el token tiene que ser
    EXACTAMENTE el que leyó el paquete — si alguien lo corrigió en el medio, la función devuelve
    `None` y el ítem se rehúsa, que es la misma regla que protege una corrección a mano en
    `restamp_salvedades` (#453)."""
    texto = f"Dice «{CITA}» (p. 3) y también «{OTRA}» (p. 3) al final."
    cambiado = rp._replace_locator(texto, 2, "p. 3", "p. 2010")
    assert cambiado == f"Dice «{CITA}» (p. 3) y también «{OTRA}» (p. 2010) al final.", cambiado
    assert rp._replace_locator(texto, 1, "p. 9", "p. 2010") is None, "el token ya no es el del paquete"
    assert rp._replace_locator(texto, 3, "p. 3", "p. 2010") is None, "no hay tercera cita"
    # y una cita SIN localizador adyacente tampoco se completa con nada: devuelve `None`
    sin_loc = f"Dice «{CITA}» y nada más, y después «{OTRA}» (p. 3)."
    assert rp._replace_locator(sin_loc, 1, "p. 3", "p. 2010") is None


def test_494_si_el_swap_no_se_puede_hacer_el_item_se_REHUSA_y_no_se_escribe_None(toy_vault, tmp_path,
                                                                                 monkeypatch):
    """⛔ La red del artefacto: `raw/extraccion/**` es versionado y NO regenerable (#311), así que
    un reemplazo que no se pudo hacer se rehúsa y se nombra — nunca se escribe el resultado vacío.
    Se fuerza el caso porque las dos caminatas (la que enumera y la que reemplaza) hoy coinciden:
    la guarda existe para que dejar de coincidir sea un rehúse y no una escritura rota."""
    d = _extraccion()
    _txt_paginado()
    monkeypatch.setattr(rp, "_replace_locator", lambda *a, **k: None)
    filas = [{"id": it["id"], "pagina": "2010", "evidencia": "Received 3 March 2013", "motivo": ""}
             for it in rp.items(d)]
    r = rp.apply(BIB, _resultado(tmp_path, filas))
    nuevo = json.loads(r["extraccion"].read_text(encoding="utf-8"))
    assert "(p. 3)" in nuevo["salvedades"][0], "el string no se tocó"
    assert not r["cerrada"] and len(r["rehusados"]) == 3
    assert nuevo["ground_truth"][0]["linea"] == "p. 2010", "el `linea` no pasa por el swap"


def test_494_apply_sobre_una_extraccion_SIN_deuda_abierta_rehusa(toy_vault, tmp_path):
    """El simétrico del rehúse del paquete: aplicar un resultado a una extracción que ya cerró su
    deuda reescribiría localizadores que alguien releyó, con las páginas de otra corrida."""
    _extraccion(marca="_repaginado")
    _txt_paginado()
    with pytest.raises(rp.ApplyError, match="no tiene deuda"):
        rp.apply(BIB, _resultado(tmp_path, []))


def test_494_la_SALVEDAD_de_la_nota_se_sustituye_por_texto_exacto(toy_vault, tmp_path, capsys):
    """⛔ Devuelto por la repaginación real de la instancia: `--restamp-salvedades` **rehúsa por
    diseño** justo en esta población —cambiar el localizador dentro de una salvedad ES reescribir
    prosa ya escrita (#453, cuarta vuelta)—, así que la operación no podía cerrar su propio último
    paso y las notas hubo que arreglarlas por fuera: 90 salvedades en 35 notas. La sustitución es
    por texto EXACTO y sólo si aparece **una** vez; si no, se lista y no se toca (18 medidas)."""
    _extraccion(vista={"sujeto": "tema", "tipo": "theme"})
    _txt_paginado()
    d = json.loads((cfg.EXTRACCION / "ica_ruido" / f"{BIB}.json").read_text(encoding="utf-8"))
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / f"{BIB}.md").write_text(
        "---\nbibcode: 2013Voss\ntags: [paper]\n---\n\n## Abstract\n\nx\n\n"
        "## Vista — tema\n\n" + cfg.SALVEDAD_MARCAS[1] + "\n\n"
        f"- {d['salvedades'][0]}\n", encoding="utf-8")
    filas = [{"id": it["id"], "pagina": "2010", "evidencia": "Received 3 March 2013", "motivo": ""}
             for it in rp.items(d)]
    assert rp.main([BIB, "--apply", str(_resultado(tmp_path, filas))]) == 0
    nota = (cfg.PAPERS / f"{BIB}.md").read_text(encoding="utf-8")
    assert "(p. 2010)" in nota and "(p. 3)" not in nota, nota
    out = capsys.readouterr().out
    assert "sustituida(s)" in out and "0 sustituida(s)" not in out, out


def test_494_la_salvedad_EDITADA_A_MANO_se_lista_y_no_se_toca(toy_vault, tmp_path):
    """La guarda que mantiene la promesa de #453: si el texto viejo no está **exactamente una vez**
    en la nota, alguien lo editó y no se pisa."""
    _extraccion(vista={"sujeto": "tema", "tipo": "theme"})
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / f"{BIB}.md").write_text("---\nbibcode: 2013Voss\n---\n\nnada parecido\n",
                                          encoding="utf-8")
    import harvest_views as hv
    r = hv.restamp_exact_text(BIB, [("un texto que la nota no tiene", "otro")])
    assert r["cambiados"] == 0 and "0 vez/veces" in r["fuera"][0][1], r


def test_494_el_MOTIVO_del_hueco_viaja_al_texto(toy_vault, tmp_path):
    """⛔ El `motivo` distingue «no lo encontré» de «no aplica al documento nuevo» —la salvedad
    sobre la marca de agua del preprint que la copia del editor no tiene—, que en la repaginación
    real fueron **35 de 2214**. Tirarlo dejaba el hueco declarado y mudo (D-43)."""
    d = _extraccion(ground_truth=[{"que": "x", "valor": CITA, "linea": "p. 4"},
                                  {"que": "y", "valor": OTRA, "linea": "p. 5 (Tabla 4)"}])
    _txt_paginado()
    filas = [{"id": it["id"], "pagina": None, "evidencia": "",
              "motivo": "no aplica: es sobre la marca de agua del preprint"} for it in rp.items(d)]
    r = rp.apply(BIB, _resultado(tmp_path, filas))
    nuevo = json.loads(r["extraccion"].read_text(encoding="utf-8"))
    assert "no aplica: es sobre la marca de agua" in nuevo["ground_truth"][0]["linea"]
    # ⛔ y el hueco TAMPOCO se lleva el calificador (observación del validador): lo único que
    # caduca es el número — el «(Tabla 4)» sigue diciendo dónde de la página estaba el dato, y es
    # lo que hace barata la próxima relectura
    assert nuevo["ground_truth"][1]["linea"].endswith(" (Tabla 4)"), \
        nuevo["ground_truth"][1]["linea"]


def test_494_el_CALIFICADOR_del_localizador_no_se_pisa(toy_vault, tmp_path, capsys):
    """⛔ Devuelto por la repaginación real: la primera versión del escritor pisaba el campo `linea`
    ENTERO y con él el calificador —`p. 4 (Tabla 2)` quedaba en `p. 491`—. Medido: **143 de 563**.
    El calificador dice DÓNDE de la página está el dato y no se re-deriva de ningún lado.

    Y el caso **colapsado** se declara: el localizador viejo nombraba varias páginas, el lector
    ubicó una, y el resto del campo —que sigue nombrando las otras— queda."""
    d = _extraccion(ground_truth=[
        {"que": "blanqueo", "valor": CITA, "linea": "p. 4 (nota al pie de la Tabla 2)"},
        {"que": "dos", "valor": OTRA, "linea": "pp. 3-4, y también p. 9 si se mira el apéndice"}])
    _txt_paginado()
    filas = [{"id": it["id"], "pagina": "2010", "evidencia": "Received 3 March 2013", "motivo": ""}
             for it in rp.items(d)]
    assert rp.main([BIB, "--apply", str(_resultado(tmp_path, filas))]) == 0
    nuevo = json.loads((cfg.EXTRACCION / "ica_ruido" / f"{BIB}.json").read_text(encoding="utf-8"))
    assert nuevo["ground_truth"][0]["linea"] == "p. 2010 (nota al pie de la Tabla 2)"
    assert nuevo["ground_truth"][1]["linea"] == "p. 2010, y también p. 9 si se mira el apéndice"
    assert "1 colapsado(s)" in capsys.readouterr().out
    # ⛔ y queda en la MARCA, no sólo en pantalla: en pantalla se lo lleva la corrida, y es lo único
    # que queda dicho sobre un campo cuyo localizador viejo nombraba varias páginas (medido: 765 de
    # 5627 `ground_truth[].linea`)
    assert nuevo["_repaginado"]["colapsados"] == ["ground_truth[1].linea"], nuevo["_repaginado"]


def _extraccion_lente(lente: str = "orden", slug: str = "ica_ruido", bib: str = BIB):
    """La SEGUNDA lectura del mismo paper bajo otra lente: `<bib>__<lente>.json` (#371/#239)."""
    d = {"bibcode": bib, "enfasis": lente,
         "ground_truth": [{"que": "orden", "valor": OTRA, "linea": "p. 7"}],
         "_paginacion": {"reemplazo": "2026-09-11", "motivo": "versión del editor",
                         "pdf_sha": _sha(cfg.PDFS / slug / f"{bib}.pdf")}}
    (cfg.EXTRACCION / slug / f"{bib}__{lente}.json").write_text(json.dumps(d, ensure_ascii=False),
                                                                encoding="utf-8")
    return d


def test_494_la_EXTRACCION_POR_LENTE_tiene_su_paquete(toy_vault, tmp_path, capsys):
    """⛔ Devuelto por el validador: el paquete se indexaba por **bibcode** y la deuda vive en el
    **archivo**, así que una fuente con una segunda lectura bajo otra lente (#371/#308) entregaba
    sólo la primera —medido: **1542 de 2032** localizadores en una pasada— y la extracción por
    lente **no se podía nombrar** desde la línea de comandos. La identidad de una extracción es el
    `bibcode` de adentro (#374) y su archivo es la unidad de trabajo."""
    _extraccion()
    _extraccion_lente()
    _txt_paginado()
    paquetes = rp.write_rounds(BIB, tmp_path)
    assert sorted(p["lente"] for p in paquetes) == ["", "orden"], paquetes
    assert sorted(p["extraccion"] for p in paquetes) == [f"ica_ruido/{BIB}",
                                                         f"ica_ruido/{BIB}__orden"]
    assert (tmp_path / "ica_ruido" / BIB / "prompt.md").exists()
    assert (tmp_path / "ica_ruido" / f"{BIB}__orden" / "prompt.md").exists()
    # y `--list` nombra la lente, que es lo que hacía falta para poder pedirla
    assert rp.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "2 extracción(es)" in out and "lente `orden`" in out, out


def test_494_apply_vuelve_al_ARCHIVO_que_el_resultado_declara(toy_vault, tmp_path):
    """El escritor elige por `(bibcode, lente)`, no por orden de glob: con dos lecturas abiertas,
    aplicar sin decir a cuál volvería sería elegir por accidente. Y una lente que no corresponde a
    ninguna extracción abierta **rehúsa** nombrando las que hay."""
    _extraccion()
    d2 = _extraccion_lente()
    _txt_paginado()
    filas = [{"id": it["id"], "pagina": "2010", "evidencia": "Received 3 March 2013", "motivo": ""}
             for it in rp.items(d2)]
    res = tmp_path / "r.json"
    res.write_text(json.dumps({"bibcode": BIB, "extraccion": f"ica_ruido/{BIB}__orden",
                               "items": filas,
                               "pdf_sha": _sha(cfg.PDFS / "ica_ruido" / f"{BIB}.pdf")}),
                   encoding="utf-8")
    r = rp.apply(BIB, res)
    assert r["extraccion"].stem == f"{BIB}__orden", r["extraccion"]
    assert json.loads(r["extraccion"].read_text(encoding="utf-8"))["ground_truth"][0]["linea"] \
        == "p. 2010"
    # el canónico NO se tocó
    canon = json.loads((cfg.EXTRACCION / "ica_ruido" / f"{BIB}.json").read_text(encoding="utf-8"))
    assert canon["ground_truth"][0]["linea"] == "p. 4" and "_paginacion" in canon
    res.write_text(json.dumps({"bibcode": BIB, "extraccion": "otro_slug/inexistente",
                               "items": filas,
                               "pdf_sha": _sha(cfg.PDFS / "ica_ruido" / f"{BIB}.pdf")}),
                   encoding="utf-8")
    with pytest.raises(rp.ApplyError, match="no corresponde a ninguna extracción abierta"):
        rp.apply(BIB, res)


def test_494_el_MISMO_PAPER_bajo_DOS_SLUGS_no_colisiona_y_converge(toy_vault, tmp_path):
    """⛔ Devuelto por SEGUNDA vez: el stem **no identifica** al archivo. El mismo paper leído bajo
    dos sujetos vive bajo dos slugs (`gj_581/` y `hd_40307/`, 16 pares en la bóveda real), y con el
    directorio de salida en `out_dir / stem` los dos paquetes caían en el mismo lugar — medido:
    **68 emitidos, 52 en disco, 1641 de 2032**.

    ⛔ Y peor que perderlos: **no convergía**. El escritor dejaba el último del glob y el aplicador
    tomaba el primero, así que el resultado del paquete que sobrevivía rebotaba siempre por los
    `id` (7 contra 30) y re-emitirlo reproducía la colisión: esos 391 localizadores no se cerraban
    con NINGUNA secuencia de comandos. La lente era una mitad de la identidad; el slug es la otra.
    """
    _extraccion(slug="gj_581")
    d2 = _extraccion(slug="hd_40307", ground_truth=[{"que": "otra", "valor": OTRA, "linea": "p. 7"}],
                     salvedades=[], ejes={})
    _txt_paginado(slug="gj_581")
    _txt_paginado(slug="hd_40307")
    paquetes = rp.write_rounds(BIB, tmp_path)
    assert sorted(p["extraccion"] for p in paquetes) == [f"gj_581/{BIB}", f"hd_40307/{BIB}"]
    # ⛔ y el stdout NOMBRA el archivo: con `Path(...).stem` tiraba el slug y cortaba el bibcode en
    # el último punto, así que las dos líneas del par salían idénticas —justo sobre el eje que este
    # issue existe para separar— y no se podía saber cuál paquete se acababa de escribir
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rp.main([BIB, "--out", str(tmp_path / "cli")])
    salida = buf.getvalue()
    assert f"gj_581/{BIB}/prompt.md" in salida and f"hd_40307/{BIB}/prompt.md" in salida, salida
    # los DOS prompts en disco, cada uno con sus items: nada se pisa
    assert (tmp_path / "gj_581" / BIB / "prompt.md").exists()
    assert (tmp_path / "hd_40307" / BIB / "prompt.md").exists()
    assert sorted(len(p["items"]) for p in paquetes) == [1, 4]
    # y converge: el resultado de cada paquete vuelve a SU archivo. ⚠ En orden INVERSO al del glob
    # a propósito: si el aplicador eligiera por orden —que es lo que hacía— el primer resultado
    # iría al archivo equivocado, y con los dos abiertos eso no lo tapa ningún accidente.
    for paq in reversed(paquetes):
        filas = [{"id": it["id"], "pagina": "2010", "evidencia": "Received 3 March 2013",
                  "motivo": ""} for it in paq["items"]]
        res = tmp_path / f"{paq['extraccion'].replace('/', '_')}.json"
        res.write_text(json.dumps({"bibcode": BIB, "extraccion": paq["extraccion"],
                                   "items": filas, "pdf_sha": paq["pdf_sha"]}), encoding="utf-8")
        r = rp.apply(BIB, res)
        assert r["cerrada"] and not r["rehusados"], (paq["extraccion"], r["rehusados"])
        assert rp.file_id(r["extraccion"]) == paq["extraccion"]
    assert not rp.pending(), "las dos deudas quedaron cerradas en una pasada"


def test_501_el_escritor_no_corrompe_el_localizador_en_el_borde_de_la_ventana(toy_vault):
    """⛔ #501 — lector y escritor cortaban a 80 caracteres fijos, así que con el localizador en el
    borde leían un PREFIJO (`p. 1` de `p. 13`), la guarda `== viejo` pasaba y se reemplazaba sólo
    el prefijo: `p. 13` → `p. 20213` → `p. 20210213` (medido: tres así en una bóveda real)."""
    c = "this is a long enough quotation to be recognized by the parser"
    t = "| «" + c + "» | " + "x" * 69 + " | p. 13 |"
    assert rp._loc_token(t, c) == "p. 13"
    for _ in range(3):
        t = rp._replace_locator(t, 1, rp._loc_token(t, c), "p. 2021") or t
    assert t.endswith("| p. 2021 |"), t


def test_504_el_escritor_no_reescribe_el_localizador_de_la_afirmacion_vecina(toy_vault):
    """⛔ #504 — el escritor usa la misma adyacencia que el gate: con prosa entre la cita y el
    número, ese número es de OTRA afirmación y no se toca; con el localizador ANTES de la cita, se
    reescribe ése."""
    c = "this is a long enough quotation to be recognized by the parser"
    vecino = f"dice «{c}», pero la Tabla 1 (p. 6) lista otra cosa"
    assert rp._loc_token(vecino, c) == ""
    assert rp._replace_locator(vecino, 1, "p. 6", "p. 9") is None
    previo = f"la p. 5 dice que «{c}», y sigue"
    assert rp._loc_token(previo, c) == "p. 5"
    assert rp._replace_locator(previo, 1, "p. 5", "p. 8") == f"la p. 8 dice que «{c}», y sigue"
