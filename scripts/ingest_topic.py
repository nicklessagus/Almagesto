"""Orquestador de la cadena mecánica de ingest-topic: despacha según `source` del tema.

Uso:
    python scripts/ingest_topic.py <slug> [--force] [--yes]

Lee la entrada del tema en vault/config/topics.yaml y corre la cadena que corresponda a su
campo `source` (formaliza el modo off-ADS del skill ingest-topic en el tooling):

- `ads` (default si el campo falta): cadena astro estándar —
  query_ads --topic → [guardia de expansión] → fetch_arxiv → fetch_pdf → make_notes --topic →
  extract_fulltext → check_retractions. La **guardia de expansión** (#37) frena entre la query y
  el primer paso que gasta red y disco si el core se multiplicó respecto de lo ya ingestado
  (default ×1.5 y >50 nuevos); `--yes` continúa a sabiendas.
- `web` | `local-pdfs` | `local-pdfs+web`: modo off-ADS. La bibliografía se declara en la
  lista `sources:` de la entrada (cada item: `key` = clave de cita sintética AAAA+Autor +
  `url` (fuente web) o `pdf` (ruta a un PDF provisto por el usuario) + metadata opcional
  `title/author/year/venue/n_authors/doi`). El orquestador stubbea el concept, procesa cada
  fuente (`fetch_web.py` para URLs; copia a raw/pdfs/<slug>/<key>.pdf para PDFs) y corre
  extract_fulltext. Tras copiar un PDF, el campo `pdf` del item se **repunta solo** a la
  copia de la bóveda (`vault/raw/pdfs/<slug>/<key>.pdf`, repo-relative): el path declarado
  suele ser staging efímero (scratchpad/descargas) que muere y deja un puntero roto en
  topics.yaml; la copia versionada es la que vale. Rutas `pdf` relativas se resuelven
  contra la raíz del repo (portable entre máquinas). Sin query_ads / fetch_ground_truth (no aplican fuera de ADS);
  check_retractions SÍ corre cuando algún item declara `doi` (Crossref lo cubre igual).
  **Tema MIXTO:** un tema off-ADS puede además declarar `extra_core: [bibcode, …]` con los
  papers del tema que SÍ están en ADS (un método no-astro casi siempre tiene aplicaciones
  publicadas en revista astro) — para ellos corre la sub-cadena ADS (query_ads --extra-only →
  fetch_arxiv → fetch_pdf → make_notes --topic): metadata ADS real, sin blockquote off-ADS.

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
import json
import re
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


def _listify_curado(v, campo: str):
    """Normaliza un campo de CURACIÓN MANUAL (`extra_core`) que `topics.yaml` instruye editar a
    mano. Un `campo: <valor>` sin corchetes es la forma natural de declarar UN solo elemento y es
    YAML válido — a diferencia de `cfg.as_list` (que trataría el escalar como forma inválida y lo
    degradaría a `[]`), acá conviene PRESERVAR la intención: la curación no se pierde por no poner
    corchetes (gemelo de `query_ads._listify_curado`, mismo defecto medido en R13). Reporta igual,
    para que la forma se corrija en origen."""
    if isinstance(v, list):
        return v
    if v:
        cfg.print_seguro(
            f"  ⚠ `{campo}` está escrito como escalar ({v!r}) en vez de lista — se toma como un "
            f"solo elemento; para declarar más de uno usá `{campo}: [{v!r}, ...]`."
        )
        return [v]
    return []


def run(script: str, *args: str) -> int:
    """Corre un script de la cadena con el mismo intérprete (rutas absolutas vía lib_config)."""
    cfg.print_seguro(f"\n→ {script} {' '.join(args)}")
    return subprocess.run([sys.executable, str(cfg.ROOT / "scripts" / script), *args],
                          cwd=cfg.ROOT / "scripts").returncode


# ── guardia de expansión (#37) ───────────────────────────────────────────────
# La cadena es idempotente respecto de NO PISAR, pero no respecto del ALCANCE: un re-run puede
# convertirse en una expansión masiva sin ningún checkpoint humano (caso real: re-correr au_mic
# dio 191 core por query directa + 659 por chaining = 850 "core" contra ~230 notas, y el
# orquestador siguió derecho a bajar PDFs). El conteo ya se imprimía, pero no gateaba nada.
EXPANSION_FACTOR = 1.5     # salto mínimo (core nuevo / ya ingestado) para frenar
EXPANSION_NEW = 50         # …y además, mínimo de papers nuevos (evita frenar por ruido chico)


def expansion_guard(slug: str, yes: bool) -> None:
    """Frena la cadena DESPUÉS de query_ads y ANTES del primer paso que gasta red y disco, si el
    pool core se multiplicó respecto de lo ya ingestado del sujeto. No aplica al primer ingest
    (sin notas previas no hay expansión que medir: el usuario acaba de pedir el sujeto entero)."""
    adsfile = cfg.ROOT / "build" / slug / "ads.json"
    if not adsfile.exists():
        return
    data = json.loads(adsfile.read_text(encoding="utf-8"))
    core = [r for r in data["records"] if r.get("relevant")]
    n_cand = len(cfg.as_list(data.get("candidates")))   # pendientes de triage (#38): no se bajan
    conocidos = {r["bibcode"] for r in core
                 if (cfg.PAPERS / f"{make_notes.safe_name(r['bibcode'])}.md").exists()}
    nuevos = [r for r in core if r["bibcode"] not in conocidos]
    if not conocidos:                       # primer ingest del sujeto
        return
    factor = len(core) / len(conocidos)
    if len(nuevos) < EXPANSION_NEW or factor < EXPANSION_FACTOR:
        return
    via_chain = sum(1 for r in nuevos if str(r.get("via") or "").startswith("chain:"))
    cfg.print_seguro(f"\n⚠ EXPANSIÓN del corpus de {slug}: {len(core)} core vs {len(conocidos)} ya ingestados "
          f"(×{factor:.1f}) → {len(nuevos)} papers NUEVOS, {via_chain} de ellos vía el grafo de citas.")
    if n_cand:
        cfg.print_seguro(f"  (además hay {n_cand} candidatos de chaining pendientes de triage — ésos no se bajan)")
    cfg.print_seguro("  Con la regla de combinación en OR (default), el chaining trae todo lo que menciona al "
          "sujeto con ≥1 faceta cualquiera. La palanca es la OBLIGATORIEDAD, no podar regex:\n"
          "    relevance.require: [<faceta-eje>]   # AND: la faceta sin la cual el paper no sirve\n"
          "    relevance.min_topics: N             # ≥N facetas cualesquiera\n"
          "  en vault/config/objective.yaml (skill setup). Después re-corré query_ads.py para "
          "re-clasificar — todavía no se bajó nada.")
    if not yes:
        sys.exit(f"cadena frenada antes de bajar {len(nuevos)} papers. Para continuar a sabiendas: "
                 f"--yes (el ads.json ya quedó regenerado; nada más se tocó).")
    cfg.print_seguro("  → --yes: sigo con la expansión a sabiendas.")


def repoint_source_pdf(key: str, declared: str, dest: Path) -> None:
    """Repunta `sources[].pdf` del item a la copia versionada de la bóveda (repo-relative).

    El path declarado suele ser staging efímero (scratchpad, carpeta de descargas): al
    limpiarse deja un puntero muerto en topics.yaml. Tras la copia, la que vale es la de la
    bóveda → el campo se reescribe a `vault/raw/pdfs/<slug>/<key>.pdf` (repo-relative,
    portable entre máquinas; al leer, las relativas se resuelven contra cfg.ROOT).
    Reescritura quirúrgica de la línea exacta — topics.yaml vive lleno de comentarios que
    un dump YAML destruiría. Si el path declarado no matchea exactamente UNA línea `pdf:`,
    se avisa y se deja a mano (no adivinar).
    """
    if not dest.exists():
        return
    rel = dest.relative_to(cfg.ROOT).as_posix()
    if declared == rel:
        return
    text = cfg.TOPICS_YAML.read_text(encoding="utf-8")
    pat = re.compile(rf"""^(\s*pdf:\s*)["']?{re.escape(declared)}["']?\s*$""", re.M)
    n = len(pat.findall(text))
    if n != 1:
        cfg.print_seguro(f"  ⚠ {key}: no repunté `pdf:` en topics.yaml (el path declarado matchea "
              f"{n} líneas, esperaba 1) — repuntalo a mano a {rel}")
        return
    cfg.TOPICS_YAML.write_text(pat.sub(lambda m: m.group(1) + rel, text), encoding="utf-8")
    cfg.print_seguro(f"  {key}: sources[].pdf repuntado → {rel}")


def ingest_ads(slug: str, yes: bool = False) -> None:
    """Cadena astro estándar (paso 2 del skill ingest-topic), abortando al primer fallo."""
    for script, args in (("query_ads.py", ["--topic", slug]),
                         ("fetch_arxiv.py", [slug]),
                         ("fetch_pdf.py", [slug]),      # los sin arXiv, vía resolver ADS (esources)
                         ("make_notes.py", ["--topic", slug]),
                         ("extract_fulltext.py", [slug])):
        rc = run(script, *args)
        if rc:
            sys.exit(f"{script} falló (rc={rc}) — cadena abortada. La cadena es idempotente: "
                     "corregí y re-corré ingest_topic.py (lo ya bajado no se re-baja).")
        if script == "query_ads.py":       # checkpoint ANTES del primer paso que gasta red y disco
            expansion_guard(slug, yes)
    # cierre: sólo los papers de ESTE ingest (el barrido completo es pasada periódica — maintain);
    # exit 1 acá significa "detectó papers retractados", no un fallo de la cadena
    if run("check_retractions.py", "--slug", slug):
        sys.exit("check_retractions detectó papers retractados — revisá las notas marcadas "
                 "(el lint las surface como bloqueante).")


def ingest_offads(slug: str, meta: dict, force: bool) -> None:
    """Modo off-ADS: concept stub + una fuente por item de `sources:` (web o PDF local)."""
    for k in ("area", "concept"):
        if not meta.get(k):
            sys.exit(f"la entrada '{slug}' no tiene `{k}` en topics.yaml (requerido para el concept).")
    # `cfg.as_list`, no `or []`: `sources:` es un archivo de instancia editado a mano y un escalar
    # truthy (una sola fuente sin corchetes) no caía en el `or` — esquivaba el `sys.exit` amable
    # de abajo y moría más adelante con `AttributeError` sin decir qué corregir (R6). Acá SÍ
    # conviene degradar a `[]` (no adivinar un elemento): el mensaje de abajo ya explica el formato
    # correcto (`sources:` con items `key + url|pdf`), y un escalar no alcanza para reconstruir eso.
    sources = cfg.as_list(meta.get("sources"))
    if not sources:
        sys.exit(f"'{slug}' es off-ADS (source: {meta.get('source')}) pero no declara `sources:` en "
                 "topics.yaml — listá ahí su bibliografía (items con key + url|pdf; ver header del YAML).")
    allowed = OFFADS_KINDS[meta["source"]]
    concept = meta["concept"]
    # #81: el rechazo de una fuente declarada vive en `decisiones` del registro versionado
    # (`triage.py --drop-source`). Es el equivalente de "no re-proponer" del otro carril: acá la
    # fuente la declara el usuario, así que no se puede filtrar sola — pero volver a declarar algo
    # que se descartó (típico al retomar el tema meses después) merece un aviso con el motivo.
    descartadas = {k: d for k, d in cfg.load_decisiones(slug).items()
                   if d.get("decision") == "descartado" and cfg.es_del_carril(d, "fuente-declarada")}

    make_notes.write_concept_note(slug, force=False)   # nunca --force acá: protege la síntesis LLM

    fails = n_pdf = 0
    pending_items: list[tuple[str, str, str]] = []   # (key, motivo, puntero) → aviso final
    failed_items: list[tuple[str, str]] = []         # (key, puntero) → aviso final
    for s in sources:
        key = s.get("key") or ""
        if not CITEKEY_RE.match(key):
            sys.exit(f"key inválida en sources de '{slug}': {key!r}. Debe empezar con AAAA+letra "
                     "(clave de cita sintética, p. ej. 2006RasmussenWilliams).")
        # Se busca por clave Y por url: `--drop-source` acepta las dos (la url es la clave cuando
        # la fuente no tiene una sintética), pero un item de `sources:` siempre trae una clave que
        # matchea CITEKEY_RE — así que un descarte registrado por url no se habría cruzado nunca
        # con la mitad que lo consume, y el aviso quedaba mudo justo en ese caso.
        if (dk := next((k for k in (key, s.get("url")) if k and k in descartadas), None)):
            d = descartadas[dk]
            cfg.print_seguro(f"  ⚠ {key}: figura DESCARTADA en el registro ({d.get('fecha', 's/f')}"
                  f"{'' if dk == key else f', por url {dk}'}): "
                  f"{d.get('motivo') or '(sin motivo)'} — se ingesta igual; si cambiaste de "
                  f"opinión, sacá la entrada de `decisiones` en {cfg.registro_path(slug)}")
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
            src = Path(str(s["pdf"])).expanduser()
            if not src.is_absolute():
                src = cfg.ROOT / src   # repo-relative: la forma canónica post-repunte
            if dest.exists() and not force:
                cfg.print_seguro(f"{key}: ya existe {dest} (usá --force para re-copiar)")
            elif not src.exists():
                if dest.exists():
                    # --force en una máquina sin la fuente externa (post-clone): la copia versionada
                    # en la bóveda es la que vale — conservarla no es un fallo.
                    cfg.print_seguro(f"  ⚠ {key}: no existe el PDF fuente {src}; conservo la copia de la bóveda ({dest})")
                else:
                    cfg.print_seguro(f"  ! {key}: no existe el PDF fuente {src} — item salteado")
                    fails += 1
                    failed_items.append((key, str(src)))
                    continue
            elif src.resolve() == dest.resolve():
                # la fuente declarada YA es la copia de la bóveda (típico post-repunte + --force)
                cfg.print_seguro(f"{key}: la fuente declarada es la copia de la bóveda — nada que copiar")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                cfg.print_seguro(f"{key}: {src.name} → {dest}")
            repoint_source_pdf(key, str(s["pdf"]), dest)
            n_pdf += 1     # sólo cuenta PDFs presentes en disco (un item fallido no dispara extract)
            # stub de nota (idempotente; detecta solo el PDF copiado y linkea el campo `pdf`)
            make_notes.write_web_paper_note(key, slug=slug, concept=concept,
                                            title=s.get("title"), first_author=s.get("author"),
                                            year=s.get("year"), n_authors=s.get("n_authors"),
                                            doi=s.get("doi"), venue=s.get("venue"))
    # Tema MIXTO: un método no-astro casi siempre tiene alguna aplicación/variante publicada en
    # revista astro — papers con bibcode ADS real. Van en `extra_core:` (no en `sources:`, que
    # degradaría el stub: clave sintética, citation_count 0, blockquote off-ADS falso) y para
    # ellos corre la sub-cadena ADS. Antes extra_core se ignoraba acá en silencio.
    # `_listify_curado`, no `or []`: gemelo de query_ads.py:910 (R13) — un `extra_core: <bibcode>`
    # sin corchetes (un solo paper con bibcode ADS en un tema mixto) es truthy y no caía en el
    # `or`; la comprensión de abajo recorría el string letra por letra y el bibcode real nunca
    # entraba a la sub-cadena ADS: la curación manual se perdía en silencio.
    extra = [b for b in _listify_curado(meta.get("extra_core"), "extra_core") if b]
    if extra:
        cfg.print_seguro(f"\nextra_core: {len(extra)} paper(s) con bibcode ADS (tema mixto) → sub-cadena ADS")
        for script, sargs in (("query_ads.py", ["--topic", slug, "--extra-only"]),
                              ("fetch_arxiv.py", [slug]),
                              ("fetch_pdf.py", [slug]),
                              ("make_notes.py", ["--topic", slug])):
            rc = run(script, *sargs)
            if rc:
                sys.exit(f"{script} falló (rc={rc}) — cadena abortada. La cadena es idempotente: "
                         "corregí y re-corré ingest_topic.py (lo ya bajado no se re-baja).")
    extract_rc = 0
    if n_pdf or extra:
        # el rc de extract se reporta aparte: un fallo de extracción NO es una "fuente fallida"
        # (contarlo ahí inflaba el conteo del aviso final)
        extract_rc = run("extract_fulltext.py", slug, *(["--force"] if force else []))
    # Aviso claro al operador (issue #7): qué fuentes faltan y con qué puntero, para que el
    # usuario las provea. Las pendientes NO son fallos (la cadena degrada limpio y sigue).
    if pending_items:
        cfg.print_seguro("\n⏳ Fuentes PENDIENTES (derivadas al usuario — no frenan la cadena):")
        for key, why, ptr in pending_items:
            cfg.print_seguro(f"  - {key} [{why}] → {ptr}")
        cfg.print_seguro("  Cuando esté la fuente: reemplazá `pending` por `pdf:`/`url:` en sources: y re-corré.")
    if failed_items:
        cfg.print_seguro("\n! Fuentes que FALLARON (¿transitorio? → re-corré; si la fuente no se puede "
              "conseguir, marcá el item con `pending: paywall|scan|unextractable` para derivarla "
              "al usuario sin frenar la cadena):")
        for key, ptr in failed_items:
            cfg.print_seguro(f"  - {key} → {ptr}")
    if fails:
        sys.exit(f"{fails} fuente(s) fallaron — revisá arriba y re-corré (idempotente).")
    if extract_rc:
        sys.exit(f"extract_fulltext.py falló (rc={extract_rc}) — corregí y re-corré "
                 "(idempotente: los PDFs ya copiados no se re-copian).")
    # off-ADS no tiene bibcode ADS, pero un DOI declarado en sources alcanza para el chequeo de
    # retracciones (Crossref) — una fuente retractada silenciosa rompe la frontera dura igual.
    # Con extra_core también corre: los papers ADS del tema mixto traen DOI. Sólo los papers de
    # ESTE tema (--slug: sources + extra_core); el barrido completo es pasada periódica (maintain).
    if any(s.get("doi") for s in sources) or extra:
        if run("check_retractions.py", "--slug", slug):
            sys.exit("check_retractions detectó papers retractados — revisá las notas marcadas "
                     "(el lint las surface como bloqueante).")


def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="tema de vault/config/topics.yaml")
    ap.add_argument("--force", action="store_true",
                    help="re-bajar/re-copiar FUENTES ya presentes (snapshot/PDF/fulltext); nunca pisa notas")
    ap.add_argument("--yes", action="store_true",
                    help="continuar a sabiendas si la guardia de expansión frena la cadena (el pool "
                         "core se multiplicó respecto de lo ya ingestado)")
    args = ap.parse_args()

    try:
        _, meta = cfg.topic_by_slug(args.slug)
    except KeyError as e:
        sys.exit(str(e))
    source = meta.get("source") or "ads"
    if source == "ads":
        if meta.get("sources"):
            cfg.print_seguro("  ⚠ la entrada tiene `sources:` pero source: ads — la lista se ignora en modo ADS.")
        if args.force:
            cfg.print_seguro("  ⚠ --force no aplica al modo ads (corré el script puntual con --force si hace falta).")
        ingest_ads(args.slug, args.yes)
    elif source in OFFADS_KINDS:
        ingest_offads(args.slug, {**meta, "source": source}, args.force)
    else:
        sys.exit(f"source desconocido en '{args.slug}': {source!r} "
                 f"(válidos: ads | {' | '.join(OFFADS_KINDS)}).")
    # Mismo criterio que en ingest_star: el hand-off nombra los pasos salteables con su número.
    # El contraste (3c, #72) faltaba, y es el que decide si la síntesis mira un paper o todos.
    cfg.print_seguro("\nCadena mecánica lista. Siguiente (LLM, skill ingest-topic): extracción por paper (3) → "
          "retro-tag por aliases (3b) → CONTRASTE cross-paper / inventario por eje (3c) → síntesis "
          "del concept, con régimen de validez (4) → verify-citations (6b) → lint.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
