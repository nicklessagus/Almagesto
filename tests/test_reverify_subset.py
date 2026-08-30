"""#282 / #257 — el emisor del subconjunto de re-verificación y del re-anclaje."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import reverify_subset as rs   # noqa: E402


NOTA = """---
tags: [star]
---

# X

## Resumen

La amplitud rotacional vale cero coma cincuenta metros por segundo [[2020aaa...1..1A]].

Ninguna fuente aplica separación ciega de componentes independientes [[2021bbb...2..2B]].

## Verificación de citas (2020-01-01)

2 pares; 2 soportadas / 0 no-soportadas / 0 contradicen (resueltas) / 0 no verificables — 0 con condición declarada.

| # | Afirmación (extracto) | Fuente | Veredicto | Evidencia | Ancla | Hash fuente | Condición |
|---|---|---|---|---|---|---|---|
| 1 | La amplitud rotacional vale cero coma cincuenta metros por segundo | [[2020aaa...1..1A]] | soportada | «…» (p. 5) | {a1} | pdf:bbbbbbbbbb |  |
| 2 | Ninguna fuente aplica separación ciega de componentes independientes | [[2021bbb...2..2B]] | soportada | «…» (p. 7) | {a2} | pdf:cccccccccc |  |
"""


def _nota_con_anclas() -> str:
    """La nota de arriba con las anclas REALES de sus dos pares.

    Se calculan con el mismo código que después las compara, que es el punto de D-4: las anclas no
    se escriben a ojo."""
    import lib_blocks as lb
    base = NOTA.replace("{a1}", "0" * 10).replace("{a2}", "1" * 10)
    a1, a2 = [p.anchor for p in lb.pairs_of(base)]
    return NOTA.replace("{a1}", a1).replace("{a2}", a2)


def test_classify_reparte_los_tres_baldes_con_la_nota_intacta():
    """Sin tocar nada, los dos pares son re-anclables por ancla idéntica y no hay nada que hacer."""
    r = rs.classify(_nota_con_anclas(), umbral=0.60)
    assert r["sin_bloque"] is False
    assert len(r["asignado"]) == 2 and r["sin_fila"] == [] and r["huerfanas"] == []


def test_classify_manda_al_subconjunto_la_afirmacion_que_cambio():
    """La otra mitad: si la corrección cambió lo que la afirmación dice, el par va a re-verificar y
    su fila queda huérfana. Es la distinción que #282 existe para hacer."""
    # ⚠ sólo en el CUERPO: la misma cadena vive en la celda `Afirmación` de la fila, y pisarla
    # también haría que la fila «siga hablando» del texto nuevo — el test dejaría de probar nada.
    texto = _nota_con_anclas().replace(
        "Ninguna fuente aplica separación ciega de componentes independientes",
        "El período orbital resulta francamente incompatible con la solución publicada", 1)
    r = rs.classify(texto, umbral=0.60)
    assert len(r["sin_fila"]) == 1 and r["sin_fila"][0].bibcode == "2021bbb...2..2B"
    assert len(r["huerfanas"]) == 1 and r["huerfanas"][0].bibcode == "2021bbb...2..2B"
    assert len(r["asignado"]) == 1, "el par que no se tocó perdió su fila"


def test_classify_sin_bloque_no_devuelve_un_cero_inventado():
    """D-43: una nota sin bloque evaluable **no** es «cero pares vencidos». Todo va al subconjunto y
    se declara, porque un `(0)` que nadie midió se lee como veredicto."""
    texto = _nota_con_anclas().split("## Verificación de citas")[0]
    r = rs.classify(texto, umbral=0.60)
    assert r["sin_bloque"] is True
    assert len(r["sin_fila"]) == len(r["pares"]) == 2 and r["asignado"] == {}


def test_by_source_agrupa_por_bibcode():
    """El fan-out es **un agente por fuente** (#100): el agrupamiento es lo que lo hace posible."""
    r = rs.classify(_nota_con_anclas().split("## Verificación de citas")[0], umbral=0.60)
    grupos = rs._by_source(r["sin_fila"])
    assert sorted(grupos) == ["2020aaa...1..1A", "2021bbb...2..2B"]
    assert all(len(v) == 1 for v in grupos.values())


def test_main_escribe_el_json_agrupado_y_no_toca_la_nota(tmp_path, monkeypatch, capsys):
    """El contrato del CLI: reporta, escribe el JSON si se lo piden, y **no toca la nota**."""
    nota = tmp_path / "n.md"
    nota.write_text(_nota_con_anclas().split("## Verificación de citas")[0], encoding="utf-8")
    antes = nota.read_text(encoding="utf-8")
    salida = tmp_path / "sub.json"
    monkeypatch.setattr(sys, "argv", ["reverify_subset.py", str(nota), "--json", str(salida)])
    assert rs.main() == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert sorted(datos) == ["2020aaa...1..1A", "2021bbb...2..2B"]
    assert "ancla" in datos["2020aaa...1..1A"][0] and "texto" in datos["2020aaa...1..1A"][0]
    assert nota.read_text(encoding="utf-8") == antes, "el emisor tocó la nota"
    assert "sin bloque" in capsys.readouterr().out


def test_main_rehusa_sobre_una_nota_que_no_existe(tmp_path, monkeypatch):
    """Un subconjunto vacío sobre una nota inexistente se leería como «no hay nada que
    re-verificar»: el falso limpio de D-43. Se rehúsa con rc 2."""
    monkeypatch.setattr(sys, "argv", ["reverify_subset.py", str(tmp_path / "no.md")])
    assert rs.main() == 2
