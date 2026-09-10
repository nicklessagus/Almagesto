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


# ── #430 · la prosa del triage se pierde en silencio ────────────────────────────────────────────
# `free_text_of` comparaba el arranque de la sub-sección SIN normalizar el markdown (regla de
# método nº 4, quinta vez: #168, #276, #283, #309). Una sub-sección adornada o con paréntesis
# aclaratorio devolvía `""`, y `note_section` escribía el placeholder ENCIMA del triage de la
# corrida — lo único que registra qué se decidió en esa ronda. Medido en una bóveda real: 10
# sub-secciones en 4 notas perdibles, y 2 con el fragmento de conteo YA duplicado.

def _con_triage(nota: Path, linea_vieja: str, linea_nueva: str) -> None:
    """Reemplaza una línea de sub-sección por la forma que el agente escribió a mano."""
    t = nota.read_text(encoding="utf-8")
    assert linea_vieja in t, linea_vieja
    nota.write_text(t.replace(linea_vieja, linea_nueva), encoding="utf-8")


@pytest.mark.parametrize("linea, esperado", [
    # adorno + paréntesis aclaratorio: la forma que el skill mismo publica en su plantilla
    ("**Inferencias declaradas (sin cita, por diseño)** — 0 marcas en el cuerpo: "
     "las tres del apartado 6", "las tres del apartado 6"),
    # terminador `.` en vez de `: ` — los tres `cierre` literales no lo cubrían
    ("**Inferencias declaradas — 0 marcas en el cuerpo.** Cada una nombra sus premisas",
     "Cada una nombra sus premisas"),
    # sólo adorno
    ("**Inferencias declaradas** — 0 marcas en el cuerpo: la comparación", "la comparación"),
])
def test_la_prosa_del_triage_SOBREVIVE_al_adorno_y_al_parentesis(toy_vault, linea, esperado):
    """#430 — `s.startswith(sub)` sobre la línea CRUDA: con `**` adelante devuelve `""` y el
    placeholder pisa el triage. Sin aviso, sin error."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    ws.write(nota, d, fecha="2026-03-01")
    _con_triage(nota, "Inferencias declaradas — 0 marcas en el cuerpo: " + ws.PENDIENTE, linea)
    ws.write(nota, d, fecha="2026-03-01")
    nuevo = nota.read_text(encoding="utf-8")
    assert esperado in nuevo, "el triage de la corrida desapareció"
    assert nuevo.count(ws.PENDIENTE) == 2, "sólo las otras dos sub-secciones siguen pendientes"


def test_el_fragmento_DUPLICADO_se_colapsa_y_la_prosa_es_la_del_ULTIMO(toy_vault):
    """#430 — el síntoma ya materializado en dos notas reales: una corrida anterior no reconoció el
    fragmento viejo y le antepuso uno nuevo, así que la línea publica DOS conteos contradictorios y
    el segundo es todo ceros."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    ws.write(nota, d, fecha="2026-03-01")
    _con_triage(nota, "Condiciones perdidas — 0 con condición: 0 `acota` (0 resueltas) / "
                      "0 `contextualiza` / 0 sin clasificar: " + ws.PENDIENTE,
                "Condiciones perdidas — 9 con condición: 1 `acota` (0 resueltas) / "
                "8 `contextualiza` / 0 sin clasificar: 0 con condición: 0 `acota` (0 resueltas) / "
                "0 `contextualiza` / 0 sin clasificar. Las **`acota`** se resolvieron en la 3.")
    ws.write(nota, d, fecha="2026-03-01")
    linea = next(l for l in nota.read_text(encoding="utf-8").split("\n")
                 if l.startswith("Condiciones perdidas"))
    assert linea.count("con condición") == 1, f"fragmento duplicado: {linea}"
    assert linea.endswith("Las **`acota`** se resolvieron en la 3.")


def test_si_la_prosa_ENTRA_y_SALE_vacia_se_ABORTA_en_vez_de_escribir(toy_vault, monkeypatch):
    """#430/#222 — la red barata: un triage que desaparece no puede pasar en silencio. Si el lector
    no reconoce la prosa que la línea vieja tenía, se rehúsa; no se escribe el placeholder."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    ws.write(nota, d, fecha="2026-03-01")
    _con_triage(nota, "Omisiones en transcripciones: " + ws.PENDIENTE,
                "Omisiones en transcripciones: la tabla 2 omitía la fila c")
    monkeypatch.setattr(lb, "subsection_split", lambda linea, sub: (True, ""))
    antes = nota.read_bytes()
    with pytest.raises(ws.SidecarError, match="Omisiones en transcripciones"):
        ws.write(nota, d, fecha="2026-03-01")
    assert nota.read_bytes() == antes, "rehusó y NO escribió"


def test_restamp_section_regenera_la_seccion_sin_fanout_y_es_idempotente(toy_vault):
    """#430 — el migrador: re-escribe la sección de la nota desde el hermano que ya existe,
    conservando la fecha del bloque. Es lo que colapsa el fragmento duplicado del corpus heredado."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    ws.write(nota, d, fecha="2026-03-01")
    _con_triage(nota, "Inferencias declaradas — 0 marcas en el cuerpo: " + ws.PENDIENTE,
                "**Inferencias declaradas (sin cita, por diseño)** — 4 marcas en el cuerpo: "
                "0 marcas en el cuerpo: las cuatro nombran sus premisas")
    hermano_antes = cfg.verif_sidecar(nota).read_bytes()
    r = ws.restamp_section(nota)
    t1 = nota.read_text(encoding="utf-8")
    linea = next(l for l in t1.split("\n") if l.startswith("Inferencias declaradas"))
    # lo que el migrador ARREGLA: un solo fragmento, con el conteo que la tabla da hoy, y la prosa
    assert linea == "Inferencias declaradas — 0 marcas en el cuerpo: las cuatro nombran sus premisas"
    assert r["cambio"] and r["filas"] == 2 and r["fecha"] == "2026-03-01"
    assert "## Verificación de citas (2026-03-01)" in t1, "la fecha del bloque se conserva"
    assert cfg.verif_sidecar(nota).read_bytes() == hermano_antes, "no toca el hermano"
    assert ws.restamp_section(nota)["cambio"] is False
    assert nota.read_text(encoding="utf-8") == t1, "idempotente"


def test_restamp_section_REHUSA_sin_hermano_y_sin_fecha(toy_vault):
    """#430/D-43 — las dos cosas que no se inventan: la tabla (no hay de dónde leer las filas) y la
    fecha del bloque (re-fechar es re-verificar, y esto no re-verifica nada)."""
    nota = _escena(toy_vault)
    with pytest.raises(ws.SidecarError, match="hermano"):
        ws.restamp_section(nota)
    d = _fanout(toy_vault, nota, {})
    ws.write(nota, d, fecha="2026-03-01")
    nota.write_text(nota.read_text(encoding="utf-8").replace(
        "## Verificación de citas (2026-03-01)", "## Verificación de citas"), encoding="utf-8")
    with pytest.raises(ws.SidecarError, match="fecha"):
        ws.restamp_section(nota)


def test_el_cli_de_restamp_barre_declarando_su_poblacion_y_no_se_frena_en_la_primera(toy_vault, capsys):
    """#430 — `--restamp-section --todo`: declara su población (INV-40) y NO para en la primera
    rehusada, porque la nota cuyo triage el lector no reconoce ES el hallazgo y frenar taparía el
    resto del corpus detrás de ella."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    ws.write(nota, d, fecha="2026-03-01")
    otra = mk_note(cfg.CONCEPTS / "methods", "otro", {"tags": ["methods"]},
                   "# Otro\n\nDato [[2020Pdf]].\n")
    toy_vault.LOG.write_text("# log\n\n- [[concepto]]\n- [[otro]]\n", encoding="utf-8")
    ws.write(otra, _fanout(toy_vault, otra, {}, ronda="r_otro"), fecha="2026-03-02")
    # una de las dos queda con la fecha borrada: rehúsa, y la otra igual se re-estampa
    otra.write_text(otra.read_text(encoding="utf-8").replace(
        "## Verificación de citas (2026-03-02)", "## Verificación de citas"), encoding="utf-8")
    rc = ws.main(["--restamp-section", "--todo"])
    salida = capsys.readouterr().out
    assert rc == 1, "una rehusada → exit ≠ 0"
    assert "sobre 2 nota(s) con hermano" in salida, "declara su población"
    assert "otro.md" in salida and "fecha" in salida, "nombra la que rehusó y por qué"


def test_el_cli_de_restamp_toma_UNA_nota_y_RECHAZA_que_le_pasen_el_hermano(toy_vault, capsys):
    """#430 — las dos entradas de un solo archivo: la nota (se re-estampa) y el HERMANO, que es el
    error de tipeo natural de esta modalidad (el nombre difiere en un sufijo) y no es una nota
    (#344): re-estamparlo escribiría una sección de verificación adentro del rastro."""
    nota = _escena(toy_vault)
    ws.write(nota, _fanout(toy_vault, nota, {}), fecha="2026-03-01")
    assert ws.main(["--restamp-section", str(nota)]) == 0
    assert "sobre 1 nota(s) con hermano" in capsys.readouterr().out
    assert ws.main(["--restamp-section", str(cfg.verif_sidecar(nota))]) == 1
    assert "no es una nota" in capsys.readouterr().out


def test_el_cli_de_restamp_nombra_la_nota_QUE_NO_EXISTE_en_vez_de_reventar(toy_vault, capsys):
    """#430 — el hermano huérfano (la nota borrada, que el lint ya bloquea por #344) llega igual a
    esta modalidad porque el universo se enumera POR HERMANOS. Se nombra y se sigue; reventar
    dejaría el resto del corpus sin re-estampar detrás de un caso que el lint ya reporta."""
    nota = _escena(toy_vault)
    ws.write(nota, _fanout(toy_vault, nota, {}), fecha="2026-03-01")
    hermano = cfg.verif_sidecar(nota)
    nota.unlink()
    assert hermano.exists()
    assert ws.main(["--restamp-section", "--todo"]) == 1
    salida = capsys.readouterr().out
    assert "sobre 1 nota(s) con hermano" in salida and "no es una nota" in salida


def test_el_cli_sin_from_ni_restamp_rehusa(toy_vault, capsys):
    """#430 — `--from` dejó de ser `required` para que exista `--restamp-section`: la combinación
    vacía tiene que seguir rehusando, no caer en un modo por default."""
    nota = _escena(toy_vault)
    assert ws.main([str(nota)]) == 2
    assert "--from" in capsys.readouterr().out


def test_la_prosa_se_preserva_con_el_nombre_en_OTRA_CAPITALIZACION(toy_vault):
    """#430 — el nombre de la sub-sección es vocabulario fijo, así que una mayúscula distinta es un
    tipeo, no otro significado. Sin plegar la caja, `Omisiones en TRANSCRIPCIONES` no matcheaba y la
    prosa se perdía con la guarda mirando: el residual sale del mismo prefijo que el lector."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    ws.write(nota, d, fecha="2026-03-01")
    _con_triage(nota, "Omisiones en transcripciones: " + ws.PENDIENTE,
                "Omisiones en TRANSCRIPCIONES: la tabla 2 omitía la fila c, corregida")
    ws.write(nota, d, fecha="2026-03-01")
    assert "la tabla 2 omitía la fila c, corregida" in nota.read_text(encoding="utf-8")


def test_NINGUNA_prosa_de_la_seccion_vieja_desaparece_sin_aviso(toy_vault):
    """#430/#222 — la red que NO depende del lector, y la razón de que exista: la guarda por
    sub-sección sólo ve lo que el lector reconoce, así que una línea con el nombre mal escrito —o un
    párrafo que el agente agregó y que la plantilla no contempla— se evaporaba con la guarda
    mirando. Ésta compara la sección vieja contra la nueva y rehúsa nombrando lo que se perdería:
    contar antes y después es la red barata de #222, un nivel más arriba."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    ws.write(nota, d, fecha="2026-03-01")
    t = nota.read_text(encoding="utf-8")
    nota.write_text(t.replace("Omisiones en transcripciones: " + ws.PENDIENTE,
                              "Omisiones en transcripciones: " + ws.PENDIENTE
                              + "\n\nOtra cosa que el agente anotó y la plantilla no contempla."),
                    encoding="utf-8")
    antes = nota.read_bytes()
    with pytest.raises(ws.SidecarError, match="se perdería"):
        ws.write(nota, d, fecha="2026-03-01")
    assert nota.read_bytes() == antes, "rehusó y NO escribió"


def test_el_triage_mas_corto_que_existe_TAMBIEN_esta_protegido(toy_vault):
    """#430 — «ninguna» tiene 7 caracteres y es la respuesta más común de las tres sub-secciones:
    un umbral cómodo para «esto no es prosa» descarta en silencio justo el caso frecuente. Debajo
    del umbral quedan sólo signos sueltos, que sí son residuo de pelar lo estampado."""
    assert ws._lost_prose("Omisiones en transcripciones: ninguna", "Omisiones en transcripciones: "
                          + ws.PENDIENTE) == ["ninguna"]
    assert ws._lost_prose("Omisiones en transcripciones: xy",
                          "Omisiones en transcripciones: " + ws.PENDIENTE) == [], \
        "un residuo de dos caracteres es signo suelto, no triage"


# ── #427 · la celda `Condición` no duplica su clase, y hay quien escribe `acota→resuelta:` ──────

def test_condition_cell_NO_duplica_la_clase_que_el_fanout_ya_escribio(toy_vault):
    """#427 — `condition_cell` anteponía `cond_tipo` sin mirar si `condicion` ya arrancaba con su
    clase, y el prompt no lo prohibía. El resultado, `acota: acota→…`, deja la fila IRRESOLUBLE:
    `condition_resolved` lee el segundo token y ahí encuentra la clase, no la resolución."""
    assert ws.condition_cell({"condicion": "SNR > 50", "cond_tipo": "acota"}) == "acota: SNR > 50"
    assert ws.condition_cell({"condicion": "acota: SNR > 50", "cond_tipo": "acota"}) == \
        "acota: SNR > 50", "la clase ya estaba: no se duplica"
    assert ws.condition_cell({"condicion": "**acota** — SNR > 50", "cond_tipo": "acota"}) == \
        "acota: SNR > 50", "adornada, sigue siendo la misma clase (#283)"
    assert ws.condition_cell({"condicion": "acota: SNR > 50", "cond_tipo": ""}) == "acota: SNR > 50"
    assert ws.condition_cell({"condicion": "", "cond_tipo": "acota"}) == "—"


def test_condition_cell_REHUSA_cuando_el_extractor_se_contradice(toy_vault):
    """#427/D-43 — `cond_tipo: acota` con `condicion: contextualiza: …` es el productor
    contradiciéndose, y elegir uno sería inventar la clase. Se rehúsa nombrando el par: el arreglo
    va en el JSON de la ronda, que es donde está el error."""
    with pytest.raises(ws.SidecarError, match="contextualiza"):
        ws.condition_cell({"condicion": "contextualiza: la muestra es de 12", "cond_tipo": "acota",
                           "ancla": "abc1234567"}, bibcode="2020Pdf")


def test_la_resolucion_de_un_acota_SOBREVIVE_a_la_ronda_siguiente(toy_vault):
    """#427/#232 — una ronda posterior recalcula la celda desde el JSON del fan-out, que no sabe
    nada de la resolución: sin esto, marcar un `acota` como resuelto y volver a correr el escritor
    lo desmarcaba en silencio. Una resolución es una decisión que alguien firmó."""
    assert ws.chained_condition(None, "acota: SNR > 50") == "acota: SNR > 50"
    assert ws.chained_condition("acota: SNR > 50", "acota: SNR > 50") == "acota: SNR > 50"
    assert ws.chained_condition("acota→resuelta: fila en el régimen", "acota: SNR > 50") == \
        "acota→resuelta: fila en el régimen", "la resolución manda sobre el recálculo"
    assert ws.chained_condition("contextualiza: x", "acota: SNR > 50") == "acota: SNR > 50"
    # las dos mitades de la guarda, cada una por su lado: previa NO resuelta (aunque sea la misma
    # clase) y previa resuelta de OTRA clase. En los dos casos manda el recálculo del fan-out.
    assert ws.chained_condition("acota: SNR > 30", "acota: SNR > 50") == "acota: SNR > 50"
    assert ws.chained_condition("contextualiza→resuelta: y", "acota: SNR > 50") == "acota: SNR > 50"


def test_resolver_escribe_la_notacion_QUE_EL_LECTOR_SABE_LEER(toy_vault):
    """#427 — `condition_resolved` definía el formato y `verif_counts` publicaba el conteo, pero
    NINGÚN script lo escribía: el agente editaba el hermano a mano, contra el banner del propio
    archivo y contra #403. Ahora lo escribe el mismo módulo que arma la tabla, y valida con el
    lector antes de escribir."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {}, condicion="SNR > 50", cond_tipo="acota")
    ws.write(nota, d, fecha="2026-03-01")
    filas = lb.verif_rows(nota)
    assert lb.verif_counts(filas)["cond_acota_resueltas"] == 0
    ancla = filas[0].anchor
    r = ws.resolve_conditions(nota, {ancla: "fila en `## Régimen de validez`"})
    assert r["resueltas"] == 1
    fila = next(f for f in lb.verif_rows(nota) if f.anchor == ancla)
    assert lb.condition_resolved(fila.condition), fila.condition
    assert "SNR > 50" in fila.condition, "la condición original se conserva detrás del `·`"
    assert "2 `acota` (1 resueltas)" in nota.read_text(encoding="utf-8"), \
        "la cabecera de la sub-sección se re-genera con el conteo nuevo (#280)"
    assert "## Verificación de citas (2026-03-01)" in nota.read_text(encoding="utf-8"), \
        "resolver no es re-verificar: la fecha del bloque no se mueve"
    assert ws.resolve_conditions(nota, {ancla: "fila en `## Régimen de validez`"})["resueltas"] == 0


def test_resolver_REHUSA_el_ancla_que_no_esta_la_fila_que_no_es_acota_y_el_texto_DISTINTO(toy_vault):
    """#427/#232 — anotar, nunca pisar. Y las dos formas de pedirlo sobre la fila equivocada: un
    ancla que no existe (¿se editó la nota?) y una `contextualiza`, que por definición no se
    resuelve — va al reporte, no a `## Régimen de validez`."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {}, condicion="la muestra es de 12", cond_tipo="contextualiza")
    ws.write(nota, d, fecha="2026-03-01")
    ancla = lb.verif_rows(nota)[0].anchor
    with pytest.raises(ws.SidecarError, match="no está"):
        ws.resolve_conditions(nota, {"0" * 10: "x"})
    with pytest.raises(ws.SidecarError, match="contextualiza"):
        ws.resolve_conditions(nota, {ancla: "x"})
    d2 = _fanout(toy_vault, nota, {}, ronda="r2", condicion="SNR > 50", cond_tipo="acota")
    ws.write(nota, d2, fecha="2026-03-01")
    ancla = lb.verif_rows(nota)[0].anchor
    ws.resolve_conditions(nota, {ancla: "fila A"})
    with pytest.raises(ws.SidecarError, match="ya declara"):
        ws.resolve_conditions(nota, {ancla: "fila B"})


def test_migrate_condition_prefix_colapsa_la_clase_DOBLE_y_es_idempotente(toy_vault):
    """#427 — el migrador de las 41 celdas medidas. Colapsa la cabeza repetida dejando el texto de
    adentro VERBATIM, que es justo la forma canónica; no re-escribe la condición."""
    assert ws.collapse_condition("acota: acota→resuelta: fila") == "acota→resuelta: fila"
    assert ws.collapse_condition("acota: acota: SNR > 50") == "acota: SNR > 50"
    assert ws.collapse_condition("contextualiza: contextualiza: x") == "contextualiza: x"
    assert ws.collapse_condition("acota: SNR > 50") == "acota: SNR > 50", "sin doble, no toca"
    assert ws.collapse_condition("acota: contextualiza: x") == "acota: contextualiza: x", \
        "clases DISTINTAS no son una duplicación: eso es una contradicción y no se resuelve sola"
    assert ws.collapse_condition("—") == "—"
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {}, condicion="SNR > 50", cond_tipo="acota")
    ws.write(nota, d, fecha="2026-03-01")
    herm = cfg.verif_sidecar(nota)
    herm.write_text(herm.read_text(encoding="utf-8")
                    .replace("acota: SNR > 50", "acota: acota→resuelta: fila A", 1), encoding="utf-8")
    assert lb.verif_counts(lb.verif_rows(nota))["cond_acota_resueltas"] == 0, "irresoluble hoy"
    assert ws.migrate_condition_prefix(nota)["migradas"] == 1
    assert lb.verif_counts(lb.verif_rows(nota))["cond_acota_resueltas"] == 1
    t1 = nota.read_bytes(), herm.read_bytes()
    assert ws.migrate_condition_prefix(nota)["migradas"] == 0
    assert (nota.read_bytes(), herm.read_bytes()) == t1, "idempotente"


def test_el_cli_de_condiciones_toma_una_nota_y_rehusa_el_par_MAL_FORMADO(toy_vault, capsys):
    """#427 — `--resolver <ancla>=<dónde>`: sin el `=` no resolvería nada y esto escribe en el
    artefacto que el lint lee, así que se rehúsa en vez de adivinar. Y no hay `--todo`: resolver una
    condición es una decisión POR PAR."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {}, condicion="SNR > 50", cond_tipo="acota")
    ws.write(nota, d, fecha="2026-03-01")
    ancla = lb.verif_rows(nota)[0].anchor
    assert ws.main(["--resolver", f"{ancla}=fila A", str(nota)]) == 0
    assert "1 condición(es)" in capsys.readouterr().out
    assert lb.verif_counts(lb.verif_rows(nota))["cond_acota_resueltas"] == 1
    assert ws.main(["--resolver", "sin-igual", str(nota)]) == 1
    assert "falta el `=`" in capsys.readouterr().out
    assert ws.main(["--migrate-condition-prefix"]) == 2
    assert "UNA nota" in capsys.readouterr().out
    assert ws.main(["--migrate-condition-prefix", str(cfg.verif_sidecar(nota))]) == 2


def test_el_cli_de_condiciones_acepta_el_LOTE_por_json(toy_vault, capsys):
    """#427 — `--resoluciones <json>`: el mismo trabajo para una nota con muchas `acota`, que es el
    caso medido (20 en una nota real). Un JSON que no es un objeto se rehúsa."""
    import json as _json
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {}, condicion="SNR > 50", cond_tipo="acota")
    ws.write(nota, d, fecha="2026-03-01")
    anclas = [f.anchor for f in lb.verif_rows(nota)]
    j = toy_vault.ROOT / "build" / "res.json"
    j.write_text(_json.dumps({a: f"fila {i}" for i, a in enumerate(anclas)}), encoding="utf-8")
    assert ws.main(["--resoluciones", str(j), str(nota)]) == 0
    assert lb.verif_counts(lb.verif_rows(nota))["cond_acota_resueltas"] == len(anclas)
    j.write_text(_json.dumps(["no", "es", "objeto"]), encoding="utf-8")
    assert ws.main(["--resoluciones", str(j), str(nota)]) == 1
    assert "objeto" in capsys.readouterr().out


# ── #428 · un artefacto ya pagado tiene que poder consumirse ────────────────────────────────────

def test_from_acepta_VARIAS_rondas_y_encadena(toy_vault):
    """#428 — el fan-out es el paso caro (N subagentes leyendo PDFs). Con un solo `--from` había
    que encadenar N invocaciones a mano, y cuando una ronda no se podía pasar sola la única salida
    era re-pagarla o escribir el ensamblador a mano — que es lo que #403 existe para eliminar.
    Encadenar en memoria da byte a byte lo mismo que las N corridas sucesivas."""
    nota = _escena(toy_vault)
    r1 = _fanout(toy_vault, nota, {"2020Pdf": "no-soportada"}, ronda="r1")
    r2 = _fanout(toy_vault, nota, {"2020Pdf": "corregida"}, ronda="r2")
    ws.write(nota, r1, fecha="2026-03-01")
    ws.write(nota, r2, fecha="2026-03-02")
    serial = (nota.read_text(encoding="utf-8"), cfg.verif_sidecar(nota).read_text(encoding="utf-8"))

    cfg.verif_sidecar(nota).unlink()
    nota.write_text("---\ntags:\n- methods\n---\n" + CUERPO, encoding="utf-8")
    r = ws.write(nota, [r1, r2], fecha="2026-03-02")
    assert (nota.read_text(encoding="utf-8"),
            cfg.verif_sidecar(nota).read_text(encoding="utf-8")) == serial, \
        "dos `--from` encadenados == dos corridas sucesivas"
    assert r["rondas"] == 2
    assert "no-soportada→corregida" in serial[1], "la ronda 2 ANOTÓ sobre la 1 (#232)"


def test_from_DECLARA_las_anclas_muertas_en_vez_de_rechazar_la_ronda_entera(toy_vault):
    """#428 — el ancla es de BLOQUE: un par cuya ancla no cambió es demostrablemente sobre texto
    intacto, así que rechazar la ronda ENTERA es una decisión a nivel archivo sobre una propiedad
    que es a nivel par. Medido en una instancia: 3 rondas, 77 pares con veredicto vivo en 72 casos,
    y ninguna forma de escribirlos. ⛔ Es opt-in y DECLARADO (D-43): el descarte silencioso sería un
    lector tolerante; el operador ve qué quedó afuera y decide si re-verificarlo."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    datos = json.loads((d / "2020Pdf.json").read_text(encoding="utf-8"))
    datos["pares"].append({"ancla": "dead0dead0", "veredicto": "soportada",
                           "evidencia": '"otra cita" (p. 9)'})
    (d / "2020Pdf.json").write_text(json.dumps(datos), encoding="utf-8")
    (d / "_esperado.json").write_text(json.dumps(
        {"nota": nota.as_posix(), "fuentes": {"2020Pdf": 2, "2019Txt": 1}, "pares": 3}),
        encoding="utf-8")

    with pytest.raises(ws.SidecarError, match="dead0dead0"):
        ws.write(nota, d, fecha="2026-03-01")              # sin el flag: rehúsa, como hoy
    r = ws.write(nota, d, fecha="2026-03-01", descartar_muertas=True)
    assert r["descartadas"] == [("2020Pdf", "dead0dead0")]
    assert r["filas"] == 2, "los pares vivos SÍ se escriben"


def test_el_cli_de_from_multiple_declara_las_descartadas_y_el_mensaje_ofrece_la_salida(toy_vault, capsys):
    """#428 — sin el flag el mensaje de rehúse tiene que NOMBRAR los dos caminos, o el operador
    queda igual de trabado que antes (le pasó dos veces en una sesión, con el error ya anotado)."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    datos = json.loads((d / "2020Pdf.json").read_text(encoding="utf-8"))
    datos["pares"].append({"ancla": "dead0dead0", "veredicto": "soportada", "evidencia": '"x" (p. 9)'})
    (d / "2020Pdf.json").write_text(json.dumps(datos), encoding="utf-8")
    (d / "_esperado.json").write_text(json.dumps(
        {"nota": nota.as_posix(), "fuentes": {"2020Pdf": 2, "2019Txt": 1}, "pares": 3}),
        encoding="utf-8")
    assert ws.main([str(nota), "--from", str(d), "--fecha", "2026-03-01"]) == 1
    salida = capsys.readouterr().out
    assert "--descartar-anclas-muertas" in salida and "reverify_subset" in salida
    assert ws.main([str(nota), "--from", str(d), "--descartar-anclas-muertas",
                    "--fecha", "2026-03-01"]) == 0
    salida = capsys.readouterr().out
    assert "1 par(es) descartado(s)" in salida and "dead0dead0" in salida


def test_el_flag_con_CERO_muertas_declara_el_cero(toy_vault, capsys):
    """#428/D-43 — «0 descartadas» se declara: lo no evaluado y lo evaluado-en-cero piden acciones
    distintas, y acá el operador pidió explícitamente el descarte."""
    nota = _escena(toy_vault)
    d = _fanout(toy_vault, nota, {})
    assert ws.main([str(nota), "--from", str(d), "--descartar-anclas-muertas",
                    "--fecha", "2026-03-01"]) == 0
    assert "0 par(es) descartado(s)" in capsys.readouterr().out


def test_las_guardas_de__rewrite_rows_son_PRECONDICIONES_del_que_lo_llame(toy_vault):
    """#427 — `_rewrite_rows` es el punto de escritura de las dos modalidades de condición, y sus
    dos guardas son precondiciones para cualquier llamador futuro: sin hermano no hay filas que
    reescribir, y sin fecha en el encabezado re-fechar sería una decisión (D-4: resolver una
    condición no es re-verificar). Hoy ningún camino las alcanza —las dos modalidades salen antes
    si no hay cambios— así que se ejercen desde acá, que es lo que las mantiene medibles."""
    nota = _escena(toy_vault)
    with pytest.raises(ws.SidecarError, match="hermano"):
        ws._rewrite_rows(nota, {"a" * 10: "acota: x"}, None, False)
    ws.write(nota, _fanout(toy_vault, nota, {}, condicion="SNR > 50", cond_tipo="acota"),
             fecha="2026-03-01")
    ancla = lb.verif_rows(nota)[0].anchor
    nota.write_text(nota.read_text(encoding="utf-8").replace(
        "## Verificación de citas (2026-03-01)", "## Verificación de citas"), encoding="utf-8")
    with pytest.raises(ws.SidecarError, match="fecha"):
        ws._rewrite_rows(nota, {ancla: "acota: y"}, None, False)


def test_resolver_NO_escribe_si_el_lector_deja_de_reconocer_lo_que_escribe(toy_vault, monkeypatch):
    """#427 — «valida con el lector antes de escribir» es una guarda, no una frase: si la notación y
    su lector se separan otra vez (que es EXACTAMENTE el defecto que este issue arregla), esto
    rehúsa en vez de escribir una celda que después nadie va a poder contar."""
    nota = _escena(toy_vault)
    ws.write(nota, _fanout(toy_vault, nota, {}, condicion="SNR > 50", cond_tipo="acota"),
             fecha="2026-03-01")
    ancla = lb.verif_rows(nota)[0].anchor
    antes = nota.read_bytes()
    monkeypatch.setattr(lb, "condition_resolved", lambda c: False)
    with pytest.raises(ws.SidecarError, match="no se lee como resuelta"):
        ws.resolve_conditions(nota, {ancla: "fila A"})
    assert nota.read_bytes() == antes


def test_el_no_op_de_las_dos_modalidades_NO_pasa_por_el_escritor(toy_vault):
    """#427 — sin cambios no se toca el artefacto: la corrida vacía devuelve su conteo y sale, en
    vez de re-renderizar la tabla para escribir lo mismo. Es lo que hace barato encadenar el
    migrador sobre toda la bóveda (y lo que el dict de retorno declara: sin `fecha` no hubo
    escritura)."""
    nota = _escena(toy_vault)
    ws.write(nota, _fanout(toy_vault, nota, {}, condicion="SNR > 50", cond_tipo="acota"),
             fecha="2026-03-01")
    assert ws.migrate_condition_prefix(nota) == {"migradas": 0, "filas": 2}
    ancla = lb.verif_rows(nota)[0].anchor
    ws.resolve_conditions(nota, {ancla: "fila A"})
    assert ws.resolve_conditions(nota, {ancla: "fila A"}) == {"resueltas": 0, "filas": 2}


def test_el_cli_migra_de_verdad_y_el_dry_run_NO_escribe(toy_vault, capsys):
    """#427 — la modalidad `--migrate-condition-prefix` por CLI, con efecto: hasta acá el CLI sólo
    estaba probado por sus rehúses, así que saltearse la migración entera pasaba limpio. Y el
    `--dry-run` dice qué haría sin tocar el artefacto, que es como se corre sobre una bóveda ajena."""
    nota = _escena(toy_vault)
    ws.write(nota, _fanout(toy_vault, nota, {}, condicion="SNR > 50", cond_tipo="acota"),
             fecha="2026-03-01")
    herm = cfg.verif_sidecar(nota)
    herm.write_text(herm.read_text(encoding="utf-8")
                    .replace("acota: SNR > 50", "acota: acota→resuelta: fila A", 1), encoding="utf-8")
    antes = herm.read_bytes()
    assert ws.main(["--migrate-condition-prefix", "--dry-run", str(nota)]) == 0
    assert "dry-run" in capsys.readouterr().out and herm.read_bytes() == antes
    assert ws.main(["--migrate-condition-prefix", str(nota)]) == 0
    assert "1 celda(s)" in capsys.readouterr().out
    assert lb.verif_counts(lb.verif_rows(nota))["cond_acota_resueltas"] == 1


def test_el_cli_de_condiciones_rehusa_la_nota_QUE_NO_EXISTE(toy_vault, capsys):
    """#427 — la ruta inexistente (un tipeo, o la nota que se renombró) se nombra; sin esto el
    error saldría desde adentro, sobre un archivo que nadie abrió."""
    assert ws.main(["--migrate-condition-prefix", str(cfg.WIKI / "no-existe.md")]) == 2
    assert "no es una nota" in capsys.readouterr().out
