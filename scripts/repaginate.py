#!/usr/bin/env python3
"""Close the pagination debt of #436 by RE-READING the PDF — the package and its serial writer (#494).

WHY IT EXISTS. `replace_pdf` stamps `_paginacion` on an extraction whose PDF was swapped, because
`raw/extraccion/**` is versioned and not regenerable (#311): the quoted text stays right and **every
locator points at a document that is no longer on disk**. The lint reports it, `contrast --validar`
names it as the cause of a `MAL` locator — and no operation closed it. Measured on a real vault:
**68 extractions, 1653 `linea` values**, plus 64 of the 75 remaining bad locators living inside the
caveat blocks that `harvest_views` stamps FROM the JSON, where they cannot be fixed in the note.

⛔ **THE RULE, decided by the user on 2026-09-20: the debt is closed by re-reading the PDF, never by
copying the page the `.txt` deduces.** `quote_pages` (#492/#494) says where the quote falls and what
that page prints, and that is the **GUIDE of which page to open** — the `.txt` is a degraded index
(#205) and the extraction is a reading of the PDF (#311). It holds for any correction of a `linea`
in `raw/extraccion/`: what gets written is what somebody SAW in the PDF.

⛔ **And the guide cannot flow into the answer by any automatic path**, which is enforced by shape
and not by asking nicely:

1. the package (`_paquete.json`, with `guia`) and the result (`<bib>.json`, with `pagina` +
   `evidencia`) are different schemas, and `--apply` validates against `RESULT_SCHEMA`, so handing
   it the package back bounces;
2. `--apply` **never reads the package**: it recomputes the items from the extraction itself, so
   there is no code path from `guia` to `linea`;
3. every confirmed page travels with `evidencia` —words the reader saw on that sheet— and the
   writer crosses it against the `.txt` split by page with `quote_page_verdict`: whoever copied the
   guide without opening the PDF has nothing to put there;
4. `pagina: null` is written as `no hallado`, **never** as the guide.

⚠ The honest limit, stated so nobody reads more into it: that an LLM opened the PDF is unfalsifiable
from outside — the same nature as `verify-citations` (#205). What is guaranteed is that the guide
cannot be written automatically and that the answer carries a local witness to the sheet.

    python scripts/repaginate.py --list                              # la deuda, por fuente
    python scripts/repaginate.py <bibcode> --out build/repag/<bib>   # el paquete de relectura
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_config as cfg  # noqa: E402
import lib_blocks as lb  # noqa: E402

def open_extractions(bibcode: str) -> list:
    """`[(path, data)]` — EVERY open extraction of this bibcode, canonical and per-lens (#494).

    ⛔ Returned by the validator: the debt lives in the FILE and the package was keyed by bibcode,
    so a source with a second reading under another lens (`<bib>__<lens>.json`, #371/#308) handed
    over **only the first** —measured: 1542 of 2032 locators in one pass— and the per-lens
    extraction **could not be named** from the command line. An extraction's identity is the
    `bibcode` INSIDE it (#374) and its file is the unit of work: both at once, which is exactly
    what `extraction_identity` exists to keep apart."""
    return [(f, d) for f, d in pending() if cfg.extraction_identity(d) == bibcode
            or f.stem.split("__")[0] == cfg.note_stem(bibcode)]


def lens_of(path) -> str:
    """The lens of an extraction file (`<bib>__<lente>.json` → `lente`), `""` for the canonical one."""
    stem = pathlib.Path(path).stem if not isinstance(path, str) else path
    return stem.split("__", 1)[1] if "__" in stem else ""


def file_id(path) -> str:
    """`<slug>/<stem>` — what IDENTIFIES an extraction file (#494, devuelto por segunda vez).

    ⛔ The stem does not identify it: the same paper read under two subjects lives under two slugs
    (`gj_581/` and `hd_40307/`), and keying by stem made the two packages land in the same
    directory — measured on the real vault: 68 emitted, **52 on disk**, 1641 of 2032 locators. And
    worse than losing them, it did not CONVERGE: the writer kept the last of the glob and the
    applier took the first, so the surviving package's result bounced on the ids and re-emitting
    reproduced the collision. The lens (#371) is one half of the identity; the slug is the other,
    and only both together name a file."""
    f = pathlib.Path(path)
    return f"{f.parent.name}/{f.stem}"


#: #494 · lo que el lector devuelve, y NADA más. Es el contrato que separa el paquete del
#: resultado: el paquete lleva `guia` y `ruta`, el resultado `pagina` y `evidencia`, así que
#: devolver el paquete rebota en vez de escribirse.
RESULT_SCHEMA = {"bibcode": "<bibcode>",
                 "extraccion": "<el `extraccion` que traía el paquete: `<slug>/<stem>`>",
                 "pdf_sha": "<el sha10 que traía el paquete>",
                 "items": [{"id": "<el id del item, tal cual>",
                            "pagina": "<la página en la que está: la que muestra la hoja o el "
                                      "índice del PDF (#500); una LISTA con una página por "
                                      "numeración si el item trae varias (#533); o null>",
                            "evidencia": "<palabras que viste en ESA hoja, distintas del valor>",
                            "motivo": "<por qué no la hallaste — sólo si pagina es null>"}]}


def pending() -> list:
    """`[(path, data)]` — the extractions whose pagination debt is still OPEN (#494).

    The same six-line walk as the lint's category, and not its result, because the writer needs the
    PATH: `_extraction_index` keys by bibcode and drops where each one lives."""
    out = []
    for f in sorted(cfg.EXTRACCION.glob("*/*.json")) if cfg.EXTRACCION.exists() else []:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue                      # el JSON ilegible tiene su propio detector
        if isinstance(data, dict) and any(cfg.as_map(data.get(m))
                                          for m in cfg.PAGINATION_OPEN_MARKS):
            out.append((f, data))
    return out


def _strings(data: dict):
    """`(ruta, texto)` for every free-text field of an extraction that can carry a locator.

    ⛔ Enumerated and not walked blindly: a locator inside `bibcode` or inside a `methods` entry
    would be a false item, and an item the reader cannot place is worse than one that is missing —
    it sends somebody to a page for a string nobody wrote."""
    for i, g in enumerate(cfg.as_list(data.get("ground_truth"))):
        if isinstance(g, dict):
            yield f"ground_truth[{i}].linea", str(g.get("linea") or "")
    for k in ("aporte", "hueco", "conclusiones"):
        if isinstance(data.get(k), str):
            yield k, data[k]
    for k, v in (data.get("ejes") or {}).items() if isinstance(data.get("ejes"), dict) else ():
        if isinstance(v, str):
            yield f"ejes.{k}", v
    for i, sv in enumerate(cfg.as_list(data.get("salvedades"))):
        if isinstance(sv, str):
            yield f"salvedades[{i}]", sv
        elif isinstance(sv, dict):
            for k in ("evidencia", "nota"):
                if isinstance(sv.get(k), str):
                    yield f"salvedades[{i}].{k}", sv[k]


#: #533 · what may stand BETWEEN two numberings of the SAME page (`p. 288 (PDF p. 3)`,
#: `p. 13 [índice del PDF] (ms. p. 12)`): brackets, punctuation and the numbering's label. Prose
#: in between (`p. 4 y p. 7`) makes them distinct pages, not numberings.
_NUMBERING_GAP_RE = re.compile(r"^[\s()\[\],;:/=–-]*(?:(?:PDF|ms\.?|manuscrito|índice|del|hoja|"
                               r"sheet|impresa|printed)[\s()\[\],;:/=–-]*)*$", re.I)


def numbering_chain(texto: str, start: int) -> list:
    """`[(a, b)]` — the page-locator spans from `start` on that are NUMBERINGS of one page (#533):
    each next token is separated from the previous one only by a label (`_NUMBERING_GAP_RE`).

    ⛔ The unit of a locator is the chain, not its first token: replacing only the first of
    `p. 288 (PDF p. 3)` left the numbering that DID change stale and reported it rewritten
    (measured: 69 of 69 locators of three PDFs whose HAL cover was removed)."""
    spans = [(m.start(), m.end()) for m in cfg.PAGE_LOC_RE.finditer(texto) if m.start() >= start]
    chain = spans[:1]
    for a, b in spans[1:]:
        if not _NUMBERING_GAP_RE.match(texto[chain[-1][1]:a]):
            break
        chain.append((a, b))
    return chain


def page_answer(pagina) -> list | None:
    """The reader's `pagina` as a list of page labels, or `None` if its FORM is wrong (#533).

    A scalar is one numbering; a list, one per numbering in order. Each label must be what
    `PAGE_LOC_RE` reads after `p. ` — a number or a range, with its prefix (`L45`) — so a whole
    locator (`§3.2, p. 13 [índice del PDF]`) cannot be written as a page (measured: 11 of 11 items
    of one source came back that way and were written inside the old locator)."""
    paginas = pagina if isinstance(pagina, list) else [pagina]
    etiquetas = [str(p).strip() for p in paginas]
    ok = etiquetas and all((m := cfg.PAGE_LOC_RE.fullmatch(f"p. {e}")) and m.end() == len(e) + 3
                           for e in etiquetas)
    return etiquetas if ok else None


_QUOTE_SPAN_RE = re.compile(r"«[^«»]*»")


def loose_chains(texto: str) -> list:
    """`[[(a, b), …]]` — the locator chains of a free-text field that NO quote owns (#534): outside
    every «…» (verbatim source text is never rewritten) and not adjacent to any quote.

    ⛔ Before #534 only quote-adjacent locators were items, so `App. A (p. 33 …): …` or
    `«…» (§3.2, p. 14 …)` —a section between quote and number cuts the adjacency— were never
    re-read and the debt closed on them anyway: 6 stale of 75 in one measured round."""
    dentro = [(m.start(), m.end()) for m in _QUOTE_SPAN_RE.finditer(texto)]
    propios = set()
    for cita in cfg.quotes_in(texto):
        pos = texto.find(cita)
        for a, _b in cfg.adjacent_locators(texto, pos, pos + len(cita))[:1]:
            propios.update(numbering_chain(texto, a))
    chains, usados = [], set()
    for m in cfg.PAGE_LOC_RE.finditer(texto):
        sp = (m.start(), m.end())
        if sp in propios or sp in usados or any(a <= sp[0] < b for a, b in dentro):
            continue
        chain = numbering_chain(texto, sp[0])
        usados.update(chain)
        chains.append(chain)
    return chains


def items(data: dict) -> list:
    """`[{id, ruta, que, valor, cita, linea}]` — every locator of this extraction to be re-read.

    Two shapes, because the 64 of 75 locators that cannot be fixed in the note live in the second:
    the `linea` of a `ground_truth` row, and the `(p. N)` adjacent to a quote inside any free-text
    field. ⚠ One item per OCCURRENCE (`salvedades[1]#2`): a caveat that quotes two pages owes two
    answers, and collapsing them would silently close one."""
    out = []
    for ruta, texto in _strings(data):
        if ruta.endswith(".linea"):
            if cfg.page_locators(texto):
                i = int(ruta.split("[")[1].split("]")[0])
                fila = cfg.as_list(data.get("ground_truth"))[i]
                out.append({"id": ruta, "ruta": ruta, "que": str(fila.get("que") or ""),
                            "valor": str(fila.get("valor") or ""), "cita": "", "linea": texto,
                            # ⛔ #533 — un `linea` pide una página por CADA token: con varias
                            # ubicaciones (`p. 291 (PDF p. 5); resumen en p. 287 (PDF p. 2)`)
                            # reescribir la primera dejaba vieja la otra («colapsado», #494)
                            "numeraciones": [m.group(0) for m in cfg.PAGE_LOC_RE.finditer(texto)]})
            continue
        for n, cita in enumerate(cfg.quotes_in(texto), 1):
            loc = cfg.page_locators_after(texto, cita)
            if loc:
                pos = texto.find(cita)
                spans = cfg.adjacent_locators(texto, pos, pos + len(cita))
                out.append({"id": f"{ruta}#{n}", "ruta": ruta, "que": "", "valor": "",
                            "cita": cita, "linea": _loc_token(texto, cita),
                            "numeraciones": [texto[a:b] for a, b in
                                             numbering_chain(texto, spans[0][0])] if spans else []})
        # #534 — y cada localizador SUELTO, con su contexto para ubicarlo en la hoja
        for k, chain in enumerate(loose_chains(texto), 1):
            a, b = chain[0][0], chain[-1][1]
            out.append({"id": f"{ruta}@{k}", "ruta": ruta, "que": "", "cita": "",
                        "valor": texto[max(0, a - 120):a].strip(),
                        "linea": texto[a:b], "numeraciones": [texto[x:y] for x, y in chain]})
    return out


def _loc_token(texto: str, cita: str) -> str:
    """The locator EXACTLY as it is written after this quote — the string `--apply` has to replace."""
    pos = texto.find(cita)
    spans = cfg.adjacent_locators(texto, pos, pos + len(cita))
    return texto[spans[0][0]:spans[0][1]] if spans else ""


def guide(item: dict, bibcode: str) -> dict:
    """`{pagina, indice, motivo}` — where the `.txt` says to OPEN, never what to write (#494).

    The quote is what can be located; a `ground_truth` row is located by its `valor`, which is the
    transcription the extractor made of it. `motivo` carries why there is no guide (D-43): the guide
    missing is not the locator being wrong."""
    # ⛔ Primero la «cita» que el valor lleve adentro: una fila de `ground_truth` suele ser una
    # PARÁFRASIS del extractor —castellano, o LaTeX— que el `.txt` no puede ubicar por
    # construcción, y la cita textual que sí trae es lo único buscable. Medido sobre 33 filas de
    # una fuente real: 7 traen cita, las otras 26 no tienen nada que el índice pueda encontrar, y
    # eso NO es un defecto de la guía: es lo que la guía declara.
    texto = item.get("cita") or ""
    if not texto:
        citas = cfg.quotes_in(str(item.get("valor") or ""))
        texto = citas[0] if citas else str(item.get("valor") or "")
    if not texto.strip():
        return {"pagina": None, "indice": None, "motivo": "el item no trae cita ni valor que ubicar"}
    u = cfg.quote_pages(texto, bibcode)
    if u["motivo"]:
        return {"pagina": None, "indice": None, "motivo": u["motivo"]}
    return {"pagina": u["impresas"][0] if u["impresas"] else None,
            "indice": u["paginas"][0] if u["paginas"] else None,
            "motivo": None if u["impresas"] else
                      "el `.txt` ubica la cita pero esa página no imprime numeración derivable: "
                      "la guía es el ÍNDICE del PDF"}


class RoundError(Exception):
    """The package cannot be written, and the message names why."""


def write_rounds(bibcode: str, out_dir: Path) -> list:
    """One package PER open extraction file of this bibcode (#494, devuelto).

    Each lens gets its own directory (`<out_dir>/<stem>/`) because each is a separate reading with
    its own items: collapsing them into one package is what dropped 490 of 2032 locators.

    ⛔ AUD-421 — with no open extraction it REFUSES, naming the zero: an empty list went out rc 0
    and silent, the «0 nobody measured» of D-43 (a mistyped bibcode read as «nothing to do»)."""
    abiertas = open_extractions(bibcode)
    if not abiertas:
        raise RoundError(f"{bibcode}: 0 extracción(es) con deuda de paginación abierta "
                         f"({' | '.join(cfg.PAGINATION_OPEN_MARKS)}) — nada que releer")
    return [write_round(bibcode, out_dir / f.parent.name / f.stem, extraccion=f)
            for f, _d in abiertas]


def write_round(bibcode: str, out_dir: Path, *, extraccion=None) -> dict:
    """Write `prompt.md` + `_paquete.json` for one source. Refuses rather than guess.

    Three refusals, each closing a way of re-reading the wrong document: no open debt (there is
    nothing to close), no PDF on disk (there is nothing to read), and a PDF whose `pdf_sha` is not
    the one the mark recorded (it was replaced AGAIN, so the package would describe a third
    document)."""
    stem = cfg.note_stem(bibcode)
    abiertas = [(f, d) for f, d in open_extractions(bibcode)
                if extraccion is None or f == extraccion]
    if not abiertas:
        raise RoundError(f"{bibcode} no tiene deuda de paginación abierta "
                         f"({' | '.join(cfg.PAGINATION_OPEN_MARKS)})")
    slug = cfg.pdf_slug(stem)
    if not slug:
        raise RoundError(f"no hay PDF de {bibcode} en disco: la relectura es del PDF (#205), así "
                         f"que sin él no hay con qué cerrar la deuda")
    pdf = cfg.PDFS / slug / f"{stem}.pdf"
    sha = lb.sha10(pdf.read_bytes())
    f, data = abiertas[0]
    marca = next(cfg.as_map(data.get(m)) for m in cfg.PAGINATION_OPEN_MARKS if cfg.as_map(data.get(m)))
    if marca.get("pdf_sha") and marca["pdf_sha"] != sha:
        raise RoundError(f"el PDF en disco ({sha}) no es el que registró la marca "
                         f"({marca['pdf_sha']}): se reemplazó otra vez, y este paquete describiría "
                         f"un tercer documento")
    los = items(data)
    paquete = {"bibcode": bibcode, "extraccion": file_id(f), "lente": lens_of(f),
               "ruta": f.as_posix(), "pdf_sha": sha,
               "items": [{**it, "guia": guide(it, bibcode)} for it in los],
               "version": cfg.ALMAGESTO_VERSION}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "_paquete.json").write_text(json.dumps(paquete, ensure_ascii=False, indent=1) + "\n",
                                           encoding="utf-8")
    (out_dir / "prompt.md").write_text(prompt_for(paquete, pdf, out_dir), encoding="utf-8")
    return paquete


def prompt_for(paquete: dict, pdf: Path, out_dir: Path) -> str:
    """The prompt of ONE re-reader: the PDF, the convention, its items with their guide, the fence."""
    bib = paquete["bibcode"]
    partes = [f"# Repaginado por RELECTURA — fuente `{bib}` (#494)", "",
              f"El PDF de esta fuente se REEMPLAZÓ y su extracción quedó con los localizadores del "
              f"documento anterior. Abrí **`{pdf.as_posix()}`** y devolvé, para cada item, la "
              f"página en la que está — la que muestra la hoja, o el índice del PDF (#500).", "",
              f"⛔ **{cfg.REGLA_LOCALIZADOR}.**", "",
              "⛔ **La `guia` dice dónde ABRIR, no qué escribir.** Sale del `.txt`, que es un "
              "índice degradado (#205); la respuesta es lo que ves en la hoja. Si coinciden, "
              "mejor — pero la que vale es la tuya, y cada página confirmada vuelve con "
              "`evidencia`: palabras que viste en ESA hoja y que no son el valor del item.", "",
              "⛔ **Lo que no encontrás se declara**: `pagina: null` + `motivo`. Un hueco "
              "declarado es correcto; copiar la guía sin abrir el PDF, no.", "",
              "⛔ **`pagina` es un NÚMERO (o rango), no un localizador** (#533): `\"13\"`, "
              "`\"5-6\"`, `\"L45\"` — nunca `\"§3.2, p. 13\"`. Si el item trae varias numeraciones "
              "de la misma página (impresa, del PDF, del manuscrito), devolvé una LISTA con una "
              "por numeración, en el orden en que aparecen.", "",
              f"Items: {len(paquete['items'])}.", ""]
    for it in paquete["items"]:
        g = it["guia"]
        guia = (f"p. {g['pagina']}" if g["pagina"] else
                f"índice {g['indice']} del PDF" if g["indice"] else "sin guía")
        partes += [f"### `{it['id']}`", "",
                   f"- localizador actual (del documento VIEJO): `{it['linea']}`",
                   *([f"- ⛔ trae {len(it['numeraciones'])} numeraciones/páginas ("
                      + ", ".join(f"`{x}`" for x in it["numeraciones"])
                      + "): devolvé `pagina` como LISTA, una por cada una y en este orden (#533)"]
                     if len(it.get("numeraciones") or []) > 1 else []),
                   f"- guía del `.txt` (dónde abrir): {guia}"
                   + (f" — {g['motivo']}" if g["motivo"] else ""),
                   f"- qué dice: {it['cita'] or it['valor'] or it['que']}", ""]
    partes += ["## Salida", "",
               f"Escribí el resultado en `{(out_dir / f'{bib}.json').as_posix()}` con EXACTAMENTE "
               f"estas claves y NINGUNA OTRA:", "",
               "```json", json.dumps(RESULT_SCHEMA, ensure_ascii=False, indent=1), "```", ""]
    return "\n".join(partes)


class ApplyError(Exception):
    """The result file cannot be applied, and the message names why. Nothing is written."""


def _set_by_path(data: dict, ruta: str, nuevo: str) -> None:
    """Write `nuevo` at `ruta` (`ground_truth[0].linea`, `salvedades[1].evidencia`, `ejes.x`)."""
    obj, *resto = ruta.split(".")
    if "[" in obj:
        k, i = obj[:obj.index("[")], int(obj[obj.index("[") + 1:obj.index("]")])
        destino = cfg.as_list(data.get(k))[i]
    else:
        destino, resto = data, [obj] + resto
    if len(resto) == 1 and isinstance(destino, dict):
        destino[resto[0]] = nuevo
    elif not resto and isinstance(destino, str):
        cfg.as_list(data.get(obj[:obj.index("[")]))[int(obj[obj.index("[") + 1:obj.index("]")])] = nuevo
    else:                                   # `ejes.<k>`
        data.setdefault(resto[0], {})[resto[1]] = nuevo


def _replace_chain(texto: str, chain: list, reemplazos: list) -> str:
    """Write one replacement per locator span of `chain`, keeping every label and qualifier (#533)
    — and the token's own `p.`/`pp.` (#534: `pp. 12-13` came back as `p. 12-13`)."""
    for (a, b), r in sorted(zip(chain, reemplazos), reverse=True):
        prefijo = re.match(r"p{1,2}\.\s*", texto[a:b], re.I)
        # `pp.` sólo si lo nuevo sigue siendo un rango o una lista
        if prefijo and r.startswith("p. ") and prefijo.group(0).lower().startswith("pp") \
                and re.search(r"[-–,]|\by\b|\band\b", r[3:]):
            r = prefijo.group(0) + r[3:]
        texto = texto[:a] + r + texto[b:]
    return texto


def _replace_locator(texto: str, ocurrencia: int, viejo: str, nuevo) -> str | None:
    """Swap the locator ADJACENT to the `ocurrencia`-th quote of this string, or `None` if it moved.

    ⛔ Anchored on the quote and not on the token, because two quotes of one string can name the
    same page: counting `p. 3` would swap the wrong one. And it matches the token EXACTLY as the
    package read it, so a locator somebody already fixed by hand is reported, never rewritten —
    the same rule that protects a correction in `restamp_salvedades` (#453)."""
    desde = 0
    for n, cita in enumerate(cfg.quotes_in(texto), 1):
        pos = texto.find(cita, desde)
        if pos < 0:
            return None
        desde = pos + len(cita)
        if n != ocurrencia:
            continue
        spans = cfg.adjacent_locators(texto, pos, desde)
        if not spans or texto[spans[0][0]:spans[0][1]] != viejo:
            return None
        if isinstance(nuevo, list):                 # #533 — una por numeración
            return _replace_chain(texto, numbering_chain(texto, spans[0][0]), nuevo)
        a, b = spans[0]
        return texto[:a] + nuevo + texto[b:]
    return None


def _replace_line_locators(texto: str, reemplazos: list) -> str | None:
    """Swap EVERY locator of a `linea`, one replacement each, and keep the rest; `None` if the count
    no longer matches (somebody edited the field by hand).

    ⛔ Returned by the real repagination: the writer's first version overwrote the whole field, and
    with it the **qualifier** — `p. 4 (Tabla 2)` became `p. 491`, `p. 2056 (nota al pie de la Tabla
    1)` became `p. 2062`. Measured: **143 of 563**. The qualifier is what makes a locator usable —
    it says WHERE on the page the datum is — and it is re-derivable from nothing.

    ⛔ #533 — and EVERY locator, not the first: swapping one left the others naming pages of the
    replaced document (the «collapsed» case of #494, 765 of 5627, and the second numbering of
    `p. 288 (PDF p. 3)`, 69 of 69). A stale locator attributes wrongly, which is worse than none."""
    locs = [(m.start(), m.end()) for m in cfg.PAGE_LOC_RE.finditer(texto)]
    if not locs or len(locs) != len(reemplazos):
        return None
    return _replace_chain(texto, locs, reemplazos)


def _check_item(item: dict, res: dict, bibcode: str) -> str | None:
    """`None` if the answer can be written, or the reason it is REFUSED (#494).

    The guards are what make «the `.txt` is a guide, not an answer» enforceable: a page confirmed
    without `evidencia` is somebody copying the guide, an `evidencia` contained in the item's own
    value is not a witness of the sheet, and an `evidencia` the `.txt` places on ANOTHER page
    contradicts the answer. A refused item stays pending and gets named — never silently written."""
    pagina, ev = res.get("pagina"), str(res.get("evidencia") or "").strip()
    if pagina in (None, ""):
        return None if str(res.get("motivo") or "").strip() else \
            "`pagina: null` sin `motivo`: un hueco se declara, no se deja mudo (D-43)"
    paginas = page_answer(pagina)
    if paginas is None:
        return (f"`pagina: {pagina!r}` no es una página: tiene que ser un número o rango "
                f"(`\"13\"`, `\"5-6\"`, `\"L45\"`), o una lista de ellos — nunca el localizador (#533)")
    n_num = max(1, len(item.get("numeraciones") or []))
    if len(paginas) != n_num:
        return (f"el localizador trae {n_num} numeración(es)/página(s) "
                f"({', '.join(item.get('numeraciones') or [])}) y volvieron {len(paginas)}: con "
                f"menos, la que no volvió queda vieja (#533) — devolvé una por cada una, en orden")
    if not ev:
        return "página confirmada sin `evidencia`: sin testigo de la hoja no se distingue de copiar la guía"
    if ev.lower() in str(item.get("valor") or item.get("cita") or "").lower():
        return "la `evidencia` está contenida en el valor del item: no es testigo de la hoja"
    estado, det = cfg.quote_page_verdict(ev, bibcode, [(paginas[0], paginas[0])])
    if estado == "mal":
        return (f"el `.txt` ubica esa `evidencia` en otra página "
                f"({', '.join(map(str, det.get('impresas') or det.get('paginas') or []))}): "
                f"la respuesta se contradice con el índice")
    return None


def apply(bibcode: str, resultado: Path, dry_run: bool = False) -> dict:
    """Write the re-read pages back into the extraction, SERIALLY and with guards (#494).

    ⛔ It does NOT read the package: it recomputes the items from the extraction itself, so there is
    no code path by which the `.txt`'s guide reaches a `linea`. Handing it the package back bounces
    on the schema.

    The debt closes only when the whole extraction was re-read: a round that leaves items pending
    writes `_repaginado_parcial` with their ids, and the lint keeps counting it."""
    abiertas = open_extractions(bibcode)
    if not abiertas:
        raise ApplyError(f"{bibcode} no tiene deuda de paginación abierta")
    try:
        res = json.loads(Path(resultado).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ApplyError(f"no se pudo leer {resultado} como JSON: {e}") from e
    if not isinstance(res, dict) or str(res.get("bibcode") or "") != bibcode:
        raise ApplyError(f"el resultado no declara `bibcode: {bibcode}`")
    # ⛔ la unidad es el ARCHIVO y lo identifica `<slug>/<stem>`: con el mismo paper bajo dos
    # sujetos —o con una segunda lente (#371)— el resultado tiene que decir a CUÁL vuelve, o el
    # escritor elegiría por orden de glob. Devuelto dos veces: la primera por la lente, la segunda
    # por el slug, que es la otra mitad de la misma identidad.
    cual = str(res.get("extraccion") or "")
    elegidas = [(f, d) for f, d in abiertas if file_id(f) == cual]
    if not elegidas:
        raise ApplyError(f"`extraccion: {cual!r}` no corresponde a ninguna extracción abierta de "
                         f"{bibcode} ({', '.join(file_id(f) for f, _ in abiertas)})")
    f, data = elegidas[0]
    filas = res.get("items")
    if not isinstance(filas, list) or any(not isinstance(x, dict) for x in filas):
        raise ApplyError("`items` tiene que ser una lista de mapas")
    sobran = {k for x in filas for k in x} - set(RESULT_SCHEMA["items"][0])
    if sobran:
        raise ApplyError(f"claves que el resultado no declara: {', '.join(sorted(sobran))} — "
                         f"¿devolviste el `_paquete.json` en vez del resultado?")
    slug = cfg.pdf_slug(cfg.note_stem(bibcode))
    # ⛔ AUD-420 · sin PDF en disco no hubo relectura posible: comparar `"" == ""` cerraba la deuda
    if not slug:
        raise ApplyError(f"no hay PDF de {bibcode} en disco: la relectura es del PDF (#205), así "
                         f"que ningún resultado puede cerrar la deuda")
    sha_disco = lb.sha10((cfg.PDFS / slug / f"{cfg.note_stem(bibcode)}.pdf").read_bytes())
    if str(res.get("pdf_sha") or "") != sha_disco:
        raise ApplyError(f"el `pdf_sha` del resultado ({res.get('pdf_sha')}) no es el del PDF en "
                         f"disco ({sha_disco}): se leyó otro documento")
    los = {it["id"]: it for it in items(data)}
    if {x.get("id") for x in filas} != set(los):
        raise ApplyError(f"los `id` del resultado no son los de la extracción "
                         f"({len(filas)} contra {len(los)}): el paquete quedó viejo, re-emitilo")
    hoy = _dt.date.today().isoformat()
    escritos, no_hallados, rehusados, para_nota, para_nota_texto = [], [], [], [], []
    sin_cambio: list = []
    for fila in filas:
        item = los[fila["id"]]
        motivo = _check_item(item, fila, bibcode)
        if motivo:
            rehusados.append((fila["id"], motivo))
            continue
        ruta, viejo = item["ruta"], item["linea"]
        ocurrencia = int(fila["id"].split("#")[1]) if "#" in fila["id"] else 1
        # ⛔ el `motivo` del hueco VIAJA al texto: es lo que distingue «no lo encontré» de «no
        # aplica al documento nuevo» —la salvedad sobre la marca de agua del preprint que la copia
        # del editor no tiene—, y medido en la repaginación real de la instancia eso fue 35 de
        # 2214. Tirarlo dejaba el hueco declarado y mudo, que es lo que D-43 no acepta.
        # ⛔ …y el hueco tampoco se lleva el CALIFICADOR (observación del validador): `p. 5 (Tabla
        # 4)` sin hallar queda `no hallado (…) (Tabla 4)`, porque el calificador sigue siendo
        # cierto —dice dónde de la página estaba el dato— y es lo que hace barata la próxima
        # relectura. Lo único que caduca es el número.
        motivo_hueco = str(fila.get("motivo") or "").strip()
        paginas = page_answer(fila["pagina"]) if fila.get("pagina") not in (None, "") else None
        n_num = max(1, len(item.get("numeraciones") or []))
        # #533 — un reemplazo por numeración: el hueco también, o la que no se tocó queda vieja
        nuevo = ([f"no hallado (relectura {hoy}: {motivo_hueco})"] * n_num if paginas is None
                 else [f"p. {p}" for p in paginas])
        actual = dict(_strings(data)).get(ruta, "")
        if ruta.endswith(".linea"):
            texto = _replace_line_locators(actual, nuevo)
        elif "@" in fila["id"]:                     # #534 — localizador suelto, por posición
            k = int(fila["id"].rsplit("@", 1)[1])
            chains = loose_chains(actual)
            chain = chains[k - 1] if k <= len(chains) else []
            texto = (_replace_chain(actual, chain, nuevo)
                     if [actual[a:b] for a, b in chain] == item["numeraciones"] else None)
        else:
            texto = _replace_locator(actual, ocurrencia, viejo, nuevo if n_num > 1 else nuevo[0])
        if texto is None:
            rehusados.append((fila["id"], f"el localizador `{viejo}` ya no está donde el paquete lo "
                                          f"leyó: alguien lo corrigió a mano"))
            continue
        if not ruta.endswith(".linea") and texto != actual:
            para_nota_texto.append((actual, texto))
        _set_by_path(data, ruta, texto)
        if fila.get("pagina") in (None, ""):
            no_hallados.append(fila["id"])
        elif texto == actual:
            # #533 — confirmado sin cambio NO es «reescrito»: el resumen decía 69 reescritos
            # cuando ninguno había cambiado donde debía
            sin_cambio.append(fila["id"])
        else:
            escritos.append(fila["id"])
            para_nota.append((item, fila))
    pendientes = sorted([i for i, _m in rehusados])
    marca = {"fecha": hoy, "pdf_sha": sha_disco, "n": len(escritos),
             "no_hallados": len(no_hallados), "fuente": "relectura del PDF (#494)"}
    # @inv INV-160
    for m in cfg.PAGINATION_OPEN_MARKS:
        data.pop(m, None)
    if pendientes:
        data["_repaginado_parcial"] = {**marca, "pendientes": pendientes}
    else:
        data["_repaginado"] = marca
    if not dry_run:
        cfg.write_text_atomic(f, json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    return {"extraccion": f, "escritos": escritos, "no_hallados": no_hallados,
            "rehusados": rehusados, "cerrada": not pendientes, "para_nota": para_nota,
            "para_nota_texto": para_nota_texto, "sin_cambio": sin_cambio}


def print_list() -> int:
    """The open debt, by source, with its population declared (INV-40)."""
    deuda = pending()
    total = sum(len(items(d)) for _f, d in deuda)
    cfg.print_seguro(f"> deuda de paginación ABIERTA: {len(deuda)} extracción(es) · {total} "
                     f"localizador(es) a releer")
    for f, d in deuda:
        bib = str(d.get("bibcode") or f.stem)
        marca = next(m for m in cfg.PAGINATION_OPEN_MARKS if cfg.as_map(d.get(m)))
        pend = cfg.as_list(cfg.as_map(d.get(marca)).get("pendientes"))
        lente = f" · lente `{lens_of(f)}`" if lens_of(f) else ""
        cfg.print_seguro(f"  · {f.parent.name}/{f.stem}: {len(items(d))} item(s) `{marca}`{lente}"
                         + (f" · {len(pend)} pendiente(s) de una ronda previa" if pend else "")
                         + f" → python scripts/repaginate.py {bib} --out build/repag/{f.stem}")
    if not deuda:
        cfg.print_seguro("  (ninguna: no hay extracción con la deuda abierta)")
    return 0


def _apply_cli(args) -> int:
    """Apply one result, SERIALLY (regla de método 6), and re-stamp what the note copied from it."""
    try:
        r = apply(args.bibcode, Path(args.apply), dry_run=args.dry_run)
    except ApplyError as e:
        cfg.print_seguro(f"⛔ {e}")
        return 2
    cfg.print_seguro(f"→ {r['extraccion']}: {len(r['escritos'])} localizador(es) reescrito(s) · "
                     f"{len(r['sin_cambio'])} confirmado(s) sin cambio · "
                     f"{len(r['no_hallados'])} `no hallado` declarado(s) · "
                     f"{len(r['rehusados'])} rehusado(s)")
    for i, motivo in r["rehusados"]:
        cfg.print_seguro(f"  ⚠ {i}: {motivo}")
    cfg.print_seguro(f"  deuda {'CERRADA' if r['cerrada'] else 'PARCIAL: sigue abierta'}")
    # la nota copió esos localizadores de la extracción (#454), así que se re-estampan acotado
    import harvest_views as hv
    slug = r["extraccion"].parent.name
    # ⛔ Sólo las filas de `ground_truth`: su localizador vive en una CELDA de la tabla, donde el
    # único ancla posible es la cita de al lado. Lo que salió de un campo de texto libre —una
    # salvedad— la nota lo publica VERBATIM, así que se sustituye entero abajo; mandarlo también
    # por acá hacía que las dos pasadas se pisaran sobre el mismo bullet.
    filas = [(it, f) for it, f in r.get("para_nota", []) if it["ruta"].endswith(".linea")]
    # ⛔ #533 — el re-estampado de la celda cambia UN token; con varias numeraciones escribiría la
    # lista entera en el lugar de la primera. Esas se nombran y se copian a mano de la extracción.
    varias = [it["id"] for it, f in filas if isinstance(f["pagina"], list)]
    cambios = [(it["cita"] or it["valor"], it["linea"], f"p. {f['pagina']}")
               for it, f in filas if not isinstance(f["pagina"], list)]
    if varias:
        cfg.print_seguro(f"  ⚠ {len(varias)} celda(s) de la vista con varias numeraciones NO se "
                         f"re-estampan solas (#533): copiá el localizador de la extracción — "
                         f"{', '.join(varias[:5])}{' …' if len(varias) > 5 else ''}")
    if cambios:
        vista = hv.restamp_view_locators(slug, paper=args.bibcode, cambios=cambios,
                                         dry_run=args.dry_run)
        cfg.print_seguro(f"  · vista: {vista['cambiados']} celda(s) re-estampada(s), "
                         f"{len(vista['fuera'])} sin tocar")
        for a_, m in vista["fuera"]:
            cfg.print_seguro(f"    ⚠ «{a_}…»: {m}")
    # ⛔ y NO `restamp_salvedades`: cambiar el localizador dentro de una salvedad ES reescribir
    # prosa ya escrita, y ese re-estampado lo rehúsa por diseño (#453). La sustitución es por texto
    # EXACTO, que es como la instancia tuvo que cerrarlo a mano (90 salvedades en 35 notas).
    if r.get("para_nota_texto"):
        salv = hv.restamp_exact_text(args.bibcode, r["para_nota_texto"], dry_run=args.dry_run)
        cfg.print_seguro(f"  · salvedades: {salv['cambiados']} sustituida(s), "
                         f"{len(salv['fuera'])} sin tocar")
        for t, m in salv["fuera"]:
            cfg.print_seguro(f"    ⚠ «{t}…»: {m}")
    cfg.print_seguro("  ⛔ los bloques que cambiaron VENCEN sus pares (D-4): "
                     f"`python scripts/reverify_subset.py vault/wiki/papers/"
                     f"{cfg.note_stem(args.bibcode)}.md`")
    return 0


def main(argv=None) -> int:
    """`--list` la deuda, `--out` el paquete de relectura, `--apply` el resultado del lector."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bibcode", nargs="?", help="la fuente a repaginar")
    ap.add_argument("--list", action="store_true", help="la deuda abierta, por fuente")
    ap.add_argument("--out", help="directorio del paquete de relectura")
    ap.add_argument("--apply", help="el resultado del lector, a escribir en la extracción")
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada")
    args = ap.parse_args(argv)
    if args.list or not args.bibcode:
        return print_list()
    if args.apply:
        return _apply_cli(args)
    if not args.out:
        cfg.print_seguro("⛔ falta `--out <dir>` (o `--apply <resultado.json>`)")
        return 2
    if args.dry_run:
        cfg.refuse_dry_run(ap, "`--out` escribe el paquete de relectura")
    try:
        paquetes = write_rounds(args.bibcode, Path(args.out))
    except RoundError as e:
        cfg.print_seguro(f"⛔ {e}")
        return 2
    for paq in paquetes:
        con_guia = sum(1 for it in paq["items"] if it["guia"]["pagina"])
        lente = f" · lente `{paq['lente']}`" if paq["lente"] else ""
        # ⛔ la línea nombra `<slug>/<stem>`, que es la identidad (#494): `Path(...).stem` tiraba
        # el slug Y cortaba el bibcode en el último punto (`2009A&A...507./prompt.md`), así que las
        # dos líneas de un par salían IDÉNTICAS — justo sobre el eje que este issue existe para
        # separar.
        cfg.print_seguro(f"→ {paq['extraccion']}/prompt.md{lente} · "
                         f"{len(paq['items'])} item(s), {con_guia} con página de guía "
                         f"(el resto la declara)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
