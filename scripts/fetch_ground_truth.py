"""Ground-truth estructurado por estrella desde NASA Exoplanet Archive + SIMBAD.

Uso:
    python fetch_ground_truth.py <slug> [--force]

Escribe ground_truth/<slug>.json con:
  - host: tipo espectral, Teff, distancia, coords, V, masa estelar (lo que haya).
  - planets: lista (letter, P_days, K_ms, e, mass_earth, ...).
Estos son hechos auditables (no extracción LLM). Los scripts de ICA los consumen directo.
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
import json
import sys

import lib_config as cfg


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
    """m·sin i [M_⊕] a partir de K, P, e y M* (aprox. m_p << M*). None si falta algo."""
    import math
    if None in (K_ms, P_days, mstar_msun) or K_ms <= 0 or P_days <= 0 or mstar_msun <= 0:
        return None
    G, Msun, Mearth, day = 6.674e-11, 1.989e30, 5.972e24, 86400.0
    ecc = e if (e is not None and 0 <= e < 1) else 0.0
    P, Mstar = P_days * day, mstar_msun * Msun
    m = K_ms * Mstar ** (2 / 3) * (P / (2 * math.pi * G)) ** (1 / 3) * math.sqrt(1 - ecc ** 2)
    return m / Mearth


def fetch_planets(host: str, mstar_msun=None) -> list[dict]:
    from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive
    tab = NasaExoplanetArchive.query_object(host, table="pscomppars")
    planets = []
    for row in tab:
        name = _val(row, "pl_name") or ""
        letter = name.split()[-1] if name else None
        import math
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


def fetch_host(host: str, tab_row=None) -> dict:
    """Datos del host: primero de NEA (ya en pscomppars), luego SIMBAD para sp_type/coords."""
    out = {"name": host}
    # NEA host columns (vienen en pscomppars)
    try:
        from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive
        tab = NasaExoplanetArchive.query_object(host, table="pscomppars")
        if len(tab):
            r = tab[0]
            out.update({
                "spectral_type": _val(r, "st_spectype"),
                "teff_K": _val(r, "st_teff"),
                "mass_msun": _val(r, "st_mass"),
                "st_rotp_days": _val(r, "st_rotp"),
                "dist_pc": _val(r, "sy_dist"),
                "Vmag": _val(r, "sy_vmag"),
                "ra_deg": _val(r, "ra"),
                "dec_deg": _val(r, "dec"),
            })
    except Exception as e:
        out["_nea_host_error"] = str(e)
    # SIMBAD (defensivo: la API de fields cambia entre versiones)
    try:
        from astroquery.simbad import Simbad
        s = Simbad()
        for f in ("sp_type", "sptype"):
            try:
                s.add_votable_fields(f)
                break
            except Exception:
                continue
        res = s.query_object(host)
        if res is not None and len(res):
            r = res[0]
            for k in ("sp_type", "SP_TYPE", "sptype"):
                if k in res.colnames and out.get("spectral_type") in (None, ""):
                    out["spectral_type"] = _val(r, k)
                    break
    except Exception as e:
        out["_simbad_error"] = str(e)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--force", action="store_true",
                    help="refrescar un ground-truth existente desde NEA/SIMBAD (pisa el snapshot)")
    args = ap.parse_args()
    name, meta = cfg.star_by_slug(args.slug)
    out = cfg.GROUND_TRUTH / f"{args.slug}.json"
    if out.exists() and not args.force:
        print(f"Ground-truth {name}: {out} ya existe — no se pisa (refrescar desde NEA: --force)")
        return 0
    host = meta["simbad"]
    print(f"Ground-truth {name} (host={host!r})")

    host_info = fetch_host(host)
    planets = fetch_planets(host, host_info.get("mass_msun"))
    print(f"  planetas confirmados: {len(planets)}  | sp_type: {host_info.get('spectral_type')}"
          f"  | M*: {host_info.get('mass_msun')}")
    for p in planets:
        if p.get("mass_flag"):
            print(f"  ⚠ {p['letter']}: {p['mass_flag']}")
        elif p.get("mass_source") == "pl_bmasse":
            print(f"  · {p['letter']}: m·sini de NEA (pl_msinie={p['msini_earth']}) era inconsistente "
                  f"→ uso pl_bmasse={p['mass_earth']} M⊕ (≈ check {p['msini_check_earth']})")

    payload = {"star": name, "slug": args.slug, "host": host_info, "planets": planets,
               "source": "NASA Exoplanet Archive (pscomppars) + SIMBAD"}
    cfg.GROUND_TRUTH.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
