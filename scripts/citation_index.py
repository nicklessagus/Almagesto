"""Índice invertido **obra citada → papers del corpus que la citan**.

PARA QUÉ, exactamente. Es el lookup de la **puerta 1** de D-26: cuando la query de un tema de
método trae candidatos, la puerta pregunta *"¿alguno de mis papers core cita a ESTE?"*. Es un
**filtro sobre lo que la búsqueda ya devolvió**, no una enumeración de lo que le falta a la bóveda.

El problema que resuelve, con el ejemplo de D-26: la lente global `require: [rv]` mata al paper
fundacional de ICA —Hyvärinen no menciona RV ni una vez— pero sin filtro *"independent component
analysis"* devuelve miles de papers de fMRI, EEG y finanzas. Hyvärinen tiene ~30k citas, casi todas
ajenas a esta bóveda; **lo que lo hace tuyo es que tu gente lo cita**. Esa señal no la puede
expresar ninguna regex, y por eso hace falta el grafo.

⛔ La puerta 1 **propone, no clasifica** (resolución §4.3 del plan): alimenta los candidatos del
triage, nunca marca core sola. INV-24 dice que ser core es función de `(paper, lente)` y sólo de
eso; si la cantidad de citas entrantes clasificara, `objective.yaml` dejaría de explicar el corpus.

DE DÓNDE SALEN LAS REFERENCIAS. De las **dos** fuentes, porque R-9 midió que ninguna alcanza: sobre
un corpus astro real ADS cubre el 80% y OpenAlex el 68%, pero en pre-2000 la diferencia es 65% vs
16% a favor de ADS, y de los papers off-ADS —la bibliografía de método que este eje existe para
servir— 14 sólo los tiene OpenAlex contra 3 sólo-ADS. La unión llegó al **84,3%** medido —477 de los 566 papers **core**; sobre las 908 notas del
corpus completo, que es el denominador que usa la proyección de R-9, da 83%— y ese techo se
**declara**: `cobertura` nombra los papers de los que no se pudo leer una sola referencia.
Un índice que calla su cobertura se lee como completo (INV-87).

DOS ESPACIOS DE IDENTIFICADORES. ADS devuelve bibcodes y OpenAlex ids `W…`, y **se solapan**: medido
sobre el corpus real, Zechmeister & Kürster 2009 está como `2009A&A...496..577Z` (lo citan 94) y
como `W4292309267` (82) — el mismo trabajo. Por eso el lookup acepta **varias llaves del mismo
trabajo** y une los citadores: preguntar por una sola da un falso negativo *"nadie lo cita"* cuando
el corpus lo cita por la otra vía. No se fusiona el índice entero —serían decenas de miles de
resoluciones de red— porque la pregunta se hace sobre los pocos candidatos de una query.

Regenerable ⇒ vive en `build/`. El **build** es caro (red sobre todo el corpus) y se corre aparte;
el **lookup** es offline, que es lo que permite usarlo dentro de la cadena sin pagar la red.
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

    import openalex
    ads_refs = fetch_ads([p["bibcode"] for p in core]) or {}
    dois = [p["doi"] for p in core if p.get("doi")]
    # La MISMA normalización con la que `refs_of` indexa. Consultar con el DOI crudo del
    # frontmatter (`https://doi.org/10.1/a`) devolvía vacío y el paper caía en `ciegos`: el
    # artefacto declaraba "OpenAlex no tenía referencias" sobre una clave que nunca se buscó —
    # cobertura MAL ATRIBUIDA, peor que cobertura faltante.
    oa_refs, oa_sin = fetch_oa(dois) if dois else ({}, [])

    citas: dict[str, list] = {}
    con_refs, ciegos = [], []
    for p in core:
        propias = list(ads_refs.get(p["bibcode"]) or [])
        if p.get("doi"):
            propias += list(oa_refs.get(openalex._bare_doi(p["doi"])) or [])
        # `dict.fromkeys` en vez de `set`: dedup CONSERVANDO el orden. Es defensa en profundidad,
        # no la garantía: el artefacto lo protege el `sorted(set(v))` de `citas` doce líneas abajo,
        # así que cambiar esto por `set` hoy **no** cambia el JSON (medido en #185, mutación
        # sobreviviente). Se mantiene porque `propias` se puede empezar a usar en otro lado, y ahí
        # el orden sí saldría — el mismo defecto que hubo que arreglar en `lint.orphans`.
        # ⚠ Lo que SÍ es observable es el `sorted(...)` de `sin_clave` doce líneas arriba: esa línea
        # va al JSON tal cual, y `tests/test_citation_index.py::test_determinista_ENTRE_PROCESOS`
        # la mata.
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
        "cobertura": {
            "n_core": len(core),
            "con_referencias": len(con_refs),
            "ciegos": sorted(ciegos),
            "sin_clave": sin_clave,
            # Lo que `refs_of` devuelve como no-resuelto y antes se descartaba: un paper con refs
            # de ADS cuyo DOI OpenAlex no resolvió NO es ciego, así que su cobertura parcial era
            # invisible. El módulo que exige declarar el techo tiraba la mitad del techo.
            "sin_refs_openalex": sorted(oa_sin),
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


def cited_by_corpus(idents, index: dict | None = None) -> list:
    """Qué papers core citan al trabajo identificado por `idents` (una llave o varias del **mismo**
    trabajo: bibcode, id de OpenAlex, lo que se tenga).

    Se unen los citadores de todas las llaves porque las dos fuentes usan espacios distintos y
    preguntar por una sola devuelve un falso negativo. **Offline**: se consume dentro de la cadena
    y no puede depender de que una API esté de buen humor."""
    idx = index if index is not None else load()
    if not idx:
        # Sin índice construido, `[]` sería indistinguible de "nadie lo cita" — y ésa es la
        # respuesta con la que la puerta 1 decide no proponer. Es el cero inventado que este mismo
        # módulo dice no producir (INV-87): un chequeo que no puede correr se declara.
        raise RuntimeError(
            f"no hay índice de citas en {_out_path(None)} — corré `citation_index.build()` antes. "
            "Devolver una lista vacía diría «nadie lo cita», que no es lo que se sabe.")
    citas = idx.get("citas") or {}
    llaves = [idents] if isinstance(idents, str) else list(idents)
    # El índice guarda el id de OpenAlex PELADO (`W9`) y `to_record` lo guarda como URL
    # (`https://openalex.org/W9`): sin normalizar, el lado OpenAlex del lookup falla siempre.
    llaves = [k.rsplit("/", 1)[-1] if isinstance(k, str) and k.startswith("http") else k
              for k in llaves if k]
    return sorted({p for k in llaves for p in (citas.get(k) or [])})



def main(argv=()) -> int:
    """CLI de la pasada de construcción — cara (red sobre todo el corpus), se corre aparte.

    Existe porque `docs/operacion.md` la publica como `python scripts/citation_index.py` desde que
    el módulo nació, y sin `__main__` el comando **corría, no imprimía nada y salía 0** sin construir
    el índice: el operador creía haberlo construido y `cited_by_corpus` levantaba `RuntimeError`
    después. Es el mismo cero inventado que este módulo dice no producir (INV-87), por la puerta del
    empaquetado."""
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=None, help=f"destino (default: build/{DEFAULT_OUT})")
    # `list(argv) or None` haría que `main([])` cayera a `sys.argv` — bajo pytest eso parsea los
    # argumentos DEL TEST RUNNER y aborta. El `__main__` ya pasa `sys.argv[1:]` explícito.
    args = ap.parse_args(list(argv))
    destino = build(out=Path(args.out) if args.out else None)
    idx = load(destino)
    cobertura = idx.get("cobertura") or {}
    cfg.print_seguro(f"→ {destino}")
    if cobertura:
        # AUD-132 — leía `con_refs`/`total`, claves que `build` NUNCA escribe (`con_referencias`
        # y `n_core`), así que la cobertura salía SIEMPRE `?/?`. El módulo que existe para declarar
        # su techo era el único que no lo publicaba. Se lee del mismo lugar que se escribe.
        cfg.print_seguro(
            f"cobertura: {cobertura.get('con_referencias', '?')}/{cobertura.get('n_core', '?')} "
            f"papers con al menos una referencia leída"
            + (f"; {len(cobertura.get('ciegos') or [])} sin ninguna" if cobertura.get("ciegos") else "")
            + (f"; {len(cobertura.get('sin_clave') or [])} sin clave consultable"
               if cobertura.get("sin_clave") else ""))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
