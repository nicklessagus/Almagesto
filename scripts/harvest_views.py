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
import re
import json
import sys
from pathlib import Path

import extraction_prompt as ep
import lib_config as cfg
import make_notes as mn


# Un `[[…]]` en markdown es un WIKILINK. Una extracción trae matrices escritas igual
# —`C_U = [[r11, r12],[r12, r22]]`— y escribirlas tal cual **fabrica wikilinks rotos**, que son
# bloqueantes: medido, 14 de una sola cosecha, sobre notas que nadie escribió a mano. Se neutraliza
# lo que NO parece un bibcode; la cita de segunda mano dentro de la vista sobrevive intacta.
# Misma heurística de target que usa el lint (`^\d{4}[A-Za-z]`), para que las dos puntas coincidan.
# Se mira la APERTURA, no el par completo: una matriz anidada —`[[r11, r12],[r12, r22]]`— no tiene
# un `]]` que cierre el primer `[[`, así que un patrón de par no la ve. Un `[[` sobrevive sólo si lo
# que sigue arranca como bibcode.
_APERTURA = re.compile(r"\[\[(?!\d{4}[A-Za-z][^\]\n]*\]\])")


def _safe_links(texto: str) -> str:
    """Deja el `[[bibcode]]` y desarma el `[[` que en realidad era notación."""
    return _APERTURA.sub("[", texto)


PLACEHOLDER_ABSTRACT = "_(no disponible)_"


def pdf_on_disk(bibcode: str) -> bool:
    """¿Hay un PDF de este bibcode bajo cualquier slug? Verdad de disco, no frontmatter.

    El cruce de #207 tiene que mirar el archivo: el campo `pdf` de la nota puede estar en drift (es
    justo lo que el WARN `pdf_issues` del lint reporta), y usarlo acá haría que un drift se leyera
    como «la vista miente»."""
    return any(cfg.PDFS.glob(f"**/{mn.safe_name(bibcode)}.pdf"))


def render_view(sujeto: str, data: dict) -> str:
    """The `## Vista — <sujeto>` section built from one extraction JSON.

    Deterministic on purpose: the same JSON has to render byte-identical, or the idempotence rule
    of the framework (`corré dos veces y hasheá`) cannot hold for this step."""
    out = [f"## Vista — {sujeto}", ""]
    if (aporte := _safe_links(str(data.get("aporte") or "").strip())):
        out += [f"**Aporte:** {aporte}", ""]
    ejes = {k: _safe_links(str(v).strip()) for k, v in (cfg.as_map(data.get("ejes")) or {}).items()
            if str(v).strip()}
    if ejes:
        out += ["**Ejes:**", ""] + [f"- **{k}:** {v}" for k, v in ejes.items()] + [""]
    filas = [f for f in cfg.as_list(data.get("ground_truth")) if isinstance(f, dict)]
    if filas:
        # «Localizador», no «Línea» (#195): la columna ya no lleva sólo un nº de línea del `.txt`.
        # Un valor levantado de una tabla-imagen se cita por PÁGINA del PDF y una lectura de
        # gráfico por `Fig. N, p. M` — llamar «Línea» a eso es la misma mentira de encabezado que
        # #200 corrige en el bloque de verificación. La CLAVE del JSON sigue siendo `linea`: el
        # artefacto vive en `build/` y renombrarla dejaría mudas las extracciones en vuelo.
        out += ["| Qué | Valor | Localizador | Régimen | Segunda mano |", "|---|---|---|---|---|"]
        for f in filas:
            celdas = [_safe_links(str(f.get(k) or "—").strip()) or "—"
                      for k in ("que", "valor", "linea", "regimen", "segunda_mano")]
            out.append("| " + " | ".join(celdas) + " |")
        out.append("")
    if (hueco := _safe_links(str(data.get("hueco") or "").strip())):
        out += [f"**Hueco:** {hueco}", ""]
    salv = [_safe_links(str(x).strip()) for x in cfg.as_list(data.get("salvedades")) if str(x).strip()]
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


def stamp_reading_aids(dest: Path, data: dict) -> bool:
    """`## Traducción del abstract`, `## Conclusiones` y su traducción — las ayudas de lectura (#124).

    ⚠ **Las traducciones NO se llaman `## Abstract (es)`.** Ese nombre hacía de `## Abstract` un
    **prefijo** del suyo, y `section_start` tolera a propósito un sufijo que arranca con puntuación
    —lo necesita para `## Vista — tau Ceti (2026-08-27)`—. Medido el 2026-08-28: con sólo la
    traducción en la nota, el guard del verbatim la daba por el original y **no lo estampaba nunca**,
    dejando a `note_lens_text` (el insumo del diff de lente offline, D-49) sin abstract para siempre.
    Es la trampa de prefijo de #176 instanciada en el vocabulario propio del framework: se saca
    renombrando, no aflojando el cortador.

    POR QUÉ. La **vista** es lenteada: dice qué aporta el paper *a ese sujeto*. Las conclusiones son
    lo que el paper afirma **sin lente**, y por eso no son redundantes — son lo que hace barata una
    **segunda vista** cuando otro sujeto reclama el mismo paper, que no es un caso raro: medido
    (#188), **141 de 908** notas las reclaman 2+ sujetos y ninguna tiene una segunda extracción.
    Y desde #205 pesa más, porque abrir el PDF es lo caro: tener las afirmaciones del paper en la
    nota evita re-abrirlo.

    ⛔ **Son ayuda de lectura, nunca fuente de la que citar.** Van en `SECCIONES_ESTAMPADAS`, así que
    `verify-citations` no las mira — una traducción no es una afirmación de la bóveda y no hay qué
    contrastar contra la fuente. La red está aguas abajo: lo que de acá llegue a una **ficha** sí se
    verifica contra el PDF, así que un error propagado desde una mala traducción se caza ahí. Si
    citás, citás del original con su página.

    ⚠ **El original no se pisa.** El `## Abstract` verbatim es la capa auditable del cuerpo (copia
    de catálogo) y `classify_offline` lo lee para el diff de lente offline (D-49); la traducción va
    **al lado**, en su propia sección.

    ⚠ **Documento largo: sin conclusiones.** Una fuente `unidad_cita: pagina` —un libro, un
    handbook— no tiene "conclusiones" como sección, y transcribir algo que no existe fabricaría una
    sección con contenido inventado. Es una exclusión estructural, no un umbral de largo (que sería
    un corte sin calibrar, y de eso este repo ya se quemó tres veces).

    Idempotente y quirúrgico: cada sección se reemplaza sola y sin tocar el resto."""
    texto_nota = dest.read_text(encoding="utf-8")
    fm = cfg.split_fm(texto_nota)
    largo = str(fm.get("unidad_cita") or "").strip() not in ("", "linea")
    piezas = []
    # `## Abstract` verbatim: el abstract tiene DOS fuentes y nada más (decidido con el usuario,
    # 2026-08-28) — **ADS**, que lo estampa `make_notes` como copia de máquina, o **el PDF**, vía el
    # extractor. No se pisa un abstract de catálogo con una transcripción del modelo.
    # Se rellena en dos casos: la sección **falta** (nota off-ADS, que no tiene catálogo del que
    # copiar) o está con el **placeholder** `_(no disponible)_` (ADS no lo devolvió). Sin el segundo
    # caso el placeholder sería permanente, porque el guard vería la sección y no la tocaría nunca.
    _ini = cfg.section_start(texto_nota, "## Abstract")
    _vacio = _ini >= 0 and PLACEHOLDER_ABSTRACT in texto_nota[_ini:_ini + 200]
    if _ini < 0 or _vacio:
        piezas.append(("## Abstract", data.get("abstract")))
    piezas.append(("## Traducción del abstract", data.get("abstract_es")))
    if not largo:
        piezas += [("## Conclusiones", data.get("conclusiones")),
                   ("## Traducción de las conclusiones", data.get("conclusiones_es"))]
    toco = False
    for header, texto in piezas:
        # Ausente = no consta: no se crea una sección vacía. Un `## Conclusiones` en blanco se
        # leería como «el paper no concluye nada», que no es lo mismo que «nadie las transcribió».
        if not (limpio := str(texto or "").strip()):
            continue
        if upsert_section(dest, header, f"{header}\n{limpio}\n"):
            toco = True
    return toco


def upsert_section(dest: Path, header: str, cuerpo: str) -> bool:
    """Reemplaza la sección `header` si existe; si no, la agrega **antes de la primera `## Vista`**.

    El orden importa para leer: las ayudas de lectura van arriba de la vista, no al final después
    del bloque de verificación. Si no hay vista todavía, va al final."""
    text = dest.read_text(encoding="utf-8")
    span = section_span(text, header)
    if span is not None:
        ini, fin = span
        nuevo = text[:ini] + cuerpo.rstrip("\n") + "\n\n" + text[fin:]
    else:
        corte = text.find("\n## Vista — ")
        punto = len(text) if corte < 0 else corte + 1
        nuevo = text[:punto].rstrip("\n") + "\n\n" + cuerpo.rstrip("\n") + "\n\n" + text[punto:]
    if nuevo == text:
        return False
    cfg.write_text_atomic(dest, nuevo)
    return True


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
        # #207 · de QUÉ se construyó la vista. Lo DECLARA el extractor (es el único que sabe qué
        # abrió) y acá se CRUZA contra el disco: `fuente: pdf` sin PDF es una contradicción, y
        # estamparla dejaría una vista de ocho líneas de abstract leyéndose como lectura del paper.
        # Fuera del vocabulario o incoherente ⇒ se rechaza el JSON entero, no se corrige a mano:
        # adivinar cuál de las dos mitades miente es exactamente lo que este campo evita.
        #  @inv INV-138
        fuente = str(vista.get("fuente") or "").strip()
        if fuente and fuente not in cfg.VISTA_FUENTES:
            n["rechazadas"] += 1
            cfg.print_seguro(f"  ⛔ {archivo.name}: `fuente: {fuente}` fuera del vocabulario "
                             f"({' | '.join(cfg.VISTA_FUENTES)})")
            continue
        if fuente == "pdf" and not pdf_on_disk(bib):
            n["rechazadas"] += 1
            cfg.print_seguro(f"  ⛔ {archivo.name}: declara `fuente: pdf` y no hay PDF en "
                             f"`raw/pdfs/**/{bib}.pdf` — la vista diría que se leyó el paper")
            continue
        entrada = {"sujeto": sujeto, "tipo": tipo, "fecha": hoy,
                   "txt": str(vista.get("txt") or slug), "lente": list(lente)}
        if fuente:
            entrada["fuente"] = fuente
        toco = upsert_view(dest, entrada)
        for campo in ("methods", "thesis_links", "role"):
            valores = [str(x).strip() for x in cfg.as_list(data.get(campo)) if str(x).strip()]
            if valores and mn.merge_frontmatter_list(dest, campo, valores):
                toco = True
        if write_view_section(dest, sujeto, render_view(sujeto, data), theme=theme, force=force):
            toco = True
        if stamp_reading_aids(dest, data):
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
