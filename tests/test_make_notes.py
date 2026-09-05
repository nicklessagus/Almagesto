"""make_notes: stubs (star/concept/paper/web), retro-linkeo add-only, unpend, excluded_table.

El invariante más importante acá es el del header del script: idempotente, NUNCA pisa la
extracción LLM salvo --force; la única excepción es el merge add-only de seeds.
"""
import json
import sys

import pytest
import yaml

import lib_config as cfg
import lint
import make_notes as mn
from conftest import mk_note, read_fm, write_yaml

GT = {"star": "Estrella Test", "slug": "test_star",
      "host": {"spectral_type": "G8V", "teff_K": 5344, "dist_pc": 3.65, "st_rotp_days": 34.0},
      "planets": [
          {"letter": "b", "P_days": 20.0, "K_ms": 1.0, "e": 0.1, "mass_earth": 2.0, "status": "confirmed"},
          {"letter": "c", "P_days": 49.3, "K_ms": 1.2, "e": 0.0, "mass_earth": 3.1, "status": "confirmed"},
      ]}


def rec(bib, relevant=True, arxiv=None, cites=0, title="Un título", facets=("actividad",),
        doctype="article"):
    return {"bibcode": bib, "title": title, "authors": ["Ana Pérez", "Bob"], "year": "2020",
            "abstract": "Abstract de prueba", "arxiv_id": arxiv, "doi": "10.1/x", "bibstem": "ApJ",
            "facets": list(facets) if relevant else [], "relevant": relevant,
            "citation_count": cites, "doctype": doctype}


def run_main(monkeypatch, argv):
    """`make_notes.py <argv>` de punta a punta. Los backfills son CLI-only (nadie los llama desde
    otro script), así que sin esto su cableado —flag, dest, despacho— no lo cubre ningún test."""
    monkeypatch.setattr(sys, "argv", ["make_notes.py", *argv])
    return mn.main()


def ads_json(records, slug="test_star"):
    d = cfg.ROOT / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"records": records}), encoding="utf-8")


def seed_topic(slug="gp", area="methods", concept="gaussian-processes", **extra):
    write_yaml(cfg.THEMES_YAML, {slug: {"title": "Gaussian processes", "area": area, "concept": concept,
                                        "aliases": ["análisis de componentes"], **extra}})


# ── helpers básicos ──────────────────────────────────────────────────────────

def test_fm_roundtrip():
    """AUD-47: parsea con `cfg.split_fm`, **el mismo parser que el tooling**, no con un splitter
    ad-hoc. Con `out.split("---")[1]` el test no podía cazar la regresión para la que existe: si
    `fm()` emite la valla de cierre fusionada (`- 2---`), el splitter textual lo lee igual y
    `split_fm` devuelve `{}`. Es el patrón doble-vs-real que `conftest.read_fm` documenta como ya
    cometido y corregido (red #3), y éste es el ÚNICO test de `fm()`."""
    out = mn.fm({"a": 1, "b": [1, 2]})
    assert out.startswith("---\n") and out.endswith("---\n")
    assert cfg.split_fm(out + "\ncuerpo\n") == {"a": 1, "b": [1, 2]}


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


def test_merge_valor_con_puntuacion_yaml_es_idempotente(toy_vault):
    """AUD-145 — un valor con `: ` se re-agregaba en CADA corrida, sin techo.

    La cirugía escribe texto; sin quotear, `- Kepler: notas` se relee como un **mapa**, así que
    `v not in current` sigue siendo verdadero para siempre y la lista crece sin límite. La
    idempotencia es invariante del framework («refrescar es seguro»), no un detalle.  @inv INV-139"""
    p = toy_vault.PAPERS / "n.md"
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nbibcode: x\nthesis_links:\n- a\n---\nbody\n", encoding="utf-8")
    raro = "shift: vs shape"
    assert mn.merge_frontmatter_list(p, "thesis_links", [raro]) is True
    assert read_fm(p)["thesis_links"] == ["a", raro]
    # segunda corrida: NO vuelve a agregarlo (es lo que fallaba)
    assert mn.merge_frontmatter_list(p, "thesis_links", [raro]) is False
    assert read_fm(p)["thesis_links"] == ["a", raro]
    # ídem en flow style, donde además la coma partía el valor
    q = toy_vault.PAPERS / "m.md"
    q.write_text("---\nstars: [Otra]\n---\nbody\n", encoding="utf-8")
    coma = "GJ 581, b"
    assert mn.merge_frontmatter_list(q, "stars", [coma]) is True
    assert read_fm(q)["stars"] == ["Otra", coma]
    assert mn.merge_frontmatter_list(q, "stars", [coma]) is False


def test_merge_una_negativa_se_dice(toy_vault, capsys):
    """AUD-146 / INV-139 — seis de los siete `False` son «no pude», y el llamador los contaba como
    «ya estaba linkeado» (`skipped`): la entidad nueva nunca entraba al roll-up y nada lo decía.

    El único mudo tiene que seguir siendo el legítimo (`not missing`), que es el caso normal e
    idempotente: si también avisara, el aviso sería ruido en cada corrida y se dejaría de mirar."""
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    casos = {
        "sin_fm.md": "sin frontmatter",
        "sin_cierre.md": "---\nstars: []\n",
        "roto.md": "---\nstars: [\n---\nbody\n",
        "escalar.md": "---\nstars: una-cadena\n---\nbody\n",
        "sin_campo.md": "---\nbibcode: x\n---\nbody\n",
    }
    for nombre, texto in casos.items():
        (toy_vault.PAPERS / nombre).write_text(texto, encoding="utf-8")
        capsys.readouterr()
        assert mn.merge_frontmatter_list(toy_vault.PAPERS / nombre, "stars", ["A"]) is False
        err = capsys.readouterr().err
        assert "no pude linkear" in err and nombre in err, nombre

    ya = mk_note(toy_vault.PAPERS, "ya", {"stars": ["A"]}, "body\n")
    capsys.readouterr()
    assert mn.merge_frontmatter_list(ya, "stars", ["A"]) is False
    assert capsys.readouterr().err == ""              # el caso normal NO habla


def test_merge_preserva_el_resto_byte_a_byte(toy_vault):
    # @inv INV-16
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
    ads.json viejo sigue mostrando la dicotomía histórica sin tópico / doctype.  @inv INV-71"""
    noncore = [rec(f"2020n....{i:02d}.nA", relevant=False, cites=i) for i in range(12)]
    noncore[11]["title"] = "Título con | pipe y [brackets] adentro que rompe tablas markdown"
    ruido = rec("2020ruid....1R", relevant=False, cites=100, doctype="catalog")
    ruido["facets"] = ["actividad"]                   # no-core por doctype, no por tópico
    ads_json(noncore + [ruido])
    tabla = mn.excluded_table("test_star")
    assert tabla.count("| [") == mn.EXCLUDED_TOP_N    # top-N filas
    assert "+ 3 más excluidos" in tabla
    assert r"\|" in tabla and r"\[brackets\]" in tabla
    # sin `why_excluded` (ads.json pre-#30) NO se reconstruye el motivo: la dicotomía vieja
    # etiquetaba `doctype: article` a los excluidos por la regla de combinación, o sea escribía un
    # motivo FALSO en la bóveda. Mejor decir que no se registró.
    assert "motivo no registrado" in tabla
    assert "doctype: catalog" not in tabla and "sin tópico" not in tabla


def test_excluded_motivo_regla_combinacion(toy_vault):
    """Regresión #30: un excluido por require/min_facets (facetas matcheadas, doctype limpio)
    muestra su motivo REAL persistido (`why_excluded`) — antes la tabla mentía `doctype: article`."""
    r = rec("2020req....1..1R", relevant=False, cites=5)
    r["facets"] = ["actividad"]
    r["why_excluded"] = "sin faceta obligatoria (rv) — relevance.require"
    ads_json([r])
    tabla = mn.excluded_table("test_star")
    assert "sin faceta obligatoria (rv)" in tabla
    assert "doctype: article" not in tabla


def test_ads_json_corrupto_no_borra_el_apendice_de_excluidos(toy_vault):
    """AUD-202 / INV-139 — un `ads.json` cortado a mitad BORRABA contenido ya publicado.

    `excluded_table` promete no lanzar y degrada a `""`; en `stamp_excluded` ese `""` significa
    «la corrida vigente no excluye a nadie» → se quitaba el apéndice. Las dos piezas están bien
    por separado: lo que faltaba era distinguir «no hay excluidos» de «no pude leer» ANTES de
    decidir un borrado."""
    nota = toy_vault.STARS / "test_star.md"
    toy_vault.STARS.mkdir(parents=True, exist_ok=True)
    apendice = ("---\ntags: [star]\n---\n# Test Star\n\nprosa\n\n"
                "## Excluidos por el filtro\n\n| Bibcode | Motivo |\n|---|---|\n| 2019X | ruido |\n")
    nota.write_text(apendice, encoding="utf-8")
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text('{"records": [{"bibcode": "2019X", "rele', encoding="utf-8")

    assert mn.stamp_excluded("test_star", nota) is False
    assert nota.read_text(encoding="utf-8") == apendice        # no se tocó nada


def test_excluded_table_no_voltea_la_generacion_de_notas(toy_vault):
    """`excluded_table` se llama desde `write_star_note`/`write_concept_note`: si revienta, la
    cadena muere DESPUÉS de gastar la red. Un `ads.json` truncado por un Ctrl-C en `query_ads` es
    el caso natural."""
    d = cfg.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text('{"records": [{"bibcode": 42, "relevant": false,'
                                ' "citation_count": "muchas"}]}', encoding="utf-8")
    assert isinstance(mn.excluded_table("test_star"), str)


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
    r["facets"] = ["actividad"]
    r["why_excluded"] = "sin faceta obligatoria (rv) — relevance.require"
    ads_json([r])
    mn.write_star_note("test_star", force=False)          # la vía pública: sin --force
    out = dest.read_text(encoding="utf-8")
    assert "Excluida nueva" in out and "sin faceta obligatoria (rv)" in out
    assert "Excluida vieja" not in out
    assert "Síntesis LLM valiosa que NO debe tocarse." in out
    assert out.count("## Excluidos por el filtro") == 1


def test_stamp_excluded_agrega_y_quita(toy_vault):
    # @inv INV-15
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
    # @inv INV-71
    # @inv INV-01
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps(GT), encoding="utf-8")
    mn.write_star_note("test_star", force=False)
    fm = read_fm(toy_vault.STARS / "test_star.md")
    assert fm["name"] == "Estrella Test" and fm["slug"] == "test_star"
    assert fm["P_rot_days"] == 34.0 and fm["teff_K"] == 5344
    assert [p["letter"] for p in fm["planets"]] == ["b", "c"]
    assert fm["planets"][0]["K_ms"] == 1.0 and fm["planets"][0]["mass_earth"] == 2.0
    assert fm["tags"] == ["star"]
    assert fm["generator"].startswith("Almagesto v")


def test_star_note_siembra_los_campos_que_llena_el_llm(toy_vault):
    """Los seeds vacíos NO son decoración: son el contrato de schema que la extracción LLM viene a
    llenar. Si `disputes` desaparece del stub la ficha nace sin dónde colgar un desacuerdo (#71) y
    nada falla — el modo de falla de #69: no rompe, sale mal. `disputes` va **justo después de
    `planets`**, donde vive la información que discute."""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps(GT), encoding="utf-8")
    mn.write_star_note("test_star", force=False)
    fm = read_fm(toy_vault.STARS / "test_star.md")
    assert fm["disputes"] == [] and fm["activity_indicators_expected"] == []
    assert fm["methods_applied"] == {"literature": [], "ours": []}
    claves = list(fm)
    assert claves.index("disputes") == claves.index("planets") + 1


def test_star_note_sin_ground_truth(toy_vault):
    # @inv INV-07
    mn.write_star_note("test_star", force=False)
    assert read_fm(toy_vault.STARS / "test_star.md")["planets"] == []


def test_star_note_crea_la_carpeta_si_no_existe(toy_vault):
    """git no versiona directorios vacíos: un clon con el scratch limpiado (o un árbol armado a
    mano) puede no tener `vault/wiki/stars/`. Los otros dos writers hacen `mkdir`; éste no, y la
    cadena moría con un traceback de FileNotFound en el primer ingest."""
    import shutil
    shutil.rmtree(toy_vault.STARS)
    mn.write_star_note("test_star", force=False)
    assert (toy_vault.STARS / "test_star.md").exists()


def test_star_note_idempotente(toy_vault):
    mn.write_star_note("test_star", force=False)
    dest = toy_vault.STARS / "test_star.md"
    dest.write_text("EXTRACCIÓN LLM", encoding="utf-8")
    mn.write_star_note("test_star", force=False)
    assert dest.read_text(encoding="utf-8") == "EXTRACCIÓN LLM"
    mn.write_star_note("test_star", force=True)
    assert dest.read_text(encoding="utf-8") != "EXTRACCIÓN LLM"


def test_cli_force_pisa_nota_existente(toy_vault, monkeypatch):
    """`--force` es la única forma pública de pisar una nota ya extraída (`write_star_note(force=…)`
    ya lo cubre directo; falta el cableado del CLI). Con el `dest` roto `args.force` queda en
    `False` pase lo que pase en la línea de comandos, y `make_notes.py <slug> --force` no-opea en
    silencio sobre una ficha existente — el modo de falla real de un dest typeado."""
    mn.write_star_note("test_star", force=False)
    dest = toy_vault.STARS / "test_star.md"
    dest.write_text("EXTRACCIÓN LLM QUE --force DEBE REEMPLAZAR", encoding="utf-8")
    assert run_main(monkeypatch, ["test_star", "--force"]) == 0
    assert dest.read_text(encoding="utf-8") != "EXTRACCIÓN LLM QUE --force DEBE REEMPLAZAR"


# ── write_concept_note ───────────────────────────────────────────────────────

def test_concept_note_methods(toy_vault):
    seed_topic()
    mn.write_concept_note("gp", force=False)
    dest = toy_vault.CONCEPTS / "methods" / "gaussian-processes.md"
    fm = read_fm(dest)
    assert fm["name"] == "Gaussian processes" and "status" not in fm
    assert fm["aliases"] == ["análisis de componentes"]
    assert fm["tags"] == ["methods", "thesis"]
    # ficha-método: el roll-up junta por `methods` Y por `thesis_links` (retro-link). D-11: ya no
    # es un bloque ```dataview``` sino una tabla ESTAMPADA — un agente que abre el .md ve los
    # papers, no el código de una query que nunca va a correr.
    texto = dest.read_text(encoding="utf-8")
    assert "## Papers que tocan este tema (auto) (0 · 0 sintetizados en este concepto)" in texto
    assert "```dataview" not in texto.split("## Papers que tocan", 1)[1]


def test_concept_note_hypotheses_lleva_status(toy_vault):
    """⚠ **Actualizado por #175.** Esto fijaba `status == "active"`, que **no está** en el
    vocabulario cerrado de D-37: el test acreditaba el valor que hacía nacer bloqueante a toda
    hipótesis nueva. Hoy fija que el `status` sale del vocabulario y que es el inicial."""
    seed_topic(area="hypotheses")
    mn.write_concept_note("gp", force=False)
    dest = toy_vault.CONCEPTS / "hypotheses" / "gaussian-processes.md"
    assert read_fm(dest)["status"] == cfg.HYP_STATUS_INICIAL == "abierta"
    # AUD-48: antes asserteaba la ausencia de `contains(methods,`, una cadena que ya no se emite a
    # ninguna nota (D-10/D-11 reemplazó el predicado Dataview por tabla estampada), o sea que era
    # verde por construcción. Lo que sí distingue a una hipótesis es que NO lleva el roll-up de
    # ficha-método.
    assert "```dataview" not in dest.read_text(encoding="utf-8")


def test_concept_note_area_no_declarada_avisa_pero_crea(toy_vault, capsys):
    seed_topic(area="zzz")
    mn.write_concept_note("gp", force=False)
    assert "no está en concept_areas" in capsys.readouterr().out
    assert (toy_vault.CONCEPTS / "zzz" / "gaussian-processes.md").exists()


def test_concept_note_sin_area_o_concept_error_amigable(toy_vault):
    """Guard de config: entrada de themes.yaml incompleta → mensaje amigable, no KeyError."""
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "Gaussian processes", "concept": "gaussian-processes"}})
    with pytest.raises(SystemExit, match="'gp' no tiene `area`"):
        mn.write_concept_note("gp", force=False)
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "Gaussian processes", "area": "methods"}})
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
    # `role` (#73) lo llena la extracción, pero el campo tiene que EXISTIR en el stub: sin él, el
    # bullet del cuerpo pide un rol que no tiene dónde ir y el contraste cross-paper queda mudo.
    assert fm_a["role"] == []
    # D-21 retiró `bearing` del paper: la postura vive en la tabla de evidencia de la
    # hipótesis, porque depende de la tesis y un paper puede tocar varias.
    assert "bearing" not in fm_a
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


def test_cli_all_incluye_no_relevantes(toy_vault, monkeypatch):
    """`--all` es lo único que hace público `include_all=True` (la función ya está cubierta
    directo arriba); falta el cableado del CLI. Con el `dest` roto `args.all` es siempre `False`
    pase lo que pase en la línea de comandos: la nota del paper no-core nunca se escribe, sin
    ningún aviso — un `make_notes.py <slug> --all` que se comporta como si no lo hubieran pasado."""
    ads_json([rec("2020nonC....1..1C", relevant=False)])
    assert run_main(monkeypatch, ["test_star", "--all"]) == 0
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
    mn.write_paper_notes("gp", include_all=False, force=False, theme=True)
    fm = read_fm(toy_vault.PAPERS / "2020gpsA...1..1A.md")
    assert fm["thesis_links"] == ["gaussian-processes"] and fm["stars"] == []


def test_cli_topic_genera_concept_en_vez_de_ficha(toy_vault, monkeypatch):
    """`--theme` decide, en `main()`, entre `write_concept_note` (tema) y `write_star_note`
    (estrella) — y además el modo `theme=True` de `write_paper_notes`. Todo eso ya está cubierto
    llamando a las funciones directo; sin este test nadie ejercita el `if args.theme:` del propio
    despacho. Con el `dest` roto, `gp` (un slug de `themes.yaml`, no de `stars.yaml`) generaría una
    ficha de ESTRELLA en `vault/wiki/stars/` en vez del concept que pidió `--theme`."""
    seed_topic()
    assert run_main(monkeypatch, ["gp", "--theme"]) == 0
    assert (toy_vault.CONCEPTS / "methods" / "gaussian-processes.md").exists()
    assert not (toy_vault.STARS / "gp.md").exists()


# ── #76: el CUERPO del stub ramifica por tipo de sujeto (los seeds ya ramificaban) ───────────

def test_el_stub_de_estrella_publica_una_LINEA_DE_ESTADO_y_no_el_prompt(toy_vault):
    """#398 — el stub estampaba las INSTRUCCIONES AL EXTRACTOR en el cuerpo de toda nota de paper,
    como marcador de posición para que el chequeo `vistas[]` ↔ cuerpo cerrara. No las lee nadie: el
    agente que lee el paper recibe sus reglas de `extraction_prompt` y el cosechador pisa la sección
    con el JSON. Mientras tanto —el estado normal de un reclamo sembrado por retro-tag— la nota le
    mostraba al lector un pedido como si fuera contenido, bajo un encabezado que ella misma presenta
    como síntesis de un LLM (#247). Medido: 47 notas.

    La ramificación por tipo de sujeto de #76 no se perdió: vive donde se usa, en el prompt (#254)."""
    ads_json([rec("2020conA...1..1A")])
    mn.write_paper_notes("test_star", include_all=False, force=False)
    body = (toy_vault.PAPERS / "2020conA...1..1A.md").read_text(encoding="utf-8")
    assert "_Reclamado por `Estrella Test`; sin leer desde este sujeto._" in body, body
    for instruccion in ("Ground-truth (planetas / parámetros)", "Ejes del objetivo",
                        "Cómo anotar cada valor", "Rol del paper", "Aporte al tema"):
        assert instruccion not in body, f"el prompt sigue en el cuerpo: {instruccion}"


def test_el_stub_de_tema_publica_la_misma_LINEA_y_ningun_bullet(toy_vault):
    """#398, la rama tema — y el cierre de #76 por otra vía: el stub ya no puede pedirle planetas a
    un tema porque no le pide NADA. La línea nombra al sujeto, que es lo único que la sección tiene
    que decir mientras la lectura no ocurrió."""
    seed_topic()
    ads_json([rec("2020gpsA...1..1A")], slug="gp")
    mn.write_paper_notes("gp", include_all=False, force=False, theme=True)
    body = (toy_vault.PAPERS / "2020gpsA...1..1A.md").read_text(encoding="utf-8")
    assert "_Reclamado por `gaussian-processes`; sin leer desde este sujeto._" in body, body
    assert "planeta" not in body.lower() and "Aporte al tema" not in body


def test_stub_off_ads_comparte_el_bloque_del_tema(toy_vault):
    """Un solo lugar de verdad (criterio de LLM_DISCLAIMER): la rama off-ADS —que ya tenía su
    propio bullet de tema— y la rama ADS de tema escriben el MISMO bloque, así que no divergen."""
    mn.write_web_paper_note("2020Smith", slug="gp", concept="gaussian-processes", url="https://x")
    body = (toy_vault.PAPERS / "2020Smith.md").read_text(encoding="utf-8")
    assert mn.vista_block("gaussian-processes") in body


def test_vista_block_sin_objetivo_degrada_a_generico(toy_vault):
    """make_notes corrido suelto, fuera de la cadena: sin objective.yaml el stub sale genérico
    (nunca inventado) y no rompe la generación."""
    toy_vault.OBJECTIVE_YAML.unlink()
    block = mn._legacy_vista_block("Estrella Test", theme=False)
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
    (regla #0, flujo unidireccional). El inventario reporta el estado de la literatura.  @inv INV-11"""
    mn.write_star_note("test_star", force=False)
    t = (toy_vault.STARS / "test_star.md").read_text(encoding="utf-8")
    cabecera = next(l for l in t.split("\n") if l.startswith("| Eje |"))
    assert [c.strip() for c in cabecera.strip("|").split("|")] == [
        "Eje", "Paper", "Dice", "Método / baseline"]
    # y la ausencia está DICHA, no sólo omitida: el que llena la tabla tiene que saber por qué
    assert 'Sin columna "valor adoptado"' in t and "regla #0" in t


# ── #71: migración de disputes a posiciones explícitas ──────────────────────────────────────

PROSA = ("# Estrella Test\n\n> Cabecera.\n>\n> _Generado con Almagesto v1.0.0._\n\n"
         "## Resumen\nLa señal **b** es dudosa según [[2020disD...1..1D]].\n")


def ficha_vieja(toy_vault, planets):
    return mk_note(toy_vault.STARS, "test_star",
                   {"name": "Estrella Test", "slug": "test_star", "P_rot_days": 34.0,
                    "planets": planets, "tags": ["star"]}, PROSA)


def test_migrate_disputes_materializa_el_polo_implicito(toy_vault, capsys):
    """El schema viejo escribía UN solo lado (el paper, con `alt`); el otro era implícito — el valor
    del frontmatter, o sea NEA. La migración lo hace explícito, que es justo lo que el consumidor
    necesita ver: "hay autoridad" vs "la bóveda no sabe"."""
    dest = ficha_vieja(toy_vault, [
        {"letter": "b", "P_days": 20.0, "K_ms": 0.9, "e": 0.1, "mass_earth": 2.0,
         "status": "confirmed",
         "disputes": [{"field": "K", "ref": "2020disD...1..1D", "alt": 1.4, "note": "K distinto"}]}])
    assert mn.migrate_disputes(dest) is True
    fm = read_fm(dest)
    assert fm["disputes"] == [{"field": "b.K", "note": "K distinto", "posiciones": [
        {"ref": "2020disD...1..1D", "value": 1.4},
        {"source": "ground_truth", "value": 0.9}]}]
    assert "disputes" not in fm["planets"][0]        # no queda duplicada en el schema viejo
    claves = list(fm)                               # va donde vivía la información que discute
    assert claves.index("disputes") == claves.index("planets") + 1


def test_migrate_disputes_no_borra_los_comentarios_del_frontmatter(toy_vault, capsys):
    """AUD-169 / INV-139 — la re-serialización con `yaml.safe_dump` tiraba TODOS los comentarios.

    El framework instruye editar el frontmatter a mano («el `P_rot` lo puso el usuario»), así que
    esos comentarios son curación: un estampador que los borra destruye trabajo que nadie puede
    reconstruir, y encima informa éxito."""
    dest = ficha_vieja(toy_vault, [
        {"letter": "b", "P_days": 20.0, "K_ms": 0.9, "e": 0.1, "mass_earth": 2.0,
         "status": "confirmed",
         "disputes": [{"field": "K", "ref": "2020disD...1..1D", "alt": 1.4}]}])
    texto = dest.read_text(encoding="utf-8")
    dest.write_text(texto.replace("P_rot_days: 34.0",
                                  "# lo puso el usuario a mano (Baliunas 1996)\nP_rot_days: 34.0  # sin NEA"),
                    encoding="utf-8")
    assert mn.migrate_disputes(dest) is True
    salida = dest.read_text(encoding="utf-8")
    assert "# lo puso el usuario a mano (Baliunas 1996)" in salida
    assert "P_rot_days: 34.0  # sin NEA" in salida
    assert read_fm(dest)["P_rot_days"] == 34.0           # y sigue parseando


def test_migrate_disputes_existence_usa_el_status_de_nea(toy_vault):
    """`existence` no tiene valor numérico: lo que NEA sostiene es el `status` del planeta."""
    dest = ficha_vieja(toy_vault, [
        {"letter": "b", "P_days": 20.0, "status": "confirmed",
         "disputes": [{"field": "existence", "ref": "2020disD...1..1D", "note": "no la ve"}]}])
    mn.migrate_disputes(dest)
    d = read_fm(dest)["disputes"][0]
    assert d["field"] == "b.existence"
    assert d["posiciones"][1] == {"source": "ground_truth", "value": "confirmed"}


def test_migrate_disputes_sin_valor_en_nea_no_lo_inventa(toy_vault):
    """Si NEA no tiene el valor —el caso normal con K y e (#70)— la posición queda SIN `value`: es
    "hay autoridad y calla", no un número supuesto."""
    dest = ficha_vieja(toy_vault, [
        {"letter": "b", "P_days": 20.0, "K_ms": None,
         "disputes": [{"field": "K", "ref": "2020disD...1..1D", "alt": 1.4}]}])
    mn.migrate_disputes(dest)
    assert read_fm(dest)["disputes"][0]["posiciones"][1] == {"source": "ground_truth"}


def test_migrate_disputes_no_toca_la_prosa_ni_las_fichas_sin_disputas(toy_vault, capsys):
    """La migración re-serializa el FRONTMATTER (cambia la estructura, no se puede hacer por línea),
    así que el cuerpo tiene que sobrevivir byte a byte — y una ficha sin disputas viejas no se
    reescribe: sin esto, un backfill tocaría toda la bóveda para nada."""
    limpia = ficha_vieja(toy_vault, [{"letter": "b", "P_days": 20.0}])
    antes = limpia.read_text(encoding="utf-8")
    assert mn.migrate_disputes(limpia) is False
    assert limpia.read_text(encoding="utf-8") == antes          # byte a byte

    dest = mk_note(toy_vault.STARS, "otra",
                   {"name": "Otra", "planets": [{"letter": "b", "K_ms": 0.9, "disputes": [
                       {"field": "K", "ref": "2020disD...1..1D", "alt": 1.4}]}], "tags": ["star"]},
                   PROSA)
    mn.migrate_disputes(dest)
    assert dest.read_text(encoding="utf-8").split("---\n", 2)[2] == PROSA


def test_migrate_disputes_tampoco_inventa_el_valor_del_paper(toy_vault):
    """La regla "si no hay valor, la posición va sin `value`" se aplicaba SÓLO al polo ground_truth.
    `alt` era exclusivo de las disputas de VALOR, así que toda disputa de `existence` —el caso más
    frecuente— migraba con `value: null` del lado del paper, que por la convención del otro polo se
    lee como "esta fuente calla": lo contrario de lo que el paper sostiene."""
    dest = ficha_vieja(toy_vault, [{"letter": "b", "status": "confirmed", "disputes": [
        {"field": "existence", "ref": "2020disD...1..1D", "note": "no la ve"}]}])
    mn.migrate_disputes(dest)
    assert read_fm(dest)["disputes"][0]["posiciones"][0] == {"ref": "2020disD...1..1D"}


def test_migrate_disputes_avisa_cuando_la_vieja_no_tiene_ref(toy_vault, capsys):
    """El lint pre-1.19.0 aceptaba una disputa sin `ref`; migrada queda como posición sin quién la
    sostenga y el lint la bloquea. El migrador es idempotente, así que sin aviso la bóveda quedaba
    en exit 1 tras correr exactamente el comando que el lint recomienda, sin pista de qué pasó."""
    dest = ficha_vieja(toy_vault, [{"letter": "b", "K_ms": 0.9, "disputes": [
        {"field": "K", "alt": 1.4, "note": "sin ref"}]}])
    mn.migrate_disputes(dest)
    assert "sin `ref`" in capsys.readouterr().out


def test_migrate_all_disputes_no_muere_a_mitad_del_barrido(toy_vault, capsys):
    """Una ficha con `planets` mal formado tiraba el backfill con AttributeError y dejaba la bóveda
    a MEDIO migrar: las fichas posteriores quedaban con el schema viejo y sin aviso."""
    for stem in ("a_sana", "c_sana"):
        mk_note(toy_vault.STARS, stem, {"name": stem, "tags": ["star"], "planets": [
            {"letter": "b", "K_ms": 0.9,
             "disputes": [{"field": "K", "ref": "2020disD...1..1D", "alt": 1.4}]}]}, PROSA)
    mk_note(toy_vault.STARS, "b_rara", {"name": "B", "tags": ["star"], "planets": ["b"]}, PROSA)
    mn.migrate_all_disputes()
    assert "disputes" in read_fm(toy_vault.STARS / "c_sana.md")      # la de después SÍ se migró
    assert "no es una lista de mapas" in capsys.readouterr().out     # y la rara se avisó


def test_migrate_disputes_no_escribe_basura_si_disputes_no_es_lista(toy_vault, capsys):
    """`disputes: "b.K"` a nivel nota + una disputa vieja escribía la lista de CARACTERES a disco
    (y con un mapa, sus claves). Cobarde: no toca el archivo."""
    dest = mk_note(toy_vault.STARS, "test_star",
                   {"name": "T", "tags": ["star"], "disputes": "b.K", "planets": [
                       {"letter": "b", "K_ms": 0.9,
                        "disputes": [{"field": "K", "ref": "2020disD...1..1D", "alt": 1.4}]}]}, PROSA)
    antes = dest.read_text(encoding="utf-8")
    assert mn.migrate_disputes(dest) is False
    assert dest.read_text(encoding="utf-8") == antes
    assert "no es una lista" in capsys.readouterr().out


def test_migrate_disputes_no_pierde_la_disputa_que_deja_sin_migrar(toy_vault, capsys):
    """`pop("disputes")` corre ANTES del `isinstance`, así que el `continue` "cobarde" salta la
    migración con el dato ya fuera del dict y el `write_text` final lo borra del disco. El mensaje
    dice "esa quedó sin migrar, revisala a mano" y no queda nada que revisar: se pierden el bibcode
    y el valor discrepante, y después el lint queda en verde afirmando que no hay desacuerdos."""
    dest = ficha_vieja(toy_vault, [
        {"letter": "b", "disputes": "Feng+2017 dice que b no existe (ref 2017AJ....154..135F)"},
        {"letter": "c", "disputes": [{"field": "K", "ref": "2019MNRAS.484L...8K", "alt": 1.6}]},
    ])
    mn.migrate_disputes(dest)
    texto = dest.read_text(encoding="utf-8")
    assert "2017AJ....154..135F" in texto, (
        "la disputa que el mensaje manda revisar a mano desapareció del archivo")


def test_migrate_disputes_no_pierde_la_entrada_vieja_que_no_es_un_mapa(toy_vault, capsys):
    """Hermano del anterior por la otra rama cobarde: el elemento que no es un mapa también se
    pierde, porque `viejas` ya salió del planeta cuando el `continue` lo saltea."""
    dest = ficha_vieja(toy_vault, [{"letter": "b", "disputes": ["esto-no-es-un-mapa",
                                                                {"field": "K",
                                                                 "ref": "2019MNRAS.484L...8K"}]}])
    mn.migrate_disputes(dest)
    assert "esto-no-es-un-mapa" in dest.read_text(encoding="utf-8")


def test_migrate_disputes_letter_nulo_no_inventa_un_eje(toy_vault):
    """`letter: null` es estado normal (lo copia el ground-truth cuando NEA no nombra el planeta):
    producía `field: None.K`, un eje que no existe y que el lint no valida."""
    dest = ficha_vieja(toy_vault, [{"letter": None, "K_ms": 0.9, "disputes": [
        {"field": "K", "ref": "2020disD...1..1D", "alt": 1.4}]}])
    mn.migrate_disputes(dest)
    assert read_fm(dest)["disputes"][0]["field"] == "K"


@pytest.mark.parametrize("obj", [{"short": 2026}, {"short": "s", "relevance": "rv"},
                                 {"short": "s", "relevance": {"facets": "radial velocity"}},
                                 {"short": "s", "relevance": {"facets": [{"rv": "x"}]}}])
def test_objetivo_mal_formado_degrada_sin_romper_ni_inventar(toy_vault, obj):
    """El stub es el ÚNICO lector de `objective.short` (ni query_ads ni el lint lo miran), así que
    un `short: 2026` mataba la generación de notas a mitad de cadena, después de gastar la red. Y
    `facets` como string se deshacía en caracteres: facetas fabricadas escritas a la bóveda."""
    write_yaml(cfg.OBJECTIVE_YAML, obj)
    block = mn._legacy_vista_block("Estrella Test", theme=False)
    assert "## Vista — Estrella Test" in block
    assert "· " not in block.split("Ejes del objetivo")[1].split(":**")[0]   # sin facetas inventadas


def test_migrate_disputes_es_idempotente(toy_vault):
    dest = ficha_vieja(toy_vault, [
        {"letter": "b", "K_ms": 0.9,
         "disputes": [{"field": "K", "ref": "2020disD...1..1D", "alt": 1.4}]}])
    assert mn.migrate_disputes(dest) is True
    texto = dest.read_text(encoding="utf-8")
    assert mn.migrate_disputes(dest) is False                   # ya no hay schema viejo que migrar
    assert dest.read_text(encoding="utf-8") == texto


def test_migrate_disputes_preserva_las_ya_migradas_y_el_orden(toy_vault):
    """Una ficha a medio migrar (o con disputas nuevas escritas a mano) no pierde las que ya
    estaban, y `disputes` queda donde vivía la información: después de `planets`."""
    dest = mk_note(toy_vault.STARS, "test_star",
                   {"name": "Estrella Test", "planets": [
                       {"letter": "b", "K_ms": 0.9,
                        "disputes": [{"field": "K", "ref": "2020disD...1..1D", "alt": 1.4}]}],
                    "disputes": [{"field": "P_rot", "posiciones": [
                        {"ref": "2018autA...1..1A", "value": 33},
                        {"ref": "2021autB...1..1B", "value": 11.5}]}],
                    "data_local": None, "tags": ["star"]}, PROSA)
    mn.migrate_disputes(dest)
    fm = read_fm(dest)
    assert [d["field"] for d in fm["disputes"]] == ["P_rot", "b.K"]
    assert list(fm).index("disputes") == list(fm).index("planets") + 1


def test_cli_migrate_disputes_no_pide_slug(toy_vault, monkeypatch, capsys):
    """El cableado del backfill (flag → dest → despacho) sólo existe en el CLI: sin un test de punta
    a punta, un `dest` mal escrito pasaría los 480 tests y fallaría en la primera corrida real."""
    ficha_vieja(toy_vault, [{"letter": "b", "K_ms": 0.9, "disputes": [
        {"field": "K", "ref": "2020disD...1..1D", "alt": 1.4}]}])
    assert run_main(monkeypatch, ["--migrate-disputes"]) == 0
    assert read_fm(toy_vault.STARS / "test_star.md")["disputes"][0]["field"] == "b.K"
    assert "1 de 1 ficha(s) migradas" in capsys.readouterr().out


def test_cli_migrate_disputes_sin_nada_que_migrar_lo_dice(toy_vault, monkeypatch, capsys):
    """Y el mensaje del caso vacío no puede leerse como "todo bien": aclara que el lector no mira el
    schema viejo, así que un cero acá no significa que no queden disputas viejas en otra bóveda."""
    assert run_main(monkeypatch, ["--migrate-disputes"]) == 0
    out = capsys.readouterr().out
    assert "0 de 0 ficha(s) migradas" in out and "NO lee el schema viejo" in out


def test_cli_sin_slug_ni_backfill_es_error_amigable(toy_vault, monkeypatch):
    """El `ap.error` nombra los tres modos que corren sin slug — si se agrega un cuarto y no se
    actualiza, el mensaje manda al usuario a adivinar."""
    with pytest.raises(SystemExit):
        run_main(monkeypatch, [])


def test_migrate_disputes_degrada_sin_romper_nada(toy_vault, capsys):
    """Una migración que reescribe frontmatter tiene que ser cobarde: ante cualquier cosa que no
    entiende, NO toca el archivo. Sobre todo con el YAML roto — ahí reescribir sería destruir la
    nota (el lint ya reporta el frontmatter no parseable como bloqueante)."""
    assert mn.migrate_disputes(toy_vault.STARS / "no-existe.md") is False

    sin_fm = toy_vault.STARS / "sin_fm.md"
    sin_fm.write_text("# Sólo prosa, sin frontmatter\n", encoding="utf-8")
    assert mn.migrate_disputes(sin_fm) is False
    assert sin_fm.read_text(encoding="utf-8") == "# Sólo prosa, sin frontmatter\n"

    abierto = toy_vault.STARS / "abierto.md"
    abierto.write_text("---\nname: X\n", encoding="utf-8")     # frontmatter sin cerrar
    assert mn.migrate_disputes(abierto) is False

    roto = toy_vault.STARS / "roto.md"
    contenido = "---\ntitle: dos: puntos sin comillas\n---\n# Cuerpo\n"
    roto.write_text(contenido, encoding="utf-8")
    assert mn.migrate_disputes(roto) is False
    assert roto.read_text(encoding="utf-8") == contenido        # intacta, no destruida
    assert "no parseable — migralo a mano" in capsys.readouterr().out


def test_migrate_all_disputes_barre_y_reporta(toy_vault, capsys):
    ficha_vieja(toy_vault, [{"letter": "b", "K_ms": 0.9, "disputes": [
        {"field": "K", "ref": "2020disD...1..1D", "alt": 1.4}]}])
    mk_note(toy_vault.STARS, "sin_disputas", {"name": "X", "tags": ["star"]}, PROSA)
    assert mn.migrate_all_disputes() == 0
    out = capsys.readouterr().out
    assert "1 de 2 ficha(s) migradas" in out and "la prosa NO se tocó" in out


# ── #74: régimen de validez (sólo en conceptos) ─────────────────────────────────────────────

def test_regimen_solo_en_concepts(toy_vault):
    """En una estrella comparás el mismo número medido dos veces; en un método, dos papers pueden
    decir cosas distintas y estar los dos bien. La tabla existe donde el modo de falla es
    generalizar de más, no donde hay ground-truth."""
    seed_topic()
    mn.write_star_note("test_star", force=False)
    mn.write_concept_note("gp", force=False)
    ficha = (toy_vault.STARS / "test_star.md").read_text(encoding="utf-8")
    concept = (toy_vault.CONCEPTS / "methods" / "gaussian-processes.md").read_text(encoding="utf-8")
    assert mn.REGIMEN in concept and "## Régimen de validez" not in ficha


def test_regimen_va_entre_el_inventario_y_los_huecos(toy_vault):
    """Los dos son productos del contraste y son complementarios: el inventario es el desacuerdo
    REAL bajo las mismas condiciones, el régimen es el aparente (que acá es el hallazgo)."""
    seed_topic()
    mn.write_concept_note("gp", force=False)
    t = (toy_vault.CONCEPTS / "methods" / "gaussian-processes.md").read_text(encoding="utf-8")
    assert t.index("## Síntesis") < t.index("## Inventario por eje") \
        < t.index("## Régimen de validez") < t.index("## Huecos")


def test_regimen_es_la_unidad_del_issue_y_cierra_en_huecos(toy_vault):
    """La unidad de síntesis de un concepto es (afirmación, condiciones, fuente, rol) — el `rol` es
    el de #73 — y el hueco accionable que sale de la tabla es "régimen no cubierto"."""
    seed_topic()
    mn.write_concept_note("gp", force=False)
    t = (toy_vault.CONCEPTS / "methods" / "gaussian-processes.md").read_text(encoding="utf-8")
    cabecera = next(l for l in t.split("\n") if l.startswith("| Afirmación |"))
    assert [c.strip() for c in cabecera.strip("|").split("|")] == [
        "Afirmación", "Vale bajo (régimen)", "Fuente", "Rol"]
    # [-1]: el propio bloque de régimen menciona `## Huecos` al decir a dónde va el hallazgo
    assert "regímenes no cubiertos" in t.split("## Huecos")[-1]


# ── #76 (unitario): objective_lens + la matriz de ramas de vista_block ───────────────────────

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
    write_objective(toy_vault, relevance={"facets": {}}, short="   ")
    assert mn.objective_lens() == ([], "")


def test_objective_lens_sin_archivo_no_propaga_el_error(toy_vault):
    """load_objective() levanta si falta el archivo; el stub NO es el lugar donde eso aborta."""
    toy_vault.OBJECTIVE_YAML.unlink()
    assert mn.objective_lens() == ([], "")


@pytest.mark.parametrize("theme,cabeza", [(True, "Aporte al tema"),
                                          (False, "Ground-truth (planetas / parámetros)")])
def test_vista_block_forma(toy_vault, theme, cabeza):
    """Contrato de forma que asumen los dos templates de cuerpo (se interpolan como `{bloque}`
    al final del f-string): encabezado propio, bullets con la cola compartida y newline final. La
    cola es compartida a propósito: métodos y rol (#73) son del paper, no del tipo de sujeto."""
    block = mn._legacy_vista_block("Sujeto", theme)
    lineas = block.rstrip("\n").split("\n")
    assert block.startswith("## Vista — Sujeto\n") and block.endswith("\n")
    assert len(lineas) == 7 and all(ln.startswith("- **") for ln in lineas[1:])
    assert cabeza in lineas[1]
    assert lineas[-4] == mn._BULLET_METHODS and lineas[-3] == mn._BULLET_ROLE
    assert lineas[-2].startswith("- **Para el objetivo:**")
    assert lineas[-1] == mn._BULLET_ANOTACION, \
        "la regla de anotación (#103) va en las DOS ramas: los seis mecanismos de error que mide " \
        "no dependen de si el sujeto es una estrella o un tema"


def test_vista_block_tema_sin_short_cae_al_generico(toy_vault):
    """La rama que faltaba de la matriz: tema + objetivo sin `short`."""
    write_objective(toy_vault, short=None)
    block = mn._legacy_vista_block("gp", theme=True)
    assert "- **Aporte al tema:**" in block
    assert "- **Para el objetivo:** _(relevancia para el objetivo de la bóveda / huecos)_" in block


def test_vista_block_estrella_sin_facetas_pero_con_short(toy_vault):
    """Y la simétrica: sin facetas el bullet va sin paréntesis, pero el `short` sigue citándose."""
    write_objective(toy_vault, relevance={"facets": {}})
    block = mn._legacy_vista_block("Estrella Test", theme=False)
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
    """La provenance sale de la marca en la primera línea del .txt (verdad de disco).  @inv INV-26"""
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
    #  la primera pasada puede agregar `fulltext_layout` (campo nuevo, INV-102); lo que el
    #  invariante pide es que NO repunte el slug — y la segunda pasada ya no toca nada.
    mn.stamp_fulltext(dest, stem, "hd40307")
    fm = read_fm(dest)
    assert fm["fulltext"] == f"../../raw/fulltext/tau_ceti/{stem}.txt"
    assert fm["fulltext_source"] == "pdftotext"
    assert mn.stamp_fulltext(dest, stem, "hd40307") is False


def test_el_primer_estampado_de_fulltext_NO_depende_del_orden(toy_vault):
    """INV-23 / INC-3 — el último INCUMPLIDO del contrato.

    Un paper relevante para varios sujetos tiene su `.txt` bajo CADA slug (contenido idéntico) y la
    nota es una sola. Todo lo demás que el invariante promete se cumplía —re-correr no repunta, la
    precedencia por calidad anda en las dos direcciones— pero el **primer** estampado tomaba el slug
    que hubiera corrido, así que `A,B` y `B,A` daban un `fulltext:` distinto byte a byte. No pierde
    información ni miente: produce un diff que depende del orden de ingesta, que es ruido, y hacía
    que el «idempotente, sin ruido de diff» de `CLAUDE.md` prometiera más de lo que el código daba.

    El desempate es DECLARADO: mejor calidad primero, y a igual calidad el slug lexicográficamente
    menor — la misma regla que `artefacto_en_otro_slug` ya usa, así que las dos no divergen.
    @inv INV-23"""
    stem = "2009ApJ...700.1732K"
    seed_txt(toy_vault, "tau_ceti", stem)
    seed_txt(toy_vault, "hd40307", stem)

    esperado = f"../../raw/fulltext/hd40307/{stem}.txt"      # `hd40307` < `tau_ceti`
    for primero, segundo in (("tau_ceti", "hd40307"), ("hd40307", "tau_ceti")):
        dest = _note_con_fulltext(toy_vault, stem, None, None)
        mn.stamp_fulltext(dest, stem, primero)
        assert read_fm(dest)["fulltext"] == esperado, f"orden {primero},{segundo}"
        assert mn.stamp_fulltext(dest, stem, segundo) is False, "y el segundo no repunta"

    # la calidad sigue mandando por sobre el orden alfabético
    seed_txt(toy_vault, "aaa-primero", stem, header=f"{cfg.FULLTEXT_OCR_MARK}: con salvedad\n")
    dest = _note_con_fulltext(toy_vault, stem, None, None)
    mn.stamp_fulltext(dest, stem, "aaa-primero")
    assert read_fm(dest)["fulltext"] == esperado, "un OCR alfabéticamente menor no gana"


def test_stamp_fulltext_multi_slug_no_alterna_el_pdf_source(toy_vault):
    """AUD-186 / INV-23 — la regla de estabilidad cubría `fulltext`/`fulltext_source` y NO al
    tercero.

    Un paper compartido por dos slugs quedaba con el `.txt` de uno y la procedencia del PDF del
    otro, **alternando en cada corrida**: el frontmatter dejaba de ser idempotente y el consumidor
    leía `pdf_source: eprint` sobre el `.txt` de un slug cuyo PDF es el publicado."""
    stem = "2009ApJ...700.1732K"
    seed_txt(toy_vault, "tau_ceti", stem)
    seed_txt(toy_vault, "hd40307", stem)
    cfg.record_pdf_source("tau_ceti", stem, "eprint")
    cfg.record_pdf_source("hd40307", stem, "publisher")
    dest = _note_con_fulltext(toy_vault, stem,
                              f"../../raw/fulltext/tau_ceti/{stem}.txt", "pdftotext")
    mn.stamp_fulltext(dest, stem, "tau_ceti")
    assert read_fm(dest)["pdf_source"] == "eprint"
    # correr la cadena del OTRO slug no repunta el `.txt` (empate) → tampoco la procedencia
    mn.stamp_fulltext(dest, stem, "hd40307")
    assert read_fm(dest)["pdf_source"] == "eprint", "alternó con el slug que corrió último"
    assert mn.stamp_fulltext(dest, stem, "hd40307") is False


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
    #  la primera pasada puede agregar `fulltext_layout` (campo nuevo, INV-102); lo que el
    #  invariante pide es que NO repunte el slug — y la segunda pasada ya no toca nada.
    mn.stamp_fulltext(dest, stem, "hd40307")
    fm = read_fm(dest)
    assert fm["fulltext"] == f"../../raw/fulltext/tau_ceti/{stem}.txt"
    assert fm["fulltext_source"] == "pdftotext"
    assert mn.stamp_fulltext(dest, stem, "hd40307") is False


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


def test_cli_web_conecta_los_flags_de_metadata(toy_vault, monkeypatch):
    """`main()` con `--web` despacha DIEZ flags de metadata a `write_web_paper_note` por nombre
    (`--url`→url, `--slug-hint`→slug, `--concept`→concept, `--title`→title, `--author`→
    first_author, `--year`→year, `--n-authors`→n_authors, `--doi`→doi, `--venue`→venue,
    `--accessed`→accessed): eso sólo lo ejercita el CLI, no las llamadas directas a la función que
    ya cubre el resto del archivo. Con cualquiera de esos `dest` mal escrito, ese valor le llega
    `None`/default a la función y la nota sale con el dato que la línea de comandos pidió pisado
    en silencio — el modo de falla real de un `--migrate-disputes` con el dest typeado."""
    seed_topic()
    assert run_main(monkeypatch, [
        "2020Smith", "--web", "--url", "https://example.org/x",
        "--slug-hint", "gp", "--concept", "gaussian-processes",
        "--title", "Un título pasado por CLI", "--author", "Fulano CLI",
        "--year", "2021", "--n-authors", "3", "--doi", "10.1/cli",
        "--venue", "arxiv.org", "--accessed", "2026-01-02"]) == 0
    dest = toy_vault.PAPERS / "2020Smith.md"
    fm = read_fm(dest)
    assert fm["source_url"] == "https://example.org/x"
    assert fm["title"] == "Un título pasado por CLI"
    assert fm["first_author"] == "Fulano CLI"
    assert fm["year"] == 2021
    assert fm["n_authors"] == 3
    assert fm["doi"] == "10.1/cli"
    assert fm["bibstem"] == "arxiv.org"
    assert fm["accessed"] == "2026-01-02"
    assert fm["thesis_links"] == ["gaussian-processes"]
    # --slug-hint no queda sólo en el frontmatter que ya cubrimos vía `slug`: el puntero al .txt
    # del cuerpo también lo usa, así que un dest roto ahí lo dejaría en el placeholder `<slug>`.
    assert "vault/raw/fulltext/gp/2020Smith.txt" in dest.read_text(encoding="utf-8")


def test_cli_web_pending_estampa_pending_source(toy_vault, monkeypatch):
    """`--pending` es la escotilla que declara una fuente off-ADS todavía no conseguida
    (paywall/scan/unextractable, #81). Con el `dest` roto `args.pending` es siempre `None` pase lo
    que pase en la línea de comandos: la nota sale SIN `pending_source`, que es justo lo que el
    lint lista como precondición — el usuario nunca se entera de que hay que proveer la fuente.

    ⚠ **Actualizado por #164**: `--pending` ahora exige `--reason`. El motivo es obligatorio desde
    #80 y este CLI lo tiraba, así que escribía una nota fuera de schema."""
    assert run_main(monkeypatch, ["1999Paywall", "--web", "--slug-hint", "gp",
                                  "--url", "https://pay.wall/x", "--pending", "paywall",
                                  "--reason", "detrás del paywall del editor"]) == 0
    fm = read_fm(toy_vault.PAPERS / "1999Paywall.md")
    assert fm["pending_source"] == "paywall"
    assert fm["accessed"] is None       # pending suprime el default "hoy UTC": sin snapshot todavía


def test_unpend_al_llegar_fulltext(toy_vault):
    mn.write_web_paper_note("1999Paywall", slug="gp", concept="gaussian-processes",
                            url="https://pay.wall/x", pending="paywall")
    dest = toy_vault.PAPERS / "1999Paywall.md"
    # el usuario ya extrajo algo en la nota: eso debe sobrevivir al des-pendeo
    dest.write_text(dest.read_text(encoding="utf-8").replace(
        "_Reclamado por", "SENTINEL_LLM _Reclamado por"), encoding="utf-8")
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
    `· ` con backticks dentro de la extracción LLM no debe confundirse con la cabecera.  @inv INV-18"""
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


def test_cli_restamp_pdf_links_no_pide_slug(toy_vault, monkeypatch, capsys):
    """El cableado del backfill (flag → dest → despacho ANTES de exigir slug) sólo lo ejercita el
    CLI: la suite entera llama a `mn.restamp_pdf_links()` directo, así que un `dest` mal escrito
    —o el despacho movido después del chequeo de slug obligatorio— pasaría los tests igual y
    fallaría recién en la primera corrida real de `make_notes.py --restamp-pdf-links` (sin slug)."""
    rel = _pdf_en_disco(toy_vault, "test_star", "2015oldD...1..1D")
    _nota_vieja(toy_vault, stem="2015oldD...1..1D", pdf_rel=rel)
    assert run_main(monkeypatch, ["--restamp-pdf-links"]) == 0
    assert "1 de 1 re-estampados" in capsys.readouterr().out
    assert f"[📄 PDF]({rel})" in (toy_vault.PAPERS / "2015oldD...1..1D.md").read_text(encoding="utf-8")


def test_find_header_line_es_contrato_compartido(toy_vault):
    """#48: el lint detecta las notas que stamp_pdf_link saltea usando ESTE helper — si cada uno
    definiera "cabecera" por su lado, el detector dejaría de cubrir al fixer. Acá se fija el
    contrato: cabecera reconocida ⇔ stamp_pdf_link actúa.  @inv INV-17"""
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

def test_estado_line_estampa_puntero_sin_tocar_la_prosa(toy_vault):
    # @inv INV-15
    """El registro completo vive en config/registro/<slug>.yaml; la ficha lleva UNA línea con
    fecha, universo→core, pendientes y la ruta. Cirugía: la síntesis LLM queda intacta."""
    mn.write_star_note("test_star", force=False)
    dest = cfg.STARS / "test_star.md"
    dest.write_text(dest.read_text(encoding="utf-8").replace(
        "## Resumen", "## Resumen\nSíntesis LLM que NO se toca."), encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-08-21", "query": "title:(x)", "rows": 2000,
                                    "n_found": 1837, "n_core": 198, "n_candidates": 42,
                                    "truncated": False})
    assert mn.stamp_estado("test_star", dest) is True
    out = dest.read_text(encoding="utf-8")
    assert ("> _Estado — búsqueda 2026-08-21 (1837 → 198 core) · 42 sin juzgar · "
            "registro en `config/registro/test_star.yaml`._") in out
    assert out.index("_Estado") < out.index("_Generado con Almagesto")   # dentro del blockquote
    assert "Síntesis LLM que NO se toca." in out
    assert mn.stamp_estado("test_star", dest) is False                # idempotente


def test_estado_line_se_actualiza_y_no_duplica(toy_vault):
    """Un refresh re-estampa la línea vieja en vez de acumular punteros.

    D-28: con dos corridas la línea muestra la fecha de la ÚLTIMA, cuántas búsquedas hubo, y el
    universo **acumulado** — 120 y no 220, porque las dos corridas se solapan en 100 papers. Sumar
    los embudos es justo el bug que D-28 cierra."""
    mn.write_star_note("test_star", force=False)
    dest = cfg.STARS / "test_star.md"
    cfg.save_busqueda("test_star", {"fecha": "2026-08-01", "n_found": 100, "n_core": 10,
                                    "n_total": 100})
    mn.stamp_estado("test_star", dest)
    cfg.save_busqueda("test_star", {"fecha": "2026-08-21", "n_found": 120, "n_core": 14,
                                    "n_total": 120, "truncated": True})
    assert mn.stamp_estado("test_star", dest) is True
    out = dest.read_text(encoding="utf-8")
    assert out.count("> _Estado") == 1
    # AUD-173: los dos números tienen ALCANCES distintos (el universo es la unión de D-28; el core
    # es el de ESTA corrida) y cada uno lo lleva escrito. Sigue sin ir el nº de corridas (#105).
    assert "búsqueda 2026-08-21 (120 acumulados; 14 core en esta corrida)" in out
    assert "⚠ truncada" in out and "2026-08-01" not in out


def test_estado_line_sin_registro_o_sin_ancla_no_toca_nada(toy_vault):
    """Sin registro no hay nada que estampar; y si la cabecera no tiene la línea `_Generado con
    Almagesto…_` está fuera del contrato → no se inventa (mismo criterio que stamp_pdf_link, #48)."""
    mn.write_star_note("test_star", force=False)
    dest = cfg.STARS / "test_star.md"
    assert mn.stamp_estado("test_star", dest) is False
    fuera = cfg.STARS / "fuera_de_contrato.md"
    fuera.write_text("---\nname: x\n---\n# x\n\n> cabecera propia\n", encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-08-21", "n_found": 5, "n_core": 1})
    assert mn.stamp_estado("test_star", fuera) is False
    # AUD-49: antes buscaba "Búsqueda" con mayúscula, cadena que el estampador NUNCA escribe
    # (`estado_line` emite "búsqueda" en minúscula): el assert no podía fallar ni estampando de más.
    assert "_Estado —" not in fuera.read_text(encoding="utf-8")


def test_estado_line_con_busqueda_no_mapa_no_crashea(toy_vault):
    """El lector (`load_registro`) es tolerante y sus dos consumidores no."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("test_star").write_text("busqueda: 2026-08-22\n", encoding="utf-8")
    assert isinstance(mn.estado_line("test_star", cfg.STARS / "test_star.md"), str)


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
    caveat importa (verify podría 'corregir' la nota hacia un preprint sin saberlo).  @inv INV-29"""
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
    El estampador ancla en el H1, no en la línea del generador, que es justo la que falta.  @inv INV-48"""
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


def test_estado_line_publica_la_verificacion_MAS_RECIENTE(toy_vault):
    """AUD-136 — la cabecera tomaba el PRIMER bloque y el lint toma el MÁXIMO.

    Una nota acumula varios bloques (pasadas sucesivas sobre secciones distintas; medido: hasta 11
    en una bóveda real), así que la cabecera publicaba una fecha vieja sobre una nota que el lint
    daba por re-verificada. Dos implementaciones de la misma regla, contradictorias: hoy es una.
    @inv INV-141"""
    dest = cfg.STARS / "test_star.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("---\ntags: [star]\n---\n# Test\n\n"
                    "## Verificación de citas (2026-01-05)\n\n"
                    "## Verificación de citas (2026-07-30)\n", encoding="utf-8")
    linea = mn.estado_line("test_star", dest)
    assert "verificación 2026-07-30" in linea
    assert "2026-01-05" not in linea


def test_las_cirugias_usan_EL_MISMO_localizador_que_el_parser(toy_vault):
    """AUD-147 — once cirugías ubicaban el frontmatter con `startswith("---\\n")` +
    `find("\\n---\\n", 4)` mientras `split_fm` matchea el delimitador como LÍNEA (`^---[ \\t]*$`).

    Una nota con un espacio al final del `---` de cierre —o con un BOM adelante— parsea perfecto
    para todo el resto del tooling y convertía a las once en un **no-op silencioso**: el estampador
    informa «nada que hacer» sobre una nota que no supo leer. Un solo localizador, no dos."""
    for nombre, texto in (("espacio", "---\ntags: [paper]\nstars: []\n--- \ncuerpo\n"),
                          ("bom", "\ufeff---\ntags: [paper]\nstars: []\n---\ncuerpo\n")):
        p = toy_vault.PAPERS / f"{nombre}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
        assert cfg.split_fm(p.read_text(encoding="utf-8")).get("tags") == ["paper"], nombre
        assert mn.merge_frontmatter_list(p, "stars", ["Estrella Test"]) is True, nombre
        salida = p.read_text(encoding="utf-8")
        assert read_fm(p)["stars"] == ["Estrella Test"], nombre
        assert salida.endswith("cuerpo\n") and "--- \n" in salida or nombre == "bom"
    # el BOM sobrevive a la cirugía: reconstruir con un `"---\n"` literal lo tiraba
    assert (toy_vault.PAPERS / "bom.md").read_text(encoding="utf-8").startswith("\ufeff")


def test_stamp_header_no_escribe_dentro_del_frontmatter(toy_vault):
    """AUD-135 / INV-139 — la rama «Capa LLM» buscaba en el TEXTO ENTERO, frontmatter incluido.

    El framework instruye editar el frontmatter a mano, así que un comentario de curación o un
    `motivo:` que mencione esas dos palabras es un estado alcanzable — y ahí el blockquote se
    insertaba ADENTRO del YAML: `split_fm` devolvía `{}` y la nota caía en una categoría
    bloqueante. Lo dispara `--restamp-headers`, o sea el comando que el propio lint receta: la
    reparación fabricaba el daño que venía a arreglar. Es la gemela de la rama del H1, que ya
    estaba arreglada, con el motivo escrito al lado."""
    dest = cfg.STARS / "hd40307.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("---\nname: HD 40307\ntags:\n- star\ngenerator: Almagesto v1.2.0\n"
                    "# ojo: la prosa de abajo es Capa LLM sin revisar\n---\n"
                    "# hd40307\n\n## Resumen\n\nProsa.\n", encoding="utf-8")
    assert mn.stamp_header(dest) is True
    texto = dest.read_text(encoding="utf-8")
    assert cfg.split_fm(texto).get("name") == "HD 40307", "el frontmatter dejó de parsear"
    assert texto.index("# hd40307") < texto.index("Capa LLM — revisar")
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
    """Una nota tan vieja que ni `generator` tiene: la línea va SIN versión, no con una supuesta.

    El assert **sí** exige el ancla `GENERATOR_LINE`. Antes la prohibía —era más fuerte que la
    intención de este test— y esa parte de más producía el deadlock que el ensayo de deploy midió
    sobre un corpus real: sin el ancla la nota queda permanentemente fuera del alcance de
    `stamp_search_line` (`if i < 0: return False`), así que el lint la reporta para siempre y
    `--restamp-headers` informa éxito en cada corrida. Lo que este test protege es que no se
    **invente** una versión, no que falte el ancla."""
    dest = cfg.STARS / "vieja.md"
    dest.write_text("---\nname: Vieja\ntags:\n- star\n---\n# vieja\n\nProsa.\n", encoding="utf-8")
    assert mn.stamp_header(dest) is True
    out = dest.read_text(encoding="utf-8")
    assert "no registra con qué versión se creó" in out
    assert mn.GENERATOR_LINE in out                  # estampable: el ancla está
    assert cfg.ALMAGESTO_VERSION not in out          # pero no se inventó ninguna versión
    assert "desconocida" in out


def test_stamp_header_no_toca_lo_que_ya_tiene_cabecera(toy_vault):
    mn.write_star_note("test_star", force=False)                   # nace con cabecera
    assert mn.stamp_header(cfg.STARS / "test_star.md") is False


def test_la_nota_de_PAPER_tambien_lleva_el_aviso_de_capa_LLM(toy_vault):
    """#247 — era la única de las tres clases SIN aviso, y es la que más contenido generado tiene:
    la vista es 100 % prosa de un LLM, escrita CON UNA LENTE y en castellano sobre una fuente en
    inglés. La confusión ya ocurrió con un usuario que conoce el sistema: abrió una nota, vio prosa
    interpretada y preguntó si estaba bien. El aviso nombra las tres capas por separado, porque en
    esta nota conviven las tres en secciones distintas."""
    from conftest import mk_note
    mk_note(cfg.PAPERS, "2020a....1A", {"tags": ["paper"], "bibcode": "2020a....1A"}, "# Paper\n")
    assert mn.stamp_header(cfg.PAPERS / "2020a....1A.md") is True
    t = (cfg.PAPERS / "2020a....1A.md").read_text(encoding="utf-8")
    assert "Capa LLM" in t and "con una lente" in t
    assert "nunca fuente de la que citar" in t, "las traducciones son ayuda de lectura"
    assert mn.stamp_header(cfg.PAPERS / "2020a....1A.md") is False, "idempotente"


def test_el_aviso_de_capa_LLM_va_DEBAJO_de_la_cabecera(toy_vault):
    """#378 — `stamp_header_note` ancla en el H1 y no mira qué hay debajo, así que mete el aviso
    ENTRE el H1 y la línea de cabecera. El orden canónico es H1 → cabecera → blockquotes, y con el
    orden invertido `restamp_abstracts` —que ancla en `GENERATOR_LINE`— inserta `## Abstract`
    ARRIBA de la cabecera, la cabecera queda DENTRO de esa sección, y de ahí se la lleva el
    reemplazo del cosechador (#379).

    Medido en una instancia real: 60 de 169 notas con el orden invertido, y **10** que avanzaron a
    los pasos 3-4 (6 con la cabecera ya borrada). La precondición del daño es la nota SIN
    `## Abstract` —el stub off-ADS de #124/#277—, así que #378 sólo hace daño donde #277 ya falló."""
    from conftest import mk_note
    mk_note(cfg.PAPERS, "2020b....1B", {"tags": ["paper"], "bibcode": "2020b....1B"},
            "# Paper\n\n**Autor** (2020)\n· fuente off-ADS · `2020b....1B`\n")
    dest = cfg.PAPERS / "2020b....1B.md"
    assert mn.stamp_header(dest) is True
    t = dest.read_text(encoding="utf-8")
    assert t.index("· fuente off-ADS") < t.index("Capa LLM"), \
        "el aviso va DEBAJO de la cabecera, no entre el H1 y ella"
    assert mn.find_header_line(t) is not None, "la cabecera sigue cumpliendo el contrato"


def test_la_cabecera_sobrevive_a_la_secuencia_COMPLETA_de_backfills(toy_vault):
    """La secuencia de cuatro pasos que #378 reconstruyó con `git log`, como test de integración:
    stub sin `## Abstract` → `--restamp-headers` → `--restamp-abstracts` → cosecha. Cada paso por
    separado parecía inocuo; el daño vive en el orden."""
    from conftest import mk_note
    mk_note(cfg.PAPERS, "2020c....1C", {"tags": ["paper"], "bibcode": "2020c....1C"},
            "# Paper\n\n**Autor** (2020)\n· fuente off-ADS · `2020c....1C`\n")
    dest = cfg.PAPERS / "2020c....1C.md"
    mn.stamp_header(dest)
    mn.restamp_abstracts()
    t = dest.read_text(encoding="utf-8")
    assert mn.find_header_line(t) is not None, "la cabecera no quedó dentro de `## Abstract`"
    assert t.index("· fuente off-ADS") < t.index("## Abstract")


def test_fix_header_order_normaliza_la_nota_ya_invertida(toy_vault, capsys):
    """La otra mitad de #378: el fix impide notas nuevas invertidas, y las que ya lo están siguen
    igual —`stamp_header` es idempotente y no vuelve a tocarlas—. Medido en una instancia real: 50
    notas con el orden invertido y SIN daño (ya tenían `## Abstract`, así que la cascada se detuvo),
    pero con el riesgo condicional de que alguna pierda la sección y el backfill corra encima."""
    from conftest import mk_note
    mk_note(cfg.PAPERS, "2020d....1D", {"tags": ["paper"], "bibcode": "2020d....1D"},
            "# Paper\n\n> ⚠ **Capa LLM — revisar antes de citar.**\n>\n"
            "> _Generado con Almagesto v1.94.0._\n\n**Autor** (2020)\n"
            "· fuente off-ADS · `2020d....1D`\n\n## Abstract\n_(no disponible)_\n")
    dest = cfg.PAPERS / "2020d....1D.md"
    assert mn.fix_header_order() == 1
    t = dest.read_text(encoding="utf-8")
    assert t.index("· fuente off-ADS") < t.index("Capa LLM"), t
    assert mn.find_header_line(t) is not None
    assert mn.fix_header_order() == 0, "idempotente: la segunda corrida no toca nada"


def test_fix_header_order_no_toca_la_nota_en_ORDEN_CANONICO(toy_vault):
    """El recorte: 109 de 169 notas de esa bóveda estaban bien, y un migrador que las reescriba
    produce un diff de 169 archivos donde el cambio real son 60."""
    from conftest import mk_note
    mk_note(cfg.PAPERS, "2020e....1E", {"tags": ["paper"], "bibcode": "2020e....1E"},
            "# Paper\n\n**Autor** (2020)\n· fuente off-ADS · `2020e....1E`\n\n"
            "> ⚠ **Capa LLM — revisar antes de citar.**\n>\n> _Generado con Almagesto v1.94.0._\n")
    antes = (cfg.PAPERS / "2020e....1E.md").read_text(encoding="utf-8")
    assert mn.fix_header_order() == 0
    assert (cfg.PAPERS / "2020e....1E.md").read_text(encoding="utf-8") == antes


def test_stamp_header_destraba_el_puntero_de_busqueda(toy_vault):
    """El punto del backfill: sin cabecera, stamp_search_line no-opea EN SILENCIO (medido: 22 de 25
    notas de una bóveda real). Después del backfill, la misma llamada sí estampa."""
    dest = cfg.STARS / "test_star.md"
    dest.write_text("---\nname: Test Star\ntags:\n- star\ngenerator: Almagesto v1.5.0\n---\n"
                    "# test_star\n\n## Resumen\n\nProsa.\n", encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-08-21", "n_found": 100, "n_core": 10})
    assert mn.stamp_estado("test_star", dest) is False        # antes: silencio
    assert mn.stamp_header(dest) is True
    assert mn.stamp_estado("test_star", dest) is True         # después: aterriza
    assert "> _Estado — búsqueda 2026-08-21" in dest.read_text(encoding="utf-8")


def test_restamp_headers_barre_fichas_y_conceptos(toy_vault, capsys):
    (cfg.CONCEPTS / "activity").mkdir(parents=True, exist_ok=True)
    (cfg.CONCEPTS / "activity" / "c.md").write_text(VIEJA, encoding="utf-8")
    (cfg.STARS / "s.md").write_text("---\nname: S\ntags:\n- star\n---\n# s\n\nProsa.\n",
                                    encoding="utf-8")
    mn.write_star_note("test_star", force=False)                   # ésta ya tiene cabecera
    assert mn.restamp_headers() == 0
    assert "2 de 3 estampadas" in capsys.readouterr().out


def test_cli_restamp_headers_no_pide_slug(toy_vault, monkeypatch):
    """Mismo cableado que --restamp-pdf-links, para el otro backfill sin slug: la suite llama a
    `mn.restamp_headers()` directo en todos lados, así que sólo el CLI de punta a punta detecta un
    `dest` mal escrito o el despacho movido después del `ap.error` que exige slug."""
    dest = cfg.STARS / "vieja.md"
    dest.write_text("---\nname: Vieja\ntags:\n- star\n---\n# vieja\n\nProsa.\n", encoding="utf-8")
    assert run_main(monkeypatch, ["--restamp-headers"]) == 0
    assert "no registra con qué versión se creó" in dest.read_text(encoding="utf-8")


def test_restamp_headers_actua_sobre_la_nota_que_el_lint_marca(toy_vault, capsys):
    """El lint marca la nota si le falta `GENERATOR_LINE`; `restamp_headers` la saltea si tiene
    "Capa LLM". Una nota con el disclaimer pero sin la línea del generador —22 de 25 en el corpus
    real— queda marcada para siempre y el comando que el propio mensaje receta no-opea en silencio.
    El backlog no se puede cerrar con la herramienta documentada."""
    nota = mk_note(toy_vault.STARS, "test_star",
                   {"tags": ["star"], "generator": "Almagesto v1.13.0"},
                   "# test_star\n\n> ⚠ **Capa LLM:** la prosa es síntesis a revisar.\n\nprosa\n")
    mn.restamp_headers()
    assert mn.GENERATOR_LINE in nota.read_text(encoding="utf-8"), (
        "la nota que el lint marca sigue sin la línea del generador tras --restamp-headers")


# ── deadlock #69 en la rama de fallback de stamp_header ──────────────────────
#
# Encontrado corriendo el ensayo de deploy sobre el corpus real de una instancia (1.11.0 →
# 1.22.1), no leyendo código: `--restamp-headers` informó "22 de 25 estampadas" y el lint siguió
# reportando 21 cabeceras no estampables, corrida tras corrida.
#
# Causa: cuando la nota no registra `generator` en su frontmatter —lo normal en todo lo creado
# antes de que el campo existiera— `stamp_header` cae a una línea de fallback ("Cabecera
# normalizada por Almagesto; la nota no registra con qué versión se creó") que no contiene
# `GENERATOR_LINE`. Y `GENERATOR_LINE` no es decorativo: es el punto de inserción que
# `stamp_search_line` busca para poder actuar (`if i < 0: return False`, "no inventamos"). O sea
# que la cabecera "arreglada" no sirve para lo único que la cabecera existe para habilitar, el
# lint tiene razón en seguir marcándola, y el comando que el propio mensaje del lint receta
# informa éxito cada vez.
#
# Es el mismo modo de falla que #69 vino a cerrar —el no-op silencioso— una capa más abajo: antes
# el estampador salteaba la nota, ahora la escribe y miente sobre el resultado.
#
# El fix no puede inventar la versión (regla del repo: "mejor sin dato que con uno supuesto"), así
# que la línea de fallback tiene que llevar el ancla y decir explícitamente que la versión es
# desconocida.

CUERPO_SIN_GENERATOR = "# s\n\n> ⚠ **Capa LLM:** la prosa es síntesis a revisar.\n\nprosa\n"


def nota_sin_generator():
    """Ficha con el disclaimer de capa LLM pero SIN `generator` — el estado de todo lo creado antes
    de que el campo existiera, que es justo la población que `--restamp-headers` viene a rescatar."""
    return mk_note(cfg.STARS, "s", {"tags": ["star"], "planets": []}, CUERPO_SIN_GENERATOR)


def test_restamp_headers_deja_la_nota_estampable(toy_vault):
    """El criterio no es "se escribió algo": es que la cabecera quede **utilizable por los
    estampadores**, que es para lo que existe."""
    p = nota_sin_generator()
    mn.restamp_headers()
    assert mn.GENERATOR_LINE in p.read_text(encoding="utf-8")


def test_restamp_headers_no_inventa_la_version(toy_vault):
    """"No inventamos" (#48): sin `generator` en el frontmatter, la línea no puede afirmar una
    versión concreta — tiene que decir que no se sabe."""
    p = nota_sin_generator()
    mn.restamp_headers()
    texto = p.read_text(encoding="utf-8")
    assert cfg.ALMAGESTO_VERSION not in texto
    assert "desconocid" in texto.lower()


def test_el_lint_deja_de_reportar_la_nota_tras_el_restamp(toy_vault, capsys):
    """El círculo lint→comando→lint tiene que **cerrar**. Éste es el test que el ensayo de deploy
    falsó: 22 estampadas y 21 seguían reportadas."""
    nota_sin_generator()
    mn.restamp_headers()
    capsys.readouterr()
    lint.main()
    rep = (cfg.ROOT / "outputs").glob("lint-*.md")
    texto = next(rep).read_text(encoding="utf-8")
    assert "Cabecera no estampable" in texto
    seccion = texto.split("## Cabecera no estampable")[1].split("\n##")[0]
    assert "(0)" in seccion.split("\n")[0], f"el lint sigue reportando la nota:\n{seccion}"


def test_stamp_estado_puede_actuar_tras_el_restamp(toy_vault):
    """El punto de todo el ejercicio: `GENERATOR_LINE` es el punto de INSERCIÓN de
    `stamp_search_line`. Si tras el restamp sigue sin poder actuar, la cabecera no se arregló —
    sólo se le escribió texto encima."""
    p = nota_sin_generator()
    mn.restamp_headers()
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.save_busqueda("s", {"fecha": "2026-08-01", "n_found": 412, "n_core": 37,
                            "n_total": 40, "n_candidates": 3, "n_dropped": 0,
                            "rows": 2000, "truncated": False,
                            "almagesto_version": cfg.ALMAGESTO_VERSION})
    assert mn.stamp_estado("s", p) is True


# ── --sync-mirror: backfill del espejo ficha↔ground-truth (#70) ──────────────
#
# Qué es `--sync-mirror` y, sobre todo, qué NO es. El frontmatter de `stars/` es espejo puro de
# NEA (#70): vale lo que dice el ground-truth o NADA. Una instancia que viene de una versión
# anterior tiene el espejo desincronizado, y el lint lo bloquea campo por campo. Medido en la
# instancia real (1.11.0 → 1.22.1): 13 contradicciones, 12 de ellas el mismo caso trivial — la
# ficha tiene el campo en `null` y NEA sí trae el valor. Eso es relleno mecánico y no necesita
# juicio.
#
# La 13ª es la que define la frontera: `hd40307 P_rot_days: 48` con NEA sin el valor. Ahí el
# número salió de literatura, y adoptarlo o no es decisión del consumidor, no del migrador —
# copiarlo al revés (ficha → GT) o borrarlo sería justamente romper #70 en la otra dirección. Por
# eso el contrato es add-only y en un solo sentido: null en la ficha + valor en NEA → se copia;
# todo lo demás se deja y se reporta.

def gt(slug, planets, **host):
    (cfg.GROUND_TRUTH / f"{slug}.json").write_text(
        json.dumps({"slug": slug, "host": host, "planets": planets}), encoding="utf-8")


def ficha(slug, fm, body="# x\n\nprosa que no se toca\n"):
    return mk_note(cfg.STARS, slug, {"tags": ["star"], **fm}, body)


# ── el caso trivial: 12 de los 13 residuos medidos ──────────────────────────

def test_sync_mirror_rellena_el_campo_nulo_desde_el_ground_truth(toy_vault):
    """El caso que domina el residuo real: la ficha tiene `mass_earth: null` y NEA trae el valor.
    Es relleno mecánico —el frontmatter es espejo de NEA— y hoy hay que hacerlo a mano en cada
    planeta de cada ficha."""
    gt("s", [{"letter": "b", "P_days": 5.0, "K_ms": 2.0, "e": 0.0, "mass_earth": 8.99,
              "status": "confirmed"}], mass_msun=1.0)
    ficha("s", {"planets": [{"letter": "b", "P_days": 5.0, "K_ms": 2.0, "e": 0.0,
                             "mass_earth": None, "status": "confirmed"}]})
    mn.sync_mirror()
    assert read_fm(cfg.STARS / "s.md")["planets"][0]["mass_earth"] == 8.99


def test_sync_mirror_rellena_tambien_los_campos_estelares(toy_vault):
    """Los cuatro campos de la estrella (`spectral_type`, `teff_K`, `dist_pc`, `P_rot_days`) son
    espejo igual que los del planeta: mismo criterio, mismo relleno."""
    gt("s", [], teff_K=5344.0, dist_pc=3.6)
    ficha("s", {"teff_K": None, "dist_pc": None, "planets": []})
    mn.sync_mirror()
    fm = read_fm(cfg.STARS / "s.md")
    assert (fm["teff_K"], fm["dist_pc"]) == (5344.0, 3.6)


def test_sync_mirror_escribe_la_clave_que_falta_aunque_nea_calle(toy_vault):
    """#272 — `mass_msun` entró al schema después de que estas fichas se crearan, así que la clave
    **no existe** en ninguna. Sin escribirla, la nota evade el espejo y queda reportada como schema
    incompleto para siempre; escribir `null` es el estado correcto (la autoridad contestó y no tiene
    el dato), no un campo a completar."""
    gt("s", [], mass_msun=None)
    ficha("s", {"planets": []})
    assert "mass_msun" not in read_fm(cfg.STARS / "s.md")
    mn.sync_mirror()
    fm = read_fm(cfg.STARS / "s.md")
    assert "mass_msun" in fm and fm["mass_msun"] is None


def test_sync_mirror_espeja_la_masa_estelar(toy_vault):
    """#272 — la masa estelar es el factor que convierte K en m·sini (m·sini ∝ M★^(2/3)), así que
    el rango 0,699–0,78 M☉ de la literatura mueve cada masa mínima un 7,6 %. Sin el campo, la ficha
    declaraba un hueco de arbitraje sobre un valor que su propia autoridad ya tiene."""
    gt("s", [], mass_msun=0.77)
    ficha("s", {"planets": []})
    mn.sync_mirror()
    assert read_fm(cfg.STARS / "s.md")["mass_msun"] == 0.77


# ── formas inesperadas del ground_truth: host/planets escalares ────────────

def test_sync_mirror_con_host_escalar_no_revienta(toy_vault, capsys):
    """`make_notes.py:489` — `host = gt.get("host") or {}`.

    `--sync-mirror` es el consumidor NUEVO (23-08) de un formato viejo. `lint.py:795-815` ya
    endurece exactamente este ground-truth (`host` no-mapa → contradicción reportada, `planets`
    no-lista → reportada, entradas no-mapa → filtradas) y sigue funcionando; `sync_mirror` lee lo
    mismo sin ninguna de esas guardas y muere con `AttributeError`. Dos lectores del mismo
    artefacto con dos niveles de tolerancia: el que ESCRIBE en las fichas es el frágil."""
    (cfg.GROUND_TRUTH / "s.json").write_text(
        json.dumps({"slug": "s", "host": "G8V", "planets": []}), encoding="utf-8")
    mk_note(cfg.STARS, "s", {"tags": ["star"], "teff_K": None, "planets": []}, "# s\n\nprosa\n")
    mn.sync_mirror()
    assert "s.md" in capsys.readouterr().out


def test_sync_mirror_con_planets_escalar_no_revienta(toy_vault, capsys):
    """Hermano del anterior sobre el otro campo. Un `planets` string se recorre carácter por
    carácter y `p.get` revienta. El lint reporta este mismo ground-truth ("`planets` del
    ground-truth no es una lista"); `sync_mirror` no."""
    (cfg.GROUND_TRUTH / "s.json").write_text(
        json.dumps({"slug": "s", "host": {}, "planets": "b"}), encoding="utf-8")
    mk_note(cfg.STARS, "s", {"tags": ["star"], "planets": [{"letter": "b", "P_days": None}]},
            "# s\n\nprosa **b**\n")
    mn.sync_mirror()
    assert "s.md" in capsys.readouterr().out


# ── la frontera: lo que NO puede tocar ─────────────────────────────────────

def test_sync_mirror_no_toca_un_valor_que_nea_no_tiene(toy_vault, capsys):
    """El 13º residuo medido (`hd40307 P_rot_days: 48`, NEA sin `st_rotp`). Ese número salió de
    literatura: adoptarlo, borrarlo o copiarlo hacia el ground-truth es decidir por el
    consumidor, que es lo que la regla #0 prohíbe. El migrador lo deja y lo reporta para que lo
    resuelva una persona (prosa citada, o `disputes[]` si hay desacuerdo real)."""
    gt("s", [], mass_msun=1.0)
    ficha("s", {"P_rot_days": 48, "planets": []})
    mn.sync_mirror()
    assert read_fm(cfg.STARS / "s.md")["P_rot_days"] == 48
    assert "P_rot_days" in capsys.readouterr().out


def test_sync_mirror_no_pisa_un_valor_distinto(toy_vault, capsys):
    """Dos valores distintos para el mismo hecho **es una disputa**, no un error de sincronización:
    pisarlo borraría la posición de la ficha sin dejar rastro. Add-only significa esto.  @inv INV-08"""
    gt("s", [{"letter": "b", "mass_earth": 8.99, "status": "confirmed"}], mass_msun=1.0)
    ficha("s", {"planets": [{"letter": "b", "mass_earth": 3.0, "status": "confirmed"}]})
    mn.sync_mirror()
    assert read_fm(cfg.STARS / "s.md")["planets"][0]["mass_earth"] == 3.0
    assert "b" in capsys.readouterr().out


def test_sync_mirror_no_inventa_un_planeta_que_la_ficha_no_lista(toy_vault):
    """Agregar un planeta entero no es sincronizar un campo: qué planetas lista la ficha es una
    contradicción que el lint reporta aparte y que alguien tiene que mirar (puede ser una señal no
    confirmada escrita en `planets[]` en vez de `disputes` como `<letra>.existence`)."""
    gt("s", [{"letter": "b", "mass_earth": 1.0, "status": "confirmed"},
             {"letter": "c", "mass_earth": 2.0, "status": "confirmed"}], mass_msun=1.0)
    ficha("s", {"planets": [{"letter": "b", "mass_earth": None, "status": "confirmed"}]})
    mn.sync_mirror()
    assert len(read_fm(cfg.STARS / "s.md")["planets"]) == 1


def test_sync_mirror_sin_ground_truth_no_hace_nada(toy_vault):
    """Sin el JSON de NEA no hay autoridad contra la cual espejar: tocar la ficha ahí sería
    inventar."""
    p = ficha("s", {"teff_K": None, "planets": []})
    antes = p.read_bytes()
    mn.sync_mirror()
    assert p.read_bytes() == antes


# ── invariantes de todo migrador del repo ──────────────────────────────────

def test_sync_mirror_no_toca_la_prosa(toy_vault):
    """La prosa es síntesis LLM: ningún migrador la toca (mismo contrato que `--migrate-disputes`).  @inv INV-15"""
    cuerpo = "# s\n\nprosa **importante** con [[2019abc]] y una tabla.\n\n| a | b |\n|---|---|\n"
    gt("s", [{"letter": "b", "mass_earth": 8.99, "status": "confirmed"}], mass_msun=1.0)
    p = ficha("s", {"planets": [{"letter": "b", "mass_earth": None, "status": "confirmed"}]}, cuerpo)
    mn.sync_mirror()
    assert p.read_text(encoding="utf-8").endswith(cuerpo)


def test_sync_mirror_es_idempotente(toy_vault):
    """Segunda corrida: cero cambios. Invariante rector de la cadena (`maintain/SKILL.md`)."""
    gt("s", [{"letter": "b", "mass_earth": 8.99, "status": "confirmed"}], mass_msun=1.0)
    p = ficha("s", {"planets": [{"letter": "b", "mass_earth": None, "status": "confirmed"}]})
    mn.sync_mirror()
    despues = p.read_bytes()
    mn.sync_mirror()
    assert p.read_bytes() == despues


def test_cli_sync_mirror_no_pide_slug(toy_vault, monkeypatch):
    """Es un backfill de toda la bóveda, como `--restamp-headers`: sin slug. El cableado del flag
    sólo existe por línea de comandos — un `dest` mal escrito pasaría la suite entera y fallaría en
    la primera corrida real (ya pasó con `--migrate-disputes`)."""
    gt("s", [{"letter": "b", "mass_earth": 8.99, "status": "confirmed"}], mass_msun=1.0)
    ficha("s", {"planets": [{"letter": "b", "mass_earth": None, "status": "confirmed"}]})
    assert run_main(monkeypatch, ["--sync-mirror"]) == 0
    assert read_fm(cfg.STARS / "s.md")["planets"][0]["mass_earth"] == 8.99


# ── issue 0.2 · toda escritura a vault/ pasa por el helper atómico (D-53 / INV-90) ───────────────

def test_notas_pasan_por_el_helper(toy_vault, monkeypatch):
    """`make_notes` es el writer que MÁS escribe de la bóveda y el único que no era atómico: sus
    14 escrituras a `vault/wiki/` iban por `dest.write_text(...)` directo. El test es de
    comportamiento y no de `grep`: intercepta `Path.write_text` y exige que **ninguna** escritura
    bajo `vault/` la use directo — así también cae una escritura futura hecha con `open()` o
    `shutil`, que un grep de `write_text(` no vería.  @inv INV-90

    ⚠ **Cobertura medida por mutación (2026-08-24): 3 de los 14 sitios de escritura de
    `make_notes`** (líneas 1170, 1261, 1293). Los otros 11 viven en cirugías que estas corridas no
    alcanzan —`stamp_excluded` sólo escribe cuando el conjunto de excluidos CAMBIA, los migradores
    sólo con material vintage sembrado—. El barrido repo-wide de los 14 lo da el test estático
    `test_lib_config.py::test_sin_escrituras_directas_a_vault` (verificado por mutación: detecta
    los 14). Los dos son complementarios y ninguno solo alcanza; decirlo acá evita que alguien lea
    este test como la garantía completa, que es el modo de falla que el repo llama "afirmar de
    menos"."""
    real = cfg.Path.write_text

    def guardia(self, *a, **kw):
        # el helper escribe primero a `<nombre>.tmp<pid>`; cualquier OTRA escritura directa bajo
        # `vault/` es la que este test existe para prohibir. Comparar conjuntos de RUTAS no
        # alcanzaba: una ruta escrita directo Y además por el helper en otra llamada pasaba
        # (auditado por mutación — el grep estático la veía, este test no).
        if ".tmp" not in self.name and str(self).startswith(str(toy_vault.VAULT)):
            raise AssertionError(f"escritura directa (no atómica) a {self}")
        return real(self, *a, **kw)

    # el sembrado del test (fixtures escribiendo `themes.yaml`, `ads.json`) NO es código de
    # producción: la guardia se instala DESPUÉS.
    ads_json([rec("2020aaaA...1..1A"), rec("2020nonC....1..1C", relevant=False)])
    seed_topic()
    monkeypatch.setattr(cfg.Path, "write_text", guardia)

    # Ejercitar las RAMAS, no una sola: la primera versión de este test corría sólo
    # `write_star_note` + `--restamp-headers` y una mutación deliberada en `stamp_excluded`
    # (línea 729) pasaba inadvertida. La cobertura de un test de comportamiento es exactamente
    # el conjunto de caminos que recorre — el barrido repo-wide lo da el test estático de
    # `test_lib_config.py::test_sin_escrituras_directas_a_vault`.
    assert run_main(monkeypatch, ["test_star", "--all"]) == 0      # ficha + papers, notas NUEVAS
    # 2ª corrida: la ficha ya existe → entran las cirugías sobre nota existente (`stamp_excluded`,
    # `stamp_search_line`, cabecera), que son la mayoría de los 14 sitios de escritura y que la
    # primera corrida no toca. Auditado por mutación: sin esta línea, romper `stamp_excluded`
    # pasaba inadvertido.
    assert run_main(monkeypatch, ["test_star", "--all"]) == 0
    assert run_main(monkeypatch, ["gp", "--theme"]) == 0           # concept + papers de tema
    assert run_main(monkeypatch, ["gp", "--theme"]) == 0
    assert run_main(monkeypatch, ["--restamp-headers"]) == 0
    assert run_main(monkeypatch, ["--restamp-pdf-links"]) == 0
    assert run_main(monkeypatch, ["--migrate-disputes"]) == 0
    assert run_main(monkeypatch, ["--sync-mirror"]) == 0
    assert (toy_vault.STARS / "test_star.md").exists(), "el test no escribió nada — no prueba nada"


def test_corte_publicando_no_deja_la_nota_a_medias(toy_vault, monkeypatch):
    """Inyección de fallo de punta a punta (patrón F4 de la 8ª): el corte llega en la publicación
    de una nota real. La nota previa —extracción LLM, lo menos regenerable de la bóveda— queda
    byte-idéntica y no queda basura `.tmp` al lado.  @inv INV-21"""
    mn.write_star_note("test_star", force=False)
    dest = toy_vault.STARS / "test_star.md"
    antes = dest.read_bytes()

    def boom(*a, **k):
        raise OSError("disco lleno")

    monkeypatch.setattr(cfg.os, "replace", boom)
    with pytest.raises(OSError):
        mn.write_star_note("test_star", force=True)
    assert dest.read_bytes() == antes
    assert [p.name for p in toy_vault.STARS.iterdir() if ".tmp" in p.name] == []


# ── issue 3.1 · D-10/D-11/D-24: la lista de papers se MATERIALIZA, con estado y origen ──────────
#
# Medido en la instancia real: la ficha de tau Ceti promete "155 papers" en su roll-up Dataview y
# discute 8. Peor: el roll-up es un bloque ```dataview``` — un agente que abre el `.md` ve el CÓDIGO
# de la query, no sus resultados, y el plugin ni siquiera está versionado. El contrato dice que la
# ficha sirve a una audiencia-modelo; una promesa que depende de un plugin no la cumple (D-11).

def _paper(stem, *, stars=("Estrella Test",), methods=None, relevance="high", year="2020"):
    mk_note(cfg.PAPERS, stem, {"tags": ["paper"], "bibcode": stem, "year": year,
                               "stars": list(stars), "relevance": relevance,
                               **({"methods": methods} if methods else {})}, "")


def test_tabla_refleja_los_cuatro_estados(toy_vault):
    """Patrón Censo: se comparan STEMS, no conteos — dos listas del mismo largo pueden no ser los
    mismos papers (la lección de #70)."""
    _paper("2020sinA...1..1A")                                   # sin extraer
    _paper("2020extB...1..1B", methods=["gp"])                   # extraído, no sintetizado
    _paper("2020sinC...1..1C", methods=["gp"])                   # extraído y sintetizado
    _paper("2020lowD...1..1D", relevance="low")                  # fuera del filtro
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    dest.write_text(dest.read_text(encoding="utf-8").replace(
        "## Huecos", "Síntesis que cita [[2020sinC...1..1C]].\n\n## Huecos"), encoding="utf-8")
    filas = {r["stem"]: r["estado"] for r in mn.papers_universe("test_star", "star")}
    assert filas == {"2020sinA...1..1A": "sin extraer",
                     "2020extB...1..1B": "extraído, no sintetizado",
                     "2020sinC...1..1C": "sintetizado",
                     "2020lowD...1..1D": "fuera del filtro"}


def test_conteo_del_encabezado_es_el_de_la_tabla(toy_vault):
    """Adversario directo del "155 arriba de un resumen de 8": el encabezado no puede prometer un
    número que la tabla de abajo no sostiene."""
    for i, stem in enumerate(["2020aaa...1..1A", "2020bbb...1..1B", "2020ccc...1..1C"]):
        _paper(stem)
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    mn.stamp_papers_table("test_star", dest)
    texto = dest.read_text(encoding="utf-8")
    # @inv INV-81
    encabezado = [l for l in texto.splitlines() if l.startswith("## Papers")][0]
    filas = [l for l in texto.splitlines() if l.startswith("| [[20")]
    assert f"({len(filas)} ·" in encabezado


def test_papers_table_no_depende_del_plugin(toy_vault):
    """D-11: la tabla estampada REEMPLAZA el bloque ```dataview```. Un agente que abre el `.md`
    tiene que ver los papers, no el código de una query que nunca va a correr.  @inv INV-35"""
    _paper("2020aaa...1..1A")
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    mn.stamp_papers_table("test_star", dest)
    texto = dest.read_text(encoding="utf-8")
    seccion = texto.split("## Papers", 1)[1].split("\n## ", 1)[0]
    assert "```dataview" not in seccion
    assert "2020aaa...1..1A" in seccion


def test_origen_manual_gana_al_de_lente(toy_vault):
    """#68: `extra_core` es override del clasificador — el juicio del usuario pisa a la lente."""
    _paper("2020aaa...1..1A")
    write_yaml(cfg.STARS_YAML, {"Estrella Test": {
        "slug": "test_star", "simbad": "tst Star", "ads_object": "Test Star", "aliases": [],
        "extra_core": [{"bibcode": "2020aaa...1..1A", "via": "triage", "motivo": "árbitro"}]}})
    fila = mn.papers_universe("test_star", "star")[0]
    assert fila["origen"] == "manual" and fila["via"] == "triage"


def test_stamp_papers_table_idempotente_byte_a_byte(toy_vault):
    _paper("2020aaa...1..1A")
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    mn.stamp_papers_table("test_star", dest)
    antes = dest.read_bytes()
    assert mn.stamp_papers_table("test_star", dest) is False
    assert dest.read_bytes() == antes


def test_stamp_papers_table_no_toca_la_prosa(toy_vault):
    _paper("2020aaa...1..1A")
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    dest.write_text(dest.read_text(encoding="utf-8").replace(
        "## Huecos", "PROSA LLM QUE NO SE TOCA\n\n## Huecos"), encoding="utf-8")
    mn.stamp_papers_table("test_star", dest)
    assert "PROSA LLM QUE NO SE TOCA" in dest.read_text(encoding="utf-8")


def test_rollup_de_concepto_es_union_y_declara_llave(toy_vault):
    # @inv INV-35
    """D-24: el roll-up de un concepto une `methods` y `thesis_links` — en la instancia real esas
    dos llaves viven en papers distintos, así que quedarse con una sola pierde la mitad."""
    seed_topic()
    mk_note(cfg.PAPERS, "2020metA...1..1A",
            {"tags": ["paper"], "bibcode": "2020metA...1..1A", "methods": ["gaussian-processes"]}, "")
    mk_note(cfg.PAPERS, "2020thlB...1..1B",
            {"tags": ["paper"], "bibcode": "2020thlB...1..1B",
             "thesis_links": ["gaussian-processes"]}, "")
    mk_note(cfg.PAPERS, "2020ambC...1..1C",
            {"tags": ["paper"], "bibcode": "2020ambC...1..1C", "methods": ["gaussian-processes"],
             "thesis_links": ["gaussian-processes"]}, "")
    filas = {r["stem"]: r["entro_por"] for r in mn.concept_rollup_rows("gp")}
    assert filas == {"2020metA...1..1A": "methods", "2020thlB...1..1B": "thesis_links",
                     "2020ambC...1..1C": "ambos"}


def test_el_universo_y_el_rollup_de_un_tema_coinciden_con_OTRA_GRAFIA(toy_vault):
    """#347 — `_papers_del_sujeto` PROMETÍA en su comentario delegar en `concept_rollup_rows`
    «porque dos predicados de pertenencia distintos para el mismo tema es cómo la tabla y el roll-up
    terminan discrepando», y no delegaba: comparaba `methods` por **string exacto** mientras el
    roll-up usa `cfg.method_matches` (clave normalizada, #243).

    O sea el defecto que #243 arregló, vivo en el camino hermano, y con un comentario afirmando lo
    contrario. Importa doble desde #338: el detector de tabla desactualizada compara el `## Papers`
    estilo ficha de un concepto contra ESE universo, así que heredaba la subdeclaración.

    El caso simétrico —`wPCA`, que NO es el mismo método (`method_key` los separa)— va en el mismo
    test: sin él, un predicado que devolviera siempre `True` pasaría igual.  @inv INV-35"""
    seed_topic(slug="pca", area="methods", concept="pca")
    mk_note(cfg.PAPERS, "2020mayu...1..1M",
            {"tags": ["paper"], "bibcode": "2020mayu...1..1M", "methods": ["PCA"]}, "")
    mk_note(cfg.PAPERS, "2020thlN...1..1N",
            {"tags": ["paper"], "bibcode": "2020thlN...1..1N", "thesis_links": ["Pca"]}, "")
    mk_note(cfg.PAPERS, "2020otrO...1..1O",
            {"tags": ["paper"], "bibcode": "2020otrO...1..1O", "methods": ["wPCA"]}, "")
    universo = {r["stem"] for r in mn.papers_universe("pca", "theme")}
    rollup = {r["stem"] for r in mn.concept_rollup_rows("pca")}
    assert universo == rollup == {"2020mayu...1..1M", "2020thlN...1..1N"}


def test_la_tabla_estampada_no_se_cuenta_a_si_misma(toy_vault):
    """Bug medido al cablear el estampado: la tabla de `## Papers` lleva un `[[bibcode]]` por fila,
    así que apenas se estampa TODO paper aparecía como "sintetizado". Un artefacto que se mide a sí
    mismo siempre da el resultado que su propia existencia produce — mismo lazo que el bloque de
    verificación en `lib_blocks`."""
    _paper("2020extB...1..1B", methods=["gp"])
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    assert "[[2020extB...1..1B]]" in dest.read_text(encoding="utf-8")   # la fila está
    assert mn.papers_universe("test_star", "star")[0]["estado"] == "extraído, no sintetizado"


# ── issue 3.2 · D-12: las TRES fechas de una nota, distinguibles (INV-82) ───────────────────────

def _fechas(dest):
    linea = [l for l in dest.read_text(encoding="utf-8").splitlines()
             if l.startswith("> _Estado")][0]
    return linea


def test_refrescar_sin_reverificar_mueve_una_sola_fecha(toy_vault):
    """El experimento del contrato (INV-82): las tres fechas —búsqueda, síntesis, verificación—
    pueden divergir **sin que ninguna mienta**. Con una sola fecha por nota, refrescar el corpus
    hacía parecer re-verificado lo que nadie volvió a chequear.  @inv INV-82"""
    _paper("2020aaa...1..1A")
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    dest.write_text(dest.read_text(encoding="utf-8") +
                    "\n## Verificación de citas (2026-01-05)\n\n"
                    "| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |\n"
                    "|---|---|---|---|---|---|\n", encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "n_total": 1, "n_core": 1})
    mn.stamp_estado("test_star", dest)
    antes = _fechas(dest)
    assert "2026-01-01" in antes and "2026-01-05" in antes

    cfg.save_busqueda("test_star", {"fecha": "2026-03-01", "n_total": 2, "n_core": 2})
    mn.stamp_estado("test_star", dest)
    despues = _fechas(dest)
    assert "2026-03-01" in despues                       # búsqueda: se movió
    assert "2026-01-05" in despues                       # verificación: NO se movió
    assert "2026-01-01" not in despues


def test_estado_congelado_si_nada_cambio(toy_vault):
    """D-54 transversal: un stamper naive re-fecha en cada corrida y ensucia el diff. Si nada
    sustantivo cambió, la nota queda byte-igual."""
    _paper("2020aaa...1..1A")
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "n_total": 1, "n_core": 1})
    mn.stamp_estado("test_star", dest)
    antes = dest.read_bytes()
    assert mn.stamp_estado("test_star", dest) is False
    assert dest.read_bytes() == antes


def test_estado_declara_la_salvedad_por_par(toy_vault):
    """La fecha de verificación es de la ÚLTIMA pasada; la vigencia real es por par y la dicen las
    anclas (D-4). Sin la salvedad, la fecha se lee como "todo verificado a esta fecha"."""
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    dest.write_text(dest.read_text(encoding="utf-8") +
                    "\n## Verificación de citas (2026-01-05)\n", encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "n_total": 1})
    mn.stamp_estado("test_star", dest)
    assert "por par" in _fechas(dest)


def test_estado_sin_ancla_no_inventa_cabecera(toy_vault):
    fuera = cfg.STARS / "fuera.md"
    fuera.write_text("---\nname: x\n---\n# x\n\n> cabecera propia\n", encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "n_total": 1})
    assert mn.stamp_estado("test_star", fuera) is False


# ── Tanda 4 · la ficha dice de dónde salieron sus valores canónicos (pedido del usuario) ─────────

def test_cabecera_declara_la_procedencia_del_ground_truth(toy_vault):
    """Un lector que abre la ficha ve valores en el frontmatter (`teff_K: 5344`) sin nada que diga
    de dónde salieron. La procedencia estaba en la doc del framework, no en el artefacto — y el
    artefacto es lo que viaja. Va ARRIBA, en el blockquote de cabecera, donde ya vive el disclaimer
    de capa-LLM: es lo primero que se lee y no se pierde al scrollear."""
    (cfg.GROUND_TRUTH / "test_star.json").write_text(json.dumps({
        "slug": "test_star", "consultado": "2026-08-24",
        "host": {"teff_K": 5344.0, "spectral_type": "K0V",
                 "_autoridad": {"teff_K": "nea", "spectral_type": "simbad"}},
        "planets": []}), encoding="utf-8")
    mn.write_star_note("test_star", force=True)
    linea = [l for l in (cfg.STARS / "test_star.md").read_text(encoding="utf-8").splitlines()
             if l.startswith("> _Ground-truth")][0]
    assert "SIMBAD" in linea and "spectral_type" in linea
    assert "NASA Exoplanet Archive" in linea and "teff_K" in linea
    assert "2026-08-24" in linea                       # cuándo se consultó
    assert "null" in linea                             # la regla del espejo (#70)
    assert "ground_truth/test_star.json" in linea      # dónde está el detalle


def test_procedencia_va_antes_del_generador(toy_vault):
    """Dentro del blockquote de cabecera, no suelta al final del archivo."""
    (cfg.GROUND_TRUTH / "test_star.json").write_text(json.dumps({
        "slug": "test_star", "host": {"teff_K": 5344.0, "_autoridad": {"teff_K": "nea"}},
        "planets": []}), encoding="utf-8")
    mn.write_star_note("test_star", force=True)
    out = (cfg.STARS / "test_star.md").read_text(encoding="utf-8")
    assert out.index("_Ground-truth") < out.index("_Generado con Almagesto")


def test_procedencia_sin_ground_truth_no_inventa(toy_vault):
    mn.write_star_note("test_star", force=True)
    assert "_Ground-truth" not in (cfg.STARS / "test_star.md").read_text(encoding="utf-8")


def test_procedencia_idempotente(toy_vault):
    (cfg.GROUND_TRUTH / "test_star.json").write_text(json.dumps({
        "slug": "test_star", "host": {"teff_K": 5344.0, "_autoridad": {"teff_K": "nea"}},
        "planets": []}), encoding="utf-8")
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    antes = dest.read_bytes()
    assert mn.stamp_ground_truth_line("test_star", dest) is False
    assert dest.read_bytes() == antes


def test_procedencia_distingue_sin_dato_de_no_preguntado(toy_vault):
    """En el frontmatter, "la autoridad contestó y no tiene el dato" y "nadie preguntó" se ven
    idénticos: `null` en los dos casos. La cabecera los separa — es lo que dice si vale la pena
    buscar ese valor en la literatura o no."""
    (cfg.GROUND_TRUTH / "test_star.json").write_text(json.dumps({
        "slug": "test_star", "consultado": "2026-08-24",
        "host": {"teff_K": 5344.0, "st_rotp_days": None, "spectral_type": None,
                 "_autoridad": {"teff_K": "nea"}},
        "planets": []}), encoding="utf-8")
    mn.write_star_note("test_star", force=True)
    linea = [l for l in (cfg.STARS / "test_star.md").read_text(encoding="utf-8").splitlines()
             if l.startswith("> _Ground-truth")][0]
    assert "sin dato: `P_rot_days`, `spectral_type`" in linea
    assert "`st_rotp_days`" not in linea      # se nombra como lo ve el lector en la ficha


def test_la_cabecera_marca_el_campo_que_la_ficha_no_publica(toy_vault):
    """#272 — la cabecera prometía autoridad NEA sobre campos que el frontmatter **no tiene dónde
    mostrar** (`Vmag`, `ra_deg`, `dec_deg`), y el consumidor que baja a buscarlos no los encuentra.
    La línea existe justamente para que el artefacto viaje solo."""
    (cfg.GROUND_TRUTH / "test_star.json").write_text(json.dumps({
        "slug": "test_star", "consultado": "2026-08-30",
        "host": {"teff_K": 5344.0, "Vmag": 7.17, "mass_msun": 0.77,
                 "_autoridad": {"teff_K": "nea", "Vmag": "nea", "mass_msun": "nea"}},
        "planets": []}), encoding="utf-8")
    mn.write_star_note("test_star", force=True)
    linea = [l for l in (cfg.STARS / "test_star.md").read_text(encoding="utf-8").splitlines()
             if l.startswith("> _Ground-truth")][0]
    assert "`Vmag` (sólo en el JSON)" in linea, linea
    assert "`teff_K` (sólo en el JSON)" not in linea, "teff_K SÍ está en el frontmatter"
    assert "`mass_msun` (sólo en el JSON)" not in linea, "#272: mass_msun entró al frontmatter"


def test_la_masa_estelar_se_espeja_al_crear_la_ficha(toy_vault):
    """#272 — espejo puro (#70): lo copia el script del JSON, `null` si NEA calla."""
    (cfg.GROUND_TRUTH / "test_star.json").write_text(json.dumps({
        "slug": "test_star", "host": {"mass_msun": 0.77, "_autoridad": {"mass_msun": "nea"}},
        "planets": []}), encoding="utf-8")
    mn.write_star_note("test_star", force=True)
    fm = cfg.split_fm((cfg.STARS / "test_star.md").read_text(encoding="utf-8"))
    assert fm["mass_msun"] == 0.77


# ── Tanda 5 · D-19: renombre preprint → publicado ───────────────────────────────────────────────

def test_ciclo_preprint_publicado(toy_vault):
    """El experimento del contrato: una nota de preprint citada desde una ficha pasa a ser el
    publicado, sin dejar wikilinks rotos ni perder el alias.  @inv INV-84"""
    _paper("2020preX...1..1X")
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "test_star" / "2020preX...1..1X.txt").write_text("texto", encoding="utf-8")
    (cfg.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "test_star" / "2020preX...1..1X.pdf").write_bytes(b"%PDF-1.4")
    mn.write_star_note("test_star", force=True)
    ficha = cfg.STARS / "test_star.md"
    ficha.write_text(ficha.read_text(encoding="utf-8").replace(
        "## Huecos", "El período es 34 d [[2020preX...1..1X]].\n\n## Huecos"), encoding="utf-8")

    mn.rename_paper("2020preX...1..1X", "2021pubY...1..1Y")

    assert not (cfg.PAPERS / "2020preX...1..1X.md").exists()
    nueva = cfg.PAPERS / "2021pubY...1..1Y.md"
    fm = read_fm(nueva)
    assert fm["bibcode"] == "2021pubY...1..1Y"
    assert [v["bibcode"] for v in fm["versions"]] == ["2020preX...1..1X"]
    assert "[[2021pubY...1..1Y]]" in ficha.read_text(encoding="utf-8")
    assert (cfg.FULLTEXT / "test_star" / "2021pubY...1..1Y.txt").exists()
    assert (cfg.PDFS / "test_star" / "2021pubY...1..1Y.pdf").exists()


def test_renombre_no_toca_menciones_en_prosa(toy_vault):
    """Adversario de un replace ciego: un bibcode citado TEXTUALMENTE —dentro de una cita
    transcripta del paper, p. ej.— no es un link a la nota y no se reescribe."""
    _paper("2020preX...1..1X")
    mn.write_star_note("test_star", force=True)
    ficha = cfg.STARS / "test_star.md"
    ficha.write_text(ficha.read_text(encoding="utf-8").replace(
        "## Huecos",
        'Link [[2020preX...1..1X]] y mención textual "ver 2020preX...1..1X en la tabla 3".\n\n## Huecos'),
        encoding="utf-8")
    mn.rename_paper("2020preX...1..1X", "2021pubY...1..1Y")
    out = ficha.read_text(encoding="utf-8")
    assert "[[2021pubY...1..1Y]]" in out
    assert '"ver 2020preX...1..1X en la tabla 3"' in out


def test_renombre_reescribe_los_wikilinks_CON_ANCLA(toy_vault):
    """AUD-168 / INV-84 — faltaban las dos formas de ancla de Obsidian (`#` y `^`).

    Son justo lo que una nota larga usa para apuntar a una sección o a un bloque concreto de un
    paper. El renombre las dejaba apuntando al bibcode viejo, o sea rotas — y el detector de
    wikilinks rotos del lint sí las lee, así que aparecían como hallazgo **después** del renombre,
    sobre un link que el renombrador tenía que haber arreglado. El ancla sobrevive intacta."""
    _paper("2020preX...1..1X")
    mn.write_star_note("test_star", force=True)
    ficha = cfg.STARS / "test_star.md"
    ficha.write_text(ficha.read_text(encoding="utf-8").replace(
        "## Huecos",
        "Ver [[2020preX...1..1X#Vista — Estrella Test]] y [[2020preX...1..1X^tabla3]], "
        "y [[2020preX...1..1X|el preprint]].\n\n## Huecos"), encoding="utf-8")
    mn.rename_paper("2020preX...1..1X", "2021pubY...1..1Y")
    out = ficha.read_text(encoding="utf-8")
    assert "[[2021pubY...1..1Y#Vista — Estrella Test]]" in out
    assert "[[2021pubY...1..1Y^tabla3]]" in out
    assert "[[2021pubY...1..1Y|el preprint]]" in out
    assert "2020preX" not in out


def test_crear_segunda_nota_mismo_trabajo_rehusa(toy_vault, capsys):
    """Se evita el duplicado desde el vamos: el conteo doble y el falso positivo de #75 nacen acá."""
    mk_note(cfg.PAPERS, "2020preX...1..1X",
            {"tags": ["paper"], "bibcode": "2020preX...1..1X", "arxiv_id": "2001.12345"}, "")
    ads_json([rec("2021pubY...1..1Y", arxiv="2001.12345")])
    mn.write_paper_notes("test_star", include_all=False, force=False)
    assert not (cfg.PAPERS / "2021pubY...1..1Y.md").exists()
    assert "2001.12345" in capsys.readouterr().out


# ── Tanda 8 · issue 8.1 (D-17): las keywords de ADS llegan al frontmatter ──────────────────────

def test_keywords_llegan_al_frontmatter(toy_vault):
    """D-17. ADS ya devuelve `keyword` y `query_ads` lo persiste en `ads.json` — la nota lo tiraba.
    Sin ellas, el diff de lente **offline** (issue 8.2) no puede re-clasificar desde las notas: la
    lente matchea sobre título + abstract + **keywords**, y re-clasificar sin la tercera daría un
    veredicto distinto del que dio el ingest, o sea un diff inventado."""
    ads_json([dict(rec("2020kwA....1..1A"),
                   keyword=["stars: activity", "techniques: radial velocities"])])
    mn.write_paper_notes("test_star", include_all=False, force=False)
    fm = read_fm(toy_vault.PAPERS / "2020kwA....1..1A.md")
    assert fm["keywords"] == ["stars: activity", "techniques: radial velocities"]


def test_keywords_no_pisa_la_extraccion(toy_vault):
    """Add-only, como todo lo que `make_notes` mergea sobre una nota que ya existe."""
    ads_json([dict(rec("2020kwB....1..1B"), keyword=["una"])])
    mn.write_paper_notes("test_star", include_all=False, force=False)
    p = toy_vault.PAPERS / "2020kwB....1..1B.md"
    p.write_text(p.read_text(encoding="utf-8").replace("keywords:\n- una", "keywords:\n- editada"),
                 encoding="utf-8")
    mn.write_paper_notes("test_star", include_all=False, force=False)
    assert read_fm(p)["keywords"] == ["editada"]


def test_migrate_bearing_saca_el_campo_y_es_idempotente(toy_vault):
    # @inv INV-13
    """Migrador de un solo uso de D-21. Borrado puro y sin pérdida recuperable: el dato viejo era
    **un** valor de postura para N tesis, o sea que ya estaba mal por construcción. Quirúrgico: no
    toca la extracción LLM ni el cuerpo."""
    mk_note(toy_vault.PAPERS, "2020Bear",
            {"tags": ["paper"], "bibcode": "2020Bear", "thesis_links": ["hip"],
             "bearing": "supports", "methods": ["ICA"]},
            "# 2020Bear\n\nExtracción LLM que no se toca.\n")
    assert mn.migrate_all_bearing() == 1
    p = toy_vault.PAPERS / "2020Bear.md"
    fm = read_fm(p)
    assert "bearing" not in fm
    assert fm["thesis_links"] == ["hip"] and fm["methods"] == ["ICA"], "no toca el resto"
    assert "Extracción LLM que no se toca." in p.read_text(encoding="utf-8")
    antes = p.read_bytes()
    assert mn.migrate_all_bearing() == 0, "segunda pasada: nada que hacer"
    assert p.read_bytes() == antes, "y no reescribe"


# ── D-17 · backfill de `keywords` (--restamp-keywords) ──────────────────────

def _ads_json(slug, records):
    d = cfg.ROOT / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"slug": slug, "records": records}), encoding="utf-8")


def test_restamp_keywords_estampa_la_nota_que_nacio_sin_ellas(toy_vault):
    """La nota pre-D-17 no tiene la clave. `merge_frontmatter_list` devuelve False ahí a propósito
    (no inventa posiciones), así que el backfill INSERTA — anclado en `facets:`, su vecino."""
    _ads_json("test_star", [{"bibcode": "2020A", "keyword": ["stellar activity", "techniques: RV"]}])
    (cfg.PAPERS).mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020A.md").write_text(
        "---\nbibcode: 2020A\ntitle: T\nfacets: [rv]\nmethods: []\ntags: [paper]\n---\n"
        "# T\n\n## Extracción\nno se toca\n", encoding="utf-8")
    assert mn.restamp_keywords() == 0
    txt = (cfg.PAPERS / "2020A.md").read_text(encoding="utf-8")
    assert cfg.split_fm(txt)["keywords"] == ["stellar activity", "techniques: RV"]
    assert "no se toca" in txt, "el cuerpo (extracción LLM) queda intacto"


def test_restamp_keywords_es_add_only(toy_vault):
    """Add-only estricto: una nota con `keywords` poblado no se toca, aunque el registro diga otra
    cosa (mismo criterio que el retro-linkeo: nunca pisar lo que ya está)."""
    _ads_json("test_star", [{"bibcode": "2020A", "keyword": ["del registro"]}])
    (cfg.PAPERS).mkdir(parents=True, exist_ok=True)
    p = cfg.PAPERS / "2020A.md"
    p.write_text("---\nbibcode: 2020A\nfacets: [rv]\nkeywords: [ya estaba]\ntags: [paper]\n"
                 "methods: []\n---\n# T\n", encoding="utf-8")
    antes = p.read_text(encoding="utf-8")
    mn.restamp_keywords()
    assert p.read_text(encoding="utf-8") == antes


def test_restamp_keywords_sin_build_declara_en_vez_de_contar_cero(toy_vault, capsys):
    """`build/` es scratch gitignored: sin él no hay de dónde sacarlas. Un "0 estampadas" pelado se
    leería como "no hacía falta"; hay que decir que no había de dónde (D-43)."""
    (cfg.PAPERS).mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020A.md").write_text(
        "---\nbibcode: 2020A\nfacets: [rv]\nmethods: []\ntags: [paper]\n---\n# T\n", encoding="utf-8")
    mn.restamp_keywords()
    out = capsys.readouterr().out
    assert "1 nota(s) sin keywords y sin registro" in out and "no había de dónde" in out


def test_restamp_keywords_es_idempotente(toy_vault):
    _ads_json("test_star", [{"bibcode": "2020A", "keyword": ["k1"]}])
    (cfg.PAPERS).mkdir(parents=True, exist_ok=True)
    p = cfg.PAPERS / "2020A.md"
    p.write_text("---\nbibcode: 2020A\nfacets: [rv]\nmethods: []\ntags: [paper]\n---\n# T\n",
                 encoding="utf-8")
    mn.restamp_keywords()
    primera = p.read_text(encoding="utf-8")
    mn.restamp_keywords()
    assert p.read_text(encoding="utf-8") == primera


def test_rename_paper_corre_sin_slug(toy_vault, monkeypatch, capsys):
    """P0 de auditoría: el guard `if not args.slug` corría ANTES del despacho de `--rename-paper`,
    así que el comando **que la doc publica** (`CLAUDE.md`, el stdout de make_notes, del lint y de
    sweep_external lo imprimen sin slug) moría con exit 2. Un comando publicado que no corre es peor
    que uno ausente: el usuario lo copia y el ciclo preprint→publicado queda a medias."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020preX.md").write_text(
        "---\nbibcode: 2020preX\ntitle: T\narxiv_id: 2001.00001\nstars: [Estrella Test]\n"
        "methods: []\ntags: [paper]\n---\n# T\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["make_notes.py", "--rename-paper", "2020preX", "2021pubY"])
    assert mn.main() == 0
    nueva = cfg.PAPERS / "2021pubY.md"
    assert nueva.exists() and not (cfg.PAPERS / "2020preX.md").exists()
    fm = cfg.split_fm(nueva.read_text(encoding="utf-8"))
    assert fm["bibcode"] == "2021pubY" and "2020preX" in str(fm["versions"])


def test_la_nota_declara_su_version(toy_vault):
    """INV-62, la mitad que faltaba: **cada nota** declara con qué versión se generó. La marca vivía
    sólo en el test de los User-Agents de los fetchers, que mide la otra mitad ("única fuente de
    verdad") y no toca ninguna nota.  @inv INV-62"""
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text(json.dumps({"slug": "test_star", "records": [
        {"bibcode": "2020A", "relevant": True, "title": "t", "authors": ["A"], "year": 2020,
         "keyword": [], "facets": ["rv"]}]}), encoding="utf-8")
    mn.write_paper_notes("test_star", False, False)
    fm = cfg.split_fm((cfg.PAPERS / "2020A.md").read_text(encoding="utf-8"))
    assert fm["generator"] == f"Almagesto v{cfg.ALMAGESTO_VERSION}"


def test_restamp_headers_no_reetiqueta_la_nota(toy_vault):
    """La otra cara de INV-62: una **cirugía posterior** no puede reetiquetar la nota con la versión
    del framework que corre hoy — la nota se generó con otra, y decir lo contrario borra la
    provenance. `--restamp-headers` lee la versión del `generator` del frontmatter.  @inv INV-62"""
    cfg.STARS.mkdir(parents=True, exist_ok=True)
    p = cfg.STARS / "vieja.md"
    p.write_text("---\nname: Vieja\nslug: vieja\ntags: [star]\ngenerator: Almagesto v1.11.0\n---\n"
                 "# Vieja\n\nSíntesis LLM cara.\n", encoding="utf-8")
    mn.restamp_headers()
    txt = p.read_text(encoding="utf-8")
    assert "Almagesto v1.11.0" in txt, "la cabecera se estampa con la versión del frontmatter"
    assert f"Almagesto v{cfg.ALMAGESTO_VERSION}" not in txt.split("# Vieja")[0].replace(
        "generator: Almagesto v1.11.0", ""), "no se reetiqueta con la versión de hoy"
    assert "Síntesis LLM cara." in txt


def test_concept_dest_resuelve_area_y_nombre(toy_vault):
    """Gate de mutación: `_concept_dest` sobrevivía a que le vaciaran el cuerpo. Es el que decide
    **dónde** cae la nota de un concepto —área y nombre salen de `themes.yaml`, no del slug—, así
    que un `return None` mudo mandaba la nota a otro lado (o a ningún lado) sin que nada fallara."""
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "GP", "area": "methods",
                                        "concept": "procesos-gaussianos", "query": "q"}})
    assert mn._concept_dest("gp") == cfg.CONCEPTS / "methods" / "procesos-gaussianos.md"
    assert mn._concept_dest("no_existe") is None, "tema desconocido: None, no una ruta inventada"
    write_yaml(cfg.THEMES_YAML, {"pelado": {"title": "P", "query": "q"}})
    assert mn._concept_dest("pelado") == cfg.CONCEPTS / "" / "pelado.md", \
        "sin `concept` declarado cae al slug (y sin `area`, a la raíz de concepts/)"


# ── INV-64 · los dos migradores que faltaban ────────────────────────────────

def test_migrate_facets_renombra_y_es_idempotente(toy_vault):
    """R-5 entregó el detector bloqueante y **no** el migrador: el lint mandaba a renombrar a mano,
    nota por nota (medido en una instancia real: 908 de 908 la traían).  @inv INV-64"""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    bloque = cfg.PAPERS / "2020Bloque.md"
    bloque.write_text("---\nbibcode: 2020Bloque\ntopics:\n  - rv\n  - activity\nmethods: []\n"
                      "tags: [paper]\n---\n# T\n\n## Extracción\nno se toca\n", encoding="utf-8")
    inline = cfg.PAPERS / "2020Inline.md"
    inline.write_text("---\nbibcode: 2020Inline\ntopics: [rv]\nmethods: []\ntags: [paper]\n---\n# T\n",
                      encoding="utf-8")
    assert mn.migrate_all_facets() == 2
    fm = cfg.split_fm(bloque.read_text(encoding="utf-8"))
    assert fm["facets"] == ["rv", "activity"] and "topics" not in fm
    assert "no se toca" in bloque.read_text(encoding="utf-8")
    assert cfg.split_fm(inline.read_text(encoding="utf-8"))["facets"] == ["rv"]
    assert mn.migrate_all_facets() == 0, "idempotente"


def test_migrate_facets_no_pisa_un_facets_existente(toy_vault):
    """Si la nota ya tiene el campo vigente, el `topics:` residual se **borra**: el vigente manda."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    p = cfg.PAPERS / "2020Dos.md"
    p.write_text("---\nbibcode: 2020Dos\nfacets: [rv]\ntopics: [viejo]\nmethods: []\n"
                 "tags: [paper]\n---\n# T\n", encoding="utf-8")
    mn.migrate_all_facets()
    fm = cfg.split_fm(p.read_text(encoding="utf-8"))
    assert fm["facets"] == ["rv"] and "topics" not in fm


def test_migrate_registros_pliega_sin_perder_la_corrida(toy_vault):
    """D-28 tenía detector y no migrador: el lint mandaba a "re-correr la cadena", que cuesta una
    pasada de red **y pierde la corrida vieja** — en el único artefacto no regenerable.  @inv INV-64"""
    cfg.save_registro("test_star", {"slug": "test_star",
                                    "busqueda": {"fecha": "2026-01-01", "query": "q", "n_total": 40},
                                    "decisiones": {"2020X": {"decision": "descartado",
                                                             "motivo": "ruido", "fecha": "2026-01-01"}}})
    assert mn.migrate_all_registros() == 1
    reg = cfg.load_registro("test_star")
    assert reg.get("busqueda") is None
    assert len(reg["busquedas"]) == 1 and reg["busquedas"][0]["n_total"] == 40
    assert "pre-D-28" in reg["busquedas"][0]["schema"]
    assert reg["decisiones"]["2020X"]["motivo"] == "ruido", "el juicio de curación no se toca"
    assert mn.migrate_all_registros() == 0, "idempotente"


# ── INV-81 / D-11 · los otros dos roll-ups de la ficha, materializados ──────

def test_planetas_se_estampa_no_es_dataview(toy_vault):
    """D-11 se había cumplido **sólo** para `## Papers`. `## Planetas` era ```dataviewjs``` — el
    peor de los tres, porque sus cinco campos son ground-truth de NEA, la capa que el contrato
    vende como auditable, y un agente que abre el `.md` veía el CÓDIGO de la query.  @inv INV-81"""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps(GT), encoding="utf-8")
    cfg.STARS.mkdir(parents=True, exist_ok=True)
    mn.write_star_note("test_star", False)
    txt = (cfg.STARS / "test_star.md").read_text(encoding="utf-8")
    assert "dataviewjs" not in txt and "dv.table" not in txt
    assert "| Letra | P (d) | K (m/s) | e | m·sini (M⊕) | Estado |" in txt


def test_planetas_muestra_null_explicito(toy_vault):
    """NEA calla seguido en `K_ms`/`e` y el contrato dice que ese null es el estado CORRECTO. Una
    celda en blanco se leería como «falta el dato»."""
    t = mn.planetas_table({"planets": [{"letter": "b", "P_days": 3.1, "K_ms": None, "e": None,
                                        "mass_earth": 2.0, "status": "confirmed"}]})
    assert "| b | 3.1 | null | null | 2.0 | confirmed |" in t


def test_planetas_sin_planetas_lo_dice(toy_vault):
    t = mn.planetas_table({"planets": []})
    assert "(0)" in t and "disputes" in t, "un vacío tiene que explicar dónde va una señal discutida"


def test_metodos_se_estampa_con_el_recorte_correcto(toy_vault):
    """Los métodos DE los papers de la estrella, no todo paper de la bóveda que use el método — el
    mismo recorte que documenta `CLAUDE.md` para el equivalente determinista.  @inv INV-81"""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020Mio.md").write_text(
        "---\nbibcode: 2020Mio\nstars: [Estrella Test]\nmethods: [gp, periodograma]\nyear: 2020\n"
        "tags: [paper]\n---\n# T\n", encoding="utf-8")
    (cfg.PAPERS / "2020Ajeno.md").write_text(
        "---\nbibcode: 2020Ajeno\nstars: [Otra]\nmethods: [gp]\nyear: 2020\ntags: [paper]\n---\n# T\n",
        encoding="utf-8")
    filas = mn.metodos_rows("Estrella Test")
    assert [f[1] for f in filas] == ["2020Mio", "2020Mio"], filas
    t = mn.metodos_table(filas)
    assert "2 método(s) · 2 aplicación(es)" in t and "gp" in t and "2020Ajeno" not in t


def test_metodos_solo_linkea_el_que_tiene_nota(toy_vault):
    """El roll-up estampa `[[link]]` **sii** la nota del método existe; si no, código.

    Sin esto, seguir `ingest-star` al pie de la letra fabricaba wikilinks rotos —bloqueantes— que no
    se podían cerrar dentro de la operación que los creaba: `methods` lo puebla la extracción
    (paso 3) y las notas de `concepts/methods/` las crea `ingest-theme`, que es otra operación.
    Medido en el clean-room del 2026-08-25: 106 sobre dos estrellas. Hasta 1.35.0 no se veía porque
    el roll-up era un bloque ```dataview``` y el detector, que lee texto, no lo miraba.

    Se fija por los DOS lados: un método CON nota tiene que seguir linkeando (si no, el roll-up
    dejaría de ser navegable y el arreglo sería peor que el defecto)."""
    (cfg.CONCEPTS / "methods").mkdir(parents=True, exist_ok=True)
    FM_GP = "---\nname: gp\n---\n# GP\n"
    (cfg.CONCEPTS / "methods" / "gp.md").write_text(FM_GP, encoding="utf-8")
    filas = [("gp", "2020Mio", "2020"), ("sin-nota", "2020Mio", "2020")]
    t = mn.metodos_table(filas)
    # #273 — la fila es por MÉTODO (agrupada), así que la celda ya no es sólo el link.
    assert "| [[gp]] |" in t, f"el método CON nota tiene que linkear:\n{t}"
    assert "| `sin-nota` |" in t and "[[sin-nota]]" not in t, \
        f"el método SIN nota no puede estamparse como wikilink:\n{t}"


def test_stamp_star_rollups_es_idempotente_y_no_toca_la_prosa(toy_vault):
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps(GT), encoding="utf-8")
    cfg.STARS.mkdir(parents=True, exist_ok=True)
    mn.write_star_note("test_star", False)
    dest = cfg.STARS / "test_star.md"
    dest.write_text(dest.read_text(encoding="utf-8").replace(
        "## Huecos", "## Resumen\n\nSíntesis LLM cara e irrepetible.\n\n## Huecos"), encoding="utf-8")
    primera = dest.read_text(encoding="utf-8")
    assert mn.stamp_star_rollups("test_star", dest) is False, "sin cambios no reescribe"
    assert dest.read_text(encoding="utf-8") == primera
    assert "Síntesis LLM cara e irrepetible." in primera


# ── INV-82 · las TRES fechas ────────────────────────────────────────────────

def test_la_cabecera_lleva_las_tres_fechas(toy_vault):
    """INV-82 prometía tres (búsqueda, síntesis, verificación) y emitía dos: la de **síntesis** no
    existía en ningún lado. El efecto es el que el invariante existe para impedir: refrescar el
    corpus movía la de búsqueda y la ficha se leía como re-sintetizada.  @inv INV-82"""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps(GT), encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-08-01", "n_found": 40, "n_core": 12})
    cfg.save_sintesis("test_star", n_papers=12)
    mn.write_star_note("test_star", False)
    dest = cfg.STARS / "test_star.md"
    dest.write_text(dest.read_text(encoding="utf-8")
                    + "\n## Verificación de citas (2026-08-03)\n\n| # |\n", encoding="utf-8")
    mn.stamp_estado("test_star", dest)
    linea = [l for l in dest.read_text(encoding="utf-8").split("\n") if l.startswith("> _Estado")][0]
    assert "búsqueda 2026-08-01" in linea
    assert "síntesis" in linea and "(12 papers)" in linea
    assert "verificación 2026-08-03" in linea


def test_refrescar_no_mueve_la_fecha_de_sintesis(toy_vault):
    """Las tres avanzan por separado y pueden divergir **sin que ninguna mienta**: un refresh mueve
    la de búsqueda y deja la de síntesis donde estaba, que es lo que hace legible que la prosa sea
    más vieja que el universo declarado.  @inv INV-82"""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps(GT), encoding="utf-8")
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "n_found": 40, "n_core": 12})
    cfg.save_sintesis("test_star", n_papers=12)
    sint_antes = cfg.load_registro("test_star")["sintesis"]["fecha"]
    mn.write_star_note("test_star", False)
    dest = cfg.STARS / "test_star.md"
    cfg.save_busqueda("test_star", {"fecha": "2026-08-24", "n_found": 60, "n_core": 20})
    mn.stamp_estado("test_star", dest)
    linea = [l for l in dest.read_text(encoding="utf-8").split("\n") if l.startswith("> _Estado")][0]
    assert "búsqueda 2026-08-24" in linea
    assert f"síntesis {sint_antes}" in linea, "el refresh no puede re-fechar la síntesis"


def test_rename_paper_reescribe_todo_vault_no_solo_wiki(toy_vault):
    """El alcance DECLARADO es `vault/` y se reescribía sólo `vault/wiki/`: un `[[bibcode]]` en
    `STATUS.md` —que vive un nivel arriba y es el archivo que se lee primero— quedaba roto."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020preX.md").write_text(
        "---\nbibcode: 2020preX\narxiv_id: 2001.1\nstars: [Estrella Test]\nmethods: []\n"
        "tags: [paper]\n---\n# T\n", encoding="utf-8")
    status = cfg.VAULT / "STATUS.md"
    status.write_text("Pendiente: revisar [[2020preX]].\n", encoding="utf-8")
    mn.rename_paper("2020preX", "2021pubY")
    assert "[[2021pubY]]" in status.read_text(encoding="utf-8")


def _paper_con_artefactos(old="2011Yang"):
    """Nota off-ADS con PDF y `.txt` en disco y los tres punteros que #356 encontró apuntando a los
    viejos: `pdf:`, `fulltext:` y el link `[📄 PDF]` del cuerpo."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "ica").mkdir(parents=True, exist_ok=True); (cfg.FULLTEXT / "ica").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "ica" / f"{old}.pdf").write_bytes(b"%PDF-1.4\n")
    (cfg.FULLTEXT / "ica" / f"{old}.txt").write_text("prosa", encoding="utf-8")
    nota = cfg.PAPERS / f"{old}.md"
    nota.write_text(f"---\nbibcode: {old}\ndoi: 10.1/x\ntags: [paper]\nthesis_links: [ica]\n"
                    f"pdf: ../../raw/pdfs/ica/{old}.pdf\nfulltext: ../../raw/fulltext/ica/{old}.txt\n"
                    f"---\n# T\n\n**Yang** (2011)\n· [[ica]] · fuente off-ADS · `{old}` · "
                    f"[📄 PDF](../../raw/pdfs/ica/{old}.pdf)\n\n> El respaldo citable es el snapshot "
                    f"`vault/raw/fulltext/ica/{old}.txt`.\n", encoding="utf-8")
    return nota


def test_rename_paper_deja_TODOS_los_punteros_apuntando_a_archivos_que_existen(toy_vault):
    """#356 — el mismo comando que movía los artefactos dejaba la nota afirmando que están donde ya
    no están: `pdf:` y `fulltext:` al viejo, el link `[📄 PDF]` y el blockquote off-ADS también. Es
    #217 al revés, y la doc prometía «re-estampa la cabecera»: re-estampaba MEDIA (el bibcode entre
    backticks). La maquinaria existía (#304, `stamp_pdf`/`stamp_fulltext`); el renombre no la
    llamaba. Es un assert, no una inspección."""
    _paper_con_artefactos()
    mn.rename_paper("2011Yang", "2011Pendse")
    nota = cfg.PAPERS / "2011Pendse.md"
    texto = nota.read_text(encoding="utf-8"); fm = cfg.split_fm(texto)
    for campo in ("pdf", "fulltext"):
        assert (nota.parent / fm[campo]).resolve().exists(), f"`{campo}` apunta a algo que no existe: {fm[campo]}"
    assert "2011Yang" not in texto.split("---", 2)[2].replace("[[2011Yang]]", ""), \
        "el cuerpo (link `[📄 PDF]` y blockquote) sigue nombrando el artefacto viejo"


def test_rename_paper_con_fix_key_NO_escribe_versions(toy_vault, capsys):
    """#355 — `--rename-paper` asumía que todo renombre es un alias D-19 y escribía `versions[]`
    incondicionalmente. Para preprint→publicado es correcto; para una CLAVE EQUIVOCADA es una
    afirmación falsa en un campo máquina-legible, y `versions[]` exime de los dos chequeos de
    identidad (#229): una clave inventada queda blindada. Decidido con el usuario: el rastro va al
    `log` (la marca de #238), no a la nota."""
    _paper_con_artefactos()
    mn.rename_paper("2011Yang", "2011Pendse", fix_key=True)
    fm = cfg.split_fm((cfg.PAPERS / "2011Pendse.md").read_text(encoding="utf-8"))
    assert not fm.get("versions"), fm.get("versions")
    assert "⚠ corregido" in capsys.readouterr().out, "imprime la entrada del log lista para pegar"


def test_rename_paper_sin_fix_key_sigue_escribiendo_el_alias(toy_vault):
    """El control: el caso D-19 no cambia."""
    _paper_con_artefactos()
    mn.rename_paper("2011Yang", "2011Pendse")
    fm = cfg.split_fm((cfg.PAPERS / "2011Pendse.md").read_text(encoding="utf-8"))
    assert [v["bibcode"] for v in fm["versions"]] == ["2011Yang"]


def test_reemplazar_el_PDF_por_otro_de_distinta_procedencia_deja_pdf_source_en_null(toy_vault, capsys):
    """#383 — #230 decide que `pdf_source` SOBREVIVE al archivo, porque describe la procedencia de
    la lectura que ocurrió, no el archivo. Son dos casos (desaparece / se mantiene) y había un
    tercero: el archivo se REEMPLAZA por otro de distinta procedencia. Ahí la lectura vieja se está
    descartando —hay que re-extraer, la paginación cambió— y el argumento de #230 no aplica: el
    valor sobrevive y ahora MIENTE. Medido: un preprint v1 (28 pp) reemplazado por el publicado
    (32 pp) quedó con `pdf_source: eprint` + `eprint_version: v1` sobre el PDF del editor — y las
    dos versiones diferían en RESULTADOS, no en redacción."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True); (cfg.PDFS / "rv").mkdir(parents=True, exist_ok=True)
    pdf = cfg.PDFS / "rv" / "2025A&A...696A.141H.pdf"; pdf.write_bytes(b"%PDF-1.4 v1\n")
    nota = cfg.PAPERS / "2025A&A...696A.141H.md"
    nota.write_text("---\nbibcode: 2025A&A...696A.141H\ntags: [paper]\npdf: null\n"
                    "pdf_source: eprint\neprint_version: v1\n---\n# F\n", encoding="utf-8")
    assert mn.stamp_pdf(nota, "2025A&A...696A.141H") is True       # primera estampa: registra el hash
    pdf.write_bytes(b"%PDF-1.4 PUBLICADO, 32 paginas\n")            # el usuario aporta el publicado
    assert mn.stamp_pdf(nota, "2025A&A...696A.141H") is True
    fm = cfg.split_fm(nota.read_text(encoding="utf-8"))
    assert fm.get("pdf_source") is None and fm.get("eprint_version") is None, fm
    out = capsys.readouterr().out
    assert "cambió de hash" in out and "re-extraer" in out


def test_el_mismo_PDF_no_toca_pdf_source(toy_vault):
    """El control de #230: sin cambio de archivo, `pdf_source` sobrevive intacto — y la segunda
    corrida es idempotente."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True); (cfg.PDFS / "rv").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "rv" / "2020x....1X.pdf").write_bytes(b"%PDF-1.4\n")
    nota = cfg.PAPERS / "2020x....1X.md"
    nota.write_text("---\nbibcode: 2020x....1X\ntags: [paper]\npdf: null\npdf_source: eprint\n"
                    "---\n# X\n", encoding="utf-8")
    mn.stamp_pdf(nota, "2020x....1X")
    assert mn.stamp_pdf(nota, "2020x....1X") is False
    assert cfg.split_fm(nota.read_text(encoding="utf-8"))["pdf_source"] == "eprint"


def test_rename_paper_usa_el_stem_saneado_en_los_wikilinks(toy_vault):
    """El archivo se crea con el stem saneado (`/` → `_`) y todos los wikilinks del repo usan el
    stem. Escribir el bibcode crudo dejaba cada link apuntando a una nota inexistente — latente,
    pero es la única razón por la que `safe_name` existe."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020preX.md").write_text(
        "---\nbibcode: 2020preX\narxiv_id: 2001.1\nstars: [Estrella Test]\nmethods: []\n"
        "tags: [paper]\n---\n# T\n", encoding="utf-8")
    (cfg.CONCEPTS / "methods").mkdir(parents=True, exist_ok=True)
    (cfg.CONCEPTS / "methods" / "gp.md").write_text(
        "---\nname: gp\ntags: [concept]\n---\n# gp\n\nVer [[2020preX]].\n", encoding="utf-8")
    nuevo = "2021ApJ/999"
    mn.rename_paper("2020preX", nuevo)
    stem = mn.safe_name(nuevo)
    assert (cfg.PAPERS / f"{stem}.md").exists()
    assert f"[[{stem}]]" in (cfg.CONCEPTS / "methods" / "gp.md").read_text(encoding="utf-8")


def test_stamp_header_no_ancla_en_un_comentario_del_frontmatter(toy_vault):
    """El `# H1` que sirve de ancla es el del CUERPO, no un comentario YAML del frontmatter.

    AUD-37: `H1_RE` corre con `re.M` sobre el texto entero, así que una nota cuyo frontmatter lleva
    un comentario (`# P_rot lo puso el usuario a mano`) matcheaba ahí y el blockquote se insertaba
    **dentro** del frontmatter → `split_fm` devuelve `{}`, que es una categoría **bloqueante** del
    lint. Lo dispara `--restamp-headers`, que es justo lo que el lint recomienda para las notas sin
    cabecera: la reparación fabricaba el daño.  @inv INV-69
    """
    dest = toy_vault.STARS / "test_star.md"
    dest.write_text(
        "---\n"
        "name: Estrella Test\n"
        "# P_rot lo puso el usuario a mano\n"
        "slug: test_star\n"
        "---\n\n"
        "# Estrella Test\n\nProsa.\n", encoding="utf-8")
    assert mn.stamp_header(dest) is True
    texto = dest.read_text(encoding="utf-8")
    assert cfg.split_fm(texto).get("name") == "Estrella Test", \
        "el frontmatter tiene que seguir parseando después de estampar"
    fm_bloque = cfg.frontmatter_span(texto)[0]
    assert ">" not in fm_bloque, "el blockquote no puede caer dentro del frontmatter"


def test_excluded_table_no_lanza_con_un_ads_json_cortado_a_media_letra(toy_vault):
    """`excluded_table` garantiza que **nunca lanza** y **siempre** devuelve un `str`.

    AUD-40: el docstring nombra el escenario exacto —«un `ads.json` truncado por un Ctrl-C a mitad
    de `query_ads`»— y explica el costo («si esto lanza, la cadena muere DESPUÉS de gastar la red»),
    pero atrapaba sólo `(OSError, json.JSONDecodeError)`. Un corte a mitad de un carácter multibyte
    da `UnicodeDecodeError`, que no es subclase de ninguna de las dos.

    ⚠ **La marca era `@inv INV-61` y estaba MAL ATRIBUIDA (#184).** INV-61 enuncia *«una fuente
    declarada que no se consigue queda pendiente con su puntero … y se surface como precondición»*:
    acá no hay fuente declarada, ni `pending`, ni puntero, ni precondición — hay un `ads.json`
    truncado y un `isinstance(..., str)`. La fila de INV-61 lo listaba como una de sus tres pruebas,
    o sea que el conteo «invariantes con test» se inflaba con una marca de conveniencia (misma
    familia que AUD-06/AUD-30, que INV-95(a) reconoce). Lo que este test mide de verdad es INV-18:
    una cirugía sobre un ancla ilegible **se reporta** —acá, devolviendo `""`— y nunca tumba la
    cadena después de haber gastado la red.  @inv INV-18
    """
    d = cfg.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    # el corte cae A MITAD de la `ñ` (2 bytes en utf-8), que es lo que produce el
    # UnicodeDecodeError; truncar después de un ASCII sólo da JSONDecodeError, ya cubierto.
    (d / "ads.json").write_bytes('{"records": [{"title": "añ'.encode("utf-8")[:-1])
    assert isinstance(mn.excluded_table("test_star"), str)


def test_una_corrida_limpia_deja_el_rollup_al_dia(toy_vault, monkeypatch):
    """Los roll-ups reflejan las notas que la MISMA corrida acaba de crear.  @inv INV-81

    `main` hacía `write_star_note` (que estampa) y DESPUÉS `write_paper_notes`, así que toda
    ingesta limpia terminaba con la ficha diciendo «ninguna nota de paper declara este sujeto
    todavía» sobre las N que sí lo declaraban — medido en un clean-room con 53 core. Correr el
    mismo comando otra vez lo arreglaba: era puro orden dentro de la corrida.

    No era silencioso (el lint lo reporta como backlog), y ése es el problema: un hallazgo que
    aparece en TODA ingesta nueva es ruido fijo, y un chequeo que siempre habla se deja de mirar.
    """
    ads_json([rec("2020AAA...1..1A"), rec("2021BBB...2..2B")])
    monkeypatch.setattr(sys, "argv", ["make_notes.py", "test_star"])
    assert mn.main() == 0
    ficha = (toy_vault.STARS / "test_star.md").read_text(encoding="utf-8")
    assert "## Papers (2 ·" in ficha, \
        f"el roll-up no vio las notas que la misma corrida creó:\n{ficha[ficha.find('## Papers'):][:200]}"


def test_excluidos_usa_la_politica_unica_de_orden_no_las_citas_crudas(toy_vault):
    """El apéndice ordena por **tasa** (citas/año), no por cuenta cruda.  @inv INV-24

    `lib_config` declara la política en un solo lugar y dice por qué: *«la cuenta cruda está
    sesgada por la EDAD … si se cambia una las otras quedan viejas sin que nadie lo note»*.
    `sweep_star` la usa; este apéndice hacía su propio `sort(key=citas)`.

    Importa porque `## Excluidos por el filtro` es el ÚNICO canal dentro de la nota para cazar
    falsos negativos de la lente: con orden por citas crudas, lo que el consumidor ve como «lo que
    la lente descartó» son sistemáticamente los papers más viejos, y un falso negativo reciente
    queda abajo del corte (AUD-34 / #94).
    """
    viejo = rec("1990old....1..1O", relevant=False, cites=300); viejo["year"] = "1990"
    nuevo = rec("2025new....2..2N", relevant=False, cites=60);  nuevo["year"] = "2025"
    ads_json([viejo, nuevo])
    tabla = mn.excluded_table("test_star")
    assert tabla.index("2025new") < tabla.index("1990old"), (
        "el reciente con 60 citas tiene MÁS tasa que el del '90 con 300 y debe ir primero:\n" + tabla)


def test_excluidos_coerce_citation_count_no_numerico(toy_vault):
    """La celda de citas del apéndice coerce lo que no es número a `0` en vez de crashear.

    El docstring de `excluded_table` promete que un `ads.json` con **tipos torcidos** —
    `citation_count` string, `bibcode` no-str— es un estado *alcanzable, no hipotético* (un Ctrl-C
    a mitad de `query_ads`) y que acá se **degrada, nunca se lanza**: la tabla se escribe desde
    `write_star_note`, o sea DESPUÉS de gastar la red, así que una excepción tira la cadena entera
    al final. Esa promesa vivía sólo en la prosa: el barrido de mutación del 2026-08-25 encontró
    que romper el helper `citas` no ponía rojo ningún test (única superviviente PURA de las cinco).

    Se fija el contrato por sus dos lados —el valor real se muestra, el no numérico cae a `0`—
    porque un helper que devuelve siempre la constante `0` satisface la mitad de arriba solo.
    """
    roto = rec("2001bad....1..1B", relevant=False); roto["citation_count"] = "muchísimas"
    sano = rec("2001ok.....2..2K", relevant=False, cites=42)
    ads_json([roto, sano])
    tabla = mn.excluded_table("test_star")
    fila = {b: next(l for l in tabla.splitlines() if b in l) for b in ("2001bad", "2001ok")}
    assert "| 0 |" in fila["2001bad"], \
        f"`citation_count` no numérico tiene que caer a 0, no propagarse:\n{fila['2001bad']}"
    assert "| 42 |" in fila["2001ok"], \
        f"el valor real tiene que llegar a la celda:\n{fila['2001ok']}"


def test_la_regla_de_anotacion_nombra_las_tres_cosas_que_previene(toy_vault):
    """#103: el stub tiene que pedir las tres, no una genérica «sé cuidadoso».

    Cada una cierra un mecanismo de error MEDIDO (2026-08-25, HD 40307, 68 pares): el nº de línea
    hace mecánicos los de fila equivocada / cantidad confundida / epígrafe contradicho; la marca de
    segunda mano cierra el de «el dato de A atribuido a B» (3 casos); la prohibición de prosa
    comparativa cierra el de «inferencia con voz de cita» (3 casos)."""
    b = mn._BULLET_ANOTACION
    # #269 — el localizador es la PÁGINA del PDF desde #205; el `grep -n` sobre el `.txt` sirve para
    # ubicar, no para citar. Hasta 1.116.x este bullet mandaba lo contrario, publicado en la nota.
    assert "página** del PDF" in b and "grep -n" in b, "sin localizador nada se puede re-chequear"
    assert "pegá el **nº de línea**" not in b, "es la doctrina que #205 retiró"
    assert "segunda mano" in b, "el mecanismo con más casos medidos"
    assert "régimen" in b, "los 11 `parcial` eran casi todos régimen faltante"
    assert "inferencia" in b and "Inventario por eje" in b, \
        "comparar dos papers no va en la nota de paper: va al inventario, y es inferencia"


_DOS_COLUMNAS = "\n".join(
    "Texto de la columna izquierda con largo suficiente" + " " * 12 +
    "y la columna derecha, que es otro parrafo distinto" for _ in range(30))


# ── la línea de estado no puede moverse si no cambió lo que la nota afirma (#105) ──
def test_estado_line_estable_entre_corridas_identicas(tmp_path, monkeypatch):
    """Regla 6 vs D-28: `busquedas` crece en cada corrida (es bitácora y debe crecer), pero la
    cabecera NO puede publicar ese contador — hacía que dos corridas idénticas dieran notas
    distintas y el chequeo de idempotencia diera falsa alarma para toda estrella y todo tema."""
    una = [{"fecha": "2026-08-26", "n_core": 11, "n_total": 11, "bibcodes": ["A", "B"]}]
    dos = una + [{"fecha": "2026-08-26", "n_core": 11, "n_total": 11, "bibcodes": ["A", "B"]}]
    tres = dos + [{"fecha": "2026-08-26", "n_core": 11, "n_total": 11, "bibcodes": ["A", "B"]}]
    monkeypatch.setattr(cfg, "universo_acumulado", lambda slug: 2)
    monkeypatch.setattr(cfg, "load_registro", lambda slug: {})
    dest = tmp_path / "x.md"

    def linea(bs):
        monkeypatch.setattr(cfg, "load_busquedas", lambda slug: bs)
        return mn.estado_line("ica", dest)

    assert linea(dos) == linea(tres)          # mirar otra vez no cambia lo que la nota afirma
    assert "búsquedas" not in linea(tres)     # el contador de corridas es bitácora, no contenido
    assert "acumulado" in linea(tres)         # pero el lector igual sabe que es una UNIÓN
    assert "acumulado" not in linea(una)      # con una sola búsqueda no hay nada que acumular


def test_nota_offads_nace_sin_conteo_de_citas_no_con_cero(tmp_path, monkeypatch):
    """#106: off-ADS no hay catálogo que dé el conteo, así que el valor honesto es `null`. Un 0
    afirma «no lo cita nadie» sobre un dato que nadie miró —medido: la nota de Comon 1994 decía 0 y
    el trabajo tiene 8266 citas— y la puerta 2 de D-26 admite core por ese número."""
    monkeypatch.setattr(cfg, "PAPERS", tmp_path)
    monkeypatch.setattr(cfg, "FULLTEXT", tmp_path / "ft")
    monkeypatch.setattr(cfg, "PDFS", tmp_path / "pdfs")
    mn.write_web_paper_note("1994Comon", slug="ica", concept="ica", title="ICA, a new concept?",
                            first_author="Comon", year=1994)
    fm = cfg.split_fm((tmp_path / "1994Comon.md").read_text(encoding="utf-8"))
    assert fm["citation_count"] is None, "0 sería «nadie lo cita»; la verdad es «no lo sé»"


# ── #114: el DOI DataCite de arXiv ES un arXiv id ────────────────────────────────────────────────

def test_identidad_normaliza_el_doi_datacite_de_arxiv():
    """El registro del preprint trae `doi: 10.48550/arXiv.<id>`; el publicado, el mismo id en
    `arxiv_id`. Compararlos como strings distintos dejaba ciego al detector de duplicados."""
    preprint = mn.identidad({"doi": "10.48550/arXiv.2605.28635"})
    publicado = mn.identidad({"arxiv_id": "2605.28635", "doi": "10.1093/rasti/rzag038"})
    assert preprint == publicado == ("arxiv", "2605.28635")


def test_identidad_no_toca_un_doi_normal():
    assert mn.identidad({"doi": "10.1093/rasti/rzag038"}) == ("doi", "10.1093/rasti/rzag038")


# ── #115: consolidar cuando existen LAS DOS notas ────────────────────────────────────────────────

def _nota_paper(toy_vault, stem, extra=""):
    p = toy_vault.PAPERS / f"{stem}.md"
    p.write_text(f"---\nbibcode: {stem}\nmethods: []\n{extra}---\n\n# {stem}\n", encoding="utf-8")
    return p


def test_consolidar_fusiona_hacia_la_canonica(toy_vault):
    """`rename_paper` cubría sólo «existe el preprint y todavía no el publicado». Con las dos notas
    —que es literalmente el duplicado de D-19— abortaba, así que la doc prometía un remedio que no
    corría."""
    _nota_paper(toy_vault, "2026arXivVIEJO")
    _nota_paper(toy_vault, "2026RASTINUEVO")
    cita = toy_vault.CONCEPTS / "methods" / "c.md"
    cita.parent.mkdir(parents=True, exist_ok=True)
    cita.write_text("---\nname: c\n---\n\nAfirmación [[2026arXivVIEJO]].\n", encoding="utf-8")

    mn.rename_paper("2026arXivVIEJO", "2026RASTINUEVO")

    assert not (toy_vault.PAPERS / "2026arXivVIEJO.md").exists(), "la vieja se borra"
    canon = toy_vault.PAPERS / "2026RASTINUEVO.md"
    fm = cfg.split_fm(canon.read_text(encoding="utf-8"))
    assert [v["bibcode"] for v in fm["versions"]] == ["2026arXivVIEJO"], "el alias queda en versions[]"
    assert "[[2026RASTINUEVO]]" in cita.read_text(encoding="utf-8"), "los wikilinks se reescriben"


def test_consolidar_REHUSA_si_la_vieja_tiene_extraccion_y_la_nueva_no(toy_vault):
    """Descartar el paso más caro de la cadena en silencio es lo que el framework evita en todos
    lados (cf. `entity.py delete`, que avisa y no borra el paper compartido)."""
    _nota_paper(toy_vault, "2026arXivVIEJO", extra="")
    p = toy_vault.PAPERS / "2026arXivVIEJO.md"
    p.write_text(p.read_text(encoding="utf-8").replace("methods: []", "methods:\n- ica"), encoding="utf-8")
    _nota_paper(toy_vault, "2026RASTINUEVO")

    with pytest.raises(SystemExit) as e:
        mn.rename_paper("2026arXivVIEJO", "2026RASTINUEVO")
    assert "extracción LLM" in str(e.value)
    assert (toy_vault.PAPERS / "2026arXivVIEJO.md").exists(), "no se borró nada"


def test_el_drop_core_se_ve_en_la_tabla_de_papers(toy_vault, monkeypatch):
    """#116: #112 promete que el excluido «queda VISIBLE», y esa visibilidad vivía sólo en `build/`
    y el registro. En la ficha aparecía como `sin extraer` — que se lee como «la lente lo dice core,
    todavía no llegamos»: el estado OPUESTO al real."""
    monkeypatch.setattr(mn.cfg, "load_decisiones", lambda slug: {
        "2020dropeado": {"decision": "descartado", "origen": "sujeto", "motivo": "polisemia"},
        "2020chaining": {"decision": "descartado", "motivo": "ruido del grafo"},   # sin `origen`
    })
    monkeypatch.setattr(mn, "_papers_del_sujeto", lambda *a, **k: [
        ("2020dropeado", {"relevance": "high", "methods": []}),
        ("2020chaining", {"relevance": "high", "methods": []}),
        ("2020normal",   {"relevance": "high", "methods": []}),
    ])
    monkeypatch.setattr(mn.cfg, "theme_by_slug", lambda s: (s, {"area": "methods", "concept": s}))
    monkeypatch.setattr(mn.cfg, "load_extra_core", lambda *a, **k: [])
    filas = {f["stem"]: f for f in mn.papers_universe("t", "theme")}
    assert filas["2020dropeado"]["estado"] == mn.ESTADO_DROPEADO
    assert filas["2020dropeado"]["origen"] == "manual-drop"
    # el descarte de un CANDIDATO del chaining nunca fue core: no se marca como excluido a mano
    assert filas["2020chaining"]["estado"] == mn.ESTADO_SIN_EXTRAER
    assert filas["2020normal"]["estado"] == mn.ESTADO_SIN_EXTRAER


# ── #117 · el migrador deduce el archivo del HASH, no del frontmatter ────────────────────────────

def _tabla(nota):
    """La tabla de verificación de esa nota — que desde #344 vive en su hermano."""
    return cfg.verif_sidecar(nota).read_text(encoding="utf-8")


def _fila(nota, viejo, nuevo):
    """Edita una celda de la tabla, en el hermano (#344)."""
    h = cfg.verif_sidecar(nota)
    h.write_text(h.read_text(encoding="utf-8").replace(viejo, nuevo), encoding="utf-8")


def _nota_con_fila(toy_vault, bib="2020citC...1..1C", hash_fila=""):
    """Una nota con un bloque de verificación de UNA fila, más el `.txt` y el PDF de esa fuente."""
    import lib_blocks as lb
    (toy_vault.FULLTEXT / "slug").mkdir(parents=True, exist_ok=True)
    ft = toy_vault.FULLTEXT / "slug" / f"{bib}.txt"
    ft.write_text("El período es de 34 días.\n", encoding="utf-8")
    (toy_vault.PDFS / "slug").mkdir(parents=True, exist_ok=True)
    pdf = toy_vault.PDFS / "slug" / f"{bib}.pdf"
    pdf.write_bytes(b"%PDF-1.4\n escaneo del editor \xff\n")
    mk_note(toy_vault.PAPERS, bib, {"tags": ["paper"], "stars": ["Estrella Test"]}, "")
    cuerpo = f"Afirmación con cita [[{bib}]].\n"
    par = lb.pairs_of(cuerpo)[0]
    nota = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    nota.parent.mkdir(parents=True, exist_ok=True)
    nota.write_text(
        "---\ntags: [methods]\n---\n" + cuerpo +
        "\n## Verificación de citas (2026-01-01)\n\n"
        "| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| 1 | extracto | [[{bib}]] | soportada | {par.anchor} | {hash_fila} | — |\n",
        encoding="utf-8")
    mn.migrate_verif_sidecar(nota)   # #344: la tabla vive en el hermano, que es lo que se migra
    return nota, ft, pdf


def test_migrar_verif_deduce_el_archivo_del_hash_no_del_frontmatter(toy_vault, capsys):
    """El punto de #117: la fila la escribió el verificador, que a veces leyó el PDF aunque el
    frontmatter no dijera nada. Inferir de un campo escribiría `txt:` sobre una fila anclada al
    PDF — una declaración falsa, en justo las filas que motivaron el issue. Se identifica el
    archivo por su huella.

    @inv INV-107"""
    import lib_blocks as lb
    nota, ft, pdf = _nota_con_fila(toy_vault, hash_fila="")
    # la fila guarda el hash del PDF — y vive en el hermano (#344)
    _fila(nota, "|  | — |", f"| {lb.bytes_hash(pdf)} | — |")
    assert mn.migrate_verif_archivo(nota) == 1
    assert f"| pdf:{lb.bytes_hash(pdf)} |" in _tabla(nota)

    nota2, ft2, _ = _nota_con_fila(toy_vault, bib="2021txtC...1..1D",
                                   hash_fila=lb.source_hash(
                                       toy_vault.FULLTEXT / "slug" / "2021txtC...1..1D.txt")
                                   if (toy_vault.FULLTEXT / "slug" / "2021txtC...1..1D.txt").exists()
                                   else "")
    _fila(nota2, "|  | — |", f"| {lb.source_hash(ft2)} | — |")
    assert mn.migrate_verif_archivo(nota2) == 1
    assert f"| txt:{lb.source_hash(ft2)} |" in _tabla(nota2)


def test_migrar_verif_es_idempotente(toy_vault):
    """Segunda corrida: cero cambios. Una celda ya prefijada se saltea.  @inv INV-107"""
    import lib_blocks as lb
    nota, ft, _ = _nota_con_fila(toy_vault)
    _fila(nota, "|  | — |", f"| {lb.source_hash(ft)} | — |")
    assert mn.migrate_verif_archivo(nota) == 1
    antes = _tabla(nota)
    assert mn.migrate_verif_archivo(nota) == 0
    assert _tabla(nota) == antes


def test_migrar_verif_avisa_cuando_no_coincide_ningun_archivo(toy_vault, capsys):
    """Sin coincidencia el par ya está vencido: se declara `txt:` —el default de cuando esas filas
    se escribieron, antes de que #205 moviera la lectura al PDF— y **se avisa** de que hay que
    re-verificar. Lo que no se hace es callarse y escribir una declaración que se lee como
    verificada.  @inv INV-107"""
    nota, _, _ = _nota_con_fila(toy_vault, hash_fila="")
    _fila(nota, "|  | — |", "| deadbeef99 | — |")
    assert mn.migrate_verif_archivo(nota) == 1
    assert "| txt:deadbeef99 |" in _tabla(nota)
    assert "re-verificar el par" in capsys.readouterr().out


def test_migrar_verif_backfill_recorre_la_boveda(toy_vault, capsys):
    """El backfill sobre toda la bóveda: toca sólo notas CON bloque de verificación y nombra cada
    una. Una bóveda sin bloques no se reescribe.  @inv INV-107"""
    import lib_blocks as lb
    assert mn.migrate_all_verif_archivo() == 0
    assert "0 fila(s)" in capsys.readouterr().out, "sin bloques no hay nada que migrar"

    nota, ft, _ = _nota_con_fila(toy_vault)
    _fila(nota, "|  | — |", f"| {lb.source_hash(ft)} | — |")
    assert mn.migrate_all_verif_archivo() == 0            # exit code, no cantidad
    salida = capsys.readouterr().out
    assert "nota-verif.md: 1 fila(s)" in salida and "1 fila(s) declaran su archivo" in salida
    assert f"txt:{lb.source_hash(ft)}" in _tabla(nota)


# ── #125 · la puerta de entrada al paper que no se sintetizó ─────────────────────────────────────

def test_la_tabla_de_papers_lleva_el_titulo(toy_vault):
    """Un paper `sin extraer` no es basura: su `.txt` participa de todo `grep` del corpus. Lo que
    falta es la **puerta de entrada** — hoy la fila es `| [[1973Ap&SS..24..407B]] | 1973 | high |
    lente | sin extraer |` y el bibcode no dice nada, así que para saber si ese paper te sirve hay
    que abrir la nota una por una (25 en un caso real).

    El título ya está en el frontmatter: es una columna más en un roll-up que ya se estampa.

    @inv INV-115"""
    mk_note(toy_vault.PAPERS, "2020tit....1..1A",
            {"tags": ["paper"], "stars": ["Estrella Test"], "year": 2020, "relevance": "high",
             "title": "Blind separation of telluric lines"}, "")
    filas = mn.papers_universe("test_star", "star")
    assert filas and filas[0].get("title") == "Blind separation of telluric lines"
    tabla = mn.papers_table(filas)
    assert "| Título |" in tabla or "| Titulo |" in tabla
    assert "Blind separation of telluric lines" in tabla




# ── #176 · el roll-up de concepto sobrevive al estampado de `## Papers` ──────────────────────────

def test_el_rollup_de_concepto_no_se_lo_come_la_tabla_de_papers(toy_vault, monkeypatch):
    """Issue #176 — `PAPERS_HEADER = "## Papers"` es **prefijo** de
    `CONCEPT_ROLLUP_HEADER = "## Papers que tocan este tema (auto)"`, y `section_start` admite texto
    colgando del encabezado (a propósito: los reales llevan sufijos como `(25 · 16 sintetizados)`).

    Resultado: en `main()`, `stamp_papers_table` corría ANTES y reemplazaba la sección del roll-up
    con la tabla de estrella; `stamp_concept_rollup` ya no encontraba su ancla y devolvía `False`
    **para siempre**. `concept_rollup_table`/`concept_rollup_rows` eran código muerto en la cadena
    real, y con ellos se perdía la columna *Entró por* — que es justo lo que D-24 dice que no se
    puede perder, porque `methods` y `thesis_links` viven en papers distintos."""
    seed_topic()
    # dos papers, uno por cada llave: es el caso que D-24 nombra (viven en papers distintos).
    (cfg.PAPERS / "2019Metodo.md").write_text(
        mn.fm({"bibcode": "2019Metodo", "year": 2019, "methods": ["gaussian-processes"]}) + "\n# x\n",
        encoding="utf-8")
    (cfg.PAPERS / "2020Tesis.md").write_text(
        mn.fm({"bibcode": "2020Tesis", "year": 2020, "thesis_links": ["gaussian-processes"]}) + "\n# x\n",
        encoding="utf-8")
    assert run_main(monkeypatch, ["gp", "--theme"]) == 0
    texto = mn._concept_dest("gp").read_text(encoding="utf-8")
    assert mn.CONCEPT_ROLLUP_HEADER in texto, "el roll-up de concepto sigue en la nota"
    assert "| Bibcode | Año | Entró por |" in texto, "y con la columna que D-24 exige"
    assert "| [[2019Metodo]] | 2019 | methods |" in texto
    assert "| [[2020Tesis]] | 2020 | thesis_links |" in texto, \
        "la UNIÓN de las dos llaves: quedarse con una pierde la mitad (D-24)"
    assert "| Bibcode | Título | Año | Relevancia | Origen | Estado |" not in texto, \
        "la tabla de ESTRELLA no reemplaza al roll-up del tema"


def test_section_start_no_confunde_un_encabezado_con_su_prefijo():
    """La causa raíz de #176, aislada. Un sufijo real es un paréntesis o nada; `que tocan este
    tema` es **otro encabezado**. Sin esta distinción, cualquier par de secciones donde una es
    prefijo de la otra se pisa en silencio.  @inv INV-98"""
    texto = "# T\n\n## Papers que tocan este tema (auto)\n\nfila\n"
    assert cfg.section_start(texto, mn.CONCEPT_ROLLUP_HEADER) > 0, "su propio encabezado sí"
    assert cfg.section_start(texto, "## Papers") < 0, "el prefijo no"
    # y los sufijos legítimos siguen andando
    assert cfg.section_start("# T\n\n## Papers (25 · 16 sintetizados)\n", "## Papers") > 0
    assert cfg.section_start("# T\n\n## Papers\n", "## Papers") > 0


# ── #175 / #178 · el stub de una hipótesis nace válido y con sus tres secciones ──────────────────

def test_una_hipotesis_nueva_no_nace_bloqueante(toy_vault):
    """Issue #175 — `write_concept_note` escribía `status: active`, que **no está** en el
    vocabulario cerrado de D-37, así que toda hipótesis recién creada nacía con un hallazgo
    bloqueante del lint. La máquina fabricaba su propia violación a partir de un campo que ella
    misma escribe.

    El valor correcto para una hipótesis recién planteada es `abierta`, y sale de la MISMA
    constante que el lint valida: si alguien toca el vocabulario, esto no puede quedar atrás."""
    import lint
    seed_topic(area="hypotheses")
    mn.write_concept_note("gp", force=False)
    dest = toy_vault.CONCEPTS / "hypotheses" / "gaussian-processes.md"
    st = read_fm(dest)["status"]
    assert st in cfg.HYP_STATUS, f"`status: {st}` fuera del vocabulario cerrado (D-37)"
    assert st == "abierta", "una hipótesis recién planteada no está sostenida ni refutada"
    assert lint.collect().por_clave("bad_status").items == (), "y el lint no la marca"


def test_el_stub_de_hipotesis_trae_sus_tres_secciones_propias(toy_vault):
    """Issue #178 — `CLAUDE.md` declara que una nota de `concepts/hypotheses/` lleva **tres cosas
    propias** que ninguna otra nota tiene: el blockquote `> Alcance …` (D-34), la tabla de evidencia
    `Paper | Postura | …` (D-21) y el veredicto marcado `inferencia` (D-36). El stub era el template
    genérico de concepto y no scaffoldeaba ninguna, así que la nota **nacía con backlog** — contra
    D-5 (*la nota nace 100 % verificada*) y contra la doctrina de que cuando el lint habla hay algo
    real."""
    seed_topic(area="hypotheses")
    mn.write_concept_note("gp", force=False)
    texto = (toy_vault.CONCEPTS / "hypotheses" / "gaussian-processes.md").read_text(encoding="utf-8")
    assert "> Alcance" in texto, "D-34: sin el alcance, un veredicto negativo se lee como universal"
    assert "| Paper | Postura | Qué dice" in texto, "D-21: la postura vive acá, no en el paper"
    assert "inferencia" in texto, "D-36: agregar N filas en un veredicto es juicio del agente"


def test_una_ficha_de_metodo_no_lleva_las_secciones_de_hipotesis(toy_vault):
    """La otra mitad de #178: el scaffolding nuevo es SÓLO de `hypotheses`. Si se filtrara a
    `methods`/`indicators`, cada concepto nacería con una tabla de evidencia vacía que nadie va a
    llenar — ruido fijo, que es el modo de falla que el propio detector existe para no producir."""
    seed_topic(area="methods")
    mn.write_concept_note("gp", force=False)
    texto = (toy_vault.CONCEPTS / "methods" / "gaussian-processes.md").read_text(encoding="utf-8")
    assert "> Alcance" not in texto and "| Paper | Postura" not in texto


def test_consolidar_conserva_el_artefacto_de_MEJOR_calidad(toy_vault):
    """Issue #170 — el docstring promete *"se conserva el MEJOR artefacto de cada tipo"* y el
    comentario *"se queda el de MEJOR calidad, y el otro se borra"*, pero el código no comparaba
    calidad en ningún lado: `if destino.exists(): art_old.unlink()` conservaba **siempre** el del
    bibcode canónico.

    El borrado es irreversible sobre `raw/`, que el contrato declara *código fuente inmutable*, y
    degrada la fuente que después leen `verify-citations` y todo `grep` del corpus. El comparador ya
    existía en este mismo archivo (`stamp_fulltext`, `_FULLTEXT_QUALITY`): no se usaba acá."""
    _nota_paper(toy_vault, "2026arXivVIEJO")
    _nota_paper(toy_vault, "2026RASTINUEVO")
    d = cfg.FULLTEXT / "tema"
    d.mkdir(parents=True, exist_ok=True)
    bueno = d / "2026arXivVIEJO.txt"
    bueno.write_text("Texto limpio de pdftotext, con la ecuacion entera.\n" * 20, encoding="utf-8")
    malo = d / "2026RASTINUEVO.txt"
    malo.write_text(f"{cfg.FULLTEXT_OCR_MARK} citable CON SALVEDAD\nmoj1b4ke\n", encoding="utf-8")

    mn.rename_paper("2026arXivVIEJO", "2026RASTINUEVO")

    sup = (d / "2026RASTINUEVO.txt").read_text(encoding="utf-8")
    assert mn._txt_provenance(d / "2026RASTINUEVO.txt") == "pdftotext", \
        "sobrevive el `.txt` de MEJOR calidad, no el que ya se llamaba como el canónico"
    assert "ecuacion entera" in sup
    assert not bueno.exists(), "y no quedan dos (el huérfano dispararía #108 para siempre)"


def test_consolidar_no_pisa_el_artefacto_bueno_del_canonico(toy_vault):
    """La otra mitad de #170: cuando el de MEJOR calidad es el del canónico, no se toca. Si el
    criterio se invirtiera, el fix sería tan destructivo como el bug."""
    _nota_paper(toy_vault, "2026arXivVIEJO")
    _nota_paper(toy_vault, "2026RASTINUEVO")
    d = cfg.FULLTEXT / "tema"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026arXivVIEJO.txt").write_text(f"{cfg.FULLTEXT_OCR_MARK} salvedad\nmoj1b4ke\n",
                                          encoding="utf-8")
    (d / "2026RASTINUEVO.txt").write_text("Texto limpio de pdftotext.\n" * 20, encoding="utf-8")
    mn.rename_paper("2026arXivVIEJO", "2026RASTINUEVO")
    assert mn._txt_provenance(d / "2026RASTINUEVO.txt") == "pdftotext"
    assert "pdftotext" in (d / "2026RASTINUEVO.txt").read_text(encoding="utf-8")


# ── #154 / #164 · el CLI `--pending` contra el schema completo de #80 ────────────────────────────

def test_el_cli_pending_acepta_los_cuatro_valores_del_vocabulario(toy_vault, monkeypatch):
    """Issue #154 — `CLAUDE.md` declara `pending` como vocabulario CERRADO de **cuatro** valores
    (*"`adquisicion` es el cuarto"*, #80) y `cfg.PENDING_OK` los tiene, pero el `choices` de este
    CLI listaba tres a mano: `argparse` rechazaba justo el que #80 agregó.

    Los `choices` salen de `cfg.PENDING_OK`, no de una copia: la asimetría era silenciosa porque el
    otro camino —`themes.yaml` vía `ingest_theme`— sí valida contra la constante."""
    for valor in cfg.PENDING_OK:
        assert run_main(monkeypatch, ["2006RasmussenWilliams", "--web", "--pending", valor,
                                      "--reason", "el usuario lo está consiguiendo",
                                      "--force"]) == 0, f"`--pending {valor}` es válido"
        fm = read_fm(toy_vault.PAPERS / "2006RasmussenWilliams.md")
        assert fm["pending_source"] == valor


def test_el_cli_pending_exige_el_motivo(toy_vault, monkeypatch, capsys):
    """Issue #164 — el camino CLI no podía producir `pending_motivo`: la llamada no lo pasaba y no
    había bandera. `CLAUDE.md` (#80) lo declara **obligatorio** y ningún chequeo del lint cazaba la
    nota que este CLI escribía fuera de schema.

    Es el mismo argumento del `--reason` del triage: en seis meses lo que sirve es el motivo (¿hay
    alguien consiguiéndola, o nadie la miró nunca?), no la categoría."""
    with pytest.raises(SystemExit):
        run_main(monkeypatch, ["2006RasmussenWilliams", "--web", "--pending", "paywall"])
    assert "motivo" in capsys.readouterr().err.lower()


def test_el_cli_pending_estampa_el_motivo_en_la_nota(toy_vault, monkeypatch):
    """El motivo declarado tiene que llegar al frontmatter: si se pide y se tira, el flag es teatro."""
    assert run_main(monkeypatch, ["2006RasmussenWilliams", "--web", "--pending", "adquisicion",
                                  "--reason", "lo trae el usuario de la biblioteca"]) == 0
    fm = read_fm(toy_vault.PAPERS / "2006RasmussenWilliams.md")
    assert fm["pending_source"] == "adquisicion"
    assert fm["pending_motivo"] == "lo trae el usuario de la biblioteca"


def test_un_alias_escalar_sobrevive_al_frontmatter_de_la_ficha(toy_vault):
    """Issue #182 — el tercer call site de `listify_curado`: el `aliases` que se ESCRIBE en la nota.

    Ningún test lo cubría, así que cambiar la función por `cfg.as_list` —que tira el escalar en vez
    de preservarlo— dejaba la suite entera verde. El docstring de la función dice que existe *"en
    vez de perder el alias en silencio en el frontmatter que se escribe"*, y perderlo en silencio
    era exactamente lo que nadie veía.

    Escribir UN alias sin corchetes es la forma natural de la primera edición de `themes.yaml`, que
    es un archivo de instancia editado a mano por definición."""
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "Gaussian processes", "area": "methods",
                                        "concept": "gaussian-processes", "aliases": "GP"}})
    mn.write_concept_note("gp", force=False)
    fm = read_fm(toy_vault.CONCEPTS / "methods" / "gaussian-processes.md")
    assert fm["aliases"] == ["GP"], \
        "el alias escalar se PRESERVA como lista de un elemento, no se tira"


def test_un_alias_escalar_sobrevive_en_la_ficha_de_estrella(toy_vault):
    """El mismo call site del otro lado (`write_star_note`). Son dos destinos distintos y la
    auditoría midió que ninguno estaba cubierto (#182)."""
    write_yaml(cfg.STARS_YAML, {"Estrella Test": {"slug": "test_star", "simbad": "s",
                                                  "ads_object": "Test Star", "aliases": "HD 12345"}})
    mn.write_star_note("test_star", force=False)
    fm = read_fm(toy_vault.STARS / "test_star.md")
    assert fm["aliases"] == ["HD 12345"]


# ── #188 paso 3 · el stub nace con su VISTA, no con una extracción sin scope ────────────────────

def test_vista_block_lleva_el_sujeto_en_el_encabezado(toy_vault):
    """El encabezado ES el scope: `## Vista — <sujeto>`. Sin él la sección vuelve a ser una sola
    por bibcode y el silencio sobre un eje se lee como «se miró y no hay nada» (#188).

    @inv INV-134"""
    block = mn.vista_block("eps Eridani")
    assert block.startswith("## Vista — eps Eridani\n") and block.endswith("\n")
    assert "`eps Eridani`" in block, "la línea de estado nombra al sujeto, no sólo el encabezado"
    assert mn.vista_block("s_index", theme=True).startswith("## Vista — s_index\n")


def test_stub_de_estrella_declara_su_vista_y_su_seccion(toy_vault):
    """El stub queda COHERENTE por construcción: la vista declarada y su sección, que es lo que el
    detector de #188 exige. Sin `fecha`: la lectura todavía no ocurrió — «no consta», que es
    justamente lo que el campo opcional significa.

    @inv INV-134"""
    ads_json([rec("2020ext....1E")])
    mn.write_paper_notes("test_star", include_all=False, force=False)
    p = toy_vault.PAPERS / "2020ext....1E.md"
    fm = read_fm(p)
    assert fm["vistas"] == [{"sujeto": "Estrella Test", "tipo": "star"}]
    assert "## Vista — Estrella Test" in p.read_text(encoding="utf-8")


def test_stub_de_tema_declara_la_vista_del_concept(toy_vault):
    seed_topic()
    ads_json([rec("2020gpsA...1..1A")], slug="gp")
    mn.write_paper_notes("gp", include_all=False, force=False, theme=True)
    p = toy_vault.PAPERS / "2020gpsA...1..1A.md"
    assert read_fm(p)["vistas"] == [{"sujeto": "gaussian-processes", "tipo": "theme"}]
    assert "## Vista — gaussian-processes" in p.read_text(encoding="utf-8")


def test_stub_off_ads_tambien_declara_su_vista(toy_vault):
    mn.write_web_paper_note("2020Smith", slug="gp", concept="gaussian-processes", url="https://x")
    p = toy_vault.PAPERS / "2020Smith.md"
    assert read_fm(p)["vistas"] == [{"sujeto": "gaussian-processes", "tipo": "theme"}]
    assert "## Vista — gaussian-processes" in p.read_text(encoding="utf-8")


def test_el_retro_linkeo_NO_escribe_vistas(toy_vault):
    """Regla 2 del diseño (#188): las vistas las escribe la LECTURA, nunca el retro-link. Es lo que
    mantiene a `stars`/`thesis_links` como RECLAMOS —`make_notes` los mergea add-only sin leer
    nada— y a `vistas[]` como lecturas. Si el retro-link las tocara, volvemos al problema que el
    campo vino a resolver: el caso medido son 141 notas retro-linkeadas sin segunda lectura.

    @inv INV-134"""
    seed_topic()
    ads_json([rec("2020gpsA...1..1A")], slug="gp")
    mn.write_paper_notes("gp", include_all=False, force=False, theme=True)
    p = toy_vault.PAPERS / "2020gpsA...1..1A.md"
    antes = read_fm(p)["vistas"]

    # el MISMO paper llega ahora por el ingest de una estrella: seed add-only, sin leer nada
    ads_json([rec("2020gpsA...1..1A")])
    mn.write_paper_notes("test_star", include_all=False, force=False)
    fm = read_fm(p)
    assert fm["vistas"] == antes, "el retro-link no declara una lectura que nadie hizo"
    assert "Estrella Test" in fm["stars"], "pero sí mergea el RECLAMO"


# ── #196: el estampador que no encuentra su ancla no puede volver en silencio ────────────────────

def test_theme_restampa_la_tabla_papers_estilo_ficha(toy_vault):
    # @inv INV-15
    """#196: una nota de concepto puede llevar el encabezado estilo ficha `## Papers`.

    `--theme` sólo llamaba a `stamp_concept_rollup`, que ancla en `## Papers que tocan este tema
    (auto)`: sobre esa nota `_reemplazar_seccion` no encontraba la sección, devolvía `False` y nadie
    se enteraba. Medido en una bóveda real: la tabla publicaba `66 · 41` sobre un universo de `90 ·
    57` y `make_notes.py <slug> --theme` no la tocaba.

    El test mide **staleness**, que es el defecto: se crea la nota, se agrega un paper DESPUÉS y se
    exige que la re-corrida lo traiga. Afirmar que el primer paper está no distingue nada — la tabla
    del stub ya lo tenía, y con esa aserción el test pasaba sin el fix (visto morir mal una vez).
    """
    #  @inv INV-136
    seed_topic()
    ads_json([rec("2020gpsA...1..1A")], slug="gp")
    mn.write_paper_notes("gp", include_all=False, force=False, theme=True)
    mn.write_concept_note("gp", force=False)
    dest = toy_vault.CONCEPTS / "methods" / "gaussian-processes.md"
    # la nota pasa a llevar el encabezado estilo FICHA, que es el caso que el bug no cubría
    dest.write_text(dest.read_text(encoding="utf-8")
                    .replace(mn.CONCEPT_ROLLUP_HEADER, mn.PAPERS_HEADER), encoding="utf-8")

    nuevo = rec("2021gpsB...2..2B") | {"doi": "10.1/otro"}   # identidad propia: D-19 rechaza el clon
    ads_json([rec("2020gpsA...1..1A"), nuevo], slug="gp")
    mn.write_paper_notes("gp", include_all=False, force=False, theme=True)
    mn.write_concept_note("gp", force=False)

    assert "2021gpsB...2..2B" in dest.read_text(encoding="utf-8"), \
        "la tabla `## Papers` quedó congelada: el paper nuevo no entró"


def test_missing_anchors_separa_al_dia_de_sin_ancla(toy_vault):
    """#196, la causa raíz: `_reemplazar_seccion` devuelve `False` en DOS casos distintos.

    «la sección ya estaba al día» (no-op idempotente, correcto) y «la sección no existe» (la cirugía
    no tiene dónde anclar, defecto). Mezclarlos es lo que dejó el bug mudo, y es el mismo modo de
    falla que #69. `missing_anchors` separa el segundo.
    """
    #  @inv INV-136
    dest = toy_vault.CONCEPTS / "methods" / "x.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("# X\n\n## Papers\n\ntabla\n", encoding="utf-8")
    assert mn.missing_anchors(dest, ["## Papers"]) == []
    assert mn.missing_anchors(dest, ["## Papers", "## No Existe"]) == ["## No Existe"]


# ── #262 / #264 · el conteo del roll-up y la marca del truncado ─────────────────────────────────


def test_metodos_table_cuenta_por_clave_normalizada_y_conserva_la_grafia(toy_vault):
    """#262 — el encabezado contaba **grafías**, no métodos.

    `methods` lo puebla la extracción con vocabulario abierto, así que el mismo método llega
    escrito de varias maneras y contar el string crudo **sobre**declara el universo — medido sobre
    una ficha real, 297 publicados sobre 291 reales, con `GLS periodogram`/`gls-periodogram` entre
    las seis colisiones. Es el defecto que #243 arregló en el detector del lint y en
    `methods_match`, sobreviviendo en el roll-up que le publica el número al lector.

    ⛔ Y se normaliza al CONTAR, nunca al escribir: las dos grafías siguen en sus filas, porque cómo
    lo nombra cada paper es información."""
    rows = [("GLS periodogram", "2020aaa...1..1A", 2020),
            ("gls-periodogram", "2021bbb...2..2B", 2021),
            ("MCMC", "2020aaa...1..1A", 2020)]
    tabla = mn.metodos_table(rows, names=set())
    assert "(2 método(s) · 3 aplicación(es))" in tabla, \
        "cuenta grafías: `GLS periodogram` y `gls-periodogram` son el mismo método"
    assert "`GLS periodogram`" in tabla and "`gls-periodogram`" in tabla, \
        "se normalizó al escribir: la grafía del extractor es información y no se toca"


def test_titulo_corto_marca_el_corte_y_no_deja_espacio_huerfano():
    """#264 — los dos roll-ups cortaban el título **sin decirlo**.

    La audiencia declarada de la bóveda es un modelo, y un modelo que lee la fila cita el paper por
    el título truncado. Era además incoherente dentro del mismo artefacto: el bloque de
    verificación, tres secciones más abajo, sí marca sus truncados porque #226 lo exige."""
    assert mn._titulo_corto("Chemical abundances of planet-host stars", 20) == "Chemical abundances…"
    assert mn._titulo_corto("corto", 20) == "corto", "no marca lo que no cortó"
    # el `rstrip()` antes del `…`: sin él quedaba el espacio huérfano de `excluded_table`
    assert mn._titulo_corto("hot super-Earths and Neptunes: dynamics", 30) == \
        "hot super-Earths and Neptunes:…"
    assert mn._titulo_corto(None, 10) == ""


# ── #260 · el separador entre la sección estampada y la siguiente ───────────────────────────────


def test_reemplazar_seccion_deja_linea_en_blanco_antes_del_proximo_encabezado(toy_vault):
    """#260 — sin la línea en blanco, Python-Markdown absorbe el `##` siguiente COMO UNA CELDA.

    `fin = nxt + 1` deja `text[fin:]` arrancando en el `## `, así que la línea en blanco que
    separaba las dos secciones cae dentro del tramo reemplazado; el `rstrip` borra además la que el
    generador produce (`planetas_table`, `papers_table` y `metodos_table` terminan las tres con
    `out.append("")`). GFM tolera un encabezado pegado a una fila de tabla y por eso no se veía en
    Obsidian; Python-Markdown —MkDocs y media cadena de export— no: medido sobre una ficha real, 3
    de sus 8 `##` desaparecían del outline y con ellos la población que D-10/INV-81 obligan a
    publicar en el título (`49 · 28 sintetizados`, `297 método(s)`, los cuatro conteos del bloque).
    """
    dest = toy_vault.STARS / "x.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("# X\n\n## Planetas (ground-truth NASA Exoplanet Archive) (0)\n\nviejo\n"
                    "\n## Papers (0 · 0)\n\n| a |\n|---|\n", encoding="utf-8")
    nuevo = ("## Planetas (ground-truth NASA Exoplanet Archive) (1)\n\n"
             "| Letra |\n|---|\n| b |\n")
    assert mn._reemplazar_seccion(dest, mn.PLANETAS_HEADER, nuevo) is True
    texto = dest.read_text(encoding="utf-8")
    assert "| b |\n\n## Papers" in texto, \
        "el `## Papers` quedó pegado a la última fila: Python-Markdown lo absorbe como celda"
    assert mn._reemplazar_seccion(dest, mn.PLANETAS_HEADER, nuevo) is False, "no es idempotente"


def test_reemplazar_seccion_no_agrega_linea_de_mas_al_final_del_archivo(toy_vault):
    """El separador es `\n\n` **sólo si hay sección siguiente**. En EOF no hay nada que separar, y
    una línea en blanco de más al final rompería la idempotencia contra el archivo ya escrito."""
    dest = toy_vault.STARS / "y.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("# Y\n\n## Planetas (ground-truth NASA Exoplanet Archive) (0)\n\nviejo\n",
                    encoding="utf-8")
    nuevo = ("## Planetas (ground-truth NASA Exoplanet Archive) (1)\n\n"
             "| Letra |\n|---|\n| b |\n")
    assert mn._reemplazar_seccion(dest, mn.PLANETAS_HEADER, nuevo) is True
    assert dest.read_text(encoding="utf-8").endswith("| b |\n"), "sobra o falta un salto en EOF"


# ── #205 · migrador de `symbols_lost` / `fulltext_layout` ───────────────────────────────────────


def test_migrar_txt_fields_saca_los_dos_campos_y_no_toca_nada_mas(toy_vault):
    # @inv INV-26
    """Los dos campos existían para UNA decisión —¿el extractor lee el `.txt` o el PDF?— y esa
    decisión ya no se toma. Un campo sin lector se lee como un gate vivo, y éstos además **mienten**
    (medido: un paper con `symbols_lost: False` había perdido igual el radical `√`).

    Cirugía a nivel línea: el resto del frontmatter y el cuerpo quedan intactos."""
    mk_note(toy_vault.PAPERS, "2020aaa...1..1A",
            {"tags": ["paper"], "symbols_lost": True, "fulltext_layout": "two-column",
             "relevance": "high"}, "Prosa que no se toca.\n")
    assert mn.migrate_all_txt_fields() == 1
    texto = (toy_vault.PAPERS / "2020aaa...1..1A.md").read_text(encoding="utf-8")
    assert "symbols_lost" not in texto and "fulltext_layout" not in texto
    assert "relevance: high" in texto, "se llevó puesto otro campo"
    assert "Prosa que no se toca." in texto, "tocó el cuerpo"


def test_migrar_txt_fields_es_idempotente_y_no_reescribe_lo_limpio(toy_vault):
    """Segunda corrida = 0 notas tocadas. Sin esto el migrador reescribiría toda la bóveda en cada
    pasada y rompería la regla «corré dos veces y hasheá»."""
    mk_note(toy_vault.PAPERS, "2020bbb...1..1B", {"tags": ["paper"], "fulltext_layout": "single-column"}, "")
    mk_note(toy_vault.PAPERS, "2020ccc...1..1C", {"tags": ["paper"], "relevance": "low"}, "")
    assert mn.migrate_all_txt_fields() == 1, "sólo la nota con el campo viejo"
    antes = (toy_vault.PAPERS / "2020ccc...1..1C.md").read_text(encoding="utf-8")
    assert mn.migrate_all_txt_fields() == 0
    assert (toy_vault.PAPERS / "2020ccc...1..1C.md").read_text(encoding="utf-8") == antes




def test_unpend_saca_tambien_el_motivo_pendiente(toy_vault):
    """`pending_motivo` viaja con `pending_source` (#80). Al llegar la fuente salía sólo el primero,
    y la nota quedaba con el motivo de un estado que ya no existe —«nadie la está consiguiendo»—
    sobre una fuente que YA está en disco."""
    (toy_vault.FULLTEXT / "gp").mkdir(parents=True, exist_ok=True)
    (toy_vault.FULLTEXT / "gp" / "2006Rasm.txt").write_text("texto", encoding="utf-8")
    mk_note(toy_vault.PAPERS, "2006Rasm",
            {"tags": ["paper"], "pdf": None, "pending_source": "paywall",
             "pending_motivo": "lo está consiguiendo el usuario"}, "cuerpo\n")
    dest = toy_vault.PAPERS / "2006Rasm.md"
    assert mn.unpend_note(dest, "2006Rasm", "gp")
    texto = dest.read_text(encoding="utf-8")
    assert "pending_source" not in texto
    assert "pending_motivo" not in texto, "quedó el motivo de un estado que ya no existe"


# ── las cirugías de cabecera no tocan el cuerpo (auditoría 2026-08-28) ──────────────────────────


def _nota_con_estado_en_la_prosa(toy_vault, slug="gp"):
    """Un concepto con cabecera estampable Y una línea de prosa que empieza como la de estado."""
    dest = toy_vault.CONCEPTS / "methods" / f"{slug}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        "---\nname: GP\ntags: [methods]\n---\n"
        f"# GP\n\n{mn.GENERATOR_LINE}1.0.0._\n\n"
        "## Síntesis\n\n"
        "> _Estado del arte: la señal de 13.9 d sigue disputada_ [[2020smith]].\n\n"
        "Prosa normal.\n", encoding="utf-8")
    return dest


def test_stamp_estado_no_se_come_prosa_del_cuerpo(toy_vault):
    """INV-15: *«destruir prosa exige una acción explícita distinta de la corrida normal»*. El
    `sub(count=1)` corría sobre el TEXTO ENTERO, así que la primera línea del cuerpo que empezara
    con `> _Estado` desaparecía en una corrida normal — sin `--force` y sin aviso. Y «Estado del
    arte» es la frase castellana estándar en un concepto."""
    dest = _nota_con_estado_en_la_prosa(toy_vault)
    mn.stamp_estado("gp", dest)
    texto = dest.read_text(encoding="utf-8")
    assert "> _Estado del arte: la señal de 13.9 d sigue disputada_ [[2020smith]]." in texto


def test_stamp_ground_truth_line_tampoco(toy_vault):
    """El gemelo, con el mismo defecto y el mismo arreglo."""
    dest = toy_vault.STARS / "test_star.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        "---\nname: Estrella Test\nslug: test_star\ntags: [star]\n---\n"
        f"# Estrella Test\n\n{mn.GENERATOR_LINE}1.0.0._\n\n"
        "## Síntesis\n\n> _Ground-truth de este survey no cubre la banda K_ [[2020a]].\n",
        encoding="utf-8")
    mn.stamp_ground_truth_line("test_star", dest)
    assert "> _Ground-truth de este survey no cubre la banda K_ [[2020a]]." in dest.read_text(encoding="utf-8")


def test_la_cirugia_de_cabecera_sigue_reemplazando_su_propia_linea(toy_vault):
    """La otra mitad: acotar el borrado no puede volverlo un no-op. Con la línea vieja DENTRO del
    bloque de cabecera, se reemplaza."""
    dest = toy_vault.CONCEPTS / "methods" / "gp2.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        "---\nname: GP2\ntags: [methods]\n---\n"
        "# GP2\n\n> _Estado — búsqueda 1999-01-01 (viejo)_\n"
        f"{mn.GENERATOR_LINE}1.0.0._\n\n## Síntesis\n\nProsa.\n", encoding="utf-8")
    cfg.save_busqueda("gp2", {"fecha": "2026-08-28", "query": "q", "n_total": 5, "n_core": 2})
    mn.stamp_estado("gp2", dest)
    texto = dest.read_text(encoding="utf-8")
    assert "1999-01-01" not in texto, "no reemplazó la línea vieja de la cabecera"
    assert "2026-08-28" in texto


@pytest.mark.parametrize("gt, esperado", [
    # `null` es legítimo: NEA calla seguido, y `as_map`/`as_list` lo absorben sin ruido.
    ({"host": None, "planets": []}, None),
    ({"host": {}, "planets": None}, None),
    # una FORMA que no es la declarada sí se avisa: el JSON está mal y hay que arreglarlo.
    ({"host": "x", "planets": []}, "no es un mapa"),
    ({"host": {}, "planets": ["b"]}, "no es una lista de mapas"),
])
def test_write_star_note_no_revienta_con_ground_truth_malformado(toy_vault, capsys, gt, esperado):
    """Las cuatro formas que el LINT sí contempla (`lint.py:1955-1976`) y que `sync_mirror` ya había
    blindado **en este mismo archivo** hacían reventar a `write_star_note` con `AttributeError` /
    `TypeError`. Es el patrón que la auditoría del 2026-08-28 encontró seis veces: el arreglo
    aplicado a un sitio y no a su gemelo.

    Cobarde y **ruidoso**, mismo criterio que `sync_mirror`: se avisa cuál es la forma mala y se
    escribe lo que se puede, en vez de tumbar la ficha entera.  @inv INV-01"""
    cfg.STARS_YAML.write_text("Estrella Test:\n  slug: test_star\n", encoding="utf-8")
    (cfg.GROUND_TRUTH).mkdir(parents=True, exist_ok=True)
    (cfg.GROUND_TRUTH / "test_star.json").write_text(json.dumps(gt), encoding="utf-8")
    mn.write_star_note("test_star", force=True)
    assert (toy_vault.STARS / "test_star.md").exists(), "no escribió la ficha"
    if esperado:
        assert esperado in capsys.readouterr().out, "escribió en silencio: la forma mala no se avisó"


# ── AUD-175 / INV-64: el migrador que #188 no entregó ────────────────────────

def test_migrate_vistas_convierte_el_schema_viejo(toy_vault, capsys):
    """AUD-175 / INV-64 — #188 entregó un **detector bloqueante sin migrador**, que es la mitad del
    contrato del repo: «schema nuevo = migrador de un solo uso + detector bloqueante, nunca lector
    tolerante». Sin él, toda nota anterior a 1.68.0 queda en rojo con la única salida de editarla a
    mano (medido en una bóveda real: 908 notas de paper)."""
    una = mk_note(cfg.PAPERS, "2020unoA...1..1A",
                  {"bibcode": "2020unoA...1..1A", "tags": ["paper"], "stars": ["Estrella Test"]},
                  "## Extracción (LLM)\n\nProsa cara.\n")
    varias = mk_note(cfg.PAPERS, "2020dosB...1..1B",
                     {"bibcode": "2020dosB...1..1B", "tags": ["paper"],
                      "stars": ["Estrella Test"], "thesis_links": ["gp"]},
                     "## Extracción (LLM)\n\nProsa cara.\n")
    n, ambiguas = mn.migrate_all_vistas()

    assert n == 1 and [a[0] for a in ambiguas] == ["2020dosB...1..1B"]
    fm = read_fm(una)
    assert fm["vistas"] == [{"sujeto": "Estrella Test", "tipo": "star"}]
    assert "fecha" not in fm["vistas"][0], "la extracción vieja ocurrió, pero CUÁNDO no consta"
    texto = una.read_text(encoding="utf-8")
    assert "## Vista — Estrella Test" in texto and "## Extracción (LLM)" not in texto
    assert "Prosa cara." in texto                       # la extracción no se toca

    # la ambigua queda intacta: elegir un sujeto afirmaría una lectura que nadie hizo desde ahí
    assert "## Extracción (LLM)" in varias.read_text(encoding="utf-8")
    # y es idempotente
    assert mn.migrate_all_vistas()[0] == 0


def test_force_no_pisa_la_nota_de_OTRO_sujeto(toy_vault, capsys):
    """AUD-197 — `--force` significa «pisá la nota de ESTE sujeto», no «pisá cualquier nota».

    Un paper compartido lleva la vista y la extracción de OTRO sujeto (#188: medido, 141 de 908
    notas las reclaman 2+), y reescribirla desde el stub las borra: trabajo caro, ajeno a la
    operación en curso y que nadie pidió tocar."""
    bib = "2020shrA...1..1A"
    ads = cfg.ROOT / "build" / "test_star"
    ads.mkdir(parents=True, exist_ok=True)
    (ads / "ads.json").write_text(json.dumps({"records": [
        {"bibcode": bib, "title": "T", "relevant": True, "authors": ["A"], "year": "2020"}]}),
        encoding="utf-8")
    compartida = mk_note(cfg.PAPERS, bib,
                         {"bibcode": bib, "tags": ["paper"],
                          "stars": ["Estrella Test", "Otra Estrella"],
                          "vistas": [{"sujeto": "Otra Estrella", "tipo": "star",
                                      "fecha": "2026-08-01"}]},
                         "## Vista — Otra Estrella\n\nExtracción cara del otro sujeto.\n")
    antes = compartida.read_text(encoding="utf-8")

    mn.write_paper_notes("test_star", False, True)

    assert compartida.read_text(encoding="utf-8") == antes
    salida = capsys.readouterr().out
    assert "`--force` NO lo pisa" in salida and "Otra Estrella" in salida


def test_stamp_accessed_es_cirugia_de_una_linea(toy_vault):
    """INV-30 / AUD-170 — `accessed` ES el "Retrieved <fecha>" de la cita, así que tiene que quedar
    igual al del snapshot de al lado, que es el archivo que `verify-citations` lee.

    Metadata de máquina como `pdf`/`fulltext`: se reescribe SU línea y nada más — la extracción LLM
    y el resto del frontmatter quedan byte a byte. Y el campo ausente NO se inventa: sin `accessed:`
    no hay posición que adivinar (mismo criterio que `merge_frontmatter_list`)."""
    dest = mk_note(cfg.PAPERS, "2006Rasmussen",
                   {"bibcode": "2006Rasmussen", "tags": ["paper", "web"],
                    "source_url": "https://x", "accessed": "2020-05-05",
                    "methods": ["gp"]},
                   "## Vista — GP\n\nExtracción cara.\n")
    antes = dest.read_text(encoding="utf-8")

    assert mn.stamp_accessed(dest, "2026-08-28") is True
    texto = dest.read_text(encoding="utf-8")
    assert str(read_fm(dest)["accessed"]) == "2026-08-28"   # YAML lo relee como `date`
    assert read_fm(dest)["methods"] == ["gp"] and "Extracción cara." in texto
    assert len(texto.split("\n")) == len(antes.split("\n")), "cambió más de una línea"
    assert mn.stamp_accessed(dest, "2026-08-28") is False, "idempotente"

    sin_campo = mk_note(cfg.PAPERS, "2007Otro", {"bibcode": "2007Otro", "tags": ["paper"]}, "x\n")
    assert mn.stamp_accessed(sin_campo, "2026-08-28") is False, "no se inventa la posición"


def test_paper_notes_no_resucita_el_dropeado(toy_vault, capsys):
    """#215 — el cuarto consumidor de `--drop-core`, el que decide QUÉ notas se escriben.

    La decisión vive en el registro VERSIONADO; `relevant` vive en `build/`, que sólo `query_ads`
    reescribe. Correr `make_notes` solo —lo que el propio aviso del drop invita a hacer— resucitaba
    el paper como stub, y encima de la extracción que el drop acababa de borrar: la nota volvía a
    existir y volvía vacía. Medido en `ica` (2026-08-29): 9 notas de ~100 líneas → stubs de 54.
    """
    ads_json([rec("2020conA...1..1A"), rec("1990preB....1..1B")])
    cfg.save_registro("test_star", {"decisiones": {
        "2020conA...1..1A": {"decision": "descartado", "origen": "sujeto",
                             "motivo": "falso positivo de polisemia", "fecha": "2026-08-29"}}})
    mn.write_paper_notes("test_star", include_all=False, force=False)
    assert not (toy_vault.PAPERS / "2020conA...1..1A.md").exists()
    assert (toy_vault.PAPERS / "1990preB....1..1B.md").exists()
    assert "--drop-core" in capsys.readouterr().out


def test_paper_notes_all_tampoco_resucita_el_dropeado(toy_vault):
    """`--all` pide los papers NO-CORE, que es otra cosa que los que el usuario sacó a mano: por eso
    el filtro va ANTES. Sin esto la escotilla de `--all` reabría en silencio la decisión de
    curación."""
    ads_json([rec("2020conA...1..1A", relevant=False)])
    cfg.save_registro("test_star", {"decisiones": {
        "2020conA...1..1A": {"decision": "descartado", "origen": "sujeto",
                             "motivo": "off-topic", "fecha": "2026-08-29"}}})
    mn.write_paper_notes("test_star", include_all=True, force=False)
    assert not (toy_vault.PAPERS / "2020conA...1..1A.md").exists()


# ── #217 · retarget_artifacts: verdad de disco después de un borrado ─────────

def _nota_apuntando_a(bib, slug, toy_vault):
    (cfg.PAPERS).mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / f"{bib}.md").write_text(
        f"---\nbibcode: {bib}\ntags: [paper]\npdf: ../../raw/pdfs/{slug}/{bib}.pdf\n"
        f"fulltext: ../../raw/fulltext/{slug}/{bib}.txt\nfulltext_source: pdftotext\n---\n"
        f"# {bib}\n\n· ADS: `{bib}` · [📄 PDF](../../raw/pdfs/{slug}/{bib}.pdf)\n",
        encoding="utf-8")
    return cfg.PAPERS / f"{bib}.md"


def test_retarget_anula_cuando_no_queda_copia(toy_vault):
    """#217 — verdad de disco: sin ningún artefacto, los dos campos van a `null` y el link de
    cabecera se cae con ellos (es metadata derivada del campo `pdf`)."""
    dest = _nota_apuntando_a("2021PASP..133g4501V", "ica", toy_vault)
    assert mn.retarget_artifacts("2021PASP..133g4501V") is True
    txt = dest.read_text(encoding="utf-8")
    assert "pdf: null" in txt and "fulltext: null" in txt and "[📄 PDF]" not in txt


def test_retarget_es_idempotente(toy_vault):
    """#217 — segunda corrida: nada que cambiar, devuelve False (la regla nº 6 del repo)."""
    _nota_apuntando_a("2021PASP..133g4501V", "ica", toy_vault)
    mn.retarget_artifacts("2021PASP..133g4501V")
    assert mn.retarget_artifacts("2021PASP..133g4501V") is False


def test_retarget_sin_nota_no_revienta(toy_vault):
    """#217 — `drop_core` lo llama sobre un bibcode cualquiera: sin nota, no-op silencioso."""
    assert mn.retarget_artifacts("2021NoExiste..1A") is False


def test_retarget_no_toca_una_nota_sin_frontmatter(toy_vault):
    """#217 — sin frontmatter no hay campos que re-apuntar, y adivinar sería peor: el lint ya
    reporta la nota rota (`fm_error`), acá no se la edita."""
    (cfg.PAPERS).mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2021Suelto.md").write_text("# sin frontmatter\n", encoding="utf-8")
    assert mn.retarget_artifacts("2021Suelto") is False
    assert (cfg.PAPERS / "2021Suelto.md").read_text(encoding="utf-8") == "# sin frontmatter\n"


# ── #228 · el renombre completo: cabecera, `bibstem` y la extracción de `build/` ─────────────────

def _con_artefactos(bib: str, *, slug: str = "test_star"):
    """Un paper con `.txt`, PDF y extracción — las tres capas que el renombre mueve (#311: la
    extracción vive versionada en `vault/raw/extraccion/<slug>/`, no en `build/`)."""
    _paper(bib)
    (cfg.FULLTEXT / slug).mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / slug / f"{bib}.txt").write_text("texto", encoding="utf-8")
    (cfg.PDFS / slug).mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / slug / f"{bib}.pdf").write_bytes(b"%PDF-1.4")
    d = cfg.EXTRACCION / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{bib}.json").write_text(json.dumps({"bibcode": bib, "methods": ["ica"]}),
                                   encoding="utf-8")
    return d


def test_el_renombre_mueve_la_extraccion(toy_vault):
    """#228 — `harvest_views` mapea JSON→nota por `data["bibcode"]`, así que una extracción dejada
    bajo el bibcode viejo hace que el cosechador imprima «no hay nota en `papers/`» y SALTEE la nota
    en toda corrida futura, en silencio. Medido: la única nota fuera del alcance del cosechador era
    justo la que cargaba una salvedad falsa — re-correr el cosechador no la habría tocado.
    Una EXTRACCIÓN no se regenera sin volver a pagarla: por eso vive versionada (#311)."""
    d = _con_artefactos("2020preX...1..1X")
    mn.rename_paper("2020preX...1..1X", "2021pubY...1..1Y")
    assert not (d / "2020preX...1..1X.json").exists()
    nuevo = d / "2021pubY...1..1Y.json"
    assert nuevo.exists(), "la extracción quedó huérfana del cosechador"
    assert json.loads(nuevo.read_text(encoding="utf-8"))["bibcode"] == "2021pubY...1..1Y", \
        "el nombre del archivo no alcanza: el cosechador mapea por el CAMPO"


def test_el_renombre_reestampa_la_cabecera(toy_vault):
    """#228 — la línea `· ADS: \\`bibcode\\`` es metadata DERIVADA (la re-estampa `make_notes` en
    cualquier otro contexto) y el renombre no la tocaba: la nota canónica del trabajo publicado le
    mostraba al lector el bibcode del preprint."""
    _con_artefactos("2020preX...1..1X")
    nota = cfg.PAPERS / "2020preX...1..1X.md"
    t = nota.read_text(encoding="utf-8")
    fm_end = t.index("---", 3) + 4
    nota.write_text(t[:fm_end] + "\n· [[test_star]] · ADS: `2020preX...1..1X`\n" + t[fm_end:],
                    encoding="utf-8")
    mn.rename_paper("2020preX...1..1X", "2021pubY...1..1Y")
    cuerpo = (cfg.PAPERS / "2021pubY...1..1Y.md").read_text(encoding="utf-8")
    assert "ADS: `2021pubY...1..1Y`" in cuerpo
    assert "2020preX...1..1X" not in cuerpo.split("## ")[0].split("---")[-1], \
        "la cabecera todavía publica el bibcode viejo"


def test_el_renombre_deja_bibstem_en_no_consta(toy_vault, capsys):
    """#228 — `bibstem` es verdad de CATÁLOGO y el renombre no tiene catálogo: dejarlo con el valor
    del preprint sería afirmar una procedencia falsa, e inventarlo es peor. Queda en null («no
    consta») y se dice, que es la mitad honesta de las dos opciones."""
    _con_artefactos("2020preX...1..1X")
    nota = cfg.PAPERS / "2020preX...1..1X.md"
    t = nota.read_text(encoding="utf-8")
    nota.write_text(t.replace("bibcode:", "bibstem: arXiv\nbibcode:", 1), encoding="utf-8")
    mn.rename_paper("2020preX...1..1X", "2021pubY...1..1Y")
    assert read_fm(cfg.PAPERS / "2021pubY...1..1Y.md").get("bibstem") is None
    assert "bibstem" in capsys.readouterr().out


def test_el_renombre_deja_paso_en_la_cadena(toy_vault, monkeypatch):
    """#231 / D-57 — la rama de `--rename-paper` retornaba ANTES del `save_paso` del final, así que
    una operación que mueve archivos y reescribe wikilinks de toda la bóveda no dejaba rastro. El
    slug sale de la verdad de disco: la misma con la que se movieron los artefactos."""
    _con_artefactos("2020preX...1..1X")
    monkeypatch.setattr(sys, "argv", ["make_notes.py", "--rename-paper",
                                      "2020preX...1..1X", "2021pubY...1..1Y"])
    mn.main()
    pasos = [p.get("paso") for p in cfg.load_cadena("test_star")]
    assert "make_notes" in pasos, pasos


def test_no_pisa_una_extraccion_ya_existente_del_bibcode_nuevo(toy_vault, capsys):
    """#228 — elegir entre dos lecturas pagadas es juicio, no mecánica: si la canónica ya tiene su
    extracción, la vieja se deja donde está y se avisa."""
    d = _con_artefactos("2020preX...1..1X")
    (d / "2021pubY...1..1Y.json").write_text(json.dumps({"bibcode": "2021pubY...1..1Y"}),
                                             encoding="utf-8")
    mn.rename_paper("2020preX...1..1X", "2021pubY...1..1Y")
    assert (d / "2020preX...1..1X.json").exists(), "se pisó una extracción ya pagada"
    assert "ya hay extracción" in capsys.readouterr().out


def test_sacar_pending_source_no_rompe_el_yaml_multilinea(toy_vault):
    """#244 — `pending_motivo` es obligatorio y de texto libre (#80), así que cualquier motivo de
    más de ~90 caracteres se serializa MULTILÍNEA. Filtrando por `startswith` se borraba la primera
    línea del escalar y quedaban huérfanas las de continuación: el frontmatter dejaba de parsear y
    la nota pasaba a evadir TODOS los chequeos de su tipo (categoría bloqueante del lint). O sea que
    el camino feliz de #80 —«cuando esté la fuente, reemplazá `pending` por `pdf:` y re-corré»—
    rompía la nota."""
    mn.write_web_paper_note(
        "2001Libro", slug="ica", concept="ica", title="Independent Component Analysis",
        first_author="Hyvarinen", year=2001, pending="adquisicion",
        pending_motivo=("libro comercial sin copia libre; lo consigue el usuario. Es la fuente que "
                        "el STATUS declara como el hueco mas grande del concepto: la derivacion de "
                        "la negentropia y las condiciones de identificabilidad no estan en ninguna "
                        "fuente de la boveda"))
    nota = cfg.PAPERS / "2001Libro.md"
    assert "pending_motivo" in nota.read_text(encoding="utf-8")
    (cfg.PDFS / "ica").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "ica" / "2001Libro.pdf").write_bytes(b"%PDF-1.4")

    assert mn.unpend_note(nota, "2001Libro", "ica") is True
    fm = read_fm(nota)
    assert fm, "el frontmatter dejó de parsear: la nota evade los chequeos de su tipo"
    assert "pending_source" not in fm and "pending_motivo" not in fm
    assert fm["pdf"].endswith("2001Libro.pdf"), "y el `pdf` sí quedó linkeado"


def test_no_escribe_si_el_frontmatter_quedaria_roto(toy_vault, capsys):
    """#244, la red decisiva: una operación no puede dejar la nota PEOR de lo que la encontró.
    Mismo principio que contar los pares antes y después en `apply_fixes` (#222)."""
    mn.write_web_paper_note("2002Otro", slug="ica", concept="ica", title="T",
                            first_author="A", year=2002, pending="paywall",
                            pending_motivo="corto")
    nota = cfg.PAPERS / "2002Otro.md"
    (cfg.PDFS / "ica").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "ica" / "2002Otro.pdf").write_bytes(b"%PDF-1.4")
    # se simula un borrado que rompería el YAML: `_drop_keys` mutado a la versión vieja
    import make_notes
    viejo = make_notes._drop_keys
    make_notes._drop_keys = lambda head, pref: [ln for ln in head.split("\n")
                                                if not ln.startswith(pref)] + ["  huerfana:"]
    try:
        assert mn.unpend_note(nota, "2002Otro", "ica") is False
    finally:
        make_notes._drop_keys = viejo
    assert "NO se escribe" in capsys.readouterr().out
    assert read_fm(nota), "la nota quedó intacta"


# ── #277 · el `## Abstract` que el stub off-ADS nunca escribía ──────────────────────────────────

def test_el_stub_off_ads_escribe_la_seccion_abstract(toy_vault):
    """#277 — `write_web_paper_note` no la escribía **nunca**, y `CLAUDE.md` afirmaba que sí «al
    crear». De ahí salían las 39 notas sin la capa auditable del cuerpo."""
    mn.write_web_paper_note("2020Autor", url="https://x.test/a", slug="ica", concept="ica")
    texto = (cfg.PAPERS / "2020Autor.md").read_text(encoding="utf-8")
    assert "## Abstract" in texto
    assert cfg.ABSTRACT_PLACEHOLDER in texto, "sin catálogo el contenido es el placeholder, no se inventa"


def test_restamp_abstracts_recupera_la_seccion_y_es_idempotente(toy_vault, capsys):
    """El backfill: escribe la SECCIÓN que falta (el contenido lo completa la próxima extracción) y
    una segunda corrida no cambia un byte — invariante del framework para todo lo que escribe en
    `vault/` (red 6)."""
    dest = mk_note(cfg.PAPERS, "2019A....1A", {"bibcode": "2019A....1A", "tags": ["paper"],
                                               "stars": ["tau Cet"]},
                   f"# p\n\n{mn.GENERATOR_LINE}\n\n## Conclusiones\nx\n")
    assert mn.restamp_abstracts() == 0
    texto = dest.read_text(encoding="utf-8")
    assert "## Abstract" in texto and cfg.ABSTRACT_PLACEHOLDER in texto
    mn.restamp_abstracts()
    assert dest.read_text(encoding="utf-8") == texto, "la segunda corrida tiene que ser no-op"


def test_restamp_abstracts_no_adivina_donde_insertar(toy_vault, capsys):
    """Sin la línea del generador no hay dónde anclar: se dice y no se toca la nota (mismo criterio
    que `stamp_estado`). Inventar el punto de inserción es cómo una cirugía parte una nota."""
    dest = mk_note(cfg.PAPERS, "2019A....1A", {"bibcode": "2019A....1A", "tags": ["paper"],
                                               "stars": ["tau Cet"]}, "# p\n\n## Conclusiones\nx\n",
                   crudo=True)
    antes = dest.read_text(encoding="utf-8")
    mn.restamp_abstracts()
    assert dest.read_text(encoding="utf-8") == antes
    assert "--restamp-headers" in capsys.readouterr().out


def test_stamp_header_repara_el_aviso_borrado(toy_vault):
    """#277 — con la línea del generador presente y el aviso borrado, el early-return dejaba esa
    nota sin reparar **para siempre**: el deadlock de #69 espejado, y la categoría del lint quedaba
    incerrable."""
    dest = mk_note(cfg.PAPERS, "2019A....1A", {"bibcode": "2019A....1A", "tags": ["paper"],
                                               "stars": ["tau Cet"]},
                   f"# p\n\n{mn.GENERATOR_LINE}\n\n## Abstract\nx\n", crudo=True)
    assert mn.AVISO_LLM_MARCA not in dest.read_text(encoding="utf-8")
    assert mn.stamp_header(dest) is True
    texto = dest.read_text(encoding="utf-8")
    assert mn.AVISO_LLM_MARCA in texto
    assert texto.count(mn.GENERATOR_LINE) == 1, "no se duplica la línea del generador"
    assert mn.stamp_header(dest) is False, "idempotente"


# ── #269 · la plantilla de la vista publicaba la doctrina que #205 retiró ────────────────────────

def test_el_stub_y_el_prompt_no_divergen_sobre_el_localizador(toy_vault):
    """#269 — el stub se estampa en el CUERPO de toda nota de paper, así que su texto viaja en el
    vault versionado. Mandaba citar por nº de línea del `.txt` mientras el prompt vigente manda la
    página del PDF: la regla vive una sola vez (`cfg.REGLA_LOCALIZADOR`) y los dos la rinden."""
    import extraction_prompt as ep
    assert cfg.REGLA_LOCALIZADOR.split(";")[0] in mn._BULLET_ANOTACION
    prompt = ep.build_prompt("tau-cet", "2020aaa...1..1A", "tau Cet", [])
    assert "la **página** del PDF (`p. 7`)" in prompt


def test_el_migrador_deja_la_vista_cosechable(toy_vault):
    """Sin el migrador, cambiar la plantilla rompe la cosecha que el arreglo viene a destrabar:
    `write_view_section` sólo pisa mientras la sección **sea** la plantilla, así que todo stub ya
    escrito deja de matchear y la próxima cosecha no escribe la vista."""
    import harvest_views as hv
    dest = mk_note(cfg.PAPERS, "2019A....1A",
                   {"bibcode": "2019A....1A", "tags": ["paper"], "stars": ["tau Cet"],
                    "vistas": [{"sujeto": "tau Cet", "tipo": "star"}]},
                   "# p\n\n" + mn._legacy_vista_block("tau Cet", theme=False).replace(
                       mn._BULLET_ANOTACION, mn._BULLET_ANOTACION_VIEJO))
    assert hv.write_view_section(dest, "tau Cet", "## Vista — tau Cet\n\nnueva\n",
                                 theme=False) is False, "la guarda no reconoce el stub viejo"
    mn.restamp_vista_stub()
    assert "pegá el **nº de línea**" not in dest.read_text(encoding="utf-8")
    assert hv.write_view_section(dest, "tau Cet", "## Vista — tau Cet\n\nnueva\n",
                                 theme=False) is True, "tras migrar, la vista se puede cosechar"


def test_el_migrador_no_toca_una_vista_con_prosa(toy_vault):
    """Prosa ya redactada no se pisa: sus anclas de verificación cuelgan del texto exacto."""
    cuerpo = "# p\n\n## Vista — tau Cet (2026-08-30)\n\nprosa redactada de verdad\n"
    dest = mk_note(cfg.PAPERS, "2019A....1A",
                   {"bibcode": "2019A....1A", "tags": ["paper"], "stars": ["tau Cet"],
                    "vistas": [{"sujeto": "tau Cet", "tipo": "star"}]}, cuerpo)
    antes = dest.read_text(encoding="utf-8")
    mn.restamp_vista_stub()
    assert dest.read_text(encoding="utf-8") == antes


def test_no_vista_no_es_sin_extraer_en_el_rollup(toy_vault):
    """#268 — el roll-up publicaba `sin extraer` sobre un paper cuyo dueño DECLARÓ que no lo va a
    leer para ese sujeto: la declaración no valía nada donde el consumidor la mira."""
    write_yaml(cfg.STARS_YAML, {"Estrella S": {"slug": "s"}})
    mk_note(cfg.PAPERS, "2009yCat..1", {"tags": ["paper"], "bibcode": "2009yCat..1",
                                        "stars": ["Estrella S"], "relevance": "high",
                                        "no_vista": [{"sujeto": "Estrella S",
                                                      "motivo": "tabla VizieR, no es un paper"}]},
            "# p\n")
    filas = mn.papers_universe("s", "star")
    assert [f["estado"] for f in filas] == [mn.ESTADO_SIN_VISTA], filas


def test_un_no_vista_roto_no_tumba_el_rollup(toy_vault):
    """`papers_universe` corre DENTRO de la escritura de notas: una nota con el campo mal formado no
    puede abortar la pasada entera (misma doctrina que `fm_broken` en el lint). Cae a la escalera
    vieja y el lint reporta la forma por su cuenta."""
    write_yaml(cfg.STARS_YAML, {"Estrella S": {"slug": "s"}})
    mk_note(cfg.PAPERS, "2009yCat..1", {"tags": ["paper"], "bibcode": "2009yCat..1",
                                        "stars": ["Estrella S"], "relevance": "high",
                                        "no_vista": "un escalar"}, "# p\n")
    filas = mn.papers_universe("s", "star")
    assert [f["estado"] for f in filas] == [mn.ESTADO_SIN_EXTRAER], filas


# ── #250 · la sección de indicadores, con su puente al concepto ─────────────────────────────────

def test_el_indicador_con_nota_se_linkea_y_sin_nota_queda_declarado(toy_vault):
    """#250 — el puente ficha→concepto que faltaba. La glosa entre paréntesis se saca al comparar
    (el campo es prosa para un humano) y la grafía se muestra tal cual: nunca se reescribe."""
    mk_note(cfg.CONCEPTS / "methods", "bis", {"tags": ["concept"], "name": "bis"}, "# bis\n")
    tabla = mn.indicadores_table({"activity_indicators_expected": ["BIS (bisector de la CCF)",
                                                                  "FWHM de la CCF"]})
    assert "| `BIS (bisector de la CCF)` | [[bis]] |" in tabla
    assert "| `FWHM de la CCF` | _(sin nota)_ |" in tabla


def test_la_seccion_de_indicadores_es_idempotente(toy_vault):
    """Red 6: todo lo que escribe en `vault/` corre dos veces sin cambiar un byte."""
    write_yaml(cfg.STARS_YAML, {"Estrella Test": {"slug": "test_star"}})
    mn.write_star_note("test_star", force=True)
    dest = cfg.STARS / "test_star.md"
    mn.stamp_star_rollups("test_star", dest)
    antes = dest.read_bytes()
    mn.stamp_star_rollups("test_star", dest)
    assert dest.read_bytes() == antes


def test_la_seccion_de_indicadores_esta_declarada_como_ESTAMPADA():
    """⛔ Sin esto `solo_prosa` no la descuenta y sus `[[links]]` cuentan como citas de prosa,
    contaminando el proxy de «planeta discutido»: el falso limpio permanente que el lint documenta
    para `## Planetas`."""
    assert mn.INDICADORES_HEADER in cfg.SECCIONES_ESTAMPADAS


# ── #273 · el roll-up de métodos: una fila por método, con tope declarado ────────────────────────

def test_el_rollup_agrupa_por_clave_y_muestra_las_variantes(toy_vault):
    """#273 — 369 filas sobre 291 métodos, 374 de 1278 líneas: el 30 % de la ficha para una tabla
    que nadie puede leer. Una fila por MÉTODO, no por par (método, paper).

    ⛔ La grafía que eligió el extractor no se reescribe: se agrupa y las variantes se muestran."""
    filas = [("PCA", "2020a", "2020"), ("pca", "2021b", "2021"), ("PCA", "2019c", "2019")]
    t = mn.metodos_table(filas, names=set())
    assert t.count("\n| ") == 2, f"encabezado + una sola fila de datos:\n{t}"
    assert "`PCA`" in t and "`pca`" in t, "las dos grafías se muestran"
    assert "| 3 | 2019-2021 |" in t, "3 papers, rango de años"
    assert "(1 método(s) · 3 aplicación(es))" in t, "el encabezado publica los DOS números (#262)"


def test_el_tope_declara_cuantos_metodos_quedan_adentro(toy_vault):
    """#107 — un corte silencioso es cómo se saca una conclusión estructural de un truncamiento que
    nadie declaró. El `<summary>` dice cuántos hay adentro."""
    filas = [(f"m{i:03d}", f"20{i:02d}x", f"20{i:02d}") for i in range(10)]
    t = mn.metodos_table(filas, names=set(), tope=3)
    assert "<details><summary>7 método(s) más" in t, t
    assert "</details>" in t


def test_el_details_no_rompe_la_forma_del_artefacto(toy_vault):
    """El `<details>` va FUERA de la tabla y con su línea en blanco: si la partiera, las filas de
    adentro dejarían de renderizar (#227) o el `##` siguiente se absorbería como celda (#260)."""
    filas = [(f"m{i:03d}", f"20{i:02d}x", f"20{i:02d}") for i in range(10)]
    t = mn.metodos_table(filas, names=set(), tope=3)
    assert cfg.table_shape_issues(t) == [], cfg.table_shape_issues(t)
    assert cfg.unclosed_markers(t) == [], cfg.unclosed_markers(t)
    assert cfg.headings_glued_to_table(t + "\n## Papers\n") == []


def test_el_rollup_ordena_por_aplicaciones_y_es_determinista(toy_vault):
    """Lo más usado arriba, y el empate se rompe alfabéticamente: dos corridas tienen que dar el
    mismo byte (red 6)."""
    filas = [("zzz", "a", "2020"), ("aaa", "b", "2020"), ("aaa", "c", "2021")]
    t = mn.metodos_table(filas, names=set())
    assert t.index("`aaa`") < t.index("`zzz`")
    assert t == mn.metodos_table(filas, names=set())


# ── #271 · el backfill del markup de catálogo en `## Abstract` ──────────────────────────────────

def test_clean_catalog_markup_notes_limpia_solo_el_abstract(toy_vault):
    """#271 — medido: 249 ocurrencias en 42 notas. `<ASTROBJ>` deja el nombre del objeto
    **invisible** al renderizar, `<A href>` vuelve un link vivo una copia que se promete verbatim.

    ⚠ Sólo `## Abstract`: el resto del cuerpo es prosa de la bóveda, no copia de catálogo."""
    dest = mk_note(cfg.PAPERS, "2019A....1A", {"bibcode": "2019A....1A", "tags": ["paper"],
                                               "stars": ["tau Cet"]},
                   "# p\n\n## Abstract\nR<SUB>p</SUB> de <ASTROBJ>HD 40307</ASTROBJ>\n\n"
                   "## Vista — tau Cet\nesto <B>no</B> se toca\n", crudo=True)
    assert mn.clean_catalog_markup_notes() == 0
    texto = dest.read_text(encoding="utf-8")
    assert "Rp de HD 40307" in texto
    assert "<B>no</B>" in texto, "fuera del abstract no se toca nada"


def test_clean_catalog_markup_notes_es_idempotente(toy_vault):
    """Red 6: dos corridas, mismo byte."""
    dest = mk_note(cfg.PAPERS, "2019A....1A", {"bibcode": "2019A....1A", "tags": ["paper"],
                                               "stars": ["tau Cet"]},
                   "# p\n\n## Abstract\nH<SUB>2</SUB>O\n", crudo=True)
    mn.clean_catalog_markup_notes()
    antes = dest.read_bytes()
    mn.clean_catalog_markup_notes()
    assert dest.read_bytes() == antes


# ── #296 · `pdf_source`/`fulltext_source`, vocabulario cerrado y su migrador ──
def _paper_con_source(toy_vault, stem, **fm):
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    campos = "\n".join(f"{k}: {v}" for k, v in fm.items())
    (cfg.PAPERS / f"{stem}.md").write_text(
        f"---\nbibcode: {stem}\ntitle: T\nstars: [tau Cet]\n{campos}\n---\n\n## Abstract\n\nx\n",
        encoding="utf-8")
    return cfg.PAPERS / f"{stem}.md"


def test_migrar_source_fields_pone_null_y_MUEVE_la_prosa(toy_vault, capsys):
    """#296 — el valor fuera de vocabulario pasa a `null` (que es el valor legítimo de
    *desconocido*, y no «publicado»), pero la prosa **se mueve, no se tira**: medido, uno de los dos
    casos reales era una nota de adquisición legítima que terminó en el campo equivocado porque el
    schema no tenía dónde ponerla."""
    f = _paper_con_source(toy_vault, "2010ComonJutten",
                          pdf_source="'null consigue el usuario. ADS sólo indexa una RESEÑA'")
    n, movidas = mn.migrate_all_source_fields()
    assert n == 1 and movidas == [("2010ComonJutten", "salvedades")]
    fm = cfg.split_fm(f.read_text(encoding="utf-8"))
    assert fm["pdf_source"] is None
    assert any("consigue el usuario" in str(s) for s in cfg.as_list(fm.get("salvedades"))), \
        "la prosa no se puede perder: era información que alguien escribió a propósito"


def test_migrar_source_fields_manda_a_pending_motivo_si_la_fuente_falta(toy_vault):
    """Si la nota declara `pending_source`, el lugar natural de esa prosa es `pending_motivo` (#80):
    describe por qué la fuente todavía no está."""
    f = _paper_con_source(toy_vault, "1998Hyvarinen", pending_source="adquisicion",
                          pdf_source="'null el 2026-08-29'")
    n, movidas = mn.migrate_all_source_fields()
    assert n == 1 and movidas == [("1998Hyvarinen", "pending_motivo")]
    fm = cfg.split_fm(f.read_text(encoding="utf-8"))
    assert fm["pdf_source"] is None and "2026-08-29" in str(fm["pending_motivo"])


def test_migrar_source_fields_no_pisa_un_pending_motivo_que_ya_existe(toy_vault):
    """El motivo declarado por el usuario es información que alguien escribió: la prosa rescatada no
    puede reemplazarlo. Cuando el destino ya está ocupado, la nota queda **visible** para moverla a
    mano en vez de perderse o pisar."""
    f = _paper_con_source(toy_vault, "2011libro", pending_source="adquisicion",
                          pending_motivo="'lo consigue el usuario'",
                          pdf_source="'null el 2026-08-29'")
    mn.migrate_all_source_fields()
    texto = f.read_text(encoding="utf-8")
    fm = cfg.split_fm(texto)
    assert fm["pending_motivo"] == "lo consigue el usuario"
    assert "2026-08-29" in texto, "la prosa sigue visible en la nota"


def test_migrar_source_fields_saltea_la_nota_ilegible(toy_vault):
    """Una nota cuyo frontmatter no parsea ya es un bloqueante del lint; el migrador no la toca —
    editar a ciegas un YAML roto es cómo se rompe más."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    rota = cfg.PAPERS / "2020rota.md"
    rota.write_text("---\nbibcode: [sin cerrar\npdf_source: 'prosa'\n---\n\ntexto\n",
                    encoding="utf-8")
    antes = rota.read_text(encoding="utf-8")
    assert mn.migrate_all_source_fields() == (0, [])
    assert rota.read_text(encoding="utf-8") == antes


def test_migrar_source_fields_no_toca_lo_valido(toy_vault):
    """`eprint`, `ads`, `publisher`, `web` y la ausencia son todos valores legítimos: un migrador
    que reescribe lo válido es un migrador que hay que revisar entero."""
    _paper_con_source(toy_vault, "2020ok", pdf_source="eprint", fulltext_source="ocr")
    _paper_con_source(toy_vault, "2021sin", pdf_source="null")
    assert mn.migrate_all_source_fields() == (0, [])


def test_migrar_source_fields_no_escribe_si_rompe_el_yaml(toy_vault, capsys, monkeypatch):
    """#244 — una operación no puede dejar la nota PEOR de lo que la encontró: si el frontmatter
    resultante dejó de parsear, no se escribe."""
    f = _paper_con_source(toy_vault, "2020roto", pdf_source="'prosa suelta'")
    antes = f.read_text(encoding="utf-8")
    monkeypatch.setattr(cfg, "split_fm", lambda t: {} if "pdf_source: null" in t
                        else {"bibcode": "2020roto", "pdf_source": "prosa suelta"})
    assert mn.migrate_all_source_fields() == (0, [])
    assert f.read_text(encoding="utf-8") == antes
    assert "NO se escribe" in capsys.readouterr().out


# ── #304 · `stamp_pdf`: el gemelo que faltaba de `stamp_fulltext` ────────────
def _nota_304(stem, **fm):
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    campos = "\n".join(f"{k}: {v}" for k, v in fm.items())
    f = cfg.PAPERS / f"{stem}.md"
    f.write_text(f"---\nbibcode: {stem}\ntitle: T\n{campos}\n---\n\n· ADS: `{stem}`\n\n"
                 f"## Abstract\n\nx\n", encoding="utf-8")
    return f


def _pdf_304(slug, stem):
    (cfg.PDFS / slug).mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / slug / f"{stem}.pdf").write_bytes(b"%PDF-1.4\n")


def test_stamp_pdf_linkea_el_PDF_que_aparecio_despues(toy_vault):
    """#304 — `pdf:` se escribía SÓLO al crear el stub, así que un PDF que aparece en disco después
    de la nota no se linkeaba nunca. No es un caso de borde: es el rescate manual de PDFs (que tiene
    su propio documento de referencia y su residuo declarado) y el cierre de un `pending`. Medido:
    4 de 4 rescates quedaron en `pdf: null`, con el lint imprimiendo la ruta exacta y ningún
    comando que la aplicara."""
    f = _nota_304("1999ISPL....6..145H", pdf="null")
    _pdf_304("ica_ruido", "1999ISPL....6..145H")
    assert mn.stamp_pdf(f, "1999ISPL....6..145H") is True
    fm = cfg.split_fm(f.read_text(encoding="utf-8"))
    assert fm["pdf"] == "../../raw/pdfs/ica_ruido/1999ISPL....6..145H.pdf"
    assert mn.stamp_pdf(f, "1999ISPL....6..145H") is False, "idempotente"


def test_stamp_pdf_no_des_estampa_ni_pisa_lo_que_resuelve(toy_vault):
    """Mismas dos propiedades que su gemelo: sin PDF en disco NO borra el campo (la ausencia la
    surface el lint), y un valor que todavía resuelve se queda — primer escritor gana, así que
    re-correr cualquier slug no repunta la nota (INV-23)."""
    f = _nota_304("2020sinpdf", pdf="../../raw/pdfs/ica/2020sinpdf.pdf")
    assert mn.stamp_pdf(f, "2020sinpdf") is False
    assert cfg.split_fm(f.read_text(encoding="utf-8"))["pdf"].endswith("ica/2020sinpdf.pdf")
    _pdf_304("ica", "2020sinpdf")
    _pdf_304("zeta", "2020sinpdf")
    assert mn.stamp_pdf(f, "2020sinpdf") is False, "el que ya está resuelve: no se repunta"
    # y el caso que la estabilidad protege (INV-23): la nota apunta al slug NO preferido y las dos
    # copias existen → se queda con la suya. Sin esto, el campo alterna según qué slug corrió.
    g = _nota_304("2003Comon", pdf="../../raw/pdfs/zeta/2003Comon.pdf")
    _pdf_304("zeta", "2003Comon")
    _pdf_304("ica", "2003Comon")
    assert mn.stamp_pdf(g, "2003Comon") is False
    assert cfg.split_fm(g.read_text(encoding="utf-8"))["pdf"].endswith("zeta/2003Comon.pdf")


def test_stamp_pdf_no_toca_una_nota_sin_frontmatter(toy_vault):
    """Sin frontmatter no hay dónde estampar, y adivinar dónde empieza sería inventar: la nota
    ilegible ya es un bloqueante del lint."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2020sinfm.md"
    f.write_text("no tengo frontmatter\n", encoding="utf-8")
    _pdf_304("ica", "2020sinfm")
    assert mn.stamp_pdf(f, "2020sinfm") is False
    assert f.read_text(encoding="utf-8") == "no tengo frontmatter\n"


def test_stamp_pdf_repunta_el_puntero_MUERTO(toy_vault):
    """El otro lado de #217: una nota que apunta a un archivo que no está afirma algo falso sobre el
    disco. Si el PDF existe bajo otro slug, el campo se repunta ahí."""
    f = _nota_304("2015MNRAS.446.3545D", pdf="../../raw/pdfs/borrado/2015MNRAS.446.3545D.pdf")
    _pdf_304("ica", "2015MNRAS.446.3545D")
    assert mn.stamp_pdf(f, "2015MNRAS.446.3545D") is True
    assert cfg.split_fm(f.read_text(encoding="utf-8"))["pdf"] == \
        "../../raw/pdfs/ica/2015MNRAS.446.3545D.pdf"


def test_stamp_pdf_elige_el_slug_con_precedencia_declarada(toy_vault):
    """Un paper de varios sujetos tiene su PDF bajo cada slug y la nota es una sola: sin regla
    declarada el campo se repunta al que corrió último. La misma que `artefacto_en_otro_slug`: el
    slug lexicográficamente menor."""
    f = _nota_304("2002Cardoso", pdf="null")
    _pdf_304("zeta", "2002Cardoso")
    _pdf_304("ica", "2002Cardoso")
    mn.stamp_pdf(f, "2002Cardoso")
    assert cfg.split_fm(f.read_text(encoding="utf-8"))["pdf"] == "../../raw/pdfs/ica/2002Cardoso.pdf"
    assert mn.best_pdf("no_existe") is None


def test_stamp_pdf_agrega_el_campo_si_la_nota_no_lo_trae(toy_vault):
    """Notas pre-contrato: el campo se inserta, no se pide que ya exista."""
    f = _nota_304("2018IEEEA...625336F")
    _pdf_304("ica_ruido", "2018IEEEA...625336F")
    assert mn.stamp_pdf(f, "2018IEEEA...625336F") is True
    assert cfg.split_fm(f.read_text(encoding="utf-8"))["pdf"].endswith("2018IEEEA...625336F.pdf")


def test_el_backfill_estampa_el_campo_y_DESPUES_el_link(toy_vault, capsys):
    """El drift que el lint reporta —«PDF en disco sin linkear», con la ruta exacta— ahora tiene
    comando: `--restamp-pdf-links` estampa primero el campo por verdad de disco y después el link
    que lo lee. Antes sólo podía QUITAR el link, porque leía un `pdf: null` que era falso."""
    f = _nota_304("2004ISPL...11..470D", pdf="null")
    _pdf_304("ica_ruido", "2004ISPL...11..470D")
    mn.restamp_pdf_links()
    texto = f.read_text(encoding="utf-8")
    assert "[📄 PDF](../../raw/pdfs/ica_ruido/2004ISPL...11..470D.pdf)" in texto
    assert "con `pdf:` estampado por verdad de disco" in capsys.readouterr().out


# ── #300 · el roll-up de CONCEPTO recupera las dos garantías de D-10 ─────────
def test_el_rollup_de_concepto_publica_los_dos_numeros_y_el_estado(toy_vault):
    """#300 — D-10 le puso al roll-up los DOS números y la columna `Estado` con un motivo
    enunciado («el defecto que evita es prometer 155 arriba de una síntesis de 8»), y las dos se
    aplicaron sólo a `stars/`. El defecto estaba VIVO en los conceptos: medido, un concepto cerrado
    y verificado anunciaba 89 papers arriba de una síntesis que cita 30, con 57 reclamados y sin
    leer — y esos 57 no son todos iguales (`sin extraer` vs `extraído, no sintetizado` vs `sin
    vista (declarado)`), que es exactamente lo que la columna transporta."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods",
                                         "query": "q"}})
    (cfg.CONCEPTS / "methods").mkdir(parents=True, exist_ok=True)
    (cfg.CONCEPTS / "methods" / "ica.md").write_text(
        "---\ntags: [concept]\n---\n\n# ICA\n\nLo sintetizado sale de [[2000Hyv]].\n",
        encoding="utf-8")
    for stem, extra in (("2000Hyv", {"methods": ["ICA"], "thesis_links": ["ica"]}),
                        ("2002Cardoso", {"thesis_links": ["ica"]}),
                        ("2004Davies", {"methods": ["ica"]})):
        campos = "\n".join(f"{k}: {v}" for k, v in extra.items())
        (cfg.PAPERS / f"{stem}.md").write_text(
            f"---\nbibcode: {stem}\ntitle: T\nyear: 2000\nrelevance: high\n{campos}\n---\n\n"
            f"## Abstract\n\nx\n", encoding="utf-8")
    filas = mn.concept_rollup_rows("ica")
    por_stem = {r["stem"]: r for r in filas}
    assert por_stem["2000Hyv"]["estado"] == mn.ESTADO_SINTETIZADO
    assert por_stem["2002Cardoso"]["estado"] == mn.ESTADO_SIN_EXTRAER, "reclamado y sin leer"
    assert por_stem["2004Davies"]["estado"] == mn.ESTADO_EXTRAIDO
    tabla = mn.concept_rollup_table(filas)
    assert "(3 · 1 sintetizados en este concepto)" in tabla, "la promesa que la tabla sostiene"
    assert "| Bibcode | Año | Entró por | Estado |" in tabla
    assert "| [[2002Cardoso]] | 2000 | thesis_links | sin extraer |" in tabla


# ── #306 · la salida de la función tiene que ser entrada válida para la función ──
def test_merge_lee_una_lista_flow_MULTILINEA(toy_vault, capsys):
    """#306 — `yaml.safe_dump(default_flow_style=True)` envuelve a los ~80 caracteres, así que la
    propia salida de `merge_frontmatter_list` dejaba de ser entrada válida para ella: el lector
    miraba UNA línea, `endswith("]")` daba False, y caía en el `else` que además reportaba «escalar
    con valor» sobre una lista flow perfectamente válida. Medido: 1 de 31 cosechas, y lo perdido
    fue `weighted PCA` — alias del tema, o sea el único `methods` con destino en el roll-up."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2023A&A...675A.187O.md"
    f.write_text(
        "---\nbibcode: 2023A&A...675A.187O\n"
        "methods: [wpca, pca, lbl, permutation-test, leave-p-out-cv, gls-periodogram,\n"
        "  quasi-periodic-gp, mcmc]\ntitle: T\n---\n\n## Abstract\n\nx\n", encoding="utf-8")
    assert mn.merge_frontmatter_list(f, "methods", ["weighted PCA", "pca"]) is True
    fm = cfg.split_fm(f.read_text(encoding="utf-8"))
    assert "weighted PCA" in fm["methods"] and "mcmc" in fm["methods"]
    assert len(fm["methods"]) == 9, "add-only: no se pierde ni se duplica nada"
    assert fm["title"] == "T", "el resto del frontmatter, intacto"
    assert "no pude linkear" not in capsys.readouterr().err


def test_merge_escribe_una_lista_flow_QUE_NO_ENVUELVE(toy_vault):
    """La otra mitad: si el escritor sigue envolviendo, la corrida siguiente vuelve al bug. La
    lista flow se emite en UNA línea (`width`), que es lo que hace que la salida sea entrada."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2020largo.md"
    f.write_text("---\nbibcode: 2020largo\nmethods: [a]\n---\n\n## Abstract\n\nx\n",
                 encoding="utf-8")
    mn.merge_frontmatter_list(f, "methods", [f"metodo-largo-numero-{i}" for i in range(12)])
    linea = next(ln for ln in f.read_text(encoding="utf-8").split("\n")
                 if ln.startswith("methods:"))
    assert linea.endswith("]"), "la lista flow no puede quedar partida en dos líneas"
    assert len(cfg.split_fm(f.read_text(encoding="utf-8"))["methods"]) == 13


# ── #311 · la extracción es cara, así que se versiona ───────────────────────
def test_migrar_extracciones_las_saca_de_build(toy_vault, capsys):
    """#311 — el framework decía dos cosas contradictorias del mismo directorio: la regla de oro
    del scratch («`build/` guarda lo REGENERABLE») y, para las extracciones, «no se regenera sin
    volver a pagar el paso más caro» (#228). Medido en un tema: 33 extracciones, 988 KB, ~4,9 M
    tokens de lectura de PDF, y `git ls-files build/` = **0** — no viajaban a ninguna máquina."""
    viejo = cfg.ROOT / "build" / "ica_ruido" / "extraccion"
    viejo.mkdir(parents=True, exist_ok=True)
    (viejo / "2002Cardoso.json").write_text('{"bibcode": "2002Cardoso"}', encoding="utf-8")
    n, choques = mn.migrate_all_extracciones()
    assert (n, choques) == (1, [])
    assert (cfg.EXTRACCION / "ica_ruido" / "2002Cardoso.json").exists()
    assert not (viejo / "2002Cardoso.json").exists(), "se MUEVE: dos copias es cosechar una vieja"


def test_migrar_extracciones_no_pisa_el_destino(toy_vault):
    """Un destino que ya existe no se sobreescribe: comparar dos extracciones del mismo bibcode es
    juicio, y pisarla sería tirar la que ya estaba versionada."""
    viejo = cfg.ROOT / "build" / "ica" / "extraccion"
    viejo.mkdir(parents=True, exist_ok=True)
    (viejo / "2000Hyv.json").write_text('{"bibcode": "2000Hyv", "v": "vieja"}', encoding="utf-8")
    (cfg.EXTRACCION / "ica").mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / "ica" / "2000Hyv.json").write_text('{"bibcode": "2000Hyv", "v": "nueva"}',
                                                         encoding="utf-8")
    n, choques = mn.migrate_all_extracciones()
    assert n == 0 and choques == ["ica/2000Hyv.json"]
    assert "nueva" in (cfg.EXTRACCION / "ica" / "2000Hyv.json").read_text(encoding="utf-8")
    assert (viejo / "2000Hyv.json").exists(), "la vieja queda para comparar a mano"


# ── #312 · `alcance`/`unidad_cita`: la config es la autoridad ────────────────
def test_restamp_alcance_re_sincroniza_la_nota(toy_vault, capsys):
    """#312 — los dos campos viajan de `sources[]` al stub y se congelan ahí, así que ampliar el
    `alcance` de un libro dejaba la nota **afirmando que ese material no entra mientras lo publica
    en su vista** (medido: 2 libros, 37 valores nuevos de capítulos declarados fuera de alcance). No
    deja al chequeo de completitud sin información: lo deja con información **falsa**."""
    write_yaml(cfg.THEMES_YAML, {"ica_ruido": {
        "title": "ICA ruidosa", "concept": "ica-ruido", "area": "methods", "source": "local-pdfs",
        "sources": [{"key": "2001HKO", "unidad_cita": "pagina",
                     "alcance": "caps. 6-9, 15, sec. 2.7, cap. 13, cap. 21"}]}})
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2001HKO.md"
    f.write_text("---\nbibcode: 2001HKO\nunidad_cita: pagina\nalcance: caps. 6-9 y 15\n---\n\n"
                 "## Abstract\n\nx\n", encoding="utf-8")
    mn.restamp_scope()
    fm = cfg.split_fm(f.read_text(encoding="utf-8"))
    assert fm["alcance"] == "caps. 6-9, 15, sec. 2.7, cap. 13, cap. 21"
    assert fm["unidad_cita"] == "pagina"
    assert mn.stamp_scope(f, "caps. 6-9, 15, sec. 2.7, cap. 13, cap. 21", "pagina") is False


def test_stamp_alcance_no_inventa_ni_borra(toy_vault):
    """La config es la autoridad **cuando declara**: sin `alcance` declarado la nota no se toca (el
    lint lo reporta), y el campo se agrega si la nota no lo traía."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2010CJ.md"
    f.write_text("---\nbibcode: 2010CJ\nalcance: caps. 1-2\n---\n\n## Abstract\n\nx\n",
                 encoding="utf-8")
    assert mn.stamp_scope(f, None, None) is False
    assert cfg.split_fm(f.read_text(encoding="utf-8"))["alcance"] == "caps. 1-2"
    g = cfg.PAPERS / "2020nuevo.md"
    g.write_text("---\nbibcode: 2020nuevo\n---\n\n## Abstract\n\nx\n", encoding="utf-8")
    assert mn.stamp_scope(g, "cap. 3", "pagina") is True
    assert cfg.split_fm(g.read_text(encoding="utf-8"))["alcance"] == "cap. 3"


def test_re_estampar_un_alcance_MULTILINEA_no_rompe_el_frontmatter(toy_vault, capsys):
    """#327 — el caso que es el 100 % de la población, y no por casualidad: un `alcance` dice qué
    capítulos de un libro entran, así que es largo **por definición**, así que el serializador lo
    envuelve, así que pisar sólo su primera línea dejaba la continuación huérfana bajo la clave
    siguiente. El frontmatter dejaba de parsear y la guarda de #244 —bien— rehusaba escribir:
    medido, **5 de 5** notas con `alcance`. La red funcionaba; lo que no funcionaba era #312.

    ⚠ El test viejo usaba un `alcance` corto, que cabe en una línea: un caso que no representa a su
    población, y por eso el gate no lo cazó."""
    largo = ("caps. 2-3 (formulación del problema y métodos de separación); 161 páginas, el resto "
             "es aplicación a audio y no entra")
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2010CJ.md"
    f.write_text("---\nbibcode: 2010CJ\nunidad_cita: pagina\n"
                 "alcance: caps. 2-3 (formulación del problema y métodos de separación); 161\n"
                 "  páginas, el resto es aplicación a audio y no entra\ntags: [paper]\n---\n\n"
                 "## Abstract\n\nx\n", encoding="utf-8")
    assert mn.stamp_scope(f, largo + " (ampliado: caps. 3 y 6)", "pagina") is True
    fm = cfg.split_fm(f.read_text(encoding="utf-8"))
    assert fm, "el frontmatter tiene que seguir parseando"
    assert fm["alcance"] == largo + " (ampliado: caps. 3 y 6)"
    assert fm["tags"] == ["paper"], "la clave siguiente no se comió la continuación huérfana"
    assert "⛔" not in capsys.readouterr().out


# ── #331 · el slug que no es de esta operación se REHÚSA, no revienta ─────────
def test_un_slug_de_TEMA_sin_flag_REHUSA_antes_de_arrancar(toy_vault, monkeypatch, capsys):
    """`write_star_note` llamaba a `star_by_slug` de rebote, así que `make_notes.py <tema>`
    imprimía «Generando notas para ica» y recién después moría con un `KeyError` crudo (rc 1)
    mandando definir en `stars.yaml` un slug que está bien definido en `themes.yaml` — un operador
    que sigue la instrucción agrega una estrella falsa a la config. D-43: se declara, no revienta;
    y se declara ANTES de arrancar la operación.

    @inv INV-141"""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods",
                                         "query": "independent component"}})
    assert run_main(monkeypatch, ["ica"]) == 2
    out = capsys.readouterr().out
    assert "Generando notas para" not in out, "no puede arrancar la operación y abortar a mitad"
    assert "themes.yaml" in out and "stars.yaml" in out, "el mensaje nombra las DOS configs"
    assert "`python scripts/make_notes.py ica --theme`" in out, "y da el comando que sí corre"


def test_un_slug_de_ESTRELLA_con_theme_REHUSA_igual(toy_vault, monkeypatch, capsys):
    """El gemelo en la otra dirección (`write_concept_note` → `theme_by_slug`): el mismo
    `KeyError`, la misma mentira sobre la causa, la misma negativa."""
    assert run_main(monkeypatch, ["test_star", "--theme"]) == 2
    out = capsys.readouterr().out
    assert "Generando notas para" not in out
    assert "`python scripts/make_notes.py test_star`" in out


def test_un_slug_que_no_esta_en_NINGUNA_config_nombra_las_dos(toy_vault, monkeypatch, capsys):
    """Sin ninguna entrada no hay comando alternativo que ofrecer: lo que sí hay que decir es
    dónde se define un sujeto, que es la mitad que el `KeyError` de `star_by_slug` acertaba a
    medias (nombraba una sola config)."""
    assert run_main(monkeypatch, ["no-existe"]) == 2
    out = capsys.readouterr().out
    assert "Generando notas para" not in out
    assert "stars.yaml" in out and "themes.yaml" in out
    assert "--theme" not in out, "no se inventa un flag para un slug que no está en themes.yaml"


# ── #344 · el migrador: la tabla se va al hermano ────────────────────────────────────────────────

_BLOQUE_344 = (
    "## Verificación de citas (2026-08-31)\n\n"
    "1 pares; 1 soportadas / 0 no-soportadas (0 resueltas) / 0 contradicen (0 resueltas) / "
    "0 no verificables — 0 con condición declarada.\n\n"
    "| # | Afirmación (extracto) | Fuente | Veredicto | Evidencia | Ancla | Hash fuente | Condición |\n"
    "|---|---|---|---|---|---|---|---|\n"
    "| 1 | x | [[2020citC...1..1C]] | soportada | «y» (p. 1) | aaaaaaaaaa | pdf:bbbbbbbbbb | — |\n\n"
    "**Inferencias declaradas** — 0 marcas en el cuerpo: ninguna.\n"
    "**Omisiones en transcripciones:** ninguna.\n"
    "**Condiciones perdidas** — 0 con condición: ninguna.\n")


def _nota_inline(toy_vault, stem="ica"):
    """Una nota con el schema VIEJO: la tabla adentro. Es lo que el migrador tiene que mover."""
    d = toy_vault.CONCEPTS / "methods"
    d.mkdir(parents=True, exist_ok=True)
    nota = d / f"{stem}.md"
    nota.write_text("---\ntags: [methods]\n---\n# ica\n\nAfirmación [[2020citC...1..1C]].\n\n"
                    + _BLOQUE_344 + "\n## Huecos\n\nnada\n", encoding="utf-8")
    return nota


def test_migrar_sidecar_mueve_la_tabla_y_deja_cabecera_subsecciones_y_puntero(toy_vault):
    """#344 — el 71-77 % de los bytes de una nota de entidad es la tabla, y NO es para el lector.
    Lo que se queda es lo que le sirve a quien copia la nota: la línea de cabecera (que es la
    afirmación), las tres sub-secciones de hallazgos y el puntero al hermano.  @inv INV-148"""
    import lib_blocks as lb
    nota = _nota_inline(toy_vault)
    assert mn.migrate_verif_sidecar(nota) == 3        # encabezado + separador + 1 fila
    texto = nota.read_text(encoding="utf-8")
    assert lb.inline_verif_rows(texto) == [], "la tabla se fue de la nota"
    assert "1 pares; 1 soportadas" in texto, "la cabecera se queda: es la afirmación que viaja"
    assert "Omisiones en transcripciones" in texto, "las tres sub-secciones se quedan"
    assert lb.verif_pointer(nota) in texto, "y el puntero al hermano"
    assert "## Huecos" in texto, "no se tocó nada fuera del bloque"
    hermano = cfg.verif_sidecar(nota)
    assert "| 1 | x | [[2020citC...1..1C]] | soportada |" in hermano.read_text(encoding="utf-8")
    assert lb.verif_rows(nota) is not None and len(lb.verif_rows(nota)) == 1


def test_migrar_sidecar_es_idempotente(toy_vault):
    """Red 6 — la segunda corrida no encuentra ninguna línea de tabla dentro de la nota y no
    escribe NADA: ni la nota ni el hermano cambian."""
    nota = _nota_inline(toy_vault)
    assert mn.migrate_verif_sidecar(nota) == 3
    antes_n = nota.read_text(encoding="utf-8")
    antes_h = cfg.verif_sidecar(nota).read_text(encoding="utf-8")
    assert mn.migrate_verif_sidecar(nota) == 0
    assert nota.read_text(encoding="utf-8") == antes_n
    assert cfg.verif_sidecar(nota).read_text(encoding="utf-8") == antes_h


def test_migrar_sidecar_no_re_renderiza_la_tabla(toy_vault):
    """⛔ La tabla se mueve VERBATIM. Re-renderizarla exigiría que las filas parseen, y la nota que
    más necesita migrar es justo la de plantilla vieja; además mover byte a byte deja intactos los
    anclas y los hashes, que es la propiedad que #344 promete."""
    nota = _nota_inline(toy_vault)
    original = [l for l in nota.read_text(encoding="utf-8").split("\n") if l.startswith("|")]
    mn.migrate_verif_sidecar(nota)
    hermano = cfg.verif_sidecar(nota).read_text(encoding="utf-8").split("\n")
    assert [l for l in hermano if l.startswith("|")] == original


def test_migrar_sidecar_no_toca_una_nota_sin_bloque(toy_vault):
    """Una nota sin bloque de verificación no se reescribe ni estrena hermano."""
    d = toy_vault.CONCEPTS / "methods"
    d.mkdir(parents=True, exist_ok=True)
    nota = d / "sin.md"
    nota.write_text("---\ntags: [methods]\n---\n# sin\n\nProsa.\n", encoding="utf-8")
    antes = nota.read_text(encoding="utf-8")
    assert mn.migrate_verif_sidecar(nota) == 0
    assert nota.read_text(encoding="utf-8") == antes
    assert not cfg.verif_sidecar(nota).exists()


def test_migrar_sidecar_backfill_recorre_la_boveda_y_saltea_los_hermanos(toy_vault, capsys):
    """El backfill nombra cada nota tocada, y NO se barre a sí mismo: un hermano no es una nota, así
    que pasarlo por el migrador crearía `ica.verif.verif.md`."""
    nota = _nota_inline(toy_vault)
    assert mn.migrate_all_verif_sidecar() == 0
    salida = capsys.readouterr().out
    assert "ica.md" in salida and "3 línea(s)" in salida
    assert mn.migrate_all_verif_sidecar() == 0
    assert "#344: 0 línea(s)" in capsys.readouterr().out
    assert not cfg.verif_sidecar(cfg.verif_sidecar(nota)).exists()


def test_rename_paper_se_lleva_el_hermano_de_verificacion(toy_vault):
    """#344/D-19 — el renombre preprint→publicado mueve la nota y sus artefactos; si deja el hermano
    atrás, queda un rastro de auditoría huérfano (bloqueante) y la nota nueva sin su tabla."""
    mk_note(cfg.PAPERS, "2020arXiv", {"bibcode": "2020arXiv", "tags": ["paper"],
                                      "stars": ["Estrella Test"]}, "# T\n")
    viejo = cfg.verif_sidecar(cfg.PAPERS / "2020arXiv.md")
    viejo.write_text("# Rastro\n\n## Verificación de citas\n\n| # |\n|---|\n", encoding="utf-8")
    mn.rename_paper("2020arXiv", "2021ApJ")
    assert cfg.verif_sidecar(cfg.PAPERS / "2021ApJ.md").exists()
    assert not viejo.exists()


def test_migrar_sidecar_rehusa_sobre_un_hermano_y_sobre_lo_que_no_existe(toy_vault):
    """Las dos guardas de entrada. Sobre un HERMANO produciría `ica.verif.verif.md` —un rastro del
    rastro— y sobre una ruta inexistente devolvería un 0 que se lee como «no había nada que
    migrar» habiendo mirado la nada."""
    nota = _nota_inline(toy_vault)
    mn.migrate_verif_sidecar(nota)
    hermano = cfg.verif_sidecar(nota)
    assert mn.migrate_verif_sidecar(hermano) == 0
    assert not cfg.verif_sidecar(hermano).exists()
    assert mn.migrate_verif_sidecar(toy_vault.CONCEPTS / "methods" / "no-existe.md") == 0


def test_rename_paper_no_pisa_un_hermano_que_ya_esta_en_el_destino(toy_vault):
    """#344 — el hermano del destino es un rastro de auditoría (caro, y no regenerable sin volver a
    correr el fan-out). Si ya hay uno bajo el bibcode nuevo, el renombre NO lo pisa."""
    mk_note(cfg.PAPERS, "2020arXiv", {"bibcode": "2020arXiv", "tags": ["paper"],
                                      "stars": ["Estrella Test"]}, "# T\n")
    viejo = cfg.verif_sidecar(cfg.PAPERS / "2020arXiv.md")
    viejo.write_text("VIEJO\n", encoding="utf-8")
    nuevo = cfg.verif_sidecar(cfg.PAPERS / "2021ApJ.md")
    nuevo.write_text("YA ESTABA\n", encoding="utf-8")
    mn.rename_paper("2020arXiv", "2021ApJ")
    assert nuevo.read_text(encoding="utf-8") == "YA ESTABA\n"


# ── #352 · la celda del índice: «sin valor» no es lo mismo que «sin columna» ──────────────────────

def test_la_celda_del_indice_marca_el_valor_ausente():
    """#352 — `_celda_idx` sobrevivía a la mutación: vaciarla entera (→ `return None`) publica la
    cadena `None` en el catálogo que #237 estampó justamente para que un agente lea RESULTADOS, y
    ningún test se ponía rojo. Lo que la función promete es que un campo ausente se vea como `—`:
    una celda vacía (`|  |`) es GFM legal y se lee igual que una columna que no está."""
    assert mn._celda_idx(None) == "—"
    assert mn._celda_idx("") == "—"
    assert mn._celda_idx([]) == "—"


def test_la_celda_del_indice_no_confunde_un_cero_con_un_hueco():
    """La otra mitad, y el motivo de que la guarda sea `v in (None, "", [])` y no `not v`: un `0`
    está PRESENTE. Con `not v` el índice publicaría `—` sobre un valor que la ficha sí trae, o sea
    afirmaría un hueco que no existe."""
    assert mn._celda_idx(0) == "0"
    assert mn._celda_idx(0.0) == "0.0"
    assert mn._celda_idx("K5V") == "K5V"


def test_la_fila_del_indice_publica_el_guion_y_no_la_cadena_None():
    """La misma garantía donde el lector la ve: la fila estampada de `## Estrellas`."""
    filas = mn._index_stars([("tau-cet", None, 34.0, 2)]).split("\n")
    assert filas[-1] == "| [[tau-cet]] | — | 34.0 | 2 |"


# ── #382 · el `alcance` de una entrada de `extra_core` llega a la nota y al prompt ───────────────

def test_extra_core_largo_estampa_alcance_en_el_stub_y_el_prompt_ramifica(toy_vault):
    """#382 — `unidad_cita`/`alcance` declarados en `extra_core` no los leía nadie: la tesis de 229
    páginas recibía el prompt de un paper normal. La nota los lleva (como el stub off-ADS los lleva
    desde `sources:`), y de ahí los lee `extraction_prompt._long_document` (#241)."""
    import extraction_prompt as ep
    seed_topic(extra_core=[{"bibcode": "2021PhDT.........6D", "via": "usuario", "motivo": "tesis",
                            "unidad_cita": "pagina", "alcance": "caps. 2-3"}])
    ads_json([rec("2021PhDT.........6D")], slug="gp")
    mn.write_paper_notes("gp", include_all=False, force=False, theme=True)
    fm = read_fm(toy_vault.PAPERS / "2021PhDT.........6D.md")
    assert fm["unidad_cita"] == "pagina" and fm["alcance"] == "caps. 2-3"
    assert ep._long_document("2021PhDT.........6D") == ("pagina", "caps. 2-3")
    # #312 también por este carril: la config es la autoridad y `--restamp-alcance` re-sincroniza
    seed_topic(extra_core=[{"bibcode": "2021PhDT.........6D", "via": "usuario", "motivo": "tesis",
                            "unidad_cita": "pagina", "alcance": "caps. 2-5"}])
    mn.restamp_scope()
    assert read_fm(toy_vault.PAPERS / "2021PhDT.........6D.md")["alcance"] == "caps. 2-5"


def test_restamp_alcance_saltea_los_items_malformados_de_sources(toy_vault, capsys):
    """#312/#382 — un item de `sources:` que no es un mapa, o sin `key`, no tumba el backfill ni
    estampa nada: lo reporta el lint (`bad_sources`), no este comando."""
    write_yaml(cfg.THEMES_YAML, {"t": {"title": "T", "concept": "t", "area": "methods",
                                       "source": "web",
                                       "sources": ["suelto", {"url": "https://x", "alcance": "cap. 1",
                                                              "unidad_cita": "pagina"}]}})
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    assert mn.restamp_scope() == 0
    assert "0 nota(s) re-sincronizadas" in capsys.readouterr().out
    assert not list(cfg.PAPERS.glob("*.md"))


def test_restamp_sources_meta_lleva_la_correccion_de_sources_al_stub(toy_vault, capsys):
    """Seguimiento de #353 (validación en la instancia): corregir `author`/`title`/`year`/`doi` en
    `sources:` no llegaba a la nota off-ADS —el stub no se pisa— y las cuatro notas se arreglaron a
    mano. La config es la autoridad (#312): se re-sincroniza por cirugía, sólo lo declarado."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "concept": "ica", "area": "methods",
                                         "source": "local-pdfs",
                                         "sources": [{"key": "2006Vrabie", "title": "Título real",
                                                      "author": "Vrabie", "year": 2006,
                                                      "doi": "10.1/real", "n_authors": 3,
                                                      "via": "usuario", "motivo": "m"},
                                                     {"key": "2099Sin", "via": "usuario", "motivo": "m"}]}})
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2006Vrabie.md"
    f.write_text("---\nbibcode: 2006Vrabie\ntitle: 'Título inventado'\nfirst_author: VanDerBaan\n"
                 "n_authors: 1\nyear: 2005\ndoi: 10.1/x\nno_vista:\n- sujeto: ica\n  motivo: m\n---\n\n"
                 "## Abstract\n\nx\n", encoding="utf-8")
    assert mn.restamp_sources_meta() == 0
    fm = read_fm(f)
    assert (fm["title"], fm["first_author"], fm["year"], fm["doi"], fm["n_authors"]) == \
        ("Título real", "Vrabie", 2006, "10.1/real", 3)
    assert fm["no_vista"] == [{"sujeto": "ica", "motivo": "m"}], "la curación no se toca"
    assert "1 nota(s)" in capsys.readouterr().out
    assert mn.restamp_sources_meta() == 0 and read_fm(f)["year"] == 2006      # idempotente
    assert "0 nota(s)" in capsys.readouterr().out, "sin diferencias no se toca ni se cuenta nada"
    # un item que NO declara el campo no borra lo que la nota tiene (la config manda cuando declara)
    g = cfg.PAPERS / "2099Sin.md"
    g.write_text("---\nbibcode: 2099Sin\ntitle: 'Lo que había'\nyear: 2099\n---\n\n## Abstract\n\nx\n",
                 encoding="utf-8")
    mn.restamp_sources_meta()
    assert read_fm(g)["title"] == "Lo que había" and read_fm(g)["year"] == 2099


def test_fix_key_no_promete_un_alias_que_no_escribe(toy_vault, capsys):
    """Validación en la instancia: el resumen de `--rename-paper --fix-key` decía «alias en
    `versions[]`» aunque con el flag no lo escribe (#355)."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2006VanDerBaan.md").write_text("---\nbibcode: 2006VanDerBaan\n---\n\n# x\n",
                                                  encoding="utf-8")
    mn.rename_paper("2006VanDerBaan", "2006Vrabie", fix_key=True)
    out = capsys.readouterr().out
    assert "alias en `versions[]`" not in out and "sin alias" in out, out


# ── Auditoría 2026-09-04 · tests rojos (xfail estricto) ─────────────────────────────────────────

# AUD-221 — cerrado en la pasada de fix de la auditoría 2026-09-04
def test_AUD221_migrar_DOS_source_fields_no_pierde_la_prosa_del_primero(toy_vault, capsys):
    """AUD-221 — el bucle decide por `fm.get("pending_motivo")` (dict viejo) y en la segunda vuelta
    filtra la línea `pending_motivo:` que acaba de escribir."""
    f = _paper_con_source(toy_vault, "2010DosCampos", pending_source="paywall",
                          pdf_source="'prosa A sobre el pdf'", fulltext_source="'prosa B sobre el txt'")
    mn.migrate_all_source_fields()
    txt = f.read_text(encoding="utf-8")
    assert "prosa A" in txt and "prosa B" in txt, txt


# AUD-223 — cerrado en la pasada de fix de la auditoría 2026-09-04
def test_AUD223_consolidar_REHUSA_si_la_vieja_tiene_una_vista_fechada(toy_vault):
    """AUD-223 — el proxy `methods` ya fue declarado insuficiente en `triage.drop_core`; acá una
    lectura cara del PDF (vista con fecha y prosa) se borra con la nota."""
    _nota_paper(toy_vault, "2026arXivVIEJO",
                extra="vistas:\n- sujeto: ica\n  tipo: theme\n  fecha: '2026-09-01'\n  fuente: pdf\n")
    p = toy_vault.PAPERS / "2026arXivVIEJO.md"
    p.write_text(p.read_text(encoding="utf-8") + "\n## Vista — ica\n\n**Aporte:** lectura cara.\n",
                 encoding="utf-8")
    _nota_paper(toy_vault, "2026RASTINUEVO")
    with pytest.raises(SystemExit):
        mn.rename_paper("2026arXivVIEJO", "2026RASTINUEVO")
    assert p.exists(), "no se borra una lectura que ocurrió"


# ── #269 · `--restamp-vista-stub`: la plantilla vieja del stub se re-estampa, la prosa no ────────

def test_restamp_vista_stub_reemplaza_SOLO_la_plantilla_vieja_y_es_idempotente(toy_vault):
    """AUD-288 + #398: el migrador prueba las tres cosas que su `help` promete, sobre las DOS
    plantillas legacy —la de #269 (citar por nº de línea) y la vigente hasta 1.211.0—: las dos son
    un stub y las dos pasan a la línea de estado; una vista con prosa redactada NO se toca (sus
    anclas cuelgan del texto exacto); y correrlo dos veces no cambia nada."""
    vieja = mn._legacy_vista_block("gp", True).replace(mn._BULLET_ANOTACION, mn._BULLET_ANOTACION_VIEJO)
    assert "nº de línea" in vieja and vieja != mn._legacy_vista_block("gp", True)
    stub = mk_note(toy_vault.PAPERS, "2020stubA...1A",
                   {"tags": ["paper"], "vistas": [{"sujeto": "gp", "tipo": "theme"}]},
                   "## Abstract\n\nx\n\n" + vieja)
    stub2 = mk_note(toy_vault.PAPERS, "2020stubC...1C",
                    {"tags": ["paper"], "vistas": [{"sujeto": "gp", "tipo": "theme"}]},
                    "## Abstract\n\nx\n\n" + mn._legacy_vista_block("gp", True))
    prosa = mk_note(toy_vault.PAPERS, "2020prosB...1B",
                    {"tags": ["paper"], "vistas": [{"sujeto": "gp", "tipo": "theme"}]},
                    "## Vista — gp\n- **Aporte al tema:** el kernel cuasi-periódico [[2020stubA...1A]]\n")
    antes_prosa = prosa.read_text(encoding="utf-8")
    assert mn.restamp_vista_stub() == 0
    for f in (stub, stub2):
        despues = f.read_text(encoding="utf-8")
        assert "_Reclamado por `gp`; sin leer desde este sujeto._" in despues, despues
        assert "nº de línea" not in despues and cfg.REGLA_LOCALIZADOR not in despues
        assert "## Abstract" in despues, "la cirugía es sobre la sección, no sobre la nota"
    assert prosa.read_text(encoding="utf-8") == antes_prosa
    despues = stub.read_text(encoding="utf-8")
    assert mn.restamp_vista_stub() == 0
    assert stub.read_text(encoding="utf-8") == despues, "no es idempotente"


# ── #395 · `--restamp-lente`: la lente y las líneas de eje, por verdad de la extracción ──────────

def _nota_y_extraccion(vista: dict, cuerpo: str, data: dict):
    """Una nota de paper con su `vistas[]` y el JSON versionado que la produjo (#311)."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2020lente..1..1L.md"
    f.write_text("---\nbibcode: 2020lente..1..1L\ntags: [paper]\nvistas:\n"
                 + yaml.safe_dump([vista], allow_unicode=True, sort_keys=False,
                                  default_flow_style=False)
                 + "---\n\n# p\n\n" + cuerpo, encoding="utf-8")
    d = cfg.EXTRACCION / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2020lente..1..1L.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return f


_CUERPO_UN_EJE = "## Vista — Estrella Test\n\n**Ejes:**\n\n- **rv:** reporta K\n\n**Aporte:** algo\n"


def test_restamp_lente_toma_la_lente_DECLARADA_por_la_extraccion(toy_vault, capsys):
    """#395a — la lente estampada eran los ejes vigentes AL COSECHAR, que es otra pregunta: medido,
    209 slots declarando tres facetas que la instancia agregó a `objective.yaml` **después** de esas
    lecturas. El migrador la corrige por verdad del artefacto versionado."""
    f = _nota_y_extraccion(
        {"sujeto": "Estrella Test", "tipo": "star", "fecha": "2026-08-30",
         "lente": ["rv", "ml", "simulation"]},                     # la lente de HOY, no la preguntada
        _CUERPO_UN_EJE,
        {"bibcode": "2020lente..1..1L", "vista": {"sujeto": "Estrella Test", "tipo": "star"},
         "lente": ["rv", "activity"], "ejes": {"rv": "reporta K", "activity": ""}})
    mn.restamp_lens()
    v = cfg.split_fm(f.read_text(encoding="utf-8"))["vistas"][0]
    assert list(v["lente"]) == ["rv", "activity"], v["lente"]
    assert v["fecha"] == "2026-08-30", "el resto de la vista no se toca"
    salida = capsys.readouterr().out
    assert "COTA INFERIOR" not in salida, "la lente estaba DECLARADA: no se reconstruyó de las claves"
    mn.restamp_lens()
    assert "0 vista(s) con `lente` re-estampada" in capsys.readouterr().out, "idempotente"


def test_restamp_lente_sin_lente_en_el_json_usa_las_claves_y_lo_DECLARA(toy_vault, capsys):
    """La extracción PRE-#395 no trae `lente:`, y ahí la mejor fuente son las CLAVES de `ejes` —lo
    que el prompt sembró—. Es una **cota inferior** y se dice: un eje que el extractor omitió no se
    recupera del disco. Callarlo dejaría al operador leyendo una lente reconstruida como si fuera
    la declarada, que es el defecto que este issue arregla en el otro sentido."""
    f = _nota_y_extraccion(
        {"sujeto": "Estrella Test", "tipo": "star", "fecha": "2026-08-30", "lente": ["ml"]},
        _CUERPO_UN_EJE,
        {"bibcode": "2020lente..1..1L", "vista": {"sujeto": "Estrella Test", "tipo": "star"},
         "ejes": {"rv": "reporta K", "activity": ""}})
    mn.restamp_lens()
    assert list(cfg.split_fm(f.read_text(encoding="utf-8"))["vistas"][0]["lente"]) == ["rv", "activity"]
    assert "COTA INFERIOR" in capsys.readouterr().out


def test_restamp_lente_backfillea_el_eje_preguntado_y_VACIO(toy_vault, capsys):
    """#395b — en 48 pares el JSON tiene la clave, vacía, y la prosa no trae su línea: ahí el
    silencio SÍ es indistinguible de «nunca se preguntó», que es lo que #270 existe para evitar. El
    cosechador las escribe desde #270; las vistas viejas no las tienen.

    ⛔ Add-only: el eje que la nota ya contesta no se reescribe — la prosa es del extractor."""
    f = _nota_y_extraccion(
        {"sujeto": "Estrella Test", "tipo": "star", "fecha": "2026-08-30",
         "lente": ["rv", "activity"]},
        _CUERPO_UN_EJE,
        {"bibcode": "2020lente..1..1L", "vista": {"sujeto": "Estrella Test", "tipo": "star"},
         "lente": ["rv", "activity"], "ejes": {"rv": "reporta K", "activity": ""}})
    mn.restamp_lens()
    cuerpo = f.read_text(encoding="utf-8")
    assert "- **activity:** _(sin datos)_" in cuerpo, cuerpo
    assert "- **rv:** reporta K" in cuerpo, "el eje contestado no se reescribe"
    assert cuerpo.index("- **activity:**") < cuerpo.index("**Aporte:**"), \
        "la línea va DENTRO del bloque de ejes, no al final de la sección"
    antes = cuerpo
    mn.restamp_lens()
    assert f.read_text(encoding="utf-8") == antes, "idempotente"


def test_restamp_lente_sin_extraccion_en_disco_no_toca_la_vista_y_avisa(toy_vault, capsys):
    """Sin el artefacto no hay verdad contra la cual re-estampar: la vista queda como está y se
    NOMBRA. Reconstruirla desde la config sería volver a escribir la lente equivocada."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2020lente..1..1L.md"
    f.write_text("---\nbibcode: 2020lente..1..1L\ntags: [paper]\n"
                 "vistas:\n- sujeto: Estrella Test\n  tipo: star\n  fecha: '2026-08-30'\n"
                 "  lente: [ml]\n---\n\n# p\n\n" + _CUERPO_UN_EJE, encoding="utf-8")
    mn.restamp_lens()
    assert list(cfg.split_fm(f.read_text(encoding="utf-8"))["vistas"][0]["lente"]) == ["ml"]
    assert "sin extracción en disco" in capsys.readouterr().out


def test_restamp_lente_backfillea_la_vista_QUE_ES_y_no_la_de_al_lado(toy_vault, capsys):
    """#395b — con dos lecturas en la misma nota, el eje que falta va a la suya. Un escritor que no
    viera el límite de `### Lente — …` (o que tomara la primera vista que encuentra) pegaría el eje
    de una lente en la sub-sección de la otra, que es el defecto de #395c del lado de la escritura."""
    f = _nota_y_extraccion(
        {"sujeto": "Estrella Test", "tipo": "star", "fecha": "2026-08-30", "lente": ["rv", "activity"]},
        "## Vista — Estrella Test\n\n**Ejes:**\n\n- **rv:** reporta K\n"
        "\n### Lente — ruido\n\n**Ejes:**\n\n- **blanqueo:** algo\n",
        {"bibcode": "2020lente..1..1L", "vista": {"sujeto": "Estrella Test", "tipo": "star"},
         "lente": ["rv", "activity"], "ejes": {"rv": "reporta K", "activity": ""}})
    mn.restamp_lens()
    cuerpo = f.read_text(encoding="utf-8")
    assert cuerpo.index("- **activity:**") < cuerpo.index("### Lente — ruido"), cuerpo
    assert cuerpo.count("- **activity:**") == 1


def test_restamp_lente_sin_bloque_de_ejes_no_lo_inventa(toy_vault, capsys):
    """Sin `**Ejes:**` el migrador no toca nada: crear la sección sería inventar la forma de una
    lectura que nadie renderizó — y el que decide qué contestó el extractor es el extractor."""
    f = _nota_y_extraccion(
        {"sujeto": "Estrella Test", "tipo": "star", "fecha": "2026-08-30", "lente": ["rv"]},
        "## Vista — Estrella Test\n\n**Aporte:** algo\n",
        {"bibcode": "2020lente..1..1L", "vista": {"sujeto": "Estrella Test", "tipo": "star"},
         "lente": ["rv"], "ejes": {"rv": "", "activity": ""}})
    antes = f.read_text(encoding="utf-8")
    mn.restamp_lens()
    assert "**Ejes:**" not in f.read_text(encoding="utf-8")
    assert cfg.solo_prosa(antes) == cfg.solo_prosa(f.read_text(encoding="utf-8"))


def test_restamp_lente_backfillea_la_SEGUNDA_lente_en_su_subseccion(toy_vault, capsys):
    """#395b+c juntos — el par `(sujeto, énfasis)` es lo que decide dónde se escribe. La vista que
    necesita el backfill acá es la de la SEGUNDA lente, y hay otra vista (otro sujeto) antes: un
    escritor que agarrara el primer span, o que sólo mirara el sujeto, pegaría el eje en la sección
    equivocada — y ahí el eje quedaría contestado para una lectura que no lo contestó."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2020lente..1..1L.md"
    f.write_text(
        "---\nbibcode: 2020lente..1..1L\ntags: [paper]\n"
        "vistas:\n"
        "- sujeto: Otra Estrella\n  tipo: star\n  fecha: '2026-08-29'\n  lente: [rv]\n"
        "- sujeto: Estrella Test\n  tipo: star\n  fecha: '2026-09-01'\n  enfasis: ruido\n"
        "  lente: [blanqueo, momentos]\n---\n\n# p\n\n"
        "## Vista — Otra Estrella\n\n**Ejes:**\n\n- **rv:** algo\n\n"
        "## Vista — Estrella Test\n\n### Lente — ruido\n\n**Ejes:**\n\n- **blanqueo:** algo\n",
        encoding="utf-8")
    d = cfg.EXTRACCION / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2020lente..1..1L.json").write_text(json.dumps(
        {"bibcode": "2020lente..1..1L", "vista": {"sujeto": "Otra Estrella", "tipo": "star"},
         "lente": ["rv"], "ejes": {"rv": "algo"}}), encoding="utf-8")
    (d / "2020lente..1..1L__ruido.json").write_text(json.dumps(
        {"bibcode": "2020lente..1..1L",
         "vista": {"sujeto": "Estrella Test", "tipo": "star", "enfasis": "ruido"},
         "lente": ["blanqueo", "momentos"], "ejes": {"blanqueo": "algo", "momentos": ""}}),
        encoding="utf-8")
    mn.restamp_lens()
    cuerpo = f.read_text(encoding="utf-8")
    assert cuerpo.index("- **momentos:**") > cuerpo.index("### Lente — ruido"), cuerpo
    otra = cuerpo[cuerpo.index("## Vista — Otra Estrella"):cuerpo.index("## Vista — Estrella Test")]
    assert "- **momentos:**" not in otra, otra


# ── #398 · la plantilla del stub bajo un sujeto declarado `no_vista` ─────────────────────────────

def _nota_no_vista(cuerpo: str, no_vista=True):
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    fm = {"bibcode": "2020nv....1..1N", "tags": ["paper"], "thesis_links": ["ica"],
          "vistas": [{"sujeto": "ica", "tipo": "theme"}]}
    if no_vista:
        fm["no_vista"] = [{"sujeto": "ica", "motivo": "no aporta al eje, entra por el roll-up"}]
    f = cfg.PAPERS / "2020nv....1..1N.md"
    f.write_text("---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n"
                 + cuerpo, encoding="utf-8")
    return f


def test_restamp_vista_stub_cambia_el_prompt_por_la_linea_de_no_vista(toy_vault, capsys):
    """#398 — el stub siembra la vista con las INSTRUCCIONES AL EXTRACTOR y nada las retira al
    declarar que ese sujeto no se va a leer: medido, 46 notas publicando el prompt bajo `## Vista —
    ica`, bajo un encabezado que la nota presenta como síntesis de un LLM (#247).

    ⛔ La entrada de `vistas[]` NO se toca: el frontmatter tiene que seguir diciendo que el sujeto
    reclama el paper (#256), y borrarla es la opción que el issue descarta a propósito."""
    f = _nota_no_vista("# p\n\n" + mn._legacy_vista_block("ica", True))
    mn.restamp_vista_stub()
    salida = f.read_text(encoding="utf-8")
    assert "_No leído desde `ica`: no aporta al eje, entra por el roll-up._" in salida, salida
    assert "Aporte al tema:" not in salida, "la plantilla se fue entera"
    assert cfg.split_fm(salida)["vistas"] == [{"sujeto": "ica", "tipo": "theme"}]
    antes = salida
    capsys.readouterr()
    mn.restamp_vista_stub()
    assert f.read_text(encoding="utf-8") == antes, "idempotente"
    assert "0 sección(es)" in capsys.readouterr().out, \
        "y el conteo lo dice: una sección ya en su forma vigente no se cuenta como tocada"


def test_restamp_vista_stub_NO_pisa_una_vista_con_prosa(toy_vault, capsys):
    """Sólo la sección que es la plantilla byte a byte: una vista con prosa real se deja como está
    —sus anclas cuelgan de ese texto exacto— aunque el sujeto figure en `no_vista`, que es un estado
    contradictorio y lo reporta el lint, no algo que un migrador resuelva pisando contenido."""
    f = _nota_no_vista("# p\n\n## Vista — ica\n\nEsto lo escribió alguien y vale.\n")
    mn.restamp_vista_stub()
    assert "Esto lo escribió alguien y vale." in f.read_text(encoding="utf-8")


def test_restamp_vista_stub_le_deja_al_sujeto_sin_leer_su_linea_de_reclamo(toy_vault, capsys):
    """Sin `no_vista` el reclamo sigue pendiente de lectura, así que la línea es la otra: la nota
    dice que el sujeto lo reclama y que nadie lo leyó desde ahí. Lo que NO puede seguir publicando
    es el prompt — el extractor recibe sus reglas de `extraction_prompt`, no del cuerpo de la nota."""
    f = _nota_no_vista("# p\n\n" + mn._legacy_vista_block("ica", True), no_vista=False)
    mn.restamp_vista_stub()
    salida = f.read_text(encoding="utf-8")
    assert "_Reclamado por `ica`; sin leer desde este sujeto._" in salida, salida
    assert "Aporte al tema:" not in salida


def test_view_stub_kind_acepta_la_plantilla_VIEJA(toy_vault):
    """Las dos plantillas son un stub: la nota que quedó con la de #269 no deja de serlo por no
    haber pasado por el migrador, y tratarla como prosa la dejaría publicando el prompt para
    siempre."""
    vieja = mn._legacy_vista_block("ica", True).replace(mn._BULLET_ANOTACION, mn._BULLET_ANOTACION_VIEJO)
    assert mn.view_stub_kind("# p\n\n" + vieja, "ica", True) == "plantilla"
    assert mn.view_stub_kind("# p\n\n" + mn._legacy_vista_block("ica", True), "ica", True) == "plantilla"
    # Los TRES estados, y por qué son tres: el lint reporta sólo `plantilla` —el prompt publicado
    # como contenido— y el migrador además reescribe una línea de estado cuyo motivo cambió.
    assert mn.view_stub_kind("# p\n\n" + mn.vista_block("ica"), "ica", True) == "estado"
    assert mn.view_stub_kind("# p\n\n" + mn.vista_block("ica", motivo="otro motivo"),
                             "ica", True) == "estado"
    assert mn.view_stub_kind("# p\n\n## Vista — ica\n\nprosa real\n", "ica", True) == ""
    assert mn.view_stub_kind("# p\n", "ica", True) == "", "sin sección no hay stub"


def test_restamp_vista_stub_saltea_la_entrada_malformada_sin_romperse(toy_vault, capsys):
    """`vistas` se lee CRUDO acá (no por `load_vistas`, que rechaza la forma inválida y aborta), así
    que una entrada que no es un mapa tiene que saltearse: el migrador no puede caerse sobre una
    nota que el lint ya está reportando como frontmatter con forma inválida."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2020nv....1..1N.md"
    f.write_text("---\nbibcode: 2020nv....1..1N\ntags: [paper]\n"
                 "vistas:\n- ica\n- {sujeto: ica, tipo: theme}\n"
                 "no_vista:\n- {sujeto: ica, motivo: entra por el roll-up}\n---\n\n"
                 "# p\n\n" + mn._legacy_vista_block("ica", True), encoding="utf-8")
    mn.restamp_vista_stub()
    assert "_No leído desde `ica`: entra por el roll-up._" in f.read_text(encoding="utf-8")
