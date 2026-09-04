"""Orquestador de la cadena mecánica de ingest-theme: despacha según `source` del tema.

Uso:
    python scripts/ingest_theme.py <slug> [--force] [--yes]

Lee la entrada del tema en vault/config/themes.yaml y corre la cadena que corresponda a su
campo `source` (formaliza el modo off-ADS del skill ingest-theme en el tooling):

- `ads` (default si el campo falta): cadena astro estándar —
  query_ads --theme → [guardia de expansión] → fetch_arxiv → fetch_pdf → make_notes --theme →
  extract_fulltext → check_retractions. La **guardia de expansión** (#37) frena entre la query y
  el primer paso que gasta red y disco si el core se multiplicó respecto de lo ya ingestado
  (default ×1.5 y 50 o más nuevos); `--yes` continúa a sabiendas.
- `web` | `local-pdfs` | `local-pdfs+web`: modo off-ADS. La bibliografía se declara en la
  lista `sources:` de la entrada (cada item: `key` = clave de cita sintética AAAA+Autor +
  `url` (fuente web) o `pdf` (ruta a un PDF provisto por el usuario) + metadata opcional
  `title/author/year/venue/n_authors/doi`). El orquestador stubbea el concept, procesa cada
  fuente (`fetch_web.py` para URLs; copia a raw/pdfs/<slug>/<key>.pdf para PDFs) y corre
  extract_fulltext. Tras copiar un PDF, el orquestador **PROPONE** repuntar el campo `pdf`
  del item a la copia de la bóveda (`vault/raw/pdfs/<slug>/<key>.pdf`, repo-relative) e
  imprime la línea exacta: **aplicarlo es del operador** (AUD-160 — la config es curada y
  versionada; un script que la edita solo convierte una decisión en un efecto colateral,
  misma regla que `triage.accept_source` y `discover.resolve_pdf`). Hacerlo importa: el path
  declarado suele ser staging efímero (scratchpad/descargas) que muere y deja un puntero roto
  en themes.yaml. ⚠ Hasta 1.127.x este párrafo decía que el repunte era automático mientras el
  docstring de la propia función, 145 líneas abajo, decía lo contrario — y un agente que sigue
  la doc no lo hace (#299: 8 de 8 fuentes sin repuntar en una corrida real).
  Rutas `pdf` relativas se resuelven
  contra la raíz del repo (portable entre máquinas). Sin query_ads / fetch_ground_truth (no aplican fuera de ADS);
  check_retractions SÍ corre cuando algún item declara `doi` (Crossref lo cubre igual).
  **Tema MIXTO:** un tema off-ADS puede además traer papers del tema que SÍ están en ADS (un
  método no-astro casi siempre tiene aplicaciones publicadas en revista astro), por dos vías que
  se excluyen entre sí, la primera con prioridad:
    · `query:` poblada (#104) → **descubrimiento ADS completo** (query_ads --theme → fetch_arxiv →
      fetch_pdf → make_notes --theme), con la misma lente, las mismas puertas de D-26 y la misma
      compuerta de triage que un tema `source: ads`. Sin esto, off-ADS le quitaba el descubrimiento
      automático a la mitad del tema que ADS sí indexa, y la única salida era enumerar bibcodes.
    · sólo `extra_core:` (lista de mapas, D-58) → sub-cadena acotada (query_ads --extra-only → …).
  En los dos casos: metadata ADS real, sin blockquote off-ADS. `extra_core` sigue siendo el
  override del clasificador y vale con o sin `query:`.

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
retro-tag) NO es de este script: la hace el agente siguiendo el skill ingest-theme.
"""
from __future__ import annotations

import argparse
import json
import re
import os
import subprocess
import sys
from pathlib import Path

import lib_config as cfg
import discover
import make_notes
from fetch_web import CITEKEY_RE

# valores válidos de `source` (ausente = "ads"); los combinados permiten mezclar url/pdf en sources
OFFADS_KINDS = {"web": ("url",), "local-pdfs": ("pdf",),
                "local-pdfs+web": ("url", "pdf"), "web+local-pdfs": ("url", "pdf")}


def _listify_curado(v, campo: str):
    """Normaliza un campo de CURACIÓN MANUAL (`extra_core`) que `themes.yaml` instruye editar a
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


def run(script: str, *args: str, flags=()) -> int:
    """Corre un script de la cadena con el mismo intérprete (rutas absolutas vía lib_config).

    Exporta `ALMAGESTO_VIA=orquestador` para que el paso —que se estampa a sí mismo en `cadena:`
    del registro (R-6/D-57)— sepa distinguirse de una corrida suelta. Va por entorno y no por flag
    porque tiene que atravesar el `subprocess.run` sin tocarle el CLI a cada script.

    `flags` son las **escotillas del orquestador** (INV-44): `--yes` saltea la guardia de expansión
    y por lo tanto cambia lo que la cadena hizo, pero no es flag de ningún paso, así que no llegaba
    a ninguna entrada de `cadena:` — la escotilla con más consecuencias era la única sin traza. Va
    por el mismo canal y se estampa con prefijo `orquestador:`."""
    cfg.print_seguro(f"\n→ {script} {' '.join(args)}")
    env = {**os.environ, cfg.VIA_ENV: "orquestador"}
    if flags:
        env[cfg.FLAGS_ENV] = " ".join(flags)
    return subprocess.run([sys.executable, str(cfg.ROOT / "scripts" / script), *args],
                          cwd=cfg.ROOT / "scripts", env=env).returncode


def _cierre_retracciones(slug: str) -> None:
    """Cierre de cadena: chequeo de retracciones de ESTE ingest, distinguiendo los tres códigos
    (issue 0.1). `1` = hay retractados (revisar las notas marcadas). `2` = el chequeo **no pudo
    correr** — aborta igual, porque la cadena no certifica lo que no miró, pero sin la frase falsa
    "detectó papers retractados", que mandaba al operador a buscar marcas inexistentes."""
    rc = run("check_retractions.py", "--slug", slug)
    if rc == 1:
        sys.exit("check_retractions detectó papers retractados — revisá las notas marcadas "
                 "(el lint las surface como bloqueante).")
    if rc:
        sys.exit(f"check_retractions no pudo chequear (rc={rc}) — la cadena no certifica lo que no "
                 "miró. Revisá el motivo que imprimió arriba y re-corré (es idempotente).")


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
          "    relevance.min_facets: N             # ≥N facetas cualesquiera\n"
          "  en vault/config/objective.yaml (skill setup). Después re-corré query_ads.py para "
          "re-clasificar — todavía no se bajó nada.")
    if not yes:
        sys.exit(f"cadena frenada antes de bajar {len(nuevos)} papers. Para continuar a sabiendas: "
                 f"--yes (el ads.json ya quedó regenerado; nada más se tocó).")
    cfg.print_seguro("  → --yes: sigo con la expansión a sabiendas.")


def repoint_source_pdf(key: str, declared: str, dest: Path) -> None:
    """PROPONE repuntar `sources[].pdf` a la copia versionada de la bóveda (repo-relative).

    El path declarado suele ser staging efímero (scratchpad, carpeta de descargas): al limpiarse
    deja un puntero muerto en `themes.yaml`. Tras la copia, la que vale es la de la bóveda.

    ⛔ AUD-160 — hasta 1.73.0 esto **reescribía `themes.yaml` solo**, contra la doctrina que el
    propio framework escribe dos veces: `triage.accept_source` («no escribe `themes.yaml`: la config
    es curada y versionada, y un script que la edita solo convierte una decisión en un efecto
    colateral») y `discover.resolve_pdf` en `CLAUDE.md` («propone una URL y para: no edita
    `sources:` — cambiar en silencio una fuente declarada por una que adivinó un script es cómo una
    cita termina apuntando a un documento que nadie abrió»). Tres sitios, la misma regla, y éste era
    el que no la cumplía. Hoy imprime la línea exacta y para."""
    if not dest.exists():
        return
    rel = dest.relative_to(cfg.ROOT).as_posix()
    if declared == rel:
        return
    cfg.print_seguro(
        f"  · {key}: el PDF quedó versionado en `{rel}` y `sources[].pdf` sigue apuntando a "
        f"`{declared}` (staging efímero: cuando se limpie, queda un puntero muerto). Repuntalo a "
        f"mano en `vault/config/themes.yaml`:\n"
        f"        pdf: {rel}")


def ingest_ads(slug: str, yes: bool = False) -> None:
    """Cadena astro estándar (paso 2 del skill ingest-theme), abortando al primer fallo."""
    escotillas = ["--yes"] if yes else []          # INV-44: la escotilla del orquestador deja traza
    for script, args in (("query_ads.py", ["--theme", slug]),
                         ("fetch_arxiv.py", [slug]),
                         ("fetch_pdf.py", [slug]),      # los sin arXiv, vía resolver ADS (esources)
                         ("make_notes.py", ["--theme", slug]),
                         ("extract_fulltext.py", [slug])):
        rc = run(script, *args, flags=escotillas)
        if rc:
            sys.exit(f"{script} falló (rc={rc}) — cadena abortada. La cadena es idempotente: "
                     "corregí y re-corré ingest_theme.py (lo ya bajado no se re-baja).")
        if script == "query_ads.py":       # checkpoint ANTES del primer paso que gasta red y disco
            expansion_guard(slug, yes)
    # cierre: sólo los papers de ESTE ingest (el barrido completo es pasada periódica — maintain);
    # exit 1 acá significa "detectó papers retractados", no un fallo de la cadena
    _cierre_retracciones(slug)


def ingest_offads(slug: str, meta: dict, force: bool) -> None:
    """Modo off-ADS: concept stub + una fuente por item de `sources:` (web o PDF local)."""
    for k in ("area", "concept"):
        if not meta.get(k):
            sys.exit(f"la entrada '{slug}' no tiene `{k}` en themes.yaml (requerido para el concept).")
    # `cfg.as_list`, no `or []`: `sources:` es un archivo de instancia editado a mano y un escalar
    # truthy (una sola fuente sin corchetes) no caía en el `or` — esquivaba el `sys.exit` amable
    # de abajo y moría más adelante con `AttributeError` sin decir qué corregir (R6). Acá SÍ
    # conviene degradar a `[]` (no adivinar un elemento): el mensaje de abajo ya explica el formato
    # correcto (`sources:` con items `key + url|pdf`), y un escalar no alcanza para reconstruir eso.
    sources = cfg.as_list(meta.get("sources"))
    # #211 — el guard viejo abortaba con `sources:` vacía, o sea medía la premisa que #104 rompió
    # (off-ADS ⇒ hay `sources:`). Un tema MIXTO con `query:` poblada y las fuentes todavía sin
    # declarar es el caso NORMAL al empezar: el paso 0b del skill manda barrer los tres backends
    # ANTES de declarar nada a mano, y el anclaje —lo que más rinde— necesita la mitad ADS ya
    # bajada. Con el guard viejo eso era un deadlock: para declarar bien las fuentes hacía falta
    # el anclaje, para el anclaje la mitad ADS, y para la mitad ADS haber declarado las fuentes.
    # Se aborta cuando el tema no tiene NINGUNA vía de papers, no cuando le falta una de tres.
    extra = [e["bibcode"] for e in cfg.load_extra_core(meta, entry=slug)]
    if not sources and not meta.get("query") and not extra:
        sys.exit(f"'{slug}' es off-ADS (source: {meta.get('source')}) y no tiene ninguna vía de "
                 "papers: ni `sources:` (bibliografía declarada: items con key + url|pdf; ver "
                 "header del YAML), ni `query:` (mitad ADS del tema mixto), ni `extra_core:` "
                 "(bibcodes ADS curados). Declará al menos una en themes.yaml.")
    if not sources:
        # No callarlo: sin este aviso la corrida se lee como "corrió todo" cuando corrió la mitad.
        cfg.print_seguro(f"  ⚠ `{slug}`: tema mixto SIN fuentes declaradas todavía → corro sólo la "
                         f"mitad ADS ({'query' if meta.get('query') else 'extra_core'}). Las "
                         f"fuentes off-ADS se declaran después en `sources:` (paso 0b del skill: "
                         f"barré los backends primero, la lista a mano es el último recurso).")
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
            # D-52: volver a declarar la fuente ES cambiar de opinión — la decisión se ANULA
            # (preservando el motivo viejo en `previa`) en vez de quedar contradiciendo lo hecho.
            # Antes esto sólo avisaba y le pedía al usuario que editara el YAML a mano: el registro
            # quedaba diciendo "descartada por X" sobre una fuente que está ingestada.
            cfg.anular_decision(slug, dk, por="sources", carril="fuente-declarada")
            cfg.print_seguro(f"  ↩ {key}: figuraba DESCARTADA en el registro ({d.get('fecha', 's/f')}"
                  f"{'' if dk == key else f', por url {dk}'}): "
                  f"{d.get('motivo') or '(sin motivo)'} — volver a declararla la revierte: decisión "
                  f"ANULADA (el motivo viejo queda en `previa`)")
        # #80: unidad de cita y alcance — se validan para TODA fuente, conseguida o pendiente.
        _unidad = str(s.get("unidad_cita") or "linea").strip()
        if _unidad not in cfg.UNIDAD_CITA_OK:
            sys.exit(f"{key}: `unidad_cita: {_unidad}` fuera del vocabulario "
                     f"({' | '.join(cfg.UNIDAD_CITA_OK)}). Un typo deja al verificador sin saber "
                     f"cómo citar esta fuente.")
        _alcance = str(s.get("alcance") or "").strip()
        if _unidad != "linea" and not _alcance:
            sys.exit(f"{key}: `unidad_cita: {_unidad}` sin `alcance`. Si la unidad no es la línea es "
                     f"un documento largo, y casi nunca entra entero: declará qué parte entró "
                     f"(p. ej. `alcance: caps. 6 y 15`). Sin eso, el chequeo de completitud de "
                     f"verify-citations no puede distinguir un recorte deliberado de una omisión.")
        if s.get("pending"):
            _pend = str(s["pending"]).strip()
            if _pend not in cfg.PENDING_OK:
                sys.exit(f"{key}: `pending: {_pend}` fuera del vocabulario "
                         f"({' | '.join(cfg.PENDING_OK)}). Un valor que nadie valida deja al "
                         f"consumidor leyendo algo que no significa nada.")
            if not str(s.get("pending_motivo") or "").strip():
                sys.exit(f"{key}: `pending: {_pend}` sin `pending_motivo`. En seis meses la "
                         f"categoría sola no dice si la fuente se pidió, se descartó o se olvidó — "
                         f"escribí qué pasa con esta fuente y quién la consigue.")
            # Fuente no-conseguible declarada: NO se fetchea ni cuenta como fallo — stub con
            # pending_source (url/doi quedan como puntero) y derivación al usuario en el aviso final.
            make_notes.write_web_paper_note(key, url=s.get("url"), slug=slug, concept=concept,
                                            title=s.get("title"), first_author=s.get("author"),
                                            year=s.get("year"), n_authors=s.get("n_authors"),
                                            doi=s.get("doi"), venue=s.get("venue"),
                                            pending=_pend,
                                            pending_motivo=str(s["pending_motivo"]).strip(),
                                            unidad_cita=_unidad, alcance=_alcance or None)
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
                cfg.copy_file_atomic(src, dest)
                cfg.print_seguro(f"{key}: {src.name} → {dest}")
            repoint_source_pdf(key, str(s["pdf"]), dest)
            n_pdf += 1     # sólo cuenta PDFs presentes en disco (un item fallido no dispara extract)
            # stub de nota (idempotente; detecta solo el PDF copiado y linkea el campo `pdf`)
            make_notes.write_web_paper_note(key, slug=slug, concept=concept,
                                            title=s.get("title"), first_author=s.get("author"),
                                            year=s.get("year"), n_authors=s.get("n_authors"),
                                            doi=s.get("doi"), venue=s.get("venue"),
                                            unidad_cita=_unidad, alcance=_alcance or None)
            # #367 — la rama «crear el stub» es la única que linkeaba `pdf:`, y en este carril
            # cerrar un `pending` es el caso NORMAL: la nota ya existe desde la corrida anterior,
            # así que esa rama no se toma nunca y la nota quedaba con `pdf: null` y el PDF en disco
            # (medido: 1 de 1). `stamp_pdf` es la única definición de «`pdf:` lo escribe la verdad
            # de disco, lo escriba quien lo escriba» (#304), y este depositante no la llamaba.
            make_notes.stamp_pdf(cfg.PAPERS / f"{make_notes.safe_name(key)}.md",
                                 make_notes.safe_name(key))
    # Tema MIXTO: un método no-astro casi siempre tiene alguna aplicación/variante publicada en
    # revista astro — papers con bibcode ADS real. Van en `extra_core:` (no en `sources:`, que
    # degradaría el stub: clave sintética, citation_count 0, blockquote off-ADS falso) y para
    # ellos corre la sub-cadena ADS. Antes extra_core se ignoraba acá en silencio.
    # `_listify_curado`, no `or []`: gemelo de query_ads.py:910 (R13) — un `extra_core: <bibcode>`
    # sin corchetes (un solo paper con bibcode ADS en un tema mixto) es truthy y no caía en el
    # `or`; la comprensión de abajo recorría el string letra por letra y el bibcode real nunca
    # entraba a la sub-cadena ADS: la curación manual se perdía en silencio.
    # (`extra` se calcula arriba, junto al guard de #211 que lo necesita.)
    # #104 — un tema MIXTO puede además declarar `query:`. Sin ella la mitad astro entra SÓLO por
    # los bibcodes que el operador enumeró a mano (`--extra-only`), o sea el modo off-ADS le quitaba
    # el descubrimiento automático a la mitad del tema que ADS sí indexa. Medido en el ingest de
    # ICA: la enumeración manual trajo 11 papers y dejó afuera familias enteras que la query
    # encuentra sola. Con `query:` poblada corre la búsqueda completa (misma lente, mismas puertas
    # de D-26, misma compuerta de triage) y `extra_core` sigue siendo el override de siempre.
    if meta.get("query"):
        cfg.print_seguro(f"\nquery declarada en un tema off-ADS (tema mixto, #104) → descubrimiento ADS completo")
        for script, sargs in (("query_ads.py", ["--theme", slug]),
                              ("fetch_arxiv.py", [slug]),
                              ("fetch_pdf.py", [slug]),
                              ("make_notes.py", ["--theme", slug])):
            rc = run(script, *sargs)
            if rc:
                sys.exit(f"{script} falló (rc={rc}) — cadena abortada. La cadena es idempotente: "
                         "corregí y re-corré ingest_theme.py (lo ya bajado no se re-baja).")
    elif extra:
        cfg.print_seguro(f"\nextra_core: {len(extra)} paper(s) con bibcode ADS (tema mixto) → sub-cadena ADS")
        for script, sargs in (("query_ads.py", ["--theme", slug, "--extra-only"]),
                              ("fetch_arxiv.py", [slug]),
                              ("fetch_pdf.py", [slug]),
                              ("make_notes.py", ["--theme", slug])):
            rc = run(script, *sargs)
            if rc:
                sys.exit(f"{script} falló (rc={rc}) — cadena abortada. La cadena es idempotente: "
                         "corregí y re-corré ingest_theme.py (lo ya bajado no se re-baja).")
    extract_rc = 0
    # #211 — `query` entra a la condición: la mitad ADS del tema mixto baja PDFs con `fetch_pdf`
    # y su extracción sale por acá. Sin esto, un tema mixto con `query:` y sin `extra_core:` ni
    # PDFs locales (el caso normal en la primera corrida) bajaba el corpus y NO lo extraía.
    if n_pdf or extra or meta.get("query"):
        # el rc de extract se reporta aparte: un fallo de extracción NO es una "fuente fallida"
        # (contarlo ahí inflaba el conteo del aviso final)
        extract_rc = run("extract_fulltext.py", slug, *(["--force"] if force else []),
                         flags=(["--force"] if force else []))
    # Aviso claro al operador (issue #7): qué fuentes faltan y con qué puntero, para que el
    # usuario las provea. Las pendientes NO son fallos (la cadena degrada limpio y sigue).
    if pending_items:
        cfg.print_seguro("\n⏳ Fuentes PENDIENTES (derivadas al usuario — no frenan la cadena):")
        for key, why, ptr in pending_items:
            cfg.print_seguro(f"  - {key} [{why}] → {ptr}")
            # #104 — encontrar no es conseguir: `pending` decía QUÉ falta y nunca DÓNDE buscarlo,
            # así que el operador salía a googlear a mano lo que dos APIs contestan. Propone una
            # URL; NO toca `sources:` (pisar una fuente declarada con una que adivinó un script es
            # cómo una cita termina apuntando a un documento que nadie abrió).
            # ⛔ #123: NO para `adquisicion`. Ahí la fuente no "falta": el usuario declaró que la
            # está consiguiendo él (un libro, una copia física), así que consultar dos APIs en cada
            # corrida de la cadena es latencia por algo que ya se resolvió — y la propuesta no puede
            # servir para nada, porque no hay copia libre que buscar. Para los otros tres valores sí
            # tiene sentido: describen un fallo, y encontrar no es conseguir.
            # @inv INV-114
            doi = ptr if str(ptr).startswith("10.") else None
            if doi and why != "adquisicion":
                url, _why = discover.resolve_pdf(doi)
                if url:
                    cfg.print_seguro(f"      ↳ copia libre candidata: {url}")
                    cfg.print_seguro("        (revisala y, si sirve, poné `url:`/`pdf:` en el item)")
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
    if any(s.get("doi") for s in sources) or extra or meta.get("query"):
        _cierre_retracciones(slug)
    else:
        # AUD-159 — esto se salteaba **en silencio**, y el silencio se lee como «corrió y está
        # limpio». La cadena cierra igual (sin DOI ni bibcode no hay a quién preguntarle a
        # Crossref: es una propiedad de las fuentes, no un fallo), pero un paso de la cadena que no
        # corrió tiene que decirlo — misma doctrina que D-43 y que el `rc 2` de `check_retractions`
        # cuando su población queda vacía.
        cfg.print_seguro(
            f"  ⚠ chequeo de retracciones NO EVALUADO para `{slug}`: ninguna fuente declara "
            f"`doi` ni hay `extra_core`, así que no hay clave que consultarle a Crossref. La "
            f"frontera dura queda sin vigilancia acá — completá los `doi` que existan, o "
            f"cubrilo con la pasada periódica (`python scripts/check_retractions.py`).")


def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser(
        description="Orquesta la cadena de ingesta de un TEMA según su `source` (ads | web | local-pdfs [+web]). El ORDEN CANÓNICO de la cadena vive en el header de este archivo, que es su fuente de verdad. Idempotente: re-correrlo no re-baja lo que ya está ni pisa notas.",
        epilog="Exit != 0 aborta la cadena: corregí y volvé a correr (es idempotente).")
    ap.add_argument("slug", help="tema de vault/config/themes.yaml")
    ap.add_argument("--force", action="store_true",
                    help="re-bajar/re-copiar FUENTES ya presentes (snapshot/PDF/fulltext); nunca pisa notas")
    ap.add_argument("--yes", action="store_true",
                    help="continuar a sabiendas si la guardia de expansión frena la cadena (el pool "
                         "core se multiplicó respecto de lo ya ingestado)")
    args = ap.parse_args()

    try:
        _, meta = cfg.theme_by_slug(args.slug)
    except KeyError as e:
        sys.exit(str(e))
    source = meta.get("source") or "ads"
    if source == "ads":
        if meta.get("sources"):
            # #78: antes esto AVISABA y seguía, o sea descartaba bibliografía declarada por el
            # usuario — y el fundamento canónico de un método casi nunca está en ADS, que es
            # justamente lo que `sources:` existe para traer. Un aviso que no frena se pierde en el
            # scroll y la cadena cierra «bien» con la mitad de la bibliografía afuera.
            # La capacidad ya existe en la otra dirección desde #104: un tema off-ADS con `query:`
            # poblada corre el descubrimiento ADS COMPLETO (misma lente, mismas puertas de D-26,
            # misma compuerta de triage). Así que acá no falta una feature: falta dejar de tragarse
            # la lista y decir qué escribir.
            # @inv INV-123
            sys.exit(
                f"'{args.slug}': la entrada declara `source: ads` y además `sources:` "
                f"({len(cfg.as_list(meta.get('sources')))} fuente(s)) — en modo ADS esa lista NO se "
                f"procesa, así que se estaría perdiendo bibliografía que declaraste.\n"
                f"  Para un tema MIXTO (fundamentos declarados + aplicaciones astro descubiertas), "
                f"poné `source: local-pdfs+web` (o `web` / `local-pdfs` según de dónde salgan tus "
                f"fuentes) y dejá la `query:` como está: la mitad ADS se sigue descubriendo igual, "
                f"con la misma lente y la misma compuerta de triage (#104).")
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
    cfg.print_seguro("\nCadena mecánica lista. Siguiente (LLM, skill ingest-theme): una VISTA por paper "
          f"(3, #188) + `python scripts/harvest_views.py {args.slug} --theme` → "
          "retro-tag por aliases (3b) —deja RECLAMOS, no lecturas— → CONTRASTE cross-paper / "
          "inventario por eje (3c) → síntesis del concept, con régimen de validez (4) → "
          "verify-citations (6b) → lint.")
    return 0


if __name__ == "__main__":
    cfg.cli_exit(main)
