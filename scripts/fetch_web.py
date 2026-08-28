"""Snapshot determinista de una página web → fulltext citable (modo off-ADS de ingest-theme).

Uso:
    python scripts/fetch_web.py <slug> <citekey> <url> [--concept C] [--title T] [--author A]
                        [--year Y] [--n-authors N] [--doi D] [--venue V] [--no-note]
                        [--force] [--force-note]

Baja la URL con **defuddle** (extractor de contenido de Obsidian: quita nav/menús/clutter y
devuelve markdown limpio), le pasa un **post-clean** determinista (saca bloques HTML de media/embed
que defuddle deja sueltos) y escribe un snapshot en `fulltext/<slug>/<citekey>.txt`, con un
encabezado **URL + fecha de acceso** para que la afirmación sea **citable y verificable** por
`verify-citations`. Además crea el **stub de nota de paper** `wiki/papers/<citekey>.md` (salvo
`--no-note`), delegando en `make_notes.write_web_paper_note` (mismo template que las notas ADS).

⛔ **`--force` re-baja la FUENTE, no pisa la NOTA.** Hasta 1.36.0 propagaba el flag hasta
`write_web_paper_note` y `ingest_theme <slug> --force` **destruía la extracción LLM** de cada fuente
web del tema (medido: `methods` y `role` a `[]`, prosa perdida) — mientras los dos docstrings
prometían que «la extracción LLM se protege siempre». Para regenerar la nota a propósito está
`--force-note`, que lo dice en el nombre.

Es la contraparte web de `extract_fulltext.py` (PDF→txt): mismo destino, misma idea de fuente
inmutable. Sólo aplica al **modo off-ADS** de `ingest-theme` (tema no-astro / bibliografía fuera de
ADS); el flujo astro normal baja PDFs por arXiv. Ver `.claude/skills/ingest-theme/SKILL.md`.

`citekey` = clave de cita sintética `AAAA+Autor` (p. ej. `2006RasmussenWilliams`); debe empezar con
`AAAA`+letra (mismo `BIBCODE_RE` que el lint) y coincidir con el `[[citekey]]` que cites en la nota.

Requiere Node/npm (usa `npx defuddle`, JS-only; se invoca por subproceso). Idempotente: no re-baja
salvo --force. defuddle baja la URL él mismo.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import lib_blocks as lb
import lib_config as cfg
import make_notes

# Misma heurística de clave que scripts/lint.py (BIBCODE_RE): 4 dígitos + letra. Garantiza que el
# .txt se llame como el [[citekey]] citado y que el lint lo reconozca como target de bibcode.
# @inv INV-27
CITEKEY_RE = re.compile(r"^\d{4}[A-Za-z]")

# Bloques HTML crudos que defuddle a veces deja embebidos y que NO aportan texto citable
# (media/embeds): se quitan para dejar el snapshot limpio y greppable. CONSERVADOR — sólo elementos
# sin prosa; nada que pueda contener texto del artículo (no se tocan figure/table/p/etc.).
_NOISE_BLOCKS = ("video", "audio", "picture", "iframe", "svg")


def clean_markdown(md: str) -> tuple[str, int]:
    """Post-clean determinista: saca bloques de media/embed que defuddle dejó como HTML crudo y
    colapsa líneas en blanco de más. Determinista (regex puro sobre entrada determinista) → el
    snapshot sigue siendo reproducible. Devuelve (markdown_limpio, n_bloques_removidos)."""
    # @inv INV-30
    removed = 0
    for tag in _NOISE_BLOCKS:
        md, n = re.subn(rf"<{tag}\b[^>]*>.*?</{tag}>", "", md, flags=re.DOTALL | re.IGNORECASE)
        removed += n
    # tags void (source/track) que hayan quedado fuera de un bloque ya removido
    md, n = re.subn(r"<(?:source|track)\b[^>]*/?>", "", md, flags=re.IGNORECASE)
    removed += n
    md = re.sub(r"\n{3,}", "\n\n", md)   # colapsar 3+ saltos a 2
    return md.strip() + "\n", removed


def defuddle_version() -> str:
    """Versión del paquete defuddle (para provenance en el header); 'desconocida' si no se puede."""
    try:
        r = subprocess.run(["npx", "--yes", "defuddle", "--version"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60)
        return r.stdout.strip() or "desconocida"
    except Exception:
        return "desconocida"


def fetch(url: str) -> str:
    """Corre `npx defuddle parse <url> --markdown` y devuelve el markdown.

    `''` cuando defuddle sale con código ≠ 0 (el caso normal de una URL que no rinde). **Propaga**
    `subprocess.TimeoutExpired` a los 180 s y `FileNotFoundError` si falta `npx`: son fallos del
    ENTORNO, no de la página, y devolverlos como `''` los haría indistinguibles de "la página no
    tenía contenido" — que es lo que `main()` reporta como snapshot vacío y `sweep_web` contaría
    como *no cambió*. El llamador los cuenta como **no evaluado** (`sweep_web` los registra en
    `fallidos`)."""
    # encoding explícito: sin él, Windows decodifica con la locale (cp1252) y el markdown
    # UTF-8 de defuddle sale mojibake — el snapshot debe ser idéntico en cualquier OS.
    r = subprocess.run(["npx", "--yes", "defuddle", "parse", url, "--markdown"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=180)
    if r.returncode != 0:
        cfg.print_seguro(f"    ! defuddle falló ({r.returncode}): {r.stderr.strip()[:200]}")
        return ""
    return r.stdout


def snapshot_body(texto: str) -> str:
    """El CUERPO del snapshot, sin el header. El header lleva `retrieved` (una fecha que cambia en
    cada corrida) y la versión del extractor: hashear el archivo entero haría que **toda** re-bajada
    se viera como "la página cambió". Lo que se compara es el contenido extraído."""
    marca = "# ---- contenido extraído (defuddle) ----"
    i = texto.find(marca)
    return texto[i + len(marca):].strip() if i >= 0 else texto.strip()


def refresh(slug: str, citekey: str) -> tuple[str, str] | None:
    """Re-baja la URL de un snapshot y devuelve `(hash_viejo, hash_nuevo)` **si el cuerpo cambió**;
    `None` si es igual. **No escribe nada** (D-45: reporta, no aplica solo).

    Es el insumo del quinto detector de la pasada de red (D-41). Una fuente web no tiene ni DOI ni
    bibcode: nada avisa que cambió, y las citas verificadas contra ella quedan apuntando a un texto
    que ya no dice eso — con la diferencia de que acá **el archivo local no se toca**, así que el
    ancla de fuente (D-20) tampoco se entera. Es el modo de caducidad más silencioso de los cinco.

    Levanta `RuntimeError` si el snapshot no declara `source_url` (no se puede re-bajar lo que no se
    sabe de dónde salió) — el llamador lo cuenta como **no evaluado**, nunca como "no cambió"."""
    out = cfg.FULLTEXT / slug / f"{citekey}.txt"
    texto = out.read_text(encoding="utf-8", errors="replace")
    url = cfg.snapshot_url(out)
    if not url:
        raise RuntimeError(f"{slug}/{citekey}.txt no declara `source_url` — no se puede re-bajar")
    raw = fetch(url)
    if not raw.strip():
        raise RuntimeError(f"{url} devolvió vacío")
    body, _ = clean_markdown(raw)
    viejo, nuevo = lb.sha10(snapshot_body(texto)), lb.sha10(body.strip())
    return None if viejo == nuevo else (viejo, nuevo)


def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="tema (subcarpeta de raw/fulltext)")
    ap.add_argument("citekey", help="clave de cita sintética AAAA+Autor (p. ej. 2006RasmussenWilliams)")
    ap.add_argument("url", help="URL a snapshotear")
    ap.add_argument("--concept", help="concept destino de la nota de paper (thesis_links)")
    ap.add_argument("--title", help="título de la fuente (para la nota de paper)")
    ap.add_argument("--author", help="primer autor (para la nota de paper)")
    ap.add_argument("--year", help="año (para la nota de paper)")
    ap.add_argument("--n-authors", dest="n_authors", help="cantidad de autores (para la nota de paper)")
    ap.add_argument("--doi", help="DOI de la fuente, si existe (para la nota; habilita check_retractions)")
    ap.add_argument("--venue", help="venue/bibstem de la nota (default: dominio de la URL)")
    ap.add_argument("--no-note", action="store_true", help="sólo el snapshot; no crear wiki/papers/<citekey>.md")
    ap.add_argument("--force", action="store_true",
                    help="re-baja el SNAPSHOT aunque ya exista (no toca la nota de wiki)")
    ap.add_argument("--force-note", action="store_true",
                    help="además, REGENERA la nota de paper: PISA la extracción LLM")
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
            "p. ej. 2006RasmussenWilliams) para que el lint la reconozca y el .txt matchee el [[citekey]]."
        )

    outdir = cfg.FULLTEXT / args.slug
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{args.citekey}.txt"
    # fecha del snapshot (UTC): la comparte el .txt y la nota. Si el .txt ya existe, se reusa la suya.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # AUD-170 — COLISIÓN de citekey: el `.txt` que ya está en disco es el snapshot de OTRA url.
    # Sin esto, la nota se escribía con la metadata de la url nueva y el `.txt` seguía siendo el de
    # la vieja: la cita apunta a una página y el archivo que `verify-citations` lee es otro. La
    # citekey es sintética (`AAAA+Autor`) y la colisión es normal —dos trabajos del mismo autor y
    # año—, así que no es hipotética.
    if out.exists() and (previa := cfg.snapshot_url(out)) and previa != args.url:
        sys.exit(f"⛔ colisión de citekey: `{out}` ya es el snapshot de\n"
                 f"     {previa}\n   y estás pidiendo\n     {args.url}\n"
                 f"   Son dos fuentes distintas con la misma clave. Elegí otra citekey (la "
                 f"convención admite un sufijo: `{args.citekey}b`), o borrá el snapshot viejo si "
                 f"de verdad querés reemplazarlo.")
    if out.exists() and not args.force:
        # la nota coincide con el .txt: si el snapshot es viejo, vale su fecha original, no hoy
        # (parser en lib_config — un solo lugar de verdad del header; lo comparte make_notes)
        stamp = cfg.snapshot_retrieved(out) or stamp
        cfg.print_seguro(f"{args.citekey}: ya existe {out} (usá --force para re-bajar)")
    else:
        cfg.print_seguro(f"  defuddle ← {args.url}")
        raw = fetch(args.url)
        if not raw.strip():
            cfg.print_seguro("  ! snapshot vacío — no se escribe nada")
            return 1
        body, removed = clean_markdown(raw)
        # Encabezado citable: URL + fecha de acceso (UTC) + provenance del extractor. El cuerpo es
        # determinista; la fecha es el metadato del snapshot (cuándo se capturó), como pide off-ADS.
        header = (
            f"{cfg.FULLTEXT_WEB_MARK} (off-ADS), determinista para citar/verificar\n"
            f"source_url : {args.url}\n"
            f"retrieved  : {stamp} (UTC)\n"
            f"extractor  : defuddle {defuddle_version()} + post-clean off-ADS (npx defuddle parse --markdown)\n"
            f"citekey    : {args.citekey}\n"
            "# ---- contenido extraído (defuddle) ----\n\n"
        )
        cfg.write_text_atomic(out, header + body)
        cfg.print_seguro(f"{args.citekey}: {len(body)} bytes → {out}  (post-clean: {removed} bloques HTML removidos)")

    # Stub de la nota de paper (mismo template que las notas ADS; idempotente). Delega en make_notes.
    if not args.no_note:
        make_notes.write_web_paper_note(
            args.citekey, url=args.url, slug=args.slug, concept=args.concept,
            title=args.title, first_author=args.author, year=args.year,
            n_authors=args.n_authors, doi=args.doi,
            venue=args.venue, accessed=stamp, force=args.force_note,
        )
        # AUD-170 — con `--force` el snapshot es NUEVO y la nota conserva el `accessed` viejo (sólo
        # se reescribe con `--force-note`): la nota publicaría un "Retrieved <fecha>" que no es el
        # del `.txt` de al lado, que es el archivo que `verify-citations` lee. Cirugía sobre la
        # línea, no re-escritura: la extracción LLM no se toca.
        if args.force and make_notes.stamp_accessed(cfg.PAPERS / f"{args.citekey}.md", stamp):
            cfg.print_seguro(f"  · `accessed` de la nota re-estampado a {stamp} (snapshot nuevo)")
        cfg.print_seguro("  siguiente: completar la extracción LLM en la nota y verificar con verify-citations")
    return 0


if __name__ == "__main__":
    cfg.cli_exit(main)
