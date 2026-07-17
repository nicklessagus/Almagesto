"""Orquestador de la cadena mecánica de ingest-topic: despacha según `source` del tema.

Uso:
    python ingest_topic.py <slug> [--force]

Lee la entrada del tema en vault/config/topics.yaml y corre la cadena que corresponda a su
campo `source` (formaliza el modo off-ADS del skill ingest-topic en el tooling):

- `ads` (default si el campo falta): cadena astro estándar —
  query_ads --topic → fetch_arxiv → make_notes --topic → extract_fulltext → check_retractions.
- `web` | `local-pdfs` | `local-pdfs+web`: modo off-ADS. La bibliografía se declara en la
  lista `sources:` de la entrada (cada item: `key` = clave de cita sintética AAAA+Autor +
  `url` (fuente web) o `pdf` (ruta a un PDF provisto por el usuario) + metadata opcional
  `title/author/year/venue/n_authors/doi`). El orquestador stubbea el concept, procesa cada
  fuente (`fetch_web.py` para URLs; copia a raw/pdfs/<slug>/<key>.pdf para PDFs) y corre
  extract_fulltext. Sin query_ads / fetch_ground_truth (no aplican fuera de ADS);
  check_retractions SÍ corre cuando algún item declara `doi` (Crossref lo cubre igual).

Fallback fuentes no-conseguibles: un item puede llevar `pending: paywall|scan|unextractable`
en vez de una fuente obtenible — declara que la fuente todavía NO se pudo conseguir (sin copia
libre / escaneo / mojibake) y queda DERIVADA al usuario. El orquestador NO la fetchea ni la
cuenta como fallo: crea el stub de nota con `pending_source` (con `url`/`doi` como puntero) y
lista las pendientes en un aviso al final; el lint las surfacea como precondición. Cuando el
usuario provee la fuente: reemplazar `pending` por `pdf:`/`url:` y re-correr (idempotente).

Idempotente como la cadena que envuelve: nada se re-baja ni se copia si ya existe. `--force`
fuerza SÓLO la re-bajada/copia de FUENTES (snapshot web, PDF, fulltext) — **nunca pisa notas
de wiki** (la extracción LLM se protege siempre; para regenerar una nota: make_notes --force
a mano). La extracción LLM posterior (leer fulltext, poblar notas, sintetizar el concept,
retro-tag) NO es de este script: la hace el agente siguiendo el skill ingest-topic.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import lib_config as cfg
import make_notes
from fetch_web import CITEKEY_RE

# valores válidos de `source` (ausente = "ads"); los combinados permiten mezclar url/pdf en sources
OFFADS_KINDS = {"web": ("url",), "local-pdfs": ("pdf",),
                "local-pdfs+web": ("url", "pdf"), "web+local-pdfs": ("url", "pdf")}


def run(script: str, *args: str) -> int:
    """Corre un script de la cadena con el mismo intérprete (rutas absolutas vía lib_config)."""
    print(f"\n→ {script} {' '.join(args)}")
    return subprocess.run([sys.executable, str(cfg.ROOT / "scripts" / script), *args],
                          cwd=cfg.ROOT / "scripts").returncode


def ingest_ads(slug: str) -> None:
    """Cadena astro estándar (paso 2 del skill ingest-topic), abortando al primer fallo."""
    for script, args in (("query_ads.py", ["--topic", slug]),
                         ("fetch_arxiv.py", [slug]),
                         ("make_notes.py", ["--topic", slug]),
                         ("extract_fulltext.py", [slug]),
                         ("check_retractions.py", [])):
        rc = run(script, *args)
        if rc:
            sys.exit(f"{script} falló (rc={rc}) — cadena abortada. La cadena es idempotente: "
                     "corregí y re-corré ingest_topic.py (lo ya bajado no se re-baja).")


def ingest_offads(slug: str, meta: dict, force: bool) -> None:
    """Modo off-ADS: concept stub + una fuente por item de `sources:` (web o PDF local)."""
    for k in ("area", "concept"):
        if not meta.get(k):
            sys.exit(f"la entrada '{slug}' no tiene `{k}` en topics.yaml (requerido para el concept).")
    sources = meta.get("sources") or []
    if not sources:
        sys.exit(f"'{slug}' es off-ADS (source: {meta.get('source')}) pero no declara `sources:` en "
                 "topics.yaml — listá ahí su bibliografía (items con key + url|pdf; ver header del YAML).")
    allowed = OFFADS_KINDS[meta["source"]]
    concept = meta["concept"]

    make_notes.write_concept_note(slug, force=False)   # nunca --force acá: protege la síntesis LLM

    fails = n_pdf = 0
    pending_items: list[tuple[str, str, str]] = []   # (key, motivo, puntero) → aviso final
    failed_items: list[tuple[str, str]] = []         # (key, puntero) → aviso final
    for s in sources:
        key = s.get("key") or ""
        if not CITEKEY_RE.match(key):
            sys.exit(f"key inválida en sources de '{slug}': {key!r}. Debe empezar con AAAA+letra "
                     "(clave de cita sintética, p. ej. 2000HyvarinenOja).")
        if s.get("pending"):
            # Fuente no-conseguible declarada: NO se fetchea ni cuenta como fallo — stub con
            # pending_source (url/doi quedan como puntero) y derivación al usuario en el aviso final.
            make_notes.write_web_paper_note(key, url=s.get("url"), slug=slug, concept=concept,
                                            title=s.get("title"), first_author=s.get("author"),
                                            year=s.get("year"), n_authors=s.get("n_authors"),
                                            doi=s.get("doi"), venue=s.get("venue"),
                                            pending=str(s["pending"]))
            pending_items.append((key, str(s["pending"]),
                                  s.get("doi") or s.get("url") or "(sin puntero conocido)"))
            continue
        if s.get("url") and s.get("pdf"):
            sys.exit(f"{key}: item de sources con `url` Y `pdf` a la vez — ambiguo. Partilo en dos "
                     "items (una clave por fuente/snapshot).")
        kind = "url" if s.get("url") else "pdf" if s.get("pdf") else None
        if kind is None:
            sys.exit(f"{key}: item de sources sin `url` ni `pdf` — no hay de dónde traer la fuente.")
        if kind not in allowed:
            sys.exit(f"{key}: tiene `{kind}` pero la entrada declara source: {meta['source']} "
                     f"(admite {'/'.join(allowed)}). ¿Typo? Para mezclar usá source: local-pdfs+web.")
        if kind == "url":
            args = [slug, key, s["url"], "--concept", concept]
            for flag in ("title", "author", "year", "venue", "n_authors", "doi"):
                if s.get(flag):
                    args += [f"--{flag.replace('_', '-')}", str(s[flag])]
            if force:
                args.append("--force")
            if run("fetch_web.py", *args):
                fails += 1
                failed_items.append((key, s["url"]))
        else:
            dest = cfg.PDFS / slug / f"{make_notes.safe_name(key)}.pdf"
            src = Path(s["pdf"]).expanduser()
            if dest.exists() and not force:
                print(f"{key}: ya existe {dest} (usá --force para re-copiar)")
            elif not src.exists():
                if dest.exists():
                    # --force en una máquina sin la fuente externa (post-clone): la copia versionada
                    # en la bóveda es la que vale — conservarla no es un fallo.
                    print(f"  ⚠ {key}: no existe el PDF fuente {src}; conservo la copia de la bóveda ({dest})")
                else:
                    print(f"  ! {key}: no existe el PDF fuente {src} — item salteado")
                    fails += 1
                    failed_items.append((key, str(src)))
                    continue
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                print(f"{key}: {src.name} → {dest}")
            n_pdf += 1     # sólo cuenta PDFs presentes en disco (un item fallido no dispara extract)
            # stub de nota (idempotente; detecta solo el PDF copiado y linkea el campo `pdf`)
            make_notes.write_web_paper_note(key, slug=slug, concept=concept,
                                            title=s.get("title"), first_author=s.get("author"),
                                            year=s.get("year"), n_authors=s.get("n_authors"),
                                            doi=s.get("doi"), venue=s.get("venue"))
    extract_rc = 0
    if n_pdf:
        # el rc de extract se reporta aparte: un fallo de extracción NO es una "fuente fallida"
        # (contarlo ahí inflaba el conteo del aviso final)
        extract_rc = run("extract_fulltext.py", slug, *(["--force"] if force else []))
    # Aviso claro al operador (issue #7): qué fuentes faltan y con qué puntero, para que el
    # usuario las provea. Las pendientes NO son fallos (la cadena degrada limpio y sigue).
    if pending_items:
        print("\n⏳ Fuentes PENDIENTES (derivadas al usuario — no frenan la cadena):")
        for key, why, ptr in pending_items:
            print(f"  - {key} [{why}] → {ptr}")
        print("  Cuando esté la fuente: reemplazá `pending` por `pdf:`/`url:` en sources: y re-corré.")
    if failed_items:
        print("\n! Fuentes que FALLARON (¿transitorio? → re-corré; si la fuente no se puede "
              "conseguir, marcá el item con `pending: paywall|scan|unextractable` para derivarla "
              "al usuario sin frenar la cadena):")
        for key, ptr in failed_items:
            print(f"  - {key} → {ptr}")
    if fails:
        sys.exit(f"{fails} fuente(s) fallaron — revisá arriba y re-corré (idempotente).")
    if extract_rc:
        sys.exit(f"extract_fulltext.py falló (rc={extract_rc}) — corregí y re-corré "
                 "(idempotente: los PDFs ya copiados no se re-copian).")
    # off-ADS no tiene bibcode ADS, pero un DOI declarado en sources alcanza para el chequeo de
    # retracciones (Crossref) — una fuente retractada silenciosa rompe la frontera dura igual.
    if any(s.get("doi") for s in sources):
        if run("check_retractions.py"):
            sys.exit("check_retractions detectó papers retractados — revisá las notas marcadas "
                     "(el lint las surface como bloqueante).")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="tema de vault/config/topics.yaml")
    ap.add_argument("--force", action="store_true",
                    help="re-bajar/re-copiar FUENTES ya presentes (snapshot/PDF/fulltext); nunca pisa notas")
    args = ap.parse_args()

    try:
        _, meta = cfg.topic_by_slug(args.slug)
    except KeyError as e:
        sys.exit(str(e))
    source = meta.get("source") or "ads"
    if source == "ads":
        if meta.get("sources"):
            print("  ⚠ la entrada tiene `sources:` pero source: ads — la lista se ignora en modo ADS.")
        if args.force:
            print("  ⚠ --force no aplica al modo ads (corré el script puntual con --force si hace falta).")
        ingest_ads(args.slug)
    elif source in OFFADS_KINDS:
        ingest_offads(args.slug, {**meta, "source": source}, args.force)
    else:
        sys.exit(f"source desconocido en '{args.slug}': {source!r} "
                 f"(válidos: ads | {' | '.join(OFFADS_KINDS)}).")
    print("\nCadena mecánica lista. Siguiente (LLM, skill ingest-topic): extracción por paper → "
          "retro-tag (3b) → síntesis del concept → verify-citations → lint.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
