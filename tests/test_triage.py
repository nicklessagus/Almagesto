"""triage: compuerta de los candidatos del chaining — listar, reportar, persistir descartes (#38)."""
import json
import sys

import pytest

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


def test_drop_persiste_con_motivo(toy_vault, monkeypatch, capsys):
    d = write_ads(toy_vault, candidates=[cand("2023PhDT....1P", "Hunting for New Physics")])
    assert run_main(monkeypatch, ["test_star", "--drop", "2023PhDT....1P",
                                  "--reason", "física de partículas, no toca el sujeto"]) == 0
    data = json.loads((d / "triage.json").read_text())
    dec = data["decisiones"]["2023PhDT....1P"]
    assert dec["decision"] == "descartado" and "partículas" in dec["motivo"] and dec["fecha"]


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
    d = write_ads(toy_vault, candidates=[cand("2020b....1B")])
    (d / "triage.json").write_text(json.dumps({"slug": "test_star", "decisiones": {
        "2020a....1A": {"decision": "descartado", "motivo": "viejo"}}}), encoding="utf-8")
    run_main(monkeypatch, ["test_star", "--drop", "2020b....1B", "--reason", "nuevo"])
    dec = json.loads((d / "triage.json").read_text())["decisiones"]
    assert set(dec) == {"2020a....1A", "2020b....1B"}


def test_report_escribe_tabla_en_outputs(toy_vault, monkeypatch):
    write_ads(toy_vault, candidates=[cand("2020b....1B", "Título con | pipe", cites=7)])
    assert run_main(monkeypatch, ["test_star", "--report"]) == 0
    md = (cfg.ROOT / "outputs" / "triage-test_star.md").read_text(encoding="utf-8")
    assert "2020b....1B" in md and "ui.adsabs.harvard.edu" in md
    assert "Título con \\| pipe" in md          # el pipe no rompe la tabla markdown


def test_query_ads_lee_los_descartes_persistidos(toy_vault):
    """El contrato entre los dos scripts: lo que triage descarta, query_ads no re-propone."""
    import query_ads as qa
    d = write_ads(toy_vault)
    (d / "triage.json").write_text(json.dumps({"decisiones": {
        "2020a....1A": {"decision": "descartado", "motivo": "ruido"},
        "2020b....1B": {"decision": "aceptado", "motivo": "sí"}}}), encoding="utf-8")
    assert qa.load_triage("test_star") == {"2020a....1A"}
    assert qa.load_triage("otro_slug") == set()
