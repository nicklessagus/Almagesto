"""#188 paso 5 / #191 — el cosechador del fan-out de extracción.

Hasta 1.68.0 **no existía**: cada subagente escribía su JSON en `build/<slug>/extraccion/` y
**nadie lo leía**. El cosechado era manual, y por eso `is_extraction` (INV-103, P0) —la función
que distingue una extracción de cualquier otro JSON con `bibcode`— no tenía un solo llamador de
producción. El defecto que la motivó está medido: un cosechador escrito a mano que aceptaba
cualquier JSON con `bibcode` levantó 13 salidas de `verify-citations` de OTRA estrella y pisó 13
notas terminadas, con JSON perfectamente válido — o sea en silencio.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import harvest_views as hv
import lib_config as cfg
import make_notes as mn
from conftest import mk_note, read_fm


BIB = "2020ext....1E"


def extraccion(**cambios) -> dict:
    d = {"bibcode": BIB,
         "vista": {"sujeto": "Estrella Test", "tipo": "star", "txt": "test_star"},
         "role": ["aplicacion"], "methods": ["periodograma"], "thesis_links": [],
         "ground_truth": [{"que": "P_rot", "valor": "34 d", "linea": "412",
                           "regimen": "HARPS 2003-2015", "segunda_mano": None}],
         "ejes": {"rv": "reporta K = 2.5 m/s", "activity": ""},
         "aporte": "mide el P_rot", "hueco": "no separa actividad", "salvedades": []}
    d.update(cambios)
    return d


def sembrar(toy_vault, data=None, *, stem=BIB, fm_extra=None, body=None):
    """Un JSON de extracción en `build/<slug>/extraccion/` + la nota stub que le corresponde."""
    d = cfg.ROOT / "build" / "test_star" / "extraccion"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.json").write_text(json.dumps(data if data is not None else extraccion()),
                                    encoding="utf-8")
    fm = {"bibcode": stem, "tags": ["paper"], "relevance": "high", "stars": ["Estrella Test"],
          "methods": [], "role": [], "thesis_links": [],
          "vistas": [{"sujeto": "Estrella Test", "tipo": "star"}]}
    fm.update(fm_extra or {})
    # el cuerpo por defecto es la PLANTILLA real del stub (paso 3): es contra eso que el
    # cosechador decide si la vista sigue sin leer, y un doble a ojo escondería la diferencia
    # (red #3 del repo).
    return mk_note(toy_vault.PAPERS, stem, fm,
                   body if body is not None else mn.vista_block("Estrella Test", theme=False))


def test_cosecha_estampa_la_vista_con_fecha_txt_y_lente(toy_vault):
    """La vista pasa de DECLARADA a HECHA: la `fecha` es lo que dice que la lectura ocurrió, el
    `txt` de qué copia salió (el ancla de fuente, D-18) y la `lente` con qué facetas se leyó — el
    diff de lente (D-49) a nivel de lectura.

    @inv INV-134"""
    dest = sembrar(toy_vault)
    hv.harvest("test_star")
    v = read_fm(dest)["vistas"]
    assert len(v) == 1 and v[0]["sujeto"] == "Estrella Test" and v[0]["tipo"] == "star"
    assert v[0]["fecha"] and v[0]["txt"] == "test_star"
    assert v[0]["lente"] == ["actividad", "rv"], "las facetas vigentes al leer, del objetivo"


def test_cosecha_mergea_methods_role_y_thesis_links_add_only(toy_vault):
    dest = sembrar(toy_vault, extraccion(methods=["periodograma", "gp"],
                                         thesis_links=["activity-rv"]),
                   fm_extra={"methods": ["bisector"]})
    hv.harvest("test_star")
    fm = read_fm(dest)
    assert set(fm["methods"]) == {"bisector", "periodograma", "gp"}, "add-only: no pisa"
    assert fm["role"] == ["aplicacion"] and fm["thesis_links"] == ["activity-rv"]


def test_cosecha_escribe_la_seccion_de_la_vista(toy_vault):
    dest = sembrar(toy_vault)
    hv.harvest("test_star")
    body = dest.read_text(encoding="utf-8")
    assert "## Vista — Estrella Test" in body
    assert "reporta K = 2.5 m/s" in body and "34 d" in body and "412" in body
    assert "no separa actividad" in body


def test_un_json_que_NO_es_extraccion_se_rechaza(toy_vault):
    """INV-103, y la razón de que esta función exista: la salida de `verify-citations` también
    trae `bibcode` y es JSON válido. Aceptarla pisa notas terminadas **en silencio** — medido:
    13 notas. El rechazo se cuenta y se nombra.

    @inv INV-103"""
    dest = sembrar(toy_vault, {"bibcode": BIB, "resultados": [{"veredicto": "soportada"}]})
    antes = dest.read_text(encoding="utf-8")
    r = hv.harvest("test_star")
    assert r["rechazadas"] == 1 and r["cosechadas"] == 0
    assert dest.read_text(encoding="utf-8") == antes, "no se toca la nota"


def test_una_extraccion_sin_vista_se_rechaza(toy_vault):
    """Sin `vista` el cosechador no sabe de quién es la lectura, y adivinarla por el slug sería
    inventar la única metadata que #188 vino a agregar."""
    d = extraccion(); del d["vista"]
    sembrar(toy_vault, d)
    r = hv.harvest("test_star")
    assert r["rechazadas"] == 1 and r["cosechadas"] == 0


def test_sin_nota_destino_no_se_inventa(toy_vault):
    d = cfg.ROOT / "build" / "test_star" / "extraccion"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{BIB}.json").write_text(json.dumps(extraccion()), encoding="utf-8")
    r = hv.harvest("test_star")
    assert r["sin_nota"] == 1 and not (toy_vault.PAPERS / f"{BIB}.md").exists()


def test_la_cosecha_es_idempotente(toy_vault):
    """Red #6 del repo: correr dos veces y hashear. La segunda corrida no puede mover un byte."""
    dest = sembrar(toy_vault)
    hv.harvest("test_star")
    primero = dest.read_text(encoding="utf-8")
    hv.harvest("test_star")
    assert dest.read_text(encoding="utf-8") == primero


def test_no_pisa_una_vista_ya_escrita_salvo_force(toy_vault):
    """«Nunca se pisa la extracción LLM sin `--force` explícito» (invariante de la cadena). Una
    vista ya redactada —y posiblemente ya verificada, con sus anclas— no se reescribe porque el
    JSON siga en `build/`."""
    dest = sembrar(toy_vault, body="## Vista — Estrella Test\n\nProsa escrita a mano.\n")
    hv.harvest("test_star")
    assert "Prosa escrita a mano." in dest.read_text(encoding="utf-8")
    hv.harvest("test_star", force=True)
    assert "Prosa escrita a mano." not in dest.read_text(encoding="utf-8")


def test_la_vista_de_un_retro_tagueado_trae_su_txt_al_slug(toy_vault):
    """D-18 aplicado a la vista: el `.txt` del paper está bajo el slug del OTRO sujeto, así que
    `extraction_prompt <tema> <bib>` salía `⛔ no existe` y el remedio que sugería tampoco aplicaba
    (el PDF tampoco está ahí). Crear la vista trae la copia."""
    otro = toy_vault.FULLTEXT / "otra_estrella"
    otro.mkdir(parents=True, exist_ok=True)
    (otro / f"{BIB}.txt").write_text("texto del paper\n", encoding="utf-8")
    sembrar(toy_vault)
    hv.harvest("test_star")
    traido = toy_vault.FULLTEXT / "test_star" / f"{BIB}.txt"
    assert traido.exists() and traido.read_text(encoding="utf-8") == "texto del paper\n"


def test_la_cosecha_se_estampa_en_la_cadena(toy_vault, monkeypatch):
    """D-57: cada script se estampa a sí mismo, o el lint lee un paso corrido a mano como un corte."""
    sembrar(toy_vault)
    monkeypatch.setattr(sys, "argv", ["harvest_views.py", "test_star"])
    assert hv.main() == 0
    assert any(p["paso"] == "harvest_views" for p in cfg.load_cadena("test_star"))
