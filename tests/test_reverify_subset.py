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


def _en_disco(tmp_path, texto=None) -> Path:
    """La nota en disco, con su tabla ya en el hermano `<nota>.verif.md` (#344).

    Se parte con el MIGRADOR real: un doble con otro contrato esconde el bug en la diferencia
    (regla de método nº2), y acá el contrato es justamente qué queda en la nota y qué se va."""
    import make_notes
    nota = tmp_path / "n.md"
    nota.write_text(texto if texto is not None else _nota_con_anclas(), encoding="utf-8")
    make_notes.migrate_verif_sidecar(nota)
    return nota


def _clasificar(tmp_path, texto=None, umbral=0.60) -> dict:
    """`classify` sobre la nota en disco: las filas salen del hermano (#344)."""
    nota = _en_disco(tmp_path, texto)
    return rs.classify(nota, nota.read_text(encoding="utf-8"), umbral)


def test_classify_reparte_los_tres_baldes_con_la_nota_intacta(tmp_path):
    """Sin tocar nada, los dos pares son re-anclables por ancla idéntica y no hay nada que hacer."""
    r = _clasificar(tmp_path)
    assert r["sin_bloque"] is False
    assert len(r["asignado"]) == 2 and r["sin_fila"] == [] and r["huerfanas"] == []


def test_classify_manda_al_subconjunto_la_afirmacion_que_cambio(tmp_path):
    """La otra mitad: si la corrección cambió lo que la afirmación dice, el par va a re-verificar y
    su fila queda huérfana. Es la distinción que #282 existe para hacer."""
    # ⚠ sólo en el CUERPO: la misma cadena vive en la celda `Afirmación` de la fila, y pisarla
    # también haría que la fila «siga hablando» del texto nuevo — el test dejaría de probar nada.
    texto = _nota_con_anclas().replace(
        "Ninguna fuente aplica separación ciega de componentes independientes",
        "El período orbital resulta francamente incompatible con la solución publicada", 1)
    r = _clasificar(tmp_path, texto)
    assert len(r["sin_fila"]) == 1 and r["sin_fila"][0].bibcode == "2021bbb...2..2B"
    assert len(r["huerfanas"]) == 1 and r["huerfanas"][0].bibcode == "2021bbb...2..2B"
    assert len(r["asignado"]) == 1, "el par que no se tocó perdió su fila"


def test_classify_sin_bloque_no_devuelve_un_cero_inventado(tmp_path):
    """D-43: una nota sin bloque evaluable **no** es «cero pares vencidos». Todo va al subconjunto y
    se declara, porque un `(0)` que nadie midió se lee como veredicto."""
    texto = _nota_con_anclas().split("## Verificación de citas")[0]
    r = _clasificar(tmp_path, texto)
    assert r["sin_bloque"] is True
    assert len(r["sin_fila"]) == len(r["pares"]) == 2 and r["asignado"] == {}


def test_by_source_agrupa_por_bibcode(tmp_path):
    """El fan-out es **un agente por fuente** (#100): el agrupamiento es lo que lo hace posible."""
    r = _clasificar(tmp_path, _nota_con_anclas().split("## Verificación de citas")[0])
    grupos = rs._by_source(r["sin_fila"])
    assert sorted(grupos) == ["2020aaa...1..1A", "2021bbb...2..2B"]
    assert all(len(v) == 1 for v in grupos.values())


def test_main_escribe_el_json_agrupado_y_no_toca_la_nota(tmp_path, monkeypatch, capsys):
    """El contrato del CLI: reporta, escribe el JSON si se lo piden, y **no toca la nota**."""
    nota = _en_disco(tmp_path, _nota_con_anclas().split("## Verificación de citas")[0])
    antes = nota.read_text(encoding="utf-8")
    salida = tmp_path / "sub.json"
    monkeypatch.setattr(sys, "argv", ["reverify_subset.py", str(nota), "--json", str(salida)])
    assert rs.main() == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    sub = datos["re_verificar"]
    assert sorted(sub) == ["2020aaa...1..1A", "2021bbb...2..2B"]
    assert "ancla" in sub["2020aaa...1..1A"][0] and "texto" in sub["2020aaa...1..1A"][0]
    assert nota.read_text(encoding="utf-8") == antes, "el emisor tocó la nota"
    assert "sin tabla de verificación evaluable" in capsys.readouterr().out


# ── #285 · el re-anclaje que se proponía y no se emitía ──────────────────────────────────────────


def test_el_json_emite_las_TRES_listas_no_una(tmp_path, monkeypatch):
    """#285 — `--json` escribía **sólo** el subconjunto a re-verificar, así que el grupo más grande
    —y el único donde un error transfiere un veredicto al par equivocado— se aceptaba a ciegas."""
    nota = _en_disco(tmp_path)
    salida = tmp_path / "sub.json"
    monkeypatch.setattr(sys, "argv", ["reverify_subset.py", str(nota), "--json", str(salida)])
    assert rs.main() == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert sorted(datos) == ["banda", "huerfanas", "nota", "re_anclaje", "re_verificar", "umbral"]
    assert len(datos["re_anclaje"]) == 2, "el emparejamiento propuesto no se emitió"
    uno = datos["re_anclaje"][0]
    for clave in ("fila", "bibcode", "score", "ancla_vieja", "ancla_nueva", "veredicto", "extracto"):
        assert clave in uno, clave
    assert uno["score"] == 1.0, "el par intacto se empareja por ancla idéntica"


def test_la_banda_de_revision_lista_el_re_anclaje_flojo(tmp_path, monkeypatch, capsys):
    """La banda de #285: lo que entra por cobertura baja sale listado para revisar A MANO, con su
    score y las dos puntas. Medido: 2 de 86 propuestas eran a la fila equivocada, las dos apenas
    sobre el umbral y las dos **dentro del mismo bibcode** (donde la guarda de bibcode no ve nada)."""
    # se reescribe el CUERPO de un par: la fila sigue hablando de lo mismo pero sólo a medias
    texto = _nota_con_anclas().replace(
        "La amplitud rotacional vale cero coma cincuenta metros por segundo [[2020aaa...1..1A]].",
        "La amplitud rotacional vale otra cosa distinta según el instrumento [[2020aaa...1..1A]].", 1)
    nota = _en_disco(tmp_path, texto)
    monkeypatch.setattr(sys, "argv", ["reverify_subset.py", str(nota), "--umbral", "0.30"])
    assert rs.main() == 0
    out = capsys.readouterr().out
    assert "REVISAR A MANO" in out, out
    assert "fila 1" in out and "2020aaa...1..1A" in out


def test_la_banda_no_marca_el_re_anclaje_por_ancla_identica(tmp_path, monkeypatch, capsys):
    """La otra dirección: un par que nadie tocó tiene score 1,0 y no puede caer en la banda — si
    cayera, la banda sería ruido sobre la nota entera y se dejaría de mirar."""
    nota = _en_disco(tmp_path)
    monkeypatch.setattr(sys, "argv", ["reverify_subset.py", str(nota)])
    assert rs.main() == 0
    assert "REVISAR A MANO" not in capsys.readouterr().out


def test_reanchor_list_ordena_por_score_ascendente(tmp_path):
    """Lo dudoso primero: es lo que se revisa."""
    r = _clasificar(tmp_path)
    lista = rs.reanchor_list(r)
    assert [x["score"] for x in lista] == sorted(x["score"] for x in lista)


def test_main_rehusa_sobre_una_nota_que_no_existe(tmp_path, monkeypatch):
    """Un subconjunto vacío sobre una nota inexistente se leería como «no hay nada que
    re-verificar»: el falso limpio de D-43. Se rehúsa con rc 2."""
    monkeypatch.setattr(sys, "argv", ["reverify_subset.py", str(tmp_path / "no.md")])
    assert rs.main() == 2
