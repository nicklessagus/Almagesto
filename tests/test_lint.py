"""lint: cada categoría detecta su caso sembrado; exit code separa bloqueante/WARN/backlog."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import lib_config as cfg
import entity
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
    # @inv INV-02
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
    todo, en silencio. Este chequeo es la única red para ese modo de falla.  @inv INV-40"""
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
    colgantes inventados, uno por letra. Ahora es un hallazgo de forma, uno solo.  @inv INV-63"""
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
    # @inv INV-33
    mk_note(toy_vault.PAPERS, "2020retR...1..1R",
            {"tags": ["paper"], "retracted": True,
             "retraction": {"type": "retraction", "date": "2021-05-01"}}, "")
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "RETRACTADOS" in out and "retraction (2021-05-01)" in out


def test_paper_con_correccion_es_backlog_no_bloquea(toy_vault, capsys):
    """#52: erratum/corrigendum/EoC se surface (un corrigendum cambia justo el valor extraído)
    pero NO bloquea — el paper sigue siendo citable, a diferencia de una retracción.  @inv INV-34"""
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
    """Con un solo lado no hay desacuerdo: es una afirmación, y va a la prosa citada.  @inv INV-12"""
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
        {"field": "b.P", "posiciones": [{"ref": "2020disD...1..1D"}, {"source": "wikipedia"}]}])
    rc, out = run_lint(capsys)
    assert rc == 1
    assert "disputa sin `field`" in out
    assert "posición sin `ref` ni `source`" in out
    # `nea` ENTRÓ al vocabulario con D-2 (la disputa entre autoridades es real desde D-1);
    # el caso adversario del vocabulario cerrado se mantiene con una fuente inventada.
    assert "`source: wikipedia` fuera del vocabulario" in out


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
    para la operación que existe para consumirlo, sin que nadie se entere.  @inv INV-46"""
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


def _bajado(toy_vault, stem, slug="slug"):
    """Deja el `.txt` del paper en disco: «bajado y nadie lo leyó», que desde #90 es una cola
    distinta de «nunca se consiguió»."""
    d = toy_vault.FULLTEXT / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.txt").write_text("texto legible del paper " * 20, encoding="utf-8")


def test_paper_sin_extraer_no_se_le_pide_role(toy_vault, capsys):
    """El rol sale de leer el paper: pedírselo a uno que nadie extrajo sería el mismo hallazgo que
    "paper relevante sin methods", dos veces."""
    mk_note(toy_vault.PAPERS, "2020raw....1R",
            {"tags": ["paper"], "relevance": "high", "methods": [], "thesis_links": []}, "")
    _bajado(toy_vault, "2020raw....1R")
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
    ve — valida cada afirmación contra su fuente, no la cobertura del conjunto.  @inv INV-45"""
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
    _bajado(toy_vault, "2020raw....1R")
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
    lo detectaba — el único chequeo comparaba el NÚMERO de planetas, nunca los valores.  @inv INV-06"""
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
    `disputes` como `d.existence`. Un planeta entero inventado en la capa auditable era invisible.  @inv INV-09"""
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
    # D-42/INV-86: la palabra pelada dejó de ser respaldo — sin premisas no es inferencia.
    ("$P_{rot}$ ≈ 34 d, inferencia a partir del ciclo", False),      # lectura propia, marcada
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
    # @inv INV-10
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
    bloqueante, con el comando de migración.  @inv INV-13"""
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
    # @inv INV-04
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
    """Guard de config: objective.yaml sin instanciar (name = default del template) → WARN.  @inv INV-57"""
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
    cfg.OBJECTIVE_YAML.write_text("name: x\nrelevance:\n  facets:\n    rv: v: mal\n",
                                  encoding="utf-8")
    assert run_lint(capsys)[0] in (0, 1)


def test_area_no_declarada_warn(toy_vault, capsys):
    mk_note(toy_vault.CONCEPTS / "zzz", "nota", {"tags": ["zzz"]}, "área typo\n")
    link_from_index(toy_vault, "nota")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "concepts/zzz/" in out and "¿typo o área nueva sin declarar?" in out


def test_obsidian_en_raiz_warn(toy_vault, capsys):
    """Guard de operación: .obsidian/ en la raíz del repo (vault abierto ahí por error) → WARN.  @inv INV-65"""
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
    # @inv INV-03
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
    assert "Citas no verificables en ficha/query/concepto/hipótesis (sin fulltext) (0)" in out


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
    assert "## Sin verificar: nota con citas y sin bloque verify-citations (backlog: pasada periódica; con `--cierre` bloquea) (0)" in out


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
    _bajado(toy_vault, "2020papA...1..1A")
    mk_note(toy_vault.CONCEPTS / "methods", "algo", {"tags": ["methods"]}, "destino [[test_star]]\n")
    link_from_index(toy_vault, "algo")
    rc, out = run_lint(capsys)
    assert rc == 0
    assert "sin P_rot: NEA no lo trae y el cuerpo no documenta uno citado" in out
    assert "activity_indicators_expected vacío" in out
    assert "planeta c en frontmatter pero no discutido en prosa" in out
    assert "planeta b" not in out                     # b sí está discutida
    assert "paper relevante sin methods" in out
    # D-21 retiró `bearing` del paper, así que el campo incompleto "thesis_links sin
    # bearing" quedó sin población y se eliminó con el schema que lo generaba.
    assert "thesis_links sin bearing" not in out


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
    versionado y reportan el snapshot CON su fecha, diciendo que no es el conteo vigente.

    Sostiene los DOS invariantes, y por eso lleva las dos marcas: **INV-25** (borrar el scratch y
    re-correr no pierde nada: el juicio de curación vive en el registro versionado) e **INV-39** (un
    dato de snapshot se reporta como snapshot, con su fecha y aclarando que no es el conteo
    vigente) — los asserts de la fecha literal y de la frase son exactamente el segundo.
    @inv INV-25, INV-39"""
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
    """Con build/ presente manda la verdad viva: el sujeto no se reporta dos veces.

    ⚠ **Sin marca a propósito.** Llevaba `@inv INV-39` y mide lo contrario: acá se assertea que el
    snapshot **no** aparece (`assert "2026-08-01" not in out`), o sea la rama donde INV-39 no se
    ejercita. La atribución falsa es peor que la ausencia — el mapa decía que un P0 estaba medido
    por un test que prueba la precedencia, no el reporte. INV-39 lo mide el test de arriba."""
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
    eso se saltea el blindaje que la 6ª pasada le puso a `load_registro`.

    Mira `collect`, no `main`: desde 10.1 el barrido vive ahí y `main` sólo parsea, renderiza y
    decide el exit."""
    import inspect
    assert "load_registro" in inspect.getsource(lint.collect), "lint.collect no usa cfg.load_registro"


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
    cuerpo = "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-01-01)\n\n| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |\n|---|---|---|---|---|---|---|\n"
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
    """La otra rama: la edición ya está committeada — la fecha sale de `git log -1 --format=%cs`.  @inv INV-31"""
    cuerpo = "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-01-01)\n\n| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |\n|---|---|---|---|---|---|---|\n"
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
    cuerpo = "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-03-01)\n\n| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |\n|---|---|---|---|---|---|---|\n"
    _skip_sin_git(_repo_con_nota(toy_vault, cuerpo, fecha="2020-01-01"))
    rc, out = run_lint(capsys)
    assert rc == 0
    assert SIN_STALE in out


def test_bloque_sin_fecha_se_marca(toy_vault, capsys):
    """Sin fecha en el encabezado no hay forma de saber si el bloque sigue vigente (no necesita git)."""
    _nota_verif(toy_vault, "sin-fecha",
                "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas\n\n| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |\n|---|---|---|---|---|---|---|\n")
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
                "Afirmación [[2020citC...1..1C]].\n\n## Verificación de citas (2020-01-01)\n\n| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |\n|---|---|---|---|---|---|---|\n")
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

BAD_OBJECTIVE = "name: Prueba\nrelevance:\n  facets:\n    rv: activity: starspot\n"
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
    verificación stale reportaba **0** en silencio — indistinguible de "todo al día".  @inv INV-87, INV-38"""
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
    reporte cuando no se pudo evaluar.  @inv INV-32"""
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
               anchor=None, source=None, kind="txt"):
    """Nota con bloque de verificación bien formado: la fila se calcula del propio cuerpo, así que
    el escenario nace VERIFICADO y cada test rompe una sola cosa (D-5: la ficha nace 100%).

    `kind` es el prefijo `txt:`/`pdf:` de #117 — con qué archivo dice la fila haberse verificado.
    `kind=None` produce la plantilla ANTERIOR a 1.54.0 (celda sin prefijo), que es el caso que el
    detector nuevo tiene que agarrar."""
    (toy_vault.FULLTEXT / "slug").mkdir(parents=True, exist_ok=True)
    ft = toy_vault.FULLTEXT / "slug" / f"{bib}.txt"
    ft.write_text(txt, encoding="utf-8")
    pares = lb.pairs_of(cuerpo)
    filas = ["| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |",
             "|---|---|---|---|---|---|---|"]
    pref = f"{kind}:" if kind else ""
    for i, par in enumerate(pares, 1):
        filas.append(f"| {i} | extracto | [[{par.bibcode}]] | soportada | "
                     f"{anchor or par.anchor} | {pref}{source or lb.source_hash(ft)} | — |")
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


def _fuente_sin_ecuaciones(toy_vault, bib="2020citC...1..1C"):
    """Marca la fuente como #113 (símbolos perdidos) y le pone un PDF: su evidencia pasa a ser una
    PÁGINA del PDF, así que el archivo a vigilar deja de ser el `.txt`."""
    import lib_config as cfg
    nota = toy_vault.PAPERS / f"{bib}.md"
    t = nota.read_text(encoding="utf-8")
    nota.write_text(t.replace("---\n", "---\nsymbols_lost: true\n", 1), encoding="utf-8")
    (toy_vault.PDFS / "slug").mkdir(parents=True, exist_ok=True)
    pdf = toy_vault.PDFS / "slug" / f"{bib}.pdf"
    pdf.write_bytes(b"%PDF-1.4\n contenido binario original \xff\n")
    return pdf


def test_symbols_lost_vigila_el_PDF_y_no_el_txt(toy_vault, capsys):
    """#113/B-2: la evidencia de estos pares es «p. 628», no una línea del `.txt`.

    Re-extraer el `.txt` NO debe marcarlos vencidos —su fuente real no se movió—, y es justo el
    escenario que el propio framework provoca (`--force`, upgrade a OCR, backfill de marcas).

    ⚠ Desde #117 lo que ancla la fila al PDF es la **fila** (`pdf:`), no el `symbols_lost` de la
    nota del paper: el frontmatter no sabe qué leyó el verificador."""
    ft = _con_ancla(toy_vault, CUERPO)
    pdf = _fuente_sin_ecuaciones(toy_vault)
    # la fila tiene que nacer anclada al PDF, que es de donde salió la cita
    nota = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    nota.write_text(nota.read_text(encoding="utf-8").replace(
        f"txt:{lb.source_hash(ft)}", f"pdf:{lb.bytes_hash(pdf)}"), encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 0, "nace verificada contra el PDF"

    ft.write_text("otro texto re-extraido, el .txt cambio\n", encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 0, "re-extraer el `.txt` no mueve la fuente real de estos pares"


def test_symbols_lost_marca_cuando_cambia_el_PDF(toy_vault, capsys):
    """La otra mitad: si cambia el archivo del que SÍ sale la cita, el par vence."""
    ft = _con_ancla(toy_vault, CUERPO)
    pdf = _fuente_sin_ecuaciones(toy_vault)
    nota = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    nota.write_text(nota.read_text(encoding="utf-8").replace(
        f"txt:{lb.source_hash(ft)}", f"pdf:{lb.bytes_hash(pdf)}"), encoding="utf-8")
    pdf.write_bytes(b"%PDF-1.4\n un escaneo distinto \xfe\n")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 1
    assert "el PDF cambió" in rep, "el mensaje nombra el PDF, no el `.txt`"


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


def test_registro_schema_viejo_detectado(toy_vault, capsys):
    """D-28: `busqueda:` (mapa, una sola corrida) es el schema pre-1.26. El lint lo DETECTA y
    bloquea, sin migrador ni lector tolerante — un registro que el lector nuevo ignora en silencio
    deja la ficha afirmando sobre un universo que nadie puede reconstruir."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    (cfg.REGISTRO / "test_star.yaml").write_text(
        "slug: test_star\nbusqueda:\n  fecha: '2026-01-01'\n  n_total: 3\n", encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1
    assert "pre-D-28" in rep or "schema viejo" in rep


def test_stars_yaml_roto_reporta_no_evaluado_en_vez_de_reventar(toy_vault, capsys):
    """@inv INV-80 — *una config que no parsea rehúsa operar y el lint la REPORTA*. D-6 cerró esa
    puerta para `objective.yaml`, pero `stars.yaml`/`themes.yaml` quedaron afuera: `load_stars`
    propaga el `yaml.ScannerError` y `lint.main()` **muere con traceback**, que no es "reportar como
    bloqueante" — es llevarse puestos los otros cuarenta chequeos y no dejar reporte. Es el mismo
    falso limpio de INV-87 por otra puerta: el usuario ve un stacktrace y no sabe qué se miró."""
    cfg.STARS_YAML.write_text("tau Ceti:\n  slug: tau_ceti\n  title: mal: sin comillas\n",
                              encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)     # no debe levantar
    assert rc != 0
    assert "No evaluado" in rep and "stars.yaml" in rep


def test_themes_yaml_roto_tambien_reporta_no_evaluado(toy_vault, capsys):
    """@inv INV-80 — el hermano del anterior. La fila del contrato declaraba "la batería se completó
    con los otros dos YAML" y sólo `stars.yaml` tenía test: el mecanismo cubría los dos
    (`lint.main` llama a `cfg.themes_error()`), pero la garantía **medida** cubría uno. Declarar de
    más una batería es el mismo defecto que mide INV-87, aplicado a la doc en vez de al reporte."""
    cfg.THEMES_YAML.write_text("gp:\n  title: mal: sin comillas\n", encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)     # no debe levantar
    assert rc != 0
    assert "No evaluado" in rep and "themes.yaml" in rep


def test_notas_huerfanas_salen_en_orden_estable(toy_vault, capsys):
    """@inv INV-43 — el reporte tiene que ser **determinista entre corridas**, o dos corridas del
    mismo estado dan diffs distintos y el reporte deja de servir de línea de base. `orphans` salía
    de iterar un `dict` construido sobre un `set` de strings, cuyo orden depende del hash que
    Python randomiza **por proceso**: la sección cambiaba de orden sola. El golden lo tapaba
    ordenando las líneas antes de comparar —o sea que el único no-determinismo medido estaba
    justamente neutralizado en el test que debía verlo—; acá se fija la propiedad observable."""
    for stem in ("zeta", "alfa", "mu", "beta", "omega", "delta", "kappa", "gamma"):
        mk_note(cfg.CONCEPTS / "methods", stem, {"tags": ["concept"], "name": stem})
    _, rep = run_lint_reporte(capsys)
    lineas = []
    dentro = False
    for l in rep.splitlines():
        if l.startswith("## "):
            dentro = "huérfanas" in l
        elif dentro and l.startswith("- "):
            lineas.append(l)
    assert len(lineas) >= 8, f"el escenario tiene que sembrar huérfanas: {lineas}"
    assert lineas == sorted(lineas), f"orden inestable en «Notas huérfanas»: {lineas}"


def test_topics_en_nota_de_paper_es_schema_viejo(toy_vault, capsys):
    """R-5: `topics:` nombraba a la vez la faceta de la lente y el tema-sujeto; el renombre lo
    partió en `facets:` (nota de paper) y `themes.yaml`. El campo viejo quedó **sin lector**: una
    nota que lo trae tiene sus facetas MUDAS y hasta hoy ningún chequeo lo decía. Es el mismo modo
    de falla que `busqueda:` (pre-D-28) y se trata igual — detector bloqueante, nunca lector
    tolerante (@inv INV-13)."""
    mk_note(cfg.PAPERS, "2020Viejo",
            {"tags": ["paper"], "bibcode": "2020Viejo", "topics": ["rv", "activity"]})
    link_from_index(toy_vault, "2020Viejo")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1, "una nota con el campo pre-R-5 tiene que bloquear"
    assert "2020Viejo" in rep and "topics" in rep and "facets" in rep


def test_facets_vigente_no_dispara_el_detector(toy_vault, capsys):
    """Control de cordura: el campo vigente no puede caer en el detector del viejo."""
    mk_note(cfg.PAPERS, "2020Nuevo",
            {"tags": ["paper"], "bibcode": "2020Nuevo", "facets": ["rv"]})
    link_from_index(toy_vault, "2020Nuevo")
    rc, rep = run_lint_reporte(capsys)
    assert "2020Nuevo" not in rep or "pre-R-5" not in rep


def test_cadena_cortada_nombra_el_paso(toy_vault, capsys):
    """INV-91: el registro dice qué pasos corrieron; el lint compara contra el orden canónico y
    **nombra el paso donde se cortó**. Sin esto, una cadena abortada a la mitad deja la bóveda con
    notas a medio hacer y nada que lo diga."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    for paso in ("query_ads", "fetch_arxiv", "fetch_pdf"):
        cfg.save_paso("test_star", paso)
    _, rep = run_lint_reporte(capsys)
    assert "fetch_ground_truth" in rep
    assert "cadena" in rep.lower()


def test_cadena_completa_no_marca(toy_vault, capsys):
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    for paso in ("query_ads", "fetch_arxiv", "fetch_pdf", "fetch_ground_truth",
                 "make_notes", "extract_fulltext", "check_retractions"):
        cfg.save_paso("test_star", paso)
    _, rep = run_lint_reporte(capsys)
    linea = [l for l in rep.splitlines() if l.startswith("## Cadena incompleta")]
    assert linea and linea[0].endswith("(0)")


def test_lint_detecta_tabla_de_papers_desactualizada(toy_vault, capsys):
    """D-10: la tabla materializada es un snapshot, y un snapshot que nadie re-estampa miente igual
    que el roll-up Dataview que reemplazó. Backlog (es "re-estampar", no una violación), pero
    nombra el stem que falta — el patrón Censo."""
    import make_notes as mn
    mn.write_star_note("test_star", force=True)
    mk_note(toy_vault.PAPERS, "2020nueA...1..1A",
            {"tags": ["paper"], "bibcode": "2020nueA...1..1A", "stars": ["Estrella Test"]}, "")
    link_from_index(toy_vault, "test_star", "2020nueA...1..1A")
    _, rep = run_lint_reporte(capsys)
    assert "2020nueA...1..1A" in rep
    assert "lista de papers" in rep.lower()


def _n_recorte(rep):
    """El conteo de la categoría. Asertar por SUBSTRING falla acá: el título de la categoría
    ("Recorte de lectura sin declarar") aparece SIEMPRE, con `(0)` incluido — el reporte imprime
    todas las secciones a propósito, para que ninguna desaparezca en silencio."""
    linea = [l for l in rep.splitlines() if l.startswith("## Recorte de lectura")]
    assert linea, "la categoría no aparece en el reporte"
    return int(linea[0].rsplit("(", 1)[1].rstrip(")"))


def test_subconjunto_sin_declarar_reporta(toy_vault, capsys):
    """D-13/D-15 · INV-83: el ingest promete leer TODOS los core. Si quedan core sin extraer y el
    registro no declara por qué, eso tiene MÁS señal que un campo incompleto suelto: la ficha se
    presenta como snapshot del universo y no lo es.  @inv INV-83"""
    mk_note(toy_vault.PAPERS, "2020relA...1..1A",
            {"tags": ["paper"], "bibcode": "2020relA...1..1A", "stars": ["Estrella Test"],
             "relevance": "high"}, "")
    link_from_index(toy_vault, "2020relA...1..1A")
    _, rep = run_lint_reporte(capsys)
    assert _n_recorte(rep) == 1
    assert "no declaró" in rep


def test_subconjunto_declarado_baja_a_backlog(toy_vault, capsys):
    """Con el criterio declarado, el pendiente sigue visible (cola de D-15 que `maintain` consume)
    pero deja de ser el hallazgo con señal: el ingest **dijo** qué leyó y por qué."""
    mk_note(toy_vault.PAPERS, "2020relA...1..1A",
            {"tags": ["paper"], "bibcode": "2020relA...1..1A", "stars": ["Estrella Test"],
             "relevance": "high"}, "")
    link_from_index(toy_vault, "2020relA...1..1A")
    cfg.save_extraccion("test_star", subconjunto=True,
                        criterio="los 20 más citados + los 3 árbitros de la señal b")
    _, rep = run_lint_reporte(capsys)
    assert _n_recorte(rep) == 0


def test_disputa_entre_autoridades_es_expresable(toy_vault, capsys):
    """D-2 / INV-77: con `DISPUTE_SOURCES = ("ground_truth",)` las dos posiciones de una disputa
    nea↔simbad decían lo mismo — el desacuerdo entre autoridades no tenía forma. Desde D-1 es un
    caso real: las dos pueden traer `spectral_type` distinto, y el que no gana no se tira.
    @inv INV-77"""
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "name": "Estrella Test", "slug": "test_star",
             "disputes": [{"field": "spectral_type",
                           "posiciones": [{"source": "simbad", "value": "K0V"},
                                          {"source": "nea", "value": "G8V"}]}]}, "")
    link_from_index(toy_vault, "test_star")
    rc, rep = run_lint_reporte(capsys)
    linea = [l for l in rep.splitlines() if l.startswith("## disputes mal formadas")][0]
    assert linea.endswith("(0)")


def test_source_inventado_sigue_bloqueando(toy_vault, capsys):
    mk_note(toy_vault.STARS, "test_star",
            {"tags": ["star"], "name": "Estrella Test", "slug": "test_star",
             "disputes": [{"field": "spectral_type",
                           "posiciones": [{"source": "wikipedia", "value": "K0V"},
                                          {"source": "nea", "value": "G8V"}]}]}, "")
    link_from_index(toy_vault, "test_star")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1 and "wikipedia" in rep


# ── Tanda 5 · D-19 / INV-84: un trabajo, UNA nota canónica ──────────────────────────────────────

def test_dos_notas_mismo_arxiv_id_bloquean(toy_vault, capsys):
    """Medido en la instancia real: 2 trabajos con dos notas cada uno (mismo `arxiv_id`, dos
    bibcodes — el preprint y el publicado). Para todo lo que cuenta papers eso es doble conteo, y
    para el consumidor son dos fuentes donde hay una."""
    mk_note(toy_vault.PAPERS, "2020preX...1..1X",
            {"tags": ["paper"], "bibcode": "2020preX...1..1X", "arxiv_id": "2001.12345"}, "")
    mk_note(toy_vault.PAPERS, "2021pubY...1..1Y",
            {"tags": ["paper"], "bibcode": "2021pubY...1..1Y", "arxiv_id": "2001.12345"}, "")
    link_from_index(toy_vault, "2020preX...1..1X", "2021pubY...1..1Y")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1
    assert "2001.12345" in rep and "--rename-paper" in rep


def test_identidad_por_doi_tambien(toy_vault, capsys):
    mk_note(toy_vault.PAPERS, "2020aX....1..1X",
            {"tags": ["paper"], "bibcode": "2020aX....1..1X", "doi": "10.1/mismo"}, "")
    mk_note(toy_vault.PAPERS, "2021bY....1..1Y",
            {"tags": ["paper"], "bibcode": "2021bY....1..1Y", "doi": "10.1/mismo"}, "")
    link_from_index(toy_vault, "2020aX....1..1X", "2021bY....1..1Y")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1 and "10.1/mismo" in rep


def test_versions_no_cuenta_como_duplicado(toy_vault, capsys):
    """El alias vive en `versions[]` de la nota canónica: eso NO es un duplicado, es el registro de
    que el mismo trabajo tuvo otro bibcode."""
    mk_note(toy_vault.PAPERS, "2021pubY...1..1Y",
            {"tags": ["paper"], "bibcode": "2021pubY...1..1Y", "arxiv_id": "2001.12345",
             "versions": [{"bibcode": "2020preX...1..1X", "pdf_source": "eprint"}]}, "")
    link_from_index(toy_vault, "2021pubY...1..1Y")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 0


# ── Tanda 6 · D-47: la prosa que cita un retractado se MARCA, no se borra ───────────────────────

RETRACTADO = {"tags": ["paper"], "bibcode": "2019retR...1..1R", "retracted": True,
              "retraction": {"type": "retraction", "date": "2021-05-03"}}


def test_cita_a_retractado_sin_marca_bloquea(toy_vault, capsys):
    """Hoy el lint bloquea la NOTA del paper retractado, pero no localiza **qué afirmación** lo
    cita — que es lo que hay que revisar. La cita sin marcar sigue leyéndose como respaldo válido."""
    mk_note(toy_vault.PAPERS, "2019retR...1..1R", RETRACTADO, "")
    mk_note(toy_vault.CONCEPTS / "methods", "c1", {"tags": ["methods"]},
            "El período es de 34 d [[2019retR...1..1R]].\n")
    link_from_index(toy_vault, "c1", "2019retR...1..1R")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1
    assert "c1" in rep and "⛔retractada" in rep       # el mensaje trae la marca a usar


def test_cita_marcada_no_bloquea_y_se_lista(toy_vault, capsys):
    # @inv INV-93
    """Marcada, la afirmación queda **visible y no destruida**: el consumidor ve que el respaldo es
    una fuente retractada y decide. Baja a informativa."""
    mk_note(toy_vault.PAPERS, "2019retR...1..1R", RETRACTADO, "")
    mk_note(toy_vault.CONCEPTS / "methods", "c1", {"tags": ["methods"]},
            "El período es de 34 d [[2019retR...1..1R]] ⛔retractada, aunque nadie lo re-midió.\n")
    link_from_index(toy_vault, "c1", "2019retR...1..1R")
    rc, rep = run_lint_reporte(capsys)
    linea = [l for l in rep.splitlines() if l.startswith("## Prosa sostenida por fuente retractada")]
    assert linea and linea[0].endswith("(1)")


def test_marca_no_se_confunde_con_prosa(toy_vault, capsys):
    """Adversario: la palabra "retractada" suelta en una oración NO es la marca. Por eso lleva el
    símbolo — un `(retractada)` pelado daría falsos positivos con cualquier mención del hecho."""
    mk_note(toy_vault.PAPERS, "2019retR...1..1R", RETRACTADO, "")
    mk_note(toy_vault.CONCEPTS / "methods", "c1", {"tags": ["methods"]},
            "La señal fue retractada más tarde [[2019retR...1..1R]].\n")
    link_from_index(toy_vault, "c1", "2019retR...1..1R")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1


def test_config_ilegible_suprime_las_categorias_que_dependen_de_ella(toy_vault, capsys):
    """@inv INV-87 — «la categoría normal **se suprime** del reporte» estaba implementado sólo para
    *Verificación stale*. Medido con `stars.yaml` roto: cinco categorías que se calculan a partir
    de él seguían imprimiendo `(0)` — cinco ceros inventados, exactamente lo que la categoría *No
    evaluado* existe para no producir. Peor todavía con `objective.yaml` roto: *Áreas de concepts/*
    afirmaba «no declara `concept_areas`» sobre un archivo que **sí** la declara y que el lint no
    pudo leer."""
    cfg.STARS_YAML.write_text("tau Ceti:\n  title: mal: sin comillas\n", encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)
    assert rc != 0 and "No evaluado" in rep
    for cat in ("Triage pendiente", "Recorte de lectura sin declarar",
                "Lista de papers desactualizada", "Cadena incompleta", "Corpus truncado"):
        assert cat not in rep, f"«{cat}» imprimió su cero sobre una config que nadie pudo leer"


# ── Tanda 8 · issue 8.3 (D-42 / INV-86): la inferencia nombra sus premisas ─────────────────────

def _seccion(rep: str, titulo: str) -> str:
    """El cuerpo de una sección `## …<titulo>…` del reporte (para no confundirse con otras)."""
    dentro, out = False, []
    for l in rep.split("\n"):
        if l.startswith("## "):
            dentro = titulo in l
        elif dentro:
            out.append(l)
    return "\n".join(out)


def test_inferencia_pelada_bloquea(toy_vault, capsys):
    """@inv INV-86 — *toda `inferencia` nombra sus premisas (≥1 bibcode); sin premisas no es
    inferencia: es afirmación sin respaldo y no entra*.

    Cierra el sumidero de `verify-citations`: una afirmación que vuelve `no-soportada` podía
    sobrevivir **cambiándole la etiqueta** a `(inferencia)`, y ahí ya no la miraba nadie — ni el
    verify (no tiene bibcode que chequear) ni el lint (`PROT_CITE` aceptaba la palabra pelada como
    respaldo del P_rot)."""
    mk_note(cfg.CONCEPTS / "methods", "infer", {"tags": ["concept"], "name": "infer"},
            "El período es de 34 d (inferencia).\n")
    link_from_index(toy_vault, "infer")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1
    assert "infer" in _seccion(rep, "`inferencia` sin premisas")


def test_inferencia_con_premisas_pasa(toy_vault, capsys):
    mk_note(cfg.PAPERS, "2020Fuente", {"tags": ["paper"], "bibcode": "2020Fuente"})
    mk_note(cfg.CONCEPTS / "methods", "infer2", {"tags": ["concept"], "name": "infer2"},
            "El período es de 34 d (inferencia de [[2020Fuente]]).\n")
    link_from_index(toy_vault, "infer2", "2020Fuente")
    _, rep = run_lint_reporte(capsys)
    assert "infer2" not in _seccion(rep, "`inferencia` sin premisas")


def test_la_palabra_inferencia_en_prosa_no_es_una_marca(toy_vault, capsys):
    """El falso positivo obvio: la palabra usada como sustantivo común. La marca es la que va
    **entre paréntesis** al cierre de una afirmación; «la inferencia bayesiana permite…» no lo es."""
    mk_note(cfg.CONCEPTS / "methods", "infer3", {"tags": ["concept"], "name": "infer3"},
            "La inferencia bayesiana permite estimar el período sin asumir una forma.\n")
    link_from_index(toy_vault, "infer3")
    _, rep = run_lint_reporte(capsys)
    assert "infer3" not in _seccion(rep, "`inferencia` sin premisas")


def test_prot_documentado_ya_no_acepta_inferencia_pelada(toy_vault, capsys):
    """Regresión dirigida sobre `PROT_CITE`: aceptaba la palabra suelta como respaldo del P_rot, así
    que una ficha podía declarar un período «documentado» sin una sola fuente."""
    assert "inferencia" not in lint.PROT_CITE.pattern or "\\[\\[" in lint.PROT_CITE.pattern
    assert not lint.prot_documentado("El P_rot es 34 d (inferencia).")
    assert lint.prot_documentado("El P_rot es 34 d (inferencia de [[2020Fuente]]).")
    assert lint.prot_documentado("El P_rot es 34 d [[2020Fuente]].")


# ── Tanda 8 · issue 8.4 (D-37 + D-21) ─────────────────────────────────────────────────────────

def test_status_de_hipotesis_fuera_del_vocabulario_bloquea(toy_vault, capsys):
    """D-37. `status` es la única cosa que un consumidor lee para saber en qué quedó una hipótesis.
    En prosa libre no dice nada: el caso medido en la instancia real era
    `supuesto operativo con caveat conocido`. Mismo patrón que `role` (#73)."""
    mk_note(cfg.CONCEPTS / "hypotheses", "hip1",
            {"tags": ["concept"], "name": "hip1", "status": "supuesto operativo con caveat"})
    link_from_index(toy_vault, "hip1")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1 and "hip1" in _seccion(rep, "status")


def test_status_del_vocabulario_pasa(toy_vault, capsys):
    for i, st in enumerate(("abierta", "sostenida", "disputada", "refutada")):
        mk_note(cfg.CONCEPTS / "hypotheses", f"ok{i}",
                {"tags": ["concept"], "name": f"ok{i}", "status": st})
    link_from_index(toy_vault, *[f"ok{i}" for i in range(4)])
    _, rep = run_lint_reporte(capsys)
    assert not any(f"ok{i}" in _seccion(rep, "status") for i in range(4))


def test_bearing_en_una_nota_de_paper_es_schema_viejo(toy_vault, capsys):
    """D-21. La **postura** de un paper respecto de una tesis no es propiedad del paper: depende de
    la tesis, y un paper puede tocar varias. Vive en la tabla de evidencia de la hipótesis. Dejarlo
    en el paper obligaba a elegir una sola postura para todas."""
    mk_note(cfg.PAPERS, "2020Bear", {"tags": ["paper"], "bibcode": "2020Bear",
                                     "thesis_links": ["hip"], "bearing": "supports"})
    link_from_index(toy_vault, "2020Bear")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1 and "2020Bear" in _seccion(rep, "bearing")


# ── Tanda 8 · issue 8.6 (D-56 + D-23 + D-32) ──────────────────────────────────────────────────

def test_data_local_no_bloquea_ni_toca_disco(toy_vault, capsys, monkeypatch):
    """D-56. `data_local` apunta a datos de la máquina del usuario: **no** es verificable desde otro
    clon, así que validar su existencia produciría un hallazgo falso en cada máquina ajena."""
    write_gt(toy_vault, [])
    mk_note(cfg.STARS, "test_star", {"tags": ["star"], "name": "Estrella Test", "slug": "test_star",
                                     "data_local": "/no/existe/en/ningun/lado",
                                     "planets": [], "activity_indicators_expected": ["S-index"],
                                     "P_rot_days": None},
            "P_rot 34 d [[2020X]].\n")
    link_from_index(toy_vault, "test_star")
    rc, rep = run_lint_reporte(capsys)
    assert "data_local" not in _seccion(rep, "⛔"), "no puede bloquear"


def test_paper_sin_ningun_destino_bloquea(toy_vault, capsys):
    # @inv INV-94
    """D-23. Un paper sin `stars`, sin `thesis_links` y sin `methods` no pertenece a nada: no
    aparece en ningún roll-up y no lo alcanza ninguna síntesis. Hoy sólo caería como huérfano, y ni
    eso si alguien lo linkea — por eso se siembra CON link entrante."""
    mk_note(cfg.PAPERS, "2020Nada", {"tags": ["paper"], "bibcode": "2020Nada",
                                     "stars": [], "thesis_links": [], "methods": []})
    link_from_index(toy_vault, "2020Nada")
    rc, rep = run_lint_reporte(capsys)
    assert rc == 1 and "2020Nada" in _seccion(rep, "sin destino")


# ── D-49 · lente desincronizada, por ficha y offline ─────────────────────────

def _registro_con_lente(slug: str, lente, bibcodes=("2020A",)):
    """Registro versionado con UNA búsqueda. `lente=None` simula el registro pre-1.10.3 (la corrida
    no la guardó): el caso adversario del cero inventado."""
    b = {"fecha": "2026-01-01", "query": "q", "rows": 10, "n_total": len(bibcodes),
         "n_core": len(bibcodes), "n_candidates": 0, "bibcodes": list(bibcodes)}
    if lente is not None:
        b["lente"] = lente
    cfg.save_registro(slug, {"slug": slug, "busquedas": [b]})


def _paper_de_la_estrella(stem, *, titulo, abstract, relevance="high", keywords=()):
    return mk_note(cfg.PAPERS, stem,
                   {"tags": ["paper"], "bibcode": stem, "title": titulo,
                    "stars": ["Estrella Test"], "keywords": list(keywords),
                    "relevance": relevance, "methods": []},
                   f"# {titulo}\n\n## Abstract\n{abstract}\n")


LENTE_VIEJA = {"facets": {"actividad": "activity|starspot", "rv": "radial velocity"},
               "require": [], "min_facets": 1, "noise_doctypes": ["catalog", "proposal"]}


def test_lente_igual_calla(toy_vault, capsys):
    """El caso NORMAL: la lente del registro es la vigente → ni hallazgo ni costo (el diff no corre).
    Es lo que hace viable el chequeo: cuando habla, hay algo real.  @inv INV-58"""
    _registro_con_lente("test_star", LENTE_VIEJA)
    _paper_de_la_estrella("2020A", titulo="Starspot evolution", abstract="activity")
    link_from_index(toy_vault, "2020A")
    rc, rep = run_lint_reporte(capsys)
    assert "Lente desincronizada" in rep, "la categoría tiene que existir en el reporte"
    assert _seccion(rep, "Lente desincronizada").strip() == "", "lente igual: sin hallazgos"


def test_lente_cambiada_reporta_diff_por_ficha(toy_vault, capsys):
    """D-49. Se saca la faceta `actividad` de la lente vigente → el paper que sólo matcheaba por
    ella deja de ser core, y el hallazgo NOMBRA su stem (contar no es accionable).  @inv INV-58"""
    obj = dict(cfg.load_objective())
    obj["relevance"] = {"facets": {"rv": "radial velocity"}, "noise_doctypes": ["catalog", "proposal"]}
    write_yaml(cfg.OBJECTIVE_YAML, obj)
    _registro_con_lente("test_star", LENTE_VIEJA, bibcodes=("2020A", "2021B"))
    _paper_de_la_estrella("2020A", titulo="Starspot evolution", abstract="activity everywhere")
    _paper_de_la_estrella("2021B", titulo="Radial velocity survey", abstract="radial velocity")
    link_from_index(toy_vault, "2020A", "2021B")
    rc, rep = run_lint_reporte(capsys)
    sec = _seccion(rep, "Lente desincronizada")
    assert "faceta `actividad` eliminada" in sec, sec
    assert "2020A" in sec and "1 saldrían" in sec.replace("−", ""), sec
    assert "2021B" not in sec, "el que sigue matcheando `rv` no se mueve"
    assert rc == 0, "es backlog: no bloquea"


def test_registro_sin_lente_no_evaluado(toy_vault, capsys):
    """Adversario del cero inventado (D-43): sin `lente` guardada no hay contra qué comparar. El
    hallazgo lo DICE; callarlo dejaría la ficha leyéndose como clasificada con la regla vigente."""
    _registro_con_lente("test_star", None)
    _paper_de_la_estrella("2020A", titulo="Starspot evolution", abstract="activity")
    link_from_index(toy_vault, "2020A")
    rc, rep = run_lint_reporte(capsys)
    sec = _seccion(rep, "Lente desincronizada")
    assert "no evaluado" in sec and "test_star" in sec, sec


def test_solo_cambian_los_doctypes_de_ruido_se_declara_no_evaluable(toy_vault, capsys):
    """La nota de paper no guarda `doctype`: un cambio que sólo mueve `noise_doctypes` es real y el
    diff offline no lo puede ver. Se declara — devolver `+0/−0` se leería como 'no movió nada'."""
    obj = dict(cfg.load_objective())
    obj["relevance"] = {"facets": {"actividad": "activity|starspot", "rv": "radial velocity"},
                        "noise_doctypes": ["catalog"]}
    write_yaml(cfg.OBJECTIVE_YAML, obj)
    _registro_con_lente("test_star", LENTE_VIEJA)
    _paper_de_la_estrella("2020A", titulo="Starspot evolution", abstract="activity")
    link_from_index(toy_vault, "2020A")
    rc, rep = run_lint_reporte(capsys)
    sec = _seccion(rep, "Lente desincronizada")
    assert "no lo puede evaluar" in sec and "doctype" in sec, sec
    assert "entrarían" not in sec, "no puede afirmar un delta que no midió"


# ── D-50 · fuga por auto-referencia + `downstream: []` ───────────────────────

def _con_downstream(nombres):
    obj = dict(cfg.load_objective())
    obj["downstream"] = nombres
    write_yaml(cfg.OBJECTIVE_YAML, obj)


def _concepto_con_prosa(prosa: str, stem="conc"):
    return mk_note(cfg.CONCEPTS / "methods", stem,
                   {"tags": ["concept"], "name": stem, "confidence": "medium"},
                   f"# {stem}\n\n## Síntesis\n{prosa}\n")


def test_autoreferencia_detectada(toy_vault, capsys):
    """D-50, los dos casos reales medidos: el nombre propio del consumidor en posición de consumo
    (`downstream: [ICA]`) y el marcador genérico, que no necesita declarar nada."""
    _con_downstream(["ICA"])
    _concepto_con_prosa("El valor lo usan los scripts de ICA para fijar el corte.", "conc_nombre")
    _concepto_con_prosa("Supuesto de trabajo del pipeline: la señal es aditiva.", "conc_generico")
    link_from_index(toy_vault, "conc_nombre", "conc_generico")
    rc, rep = run_lint_reporte(capsys)
    sec = _seccion(rep, "Fuga de implementación")
    assert "conc_nombre" in sec and "ICA" in sec, sec
    assert "conc_generico" in sec and "supuesto de trabajo" in sec.lower(), sec
    assert rc == 0, "es WARN: no bloquea"


def test_downstream_vacio_apagado(toy_vault, capsys):
    """Sin `downstream` declarado esa mitad queda apagada y **no** hay WARN de ausencia: declarar a
    quién le sirve la bóveda es opcional por diseño (a diferencia de `concept_areas`)."""
    _concepto_con_prosa("El valor lo usan los scripts de ICA para fijar el corte.", "conc_nombre")
    link_from_index(toy_vault, "conc_nombre")
    rc, rep = run_lint_reporte(capsys)
    assert "conc_nombre" not in _seccion(rep, "Fuga de implementación")
    assert "downstream" not in rep, "la ausencia no se reporta"


def test_nombre_declarado_en_uso_legitimo_no_marca(toy_vault, capsys):
    """El nombre pelado NO alcanza: en esta bóveda `ICA` es además un método real (está en
    `relevance.facets`). Marcar cada mención volvería la categoría un rojo permanente — y un rojo
    permanente se deja de mirar. Lo que delata la fuga es el nombre en posición de CONSUMIDOR."""
    _con_downstream(["ICA"])
    _concepto_con_prosa("ICA es una separación ciega de fuentes [[2000Hyvarinen]]; aplicando ICA "
                        "a las CCF se recuperan las componentes.", "conc_metodo")
    link_from_index(toy_vault, "conc_metodo")
    rc, rep = run_lint_reporte(capsys)
    assert "conc_metodo" not in _seccion(rep, "Fuga de implementación")


def test_blockquote_sigue_exento(toy_vault, capsys):
    """Regresión: el blockquote meta (frontera/alcance/disclaimer de capa-LLM) puede NOMBRAR la
    frontera sin violarla. Si el scan lo mirara, cada cabecera estampada sería un hallazgo."""
    _con_downstream(["ICA"])
    _concepto_con_prosa("> Alcance: nada de esto describe los scripts de ICA ni su pipeline.",
                        "conc_bq")
    link_from_index(toy_vault, "conc_bq")
    rc, rep = run_lint_reporte(capsys)
    assert "conc_bq" not in _seccion(rep, "Fuga de implementación")


# ── D-34 · el alcance declarado de una hipótesis, y cómo queda corto ─────────

def _hipotesis(stem, cuerpo, status="abierta"):
    return mk_note(cfg.CONCEPTS / "hypotheses", stem,
                   {"tags": ["hypothesis"], "name": stem, "status": status}, cuerpo)


def _fulltexts(slug, n):
    d = cfg.FULLTEXT / slug
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (d / f"20{i:02d}Paper{i}.txt").write_text("texto", encoding="utf-8")


def test_alcance_sin_declarar_marca(toy_vault, capsys):
    # @inv INV-92
    """D-34. Sin alcance escrito, un veredicto negativo se lee como UNIVERSAL: "no existe evidencia"
    en vez de "no hay evidencia en estos 190 papers". Es *afirmar de más* aplicado a la conclusión."""
    _hipotesis("hip_pelada", "# hip\n\nEl corpus no dice nada [[2020X]].\n")
    mk_note(cfg.PAPERS, "2020X", {"tags": ["paper"], "bibcode": "2020X"})
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "test_star" / "2020X.txt").write_text(
        "El corpus no dice nada sobre eso. " * 20, encoding="utf-8")
    link_from_index(toy_vault, "hip_pelada", "2020X")
    rc, rep = run_lint_reporte(capsys)
    sec = _seccion(rep, "Alcance de hipótesis")
    assert "hip_pelada" in sec and "universal" in sec, sec
    # backlog: la nota no es inválida, le falta una declaración. Se comprueba mirando el reporte,
    # no sólo el rc — la nota mínima dispara otros backlogs (cabecera, sin verificar) y un rc==0
    # obligaría a sembrarlos todos, que es tuning de fixture, no la propiedad que interesa.
    assert not any(l.startswith("## ⛔") and "Alcance" in l for l in rep.split("\n"))


def test_alcance_quedo_corto_marca(toy_vault, capsys):
    # @inv INV-92
    """El alcance CRECE: se declaró sobre 2 papers y hoy esos slugs tienen 5. El veredicto se testeó
    contra un universo que ya no es el vigente — misma familia de staleness que los pares."""
    _fulltexts("test_star", 5)
    _hipotesis("hip_corta",
               "# hip\n\n> Alcance 2026-01-01 · estrellas: [test_star] · 2 papers · 1 con hits\n\n"
               "Sostiene [[2020X]].\n")
    link_from_index(toy_vault, "hip_corta")
    rc, rep = run_lint_reporte(capsys)
    sec = _seccion(rep, "Alcance de hipótesis")
    assert "hip_corta" in sec and "+3" in sec and "2026-01-01" in sec, sec


def test_alcance_al_dia_calla(toy_vault, capsys):
    """El caso normal no puede ser ruido: si el universo no creció, la hipótesis no aparece."""
    _fulltexts("test_star", 2)
    _hipotesis("hip_ok",
               "# hip\n\n> Alcance 2026-01-01 · estrellas: [test_star] · 2 papers · 1 con hits\n\n"
               "Sostiene [[2020X]].\n")
    link_from_index(toy_vault, "hip_ok")
    rc, rep = run_lint_reporte(capsys)
    assert "hip_ok" not in _seccion(rep, "Alcance de hipótesis")


def test_alcance_con_slug_inexistente_lo_nombra(toy_vault, capsys):
    """No se puede contar lo que no existe: se DICE cuál falta. Contar sobre un universo recortado
    en silencio daría "quedó corto" al revés — el alcance se vería sobrado."""
    _fulltexts("test_star", 5)
    _hipotesis("hip_typo",
               "# hip\n\n> Alcance 2026-01-01 · estrellas: [test_star, tets_star] · 2 papers\n\n"
               "Sostiene [[2020X]].\n")
    link_from_index(toy_vault, "hip_typo")
    rc, rep = run_lint_reporte(capsys)
    sec = _seccion(rep, "Alcance de hipótesis")
    assert "tets_star" in sec and "typo" in sec, sec


def test_la_tabla_estampada_de_planetas_no_cuenta_como_prosa(toy_vault, capsys):
    """Desde que `## Planetas` dejó de ser ```dataviewjs``` y pasó a tabla materializada
    (D-11/INV-81), sus celdas satisfacen el patrón `|\\s*b\\s*|` del proxy de autosuficiencia: TODO
    planeta quedaba "discutido en prosa" en una ficha con cero líneas escritas. Es el mismo falso
    limpio permanente que el bug del `[^*]*`, por otra puerta — y peor, porque lo introduce la
    propia máquina."""
    write_gt(toy_vault, [gt_planet(l) for l in "bcd"])
    import make_notes as mn
    mn.write_star_note("test_star", force=False)
    link_from_index(toy_vault, "test_star")
    rc, rep = run_lint_reporte(capsys)
    sec = _seccion(rep, "Campos incompletos")
    for l in "bcd":
        assert f"planeta {l} en frontmatter pero no discutido en prosa" in sec, sec


def test_solo_prosa_descuenta_las_secciones_estampadas():
    body = ("## Resumen\nEsto lo escribió alguien: la señal **b** es real.\n\n"
            "## Planetas (ground-truth NASA Exoplanet Archive) (1)\n| c |\n\n"
            "## Huecos\nfalta el P_rot de la **d**.\n")
    p = lint.solo_prosa(body)
    assert "señal **b**" in p and "**d**" in p
    assert "| c |" not in p, "la tabla estampada no es prosa"


# ── INV-19 · capas colgadas de una entidad que ya no existe ─────────────────

def test_capas_colgadas_se_reportan(toy_vault, capsys):
    """La otra mitad de INV-19 ("ni archivo huérfano en `raw/`") no tenía red: había chequeo para
    `wiki/` y para el ground-truth, y **ninguno** para el registro, `raw/{pdfs,fulltext}/` ni
    `build/`. Borrar una entidad a mano —que era el único modo— dejaba esos directorios ahí."""
    cfg.save_busqueda("fantasma", {"fecha": "2026-01-01", "n_total": 1})
    (cfg.PDFS / "fantasma").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "fantasma").mkdir(parents=True, exist_ok=True)
    (cfg.ROOT / "build" / "fantasma").mkdir(parents=True, exist_ok=True)
    rc, rep = run_lint_reporte(capsys)
    sec = _seccion(rep, "Capas colgadas")
    for capa in ("registro/fantasma", "raw/pdfs/fantasma", "raw/fulltext/fantasma", "build/fantasma"):
        assert capa in sec, f"falta {capa}: {sec}"
    assert "ÚNICO artefacto no regenerable" in sec, "el registro es el peor de los cuatro"
    assert rc == 0, "backlog: no invalida lo que hay"


def test_la_entidad_viva_no_se_reporta_colgada(toy_vault, capsys):
    """El caso normal no puede ser ruido."""
    cfg.save_busqueda("test_star", {"fecha": "2026-01-01", "n_total": 1})
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    rc, rep = run_lint_reporte(capsys)
    assert "test_star" not in _seccion(rep, "Capas colgadas")


def test_el_registro_de_red_no_es_una_capa_colgada(toy_vault, capsys):
    """`_red.yaml` es de la bóveda entera (la pasada de red, D-46), no de un sujeto: reportarlo
    sería un hallazgo permanente que nadie puede cerrar."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    (cfg.REGISTRO / "_red.yaml").write_text("ultima_pasada: 2026-08-24\n", encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)
    assert "_red" not in _seccion(rep, "Capas colgadas")


# ── 10.1 · el lint expone su resultado estructurado ─────────────────────────

def test_collect_y_main_coinciden(toy_vault, capsys):
    """`collect()` es lo que `main()` renderiza: mismo contenido, mismo exit. Es el assert que hace
    del refactor un cambio de FORMA y no de comportamiento (el otro instrumento es el golden, que
    compara byte a byte sobre 900 notas)."""
    mk_note(cfg.CONCEPTS / "methods", "huerfano", {"tags": ["concept"], "name": "huerfano"}, "# h\n")
    res = lint.collect()
    rc, rep = run_lint_reporte(capsys)
    assert lint.render(res) == rep.rstrip("\n") or lint.render(res) == rep
    assert (rc == 1) == (res.n_block() > 0)
    assert res.por_clave("orphans") is not None and len(res.por_clave("orphans")) == 1


def test_la_severidad_se_declara_una_sola_vez(toy_vault):
    """El defecto que 10.1 cierra: la severidad vivía **dos veces** —el título decía "(backlog)" o
    llevaba "⚠ WARN", y la pertenencia a la tupla de `n_block` decidía el exit— sin nada que las
    atara. Agregar una categoría bloqueante y olvidarla en `n_block` (o al revés) no rompía ningún
    test. Ahora el exit se deriva de la tabla, así que el título y el exit no pueden divergir."""
    res = lint.collect()
    incoherentes = []
    for c in res.categorias:
        dice_backlog = "(backlog" in c.titulo
        dice_warn = "WARN" in c.titulo
        if c.severidad == lint.SEV_BLOQUEANTE and (dice_backlog or dice_warn):
            incoherentes.append(f"{c.clave}: bloqueante pero el título dice backlog/WARN")
        if c.severidad == lint.SEV_WARN and not dice_warn:
            incoherentes.append(f"{c.clave}: SEV_WARN pero el título no lo dice")
        if c.severidad == lint.SEV_BACKLOG and dice_warn:
            incoherentes.append(f"{c.clave}: SEV_BACKLOG con título de WARN")
    assert incoherentes == [], "\n  ".join(incoherentes)


def test_las_claves_de_categoria_son_unicas_y_estables(toy_vault):
    """`clave` es lo estable; el título es prosa que se reescribe. Un consumidor (el tablero, un
    test, otro script) matchea por clave — y dos claves iguales lo mandarían a la categoría
    equivocada en silencio."""
    claves = [c.clave for c in lint.collect().categorias]
    assert len(claves) == len(set(claves)), [k for k in claves if claves.count(k) > 1]
    assert len(claves) == 61, f"el reporte tiene {len(claves)} categorías, se esperaban 61"


def test_el_modo_cierre_solo_cambia_el_exit_de_los_pares(toy_vault):
    """R-1: el MISMO detector, dos severidades según el momento. `SEV_CIERRE` es la única que
    cambia de lado según el flag; ninguna otra puede depender de él."""
    sin, con = lint.collect(cierre=False), lint.collect(cierre=True)
    assert [c.clave for c in sin.categorias] == [c.clave for c in con.categorias]
    solo_con = {c.clave for c in con.bloquean()} - {c.clave for c in sin.bloquean()}
    assert solo_con <= {"stale_pairs"}, solo_con


def test_el_lint_no_depende_de_nada_que_ci_no_instale():
    """El lint es la compuerta de CI y su job instala **sólo `pyyaml`** — su docstring lo promete:
    *"Sólo necesita pyyaml + stdlib"*. Esa promesa no tenía test, y se rompió: al mover la
    comparación de lentes (D-49), `lint.py` pasó a importar `query_ads`, que importa `requests`.
    En CI el import fallaba, el fallo caía en «no evaluado» —que cuenta para el exit— y **el lint
    salía 1 sobre una bóveda sana**. Un chequeo que existe para no producir falsos limpios se
    volvió un falso rojo por una dependencia que no necesita.

    Se mira el árbol de imports transitivo de `lint.py` contra lo que el workflow instala."""
    import ast
    import sys as _sys
    raiz = Path(__file__).resolve().parent.parent
    permitidos = set(_sys.stdlib_module_names) | {"yaml"}
    # los módulos propios se recorren; lo que no es propio ni permitido, es dependencia externa
    vistos, pendientes, externas = set(), ["lint"], set()
    while pendientes:
        mod = pendientes.pop()
        if mod in vistos:
            continue
        vistos.add(mod)
        f = raiz / "scripts" / f"{mod}.py"
        if not f.exists():
            if mod not in permitidos:
                externas.add(mod)
            continue
        # SÓLO imports de nivel de módulo: los que se pagan al importar. `fetch_ground_truth`
        # importa `numpy`/`astroquery` **dentro de sus funciones** justamente para que el lint pueda
        # tomarle `msini_earth` sin arrastrarlos — un import lazy no es una dependencia del lint, y
        # contarlo haría que este test exigiera desinstalar la razón por la que el diseño funciona.
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        cuerpo = list(arbol.body)
        for node in list(cuerpo):          # un import dentro de `try:`/`if` de nivel módulo cuenta
            if isinstance(node, (ast.Try, ast.If)):
                cuerpo += node.body + node.orelse + getattr(node, "finalbody", [])
                for h in getattr(node, "handlers", []):
                    cuerpo += h.body
        for node in cuerpo:
            if isinstance(node, ast.Import):
                pendientes += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                pendientes.append(node.module.split(".")[0])
    assert externas == set(), (
        f"`lint.py` arrastra dependencias que el job de CI no instala: {sorted(externas)}. "
        f"El workflow corre `pip install pyyaml` y nada más — o se agrega al workflow (y se "
        f"justifica: el lint es OFFLINE), o el import no va.")


def test_ground_truth_cambiado_pide_la_marca_y_con_la_marca_baja(toy_vault, capsys):
    """AUD-42: la TERCERA marca en línea, `⚠desactualizado`.

    El ancla de fuente (D-20) hashea `raw/fulltext/**/*.txt` y **nunca** el ground-truth, así que un
    valor que NEA corrige cambia bajo los pies de la prosa que ya lo citó sin que ninguna fila de
    verificación se entere. `sweep_external.aplicar_ground_truth` deja `_cambios` en el JSON; acá se
    pide la marca. Mismo criterio que D-47 con las fuentes retractadas: **no se borra la afirmación**
    —puede seguir siendo correcta— se la hace visible.
    """
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps({
        "star": "Estrella Test", "slug": "test_star", "host": {}, "planets": [],
        "_cambios": [{"campo": "host.teff_K", "viejo": 5344, "nuevo": 5390, "fecha": "2026-08-24"}],
    }), encoding="utf-8")
    mk_note(toy_vault.STARS, "test_star", {"tags": ["star"], "name": "Estrella Test",
                                           "slug": "test_star"},
            "La temperatura efectiva es 5344 K.\n")
    link_from_index(toy_vault, "test_star")
    _, out = run_lint_reporte(capsys)
    assert "NEA cambió host.teff_K" in out and "5344" in out and "5390" in out
    assert "Ground-truth que cambió bajo la prosa, sin marcar" in out

    # con la marca puesta baja a informativa (visible, no destruida)
    mk_note(toy_vault.STARS, "test_star", {"tags": ["star"], "name": "Estrella Test",
                                           "slug": "test_star"},
            "La temperatura efectiva es 5344 K ⚠desactualizado.\n")
    _, out = run_lint_reporte(capsys)
    assert "Ground-truth que cambió bajo la prosa, sin marcar (backlog) (0)" in out
    assert "prosa marcada" in out


def test_inferencia_con_wikilink_que_no_es_bibcode_no_es_premisa():
    """INV-86 dice «≥1 **bibcode**», no «≥1 wikilink».  @inv INV-86

    El filtro era `"[[" not in ...`, así que `(inferencia de [[gp-kernels]])` —un link a una nota de
    concepto— pasaba limpia: el verify no tiene ahí ningún `.txt` que leer, que es justo lo que la
    marca promete. Encontrado por la pasada `/auditar` del 2026-08-24 (AUD-01)."""
    assert lint.inferencias_sin_premisas("Vale X (inferencia de [[2020Foo]]).") == []
    assert lint.inferencias_sin_premisas("Vale X (inferencia).") == ["(inferencia)"]
    assert lint.inferencias_sin_premisas("Vale X (inferencia de [[gp-kernels]]).") != [], \
        "una premisa que no es bibcode no es premisa"


def test_cita_sin_fulltext_en_una_ficha_de_estrella_es_precondicion(toy_vault, capsys):
    """INV-03: «Para cada clave de cita hay fulltext local **o** la nota declara por qué no. No hay
    tercer estado silencioso.»  @inv INV-03

    `in_verifiable_note` era sólo `queries/` + `concepts/`, así que la cita sin `.txt` en una ficha
    de estrella —donde el contrato pone el estándar de autosuficiencia y donde más `[[bibcode]]` se
    acumulan— no producía NINGÚN hallazgo (AUD-03)."""
    mk_note(toy_vault.PAPERS, "2020citC...1..1C", {"tags": ["paper"]}, "")
    mk_note(toy_vault.STARS, "test_star", {"tags": ["star"], "name": "Estrella Test",
                                           "slug": "test_star"},
            "Según [[2020citC...1..1C]] pasa X.\n")
    link_from_index(toy_vault, "test_star", "2020citC...1..1C")
    _, out = run_lint_reporte(capsys)
    assert "cita 2020citC...1..1C sin fulltext" in out


def test_nota_con_citas_y_sin_bloque_de_verificacion_no_cierra(toy_vault, capsys):
    """INV-79: «Una nota con citas sin verificar … **no cierra** la operación que la tocó.»

    D-5 dice que la nota NACE 100% verificada, así que «citas y ningún bloque» es el estado anómalo.
    Caía en el backlog `unverified` mientras `stale_pairs` —el detector que sí contaba para el exit
    de `--cierre`— sólo se poblaba con notas que YA tienen bloque: la nota nunca verificada se
    escapaba por abajo (AUD-04)."""
    d = toy_vault.FULLTEXT / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2020citC...1..1C.txt").write_text("texto legible del paper " * 20, encoding="utf-8")
    mk_note(toy_vault.PAPERS, "2020citC...1..1C", {"tags": ["paper"]}, "")
    mk_note(toy_vault.CONCEPTS / "methods", "con-citas", {"tags": ["methods"]},
            "Afirmación citada [[2020citC...1..1C]].\n")
    link_from_index(toy_vault, "con-citas", "2020citC...1..1C")
    assert lint.collect(cierre=True).n_block() > 0
    assert lint.collect(cierre=False).n_block() == 0, "sin --cierre es backlog, no bloqueante"


def test_los_bibcodes_estampados_no_cuentan_como_citas(toy_vault, capsys):
    """Un `[[bibcode]]` de la tabla `## Papers` NO es una cita: es metadata que estampó `make_notes`.

    `verify-citations` no puede chequearla —no hay afirmación que contrastar contra la fuente, hay
    una fila—, así que contarla hacía que una ficha recién creada, con la prosa todavía en
    plantilla, naciera pidiendo verificación de decenas de pares imposibles, y reportando como "no
    verificable" cada paper del universo sin fulltext. Medido en el clean-room del 2026-08-25:
    117 "citas" en la ficha de tau_ceti, **0** de ellas en prosa.

    Es el mismo lazo que `solo_prosa` ya cierra para los otros proxies (INV-81): un artefacto que se
    mide a sí mismo siempre da el resultado que su propia existencia produce.

    Se fija por los DOS lados: una cita **en prosa** tiene que seguir contando, o el arreglo apagaría
    el detector entero — que es justo la falla que el detector existe para no producir.
    """
    (cfg.STARS / "solo_tabla.md").write_text(
        "---\nname: Solo Tabla\nslug: solo_tabla\ntags: [star]\n---\n# Solo Tabla\n\n"
        "## Resumen\n_(plantilla sin escribir)_\n\n"
        "## Papers (1 · 0 sintetizados en esta ficha)\n\n"
        "| Bibcode | Año |\n|---|---|\n| [[2020Fantasma....1..1F]] | 2020 |\n",
        encoding="utf-8")
    (cfg.STARS / "con_prosa.md").write_text(
        "---\nname: Con Prosa\nslug: con_prosa\ntags: [star]\n---\n# Con Prosa\n\n"
        "## Resumen\nEl período es 4.3 d [[2020Fantasma....1..1F]].\n",
        encoding="utf-8")
    cats = {c.clave: c for c in lint.collect().categorias}
    sin_verificar = {stem for stem, _ in cats["unverified"].items}
    no_verificables = {stem for stem, _ in cats["unverifiable"].items}
    assert "solo_tabla" not in sin_verificar, \
        "la ficha cuya única 'cita' está en la tabla estampada no tiene nada que verificar"
    assert "solo_tabla" not in no_verificables, \
        "un paper del universo sin fulltext no es una 'cita no verificable' de la ficha"
    assert "con_prosa" in sin_verificar, \
        "una cita EN PROSA sin bloque de verificación tiene que seguir saliendo"
    assert "con_prosa" in no_verificables, \
        "una cita EN PROSA sin fulltext tiene que seguir saliendo"


def test_methods_sin_pagina_destino_es_backlog_no_bloqueante(toy_vault, capsys):
    """`methods` sin nota destino sale como backlog propio, no como wikilink roto bloqueante.

    La asimetría con `thesis_links` —que sí bloquea— es deliberada y está en el comentario del
    detector: un `thesis_links` nombra un concepto que `ingest-theme` **crea** en la misma operación
    que lo siembra; `methods` lo puebla la extracción de `ingest-star`, que no crea conceptos.
    Bloquear acá le pediría a `ingest-star` cerrar algo que no está en su cadena.
    """
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020Metodo.md").write_text(
        "---\nbibcode: 2020Metodo\nstars: [Estrella Test]\nmethods: [gp_qp, sin_nota_alguna]\n"
        "year: 2020\ntags: [paper]\n---\n# T\n", encoding="utf-8")
    (cfg.CONCEPTS / "methods").mkdir(parents=True, exist_ok=True)
    (cfg.CONCEPTS / "methods" / "gp_qp.md").write_text(
        "---\nname: gp_qp\ntags: [concept]\n---\n# GP QP\n", encoding="utf-8")
    cats = {c.clave: c for c in lint.collect().categorias}
    colgados = {m for m, _ in cats["dangling_methods"].items}
    assert colgados == {"sin_nota_alguna"}, colgados
    assert cats["dangling_methods"].severidad == lint.SEV_BACKLOG, \
        "bloquear acá le pide a ingest-star cerrar algo que no está en su cadena"


def _ficha_con_inventario(toy_vault, filas: str, n_papers: int = 2):
    """Ficha que cita `n_papers` papers YA extraídos, con el inventario en el estado que se pase."""
    bibs = [f"2020ext{i}...1..1E" for i in range(n_papers)]
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    for b in bibs:
        (cfg.PAPERS / f"{b}.md").write_text(
            f"---\nbibcode: {b}\nstars: [Estrella Test]\nmethods: [gp]\nrole: [aplicacion]\n"
            f"year: 2020\ntags: [paper]\nno_sintetizado: 'poda'\n---\n# T\n", encoding="utf-8")
    citas = " ".join(f"[[{b}]]" for b in bibs)
    mk_note(toy_vault.STARS, "con_inv", {"tags": ["star"]},
            f"# con_inv\n\n## Resumen\nAlgo {citas}.\n\n## Inventario por eje\n{filas}\n")


PLANTILLA = "| Eje | Paper | Dice |\n|---|---|---|\n|  |  |  |"
LLENO = "| Eje | Paper | Dice |\n|---|---|---|\n| P_rot | [[2020ext0...1..1E]] | 47 d |"


def test_inventario_en_plantilla_con_dos_extraidos_es_backlog(toy_vault, capsys):
    """#101: la red que le faltaba al paso 3b. `CLAUDE.md` lo llama el paso con más apalancamiento y
    el que más fácil se saltea «porque su producto no se nota si falta», y su única red medía si el
    paper LLEGÓ (#75), no si el contraste OCURRIÓ."""
    _ficha_con_inventario(toy_vault, PLANTILLA)
    cats = {c.clave: c for c in lint.collect().categorias}
    assert [h[0] for h in cats["contrast_missing"].items] == ["con_inv"]
    assert cats["contrast_missing"].severidad == lint.SEV_BACKLOG


def test_inventario_lleno_no_dispara(toy_vault, capsys):
    """El lado positivo: una fila real apaga el hallazgo."""
    _ficha_con_inventario(toy_vault, LLENO)
    cats = {c.clave: c for c in lint.collect().categorias}
    assert cats["contrast_missing"].items == ()


def test_sin_seccion_es_la_escotilla_declarada_no_un_hallazgo(toy_vault, capsys):
    """La plantilla dice: «si no hay ningún eje en disputa, borrar la sección y decirlo en el log».
    Ausencia = declarado; presente-y-vacío = saltado. Sin esa asimetría el detector castigaría
    justo a quien siguió la instrucción."""
    _ficha_con_inventario(toy_vault, PLANTILLA)
    p = toy_vault.STARS / "con_inv.md"
    p.write_text(p.read_text(encoding="utf-8").split("## Inventario por eje")[0], encoding="utf-8")
    cats = {c.clave: c for c in lint.collect().categorias}
    assert cats["contrast_missing"].items == ()


def test_con_un_solo_paper_extraido_no_dispara(toy_vault, capsys):
    """Con un solo paper no hay contra qué contrastar: pedir el inventario sería ruido fijo, y un
    hallazgo que aparece siempre se deja de mirar."""
    _ficha_con_inventario(toy_vault, PLANTILLA, n_papers=1)
    cats = {c.clave: c for c in lint.collect().categorias}
    assert cats["contrast_missing"].items == ()


def test_lente_no_evaluable_nombra_el_motivo_correcto(tmp_path, monkeypatch, capsys):
    """#106: el mensaje decía SIEMPRE «la nota no guarda `doctype`». Sobre un cambio de umbral eso
    es la explicación de otro caso — el reporte atribuye mal, que es peor que no decir nada."""
    import lib_config as c
    assert c.lens_textual_changed(["fundacional_min_citas 2000 → 30"]) is False
    assert c.lens_textual_changed(["noise_doctypes ['a'] → ['b']"]) is False


# ── fulltext sin nota: extracción pagada que no alcanza ninguna síntesis (#108) ──
def test_fulltext_sin_nota_es_backlog(toy_vault, capsys):
    """Medido: al angostar la `query` de un tema, sus registros salen de `ads.json`, `make_notes`
    deja de escribirles nota y el `.txt` queda en disco — 10 de 30 en una bóveda real. Nadie lo
    miraba: es el hermano simétrico de la «cita no verificable» (bibcode citado SIN .txt)."""
    d = cfg.FULLTEXT / "ica"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2012ApJ...747...12W.txt").write_text("texto", encoding="utf-8")
    lint.main([])
    out = capsys.readouterr().out
    assert "2012ApJ...747...12W.txt" in out
    assert "sin su nota" in out
    assert "make_notes.py --theme ica" in out          # el arreglo, nombrado


def test_fulltext_con_nota_no_es_hallazgo(toy_vault, capsys):
    d = cfg.FULLTEXT / "ica"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2012ApJ...747...12W.txt").write_text("texto", encoding="utf-8")
    (cfg.PAPERS / "2012ApJ...747...12W.md").write_text(
        "---\nbibcode: 2012ApJ...747...12W\ntags: [paper]\nthesis_links: [ica]\n---\n# T\n",
        encoding="utf-8")
    lint.main([])
    assert "sin su nota" not in capsys.readouterr().out


# ── `sources:` sin procedencia: el último cuadrante de curación sin registro (#111) ──
def test_source_sin_via_ni_motivo_bloquea(toy_vault, capsys):
    """Los otros tres cuadrantes ya registran quién y por qué (extra_core D-58, drop #51,
    drop-source #81). En off-ADS **todo** entra por decisión de alguien, así que sin el campo la
    pregunta «¿lo pediste vos, lo propuso el descubrimiento, o salió de un reporte?» no tiene
    respuesta — medido: los 40 papers que la bóveda anterior tenía entraron los 40 a mano y no hay
    forma de saber cuáles pidió el usuario."""
    (cfg.CONFIG / "themes.yaml").write_text(
        "ica:\n  title: T\n  area: methods\n  concept: ica\n  source: local-pdfs\n"
        "  sources:\n    - key: 1994Comon\n      pdf: x.pdf\n", encoding="utf-8")
    rc = lint.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "ica/1994Comon" in out and "sin `via`" in out
    assert "--accept-source" in out                    # el arreglo, nombrado


def test_source_con_via_fuera_del_vocabulario_bloquea(toy_vault, capsys):
    (cfg.CONFIG / "themes.yaml").write_text(
        "ica:\n  title: T\n  area: methods\n  concept: ica\n  source: local-pdfs\n"
        "  sources:\n    - key: 1994Comon\n      pdf: x.pdf\n      via: inventado\n"
        "      motivo: porque si\n", encoding="utf-8")
    assert lint.main([]) == 1
    assert "fuera del vocabulario cerrado" in capsys.readouterr().out


def test_source_completa_no_bloquea(toy_vault, capsys):
    (cfg.CONFIG / "themes.yaml").write_text(
        "ica:\n  title: T\n  area: methods\n  concept: ica\n  source: local-pdfs\n"
        "  sources:\n    - key: 1994Comon\n      pdf: x.pdf\n      via: usuario\n"
        "      motivo: canon del metodo\n", encoding="utf-8")
    lint.main([])
    assert "sin `via`" not in capsys.readouterr().out


def test_log_sin_entrada_se_reporta(toy_vault, capsys):
    """#118: lo que escribe un SCRIPT se registra solo (`cadena` del registro); lo que escribe el
    LLM depende de que se acuerde. Es el único paso salteable sin red. Medido sobre un tema real:
    22 pasos de cadena registrados, 0 entradas en el log."""
    import yaml
    reg = toy_vault.VAULT / "config" / "registro"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "elslug.yaml").write_text(
        yaml.safe_dump({"slug": "elslug", "cadena": [{"paso": "query_ads", "fecha": "2026-03-01"}]}),
        encoding="utf-8")
    toy_vault.LOG.write_text("# log\n\n## 2026-01-01 — otra cosa\n", encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    linea = [l for l in rep.splitlines() if l.startswith("## 📓 Operación sin entrada")]
    assert linea, rep
    assert int(linea[0].rsplit("(", 1)[1].rstrip(")")) == 1, linea[0]


def test_log_con_su_entrada_no_se_reporta(toy_vault, capsys):
    """El caso normal tiene que ser silencioso, o la categoría se vuelve ruido que nadie mira."""
    import yaml
    reg = toy_vault.VAULT / "config" / "registro"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "elslug.yaml").write_text(
        yaml.safe_dump({"slug": "elslug", "cadena": [{"paso": "query_ads", "fecha": "2026-03-01"}]}),
        encoding="utf-8")
    toy_vault.LOG.write_text("# log\n\n## 2026-03-01 — ingest-theme: elslug\n", encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    linea = [l for l in rep.splitlines() if l.startswith("## 📓 Operación sin entrada")]
    assert linea, rep
    assert int(linea[0].rsplit("(", 1)[1].rstrip(")")) == 0, linea[0]


# ── #121 · `--cierre <slug>`: el gate de cierre se acota al sujeto que la operación tocó ─────────
# El razonamiento de R-1 —«un par sin verificar significa que NO TERMINASTE»— es correcto y estaba
# aplicado al alcance equivocado: la bóveda entera. Medido al cerrar un tema real, el único
# bloqueante era la deuda de OTRA estrella (147 citas sin bloque), así que el gate arrancaba en rojo
# y seguía en rojo sin importar lo que la operación hiciera. Un gate que hay que auditar a mano,
# categoría por categoría, para saber si el rojo es tuyo, dejó de ser un gate.

def _dos_sujetos(toy_vault):
    """Dos sujetos con deuda de cierre INDEPENDIENTE: una estrella y un tema.

    La estrella `test_star` y el tema `gp` tienen cada uno una nota con citas y sin bloque de
    `verify-citations` (la categoría `unverified`, severidad de cierre)."""
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "Procesos gaussianos", "area": "methods",
                                        "concept": "procesos-gaussianos"}})
    for slug, bib in (("test_star", "2020ajeC...1..1A"), ("gp", "2021propC...1..1B")):
        d = toy_vault.FULLTEXT / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{bib}.txt").write_text("texto legible del paper " * 20, encoding="utf-8")
    mk_note(toy_vault.PAPERS, "2020ajeC...1..1A", {"tags": ["paper"], "stars": ["Estrella Test"]}, "")
    mk_note(toy_vault.PAPERS, "2021propC...1..1B", {"tags": ["paper"], "methods": ["gp"]}, "")
    mk_note(toy_vault.STARS, "test_star", {"tags": ["star"], "slug": "test_star"},
            "Afirmación de la estrella [[2020ajeC...1..1A]].\n")
    mk_note(toy_vault.CONCEPTS / "methods", "procesos-gaussianos", {"tags": ["methods"]},
            "Afirmación del tema [[2021propC...1..1B]].\n")
    link_from_index(toy_vault, "test_star", "procesos-gaussianos",
                    "2020ajeC...1..1A", "2021propC...1..1B")


def test_el_cierre_acotado_no_cuenta_la_deuda_del_otro_sujeto(toy_vault):
    """El caso medido: cerrar un tema no se frena por lo que le falta a una estrella ajena.

    Y el simétrico, que es lo que impide que el flag sea una escotilla: la deuda PROPIA del sujeto
    sigue contando. Acotar el alcance no es apagar el gate.  @inv INV-105"""
    _dos_sujetos(toy_vault)
    def deuda(res):
        return {a for a, _ in res.en_alcance(res.por_clave("unverified"))}

    assert deuda(lint.collect(cierre=True)) == {"test_star", "procesos-gaussianos"}, \
        "sin alcance, las dos deudas frenan"
    assert deuda(lint.collect(cierre=True, slug="gp")) == {"procesos-gaussianos"}, "sólo la propia"
    assert deuda(lint.collect(cierre=True, slug="test_star")) == {"test_star"}, "y el simétrico"
    # la categoría se sigue reportando ENTERA: lo que cambia es qué cuenta para el exit
    assert len(lint.collect(cierre=True, slug="gp").por_clave("unverified")) == 2


def test_el_alcance_no_debilita_a_los_bloqueantes(toy_vault):
    """⛔ El alcance acota SÓLO la severidad de cierre. Un bloqueante ajeno sigue frenando.

    Si no, `--cierre <slug>` sería un gate MÁS DÉBIL que un `lint` pelado —que hoy sale 1 con
    cualquier bloqueante, venga de donde venga— y el paso de cierre de una operación pasaría a
    garantizar menos que la pasada de higiene. Es la inversión exacta de para qué existe el flag.

    @inv INV-105"""
    _dos_sujetos(toy_vault)
    mk_note(toy_vault.CONCEPTS / "methods", "otro-tema", {"tags": ["methods"]},
            "Link a una página que no existe: [[pagina-fantasma]].\n")
    link_from_index(toy_vault, "test_star", "procesos-gaussianos", "otro-tema",
                    "2020ajeC...1..1A", "2021propC...1..1B")
    gp = lint.collect(cierre=True, slug="gp")
    rotos = gp.por_clave("broken")
    assert len(rotos) == 1 and gp.en_alcance(rotos) == rotos.items, \
        "un bloqueante NO se acota por slug"
    assert "broken" in {c.clave for c in gp.bloquean()}, "el wikilink roto ajeno frena igual"


def test_el_alcance_junta_las_tres_poblaciones(toy_vault):
    """El alcance de un tema son su nota Y sus papers, por las tres vías que existen.

    (a) la nota se llama por `concept`, que NO es el slug; (b) el paper cuyo `.txt` vive bajo el
    slug; (c) el paper RETRO-LINKEADO, cuyo artefacto vive bajo otro slug y que sólo se alcanza por
    el frontmatter — y por `methods`, no sólo por `thesis_links` (D-24: las dos llaves viven en
    papers distintos y quedarse con una pierde la mitad)."""
    _dos_sujetos(toy_vault)
    mk_note(toy_vault.PAPERS, "2019retroC...1..1C",
            {"tags": ["paper"], "stars": ["Estrella Test"], "thesis_links": ["gp"]}, "")
    alcance = entity.notas_del_slug("gp")
    assert "procesos-gaussianos" in alcance, "(a) la nota del tema se llama por `concept`"
    assert "2021propC...1..1B" in alcance, "(b) el paper con artefacto bajo el slug"
    assert "2019retroC...1..1C" in alcance, "(c) el retro-linkeado, sólo visible por frontmatter"
    assert "2020ajeC...1..1A" not in alcance, "el paper del otro sujeto no entra"


def test_un_slug_inexistente_no_da_un_verde_inventado(toy_vault, capsys):
    """Acotar a una entidad que no existe daría 0 hallazgos EN ALCANCE, o sea exit 0 sobre una
    bóveda con deuda: el falso limpio que este lint existe para no producir. Se rehúsa.  @inv INV-105"""
    _dos_sujetos(toy_vault)
    with pytest.raises(ValueError, match="entidad desconocida"):
        lint.collect(cierre=True, slug="no-existe")
    assert lint.main(["--cierre", "no-existe"]) == 2


def test_el_resultado_se_etiqueta_con_el_slug_pedido(toy_vault):
    """El alcance se captura ANTES del barrido: `collect` rebindea `slug` como variable de loop en
    cuatro lugares, así que leerlo al final etiquetaba el resultado con el último slug que tocó el
    barrido — un alcance inventado, y encima plausible. Medido: `collect(slug=None)` volvía
    diciendo `slug='tau_ceti'`."""
    _dos_sujetos(toy_vault)
    write_gt(toy_vault, [gt_planet()])          # puebla los loops que usan `slug` adentro de collect
    assert lint.collect(cierre=True).slug is None
    assert lint.collect(cierre=True, slug="gp").slug == "gp"


def test_el_reporte_acotado_no_esconde_la_deuda_ajena(toy_vault):
    """El modo de falla obvio de la idea: que acotar el exit acote también el REPORTE, y la deuda
    de al lado se vuelva invisible. El ítem ajeno se sigue listando, marcado."""
    _dos_sujetos(toy_vault)
    txt = lint.render(lint.collect(cierre=True, slug="gp"))
    assert "test_star" in txt, "la deuda ajena se sigue listando entera"
    assert "ajeno a `gp`" in txt, "y marcada como que no frena"
    assert "Alcance del exit: `gp`" in txt


# ── #117 · la FILA declara contra qué archivo se verificó; el lint no lo infiere ─────────────────

def test_ocr_verificado_contra_el_PDF_no_vence_al_re_extraer_el_txt(toy_vault, capsys):
    """El caso medido, y el que la regla de #113 no cubría.

    Una fuente `fulltext_source: ocr` **también** se verifica a veces contra el PDF —el OCR del
    editor destruye los símbolos— y eso pasó con 3 de las 5 fuentes marcadas de un tema real. La
    regla vieja miraba `symbols_lost` en el frontmatter, así que para estas hasheaba el `.txt`:
    **17 pares volvieron «vencidos por fuente»** sin que nadie tocara nada. Acá la fuente NO está
    marcada `symbols_lost` y la fila dice `pdf:`; re-extraer el `.txt` no la mueve.

    @inv INV-107"""
    ft = _con_ancla(toy_vault, CUERPO)
    (toy_vault.PDFS / "slug").mkdir(parents=True, exist_ok=True)
    pdf = toy_vault.PDFS / "slug" / "2020citC...1..1C.pdf"
    pdf.write_bytes(b"%PDF-1.4\n el escaneo del editor \xff\n")
    nota = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    nota.write_text(nota.read_text(encoding="utf-8").replace(
        f"txt:{lb.source_hash(ft)}", f"pdf:{lb.bytes_hash(pdf)}"), encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 0, "nace verificada contra el PDF que declara"

    ft.write_text("otro texto re-extraido\n", encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 0, "el `.txt` no es su fuente: re-extraerlo no la vence"

    pdf.write_bytes(b"%PDF-1.4\n otro escaneo \xfe\n")
    _, rep = run_lint_reporte(capsys)
    assert _n_vencidos(rep) == 1, "y el archivo que SÍ declaró, sí la vence"


def test_fila_sin_declarar_archivo_no_se_adivina(toy_vault, capsys):
    """Una celda `Hash fuente` sin prefijo es la plantilla anterior a 1.54.0: **no consta** contra
    qué archivo se verificó. Inferirlo del frontmatter es exactamente lo que fabricaba pares
    vencidos, así que se declara no evaluable y se migra — no se adivina ni se da por limpio
    (D-43).  @inv INV-107"""
    _con_ancla(toy_vault, CUERPO, kind=None)
    rc, rep = run_lint_reporte(capsys)
    assert "no declara contra qué archivo" in rep
    assert "--migrate-verif-archivo" in rep, "el hallazgo trae su comando de migración"
    assert _n_vencidos(rep) == 0, "no se cuenta DOS veces: o es sin declarar, o es vencido"
    assert rc == 1, "bloqueante: un bloque que nadie puede evaluar no es un bloque limpio"


def test_fila_que_declara_un_archivo_ausente_no_da_limpio(toy_vault, capsys):
    """Dice haberse verificado contra el PDF y el PDF no está: el hash no se puede comparar. Es
    «no evaluado», que no es «al día».  @inv INV-107"""
    ft = _con_ancla(toy_vault, CUERPO)
    nota = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    nota.write_text(nota.read_text(encoding="utf-8").replace(
        f"txt:{lb.source_hash(ft)}", "pdf:aaaaaaaaaa"), encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)
    assert "ese archivo no está en la bóveda" in rep
    assert rc == 1


def test_pending_sin_motivo_se_reporta_pero_no_bloquea(toy_vault, capsys):
    """#80: la categoría sola no dice si alguien está consiguiendo la fuente o si nadie la miró
    nunca. El motivo no se puede **inventar** —a diferencia del archivo de #117, que se deduce del
    hash—, así que esto es backlog: nombra la nota para que alguien lo escriba.  @inv INV-108"""
    mk_note(toy_vault.PAPERS, "2001Libro",
            {"tags": ["paper"], "thesis_links": ["ica"], "pending_source": "adquisicion",
             "doi": "10.1/x"}, "")
    mk_note(toy_vault.CONCEPTS / "methods", "ica", {"tags": ["methods"]}, "Tema.\n")
    link_from_index(toy_vault, "ica", "2001Libro")
    rc, rep = run_lint_reporte(capsys)
    assert "sin `pending_motivo`" in rep
    assert rc == 0, "backlog: una fuente sin conseguir no invalida ninguna afirmación"


def test_pending_fuera_del_vocabulario_se_nombra(toy_vault, capsys):
    """Un `pending` que nadie valida deja al consumidor leyendo un valor que no significa nada —
    la familia de `role` y de `via`. En la config aborta; acá, sobre una nota ya escrita, se
    nombra.  @inv INV-108"""
    mk_note(toy_vault.PAPERS, "2001Typo",
            {"tags": ["paper"], "thesis_links": ["ica"], "pending_source": "paywal",
             "pending_motivo": "x", "doi": "10.1/x"}, "")
    mk_note(toy_vault.CONCEPTS / "methods", "ica", {"tags": ["methods"]}, "Tema.\n")
    link_from_index(toy_vault, "ica", "2001Typo")
    _, rep = run_lint_reporte(capsys)
    assert "fuera del vocabulario" in rep


def test_documento_largo_sin_alcance_se_reporta(toy_vault, capsys):
    """#80: si la unidad de cita no es la línea, la fuente es un documento largo y casi nunca entró
    entera. Sin `alcance`, el chequeo de completitud de `verify-citations` no puede distinguir un
    recorte deliberado de una omisión.  @inv INV-109"""
    mk_note(toy_vault.PAPERS, "2001Libro",
            {"tags": ["paper"], "thesis_links": ["ica"], "unidad_cita": "pagina"}, "")
    mk_note(toy_vault.CONCEPTS / "methods", "ica", {"tags": ["methods"]}, "Tema.\n")
    link_from_index(toy_vault, "ica", "2001Libro")
    rc, rep = run_lint_reporte(capsys)
    assert "sin `alcance`" in rep and rc == 0, "backlog: no invalida lo que la nota afirma"


def test_unidad_de_cita_invalida_bloquea(toy_vault, capsys):
    """Vocabulario cerrado, misma severidad que `role`: un typo deja el campo mudo para la única
    operación que existe para consumirlo.  @inv INV-109"""
    mk_note(toy_vault.PAPERS, "2001Libro",
            {"tags": ["paper"], "thesis_links": ["ica"], "unidad_cita": "paginas",
             "alcance": "cap. 6"}, "")
    mk_note(toy_vault.CONCEPTS / "methods", "ica", {"tags": ["methods"]}, "Tema.\n")
    link_from_index(toy_vault, "ica", "2001Libro")
    rc, rep = run_lint_reporte(capsys)
    assert "fuera del vocabulario" in rep and rc == 1


def test_core_sin_pdf_no_se_confunde_con_sin_leer(toy_vault, capsys):
    """#90: el lint reportaba **dos situaciones opuestas con el mismo mensaje**.

    | situación | qué hay que hacer | dueño |
    |---|---|---|
    | bajado, con fulltext, nadie lo leyó | leerlo | el agente |
    | nunca se pudo bajar | conseguir la fuente | el usuario |

    Las dos salían como *«paper relevante sin `methods` (sin extraer)»*, así que el backlog mezclaba
    trabajo del agente con fuentes que faltan: dos colas con dueños distintos, imposibles de
    priorizar o derivar.  @inv INV-112"""
    # bajado y sin leer: sigue siendo "falta extraerlo"
    d = toy_vault.FULLTEXT / "slug"; d.mkdir(parents=True, exist_ok=True)
    (d / "2020Leido..1..1A.txt").write_text("texto legible " * 40, encoding="utf-8")
    mk_note(toy_vault.PAPERS, "2020Leido..1..1A",
            {"tags": ["paper"], "stars": ["Estrella Test"], "relevance": "high"}, "")
    # nunca se consiguió: sin fulltext y sin PDF
    mk_note(toy_vault.PAPERS, "2020Falta..1..1A",
            {"tags": ["paper"], "stars": ["Estrella Test"], "relevance": "high"}, "")
    mk_note(toy_vault.STARS, "test_star", {"tags": ["star"], "slug": "test_star"}, "Ficha.\n")
    link_from_index(toy_vault, "test_star", "2020Leido..1..1A", "2020Falta..1..1A")
    _, rep = run_lint_reporte(capsys)
    sin_fuente = [l for l in rep.splitlines() if "2020Falta" in l]
    sin_leer = [l for l in rep.splitlines() if "2020Leido" in l]
    assert any("sin fuente" in l for l in sin_fuente), \
        "el que nunca se bajó se reporta como fuente faltante (cola del usuario)"
    assert not any("sin fuente" in l for l in sin_leer), \
        "el que está en disco y nadie leyó sigue siendo trabajo del agente"


def test_localizador_que_contradice_al_archivo_vigilado(toy_vault, capsys):
    """#122: `Evidencia` y `Hash fuente` dicen lo mismo desde ángulos distintos, y nada los cruzaba.

    Una fila puede citar `p. 628` y vigilar el `.txt`: el hash cuida un archivo del que esa cita no
    salió, se dispara en falso al re-extraerlo y no ve que el PDF cambió. Es el modo de falla de
    #117 sobrevivido a #117 — medido, 11 de 114 filas de un concepto real.

    Backlog y no bloqueante: el par puede estar perfectamente verificado; lo que hay que hacer es
    re-anclarlo.  @inv INV-113"""
    ft = _con_ancla(toy_vault, CUERPO)
    nota = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    t = nota.read_text(encoding="utf-8")
    t = t.replace("| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |",
                  "| # | Afirmación (extracto) | Fuente | Veredicto | Evidencia | Ancla | Hash fuente | Condición |")
    t = t.replace("|---|---|---|---|---|---|---|", "|---|---|---|---|---|---|---|---|")
    t = t.replace("| soportada | ", '| soportada | "la cita" (p. 628) | ')
    nota.write_text(t, encoding="utf-8")
    _, rep = run_lint_reporte(capsys)
    assert "cita una PÁGINA y la fila vigila el `.txt`" in rep
    cat = lint.collect().por_clave("verif_localizador")
    assert cat.severidad == lint.SEV_BACKLOG and len(cat) == 1, \
        "backlog: el par puede estar bien verificado, lo que hay que hacer es re-anclarlo"
    assert lint.collect().por_clave("stale_pairs").items == (), \
        "y NO se cuenta además como vencido: es un hallazgo propio"


def test_veredicto_sin_resolver_en_el_bloque_bloquea(toy_vault, capsys):
    """#91: el lint leía el bloque `## Verificación de citas` **sólo por su encabezado** —¿existe?
    ¿está fresco?— y nunca su contenido. La columna `Veredicto` no la miraba nadie.

    Entonces esto pasaba limpio: una fila `no-soportada` sentada bajo un encabezado que se lee como
    garantía. Eso es **una afirmación que la bóveda hace y que su propia fuente no respalda** — el
    contrato dice que cada falla se RESUELVE (bajar la afirmación, reasignar la cita, marcar
    `inferencia`, o taguear la disputa), no que se registre y se deje.

    Bloqueante: es la frontera dura, igual que una fuente retractada citada.  @inv INV-117"""
    _con_ancla(toy_vault, CUERPO)
    nota = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    nota.write_text(nota.read_text(encoding="utf-8").replace("| soportada |", "| no-soportada |"),
                    encoding="utf-8")
    rc, rep = run_lint_reporte(capsys)
    assert "SIN RESOLVER" in rep, "la categoría se nombra"
    assert "afirma algo que su propia fuente no respalda" in rep, "y el hallazgo dice qué hacer"
    assert rc == 1
    cat = lint.collect().por_clave("verif_sin_resolver")
    assert cat.severidad == lint.SEV_BLOQUEANTE and len(cat) == 1


def test_contradice_tambien_cuenta_y_soportada_no(toy_vault, capsys):
    """`contradice` es el otro veredicto que exige acción (corrección o disputa tagueada). Y el
    caso normal —todo `soportada`— no dispara nada: si lo hiciera, el detector sería ruido y se
    dejaría de mirar.  @inv INV-117"""
    _con_ancla(toy_vault, CUERPO)
    assert lint.collect().por_clave("verif_sin_resolver").items == ()
    nota = toy_vault.CONCEPTS / "methods" / "nota-verif.md"
    nota.write_text(nota.read_text(encoding="utf-8").replace("| soportada |", "| contradice |"),
                    encoding="utf-8")
    assert len(lint.collect().por_clave("verif_sin_resolver")) == 1
