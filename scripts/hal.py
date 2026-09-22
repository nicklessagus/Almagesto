"""HAL (archives-ouvertes.fr) as a lane before declaring a HOLE — of `bibtex` and of the PDF (#505).

HAL is where authors deposit, and it publishes the official BibTeX export of every deposit by API
(`?q=halId_s:<id>&wt=bibtex`) plus, often, the full text (`fileMain_s`). Nothing consulted it, so a
hole could stay declared with the export one request away. Measured on a real vault: 1 of the 8
declared `sin_bibtex` holes was in HAL (`2010ComonJutten`, `hal-00460653`), and 43 of 248 notes
with a DOI have a HAL record — all of them already with a BibTeX from ADS or Crossref, so HAL only
ever fills holes; it does not compete with the lanes that exist.

⛔ The match rule is the repo's: by DOI, or by EXACT normalised title + the first author's family
name + year ±1. Never by an approximate title (`discover`: 18 of 25 resolved by title, 2 pointing at
another work). ⚠ A HAL record does not always carry its DOI (Comon & Jutten's does not), which is
why the title stage exists.

⛔ What is found is PROPOSED, never written: a HAL export is the `institucional` lane of #503 —
exported by whoever deposited, not by the publisher — and that lane is pasted by a person (#484).

`get` is injected (the caller's `requests.get`), so each caller's network double covers this module.
"""
from __future__ import annotations

import urllib.parse

import lib_config as cfg

API = "https://api.archives-ouvertes.fr/search/"
_FIELDS = "halId_s,title_s,authLastName_s,producedDateY_i,doiId_s,fileMain_s"


def bibtex_url(halid: str) -> str:
    """The API URL of a deposit's official BibTeX export — what goes in `bibtex_url`."""
    return API + "?" + urllib.parse.urlencode({"q": f"halId_s:{halid}", "wt": "bibtex"})


def _query(get, q: str, rows: int) -> list:
    """One HAL search → its docs. Raises on a network failure or a non-200: the caller turns that
    into «HAL did not answer», never into «HAL has nothing» (#468)."""
    r = get(API, params={"q": q, "fl": _FIELDS, "rows": rows, "wt": "json"}, timeout=30)
    if getattr(r, "status_code", 200) != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return ((r.json() or {}).get("response") or {}).get("docs") or []


def _family(nombre: str) -> str:
    """Family name out of `Mayor, Michel` or `Michel Mayor` (same rule as `fetch_bibtex._family`)."""
    nombre = str(nombre or "").strip()
    if "," in nombre:
        return nombre.split(",", 1)[0].strip()
    return nombre.split()[-1] if nombre.split() else ""


def _matches(doc: dict, titulo: str, familia: str, year) -> bool:
    """EXACT normalised title + first author's family name + year ±1 (when both years exist)."""
    titulos = doc.get("title_s") or []
    if cfg.method_key(titulo) not in {cfg.method_key(t) for t in titulos}:
        return False
    autores = doc.get("authLastName_s") or []
    if not autores or cfg.method_key(autores[0]) != cfg.method_key(familia):
        return False
    y = doc.get("producedDateY_i")
    return not (year and y and abs(int(y) - int(year)) > 1)


def find(get, doi=None, title=None, first_author=None, year=None) -> tuple:
    """`(record | None, reason, not_measured)` — the HAL deposit of one work, or why there is none.

    `record` = `{halid, bibtex_url, pdf, via}`. `not_measured` is non-empty only when HAL did not
    answer: that is no verdict, and the caller keeps the note on the debt side (#468)."""
    etapas, hechas = [], []
    if (doi := str(doi or "").strip()):
        etapas.append(("por DOI", f'doiId_s:"{doi}"', 5, None))
    titulo, familia = str(title or "").strip(), _family(first_author)
    if titulo and familia:
        frase = titulo.replace('"', " ")
        etapas.append(("por título exacto + autor + año", f'title_t:"{frase}"', 20,
                       (titulo, familia, year)))
    if not etapas:
        return None, "HAL no consultado: sin DOI y sin título + autor", ""
    for etiqueta, q, rows, criterio in etapas:
        try:
            docs = _query(get, q, rows)
        except Exception as e:                                  # noqa: BLE001 — se declara
            return None, "", f"HAL no contestó ({e.__class__.__name__}: {e}): no consta"
        for d in docs:
            ok = (str(d.get("doiId_s") or "").lower() == doi.lower() if criterio is None
                  else _matches(d, *criterio))
            if ok and d.get("halId_s"):
                return ({"halid": d["halId_s"], "bibtex_url": bibtex_url(d["halId_s"]),
                         "pdf": d.get("fileMain_s") or None, "via": f"HAL {etiqueta}"}, "", "")
        hechas.append(f"{etiqueta}: {len(docs)} resultado(s), ninguno exacto")
    return None, "HAL: " + " · ".join(hechas), ""


def export(get, halid: str, decode) -> tuple:
    """`(bibtex, not_measured)` — the deposit's official export, verbatim (never post-processed, #473).

    `decode` is the caller's UTF-8 decoder (`fetch_bibtex._utf8`, #419): never the response's
    guessed text encoding, which is how a surname with a diaeresis gets printed as mojibake."""
    try:
        r = get(bibtex_url(halid), timeout=30)
        if getattr(r, "status_code", 200) != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        return decode(r).strip(), ""
    except Exception as e:                                      # noqa: BLE001 — se declara
        return "", f"HAL no devolvió la exportación de {halid} ({e.__class__.__name__}): no consta"
