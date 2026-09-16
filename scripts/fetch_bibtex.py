"""Brings the OFFICIAL BibTeX entry of each paper into its note — never one written by a model.

Uso:
    python scripts/fetch_bibtex.py                    # toda la bóveda (pasada periódica)
    python scripts/fetch_bibtex.py --slug <slug>      # sólo los papers de un ingest
    python scripts/fetch_bibtex.py --paper <bibcode>  # uno solo
    python scripts/fetch_bibtex.py --force            # re-bajar también los que ya lo tienen

#397 — la ficha guardaba campos sueltos (`title`, `first_author`, `year`, `doi`, `bibstem`) y no la
REFERENCIA. Quien escribe un informe tenía que rearmar la entrada BibTeX, y el material del que la
armaba era la ficha más lo que recordara el modelo: una entrada redactada de memoria sale plausible
—volumen y páginas verosímiles— y nadie la vuelve a mirar. Es la regla de método nº 4 sobre el dato
que termina impreso. La regla #0 dice que todo lo que la bóveda afirma está respaldado por una
fuente citable; la cita en sí era lo único que se reconstruía.

Medido contra el `.bib` de una tesis real: 81 entradas, 63 con DOI, y cotejarlas con las 189 fichas
exigió resolver por DOI y matching difuso de título — 26 quedaron sin ficha y 8 papers tenían id
distinto entre dos instancias de la misma bóveda.

⛔ **La cascada, en orden, y el cuarto caso es un HUECO, no un relleno:**

1. `bibcode` de ADS → `POST /v1/export/bibtex`, la exportación autoritativa (`ads`).
2. sin bibcode pero con `doi` → content negotiation contra `https://doi.org/<DOI>`
   (`Accept: application/x-bibtex`), que contesta el registrante: `crossref` | `datacite`, o `doi`
   si la agencia no se pudo determinar.
3. sólo `arxiv_id` → la exportación que publica arXiv (`arxiv`).
4. nada de lo anterior (un libro, un manual de instrumento, un PDF off-ADS) → **el campo queda
   vacío**. Un hueco declarado es correcto; una entrada inventada es el defecto que este script
   existe para no cometer.

⚠ Y una respuesta con status 200 no alcanza: `doi.org` contesta **404 con una página HTML** cuando
el DOI no existe, así que se exige además el `Content-Type` de BibTeX. Guardar ese HTML en el
frontmatter sería exactamente el bloque inventado, con la firma de una descarga.

⛔ **Y la exportación se pide en la forma en que se PEGA (#471).** ADS exporta por defecto la revista
como macro de AASTeX (`journal = {\\aap}`), que sin `aas_macros.sty` compila VACÍO; medido en una
instancia, 126 de 219 bloques `ads`. La salida NO es una tabla macro → nombre en el repo —eso es
redactar un campo de la cita, lo que #397 prohíbe—: se pide `journalformat: 3` (nombre completo) y
un bloque con macro cuenta como **pendiente**, así que re-correr la cadena lo re-baja sin `--force`.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_config as cfg   # noqa: E402

ADS_EXPORT = "https://api.adsabs.harvard.edu/v1/export/bibtex"
DOI_RESOLVER = "https://doi.org/{doi}"
DOI_RA = "https://doi.org/ra/{doi}"
ARXIV_BIBTEX = "https://arxiv.org/bibtex/{arxiv_id}"
CROSSREF_SEARCH = "https://api.crossref.org/works"

#: Lo que el resolver tiene que devolver para que la respuesta sea una entrada y no una página de
#: error. `doi.org` sirve su 404 como `text/html` con status 404, pero el chequeo va por los dos
#: lados a propósito: un proxy que devuelva 200 con HTML no puede terminar en el frontmatter.
BIBTEX_CT = "application/x-bibtex"

#: #471 — `journalformat` de la exportación de ADS: 1 = macro de AASTeX (`\\aap`, el default),
#: 2 = abreviatura, 3 = nombre completo. Se pide el 3 porque es el único que se pega tal cual en
#: un `.bib` que no carga `aas_macros.sty`; el bloque `bibtex` es lo que ADS devolvió, sin tocar.
ADS_JOURNALFORMAT = 3

#: Cuántos bibcodes por request a ADS. La exportación acepta listas; el tope es para que un fallo
#: de red no tire una bóveda entera de golpe y para que el reporte diga por dónde iba.
ADS_CHUNK = 50


def split_entries(export: str) -> dict:
    """`{clave de cita: entrada}` de una exportación BibTeX con varias entradas.

    ⛔ ADS **no** devuelve las entradas en el orden en que se pidieron (medido contra el servicio
    real: dos bibcodes, vuelven al revés), así que emparejarlas por posición adjudicaría la entrada
    de un paper a otro — la atribución falsa que la regla de método nº 4 llama peor que el vacío.
    La clave de cita de ADS ES el bibcode, así que se indexa por ella."""
    out: dict = {}
    actual, buf = "", []
    for linea in (export or "").split("\n"):
        if linea.lstrip().startswith("@"):
            if actual:
                out[actual] = "\n".join(buf).strip() + "\n"
            buf = [linea]
            cabeza = linea.split("{", 1)
            actual = cabeza[1].rstrip().rstrip(",").strip() if len(cabeza) > 1 else ""
        elif actual:
            buf.append(linea)
    if actual:
        out[actual] = "\n".join(buf).strip() + "\n"
    return out


def ads_bibtex(bibcodes: list, token: str) -> tuple:
    """`({bibcode: entrada}, [errores], {bibcodes sin consultar})` — la exportación oficial de ADS,
    en tandas de `ADS_CHUNK`.

    Un error de red devuelve lo que sí se pudo traer y lo DECLARA: la alternativa es que una caída a
    mitad de camino se lea como «esos papers no tienen BibTeX», que es el falso limpio de siempre.

    ⛔ Y los declara POR BIBCODE (#468), no sólo como texto de error: `errores` saca la corrida en
    rc 2, pero cada nota de la tanda caída seguía recorriendo la cascada y terminaba con su hueco
    ESTAMPADO —`sin_bibtex`, que el lint titula «decisión registrada, no es deuda»— sobre una
    consulta que nunca contestó. El tercer elemento es lo que le permite al llamador saltearlas."""
    out, errores, sin_consultar = {}, [], set()
    # #399 — sólo lo que TIENE forma de bibcode. Con las claves sintéticas adentro, ADS contesta 404
    # al lote entero y la corrida anunciaba «ADS export falló» sobre papers que sí se habían
    # evaluado bien: el ⛔ afirmaba «no evaluado» de algo evaluado, que es la confusión que este
    # script existe para separar (D-43).
    reales = [b for b in bibcodes if cfg.is_ads_bibcode(b)]
    for i in range(0, len(reales), ADS_CHUNK):
        tanda = reales[i:i + ADS_CHUNK]
        try:
            r = requests.post(ADS_EXPORT,
                              headers={"Authorization": f"Bearer {token}",
                                       "Content-Type": "application/json"},
                              json={"bibcode": tanda, "journalformat": ADS_JOURNALFORMAT},
                              timeout=60)
        except requests.RequestException as exc:
            errores.append(f"ADS export no contestó para {len(tanda)} bibcode(s) "
                           f"({tanda[0]}…): {exc.__class__.__name__} — esos papers quedaron SIN "
                           f"consultar")
            sin_consultar.update(tanda)
            continue
        # ⛔ #399 — el 404 de un lote es una RESPUESTA: «ninguno de éstos está en ADS», que es un
        # hueco legítimo y lo clasifica la cascada. Sólo el resto —timeout, 5xx, JSON roto— deja
        # papers sin consultar, y ésa es la única condición que puede sacar la corrida en rc 2.
        if r.status_code == 404:
            continue
        try:
            r.raise_for_status()
            out.update(split_entries(r.json().get("export") or ""))
        except (requests.RequestException, ValueError) as exc:
            errores.append(f"ADS export falló para {len(tanda)} bibcode(s) "
                           f"({tanda[0]}…): {exc.__class__.__name__} — esos papers quedaron SIN "
                           f"consultar")
            sin_consultar.update(tanda)
    return out, errores, sin_consultar


def doi_agency(doi: str) -> str:
    """`crossref` | `datacite` | `doi` — quién registró el DOI, para no adivinar la procedencia.

    El tercer valor es el estado honesto: se bajó del resolver y la agencia no se pudo determinar
    (D-43). Poner `crossref` por default sería declarar una fuente que nadie verificó."""
    try:
        r = requests.get(DOI_RA.format(doi=doi), timeout=20)
        r.raise_for_status()
        ra = str((r.json() or [{}])[0].get("RA") or "").strip().casefold()
    except (requests.RequestException, ValueError, IndexError, AttributeError):
        return "doi"
    return ra if ra in ("crossref", "datacite") else "doi"


def _utf8(r) -> str:
    """The body decoded as UTF-8 explicitly, never `r.text` (#419).

    ⛔ `requests` decodes `.text` with the charset of the header and, when the response does not
    declare one, it GUESSES. Crossref's BibTeX export declares none, so `.text` came back as
    Windows-1252: measured on a real vault, **17 of 30** Crossref entries were stored with mojibake
    and **2 of them in the author field** — `Hyv{\"a}rinen` is the surname that gets PRINTED in the
    bibliography of whoever cites from the vault. #397 says the entry is brought VERBATIM from the
    official export; a badly decoded export is not verbatim.

    `errors="replace"` rather than raising: a mangled byte should degrade one character, not throw
    away an entry that is otherwise correct — and the mojibake detector of the lint sees it."""
    return (r.content or b"").decode("utf-8", errors="replace")


def doi_bibtex(doi: str) -> tuple:
    """`(entrada, fuente, sin_medir)` por content negotiation contra `doi.org` (#468).

    ⛔ Se exige status 2xx **y** `Content-Type` de BibTeX: el resolver contesta su «DOI Not Found»
    como HTML, y ese HTML en el frontmatter sería una cita inventada con cara de descargada.

    ⛔ `sin_medir` separa **«el resolver no contestó»** de **«contestó que no hay»** (D-43). Los dos
    devuelven entrada vacía, y sin el tercer elemento el llamador estampaba el hueco declarado sobre
    una consulta que nunca ocurrió: el 404 del resolver ES una respuesta y clasifica; el timeout no.
    Un status raro con el `Content-Type` equivocado tampoco es red caída — es el resolver diciendo
    que no tiene la entrada, y ahí el hueco es medido."""
    try:
        r = requests.get(DOI_RESOLVER.format(doi=doi), headers={"Accept": BIBTEX_CT},
                         timeout=30, allow_redirects=True)
    except requests.RequestException as exc:
        return "", "", f"`doi.org` no contestó por `{doi}` ({exc.__class__.__name__}): no consta"
    if r.status_code >= 500:                   # el 5xx no dice nada del DOI: no se midió
        return "", "", f"`doi.org` no contestó por `{doi}` (HTTP {r.status_code}): no consta"
    if not r.ok or BIBTEX_CT not in (r.headers.get("Content-Type") or ""):
        return "", "", ""
    entrada = _utf8(r).strip()
    return (entrada + "\n", doi_agency(doi), "") if entrada.startswith("@") else ("", "", "")


def arxiv_bibtex(arxiv_id: str) -> tuple:
    """`(entrada, sin_medir)` — la exportación que publica arXiv para ese id (#468).

    Mismo criterio que el carril del DOI en las dos mitades: lo que no arranca con `@` no es una
    entrada, venga con el status que venga; y una caída de red se DECLARA aparte en vez de volver
    como un vacío que el llamador persistiría como hueco medido (D-43)."""
    try:
        r = requests.get(ARXIV_BIBTEX.format(arxiv_id=arxiv_id), timeout=30)
    except requests.RequestException as exc:
        return "", f"arXiv no contestó por `{arxiv_id}` ({exc.__class__.__name__}): no consta"
    # ⛔ El 4xx ES una respuesta —«ese id no está»— y clasifica como hueco medido; el 5xx no dice
    # nada del paper, así que sale por el carril de «no se midió» (mismo corte que el 404 de ADS).
    if r.status_code >= 500:
        return "", f"arXiv no contestó por `{arxiv_id}` (HTTP {r.status_code}): no consta"
    if not r.ok:
        return "", ""
    entrada = _utf8(r).strip()
    return (entrada + "\n" if entrada.startswith("@") else ""), ""


def _family(nombre: str) -> str:
    """The family name out of whatever `first_author` holds: `Mayor, Michel` or `Michel Mayor`."""
    nombre = str(nombre or "").strip()
    if "," in nombre:
        return nombre.split(",", 1)[0].strip()
    return nombre.split()[-1] if nombre.split() else ""


def doi_candidate(title: str, first_author: str, year=None) -> tuple:
    """`(doi, motivo, sin_medir)` — PROPOSES a DOI for a note that has none. Never stamps one (#397).

    The off-ADS rail declared the hole without ever asking whether the DOI exists: measured on a
    real vault, `2011Naik` is not case 4 of the cascade (no official source) but case 2 — Crossref
    has `10.5772/52324` and the note simply does not carry it.

    ⛔ The match is EXACT on the normalised title **and** on the first author's family name, and
    that severity is the point: this repo's own doctrine forbids resolving by title —`discover`
    measured it at 18 of 25 resolved with **2 pointing at another work**— so anything short of an
    exact hit returns the reason and no candidate. Verified against the live service: an exact title
    resolves (Mayor 1995 → `10.1038/378355a0`), while a remembered one returns three plausible
    papers, none of them the target — which is the failure this strictness exists to refuse.

    `year` is a tie-breaker with ±1 slack, because the deposit and the publication disagree by a
    year often enough (`2011Naik` declares 2012 in its own frontmatter).

    ⛔ Two stages (#466): the server-side author filter is tried first and then dropped, because
    Crossref does not fold diacritics when SEARCHING while the local check does when COMPARING.
    The reason it returns names the stages and what each brought, so a hole is never blamed on the
    title when what failed was a query nobody sees.

    ⛔ The third element is the NETWORK signal (#468). `_crossref_try` already tells «the service did
    not answer» apart from a verdict, and this function already stopped there — but it returned the
    reason through the same slot as a measured one, so `main` concatenated it into a hole it then
    STAMPED (`sin_bibtex`, which the lint titles «decisión registrada, no es deuda»). The distinction
    has to be in the field, not in the prose: whoever reads it is a category, not a person."""
    titulo, familia = str(title or "").strip(), _family(first_author)
    if not titulo or not familia:
        return "", "sin `title` o sin `first_author`: no hay con qué preguntar", ""
    # ⛔ DOS ETAPAS (#466). La query RECUPERA y el chequeo DECIDE, así que el filtro server-side no
    # puede repetir el criterio que abajo se compara NORMALIZADO: Crossref no pliega la diéresis al
    # buscar, así que `query.author=Hyvarinen` descarta el registro cuyo `family` es «Hyvärinen»
    # —el que `cfg.method_key` aceptaría— antes de que el chequeo lo vea. Medido contra el servicio
    # real: con el filtro, cinco resultados y ninguno con el título exacto; sin él, el título exacto
    # aparece con `family: "Hyvärinen"`. La etapa 1 conserva el recall preciso de siempre; la 2
    # rescata ese caso y paga más `rows`, porque sin el filtro compiten más registros por slot (el
    # bueno entró 5º en la sonda). La severidad NO se afloja: sigue exigiendo título exacto Y
    # apellido normalizado, sólo que ahora sobre candidatos que llegaron.
    etapas = (("con `query.author`", {"query.author": familia, "rows": 5}),
              ("sin `query.author` (#466)", {"rows": 20}))
    dudosos, traidos = [], []
    for etiqueta, extra in etapas:
        doi, motivo, items, duda = _crossref_try(titulo, familia, year, extra)
        traidos.append(f"{etiqueta}: {len(items)}")
        if motivo:                             # la red no contestó: no consta, y no se sigue
            return "", motivo, motivo
        if doi:
            return doi, f"título exacto + autor «{familia}» en Crossref [{etiqueta}]", ""
        dudosos += [d for d in duda if d not in dudosos]
    if dudosos:
        return "", "DUDOSO — " + "; ".join(dudosos), ""
    return "", (f"ningún resultado con el título EXACTO en dos etapas ({' · '.join(traidos)}): "
                f"resolvelo a mano — acá no se propone por parecido (#397)"), ""


def _crossref_try(titulo: str, familia: str, year, extra: dict) -> tuple:
    """One Crossref query → `(doi, motivo_de_red, items, dudosos)` (#466).

    Split out of `doi_candidate` so the two stages share ONE judging rule: duplicating it is how
    the strictness of #397/#399 would drift between them. `motivo_de_red` is only for «the service
    did not answer» — the caller stops there instead of declaring a hole the query never measured.
    """
    params = {"query.bibliographic": titulo,
              "select": "DOI,title,author,issued,published-print,published-online", **extra}
    if (correo := cfg.get_mailto()):
        params["mailto"] = correo              # polite pool, opt-in (#: nunca sale de git config)
    try:
        r = requests.get(CROSSREF_SEARCH, params=params,
                         headers={"User-Agent": "Almagesto (https://github.com/nicklessagus/Almagesto)"},
                         timeout=30)
        r.raise_for_status()
        items = (r.json().get("message") or {}).get("items") or []
    except (requests.RequestException, ValueError, AttributeError) as exc:
        return "", f"Crossref no contestó ({exc.__class__.__name__}): no consta", [], []
    dudosos = []
    for it in items:
        cand = ((it.get("title") or [""])[0] or "").strip()
        if cfg.method_key(cand) != cfg.method_key(titulo):
            continue                           # ⛔ título EXACTO normalizado, nunca parecido
        if year:
            # ⛔ Los años que Crossref publica, print primero (`cfg.crossref_years`, #414): `issued`
            # es el MÁS TEMPRANO de print y online, así que en un online-first el candidato bueno
            # queda a dos años del declarado y se descartaba solo.
            años = cfg.crossref_years(it)
            if años and min(abs(int(a) - int(year)) for a in años) > 1:
                continue
        autores = it.get("author") or [{}]
        cr_familia = str(autores[0].get("family") or "").strip()
        if cfg.method_key(cr_familia) != cfg.method_key(familia):
            # ⛔ #399 — el título coincide EXACTO y el autor no: el candidato se IMPRIME como
            # dudoso en vez de callarse. Medido: el registro Crossref de `2011Naik` lleva
            # `family: "R."` —metadata rota del editor— así que el caso que motivó #397 no
            # aparecía en ninguna salida. La severidad no se afloja: sigue sin proponerse como
            # bueno, pero un candidato que nadie ve es indistinguible de no haber buscado.
            dudosos.append(f"`{str(it.get('DOI') or '')}` (título exacto, pero Crossref dice autor "
                           f"«{cr_familia or 's/d'}» ≠ «{familia}»: confirmalo contra la portada)")
            continue
        return str(it.get("DOI") or ""), "", items, dudosos
    return "", "", items, dudosos


def bibtex_for(fm: dict, stem: str, ads_cache: dict, sin_consultar=()) -> tuple:
    """`(entrada, fuente, motivo, sin_medir)` para una nota, recorriendo la cascada declarada.

    `motivo` sólo se puebla cuando NO hay entrada, y dice cuál es el hueco: es la diferencia entre
    «este paper no tiene exportación oficial» y «nadie preguntó».

    ⛔ `sin_medir` es la lista de carriles que NO CONTESTARON (#468), y existe porque los tres de la
    cascada devolvían un vacío indistinguible del hueco: una caída de ADS, de `doi.org` o de arXiv
    caía por el mismo `return` que un libro sin exportación oficial, y el llamador lo PERSISTÍA como
    `sin_bibtex` — el campo que el lint titula «decisión registrada, **no es deuda**». Un 429 movía
    así la nota de la deuda a la decisión firmada sin que nadie decidiera nada, y con `rc 0`. Es
    D-43 un nivel más abajo: un detector que no pudo correr se declara no evaluado y se queda del
    lado de la deuda. Mientras la lista no esté vacía el motivo NO es un veredicto.

    @inv INV-151"""
    bib = str(fm.get("bibcode") or "").strip() or stem
    sin_medir: list = []
    if (entrada := ads_cache.get(bib)):
        return entrada, "ads", "", []
    if bib in sin_consultar:
        sin_medir.append(f"ADS no contestó por `{bib}`: no consta")
    if (doi := str(fm.get("doi") or "").strip()):
        entrada, fuente, no_medido = doi_bibtex(doi)
        if entrada:
            return entrada, fuente, "", []
        if no_medido:
            sin_medir.append(no_medido)
    if (arx := str(fm.get("arxiv_id") or "").strip()):
        entrada, no_medido = arxiv_bibtex(arx)
        if entrada:
            return entrada, "arxiv", "", []
        if no_medido:
            sin_medir.append(no_medido)
    faltan = [c for c, v in (("bibcode ADS", ads_cache.get(bib)), ("doi", fm.get("doi")),
                             ("arxiv_id", fm.get("arxiv_id"))) if not v]
    return "", "", "sin exportación oficial (sin " + ", sin ".join(faltan) + ")", sin_medir


def stamp_bibtex(path: Path, fm: dict, body: str, entrada: str, fuente: str, fecha: str) -> None:
    """Estampa `bibtex` + `bibtex_source` + `bibtex_accessed`, con el mismo escritor quirúrgico que
    usa `check_retractions` (`cfg.stamp_fm_fields`): no re-serializa el YAML, así que la extracción
    LLM que vive abajo queda byte a byte.

    ⚠ `bibtex_accessed` es la fecha de ESTA descarga, no la de hoy en una corrida que no bajó nada
    (#34): sin eso el campo afirma un snapshot que nadie tomó."""
    cfg.stamp_fm_fields(path, fm, body,
                        {"bibtex": entrada, "bibtex_source": fuente, "bibtex_accessed": fecha})


def stamp_bibtex_gap(path: Path, fm: dict, body: str, motivo: str, fecha: str) -> None:
    """Persist the HOLE with its reason: `sin_bibtex` + `bibtex_accessed` of THIS attempt (#467).

    `bibtex_for` computed the reason and its docstring said what for —«the difference between *this
    paper has no official export* and *nobody asked*»— and then threw it away on stdout, so seeing
    it meant re-running the expensive step. `bibtex` is the sixth field of the same family
    (`no_sintetizado` #75, `pending_motivo` #80, `sin_abstract_motivo` #413, `sin_conclusiones`
    #277, `no_vista` #268): a hole the system decides to leave empty records its reason, or it is
    indistinguishable from one nobody looked at — and this is the field that exists so a printed
    citation is not retyped from memory (#397), where that confusion leads straight to the thing
    #397 forbids.

    ⚠ The date is the one of the attempt that produced THIS reason, same rule as `bibtex_accessed`
    (#34): otherwise the note claims an enquiry nobody made."""
    cfg.stamp_fm_fields(path, fm, body,
                        {"sin_bibtex": motivo, "bibtex_accessed": fecha})


def bibtex_closed(fm: dict) -> bool:
    """True when the note's `bibtex` is DONE: present and pasteable as is (#471).

    A block whose journal is an AASTeX macro (`journal = {\\aap}`) compiles empty without
    `aas_macros.sty`, so it is not closed: `main` treats it as pending without `--force`, which is
    what lets the idempotent chain close the backlog the lint names (`bibtex_macro_revista`, same
    function: `cfg.bibtex_journal_macro`)."""
    _btx = str(fm.get("bibtex") or "").strip()
    return bool(_btx) and not cfg.bibtex_journal_macro(_btx)


def notes_to_check(args) -> list:
    """Las notas de paper que esta corrida mira: una (`--paper`), las de un ingest (`--slug`, el
    mismo enumerador que `check_retractions`) o todas."""
    import check_retractions as cr
    if args.paper:
        f = cfg.PAPERS / f"{cfg.note_stem(args.paper)}.md"
        return [f] if f.exists() else []
    if args.slug:
        return cr.slug_notes(args.slug)
    return cfg.note_paths(cfg.PAPERS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--paper", help="un solo bibcode (default: todas las notas de `papers/`)")
    ap.add_argument("--slug", help="sólo los papers de un ingest (modo de la cadena)")
    ap.add_argument("--force", action="store_true",
                    help="re-bajar también las notas que ya tienen `bibtex`")
    args = ap.parse_args()

    notas = notes_to_check(args)
    if not notas:
        cfg.print_seguro("⛔ no evaluado: no hay notas de paper que mirar "
                         "(¿`--paper`/`--slug` equivocado, o bóveda vacía?)")
        return 2

    pendientes, fms, n_macro = [], {}, 0
    for f in notas:
        text = f.read_text(encoding="utf-8")
        fm = cfg.split_fm(text) or {}
        # #471 — un bloque con la revista como macro NO está cerrado: no se pega. Cuenta como
        # pendiente sin `--force`, para que re-correr la cadena (idempotente) cierre el backlog.
        if bibtex_closed(fm) and not args.force:
            continue
        if str(fm.get("bibtex") or "").strip() and not bibtex_closed(fm):
            n_macro += 1
        fms[f] = (fm, text)
        pendientes.append(f)
    if not pendientes:
        cfg.print_seguro(f"bibtex: {len(notas)} nota(s) miradas, todas ya lo tienen "
                         f"(--force para re-bajar)")
        # ⛔ #423 — un paso que corrió y no tenía trabajo IGUAL corrió. Es el caso OPUESTO al que
        # protege la guarda del final (el paso que no pudo mirar todo no deja traza): acá se
        # miraron las N notas y no había nada que hacer. Sin estampar, el sujeto cuyo BibTeX ya
        # está completo queda con «la cadena se cortó en fetch_bibtex» PARA SIEMPRE —`pendientes`
        # va a estar vacío en toda corrida futura— y el consejo del propio hallazgo (re-correr la
        # cadena, que es idempotente) no lo cierra.
        if args.slug:
            cfg.save_paso(args.slug, "fetch_bibtex", flags=cfg.flags_usados(args, ap))
        return 0

    # Una sola llamada a ADS para todos los bibcodes de la corrida: es el carril que resuelve la
    # mayoría y la exportación acepta listas — pedir uno por uno sería N requests por una respuesta.
    bibcodes = [str(fms[f][0].get("bibcode") or "").strip() or f.stem for f in pendientes]
    errores: list = []
    ads_cache: dict = {}
    sin_consultar: set = set()
    try:
        ads_cache, errores, sin_consultar = ads_bibtex(bibcodes, cfg.get_ads_token())
    except RuntimeError as exc:            # sin token: los otros dos carriles siguen sirviendo
        errores.append(f"sin token ADS, el carril `ads` NO corrió: {exc}")

    hoy = _dt.date.today().isoformat()
    n_ok, huecos, propuestas, no_evaluadas = 0, [], [], []
    por_fuente: dict = {}
    for f in pendientes:
        fm, text = fms[f]
        entrada, fuente, motivo, sin_medir = bibtex_for(fm, f.stem, ads_cache, sin_consultar)
        if not entrada:
            # #397 (cola) — antes de declarar el hueco, preguntar si el DOI EXISTE. El carril
            # off-ADS declaraba metadata a mano y nadie chequeaba: medido, `2011Naik` no era un
            # paper sin fuente oficial sino uno cuyo DOI Crossref tiene y la nota no lleva.
            # ⛔ PROPONE y no escribe: poblar `doi:` es curación, y el matcheo por título es lo que
            # este repo prohíbe (`discover`: 18 de 25 resueltos, 2 apuntando a OTRO trabajo).
            if not str(fm.get("doi") or "").strip():
                doi_prop, por_que, no_medido = doi_candidate(fm.get("title"),
                                                             fm.get("first_author"),
                                                             fm.get("year"))
                if doi_prop:
                    propuestas.append(f"{f.stem}: Crossref tiene `{doi_prop}` ({por_que}) — poblá "
                                      f"`doi:` en la nota y re-corré; NO se estampa solo")
                    continue
                if por_que.startswith("DUDOSO"):
                    # #399 — sale por el canal de las propuestas y no enterrado entre los huecos:
                    # un candidato que nadie ve es indistinguible de no haber buscado.
                    propuestas.append(f"{f.stem}: {por_que} — si es el mismo trabajo, poblá `doi:`")
                    continue
                if no_medido:
                    sin_medir.append(no_medido)
                else:
                    motivo += f" · {por_que}"
            # ⛔ #468 — una consulta que NO contestó no produce un veredicto PERSISTIDO. El hueco se
            # estampa sólo sobre carriles que contestaron; si alguno se cayó, la nota se queda del
            # lado de la deuda (`sin_bibtex_mudo`, que es lo que es) y la corrida sale en rc 2, así
            # que `save_paso` tampoco registra la cadena sobre notas que nadie midió (D-57).
            if sin_medir:
                no_evaluadas.append(f"{f.stem}: {' · '.join(sin_medir)}")
                continue
            huecos.append(f"{f.stem}: {motivo}")
            # #467 — el motivo se PERSISTE: sin esto la distinción que el docstring de `bibtex_for`
            # promete se pierde al terminar el proceso, y para verla hay que re-correr el paso caro.
            stamp_bibtex_gap(f, fm, text.split("\n---\n", 1)[-1], motivo, hoy)
            continue
        if str(fm.get("sin_bibtex") or "").strip():
            # El hueco se cerró: el motivo describía un estado que ya no es. Dejarlo haría que la
            # nota publique «no tiene exportación oficial» arriba de su propia entrada.
            cfg.drop_fm_keys(f, "sin_bibtex")
            fm, text = cfg.split_fm(t2 := f.read_text(encoding="utf-8")) or {}, t2
        stamp_bibtex(f, fm, text.split("\n---\n", 1)[-1], entrada, fuente, hoy)
        por_fuente[fuente] = por_fuente.get(fuente, 0) + 1
        n_ok += 1

    detalle = ", ".join(f"{k}: {v}" for k, v in sorted(por_fuente.items())) or "ninguna"
    cfg.print_seguro(f"bibtex: {n_ok} de {len(pendientes)} nota(s) con exportación oficial "
                     f"({detalle}) — sobre {len(notas)} nota(s) de paper miradas"
                     + (f"; {n_macro} re-bajada(s) porque la revista era una macro de AASTeX "
                        f"(#471)" if n_macro else ""))
    for pr in propuestas:
        cfg.print_seguro(f"  ⚑ el hueco NO es tal — hay DOI y la nota no lo lleva: {pr}")
    for h in huecos:
        cfg.print_seguro(f"  · sin BibTeX (campo VACÍO + `sin_bibtex` con el motivo, #467): {h}")
    for ne in no_evaluadas:
        cfg.print_seguro(f"  ⛔ NO EVALUADA — el hueco no se midió, NO se estampó `sin_bibtex` "
                         f"(#468): {ne}")
    for e in errores:
        cfg.print_seguro(f"  ⛔ {e}")
    # D-57/R-6 — el paso se estampa a sí mismo, y sólo al salir 0: un paso que no pudo mirar todo
    # no puede dejar traza de haber corrido, o el lint reporta la cadena completa sobre un hueco.
    if args.slug and not errores and not no_evaluadas:
        cfg.save_paso(args.slug, "fetch_bibtex", flags=cfg.flags_usados(args, ap))
    # Un error de red deja papers SIN consultar, y eso no se puede leer como «no tienen BibTeX».
    return 2 if (errores or no_evaluadas) else 0


if __name__ == "__main__":
    raise SystemExit(main())
