"""Quote verification: the text-level rail that decides whether a «quote» is in its source.

Split out of `lib_config` (auditoría 2026-09-04, AUD-306): ~670 lines and 25 symbols that only
`contrast`, `harvest_views` and the lint consume, living in the config module. Nothing here reads
`vault/config/`; what it needs from `lib_config` (paths, frontmatter parsing, the layout constants)
it reaches through `cfg.` at call time. `lib_config` re-exports every public name so
`cfg.quote_verdict(...)` keeps working for callers, tests and the `@inv` map.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import unicodedata
from pathlib import Path

#: #220 · largo mínimo de una cita textual para chequearla contra su fuente. Por debajo, una
#: coincidencia no dice nada (una frase de cinco palabras aparece en cualquier paper del tema) y el
#: ruido de falsos positivos por markup se come la señal.
QUOTE_MIN = 40

#: Fragmento mínimo tras partir por elipsis: la cita cortada («A … B») se chequea por partes, y una
#: parte muy corta no es evidencia de nada.
QUOTE_FRAG_MIN = 25

_QUOTE_RE = re.compile(r"«([^»]+)»")
_QUOTE_MARKUP_RE = re.compile(r"\$[^$]*\$|\[\[|\]\]|[*_`\\]")
#: #336 · lo MISMO menos el span `$…$`. Es la única diferencia entre las dos normalizaciones, y es
#: asimétrica a propósito: en la CITA los `$` son marcado que la nota puso (`CLAUDE.md` lo manda) y
#: el `.txt` no puede tener igual; en la FUENTE son caracteres del documento —el copyright de
#: Elsevier trae uno—, así que borrar entre dos se come el texto del medio.
_SOURCE_MARKUP_RE = re.compile(r"\[\[|\]\]|[*_`\\]")
#: #336 · el guión de corte de `pdftotext -layout` y **la sangría de su continuación**: la línea
#: siguiente arranca indentada porque es la columna física, así que sin absorberla la palabra
#: partida queda como dos.
_HYPHEN_BREAK_RE = re.compile(r"-\n[ \t]*")
_QUOTE_ELLIPSIS_RE = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]|…|\.\.\.")
#: #364/#388 · las **ligaduras tipográficas** van primero: `pdftotext` las deja como UN carácter
#: (`\ufb01nal`) y quien transcribe escribe las dos letras. Es un carácter, no un borde de palabra, así
#: que la guarda de #333 —que existe porque `pdftotext` rompe PALABRAS y un LLM cambia PALABRAS— no
#: podía verlo, y la acusación salía sobre una cita verbatim.
_LIGATURE_SUBS = (("\ufb00", "ff"), ("\ufb01", "fi"), ("\ufb02", "fl"), ("\ufb03", "ffi"), ("\ufb04", "ffl"))

_QUOTE_SUBS = (*_LIGATURE_SUBS,
               ("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'"),
               ("\u2013", "-"), ("\u2014", "-"), ("\u00ad", ""),
               # …y recién ACÁ el modo TeX: el PDF compone la comilla doble con DOS simples
               # (`\u2018\u2018…\u2019\u2019`), que las dos líneas de arriba dejan en `''`, y la transcripción escribe
               # `"`. Cero diferencia de palabras. El orden importa: plegar `''` antes de unificar
               # las simples no vería el par tipográfico.
               ("''", '"'), ("``", '"'))


def normalize_quote(s: str) -> str:
    """A quoted string reduced to what can be compared against a `.txt`.

    The normalization is deliberately minimal and DECLARED (#220): inline math and markdown markup
    are dropped —the note necessarily re-marked the quote up, so `$A$` would never match the source
    verbatim—, typographic quotes and dashes are unified, soft hyphens go, whitespace collapses and
    case is folded. Anything beyond that would start matching text the source does not have.
    """
    return _normalize_text(_QUOTE_MARKUP_RE.sub("", s))


def _normalize_text(s: str) -> str:
    """What the quote side and the source side SHARE: typographic substitutions, the hyphen,
    whitespace and case. One function on purpose (regla de método 2) — a difference between the two
    sides that nobody decided is a match that nobody decided. What legitimately differs is the
    markup regex each caller passes in, and that difference is declared where it lives."""
    for a, b in _QUOTE_SUBS:
        s = s.replace(a, b)
    # #275 — el guión se borra de los DOS lados. `normalize_source_text` ya unió el corte de línea
    # (`inde-\npendent` → `independent`), así que el `-` que queda es el de `p-mode`, que el `.txt`
    # puede traer partido (`p-\nmode` → `pmode`) o entero. Sin esto, toda cita con un guión real
    # fallaba contra una fuente donde ese guión cayó en un fin de línea. ⛔ El orden importa: borrar
    # el `-` ANTES del join daría `p mode` y el defecto se invierte.
    s = s.replace("-", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def normalize_source_text(t: str) -> str:
    """The same normalization on the SOURCE side — with two differences, both measured (#336).

    The hyphen `pdftotext` leaves at a line break (`inde-\npendent`) is joined, or every quote
    crossing a line break would fail; and the join absorbs **the indentation of the continuation**
    (`homoscedas-\n     tic`), because `-layout` keeps the physical column so the next line starts
    indented. Joining only `-\n` left `homoscedas tic` and the split word never came back together:
    measured over a real vault, **141 of 155** `.txt`, **4232** occurrences.

    ⛔ And the `$…$` span is **not** dropped here. That deletion belongs to the quote (#287/#326),
    where the `$` is markup the note added and the `.txt` cannot carry; in a `.txt` the `$` is a
    character of the document, so deleting between two of them eats whatever lies in the middle —
    the Elsevier copyright line (`0925-2312/98/$ — see front matter`) plus one more `$` ate
    **16 434 of 43 401 characters (37,9 %)** of one column, and **10 of 155** `.txt` lost text,
    the worst three 37,9 %, 26,1 % and 22,5 %. What that costs is step 1 of `quote_verdict` (`en_su_txt`,
    #324), the step that prevents the false `alterada` — and since #323 that gate stops
    operations."""
    return _normalize_text(_SOURCE_MARKUP_RE.sub("", _HYPHEN_BREAK_RE.sub("", t)))


def quote_fragments(quote: str) -> list[str]:
    """The pieces of a quote that can be looked up, split at the ellipsis that marks an elision.

    A quote written «A … B» does not appear verbatim anywhere: what the source has is A and B, with
    something in between. Checking the pieces is what makes the elided quote decidable at all;
    pieces below `QUOTE_FRAG_MIN` are dropped, since a short one matches anything.
    """
    return [f for f in (x.strip() for x in _QUOTE_ELLIPSIS_RE.split(quote))
            if len(f) >= QUOTE_FRAG_MIN]


def quotes_in(text: str) -> list[str]:
    """The «…» quotes of a block that are long enough to be worth checking (`QUOTE_MIN`)."""
    return [q.strip() for q in _QUOTE_RE.findall(text) if len(q.strip()) >= QUOTE_MIN]


#: #46/#275 · la canaleta: el hueco de espacios que separa dos columnas en un `.txt` de
#: `pdftotext -layout`. Se DEFINE una vez acá; `measure_layout` la **detecta** (con `\S…\S`, que
#: exige contenido a los lados) y `deinterleave_columns` **parte** por ella. Lo que no puede pasar
#: es que difieran en qué cuenta como canaleta — lo fija un test de paridad (regla de método 2).
CANALETA_MIN = 8
GUTTER = re.compile(rf"\S {{{CANALETA_MIN},}}\S")

#: #332 · cuántos espacios alcanzan para leer el borde de columna de la PÁGINA en una línea que no
#: tiene canaleta propia. **Un** espacio es separación entre palabras, así que cortar ahí partiría
#: una línea a todo el ancho por el medio; dos ya no aparecen dentro de una palabra. Medido sobre
#: los 251 pares únicos (cita, `.txt`) de una bóveda real: con 1 se recuperan 189; con 2 y con 3,
#: 198; con 4, 196; con 8, 187 — o sea que la guarda decide, y su valor exacto por encima de 2 no.
BOUNDARY_SPACES_MIN = 2


def _gutter_runs(line: str) -> list:
    """`(start, end)` of every gutter on this line — `end` is where the next column starts.

    Uses `GUTTER`, the module's ONE definition of a gutter (content on both sides), and resumes the
    scan on the character that closed the previous match: `finditer` would eat it and miss the
    second gutter of a three-column line."""
    out: list = []
    pos = 0
    while True:
        m = GUTTER.search(line, pos)
        if not m:
            return out
        out.append((m.start() + 1, m.end() - 1))
        pos = m.end() - 1


def _column_boundary(lines: list) -> int | None:
    """The offset where this PAGE breaks into two columns, or `None` if it has only one (#332).

    The most voted gutter END over the page's non-blank lines: the end is where the right column
    starts, and a printed page keeps that offset even where the gutter narrows or widens. Ties go to
    the leftmost, so the answer does not depend on dict order."""
    votos: dict = {}
    for line in lines:
        for _, end in _gutter_runs(line):
            votos[end] = votos.get(end, 0) + 1
    if not votos:
        return None
    return min(votos, key=lambda c: (-votos[c], c))


def _split_at_boundary(line: str, boundary: int) -> tuple:
    """`(left, right)` — this line cut at the page's column boundary (#332).

    The cut lands on the candidate CLOSEST to `boundary`: one of the line's own gutters, or
    `boundary` itself when the line merely has `BOUNDARY_SPACES_MIN` spaces there (the narrow gutter
    of a line whose left column almost reaches the edge — the shape that #332 measured). A line with
    no candidate spans the whole width (a heading, a caption, a running header) and stays left,
    which is where the flow that surrounds it lives."""
    if boundary >= len(line):
        return line, ""
    cortes = [end for _, end in _gutter_runs(line)]
    # ⚠ Sin `boundary > 0`, a propósito (#319): con `boundary == 0` la línea vacía ya salió por la
    # guarda de arriba y `line[-1]` no puede aportar un corte —el run de espacios que termina en 0
    # mide 0, y 0 < BOUNDARY_SPACES_MIN—, así que la cláusula no decidiría nada.
    if line[boundary - 1] == " ":
        inicio = boundary
        while inicio > 0 and line[inicio - 1] == " ":
            inicio -= 1
        if boundary - inicio >= BOUNDARY_SPACES_MIN:
            cortes.append(boundary)
    if not cortes:
        return line, ""
    corte = min(cortes, key=lambda x: (abs(x - boundary), x))
    return line[:corte], line[corte:]


def deinterleave_columns(t: str) -> list:
    """The physical COLUMNS of a `pdftotext -layout` `.txt`, one string per column (#275/#332).

    `-layout` keeps the physical page: in a two-column paper every line carries column 1, a run of
    spaces (the gutter) and column 2, so the flat text **interleaves** them and no quote longer than
    one physical line can be found. A single-column file yields exactly one stream, identical to the
    flat text.

    ⛔ **The gutter belongs to the PAGE, not to the line (#332).** Splitting each line at every run
    of spaces made the column index drift line by line —an equation and its number, a narrow gutter,
    a full-width caption each shift it— so a continuous paragraph landed in two different readings
    and a quote that IS verbatim in the `.txt` came back «not there». Measured over a real vault:
    **148 of 155** `.txt` returned more than two readings, up to **19**, and a single sentence of
    ONE physical column fell into two of them. Pages are split at `\f`, each page gets ONE boundary
    (`_column_boundary`), and every line is cut there or, when it spans the width, kept whole on the
    left. Recovery over the 251 unique (quote, `.txt`) pairs of that vault: **176 → 196**, measured
    as a FROZEN A/B —the same population against both versions of the module in one run, because the
    vault is a live instance and was being edited while it was measured—.

    ⛔ The flat text is NOT searched as a fallback: it contains the column-1→column-2 splice, so a
    quote nobody ever wrote would pass as verbatim (pinned since #46). That is why the fix is a
    better cut and never a flattening."""
    izquierda: list = []
    derecha: list = []
    for pagina in str(t or "").split("\f"):
        lineas = pagina.split("\n")
        borde = _column_boundary([l for l in lineas if l.strip()])
        for linea in lineas:
            l, r = (linea, "") if borde is None else _split_at_boundary(linea, borde)
            izquierda.append(l.rstrip())
            derecha.append(r.rstrip())
    columnas = ["\n".join(izquierda)]
    if any(x.strip() for x in derecha):
        columnas.append("\n".join(derecha))
    return columnas


def source_texts(raw: str) -> list:
    """Every normalized reading of a `.txt` a quote may legitimately live in (#275).

    One per physical column, deduplicated — so **one or two**, never the up-to-19 that #332
    measured. A single-column source gives exactly one, so the caller does not branch on layout —
    which is the point: whether the `.txt` is interleaved is a property of the PDF nobody declared
    anywhere."""
    vistos, out = set(), []
    for col in deinterleave_columns(raw):
        norm = normalize_source_text(col)
        if norm and norm not in vistos:
            vistos.add(norm)
            out.append(norm)
    return out


#: #287 · las DOS lecturas de una cita con matemática en el medio. `normalize_quote` **borra** el
#: span `$…$` —correcto cuando la nota re-marcó una fórmula que el `.txt` no puede tener igual—,
#: pero eso convierte «of either $A$ and $S$» en «of either and», que no está en ninguna fuente
#: aunque el paper diga exactamente esa frase con las letras sueltas. Medido al desactivar la
#: exención de #275 sobre una bóveda real: falsos positivos en masa, sobre citas correctas.
_MATH_DELIMS = re.compile(r"\$([^$\n]*)\$")


def quote_variants(quote: str) -> list:
    """The normalized readings of a quote a source may legitimately contain (#287/#326).

    Three, and las tres conservadoras: the math span **dropped** (the note re-marked a formula the
    `.txt` cannot carry), the math span **unwrapped** (`$A$` → `A`, which is exactly how a plain
    letter appears in the extracted text) and the math span treated as an **ELISION** (#326). A
    quote counts as found if **any** reading is there — the words still have to be in the source;
    what changes is which markup of the same words we compare against.

    ⛔ The third one is the fix for a defect that made the whole check unusable on 14 % of a real
    vault (**412 of 3036 quotes carry `$…$`**, and `CLAUDE.md` MANDATES that notation inside
    `vault/wiki/`, so the affected population is by design every quote that touches a formula).
    Dropping the span **glued the two halves together** and produced a string that exists nowhere:
    «Reaching such a high $S/N_{cont}$ is not achievable» became *«reaching such a high is not
    achievable»*, while the `.txt` has `s/ncont` in the middle. It is the very argument this
    module's `quote_fragments` makes one screen below —a quote written «A … B» is not verbatim
    anywhere, so it is checked in pieces— applied to the wrong marker. Consequence with the
    #315→#321→#324 chain: step 1 of `quote_verdict` (*is it in the `.txt` of its source?*) could
    **never** return True for those quotes, so they always fell through to the extraction
    comparison and could be reported `alterada`, which blocks `--cierre` (#318) and the closing step
    of four skills (#323) — **with no correction able to switch it off**, since the quote was
    already right.

    ⚠ Only `$…$` had this treatment: backticks and `[[wikilink]]` lose their DELIMITERS and keep
    their text, which is unwrapping, not deletion."""
    directa = normalize_quote(quote)
    crudo = str(quote or "")
    lecturas = [directa]
    for otra in (normalize_quote(_MATH_DELIMS.sub(r"\1", crudo)),
                 normalize_quote(_MATH_DELIMS.sub(" … ", crudo)),
                 # #373 — la cuarta, y es la SIMÉTRICA: la cita normalizada **como se normaliza una
                 # fuente**, o sea conservando el span. Las otras tres nacieron mirando el `.txt`,
                 # que no puede llevar la fórmula; pero la EXTRACCIÓN sí la lleva, y
                 # `normalize_source_text` la conserva desarmada. Sin esta lectura, una cita cuyo
                 # contenido es sobre todo matemática no se encontraba NUNCA en su propia
                 # extracción, aunque estuviera ahí carácter por carácter. Estaba latente hasta que
                 # #373 metió las `## Vista` en la población: 7 hallazgos, los 7 falsos, sobre una
                 # bóveda real — y un falso positivo acá frena operaciones (#323).
                 normalize_source_text(crudo)):
        if otra not in lecturas:
            lecturas.append(otra)
    return lecturas


#: #288 · tokens que la EXTRACCIÓN mete en medio de la prosa y el paper no tiene: números de línea
#: de un preprint A&A, marcas de columna, coordenadas. Sirven para **clasificar** un hallazgo que ya
#: falló, nunca para aceptarlo.
_TOKEN_RUIDO = re.compile(r"(?<![a-z])\d+(?:[.,]\d+)?(?![a-z])")


def quote_found_degraded(quote: str, source_norm: str) -> bool:
    """Would this quote be in that source if the extraction had not degraded it? (#288)

    ⛔ **This never makes a finding pass.** It only tells apart two things that need opposite work:
    a note that misquotes its source (fix the note) and a `.txt` whose extraction dropped the quote
    apart — line numbers of a two-column preprint injected mid-sentence, a neighbouring column
    spliced in. Measured on a real vault: of five findings opened one by one, **four** were the
    artefact and only one was the note.

    The comparison drops standalone numeric tokens from BOTH sides, which is exactly what would make
    a wrong number match — hence it may never accept, only classify, and the message it produces
    sends the reader to the PDF."""
    limpio = _TOKEN_RUIDO.sub(" ", source_norm)
    for variante in quote_variants(quote):
        frags = quote_fragments(_TOKEN_RUIDO.sub(" ", variante))
        if frags and all(re.sub(r"\s+", " ", f).strip() in re.sub(r"\s+", " ", limpio)
                         for f in frags):
            return True
    return False


def _extraction_index() -> dict:
    """`{bibcode: [data]}` over `raw/extraccion/`, built from the `bibcode` INSIDE each file (#374).

    ⛔ The glob it replaces was `*/<bibcode>.json`, i.e. the **file name** as identity — the third
    reader of this directory to carry its own answer, and the one that decides the verdict of the
    closing gate. With a second lens (`<bib>__<lens>.json`, #308) that glob finds nothing, so every
    quote of the re-reading fell into *not evaluable* and the gate returned rc 0 over them.

    ⚠ Reading every file once and indexing is also **cheaper** than the glob it replaces: the old
    one ran per bibcode (memoised per bibcode, but a sweep asks for hundreds), this one runs once
    per vault. It is rebuilt when `EXTRACCION` changes, which is what a monkeypatched vault does."""
    clave = str(cfg.EXTRACCION)
    if clave in cfg._EXTRACTION_INDEX:
        return cfg._EXTRACTION_INDEX[clave]
    idx: dict = {}
    for f in sorted(cfg.EXTRACCION.glob("*/*.json")) if cfg.EXTRACCION.exists() else []:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue          # el JSON roto lo DECLARA quien lo lee entero (`contrast.extracciones`)
        bib = extraction_identity(data)
        if bib:
            # ⚠ Se guarda el DATO ya parseado, no el path: si no, cada consumidor vuelve a abrir el
            # archivo y se pierde la propiedad que #320 midió —un JSON, una lectura por corrida—,
            # que importa porque el chequeo corre por CITA sobre JSON de decenas de KB.
            idx.setdefault(bib, []).append(data)
    cfg._EXTRACTION_INDEX[clave] = idx
    return idx


def extraction_texts(bibcode: str) -> list:
    """Every textual field of this paper's EXTRACTIONS, normalised for quote lookup (#315/#317).

    ⛔ The decisive comparison nobody was making. #220 tests a note's verbatim quote against the
    `.txt`, which #205 declares a degraded index — so the check reports the degradation of the
    `.txt` as if it were a defect of the note: measured, **2 of 17** real findings in one concept
    and **0 of 35** in another. The extraction JSON, on the other hand, is the transcription made
    **while reading the PDF**, so comparing against it makes *"the synthesiser invented this quote"*
    decidable offline and without opening the PDF: if the quote is not in any extraction of its
    bibcode, no degraded-artefact excuse applies.

    Returns the normalised readings (same shape `quote_found` expects), one per JSON on disk.
    Memoised per bibcode (#320): the check runs per QUOTE, and this is the only disk read left
    uncached on that hot path."""
    clave = (str(cfg.EXTRACCION), bibcode)
    if clave in cfg._EXTRACCION_CACHE:
        return cfg._EXTRACCION_CACHE[clave]
    out = []
    for data in _extraction_index().get(bibcode, []):
        trozos: list = []

        def _walk(v):
            """Every string inside the JSON — the extractor's quotes live in several fields."""
            if isinstance(v, str):
                trozos.append(v)
            elif isinstance(v, dict):
                for x in v.values():
                    _walk(x)
            elif isinstance(v, list):
                for x in v:
                    _walk(x)
        _walk(data)
        out.append(normalize_source_text(" \n ".join(trozos)))
    cfg._EXTRACCION_CACHE[clave] = out
    return out


#: #321/#324 · how many characters of the opening must match to call it «completed while copying».
#: Above `QUOTE_MIN` (40) on purpose: a short prefix matches by chance between two sentences of the
#: same paper, and this check BLOCKS — the evidence must be positive, not plausible.
#: ⛔ ONE definition (#324): `lint.py` and `contrast.py --validar` decide the same thing, and while
#: each carried its own copy the comment *declared* they had to be the same number and nothing
#: checked it. Tuning one would leave a skill closing green on what the other blocks.
CITA_PREFIJO = 60

#: #225/#341 · the fourth in-line mark, and the ONE place its wording lives. It does not destroy the
#: claim —which may well be true—, it is visible to the consumer, the lint raises it as backlog, and
#: it comes off when somebody verifies it with evidence. Until 1.162.0 only `lint.py` knew the
#: string, so the only tool that could ever produce one was a human reading the report.
VERIFICAR_PDF_MARK = "⚠verificar en el PDF"


def verificar_pdf_mark(motivo: str, fecha: str = "") -> str:
    """The mark to paste at the end of a claim nobody could close: `⚠verificar en el PDF (…)`.

    ⛔ **Emitted, never applied** (#341). Which of the two readings of the PDF wins is decided by
    whoever opens the page — and the measurement that settles it is the opposite case: the `log.md`
    of a real vault records a correction that trimmed the note **towards** an invented tail, because
    the split `.txt` seemed to say it. A broken reading artefact does not produce silence, it
    produces corrections in the wrong direction. So the tool hands over the string and stops.

    The `motivo` says **what was doubted** — a category would not survive six months, the sentence
    does — and the date says when. Both are part of the mark by contract (`CLAUDE.md`), and this is
    the only function that builds it, so the string the lint looks for and the string a tool offers
    cannot drift apart (regla de método 2)."""
    return f"{VERIFICAR_PDF_MARK} ({motivo}, {fecha or _dt.date.today().isoformat()})"


def extraction_identity(data: dict) -> str:
    """Which bibcode an extraction belongs to: the `bibcode` INSIDE it, never the file name (#374).

    ⛔ ONE implementation for every reader of `raw/extraccion/`. `contrast` keyed by `f.stem` and
    `harvest_views` by `data["bibcode"]` — two consumers of the same directory with two identities.
    While the file name IS the bibcode the two coincide and the divergence is invisible; it shows up
    the moment a **second lens** (#239/#308) writes `<bibcode>__<lens>.json`, which is the very
    mechanism #308 built. Measured in a real vault: 32 extractions, 13 whose stem matched no note,
    **309 quotes that fell into «not evaluable» while the gate returned rc 0** over quotes it had
    never looked at — the false clean D-43 exists to prevent. And `--filas` emitted `[[<stem>]]`, a
    wikilink that does not resolve, straight into an inventory #322 says to paste unedited.

    This is the error #228 already paid for once in the other direction —an extraction left under
    the old bibcode made the harvester skip that note forever— and the conclusion was the same one:
    map by the field inside.

    Empty when the extraction declares none: an artefact that cannot say whose reading it is gets
    DECLARED by the caller, never guessed from the file name — guessing is what put the two
    identities out of step to begin with.

    @inv INV-103"""
    return str(data.get("bibcode") or "").strip()




def log_quote_exempt(stem: str, texto: str, kind: str = "") -> str | None:
    """Why this block of `log.md` is NOT a claim of the vault, or `None` if it is one (#386/#387).

    ⛔ **ONE implementation, because a convention written in prose does not COMPOSE.** The mark is
    free text that every check has to learn separately: there were two and they had already
    diverged —the lint honoured it, `contrast` had never heard of it (`grep -c corregido` → 0)—, and
    the third one to be written would not know it either. Same failure mode as regla de método 2,
    applied to a convention instead of to a test double.

    ⛔ **ONE exemption, scoped to `log.md`** (#391). Until 1.215.0 there were two, and the other one
    —the `⚠ corregido` mark— is what this issue took out: a **free-text** convention that gated a
    check, so every new consumer had to learn it or the entry came back as a defect. It existed
    because the log carried a verbatim QUOTE, which is a machine-checkable claim in the one place no
    verification layer audits: `verify-citations` goes note by note and never reads the bitácora.
    Taking the quote out of the log —it belongs in a note, or in a blockquote as a mention— removes
    the reason for the mark instead of the mark alone.

    · **the blockquote** (#387): the REFLEXIVE case, which had no way out inside the rule. An entry
      that documents a malformed quote **has to quote it in order to explain it**, and the moment it
      does, it *is* a malformed quote in the eyes of the check — measured in a real vault, the entry
      that corrects the defect reported itself. Inside a blockquote of the `log` a quote is a
      MENTION, not an assertion of the vault: the same doctrine that keeps `SECCIONES_ESTAMPADAS`
      out of `verify-citations`.

    ⚠ The blockquote is recognised by the parser's own `Block.kind`, not by sniffing for a `>`:
    `split_blocks` **strips** the marker when it builds `text`, so a text-level check would silently
    never fire — the same shape of bug as #168/#276, a check looking at markup that the layer below
    already normalised away.

    @inv INV-141

    ⚠ **Scoped to `log.md` on purpose.** In a note or a concept a correction is made by editing, so
    the exemption does not apply there and a quote inside a blockquote of a ficha is still a claim.
    Widening this into a general assert/mention distinction touches `verify-citations` and the leak
    detector too — it is not decided here."""
    if stem != "log":
        return None
    if kind == "blockquote":
        return "cita dentro de un blockquote del `log`: es mención, no afirmación (#387)"
    return None


#: #333 · how far the `.txt` must KEEP GOING past the divergence point for it to be a divergence at
#: all. A reading that simply runs out —a page break, a column edge— does not say something else: it
#: falls silent, and silence is absence (step 3 of the rule), never an accusation.
CITA_COLA_MIN = 12


def _common_prefix_len(a: str, b: str) -> int:
    """How many leading characters two strings share."""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def txt_accuses(quote: str, readings: list) -> dict | None:
    """Does the DETERMINISTIC reading contradict the quote the extraction approved? (#333)

    ⛔ **The discrepancy is not «PDF vs `.txt`».** The PDF is the source and is always right; what
    differs is **who read it**: the `.txt` was read by `pdftotext` (deterministic, loses formulas,
    image-tables and columns) and the extraction by **an LLM** (sees everything, sometimes
    transcribes wrong). Two readings of the same document — so an alteration born IN the extraction
    is invisible to the check whose judge IS the extraction (#315/#317), and until now the `.txt`
    could only absolve (`en_su_txt`), never accuse.

    What makes the accusation admissible is an asymmetry that was **measured**: when the `.txt`
    fails, the chain is **ABSENT, not different** — the three failure modes are the math span, the
    column cut (#332) and the line break. None of them makes the `.txt` say *something else* in
    running prose. So there is positive evidence, the same shape #318/#321 accept against another
    bibcode, applied here to the same bibcode between **its two artefacts**:

      · a long prefix (`CITA_PREFIJO`) of the quote is in the `.txt`, and it **continues
        differently** for at least `CITA_COLA_MIN` more characters;
      · the divergence starts **on a word boundary**. This is the discriminator, and it is what the
        re-measurement bought: of 7 candidates over a real vault, the 4 false ones diverge **inside
        a word** —a `ﬁ` ligature, a word split by a bare space (`mix tures`, `non identifiability`),
        a splice— and the 3 true ones diverge at a whole word. `pdftotext` breaks WORDS; an LLM
        that transcribes badly changes WORDS;
      · nothing of the divergence touches `$…$` or a table pipe → otherwise the `.txt` **does not
        opine** and the answer is the PDF. The math guard carries its weight: all 3 excluded cases
        of that vault would otherwise have accused, and a 60-character prefix can only match where
        the span deletion glued nothing, so *«the quote carries math»* and *«the divergence touches
        math»* coincide in practice.

    ⛔ **The output is a MARK, never a correction** (#341): which of the two readings wins is decided
    by whoever opens the page. Measured against the opposite: the `log.md` of that vault records a
    previous correction that trimmed the note **towards** the invented tail, because the split `.txt`
    seemed to say it — a broken reading artefact does not produce silence, it produces corrections
    in the wrong direction.

    Returns `{"comun", "cola_cita", "cola_txt"}`, or `None` when the `.txt` has nothing to say."""
    if _MATH_DELIMS.search(str(quote or "")):
        return None
    q = normalize_quote(str(quote or ""))
    # Una cita elidida («A … B») no está verbatim en ningún lado por definición, así que su «cola
    # divergente» sería el propio recorte: se chequea por fragmentos (`quote_fragments`) o no se
    # chequea. Acá no se chequea.
    if len(quote_fragments(q)) != 1:
        return None
    # ⚠ El «prefijo largo» lo IMPONE este recorte, no una guarda aparte (#319): con una cita más
    # corta que `CITA_PREFIJO` el arranque es la cita entera, así que un hit implica `comun ==
    # len(q)` y lo corta la guarda de abajo. Una condición que no decide nada es una regla escrita
    # a medias. Ídem `readings` vacío: sin lecturas el barrido no encuentra nada y `mejor` queda
    # `None`, que es la respuesta correcta (D-43: no evaluable, no una acusación vacía).
    arranque = q[:CITA_PREFIJO]
    mejor = None
    for src in readings:
        pos = src.find(arranque)
        while pos != -1:
            comun = _common_prefix_len(q, src[pos:])
            if mejor is None or comun > mejor[0]:
                mejor = (comun, src[pos + comun:pos + comun + 2 * CITA_PREFIJO], src, pos)
            pos = src.find(arranque, pos + 1)
    if mejor is None:
        return None
    comun, cola_txt, src, pos = mejor
    # #388 — el EMPALME DE COLUMNAS rompe el argumento de arriba: lo que `pdftotext` intercala es la
    # columna vecina, que es texto real y **arranca en un borde de palabra perfecto**. La guarda
    # anterior no lo ve porque no rompe ninguna palabra. El discriminante es que la cita REANUDA más
    # adelante en la misma lectura: si el `.txt` trae la continuación, no está diciendo otra cosa,
    # está diciendo lo mismo con algo metido en el medio. ⚠ En el verdadero positivo medido de esa
    # misma tanda la cola SEGUÍA la misma frase y no reanuda, así que el filtro no lo toca.
    sonda = q[comun:comun + CITA_COLA_MIN * 2].strip()
    if len(sonda) >= CITA_COLA_MIN and sonda in src[pos + comun:]:
        return None
    # El borde de palabra, y de paso la cita que el `.txt` tiene ENTERA: `normalize_quote` recorta
    # el espacio final, así que una coincidencia completa termina en una letra y la guarda la corta
    # sola — un `comun >= len(q)` aparte no decidiría nada (#319).
    if q[comun - 1] != " ":
        return None
    if len(cola_txt.strip()) < CITA_COLA_MIN:
        return None
    if "|" in q[comun:] or "|" in cola_txt:
        return None
    return {"comun": comun, "cola_cita": q[comun:], "cola_txt": cola_txt}


def fulltext_readings(bibcode: str) -> list:
    """Normalised readings of this paper's `.txt`, one per physical column (#275), memoised.

    `[]` when there is no `.txt` on disk, which is *not evaluable*, never *"the quote is not
    there"*. Shared by the two callers that ask the same question (#324)."""
    clave = (str(cfg.FULLTEXT), bibcode)
    if clave in cfg._FULLTEXT_CACHE:
        return cfg._FULLTEXT_CACHE[clave]
    txts = sorted(cfg.FULLTEXT.glob(f"*/{bibcode}.txt")) if cfg.FULLTEXT.exists() else []
    out = []
    if txts:
        try:
            out = source_texts(txts[0].read_text(encoding="utf-8", errors="replace"))
        except OSError:
            out = []
    cfg._FULLTEXT_CACHE[clave] = out
    return out


#: #492 · el localizador de PÁGINA tal como la bóveda lo escribe: `p. 7`, `pp. 12-14`. UNA
#: definición para sus dos lectores —`lib_blocks.locator_kinds`, que mira la celda `Evidencia`, y el
#: chequeo de esa página contra el `.txt`—: dos regex de «un localizador» es la divergencia que
#: #324 declaró prohibida, y acá una de las dos decide un veredicto.
#: …y la forma COMPUESTA (#492, defecto A): `pp. 12-14` es un rango, `pp. 179 y 190` y
#: `p. 9, p. 6` son DOS localizadores (medido: 132 + 143 en una bóveda real). El número suelto que
#: sigue a una coma o a una conjunción se toma como otra página; el de más de cuatro cifras no (un
#: año pegado a la página no es una página).
#: …y el número puede llevar PREFIJO (#496): la página que imprime la hoja no siempre es un entero
#: —A&A Letters imprime `L43`, ApJL `L24`, MNRAS Letters `L1`—, así que un localizador correcto de
#: esa fuente no se podía escribir de forma que ninguna capa lo leyera: sus 57 localizadores caían
#: FUERA DE ALCANCE del chequeo, que no es `mal` sino invisible, y del otro lado `printed_pages`
#: devolvía `[None]*5`. La bóveda elegía entre escribir la verdad y perder el chequeo, o escribir
#: un número que el paper no muestra y conservarlo — la segunda pasa en verde.
PAGE_LOC_RE = re.compile(r"\bp{1,2}\.\s*[A-Z]?\d{1,4}(?:\s*(?:[-–—]|,|\by\b|\band\b|\be\b)\s*(?:p{1,2}\.\s*)?[A-Z]?\d{1,4}(?!\d))*",
                         re.I)
_PAGE_LOC_SEP = re.compile(r"\s*(?:,|\by\b|\band\b|\be\b)\s*", re.I)

#: #496 · una página es su ETIQUETA (`"45"`, `"L45"`) y la aritmética —rango, consecutividad,
#: offset— corre sobre el número DENTRO de un mismo prefijo. ⛔ El prefijo viaja con el número y
#: NUNCA se descarta: `p. 45` y `p. L45` son páginas distintas del mismo documento (A&A numera el
#: cuerpo y las Letters por separado), así que plegar `L45 → 45` para poder comparar convertiría el
#: chequeo en un aprobador de la convención equivocada. ⛔ El prefijo es MAYÚSCULA: en minúscula
#: es una variable de la matemática, no una página (`= E { s1 s2 }` en el pie de una fórmula), y
#: leerlo con `re.I` costó —medido sobre una bóveda real de 255 fuentes— 34 páginas impresas
#: perdidas por ambigüedad y 2 leídas como `S1`/`S2` en tres documentos largos.
_PAGE_LABEL_RE = re.compile(r"^([A-Z]?)(\d{1,4})$")
_PAGE_LABEL_IN = re.compile(r"(?i)[A-Z]?\d{1,4}")
_PAGE_LOC_PREFIX = re.compile(r"(?i)\bp{1,2}\.\s*")


def page_parts(etiqueta) -> tuple | None:
    """`(prefix, number)` of a page label — `("L", 45)` for `L45`, `("", 45)` for `45` (#496).

    ⛔ The ONE place that decides what a page label is, so the prefix's case is decided ONCE: the
    harvesting regexes stay permissive and everything they find comes through here. An UPPERCASE
    prefix is a page (`L45`, `V133`); a lowercase one is a variable of the maths (`= E { s1 s2 }`
    in the footer of a formula) — measured over a real 255-source corpus, reading it case-blind
    cost 34 printed pages to ambiguity and misread 2 as `S1`/`S2`."""
    m = _PAGE_LABEL_RE.match(str(etiqueta or "").strip())
    return (m.group(1).upper(), int(m.group(2))) if m else None


def page_label(partes) -> str:
    """`("L", 45)` → `"L45"` — the inverse of `page_parts`, so the prefix survives every round trip."""
    return f"{partes[0]}{partes[1]}"


def page_span(desde, hasta) -> set:
    """Every page LABEL a locator range names: `L43`–`L45` → `{L43, L44, L45}` (#496).

    Empty when the two ends are not the same numbering (`12`–`L14` names no range): comparing
    across prefixes is the one thing this type exists to prevent."""
    a, b = page_parts(desde), page_parts(hasta)
    if not a or not b or a[0] != b[0] or b[1] < a[1]:
        return {page_label(a)} if a else set()
    return {page_label((a[0], n)) for n in range(a[1], b[1] + 1)}

#: #492 · cuántas líneas de la cabecera y del pie se miran buscando el número IMPRESO, y en cuántas
#: páginas tiene que repetirse el desfasaje para darlo por derivado. Tres es lo mínimo que distingue
#: una numeración de una coincidencia: dos enteros que crezcan de a uno —un año, el número de una
#: ecuación— dan el mismo desfasaje en dos páginas cualesquiera.
PAGE_EDGE_LINES = 2
PAGE_OFFSET_MIN = 3

_PAGE_EDGE_RE = re.compile(r"(?i)(?<!\S)([A-Z]?\d{1,4})(?!\S)")


def page_locators(texto: str) -> list:
    """`[(desde, hasta)]` — every page locator in a string, as LABELS: `pp. 12-14` is one range,
    `pp. 179 y 190` two pages, `p. 9, p. 6` two pages (#492), `pp. L43-L47` one range (#496)."""
    out = []
    for m in PAGE_LOC_RE.finditer(texto or ""):
        for parte in _PAGE_LOC_SEP.split(m.group(0)):
            # el `p.`/`pp.` se saca ANTES de buscar la etiqueta: si no, su `p` se leería como el
            # prefijo del número que introduce (#496)
            partes = [x for x in (page_parts(e) for e in
                                  _PAGE_LABEL_IN.findall(_PAGE_LOC_PREFIX.sub(" ", parte))) if x]
            if partes:
                a, b = partes[0], partes[-1]
                out.append((page_label(a),
                            page_label(b if b[0] == a[0] and b[1] >= a[1] else a)))
    return out


def locator_matches(texto: str, desde: int, ventana: int = 80) -> list:
    """Every `PAGE_LOC_RE` match that STARTS within `ventana` chars of `desde`, read WHOLE (#501).

    ⛔ The window bounds where a locator may START, never where it ends: cut at a fixed width,
    `p. 2021` on the border was read `p. 2` — a false `MAL` for a reader and, for a writer that
    compares against what it read with the same cut, a corrupted number (`p. 13` → `p. 20213`).
    It still stops at the next `«`: past it the number belongs to ANOTHER quote (#325). The ONE
    implementation of the window: the gate, the repaginator and the view re-stamper all read here.
    Match positions are relative to `desde`."""
    cola = str(texto or "")[desde:].split("«")[0]
    return [m for m in PAGE_LOC_RE.finditer(cola) if m.start() < ventana]


def page_locators_after(texto: str, cita: str, ventana: int = 80) -> list | None:
    """`[(from, to), …]` — the page locators ADJACENT to a quote, or `None`.

    Adjacency is the rule of #325 applied to the other half of the pair: the vault writes `«…»
    (p. 4) [[bib]]`, `«…» ([[bib]], p. 4)` and, in a row, `| «…» | p. 4 |`, so the window after the
    closing `»` covers the three. ⛔ It stops at the next `«`: past it the number belongs to
    ANOTHER quote, and stealing it is the failure mode #325 measured for the bibcode — here it
    would report a correct locator as wrong.

    ⛔ **ALL of them, not the first one** (#492, defecto A del validador). A quote that spans two
    pages is written `(p. 9 y p. 6)` or `(pp. 179 y 190)` — 132 + 143 occurrences in a real vault —
    and keeping only the first turns a CORRECT locator into a finding, in the category that exists
    to correct locators. The second form is not even a range: `pp. 179 y 190` is two locators, so
    parsing a range would not have been enough either. The quote satisfies the pair if it is on
    ANY of the pages named, which is what the locator claims.

    ⚠ It does NOT report which numbering the locator says it uses: since #500 the verdict accepts
    either one, so `[índice del PDF]` is a courtesy to the reader and no longer a branch.
    """
    pos = str(texto or "").find(cita)
    if pos < 0:
        return None
    return [loc for m in locator_matches(texto, pos + len(cita), ventana)
            for loc in page_locators(m.group(0))] or None


def page_number_candidates(paginas: list) -> list:
    """`[{etiquetas}]` — the page labels in the header and footer of each page (#492/#496).

    The ONE place that decides where a printed page number can live: the first and last
    `PAGE_EDGE_LINES` non-empty lines. Its two readers —the global offset and the per-page
    number— have to look at the same thing, or one of them would be auditing a different document.
    """
    out = []
    for pag in paginas:
        lineas = [l for l in str(pag or "").split("\n") if l.strip()]
        cand: set = set()
        for linea in lineas[:PAGE_EDGE_LINES] + lineas[-PAGE_EDGE_LINES:]:
            cand |= {page_label(x) for x in map(page_parts, _PAGE_EDGE_RE.findall(linea)) if x}
        out.append(cand)
    return out


#: #493 · las DOS formas en que un entero del borde ES el número de página, y no otra cosa: la X
#: de «page X of Y» (A&A: `A2, page 22 of 23` — la Y es el total del artículo, y toda cita con
#: localizador igual al total pasaba a «impresa»: 8 casos medidos) y la línea que es SÓLO un
#: entero (`'10'`, el caso Naik). Un entero dentro de otra línea —una fecha del pie, un `4` suelto—
#: sólo cuenta si forma secuencia con la vecina (`printed_pages`), y un año, nunca.
_PAGE_OF_RE = re.compile(r"(?i)\b(?:page|p[áa]g(?:ina)?\.?|p\.)\s*([A-Z]?\d{1,4})\s*(?:of|de)\s*[A-Z]?\d{1,4}\b")
_ONLY_INT_RE = re.compile(r"^\s*([A-Z]?\d{1,4})\s*$")


def page_number_evidence(paginas: list) -> list:
    """`[{etiquetas}]` — per page, the edge labels that ARE a page number on their own (#493/#496).

    ⛔ Stricter than `page_number_candidates` on purpose. The verdict uses this set to accept a
    declared page BEFORE consecutiveness and offset, so it has to be evidence and not a number:
    measured on a real vault, accepting any edge integer flipped **19** findings to «impresa» and
    **18 were false** — the article total of A&A's footer, a date, a bare `4`. Only two shapes
    qualify: `X` in «page X of Y», and a line that is nothing but an integer; a four-digit year on
    its own line does not.
    """
    out = []
    for pag in paginas:
        lineas = [l for l in str(pag or "").split("\n") if l.strip()]
        ev: set = set()
        for linea in lineas[:PAGE_EDGE_LINES] + lineas[-PAGE_EDGE_LINES:]:
            ev |= {page_label(x) for x in map(page_parts, _PAGE_OF_RE.findall(linea)) if x}
            # el descarte del AÑO vale para el entero pelado: `L1998` no es un año, es una página
            # de Letters (#496)
            if (m := _ONLY_INT_RE.match(linea)) and (x := page_parts(m.group(1))) \
                    and not (x[0] == "" and 1900 <= x[1] <= 2099):
                ev.add(page_label(x))
        out.append(ev)
    return out


def printed_page_offset(paginas: list) -> tuple | None:
    """`(prefix, offset)` with `impresa = prefix + (índice + offset)` — or `None` (#492/#496).

    ⛔ The prefix travels with the offset because it is part of the numbering: a Letters document
    numbers `L43, L44, …`, so `índice + offset` alone would reconstruct a page the paper does not
    show (#496). Counting is per `(prefix, desfasaje)`, so two numberings never add up into one.

    ⛔ It does not guess. A `.txt` whose pages carry no number (a preprint, a scan whose header the
    OCR ate) has NO derivable printed numbering, and that is a different answer from «the locator is
    wrong»: without the offset the only decidable thing is the PDF index, and which of the two
    conventions the note used cannot be told apart from a coincidence (D-43).

    Takes the RAW pages, not the normalized readings: the number lives in the header or the footer,
    which is exactly what `normalize_source_text` folds into the running text. A TIE between two
    candidate offsets is also `None` — see below.

    ⚠ It describes the WHOLE document with one number, which is false in a book whose chapters
    restart the numbering: `printed_pages` is the reader that resolves that, and this one is its
    fallback.
    """
    cands = [{x for x in map(page_parts, c) if x} for c in page_number_candidates(paginas)]
    cuenta: dict = {}
    for i, cand in enumerate(cands, 1):
        for pref, n in cand:
            cuenta[(pref, n - i)] = cuenta.get((pref, n - i), 0) + 1
    if not cuenta:
        return None
    techo = max(cuenta.values())
    # ⛔ #493 — un offset que ningún par de páginas VECINAS sostiene no es una paginación: es una
    # coincidencia de enteros que no son páginas (números de ecuación, valores en los bordes). En
    # `2012Naik`, `0` alcanzaba el techo 3 sobre 22 páginas así, y le ganaba al `10` impreso en la
    # página donde caía la cita.
    candidatos = [k for k, v in cuenta.items() if v == techo and any(
        (k[0], i + k[1]) in cands[i - 1] and (k[0], i + 1 + k[1]) in cands[i]
        for i in range(1, len(cands)))]
    # ⛔ Un EMPATE no se desempata: dos numeraciones que se repiten lo mismo son dos lecturas del
    # mismo documento, y elegir una sería inventar la convención que este chequeo existe para
    # auditar. Sale `None` —no evaluable con su motivo (D-43)—, no la más chica ni la primera.
    if techo < PAGE_OFFSET_MIN or len(candidatos) != 1:
        return None
    return candidatos[0]


def printed_pages(paginas: list) -> list:
    """`[etiqueta | None]` — the PRINTED page of each page, one by one (#492, defecto B).

    ⛔ **A document does not have one offset.** A book whose chapters restart the numbering breaks
    the assumption `impresa = índice + offset` that `printed_page_offset` makes, and the failure is
    not a rounding error: measured on Comon–Jutten —the most cited source of a real hub— the global
    offset came out `+1` and the check reported **94 MAL, all 94 false**, 14 % of the whole
    category. A detector whose false positives concentrate on the biggest source is worse than no
    detector: it is read once and then ignored.

    So the number is read **where the quote falls**, from that page's own header or footer, and the
    ambiguity —any page carries other integers— is resolved by **local consecutiveness**: the
    candidate whose predecessor is on the previous page or whose successor is on the next one, and
    only when there is exactly ONE such candidate. The global offset stays as the fallback for
    pages that show nothing, and is **dropped** as soon as any page contradicts it: an offset that
    the document itself denies cannot be used to judge the pages that stayed silent.
    """
    cands = [{x for x in map(page_parts, c) if x} for c in page_number_candidates(paginas)]
    off = printed_page_offset(paginas)
    locales = []
    for i, c in enumerate(cands, 1):
        vecinos: set = set()
        if i >= 2:
            vecinos |= {(pref, n + 1) for pref, n in cands[i - 2]}
        if i < len(cands):
            vecinos |= {(pref, n - 1) for pref, n in cands[i]}
        consecutivos = sorted(c & vecinos)
        # #496 — un documento tiene UNA numeración, así que entre dos candidatos consecutivos gana
        # el que está en la del documento (el prefijo del offset). Sin este desempate, el par
        # `J1`/`J2` de una fórmula —o `G1`/`G2`— hace ambigua la página que la cabecera imprime al
        # lado: medido sobre una bóveda real, 6 páginas de dos libros perdían su número. Si el
        # documento no tiene numeración dominante, la ambigüedad NO se adivina (D-43).
        if off is not None:
            consecutivos = [x for x in consecutivos if x[0] == off[0]] or consecutivos
        locales.append(consecutivos[0] if len(consecutivos) == 1 else None)
    contradice = off is not None and any(
        n is not None and n != (off[0], i + off[1]) for i, n in enumerate(locales, 1))
    return [page_label(n) if n is not None else
            (page_label((off[0], i + off[1])) if off is not None and not contradice else None)
            for i, n in enumerate(locales, 1)]


def fulltext_pagination(bibcode: str) -> dict:
    """`{"paginas": [[lecturas]], "impresas": [int|None], "offset": int|None}` — the `.txt` split by
    PAGE (#492), memoised.

    `pdftotext` leaves one form feed per page (AUD-165) and `extract_fulltext` keeps it, so *on
    which page is this quote* is decidable on an artefact the vault already has. Each page is
    normalized with `source_texts`, i.e. with the same column de-interleaving (#275/#332) the
    whole-file reading uses: a quote that only appears once the columns are split has to be found
    here too, or the check would report the layout as a wrong locator.

    `{"paginas": [], "impresas": [], "evidencia": [], "offset": None}` when there is no `.txt` on
    disk — *not evaluable*, never «the
    page is wrong».
    """
    clave = (str(cfg.FULLTEXT), bibcode)
    if clave in cfg._PAGINAS_CACHE:
        return cfg._PAGINAS_CACHE[clave]
    txts = sorted(cfg.FULLTEXT.glob(f"*/{bibcode}.txt")) if cfg.FULLTEXT.exists() else []
    out = {"paginas": [], "impresas": [], "evidencia": [], "offset": None}
    if txts:
        try:
            crudas = txts[0].read_text(encoding="utf-8", errors="replace").split("\f")
        except OSError:
            crudas = []
        if crudas:
            out = {"paginas": [source_texts(p) for p in crudas],
                   "impresas": printed_pages(crudas),
                   "evidencia": page_number_evidence(crudas),
                   "offset": printed_page_offset(crudas)}
    cfg._PAGINAS_CACHE[clave] = out
    return out


def quote_pages(quote: str, bibcode: str) -> dict:
    """`{"paginas": [índice], "impresas": [etiqueta], "motivo": str|None}` — where in the `.txt` the
    quote falls and what those pages PRINT (#492, extracted by #494).

    One implementation for its two readers: the verdict of #492 judges a locator against it, and the
    re-reading package of #494 uses it as the **GUIDE** of which page to open. They have to look at
    the same thing, or the guide would point somewhere the check does not (#324).

    ⛔ `motivo` carries the reason it could NOT be located (D-43), which is not the same as «the
    locator is wrong»: no `.txt` on disk, or a quote the degraded INDEX does not have (#205, whose
    silence proves nothing, #321). The caller decides what to do with the difference.

    ⚠ `impresas` leaves out the pages that print nothing, so it can be shorter than `paginas` — and
    the pairing is by position among the pages that DO carry a number, never by index."""
    pag = fulltext_pagination(bibcode)
    paginas = pag["paginas"]
    if not paginas:
        return {"paginas": [], "impresas": [], "motivo": f"{bibcode} no tiene `.txt` en disco"}
    halladas = [i for i, lecturas in enumerate(paginas, 1)
                if any(quote_found(quote, lectura) for lectura in lecturas)]
    if not halladas:
        return {"paginas": [], "impresas": [],
                "motivo": f"la cita no está en ninguna página del `.txt` de {bibcode} (índice "
                          f"degradado, #205: su silencio no prueba nada)"}
    # #492 (defecto B) — la página impresa se lee DONDE cae la cita, no de un offset global: en un
    # libro con numeración por capítulo el offset único marcaba 94 MAL, los 94 falsos.
    impresas = [pag["impresas"][i - 1] for i in halladas]
    return {"paginas": halladas, "impresas": [n for n in impresas if n is not None], "motivo": None}


def quote_page_verdict(quote: str, bibcode: str, rangos: list) -> tuple:
    """Is the page locator pointing at the page the quote is ON? (#492/#500)

    `rangos` is the list of `(from, to)` ranges `page_locators_after` read —ALL the pages the
    locator names, a single page being `(N, N)`—.

    ⛔ **The most decidable half of a pair, and no layer looked at it.** `verify-citations` judges
    the claim against its source, `quote_verdict` judges the CHAIN of the quote, and #436 says as much
    in writing: *«…ninguna capa mira el localizador»*. And the locator is what lets whoever CHECKS
    the claim find it in the PDF on disk, while the `.txt` knows which page the quote is on.
    Measured on a real vault: **104 of 893** locators point at a REPLACED document and 12 of
    190 were wrong in a note that had passed `audit-note`, `lint --cierre` at 0 and 239/239 pairs
    `soportada`.

    Three states, and the one that is not a finding carries its reason:

      · `ok` — the quote IS on the page the locator names, by either numbering (the sheet's printed
        number or the PDF index). ⛔ #500: which of the two is not the question. Asking it cost 413
        hand-fixed locators on a real vault for zero reader value —the claim was findable before
        and after— while the half that does matter, `mal`, is identical under both rules.
      · `mal` — the quote sits on another page, and the detail carries the page it sits on. With
        that, the `_paginacion` debt of #436 stops being global and becomes a list of locators with
        their new page.
      · `no_evaluable` — with its reason (D-43): no `.txt` on disk, the quote is not in it (a
        degraded INDEX, #205, whose silence proves nothing, #321), or the locator matches neither
        numbering and none can be derived, so there is nothing to decide it against.

    ⛔ It never accuses on silence, and it is **not** blocking: a false positive on this gate stops
    operations (#323), and the population it looks at —every quote carrying a locator— is the
    largest of the vault.

    @inv INV-155"""
    ubic = quote_pages(quote, bibcode)
    if ubic["motivo"]:
        return "no_evaluable", {"motivo": ubic["motivo"]}
    pag = fulltext_pagination(bibcode)
    halladas, con_numero = ubic["paginas"], ubic["impresas"]
    det = {"paginas": halladas, "offset": pag["offset"], "impresas": con_numero}

    def _en_rango(pagina):
        """Is this page inside ANY of the ranges the locator names? (defecto A: all of them count).

        ⛔ Across NUMBERINGS nothing is inside anything (#496): `p. 45` over the page that prints
        `L45` is not a hit — they are different pages of the same document."""
        lab = page_label(pagina) if isinstance(pagina, tuple) else str(pagina)
        return any(lab in page_span(a, b) for a, b in rangos)
    # #493 — la primera rama: el número que el localizador declara está IMPRESO como número de
    # página en la cabecera o el pie de la página donde cae la cita (`page_number_evidence`, no
    # cualquier entero). Es el caso del capítulo con título corrido en la cabecera: la página lleva
    # su número y las vecinas no, así que la consecutividad no lo confirma y el offset lo desmentía
    # — y por eso sigue siendo una rama propia aunque hoy las tres devuelvan lo mismo.
    # ⛔ #500 — las TRES formas de estar en la página que el localizador nombra valen igual: el
    # número impreso en la hoja donde cae la cita, la numeración impresa derivada, y el índice del
    # PDF. Distinguirlas era decidir una CONVENCIÓN de escritura, no un hecho.
    if (any(_en_rango(n) for i in halladas for n in pag["evidencia"][i - 1])
            or any(_en_rango(n) for n in con_numero)
            or any(_en_rango(i) for i in halladas)):
        return "ok", det
    if not con_numero:
        det["motivo"] = (f"la cita está en la(s) página(s) {', '.join(map(str, halladas))} del PDF "
                         f"de {bibcode} y ese `.txt` no tiene numeración impresa derivable: el "
                         f"localizador no se puede decidir")
        return "no_evaluable", det
    return "mal", det

def note_own_bibcode(note: Path, fm) -> str:
    """The bibcode a PAPER note IS, for quote attribution — `""` for any other note (#373/#394).

    In a paper note the bibcode is the note itself, not a `[[wikilink]]`, so the transcriptions in
    its `## Vista` have no adjacent source and no layer was looking at them: measured on a real
    vault, 3838 quotes of >=40 chars over 159 notes, of which the verify fan-out saw 11 (there is no
    pair without a `[[bibcode]]`).

    The frontmatter wins over the stem because `--rename-paper` moves the file and the identity of
    an extraction is the `bibcode` INSIDE it (#228/#374); the stem is the fallback for the note the
    migrator has not reached yet.

    ⚠ Takes the ALREADY PARSED frontmatter, never the text: the lint parses each note once and
    `tests/poblada/test_escala.py::test_lint_una_pasada_de_yaml` ratchets that (a re-parse in here
    took the corpus from ~2.0 to over 2.3 `yaml.safe_load` per note — caught by the poblada tier,
    green in tier 0)."""
    if note.parent != cfg.PAPERS:
        return ""
    return str((fm or {}).get("bibcode") or "").strip() or note.stem


def with_own_bibcode(bibs, own: str) -> list:
    """Adds the note's own bibcode to the adjacent candidates. ⛔ ADDS — never replaces (#373/#394).

    Measured on a real vault: a row of the view quotes its own paper and mentions ANOTHER one in a
    neighbouring cell («sobre esto se construye [[X]]»); with *"the adjacent one wins"* that mention
    stole the attribution — 5 findings, 5 of them false, and the message named the right source
    (the failure mode of #325 inside a table). With the union there is no false accusation in either
    direction: a quote from another source is backed by its own extraction, and one altered with
    respect to the note's own subject still diverges against the subject's.

    ONE implementation for the two gates that judge the same quote (#324): the lint reported these
    five as backlog while `contrast --validar-todo` cleared them, and two verdicts on one quote is
    the divergence #324 declared forbidden."""
    bibs = list(bibs)
    return bibs if not own or own in bibs else [*bibs, own]


#: #453/#454 · las dos marcas que abren el bloque de salvedades de una `## Vista`. Viven acá —y no
#: en el cosechador que las escribe— porque las leen los DOS gates de citas: el bloque es el único
#: que la máquina estampa **desde la extracción** dentro de una sección que `verify-citations` sí
#: contrasta, y ésa es la asimetría que produce #454.
SALVEDAD_MARCAS = ("**Salvedades (verificadas contra el archivo):**",
                   "**Salvedades (⚠ NO VERIFICADAS — juicio del extractor):**")

#: #453 · el bloque PELADO anterior a #213, que ya no se escribe y sigue en las notas viejas. Se
#: RECONOCE aparte de las dos de arriba: escribirlo otra vez sería reintroducir el schema que #213
#: retiró, pero no reconocerlo hace que el re-estampado no encuentre el bloque y lo AGREGUE abajo —
#: medido, **25 notas duplicadas** en un barrido, con el lint mostrándolo en lockstep («Salvedades
#: sin la marca de #213» 25 → 0 y «párrafo duplicado» 0 → 25, las mismas notas) y un falso verde
#: doble: la nota sale de la categoría de #213 **justo porque** ahora tiene el bloque marcado, con
#: el contenido repetido abajo.
SALVEDAD_MARCA_LEGACY = "**Salvedades:**"

#: Lo que se LEE como apertura de un bloque de salvedades. `SALVEDAD_MARCAS` es lo que se ESCRIBE:
#: la asimetría es el migrador de #213 —el bloque viejo se reconoce para reemplazarlo por el nuevo—
#: y no una capa de compatibilidad (el schema viejo no vuelve a salir de ningún escritor).
SALVEDAD_MARCAS_LEIDAS = (*SALVEDAD_MARCAS, SALVEDAD_MARCA_LEGACY)


def quote_from_stamped_block(text: str, intro: str | None = None) -> bool:
    """Did the MACHINE copy this block out of the extraction? (#454)

    ⛔ The one predicate both quote gates use (#324). It matters because `quote_verdict` treats the
    extraction as a WITNESS —«the transcription made while reading the PDF»— and that is true of a
    quote the synthesiser re-typed into a note, not of one `harvest_views` copied verbatim out of
    the JSON: there the witness and the accused are the same file, so step 2 always finds it and
    answers `txt_degradado` («the note is right, the index lost it») over a quote nobody ever
    checked. Measured: a quote the source does not say —«…it converges globally» where the paper
    says «…the convergence is proven globally», 1 occurrence of the note's in the `.txt` and 0 of
    the JSON's— published with `lint` rc 0 and `contrast --validar-todo` rc 0.

    ⚠ The caveat block is the only stamped one INSIDE a section the fan-out has to contrast
    (`## Vista`); `SECCIONES_ESTAMPADAS` are already out of it (#214), and that asymmetry is the
    whole case."""
    return any(str(intro or "").lstrip().startswith(m) or m in (text or "")
               for m in SALVEDAD_MARCAS_LEIDAS)


def quote_verdict(quote: str, cited, note_bibs, txt_texts: dict, *, ambiguo: bool = False,
                  copiada: bool = False) -> tuple:
    """Is this quote altered, or is the artefact the problem? ONE implementation (#324).

    ⛔ `lint.collect` and `contrast.validar` were deciding this with separate code and **already
    diverged**: measured the same day over the same vault, 13 against 12. The extra one was a
    FALSE positive — a piece of A&A boilerplate («only available in electronic form at the CDS»)
    that is verbatim in the `.txt` of the paper the note cites and that the *selective* extraction
    (#188) of that paper did not transcribe, while another paper's extraction did. `lint` never saw
    it because it tests against the cited source's `.txt` **first**; `contrast` went straight to
    comparing extractions and called it a wrong attribution. It is the very shape of error #321 had
    just fixed —judging against an artefact that does not contain what is being asked of it—
    displaced into the tool, and it hurts more there: since #323 `--validar-todo` is a mandatory
    closing step with exit ≠ 0, so a false positive **stops operations**.

    Order (each step is a different job, so it is not interchangeable):

      1. the quote is in the `.txt` of ITS source → `en_su_txt`: nothing to say, whatever the
         extractions hold. #205 makes the `.txt` a degraded INDEX, not a bad witness: finding the
         string there proves the sentence is in THAT paper.
      2. an extraction of its source has it → `txt_degradado`: the note is right, the index lost it
         — unless the `.txt` of that SAME source carries the opening and continues differently in
         prose, and then it is `txt_acusa` (#333): two readings of one PDF disagree, go to the page.
         It does not block, on purpose — the `.txt` is a degraded index, and since #323 this gate
         stops operations.
      3. the source says it and the `.txt` breaks it apart → `txt_parte` (#288).
      4. positive evidence that it moved or was completed → `alterada` (blocking, #321).
      5. sources on disk and nothing else → `no_verbatim`; no sources → `no_evaluable` (D-43).
      4b. (#437) the prefix evidence comes ONLY from extractions marked `_paginacion` —they
         describe a document that was replaced— → the `.txt` of the new document is the judge:
         `alterada` if it carries the opening and continues differently (`txt_nuevo`), else
         `extraccion_vieja` (mark, never «passes»). The old reading cannot accuse the new PDF.

    `txt_texts` is injected —`{bibcode: [readings]}`— because each caller obtains it differently;
    `ambiguo` reproduces #316 (a quote with no adjacent `[[bibcode]]` was tested against every
    source of the block, so the finding is weaker and never blocks).

    Returns `(veredicto, detalle)`."""
    fuentes = {b: ts for b, ts in (txt_texts or {}).items() if ts}
    if any(quote_found(quote, t) for ts in fuentes.values() for t in ts):
        return "en_su_txt", {}
    # ⛔ #454 — la cita que la MÁQUINA copió de la extracción no se juzga contra la extracción: ahí
    # el testigo y el juzgado son el mismo archivo, y el paso 2 la aprobaría siempre. Su único
    # testigo independiente es el `.txt` (paso 1, arriba); si calla, es **no evaluable con su
    # motivo** (D-43), nunca `txt_degradado`.
    if copiada:
        return "sin_testigo_propio", {}
    extracciones = {b: extraction_texts(b) for b in (cited or [])}
    en_extraccion = sorted(b for b, ts in extracciones.items()
                           if any(quote_found(quote, t) for t in ts))
    if en_extraccion:
        # #333 — el `.txt` del MISMO bibcode, no el de otro: la evidencia es entre los dos
        # artefactos de una fuente (`pdftotext` contra el LLM), y cruzarla con otra fuente sería
        # fabricar la atribución que este framework más persigue.
        for b in en_extraccion:
            acusa = txt_accuses(quote, fuentes.get(b) or [])
            if acusa:
                return "txt_acusa", {"en_extraccion": en_extraccion, "bib": b, **acusa}
        return "txt_degradado", {"en_extraccion": en_extraccion}
    if any(quote_found_degraded(quote, t) for ts in fuentes.values() for t in ts):
        return "txt_parte", {}
    otro = [b for b in sorted(set(note_bibs or ()) - set(cited or ()))
            if any(quote_found(quote, t) for t in extraction_texts(b))]
    prefijo = (len(quote) > CITA_PREFIJO
               and any(quote_found(quote[:CITA_PREFIJO], t)
                       for ts in extracciones.values() for t in ts))
    # #318 — «no está en la extracción» sólo significa algo si la extracción EXISTE: una fuente
    # off-ADS sin extraer, o una bóveda pre-#311 sin migrar, no es una cita alterada. (Y esto ya
    # implica `fuentes` no vacío, así que agregarlo sería una condición que no decide nada, #319.)
    con_extraccion = any(extracciones.get(b) for b in fuentes)
    if con_extraccion and not ambiguo and (otro or prefijo):
        # #437 — la extracción que lleva el prefijo describe un documento que YA NO ESTÁ (el PDF se
        # reemplazó: `_paginacion`). Su cola distinta no es evidencia contra el documento en disco:
        # es la redacción del preprint contra la del publicado (medido: 23 pares de copyedición, la
        # nota correcta bloqueaba y la incorrecta pasaba). Ahí el único testigo del documento nuevo
        # es su `.txt`: si TRAE el arranque y sigue distinto, la cita sí está alterada contra lo que
        # hay en disco y bloquea; si calla, la marca `⚠verificar en el PDF` — nunca «pasa». La
        # atribución movida (`otro`) no depende del documento y bloquea igual.
        # (acá `otro or prefijo` ya es verdad, así que `not otro` implica `prefijo`; y como
        # `prefijo` se midió sobre ESTAS extracciones, `viejas ∪ vigentes` no puede ser vacío —
        # dos condiciones que no deciden nada, #319)
        if not otro:
            viejas = [b for b in cited or [] if extraction_depaginated(b)
                      and any(quote_found(quote[:CITA_PREFIJO], t) for t in extracciones.get(b, []))]
            vigentes = [b for b in cited or [] if b not in viejas
                        and any(quote_found(quote[:CITA_PREFIJO], t) for t in extracciones.get(b, []))]
            if not vigentes:
                for b in viejas:
                    acusa = txt_accuses(quote, fuentes.get(b) or [])
                    if acusa:
                        return "alterada", {"otro_bib": [], "prefijo": True, "txt_nuevo": b, **acusa}
                return "extraccion_vieja", {"bibs": viejas}
        return "alterada", {"otro_bib": otro, "prefijo": prefijo}
    if fuentes:
        return "no_verbatim", {}
    return "no_evaluable", {}


#: #495 — every mark that declares «this extraction describes a document that is NO LONGER on
#: disk». `_paginacion` opens the debt (`replace_pdf`, #436) and the repagination of #494 closes
#: it with `_repaginado` / `_repaginado_parcial` — but closing it only updates the LOCATORS, never
#: the transcription: the prose keeps the wording the extractor read off the replaced PDF. Keying
#: the exemption on the opening mark alone switched it off exactly when the debt was paid well
#: (measured in a live vault: 0 → 4 altered quotes, rc 0 → 1, three notes that nobody had touched,
#: all four of them preprint→published copyediting — the very population #437 exists not to accuse).
REPLACED_DOC_MARKS = ("_paginacion", "_repaginado", "_repaginado_parcial")

#: #494 · el subconjunto que dice que la deuda de paginación sigue ABIERTA: sus localizadores son
#: los del documento anterior. `_repaginado` no está —ahí la relectura ya los actualizó—, y ésa es
#: justo la pregunta que NO se puede contestar con `REPLACED_DOC_MARKS`: aquélla dice «la
#: transcripción describe un documento que ya no está» (y sobrevive al cierre, #495), ésta «los
#: localizadores todavía no se releyeron». Dos preguntas distintas sobre la misma marca, que es por
#: lo que el lint contaba deuda con el mismo campo con el que `contrast` eximía una cita.
PAGINATION_OPEN_MARKS = ("_paginacion", "_repaginado_parcial")


def extraction_pagination_open(bibcode: str) -> bool:
    """Does any extraction of this bibcode still owe the re-reading of its LOCATORS? (#494)

    The twin of `extraction_depaginated` on the other question: that one asks whether the
    TRANSCRIPTION describes a replaced document (and stays true after the debt is paid, #495), this
    one whether the LOCATORS are still the old document's (and stops being true when they are
    re-read). `_repaginado_parcial` counts: a round that closed some items and left others named in
    `pendientes` has not closed the debt."""
    return any(any(cfg.as_map(d.get(m)) for m in PAGINATION_OPEN_MARKS)
               for d in _extraction_index().get(bibcode, []) if isinstance(d, dict))


def extraction_depaginated(bibcode: str) -> bool:
    """Does any extraction of this bibcode describe a REPLACED PDF? (#437, family per #495)

    `replace_pdf` stamps `_paginacion` (#436) because `raw/extraccion/**` is versioned and not
    regenerable (#311): the reading stays, the document it read is gone. For `quote_verdict` that
    means the extraction can still prove a quote is in that paper, but its divergent tail cannot
    accuse the document on disk — the tail may be the preprint's wording against the publisher's.

    ⛔ Any of `REPLACED_DOC_MARKS` answers yes, because repaginating (#494) rewrites the locators
    and leaves the transcription untouched: the reason the tail cannot judge survives the debt."""
    return any(any(cfg.as_map(d.get(m)) for m in REPLACED_DOC_MARKS)
               for d in _extraction_index().get(bibcode, []) if isinstance(d, dict))


def quote_found(quote: str, source_norm: str) -> bool:
    """Is this quote in that (already normalized) source text? All its fragments must be."""
    for variante in quote_variants(quote):
        frags = quote_fragments(variante)
        if frags and all(f in source_norm for f in frags):
            return True
    return False


import lib_config as cfg   # at the END on purpose: no cycle at import time (see module docstring)
