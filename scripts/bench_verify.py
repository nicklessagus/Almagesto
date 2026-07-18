"""Auto-benchmark del verificador de citas (CiteAudit-style): siembra citas falsas y puntúa.

Uso:
    python bench_verify.py seed [--max N]     # arma build/verify_bench/bench.json
    python bench_verify.py score              # puntúa los veredictos → outputs/verify-bench-<fecha>.md

`verify-citations` es juicio de LLM ("robusto pero no prueba"). Este benchmark le pone un número:
`seed` toma pares (afirmación, [[bibcode]]) REALES de las notas verificables de la bóveda
(queries/concepts) y siembra, por cada uno, un par FALSO por construcción — la misma afirmación
atribuida a OTRO bibcode del corpus (rotación determinista sobre los bibcodes con fulltext, nunca
el original). El skill (modo benchmark) verifica todos los pares A CIEGAS —cada subagente recibe
sólo (afirmación, ruta al fulltext), nunca este archivo ni las etiquetas— y llena `verdict` en el
JSON; `score` compara veredictos vs etiquetas:

  - sembradas: el verificador debería decir `no-soportada`/`contradice` → **recall** (cuántas cazó).
  - reales (grupo de control): deberían salir `soportada`/`parcial`; una real "caída" es o un flaky
    del verificador o un error de grounding genuino de la nota — ambos valen revisarse.

Caveat de la siembra por rotación: una sembrada puede tener **soporte casual** (el otro paper dice
lo mismo de verdad) — una "pasada" se revisa a mano antes de culpar al verificador. Todo vive en
`build/` y `outputs/` (scratch gitignored): **nada del benchmark toca `vault/`** (regla #0 — las
citas falsas no son bibliografía). Determinista: mismo corpus → mismo bench.json byte a byte.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import re
import sys
from pathlib import Path

import lib_config as cfg

BIBCODE_RE = re.compile(r"^\d{4}[A-Za-z]")           # misma heurística que lint/fetch_web
LINK_RE = re.compile(r"\[\[([^\]\|#]+)")
VERIFY_HEADER = "## Verificación de citas"
MIN_CLAIM_CHARS = 15                                  # un link pelado no es una afirmación
DEFAULT_MAX = 20                                      # cota de pares reales (costo LLM acotado)


def bench_path():
    """Ruta del benchmark (en llamada, no en import: respeta un cfg.ROOT re-apuntado)."""
    return cfg.ROOT / "build" / "verify_bench" / "bench.json"

CATCH = ("no-soportada", "contradice")                # veredictos que CAZAN una sembrada
PASS = ("soportada", "parcial")
VALID_VERDICTS = CATCH + PASS + ("no verificable por extracción",)


def fulltext_map() -> dict[str, str]:
    """bibcode → ruta del .txt, para todo el corpus (bajo cualquier slug/tema)."""
    out: dict[str, str] = {}
    for p in sorted(glob.glob(str(cfg.FULLTEXT / "**" / "*.txt"), recursive=True)):
        out.setdefault(Path(p).stem, p)      # separador nativo del OS: no splitear "/" a mano
    return out


def claim_lines(text: str) -> list[tuple[int, str]]:
    """(nº de línea, línea) del CUERPO con potencial de afirmación: fuera del frontmatter,
    antes del bloque de verificación (son registros de auditoría, no claims), sin blockquotes
    (disclaimers meta) ni code fences (Dataview)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        body = parts[-1]
        offset = ("---".join(parts[:-1]) + "---").count("\n")   # líneas que consume el frontmatter
    else:
        body, offset = text, 0
    out, fenced = [], False
    for i, line in enumerate(body.split("\n"), 1 + offset):
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or line.lstrip().startswith(">") or line.lstrip().startswith("#"):
            continue
        out.append((i, line))
    return out


def extract_pairs(max_pairs: int) -> list[dict]:
    """Pares (afirmación, bibcode-con-fulltext) reales de las notas verificables, deterministas
    (orden por nota y línea; cap en max_pairs)."""
    ft = fulltext_map()
    files = sorted(glob.glob(str(cfg.QUERIES / "**" / "*.md"), recursive=True)
                   + glob.glob(str(cfg.CONCEPTS / "**" / "*.md"), recursive=True))
    pairs, seen = [], set()
    for f in files:
        text = open(f, encoding="utf-8").read()
        cut = text.find(VERIFY_HEADER)
        if cut >= 0:
            text = text[:cut]
        stem = Path(f).stem
        for lineno, line in claim_lines(text):
            bibs = [t.strip() for t in LINK_RE.findall(line) if BIBCODE_RE.match(t.strip())]
            if not bibs:
                continue
            claim = line.strip().lstrip("-* ").strip()
            if len(LINK_RE.sub("", claim).replace("]]", "")) < MIN_CLAIM_CHARS:
                continue                              # link pelado, no afirma nada
            for bib in bibs:
                if bib not in ft or (stem, claim, bib) in seen:
                    continue
                seen.add((stem, claim, bib))
                pairs.append({"note": stem, "line": lineno, "claim": claim,
                              "bibcode": bib, "fulltext": ft[bib]})
    return pairs[:max_pairs]


def seed_pairs(real: list[dict], ft: dict[str, str]) -> list[dict]:
    """Un par FALSO por cada real: misma afirmación, bibcode ROTADO (determinista, nunca el
    original) sobre los bibcodes citados en la selección. La rotación excluye TODOS los
    bibcodes que esa misma afirmación cita (una afirmación con [[A]] y [[B]] no puede
    sembrarse con B: sería un falso-falso — la fuente sí la respalda). Si una afirmación
    cita todo el pool, se saltea (no hay cruce falso posible para ella)."""
    bibs = sorted({p["bibcode"] for p in real})
    if len(bibs) < 2:
        raise SystemExit("hacen falta ≥2 bibcodes distintos con fulltext para sembrar cruces — "
                         "la bóveda no tiene todavía material para el benchmark.")
    cited: dict[tuple, set] = {}
    for p in real:
        cited.setdefault((p["note"], p["line"]), set()).add(p["bibcode"])
    out = []
    for p in real:
        own = cited[(p["note"], p["line"])]
        start = bibs.index(p["bibcode"])
        swapped = next((bibs[(start + k) % len(bibs)] for k in range(1, len(bibs))
                        if bibs[(start + k) % len(bibs)] not in own), None)
        if swapped is None:
            continue
        out.append({**p, "bibcode": swapped, "fulltext": ft[swapped]})
    return out


def cmd_seed(max_pairs: int) -> int:
    real = extract_pairs(max_pairs)
    if not real:
        raise SystemExit("no hay pares (afirmación, [[bibcode]] con fulltext) en queries/concepts — "
                         "el benchmark necesita una bóveda ya poblada y citada.")
    seeded = seed_pairs(real, fulltext_map())
    if not seeded:
        raise SystemExit("ninguna afirmación admite un cruce falso (todas citan todos los bibcodes "
                         "del pool) — ampliá --max o esperá a que la bóveda tenga más notas citadas.")
    pairs = ([{**p, "id": f"r{i:03d}", "label": "real"} for i, p in enumerate(real)]
             + [{**p, "id": f"s{i:03d}", "label": "sembrada"} for i, p in enumerate(seeded)])
    # orden mezclado pero determinista (hash del contenido): el orden no telegrafía la etiqueta.
    pairs.sort(key=lambda p: hashlib.sha1(f"{p['id']}|{p['claim']}".encode()).hexdigest())
    for p in pairs:
        p["verdict"] = None
    bench = bench_path()
    bench.parent.mkdir(parents=True, exist_ok=True)
    bench.write_text(json.dumps({"n_real": len(real), "n_seeded": len(seeded), "pairs": pairs},
                                indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(real)} pares reales + {len(seeded)} sembrados → {bench}")
    print("Siguiente (skill verify-citations, modo benchmark): verificar cada par A CIEGAS "
          "(el subagente recibe SOLO afirmación + ruta al fulltext, nunca este JSON), llenar "
          "`verdict` y correr `bench_verify.py score`.")
    return 0


def cmd_score() -> int:
    bench = bench_path()
    if not bench.exists():
        raise SystemExit(f"no existe {bench} — corré primero `bench_verify.py seed`.")
    pairs = json.loads(bench.read_text(encoding="utf-8"))["pairs"]
    missing = [p["id"] for p in pairs if p.get("verdict") not in VALID_VERDICTS]
    if missing:
        print(f"✗ {len(missing)} par(es) sin veredicto válido ({', '.join(missing[:8])}"
              + (" …" if len(missing) > 8 else "") + f") — veredictos: {', '.join(VALID_VERDICTS)}")
        return 1
    sown = [p for p in pairs if p["label"] == "sembrada"]
    real = [p for p in pairs if p["label"] == "real"]
    caught = [p for p in sown if p["verdict"] in CATCH]
    slipped = [p for p in sown if p["verdict"] in PASS]
    suspect = [p for p in real if p["verdict"] in CATCH]
    lines = [f"# Benchmark del verificador de citas — {dt.date.today().isoformat()}", "",
             f"{len(pairs)} pares ({len(real)} reales de control + {len(sown)} sembrados falsos).", "",
             f"## Sembradas cazadas (recall): {len(caught)}/{len(sown)}"
             f" ({len(caught) / len(sown):.0%})" if sown else "## Sin sembradas", ""]
    if slipped:
        lines += ["**Sembradas que PASARON** (¿soporte casual del otro paper, o miss del "
                  "verificador? revisar a mano antes de culpar al verificador):"]
        lines += [f"- {p['id']} {p['note']}:L{p['line']} → [[{p['bibcode']}]] dio {p['verdict']}"
                  for p in slipped]
        lines += [""]
    lines += [f"## Reales consistentes: {len(real) - len(suspect)}/{len(real)}", ""]
    if suspect:
        lines += ["**Reales caídas** (flaky del verificador O error de grounding real de la nota "
                  "— ambos valen revisarse):"]
        lines += [f"- {p['id']} {p['note']}:L{p['line']} → [[{p['bibcode']}]] dio {p['verdict']}"
                  for p in suspect]
        lines += [""]
    lines += ["> Juicio de LLM, no prueba: el recall calibra cuánto confiar en verify-citations.",
              "> Nada de este benchmark entra al vault (build/ y outputs/ son scratch)."]
    report = "\n".join(lines)
    outdir = cfg.ROOT / "outputs"
    outdir.mkdir(exist_ok=True)
    out = outdir / f"verify-bench-{dt.date.today().isoformat()}.md"
    out.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\n→ {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_seed = sub.add_parser("seed", help="armar el benchmark (pares reales + sembrados)")
    p_seed.add_argument("--max", type=int, default=DEFAULT_MAX,
                        help=f"máximo de pares reales (default {DEFAULT_MAX}; acota el costo LLM)")
    sub.add_parser("score", help="puntuar los veredictos del bench.json")
    args = ap.parse_args()
    return cmd_seed(args.max) if args.cmd == "seed" else cmd_score()


if __name__ == "__main__":
    sys.exit(main())
