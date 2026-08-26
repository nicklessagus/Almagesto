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

CLI (preview only — writes nothing, downloads nothing):
    python scripts/discover.py --topics "blind source separation"
    python scripts/discover.py --theme ica
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.parse

import requests

import lib_config as cfg
import openalex as oa

TIMEOUT = 90
TOPICS_API = "https://api.openalex.org/topics"


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
    d = requests.get(url, timeout=TIMEOUT).json()
    return [{"id": (r.get("id") or "").rsplit("/", 1)[-1],
             "name": r.get("display_name"),
             "works_count": r.get("works_count")}
            for r in d.get("results", [])]


def seed(topic_id: str, rows: int = 25, min_citas: int | None = None) -> list[dict]:
    """Top works of one OpenAlex topic by citation count, normalised to the shared record schema.

    ⚠ The filter is looser than its name suggests, and it is worth knowing before reading the
    output: measured on T11447, the topic declares 55,210 works and `topics.id:` returns 169,977,
    because it matches secondary topic assignments too. This is a seed for triage, not a corpus."""
    url = oa.API + "?" + urllib.parse.urlencode(
        {"filter": f"topics.id:{topic_id}", "sort": "cited_by_count:desc",
         "per-page": min(rows, 200), "mailto": oa._mailto()})
    d = requests.get(url, timeout=TIMEOUT).json()
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
            d = requests.get(url, timeout=TIMEOUT).json()
        except Exception as e:                                  # noqa: BLE001 — declared, not swallowed
            cfg.print_seguro(f"  ⚠ hydrate: lote {i // 50 + 1} falló ({e}) — {len(lote)} sin resolver")
            continue
        out += [oa.to_record(w) for w in d.get("results", [])]
        time.sleep(0.2)
        if len(out) >= rows:
            break
    return out[:rows]


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
        d = requests.get(oa.API + "/doi:" + urllib.parse.quote(doi) + "?" +
                         urllib.parse.urlencode({"mailto": oa._mailto()}), timeout=TIMEOUT).json()
        url = ((d.get("best_oa_location") or {}).get("pdf_url"))
        if url:
            return url, "OpenAlex best_oa_location"
    except Exception as e:                                      # noqa: BLE001 — declarado, no tragado
        cfg.print_seguro(f"  ⚠ resolve_pdf: OpenAlex falló para {doi} ({e})")
    # 2. Unpaywall: mismo universo de depósitos, distinta resolución de OA locations
    try:
        d = requests.get(UNPAYWALL + urllib.parse.quote(doi) + "?" +
                         urllib.parse.urlencode({"email": oa._mailto()}), timeout=TIMEOUT).json()
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
    return (f'  {(r.get("citation_count") or 0):>6}  {r.get("year") or "----"}{cit}  '
            f'{",".join(r.get("found_in") or ["?"]):<12}  {t}')


def main(argv=()) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topics", metavar="TEXTO", help="buscar el subtema en la taxonomía de OpenAlex")
    ap.add_argument("--seed", metavar="TOPIC_ID", help="top works de ese topic, por citas")
    ap.add_argument("--rows", type=int, default=25)
    ap.add_argument("--resolve", metavar="DOI", help="buscar una copia libre del PDF de ese DOI")
    args = ap.parse_args(list(argv) or None)

    if args.topics:
        for t in topics(args.topics):
            cfg.print_seguro(f'  {t["id"]:<8} works={t["works_count"]:<8} {t["name"]}')
        cfg.print_seguro("\n  → el filtro por topic es lo que hace usable el ranking por citas: "
                         "sin él, ordenar por citas trae los papers más citados del mundo, no del tema.")
        return 0
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
