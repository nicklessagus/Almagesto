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

Exit code (issue 0.1 — desambiguado; antes el 1 estaba SOBRECARGADO):

    0  corrió y limpio
    1  corrió y detectó papers retractados
    2  **no pudo chequear**: precondición ausente (sin `papers/`, sin notas, sin `ads.json` ni
       entrada en `themes.yaml` para el `--slug`) o errores que dejaron papers sin consultar y
       ningún retractado.

**Retractados mandan**: con retractados Y errores sale 1, con los errores igual en el reporte.

Por qué importa: hasta 1.23.1 `slug_notes` hacía `sys.exit(str)` —exit 1— cuando no había nada que
chequear, y `ingest_star.py` traducía **cualquier** rc≠0 a "detectó papers retractados". La cadena
abortaba con un mensaje falso, y —peor— un error de red en el único paper del corpus salía **0**:
"no encontré retractados" sobre un paper que nadie miró, el falso limpio que D-43 prohíbe justo en
la frontera dura. Con D-45 esta misma pasada va a cubrir cinco eventos: el código se desambigua
antes de apoyarle una feature encima.
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


class NothingToCheck(RuntimeError):
    """Precondición ausente: no hay nada que chequear (→ rc 2).

    `slug_notes` es una función de librería y no debe matar el proceso: fijar el código de salida
    desde adentro es justo lo que producía el 1 sobrecargado. Informa, y `main()` decide."""


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


def stamp_fields(path, fm: dict, body: str, fields: dict) -> None:
    """Estampa claves de frontmatter editando el TEXTO (como merge_frontmatter_list de make_notes):
    NO re-serializa el YAML completo → preserva byte a byte comentarios/orden que haya dejado la
    extracción LLM. Si la nota ya traía esas claves (re-chequeo con --force, o una corrección nueva
    sobre un paper ya anotado), las reemplaza —incluidos sus bloques indentados y los ítems `-` de
    una lista—. Fallback (nota sin estructura `---\\n…\\n---\\n`): re-serializa el frontmatter parseado.
    La publicación en disco es atómica (`cfg.write_text_atomic`, H-01/D-53): un corte a mitad de
    camino nunca deja la nota truncada."""
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
    cfg.write_text_atomic(path, new_text)


def stamp_retraction(path, fm: dict, body: str, retraction: dict) -> None:
    """`retracted: true` + `retraction{...}`: la fuente deja de ser válida (bloqueante en el lint)."""
    # @inv INV-33
    stamp_fields(path, fm, body, {"retracted": True, "retraction": retraction})


def stamp_corrections(path, fm: dict, body: str, corrections: list) -> None:
    """`corrections: [...]` (#52): el paper SIGUE siendo citable — lo que hay que revisar son las
    afirmaciones que lo citan (un corrigendum cambia justo el valor extraído). Backlog en el lint."""
    # @inv INV-34
    stamp_fields(path, fm, body, {"corrections": corrections})


def crossref_retraction(doi: str, headers: dict) -> tuple[dict | None, list, str]:
    """Consulta Crossref por DOI → `(retraction | None, soft_updates, estado)`.

    `retraction` es el primer `updated-by` con tipo retractante; `soft_updates` son las ENTRADAS
    COMPLETAS (`{type, notice_doi, date, source}`) de errata/corrigenda/EoC, que se estampan en
    `corrections` (#52 — antes se devolvía sólo el tipo y moría en stdout).

    Sigue siendo **red tolerante** (nunca revienta, nunca afirma retracción sin evidencia), pero
    desde el issue 0.1 dice además **si pudo consultar** — `estado`:

    - `"ok"`      Crossref contestó y se leyó la respuesta.
    - `"sin-registro"`  404: contestó *"no tengo ese DOI"*. Es una **respuesta**, no un fallo; si
      contara como error, todo corpus con DOIs no indexados quedaría en rc 2 permanente y el código
      volvería a no distinguir nada.
    - `"error"`   no contestó (red caída tras los retries, 5xx, cuerpo no-json). Ese paper quedó
      **sin chequear**: el llamador no puede reportarlo como limpio.
    """
    for wait in (2, 6, None):
        try:
            resp = requests.get(CROSSREF.format(doi=doi), headers=headers, timeout=30)
        except requests.RequestException:
            if wait is None:
                return None, [], "error"
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            return None, [], "sin-registro"
        if resp.status_code == 429 and wait is not None:
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            return None, [], "error"
        break
    else:
        return None, [], "error"
    try:
        msg = resp.json()["message"]
    except (ValueError, KeyError):
        return None, [], "error"
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
    return retraction, soft, "ok"


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
    editar a mano en YAML. Gemelo de `query_ads.py:_listify_curado`/`ingest_theme.py:_listify_curado`
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
    themes.yaml (off-ADS/mixto declara ahí su bibliografía). Sólo notas que existen en disco
    (make_notes acaba de crearlas en la cadena); el barrido completo cubre cualquier drift."""
    stems: list[str] = []
    adsfile = cfg.ROOT / "build" / slug / "ads.json"
    if adsfile.exists():
        data = json.loads(adsfile.read_text(encoding="utf-8"))
        stems += [r["bibcode"] for r in data.get("records", [])
                  if r.get("relevant") and r.get("bibcode")]
    try:
        _, meta = cfg.theme_by_slug(slug)
    except KeyError:
        meta = {}
    # `_listify_curado`, no `or []` (R5/R7): `sources`/`extra_core` son campos de curación manual
    # y un escalar (UN solo bibcode/clave, sin corchetes) es YAML válido. Un `s` de `sources` que
    # además llegue escalar (en vez de `{key: ..., ...}`) se toma como si fuera él mismo la clave.
    stems += [key for s in _listify_curado(meta.get("sources"), "sources")
              for key in [s.get("key") if isinstance(s, dict) else s] if key]
    stems += [e["bibcode"] for e in cfg.load_extra_core(meta, entry=slug)]
    if not stems:
        raise NothingToCheck(
            f"--slug {slug}: no hay build/{slug}/ads.json ni entrada con sources/extra_core "
            "en themes.yaml — nada que chequear (¿corriste la cadena de ingest primero?).")
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


def _estampar(args, ap=None) -> None:
    """R-6/D-57: el paso se estampa a sí mismo al salir 0 o 1 (las dos ramas en que **corrió**);
    con rc 2 no, porque el registro no puede afirmar haber mirado lo que no miró.

    Es el último paso de `CADENA_ESTRELLA` y era el único de los siete que no se estampaba: la
    cadena completa se reportaba como cortada acá, siempre.  @inv INV-91"""
    if args.slug:
        cfg.save_paso(args.slug, "check_retractions", flags=_flags_usados(args, ap))


def _flags_usados(args, ap=None) -> list:
    """Los flags no-default de esta corrida, para `cadena:` del registro (D-48/D-57)."""
    return cfg.flags_usados(args, ap)


def main() -> int:
    """Las tres ramas de salida (ver el contrato en la docstring del módulo).  @inv INV-87

    El invariante que cierra acá: *un chequeo que no puede correr reporta error, nunca contribuye
    un cero al total*. Antes, "sin nada que chequear" y "Crossref caído" terminaban los dos en un
    código que la cadena leía como veredicto sobre la frontera dura."""
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
        cfg.print_seguro("⛔ no pudo chequear: no hay vault/wiki/papers/ (rc 2). Un 0 acá se lee "
                         "como «corrió y está limpio» sobre un corpus que nadie miró.")
        return 2
    if args.slug:
        try:
            notes = slug_notes(args.slug)
        except NothingToCheck as e:
            cfg.print_seguro(f"⛔ no pudo chequear (rc 2): {e}")
            return 2
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
    # Papers SIN `doi`: no se les puede preguntar a Crossref, así que no entran en `checked` — pero
    # tampoco son un `error`, porque no falló nada: es una propiedad del paper. Antes caían en un
    # tercer estado MUDO, y con un corpus enteramente off-ADS (que nace sin DOI por construcción)
    # el barrido salía 0 con "0 con error al chequear": se leía como «la bóveda está limpia de
    # retracciones» sobre papers a los que nadie preguntó. Se cuentan y se nombran.
    sin_doi: list = []
    if not notes:
        cfg.print_seguro("⛔ no pudo chequear (rc 2): no hay ninguna nota de paper que mirar.")
        return 2

    for note in notes:
        if not note.exists():
            # precondición ausente para ESTE paper (típico: `--paper <bibcode>` mal escrito). No es
            # un chequeo limpio: es un paper que nadie miró.
            cfg.print_seguro(f"  ! no existe {note.name}")
            errors.append((note.stem, "la nota no existe"))
            continue
        # H-10: la pasada periódica barre TODA la bóveda — un registro de Crossref legal-pero-de-
        # otra-forma (u otra sorpresa puntual de un paper) no debe abortar el barrido entero; se
        # reporta el paper como no chequeado y se sigue con el resto (antes, `main()` no tenía
        # try/except por paper y un solo caso raro tumbaba la corrida completa).
        try:
            fm, body = split_note(note.read_text(encoding="utf-8"))
            if fm is None:
                # el paper existe y es del corpus, pero quedó SIN consultar: cuenta como error, no
                # como "limpio" (rc 2). El lint lo marca aparte como frontmatter no parseable.
                cfg.print_seguro(f"  ⚠ {note.name}: sin frontmatter parseable — no chequeable "
                      "(arreglá el YAML; el lint lo marca)")
                errors.append((note.stem, "sin frontmatter parseable"))
                continue
            if "paper" not in (fm.get("tags") or []):
                continue
            if fm.get("retracted") and not args.force:
                found.append((fm.get("bibcode") or note.stem, "ya marcado"))
                continue
            doi, title = fm.get("doi"), fm.get("title") or ""
            retraction, soft, estado = (crossref_retraction(doi, headers) if doi
                                        else (None, [], "sin-doi"))
            if not doi:
                sin_doi.append(fm.get("bibcode") or note.stem)
            if doi:
                if estado == "error":
                    # Crossref no contestó: este paper NO se chequeó. Antes esto salía 0 —"no
                    # encontré retractados"— sobre un paper que nadie miró.
                    errors.append((fm.get("bibcode") or note.stem, "Crossref no contestó"))
                    cfg.print_seguro(f"  ✗ {fm.get('bibcode') or note.stem}: Crossref no contestó "
                                     "— queda SIN chequear")
                else:
                    checked += 1  # sólo los consultados de verdad (los sin DOI van por prefijo de título)
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
          f"({annotated} recién anotadas); {len(errors)} con error al chequear; "
          f"{len(sin_doi)} sin DOI (no consultables en Crossref).")
    if sin_doi:
        cfg.print_seguro(
            "Sin DOI — a estos NADIE les preguntó a Crossref; los cubre sólo el prefijo de título "
            "(`RETRACTED:`), que es una heurística, no el registro:")
        for bib in sin_doi[:10]:
            cfg.print_seguro(f"  · {bib}")
        if len(sin_doi) > 10:
            cfg.print_seguro(f"  · … y {len(sin_doi) - 10} más")
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
        # "retractados mandan": con retractados Y errores sale 1 (lo urgente es la fuente
        # retractada), y los errores quedan igual en el reporte de arriba.
        _estampar(args, ap)
        return 1
    if errors:
        cfg.print_seguro("⛔ no pudo chequear (rc 2): quedaron papers sin consultar y no se detectó "
                         "ninguna retracción — el resultado NO es «limpio», es «no se miró».")
        return 2
    if sin_doi and not checked:
        # El barrido no consultó Crossref **ni una vez**: todo lo que hay son papers sin DOI. Salir
        # 0 acá afirma que la bóveda está limpia de retracciones sobre una población que nadie
        # miró — el cero inventado que INV-87 prohíbe, en el detector que más caro sale equivocar.
        # Un corpus enteramente off-ADS cae acá legítimamente: se cierra declarando los DOI que
        # existan (los hay para casi todo lo publicado) y asumiendo que el resto sólo lo cubre el
        # prefijo de título.
        cfg.print_seguro(f"⛔ no pudo chequear (rc 2): los {len(sin_doi)} paper(s) del barrido no "
                         f"tienen `doi`, así que no se consultó Crossref ni una vez — el resultado "
                         f"NO es «limpio», es «no se miró». Completá los `doi` que existan.")
        return 2
    _estampar(args, ap)
    return 0


if __name__ == "__main__":
    sys.exit(main())
