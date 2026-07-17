"""ingest_topic: despacho por `source`, validaciones de sources:, pending, copia de PDFs."""
import sys
from types import SimpleNamespace

import pytest

import ingest_topic as it
import lib_config as cfg
from conftest import write_yaml


@pytest.fixture
def fake_run(monkeypatch):
    """Reemplaza run(): graba (script, *args) y devuelve el rc configurado por script."""
    state = SimpleNamespace(calls=[], rcs={})

    def run(script, *args):
        state.calls.append((script, *args))
        return state.rcs.get(script, 0)
    monkeypatch.setattr(it, "run", run)
    return state


@pytest.fixture
def fake_notes(monkeypatch):
    state = SimpleNamespace(concepts=[], webs=[])
    monkeypatch.setattr(it.make_notes, "write_concept_note",
                        lambda slug, force=None: state.concepts.append((slug, force)))
    monkeypatch.setattr(it.make_notes, "write_web_paper_note",
                        lambda key, **kw: state.webs.append((key, kw)) or True)
    return state


def topic(source=None, sources=None, area="methods", concept="fastica", **extra):
    entry = {"title": "ICA", "area": area, "concept": concept, **extra}
    if source:
        entry["source"] = source
    if sources is not None:
        entry["sources"] = sources
    write_yaml(cfg.TOPICS_YAML, {"ica": entry})


def run_main(monkeypatch, argv=("ica",)):
    monkeypatch.setattr(sys, "argv", ["ingest_topic.py", *argv])
    return it.main()


# ── despacho ─────────────────────────────────────────────────────────────────

def test_slug_desconocido(toy_vault, fake_run, monkeypatch):
    with pytest.raises(SystemExit, match="desconocido"):
        run_main(monkeypatch, ("no-existe",))


def test_source_invalido(toy_vault, fake_run, monkeypatch):
    topic(source="ftp")
    with pytest.raises(SystemExit, match="source desconocido"):
        run_main(monkeypatch)


def test_cadena_ads_en_orden(toy_vault, fake_run, fake_notes, monkeypatch):
    topic()                                          # sin source → ads
    assert run_main(monkeypatch) == 0
    assert [c[0] for c in fake_run.calls] == ["query_ads.py", "fetch_arxiv.py", "fetch_pdf.py",
                                              "make_notes.py", "extract_fulltext.py",
                                              "check_retractions.py"]
    assert fake_run.calls[0] == ("query_ads.py", "--topic", "ica")
    assert fake_run.calls[3] == ("make_notes.py", "--topic", "ica")


def test_cadena_ads_aborta_al_primer_fallo(toy_vault, fake_run, monkeypatch):
    topic()
    fake_run.rcs["fetch_arxiv.py"] = 1
    with pytest.raises(SystemExit, match="fetch_arxiv.py falló"):
        run_main(monkeypatch)
    assert [c[0] for c in fake_run.calls] == ["query_ads.py", "fetch_arxiv.py"]


def test_ads_con_sources_avisa(toy_vault, fake_run, monkeypatch, capsys):
    topic(sources=[{"key": "2000Hyvarinen", "url": "https://x"}])
    run_main(monkeypatch)
    assert "se ignora en modo ADS" in capsys.readouterr().out


# ── validaciones off-ADS ─────────────────────────────────────────────────────

def test_offads_sin_concept(toy_vault, fake_run, monkeypatch):
    write_yaml(cfg.TOPICS_YAML, {"ica": {"title": "ICA", "area": "methods", "source": "web",
                                         "sources": [{"key": "2000Hyv", "url": "https://x"}]}})
    with pytest.raises(SystemExit, match="`concept`"):
        run_main(monkeypatch)


def test_offads_sin_sources(toy_vault, fake_run, monkeypatch):
    topic(source="web")
    with pytest.raises(SystemExit, match="sources"):
        run_main(monkeypatch)


def test_offads_key_invalida(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "SinAnio", "url": "https://x"}])
    with pytest.raises(SystemExit, match="key inválida"):
        run_main(monkeypatch)


def test_offads_url_y_pdf_ambiguo(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="local-pdfs+web",
          sources=[{"key": "2000Hyvarinen", "url": "https://x", "pdf": "/tmp/x.pdf"}])
    with pytest.raises(SystemExit, match="ambiguo"):
        run_main(monkeypatch)


def test_offads_sin_url_ni_pdf(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2000Hyvarinen"}])
    with pytest.raises(SystemExit, match="no hay de dónde"):
        run_main(monkeypatch)


def test_offads_kind_no_admitido(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2000Hyvarinen", "pdf": "/tmp/x.pdf"}])
    with pytest.raises(SystemExit, match="admite url"):
        run_main(monkeypatch)


# ── flujos off-ADS ───────────────────────────────────────────────────────────

def test_offads_web_llama_fetch_web(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2000Hyvarinen", "url": "https://x",
                                  "title": "ICA", "year": 2000, "n_authors": 2}])
    assert run_main(monkeypatch) == 0
    (script, *args) = fake_run.calls[0]
    assert script == "fetch_web.py"
    assert args[:3] == ["ica", "2000Hyvarinen", "https://x"]
    assert "--concept" in args and "fastica" in args
    assert "--n-authors" in args and "2" in args
    assert "--force" not in args
    assert fake_notes.concepts == [("ica", False)]   # el concept NUNCA se pisa


def test_offads_force_solo_re_baja_fuentes(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2000Hyvarinen", "url": "https://x"}])
    run_main(monkeypatch, ("ica", "--force"))
    (_, *args) = fake_run.calls[0]
    assert "--force" in args
    assert fake_notes.concepts == [("ica", False)]   # --force no llega al concept


def test_offads_web_fallo_aborta_con_aviso(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    topic(source="web", sources=[{"key": "2000Hyvarinen", "url": "https://x"}])
    fake_run.rcs["fetch_web.py"] = 1
    with pytest.raises(SystemExit, match="1 fuente\\(s\\) fallaron"):
        run_main(monkeypatch)
    assert "FALLARON" in capsys.readouterr().out


def test_offads_pending_deriva_sin_fallar(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    topic(source="web", sources=[{"key": "1999Paywall", "pending": "paywall", "doi": "10.1/x"}])
    assert run_main(monkeypatch) == 0
    key, kw = fake_notes.webs[0]
    assert key == "1999Paywall" and kw["pending"] == "paywall"
    assert [c[0] for c in fake_run.calls] == ["check_retractions.py"]   # doi → chequeo igual
    out = capsys.readouterr().out
    assert "Fuentes PENDIENTES" in out and "10.1/x" in out


def test_offads_pdf_copia_y_extrae(toy_vault, fake_run, fake_notes, monkeypatch, tmp_path):
    src = tmp_path / "externo.pdf"
    src.write_bytes(b"%PDF-contenido")
    topic(source="local-pdfs", sources=[{"key": "2000Hyvarinen", "pdf": str(src)}])
    assert run_main(monkeypatch) == 0
    dest = cfg.PDFS / "ica" / "2000Hyvarinen.pdf"
    assert dest.read_bytes() == b"%PDF-contenido"
    assert fake_notes.webs[0][0] == "2000Hyvarinen"
    assert "pending" not in fake_notes.webs[0][1] or not fake_notes.webs[0][1].get("pending")
    assert ("extract_fulltext.py", "ica") in fake_run.calls
    assert "check_retractions.py" not in [c[0] for c in fake_run.calls]   # sin doi


def test_offads_pdf_idempotente(toy_vault, fake_run, fake_notes, monkeypatch, tmp_path, capsys):
    src = tmp_path / "externo.pdf"
    src.write_bytes(b"%PDF-v1")
    topic(source="local-pdfs", sources=[{"key": "2000Hyvarinen", "pdf": str(src)}])
    run_main(monkeypatch)
    src.write_bytes(b"%PDF-v2")
    run_main(monkeypatch)                            # sin --force: no re-copia
    assert (cfg.PDFS / "ica" / "2000Hyvarinen.pdf").read_bytes() == b"%PDF-v1"
    assert "ya existe" in capsys.readouterr().out


def test_offads_pdf_fuente_faltante_falla(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    """Regresión (hallazgo 1): UNA fuente fallida → '1 fuente(s) fallaron' (no 2), y
    extract_fulltext NO corre si ningún PDF quedó en disco."""
    topic(source="local-pdfs", sources=[{"key": "2000Hyvarinen", "pdf": "/no/existe.pdf"}])
    with pytest.raises(SystemExit, match="1 fuente\\(s\\) fallaron"):
        run_main(monkeypatch)
    assert "item salteado" in capsys.readouterr().out
    assert "extract_fulltext.py" not in [c[0] for c in fake_run.calls]


def test_offads_fallo_de_extract_se_reporta_aparte(toy_vault, fake_run, fake_notes, monkeypatch,
                                                   tmp_path):
    """Regresión (hallazgo 1): un fallo de extracción no se cuenta como 'fuente fallida'."""
    src = tmp_path / "externo.pdf"
    src.write_bytes(b"%PDF-x")
    topic(source="local-pdfs", sources=[{"key": "2000Hyvarinen", "pdf": str(src)}])
    fake_run.rcs["extract_fulltext.py"] = 1
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch)
    assert "extract_fulltext.py falló" in str(exc.value)
    assert "fuente(s) fallaron" not in str(exc.value)


def test_offads_pdf_faltante_pero_copia_versionada(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    """--force post-clone sin la fuente externa: la copia de la bóveda se conserva, no es fallo."""
    dest = cfg.PDFS / "ica" / "2000Hyvarinen.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"%PDF-versionado")
    topic(source="local-pdfs", sources=[{"key": "2000Hyvarinen", "pdf": "/no/existe.pdf"}])
    assert run_main(monkeypatch, ("ica", "--force")) == 0
    assert dest.read_bytes() == b"%PDF-versionado"
    assert "conservo la copia" in capsys.readouterr().out


def test_offads_retraccion_detectada_aborta(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2000Hyvarinen", "url": "https://x", "doi": "10.1/x"}])
    fake_run.rcs["check_retractions.py"] = 1
    with pytest.raises(SystemExit, match="retractados"):
        run_main(monkeypatch)
