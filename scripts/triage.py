"""Compuerta de triage de los candidatos del citation chaining (#38).

Uso:
    python scripts/triage.py <slug>                                   # listar los candidatos pendientes
    python scripts/triage.py <slug> --report                          # + tabla en outputs/triage-<slug>.md
    python scripts/triage.py <slug> --drop <bib> [<bib> …] --reason "<motivo>"
    python scripts/triage.py <slug> --drop-source <clave> […] --reason "<motivo>" [--pointer <url|doi>]
    python scripts/triage.py <slug> --migrate                 # consolidar el triage.json pre-1.9.0

El chaining trae papers conectados por citas al corpus del sujeto. La lente
(`relevance.topics`) clasifica **tema**, no **pertinencia al sujeto**: anclado a "menciona al
sujeto en el fulltext", el grafo trae cualquier paper del área que tabule la estrella una vez
(medido: 18% de precisión en los core nuevos del grafo — incluyendo una tesis de física de
partículas como "core" de AU Mic). Y la pertinencia **no** es sintáctica: ni el título ni la
densidad de mención la aproximan (los papers ruido nombran al sujeto 27 veces de mediana; los
valiosos, 2). Por eso el juicio tiene lugar propio en la cadena, ANTES de gastar red y disco.

Los tres niveles:
- **0 — entra solo:** core de la query directa, `extra_core`, y los candidatos del chaining con el
  sujeto en el **título** (1 falso positivo en 310). Lo resuelve `query_ads` solo.
- **1 — juicio del LLM (sin bajar nada):** el resto queda en `candidates` de
  `build/<slug>/ads.json`. Este script los lista con título+abstract+vía+citas; el agente
  (paso 2c del skill `ingest-star`) los clasifica pertinente / ruido / dudoso.
  Las decisiones **persisten y viajan en git**: aceptado → `extra_core` en `stars.yaml` (override
  del clasificador, #39); descartado → `decisiones` de `vault/config/registro/<slug>.yaml` (con
  motivo y fecha) para que el próximo refresh no lo vuelva a proponer. Los dos lados del juicio
  viven en config versionada (#51): hasta 1.8.x el descarte iba a `build/<slug>/triage.json`
  —scratch gitignored— y en otra máquina el triage volvía a proponer todo lo descartado, sin el
  motivo. Ese archivo viejo **ya no se lee** (sin capas de compatibilidad: son complejidad permanente
  en el lector): se consolida con `--migrate`, y mientras exista el **lint lo reporta como
  bloqueante** — que quede mudo sería justamente el bug que #51 arregló.
  Los candidatos que **ya tienen nota** en la bóveda (entraron por OTRO slug —
  papers de método curados a otra estrella) se marcan `◆` (#42): ya están bajados y extraídos, la
  decisión sigue siendo por-slug pero se despachan rápido — no se filtran, se etiquetan.
- **2 — informe al usuario:** `--report` deja la tabla en `outputs/triage-<slug>.md` (título, año,
  citas, vía, tópicos, link a ADS) para decidir los **dudosos** por lote.

**El otro carril de curación: las fuentes DECLARADAS (`--drop-source`, #81).** En un tema off-ADS
no hay descubrimiento —la bibliografía se declara una por una en `sources:` de `topics.yaml`—, así
que ahí `sources:` registra lo aceptado y el rechazo ("miré este libro / esta URL y decidí que no es
core") no quedaba en ningún lado. Es la misma asimetría de #51 en el otro carril: el juicio de
rechazo es tan **no regenerable** como el del triage y se perdía igual al cambiar de máquina o al
volver seis meses después. `--drop-source` lo escribe en las MISMAS `decisiones` del registro
versionado (no inventa mecanismo), con `origen: fuente-declarada` para distinguir el carril y un
`fuente:` opcional (url/doi/ruta), que es lo que vuelve resoluble una clave sintética. No necesita
`build/<slug>/ads.json`: un tema off-ADS puro no lo tiene. Lo consume `ingest_topic`, que **avisa**
si un item de `sources:` lleva una clave ya descartada — el equivalente de "no re-proponer".

Este script NO decide: lista y persiste. El juicio es del agente/usuario.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

import lib_config as cfg

ADS_URL = "https://ui.adsabs.harvard.edu/abs/"


def load_ads(slug: str) -> dict:
    f = cfg.ROOT / "build" / slug / "ads.json"
    if not f.exists():
        sys.exit(f"no existe build/{slug}/ads.json — corré primero la cadena de ingest "
                 f"(o python scripts/query_ads.py {slug}).")
    return json.loads(f.read_text(encoding="utf-8"))


def triage_file(slug: str):
    """Dónde vive el juicio: el registro VERSIONADO del sujeto (#51). Antes era
    `build/<slug>/triage.json` —scratch gitignored—, así que en otra máquina (o tras limpiar
    build/) el triage re-proponía todo lo descartado y el motivo se perdía con el archivo."""
    return cfg.registro_path(slug)


def load_decisions(slug: str) -> dict:
    """Decisiones del registro versionado. El `triage.json` pre-1.9.0 NO se lee acá: se migra con
    `--migrate` y, mientras exista, el lint lo reporta como bloqueante."""
    return cfg.load_decisiones(slug)


def save_decisions(slug: str, decisiones: dict) -> None:
    """Escribe SIEMPRE en el registro versionado; `busqueda` (de query_ads) se preserva. Lo que
    venía del legacy entra por `--migrate`, que es el único camino."""
    cfg.save_decisiones(slug, decisiones)


def drop(slug: str, bibcodes: list[str], reason: str) -> int:
    """Persiste el descarte de candidatos (no se re-proponen en el próximo refresh)."""
    pendientes = {c["bibcode"] for c in cfg.as_list(load_ads(slug).get("candidates"))}
    desconocidos = [b for b in bibcodes if b not in pendientes]
    if desconocidos:
        cfg.print_seguro(f"  ⚠ {len(desconocidos)} bibcode(s) no están entre los candidatos pendientes "
              f"(¿ya decididos, o typo?): {', '.join(desconocidos)}")
    decisiones = load_decisions(slug)
    hoy = dt.date.today().isoformat()
    for b in bibcodes:
        # Los dos carriles (chaining acá, fuente-declarada en `drop_source`) comparten el mismo
        # espacio de claves en `decisiones`: pisar sin avisar borra en silencio el `motivo` y el
        # `origen` de un juicio anterior — justo lo que #51 existe para que no se pierda. Mismo
        # aviso que su hermano `drop_source`, para que los dos carriles se comporten igual.
        if (previa := decisiones.get(b)):
            cfg.print_seguro(f"  ⚠ {b} ya tenía decisión ({previa.get('decision', '?')}, "
                  f"{previa.get('origen') or 'chaining'}, {previa.get('fecha', 's/f')}): "
                  f"{previa.get('motivo') or '(sin motivo)'} — la piso con ésta")
        decisiones[b] = {"decision": "descartado", "motivo": reason, "fecha": hoy}
    save_decisions(slug, decisiones)
    cfg.print_seguro(f"  {len(bibcodes)} candidato(s) descartados en {triage_file(slug)} — motivo: {reason}")
    cfg.print_seguro("  (versionado: se commitea y viaja entre máquinas, como `extra_core` — los dos lados "
          "de la decisión sobreviven al clon)")
    cfg.print_seguro("  (los aceptados NO van acá: van a `extra_core` en stars.yaml, curación persistente)")
    return 0


def drop_source(slug: str, claves: list[str], reason: str, pointer: str | None) -> int:
    """Persiste el rechazo de una fuente DECLARADA de un tema off-ADS (#81).

    Hermano de `drop()` en el otro carril de curación, con dos diferencias que salen del carril, no
    del capricho: (a) no hay lista de pendientes contra la cual validar —las fuentes off-ADS no se
    descubren, se declaran—, así que tampoco hay `build/<slug>/ads.json` que leer; (b) la clave es
    sintética (`AAAA+Autor`) o directamente una URL, así que se guarda el `fuente:` que la vuelve
    resoluble dentro de seis meses. Misma forma que el descarte del triage: la decisión vive en
    `decisiones` del registro versionado y viaja en git."""
    # El sujeto tiene que EXISTIR: `drop()` lo valida de rebote (muere en `load_ads` si no hay
    # ads.json), este carril no leía nada, así que un typo en el slug escribía un registro huérfano
    # que nadie lee jamás — el juicio se pierde en silencio, que es lo que #81 existe para impedir.
    try:
        cfg.topic_by_slug(slug)
    except KeyError:
        try:
            cfg.star_by_slug(slug)
        except KeyError:
            sys.exit(f"slug desconocido: '{slug}' — no está en topics.yaml ni en stars.yaml. "
                     f"El registro de un sujeto que no existe no lo lee nadie.")
    limpias = list(dict.fromkeys(k.strip() for k in claves if k and k.strip()))
    if not limpias:
        sys.exit("--drop-source necesita al menos una clave no vacía.")
    reason = reason.strip()
    if not reason:
        sys.exit("--drop-source necesita un --reason con contenido (no espacios).")
    decisiones = load_decisions(slug)
    hoy = dt.date.today().isoformat()
    for k in limpias:
        if (previa := decisiones.get(k)):
            cfg.print_seguro(f"  ⚠ {k} ya tenía decisión ({previa.get('decision', '?')}, "
                  f"{previa.get('origen') or 'chaining'}, {previa.get('fecha', 's/f')}): "
                  f"{previa.get('motivo') or '(sin motivo)'} — la piso con ésta")
        decisiones[k] = {"decision": "descartado", "motivo": reason, "fecha": hoy,
                         "origen": "fuente-declarada",
                         **({"fuente": pointer.strip()} if pointer and pointer.strip() else {})}
    save_decisions(slug, decisiones)
    cfg.print_seguro(f"  {len(limpias)} fuente(s) declarada(s) descartada(s) en {triage_file(slug)} — "
          f"motivo: {reason}")
    if not pointer:
        cfg.print_seguro("  (sin --pointer: la clave queda sin url/doi que la resuelva — conviene pasarlo)")
    cfg.print_seguro("  (versionado: se commitea y viaja. `ingest_topic` avisa si volvés a declarar esta "
          "clave en `sources:`)")
    return 0


def migrate(slug: str) -> int:
    """Consolida en el registro VERSIONADO las decisiones que hayan quedado en el
    `build/<slug>/triage.json` de una bóveda pre-1.9.0 (#51).

    Es el **único** camino: el lector no mergea el archivo viejo (sin capas de compatibilidad), así
    que mientras no se corra esto el juicio sigue viviendo únicamente en scratch gitignored y un
    clon en otra máquina lo pierde — exactamente el bug que #51 arregla. Por eso el lint lo reporta
    como bloqueante. Idempotente: ante el mismo bibcode gana lo ya versionado, y si no hay nada que
    migrar no escribe."""
    legacy = cfg.legacy_triage_path(slug)
    if not legacy.exists():
        cfg.print_seguro(f"{slug}: no hay {legacy} — nada que migrar "
              f"(el juicio nuevo ya se escribe en {cfg.registro_path(slug)}).")
        return 0
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        sys.exit(f"{legacy} no se pudo leer ({type(e).__name__}) — revisalo a mano antes de migrar.")
    if not isinstance(data, dict):
        sys.exit(f"{legacy} no es un objeto JSON (es {type(data).__name__}) — revisalo a mano.")
    # `"decisiones" not in data` (no `.get(...) or {}`) porque acá SÍ hace falta distinguir "no
    # tiene la clave" de "la tiene vacía": lo primero es un triage.json que este migrador no sabe
    # leer (no consolidó nada, no toca borrar); lo segundo es un legado sin decisiones pendientes,
    # que sigue siendo un migrar-y-borrar legítimo.
    if "decisiones" not in data:
        cfg.print_seguro(f"{slug}: {legacy} no tiene la clave 'decisiones' — no es el formato que este "
              f"migrador consolida, así que no se leyó ni se migró nada. Lo dejo: si es scratch "
              f"viejo sin valor, borralo a mano; si trae un juicio en otra forma, migralo primero "
              f"a `decisiones` y volvé a correr `--migrate`.")
        return 1
    viejas = data["decisiones"] or {}
    # `cfg.load_decisiones`, no un `.get(...) or {}` propio: el registro es el ÚNICO artefacto no
    # regenerable de la bóveda y el framework instruye editarlo a mano — una `decisiones:` escalar
    # (edición a mano rota) es YAML válido. `cfg.load_decisiones` ya trae el `isinstance` que hace
    # falta (lib_config:412); duplicar el lector acá es donde vivía el defecto (R15): con `ya`
    # escalar, `b not in ya` se volvía un substring match silencioso y `{**viejas, **ya}` reventaba
    # con `TypeError: 'str' object is not a mapping` a mitad de la migración.
    ya = cfg.load_decisiones(slug)
    nuevas = {b: d for b, d in viejas.items() if b not in ya}
    if nuevas:
        cfg.save_decisiones(slug, {**viejas, **ya})   # el registro gana ante el mismo bibcode
        cfg.print_seguro(f"{slug}: {len(nuevas)} decisión(es) migradas a {cfg.registro_path(slug)} "
              f"({len(ya)} ya estaban).")
    else:
        cfg.print_seguro(f"{slug}: las {len(viejas)} decisión(es) del triage.json viejo ya estaban en el "
              f"registro.")
    # El migrador CONSUME su entrada. Sin esto, el detector del lint —que bloquea por EXISTENCIA del
    # archivo— seguía en 1 después de correr el único comando que el propio mensaje recomienda, sin
    # ninguna acción disponible: el círculo migrador→detector no cerraba. Borrarlo es exactamente lo
    # que este mismo mensaje declaraba seguro ("build/ es scratch"), y lo que ya está en el registro
    # versionado sobrevive al borrado (que es el punto de #51). Pero eso vale sólo llegados hasta
    # acá: con `viejas` vacío (clave presente pero sin contenido) o ya cubierto por `ya`, seguimos
    # habiendo LEÍDO y consolidado la clave — es distinto del caso de arriba, que nunca la leyó.
    legacy.unlink()
    cfg.print_seguro(f"  Ahora viajan en git: commiteá el registro. Borré {legacy} (scratch, ya consolidado): "
          f"el lint deja de reportarlo.")
    return 0


def show_decisions(slug: str, decisiones: dict) -> int:
    """Sin `build/<slug>/ads.json` no hay candidatos que juzgar, pero el juicio YA registrado sí
    existe y hay que poder verlo: es el caso normal de un tema **off-ADS puro** (nunca hubo query,
    así que nunca hubo ads.json) y el de cualquier sujeto tras limpiar `build/`. Antes esto moría
    con "corré primero la cadena", que para un off-ADS es un consejo imposible."""
    # NO afirmar "no hay pendientes": sin `build/` no se miró nada. El registro sí sabe cuántos
    # candidatos dejó la última corrida — y es justo el caso (post-clone) donde el lint los reporta
    # y manda correr este comando: negarlos acá reintroduce el falso limpio que #64 cerró.
    b = cfg.load_registro(slug).get("busqueda") or {}
    # #H11: una `busqueda:` editada a mano puede ser un escalar en vez de un mapa;
    # el lector es tolerante, pero este consumidor no → tratala como ausente.
    if not isinstance(b, dict):
        b = {}
    pend = b.get("n_candidates")
    cola = (f"sin build/{slug}/ads.json: no se puede juzgar candidatos hasta re-correr la cadena"
            if not pend else
            f"sin build/{slug}/ads.json, y el registro del {b.get('fecha', 's/f')} anotó "
            f"{pend} candidato(s) sin juzgar → re-corré la cadena para poder juzgarlos")
    cfg.print_seguro(f"Registro de {slug}: {len(decisiones)} decisión(es) persistidas · {cola}")
    for k, d in sorted(decisiones.items()):
        origen = d.get("origen") or "chaining"
        ptr = f" → {d['fuente']}" if d.get("fuente") else ""
        cfg.print_seguro(f"  [{d.get('decision', '?')}] {k}  ({origen}, {d.get('fecha', 's/f')}){ptr}\n"
              f"      motivo: {d.get('motivo') or '(sin motivo registrado)'}")
    cfg.print_seguro(f"\n  → viven en {triage_file(slug)} (versionado). Para juzgar candidatos del chaining "
          f"hace falta la cadena de ingest; un tema off-ADS no los tiene por diseño.")
    return 0


def has_note(bibcode: str) -> bool:
    """¿El candidato ya tiene nota en `vault/wiki/papers/`? Pasa cuando entró por OTRO slug (paper
    de método curado a otra estrella): ya está bajado y extraído, así que proponerlo sin marcar es
    trabajo repetido (#42). La decisión sigue siendo legítimamente por-slug (¿pertinente a ESTE
    sujeto?) — se etiqueta `◆`, no se filtra; el `stars:` que falte lo cubre el retro-linkeo
    add-only de make_notes."""
    return (cfg.PAPERS / f"{bibcode.replace('/', '_')}.md").exists()


def row(c: dict) -> str:
    cites = c.get("citation_count") or 0
    nota = "◆" if has_note(c["bibcode"]) else " "
    title = " ".join((c.get("title") or "").split())[:76]
    return f"  {cites:>5} {nota} {c['bibcode']}  {title}  «{','.join(cfg.as_list(c.get('topics')))}»"


def report(slug: str, cands: list[dict]) -> None:
    """Tabla markdown en outputs/ (nivel 2): para decidir por lote y/o mostrarle al usuario."""
    out = cfg.ROOT / "outputs" / f"triage-{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Triage de candidatos del chaining — {slug}",
             "",
             f"{len(cands)} candidatos pendientes (no bajados). Criterio: ¿el paper es **pertinente "
             "al sujeto** o sólo lo menciona? Aceptados → `extra_core` en `vault/config/stars.yaml`; "
             "descartados → `python scripts/triage.py " + slug + " --drop <bib> --reason \"<motivo>\"`. "
             "`◆` = ya tiene nota en la bóveda (entró por otro slug): bajado y extraído, se "
             "despacha rápido.",
             "",
             "| citas | ◆ | año | bibcode | título | vía | tópicos |",
             "|---:|:-:|---:|---|---|---|---|"]
    for c in cands:
        title = " ".join((c.get("title") or "").split()).replace("|", "\\|")
        lines.append(f"| {c.get('citation_count') or 0} | {'◆' if has_note(c['bibcode']) else ''} | "
                     f"{c.get('year') or ''} | "
                     f"[{c['bibcode']}]({ADS_URL}{c['bibcode']}/abstract) | {title} | "
                     f"{c.get('via') or ''} | {','.join(cfg.as_list(c.get('topics')))} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cfg.print_seguro(f"  → {out}")


def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="estrella (o tema) con build/<slug>/ads.json; con --drop-source "
                                 "(fuente declarada off-ADS) no hace falta el ads.json")
    ap.add_argument("--report", action="store_true",
                    help="además de listar, escribir la tabla en outputs/triage-<slug>.md")
    ap.add_argument("--drop", nargs="+", metavar="BIBCODE",
                    help="persistir el descarte de estos candidatos (no se re-proponen)")
    ap.add_argument("--drop-source", nargs="+", metavar="CLAVE", dest="drop_source",
                    help="#81: persistir el rechazo de una FUENTE DECLARADA (tema off-ADS): la "
                         "clave de cita sintética, o la url si no tiene. No requiere ads.json")
    ap.add_argument("--pointer", default="",
                    help="(--drop-source) url/doi/ruta de la fuente rechazada — lo que vuelve "
                         "resoluble una clave sintética meses después")
    ap.add_argument("--reason", default="",
                    help="motivo del descarte (obligatorio con --drop/--drop-source; queda en el "
                         "registro)")
    ap.add_argument("--migrate", action="store_true",
                    help="consolidar en el registro versionado las decisiones del "
                         "build/<slug>/triage.json viejo (bóvedas pre-1.9.0) y salir")
    args = ap.parse_args()

    if args.migrate:
        return migrate(args.slug)

    if args.drop and args.drop_source:
        ap.error("--drop y --drop-source son los dos carriles de curación (candidato del chaining "
                 "vs fuente declarada): usá uno por corrida, con su motivo")

    if args.drop:
        if not args.reason:
            ap.error("--drop necesita --reason (el motivo queda registrado; no curar en silencio)")
        return drop(args.slug, args.drop, args.reason)

    if args.drop_source:
        if not args.reason:
            ap.error("--drop-source necesita --reason (el motivo queda registrado; no curar en "
                     "silencio)")
        return drop_source(args.slug, args.drop_source, args.reason, args.pointer or None)

    decisiones = load_decisions(args.slug)
    if not (cfg.ROOT / "build" / args.slug / "ads.json").exists():
        if decisiones:
            return show_decisions(args.slug, decisiones)
        # Un tema off-ADS PURO no tiene `ads.json` por diseño: mandarlo a "corré la cadena" (con un
        # comando que además no resuelve su slug) es el consejo imposible que #81 vino a sacar.
        try:
            _, meta = cfg.topic_by_slug(args.slug)
        except KeyError:
            meta = None
        if meta is not None and (meta.get("source") or "ads") != "ads":
            sys.exit(f"'{args.slug}' es un tema off-ADS (source: {meta.get('source')}): no tiene "
                     f"candidatos del chaining por diseño y no hay decisiones registradas. El "
                     f"carril de este tema es `triage.py {args.slug} --drop-source <clave> "
                     f"--reason \"<motivo>\"`.")
    data = load_ads(args.slug)
    cands = cfg.as_list(data.get("candidates"))
    con_nota = sum(1 for c in cands if has_note(c["bibcode"]))
    cfg.print_seguro(f"Triage de {args.slug}: {len(cands)} candidatos pendientes "
          f"(◆ {con_nota} ya con nota en la bóveda, vía otro slug) · "
          f"{len(decisiones)} decisiones persistidas · {data.get('n_relevant', 0)} core actuales")
    if not cands:
        cfg.print_seguro("  → nada pendiente. (Los candidatos aparecen tras un query_ads con chaining.)")
        return 0
    for c in sorted(cands, key=lambda c: c.get("citation_count") or 0, reverse=True):
        cfg.print_seguro(row(c))
    if args.report:
        report(args.slug, cands)
    cfg.print_seguro("\n  → juicio (LLM/usuario) por título+abstract: pertinente al SUJETO / ruido / dudoso.\n"
          "     aceptados  → `extra_core: [<bibcode>, …]` en vault/config/stars.yaml y re-correr la "
          "cadena (idempotente: sólo baja los nuevos).\n"
          "     descartados → python scripts/triage.py <slug> --drop <bib> … --reason \"<motivo>\".\n"
          "     dudosos    → al usuario (--report deja la tabla en outputs/).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
