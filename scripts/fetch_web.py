"""Snapshot determinista de una página web → fulltext citable (modo off-ADS de ingest-topic).

Uso:
    python fetch_web.py <slug> <citekey> <url> [--force]

Baja la URL con **defuddle** (extractor de contenido de Obsidian: quita nav/menús/clutter y
devuelve markdown limpio) y escribe un snapshot determinista en
`fulltext/<slug>/<citekey>.txt`, con un encabezado **URL + fecha de acceso** para que la
afirmación sea **citable y verificable** por `verify-citations`. Es la contraparte web de
`extract_fulltext.py` (que hace PDF→txt): mismo destino, misma idea de fuente inmutable.

Sólo aplica al **modo off-ADS** de `ingest-topic` (tema no-astro / bibliografía fuera de ADS);
el flujo astro normal baja PDFs por arXiv. Ver `.claude/skills/ingest-topic/SKILL.md`.

`citekey` = clave de cita sintética `AAAA+Autor` (p. ej. `2000HyvarinenOja`); debe empezar con
`AAAA`+letra (mismo `BIBCODE_RE` que el lint) y coincidir con el `[[citekey]]` que cites en la nota.

Requiere Node/npm (usa `npx defuddle`). defuddle es JS-only; se invoca por subproceso, no hay
binding Python. Idempotente: no re-baja salvo --force. defuddle baja la URL él mismo.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import lib_config as cfg

# Misma heurística de clave que scripts/lint.py (BIBCODE_RE): 4 dígitos + letra. Garantiza que el
# .txt se llame como el [[citekey]] citado y que el lint lo reconozca como target de bibcode.
CITEKEY_RE = re.compile(r"^\d{4}[A-Za-z]")


def defuddle_version() -> str:
    """Versión del paquete defuddle (para provenance en el header); 'desconocida' si no se puede."""
    try:
        r = subprocess.run(["npx", "--yes", "defuddle", "--version"],
                           capture_output=True, text=True, timeout=60)
        return r.stdout.strip() or "desconocida"
    except Exception:
        return "desconocida"


def fetch(url: str) -> str:
    """Corre `npx defuddle parse <url> --markdown` y devuelve el markdown. '' si falla."""
    r = subprocess.run(["npx", "--yes", "defuddle", "parse", url, "--markdown"],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print(f"    ! defuddle falló ({r.returncode}): {r.stderr.strip()[:200]}")
        return ""
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="tema (subcarpeta de raw/fulltext)")
    ap.add_argument("citekey", help="clave de cita sintética AAAA+Autor (p. ej. 2000HyvarinenOja)")
    ap.add_argument("url", help="URL a snapshotear")
    ap.add_argument("--force", action="store_true", help="re-baja aunque el .txt ya exista")
    args = ap.parse_args()

    if shutil.which("npx") is None:
        sys.exit(
            "Falta `npx` (Node.js), necesario para correr defuddle (extractor web):\n"
            "  https://nodejs.org  ·  o vía nvm: https://github.com/nvm-sh/nvm\n"
            "Alternativa sin Node: traer la página con WebFetch y guardar el snapshot a mano."
        )
    if not CITEKEY_RE.match(args.citekey):
        sys.exit(
            f"citekey inválida: {args.citekey!r}. Debe empezar con AAAA+letra (año+inicial del autor, "
            "p. ej. 2000HyvarinenOja) para que el lint la reconozca y el .txt matchee el [[citekey]]."
        )

    outdir = cfg.FULLTEXT / args.slug
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{args.citekey}.txt"
    if out.exists() and not args.force:
        print(f"{args.citekey}: ya existe {out} (usá --force para re-bajar)")
        return 0

    print(f"  defuddle ← {args.url}")
    body = fetch(args.url)
    if not body.strip():
        print("  ! snapshot vacío — no se escribe nada")
        return 1

    # Encabezado citable: URL + fecha de acceso (UTC) + provenance del extractor. El cuerpo (defuddle)
    # es determinista; la fecha es el metadato del snapshot (cuándo se capturó), como pide el modo off-ADS.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = (
        "# Almagesto — snapshot web (off-ADS), determinista para citar/verificar\n"
        f"source_url : {args.url}\n"
        f"retrieved  : {stamp} (UTC)\n"
        f"extractor  : defuddle {defuddle_version()} (npx defuddle parse --markdown)\n"
        f"citekey    : {args.citekey}\n"
        "# ---- contenido extraído (defuddle) ----\n\n"
    )
    out.write_text(header + body, encoding="utf-8")
    print(f"{args.citekey}: {len(body)} bytes → {out}")
    print("  siguiente: crear vault/wiki/papers/<citekey>.md a mano (make_notes asume ADS); ver SKILL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
