"""lint: cada categoría detecta su caso sembrado; exit code separa bloqueante/WARN/backlog."""
import json

import pytest

import lib_config as cfg
import lint
from conftest import mk_note

MOJIBAKE = "ˆÿþ" * 150


def run_lint(capsys):
    rc = lint.main()
    return rc, capsys.readouterr().out


def link_from_index(toy_vault, *stems):
    """Evita huérfanos accidentales: index.md linkea las notas del escenario."""
    toy_vault.INDEX.write_text("".join(f"- [[{s}]]\n" for s in stems), encoding="utf-8")


def gt_planet(letter="b", mass=1.0, flag=None):
    """Planeta de GT consistente por construcción (K,P,e,M*=1 → m·sini ≈ 1 M⊕)."""
    return {"letter": letter, "P_days": 365.25, "K_ms": 0.0895, "e": 0.0,
            "mass_earth": mass, "status": "confirmed", "mass_flag": flag}


def write_gt(toy_vault, planets, mstar=1.0, host=None):
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(
        json.dumps({"slug": "test_star", "host": {"mass_msun": mstar, **(host or {})},
                    "planets": planets}),
        encoding="utf-8")


# ── bóveda vacía / reporte ───────────────────────────────────────────────────

def test_boveda_vacia_pasa(toy_vault, capsys):
    rc, out = run_lint(capsys)
    assert rc == 0
    assert (toy_vault.ROOT / "outputs").exists()      # reporte escrito en outputs/


# ── bloqueantes ──────────────────────────────────────────────────────────────

def test_wikilink_roto_bloquea(toy_vault, capsys):
    mk_note(toy_vault.CONCEPTS / "methods", "nota", {"tags": ["methods"]},
            "Cita a [[pagina-inexistente]].\n")
    link_from_index(toy_vault, "nota")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "## Wikilinks rotos (página faltante) (1)" in out
    assert "pagina-inexistente" in out


def test_frontmatter_roto_bloquea(toy_vault, capsys):
    """Regresión (hallazgo 4): YAML roto ya no evade el lint en silencio."""
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    (toy_vault.PAPERS / "2020rotoX..1..1X.md").write_text(
        "---\ntitle: RETRACTED: sin comillas\ntags:\n- paper\n---\ncuerpo\n", encoding="utf-8")
    (toy_vault.QUERIES / "sin-cierre.md").write_text("---\ntags: [query]\nsin cierre",
                                                     encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "## ⛔ Frontmatter no parseable (la nota evade los chequeos de su tipo) (2)" in out
    assert "YAML inválido" in out and "sin cierre `---`" in out


def test_prosa_plana_sin_frontmatter_es_legitima(toy_vault, capsys):
    toy_vault.INDEX.write_text("# Índice\n\nprosa plana sin frontmatter\n", encoding="utf-8")
    toy_vault.LOG.write_text("# Log\n", encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "## ⛔ Frontmatter no parseable (la nota evade los chequeos de su tipo) (0)" in out


def test_huerfanas_solo_conceptos_sueltos(toy_vault, capsys):
    mk_note(toy_vault.CONCEPTS / "methods", "suelta", {"tags": ["methods"]}, "sin links entrantes\n")
    mk_note(toy_vault.PAPERS, "2020papA...1..1A", {"tags": ["paper"]}, "")
    mk_note(toy_vault.STARS, "test_star", {"tags": ["star"]}, "")
    mk_note(toy_vault.MATRICES, "metodo-estrella", {"tags": ["matrix"]}, "")
    mk_note(toy_vault.RAW / "refs", "diseno", {}, "doc de diseño\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "## Notas huérfanas (sin links entrantes) (1)" in out
    assert "- suelta" in out


def test_paper_retractado_bloquea(toy_vault, capsys):
    mk_note(toy_vault.PAPERS, "2020retR...1..1R",
            {"tags": ["paper"], "retracted": True,
             "retraction": {"type": "retraction", "date": "2021-05-01"}}, "")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "RETRACTADOS" in out and "retraction (2021-05-01)" in out


def test_paper_con_correccion_es_backlog_no_bloquea(toy_vault, capsys):
    """#52: erratum/corrigendum/EoC se surface (un corrigendum cambia justo el valor extraído)
    pero NO bloquea — el paper sigue siendo citable, a diferencia de una retracción."""
    mk_note(toy_vault.PAPERS, "2020corC...1..1C",
            {"tags": ["paper"], "corrections": [
                {"type": "corrigendum", "notice_doi": "10.1/corr", "date": "2023-07-01"},
                {"type": "expression-of-concern", "notice_doi": None, "date": None}]}, "")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "corrección publicada (erratum/corrigendum/EoC)" in out
    assert "corrigendum (2023-07-01) → 10.1/corr" in out
    assert "expression-of-concern (s/f) → sin DOI del aviso" in out


def test_contradiccion_gt_ficha(toy_vault, capsys):
    write_gt(toy_vault, [gt_planet("b"), gt_planet("c")])
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["halpha"],
             "planets": [{"letter": "b"}]}, "**b** (P=365 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "ficha 1 planetas vs ground-truth 2" in out


# ── #75: extraído pero no sintetizado ────────────────────────────────────────

def paper_extraido(toy_vault, stem="2020ext....1E", **extra):
    """Nota de paper que YA pasó por la extracción cara (`methods` poblado)."""
    fm = {"tags": ["paper"], "relevance": "high", "methods": ["periodograma"],
          "thesis_links": [], "bearing": None}
    fm.update(extra)
    return mk_note(toy_vault.PAPERS, stem, fm, "")


def test_extraido_sin_llegar_a_ninguna_entidad_es_backlog(toy_vault, capsys):
    """El paso más caro de la cadena era el único sin red, y su modo de falla es OMISIÓN: nada
    quedaba mal escrito, simplemente el paper nunca llegó a la ficha. `verify-citations` tampoco lo
    ve — valida cada afirmación contra su fuente, no la cobertura del conjunto."""
    paper_extraido(toy_vault)
    mk_note(toy_vault.STARS, "test_star", {"tags": ["star"], "P_rot_days": 34.0,
                                           "activity_indicators_expected": ["halpha"]}, "Síntesis.\n")
    rc, out = run_lint(capsys)
    assert rc == 0                                        # backlog: no bloquea
    assert "Extraído pero no sintetizado" in out
    assert "2020ext....1E" in out and "no está citado en ninguna ficha ni concepto" in out


def test_citado_en_la_ficha_no_es_hallazgo(toy_vault, capsys):
    paper_extraido(toy_vault)
    mk_note(toy_vault.STARS, "test_star", {"tags": ["star"], "P_rot_days": 34.0,
                                           "activity_indicators_expected": ["halpha"]},
            "La señal la arbitra [[2020ext....1E]].\n")
    rc, out = run_lint(capsys)
    assert "Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog) (0)" in out


def test_citado_en_un_concepto_tambien_cuenta(toy_vault, capsys):
    """"Llegó" es a cualquier nota de ENTIDAD: un paper de método puede aterrizar en el concepto y
    no en la ficha de la estrella, y eso es síntesis igual."""
    paper_extraido(toy_vault)
    mk_note(toy_vault.CONCEPTS / "methods", "periodograma", {"tags": ["methods"]},
            "Definido en [[2020ext....1E]].\n")
    link_from_index(toy_vault, "periodograma")
    rc, out = run_lint(capsys)
    assert "Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog) (0)" in out


def test_citado_solo_en_una_query_no_alcanza(toy_vault, capsys):
    """Una query es una respuesta puntual, no la síntesis durable de un sujeto: que el paper aparezca
    ahí no significa que haya llegado a la bóveda."""
    paper_extraido(toy_vault)
    mk_note(toy_vault.QUERIES, "una-pregunta", {"tags": ["query"]},
            "Respuesta con [[2020ext....1E]].\n")
    link_from_index(toy_vault, "una-pregunta")
    rc, out = run_lint(capsys)
    assert "Extraído pero no sintetizado" in out and "2020ext....1E" in out


def test_paper_sin_extraer_no_entra_en_esta_categoria(toy_vault, capsys):
    """La población son los YA extraídos. El core sin extraer tiene su propia categoría ("paper
    relevante sin methods"): reportarlo en las dos sería el mismo hallazgo dos veces."""
    mk_note(toy_vault.PAPERS, "2020raw....1R",
            {"tags": ["paper"], "relevance": "high", "methods": [], "thesis_links": []}, "")
    rc, out = run_lint(capsys)
    assert "paper relevante sin methods" in out
    assert "Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog) (0)" in out


def test_paper_no_core_no_entra(toy_vault, capsys):
    """Una nota escrita con `--all` (no-core) no tiene por qué aterrizar en ninguna síntesis."""
    paper_extraido(toy_vault, relevance="low")
    rc, out = run_lint(capsys)
    assert "Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog) (0)" in out


def test_no_sintetizado_con_motivo_cierra_el_hallazgo(toy_vault, capsys):
    """La escotilla que pide el issue: la regla de poda manda dejar lo tangencial fuera de la prosa,
    así que un extraído puede legítimamente no aterrizar — pero se declara, con su motivo."""
    paper_extraido(toy_vault, no_sintetizado="metodología RV genérica: no cambia cómo se lee ninguna señal")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog) (0)" in out


def test_no_sintetizado_sin_motivo_sigue_reportando(toy_vault, capsys):
    """Mismo criterio que el `--reason` obligatorio del triage: no curar en silencio. Una marca
    pelada cierra el hallazgo sin dejar el porqué, que es lo único no regenerable."""
    paper_extraido(toy_vault, no_sintetizado=True)
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "`no_sintetizado` sin motivo" in out and "2020ext....1E" in out


# ── #70: el frontmatter de stars/ es espejo puro de NEA ──────────────────────

def ficha_espejo(toy_vault, front=None, body="**b** (P=365 d)\n"):
    """Ficha que ESPEJA el `gt_planet` por defecto; los tests pisan sólo el campo que prueban.
    Crea también el paper citable, para que un `[[bibcode]]` en el cuerpo no sea link roto."""
    mk_note(toy_vault.PAPERS, "2019A....1A", {"tags": ["paper"], "relevance": "low"}, "")
    fm = {"tags": ["star"], "activity_indicators_expected": ["halpha"],
          "planets": [{"letter": "b", "P_days": 365.25, "K_ms": 0.0895, "e": 0.0,
                       "mass_earth": 1.0, "status": "confirmed"}]}
    fm.update(front or {})
    return mk_note(toy_vault.STARS, "test_star", fm, body)


def test_espejo_valor_que_nea_no_tiene_es_bloqueante(toy_vault, capsys):
    """El caso de #70: NEA no trae `st_rotp` (pasa seguido) y alguien completó el campo con el
    valor de un paper. Queda con el MISMO aspecto que un valor auditable de NEA y hasta ahora nada
    lo detectaba — el único chequeo comparaba el NÚMERO de planetas, nunca los valores."""
    write_gt(toy_vault, [gt_planet("b")])
    ficha_espejo(toy_vault, {"P_rot_days": 34.0}, "**b** (P=365 d) · P_rot 34 d [[2019A....1A]]\n")
    rc, out = run_lint(capsys)
    assert rc == 1                                       # bloqueante: rompe la capa auditable
    assert "`P_rot_days: 34.0` pero el ground-truth no tiene el valor" in out
    assert "dejalo null y poné el valor de literatura en el cuerpo" in out


def test_espejo_valor_que_contradice_a_nea_manda_a_disputes(toy_vault, capsys):
    """Distinto arreglo, distinto mensaje: acá NEA SÍ tiene el valor y la ficha dice otra cosa —
    si sale de un paper es una `disputes[]`, no una sobreescritura."""
    write_gt(toy_vault, [gt_planet("b")], host={"st_rotp_days": 34.0})
    ficha_espejo(toy_vault, {"P_rot_days": 20.0})
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "contradice el ground-truth (34.0)" in out and "`disputes[]`" in out


def test_espejo_nulls_y_formato_numerico_no_son_hallazgo(toy_vault, capsys):
    """Un null de NEA espejado como null es el estado CORRECTO (no un campo a completar), y 34 vs
    34.0 es formato de YAML/JSON, no discrepancia."""
    write_gt(toy_vault, [gt_planet("b")], host={"st_rotp_days": 34})
    ficha_espejo(toy_vault, {"P_rot_days": 34.0, "teff_K": None, "dist_pc": None})
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "Contradicciones ground-truth ↔ ficha (0)" in out


def test_espejo_cubre_los_parametros_de_cada_planeta(toy_vault, capsys):
    """La evidencia del issue nombra `planets[]`: en NEA `pl_rvamp` (K) y `pl_orbeccen` (e) faltan
    seguido, así que el rellenado con literatura es MÁS probable ahí que en el host."""
    write_gt(toy_vault, [{"letter": "b", "P_days": 365.25, "K_ms": None, "e": 0.0,
                          "mass_earth": 1.0, "status": "confirmed"}])
    ficha_espejo(toy_vault, {"planets": [{"letter": "b", "P_days": 365.25, "K_ms": 2.5,
                                          "e": 0.3, "mass_earth": 1.0, "status": "confirmed"}]})
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "`b.K_ms: 2.5` pero el ground-truth no tiene el valor" in out
    assert "`b.e: 0.3` contradice el ground-truth (0.0)" in out


def test_espejo_no_duplica_el_planeta_que_no_esta_en_nea(toy_vault, capsys):
    """Un planeta de más ya lo reporta el chequeo de cantidad; repetirlo campo por campo sería
    ruido sobre el mismo hallazgo."""
    write_gt(toy_vault, [gt_planet("b")])
    ficha_espejo(toy_vault, {"planets": [{"letter": "b", "P_days": 365.25, "K_ms": 0.0895,
                                          "e": 0.0, "mass_earth": 1.0, "status": "confirmed"},
                                         {"letter": "z", "P_days": 9.9, "K_ms": 3.0}]},
                 "**b** (P=365 d) y **z** (P=9.9 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "ficha 2 planetas vs ground-truth 1" in out
    assert "z.P_days" not in out and "z.K_ms" not in out


def test_p_rot_documentado_en_la_prosa_no_es_backlog(toy_vault, capsys):
    """#70 punto 4: `P_rot_days` nulo dejó de ser "campo incompleto" (no era accionable: NEA no lo
    tiene y completarlo es justo lo prohibido). Lo accionable es que el P_rot esté DOCUMENTADO en
    la prosa con su cita — si está, no hay nada que reportar."""
    write_gt(toy_vault, [gt_planet("b")])
    ficha_espejo(toy_vault, {"P_rot_days": None},
                 "**b** (P=365 d)\n\nEl período de rotación es 34 d [[2019A....1A]].\n")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "sin P_rot" not in out


def test_p_rot_ni_en_nea_ni_citado_sigue_siendo_backlog(toy_vault, capsys):
    write_gt(toy_vault, [gt_planet("b")])
    ficha_espejo(toy_vault, {"P_rot_days": None})
    rc, out = run_lint(capsys)
    assert rc == 0                                       # backlog, no bloquea
    assert "sin P_rot: NEA no lo trae y el cuerpo no documenta uno citado" in out


@pytest.mark.parametrize("linea,documentado", [
    ("P_rot = 34 d [[2019A....1A]]", True),
    ("El período de rotación es 34 d [[2019A....1A]]", True),
    ("The rotation period is 34 d [[2019A....1A]]", True),
    ("$P_{rot}$ ≈ 34 d, inferencia a partir del ciclo", True),      # lectura propia, marcada
    ("P_rot = 34 d", False),                                        # sin respaldo: no cuenta
    ("Nada que ver [[2019A....1A]]", False),                        # cita sin la afirmación
])
def test_prot_citado_regex(linea, documentado):
    assert bool(lint.PROT_CITED_RE.search(linea)) is documentado


def test_same_value_tolerancias():
    """Unitario del comparador: los números viajan por YAML y JSON y vuelven con otro tipo."""
    assert lint.same_value(34, 34.0) and lint.same_value(None, None)
    assert lint.same_value("G8V", " G8V ") and lint.same_value(0.0, 0.0)
    assert not lint.same_value(34.0, None) and not lint.same_value(None, 34.0)
    assert not lint.same_value(34.0, 20.0) and not lint.same_value("G8V", "K0V")
    assert lint.same_value(1e6, 1e6 + 0.5)               # tolerancia relativa
    assert not lint.same_value(1.0, 1.1)


def test_mirror_issues_sin_ground_truth_no_inventa():
    """Unitario: con un GT vacío y una ficha vacía no hay nada que reportar (una bóveda recién
    creada no puede empezar en rojo)."""
    assert lint.mirror_issues("x", {}, {}) == []
    assert lint.mirror_issues("x", {"planets": []}, {"host": {}, "planets": []}) == []


def test_masa_inconsistente(toy_vault, capsys):
    write_gt(toy_vault, [gt_planet("b", mass=300.0),          # 300 M⊕ vs implícita ~1
                         gt_planet("c", flag="best-mass espuria")])
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "## Ground-truth: masa inconsistente con m·sini (K,P,e,M*) (2)" in out
    assert "m·sini implícita" in out and "best-mass espuria" in out


def test_masa_consistente_no_flaggea(toy_vault, capsys):
    write_gt(toy_vault, [gt_planet("b", mass=1.05)])
    rc, out = run_lint(capsys)
    assert rc == 0


def test_thesis_link_colgante(toy_vault, capsys):
    mk_note(toy_vault.PAPERS, "2020papA...1..1A",
            {"tags": ["paper"], "thesis_links": ["concepto-inexistente"], "bearing": "supports"}, "")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "## thesis_links sin página destino (1)" in out
    mk_note(toy_vault.CONCEPTS / "methods", "concepto-inexistente", {"tags": ["methods"]},
            "ahora existe [[2020papA...1..1A]]\n")
    link_from_index(toy_vault, "concepto-inexistente")
    rc, out = run_lint(capsys)
    assert "## thesis_links sin página destino (0)" in out


def test_dispute_ref_colgante(toy_vault, capsys):
    star_fm = {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
               "planets": [{"letter": "b",
                            "disputes": [{"field": "existence", "ref": "2020disD...1..1D",
                                          "note": "no la ve"}]}]}
    mk_note(toy_vault.STARS, "test_star", star_fm, "**b** (P=1 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "## disputes[].ref sin paper destino (1)" in out
    # la ref existe pero NO es nota de paper → sigue colgante
    mk_note(toy_vault.QUERIES, "2020disD...1..1D", {"tags": ["query"]}, "")
    link_from_index(toy_vault, "2020disD...1..1D")
    rc, out = run_lint(capsys)
    assert "## disputes[].ref sin paper destino (1)" in out


def test_dispute_ref_con_paper_ok(toy_vault, capsys):
    star_fm = {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
               "planets": [{"letter": "b",
                            "disputes": [{"field": "K", "ref": "2020disD...1..1D",
                                          "alt": 1.4, "note": "K distinto"}]}]}
    mk_note(toy_vault.STARS, "test_star", star_fm, "**b** (P=1 d)\n")
    mk_note(toy_vault.PAPERS, "2020disD...1..1D", {"tags": ["paper"]}, "")
    rc, out = run_lint(capsys)
    assert "## disputes[].ref sin paper destino (0)" in out


# ── WARN (no bloquean) ───────────────────────────────────────────────────────

def test_fuga_de_implementacion_warn(toy_vault, capsys):
    mk_note(toy_vault.CONCEPTS / "methods", "nota",
            {"tags": ["methods"]},
            "La perilla del contraste se ajusta así.\n"
            "> perilla mencionada en blockquote meta: exenta\n")
    link_from_index(toy_vault, "nota")
    rc, out = run_lint(capsys)
    assert rc == 0                                   # WARN no bloquea
    assert "Fuga de implementación (código no bibliográfico) → frontera dura (WARN, revisar a mano) (1)" in out
    assert "perilla" in out


def test_fuga_numera_lineas_como_grep(toy_vault, capsys):
    """#29: la línea reportada es la de `grep -n` (convención fija del corpus) — un form feed
    colado en la nota no corre la numeración (splitlines() lo contaría como salto extra)."""
    mk_note(toy_vault.CONCEPTS / "methods", "nota", {"tags": ["methods"]},
            "línea uno\ncon un form feed \x0c en el medio\nla perilla en la línea 3\n")
    link_from_index(toy_vault, "nota")
    rc, out = run_lint(capsys)
    # numeración relativa al cuerpo post-frontmatter: L1 vacía (el \n tras el `---`), L2 "línea
    # uno", L3 la del form feed, L4 la perilla. Con splitlines() el \x0c partiría L3 en dos y la
    # perilla se correría a L5.
    assert "L4 [perilla" in out


def test_objetivo_default_warn(toy_vault, capsys):
    """Guard de config: objective.yaml sin instanciar (name = default del template) → WARN."""
    import lib_config as cfg
    from conftest import write_yaml
    obj = dict(cfg.load_objective())
    obj["name"] = cfg.DEFAULT_OBJECTIVE_NAME
    write_yaml(cfg.OBJECTIVE_YAML, obj)
    rc, out = run_lint(capsys)
    assert rc == 0                                   # WARN, no bloquea
    assert "objective.name sigue siendo el placeholder del template" in out
    assert "`setup`" in out


def test_objetivo_propio_sin_warn(toy_vault, capsys):
    rc, out = run_lint(capsys)                       # el toy objective ya tiene name propio
    assert "Objetivo sin instanciar (WARN — objective.yaml sigue en el placeholder del template) (0)" in out


def test_area_no_declarada_warn(toy_vault, capsys):
    mk_note(toy_vault.CONCEPTS / "zzz", "nota", {"tags": ["zzz"]}, "área typo\n")
    link_from_index(toy_vault, "nota")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "concepts/zzz/" in out and "¿typo o área nueva sin declarar?" in out


def test_obsidian_en_raiz_warn(toy_vault, capsys):
    """Guard de operación: .obsidian/ en la raíz del repo (vault abierto ahí por error) → WARN."""
    (toy_vault.ROOT / ".obsidian").mkdir()
    rc, out = run_lint(capsys)
    assert rc == 0                                   # WARN, no bloquea
    assert "Obsidian fue abierto en la raíz en vez de `vault/`" in out


def test_sin_obsidian_en_raiz_sin_warn(toy_vault, capsys):
    rc, out = run_lint(capsys)
    assert "Obsidian en la raíz del repo (WARN — la bóveda se abre en vault/) (0)" in out


def test_pdf_drift_ambas_direcciones(toy_vault, capsys):
    # (a) PDF bajado pero frontmatter pdf: null
    pdf_dir = toy_vault.PDFS / "test_star"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / "2020drfA...1..1A.pdf").write_bytes(b"%PDF")
    mk_note(toy_vault.PAPERS, "2020drfA...1..1A", {"tags": ["paper"], "pdf": None}, "")
    # (b) frontmatter apunta a un PDF que no existe
    mk_note(toy_vault.PAPERS, "2020drfB...1..1B",
            {"tags": ["paper"], "pdf": "../../raw/pdfs/test_star/no-esta.pdf"}, "")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "PDF en disco sin linkear" in out
    assert "apunta a archivo inexistente" in out


PDF_LABEL = ("PDF ↔ disco / cuerpo (WARN — higiene: frontmatter `pdf` vs PDF bajado vs "
             "link de cabecera)")


def _nota_con_pdf(toy_vault, stem, cuerpo):
    """Nota de paper con el PDF en disco y el frontmatter apuntándolo; el cuerpo lo pone el test."""
    pdf_dir = toy_vault.PDFS / "test_star"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / f"{stem}.pdf").write_bytes(b"%PDF")
    rel = f"../../raw/pdfs/test_star/{stem}.pdf"
    mk_note(toy_vault.PAPERS, stem, {"tags": ["paper"], "pdf": rel}, cuerpo.format(rel=rel))
    return rel


def test_pdf_linkeado_correcto_sin_warn(toy_vault, capsys):
    """Nota sana: PDF en disco, frontmatter apuntándolo y cabecera con el link → 0 hallazgos."""
    _nota_con_pdf(toy_vault, "2020okC....1..1C",
                  "# T\n\n**Ana** (2020)\n· ADS: `2020okC....1..1C` · [📄 PDF]({rel})\n")
    rc, out = run_lint(capsys)
    assert f"{PDF_LABEL} (0)" in out


def test_cuerpo_sin_link_pdf_se_marca(toy_vault, capsys):
    """#48: el frontmatter está sano (el chequeo viejo no ve nada) pero la cabecera no tiene el
    link → WARN accionable, apuntando al backfill."""
    _nota_con_pdf(toy_vault, "2020nolD...1..1D",
                  "# T\n\n**Ana** (2020)\n· ADS: `2020nolD...1..1D`\n")
    rc, out = run_lint(capsys)
    assert rc == 0                                    # WARN, no bloquea
    assert "sin `[📄 PDF]` en el cuerpo" in out
    assert "--restamp-pdf-links" in out


def test_cabecera_fuera_del_contrato_se_marca(toy_vault, capsys):
    """#48, el caso que quedaba mudo: sin línea de cabecera reconocible, stamp_pdf_link saltea
    la nota → el lint la distingue del caso anterior (hay que normalizar la cabecera primero)."""
    _nota_con_pdf(toy_vault, "2012ApJ...753..122T",
                  "# T\n\nAna Pérez (2012), escrito a mano sin la línea de cabecera\n")
    rc, out = run_lint(capsys)
    assert "cabecera fuera del contrato de stamp_pdf_link" in out


def test_link_en_cuerpo_sin_pdf_vigente_se_marca(toy_vault, capsys):
    """Drift inverso: el cuerpo linkea un PDF que el frontmatter ya no tiene."""
    mk_note(toy_vault.PAPERS, "2020invE...1..1E", {"tags": ["paper"], "pdf": None},
            "# T\n\n**Ana** (2020)\n· ADS: `2020invE...1..1E` · "
            "[📄 PDF](../../raw/pdfs/test_star/2020invE...1..1E.pdf)\n")
    rc, out = run_lint(capsys)
    assert "sin PDF vigente en `pdf`" in out


def test_nota_sin_pdf_ni_link_sin_warn(toy_vault, capsys):
    """Paper sin PDF bajado: ni frontmatter ni cuerpo lo mencionan → nada que marcar."""
    mk_note(toy_vault.PAPERS, "2020nadF...1..1F", {"tags": ["paper"], "pdf": None},
            "# T\n\n**Ana** (2020)\n· ADS: `2020nadF...1..1F`\n")
    rc, out = run_lint(capsys)
    assert f"{PDF_LABEL} (0)" in out


def test_fuente_pendiente_listada(toy_vault, capsys):
    mk_note(toy_vault.PAPERS, "1999Paywall",
            {"tags": ["paper"], "pending_source": "paywall", "doi": "10.1/pw"}, "")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "Fuentes pendientes" in out
    assert "paywall — proveer la fuente; puntero: 10.1/pw" in out


def test_fulltext_ilegible(toy_vault, capsys):
    d = toy_vault.FULLTEXT / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2020badB...1..1B.txt").write_text(MOJIBAKE, encoding="utf-8")
    (d / "2020okC....1..1C.txt").write_text("texto perfectamente legible " * 20, encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "fulltext/test_star/2020badB...1..1B.txt" in out
    assert "2020okC....1..1C" not in out.split("Fulltext ilegible")[1].split("##")[0]


# ── precondiciones / backlog ─────────────────────────────────────────────────

def test_cita_sin_fulltext_no_verificable(toy_vault, capsys):
    mk_note(toy_vault.PAPERS, "2020citC...1..1C", {"tags": ["paper"]}, "")
    mk_note(toy_vault.QUERIES, "mi-query", {"tags": ["query"]},
            "Según [[2020citC...1..1C]] pasa X.\n")
    link_from_index(toy_vault, "mi-query")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "cita 2020citC...1..1C sin fulltext" in out
    d = toy_vault.FULLTEXT / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2020citC...1..1C.txt").write_text("texto legible del paper " * 20, encoding="utf-8")
    rc, out = run_lint(capsys)
    assert "Citas no verificables en query/concepto/hipótesis (sin fulltext) (0)" in out


def test_con_citas_pero_sin_bloque_verify(toy_vault, capsys):
    d = toy_vault.FULLTEXT / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2020citC...1..1C.txt").write_text("texto legible del paper " * 20, encoding="utf-8")
    mk_note(toy_vault.PAPERS, "2020citC...1..1C", {"tags": ["paper"]}, "")
    mk_note(toy_vault.CONCEPTS / "methods", "con-citas", {"tags": ["methods"]},
            "Afirmación citada [[2020citC...1..1C]].\n")
    link_from_index(toy_vault, "con-citas")
    rc, out = run_lint(capsys)
    assert "sin bloque de verify-citations" in out
    # con el bloque presente deja de listarse
    mk_note(toy_vault.CONCEPTS / "methods", "con-citas", {"tags": ["methods"]},
            "Afirmación citada [[2020citC...1..1C]].\n\n## Verificación de citas\nok\n")
    rc, out = run_lint(capsys)
    assert "## Sin verificar: query/concepto con citas pero sin bloque verify-citations (backlog) (0)" in out


def test_cobertura_concepto_sin_citas(toy_vault, capsys):
    mk_note(toy_vault.CONCEPTS / "methods", "sin-citas", {"tags": ["methods"]},
            "Afirma sin ninguna fuente.\n")
    link_from_index(toy_vault, "sin-citas")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "- sin-citas → sin citas [[bibcode]]" in out


def test_campos_incompletos(toy_vault, capsys):
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": None, "activity_indicators_expected": [],
             "planets": [{"letter": "b"}, {"letter": "c"}]},
            "Sólo **b** (P=20 d) se discute; c no aparece marcada.\n")
    mk_note(toy_vault.PAPERS, "2020papA...1..1A",
            {"tags": ["paper"], "relevance": "high", "methods": [],
             "thesis_links": ["algo"], "bearing": None}, "")
    mk_note(toy_vault.CONCEPTS / "methods", "algo", {"tags": ["methods"]}, "destino [[test_star]]\n")
    link_from_index(toy_vault, "algo")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "sin P_rot: NEA no lo trae y el cuerpo no documenta uno citado" in out
    assert "activity_indicators_expected vacío" in out
    assert "planeta c en frontmatter pero no discutido en prosa" in out
    assert "planeta b" not in out                     # b sí está discutida
    assert "paper relevante sin methods" in out
    assert "thesis_links sin bearing" in out


def test_prosa_reconoce_variantes_de_mencion(toy_vault, capsys):
    body = ("La señal **b** es sólida.\n\n| c | 49.3 |\n\n"
            "El valor $K_d$ es chico.\ne (P=100 d) sigue dudosa.\n")
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
             "planets": [{"letter": "b"}, {"letter": "c"}, {"letter": "d"}, {"letter": "e"}]},
            body)
    rc, out = run_lint(capsys)
    assert "no discutido en prosa" not in out


def test_registro_versionado_cubre_la_falta_de_build(toy_vault, capsys):
    """#51/#64: sin build/ local (post-clone, otra máquina, scratch limpiado) los chequeos de
    triage y truncamiento reportaban 0 SIN MIRAR NADA — un falso limpio. Ahora caen al registro
    versionado y reportan el snapshot CON su fecha, diciendo que no es el conteo vigente."""
    cfg.save_busqueda("au_mic", {"fecha": "2026-08-21", "query": "title:(x)", "rows": 400,
                                 "n_found": 410, "n_core": 198, "n_candidates": 42,
                                 "truncated": True})
    assert not (toy_vault.ROOT / "build" / "au_mic").exists()
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "42 candidato(s) sin juzgar según el registro del 2026-08-21" in out
    assert "no el conteo vigente" in out
    assert "corpus truncado según el registro del 2026-08-21" in out and "410" in out


def test_build_local_gana_sobre_el_registro(toy_vault, capsys):
    """Con build/ presente manda la verdad viva: el sujeto no se reporta dos veces."""
    cfg.save_busqueda("au_mic", {"fecha": "2026-08-01", "n_candidates": 99, "truncated": False})
    d = toy_vault.ROOT / "build" / "au_mic"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps(
        {"slug": "au_mic", "records": [],
         "candidates": [{"bibcode": "2020cand0..1..1C"}]}), encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "au_mic → 1 candidato(s) del chaining sin juzgar" in out
    assert "99 candidato(s)" not in out and "2026-08-01" not in out


def test_cabecera_no_estampable_surface_backlog(toy_vault, capsys):
    """#69: una ficha sin la línea del generador deja sin efecto a TODOS los estampadores de
    cabecera, y hasta ahora el no-op era silencioso. Backlog, no bloqueante: la nota es válida."""
    mk_note(toy_vault.STARS, "vieja", {"tags": ["star"], "P_rot_days": 1.0,
                                       "activity_indicators_expected": ["halpha"]},
            "# vieja\n\n> Prosa del LLM, sin la cabecera del template.\n")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "Cabecera no estampable" in out
    assert "vieja" in out and "--restamp-headers" in out


def test_cabecera_con_ancla_no_se_reporta(toy_vault, capsys):
    mk_note(toy_vault.STARS, "nueva", {"tags": ["star"], "P_rot_days": 1.0,
                                       "activity_indicators_expected": ["halpha"]},
            "# nueva\n\n> _Generado con Almagesto v1.9.0._\n")
    rc, out = run_lint(capsys)
    assert "## Cabecera no estampable" in out
    assert "nueva" not in out.split("## Cabecera no estampable")[1].split("##")[0]


def test_triage_pendiente_surface_backlog(toy_vault, capsys):
    """#55: candidatos del chaining sin juzgar → backlog visible. Antes el único recordatorio era
    el stdout de query_ads: un ingest podía cerrarse con lint en 0 y cientos de pendientes."""
    d = toy_vault.ROOT / "build" / "au_mic"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps(
        {"kind": "star", "slug": "au_mic", "records": [],
         "candidates": [{"bibcode": f"2020cand{i}..1..1C"} for i in range(4)]}), encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0                                     # backlog, no bloqueante
    assert "Triage pendiente" in out
    assert "au_mic → 4 candidato(s) del chaining sin juzgar" in out
    assert "2020cand0..1..1C" in out and "…" in out    # muestra los 3 primeros + elipsis
    assert "python scripts/triage.py au_mic" in out


def test_triage_sin_candidatos_no_reporta(toy_vault, capsys):
    """`candidates: []` (todos juzgados) o ads.json sin la clave (corpus de tema, --no-triage,
    ads.json viejo) → nada que reportar."""
    for slug, payload in (("sin_cands", {"slug": "sin_cands", "records": [], "candidates": []}),
                          ("sin_clave", {"slug": "sin_clave", "records": []})):
        d = toy_vault.ROOT / "build" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "ads.json").write_text(json.dumps(payload), encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "## Triage pendiente: candidatos del chaining sin juzgar (backlog) (0)" in out


def test_corpus_truncado_surface_backlog(toy_vault, capsys):
    """build/<slug>/ads.json con `truncated` seteado → el lint lo surface como backlog (no bloquea, #17)."""
    d = toy_vault.ROOT / "build" / "au_mic"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps(
        {"kind": "star", "slug": "au_mic", "truncated": {"num_found": 410, "rows": 400},
         "records": []}), encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0                                     # backlog, no bloqueante
    assert "Corpus truncado" in out and "au_mic" in out and "410" in out
    assert "segunda pasada" not in out                 # ads.json viejo (sin `recent`): no lo afirma


def test_corpus_truncado_reporta_la_segunda_pasada(toy_vault, capsys):
    """#79: con `recent` en la marca, el backlog dice qué parte del universo YA se cubrió — sin
    eso, "corpus truncado" se lee como "falta todo", y lo que falta es el medio, no la cola."""
    d = toy_vault.ROOT / "build" / "au_mic"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps(
        {"kind": "star", "slug": "au_mic",
         "truncated": {"num_found": 5000, "rows": 2000, "recent": 137}, "records": []}),
        encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "+ 137 de la segunda pasada por fecha" in out and "falta el medio" in out


def test_rescate_glifo_truncado_surface_backlog(toy_vault, capsys):
    """#43: `truncated_glyph` en ads.json (el superset del rescate por glifo se cortó por citas
    ANTES del filtro client-side) → backlog, distinguible del truncamiento de la query directa."""
    d = toy_vault.ROOT / "build" / "eps_eridani"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps(
        {"kind": "star", "slug": "eps_eridani", "truncated": None,
         "truncated_glyph": [{"letter": "epsilon", "constellations": ["Eri", "Eridani"],
                              "num_found": 2342, "rows": 2000}],
         "records": []}), encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0                                     # backlog, no bloqueante
    assert "rescate por glifo incompleto" in out and "eps_eridani" in out
    assert "Eri/Eridani" in out and "2342" in out


def test_corpus_no_truncado_no_reporta(toy_vault, capsys):
    """ads.json con `truncated: null` (no truncó) o sin la clave (ads.json viejo) → nada que reportar."""
    for slug, payload in (("hd40307", {"slug": "hd40307", "truncated": None, "records": []}),
                          ("tau_ceti", {"slug": "tau_ceti", "records": []})):   # sin la clave (legacy)
        d = toy_vault.ROOT / "build" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "ads.json").write_text(json.dumps(payload), encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "Corpus truncado: la query directa trajo menos de lo que ADS reporta (backlog) (0)" in out


# ── verificación stale (#56) ─────────────────────────────────────────────────

def test_verify_block_parsea_encabezado():
    """El bloque se reconoce por su encabezado y la fecha sale de ahí (convención del skill)."""
    assert lint.verify_block("prosa\n") == (False, None)
    assert lint.verify_block("## Verificación de citas (2026-08-19)\n| a | b |\n") == (True, "2026-08-19")
    assert lint.verify_block("## Verificacion de citas\nok\n") == (True, None)   # sin tilde, sin fecha
    # una fecha en la prosa no es la del bloque: sólo cuenta la del encabezado
    assert lint.verify_block("El 2020-01-01 pasó algo.\n## Verificación de citas\nok\n") == (True, None)
    # varios bloques (pasadas sucesivas): vigencia = la más reciente, no la primera
    assert lint.verify_block("## Verificación de citas (2026-01-05)\na\n"
                             "## Verificación de citas (2026-03-02)\nb\n"
                             "## Verificación de citas (2026-02-01)\nc\n") == (True, "2026-03-02")
    # con fecha en alguno alcanza: no se marca "sin fecha"
    assert lint.verify_block("## Verificación de citas\na\n"
                             "## Verificación de citas (2026-02-01)\nb\n") == (True, "2026-02-01")


SIN_STALE = "Verificación stale: la nota se editó después de su último verify-citations (backlog) (0)"


def _git(root, *args, fecha=None):
    import os
    import subprocess
    env = dict(os.environ)
    if fecha:                                   # %cs sale del committer date
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = f"{fecha}T12:00:00"
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                           "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, env=env)


def _nota_verif(toy_vault, stem, cuerpo):
    """Nota-concepto con bloque de verificación + el paper que cita (para no romper el wikilink)."""
    mk_note(toy_vault.PAPERS, "2020citC...1..1C", {"tags": ["paper"]}, "")
    mk_note(toy_vault.CONCEPTS / "methods", stem, {"tags": ["methods"]}, cuerpo)
    link_from_index(toy_vault, stem)


def _repo_con_nota(toy_vault, cuerpo, fecha="2020-01-01"):
    """Repo git de juguete con la nota ya committeada en `fecha` (para separar la rama
    `git log` de la rama working-tree). False si no hay git → el test se saltea."""
    _nota_verif(toy_vault, "nota-verif", cuerpo)
    if _git(toy_vault.ROOT, "init", "-q").returncode != 0:
        return False
    _git(toy_vault.ROOT, "add", "-A")
    return _git(toy_vault.ROOT, "commit", "-q", "-m", "seed", fecha=fecha).returncode == 0


def _skip_sin_git(ok):
    if not ok:
        import pytest
        pytest.skip("git no disponible")


def test_verificacion_stale_por_edicion_sin_commitear(toy_vault, capsys):
    """El caso que importa: el lint corre ANTES del commit, así que la edición que dejó el bloque
    atrasado todavía no está en `git log` — un archivo sucio se toma como cambiado hoy."""
    cuerpo = "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-01-01)\nok\n"
    _skip_sin_git(_repo_con_nota(toy_vault, cuerpo, fecha="2020-01-01"))
    rc, out = run_lint(capsys)
    assert rc == 0                                     # backlog, no bloqueante
    assert SIN_STALE in out                            # verificada el mismo día del commit: al día
    # ahora se amplía la nota sin re-verificar (append-knowledge / maintain A)
    p = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    p.write_text(p.read_text(encoding="utf-8").replace("Afirmación", "Afirmación nueva y otra más"),
                 encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "- nota-verif → la nota se editó el" in out
    assert "su último verify es del 2020-01-01" in out


def test_verificacion_stale_por_commit_posterior(toy_vault, capsys):
    """La otra rama: la edición ya está committeada — la fecha sale de `git log -1 --format=%cs`."""
    cuerpo = "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-01-01)\nok\n"
    _skip_sin_git(_repo_con_nota(toy_vault, cuerpo, fecha="2020-01-01"))
    p = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    p.write_text(p.read_text(encoding="utf-8") + "\nPárrafo agregado después.\n", encoding="utf-8")
    _git(toy_vault.ROOT, "add", "-A")
    _git(toy_vault.ROOT, "commit", "-q", "-m", "amplía", fecha="2020-06-01")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "la nota se editó el 2020-06-01 y su último verify es del 2020-01-01" in out


def test_verificacion_al_dia_no_se_marca(toy_vault, capsys):
    """Bloque fechado DESPUÉS del último cambio del archivo: verificada al día → no se marca."""
    cuerpo = "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-03-01)\nok\n"
    _skip_sin_git(_repo_con_nota(toy_vault, cuerpo, fecha="2020-01-01"))
    rc, out = run_lint(capsys)
    assert rc == 0
    assert SIN_STALE in out


def test_bloque_sin_fecha_se_marca(toy_vault, capsys):
    """Sin fecha en el encabezado no hay forma de saber si el bloque sigue vigente (no necesita git)."""
    _nota_verif(toy_vault, "sin-fecha",
                "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas\nok\n")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "- sin-fecha → bloque de verificación sin fecha en el encabezado" in out


def test_stale_sin_git_no_rompe(toy_vault, capsys, monkeypatch):
    """Fuera de un repo (o sin git en el PATH) el chequeo se omite en silencio: el resto del lint
    no depende de él."""
    monkeypatch.setattr(lint, "git_out", lambda *a: None)
    _nota_verif(toy_vault, "nota-verif",
                "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-01-01)\nok\n")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert SIN_STALE in out


# ── in_dir (portabilidad de separador, #33) ──────────────────────────────────

def test_in_dir_componente_no_substring():
    """Regresión #33: el chequeo es por COMPONENTE de directorio (Path.parts, separador nativo),
    no por substring "/x/" — que en Windows no matcheaba nunca. Misma semántica que el literal
    viejo en POSIX: una nota llamada queries.md no es la carpeta queries/."""
    import lint
    assert lint.in_dir("vault/wiki/queries/x.md", "queries") is True
    assert lint.in_dir("vault/wiki/concepts/methods/gp.md", "concepts") is True
    assert lint.in_dir("vault/wiki/queries.md", "queries") is False       # stem ≠ carpeta
    assert lint.in_dir("vault/wiki/stars/x.md", "queries") is False

