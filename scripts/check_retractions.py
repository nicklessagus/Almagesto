"""Chequea si algún paper de la bóveda fue RETRACTADO y lo marca en su nota.

Uso:
    python scripts/check_retractions.py            # todos los papers de vault/wiki/papers/ (pasada periódica)
    python scripts/check_retractions.py --slug <slug>       # sólo los papers de UN ingest (modo de la cadena)
    python scripts/check_retractions.py --paper <bibcode>   # uno solo
    python scripts/check_retractions.py --force    # re-chequear también los ya marcados

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
import os
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
    """(frontmatter dict, body) de una nota `---\\n<yaml>---\\n<body>`. Delimita con
    `cfg.frontmatter_span` (por LÍNEA delimitadora, no por búsqueda textual de la subcadena
    `---`, H-11): un `text.split("---", 2)` corta también dentro de un escalar entrecomillado que
    trae un `---` adentro (`title: "Un titulo con --- adentro"`, YAML perfectamente válido) — el
    split textual parte el valor a la mitad, `yaml.safe_load` sobre ese pedazo no parsea, y el
    paper **se saltea del chequeo de retracciones** con el mensaje falso "arreglá el YAML": falso
    limpio justo en la frontera dura (regla #0 — una fuente retractada citada sin chequear).
    (None, text) si no hay frontmatter o no parsea."""
    span = cfg.frontmatter_span(text)
    if span is None:
        return None, text
    yaml_block, body = span
    try:
        return (yaml.safe_load(yaml_block) or {}), body
    except yaml.YAMLError:
        return None, text


def _write_atomic(path, new_text: str) -> None:
    """Publica `new_text` en `path` sin dejarla nunca a medio escribir (H-01).

    Medido con `ulimit -f`: el `write_text` directo dejaba una nota de 16.071 B en 8.192 B, con 198
    de 400 ocurrencias de la extracción LLM —lo MENOS regenerable de la bóveda— desaparecidas sin
    aviso.

    El contenido nuevo se escribe primero a un temporal en el MISMO directorio (mismo filesystem) y
    recién se publica con `os.replace`, que es un **rename atómico**: o está el archivo viejo entero
    o el nuevo entero, nunca la mitad. Si el corte pasa mientras se llena el temporal, `path` **no
    se tocó**.

    ⚠ Por qué NO alcanza el patrón "respaldar el original y restaurar en el `except`": ese sólo
    cubre el corte que llega como **excepción**. Ante un `SIGKILL` o un corte de energía no corre
    ningún `except` y la nota queda truncada igual — que es exactamente el escenario que la
    docstring afirmaba cubrir. Mismo mecanismo que `lib_config.save_registro`, y `os.replace` se
    llama como atributo del módulo `os` para que un test pueda interceptarlo."""
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    try:
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def stamp_fields(path, fm: dict, body: str, fields: dict) -> None:
    """Estampa claves de frontmatter editando el TEXTO (como merge_frontmatter_list de make_notes):
    NO re-serializa el YAML completo → preserva byte a byte comentarios/orden que haya dejado la
    extracción LLM. Si la nota ya traía esas claves (re-chequeo con --force, o una corrección nueva
    sobre un paper ya anotado), las reemplaza —incluidos sus bloques indentados y los ítems `-` de
    una lista—. Fallback (nota sin estructura `---\\n…\\n---\\n`): re-serializa el frontmatter parseado.
    La publicación en disco es atómica (`_write_atomic`, H-01): un corte a mitad de camino nunca
    deja la nota truncada."""
    text = path.read_text(encoding="utf-8")
    keys = tuple(f"{k}:" for k in fields)
    end = text.find("\n---\n", 4)
    if text.startswith("---\n") and end > 0:
        out, dropping = [], False
        # una clave top-level nunca arranca con espacio/tab/`-`: mientras `dropping`, esas líneas
        # son el bloque (mapa indentado o lista) de la clave vieja que estamos reemplazando
        lines = text[4:end].split("\n")
        i, n = 0, len(lines)
        while i < n:
            ln = lines[i]
            if dropping:
                if ln.strip() == "":
                    # H-02: una línea EN BLANCO dentro del bloque (mapa/lista multilínea) es YAML
                    # válido y no corta el bloque — el bug viejo la trataba como "clave nueva",
                    # dejaba de dropear ahí, y el ítem huérfano que seguía se absorbía en la clave
                    # anterior en silencio (`tags: ['paper', {'type': 'corrigendum'}]`, ninguna
                    # categoría del lint lo veía). Se mira hacia adelante, saltando blancas: si lo
                    # que sigue todavía está indentado, la(s) blanca(s) eran parte del bloque viejo
                    # y se descartan con él; si lo que sigue es una clave nueva a nivel top, eran
                    # separador legítimo y se conservan.
                    j = i + 1
                    while j < n and lines[j].strip() == "":
                        j += 1
                    if j < n and lines[j][:1] in (" ", "\t", "-"):
                        i += 1
                        continue
                    dropping = False
                    out.append(ln)
                    i += 1
                    continue
                if ln[:1] in (" ", "\t", "-"):
                    i += 1
                    continue
                dropping = False
            if ln.startswith(keys):
                dropping = True
                i += 1
                continue
            out.append(ln)
            i += 1
        block = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True,
                               default_flow_style=False).rstrip("\n")
        new_text = "---\n" + "\n".join(out + [block]) + text[end:]
    else:
        dumped = yaml.safe_dump({**fm, **fields}, sort_keys=False, allow_unicode=True,
                                default_flow_style=False)
        new_text = f"---\n{dumped}---{body}"
    _write_atomic(path, new_text)


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
    # H-10: Crossref es una API ajena — `updated-by` "debería" ser una lista de mapas, pero un
    # registro hostil (mapa en vez de lista, o una lista con un elemento que no es mapa) hacía
    # `AttributeError` acá (`upd.get(...)` sobre un `str`, al iterar las CLAVES de un dict). La
    # promesa de la función es "red tolerante: ante forma rara, (None, [])" — `cfg.as_list`/
    # `cfg.as_map` cierran las dos formas que la rompían sin dejar de cumplirla.
    for upd in cfg.as_list(msg.get("updated-by")):
        upd = cfg.as_map(upd)
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
    """Fecha `AAAA[-MM[-DD]]` de un `updated-by` de Crossref, o `None` si la forma no es la
    esperada (R11). `date-parts` debe ser una lista de listas de enteros (`[[2021, 5, 3]]`); una
    respuesta que trae otra forma (p. ej. `date-parts: "2021"`, string en vez de lista) NO debe
    FABRICAR una fecha truncada — el `dp[0]` de un string da su primer CARÁCTER (`"2"`), que antes
    se estampaba tal cual como `retraction.date`/`corrections[].date`. Un dato inventado en la
    capa auditable del frontmatter es peor que una excepción: no deja rastro de que la fuente no
    se pudo interpretar. Ante forma inesperada, `None` (el llamador ya sabe leer un date ausente)."""
    dp = cfg.as_list(cfg.as_map(upd.get("updated")).get("date-parts"))
    parts = cfg.as_list(dp[0]) if dp else []
    if not parts or not all(isinstance(p, int) for p in parts):
        return None
    return "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts))


def title_says_retracted(title: str) -> bool:
    """Fallback offline para papers SIN DOI: prefijo del título que los publishers ponen al retractar."""
    t = (title or "").strip().lower()
    return t.startswith(("retracted", "retraction:", "retracted article", "withdrawn"))


def _listify_curado(v, campo: str):
    """Normaliza un campo de CURACIÓN MANUAL (`extra_core`, `sources`) que el framework instruye
    editar a mano en YAML. Gemelo de `query_ads.py:_listify_curado`/`ingest_topic.py:_listify_curado`
    (R5/R7): un `campo: <valor>` sin corchetes es la forma natural de declarar UN solo elemento y
    es YAML válido — a diferencia de `cfg.as_list` (que trataría el escalar como forma inválida y
    lo degradaría a `[]`), acá conviene PRESERVAR la intención. El `or []` viejo no disparaba con
    un escalar truthy y la comprensión de abajo lo recorría CARÁCTER POR CARÁCTER: con
    `extra_core: 2020ApJ...900....1X` el paper real nunca se pedía a Crossref y el paso cerraba en
    verde sin haber chequeado nada — falso limpio en la frontera dura."""
    if isinstance(v, list):
        return v
    if v:
        cfg.print_seguro(
            f"  ⚠ `{campo}` está escrito como escalar ({v!r}) en vez de lista — se toma como un "
            f"solo elemento; para declarar más de uno usá `{campo}: [{v!r}, ...]`."
        )
        return [v]
    return []


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
    # `_listify_curado`, no `or []` (R5/R7): `sources`/`extra_core` son campos de curación manual
    # y un escalar (UN solo bibcode/clave, sin corchetes) es YAML válido. Un `s` de `sources` que
    # además llegue escalar (en vez de `{key: ..., ...}`) se toma como si fuera él mismo la clave.
    stems += [key for s in _listify_curado(meta.get("sources"), "sources")
              for key in [s.get("key") if isinstance(s, dict) else s] if key]
    stems += [b for b in _listify_curado(meta.get("extra_core"), "extra_core") if b]
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
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", help="chequear un solo bibcode (default: todos los de papers/)")
    ap.add_argument("--slug", help="chequear sólo los papers de un ingest (modo de la cadena; "
                                   "el barrido completo, sin --slug, es la pasada periódica)")
    ap.add_argument("--force", action="store_true", help="re-chequear también los ya marcados")
    args = ap.parse_args()
    if args.paper and args.slug:
        ap.error("--paper y --slug son excluyentes (uno puntual vs los de un ingest)")

    if not cfg.PAPERS.exists():
        cfg.print_seguro("No hay vault/wiki/papers/ — nada que chequear.")
        return 0
    if args.slug:
        notes = slug_notes(args.slug)
        cfg.print_seguro(f"--slug {args.slug}: {len(notes)} nota(s) del ingest (el barrido completo de la "
              "bóveda es la pasada periódica — correr sin --slug)")
    else:
        notes = ([cfg.PAPERS / f"{args.paper.replace('/', '_')}.md"] if args.paper
                 else sorted(cfg.PAPERS.glob("*.md")))
    headers = _ua()

    found, checked, marked = [], 0, 0
    corrected: list = []               # (bibcode, tipos) — #52: correcciones no-retractantes
    annotated = 0
    errors: list = []                  # (nombre, motivo) — H-10: un paper raro no tumba el barrido
    for note in notes:
        if not note.exists():
            cfg.print_seguro(f"  ! no existe {note.name}")
            continue
        # H-10: la pasada periódica barre TODA la bóveda — un registro de Crossref legal-pero-de-
        # otra-forma (u otra sorpresa puntual de un paper) no debe abortar el barrido entero; se
        # reporta el paper como no chequeado y se sigue con el resto (antes, `main()` no tenía
        # try/except por paper y un solo caso raro tumbaba la corrida completa).
        try:
            fm, body = split_note(note.read_text(encoding="utf-8"))
            if fm is None:
                cfg.print_seguro(f"  ⚠ {note.name}: sin frontmatter parseable — no chequeable "
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
                    cfg.print_seguro(f"  · {bib}: corrección publicada ({types}) — anotada en `corrections`")
                else:
                    cfg.print_seguro(f"  · {bib}: corrección publicada ({types}) — ya anotada")
            if retraction:
                stamp_retraction(note, fm, body, retraction)
                marked += 1
                found.append((fm.get("bibcode") or note.stem,
                              f"{retraction['type']} ({retraction.get('date') or 's/f'})"))
                cfg.print_seguro(f"  ⛔ RETRACTADO {fm.get('bibcode') or note.stem}: {retraction['type']} "
                      f"— marcado en la nota")
        except Exception as exc:
            errors.append((note.stem, str(exc)))
            cfg.print_seguro(f"  ✗ {note.stem}: no se pudo chequear ({exc}) — sigo con el resto")

    cfg.print_seguro(f"\n{checked} chequeados vía Crossref, {marked} recién marcados, "
          f"{len(found)} retractados en total; {len(corrected)} con corrección publicada "
          f"({annotated} recién anotadas); {len(errors)} con error al chequear.")
    if corrected:
        cfg.print_seguro("Correcciones no-retractantes (el paper SIGUE siendo citable; revisá los valores que "
              "le extrajiste — el lint las lista como backlog):")
        for bib, types in corrected:
            cfg.print_seguro(f"  · {bib}: {types}")
    if errors:
        cfg.print_seguro("No se pudieron chequear (error inesperado — no tumbaron el barrido; revisar a mano):")
        for name, why in errors:
            cfg.print_seguro(f"  · {name}: {why}")
    if found:
        cfg.print_seguro("Retractados (revisá cada afirmación que los cita — quitá o marcá la fuente):")
        for bib, why in found:
            cfg.print_seguro(f"  - {bib}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
