"""Escala / performance del lint y de los estampadores — plan §3.1.

Estos tests NO cazan "¿el chequeo encuentra el hallazgo?" (eso es `test_conteos_exactos.py`, otra
ola): cazan **complejidad peor que lineal** — un chequeo nuevo que compara todo-contra-todo con
listas en vez de sets/dicts, un barrido que se vuelve O(n²) sin que nadie lo note porque en la
bóveda de juguete (1-3 notas) da lo mismo O(n) que O(n²) — y **regresiones de presupuesto**
(alguien agrega una categoría cara y el lint deja de ser "barato").

⚠ Tiempo absoluto es frágil (máquina/CI): la estrategia primaria es **ratio**
`t(N grande) / t(N chico)` — para un `N` 4× más grande, lineal da ≈4, cuadrático da ≈16; un
umbral de 8 separa ambos con margen amplio para ruido. Los presupuestos absolutos que sí aparecen
llevan margen explícito (≥5×) sobre el número medido, documentado en cada test — nunca un número
inventado.

Todos los números de referencia de este archivo están MEDIDOS en esta sesión (no estimados),
corriendo el generador de `tests/poblada/generador.py` sobre esta máquina; se repiten en cada
docstring para que el próximo ajuste de umbral tenga de dónde partir.
"""
from __future__ import annotations

import contextlib
import io
import random
import re
import sys
import time
from pathlib import Path

import pytest
import yaml

import lint
import make_notes
from extract_fulltext import is_legible

from generador import hash_tree

pytestmark = pytest.mark.poblada


def _lint_silencioso() -> int:
    """Corre `lint.main()` con stdout silenciado: a N=800-900 el reporte son miles de líneas que
    no aportan nada a un test de tiempo y ensucian la salida de pytest."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return lint.main()


def _tiempo_lint() -> float:
    t0 = time.perf_counter()
    rc = _lint_silencioso()
    assert rc in (0, 1)
    return time.perf_counter() - t0


# ── ratios: cazan crecimiento peor-que-lineal sin ser frágiles a la velocidad de la máquina ────

def test_lint_escala_lineal(sembrar):
    """Caza un chequeo nuevo O(n²) (p. ej. un barrido anidado de wikilinks, o `cited_in_entity`
    cruzado contra los papers con listas en vez de sets/dicts — hoy nada en el lint hace eso,
    medido por perfil, pero nada lo fija tampoco). Ratio, no presupuesto absoluto: medido en esta
    máquina, `lint(800)/lint(200)` da 3.67–3.90 en corridas repetidas (lineal puro = 800/200 = 4;
    un barrido cuadrático daría ≈16). El umbral ≤8 deja margen amplio de ruido sin dejar pasar una
    regresión a complejidad peor que lineal."""
    sembrar(n_papers=200, n_stars=4, n_concepts=20, seed=100)
    t200 = _tiempo_lint()
    sembrar(n_papers=800, n_stars=4, n_concepts=20, seed=101)
    t800 = _tiempo_lint()
    ratio = t800 / max(t200, 1e-6)
    assert ratio <= 8, (
        f"lint(800)/lint(200) = {ratio:.2f} (referencia medida: 3.67-3.90; lineal puro=4.00, "
        "cuadrático≈16) — posible chequeo nuevo con complejidad peor que lineal")


def test_restamp_pdf_links_escala(sembrar):
    """`make_notes.restamp_pdf_links()` es un barrido PLANO sobre `cfg.PAPERS` (un
    `stamp_pdf_link` por paper, sin comparar contra otros papers) — debe escalar lineal por
    construcción; este test lo fija para que una futura refactor (p. ej. que empiece a indexar
    contra todos los PDFs del disco por cada paper) no lo rompa en silencio. Medido:
    `restamp(800)/restamp(200)` ≈ 3.90 (lineal puro=4.00); mismo umbral ≤8 que el lint, con la
    misma justificación (margen amplio, bien separado del ≈16 de un barrido cuadrático). Presupuesto
    absoluto a N=800: medido 0.64 s → 10 s da >15× de margen (la instancia real, con PDFs de
    verdad en disco, mide 0.84 s para 908 papers — CLAUDE.md #47)."""
    sembrar(n_papers=200, n_stars=4, n_concepts=20, seed=110)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        t0 = time.perf_counter()
        make_notes.restamp_pdf_links()
        t200 = time.perf_counter() - t0

    sembrar(n_papers=800, n_stars=4, n_concepts=20, seed=111)
    with contextlib.redirect_stdout(buf):
        t0 = time.perf_counter()
        make_notes.restamp_pdf_links()
        t800 = time.perf_counter() - t0

    ratio = t800 / max(t200, 1e-6)
    assert ratio <= 8, (
        f"restamp_pdf_links(800)/restamp_pdf_links(200) = {ratio:.2f} (referencia medida ≈3.90, "
        "lineal puro=4.00) — posible regresión a complejidad peor que lineal")
    assert t800 < 10.0, f"restamp_pdf_links(N=800) tardó {t800:.2f}s (presupuesto 10s, medido ≈0.64s)"


def test_is_legible_proporcional_al_tamano():
    """`is_legible` (`extract_fulltext.py`) es, medido por perfil sobre el corpus real, el 77% del
    tiempo total de un lint completo (CLAUDE.md / diagnóstico de esta sesión): itera el texto
    completo dos veces (la lista de caracteres no-espacio, y la proporción de caracteres
    "legibles" sobre esa lista) — O(bytes del fulltext) por construcción. No necesita corpus ni
    fixtures: es una función pura, así que el blanco más preciso es medirla directo. Medido acá:
    cuadruplicar el tamaño del texto (20 000 → 80 000 palabras) cuadruplica el tiempo casi exacto
    (ratio ≈4.0 en textos de 40 KB a 660 KB, en pasos de 2×: 2.36, 4.69, 9.34, 18.60, 37.40 ms —
    cada paso duplica limpio). Si alguien la vuelve O(n²) (p. ej. cacheando mal, o agregando una
    comparación cruzada de caracteres), cuadruplicar el tamaño daría ≈16× el tiempo, no ≈4×."""
    rng = random.Random(99)
    words = ("radial velocity activity index chromospheric spot rotation period amplitude "
             "signal periodogram bisector correlation host star").split()

    def _texto(n_words: int) -> str:
        return " ".join(rng.choice(words) for _ in range(n_words)) + ".\n"

    chico = _texto(20_000)
    grande = _texto(80_000)          # 4x más caracteres

    def _tiempo(txt: str, reps: int = 8) -> float:
        t0 = time.perf_counter()
        for _ in range(reps):
            ok, _ = is_legible(txt)
            assert ok
        return (time.perf_counter() - t0) / reps

    t_chico = _tiempo(chico)
    t_grande = _tiempo(grande)
    ratio = t_grande / max(t_chico, 1e-9)
    assert ratio <= 8, (
        f"is_legible: 4x el texto dio {ratio:.2f}x el tiempo (referencia medida ≈4.0, lineal "
        "puro=4.00, cuadrático≈16) — posible regresión a complejidad peor que lineal")


# ── presupuesto absoluto: margen amplio y justificado, sobre el árbol de SESIÓN (N=900) ────────

def test_lint_presupuesto_absoluto(boveda_poblada):
    """Presupuesto absoluto sobre el árbol de SESIÓN (N=900, sin resembrar — reusa `arbol_poblado`
    en vez de sembrar de nuevo, como pide el criterio de la tarea). Medido en esta máquina:
    lint(N=900) ≈ 1.7-1.8 s. El corpus sintético no carga ~80 MB de fulltext real como
    una instancia real, donde el mismo lint mide 5.6 s (CLAUDE.md) — así que 1.7 s acá es la referencia
    correcta, no 5.6 s. Presupuesto elegido: 10 s (≈5.5-6× de margen sobre lo medido), suficiente
    para un CI más lento sin dejar pasar una regresión grosera de presupuesto (agregar una
    categoría O(n) cara, por ejemplo triplicar el parseo YAML por nota)."""
    assert boveda_poblada.censo.n_papers == 900
    t = _tiempo_lint()
    assert t < 10.0, f"lint(N=900) tardó {t:.2f}s (presupuesto 10s, medido de referencia ≈1.7-1.8s)"


def test_lint_una_pasada_de_yaml(boveda_poblada, monkeypatch):
    """Ratchet del hotspot medido (CLAUDE.md / diagnóstico de esta sesión): `split_fm` y
    `fm_error` (`lint.py`) parsean el MISMO frontmatter YAML dos veces por nota — en el corpus
    real, 941 notas → 1882 `yaml.safe_load` (ratio ≈2.0); acá, sobre el árbol de sesión (N=900:
    900 papers + 4 estrellas + 20 conceptos + 2 queries + 1 matriz = 927 notas con frontmatter),
    se miden 1860 llamadas (ratio 2.006) — el mismo patrón, a otra escala.

    Este test NO exige arreglar el doble parseo (`scripts/` está fuera de alcance para esta capa):
    sólo FIJA que no empeore en silencio a un tercer parseo (o más) por nota. Sin cota inferior a
    propósito — si algún día se corrige el doble parseo, el conteo baja y el test debe seguir
    pasando con MENOS llamadas, no romperse por mejorar."""
    n_notas = (len(list(boveda_poblada.PAPERS.glob("*.md")))
               + len(list(boveda_poblada.STARS.glob("*.md")))
               + len(list(boveda_poblada.CONCEPTS.glob("*/*.md")))
               + len(list(boveda_poblada.QUERIES.glob("*.md")))
               + len(list(boveda_poblada.MATRICES.glob("*.md"))))
    assert n_notas == 927, "el árbol de sesión no tiene el shape default (900/4/20/2/1) esperado"

    calls = {"n": 0}
    original = yaml.safe_load

    def _contando(*a, **kw):
        calls["n"] += 1
        return original(*a, **kw)

    monkeypatch.setattr(yaml, "safe_load", _contando)
    rc = _lint_silencioso()
    assert rc == 0

    ratio = calls["n"] / n_notas
    assert calls["n"] <= 2.3 * n_notas, (
        f"{calls['n']} llamadas a yaml.safe_load para {n_notas} notas con frontmatter "
        f"(ratio {ratio:.3f}) — se esperaba ≤2.3x (hoy ≈2.0x, el doble parseo conocido de "
        "split_fm+fm_error); un salto a 3x o más es una regresión NUEVA, no el hotspot conocido")


def test_lint_no_muta_la_boveda(boveda_poblada):
    """El docstring de `lint.py` promete: 'No modifica nada: reporta para que el agente/usuario
    decida'. Sobre el árbol de SESIÓN (N=900, sin resembrar): hash SHA-256 determinista de todo
    `vault/` antes y después de `lint.main()` — debe ser idéntico byte a byte. Un chequeo que
    'arregla de paso' (p. ej. un futuro auto-fix de cabeceras colado adentro del lint en vez de
    vivir en `make_notes.py --restamp-headers`) rompería este hash sin que ningún otro test lo
    note, porque el lint seguiría reportando bien — el contrato que este test vigila no es
    "encuentra los hallazgos" sino "no toca lo que audita".  @inv INV-42"""
    antes = hash_tree(boveda_poblada.VAULT)
    _lint_silencioso()
    despues = hash_tree(boveda_poblada.VAULT)
    assert antes == despues, "lint.main() modificó vault/ — viola 'No modifica nada' de su docstring"


def test_source_hash_comparte_la_lectura_con_is_legible(boveda_poblada, monkeypatch):
    """Ancla de hotspot (10.3): el hash de fuente (D-20) y `is_legible` leen **cada `.txt` una sola
    vez, juntos**.

    Por qué es un ancla y no un detalle: `is_legible` sobre el corpus real es el **77% del costo del
    lint** (5,6 s sobre 908 notas). El hash de fuente necesita exactamente el mismo contenido, así
    que se calcula sobre esa lectura — cero lecturas extra. Si alguien los separa "para que quede
    más prolijo", el costo del lint sube un 77% de golpe **y ningún test se pone rojo**: el reporte
    sale idéntico. Este es el test que se pondría rojo.

    Se cuenta la cantidad de `open()` sobre `.txt` de `raw/fulltext/`, no el tiempo: un umbral de
    segundos mide la máquina, un conteo de lecturas mide el código."""
    import builtins
    from pathlib import Path as _P
    lecturas = []
    real_open, real_read_text = builtins.open, _P.read_text

    def _mirar(path):
        s = str(path)
        if s.endswith(".txt") and "fulltext" in s:
            lecturas.append(s)

    def contando(path, *a, **kw):
        _mirar(path)
        return real_open(path, *a, **kw)

    def contando_rt(self, *a, **kw):
        # ⚠ Los DOS caminos. La primera versión de este test contaba sólo `builtins.open` y
        # **no mordió** la mutación que lo tenía que matar: `lib_blocks.source_hash` lee con
        # `Path.read_text`, que va por `io.open` y no pasa por el builtin. Un test que mide una
        # sola de las dos puertas es el mismo defecto que persigue.
        _mirar(self)
        return real_read_text(self, *a, **kw)

    monkeypatch.setattr(builtins, "open", contando)
    monkeypatch.setattr(_P, "read_text", contando_rt)
    lint.collect()
    monkeypatch.undo()
    n_txt = len(list(boveda_poblada.FULLTEXT.glob("*/*.txt")))
    assert n_txt > 100, "el corpus tiene que tener fulltexts para que este ancla mida algo"
    repetidas = [p for p in set(lecturas) if lecturas.count(p) > 1]
    assert repetidas == [], (
        f"{len(repetidas)} `.txt` leídos más de una vez — `source_hash` dejó de compartir la "
        f"lectura de `is_legible` y el 77% del costo del lint se duplicó: {repetidas[:3]}")
    assert len(lecturas) <= n_txt, (
        f"{len(lecturas)} lecturas para {n_txt} archivos: hay una pasada de más")


# ── 10.3 · el presupuesto de la suite, medido ──────────────────────────────────────────────────
#
# `tests/README.md` prometía tier 0 ≤ 2,5 s y el número se fue a 7,3 s a lo largo de nueve tandas —
# una decena de tests por vez, sin que nada fallara nunca: **ninguna corrida se pone roja por
# lenta**. Es el caso de manual de "una promesa que el sistema dejó de cumplir en silencio", y la
# respuesta del repo a eso no es bajar la promesa: es medirla.
#
# Lo que la medición mostró (2026-08-24, con la medición en la mano, como pide el issue):
#   · el hotspot NO era `is_legible` —tier 0 no tiene corpus grande—: era **un solo test** que
#     barría el repo entero con AST para mirar dos archivos (2,6 s de 7,3);
#   · el resto es piso por test (~4 ms de tmpdir por `toy_vault`) × 1000 tests;
#   · o sea que el costo POR TEST bajó desde que se escribió el techo (2,5 s / ~400 tests ≈ 6 ms);
#     lo que creció es la cantidad.
# Por eso el presupuesto pasa a ser una **tasa** con un techo absoluto encima: la tasa es lo que
# protege la propiedad real ("una suite que tarda se deja de correr antes de commitear") y el techo
# impide que la cantidad crezca sin límite amparada en la tasa.

MS_POR_TEST = 9.0        # medido 4,7 ms/test; el margen absorbe una máquina más lenta
# ⚠ 2026-08-27: 8.0 → 9.0, y el motivo NO es que los tests se pusieran caros — es que este
# presupuesto mide **wall-clock sobre una máquina sin especificar**, así que su veredicto depende de
# en qué máquina y bajo qué carga corre. Verificado de la única forma que lo decide: el gate se corrió
# contra el commit **anterior a esta tanda**, sin un solo test agregado, y también dio rojo (8,5
# ms/test). O sea el rojo era del entorno y se habría leído como una regresión de la tanda. La tasa
# real apenas se movió —7,61 ms/test en el baseline contra 7,80 con los 17 tests nuevos, medidos
# seguido en la misma máquina— y `--durations` no muestra hotspot: el test más caro es 0,34 s.
# Queda como issue: un presupuesto de tiempo absoluto no es un gate estable (ver #201).
TIER0_TECHO_S = 12.0     # techo absoluto: con ~1000 tests el piso son ~5 s
# 2026-08-27 (#196/#197): 10.0 → 12.0. La **tasa** siguió sana —7,6 ms/test contra un techo de 8,0—
# y `--durations` no mostró ningún hotspot: el más caro es 0,34 s y los ocho primeros suman ~1,8 s de
# 10,3. Lo que creció es la CANTIDAD, +15 tests por dos issues reales (1447 → 1462), que es
# exactamente el caso que este techo manda decidir en vez de tramitar. Se sube porque la propiedad
# que el presupuesto protege —«una suite que tarda se deja de correr antes de commitear»— se sostiene
# a 12 s. Si vuelve a tocar el techo SIN que la tasa se mueva, la respuesta ya no es subirlo: es
# preguntarse si hacen falta todos los tests.


def test_presupuesto_de_tier_0():
    """Corre el tier 0 como subproceso y mide. Va en tier 1 porque **un tier no puede medirse a sí
    mismo**: el test que mide sumaría su propio costo al que reporta."""
    import subprocess
    repo = Path(__file__).resolve().parent.parent.parent
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "-p", "no:randomly"],
                       cwd=repo, capture_output=True, text=True)
    dur = time.time() - t0
    assert r.returncode == 0, r.stdout[-2000:]
    m = re.search(r"(\d+) passed", r.stdout)
    assert m, r.stdout[-500:]
    n = int(m.group(1))
    ms = dur * 1000 / n
    assert ms <= MS_POR_TEST, (
        f"tier 0: {dur:.1f}s / {n} tests = {ms:.1f} ms/test (techo {MS_POR_TEST}). No es la "
        f"cantidad de tests: es que cada uno se puso caro. Mirá `--durations` antes de tocar el techo.")
    assert dur <= TIER0_TECHO_S, (
        f"tier 0 tarda {dur:.1f}s (techo absoluto {TIER0_TECHO_S}s) con {n} tests a {ms:.1f} "
        f"ms/test. El costo por test está bien: creció la CANTIDAD. Decidilo explícitamente — "
        f"subir el techo acá es una decisión, no un trámite.")


TIER1_TECHO_S = 120.0    # medido 91 s; subió de 90 con 10.3 y está razonado en tests/README.md


def test_presupuesto_de_tier_1(boveda_poblada):
    """El hermano del de arriba, para el tier caro. **No corre el tier**: sumaría el suyo y sería
    recursivo. Mide el costo de lo único que escala con el corpus —una pasada de `lint.collect()`
    sobre las ~900 notas— y lo compara contra la fracción del presupuesto que le toca.

    Por qué así: el tier 1 son ~25 siembras + ~25 pasadas de lint, y si el reloj de pared se pasa,
    la pregunta útil es **cuál de las dos** se puso cara. Un techo de wall-clock sin esa distinción
    manda a mirar el archivo equivocado."""
    import time
    t0 = time.time()
    lint.collect()
    una_pasada = time.time() - t0
    # ~25 pasadas de lint en el tier; el resto del presupuesto es siembra e I/O.
    presupuesto_lint = TIER1_TECHO_S * 0.6 / 25
    assert una_pasada <= presupuesto_lint, (
        f"una pasada de `lint.collect()` sobre {len(list(boveda_poblada.PAPERS.glob('*.md')))} "
        f"notas tarda {una_pasada:.2f}s (presupuesto {presupuesto_lint:.2f}s por pasada, "
        f"≈{TIER1_TECHO_S}s de tier). El hotspot medido es `is_legible` (77%): mirá primero que "
        f"`source_hash` siga compartiendo su lectura (`test_source_hash_comparte_la_lectura...`).")
