"""Generate the per-source prompts of the `verify-citations` fan-out, and the MANIFEST (#369).

    python scripts/verify_fanout.py <nota.md> --out build/<slug>/verif/<ronda>

WHY IT EXISTS. The barrier of #259 (`check_verify_fanout.py --esperados N`) works — and its most
important parameter came from the operator reading the generator's output and transcribing it. In
a real round: the ad-hoc generator printed «TOTAL 60 en 16 fuentes», the operator launched **15**
subagents and passed `--esperados 60`. The barrier caught it («faltan 1»); finding out **which**
source was missing took a script written on the spot, because nothing had recorded the plan. And
the symmetric failure is silent: an `--esperados` miscounted in the same direction as the missing
source passes a ✅ over an incomplete fan-out, and the block gets written anyway.

The generator was the only link of the verify chain with no tool: prose in the skill, code written
by the agent each time (the same argument #314 made for the contrast step). So it moves here, and
it WRITES what it knows:

  · one prompt per source under `<out>/prompts/<bibcode>.md`, with that source's pairs, the fence
    of `lib_blocks.verify_fanout_json_block()` and the output path it must write;
  · `<out>/_esperado.json` — `{nota, fuentes: {bibcode: n}, pares: N, anclas, alcance,
    nota_total}`. The barrier reads it, refuses an `--esperados` that contradicts it, names the
    source that is missing, and crosses each source's returned anchors against `anclas` (AUD-494).

⛔ A round can be SCOPED (#407): `--fuentes b1,b2` or `--solo-nuevos`. #282 prescribes exactly
that —re-verify the pairs whose claim changed, re-anchor the rest— and `reverify_subset` emits the
partition, but the generator only knew full rounds, so the scoped one could not pass the barrier
(«faltan 114») and the three ways out were all bad: pay the full round, skip the barrier, or edit
the manifest by hand. The scope now travels IN the manifest (`alcance: {modo, fuentes}`) next to
the note's total, so the barrier can say «32 de 32 en el alcance; 114 fuera, re-anclados» instead
of «faltan 114» — declared, not indistinguishable from a fan-out that died halfway (D-43).

⛔ It does not launch anything and does not touch `vault/`: the fan-out is the operator's (one
`general-purpose` subagent per source, in parallel, #100/#219). The prompt points the subagent at
the judge's rules (`reference/juez.md`) — a rule that lives only in prose falls off in the fan-out.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_blocks as lb   # noqa: E402
import lib_config as cfg  # noqa: E402

MANIFEST = "_esperado.json"
JUEZ = ".claude/skills/verify-citations/reference/juez.md"


def by_source(pairs: list) -> dict:
    """Group pairs by bibcode, preserving first-seen order — one subagent per source (#100)."""
    out: dict = {}
    for p in pairs:
        out.setdefault(p.bibcode, []).append(p)
    return out


def prompt_for(nota: Path, bibcode: str, pares: list, out_dir: Path) -> str:
    """The prompt of ONE verifier: its pairs, the fence, the output path, and where the rules are."""
    partes = [f"# Verificación de citas — fuente `{bibcode}` · nota `{nota.name}`", "",
              f"Antes de juzgar, leé las reglas del juez en `{JUEZ}`: la fuente, el veredicto y su "
              f"evidencia, la condición y su clase, la completitud y los claims multi-cláusula. Leés SÓLO esta fuente, del PDF "
              f"(`vault/raw/pdfs/**/{bibcode}.pdf`); el `.txt` sirve para ubicar con `grep`, no para "
              f"citar.", "",
              f"Pares a juzgar: {len(pares)}. Cada uno vuelve con su `ancla` tal cual.", ""]
    for i, p in enumerate(pares, 1):
        partes += [f"### Par {i} · ancla `{p.anchor}`", "", p.block.text.strip(), ""]
    partes += ["## Salida", "",
               f"Escribí el resultado en `{(out_dir / f'{bibcode}.json').as_posix()}` con "
               f"EXACTAMENTE esta forma:", "", lb.verify_fanout_json_block(bibcode), ""]
    return "\n".join(partes)


class ScopeError(Exception):
    """The requested scope does not fit the note: the message names what."""


def scoped_sources(nota: Path, text: str, grupos: dict, fuentes: list | None,
                   solo_nuevos: bool) -> tuple[str, dict]:
    """`(modo, {bibcode: [pares]})` — which sources this round judges (#407).

    `completa` is every source; `fuentes` is the explicit list, refused if it names a source the
    note does not cite; `solo-nuevos` is the partition `reverify_subset` prescribes (#282/#257):
    the pairs with NO row to carry — the claim changed, or it is new — grouped by source. A note
    with no evaluable block sends every pair there (D-43: that is not «nothing to re-verify»), so
    `solo-nuevos` on such a note equals a full round, and the manifest says which mode asked for it.
    """
    if fuentes:
        desconocidas = sorted(set(fuentes) - set(grupos))
        if desconocidas:
            raise ScopeError(f"`--fuentes` nombra fuente(s) que la nota no cita: "
                             f"{', '.join(desconocidas)}")
        return "fuentes", {b: grupos[b] for b in grupos if b in set(fuentes)}
    if solo_nuevos:
        import reverify_subset
        r = reverify_subset.classify(nota, text, umbral=0.60)
        return "solo-nuevos", by_source(r["sin_fila"])
    return "completa", grupos


def write_round(nota: Path, out_dir: Path, fuentes: list | None = None,
                solo_nuevos: bool = False) -> dict:
    """Write the prompts and the manifest for one round. Returns the manifest.

    `fuentes` / `pares` are what the barrier COUNTS — the scope; `alcance` says how the scope was
    chosen and `nota_total` what the note holds, so a scoped round reads as scoped, never as a
    full round that came back short (#407)."""
    text = nota.read_text(encoding="utf-8")
    todos = by_source(lb.pairs_of(text))
    modo, grupos = scoped_sources(nota, text, todos, fuentes, solo_nuevos)
    (out_dir / "prompts").mkdir(parents=True, exist_ok=True)
    for bib, pares in grupos.items():
        (out_dir / "prompts" / f"{bib}.md").write_text(prompt_for(nota, bib, pares, out_dir),
                                                       encoding="utf-8")
    # @inv INV-161
    manifest = {"nota": nota.as_posix(),
                "fuentes": {bib: len(pares) for bib, pares in grupos.items()},
                "pares": sum(len(pares) for pares in grupos.values()),
                # AUD-494 — las anclas que se mandaron: la barrera cruza lo devuelto contra esto
                "anclas": {bib: [p.anchor for p in pares] for bib, pares in grupos.items()},
                "alcance": {"modo": modo, "fuentes": sorted(grupos)},
                "nota_total": {"pares": sum(len(p) for p in todos.values()),
                               "fuentes": len(todos)},
                "version": cfg.ALMAGESTO_VERSION}
    (out_dir / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    return manifest


CLASS_PROMPT = "_clase.md"
CLASS_OUT = "_clase.json"


def class_items(nota: Path, text: str) -> tuple[list, int]:
    """`([(address, claim block, condition prose)], n_without_block)` for every `contextualiza` in
    force in the note's sidecar (#580).

    Only the claim and the condition travel: no verdict, no evidence and no class, because the
    second opinion exists to apply the #221 test WITHOUT the first judge's call in view. A row whose
    pair is no longer in the body cannot be shown its claim; it is counted, not dropped in silence
    (D-43) — the lint already reports it as stale."""
    bloques = {(p.bibcode, p.anchor): p.block.text.strip() for p in lb.pairs_of(text)}
    items, sin_bloque = [], 0
    for r in lb.verif_rows(nota) or []:
        if lb.condition_kind(r.condition) != "contextualiza":
            continue
        bloque = bloques.get((r.bibcode, r.anchor))
        if bloque is None:
            sin_bloque += 1
            continue
        items.append((":".join(lb.row_key(r)), bloque, lb.condition_text(r.condition)))
    return items, sin_bloque


def class_prompt(nota: Path, items: list, out_dir: Path) -> str:
    """The prompt of the class's second opinion (#580): the #221 test, the items, the output."""
    partes = [f"# Segunda opinión sobre la clase de la condición — nota `{nota.name}`", "",
              "Cada ítem trae una AFIRMACIÓN de la nota y una CONDICIÓN bajo la que su fuente la "
              "afirma. No leas ninguna fuente: juzgás la relación entre las dos.", "",
              "La prueba (#221): ¿la afirmación, tal como está escrita, queda FALSA o afirma DE MÁS "
              "si se saca la condición? Sí → `acota` (otro sujeto, otro régimen, otra atribución, "
              "un hedge que la afirmación pierde, un paso que describe mal). No → `contextualiza` "
              "(procedencia, instrumento, definición que no cambia lo afirmado). Leé el bloque "
              "entero: si la afirmación ya lleva la condición —o lo que la vuelve verdadera—, es "
              "`contextualiza`, porque no le falta nada. Que la condición sea útil, precise o "
              "agregue detalle no la vuelve `acota`: lo es sólo si sin ella lo escrito es falso.",
              "",
              f"Ítems: {len(items)}. Cada uno vuelve con su `direccion` tal cual.", ""]
    for i, (direccion, bloque, cond) in enumerate(items, 1):
        partes += [f"### Ítem {i} · `{direccion}`", "", "**Afirmación:**", "", bloque, "",
                   f"**Condición:** {cond}", ""]
    partes += ["## Salida", "", f"Escribí `{(out_dir / CLASS_OUT).as_posix()}` con esta forma:",
               "", "```json",
               '{"clases": [{"direccion": "<ancla>:<bibcode>", "clase": "acota | contextualiza", '
               '"motivo": "<una línea: qué parte de la afirmación cae sin la condición>"}]}',
               "```", ""]
    return "\n".join(partes)


def write_class_round(nota: Path, out_dir: Path, muestra: int | None = None) -> dict:
    """Write the class's second-opinion prompt (#580). Returns `{items, contextualiza, sin_bloque}`.

    `muestra` caps the items with a sample seeded by the note's name, so the same call reproduces
    the same sample. It proposes: the judge's `acota` answers are signed by the operator and written
    by `write_verif_sidecar.py --reclasificar`, never applied by this."""
    items, sin_bloque = class_items(nota, nota.read_text(encoding="utf-8"))
    total = len(items)
    if muestra is not None and muestra < total:
        elegidos = set(random.Random(nota.stem).sample(range(total), muestra))
        items = [it for i, it in enumerate(items) if i in elegidos]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / CLASS_PROMPT).write_text(class_prompt(nota, items, out_dir), encoding="utf-8")
    return {"items": len(items), "contextualiza": total, "sin_bloque": sin_bloque}


def _main_class(nota: Path, out: Path, muestra: int | None) -> int:
    """`--segunda-clase` (#580): rc 0 with the prompt written, 1 when there is nothing to show."""
    c = write_class_round(nota, out, muestra=muestra)
    if c["sin_bloque"]:
        cfg.print_seguro(f"⚠ {c['sin_bloque']} `contextualiza` sin su bloque en la nota (ancla "
                         f"vencida): quedan FUERA — re-anclá primero")
    if not c["items"]:
        cfg.print_seguro(f"⚠ {nota.name}: 0 `contextualiza` que mostrar — nada que contrastar, y "
                         f"no es un cierre en verde (D-43)")
        return 1
    cfg.print_seguro(f"{c['items']} de {c['contextualiza']} `contextualiza` → {out}/{CLASS_PROMPT}. "
                     f"Lanzá UN subagente con ese prompt; cada `acota` que devuelva es una "
                     f"PROPUESTA: ADJUDICALA CONTRA EL PDF antes de firmar (medido: 20 de 31 "
                     f"correctas) y, si la firmás, `python scripts/write_verif_sidecar.py {nota} "
                     f"--reclasificar <ancla>:<bibcode>`, y después se resuelve (`--resolver`)")
    return 0


def main(argv=None) -> int:
    """CLI. rc 0 with the plan written, 1 for a note with no pairs (not a green close, D-43), 2 if
    the note does not exist. Launches nothing: the fan-out is the operator's."""
    cfg.stdout_tolerante()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nota", help="ruta de la nota (p. ej. vault/wiki/concepts/methods/icasso.md)")
    ap.add_argument("--out", required=True, metavar="DIR",
                    help="directorio de la ronda (p. ej. build/<slug>/verif/r3); ahí van los prompts y "
                         "ahí escriben los subagentes")
    alcance = ap.add_mutually_exclusive_group()
    alcance.add_argument("--fuentes", default=None, metavar="B1,B2",
                         help="ronda ACOTADA a estas fuentes (#407); el alcance queda en el manifiesto")
    alcance.add_argument("--solo-nuevos", action="store_true",
                         help="ronda acotada a los pares SIN fila que llevar (la partición de #282, "
                              "vía `reverify_subset`); el resto se re-ancla")
    ap.add_argument("--segunda-clase", action="store_true", dest="clase",
                    help="#580: en vez de la ronda, el prompt de la segunda opinión sobre la clase "
                         "de cada `contextualiza` del hermano (sin veredicto ni clase a la vista)")
    ap.add_argument("--muestra", type=int, default=None, metavar="N",
                    help="con --segunda-clase: sólo N ítems, muestra reproducible por nota")
    args = ap.parse_args(argv)
    nota = Path(args.nota)
    if not nota.is_file():
        cfg.print_seguro(f"⛔ no existe: {nota}")
        return 2
    if args.muestra is not None and (not args.clase or args.muestra < 1):
        ap.error("`--muestra N` va con `--segunda-clase` y N ≥ 1")
    if args.clase:
        if args.fuentes or args.solo_nuevos:
            ap.error("`--segunda-clase` no toma alcance de ronda (`--fuentes`/`--solo-nuevos`)")
        return _main_class(nota, Path(args.out), args.muestra)
    try:
        m = write_round(nota, Path(args.out),
                        fuentes=[x.strip() for x in args.fuentes.split(",") if x.strip()]
                        if args.fuentes else None, solo_nuevos=args.solo_nuevos)
    except ScopeError as exc:
        cfg.print_seguro(f"⛔ {exc}")
        return 2
    if not m["pares"]:
        if m["alcance"]["modo"] == "solo-nuevos" and m["nota_total"]["pares"]:
            cfg.print_seguro(f"✓ {nota.name}: 0 pares sin fila que llevar sobre "
                             f"{m['nota_total']['pares']} — no hay nada que RE-verificar; el "
                             f"re-anclaje lo hace `write_verif_sidecar.py` sin fan-out")
            return 0
        cfg.print_seguro(f"⚠ {nota.name}: 0 pares (afirmación, [[bibcode]]) — no hay nada que verificar, "
                         f"y un fan-out de cero no es un cierre en verde (D-43)")
        return 1
    fuera = m["nota_total"]["pares"] - m["pares"]
    cfg.print_seguro(f"TOTAL {m['pares']} pares en {len(m['fuentes'])} fuentes → "
                     f"{args.out}/prompts/<bibcode>.md · manifiesto: {args.out}/{MANIFEST}"
                     + (f"\n  alcance `{m['alcance']['modo']}`: {fuera} par(es) de la nota quedan "
                        f"FUERA y se re-anclan al escribir el hermano (#407)" if fuera else ""))
    for bib, n in m["fuentes"].items():
        cfg.print_seguro(f"  {bib}: {n}")
    cfg.print_seguro(f"Lanzá UN subagente `general-purpose` por fuente, en paralelo, con su prompt. "
                     f"Después: python scripts/check_verify_fanout.py {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
