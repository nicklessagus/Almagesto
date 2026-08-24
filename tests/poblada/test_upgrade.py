"""Upgrade 1.11.0 → framework actual (§3.4 del plan de la 7ª auditoría de `tests/poblada/`).

**Por qué existe.** El ensayo real de deploy (una instancia real en 1.11.0, corpus real de
25 notas / 4 estrellas) midió un ciclo de tres pasos que una bóveda vacía no puede ejercitar: (1) el
lint del framework nuevo, corrido sobre un corpus del schema viejo, **bloquea** con categorías que
el lector ya no tolera (`planets[].disputes[]` pre-#71, `build/<slug>/triage.json` pre-#51, el
espejo #70 roto porque `planets[]` no traía `mass_earth`); (2) los migradores/estampadores
(`make_notes.py --migrate-disputes/--restamp-headers/--sync-mirror`, `triage.py --migrate`) se
corren; (3) el lint **cierra** el hallazgo — no sólo "el comando no tiró error", sino que el
CONTEO baja a 0. Ese tercer paso es el que fallaba en el propio framework hasta hace poco: el
deadlock #69 (documentado en el docstring de `make_notes.stamp_header`) hacía que
`--restamp-headers` informara "22 estampadas" en CADA corrida sin que el lint bajara nunca de 22 —
el comando recetado por el propio mensaje del lint no cerraba el hallazgo que recetaba. `sembrar_corpus(vintage="1.11.0")` (`tests/poblada/generador.py`) reproduce ese schema viejo de
forma determinista para poder fijar el ciclo completo sin depender de tener la instancia real a mano.

**Qué NO cubre este archivo** (ver el reporte final de la tarea para el detalle): el residuo humano
medido en el deploy real —`hd40307 P_rot_days: 48` sin respaldo en NEA, 1 de 13 contradicciones del
espejo que `--sync-mirror` no puede cerrar solo— no es reproducible con `sembrar_corpus`: el
generador deriva `P_rot_days` de la ficha **directamente** del mismo `host["st_rotp_days"]` que
escribe al ground-truth (mismo valor o ambos `null`), así que nunca genera el caso "la ficha tiene
un número de literatura que el ground-truth no tiene". El test de closure del espejo (abajo) por
eso cierra a 0 con el corpus vintage — la asimetría se prueba aparte, craftenado el frontmatter a
mano (`test_sync_mirror_es_add_only_nunca_pisa_ni_inventa`), que es donde vive el contrato real de
`--sync-mirror` con independencia del generador.

No se tocan `generador.py`/`conftest.py`/`test_generador.py` (otra gente depende de esas firmas) ni
`scripts/`: los helpers de lectura del reporte se reimplementan acá, mismo criterio que
`test_conteos_exactos.py` (que tampoco importa de `test_generador.py`).
"""
from __future__ import annotations

import datetime as dt
import json
import re

import pytest
import yaml

import lib_config as cfg
import lint
import make_notes
import triage

from generador import hash_tree

pytestmark = pytest.mark.poblada


# ── lectura del reporte (NO stdout — ver tests/README.md, "Corolario que ya mordió dos veces": la
# última línea de stdout es la RUTA del reporte, bajo el tmpdir de pytest cuyo nombre incluye el
# del test, así que un assert de substring contra stdout puede matchear el PATH). ──────────────────

def _run_lint_reporte() -> tuple[int, str]:
    rc = lint.main()
    reporte = (cfg.ROOT / "outputs" / f"lint-{dt.date.today().isoformat()}.md").read_text(
        encoding="utf-8")
    return rc, reporte


def _categoria(reporte: str, contiene: str) -> tuple[int, list[str]]:
    """(conteo, líneas completas `stem → motivo`) de la categoría cuyo título contiene `contiene`."""
    lines = reporte.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## ") and contiene in l), None)
    assert start is not None, f"categoría no encontrada en el reporte: {contiene!r}"
    m = re.search(r"\((\d+)\)\s*$", lines[start])
    assert m, f"título sin conteo: {lines[start]!r}"
    n = int(m.group(1))
    items = []
    for l in lines[start + 1:]:
        if l.startswith("## "):
            break
        if l.startswith("- "):
            items.append(l[2:])
    assert len(items) == n, f"{contiene!r}: título dice {n} pero hay {len(items)} líneas listadas"
    return n, items


def _load_fm_body(path) -> tuple[dict, str]:
    """(frontmatter parseado, cuerpo crudo tal como está en disco) — para craftear escenarios a
    mano sin pasar por `sembrar_corpus` (que no soporta `vintage` + edición fina combinados)."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: no tiene frontmatter"
    end = text.find("\n---\n", 4)
    assert end >= 0, f"{path}: frontmatter sin cierre"
    front = yaml.safe_load(text[4:end]) or {}
    return front, text[end + 5:]


def _write_fm_body(path, front: dict, body: str) -> None:
    path.write_text(make_notes.fm(front) + body, encoding="utf-8")


def _all_bodies(paths) -> dict:
    """ruta → cuerpo (todo lo que sigue al frontmatter) de toda nota de stars/concepts/papers.
    Sirve de "antes" para comprobar que un migrador no perdió prosa."""
    out = {}
    globs = (paths.STARS.glob("*.md"), paths.CONCEPTS.glob("*/*.md"), paths.PAPERS.glob("*.md"))
    for g in globs:
        for p in g:
            _, body = _load_fm_body(p)
            out[str(p)] = body
    return out


def _is_line_subsequence(old_lines: list[str], new_lines: list[str]) -> bool:
    """¿Toda línea de `old_lines` aparece en `new_lines`, en el mismo orden relativo (con líneas
    NUEVAS intercaladas permitidas)? Es el invariante de una migración que sólo INSERTA (el
    `stamp_header` de `restamp_headers` agrega un bloque después del `# H1`, nunca borra ni edita
    una línea existente): si una línea de la prosa original desaparece o cambia, esto es False."""
    it = iter(new_lines)
    for old in old_lines:
        for new in it:
            if new == old:
                break
        else:
            return False
    return True


# ── 1. el schema viejo bloquea, con conteos exactos y la receta visible en el mensaje ──────────

def test_vintage_bloquea_con_categorias_de_schema_viejo_y_receta_visible(sembrar):
    """Caza el modo de falla "el schema viejo se volvió mudo": si algún día se agrega tolerancia de
    lectura para `planets[].disputes[]` o `build/<slug>/triage.json` (la "capa de compatibilidad"
    que CLAUDE.md prohíbe expresamente), este test es el primero en notarlo porque deja de bloquear.
    Los conteos NO se hardcodean (el plan pide no fijar números del corpus sintético): salen del
    propio `Censo.star_gt` — un planeta por dispute vieja, un planeta por contradicción de espejo —
    así que valen para cualquier seed/tamaño. Referencia del ensayo real (no el umbral de este
    test): 16 bloqueantes, de los cuales 13 eran el espejo #70 y 2+1 el resto del schema viejo.  @inv INV-64"""
    _, censo = sembrar(n_papers=60, n_stars=4, n_concepts=8, seed=100, vintage="1.11.0")

    n_planetas = sum(len(gt["planets"]) for gt in censo.star_gt.values())
    n_estrellas_con_planeta = sum(1 for gt in censo.star_gt.values() if gt["planets"])
    assert n_planetas > 0 and n_estrellas_con_planeta > 0, (
        "el generador vintage fuerza ≥1 planeta en la primera estrella — si esto falla, cambió esa "
        "garantía y el resto de este test pierde sentido")

    rc, reporte = _run_lint_reporte()
    assert rc == 1

    n_old, items_old = _categoria(reporte, "disputes en el schema viejo")
    assert n_old == n_estrellas_con_planeta
    assert all("python scripts/make_notes.py --migrate-disputes" in it for it in items_old)

    n_legacy, items_legacy = _categoria(reporte, "Juicio de triage en build")
    assert n_legacy == 1                     # un solo build/<slug>/triage.json sembrado
    assert f"python scripts/triage.py {censo.star_slugs[0]} --migrate" in items_legacy[0]

    n_mirror, _ = _categoria(reporte, "Contradicciones ground-truth")
    assert n_mirror == n_planetas            # un `mass_earth` faltante por planeta (#70)

    n_headerless, items_headerless = _categoria(reporte, "Cabecera no estampable")
    assert n_headerless == len(censo.star_slugs) + len(censo.concept_stems)
    assert all("python scripts/make_notes.py --restamp-headers" in it for it in items_headerless)

    # las categorías del schema NUEVO que el vintage no toca siguen mudas de verdad (no por
    # casualidad): confirma que lo de arriba lo dispara el VINTAGE, no un efecto de los params
    n_bad_roles, _ = _categoria(reporte, "`role` fuera del vocabulario")
    assert n_bad_roles == 0


# ── 2. --migrate-disputes cierra, no toca prosa, es idempotente ────────────────────────────────

def test_migrate_disputes_cierra_y_es_idempotente_sin_tocar_prosa(sembrar):
    """El modo de falla medido en el ensayo real: la primera corrida migra ("2 de 4 fichas
    migradas"), pero sin el `unlink`/guardas correctos una segunda corrida podía migrar DE NUEVO
    (duplicando posiciones) o dejar el archivo a medio migrar. Fija las dos mitades: 1ª corrida
    baja la categoría a 0 y migra EXACTAMENTE las fichas con disputa vieja; 2ª corrida no cambia
    nada (ni el conteo del lint ni un solo byte de las fichas)."""
    paths, censo = sembrar(n_papers=50, n_stars=5, n_concepts=6, seed=101, vintage="1.11.0")
    n_esperadas = sum(1 for gt in censo.star_gt.values() if gt["planets"])

    pre_bodies = _all_bodies(paths)          # migrate_disputes NUNCA debe tocar el cuerpo

    rc0, reporte0 = _run_lint_reporte()
    assert rc0 == 1
    n0, _ = _categoria(reporte0, "disputes en el schema viejo")
    assert n0 == n_esperadas

    changed1 = sum(1 for slug in censo.star_slugs
                   if make_notes.migrate_disputes(paths.STARS / f"{slug}.md"))
    assert changed1 == n_esperadas

    rc1, reporte1 = _run_lint_reporte()
    n1, _ = _categoria(reporte1, "disputes en el schema viejo")
    assert n1 == 0, "el migrador corrió pero el lint sigue viendo el schema viejo"
    # el nuevo schema con posiciones explícitas tiene que ser LEGIBLE, no sólo "no viejo":
    n_bad, _ = _categoria(reporte1, "disputes mal formadas")
    assert n_bad == 0
    n_dangling, _ = _categoria(reporte1, "disputes: ref de una posición")
    assert n_dangling == 0                   # el `ref` migrado (paper_stems[0]) resuelve a una nota

    post_bodies = _all_bodies(paths)
    assert post_bodies == pre_bodies, "migrate_disputes tocó el cuerpo de alguna nota (sólo debe re-serializar frontmatter)"

    changed2 = sum(1 for slug in censo.star_slugs
                   if make_notes.migrate_disputes(paths.STARS / f"{slug}.md"))
    assert changed2 == 0, "segunda corrida: no debería quedar nada para migrar"
    rc2, reporte2 = _run_lint_reporte()
    n2, _ = _categoria(reporte2, "disputes en el schema viejo")
    assert n2 == 0


# ── 3. triage --migrate consolida y CONSUME su entrada (el detector deja de bloquear) ──────────

def test_triage_migrate_consolida_borra_legacy_y_es_idempotente(sembrar):
    """El ciclo que #51 exige: el detector del lint bloquea por EXISTENCIA de
    `build/<slug>/triage.json`, así que el migrador tiene que CONSUMIR el archivo (borrarlo), no
    sólo leerlo — si lo dejara en disco, `triage.migrate` "tendría éxito" en cada corrida sin que el
    lint bajara nunca de 1, el mismo patrón de deadlock que #69. Referencia del ensayo real: "100
    decisiones ya estaban en el registro"; acá el `triage.json` sintético trae `decisiones: {}`
    (0), así que el número relevante no es CUÁNTAS se migran sino que el archivo se borra Y el
    lint cierra."""
    paths, censo = sembrar(n_papers=40, n_stars=3, n_concepts=5, seed=102, vintage="1.11.0")
    slug0 = censo.star_slugs[0]
    legacy = cfg.legacy_triage_path(slug0)
    assert legacy.exists()

    rc0, reporte0 = _run_lint_reporte()
    n0, _ = _categoria(reporte0, "Juicio de triage en build")
    assert n0 == 1

    rc = triage.migrate(slug0)
    assert rc == 0
    assert not legacy.exists(), "el migrador tiene que CONSUMIR (borrar) el triage.json viejo"

    rc1, reporte1 = _run_lint_reporte()
    n1, _ = _categoria(reporte1, "Juicio de triage en build")
    assert n1 == 0

    # idempotente: sin el archivo, una segunda corrida no revienta y no hay nada más que consolidar
    rc2 = triage.migrate(slug0)
    assert rc2 == 0
    rc3, reporte3 = _run_lint_reporte()
    n3, _ = _categoria(reporte3, "Juicio de triage en build")
    assert n3 == 0


# ── 4. --sync-mirror cierra el espejo del corpus vintage y es idempotente ──────────────────────

def test_sync_mirror_cierra_el_espejo_del_vintage_y_es_idempotente(sembrar):
    """El residuo medido en el ensayo real fue 13→1 (12 `mass_earth` triviales se llenan solos, 1
    `P_rot_days` de literatura queda para juicio humano). Este generador NO puede reproducir ese
    residuo (ver el docstring del módulo): el `P_rot_days` de la ficha vintage es SIEMPRE un espejo
    exacto del ground-truth por construcción, así que la única asimetría que el vintage produce es
    `mass_earth` ausente en `planets[]` — el caso 100% mecánico. Por eso acá el cierre es a 0 exacto
    (no queda residuo); el contrato add-only en sí —lo que SÍ puede dejar residuo— se prueba aparte
    en `test_sync_mirror_es_add_only_nunca_pisa_ni_inventa`."""
    paths, censo = sembrar(n_papers=50, n_stars=4, n_concepts=6, seed=103, vintage="1.11.0")
    n_planetas = sum(len(gt["planets"]) for gt in censo.star_gt.values())

    pre_bodies = _all_bodies(paths)          # sync_mirror tampoco debe tocar el cuerpo

    rc0, reporte0 = _run_lint_reporte()
    n0, _ = _categoria(reporte0, "Contradicciones ground-truth")
    assert n0 == n_planetas

    rc = make_notes.sync_mirror()
    assert rc == 0

    rc1, reporte1 = _run_lint_reporte()
    n1, _ = _categoria(reporte1, "Contradicciones ground-truth")
    assert n1 == 0, f"sync-mirror debería cerrar las {n_planetas} contradicciones de mass_earth a 0"

    assert _all_bodies(paths) == pre_bodies

    # idempotente: sin más `null` que rellenar, la 2ª corrida no cambia nada
    rc2 = make_notes.sync_mirror()
    assert rc2 == 0
    rc3, reporte3 = _run_lint_reporte()
    n3, _ = _categoria(reporte3, "Contradicciones ground-truth")
    assert n3 == 0


# ── 5. --sync-mirror es add-only: nunca pisa un valor distinto ni inventa uno que el GT no tiene ──

def test_sync_mirror_es_add_only_nunca_pisa_ni_inventa(sembrar, capsys):
    """El contrato explícito del backfill (docstring de `make_notes.sync_mirror`, y la tarea que
    pidió este archivo lo repite): `campo: null` en la ficha + valor en el ground-truth → se copia
    (el único caso que se toca); ficha con valor DISTINTO del ground-truth → se dejan los dos, se
    reporta (`disputes[]`, no un error de sincronización); ficha con valor y ground-truth en `null`
    → se deja, se reporta (número de literatura, no relleno mecánico). El corpus vintage no puede
    ejercitar las dos últimas ramas por construcción (ver el docstring del módulo), así que acá se
    craftea el frontmatter/ground-truth a mano — es la única forma de probar el contrato completo."""
    paths, censo = sembrar(n_papers=40, n_stars=6, n_concepts=5, seed=104)   # vintage actual: da igual

    host_slug = censo.star_slugs[0]
    host_path = paths.STARS / f"{host_slug}.md"
    gt_path = paths.GROUND_TRUTH / f"{host_slug}.json"
    front, body = _load_fm_body(host_path)
    gt = json.loads(gt_path.read_text(encoding="utf-8"))

    front["dist_pc"] = None                     # caso 1: null en la ficha, GT con valor → copia
    gt["host"]["dist_pc"] = 15.5
    front["teff_K"] = 9999                       # caso 2: valores DISTINTOS → no se toca, se reporta
    gt["host"]["teff_K"] = 5000
    front["spectral_type"] = "K0V"               # caso 3: ficha con valor, GT en null → no se toca
    gt["host"]["spectral_type"] = None

    _write_fm_body(host_path, front, body)
    gt_path.write_text(json.dumps(gt, indent=2), encoding="utf-8")

    # caso 1 también a nivel PLANETA (loop de código distinto: MIRROR_PLANET, no MIRROR_HOST) —
    # busca una estrella CON planeta entre el resto del censo para no pisar el host ya craftado.
    planet_slug = next((s for s in censo.star_slugs[1:] if censo.star_gt[s]["planets"]), None)
    if planet_slug is None:
        pytest.skip("ningún star sembrado (seed=104) tiene planetas — no se puede craftear el "
                    "caso planet-level de este test; no es un fallo del contrato, es mala suerte "
                    "de este seed")
    p_path = paths.STARS / f"{planet_slug}.md"
    p_front, p_body = _load_fm_body(p_path)
    letra = str(censo.star_gt[planet_slug]["planets"][0]["letter"])
    pl = next(pl for pl in p_front["planets"] if str(pl.get("letter")) == letra)
    k_gt_esperado = pl["K_ms"]                   # el ground-truth ya trae este valor (mirror exacto)
    pl["K_ms"] = None
    _write_fm_body(p_path, p_front, p_body)

    capsys.readouterr()
    rc = make_notes.sync_mirror()
    assert rc == 0
    out = capsys.readouterr().out

    front2, _ = _load_fm_body(host_path)
    assert front2["dist_pc"] == 15.5, "null+GT-con-valor: sync-mirror debía copiar y no copió"
    assert front2["teff_K"] == 9999, "sync-mirror PISÓ un valor de la ficha que difería del GT"
    assert front2["spectral_type"] == "K0V", (
        "sync-mirror INVENTÓ un valor donde el ground-truth no tenía nada")

    p_front2, _ = _load_fm_body(p_path)
    pl2 = next(pl for pl in p_front2["planets"] if str(pl.get("letter")) == letra)
    assert pl2["K_ms"] == k_gt_esperado, "null+GT-con-valor a nivel planeta: no se copió"

    # los dos casos "sin tocar" tienen que quedar REPORTADOS (no silenciosos: es la diferencia
    # entre "no hay autoridad" y "hay autoridad y la ficha la contradice", #70) — y el que SÍ se
    # copió no debe aparecer en el mismo renglón de "sin tocar".
    assert "teff_K" in out and "valores distintos" in out
    assert "spectral_type" in out and "no trae el valor" in out
    for linea in out.splitlines():
        if "sin tocar" in linea:
            assert "dist_pc" not in linea, "dist_pc se copió pero también quedó listado como sin tocar"

    m = re.search(r"sync-mirror: (\d+) campo\(s\) rellenados.*?(\d+) sin tocar", out)
    assert m, f"resumen de sync-mirror no matchea el formato esperado: {out!r}"
    rellenados, sin_tocar = int(m.group(1)), int(m.group(2))
    assert rellenados >= 2                        # dist_pc + K_ms del planeta
    assert sin_tocar >= 2                          # teff_K + spectral_type

    # add-only implica ADEMÁS idempotente sobre lo que quedó sin tocar: correrlo de nuevo no cambia
    # los dos residuos ni los vuelve a copiar.
    make_notes.sync_mirror()
    front3, _ = _load_fm_body(host_path)
    assert front3["teff_K"] == 9999
    assert front3["spectral_type"] == "K0V"


# ── 6. el ciclo completo: bloquea → migra → cierra → segunda pasada es un no-op byte a byte ────

def _correr_ciclo(paths, censo) -> None:
    """Los cuatro migradores/estampadores, en el orden del deploy real (CLAUDE.md, plan §5)."""
    make_notes.migrate_all_disputes()
    make_notes.restamp_headers()
    make_notes.sync_mirror()
    triage.migrate(censo.star_slugs[0])          # el único sujeto con build/<slug>/triage.json


def test_ciclo_completo_cierra_el_lint_y_la_segunda_pasada_es_no_op(sembrar):
    """EL test del task: no alcanza con "el migrador corrió sin error" (eso es lo que ya fallaba en
    el propio framework con el deadlock #69 — "22 estampadas" en cada corrida sin que el lint
    bajara nunca de 22). Acá el criterio es el ciclo completo: bloquea con las 3 categorías del
    schema viejo (conteo > 0) → se corren los 4 migradores en el orden del deploy → el lint da
    EXIT 0 con las 12 categorías bloqueantes en 0 → se corren los 4 DE NUEVO → el árbol de
    `vault/` es BYTE A BYTE idéntico al de la primera pasada (no sólo "el lint sigue en 0": nada se
    reescribió) y el lint sigue en exit 0.  @inv INV-22"""
    paths, censo = sembrar(n_papers=70, n_stars=5, n_concepts=8, seed=105, vintage="1.11.0")

    rc0, _ = _run_lint_reporte()
    assert rc0 == 1, "el corpus vintage tiene que arrancar bloqueado — si no, este test no prueba nada"

    _correr_ciclo(paths, censo)

    rc1, reporte1 = _run_lint_reporte()
    assert rc1 == 0, reporte1[:3000]
    for titulo in ("Wikilinks rotos", "Frontmatter no parseable", "Papers RETRACTADOS",
                  "Notas huérfanas", "Contradicciones ground-truth", "masa inconsistente con m",
                  "thesis_links sin página destino", "disputes: ref de una posición",
                  "disputes mal formadas", "disputes en el schema viejo",
                  "Juicio de triage en build", "`role` fuera del vocabulario"):
        n, _ = _categoria(reporte1, titulo)
        assert n == 0, f"{titulo!r} sigue con hallazgos después del ciclo completo"

    hash1 = hash_tree(paths.VAULT)

    _correr_ciclo(paths, censo)                  # segunda pasada: nada más que hacer

    rc2, reporte2 = _run_lint_reporte()
    assert rc2 == 0
    hash2 = hash_tree(paths.VAULT)
    assert hash1 == hash2, (
        "la segunda pasada de los migradores reescribió algo en vault/ — no es no-op: "
        "un estampador sin ancla de idempotencia (el patrón del deadlock #69) reescribiría en "
        "cada corrida sin que el lint lo note, porque el lint mide CATEGORÍAS, no bytes")


# ── 7. el ciclo no pierde contenido: papers intactos, prosa de fichas/conceptos preservada ─────

def test_upgrade_no_pierde_contenido_fuera_de_frontmatter_y_cabecera(sembrar):
    """Los cuatro pasos re-serializan frontmatter (los tres primeros) o insertan un bloque de
    cabecera (`restamp_headers`, después del `# H1`) — ninguno debería BORRAR o EDITAR una línea de
    prosa ya escrita. Papers: ningún migrador los toca → cuerpo IDÉNTICO byte a byte. Fichas y
    conceptos: el cuerpo cambia (crece con la cabecera), pero cada línea que estaba ANTES tiene que
    seguir apareciendo DESPUÉS, en el mismo orden relativo — la firma de "sólo inserción, nunca
    reescritura" (ver `_is_line_subsequence`)."""
    paths, censo = sembrar(n_papers=40, n_stars=4, n_concepts=6, seed=106, vintage="1.11.0")
    pre_bodies = _all_bodies(paths)

    _correr_ciclo(paths, censo)

    post_bodies = _all_bodies(paths)
    assert set(pre_bodies) == set(post_bodies), "el ciclo agregó o borró notas — no debería"

    for path_str, pre in pre_bodies.items():
        post = post_bodies[path_str]
        if "/papers/" in path_str.replace("\\", "/"):
            assert post == pre, f"{path_str}: un migrador tocó el cuerpo de un paper (no debería)"
        else:
            pre_lines = [l for l in pre.splitlines() if l.strip()]
            post_lines = [l for l in post.splitlines() if l.strip()]
            assert _is_line_subsequence(pre_lines, post_lines), (
                f"{path_str}: alguna línea de la prosa original desapareció o se editó tras el ciclo")
