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
                                      "índice del PDF (#500), o null>",
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
                            "valor": str(fila.get("valor") or ""), "cita": "", "linea": texto})
            continue
        for n, cita in enumerate(cfg.quotes_in(texto), 1):
            loc = cfg.page_locators_after(texto, cita)
            if loc:
                out.append({"id": f"{ruta}#{n}", "ruta": ruta, "que": "", "valor": "",
                            "cita": cita, "linea": _loc_token(texto, cita)})
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
    its own items: collapsing them into one package is what dropped 490 of 2032 locators."""
    return [write_round(bibcode, out_dir / f.parent.name / f.stem, extraccion=f)
            for f, _d in open_extractions(bibcode)]


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
              f"Items: {len(paquete['items'])}.", ""]
    for it in paquete["items"]:
        g = it["guia"]
        guia = (f"p. {g['pagina']}" if g["pagina"] else
                f"índice {g['indice']} del PDF" if g["indice"] else "sin guía")
        partes += [f"### `{it['id']}`", "",
                   f"- localizador actual (del documento VIEJO): `{it['linea']}`",
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


def _replace_locator(texto: str, ocurrencia: int, viejo: str, nuevo: str) -> str | None:
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
        a, b = spans[0]
        return texto[:a] + nuevo + texto[b:]
    return None


def _replace_first_locator(texto: str, nuevo: str) -> tuple:
    """`(texto_nuevo, n_localizadores)` — swap the FIRST locator of a `linea` and keep the rest.

    ⛔ Returned by the real repagination: the writer's first version overwrote the whole field, and
    with it the **qualifier** — `p. 4 (Tabla 2)` became `p. 491`, `p. 2056 (nota al pie de la Tabla
    1)` became `p. 2062`. Measured: **143 of 563**. The qualifier is what makes a locator usable —
    it says WHERE on the page the datum is — and it is re-derivable from nothing.

    `n_localizadores` > 1 is the **collapsed** case: the old value named several pages with prose
    in between and the reader placed one. It is counted and declared, because the rest of the
    string —which stays— still names the others."""
    locs = list(cfg.PAGE_LOC_RE.finditer(texto))
    if not locs:
        return texto, 0
    m = locs[0]
    return texto[:m.start()] + nuevo + texto[m.end():], len(locs)


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
    if not ev:
        return "página confirmada sin `evidencia`: sin testigo de la hoja no se distingue de copiar la guía"
    if ev.lower() in str(item.get("valor") or item.get("cita") or "").lower():
        return "la `evidencia` está contenida en el valor del item: no es testigo de la hoja"
    estado, det = cfg.quote_page_verdict(ev, bibcode, [(str(pagina), str(pagina))])
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
    writes `_repaginado_parcial` with their ids, and the lint keeps counting it.

    @inv INV-147"""
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
    sha_disco = lb.sha10((cfg.PDFS / slug / f"{cfg.note_stem(bibcode)}.pdf").read_bytes()) \
        if slug else None
    if str(res.get("pdf_sha") or "") != (sha_disco or ""):
        raise ApplyError(f"el `pdf_sha` del resultado ({res.get('pdf_sha')}) no es el del PDF en "
                         f"disco ({sha_disco}): se leyó otro documento")
    los = {it["id"]: it for it in items(data)}
    if {x.get("id") for x in filas} != set(los):
        raise ApplyError(f"los `id` del resultado no son los de la extracción "
                         f"({len(filas)} contra {len(los)}): el paquete quedó viejo, re-emitilo")
    hoy = _dt.date.today().isoformat()
    escritos, no_hallados, rehusados, para_nota, para_nota_texto = [], [], [], [], []
    colapsados: list = []
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
        nuevo = (f"p. {fila['pagina']}" if fila.get("pagina") not in (None, "")
                 else f"no hallado (relectura {hoy}: {motivo_hueco})")
        actual = dict(_strings(data)).get(ruta, "")
        if ruta.endswith(".linea"):
            texto, n_locs = _replace_first_locator(actual, nuevo)
            if n_locs > 1:
                colapsados.append(fila["id"])
            texto = texto if n_locs else None
        else:
            texto = _replace_locator(actual, ocurrencia, viejo, nuevo)
        if texto is None:
            rehusados.append((fila["id"], f"el localizador `{viejo}` ya no está donde el paquete lo "
                                          f"leyó: alguien lo corrigió a mano"))
            continue
        if not ruta.endswith(".linea") and texto != actual:
            para_nota_texto.append((actual, texto))
        _set_by_path(data, ruta, texto)
        if fila.get("pagina") in (None, ""):
            no_hallados.append(fila["id"])
        else:
            escritos.append(fila["id"])
            para_nota.append((item, fila))
    pendientes = sorted([i for i, _m in rehusados])
    # ⛔ `colapsados` va en la MARCA y no sólo por pantalla: es lo único que queda dicho sobre un
    # campo cuyo localizador viejo nombraba varias páginas y el lector ubicó una — medido sobre la
    # bóveda real, 765 de 5627 `ground_truth[].linea`. En pantalla se lo lleva la corrida; en el
    # artefacto sobrevive, que es donde lo va a buscar quien lea ese campo dentro de seis meses.
    marca = {"fecha": hoy, "pdf_sha": sha_disco, "n": len(escritos),
             "no_hallados": len(no_hallados), "colapsados": colapsados,
             "fuente": "relectura del PDF (#494)"}
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
            "para_nota_texto": para_nota_texto, "colapsados": colapsados}


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
                     f"{len(r['no_hallados'])} `no hallado` declarado(s) · "
                     f"{len(r['rehusados'])} rehusado(s)")
    for i, motivo in r["rehusados"]:
        cfg.print_seguro(f"  ⚠ {i}: {motivo}")
    if r.get("colapsados"):
        cfg.print_seguro(f"  · {len(r['colapsados'])} colapsado(s): el localizador viejo nombraba "
                         f"varias páginas y el lector ubicó una — el resto del campo queda")
    cfg.print_seguro(f"  deuda {'CERRADA' if r['cerrada'] else 'PARCIAL: sigue abierta'}")
    # la nota copió esos localizadores de la extracción (#454), así que se re-estampan acotado
    import harvest_views as hv
    slug = r["extraccion"].parent.name
    # ⛔ Sólo las filas de `ground_truth`: su localizador vive en una CELDA de la tabla, donde el
    # único ancla posible es la cita de al lado. Lo que salió de un campo de texto libre —una
    # salvedad— la nota lo publica VERBATIM, así que se sustituye entero abajo; mandarlo también
    # por acá hacía que las dos pasadas se pisaran sobre el mismo bullet.
    cambios = [(it["cita"] or it["valor"], it["linea"], f"p. {f['pagina']}")
               for it, f in r.get("para_nota", []) if it["ruta"].endswith(".linea")]
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
