"""lint: cada categoría detecta su caso sembrado; exit code separa bloqueante/WARN/backlog."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import lib_config as cfg
import lint
from conftest import mk_note, write_yaml

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


def run_lint_reporte(capsys):
    """Devuelve `(rc, reporte)` leyendo el .md, NO stdout. `run_lint` de más arriba captura
    `capsys.readouterr().out`, que trae el reporte PERO TAMBIÉN la última línea (`→ <ruta>`), y esa
    ruta vive bajo el tmpdir de pytest —cuyo nombre es el del test—: un assert de substring contra
    ese stdout puede pasar por el texto del path en vez de por un hallazgo real del lint. Ya mordió
    dos veces en este repo (ver STATUS.md); los tests que comparan contenido puntual usan este
    helper en vez de `run_lint`."""
    rc = lint.main()
    capsys.readouterr()
    import datetime as dt
    return rc, (cfg.ROOT / "outputs" / f"lint-{dt.date.today().isoformat()}.md").read_text(
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
    assert "## ⛔ Frontmatter no parseable o con forma inválida (la nota evade los chequeos de su tipo) (2)" in out
    assert "YAML inválido" in out and "sin cierre `---`" in out


NOTA_CON_GUIONES = (
    '---\n'
    'bibcode: 2020aaa...1..1A\n'
    'title: "Un titulo con --- adentro"\n'
    'tags:\n'
    '- paper\n'
    '---\n'
    'cuerpo\n'
)


def test_el_lint_no_reporta_yaml_invalido_sobre_yaml_valido():
    """Peor que perderlo: el lint lo reporta como **YAML inválido** —categoría BLOQUEANTE— y manda a
    arreglar un frontmatter que no está roto. Falso positivo que frena un commit."""
    assert lint.fm_error(NOTA_CON_GUIONES) is None, (
        f"falso positivo bloqueante: {lint.fm_error(NOTA_CON_GUIONES)!r}")


def test_paper_sin_tag_paper_evade_los_chequeos_de_su_tipo(toy_vault, capsys):
    """Sin `tags: [paper]` la nota queda invisible para TODOS los chequeos de su tipo —incluida la
    frontera dura de `retracted`— y ni siquiera sale como huérfana si algo la linkea: se pierde del
    todo, en silencio. Este chequeo es la única red para ese modo de falla."""
    mk_note(toy_vault.PAPERS, "2020notg....1N", {"relevance": "high"}, "cuerpo\n")
    rc, out = run_lint_reporte(capsys)
    assert rc == 1
    assert "nota en `papers/` sin `tags: [paper]`" in out


def test_pdf_no_string_bloquea_el_chequeo_pdf_disco(toy_vault, capsys):
    """Un `pdf: 42` (edición a mano, o un estampador con bug) se comparaba contra el disco como si
    fuera una ruta; sin este chequeo el drift PDF↔disco de esa nota queda silenciado para siempre,
    sin dejar rastro de que dejó de correr."""
    mk_note(toy_vault.PAPERS, "2020pdfN...1N", {"tags": ["paper"], "pdf": 42}, "")
    rc, out = run_lint_reporte(capsys)
    assert rc == 1
    assert "`pdf` no es una ruta (es int)" in out


def test_prosa_plana_sin_frontmatter_es_legitima(toy_vault, capsys):
    toy_vault.INDEX.write_text("# Índice\n\nprosa plana sin frontmatter\n", encoding="utf-8")
    toy_vault.LOG.write_text("# Log\n", encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "## ⛔ Frontmatter no parseable o con forma inválida (la nota evade los chequeos de su tipo) (0)" in out


def test_planets_con_forma_invalida_se_reporta_y_no_voltea_el_lint(toy_vault, capsys):
    """El lint es la compuerta de CI: ante un frontmatter raro reporta, no se muere. Un `planets:`
    con un elemento que no es mapa (lista a medio escribir, edición a mano) volteaba el barrido
    entero con un AttributeError — y el resto de la bóveda quedaba sin chequear."""
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["s"],
             "planets": ["b", {"letter": "c"}]}, "**b** (P=1 d) y **c** (P=2 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "Traceback" not in out
    assert "1 entrada(s) de `planets` que no son un mapa" in out
    assert "## Campos incompletos" in out          # el resto de los chequeos siguió corriendo


def test_campo_de_lista_escrito_como_escalar_se_reporta_una_vez(toy_vault, capsys):
    """`thesis_links: shift` (sin corchetes) se iteraba CARÁCTER POR CARÁCTER: cinco `thesis_links`
    colgantes inventados, uno por letra. Ahora es un hallazgo de forma, uno solo."""
    mk_note(toy_vault.PAPERS, "2020strS...1..1S",
            {"tags": ["paper"], "relevance": "high", "methods": ["x"], "role": ["arbitro"],
             "thesis_links": "shift", "bearing": "supports"}, "")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert out.count("`thesis_links` no es una lista") == 1
    assert "thesis_links sin página destino (0)" in out      # ningún colgante inventado


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


def test_retraction_escalar_no_voltea_el_lint(toy_vault, capsys):
    """El lint es la compuerta de CI: `retraction` mal formado (un string suelto en vez del mapa
    `{type,date,...}`) tiene que reportarse, no tumbar la corrida entera."""
    mk_note(toy_vault.PAPERS, "2020aaa...1..1A",
            {"tags": ["paper"], "retracted": True, "retraction": "retractado en 2021"}, "")
    assert run_lint(capsys)[0] in (0, 1)


def test_contradiccion_gt_ficha(toy_vault, capsys):
    write_gt(toy_vault, [gt_planet("b"), gt_planet("c")])
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["halpha"],
             "planets": [{"letter": "b"}]}, "**b** (P=365 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "el ground-truth trae el planeta `c` y la ficha no lo lista" in out


# ── sin capas de compatibilidad: cada tolerancia sacada deja un detector ─────

def test_triage_json_viejo_es_bloqueante(toy_vault, capsys):
    """`load_decisiones` dejó de mergear el `build/<slug>/triage.json` pre-1.9.0. Sin detector eso
    sería una pérdida SILENCIOSA: el triage volvería a proponer lo ya descartado, sin el motivo."""
    d = toy_vault.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"slug": "test_star", "records": []}), encoding="utf-8")
    (d / "triage.json").write_text(json.dumps({"decisiones": {
        "2020a....1A": {"decision": "descartado", "motivo": "ruido"},
        "2020b....1B": {"decision": "descartado", "motivo": "ruido"}}}), encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "2 decisión(es) en build/test_star/triage.json" in out
    assert "triage.py test_star --migrate" in out


def test_triage_json_se_detecta_sin_ads_json(toy_vault, capsys):
    """El detector NO puede colgar del barrido de `ads.json`: un `build/` limpiado a medias (o una
    bóveda vieja sin ads.json) tiene el triage.json igual, y ése es justo el caso que este chequeo
    existe para cubrir."""
    d = toy_vault.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "triage.json").write_text(json.dumps({"decisiones": {
        "2020a....1A": {"decision": "descartado", "motivo": "ruido"}}}), encoding="utf-8")
    assert not (d / "ads.json").exists()
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "1 decisión(es) en build/test_star/triage.json" in out


def test_paper_no_core_extraido_tampoco_pide_role(toy_vault, capsys):
    """Simétrico con #75: a una nota escrita con `--all` (no-core) no se le pide que aterrice en una
    síntesis, así que tampoco se le pide rol."""
    paper_extraido(toy_vault, relevance="low")
    rc, out = run_lint(capsys)
    assert rc == 0 and "sin `role`" not in out


def test_triage_json_ilegible_igual_se_reporta(toy_vault, capsys):
    """Un JSON roto no puede convertirse en "no hay nada que migrar": se reporta sin el conteo."""
    d = toy_vault.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"slug": "test_star", "records": []}), encoding="utf-8")
    (d / "triage.json").write_text("{roto", encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 1 and "? decisión(es) en build/test_star/triage.json" in out


def test_concept_areas_sin_declarar_se_reporta_una_vez(toy_vault, capsys):
    """Al sacar el modo tolerante, un objetivo sin `concept_areas` deja el typo-check APAGADO. Se
    reporta esa ausencia (WARN, una línea) en vez de marcar cada carpeta como no declarada — que
    sería ruido sobre un chequeo que ni siquiera está corriendo."""
    obj = dict(cfg.load_objective())
    obj.pop("concept_areas")
    write_yaml(toy_vault.OBJECTIVE_YAML, obj)
    mk_note(toy_vault.CONCEPTS / "activity", "algo", {"tags": ["activity"]}, "texto\n")
    mk_note(toy_vault.CONCEPTS / "zzz", "otro", {"tags": ["zzz"]}, "texto\n")
    link_from_index(toy_vault, "algo", "otro")
    rc, out = run_lint(capsys)
    assert rc == 0                                        # WARN, no bloquea
    assert "no declara `concept_areas`" in out and "está APAGADO" in out
    assert "concepts/zzz/" not in out                     # no se duplica por carpeta


# ── #71: disputas con posiciones explícitas ─────────────────────────────────

def ficha_con_disputas(toy_vault, disputes, planets=None):
    fm = {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
          "planets": planets if planets is not None else [{"letter": "b"}],
          "disputes": disputes}
    return mk_note(toy_vault.STARS, "test_star", fm, "**b** (P=1 d)\n")


def test_disputa_paper_contra_paper_sobre_un_campo_estelar(toy_vault, capsys):
    """El caso que el schema viejo NO podía expresar: NEA calla (no hay `st_rotp`), así que no hay
    contra qué poner un `alt` — y `P_rot` es de la ESTRELLA, ni siquiera tenía dónde colgar."""
    mk_note(toy_vault.PAPERS, "2018autA...1..1A", {"tags": ["paper"]}, "")
    mk_note(toy_vault.PAPERS, "2021autB...1..1B", {"tags": ["paper"]}, "")
    ficha_con_disputas(toy_vault, [
        {"field": "P_rot", "note": "11.5 d podría ser el armónico",
         "posiciones": [{"ref": "2018autA...1..1A", "value": 33},
                        {"ref": "2021autB...1..1B", "value": 11.5}]}])
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "## disputes mal formadas (posiciones explícitas, #71) (0)" in out
    assert "## disputes: ref de una posición sin paper destino (0)" in out


def test_disputa_con_ground_truth_como_posicion(toy_vault, capsys):
    """`{source: ground_truth}` es lo que distingue "hay autoridad" de "la bóveda no sabe" — la
    diferencia que el consumidor necesita ver."""
    mk_note(toy_vault.PAPERS, "2020disD...1..1D", {"tags": ["paper"]}, "")
    ficha_con_disputas(toy_vault, [
        {"field": "b.K", "posiciones": [{"ref": "2020disD...1..1D", "value": 1.4},
                                        {"source": "ground_truth", "value": 0.9}]}])
    rc, out = run_lint(capsys)
    assert rc == 0 and "(posiciones explícitas, #71) (0)" in out


def test_disputa_ref_colgante_en_posicion(toy_vault, capsys):
    ficha_con_disputas(toy_vault, [
        {"field": "P_rot", "posiciones": [{"ref": "2018noExiste...1A", "value": 33},
                                          {"source": "ground_truth"}]}])
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "disputa `P_rot`: ref `2018noExiste...1A` sin nota de paper" in out


def test_disputa_con_una_sola_posicion_no_es_disputa(toy_vault, capsys):
    """Con un solo lado no hay desacuerdo: es una afirmación, y va a la prosa citada."""
    mk_note(toy_vault.PAPERS, "2020disD...1..1D", {"tags": ["paper"]}, "")
    ficha_con_disputas(toy_vault, [
        {"field": "P_rot", "posiciones": [{"ref": "2020disD...1..1D", "value": 33}]}])
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "con 1 posición(es)" in out and "va a la prosa citada" in out


def test_disputa_sin_field_o_con_posicion_muda(toy_vault, capsys):
    mk_note(toy_vault.PAPERS, "2020disD...1..1D", {"tags": ["paper"]}, "")
    ficha_con_disputas(toy_vault, [
        {"posiciones": [{"ref": "2020disD...1..1D"}, {"source": "ground_truth"}]},
        {"field": "b.e", "posiciones": [{"ref": "2020disD...1..1D"}, {"value": 0.3}]},
        {"field": "b.P", "posiciones": [{"ref": "2020disD...1..1D"}, {"source": "nea"}]}])
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "disputa sin `field`" in out
    assert "posición sin `ref` ni `source`" in out
    assert "`source: nea` fuera del vocabulario" in out


def test_disputa_con_formas_basura_no_crashea_el_lint(toy_vault, capsys):
    """El lint corre sobre notas escritas a mano: una disputa que es un string suelto, o una
    posición que no es un mapa, tiene que reportarse (o saltearse) sin voltear el barrido entero."""
    ficha_con_disputas(toy_vault, [
        "esto no es un mapa",                                   # la disputa entera es basura
        {"field": "P_rot", "posiciones": ["2018autA", "2021autB"]}])
    rc, out = run_lint(capsys)
    assert rc == 1
    assert out.count("posición que no es un mapa") == 2     # las dos posiciones basura
    # y la disputa que ni siquiera es un mapa se REPORTA: filtrarla en silencio era el mismo modo
    # de falla que #71 vino a cerrar (lo que el lector ignora sin decir nada).
    assert "1 entrada(s) de `disputes` que no son un mapa" in out
    assert "Traceback" not in out


def test_disputes_que_no_es_una_lista_se_reporta(toy_vault, capsys):
    """`disputes: "b.K"` (escrito a mano como escalar): iterarlo daba caracteres, ninguno un mapa,
    y la nota pasaba como si no tuviera disputas. Se reporta una vez, no una por carácter."""
    ficha_con_disputas(toy_vault, "b.K")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert out.count("`disputes` no es una lista") == 1


def test_disputa_en_un_concepto(toy_vault, capsys):
    """Punto 3 del issue: en un concepto la disputa es simétrica por definición — no hay valor de
    frontmatter contra el cual poner un `alt`."""
    mk_note(toy_vault.PAPERS, "2018autA...1..1A", {"tags": ["paper"]}, "")
    mk_note(toy_vault.PAPERS, "2021autB...1..1B", {"tags": ["paper"]}, "")
    mk_note(toy_vault.CONCEPTS / "methods", "gp",
            {"tags": ["methods"], "disputes": [
                {"field": "signo de la correlación",
                 "posiciones": [{"ref": "2018autA...1..1A", "value": "positiva"},
                                {"ref": "2021autB...1..1B", "value": "negativa"}]}]},
            "Síntesis con [[2018autA...1..1A]] y [[2021autB...1..1B]].\n")
    link_from_index(toy_vault, "gp")
    rc, out = run_lint(capsys)
    assert rc == 0 and "(posiciones explícitas, #71) (0)" in out


def test_disputa_mal_formada_en_un_concepto_tambien_bloquea(toy_vault, capsys):
    """Hermano del de arriba, y el que hace que ese valga: el caso feliz de un concepto da 0 hits
    tanto si la disputa se validó como si el chequeo ni la miró. Acá el concepto trae las dos fallas
    —una posición sola (afirmación, no desacuerdo) y una `ref` sin nota de paper— así que un lint que
    saltee los conceptos vuelve limpio y miente."""
    mk_note(toy_vault.PAPERS, "2018autA...1..1A", {"tags": ["paper"]}, "")
    mk_note(toy_vault.CONCEPTS / "methods", "gp",
            {"tags": ["methods"], "disputes": [
                {"field": "signo", "posiciones": [{"ref": "2018autA...1..1A", "value": "positiva"}]},
                {"field": "escala", "posiciones": [{"ref": "2018autA...1..1A", "value": 1},
                                                   {"ref": "2099fantasma..1..1F", "value": 2}]}]},
            "Síntesis con [[2018autA...1..1A]].\n")
    link_from_index(toy_vault, "gp")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "disputa `signo` con 1 posición(es)" in out
    assert "disputa `escala`: ref `2099fantasma..1..1F` sin nota de paper" in out


def test_posiciones_escalar_no_voltea_el_lint(toy_vault, capsys):
    """`posiciones:` escalar es frontmatter editado a mano: se REPORTA, no voltea el barrido — y un
    string se reporta UNA vez, no una por carácter (`normalize_lists` sanea el primer nivel del
    frontmatter y esto está anidado, así que necesita su propia guarda)."""
    ficha_con_disputas(toy_vault, [{"field": "b.K", "posiciones": 5},
                                   {"field": "b.e", "posiciones": "2020disD"}])
    rc, out = run_lint(capsys)
    assert rc == 1 and "Traceback" not in out
    assert out.count("`posiciones` no es una lista") == 2


def test_disputes_escalar_dentro_de_un_planeta_no_voltea_el_lint(toy_vault, capsys):
    """El detector del schema VIEJO mira justamente frontmatter viejo y editado a mano: un
    `planets[].disputes` escalar llegaba a `len()` y lo mataba."""
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
             "planets": [{"letter": "b", "disputes": 5}]}, "**b** (P=1 d)\n")
    rc, out = run_lint(capsys)
    assert "Traceback" not in out


def test_disputa_con_field_nulo_tambien_bloquea(toy_vault, capsys):
    """`field:` a secas es la forma normal de dejarlo sin llenar. `.get("field", "")` devuelve None
    con la clave presente y nula, y `str(None)` == "None" (truthy): el bloqueante no disparaba y el
    resto de los mensajes la nombraban "disputa None"."""
    mk_note(toy_vault.PAPERS, "2020disD...1..1D", {"tags": ["paper"]}, "")
    ficha_con_disputas(toy_vault, [{"field": None, "posiciones": [
        {"ref": "2020disD...1..1D", "value": 1}, {"source": "ground_truth", "value": 2}]}])
    rc, out = run_lint(capsys)
    assert rc == 1 and "disputa sin `field`" in out


def test_posicion_con_ref_y_source_no_esquiva_el_vocabulario(toy_vault, capsys):
    """Con `ref` presente el `elif` nunca miraba `source`: una posición que declara DOS dueños
    distintos pasaba entera y el vocabulario cerrado se salteaba."""
    mk_note(toy_vault.PAPERS, "2020disD...1..1D", {"tags": ["paper"]}, "")
    ficha_con_disputas(toy_vault, [{"field": "b.K", "posiciones": [
        {"ref": "2020disD...1..1D", "source": "wikipedia", "value": 1},
        {"source": "ground_truth", "value": 2}]}])
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "`source: wikipedia` fuera del vocabulario" in out
    assert "posición con `ref` Y `source`" in out


# ── #73: el ROL del paper ────────────────────────────────────────────────────

def test_role_fuera_del_vocabulario_es_bloqueante(toy_vault, capsys):
    """Mismo trato que un `thesis_links` que no matchea ninguna nota: un typo deja el campo mudo
    para la operación que existe para consumirlo, sin que nadie se entere."""
    paper_extraido(toy_vault, role=["fundacinal"], no_sintetizado="tangencial")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "`role: fundacinal` no está en el vocabulario" in out


@pytest.mark.parametrize("rol", ["fundacional", "aplicacion", "arbitro"])
def test_role_valido_escalar_o_lista(toy_vault, capsys, rol):
    """El issue admite "uno o varios": un rol solo se puede escribir como escalar o como lista de
    un elemento, y las dos formas valen (`merge_frontmatter_list` deja una, `make_notes` la otra)."""
    paper_extraido(toy_vault, stem="2020esc....1E", role=rol, no_sintetizado="tangencial")
    paper_extraido(toy_vault, stem="2020lis....1L", role=[rol], no_sintetizado="tangencial")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "`role` fuera del vocabulario (fundacional/aplicacion/arbitro) (0)" in out


def test_role_multiple_valida_cada_elemento(toy_vault, capsys):
    paper_extraido(toy_vault, role=["fundacional", "arbitro"], no_sintetizado="tangencial")
    rc, out = run_lint(capsys)
    assert rc == 0
    paper_extraido(toy_vault, stem="2021mal....1M", role=["arbitro", "revisión"],
                   no_sintetizado="tangencial")
    rc, out = run_lint(capsys)
    assert rc == 1 and "`role: revisión`" in out


def test_paper_extraido_sin_role_es_backlog(toy_vault, capsys):
    """El campo lo puebla la EXTRACCIÓN (la regex del clasificador clasifica tema, no rol), así que
    sin red nace muerto — el patrón de #87, "se guarda y nunca se usa", en su versión previa."""
    paper_extraido(toy_vault, no_sintetizado="tangencial")
    rc, out = run_lint(capsys)
    assert rc == 0                                       # backlog: no bloquea
    assert "paper extraído sin `role`" in out


def test_paper_sin_extraer_no_se_le_pide_role(toy_vault, capsys):
    """El rol sale de leer el paper: pedírselo a uno que nadie extrajo sería el mismo hallazgo que
    "paper relevante sin methods", dos veces."""
    mk_note(toy_vault.PAPERS, "2020raw....1R",
            {"tags": ["paper"], "relevance": "high", "methods": [], "thesis_links": []}, "")
    rc, out = run_lint(capsys)
    assert "paper relevante sin methods" in out
    assert "sin `role`" not in out


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


def test_clave_sintetica_off_ads_citada_cierra_extraido_no_sintetizado(toy_vault, capsys):
    """Una clave de cita off-ADS que NO matchea `BIBCODE_RE` (a diferencia de la convención
    `AAAA+Autor`, que sí matchea) es sólo un target de link más para #75: "citado" se mide contra el
    STEM de la nota de paper, así que se registra TODO target de una nota de entidad, no sólo los
    que parecen bibcode. Sin eso, un paper así queda reportado como "no sintetizado" PARA SIEMPRE
    aunque la ficha lo cite, sin forma de cerrar el hallazgo."""
    paper_extraido(toy_vault, stem="misc-blog-note")
    mk_note(toy_vault.STARS, "test_star", {"tags": ["star"], "P_rot_days": 34.0,
                                           "activity_indicators_expected": ["halpha"]},
            "Dato de [[misc-blog-note]].\n")
    rc, out = run_lint(capsys)
    assert "Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog) (0)" in out


def test_citado_solo_en_una_query_no_alcanza(toy_vault, capsys):
    """Una query es una respuesta puntual, no la síntesis durable de un sujeto: que el paper aparezca
    ahí no significa que haya llegado a la bóveda.

    El assert va contra el **conteo de la categoría**, no contra el título: los encabezados se
    imprimen con (0) hits igual, y el bibcode aparece además en otras categorías del mismo paper
    (`role` sin llenar), así que "el título está y el bibcode está" pasaba también cuando la
    distinción entre nota de entidad y query no se aplicaba."""
    paper_extraido(toy_vault, role=["arbitro"])
    mk_note(toy_vault.QUERIES, "una-pregunta", {"tags": ["query"]},
            "Respuesta con [[2020ext....1E]].\n")
    link_from_index(toy_vault, "una-pregunta")
    rc, out = run_lint(capsys)
    assert "Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog) (1)" in out
    assert "2020ext....1E → extraído" in out


def test_dos_notas_con_el_mismo_stem_no_voltean_el_lint(toy_vault, capsys):
    """Regresión: `sorted(extracted)` comparaba la tupla entera, así que dos notas de paper con el
    mismo stem —una copia de trabajo en otra carpeta— comparaban `no_sintetizado` (str contra None)
    y el lint MORÍA con un TypeError. El lint es la compuerta de CI: ante una bóveda rara reporta,
    no se cae."""
    paper_extraido(toy_vault, role=["arbitro"])
    mk_note(toy_vault.QUERIES, "2020ext....1E",
            {"tags": ["paper"], "relevance": "high", "methods": ["periodograma"],
             "no_sintetizado": "copia de trabajo"}, "")
    link_from_index(toy_vault, "2020ext....1E")
    rc, out = run_lint(capsys)
    assert "Traceback" not in out
    # y reporta: la copia lleva `no_sintetizado` con motivo (se cierra sola), la original no
    assert "Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog) (1)" in out


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


def test_relevance_low_capitalizado_tambien_excluye_de_extraido(toy_vault, capsys):
    """El tooling siempre escribe `low` en minúscula, pero una edición a mano puede dejar `Low`. Sin
    el `.lower()` del lector, ese paper entra a la población de #75 de la que el recorte lo quería
    dejar afuera (a una nota no-core no se le pide aterrizar en ninguna síntesis)."""
    paper_extraido(toy_vault, relevance="Low")
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


def test_no_sintetizado_no_string_tambien_se_reporta_sin_motivo(toy_vault, capsys):
    """`no_sintetizado: 5` (o una lista, o un mapa) es marca PRESENTE pero sin motivo TEXTUAL. El
    chequeo de tipo tiene que atraparla antes de llegar a `.strip()`, que sólo existe en `str`: sin
    el `isinstance`, un valor no-string cierra el hallazgo #75 en falso (o revienta el barrido, si
    el tipo no tiene `.strip()`) en vez de seguir pidiendo el motivo."""
    paper_extraido(toy_vault, no_sintetizado=5)
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
    """Un planeta de más se reporta ENTERO (una línea); repetirlo campo por campo sería ruido sobre
    el mismo hallazgo."""
    write_gt(toy_vault, [gt_planet("b")])
    ficha_espejo(toy_vault, {"planets": [{"letter": "b", "P_days": 365.25, "K_ms": 0.0895,
                                          "e": 0.0, "mass_earth": 1.0, "status": "confirmed"},
                                         {"letter": "z", "P_days": 9.9, "K_ms": 3.0}]},
                 "**b** (P=365 d) y **z** (P=9.9 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "planeta `z` en la ficha y NO en el ground-truth" in out
    assert "z.P_days" not in out and "z.K_ms" not in out


def test_espejo_compara_que_planetas_no_cuantos(toy_vault, capsys):
    """El agujero que dejaba el `len()`: la ficha lista **b** y **d**, NEA confirma **b** y **c** —
    mismo largo, planetas distintos, lint en verde. Y no es un caso raro: es exactamente cómo una
    señal no confirmada termina en `planets[]` (donde se lee como ground-truth) en vez de en
    `disputes` como `d.existence`. Un planeta entero inventado en la capa auditable era invisible."""
    write_gt(toy_vault, [gt_planet("b"), gt_planet("c")])
    ficha_espejo(toy_vault, {"planets": [{"letter": "b", "P_days": 365.25, "K_ms": 0.0895,
                                          "e": 0.0, "mass_earth": 1.0, "status": "confirmed"},
                                         {"letter": "d", "P_days": 11.5, "K_ms": 0.6}]},
                 "**b** (P=365 d) y **d** (P=11.5 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "planeta `d` en la ficha y NO en el ground-truth" in out
    assert "el ground-truth trae el planeta `c` y la ficha no lo lista" in out


def test_espejo_reporta_la_letra_repetida(toy_vault, capsys):
    """Lo único que el conteo veía y el conjunto de letras no: `planets[]` con la misma letra dos
    veces (dos fuentes pegadas a mano). Sin esto, el reemplazo perdía un chequeo."""
    write_gt(toy_vault, [gt_planet("b")])
    ficha_espejo(toy_vault, {"planets": [{"letter": "b", "P_days": 365.25, "K_ms": 0.0895,
                                          "e": 0.0, "mass_earth": 1.0, "status": "confirmed"},
                                         {"letter": "b", "P_days": 365.25, "K_ms": 0.0895,
                                          "e": 0.0, "mass_earth": 1.0, "status": "confirmed"}]},
                 "**b** (P=365 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "planeta `b` repetido en `planets[]` (2 veces)" in out


def test_ficha_con_planets_mal_formado_no_revienta_el_espejo(toy_vault, capsys):
    """`mirror_issues` recibe la ficha RE-PARSEADA aparte del barrido principal de notas —`fm_ficha`
    es un dict nuevo, no el que ese barrido ya normalizó—: sin volver a normalizar ADENTRO de
    `mirror_issues`, un elemento de `planets` que no es mapa llega crudo a `pl.get("letter")` y
    revienta el espejo #70 con un AttributeError en cuanto la ficha tiene ground-truth."""
    write_gt(toy_vault, [gt_planet("b")])
    ficha_espejo(toy_vault, {"planets": ["b_a_medio_escribir",
                                         {"letter": "b", "P_days": 365.25, "K_ms": 0.0895,
                                          "e": 0.0, "mass_earth": 1.0, "status": "confirmed"}]})
    rc, out = run_lint(capsys)
    assert "Traceback" not in out
    assert "en la ficha y NO en el ground-truth" not in out
    assert "el ground-truth trae el planeta" not in out


def test_ficha_sin_ground_truth_se_reporta(toy_vault, capsys):
    """El barrido del espejo lo maneja el JSON, así que una ficha SIN archivo no la miraba nadie:
    se le podían inventar `teff_K`, `P_rot_days` o planetas enteros con el lint en verde. Es
    alcanzable sin salirse de lo documentado (`make_notes.py <slug>` corre solo, y el sub-modo
    borrar de `maintain` saca el JSON). Backlog, no bloqueante: la garantía no corrió acá, que es
    distinto de una violación (mismo criterio que #55 y #56)."""
    ficha_espejo(toy_vault, {"teff_K": 9999.0, "P_rot_days": 34.0, "planets": []},
                 "Prosa con P_rot 34 d [[2019A....1A]]\n")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "ficha sin `raw/ground_truth/<slug>.json`" in out


def test_ground_truth_sin_ficha_se_reporta(toy_vault, capsys):
    """Hermano simétrico de "ficha sin ground-truth". Un `raw/ground_truth/<slug>.json` sin su
    `stars/<slug>.md` es un renombre a medias o una ficha borrada sin limpiar: el espejo #70 no
    compara nada y nadie avisa que ese ground-truth quedó colgado."""
    (toy_vault.GROUND_TRUTH / "huerfana.json").write_text(
        json.dumps({"slug": "huerfana", "host": {"mass_msun": 1.0}, "planets": []}),
        encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)
    assert "huerfana" in rep, "un ground-truth sin ficha no aparece en el reporte"


def test_slug_interno_del_ground_truth_que_no_matchea_el_archivo(toy_vault, capsys):
    """El campo `slug` de adentro ganaba sobre el nombre del archivo, así que un renombre a medias
    —el sub-modo C de `maintain` nombra el archivo, la nota y el registro, no el campo— dejaba al
    espejo buscando una ficha inexistente: MUDO en silencio, que es lo que #70 existe para impedir."""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(
        json.dumps({"slug": "otro_slug", "host": {"teff_K": 5344.0}, "planets": []}),
        encoding="utf-8")
    ficha_espejo(toy_vault, {"teff_K": 9999.0, "planets": []}, "Prosa.\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "declara `slug: otro_slug` y el archivo es test_star.json" in out
    assert "`teff_K: 9999.0` contradice el ground-truth" in out       # y la ficha SÍ se compara


def test_ground_truth_ilegible_se_reporta_y_no_voltea_el_lint(toy_vault, capsys):
    """Un JSON corrupto abortaba la corrida entera con JSONDecodeError. El lint es la compuerta de
    CI: reporta la bóveda rara y sigue con el resto."""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text("{no es json", encoding="utf-8")
    mk_note(toy_vault.CONCEPTS / "methods", "suelta", {"tags": ["methods"]}, "sin links\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "Traceback" not in out
    assert "no se pudo leer" in out
    assert "## Notas huérfanas (sin links entrantes) (1)" in out      # el barrido siguió


def test_ground_truth_no_es_objeto_se_reporta(toy_vault, capsys):
    """Distinto del JSON ilegible de arriba: acá el JSON SÍ parsea (`json.loads` no revienta) pero
    no es un objeto (un array pelado, un número, …). Sin este chequeo `gt.get("slug")` tres líneas
    más abajo revienta con AttributeError sobre una lista, y el barrido entero se cae con él."""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps(["x"]), encoding="utf-8")
    mk_note(toy_vault.CONCEPTS / "methods", "suelta", {"tags": ["methods"]}, "sin links\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "Traceback" not in out
    assert "no es un objeto JSON (es list)" in out
    assert "## Notas huérfanas (sin links entrantes) (1)" in out      # el barrido siguió


def test_ground_truth_planets_no_es_lista_se_reporta(toy_vault, capsys):
    """Hermano del `host` no-mapa: un `planets` de nivel superior que no es lista (edición a mano)
    se itera más abajo (`for x in planetas_gt`) para separar los elementos malformados de los
    válidos — sin reportarlo y sanearlo a `[]` acá, ese `for` revienta iterando un entero."""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(
        json.dumps({"slug": "test_star", "host": {"mass_msun": 1.0}, "planets": 5}),
        encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "Traceback" not in out
    assert "`planets` del ground-truth no es una lista (es int)" in out


def test_ground_truth_con_planetas_mal_formados_no_voltea_el_lint(toy_vault, capsys):
    """`raw/` lo cura el usuario a mano: un `planets` con un elemento que no es mapa rompía el
    espejo con AttributeError."""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(
        json.dumps({"slug": "test_star", "host": {"mass_msun": 1.0},
                    "planets": ["b", {"letter": "c", "P_days": 1.0}]}), encoding="utf-8")
    ficha_espejo(toy_vault, {"planets": [{"letter": "c", "P_days": 1.0}]}, "**c** (P=1 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "Traceback" not in out
    assert "1 entrada(s) de `planets` del ground-truth que no son un mapa" in out


def test_host_del_ground_truth_no_mapa_se_reporta(toy_vault, capsys):
    """Con `host` escalar el espejo deja de vigilar los cuatro campos estelares SIN reportar nada,
    mientras el hermano `planets` no-lista sí reporta. Falso limpio asimétrico."""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(
        json.dumps({"slug": "test_star", "host": "no-soy-un-mapa", "planets": []}),
        encoding="utf-8")
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
             "planets": []}, "**b** (P=1 d)\n")
    rc, rep = run_lint_reporte(capsys)
    assert "host" in rep, "el `host` malformado del ground-truth no se reporta"


def test_ground_truth_con_valores_no_numericos_no_voltea_el_lint(toy_vault, capsys):
    """Ground-truth corrupto (K_ms/P_days/e/mass_msun editado a mano como texto) alimentado a
    `msini_earth` revienta comparando un string con 0 — se detecta ANTES de llamarlo y se reporta
    en vez de tumbar el barrido con un TypeError."""
    write_gt(toy_vault, [{"letter": "b", "P_days": 365.0, "K_ms": "no-numérico", "e": 0.0,
                          "mass_earth": 1.0, "status": "confirmed"}])
    assert run_lint(capsys)[0] in (0, 1)


def test_ficha_sin_frontmatter_no_genera_hallazgos_fantasma(toy_vault, capsys):
    """Sin frontmatter legible, comparar campo por campo producía un hallazgo por cada valor de NEA
    ('teff_K: None contradice…') apuntando al síntoma equivocado."""
    write_gt(toy_vault, [gt_planet("b")], host={"teff_K": 5344.0, "spectral_type": "G8V"})
    (toy_vault.STARS / "test_star.md").write_text("# Estrella\n\nprosa sin frontmatter\n",
                                                  encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "no tiene frontmatter legible" in out
    assert "contradice el ground-truth" not in out


def test_el_template_no_satisface_el_proxy_de_planeta(toy_vault, capsys):
    """Regresión de #72: el patrón de negrita usaba `[^*]*`, que cruza saltos de línea, así que
    matcheaba el texto ENTRE dos negritas cualesquiera. El ejemplo que #72 metió en el template
    ("11.5 d es el armónico de 34 d") dejaba al planeta **d** —de las letras más frecuentes del
    corpus— "discutido" en una ficha con CERO líneas de prosa."""
    write_gt(toy_vault, [gt_planet(l) for l in "bcdefg"])
    import make_notes as mn
    mn.write_star_note("test_star", force=False)
    link_from_index(toy_vault, "test_star")
    rc, out = run_lint(capsys)
    faltan = [l for l in "bcdefg" if f"planeta {l} en frontmatter pero no discutido en prosa" not in out]
    assert faltan == [], f"el template ya 'discute' {faltan} sin una sola línea de prosa"


def test_triage_json_valido_pero_no_objeto_se_reporta(toy_vault, capsys):
    """JSON válido que no es un objeto (`["x"]`, `null`) llegaba a `.get` y volteaba el reporte
    entero — el modo de falla equivocado justo para el chequeo que existe para no quedar mudo."""
    d = toy_vault.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "triage.json").write_text('["2019A....1A"]', encoding="utf-8")
    rc, out = run_lint(capsys)
    assert rc == 1 and "Traceback" not in out
    assert "? decisión(es) en build/test_star/triage.json" in out


def test_triage_json_con_decisiones_escalar_no_voltea_el_lint(toy_vault, capsys):
    """El guard `isinstance(data_lt, dict)` quedó un nivel arriba del uso: `{"decisiones": 3}` es un
    objeto JSON válido, pero `decisiones` no es un mapa y llega igual a `len()`."""
    d = toy_vault.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "triage.json").write_text('{"decisiones": 3}', encoding="utf-8")
    assert run_lint(capsys)[0] in (0, 1)


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
    # la notación que el propio CLAUDE.md pide en vault/wiki/ ($...$) — sin esto la heurística
    # marcaba "sin P_rot" sobre notas que SÍ lo documentan
    (r"con $P_{\rm rot}$ = 34 d [[2019A....1A]]", True),
    (r"P$_{\rm rot}$ ≈ 34 d [[2019A....1A]]", True),
    (r"$P_\mathrm{rot}$ = 34 d [[2019A....1A]]", True),
    ("P_rot = 34 d", False),                                        # sin respaldo: no cuenta
    ("Nada que ver [[2019A....1A]]", False),                        # cita sin la afirmación
    ("Protostellar disks en [[2019A....1A]]", False),               # "Prot" de otra palabra
    ("la rotación estelar de la muestra [[2019A....1A]]", False),   # sin "período de"
])
def test_prot_citado_regex(linea, documentado):
    assert lint.prot_documentado(linea) is documentado


@pytest.mark.parametrize("texto,documentado", [
    ("El período de rotación es\n34 d [[2019A....1A]].", True),      # prosa envuelta a 100 columnas
    ("[[2019A....1A]] mide un período de rotación de 34 d.", True),  # la cita, antes de la mención
    ("No se conoce el período de rotación [[2019A....1A]].", False), # el hueco, no el dato
    ("El P_rot no está medido [[2019A....1A]].", False),
    ("Falta el P_rot; ver [[2019A....1A]].", False),
    ("El P_rot es 34 d. Otra cosa [[2019A....1A]].", False),         # cita de OTRA oración
])
def test_prot_documentado_por_oracion(texto, documentado):
    """#70: el ámbito es la ORACIÓN (mención + cita en cualquier orden, sin negador), no la línea.
    Los tres modos de falla medidos: prosa envuelta, cita antes de la mención, y el hueco declarado
    —"no se conoce el período de rotación [[ref]]"— que apagaba el backlog que existe para eso."""
    assert lint.prot_documentado(texto) is documentado


@pytest.mark.parametrize("texto,documentado", [
    # el negador niega OTRA cosa en la misma oración: el P_rot SÍ está documentado y citado
    ("El período de rotación es 34 d [[2019abc]] y no hay señal en el bisector.", True),
    ("P_rot = 34 d [[2019abc]], aunque no se conoce la inclinación.", True),
    # el negador sí niega el P_rot: sigue siendo hueco
    ("No se conoce el período de rotación [[2019abc]].", False),
    ("El período de rotación no fue medido [[2019abc]].", False),
])
def test_prot_negador_de_otra_cosa_no_apaga_el_hallazgo(texto, documentado):
    """El negador se busca en toda la oración, así que cualquier "no hay …" que conviva con la
    mención apaga el backlog de `P_rot`. Es el falso NEGATIVO del chequeo: la ficha queda sin el
    hueco marcado justamente cuando el dato SÍ está."""
    assert lint.prot_documentado(texto) is documentado


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
    """El bibcode que sostiene una posición tiene que existir como nota de paper: si no, la disputa
    no es trazable (typo, o paper sin ingestar)."""
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
             "planets": [{"letter": "b"}],
             "disputes": [{"field": "b.existence",
                           "posiciones": [{"ref": "2020disD...1..1D"},
                                          {"source": "ground_truth", "value": "confirmed"}]}]},
            "**b** (P=1 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "## disputes: ref de una posición sin paper destino (1)" in out
    # la ref existe pero NO es nota de paper → sigue colgante
    mk_note(toy_vault.QUERIES, "2020disD...1..1D", {"tags": ["query"]}, "")
    link_from_index(toy_vault, "2020disD...1..1D")
    rc, out = run_lint(capsys)
    assert "## disputes: ref de una posición sin paper destino (1)" in out


def test_dispute_ref_con_paper_ok(toy_vault, capsys):
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
             "planets": [{"letter": "b"}],
             "disputes": [{"field": "b.K", "note": "K distinto",
                           "posiciones": [{"ref": "2020disD...1..1D", "value": 1.4},
                                          {"source": "ground_truth", "value": 0.9}]}]},
            "**b** (P=1 d)\n")
    mk_note(toy_vault.PAPERS, "2020disD...1..1D", {"tags": ["paper"]}, "")
    rc, out = run_lint(capsys)
    assert "## disputes: ref de una posición sin paper destino (0)" in out


def test_schema_viejo_de_disputes_grita_en_vez_de_volverse_mudo(toy_vault, capsys):
    """El lint dejó de leer `planets[].disputes[]` a propósito (una sola semántica). Lo que NO puede
    pasar es que esas disputas queden invisibles y la bóveda siga en verde: se reportan como
    bloqueante, con el comando de migración."""
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
             "planets": [{"letter": "b", "disputes": [
                 {"field": "K", "ref": "2020disD...1..1D", "alt": 1.4},
                 {"field": "existence", "ref": "2020disD...1..1D"}]}]},
            "**b** (P=1 d)\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "2 disputa(s) en `planets[].disputes[]`" in out
    assert "--migrate-disputes" in out


def test_disputes_escalar_dentro_de_un_planeta_del_schema_viejo_se_reporta(toy_vault, capsys):
    """`isinstance(d,(list,dict,str))` filtra el escalar: sección "(0)", exit 0. Un crash cambiado
    por SILENCIO es el modo de falla que el docstring de `legacy_disputes` dice impedir."""
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
             "planets": [{"letter": "b", "disputes": 5}]}, "**b** (P=1 d)\n")
    rc, rep = run_lint(capsys)
    assert rc == 1, "una disputa en el schema viejo mal formada no bloquea ni se reporta"


def test_disputes_string_del_schema_viejo_no_cuenta_una_por_caracter(toy_vault, capsys):
    """`len("abcdefg")` = 7 disputas inventadas, una por letra."""
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "P_rot_days": 1.0, "activity_indicators_expected": ["x"],
             "planets": [{"letter": "b", "disputes": "abcdefg"}]}, "**b** (P=1 d)\n")
    rc, rep = run_lint_reporte(capsys)
    assert "7 disputa(s)" not in rep, "se cuenta una disputa por carácter"


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


def test_objective_yaml_invalido_no_voltea_el_lint(toy_vault, capsys):
    """El skill `setup` hace que el agente escriba REGEX dentro de YAML: un `:` sin comillas es el
    error más probable de toda la config. El lint es la compuerta de CI: reporta, no se muere."""
    cfg.OBJECTIVE_YAML.write_text("name: x\nrelevance:\n  topics:\n    rv: v: mal\n",
                                  encoding="utf-8")
    assert run_lint(capsys)[0] in (0, 1)


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


# ── robustez del lint ante el registro malformado (blindaje de load_registro) ─

REGISTRO_ROTO = 'busqueda:\n  motivo: "sin cerrar\n  fecha: 2026-08-01\n'


def test_registro_no_es_un_mapa_no_voltea_el_lint(toy_vault, capsys):
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("test_star").write_text("- a\n- b\n", encoding="utf-8")
    assert run_lint(capsys)[0] in (0, 1)


def test_busqueda_del_registro_no_es_un_mapa_no_voltea_el_lint(toy_vault, capsys):
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("test_star").write_text("busqueda: 2026-08-22\n", encoding="utf-8")
    assert run_lint(capsys)[0] in (0, 1)


def test_registro_ilegible_se_reporta(toy_vault, capsys):
    """Sin `build/`, el lint cae al registro para saber si hay triage pendiente y corpus truncado.
    Si el archivo no parsea lo saltea MUDO: exit 0 y "Triage pendiente (0)" sobre un registro que
    declara 3 candidatos sin juzgar. Es el "cero inventado" que #64 cerró, por otra puerta — y la
    docstring de `load_registro` afirma justamente que el lint lo reporta."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("test_star").write_text(REGISTRO_ROTO, encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)
    assert "test_star" in rep and "registro" in rep.lower(), (
        "el registro ilegible no aparece en el reporte del lint")


def test_lint_usa_el_lector_blindado_del_registro():
    """`lint.py` es el único de seis lectores del registro que reimplementa la lectura cruda, y por
    eso se saltea el blindaje que la 6ª pasada le puso a `load_registro`."""
    import inspect
    assert "load_registro" in inspect.getsource(lint.main), "lint.main no usa cfg.load_registro"


def test_lint_no_muere_en_una_consola_no_utf8():
    """El reporte lleva `⛔`/`⚠`/`→` y español. En una consola `cp1252` o `ascii` el `print` final
    tira `UnicodeEncodeError` y el lint sale con exit 1 —indistinguible de "hay bloqueantes"—
    aunque el `.md` en disco haya quedado perfecto. La compuerta de CI tiene que dar su veredicto
    en cualquier consola.

    El `cwd` sale de `__file__`, **no** de `cfg.ROOT`: este test invoca el repo REAL como subproceso,
    y `cfg.ROOT` es una constante de módulo que cualquier fixture re-apunta (es justo el mecanismo de
    `toy_vault`). Con el tier `instancia` corriendo en la misma sesión, `cfg.ROOT` apuntaba a la copia
    de la instancia —que no tiene `scripts/`— y este test rompía; el síntoma sólo aparecía en el modo
    combinado `-m ""`, nunca en un tier corrido solo."""
    repo = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, "scripts/lint.py"], cwd=repo, capture_output=True,
                       env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "PYTHONIOENCODING": "ascii",
                            "HOME": str(Path.home())})
    assert b"UnicodeEncodeError" not in r.stderr, r.stderr[-400:].decode("utf-8", "replace")
    assert r.returncode == 0


def test_decision_que_no_es_un_mapa_se_reporta(toy_vault, capsys):
    """`lib_config.py:303` promete que el lint reporta esta forma. No existe: la entrada queda muda
    y el triage vuelve a proponer lo ya descartado SIN el motivo — el bug que #51 cerró."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    cfg.registro_path("test_star").write_text(
        "decisiones:\n  2006Rasmussen: descartado\n", encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)
    assert "2006Rasmussen" in rep, "la decisión mal formada no se reporta en ninguna categoría"


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


def test_constellations_no_lista_no_tumba_el_lint(toy_vault, capsys):
    """`lint.py:1032` — `"/".join(tg.get("constellations") or [])`.

    Las dos líneas de alrededor (1019 `candidates`, 1030 `truncated_glyph`) YA fueron migradas a
    `cfg.as_list` por la 6ª pasada; el `constellations` de adentro quedó sin migrar. Con un
    entero el `join` levanta `TypeError` y **voltea la compuerta de CI**, cuyo contrato
    documentado es "ante una bóveda rara reporta, no se muere". Alcanzabilidad baja (`query_ads`
    siempre escribe `sorted(consts)`), pero es el mismo sitio, el mismo bloque y el mismo helper:
    migrar el vecino y dejar el de adentro es la definición de barrido incompleto."""
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text(json.dumps(
        {"records": [], "candidates": [],
         "truncated_glyph": [{"letter": "e", "constellations": 5, "num_found": 9, "rows": 2}]}),
        encoding="utf-8")
    mk_note(cfg.STARS, "test_star", {"tags": ["star"], "planets": []}, "# t\n")
    run_lint(capsys)          # no debe reventar: la compuerta reporta, no se muere


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


def test_ads_json_no_es_un_objeto_no_voltea_el_lint(toy_vault, capsys):
    """`ads.json` con forma rara (`[]` en vez de un objeto) es un camino documentado — un Ctrl-C a
    mitad de `query_ads` o un archivo a medio escribir— y el lint es la compuerta de CI: reporta,
    no se muere."""
    d = cfg.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text("[]", encoding="utf-8")
    assert run_lint(capsys)[0] in (0, 1)


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
    cuerpo = "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-01-01)\n\n| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente |\n|---|---|---|---|---|---|\n"
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
    cuerpo = "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-01-01)\n\n| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente |\n|---|---|---|---|---|---|\n"
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
    cuerpo = "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-03-01)\n\n| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente |\n|---|---|---|---|---|---|\n"
    _skip_sin_git(_repo_con_nota(toy_vault, cuerpo, fecha="2020-01-01"))
    rc, out = run_lint(capsys)
    assert rc == 0
    assert SIN_STALE in out


def test_bloque_sin_fecha_se_marca(toy_vault, capsys):
    """Sin fecha en el encabezado no hay forma de saber si el bloque sigue vigente (no necesita git)."""
    _nota_verif(toy_vault, "sin-fecha",
                "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas\n\n| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente |\n|---|---|---|---|---|---|\n")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "- sin-fecha → bloque de verificación sin fecha en el encabezado" in out


def test_stale_sin_git_no_rompe(toy_vault, capsys, monkeypatch):
    """Fuera de un repo (o sin git en el PATH) el chequeo no se puede evaluar. El resto del lint
    sigue corriendo —eso no cambió—, pero **desde el issue 0.3 ya no se omite en silencio**: antes
    reportaba `stale (0)`, indistinguible de "todo al día". Hoy cae en *no evaluado* y cuenta para
    el exit (D-43 / INV-87).

    ⚠ Consecuencia asumida: una bóveda legítimamente sin git, con bloques de verificación, no
    puede dar lint limpio. Es el precio de no mentir sobre lo que no se miró; el mensaje dice qué
    falta y cómo."""
    monkeypatch.setattr(lint, "git_out", lambda *a: None)
    _nota_verif(toy_vault, "nota-verif",
                "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-01-01)\n\n| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente |\n|---|---|---|---|---|---|\n")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "No evaluado" in out
    assert SIN_STALE not in out    # su categoría se suprime: no muestra un cero que no midió


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


def test_in_dir_no_confunde_carpeta_hermana_stars_borradores(toy_vault, capsys):
    """Regresión #33 a nivel CONSUMIDOR (el predicado ya tiene su test de arriba, pero eso no
    protege al que lo LLAMA): comparar rutas como texto (`f.startswith(str(cfg.STARS))`) matchea
    `wiki/stars-borradores/` como si fuera `wiki/stars/`. Una carpeta de trabajo vecina con ese
    prefijo cerraría en falso el backlog de #75 — la cita desde un borrador NO cuenta como que el
    paper llegó a una nota de entidad."""
    paper_extraido(toy_vault)
    mk_note(toy_vault.WIKI / "stars-borradores", "borrador", {"tags": ["draft"]},
            "Mención de [[2020ext....1E]] en un borrador.\n")
    link_from_index(toy_vault, "borrador")
    rc, out = run_lint(capsys)
    assert "Extraído pero no sintetizado: el paper se extrajo y su contenido nunca llegó a una ficha/concepto (backlog) (1)" in out
    assert "2020ext....1E → extraído" in out



# ── issue 0.3 · "no evaluado": un chequeo que no pudo correr NO aporta un cero (D-43 / INV-87) ──

BAD_OBJECTIVE = "name: Prueba\nrelevance:\n  topics:\n    rv: activity: starspot\n"
# ⚠ el caso adversario tiene que ROMPER de verdad: `rv: foo:bar` —lo que proponía el plan—
# **parsea**, porque en YAML un `:` pegado al carácter siguiente es parte del escalar. El que
# rompe es `:` SEGUIDO DE ESPACIO, que es justo lo que produce una regex con una alternación
# y una descripción. Un test sembrado con el caso equivocado habría quedado verde por la
# razón equivocada.


def test_lint_objective_roto_bloquea(toy_vault, capsys):
    """El error más probable de toda la config —un `:` sin comillas dentro de una regex, que el
    skill `setup` hace escribir a mano— dejaba a `load_objective` degradando a `{}` **mudo**
    (`lib_config.py:185-187`): el clasificador seguía corriendo con una regla que nadie escribió, y
    el lint no decía nada. Hoy: categoría *no evaluado*, exit ≠ 0, y el motivo en el REPORTE (no en
    stdout — corolario del protocolo).  @inv INV-80"""
    cfg.OBJECTIVE_YAML.write_text(BAD_OBJECTIVE, encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)
    assert rc != 0
    assert "No evaluado" in rep
    assert "objective.yaml" in rep


def test_lint_sin_git_reporta_no_evaluado(toy_vault, capsys, monkeypatch):
    """La otra puerta del mismo cero inventado: sin `git`, `last_change_dates` devuelve `{}` y la
    verificación stale reportaba **0** en silencio — indistinguible de "todo al día".  @inv INV-87"""
    mk_note(toy_vault.QUERIES, "q1", {"tags": ["query"]},
            "Afirmación [[2020aaaA...1..1A]].\n\n## Verificación de citas (2020-01-01)\n")
    mk_note(toy_vault.PAPERS, "2020aaaA...1..1A", {"tags": ["paper"], "bibcode": "2020aaaA...1..1A"})
    link_from_index(toy_vault, "q1", "2020aaaA...1..1A")
    monkeypatch.setattr(lint, "git_out", lambda *a: None)
    rc, rep = run_lint_reporte(capsys)
    assert rc != 0
    assert "No evaluado" in rep
    assert "git" in rep.lower()


def test_no_evaluado_no_contamina_conteos(toy_vault, capsys, monkeypatch):
    """Adversario del cero inventado: el chequeo que no corrió NO puede aparecer como "(0)" en su
    categoría normal, porque ese 0 se lee como veredicto. La categoría stale queda fuera del
    reporte cuando no se pudo evaluar."""
    mk_note(toy_vault.QUERIES, "q1", {"tags": ["query"]},
            "Afirmación [[2020aaaA...1..1A]].\n\n## Verificación de citas (2020-01-01)\n")
    mk_note(toy_vault.PAPERS, "2020aaaA...1..1A", {"tags": ["paper"], "bibcode": "2020aaaA...1..1A"})
    link_from_index(toy_vault, "q1", "2020aaaA...1..1A")
    monkeypatch.setattr(lint, "git_out", lambda *a: None)
    _, rep = run_lint_reporte(capsys)
    assert "Verificación stale" not in rep, (
        "la categoría stale sigue reportando su conteo aunque no se haya podido evaluar")


def test_lint_limpio_sigue_en_cero(toy_vault, capsys):
    """Control de cordura: con git y con `objective.yaml` sano, "no evaluado" está vacío y no
    inventa un bloqueo (si no, la categoría nueva rompería toda bóveda sana)."""
    rc, rep = run_lint_reporte(capsys)
    assert "## ⛔ No evaluado" in rep and rep.split("## ⛔ No evaluado")[1].split("\n")[0].endswith("(0)")


# ── issue 1.2 · pares de verificación vencidos (D-4 / D-20 / INV-78) ────────────────────────────
#
# El bloque `## Verificación de citas` se lee como "esta nota está verificada". El ancla mide eso
# por PAR, no por archivo: qué afirmación exacta se chequeó, contra qué bytes de qué fuente.

import lib_blocks as lb   # noqa: E402


def _con_ancla(toy_vault, cuerpo, txt="El período es de 34 días.\n", bib="2020citC...1..1C",
               anchor=None, source=None):
    """Nota con bloque de verificación bien formado: la fila se calcula del propio cuerpo, así que
    el escenario nace VERIFICADO y cada test rompe una sola cosa (D-5: la ficha nace 100%)."""
    (toy_vault.FULLTEXT / "slug").mkdir(parents=True, exist_ok=True)
    ft = toy_vault.FULLTEXT / "slug" / f"{bib}.txt"
    ft.write_text(txt, encoding="utf-8")
    pares = lb.pairs_of(cuerpo)
    filas = ["| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente |",
             "|---|---|---|---|---|---|"]
    for i, par in enumerate(pares, 1):
        filas.append(f"| {i} | extracto | [[{par.bibcode}]] | soportada | "
                     f"{anchor or par.anchor} | {source or lb.source_hash(ft)} |")
    completo = cuerpo + "\n## Verificación de citas (2026-01-01)\n\n" + "\n".join(filas) + "\n"
    _nota_verif(toy_vault, "nota-verif", completo)
    return ft


CUERPO = "Afirmación con cita [[2020citC...1..1C]] sobre el período.\n"
TITULO = "Pares de verificación vencidos"


def _n_vencidos(rep):
    """El título lleva sufijo de severidad (cambia con --cierre): se lee el conteo."""
    linea = [l for l in rep.splitlines() if l.startswith(f"## {TITULO}")]
    assert linea, "la categoría de pares vencidos no aparece en el reporte"
    return int(linea[0].rsplit("(", 1)[1].rstrip(")"))


def test_nota_verificada_no_marca_nada(toy_vault, capsys):
    """Control de cordura, y D-5: la ficha nace 100% verificada. Sin este test, todos los de abajo
    podrían estar pasando por un escenario roto de base.  @inv INV-79"""
    _con_ancla(toy_vault, CUERPO)
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 0


def test_par_nuevo_sin_fila_marca(toy_vault, capsys):
    """Agregar una frase citada a una nota ya verificada: ese par nunca pasó por el fan-out, pero
    queda bajo un encabezado que se lee como vigente."""
    ft = _con_ancla(toy_vault, CUERPO)
    p = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    p.write_text(p.read_text(encoding="utf-8").replace(
        CUERPO, CUERPO + "\nAfirmación NUEVA [[2020citC...1..1C]].\n"), encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 1
    assert "sin verificar" in rep


def test_edicion_marca_solo_sus_pares(toy_vault, capsys):
    """Adversario de la invalidación por SECCIÓN: tres bloques citados, se edita uno."""
    cuerpo = ("Bloque uno [[2020citC...1..1C]].\n\nBloque dos [[2020citC...1..1C]].\n\n"
              "Bloque tres [[2020citC...1..1C]].\n")
    _con_ancla(toy_vault, cuerpo)
    p = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    p.write_text(p.read_text(encoding="utf-8").replace("Bloque dos", "Bloque DOS editado"),
                 encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 1
    assert "por edición" in rep


def test_reflow_no_marca_nada(toy_vault, capsys):
    """Re-wrapear la nota entera no cambia lo que afirma."""
    cuerpo = ("Una afirmación larga con su cita [[2020citC...1..1C]] que ocupa varias palabras "
              "y sigue hasta acá.\n")
    _con_ancla(toy_vault, cuerpo)
    p = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "varias palabras y sigue", "varias palabras\ny sigue"), encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 0


def test_reemplazo_del_txt_marca_por_fuente(toy_vault, capsys):
    """La otra mitad de INV-78 (D-20): se re-extrajo el PDF y el `.txt` ya no dice lo mismo. La
    nota no se tocó, así que ninguna medida basada en fechas de la NOTA lo vería.  @inv INV-78"""
    ft = _con_ancla(toy_vault, CUERPO)
    ft.write_text("El período es de 36 días.\n", encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 1
    assert "por fuente" in rep


def test_fila_huerfana_se_marca(toy_vault, capsys):
    """La afirmación se borró y la fila quedó apuntando a la nada — el bloque afirma haber
    verificado algo que ya no está."""
    _con_ancla(toy_vault, CUERPO)
    p = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    p.write_text(p.read_text(encoding="utf-8").replace(CUERPO, "Prosa sin citas.\n"),
                 encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 1
    assert "huérfana" in rep


def test_bloque_sin_columnas_de_hash_detectado(toy_vault, capsys):
    """Plantilla vieja: no hay dónde colgar el ancla. Bloqueante SIEMPRE (no depende de --cierre):
    no es un par vencido, es un bloque que nadie puede evaluar."""
    _nota_verif(toy_vault, "nota-verif", CUERPO +
                "\n## Verificación de citas (2026-01-01)\n\n"
                "| # | Afirmación | Fuente | Veredicto |\n|---|---|---|---|\n"
                "| 1 | extracto | [[2020citC...1..1C]] | soportada |\n")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1
    assert "plantilla vieja" in rep


def test_cierre_bloquea_periodica_reporta(toy_vault, capsys, monkeypatch):
    """R-1, decidida por el usuario el 2026-08-24: el MISMO detector, dos severidades según el
    momento. Sin flag es la pasada periódica (backlog, exit 0 — no tiene sentido frenar una bóveda
    con deuda vieja un martes cualquiera); `--cierre` es el paso de cierre de una operación que
    tocó la nota, donde un par sin verificar significa que no terminaste."""
    # el toy_vault no es un repo git y la nota lleva bloque FECHADO → sin esto cae en "no
    # evaluado" (issue 0.3) y el rc de la pasada periódica no mediría lo que este test mide.
    monkeypatch.setattr(lint, "git_out", lambda *a: "")
    ft = _con_ancla(toy_vault, CUERPO)
    ft.write_text("El período es de 36 días.\n", encoding="utf-8")
    rc_periodica, rep = run_lint_reporte(capsys)
    assert rc_periodica == 0
    assert _n_vencidos(rep) == 1
    assert lint.main(["--cierre"]) == 1
