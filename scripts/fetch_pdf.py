"""Baja PDFs de papers SIN arXiv vía el resolver de ADS (esources) — completa a fetch_arxiv.

Uso:
    python scripts/fetch_pdf.py <slug> [--all] [--limit N] [--force]

Lee build/<slug>/ads.json y, para cada paper relevante SIN PDF en disco — los sin arxiv_id
(revistas viejas / sin e-print) y también los CON arXiv cuya bajada falló en fetch_arxiv
(#32: el resolver suele rescatarlos vía ADS_PDF/PUB_PDF cuando export.arxiv.org no entrega) —,
consulta el resolver de ADS (`/v1/resolver/<bibcode>/esource`) y prueba las fuentes en orden:

  EPRINT_PDF → ADS_PDF (escaneos alojados por ADS; el request VA con el token — verificado
  2026-07-17: sin el Bearer el host no entrega) → PUB_PDF (publisher; SIN token — el token ADS
  no viaja nunca fuera de *.adsabs.harvard.edu; requests además lo quita solo en un redirect
  cross-host. Variable por publisher: algunos WAF desafían el fingerprint de python-requests
  → fallback al MISMO pedido con `curl` del sistema (_curl_pdf); si tampoco, paywall real →
  se degrada).

Un PUB_PDF que viene como DOI pelado ("10.1086/…") se resuelve vía https://doi.org/. Los
placeholders del resolver (`$SIMBAD$`…) y los links HTML (ADS_SCAN /full/, *_HTML) se
descartan. Cada respuesta se valida por magic `%PDF` (el HTML de un paywall no se guarda) y
se reintenta con backoff (el host de escaneos throttlea ráfagas — medido en el probe).

Si el resolver no entrega y el paper tiene `doi`, sigue la **cascada de acceso abierto** (#358,
`fetch_free_copy`): OpenAlex → Unpaywall → Europe PMC → arXiv por título EXACTO (los candidatos
los arma `discover.iter_pdf_candidates`). Se recorren TODOS, no el primero — medido: la primera
URL (OUP) contestó un desafío Cloudflare con HTTP 200 y la copia real era la de Europe PMC—, y
cada uno se valida por magic `%PDF`.

Lo que ni así se consigue queda en build/<slug>/missing_pdf.json (superset del formato de
fetch_arxiv; al correr último en la cadena, es el residuo COMPLETO del ingest por verdad
de disco). Cada entrada lleva `bibstem`/`year`, un `hint` con la rama de la cascada MANUAL
por donde seguir (#50: "bajar por DOI" no alcanza — Messenger, página del instrumento,
mirror académico, o derivar al usuario si es un A&A pre-arXiv; el detalle de cada rama vive
en `## Notas` del skill ingest-star) y —#358— **`estado` + `copias_libres`**, que son lo primero
que hay que mirar: `sin-copia-libre` (ningún depósito tiene copia → pide `pending:`) contra
`bloqueado` (la hubo, y el host la bloqueó o no entregó un PDF → `copias_libres` lista las URL
probadas: bajarla a mano desde ahí antes del rescate manual). Salían iguales.
Idempotente: no re-baja lo que ya está en vault/raw/pdfs/<slug>/; `--force` re-intenta incluso
lo que ya tiene PDF (un PDF truncado por un corte anterior).

Deja además en build/<slug>/pdf_source.json qué rama entregó cada PDF (`eprint` | `ads` |
`publisher`; la cascada OA lo registra sólo cuando el candidato lo sabe —arXiv → `eprint`, una
`publishedVersion` → `publisher`— y si no queda desconocido), que make_notes estampa como
`pdf_source` en la nota (#57): distinguir el preprint de la versión publicada cambia cómo se lee
una discrepancia numérica al verificar citas.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

import lib_config as cfg

RESOLVER = "https://api.adsabs.harvard.edu/v1/resolver/{bibcode}/esource"
UA = {"User-Agent": f"Mozilla/5.0 (X11; Linux x86_64) Almagesto/{cfg.ALMAGESTO_VERSION} "
                    "(academic literature vault)"}
SLEEP_S = 2.0                        # cortesía entre papers (resolver + descarga)
RETRY_WAITS_S = (3, 8)               # backoff: el host de escaneos corta ráfagas (probe 2026-07-17)
RETRY_STATUS = (429, 500, 502, 503, 504)
# Subtipos de esource que son PDF bajable, en orden de preferencia. ADS_SCAN (visor /full/,
# HTML) y los *_HTML no sirven como fuente de la bóveda.
PDF_TYPES = ("EPRINT_PDF", "ADS_PDF", "PUB_PDF")
# Qué DOCUMENTO entrega cada rama del resolver (#57): el eprint de arXiv puede ser un v1
# pre-referato (valores y secciones distintos de la versión publicada que cita el bibcode);
# ADS_PDF suele ser el escaneo del publicado; PUB_PDF es el publicado. Se registra al bajar.
# #296 — los valores DERIVAN de la constante, no la duplican (regla de método nº 2: un doble con
# otro contrato esconde el bug en la diferencia). Acá el "doble" era este dict: si alguien renombra
# un valor del vocabulario, el escritor seguiría estampando el viejo y el lint lo bloquearía.
PDF_SOURCE = dict(zip(("EPRINT_PDF", "ADS_PDF", "PUB_PDF"), cfg.PDF_SOURCE_OK))

# Ramas de la cascada MANUAL de rescate (issue #50): lo que el resolver no entrega se busca a mano,
# y el bibstem dice por dónde empezar (medido en un ingest real: 5 de 17 fallaron; 4 se recuperaron
# por estas ramas). El detalle de cada rama vive en `## Notas` del skill ingest-star — acá sólo el
# puntero para no re-descubrirla en cada ingest.
RESCUE_HINTS = {
    "Msngr": "archivo abierto de The Messenger (eso.org/sci/publications/messenger/archive/)",
    "SPIE": "página de papers del instrumento (los SPIE suelen estar en abierto ahí) o mirror académico",
}
AANDA_STEMS = ("A&A", "A&AS")
AANDA_PREARXIV_YEAR = 2005     # A&A anterior al depósito sistemático en arXiv: sin preprint


def rescue_hint(bibstem: str | None, year=None) -> str:
    """Rama sugerida de la cascada manual para un fallo del resolver, según el bibstem."""
    stem = (bibstem or "").strip()
    for key, hint in RESCUE_HINTS.items():
        if stem.startswith(key):
            return hint
    try:
        yr = int(year)
    except (TypeError, ValueError):
        yr = None
    if stem.startswith(AANDA_STEMS) and yr is not None and yr < AANDA_PREARXIV_YEAR:
        return ("A&A pre-arXiv: aanda.org está detrás de DataDome (ningún curl pasa) y no hay preprint "
                "→ derivar al usuario (acceso institucional), no gastar intentos")
    return "mirror académico / tablas del CDN del publisher / pedir el PDF al usuario"


safe_name = cfg.note_stem       # alias kept for callers/tests; ONE rule in lib_config (AUD-273)


def write_pdf_atomic(dest: Path, data: bytes) -> bool:
    """Escritura atómica del PDF final, vía `cfg.write_bytes_atomic` (D-53: un solo writer
    atómico en el repo; esta función y su gemela de la otra vía de bajada eran dos clones del
    patrón tmp+os.replace).

    H-07: antes se escribía el destino directo — un corte a mitad (proceso matado, disco lleno)
    deja un PDF TRUNCADO en el destino FINAL (medido: 35 B), y el único chequeo de idempotencia
    de la cadena es `dest.exists()`: ese PDF roto cuenta como "ya bajado" para siempre, sin forma
    de reintentarlo salvo borrarlo a mano. Con la escritura atómica un corte NUNCA deja nada en
    `dest`: o el PDF completo se publica, o `dest` sigue sin existir y la próxima corrida lo
    reintenta sola. `False` si la publicación falló (queda como "no conseguido" → entra al
    residuo, igual que si la fuente no hubiera entregado nada)."""
    try:
        cfg.write_bytes_atomic(dest, data)
        return True
    except OSError as e:
        cfg.print_seguro(f"      ✗ no se pudo escribir {dest.name} en disco: {e}")
        return False


def is_ads_host(url: str) -> bool:
    """True sólo para *.adsabs.harvard.edu (o el host pelado). H-19: `netloc.endswith(...)` sin
    chequear el punto de borde acepta hosts que NO son subdominios — `is_ads_host
    ('https://xadsabs.harvard.edu/x')` daba `True`, y el token ADS (higiene de credenciales, ver
    `download_pdf`) viajaría a un host que sólo se PARECE al de ADS. `.hostname` (vía urlparse)
    ya descarta userinfo/puerto; el chequeo de igualdad + sufijo CON el punto (`.adsabs...`) es lo
    que impone el límite de subdominio."""
    host = (urlparse(url).hostname or "").lower()
    return host == "adsabs.harvard.edu" or host.endswith(".adsabs.harvard.edu")


def esource_records(bibcode: str, token: str) -> list[dict]:
    """Registros esource del resolver para un bibcode; [] si no hay o falla (tolerante — un
    resolver caído no aborta el barrido). Con UNA sola fuente el resolver devuelve `link`
    directo en vez de `links.records`; se normaliza a la misma forma.

    ⚠ AUD-162 — el `[]` fusiona dos estados que piden cosas distintas: *«el resolver contestó y
    este paper no tiene PDF»* (rescate manual, que es lo que el `hint` de `missing_pdf.json`
    propone) y *«el resolver no contestó»* (re-correr la cadena más tarde; **no** hay nada que
    rescatar a mano). El llamador los trataba igual y el residuo salía diciendo «sin fuentes PDF en
    el resolver» sobre un paper al que nadie le preguntó. Se mantiene el `[]` —tolerar la caída es
    correcto y cambiar la firma movería a todos los llamadores— y la diferencia se **dice**."""
    try:
        resp = requests.get(RESOLVER.format(bibcode=bibcode),
                            headers={"Authorization": f"Bearer {token}", **UA}, timeout=60)
    except requests.RequestException as exc:
        cfg.print_seguro(f"      ⚠ el resolver de ADS no contestó por {bibcode} ({exc.__class__.__name__}) "
                         f"— NO es «este paper no tiene PDF»: nadie preguntó. Re-corré la cadena.",
                         file=sys.stderr)
        return []
    if resp.status_code != 200:
        cfg.print_seguro(f"      ⚠ el resolver de ADS devolvió HTTP {resp.status_code} por {bibcode} "
                         f"— NO es «este paper no tiene PDF»: nadie preguntó. Re-corré la cadena.",
                         file=sys.stderr)
        return []
    try:
        data = resp.json()
    except ValueError:
        cfg.print_seguro(f"      ⚠ el resolver de ADS contestó algo que no es JSON por {bibcode} "
                         f"— NO es «este paper no tiene PDF».", file=sys.stderr)
        return []
    # La respuesta viene de la RED: su forma no está garantizada. Un `links` que no es mapa —o un
    # `records` que no es lista— llegaba tal cual al `.get`/iteración y volteaba el resolver con
    # AttributeError, abortando la bajada de TODO el slug por un solo registro raro.
    data = cfg.as_map(data)
    recs = [r for r in cfg.as_list(cfg.as_map(data.get("links")).get("records")) if isinstance(r, dict)]
    if not recs and isinstance(data.get("link"), str):
        recs = [{"url": data["link"], "link_type": str(data.get("link_type") or "")}]
    return recs


def candidate_urls(records: list[dict]) -> list[tuple[str, str]]:
    """(subtipo, url) bajables en orden de preferencia (PDF_TYPES). Filtra placeholders sin
    resolver (`$SIMBAD$`…) y normaliza un PUB_PDF que viene como DOI pelado → https://doi.org/."""
    by_type: dict[str, str] = {}
    for r in records:
        sub = (r.get("link_type") or "").split("|")[-1]
        url = (r.get("url") or "").strip()
        if not url or "$" in url or sub not in PDF_TYPES or sub in by_type:
            continue
        if not url.startswith("http"):
            url = f"https://doi.org/{url}"           # DOI pelado (visto en el probe: 10.1086/…)
        by_type[sub] = url
    return [(t, by_type[t]) for t in PDF_TYPES if t in by_type]


def _curl_pdf(url: str) -> bytes | None:
    """Fallback con `curl` del sistema para PUBLISHERS: algunos WAF (Radware en IOP, medido
    2026-07-17) desafían el fingerprint TLS de python-requests pero aceptan el MISMO pedido
    (misma URL y User-Agent) hecho con curl, otro cliente HTTP estándar. Sin token (es un
    publisher). None si no hay curl o no entregó un PDF real."""
    if shutil.which("curl") is None:
        return None
    # TemporaryDirectory y no NamedTemporaryFile: en Windows el archivo con nombre queda abierto
    # por Python y curl no puede escribirlo (sharing violation).
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "dl.pdf"
        r = subprocess.run(["curl", "-sL", "--max-time", "120", "-A", UA["User-Agent"],
                            "-o", str(dest), url], capture_output=True, text=True)
        data = dest.read_bytes() if r.returncode == 0 and dest.exists() else b""
    return data if data[:4] == b"%PDF" else None


def download_pdf(url: str, token: str) -> bytes | None:
    """GET con retries/backoff. El token SÓLO viaja a *.adsabs.harvard.edu (y requests lo
    descarta solo si un redirect cambia de host). Valida el magic %PDF (el HTML de un paywall
    o de un challenge de bot no se guarda). Para publishers, si requests no consigue el PDF,
    cae a `curl` del sistema (_curl_pdf). None si nada entregó — el caller prueba la
    siguiente fuente."""
    headers = dict(UA)
    ads = is_ads_host(url)
    if ads:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    for wait in (*RETRY_WAITS_S, None):
        try:
            resp = requests.get(url, headers=headers, timeout=120, allow_redirects=True)
        except requests.RequestException:            # conexión cortada (throttling de ráfagas)
            if wait is None:
                break
            time.sleep(wait)
            continue
        if resp.status_code in RETRY_STATUS and wait is not None:
            time.sleep(wait)
            continue
        if resp.status_code == 200 and resp.content[:4] == b"%PDF":
            data = resp.content
        break
    if data is None and not ads:
        data = _curl_pdf(url)
    return data


def fetch_free_copy(slug: str, r: dict, dest: Path, token: str) -> tuple[bool, list]:
    """Walk EVERY open-access candidate for record `r` (#358) and publish the first real PDF at
    `dest` → `(got one, urls tried)`.

    Cascade: OpenAlex → Unpaywall → Europe PMC → arXiv by exact title (`discover`). All of them,
    not the first: measured, the first URL (OUP) answered a Cloudflare challenge with HTTP 200 and
    the real copy was Europe PMC's. `download_pdf` validates the `%PDF` magic, so that HTML never
    lands with a `.pdf` extension. The urls tried are what separates «no free copy» from «there
    was one and the host blocked it» in the residue — those two ask for opposite actions.
    Records `pdf_source` (#57) only when the candidate knows it (arXiv → `eprint`, a
    `publishedVersion` OA location → `publisher`); otherwise it stays unknown."""
    bib = r["bibcode"]
    tried: list = []
    for url, why, src in oa_candidates(r.get("doi"), r.get("title")):
        tried.append(url)
        pdf = download_pdf(url, token)
        if pdf and write_pdf_atomic(dest, pdf):
            cfg.print_seguro(f"      ✓ copia libre ({why}) → {dest.name} ({len(pdf)} bytes)")
            if src:
                cfg.record_pdf_source(slug, safe_name(bib), src)
            return True, tried
        cfg.print_seguro(f"      · copia libre ({why}) no entregó PDF: {url}")
    return False, tried


def oa_candidates(doi: str | None, title: str | None = None):
    """Free-copy candidates for one DOI, in cascade order (#358): `discover.iter_pdf_candidates`,
    imported here so tests can double it. The ADS lane never asked the open-access resolver the
    repo already had — the exact mirror of #313 — and measured, 2 of 6 papers declared «sin
    conseguir» in one theme were open access, with `discover.py --resolve` returning their URL."""
    import discover
    return discover.iter_pdf_candidates(doi, title)


def drop_filter(recs: list, slug: str) -> tuple[list, list]:
    """Split `recs` into (fetchable, actively dropped by the user for this subject).

    ⛔ AUD-137 — `--all` means «include the non-relevant ones», and a paper the user removed with
    `triage --drop-core` is left in the record precisely so it stays VISIBLE (`via: manual-drop`,
    with its motive). Neither fetcher consulted `load_decisiones`, so the escape hatch re-downloaded
    exactly what #112 deletes from disk on purpose: a curation decision that a script quietly
    undoes is worse than not having taken it.

    Also skipped: a bibcode declared as an alias in some note's `versions[]` (D-19) — same work,
    already on disk under the canonical bibcode.

    Both carriles are honoured: the chaining drop and the per-subject one. A decision that was
    `anulada` (D-52) is not a drop any more, and `load_decisiones` only returns what the registro
    says — an unreadable registro raises rather than reviving everything (INV-139)."""
    fuera = {b for b, d in cfg.load_decisiones(slug).items() if d.get("decision") == "descartado"}
    # D-19 — y el bibcode que alguna nota declara como ALIAS de sí misma en `versions[]`: es el
    # MISMO trabajo, ya está en disco bajo el bibcode canónico. Sin esto, después de un
    # `--rename-paper` la próxima corrida lo re-bajaba y el lint reportaba el par PDF+`.txt` como
    # artefacto colgado **para siempre** — no tiene nota, y no puede tenerla (#229 bloquea la
    # segunda). Medido en una bóveda real: la copia sobrante quedó fechada un día DESPUÉS de la
    # consolidación, byte a byte idéntica.
    fuera |= cfg.alias_bibcodes()
    if not fuera:
        return recs, []
    dentro = [r for r in recs if r.get("bibcode") not in fuera]
    dropeados = [r for r in recs if r.get("bibcode") in fuera]
    return dentro, dropeados


def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug")
    ap.add_argument("--all", action="store_true", help="incluir no-relevantes")
    ap.add_argument("--limit", type=int, default=0, help="máximo a intentar (0 = sin límite)")
    ap.add_argument("--force", action="store_true",
                    help="re-intentar incluso lo que ya tiene PDF en disco (p. ej. un PDF "
                         "truncado por un corte anterior — H-07: nada valida el contenido de lo "
                         "ya bajado, ésta es la vía de escape manual)")
    args = ap.parse_args()

    adsfile = cfg.ROOT / "build" / args.slug / "ads.json"
    if not adsfile.exists():
        cfg.print_seguro(f"No existe {adsfile}. Corré primero query_ads.py {args.slug}")
        return 1
    data = json.loads(adsfile.read_text(encoding="utf-8"))
    recs = data["records"]
    if not args.all:
        recs = [r for r in recs if r["relevant"]]
    recs, dropeados = drop_filter(recs, args.slug)          # AUD-137: ni con `--all`
    if dropeados:
        cfg.print_seguro(f"  · {len(dropeados)} excluido(s) por decisión de curación vigente "
                         f"(`triage --drop`/`--drop-core`): {', '.join(r['bibcode'] for r in dropeados[:5])}"
                         + (" …" if len(dropeados) > 5 else ""))

    destdir = cfg.PDFS / args.slug
    destdir.mkdir(parents=True, exist_ok=True)

    # objetivo: TODO paper relevante sin PDF en disco (#32) — los sin arXiv (su única vía es
    # este resolver) y los con arXiv cuya bajada falló en fetch_arxiv (antes quedaban invisibles:
    # ni acá ni en el missing_pdf.json final). Verdad de disco: lo ya bajado no se toca (salvo
    # --force, H-07: la única forma de reemplazar un PDF truncado congelado).
    pendientes = [r for r in recs
                  if args.force or not (destdir / f"{safe_name(r['bibcode'])}.pdf").exists()]
    # D-18: antes de gastar red, reusar el PDF que YA está bajado bajo otro slug. Es el mismo
    # bibcode: el archivo es idéntico. Se copia (no symlink: `raw/` viaja en git-lfs y un enlace
    # roto es peor que una copia).
    # ⚠ `--force` **no** entra acá (gemelo de `fetch_arxiv.py`, que ya lo hacía bien). El reuso
    # entre slugs es una optimización sobre "el archivo ya existe y es el mismo bibcode"; `--force`
    # es la única vía de escape documentada para reemplazar un PDF **truncado o congelado**, y con
    # el reuso adentro lo sobreescribía con la copia de otro slug —sin validar `%PDF`— y lo sacaba
    # de pendientes: la escotilla hacía exactamente lo contrario de lo que promete.
    reusados = 0
    for r in ([] if args.force else list(pendientes)):
        stem = safe_name(r["bibcode"])
        otro = cfg.artefacto_en_otro_slug(cfg.PDFS, args.slug, stem, ".pdf")
        if otro is not None:
            cfg.write_bytes_atomic(destdir / f"{stem}.pdf", otro.read_bytes())
            cfg.print_seguro(cfg.reuse_note(r["bibcode"], otro))   # #297: qué NO se chequeó
            pendientes.remove(r)
            reusados += 1
    skipped = len(recs) - len(pendientes)
    todo = pendientes[: args.limit] if args.limit else pendientes
    # H-05: con --limit, `todo` es un SUBSET arbitrario de lo pendiente — lo que queda afuera no
    # se intentó, no "falló". Antes `missing` (calculado sólo sobre `todo`) se escribía igual, y
    # si daba vacío se BORRABA el residuo completo (medido: 4 papers, 1 bajado con --limit 1,
    # residuo de los otros 3 borrado, cierre "sin conseguir 0"). El residuo es, por contrato
    # (docstring del módulo), "el residuo COMPLETO del ingest" — con --limit no puede serlo, así
    # que ni se escribe ni se borra: se deja el archivo tal como estaba.
    limited = bool(args.limit) and len(todo) < len(pendientes)
    token = cfg.get_ads_token()

    label = data.get("star") or data.get("title") or args.slug
    n_arx = sum(1 for r in todo if r.get("arxiv_id"))
    cfg.print_seguro(f"{label}: {len(todo)} sin PDF → resolver de ADS (esources)"
                      + (f" ({n_arx} con arXiv cuya bajada falló)" if n_arx else ""))
    got = 0
    missing = []
    for i, r in enumerate(todo, 1):
        bib = r["bibcode"]
        dest = destdir / f"{safe_name(bib)}.pdf"
        cands = candidate_urls(esource_records(bib, token))
        cfg.print_seguro(f"  [{i}/{len(todo)}] {bib}: "
                          + (", ".join(t for t, _ in cands) if cands
                             else "sin fuentes PDF en el resolver"))
        ok = False
        for sub, url in cands:
            pdf = download_pdf(url, token)
            if pdf and write_pdf_atomic(dest, pdf):
                cfg.print_seguro(f"      ✓ {sub} → {dest.name} ({len(pdf)} bytes)")
                got += 1
                cfg.record_pdf_source(args.slug, safe_name(bib), PDF_SOURCE[sub])   # #57
                ok = True
                break
            elif pdf:
                pass    # write_pdf_atomic ya imprimió el motivo; probar la siguiente fuente
            else:
                cfg.print_seguro(f"      · {sub} no entregó PDF")
        # #358 — agotados los `esource` de ADS, el resolver de acceso abierto ANTES de rendirse.
        copias_libres: list = []
        if not ok and r.get("doi"):
            ok, copias_libres = fetch_free_copy(args.slug, r, dest, token)
            got += int(ok)
        if not ok:
            hint = rescue_hint(r.get("bibstem"), r.get("year"))
            # Tres estados, no uno (#358): «no hay copia libre» pide `pending:`; «la hubo y el
            # host la bloqueó» pide otro depósito o bajarla a mano desde esa URL. Salían iguales.
            estado = "bloqueado" if copias_libres else "sin-copia-libre"
            missing.append({"bibcode": bib, "title": r.get("title"), "doi": r.get("doi"),
                            "bibstem": r.get("bibstem"), "year": r.get("year"), "hint": hint,
                            "estado": estado, "copias_libres": copias_libres})
            if copias_libres:
                cfg.print_seguro(f"      → había copia libre y el host la bloqueó o no entregó un PDF "
                                 f"({len(copias_libres)} URL en missing_pdf.json): probá bajarla a "
                                 f"mano desde ahí antes del rescate manual")
            else:
                cfg.print_seguro(f"      → sin copia libre en OpenAlex, Unpaywall, Europe PMC ni arXiv"
                                 + ("" if r.get("doi") else " (sin DOI: no se consultaron)")
                                 + f" → rescate manual [{r.get('bibstem') or 'sin bibstem'}]: {hint}")
        time.sleep(SLEEP_S)

    n_bloq = sum(1 for m in missing if m["estado"] == "bloqueado")
    cfg.print_seguro(f"Bajados {got}, ya estaban {skipped}, sin conseguir {len(missing)}"
                     + (f" ({n_bloq} con copia libre que el host bloqueó)" if n_bloq else "") + ".")
    miss = cfg.ROOT / "build" / args.slug / "missing_pdf.json"
    if limited:
        cfg.print_seguro(f"  ⚠ --limit activo: quedaron {len(pendientes) - len(todo)} paper(s) "
                          "sin intentar — el residuo en missing_pdf.json NO se toca (no sería "
                          "completo). Corré sin --limit para cerrar el residuo por verdad de disco.")
    elif missing:
        cfg.write_text_atomic(miss, json.dumps(missing, indent=2, ensure_ascii=False))
        cfg.print_seguro(f"Residuo en {miss} — cada entrada trae su `hint` (rama de la cascada "
                          "manual según el bibstem); detalle en `## Notas` del skill ingest-star. "
                          "Lo que no salga: pedir el PDF al usuario / marcar `pending`.")
    elif miss.exists():
        miss.unlink()      # el listado de fetch_arxiv quedó cubierto: no dejar un residuo viejo
    # #304 — simétrico de `extract_fulltext` → `stamp_fulltext`: el PDF ya está en disco, así que
    # la nota que ya existe se estampa por verdad de disco. Sin esto, un PDF que aparece DESPUÉS
    # del stub —el rescate manual, o cerrar un `pending`— no se linkea nunca y la nota afirma
    # `pdf: null` sobre un archivo que está ahí.
    import make_notes
    _stamped = sum(1 for r in recs
                   if make_notes.stamp_pdf(cfg.PAPERS / f"{safe_name(r['bibcode'])}.md",
                                           safe_name(r["bibcode"])))
    if _stamped:
        cfg.print_seguro(f"  {_stamped} nota(s) con `pdf:` estampado por verdad de disco (#304)")
    cfg.save_paso(args.slug, "fetch_pdf", flags=cfg.flags_usados(args, ap))
    return 0


if __name__ == "__main__":
    cfg.cli_exit(main)
