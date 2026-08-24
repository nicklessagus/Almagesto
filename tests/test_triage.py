"""triage: compuerta de los candidatos del chaining — listar, reportar, persistir descartes (#38)."""
import json
import sys

import pytest
import yaml

import lib_config as cfg
import triage
from conftest import write_yaml


def write_ads(toy_vault, slug="test_star", candidates=None, n_relevant=3):
    d = toy_vault.ROOT / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({
        "kind": "star", "slug": slug, "n_relevant": n_relevant, "records": [],
        "candidates": candidates if candidates is not None else []}), encoding="utf-8")
    return d


def cand(bib, title="un título", cites=0, via="chain:citations", year="2020"):
    return {"bibcode": bib, "title": title, "citation_count": cites, "via": via,
            "year": year, "facets": ["rv"], "abstract": "resumen"}


def seed_topic_offads(slug="gp"):
    """Tema off-ADS declarado en themes.yaml. Hace falta porque `--drop-source` ahora valida que el
    sujeto exista: un registro de un slug inexistente no lo lee nadie."""
    write_yaml(cfg.THEMES_YAML, {slug: {"concept": slug, "area": "methods", "source": "web",
                                        "sources": [{"key": "2006Rasmussen", "url": "https://x"}]}})


def run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["triage.py", *argv])
    return triage.main()


def test_lista_candidatos_por_citas(toy_vault, monkeypatch, capsys):
    write_ads(toy_vault, candidates=[cand("2020a....1A", "poco citado", cites=1),
                                     cand("2020b....1B", "muy citado", cites=99)])
    assert run_main(monkeypatch, ["test_star"]) == 0
    out = capsys.readouterr().out
    assert "2 candidatos pendientes" in out
    assert out.index("muy citado") < out.index("poco citado")


def test_sin_candidatos_no_pide_juicio(toy_vault, monkeypatch, capsys):
    write_ads(toy_vault)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert "nada pendiente" in capsys.readouterr().out


def test_sin_ads_json_error_amigable(toy_vault, monkeypatch):
    with pytest.raises(SystemExit, match="ads.json"):
        run_main(monkeypatch, ["test_star"])


def test_drop_persiste_con_motivo_en_config_versionada(toy_vault, monkeypatch, capsys):
    """#51: el juicio va a vault/config/registro/<slug>.yaml (se commitea), NO a build/ (scratch)."""
    write_ads(toy_vault, candidates=[cand("2023PhDT....1P", "Hunting for New Physics")])
    assert run_main(monkeypatch, ["test_star", "--drop", "2023PhDT....1P",
                                  "--reason", "física de partículas, no toca el sujeto"]) == 0
    reg = cfg.registro_path("test_star")
    assert reg.exists() and reg.parent == cfg.CONFIG / "registro"
    dec = yaml.safe_load(reg.read_text(encoding="utf-8"))["decisiones"]["2023PhDT....1P"]
    assert dec["decision"] == "descartado" and "partículas" in dec["motivo"] and dec["fecha"]
    assert not (cfg.ROOT / "build" / "test_star" / "triage.json").exists()   # ya no se escribe ahí
    assert "versionado" in capsys.readouterr().out


def test_drop_exige_motivo(toy_vault, monkeypatch):
    write_ads(toy_vault, candidates=[cand("2023PhDT....1P")])
    with pytest.raises(SystemExit):
        run_main(monkeypatch, ["test_star", "--drop", "2023PhDT....1P"])


def test_drop_avisa_bibcode_ajeno(toy_vault, monkeypatch, capsys):
    """Descartar algo que no está entre los pendientes (typo o ya decidido) no rompe, pero avisa."""
    write_ads(toy_vault, candidates=[cand("2023PhDT....1P")])
    assert run_main(monkeypatch, ["test_star", "--drop", "2020typo...1X", "--reason", "x"]) == 0
    assert "no están entre los candidatos pendientes" in capsys.readouterr().out


def test_drop_avisa_si_la_clave_ya_tenia_decision(toy_vault, monkeypatch, capsys):
    """`drop_source` avisa antes de pisar ("la piso"); su hermano `drop` no. Los dos carriles
    comparten espacio de claves, así que pisar en silencio borra el motivo y el `origen` de un
    juicio anterior — y el motivo es justamente lo que #51 existe para que no se pierda."""
    d = cfg.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps(
        {"candidates": [{"bibcode": "2020aaa...1..1A", "title": "t"}]}), encoding="utf-8")
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.save_decisiones("test_star", {"2020aaa...1..1A": {
        "decision": "descartado", "motivo": "motivo viejo que no hay que perder en silencio",
        "fecha": "2026-01-01", "origen": "fuente-declarada"}})
    triage.drop("test_star", ["2020aaa...1..1A"], "motivo nuevo")
    out = capsys.readouterr().out
    assert "motivo viejo que no hay que perder en silencio" in out, (
        "se pisó un juicio previo sin decir qué decía")


def test_drop_acumula_decisiones_previas(toy_vault, monkeypatch):
    write_ads(toy_vault, candidates=[cand("2020b....1B")])
    cfg.save_decisiones("test_star", {"2020a....1A": {"decision": "descartado", "motivo": "viejo"}})
    run_main(monkeypatch, ["test_star", "--drop", "2020b....1B", "--reason", "nuevo"])
    dec = yaml.safe_load(cfg.registro_path("test_star").read_text(encoding="utf-8"))["decisiones"]
    assert set(dec) == {"2020a....1A", "2020b....1B"}


def test_el_triage_json_viejo_ya_no_se_lee_solo(toy_vault, monkeypatch):
    """El lector NO mergea el `triage.json` pre-1.9.0: una capa de compatibilidad es complejidad
    permanente, y el juicio viejo tiene un camino explícito (`--migrate`). El riesgo que eso
    introduce —que el archivo quede mudo— lo cubre el detector bloqueante del lint."""
    d = write_ads(toy_vault, candidates=[cand("2020b....1B")])
    (d / "triage.json").write_text(json.dumps({"slug": "test_star", "decisiones": {
        "2020a....1A": {"decision": "descartado", "motivo": "juicio viejo"}}}), encoding="utf-8")
    assert cfg.load_decisiones("test_star") == {}
    run_main(monkeypatch, ["test_star", "--drop", "2020b....1B", "--reason", "nuevo"])
    dec = yaml.safe_load(cfg.registro_path("test_star").read_text(encoding="utf-8"))["decisiones"]
    assert set(dec) == {"2020b....1B"}
    # y el camino explícito sí lo recupera, sin perder el motivo
    run_main(monkeypatch, ["test_star", "--migrate"])
    dec = yaml.safe_load(cfg.registro_path("test_star").read_text(encoding="utf-8"))["decisiones"]
    assert set(dec) == {"2020a....1A", "2020b....1B"}
    assert dec["2020a....1A"]["motivo"] == "juicio viejo"


def test_registro_preserva_la_busqueda_al_dropear(toy_vault, monkeypatch):
    """El registro tiene dos secciones con dueños distintos: `busquedas` las escribe query_ads y
    `decisiones` triage.py — ninguno pisa al otro."""
    write_ads(toy_vault, candidates=[cand("2020b....1B")])
    cfg.save_busqueda("test_star", {"fecha": "2026-08-21", "query": "title:(x)", "n_core": 3})
    run_main(monkeypatch, ["test_star", "--drop", "2020b....1B", "--reason", "ruido"])
    reg = yaml.safe_load(cfg.registro_path("test_star").read_text(encoding="utf-8"))
    assert reg["busquedas"][-1]["n_core"] == 3 and "2020b....1B" in reg["decisiones"]


def test_report_escribe_tabla_en_outputs(toy_vault, monkeypatch):
    write_ads(toy_vault, candidates=[cand("2020b....1B", "Título con | pipe", cites=7)])
    assert run_main(monkeypatch, ["test_star", "--report"]) == 0
    md = (cfg.ROOT / "outputs" / "triage-test_star.md").read_text(encoding="utf-8")
    assert "2020b....1B" in md and "ui.adsabs.harvard.edu" in md
    assert "Título con \\| pipe" in md          # el pipe no rompe la tabla markdown


def test_marca_candidatos_que_ya_tienen_nota(toy_vault, monkeypatch, capsys):
    """#42: un candidato que YA tiene nota en la bóveda (entró por otro slug) se etiqueta ◆ —
    bajado y extraído, se despacha rápido. No se filtra: la decisión sigue siendo por-slug."""
    from conftest import mk_note, write_yaml
    mk_note(cfg.PAPERS, "2020a....1A", {"tags": ["paper"], "bibcode": "2020a....1A"})
    write_ads(toy_vault, candidates=[cand("2020a....1A", "con nota", cites=9),
                                     cand("2020b....1B", "sin nota", cites=1)])
    assert run_main(monkeypatch, ["test_star", "--report"]) == 0
    out = capsys.readouterr().out
    assert "◆ 1 ya con nota en la bóveda" in out
    assert "◆ 2020a....1A" in out and "◆ 2020b....1B" not in out
    md = (cfg.ROOT / "outputs" / "triage-test_star.md").read_text(encoding="utf-8")
    assert "| 9 | ◆ |" in md and "| 1 |  |" in md      # columna ◆ sólo para el que tiene nota


def test_query_ads_lee_los_descartes_persistidos(toy_vault):
    """El contrato entre los dos scripts: lo que triage descarta, query_ads no re-propone."""
    import query_ads as qa
    write_ads(toy_vault)
    cfg.save_decisiones("test_star", {
        "2020a....1A": {"decision": "descartado", "motivo": "ruido"},
        "2020b....1B": {"decision": "aceptado", "motivo": "sí"}})
    assert qa.load_triage("test_star") == {"2020a....1A"}
    assert qa.load_triage("otro_slug") == set()


# ── #81: rechazo de una fuente DECLARADA (el otro carril de curación) ────────

def leer_decisiones(slug="gp"):
    return yaml.safe_load(cfg.registro_path(slug).read_text(encoding="utf-8"))["decisiones"]


def test_drop_source_persiste_sin_ads_json(toy_vault, monkeypatch, capsys):
    """Un tema off-ADS puro NUNCA tiene build/<slug>/ads.json (no hubo query que lo genere), así
    que este carril tiene que funcionar sin él. Misma forma que el descarte del triage, más
    `origen` (qué carril) y el puntero que vuelve resoluble una clave sintética meses después."""
    seed_topic_offads()
    assert run_main(monkeypatch, [
        "gp", "--drop-source", "2006RasmussenWilliams",
        "--reason", "libro de texto general; el capítulo relevante ya está sintetizado en el hub",
        "--pointer", "https://gaussianprocess.org/gpml/"]) == 0
    d = leer_decisiones()["2006RasmussenWilliams"]
    assert d["decision"] == "descartado" and d["origen"] == "fuente-declarada" and d["fecha"]
    assert "capítulo relevante" in d["motivo"]
    assert d["fuente"] == "https://gaussianprocess.org/gpml/"


def test_drop_source_exige_motivo(toy_vault, monkeypatch):
    """Simétrico con --drop: no curar en silencio. El motivo ES lo no regenerable."""
    with pytest.raises(SystemExit):
        run_main(monkeypatch, ["gp", "--drop-source", "2006RasmussenWilliams"])


def test_drop_source_sin_pointer_no_lo_inventa(toy_vault, monkeypatch, capsys):
    seed_topic_offads()
    assert run_main(monkeypatch, ["gp", "--drop-source", "2019Fulano",
                                  "--reason", "no es del tema"]) == 0
    assert "fuente" not in leer_decisiones()["2019Fulano"]
    assert "sin --pointer" in capsys.readouterr().out          # lo avisa, no lo rellena


def test_drop_source_convive_con_el_triage_sin_pisar(toy_vault, monkeypatch):
    """Los dos carriles escriben las MISMAS `decisiones` (reusa el mecanismo, no inventa otro) sin
    pisarse entre sí ni pisar `busqueda`, que es de query_ads. El descarte del chaining NO cambia
    de forma: sin `origen` significa chaining (compatibilidad hacia atrás)."""
    seed_topic_offads()
    seed_topic_offads()
    write_ads(toy_vault, slug="gp", candidates=[cand("2020b....1B")])
    cfg.save_busqueda("gp", {"fecha": "2026-08-21", "n_core": 3})
    run_main(monkeypatch, ["gp", "--drop", "2020b....1B", "--reason", "ruido"])
    run_main(monkeypatch, ["gp", "--drop-source", "2006Rasmussen", "--reason", "libro general"])
    reg = yaml.safe_load(cfg.registro_path("gp").read_text(encoding="utf-8"))
    assert reg["busquedas"][-1]["n_core"] == 3
    assert set(reg["decisiones"]) == {"2020b....1B", "2006Rasmussen"}
    assert "origen" not in reg["decisiones"]["2020b....1B"]
    assert reg["decisiones"]["2006Rasmussen"]["origen"] == "fuente-declarada"


def test_drop_y_drop_source_no_se_mezclan(toy_vault, monkeypatch):
    """Son dos juicios distintos (candidato del chaining vs fuente declarada) y comparten
    --reason: mezclarlos en una corrida escribiría el mismo motivo para los dos.

    El `ads.json` sembrado es parte del test: sin él, `--drop` moría igual en `load_ads` ("corré
    primero la cadena") y el `pytest.raises` pasaba **sin la guarda** — verde por el motivo
    equivocado. Con el archivo puesto, el único SystemExit posible es el del argparse, y el registro
    tiene que quedar intacto."""
    write_ads(toy_vault, slug="gp", candidates=[cand("2020b....1B")])
    with pytest.raises(SystemExit):
        run_main(monkeypatch, ["gp", "--drop", "2020b....1B", "--drop-source", "2006R",
                               "--reason", "x"])
    assert not cfg.registro_path("gp").exists()      # ninguno de los dos carriles escribió


def test_listado_sin_ads_json_muestra_el_juicio_registrado(toy_vault, monkeypatch, capsys):
    """Antes moría con "corré primero la cadena", que para un off-ADS puro es un consejo imposible
    (nunca va a haber ads.json). Ahora lista lo registrado, con motivo, carril y puntero."""
    seed_topic_offads()
    run_main(monkeypatch, ["gp", "--drop-source", "2006Rasmussen", "--reason", "libro general",
                           "--pointer", "https://x"])
    capsys.readouterr()
    assert run_main(monkeypatch, ["gp"]) == 0
    out = capsys.readouterr().out
    assert "1 decisión(es) persistidas" in out and "fuente-declarada" in out
    assert "libro general" in out and "https://x" in out


def test_listado_sin_ads_json_nombra_los_candidatos_pendientes_con_fecha(toy_vault, monkeypatch, capsys):
    """#64: sin `build/` no se puede juzgar, pero el registro versionado SÍ sabe cuántos candidatos
    dejó la última corrida (lo anota `query_ads` en `busqueda.n_candidates`). Negar ese dato y decir
    genéricamente "no se puede juzgar candidatos" reintroduce el falso limpio que #64 cerró: hay que
    nombrarlos, con la fecha de la corrida que los dejó."""
    cfg.save_decisiones("test_star", {"2020a....1A": {"decision": "descartado", "motivo": "ruido"}})
    cfg.save_busqueda("test_star", {"fecha": "2026-08-20", "n_candidates": 3})
    assert run_main(monkeypatch, ["test_star"]) == 0
    out = capsys.readouterr().out
    assert "anotó 3 candidato(s) sin juzgar" in out and "2026-08-20" in out
    assert "no se puede juzgar candidatos hasta re-correr la cadena" not in out


def test_drop_source_rechaza_un_slug_inexistente(toy_vault, monkeypatch):
    """`drop()` valida el slug de rebote (muere en `load_ads`); este carril no leía nada, así que un
    typo escribía un registro huérfano que nadie lee jamás — el juicio se pierde en silencio, que es
    exactamente lo que #81 existe para impedir."""
    with pytest.raises(SystemExit, match="slug desconocido"):
        run_main(monkeypatch, ["gpp", "--drop-source", "2006R", "--reason", "x"])
    assert not cfg.registro_path("gpp").exists()


def test_drop_source_normaliza_las_claves_y_rechaza_la_basura(toy_vault, monkeypatch, capsys):
    """Una clave vacía queda invisible para el aviso de `ingest_theme` (que filtra `if k`), y una
    con espacios no matchea nunca el item de `sources:`. El motivo en blanco esquivaba el
    "no curar en silencio"."""
    seed_topic_offads()
    with pytest.raises(SystemExit, match="--reason"):
        run_main(monkeypatch, ["gp", "--drop-source", "2006R", "--reason", "   "])
    assert run_main(monkeypatch, ["gp", "--drop-source", "", "  2006R  ", "2006R",
                                  "--reason", " no es del tema "]) == 0
    d = leer_decisiones()
    assert list(d) == ["2006R"]                      # normalizada y deduplicada
    assert d["2006R"]["motivo"] == "no es del tema"
    assert "1 fuente(s)" in capsys.readouterr().out   # el conteo dice lo que escribió


def test_drop_source_avisa_si_la_clave_ya_tenia_decision(toy_vault, monkeypatch, capsys):
    """Los dos carriles comparten espacio de claves: pisar el juicio del otro sin decir nada borra
    un motivo que no es regenerable."""
    seed_topic_offads()
    cfg.save_decisiones("gp", {"2006R": {"decision": "aceptado", "motivo": "sí va",
                                         "fecha": "2026-01-01"}})
    run_main(monkeypatch, ["gp", "--drop-source", "2006R", "--reason", "cambié de opinión"])
    out = capsys.readouterr().out
    assert "ya tenía decisión" in out and "sí va" in out


def test_offads_puro_sin_decisiones_no_da_un_consejo_imposible(toy_vault, monkeypatch):
    """Un tema off-ADS NUNCA va a tener ads.json: mandarlo a "corré la cadena" (con un comando que
    además no resuelve su slug, porque busca en stars.yaml) es el consejo imposible que #81 vino a
    sacar; el fallback sólo se activaba si ya había decisiones, o sea nunca al empezar."""
    seed_topic_offads()
    with pytest.raises(SystemExit, match="off-ADS"):
        run_main(monkeypatch, ["gp"])


def test_migrate_consume_el_triage_json_viejo(toy_vault, monkeypatch, capsys):
    """El detector del lint bloquea por EXISTENCIA del archivo: sin borrarlo, correr el único
    comando que el propio mensaje recomienda dejaba el lint en 1 para siempre, sin ninguna acción
    disponible. Borrarlo es lo que el mismo mensaje declara seguro (`build/` es scratch)."""
    legacy = cfg.legacy_triage_path("test_star")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"decisiones": {"2019A....1A": {"decision": "descartado",
                                                                "motivo": "ruido"}}}),
                      encoding="utf-8")
    assert run_main(monkeypatch, ["test_star", "--migrate"]) == 0
    assert not legacy.exists()
    assert cfg.load_decisiones("test_star")["2019A....1A"]["motivo"] == "ruido"


def test_migrate_con_json_valido_pero_no_objeto(toy_vault, monkeypatch):
    legacy = cfg.legacy_triage_path("test_star")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('["2019A....1A"]', encoding="utf-8")
    with pytest.raises(SystemExit, match="no es un objeto JSON"):
        run_main(monkeypatch, ["test_star", "--migrate"])


def test_listado_sin_ads_json_ni_decisiones_sigue_avisando(toy_vault, monkeypatch):
    """Sin juicio registrado el diagnóstico correcto sigue siendo "corré la cadena" — el fallback
    no puede tapar el caso de la estrella a la que le falta el ingest."""
    with pytest.raises(SystemExit, match="ads.json"):
        run_main(monkeypatch, ["test_star"])


def test_show_decisions_con_busqueda_no_mapa_no_crashea(toy_vault, capsys):
    """El lector (`load_registro`) es tolerante y sus dos consumidores no."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("test_star").write_text(
        "busquedas: 2026-08-22\ndecisiones:\n  2020aaa...1..1A:\n    decision: descartado\n",
        encoding="utf-8")
    assert triage.show_decisions("test_star", cfg.load_decisiones("test_star")) == 0


# ── --migrate: consolidar el triage.json viejo (#51) ─────────────────────────

def test_migrate_consolida_sin_esperar_un_drop(toy_vault, monkeypatch, capsys):
    """El juicio pre-1.9.0 no puede depender de que el usuario justo descarte algo: hasta el
    próximo --drop seguiría viviendo sólo en scratch, y un clon lo perdería igual que antes."""
    d = write_ads(toy_vault)
    (d / "triage.json").write_text(json.dumps({"slug": "test_star", "decisiones": {
        "2020a....1A": {"decision": "descartado", "motivo": "ruido", "fecha": "2026-01-01"},
        "2020b....1B": {"decision": "descartado", "motivo": "otro"}}}), encoding="utf-8")
    assert run_main(monkeypatch, ["test_star", "--migrate"]) == 0
    dec = yaml.safe_load(cfg.registro_path("test_star").read_text(encoding="utf-8"))["decisiones"]
    assert set(dec) == {"2020a....1A", "2020b....1B"}
    assert dec["2020a....1A"]["motivo"] == "ruido"          # el motivo viaja, no sólo el bibcode
    assert "2 decisión(es) migradas" in capsys.readouterr().out


def test_migrate_es_idempotente_y_no_pisa_lo_versionado(toy_vault, monkeypatch, capsys):
    d = write_ads(toy_vault)
    (d / "triage.json").write_text(json.dumps({"decisiones": {
        "2020a....1A": {"decision": "descartado", "motivo": "viejo"}}}), encoding="utf-8")
    cfg.save_decisiones("test_star", {"2020a....1A": {"decision": "descartado",
                                                      "motivo": "revisado después"}})
    assert run_main(monkeypatch, ["test_star", "--migrate"]) == 0
    dec = cfg.load_registro("test_star")["decisiones"]
    assert dec["2020a....1A"]["motivo"] == "revisado después"      # gana el registro
    assert "ya estaban en el registro" in capsys.readouterr().out


def test_migrate_sin_legacy_no_rompe(toy_vault, monkeypatch, capsys):
    write_ads(toy_vault)
    assert run_main(monkeypatch, ["test_star", "--migrate"]) == 0
    assert "nada que migrar" in capsys.readouterr().out


def test_migrate_no_borra_un_triage_json_que_no_consolido(toy_vault, monkeypatch, capsys):
    """El `unlink` es correcto cuando el migrador CONSUMIÓ su entrada. Si el JSON no trae la clave
    `decisiones` no se consolidó nada: borrarlo diciendo "ya consolidado" destruye un archivo que
    nadie leyó y cierra el hallazgo del lint con una afirmación falsa."""
    legacy = cfg.ROOT / "build" / "test_star" / "triage.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('{"otra_cosa": 1}', encoding="utf-8")
    triage.migrate("test_star")
    assert legacy.exists(), "se borró un triage.json del que no se consolidó ninguna decisión"


def test_migrate_con_decisiones_escalar_en_el_registro(toy_vault, capsys):
    """`triage.py:194` — `ya = cfg.load_registro(slug).get("decisiones") or {}`.

    El registro es el archivo que el framework **manda editar a mano** (el aviso de #81 dice
    literalmente "sacá la entrada de `decisiones`"). `cfg.load_decisiones` (lib_config:374) ya
    tiene el `isinstance` que hace falta; este lector paralelo del migrador no lo usa. Con
    `decisiones` escalar el `b not in ya` de la línea siguiente se vuelve un **substring match**
    silencioso y el `{**viejas, **ya}` termina en `TypeError: 'str' object is not a mapping` —
    a mitad de una migración que toca el único artefacto no regenerable de la bóveda."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("test_star").write_text(
        yaml.safe_dump({"slug": "test_star", "decisiones": "ninguna"}), encoding="utf-8")
    legacy = cfg.legacy_triage_path("test_star")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps(
        {"decisiones": {"2020a....1A": {"decision": "descartado", "motivo": "ruido"}}}),
        encoding="utf-8")
    assert triage.migrate("test_star") == 0


def test_triage_imprime_el_snippet_estructurado(toy_vault, capsys, monkeypatch):
    """R-2: la forma dura de `extra_core` es aceptable justamente porque el triage imprime el
    snippet listo para pegar — sin eso, aceptar un paper pasaba de una línea a cuatro campos a
    mano, y el costo caía todo sobre la operación más frecuente."""
    write_ads(toy_vault, candidates=[cand("2020cndA...1..1A", "Un candidato", cites=5)])
    monkeypatch.setattr(sys, "argv", ["triage.py", "test_star"])
    assert triage.main() == 0
    out = capsys.readouterr().out
    assert "extra_core:" in out
    assert "- bibcode: 2020cndA...1..1A" in out
    assert "via: triage" in out and "motivo:" in out
