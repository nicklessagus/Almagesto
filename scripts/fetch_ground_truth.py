"""Ground-truth estructurado por estrella desde NASA Exoplanet Archive + SIMBAD.

Uso:
    python scripts/fetch_ground_truth.py <slug> [--force]

Escribe ground_truth/<slug>.json con:
  - host: tipo espectral, Teff, distancia, coords, V, masa estelar (lo que haya).
  - planets: lista (letter, P_days, K_ms, e, mass_earth, ...).
Estos son hechos auditables (no extracción LLM). Los scripts que los consumen los leen directo.
Idempotente: NO pisa un ground_truth/<slug>.json existente salvo --force (vault/raw/ es fuente
inmutable, y NEA cambia valores entre releases — refrescar es una decisión, no un side-effect).

Sobre la masa: `mass_earth` = **m·sin i** (`pl_msinie`), que es la cantidad robusta para planetas
RV. Se preserva `bmass_earth`/`bmass_prov` (la "best mass" de NEA, que a veces viene de una ref de
masa verdadera y puede ser muy distinta) para auditoría. Verificación: se recomputa m·sin i a partir
de K, P, e y M* y se compara con `mass_earth`; si difieren >3× se marca `mass_flag` (caso típico:
NEA devuelve una best-mass espuria). Ver también el chequeo análogo en lint.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import lib_config as cfg


def _norm_id(s: str) -> str:
    """Un identificador de catálogo, comparable: sin espacios internos y en minúsculas.

    SIMBAD escribe `HD  40307` con espaciado variable y `stars.yaml` `HD 40307`; sin normalizar,
    todo alias legítimo saldría reportado."""
    return "".join(str(s).split()).lower()


def simbad_identifiers(host: str) -> list | None:
    """Todos los identificadores que SIMBAD conoce para `host`, en su orden. `None` si no contestó.

    #82, el lado **de menos** — el simétrico de `unresolved_aliases`. El skill advierte que *«un
    alias que falta es un paper que nunca aparece, en silencio»* y por eso manda resolverlos en
    SIMBAD; en la práctica los completa el LLM **de memoria**, sin fuente y sin rastro, y son la
    entrada de **tres** mecanismos de recall: la query directa, el barrido `--sweep` y el rescate
    por glifo. Un alias que falta los degrada a los tres a la vez.

    La llamada ya se hace (`query_objectids`, la misma de `unresolved_aliases`), así que persistir
    la lista es gratis y convierte «lo que el LLM se acordó» en «lo que SIMBAD dice», auditable y
    fechado con el snapshot.

    ⛔ Persistir NO es adoptar. Cuáles entran a `stars.yaml` es **curación humana**: SIMBAD devuelve
    identificadores que no sirven para buscar texto (Gaia DR3, 2MASS J…) junto a los que sí (HD,
    HIP, GJ). Acá queda la propuesta, determinista y con su fuente; la elección se versiona.

    `None` ≠ `[]`: sin esa distinción una caída de red se lee como «no hay más identificadores».

    @inv INV-122"""
    try:
        from astroquery.simbad import Simbad
        tabla = Simbad().query_objectids(host)
    except Exception as e:
        cfg.print_seguro(f"  ⚠ SIMBAD no devolvió los identificadores de {host!r}: {e} — la lista "
                         "de alias queda SIN completar (no es lo mismo que completa).")
        return None
    if tabla is None or not len(tabla):
        return None
    col = tabla.colnames[0]
    return [str(fila[col]) for fila in tabla]


def unresolved_aliases(host: str, aliases: list) -> list | None:
    """Alias declarados que SIMBAD **no** lista como identificadores de `host` (#82).

    Por qué existe. El skill advierte que *«un alias que falta es un paper que nunca aparece — en
    silencio»* y por eso manda resolverlos en SIMBAD. No dice nada del alias **de más**, que es el
    modo de falla simétrico: mete papers de OTRO objeto al corpus por la misma puerta. Medido en el
    clean-room del 2026-08-25 sobre una instancia real — `HR 2102` declarado para HD 40307 es en
    realidad **36 Dor**, K2III-IV. Impacto de ESE caso: 0 papers contaminados, o sea latente; pero
    nada lo detectaba.

    Es barato porque los datos ya se bajan: `query_objectids` es una llamada más al mismo servicio
    que ya se consulta para `spectral_type`.

    Devuelve `None` si SIMBAD no contestó — **distinto de `[]`** («contestó y están todos»): sin esa
    distinción, una caída de red se leería como "alias verificados"."""
    try:
        from astroquery.simbad import Simbad
        tabla = Simbad().query_objectids(host)
    except Exception as e:
        cfg.print_seguro(f"  ⚠ SIMBAD no devolvió los identificadores de {host!r}: {e} — los alias "
                          "quedan SIN verificar (no es lo mismo que verificados y correctos).")
        return None
    if tabla is None or not len(tabla):
        return None
    col = tabla.colnames[0]
    conocidos = {_norm_id(fila[col]) for fila in tabla}
    conocidos.add(_norm_id(host))
    return [a for a in cfg.as_list(aliases) if _norm_id(a) not in conocidos]


def _val(row, key):
    """Valor escalar limpio (float/int/str), sin unidades, o None si enmascarado/nan."""
    import numpy as np
    if key not in row.colnames:
        return None
    v = row[key]
    try:
        if v is None or (hasattr(v, "mask") and bool(v.mask)):
            return None
        if hasattr(v, "value"):          # astropy Quantity → escalar sin unidad
            v = v.value
        if isinstance(v, bytes):
            v = v.decode()
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating, float)):
            return None if np.isnan(v) else float(v)
        s = str(v).strip()
        if s.lower() in ("", "nan", "--", "none"):
            return None
        try:                              # numéricos que vinieron como string
            f = float(s)
            return int(f) if f.is_integer() and "." not in s else f
        except ValueError:
            return s
    except Exception:
        return None


def msini_earth(K_ms, P_days, e, mstar_msun):
    """m·sin i [M_⊕] a partir de K, P, e y M* (aprox. m_p << M*). None si falta algo.  @inv INV-10"""
    import math
    if None in (K_ms, P_days, mstar_msun) or K_ms <= 0 or P_days <= 0 or mstar_msun <= 0:
        return None
    G, Msun, Mearth, day = 6.674e-11, 1.989e30, 5.972e24, 86400.0
    ecc = e if (e is not None and 0 <= e < 1) else 0.0
    P, Mstar = P_days * day, mstar_msun * Msun
    m = K_ms * Mstar ** (2 / 3) * (P / (2 * math.pi * G)) ** (1 / 3) * math.sqrt(1 - ecc ** 2)
    return m / Mearth


def write_ground_truth(slug: str, payload: dict) -> Path:
    """Escritura atómica de ground_truth/<slug>.json, vía `cfg.write_text_atomic` (D-53: un solo
    writer atómico en el repo; esta función era uno de los tres clones del patrón). Sin ella, `--force` reescribía el archivo directo con
    `write_text` y un corte a mitad de la escritura (proceso matado, disco lleno) dejaba el JSON
    TRUNCADO: medido, 162 B de snapshot previo → 1.024 B de JSON inválido, contenido viejo
    IRRECUPERABLE. El propio docstring del módulo dice que NEA cambia valores entre releases: el
    snapshot no es regenerable, así que perderlo a mitad de una escritura no es aceptable."""
    out = cfg.GROUND_TRUTH / f"{slug}.json"
    cfg.write_text_atomic(out, json.dumps(payload, indent=2, ensure_ascii=False))
    return out


def fetch_pscomppars(host: str):
    """Tabla `pscomppars` de NEA para el host — se consulta UNA vez por corrida y la comparten
    `fetch_host` y `fetch_planets` (#31: antes cada uno repetía la misma query → dos round-trips
    idénticos por estrella; el parámetro muerto `tab_row` era la huella del reuso nunca cableado).
    Import lazy: astroquery se carga sólo cuando hay red que consultar."""
    from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive
    return NasaExoplanetArchive.query_object(host, table="pscomppars")


def fetch_planets(tab, mstar_msun=None) -> list[dict]:
    """Planetas desde la tabla pscomppars YA consultada (`fetch_pscomppars`)."""
    import math
    planets = []
    for row in tab:
        name = _val(row, "pl_name") or ""
        letter = name.split()[-1] if name else None
        K, P, e = _val(row, "pl_rvamp"), _val(row, "pl_orbper"), _val(row, "pl_orbeccen")
        msini = _val(row, "pl_msinie")          # columna m·sin i de NEA
        bmass = _val(row, "pl_bmasse")          # best-mass de NEA (provenance variable)
        check = msini_earth(K, P, e, mstar_msun)   # m·sin i implícita por K,P,e,M*
        # elegir, entre los valores reportados, el consistente con la física (NEA es inconsistente:
        # a veces el bueno está en pl_msinie, a veces en pl_bmasse). No se inventa nada.
        cand = {k: v for k, v in (("pl_msinie", msini), ("pl_bmasse", bmass)) if v}
        flag = None
        if check and cand:
            src = min(cand, key=lambda k: abs(math.log(cand[k] / check)))
            mass = cand[src]
            if not (1 / 3 < mass / check < 3):
                flag = (f"ningún valor NEA coincide con m·sini implícita {check:.3g} M⊕ "
                        f"(msini={msini}, bmass={bmass})")
        else:                                   # sin K → no se puede verificar
            src = "pl_msinie" if msini is not None else ("pl_bmasse" if bmass else None)
            mass = cand.get(src) if src else None
            if msini and bmass and not (1 / 3 < msini / bmass < 3):
                flag = f"msini={msini} vs bmass={bmass} discrepantes y sin K para dirimir"
        planets.append({
            "pl_name": name,
            "letter": letter,
            "P_days": P,
            "K_ms": K,
            "e": e,
            "mass_earth": mass,               # elegido por consistencia física
            "mass_source": src,               # de qué columna NEA salió
            "msini_earth": msini,             # pl_msinie crudo (auditoría)
            "bmass_earth": bmass,             # pl_bmasse crudo (auditoría)
            "bmass_prov": _val(row, "pl_bmassprov"),
            "msini_check_earth": round(check, 3) if check else None,
            "mass_flag": flag,
            "method": _val(row, "discoverymethod"),
            "disc_year": _val(row, "disc_year"),
            "disc_refname": _val(row, "disc_refname"),
            "status": "confirmed",
        })
    # ordenar por período
    planets.sort(key=lambda p: (p["P_days"] is None, p["P_days"] or 0))
    return planets


def fetch_host(host: str, tab=None) -> dict:
    """Datos del host: primero de NEA (columnas host de pscomppars — pasar la tabla ya
    consultada; si viene None se consulta acá, tolerante), luego SIMBAD **sólo** para `spectral_type` (`cfg.AUTORIDAD_CAMPO` se lo asigna a SIMBAD; `ra_deg`/`dec_deg` son de NEA y SIMBAD no los aporta acá — si NEA falla quedan `None`, y ésa es la ausencia que el JSON declara, no un dato perdido).

    H-14/H-15: antes, una falla de NEA o de SIMBAD acá se escribía al payload como
    `_nea_host_error`/`_simbad_error` — campos que NINGÚN lector consume (0 consumidores, medido
    por grep): quedaban muertos en el JSON para siempre. Peor, si la falla era en SIMBAD,
    `spectral_type` quedaba `None` exactamente igual que cuando NEA/SIMBAD genuinamente no tienen
    el dato — desde #70 (espejo puro) un `None` de host es "normal", así que la falla técnica
    quedaba INDISTINGUIBLE de una ausencia legítima. Se decidió no escribir esos campos (nada los
    lee) y en cambio avisar por stdout en el momento del ingest, que es donde alguien puede
    efectivamente actuar (reintentar, revisar el host, etc.) — sin inventar un nuevo campo
    write-only que reproduciría el mismo problema."""
    # INV-07: la clave va PRESENTE y en `null` cuando la autoridad calla — no se omite. Un campo
    # ausente y un campo nulo se leen distinto: el primero parece un schema viejo, el segundo dice
    # "la autoridad no tiene el dato", que es la información real.
    out = {"name": host, **{campo: None for campo in cfg.AUTORIDAD_CAMPO}}
    otras: dict = {}          # D-2: valores de la autoridad NO declarada, que no se adoptan
    # NEA host columns (vienen en pscomppars)
    try:
        if tab is None:
            tab = fetch_pscomppars(host)
        if len(tab):
            r = tab[0]
            # `spectral_type` NO se toma de NEA (D-1: su autoridad declarada es SIMBAD). Si NEA
            # lo trae, se guarda aparte como discrepancia potencial en vez de tirarse (D-2).
            if (sp_nea := _val(r, "st_spectype")) not in (None, ""):
                otras["spectral_type"] = {"nea": sp_nea}
            out.update({
                "teff_K": _val(r, "st_teff"),
                "mass_msun": _val(r, "st_mass"),
                "st_rotp_days": _val(r, "st_rotp"),
                "dist_pc": _val(r, "sy_dist"),
                "Vmag": _val(r, "sy_vmag"),
                "ra_deg": _val(r, "ra"),
                "dec_deg": _val(r, "dec"),
            })
    except Exception as e:
        out.setdefault(AUTORIDAD_CAIDA, []).append("nea")
        cfg.print_seguro(f"  ⚠ NEA (columnas de host) no respondió para {host!r}: {e} — los "
                          "campos de host quedan sin completar (no es lo mismo que NEA sin el "
                          "dato: revisar a mano si hace falta).")
    # SIMBAD (defensivo: la API de fields cambia entre versiones)
    try:
        from astroquery.simbad import Simbad
        s = Simbad()
        agregado = False
        for f in ("sp_type", "sptype"):
            try:
                s.add_votable_fields(f)
                agregado = True
                break
            except Exception:
                continue
        if not agregado:
            cfg.print_seguro(f"  ⚠ SIMBAD: no se pudo agregar sp_type/sptype como campo para "
                              f"{host!r} — si spectral_type queda null, puede ser por esto y no "
                              "porque SIMBAD no tenga el dato (indistinguible desde #70).")
        res = s.query_object(host)
        if res is not None and len(res):
            r = res[0]
            for k in ("sp_type", "SP_TYPE", "sptype"):
                # sin el `out.get(...) in (None, "")` de antes: SIMBAD es la autoridad declarada
                # para este campo, así que su valor MANDA — no rellena el hueco que NEA dejó.
                if k in res.colnames:
                    out["spectral_type"] = _val(r, k)
                    break
    except Exception as e:
        out.setdefault(AUTORIDAD_CAIDA, []).append("simbad")
        cfg.print_seguro(f"  ⚠ SIMBAD no respondió para {host!r}: {e} — spectral_type puede "
                          "quedar null por esto y no por ausencia real del dato.")
    # D-1: qué autoridad contestó cada campo. Se persiste porque es lo que la ficha publica en su
    # cabecera y lo que hace AUDITABLE la elección — sin esto, "vino de SIMBAD" es una promesa de
    # la doc, no un hecho del archivo. Sólo los campos con valor: un `null` no tiene procedencia.
    out["_autoridad"] = {campo: cfg.AUTORIDAD_CAMPO[campo]
                         for campo in cfg.AUTORIDAD_CAMPO
                         if out.get(campo) not in (None, "")}
    # D-2 / INV-77: lo que la OTRA autoridad decía y no se adoptó. No se tira: sin registrarlo, el
    # desacuerdo entre autoridades desaparece y la ficha afirma un valor único donde había dos.
    if otras:
        out["_otras_autoridades"] = otras
    return out




# ── D-45 / INV-85: qué cambió afuera desde el snapshot ───────────────────────────────────────────

# #171 · qué autoridad NO contestó en esta corrida. Es un marcador **efímero**: lo lee `nea_diff`
# para levantar en vez de reportar el corte como un cambio real, y `host_persistible` lo saca antes
# de escribir. No es un campo del schema — H-14/H-15 ya decidió que al ground-truth no se le
# escriben campos sin lector, y ése sigue siendo el criterio.
AUTORIDAD_CAIDA = "_autoridad_caida"


def host_persistible(host: dict) -> dict:
    """El dict de host sin los marcadores efímeros (#171). Lo que se escribe al JSON."""
    return {k: v for k, v in host.items() if k != AUTORIDAD_CAIDA}


def nea_diff(slug: str) -> list:
    """Diff campo a campo entre el snapshot en disco y lo que NEA/SIMBAD dicen HOY.  @inv INV-85

    Devuelve `[(campo, viejo, nuevo)]` y **no escribe nada**. Esa separación es el punto: un
    snapshot que se actualiza solo cambia valores bajo los pies de la prosa que ya los citó, y el
    consumidor no tiene forma de enterarse. Aplicar sigue siendo `--force`, explícito.

    Un valor **retirado** (NEA lo tenía y ya no) es un cambio como cualquier otro: la ficha lo
    sigue mostrando y nadie lo diría. Los planetas se comparan **por letra**, no por posición ni
    por cardinalidad — dos listas del mismo largo pueden no ser los mismos planetas (la lección de
    #70, que costó el defecto que cerró ese issue).
    """
    out = cfg.GROUND_TRUTH / f"{slug}.json"
    if not out.exists():
        return []
    try:
        viejo = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        # ⛔ NO `return []`: un snapshot ilegible no es "no cambió nada". Devolverlo así hacía que
        # el slug no entrara en `fallidos` de `sweep_ground_truth` y que la pasada estampara
        # `cubrio: ground-truth` sobre una comparación que nunca ocurrió — exactamente el registro
        # falso que ese docstring dice existir para impedir (AUD-43). El lint ya trata al
        # ground-truth ilegible como bloqueante: acá se propaga para que el barrido lo cuente.
        raise ValueError(f"ground-truth de {slug} ilegible: {exc}") from exc
    name, _ = cfg.star_by_slug(slug)
    tab = fetch_pscomppars(name)
    host_nuevo = fetch_host(name, tab=tab)
    if (caidas := host_nuevo.get(AUTORIDAD_CAIDA)):
        # ⛔ #171: sin esto, una caída de SIMBAD devolvía `spectral_type=None` y el diff reportaba
        # `'G8V' → None` como si NEA/SIMBAD hubieran RETIRADO el valor. El slug no entraba en
        # `fallidos`, la pasada estampaba `cubrio: ground-truth` sobre una comparación que no se
        # hizo, y con `--yes` además aplicaba el cambio inventado. Mismo trato que el snapshot
        # ilegible (AUD-43): se propaga para que el barrido lo cuente como NO evaluado.
        raise ValueError(f"{', '.join(str(c).upper() for c in caidas)} no respondió para {slug}: "
                         f"no se puede diffear contra una autoridad que no contestó")
    host_nuevo = host_persistible(host_nuevo)
    planets_nuevos = fetch_planets(tab, host_nuevo.get("mass_msun"))

    cambios = []
    host_viejo = cfg.as_map(viejo.get("host"))
    for campo in sorted(set(host_viejo) | set(host_nuevo)):
        if campo.startswith("_") or campo == "name":
            continue                      # metadata de procedencia, no valor
        a, b = host_viejo.get(campo), host_nuevo.get(campo)
        if a != b:
            cambios.append((f"host.{campo}", a, b))

    por_letra_viejo = {p.get("letter"): p for p in cfg.as_list(viejo.get("planets"))
                       if isinstance(p, dict)}
    por_letra_nuevo = {p.get("letter"): p for p in planets_nuevos}
    for letra in sorted(set(por_letra_viejo) | set(por_letra_nuevo), key=str):
        a, b = por_letra_viejo.get(letra), por_letra_nuevo.get(letra)
        if a is None or b is None:
            cambios.append((f"planets.{letra}", a, b))     # planeta nuevo o retirado
            continue
        for campo in sorted(set(a) | set(b)):
            if a.get(campo) != b.get(campo):
                cambios.append((f"planets.{letra}.{campo}", a.get(campo), b.get(campo)))
    return cambios


def _flags_usados(args, ap=None) -> list:
    """Los flags no-default de esta corrida, para dejarlos en `cadena:` del registro (D-48/D-57).
    Son las **escotillas**: `--force`, `--yes`, `--all` cambian lo que la corrida hizo, y sin
    registrarlas la traza dice "corrió make_notes" sobre dos corridas que no hicieron lo mismo."""
    return cfg.flags_usados(args, ap)

def main() -> int:
    cfg.stdout_tolerante()  # Tolera encoding no-UTF8 en argparse --help
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--force", action="store_true",
                    help="refrescar un ground-truth existente desde NEA/SIMBAD (pisa el snapshot)")
    args = ap.parse_args()
    name, meta = cfg.star_by_slug(args.slug)
    out = cfg.GROUND_TRUTH / f"{args.slug}.json"
    if out.exists() and not args.force:
        print(f"Ground-truth {name}: {out} ya existe — no se pisa (refrescar desde NEA: --force)")
        # El atajo idempotente SÍ estampa el paso (R-6): salir 0 sin estamparlo dejaba
        # `cadena_cortada` reportando "se cortó en `fetch_ground_truth`" **para siempre** sobre un
        # paso que corre y decide correctamente no pisar nada. El caso alcanzable es el mixto —
        # snapshot en disco sin `cadena:` para ese paso (corpus pre-D-57, slug renombrado, o JSON
        # creado por `sweep_external.aplicar_ground_truth`)— y el único modo de cerrarlo era
        # `--force`, o sea pisar el snapshot: justo lo que el mensaje de arriba dice no hacer. Es
        # el mismo falso positivo permanente que `check_retractions` ya tenía y cerró.
        cfg.save_paso(args.slug, "fetch_ground_truth", flags=_flags_usados(args, ap))
        return 0
    host = cfg.require_field(meta, "simbad", name, "stars.yaml")
    print(f"Ground-truth {name} (host={host!r})")

    # UNA consulta pscomppars por corrida, compartida por host y planetas (#31). Falla de
    # NEA → aborto amigable (la cadena es idempotente: reintentar es seguro).
    try:
        tab = fetch_pscomppars(host)
    except Exception as e:
        sys.exit(f"NEA (pscomppars) no respondió para {host!r}: {e} — reintentá; "
                 "fetch_ground_truth no pisa un snapshot existente.")
    host_info = host_persistible(fetch_host(host, tab))
    planets = fetch_planets(tab, host_info.get("mass_msun"))
    print(f"  planetas confirmados: {len(planets)}  | sp_type: {host_info.get('spectral_type')}"
          f"  | M*: {host_info.get('mass_msun')}")
    for p in planets:
        if p.get("mass_flag"):
            print(f"  ⚠ {p['letter']}: {p['mass_flag']}")
        elif p.get("mass_source") == "pl_bmasse":
            print(f"  · {p['letter']}: m·sini de NEA (pl_msinie={p['msini_earth']}) era inconsistente "
                  f"→ uso pl_bmasse={p['mass_earth']} M⊕ (≈ check {p['msini_check_earth']})")

    # #82 — el lado "alias DE MÁS" del recall: uno que resuelve a otro objeto mete papers ajenos.
    # `None` (SIMBAD no contestó) se persiste distinto de `[]` (contestó y están todos): sin esa
    # distinción una caída de red se leería como "alias verificados".
    colgados = unresolved_aliases(host, meta.get("aliases"))
    if colgados:
        print(f"  ⚠ alias que SIMBAD NO lista como identificadores de {host!r}: "
              f"{', '.join(colgados)} — ¿resuelven a OTRO objeto? Un alias de más mete papers "
              "ajenos al corpus (el lint lo reporta como WARN).")

    payload = {"star": name, "slug": args.slug, "host": host_info, "planets": planets,
               # inglés por la regla de código nuevo; las claves `_autoridad`/`_otras_autoridades`
               # se dejan como están (sin retrofit).
               "_unresolved_aliases": colgados,
               # #82, lado de MENOS: lo que SIMBAD conoce, para que la propuesta de alias salga de
               # una fuente y no de la memoria del LLM. Persistir no es adoptar: el lint lo reporta
               # y la elección se versiona en `stars.yaml`.
               # ⛔ SIN `or []`: mataba la distinción que INV-122 enuncia y que la propia
               # `simbad_identifiers` honra — `None` (SIMBAD no contestó) ≠ `[]` (contestó y no hay
               # más identificadores). El `@inv` estaba sobre código que SÍ cumple y la garantía se
               # rompía un renglón después: una caída de red se persistía como «está todo
               # declarado». Medido el 2026-08-28.
               "_simbad_aliases": simbad_identifiers(host),
               # D-1: la fecha del snapshot es parte de la procedencia que la ficha publica —
               # "de dónde salió" sin "cuándo" no alcanza: NEA cambia valores entre releases.
               "consultado": dt.date.today().isoformat(),
               "source": "NASA Exoplanet Archive (pscomppars) + SIMBAD"}
    out = write_ground_truth(args.slug, payload)
    print(f"  → {out}")
    cfg.save_paso(args.slug, "fetch_ground_truth", flags=_flags_usados(args, ap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
