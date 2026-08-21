"""Chequea si algún paper de la bóveda fue RETRACTADO y lo marca en su nota.

Uso:
    python check_retractions.py            # todos los papers de vault/wiki/papers/ (pasada periódica)
    python check_retractions.py --slug <slug>       # sólo los papers de UN ingest (modo de la cadena)
    python check_retractions.py --paper <bibcode>   # uno solo
    python check_retractions.py --force    # re-chequear también los ya marcados

`--slug` es el modo que usan los orquestadores: chequea sólo los papers del ingest en curso
(bibcodes relevantes de build/<slug>/ads.json + `sources[].key`/`extra_core` de la entrada del
tema, si es un tema). El barrido completo (sin --slug) re-consulta Crossref por TODA la bóveda
—minutos, crece linealmente— y queda como pasada PERIÓDICA explícita (skill maintain): un paper
puede retractarse años después de ingestado.

Para una wiki cuyo contrato es "todo lo que afirma está respaldado por una fuente citable", una
fuente **retractada** silenciosa es el peor bug posible. Este script cierra ese agujero.

Señal (determinista, por DOI): el registro Crossref del propio paper trae `updated-by` con
`type: retraction | partial-retraction | removal | withdrawal` cuando fue retractado (ADS NO expone
un `property:retracted` — sólo, a veces, el prefijo "RETRACTED"/"Retraction:" en el título, que se
usa acá como *fallback* para papers sin DOI). Un `erratum`/`corrigendum`/`expression-of-concern` NO
retracta pero **cambia justamente el número que extrajiste** (o, la EoC, deja la fuente en duda):
se estampa `corrections: [{type, notice_doi, date, source}]` (#52). Antes sólo se imprimía a
stdout, donde un ingest de cientos de papers se lo come.

Efecto: estampa en el frontmatter de la nota `retracted: true` + `retraction: {...}` —y/o
`corrections: [...]`— (idempotente:
sólo reescribe notas cuyo estado cambió; edición quirúrgica del texto — no re-serializa el YAML,
preserva comentarios/orden de la extracción LLM). El flag **viaja en git**, así que un clon ve la retracción
sin re-consultar, y `lint.py` la surface offline como categoría bloqueante (las `corrections`, como backlog: el paper
sigue siendo citable, lo que hay que revisar son las afirmaciones que lo citan). Parte de RED (como los
`fetch_*`), separada del lint offline: correr periódicamente y al ingestar.

Exit code: 1 si se detectó al menos una retracción (gateable).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

import requests
import yaml

import lib_config as cfg

CROSSREF = "https://api.crossref.org/works/{doi}"
# tipos de `update-type` de Crossref que implican que el paper ya NO es citable como válido
RETRACTING = ("retraction", "partial-retraction", "removal", "withdrawal")
# correcciones (no retractan, pero conviene saberlo) → se estampan en `corrections`, NO en `retracted`
SOFT = ("erratum", "corrigendum", "expression-of-concern")


def _mailto() -> str | None:
    """Email para el 'polite pool' de Crossref (mejor servicio). Se toma de git config —NO se
    hardcodea en el template (es per-instancia)—; si no hay, se consulta sin mailto (pool público)."""
    try:
        r = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True, timeout=5)
        email = r.stdout.strip()
        return email or None
    except Exception:
        return None


def _ua() -> dict:
    m = _mailto()
    ua = (f"Almagesto/{cfg.ALMAGESTO_VERSION} (academic literature vault; "
          "https://github.com/nicklessagus/Almagesto")
    ua += f"; mailto:{m})" if m else ")"
    return {"User-Agent": ua}


def split_note(text: str) -> tuple[dict | None, str]:
    """(frontmatter dict, body) de una nota `---\\n<yaml>---\\n<body>`. maxsplit=2 preserva
    cualquier `---` (regla horizontal) del cuerpo. (None, text) si no hay frontmatter parseable."""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    try:
        return (yaml.safe_load(parts[1]) or {}), parts[2]
    except yaml.YAMLError:
        return None, text


def stamp_fields(path, fm: dict, body: str, fields: dict) -> None:
    """Estampa claves de frontmatter editando el TEXTO (como merge_frontmatter_list de make_notes):
    NO re-serializa el YAML completo → preserva byte a byte comentarios/orden que haya dejado la
    extracción LLM. Si la nota ya traía esas claves (re-chequeo con --force, o una corrección nueva
    sobre un paper ya anotado), las reemplaza —incluidos sus bloques indentados y los ítems `-` de
    una lista—. Fallback (nota sin estructura `---\\n…\\n---\\n`): re-serializa el frontmatter parseado."""
    text = path.read_text(encoding="utf-8")
    keys = tuple(f"{k}:" for k in fields)
    end = text.find("\n---\n", 4)
    if text.startswith("---\n") and end > 0:
        out, dropping = [], False
        # una clave top-level nunca arranca con espacio/tab/`-`: mientras `dropping`, esas líneas
        # son el bloque (mapa indentado o lista) de la clave vieja que estamos reemplazando
        for ln in text[4:end].split("\n"):
            if dropping and ln[:1] in (" ", "\t", "-"):
                continue
            dropping = False
            if ln.startswith(keys):
                dropping = True
                continue
            out.append(ln)
        block = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True,
                               default_flow_style=False).rstrip("\n")
        path.write_text("---\n" + "\n".join(out + [block]) + text[end:], encoding="utf-8")
    else:
        dumped = yaml.safe_dump({**fm, **fields}, sort_keys=False, allow_unicode=True,
                                default_flow_style=False)
        path.write_text(f"---\n{dumped}---{body}", encoding="utf-8")


def stamp_retraction(path, fm: dict, body: str, retraction: dict) -> None:
    """`retracted: true` + `retraction{...}`: la fuente deja de ser válida (bloqueante en el lint)."""
    stamp_fields(path, fm, body, {"retracted": True, "retraction": retraction})


def stamp_corrections(path, fm: dict, body: str, corrections: list) -> None:
    """`corrections: [...]` (#52): el paper SIGUE siendo citable — lo que hay que revisar son las
    afirmaciones que lo citan (un corrigendum cambia justo el valor extraído). Backlog en el lint."""
    stamp_fields(path, fm, body, {"corrections": corrections})


def crossref_retraction(doi: str, headers: dict) -> tuple[dict | None, list]:
    """Consulta Crossref por DOI. Devuelve (retraction | None, soft_updates). `retraction` es el
    primer `updated-by` con tipo retractante; `soft_updates` son las ENTRADAS COMPLETAS
    (`{type, notice_doi, date, source}`) de errata/corrigenda/EoC, que se estampan en `corrections`
    (#52 — antes se devolvía sólo el tipo y moría en stdout). Red tolerante: ante
    error de red o 404 devuelve (None, []) —no se puede afirmar retracción→ no se marca."""
    for wait in (2, 6, None):
        try:
            resp = requests.get(CROSSREF.format(doi=doi), headers=headers, timeout=30)
        except requests.RequestException:
            if wait is None:
                return None, []
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            return None, []
        if resp.status_code == 429 and wait is not None:
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            return None, []
        break
    else:
        return None, []
    try:
        msg = resp.json()["message"]
    except (ValueError, KeyError):
        return None, []
    retraction, soft = None, []
    for upd in msg.get("updated-by", []) or []:
        typ = str(upd.get("type", "")).lower()
        entry = {
            "type": typ,
            "notice_doi": upd.get("DOI"),
            "date": _upd_date(upd),
            "source": upd.get("source"),
        }
        if typ in RETRACTING and retraction is None:
            retraction = entry
        elif typ in SOFT:
            soft.append(entry)          # #52: la entrada COMPLETA (se persiste en `corrections`)
    return retraction, soft


def _upd_date(upd: dict) -> str | None:
    dp = (upd.get("updated") or {}).get("date-parts") or [[]]
    parts = dp[0] if dp else []
    return "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts)) if parts else None


def title_says_retracted(title: str) -> bool:
    """Fallback offline para papers SIN DOI: prefijo del título que los publishers ponen al retractar."""
    t = (title or "").strip().lower()
    return t.startswith(("retracted", "retraction:", "retracted article", "withdrawn"))


def slug_notes(slug: str) -> list:
    """Notas de paper de UN ingest (modo --slug de la cadena): bibcodes relevantes de
    build/<slug>/ads.json (vía ADS) + `sources[].key` y `extra_core` de la entrada del tema en
    topics.yaml (off-ADS/mixto declara ahí su bibliografía). Sólo notas que existen en disco
    (make_notes acaba de crearlas en la cadena); el barrido completo cubre cualquier drift."""
    stems: list[str] = []
    adsfile = cfg.ROOT / "build" / slug / "ads.json"
    if adsfile.exists():
        data = json.loads(adsfile.read_text(encoding="utf-8"))
        stems += [r["bibcode"] for r in data.get("records", [])
                  if r.get("relevant") and r.get("bibcode")]
    try:
        _, meta = cfg.topic_by_slug(slug)
    except KeyError:
        meta = {}
    stems += [s.get("key") for s in (meta.get("sources") or []) if s.get("key")]
    stems += [b for b in (meta.get("extra_core") or []) if b]
    if not stems:
        sys.exit(f"--slug {slug}: no hay build/{slug}/ads.json ni entrada con sources/extra_core "
                 "en topics.yaml — nada que chequear (¿corriste la cadena de ingest primero?).")
    notes, seen = [], set()
    for stem in stems:
        name = stem.replace("/", "_")
        if name in seen:
            continue
        seen.add(name)
        p = cfg.PAPERS / f"{name}.md"
        if p.exists():
            notes.append(p)
    return notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", help="chequear un solo bibcode (default: todos los de papers/)")
    ap.add_argument("--slug", help="chequear sólo los papers de un ingest (modo de la cadena; "
                                   "el barrido completo, sin --slug, es la pasada periódica)")
    ap.add_argument("--force", action="store_true", help="re-chequear también los ya marcados")
    args = ap.parse_args()
    if args.paper and args.slug:
        ap.error("--paper y --slug son excluyentes (uno puntual vs los de un ingest)")

    if not cfg.PAPERS.exists():
        print("No hay vault/wiki/papers/ — nada que chequear.")
        return 0
    if args.slug:
        notes = slug_notes(args.slug)
        print(f"--slug {args.slug}: {len(notes)} nota(s) del ingest (el barrido completo de la "
              "bóveda es la pasada periódica — correr sin --slug)")
    else:
        notes = ([cfg.PAPERS / f"{args.paper.replace('/', '_')}.md"] if args.paper
                 else sorted(cfg.PAPERS.glob("*.md")))
    headers = _ua()

    found, checked, marked = [], 0, 0
    corrected: list = []               # (bibcode, tipos) — #52: correcciones no-retractantes
    annotated = 0
    for note in notes:
        if not note.exists():
            print(f"  ! no existe {note.name}")
            continue
        fm, body = split_note(note.read_text(encoding="utf-8"))
        if fm is None:
            print(f"  ⚠ {note.name}: sin frontmatter parseable — no chequeable "
                  "(arreglá el YAML; el lint lo marca)")
            continue
        if "paper" not in (fm.get("tags") or []):
            continue
        if fm.get("retracted") and not args.force:
            found.append((fm.get("bibcode") or note.stem, "ya marcado"))
            continue
        doi, title = fm.get("doi"), fm.get("title") or ""
        retraction, soft = (crossref_retraction(doi, headers) if doi else (None, []))
        if doi:
            checked += 1      # sólo los consultados de verdad (los sin DOI van por prefijo de título)
            time.sleep(0.2)   # cortesía con Crossref
        # fallback offline por título para papers sin DOI (o que Crossref no marcó)
        if retraction is None and title_says_retracted(title):
            retraction = {"type": "retraction", "notice_doi": None, "date": None,
                          "source": "title-prefix (sin DOI en Crossref — verificar a mano)"}
        bib = fm.get("bibcode") or note.stem
        if soft:
            # #52: la corrección NO retracta (el paper sigue citable) pero cambia justo el valor
            # que se extrajo → se persiste en la nota; antes moría en este mismo print.
            types = ", ".join(dict.fromkeys(c["type"] for c in soft))
            corrected.append((bib, types))
            if (fm.get("corrections") or []) != soft:
                stamp_corrections(note, fm, body, soft)
                annotated += 1
                print(f"  · {bib}: corrección publicada ({types}) — anotada en `corrections`")
            else:
                print(f"  · {bib}: corrección publicada ({types}) — ya anotada")
        if retraction:
            stamp_retraction(note, fm, body, retraction)
            marked += 1
            found.append((fm.get("bibcode") or note.stem,
                          f"{retraction['type']} ({retraction.get('date') or 's/f'})"))
            print(f"  ⛔ RETRACTADO {fm.get('bibcode') or note.stem}: {retraction['type']} "
                  f"— marcado en la nota")

    print(f"\n{checked} chequeados vía Crossref, {marked} recién marcados, "
          f"{len(found)} retractados en total; {len(corrected)} con corrección publicada "
          f"({annotated} recién anotadas).")
    if corrected:
        print("Correcciones no-retractantes (el paper SIGUE siendo citable; revisá los valores que "
              "le extrajiste — el lint las lista como backlog):")
        for bib, types in corrected:
            print(f"  · {bib}: {types}")
    if found:
        print("Retractados (revisá cada afirmación que los cita — quitá o marcá la fuente):")
        for bib, why in found:
            print(f"  - {bib}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
