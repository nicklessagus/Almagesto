"""Lint de la wiki — chequeo de salud (operación del patrón LLM Wiki).

Uso:
    python lint.py            # imprime resumen y escribe outputs/lint-<fecha>.md

Detecta: wikilinks rotos (página faltante), notas huérfanas (sin links entrantes),
contradicciones ground-truth ↔ ficha, **masa de ground-truth inconsistente** con la
m·sini implícita por K/P/e/M* (atrapa best-mass espurias de NEA), `thesis_links` sin
página destino (tag que no matchea ninguna nota concepto/hipótesis → no acumula),
**fuga de implementación** (material de implementación/código no bibliográfico que se
filtró al vault; frontera dura, regla #0 de CLAUDE.md; WARN no bloqueante), **áreas de concepts/ fuera
de `concept_areas`** (subcarpeta de concepts/ no declarada en objective.yaml → posible typo/carpeta
fantasma; WARN), **PDF ↔ disco** (drift: el campo `pdf` de un paper no refleja el PDF bajado — sin linkear
o puntero a archivo inexistente; WARN), **citas no verificables** (bibcode
citado en query/concepto/hipótesis sin su `.txt` en `vault/raw/fulltext/` → no se puede chequear claim↔fuente
con el skill `verify-citations`), **cobertura** (concepto/hipótesis sin ninguna cita `[[bibcode]]` →
afirmaciones no chequeables; backlog), y campos clave
incompletos (P_rot null, papers relevantes sin `methods`, `thesis_links` sin `bearing`).
No modifica nada: reporta para que el agente/usuario decida.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import re

import yaml

import lib_config as cfg
from fetch_ground_truth import msini_earth   # verificación de masa (m·sini implícita)

LINK_RE = re.compile(r"\[\[([^\]\|#]+)")
# Frontera dura (regla #0 de CLAUDE.md): la bóveda es SÓLO bibliografía. Detecta material de
# implementación/código no bibliográfico que se filtró a una nota. WARN, no bloquea: son heurísticas de
# alta señal/bajo ruido; se saltan los blockquotes meta (frontera/alcance). Revisar a mano cada hit.
IMPL_LEAK_RE = [
    (re.compile(r"\bperilla\b", re.I), "perilla (dial de implementación)"),
    (re.compile(r"\bdial\b", re.I), "dial de implementación"),
    (re.compile(r"w_\{?j"), "pesos por orden w_j (parámetro de código)"),
    (re.compile(r"=\s*peso\("), "vector de mezcla peso(azul)/peso(rojo)"),
]
# targets que son texto de ejemplo/placeholder, no links reales
LINK_SKIP = {"..", "...", "link", "links", "wikilinks", "bibcode", "related-concept",
             "attention-mechanism", "rag"}
NON_ORPHAN = {"index", "log", "README"}  # navegación, no son huérfanos


def split_fm(text: str) -> dict:
    parts = text.split("---")
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


def basename(p: str) -> str:
    return p.rsplit("/", 1)[-1]


def note_files() -> list:
    # incluye index.md/log.md (aportan links entrantes); se excluyen de orfandad por nombre.
    files = glob.glob(str(cfg.WIKI / "**" / "*.md"), recursive=True)
    files += glob.glob(str(cfg.RAW / "refs" / "*.md"))
    return files


BIBCODE_RE = re.compile(r"^\d{4}[A-Za-z]")   # heurística: target de link que parece bibcode


def main() -> int:
    files = note_files()
    # fulltext disponible (un .txt por bibcode, bajo cualquier slug/tema) → precondición de
    # verificabilidad: una cita en query/hipótesis sin su .txt no se puede chequear claim↔fuente.
    fulltext = {basename(p)[:-4] for p in glob.glob(str(cfg.RAW / "fulltext" / "**" / "*.txt"),
                                                     recursive=True)}
    # PDFs en disco (un <bibcode>.pdf por slug en vault/raw/pdfs/) → chequear drift `pdf` ↔ archivo.
    # stem = safe_name(bibcode), igual que el nombre de la nota del paper.
    pdf_on_disk = {}
    for _p in glob.glob(str(cfg.PDFS / "**" / "*.pdf"), recursive=True):
        pdf_on_disk.setdefault(basename(_p)[:-4], _p)
    unverifiable: list = []            # (stem, "cita <bibcode> sin fulltext")
    coverage: list = []                # concept/hipótesis sin citas [[bibcode]] → no chequeable
    names = {p.rsplit("/", 1)[-1][:-3] for p in files}  # stems referenciables por [[..]]
    incoming: dict[str, int] = {n: 0 for n in names}
    kinds: dict[str, list] = {}
    broken, incomplete, contradictions = [], [], []
    impl_leaks: list = []              # (stem, "línea N: marcador → texto") — fuga de implementación
    pdf_issues: list = []              # (stem, ...) — drift frontmatter `pdf` ↔ PDF en disco
    thesis_refs: dict[str, list] = {}  # valor de thesis_link -> notas que lo usan
    dispute_refs: list = []            # (estrella, planeta, ref) de planets[].disputes

    refs_dir = str(cfg.RAW / "refs")
    refs_stems = {basename(f)[:-3] for f in files if f.startswith(refs_dir)}  # docs de diseño, no fichas
    for f in files:
        text = open(f, encoding="utf-8").read()
        fm = split_fm(text)
        stem = basename(f)[:-3]
        kinds[stem] = fm.get("tags", []) or []
        # links salientes (las refs de diseño tienen links-ejemplo: no contar sus salientes)
        if f.startswith(refs_dir):
            continue
        # precondición de verificabilidad: en queries/concepts/hipótesis, toda cita-bibcode necesita
        # su fulltext para poder correr verify-citations (chequeo claim↔fuente).
        in_verifiable_note = "/queries/" in f or "/concepts/" in f   # concepts/ incluye hypotheses/
        nbib = 0                              # citas [[bibcode]] en esta nota
        for tgt in LINK_RE.findall(text):
            tgt = tgt.strip()
            if "/" in tgt or tgt in LINK_SKIP:
                continue                       # placeholder/ejemplo, no link real
            if tgt in incoming:
                incoming[tgt] += 1
            elif tgt not in names:
                broken.append((stem, tgt))
            if BIBCODE_RE.match(tgt):
                nbib += 1
                if in_verifiable_note and tgt not in fulltext:
                    unverifiable.append((stem, f"cita {tgt} sin fulltext (no chequeable claim↔fuente)"))
        # cobertura: un concepto/hipótesis que afirma sin ninguna cita [[bibcode]] no es chequeable
        # (todo lo apuntable debe ser citable o marcado `inferencia`; ver Verify en CLAUDE.md). Backlog.
        if "/concepts/" in f and nbib == 0:
            coverage.append((stem, "sin citas [[bibcode]] → afirmaciones no chequeables (cobertura)"))
        # frontera dura: fuga de implementación (código no bibliográfico) al vault (WARN, no bloquea).
        body_full = text.split("---", 2)[-1] if text.startswith("---") else text
        scan_leaks = stem not in NON_ORPHAN    # log/index/README son historia/navegación, no fichas
        for i, line in enumerate(body_full.splitlines(), 1) if scan_leaks else []:
            if line.lstrip().startswith(">"):
                continue                       # blockquote meta (frontera/alcance)
            for rx, label in IMPL_LEAK_RE:
                if rx.search(line):
                    impl_leaks.append((stem, f"L{i} [{label}]: {line.strip()[:80]}"))
                    break
        # chequeos de completitud por tipo
        tags = fm.get("tags", []) or []
        if "star" in tags:
            if fm.get("P_rot_days") in (None, ""):
                incomplete.append((stem, "P_rot_days nulo"))
            if not fm.get("activity_indicators_expected"):
                incomplete.append((stem, "activity_indicators_expected vacío"))
            # autosuficiencia (proxy estructural): cada planeta del frontmatter debe discutirse en
            # la prosa (la ficha tiene que alcanzar sola; ver "estándar de la ficha" en CLAUDE.md).
            body = text.split("---", 2)[-1] if text.startswith("---") else text
            for pl in (fm.get("planets") or []):
                l = str(pl.get("letter", "")).strip()
                if not l:
                    continue
                pats = [rf"\*\*[^*]*\b{re.escape(l)}\b[^*]*\*\*",  # negrita (incl. **b/c/d**)
                        rf"\|\s*{re.escape(l)}\s*\|",               # celda de tabla
                        rf"_{re.escape(l)}\b",                       # subíndice $M_b$/$K_b$
                        rf"\b{re.escape(l)}\s*\("]                   # "b (P=...)"
                if not any(re.search(p, body) for p in pats):
                    incomplete.append((stem, f"planeta {l} en frontmatter pero no discutido en prosa"))
                for d in (pl.get("disputes") or []):       # disputa de existencia/valor → traza paper
                    ref = str(d.get("ref", "")).strip()
                    if ref:
                        dispute_refs.append((stem, l, ref))
        if "paper" in tags:
            if fm.get("relevance") == "high" and not fm.get("methods"):
                incomplete.append((stem, "paper relevante sin methods (sin extraer)"))
            if fm.get("thesis_links") and not fm.get("bearing"):
                incomplete.append((stem, "thesis_links sin bearing"))
            for tl in (fm.get("thesis_links") or []):
                thesis_refs.setdefault(str(tl), []).append(stem)
            # PDF ↔ disco (higiene; WARN): el campo `pdf` debe reflejar el PDF real bajado.
            pdf, on_disk = fm.get("pdf"), pdf_on_disk.get(stem)
            if pdf:
                if not (cfg.WIKI / "papers" / pdf).resolve().exists():
                    pdf_issues.append((stem, f"`pdf` apunta a archivo inexistente: {pdf}"))
            elif on_disk:                      # pdf null/vacío pero el PDF está bajado → drift
                slug_dir = on_disk.rsplit("/", 2)[-2]
                pdf_issues.append((stem, f"PDF en disco sin linkear → poné `pdf: ../../raw/pdfs/{slug_dir}/{stem}.pdf`"))

    # contradicción ground-truth ↔ ficha (nº de planetas) + masa sospechosa
    mass_issues = []
    for gtf in glob.glob(str(cfg.GROUND_TRUTH / "*.json")):
        gt = json.loads(open(gtf).read())
        slug = gt.get("slug") or basename(gtf)[:-5]   # robusto si un GT a mano no trae 'slug'
        mstar = (gt.get("host") or {}).get("mass_msun")
        for p in gt.get("planets", []) or []:
            if p.get("mass_flag"):                       # ya marcado por el fetch
                mass_issues.append((slug, f"{p.get('letter')}: {p['mass_flag']}"))
                continue
            chk = msini_earth(p.get("K_ms"), p.get("P_days"), p.get("e"), mstar)
            m = p.get("mass_earth")
            if chk and m and not (1 / 3 < m / chk < 3):  # fallback (json viejo sin flag)
                mass_issues.append((slug, f"{p.get('letter')}: mass_earth={m:.3g} M⊕ "
                                          f"≠ m·sini implícita {chk:.3g} M⊕"))
        sf = cfg.STARS / f"{slug}.md"
        if sf.exists():
            fm = split_fm(open(sf).read())
            n_note = len(fm.get("planets", []) or [])
            n_gt = len(gt.get("planets", []) or [])
            if n_note != n_gt:
                contradictions.append((slug, f"ficha {n_note} planetas vs ground-truth {n_gt}"))

    # huérfanos: notas-concepto sin links entrantes. Papers/estrellas se acceden por
    # Dataview/index, no por wikilink → no son huérfanos genuinos. README tampoco.
    def is_orphan_candidate(n: str) -> bool:
        tags = kinds.get(n, [])
        return (not ({"paper", "star"} & set(tags))
                and n not in NON_ORPHAN and n not in refs_stems)
    orphans = [n for n, c in incoming.items() if c == 0 and is_orphan_candidate(n)]

    # thesis_links sin página destino: el tag no matchea ninguna nota → no acumula en el roll-up
    # Dataview de ninguna hipótesis/concepto (típico typo: shift-vs-shape vs shift_vs_shape).
    dangling_thesis = sorted(
        (tl, f"usado en {len(refs)} paper(s): {', '.join(sorted(refs)[:3])}"
             + (" …" if len(refs) > 3 else ""))
        for tl, refs in thesis_refs.items() if tl not in names)

    # planets[].disputes[].ref sin paper destino: el bibcode discrepante no existe como nota →
    # la disputa no es trazable (typo en el bibcode o paper sin ingestar).
    dangling_disputes = sorted(
        (f"{star}", f"planeta {l}: ref `{ref}` sin nota de paper")
        for star, l, ref in dispute_refs if ref not in names or "paper" not in kinds.get(ref, []))

    # áreas de concepts/ no declaradas en concept_areas (objective.yaml) → posible typo / carpeta
    # fantasma: un `area` mal tipeado en topics.yaml crea carpeta en silencio (ver make_notes). WARN
    # blando (un typo y un área nueva legítima se ven igual → no se bloquea, se marca para revisar).
    declared_areas = set(cfg.load_concept_areas())
    undeclared_areas = []
    if cfg.CONCEPTS.exists():
        for d in sorted(cfg.CONCEPTS.iterdir()):
            if d.is_dir() and d.name not in declared_areas:
                n = len(list(d.glob("*.md")))
                undeclared_areas.append(
                    (f"concepts/{d.name}/",
                     f"área fuera de concept_areas; {n} nota(s) — ¿typo o área nueva sin declarar?"))

    # reporte
    lines = [f"# Lint de la bóveda — {dt.date.today().isoformat()}", ""]
    for title, items in [("Wikilinks rotos (página faltante)", broken),
                         ("Notas huérfanas (sin links entrantes)", [(o, "") for o in orphans]),
                         ("Contradicciones ground-truth ↔ ficha", contradictions),
                         ("Ground-truth: masa inconsistente con m·sini (K,P,e,M*)", mass_issues),
                         ("thesis_links sin página destino", dangling_thesis),
                         ("disputes[].ref sin paper destino", dangling_disputes),
                         ("⛔ Fuga de implementación (código no bibliográfico) → frontera dura (WARN, revisar a mano)", impl_leaks),
                         ("Áreas de concepts/ no declaradas en objective.yaml (WARN, posible typo)", undeclared_areas),
                         ("PDF ↔ disco (WARN — higiene: frontmatter `pdf` vs PDF bajado)", pdf_issues),
                         ("Citas no verificables en query/concepto/hipótesis (sin fulltext)", unverifiable),
                         ("Cobertura: concepto/hipótesis sin citas [[bibcode]] (backlog)", coverage),
                         ("Campos incompletos", incomplete)]:
        lines.append(f"## {title} ({len(items)})")
        for a, b in items:
            lines.append(f"- {a}" + (f" → {b}" if b else ""))
        lines.append("")
    report = "\n".join(lines)

    outdir = cfg.ROOT / "outputs"
    outdir.mkdir(exist_ok=True)
    out = outdir / f"lint-{dt.date.today().isoformat()}.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
