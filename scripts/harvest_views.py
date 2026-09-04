#!/usr/bin/env python3
"""Harvest the extraction fan-out: `vault/raw/extraccion/<slug>/*.json` → the paper notes (#188 / #191).

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
import shutil
import subprocess
import sys
from pathlib import Path

import extraction_prompt as ep
import lib_blocks as lb
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


#: #270 · lo que se estampa en un eje que la extracción contestó vacío.
SIN_DATOS = "_(sin datos)_"

PLACEHOLDER_ABSTRACT = cfg.ABSTRACT_PLACEHOLDER   # #277: una sola definición, en `lib_config`


def _resolve_txt_slug(bib: str, declarado: str) -> str | None:
    """Which slug actually holds this bibcode's `.txt`, or `None` when no copy exists (#230).

    Prefers the declared one —that is the extractor's claim and, when it holds, the anchor is
    exact— and falls back to any surviving copy, because the same bibcode legitimately lives under
    several slugs with identical content. `None` means the vault has no `.txt` for it at all.
    """
    if declarado and (cfg.FULLTEXT / declarado / f"{bib}.txt").exists():
        return declarado
    otros = sorted(cfg.FULLTEXT.glob(f"*/{bib}.txt")) if cfg.FULLTEXT.exists() else []
    return otros[0].parent.name if otros else None


def pdf_on_disk(bibcode: str) -> bool:
    """¿Hay un PDF de este bibcode bajo cualquier slug? Verdad de disco, no frontmatter.

    El cruce de #207 tiene que mirar el archivo: el campo `pdf` de la nota puede estar en drift (es
    justo lo que el WARN `pdf_issues` del lint reporta), y usarlo acá haría que un drift se leyera
    como «la vista miente»."""
    return cfg.pdf_slug(mn.safe_name(bibcode)) is not None   # #305: una sola resolución


def check_salvedad(bibcode: str, item: dict) -> tuple[bool | None, str]:
    """Check one STRUCTURED caveat against the file it talks about (#213).

    Returns `(veredicto, detalle)`: `True` it holds, `False` it is FALSE, `None` it could not be
    evaluated — and the third is not the second (D-43). `detalle` is the human-readable evidence,
    which is what ends up in the note so the reader sees HOW it was checked and not just that
    someone said so.

    This exists because a caveat about the ARTEFACT (`the .txt lost this symbol`, `the PDF is an
    unreadable scan`) carries no `[[bibcode]]`, so `verify-citations` drops it from the fan-out by
    construction — it decomposes a note into (claim, bibcode) pairs. Measured: an extractor claimed
    a `.txt` degradation that did not exist, quoting #205 for authority, and what caught it was an
    ACCIDENTAL duplicate of the extraction. The claim was one `grep` away from being decidable.

    ⛔ Machine, not LLM: the whole point is that these claims are decidable, and paying a subagent
    to judge what `grep` settles is both more expensive and less reliable."""
    tipo = str(item.get("tipo") or "").strip()
    if tipo not in cfg.SALVEDAD_TIPOS:
        return None, f"`tipo: {tipo}` fuera del vocabulario ({' | '.join(cfg.SALVEDAD_TIPOS)})"
    stem = mn.safe_name(bibcode)
    if tipo == "txt_pierde":
        cadena = str(item.get("cadena") or "")
        if not cadena:
            return None, "sin `cadena`: no hay qué buscar"
        txts = sorted(cfg.FULLTEXT.glob(f"*/{stem}.txt")) if cfg.FULLTEXT.exists() else []
        if not txts:
            return None, "no hay `.txt` en disco contra el cual chequear"
        presente = any(cadena in t.read_text(encoding="utf-8", errors="replace") for t in txts)
        return (not presente,
                (f"el `.txt` NO contiene `{cadena}`" if not presente
                 else f"el `.txt` SÍ contiene `{cadena}` — la salvedad es FALSA"))
    # pdf_paginas
    try:
        n_dicho = int(item.get("n"))
    except (TypeError, ValueError):
        return None, "sin `n` numérico: no hay qué comparar"
    pdfs = sorted(cfg.PDFS.glob(f"*/{stem}.pdf")) if cfg.PDFS.exists() else []
    if not pdfs:
        return None, "no hay PDF en disco contra el cual chequear"
    # `pdfinfo` (poppler), no una librería nueva: es la MISMA dependencia de sistema que ya declara
    # `requirements.txt` para `pdftotext`, así que el chequeo no agrega un modo de falla propio.
    if shutil.which("pdfinfo") is None:
        return None, "sin `pdfinfo` (poppler-utils) no se pueden contar las páginas"
    try:
        r = subprocess.run(["pdfinfo", str(pdfs[0])], capture_output=True, text=True, timeout=30)
        m = re.search(r"^Pages:\s+(\d+)", r.stdout, re.M)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"no se pudo correr `pdfinfo` ({e.__class__.__name__})"
    if not m:
        return None, "`pdfinfo` no devolvió el número de páginas"
    n_real = int(m.group(1))
    return n_dicho == n_real, f"el PDF tiene {n_real} página(s) (la salvedad dice {n_dicho})"


def split_salvedades(bibcode: str, data: dict) -> tuple[list, list, list]:
    """`(verificadas, sin_verificar, falsas)` — las tres poblaciones de #213.

    A caveat is either **structured** (a map with a `tipo` from `SALVEDAD_TIPOS`: decidable, so it
    gets checked) or **prose** (a string: not decidable, so it is published marked NOT VERIFIED).
    Publishing both at the same visual level is what let a fabricated defect read as a measured
    fact, in the very section a consumer reads to decide how much to trust the extraction."""
    verificadas, prosa, falsas = [], [], []
    for item in cfg.as_list(data.get("salvedades")):
        if isinstance(item, dict):
            ok, detalle = check_salvedad(bibcode, item)
            if ok is True:
                verificadas.append(f"⚙ verificada: {detalle}")
            elif ok is False:
                falsas.append(detalle)
            else:
                # No evaluable NO es «verificada» ni «falsa» (D-43): se publica como prosa marcada.
                prosa.append(f"{item.get('nota') or item.get('tipo')} (no evaluable: {detalle})")
        elif str(item).strip():
            prosa.append(str(item).strip())
    return verificadas, prosa, falsas


def render_view(sujeto: str, data: dict) -> str:
    """The `## Vista — <sujeto>` section built from one extraction JSON.

    Deterministic on purpose: the same JSON has to render byte-identical, or the idempotence rule
    of the framework (`corré dos veces y hasheá`) cannot hold for this step."""
    # #239 — con `enfasis`, la lectura va en una SUB-sección dentro de la vista del sujeto. Se
    # eligió así y no partiendo el encabezado (`## Vista — X · <énfasis>`) porque `section_start` y
    # `vistas_en_cuerpo` recortan a propósito el sufijo que arranca con puntuación (AUD-178, para
    # tolerar `## Vista — X (2026-08-27)`): las dos secciones colapsarían al mismo sujeto y el
    # chequeo de coherencia pasaría **en verde** con una vista invisible.
    enfasis = str((data or {}).get("enfasis") or "").strip()
    out = [f"## Vista — {sujeto}", ""]
    if enfasis:
        out += [f"### Lente — {enfasis}", ""]
    if (aporte := _safe_links(str(data.get("aporte") or "").strip())):
        out += [f"**Aporte:** {aporte}", ""]
    ejes = {k: _safe_links(str(v).strip()) for k, v in (cfg.as_map(data.get("ejes")) or {}).items()}
    if ejes:
        # #270 — el eje contestado en VACÍO se estampa igual, con `_(sin datos)_`. Filtrándolo,
        # «se preguntó y no hay nada» era indistinguible de «nunca se preguntó», que es el mismo
        # falso limpio que #188 cierra un nivel más arriba — y sin esta línea el detector de ejes
        # faltantes nace con centenares de ítems permanentes.
        out += ["**Ejes:**", ""] + [f"- **{k}:** {str(v).strip() or SIN_DATOS}"
                                    for k, v in ejes.items()] + [""]
    filas = [f for f in cfg.as_list(data.get("ground_truth")) if isinstance(f, dict)]
    if filas:
        # «Localizador», no «Línea» (#195): la columna ya no lleva sólo un nº de línea del `.txt`.
        # Un valor levantado de una tabla-imagen se cita por PÁGINA del PDF y una lectura de
        # gráfico por `Fig. N, p. M` — llamar «Línea» a eso es la misma mentira de encabezado que
        # #200 corrige en el bloque de verificación. La CLAVE del JSON sigue siendo `linea`: el
        # artefacto vive en `build/` y renombrarla dejaría mudas las extracciones en vuelo.
        out += ["| " + " | ".join(lb.VISTA_COLS) + " |", "|" + "---|" * len(lb.VISTA_COLS)]
        for f in filas:
            # #240 — `cfg.escape_cell` ANTES de armar la fila: la prosa del extractor trae `|`
            # todo el tiempo (matemática, columnas transcritas de una tabla del paper, una
            # alternación de `grep`) y un `|` crudo PARTE la fila — las celdas de más no se
            # renderizan, así que una afirmación citada y verificada queda invisible para el lector
            # mientras el lint sigue contando su fila. Medido: 19 filas en 13 notas de un tema.
            celdas = [cfg.escape_cell(_safe_links(str(f.get(k) or "—").strip())) or "—"
                      for k in ("que", "valor", "linea", "regimen", "segunda_mano")]
            out.append("| " + " | ".join(celdas) + " |")
        out.append("")
    if (hueco := _safe_links(str(data.get("hueco") or "").strip())):
        out += [f"**Hueco:** {hueco}", ""]
    # #213 — dos bloques, no uno: la salvedad CHEQUEADA contra el archivo y la que es juicio del
    # extractor no pueden publicarse al mismo nivel visual. Ésta es la sección que el consumidor lee
    # para saber cuánto confiar en la extracción, y un defecto inventado ahí le dice que la fuente
    # está rota donde no lo está. Las FALSAS no se publican: las filtró el cosechador y las gritó.
    verificadas, prosa, _falsas = split_salvedades(str(data.get("bibcode") or ""), data)
    if verificadas:
        out += ["**Salvedades (verificadas contra el archivo):**", ""] + [
            f"- {_safe_links(s)}" for s in verificadas] + [""]
    if prosa:
        out += ["**Salvedades (⚠ NO VERIFICADAS — juicio del extractor):**", ""] + [
            f"- {_safe_links(s)}" for s in prosa] + [""]
    return "\n".join(out).rstrip("\n") + "\n"


def _norm(texto: str) -> str:
    return "\n".join(ln.rstrip() for ln in texto.strip().splitlines() if ln.strip())


# #216 — la implementación vive en `lib_config` (dos consumidores: esto y el detector de
# duplicados). El nombre local se conserva para no tocar a sus llamadores.
section_span = cfg.section_span


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
        # ⛔ AUD-203 / INV-110 — el abstract que llega por acá lo **transcribió el modelo del PDF**,
        # no es la copia de catálogo, y el contrato hace descansar en esa distinción que
        # `## Abstract` sea la capa **auditable** del cuerpo. Sin decirlo, las dos se leen igual y
        # el lector no tiene cómo saber cuál está mirando. Y el frontmatter sigue declarando
        # `sin_abstract: true` —que es historia y NO se toca: describe con qué se **clasificó** el
        # paper (título + keywords y nada más), no qué tiene la nota hoy—, así que sin esta línea la
        # nota se contradice a sí misma a la vista.
        if (_abs := str(data.get("abstract") or "").strip()):
            _abs = (f"_(transcrito del PDF por la extracción — el catálogo no lo devolvió; la nota "
                    f"sigue declarando `sin_abstract` porque así se **clasificó**.)_\n\n{_abs}")
        piezas.append(("## Abstract", _abs))
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
        # #379 — REHÚSA si el span a descartar contiene algo que no es de esta sección. Reemplazaba
        # de `ini` a `fin` sin mirar qué se llevaba, y cuando un backfill anterior dejó la cabecera
        # ADENTRO (#378) se la llevó puesta: 6 de 169 notas en UNA corrida, sin aviso y con el lint
        # en exit 0. La doctrina ya estaba escrita dos veces —#244 y #284— y ninguna cubría el
        # cuerpo de la nota; el modo de falla es el que la regla de método declara peor: una promesa
        # que el sistema deja de cumplir en silencio. Grita con el archivo, como #213 con la
        # salvedad falsa, en vez de escribir y callar.
        # ⚠ `find_header_line` se corre sobre la NOTA ENTERA y después se mira si su span cae
        # adentro: sobre el fragmento devuelve None siempre (necesita el frontmatter para acotar),
        # y ahí la guarda no dispararía nunca — un detector que no puede fallar se lee como
        # cobertura. La fuente de verdad de «qué es la cabecera» sigue siendo una (#48).
        cab = mn.header_line_anywhere(text)
        descarta = text[ini:fin]
        ajeno = ("la línea de cabecera" if cab and ini <= cab[0] < fin
                 else "un blockquote" if any(ln.lstrip().startswith(">")
                                             for ln in descarta.splitlines()) else "")
        if ajeno:
            cfg.print_seguro(f"  ⛔ {dest.name}: `{header}` contiene {ajeno} — reemplazarla la "
                             f"borraría. NO se escribe: movela a su lugar "
                             f"(`make_notes.py --fix-header-order`) y volvé a cosechar (#379)")
            return False
        nuevo = text[:ini] + cuerpo.rstrip("\n") + "\n\n" + text[fin:]
    else:
        corte = text.find("\n## Vista — ")
        punto = len(text) if corte < 0 else corte + 1
        nuevo = text[:punto].rstrip("\n") + "\n\n" + cuerpo.rstrip("\n") + "\n\n" + text[punto:]
    if nuevo == text:
        return False
    cfg.write_text_atomic(dest, nuevo)
    return True


def _lens_span(seccion: str, enfasis: str) -> tuple | None:
    """Span of the `### Lente — <énfasis>` sub-section inside a view section, or `None` (#239)."""
    marca = f"### Lente — {enfasis}"
    ini = seccion.find(marca)
    if ini < 0:
        return None
    fin = seccion.find("\n### ", ini + 1)
    return (ini, len(seccion) if fin < 0 else fin + 1)


def _write_lens_subsection(dest: Path, text: str, sujeto: str, enfasis: str, cuerpo: str, *,
                           force: bool) -> bool:
    """Write one `### Lente — <énfasis>` inside `## Vista — <sujeto>`, without touching the rest.

    The view section is created if missing; an existing sub-section with prose is NOT overwritten
    without `force` — same rule as the whole section, one level down."""
    span = section_span(text, f"## Vista — {sujeto}")
    if span is None:
        nuevo = text.rstrip("\n") + "\n\n" + cuerpo.rstrip("\n") + "\n"
    else:
        ini, fin = span
        seccion = text[ini:fin]
        sub = _lens_span(seccion, enfasis)
        # el cuerpo trae el `## Vista — X` arriba; acá se escribe SÓLO la sub-sección
        solo_sub = cuerpo[cuerpo.find(f"### Lente — {enfasis}"):] if f"### Lente — {enfasis}" in cuerpo else cuerpo
        if sub is None:
            seccion_nueva = seccion.rstrip("\n") + "\n\n" + solo_sub.rstrip("\n") + "\n"
        else:
            s_ini, s_fin = sub
            if not force and _norm(seccion[s_ini:s_fin]) != _norm(solo_sub):
                cfg.print_seguro(
                    f"  ⚠ {dest.name}: `### Lente — {enfasis}` de «{sujeto}» ya tiene prosa → NO se "
                    f"pisa (usá --force; sus anclas de verificación se vencen)")
                return False
            seccion_nueva = seccion[:s_ini] + solo_sub.rstrip("\n") + "\n" + seccion[s_fin:]
        sep = "\n" if fin < len(text) else ""
        nuevo = text[:ini] + seccion_nueva.rstrip("\n") + "\n" + sep + text[fin:]
    if nuevo == text:
        return False
    cfg.write_text_atomic(dest, nuevo)
    return True


def write_view_section(dest: Path, sujeto: str, cuerpo: str, *, theme: bool,
                       force: bool = False, enfasis: str = "") -> bool:
    """Escribe la sección de la vista. Devuelve True si tocó el archivo.

    ⛔ Sólo pisa mientras la sección sigue siendo **la plantilla del stub** (se compara contra
    `make_notes.vista_block`, la misma fuente que la escribió). Prosa ya redactada no se toca sin
    `--force`: puede estar verificada, y sus anclas cuelgan del texto exacto.

    #239 — con `enfasis`, la unidad que se escribe es la **sub-sección** `### Lente — <énfasis>`
    DENTRO de la vista del sujeto: dos lecturas del mismo sujeto con lentes distintas conviven, y
    ninguna pisa a la otra. Una sub-sección con prosa tampoco se pisa sin `--force`."""
    text = dest.read_text(encoding="utf-8")
    if enfasis:
        return _write_lens_subsection(dest, text, sujeto, enfasis, cuerpo, force=force)
    span = section_span(text, f"## Vista — {sujeto}")
    if span is None:
        nuevo = text.rstrip("\n") + "\n\n" + cuerpo
    else:
        ini, fin = span
        actual = text[ini:fin]
        if not force and _norm(actual) != _norm(mn.vista_block(sujeto, theme)):
            # AUD-200: esto se contaba como «sin cambios». Es una NEGATIVA —la sección ya tiene
            # prosa redactada, cuyas anclas cuelgan del texto exacto— y el operador tiene que
            # saber que la vista nueva NO quedó escrita; si no, la cosecha se lee como completa.
            cfg.print_seguro(
                f"  ⚠ {dest.name}: `## Vista — {sujeto}` ya tiene prosa redactada → NO se pisa "
                f"(usá --force si la querés reemplazar; sus anclas de verificación se vencen)")
            return False
        # #260: mismo splice, mismo hazard — `section_span` devuelve el fin EN el `## ` siguiente.
        sep = "\n\n" if fin < len(text) else "\n"
        nuevo = text[:ini] + cuerpo.rstrip("\n") + sep + text[fin:]
    if nuevo == text:
        return False
    cfg.write_text_atomic(dest, nuevo)
    return True


class ViewUpsertError(RuntimeError):
    """The view could not be declared in `vistas[]` — the note's frontmatter is unusable.

    Distinct from «nothing to change», which is the normal idempotent case.  @inv INV-139"""


def upsert_view(dest: Path, vista: dict, *, force: bool = False) -> bool:
    """Mergea `vista` en `vistas[]` del frontmatter, por `(sujeto, enfasis)`. True si modificó.

    Reescribe **sólo el bloque `vistas:`**, dejando el resto del frontmatter byte a byte — mismo
    criterio que `merge_frontmatter_list`: ahí abajo hay campos que tocó la extracción LLM.

    ⛔ **Un `False` significa una sola cosa: no había nada que cambiar** (AUD-200 / INV-139). Los
    tres estados de *no pude* —sin frontmatter, frontmatter sin cerrar, YAML roto— levantan
    `ViewUpsertError`, porque el llamador los contaba como «sin cambios» y **escribía igual la
    sección del cuerpo**: la nota quedaba con `## Vista — X` y sin la entrada en `vistas[]`, que es
    justo la incoherencia que el lint bloquea. Declarar la lectura y escribirla son una operación,
    no dos."""
    import yaml
    text = dest.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ViewUpsertError("la nota no arranca con frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ViewUpsertError("el frontmatter no cierra con `---`")
    head = text[4:end]
    try:
        data = yaml.safe_load(head) or {}
    except yaml.YAMLError as exc:
        raise ViewUpsertError(
            f"el frontmatter no parsea ({' '.join(str(exc).split())[:80]})") from exc
    previas = [v for v in cfg.as_list(data.get("vistas")) if isinstance(v, dict)]
    nuevas, visto = [], False
    for v in previas:
        # #239 — la identidad de una vista es `(sujeto, enfasis)`, no el sujeto a secas. Con la
        # clave vieja, una segunda lectura del mismo sujeto con OTRA lente entraba por esta rama y
        # `{**v, **vista}` **pisaba la anterior en silencio**: no es que la segunda lectura no
        # estuviera soportada, es que era destructiva.
        if cfg.vista_key(v) == cfg.vista_key(vista):
            # Y aun con la MISMA clave el merge es add-only: completa lo que falta (`fecha`, `txt`)
            # y **rehúsa** cambiar un valor ya escrito. Un valor distinto bajo la misma clave es
            # otra lectura mal declarada, y resolverla en silencio es lo que este issue arregla.
            choques = [k for k, nuevo in vista.items()
                       if k in v and str(v[k] or "").strip()
                       and str(nuevo or "").strip() != str(v[k] or "").strip()]
            if choques and not force:
                raise ViewUpsertError(
                    f"la vista de «{vista['sujeto']}»"
                    + (f" (lente «{vista['enfasis']}»)" if vista.get("enfasis") else "")
                    + f" ya declara otro valor en {', '.join(sorted(choques))}: si es otra lectura, "
                      f"declarala con su propio `enfasis`; si querés reemplazarla, --force")
            nuevas.append({**v, **vista} if force else {**vista, **v})
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
    src = src or (cfg.EXTRACCION / slug)     # #311: versionadas, no en `build/`
    n = {"cosechadas": 0, "rechazadas": 0, "sin_nota": 0, "sin_cambios": 0, "txt_traidos": 0}
    if not src.exists():
        cfg.print_seguro(f"  (sin {src}; nada que cosechar)")
        return n
    # #307 — la `lente` de la vista guarda LOS EJES QUE SE PREGUNTARON, que es lo que hace posible
    # el diff de D-49 a nivel de lectura. Con ejes propios del tema, registrar las facetas globales
    # describiría una lectura que no ocurrió.
    _tmeta = None
    try:
        _tmeta = cfg.theme_by_slug(slug)[1] if theme else None
    except (KeyError, RuntimeError):
        _tmeta = None
    lente = cfg.theme_axes(_tmeta)
    if lente is None:
        lente = mn.objective_lens()[0]
    hoy = _dt.date.today().isoformat()
    refutados: list = []               # #212 · (bibcode, [sujetos]) — para el aviso de cierre
    salvedades_falsas: list = []       # #213 · (bibcode, detalle) — chequeadas y desmentidas
    citas_dudosas: list = []           # #359 · (bibcode, cita) — el `.txt` contradice a la extracción
    # #371 — la identidad de una VISTA es el par `(sujeto, enfasis)`, y desde que el nombre del
    # archivo sale de la lente puede haber varios JSON del mismo bibcode. Dos que declaren el mismo
    # par compiten por la misma sub-sección y el cosechador escribiría una y después la otra sin
    # decir nada. AVISA y no rechaza: las dos son artefactos caros (#311) y cuál gana lo decide
    # quien las produjo.
    vistos_par: dict = {}
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
        # #228/#374 — la identidad es el `bibcode` DE ADENTRO, y la resuelve la MISMA función
        # que usan los otros lectores de `raw/extraccion/`: con una copia por consumidor ya
        # divergieron una vez, y el que quedó atrás dio un gate en verde sobre 309 citas.
        bib = cfg.extraction_identity(data)
        par = (bib, sujeto, str(vista.get("enfasis") or "").strip())
        if par in vistos_par:
            cfg.print_seguro(f"  ⚠ {archivo.name}: declara el mismo par (bibcode, sujeto, lente) "
                             f"que `{vistos_par[par]}` — «{par[0]}» sobre «{par[1]}»"
                             + (f", lente «{par[2]}»" if par[2] else " (sin lente)")
                             + ": son dos lecturas compitiendo por la misma sub-sección (#371)")
        vistos_par.setdefault(par, archivo.name)
        dest = cfg.PAPERS / f"{mn.safe_name(bib)}.md"
        if not dest.exists():
            n["sin_nota"] += 1
            # #331 — con el slug pelado, en un tema el remedio que se imprime no corre (`KeyError`).
            cfg.print_seguro(f"  ⚠ {bib}: no hay nota en papers/ — corré "
                             f"`{cfg.make_notes_cmd(slug)}`")
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
        # #230 — `txt` se CRUZA contra el disco, igual que `fuente` dos líneas más arriba. Se
        # estampaba lo que el extractor dijera (o el slug, por default), así que 9 notas de una
        # bóveda real declaraban `txt: ica` sin que existiera `raw/fulltext/ica/<bib>.txt` — el
        # contrato lo llama «el ancla de fuente cuando el mismo bibcode vive bajo varios slugs», y
        # un ancla que apunta a un archivo inexistente no ancla nada.
        #
        # ⚠ NO se rechaza la extracción, y la asimetría con `fuente: pdf` es deliberada: desde #205
        # se lee el PDF, así que una vista `fuente: pdf` puede no tener `.txt` en absoluto y
        # rechazarla tiraría una lectura buena. Se degrada declarando: si el `.txt` declarado no
        # está pero existe bajo otro slug, se apunta ahí; si no existe en ningún lado, la clave NO
        # se escribe —«no consta», que es distinto de un puntero falso— y se avisa.
        # #372 — la lente de una vista son los ejes que se PREGUNTARON. `theme_axes` se resolvía una
        # vez antes del bucle, así que una SEGUNDA lente con `--ejes` propios (#308) quedaba
        # declarando los del tema, que nadie le preguntó: medido, 13 de 13 vistas, solapamiento 0 de
        # 7. Rompe INV-146 en su enunciado literal, y con eso el diff de D-49 describe otra lectura.
        # ⛔ El discriminante es `enfasis`, no «qué trae el JSON»: con una lectura normal las claves
        # del JSON son lo CONTESTADO —el extractor puede dejar afuera las que no aplican— y tomarlas
        # como lente encogería el denominador del detector de ejes sin contestar (#254/#270), que
        # pasaría de medir cobertura a no poder medirla. `enfasis` es la marca DECLARADA de que esta
        # lectura se pidió con otra lente, así que ahí sus claves sí son lo preguntado.
        _propios = cfg.as_map(data.get("ejes"))
        lente_vista = list(_propios) if (vista.get("enfasis") and _propios) else list(lente)
        entrada = {"sujeto": sujeto, "tipo": tipo, "fecha": hoy, "lente": lente_vista}
        # #239 — la lente con la que se leyó, si la extracción declara una. Ausente = la lectura
        # por default del sujeto; presente = una segunda lectura que CONVIVE con la anterior.
        if (_enfasis := str((cfg.as_map(data.get("vista")) or {}).get("enfasis") or "").strip()):
            entrada["enfasis"] = _enfasis
            data["enfasis"] = _enfasis
        txt_real = _resolve_txt_slug(bib, str(vista.get("txt") or slug))
        if txt_real:
            entrada["txt"] = txt_real
        else:
            cfg.print_seguro(f"  ⚠ {archivo.name}: no hay `raw/fulltext/**/{bib}.txt` en disco — la "
                             f"vista se estampa SIN `txt:` (no consta) en vez de apuntar a un "
                             f"archivo que no existe")
        if fuente:
            entrada["fuente"] = fuente
        # #212 — el único canal en la dirección que faltaba: la lectura puede REFUTAR el reclamo que
        # la trajo. `stars`/`thesis_links` son reclamos sembrados ANTES de leer, y el merge es
        # add-only (bien: protege la extracción de que un re-seed la pise), así que un reclamo falso
        # era INFALSIFICABLE por la lectura — la nota quedaba con `thesis_links: [ica]` y una vista
        # adjunta diciendo, textual, que el paper no tiene nada que ver con ICA. #188 daba dos
        # salidas para un reclamo SIN vista (hacerla, o declarar `no_vista`) y ninguna para el
        # tercer caso: hice la vista y el reclamo es FALSO.
        # ⛔ Se REGISTRA, no se aplica: borrar el reclamo sería un LLM editando curación en
        # silencio, y además la decisión es del par (paper, sujeto) —el paper puede ser core de
        # otro—. Mismo patrón que `triage --accept-source`: arma la decisión, no la toma.
        refuta = sorted({str(x).strip() for x in cfg.as_list(data.get("refuta")) if str(x).strip()})
        if refuta:
            entrada["refuta"] = refuta
            refutados.append((bib, refuta))
        try:
            toco = upsert_view(dest, entrada)
        except ViewUpsertError as exc:
            # AUD-200 / INV-139 — si la vista no se puede DECLARAR, la sección del cuerpo tampoco
            # se escribe: una `## Vista — X` sin su entrada en `vistas[]` es la incoherencia que el
            # lint bloquea, y dejarla sería cambiar un fallo visible por uno que hay que descubrir.
            n["rechazadas"] += 1
            cfg.print_seguro(f"  ⛔ {archivo.name}: no se pudo declarar la vista de «{sujeto}» "
                             f"({exc}) → la nota queda sin tocar")
            continue
        for campo in ("methods", "thesis_links", "role"):
            valores = [str(x).strip() for x in cfg.as_list(data.get(campo)) if str(x).strip()]
            if valores and mn.merge_frontmatter_list(dest, campo, valores):
                toco = True
        # #213 — la salvedad estructurada que NO resiste su propio chequeo no se publica, y se
        # GRITA: es una afirmación fabricada sobre el artefacto, justo en la sección que el
        # consumidor lee para saber cuánto confiar. ⚠ No se rechaza la extracción entera (a
        # diferencia de `fuente: pdf` sin PDF, #207): aquello es una contradicción sobre QUÉ se
        # abrió —no se puede saber cuál mitad miente— y esto es un campo secundario que se puede
        # descartar sin tirar la lectura, que es la mitad más cara de la cadena.
        for _detalle in split_salvedades(bib, data)[2]:
            salvedades_falsas.append((bib, _detalle))
            cfg.print_seguro(f"  ⛔ {bib}: salvedad FALSA, no se publica — {_detalle}")
        # #359 — el cruce contra el `.txt` corría sobre la NOTA, así que una cita mal transcrita AL
        # LEER EL PDF pasaba por acá sin que nadie la mirara y sólo se cazaba si llegaba a una ficha
        # (medido: 2 de 265 valores de una ingesta, las dos nacidas en la extracción). Importa dónde
        # se caza: una extracción no se regenera (#311) y alimenta a N sujetos, así que verla en el
        # origen es verla UNA vez en lugar de una por nota. ⛔ Se LLAMA a la regla, no se
        # re-implementa (#324), y AVISA sin rechazar: el `.txt` es índice degradado (#205) y
        # rechazar produciría falsos negativos sobre extracciones correctas — la misma asimetría
        # que #213 ya eligió para la salvedad falsa.
        _lecturas = cfg.fulltext_readings(bib)
        for _v in cfg.as_list(data.get("ground_truth")):
            for _q in (cfg.quotes_in(str(cfg.as_map(_v).get("valor") or "")) if _lecturas else []):
                # ⚠ Sin guarda de «ya está en el `.txt`»: una cita presente ENTERA no puede acusar
                # —el prefijo común la cubre toda y termina en letra, así que la corta el borde de
                # palabra—, y un condicional que no decide nada es una regla escrita a medias
                # (#319). En `contrast` el orden sí decide, porque ahí el veredicto es otro.
                _ac = cfg.txt_accuses(_q, _lecturas)
                if _ac:
                    citas_dudosas.append((bib, _q))
                    cfg.print_seguro(
                        f"  ⚠ {bib}: el `.txt` trae el arranque de «{_q[:60]}…» y sigue distinto "
                        f"(«…{_ac['cola_txt'][:60]}»). Son DOS lecturas del mismo PDF y la fuente es "
                        f"el PDF: andá a la página antes de propagar esta cita (#359/#333)")
        _enf = str(data.get("enfasis") or "").strip()
        if write_view_section(dest, sujeto, render_view(sujeto, data), theme=theme, force=force,
                              enfasis=_enf):
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
    if salvedades_falsas:
        cfg.print_seguro(f"\n⛔ {len(salvedades_falsas)} salvedad(es) ESTRUCTURADAS resultaron "
                         f"FALSAS contra el archivo y NO se publicaron (#213). Una afirmación "
                         f"fabricada sobre el artefacto le dice al próximo lector que la fuente "
                         f"está rota donde no lo está:")
        for bib, detalle in salvedades_falsas:
            cfg.print_seguro(f"  - {bib}: {detalle}")
    if refutados:
        # El comando queda listo para pegar, con el motivo puesto: sin él la decisión se toma igual
        # pero el registro no dice por qué, que es lo único que sirve dentro de seis meses.
        cfg.print_seguro(f"\n⚠ {len(refutados)} lectura(s) REFUTAN el reclamo que las trajo (#212). "
                         f"La vista lo deja registrado; sacar el paper del sujeto lo decidís vos "
                         f"(puede ser core de OTRO sujeto):")
        for bib, sujetos in refutados:
            cfg.print_seguro(f"  - {bib} → refuta: {', '.join(sujetos)}")
            cfg.print_seguro(f"      python scripts/triage.py {slug} --drop-core {bib} "
                             f"--reason \"la vista del paper no sostiene el reclamo de "
                             f"{', '.join(sujetos)}\"")
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
    cfg.cli_exit(main)
