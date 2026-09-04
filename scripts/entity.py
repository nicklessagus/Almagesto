"""Borrar o renombrar una ENTIDAD (estrella / tema) sin dejar nada colgado — INV-19.

    python scripts/entity.py plan   <slug>                 # qué toca (no escribe nada)
    python scripts/entity.py rename <viejo> <nuevo> --yes  # renombrar en las ocho capas
    python scripts/entity.py delete <slug> --yes           # borrar en las ocho capas

POR QUÉ EXISTE. El contrato promete que *"después de borrar o renombrar una entidad no queda
ninguna referencia colgada **en ninguna capa** ni archivo huérfano en `raw/`"*, y hasta hoy eso era
un **procedimiento en prosa** del skill `maintain`: nueve pasos a mano, en orden, sobre ocho
lugares distintos. El único renombre con herramienta era el de un PAPER (`make_notes
--rename-paper`), que es el caso chico. Un procedimiento manual de nueve pasos no es una garantía:
es una lista de cosas que alguien puede saltear, y las que se saltean no dejan rastro —el lint
tenía red para `wiki/` (wikilinks rotos, huérfanos) y **ninguna** para el registro, los directorios
de `raw/`, la entrada del YAML ni `build/`.

LAS OCHO CAPAS de una entidad, que es la lista que hay que no olvidar:

  1. la clave en `vault/config/stars.yaml` (o `themes.yaml`)
  2. `vault/config/registro/<slug>.yaml`   ← el ÚNICO artefacto no regenerable
  3. `vault/raw/ground_truth/<slug>.json`
  4. `vault/raw/pdfs/<slug>/`
  5. `vault/raw/fulltext/<slug>/` y `vault/raw/extraccion/<slug>/` (#311: la extracción es el
     artefacto MÁS caro y vive versionada, no en `build/`)
  6. la nota: `vault/wiki/stars/<slug>.md` (estrella) o `concepts/<area>/<concept>.md` (tema)
  7. su hermano de auditoría `<nota>.verif.md` (#344: la tabla de verificación vive ahí)
  8. `build/<slug>/`  (scratch, pero si queda se re-propone triage de una entidad que no existe)

  …más las **referencias**: los `[[wikilink]]` de toda la bóveda y los `stars:` / `thesis_links:`
  del frontmatter de las notas de paper.

⛔ **DESTRUCTIVO: no aplica sin `--yes`.** Sin el flag imprime el plan y sale. Es la misma doctrina
que `sweep_external` ("reporta, no aplica solo"), y acá con más razón: la capa 2 no se regenera.

⚠ **Un paper compartido NO se borra.** Una nota con `stars: [A, B]` pertenece a las dos: al borrar
A se le saca A del frontmatter y la nota queda. Si con eso se queda **sin ningún destino** (D-23)
se **avisa**, porque pasa a ser un hallazgo bloqueante del lint — y borrarla en silencio sería
decidir por el usuario sobre trabajo de extracción ya pagado.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml

import lib_config as cfg


def buscar(slug: str) -> tuple[str, str, dict] | None:
    """`(tipo, clave_yaml, meta)` o `None` si el slug no existe. `tipo` es `star` o `theme`.

    La clave del YAML **no** es el slug en los dos casos: en `stars.yaml` la clave es el nombre
    canónico (`tau Cet`) y el slug es un campo; en `themes.yaml` la clave ES el slug. Confundirlos
    es la forma más fácil de dejar la entrada del YAML colgada.

    Existe aparte de `resolver` porque hay **dos** llamadores con contratos distintos: el CLI de
    este script muere con un mensaje, y el lint (#121) tiene que poder quejarse con su propio exit
    sin que un `sys.exit` ajeno lo saque del medio."""
    for nombre, meta in cfg.load_stars().items():
        if isinstance(meta, dict) and meta.get("slug") == slug:
            return "star", nombre, meta
    themes = cfg.load_themes()
    if slug in themes:
        return "theme", slug, cfg.as_map(themes[slug])
    return None


def resolver(slug: str) -> tuple[str, str, dict]:
    """`buscar` con la queja del CLI: SystemExit si la entidad no existe."""
    hit = buscar(slug)
    if hit is None:
        sys.exit(f"entidad desconocida: {slug!r} — no está en stars.yaml ni en themes.yaml")
    return hit


def nota_de(tipo: str, slug: str, meta: dict) -> Path:
    """La nota de la entidad. Para un tema depende de `area`/`concept`, no del slug."""
    if tipo == "star":
        return cfg.STARS / f"{slug}.md"
    return cfg.CONCEPTS / str(meta.get("area") or "") / f"{(meta.get('concept') or slug)}.md"


def capas(slug: str, tipo: str, meta: dict) -> list[tuple[str, Path]]:
    """Las capas EN DISCO de la entidad, en el orden del docstring. Sólo las que existen.

    **Una sola lista de capas** para las tres operaciones y para el chequeo del lint: la cobertura
    de INV-19 se había construido por accidente, un hermano por vez (el ground-truth colgado se
    agregó porque alguien lo pisó de verdad), y de ahí que faltaran cuatro.  @inv INV-19"""
    candidatas = [
        ("registro", cfg.registro_path(slug)),
        ("ground_truth", cfg.GROUND_TRUTH / f"{slug}.json"),
        ("pdfs", cfg.PDFS / slug),
        ("fulltext", cfg.FULLTEXT / slug),
        ("extraccion", cfg.EXTRACCION / slug),     # #311
        ("nota", nota_de(tipo, slug, meta)),
        # #344 — la OCTAVA capa: el hermano de auditoría de la nota. Borrar la nota y dejarlo es
        # exactamente el hermano huérfano que el lint bloquea, y renombrar sin llevarlo lo deja
        # apuntando a una nota que ya no existe.
        ("verif", cfg.verif_sidecar(nota_de(tipo, slug, meta))),
        ("build", cfg.ROOT / "build" / slug),
    ]
    return [(k, p) for k, p in candidatas if p.exists()]


#: Los nombres de las capas de `capas()`, en su orden. Se derivan de la función, no se re-tipean:
#: `plan` publicaba «de 6» sobre siete capas y su lista de faltantes omitía `extraccion` — dos
#: números escritos a mano que ya habían quedado atrás de la única lista que manda.
CAPAS = ("registro", "ground_truth", "pdfs", "fulltext", "extraccion", "nota", "verif", "build")


def _campo_de(tipo: str) -> str:
    """Por qué campo del frontmatter de un paper se referencia esta entidad."""
    return "stars" if tipo == "star" else "thesis_links"


def referencias(nombre: str, tipo: str) -> tuple[list, list]:
    """`(notas_de_paper_que_la_referencian, notas_con_wikilink)`.

    Se lee el frontmatter con `split_fm`, **no** con grep: `stars: [tau Cet]` en flow style y en
    bloque conviven en el mismo corpus, y el matcheo textual confunde `GJ 71` con `GJ 710`."""
    campo = _campo_de(tipo)
    papers, wikis = [], []
    for f in sorted(cfg.WIKI.rglob("*.md")):
        texto = f.read_text(encoding="utf-8")
        if nombre in cfg.as_list(cfg.split_fm(texto).get(campo)):
            papers.append(f)
        if f"[[{nombre}]]" in texto or f"[[{nombre}|" in texto:
            wikis.append(f)
    return papers, wikis


def notas_del_slug(slug: str) -> set[str] | None:
    """Los **stems de nota** que pertenecen a una entidad: su ficha/concepto y sus papers.
    `None` si el slug no existe.

    Es el alcance de `lint --cierre <slug>` (#121). Tres poblaciones, **unión**, porque ninguna
    sola cubre lo que una operación toca:
      (a) la nota de la entidad (`nota_de`: para un tema NO se llama como el slug);
      (b) los papers cuyo ARTEFACTO vive bajo el slug (`raw/fulltext/<slug>/`, `raw/pdfs/<slug>/`)
          — la población que bajó este ingest, y la única que existe antes de que se escriba
          ninguna nota;
      (c) los papers que REFERENCIAN a la entidad en su frontmatter — así entra el **retro-linkeo**
          (un paper ya extraído por otro sujeto que este tema también usa: su `.txt` vive bajo el
          slug ajeno, así que (b) no lo ve).

    En un tema se miran `thesis_links` **y** `methods` (D-24: las dos llaves viven en papers
    distintos y quedarse con una pierde la mitad), y se aceptan tanto el slug como el `concept`,
    que pueden diferir.

    @inv INV-105"""
    hit = buscar(slug)
    if hit is None:
        return None
    tipo, nombre, meta = hit
    stems = {nota_de(tipo, slug, meta).stem}
    for carpeta, suf in ((cfg.FULLTEXT / slug, ".txt"), (cfg.PDFS / slug, ".pdf")):
        if carpeta.is_dir():
            stems |= {p.name[:-len(suf)] for p in carpeta.glob("*" + suf)}
    campos = ("stars",) if tipo == "star" else ("thesis_links", "methods")
    # AUD-156 / INV-105 — sin los `aliases` el alcance perdía papers REALES: `make_notes` mergea en
    # `stars[]` el nombre con el que la entidad se nombró en ese ingest, y una bóveda usa los alias
    # todo el tiempo (`HD 10700` por `tau Ceti`). Un paper tagueado así quedaba fuera del gate de
    # cierre de su propio sujeto —o sea que `lint --cierre tau_ceti` daba verde sobre deuda suya— y
    # fuera del barrido de capas de `entity delete`.
    claves = {nombre, slug, str(meta.get("concept") or slug)}
    claves |= {str(a) for a in cfg.as_list(meta.get("aliases")) if str(a).strip()}
    for f in cfg.note_paths(cfg.PAPERS):
        fm = cfg.split_fm(f.read_text(encoding="utf-8"))
        if any(claves & set(cfg.as_list(fm.get(campo))) for campo in campos):
            stems.add(f.stem)
    return stems


def _yaml_sin(path: Path, clave: str) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if isinstance(data, dict) and clave in data:
        data.pop(clave)
        cfg.write_text_atomic(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def _yaml_renombrar(path: Path, vieja: str, nueva: str, *, slug_nuevo: str | None = None) -> None:
    """Renombra la clave preservando el ORDEN del archivo (un `pop`+`update` la manda al final, y
    el YAML de config lo edita gente: reordenarlo ensucia el diff sin motivo)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(data, dict) or vieja not in data:
        return
    out = {}
    for k, v in data.items():
        if k == vieja:
            if slug_nuevo and isinstance(v, dict):
                v = {**v, "slug": slug_nuevo}
            out[nueva] = v
        else:
            out[k] = v
    cfg.write_text_atomic(path, yaml.safe_dump(out, sort_keys=False, allow_unicode=True))


def _quitar_del_frontmatter(f: Path, campo: str, valor: str) -> bool:
    """Saca `valor` de la lista `campo` del frontmatter. Cirugía a nivel texto (familia
    `merge_frontmatter_list`): preserva byte a byte el resto, incluida la extracción LLM."""
    texto = f.read_text(encoding="utf-8")
    span = cfg.frontmatter_span(texto)
    if span is None:
        return False
    head, resto = span
    lineas = head.split("\n")
    out, dentro, cambio = [], False, False
    for ln in lineas:
        if ln.startswith(f"{campo}:"):
            rest = ln[len(campo) + 1:].strip()
            if rest.startswith("[") and rest.endswith("]"):
                items = [x.strip() for x in rest[1:-1].split(",") if x.strip()]
                nuevos = [x for x in items if x != valor]
                cambio = cambio or len(nuevos) != len(items)
                out.append(f"{campo}: [{', '.join(nuevos)}]")
                continue
            dentro = True
            out.append(ln)
            continue
        if dentro:
            if ln.lstrip().startswith("- "):
                if ln.lstrip()[2:].strip() == valor:
                    cambio = True
                    continue
                out.append(ln)
                continue
            dentro = False
        out.append(ln)
    if not cambio:
        return False
    # ⚠ Reconstrucción EXACTA: `head` ya viene con su `\n` inicial y final desde
    # `frontmatter_span`. Agregar `"\n---\n"` metía una línea en blanco DENTRO del
    # frontmatter y `resto.lstrip("\n")` borraba la de después del `---`: las dos rompían el
    # "byte a byte" que el docstring promete (AUD-38/39, auditoría 2026-08-24).
    cfg.write_text_atomic(f, "---" + "\n".join(out) + "---" + resto)
    return True


def _renombrar_en_frontmatter(f: Path, campo: str, viejo: str, nuevo: str) -> bool:
    texto = f.read_text(encoding="utf-8")
    span = cfg.frontmatter_span(texto)
    if span is None:
        return False
    head, resto = span
    out, dentro, cambio = [], False, False
    for ln in head.split("\n"):
        if ln.startswith(f"{campo}:"):
            rest = ln[len(campo) + 1:].strip()
            if rest.startswith("[") and rest.endswith("]"):
                items = [x.strip() for x in rest[1:-1].split(",") if x.strip()]
                nuevos = [nuevo if x == viejo else x for x in items]
                cambio = cambio or nuevos != items
                out.append(f"{campo}: [{', '.join(nuevos)}]")
                continue
            dentro = True
            out.append(ln)
            continue
        if dentro:
            if ln.lstrip().startswith("- "):
                if ln.lstrip()[2:].strip() == viejo:
                    cambio = True
                    out.append(ln[:len(ln) - len(ln.lstrip())] + f"- {nuevo}")
                    continue
                out.append(ln)
                continue
            dentro = False
        out.append(ln)
    if not cambio:
        return False
    cfg.write_text_atomic(f, "---" + "\n".join(out) + "---" + resto)
    return True


def _reescribir_wikilinks(viejo: str, nuevo: str) -> int:
    """`[[viejo]]` / `[[viejo|alias]]` → `[[nuevo…]]` en toda la bóveda. Deliberadamente **no**
    toca el nombre suelto en prosa: un texto que menciona la estrella no es un link a su nota, y un
    replace ciego lo reescribiría (mismo criterio que `make_notes._wikilink_re`)."""
    # AUD-218 — la MISMA regex que `make_notes` (anclas `#`/`^` incluidas) y el MISMO alcance:
    # `vault/`, no `wiki/` — `STATUS.md` también linkea entidades y quedaba colgado.
    rx = cfg.wikilink_re(viejo)
    n = 0
    for f in sorted(cfg.VAULT.rglob("*.md")):
        texto = f.read_text(encoding="utf-8")
        nuevo_texto = rx.sub(lambda m: f"[[{nuevo}{m.group(1)}", texto)
        if nuevo_texto != texto:
            cfg.write_text_atomic(f, nuevo_texto)
            n += 1
    return n


def plan(slug: str) -> int:
    """Imprime qué tocaría una operación sobre esta entidad. No escribe nada."""
    tipo, nombre, meta = resolver(slug)
    cfg.print_seguro(f"{slug} — {tipo}, clave en YAML: {nombre!r}")
    cs = capas(slug, tipo, meta)
    cfg.print_seguro(f"\ncapas en disco ({len(cs)} de {len(CAPAS)}):")
    for k, p in cs:
        marca = "  ⚠ NO REGENERABLE" if k == "registro" else ""
        cfg.print_seguro(f"  · {k:<12} {p}{marca}")
    faltan = set(CAPAS) - {k for k, _ in cs}
    if faltan:
        cfg.print_seguro(f"  (no existen: {', '.join(sorted(faltan))})")
    papers, wikis = referencias(nombre, tipo)
    cfg.print_seguro(f"\nreferencias: {len(papers)} nota(s) de paper con `{_campo_de(tipo)}: "
                     f"{nombre}` · {len(wikis)} nota(s) con `[[{nombre}]]`")
    for f in papers[:10]:
        cfg.print_seguro(f"  · {f.relative_to(cfg.WIKI)}")
    if len(papers) > 10:
        cfg.print_seguro(f"  · … y {len(papers) - 10} más")
    return 0


def delete(slug: str, yes: bool) -> int:
    """Borra la entidad en las ocho capas. Dry-run sin `--yes`.  @inv INV-19"""
    tipo, nombre, meta = resolver(slug)
    cs = capas(slug, tipo, meta)
    papers, wikis = referencias(nombre, tipo)
    if not yes:
        plan(slug)
        cfg.print_seguro("\n⛔ dry-run: no se borró nada. Repetí con `--yes` para aplicar.\n"
                         "   (el registro NO es regenerable: guardá una copia si dudás)")
        return 0
    campo = _campo_de(tipo)
    huerfanos = []
    for f in papers:
        _quitar_del_frontmatter(f, campo, nombre)
        fm = cfg.split_fm(f.read_text(encoding="utf-8"))
        if not any(cfg.as_list(fm.get(k)) for k in ("stars", "thesis_links", "methods")):
            huerfanos.append(f.stem)
    for k, p in cs:
        shutil.rmtree(p) if p.is_dir() else p.unlink()
        cfg.print_seguro(f"  ✗ {k}: {p}")
    _yaml_sin(cfg.STARS_YAML if tipo == "star" else cfg.THEMES_YAML, nombre)
    cfg.print_seguro(f"  ✗ entrada {nombre!r} de "
                     f"{'stars.yaml' if tipo == 'star' else 'themes.yaml'}")
    cfg.print_seguro(f"\n{slug} borrado. {len(papers)} nota(s) de paper perdieron `{campo}: {nombre}`.")
    if wikis:
        # No se tocan los `[[wikilink]]`: apuntan a una nota que ya no existe y el lint los reporta
        # como BLOQUEANTES. Repararlos automáticamente sería decidir por el usuario qué decía esa
        # frase; dejarlos rotos y visibles es la conducta correcta.
        cfg.print_seguro(f"⚠ {len(wikis)} nota(s) tienen `[[{nombre}]]`, que ahora es un wikilink "
                         f"ROTO (bloqueante en el lint): repará o quitá cada uno —")
        for f in wikis[:10]:
            cfg.print_seguro(f"    · {f.relative_to(cfg.WIKI)}")
    if huerfanos:
        cfg.print_seguro(f"⚠ {len(huerfanos)} nota(s) de paper quedaron SIN destino (D-23, "
                         f"bloqueante): {', '.join(huerfanos[:8])}"
                         + (" …" if len(huerfanos) > 8 else "")
                         + "\n    No se borran: son extracción ya pagada. Reasignalas o borralas a mano.")
    cfg.print_seguro("→ cerrá con `python scripts/lint.py --cierre` (tiene que dar 0)")
    return 0


def rename(viejo: str, nuevo: str, yes: bool) -> int:
    """Renombra el slug en las ocho capas. Dry-run sin `--yes`.  @inv INV-19"""
    tipo, nombre, meta = resolver(viejo)
    if not yes:
        plan(viejo)
        cfg.print_seguro(f"\n⛔ dry-run: no se renombró nada. Repetí con `--yes` para aplicar "
                         f"({viejo} → {nuevo}).")
        return 0
    # ⛔ La guarda mira LAS OCHO CAPAS, con la misma lista que usan las tres operaciones. Miraba
    # dos (`registro` y `fulltext`), así que renombrar sobre un slug con ground-truth y ficha los
    # **pisaba**: `Path.rename` sobreescribe en POSIX, y el script salía con 0 y mensaje de éxito.
    # Reproducido en la pasada `/auditar` del 2026-08-28: la síntesis cara del LLM de la ficha
    # destino desapareció, `stars.yaml` quedó con dos entradas con el mismo slug, y el daño es
    # **invisible después** — el espejo #70 compara la ficha nueva contra el JSON nuevo y da
    # consistente. Es exactamente lo que el mensaje de abajo dice que no puede pasar.
    # La capa `nota` de un TEMA se excluye porque el rename no la toca (#169: se llama por
    # `concept`, no por slug), así que su existencia no es una colisión.
    ocupadas = [k for k, _ in capas(nuevo, tipo, meta)
                if not (k in ("nota", "verif") and tipo != "star")]
    if ocupadas:
        sys.exit(f"ya hay artefactos bajo el slug {nuevo!r} ({', '.join(ocupadas)}) — renombrar "
                 f"encima fusionaría dos entidades en silencio y PISARÍA esas capas. Elegí otro "
                 f"slug o borrá la que sobra primero (`entity.py delete {nuevo}`).")
    for capa, p in capas(viejo, tipo, meta):
        if capa in ("nota", "verif") and tipo != "star":
            # ⛔ #169. La nota de un TEMA se llama por `concept`, un campo APARTE del slug: renombrar
            # el slug no la toca. Acá había un `p.name.replace(viejo, nuevo, 1)` con un guard
            # `if p.name == destino.name: continue`, que sólo cubre el caso en que el slug NO aparece
            # en el nombre. Con `ica` → nota `ica-bss.md` —la forma normal— la nota se movía y
            # `themes.yaml` seguía apuntando a `ica-bss`: la entidad quedaba SIN NOTA ALCANZABLE y
            # los `[[wikilink]]` rotos, mientras el script imprimía que había renombrado.
            # ⚠ Su hermano de verificación (#344) va con ella: mover uno sin el otro rompe el par.
            continue
        destino = p.parent / p.name.replace(viejo, nuevo, 1)
        if p.name == destino.name:
            continue                       # nada que mover en esta capa
        p.rename(destino)
        cfg.print_seguro(f"  → {p.name} → {destino.name}")
    if tipo == "star":
        # En `stars.yaml` la clave es el NOMBRE canónico y el slug es un campo: se renombra el campo
        # y la clave se deja (renombrar la estrella es otra operación).
        _yaml_renombrar(cfg.STARS_YAML, nombre, nombre, slug_nuevo=nuevo)
        cfg.print_seguro(f"  → stars.yaml: {nombre!r} ahora tiene slug {nuevo!r}")
        cfg.print_seguro("\nnota: los `[[wikilink]]` y los `stars:` apuntan al NOMBRE de la "
                         "estrella, que no cambió — no hace falta reescribirlos.")
    else:
        _yaml_renombrar(cfg.THEMES_YAML, viejo, nuevo)
        n_fm = sum(_renombrar_en_frontmatter(f, "thesis_links", viejo, nuevo)
                   for f in cfg.note_paths(cfg.PAPERS))
        n_wl = _reescribir_wikilinks(viejo, nuevo)
        cfg.print_seguro(f"  → themes.yaml: {viejo!r} → {nuevo!r} · {n_fm} frontmatter(s) · "
                         f"{n_wl} nota(s) con wikilinks reescritos")
    cfg.print_seguro("→ cerrá con `python scripts/lint.py --cierre` (tiene que dar 0)")
    return 0


def main(argv=None) -> int:
    cfg.stdout_tolerante()
    ap = argparse.ArgumentParser(
        description="Borrar o renombrar una ENTIDAD (estrella/tema) en sus ocho capas (INV-19). "
                    "Destructivo: sin --yes sólo imprime el plan.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="qué tocaría (no escribe nada)")
    p_plan.add_argument("slug")
    p_del = sub.add_parser("delete", help="borrar la entidad en las ocho capas")
    p_del.add_argument("slug")
    p_del.add_argument("--yes", action="store_true", help="aplicar (sin esto es dry-run)")
    p_ren = sub.add_parser("rename", help="renombrar el slug de la entidad")
    p_ren.add_argument("viejo")
    p_ren.add_argument("nuevo")
    p_ren.add_argument("--yes", action="store_true", help="aplicar (sin esto es dry-run)")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])
    if args.cmd == "plan":
        return plan(args.slug)
    if args.cmd == "delete":
        return delete(args.slug, args.yes)
    return rename(args.viejo, args.nuevo, args.yes)


if __name__ == "__main__":
    cfg.cli_exit(main)
