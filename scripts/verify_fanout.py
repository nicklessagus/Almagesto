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
  · `<out>/_esperado.json` — `{nota, fuentes: {bibcode: n}, pares: N}`. The barrier reads it,
    refuses an `--esperados` that contradicts it, and names the source that is missing.

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


def write_round(nota: Path, out_dir: Path) -> dict:
    """Write the prompts and the manifest for one round. Returns the manifest."""
    text = nota.read_text(encoding="utf-8")
    grupos = by_source(lb.pairs_of(text))
    (out_dir / "prompts").mkdir(parents=True, exist_ok=True)
    for bib, pares in grupos.items():
        (out_dir / "prompts" / f"{bib}.md").write_text(prompt_for(nota, bib, pares, out_dir),
                                                       encoding="utf-8")
    manifest = {"nota": nota.as_posix(),
                "fuentes": {bib: len(pares) for bib, pares in grupos.items()},
                "pares": sum(len(pares) for pares in grupos.values()),
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
    args = ap.parse_args(argv)
    nota = Path(args.nota)
    if not nota.is_file():
        cfg.print_seguro(f"⛔ no existe: {nota}")
        return 2
    m = write_round(nota, Path(args.out))
    if not m["pares"]:
        cfg.print_seguro(f"⚠ {nota.name}: 0 pares (afirmación, [[bibcode]]) — no hay nada que verificar, "
                         f"y un fan-out de cero no es un cierre en verde (D-43)")
        return 1
    cfg.print_seguro(f"TOTAL {m['pares']} pares en {len(m['fuentes'])} fuentes → "
                     f"{args.out}/prompts/<bibcode>.md · manifiesto: {args.out}/{MANIFEST}")
    for bib, n in m["fuentes"].items():
        cfg.print_seguro(f"  {bib}: {n}")
    cfg.print_seguro(f"Lanzá UN subagente `general-purpose` por fuente, en paralelo, con su prompt. "
                     f"Después: python scripts/check_verify_fanout.py {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
