"""lint: cada categoría detecta su caso sembrado; exit code separa bloqueante/WARN/backlog."""
import json

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
            "mass_earth": mass, "mass_flag": flag}


def write_gt(toy_vault, planets, mstar=1.0):
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(
        json.dumps({"slug": "test_star", "host": {"mass_msun": mstar}, "planets": planets}),
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


def test_contradiccion_gt_ficha(toy_vault, capsys):
    write_gt(toy_vault, [gt_planet("b"), gt_planet("c")])
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["halpha"],
             "planets": [{"letter": "b"}]}, "**b** (P=365 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "ficha 1 planetas vs ground-truth 2" in out


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
    assert "P_rot_days nulo" in out
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

