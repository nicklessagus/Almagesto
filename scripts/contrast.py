#!/usr/bin/env python3
"""The reader of extractions for step 3b/3c — the cross-paper contrast (#314/#317).

WHY IT EXISTS, measured. The chain has a tool at every link **except one**: `extraction_prompt.py`
produces (INV-100: the prompt is GENERATED, never written from memory), `harvest_views.py` harvests
(INV-103), the `verify-citations` fan-out verifies. In between sits the step `CLAUDE.md` calls *"the
one with the most leverage and the easiest to skip"*, and doing it means reading N extractions of
~25 KB each and comparing them field by field. With no tool the natural move is a throwaway
`python -c` printing a trimmed digest — **and that is where the defect is**: the cut lands inside
the quoted text and the model completes it with something plausible.

Measured on a real theme (32 papers, 139 pairs): **2 fabricated quotes**, both at the exact
character where the digest cut, and one of them inverting the scope of the claim (*«significantly
more complicated **even in the absence of noise**»* became *«significantly harder»*). The
extraction JSON had the full sentence; the paper note had it right; the defect lived **only** in the
concept note — the single step with no tool. The control: a note written paper by paper, 11 rows,
35 quotes re-verified against the PDF, **0 real defects**.

Three guarantees, each closing one of the measured failure modes:

  1. **A quote is never truncated.** If output must be shortened it goes through
     `lib_blocks.truncate_claim` —which already retreats out of `$…$`, backticks and `[[ ]]`— and
     the cut is MARKED. Default is `--completo`: when the material does not fit, the remedy is to
     filter fewer rows, never to cut more text (#226's doctrine, one step earlier).
  2. **Provenance travels**: `linea` (the locator) and `segunda_mano` ride with every value. The six
     false attributions of that run came from a digest that dropped them.
  3. **One row, one source.** The row skeleton it prints carries a single bibcode, so grouping
     several under a shared gloss becomes an explicit decision instead of the natural output.

⛔ **It proposes and does not write**: the inventory is written by the synthesiser.

    python scripts/contrast.py <slug> --campo regimen
    python scripts/contrast.py <slug> --grep 'Sigma|covarian'
    python scripts/contrast.py <slug> --eje identificabilidad --filas
    python scripts/contrast.py <slug> --validar vault/wiki/concepts/methods/<x>.md
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import lib_config as cfg
import lib_blocks as lb

CAMPOS = ("valor", "regimen", "aporte", "hueco", "ejes", "salvedades")


def extracciones(slug: str) -> list[tuple[str, dict]]:
    """`[(bibcode, data)]` of every extraction of the subject, in bibcode order.

    Reads `vault/raw/extraccion/<slug>/` (#311: versioned, because an extraction is not regenerable
    in the sense an `ads.json` is). A JSON that does not parse is DECLARED, never skipped in
    silence: this is the most expensive artefact of the chain."""
    out = []
    for f in sorted((cfg.EXTRACCION / slug).glob("*.json")):
        try:
            out.append((f.stem, json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as exc:
            cfg.print_seguro(f"  ⛔ {f.name}: no parsea ({exc}) — NO se saltea en silencio")
    return out


def valores(data: dict) -> list[dict]:
    """The `ground_truth` rows of one extraction, with their provenance attached."""
    filas = []
    for v in cfg.as_list(data.get("ground_truth")):
        if isinstance(v, dict):
            filas.append(v)
    return filas


def _mostrar(texto: str, completo: bool, limite: int) -> str:
    """One textual value, whole by default; when cut, the cut is VISIBLE (#314)."""
    t = " ".join(str(texto or "").split())
    if completo or len(t) <= limite:
        return t
    return lb.truncate_claim(t, limite) + " […✂ CORTADO: no lo cites desde acá]"


def imprimir(slug: str, *, campo: str | None, patron: str | None, paper: str | None,
             eje: str | None, completo: bool, limite: int, filas: bool) -> int:
    """The contrast view: group by FIELD, not by paper — contrasting is filtering, not reading 32
    files. Returns the number of lines printed."""
    rx = re.compile(patron, re.I) if patron else None
    n = 0
    for bib, data in extracciones(slug):
        if paper and paper != bib:
            continue
        if eje is not None:
            for k, v in cfg.as_map(data.get("ejes")).items():
                if eje and eje.lower() not in k.lower():
                    continue
                texto = _mostrar(v, completo, limite)
                if rx and not rx.search(f"{k} {texto}"):
                    continue
                cfg.print_seguro(f"[[{bib}]] · eje `{k}`\n    {texto}")
                n += 1
            continue
        for v in valores(data):
            texto = _mostrar(v.get("valor"), completo, limite)
            regimen = _mostrar(v.get("regimen"), completo, limite)
            que = " ".join(str(v.get("que") or "").split())
            campos = {"valor": texto, "regimen": regimen, "que": que}
            if campo and campo in campos:
                mostrado = campos[campo]
            elif campo:
                mostrado = _mostrar(data.get(campo), completo, limite)
            else:
                mostrado = f"{que} → {texto}"
            if rx and not rx.search(f"{que} {texto} {regimen}"):
                continue
            # La PROCEDENCIA viaja siempre (#314): los seis errores de atribución de la corrida
            # medida salieron de un digest que no la imprimía.
            loc = v.get("linea") or "sin localizador"
            sm = f" · ⚠ SEGUNDA MANO: {v['segunda_mano']}" if v.get("segunda_mano") else ""
            if filas:
                # Una fila, UNA fuente (#317): agrupar bibcodes bajo una glosa compartida es cómo
                # se fabrican atribuciones — que sea una decisión explícita, no la salida natural.
                cfg.print_seguro(f"| {cfg.escape_cell(que)} | [[{bib}]] | "
                                 f"{cfg.escape_cell(mostrado)} | {loc}{sm} |")
            else:
                cfg.print_seguro(f"[[{bib}]] · {loc}{sm}\n    {mostrado}"
                                 + (f"\n    régimen: {regimen}" if regimen and not campo else ""))
            n += 1
    if filas and n:
        cfg.print_seguro("\n  ⛔ Las filas son un ESQUELETO: el inventario lo redactás vos. Una "
                         "fila = una fuente, y la cita se copia ENTERA o se parafrasea sin comillas.")
    return n


def validar(slug: str, nota: pathlib.Path) -> int:
    """Cross-check note ↔ extraction ↔ `.txt`, and say what each discrepancy MEANS (#317).

    ⛔ The comparison nobody was making. #220 tests the note's verbatim quote against the `.txt`,
    which #205 declares a degraded index, so its signal was **2 of 17** in one concept and **0 of
    35** in another. The extraction is the transcription made while reading the PDF, so:

      · quote not in ANY extraction of its bibcode  → **the synthesiser invented it** (blocking)
      · quote in the extraction but not in the `.txt` → the `.txt` is degraded, the note is fine
      · quote in both                                 → nothing to say

    Returns the count of the first class, which is the one that must be zero."""
    texto = nota.read_text(encoding="utf-8")
    por_bib = {b: cfg.extraction_texts(b) for b, _d in extracciones(slug)}
    inventadas = 0
    for b in lb.split_blocks(texto):
        bibs = lb._bibcodes(b.text) or lb._bibcodes(b.intro or "")
        for cita in cfg.quotes_in(b.text):
            duenio = lb.quote_owner(b.text, cita, bibs)          # #316
            candidatos = [duenio] if duenio else bibs
            fuentes = [t for x in candidatos for t in por_bib.get(x, [])]
            if not fuentes:
                continue                # sin extracción de esa fuente: no evaluable, no se inventa
            if any(cfg.quote_found(cita, t) for t in fuentes):
                continue
            inventadas += 1
            cfg.print_seguro(
                f"  ⛔ L{b.first_line}: «{cita[:80]}{'…' if len(cita) > 80 else ''}» NO está en la "
                f"extracción de {', '.join(candidatos)} — la extracción se hizo leyendo el PDF, "
                f"así que esto no es un `.txt` degradado: la cita se alteró al sintetizar")
    cfg.print_seguro(f"  {inventadas} cita(s) que la extracción no respalda"
                     + (" ✅" if not inventadas else " ⛔ — corregilas contra el JSON, no contra el "
                        "`.txt`"))
    return inventadas


def main(argv=()) -> int:
    """CLI: filtra las extracciones del sujeto, o valida una nota contra ellas (`--validar`)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--campo", choices=CAMPOS + ("que",), help="agrupar por ese campo")
    ap.add_argument("--grep", metavar="RE", help="filtrar por expresión regular")
    ap.add_argument("--paper", metavar="BIBCODE", help="sólo esa fuente")
    ap.add_argument("--eje", nargs="?", const="", metavar="NOMBRE",
                    help="los `ejes` de cada extracción (sin valor: todos)")
    ap.add_argument("--filas", action="store_true",
                    help="esqueleto de fila de tabla, UNA fuente por fila (#317)")
    ap.add_argument("--limite", type=int, default=lb.TRUNCADO_CLAIM,
                    help="ancho máximo con --corto (default: el del bloque de verificación)")
    ap.add_argument("--corto", action="store_true",
                    help="acorta los valores MARCANDO el corte. Por default NO se corta: si no "
                         "entra, filtrá menos filas — un recorte cae dentro de la cita y el modelo "
                         "la completa (#314: 2 citas fabricadas en el carácter exacto del corte)")
    ap.add_argument("--validar", metavar="NOTA",
                    help="cruza esa nota contra las extracciones: una cita que la extracción no "
                         "respalda la inventó el sintetizador (#317)")
    args = ap.parse_args(list(argv) or None)

    if args.validar:
        nota = pathlib.Path(args.validar)
        if not nota.exists():
            cfg.print_seguro(f"⛔ no existe {nota}")
            return 2
        return 1 if validar(args.slug, nota) else 0

    if not (cfg.EXTRACCION / args.slug).exists():
        cfg.print_seguro(f"⛔ no hay extracciones en {cfg.EXTRACCION / args.slug} — corré el "
                         f"fan-out del paso 3 primero (`extraction_prompt.py {args.slug} <bib>`)")
        return 2
    n = imprimir(args.slug, campo=args.campo, patron=args.grep, paper=args.paper, eje=args.eje,
                 completo=not args.corto, limite=args.limite, filas=args.filas)
    cfg.print_seguro(f"\n  {n} valor(es) — el contraste es FILTRAR, no leer los JSON enteros. "
                     f"⛔ La cita se copia ENTERA o se parafrasea sin comillas.")
    return 0


if __name__ == "__main__":
    cfg.stdout_tolerante()
    cfg.cli_exit(main)
