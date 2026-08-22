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


def test_web_note_accessed_reusa_retrieved_del_snapshot(toy_vault):
    """Regresión #34: con un snapshot ya en disco (flujo "sin Node": guardado a mano y stubbeado
    con make_notes --web), `accessed` debe ser la fecha `retrieved` del .txt — no la de hoy."""
    d = cfg.FULLTEXT / "gp"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2020Smith.txt").write_text(
        f"{cfg.FULLTEXT_WEB_MARK} (off-ADS)\nsource_url : https://x\nretrieved  : 2024-05-01 (UTC)\n",
        encoding="utf-8")
    assert mn.write_web_paper_note("2020Smith", slug="gp", url="https://x") is True
    fm = read_fm(cfg.PAPERS / "2020Smith.md")
    assert fm["accessed"] == "2024-05-01"
    assert fm["fulltext_source"] == "web"            # de paso: nace con el contrato completo


def test_web_note_accessed_hoy_si_no_hay_snapshot(toy_vault):
    """Sin snapshot en disco, el default sigue siendo hoy UTC (comportamiento histórico)."""
    from datetime import datetime, timezone
    assert mn.write_web_paper_note("2021Doe", slug="gp", url="https://y") is True
    fm = read_fm(cfg.PAPERS / "2021Doe.md")
    assert fm["accessed"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")


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
    """Los records acá NO traen `why_excluded` → cubre además el fallback legacy (#30): un
    ads.json viejo sigue mostrando la dicotomía histórica sin tópico / doctype."""
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


def test_excluded_motivo_regla_combinacion(toy_vault):
    """Regresión #30: un excluido por require/min_topics (facetas matcheadas, doctype limpio)
    muestra su motivo REAL persistido (`why_excluded`) — antes la tabla mentía `doctype: article`."""
    r = rec("2020req....1..1R", relevant=False, cites=5)
    r["topics"] = ["actividad"]
    r["why_excluded"] = "sin faceta obligatoria (rv) — relevance.require"
    ads_json([r])
    tabla = mn.excluded_table("test_star")
    assert "sin faceta obligatoria (rv)" in tabla
    assert "doctype: article" not in tabla


# ── stamp_excluded (re-estampado quirúrgico del apéndice, #35) ───────────────

def test_stamp_excluded_refresca_sin_tocar_la_sintesis(toy_vault):
    """Regresión #35 (maintain D, re-clasificar): make_notes sin --force sobre una ficha
    existente re-estampa SÓLO el apéndice máquina con el ads.json vigente — la prosa LLM
    queda byte a byte."""
    ads_json([rec("2020vieja...1V", relevant=False, cites=3, title="Excluida vieja")])
    mn.write_star_note("test_star", force=False)
    dest = cfg.STARS / "test_star.md"
    text = dest.read_text(encoding="utf-8").replace(
        "_(síntesis por LLM:", "Síntesis LLM valiosa que NO debe tocarse. _(síntesis por LLM:")
    dest.write_text(text, encoding="utf-8")
    # cambió la regla → re-clasificación regeneró ads.json con otra excluida y otro motivo
    r = rec("2021nueva...1N", relevant=False, cites=9, title="Excluida nueva")
    r["topics"] = ["actividad"]
    r["why_excluded"] = "sin faceta obligatoria (rv) — relevance.require"
    ads_json([r])
    mn.write_star_note("test_star", force=False)          # la vía pública: sin --force
    out = dest.read_text(encoding="utf-8")
    assert "Excluida nueva" in out and "sin faceta obligatoria (rv)" in out
    assert "Excluida vieja" not in out
    assert "Síntesis LLM valiosa que NO debe tocarse." in out
    assert out.count("## Excluidos por el filtro") == 1


def test_stamp_excluded_agrega_y_quita(toy_vault):
    """El apéndice se agrega si la nota no lo tenía (no había ads.json al crearla) y se QUITA
    si ya no hay excluidos; sin cambios, no reescribe (idempotente)."""
    mn.write_star_note("test_star", force=False)          # sin ads.json → sin apéndice
    dest = cfg.STARS / "test_star.md"
    assert "## Excluidos por el filtro" not in dest.read_text(encoding="utf-8")
    ads_json([rec("2020noc....1..1N", relevant=False)])
    assert mn.stamp_excluded("test_star", dest) is True   # ahora hay excluidos → se agrega
    assert "## Excluidos por el filtro" in dest.read_text(encoding="utf-8")
    assert mn.stamp_excluded("test_star", dest) is False  # idempotente
    ads_json([rec("2020core...1..1C", relevant=True)])    # re-clasificación: todo core
    assert mn.stamp_excluded("test_star", dest) is True
    assert "## Excluidos por el filtro" not in dest.read_text(encoding="utf-8")


def test_stamp_excluded_sin_ads_json_no_toca(toy_vault):
    """build/ es scratch: sin ads.json vigente (post-clone / limpieza) el apéndice existente NO
    se quita — quitarlo destruiría el snapshot del ingest por ausencia de un archivo regenerable."""
    ads_json([rec("2020noc....1..1N", relevant=False)])
    mn.write_star_note("test_star", force=False)
    dest = cfg.STARS / "test_star.md"
    before = dest.read_text(encoding="utf-8")
    assert "## Excluidos por el filtro" in before
    (cfg.ROOT / "build" / "test_star" / "ads.json").unlink()      # build/ limpiado
    assert mn.stamp_excluded("test_star", dest) is False
    assert dest.read_text(encoding="utf-8") == before


def test_stamp_excluded_concept_via_publica(toy_vault, capsys):
    """La rama "ya existe" de write_concept_note también re-estampa (temas, D re-clasificar)."""
    seed_topic()
    mn.write_concept_note("gp", force=False)
    ads_json([rec("2020exc....1..1X", relevant=False, title="Fuera del corte")], slug="gp")
    mn.write_concept_note("gp", force=False)
    out = (cfg.CONCEPTS / "methods" / "gaussian-processes.md").read_text(encoding="utf-8")
    assert "Fuera del corte" in out
    assert "re-estampado" in capsys.readouterr().out


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


# ── #76: el CUERPO del stub ramifica por tipo de sujeto (los seeds ya ramificaban) ───────────

def test_stub_estrella_no_hardcodea_los_ejes(toy_vault):
    """El eje estrella es astro por schema (ground-truth NEA), pero los ejes de CONTENIDO salen
    del objetivo de la bóveda — no de un hardcodeo a actividad/planetas."""
    ads_json([rec("2020conA...1..1A")])
    mn.write_paper_notes("test_star", include_all=False, force=False)
    body = (toy_vault.PAPERS / "2020conA...1..1A.md").read_text(encoding="utf-8")
    assert "- **Ground-truth (planetas / parámetros):**" in body
    assert "**Ejes del objetivo (actividad · rv):**" in body   # las facetas de la lente de juguete
    assert "«toy»" in body                                     # objective.short, no un texto fijo
    assert "Aporte al tema" not in body


def test_stub_tema_no_pide_planetas_ni_actividad(toy_vault):
    """El defecto de #76: un tema ingestado por ADS recibía los bullets de planetas y actividad,
    contradiciendo que el eje tema/concepto es agnóstico de disciplina."""
    seed_topic()
    ads_json([rec("2020gpsA...1..1A")], slug="gp")
    mn.write_paper_notes("gp", include_all=False, force=False, topic=True)
    body = (toy_vault.PAPERS / "2020gpsA...1..1A.md").read_text(encoding="utf-8")
    assert "- **Aporte al tema:**" in body and "- **Régimen de validez:**" in body
    assert "planeta" not in body.lower() and "Ejes del objetivo" not in body


def test_stub_off_ads_comparte_el_bloque_del_tema(toy_vault):
    """Un solo lugar de verdad (criterio de LLM_DISCLAIMER): la rama off-ADS —que ya tenía su
    propio bullet de tema— y la rama ADS de tema escriben el MISMO bloque, así que no divergen."""
    mn.write_web_paper_note("2020Smith", slug="gp", concept="gaussian-processes", url="https://x")
    body = (toy_vault.PAPERS / "2020Smith.md").read_text(encoding="utf-8")
    assert mn.extraction_block(topic=True) in body


def test_extraction_block_sin_objetivo_degrada_a_generico(toy_vault):
    """make_notes corrido suelto, fuera de la cadena: sin objective.yaml el stub sale genérico
    (nunca inventado) y no rompe la generación."""
    toy_vault.OBJECTIVE_YAML.unlink()
    block = mn.extraction_block(topic=False)
    assert "- **Ejes del objetivo:**" in block           # sin facetas: sin paréntesis
    assert "objetivo de la bóveda / huecos" in block     # sin `short`: texto genérico


# ── #72: el paso de contraste (inventario por eje) ──────────────────────────────────────────

def test_inventario_en_ficha_y_concept(toy_vault):
    """El paso de contraste es el mismo para los dos tipos de entidad, así que el bloque es UNO
    (criterio de LLM_DISCLAIMER: lo escriben dos templates y divergirían)."""
    seed_topic()
    mn.write_star_note("test_star", force=False)
    mn.write_concept_note("gp", force=False)
    ficha = (toy_vault.STARS / "test_star.md").read_text(encoding="utf-8")
    concept = (toy_vault.CONCEPTS / "methods" / "gaussian-processes.md").read_text(encoding="utf-8")
    assert mn.INVENTARIO in ficha and mn.INVENTARIO in concept


def test_inventario_va_entre_la_sintesis_y_los_huecos(toy_vault):
    """El orden es el del razonamiento: primero la evidencia contrastada, después la síntesis que se
    apoya en ella y los huecos que deja."""
    mn.write_star_note("test_star", force=False)
    t = (toy_vault.STARS / "test_star.md").read_text(encoding="utf-8")
    assert t.index("## Resumen") < t.index("## Inventario por eje") < t.index("## Huecos")


def test_inventario_no_tiene_columna_de_valor_adoptado(toy_vault):
    """La columna que NO está es el punto del issue: adoptar un valor es decidir por el consumidor
    (regla #0, flujo unidireccional). El inventario reporta el estado de la literatura."""
    mn.write_star_note("test_star", force=False)
    t = (toy_vault.STARS / "test_star.md").read_text(encoding="utf-8")
    cabecera = next(l for l in t.split("\n") if l.startswith("| Eje |"))
    assert [c.strip() for c in cabecera.strip("|").split("|")] == [
        "Eje", "Paper", "Dice", "Método / baseline"]
    # y la ausencia está DICHA, no sólo omitida: el que llena la tabla tiene que saber por qué
    assert 'Sin columna "valor adoptado"' in t and "regla #0" in t


# ── #76 (unitario): objective_lens + la matriz de ramas de extraction_block ──────────────────

def write_objective(toy_vault, **cambios):
    """objective.yaml de juguete con los campos pisados (o borrados con None)."""
    from conftest import OBJECTIVE
    obj = {k: v for k, v in {**OBJECTIVE, **cambios}.items() if v is not None}
    write_yaml(toy_vault.OBJECTIVE_YAML, obj)


def test_objective_lens_lee_facetas_y_short(toy_vault):
    """La lente sale del objetivo, en el ORDEN declarado (es lo que se lista en el bullet)."""
    assert mn.objective_lens() == (["actividad", "rv"], "toy")


def test_objective_lens_tolera_objetivo_incompleto(toy_vault):
    """Un objective.yaml a medio escribir (sin `relevance`, o con `short` vacío) no rompe la
    generación de notas: la lente queda vacía y el stub cae al texto genérico."""
    write_objective(toy_vault, relevance=None)
    assert mn.objective_lens() == ([], "toy")
    write_objective(toy_vault, relevance={"topics": {}}, short="   ")
    assert mn.objective_lens() == ([], "")


def test_objective_lens_sin_archivo_no_propaga_el_error(toy_vault):
    """load_objective() levanta si falta el archivo; el stub NO es el lugar donde eso aborta."""
    toy_vault.OBJECTIVE_YAML.unlink()
    assert mn.objective_lens() == ([], "")


@pytest.mark.parametrize("topic,cabeza", [(True, "Aporte al tema"),
                                          (False, "Ground-truth (planetas / parámetros)")])
def test_extraction_block_forma(toy_vault, topic, cabeza):
    """Contrato de forma que asumen los dos templates de cuerpo (se interpolan como `{bloque}`
    al final del f-string): encabezado propio, bullets con la cola compartida y newline final. La
    cola es compartida a propósito: métodos y rol (#73) son del paper, no del tipo de sujeto."""
    block = mn.extraction_block(topic)
    lineas = block.rstrip("\n").split("\n")
    assert block.startswith("## Extracción (LLM)\n") and block.endswith("\n")
    assert len(lineas) == 6 and all(ln.startswith("- **") for ln in lineas[1:])
    assert cabeza in lineas[1]
    assert lineas[-3] == mn._BULLET_METHODS and lineas[-2] == mn._BULLET_ROLE
    assert lineas[-1].startswith("- **Para el objetivo:**")


def test_extraction_block_tema_sin_short_cae_al_generico(toy_vault):
    """La rama que faltaba de la matriz: tema + objetivo sin `short`."""
    write_objective(toy_vault, short=None)
    block = mn.extraction_block(topic=True)
    assert "- **Aporte al tema:**" in block
    assert "- **Para el objetivo:** _(relevancia para el objetivo de la bóveda / huecos)_" in block


def test_extraction_block_estrella_sin_facetas_pero_con_short(toy_vault):
    """Y la simétrica: sin facetas el bullet va sin paréntesis, pero el `short` sigue citándose."""
    write_objective(toy_vault, relevance={"topics": {}})
    block = mn.extraction_block(topic=False)
    assert "- **Ejes del objetivo:** _(qué dice el paper" in block
    assert "«toy»" in block


# ── contrato fulltext (fulltext: / fulltext_source:) ─────────────────────────

def seed_txt(toy_vault, slug, stem, header=""):
    d = toy_vault.FULLTEXT / slug
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{stem}.txt"
    p.write_text(header + "Texto del paper con contenido de sobra.\n", encoding="utf-8")
    return p


def test_fulltext_info_provenance(toy_vault):
    """La provenance sale de la marca en la primera línea del .txt (verdad de disco)."""
    seed_txt(toy_vault, "test_star", "2020plain..1..1P")
    seed_txt(toy_vault, "test_star", "2020ocrX...1..1O",
             header=f"{cfg.FULLTEXT_OCR_MARK}: citable CON SALVEDAD\n")
    seed_txt(toy_vault, "gp", "2020Web",
             header=f"{cfg.FULLTEXT_WEB_MARK} (off-ADS), determinista para citar/verificar\n")
    assert mn.fulltext_info("test_star", "2020plain..1..1P") \
        == ("../../raw/fulltext/test_star/2020plain..1..1P.txt", "pdftotext")
    assert mn.fulltext_info("test_star", "2020ocrX...1..1O")[1] == "ocr"
    assert mn.fulltext_info("gp", "2020Web")[1] == "web"
    assert mn.fulltext_info("test_star", "no-existe") == (None, None)
    assert mn.fulltext_info(None, "x") == (None, None)


def test_paper_notes_fulltext_verdad_de_disco(toy_vault):
    """Re-run con .txt ya extraído → el stub nace con el contrato completo; sin .txt → null
    (en el primer run de la cadena lo estampa extract_fulltext después, vía stamp_fulltext)."""
    ads_json([rec("2020conA...1..1A"), rec("1990preB....1..1B")])
    seed_txt(toy_vault, "test_star", "2020conA...1..1A")
    mn.write_paper_notes("test_star", include_all=False, force=False)
    fm_a = read_fm(toy_vault.PAPERS / "2020conA...1..1A.md")
    assert fm_a["fulltext"] == "../../raw/fulltext/test_star/2020conA...1..1A.txt"
    assert fm_a["fulltext_source"] == "pdftotext"
    fm_b = read_fm(toy_vault.PAPERS / "1990preB....1..1B.md")
    assert fm_b["fulltext"] is None and fm_b["fulltext_source"] is None


def test_stamp_fulltext_quirurgico(toy_vault):
    """stamp_fulltext actualiza `fulltext: null` → ruta sin tocar la extracción LLM; idempotente."""
    ads_json([rec("2020conA...1..1A")])
    mn.write_paper_notes("test_star", include_all=False, force=False)   # sin .txt → null
    dest = toy_vault.PAPERS / "2020conA...1..1A.md"
    dest.write_text(dest.read_text(encoding="utf-8")
                    + "\n- **Métodos:** GP con kernel QP\n", encoding="utf-8")
    seed_txt(toy_vault, "test_star", "2020conA...1..1A",
             header=f"{cfg.FULLTEXT_OCR_MARK}: citable CON SALVEDAD\n")
    assert mn.stamp_fulltext(dest, "2020conA...1..1A", "test_star") is True
    fm_a = read_fm(dest)
    assert fm_a["fulltext"] == "../../raw/fulltext/test_star/2020conA...1..1A.txt"
    assert fm_a["fulltext_source"] == "ocr"                  # la salvedad OCR viaja en la nota
    assert "GP con kernel QP" in dest.read_text(encoding="utf-8")
    assert mn.stamp_fulltext(dest, "2020conA...1..1A", "test_star") is False


def test_stamp_fulltext_migra_nota_pre_contrato(toy_vault):
    """Nota vieja SIN los campos → se insertan tras `pdf:` (migración: re-correr la cadena)."""
    mk_note(toy_vault.PAPERS, "2019oldC...1..1C",
            {"bibcode": "2019oldC...1..1C", "pdf": None, "tags": ["paper"]}, "extracción vieja\n")
    seed_txt(toy_vault, "test_star", "2019oldC...1..1C")
    dest = toy_vault.PAPERS / "2019oldC...1..1C.md"
    assert mn.stamp_fulltext(dest, "2019oldC...1..1C", "test_star") is True
    fm_c = read_fm(dest)
    assert fm_c["fulltext"].endswith("2019oldC...1..1C.txt")
    assert fm_c["fulltext_source"] == "pdftotext"
    assert "extracción vieja" in dest.read_text(encoding="utf-8")
    assert mn.stamp_fulltext(dest, "2019oldC...1..1C", "test_star") is False


# ── multi-slug: fulltext determinista aunque el paper viva bajo varios slugs (#16) ──

def _note_con_fulltext(toy_vault, stem, rel, src):
    return mk_note(toy_vault.PAPERS, stem,
                   {"bibcode": stem, "pdf": None,
                    "fulltext": rel, "fulltext_source": src, "tags": ["paper"]}, "cuerpo\n")


def test_stamp_fulltext_multi_slug_empate_no_toca(toy_vault):
    """Mismo paper bajo dos slugs con .txt de igual calidad: la nota apunta a A y correr la
    cadena de B NO la repunta (primer escritor gana → idempotente, sin ruido de diff)."""
    stem = "2009ApJ...700.1732K"
    seed_txt(toy_vault, "tau_ceti", stem)                    # pdftotext
    seed_txt(toy_vault, "hd40307", stem)                     # pdftotext (contenido igual)
    dest = _note_con_fulltext(toy_vault, stem,
                              f"../../raw/fulltext/tau_ceti/{stem}.txt", "pdftotext")
    assert mn.stamp_fulltext(dest, stem, "hd40307") is False
    fm = read_fm(dest)
    assert fm["fulltext"] == f"../../raw/fulltext/tau_ceti/{stem}.txt"
    assert fm["fulltext_source"] == "pdftotext"


def test_stamp_fulltext_multi_slug_prefiere_pdftotext_sobre_ocr(toy_vault):
    """La nota apunta a una copia OCR; llega un slug con extracción pdftotext limpia → gana la
    mejor calidad (converge a la fuente más citable, no al último que corrió)."""
    stem = "2016ApJ...820...89F"
    seed_txt(toy_vault, "crx-index", stem,
             header=f"{cfg.FULLTEXT_OCR_MARK}: citable CON SALVEDAD\n")
    seed_txt(toy_vault, "hd40307", stem)                     # pdftotext limpio
    dest = _note_con_fulltext(toy_vault, stem,
                              f"../../raw/fulltext/crx-index/{stem}.txt", "ocr")
    assert mn.stamp_fulltext(dest, stem, "hd40307") is True
    fm = read_fm(dest)
    assert fm["fulltext"] == f"../../raw/fulltext/hd40307/{stem}.txt"
    assert fm["fulltext_source"] == "pdftotext"


def test_stamp_fulltext_multi_slug_no_degrada_a_ocr(toy_vault):
    """La nota ya apunta a una extracción pdftotext limpia; llega un slug con sólo OCR → NO se
    degrada (la calidad manda por sobre el orden de ejecución)."""
    stem = "2018ApJ...864...75K"
    seed_txt(toy_vault, "tau_ceti", stem)                    # pdftotext
    seed_txt(toy_vault, "hd40307", stem,
             header=f"{cfg.FULLTEXT_OCR_MARK}: citable CON SALVEDAD\n")
    dest = _note_con_fulltext(toy_vault, stem,
                              f"../../raw/fulltext/tau_ceti/{stem}.txt", "pdftotext")
    assert mn.stamp_fulltext(dest, stem, "hd40307") is False
    fm = read_fm(dest)
    assert fm["fulltext"] == f"../../raw/fulltext/tau_ceti/{stem}.txt"
    assert fm["fulltext_source"] == "pdftotext"


def test_stamp_fulltext_repara_puntero_colgado(toy_vault):
    """Si el `fulltext:` estampado apunta a un .txt que ya NO existe en disco, la corrida en
    curso lo repara (la precedencia sólo protege punteros vivos)."""
    stem = "2020conA...1..1A"
    seed_txt(toy_vault, "hd40307", stem)                     # única copia que existe
    dest = _note_con_fulltext(toy_vault, stem,
                              f"../../raw/fulltext/borrado/{stem}.txt", "pdftotext")
    assert mn.stamp_fulltext(dest, stem, "hd40307") is True
    assert read_fm(dest)["fulltext"] == f"../../raw/fulltext/hd40307/{stem}.txt"


def test_web_note_nace_con_fulltext(toy_vault):
    """Flujo web: fetch_web escribe el snapshot ANTES de la nota → nace con provenance web."""
    seed_txt(toy_vault, "gp", "2020Smith",
             header=f"{cfg.FULLTEXT_WEB_MARK} (off-ADS), determinista para citar/verificar\n")
    mn.write_web_paper_note("2020Smith", slug="gp", url="https://x", concept="gaussian-processes")
    fm_s = read_fm(toy_vault.PAPERS / "2020Smith.md")
    assert fm_s["fulltext"] == "../../raw/fulltext/gp/2020Smith.txt"
    assert fm_s["fulltext_source"] == "web"


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


# ── stamp_pdf_link: la cabecera sigue al frontmatter `pdf` (#47) ─────────────

def _nota_vieja(toy_vault, stem="2015oldD...1..1D", pdf_rel=None, link_en_cuerpo=None):
    """Nota de paper pre-#13: frontmatter con `pdf`, cabecera SIN link (o con el que se pida)."""
    seg = f" · [📄 PDF]({link_en_cuerpo})" if link_en_cuerpo else ""
    body = (f"# Un título\n\n**Ana Pérez, Bob** (2015)\n"
            f"· [[test_star]] · ADS: `{stem}`{seg}\n\n"
            "## Abstract\nAbstract de prueba\n\n"
            "## Extracción (LLM)\n- **Métodos:** SENTINEL_LLM con `codigo`\n")
    return mk_note(toy_vault.PAPERS, stem, {"bibcode": stem, "pdf": pdf_rel, "tags": ["paper"]}, body)


def _pdf_en_disco(toy_vault, slug, stem):
    d = toy_vault.PDFS / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.pdf").write_bytes(b"%PDF")
    return f"../../raw/pdfs/{slug}/{stem}.pdf"


def test_stamp_pdf_link_agrega_en_nota_vieja(toy_vault):
    """#47 caso 1: nota pre-#13 (frontmatter `pdf` sano, cuerpo sin link) → se agrega el link
    en la cabecera sin tocar la extracción LLM; idempotente."""
    rel = _pdf_en_disco(toy_vault, "test_star", "2015oldD...1..1D")
    dest = _nota_vieja(toy_vault, pdf_rel=rel)
    assert mn.stamp_pdf_link(dest) is True
    text = dest.read_text(encoding="utf-8")
    assert f"· [[test_star]] · ADS: `2015oldD...1..1D` · [📄 PDF]({rel})" in text
    assert "SENTINEL_LLM con `codigo`" in text                # extracción intacta
    assert mn.stamp_pdf_link(dest) is False                   # idempotente


def test_stamp_pdf_link_quita_drift_inverso(toy_vault):
    """Link en el cuerpo pero `pdf: null` (o apuntando a un archivo que ya no está) → se quita."""
    dest = _nota_vieja(toy_vault, pdf_rel=None,
                       link_en_cuerpo="../../raw/pdfs/test_star/2015oldD...1..1D.pdf")
    assert mn.stamp_pdf_link(dest) is True
    assert "📄 PDF" not in dest.read_text(encoding="utf-8")
    # ídem con `pdf` seteado pero sin archivo en disco (puntero roto)
    dest2 = _nota_vieja(toy_vault, stem="2016oldE...1..1E",
                        pdf_rel="../../raw/pdfs/test_star/2016oldE...1..1E.pdf",
                        link_en_cuerpo="../../raw/pdfs/test_star/2016oldE...1..1E.pdf")
    assert mn.stamp_pdf_link(dest2) is True
    assert "📄 PDF" not in dest2.read_text(encoding="utf-8")


def test_stamp_pdf_link_corrige_ruta(toy_vault):
    """El link del cuerpo apunta a una ruta vieja y el frontmatter a la vigente → se corrige."""
    rel = _pdf_en_disco(toy_vault, "test_star", "2015oldD...1..1D")
    dest = _nota_vieja(toy_vault, pdf_rel=rel,
                       link_en_cuerpo="../../raw/pdfs/otro_slug/2015oldD...1..1D.pdf")
    assert mn.stamp_pdf_link(dest) is True
    text = dest.read_text(encoding="utf-8")
    assert f"[📄 PDF]({rel})" in text
    assert "otro_slug" not in text


def test_stamp_pdf_link_sin_cabecera_no_adivina(toy_vault):
    """Sin línea de cabecera reconocible ANTES de la primera sección: no toca nada — una línea
    `· ` con backticks dentro de la extracción LLM no debe confundirse con la cabecera."""
    rel = _pdf_en_disco(toy_vault, "test_star", "2017oldF...1..1F")
    body = ("# Un título\n\n## Extracción (LLM)\n"
            "· nota del LLM con `backticks` que parece cabecera pero no lo es\n")
    dest = mk_note(toy_vault.PAPERS, "2017oldF...1..1F",
                   {"bibcode": "2017oldF...1..1F", "pdf": rel, "tags": ["paper"]}, body)
    antes = dest.read_text(encoding="utf-8")
    assert mn.stamp_pdf_link(dest) is False
    assert dest.read_text(encoding="utf-8") == antes


def test_paper_notes_rerun_restamp_cabecera(toy_vault, capsys):
    """#47 en la cadena: re-correr make_notes sobre una nota existente re-estampa la cabecera
    (el fix viaja solo con el re-run idempotente, sin --force)."""
    rel = _pdf_en_disco(toy_vault, "test_star", "2020conA...1..1A")
    _nota_vieja(toy_vault, stem="2020conA...1..1A", pdf_rel=rel)
    ads_json([rec("2020conA...1..1A")])
    mn.write_paper_notes("test_star", include_all=False, force=False)
    dest = toy_vault.PAPERS / "2020conA...1..1A.md"
    assert f"[📄 PDF]({rel})" in dest.read_text(encoding="utf-8")
    assert "re-estampado" in capsys.readouterr().out


def test_unpend_al_llegar_pdf_restamp_cabecera(toy_vault):
    """#47 caso 2 (off-ADS): la fuente pendiente llega como PDF → unpend linkea `pdf:` y la
    cabecera lo sigue en la misma pasada."""
    mn.write_web_paper_note("1999Paywall", slug="gp", pending="paywall", doi="10.1/x")
    pdf_dir = toy_vault.PDFS / "gp"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / "1999Paywall.pdf").write_bytes(b"%PDF")
    mn.write_web_paper_note("1999Paywall", slug="gp", doi="10.1/x")
    text = (toy_vault.PAPERS / "1999Paywall.md").read_text(encoding="utf-8")
    assert "[📄 PDF](../../raw/pdfs/gp/1999Paywall.pdf)" in text


def test_restamp_pdf_links_barrido(toy_vault, capsys):
    """Backfill --restamp-pdf-links: barre todas las notas — agrega donde falta, quita el
    drift inverso, deja en paz las que ya están bien."""
    rel = _pdf_en_disco(toy_vault, "test_star", "2015oldD...1..1D")
    _nota_vieja(toy_vault, stem="2015oldD...1..1D", pdf_rel=rel)                 # falta el link
    _nota_vieja(toy_vault, stem="2016oldE...1..1E", pdf_rel=None,
                link_en_cuerpo="../../raw/pdfs/test_star/2016oldE...1..1E.pdf")  # drift inverso
    rel_ok = _pdf_en_disco(toy_vault, "test_star", "2018okG...1..1G")
    sana = _nota_vieja(toy_vault, stem="2018okG...1..1G", pdf_rel=rel_ok, link_en_cuerpo=rel_ok)
    antes_sana = sana.read_text(encoding="utf-8")
    assert mn.restamp_pdf_links() == 0
    assert "2 de 3 re-estampados" in capsys.readouterr().out
    assert f"[📄 PDF]({rel})" in (toy_vault.PAPERS / "2015oldD...1..1D.md").read_text(encoding="utf-8")
    assert "📄 PDF" not in (toy_vault.PAPERS / "2016oldE...1..1E.md").read_text(encoding="utf-8")
    assert sana.read_text(encoding="utf-8") == antes_sana


def test_find_header_line_es_contrato_compartido(toy_vault):
    """#48: el lint detecta las notas que stamp_pdf_link saltea usando ESTE helper — si cada uno
    definiera "cabecera" por su lado, el detector dejaría de cubrir al fixer. Acá se fija el
    contrato: cabecera reconocida ⇔ stamp_pdf_link actúa."""
    rel = _pdf_en_disco(toy_vault, "test_star", "2015oldD...1..1D")
    ok = _nota_vieja(toy_vault, pdf_rel=rel)                       # cabecera en contrato
    fuera = mk_note(toy_vault.PAPERS, "2012manT...1..1T",
                    {"bibcode": "2012manT...1..1T", "pdf": rel, "tags": ["paper"]},
                    "# T\n\nAna Pérez (2012), cabecera escrita a mano\n")
    assert mn.find_header_line(ok.read_text(encoding="utf-8")) is not None
    assert mn.stamp_pdf_link(ok) is True                           # reconocida → actúa
    assert mn.find_header_line(fuera.read_text(encoding="utf-8")) is None
    assert mn.stamp_pdf_link(fuera) is False                       # fuera del contrato → saltea


# ── puntero al registro de búsqueda en la cabecera (#64) ─────────────────────

def test_search_line_estampa_puntero_sin_tocar_la_prosa(toy_vault):
    """El registro completo vive en config/registro/<slug>.yaml; la ficha lleva UNA línea con
    fecha, universo→core, pendientes y la ruta. Cirugía: la síntesis LLM queda intacta."""
    mn.write_star_note("test_star", force=False)
    dest = cfg.STARS / "test_star.md"
    dest.write_text(dest.read_text(encoding="utf-8").replace(
        "## Resumen", "## Resumen\nSíntesis LLM que NO se toca."), encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-08-21", "query": "title:(x)", "rows": 2000,
                                    "n_found": 1837, "n_core": 198, "n_candidates": 42,
                                    "truncated": False})
    assert mn.stamp_search_line("test_star", dest) is True
    out = dest.read_text(encoding="utf-8")
    assert ("> _Búsqueda 2026-08-21: 1837 → 198 core · 42 sin juzgar · registro en "
            "`config/registro/test_star.yaml`._") in out
    assert out.index("_Búsqueda") < out.index("_Generado con Almagesto")   # dentro del blockquote
    assert "Síntesis LLM que NO se toca." in out
    assert mn.stamp_search_line("test_star", dest) is False                # idempotente


def test_search_line_se_actualiza_y_no_duplica(toy_vault):
    """Un refresh re-estampa la línea vieja en vez de acumular punteros."""
    mn.write_star_note("test_star", force=False)
    dest = cfg.STARS / "test_star.md"
    cfg.save_busqueda("test_star", {"fecha": "2026-08-01", "n_found": 100, "n_core": 10})
    mn.stamp_search_line("test_star", dest)
    cfg.save_busqueda("test_star", {"fecha": "2026-08-21", "n_found": 120, "n_core": 14,
                                    "truncated": True})
    assert mn.stamp_search_line("test_star", dest) is True
    out = dest.read_text(encoding="utf-8")
    assert out.count("> _Búsqueda") == 1
    assert "2026-08-21: 120 → 14 core" in out and "⚠ truncada" in out and "2026-08-01" not in out


def test_search_line_sin_registro_o_sin_ancla_no_toca_nada(toy_vault):
    """Sin registro no hay nada que estampar; y si la cabecera no tiene la línea `_Generado con
    Almagesto…_` está fuera del contrato → no se inventa (mismo criterio que stamp_pdf_link, #48)."""
    mn.write_star_note("test_star", force=False)
    dest = cfg.STARS / "test_star.md"
    assert mn.stamp_search_line("test_star", dest) is False
    fuera = cfg.STARS / "fuera_de_contrato.md"
    fuera.write_text("---\nname: x\n---\n# x\n\n> cabecera propia\n", encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-08-21", "n_found": 5, "n_core": 1})
    assert mn.stamp_search_line("test_star", fuera) is False
    assert "Búsqueda" not in fuera.read_text(encoding="utf-8")


# ── pdf_source: de qué DOCUMENTO salió el texto (#57) ────────────────────────

def _txt(slug, stem, body):
    d = cfg.FULLTEXT / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.txt").write_text(body, encoding="utf-8")


def test_pdf_source_detecta_el_eprint_por_la_marca_de_arxiv(toy_vault):
    """Verdad de disco: la marca que arXiv estampa en cada página delata que el .txt salió del
    EPRINT (posible v1 pre-referato), sin depender de que el fetcher haya dejado registro — así
    funciona retroactivamente sobre un corpus ya bajado."""
    _txt("test_star", "2020arx....1..1A",
         "arXiv:2201.01234v3 [astro-ph.EP] 5 Jan 2022\n\nA Study of Something\n")
    assert mn.pdf_source_info("test_star", "2020arx....1..1A") == ("eprint", "v3")


def test_pdf_source_sin_marca_usa_lo_que_registro_el_fetcher(toy_vault):
    """Sin marca de arXiv vale la rama que entregó el PDF en la corrida (ads vs publisher es
    justo lo que la marca NO distingue)."""
    _txt("test_star", "2020pub....1..1P", "A&A 641, A1 (2020)\n\nPublished version\n")
    cfg.record_pdf_source("test_star", "2020pub....1..1P", "publisher")
    assert mn.pdf_source_info("test_star", "2020pub....1..1P") == ("publisher", None)


def test_pdf_source_la_marca_gana_sobre_el_registro(toy_vault):
    """Un ADS_PDF que sirve el eprint ES el eprint, diga lo que diga la rama: manda el disco."""
    _txt("test_star", "2020mix....1..1M", "arXiv:2201.09999v1 [astro-ph.SR] 1 Jan 2022\n\nx\n")
    cfg.record_pdf_source("test_star", "2020mix....1..1M", "ads")
    assert mn.pdf_source_info("test_star", "2020mix....1..1M") == ("eprint", "v1")


def test_pdf_source_desconocido_no_afirma_publicado(toy_vault):
    """Sin marca y sin registro: None. Asumir 'publisher' sería afirmar de más justo donde el
    caveat importa (verify podría 'corregir' la nota hacia un preprint sin saberlo)."""
    _txt("test_star", "2020unk....1..1U", "Sin marcas de nada\n")
    assert mn.pdf_source_info("test_star", "2020unk....1..1U") == (None, None)
    assert mn.pdf_source_info("test_star", "2020sinTxt.1..1S") == (None, None)


def test_pdf_source_snapshot_web(toy_vault):
    _txt("test_star", "2020Autor", f"{cfg.FULLTEXT_WEB_MARK}\nurl: https://x\n\ncontenido\n")
    assert mn.pdf_source_info("test_star", "2020Autor") == ("web", None)


def test_stamp_fulltext_estampa_pdf_source_retroactivamente(toy_vault):
    """La vía retroactiva: en una bóveda ya ingestada alcanza con re-correr extract_fulltext
    (que llama a stamp_fulltext) — no hay que re-bajar ningún PDF."""
    from conftest import mk_note, read_fm
    mk_note(cfg.PAPERS, "2020arx....1..1A", {"bibcode": "2020arx....1..1A", "tags": ["paper"],
                                             "pdf": None}, "# Paper\n\nExtracción LLM.\n")
    _txt("test_star", "2020arx....1..1A", "arXiv:2201.01234v2 [astro-ph.EP] 5 Jan 2022\n\nx\n")
    dest = cfg.PAPERS / "2020arx....1..1A.md"
    assert mn.stamp_fulltext(dest, "2020arx....1..1A", "test_star") is True
    fm = read_fm(dest)
    assert fm["pdf_source"] == "eprint" and fm["eprint_version"] == "v2"
    assert fm["fulltext_source"] == "pdftotext"          # el método de extracción, aparte
    assert "Extracción LLM." in dest.read_text(encoding="utf-8")
    assert mn.stamp_fulltext(dest, "2020arx....1..1A", "test_star") is False   # idempotente


# ── backfill de la cabecera (#69) ────────────────────────────────────────────

VIEJA = """---
name: Forma y variabilidad de los ciclos
tags:
- activity
generator: Almagesto v1.4.0
---
# cycle-shape-and-variability

> Concept durable. Marco para leer las "señales secundarias" de un ciclo de actividad.
> Trazabilidad por `[[bibcode]]`.

## Síntesis

Un ciclo tipo-solar no es una sinusoide fija [[2020A&A...638A..69W]].
"""


def test_stamp_header_backfillea_la_nota_que_nacio_sin_cabecera(toy_vault):
    """#69: la nota vieja tiene blockquote propio (prosa del LLM) pero no la cabecera del template.
    El estampador ancla en el H1, no en la línea del generador, que es justo la que falta."""
    dest = cfg.CONCEPTS / "activity" / "cycle-shape-and-variability.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(VIEJA, encoding="utf-8")
    assert mn.stamp_header(dest) is True
    out = dest.read_text(encoding="utf-8")
    assert "⚠ **Capa LLM — revisar antes de citar.**" in out
    assert "La síntesis la compiló un LLM" in out                  # variante de concepto, no la de star
    # la versión sale del frontmatter de la nota, NO de la del framework corriendo
    assert "> _Generado con Almagesto v1.4.0._" in out
    assert f"v{cfg.ALMAGESTO_VERSION}" not in out
    # la prosa del LLM sobrevive entera y queda DEBAJO del H1
    assert 'Marco para leer las "señales secundarias"' in out
    assert "Un ciclo tipo-solar no es una sinusoide fija [[2020A&A...638A..69W]]." in out
    assert out.index("Capa LLM") < out.index("Marco para leer")
    assert mn.stamp_header(dest) is False                          # idempotente


def test_stamp_header_usa_la_variante_de_estrella(toy_vault):
    dest = cfg.STARS / "hd40307.md"
    dest.write_text("---\nname: HD 40307\ntags:\n- star\ngenerator: Almagesto v1.2.0\n---\n"
                    "# hd40307\n\n## Resumen\n\nProsa.\n", encoding="utf-8")
    assert mn.stamp_header(dest) is True
    out = dest.read_text(encoding="utf-8")
    assert "El ground-truth del frontmatter (NEA/SIMBAD) es auditable" in out
    assert "> _Generado con Almagesto v1.2.0._" in out


def test_stamp_header_sin_generator_no_inventa_version(toy_vault):
    """Una nota tan vieja que ni `generator` tiene: la línea va SIN versión, no con una supuesta."""
    dest = cfg.STARS / "vieja.md"
    dest.write_text("---\nname: Vieja\ntags:\n- star\n---\n# vieja\n\nProsa.\n", encoding="utf-8")
    assert mn.stamp_header(dest) is True
    out = dest.read_text(encoding="utf-8")
    assert "no registra con qué versión se creó" in out
    assert "Generado con Almagesto v" not in out


def test_stamp_header_no_toca_lo_que_ya_tiene_cabecera_ni_las_notas_de_paper(toy_vault):
    mn.write_star_note("test_star", force=False)                   # nace con cabecera
    assert mn.stamp_header(cfg.STARS / "test_star.md") is False
    from conftest import mk_note
    mk_note(cfg.PAPERS, "2020a....1A", {"tags": ["paper"], "bibcode": "2020a....1A"}, "# Paper\n")
    assert mn.stamp_header(cfg.PAPERS / "2020a....1A.md") is False  # los papers tienen su contrato (#48)


def test_stamp_header_destraba_el_puntero_de_busqueda(toy_vault):
    """El punto del backfill: sin cabecera, stamp_search_line no-opea EN SILENCIO (medido: 22 de 25
    notas de una bóveda real). Después del backfill, la misma llamada sí estampa."""
    dest = cfg.STARS / "test_star.md"
    dest.write_text("---\nname: Test Star\ntags:\n- star\ngenerator: Almagesto v1.5.0\n---\n"
                    "# test_star\n\n## Resumen\n\nProsa.\n", encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-08-21", "n_found": 100, "n_core": 10})
    assert mn.stamp_search_line("test_star", dest) is False        # antes: silencio
    assert mn.stamp_header(dest) is True
    assert mn.stamp_search_line("test_star", dest) is True         # después: aterriza
    assert "> _Búsqueda 2026-08-21" in dest.read_text(encoding="utf-8")


def test_restamp_headers_barre_fichas_y_conceptos(toy_vault, capsys):
    (cfg.CONCEPTS / "activity").mkdir(parents=True, exist_ok=True)
    (cfg.CONCEPTS / "activity" / "c.md").write_text(VIEJA, encoding="utf-8")
    (cfg.STARS / "s.md").write_text("---\nname: S\ntags:\n- star\n---\n# s\n\nProsa.\n",
                                    encoding="utf-8")
    mn.write_star_note("test_star", force=False)                   # ésta ya tiene cabecera
    assert mn.restamp_headers() == 0
    assert "2 de 3 estampadas" in capsys.readouterr().out
