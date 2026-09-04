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
    page = ("Independent Component Analysis\nAapo Hyv¨arinen and Erkki Oja\nNeural Networks 13 (2000)\n"
            + "abstract " * 60)          # una primera página real supera el mínimo de `is_legible`
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
    monkeypatch.setattr(cs, "pdf_first_page", lambda p: "Voss, Belkin, Saul 2015 " + "abstract " * 60)
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


# ── seguimiento de #353 (validación en la instancia): tres falsos del carril PDF y del apellido ──

def test_primera_pagina_ilegible_es_no_evaluable_no_autor():
    """Validación en la instancia: los cuatro PDFs de Hyvärinen salen como glifos (fuentes sin
    ToUnicode) y el carril decía «falta el apellido». `is_legible` ya los marca como mojibake."""
    mojibake = "\u00c3\u00bf\u00c2\u00a7\u00e2" * 200
    v, det = cs.compare_pdf({"author": "Hyv\u00e4rinen", "year": 2001, "title": ""}, mojibake)
    assert v == "no-evaluable" and "ilegible" in det, (v, det)


def test_digito_de_afiliacion_pegado_al_apellido_no_es_autor_falso():
    """Validación en la instancia: `G\u00f3mez-Herrero1` (el superíndice de afiliación pegado por
    pdftotext) daba «falta el apellido»."""
    page = ("Independent Component Analysis of EEG\nG. G\u00f3mez-Herrero1, Z. Koldovsk\u00fd2, "
            "P. Tichavsk\u00fd2\n2007 IEEE " + "x " * 200)
    assert cs.compare_pdf({"author": "G\u00f3mez-Herrero", "year": 2007, "title": ""}, page) == ("ok", "")


@pytest.mark.parametrize("declarado,crossref,esperado", [
    ("Le Bihan", "Le Bihan", True), ("VanDerBaan", "van der Baan", True), ("Bihan", "Le Bihan", True),
    ("G\u00f3mez-Herrero", "G\u00f3mez-Herrero", True), ("Gomez", "G\u00f3mez-Herrero", False),
    ("Yang", "Pendse", False),
])
def test_family_match_tolera_apellidos_compuestos(declarado, crossref, esperado):
    """Validación en la instancia: `declared_family` se quedaba con el último token, así que un
    apellido compuesto (Le Bihan, van der Baan) bloqueaba contra Crossref siendo correcto."""
    assert cs.family_match(declarado, crossref) is esperado
    if esperado:
        assert cs.compare_crossref({"author": declarado, "year": None, "title": ""},
                                   {"family": crossref, "year": None, "title": ""})[0] != "autor"


# ── #392 (3 y 4) · el `.bib` del usuario y el snapshot web como carriles ─────────────────────────

BIB = """@article{vrabie2006,
  author = {Vrabie, Valeriu and Le Bihan, Nicolas and Mars, J\\'er\\^ome},
  title = {{Multicomponent} wave separation using {HOSVD}/unimodal-{ICA} subspace method},
  journal = {Geophysics}, year = {2006}, doi = {10.1190/1.2335387},
  file = {VLM06 (subspace method).pdf}
}

@inproceedings{vollgraf2001,
  author = "Roland Vollgraf and Klaus Obermayer",
  title = "Multi-dimensional {ICA} to separate correlated sources",
  year = 2001,
}
"""


def test_bib_entries_parsea_llaves_comillas_y_and():
    es = cs.bib_entries.__wrapped__ if hasattr(cs.bib_entries, "__wrapped__") else None
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "biblio.bib"; p.write_text(BIB, encoding="utf-8")
        es = cs.bib_entries(p)
    assert [e["clave"] for e in es] == ["vrabie2006", "vollgraf2001"]
    assert es[0]["doi"] == "10.1190/1.2335387" and es[0]["file"] == "VLM06 (subspace method).pdf"
    assert es[0]["title"].startswith("Multicomponent wave separation")
    assert cs.bib_meta(es[0]) == {"family": "Vrabie", "year": 2006,
                                  "title": es[0]["title"]}
    assert cs.bib_meta(es[1])["family"] == "Vollgraf" and cs.bib_meta(es[1])["year"] == 2001
    assert cs.bib_entries(pathlib.Path("/no/existe.bib")) == []


def test_bib_match_por_doi_archivo_o_titulo_nunca_por_autor(tmp_path):
    p = tmp_path / "b.bib"; p.write_text(BIB, encoding="utf-8")
    es = cs.bib_entries(p)
    assert cs.bib_match({"doi": "https://doi.org/10.1190/1.2335387"}, es)["clave"] == "vrabie2006"
    assert cs.bib_match({"pdf": "/lib/VLM06 (subspace method).pdf"}, es)["clave"] == "vrabie2006"
    assert cs.bib_match({"title": "multi-dimensional ica to separate correlated sources"}, es)["clave"] == "vollgraf2001"
    assert cs.bib_match({"author": "Vrabie"}, es) is None


def test_el_caso_de_392_lo_caza_el_bib_al_lado_del_pdf(toy_vault, tmp_path, monkeypatch):
    """#392 — `2006VanDerBaan` declaraba a van der Baan; el `.bib` del usuario, en la misma carpeta
    que el PDF, decía Vrabie. Crossref no hacía falta: el carril es offline y bloquea como Crossref."""
    (tmp_path / "biblio.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "VLM06 (subspace method).pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(cs.cr, "crossref_message", lambda doi, headers: (None, "sin-registro"))
    rec = cs.check_item({"key": "2006VanDerBaan", "author": "VanDerBaan", "year": 2006,
                         "doi": "10.1190/1.2335387", "pdf": str(tmp_path / "VLM06 (subspace method).pdf")}, "ica")
    assert rec["via"] == "bib" and rec["veredicto"] == "autor" and "Vrabie" in rec["detalle"]
    assert rec["encontrado"]["bib"] == "biblio.bib"


def test_sin_bib_al_lado_el_carril_no_existe(tmp_path):
    assert cs.bib_files_near({"pdf": str(tmp_path / "x.pdf")}) == []
    assert cs.bib_files_near({}) == []


def test_una_url_se_cruza_contra_el_snapshot_web(toy_vault, monkeypatch):
    """#392 (4) — una fuente web no tenía contra qué cruzar. El snapshot que `fetch_web` guarda
    arranca con el título de la página: apellido y año tienen que estar ahí. Nunca bloquea."""
    monkeypatch.setattr(cs.cr, "crossref_message", lambda *a, **k: pytest.fail("sin doi"))
    d = cfg.FULLTEXT / "ica"; d.mkdir(parents=True, exist_ok=True)
    (d / "2015Shlens.txt").write_text(
        f"{cfg.FULLTEXT_WEB_MARK} (off-ADS), determinista para citar/verificar\n"
        "source_url : https://x\nretrieved  : 2026-09-04 (UTC)\ncitekey    : 2015Shlens\n"
        "# ---- contenido extraído (defuddle) ----\n\n# A Tutorial on Independent Component Analysis\n\n"
        "Jonathon Shlens, 2014\n" + "texto " * 120, encoding="utf-8")
    rec = cs.check_item({"key": "2015Shlens", "url": "https://x", "author": "Shlens", "year": 2014}, "ica")
    assert rec["via"] == "web" and rec["veredicto"] == "ok", rec
    rec = cs.check_item({"key": "2015Shlens", "url": "https://x", "author": "Pendse", "year": 2014}, "ica")
    assert rec["via"] == "web" and rec["veredicto"] == "autor" and "snapshot" in rec["detalle"]
    assert cs.web_snapshot({"key": "2099Nada"}, "ica") is None


def test_las_guardas_de_los_carriles_nuevos_no_miran_donde_no_deben(toy_vault, tmp_path, monkeypatch):
    """Sin `pdf:` declarado no se globea la raíz del repo; una clave vacía no lee `<slug>/.txt`;
    un `.txt` que no es snapshot web (es un PDF extraído) no entra al carril web."""
    monkeypatch.setattr(cs.cfg, "ROOT", tmp_path / "repo")          # sin `pdf:`, `Path("")` resolvería
    (tmp_path / "repo").mkdir()                                       # al PADRE de la raíz: ahí va la trampa
    (tmp_path / "trampa.bib").write_text("@article{x, author={Y}}", encoding="utf-8")
    assert cs.bib_files_near({}) == [] and cs.bib_files_near({"pdf": ""}) == []
    d = cfg.FULLTEXT / "ica"; d.mkdir(parents=True, exist_ok=True)
    (d / ".txt").write_text(f"{cfg.FULLTEXT_WEB_MARK}\n# ---- contenido extraído (defuddle) ----\nx",
                            encoding="utf-8")
    assert cs.web_snapshot({"key": ""}, "ica") is None
    (d / "2001HKO.txt").write_text("# Almagesto — fulltext por pdftotext\nprosa\n", encoding="utf-8")
    assert cs.web_snapshot({"key": "2001HKO"}, "ica") is None
