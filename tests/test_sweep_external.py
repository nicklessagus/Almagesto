"""sweep_external: la pasada de red UNIFICADA (D-41/D-45/D-46, INV-85).

Qué protege este archivo:

1. **Una sola pasada cubre los cinco eventos** que cambian afuera. Antes existía sólo el chequeo de
   retracciones; el ground-truth era un snapshot congelado que **nada** comparaba, y el snapshot
   web tampoco. Cinco cosas que caducan, un solo lugar donde mirarlas.
2. **Avisa con el diff ANTES de aplicar.** Un snapshot que se actualiza solo cambia valores bajo
   los pies de la prosa que ya los citó, y el consumidor no se entera.
3. **La caducidad se registra y viaja** (R-4): "cuándo se miró afuera por última vez" es
   información sobre la bóveda, no sobre la máquina que corrió la pasada.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import lib_config as cfg          # noqa: E402
import sweep_external as sw       # noqa: E402
import fetch_ground_truth        # noqa: E402


@pytest.fixture
def detectores(monkeypatch):
    """Los SEIS detectores, grabados. Cada uno devuelve un hallazgo para que la pasada tenga algo
    que reportar."""
    llamados = []

    def graba(nombre, devuelve):
        def f(*a, **k):
            llamados.append(nombre)
            return devuelve
        return f

    monkeypatch.setattr(sw, "sweep_retracciones", graba("retracciones", ["2019retR: retraction"]))
    monkeypatch.setattr(sw, "sweep_correcciones", graba("correcciones", ["2020corC: corrigendum"]))
    # ⚠ La forma del doble es la de la función REAL (red #3): `discover_versions` y
    # `sweep_ground_truth` devuelven `(hallazgos, fallidos)` desde el arreglo del cero inventado —
    # un doble que siga devolviendo la lista pelada escondería el bug en la diferencia.
    monkeypatch.setattr(sw, "discover_versions", graba("versiones", ([("2020preX", "2021pubY")], [])))
    monkeypatch.setattr(sw, "sweep_web", graba("web", (["2006Rasmussen: distinto"], [])))
    monkeypatch.setattr(sw, "sweep_ground_truth", graba("ground-truth",
                                                        ([("test_star", [("host.teff_K", 5344, 5350)])], [])))
    # #106 — el sexto: `citation_count` es la única metadata que cambia SOLA y admite core (puerta 2).
    monkeypatch.setattr(sw, "sweep_citas", graba("citas-puerta2",
                                                ([("ica", [("2004Himberg", 1200, 1295)])], [])))
    # el APLICADOR no es un detector: se anula por default para que los tests midan la
    # orquestación y no lancen subprocesos contra el árbol de juguete.
    monkeypatch.setattr(sw, "aplicar_ground_truth", lambda slug: None)
    return llamados


def run_main(monkeypatch, argv=()):
    monkeypatch.setattr(sys, "argv", ["sweep_external.py", *argv])
    return sw.main()


def test_pasada_cubre_los_seis_eventos(toy_vault, detectores, monkeypatch, capsys):
    """INV-85: los SEIS, en una pasada. Que falte uno es el modo de falla que esto cierra — el
    ground-truth era un snapshot congelado que nada comparaba, y el conteo de citas de la puerta 2
    (#106) era la última metadata que cambia sola y admite core sin que nada lo dijera."""
    run_main(monkeypatch, ["--yes"])
    assert sorted(detectores) == ["citas-puerta2", "correcciones", "ground-truth", "retracciones",
                                  "versiones", "web"]


def test_pregunta_antes_de_aplicar(toy_vault, detectores, monkeypatch, capsys):
    """Sin `--yes` y sin TTY, la pasada REPORTA y no aplica nada. El diff se ve antes de que un
    valor cambie bajo los pies de la prosa que lo citó."""
    aplicados = []
    monkeypatch.setattr(sw, "aplicar_ground_truth", lambda slug: aplicados.append(slug))  # re-arma
    monkeypatch.setattr(sw.sys.stdin, "isatty", lambda: False)
    rc = run_main(monkeypatch)
    assert aplicados == []
    out = capsys.readouterr().out
    assert "5344" in out and "5350" in out            # el diff se muestra igual
    assert rc != 0                                     # hay cambios pendientes: no es "limpio"


def test_version_nueva_se_propone_no_se_renombra_sola(toy_vault, detectores, monkeypatch, capsys):
    """El renombre reescribe wikilinks de TODA la bóveda: se propone el comando, no se ejecuta.

    ⚠ El assert que había acá (`renombrados == []` sobre un monkeypatch de `sw.rename_paper`) **no
    podía fallar**: `sweep_external` no invoca `rename_paper` en ninguna línea —el import es sólo
    para que los tests lo graben— así que no existía código capaz de appendear. Peor: tampoco cubría
    la regresión que decía cubrir, porque un renombre por `_run("make_notes.py", …)` no pasa por ese
    nombre. Se mide sobre el ÁRBOL: ninguna nota se movió, y el comando salió propuesto."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020preX.md").write_text(
        "---\nbibcode: 2020preX\nmethods: []\ntags: [paper]\n---\n# T\n", encoding="utf-8")
    antes = sorted(p.name for p in cfg.PAPERS.glob("*.md"))
    run_main(monkeypatch, ["--yes"])
    out = capsys.readouterr().out
    assert sorted(p.name for p in cfg.PAPERS.glob("*.md")) == antes, "la pasada no renombra nada"
    assert "--rename-paper 2020preX 2021pubY" in out, "propone el comando"


def test_registra_la_fecha_de_pasada(toy_vault, detectores, monkeypatch):
    """R-4: versionada, en `config/registro/_red.yaml`. Sin esto, otro clon reporta "nunca se
    corrió una pasada de red", que es falso."""
    run_main(monkeypatch, ["--yes"])
    reg = sw.load_ultima_pasada()
    assert reg["fecha"]
    assert sorted(reg["cubrio"]) == ["citas-puerta2", "correcciones", "ground-truth",
                                     "retracciones", "versiones", "web"]
    assert (cfg.REGISTRO / "_red.yaml").exists()


def test_sin_cambios_sale_0(toy_vault, monkeypatch):
    for nombre in ("sweep_retracciones", "sweep_correcciones"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: [])
    for nombre in ("discover_versions", "sweep_ground_truth", "sweep_web"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: ([], []))    # (hallazgos, fallidos)
    assert run_main(monkeypatch) == 0


def test_detector_no_implementado_no_aporta_un_cero(toy_vault, monkeypatch, capsys):
    """D-43 aplicado a la pasada de red: un detector que **no pudo correr** no aporta un cero y no
    entra en `cubrio` — otro clon leería "cubrió: web" y no sería cierto. Ya no hay stub sin
    implementar, así que se siembra el caso real: `sweep_web` se lleva puesta la corrida.  @inv INV-85"""
    for nombre in ("discover_versions", "sweep_ground_truth"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: ([], []))
    for nombre in ("sweep_retracciones", "sweep_correcciones"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: [])
    monkeypatch.setattr(sw, "sweep_web", lambda *a, **k: (_ for _ in ()).throw(
        NotImplementedError("re-snapshot web: npx ausente")))
    rc = run_main(monkeypatch, ["--yes"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "NO EVALUADO" in out and "web" in out
    assert "web" not in sw.load_ultima_pasada()["cubrio"]


def test_sweep_web_ignora_lo_que_no_es_snapshot_web(toy_vault):
    """Un `.txt` de `pdftotext` no tiene URL que re-bajar: no es fallido, es que no aplica."""
    (cfg.FULLTEXT / "tau_ceti").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "tau_ceti" / "2020A.txt").write_text("texto de un PDF", encoding="utf-8")
    assert sw.sweep_web() == ([], [])


def test_sweep_web_detecta_el_cambio_y_no_escribe(toy_vault, monkeypatch):
    """D-41 — el modo de caducidad **más silencioso** de los cinco: una fuente web no tiene DOI ni
    bibcode, nada avisa que cambió, y como el archivo local no se toca **el ancla de fuente tampoco
    se entera**. ⛔ Reporta, no aplica (D-45): el snapshot en disco queda igual.  @inv INV-85"""
    import fetch_web
    d = cfg.FULLTEXT / "gp"
    d.mkdir(parents=True, exist_ok=True)
    txt = d / "2006Rasmussen.txt"
    txt.write_text(f"{cfg.FULLTEXT_WEB_MARK} (off-ADS)\nsource_url : https://x.test/gp\n"
                   "retrieved  : 2026-01-01 (UTC)\n"
                   "# ---- contenido extraído (defuddle) ----\n\nTexto viejo.\n", encoding="utf-8")
    antes = txt.read_text(encoding="utf-8")
    monkeypatch.setattr(fetch_web, "fetch", lambda url: "Texto NUEVO y distinto.")
    hallazgos, fallidos = sw.sweep_web()
    assert fallidos == [] and len(hallazgos) == 1
    assert "el snapshot cambió" in hallazgos[0] and "--force" in hallazgos[0]
    assert txt.read_text(encoding="utf-8") == antes, "reporta, no aplica"


def test_sweep_web_calla_si_la_pagina_no_cambio(toy_vault, monkeypatch):
    """El header lleva `retrieved` y la versión del extractor —que cambian en cada corrida—, así que
    se compara el CUERPO: hashear el archivo entero haría que toda re-bajada se viera como cambio."""
    import fetch_web
    d = cfg.FULLTEXT / "gp"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2006Rasmussen.txt").write_text(
        f"{cfg.FULLTEXT_WEB_MARK} (off-ADS)\nsource_url : https://x.test/gp\n"
        "retrieved  : 2026-01-01 (UTC)\nextractor  : defuddle 0.1\n"
        "# ---- contenido extraído (defuddle) ----\n\nTexto igual.\n", encoding="utf-8")
    monkeypatch.setattr(fetch_web, "fetch", lambda url: "Texto igual.")
    assert sw.sweep_web() == ([], [])


def test_sweep_web_sin_source_url_es_fallido_no_limpio(toy_vault):
    """No se puede re-bajar lo que no se sabe de dónde salió. Contarlo como "no cambió" sería el
    cero inventado: el registro afirmaría haber mirado un snapshot que nadie pudo re-pedir."""
    d = cfg.FULLTEXT / "gp"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2006Rasmussen.txt").write_text(
        f"{cfg.FULLTEXT_WEB_MARK} (off-ADS)\nretrieved  : 2026-01-01 (UTC)\n"
        "# ---- contenido extraído (defuddle) ----\n\nTexto.\n", encoding="utf-8")
    hallazgos, fallidos = sw.sweep_web()
    assert hallazgos == [] and fallidos == ["gp/2006Rasmussen"]


def test_correcciones_se_leen_del_vault(toy_vault):
    """Devolvía `[]` fijo y aun así contaba como cubierto: la pasada decía "cubrió: correcciones" y
    no listaba ninguna. El dato SÍ está —lo estampa el barrido de Crossref—, sólo que nadie lo leía."""
    from conftest import mk_note
    mk_note(cfg.PAPERS, "2020corC...1..1C",
            {"tags": ["paper"], "bibcode": "2020corC...1..1C",
             "corrections": [{"type": "corrigendum", "date": "2023-07-01"}]}, "")
    mk_note(cfg.PAPERS, "2020sanS...1..1S", {"tags": ["paper"], "bibcode": "2020sanS...1..1S"}, "")
    hallazgos = sw.sweep_correcciones()
    assert len(hallazgos) == 1 and "2020corC...1..1C" in hallazgos[0]
    assert "corrigendum" in hallazgos[0]


# ── El cero inventado en la pasada de red (auditoría P0-1/P0-2) ──────────────

def test_retracciones_rc2_no_es_limpio(toy_vault, monkeypatch, capsys):
    """`check_retractions` tiene TRES códigos y acá se leían dos: el `rc == 2` ("no pude chequear")
    colapsaba contra el 0 y salía como limpio, con `cubrio` registrando la pasada como hecha. Es el
    cero inventado en el detector que más caro sale equivocar: una fuente retractada citada rompe
    la frontera dura.  @inv INV-85"""
    monkeypatch.setattr(sw, "_run", lambda *a: 2)
    with pytest.raises(NotImplementedError, match="no pudo chequear"):
        sw.sweep_retracciones()


def test_retracciones_rc0_y_rc1_siguen_distinguiendose(toy_vault, monkeypatch):
    monkeypatch.setattr(sw, "_run", lambda *a: 0)
    assert sw.sweep_retracciones() == []
    monkeypatch.setattr(sw, "_run", lambda *a: 1)
    assert len(sw.sweep_retracciones()) == 1


def test_ground_truth_con_nea_caida_no_dice_haber_cubierto(toy_vault, monkeypatch, capsys):
    """Con NEA caída **todos** los sujetos fallan por ítem (a propósito: uno raro no tumba la
    pasada), la lista de cambios queda vacía y antes el registro afirmaba "cubrió: ground-truth ·
    0 cosas para revisar". La próxima pasada tomaba ese registro como línea de base."""
    from conftest import write_yaml
    write_yaml(cfg.STARS_YAML, {"Estrella Test": {"slug": "test_star"}})
    (cfg.GROUND_TRUTH).mkdir(parents=True, exist_ok=True)
    (cfg.GROUND_TRUTH / "test_star.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sw.fetch_ground_truth, "nea_diff",
                        lambda slug: (_ for _ in ()).throw(RuntimeError("NEA 503")))
    cambios, fallidos = sw.sweep_ground_truth()
    assert cambios == [] and fallidos == ["test_star"], "el fallo por ítem tiene que salir declarado"

    for nombre in ("sweep_retracciones", "sweep_correcciones"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: [])
    for nombre in ("discover_versions", "sweep_web"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: ([], []))
    rc = run_main(monkeypatch)
    out = capsys.readouterr().out
    assert rc == 2, "no evaluado gana sobre limpio"
    assert "ground-truth" not in out.split("cubrió:")[-1].split("·")[0], out
    assert "NO evaluado" in out and "ground-truth" in out


def test_versiones_con_ads_caido_no_dice_haber_cubierto(toy_vault, monkeypatch):
    """Gemelo del anterior en el otro detector: `discover_versions` traga el error por nota."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020arXivX.md").write_text(
        "---\nbibcode: 2020arXivX\narxiv_id: 2001.1\nmethods: []\ntags: [paper]\n---\n# T\n",
        encoding="utf-8")
    import query_ads
    monkeypatch.setattr(query_ads, "query_ads",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ADS 500")))
    hallazgos, fallidos = sw.discover_versions()
    assert hallazgos == [] and fallidos == ["2020arXivX"]


def test_ground_truth_ilegible_cuenta_como_fallido_no_como_sin_cambios(toy_vault, monkeypatch):
    """AUD-43: un snapshot ilegible tiene que entrar en `fallidos`, no devolver «sin cambios».

    `nea_diff` atrapaba el JSON roto y devolvía `[]`, así que el slug no entraba en `fallidos` y
    `_cubrir` estampaba `cubrio: ground-truth` en `_red.yaml` sobre una pasada que **no comparó
    nada** — el registro falso que el propio docstring de `sweep_ground_truth` dice existir para
    impedir, y que la corrida siguiente toma como línea de base.  @inv INV-85
    """
    cfg.GROUND_TRUTH.mkdir(parents=True, exist_ok=True)
    (cfg.GROUND_TRUTH / "test_star.json").write_text("{ esto no es json", encoding="utf-8")
    cambios, fallidos = sw.sweep_ground_truth()
    assert cambios == []
    assert "test_star" in fallidos, "el snapshot ilegible no se puede leer como «no cambió nada»"


def test_aplicar_ground_truth_registra_que_cambio_para_que_el_lint_pida_la_marca(toy_vault, monkeypatch):
    """`_cambios` es lo que hace detectable la caducidad del ground-truth (AUD-42).

    El ancla de fuente hashea `raw/fulltext/**/*.txt` y **nunca** el JSON de NEA, así que un valor
    corregido cambia bajo los pies de la prosa que ya lo citó y ninguna fila de verificación se
    entera. El diff se calcula ANTES de re-bajar (después daría vacío, comparándose consigo mismo)
    y se persiste DESPUÉS, sobre el payload nuevo.  @inv INV-85
    """
    cfg.GROUND_TRUTH.mkdir(parents=True, exist_ok=True)
    gt = cfg.GROUND_TRUTH / "test_star.json"
    gt.write_text(json.dumps({"star": "Estrella Test", "slug": "test_star",
                              "host": {"teff_K": 5344}, "planets": []}), encoding="utf-8")
    monkeypatch.setattr(fetch_ground_truth, "nea_diff",
                        lambda slug: [("host.teff_K", 5344, 5390)])
    monkeypatch.setattr(sw, "_run", lambda *a, **k: 0)     # el re-fetch real no corre acá

    sw.aplicar_ground_truth("test_star")

    cambios = json.loads(gt.read_text(encoding="utf-8"))["_cambios"]
    assert len(cambios) == 1
    assert cambios[0]["campo"] == "host.teff_K"
    assert (cambios[0]["viejo"], cambios[0]["nuevo"]) == (5344, 5390)
    assert cambios[0]["fecha"]


def test_aplicar_ground_truth_sin_cambios_no_ensucia_el_json(toy_vault, monkeypatch):
    """Sin diff no se estampa `_cambios`: si no, el lint pediría la marca en cada pasada de red y
    el hallazgo se volvería ruido fijo."""
    cfg.GROUND_TRUTH.mkdir(parents=True, exist_ok=True)
    gt = cfg.GROUND_TRUTH / "test_star.json"
    gt.write_text(json.dumps({"slug": "test_star", "host": {}, "planets": []}), encoding="utf-8")
    monkeypatch.setattr(fetch_ground_truth, "nea_diff", lambda slug: [])
    monkeypatch.setattr(sw, "_run", lambda *a, **k: 0)
    sw.aplicar_ground_truth("test_star")
    assert "_cambios" not in json.loads(gt.read_text(encoding="utf-8"))


# ── sweep_citas: el sexto detector (#106, INV-104) ──────────────────────────
def _tema_citas(monkeypatch, umbral, notas, frescos, revienta=False):
    import query_ads
    monkeypatch.setattr(cfg, "load_themes", lambda: {
        "ica": ({"title": "T", "fundacional_min_citas": umbral} if umbral is not None
                else {"title": "T"})})
    monkeypatch.setattr(cfg, "notes_of_subject",
                        lambda s: [(b, {"bibcode": b, "citation_count": n}, "") for b, n in notas])

    def fake(bibs):
        if revienta:
            raise RuntimeError("ADS 503")
        return [{"bibcode": b, "citation_count": n} for b, n in frescos.items()]
    monkeypatch.setattr(query_ads, "fetch_bibcodes", fake)


def test_sweep_citas_detecta_el_cruce_hacia_arriba(monkeypatch):
    """@inv INV-104"""
    _tema_citas(monkeypatch, 1000, [("2004A..1", 900)], {"2004A..1": 1100})
    out, fallidos = sw.sweep_citas()
    assert out == [("ica", [("2004A..1", 900, 1100)])] and fallidos == []


def test_sweep_citas_detecta_el_cruce_hacia_abajo(monkeypatch):
    """NEA-style: pasa si el umbral se movió entre corridas y el conteo quedó por debajo."""
    _tema_citas(monkeypatch, 1000, [("2004A..1", 1100)], {"2004A..1": 900})
    out, _f = sw.sweep_citas()
    assert out[0][1] == [("2004A..1", 1100, 900)]


def test_sweep_citas_calla_si_nadie_cruzo(monkeypatch):
    _tema_citas(monkeypatch, 1000, [("2004A..1", 1100)], {"2004A..1": 1300})
    assert sw.sweep_citas() == ([], [])


def test_sweep_citas_ignora_el_tema_sin_umbral_declarado(monkeypatch):
    """Puerta cerrada por no declarada (D-26): no hay umbral que cruzar, no hay nada que vigilar."""
    _tema_citas(monkeypatch, None, [("2004A..1", 5)], {"2004A..1": 999999})
    assert sw.sweep_citas() == ([], [])


def test_sweep_citas_no_afirma_un_cruce_si_falta_un_lado(monkeypatch):
    _tema_citas(monkeypatch, 1000, [("2004A..1", None)], {"2004A..1": 5000})
    assert sw.sweep_citas() == ([], [])


def test_sweep_citas_con_ads_caido_es_fallido_no_limpio(monkeypatch):
    """Mismo contrato que sweep_ground_truth: sin los fallidos, el registro afirma haber mirado."""
    _tema_citas(monkeypatch, 1000, [("2004A..1", 900)], {}, revienta=True)
    out, fallidos = sw.sweep_citas()
    assert out == [] and fallidos == ["ica"]


def test_una_segunda_pasada_no_borra_la_caducidad_pendiente(toy_vault, monkeypatch):
    """Issue #130 — `payload["_cambios"] = [...]` **asignaba**: la segunda aplicación de un diff de
    NEA perdía los cambios de la primera, y el lint dejaba de pedir la marca por ellos. La marca
    pendiente de un campo desaparecía **sin que nadie la hubiera resuelto**, con la prosa todavía
    citando el valor viejo.

    Es lo contrario de D-28/`busquedas` y de `save_barrido`/`save_descubrimiento`, que acumulan por
    diseño: el registro guarda lo que no es regenerable, y una caducidad pendiente no lo es."""
    cfg.GROUND_TRUTH.mkdir(parents=True, exist_ok=True)
    gt = cfg.GROUND_TRUTH / "test_star.json"
    gt.write_text(json.dumps({"slug": "test_star", "host": {"teff_K": 5344}, "planets": []}),
                  encoding="utf-8")
    monkeypatch.setattr(sw, "_run", lambda *a, **k: 0)

    monkeypatch.setattr(fetch_ground_truth, "nea_diff", lambda s: [("host.teff_K", 5344, 5390)])
    sw.aplicar_ground_truth("test_star")
    monkeypatch.setattr(fetch_ground_truth, "nea_diff", lambda s: [("planets.b.P_days", 3.1, 9.9)])
    sw.aplicar_ground_truth("test_star")

    campos = [c["campo"] for c in json.loads(gt.read_text(encoding="utf-8"))["_cambios"]]
    assert set(campos) == {"host.teff_K", "planets.b.P_days"}, \
        "la caducidad de la primera pasada sigue pendiente: nadie la resolvió"


def test_un_campo_que_vuelve_a_cambiar_conserva_el_valor_QUE_LA_PROSA_CITA(toy_vault, monkeypatch):
    """La otra mitad de #130: acumular no puede volverse duplicar. Si el mismo campo cambia dos
    veces antes de que alguien toque la prosa, lo pendiente es UNA cosa —la prosa cita `viejo` y NEA
    hoy dice `nuevo`—, así que la entrada se actualiza en vez de agregarse. Y el `viejo` que se
    conserva es el **original**: es el que está escrito en la nota."""
    cfg.GROUND_TRUTH.mkdir(parents=True, exist_ok=True)
    gt = cfg.GROUND_TRUTH / "test_star.json"
    gt.write_text(json.dumps({"slug": "test_star", "host": {"teff_K": 5344}, "planets": []}),
                  encoding="utf-8")
    monkeypatch.setattr(sw, "_run", lambda *a, **k: 0)
    monkeypatch.setattr(fetch_ground_truth, "nea_diff", lambda s: [("host.teff_K", 5344, 5390)])
    sw.aplicar_ground_truth("test_star")
    monkeypatch.setattr(fetch_ground_truth, "nea_diff", lambda s: [("host.teff_K", 5390, 5401)])
    sw.aplicar_ground_truth("test_star")

    cambios = json.loads(gt.read_text(encoding="utf-8"))["_cambios"]
    assert len(cambios) == 1, "un campo, una caducidad pendiente"
    assert (cambios[0]["viejo"], cambios[0]["nuevo"]) == (5344, 5401), \
        "el `viejo` es el que la prosa cita, no el intermedio que nadie escribió nunca"


def test_el_registro_declara_lo_que_NO_se_pudo_mirar(toy_vault, monkeypatch, capsys):
    """Issue #172 — el docstring de `_cubrir` dice *"si falló una parte, **el registro** dice cuántos
    quedaron sin mirar"*, y `save_ultima_pasada(cubrio)` persistía sólo `fecha`/`cubrio`/`version`.
    En el archivo versionado, un detector que **falló parcialmente** quedaba byte-idéntico a uno que
    **nunca corrió**.

    El propio módulo justifica versionar la caducidad porque *"sin versionarla, otro clon reporta
    'nunca se corrió', que es falso"*. Acá el fallo parcial se perdía al revés: quedaba sólo en
    stdout — el mismo argumento con el que #55 y #88 mudaron el triage y el barrido al registro."""
    for nombre in ("sweep_retracciones", "sweep_correcciones"):
        monkeypatch.setattr(sw, nombre, lambda: [])
    monkeypatch.setattr(sw, "discover_versions", lambda: ([], []))
    monkeypatch.setattr(sw, "sweep_web", lambda: ([], ["tema/a", "tema/b", "tema/c"]))
    monkeypatch.setattr(sw, "sweep_ground_truth", lambda: ([], []))
    monkeypatch.setattr(sw, "sweep_citas", lambda: ([], []))

    assert sw.main([]) == 2, "un detector que no pudo correr cuenta para el exit"
    reg = sw.load_ultima_pasada()
    assert "web" not in reg["cubrio"], "no se afirma haber mirado lo que no se miró"
    assert "web" in str(reg.get("no_evaluados")), "y se DECLARA cuál quedó sin mirar"
    assert "3" in str(reg.get("no_evaluados")), "con cuántos sujetos"


def test_una_pasada_limpia_no_declara_no_evaluados(toy_vault, monkeypatch):
    """La otra mitad de #172: el campo sólo aparece cuando hay algo que declarar. Un
    `no_evaluados: []` fijo en cada pasada sería ruido en el único artefacto no regenerable."""
    for nombre in ("sweep_retracciones", "sweep_correcciones"):
        monkeypatch.setattr(sw, nombre, lambda: [])
    monkeypatch.setattr(sw, "discover_versions", lambda: ([], []))
    for nombre in ("sweep_web", "sweep_ground_truth", "sweep_citas"):
        monkeypatch.setattr(sw, nombre, lambda: ([], []))
    sw.main([])
    assert "no_evaluados" not in sw.load_ultima_pasada()


def test_sweep_citas_dice_las_claves_off_ADS_que_nadie_consulto(monkeypatch, capsys):
    """AUD-158 — las claves sintéticas off-ADS no son consultables en ADS y se salteaban **mudas**.

    La pasada las contaba como miradas y el registro afirmaba haber vigilado su conteo de citas: el
    cero inventado de D-43, dentro del detector que existe justamente para ver que el mundo se
    movió. No son un fallo (es una propiedad de la clave, no una caída de red), así que se nombran
    aparte de `fallidos`."""
    _tema_citas(monkeypatch, 1000, [("2006Rasmussen", 900), ("2004A..1", 900)],
                {"2004A..1": 1100})
    out, fallidos = sw.sweep_citas()
    assert fallidos == [], "una clave no consultable no es una caída de red"
    salida = capsys.readouterr().out
    assert "clave sintética off-ADS" in salida and "2006Rasmussen" in salida
