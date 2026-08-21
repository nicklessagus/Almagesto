"""triage: compuerta de los candidatos del chaining — listar, reportar, persistir descartes (#38)."""
import json
import sys

import pytest
import yaml

import lib_config as cfg
import triage


def write_ads(toy_vault, slug="test_star", candidates=None, n_relevant=3):
    d = toy_vault.ROOT / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({
        "kind": "star", "slug": slug, "n_relevant": n_relevant, "records": [],
        "candidates": candidates if candidates is not None else []}), encoding="utf-8")
    return d


def cand(bib, title="un título", cites=0, via="chain:citations", year="2020"):
    return {"bibcode": bib, "title": title, "citation_count": cites, "via": via,
            "year": year, "topics": ["rv"], "abstract": "resumen"}


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


def test_drop_acumula_decisiones_previas(toy_vault, monkeypatch):
    write_ads(toy_vault, candidates=[cand("2020b....1B")])
    cfg.save_decisiones("test_star", {"2020a....1A": {"decision": "descartado", "motivo": "viejo"}})
    run_main(monkeypatch, ["test_star", "--drop", "2020b....1B", "--reason", "nuevo"])
    dec = yaml.safe_load(cfg.registro_path("test_star").read_text(encoding="utf-8"))["decisiones"]
    assert set(dec) == {"2020a....1A", "2020b....1B"}


def test_drop_consolida_el_triage_json_viejo(toy_vault, monkeypatch):
    """Migración (#51): una bóveda pre-1.9 tiene el juicio en build/<slug>/triage.json. Se sigue
    leyendo (no se pierde) y el primer --drop lo consolida en el registro versionado."""
    d = write_ads(toy_vault, candidates=[cand("2020b....1B")])
    (d / "triage.json").write_text(json.dumps({"slug": "test_star", "decisiones": {
        "2020a....1A": {"decision": "descartado", "motivo": "juicio viejo"}}}), encoding="utf-8")
    assert cfg.load_decisiones("test_star")["2020a....1A"]["motivo"] == "juicio viejo"
    run_main(monkeypatch, ["test_star", "--drop", "2020b....1B", "--reason", "nuevo"])
    dec = yaml.safe_load(cfg.registro_path("test_star").read_text(encoding="utf-8"))["decisiones"]
    assert set(dec) == {"2020a....1A", "2020b....1B"}      # el viejo sobrevive en el lugar nuevo


def test_registro_preserva_la_busqueda_al_dropear(toy_vault, monkeypatch):
    """El registro tiene dos secciones con dueños distintos: `busqueda` la escribe query_ads y
    `decisiones` triage.py — ninguno pisa al otro."""
    write_ads(toy_vault, candidates=[cand("2020b....1B")])
    cfg.save_busqueda("test_star", {"fecha": "2026-08-21", "query": "title:(x)", "n_core": 3})
    run_main(monkeypatch, ["test_star", "--drop", "2020b....1B", "--reason", "ruido"])
    reg = yaml.safe_load(cfg.registro_path("test_star").read_text(encoding="utf-8"))
    assert reg["busqueda"]["n_core"] == 3 and "2020b....1B" in reg["decisiones"]


def test_report_escribe_tabla_en_outputs(toy_vault, monkeypatch):
    write_ads(toy_vault, candidates=[cand("2020b....1B", "Título con | pipe", cites=7)])
    assert run_main(monkeypatch, ["test_star", "--report"]) == 0
    md = (cfg.ROOT / "outputs" / "triage-test_star.md").read_text(encoding="utf-8")
    assert "2020b....1B" in md and "ui.adsabs.harvard.edu" in md
    assert "Título con \\| pipe" in md          # el pipe no rompe la tabla markdown


def test_marca_candidatos_que_ya_tienen_nota(toy_vault, monkeypatch, capsys):
    """#42: un candidato que YA tiene nota en la bóveda (entró por otro slug) se etiqueta ◆ —
    bajado y extraído, se despacha rápido. No se filtra: la decisión sigue siendo por-slug."""
    from conftest import mk_note
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
