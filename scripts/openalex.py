"""Cliente de OpenAlex: descubrimiento (`works`) y referencias por lote (`refs_of`).

POR QUÉ EXISTE, medido (R-9, 2026-08-24, sobre las 908 notas de una bóveda real). Para el índice
de citas se consultan **las dos** fuentes, ADS y OpenAlex, porque ninguna es prescindible y se
tapan los agujeros en extremos opuestos del corpus:

  · en **astro** gana ADS — 80% del corpus contra 68%, y en pre-2000 la diferencia es 4×
    (65% vs 16%): `referenced_works` sale de depósitos Crossref, que la literatura astro vieja
    no tiene, mientras ADS resuelve referencias de escaneos con su propio pipeline.
  · en lo **no-astro** gana OpenAlex, y es el caso que el eje tema/concepto existe para servir:
    de los 38 papers off-ADS del corpus (ICA/PCA: Comon, Cardoso, Hyvärinen, Shlens…) **14 sólo
    los tiene OpenAlex** — ADS no puede tenerlos, no tienen bibcode — contra 3 sólo-ADS.

Dos consecuencias de esa medición que son contrato de este módulo, no detalle:

  1. **La llave es DOI**, nunca el título. Matchear por título resolvió 18 de 25 casos ciegos pero
     **2 de esos 18 apuntaban a otro trabajo**; en un índice de citas una arista falsa es peor que
     una faltante, porque propone candidatos que nadie citó.
  2. **La cobertura se declara.** `refs_of` devuelve `(mapa, no_resueltos)`: un mapa al que le
     faltan entradas en silencio se lee como completo, que es el falso limpio que INV-87 prohíbe.

Sin API key. `mailto` en la query es la cortesía que pide OpenAlex para el pool educado.
"""
from __future__ import annotations

import re
import time
import urllib.parse

import requests

import lib_config as cfg

API = "https://api.openalex.org/works"
MAILTO = "almagesto@example.org"   # se sobreescribe con `--mailto` desde el orquestador
PER_PAGE = 200                     # máximo de OpenAlex
BATCH = 50                         # DOIs por request en el filtro `doi:a|b|c`
TIMEOUT = 60
MAX_ATTEMPTS = 5      # OpenAlex 504ea; medido en vivo el 2026-08-24 (ver `_get`)
BACKOFF_S = 2.0
SELECT = ("id,doi,title,publication_year,referenced_works,referenced_works_count,"
          "cited_by_count,authorships,primary_location,abstract_inverted_index,type")
HEADERS = {"User-Agent": f"Almagesto/{cfg.ALMAGESTO_VERSION} (academic literature vault)"}


def _bare_doi(doi: str | None) -> str | None:
    """`https://doi.org/10.1/a` → `10.1/a`, en minúsculas (OpenAlex normaliza así)."""
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.I).lower()


def _apellido(work: dict) -> str | None:
    """Apellido del primer autor, sin acentos raros ni puntuación: la mitad de la clave sintética."""
    aut = (work.get("authorships") or [])
    if not aut:
        return None
    nombre = ((aut[0] or {}).get("author") or {}).get("display_name") or ""
    partes = [p for p in re.split(r"\s+", nombre.strip()) if p]
    if not partes:
        return None
    return re.sub(r"[^A-Za-zÀ-ÿ]", "", partes[-1]) or None


def citekey(work: dict) -> str | None:
    """Clave sintética `AAAA+Autor`, la misma convención del modo off-ADS.

    NO se usa el id de OpenAlex (`W1994703407`): el vault cita por clave legible y estable entre
    proveedores, y el lint exige que empiece con `AAAA` + letra. Sin año o sin autor devuelve
    `None` — inventar una clave es peor que no tenerla, porque colisiona en silencio."""
    anio, apellido = work.get("publication_year"), _apellido(work)
    if not anio or not apellido:
        return None
    return f"{anio}{apellido[0].upper()}{apellido[1:]}"


def _abstract(work: dict) -> str:
    """OpenAlex sirve el abstract como índice invertido (palabra → posiciones); se rearma."""
    inv = work.get("abstract_inverted_index") or {}
    if not inv:
        return ""
    pos: dict[int, str] = {}
    for palabra, idxs in inv.items():
        for i in idxs:
            pos[i] = palabra
    return " ".join(pos[i] for i in sorted(pos))


def to_record(work: dict) -> dict:
    """Normaliza al **mismo** schema de registro que `query_ads`, para que `classify` lo clasifique
    sin tocarlo. Un backend que trae su propio schema obliga a un clasificador propio, y ahí la
    lente deja de ser una sola — que es justo lo que `objective.yaml` promete ser."""
    venue = ((work.get("primary_location") or {}).get("source") or {}).get("display_name")
    return {
        "bibcode": citekey(work),
        "title": work.get("title") or "",
        "authors": [((a or {}).get("author") or {}).get("display_name")
                    for a in (work.get("authorships") or [])],
        "year": work.get("publication_year"),
        "pubdate": None,
        "abstract": _abstract(work),
        "arxiv_id": None,
        "doi": _bare_doi(work.get("doi")),
        "doctype": work.get("type"),
        "bibstem": venue,
        "citation_count": work.get("cited_by_count", 0),
        "keyword": [],
        "via": "openalex",
        "openalex_id": work.get("id"),
    }


def _get(params: dict) -> dict:
    """GET con reintento ante 5xx/429 y espera creciente.

    Medido en vivo el 2026-08-24: OpenAlex devolvió **504 en todos** sus endpoints —incluido el
    raíz— una hora después de contestar bien. Un índice de citas que muere en el primer hipo no se
    puede construir. Los **4xx no se reintentan**: son la query mal armada, y repetirla gasta cuota
    para el mismo error. Si el servicio no cede, **levanta**: devolver `[]` sería indistinguible de
    "no hay resultados", que es el falso limpio que INV-69/INV-87 prohíben."""
    params = {**params, "mailto": MAILTO, "select": SELECT}
    url = f"{API}?{urllib.parse.urlencode(params, safe=':|/.')}"
    for intento in range(MAX_ATTEMPTS):
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code < 500 and r.status_code != 429:
            r.raise_for_status()
            return r.json()
        if intento == MAX_ATTEMPTS - 1:
            r.raise_for_status()
        time.sleep(BACKOFF_S * (intento + 1))
    raise RuntimeError("inalcanzable")   # pragma: no cover


def works(filter: str, per_page: int = PER_PAGE):
    """Itera los works que matchean `filter`, paginando por cursor y **deduplicando por id**.

    OpenAlex puede devolver el mismo work en dos páginas cuando el corpus cambia entre requests;
    sin dedup eso se convierte en doble conteo aguas abajo."""
    cursor, vistos = "*", set()
    while cursor:
        data = _get({"filter": filter, "per-page": per_page, "cursor": cursor})
        for w in data.get("results", []):
            wid = w.get("id")
            if wid in vistos:
                continue
            vistos.add(wid)
            yield w
        cursor = (data.get("meta") or {}).get("next_cursor")


def refs_of(idents: list) -> tuple[dict, list]:
    """Referencias por lote. Devuelve `(mapa doi → [openalex_id, …], dois_que_no_resolvieron)`.

    Los **dos** valores son el resultado: el segundo es la cobertura, y sin él un mapa incompleto
    se lee como completo (INV-87). Medido: OpenAlex no resuelve ~3,5% de los DOI de un corpus astro
    real, y de los que resuelve ~13% vuelven con `referenced_works` vacío."""
    dois = [d for d in ({_bare_doi(i) for i in idents} - {None})]
    if not dois:
        return {}, []
    dois.sort()
    refs: dict[str, list] = {}
    for i in range(0, len(dois), BATCH):
        lote = dois[i:i + BATCH]
        data = _get({"filter": "doi:" + "|".join(lote), "per-page": PER_PAGE})
        for w in data.get("results", []):
            k = _bare_doi(w.get("doi"))
            if k in lote:
                refs[k] = [r.split("/")[-1] for r in (w.get("referenced_works") or [])]
    return refs, [d for d in dois if d not in refs]
