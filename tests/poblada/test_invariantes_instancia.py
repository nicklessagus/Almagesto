"""Tier `instancia` (§3.3 del plan de la 7ª auditoría, `tests/poblada/`): invariantes y *ratchet*
sobre una bóveda REAL, no sintética. Es el gate del deploy — corre SÓLO en la máquina del usuario,
opt-in vía `ALMAGESTO_INSTANCIA` (fixture `instancia_real` de `conftest.py`, que copia lo liviano y
symlinkea lo pesado, SIEMPRE read-only sobre la ruta original).

**Por qué existe un archivo aparte de `test_conteos_exactos.py`.** El generador sintético
(`generador.py`) sólo tiene la mugre que se le programa a propósito. Una instancia real tiene la
que nadie inventaría: schemas mezclados de cinco versiones de Almagesto conviviendo en el mismo
corpus, listas YAML en block y en flow style, ediciones a mano, un `raw/ground_truth/ds_tuc.json`
sin su ficha. Este archivo mide eso.

**Dos familias de test, con semántica distinta:**
- **Invariantes duros** (`test_todo_*`, `test_ningun_*`, `test_bibcode_*`, `test_vocabularios_*`,
  `test_campos_obligatorios_*`): afirman `== 0` / `100%` — cosas que valen sobre CUALQUIER corpus
  sano, medidas hoy en verde sobre una instancia real. Si alguna se pone roja, es una regresión real, sin
  techo que perdonarla.
- **Ratchet** (`test_ratchet_categorias_no_superan_el_techo`): la instancia HOY no está limpia (16
  hallazgos bloqueantes + backlog grueso — ver `ratchet_instancia.yaml`), y exigir 0 sería rojo
  permanente hasta que alguien lo silencie. El techo por categoría vive en ese YAML commiteado,
  **sólo puede bajar**, y el archivo documenta cómo actualizarlo.
- **Idempotencia de la cadena sobre datos reales** (`test_idempotencia_ciclo_de_migradores_...`):
  corre el ciclo de migradores/estampadores del deploy real (plan §5) sobre una COPIA MUTABLE de la
  instancia — nunca sobre `instancia_real` en sí, que otros tests de este mismo archivo siguen
  leyendo en la misma sesión — y confirma que cierra el residuo y que la segunda pasada es un no-op
  byte a byte.

**Limitación heredada de la fixture (documentada en su docstring, repetida acá porque afecta
directamente a esta ola de tests):** la copia de `instancia_real` NO es un repo git, así que
`verificación stale` (que el lint mide comparando contra `git log`) degrada a "0 sin mirar nada".
Ningún test de este archivo depende de esa categoría por eso — está deliberadamente fuera del
ratchet (agregarla mediría el degradado de la fixture, no la instancia).

**Regla de oro de este archivo, la que manda sobre cualquier otra:** ningún test escribe sobre
`ALMAGESTO_INSTANCIA`. `instancia_real` ya se audita sola (mtime de `vault/`+`build/` antes/después
de la SESIÓN completa); el test que muta (`test_idempotencia_...`) agrega un cinturón propio, LOCAL
a ese test, comparando mtimes del árbol original antes/después de sí mismo — no hace falta esperar
al teardown de sesión para saber si ESTE test en particular tocó algo que no debía.
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import extract_fulltext
import lib_config as cfg
import lint
import make_notes
import triage

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
from generador import hash_tree   # noqa: E402  (mismo import que test_upgrade.py)

pytestmark = pytest.mark.instancia

RATCHET_FILE = THIS_DIR / "ratchet_instancia.yaml"

_PATH_ATTRS = ("ROOT", "VAULT", "CONFIG", "STARS_YAML", "TOPICS_YAML", "OBJECTIVE_YAML",
              "ADS_KEY_FILE", "REGISTRO", "RAW", "WIKI", "PDFS", "FULLTEXT", "GROUND_TRUTH",
              "STARS", "PAPERS", "CONCEPTS", "QUERIES", "MATRICES", "INDEX", "LOG")

# El re-apuntado de `lib_config` lo hace ahora la fixture `instancia_real` (function-scoped, vía
# `monkeypatch`, que auto-revierte al terminar cada test). Acá vivía un cinturón local que
# restauraba `cfg` al cerrar el módulo, porque el parcheo estaba en el fixture de SESIÓN y dejaba
# las constantes apuntando a la copia de la instancia durante todo el resto de la corrida — un test
# de otro archivo que confiara en `cfg.ROOT` corría contra la instancia sin saberlo. Se arregló en
# `conftest.py` (ver el docstring de `instancia_real`), así que el cinturón ya no hace falta: un
# cinturón por archivo obliga a que el próximo que use el fixture se acuerde de ponerlo.


# ── lectura del reporte del lint (NO stdout — ver tests/README.md, "corolario que ya mordió dos
# veces": la última línea de stdout es la RUTA del reporte, bajo un tmpdir cuyo nombre incluye el
# del test). Reimplementado acá, mismo criterio que test_conteos_exactos.py/test_upgrade.py (no
# importar de esos archivos: no están pensados para eso). ─────────────────────────────────────────

def _run_lint_reporte() -> tuple[int, str]:
    rc = lint.main()
    reporte = (cfg.ROOT / "outputs" / f"lint-{dt.date.today().isoformat()}.md").read_text(
        encoding="utf-8")
    return rc, reporte


def _categoria(reporte: str, contiene: str) -> tuple[int, list[str]]:
    """(conteo, stems) de la categoría cuyo título contiene `contiene`. Ver test_conteos_exactos.py
    para el razonamiento de por qué se valida también que el título coincida con la cantidad de
    líneas listadas (protege contra un título desincronizado del cuerpo)."""
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


# El lint corre UNA sola vez por sesión de este archivo (module-scoped): todos los invariantes
# duros + el ratchet leen el MISMO reporte. Correrlo por test (como hace test_conteos_exactos.py
# sobre corpus sintético, que es barato) sería ~8 corridas × ~5 s sobre el fulltext real de 79 MB —
# sigue entrando en el presupuesto de 60 s, pero no hay motivo: el reporte no cambia entre tests que
# sólo LEEN (nada en este archivo, salvo el test de idempotencia, escribe algo antes del último uso
# compartido de este fixture).
@pytest.fixture(scope="module")
def reporte(instancia_real):
    rc, txt = _run_lint_reporte()
    return rc, txt


# ── invariantes duros: valen hoy en verde sobre una instancia real, sin techo que los perdone ──────────

def test_todo_wikilink_resuelve(reporte):
    """Caza un `[[wikilink]]` que apunta a una nota inexistente (typo de nombre, nota borrada sin
    reparar sus referencias) — medido hoy: 0 sobre ~3600 links reales."""
    rc, txt = reporte
    n, stems = _categoria(txt, "Wikilinks rotos")
    assert n == 0, f"wikilinks rotos: {stems}"


def test_todo_frontmatter_parsea(reporte):
    """Caza una nota cuyo YAML de frontmatter no parsea (título con `:` sin comillas editado a
    mano, frontmatter sin cierre `---`) o cuya forma es inválida (una lista del schema escrita
    escalar) — cualquiera de las dos hace que la nota EVADA en silencio todos los chequeos de su
    tipo. Medido hoy: 0/941 notas."""
    rc, txt = reporte
    n, stems = _categoria(txt, "Frontmatter no parseable")
    assert n == 0, f"frontmatter roto o con forma inválida: {stems}"


def test_ningun_retractado_ninguna_huerfana_masa_consistente(reporte):
    """Tres categorías bloqueantes independientes, agrupadas porque las tres barren el mismo tipo
    de corpus real y las tres dan 0 hoy: ningún paper retractado citado (frontera dura: fuente no
    válida), ninguna nota huérfana (sin links entrantes) y ninguna masa de ground-truth inconsistente
    con la m·sini implícita por K/P/e/M* (atraparía una `best-mass` espuria de NEA)."""
    rc, txt = reporte
    n_ret, s_ret = _categoria(txt, "Papers RETRACTADOS")
    assert n_ret == 0, f"papers retractados citados: {s_ret}"
    n_orf, s_orf = _categoria(txt, "Notas huérfanas")
    assert n_orf == 0, f"notas huérfanas: {s_orf}"
    n_mass, s_mass = _categoria(txt, "masa inconsistente con m")
    assert n_mass == 0, f"masa de ground-truth inconsistente: {s_mass}"


def test_thesis_links_y_disputes_colgantes_y_mal_formadas_en_cero(reporte):
    """Las tres categorías bloqueantes que quedan del set de 12 que suman `n_block` en `lint.py`
    sin cubrir por otro test de este archivo (las otras nueve: wikilinks, frontmatter, retracted,
    huérfanas, masa, `role`, y las dos del ratchet con techo>0 — contradicciones_gt/
    disputes_schema_viejo/triage_legacy). Medido hoy: 0 en las tres. Existe separado de
    `test_ratchet_categorias_no_superan_el_techo` porque ESE test necesita, para chequear que no
    quedó ninguna categoría bloqueante sin cubrir, la lista COMPLETA de títulos bloqueantes — y
    estos tres son la parte de esa lista que no tiene su propio test dedicado en otro lado."""
    rc, txt = reporte
    n_thesis, s_thesis = _categoria(txt, "thesis_links sin página destino")
    assert n_thesis == 0, f"thesis_links colgantes: {s_thesis}"
    n_dd, s_dd = _categoria(txt, "disputes: ref de una posición")
    assert n_dd == 0, f"disputes con ref colgante: {s_dd}"
    n_bd, s_bd = _categoria(txt, "disputes mal formadas")
    assert n_bd == 0, f"disputes mal formadas: {s_bd}"


def test_role_fuera_de_vocabulario_en_cero(reporte):
    """`role` es un vocabulario CERRADO (fundacional/aplicacion/arbitro, #73): un typo lo deja mudo
    para el contraste cross-paper sin que nadie se entere. Medido hoy: 0 papers con `role` fuera del
    vocabulario (la instancia está en 1.11.0, que no tenía el campo — 0 papers lo llevan todavía;
    ver el ratchet `campos_incompletos` para el backlog de poblarlo, y el chequeo directo de
    `test_vocabularios_cerrados_en_todo_el_corpus` para la doble verificación sin pasar por el
    lint)."""
    rc, txt = reporte
    n, stems = _categoria(txt, "`role` fuera del vocabulario")
    assert n == 0, f"role fuera de vocabulario: {stems}"


# ── invariantes duros que NO pasan por el lint (chequeo directo sobre frontmatter) ───────────────
# El lint no valida vocabulario cerrado de TODO campo — `bearing`, `status` de planeta y `source` de
# disputas no tienen categoría propia (sólo `role` la tiene, arriba). Estos barridos son
# independientes del lint: leen el frontmatter directo con el mismo parser (`cfg.split_fm`) que usa
# el tooling, así que no heredan un bug del lector compartido si algún día lo tuviera.

def test_bibcode_es_el_stem_en_todos_los_papers(instancia_real):
    """Contrato de nombrado: el archivo `vault/wiki/papers/<bibcode>.md` tiene que declarar
    `bibcode: <bibcode>` en su frontmatter — es lo que hace resoluble `[[bibcode]]` como wikilink Y
    lo que usa `verify-citations` para encontrar el `.txt`. Medido hoy: 908/908. Un mismatch
    (nota renombrada a mano sin actualizar el campo, o viceversa) desincroniza las dos mitades del
    contrato sin que el lint lo note (no hay categoría dedicada)."""
    papers = sorted(cfg.PAPERS.glob("*.md"))
    assert papers, "no se encontró ningún paper bajo vault/wiki/papers/ — ¿ALMAGESTO_INSTANCIA apunta a la instancia correcta?"
    mismatches = []
    for p in papers:
        fm = cfg.split_fm(p.read_text(encoding="utf-8"))
        if str(fm.get("bibcode")) != p.stem:
            mismatches.append((p.stem, fm.get("bibcode")))
    assert mismatches == [], f"bibcode != nombre de archivo: {mismatches}"


def test_todo_paper_en_papers_lleva_tag_paper(instancia_real):
    """Una nota en `papers/` sin `tags: [paper]` es invisible para TODOS los chequeos de su tipo del
    lint (retracción, PDF↔disco, `role`, cobertura de citas) — el lint la reporta como
    `fm_broken` (bloqueante), así que ya está cubierta por `test_todo_frontmatter_parsea` de forma
    indirecta; este test la aísla para que un fallo diga exactamente "falta el tag", no "frontmatter
    roto" genérico. Medido hoy: 908/908 con el tag."""
    papers = sorted(cfg.PAPERS.glob("*.md"))
    sin_tag = [p.stem for p in papers
               if "paper" not in (cfg.split_fm(p.read_text(encoding="utf-8")).get("tags") or [])]
    assert sin_tag == [], f"papers sin `tags: [paper]`: {sin_tag}"


def test_vocabularios_cerrados_en_todo_el_corpus(instancia_real):
    """Barrido directo (no vía lint) de CADA vocabulario cerrado que CLAUDE.md documenta y que el
    lint no valida con una categoría propia: `bearing` (supports/challenges/method), `relevance`
    (high/medium/low), `confidence` (high/medium/low), `status` de planeta (siempre `confirmed`: es
    lo único que `fetch_ground_truth.py` escribe — NEA sólo entrega planetas confirmados) y `source`
    de las posiciones de una disputa (`ground_truth`, o ausente cuando la posición la sostiene un
    `ref`). Un valor fuera de vocabulario en cualquiera de estos deja mudo el consumidor que lo lee
    (el roll-up por `bearing`, el corte core/no-core por `relevance`, el árbitro de una disputa) sin
    que el lint lo vea — por eso el chequeo es propio, no un espejo de una categoría existente."""
    BEARINGS = {"supports", "challenges", "method"}
    RELEVANCES = {"high", "medium", "low"}
    CONFIDENCES = {"high", "medium", "low"}
    STATUSES = {"confirmed"}
    DISPUTE_SOURCES = {"ground_truth"}

    malos = []
    for p in sorted(cfg.PAPERS.glob("*.md")):
        fm = cfg.split_fm(p.read_text(encoding="utf-8"))
        b = fm.get("bearing")
        if b is not None and str(b) not in BEARINGS:
            malos.append((p.stem, "bearing", b))
        rel = fm.get("relevance")
        if rel is not None and str(rel) not in RELEVANCES:
            malos.append((p.stem, "relevance", rel))
        conf = fm.get("confidence")
        if conf is not None and str(conf) not in CONFIDENCES:
            malos.append((p.stem, "confidence", conf))

    for area_dir in (cfg.STARS, cfg.CONCEPTS):
        if not area_dir.exists():
            continue
        for p in sorted(area_dir.glob("**/*.md")):
            fm = cfg.split_fm(p.read_text(encoding="utf-8"))
            conf = fm.get("confidence")
            if conf is not None and str(conf) not in CONFIDENCES:
                malos.append((p.stem, "confidence", conf))
            for d in (fm.get("disputes") or []):
                if not isinstance(d, dict):
                    continue
                for pos in (d.get("posiciones") or []):
                    if not isinstance(pos, dict):
                        continue
                    src = pos.get("source")
                    if src and str(src) not in DISPUTE_SOURCES:
                        malos.append((p.stem, "disputes.source", src))

    for p in sorted(cfg.STARS.glob("*.md")) if cfg.STARS.exists() else []:
        fm = cfg.split_fm(p.read_text(encoding="utf-8"))
        for pl in (fm.get("planets") or []):
            if not isinstance(pl, dict):
                continue
            st = pl.get("status")
            if st is not None and str(st) not in STATUSES:
                malos.append((p.stem, f"planets[{pl.get('letter')}].status", st))

    assert malos == [], f"valores fuera de vocabulario cerrado: {malos}"


def test_campos_obligatorios_100_por_ciento_por_tipo(instancia_real):
    """Los campos que el schema de CLAUDE.md documenta y que, medido sobre el corpus real, están en
    el 100% de las notas de su tipo — NO el schema completo: campos legítimamente opcionales
    (`role`/`generator`/`fulltext_source`/`pdf_source`/`confidence`/`disputes` — su ausencia es
    backlog conocido, cubierto por el ratchet, no un defecto de forma) quedan deliberadamente
    afuera. Estos son la identidad mínima sin la cual la nota no es ni siquiera direccionable:

    - `papers/`: bibcode, title, first_author, n_authors, year, arxiv_id, doi, bibstem, stars,
      topics, methods, relevance, citation_count, pdf, tags.
    - `stars/`: name, slug, aliases, simbad_id, spectral_type, teff_K, dist_pc, P_rot_days,
      activity_indicators_expected, planets, data_local, methods_applied, tags.
    - `concepts/` (incluye `hypotheses/`): name, aliases, tags.

    "Presente" es `campo in frontmatter`, NO "no nulo": `teff_K: null` es el caso NORMAL del
    espejo #70 (NEA sin el valor) y no es lo que este test vigila — eso es un problema de VALOR, no
    de FORMA, y lo vigila el propio lint (contradicciones ground-truth ↔ ficha, en el ratchet)."""
    PAPER_FIELDS = ("bibcode", "title", "first_author", "n_authors", "year", "arxiv_id", "doi",
                    "bibstem", "stars", "topics", "methods", "relevance", "citation_count", "pdf",
                    "tags")
    STAR_FIELDS = ("name", "slug", "aliases", "simbad_id", "spectral_type", "teff_K", "dist_pc",
                  "P_rot_days", "activity_indicators_expected", "planets", "data_local",
                  "methods_applied", "tags")
    CONCEPT_FIELDS = ("name", "aliases", "tags")

    faltantes = []
    for p in sorted(cfg.PAPERS.glob("*.md")):
        fm = cfg.split_fm(p.read_text(encoding="utf-8"))
        for campo in PAPER_FIELDS:
            if campo not in fm:
                faltantes.append((p.stem, "papers", campo))
    for p in sorted(cfg.STARS.glob("*.md")) if cfg.STARS.exists() else []:
        fm = cfg.split_fm(p.read_text(encoding="utf-8"))
        for campo in STAR_FIELDS:
            if campo not in fm:
                faltantes.append((p.stem, "stars", campo))
    for p in sorted(cfg.CONCEPTS.glob("**/*.md")) if cfg.CONCEPTS.exists() else []:
        fm = cfg.split_fm(p.read_text(encoding="utf-8"))
        for campo in CONCEPT_FIELDS:
            if campo not in fm:
                faltantes.append((p.stem, "concepts", campo))

    assert faltantes == [], f"notas sin un campo obligatorio de su tipo: {faltantes[:30]}" + (
        f" (+{len(faltantes) - 30} más)" if len(faltantes) > 30 else "")


# ── el hueco documentado que SÍ falla hoy: se escribe como test del hallazgo, no se esconde ──────

@pytest.mark.xfail(
    strict=True,
    reason="hueco medido 2026-08-23: raw/ground_truth/ds_tuc.json existe sin su stars/ds_tuc.md — "
           "el espejo #70 barre por GT→ficha (`for gtf in ground_truth/*.json: ... if sf.exists()`) "
           "así que un GT sin ficha nunca lo mira nadie (la inversa, ficha sin GT, sí es hallazgo). "
           "Se cierra creando `stars/ds_tuc.md` (`make_notes.py ds_tuc`) o borrando el GT colgado; "
           "strict=True: si este test empieza a PASAR sin que se haya tocado, es una señal de que "
           "alguien cerró el hueco y hay que borrar el xfail (o de que un lint nuevo lo detecta y "
           "el chequeo directo de acá quedó redundante).")
def test_gt_y_fichas_apareados(instancia_real):
    """Todo `raw/ground_truth/<slug>.json` debería tener su `stars/<slug>.md` (y viceversa — la
    inversa la vigila `incomplete` del lint hoy: "ficha sin GT"). Es el chequeo SIMÉTRICO que hoy no
    existe: el barrido de #70 en `lint.py` itera `ground_truth/*.json` y hace `if sf.exists(): ...
    else: incomplete.append(...)` — así que si la ficha falta SÍ se reporta (dentro de "Campos
    incompletos", agregado con otras 769 cosas); lo que este test aísla es que la contraparte
    exacta (ds_tuc) está documentada y nombrada, no perdida en el ruido del balde grande."""
    gts = {p.stem for p in cfg.GROUND_TRUTH.glob("*.json")} if cfg.GROUND_TRUTH.exists() else set()
    fichas = {p.stem for p in cfg.STARS.glob("*.md")} if cfg.STARS.exists() else set()
    sin_ficha = sorted(gts - fichas)
    assert sin_ficha == [], (
        f"ground-truth sin su ficha de estrella: {sin_ficha} — recreá la ficha "
        f"(`python scripts/make_notes.py <slug>`) o borrá el ground-truth colgado")


# ── ratchet: techo por categoría, commiteado, sólo puede bajar ───────────────────────────────────

# Los 12 títulos que `lint.py::main()` suma en `n_block` (el cómputo del exit code) — mismo orden
# que la tupla `(broken, fm_broken, retracted, orphans, contradictions, mass_issues,
# dangling_thesis, dangling_disputes, bad_roles, bad_disputes, old_disputes, legacy_triage)` de
# `lint.py`. Se usa para RECALCULAR `n_block` a mano a partir del REPORTE (archivo en disco, no
# stdout — la línea `✗ N hallazgo(s)...` sólo se imprime a consola y no se escribe al `.md`, así
# que no hay forma de leerla del reporte; recomputarla acá evita depender de stdout, que
# `tests/README.md` señala como frágil por el motivo opuesto — el path del tmpdir puede matchear
# un substring cualquiera).
BLOQUEANTE_TITULOS = (
    "Wikilinks rotos", "Frontmatter no parseable", "Papers RETRACTADOS", "Notas huérfanas",
    "Contradicciones ground-truth", "masa inconsistente con m", "thesis_links sin página destino",
    "disputes: ref de una posición", "`role` fuera del vocabulario", "disputes mal formadas",
    "disputes en el schema viejo", "Juicio de triage en build",
)


def _cargar_ratchet() -> dict:
    data = yaml.safe_load(RATCHET_FILE.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and isinstance(data.get("categorias"), dict), (
        f"{RATCHET_FILE} no tiene la forma esperada (mapa con clave `categorias`)")
    return data["categorias"]


def test_ratchet_categorias_no_superan_el_techo(reporte):
    """El mecanismo anti-"verde por no mirar" del deploy: `ratchet_instancia.yaml` fija, por
    categoría, un TECHO commiteado que hoy vale exactamente lo medido (documentado en el propio
    YAML, con fecha). Este test:
      1. Para cada categoría del ratchet, el conteo del lint sobre la instancia real no puede
         SUPERAR el techo — si sube, hay una regresión (o deuda nueva) que alguien tiene que mirar
         antes de que este archivo la vuelva a aceptar como "normal".
      2. Si el conteo BAJA del techo, no falla (bajar es la meta), pero emite un `UserWarning` con
         la categoría y el conteo nuevo — la receta para actualizar el YAML está en su propio
         encabezado.
      3. Las categorías bloqueantes del ratchet (`severidad: bloqueante`) tienen que explicar TODO
         el `n_block` que hace que el lint salga con exit 1 hoy — si aparece un hallazgo bloqueante
         por FUERA de las tres categorías del ratchet, esto también se reporta (sería una categoría
         bloqueante nueva que ni el ratchet ni los invariantes duros de arriba están mirando)."""
    rc, txt = reporte
    categorias = _cargar_ratchet()

    excedidos = []
    bajaron = []
    for clave, meta in categorias.items():
        n, _ = _categoria(txt, meta["titulo"])
        techo = meta["techo"]
        if n > techo:
            excedidos.append(f"{clave} ({meta['titulo']!r}): {n} > techo {techo}")
        elif n < techo:
            bajaron.append(f"{clave}: {n} < techo {techo}")

    assert excedidos == [], (
        "categorías del ratchet por encima de su techo — regresión o deuda nueva sin revisar:\n  "
        + "\n  ".join(excedidos))

    if bajaron:
        warnings.warn(
            "categorías del ratchet por DEBAJO de su techo — bajá el techo en "
            f"{RATCHET_FILE.name} (ver el encabezado del archivo para el comando):\n  "
            + "\n  ".join(bajaron), UserWarning, stacklevel=2)

    # las tres bloqueantes del ratchet + las nueve que los otros invariantes duros de este archivo
    # ya fijan en 0 (`BLOQUEANTE_TITULOS`) tienen que agotar el `n_block` que hace que el lint dé
    # exit 1 hoy — recalculado del REPORTE (no de stdout: la línea `✗ N hallazgo(s)...` sólo se
    # imprime a consola, `lint.py` no la escribe al `.md`). Si `rc` y este recálculo divergen, hay
    # una categoría bloqueante NUEVA que ni el ratchet ni los invariantes duros de arriba cubren.
    n_block_recalculado = sum(_categoria(txt, t)[0] for t in BLOQUEANTE_TITULOS)
    assert rc == (1 if n_block_recalculado else 0), (
        f"rc={rc} pero recalculando los 12 títulos bloqueantes de `lint.py` da "
        f"n_block={n_block_recalculado} — alguna categoría bloqueante no está en "
        "`BLOQUEANTE_TITULOS` (o cambió de título)")
    n_bloq_ratchet = sum(_categoria(txt, meta["titulo"])[0]
                         for meta in categorias.values() if meta["severidad"] == "bloqueante")
    assert n_bloq_ratchet <= n_block_recalculado


# ── idempotencia de la cadena de migradores sobre datos reales ───────────────────────────────────

def _snapshot_mtimes(root: Path) -> dict:
    """(ruta relativa → mtime) — mismo propósito que el cinturón de `instancia_real` en
    `conftest.py`, reimplementado acá (no se toca conftest.py) para un cinturón LOCAL a este único
    test: no hace falta esperar al teardown de sesión para saber si ESTE test tocó algo."""
    out = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            try:
                out[str(p.relative_to(root))] = p.stat().st_mtime
            except OSError:
                pass
    return out


def _build_paths(root: Path) -> SimpleNamespace:
    """Mismo shape que `conftest.py::_build_paths` (privado allá, así que se reimplementa acá en
    vez de importarlo — mismo criterio que `_run_lint_reporte`/`_categoria` arriba). `_PATH_ATTRS`
    está definido arriba del todo del archivo (hace falta antes, para el cinturón de aislamiento
    entre tiers)."""
    vault = root / "vault"
    d = {
        "ROOT": root, "VAULT": vault, "CONFIG": vault / "config",
        "STARS_YAML": vault / "config" / "stars.yaml",
        "TOPICS_YAML": vault / "config" / "topics.yaml",
        "OBJECTIVE_YAML": vault / "config" / "objective.yaml",
        "ADS_KEY_FILE": vault / "config" / "ads_dev_key",
        "REGISTRO": vault / "config" / "registro",
        "RAW": vault / "raw", "WIKI": vault / "wiki",
        "PDFS": vault / "raw" / "pdfs", "FULLTEXT": vault / "raw" / "fulltext",
        "GROUND_TRUTH": vault / "raw" / "ground_truth",
        "STARS": vault / "wiki" / "stars", "PAPERS": vault / "wiki" / "papers",
        "CONCEPTS": vault / "wiki" / "concepts", "QUERIES": vault / "wiki" / "queries",
        "MATRICES": vault / "wiki" / "matrices",
        "INDEX": vault / "wiki" / "index.md", "LOG": vault / "wiki" / "log.md",
    }
    return SimpleNamespace(**d)


def _copiar_instancia_mutable(instancia_real, tmp_path: Path) -> SimpleNamespace:
    """Copia MUTABLE, propia de un test, del árbol que `instancia_real` ya copió (que a su vez es
    una copia read-only de la instancia real — dos saltos de distancia del original, nunca uno).

    ⚠ `build/` NO se puede dejar como symlink acá. `instancia_real` lo symlinkea al `build/` REAL
    de la instancia (legítimo: los tests read-only sólo lo GLOBEAN para leer `ads.json`/
    `triage.json`, nunca escriben). Pero `triage.migrate()` (`scripts/triage.py`) hace
    `legacy.unlink()` sobre `build/<slug>/triage.json` al consolidar — si esta copia heredara el
    symlink de `instancia_real`, ese unlink borraría el archivo REAL de la instancia del usuario.
    Por eso acá se reemplaza el symlink de `build/` por una copia de verdad (liviana: ~3.6 MB
    medido) ANTES de que cualquier migrador corra. `raw/pdfs`/`raw/fulltext` sí quedan como
    symlinks: ningún migrador de la cadena (`restamp_headers`, `restamp_pdf_links`,
    `migrate_disputes`, `sync_mirror`, `triage.migrate`) escribe ahí — sólo leen `raw/ground_truth`
    (que ya es una copia real, heredada de `instancia_real`) y escriben en `wiki/`+`config/registro`."""
    dest = tmp_path / "instancia_mutable"
    shutil.copytree(instancia_real.ROOT, dest, symlinks=True)
    build_link = dest / "build"
    if build_link.is_symlink():
        real_build = build_link.resolve()
        build_link.unlink()
        if real_build.is_dir():
            shutil.copytree(real_build, build_link)
        else:
            build_link.mkdir()
    elif not build_link.exists():
        build_link.mkdir()
    return _build_paths(dest)


def test_idempotencia_ciclo_de_migradores_sobre_datos_reales(instancia_real, tmp_path, monkeypatch):
    """El test del deploy real (plan §5): sobre una copia MUTABLE (nunca `instancia_real` ni la
    instancia original) se corre el mismo ciclo de migradores que `test_upgrade.py` ya fija sobre
    corpus SINTÉTICO vintage — acá la pregunta es si el ciclo también cierra sobre la mugre REAL,
    que el generador no puede fabricar a propósito (ediciones a mano, campos que faltan por razones
    que nadie documentó). Fija dos cosas:
      1. **Cierra**: las tres categorías bloqueantes del ratchet (`contradicciones_gt`,
         `disputes_schema_viejo`, `triage_legacy`) bajan — no hace falta que lleguen a 0 exacto (el
         plan documenta 1 residuo humano, `hd40307 P_rot_days`, que ningún migrador puede resolver
         solo — es una decisión de contenido, no de forma), pero si el ciclo no las mueve NADA, algo
         se rompió.
      2. **Es idempotente**: correr el mismo ciclo una SEGUNDA vez sobre lo que quedó no cambia un
         solo byte de `vault/` (`hash_tree` — mismo criterio que `test_upgrade.py`) — el modo de
         falla del deadlock #69 era exactamente que el comando recetado "tenía éxito" en cada
         corrida sin que el lint bajara nunca: acá se mide directo sobre el árbol, no sólo sobre el
         conteo del lint.

    Cinturón LOCAL (además del que hace `instancia_real` a nivel de sesión): mtimes del árbol
    ORIGINAL antes/después de ESTE test puntual — no hace falta esperar al teardown de la sesión
    completa para saber si este test en particular, el único que muta algo, tocó lo que no debía."""
    original = instancia_real.instancia_src
    antes = {**_snapshot_mtimes(original / "vault"), **_snapshot_mtimes(original / "build")}

    paths = _copiar_instancia_mutable(instancia_real, tmp_path)
    for attr in _PATH_ATTRS:
        monkeypatch.setattr(cfg, attr, getattr(paths, attr))
    monkeypatch.setattr(extract_fulltext, "FULLTEXT", paths.FULLTEXT)

    rc0, reporte0 = _run_lint_reporte()
    categorias = _cargar_ratchet()
    bloqueantes = {c: m for c, m in categorias.items() if m["severidad"] == "bloqueante"}
    antes_conteo = {c: _categoria(reporte0, m["titulo"])[0] for c, m in bloqueantes.items()}
    assert sum(antes_conteo.values()) > 0, (
        "el corpus de arranque no tiene ningún bloqueante de los tres del ratchet — este test no "
        "prueba nada así (¿la instancia ya fue migrada? actualizá el ratchet)")

    # el ciclo del deploy real, mismo orden que `test_upgrade.py::_correr_ciclo` y que CLAUDE.md
    # (plan §5, pasos 6-9): disputas → cabeceras → espejo → triage legacy del único sujeto que lo trae.
    make_notes.migrate_all_disputes()
    make_notes.restamp_headers()
    make_notes.sync_mirror()
    legacy_slugs = [p.parent.name for p in (paths.ROOT / "build").glob("*/triage.json")]
    for slug in legacy_slugs:
        triage.migrate(slug)

    rc1, reporte1 = _run_lint_reporte()
    despues_conteo = {c: _categoria(reporte1, m["titulo"])[0] for c, m in bloqueantes.items()}
    assert sum(despues_conteo.values()) < sum(antes_conteo.values()), (
        f"el ciclo de migradores no bajó ningún bloqueante: antes={antes_conteo} "
        f"después={despues_conteo}")
    # disputes_schema_viejo y triage_legacy son 100% mecánicos (sin residuo posible) — tienen que
    # cerrar en 0 exacto; contradicciones_gt puede dejar el residuo humano documentado en el ratchet.
    for clave in ("disputes_schema_viejo", "triage_legacy"):
        if clave in despues_conteo:
            assert despues_conteo[clave] == 0, (
                f"{clave} no cerró en 0 tras el ciclo: {despues_conteo[clave]} — "
                f"{bloqueantes[clave]['titulo']!r} debería ser 100% mecánico")

    hash1 = hash_tree(paths.VAULT)
    make_notes.migrate_all_disputes()
    make_notes.restamp_headers()
    make_notes.sync_mirror()
    for slug in legacy_slugs:
        triage.migrate(slug)          # ya no hay legacy.json — cada llamada debe ser un no-op
    hash2 = hash_tree(paths.VAULT)
    assert hash1 == hash2, (
        "la segunda pasada del ciclo reescribió algo en vault/ — no es no-op (el patrón del "
        "deadlock #69: un migrador sin ancla de idempotencia parece 'funcionar' en cada corrida "
        "sin que el lint lo note, porque el lint mide categorías, no bytes)")

    rc2, reporte2 = _run_lint_reporte()
    tercera_conteo = {c: _categoria(reporte2, m["titulo"])[0] for c, m in bloqueantes.items()}
    assert tercera_conteo == despues_conteo, (
        f"el conteo del lint cambió en la segunda pasada del ciclo: {despues_conteo} → "
        f"{tercera_conteo} (debería ser idéntico: nada quedó por migrar)")

    despues = {**_snapshot_mtimes(original / "vault"), **_snapshot_mtimes(original / "build")}
    assert antes == despues, (
        f"ALMAGESTO_INSTANCIA={original}: algo cambió en vault/build del ORIGINAL durante este "
        "test — el cinturón local lo agarró antes de esperar al teardown de sesión")
