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
  3. **One row, one source, and the string from the JSON already inside it (#322).** The row
     carries a single bibcode **and the value verbatim from the JSON**, escaped and with its
     locator: measured, the 12 true positives of the gate were **copying** errors, not comprehension
     ones — 6 of attribution (one paper's sentence under another) and 6 of altered tail. Those are
     the class of task a script does perfectly and an LLM does badly, so the synthesiser writes the
     **gloss** and picks which rows enter; the string is the machine's.
  4. ⛔ **And the script NEVER adds a quotation mark of its own (#330).** `valor` is not «the
     quotation»: it is what the extractor wrote, and it arrives in three shapes. Wrapping all three
     in guillemets published 1262 of 1948 real values as verbatim when they were not — 315 of them
     the extractor's Spanish gloss presented as the words of an English paper, and 686 doubled into
     `««…»»`, which silently drops the quote from the effective population of the #323 gate.

⛔ **It proposes and does not write**: the inventory is written by the synthesiser.

    python scripts/contrast.py <slug> --campo regimen        # sin lo que `--drop-core` sacó (#329)
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

#: #330 · las tres formas en que llega `ground_truth[].valor`, con lo que la fila afirma de cada una.
#: El orden importa: es el del test de `quote_form`, y el banner las nombra a las tres.
FORMAS = {"cita": "cita textual, tal como la escribió el extractor",
          "glosa": "glosa del extractor CON la cita adentro, entre «»",
          "pelado": "SIN comillas: no es verbatim — no lo entrecomilles al pegarlo"}


def quote_form(texto: str) -> str:
    """Which of the three shapes `ground_truth[].valor` has: `cita` | `glosa` | `pelado` (#330).

    ⛔ **The script cannot know whether a value is verbatim** — that is the extractor's knowledge,
    and there is no honest heuristic for it. So it decides only what is decidable **on the string**,
    and it **never adds a guillemet of its own**: the quotation marks a row shows are the ones the
    extractor wrote. Measured over 1948 real values: 686 already open with `«` (wrapping them again
    produced `««…»»`, and `_QUOTE_RE` then captures a dangling `«` that exists in no source — the
    quote leaves the effective population of the #323 gate while the report still says `0 ✅`, the
    mould of #275), 315 carry a quote **inside** a gloss (wrapping published the extractor's Spanish
    prose as the words of an English paper — the very mechanism #322 exists to prevent) and 947 have
    no quotation at all (a table value presented as a quotation)."""
    t = (texto or "").strip()
    if t.startswith("«"):
        return "cita"
    if "«" in t:
        return "glosa"
    return "pelado"


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
             eje: str | None, completo: bool, limite: int, filas: bool,
             incluir_dropeados: bool = False) -> int:
    """The contrast view: group by FIELD, not by paper — contrasting is filtering, not reading 32
    files. Returns the number of lines printed.

    ⛔ **Declared curation applies HERE (#329).** The extractions of the papers the user took out of
    the subject with `--drop-core` are not served to step 3b: measured on a real theme, **13 of 51
    (25 %)** of its material, and all thirteen were declared polysemy false positives — feeding them
    to the step that PRODUCES the axes is handing the agent exactly the material that fabricates a
    false one (#112: a curation decision the reader ignores in silence is worse than not taking it).

    Two boundaries. It is the READING rail only: `validar`/`validar_todo` keep seeing every
    extraction, because a dropped paper is still a valid witness of whose sentence a quote is
    (#317/#321/#323) and filtering there would lower the detector's population and manufacture false
    «wrong attribution». And it MARKS instead of silently dropping: the population line declares how
    many were excluded (INV-40) and `--incluir-dropeados` shows them, each behind its own banner."""
    rx = re.compile(patron, re.I) if patron else None
    formas = dict.fromkeys(FORMAS, 0)          # #330: qué emitió, por forma — se declara al cerrar
    todas = extracciones(slug)
    # #112 vive en el registro VERSIONADO, no en `build/`: la única implementación de «qué papers
    # sacó el usuario de ESTE sujeto» es `cfg.dropped_from_subject` (regla de método nº 2 — el molde
    # de #215 es justamente el consumidor que nunca recibió copia).
    dropeados = cfg.dropped_from_subject(slug)
    n_drop = sum(1 for bib, _ in todas if bib in dropeados)
    items = todas if incluir_dropeados else [(b, d) for b, d in todas if b not in dropeados]
    n = 0
    for bib, data in items:
        if paper and paper != bib:
            continue
        if bib in dropeados:
            # sólo alcanzable con `--incluir-dropeados`: la extracción se pagó (#311) y a veces se
            # quiere ver, pero mezclada sin marca vuelve a ser material del 3b.
            cfg.print_seguro(f"  ⚠ [[{bib}]] fue DESCARTADO del sujeto con `--drop-core` "
                             f"({dropeados[bib]}): se muestra por `--incluir-dropeados` — NO lo "
                             f"pegues en el inventario")
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
                # ⛔ #322 — la fila sale con el VALOR YA ADENTRO, con su `[[bibcode]]` y su
                # localizador pegados. Medido sobre 32 hits: los 12 verdaderos positivos eran
                # errores de **copiado**, no de comprensión —6 de atribución (la frase de un paper
                # bajo otro) y 6 de cola alterada—, o sea de mover una cadena de un archivo a otro:
                # lo que un LLM hace mal y un script hace perfecto. El sintetizador escribe la
                # GLOSA y elige qué filas entran; la cadena es de la máquina.
                # ⛔ #330 — y sale TAL CUAL: las comillas son las que escribió el extractor. El
                # script no puede saber qué parte de `valor` es verbatim, así que no agrega ni una:
                # envolviendo las tres formas, 1262 de 1948 valores reales salían presentados como
                # cita sin serlo (686 doblados `««…»»`, que además se caen de la población del gate
                # de #323, y 315 con la glosa en castellano publicada como palabras del paper).
                formas[quote_form(texto)] += 1
                cfg.print_seguro(f"| {cfg.escape_cell(que)} | [[{bib}]] | "
                                 f"{cfg.escape_cell(texto)} ({loc}){sm} | {GLOSA} |")
            else:
                cfg.print_seguro(f"[[{bib}]] · {loc}{sm}\n    {mostrado}"
                                 + (f"\n    régimen: {regimen}" if regimen and not campo else ""))
            n += 1
    if filas and n:
        cfg.print_seguro(f"\n  ⛔ La celda sale TAL CUAL del JSON, con su bibcode y su localizador: "
                         f"**no la re-tipees** — ahí es donde se pierden las citas (#322). Vos "
                         f"escribís la glosa (`{GLOSA}`) y decidís qué filas entran; si no entra en "
                         f"la celda, se parafrasea SIN comillas.")
        cfg.print_seguro(f"  ⚠ Las comillas son las del EXTRACTOR, no las pone el script (#330). "
                         f"Tres formas, y esta corrida emitió: "
                         f"{formas['cita']} que abren con «» ({FORMAS['cita']}) · "
                         f"{formas['glosa']} con «» adentro ({FORMAS['glosa']}) · "
                         f"{formas['pelado']} sin «» ({FORMAS['pelado']}).")
    # INV-40 — la población se DECLARA, incluido el cero: un listado que calla cuántas extracciones
    # dejó afuera no distingue «no había ninguna dropeada» de «nadie miró la curación» (#329).
    if incluir_dropeados:
        cola = f"{n_drop} DROPEADA(s) mostrada(s) por `--incluir-dropeados`"
    elif n_drop:
        cola = f"{n_drop} excluida(s) por `--drop-core` (`--incluir-dropeados` para verlas)"
    else:
        cola = "0 excluida(s) por `--drop-core`"
    cfg.print_seguro(f"\n> sobre {len(todas)} extracción(es) del sujeto · {cola}")
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

    ⛔ **What it approves with ONE witness is counted, not hidden (#341).** Step 2 of
    `quote_verdict` —`txt_degradado`— clears a quote because an extraction of its own source holds
    it while the `.txt` of that same source does not. That is the right call (the `.txt` is a
    degraded index, #205) and it is **a single reading of the PDF**: the one made by an LLM.
    Measured over a real vault (2026-08-31, 163 notes, 3099 quotes): of the **242** it approved,
    **45** rest on that single witness, and the command printed `0 ✅` over all of them without
    saying so. So it travels in the population line (INV-40); it is not a finding and **does not
    move the rc** — if it did, the mandatory closing step of #323 would stop on 45 correct quotes.

    ⛔ **And the single witness can be CONTRADICTED by the other one (#333).** When the `.txt` of
    that same source carries the opening of the quote and continues differently in running prose,
    the two readings of one PDF disagree and that is reported —`discrepan`— as its own population.
    It **does not move the rc**: the `.txt` is a degraded index and this gate stops operations
    (#323), so an accusation of it is a *go and look at the page*, never a failed close.

    ⛔ **And when the divergence is decidable it hands over the MARK (#341).** No new mechanism is
    needed: `⚠verificar en el PDF (<what was doubted>, <date>)` already exists —the fourth of the
    five in-line marks— and has exactly the properties this case wants: it does **not** destroy the
    claim, it is visible, the lint raises it, and it comes off when somebody verifies it with
    evidence. ⛔ It is **emitted, never applied**: `contrast` proposes and does not write in
    `vault/`, and which of the two readings wins is decided by whoever opens the page.

    Returns `{"alteradas": [(línea, motivo)], "no_evaluables": [(línea, motivo)],
    "discrepan": [(línea, motivo, marca)], "citas": N, "solo_extraccion": J}` — counts, so the sweep
    can declare its population (INV-40) instead of printing a bare zero."""
    texto = nota.read_text(encoding="utf-8")
    out = {"alteradas": [], "no_evaluables": [], "discrepan": [], "citas": 0, "solo_extraccion": 0}
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
            if ver in ("txt_degradado", "txt_acusa"):
                # #341 — aprobada por UN SOLO TESTIGO: la extracción de su fuente la dice y el
                # `.txt` de esa misma fuente no. Se cuenta acá, antes del `continue`, porque el
                # veredicto es correcto y aun así la población que lo lleva tiene que ser visible.
                out["solo_extraccion"] += 1
            if ver == "txt_acusa":
                # #333 — y de esas, la que el OTRO lector contradice: no es un hallazgo bloqueante
                # (el `.txt` es índice degradado, #205) y tampoco es silencio. #341 — y como la
                # divergencia es decidible, sale con la MARCA armada: no hace falta mecanismo nuevo,
                # `⚠verificar en el PDF` ya existe y tiene justo las propiedades que hacen falta.
                out["discrepan"].append(
                    (b.first_line, f"«{corte}» — el `.txt` de {det['bib']} trae el mismo arranque y "
                                   f"sigue distinto: dice «…{det['cola_txt'][:70]}» donde la "
                                   f"extracción dice «…{det['cola_cita'][:70]}». Son DOS lecturas "
                                   f"del mismo PDF —`pdftotext` y un LLM— y la fuente es el PDF: "
                                   f"andá a la página (#333)",
                     cfg.verificar_pdf_mark(
                         f"el `.txt` de {det['bib']} sigue «…{det['cola_txt'][:40]}» y la "
                         f"extracción «…{det['cola_cita'][:40]}»")))
            if ver in ("en_su_txt", "txt_degradado", "txt_acusa", "txt_parte"):
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
        for ln, motivo, marca in out["discrepan"]:
            cfg.print_seguro(f"  ⚠ L{ln}: {motivo}\n     → si no podés abrirlo ahora, pegá al final "
                             f"de la afirmación:  {marca}")
        for ln, motivo in out["no_evaluables"]:
            cfg.print_seguro(f"  · L{ln}: {motivo}")
    return out


def _notes_of(slug: str | None) -> list:
    """The notes the sweep looks at, and it says so: whole vault, or the subject's (#121/#323).

    With a slug the population is the entity note plus the paper notes whose extraction lives under
    that subject — the same asymmetry as `lint --cierre`: the scope narrows what is MINE to close,
    not what exists.

    ⛔ **It does NOT cross `dropped_from_subject`, unlike the reading rail (#329).** A paper the user
    took out of the subject is still a valid witness of whose sentence a quote is, so filtering here
    would lower the detector's population and turn a correct attribution into a false «wrong
    attribution» — the very class of false positive #324/#325 just removed from a closing step."""
    # #344 — los hermanos `.verif.md` NO son notas: su tabla es el rastro de auditoría, y sus
    # celdas `Evidencia` son citas que el fan-out ya sacó de la fuente. Barrerlas acá inventaría una
    # población entera de «citas de la bóveda» sobre un artefacto que no afirma nada, y este gate
    # frena operaciones (#323).
    todas = cfg.note_paths(cfg.WIKI, "**/*.md")
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

    Declares its population (INV-40), what it could not evaluate (D-43), what it approved with
    a single witness (#341) and where the OTHER reading of the same PDF contradicts it (#333) —
    without `--migrate-extracciones` that population is **zero**, and a silent zero would read as a
    verdict. Returns the number of blocking findings, so it works as a gate: none of the three extra
    counts moves it."""
    notas = _notes_of(slug)
    alteradas = no_eval = citas = solo_ext = 0
    discrepan: list = []
    for f in notas:
        r = validar(f, mostrar=False)
        citas += r["citas"]
        no_eval += len(r["no_evaluables"])
        solo_ext += r["solo_extraccion"]
        discrepan += [(f, ln, m, k) for ln, m, k in r["discrepan"]]
        if r["alteradas"]:
            cfg.print_seguro(f"\n{f.relative_to(cfg.ROOT)}")
            for ln, motivo in r["alteradas"]:
                cfg.print_seguro(f"  ⛔ L{ln}: {motivo}")
            alteradas += len(r["alteradas"])
    for f, ln, motivo, marca in discrepan:
        cfg.print_seguro(f"\n{f.relative_to(cfg.ROOT)}\n  ⚠ L{ln}: {motivo}"
                         f"\n     → si no podés abrirlo ahora, pegá al final de la afirmación:"
                         f"  {marca}")
    ambito = f"las notas de `{slug}`" if slug else "toda la bóveda"
    cfg.print_seguro(f"\n> sobre {len(notas)} nota(s) de {ambito} · {citas} cita(s) «…» · "
                     f"{no_eval} no evaluable(s) (sin extracción en disco, o la extracción calla) · "
                     f"{solo_ext} sólo respaldada(s) por la extracción, "
                     f"{len(discrepan)} de ellas con el `.txt` en contra")
    if not citas:
        cfg.print_seguro("  ⚠ NO EVALUADO: ninguna cita mirada. Si la bóveda es anterior a #311, "
                         "corré `python scripts/make_notes.py --migrate-extracciones` — un cero sin "
                         "denominador se lee como veredicto (D-43)")
    cfg.print_seguro(f"  {alteradas} cita(s) con evidencia POSITIVA de alteración"
                     + (" ✅" if not alteradas else " ⛔ — corregilas contra el JSON de extracción, "
                        "no contra el `.txt`"))
    if solo_ext:
        cfg.print_seguro(f"  ⚠ de las aprobadas, {solo_ext} se apoyan en UN SOLO TESTIGO: la "
                         f"extracción de su fuente las dice y el `.txt` de esa misma fuente no. Es "
                         f"el veredicto correcto (el `.txt` es un índice degradado, #205) y "
                         f"**no** es un hallazgo: ante la duda, la página del PDF (#341)")
    if discrepan:
        cfg.print_seguro(f"  ⚠ y en {len(discrepan)} de ésas el OTRO lector del mismo PDF dice "
                         f"otra cosa (arriba, con su cola y su marca lista para pegar). No mueve el "
                         f"rc —el `.txt` es índice degradado— y tampoco es silencio: andá a la "
                         f"página, y lo que no puedas cerrar queda MARCADO en la nota (#333/#341)")
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
    ap.add_argument("--incluir-dropeados", action="store_true",
                    help="mostrar TAMBIÉN las extracciones de los papers que `--drop-core` sacó del "
                         "sujeto (#329). Por default no entran al 3b: son curación declarada, y "
                         "cada una sale con su banner para que no se mezclen con el material")
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
                         f"· {len(r['no_evaluables'])} no evaluable(s) · "
                         f"{r['solo_extraccion']} sólo respaldada(s) por la extracción "
                         f"({len(r['discrepan'])} con el `.txt` en contra) · "
                         f"{r['citas']} mirada(s)"
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
                 completo=not args.corto, limite=args.limite, filas=args.filas,
                 incluir_dropeados=args.incluir_dropeados)
    cfg.print_seguro(f"\n  {n} valor(es) — el contraste es FILTRAR, no leer los JSON enteros. "
                     f"⛔ La cita se copia ENTERA o se parafrasea sin comillas.")
    return 0


if __name__ == "__main__":
    cfg.stdout_tolerante()
    cfg.cli_exit(main)
