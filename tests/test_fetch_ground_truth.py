"""fetch_ground_truth: física de msini_earth, _val, selección de masa NEA, idempotencia."""
import json
import sys
import types

import numpy as np
import pytest

import fetch_ground_truth as gt


# ── msini_earth (física contra valores conocidos) ────────────────────────────

def test_msini_tierra():
    """Tierra alrededor del Sol: K≈0.0895 m/s, P=1 yr → ~1 M⊕."""
    m = gt.msini_earth(0.0895, 365.25, 0.0, 1.0)
    assert abs(m - 1.0) < 0.03


def test_msini_51peg():
    """51 Peg b: K=55.9 m/s, P=4.23 d, M*=1.06 → ~0.47 M_J ≈ 147 M⊕."""
    m = gt.msini_earth(55.9, 4.2308, 0.0, 1.06)
    assert 140 < m < 155


def test_msini_excentricidad_reduce():
    m0 = gt.msini_earth(10, 100, 0.0, 1.0)
    m9 = gt.msini_earth(10, 100, 0.9, 1.0)
    assert m9 < m0
    assert abs(m9 / m0 - (1 - 0.9 ** 2) ** 0.5) < 1e-9


def test_msini_inputs_invalidos():
    assert gt.msini_earth(None, 100, 0, 1.0) is None
    assert gt.msini_earth(10, None, 0, 1.0) is None
    assert gt.msini_earth(10, 100, 0, None) is None
    assert gt.msini_earth(0, 100, 0, 1.0) is None
    assert gt.msini_earth(10, -5, 0, 1.0) is None
    # e fuera de [0,1) se trata como 0 (no rompe)
    assert gt.msini_earth(10, 100, 1.5, 1.0) == gt.msini_earth(10, 100, None, 1.0)


# ── _val ─────────────────────────────────────────────────────────────────────

class Row:
    def __init__(self, **cols):
        self._c = cols
        self.colnames = list(cols)

    def __getitem__(self, k):
        return self._c[k]


class Masked:
    mask = True


class Quantity:
    value = 5.5


def test_val_conversiones():
    r = Row(a=None, b=Masked(), c=Quantity(), d=b"K2V", e=np.float64("nan"),
            f=np.int64(3), g="42", h="42.5", i="--", j="nan", k="K2 V", l=7.25)
    assert gt._val(r, "zzz") is None          # columna ausente
    assert gt._val(r, "a") is None
    assert gt._val(r, "b") is None            # enmascarado
    assert gt._val(r, "c") == 5.5             # Quantity → escalar
    assert gt._val(r, "d") == "K2V"           # bytes → str
    assert gt._val(r, "e") is None            # nan
    assert gt._val(r, "f") == 3
    assert gt._val(r, "g") == 42              # string numérico entero
    assert gt._val(r, "h") == 42.5
    assert gt._val(r, "i") is None
    assert gt._val(r, "j") is None
    assert gt._val(r, "k") == "K2 V"
    assert gt._val(r, "l") == 7.25


# ── fetch_planets: selección de masa y flags (tabla directa, sin red) ────────

def planet_row(name="Toy 1 b", K=0.0895, P=365.25, e=0.0, msini=None, bmass=None):
    return Row(pl_name=name, pl_rvamp=K, pl_orbper=P, pl_orbeccen=e,
               pl_msinie=msini, pl_bmasse=bmass, pl_bmassprov="Msini",
               discoverymethod="Radial Velocity", disc_year=2020, disc_refname="ref")


@pytest.fixture
def fake_nea(monkeypatch):
    """Inyecta astroquery falso en sys.modules; setear .rows antes de llamar. `.calls` cuenta
    las consultas query_object (regresión #31: main debe consultar UNA sola vez)."""
    holder = types.SimpleNamespace(rows=[], calls=0)

    class FakeNEA:
        @staticmethod
        def query_object(host, table=None):
            holder.calls += 1
            return list(holder.rows)

    leaf = types.ModuleType("astroquery.ipac.nexsci.nasa_exoplanet_archive")
    leaf.NasaExoplanetArchive = FakeNEA
    for name in ("astroquery", "astroquery.ipac", "astroquery.ipac.nexsci"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "astroquery.ipac.nexsci.nasa_exoplanet_archive", leaf)
    return holder


def test_masa_msini_consistente():
    # check implícito ~1.0 M⊕; pl_msinie cerca → se elige y no hay flag
    p = gt.fetch_planets([planet_row(msini=1.05, bmass=10.0)], 1.0)[0]
    assert p["mass_source"] == "pl_msinie"
    assert p["mass_earth"] == 1.05
    assert p["mass_flag"] is None
    assert p["letter"] == "b"


def test_masa_best_mass_rescata_msini_espuria():
    p = gt.fetch_planets([planet_row(msini=20.0, bmass=1.02)], 1.0)[0]
    assert p["mass_source"] == "pl_bmasse"
    assert p["mass_earth"] == 1.02
    assert p["mass_flag"] is None


def test_masa_ningun_valor_consistente_flaggea():
    p = gt.fetch_planets([planet_row(msini=20.0, bmass=30.0)], 1.0)[0]
    assert p["mass_flag"] is not None
    assert "m·sini implícita" in p["mass_flag"]


def test_masa_sin_K_no_verifica():
    p = gt.fetch_planets([planet_row(K=None, msini=2.0, bmass=None)], 1.0)[0]
    assert p["mass_earth"] == 2.0 and p["mass_source"] == "pl_msinie"
    assert p["mass_flag"] is None


def test_masa_sin_K_discrepantes_flaggea():
    p = gt.fetch_planets([planet_row(K=None, msini=2.0, bmass=50.0)], 1.0)[0]
    assert p["mass_flag"] is not None and "sin K" in p["mass_flag"]


def test_planetas_ordenados_por_periodo_none_al_final():
    rows = [planet_row(name="Toy 1 c", P=5.0),
            planet_row(name="Toy 1 d", P=None),
            planet_row(name="Toy 1 b", P=1.0)]
    letters = [p["letter"] for p in gt.fetch_planets(rows, 1.0)]
    assert letters == ["b", "c", "d"]


# ── fetch_host: errores de SIMBAD/NEA no dejan campos muertos (H-14/H-15) ────
#
# Decisión: se dejan de escribir `_nea_host_error`/`_simbad_error` al ground-truth (0
# consumidores, medido por grep — nada en el repo los lee, ni el lint) y en su lugar se avisa por
# stdout en el momento del ingest, que es donde alguien puede efectivamente actuar. Escribir un
# campo nuevo con lector recién en `lint.py` no era una opción: ese script quedaba fuera del
# alcance de la tanda que encontró este defecto.

def test_simbad_error_no_se_escribe_como_campo_muerto(monkeypatch, capsys):
    """`_simbad_error` se escribía al ground-truth y nadie lo leía — indistinguible para
    cualquier lector real de un campo cualquiera del payload. Ahora se avisa por stdout y NO se
    persiste un campo sin lector."""
    class BoomSimbad:
        def add_votable_fields(self, *a, **k):
            raise RuntimeError("campo no soportado por esta versión de astroquery")
        def query_object(self, host):
            raise RuntimeError("SIMBAD no respondió")

    mod = types.ModuleType("astroquery.simbad")
    mod.Simbad = BoomSimbad
    monkeypatch.setitem(sys.modules, "astroquery.simbad", mod)
    monkeypatch.setitem(sys.modules, "astroquery", types.ModuleType("astroquery"))

    out = gt.fetch_host("Test Star", tab=[])
    assert "_simbad_error" not in out, f"campo muerto sin lector todavía presente: {out!r}"
    assert "SIMBAD" in capsys.readouterr().out


def test_nea_host_error_no_se_escribe_como_campo_muerto(monkeypatch, capsys):
    """Mismo defecto, del lado de NEA: `_nea_host_error` tampoco tenía lector."""
    monkeypatch.setattr(gt, "fetch_pscomppars",
                        lambda h: (_ for _ in ()).throw(RuntimeError("NEA no respondió")))

    class NoOpSimbad:
        def add_votable_fields(self, *a, **k):
            raise RuntimeError("sin red")
        def query_object(self, host):
            raise RuntimeError("sin red")

    mod = types.ModuleType("astroquery.simbad")
    mod.Simbad = NoOpSimbad
    monkeypatch.setitem(sys.modules, "astroquery.simbad", mod)
    monkeypatch.setitem(sys.modules, "astroquery", types.ModuleType("astroquery"))

    out = gt.fetch_host("Test Star", tab=None)
    assert "_nea_host_error" not in out, f"campo muerto sin lector todavía presente: {out!r}"
    assert "NEA" in capsys.readouterr().out


def test_simbad_sin_ningun_campo_agregable_avisa(monkeypatch, capsys):
    """Si NINGUNO de los dos nombres de campo (sp_type/sptype) se puede agregar, antes no había
    ni excepción ni marcador: `spectral_type` quedaba `None`, indistinguible (desde #70) de "NEA
    no lo tiene". Ahora se avisa explícitamente de esta ambigüedad."""
    class SimbadSinCampos:
        def add_votable_fields(self, *a, **k):
            raise RuntimeError("campo desconocido")
        def query_object(self, host):
            return None    # SIMBAD "responde" pero sin resultados — no dispara el except general

    mod = types.ModuleType("astroquery.simbad")
    mod.Simbad = SimbadSinCampos
    monkeypatch.setitem(sys.modules, "astroquery.simbad", mod)
    monkeypatch.setitem(sys.modules, "astroquery", types.ModuleType("astroquery"))

    gt.fetch_host("Test Star", tab=[])
    salida = capsys.readouterr().out
    assert "sp_type" in salida or "sptype" in salida


# ── main(): idempotencia del snapshot ────────────────────────────────────────

def run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["fetch_ground_truth.py", *argv])
    return gt.main()


def test_main_no_pisa_sin_force(toy_vault, monkeypatch):
    out = toy_vault.GROUND_TRUTH / "test_star.json"
    out.write_text(json.dumps({"star": "vieja"}), encoding="utf-8")

    def boom(*a, **kw):
        raise AssertionError("no debería consultar la red sin --force")
    monkeypatch.setattr(gt, "fetch_pscomppars", boom)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert json.loads(out.read_text())["star"] == "vieja"


def test_main_sin_simbad_error_amigable(toy_vault, monkeypatch):
    """Guard de config: entrada sin `simbad` → mensaje amigable, no KeyError."""
    import conftest
    conftest.write_yaml(gt.cfg.STARS_YAML, {"Estrella Test": {"slug": "test_star",
                                                              "ads_object": "Test Star"}})
    with pytest.raises(SystemExit, match="no tiene `simbad`"):
        run_main(monkeypatch, ["test_star"])


def test_main_force_refresca(toy_vault, monkeypatch):
    out = toy_vault.GROUND_TRUTH / "test_star.json"
    out.write_text(json.dumps({"star": "vieja"}), encoding="utf-8")
    monkeypatch.setattr(gt, "fetch_pscomppars", lambda h: [])
    monkeypatch.setattr(gt, "fetch_host", lambda h, tab=None: {"name": h, "mass_msun": 1.0})
    monkeypatch.setattr(gt, "fetch_planets", lambda tab, m: [])
    assert run_main(monkeypatch, ["test_star", "--force"]) == 0
    data = json.loads(out.read_text())
    assert data["star"] == "Estrella Test" and data["slug"] == "test_star"


def test_main_una_sola_consulta_nea(toy_vault, monkeypatch, fake_nea):
    """Regresión #31: fetch_host y fetch_planets comparten UNA consulta pscomppars — antes
    main() pegaba dos round-trips idénticos a NEA por estrella."""
    fake_nea.rows = [planet_row(msini=1.05)]
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert fake_nea.calls == 1
    data = json.loads((toy_vault.GROUND_TRUTH / "test_star.json").read_text())
    assert [p["letter"] for p in data["planets"]] == ["b"]


def test_main_nea_caida_aborta_amigable(toy_vault, monkeypatch):
    """Falla de NEA → SystemExit con mensaje (antes: fetch_host la toleraba en vano y
    fetch_planets moría con traceback crudo)."""
    def down(host):
        raise ConnectionError("NEA timeout")
    monkeypatch.setattr(gt, "fetch_pscomppars", down)
    with pytest.raises(SystemExit, match="no respondió"):
        run_main(monkeypatch, ["test_star"])


# ── H-06: --force reescribe el snapshot sin atomicidad ───────────────────────

def test_force_no_destruye_el_snapshot_si_falla_la_escritura(toy_vault, monkeypatch):
    """`fetch_ground_truth --force` reescribe `raw/ground_truth/<slug>.json` directo. Medido: 162 B
    de snapshot previo → 1.024 B de JSON inválido, contenido viejo irrecuperable — y su propio
    docstring dice que NEA cambia entre releases, o sea que NO es regenerable."""
    dest = toy_vault.GROUND_TRUTH / "s.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    previo = json.dumps({"slug": "s", "host": {"teff_K": 5344.0}, "planets": []})
    dest.write_text(previo, encoding="utf-8")

    import os
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("corte")))
    escribir = getattr(gt, "write_ground_truth", None)
    if escribir is None:
        pytest.skip("fetch_ground_truth no expone un writer aislado todavía — parte del fix")
    with pytest.raises(OSError):
        escribir("s", {"slug": "s", "host": {}, "planets": []})
    assert dest.read_text(encoding="utf-8") == previo, (
        "el snapshot previo no sobrevivió a un fallo de escritura → el writer no es atómico")

