"""Auto-benchmark del verificador de citas (CiteAudit-style): siembra citas falsas y puntúa.

Uso:
    python scripts/bench_verify.py seed [--max N]     # arma build/verify_bench/{exam,key}.json
    python scripts/bench_verify.py score              # puntúa los veredictos → outputs/verify-bench-<fecha>.md

`verify-citations` es juicio de LLM ("robusto pero no prueba"). Este benchmark le pone un número:
`seed` toma pares (afirmación, [[bibcode]]) REALES de las notas verificables de la bóveda
(queries/concepts) y siembra, por cada uno, un par FALSO por construcción — la misma afirmación
atribuida a OTRO bibcode del corpus (rotación determinista sobre los bibcodes con fulltext, nunca
el original). El skill (modo benchmark) verifica todos los pares A CIEGAS —cada subagente recibe
sólo (afirmación, ruta al fulltext), nunca la clave— y llena `verdict` en el examen; `score` cruza
los veredictos contra la clave.

**D-55 — examen y clave son DOS archivos.** Hasta 1.32 convivían en `bench.json`: la etiqueta
(`label: real|sembrada`) y hasta el prefijo del `id` (`r###`/`s###`) viajaban al lado de la
pregunta, así que **la ceguera la sostenía una instrucción del skill, no la construcción** — una
medición del propio error que depende de que nadie mire el archivo que tiene al lado no mide nada.
Ahora `seed` escribe `exam.json` (pares con `id` neutro y **sin** etiqueta ni conteos por clase) y
`key.json` (qué id es sembrado, y la procedencia para el reporte); `score` los cruza. El skill lee
**sólo** `exam.json`.

*Residuo declarado:* cada sembrada es la afirmación de un par real con el bibcode rotado, así que
el examen contiene el mismo `claim` dos veces con bibcodes distintos. Quien lea el examen ENTERO
puede deducir que uno de esos dos es falso —no cuál—. No lo ve el juez real: el fan-out del skill
le da a cada subagente su par y nada más. Eliminarlo pediría otra siembra, no otro archivo. El claim se guarda ya **cegado** (sin `[[wikilinks]]`):
con el bibcode original inline, una sembrada se cazaría por mismatch de strings (cita ≠ archivo
recibido) sin leer el paper — el verificador debe juzgar contenido, no comparar strings.

  - sembradas: el verificador debería decir `no-soportada`/`contradice` → **recall** (cuántas cazó).
  - reales (grupo de control): deberían salir `soportada`; una real "caída" es o un flaky
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
WIKILINK_RE = re.compile(r"\[\[[^\]]*\]\]")          # wikilink completo, para CEGAR el claim
LEADIN_RE = re.compile(r"^(\*\*[^*]{2,80}?\*\*:?)\s*")           # etiqueta del bullet: **Foo:**
# marcador de lista SOLO (`- `, `* `, `1. `). Un lstrip("-* ") se comería también los `**` de una
# etiqueta en negrita (`- **Tema:**` → `Tema:**`) y el lead-in dejaría de reconocerse.
BULLET_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")
# corte de oración: punto + espacio ANTES de mayúscula/`[[`/`**`/`(`. Deja intactos los decimales
# ("1.4 m/s": sin espacio) y las abreviaturas en minúscula ("p. ej.": sigue minúscula).
SENT_SPLIT_RE = re.compile(r"(?<=\.)\s+(?=[A-ZÁÉÍÓÚÑ¿¡(\[*])")
VERIFY_HEADER = "## Verificación de citas"
MIN_CLAIM_CHARS = 15                                  # un link pelado no es una afirmación
DEFAULT_MAX = 20                                      # cota de pares reales (costo LLM acotado)


def bench_dir():
    """Directorio del benchmark (en llamada, no en import: respeta un cfg.ROOT re-apuntado)."""
    return cfg.ROOT / "build" / "verify_bench"


def exam_path():
    """El EXAMEN: lo único que ve quien juzga. Sin etiquetas, sin conteos por clase, `id` neutro."""
    return bench_dir() / "exam.json"


def key_path():
    """La CLAVE: qué id es sembrado, con la procedencia (nota, línea, bibcode) para el reporte."""
    return bench_dir() / "key.json"


def legacy_bench_path():
    """El archivo único pre-D-55. No se lee: se DETECTA y se manda a re-sembrar (el framework no
    lleva capas de compatibilidad, y un lector tolerante acá reintroduciría justo la fuga)."""
    return bench_dir() / "bench.json"

CATCH = ("no-soportada", "contradice")                # veredictos que CAZAN una sembrada
# `parcial` salió del vocabulario en 1.39.0 (ver `lib_blocks.VEREDICTOS`): fusionaba el eje textual
# con el de grado, y las tres divergencias entre dos corridas independientes del fan-out caían
# justo en ese borde. Acá el efecto es que el gate se ENDURECE: una sembrada que antes "pasaba"
# como `parcial` ahora tiene que salir `soportada` para contar como no-cazada.
PASS = ("soportada",)
VALID_VERDICTS = CATCH + PASS + ("no verificable por extracción",)


def fulltext_map() -> dict[str, str]:
    """bibcode → ruta del .txt, para todo el corpus (bajo cualquier slug/tema)."""
    out: dict[str, str] = {}
    for p in sorted(glob.glob(str(cfg.FULLTEXT / "**" / "*.txt"), recursive=True)):
        out.setdefault(Path(p).stem, p)      # separador nativo del OS: no splitear "/" a mano
    return out


def claim_blocks(text: str) -> list[tuple[int, str]]:
    """(nº de línea inicial, bloque) del CUERPO con potencial de afirmación: fuera del
    frontmatter, antes del bloque de verificación (son registros de auditoría, no claims),
    sin blockquotes (disclaimers meta) ni code fences (Dataview).

    Issue #19: la unidad es el **bloque lógico** —bullet con sus líneas de continuación
    hard-wrapped unidas, o párrafo—, no la línea física: un claim-fragmento truncado a mitad
    de oración mezcla cláusulas de citas vecinas (falsas alarmas sobre pares reales) y queda
    tan genérico que cualquier paper del tema lo "respalda" (sembradas fáciles). Las filas
    de tabla siguen siendo un claim por fila (afirmaciones atómicas por diseño del schema)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        body = parts[-1]
        offset = ("---".join(parts[:-1]) + "---").count("\n")   # líneas que consume el frontmatter
    else:
        body, offset = text, 0
    out: list[tuple[int, str]] = []
    cur: list[str] = []
    cur_line = 0
    fenced = False

    def flush():
        nonlocal cur
        if cur:
            out.append((cur_line, " ".join(cur)))
        cur = []

    for i, line in enumerate(body.split("\n"), 1 + offset):
        s = line.strip()
        if s.startswith("```"):
            fenced = not fenced
            flush()
            continue
        if fenced or s.startswith(">") or s.startswith("#") or not s:
            flush()                                   # separador: cierra el bloque en curso
            continue
        if s.startswith("|"):                         # fila de tabla: claim atómico propio
            flush()
            out.append((i, s))
            continue
        if s.startswith(("- ", "* ")) or re.match(r"\d+\.\s", s):
            flush()                                   # bullet nuevo: abre bloque
            cur, cur_line = [s], i
        elif cur:
            cur.append(s)                             # continuación hard-wrapped: se une
        else:
            cur, cur_line = [s], i                    # arranque de párrafo
    flush()
    return out


def blind(text: str) -> str:
    """Claim CIEGO: sin wikilinks, espacios colapsados (issue #18). Con el `[[bibcode]]` original
    inline, una sembrada se caza por mismatch de strings (cita ≠ archivo recibido) sin leer el
    paper — y una real se aprueba por la coincidencia. El verificador debe juzgar contenido."""
    return re.sub(r"\s+", " ", WIKILINK_RE.sub("", text)).strip(" :;,–—")


def claim_for_bibcode(block: str, bib: str) -> str:
    """Recorta el bloque a la cláusula que porta ESA cita, con la etiqueta del bullet de sujeto.

    Issue #22: un bloque suele ser multi-cláusula (etiqueta de encuadre sin cita + la cláusula
    atribuida + cláusulas de OTRAS citas). Sembrado entero, el paper rotado respalda con razón
    alguna de esas otras cláusulas y la sembrada "pasa" como soportada sin que nadie se
    equivoque. La etiqueta (`**...:**`) se antepone porque sin ella la cláusula pierde el sujeto
    ("la trata como limitante de precisión RV" ← ¿qué?). Fallback al bloque completo si no hay
    corte posible."""
    m = LEADIN_RE.match(block)
    leadin, rest = (m.group(1), block[m.end():]) if m else ("", block)
    segs = SENT_SPLIT_RE.split(rest)
    own = [s for s in segs if f"[[{bib}" in s]
    if len(segs) < 2 or not own:
        return block
    return " ".join([leadin, *own]).strip() if leadin else " ".join(own).strip()


def extract_pairs(max_pairs: int) -> list[dict]:
    """Pares (afirmación, bibcode-con-fulltext) reales de las notas verificables, deterministas
    (orden por nota y bloque; cap en max_pairs)."""
    ft = fulltext_map()
    files = sorted(glob.glob(str(cfg.QUERIES / "**" / "*.md"), recursive=True)
                   + glob.glob(str(cfg.CONCEPTS / "**" / "*.md"), recursive=True))
    pairs, seen = [], set()
    for f in files:
        text = open(f, encoding="utf-8").read()
        cut = cfg.section_start(text, VERIFY_HEADER)
        if cut >= 0:
            text = text[:cut]
        stem = Path(f).stem
        for lineno, line in claim_blocks(text):
            bibs = [t.strip() for t in LINK_RE.findall(line) if BIBCODE_RE.match(t.strip())]
            if not bibs:
                continue
            raw = BULLET_RE.sub("", line.strip()).strip()
            if len(LINK_RE.sub("", raw).replace("]]", "")) < MIN_CLAIM_CHARS:
                continue                              # link pelado, no afirma nada
            for bib in bibs:
                claim = blind(claim_for_bibcode(raw, bib))
                if len(claim) < MIN_CLAIM_CHARS:      # recorte demasiado magro → bloque entero
                    claim = blind(raw)
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
    cita todo el pool, se saltea (no hay cruce falso posible para ella). El recorte por cláusula
    (#22) NO relaja esta veda: aunque el claim ya sea sólo la cláusula de A, sembrarla con la B
    del mismo bloque es el cruce con mayor chance de soporte casual (misma frase, mismo tema) —
    se prefiere sembrar menos y más limpio.

    Issue #20 — preferencia CROSS-NOTA: el destino del cruce se busca primero entre los
    bibcodes que la nota de origen NO cita en ningún bloque (si la nota no lo cita, su autor
    no lo consideró material del tema → mucha menos chance de que "casualmente" respalde la
    afirmación; en el run real, sembrar dentro del corpus de la misma nota dio 25% de falsas
    que el otro paper sí respaldaba). Fallback si la nota cita todo el pool: excluir sólo el
    bloque (comportamiento histórico). Pool y protecciones se computan sobre la selección
    (post-cap), igual que siempre — determinista."""
    # @inv INV-74
    bibs = sorted({p["bibcode"] for p in real})
    if len(bibs) < 2:
        raise SystemExit("hacen falta ≥2 bibcodes distintos con fulltext para sembrar cruces — "
                         "la bóveda no tiene todavía material para el benchmark.")
    cited: dict[tuple, set] = {}
    note_cited: dict[str, set] = {}
    for p in real:
        cited.setdefault((p["note"], p["line"]), set()).add(p["bibcode"])
        note_cited.setdefault(p["note"], set()).add(p["bibcode"])
    out = []
    for p in real:
        own = cited[(p["note"], p["line"])]
        start = bibs.index(p["bibcode"])
        ring = [bibs[(start + k) % len(bibs)] for k in range(1, len(bibs))]
        swapped = next((b for b in ring if b not in note_cited[p["note"]]),   # cross-nota
                       next((b for b in ring if b not in own), None))         # fallback: bloque
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
    pairs = ([{**p, "_seed": f"r{i:03d}", "label": "real"} for i, p in enumerate(real)]
             + [{**p, "_seed": f"s{i:03d}", "label": "sembrada"} for i, p in enumerate(seeded)])
    # orden mezclado pero determinista (hash del contenido): el orden no telegrafía la etiqueta.
    # `_seed` es la clave de ORDENAMIENTO, interna a esta función: no sale a ningún archivo. El `id`
    # público se asigna DESPUÉS del sort y por posición, así que no codifica la clase (el prefijo
    # `r`/`s` del schema viejo la entregaba en el nombre mismo del par).
    pairs.sort(key=lambda p: hashlib.sha1(f"{p['_seed']}|{p['claim']}".encode()).hexdigest())
    for i, p in enumerate(pairs):
        p["id"] = f"p{i:03d}"
    bench_dir().mkdir(parents=True, exist_ok=True)
    # EXAMEN: sólo lo que hace falta para juzgar. Ni `label`, ni `_seed`, ni `n_real`/`n_seeded`
    # (dos conteos por clase también son clave: con 20 pares y "n_seeded: 8" el que mira ya sabe
    # cuántas buscar). `note`/`line` se quedan porque son la trazabilidad que el humano necesita
    # para revisar una caída, y no dicen de qué lado está el par.
    exam = {"n_pairs": len(pairs),
            "pairs": [{"id": p["id"], "claim": p["claim"], "bibcode": p["bibcode"],
                       "fulltext": p["fulltext"], "note": p["note"], "line": p["line"],
                       "verdict": None} for p in pairs]}
    clave = {"n_real": len(real), "n_seeded": len(seeded),
             "key": {p["id"]: p["label"] for p in pairs}}
    cfg.write_text_atomic(exam_path(), json.dumps(exam, indent=2, ensure_ascii=False))
    cfg.write_text_atomic(key_path(), json.dumps(clave, indent=2, ensure_ascii=False))
    # Un `bench.json` de una corrida pre-D-55 quedaría al lado del examen nuevo, con las etiquetas
    # adentro: dejarlo sería reponer la fuga que esta partición cierra.
    legacy_bench_path().unlink(missing_ok=True)
    print(f"{len(real)} pares reales + {len(seeded)} sembrados → {exam_path()}")
    print(f"clave (NO abrirla para juzgar) → {key_path()}")
    print("Siguiente (skill verify-citations, modo benchmark): verificar cada par A CIEGAS "
          "(el subagente recibe SOLO afirmación + ruta al fulltext), llenar `verdict` en "
          "exam.json y correr `bench_verify.py score`.")
    return 0


def cmd_score() -> int:
    exam, key = exam_path(), key_path()
    if not exam.exists():
    #  @inv INV-75
        if legacy_bench_path().exists():
            raise SystemExit(
                f"{legacy_bench_path()} es el archivo único pre-D-55 (examen y clave juntos): el "
                f"lector ya no lo mira. Re-sembrá con `bench_verify.py seed` — los veredictos que "
                f"tenga adentro se pierden, que es más barato que puntuar una corrida cuya ceguera "
                f"no está garantizada.")
        raise SystemExit(f"no existe {exam} — corré primero `bench_verify.py seed`.")
    if not key.exists():
        raise SystemExit(f"no existe {key} — el examen no se puede puntuar sin su clave; "
                         f"re-sembrá con `bench_verify.py seed`.")
    pairs = json.loads(exam.read_text(encoding="utf-8"))["pairs"]
    etiquetas = json.loads(key.read_text(encoding="utf-8"))["key"]
    huerfanos = [p["id"] for p in pairs if p["id"] not in etiquetas]
    if huerfanos:
        raise SystemExit(f"{len(huerfanos)} par(es) del examen no están en la clave "
                         f"({', '.join(huerfanos[:5])}) — examen y clave son de corridas distintas; "
                         f"re-sembrá con `bench_verify.py seed`.")
    for p in pairs:
        p["label"] = etiquetas[p["id"]]
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
    out.write_text(report + "\n", encoding="utf-8")  # noqa: vault-write — destino `outputs/`, scratch regenerable (#137)
    print(report)
    print(f"\n→ {out}")
    return 0


def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
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
