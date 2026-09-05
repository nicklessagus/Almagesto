"""La pasada de red UNIFICADA: todo lo que cambia afuera, en un solo lugar (D-41/D-45/D-46).

Uso:
    python scripts/sweep_external.py            # reporta el diff y pregunta antes de aplicar
    python scripts/sweep_external.py --yes      # no interactivo: aplica lo aplicable

QUÉ PROBLEMA CIERRA. Una bóveda afirma cosas sobre el mundo, y el mundo cambia después del ingest.
Hasta 1.29.0 existía **un solo** detector —retracciones/correcciones vía Crossref— y las otras
cuatro cosas que caducan no las miraba nadie:

  1. **retracciones**   — la fuente dejó de ser válida (frontera dura).
  2. **correcciones**   — un corrigendum cambia justo el número que se extrajo (#52).
  3. **versiones**      — el preprint salió publicado: otro bibcode para el mismo trabajo (D-19).
  4. **snapshot web**   — la URL de una fuente off-ADS ya no dice lo mismo.
  5. **ground-truth**   — NEA cambia valores entre releases, y el snapshot es un JSON congelado que
     **nada** comparaba: el caso más silencioso de los cinco.
  6. **citas-puerta2**  — el `citation_count` que la puerta 2 de D-26 usa para admitir un paper como
     core es la única metadata que cambia sola: un paper puede volverse core sin que nadie edite
     el paper ni la regla (#106). Entró después que los cinco de arriba.

Seis cosas que caducan y un solo momento para mirarlas — si están repartidas, se corren cinco y
la sexta nunca.

⛔ **REPORTA, no aplica solo — con UNA excepción declarada.** El diff se muestra siempre y se
pregunta antes de tocar nada: un snapshot que se actualiza solo cambia valores **bajo los pies de la
prosa que ya los citó**, y el consumidor no tiene forma de enterarse.

⚠ **La excepción es `retracciones`**, y hay que decirla acá arriba y no 47 líneas más abajo, porque
la promesa de cabecera se leía como absoluta: `check_retractions` **escribe** `retracted:` /
`corrections:` en las notas sin preguntar, y se conserva así a propósito — una fuente retractada
citada rompe la frontera dura, así que enterarse tarde es peor que el ruido de diff, y lo que estampa
es una **marca de metadata**, no un valor que la prosa haya citado. Los otros cinco detectores no
escriben nada: versiones y web **proponen el comando**, ground-truth pregunta, y citas-puerta2
sólo reporta el cruce (aplicarlo es re-correr la cadena del tema). Lo que sí es automático es la consecuencia offline: al
cambiar un `.txt`, el **ancla de fuente** (D-20) marca sola los pares verificados contra él.

El renombre preprint→publicado **nunca** es automático: reescribe wikilinks de toda la bóveda
(D-19), así que se propone el comando y decide una persona.

**Caducidad (D-46/R-4):** la fecha de la última pasada se registra en
`vault/config/registro/_red.yaml`, **versionado** — "cuándo se miró afuera por última vez" es
información sobre la bóveda, no sobre la máquina que corrió la pasada: sin versionarla, otro clon
reporta "nunca se corrió", que es falso. El **lint no la reporta** (D-46: es hecho del entorno y
del tiempo, no una inconsistencia de la bóveda); la muestra el dashboard.

Exit code, heredado del contrato del issue 0.1:
    0  corrió y no hay nada que revisar
    1  corrió y hay cambios pendientes de revisión
    2  no pudo chequear (precondición ausente)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys

import yaml

import lib_config as cfg
import fetch_ground_truth
from make_notes import rename_paper       # noqa: F401  (lo usan los tests como grabador)

# ── los seis detectores (#106 sumó `sweep_citas`) ─────────────────────────────────────────────────────────────────────────
#
# Cada uno vive en SU script (el que ya sabe hablar con esa fuente) y acá sólo se orquestan. Estas
# funciones son la fachada: los tests las graban, y mover un detector de script no cambia el
# orquestador.

def _run(script: str, *args: str) -> int:
    return subprocess.run([sys.executable, str(cfg.ROOT / "scripts" / script), *args],
                          cwd=cfg.ROOT / "scripts").returncode


def sweep_retracciones() -> list:
    """Barrido Crossref de TODA la bóveda (sin `--slug`). Estampa `retracted` donde corresponde —
    es el único de los cinco que ya escribía, y se conserva: una fuente retractada citada rompe la
    frontera dura, así que enterarse tarde es peor que el ruido de diff.

    ⚠ `check_retractions` tiene **tres** códigos y acá se leían dos: `0` limpio, `1` encontró algo,
    **`2` no pudo chequear** (red caída, papers sin identificador). El `if rc == 1` colapsaba el 2
    contra el 0, así que "no se miró" salía como "limpio" y `cubrio` registraba la pasada como
    hecha. Es el cero inventado de D-43 en el detector que más caro sale equivocar. Ahora el 2
    levanta, que es como esta pasada expresa *no evaluado*."""
    rc = _run("check_retractions.py")
    if rc == 2:
        raise NotImplementedError(
            "check_retractions salió 2 (no pudo chequear: red caída, o papers sin DOI/identificador "
            "con que preguntar) — la bóveda NO quedó barrida; ver su salida para el motivo")
    return ["retracciones/correcciones detectadas — ver las notas marcadas"] if rc == 1 else []


def sweep_correcciones() -> list:
    """Papers con corrección publicada (erratum/corrigendum/EoC), leídos del vault (#52).

    Las correcciones las **estampa** el mismo barrido de Crossref que las retracciones, así que acá
    no se vuelve a la red: se leen del frontmatter. Es un detector propio porque su consecuencia es
    distinta — el paper **sigue citable**; lo que hay que revisar son los valores que se le
    extrajeron, porque un corrigendum corrige justo el número que la ficha destiló.

    ⚠ Devolvía `[]` fijo y aun así contaba como cubierto: la pasada decía "cubrió: correcciones" y
    no listaba ninguna. Es la misma familia del cero inventado que `sweep_web` evita levantando —
    con la diferencia de que acá el dato SÍ está, sólo que nadie lo leía."""
    out = []
    for f in cfg.note_paths(cfg.PAPERS):
        fm = cfg.split_fm(f.read_text(encoding="utf-8"))
        correcciones = [c for c in cfg.as_list(fm.get("corrections")) if isinstance(c, dict)]
        if correcciones:
            tipos = ", ".join(dict.fromkeys(str(c.get("type")) for c in correcciones))
            out.append(f"{f.stem}: {tipos} — revisá los valores extraídos de este paper")
    return out


def stamp_version_disponible(stem: str, nuevo_bib: str) -> bool:
    """Stamp `versions_disponible: <bibcode>` on the note, so the finding SURVIVES the run (#298).

    ⛔ Versions was the only one of the six expiries leaving **nothing** in the vault: retractions
    stamp `retracted`, corrections stamp `corrections`, ground-truth writes `_cambios` and the lint
    demands a mark, web and citations propose a command. This one printed one line to stdout — run
    the pass, don't act right then, and the finding is gone: not in the note, not in `log.md`, not
    in the lint, and the next pass rediscovers it from scratch. Same treatment as `corrections`,
    which also does not invalidate the paper: it is a metadata MARK, not a value the prose cited,
    so stamping it without asking is the same exception the retraction branch already carries.

    ⚠ It is NOT `versions[]`: that field declares an alias of the SAME work already resolved, and a
    bibcode listed there with its own note blocks (#229). This one says *"there is a published
    version and nobody renamed anything yet"* — the lint reports it as backlog with the command."""
    dest = cfg.PAPERS / f"{stem}.md"
    if not dest.exists():
        return False
    texto = dest.read_text(encoding="utf-8")
    lim = cfg.fm_bounds(texto)
    if lim is None:
        return False
    ini, fin = lim
    lineas = texto[ini:fin].split("\n")
    want = f"versions_disponible: {nuevo_bib}"
    for i, ln in enumerate(lineas):
        if ln.startswith("versions_disponible:"):
            if ln == want:
                return False
            lineas[i] = want
            break
    else:
        lineas.append(want)
    cfg.write_text_atomic(dest, texto[:ini] + "\n".join(lineas) + texto[fin:])
    return True


def discover_versions(solo: set | None = None, meta: dict | None = None) -> tuple[list, list]:
    """`[(bibcode_viejo, bibcode_nuevo)]` — preprints que ya salieron publicados (D-19).

    `solo` acota el barrido a unos bibcodes concretos (#297). Existe para el momento del **reuso
    D-18**: cuando un tema nuevo importa el artefacto que ya estaba bajo otro slug, se ahorra la
    descarga y además se hereda un archivo cuya antigüedad nadie chequeó — y la respuesta natural
    («si hubiera versión nueva, la búsqueda habría traído OTRO bibcode y D-19 los une») es falsa
    justo en el caso frecuente: el DOI del preprint identifica el *depósito*, así que #216
    **garantiza** que preprint y publicado no colisionen. Acotado son unidades, no el corpus.

    Por cada nota con `arxiv_id` cuyo bibcode es de eprint (`…arXiv…`), se le pregunta a ADS qué
    bibcodes tiene ese arXiv id. Si aparece uno que **no** es de eprint, el trabajo salió publicado
    y hay dos identidades para el mismo paper.

    **No renombra: propone.** El renombre reescribe wikilinks de toda la bóveda, y eso no se hace
    sin que alguien lo pida.

    Devuelve `(hallazgos, fallidos)`. Los fallos son **por nota** y no tumban la pasada (un sujeto
    raro no debe llevarse puesta la corrida), pero **se declaran**: con ADS caído todas las notas
    fallan, la función devolvía `[]` y el orquestador registraba "cubrió: versiones" sobre un
    barrido que no miró nada. Tragarse el error y devolver la lista vacía es el cero inventado."""
    import query_ads
    out, fallidos = [], []
    notas = cfg.note_paths(cfg.PAPERS)
    miradas = 0
    for f in notas:
        if solo is not None and f.stem not in solo:
            continue
        fm = cfg.split_fm(f.read_text(encoding="utf-8"))
        arxiv = fm.get("arxiv_id")
        if not arxiv or "arXiv" not in str(fm.get("bibcode") or ""):
            continue
        # #298 — la POBLACIÓN, declarada. El filtro es correcto por contrato (D-19 es sobre
        # IDENTIDAD, y una nota que ya tiene bibcode publicado no tiene problema de identidad), pero
        # `cubrió: versiones` sobre 3 de 138 notas se lee como «se miraron las versiones de la
        # bóveda». Es INV-40 aplicado a la pasada de red, el único carril que no lo hacía.
        miradas += 1
        ya_alias = {str(v.get("bibcode")) for v in cfg.as_list(fm.get("versions"))
                    if isinstance(v, dict)}
        try:
            # `fq=None`: sin la lente astro (#68). Acá el universo de búsqueda ya lo fija el
            # arXiv id —se busca UN trabajo concreto, no se descubre nada—, y `database:astronomy`
            # descartaría justo los casos que este detector existe para encontrar: un método de
            # otra disciplina (stat.ML, cs.LG) que salió publicado fuera de una revista astro.
            # Mismo criterio que `fetch_bibcodes`.
            recs = query_ads.query_ads(f'arxiv:"{arxiv}"', rows=10, quiet_truncate=True, fq=None)
        except Exception as exc:                      # noqa: BLE001 — red ajena, por nota
            cfg.print_seguro(f"  ✗ {f.stem}: no se pudo consultar ADS por arXiv:{arxiv} ({exc})")
            fallidos.append(f.stem)
            continue
        for r in recs:
            bib = r.get("bibcode")
            if bib and "arXiv" not in bib and bib != f.stem and bib not in ya_alias:
                out.append((f.stem, bib))
                if stamp_version_disponible(f.stem, bib):
                    cfg.print_seguro(f"    · {f.stem}: `versions_disponible: {bib}` estampado "
                                     f"(el hallazgo sobrevive a la corrida — #298)")
                break
    if meta is not None:
        meta.update(miradas=miradas, notas=len(notas))
    return out, fallidos


def sweep_web() -> tuple[list, list]:
    """Snapshots web que ya no dicen lo mismo (D-41). `(hallazgos, fallidos)`.

    Es el modo de caducidad **más silencioso** de los cinco: una fuente web no tiene ni DOI ni
    bibcode, nada avisa que cambió, y —a diferencia de un `.txt` re-extraído— el archivo local no se
    toca, así que **el ancla de fuente (D-20) tampoco se entera**. Las citas verificadas contra ella
    quedan apuntando a un texto que ya no dice eso.

    ⛔ **Reporta, no aplica** (D-45): el diff se muestra y re-snapshotear es decisión del usuario
    (`fetch_web.py <slug> <citekey> <url> --force`). Escribir el snapshot nuevo cambiaría el texto
    **bajo los pies de la prosa que ya lo citó**; lo que sí es automático es la consecuencia
    offline, porque al reescribir el `.txt` el ancla marca sola los pares verificados contra él.

    Un snapshot sin `source_url` en el header, o cuya URL no contesta, es **fallido** — no "no
    cambió": el registro de caducidad no puede afirmar haber mirado lo que no miró."""
    import fetch_web
    out, fallidos = [], []
    if not cfg.FULLTEXT.exists():
        return out, fallidos
    for txt in sorted(cfg.FULLTEXT.glob("*/*.txt")):
        cabeza = txt.read_text(encoding="utf-8", errors="replace")[:400]
        if cfg.FULLTEXT_WEB_MARK not in cabeza:
            continue                       # no es un snapshot web: no hay URL que re-bajar
        slug, citekey = txt.parent.name, txt.stem
        try:
            cambio = fetch_web.refresh(slug, citekey)
        except Exception as exc:           # noqa: BLE001 — red/URL ajena, por snapshot
            cfg.print_seguro(f"  ✗ {slug}/{citekey}: no se pudo re-bajar ({exc})")
            fallidos.append(f"{slug}/{citekey}")
            continue
        if cambio:
            viejo, nuevo = cambio
            out.append(f"{slug}/{citekey}: el snapshot cambió ({viejo} → {nuevo}) → revisá las "
                       f"citas que lo usan y re-snapshoteá con `python scripts/fetch_web.py "
                       f"{slug} {citekey} <url> --force`")
    return out, fallidos


def sweep_ground_truth() -> tuple[list, list]:
    """`([(slug, [(campo, viejo, nuevo)])], fallidos)` — qué cambió en NEA/SIMBAD desde cada snapshot,
    y **qué sujetos no se pudieron mirar**.

    Los dos valores hacen falta: con NEA caída todos los sujetos fallan, la lista de cambios queda
    vacía y sin los fallidos el orquestador registra "cubrió: ground-truth · 0 cosas para revisar"
    sobre una pasada que no comparó nada — y la próxima toma ese registro como línea de base."""
    out, fallidos = [], []
    for nombre, meta in cfg.load_stars().items():
        slug = meta.get("slug") if isinstance(meta, dict) else None
        if not slug or not (cfg.GROUND_TRUTH / f"{slug}.json").exists():
            continue
        try:
            cambios = fetch_ground_truth.nea_diff(slug)
        except Exception as exc:                     # red ajena: un sujeto raro no tumba la pasada
            cfg.print_seguro(f"  ✗ {slug}: no se pudo diffear contra NEA ({exc})")
            fallidos.append(slug)
            continue
        if cambios:
            out.append((slug, cambios))
    return out, fallidos


def sweep_citas() -> tuple[list, list]:
    """`([(slug, [(bibcode, viejo, nuevo)])], fallidos)` — papers de un tema de método que **cruzaron
    el umbral de la puerta 2** desde que se los clasificó.

    LA SEXTA COSA QUE CAMBIA AFUERA (#106), y la última que no tenía detector. La puerta 2 de D-26
    admite un paper por `citation_count`; ese número es metadata del paper (así que INV-24 se
    sostiene y el veredicto sigue siendo re-derivable offline) pero **cambia solo con el tiempo**. La
    función es estable y su entrada deriva: un paper puede volverse core sin que nadie edite ni el
    paper ni la regla, y nada lo decía. Las otras cinco caducidades ya se miran acá y la respuesta
    nunca fue congelar el dato — es detectar, reportar y **no aplicar solo**.

    Su gemelo offline es `lib_config.puerta2_cruces`, que ve *"editaste el umbral"*; esto ve *"el
    mundo se movió"*, y por eso necesita red y vive acá. Devuelve los fallidos por la misma razón
    que `sweep_ground_truth`: con ADS caída todos los temas fallan, la lista de cruces queda vacía y
    sin los fallidos el registro afirmaría haber mirado lo que no miró.  @inv INV-104"""
    out, fallidos = [], []
    for slug, meta in cfg.load_themes().items():
        meta = cfg.as_map(meta)
        # AUD-142: la forma del umbral la decide la MISMA función que el clasificador.
        umbral, _mal = cfg.gate2_threshold(meta)
        if umbral is None:
            continue                     # puerta cerrada por no declarada: nada que vigilar
        try:
            import query_ads
            notas = {(fm.get("bibcode") or stem): fm
                     for stem, fm, _t in cfg.notes_of_subject(slug)}
            bibs = [b for b in notas if not str(b)[:1].isdigit() or "." in str(b)]
            # AUD-158 — las claves sintéticas off-ADS (`2006Rasmussen`) NO son consultables en ADS y
            # se salteaban **mudas**: la pasada las contaba como miradas y el registro afirmaba
            # haber vigilado su conteo de citas. Es el cero inventado de D-43 dentro del detector
            # que existe para ver que el mundo se movió. No son un fallo (es una propiedad de la
            # clave, no una caída de red), así que van aparte de `fallidos` y se nombran.
            if (sin_clave := sorted(set(notas) - set(bibs))):
                cfg.print_seguro(
                    f"  · {slug}: {len(sin_clave)} nota(s) con clave sintética off-ADS — a esas "
                    f"NADIE les re-consultó el conteo, así que la puerta 2 queda sin vigilancia "
                    f"para ellas ({', '.join(str(b) for b in sin_clave[:3])}…)")
            frescos = {r["bibcode"]: r.get("citation_count")
                       for r in query_ads.fetch_bibcodes(bibs)} if bibs else {}
        except Exception as exc:         # noqa: BLE001 — red ajena: un tema raro no tumba la pasada
            cfg.print_seguro(f"  ✗ {slug}: no se pudo re-consultar el conteo de citas ({exc})")
            fallidos.append(slug)
            continue
        cruces = []
        for bib, fm in notas.items():
            viejo, nuevo = fm.get("citation_count"), frescos.get(bib)
            if not isinstance(viejo, (int, float)) or not isinstance(nuevo, (int, float)):
                continue                 # sin uno de los dos no hay cruce que afirmar
            if (viejo >= umbral) != (nuevo >= umbral):
                cruces.append((bib, viejo, nuevo))
        if cruces:
            out.append((slug, sorted(cruces)))
    return out, fallidos


def aplicar_ground_truth(slug: str) -> None:
    """Re-baja el snapshot (`--force`) y **deja registrado qué se movió**, en `_cambios` del JSON.

    Al aplicar, un valor retirado va a `null` — decisión del usuario en D-45. El registro hace falta
    porque el ancla de fuente NO cubre esto: hashea `raw/fulltext/**/*.txt`, nunca
    `raw/ground_truth/<slug>.json`, así que un valor que NEA corrige cambia **bajo los pies de la
    prosa que ya lo citó** y ninguna fila de verificación se entera (AUD-42). Con `_cambios` el lint
    puede pedir la tercera marca en línea, `⚠desactualizado`.

    Se calcula ANTES de re-bajar (después, el diff contra sí mismo da vacío) y se persiste DESPUÉS,
    sobre el payload nuevo."""
    try:
        cambios = fetch_ground_truth.nea_diff(slug)
    except Exception as exc:
        cfg.print_seguro(f"  ✗ {slug}: no se pudo diffear antes de aplicar ({exc}) — no se aplica")
        return
    # AUD-222 — el `returncode` se ignoraba: con la re-bajada fallida el JSON seguía con el valor
    # viejo y `_cambios` decía que cambió, y el lint pedía `⚠desactualizado` sobre el vigente.
    if _run("fetch_ground_truth.py", slug, "--force"):
        cfg.print_seguro(f"  ✗ {slug}: la re-bajada FALLÓ — el snapshot no cambió y no se registra "
                         f"ningún `_cambios` (volvé a correr)")
        return
    if not cambios:
        return
    out = cfg.GROUND_TRUTH / f"{slug}.json"
    try:
        payload = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        cfg.print_seguro(f"  ✗ {slug}: se aplicó pero no se pudo registrar `_cambios` ({exc})")
        return
    payload["_cambios"] = _merge_changes(payload.get("_cambios"), cambios)
    fetch_ground_truth.write_ground_truth(slug, payload)
    cfg.print_seguro(
        f"  · {slug}: {len(cambios)} valor(es) cambiaron — la prosa que los citaba NO se actualizó "
        f"sola. Revisala y, si la dejás como está, marcala con `⚠desactualizado`.")


def _merge_changes(previos, cambios) -> list:
    """Acumula la caducidad PENDIENTE de ground-truth, por campo (#130).

    Acá había una asignación (`payload["_cambios"] = [...]`), así que la segunda pasada borraba lo
    de la primera: la marca `⚠desactualizado` que el lint pedía por un campo desaparecía **sin que
    nadie la hubiera resuelto**, con la prosa todavía citando el valor viejo. Es lo contrario de
    D-28/`busquedas` y de `save_barrido`, que acumulan porque el registro guarda justamente lo que
    no es regenerable.

    Acumular no es duplicar: un campo tiene UNA caducidad pendiente —la prosa dice `viejo`, NEA hoy
    dice `nuevo`—, así que si vuelve a cambiar se actualiza. El `viejo` que se conserva es el
    **original**: es el que está escrito en la nota. El intermedio no lo escribió nadie nunca.
    """
    hoy = dt.date.today().isoformat()
    out = [dict(c) for c in (previos or []) if isinstance(c, dict)]
    por_campo = {c.get("campo"): c for c in out}
    for campo, v, n in cambios:
        if campo in por_campo:
            por_campo[campo].update(nuevo=n, fecha=hoy)     # `viejo` NO se toca: es lo que la nota cita
        else:
            fila = {"campo": campo, "viejo": v, "nuevo": n, "fecha": hoy}
            out.append(fila); por_campo[campo] = fila
    return out


# ── la caducidad, versionada (D-46 / R-4) ────────────────────────────────────────────────────────

def save_ultima_pasada(cubrio: list, no_evaluados: list | None = None,
                       poblaciones: dict | None = None) -> None:
    """Persiste qué se miró afuera y **qué no se pudo mirar** (#172).

    Acá se guardaba sólo `cubrio`, así que en el archivo versionado un detector que falló
    parcialmente quedaba **byte-idéntico** a uno que nunca corrió: el aviso vivía sólo en stdout, que
    es el mismo modo de falla con el que #55 y #88 mudaron el triage y el barrido al registro. El
    propio módulo justifica versionar la caducidad porque *"sin versionarla, otro clon reporta
    'nunca se corrió', que es falso"* — y no declarar el fallo parcial es la otra mitad de eso.

    `no_evaluados` sólo aparece cuando hay algo que declarar: un `[]` fijo en cada pasada sería ruido
    en el único artefacto de la bóveda que no es regenerable."""
    cfg.REGISTRO.mkdir(parents=True, exist_ok=True)
    pasada = {"fecha": dt.date.today().isoformat(),
              "cubrio": sorted(cubrio),
              "version": cfg.ALMAGESTO_VERSION}
    if no_evaluados:
        pasada["no_evaluados"] = [{"detector": n, "motivo": m} for n, m in no_evaluados]
    # #298 — SOBRE CUÁNTAS miró cada detector. «cubrió: versiones» sobre 3 de 138 notas se lee como
    # «se miraron las versiones de la bóveda», que es el mismo `(0)` sin denominador que INV-40
    # prohíbe en el lint. Sólo aparece cuando hay algo que declarar (el registro no es regenerable).
    if poblaciones:
        pasada["poblaciones"] = {k: dict(v) for k, v in poblaciones.items() if v}
    cfg.write_text_atomic(cfg.red_path(), yaml.safe_dump(
        {"ultima_pasada_red": pasada}, sort_keys=False, allow_unicode=True))


# ── orquestador ──────────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    # @inv INV-85 — the six detectors run from here, and the diff is shown before anything applies
    cfg.stdout_tolerante()
    ap = argparse.ArgumentParser(
        description="Pasada de red unificada: retracciones, correcciones, versiones, snapshots web, "
                    "ground-truth y cruces del umbral de la puerta 2. Reporta el diff y pregunta "
                    "antes de aplicar.")
    ap.add_argument("--yes", action="store_true",
                    help="no interactivo: aplica lo aplicable sin preguntar (queda registrado)")
    ap.add_argument("--bibcodes", metavar="B1,B2",
                    help="#297: corre SÓLO el detector de versiones, acotado a esos bibcodes. Es "
                         "lo que el reuso D-18 deja pendiente —un artefacto importado a un sujeto "
                         "nuevo cuya antigüedad nadie chequeó— y son unidades, no el corpus. No "
                         "registra la pasada: mirar 7 papers no es haber mirado la bóveda.")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    if args.bibcodes:
        pedidos = {b.strip() for b in args.bibcodes.split(",") if b.strip()}
        versiones, fallidos = discover_versions(solo=pedidos)
        for viejo_b, nuevo_b in versiones:
            cfg.print_seguro(f"  · versiones: {viejo_b} salió publicado como {nuevo_b} → "
                             f"`python scripts/make_notes.py --rename-paper {viejo_b} {nuevo_b}`")
        if fallidos:
            cfg.print_seguro(f"  ⛔ {len(fallidos)} sin poder mirar: {', '.join(fallidos[:5])}")
        sin_nota = sorted(pedidos - {f.stem for f in cfg.note_paths(cfg.PAPERS)})
        if sin_nota:
            cfg.print_seguro(f"  ⚠ sin nota en la bóveda (no se miraron): {', '.join(sin_nota[:5])}")
        if not versiones:
            cfg.print_seguro(f"  versiones: nada nuevo sobre {len(pedidos) - len(sin_nota)} "
                             f"bibcode(s) mirado(s) — ⚠ esto NO es una pasada de red completa")
        return 0

    cubrio, pendientes = [], 0
    poblaciones: dict = {}          # #298: sobre cuántas notas miró cada detector

    def _cubrir(nombre: str, fallidos: list) -> None:
        """`cubrio` sólo si el detector realmente miró. Un fallo por ítem no tumba la pasada —a
        propósito— pero tampoco puede desaparecer: si TODOS los ítems fallaron, el detector no
        cubrió nada; si falló una parte, el registro dice cuántos quedaron sin mirar. Antes esto
        era un `append` incondicional escrito **antes** de la llamada."""
        if fallidos:
            no_evaluados.append((nombre, f"{len(fallidos)} sujeto(s) sin poder mirar: "
                                         f"{', '.join(fallidos[:5])}"
                                         + (" …" if len(fallidos) > 5 else "")))
            cfg.print_seguro(f"  ⛔ {nombre}: {len(fallidos)} sujeto(s) NO evaluado(s)")
        else:
            cubrio.append(nombre)

    no_evaluados = []
    for nombre, detector in (("retracciones", sweep_retracciones),
                             ("correcciones", sweep_correcciones)):
        try:
            hallazgos = detector()
        except NotImplementedError as exc:
            # D-43 aplicado a la pasada de red: un detector que no corrió NO aporta un cero, y no
            # entra en `cubrio` — el registro de caducidad no puede afirmar haber mirado lo que no
            # miró. Otro clon leería "cubrió: web" y no sería cierto.
            no_evaluados.append((nombre, str(exc)))
            cfg.print_seguro(f"  ⛔ {nombre}: NO EVALUADO — {exc}")
            continue
        cubrio.append(nombre)
        for h in hallazgos:
            cfg.print_seguro(f"  · {nombre}: {h}")
        pendientes += len(hallazgos)

    # ⚠ `cubrio.append` va DESPUÉS de que el detector devuelva, no antes. Estaba antes de la
    # llamada, así que el registro versionado `_red.yaml` afirmaba "cubrió: versiones,
    # ground-truth" aunque los dos hubieran fallado en todos sus sujetos —los errores por ítem se
    # loguean y se saltean, por diseño: un sujeto raro no debe tumbar la pasada—. Un registro que
    # dice haber mirado lo que no miró es peor que uno vacío: la próxima pasada lo toma como línea
    # de base. Si el detector se lleva puesta la corrida entera, es *no evaluado*, no *cubierto*.
    try:
        web, w_fallidos = sweep_web()
    except Exception as exc:                          # noqa: BLE001 — red ajena
        no_evaluados.append(("web", str(exc)))
        cfg.print_seguro(f"  ⛔ web: NO EVALUADO — {exc}")
    else:
        _cubrir("web", w_fallidos)
        for h in web:
            cfg.print_seguro(f"  · web: {h}")
        pendientes += len(web)

    vmeta: dict = {}
    try:
        versiones, v_fallidos = discover_versions(meta=vmeta)
    except Exception as exc:                          # noqa: BLE001 — red ajena
        no_evaluados.append(("versiones", str(exc)))
        cfg.print_seguro(f"  ⛔ versiones: NO EVALUADO — {exc}")
    else:
        _cubrir("versiones", v_fallidos)
        # #298 — INV-40 en la pasada de red: `cubrió: versiones` sin población se lee como «se
        # miraron las versiones de la bóveda», y son las notas cuyo bibcode SIGUE siendo el eprint
        # (medido: 3 de 138). El filtro es correcto; lo que faltaba era decirlo.
        cfg.print_seguro(f"  > versiones: sobre {vmeta.get('miradas', 0)} nota(s) con bibcode de "
                         f"eprint, de {vmeta.get('notas', 0)} notas de paper")
        poblaciones["versiones"] = dict(vmeta)
        for viejo, nuevo in versiones:
            # se PROPONE: el renombre reescribe wikilinks de toda la bóveda (D-19).
            cfg.print_seguro(f"  · versiones: {viejo} salió publicado como {nuevo} → "
                             f"`python scripts/make_notes.py --rename-paper {viejo} {nuevo}`")
            pendientes += 1

    try:
        gt_cambios, gt_fallidos = sweep_ground_truth()
    except Exception as exc:                          # noqa: BLE001 — red ajena
        no_evaluados.append(("ground-truth", str(exc)))
        cfg.print_seguro(f"  ⛔ ground-truth: NO EVALUADO — {exc}")
        gt_cambios = []
    else:
        _cubrir("ground-truth", gt_fallidos)
    for slug, cambios in gt_cambios:
        cfg.print_seguro(f"  · ground-truth: {slug} cambió en NEA/SIMBAD desde el snapshot:")
        for campo, viejo, nuevo in cambios:
            cfg.print_seguro(f"      {campo}: {viejo!r} → {nuevo!r}")
        pendientes += len(cambios)

    try:
        cit_cruces, cit_fallidos = sweep_citas()
    except Exception as exc:                          # noqa: BLE001 — red ajena
        no_evaluados.append(("citas-puerta2", str(exc)))
        cfg.print_seguro(f"  ⛔ citas-puerta2: NO EVALUADO — {exc}")
        cit_cruces = []
    else:
        _cubrir("citas-puerta2", cit_fallidos)
    for slug, cruces in cit_cruces:
        cfg.print_seguro(f"  · citas-puerta2: {slug} — papers que cruzaron el umbral de la puerta 2:")
        for bib, viejo, nuevo in cruces:
            cfg.print_seguro(f"      {bib}: {viejo} → {nuevo} citas")
        cfg.print_seguro("      → el veredicto core cambiaría sin que nadie editara el paper ni la "
                         "regla. Re-corré la cadena del tema para aplicarlo (no se aplica solo).")
        pendientes += len(cruces)

    save_ultima_pasada(cubrio, no_evaluados, poblaciones)

    if gt_cambios:
        # El diff YA se mostró. Aplicar es lo que se pregunta — no lo que se hace y después se avisa.
        if args.yes or (sys.stdin.isatty() and
                        input("  ¿aplicar los snapshots de ground-truth? [y/N] ").strip().lower() == "y"):
            for slug, _ in gt_cambios:
                aplicar_ground_truth(slug)
        else:
            cfg.print_seguro("  → no se aplicó nada. Re-corré con --yes, o "
                             "`python scripts/fetch_ground_truth.py <slug> --force` por sujeto.")

    faltantes = (f" · NO evaluado: {', '.join(n for n, _ in no_evaluados)}" if no_evaluados else "")
    cfg.print_seguro(f"\nPasada de red {dt.date.today().isoformat()} · cubrió: {', '.join(cubrio)}"
                     f"{faltantes} · {pendientes} cosa(s) para revisar · registro en "
                     f"`vault/config/registro/{cfg.RED_FILE}`")
    if no_evaluados:
        return 2          # contrato del issue 0.1: "no pudo chequear" gana sobre "limpio"
    return 1 if pendientes else 0


if __name__ == "__main__":
    cfg.cli_exit(main)
