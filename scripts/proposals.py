#!/usr/bin/env python3
"""The pending PROPOSALS of the vault, gathered in one place (#328).

WHY IT EXISTS, measured. While synthesising a theme, the extractor of an 824-page book answered:
*«the chapter on contrasts is ch. 3 and FastICA/negentropy live in ch. 6 — both OUTSIDE the declared
scope. Left in `hueco` as an explicit request to widen it.»* That is the most valuable output the
chain produces —**the system asking permission to grow**, with the motive written and without having
grown on its own (#241 forbids that, rightly)— and it lived inside the `hueco` field of one of 43
JSONs. Nobody sees it unless somebody happens to read the subagent's answer at the exact moment it
occurs, which is how this one was found.

⛔ **A proposal is not debt, and that is the whole point.** Debt is something missing that has to be
done, and the lint reports it well; a proposal is something the system suggests and that **needs
somebody to sign**. Two different queues: one gets scheduled, the other gets decided. And they age
differently — debt stays in the report until it is closed, while a proposal nobody reads **is lost**:
the JSON stays on disk but stops appearing anywhere anyone opens.

⚠ Each row carries the **verbatim motive** its author wrote, never a category: in six months what
helps is *«ch. 3 is Contrasts and the theme needs it»*, not *«scope widening»*. Same argument as the
mandatory `--reason` of the triage.

It REPORTS: it never widens a scope, drops a claim or edits a config — those are the decisions this
exists to surface. Exit is always 0: it is a surface, not a gate.

    python scripts/proposals.py                # toda la bóveda
    python scripts/proposals.py <slug>         # las de un sujeto
"""
from __future__ import annotations

import argparse
import json
import re
import sys

import lib_config as cfg
import lib_blocks as lb

#: #328 · lo que este barrido NO puede juntar, declarado (D-43). Un eje descubierto en el paso 3b
#: vive en la respuesta del agente y no toca el disco: decir «0 propuestas» sin nombrar esta ausencia
#: convertiría un hueco conocido en un veredicto.
NO_BARRIBLE = (
    ("ejes descubiertos en el paso 3b (#307/#310)",
     "viven en la conversación, no en disco — el agente los propone y los escribe el usuario en "
     "`themes.yaml`"),
)


def scope_requests(slug: str | None = None) -> tuple:
    """Requests to widen a source's `alcance`, as the extractor wrote them (#241/#328).

    `hueco` is where the prompt tells the extractor to leave what the declared scope kept it from
    reading: the framework refuses to widen the scope on its own, so the request has nowhere else to
    go.

    Returns `([(bibcode, subject, verbatim motive, context)], population, signed)` — every producer
    returns those three, and a row is four columns wide so the verbatim motive stays verbatim
    (#328) while the context —here, the scope in force— travels next to it. The population is the
    number of extractions actually read, because a `0` without a denominator does not tell «I
    looked at everything» from «there was nothing to look at» (INV-40).

    ⛔ #402 — three things this used to get wrong, and the first was a FALSE CLEAN with a declared
    population: (1) `hueco` is a **string** in the schema every extractor receives
    (`"hueco":""` in the prompt's output block) and this read it with `as_list`, which turns a
    scalar into `[]` — so the loop never ran and the screen printed a zero over 206 non-empty
    fields; (2) the prompt tells the extractor to leave the scope request in `salvedades`, which
    this never read; and (3) the population is **long sources** — the category is about widening
    the declared scope of a long source, and the gap field of an 11-page paper is a general-purpose
    field the prompt asks to fill always, not a request to widen anything. Counting those would
    list every extraction in the vault as a proposal, which is the noise that makes a category
    stop being read.

    So: population = extractions whose paper note declares `unidad_cita` other than `linea`; a
    request is any non-empty `hueco` (string, or list — both are tolerated on READ, never
    normalised on write) or any PROSE `salvedades` item (a string, or a map without `tipo`: the
    structured ones are decidable facts about the artefact, not requests).

    ⛔ #435 — the signature of this one lands in `alcance:` of `themes.yaml` (the authority, #312)
    and it is **free text**, so nobody can decide whether THIS request is the one that was granted.
    The row therefore carries the scope IN FORCE next to the request —which is what lets a person
    decide in one line— and `report` declares the cross as NOT decidable instead of showing a
    signed proposal as pending forever (D-43). The queue is not filtered on a guess: a filter that
    guesses wrong loses the request, and a request nobody reads is lost by definition (#328)."""
    out, poblacion = [], 0
    alcances = cfg.declared_scopes()
    dirs = [cfg.EXTRACCION / slug] if slug else sorted(
        d for d in (cfg.EXTRACCION.iterdir() if cfg.EXTRACCION.exists() else []) if d.is_dir())
    for d in dirs:
        for f in sorted(d.glob("*.json")) if d.exists() else []:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not is_long_source(f.stem):
                continue
            poblacion += 1
            alc = str((alcances.get(f.stem) or (None, None, None))[0] or "").strip()
            for texto in scope_request_texts(data):
                # ⚠ el motivo va VERBATIM (#328) y el alcance vigente viaja en su propia columna:
                # concatenarlo adentro rompería justo la propiedad que esta superficie promete.
                out.append((f.stem, d.name, texto,
                            f"alcance vigente: {alc or 'NO DECLARADO'}"))
    return out, poblacion, []


def is_long_source(bibcode: str) -> bool:
    """Does this paper's note declare it is cited by page/section, i.e. a LONG source (#80)?

    Read from the note's frontmatter, which is where `unidad_cita` lives (the extraction JSON does
    not carry it). A missing note or `linea` (the default) is «not long»."""
    nota = cfg.PAPERS / f"{cfg.note_stem(bibcode)}.md"
    if not nota.exists():
        return False
    fm = cfg.split_fm(nota.read_text(encoding="utf-8")) or {}
    unidad = str(fm.get("unidad_cita") or "").strip()
    return bool(unidad) and unidad != "linea"


def scope_request_texts(data: dict) -> list:
    """The verbatim requests one extraction JSON carries: its `hueco` and its prose `salvedades`.

    `hueco` may arrive as a string (the schema) or a list (tolerated); a `salvedades` item is
    prose when it is a string or a map with no `tipo` — the structured ones (`SALVEDAD_TIPOS`) are
    decidable facts about the artefact, which the harvester checks, not requests to a person."""
    textos: list = []
    hueco = data.get("hueco")
    for h in (hueco if isinstance(hueco, list) else [hueco]):
        texto = h if isinstance(h, str) else str(h.get("hueco") or "") if isinstance(h, dict) else ""
        if texto.strip():
            textos.append(texto.strip())
    for s in cfg.as_list(data.get("salvedades")):
        if isinstance(s, str) and s.strip():
            textos.append(s.strip())
        elif isinstance(s, dict) and not s.get("tipo") and str(s.get("nota") or "").strip():
            textos.append(str(s["nota"]).strip())
    return textos


def refutations(slug: str | None = None) -> tuple:
    """Claims a READING retracted (`vistas[].refuta`, #212) — the one channel that runs backwards.

    `stars`/`thesis_links` are seeded **before** reading and `harvest_views` merges add-only, so a
    false claim used to be unfalsifiable by the reading itself. The harvester records it and
    **proposes**; applying it would be an LLM editing curation in silence. Returns
    `(pending, population, signed)`, the population being the paper notes read.

    ⛔ #435 — the signature lands in `decisiones` of the SUBJECT's registro (that is what
    `triage --drop-core` writes) and the artefact this reads is versioned and, by #311, not
    regenerable: `refuta` cannot be taken out without re-paying the reading, and `harvest_views`
    merges add-only. So without this cross the proposal was **permanent** — measured on a real
    vault, 60 of its 62 proposals were, and the case that found it had been signed and still
    printed the same `→` that had already been run.

    The cross is `cfg.dropped_from_subject`, the canonical implementation of the `sujeto` rail, and
    it needs `cfg.subject_slug` because a claim carries the NAME (`refuta: ["GJ 581"]`) while the
    registro is keyed by slug (`gj_581`). A subject whose name resolves to nothing stays PENDING —
    an unresolvable claim is not a signed one."""
    out, firmadas, poblacion = [], [], 0
    for f in cfg.note_paths(cfg.PAPERS):
        poblacion += 1
        fm = cfg.split_fm(f.read_text(encoding="utf-8")) or {}
        for v in cfg.as_list(fm.get("vistas")):
            if not isinstance(v, dict):
                continue
            for suj in cfg.as_list(v.get("refuta")):
                s_slug = cfg.subject_slug(str(suj))
                if slug and suj != slug and s_slug != slug:
                    continue
                firma = dropped_signature(s_slug, f.stem) if s_slug else None
                if firma is not None:
                    firmadas.append((f.stem, str(suj),
                                     f"ya descartado de `{s_slug}`: {firma}", ""))
                else:
                    out.append((f.stem, str(suj),
                                str(v.get("motivo") or v.get("enfasis") or ""), ""))
    return out, poblacion, firmadas


def dropped_signature(slug: str, bibcode: str) -> str | None:
    """The motive with which `--drop-core` signed the pair `(bibcode, slug)`, or `None` (#435).

    `cfg.dropped_from_subject` is the canonical implementation of the `sujeto` rail (#112) — this
    only adds the tolerance this surface needs: an **unreadable** registro leaves the proposal
    PENDING instead of reading as «nobody signed». That is the safe direction here (the proposal
    stays visible, which is the whole point of #328) and it is not silent anywhere else: the lint
    blocks the unreadable registro as a finding of its own (AUD-131/INV-139)."""
    try:
        return cfg.dropped_from_subject(slug).get(bibcode)
    except cfg.UnreadableRegistro:
        return None


#: #328 · una celda vacía del inventario **es** una query: el eje existe y esa fuente no lo dice.
_VACIA = re.compile(r"^[\s\-–—.·]*$")


def empty_axis_cells(slug: str | None = None) -> tuple:
    """Empty cells of a `## Inventario por eje`: the next search, written down (#310 §4).

    The contrast table has one row per paper for each axis where the papers DISAGREE, so a cell with
    nothing in it is not a formatting defect: it says *this source has not been asked about this
    axis*. Returns `(rows, population, signed)` — `signed` is always empty **and that is the point**
    (#435): this is the one producer that reads the NOTE, so the proposal disappears on its own when
    the cell gets filled. It is the counterexample that shows what a closable proposal looks like."""
    out, poblacion = [], 0
    notas = [p for p in cfg.note_paths(cfg.STARS)
             + cfg.note_paths(cfg.CONCEPTS, "*/*.md")
             if not slug or p.stem == slug]
    for f in sorted(notas):
        texto = f.read_text(encoding="utf-8")
        corte = cfg.section_start(texto, "## Inventario por eje")
        if corte < 0:                    # `section_start` devuelve -1, no None
            continue
        poblacion += 1
        cuerpo = []
        for ln in texto[corte:].split("\n")[1:]:
            if ln.startswith("## "):
                break                    # hasta el próximo encabezado de nivel 2
            cuerpo.append(ln)
        for ln in cuerpo:
            if not ln.lstrip().startswith("|"):
                continue
            celdas = lb.split_row(ln)
            if len(celdas) < 3 or set(celdas[0]) <= set("-: ") or celdas[0].lower() == "eje":
                continue
            if any(_VACIA.match(c) for c in celdas[1:]):
                out.append((f.stem, celdas[0], celdas[1], ""))
    return out, poblacion, []


#: #435 · DÓNDE aterriza la firma de cada categoría, y si el barrido puede cruzarla. Los tres
#: estados de D-43, porque las dos formas de no poder cerrarse piden cosas opuestas: una se arregla
#: cruzando (y se cruzó), la otra sólo se puede DECLARAR — y mostrarlas iguales es lo que dejó 60 de
#: 62 propuestas permanentes en una bóveda real.
FIRMA_CRUZADA = "cruzada"
FIRMA_NO_CRUZABLE = "no cruzable"
FIRMA_SE_CIERRA_SOLA = "se cierra sola"


def report(slug: str | None = None) -> int:
    """Print every pending proposal with its verbatim motive, and DECLARE what it could not sweep."""
    #  @inv INV-147
    ambito = f"`{slug}`" if slug else "toda la bóveda"
    cfg.print_seguro(f"# Propuestas pendientes — {ambito}\n")
    total = 0
    for titulo, (filas, poblacion, firmadas), unidad, como, firma in (
        ("📐 Ampliar el `alcance` de una fuente larga (#241)", scope_requests(slug), "extracciones",
         "editá `sources[].alcance` en `themes.yaml` y corré `make_notes.py --restamp-alcance`",
         (FIRMA_NO_CRUZABLE, "la firma es el `alcance` de `themes.yaml` (#312) y es TEXTO LIBRE: "
                             "nadie puede decidir si ESTE pedido es el que se concedió. Cada fila "
                             "trae el alcance vigente al lado para que lo decidas en una línea")),
        ("↩ La lectura REFUTA el reclamo que la trajo (#212)", refutations(slug), "notas de paper",
         "`triage.py <slug> --drop-core <bibcode> --reason \"<motivo>\"`",
         (FIRMA_CRUZADA, "`decisiones` del registro del sujeto, carril `sujeto` (#112)")),
        ("🔍 Celda vacía del `## Inventario por eje` = la próxima query (#310)",
         empty_axis_cells(slug), "notas con inventario",
         "buscá ese eje en esa fuente, o declaralo hueco",
         (FIRMA_SE_CIERRA_SOLA, "lee la NOTA: la celda llena desaparece de la tabla")),
    ):
        estado, porque = firma
        cfg.print_seguro(f"## {titulo} — {len(filas)}")
        cfg.print_seguro(f"  > sobre {poblacion} {unidad} · firma: {estado} — {porque}")
        for a, b, motivo, contexto in filas:
            cfg.print_seguro(f"  · {a} · {b}" + (f" — «{motivo}»" if motivo else "")
                             + (f" · {contexto}" if contexto else ""))
        cfg.print_seguro(f"  → {como}\n" if filas else "  (ninguna)\n")
        # AUD-207 — lo FIRMADO se lista aparte y no se mezcla con la deuda real, igual que el
        # «considerado y rechazado» del lint. No se silencia: sin esto, la propuesta ya decidida
        # seguía en pantalla con el mismo `→` que alguien ya corrió.
        if firmadas:
            cfg.print_seguro(f"  ✓ {len(firmadas)} ya FIRMADA(s) — visible, no espera nada:")
            for a, b, por, _ctx in firmadas:
                cfg.print_seguro(f"      {a} · {b} — {por}")
            cfg.print_seguro("")
        total += len(filas)
    cfg.print_seguro("## ⚠ NO BARRIBLE — se declara, no se cuenta como cero (D-43)")
    for que, porque in NO_BARRIBLE:
        cfg.print_seguro(f"  · {que}: {porque}")
    cfg.print_seguro(f"\n> {total} propuesta(s) esperando una decisión. ⛔ Esto NO es la deuda del "
                     f"lint: una propuesta necesita que alguien **firme**, no que alguien la agende.")
    return total


def main(argv=()) -> int:
    """CLI: lista las propuestas pendientes de la bóveda (o de un sujeto). Siempre sale 0."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug", nargs="?", help="acotar a un sujeto")
    # `argv` por defecto VACÍO, no `sys.argv`: un test que llama `main([])` leería los argumentos de
    # **pytest** (el mismo cuidado que documenta `lint.main`). El `__main__` pasa los reales.
    args = ap.parse_args(list(argv))
    report(args.slug)
    return 0


if __name__ == "__main__":
    cfg.stdout_tolerante()
    cfg.cli_exit(lambda: main(sys.argv[1:]))
