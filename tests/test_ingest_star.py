"""ingest_star: orquestador de la cadena de estrellas (fuente de verdad única del orden)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import ingest_star as ist
import ingest_theme as it
import lib_config as cfg


@pytest.fixture
def fake_run(monkeypatch):
    """Doble de `ingest_theme.run` con **la firma real** (red #3): desde INV-44 acepta `flags=`
    —las escotillas del orquestador—, y un doble que no lo hiciera reventaría con `TypeError` en
    producción mientras la suite queda verde."""
    state = SimpleNamespace(calls=[], rcs={}, flags=[])

    def run(script, *args, flags=()):
        state.calls.append((script, *args))
        state.flags.append((script, list(flags)))
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
                              ("check_retractions.py", "--slug", "test_star"),
                              ("fetch_bibtex.py", "--slug", "test_star")]     # #397, cierra la cadena


def test_handoff_nombra_los_pasos_salteables(toy_vault, fake_run, monkeypatch, capsys):
    """El último print es el hand-off a la capa LLM: es donde el operador lee qué sigue. Los pasos
    que nombra tienen que ser los SALTEABLES del skill —los que no dejan rastro si se omiten—, y el
    contraste (3b, #72) faltaba: la línea saltaba de la extracción a la ficha, que es exactamente el
    orden que ese issue existe para impedir."""
    assert run_main(monkeypatch) == 0
    out = capsys.readouterr().out
    assert "(2b)" in out and "(2c)" in out and "(3b)" in out and "(5b)" in out
    assert "CONTRASTE" in out


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


def test_ingest_star_distingue_rc2(toy_vault, fake_run, monkeypatch):
    """Issue 0.1 — el mensaje deja de mentir. `check_retractions` rc 2 = "no pude chequear"
    (precondición ausente o Crossref caído), NO "detectó papers retractados": hasta 1.23.1
    `ingest_star` traducía CUALQUIER rc≠0 a esa frase, así que el operador salía a revisar notas
    marcadas que no existían mientras la frontera dura quedaba sin verificar. Aborta igual —la
    cadena no certifica lo que no miró— pero diciendo la verdad."""
    fake_run.rcs["check_retractions.py"] = 2
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch)
    msg = str(exc.value)
    assert "retractados" not in msg
    assert "no pudo" in msg or "no pude" in msg


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


# AUD-54: acá vivía `test_guardia_sin_ads_json_no_rompe`, subconjunto estricto de
# `test_cadena_completa_en_orden` — mismas fixtures, mismo setup (tampoco hay `build/<slug>/ads.json`
# allá), misma llamada, y su único assert ya estaba en el otro. No existía cambio que lo pusiera
# rojo sin poner rojo antes a aquél, que además asserta la cadena completa en orden. Borrado.


def test_la_escotilla_del_orquestador_deja_traza(toy_vault, fake_run, monkeypatch):
    """INV-44. `--yes` saltea la guardia de expansión —o sea que **cambia lo que la cadena hizo**—
    pero no es flag de ningún paso: `save_paso` estampa los flags del PASO y cada script se estampa
    a sí mismo, así que la escotilla con más consecuencias era la única sin traza. Viaja por entorno
    (tiene que atravesar el `subprocess.run`) y se estampa con prefijo `orquestador:`."""
    # @inv INV-44
    monkeypatch.setattr(ist, "expansion_guard", lambda slug, yes: None)
    run_main(monkeypatch, ("test_star", "--yes"))
    assert all(f == ["--yes"] for _, f in fake_run.flags), fake_run.flags

    fake_run.flags.clear()
    run_main(monkeypatch, ("test_star",))
    assert all(f == [] for _, f in fake_run.flags), "sin escotilla no se declara ninguna"


def test_save_paso_estampa_la_escotilla_del_orquestador(toy_vault, monkeypatch):
    """La otra punta: el paso, al estamparse, recoge del entorno lo que el orquestador declaró."""
    # @inv INV-44
    monkeypatch.setenv(cfg.FLAGS_ENV, "--yes")
    monkeypatch.setenv(cfg.VIA_ENV, "orquestador")
    cfg.save_paso("test_star", "query_ads", flags=["--rows"])
    entrada = cfg.load_cadena("test_star")[-1]
    assert entrada["flags"] == ["--rows", "orquestador:--yes"]
    assert entrada["via"] == "orquestador"
