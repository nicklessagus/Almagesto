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
  3. **One row, one source, and the quote already inside it (#322).** The row carries a single
     bibcode **and the string from the JSON**, quoted, escaped and with its locator: measured, the
     12 true positives of the gate were **copying** errors, not comprehension ones — 6 of
     attribution (one paper's sentence under another) and 6 of altered tail. Those are the class of
     task a script does perfectly and an LLM does badly, so the synthesiser writes the **gloss** and
     picks which rows enter; the quoted string is the machine's.

⛔ **It proposes and does not write**: the inventory is written by the synthesiser.

    python scripts/contrast.py <slug> --campo regimen
    python scripts/contrast.py <slug> --grep 'Sigma|covarian'
    python scripts/contrast.py <slug> --eje identificabilidad --filas
    python scripts/contrast.py --validar vault/wiki/concepts/methods/<x>.md
    python scripts/contrast.py --validar-todo            # toda la bóveda (gate: exit ≠ 0)
    python scripts/contrast.py <slug> --validar-todo     # sólo las notas del sujeto
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

#: #322 · el único hueco que el sintetizador llena a mano en una fila. Se emite como marcador
#: visible —no como celda vacía— para que una fila pegada sin escribir la glosa se note al leer la
#: nota, en vez de publicarse como una fila muda.
GLOSA = "«…tu glosa…»"


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
                # ⛔ #322 — la fila sale con la CITA YA ADENTRO, entre comillas, con su `[[bibcode]]`
                # y su localizador pegados. Medido sobre 32 hits: los 12 verdaderos positivos eran
                # errores de **copiado**, no de comprensión —6 de atribución (la frase de un paper
                # bajo otro) y 6 de cola alterada—, o sea de mover una cadena de un archivo a otro:
                # lo que un LLM hace mal y un script hace perfecto. El sintetizador escribe la
                # GLOSA y elige qué filas entran; la cadena entre comillas es de la máquina.
                cfg.print_seguro(f"| {cfg.escape_cell(que)} | [[{bib}]] | "
                                 f"«{cfg.escape_cell(texto)}» ({loc}){sm} | {GLOSA} |")
            else:
                cfg.print_seguro(f"[[{bib}]] · {loc}{sm}\n    {mostrado}"
                                 + (f"\n    régimen: {regimen}" if regimen and not campo else ""))
            n += 1
    if filas and n:
        cfg.print_seguro(f"\n  ⛔ La cadena entre «» ya es correcta por construcción (sale del JSON "
                         f"con su bibcode y su localizador): **no la re-tipees** — ahí es donde se "
                         f"pierden las citas (#322). Vos escribís la glosa (`{GLOSA}`) y decidís "
                         f"qué filas entran; si la cita no entra en la celda, se parafrasea SIN "
                         f"comillas.")
    return n


def validar(nota: pathlib.Path, *, mostrar: bool = True) -> dict:
    """Cross-check one note against the extractions of the bibcodes it cites (#317/#321/#323).

    ⛔ The comparison nobody was making. #220 tests the note's verbatim quote against the `.txt`,
    which #205 declares a degraded index, so its signal was **2 of 17** in one concept and **0 of
    35** in another. The extraction is the transcription made while reading the PDF.

    ⛔ **It blocks only on POSITIVE evidence, the partition of #321.** An extraction is a
    **selective, lensed** transcription (#188) and the framework tells you to quote from the PDF
    (#205), so its silence does not prove fabrication — measured, only 12 of 32 hits were real, and
    one of the other 20 is a quote #315 uses as an example of a CORRECT one. So:

      · verbatim under ANOTHER cited bibcode → **wrong attribution** (blocking; 6 of the 12)
      · long prefix matches and the tail diverges → **completed while copying** (blocking; 6 of 12)
      · extraction silent, or none on disk → **not evaluable**, declared and never counted as a
        finding (D-43)

    ⛔ **The rule lives in ONE place** (#324): `cfg.quote_verdict`, shared with `lint.collect`. With
    separate code they already diverged —13 against 12 over the same vault the same day— and the
    extra one was a FALSE positive this command would have turned into a blocked closing step.

    Returns `{"alteradas": [(línea, motivo)], "no_evaluables": [(línea, motivo)], "citas": N}` —
    counts, so the sweep can declare its population (INV-40) instead of printing a bare zero."""
    texto = nota.read_text(encoding="utf-8")
    out = {"alteradas": [], "no_evaluables": [], "citas": 0}
    bibs_nota = set(lb._bibcodes(texto))
    for b in lb.split_blocks(texto):
        bibs = lb._bibcodes(b.text) or lb._bibcodes(b.intro or "")
        for cita in cfg.quotes_in(b.text):
            out["citas"] += 1
            duenio = lb.quote_owner(b.text, cita, bibs)          # #316
            candidatos = [duenio] if duenio else bibs
            ambiguo = not duenio and len(bibs) > 1
            txts = {x: cfg.fulltext_readings(x) for x in candidatos}
            # #324 — la MISMA función que usa el lint, no una re-implementación: con código separado
            # daban 13 y 12 sobre el mismo corpus, y el de más era una cita CORRECTA cuya extracción
            # simplemente no la había transcripto.
            ver, det = cfg.quote_verdict(cita, candidatos, bibs_nota, txts, ambiguo=ambiguo)
            corte = cita if len(cita) <= 70 else cita[:70] + "…"
            quienes = ", ".join(candidatos) or "sin fuente adyacente"
            if ver in ("en_su_txt", "txt_degradado", "txt_parte"):
                continue
            if ver == "alterada" and det["otro_bib"]:
                out["alteradas"].append(
                    (b.first_line, f"«{corte}» está verbatim en la extracción de "
                                   f"**{', '.join(det['otro_bib'])}**, no en la de {quienes}: la "
                                   f"cita está atribuida a la fuente equivocada"))
            elif ver == "alterada":
                out["alteradas"].append(
                    (b.first_line, f"«{corte}» — el arranque coincide con la extracción de "
                                   f"{quienes} y la cola diverge: la cita se completó al copiar (el "
                                   f"patrón de #314)"))
            elif ver == "no_evaluable":
                out["no_evaluables"].append(
                    (b.first_line, f"«{corte}» — {quienes} sin `.txt` ni extracción en disco: no "
                                   f"evaluable, no es una cita alterada"))
            else:
                out["no_evaluables"].append(
                    (b.first_line, f"«{corte}» — ni el `.txt` ni la extracción de {quienes} la "
                                   f"dicen, y ninguna es evidencia positiva: la transcripción es "
                                   f"SELECTIVA y el `.txt` un índice degradado (#321/#205). "
                                   f"Confirmala en el PDF"))
    if mostrar:
        for ln, motivo in out["alteradas"]:
            cfg.print_seguro(f"  ⛔ L{ln}: {motivo}. Copiala del JSON con `contrast.py <slug> "
                             f"--grep …` — NO la re-tipees (#322)")
        for ln, motivo in out["no_evaluables"]:
            cfg.print_seguro(f"  · L{ln}: {motivo}")
    return out


def _notes_of(slug: str | None) -> list:
    """The notes the sweep looks at, and it says so: whole vault, or the subject's (#121/#323).

    With a slug the population is the entity note plus the paper notes whose extraction lives under
    that subject — the same asymmetry as `lint --cierre`: the scope narrows what is MINE to close,
    not what exists."""
    todas = sorted(cfg.WIKI.rglob("*.md")) if cfg.WIKI.exists() else []
    if not slug:
        return todas
    dir_ = cfg.EXTRACCION / slug
    stems = {f.stem for f in dir_.glob("*.json")} if dir_.exists() else set()
    stems.add(slug)
    return [f for f in todas if f.stem in stems]


def validar_todo(slug: str | None = None) -> int:
    """Sweep mode: every note of the vault (or of one subject) against its extractions (#323).

    ⛔ **The capability existed and nobody ran it.** `--validar` took one note at a time and no
    skill named it, so it only ran if somebody remembered — which is the definition of a control
    that does not exist. Measured: the note that produced #314–#318 closed with a full
    `verify-citations`, `lint --cierre` at 0 and **12 altered or misattributed quotes inside**; the
    comparison that caught them in seconds was written and never run.

    Declares its population (INV-40) and what it could not evaluate (D-43) — without
    `--migrate-extracciones` that population is **zero**, and a silent zero would read as a verdict.
    Returns the number of blocking findings, so it works as a gate."""
    notas = _notes_of(slug)
    alteradas = no_eval = citas = 0
    for f in notas:
        r = validar(f, mostrar=False)
        citas += r["citas"]
        no_eval += len(r["no_evaluables"])
        if r["alteradas"]:
            cfg.print_seguro(f"\n{f.relative_to(cfg.ROOT)}")
            for ln, motivo in r["alteradas"]:
                cfg.print_seguro(f"  ⛔ L{ln}: {motivo}")
            alteradas += len(r["alteradas"])
    ambito = f"las notas de `{slug}`" if slug else "toda la bóveda"
    cfg.print_seguro(f"\n> sobre {len(notas)} nota(s) de {ambito} · {citas} cita(s) «…» · "
                     f"{no_eval} no evaluable(s) (sin extracción en disco, o la extracción calla)")
    if not citas:
        cfg.print_seguro("  ⚠ NO EVALUADO: ninguna cita mirada. Si la bóveda es anterior a #311, "
                         "corré `python scripts/make_notes.py --migrate-extracciones` — un cero sin "
                         "denominador se lee como veredicto (D-43)")
    cfg.print_seguro(f"  {alteradas} cita(s) con evidencia POSITIVA de alteración"
                     + (" ✅" if not alteradas else " ⛔ — corregilas contra el JSON de extracción, "
                        "no contra el `.txt`"))
    return alteradas


def main(argv=()) -> int:
    """CLI: filtra las extracciones del sujeto, o valida una nota contra ellas (`--validar`)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?", help="el sujeto (opcional con --validar/--validar-todo)")
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
                    help="cruza esa nota contra las extracciones: la cita que aparece bajo OTRO "
                         "bibcode, o cuya cola diverge, se alteró al sintetizar (#317/#321)")
    ap.add_argument("--validar-todo", action="store_true",
                    help="barrido: toda la bóveda, o las notas del sujeto si das el slug (#323)")
    args = ap.parse_args(list(argv) or None)

    if args.validar_todo:
        return 1 if validar_todo(args.slug) else 0

    if args.validar:
        nota = pathlib.Path(args.validar)
        if not nota.exists():
            cfg.print_seguro(f"⛔ no existe {nota}")
            return 2
        r = validar(nota)
        cfg.print_seguro(f"  {len(r['alteradas'])} cita(s) con evidencia positiva de alteración "
                         f"· {len(r['no_evaluables'])} no evaluable(s) · {r['citas']} mirada(s)"
                         + (" ✅" if not r["alteradas"] else " ⛔"))
        return 1 if r["alteradas"] else 0

    if not args.slug:
        cfg.print_seguro("⛔ falta el slug (sólo --validar/--validar-todo pueden ir sin él)")
        return 2
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
