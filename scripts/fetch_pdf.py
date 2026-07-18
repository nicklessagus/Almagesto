"""Baja PDFs de papers SIN arXiv vía el resolver de ADS (esources) — completa a fetch_arxiv.

Uso:
    python fetch_pdf.py <slug> [--all] [--limit N]

Lee build/<slug>/ads.json y, para cada paper relevante SIN arxiv_id (revistas viejas /
sin e-print — los que tienen arXiv los baja fetch_arxiv.py) cuyo PDF no esté ya en disco,
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

Lo que ni así se consigue queda en build/<slug>/missing_pdf.json (mismo formato que
fetch_arxiv: residuo a conseguir a mano vía DOI, o marcar `pending` en la fuente).
Idempotente: no re-baja lo que ya está en vault/raw/pdfs/<slug>/.
"""
from __future__ import annotations

import argparse
import json
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


def safe_name(bibcode: str) -> str:
    return bibcode.replace("/", "_")


def is_ads_host(url: str) -> bool:
    return urlparse(url).netloc.endswith("adsabs.harvard.edu")


def esource_records(bibcode: str, token: str) -> list[dict]:
    """Registros esource del resolver para un bibcode; [] si no hay o falla (tolerante — un
    resolver caído no aborta el barrido). Con UNA sola fuente el resolver devuelve `link`
    directo en vez de `links.records`; se normaliza a la misma forma."""
    try:
        resp = requests.get(RESOLVER.format(bibcode=bibcode),
                            headers={"Authorization": f"Bearer {token}", **UA}, timeout=60)
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    recs = (data.get("links") or {}).get("records") or []
    if not recs and data.get("link"):
        recs = [{"url": data["link"], "link_type": data.get("link_type", "")}]
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--all", action="store_true", help="incluir no-relevantes")
    ap.add_argument("--limit", type=int, default=0, help="máximo a intentar (0 = sin límite)")
    args = ap.parse_args()

    adsfile = cfg.ROOT / "build" / args.slug / "ads.json"
    if not adsfile.exists():
        print(f"No existe {adsfile}. Corré primero query_ads.py {args.slug}")
        return 1
    data = json.loads(adsfile.read_text(encoding="utf-8"))
    recs = data["records"]
    if not args.all:
        recs = [r for r in recs if r["relevant"]]

    destdir = cfg.PDFS / args.slug
    destdir.mkdir(parents=True, exist_ok=True)

    # objetivo: los SIN arXiv (fetch_arxiv cubre el resto) que no estén ya bajados
    todo = [r for r in recs if not r.get("arxiv_id")]
    if args.limit:
        todo = todo[: args.limit]
    token = cfg.get_ads_token()

    label = data.get("star") or data.get("title") or args.slug
    print(f"{label}: {len(todo)} sin arXiv → resolver de ADS (esources)")
    got = skipped = 0
    missing = []
    for i, r in enumerate(todo, 1):
        bib = r["bibcode"]
        dest = destdir / f"{safe_name(bib)}.pdf"
        if dest.exists():
            skipped += 1
            continue
        cands = candidate_urls(esource_records(bib, token))
        print(f"  [{i}/{len(todo)}] {bib}: "
              + (", ".join(t for t, _ in cands) if cands else "sin fuentes PDF en el resolver"))
        ok = False
        for sub, url in cands:
            pdf = download_pdf(url, token)
            if pdf:
                dest.write_bytes(pdf)
                print(f"      ✓ {sub} → {dest.name} ({len(pdf)} bytes)")
                got += 1
                ok = True
                break
            print(f"      · {sub} no entregó PDF")
        if not ok:
            missing.append({"bibcode": bib, "title": r.get("title"), "doi": r.get("doi")})
        time.sleep(SLEEP_S)

    print(f"Bajados {got}, ya estaban {skipped}, sin conseguir {len(missing)}.")
    miss = cfg.ROOT / "build" / args.slug / "missing_pdf.json"
    if missing:
        miss.write_text(json.dumps(missing, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Residuo en {miss} — cascada manual del skill (tablas del CDN, HTML legacy) "
              "o pedir el PDF al usuario / marcar `pending`.")
    elif miss.exists():
        miss.unlink()      # el listado de fetch_arxiv quedó cubierto: no dejar un residuo viejo
    return 0


if __name__ == "__main__":
    sys.exit(main())
