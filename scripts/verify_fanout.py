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
  · `<out>/_esperado.json` — `{nota, fuentes: {bibcode: n}, pares: N, alcance, nota_total}`. The
    barrier reads it, refuses an `--esperados` that contradicts it, and names the source that is
    missing.

⛔ A round can be SCOPED (#407): `--fuentes b1,b2` or `--solo-nuevos`. #282 prescribes exactly
that —re-verify the pairs whose claim changed, re-anchor the rest— and `reverify_subset` emits the
partition, but the generator only knew full rounds, so the scoped one could not pass the barrier
(«faltan 114») and the three ways out were all bad: pay the full round, skip the barrier, or edit
the manifest by hand. The scope now travels IN the manifest (`alcance: {modo, fuentes}`) next to
the note's total, so the barrier can say «32 de 32 en el alcance; 114 fuera, re-anclados» instead
of «faltan 114» — declared, not indistinguishable from a fan-out that died halfway (D-43).

⛔ It does not launch anything and does not touch `vault/`: the fan-out is the operator's (one
`general-purpose` subagent per source, in parallel, #100/#219). The prompt points the subagent at
the skill for the judging rules — a rule that lives only in prose falls off in the fan-out.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_blocks as lb   # noqa: E402
import lib_config as cfg  # noqa: E402

MANIFEST = "_esperado.json"
SKILL = ".claude/skills/verify-citations/SKILL.md"


def by_source(pairs: list) -> dict:
    """Group pairs by bibcode, preserving first-seen order — one subagent per source (#100)."""
    out: dict = {}
    for p in pairs:
        out.setdefault(p.bibcode, []).append(p)
    return out


def prompt_for(nota: Path, bibcode: str, pares: list, out_dir: Path) -> str:
    """The prompt of ONE verifier: its pairs, the fence, the output path, and where the rules are."""
    partes = [f"# Verificación de citas — fuente `{bibcode}` · nota `{nota.name}`", "",
              f"⛔ Antes de juzgar, leé las reglas del verificador en `{SKILL}` (§2): grounding-first, "
              f"claims multi-cláusula, completitud de transcripciones. Leés SÓLO esta fuente, del PDF "
              f"(`vault/raw/pdfs/**/{bibcode}.pdf`); el `.txt` sirve para ubicar con `grep`, no para "
              f"citar.", "",
              f"Pares a juzgar: {len(pares)}. Cada uno vuelve con su `ancla` tal cual.", ""]
    for i, p in enumerate(pares, 1):
        partes += [f"### Par {i} · ancla `{p.anchor}`", "", p.block.text.strip(), ""]
    partes += ["## Salida", "",
               f"Escribí el resultado en `{(out_dir / f'{bibcode}.json').as_posix()}` con "
               f"EXACTAMENTE esta forma:", "", lb.verify_fanout_json_block(), ""]
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
    manifest = {"nota": nota.as_posix(),
                "fuentes": {bib: len(pares) for bib, pares in grupos.items()},
                "pares": sum(len(pares) for pares in grupos.values()),
                "alcance": {"modo": modo, "fuentes": sorted(grupos)},
                "nota_total": {"pares": sum(len(p) for p in todos.values()),
                               "fuentes": len(todos)},
                "version": cfg.ALMAGESTO_VERSION}
    (out_dir / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    return manifest


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
    args = ap.parse_args(argv)
    nota = Path(args.nota)
    if not nota.is_file():
        cfg.print_seguro(f"⛔ no existe: {nota}")
        return 2
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
