"""Generador determinista de una bóveda POBLADA — la red que le falta a la suite de tier 0.

`tests/conftest.py::toy_vault` siembra 1-2 notas por test: toda categoría del lint que sólo
significa algo a ESCALA (¿son EXACTAMENTE los 30 huérfanos que sembré, ni uno más ni uno menos?
¿el lint sigue en 0 con 900 notas? ¿un schema viejo bloquea de verdad?) queda ciega ahí, porque en
vacío toda categoría da `(0)` y el test no distingue "pasa" de "ni miró" — ver
`vault/STATUS.md`/el plan de la 7ª auditoría para el diagnóstico completo.

`sembrar_corpus(paths, ...)` puebla un árbol repo/vault (la MISMA forma de `paths` que
`tests/conftest.py::toy_vault` expone: `paths.STARS`, `paths.PAPERS`, etc. — un `SimpleNamespace`
o cualquier objeto con esos atributos `Path`) con una distribución MEDIDA sobre el corpus real de
Almagesto-RV (relevancia 60/2/38 high/medium/low, ~24% de papers extraídos, ~74% con fulltext
legible, ground-truth consistente por construcción, fichas espejo exacto del ground-truth) y
devuelve un `Censo` — no un conteo suelto: los STEMS exactos de cada anomalía inyectada, para que
un test pueda afirmar "el lint reporta EXACTAMENTE estos 30 huérfanos" en vez de "≥1".

Determinismo: `random.Random(seed)` únicamente (nunca `random` global, nunca reloj de pared —
ver `hash_tree`, que dos siembras con el mismo seed deben producir bit a bit). Cuidado aparte:
NUNCA se itera un `set` de strings para tomar decisiones con el rng (la iteración de un `set` de
str depende de `PYTHONHASHSEED`, que no es fijo entre procesos) — todo lo que necesita orden
estable es una `list`/`range` construida en orden determinista, o un `set`/`dict` de ENTEROS (el
hash de un `int` chico es estable, `PYTHONHASHSEED` sólo mueve str/bytes).

`vintage="1.11.0"` emite el schema PRE-#71/#69/#73 (medido en la instancia real antes del
deploy a 1.21.0): `planets[]` sin `mass_earth` (dispara el espejo #70: la ficha no coincide con el
ground-truth que SÍ trae `mass_earth`), `planets[].disputes[]` en vez de `disputes` a nivel nota
(schema pre-#71, bloqueante), `build/<slug>/triage.json` (lugar pre-#51, bloqueante), papers sin
`role` ni `generator`, y ninguna nota lleva la línea `GENERATOR_LINE` (pre-#69). Combinar
`vintage="1.11.0"` con `anomalias` no está soportado (ver el `NotImplementedError` de abajo): el
schema viejo ya dispara sus categorías bloqueantes sobre TODO el corpus, así que "inyectar
exactamente K" del resto de las categorías dejaría de tener el significado que promete.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import yaml

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import lib_config as cfg                       # noqa: E402  (constante pura: ALMAGESTO_VERSION)
from extract_fulltext import is_legible         # noqa: E402  (función pura, sin side effects de ruta)
from fetch_ground_truth import msini_earth      # noqa: E402  (función pura)

# NO `from conftest import write_yaml`: tanto `tests/conftest.py` como `tests/poblada/conftest.py`
# se llaman "conftest.py" y ninguno de los dos directorios tiene `__init__.py`, así que pytest los
# importa a los DOS bajo el mismo nombre de módulo `conftest` — un `import conftest` desde acá
# (que pytest carga COMO PARTE de `tests/poblada/conftest.py`) resuelve contra el módulo que ya
# está a mitad de importar (éste mismo), no contra `tests/conftest.py` (`ImportError: partially
# initialized module`, reproducido al escribir este módulo). `write_yaml` es tres líneas: se
# reimplementa acá en vez de arrastrar esa fragilidad. `mk_note` (formato fijo, block-style) no
# sirve de todos modos: este módulo necesita alternar block/flow por campo (ver `_dump_fm`).


def write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

# GENERATOR_LINE es el ancla que el lint (#69) exige en TODA ficha/concepto; se referencia por
# STRING LITERAL (no `from make_notes import GENERATOR_LINE`) para no importar `make_notes`, que
# a su vez no hace nada pesado pero no hace falta — un solo lugar de verdad más simple: si el ancla
# cambia en el template, el test de vintage/cabecera de este módulo debe fallar y avisar.
GENERATOR_LINE = "> _Generado con Almagesto v"

ROLES = ("fundacional", "aplicacion", "arbitro")
BEARINGS = ("supports", "challenges", "method")
AREAS_OPEN = ("indicators", "activity")          # declaradas en concept_areas del objective sintético
AREAS_CYCLE = ("indicators", "activity", "methods", "hypotheses")   # 2 abiertas + 2 reservadas
SPECTRAL_TYPES = ("G2V", "K0V", "M3V", "F8V", "K5V", "G8V", "M0V")

# Campos de frontmatter que el schema declara LISTA DE ESCALARES (LIST_FIELDS con de_mapas=False en
# lint.py): son los que conviven en las dos formas YAML (block/flow) en el corpus real — CLAUDE.md
# documenta la confusión de las dos como un error medido DOS VECES. Los de lista-de-MAPAS
# (`planets`, `disputes`, `corrections`) siempre van en block (así los emite make_notes.fm() de
# verdad; nunca se vio la forma flow de esos en el corpus real).
_FLOWABLE_FIELDS = {"tags", "aliases", "stars", "topics", "methods", "thesis_links",
                    "activity_indicators_expected", "role"}

_WORDS = ("radial velocity activity index chromospheric spot rotation period amplitude signal "
         "periodogram bisector correlation host star planet candidate orbit eccentricity mass "
         "spectral synthetic corpus method indicator regime validity dataset harmonic alias "
         "window function noise jitter cadence baseline instrument").split()

SOPORTADAS = frozenset({
    "huerfanas", "thesis_colgantes", "disputes_colgantes", "no_sintetizado",
    "cobertura_citas", "cabecera_no_estampable", "fulltext_ilegible",
})


@dataclass(frozen=True)
class Censo:
    """Lo que `sembrar_corpus` sembró — no sólo conteos, los STEMS exactos: es lo que le permite a
    un test afirmar "el lint reporta EXACTAMENTE estos K, ni uno más" en vez de "≥1" (ver el
    docstring del módulo — es el requisito central del plan, §"de ahí sale...")."""
    seed: int
    vintage: str
    n_papers: int
    n_stars: int
    n_concepts: int
    paths: SimpleNamespace
    star_slugs: list           # [slug, ...]
    concept_stems: list        # [stem, ...] (normales + los reservados para anomalías)
    query_stems: list
    matrix_stems: list
    paper_stems: list          # [stem, ...] (== bibcode == nombre de archivo)
    relevance: dict            # stem(paper) -> "high"|"medium"|"low"
    extracted: set             # stems(paper) con `methods` poblado
    fulltext_legible: set      # stems(paper) con .txt legible en disco
    fulltext_illegible: set    # stems(paper) con .txt ILEGIBLE en disco (anomalía)
    star_gt: dict              # slug -> dict (el ground-truth tal como se escribió a JSON)
    anomalias: dict            # categoría -> lista de stems/claves inyectados (censo exacto)


def hash_tree(vault_root: Path) -> str:
    """SHA-256 determinista de TODO el árbol bajo `vault_root` (ruta relativa + contenido de cada
    archivo, en orden ordenado). Dos siembras con el mismo seed deben dar el MISMO hash byte a
    byte; seeds distintos, uno distinto — es el test de determinismo del generador."""
    h = hashlib.sha256()
    for p in sorted(vault_root.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(vault_root)).encode("utf-8")
            h.update(len(rel).to_bytes(4, "big"))
            h.update(rel)
            data = p.read_bytes()
            h.update(len(data).to_bytes(8, "big"))
            h.update(data)
    return h.hexdigest()


def _lorem(rng: random.Random, n_words: int) -> str:
    txt = " ".join(rng.choice(_WORDS) for _ in range(n_words))
    return txt[:1].upper() + txt[1:] + "."


def _dump_fm(d: dict, flow: bool) -> str:
    """Frontmatter YAML, campo por campo — así se puede forzar estilo FLOW por campo (las listas de
    escalares de `_FLOWABLE_FIELDS`) manteniendo todo lo demás en block, que es como lo emiten de
    verdad `make_notes.fm()` (siempre block) y `merge_frontmatter_list` (flow, la cirugía add-only
    del retro-linkeo) — las DOS formas que CLAUDE.md documenta conviviendo en el corpus real."""
    lines = []
    for k, v in d.items():
        if (flow and k in _FLOWABLE_FIELDS and isinstance(v, list)
                and all(isinstance(x, (str, int, float, bool)) or x is None for x in v)):
            inner = ", ".join("null" if x is None else str(x) for x in v)
            lines.append(f"{k}: [{inner}]")
        else:
            chunk = yaml.safe_dump({k: v}, sort_keys=False, allow_unicode=True,
                                   default_flow_style=False)
            lines.append(chunk.rstrip("\n"))
    return "---\n" + "\n".join(lines) + "\n---\n"


def _write_note(path: Path, fm: dict, body: str, flow: bool) -> None:
    fm_text = _dump_fm(fm, flow)
    # cinturón: el round-trip tiene que reconstruir el MISMO dict — si `_dump_fm` alguna vez rompe
    # el YAML (un campo con un carácter especial, p.ej.) mejor reventar acá, en la siembra, que
    # dejar una nota corrupta que el lint reporte de forma confusa después.
    parsed = yaml.safe_load(fm_text.split("---")[1])
    assert parsed == fm, f"round-trip de frontmatter roto para {path.name}: {parsed!r} != {fm!r}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm_text + body, encoding="utf-8")


def _make_planet(rng: random.Random, letter: str, mstar_msun: float) -> dict:
    """Planeta GT consistente POR CONSTRUCCIÓN: `mass_earth` sale de `msini_earth(K,P,e,M*)`, la
    MISMA función que usa el lint para re-derivarlo — así el chequeo "masa inconsistente con
    m·sini" (bloqueante) nunca puede fallar por drift de redondeo (el margen del lint es además
    generoso, factor 3, pero acá coincide exacto)."""
    P = round(rng.uniform(2.0, 400.0), 2)
    K = round(rng.uniform(0.5, 60.0), 3)
    e = round(rng.uniform(0.0, 0.4), 3)
    mass = msini_earth(K, P, e, mstar_msun)
    assert mass is not None
    return {"letter": letter, "P_days": P, "K_ms": K, "e": e,
            "mass_earth": round(mass, 3), "status": "confirmed"}


def _make_star_gt(rng: random.Random, slug: str, n_planets: int) -> tuple[dict, dict]:
    """(gt, host) — `gt` es el dict tal como se escribe a `raw/ground_truth/<slug>.json`."""
    mstar = round(rng.uniform(0.6, 1.3), 3)
    host = {
        "mass_msun": mstar,
        "spectral_type": rng.choice(SPECTRAL_TYPES),
        "teff_K": rng.randint(3200, 6200),
        "dist_pc": round(rng.uniform(3.0, 60.0), 2),
        "st_rotp_days": round(rng.uniform(5.0, 45.0), 2) if rng.random() < 0.5 else None,
    }
    planets = [_make_planet(rng, chr(ord("b") + k), mstar) for k in range(n_planets)]
    gt = {"slug": slug, "host": host, "planets": planets}
    return gt, host


def sembrar_corpus(paths, n_papers: int = 900, n_stars: int = 4, n_concepts: int = 20,
                   seed: int = 0, vintage: str = cfg.ALMAGESTO_VERSION,
                   anomalias: dict | None = None) -> Censo:
    """Puebla `paths` (mismo shape que `tests/conftest.py::toy_vault`) con un corpus sintético
    determinista. Ver el docstring del módulo para la distribución, el vintage y las anomalías
    soportadas. `paths` DEBE ser un árbol vacío (o al menos, sin colisión de nombres): esta función
    no es idempotente y no protege nada existente — es un generador, no un `make_notes`."""
    anomalias = dict(anomalias or {})
    no_soportadas = set(anomalias) - SOPORTADAS
    if no_soportadas:
        raise ValueError(f"anomalías no soportadas: {sorted(no_soportadas)} — soportadas: "
                         f"{sorted(SOPORTADAS)}")
    for k, v in anomalias.items():
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ValueError(f"anomalias[{k!r}] debe ser un entero >= 0, es {v!r}")

    vintage_old = (vintage == "1.11.0")
    if vintage_old and anomalias:
        raise NotImplementedError(
            "combinar vintage='1.11.0' con `anomalias` no está soportado: el schema viejo ya "
            "dispara sus categorías bloqueantes (old_disputes, legacy_triage, contradicciones del "
            "espejo #70) sobre TODO el corpus, así que 'inyectar exactamente K' del resto de las "
            "categorías dejaría de tener el significado que promete el Censo. Sembrá dos corpus "
            "separados (uno por vintage, otro por anomalias) si necesitás las dos cosas."
        )

    rng = random.Random(seed)

    K_huer = anomalias.get("huerfanas", 0)
    K_thesis = anomalias.get("thesis_colgantes", 0)
    K_disp = anomalias.get("disputes_colgantes", 0)
    K_nosint = anomalias.get("no_sintetizado", 0)
    K_cov = anomalias.get("cobertura_citas", 0)
    K_header = anomalias.get("cabecera_no_estampable", 0)
    K_illeg = anomalias.get("fulltext_ilegible", 0)

    K_header_stars = min(K_header, n_stars)
    K_header_concepts = K_header - K_header_stars

    n_concept_anom = K_cov + K_huer + K_disp + K_header_concepts
    total_concepts = n_concepts + n_concept_anom
    n_paper_anom = K_thesis + K_nosint + K_illeg
    if n_paper_anom > n_papers:
        raise ValueError(f"anomalías de papers ({n_paper_anom}) exceden n_papers ({n_papers})")

    ALMAGESTO_VERSION = cfg.ALMAGESTO_VERSION

    # ── estructura de conceptos (stems/áreas; el CONTENIDO se llena después de los papers) ──────
    all_concepts = [(f"concepto-{AREAS_CYCLE[i % 4]}-{i:03d}", AREAS_CYCLE[i % 4])
                    for i in range(total_concepts)]
    cursor = total_concepts

    def _take_c(k):
        nonlocal cursor
        cursor -= k
        return all_concepts[cursor:cursor + k]

    cov_concepts = _take_c(K_cov)
    huer_concepts = _take_c(K_huer)
    disp_concepts = _take_c(K_disp)
    header_concepts = _take_c(K_header_concepts)
    huer_stems = {s for s, _ in huer_concepts}
    cov_stems = {s for s, _ in cov_concepts}
    # "citable" = puede recibir citas [[bibcode]] de un paper extraído sin arruinar la anomalía que
    # lleva encima: huérfano sigue siendo huérfano si nadie lo LINKEA (incoming), citar HACIA
    # AFUERA no lo afecta; cobertura_citas en cambio exige CERO citas propias, así que se excluye.
    citable_concepts = [c for c in all_concepts if c[0] not in cov_stems]
    # "linkeable" = puede recibir un [[wikilink]] de index.md/estrella sin arruinar "huérfano".
    linkable_concepts = [c for c in all_concepts if c[0] not in huer_stems]

    # ── estrellas + ground-truth ──────────────────────────────────────────────────────────────
    star_slugs = [f"star{i:02d}" for i in range(n_stars)]
    star_names = [f"Estrella Poblada {i:02d}" for i in range(n_stars)]
    header_star_slugs = set(star_slugs[-K_header_stars:]) if K_header_stars else set()

    star_gt, star_hosts, star_planets = {}, {}, {}
    for i, slug in enumerate(star_slugs):
        n_pl = rng.choice([0, 1, 1, 2, 2, 3])
        if vintage_old and i == 0:
            n_pl = max(n_pl, 1)     # necesita ≥1 planeta para la disputa vieja + espejo roto
        gt, host = _make_star_gt(rng, slug, n_pl)
        star_gt[slug] = gt
        star_hosts[slug] = host
        star_planets[slug] = gt["planets"]

    # ── papers: metadata + reservas de anomalías (cola de índices, ver docstring del módulo) ────
    REL_LABELS, REL_WEIGHTS = ("high", "medium", "low"), (0.60, 0.02, 0.38)

    def _pick_relevance():
        r, c = rng.random(), 0.0
        for lab, w in zip(REL_LABELS, REL_WEIGHTS):
            c += w
            if r < c:
                return lab
        return REL_LABELS[-1]

    paper_years = [rng.randint(1995, 2025) for _ in range(n_papers)]
    paper_stems = [f"{paper_years[i]}Alm{i:05d}A" for i in range(n_papers)]
    paper_relevance = {paper_stems[i]: _pick_relevance() for i in range(n_papers)}

    tail = n_papers

    def _take_p(k):
        nonlocal tail
        tail -= k
        return list(range(tail, tail + k))

    illeg_idx = set(_take_p(K_illeg))
    nosint_idx = set(_take_p(K_nosint))
    thesis_idx = set(_take_p(K_thesis))
    normal_range = range(0, tail)
    for i in nosint_idx:
        paper_relevance[paper_stems[i]] = "high"   # asegura elegibilidad (relevancia != low)

    extract_pool = [i for i in normal_range if paper_relevance[paper_stems[i]] in ("high", "medium")]
    rng.shuffle(extract_pool)
    n_extract_target = round(0.24 * n_papers)
    extracted_idx = set(extract_pool[:min(n_extract_target, len(extract_pool))])
    extracted_idx |= nosint_idx     # los anómalos de "no_sintetizado" están SIEMPRE extraídos

    to_cite = sorted(extracted_idx - nosint_idx)     # los que SÍ deben terminar citados en algún lado

    home_slugs = [star_slugs[i % n_stars] for i in range(n_papers)]
    legible_target = round(0.74 * n_papers)
    legible_pool = [i for i in range(n_papers) if i not in illeg_idx]
    rng.shuffle(legible_pool)
    legible_idx = set(legible_pool[:min(legible_target, len(legible_pool))])

    # roles/thesis_links/bearing de los extraídos (sólo lo NECESARIO para que el vocabulario
    # cerrado nunca produzca un `bad_roles`/`dangling_thesis` accidental en el corpus limpio)
    paper_roles: dict[int, list] = {}
    paper_thesis: dict[int, list] = {}
    paper_bearing: dict[int, str | None] = {}
    for k, i in enumerate(sorted(extracted_idx)):
        if rng.random() < 0.6:
            paper_roles[i] = [rng.choice(ROLES)]
        else:
            paper_roles[i] = []
    for k, i in enumerate(to_cite):
        if k % 2 == 0 and all_concepts:
            paper_thesis[i] = [all_concepts[k % len(all_concepts)][0]]
            paper_bearing[i] = rng.choice(BEARINGS)
    for i in thesis_idx:
        paper_thesis[i] = [f"tema-fantasma-{i:04d}"]
        paper_bearing[i] = "supports"

    # ── reparto de citas [[bibcode]] hacia los conceptos: TODO extraído "normal" (no reservado
    # para no_sintetizado) tiene que terminar citado por al menos un concepto — si no, el corpus
    # "limpio" no daría lint exit 0 (ver #75 en CLAUDE.md/lint.py: extraído-pero-no-sintetizado es
    # backlog, pero acá lo cerramos también en la línea base para que la anomalía sea el ÚNICO
    # motivo del hallazgo cuando se pide explícitamente). ──
    concept_citations: dict[str, list] = {s: [] for s, _ in all_concepts}
    it = iter(to_cite)
    for stem, _ in citable_concepts:
        try:
            j = next(it)
        except StopIteration:
            break
        concept_citations[stem].append(paper_stems[j])
    resto = list(it)
    if citable_concepts:
        for k, j in enumerate(resto):
            stem, _ = citable_concepts[k % len(citable_concepts)]
            concept_citations[stem].append(paper_stems[j])
    elif resto:
        raise ValueError("no hay conceptos citables (revisá n_concepts vs. cobertura_citas) pero "
                         f"hay {len(resto)} papers extraídos que necesitan cita")

    # ── escritura: ground-truth ───────────────────────────────────────────────────────────────
    for slug, gt in star_gt.items():
        p = paths.GROUND_TRUTH / f"{slug}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(gt, indent=2, sort_keys=False), encoding="utf-8")

    # ── escritura: estrellas ──────────────────────────────────────────────────────────────────
    for i, slug in enumerate(star_slugs):
        host = star_hosts[slug]
        planets_ficha = [dict(p) for p in star_planets[slug]]        # espejo EXACTO (mismos floats)
        if vintage_old:
            for p in planets_ficha:
                p.pop("mass_earth", None)
            if planets_ficha:
                planets_ficha[0]["disputes"] = [
                    {"field": "K", "ref": paper_stems[0], "alt": 5.0,
                     "note": "disputa vieja de ejemplo (schema pre-1.19.0)"}]
        front = {
            "name": star_names[i], "slug": slug, "aliases": [f"ALM {i:04d}"],
            "simbad_id": f"TST {i:04d}",
            "spectral_type": host["spectral_type"], "teff_K": host["teff_K"],
            "dist_pc": host["dist_pc"], "P_rot_days": host["st_rotp_days"],
            "activity_indicators_expected": ["H-alpha", "Ca II H&K"],
            "planets": planets_ficha,
        }
        if not vintage_old:
            front["disputes"] = []
        front.update({
            "data_local": None,
            "methods_applied": {"literature": [], "ours": []},
            "confidence": "medium",
            "tags": ["star"],
        })
        if not vintage_old:
            front["generator"] = f"Almagesto v{ALMAGESTO_VERSION}"

        link_concepts = citable_concepts[i % len(citable_concepts)][0] if citable_concepts else None
        planet_lines = "\n".join(f"**{p['letter']}** (P={p['P_days']} d, K={p['K_ms']} m/s)."
                                 for p in planets_ficha)
        gen_line = (f"{GENERATOR_LINE}{ALMAGESTO_VERSION}._\n"
                   if (not vintage_old) and slug not in header_star_slugs else "")
        body = f"""
# {star_names[i]}

> Ficha sintética (bóveda poblada de tests). {gen_line}
## Resumen
{_lorem(rng, 25)} {planet_lines}
{f"Ver también [[{link_concepts}]]." if link_concepts else ""}

## Huecos
_(ninguno relevante — corpus sintético)_
"""
        _write_note(paths.STARS / f"{slug}.md", front, body, flow=(i % 2 == 0))

    # ── escritura: conceptos ──────────────────────────────────────────────────────────────────
    disp_stems = {s for s, _ in disp_concepts}
    header_c_stems = {s for s, _ in header_concepts}
    for k, (stem, area) in enumerate(all_concepts):
        front = {"name": stem.replace("-", " ").title(), "aliases": []}
        if area == "hypotheses":
            front["status"] = "active"
        front["disputes"] = []
        if stem in disp_stems:
            front["disputes"] = [{
                "field": "eje-sintetico",
                "posiciones": [
                    {"ref": f"__nota_inexistente_{k:04d}__"},
                    {"source": "ground_truth", "value": "x"},
                ],
            }]
        front.update({"tags": [area, "thesis"], "confidence": "medium"})
        if not vintage_old:
            front["generator"] = f"Almagesto v{ALMAGESTO_VERSION}"

        citas = concept_citations.get(stem, [])
        citas_txt = ("Ver " + ", ".join(f"[[{c}]]" for c in citas) + "."
                    if citas else "_(sin papers citados)_")
        gen_line = (f"{GENERATOR_LINE}{ALMAGESTO_VERSION}._\n"
                   if (not vintage_old) and stem not in header_c_stems else "")
        body = f"""
# {front['name']}

> Concepto sintético (bóveda poblada de tests). {gen_line}
## Síntesis
{_lorem(rng, 25)} {citas_txt}

## Huecos
_(ninguno relevante — corpus sintético)_
"""
        _write_note(paths.CONCEPTS / area / f"{stem}.md", front, body, flow=(k % 2 == 1))

    # ── escritura: papers + fulltext ──────────────────────────────────────────────────────────
    fulltext_legible, fulltext_illegible = set(), set()
    for i in range(n_papers):
        stem, year, home = paper_stems[i], paper_years[i], home_slugs[i]
        relev = paper_relevance[stem]
        is_extracted = i in extracted_idx
        methods = [f"metodo-sintetico-{(i % 5) + 1}"] if is_extracted else []
        roles = paper_roles.get(i, [])
        thesis_links = paper_thesis.get(i, [])
        bearing = paper_bearing.get(i)

        has_ft = i in legible_idx or i in illeg_idx
        ft_rel = f"../../raw/fulltext/{home}/{stem}.txt" if has_ft else None
        ft_src = "pdftotext" if has_ft else None

        front = {
            "bibcode": stem, "title": f"Paper sintético {i:05d}",
            "first_author": f"Autor{i:04d}", "n_authors": rng.randint(1, 6),
            "year": year, "arxiv_id": None, "doi": None, "bibstem": "Synt",
            "stars": [star_names[i % n_stars]], "topics": [], "methods": methods,
            "thesis_links": thesis_links, "bearing": bearing,
            "relevance": relev, "citation_count": rng.randint(0, 200),
            "pdf": None, "fulltext": ft_rel, "fulltext_source": ft_src, "pdf_source": None,
            "confidence": "medium", "tags": ["paper"],
        }
        if not vintage_old:
            front["role"] = roles
            front["generator"] = f"Almagesto v{ALMAGESTO_VERSION}"
        flow = (i % 2 == 1)
        # citas cruzadas paper→paper: sólo densidad de wikilinks (~4/nota medido en el corpus real,
        # CLAUDE.md §"Inventario por eje"), sin efecto en NINGUNA categoría del lint — un link
        # SALIENTE de una nota de `papers/` no es de una "nota de entidad" (`in_entity_note` sólo
        # mira `stars/`/`concepts/`), así que no cuenta para `cited_in_entity` (#75) ni para
        # ninguna otra categoría: citar acá un `no_sintetizado` reservado NO lo "sintetiza".
        related = [paper_stems[(i + off) % n_papers] for off in (37, 101, 199, 251, 307)
                  if (i + off) % n_papers != i][:rng.randint(2, 5)]
        related_txt = ("\n\nVer también " + ", ".join(f"[[{r}]]" for r in related) + "."
                      if related else "")
        body = (f"# {front['title']}\n\n**{front['first_author']}** ({year}) · ADS: `{stem}`\n\n"
               f"## Abstract\n{_lorem(rng, 40)}{related_txt}\n")
        _write_note(paths.PAPERS / f"{stem}.md", front, body, flow)

        if has_ft:
            ftdir = paths.FULLTEXT / home
            ftdir.mkdir(parents=True, exist_ok=True)
            if i in illeg_idx:
                txt = "x"                                    # < 200 chars no-espacio → ilegible
                ok, _ = is_legible(txt)
                assert not ok
                fulltext_illegible.add(stem)
            else:
                txt = " ".join(rng.choice(_WORDS) for _ in range(400)) + ".\n"
                ok, _ = is_legible(txt)
                assert ok
                fulltext_legible.add(stem)
            (ftdir / f"{stem}.txt").write_text(txt, encoding="utf-8")

    # ── escritura: queries ────────────────────────────────────────────────────────────────────
    n_queries = max(2, n_concepts // 10)
    query_stems = [f"query-{i:03d}" for i in range(n_queries)]
    for i, qstem in enumerate(query_stems):
        cite = paper_stems[i % n_papers]
        front = {"tags": ["query"], "confidence": "medium"}
        if not vintage_old:
            front["generator"] = f"Almagesto v{ALMAGESTO_VERSION}"
        body = f"\n# Query sintética {i:03d}\n\n_(pregunta sintética, corpus de tests)_\n\nVer [[{cite}]].\n"
        _write_note(paths.QUERIES / f"{qstem}.md", front, body, flow=(i % 2 == 0))

    # ── escritura: matriz ─────────────────────────────────────────────────────────────────────
    matrix_stem = "method_star"
    front = {"tags": ["matrix"], "confidence": "medium"}
    if not vintage_old:
        front["generator"] = f"Almagesto v{ALMAGESTO_VERSION}"
    rows = "\n".join(f"| [[{s}]] | metodo-sintetico-1 |" for s in star_slugs)
    body = f"\n# Matriz método x estrella\n\n_(matriz sintética, corpus de tests)_\n\n| Estrella | Método |\n|---|---|\n{rows}\n"
    _write_note(paths.MATRICES / f"{matrix_stem}.md", front, body, flow=False)

    # ── escritura: index/log (prosa plana, sin frontmatter — legítimo, ver fm_error) ────────────
    idx_lines = ["# Índice de la bóveda poblada (tests)", "", "## Estrellas"]
    idx_lines += [f"- [[{s}]]" for s in star_slugs]
    idx_lines += ["", "## Conceptos"]
    idx_lines += [f"- [[{s}]]" for s, _ in linkable_concepts]
    idx_lines += ["", "## Queries"]
    idx_lines += [f"- [[{q}]]" for q in query_stems]
    idx_lines += ["", "## Matrices", f"- [[{matrix_stem}]]", ""]
    paths.INDEX.parent.mkdir(parents=True, exist_ok=True)
    paths.INDEX.write_text("\n".join(idx_lines), encoding="utf-8")
    paths.LOG.write_text("# Log\n\n## sembrado — corpus sintético\n- generado por sembrar_corpus\n",
                         encoding="utf-8")

    # ── escritura: config ─────────────────────────────────────────────────────────────────────
    objective = {
        "name": "Bóveda poblada (tests)",
        "short": "poblada",
        "description": "Corpus sintético determinista para tests/poblada — no es una bóveda real.",
        "concept_areas": [*AREAS_OPEN, "methods", "hypotheses"],
        "relevance": {"topics": {"sintetico": "synthetic|sintetico"}, "noise_doctypes": ["catalog"]},
    }
    stars_yaml = {star_names[i]: {"slug": star_slugs[i], "simbad": f"TST {i:04d}",
                                  "ads_object": star_names[i], "aliases": [], "data_local": None}
                 for i in range(n_stars)}
    paths.CONFIG.mkdir(parents=True, exist_ok=True)
    write_yaml(paths.OBJECTIVE_YAML, objective)
    write_yaml(paths.STARS_YAML, stars_yaml)
    write_yaml(paths.TOPICS_YAML, {})
    paths.REGISTRO.mkdir(parents=True, exist_ok=True)
    paths.PDFS.mkdir(parents=True, exist_ok=True)

    # ── vintage: resto pre-1.9.0/#51 (triage.json legacy) ─────────────────────────────────────
    if vintage_old:
        legacy = paths.ROOT / "build" / star_slugs[0] / "triage.json"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(json.dumps({"decisiones": {}}), encoding="utf-8")

    # ── censo de anomalías (stems exactos) ────────────────────────────────────────────────────
    anomalias_censo: dict[str, list] = {}
    if K_huer:
        anomalias_censo["huerfanas"] = sorted(s for s, _ in huer_concepts)
    if K_thesis:
        anomalias_censo["thesis_colgantes"] = sorted(f"tema-fantasma-{i:04d}" for i in thesis_idx)
    if K_disp:
        anomalias_censo["disputes_colgantes"] = sorted(s for s, _ in disp_concepts)
    if K_nosint:
        anomalias_censo["no_sintetizado"] = sorted(paper_stems[i] for i in nosint_idx)
    if K_cov:
        anomalias_censo["cobertura_citas"] = sorted(s for s, _ in cov_concepts)
    if K_header:
        anomalias_censo["cabecera_no_estampable"] = sorted(
            header_star_slugs | {s for s, _ in header_concepts})
    if K_illeg:
        anomalias_censo["fulltext_ilegible"] = sorted(paper_stems[i] for i in illeg_idx)

    return Censo(
        seed=seed, vintage=vintage, n_papers=n_papers, n_stars=n_stars, n_concepts=n_concepts,
        paths=paths, star_slugs=list(star_slugs),
        concept_stems=[s for s, _ in all_concepts], query_stems=list(query_stems),
        matrix_stems=[matrix_stem], paper_stems=list(paper_stems),
        relevance=dict(paper_relevance), extracted={paper_stems[i] for i in extracted_idx},
        fulltext_legible=fulltext_legible, fulltext_illegible=fulltext_illegible,
        star_gt=star_gt, anomalias=anomalias_censo,
    )
