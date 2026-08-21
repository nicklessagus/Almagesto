"""Compuerta de triage de los candidatos del citation chaining (#38).

Uso:
    python scripts/triage.py <slug>                                   # listar los candidatos pendientes
    python scripts/triage.py <slug> --report                          # + tabla en outputs/triage-<slug>.md
    python scripts/triage.py <slug> --drop <bib> [<bib> …] --reason "<motivo>"
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
  motivo. Ese archivo viejo se sigue LEYENDO (no se pierde juicio hecho) y se consolida solo en el
  primer `--drop`. Los candidatos que **ya tienen nota** en la bóveda (entraron por OTRO slug —
  papers de método curados a otra estrella) se marcan `◆` (#42): ya están bajados y extraídos, la
  decisión sigue siendo por-slug pero se despachan rápido — no se filtran, se etiquetan.
- **2 — informe al usuario:** `--report` deja la tabla en `outputs/triage-<slug>.md` (título, año,
  citas, vía, tópicos, link a ADS) para decidir los **dudosos** por lote.

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
    """Decisiones del registro versionado + las del triage.json viejo (migración transparente)."""
    return cfg.load_decisiones(slug)


def save_decisions(slug: str, decisiones: dict) -> None:
    """Escribe SIEMPRE en el registro versionado; `busqueda` (de query_ads) se preserva. Lo que
    venía del legacy se consolida acá en el primer --drop, sin pasos de migración a mano."""
    cfg.save_decisiones(slug, decisiones)


def drop(slug: str, bibcodes: list[str], reason: str) -> int:
    """Persiste el descarte de candidatos (no se re-proponen en el próximo refresh)."""
    pendientes = {c["bibcode"] for c in load_ads(slug).get("candidates") or []}
    desconocidos = [b for b in bibcodes if b not in pendientes]
    if desconocidos:
        print(f"  ⚠ {len(desconocidos)} bibcode(s) no están entre los candidatos pendientes "
              f"(¿ya decididos, o typo?): {', '.join(desconocidos)}")
    decisiones = load_decisions(slug)
    hoy = dt.date.today().isoformat()
    for b in bibcodes:
        decisiones[b] = {"decision": "descartado", "motivo": reason, "fecha": hoy}
    save_decisions(slug, decisiones)
    print(f"  {len(bibcodes)} candidato(s) descartados en {triage_file(slug)} — motivo: {reason}")
    print("  (versionado: se commitea y viaja entre máquinas, como `extra_core` — los dos lados "
          "de la decisión sobreviven al clon)")
    print("  (los aceptados NO van acá: van a `extra_core` en stars.yaml, curación persistente)")
    return 0


def migrate(slug: str) -> int:
    """Consolida en el registro VERSIONADO las decisiones que hayan quedado en el
    `build/<slug>/triage.json` de una bóveda pre-1.9.0 (#51).

    Sin esto la migración sólo ocurre en el próximo `--drop`: hasta entonces el juicio sigue
    viviendo únicamente en scratch gitignored, y un clon en otra máquina lo pierde igual que antes
    —exactamente el bug que #51 arregla—. Depender de que el usuario justo descarte algo no es una
    migración. Idempotente: ante el mismo bibcode gana lo ya versionado, y si no hay nada que
    migrar no escribe."""
    legacy = cfg.legacy_triage_path(slug)
    if not legacy.exists():
        print(f"{slug}: no hay {legacy} — nada que migrar "
              f"(el juicio nuevo ya se escribe en {cfg.registro_path(slug)}).")
        return 0
    try:
        viejas = json.loads(legacy.read_text(encoding="utf-8")).get("decisiones") or {}
    except ValueError:
        sys.exit(f"{legacy} no es JSON válido — revisalo a mano antes de migrar.")
    ya = cfg.load_registro(slug).get("decisiones") or {}
    nuevas = {b: d for b, d in viejas.items() if b not in ya}
    if not nuevas:
        print(f"{slug}: las {len(viejas)} decisión(es) del triage.json viejo ya estaban en el "
              f"registro — nada que hacer.")
        return 0
    cfg.save_decisiones(slug, {**viejas, **ya})       # el registro gana ante el mismo bibcode
    print(f"{slug}: {len(nuevas)} decisión(es) migradas a {cfg.registro_path(slug)} "
          f"({len(ya)} ya estaban).")
    print("  Ahora viajan en git: commiteá el registro. El triage.json viejo queda como estaba "
          "(build/ es scratch; se puede borrar).")
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
    return f"  {cites:>5} {nota} {c['bibcode']}  {title}  «{','.join(c.get('topics') or [])}»"


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
                     f"{c.get('via') or ''} | {','.join(c.get('topics') or [])} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  → {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="estrella (o tema) con build/<slug>/ads.json")
    ap.add_argument("--report", action="store_true",
                    help="además de listar, escribir la tabla en outputs/triage-<slug>.md")
    ap.add_argument("--drop", nargs="+", metavar="BIBCODE",
                    help="persistir el descarte de estos candidatos (no se re-proponen)")
    ap.add_argument("--reason", default="",
                    help="motivo del descarte (obligatorio con --drop; queda en el registro)")
    ap.add_argument("--migrate", action="store_true",
                    help="consolidar en el registro versionado las decisiones del "
                         "build/<slug>/triage.json viejo (bóvedas pre-1.9.0) y salir")
    args = ap.parse_args()

    if args.migrate:
        return migrate(args.slug)

    if args.drop:
        if not args.reason:
            ap.error("--drop necesita --reason (el motivo queda registrado; no curar en silencio)")
        return drop(args.slug, args.drop, args.reason)

    data = load_ads(args.slug)
    cands = data.get("candidates") or []
    decisiones = load_decisions(args.slug)
    con_nota = sum(1 for c in cands if has_note(c["bibcode"]))
    print(f"Triage de {args.slug}: {len(cands)} candidatos pendientes "
          f"(◆ {con_nota} ya con nota en la bóveda, vía otro slug) · "
          f"{len(decisiones)} decisiones persistidas · {data.get('n_relevant', 0)} core actuales")
    if not cands:
        print("  → nada pendiente. (Los candidatos aparecen tras un query_ads con chaining.)")
        return 0
    for c in sorted(cands, key=lambda c: c.get("citation_count") or 0, reverse=True):
        print(row(c))
    if args.report:
        report(args.slug, cands)
    print("\n  → juicio (LLM/usuario) por título+abstract: pertinente al SUJETO / ruido / dudoso.\n"
          "     aceptados  → `extra_core: [<bibcode>, …]` en vault/config/stars.yaml y re-correr la "
          "cadena (idempotente: sólo baja los nuevos).\n"
          "     descartados → python scripts/triage.py <slug> --drop <bib> … --reason \"<motivo>\".\n"
          "     dudosos    → al usuario (--report deja la tabla en outputs/).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
