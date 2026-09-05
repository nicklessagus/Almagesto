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


def quote_verdict(quote: str, cited, note_bibs, txt_texts: dict, *, ambiguo: bool = False) -> tuple:
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

    `txt_texts` is injected —`{bibcode: [readings]}`— because each caller obtains it differently;
    `ambiguo` reproduces #316 (a quote with no adjacent `[[bibcode]]` was tested against every
    source of the block, so the finding is weaker and never blocks).

    Returns `(veredicto, detalle)`."""
    fuentes = {b: ts for b, ts in (txt_texts or {}).items() if ts}
    if any(quote_found(quote, t) for ts in fuentes.values() for t in ts):
        return "en_su_txt", {}
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
        return "alterada", {"otro_bib": otro, "prefijo": prefijo}
    if fuentes:
        return "no_verbatim", {}
    return "no_evaluable", {}


def quote_found(quote: str, source_norm: str) -> bool:
    """Is this quote in that (already normalized) source text? All its fragments must be."""
    for variante in quote_variants(quote):
        frags = quote_fragments(variante)
        if frags and all(f in source_norm for f in frags):
            return True
    return False


import lib_config as cfg   # at the END on purpose: no cycle at import time (see module docstring)
