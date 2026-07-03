"""Baja PDFs desde export.arxiv.org para los papers relevantes de una estrella.

Uso:
    python fetch_arxiv.py <slug> [--all] [--limit N]

Lee build/<slug>/ads.json y baja el PDF de cada paper relevante con arxiv_id a
pdfs/<slug>/<bibcode>.pdf. Respeta el rate limit de arXiv: 1 request / 3 s.
Papers sin arxiv_id (revistas viejas pre-arXiv) se listan como faltantes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import requests

import lib_config as cfg

ARXIV_PDF = "https://export.arxiv.org/pdf/{arxiv_id}"
SLEEP_S = 3.0  # arXiv: no más de 1 req / 3 s
MAX_ATTEMPTS = 12  # arXiv throttlea por bytes y corta la conexión en PDFs grandes
HEADERS = {"User-Agent": "Almagesto/0.1 (academic literature vault; https://github.com/nicklessagus/Almagesto)"}


def safe_name(bibcode: str) -> str:
    return bibcode.replace("/", "_")


def download_pdf(arxiv_id: str, dest) -> bool:
    """Baja el PDF con resume por HTTP Range.

    arXiv throttlea por ancho de banda y cierra la conexión a mitad de los PDFs
    grandes (IncompleteRead/ChunkedEncodingError). Acumulamos los bytes ya
    recibidos y reanudamos con `Range: bytes=N-` hasta completar; los 429 se
    esperan sin appendear (su cuerpo de error corrompería la cola del PDF).
    """
    url = ARXIV_PDF.format(arxiv_id=arxiv_id)
    buf = bytearray()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        headers = dict(HEADERS)
        if buf:
            headers["Range"] = f"bytes={len(buf)}-"
        try:
            with requests.get(url, headers=headers, timeout=180, stream=True) as r:
                if r.status_code == 429:
                    time.sleep(15)
                    continue
                if r.status_code not in (200, 206):
                    print(f"    ! {arxiv_id}: HTTP {r.status_code}")
                    time.sleep(8)
                    continue
                if r.status_code == 200 and buf:
                    buf.clear()  # 200 con Range pedido = el servidor ignoró el Range y manda el archivo ENTERO
                for chunk in r.iter_content(chunk_size=65536):
                    buf += chunk
            break  # cuerpo recibido completo sin cortes
        except requests.RequestException:
            time.sleep(4)  # conexión cortada → reanudar desde len(buf)
    else:
        print(f"    ! fallo {arxiv_id}: incompleto tras {MAX_ATTEMPTS} intentos ({len(buf)} bytes)")
        return False
    if bytes(buf[:4]) != b"%PDF":
        print(f"    ! {arxiv_id}: respuesta no es PDF (¿aún sin procesar en arXiv?)")
        return False
    dest.write_bytes(buf)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--all", action="store_true", help="incluir no-relevantes")
    ap.add_argument("--limit", type=int, default=0, help="máximo a bajar (0 = sin límite)")
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

    todo = [r for r in recs if r.get("arxiv_id")]
    no_arxiv = [r for r in recs if not r.get("arxiv_id")]
    if args.limit:
        todo = todo[: args.limit]

    label = data.get("star") or data.get("title") or args.slug
    print(f"{label}: {len(todo)} con arXiv a bajar, "
          f"{len(no_arxiv)} sin arXiv (pre-arXiv / no e-print)")
    got, skipped = 0, 0
    for i, r in enumerate(todo, 1):
        dest = destdir / f"{safe_name(r['bibcode'])}.pdf"
        if dest.exists():
            skipped += 1
            continue
        print(f"  [{i}/{len(todo)}] {r['arxiv_id']}  {r['bibcode']}")
        if download_pdf(r["arxiv_id"], dest):
            got += 1
        time.sleep(SLEEP_S)

    print(f"Bajados {got}, ya estaban {skipped}.")
    if no_arxiv:
        miss = cfg.ROOT / "build" / args.slug / "missing_pdf.json"
        miss.write_text(json.dumps(
            [{"bibcode": r["bibcode"], "title": r["title"], "doi": r.get("doi")}
             for r in no_arxiv], indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Papers sin arXiv listados en {miss} (bajar manual vía DOI si hacen falta).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
