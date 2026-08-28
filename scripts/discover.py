"""Multi-backend discovery cascade for a THEME: ADS → arXiv → OpenAlex, plus anchored discovery.

WHY IT EXISTS, measured (2026-08-26, ICA/BSS ingest into a real vault). For a method theme whose
canon lives outside astronomy, the ADS-only chain finds nothing and the framework's answer was to
have the operator DECLARE every source by hand (`sources:` in themes.yaml). Two measurements say
that is a gap, not a design:

  · the eight canonical ICA/BSS works — Jutten&Hérault 1991, Comon 1994, Bell&Sejnowski 1995,
    Hyvärinen&Oja 1997/1999/2000, noisy-ICA 1999, Himberg+2004 (Icasso) — are in **ADS 0/8,
    arXiv 0/8, OpenAlex 8/8**. `author:"Hyvarinen, A"` in ADS returns two papers about sulfuric
    acid droplets (a different Hyvärinen). One backend is not a preference here; it is the
    difference between finding the canon and not.
  · the old vault held six ADS-indexed papers the keyword sweep never reached, and **none of them
    is an ICA paper**: they are *PCA with Noisy and/or Missing Data*, *Weighted PCA*, *Matrix
    Denoising with Doubly Heteroscedastic Noise* — the whitening step. No ICA keyword reaches
    "weighted principal component analysis". Only the reference lists of the theme's own astro
    papers do.

Three contracts, each the direct consequence of a measurement:

  1. **Discovery PROPOSES; it never classifies.** Everything here returns candidates for triage.
     `core` stays a function of `(paper, lens)` — re-derivable offline from the note — or the
     registry's stored `lens` and the lens-desync detector stop meaning anything (INV-24). A
     record that reached us from only one backend is not thereby core.
  2. **The dedup key is the DOI, never the title.** `openalex.py` fixes this with its own
     measurement: title matching resolved 18 of 25 blind cases and **2 of those 18 pointed at a
     different work**. What has no DOI is reported as non-dedupable, not silently merged.
  3. **Coverage is declared.** Every stage reports what it could not do — a backend that failed,
     an identifier that did not resolve — because a result set missing entries in silence reads
     as complete (INV-87).

Ranking note, measured: OpenAlex `search:"independent component analysis blind source separation"`
sorted by citations returns 143,450 works whose top 30 is AlphaFold, heart-failure guidelines and
hepatocellular carcinoma — **2 of 30** on topic. Filtering by `topics.id` first puts the canon in
the top 25 (Bell&Sejnowski #19, Hyvärinen&Oja #20, Comon #22, the HKO book #25). Ranking without a
structural filter amplifies; it does not filter. Hence `topics()` before `seed()`.

CLI (proposes only: downloads nothing and writes no note; it DOES append the
discovery run to the versioned registry — see `_preview_theme`):
    python scripts/discover.py --topics "blind source separation"
    python scripts/discover.py --theme ica
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time
import urllib.parse

import requests

import datetime as dt

import lib_config as cfg
import openalex as oa

TIMEOUT = 90
TOPICS_API = "https://api.openalex.org/topics"


def _json(url: str) -> dict:
    """GET a OpenAlex que **levanta** ante un payload de error, en vez de devolver `{}`.

    Existe porque este módulo llamaba `requests.get(...).json()` directo, salteando el helper ya
    endurecido de `openalex._get` — un camino paralelo con otro contrato, y el bug vivió justo en la
    diferencia (regla de método #3). Medido en vivo: con el presupuesto diario agotado OpenAlex
    responde **HTTP 429** con un JSON `{error, message, retryAfter, …}` y **sin** `results`; leer
    sólo `results` daba 0, y la cobertura imprimía «openalex 0 registros» como si el backend hubiera
    mirado y no tuviera nada. Ése es el cero silencioso que INV-87 prohíbe: acá el 0 tiene que ser
    un FALLO declarado, porque «se acabó la cuota» y «el tema no existe en OpenAlex» son
    conclusiones opuestas."""
    r = requests.get(url, timeout=TIMEOUT)
    try:
        d = r.json()
    except ValueError as exc:
        raise RuntimeError(f"OpenAlex HTTP {r.status_code}: respuesta no-JSON") from exc
    if isinstance(d, dict) and d.get("error"):
        raise RuntimeError(f"OpenAlex HTTP {r.status_code}: {d.get('error')} — "
                           f"{str(d.get('message'))[:120]}")
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAlex HTTP {r.status_code}")
    return d


# ── identity / dedup ─────────────────────────────────────────────────────────
def ident(rec: dict) -> str | None:
    """Cross-backend identity of a record: DOI first, then arXiv id. Never the title (contract 2).
    `None` means the record cannot be deduped — the caller must say so, not merge it."""
    doi = oa._bare_doi(rec.get("doi"))
    if doi:
        return f"doi:{doi}"
    ax = (rec.get("arxiv_id") or "").strip()
    return f"arxiv:{ax.lower()}" if ax else None


def dedup(batches: list[tuple[str, list]]) -> tuple[list, list]:
    """`[(backend, records), …]` → `(merged, undedupable)`.

    Earlier batches win the record body (the cascade is ordered cheapest/richest first), but every
    backend that carried a work is accumulated in `found_in`, because that list is what lets the
    caller route by provenance without letting provenance decide `core`. Records with no DOI and
    no arXiv id are returned separately and NOT merged: two of them could be the same work or not,
    and guessing is exactly the failure mode contract 2 exists to prevent."""
    merged: dict[str, dict] = {}
    undedupable: list[dict] = []
    for backend, records in batches:
        for r in records or []:
            k = ident(r)
            if k is None:
                r = dict(r)
                r["found_in"] = [backend]
                undedupable.append(r)
                continue
            if k in merged:
                if backend not in merged[k]["found_in"]:
                    merged[k]["found_in"].append(backend)
                # keep a citation count if the first backend had none
                if not merged[k].get("citation_count") and r.get("citation_count"):
                    merged[k]["citation_count"] = r["citation_count"]
            else:
                r = dict(r)
                r["found_in"] = [backend]
                merged[k] = r
    return list(merged.values()), undedupable


def only_from(records: list, backend: str) -> list:
    """Records that ONLY this backend carried. For a non-astro theme, `only_from(recs, 'openalex')`
    is the half that no astro index knows about — the half that must go through triage."""
    return [r for r in records if r.get("found_in") == [backend]]


# ── OpenAlex: topic filter, then rank (measured: the filter is what makes the rank usable) ──
def topics(query: str, rows: int = 5) -> list[dict]:
    """OpenAlex topic taxonomy search → `[{id, name, works_count}, …]`, best match first."""
    url = f"{TOPICS_API}?" + urllib.parse.urlencode(
        {"search": query, "per-page": rows, "mailto": oa._mailto()})
    d = _json(url)
    return [{"id": (r.get("id") or "").rsplit("/", 1)[-1],
             "name": r.get("display_name"),
             "works_count": r.get("works_count")}
            for r in d.get("results", [])]


def seed_terms(topic_id: str, terms: list, rows_por_termino: int = 200) -> list[dict]:
    """Text search **inside** the topic, one slice per term → records.

    WHY THE CITATION-RANKED SEED IS NOT ENOUGH, measured (#107). `seed` sorts a topic's works by
    citations, and the specialist mid-tail of a topic is unreachable that way **by construction**:
    T11447 holds 169,977 works, so the top-200 floor sits in the thousands of citations, while the
    noisy-ICA literature the old vault had curated by hand — Cardoso 2002, Davies 2004, Cichocki
    1998, Voss 2013, Pfister 2019, Pan 2022 — sits at **11 to 72 citations**. All six ARE in
    OpenAlex and all six carry the CORRECT topic: nothing was missing, the ranking buried them.

    A term slice is a different retrieval axis over the same backend, and it collapses the haystack:
    `quasi-whitening` inside T11447 returns **15** works, not 169,977. The terms come from the
    theme's `aliases`, which is why those are worth writing carefully.

    ⚠ **`rows_por_termino` defaults high on purpose, and the default is a measurement.** With the
    first default (15) this function looked useless — 217 candidates for 1 recovery — and that
    number was an artifact of the cap, not of the backend: four of the six papers it was meant to
    reach sit at ranks **28, 44, 110 and 121** of a slice holding only **579 works**. Capping at 15
    and then concluding the tail was unreachable was drawing a structural conclusion from a silent
    truncation. The slice is bounded (hundreds, not the topic's 169,977), so paging it is
    affordable; what is not affordable is a cap that hides its own effect — hence the warning
    printed per term when the slice holds more than was taken."""
    out: list[dict] = []
    vistos: set = set()
    for term in terms:
        f = f"topics.id:{topic_id},title_and_abstract.search:{term}"
        url = oa.API + "?" + urllib.parse.urlencode(
            {"filter": f, "sort": "cited_by_count:desc",
             "per-page": min(rows_por_termino, 200), "mailto": oa._mailto()})
        try:
            d = _json(url)
        except Exception as e:                                  # noqa: BLE001 — declarado
            cfg.print_seguro(f"  ⚠ seed_terms: «{term}» falló ({e}) — 0 de ese término")
            continue
        hay = ((d.get("meta") or {}).get("count") or 0)
        traidos = 0
        for w in d.get("results", []):
            traidos += 1
            wid = _oa_id(w.get("id"))
            if wid in vistos:
                continue
            vistos.add(wid)
            r = oa.to_record(w)
            r["found_in"] = ["openalex"]
            out.append(r)
        # No silent caps: si el slice tiene más de lo que se trajo, se DICE. Es la regla que el
        # framework ya aplica al `truncated` de ADS, y su ausencia acá produjo una conclusión falsa.
        if hay > traidos:
            cfg.print_seguro(f"  ⚠ «{term}»: el slice tiene {hay} y se trajeron {traidos} "
                             f"(top por citas) — subí `rows_por_termino` para cubrir el resto")
        time.sleep(0.2)
    return out


def seed(topic_id: str, rows: int = 25, min_citas: int | None = None) -> list[dict]:
    """Top works of one OpenAlex topic by citation count, normalised to the shared record schema.

    ⚠ The filter is looser than its name suggests, and it is worth knowing before reading the
    output: measured on T11447, the topic declares 55,210 works and `topics.id:` returns 169,977,
    because it matches secondary topic assignments too. This is a seed for triage, not a corpus."""
    url = oa.API + "?" + urllib.parse.urlencode(
        {"filter": f"topics.id:{topic_id}", "sort": "cited_by_count:desc",
         "per-page": min(rows, 200), "mailto": oa._mailto()})
    d = _json(url)
    recs = [oa.to_record(w) for w in d.get("results", [])]
    for r in recs:                      # provenance stamped at the source, so the preview cannot lie
        r["found_in"] = ["openalex"]
    if min_citas is not None:
        recs = [r for r in recs if (r.get("citation_count") or 0) >= min_citas]
    return recs


# ── anchored discovery: what YOUR papers cite (the half no keyword reaches) ──
def _oa_id(x: str | None) -> str:
    """OpenAlex work id, bare: `https://openalex.org/W123` → `W123`.

    It exists because `refs_of` returns bare ids and `to_record` stores the full URL, so joining
    the two by hand silently produced zero matches — the count that ranks anchored candidates came
    out 0 for every one of them, and a rank of all-zeros still prints a plausible-looking list.
    Same failure shape as regla 2 of CLAUDE.md: the bug lives in the difference between two
    contracts nobody compared. Normalise on both sides, once, here."""
    return (x or "").rsplit("/", 1)[-1]


def anchored(records: list, min_citadores: int = 2) -> tuple[list, list]:
    """Works cited by ≥`min_citadores` of `records` → `(ranked candidates, unresolved idents)`.

    This is the framework's puerta 1 ("your corpus cites it") applied to a NEW theme, where the
    citation index does not exist yet because it is built from the already-ingested corpus. The
    anchor is the theme's own astro half: its reference lists contain the canon ranked by how many
    of them agree it matters — which is why it reaches works no keyword of the theme ever will.

    Returns unresolved identifiers as a separate list (contract 3): OpenAlex resolves references
    from Crossref deposits, which pre-2000 astronomy largely lacks."""
    idents = [d for d in (oa._bare_doi(r.get("doi")) for r in records) if d]
    if not idents:
        return [], []
    mapa, no_resueltos = oa.refs_of(idents)
    cuenta: dict[str, int] = {}
    for refs in mapa.values():
        for ref in set(refs or []):
            cuenta[ref] = cuenta.get(ref, 0) + 1
    return (sorted(((_oa_id(ref), n) for ref, n in cuenta.items() if n >= min_citadores),
                   key=lambda t: -t[1]),
            no_resueltos)


def anchored_records(records: list, min_citadores: int = 2, rows: int = 40) -> tuple[list, list]:
    """`anchored` + `hydrate` + the join, done once and correctly.

    Returns `(records ranked by how many of YOUR papers cite them, unresolved idents)`. Each record
    carries `citadores` (the consensus count) and `found_in: ["anclado"]`. Callers must not redo
    the id join themselves — see `_oa_id` for why that is the whole point of this function."""
    pares, no_resueltos = anchored(records, min_citadores=min_citadores)
    if not pares:
        return [], no_resueltos
    cuenta = dict(pares)
    hidratados = hydrate([oid for oid, _ in pares[:rows]], rows=rows)
    for r in hidratados:
        r["citadores"] = cuenta.get(_oa_id(r.get("openalex_id")), 0)
        r["found_in"] = ["anclado"]
    hidratados.sort(key=lambda r: (-r["citadores"], -(r.get("citation_count") or 0)))
    return hidratados, no_resueltos


def hydrate(openalex_ids: list, rows: int = 50) -> list[dict]:
    """OpenAlex ids → records (the anchored stage returns ids; triage needs titles and citations)."""
    out: list[dict] = []
    for i in range(0, len(openalex_ids), 50):
        lote = [x.rsplit("/", 1)[-1] for x in openalex_ids[i:i + 50]]
        url = oa.API + "?" + urllib.parse.urlencode(
            {"filter": "openalex_id:" + "|".join(lote), "per-page": 50, "mailto": oa._mailto()})
        try:
            d = _json(url)
        except Exception as e:                                  # noqa: BLE001 — declared, not swallowed
            cfg.print_seguro(f"  ⚠ hydrate: lote {i // 50 + 1} falló ({e}) — {len(lote)} sin resolver")
            continue
        out += [oa.to_record(w) for w in d.get("results", [])]
        time.sleep(0.2)
        if len(out) >= rows:
            break
    return out[:rows]


# ── the cascade proper: ADS → arXiv → OpenAlex, deduped, coverage declared ───
def cascade(*, ads_query: str | None = None, arxiv_terms: list | None = None,
            topic_id: str | None = None, rows: int = 100,
            min_citas: int | None = None, term_slices: list | None = None) -> dict:
    """Run every discovery backend and merge → `{records, undedupable, cobertura}`.

    Each backend gets its query **in its own language**, which is why this takes three arguments
    instead of one: `ads_query` is raw Solr (`abs:"…" OR …`), arXiv wants its own field syntax and
    is given the theme's plain term family, and OpenAlex is filtered by topic id rather than by
    text at all (see `seed` for the measurement that forced that). Handing one string to all three
    would silently mean something different in each.

    `cobertura` is a list of `(backend, n, error|None)` and is the point of contract 3: a backend
    that timed out contributes zero records, and zero records is indistinguishable from "this
    backend knows nothing about your theme" unless the failure is stated. Callers must print it.

    `term_slices` (opt-in) adds one OpenAlex text-search slice per term inside the topic. It is off
    by default because of its TRIAGE COST, not because it underperforms (#107): measured on the
    real corpus it takes recall from **7/18 to 13/18** and the candidate universe from **776 to
    2521**. That trade is decided per theme. ⚠ The first measurement said *"217 candidates, 1
    recovery"* and is **retracted**: it was an artifact of a 15-row-per-term cap — see the
    `rows_por_termino` note in `seed_terms`.

    ⚠ **Declared limit of automated discovery** (#107, measured): the specialist mid-tail of a
    method topic is unreachable by any citation-ranked axis. Cardoso 2002, Davies 2004, Cichocki
    1998, Voss 2013, Pfister 2019 and Pan 2022 all sit at **11-72 citations** inside a topic of
    169,977 works, and the axes that do contain them ("who cites the canon" ∩ topic) return
    **3,467-5,270** candidates — worse than useless, because the triage cost exceeds the benefit.
    The axis that DOES reach that mid-tail is `term_slices` (text slice inside the topic), at the
    cost stated above. What stays outside automated discovery is narrower and of one shape:
    chapters and proceedings, and papers whose title/abstract uses none of the theme's terms. That
    population is what months of hand curation are good at. This is a boundary to state, not a gap
    to close: what the framework can do is make each hand-curated entry record why it entered
    (`extra_core` with `via`/`motivo`, or `sources`), and that it already does.

    Returns candidates. It does NOT classify — see the module docstring, contract 1."""
    batches: list[tuple[str, list]] = []
    cobertura: list[tuple[str, int, str | None]] = []

    if not ads_query:
        # Contrato 3 llevado hasta el final: un backend que NO CORRIÓ tiene que decirlo. Saltearlo
        # en silencio deja una cascada de tres que corrió una sola, y el resultado se lee como
        # «los tres miraron y esto es todo lo que hay» — el falso limpio que INV-87 prohíbe.
        cobertura.append(("ads", 0, "NO CORRIÓ: sin `query:` en themes.yaml — el tema no declara búsqueda ADS"))
    if ads_query:
        try:
            import query_ads
            recs = query_ads.query_ads(ads_query, rows=rows)
            batches.append(("ads", recs))
            cobertura.append(("ads", len(recs), None))
        except Exception as e:                                  # noqa: BLE001 — declarado
            cobertura.append(("ads", 0, str(e)[:120]))

    if not arxiv_terms:
        # Contrato 3 llevado hasta el final: un backend que NO CORRIÓ tiene que decirlo. Saltearlo
        # en silencio deja una cascada de tres que corrió una sola, y el resultado se lee como
        # «los tres miraron y esto es todo lo que hay» — el falso limpio que INV-87 prohíbe.
        cobertura.append(("arxiv", 0, "NO CORRIÓ: sin `aliases:` en themes.yaml — no hay términos que buscar"))
    if arxiv_terms:
        try:
            import search_arxiv
            q = " OR ".join(f'all:"{t}"' for t in arxiv_terms)
            recs = search_arxiv.search(q, rows=min(rows, 100))
            batches.append(("arxiv", recs))
            cobertura.append(("arxiv", len(recs), None))
        except Exception as e:                                  # noqa: BLE001
            cobertura.append(("arxiv", 0, str(e)[:120]))

    if not topic_id:
        # Contrato 3 llevado hasta el final: un backend que NO CORRIÓ tiene que decirlo. Saltearlo
        # en silencio deja una cascada de tres que corrió una sola, y el resultado se lee como
        # «los tres miraron y esto es todo lo que hay» — el falso limpio que INV-87 prohíbe.
        cobertura.append(("openalex", 0, "NO CORRIÓ: sin `topic:` en themes.yaml y no se pudo inferir — declaralo (`discover.py --topics \"<tema en inglés>\"`)"))
    if topic_id:
        try:
            recs = seed(topic_id, rows=min(rows, 200), min_citas=min_citas)
            # `seed_terms` es opt-in por su COSTO, no por falta de rendimiento (#107). Medido
            # sobre el corpus real: activarlo lleva la recuperación de **7/18 a 13/18** y el
            # universo de candidatos de **776 a 2521**. Es cobertura contra costo de triage, y esa
            # decisión es por tema. (La primera medición decía "217 candidatos, 1 recuperación" y
            # era artefacto de un tope de 15 filas por término — ver el docstring de `seed_terms`.)
            if term_slices:
                recs += seed_terms(topic_id, term_slices)
            batches.append(("openalex", recs))
            cobertura.append(("openalex", len(recs), None))
        except Exception as e:                                  # noqa: BLE001
            cobertura.append(("openalex", 0, str(e)[:120]))

    merged, undedupable = dedup(batches)
    return {"records": merged, "undedupable": undedupable, "cobertura": cobertura}


def print_cobertura(cobertura: list) -> None:
    """Print what each backend contributed, failures included. Never silent: a backend that fell
    over looks exactly like one that had nothing, and only one of those is a reason to stop."""
    for backend, n, err in cobertura:
        if err and err.startswith("NO CORRIÓ"):
            cfg.print_seguro(f"  — {backend:<9} {err}")
        elif err:
            cfg.print_seguro(f"  ⚠ {backend:<9} FALLÓ ({err}) — 0 registros, y eso NO significa "
                             "que no tenga nada del tema")
        else:
            cfg.print_seguro(f"  {backend:<9} {n:>4} registros")


# ── file resolution: finding a work is not the same as getting it ────────────
UNPAYWALL = "https://api.unpaywall.org/v2/"


def resolve_pdf(doi: str | None, title: str | None = None) -> tuple[str | None, str]:
    """`(url of a free PDF, reason)` for one work. Never downloads; never writes.

    WHY IT IS A SEPARATE STAGE, measured: OpenAlex identified 8 of 8 canonical ICA works — with
    DOI and citation counts — and returned `best_oa_location.pdf_url = None` for **8 of 8**. The
    discovery cascade answers *does it exist*; nothing answered *can I get the file*, so the
    operator hit a wall the tooling had no vocabulary for beyond `pending:`. What actually resolved
    those files was: the author's own page (3), an institutional repository (1); HAL blocked
    scripted access with an anti-bot page (1) and two are behind IEEE/MIT paywalls.

    It PROPOSES a URL and stops. It never rewrites a `pending:` an operator declared, and never
    edits `sources:` — the file still has to be looked at before it is trusted, and silently
    swapping a declared source for one a script guessed is how a citation ends up pointing at a
    document nobody opened."""
    doi = oa._bare_doi(doi)
    if not doi:
        return None, "sin DOI — no hay por dónde empezar (dejar `pending`, o declarar `url:`)"
    # 1. OpenAlex: ya lo tenemos consultado en la cascada, y trae la ubicación OA si existe
    try:
        d = _json(oa.API + "/doi:" + urllib.parse.quote(doi) + "?" +
                  urllib.parse.urlencode({"mailto": oa._mailto()}))
        url = ((d.get("best_oa_location") or {}).get("pdf_url"))
        if url:
            return url, "OpenAlex best_oa_location"
    except Exception as e:                                      # noqa: BLE001 — declarado, no tragado
        cfg.print_seguro(f"  ⚠ resolve_pdf: OpenAlex falló para {doi} ({e})")
    # 2. Unpaywall: mismo universo de depósitos, distinta resolución de OA locations
    try:
        d = requests.get(UNPAYWALL + urllib.parse.quote(doi) + "?" +
                         urllib.parse.urlencode({"email": oa._mailto()}), timeout=TIMEOUT).json()  # Unpaywall: otro servicio
        url = ((d.get("best_oa_location") or {}).get("url_for_pdf"))
        if url:
            return url, "Unpaywall"
    except Exception as e:                                      # noqa: BLE001
        cfg.print_seguro(f"  ⚠ resolve_pdf: Unpaywall falló para {doi} ({e})")
    return None, ("sin copia libre en OpenAlex ni Unpaywall — probá la página del autor o el "
                  "repositorio institucional; si no, dejalo `pending: paywall`")


# ── CLI (preview only) ───────────────────────────────────────────────────────
def _row(r: dict) -> str:
    t = " ".join((r.get("title") or "").split())[:60]
    cit = f'  citado x{r["citadores"]:<3}' if r.get("citadores") is not None else ""
    # `?`, NO 0, cuando el backend no publica el conteo (arXiv). Es la advertencia que
    # `search_arxiv.to_record` deja escrita: un 0 afirma «no lo cita nadie» sobre un dato que nadie
    # miró, y acá el operador lee la columna para decidir qué mandar a triage — un fundacional con
    # «0» al lado se descarta de un vistazo.
    n = r.get("citation_count")
    cites = "     ?" if n is None else f"{n:>6}"
    return (f'  {cites}  {r.get("year") or "----"}{cit}  '
            f'{",".join(r.get("found_in") or ["?"]):<12}  {t}')


def _theme_anchor(slug: str, concept: str | None = None) -> tuple[list, int]:
    """DOIs of the theme's papers already in the vault, plus how many of its papers were found.

    Reads the notes with `lib_config.split_fm`, the same parser the rest of the tooling uses, and
    never `grep` over the frontmatter: `thesis_links` is written in block style by `make_notes` and
    in flow style by the retro-linker, and a textual match misses one of the two. That failure is
    recorded twice in CLAUDE.md; this is the third place it would have happened.

    ⛔ AUD-134 — it matched the **slug** against `thesis_links`, which holds the theme's `concept`
    NAME. The anchor was therefore always empty and the CLI printed «sin anclaje: el tema todavía
    no tiene papers con DOI en la bóveda», an affirmative sentence about a lookup that never
    matched: the highest-leverage half of `discover` was off and said so as if it were a fact. It
    is the same slug-vs-concept confusion #188 fixed for the view's `sujeto`.

    The second return value is what makes the CLI able to tell «the theme has no papers here» from
    «it has papers and none carries a DOI» — two different next steps."""
    import glob
    nombres = {n for n in (concept, slug) if n}
    fuera, del_tema = [], 0
    for f in sorted(glob.glob(str(cfg.PAPERS / "*.md"))):
        fm = cfg.split_fm(pathlib.Path(f).read_text(encoding="utf-8"))
        if not nombres & set(fm.get("thesis_links") or []):
            continue
        del_tema += 1
        if fm.get("doi"):
            fuera.append({"doi": fm["doi"], "title": fm.get("title")})
    return fuera, del_tema


def _preview_theme(slug: str, rows: int = 25, min_citadores: int = 2) -> int:
    """Full cascade for one theme, proposes only: downloads no file and writes nothing to `vault/wiki/`. It DOES
    append this run to `descubrimientos:` of the versioned registry (INV-121), which is
    deliberate — a discovery pass that leaves no trace is lost as soon as the terminal
    scrolls, the failure mode #55/#88 closed for triage and sweep. The docstring said
    otherwise until #133, contradicting INV-59 on paper."""
    tema = cfg.as_map(cfg.load_themes().get(slug))
    if not tema:
        cfg.print_seguro(f"'{slug}' no está en themes.yaml")
        return 2
    topic_id = tema.get("topic")
    if not topic_id:
        # sin `topic:` declarado, se propone el mejor match y se DICE que se eligió solo. Se busca
        # por el TÍTULO del tema, no por el primer alias: los alias son siglas (`ICA`, `BSS`, `GP`)
        # y la taxonomía de OpenAlex se busca por frase — medido, `topics("ICA")` no devuelve nada
        # y el tema se quedaba sin la mitad OpenAlex en silencio.
        cands = topics(str(tema.get("title") or (cfg.as_list(tema.get("aliases")) or [slug])[0]),
                       rows=1)
        if cands:
            topic_id = cands[0]["id"]
            cfg.print_seguro(f"  (sin `topic:` en themes.yaml — usando {topic_id} "
                             f"«{cands[0]['name']}», elegido por alias; declaralo si sirve)")
    out = cascade(ads_query=tema.get("query"),
                  arxiv_terms=cfg.as_list(tema.get("aliases"))[:6] or None,
                  topic_id=topic_id, rows=rows,
                  min_citas=tema.get("fundacional_min_citas"))
    cfg.print_seguro(f"\nCascada para `{slug}` (preview — no baja nada, no clasifica):")
    print_cobertura(out["cobertura"])
    # #77: el rastro versionado. La cascada corría tres backends y su resultado moría en stdout, así
    # que un tema off-ADS no podía responder «sobre qué universo afirma esta nota, y con qué se
    # buscó» — lo que D-28 sí garantiza para un tema ADS. Se guarda la COBERTURA por backend con sus
    # tres estados, no un total: un backend caído (0 por timeout) y uno que corrió y no trajo nada
    # se leen igual en una suma, y esa distinción es la que hace honesta la frase «los tres miraron».
    cfg.save_descubrimiento(slug, {
        "fecha": dt.date.today().isoformat(),
        "rows": rows,
        "topic": topic_id,
        "n_records": len(out["records"]),
        "n_undedupable": len(out["undedupable"]),
        "cobertura": {b: {"n": n_, "error": err} for b, n_, err in out["cobertura"]},
        "almagesto_version": cfg.ALMAGESTO_VERSION,
    })
    cfg.print_seguro(f"  → registrado en {cfg.registro_path(slug)}")
    cfg.print_seguro(f"  → {len(out['records'])} tras dedup por DOI"
                     + (f" · {len(out['undedupable'])} sin identificador (NO mergeados)"
                        if out["undedupable"] else ""))
    solo_oa = only_from(out["records"], "openalex")
    if solo_oa:
        cfg.print_seguro(f"  · {len(solo_oa)} los tiene SÓLO OpenAlex → no-astro, van a triage")
    for r in sorted(out["records"], key=lambda r: -(r.get("citation_count") or 0))[:rows]:
        cfg.print_seguro(_row(r))

    ancla, del_tema = _theme_anchor(slug, tema.get("concept"))
    if ancla:
        cfg.print_seguro(f"\nAnclaje: {len(ancla)} papers del tema con DOI en la bóveda "
                         f"→ qué citan ≥{min_citadores} de ellos")
        anclados, no_res = anchored_records(ancla, min_citadores=min_citadores, rows=rows)
        if no_res:
            cfg.print_seguro(f"  ⚠ {len(no_res)} DOIs sin referencias resueltas "
                             "(OpenAlex las saca de depósitos Crossref; el astro pre-2000 no los tiene)")
        for r in anclados[:rows]:
            cfg.print_seguro(_row(r))
    elif del_tema:
        cfg.print_seguro(f"\n  (sin anclaje: el tema tiene {del_tema} paper(s) en la bóveda y "
                         f"NINGUNO trae `doi` — el anclaje sale de las referencias, que OpenAlex "
                         f"indexa por DOI; completá los `doi` que existan)")
    else:
        cfg.print_seguro("\n  (sin anclaje: el tema todavía no tiene papers en la bóveda — "
                         "corré primero la mitad ADS y volvé)")
    cfg.print_seguro("\n  → todo esto son CANDIDATOS: pasan por triage, no entran como core.")
    return 0


def main(argv=()) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topics", metavar="TEXTO", help="buscar el subtema en la taxonomía de OpenAlex")
    ap.add_argument("--seed", metavar="TOPIC_ID", help="top works de ese topic, por citas")
    ap.add_argument("--rows", type=int, default=25)
    ap.add_argument("--resolve", metavar="DOI", help="buscar una copia libre del PDF de ese DOI")
    ap.add_argument("--theme", metavar="SLUG",
                    help="cascada completa para un tema de themes.yaml (ADS + arXiv + OpenAlex, "
                         "más el anclaje si el tema ya bajó papers con DOI)")
    ap.add_argument("--min-citadores", type=int, default=2,
                    help="anclaje: mínimo de papers TUYOS que tienen que citar un trabajo (default 2)")
    args = ap.parse_args(list(argv) or None)

    if args.topics:
        for t in topics(args.topics):
            cfg.print_seguro(f'  {t["id"]:<8} works={t["works_count"]:<8} {t["name"]}')
        cfg.print_seguro("\n  → el filtro por topic es lo que hace usable el ranking por citas: "
                         "sin él, ordenar por citas trae los papers más citados del mundo, no del tema.")
        return 0
    if args.theme:
        return _preview_theme(args.theme, rows=args.rows, min_citadores=args.min_citadores)
    if args.resolve:
        url, why = resolve_pdf(args.resolve)
        cfg.print_seguro(f"  {url or '(sin copia libre)'}\n  motivo: {why}")
        return 0 if url else 1
    if args.seed:
        recs = seed(args.seed, rows=args.rows)
        cfg.print_seguro(f"  {len(recs)} works (preview — NO clasifica: son candidatos a triage)\n")
        for r in recs:
            cfg.print_seguro(_row(r))
        return 0
    ap.error("falta --topics o --seed")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
