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
                              ("check_retractions.py",)]


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
