"""Tests del GENERADOR mismo (`sembrar_corpus`/`Censo`/fixtures) — la red que le falta a código
nuevo. NO son los tests de catálogo de §3.1-3.5 del plan (esos son otra ola, sobre categorías del
lint que ya tienen su propio test en `tests/test_lint.py` con una nota sembrada a mano); acá se
prueba que EL GENERADOR se comporta como promete: determinismo, censo↔disco, un corpus limpio da
lint exit 0 (el test más importante — si esto no vale, el generador no modela lo que dice
modelar), cada anomalía soportada da EXACTAMENTE K, `vintage="1.11.0"` bloquea con las categorías
de schema viejo, y las validaciones de entrada (anomalía no soportada, capacidad excedida,
vintage+anomalias) fallan rápido en vez de sembrar un corpus incoherente.

Todo este archivo es tier `poblada` (corpus a escala: segundos, no milisegundos — no toca el
tier 0, que sigue corriendo con `-m "not poblada and not instancia"`, ver pytest.ini), salvo el
único test de `instancia_real` cuyo fixture homónimo es opt-in y auto-marcado abajo.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import lib_config as cfg
import lint

from generador import hash_tree

pytestmark = pytest.mark.poblada

THIS_DIR = Path(__file__).resolve().parent


# ── helpers de lectura del reporte (NO stdout — ver tests/README.md, "Corolario que ya mordió dos
# veces": la última línea de stdout es la RUTA del reporte, que vive bajo el tmpdir de pytest cuyo
# nombre incluye el del test, así que un assert de substring ahí puede matchear el PATH). ──────────

def _run_lint_reporte() -> tuple[int, str]:
    rc = lint.main()
    reporte = (cfg.ROOT / "outputs" / f"lint-{dt.date.today().isoformat()}.md").read_text(
        encoding="utf-8")
    return rc, reporte


def _categoria(reporte: str, contiene: str) -> tuple[int, list[str]]:
    """(conteo, stems) de la categoría cuyo título contiene `contiene`. Los stems son el texto
    antes de ` → ` de cada línea `- ...` de la sección (hasta el próximo `## ` o el final)."""
    lines = reporte.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## ") and contiene in l), None)
    assert start is not None, f"categoría no encontrada en el reporte: {contiene!r}"
    m = re.search(r"\((\d+)\)\s*$", lines[start])
    assert m, f"título sin conteo: {lines[start]!r}"
    n = int(m.group(1))
    stems = []
    for l in lines[start + 1:]:
        if l.startswith("## "):
            break
        if l.startswith("- "):
            stems.append(l[2:].split(" → ", 1)[0].strip())
    assert len(stems) == n, f"{contiene!r}: título dice {n} pero hay {len(stems)} líneas listadas"
    return n, stems


# Las 12 categorías BLOQUEANTES (n_block en lint.py) por un substring distintivo de su título.
BLOQUEANTES = (
    "Wikilinks rotos", "Frontmatter no parseable", "Papers RETRACTADOS", "Notas huérfanas",
    "Contradicciones ground-truth", "masa inconsistente con m", "thesis_links sin página destino",
    "disputes: ref de una posición", "disputes mal formadas", "disputes en el schema viejo",
    "Juicio de triage en build", "`role` fuera del vocabulario",
)


# ── determinismo ─────────────────────────────────────────────────────────────────────────────

def test_determinismo_mismo_seed_mismo_hash(sembrar):
    paths_a, _ = sembrar(n_papers=60, n_stars=3, n_concepts=8, seed=7)
    ha = hash_tree(paths_a.VAULT)
    paths_b, _ = sembrar(n_papers=60, n_stars=3, n_concepts=8, seed=7)
    hb = hash_tree(paths_b.VAULT)
    assert ha == hb


def test_determinismo_seed_distinto_hash_distinto(sembrar):
    paths_a, _ = sembrar(n_papers=60, n_stars=3, n_concepts=8, seed=1)
    ha = hash_tree(paths_a.VAULT)
    paths_b, _ = sembrar(n_papers=60, n_stars=3, n_concepts=8, seed=2)
    hb = hash_tree(paths_b.VAULT)
    assert ha != hb


# ── censo == disco ───────────────────────────────────────────────────────────────────────────

def test_censo_coincide_con_lo_sembrado_en_disco(sembrar):
    paths, censo = sembrar(n_papers=80, n_stars=3, n_concepts=10, seed=3)

    stems_en_disco = {p.stem for p in paths.PAPERS.glob("*.md")}
    assert stems_en_disco == set(censo.paper_stems)
    assert len(censo.paper_stems) == censo.n_papers == 80

    slugs_en_disco = {p.stem for p in paths.STARS.glob("*.md")}
    assert slugs_en_disco == set(censo.star_slugs)
    assert len(censo.star_slugs) == censo.n_stars == 3

    concept_stems_en_disco = {p.stem for p in paths.CONCEPTS.glob("*/*.md")}
    assert concept_stems_en_disco == set(censo.concept_stems)

    gt_en_disco = {p.stem for p in paths.GROUND_TRUTH.glob("*.json")}
    assert gt_en_disco == set(censo.star_gt) == set(censo.star_slugs)

    # fulltext: legible + ilegible es exactamente lo que hay en disco bajo raw/fulltext/**
    ft_en_disco = {p.stem for p in paths.FULLTEXT.glob("**/*.txt")}
    assert ft_en_disco == censo.fulltext_legible | censo.fulltext_illegible
    assert censo.fulltext_legible.isdisjoint(censo.fulltext_illegible)

    # relevancia: una entrada por paper, vocabulario cerrado
    assert set(censo.relevance) == set(censo.paper_stems)
    assert set(censo.relevance.values()) <= {"high", "medium", "low"}

    # extraídos: subconjunto de papers, con `methods` REALMENTE poblado en disco
    assert censo.extracted <= set(censo.paper_stems)
    import lib_config as _c
    for stem in censo.extracted:
        fm = _c.split_fm((paths.PAPERS / f"{stem}.md").read_text(encoding="utf-8"))
        assert fm.get("methods"), f"{stem} está en censo.extracted pero methods no está poblado"


# ── el test más importante: corpus limpio (sin anomalías) → lint exit 0 ─────────────────────

def test_corpus_limpio_da_lint_exit_0(boveda_poblada):
    """Si esto no vale, el generador no modela la bóveda que dice modelar (ver el criterio de
    éxito del task). Usa el árbol de SESIÓN (params por default: 900 papers/4 estrellas/20
    conceptos) para no re-sembrar — `arbol_poblado` ya lo sembró una vez."""
    censo = boveda_poblada.censo
    assert censo.n_papers == 900
    rc, reporte = _run_lint_reporte()
    assert rc == 0, reporte[:4000]
    for titulo in BLOQUEANTES:
        n, _ = _categoria(reporte, titulo)
        assert n == 0, f"{titulo!r}: {n} hallazgo(s) en un corpus que debería estar limpio"


def test_corpus_limpio_chico_tambien_da_lint_exit_0(sembrar):
    """El caso grande (900) es el que importa para el criterio de éxito, pero un `n` chico separado
    corrobora que la limpieza no es un artefacto de escala (p. ej. un pool de citas que sólo
    alcanza a cubrir todo a partir de cierto tamaño)."""
    _, censo = sembrar(n_papers=40, n_stars=2, n_concepts=5, seed=11)
    rc, reporte = _run_lint_reporte()
    assert rc == 0, reporte[:4000]
    for titulo in BLOQUEANTES:
        n, _ = _categoria(reporte, titulo)
        assert n == 0, f"{titulo!r}: {n} hallazgo(s)"


# ── anomalías: cada categoría soportada da EXACTAMENTE K, con los stems del censo ────────────

def test_anomalia_huerfanas_exacta(sembrar):
    _, censo = sembrar(n_papers=100, n_stars=3, n_concepts=15, seed=20,
                       anomalias={"huerfanas": 5})
    rc, reporte = _run_lint_reporte()
    assert rc == 1
    n, stems = _categoria(reporte, "Notas huérfanas")
    assert n == 5
    assert sorted(stems) == sorted(censo.anomalias["huerfanas"])


def test_anomalia_thesis_colgantes_exacta(sembrar):
    _, censo = sembrar(n_papers=100, n_stars=3, n_concepts=15, seed=21,
                       anomalias={"thesis_colgantes": 4})
    rc, reporte = _run_lint_reporte()
    assert rc == 1
    n, stems = _categoria(reporte, "thesis_links sin página destino")
    assert n == 4
    assert sorted(stems) == sorted(censo.anomalias["thesis_colgantes"])


def test_anomalia_disputes_colgantes_exacta(sembrar):
    _, censo = sembrar(n_papers=100, n_stars=3, n_concepts=15, seed=22,
                       anomalias={"disputes_colgantes": 4})
    rc, reporte = _run_lint_reporte()
    assert rc == 1
    n, stems = _categoria(reporte, "disputes: ref de una posición")
    assert n == 4
    assert sorted(stems) == sorted(censo.anomalias["disputes_colgantes"])


def test_anomalia_no_sintetizado_exacta(sembrar):
    _, censo = sembrar(n_papers=200, n_stars=3, n_concepts=15, seed=23,
                       anomalias={"no_sintetizado": 4})
    rc, reporte = _run_lint_reporte()
    assert rc == 0          # backlog, NO bloqueante
    n, stems = _categoria(reporte, "Extraído pero no sintetizado")
    assert n == 4
    assert sorted(stems) == sorted(censo.anomalias["no_sintetizado"])


def test_anomalia_cobertura_citas_exacta(sembrar):
    _, censo = sembrar(n_papers=200, n_stars=3, n_concepts=15, seed=24,
                       anomalias={"cobertura_citas": 4})
    rc, reporte = _run_lint_reporte()
    assert rc == 0          # backlog, NO bloqueante
    n, stems = _categoria(reporte, "Cobertura:")
    assert n == 4
    assert sorted(stems) == sorted(censo.anomalias["cobertura_citas"])


def test_anomalia_cabecera_no_estampable_exacta(sembrar):
    _, censo = sembrar(n_papers=100, n_stars=3, n_concepts=15, seed=25,
                       anomalias={"cabecera_no_estampable": 4})
    rc, reporte = _run_lint_reporte()
    assert rc == 0          # backlog, NO bloqueante
    n, stems = _categoria(reporte, "Cabecera no estampable")
    assert n == 4
    assert sorted(stems) == sorted(censo.anomalias["cabecera_no_estampable"])
    # mezcla estrellas + conceptos (K_header_stars = min(K, n_stars) primero) — no todo es concepto
    assert any(s.startswith("star") for s in censo.anomalias["cabecera_no_estampable"])


def test_anomalia_fulltext_ilegible_exacta(sembrar):
    _, censo = sembrar(n_papers=100, n_stars=3, n_concepts=15, seed=26,
                       anomalias={"fulltext_ilegible": 4})
    rc, reporte = _run_lint_reporte()
    assert rc == 0          # backlog, NO bloqueante
    n, stems = _categoria(reporte, "Fulltext ilegible")
    assert n == 4
    # el reporte lista "raw/fulltext/<slug>/<stem>.txt", no el stem pelado — comparamos por sufijo
    assert sorted(Path(s).stem for s in stems) == sorted(censo.anomalias["fulltext_ilegible"])


def test_anomalias_combinadas_no_se_pisan(sembrar):
    """Dos categorías a la vez (una de concepto, una de paper) no deben interferir: cada una da
    exactamente su K, sin filtrarse a la otra."""
    _, censo = sembrar(n_papers=150, n_stars=3, n_concepts=15, seed=27,
                       anomalias={"huerfanas": 3, "fulltext_ilegible": 3})
    rc, reporte = _run_lint_reporte()
    assert rc == 1
    n_h, stems_h = _categoria(reporte, "Notas huérfanas")
    assert n_h == 3
    assert sorted(stems_h) == sorted(censo.anomalias["huerfanas"])
    n_f, stems_f = _categoria(reporte, "Fulltext ilegible")
    assert n_f == 3
    assert sorted(Path(s).stem for s in stems_f) == sorted(censo.anomalias["fulltext_ilegible"])


# ── vintage="1.11.0" ──────────────────────────────────────────────────────────────────────────

def test_vintage_1_11_0_bloquea_con_categorias_de_schema_viejo(sembrar):
    _, censo = sembrar(n_papers=50, n_stars=3, n_concepts=10, seed=30, vintage="1.11.0")
    rc, reporte = _run_lint_reporte()
    assert rc == 1
    n_old_disp, _ = _categoria(reporte, "disputes en el schema viejo")
    assert n_old_disp > 0
    n_legacy_triage, _ = _categoria(reporte, "Juicio de triage en build")
    assert n_legacy_triage == 1                 # un solo build/<slug>/triage.json sembrado
    n_mirror, _ = _categoria(reporte, "Contradicciones ground-truth")
    assert n_mirror > 0                          # mass_earth ausente en planets[] vs GT (#70)
    # sin la línea del generador en NINGUNA ficha/concepto (backlog, no bloqueante, pero real):
    n_headerless, _ = _categoria(reporte, "Cabecera no estampable")
    assert n_headerless == len(censo.star_slugs) + len(censo.concept_stems)
    # papers sin `role`: el vocabulario no puede estar "mal" porque el campo no existe
    n_bad_roles, _ = _categoria(reporte, "`role` fuera del vocabulario")
    assert n_bad_roles == 0


def test_vintage_actual_no_dispara_categorias_de_schema_viejo(sembrar):
    """El contraste del test anterior: con el vintage por default (schema actual) esas mismas
    categorías dan 0 — así el test de arriba prueba de verdad que es EL VINTAGE lo que las
    dispara, no un efecto de los parámetros chicos (n_papers=50, etc.)."""
    sembrar(n_papers=50, n_stars=3, n_concepts=10, seed=30)
    rc, reporte = _run_lint_reporte()
    assert rc == 0
    for titulo in ("disputes en el schema viejo", "Juicio de triage en build",
                  "Contradicciones ground-truth"):
        n, _ = _categoria(reporte, titulo)
        assert n == 0, titulo


# ── validaciones de entrada: fallar rápido, no sembrar un corpus incoherente ────────────────

def test_anomalia_no_soportada_lanza_valueerror(sembrar):
    with pytest.raises(ValueError, match="no soportadas"):
        sembrar(n_papers=20, anomalias={"esto-no-existe": 1})


def test_anomalia_negativa_lanza_valueerror(sembrar):
    with pytest.raises(ValueError, match="entero >= 0"):
        sembrar(n_papers=20, anomalias={"huerfanas": -1})


def test_vintage_viejo_con_anomalias_no_soportado(sembrar):
    with pytest.raises(NotImplementedError, match="vintage='1.11.0'"):
        sembrar(n_papers=20, vintage="1.11.0", anomalias={"huerfanas": 1})


def test_capacidad_de_papers_excedida_lanza_valueerror(sembrar):
    with pytest.raises(ValueError, match="exceden n_papers"):
        sembrar(n_papers=10,
               anomalias={"fulltext_ilegible": 4, "no_sintetizado": 4, "thesis_colgantes": 4})


# ── fixtures: wiring y aislamiento ───────────────────────────────────────────────────────────

def test_boveda_poblada_re_apunta_lib_config(boveda_poblada):
    assert cfg.STARS == boveda_poblada.STARS
    assert cfg.PAPERS == boveda_poblada.PAPERS
    assert len(list(boveda_poblada.PAPERS.glob("*.md"))) == boveda_poblada.censo.n_papers


def test_boveda_poblada_mutable_no_toca_el_arbol_de_sesion(arbol_poblado, boveda_poblada_mutable):
    paths_sesion, censo = arbol_poblado
    slug = censo.star_slugs[0]
    original = (paths_sesion.STARS / f"{slug}.md").read_text(encoding="utf-8")

    mutable_file = boveda_poblada_mutable.STARS / f"{slug}.md"
    assert mutable_file.read_text(encoding="utf-8") == original      # copia fiel al arrancar
    mutable_file.write_text(original + "\n<mutado por el test>\n", encoding="utf-8")

    # el árbol de SESIÓN no se movió un bit
    assert (paths_sesion.STARS / f"{slug}.md").read_text(encoding="utf-8") == original
    assert mutable_file.read_text(encoding="utf-8") != original


def test_boveda_poblada_mutable_censo_apunta_a_la_copia(boveda_poblada_mutable):
    assert boveda_poblada_mutable.censo.paths.ROOT == boveda_poblada_mutable.ROOT


# ── instancia_real: el skip tiene que ser VISIBLE, no silencioso ────────────────────────────

def test_instancia_real_skipea_con_motivo_visible_sin_env():
    """Corrobora en un sub-proceso de pytest AISLADO (no en el proceso de esta suite, que puede o
    no tener ALMAGESTO_INSTANCIA seteada en el entorno del que la corre) que sin la variable el
    fixture `instancia_real` SKIPEA con un mensaje — no pasa en silencio ni falla oscuro."""
    caso = THIS_DIR / "_tmp_check_instancia_skip.py"
    caso.write_text(
        "def test_usa_instancia(instancia_real):\n"
        "    raise AssertionError('no debería llegar acá sin ALMAGESTO_INSTANCIA')\n",
        encoding="utf-8")
    try:
        env = dict(os.environ)
        env.pop("ALMAGESTO_INSTANCIA", None)
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(caso), "-q", "-rs", "-o", "addopts="],
            cwd=str(cfg.ROOT), env=env, capture_output=True, text=True, timeout=60)
    finally:
        caso.unlink(missing_ok=True)
    out = r.stdout + r.stderr
    assert "1 skipped" in out, out
    assert "ALMAGESTO_INSTANCIA no está seteada" in out, out
