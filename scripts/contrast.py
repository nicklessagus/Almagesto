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

Four guarantees, each closing one of the measured failure modes:

  1. **A quote is never truncated INSIDE its quotation marks.** The reader of extractions (3b)
     prints every value whole, always: when the material does not fit, the remedy is to filter
     fewer rows, never to cut text (#226's doctrine, one step earlier). The opt-in cut
     (`--corto`/`--limite`) was retired (AUD-287): nothing used it, and it reintroduced the exact
     cut that #314 measured two fabricated quotes on. The `--validar` REPORT does shorten a quote
     to name it, but the cut is declared as such — the ellipsis goes OUTSIDE the «» (`lib_quotes.quote_fragment`,
     AUD-427) — and the `⚠verificar en el PDF` mark handed over to paste carries the extraction's
     tail whole.
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
import datetime as _dt
import json
import pathlib
import re
import sys

import yaml

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
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            cfg.print_seguro(f"  ⛔ {f.name}: no parsea ({exc}) — NO se saltea en silencio")
            continue
        # #374 — la identidad es el `bibcode` DE ADENTRO, no `f.stem`: con una segunda lente
        # (`<bib>__<lente>.json`, #308) el nombre deja de ser el bibcode y este lector divergía del
        # cosechador, que mapea por el campo desde #228.
        bib = cfg.extraction_identity(data)
        if not bib:
            cfg.print_seguro(f"  ⛔ {f.name}: sin `bibcode` — de quién es la lectura no se adivina "
                             f"del nombre del archivo (#374)")
            continue
        out.append((bib, data))
    return sorted(out, key=lambda par: par[0])


def valores(data: dict) -> list[dict]:
    """The `ground_truth` rows of one extraction, with their provenance attached."""
    filas = []
    for v in cfg.as_list(data.get("ground_truth")):
        if isinstance(v, dict):
            filas.append(v)
    return filas


def _mostrar(texto: str) -> str:
    """One textual value, whole — whitespace collapsed, never cut (#314)."""
    return " ".join(str(texto or "").split())


def imprimir(slug: str, *, campo: str | None, patron: str | None, paper: str | None,
             eje: str | None, filas: bool,
             incluir_dropeados: bool = False, cita: bool = False) -> int:
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
                texto = _mostrar(v)
                if rx and not rx.search(f"{k} {texto}"):
                    continue
                cfg.print_seguro(f"[[{bib}]] · eje `{k}`\n    {texto}")
                n += 1
            continue
        for v in valores(data):
            texto = _mostrar(v.get("valor"))
            regimen = _mostrar(v.get("regimen"))
            que = " ".join(str(v.get("que") or "").split())
            campos = {"valor": texto, "regimen": regimen, "que": que}
            if campo and campo in campos:
                mostrado = campos[campo]
            elif campo:
                mostrado = _mostrar(data.get(campo))
            else:
                mostrado = f"{que} → {texto}"
            if rx and not rx.search(f"{que} {texto} {regimen}"):
                continue
            # La PROCEDENCIA viaja siempre (#314): los seis errores de atribución de la corrida
            # medida salieron de un digest que no la imprimía.
            loc = v.get("linea") or "sin localizador"
            sm = f" · ⚠ SEGUNDA MANO: {v['segunda_mano']}" if v.get("segunda_mano") else ""
            if cita:
                # #385 — el copiado sin re-tipear existía sólo para el INVENTARIO (`--filas`), y la
                # síntesis es PROSA: en una ficha real, 33 de 43 citas. Para ésas el operador
                # transcribía a mano, que es el gesto que #322 declara inseguro — y produjo el
                # defecto que abrió el issue (dos palabras caídas al copiar). El fragmento trae lo
                # que un LLM transcribiendo se come: la cadena TAL CUAL (#330: las comillas son las
                # del extractor, el script no pone ninguna), el localizador, y el `[[bibcode]]`
                # PEGADO (#325: entre la cita y el link, sólo el paréntesis del localizador — la
                # marca de segunda mano va DESPUÉS del bibcode, no en el medio).
                formas[quote_form(texto)] += 1
                cfg.print_seguro(f"{texto} ({loc}) [[{bib}]]{sm}")
            elif filas:
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
                # AUD-470 — la fila va a una nota: también el `$` suelto (#457), después del `|`.
                cfg.print_seguro(f"| {cfg.escape_dollars(cfg.escape_cell(que))} | [[{bib}]] | "
                                 f"{cfg.escape_dollars(cfg.escape_cell(texto))} ({loc}){sm} | "
                                 f"{GLOSA} |")
            else:
                cfg.print_seguro(f"[[{bib}]] · {loc}{sm}\n    {mostrado}"
                                 + (f"\n    régimen: {regimen}" if regimen and not campo else ""))
            n += 1
    if (filas or cita) and n:
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


def _page_check(b, cita: str, duenio: str | None, out: dict) -> None:
    """This quote's page locator, contrasted against the `.txt` of its source (#492).

    ⛔ Runs **before** any `continue` of the chain verdict: they are two different axes of one pair
    —*is this the sentence?* and *is it on that page?*— and the quote that IS verbatim in its `.txt`
    (the normal case, `en_su_txt`) is precisely the one this check can decide.

    ⛔ With AMBIGUOUS attribution it does not judge (#316/#325): the locator would be contrasted
    against the wrong source, which is how the finding this repo hunts the most gets fabricated. It
    comes out *not evaluable*, which is what it is.
    """
    rangos = cfg.page_locators_after(b.text, cita)
    if not rangos:
        return
    out["pag_total"] += 1
    out["pag_consumidos"] += len(rangos)
    if not duenio:
        out["pag_no_eval"] += 1
        return
    estado, det = cfg.quote_page_verdict(cita, duenio, rangos)
    corte = cfg.quote_fragment(cita, 70)
    decl = ", ".join(f"p. {a}" if a == b_ else f"pp. {a}-{b_}" for a, b_ in rangos)
    if estado == "ok":
        out["pag_ok"] += 1
    elif estado == "mal":
        # #436/#437 — el PDF reemplazado es la causa MEDIDA de la mayoría (104 de 893 en una bóveda
        # real), y es la que convierte la deuda global de `_paginacion` en esta lista con su página
        # nueva. Se nombra acá porque cambia qué hay que hacer: no es un error de transcripción.
        # #494 — la causa es la deuda ABIERTA, no la familia: tras `_repaginado` la relectura ya
        # actualizó los localizadores de la extracción, así que decir «es del documento anterior»
        # sería falso. La exención de #437/#495 mira la familia entera porque contesta la otra
        # pregunta —la transcripción—, que el repaginado no toca.
        causa = (" · la extracción de esa fuente es de un PDF REEMPLAZADO (#436) y su deuda de "
                 "paginación sigue ABIERTA: el localizador es del documento anterior"
                 if cfg.extraction_pagination_open(duenio) else "")
        out["pag_mal"].append(
            (b.first_line, f"{corte} ({decl}) — la cita está en la p. "
                           f"{', '.join(map(str, det['impresas']))} de {duenio} (índice "
                           f"{', '.join(map(str, det['paginas']))} del PDF){causa}"))
    else:
        out["pag_no_eval"] += 1


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

    ⛔ **And it judges the OTHER half of the pair: the page LOCATOR** (#492, `_page_check`). Same walk,
    same attribution, a different axis — *is this the sentence* and *is it on that page* are two
    questions, and until now nobody asked the second one.

    Returns `{"alteradas": [(línea, motivo)], "no_evaluables": [(línea, motivo)],
    "discrepan": [(línea, motivo, marca)], "citas": N, "solo_extraccion": J}` plus the page axis
    (`pag_total`, `pag_ok`, `pag_mal`, `pag_no_eval`) — counts, so the sweep can
    declare its population (INV-40) instead of printing a bare zero."""
    texto = nota.read_text(encoding="utf-8")
    out = {"alteradas": [], "no_evaluables": [], "discrepan": [], "resueltas": [],
           # #454 — población propia: las citas que viven en un bloque estampado desde la
           # extracción. Contarlas dentro de `solo_extraccion` mezclaba dos cosas distintas.
           "citas": 0, "solo_extraccion": 0, "copiadas": 0,
           # #492 — el otro eje del par: la PÁGINA que el localizador declara. No mueve el rc (ver
           # `quote_page_verdict`): este gate frena operaciones (#323) y la población que mira es la
           # más grande de la bóveda.
           "pag_total": 0, "pag_ok": 0, "pag_mal": [], "pag_no_eval": 0,
           # #492 — y la población que este chequeo NO alcanza por construcción: el localizador sin
           # cita textual adyacente (el caso de `Almagesto-Tesis#8` mismo). Sin cita no hay qué buscar
           # en el `.txt`; se cuenta para que un «0 MAL» no se lea como «todo mirado» (INV-40).
           "pag_consumidos": 0, "pag_sin_cita": 0}
    bibs_nota = set(lb._bibcodes(texto))
    # #373/#394 — en una nota de PAPER el bibcode es la nota, no un link, y desde #394 la regla
    # (y su medición) vive en `cfg.note_own_bibcode`/`cfg.with_own_bibcode`, compartida con el lint:
    # dos gates que juzgan la misma cita no pueden tener dos implementaciones (#324).
    fm = cfg.split_fm(texto)
    propio = cfg.note_own_bibcode(nota, fm)
    if propio:
        bibs_nota.add(propio)
    # #516 — la cita confirmada en la página y firmada calla ACÁ también (misma función que el lint,
    # #324). La firma rota no se juzga acá: la reporta el lint (`cita_revisada_huerfana`).
    try:
        firmas = cfg.load_reviewed_quotes(fm or {}, entry=nota.stem)
    except cfg.VistasError:
        firmas = []
    for b in lb.split_blocks(texto):
        # #386/#387 — el `log` es append-only por contrato, así que su corrección es una MARCA y no
        # una edición, y una entrada que documenta una cita defectuosa tiene que citarla. Las dos
        # exenciones las decide UNA función, compartida con el lint: una convención en prosa que
        # cada chequeo aprende por su cuenta no compone, y éstos ya divergían.
        exento = cfg.log_quote_exempt(nota.stem, b.text, b.kind)
        if exento:
            for _c in cfg.quotes_in(b.text):
                out["citas"] += 1
                out["resueltas"].append((b.first_line, f"{exento}: visible, no es deuda"))
            continue
        bibs = cfg.with_own_bibcode(lb._bibcodes(b.text) or lb._bibcodes(b.intro or ""), propio)
        antes = out["pag_consumidos"]
        citas_bloque = cfg.quotes_in(b.text)
        for cita in citas_bloque:
            out["citas"] += 1
            duenio = lb.quote_owner(b.text, cita, bibs)          # #316
            candidatos = [duenio] if duenio else bibs
            ambiguo = not duenio and len(bibs) > 1
            _page_check(b, cita, duenio, out)
            txts = {x: cfg.fulltext_readings(x) for x in candidatos}
            # #324 — la MISMA función que usa el lint, no una re-implementación: con código separado
            # daban 13 y 12 sobre el mismo corpus, y el de más era una cita CORRECTA cuya extracción
            # simplemente no la había transcripto.
            # #454 — la cita que la MÁQUINA copió de la extracción (el bloque de salvedades) no
            # puede juzgarse contra la extracción: el testigo y el juzgado son el mismo archivo.
            copiada = cfg.quote_from_stamped_block(b.text, b.intro)
            ver, det = cfg.quote_verdict(cita, candidatos, bibs_nota, txts, ambiguo=ambiguo,
                                         copiada=copiada)
            corte = cfg.quote_fragment(cita, 70)
            quienes = ", ".join(candidatos) or "sin fuente adyacente"
            firma = cfg.reviewed_quote(firmas, candidatos, cita) \
                if ver in cfg.QUOTE_REVIEWABLE else None
            if firma:
                out["resueltas"].append(
                    (b.first_line, f"`cita_revisada`: confirmada en el PDF de {firma['ref']}, p. "
                                   f"{firma['pagina']} — {firma['motivo']} (#516)"))
                continue
            firmala = cfg.reviewed_quote_entry(candidatos, cita) \
                if ver in cfg.QUOTE_REVIEWABLE else ""
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
                    (b.first_line, f"{corte} — el `.txt` de {det['bib']} trae el mismo arranque y "
                                   f"sigue distinto: dice {cfg.quote_fragment(det['cola_txt'], 70, lead=True)} donde la "
                                   f"extracción dice {cfg.quote_fragment(det['cola_cita'], 70, lead=True)}. Son DOS lecturas "
                                   f"del mismo PDF —`pdftotext` y un LLM— y la fuente es el PDF: "
                                   f"andá a la página (#333){firmala}",
                     cfg.verificar_pdf_mark(
                         f"el `.txt` de {det['bib']} sigue {cfg.quote_fragment(det['cola_txt'], lead=True, trail=True)} y la "
                         f"extracción {cfg.quote_fragment(det['cola_cita'], lead=True)}")))
            if ver == "extraccion_vieja":
                # #437 — la extracción describe un PDF reemplazado: su cola distinta es la redacción
                # del preprint, no evidencia contra el documento en disco. Y el `.txt` nuevo calla,
                # así que no «pasa»: sale con la marca, como el `txt_acusa` de #341.
                out["discrepan"].append(
                    (b.first_line, f"{corte} — la extracción de {', '.join(det['bibs'])} es de un "
                                   f"PDF REEMPLAZADO (#436) y el `.txt` del nuevo no la "
                                   f"encuentra: no se puede decidir desde acá. Abrí el PDF nuevo "
                                   f"(#437){firmala}",
                     cfg.verificar_pdf_mark(
                         f"la extracción de {', '.join(det['bibs'])} es del PDF anterior y el "
                         f"nuevo no la trae verbatim")))
            if ver in ("en_su_txt", "txt_degradado", "txt_acusa", "txt_parte", "extraccion_vieja"):
                continue
            if ver == "alterada" and det["otro_bib"]:
                out["alteradas"].append(
                    (b.first_line, f"{corte} está verbatim en la extracción de "
                                   f"**{', '.join(det['otro_bib'])}**, no en la de {quienes}: la "
                                   f"cita está atribuida a la fuente equivocada"))
            elif ver == "alterada" and det.get("txt_nuevo"):
                out["alteradas"].append(
                    (b.first_line, f"{corte} — el PDF de {det['txt_nuevo']} se reemplazó y su "
                                   f"`.txt` NUEVO trae el mismo arranque y sigue distinto: dice "
                                   f"{cfg.quote_fragment(det['cola_txt'], 70, lead=True)} donde la nota dice "
                                   f"{cfg.quote_fragment(det['cola_cita'], 70, lead=True)}. La cita no es la del documento en "
                                   f"disco (#437)"))
            elif ver == "alterada":
                out["alteradas"].append(
                    (b.first_line, f"{corte} — el arranque coincide con la extracción de "
                                   f"{quienes} y la cola diverge: la cita se completó al copiar (el "
                                   f"patrón de #314)"))
            elif ver == "sin_testigo_propio":
                # ⛔ #454 — la cita vive en el bloque que la máquina copió de la extracción, así que
                # la extracción NO es testigo: la aprobaría siempre. Su único testigo independiente
                # es el `.txt`, y no la tiene. Sale con la marca de #225/#341, que no destruye la
                # afirmación, es visible y se saca con evidencia.
                out["copiadas"] += 1
                # ⚠ Acá el dueño es LA NOTA, no un candidato adyacente: el bloque de salvedades
                # no lleva `[[bibcode]]`, así que `quienes` caía en su literal por defecto y el
                # mensaje decía «la extracción de sin fuente adyacente».
                out["discrepan"].append(
                    (b.first_line,
                     f"{corte} — la escribió la máquina DESDE la extracción de "
                     f"{propio or quienes}, así que esa extracción no es testigo (#454), y el "
                     f"`.txt` no la dice: nadie la verificó nunca{firmala}",
                     cfg.verificar_pdf_mark("la cita de una salvedad, sin testigo independiente")))
            elif ver == "no_evaluable":
                out["no_evaluables"].append(
                    (b.first_line, f"{corte} — {quienes} sin `.txt` ni extracción en disco: no "
                                   f"evaluable, no es una cita alterada"))
            else:
                out["no_evaluables"].append(
                    (b.first_line, f"{corte} — ni el `.txt` ni la extracción de {quienes} la "
                                   f"dicen, y ninguna es evidencia positiva: la transcripción es "
                                   f"SELECTIVA y el `.txt` un índice degradado (#321/#205). "
                                   f"Confirmala en el PDF{firmala}"))
        out["pag_sin_cita"] += max(0, len(cfg.page_locators(b.text))
                                   - (out["pag_consumidos"] - antes))
    if mostrar:
        for ln, motivo in out["alteradas"]:
            cfg.print_seguro(f"  ⛔ L{ln}: {motivo}. Copiala del JSON con `contrast.py <slug> "
                             f"--grep …` — NO la re-tipees (#322)")
        for ln, motivo, marca in out["discrepan"]:
            cfg.print_seguro(f"  ⚠ L{ln}: {motivo}\n     → si no podés abrirlo ahora, pegá al final "
                             f"de la afirmación:  {marca}")
        for ln, motivo in out["pag_mal"]:
            cfg.print_seguro(f"  ⚠ L{ln}: {motivo}. Corregí el localizador — es lo que hace "
                             f"encontrable la afirmación en el PDF (#492/#500)")
        for ln, motivo in out["no_evaluables"]:
            cfg.print_seguro(f"  · L{ln}: {motivo}")
        for ln, motivo in out["resueltas"]:
            cfg.print_seguro(f"  ✓ L{ln}: declarada y resuelta — {motivo}")
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
    # #374 — por BIBCODE, no por `f.stem`: con el stem, la nota de un paper releído bajo otra lente
    # quedaba fuera de la población del barrido acotado (medido: 13 stems sin ninguna nota).
    stems = {b for b, _ in extracciones(slug)}
    stems.add(slug)
    return [f for f in todas if f.stem in stems]


CITAS_FILE = "_citas.yaml"


def save_ultima_pasada_citas(poblacion: dict, alteradas: int) -> None:
    """Registra que el barrido GLOBAL de citas corrió, con su población (#386).

    Same doctrine as `_red.yaml` (D-46): *when it was last looked at* is information about the
    vault, not about the machine, so it is versioned and travels. Without it a clone reports
    «never run», which is false.

    ⛔ **Only the global sweep writes it.** With a slug the sweep looks at the notes of ONE subject,
    and recording that as «the pass» would claim the vault was swept when a corner was — the same
    reason `sweep_external --bibcodes` does not register a pass. That gap is exactly what #386
    measured: the skill's closing step runs it **with the slug**, which returns 0 while the global
    returns 1, so four subjects closed green over a gate that had never been in the green."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    pasada = {"fecha": _dt.date.today().isoformat(),
              "version": cfg.ALMAGESTO_VERSION,
              "poblacion": dict(poblacion),
              "alteradas": alteradas}
    cfg.write_text_atomic(cfg.REGISTRO / CITAS_FILE, yaml.safe_dump(
        {"ultima_pasada_citas": pasada}, sort_keys=False, allow_unicode=True))


#: #490 — el patrón MEDIDO de la afirmación negativa o superlativa (114 en una bóveda de 8 notas
#: de entidad). No se amplía sin volver a medir: cada término nuevo cambia la población sobre la que
#: el issue prometió su número. ⚠ AUD-456: la apocopada «ningún» —la forma más común— no estaba
#: (`ningun[oa]s?` no acepta la `ú`), así que el 114 de #490 se midió SIN ella: es un piso, no el
#: número. Se agrega porque es la misma palabra, no un término nuevo.
NEGATIVA_RE = re.compile(r"(?i)\b(?:el|la|lo)\s+únic[oa]\b|\bning(?:ún|un[oa]s?)\b|\bnadie\b|"
                         r"\bnunca\b|\bno existe\b|\bsólo\s+(?:dos|tres|cuatro|cinco|seis)\b")

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def added_lines(ref: str = "HEAD") -> dict:
    """`{nota: {nº de línea: texto}}` — the lines THIS diff adds under `vault/wiki/` (#490).

    ⛔ The pre-flight looks at the **added lines**, not at the note: that is where the corrector's
    defect lives and where the noise is smallest. Measured on an `audit-note` over three notes: the
    corrector introduced **14** defects, `lint` caught **0** and the blind fan-out **11** — three
    rounds of subagents for classes that are decidable on the diff.

    An untracked note counts whole: it has nothing to diff against, and a note written in this pass
    is all «added».
    """
    import subprocess
    out: dict = {}
    r = subprocess.run(["git", "diff", "-U0", ref, "--", "vault/wiki"],
                       cwd=cfg.ROOT, capture_output=True, text=True)
    actual, n = None, 0
    for ln in r.stdout.split("\n"):
        if ln.startswith("+++ b/"):
            actual, n = cfg.ROOT / ln[6:], 0
        elif (m := _HUNK_RE.match(ln)):
            n = int(m.group(1))
        elif ln.startswith("+") and actual is not None and actual.suffix == ".md":
            out.setdefault(actual, {})[n] = ln[1:]
            n += 1
    r = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "vault/wiki"],
                       cwd=cfg.ROOT, capture_output=True, text=True)
    for rel in r.stdout.split():
        f = cfg.ROOT / rel
        if f.suffix == ".md" and f.exists():
            out[f] = dict(enumerate(f.read_text(encoding="utf-8").split("\n"), 1))
    return out


def _row_role_claims(fila: str) -> list:
    """`[(bibcode, rol escrito)]` for an added table row that assigns a `role` to a paper (#490)."""
    bibs = lb.BIBCODE_LINK_RE.findall(fila) if hasattr(lb, "BIBCODE_LINK_RE") else \
        re.findall(r"\[\[([^\]]+)\]\]", fila)
    celdas = [c.strip(" *_`") for c in fila.split("|")]
    roles = [c for c in celdas if cfg.method_key(c) in cfg.ROLES]
    return [(b, r) for b in bibs[:1] for r in roles]


def preflight(ref: str = "HEAD") -> int:
    """Pre-flight over the DIFF of a correction, BEFORE the fan-out (#490).

    ⛔ **Correcting is WRITING, and what gets written does not inherit the diagnosis's evidence.**
    #203 says what is corrected gets re-verified and #282 that the cycle does not converge by
    itself; what neither says is WHICH class of sentence the corrector produces — and those classes
    are decidable on the diff, before spending one subagent per source. Three, none needing an LLM:

    1. **negative or superlative added** — outside `## Huecos`, which declares its scope (D-34), and
       outside a blockquote, which is a mention and not a claim (#387);
    2. **quote added** that its source's extraction contradicts — the rule of #333 restricted to the
       diff, where a false positive costs a look and not an operation;
    3. **`role` added in a row** that the cited paper's frontmatter does not declare — crossed by
       hand until now.

    ⚠ **What it does NOT promise**, and it is the larger half: the 7 «condition that falls off while
    transcribing» of the same measurement are **not decidable without reading the source**, so they
    stay in blind verification. This does not loosen it. ⛔ Nor does it catch the **re-typed quote**
    («omit*s*» for «omit*ting*»): that diverges INSIDE a word and the guard of #333 only accuses on
    a word boundary, on purpose, so as not to catch `pdftotext` breaks. For that class the detector
    cannot be `contrast`: it is **not re-typing** (#322). Measured net gain: **2**.

    The exit code follows the rule already in force (#323): only POSITIVE evidence of alteration
    blocks; the three categories are backlog, which is what a pre-flight is for."""
    todo = added_lines(ref)
    # ⛔ #490 (validación en la instancia) — el alcance es la PROSA DE NOTA, no «todo `.md` bajo
    # `vault/wiki/`». Dos exenciones ESTRUCTURALES, de la misma forma que `## Huecos` (D-34) y el
    # blockquote (#387), y del mismo tamaño: medido replayando los cuatro commits de una corrección
    # real, **130 de 150** líneas caían fuera de la prosa —122 en el hermano, 8 en la bitácora— y
    # la precisión de la categoría pasaba de 2/20 a 2/150, que es la definición de la categoría que
    # se deja de mirar.
    #   · el hermano `.verif.md` **no lleva prosa nueva**: sus filas son el EXTRACTO de afirmaciones
    #     que ya están en la nota, y el re-anclaje (#407) las reescribe TODAS en cada ronda — así
    #     que cada ronda inundaba esto con texto que nadie escribió, y contado dos veces. Un hermano
    #     no es una nota (#344), y `cfg.note_paths` lo saca de todo enumerador por eso mismo.
    #   · `log.md` es la bitácora: ahí una negativa es narración de la operación, no una afirmación
    #     de la bóveda (#391 la trata aparte por lo mismo).
    diff = {f: v for f, v in todo.items()
            if not cfg.is_verif_sidecar(f) and f != cfg.LOG}
    n_exentas = sum(len(v) for f, v in todo.items() if f not in diff)
    if not diff:
        # ⛔ El veredicto es el mismo (no evaluado) y el MOTIVO no: «no agregaste nada» y «lo que
        # agregaste lo sacó el filtro» piden cosas distintas —la segunda dice que la corrección
        # tocó sólo el hermano y la bitácora, que es información—, y el conteo ya está calculado.
        # Un mensaje que afirma algo falso sobre el disco es el defecto que este repo persigue,
        # aunque el rc esté bien.
        cfg.print_seguro(
            f"⛔ no evaluado: el diff contra `{ref}` " + (
                f"agrega {n_exentas} línea(s) bajo `vault/wiki/` y las SALTEA todas por estructura "
                f"(hermano `.verif.md` y `log.md`): no hay prosa de nota que mirar"
                if n_exentas else
                "no agrega ni una línea bajo `vault/wiki/` — no hay corrección que mirar")
            + " (no es un verde)")
        return 2
    negativas: list = []
    roles: list = []
    citas: list = []
    bloqueantes = 0
    for nota, agregadas in sorted(diff.items()):
        seccion = ""
        for i, linea in enumerate(nota.read_text(encoding="utf-8").split("\n"), 1):
            if linea.startswith("## "):
                seccion = linea[3:].strip()
            if i not in agregadas:
                continue
            txt = agregadas[i]
            if (m := NEGATIVA_RE.search(txt)) and not seccion.startswith("Huecos") \
                    and not txt.lstrip().startswith(">"):
                negativas.append((nota, i, m.group(0), txt.strip()[:90]))
            for bib, rol in _row_role_claims(txt):
                f = cfg.PAPERS / f"{cfg.note_stem(bib)}.md"
                if not f.exists():
                    continue
                declarado = (cfg.split_fm(f.read_text(encoding="utf-8")) or {}).get("role") or []
                if cfg.method_key(rol) not in {cfg.method_key(x) for x in declarado}:
                    roles.append((nota, i, bib, rol, ", ".join(declarado) or "(vacío)"))
        r = validar(nota, mostrar=False)
        for ln, motivo in r["alteradas"]:
            if ln in agregadas:
                citas.append((nota, ln, "⛔ " + motivo))
                bloqueantes += 1
        for ln, motivo, marca in r["discrepan"]:
            if ln in agregadas:
                citas.append((nota, ln, f"⚠ {motivo}\n     → {marca}"))

    for titulo, filas, fmt in (
            ("Afirmación negativa o superlativa AGREGADA (backlog: ¿está acotada?)", negativas,
             lambda x: f"L{x[1]}: «{x[2]}» — {x[3]}"),
            ("`role` AGREGADO que el paper no declara (backlog)", roles,
             lambda x: f"L{x[1]}: la fila le pone `{x[3]}` a [[{x[2]}]], que declara {x[4]}"),
            ("Cita AGREGADA contra la extracción de su fuente (#333 acotado al diff)", citas,
             lambda x: f"L{x[1]}: {x[2]}")):
        cfg.print_seguro(f"\n## {titulo} ({len(filas)})")
        actual = None
        for x in filas:
            if x[0] != actual:
                actual = x[0]
                cfg.print_seguro(f"\n{actual.relative_to(cfg.ROOT)}")
            cfg.print_seguro(f"  {fmt(x)}")
    n_lineas = sum(len(v) for v in diff.values())
    cfg.print_seguro(f"\n> sobre {n_lineas} línea(s) agregada(s) en {len(diff)} nota(s), contra "
                     f"`{ref}`"
                     + (f" · {n_exentas} salteada(s) por estructura: el hermano `.verif.md` "
                        f"(extracto re-anclado, no prosa nueva) y `log.md` (bitácora)"
                        if n_exentas else ""))
    cfg.print_seguro("  ⚠ Lo que ESTE paso NO mira: la condición o el localizador que se cae al "
                     "transcribir (7 de los 14 defectos medidos). No son decidibles sin abrir la "
                     "fuente y siguen donde estaban: en la verificación a ciegas (#203/#282).")
    return bloqueantes


def validar_todo(slug: str | None = None) -> int:
    """Sweep mode: every note of the vault (or of one subject) against its extractions (#323).

    ⛔ **The capability existed and nobody ran it.** `--validar` took one note at a time and no
    skill named it, so it only ran if somebody remembered — which is the definition of a control
    that does not exist. Measured: the note that produced #314–#318 closed with a full
    `verify-citations`, `lint --cierre` at 0 and **12 altered or misattributed quotes inside**; the
    comparison that caught them in seconds was written and never run.

    Declares its population (INV-40), what it could not evaluate (D-43), what it approved with
    a single witness (#341), where the OTHER reading of the same PDF contradicts it (#333) and what
    the `log` declared and resolved with the mark of #238 (#386) —
    without `--migrate-extracciones` that population is **zero**, and a silent zero would read as a
    verdict. Returns the number of blocking findings, so it works as a gate: none of the three extra
    counts moves it."""
    notas = _notes_of(slug)
    alteradas = no_eval = citas = solo_ext = resueltas = 0
    pag = {"pag_total": 0, "pag_ok": 0, "pag_no_eval": 0, "pag_sin_cita": 0}
    pag_mal: list = []
    discrepan: list = []
    for f in notas:
        r = validar(f, mostrar=False)
        for k in pag:
            pag[k] += r[k]
        pag_mal += [(f, ln, m) for ln, m in r["pag_mal"]]
        citas += r["citas"]
        no_eval += len(r["no_evaluables"])
        solo_ext += r["solo_extraccion"]
        resueltas += len(r["resueltas"])
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
    for f, ln, motivo in pag_mal:  # ⚠ localizador que no es la página de la cita (#492)
        cfg.print_seguro(f"\n{f.relative_to(cfg.ROOT)}\n  ⚠ L{ln}: {motivo}")
    ambito = f"las notas de `{slug}`" if slug else "toda la bóveda"
    cfg.print_seguro(f"\n> sobre {len(notas)} nota(s) de {ambito} · {citas} cita(s) «…» · "
                     f"{no_eval} no evaluable(s) (sin extracción en disco, o la extracción calla) · "
                     f"{solo_ext} sólo respaldada(s) por la extracción, "
                     f"{len(discrepan)} de ellas con el `.txt` en contra"
                     + (f" · {resueltas} declarada(s) y resuelta(s): en el `log` (#386/#387) o "
                        f"firmada(s) `cita_revisada` (#516)"
                        if resueltas else ""))
    if not citas:
        cfg.print_seguro("  ⚠ NO EVALUADO: ninguna cita mirada. Si la bóveda es anterior a #311, "
                         "corré `python scripts/make_notes.py --migrate-extracciones` — un cero sin "
                         "denominador se lee como veredicto (D-43)")
    cfg.print_seguro(f"  {alteradas} cita(s) con evidencia POSITIVA de alteración"
                     + (" ✅" if not alteradas else " ⛔ — corregilas contra el JSON de extracción, "
                        "no contra el `.txt`"))
    cfg.print_seguro(
        f"  > localizadores de página: {pag['pag_total']} · {pag['pag_ok']} en la página que "
        f"dicen · {len(pag_mal)} MAL · {pag['pag_no_eval']} no evaluable(s) (sin `.txt`, la cita "
        f"no está en él, atribución ambigua, o el localizador no coincide con ninguna numeración "
        f"derivable) · "
        f"{pag['pag_sin_cita']} FUERA DE ALCANCE (sin cita textual adyacente con la que ubicarlos)"
        + ("" if pag["pag_total"] else " — NO EVALUADO: ninguna cita lleva localizador"))
    if pag_mal:
        cfg.print_seguro(f"  ⚠ {len(pag_mal)} localizador(es) apuntan a otra página. No mueve el rc "
                         f"—la población es la más grande de la bóveda y un falso positivo acá "
                         f"frena operaciones (#323)— y sí se corrige: es lo que hace encontrable la "
                         f"afirmación en el PDF de disco (#492/#500)")
    if not slug:
        # #386 — sólo la pasada GLOBAL cuenta como pasada: con slug se miró un rincón.
        save_ultima_pasada_citas({"notas": len(notas), "citas": citas, "no_evaluables": no_eval,
                                  "solo_extraccion": solo_ext, "discrepan": len(discrepan),
                                  "resueltas": resueltas, "localizadores": pag["pag_total"],
                                  "pagina_ok": pag["pag_ok"], "pagina_mal": len(pag_mal),
                                  "pagina_no_evaluables": pag["pag_no_eval"],
                                  "pagina_sin_cita": pag["pag_sin_cita"]}, alteradas)
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
    ap.add_argument("--cita", action="store_true",
                    help="fragmento pegable en PROSA: «valor» (loc) [[bibcode]], con las comillas "
                         "del extractor y el bibcode PEGADO (#385)")
    ap.add_argument("--incluir-dropeados", action="store_true",
                    help="mostrar TAMBIÉN las extracciones de los papers que `--drop-core` sacó del "
                         "sujeto (#329). Por default no entran al 3b: son curación declarada, y "
                         "cada una sale con su banner para que no se mezclen con el material")
    ap.add_argument("--validar", metavar="NOTA",
                    help="cruza esa nota contra las extracciones: la cita que aparece bajo OTRO "
                         "bibcode, o cuya cola diverge, se alteró al sintetizar (#317/#321)")
    ap.add_argument("--preflight", nargs="?", const="HEAD", metavar="REF",
                    help="#490: chequea las líneas AGREGADAS bajo vault/wiki/ contra REF "
                         "(default HEAD), ANTES del fan-out")
    ap.add_argument("--validar-todo", action="store_true",
                    help="barrido: toda la bóveda, o las notas del sujeto si das el slug (#323)")
    args = ap.parse_args(list(argv) or None)

    if args.preflight:
        return preflight(args.preflight)
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
                 filas=args.filas, cita=args.cita,
                 incluir_dropeados=args.incluir_dropeados)
    cfg.print_seguro(f"\n  {n} valor(es) — el contraste es FILTRAR, no leer los JSON enteros. "
                     f"⛔ La cita se copia ENTERA o se parafrasea sin comillas.")
    return 0


if __name__ == "__main__":
    cfg.stdout_tolerante()
    cfg.cli_exit(main)
