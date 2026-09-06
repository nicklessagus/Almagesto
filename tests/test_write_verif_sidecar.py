"""`write_verif_sidecar`: el eslabón que faltaba en la cadena de `verify-citations` (#403)."""
import hashlib
import json
from pathlib import Path

import pytest

import lib_config as cfg
import lib_blocks as lb
import lint
import write_verif_sidecar as ws
from conftest import mk_note


CUERPO = ("# Concepto\n\nEl período es de 34.5 días [[2020Pdf]].\n\n"
          "La amplitud es 2.5 m/s [[2019Txt]].\n")


def _escena(toy_vault, cuerpo=CUERPO):
    """Un concepto con dos citas: una fuente con PDF (kind `pdf:`) y otra sólo con `.txt`."""
    nota = mk_note(cfg.CONCEPTS / "methods", "concepto", {"tags": ["methods"]}, cuerpo)
    for bib in ("2020Pdf", "2019Txt"):
        mk_note(cfg.PAPERS, bib, {"tags": ["paper"], "bibcode": bib})
    (cfg.PDFS / "s").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "s" / "2020Pdf.pdf").write_bytes(b"%PDF-1.4\n\x00\xffbinario\n")
    (cfg.FULLTEXT / "s").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "s" / "2019Txt.txt").write_text("The amplitude is 2.5 m/s.\n", encoding="utf-8")
    toy_vault.LOG.write_text("# log\n\n- [[concepto]]\n", encoding="utf-8")
    return nota


def _fanout(toy_vault, nota: Path, veredictos: dict, ronda="r1", **extra_par):
    """El directorio del fan-out con un JSON por fuente, anclas REALES del cuerpo (#369)."""
    d = toy_vault.ROOT / "build" / "concepto" / "verif" / ronda
    d.mkdir(parents=True, exist_ok=True)
    pares = lb.pairs_of(nota.read_text(encoding="utf-8"))
    por_bib: dict = {}
    for p in pares:
        v = veredictos.get(p.bibcode, "soportada")
        par = {"ancla": p.anchor, "veredicto": v, "evidencia": f'"cita textual" (p. 4)', **extra_par}
        por_bib.setdefault(p.bibcode, []).append(par)
    for bib, ps in por_bib.items():
        (d / f"{bib}.json").write_text(json.dumps({"bibcode": bib, "pares": ps}), encoding="utf-8")
    # el MANIFIESTO del generador (#369) vive en el mismo directorio y no es salida del fan-out:
    # el escritor lo tiene que saltear, como hace la barrera
    (d / "_esperado.json").write_text(json.dumps(
        {"nota": nota.as_posix(), "fuentes": {b: len(ps) for b, ps in por_bib.items()},
         "pares": len(pares)}), encoding="utf-8")
    return d


def test_escribe_el_hermano_y_la_nota_con_los_hashes_que_el_lint_LEE(toy_vault):
    """#403 — los dos errores medidos del armador escrito a mano: matchear `bibcode` en el nivel
    equivocado (55 falsos «sin veredicto») y hashear un PDF como texto (117 «vencidos por fuente»
    falsos). La prueba de que este escritor no comete ninguno es que el lint, que es quien lee, no
    reporta un solo par vencido ni una fila sin archivo."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    r = ws.write(nota, d, fecha="2026-03-01")
    assert r["filas"] == 2 and r["pares_cuerpo"] == 2 and r["encadenadas"] == 0

    hermano = cfg.verif_sidecar(nota)
    assert hermano.exists()
    filas = lb.verif_rows(nota)
    assert filas is not None and len(filas) == 2
    por_bib = {f.bibcode: f for f in filas}
    assert por_bib["2020Pdf"].source_kind == "pdf"
    assert por_bib["2020Pdf"].source_hash == lb.bytes_hash(cfg.PDFS / "s" / "2020Pdf.pdf"), \
        "el PDF se hashea por BYTES, con la misma función que el lint"
    assert por_bib["2019Txt"].source_kind == "txt"
    assert por_bib["2019Txt"].source_hash == lb.source_hash(cfg.FULLTEXT / "s" / "2019Txt.txt")

    texto = nota.read_text(encoding="utf-8")
    assert "## Verificación de citas (2026-03-01)" in texto
    assert lb.verif_summary(filas) in texto, "la cabecera la GENERA `verif_summary` (INV-81)"
    assert lb.verif_pointer(nota) in texto
    for sub in lb.VERIF_SUBSECCIONES:
        assert sub in texto
    assert ws.PENDIENTE in texto, "el triage de la corrida no se inventa: queda visible como pendiente"

    res = lint.collect()
    for cat in ("stale_pairs", "verif_sin_archivo", "verif_cabecera", "verif_sin_hermano",
                "verif_inline", "old_verif_template", "verif_estructura"):
        assert res.por_clave(cat).items == (), (cat, res.por_clave(cat).items)


def test_la_segunda_ronda_ENCADENA_y_la_misma_ronda_es_no_op(toy_vault):
    """#232/#274c — la segunda ronda anota, no pisa: `no-soportada→corregida`. Y una ronda que
    repite el último veredicto no alarga la cadena, que es lo que hace que correr el escritor dos
    veces sobre el mismo fan-out sea idempotente (red 6)."""
    nota = _escena(toy_vault)
    d1 = _fanout(toy_vault, nota, {"2020Pdf": "no-soportada"}, ronda="r1")
    ws.write(nota, d1, fecha="2026-03-01")
    h1 = (hashlib.sha256(nota.read_bytes()).hexdigest(),
          hashlib.sha256(cfg.verif_sidecar(nota).read_bytes()).hexdigest())
    ws.write(nota, d1, fecha="2026-03-01")
    h2 = (hashlib.sha256(nota.read_bytes()).hexdigest(),
          hashlib.sha256(cfg.verif_sidecar(nota).read_bytes()).hexdigest())
    assert h1 == h2, "IDEMPOTENTE: la misma ronda dos veces no cambia un byte"

    d2 = _fanout(toy_vault, nota, {"2020Pdf": "soportada"}, ronda="r2")
    r = ws.write(nota, d2, fecha="2026-03-02")
    filas = {f.bibcode: f for f in lb.verif_rows(nota)}
    assert filas["2020Pdf"].verdict == "no-soportada→soportada", filas["2020Pdf"].verdict
    assert filas["2019Txt"].verdict == "soportada", "la que no cambió no se toca"
    assert r["encadenadas"] == 1
    assert lint.collect().por_clave("verif_sin_resolver").items == (), \
        "la cadena anota la resolución: ya no es un veredicto pelado (#91)"

    assert ws.chained_verdict(None, "soportada") == "soportada"
    assert ws.chained_verdict("no-soportada", "no-soportada") == "no-soportada"
    assert ws.chained_verdict("a→b", "b") == "a→b" and ws.chained_verdict("a→b", "c") == "a→b→c"


def test_la_condicion_lleva_su_clase_y_el_no_verificable_no_lleva_archivo(toy_vault):
    """#221/#223 — la celda `Condición` arranca con su CLASE (`acota:`/`contextualiza:`), que es lo
    que separa la que obliga a editar de la que va al reporte; y el veredicto que no puede nombrar
    archivo no lo nombra, en vez de inventar un hash sobre la nada."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {"2019Txt": "no verificable por extracción"},
                condicion="sólo para SNR > 50", cond_tipo="acota")
    ws.write(nota, d, fecha="2026-03-01")
    filas = {f.bibcode: f for f in lb.verif_rows(nota)}
    assert filas["2020Pdf"].condition == "acota: sólo para SNR > 50"
    assert filas["2019Txt"].source_kind is None and filas["2019Txt"].source_hash == "—", \
        "sin archivo la celda es `—` — lo que el parser lee; `\"\"` no sobrevive al round-trip"
    assert lint.collect().por_clave("verif_sin_archivo").items == (), \
        "#223: la fila sin archivo NO es «no consta»: es la propiedad de ese veredicto"
    assert ws.condition_cell({}) == "—" and ws.condition_cell({"condicion": "x"}) == "x"


def test_preserva_el_triage_que_el_agente_ya_escribio(toy_vault):
    """El texto libre después de los dos puntos es el triage de la corrida y lo escribe quien leyó
    las fuentes: el escritor regenera el FRAGMENTO de conteo (#280) y deja lo demás."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    ws.write(nota, d, fecha="2026-03-01")
    texto = nota.read_text(encoding="utf-8").replace(
        f"Omisiones en transcripciones: {ws.PENDIENTE}",
        "Omisiones en transcripciones: la tabla 2 omitía la fila c, corregida")
    nota.write_text(texto, encoding="utf-8")
    ws.write(nota, d, fecha="2026-03-01")
    nuevo = nota.read_text(encoding="utf-8")
    assert "la tabla 2 omitía la fila c, corregida" in nuevo
    assert nuevo.count("Omisiones en transcripciones") == 1


def test_REHUSA_el_fanout_que_no_cerro_el_par_que_no_esta_y_la_fuente_que_no_existe(toy_vault):
    """Tres rechazos, cada uno nombrando qué. La barrera (#259) primero: un hermano armado desde un
    fan-out que no cerró es el trabajo derivado que #199 midió sin que nadie lo mirara. Después el
    par cuya ancla no está en el cuerpo — la nota cambió después de generar los prompts, y una fila
    sin par detrás es exactamente la huérfana que el lint reporta (D-4). Y la fuente que el fan-out
    dice haber leído y no está en disco."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    (d / "2020Pdf.json").write_text('{"bibcode": "2020Pdf", "veredictos": []}', encoding="utf-8")
    with pytest.raises(ws.SidecarError, match="barrera"):
        ws.write(nota, d)
    assert not cfg.verif_sidecar(nota).exists(), "rehusar es no escribir NADA"

    d = _fanout(toy_vault, nota, {}, ronda="r2")
    datos = json.loads((d / "2020Pdf.json").read_text(encoding="utf-8"))
    datos["pares"][0]["ancla"] = "ffffffffff"
    (d / "2020Pdf.json").write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ws.SidecarError, match="ffffffffff"):
        ws.write(nota, d)

    d = _fanout(toy_vault, nota, {}, ronda="r3")
    (cfg.FULLTEXT / "s" / "2019Txt.txt").unlink()
    with pytest.raises(ws.SidecarError, match="2019Txt"):
        ws.write(nota, d)


def test_el_cli_dice_que_hizo_y_no_escribe_con_dry_run(toy_vault, capsys):
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    assert ws.main([str(nota), "--from", str(d), "--dry-run", "--fecha", "2026-03-01"]) == 0
    assert "se escribiría" in capsys.readouterr().out
    assert not cfg.verif_sidecar(nota).exists()
    assert ws.main([str(nota), "--from", str(d), "--fecha", "2026-03-01"]) == 0
    assert "escrito" in capsys.readouterr().out and cfg.verif_sidecar(nota).exists()
    assert ws.main([str(cfg.verif_sidecar(nota)), "--from", str(d)]) == 2, "el hermano no es una nota"
    assert ws.main([str(nota), "--from", str(d / "no_existe")]) == 2
    (d / "2020Pdf.json").write_text("roto", encoding="utf-8")
    assert ws.main([str(nota), "--from", str(d)]) == 1
    assert "⛔" in capsys.readouterr().out


def test_las_cuatro_guardas_que_el_barrido_no_distinguia(toy_vault):
    """Las cuatro que `mutar --guardas` encontró sin test, cada una con su caso:

    · el par del cuerpo que el fan-out NO juzgó se deja afuera — el lint lo reporta como «sin
      verificar», que es la verdad — en vez de inventarle una fila;
    · un fan-out que no juzgó NINGÚN par no escribe una tabla vacía: rehúsa y lo dice;
    · una sub-sección escrita sin dos puntos no tiene texto libre, y se re-marca pendiente;
    · el texto libre que trae `: ` adentro se preserva ENTERO — cortarlo en el último `: ` (que es
      lo que hace `rpartition`) se lo comería."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    (d / "2019Txt.json").unlink()                         # el fan-out juzgó UNA sola fuente
    r = ws.write(nota, d, fecha="2026-03-01")
    assert r["filas"] == 1 and r["pares_cuerpo"] == 2
    assert [f.bibcode for f in lb.verif_rows(nota)] == ["2020Pdf"]
    assert any("2019Txt" in m for _s, m in lint.collect().por_clave("stale_pairs").items), \
        "el par no juzgado sale como SIN VERIFICAR, no como verificado ni como huérfano"

    # un fan-out VACÍO con hermano previo no es un error: es la ronda de re-anclaje puro que
    # `--solo-nuevos` produce cuando no hay nada nuevo (#407) — 0 juzgadas, todas arrastradas
    vacio = toy_vault.ROOT / "build" / "concepto" / "verif" / "vacia"
    vacio.mkdir(parents=True)
    r = ws.write(nota, vacio, fecha="2026-03-02")
    assert r["juzgadas"] == 0 and r["arrastradas"] == 1
    # …y SIN hermano previo sí es un error: no hay tabla que escribir ni fila que llevar
    cfg.verif_sidecar(nota).unlink()
    with pytest.raises(ws.SidecarError, match="ningún par"):
        ws.write(nota, vacio)

    assert ws.free_text_of("Omisiones en transcripciones sin dos puntos", "Omisiones en transcripciones") == ""
    assert ws.free_text_of("Otra cosa: x", "Omisiones en transcripciones") == ""
    con_colon = "Omisiones en transcripciones: la tabla 2: fila c omitida, corregida"
    assert ws.free_text_of(con_colon, "Omisiones en transcripciones") == \
        "la tabla 2: fila c omitida, corregida"
    largo = ("Condiciones perdidas — 3 con condición: 1 `acota` (1 resueltas) / 2 `contextualiza` "
             "/ 0 sin clasificar: la `acota` era: SNR > 50, resuelta acotando la frase")
    assert ws.free_text_of(largo, "Condiciones perdidas") == \
        "la `acota` era: SNR > 50, resuelta acotando la frase"


def test_la_ronda_ACOTADA_arrastra_los_pares_de_afuera_con_el_ancla_recalculada(toy_vault):
    """#407/#282/#257 — la partición que `reverify_subset` emite, cerrada: los pares del alcance
    reciben su veredicto nuevo; los de AFUERA se llevan el veredicto que tenían con el ancla
    recalculada (match por ancla exacta o por cobertura del extracto, nunca cruzando `bibcode`).
    La prueba de que el ciclo converge es que el lint no reporta un solo par vencido después."""
    nota = _escena(toy_vault)
    ws.write(nota, _fanout(toy_vault, nota, {}, ronda="r1"), fecha="2026-03-01")
    ancla_vieja = {f.bibcode: f.anchor for f in lb.verif_rows(nota)}["2019Txt"]

    # se edita la frase de 2019Txt SIN cambiar lo que afirma (cobertura alta) y se re-verifica SÓLO
    # 2020Pdf: la ronda acotada de #407
    texto = nota.read_text(encoding="utf-8").replace(
        "La amplitud es 2.5 m/s [[2019Txt]].", "La amplitud es 2.5 m/s, medida en 2019 [[2019Txt]].")
    nota.write_text(texto, encoding="utf-8")
    d = _fanout(toy_vault, nota, {"2020Pdf": "no-soportada"}, ronda="r2")
    (d / "2019Txt.json").unlink()
    r = ws.write(nota, d, fecha="2026-03-02")
    assert r["juzgadas"] == 1 and r["arrastradas"] == 1 and r["filas"] == 2

    filas = {f.bibcode: f for f in lb.verif_rows(nota)}
    assert filas["2020Pdf"].verdict == "soportada→no-soportada"
    assert filas["2019Txt"].verdict == "soportada", "fuera del alcance: el veredicto se LLEVA"
    assert filas["2019Txt"].anchor != ancla_vieja, "…y el ancla se RECALCULA sobre el texto nuevo"
    assert lint.collect().por_clave("stale_pairs").items == (), \
        "ni vencido por edición ni huérfano: la partición de #282 cerró"
