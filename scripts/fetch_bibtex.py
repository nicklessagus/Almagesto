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
    """`({bibcode: entrada}, [errores])` — la exportación oficial de ADS, en tandas de `ADS_CHUNK`.

    Un error de red devuelve lo que sí se pudo traer y lo DECLARA: la alternativa es que una caída a
    mitad de camino se lea como «esos papers no tienen BibTeX», que es el falso limpio de siempre."""
    out, errores = {}, []
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
                              json={"bibcode": tanda}, timeout=60)
        except requests.RequestException as exc:
            errores.append(f"ADS export no contestó para {len(tanda)} bibcode(s) "
                           f"({tanda[0]}…): {exc.__class__.__name__} — esos papers quedaron SIN "
                           f"consultar")
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
    return out, errores


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


def doi_bibtex(doi: str) -> tuple:
    """`(entrada, fuente)` por content negotiation contra `doi.org`, o `("", "")`.

    ⛔ Se exige status 2xx **y** `Content-Type` de BibTeX: el resolver contesta su «DOI Not Found»
    como HTML, y ese HTML en el frontmatter sería una cita inventada con cara de descargada."""
    try:
        r = requests.get(DOI_RESOLVER.format(doi=doi), headers={"Accept": BIBTEX_CT},
                         timeout=30, allow_redirects=True)
    except requests.RequestException:
        return "", ""
    if not r.ok or BIBTEX_CT not in (r.headers.get("Content-Type") or ""):
        return "", ""
    entrada = (r.text or "").strip()
    return (entrada + "\n", doi_agency(doi)) if entrada.startswith("@") else ("", "")


def arxiv_bibtex(arxiv_id: str) -> str:
    """La exportación que publica arXiv para ese id, o `""`. Mismo criterio que el carril del DOI:
    lo que no arranca con `@` no es una entrada, venga con el status que venga."""
    try:
        r = requests.get(ARXIV_BIBTEX.format(arxiv_id=arxiv_id), timeout=30)
        r.raise_for_status()
    except requests.RequestException:
        return ""
    entrada = (r.text or "").strip()
    return entrada + "\n" if entrada.startswith("@") else ""


def _family(nombre: str) -> str:
    """The family name out of whatever `first_author` holds: `Mayor, Michel` or `Michel Mayor`."""
    nombre = str(nombre or "").strip()
    if "," in nombre:
        return nombre.split(",", 1)[0].strip()
    return nombre.split()[-1] if nombre.split() else ""


def doi_candidate(title: str, first_author: str, year=None) -> tuple:
    """`(doi, motivo)` — PROPOSES a DOI for a note that has none. It never stamps one (#397).

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
    year often enough (`2011Naik` declares 2012 in its own frontmatter)."""
    titulo, familia = str(title or "").strip(), _family(first_author)
    if not titulo or not familia:
        return "", "sin `title` o sin `first_author`: no hay con qué preguntar"
    params = {"query.bibliographic": titulo, "query.author": familia, "rows": 5,
              "select": "DOI,title,author,issued"}
    if (correo := cfg.get_mailto()):
        params["mailto"] = correo              # polite pool, opt-in (#: nunca sale de git config)
    try:
        r = requests.get(CROSSREF_SEARCH, params=params,
                         headers={"User-Agent": "Almagesto (https://github.com/nicklessagus/Almagesto)"},
                         timeout=30)
        r.raise_for_status()
        items = (r.json().get("message") or {}).get("items") or []
    except (requests.RequestException, ValueError, AttributeError) as exc:
        return "", f"Crossref no contestó ({exc.__class__.__name__}): no consta"
    dudosos = []
    for it in items:
        cand = ((it.get("title") or [""])[0] or "").strip()
        if cfg.method_key(cand) != cfg.method_key(titulo):
            continue                           # ⛔ título EXACTO normalizado, nunca parecido
        if year:
            partes = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
            if partes and partes[0] and abs(int(partes[0]) - int(year)) > 1:
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
        return str(it.get("DOI") or ""), f"título exacto + autor «{familia}» en Crossref"
    if dudosos:
        return "", "DUDOSO — " + "; ".join(dudosos)
    return "", (f"Crossref devolvió {len(items)} resultado(s) y ninguno con el título EXACTO: "
                f"resolvelo a mano — acá no se propone por parecido (#397)")


def bibtex_for(fm: dict, stem: str, ads_cache: dict) -> tuple:
    """`(entrada, fuente, motivo)` para una nota, recorriendo la cascada declarada.

    `motivo` sólo se puebla cuando NO hay entrada, y dice cuál es el hueco: es la diferencia entre
    «este paper no tiene exportación oficial» y «nadie preguntó».

    @inv INV-151"""
    bib = str(fm.get("bibcode") or "").strip() or stem
    if (entrada := ads_cache.get(bib)):
        return entrada, "ads", ""
    if (doi := str(fm.get("doi") or "").strip()):
        entrada, fuente = doi_bibtex(doi)
        if entrada:
            return entrada, fuente, ""
    if (arx := str(fm.get("arxiv_id") or "").strip()):
        if (entrada := arxiv_bibtex(arx)):
            return entrada, "arxiv", ""
    faltan = [c for c, v in (("bibcode ADS", ads_cache.get(bib)), ("doi", fm.get("doi")),
                             ("arxiv_id", fm.get("arxiv_id"))) if not v]
    return "", "", "sin exportación oficial (sin " + ", sin ".join(faltan) + ")"


def stamp_bibtex(path: Path, fm: dict, body: str, entrada: str, fuente: str, fecha: str) -> None:
    """Estampa `bibtex` + `bibtex_source` + `bibtex_accessed`, con el mismo escritor quirúrgico que
    usa `check_retractions` (`cfg.stamp_fm_fields`): no re-serializa el YAML, así que la extracción
    LLM que vive abajo queda byte a byte.

    ⚠ `bibtex_accessed` es la fecha de ESTA descarga, no la de hoy en una corrida que no bajó nada
    (#34): sin eso el campo afirma un snapshot que nadie tomó."""
    cfg.stamp_fm_fields(path, fm, body,
                        {"bibtex": entrada, "bibtex_source": fuente, "bibtex_accessed": fecha})


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

    pendientes, fms = [], {}
    for f in notas:
        text = f.read_text(encoding="utf-8")
        fm = cfg.split_fm(text) or {}
        if str(fm.get("bibtex") or "").strip() and not args.force:
            continue
        fms[f] = (fm, text)
        pendientes.append(f)
    if not pendientes:
        cfg.print_seguro(f"bibtex: {len(notas)} nota(s) miradas, todas ya lo tienen "
                         f"(--force para re-bajar)")
        return 0

    # Una sola llamada a ADS para todos los bibcodes de la corrida: es el carril que resuelve la
    # mayoría y la exportación acepta listas — pedir uno por uno sería N requests por una respuesta.
    bibcodes = [str(fms[f][0].get("bibcode") or "").strip() or f.stem for f in pendientes]
    errores: list = []
    ads_cache: dict = {}
    try:
        ads_cache, errores = ads_bibtex(bibcodes, cfg.get_ads_token())
    except RuntimeError as exc:            # sin token: los otros dos carriles siguen sirviendo
        errores.append(f"sin token ADS, el carril `ads` NO corrió: {exc}")

    hoy = _dt.date.today().isoformat()
    n_ok, huecos, propuestas = 0, [], []
    por_fuente: dict = {}
    for f in pendientes:
        fm, text = fms[f]
        entrada, fuente, motivo = bibtex_for(fm, f.stem, ads_cache)
        if not entrada:
            # #397 (cola) — antes de declarar el hueco, preguntar si el DOI EXISTE. El carril
            # off-ADS declaraba metadata a mano y nadie chequeaba: medido, `2011Naik` no era un
            # paper sin fuente oficial sino uno cuyo DOI Crossref tiene y la nota no lleva.
            # ⛔ PROPONE y no escribe: poblar `doi:` es curación, y el matcheo por título es lo que
            # este repo prohíbe (`discover`: 18 de 25 resueltos, 2 apuntando a OTRO trabajo).
            if not str(fm.get("doi") or "").strip():
                doi_prop, por_que = doi_candidate(fm.get("title"), fm.get("first_author"),
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
                motivo += f" · {por_que}"
            huecos.append(f"{f.stem}: {motivo}")
            continue
        stamp_bibtex(f, fm, text.split("\n---\n", 1)[-1], entrada, fuente, hoy)
        por_fuente[fuente] = por_fuente.get(fuente, 0) + 1
        n_ok += 1

    detalle = ", ".join(f"{k}: {v}" for k, v in sorted(por_fuente.items())) or "ninguna"
    cfg.print_seguro(f"bibtex: {n_ok} de {len(pendientes)} nota(s) con exportación oficial "
                     f"({detalle}) — sobre {len(notas)} nota(s) de paper miradas")
    for pr in propuestas:
        cfg.print_seguro(f"  ⚑ el hueco NO es tal — hay DOI y la nota no lo lleva: {pr}")
    for h in huecos:
        cfg.print_seguro(f"  · sin BibTeX (campo VACÍO, que es el hueco correcto): {h}")
    for e in errores:
        cfg.print_seguro(f"  ⛔ {e}")
    # D-57/R-6 — el paso se estampa a sí mismo, y sólo al salir 0: un paso que no pudo mirar todo
    # no puede dejar traza de haber corrido, o el lint reporta la cadena completa sobre un hueco.
    if args.slug and not errores:
        cfg.save_paso(args.slug, "fetch_bibtex", flags=cfg.flags_usados(args, ap))
    # Un error de red deja papers SIN consultar, y eso no se puede leer como «no tienen BibTeX».
    return 2 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
