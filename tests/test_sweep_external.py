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

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import lib_config as cfg          # noqa: E402
import sweep_external as sw       # noqa: E402


@pytest.fixture
def detectores(monkeypatch):
    """Los cinco detectores, grabados. Cada uno devuelve un hallazgo para que la pasada tenga algo
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
    monkeypatch.setattr(sw, "sweep_web", graba("web", ["2006Rasmussen: distinto"]))
    monkeypatch.setattr(sw, "sweep_ground_truth", graba("ground-truth",
                                                        ([("test_star", [("host.teff_K", 5344, 5350)])], [])))
    # el APLICADOR no es un detector: se anula por default para que los tests midan la
    # orquestación y no lancen subprocesos contra el árbol de juguete.
    monkeypatch.setattr(sw, "aplicar_ground_truth", lambda slug: None)
    return llamados


def run_main(monkeypatch, argv=()):
    monkeypatch.setattr(sys, "argv", ["sweep_external.py", *argv])
    return sw.main()


def test_pasada_cubre_los_cinco_eventos(toy_vault, detectores, monkeypatch, capsys):
    """INV-85: los CINCO, en una pasada. Que falte uno es el modo de falla que esto cierra — el
    ground-truth era un snapshot congelado que nada comparaba."""
    run_main(monkeypatch, ["--yes"])
    assert sorted(detectores) == ["correcciones", "ground-truth", "retracciones", "versiones", "web"]


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
    """El renombre reescribe wikilinks de toda la bóveda (D-19): eso no se hace sin que alguien lo
    pida. Se PROPONE el comando."""
    renombrados = []
    monkeypatch.setattr(sw, "rename_paper", lambda a, b: renombrados.append((a, b)))
    run_main(monkeypatch, ["--yes"])
    assert renombrados == []
    assert "--rename-paper 2020preX 2021pubY" in capsys.readouterr().out


def test_registra_la_fecha_de_pasada(toy_vault, detectores, monkeypatch):
    """R-4: versionada, en `config/registro/_red.yaml`. Sin esto, otro clon reporta "nunca se
    corrió una pasada de red", que es falso."""
    run_main(monkeypatch, ["--yes"])
    reg = sw.load_ultima_pasada()
    assert reg["fecha"]
    assert sorted(reg["cubrio"]) == ["correcciones", "ground-truth", "retracciones", "versiones",
                                     "web"]
    assert (cfg.REGISTRO / "_red.yaml").exists()


def test_sin_cambios_sale_0(toy_vault, monkeypatch):
    for nombre in ("sweep_retracciones", "sweep_correcciones", "sweep_web"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: [])
    for nombre in ("discover_versions", "sweep_ground_truth"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: ([], []))    # (hallazgos, fallidos)
    assert run_main(monkeypatch) == 0


def test_detector_no_implementado_no_aporta_un_cero(toy_vault, monkeypatch, capsys):
    """D-43 aplicado a la pasada de red. `sweep_web` todavía no existe: si devolviera `[]` la
    pasada cerraría en verde y el registro de caducidad diría "cubrió: web" — otro clon leería que
    los snapshots se chequearon y no es cierto. Levanta, se reporta como NO evaluado, no entra en
    `cubrio`, y el exit es 2.  @inv INV-85"""
    for nombre in ("discover_versions", "sweep_ground_truth"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: ([], []))
    for nombre in ("sweep_retracciones", "sweep_correcciones",
                   "sweep_ground_truth"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: [])
    rc = run_main(monkeypatch, ["--yes"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "NO EVALUADO" in out and "web" in out
    assert "web" not in sw.load_ultima_pasada()["cubrio"]


def test_sweep_web_declara_que_no_esta(toy_vault):
    """El stub levanta con el motivo, no devuelve vacío."""
    with pytest.raises(NotImplementedError, match="fetch_web.refresh"):
        sw.sweep_web()


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

    for nombre in ("sweep_retracciones", "sweep_correcciones", "sweep_web"):
        monkeypatch.setattr(sw, nombre, lambda *a, **k: [])
    monkeypatch.setattr(sw, "discover_versions", lambda *a, **k: ([], []))
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
