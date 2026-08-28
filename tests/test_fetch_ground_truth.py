"""fetch_ground_truth: física de msini_earth, _val, selección de masa NEA, idempotencia."""
import json
import sys
import types

import numpy as np
import pytest

import fetch_ground_truth as gt
import lib_config as cfg


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

    # SIMBAD también: la fixture dobla NEA, pero `fetch_host` y `unresolved_aliases` (#82) importan
    # `astroquery.simbad` por su cuenta y el stub de `astroquery` no impedía que resolvieran el
    # módulo REAL — o sea que la suite le pegaba a la red. Se detectó por el `NoResultsWarning` que
    # apareció al cablear #82. Doble mudo: devuelve "sin resultados", que es el comportamiento que
    # los tests de esta fixture ya asumían.
    simbad = types.ModuleType("astroquery.simbad")
    simbad.Simbad = lambda: types.SimpleNamespace(
        add_votable_fields=lambda *a, **k: None,
        query_object=lambda host: None,
        query_objectids=lambda host: None)
    monkeypatch.setitem(sys.modules, "astroquery.simbad", simbad)
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
    # @inv INV-20
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
    # #123: quedaba viva una consulta REAL a SIMBAD (`query_objectids`, para verificar los alias).
    # El try/except de producción la degrada limpio, así que la suite no se enteraba: salía a la red
    # en cada corrida y pasaba igual.
    import astroquery.simbad as _sim
    monkeypatch.setattr(_sim, "Simbad", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("SIMBAD mockeado: la suite es offline")))
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
    # `getattr` + `skip` convertía un test de PÉRDIDA DE DATOS en un salto silencioso ante
    # cualquier renombre de la función (y `-q` ni lo muestra). Si el writer no está, es un fallo.
    escribir = getattr(gt, "write_ground_truth", None)
    assert escribir is not None, ("`fetch_ground_truth.write_ground_truth` no existe: o se renombró "
                                  "—y este test hay que re-apuntarlo— o la escritura atómica del "
                                  "snapshot dejó de tener writer propio")
    with pytest.raises(OSError):
        escribir("s", {"slug": "s", "host": {}, "planets": []})
    assert dest.read_text(encoding="utf-8") == previo, (
        "el snapshot previo no sobrevivió a un fallo de escritura → el writer no es atómico")



# ── D-1 · INV-76: cada campo tiene UNA autoridad; si calla, el campo es null ─────────────────────
#
# Hasta 1.27.0 `spectral_type` salía de NEA y SIMBAD sólo rellenaba si NEA callaba — o sea: la
# autoridad efectiva dependía de quién contestara primero, y el JSON no registraba cuál ganó. Para
# el consumidor eso es indistinguible de un valor auditable con una sola procedencia.

def _fila(campos: dict):
    """Fila estilo astropy: `_val` accede por `row[key]` y consulta `row.colnames`."""
    class Fila(dict):
        @property
        def colnames(self):
            return list(self.keys())
    return Fila(campos)


def _nea(monkeypatch, campos):
    """`fetch_pscomppars` falso: una fila con los campos pedidos."""
    monkeypatch.setattr(gt, "fetch_pscomppars", lambda h: [_fila(campos)])


def _simbad(monkeypatch, sptype):
    """SIMBAD falso. `sptype=None` = no contesta (o no tiene el dato)."""
    class FakeSimbad:
        def add_votable_fields(self, *a, **k):
            return None

        def query_object(self, host):
            if sptype is None:
                return None
            # astroquery devuelve una Table: lista de filas CON `.colnames` en el objeto tabla.
            class Tabla(list):
                colnames = ["sp_type"]
            return Tabla([_fila({"sp_type": sptype})])

    mod = types.ModuleType("astroquery.simbad")
    mod.Simbad = FakeSimbad
    monkeypatch.setitem(sys.modules, "astroquery.simbad", mod)
    monkeypatch.setitem(sys.modules, "astroquery", types.ModuleType("astroquery"))


def test_spectral_type_solo_de_simbad(monkeypatch, toy_vault):
    """Los cuatro casos del contrato. NEA trae `st_spectype` y SIMBAD calla → el campo es **null**,
    aunque NEA tenga el dato: la autoridad declarada para `spectral_type` es SIMBAD.  @inv INV-76"""
    _nea(monkeypatch, {"st_spectype": "G8V", "st_teff": 5344.0})
    _simbad(monkeypatch, None)
    host = gt.fetch_host("Test Star", tab=None)
    assert host["spectral_type"] is None
    assert host["teff_K"] == 5344.0


def test_spectral_type_de_simbad_gana(monkeypatch, toy_vault):
    _nea(monkeypatch, {"st_spectype": "G8V"})
    _simbad(monkeypatch, "K0V")
    assert gt.fetch_host("Test Star", tab=None)["spectral_type"] == "K0V"


def test_autoridad_registrada_en_el_json(monkeypatch, toy_vault):
    """No alcanza con elegir bien: el JSON registra QUIÉN contestó cada campo, porque es lo que la
    ficha publica en su cabecera y lo que hace auditable la elección."""
    _nea(monkeypatch, {"st_spectype": "G8V", "st_teff": 5344.0})
    _simbad(monkeypatch, "K0V")
    host = gt.fetch_host("Test Star", tab=None)
    assert host["_autoridad"]["spectral_type"] == "simbad"
    assert host["_autoridad"]["teff_K"] == "nea"


def test_discrepancia_entre_autoridades_queda_registrada(monkeypatch, toy_vault):
    """D-2 / INV-77: si NEA **también** tiene `spectral_type` y difiere del de SIMBAD, eso es una
    discrepancia entre autoridades — el valor sigue siendo el de la autoridad declarada, pero el
    otro no se tira: sin registrarlo, el desacuerdo desaparece."""
    _nea(monkeypatch, {"st_spectype": "G8V"})
    _simbad(monkeypatch, "K0V")
    host = gt.fetch_host("Test Star", tab=None)
    assert host["spectral_type"] == "K0V"
    assert host["_otras_autoridades"]["spectral_type"] == {"nea": "G8V"}


# ── Tanda 6 · D-45: `nea_diff` REPORTA, no aplica ───────────────────────────────────────────────

def _snapshot(toy_vault, host=None, planets=None):
    (gt_cfg().GROUND_TRUTH / "test_star.json").write_text(json.dumps({
        "star": "Estrella Test", "slug": "test_star",
        "host": {"teff_K": 5344.0, "st_rotp_days": 34.5, **(host or {})},
        "planets": planets if planets is not None else
        [{"letter": "b", "P_days": 20.0, "K_ms": 1.0, "e": 0.1, "mass_earth": 2.0,
          "status": "confirmed"}]}), encoding="utf-8")


def gt_cfg():
    import lib_config as cfg
    return cfg


def test_nea_diff_reporta_y_no_aplica(toy_vault, monkeypatch):
    """El experimento del contrato (INV-85): NEA cambió y el diff se REPORTA; el JSON en disco
    queda **byte-idéntico**. Aplicar sigue siendo `--force` — un snapshot que se actualiza solo
    cambia valores bajo los pies de la prosa que ya los citó."""
    _snapshot(toy_vault)
    antes = (gt_cfg().GROUND_TRUTH / "test_star.json").read_bytes()
    _nea(monkeypatch, {"st_teff": 5350.0})          # cambió teff, y P_rot ya no viene
    _simbad(monkeypatch, None)
    monkeypatch.setattr(gt, "fetch_planets", lambda tab, m: [])
    campos = {c for c, _, _ in gt.nea_diff("test_star")}
    assert "host.teff_K" in campos
    assert "host.st_rotp_days" in campos            # el valor RETIRADO también es un cambio
    assert (gt_cfg().GROUND_TRUTH / "test_star.json").read_bytes() == antes


def test_nea_diff_sin_cambios_es_vacio(toy_vault, monkeypatch):
    _snapshot(toy_vault, planets=[])
    _nea(monkeypatch, {"st_teff": 5344.0, "st_rotp": 34.5})
    _simbad(monkeypatch, None)
    monkeypatch.setattr(gt, "fetch_planets", lambda tab, m: [])
    assert gt.nea_diff("test_star") == []


def test_nea_diff_compara_planetas_por_letra(toy_vault, monkeypatch):
    """Por LETRA, no por posición ni por cardinalidad: dos listas del mismo largo pueden no ser los
    mismos planetas (la lección de #70)."""
    _snapshot(toy_vault)
    _nea(monkeypatch, {"st_teff": 5344.0, "st_rotp": 34.5})
    _simbad(monkeypatch, None)
    monkeypatch.setattr(gt, "fetch_planets", lambda tab, m: [
        {"letter": "b", "P_days": 21.0, "K_ms": 1.0, "e": 0.1, "mass_earth": 2.0,
         "status": "confirmed"},
        {"letter": "c", "P_days": 49.0, "K_ms": 1.2, "e": 0.0, "mass_earth": 3.0,
         "status": "confirmed"}])
    campos = {c: (v, n) for c, v, n in gt.nea_diff("test_star")}
    assert campos["planets.b.P_days"] == (20.0, 21.0)
    assert "planets.c" in campos                     # planeta NUEVO


def test_el_atajo_idempotente_estampa_el_paso(toy_vault, monkeypatch, capsys):
    """R-6: *cada script se estampa a sí mismo al salir 0*. Salir 0 por el atajo idempotente **sin**
    estamparlo dejaba `cadena_cortada` reportando "se cortó en `fetch_ground_truth`" para siempre
    sobre un paso que corre y decide correctamente no pisar nada — y el único modo de cerrarlo era
    `--force`, o sea pisar el snapshot: lo que el propio mensaje del script dice no hacer.
    Es el falso positivo permanente que `check_retractions` ya había tenido.  @inv INV-91"""
    (cfg.GROUND_TRUTH).mkdir(parents=True, exist_ok=True)
    (cfg.GROUND_TRUTH / "test_star.json").write_text('{"host": {}, "planets": []}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["fetch_ground_truth.py", "test_star"])
    assert gt.main() == 0
    assert "ya existe" in capsys.readouterr().out
    pasos = [p["paso"] for p in cfg.load_cadena("test_star")]
    assert "fetch_ground_truth" in pasos, "el atajo tiene que dejar traza igual"
    assert cfg.cadena_cortada("test_star") != "fetch_ground_truth"


# ── #82 · el lado «de MENOS»: los identificadores que SIMBAD conoce y la bóveda no ───────────────

def _simbad_con(ids, monkeypatch):
    """SIMBAD que devuelve una tabla de identificadores, con la forma real (una columna, N filas)."""
    import sys, types
    simbad = types.ModuleType("astroquery.simbad")
    tabla = [{"ID": x} for x in ids]

    class _T(list):
        colnames = ["ID"]

    simbad.Simbad = lambda: types.SimpleNamespace(
        add_votable_fields=lambda *a, **k: None,
        query_object=lambda host: None,
        query_objectids=lambda host: _T(tabla))
    monkeypatch.setitem(sys.modules, "astroquery.simbad", simbad)


def test_los_identificadores_de_simbad_quedan_en_el_ground_truth(toy_vault, monkeypatch):
    """#82: `unresolved_aliases` ya cubría el alias **de más** (declarado y ajeno). Falta el de
    **menos**, que es el que el skill llama *«un alias que falta es un paper que nunca aparece — en
    silencio»*: los aliases se escriben a mano y en la práctica los completa el LLM de memoria, sin
    fuente y sin rastro, siendo la entrada de tres mecanismos de recall (query directa, `--sweep` y
    rescate por glifo).

    La misma llamada que ya se hace (`query_objectids`) devuelve la lista completa. Persistirla es
    gratis y convierte «lo que el LLM se acordó» en «lo que SIMBAD dice», auditable y fechado.

    ⛔ Persistir NO es adoptar: cuáles entran a `stars.yaml` es curación humana (el paso 4 del
    issue). Acá sólo queda la propuesta, determinista y con su fuente.

    @inv INV-122"""
    _simbad_con(["HD 10700", "HIP 8102", "GJ 71", "* tau Cet"], monkeypatch)
    assert gt.simbad_identifiers("tau Cet") == ["HD 10700", "HIP 8102", "GJ 71", "* tau Cet"]


def test_sin_respuesta_de_simbad_es_None_y_no_lista_vacia(toy_vault, monkeypatch):
    """`None` = SIMBAD no contestó; `[]` = contestó y no hay nada. Sin esa distinción una caída de
    red se lee como «no hay más identificadores», que es el cero inventado de D-43.  @inv INV-122"""
    import astroquery.simbad as _sim
    monkeypatch.setattr(_sim, "Simbad", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caído")))
    assert gt.simbad_identifiers("tau Cet") is None


# ── #171 · una autoridad que no contestó no es "el valor cambió" ─────────────────────────────────

def test_una_caida_de_simbad_no_se_lee_como_un_cambio_de_ground_truth(monkeypatch, toy_vault):
    """Issue #171 — una caída de SIMBAD se tragaba en `fetch_host` y devolvía `spectral_type=None`,
    así que `nea_diff` **no levantaba**: el slug no entraba en `fallidos`, `sweep_ground_truth`
    estampaba `cubrio: ground-truth` sobre una comparación que no se hizo, y el corte se reportaba
    como un cambio real `'G8V' → None`. Con `--yes` eso además **aplicaba** el diff y persistía
    `_cambios`.

    Es el falso limpio invertido, y con el agravante de que **fabrica** un cambio. El docstring de
    `sweep_ground_truth` ya decía que sin los `fallidos` *"el orquestador registra 'cubrió:
    ground-truth' sobre una pasada que no comparó nada"*: para SIMBAD seguía pasando.  @inv INV-85"""
    cfg.GROUND_TRUTH.mkdir(parents=True, exist_ok=True)
    (cfg.GROUND_TRUTH / "test_star.json").write_text(json.dumps({
        "star": "Estrella Test", "slug": "test_star",
        "host": {"spectral_type": "G8V"}, "planets": []}), encoding="utf-8")
    monkeypatch.setattr(gt, "fetch_pscomppars", lambda h: [])
    monkeypatch.setattr(gt, "fetch_planets", lambda tab, m=None: [])

    class BoomSimbad:
        def add_votable_fields(self, *a, **k):
            raise RuntimeError("sin red")
        def query_object(self, host):
            raise RuntimeError("SIMBAD no respondió")
    mod = types.ModuleType("astroquery.simbad")
    mod.Simbad = BoomSimbad
    monkeypatch.setitem(sys.modules, "astroquery.simbad", mod)
    monkeypatch.setitem(sys.modules, "astroquery", types.ModuleType("astroquery"))

    with pytest.raises(ValueError, match="SIMBAD"):
        gt.nea_diff("test_star")


def test_el_marcador_de_autoridad_caida_no_se_persiste_en_el_json(monkeypatch, capsys):
    """La otra mitad de #171: el marcador es para que `nea_diff` levante, no un campo nuevo del
    schema. La decisión de H-14/H-15 sigue en pie —no se escriben campos sin lector al
    ground-truth— y el aviso por stdout tampoco se pierde."""
    class BoomSimbad:
        def add_votable_fields(self, *a, **k):
            raise RuntimeError("sin red")
        def query_object(self, host):
            raise RuntimeError("SIMBAD no respondió")
    mod = types.ModuleType("astroquery.simbad")
    mod.Simbad = BoomSimbad
    monkeypatch.setitem(sys.modules, "astroquery.simbad", mod)
    monkeypatch.setitem(sys.modules, "astroquery", types.ModuleType("astroquery"))
    out = gt.fetch_host("Test Star", tab=[])
    assert out.get(gt.AUTORIDAD_CAIDA) == ["simbad"], "el marcador existe para que nea_diff lo lea"
    assert "SIMBAD" in capsys.readouterr().out
    assert gt.AUTORIDAD_CAIDA not in gt.host_persistible(out), "y no entra al JSON"


def test_el_payload_preserva_el_None_de_simbad(monkeypatch):
    """INV-122: `None` (SIMBAD no contestó) ≠ `[]` (contestó y no hay más). La función lo honraba y
    el **llamador** lo destruía con un `or []`, un renglón después de la marca `@inv` — así que una
    caída de red se persistía como «está todo declarado» y el lint no podía distinguirlas.

    Es el patrón que la auditoría del 2026-08-28 encontró seis veces: el defecto no está en la
    función marcada, está en el llamador."""
    import pathlib
    fuente = pathlib.Path(gt.__file__).read_text(encoding="utf-8")
    i = fuente.index('"_simbad_aliases"')
    linea = fuente[i:fuente.index("\n", i)]
    assert "or []" not in linea, f"el llamador colapsa el None de INV-122: {linea.strip()}"
