"""Write a note's `<nota>.verif.md` sibling from a finished verify fan-out (#403).

    python scripts/write_verif_sidecar.py <nota.md> --from build/<slug>/verif/<ronda> [--fecha AAAA-MM-DD] [--dry-run]
    python scripts/write_verif_sidecar.py [<nota.md> | --todo] --restamp-section    # #430

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
     agent already wrote after it.

It does NOT judge: the verdicts are the fan-out's. And it does not write the three sub-sections'
free text: that is the round's triage, which only the agent that read the sources can write — the
placeholder it leaves is visible on purpose.

⛔ **Preserving that triage is a READING, and it is done normalised (#430).** The sub-section line
is matched with markdown adornment, a parenthetical after the name and the spacing folded, and its
count fragment is recognised through the SAME template that writes it (`subsection_fragment_re`).
Compared raw, an adorned sub-section came back empty and the placeholder was stamped **over** the
only record of what the round decided — measured on a real vault: 10 sub-sections in 4 notes, and 2
already publishing two contradictory counts on one line. Two nets of #222 close it, and the second
exists because the first was not enough: per sub-section, prose that goes in cannot come out empty;
and **per SECTION** (`_lost_prose`), nothing anybody typed in there disappears without this refusing
and naming it — measured writing this fix, a sub-section name in a different case, or a paragraph
the template does not contemplate, evaporated **with the first guard watching**, because that one
goes through the reader and only ever sees what the reader recognises.

`--restamp-section` is the migration half: it re-stamps the note's section from the sibling that
already exists, with no fan-out, keeping the block's date and the table byte for byte.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
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
    # #407/#282 — la fila previa de cada par se resuelve como `reverify_subset`: ancla exacta
    # primero, cobertura del extracto después, NUNCA cruzando `bibcode`. Es lo que permite que una
    # ronda ACOTADA deje a los pares de afuera con su veredicto y el ancla recalculada.
    asignado = lb.match_rows_to_pairs(pares, previous or [])[0] if previous else {}
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
        previa = asignado.get(p, (None, 0.0))[0]
        if par is None:
            if previa is None:
                continue                      # sin veredicto ni fila que llevar: «sin verificar»
            # fuera del alcance de esta ronda: el veredicto se LLEVA y el ancla se recalcula (#257)
            n += 1
            rows.append(lb.Row(n=str(n), claim=lb.truncate_claim(lb.normalize_ws(p.block.text)),
                               bibcode=p.bibcode, verdict=previa.verdict, anchor=p.anchor,
                               source_hash=previa.source_hash, condition=previa.condition,
                               source_kind=previa.source_kind, evidence=previa.evidence))
            continue
        n += 1
        veredicto = str(par["veredicto"]).strip()
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
        texto = free_text_of(vieja, sub)
        # #430/#222 — la red barata: si la línea vieja llevaba algo y el lector volvió con las manos
        # vacías, no se escribe. Un triage que desaparece no puede pasar en silencio: es el único
        # registro de qué se decidió en la ronda, y la pérdida es invisible en el diff siguiente.
        if not texto and (residual := _residual_prose(vieja, sub)):
            raise SidecarError(
                f"la prosa de «{sub}» se perdería: la línea lleva texto que el lector no reconoció "
                f"como triage — «{residual[:120]}». No se escribe nada. Revisá la forma de esa "
                f"sub-sección en la nota (el nombre, su fragmento de conteo) o reportá el caso")
        lineas.append(f"{sub} {frag}: {texto or PENDIENTE}" if frag
                      else f"{sub}: {texto or PENDIENTE}")
        lineas.append("")
    return "\n".join(lineas).rstrip() + "\n"


def free_text_of(seccion: str, sub: str) -> str:
    """What the agent wrote after the count fragment of one sub-section, or `""` (#280/#430).

    ⛔ The generated fragment carries colons of its own («— 0 con condición: 0 `acota` …»), so
    splitting on the FIRST `:` re-captures half the fragment and the line grows on every run.
    #430 — and the line is read NORMALISED (`lb.subsection_split`), which is what makes an adorned
    or parenthesised sub-section name still be recognised as its own; comparing the raw line
    returned `""` and the caller wrote the placeholder on top of the round's triage."""
    for ln in seccion.split("\n"):
        es_esta, prosa = lb.subsection_split(ln.strip(), sub)
        if es_esta:
            return prosa
    return ""


def _residual_prose(seccion: str, sub: str) -> str:
    """What the sub-section's line carried besides its name, fragment and placeholder (#430/#222).

    The cheap net: the writer cannot tell «the agent wrote no triage» from «the reader failed to
    recognise it», and only the second destroys something. `lb.subsection_residual` answers it
    without going through the reader, so a reader that stops recognising a form makes the writer
    REFUSE instead of stamping the placeholder over the round's triage."""
    for ln in seccion.split("\n"):
        resto = lb.subsection_residual(ln.strip(), sub)
        if resto:
            return resto.replace(lb._plain_line(PENDIENTE), " ").strip(" .:—-").strip()
    return ""


#: Debajo de esto el residuo de una línea no es prosa de nadie: signos sueltos que quedan al pelar
#: lo estampado. ⚠ Bajo a propósito — **«ninguna» tiene 7 caracteres** y es la respuesta de triage
#: más común de las tres sub-secciones, así que un umbral cómodo descarta en silencio justo el caso
#: frecuente. Es más barato rehusar de más (se mira una línea) que perder un triage.
_NO_ES_PROSA = 3


def _lost_prose(vieja: str, nueva: str) -> list:
    """Content lines of the old section that the new one does not carry (#430/#222).

    The net that does NOT go through the reader, and the reason it has to exist: the per-sub-section
    guard only sees what the reader recognises, so a line whose NAME is misspelled —or a paragraph
    the agent wrote that the template does not contemplate— evaporated with the guard watching.
    Measured writing this, on the very fix for #430.

    Everything generated is stripped before comparing (the header, the intro, the pointer, each
    sub-section's count fragment and the placeholder), because those legitimately change on every
    run; what is left is what somebody typed, and it has to still be there. Same shape as #222's
    cheap net —count before and after, refuse if it dropped— one level up from the pairs."""
    def _contenido(linea: str) -> str:
        """What somebody TYPED on this line: everything the script re-stamps, removed."""
        s = lb._plain_line(linea)
        # la línea de cabecera es ENTERA generada (`verif_summary`): sus conteos cambian en cada
        # corrida a propósito, así que no es prosa de nadie y compararla daría un falso positivo
        # en toda ronda que mueva un número — que es el caso normal.
        if s.startswith(lb._plain_line(INTRO)):
            return ""
        # la sub-sección que el lector SÍ reconoce se pela con el mismo lector (nombre, paréntesis
        # aclaratorio y fragmento afuera: los tres los re-escribe el script); la que no reconoce
        # entra entera, y ésa es justamente la que esta red existe para ver.
        for sub in lb.VERIF_SUBSECCIONES:
            if lb.subsection_split(linea, sub)[0]:
                s = lb.subsection_residual(linea, sub)
                break
        s = s.replace(lb._plain_line(PENDIENTE), " ")
        return re.sub(r"\s+", " ", s).strip(" .:—-()")

    nueva_plana = " ".join(_contenido(ln) for ln in nueva.split("\n"))
    perdidas = []
    for ln in vieja.split("\n"):
        s = ln.strip()
        if s.startswith(("#", ">", "|")):       # encabezado, puntero y tabla: los estampa el script
            continue
        c = _contenido(s)
        if len(c) >= _NO_ES_PROSA and c not in nueva_plana:
            perdidas.append(c)
    return perdidas


def emit(note: Path, text: str, rows: list, fecha: str, *, dry_run: bool = False,
         solo_seccion: bool = False) -> None:
    """Render the sibling and the note's section from `rows`, and (unless `dry_run`) write them.

    The single writing point of this module — every mode that produces rows goes through here, so
    the round-trip guard (#284), the header line (INV-81) and the triage guard (#430) apply to all
    of them and cannot be forgotten by a mode added later. `solo_seccion` keeps the sibling
    untouched: that is the re-stamping mode, which reads the rows FROM the sibling."""
    seccion = note_section(note, text, rows, fecha)            # #430: rehúsa antes de escribir nada
    vieja = lb.verif_section(text)
    if perdida := _lost_prose(vieja, seccion):
        raise SidecarError(
            "prosa de la sección vieja que se perdería al re-escribirla — no se escribe nada:\n  "
            + "\n  ".join(f"«{x[:120]}»" for x in perdida)
            + "\n  Si es triage, ponelo en una de las tres sub-secciones "
              f"({', '.join(lb.VERIF_SUBSECCIONES)}); si no lo es, no va en esta sección "
              "(la re-escribe el script en cada corrida)")
    nuevo = text.replace(vieja, seccion, 1) if vieja else text.rstrip("\n") + "\n\n" + seccion
    hermano = None if solo_seccion else lb.render_verif_sidecar(
        note, lb.render_verif_table(rows))                     # #284: round-trip o rehúsa
    if dry_run:
        return
    if hermano is not None:
        cfg.write_text_atomic(cfg.verif_sidecar(note), hermano)
    cfg.write_text_atomic(note, nuevo)


def restamp_section(note: Path, fecha: str | None = None, dry_run: bool = False) -> dict:
    """Re-stamp the NOTE's `## Verificación de citas` section from its existing sibling (#430).

    The migrator half. It needs no fan-out —the rows are already written— and touches only the
    note: the sibling's table, with its anchors and source hashes, is left byte for byte. Two
    things it repairs on the inherited corpus: the count fragment a previous run duplicated (one is
    rendered, and the prose kept is the one after the LAST fragment) and the sub-section whose
    adorned name made the placeholder land on top of the triage — that one now refuses instead.

    ⚠ The block's date is PRESERVED (`cfg.verification_date`): re-stamping is not re-verifying, and
    moving the date forward would make untouched pairs read as freshly checked (D-4, and the same
    argument INV-82 makes for the three dates of a note's header)."""
    text = note.read_text(encoding="utf-8")
    rows = lb.verif_rows(note)
    if not rows:
        raise SidecarError(f"{note.name}: no hay hermano `.verif.md` con filas que leer — "
                           f"esta modalidad re-estampa la sección desde la tabla ya escrita")
    d = fecha or cfg.verification_date(text)[1]
    if not d:
        raise SidecarError(f"{note.name}: el bloque no declara fecha en su encabezado y no se pasó "
                           f"`--fecha`: re-fechar es una decisión, no un default")
    antes = text
    emit(note, text, rows, d, dry_run=dry_run, solo_seccion=True)
    return {"nota": note.name, "filas": len(rows), "fecha": d,
            "cambio": dry_run or note.read_text(encoding="utf-8") != antes}


def write(note: Path, fanout_dir: Path, fecha: str | None = None, dry_run: bool = False) -> dict:
    """Build and (unless `dry_run`) write the sibling and the note's section. Returns the counts."""
    text = note.read_text(encoding="utf-8")
    fanout = load_fanout(fanout_dir)
    previas = lb.verif_rows(note) if cfg.verif_sidecar(note).exists() else None
    rows = build_rows(note, text, fanout, previas)
    if not rows:
        raise SidecarError("el fan-out no juzgó ningún par del cuerpo: no hay tabla que escribir")
    emit(note, text, rows, fecha or dt.date.today().isoformat(), dry_run=dry_run)
    c = lb.verif_counts(rows)
    juzgados = sum(len(ps) for ps in fanout.values())
    return {"filas": len(rows), "pares_cuerpo": len(lb.pairs_of(text)), "juzgadas": juzgados,
            "arrastradas": len(rows) - juzgados,
            "encadenadas": c["cadenas"], "hermano": cfg.verif_sidecar(note).name}


def _main_restamp(args) -> int:
    """`--restamp-section` for one note or for the whole vault (#430).

    Declares its population (INV-40) and, on a sweep, does NOT stop at the first refusal: a note
    whose triage the reader cannot recognise is exactly the finding, and stopping would hide the
    rest of the corpus behind it. Every refusal is named; the exit code is non-zero if any."""
    if args.todo:
        # el universo se enumera por los HERMANOS: la modalidad lee las filas de ahí, así que una
        # nota sin hermano no tiene nada que re-estampar (y `note_paths` los excluye por #344)
        notas = sorted(s.with_name(s.name[:-len(cfg.VERIF_SUFFIX)] + ".md")
                       for s in cfg.WIKI.rglob("*" + cfg.VERIF_SUFFIX)) if cfg.WIKI.exists() else []
    elif args.nota:
        notas = [Path(args.nota)]
    else:
        cfg.print_seguro("⛔ `--restamp-section` necesita una nota o `--todo`")
        return 2
    cambiadas, fallas = 0, []
    for n in notas:
        if not n.exists() or cfg.is_verif_sidecar(n):
            fallas.append((n.name, "no es una nota"))
            continue
        try:
            r = restamp_section(n, fecha=args.fecha, dry_run=args.dry_run)
        except SidecarError as exc:
            fallas.append((n.name, str(exc)))
            continue
        cambiadas += bool(r["cambio"])
    verbo = "se re-estamparía(n)" if args.dry_run else "re-estampada(s)"
    cfg.print_seguro(f"{cambiadas} sección(es) {verbo} sobre {len(notas)} nota(s) con hermano")
    for nombre, motivo in fallas:
        cfg.print_seguro(f"⛔ {nombre}: {motivo}")
    return 1 if fallas else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("nota", nargs="?", help="la nota (`vault/wiki/.../<x>.md`)")
    ap.add_argument("--from", dest="fanout", default=None,
                    help="directorio de la ronda (p. ej. build/<slug>/verif/r1)")
    ap.add_argument("--restamp-section", action="store_true", dest="restamp",
                    help="#430: re-estampa la SECCIÓN de la nota desde su hermano (sin fan-out); "
                         "conserva la fecha del bloque y no toca la tabla")
    ap.add_argument("--todo", action="store_true",
                    help="con --restamp-section: barre toda la bóveda (notas con hermano)")
    ap.add_argument("--fecha", default=None, help="fecha del bloque (default: hoy)")
    ap.add_argument("--dry-run", action="store_true", help="no escribe: dice qué haría")
    args = ap.parse_args(argv)
    if args.restamp:
        return _main_restamp(args)
    if not args.nota or not args.fanout:
        cfg.print_seguro("⛔ hace falta la nota y `--from <dir>` (o `--restamp-section`)")
        return 2
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
                     f"par(es) del cuerpo — {r['juzgadas']} juzgada(s) en esta ronda"
                     + (f", {r['arrastradas']} arrastrada(s) re-ancladas de la anterior (#407)"
                        if r["arrastradas"] else "")
                     + (f", {r['encadenadas']} encadenada(s)" if r["encadenadas"] else "")
                     + f" — la cabecera de la nota la da `verif_summary`; las sub-secciones que "
                       f"digan «{PENDIENTE}» son el triage de la corrida: completalas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
