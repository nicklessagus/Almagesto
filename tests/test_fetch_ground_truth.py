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


# ── fetch_planets: selección de masa y flags (astroquery falso) ──────────────

def planet_row(name="Toy 1 b", K=0.0895, P=365.25, e=0.0, msini=None, bmass=None):
    return Row(pl_name=name, pl_rvamp=K, pl_orbper=P, pl_orbeccen=e,
               pl_msinie=msini, pl_bmasse=bmass, pl_bmassprov="Msini",
               discoverymethod="Radial Velocity", disc_year=2020, disc_refname="ref")


@pytest.fixture
def fake_nea(monkeypatch):
    """Inyecta astroquery falso en sys.modules; setear .rows antes de llamar."""
    holder = types.SimpleNamespace(rows=[])

    class FakeNEA:
        @staticmethod
        def query_object(host, table=None):
            return list(holder.rows)

    leaf = types.ModuleType("astroquery.ipac.nexsci.nasa_exoplanet_archive")
    leaf.NasaExoplanetArchive = FakeNEA
    for name in ("astroquery", "astroquery.ipac", "astroquery.ipac.nexsci"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "astroquery.ipac.nexsci.nasa_exoplanet_archive", leaf)
    return holder


def test_masa_msini_consistente(fake_nea):
    # check implícito ~1.0 M⊕; pl_msinie cerca → se elige y no hay flag
    fake_nea.rows = [planet_row(msini=1.05, bmass=10.0)]
    p = gt.fetch_planets("Toy 1", 1.0)[0]
    assert p["mass_source"] == "pl_msinie"
    assert p["mass_earth"] == 1.05
    assert p["mass_flag"] is None
    assert p["letter"] == "b"


def test_masa_best_mass_rescata_msini_espuria(fake_nea):
    fake_nea.rows = [planet_row(msini=20.0, bmass=1.02)]
    p = gt.fetch_planets("Toy 1", 1.0)[0]
    assert p["mass_source"] == "pl_bmasse"
    assert p["mass_earth"] == 1.02
    assert p["mass_flag"] is None


def test_masa_ningun_valor_consistente_flaggea(fake_nea):
    fake_nea.rows = [planet_row(msini=20.0, bmass=30.0)]
    p = gt.fetch_planets("Toy 1", 1.0)[0]
    assert p["mass_flag"] is not None
    assert "m·sini implícita" in p["mass_flag"]


def test_masa_sin_K_no_verifica(fake_nea):
    fake_nea.rows = [planet_row(K=None, msini=2.0, bmass=None)]
    p = gt.fetch_planets("Toy 1", 1.0)[0]
    assert p["mass_earth"] == 2.0 and p["mass_source"] == "pl_msinie"
    assert p["mass_flag"] is None


def test_masa_sin_K_discrepantes_flaggea(fake_nea):
    fake_nea.rows = [planet_row(K=None, msini=2.0, bmass=50.0)]
    p = gt.fetch_planets("Toy 1", 1.0)[0]
    assert p["mass_flag"] is not None and "sin K" in p["mass_flag"]


def test_planetas_ordenados_por_periodo_none_al_final(fake_nea):
    fake_nea.rows = [planet_row(name="Toy 1 c", P=5.0),
                     planet_row(name="Toy 1 d", P=None),
                     planet_row(name="Toy 1 b", P=1.0)]
    letters = [p["letter"] for p in gt.fetch_planets("Toy 1", 1.0)]
    assert letters == ["b", "c", "d"]


# ── main(): idempotencia del snapshot ────────────────────────────────────────

def run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["fetch_ground_truth.py", *argv])
    return gt.main()


def test_main_no_pisa_sin_force(toy_vault, monkeypatch):
    out = toy_vault.GROUND_TRUTH / "test_star.json"
    out.write_text(json.dumps({"star": "vieja"}), encoding="utf-8")

    def boom(*a, **kw):
        raise AssertionError("no debería consultar la red sin --force")
    monkeypatch.setattr(gt, "fetch_host", boom)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert json.loads(out.read_text())["star"] == "vieja"


def test_main_force_refresca(toy_vault, monkeypatch):
    out = toy_vault.GROUND_TRUTH / "test_star.json"
    out.write_text(json.dumps({"star": "vieja"}), encoding="utf-8")
    monkeypatch.setattr(gt, "fetch_host", lambda h: {"name": h, "mass_msun": 1.0})
    monkeypatch.setattr(gt, "fetch_planets", lambda h, m: [])
    assert run_main(monkeypatch, ["test_star", "--force"]) == 0
    data = json.loads(out.read_text())
    assert data["star"] == "Estrella Test" and data["slug"] == "test_star"
