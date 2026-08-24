"""Baja PDFs de papers SIN arXiv vía el resolver de ADS (esources) — completa a fetch_arxiv.

Uso:
    python scripts/fetch_pdf.py <slug> [--all] [--limit N]

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

Lo que ni así se consigue queda en build/<slug>/missing_pdf.json (superset del formato de
fetch_arxiv; al correr último en la cadena, es el residuo COMPLETO del ingest por verdad
de disco). Cada entrada lleva `bibstem`/`year` y un `hint` con la rama de la cascada MANUAL
por donde seguir (#50: "bajar por DOI" no alcanza — Messenger, página del instrumento,
mirror académico, o derivar al usuario si es un A&A pre-arXiv); el detalle de cada rama vive
en `## Notas` del skill ingest-star.
Idempotente: no re-baja lo que ya está en vault/raw/pdfs/<slug>/.

Deja además en build/<slug>/pdf_source.json qué rama entregó cada PDF (`eprint` | `ads` |
`publisher`), que make_notes estampa como `pdf_source` en la nota (#57): distinguir el preprint
de la versión publicada cambia cómo se lee una discrepancia numérica al verificar citas.
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
PDF_SOURCE = {"EPRINT_PDF": "eprint", "ADS_PDF": "ads", "PUB_PDF": "publisher"}

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


def safe_name(bibcode: str) -> str:
    return bibcode.replace("/", "_")


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



def _flags_usados(args) -> list:
    """Los flags no-default de esta corrida, para dejarlos en `cadena:` del registro (D-48/D-57).
    Son las **escotillas**: `--force`, `--yes`, `--all` cambian lo que la corrida hizo, y sin
    registrarlas la traza dice "corrió make_notes" sobre dos corridas que no hicieron lo mismo."""
    return sorted(f"--{k.replace('_', '-')}" for k, v in vars(args).items()
                  if v is True and k not in ("topic",))

def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser()
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
    reusados = 0
    for r in list(pendientes):
        stem = safe_name(r["bibcode"])
        otro = cfg.artefacto_en_otro_slug(cfg.PDFS, args.slug, stem, ".pdf")
        if otro is not None:
            cfg.write_bytes_atomic(destdir / f"{stem}.pdf", otro.read_bytes())
            cfg.print_seguro(f"  ↺ {r['bibcode']}: ya estaba bajo `{otro.parent.name}` — copiado "
                             "sin ir a la red (D-18)")
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
        if not ok:
            hint = rescue_hint(r.get("bibstem"), r.get("year"))
            missing.append({"bibcode": bib, "title": r.get("title"), "doi": r.get("doi"),
                            "bibstem": r.get("bibstem"), "year": r.get("year"), "hint": hint})
            cfg.print_seguro(f"      → rescate manual [{r.get('bibstem') or 'sin bibstem'}]: {hint}")
        time.sleep(SLEEP_S)

    cfg.print_seguro(f"Bajados {got}, ya estaban {skipped}, sin conseguir {len(missing)}.")
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
    cfg.save_paso(args.slug, "fetch_pdf", flags=_flags_usados(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
