"""check_sources.py — lo DECLARADO en `sources:` contra su `doi` (Crossref) o la primera página del
PDF (#353). Red sin red: el doble de Crossref deriva de la respuesta REAL capturada el 2026-09-04
para 10.1371/journal.pone.0027594 (el caso del issue), recortada a los campos que se leen."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_sources as cs  # noqa: E402
import lib_config as cfg  # noqa: E402
from conftest import write_yaml  # noqa: E402

# Respuesta REAL de Crossref (2026-09-04) para el DOI del issue, recortada. Es el paper de PENDSE;
# la nota de la bóveda decía «Yang», derivado del nombre del archivo `RAICAR-N.pdf`.
PENDSE = {"author": [{"family": "Pendse", "given": "Gautam V.", "sequence": "first"},
                     {"family": "Borsook", "given": "David", "sequence": "additional"}],
          "issued": {"date-parts": [[2011, 12, 12]]},
          "title": ["A Simple and Objective Method for Reproducible Resting State Network (RSN) "
                    "Detection in fMRI"]}


def _crossref(monkeypatch, msg, estado="ok"):
    monkeypatch.setattr(cs.cr, "crossref_message", lambda doi, headers: (msg, estado))


# ── normalización y apellido declarado ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("author,esperado", [
    ("Hyvärinen, A.", "hyvarinen"), ("Pendse et al.", "pendse"), ("Rasmussen & Williams", "rasmussen"),
    ("Gautam V. Pendse", "pendse"), ("Yang", "yang"), ("", ""), (None, ""),
    ("Comon and Jutten", "comon"), ("Koldovský, Z.; Tichavský, P.", "koldovsky"),
])
def test_declared_family_saca_el_primer_apellido(author, esperado):
    assert cs.declared_family(author) == esperado


def test_norm_tira_la_dieresis_suelta_de_pdftotext():
    """Medido: `pdftotext` rinde «Hyvärinen» como `Hyv¨arinen` (diéresis suelta), y con ella el
    apellido «no estaba» en 6 de 7 primeras páginas del mismo autor."""
    assert cs.norm("Hyv¨arinen") == cs.norm("Hyvärinen") == "hyvarinen"
    assert cs.norm("Crame/spl acute/r-Rao") == "crame spl acute r rao"


# ── Crossref ─────────────────────────────────────────────────────────────────────────────────────

def test_crossref_meta_lee_primer_autor_anio_y_titulo():
    assert cs.crossref_meta(PENDSE) == {"family": "Pendse", "year": 2011,
                                        "title": PENDSE["title"][0]}
    assert cs.crossref_meta({}) == {"family": "", "year": None, "title": ""}


def test_el_caso_del_issue_da_autor_falso():
    """#353 — `2011Yang` declaraba a Yang sobre el DOI de Pendse: `autor`, y va a bloquear."""
    declared = {"author": "Yang", "year": 2011, "title": "RAICAR-N: a noise-aware extension of RAICAR"}
    v, det = cs.compare_crossref(declared, cs.crossref_meta(PENDSE))
    assert v == "autor" and "Pendse" in det and "Yang" in det


def test_compare_crossref_distingue_anio_titulo_y_ok():
    found = cs.crossref_meta(PENDSE)
    ok = {"author": "Pendse, G.", "year": 2011, "title": PENDSE["title"][0].upper()}
    assert cs.compare_crossref(ok, found) == ("ok", "")               # el título compara normalizado
    assert cs.compare_crossref({**ok, "year": 2012}, found)[0] == "anio"
    assert cs.compare_crossref({**ok, "title": "Otro título"}, found)[0] == "titulo"
    assert cs.compare_crossref({"author": "", "year": None, "title": ""}, found) == ("ok", "")
    assert cs.compare_crossref(ok, {"family": "", "year": None, "title": ""})[0] == "no-evaluable"


# ── primera página del PDF ───────────────────────────────────────────────────────────────────────

def test_compare_pdf_exige_apellido_y_anio_en_la_pagina():
    page = "Independent Component Analysis\nAapo Hyv¨arinen and Erkki Oja\nNeural Networks 13 (2000)"
    assert cs.compare_pdf({"author": "Hyvärinen, A.", "year": 2000, "title": ""}, page) == ("ok", "")
    assert cs.compare_pdf({"author": "Yang", "year": 2000, "title": ""}, page)[0] == "autor"
    assert cs.compare_pdf({"author": "Hyvarinen", "year": 2004, "title": ""}, page)[0] == "anio"
    assert cs.compare_pdf({"author": "", "year": None, "title": ""}, page)[0] == "no-evaluable"
    assert cs.compare_pdf({"author": "Yang", "year": 2000, "title": ""}, "   ")[0] == "no-evaluable"


def test_pdf_first_page_declara_cuando_no_puede(monkeypatch, tmp_path):
    monkeypatch.setattr(cs.subprocess, "run", lambda *a, **k: pytest.fail("sin herramienta o sin archivo no se lanza nada"))
    f = tmp_path / "a.pdf"; f.write_bytes(b"%PDF")
    monkeypatch.setattr(cs.shutil, "which", lambda x: None)
    assert cs.pdf_first_page(f) is None
    monkeypatch.setattr(cs.shutil, "which", lambda x: "/usr/bin/pdftotext")
    assert cs.pdf_first_page(tmp_path / "no-existe.pdf") is None
    monkeypatch.setattr(cs.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout="Pendse 2011"))
    assert cs.pdf_first_page(f) == "Pendse 2011"
    monkeypatch.setattr(cs.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=""))
    assert cs.pdf_first_page(f) is None


# ── check_item: los dos carriles y el fallback ───────────────────────────────────────────────────

def test_check_item_con_doi_va_por_crossref(toy_vault, monkeypatch):
    _crossref(monkeypatch, PENDSE)
    rec = cs.check_item({"key": "2011Yang", "doi": "10.1371/journal.pone.0027594", "author": "Yang",
                         "year": 2011, "title": "RAICAR-N"}, "ica")
    assert rec["via"] == "crossref" and rec["veredicto"] == "autor"
    assert rec["declarado"] == {"author": "Yang", "year": 2011, "title": "RAICAR-N"}
    assert rec["encontrado"]["family"] == "Pendse" and rec["fecha"]


def test_check_item_sin_registro_en_crossref_cae_al_pdf(toy_vault, monkeypatch):
    """Medido: 5 de 32 DOIs de una bóveda son `10.48550/arXiv.*`, que Crossref no registra. Sin el
    fallback quedaban `no-evaluable` teniendo el PDF en disco."""
    _crossref(monkeypatch, None, "sin-registro")
    pdf = cfg.PDFS / "ica" / "2015Voss.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True); pdf.write_bytes(b"%PDF")
    monkeypatch.setattr(cs, "pdf_first_page", lambda p: "Voss, Belkin, Saul 2015")
    rec = cs.check_item({"key": "2015Voss", "doi": "10.48550/arxiv.1502.04148", "author": "Voss",
                         "year": 2015}, "ica")
    assert rec["via"] == "pdf" and rec["veredicto"] == "ok"


def test_check_item_sin_doi_ni_pdf_es_no_evaluable_con_motivo(toy_vault, monkeypatch):
    monkeypatch.setattr(cs.cr, "crossref_message",
                        lambda *a, **k: pytest.fail("sin doi no se consulta Crossref"))
    rec = cs.check_item({"key": "2001X", "author": "X", "year": 2001}, "ica")
    assert rec["veredicto"] == "no-evaluable" and "sin PDF" in rec["detalle"]


def test_resolve_pdf_path_prefiere_la_copia_de_la_boveda(toy_vault):
    copia = cfg.PDFS / "ica" / "2012W.pdf"
    copia.parent.mkdir(parents=True, exist_ok=True); copia.write_bytes(b"%PDF")
    assert cs.resolve_pdf_path({"key": "2012W", "pdf": "/otro/lado.pdf"}, "ica") == copia
    assert cs.resolve_pdf_path({"key": "2013W", "pdf": "/otro/lado.pdf"}, "ica") == Path("/otro/lado.pdf")
    assert cs.resolve_pdf_path({"key": "2013W", "pdf": "vault/raw/x.pdf"}, "ica") == cfg.ROOT / "vault/raw/x.pdf"
    assert cs.resolve_pdf_path({"key": "2014W"}, "ica") is None


# ── run: registra y no toca la config ────────────────────────────────────────────────────────────

def _tema(**items):
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods",
                                         "source": "local-pdfs",
                                         "sources": [{"key": "2011Yang", "doi": "10.1371/x",
                                                      "author": "Yang", "year": 2011, "pdf": "x.pdf",
                                                      "via": "usuario", "motivo": "m"}]}})


def test_run_persiste_en_el_registro_y_no_reescribe_sources(toy_vault, monkeypatch, capsys):
    """#353 — reporta y registra; `sources:` es curación versionada y no se toca (misma doctrina
    que `--accept-source`). `--dry-run` mide sin escribir."""
    _tema(); _crossref(monkeypatch, PENDSE)
    antes = cfg.THEMES_YAML.read_bytes()
    recs = cs.run("ica", dry_run=True)
    assert recs["2011Yang"]["veredicto"] == "autor"
    assert not cfg.registro_path("ica").exists(), "dry-run no escribe"
    recs = cs.run("ica")
    reg = cfg.load_registro("ica")["fuentes_chequeadas"]
    assert reg["2011Yang"]["veredicto"] == "autor" and reg["2011Yang"]["declarado"]["author"] == "Yang"
    assert cfg.THEMES_YAML.read_bytes() == antes
    out = capsys.readouterr().out
    assert "autor 1" in out and "⛔ 2011Yang" in out


def test_main_dry_run(toy_vault, monkeypatch):
    _tema(); _crossref(monkeypatch, PENDSE)
    assert cs.main(["ica", "--dry-run"]) == 0
    assert not cfg.registro_path("ica").exists()


def test_run_sin_fuentes_validas_no_escribe_el_registro(toy_vault, monkeypatch):
    """Sin items con `key` no hay nada que cruzar: ni red ni registro (un `fuentes_chequeadas: {}`
    se leería como «se cruzaron todas»)."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods",
                                         "source": "web", "sources": ["suelto", {"url": "https://x"}]}})
    monkeypatch.setattr(cs.cr, "crossref_message", lambda *a, **k: pytest.fail("nada que consultar"))
    assert cs.run("ica") == {}
    assert not cfg.registro_path("ica").exists()
