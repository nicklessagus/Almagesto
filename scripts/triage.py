"""Compuerta de triage de los candidatos del citation chaining (#38).

Uso:
    python scripts/triage.py <slug>                                   # listar los candidatos pendientes
    python scripts/triage.py <slug> --report                          # + tabla en outputs/triage-<slug>.md
    python scripts/triage.py <slug> --drop <bib> [<bib> …] --reason "<motivo>"
    python scripts/triage.py <slug> --drop-source <clave> […] --reason "<motivo>" [--pointer <url|doi>]
    python scripts/triage.py <slug> --drop-core <bib> […] --reason "<motivo>"      # #112: sacar un CORE del sujeto
    python scripts/triage.py <slug> --accept-source <doi> […] --via <via> --reason "<motivo>"  # #111: entrada lista para pegar
    python scripts/triage.py <slug> --promote-source <clave> --bibcode <bib>    # fuente off-ADS que resultó tener bibcode
    python scripts/triage.py <slug> --prioridad                                # core agrupados por puerta (#126)
    python scripts/triage.py <slug> --extraccion todos|subconjunto [--reason …]  # D-13: qué se leyó
    python scripts/triage.py <slug> --sintesis [--n-papers N] [--reason …]     # INV-82: fecha de síntesis
    python scripts/triage.py <slug> --migrate                 # consolidar el triage.json pre-1.9.0

El chaining trae papers conectados por citas al corpus del sujeto. La lente
(`relevance.facets`) clasifica **tema**, no **pertinencia al sujeto**: anclado a "menciona al
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
  Los candidatos que **ya tienen nota** en la bóveda (entraron por OTRO slug — papers de método
  curados a otra estrella) se marcan (#42): no se filtran, se etiquetan, porque la decisión sigue
  siendo por-slug. La marca distingue **tres** estados y no dos (#189): `◆` hay vista fechada de
  ESTE sujeto (ya se leyó desde acá), `◇` hay nota pero ninguna vista de este sujeto (se leyó desde
  otro eje: el PDF y el `.txt` ya están, la LECTURA no está hecha), y sin marca es un candidato
  nuevo. Que la nota exista significa que alguien la **creó**, no que alguien la haya **leído** desde
  este ángulo: `make_notes` mergea los seeds add-only sin leer nada, y medido en una bóveda real 141
  de 908 notas las reclaman 2+ sujetos sin una sola segunda extracción. El `◆` viejo le decía al
  operador «ya está leído, despachalo rápido» sobre papers que nadie leyó desde ese eje — una
  premisa falsa orientando una decisión de curación humana.
- **2 — informe al usuario:** `--report` deja la tabla en `outputs/triage-<slug>.md` (título, año,
  citas, vía, tópicos, link a ADS) para decidir los **dudosos** por lote.

**El otro carril de curación: las fuentes DECLARADAS (`--drop-source`, #81).** En un tema off-ADS
no hay descubrimiento —la bibliografía se declara una por una en `sources:` de `themes.yaml`—, así
que ahí `sources:` registra lo aceptado y el rechazo ("miré este libro / esta URL y decidí que no es
core") no quedaba en ningún lado. Es la misma asimetría de #51 en el otro carril: el juicio de
rechazo es tan **no regenerable** como el del triage y se perdía igual al cambiar de máquina o al
volver seis meses después. `--drop-source` lo escribe en las MISMAS `decisiones` del registro
versionado (no inventa mecanismo), con `origen: fuente-declarada` para distinguir el carril y un
`fuente:` opcional (url/doi/ruta), que es lo que vuelve resoluble una clave sintética. No necesita
`build/<slug>/ads.json`: un tema off-ADS puro no lo tiene. Lo consume `ingest_theme`, que **avisa**
si un item de `sources:` lleva una clave ya descartada — el equivalente de "no re-proponer".

Este script NO decide: lista y persiste. El juicio es del agente/usuario.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import urllib.parse
import json
import sys

import yaml

import lib_config as cfg
import make_notes                       # #217: la limpieza de `pdf:`/`fulltext:` vive donde se estampan

ADS_URL = "https://ui.adsabs.harvard.edu/abs/"


def load_ads(slug: str) -> dict:
    f = cfg.ROOT / "build" / slug / "ads.json"
    if not f.exists():
        sys.exit(f"no existe build/{slug}/ads.json — corré primero la cadena de ingest "
                 f"(o python scripts/query_ads.py {slug}).")
    return json.loads(f.read_text(encoding="utf-8"))


def prioridad(slug: str) -> int:
    """#87 · la cola de EXTRACCIÓN, ordenada por cuánto del objetivo toca cada core.

    `classify()` ya calcula **qué facetas** del objetivo matcheó cada paper y lo persiste (en el
    registro y en el frontmatter de la nota), y aguas abajo eso se usaba **sólo para mostrar**: un
    paper que toca 4 facetas y uno que toca la mínima para pasar el corte eran indistinguibles para
    todo lo que viene después — incluido el paso más caro de la cadena.

    Por qué esta señal y no las citas: citas/año mide **atención de la comunidad**; el número de
    facetas mide **pertinencia a lo que ESTA bóveda quiere saber**, que es la pregunta que la
    priorización tiene que responder. Sale gratis (ya está computada) y es la única que no hereda el
    sesgo de edad de #79 — por eso las citas quedan como desempate, no como criterio.

    ⛔ NO es un filtro y no toca la lente: `relevant` no se recalcula acá. Es un ORDEN sobre los core
    que ya son core, para que el recorte de lectura (D-13) se declare sobre un criterio y no sobre
    lo que apareció primero.

    @inv INV-111"""
    recs = [r for r in load_ads(slug).get("records", []) if r.get("relevant")]
    if not recs:
        cfg.print_seguro(f"{slug}: ningún core en build/{slug}/ads.json")
        return 0
    recs.sort(key=lambda r: (-len(cfg.as_list(r.get("facets"))), -(r.get("citation_count") or 0),
                             r.get("bibcode") or ""))
    cfg.print_seguro(f"\n{slug}: {len(recs)} core por PERTINENCIA (facetas del objetivo, "
                     f"citas como desempate)\n")
    # La cuarta superficie del marcador (#189): ésta es la cola de LECTURA, así que «leído desde
    # este sujeto» (`◆`) vs «tiene nota, leído desde otro eje» (`◇`) es exactamente lo que hay que
    # ver acá para decidir el recorte.
    subject = subject_name(slug)
    for r in recs:
        f = cfg.as_list(r.get("facets"))
        pu = cfg.as_list(r.get("puertas"))
        cfg.print_seguro(f"  {len(f)} ✦  {row(r, subject).strip()}"
                         + (f"  · {'+'.join(pu)}" if pu else ""))
    # #126: en un tema de MÉTODO la pregunta útil no es paper por paper sino por POLÍTICA. La puerta
    # que admitió a cada uno ya está en el registro, así que el corte se propone una vez —y se
    # declara con `--extraccion subconjunto --reason`— en vez de reconstruirse a ojo cada corrida.
    grupos: dict = {}
    for r in recs:
        grupos.setdefault("+".join(cfg.as_list(r.get("puertas"))) or "(sin puerta registrada)",
                          []).append(r)
    if any(k != "(sin puerta registrada)" for k in grupos):
        cfg.print_seguro("\n  Por POLÍTICA (D-26: qué puerta lo admitió):")
        for k in sorted(grupos):
            cfg.print_seguro(f"    · {k}: {len(grupos[k])}")
        cfg.print_seguro("    Elegí una política —sólo fundacionales, fundacionales + astro, todo— "
                         "y declarala:")
    cfg.print_seguro("\n  Al recortar la lectura, declaralo: "
                     f"`python scripts/triage.py {slug} --extraccion subconjunto --reason \"...\"`")
    return 0


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
    """Persist the rejection of chaining candidates so they are not proposed again on the next run.

    ⚠ AUD-151 — normalises exactly like its twin `drop_source`, which already did. Without it a
    bibcode with surrounding whitespace — the normal shape when pasted from a terminal — was
    persisted **verbatim**: the stored key matched nothing, the real candidate stayed in the queue,
    and `n_dropped` counted the ineffective drop, so the note's header published «N descartados»
    over one that was not. A `--reason "   "` passed too, leaving the judgement without the motive
    #51 exists to preserve. The fix applied to one site and not to its twin, once again."""
    limpios = list(dict.fromkeys(b.strip() for b in bibcodes if b and b.strip()))
    if not limpios:
        sys.exit("--drop necesita al menos un bibcode no vacío.")
    reason = reason.strip()
    if not reason:
        sys.exit("--drop necesita un --reason con contenido (no espacios).")
    bibcodes = limpios
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
    #  @inv INV-48
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
        cfg.theme_by_slug(slug)
    except KeyError:
        try:
            cfg.star_by_slug(slug)
        except KeyError:
            sys.exit(f"slug desconocido: '{slug}' — no está en themes.yaml ni en stars.yaml. "
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
    cfg.print_seguro("  (versionado: se commitea y viaja. `ingest_theme` avisa si volvés a declarar esta "
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
    #  @inv INV-54
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
    # AUD-152 — un `decisiones` que no es un mapa (o con entradas que no lo son) reventaba con
    # `AttributeError`/`TypeError` a mitad de la migración, y como el lint bloquea por EXISTENCIA
    # del archivo el usuario quedaba con un bloqueante **sin salida**: el único comando que el
    # propio mensaje receta no podía correr nunca. Se reporta con la forma real y no se borra nada.
    if not isinstance(viejas, dict):
        cfg.print_seguro(f"{slug}: `decisiones` de {legacy} no es un mapa (es "
                         f"{type(viejas).__name__}) — no se migró nada y NO lo borro. Arreglalo a "
                         f"mano (tiene que ser `{{bibcode: {{decision, motivo, fecha}}}}`) y volvé "
                         f"a correr `--migrate`.")
        return 1
    if (malas := sorted(b for b, d in viejas.items() if not isinstance(d, dict))):
        cfg.print_seguro(f"  ⚠ {len(malas)} entrada(s) de {legacy} no son un mapa y NO se migran "
                         f"({', '.join(malas[:3])}…): `load_decisiones` las descartaría igual, así "
                         f"que migrarlas guardaría un juicio que nadie lee.")
        viejas = {b: d for b, d in viejas.items() if isinstance(d, dict)}
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
    # D-28: `busquedas` es una lista de corridas; acá interesa la ÚLTIMA (el snapshot vigente del
    # embudo). El universo acumulado del sujeto lo da `cfg.universo_acumulado`.
    bs = cfg.load_busquedas(slug)
    b = bs[-1] if bs else {}
    # #H11 sigue cubierto por `load_busquedas`, que filtra por `isinstance(dict)` los elementos
    # de la lista (una entrada editada a mano puede ser un escalar).
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


# Los tres estados del candidato frente a la bóveda (#189), con su marca en el listado. `◆` y `◇`
# se leen distinto de un vistazo y ocupan una sola columna, así que la tabla del reporte no cambia
# de forma.
READ_HERE, OTHER_AXIS, NO_NOTE = "leido", "otro-eje", "nuevo"
MARKS = {READ_HERE: "◆", OTHER_AXIS: "◇", NO_NOTE: " "}


def subject_name(slug: str) -> str:
    """El nombre con el que los papers reclaman este sujeto — el que va en `stars[]`/
    `thesis_links[]` y, desde #188, en `vistas[].sujeto`.

    En un tema es el `concept` (NO el slug: son cosas distintas y el slug no aparece en ninguna
    nota); en una estrella, el nombre canónico de `stars.yaml`. Un slug que no resuelve devuelve el
    slug: el triage sólo está listando candidatos y no es el lugar donde eso se aborta."""
    meta = cfg.as_map(_tema_meta(slug))
    if meta:
        return str(meta.get("concept") or slug)
    try:
        return cfg.star_by_slug(slug)[0]
    except (KeyError, RuntimeError):
        return slug


_STATE_MARK = {cfg.NOTE_ABSENT: NO_NOTE, cfg.NOTE_READ: READ_HERE, cfg.NOTE_STUB: OTHER_AXIS}


def note_state(bibcode: str, subject: str) -> str:
    """¿En qué estado está este candidato respecto de la bóveda? (#189)

    `has_note` —lo que había hasta acá— sólo preguntaba si el archivo existe, y con eso el listado
    le afirmaba al operador que el paper «ya está bajado y **extraído**». Es falso: la nota existe
    porque alguien la **creó**, y el retro-linkeo de `make_notes` mergea `stars`/`thesis_links`
    add-only **sin leer nada**. La extracción es una lectura CON LENTE (#188) y quien la hizo la
    declara en `vistas[]`, **fechada**. La regla vive en `cfg.note_state` (AUD-286: acá y en
    `query_ads` había dos definiciones de «extraída»); esto sólo traduce al vocabulario de las
    marcas del listado."""
    return _STATE_MARK[cfg.note_state(bibcode, subject)]


def row(c: dict, subject: str) -> str:
    cites = c.get("citation_count") or 0
    nota = MARKS[note_state(c["bibcode"], subject)]
    title = " ".join((c.get("title") or "").split())[:76]
    # #86: el candidato sin abstract se juzgó con menos información que los demás — y acá se está
    # decidiendo justamente si entra. Sin la marca, el veredicto se lee igual de firme que el resto.
    sin_abs = " ⚠sin-abstract" if c.get("sin_abstract") else ""
    return (f"  {cites:>5} {nota} {c['bibcode']}  {title}  "
            f"«{','.join(cfg.as_list(c.get('facets')))}»{sin_abs}")


def report(slug: str, cands: list[dict]) -> None:
    """Tabla markdown en outputs/ (nivel 2): para decidir por lote y/o mostrarle al usuario."""
    out = cfg.ROOT / "outputs" / f"triage-{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    subject = subject_name(slug)
    lines = [f"# Triage de candidatos del chaining — {slug}",
             "",
             f"{len(cands)} candidatos pendientes (no bajados). Criterio: ¿el paper es **pertinente "
             "al sujeto** o sólo lo menciona? Aceptados → `extra_core` en `vault/config/stars.yaml`; "
             "descartados → `python scripts/triage.py " + slug + " --drop <bib> --reason \"<motivo>\"`. "
             f"`◆` = ya **leído** desde **{subject}** (hay vista fechada, #188). "
             "`◇` = tiene nota pero se leyó desde otro eje: **hay que leerlo** — lo que ya está "
             "hecho es la descarga (**no hay que bajarlo**), no la lectura.",
             "",
             "| citas | ◆/◇ | año | bibcode | título | vía | tópicos |",
             "|---:|:-:|---:|---|---|---|---|"]
    for c in cands:
        title = " ".join((c.get("title") or "").split()).replace("|", "\\|")
        lines.append(f"| {c.get('citation_count') or 0} | "
                     f"{MARKS[note_state(c['bibcode'], subject)].strip()} | "
                     f"{c.get('year') or ''} | "
                     f"[{c['bibcode']}]({ADS_URL}{c['bibcode']}/abstract) | {title} | "
                     f"{c.get('via') or ''} | {','.join(cfg.as_list(c.get('facets')))} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")  # noqa: vault-write — destino `outputs/`, scratch regenerable (#137)
    cfg.print_seguro(f"  → {out}")


def _tema_meta(slug: str) -> dict:
    """La entrada del tema, o `{}` si el slug es una estrella (o no existe). Sólo para resolver el
    nombre del `concept`, que es lo que `thesis_links` guarda — no el slug."""
    try:
        _, m = cfg.theme_by_slug(slug)
        return m
    except (KeyError, RuntimeError):
        return {}


def _notes_citing(bibcode: str) -> list:
    """Notas de `wiki/` con un `[[bibcode]]` a este paper (#132).

    Mismo matcheo que `entity.referencias`: el wikilink pelado y el que lleva alias (`[[b|texto]]`).
    Se usa para AVISAR, nunca para reescribir."""
    stem = cfg.note_stem(bibcode)
    return [f for f in sorted(cfg.WIKI.rglob("*.md"))
            if f.name != f"{stem}.md"
            and (f"[[{stem}]]" in (txt := f.read_text(encoding="utf-8")) or f"[[{stem}|" in txt)]


def drop_core(slug: str, bibcodes: list, motivo: str) -> int:
    """Saca un paper que la lente dice CORE de ESTE sujeto, y borra sus artefactos (#112).

    @inv INV-127

    Es el simétrico que a `extra_core` le faltaba. Hasta ahora `--drop` sólo evitaba re-proponer un
    candidato del chaining: sobre un core no tenía efecto, así que un descarte con motivo quedaba
    escrito y **no se aplicaba** — medido en `ica`, 7 papers off-topic seguían siendo core corrida
    tras corrida. Una decisión que el clasificador ignora en silencio es peor que no tomarla.

    Borra el PDF y el `.txt` a propósito: si quedan, el detector de #108 los reporta como
    «extracción pagada sin nota» para siempre, y el `.txt` sigue apareciendo en los greps del
    corpus. La decisión queda igual —versionada, con motivo, en `decisiones`— así que borrar el
    artefacto no borra el juicio, y re-correr la cadena no los vuelve a bajar."""
    if not motivo:
        sys.exit("sacar un paper del sujeto sin `--reason` deja el registro sin decir POR QUÉ — y "
                 "acá el motivo es lo único que distingue una curación de un borrado a ciegas.")
    hoy = dt.date.today().isoformat()
    data = cfg.load_registro(slug)
    dec = data.setdefault("decisiones", {}) if isinstance(data.get("decisiones"), dict) or         "decisiones" not in data else data["decisiones"]
    borrados, colgados = 0, []
    for b in bibcodes:
        dec[b] = {"decision": "descartado", "origen": "sujeto", "motivo": motivo, "fecha": hoy}
        for ruta in (cfg.PDFS / slug / f"{b}.pdf", cfg.FULLTEXT / slug / f"{b}.txt"):
            if ruta.exists():
                ruta.unlink()
                borrados += 1
        nota = cfg.PAPERS / f"{cfg.note_stem(b)}.md"
        if nota.exists():
            fm = cfg.split_fm(nota.read_text(encoding="utf-8"))
            # AUD-219 — `stars:` lleva el NOMBRE de la estrella y `thesis_links` el concepto del
            # tema: el propio sujeto se nombra de tres maneras, y comparando sólo contra el slug
            # contaba como «otro dueño» y el stub de una estrella no se borraba nunca.
            propios = {slug, cfg.as_map(_tema_meta(slug)).get("concept") or slug}
            try:
                propios.add(cfg.star_by_slug(slug)[0])
            except (KeyError, RuntimeError, OSError):
                pass
            otros = [x for x in cfg.as_list(fm.get("stars")) + cfg.as_list(fm.get("thesis_links"))
                     if x not in propios]
            # ⛔ `methods` es SUFICIENTE pero NO NECESARIO para «tiene extracción» (#188/#207).
            # `methods` es lo que la lectura ENCONTRÓ; `vistas[].fecha` es lo que dice que la
            # lectura OCURRIÓ, y sólo la escribe la lectura. La brecha entre las dos es exactamente
            # el caso que este carril existe para cerrar: un FALSO POSITIVO de polisemia se leyó
            # entero y volvió con `methods` vacío porque el método del paper no es del tema. Con
            # sólo el primer proxy la guarda protegía al revés de donde importa — medido en `ica`
            # (2026-08-29): borró 9 notas de ~100 líneas, cada una con la vista que documentaba POR
            # QUÉ el paper no era del tema, informando que no había extracción que perder.
            extraida = cfg.note_has_reading(fm)
            if otros or extraida:
                # No se borra: o pertenece a otro sujeto (la exclusión es del PAR paper-sujeto), o
                # ya tiene extracción encima —trabajo pagado— y eso no se destruye en silencio.
                por = ("pertenece también a " + ", ".join(map(str, otros[:3]))) if otros else                     "ya tiene extracción LLM (`methods` o vista con fecha): trabajo pagado"
                cfg.print_seguro(f"  ⚠ {b}: su nota `papers/` NO se borra — {por}. Revisala a mano.")
                # #217 — la nota se conserva, pero los artefactos que este drop borró NO existen
                # más: `pdf:`/`fulltext:` y el link `[📄 PDF]` de la cabecera quedaban afirmando
                # algo falso sobre el disco, y son —por contrato— verdad de disco. Antes de #215 el
                # drift se curaba solo en el próximo `make_notes`; el fix de #215 filtra los
                # dropeados ANTES de escribir notas (correcto: no queremos resucitar el dropeado),
                # así que esas notas ya no vuelven a pasar por el re-estampado y el drift pasó de
                # transitorio a PERMANENTE. La limpieza la tiene que hacer quien borró: es el único
                # que sabe qué borró. NO se toca la vista ni la extracción: la lectura ocurrió.
                if make_notes.retarget_artifacts(b):
                    cfg.print_seguro(f"     ↳ `pdf:`/`fulltext:` re-apuntados por verdad de disco "
                                     f"(null si no quedó copia bajo otro slug)")
            else:
                # #132: la nota se borra, así que todo `[[bibcode]]` que la citaba queda ROTO
                # (INV-02, P0, bloqueante en el próximo lint). No se reparan solos —eso sería
                # decidir por el usuario qué decía esa frase—: se los deja rotos y VISIBLES, con el
                # puntero de dónde están. Mismo criterio y misma redacción que `entity.py delete`,
                # cuya garantía (INV-19) es que tras borrar no quede referencia colgada sin avisar.
                colgados.extend(_notes_citing(b))
                nota.unlink()
                borrados += 1
    data["decisiones"] = dec
    cfg.save_registro(slug, data)
    cfg.print_seguro(f"  {len(bibcodes)} paper(s) excluido(s) de `{slug}` (carril `sujeto`) · "
                     f"{borrados} artefacto(s) borrado(s) · motivo: {motivo}")
    if colgados:
        cfg.print_seguro(f"⚠ {len(colgados)} nota(s) citan un paper que se borró: el `[[wikilink]]` "
                         f"quedó ROTO (bloqueante en el lint). Repará o quitá cada uno —")
        for f in colgados[:10]:
            cfg.print_seguro(f"    · {f.relative_to(cfg.WIKI)}")
    cfg.print_seguro(f"  → {cfg.registro_path(slug)} (versionado: la decisión viaja). Re-corré la "
                     "cadena: no vuelven a entrar ni a bajarse.")
    return 0


# Vocabulario CERRADO del carril OFF-ADS (#111): quién declaró una fuente de `sources:`.
# ⛔ NO es el mismo que `cfg.EXTRA_CORE_VIA` (`usuario | triage | citado-por-corpus`), que es el del
# carril ADS. Comparten un solo valor —`usuario`— y el `help=` los llamaba «gemelos», con lo cual
# inducía a escribir en `extra_core` un `via` que el loader rechaza, y al revés (#162). Son dos
# cuadrantes distintos de la tabla de curación de CLAUDE.md, y por buena razón: en off-ADS no hay
# query que descubra, así que TODO entra por decisión de alguien y el eje es quién.
# #206: DOS valores, no tres. El eje que `via` mide es **quién decidió** —una persona o la cascada
# de descubrimiento— y eso es binario. Que el usuario traiga una lista de papers (un reporte de
# literatura, una review de terceros) o los PDFs no cambia quién decidió: lo trajo él. Partirlo
# obligaba a sumar dos casilleros para contestar la única pregunta que el campo existe para
# contestar. Lo que `reporte` agregaba —de qué documento salió— lo lleva `motivo`, que es
# obligatorio y nombra CUÁL documento.
VIA_FUENTE = ("usuario", "descubrimiento")


def accept_source(slug: str, idents: list, via: str, motivo: str) -> int:
    """Candidato off-ADS aceptado → **entrada de `sources:` lista para pegar**, con metadata real,
    procedencia y archivo resuelto. Es la salida que al carril off-ADS le faltaba (#111).

    POR QUÉ EXISTE, medido. El carril del bibcode ADS está **completo**: aceptás un candidato, va a
    `extra_core`, re-corrés la cadena y **se baja solo**. El de off-ADS se cortaba en el hallazgo:
    el descubrimiento proponía el paper y después había que escribir a mano una entrada de
    `sources:` con un archivo conseguido por tu cuenta. Medido sobre una bóveda real: el
    descubrimiento anclado **encontró** a Comon 1994 (citado por 8 de los 19 papers astro del tema)
    y al libro de Hyvärinen-Karhunen-Oja (citado por 6), y ninguno de los dos entró — no por fallo
    de búsqueda, sino porque nadie hizo el trabajo manual. Los 40 papers que la bóveda anterior
    tenía y la nueva no **entraron los 40 a mano**.

    Y de paso cierra la otra mitad de la asimetría de #51: una entrada de `sources:` no decía
    **quién la declaró ni por qué** —el `extra_core` sí lo dice desde D-58, y el descarte de una
    fuente desde #81—, así que la aceptación off-ADS era el único de los cuatro cuadrantes sin
    registro de curación. Por eso `via` y `motivo` son obligatorios acá.

    No escribe `themes.yaml`: imprime el bloque, igual que el snippet de `extra_core`. La config es
    curada y versionada, y un script que la edita solo convierte una decisión en un efecto
    colateral."""
    if via not in VIA_FUENTE:
        sys.exit(f"`--via {via}` no está en el vocabulario cerrado: {' | '.join(VIA_FUENTE)}")
    if not motivo:
        sys.exit("aceptar una fuente sin `--reason` deja el registro sin decir POR QUÉ entró — es "
                 "la asimetría que #51 cerró del lado del descarte. Poné el motivo.")
    import discover
    import openalex as oa
    hoy = dt.date.today().isoformat()
    cfg.print_seguro(f"\n  sources:      # pegar en la entrada `{slug}` de vault/config/themes.yaml")
    fallidos = []
    for ident in idents:
        try:
            w = discover._json(oa.API + "/doi:" + urllib.parse.quote(ident) + "?" +
                               urllib.parse.urlencode({"mailto": oa._mailto()}))
        except Exception as exc:                    # noqa: BLE001 — declarado, no tragado
            fallidos.append((ident, str(exc)[:90]))
            continue
        # AUD-231 — `_json` devuelve None cuando el archivo contesta 404, y eso NO estaba en la
        # rama de fallo: seguía derecho y reventaba con `AttributeError` dentro de `openalex`, o
        # sea la peor forma de fallar (un traceback donde había un carril de error declarado, y la
        # entrada a medias ya impresa arriba).
        if not isinstance(w, dict):
            fallidos.append((ident, "el archivo no devolvió metadata para ese identificador"))
            continue
        key = oa.citekey(w) or ident
        doi = oa._bare_doi(w.get("doi"))
        url, _por = discover.resolve_pdf(doi)
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
        autor = (((w.get("authorships") or [{}])[0].get("author") or {}).get("display_name") or "")
        cfg.print_seguro(f"    - key: {key}")
        # `url:` si hay copia libre; si no, `pending: paywall` — el carril que ya existe para
        # derivar al usuario sin frenar la cadena. Nunca se inventa un archivo.
        cfg.print_seguro(f"      url: {url}" if url else "      pending: paywall")
        cfg.print_seguro(f"      title: {(w.get('title') or '').replace(chr(10), ' ')!r}")
        if autor:
            cfg.print_seguro(f"      author: {autor.split()[-1]}")
        if w.get("publication_year"):
            cfg.print_seguro(f"      year: {w['publication_year']}")
        if venue:
            cfg.print_seguro(f"      venue: {venue!r}")
        if doi:
            cfg.print_seguro(f"      doi: {doi}")
        if w.get("authorships"):
            cfg.print_seguro(f"      n_authors: {len(w['authorships'])}")
        cfg.print_seguro(f"      via: {via}")
        cfg.print_seguro(f"      fecha: {hoy}")
        cfg.print_seguro(f"      motivo: {motivo!r}")
    for ident, why in fallidos:
        cfg.print_seguro(f"  ⚠ {ident}: no se pudo resolver la metadata ({why}) — NO se inventa "
                         "una entrada a medias; re-intentá o declarala a mano")
    cfg.print_seguro("\n  → después: `python scripts/ingest_theme.py " + slug +
                     "` (idempotente: sólo baja lo nuevo).")
    return 1 if fallidos else 0


CURATED_KEYS = ("no_vista", "no_sintetizado", "salvedades", "vistas", "methods", "thesis_links",
                "role", "refuta")


def _yaml_scalar(v) -> str:
    """One-line YAML scalar for `_set_campo` (quoted when the value needs it)."""
    return yaml.safe_dump(v, allow_unicode=True, width=10 ** 6).split("\n")[0]


def promote_source(slug: str, key: str, bibcode: str) -> int:
    """Migrate a declared source (`sources:` item `key`) to its ADS identity `bibcode` (#353, T5b).

    WHY, measured: the #353 case was fixed by hand and it took five steps — move two artifacts,
    delete the stub, remove the item, add the `extra_core` map, re-run the chain — and it LOST the
    old note's `no_vista` declaration silently (recovered from `git show HEAD:`). That is exactly
    the class of artifact the framework calls non-regenerable: a curation judgement with its
    motive. A note with an ADS bibcode never belonged in `sources:` (hand metadata, and the false
    attribution #353 caught is impossible by construction in `extra_core`, where ADS is the
    authority).

    What it does, in order: `make_notes.rename_paper(key, bibcode, fix_key=True)` — note, sidecar,
    PDF/`.txt` under every slug, extraction JSON and every wikilink; NO `versions[]` (the key was
    wrong, not an alias, #355) — so every curated frontmatter key travels untouched (asserted
    after); then the ADS record (`query_ads.fetch_bibcodes`) re-stamps the CATALOG fields the stub
    had by hand (title, first author, year, doi, bibstem, citation_count, keywords, verbatim
    abstract) and clears `source_url`/`accessed`. It prints the `extra_core` entry and the item to
    remove; it never edits `themes.yaml`, like `accept_source`."""
    import make_notes
    import query_ads
    try:
        _, meta = cfg.theme_by_slug(slug)
    except KeyError as e:
        sys.exit(str(e))
    item = next((s_ for s_ in cfg.as_list(meta.get("sources"))
                 if isinstance(s_, dict) and str(s_.get("key") or "").strip() == key), None)
    if item is None:
        sys.exit(f"'{slug}': no hay un item de `sources:` con `key: {key}` — nada que promover")
    if not re.fullmatch(r"\d{4}[A-Za-z0-9.&]{15}", bibcode):
        sys.exit(f"`{bibcode}` no tiene forma de bibcode ADS (19 caracteres, AAAA + revista + …): la "
                 f"promoción es hacia una identidad ADS real")
    old_note = cfg.PAPERS / f"{make_notes.safe_name(key)}.md"
    new_note = cfg.PAPERS / f"{make_notes.safe_name(bibcode)}.md"
    if not old_note.exists():
        sys.exit(f"no existe `papers/{old_note.name}`: promover una fuente que no tiene nota es sólo "
                 f"editar `themes.yaml` (sacá el item y agregá el `extra_core`)")
    if new_note.exists():
        sys.exit(f"ya existe `papers/{new_note.name}`: son dos notas del mismo trabajo — consolidá con "
                 f"`python scripts/make_notes.py --rename-paper {key} {bibcode}`")
    antes = cfg.split_fm(old_note.read_text(encoding="utf-8")) or {}
    curados = {k: antes.get(k) for k in CURATED_KEYS if k in antes}

    make_notes.rename_paper(key, bibcode, fix_key=True)

    recs = query_ads.fetch_bibcodes([bibcode], via_de={bibcode: "usuario"})
    if recs:
        r = recs[0]
        autores = cfg.as_list(r.get("authors"))
        campos = {"title": r.get("title"), "first_author": autores[0] if autores else None,
                  "n_authors": len(autores), "year": int(r["year"]) if r.get("year") else None,
                  "arxiv_id": r.get("arxiv_id"), "doi": r.get("doi"), "bibstem": r.get("bibstem"),
                  "citation_count": r.get("citation_count"), "source_url": None, "accessed": None}
        for k, v in campos.items():
            make_notes._set_campo(new_note, k, _yaml_scalar(v))
        make_notes.merge_frontmatter_list(new_note, "keywords", cfg.as_list(r.get("keyword")))
        if r.get("abstract"):
            texto = new_note.read_text(encoding="utf-8")
            nuevo = re.sub(r"(## Abstract\s*\n)\s*" + re.escape(cfg.ABSTRACT_PLACEHOLDER),
                           lambda m: m.group(1) + "\n" + r["abstract"].strip(), texto, count=1)
            if nuevo != texto:
                cfg.write_text_atomic(new_note, nuevo)
        cfg.print_seguro(f"  metadata de catálogo re-estampada desde ADS ({r.get('title')!r}, "
                         f"{r.get('citation_count')} citas)")
    else:
        cfg.print_seguro(f"  ⚠ ADS no devolvió `{bibcode}`: la metadata queda la declarada a mano — "
                         f"revisá el bibcode y re-corré `make_notes.py --theme {slug}` cuando entre")

    despues = cfg.split_fm(new_note.read_text(encoding="utf-8")) or {}
    perdidos = [k for k, v in curados.items() if despues.get(k) != v]
    if perdidos:
        cfg.print_seguro(f"  ⛔ la promoción PERDIÓ curación de la nota vieja: {', '.join(perdidos)} — "
                         f"recuperala de `git show HEAD:vault/wiki/papers/{old_note.name}`")
    hoy = dt.date.today().isoformat()
    motivo = str(item.get("motivo") or "").strip()
    cfg.print_seguro(f"\n  extra_core:   # pegar en la entrada `{slug}` de vault/config/themes.yaml")
    cfg.print_seguro(f"    - bibcode: {bibcode}")
    cfg.print_seguro(f"      via: usuario")
    cfg.print_seguro(f"      fecha: {hoy}")
    texto_motivo = ((motivo + " ") if motivo else "") + (
        f"(promovido desde `sources:` `{key}`, via {item.get('via') or '?'}; tiene bibcode ADS, #353)")
    cfg.print_seguro(f"      motivo: {_yaml_scalar(texto_motivo)}")
    cfg.print_seguro(f"\n  → y SACÁ el item `key: {key}` de `sources:` (la misma decisión, en el "
                     f"carril correcto). Después: `python scripts/ingest_theme.py {slug}` "
                     f"(idempotente: sólo baja lo que falte).")
    return 1 if perdidos else 0


def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser(
        description="La compuerta de curación: juzga los candidatos del citation chaining y "
                    "persiste la decisión en el registro VERSIONADO (viaja en git). Sin flags, "
                    "lista lo pendiente. Todo lo que decide algo exige --reason: no se cura en "
                    "silencio.")
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
                    # AUD-210: el help nombraba dos de las CINCO operaciones que lo exigen.
                    help="el motivo, y queda en el registro versionado. OBLIGATORIO con --drop, "
                         "--drop-source, --drop-core, --accept-source y --extraccion subconjunto "
                         "(ahí es el criterio del recorte). Con --sintesis es opcional, como nota")
    ap.add_argument("--extraccion", choices=("todos", "subconjunto"),
                    help="D-13/INV-83: declarar QUÉ SE LEYÓ de los core de este sujeto. `todos` = "
                         "el default del contrato; `subconjunto` = se recortó, y entonces --reason "
                         "es el criterio (obligatorio). Queda en `extraccion:` del registro "
                         "versionado; sin esto el lint reporta *recorte de lectura sin declarar*")
    ap.add_argument("--sintesis", action="store_true",
                    help="INV-82: declarar que ACÁ se sintetizó el sujeto (la tercera fecha de la "
                         "cabecera). Opcional `--n-papers N` y `--reason` como nota. Se estampa en "
                         "la ficha con `make_notes.py <slug>`")
    ap.add_argument("--n-papers", type=int, dest="n_papers",
                    help="(--sintesis) sobre cuántos papers se sintetizó")
    ap.add_argument("--drop-core", nargs="+", metavar="BIBCODE", dest="drop_core",
                    help="sacar de ESTE sujeto papers que la lente dice core, y borrar sus "
                         "artefactos: PDF, .txt y —si el paper no pertenece a otro sujeto y no "
                         "tiene extracción— TAMBIÉN SU NOTA, dejando rotos los wikilinks que la "
                         "citaban (se listan) (#112/#132). Es el simétrico de `extra_core`. Exige "
                         "--reason. La exclusión es del par paper-sujeto: el mismo paper puede ser "
                         "core de otro.")
    ap.add_argument("--accept-source", nargs="+", metavar="DOI", dest="accept_source",
                    help="candidato OFF-ADS aceptado → arma la entrada de `sources:` (metadata "
                         "real + archivo resuelto + procedencia) lista para pegar. Es la salida "
                         "que al carril off-ADS le faltaba: sin esto, el descubrimiento proponía "
                         "el paper y el trabajo de bajarlo quedaba a mano. Exige --reason y --via.")
    ap.add_argument("--via", default="usuario", choices=VIA_FUENTE,
                    # AUD-210: nombraba `reporte`, RETIRADO en #206 y ausente de `choices` —
                    # el help contradecía a su propio parser. Los dos vocabularios salen del código.
                    help=f"quién acepta la fuente OFF-ADS (vocabulario CERRADO): "
                         f"{' | '.join(VIA_FUENTE)}. ⚠ NO es el de `extra_core` (carril ADS), que "
                         f"es {' | '.join(cfg.EXTRA_CORE_VIA)}")
    ap.add_argument("--promote-source", metavar="CLAVE", dest="promote_source",
                    help="#353 (T5b): migra la fuente declarada CLAVE a su identidad ADS (--bibcode), "
                         "preservando la curación de la nota; imprime el `extra_core` y no edita themes.yaml")
    ap.add_argument("--bibcode", default="", help="bibcode ADS destino de --promote-source")
    ap.add_argument("--prioridad", action="store_true",
                    help="la cola de extracción: no filtra ni toca la lente, ordena lo que ya es "
                         "core. Dos vistas — #87: por cuántas facetas del objetivo toca cada uno "
                         "(citas como desempate); #126: agrupado por POLÍTICA, o sea por cuál puerta "
                         "de D-26 entró (fundacional / astro / las dos), que es con lo que se decide "
                         "el recorte de lectura UNA vez y se declara con --extraccion.")
    ap.add_argument("--migrate", action="store_true",
                    help="consolidar en el registro versionado las decisiones del "
                         "build/<slug>/triage.json viejo (bóvedas pre-1.9.0) y salir")
    args = ap.parse_args()

    def close(rc: int, paso: str) -> int:
        """Stamp the step in `cadena:` when it actually ran, and return its exit code.

        #231 / D-57 — «each script stamps itself, so a step run by hand leaves a trace instead of
        reading as a cut». `triage.py` was the one that did not: measured on a real vault, **21
        runs** of `--drop-core`/`--drop` left no step at all. The judgement itself was not lost —it
        lives in `decisiones`, dated— but WHEN it was applied relative to the `make_notes` runs was,
        and that is exactly what explains a vault holding 32 notes for 30 papers.

        Only on success: a run that refused did not curate anything, and stamping it would put a
        step in the chain that never happened.
        """
        if rc == 0:
            cfg.save_paso(args.slug, "triage", cfg.flags_usados(args, ap))
        return rc

    if args.drop_core:
        return close(drop_core(args.slug, args.drop_core, args.reason), "triage")
    if args.accept_source:
        return close(accept_source(args.slug, args.accept_source, args.via, args.reason), "triage")
    if args.promote_source:
        if not args.bibcode:
            ap.error("--promote-source necesita --bibcode <bibcode ADS destino>")
        return close(promote_source(args.slug, args.promote_source, args.bibcode), "triage")
    if args.prioridad:
        return prioridad(args.slug)
    if args.migrate:
        return migrate(args.slug)

    # D-13/INV-83 — el canal de DECLARACIÓN del recorte de lectura. Vivía sólo como función de
    # `lib_config` y **ningún script ni skill la llamaba**: el detector del lint existía y el
    # hallazgo no tenía cómo cerrarse. Va acá porque `triage.py` ya es el CLI del juicio de curación
    # (los dos carriles de descarte escriben en el mismo registro); leer 8 de 42 core es una
    # decisión de curación más, y del mismo tipo: la que hay que poder auditar seis meses después.
    if args.sintesis:
        cfg.save_sintesis(args.slug, n_papers=args.n_papers, nota=args.reason)
        cfg.print_seguro(f"{args.slug}: síntesis declarada hoy"
                         + (f" sobre {args.n_papers} papers" if args.n_papers else "")
                         + f"\n  → {cfg.registro_path(args.slug)}"
                         # #331 — el comando sale de `make_notes_cmd`, no del slug pelado: en un
                         # tema falta `--theme` y el paso siguiente muere con un `KeyError` que
                         # culpa a `stars.yaml` de un slug bien definido en `themes.yaml`. Este
                         # script es el ÚNICO canal de la fecha de síntesis (INV-82), así que el
                         # hallazgo del lint sólo se podía cerrar sabiendo agregar el flag a mano.
                         + f"\n  Estampala en la ficha: `{cfg.make_notes_cmd(args.slug)}`")
        return 0

    if args.extraccion:
        subconjunto = args.extraccion == "subconjunto"
        if subconjunto and not args.reason:
            ap.error("--extraccion subconjunto necesita --reason: el CRITERIO del recorte es la "
                     "pieza que más se va a leer (qué se leyó y por qué), no un booleano")
        criterio = args.reason or "todos los core del sujeto"
        cfg.save_extraccion(args.slug, subconjunto=subconjunto, criterio=criterio)
        cfg.print_seguro(
            f"{args.slug}: extracción declarada — "
            f"{'SUBCONJUNTO' if subconjunto else 'todos los core'} · {criterio}\n"
            f"  → {cfg.registro_path(args.slug)}")
        return 0

    if args.drop and args.drop_source:
        ap.error("--drop y --drop-source son los dos carriles de curación (candidato del chaining "
                 "vs fuente declarada): usá uno por corrida, con su motivo")

    if args.drop:
        if not args.reason:
            ap.error("--drop necesita --reason (el motivo queda registrado; no curar en silencio)")
        return close(drop(args.slug, args.drop, args.reason), "triage")

    if args.drop_source:
        if not args.reason:
            ap.error("--drop-source necesita --reason (el motivo queda registrado; no curar en "
                     "silencio)")
        return close(drop_source(args.slug, args.drop_source, args.reason,
                                  args.pointer or None), "triage")

    decisiones = load_decisions(args.slug)
    if not (cfg.ROOT / "build" / args.slug / "ads.json").exists():
        if decisiones:
            return show_decisions(args.slug, decisiones)
        # Un tema off-ADS PURO no tiene `ads.json` por diseño: mandarlo a "corré la cadena" (con un
        # comando que además no resuelve su slug) es el consejo imposible que #81 vino a sacar.
        try:
            _, meta = cfg.theme_by_slug(args.slug)
        except KeyError:
            meta = None
        if meta is not None and (meta.get("source") or "ads") != "ads":
            sys.exit(f"'{args.slug}' es un tema off-ADS (source: {meta.get('source')}): no tiene "
                     f"candidatos del chaining por diseño y no hay decisiones registradas. El "
                     f"carril de este tema es `triage.py {args.slug} --drop-source <clave> "
                     f"--reason \"<motivo>\"`.")
    data = load_ads(args.slug)
    cands = cfg.as_list(data.get("candidates"))
    # #189: DOS números, no uno. El viejo sumaba los dos estados «tiene nota» y los anunciaba como
    # leídos; el del medio es el que hay que leer, y es el mayoritario (141 de 908 notas de una
    # bóveda real son de 2+ sujetos y ninguna tiene una segunda extracción).
    subject = subject_name(args.slug)
    estados = [note_state(c["bibcode"], subject) for c in cands]
    cfg.print_seguro(f"Triage de {args.slug}: {len(cands)} candidatos pendientes "
          f"(◆ {estados.count(READ_HERE)} con lectura hecha desde {subject} · "
          f"◇ {estados.count(OTHER_AXIS)} con nota y sin lectura desde este sujeto: hay que "
          f"leerlo, bajado ya está) · "
          f"{len(decisiones)} decisiones persistidas · {data.get('n_relevant', 0)} core actuales")
    if not cands:
        cfg.print_seguro("  → nada pendiente. (Los candidatos aparecen tras un query_ads con chaining.)")
        return 0
    # #79 (cuarta fuga de ranking): por TASA de citas, no por cuenta cruda. La cuenta está sesgada
    # por la edad —un paper viejo tuvo más tiempo de acumularlas— y acá se decide qué ENTRA al
    # corpus: con orden crudo, un candidato reciente y pertinente queda sistemáticamente abajo del
    # corte visual. Política ÚNICA de `lib_config`, la misma que ordena el barrido (#88) y el
    # apéndice de excluidos: tres `sort(key=…)` inline en archivos distintos era la garantía de que
    # cambiar uno dejara los otros viejos sin que nadie lo notara.
    # @inv INV-120
    ordenados = cfg.sort_by_citation_rate(cands)
    for c in ordenados:
        cfg.print_seguro(row(c, subject))
    if args.report:
        report(args.slug, cands)
    cfg.print_seguro("\n  → juicio (LLM/usuario) por título+abstract: pertinente al SUJETO / ruido / dudoso.\n"
          "     aceptados  → pegar el bloque de abajo en `extra_core:` de vault/config/stars.yaml y "
          "re-correr la cadena (idempotente: sólo baja los nuevos).\n"
          "     descartados → python scripts/triage.py <slug> --drop <bib> … --reason \"<motivo>\".\n"
          "     dudosos    → al usuario (--report deja la tabla en outputs/).")
    # D-58/R-2: `extra_core` es lista de MAPAS (con `via` y `motivo`). El snippet se imprime ya
    # armado porque ahí está el costo de UX de la forma dura: escribir cuatro campos a mano por
    # cada aceptación. Con el snippet, aceptar sigue siendo copiar y pegar — y el registro gana el
    # dato que el carril del descarte ya tenía (quién y por qué), que era la asimetría.
    # #161: el snippet lo arma `cfg.extra_core_snippet`, la MISMA pieza que usa `query_ads --sweep`.
    # Estaba duplicado inline en los dos carriles y el otro había divergido a una forma que el
    # framework bloquea — dos implementaciones de la misma promesa es la garantía de que una envejece.
    # AUD-285: el tope (`cfg.EXTRA_CORE_SNIPPET_TOPE`) lo declara el propio snippet, para los dos
    # carriles — acá se repetía a mano con un `10` literal y `query_ads --sweep` no lo decía.
    cfg.print_seguro("\n" + cfg.extra_core_snippet(ordenados, via="triage").rstrip("\n"))
    return 0


if __name__ == "__main__":
    cfg.cli_exit(main)
