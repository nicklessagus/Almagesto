"""#259 — el validador de la salida del fan-out de `verify-citations`: CLI y contadores.

Vive en su propio archivo para que `python tools/mutar.py --dirigida
scripts/check_verify_fanout.py` lo encuentre: ese modo corre SÓLO
`tests/test_<módulo>.py`, así que un test en otro archivo deja la función sin red
medible (y el modo lo reporta como «sin test propio», que es lo correcto).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import check_verify_fanout as cvf   # noqa: E402
import lib_blocks as lb             # noqa: E402

SKILL = RAIZ / ".claude" / "skills" / "verify-citations" / "SKILL.md"

#: Un archivo que CUMPLE, del que salen todas las mutaciones de abajo. Se arma desde la constante
#: para que agregar una clave obligatoria al schema no deje este molde silenciosamente viejo.
def _ok(**cambios) -> dict:
    par = {k: "x" for k in lb.VERIF_FANOUT_SCHEMA["par"]}
    par.update({k: "" for k in lb.VERIF_FANOUT_SCHEMA["par_opt"]})
    datos = {"bibcode": "2020ApJ...900....1A", "pares": [par]}
    datos.update(cambios)
    return datos


# ── el validador de directorio: rehúsa, cuenta, y no degrada ─────────────────

def _dir_con(tmp_path: Path, **archivos) -> Path:
    d = tmp_path / "r1"
    d.mkdir()
    for nombre, datos in archivos.items():
        (d / f"{nombre}.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return d


def test_el_validador_rehusa_sobre_un_directorio_que_no_existe(tmp_path, monkeypatch):
    """D-43: «0 archivos con problemas» sobre un directorio que nadie miró es un veredicto que nadie
    midió — el falso limpio que este validador existe para no producir. rc **2**, no 0."""
    monkeypatch.setattr(sys, "argv", ["check_verify_fanout.py", str(tmp_path / "no_existe")])
    assert cvf.main() == 2


def test_el_directorio_vacio_tampoco_es_un_verde(tmp_path, monkeypatch):
    """Medido en el skill: los verificadores de sólo lectura devolvieron el JSON en el mensaje y la
    barrera contó **0 de 30**. Cero archivos no es «todos cumplen»."""
    d = tmp_path / "vacio"
    d.mkdir()
    monkeypatch.setattr(sys, "argv", ["check_verify_fanout.py", str(d)])
    assert cvf.main() == 1


def test_el_validador_nombra_el_archivo_que_no_cumple(tmp_path, monkeypatch, capsys):
    """Con dos archivos y uno malo, el rc no alcanza: el reporte tiene que decir CUÁL re-correr."""
    d = _dir_con(tmp_path, bueno=_ok(), malo={"bibcode": "2020X", "veredictos": []})
    monkeypatch.setattr(sys, "argv", ["check_verify_fanout.py", str(d)])
    assert cvf.main() == 1
    salida = capsys.readouterr().out
    assert "malo.json" in salida and "bueno.json" not in salida


def test_el_json_que_no_parsea_es_un_hallazgo_como_cualquier_otro(tmp_path, monkeypatch, capsys):
    """El fan-out escribe JSON a mano: uno truncado es la misma clase de defecto que una clave
    renombrada, y saltearlo dejaría el conteo corto **sin decirlo**."""
    d = _dir_con(tmp_path, bueno=_ok())
    (d / "roto.json").write_text('{"bibcode": "2020X", "pares": [', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_verify_fanout.py", str(d)])
    assert cvf.main() == 1
    assert "roto.json" in capsys.readouterr().out


def test_el_conteo_de_pares_aborta_si_no_coincide(tmp_path, monkeypatch, capsys):
    """La red barata de #222 (contar antes y después, como la guarda «los pares no bajaron» de
    `apply_fixes`) en el otro extremo de la cadena: un subagente que devolvió **la mitad** de sus
    pares escribe un archivo perfectamente VÁLIDO — la forma no lo ve, el conteo sí."""
    d = _dir_con(tmp_path, a=_ok())            # un solo par
    monkeypatch.setattr(sys, "argv", ["check_verify_fanout.py", str(d), "--esperados", "3"])
    assert cvf.main() != 0
    salida = capsys.readouterr().out
    assert "1" in salida and "3" in salida, salida


def test_el_conteo_que_cierra_no_inventa_un_hallazgo(tmp_path, monkeypatch):
    """Y el simétrico: con los pares que se mandaron a juzgar, rc 0. Un gate que bloquea siempre se
    apaga en la primera corrida."""
    d = _dir_con(tmp_path, a=_ok(), b=_ok())
    monkeypatch.setattr(sys, "argv", ["check_verify_fanout.py", str(d), "--esperados", "2"])
    assert cvf.main() == 0


def test_pair_count_errors_cuenta_solo_lo_que_cumple_y_lo_declara():
    """Un archivo malformado aporta un número de pares **desconocido**: sumarlo como cero cambiaría
    un hallazgo ruidoso por uno silencioso y equivocado. Por eso el mensaje dice sobre cuántos
    archivos contó."""
    assert cvf.pair_count_errors({"a.json": 2}, 2) == []
    (msg,) = cvf.pair_count_errors({"a.json": 2}, 5)
    assert "2" in msg and "5" in msg and "1 archivo" in msg


# ── #369 · el manifiesto: la barrera lee el PLAN en vez de un conteo a ojo ──

def _manifiesto(d: Path, fuentes: dict):
    (d / cvf.MANIFEST).write_text(json.dumps({"nota": "x.md", "fuentes": fuentes,
                                              "pares": sum(fuentes.values())}), encoding="utf-8")


def test_la_barrera_NOMBRA_la_fuente_que_falta(tmp_path):
    """#369 — con `--esperados 60` la barrera decía «faltan 1»; saber CUÁL requirió un script
    ad-hoc. El generador ya sabía el reparto: ahora lo escribe y la barrera lo lee."""
    d = _dir_con(tmp_path, **{"2020ApJ...900....1A": _ok()})
    _manifiesto(d, {"2020ApJ...900....1A": 1, "2011PLoSO...627594P": 1})
    pairs, errors = cvf.check_dir(d)
    errs = cvf.manifest_errors(pairs, json.loads((d / cvf.MANIFEST).read_text()), None)
    assert any("falta la fuente `2011PLoSO...627594P`" in e for e in errs), errs


def test_un_esperados_que_contradice_el_manifiesto_se_RECHAZA(tmp_path):
    """El hueco simétrico y silencioso: un `--esperados` mal contado en la MISMA dirección que la
    fuente que falta habría dado ✅ sobre un fan-out incompleto. El plan lo escribió el generador;
    no se transcribe."""
    d = _dir_con(tmp_path, **{"2020ApJ...900....1A": _ok()})
    _manifiesto(d, {"2020ApJ...900....1A": 1})
    errs = cvf.manifest_errors(cvf.check_dir(d)[0], json.loads((d / cvf.MANIFEST).read_text()), 2)
    assert any("contradice el manifiesto" in e for e in errs), errs


def test_el_manifiesto_NO_cuenta_como_salida_del_fanout(tmp_path):
    """Es un `*.json` en el mismo directorio y no tiene `pares`: sin el recorte, la barrera lo
    reportaría como archivo malformado en cada ronda."""
    d = _dir_con(tmp_path, **{"2020ApJ...900....1A": _ok()})
    _manifiesto(d, {"2020ApJ...900....1A": 1})
    pairs, errors = cvf.check_dir(d)
    assert errors == [] and list(pairs) == ["2020ApJ...900....1A.json"]
