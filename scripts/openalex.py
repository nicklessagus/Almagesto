"""Cliente de OpenAlex: descubrimiento (`works`) y referencias por lote (`refs_of`).

POR QUÉ EXISTE, medido (R-9, 2026-08-24, sobre las 908 notas de una bóveda real). Para el índice
de citas se consultan **las dos** fuentes, ADS y OpenAlex, porque ninguna es prescindible y se
tapan los agujeros en extremos opuestos del corpus:

  · en **astro** gana ADS — 80% del corpus contra 68%, y en pre-2000 la diferencia es 4×
    (65% vs 16%): `referenced_works` sale de depósitos Crossref, que la literatura astro vieja
    no tiene, mientras ADS resuelve referencias de escaneos con su propio pipeline.
  · en lo **no-astro** gana OpenAlex, y es el caso que el eje tema/concepto existe para servir:
    de los 38 papers off-ADS del corpus (ICA/PCA: Comon, Cardoso, Hyvärinen, Shlens…) **14 sólo
    los tiene OpenAlex** (no tienen bibcode, así que ADS sólo los alcanza por DOI o título)
    contra **3 sólo-ADS**.

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
import subprocess
import sys
import time
import urllib.parse

import requests

import lib_config as cfg

API = "https://api.openalex.org/works"
def _mailto() -> str:
    """Contact email for OpenAlex's polite pool — opt-in, see `lib_config.get_mailto`."""
    return cfg.get_mailto()


MAILTO = ""                        # se resuelve por llamada; "" = pool público
PER_PAGE = 200                     # máximo de OpenAlex
BATCH = 50                         # DOIs por request en el filtro `doi:a|b|c`
TIMEOUT = 60
MAX_ATTEMPTS = 5      # OpenAlex 504ea a rachas; medido en vivo el 2026-08-24 (ver `_get`)
BACKOFF_S = 2.0
SELECT = ("id,doi,title,publication_year,referenced_works,referenced_works_count,"
          "cited_by_count,authorships,primary_location,abstract_inverted_index,type,"
          # `keywords`/`topics`: la lente matchea título+abstract+KEYWORDS, y sin pedirlas
          # `to_record` devolvía `keyword: []` — la lente buscaba en dos de tres fuentes.
          "keywords,topics")
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
    rec = {
        "bibcode": citekey(work),
        "title": cfg.clean_catalog_markup(work.get("title") or ""),   # #271
        "authors": [((a or {}).get("author") or {}).get("display_name")
                    for a in (work.get("authorships") or [])],
        "year": work.get("publication_year"),
        "pubdate": None,
        "abstract": cfg.clean_catalog_markup(_abstract(work)),        # #271
        "arxiv_id": None,
        "doi": _bare_doi(work.get("doi")),
        "doctype": work.get("type"),
        "bibstem": venue,
        # AUD-166 / INV-69: ausente = «no consta», nunca 0 (mismo contrato que `search_arxiv` y,
        # desde 1.74.0, que `query_ads.to_record`).
        "citation_count": work.get("cited_by_count"),
        "keyword": [n for campo in ("keywords", "topics")
                    for x in (work.get(campo) or [])
                    for n in [(x or {}).get("display_name")] if n],
        "via": "openalex",
        "openalex_id": work.get("id"),
    }
    # Las tres claves del CLASIFICADOR. Sin ellas el registro no es del mismo schema y los
    # consumidores o revientan (indexan con corchetes) o dan falsos limpios: `core` vacío en
    # `ingest_theme`, y toda nota naciendo `relevance: low` en `make_notes` — lo que encima
    # las excluye de `citation_index.corpus_idents`, o sea de la puerta 1 que estos backends
    # existen para alimentar. Se clasifica acá con `classify_record`, la ÚNICA lente.
    import query_ads
    facets, relevant = query_ads.classify_record(rec)
    rec["facets"], rec["relevant"] = facets, relevant
    # #126/#179: el schema declara `puertas` SIEMPRE (lista vacía = ninguna), así que «no
    # consta» y «ninguna puerta» no se confunden. Lo fija `tests/test_backends_schema.py`.
    rec["puertas"] = []
    # #86: se juzgó sin abstract (título + keywords y nada más). Mismo schema que
    # `query_ads.to_record`, que es quien lo define — la paridad la fija un test.
    rec["sin_abstract"] = not (rec.get("abstract") or "").strip()
    rec["why_excluded"] = None if relevant else query_ads.exclusion_reason(
        facets, rec.get("doctype") or "")
    return rec



# #186 · el backoff duerme por ESTE nombre, no por `time.sleep` directo. Es una indirección de una
# línea con un motivo medido: el test del retry parcheaba `oa.time.sleep`, y `oa.time is time` es
# **True** —`import time` no crea un alias, referencia el módulo global—, así que el acumulador
# contaba CUALQUIER `sleep` del proceso. Capturó un `0.001` ajeno en una corrida de la suite
# completa (`assert 3 == 2 where [0.001, 2.0, 4.0]`) y ésa era la «intermitencia sin causa
# demostrada» que el propio test declaraba. Con el indirecto, el doble queda acotado al sujeto bajo
# prueba, que es lo que la red #3 pide de cualquier doble.
_sleep = time.sleep


class BudgetExhausted(RuntimeError):
    """The daily OpenAlex budget is at zero: waiting does not help, and retrying wastes attempts."""


def _budget_exhausted(r) -> bool:
    """Is this 429 the BUDGET (`x-ratelimit-remaining: 0`, «Insufficient budget») or the rate?"""
    headers = {k.lower(): v for k, v in (getattr(r, "headers", None) or {}).items()}
    if headers.get("x-ratelimit-remaining", "").strip() == "0":
        return True
    return "insufficient budget" in str(getattr(r, "text", "") or "").lower()


def _budget_message(r) -> str:
    """The message for a budget 429: says WHEN it comes back, from `retry-after`, not «try later»."""
    headers = {k.lower(): v for k, v in (getattr(r, "headers", None) or {}).items()}
    secs = headers.get("retry-after", "").strip()
    cuando = (f"vuelve en {int(secs) // 3600} h {(int(secs) % 3600) // 60} min (medianoche UTC)"
              if secs.isdigit() else "vuelve a medianoche UTC")
    return (f"OpenAlex: presupuesto diario AGOTADO — no es una caída y no se arregla esperando; "
            f"{cuando}. Las entidades únicas (`works/doi:<doi>`) cuestan 0 y siguen andando")


def entity_by_doi(doi: str) -> dict | None:
    """ONE work by DOI via the single-entity endpoint, which OpenAlex prices at ZERO (#362).

    Measured with the quota at zero: `works/doi:<doi>` answers 200 with `x-ratelimit-cost-usd: 0`,
    while `works?filter=doi:A|B` (the list endpoint) answers 429. Same fields — `referenced_works`,
    `cited_by_count` — so whatever only needs to RESOLVE known DOIs has a free path."""
    url = f"{API}/doi:{urllib.parse.quote(_bare_doi(doi) or doi)}?{urllib.parse.urlencode({'select': SELECT})}"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _get(params: dict) -> dict:
    """GET con reintento ante 5xx/429 y espera creciente.

    Medido en vivo el 2026-08-24: OpenAlex devolvió **504 en todos** sus endpoints —incluido el
    raíz, o sea que no era el peso de la query— durante unos minutos, y volvió solo poco después.
    No es una caída: son **rachas**, y son el caso normal, no la excepción. Un índice de citas que
    muere en el primer hipo no se puede construir. Los **4xx no se reintentan**: son la query mal armada, y repetirla gasta cuota
    para el mismo error. Si el servicio no cede, **levanta**: devolver `[]` sería indistinguible de
    "no hay resultados", que es el falso limpio que INV-69/INV-87 prohíben."""
    params = {**params, "select": SELECT}
    correo = MAILTO or _mailto()
    if correo:
        params["mailto"] = correo
    url = f"{API}?{urllib.parse.urlencode(params, safe=':|/.')}"
    for intento in range(MAX_ATTEMPTS):
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 429 and _budget_exhausted(r):
            # #362 — este 429 NO es throttling: es la CUOTA diaria (1000 créditos, $0.10) en cero, y
            # no se recupera esperando. Reintentar con backoff creciente consume los MAX_ATTEMPTS
            # contra un error que no va a ceder — tiempo perdido y ruido en el log. La distinción
            # es un header, no adivinar por el texto: `retry-after` trae el segundo exacto del reset.
            raise BudgetExhausted(_budget_message(r))
        if r.status_code < 500 and r.status_code != 429:
            r.raise_for_status()
            return r.json()
        if intento == MAX_ATTEMPTS - 1:
            r.raise_for_status()
        _sleep(BACKOFF_S * (intento + 1))
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
        try:
            data = _get({"filter": "doi:" + "|".join(lote), "per-page": PER_PAGE})
            works_ = data.get("results", [])
        except BudgetExhausted as exc:
            # #362 — `refs_of` RESUELVE DOIs conocidos, no busca nada: cada uno es exactamente lo
            # que el endpoint de entidad única devuelve GRATIS. El lote es 1 request por 200 DOIs y
            # esto es 1 por DOI —más tráfico, cero presupuesto—, y es el canje correcto cuando el
            # recurso que se agota es el presupuesto. Sin esto el anclaje de `discover` (#361) y
            # `citation_index` quedaban en la cola del recurso escaso sin necesitarlo.
            print(f"  ⚠ {exc} → resolviendo {len(lote)} DOI(s) por entidad única", file=sys.stderr)
            works_ = [w for w in (entity_by_doi(d) for d in lote) if w]
        for w in works_:
            k = _bare_doi(w.get("doi"))
            if k in lote:
                refs[k] = [r.split("/")[-1] for r in (w.get("referenced_works") or [])]
    return refs, [d for d in dois if d not in refs]
