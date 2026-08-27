#!/usr/bin/env python3
"""Harvest the extraction fan-out: `build/<slug>/extraccion/*.json` → the paper notes (#188 / #191).

Until 1.68.0 this step **did not exist**. Each subagent wrote its JSON and nobody read it: the
harvest was manual, and `extraction_prompt.is_extraction` — the P0 guard that tells an extraction
apart from any other JSON carrying a `bibcode` (INV-103) — had no production caller at all. The
defect it exists for is measured: a hand-written harvest that accepted any JSON with a `bibcode`
picked up 13 `verify-citations` outputs from ANOTHER star and overwrote 13 finished notes, with
perfectly valid JSON — that is, in silence.

    python scripts/harvest_views.py <slug> [--theme] [--force]

What it writes, per paper:
  · the VIEW in the frontmatter (#188) — `sujeto`/`tipo` from the JSON, plus the three fields the
    subagent cannot know for sure: `fecha` (the reading happened), `txt` (which copy was read —
    the source anchor of D-18) and `lente` (the facets in force, so D-49 can diff at reading level);
  · `methods` / `thesis_links` / `role`, add-only — never overwriting what is already there;
  · the `## Vista — <sujeto>` section, only while it still is the stub template. Redacted prose is
    never overwritten without `--force`: it may already carry verification anchors.

It also brings the `.txt` to the subject's slug (D-18) so a retro-tagged paper's view is runnable:
without that, `extraction_prompt.py <theme> <bib>` exits `⛔ no existe` and the remedy it suggests
does not apply either, because the PDF is not under that slug.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

import extraction_prompt as ep
import lib_config as cfg
import make_notes as mn


def render_view(sujeto: str, data: dict) -> str:
    """The `## Vista — <sujeto>` section built from one extraction JSON.

    Deterministic on purpose: the same JSON has to render byte-identical, or the idempotence rule
    of the framework (`corré dos veces y hasheá`) cannot hold for this step."""
    out = [f"## Vista — {sujeto}", ""]
    if (aporte := str(data.get("aporte") or "").strip()):
        out += [f"**Aporte:** {aporte}", ""]
    ejes = {k: str(v).strip() for k, v in (cfg.as_map(data.get("ejes")) or {}).items()
            if str(v).strip()}
    if ejes:
        out += ["**Ejes:**", ""] + [f"- **{k}:** {v}" for k, v in ejes.items()] + [""]
    filas = [f for f in cfg.as_list(data.get("ground_truth")) if isinstance(f, dict)]
    if filas:
        out += ["| Qué | Valor | Línea | Régimen | Segunda mano |", "|---|---|---|---|---|"]
        for f in filas:
            celdas = [str(f.get(k) or "—").strip() or "—"
                      for k in ("que", "valor", "linea", "regimen", "segunda_mano")]
            out.append("| " + " | ".join(celdas) + " |")
        out.append("")
    if (hueco := str(data.get("hueco") or "").strip()):
        out += [f"**Hueco:** {hueco}", ""]
    salv = [str(x).strip() for x in cfg.as_list(data.get("salvedades")) if str(x).strip()]
    if salv:
        out += ["**Salvedades:**", ""] + [f"- {s}" for s in salv] + [""]
    return "\n".join(out).rstrip("\n") + "\n"


def _norm(texto: str) -> str:
    return "\n".join(ln.rstrip() for ln in texto.strip().splitlines() if ln.strip())


def section_span(text: str, header: str) -> tuple[int, int] | None:
    """`(inicio, fin)` de la sección que abre en `header`, hasta el próximo `## ` (o EOF)."""
    inicio = cfg.section_start(text, header)
    if inicio < 0:
        return None
    nxt = text.find("\n## ", inicio + 1)
    return inicio, (len(text) if nxt < 0 else nxt + 1)


def write_view_section(dest: Path, sujeto: str, cuerpo: str, *, theme: bool,
                       force: bool = False) -> bool:
    """Escribe la sección de la vista. Devuelve True si tocó el archivo.

    ⛔ Sólo pisa mientras la sección sigue siendo **la plantilla del stub** (se compara contra
    `make_notes.vista_block`, la misma fuente que la escribió). Prosa ya redactada no se toca sin
    `--force`: puede estar verificada, y sus anclas cuelgan del texto exacto."""
    text = dest.read_text(encoding="utf-8")
    span = section_span(text, f"## Vista — {sujeto}")
    if span is None:
        nuevo = text.rstrip("\n") + "\n\n" + cuerpo
    else:
        ini, fin = span
        actual = text[ini:fin]
        if not force and _norm(actual) != _norm(mn.vista_block(sujeto, theme)):
            return False
        nuevo = text[:ini] + cuerpo.rstrip("\n") + "\n" + text[fin:]
    if nuevo == text:
        return False
    cfg.write_text_atomic(dest, nuevo)
    return True


def upsert_view(dest: Path, vista: dict) -> bool:
    """Mergea `vista` en `vistas[]` del frontmatter, por `sujeto`. Devuelve True si modificó.

    Reescribe **sólo el bloque `vistas:`**, dejando el resto del frontmatter byte a byte — mismo
    criterio que `merge_frontmatter_list`: ahí abajo hay campos que tocó la extracción LLM."""
    import yaml
    text = dest.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end < 0:
        return False
    head = text[4:end]
    try:
        data = yaml.safe_load(head) or {}
    except yaml.YAMLError:
        return False
    previas = [v for v in cfg.as_list(data.get("vistas")) if isinstance(v, dict)]
    nuevas, visto = [], False
    for v in previas:
        if str(v.get("sujeto") or "").strip() == vista["sujeto"]:
            nuevas.append({**v, **vista})
            visto = True
        else:
            nuevas.append(v)
    if not visto:
        nuevas.append(vista)
    if nuevas == previas:
        return False
    bloque = yaml.safe_dump({"vistas": nuevas}, sort_keys=False, allow_unicode=True,
                            default_flow_style=False)
    lineas, out, i = head.splitlines(keepends=True), [], 0
    while i < len(lineas):
        if lineas[i].startswith("vistas:"):
            i += 1
            while i < len(lineas) and (lineas[i].startswith((" ", "-", "\t"))
                                       or not lineas[i].strip()):
                i += 1
            out.append(bloque)
        else:
            out.append(lineas[i])
            i += 1
    nuevo_head = "".join(out)
    if "vistas:" not in head:
        nuevo_head = nuevo_head.rstrip("\n") + "\n" + bloque
    # `head` no incluye el `\n` que separa la última clave del `---` de cierre (queda en `end`), así
    # que se normaliza acá: se saca el salto sobrante del bloque reconstruido y se reusa `text[end:]`,
    # que ya lo trae. Cortar en `end + 1` se lo comía, y una nota con `generator: v1.69.0---` deja de
    # parsear ENTERA — o sea que desaparece de todos los chequeos por tipo, en silencio. Medido: 24
    # de 202 notas de una bóveda real, con el cosechador informando «65 cosechadas».
    cfg.write_text_atomic(dest, "---\n" + nuevo_head.rstrip("\n") + text[end:])
    return True


def bring_fulltext(slug: str, bibcode: str) -> bool:
    """Trae el `.txt` del paper al slug del sujeto si ya está bajo otro (D-18). True si copió."""
    destino = cfg.FULLTEXT / slug / f"{bibcode}.txt"
    if destino.exists():
        return False
    origen = cfg.artefacto_en_otro_slug(cfg.FULLTEXT, slug, bibcode, ".txt")
    if origen is None:
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Atómico (D-53 / INV-90), como el mismo atajo en `extract_fulltext`: un `shutil.copy2` al
    # destino final deja un `.txt` torn si el proceso muere a mitad, y `raw/` es inmutable — el
    # archivo roto se queda. El guard de escrituras directas lo caza, y acá cazó esto.
    cfg.write_bytes_atomic(destino, origen.read_bytes())
    return True


def harvest(slug: str, *, theme: bool = False, force: bool = False,
            src: Path | None = None) -> dict:
    """Cosecha todas las extracciones de `slug`. Devuelve los contadores del reporte."""
    src = src or (cfg.ROOT / "build" / slug / "extraccion")
    n = {"cosechadas": 0, "rechazadas": 0, "sin_nota": 0, "sin_cambios": 0, "txt_traidos": 0}
    if not src.exists():
        cfg.print_seguro(f"  (sin {src}; nada que cosechar)")
        return n
    lente = mn.objective_lens()[0]
    hoy = _dt.date.today().isoformat()
    for archivo in sorted(src.glob("*.json")):
        try:
            data = json.loads(archivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            n["rechazadas"] += 1
            cfg.print_seguro(f"  ⛔ {archivo.name}: no parsea ({e.__class__.__name__})")
            continue
        # INV-103 — la identidad es la FORMA, no el `bibcode`: la salida de `verify-citations`
        # también lo trae. Ésta es la comprobación que faltaba tener en producción.
        if not ep.is_extraction(data):
            n["rechazadas"] += 1
            cfg.print_seguro(f"  ⛔ {archivo.name}: no es una extracción (¿salida de verify?) — "
                             f"no se toca ninguna nota")
            continue
        vista = cfg.as_map(data.get("vista"))
        sujeto, tipo = str(vista.get("sujeto") or "").strip(), str(vista.get("tipo") or "").strip()
        if not sujeto or tipo not in cfg.VISTA_TIPOS:
            n["rechazadas"] += 1
            cfg.print_seguro(f"  ⛔ {archivo.name}: sin `vista` válida (`sujeto` + `tipo` en "
                             f"{' | '.join(cfg.VISTA_TIPOS)}) — de quién es la lectura no se adivina")
            continue
        bib = str(data.get("bibcode")).strip()
        dest = cfg.PAPERS / f"{mn.safe_name(bib)}.md"
        if not dest.exists():
            n["sin_nota"] += 1
            cfg.print_seguro(f"  ⚠ {bib}: no hay nota en papers/ — corré `make_notes.py {slug}`")
            continue
        entrada = {"sujeto": sujeto, "tipo": tipo, "fecha": hoy,
                   "txt": str(vista.get("txt") or slug), "lente": list(lente)}
        toco = upsert_view(dest, entrada)
        for campo in ("methods", "thesis_links", "role"):
            valores = [str(x).strip() for x in cfg.as_list(data.get(campo)) if str(x).strip()]
            if valores and mn.merge_frontmatter_list(dest, campo, valores):
                toco = True
        if write_view_section(dest, sujeto, render_view(sujeto, data), theme=theme, force=force):
            toco = True
        if bring_fulltext(slug, mn.safe_name(bib)):
            n["txt_traidos"] += 1
        n["cosechadas" if toco else "sin_cambios"] += 1
    cfg.print_seguro(
        f"  vistas: {n['cosechadas']} cosechadas, {n['sin_cambios']} sin cambios"
        + (f", {n['rechazadas']} RECHAZADAS" if n["rechazadas"] else "")
        + (f", {n['sin_nota']} sin nota destino" if n["sin_nota"] else "")
        + (f", {n['txt_traidos']} .txt traídos al slug" if n["txt_traidos"] else ""))
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug")
    ap.add_argument("--theme", action="store_true", help="el slug es un tema, no una estrella")
    ap.add_argument("--force", action="store_true",
                    help="reescribe la sección de la vista aunque ya tenga prosa redactada")
    args = ap.parse_args()
    harvest(args.slug, theme=args.theme, force=args.force)
    cfg.save_paso(args.slug, "harvest_views", flags=["--force"] if args.force else [])
    return 0


if __name__ == "__main__":
    cfg.stdout_tolerante()
    sys.exit(main())
