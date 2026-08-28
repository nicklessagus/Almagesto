"""Baja PDFs desde export.arxiv.org para los papers relevantes de una estrella.

Uso:
    python scripts/fetch_arxiv.py <slug> [--all] [--limit N]

Lee build/<slug>/ads.json y baja el PDF de cada paper relevante con arxiv_id a
pdfs/<slug>/<bibcode>.pdf. Respeta el rate limit de arXiv: 1 request / 3 s.
Al residuo build/<slug>/missing_pdf.json van los papers sin arxiv_id (revistas viejas
pre-arXiv) Y las bajadas que fallaron (#32: antes un fallo sólo quedaba en el stdout —
invisible para la cascada manual); fetch_pdf, el siguiente paso de la cadena, intenta
todo lo que siga sin PDF en disco vía el resolver de ADS.

Deja además en build/<slug>/pdf_source.json de qué rama salió cada PDF (acá siempre `eprint`:
arXiv sirve el EPRINT, que puede ser un v1 pre-referato distinto del publicado que cita el
bibcode). Lo consume make_notes para estampar `pdf_source` (#57).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import requests

import fetch_pdf
import lib_config as cfg

ARXIV_PDF = "https://export.arxiv.org/pdf/{arxiv_id}"
SLEEP_S = 3.0  # arXiv: no más de 1 req / 3 s
MAX_ATTEMPTS = 12  # arXiv throttlea por bytes y corta la conexión en PDFs grandes
HEADERS = {"User-Agent": f"Almagesto/{cfg.ALMAGESTO_VERSION} (academic literature vault; "
                         "https://github.com/nicklessagus/Almagesto)"}


def safe_name(bibcode: str) -> str:
    return bibcode.replace("/", "_")


def write_pdf_atomic(dest, data: bytes) -> bool:
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
        cfg.print_seguro(f"    ! no se pudo escribir {dest.name} en disco: {e}")
        return False


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
                    cfg.print_seguro(f"    ! {arxiv_id}: HTTP {r.status_code}")
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
        cfg.print_seguro(f"    ! fallo {arxiv_id}: incompleto tras {MAX_ATTEMPTS} intentos ({len(buf)} bytes)")
        return False
    if bytes(buf[:4]) != b"%PDF":
        cfg.print_seguro(f"    ! {arxiv_id}: respuesta no es PDF (¿aún sin procesar en arXiv?)")
        return False
    return write_pdf_atomic(dest, bytes(buf))



def _flags_usados(args, ap=None) -> list:
    """Los flags no-default de esta corrida, para dejarlos en `cadena:` del registro (D-48/D-57).
    Son las **escotillas**: `--force`, `--yes`, `--all` cambian lo que la corrida hizo, y sin
    registrarlas la traza dice "corrió make_notes" sobre dos corridas que no hicieron lo mismo."""
    return cfg.flags_usados(args, ap)

def drop_filter(recs: list, slug: str) -> tuple[list, list]:
    """Same guard as `fetch_pdf.drop_filter`, and it delegates so the two cannot drift (AUD-137).

    The audit's second most expensive pattern is «the fix was applied to one site and not to its
    twin»; these two fetchers are literally twins."""
    return fetch_pdf.drop_filter(recs, slug)


def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--all", action="store_true", help="incluir no-relevantes")
    ap.add_argument("--limit", type=int, default=0, help="máximo a bajar (0 = sin límite)")
    ap.add_argument("--force", action="store_true",
                    help="re-bajar incluso lo que ya tiene PDF en disco (p. ej. un PDF truncado "
                         "por un corte anterior — H-07: nada valida el contenido de lo ya "
                         "bajado, ésta es la vía de escape manual)")
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

    todo = [r for r in recs if r.get("arxiv_id")]
    no_arxiv = [r for r in recs if not r.get("arxiv_id")]
    if args.limit:
        todo = todo[: args.limit]

    label = data.get("star") or data.get("title") or args.slug
    cfg.print_seguro(f"{label}: {len(todo)} con arXiv a bajar, "
                      f"{len(no_arxiv)} sin arXiv (pre-arXiv / no e-print)")
    got, skipped, failed = 0, 0, []
    for i, r in enumerate(todo, 1):
        stem = safe_name(r["bibcode"])
        dest = destdir / f"{stem}.pdf"
        if dest.exists() and not args.force:
            skipped += 1
            continue
        # D-18: el mismo bibcode ya bajado bajo otro slug es el MISMO archivo — copiarlo evita una
        # bajada idéntica (33 copias medidas en la instancia) y un modo de falla (la red).
        if not args.force and (otro := cfg.artefacto_en_otro_slug(cfg.PDFS, args.slug, stem, ".pdf")):
            cfg.write_bytes_atomic(dest, otro.read_bytes())
            cfg.print_seguro(f"  ↺ {r['bibcode']}: ya estaba bajo `{otro.parent.name}` — copiado "
                             "sin ir a la red (D-18)")
            got += 1
            continue
        cfg.print_seguro(f"  [{i}/{len(todo)}] {r['arxiv_id']}  {r['bibcode']}")
        if download_pdf(r["arxiv_id"], dest):
            got += 1
            # de dónde salió este PDF (#57): arXiv sirve el EPRINT, que puede ser un v1
            # pre-referato — distinto de la versión publicada que cita el bibcode.
            cfg.record_pdf_source(args.slug, safe_name(r["bibcode"]), "eprint")
        else:
            failed.append(r)
        time.sleep(SLEEP_S)

    cfg.print_seguro(f"Bajados {got}, ya estaban {skipped}"
                      + (f", fallaron {len(failed)}" if failed else "") + ".")
    # residuo = sin arXiv + bajadas fallidas (#32): la contabilidad de "qué falta" debe cubrir
    # también los fallos, que antes morían en el stdout. En la cadena, fetch_pdf (siguiente paso)
    # intenta todo lo que siga sin PDF en disco y reescribe este archivo con el residuo final.
    residue = no_arxiv + failed
    if residue:
        miss = cfg.ROOT / "build" / args.slug / "missing_pdf.json"
        cfg.write_text_atomic(miss, json.dumps(
            [{"bibcode": r["bibcode"], "title": r["title"], "doi": r.get("doi")}
             for r in residue], indent=2, ensure_ascii=False))
        cfg.print_seguro(f"Sin PDF ({len(no_arxiv)} sin arXiv + {len(failed)} fallidos) → {miss} "
                          "(fetch_pdf los intenta vía el resolver de ADS; el residuo final es el suyo).")
    cfg.save_paso(args.slug, "fetch_arxiv", flags=_flags_usados(args, ap))
    return 0


if __name__ == "__main__":
    cfg.cli_exit(main)
