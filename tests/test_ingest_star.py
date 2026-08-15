"""ingest_star: orquestador de la cadena de estrellas (fuente de verdad única del orden)."""
import sys
from types import SimpleNamespace

import pytest

import ingest_star as ist


@pytest.fixture
def fake_run(monkeypatch):
    state = SimpleNamespace(calls=[], rcs={})

    def run(script, *args):
        state.calls.append((script, *args))
        return state.rcs.get(script, 0)
    monkeypatch.setattr(ist, "run", run)
    return state


def run_main(monkeypatch, argv=("test_star",)):
    monkeypatch.setattr(sys, "argv", ["ingest_star.py", *argv])
    return ist.main()


def test_cadena_completa_en_orden(toy_vault, fake_run, monkeypatch):
    assert run_main(monkeypatch) == 0
    assert fake_run.calls == [("query_ads.py", "test_star"),
                              ("fetch_arxiv.py", "test_star"),
                              ("fetch_pdf.py", "test_star"),
                              ("fetch_ground_truth.py", "test_star"),
                              ("make_notes.py", "test_star"),
                              ("extract_fulltext.py", "test_star"),
                              ("check_retractions.py", "--slug", "test_star")]


def test_slug_desconocido_amigable(toy_vault, fake_run, monkeypatch):
    with pytest.raises(SystemExit, match="stars.yaml"):
        run_main(monkeypatch, ("no-existe",))
    assert fake_run.calls == []


def test_aborta_al_primer_fallo(toy_vault, fake_run, monkeypatch):
    fake_run.rcs["fetch_pdf.py"] = 1
    with pytest.raises(SystemExit, match="fetch_pdf.py falló"):
        run_main(monkeypatch)
    assert [c[0] for c in fake_run.calls] == ["query_ads.py", "fetch_arxiv.py", "fetch_pdf.py"]


def test_retraccion_detectada_no_es_fallo_de_cadena(toy_vault, fake_run, monkeypatch):
    fake_run.rcs["check_retractions.py"] = 1
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch)
    assert "retractados" in str(exc.value) and "falló" not in str(exc.value)


# ── guardia de expansión (#37) ───────────────────────────────────────────────

def write_core(toy_vault, slug, n_core, via="chain:citations", start=0):
    """build/<slug>/ads.json con n_core papers core (bibcodes sintéticos)."""
    import json
    d = toy_vault.ROOT / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    recs = [{"bibcode": f"20{i:02d}core...{i:03d}A", "relevant": True, "via": via}
            for i in range(start, start + n_core)]
    (d / "ads.json").write_text(json.dumps({"records": recs}), encoding="utf-8")
    return recs


def with_notes(bibcodes):
    import lib_config as cfg
    from conftest import mk_note
    for b in bibcodes:
        mk_note(cfg.PAPERS, b, {"bibcode": b})


def test_guardia_frena_expansion_antes_de_fetch(toy_vault, fake_run, monkeypatch, capsys):
    """El core saltó de 10 notas a 200 → frena DESPUÉS de query_ads y ANTES de fetch_arxiv."""
    recs = write_core(toy_vault, "test_star", 200)
    with_notes([r["bibcode"] for r in recs[:10]])
    with pytest.raises(SystemExit, match="frenada"):
        run_main(monkeypatch)
    assert fake_run.calls == [("query_ads.py", "test_star")]      # no llegó a bajar nada
    out = capsys.readouterr().out
    assert "EXPANSIÓN" in out and "190 papers NUEVOS" in out and "relevance.require" in out


def test_guardia_yes_continua(toy_vault, fake_run, monkeypatch):
    recs = write_core(toy_vault, "test_star", 200)
    with_notes([r["bibcode"] for r in recs[:10]])
    assert run_main(monkeypatch, ("test_star", "--yes")) == 0
    assert ("fetch_arxiv.py", "test_star") in fake_run.calls


def test_guardia_no_frena_el_primer_ingest(toy_vault, fake_run, monkeypatch):
    """Sin notas previas no hay expansión que medir: el usuario acaba de pedir el sujeto."""
    write_core(toy_vault, "test_star", 500)
    assert run_main(monkeypatch) == 0


def test_guardia_no_frena_un_refresh_normal(toy_vault, fake_run, monkeypatch):
    """+20 papers sobre 100 ya ingestados: ni factor ni volumen alcanzan el umbral."""
    recs = write_core(toy_vault, "test_star", 120)
    with_notes([r["bibcode"] for r in recs[:100]])
    assert run_main(monkeypatch) == 0


def test_guardia_sin_ads_json_no_rompe(toy_vault, fake_run, monkeypatch):
    assert run_main(monkeypatch) == 0
