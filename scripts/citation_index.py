"""Índice invertido **obra citada → papers del corpus que la citan**.

PARA QUÉ. Es el insumo de la **puerta 1** de D-26 (INV-88): un trabajo que citan N papers core de
la bóveda es un **candidato** del triage. ⛔ Nunca core automático — INV-24 dice que ser core es
función de `(paper, lente)` y sólo de eso; si la cantidad de citas entrantes clasificara, la lente
dejaría de ser la única regla y `objective.yaml` dejaría de explicar el corpus.

DE DÓNDE SALEN LAS REFERENCIAS. De las **dos** fuentes, porque R-9 midió que ninguna es
prescindible: sobre un corpus astro real ADS cubre el 80% y OpenAlex el 68%, pero en pre-2000 la
diferencia es 65% vs 16% a favor de ADS, y de los papers off-ADS —la bibliografía de método que el
eje tema existe para servir— 14 sólo los tiene OpenAlex contra 3 sólo-ADS. La unión llegó al 83%,
y **ese techo se declara**: `cobertura` nombra los papers de los que no se pudo leer ninguna
referencia. Un índice que calla su cobertura se lee como completo (INV-87).

DOS ESPACIOS DE IDENTIFICADORES, Y HAY QUE FUSIONARLOS — PERO TARDE. ADS devuelve bibcodes y
OpenAlex ids `W…`: universos distintos que **se solapan mucho**. Medido sobre el corpus real
(2026-08-24): el candidato más citado salía **partido en dos** —`2009A&A...496..577Z` con 94
citadores y `W4292309267` con 82 son el mismo paper, Zechmeister & Kürster 2009— y lo mismo Mayor
& Queloz (85 y 68). Sin fusionar, el triage ve dos candidatos con la mitad del peso cada uno.

La fusión se hace por **DOI** y **sólo sobre los candidatos que pasan el umbral** (`merge_candidates`),
no sobre el índice entero: el corpus real dio **20.824 obras citadas** contra **214 candidatos con
≥20 citadores**, así que resolver todo sería una pasada de red dos órdenes de magnitud más cara
para responder la misma pregunta. Lo que **no** tiene DOI no se fusiona: inventar la equivalencia
crea una arista falsa, y en R-9 el matcheo laxo (por título) erró 2 de 18.

Regenerable ⇒ vive en `build/` (regla de oro del registro: `build/` guarda lo que se recupera
pidiéndolo de nuevo; el registro guarda el juicio, que no).
"""
from __future__ import annotations

import json
from pathlib import Path

import lib_config as cfg

DEFAULT_OUT = "citation_index.json"


def _out_path(out: Path | None) -> Path:
    return Path(out) if out else (cfg.ROOT / "build" / DEFAULT_OUT)


def corpus_idents() -> list[dict]:
    """Los papers **core** de la bóveda, con sus llaves de consulta.

    `relevance: low` no entra: la puerta 1 pregunta cuántos papers **core** citan la obra, y un
    no-core no vota. El paper **sin clave** tampoco entra al conteo — se reporta aparte, porque
    saltearlo en silencio bajaría el denominador de la cobertura sin que nadie lo vea."""
    out = []
    for f in sorted(cfg.PAPERS.glob("*.md")):
        fm = cfg.split_fm(f.read_text(encoding="utf-8"))
        if not isinstance(fm, dict) or "paper" not in (fm.get("tags") or []):
            continue
        if (fm.get("relevance") or "").lower() == "low":
            continue
        out.append({"stem": f.stem, "bibcode": fm.get("bibcode"),
                    "doi": fm.get("doi"), "arxiv_id": fm.get("arxiv_id")})
    return out


def _fetch_ads_default(bibcodes: list) -> dict:
    """Referencias por bibcode desde ADS (`fl=reference`). Import perezoso: el lookup es offline."""
    import query_ads  # noqa: F401  (comparte el token y el cliente)
    import requests
    token = cfg.get_ads_token()
    refs: dict[str, list] = {}
    B = 40
    for i in range(0, len(bibcodes), B):
        lote = bibcodes[i:i + B]
        q = "bibcode:(" + " OR ".join(f'"{b}"' for b in lote) + ")"
        r = requests.get("https://api.adsabs.harvard.edu/v1/search/query",
                         params={"q": q, "fl": "bibcode,reference", "rows": len(lote) + 5},
                         headers={"Authorization": f"Bearer {token}"}, timeout=90)
        r.raise_for_status()
        for d in r.json()["response"]["docs"]:
            refs[d["bibcode"]] = list(d.get("reference") or [])
    return refs


def _fetch_oa_default(dois: list) -> tuple[dict, list]:
    import openalex
    return openalex.refs_of(dois)


def build(out: Path | None = None, fetch_ads=None, fetch_oa=None) -> Path:
    """Construye el índice y lo escribe. Los fetchers se inyectan para poder testear sin red."""
    fetch_ads = fetch_ads or _fetch_ads_default
    fetch_oa = fetch_oa or _fetch_oa_default
    papers = corpus_idents()
    sin_clave = sorted(p["stem"] for p in papers if not p.get("bibcode"))
    core = [p for p in papers if p.get("bibcode")]

    ads_refs = fetch_ads([p["bibcode"] for p in core]) or {}
    dois = [p["doi"] for p in core if p.get("doi")]
    oa_refs, _oa_sin = fetch_oa(dois) if dois else ({}, [])

    citas: dict[str, list] = {}
    con_refs, ciegos = [], []
    for p in core:
        propias = list(ads_refs.get(p["bibcode"]) or [])
        if p.get("doi"):
            propias += list(oa_refs.get(p["doi"]) or [])
        # `dict.fromkeys` en vez de `set`: dedup CONSERVANDO el orden. Un `set` de strings itera en
        # orden dependiente del hash, y eso volvería el artefacto no determinista entre procesos —
        # el mismo defecto que hubo que arreglar en `lint.orphans`.
        propias = list(dict.fromkeys(propias))
        if not propias:
            ciegos.append(p["stem"])
            continue
        con_refs.append(p["stem"])
        for obra in propias:
            citas.setdefault(obra, []).append(p["stem"])

    doc = {
        "generator": f"Almagesto v{cfg.ALMAGESTO_VERSION}",
        "citas": {k: sorted(set(v)) for k, v in sorted(citas.items())},
        "del_corpus": sorted(p["bibcode"] for p in core),
        "cobertura": {
            "n_core": len(core),
            "con_referencias": len(con_refs),
            "ciegos": sorted(ciegos),
            "sin_clave": sin_clave,
        },
    }
    dest = _out_path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Sin fecha adentro: el artefacto tiene que ser byte-idéntico ante el mismo insumo, o el
    # `--check` de cualquier consumidor daría diff siempre.
    cfg.write_text_atomic(dest, json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    return dest


def load(path: Path | None = None) -> dict:
    p = _out_path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cited_by_corpus(ident: str, index: dict | None = None) -> list:
    """Qué papers core citan a `ident`. **Offline**: lo consume el triage en cada corrida, y no
    puede depender de que una API esté de buen humor."""
    idx = index if index is not None else load()
    return list((idx.get("citas") or {}).get(ident) or [])


def candidates(min_citers: int = 2, index: dict | None = None) -> list:
    """Obras citadas por ≥ `min_citers` papers core y que **la bóveda todavía no tiene**.

    Lo segundo importa tanto como lo primero: proponer un paper que ya está ingestado es ruido, y
    el ruido es lo que hace que una compuerta se empiece a ignorar."""
    idx = index if index is not None else load()
    ya = set(idx.get("del_corpus") or [])
    return [(obra, citadores) for obra, citadores in sorted((idx.get("citas") or {}).items())
            if len(citadores) >= min_citers and obra not in ya]


def _resolver_default(claves: list) -> dict:
    """`{clave → doi | None}` para claves mezcladas (bibcodes de ADS e ids `W…` de OpenAlex).

    Import perezoso y una pasada por espacio: se llama sólo con los candidatos del umbral."""
    import requests
    out: dict[str, str | None] = {k: None for k in claves}
    ws = [k for k in claves if k.startswith("W") and k[1:].isdigit()]
    bibs = [k for k in claves if k not in ws]
    for i in range(0, len(ws), 50):
        lote = ws[i:i + 50]
        r = requests.get("https://api.openalex.org/works",
                         params={"per-page": 50, "select": "id,doi",
                                 "filter": "openalex_id:" + "|".join(lote)}, timeout=60)
        r.raise_for_status()
        for w in r.json().get("results", []):
            doi = (w.get("doi") or "").replace("https://doi.org/", "").lower() or None
            out[w["id"].split("/")[-1]] = doi
    if bibs:
        token = cfg.get_ads_token()
        for i in range(0, len(bibs), 40):
            lote = bibs[i:i + 40]
            q = "bibcode:(" + " OR ".join(f'"{b}"' for b in lote) + ")"
            r = requests.get("https://api.adsabs.harvard.edu/v1/search/query",
                             params={"q": q, "fl": "bibcode,doi", "rows": len(lote) + 5},
                             headers={"Authorization": f"Bearer {token}"}, timeout=90)
            r.raise_for_status()
            for d in r.json()["response"]["docs"]:
                out[d["bibcode"]] = ((d.get("doi") or [None])[0] or "").lower() or None
    return out


def merge_candidates(cands: list, resolver=None) -> list:
    """Fusiona por DOI los candidatos que son **el mismo trabajo** visto por las dos fuentes.

    Devuelve `[(clave, citadores_unidos, alias)]`, donde `clave` es el DOI cuando se pudo resolver
    y el id original cuando no, y `alias` son los ids que se fusionaron — quedan **a la vista**
    porque el triage tiene que poder ir a buscar la obra en cualquiera de las dos fuentes.

    Los citadores se **unen**, no se suman: el mismo paper del corpus puede aportar la obra por ADS
    y por OpenAlex a la vez, y sumar lo contaría dos veces."""
    resolver = resolver or _resolver_default
    dois = resolver([obra for obra, _ in cands])
    grupos: dict[str, dict] = {}
    for obra, citadores in cands:
        doi = dois.get(obra)
        clave = doi or obra
        g = grupos.setdefault(clave, {"citadores": set(), "alias": set()})
        g["citadores"].update(citadores)
        if doi:
            g["alias"].add(obra)
    return [(clave, sorted(g["citadores"]), sorted(g["alias"]))
            for clave, g in sorted(grupos.items(), key=lambda kv: (-len(kv[1]["citadores"]), kv[0]))]
