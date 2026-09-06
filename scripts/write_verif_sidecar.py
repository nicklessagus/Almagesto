"""Write a note's `<nota>.verif.md` sibling from a finished verify fan-out (#403).

    python scripts/write_verif_sidecar.py <nota.md> --from build/<slug>/verif/<ronda> [--fecha AAAA-MM-DD] [--dry-run]

The missing link of the `verify-citations` chain. It had a generator (`verify_fanout.py`, #369), a
barrier (`check_verify_fanout.py`, #259) and a re-anchoring proposer (`reverify_subset.py`, #257),
and the last step —the one that actually WRITES in `vault/`— was code the agent typed again on every
run. Measured closing one theme: the assembler was written four times and got wrong twice, once by
matching `bibcode` at the wrong level (57 rows verified out of 112, with 55 false «sin veredicto»),
once by hashing a PDF as text (117 pairs «vencidos por fuente» over PDFs nobody touched).

What it does, in order, and every step is a `lib_blocks` function the lint also reads:

  1. runs the BARRIER (`check_verify_fanout.check_dir`) and refuses on any error — a sidecar built
     from a fan-out that did not close is the derived work #199 forbids;
  2. matches each fan-out pair to the note's pairs by `(bibcode, ancla)` — the `bibcode` is at file
     level, the `ancla` at pair level — and REFUSES naming what does not match, instead of emitting
     a row with no verdict;
  3. hashes the file the pair was read against BY KIND: `pdf:` with `bytes_hash` (what the lint
     recomputes), `txt:` with `source_hash`, and no file at all for `no verificable por extracción`
     (#223: that verdict is the property of having no file);
  4. prefixes the condition with its class from `cond_tipo` (`acota:` / `contextualiza:`, #221);
  5. on a second round, CHAINS the verdict cell instead of overwriting (`no-soportada→corregida`,
     #232/#274c) — a chain that repeats the last verdict is not extended, which is what makes the
     second identical run a no-op;
  6. renders the table through `render_verif_table` (escaped, round-trip checked, #284), the sibling
     through `render_verif_sidecar`, and the note's header line through `verif_summary` (INV-81) with
     the three sub-sections carrying their generated count fragment (#280) and whatever free text the
     agent already wrote after the colon.

It does NOT judge: the verdicts are the fan-out's. And it does not write the three sub-sections'
free text: that is the round's triage, which only the agent that read the sources can write — the
placeholder it leaves is visible on purpose.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_config as cfg          # noqa: E402
import lib_blocks as lb           # noqa: E402
import check_verify_fanout        # noqa: E402

PENDIENTE = "⚠ triage de la corrida pendiente"
INTRO = "Chequeo afirmación↔fuente (skill `verify-citations`)."


class SidecarError(Exception):
    """The sidecar cannot be built from this fan-out: the message names why."""


def load_fanout(directory: Path) -> dict:
    """`{bibcode: [par, …]}` from a fan-out directory that PASSED the barrier.

    Raises `SidecarError` listing the barrier's findings otherwise: building the sibling from a
    fan-out that did not close is exactly the derived work #199 measured going unread."""
    _pairs, errors = check_verify_fanout.check_dir(directory)
    if errors:
        raise SidecarError("el fan-out no pasa la barrera (#259) — no se arma nada:\n  "
                           + "\n  ".join(errors))
    out: dict = {}
    for f in sorted(directory.glob("*.json")):
        if f.name == check_verify_fanout.MANIFEST:
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        out.setdefault(str(data["bibcode"]), []).extend(data["pares"])
    return out


def source_ref_for(bibcode: str, verdict: str, prefiere: str | None = None) -> str:
    """The `Hash fuente` cell for one pair: `pdf:<sha10>`, `txt:<sha10>`, or `""` (#117/#223).

    The kind is decided by what is on disk, PDF first (since #205 the PDF is what gets read); the
    hash is computed by the SAME function the lint recomputes it with, which is the whole point of
    this module existing — hashing a PDF as text produced 117 false «vencidos por fuente».
    A verdict that cannot name a file (`no verificable por extracción`) carries none.

    ⚠ With copies under several slugs this resolves the lexicographically smallest (`pdf_slug`
    with no preference) while the lint keeps the first its glob returns; they hash the same only
    because D-18 COPIES the artefact — `raw/` is immutable — and the `.txt` half of that is what
    `diverged_copies` guards. If a PDF ever diverged between slugs, `pdf_sha` (#383) is the net.

    Raises `SidecarError` when the fan-out claims to have read a source that is not on disk."""
    if lb.has_no_source_file(verdict):
        return ""
    slug_pdf = cfg.pdf_slug(bibcode, prefiere)
    if slug_pdf:
        return "pdf:" + lb.bytes_hash(cfg.PDFS / slug_pdf / f"{bibcode}.pdf")
    slug_txt = cfg.txt_slug(bibcode, prefiere)
    if slug_txt:
        return "txt:" + lb.source_hash(cfg.FULLTEXT / slug_txt / f"{bibcode}.txt")
    raise SidecarError(f"{bibcode}: el fan-out dice haber leído la fuente y no hay ni PDF ni `.txt` "
                       f"en disco — ¿se borró después de verificar? Si no hay archivo, el veredicto "
                       f"es `no verificable por extracción` (#223)")


def condition_cell(par: dict) -> str:
    """`acota: …` / `contextualiza: …` from `cond_tipo` + `condicion` (#221); `—` when none."""
    cond = str(par.get("condicion") or "").strip()
    if not cond:
        return "—"
    tipo = str(par.get("cond_tipo") or "").strip().lower()
    return f"{tipo}: {cond}" if tipo else cond


def chained_verdict(previous: str | None, new: str) -> str:
    """The verdict cell for a pair that may already have a row: annotate, never overwrite (#232).

    `no-soportada` then `corregida` → `no-soportada→corregida`; more rounds keep chaining (#274c).
    A round that repeats the LAST verdict of the chain does not extend it — that is what makes
    re-running the writer on the same fan-out a no-op, and what keeps a chain from reading as «three
    rounds fought this» when one round confirmed it three times."""
    if not previous:
        return new
    ultimo = lb._bare_verdict(previous.split("→")[-1]) if "→" in previous else lb._bare_verdict(previous)
    return previous if ultimo == lb._bare_verdict(new) else f"{previous}→{new}"


def build_rows(note: Path, text: str, fanout: dict, previous: list | None) -> list:
    """One `Row` per body pair that the fan-out judged, in body order (#403).

    Matching is by `(bibcode, ancla)`, the two keys the fan-out schema carries at file and pair
    level. A fan-out pair whose anchor is not in the body is REFUSED and named: the note changed
    after the prompts were generated, and a row with no pair behind it is exactly the orphan the
    lint reports (D-4). A body pair the fan-out did not judge is left out — the lint reports it as
    «sin verificar», which is true."""
    pares = lb.pairs_of(text)
    por_clave = {(p.bibcode, p.anchor): p for p in pares}
    previas = {(r.bibcode, r.anchor): r for r in (previous or [])}
    sobrantes = [(b, str(par.get("ancla") or "")) for b, ps in fanout.items() for par in ps
                 if (b, str(par.get("ancla") or "")) not in por_clave]
    if sobrantes:
        raise SidecarError("pares del fan-out que NO están en el cuerpo de la nota (¿se editó "
                           "después de generar los prompts?) — no se arma nada:\n  "
                           + "\n  ".join(f"{b} · ancla {a}" for b, a in sobrantes))
    juzgados = {(b, str(par.get("ancla") or "")): par for b, ps in fanout.items() for par in ps}
    rows, n = [], 0
    for p in pares:
        par = juzgados.get((p.bibcode, p.anchor))
        if par is None:
            continue
        n += 1
        veredicto = str(par["veredicto"]).strip()
        previa = previas.get((p.bibcode, p.anchor))
        celda = chained_verdict(previa.verdict if previa else None, veredicto)
        ref = source_ref_for(p.bibcode, veredicto)
        kind, h = lb.split_source_ref(ref)
        # la fila SIN archivo (#223) se escribe `—`, que es lo que el parser devuelve para esa
        # celda: con `""` el round-trip de `render_verif_table` rehúsa, y con razón
        rows.append(lb.Row(n=str(n), claim=lb.truncate_claim(lb.normalize_ws(p.block.text)),
                           bibcode=p.bibcode, verdict=celda, anchor=p.anchor, source_hash=h or "—",
                           condition=condition_cell(par), source_kind=kind,
                           evidence=str(par.get("evidencia") or "").strip()))
    return rows


def note_section(note: Path, text: str, rows: list, fecha: str) -> str:
    """The `## Verificación de citas` section the NOTE keeps: header line, pointer, sub-sections.

    The header line is GENERATED (`verif_summary`, INV-81) and the three sub-sections carry their
    generated count fragment (#280) — the free text after the colon is the agent's triage and is
    preserved when it exists; when it does not, a visible placeholder says so rather than a
    «ninguna» nobody wrote."""
    fm = cfg.frontmatter_span(text)
    prosa = cfg.solo_prosa(fm[1] if fm else text)
    frags = lb.verif_subsection_lines(rows, prosa)
    vieja = lb.verif_section(text)
    lineas = [f"{lb.VERIFY_HEADER} ({fecha})", f"{INTRO} {lb.verif_summary(rows)}", "",
              lb.verif_pointer(note), ""]
    for sub in lb.VERIF_SUBSECCIONES:
        frag = frags.get(sub)
        texto = free_text_of(vieja, sub) or PENDIENTE
        lineas.append(f"{sub} {frag}: {texto}" if frag else f"{sub}: {texto}")
        lineas.append("")
    return "\n".join(lineas).rstrip() + "\n"


def free_text_of(seccion: str, sub: str) -> str:
    """What the agent wrote after the count fragment of one sub-section, or `""` (#280).

    ⛔ The generated fragment carries colons of its own («— 0 con condición: 0 `acota` …»), so
    splitting on the FIRST `:` re-captures half the fragment and the line grows on every run —
    measured writing this: the second run appended the counts twice. The free text is what follows
    the LAST `: ` that closes the fragment, which for every sub-section is the one before the
    agent's prose; a line with no colon has no free text."""
    for ln in seccion.split("\n"):
        s = ln.strip()
        if not s.startswith(sub) or ":" not in s:
            continue
        cabeza, _, cola = s.rpartition(": ")
        # el fragmento generado termina en `sin clasificar` / `en el cuerpo`; lo que sigue al ÚLTIMO
        # `: ` es la prosa. Si la prosa misma trae `: `, `rpartition` la partiría: se reconstruye
        # buscando el cierre del fragmento conocido.
        for cierre in (" sin clasificar: ", " en el cuerpo: ", f"{sub}: "):
            if cierre in s:
                return s.split(cierre, 1)[1].strip()
        return cola.strip()
    return ""


def write(note: Path, fanout_dir: Path, fecha: str | None = None, dry_run: bool = False) -> dict:
    """Build and (unless `dry_run`) write the sibling and the note's section. Returns the counts."""
    text = note.read_text(encoding="utf-8")
    fanout = load_fanout(fanout_dir)
    previas = lb.verif_rows(note) if cfg.verif_sidecar(note).exists() else None
    rows = build_rows(note, text, fanout, previas)
    if not rows:
        raise SidecarError("el fan-out no juzgó ningún par del cuerpo: no hay tabla que escribir")
    tabla = lb.render_verif_table(rows)                       # #284: round-trip o rehúsa
    hermano = lb.render_verif_sidecar(note, tabla)
    seccion = note_section(note, text, rows, fecha or dt.date.today().isoformat())
    vieja = lb.verif_section(text)
    nuevo = text.replace(vieja, seccion, 1) if vieja else text.rstrip("\n") + "\n\n" + seccion
    if not dry_run:
        cfg.write_text_atomic(cfg.verif_sidecar(note), hermano)
        cfg.write_text_atomic(note, nuevo)
    c = lb.verif_counts(rows)
    return {"filas": len(rows), "pares_cuerpo": len(lb.pairs_of(text)),
            "encadenadas": c["cadenas"], "hermano": cfg.verif_sidecar(note).name}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("nota", help="la nota (`vault/wiki/.../<x>.md`)")
    ap.add_argument("--from", dest="fanout", required=True,
                    help="directorio de la ronda (p. ej. build/<slug>/verif/r1)")
    ap.add_argument("--fecha", default=None, help="fecha del bloque (default: hoy)")
    ap.add_argument("--dry-run", action="store_true", help="no escribe: dice qué haría")
    args = ap.parse_args(argv)
    nota, fanout = Path(args.nota), Path(args.fanout)
    if not nota.exists() or cfg.is_verif_sidecar(nota):
        cfg.print_seguro(f"⛔ {nota} no es una nota")
        return 2
    if not fanout.is_dir():
        cfg.print_seguro(f"⛔ {fanout} no es un directorio de fan-out")
        return 2
    try:
        r = write(nota, fanout, fecha=args.fecha, dry_run=args.dry_run)
    except SidecarError as exc:
        cfg.print_seguro(f"⛔ {exc}")
        return 1
    accion = "se escribiría" if args.dry_run else "escrito"
    cfg.print_seguro(f"{accion} {r['hermano']}: {r['filas']} fila(s) sobre {r['pares_cuerpo']} "
                     f"par(es) del cuerpo" + (f", {r['encadenadas']} encadenada(s)" if r["encadenadas"] else "")
                     + f" — la cabecera de la nota la da `verif_summary`; las sub-secciones que "
                       f"digan «{PENDIENTE}» son el triage de la corrida: completalas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
