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


def test_upsert_view_no_se_come_el_cierre_del_frontmatter(toy_vault):
    """Regresión medida: `upsert_view` reconstruía la nota con `text[end + 1:]`, y ese `+1` se
    comía el `\\n` que separa la última clave del `---` de cierre. Resultado: `generator: v1.69.0---`
    en la misma línea, el YAML deja de parsear y **la nota entera desaparece de todos los chequeos
    por tipo** — que es justo el modo de falla que la categoría `fm_broken` del lint existe para
    reportar.

    Medido al cosechar un tema real: **24 de 202 notas** quedaron ilegibles, y encima en silencio,
    porque el cosechador informó «65 cosechadas».

    @inv INV-134"""
    # ⚠ El fixture por defecto tiene `vistas` como ÚLTIMA clave y por ahí el bug NO aparece: al
    # reemplazar el bloque final se append`ea uno que ya termina en `\n`. Se reproduce sólo cuando
    # hay claves DESPUÉS —que es el caso real, `write_web_paper_note` pone `confidence`, `tags` y
    # `generator` detrás—, porque ahí la última línea del frontmatter es la que pierde su salto.
    dest = sembrar(toy_vault, fm_extra={"confidence": "medium", "generator": "Almagesto v1.69.0"})
    hv.harvest("test_star")
    texto = dest.read_text(encoding="utf-8")
    assert "v1.69.0---" not in texto, "la última clave y el `---` no pueden quedar pegados"
    assert "\n---\n" in texto[4:], "el frontmatter tiene que seguir cerrando en su propia línea"
    fm = read_fm(dest)
    assert fm.get("bibcode") == BIB, "y tiene que seguir parseando entero, no sólo cerrar"
    assert fm["vistas"][0]["fecha"], "…con la vista estampada"


def test_render_view_no_fabrica_wikilinks_con_notacion_de_matriz(toy_vault):
    """Regresión medida: una extracción que trae una matriz —`C_U = [[r11, r12],[r12, r22]]`— se
    escribía tal cual, y markdown lee `[[...]]` como **wikilink**. Resultado: 14 wikilinks rotos
    (bloqueantes) fabricados por el cosechador sobre notas que nadie escribió a mano.

    El `[[bibcode]]` legítimo —una atribución de segunda mano dentro de la vista— tiene que
    sobrevivir: lo que se neutraliza es lo que NO parece un bibcode.

    @inv INV-134"""
    d = extraccion(aporte="Con C_U = [[r11, r12],[r12, r22]] la covarianza queda diagonal; "
                          "el método es de [[1994Comon]].")
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    cuerpo = dest.read_text(encoding="utf-8")
    assert "[[r11" not in cuerpo, "una matriz no puede quedar como wikilink"
    assert "[[1994Comon]]" in cuerpo, "…y la cita de segunda mano SÍ se conserva"


def test_la_columna_del_localizador_no_se_llama_linea(toy_vault):
    """#195 — la columna ya no lleva sólo un nº de línea del `.txt`: un valor levantado de una
    tabla-imagen se cita por PÁGINA y una lectura de gráfico por `Fig. N, p. M`. Llamarla «Línea»
    es la misma mentira de encabezado que #200 corrige en el bloque de verificación: el lector no
    puede distinguir un localizador honesto de una línea inventada."""
    md = hv.render_view("ICA", {"ground_truth": [
        {"que": "SNR del test", "valor": "≈ 12 dB", "linea": "Fig. 3, p. 7",
         "regimen": "lectura de gráfico"}]})
    assert "| Qué | Valor | Localizador | Régimen | Segunda mano |" in md
    assert "Línea" not in md
    assert "Fig. 3, p. 7" in md, "el localizador de figura tiene que llegar a la tabla"


# ── #207 · la vista declara DE QUÉ se construyó ─────────────────────────────────────────────────


def _con_pdf(toy_vault, bib=BIB):
    (toy_vault.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
    (toy_vault.PDFS / "test_star" / f"{bib}.pdf").write_bytes(b"%PDF-1.4\n")


def test_la_vista_estampa_la_fuente_declarada(toy_vault):
    """#207 — `fuente` dice si la vista salió del paper o de ocho líneas de abstract. Sin el campo
    las dos se leen igual, que es el falso limpio de D-34 aplicado a la lectura."""
    _con_pdf(toy_vault)
    dest = sembrar(toy_vault, extraccion(vista={"sujeto": "Estrella Test", "tipo": "star",
                                                "txt": "test_star", "fuente": "pdf"}))
    hv.harvest("test_star")
    assert read_fm(dest)["vistas"][0]["fuente"] == "pdf"


def test_declarar_pdf_sin_PDF_en_disco_rechaza_la_extraccion(toy_vault):
    """El cruce contra el disco: `fuente: pdf` sin PDF diría que se leyó el paper. Se rechaza el
    JSON entero en vez de corregirlo — adivinar cuál de las dos mitades miente es exactamente lo
    que este campo existe para evitar."""
    dest = sembrar(toy_vault, extraccion(vista={"sujeto": "Estrella Test", "tipo": "star",
                                                "txt": "test_star", "fuente": "pdf"}))
    n = hv.harvest("test_star")
    assert n["rechazadas"] == 1
    assert "fuente" not in (read_fm(dest)["vistas"][0] or {}), "estampó una lectura que no ocurrió"


def test_una_vista_solo_abstract_se_estampa_aunque_no_haya_PDF(toy_vault):
    """El caso que motiva el issue: sin PDF la vista igual vale —el abstract de ADS puede traer una
    existencia negada y un período— con tal de que **diga** de dónde salió."""
    dest = sembrar(toy_vault, extraccion(vista={"sujeto": "Estrella Test", "tipo": "star",
                                                "txt": "test_star", "fuente": "abstract"}))
    hv.harvest("test_star")
    assert read_fm(dest)["vistas"][0]["fuente"] == "abstract"


def test_fuente_fuera_del_vocabulario_rechaza(toy_vault):
    _con_pdf(toy_vault)
    sembrar(toy_vault, extraccion(vista={"sujeto": "Estrella Test", "tipo": "star",
                                         "txt": "test_star", "fuente": "pdftotext"}))
    assert hv.harvest("test_star")["rechazadas"] == 1


def test_pdf_on_disk_mira_el_ARCHIVO_no_el_frontmatter(toy_vault):
    """El cruce tiene que mirar disco: el campo `pdf` de la nota puede estar en drift —es lo que el
    WARN `pdf_issues` del lint reporta— y usarlo acá haría que un drift se leyera como «la vista
    miente»."""
    assert not hv.pdf_on_disk(BIB)
    _con_pdf(toy_vault)
    assert hv.pdf_on_disk(BIB)


# ── #124 · las ayudas de lectura: traducción y conclusiones ─────────────────────────────────────


def test_estampa_traduccion_y_conclusiones(toy_vault):
    """La **vista** es lenteada (qué aporta a ESE sujeto); las conclusiones son lo que el paper
    afirma **sin lente**, y por eso no son redundantes: son lo que hace barata una segunda vista
    cuando otro sujeto reclama el mismo paper (#188: 141 de 908 notas lo son)."""
    _con_pdf(toy_vault)
    dest = sembrar(toy_vault, extraccion(
        abstract_es="Medimos el período de rotación.",
        conclusiones="We measure P_rot = 34 d.",
        conclusiones_es="Medimos P_rot = 34 d."))
    hv.harvest("test_star")
    texto = dest.read_text(encoding="utf-8")
    assert "## Abstract (es)\nMedimos el período de rotación." in texto
    assert "## Conclusiones\nWe measure P_rot = 34 d." in texto
    assert "## Conclusiones (es)\nMedimos P_rot = 34 d." in texto


def test_las_ayudas_de_lectura_van_ANTES_de_la_vista(toy_vault):
    """Orden de lectura: el resumen del paper arriba, la vista después. Al final quedaría detrás del
    bloque de verificación, que es donde nadie lo lee."""
    _con_pdf(toy_vault)
    dest = sembrar(toy_vault, extraccion(conclusiones="C."))
    hv.harvest("test_star")
    texto = dest.read_text(encoding="utf-8")
    assert texto.index("## Conclusiones") < texto.index("## Vista — Estrella Test")


def test_un_documento_largo_no_recibe_conclusiones(toy_vault):
    """Una fuente `unidad_cita: pagina` —un libro, un handbook— no tiene «conclusiones» como
    sección, y transcribir algo que no existe fabricaría contenido. Exclusión estructural, no un
    umbral de largo (que sería un corte sin calibrar)."""
    _con_pdf(toy_vault)
    dest = sembrar(toy_vault, extraccion(conclusiones="No debería entrar.",
                                         abstract_es="Esto sí."),
                   fm_extra={"unidad_cita": "pagina", "alcance": "caps. 6 y 15"})
    hv.harvest("test_star")
    texto = dest.read_text(encoding="utf-8")
    assert "## Conclusiones" not in texto
    assert "## Abstract (es)\nEsto sí." in texto, "la traducción del abstract sí, que es corta"


def test_las_ayudas_de_lectura_son_idempotentes(toy_vault):
    """Regla del framework: corré dos veces y el contenido no cambia."""
    _con_pdf(toy_vault)
    dest = sembrar(toy_vault, extraccion(conclusiones="C.", abstract_es="A."))
    hv.harvest("test_star")
    antes = dest.read_text(encoding="utf-8")
    hv.harvest("test_star")
    assert dest.read_text(encoding="utf-8") == antes


def test_sin_traduccion_no_se_crea_una_seccion_vacia(toy_vault):
    """Ausente = no consta. Un `## Conclusiones` en blanco se leería como «el paper no concluye
    nada», que no es lo mismo que «nadie las transcribió»."""
    _con_pdf(toy_vault)
    dest = sembrar(toy_vault)
    hv.harvest("test_star")
    texto = dest.read_text(encoding="utf-8")
    assert "## Abstract (es)" not in texto and "## Conclusiones" not in texto


def test_las_ayudas_de_lectura_estan_exentas_del_fan_out(toy_vault):
    """⛔ Son ayuda de lectura, nunca fuente de la que citar: `verify-citations` no las mira, porque
    una traducción no es una afirmación de la bóveda. La red está aguas abajo — lo que de acá llegue
    a una ficha sí se verifica contra el PDF."""
    for h in ("## Abstract", "## Abstract (es)", "## Conclusiones", "## Conclusiones (es)"):
        assert any(h.startswith(e) for e in cfg.SECCIONES_ESTAMPADAS), h
