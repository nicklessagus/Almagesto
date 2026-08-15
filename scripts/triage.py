"""Compuerta de triage de los candidatos del citation chaining (#38).

Uso:
    python triage.py <slug>                                   # listar los candidatos pendientes
    python triage.py <slug> --report                          # + tabla en outputs/triage-<slug>.md
    python triage.py <slug> --drop <bib> [<bib> …] --reason "<motivo>"

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
  Las decisiones **persisten**: aceptado → `extra_core` en `stars.yaml` (override del clasificador,
  #39); descartado → `build/<slug>/triage.json` (con motivo) para que el próximo refresh no lo
  vuelva a proponer.
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
                 f"(o query_ads.py {slug}).")
    return json.loads(f.read_text(encoding="utf-8"))


def triage_file(slug: str):
    return cfg.ROOT / "build" / slug / "triage.json"


def load_decisions(slug: str) -> dict:
    f = triage_file(slug)
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("decisiones") or {}


def save_decisions(slug: str, decisiones: dict) -> None:
    f = triage_file(slug)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"slug": slug, "decisiones": decisiones}, indent=2, ensure_ascii=False),
                 encoding="utf-8")


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
    print("  (los aceptados NO van acá: van a `extra_core` en stars.yaml, curación persistente)")
    return 0


def row(c: dict) -> str:
    cites = c.get("citation_count") or 0
    title = " ".join((c.get("title") or "").split())[:76]
    return f"  {cites:>5}  {c['bibcode']}  {title}  «{','.join(c.get('topics') or [])}»"


def report(slug: str, cands: list[dict]) -> None:
    """Tabla markdown en outputs/ (nivel 2): para decidir por lote y/o mostrarle al usuario."""
    out = cfg.ROOT / "outputs" / f"triage-{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Triage de candidatos del chaining — {slug}",
             "",
             f"{len(cands)} candidatos pendientes (no bajados). Criterio: ¿el paper es **pertinente "
             "al sujeto** o sólo lo menciona? Aceptados → `extra_core` en `vault/config/stars.yaml`; "
             "descartados → `python triage.py " + slug + " --drop <bib> --reason \"<motivo>\"`.",
             "",
             "| citas | año | bibcode | título | vía | tópicos |",
             "|---:|---:|---|---|---|---|"]
    for c in cands:
        title = " ".join((c.get("title") or "").split()).replace("|", "\\|")
        lines.append(f"| {c.get('citation_count') or 0} | {c.get('year') or ''} | "
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
                    help="motivo del descarte (obligatorio con --drop; queda en triage.json)")
    args = ap.parse_args()

    if args.drop:
        if not args.reason:
            ap.error("--drop necesita --reason (el motivo queda registrado; no curar en silencio)")
        return drop(args.slug, args.drop, args.reason)

    data = load_ads(args.slug)
    cands = data.get("candidates") or []
    decisiones = load_decisions(args.slug)
    print(f"Triage de {args.slug}: {len(cands)} candidatos pendientes · "
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
          "     descartados → python triage.py <slug> --drop <bib> … --reason \"<motivo>\".\n"
          "     dudosos    → al usuario (--report deja la tabla en outputs/).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
