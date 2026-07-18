"""make_notes: stubs (star/concept/paper/web), retro-linkeo add-only, unpend, excluded_table.

El invariante más importante acá es el del header del script: idempotente, NUNCA pisa la
extracción LLM salvo --force; la única excepción es el merge add-only de seeds.
"""
import json

import pytest
import yaml

import lib_config as cfg
import make_notes as mn
from conftest import mk_note, read_fm, write_yaml

GT = {"star": "Estrella Test", "slug": "test_star",
      "host": {"spectral_type": "G8V", "teff_K": 5344, "dist_pc": 3.65, "st_rotp_days": 34.0},
      "planets": [
          {"letter": "b", "P_days": 20.0, "K_ms": 1.0, "e": 0.1, "mass_earth": 2.0, "status": "confirmed"},
          {"letter": "c", "P_days": 49.3, "K_ms": 1.2, "e": 0.0, "mass_earth": 3.1, "status": "confirmed"},
      ]}


def rec(bib, relevant=True, arxiv=None, cites=0, title="Un título", topics=("actividad",),
        doctype="article"):
    return {"bibcode": bib, "title": title, "authors": ["Ana Pérez", "Bob"], "year": "2020",
            "abstract": "Abstract de prueba", "arxiv_id": arxiv, "doi": "10.1/x", "bibstem": "ApJ",
            "topics": list(topics) if relevant else [], "relevant": relevant,
            "citation_count": cites, "doctype": doctype}


def ads_json(records, slug="test_star"):
    d = cfg.ROOT / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"records": records}), encoding="utf-8")


def seed_topic(slug="gp", area="methods", concept="gaussian-processes"):
    write_yaml(cfg.TOPICS_YAML, {slug: {"title": "Gaussian processes", "area": area, "concept": concept,
                                        "aliases": ["análisis de componentes"]}})


# ── helpers básicos ──────────────────────────────────────────────────────────

def test_fm_roundtrip():
    out = mn.fm({"a": 1, "b": [1, 2]})
    assert out.startswith("---\n") and out.endswith("---\n")
    assert yaml.safe_load(out.split("---")[1]) == {"a": 1, "b": [1, 2]}


def test_safe_name():
    assert mn.safe_name("astro-ph/9605059") == "astro-ph_9605059"
    assert mn.safe_name("2020ApJ...1..1A") == "2020ApJ...1..1A"


def test_parse_year_tolerante(capsys):
    """Regresión (hallazgo 2): metadata off-ADS no numérica no aborta la cadena."""
    assert mn.parse_year(2020) == 2020
    assert mn.parse_year("2020") == 2020
    assert mn.parse_year("2020a") == 2020
    assert mn.parse_year(None) is None
    assert mn.parse_year("in press") is None
    assert "year no numérico" in capsys.readouterr().out
    assert mn.parse_int("2", "n_authors") == 2
    assert mn.parse_int("dos", "n_authors") is None
    assert mn.parse_int(None, "n_authors") is None


def test_web_note_year_no_numerico_no_crashea(toy_vault):
    """Regresión (hallazgo 2): '--year \"in press\"' creaba un ValueError crudo."""
    assert mn.write_web_paper_note("2020Smith", slug="gp", url="https://x",
                                   year="in press", n_authors="dos") is True
    fm = read_fm(toy_vault.PAPERS / "2020Smith.md")
    assert fm["year"] is None and fm["n_authors"] is None


# ── merge_frontmatter_list (retro-linkeo add-only) ───────────────────────────

def test_merge_lista_inline_vacia(toy_vault):
    p = mk_note(toy_vault.PAPERS, "n", {"bibcode": "x", "stars": [], "tags": ["paper"]}, "body\n")
    assert mn.merge_frontmatter_list(p, "stars", ["Estrella Test"]) is True
    assert read_fm(p)["stars"] == ["Estrella Test"]


def test_merge_lista_inline_con_items(toy_vault):
    p = toy_vault.PAPERS / "n.md"
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nbibcode: x\nstars: [Otra Estrella]\n---\nbody\n", encoding="utf-8")
    assert mn.merge_frontmatter_list(p, "stars", ["Estrella Test"]) is True
    assert read_fm(p)["stars"] == ["Otra Estrella", "Estrella Test"]


def test_merge_lista_en_bloque_preserva_indent(toy_vault):
    p = toy_vault.PAPERS / "n.md"
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nbibcode: x\nthesis_links:\n  - a\ntags:\n- paper\n---\nbody\n",
                 encoding="utf-8")
    assert mn.merge_frontmatter_list(p, "thesis_links", ["b"]) is True
    text = p.read_text(encoding="utf-8")
    assert "\n  - a\n  - b\n" in text                 # indent preservado
    assert read_fm(p)["thesis_links"] == ["a", "b"]
    assert read_fm(p)["tags"] == ["paper"]            # el resto intacto


def test_merge_campo_null_se_normaliza(toy_vault):
    p = toy_vault.PAPERS / "n.md"
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nstars: null\nother: 1\n---\nbody\n", encoding="utf-8")
    assert mn.merge_frontmatter_list(p, "stars", ["A"]) is True
    assert read_fm(p)["stars"] == ["A"] and read_fm(p)["other"] == 1


def test_merge_no_toca_cuando_ya_esta(toy_vault):
    p = mk_note(toy_vault.PAPERS, "n", {"stars": ["Estrella Test"]}, "body\n")
    before = p.read_text(encoding="utf-8")
    assert mn.merge_frontmatter_list(p, "stars", ["Estrella Test"]) is False
    assert p.read_text(encoding="utf-8") == before


def test_merge_casos_que_no_debe_tocar(toy_vault):
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    sin_campo = mk_note(toy_vault.PAPERS, "a", {"bibcode": "x"}, "")
    assert mn.merge_frontmatter_list(sin_campo, "stars", ["A"]) is False
    escalar = toy_vault.PAPERS / "b.md"
    escalar.write_text("---\nstars: una-cadena\n---\n", encoding="utf-8")
    assert mn.merge_frontmatter_list(escalar, "stars", ["A"]) is False
    sin_fm = toy_vault.PAPERS / "c.md"
    sin_fm.write_text("sin frontmatter", encoding="utf-8")
    assert mn.merge_frontmatter_list(sin_fm, "stars", ["A"]) is False


def test_merge_preserva_el_resto_byte_a_byte(toy_vault):
    p = toy_vault.PAPERS / "n.md"
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    original = "---\nbibcode: x\nstars: []\ntags:\n- paper\n---\n# Cuerpo\n\nExtracción LLM valiosa.\n"
    p.write_text(original, encoding="utf-8")
    mn.merge_frontmatter_list(p, "stars", ["Estrella Test"])
    esperado = original.replace("stars: []", "stars: [Estrella Test]")
    assert p.read_text(encoding="utf-8") == esperado


# ── excluded_table ───────────────────────────────────────────────────────────

def test_excluded_sin_ads_json(toy_vault):
    assert mn.excluded_table("test_star") == ""


def test_excluded_todo_core(toy_vault):
    ads_json([rec("2020a....1..1A")])
    assert mn.excluded_table("test_star") == ""


def test_excluded_top_n_y_escapes(toy_vault):
    noncore = [rec(f"2020n....{i:02d}.nA", relevant=False, cites=i) for i in range(12)]
    noncore[11]["title"] = "Título con | pipe y [brackets] adentro que rompe tablas markdown"
    ruido = rec("2020ruid....1R", relevant=False, cites=100, doctype="catalog")
    ruido["topics"] = ["actividad"]                   # no-core por doctype, no por tópico
    ads_json(noncore + [ruido])
    tabla = mn.excluded_table("test_star")
    assert tabla.count("| [") == mn.EXCLUDED_TOP_N    # top-N filas
    assert "+ 3 más excluidos" in tabla
    assert r"\|" in tabla and r"\[brackets\]" in tabla
    assert "doctype: catalog" in tabla and "sin tópico" in tabla


# ── write_star_note ──────────────────────────────────────────────────────────

def test_star_note_desde_ground_truth(toy_vault, capsys):
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps(GT), encoding="utf-8")
    mn.write_star_note("test_star", force=False)
    fm = read_fm(toy_vault.STARS / "test_star.md")
    assert fm["name"] == "Estrella Test" and fm["slug"] == "test_star"
    assert fm["P_rot_days"] == 34.0 and fm["teff_K"] == 5344
    assert [p["letter"] for p in fm["planets"]] == ["b", "c"]
    assert fm["planets"][0]["K_ms"] == 1.0 and fm["planets"][0]["mass_earth"] == 2.0
    assert fm["tags"] == ["star"]
    assert fm["generator"].startswith("Almagesto v")


def test_star_note_sin_ground_truth(toy_vault):
    mn.write_star_note("test_star", force=False)
    assert read_fm(toy_vault.STARS / "test_star.md")["planets"] == []


def test_star_note_idempotente(toy_vault):
    mn.write_star_note("test_star", force=False)
    dest = toy_vault.STARS / "test_star.md"
    dest.write_text("EXTRACCIÓN LLM", encoding="utf-8")
    mn.write_star_note("test_star", force=False)
    assert dest.read_text(encoding="utf-8") == "EXTRACCIÓN LLM"
    mn.write_star_note("test_star", force=True)
    assert dest.read_text(encoding="utf-8") != "EXTRACCIÓN LLM"


# ── write_concept_note ───────────────────────────────────────────────────────

def test_concept_note_methods(toy_vault):
    seed_topic()
    mn.write_concept_note("gp", force=False)
    dest = toy_vault.CONCEPTS / "methods" / "gaussian-processes.md"
    fm = read_fm(dest)
    assert fm["name"] == "Gaussian processes" and "status" not in fm
    assert fm["aliases"] == ["análisis de componentes"]
    assert fm["tags"] == ["methods", "thesis"]
    # ficha-método: la tabla junta también por methods: (retro-link)
    assert 'contains(methods, "gaussian-processes")' in dest.read_text(encoding="utf-8")


def test_concept_note_hypotheses_lleva_status(toy_vault):
    seed_topic(area="hypotheses")
    mn.write_concept_note("gp", force=False)
    dest = toy_vault.CONCEPTS / "hypotheses" / "gaussian-processes.md"
    assert read_fm(dest)["status"] == "active"
    assert 'contains(methods,' not in dest.read_text(encoding="utf-8")


def test_concept_note_area_no_declarada_avisa_pero_crea(toy_vault, capsys):
    seed_topic(area="zzz")
    mn.write_concept_note("gp", force=False)
    assert "no está en concept_areas" in capsys.readouterr().out
    assert (toy_vault.CONCEPTS / "zzz" / "gaussian-processes.md").exists()


def test_concept_note_sin_area_o_concept_error_amigable(toy_vault):
    """Guard de config: entrada de topics.yaml incompleta → mensaje amigable, no KeyError."""
    write_yaml(cfg.TOPICS_YAML, {"gp": {"title": "Gaussian processes", "concept": "gaussian-processes"}})
    with pytest.raises(SystemExit, match="'gp' no tiene `area`"):
        mn.write_concept_note("gp", force=False)
    write_yaml(cfg.TOPICS_YAML, {"gp": {"title": "Gaussian processes", "area": "methods"}})
    with pytest.raises(SystemExit, match="'gp' no tiene `concept`"):
        mn.write_concept_note("gp", force=False)


def test_concept_note_idempotente(toy_vault):
    seed_topic()
    mn.write_concept_note("gp", force=False)
    dest = toy_vault.CONCEPTS / "methods" / "gaussian-processes.md"
    dest.write_text("SÍNTESIS LLM", encoding="utf-8")
    mn.write_concept_note("gp", force=False)
    assert dest.read_text(encoding="utf-8") == "SÍNTESIS LLM"


# ── write_paper_notes ────────────────────────────────────────────────────────

def test_paper_notes_estrella(toy_vault):
    ads_json([rec("2020conA...1..1A", arxiv="2101.00001"),
              rec("1990preB....1..1B"),
              rec("2020nonC....1..1C", relevant=False)])
    # verdad de disco: sólo el PDF realmente bajado se linkea (la cadena corre fetch_* antes)
    pdf_dir = toy_vault.PDFS / "test_star"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / "2020conA...1..1A.pdf").write_bytes(b"%PDF")
    mn.write_paper_notes("test_star", include_all=False, force=False)
    assert not (toy_vault.PAPERS / "2020nonC....1..1C.md").exists()
    fm_a = read_fm(toy_vault.PAPERS / "2020conA...1..1A.md")
    assert fm_a["stars"] == ["Estrella Test"]
    assert fm_a["relevance"] == "high" and fm_a["thesis_links"] == []
    assert fm_a["pdf"] == "../../raw/pdfs/test_star/2020conA...1..1A.pdf"
    assert fm_a["first_author"] == "Ana Pérez" and fm_a["n_authors"] == 2
    assert read_fm(toy_vault.PAPERS / "1990preB....1..1B.md")["pdf"] is None


def test_paper_notes_pdf_es_verdad_de_disco(toy_vault):
    """Con arXiv pero SIN el PDF bajado → pdf null (antes quedaba un puntero roto que el
    lint marcaba 'apunta a archivo inexistente'); sin arXiv pero CON PDF (fetch_pdf) → linkeado."""
    ads_json([rec("2020conA...1..1A", arxiv="2101.00001"),
              rec("1978oldW...1..1W")])
    pdf_dir = toy_vault.PDFS / "test_star"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / "1978oldW...1..1W.pdf").write_bytes(b"%PDF")     # bajado por fetch_pdf
    mn.write_paper_notes("test_star", include_all=False, force=False)
    assert read_fm(toy_vault.PAPERS / "2020conA...1..1A.md")["pdf"] is None
    assert read_fm(toy_vault.PAPERS / "1978oldW...1..1W.md")["pdf"] \
        == "../../raw/pdfs/test_star/1978oldW...1..1W.pdf"


def test_paper_notes_link_pdf_clickeable(toy_vault):
    """El stub deja en el CUERPO un link markdown al PDF (el `pdf:` del frontmatter se renderiza
    como texto plano en Obsidian, no navegable). Markdown y NO wikilink: un [[x.pdf]] sería
    wikilink roto para el lint (sólo indexa destinos .md)."""
    ads_json([rec("2020conA...1..1A"), rec("1990preB....1..1B")])
    pdf_dir = toy_vault.PDFS / "test_star"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / "2020conA...1..1A.pdf").write_bytes(b"%PDF")     # bibcode con puntos consecutivos
    mn.write_paper_notes("test_star", include_all=False, force=False)
    body_a = (toy_vault.PAPERS / "2020conA...1..1A.md").read_text(encoding="utf-8")
    assert "[📄 PDF](../../raw/pdfs/test_star/2020conA...1..1A.pdf)" in body_a
    body_b = (toy_vault.PAPERS / "1990preB....1..1B.md").read_text(encoding="utf-8")
    assert "📄 PDF" not in body_b                # sin PDF bajado → sin link


def test_paper_notes_all_incluye_no_core(toy_vault):
    ads_json([rec("2020nonC....1..1C", relevant=False)])
    mn.write_paper_notes("test_star", include_all=True, force=False)
    assert read_fm(toy_vault.PAPERS / "2020nonC....1..1C.md")["relevance"] == "low"


def test_paper_notes_no_pisa_extraccion(toy_vault):
    ads_json([rec("2020conA...1..1A")])
    mn.write_paper_notes("test_star", include_all=False, force=False)
    dest = toy_vault.PAPERS / "2020conA...1..1A.md"
    antes = dest.read_text(encoding="utf-8")
    mn.write_paper_notes("test_star", include_all=False, force=False)
    assert dest.read_text(encoding="utf-8") == antes


def test_paper_notes_retrolinkea_nota_preexistente(toy_vault):
    """Paper ya extraído para otra entidad: se mergea el seed, no se pisa la extracción."""
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    dest = toy_vault.PAPERS / "2020conA...1..1A.md"
    dest.write_text("---\nbibcode: 2020conA...1..1A\nstars: [Otra]\ntags:\n- paper\n---\n"
                    "# Nota\n\nExtracción LLM previa.\n", encoding="utf-8")
    ads_json([rec("2020conA...1..1A")])
    mn.write_paper_notes("test_star", include_all=False, force=False)
    text = dest.read_text(encoding="utf-8")
    assert "Extracción LLM previa." in text
    assert read_fm(dest)["stars"] == ["Otra", "Estrella Test"]


def test_paper_notes_topic_siembra_thesis_links(toy_vault):
    seed_topic()
    ads_json([rec("2020gpsA...1..1A")], slug="gp")
    mn.write_paper_notes("gp", include_all=False, force=False, topic=True)
    fm = read_fm(toy_vault.PAPERS / "2020gpsA...1..1A.md")
    assert fm["thesis_links"] == ["gaussian-processes"] and fm["stars"] == []


# ── write_web_paper_note / unpend ────────────────────────────────────────────

def test_web_note_local_pdf(toy_vault):
    pdf_dir = toy_vault.PDFS / "gp"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / "2006Rasmussen.pdf").write_bytes(b"%PDF")
    mn.write_web_paper_note("2006Rasmussen", slug="gp", concept="gaussian-processes",
                            title="GP book", first_author="Rasmussen", year="2000")
    fm = read_fm(toy_vault.PAPERS / "2006Rasmussen.md")
    assert fm["tags"] == ["paper", "local-pdf"]
    assert fm["accessed"] is None and fm["source_url"] is None
    assert fm["pdf"] == "../../raw/pdfs/gp/2006Rasmussen.pdf"   # verdad de disco
    body = (toy_vault.PAPERS / "2006Rasmussen.md").read_text(encoding="utf-8")
    assert "[📄 PDF](../../raw/pdfs/gp/2006Rasmussen.pdf)" in body   # link clickeable en el cuerpo


def test_web_note_pending(toy_vault):
    mn.write_web_paper_note("1999Paywall", slug="gp", concept="gaussian-processes",
                            url="https://pay.wall/x", doi="10.1/pw", pending="paywall")
    dest = toy_vault.PAPERS / "1999Paywall.md"
    fm = read_fm(dest)
    assert fm["pending_source"] == "paywall"
    assert fm["accessed"] is None                     # sin snapshot todavía
    assert "⏳ **Fuente pendiente" in dest.read_text(encoding="utf-8")


def test_web_note_idempotente(toy_vault):
    assert mn.write_web_paper_note("2006Rasmussen", slug="gp", url="https://x") is True
    dest = toy_vault.PAPERS / "2006Rasmussen.md"
    antes = dest.read_text(encoding="utf-8")
    assert mn.write_web_paper_note("2006Rasmussen", slug="gp", url="https://x") is False
    assert dest.read_text(encoding="utf-8") == antes


def test_unpend_al_llegar_fulltext(toy_vault):
    mn.write_web_paper_note("1999Paywall", slug="gp", concept="gaussian-processes",
                            url="https://pay.wall/x", pending="paywall")
    dest = toy_vault.PAPERS / "1999Paywall.md"
    # el usuario ya extrajo algo en la nota: eso debe sobrevivir al des-pendeo
    dest.write_text(dest.read_text(encoding="utf-8").replace(
        "- **Aporte al tema:**", "- **Aporte al tema:** SENTINEL_LLM"), encoding="utf-8")
    ft = toy_vault.FULLTEXT / "gp"
    ft.mkdir(parents=True, exist_ok=True)
    (ft / "1999Paywall.txt").write_text("fuente conseguida", encoding="utf-8")
    mn.write_web_paper_note("1999Paywall", slug="gp", concept="gaussian-processes", url="https://pay.wall/x")
    text = dest.read_text(encoding="utf-8")
    assert "pending_source" not in text
    assert "⏳ **Fuente pendiente" not in text
    assert "SENTINEL_LLM" in text                     # extracción LLM intacta


def test_unpend_al_llegar_pdf_linkea(toy_vault):
    mn.write_web_paper_note("1999Paywall", slug="gp", pending="paywall", doi="10.1/x")
    pdf_dir = toy_vault.PDFS / "gp"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / "1999Paywall.pdf").write_bytes(b"%PDF")
    mn.write_web_paper_note("1999Paywall", slug="gp", doi="10.1/x")
    fm = read_fm(toy_vault.PAPERS / "1999Paywall.md")
    assert "pending_source" not in fm
    assert fm["pdf"] == "../../raw/pdfs/gp/1999Paywall.pdf"


def test_unpend_sin_fuente_no_toca(toy_vault):
    mn.write_web_paper_note("1999Paywall", slug="gp", pending="paywall")
    dest = toy_vault.PAPERS / "1999Paywall.md"
    antes = dest.read_text(encoding="utf-8")
    mn.write_web_paper_note("1999Paywall", slug="gp")   # la fuente sigue faltando
    assert dest.read_text(encoding="utf-8") == antes     # el flag se queda
