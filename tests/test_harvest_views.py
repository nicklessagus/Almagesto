"""#188 paso 5 / #191 — el cosechador del fan-out de extracción.

Hasta 1.68.0 **no existía**: cada subagente escribía su JSON en el directorio de extracciones y
**nadie lo leía**. El cosechado era manual, y por eso `is_extraction` (INV-103, P0) —la función
que distingue una extracción de cualquier otro JSON con `bibcode`— no tenía un solo llamador de
producción. El defecto que la motivó está medido: un cosechador escrito a mano que aceptaba
cualquier JSON con `bibcode` levantó 13 salidas de `verify-citations` de OTRA estrella y pisó 13
notas terminadas, con JSON perfectamente válido — o sea en silencio.
"""
from __future__ import annotations

import datetime as _dt
import json
from types import SimpleNamespace
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import harvest_views as hv
import lib_config as cfg
import make_notes as mn
from conftest import mk_note, read_fm, write_yaml


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
    """Un JSON de extracción en `vault/raw/extraccion/<slug>/` + la nota stub (#311)."""
    d = cfg.EXTRACCION / "test_star"
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


def test_upsert_section_REHUSA_si_la_seccion_traga_algo_ajeno(toy_vault, capsys):
    """#379 — `upsert_section` reemplazaba de `ini` a `fin` **sin mirar qué descarta**. Cuando la
    sección `## Abstract` contiene algo que no es abstract —porque un backfill anterior la insertó
    en el lugar equivocado y la cabecera quedó adentro (#378)— ese contenido se va con el reemplazo:
    6 de 169 notas perdieron su cabecera en UNA corrida, sin aviso, con el lint en exit 0.

    El guard que sí existía cuida el verbatim ya puesto, y está bien; lo que no cuidaba es lo AJENO
    que la sección haya tragado, que es otro eje. La doctrina ya estaba escrita dos veces en el
    repo —#244 (se re-parsea y no se escribe si dejó de parsear) y #284 (`render_verif_table`
    rehúsa un bloque cuya lectura no reproduce lo que se le escribió)— y ninguna cubría el CUERPO."""
    dest = cfg.PAPERS / f"{BIB}.md"
    mk_note(cfg.PAPERS, BIB, {"tags": ["paper"], "bibcode": BIB},
            "# Paper\n\n## Abstract\n_(no disponible)_\n\n**Autor** (2020)\n"
            "· fuente off-ADS · `" + BIB + "`\n\n## Vista — Estrella Test\n\n_(pendiente)_\n")
    antes = dest.read_text(encoding="utf-8")
    assert hv.upsert_section(dest, "## Abstract", "## Abstract\nel verbatim del catálogo\n") is False
    out = capsys.readouterr().out
    assert "cabecera" in out and BIB in out
    assert dest.read_text(encoding="utf-8") == antes, "no se escribe: se grita con el archivo"


def test_upsert_section_reemplaza_normal_cuando_no_hay_nada_ajeno(toy_vault):
    """El control: el caso normal sigue funcionando, o la guarda rompería el cosechador entero."""
    dest = cfg.PAPERS / f"{BIB}.md"
    mk_note(cfg.PAPERS, BIB, {"tags": ["paper"], "bibcode": BIB},
            "# Paper\n\n**Autor** (2020)\n· fuente off-ADS · `" + BIB + "`\n\n"
            "## Abstract\n_(no disponible)_\n\n## Vista — Estrella Test\n\n_(pendiente)_\n")
    assert hv.upsert_section(dest, "## Abstract", "## Abstract\nel verbatim del catálogo\n") is True
    t = dest.read_text(encoding="utf-8")
    assert "el verbatim del catálogo" in t and "· fuente off-ADS" in t


def test_el_cosechador_AVISA_si_el_txt_contradice_una_cita_de_la_extraccion(toy_vault, capsys):
    """#359 — el cruce contra el `.txt` corría sobre la NOTA, así que una cita mal transcrita **al
    leer el PDF** pasaba por el cosechador sin que nada la mirara y sólo se cazaba si llegaba a una
    ficha. Medido en una ingesta real: 2 de 265 valores, las dos nacidas en la extracción.

    Importa por dónde se caza: una extracción **no se regenera** (#311) y alimenta a N sujetos, así
    que verla en el origen es verla una vez en lugar de una vez por nota."""
    d = extraccion(ground_truth=[{"que": "velocidad", "linea": "412", "regimen": "", "segunda_mano": None,
                                  "valor": "«Speed is, however, a crucial factor because we have to "
                                           "run the ICA algorithm many times and again»"}])
    sembrar(toy_vault, d)
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "test_star" / f"{BIB}.txt").write_text(
        "Speed is, however, a crucial factor because we have to run the ICA algorithm many times "
        "which is why FastICA is very suitable for this purpose.", encoding="utf-8")
    r = hv.harvest("test_star")
    out = capsys.readouterr().out
    assert "el `.txt`" in out and BIB in out
    # ⛔ AVISA y no rechaza: el `.txt` es índice degradado (#205), así que rechazar produciría
    # falsos negativos sobre extracciones correctas. Misma asimetría que #213.
    assert r["rechazadas"] == 0 and r["cosechadas"] == 1


def test_el_aviso_del_txt_vuelve_a_salir_en_una_boveda_YA_COSECHADA(toy_vault, capsys):
    """El caso que reportó quien migró la instancia: sobre una bóveda toda cosechada el aviso de
    #359 no se veía. Si el aviso dependiera de que la nota cambie, el chequeo serviría **una sola
    vez** —en la corrida que estampa la vista— y sería inútil justo donde importa: la extracción ya
    está en disco y sigue alimentando a N sujetos."""
    d = extraccion(ground_truth=[{"que": "velocidad", "linea": "412", "regimen": "", "segunda_mano": None,
                                  "valor": "«Speed is, however, a crucial factor because we have to "
                                           "run the ICA algorithm many times and again»"}])
    sembrar(toy_vault, d)
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "test_star" / f"{BIB}.txt").write_text(
        "Speed is, however, a crucial factor because we have to run the ICA algorithm many times "
        "which is why FastICA is very suitable for this purpose.", encoding="utf-8")
    hv.harvest("test_star")
    capsys.readouterr()
    r = hv.harvest("test_star")                      # segunda corrida: nada que estampar
    out = capsys.readouterr().out
    assert "sin cambios" in out, "el escenario es una bóveda ya cosechada"
    assert "el `.txt`" in out, "el aviso NO puede depender de que la nota cambie"


def test_el_aviso_del_txt_sale_AUNQUE_la_vista_se_RECHACE(toy_vault, capsys):
    """El caso real que reportó quien migró la instancia, y que el test de «sin cambios» no cubría.

    Sus 187 extracciones tienen `vista.fecha` vacía, así que el cosechador propone la de hoy, la
    vista ya estampada dice otra, `upsert_view` **rehúsa** cambiar un valor escrito (#239) y el
    `continue` del rechazo corre **antes** del cruce. Consecuencia medida: en una bóveda así,
    re-correr el cosechador no muestra #359 sobre lo ya cosechado **nunca**.

    El cruce no depende de la nota —compara la EXTRACCIÓN con su `.txt`—, así que va antes de tocar
    la nota. Su población es «toda extracción admisible», no «toda nota que cambió»."""
    v = {"sujeto": "Estrella Test", "tipo": "star", "txt": "test_star", "fuente": "abstract"}
    d = extraccion(vista=dict(v), ground_truth=[
        {"que": "velocidad", "linea": "412", "regimen": "", "segunda_mano": None,
         "valor": "«Speed is, however, a crucial factor because we have to run the ICA algorithm "
                  "many times and again»"}])
    sembrar(toy_vault, d)
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "test_star" / f"{BIB}.txt").write_text(
        "Speed is, however, a crucial factor because we have to run the ICA algorithm many times "
        "which is why FastICA is very suitable for this purpose.", encoding="utf-8")
    hv.harvest("test_star")                          # primera: estampa la vista con la fecha de hoy
    capsys.readouterr()
    # y ahora la vista queda declarando OTRA fecha, así que la segunda corrida la rechaza
    mn.merge_frontmatter_list  # noqa: B018 — sólo para dejar claro de dónde sale el frontmatter
    dest = cfg.PAPERS / f"{BIB}.md"
    dest.write_text(dest.read_text(encoding="utf-8").replace(_dt.date.today().isoformat(),
                                                             "2020-01-01"), encoding="utf-8")
    hv.harvest("test_star")
    out = capsys.readouterr().out
    assert "RECHAZADAS" in out, "el escenario es el rechazo, no el «sin cambios»"
    assert "el `.txt`" in out, "el cruce no puede depender de que la vista se pueda declarar"


def test_el_SILENCIO_del_txt_sobre_una_cita_no_avisa(toy_vault, capsys):
    """El recorte que lo hace usable: si el `.txt` no tiene la cadena, es *no evaluable* (#321) — la
    extracción es selectiva y se cita del PDF. Sin esto el aviso saldría sobre el 36 % de los
    valores de una bóveda real, y un reporte donde casi nada es accionable se deja de mirar."""
    d = extraccion(ground_truth=[{"que": "x", "linea": "1", "regimen": "", "segunda_mano": None,
                                  "valor": "«una frase larga que el `.txt` no contiene en absoluto»"}])
    sembrar(toy_vault, d)
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "test_star" / f"{BIB}.txt").write_text("prosa distinta del paper.", encoding="utf-8")
    hv.harvest("test_star")
    assert "el `.txt`" not in capsys.readouterr().out


def test_la_lente_de_la_vista_sale_de_LO_QUE_LA_LECTURA_PREGUNTO(toy_vault):
    """#372 — la lente se tomaba del TEMA, una sola vez antes del bucle, así que toda vista
    declaraba los ejes del tema sin mirar cuáles contestó esa lectura. Con `--enfasis --ejes`
    (#308) el resultado es una vista que dice haber cubierto ejes **que nunca se le preguntaron**:
    medido, 13 de 13 vistas de segunda lente, con solapamiento **0 de 7**.

    Rompe INV-146 en su enunciado literal —«toda vista declara los ejes vigentes AL LEERLA»—, así
    que el diff de D-49 describe otra lectura y el detector de ejes sin contestar (#254/#270) pasa
    de medir cobertura a inventarla."""
    propios = {"como_se_estima": "por remuestreo", "cuantas_se_piden": "por criterio de orden"}
    sembrar(toy_vault, extraccion(ejes=propios,
                                  vista={"sujeto": "Estrella Test", "tipo": "star",
                                         "txt": "test_star", "fuente": "abstract",
                                         "enfasis": "orden"}))
    hv.harvest("test_star")
    vistas = read_fm(cfg.PAPERS / f"{BIB}.md")["vistas"]
    v = [x for x in vistas if x.get("enfasis") == "orden"][0]
    assert list(v["lente"]) == list(propios), v["lente"]


def test_sin_enfasis_la_lente_declarada_del_sujeto_es_la_que_MANDA(toy_vault):
    """El recorte, y no es cosmético: en una lectura NORMAL las claves del JSON son lo **contestado**
    —el extractor puede dejar afuera las que no aplican— así que tomarlas como lente encogería el
    denominador del detector de ejes sin contestar (#254/#270), que pasaría de medir cobertura a no
    poder medirla. El discriminante es `enfasis`, la marca declarada de que se pidió otra lente."""
    sembrar(toy_vault, extraccion(ejes={"rv": "reporta K"}))
    hv.harvest("test_star")
    v = read_fm(cfg.PAPERS / f"{BIB}.md")["vistas"][0]
    assert v["lente"] == list(mn.objective_lens()[0])


def test_dos_archivos_con_el_mismo_par_sujeto_lente_se_AVISAN(toy_vault, capsys):
    """#371, la red simétrica del nombre de archivo: la identidad de una vista es el par
    `(sujeto, enfasis)`, así que dos JSON que declaran el mismo par son dos lecturas compitiendo por
    la misma sub-sección — y el cosechador escribiría una y después la otra sin decir nada.

    ⚠ Avisa, no rechaza: las dos extracciones son artefactos caros (#311) y cuál gana es una
    decisión de quien las produjo, no del cosechador."""
    v = {"sujeto": "Estrella Test", "tipo": "star", "txt": "test_star", "fuente": "abstract",
         "enfasis": "ruido"}
    sembrar(toy_vault, extraccion(vista=v))                      # `<bib>.json`
    (cfg.EXTRACCION / "test_star" / f"{BIB}__ruido.json").write_text(
        json.dumps(extraccion(vista=dict(v))), encoding="utf-8")  # el MISMO par, otro archivo
    hv.harvest("test_star")
    out = capsys.readouterr().out
    assert "mismo par" in out, out
    assert BIB in out and "lente «ruido»" in out
    # y NO rechaza: las dos entran, que es la asimetría deliberada
    assert "RECHAZADAS" not in out


def test_cosecha_estampa_la_vista_con_fecha_txt_y_lente(toy_vault):
    """La vista pasa de DECLARADA a HECHA: la `fecha` es lo que dice que la lectura ocurrió, el
    `txt` de qué copia salió (el ancla de fuente, D-18) y la `lente` con qué facetas se leyó — el
    diff de lente (D-49) a nivel de lectura.

    @inv INV-134"""
    dest = sembrar(toy_vault)
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "test_star" / f"{BIB}.txt").write_text("texto", encoding="utf-8")
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


def test_el_SLUG_del_sujeto_no_se_publica_como_metodo(toy_vault, capsys):
    """#404 — el prompt nombra el sujeto por su slug y el extractor lo devuelve dentro de `methods`
    (19 de 206 extracciones, en cuatro temas). `methods` es «cómo lo nombra el PAPER» —por eso se
    normaliza al comparar y nunca al escribir (#243)— y ningún paper escribe `harps-drs`. Publicado,
    el lint reportaba «el mismo método con 2 grafías» y proponía unificar la grafía, que CONTRADICE
    #243: el operador quedaba eligiendo entre dos reglas del framework.

    El filtro vive en la única compuerta que ESCRIBE la nota; el JSON no se toca (#311).

    ⚠ Y filtra SÓLO el slug del sujeto, no los stems de `concepts/` que el issue también sugería:
    `methods: [PCA]` con `concepts/methods/pca.md` en disco es el roll-up funcionando (#245), no un
    defecto — filtrarlo desconectaría en silencio a todo paper de todo método que nombra.

    ⚠ Y sólo el slug LITERAL (#410): `TEST_STAR` sobrevive. Es el recorte declarado — la variante de
    caja de un slug de estrella no está en la población medida, y perseguirla cuesta la grafía del
    paper en todo tema cuyo slug es el nombre del método, que sí lo está (24 contra 19)."""
    (cfg.CONCEPTS / "methods").mkdir(parents=True, exist_ok=True)
    (cfg.CONCEPTS / "methods" / "pca.md").write_text("---\ntags: [concept]\n---\n# PCA\n",
                                                     encoding="utf-8")
    dest = sembrar(toy_vault, extraccion(methods=["periodograma", "test_star", "TEST_STAR", "PCA"]))
    hv.harvest("test_star")
    fm = read_fm(dest)
    assert fm["methods"] == ["periodograma", "TEST_STAR", "PCA"], fm["methods"]
    out = capsys.readouterr().out
    assert "es el SLUG del sujeto" in out and "1 slug(s) filtrados" in out
    assert "test_star" in out, "se NOMBRA lo que se filtró: no se cura en silencio"
    # el JSON versionado queda tal cual (#311): el filtro es del cosechador, no de la extracción
    import json as _json
    guardado = _json.loads(next((cfg.EXTRACCION / "test_star").glob("*.json")).read_text(encoding="utf-8"))
    assert "test_star" in guardado["methods"]


def test_split_subject_slugs_compara_por_string_LITERAL_no_por_clave(toy_vault):
    """#404 arreglado por #410. El identificador de la bóveda que el extractor devolvió es el string
    LITERAL; comparar por `method_key` aplica la regla al revés en todo tema cuyo slug ES el nombre
    del método —`method_key('ICA') == method_key('ica')`— y descarta la grafía del paper, que es lo
    que #243 declara información. Medido en la bóveda real: 24 falsos contra 19 verdaderos."""
    metodos, slugs = hv.split_subject_slugs(["GLS", "ica", "ICA", "SysRem"], "ica")
    assert slugs == ["ica"], "sólo el slug literal"
    assert metodos == ["GLS", "ICA", "SysRem"], "`ICA` es cómo el paper nombra el método"
    assert hv.split_subject_slugs([], "ica") == ([], [])


def test_split_subject_slugs_no_descarta_la_grafia_DEL_PAPER(toy_vault):
    """Los tres casos medidos en `Almagesto-Tesis` (#410), incluido `HARPS DRS` en el tema que
    originó #404: el fix viejo tiraba justamente el caso que decía resolver."""
    assert hv.split_subject_slugs(["ICASSO", "Icasso", "centrotipo"], "icasso") == (
        ["ICASSO", "Icasso", "centrotipo"], [])
    assert hv.split_subject_slugs(["harps-drs", "HARPS DRS", "CCF"], "harps-drs") == (
        ["HARPS DRS", "CCF"], ["harps-drs"])


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

    ⚠ El JSON sembrado trae **`vista` válida y PDF en disco**, a propósito: sin eso lo rechazaba la
    guarda *siguiente* y el test no distinguía cuál actuó. Medido el 2026-08-28 (frente F de la
    pasada `/auditar`): con `is_extraction` neutralizada, el archivo entero seguía en verde.
    Ahora el único motivo posible de rechazo es INV-103, que es lo que este test acredita.

    @inv INV-103"""
    (toy_vault.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
    (toy_vault.PDFS / "test_star" / f"{BIB}.pdf").write_bytes(b"%PDF-1.4\n")
    dest = sembrar(toy_vault, {
        "bibcode": BIB,
        "vista": {"sujeto": "Estrella Test", "tipo": "star", "txt": "test_star", "fuente": "pdf"},
        "resultados": [{"veredicto": "soportada", "ancla": "ab12cd34ef"}]})   # salida de verify
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
    d = cfg.EXTRACCION / "test_star"
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


def test_481_upsert_view_escribe_la_fecha_como_STR_y_normaliza_la_que_estaba(toy_vault):
    """#481 — el escritor del bloque `vistas:` fuerza str en `fecha`: la que YAML leyó como `date`
    se re-serializa con comillas en el primer upsert, y una entrada sin fecha (sin choque) alcanza."""
    import yaml
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    f = cfg.PAPERS / "2020fecha..1..1F.md"
    f.write_text("---\nbibcode: 2020fecha..1..1F\ntags: [paper]\nvistas:\n"
                 "- sujeto: Estrella Test\n  tipo: star\n  fecha: 2026-08-30\n---\n\n# p\n",
                 encoding="utf-8")
    assert not isinstance(yaml.safe_load(f.read_text()[4:].split("\n---\n")[0])["vistas"][0]["fecha"], str)
    assert hv.upsert_view(f, {"sujeto": "Estrella Test", "tipo": "star"}) is True
    raw = yaml.safe_load(f.read_text()[4:].split("\n---\n")[0])["vistas"][0]
    assert raw["fecha"] == "2026-08-30" and isinstance(raw["fecha"], str)
    assert "'2026-08-30'" in f.read_text(), "con comillas en el disco"
    assert hv.upsert_view(f, {"sujeto": "Estrella Test", "tipo": "star"}) is False, "idempotente"


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
    #  @inv INV-138
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
    assert "## Traducción del abstract\nMedimos el período de rotación." in texto
    assert "## Conclusiones\nWe measure P_rot = 34 d." in texto
    assert "## Traducción de las conclusiones\nMedimos P_rot = 34 d." in texto


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
    assert "## Traducción del abstract\nEsto sí." in texto, "la traducción del abstract sí, que es corta"


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
    assert "## Traducción" not in texto and "## Conclusiones" not in texto


def test_las_ayudas_de_lectura_estan_exentas_del_fan_out(toy_vault):
    """⛔ Son ayuda de lectura, nunca fuente de la que citar: `verify-citations` no las mira, porque
    una traducción no es una afirmación de la bóveda. La red está aguas abajo — lo que de acá llegue
    a una ficha sí se verifica contra el PDF."""
    for h in ("## Abstract", "## Traducción del abstract", "## Conclusiones",
              "## Traducción de las conclusiones"):
        assert any(h.startswith(e) for e in cfg.SECCIONES_ESTAMPADAS), h


def test_el_abstract_verbatim_se_estampa_SOLO_si_la_nota_no_lo_tiene(toy_vault):
    """El `## Abstract` del catálogo es copia de máquina —la capa auditable del cuerpo— y no se pisa
    con una transcripción del modelo. Pero una nota off-ADS creada antes de #124 **no tiene la
    sección en absoluto** (medido: 32 de 201 en una bóveda real) y sin esto no la recibiría nunca:
    `write_web_paper_note` sólo la escribe al crear. El extractor ya abrió el PDF, así que el texto
    está a mano y no hace falta red."""
    _con_pdf(toy_vault)
    dest = sembrar(toy_vault, extraccion(abstract="Transcrito del PDF."))
    hv.harvest("test_star")
    assert "Transcrito del PDF." in dest.read_text(encoding="utf-8")


def test_no_pisa_el_abstract_del_catalogo(toy_vault):
    _con_pdf(toy_vault)
    dest = sembrar(toy_vault, extraccion(abstract="Transcripción del modelo."),
                   body="## Abstract\nVerbatim de ADS.\n\n" + mn.vista_block("Estrella Test", theme=False))
    hv.harvest("test_star")
    texto = dest.read_text(encoding="utf-8")
    assert "Verbatim de ADS." in texto
    assert "Transcripción del modelo." not in texto, "pisó la capa auditable"


def test_el_abstract_se_rellena_tambien_sobre_el_placeholder(toy_vault):
    """El abstract tiene DOS fuentes: **ADS** o **el PDF** (decidido con el usuario, 2026-08-28).
    Cuando ADS no lo devuelve, `make_notes` deja `_(no disponible)_` — y si el guard sólo mirara la
    ausencia de la sección, ese placeholder sería **permanente**: vería el `## Abstract`, lo daría
    por lleno y no lo tocaría nunca."""
    _con_pdf(toy_vault)
    dest = sembrar(toy_vault, extraccion(abstract="Del PDF."),
                   body="## Abstract\n_(no disponible)_\n\n" + mn.vista_block("Estrella Test", theme=False))
    hv.harvest("test_star")
    texto = dest.read_text(encoding="utf-8")
    assert "Del PDF." in texto
    assert "_(no disponible)_" not in texto


def test_la_traduccion_no_es_prefijo_del_original(toy_vault):
    """#176 instanciado en el vocabulario propio: `## Abstract (es)` hacía de `## Abstract` un
    prefijo del suyo, y `section_start` tolera un sufijo que arranca con puntuación (lo necesita
    para `## Vista — X (2026-08-27)`). Con sólo la traducción presente, el guard del verbatim la
    daba por el original y **no lo estampaba nunca** — dejando el insumo del diff de lente offline
    sin abstract para siempre."""
    _con_pdf(toy_vault)
    dest = sembrar(toy_vault, extraccion(abstract_es="Resumen traducido."))
    hv.harvest("test_star")                       # sólo la traducción
    assert "## Traducción del abstract" in dest.read_text(encoding="utf-8")

    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(
        json.dumps(extraccion(abstract="The verbatim abstract.", abstract_es="Resumen traducido.")),
        encoding="utf-8")
    hv.harvest("test_star")                       # ahora sí el verbatim
    texto = dest.read_text(encoding="utf-8")
    assert "The verbatim abstract." in texto, "el verbatim quedó tapado por su traducción"
    assert cfg.section_start(texto, "## Abstract") != cfg.section_start(texto, "## Traducción del abstract")


def test_frontmatter_roto_no_deja_una_vista_a_medias(toy_vault, capsys):
    """AUD-200 / INV-139 — si la vista no se puede DECLARAR, la sección del cuerpo tampoco se escribe.

    `upsert_view` devolvía `False` pelado para tres estados de *no pude* (sin frontmatter, sin
    cerrar, YAML roto) y el llamador los contaba como «sin cambios»… pero seguía adelante y
    escribía `## Vista — X`. Resultado: la nota queda con la sección y sin la entrada en `vistas[]`,
    que es exactamente la incoherencia que el lint bloquea — un fallo visible cambiado por uno que
    hay que descubrir."""
    dest = sembrar(toy_vault)
    dest.write_text("---\nbibcode: " + BIB + "\ntags: [paper\n---\ncuerpo\n", encoding="utf-8")
    antes = dest.read_text(encoding="utf-8")

    r = hv.harvest("test_star")

    assert r["rechazadas"] == 1 and r["cosechadas"] == 0
    assert dest.read_text(encoding="utf-8") == antes        # nada a medias
    assert "no se pudo declarar la vista" in capsys.readouterr().out


def test_prosa_redactada_no_se_pisa_pero_se_dice(toy_vault, capsys):
    """AUD-200 — la negativa de `write_view_section` se contaba como «sin cambios».

    Que no se pise prosa verificada es correcto (sus anclas cuelgan del texto exacto); lo que no
    puede pasar es que la cosecha se lea como completa cuando la vista nueva NO quedó escrita."""
    dest = sembrar(toy_vault, body="## Vista — Estrella Test\n\nprosa ya redactada a mano.\n")
    hv.harvest("test_star")
    salida = capsys.readouterr().out
    assert "ya tiene prosa redactada" in salida and "--force" in salida
    assert "prosa ya redactada a mano" in dest.read_text(encoding="utf-8")


def test_la_vista_escrita_deja_linea_en_blanco_antes_de_la_seccion_siguiente(toy_vault):
    """#260 — `section_span` devuelve el fin **en** el `## ` siguiente, así que el splice se comía
    la línea en blanco y el encabezado quedaba pegado al último párrafo de la vista.

    Es el mismo defecto que `_reemplazar_seccion` (los roll-ups de la ficha) por el otro camino de
    escritura. Acá el daño es menor —una vista termina en prosa, no en tabla, y un `##` pegado a un
    párrafo sí se parsea como encabezado— pero el arreglo es el mismo y no tener los dos sitios
    iguales es cómo la comprensión se pierde en el siguiente call site (cf. #222, #214, INV-98).
    """
    dest = sembrar(toy_vault, body=mn.vista_block("Estrella Test", False)
                   + "\n## Verificación de citas (2020-01-01)\n\ntabla\n")
    hv.harvest("test_star")
    texto = dest.read_text(encoding="utf-8")
    assert "\n\n## Verificación de citas" in texto, \
        "el encabezado siguiente quedó pegado al final de la vista"


def test_el_abstract_transcrito_dice_que_lo_transcribio_el_modelo(toy_vault):
    """AUD-203 / INV-110 — el abstract que llega por acá lo **transcribió el modelo del PDF**, no es
    la copia de catálogo, y el contrato hace descansar en esa distinción que `## Abstract` sea la
    capa **auditable** del cuerpo.

    Sin decirlo las dos se leen igual. Y el frontmatter sigue declarando `sin_abstract: true` —que
    es historia y no se toca: describe con qué se **clasificó** el paper— así que la nota se
    contradecía a sí misma a la vista."""
    dest = sembrar(toy_vault, extraccion(abstract="Texto del abstract, transcrito."),
                   fm_extra={"sin_abstract": True},
                   body="## Abstract\n_(no disponible)_\n\n" + mn.vista_block("Estrella Test", False))
    hv.harvest("test_star")
    texto = dest.read_text(encoding="utf-8")
    assert "Texto del abstract, transcrito." in texto
    assert "transcrito del PDF por la extracción" in texto
    assert read_fm(dest)["sin_abstract"] is True, "el flag es historia de la CLASIFICACIÓN"


# ── #212 · la lectura puede REFUTAR el reclamo que la trajo ──────────────────

def test_refuta_queda_registrado_en_la_vista(toy_vault):
    """#212 — el reclamo sembrado era infalsificable por la lectura: `stars`/`thesis_links` se
    siembran ANTES de leer y el merge es add-only (bien: protege la extracción de que un re-seed la
    pise). #188 daba dos salidas para un reclamo SIN vista —hacerla, o declarar `no_vista`— y
    ninguna para el tercer caso: hice la vista y el reclamo es FALSO."""
    d = extraccion()
    d["refuta"] = ["ica"]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    assert read_fm(dest)["vistas"][0]["refuta"] == ["ica"]


def test_refuta_NO_borra_el_reclamo_y_propone_el_comando(toy_vault, capsys):
    """#212 — se REGISTRA, no se aplica. Borrar el reclamo sería un LLM editando curación en
    silencio, y además la decisión es del par (paper, sujeto): el paper puede ser core de OTRO.
    Mismo patrón que `triage --accept-source`: arma la decisión, no la toma."""
    d = extraccion()
    d["refuta"] = ["ica"]
    dest = sembrar(toy_vault, d, fm_extra={"thesis_links": ["ica"]})
    hv.harvest("test_star")
    assert read_fm(dest)["thesis_links"] == ["ica"], "add-only: el guard NO se afloja"
    out = capsys.readouterr().out
    assert "REFUTAN el reclamo" in out
    assert "--drop-core" in out and "--reason" in out


def test_sin_refuta_no_pasa_nada(toy_vault, capsys):
    """#212 — el caso normal (lista vacía o ausente) no agrega campo ni ruido."""
    dest = sembrar(toy_vault)
    hv.harvest("test_star")
    assert "refuta" not in read_fm(dest)["vistas"][0]
    assert "REFUTAN el reclamo" not in capsys.readouterr().out


# ── #213 · las salvedades: chequeo mecánico + marca de no verificada ─────────

def _con_txt(toy_vault, contenido, stem=BIB):
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "test_star" / f"{stem}.txt").write_text(contenido, encoding="utf-8")


def test_salvedad_estructurada_verdadera_se_publica_verificada(toy_vault):
    """#213 — «el `.txt` perdió esta cadena» es un `grep`, no un juicio: se chequea con un script y
    la nota dice CÓMO se verificó, no sólo que alguien lo dijo."""
    _con_txt(toy_vault, "el texto sin el simbolo raro")
    d = extraccion()
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ_{×+×}"}]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    body = dest.read_text(encoding="utf-8")
    assert "Salvedades (verificadas contra el archivo)" in body
    assert "⚙ verificada" in body and "ζ_{×+×}" in body


def test_salvedad_estructurada_FALSA_no_se_publica_y_se_grita(toy_vault, capsys):
    """#213, el caso medido — el extractor afirmó una degradación del `.txt` que NO existía,
    invocando #205 para darse autoridad, y lo cazó un duplicado ACCIDENTAL de la extracción. La
    afirmación iba a entrar bajo `**Salvedades:**`, que es justo la sección que el consumidor lee
    para saber cuánto confiar."""
    _con_txt(toy_vault, "la fuente dice ζ_{×+×} y el .txt también")
    d = extraccion()
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ_{×+×}"}]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    assert "ζ_{×+×}" not in dest.read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "salvedad FALSA" in out and "la salvedad es FALSA" in out


def test_salvedad_falsa_no_tira_la_extraccion(toy_vault):
    """#213 — NO se rechaza la extracción entera (a diferencia de `fuente: pdf` sin PDF, #207):
    aquello es una contradicción sobre QUÉ se abrió y esto un campo secundario que se descarta sin
    tirar la lectura, que es la mitad más cara de la cadena."""
    _con_txt(toy_vault, "contiene ζ_{×+×}")
    d = extraccion()
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ_{×+×}"}]
    dest = sembrar(toy_vault, d)
    n = hv.harvest("test_star")
    assert n["rechazadas"] == 0 and n["cosechadas"] == 1
    assert "## Vista — Estrella Test" in dest.read_text(encoding="utf-8")


def test_salvedad_en_prosa_se_marca_NO_VERIFICADA(toy_vault):
    """#213, la otra mitad — lo que no es decidible por un script se publica marcado, en su propio
    bloque. Publicarlo al mismo nivel visual que una fila chequeada es lo que dejó leer un defecto
    fabricado como un hecho medido."""
    d = extraccion()
    d["salvedades"] = ["la Fig. 3 es difícil de leer"]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    body = dest.read_text(encoding="utf-8")
    assert "NO VERIFICADAS — juicio del extractor" in body
    assert "la Fig. 3 es difícil de leer" in body


def test_salvedad_no_evaluable_no_es_verificada_ni_falsa(toy_vault, capsys):
    """#213 / D-43 — sin `.txt` en disco el chequeo NO CORRIÓ, y eso no es «se verificó» ni «es
    falsa». Se publica como prosa marcada, diciendo por qué no se pudo evaluar."""
    d = extraccion()
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "√"}]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    body = dest.read_text(encoding="utf-8")
    assert "no evaluable" in body and "NO VERIFICADAS" in body
    assert "salvedad FALSA" not in capsys.readouterr().out


def test_452_pdf_leido_se_chequea_contra_LOS_TRES_TESTIGOS(toy_vault):
    """⛔ #452 — la salvedad más decidible que escribe el extractor («el PDF en disco es el
    preprint») era la única que quedaba en PROSA, y sobre prosa el detector de #449 tiene que
    ADIVINAR de quién habla la oración: midió 5 hallazgos con precisión 0/5 sobre 268 notas.
    Estructurada la deciden los tres testigos de `doc_on_disk`, en su precedencia."""
    _con_txt(toy_vault, "arXiv:2001.00001v2 [astro-ph.EP] 1 Jan 2020\nel cuerpo del paper\n")
    d = extraccion()
    d["salvedades"] = [{"tipo": "pdf_leido", "documento": "eprint"}]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    body = dest.read_text(encoding="utf-8")
    assert "⚙ verificada" in body and "preprint" in body, \
        "la marca de arXiv en el `.txt` es verdad del artefacto y manda (#57)"


def test_452_pdf_leido_FALSA_no_se_publica_y_se_grita(toy_vault, capsys):
    """#452 — el caso que produjo el issue: `replace_pdf` cambia los tres testigos y la salvedad
    sigue diciendo preprint. Medido al cerrar #436: 43 salvedades en 31 notas, con `lint` rc 0."""
    _con_txt(toy_vault, "el cuerpo del paper, sin marca de arXiv\n")
    d = extraccion()
    d["salvedades"] = [{"tipo": "pdf_leido", "documento": "eprint"}]
    dest = sembrar(toy_vault, d, fm_extra={"pdf_source": "publisher"})
    hv.harvest("test_star")
    assert "⚙ verificada" not in dest.read_text(encoding="utf-8")
    assert "salvedad FALSA" in capsys.readouterr().out


def test_452_pdf_leido_declara_el_bibcode_de_OTRA_fuente(toy_vault):
    """⛔ #452 — es el falso positivo nº 4 de #449, el que ninguna heurística sobre prosa puede
    cerrar: «la comparación es contra la copia publicada de [otro] (en disco desde …)» es VERDADERA
    y habla del PDF de otro bibcode. Declarado, no hay nada que adivinar."""
    mn_nota = mn  # el otro paper, con su propio testigo
    otra = cfg.PAPERS / "2007otro....1U.md"
    otra.write_text("---\nbibcode: 2007otro....1U\npdf_source: publisher\ntags: [paper]\n---\n\n"
                    "## Abstract\n\nx\n", encoding="utf-8")
    assert mn_nota.safe_name("2007otro....1U")
    d = extraccion()
    d["salvedades"] = [{"tipo": "pdf_leido", "documento": "publisher",
                        "bibcode": "2007otro....1U"}]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    body = dest.read_text(encoding="utf-8")
    assert "⚙ verificada" in body and "2007otro....1U" in body, \
        "se chequea contra los testigos de ESE bibcode, no contra los de la nota"


def test_452_documento_fuera_del_vocabulario_o_sin_testigo_es_NO_EVALUABLE(toy_vault):
    """#452 / D-43 — el tercer estado. `web` es un valor legítimo de `PDF_SOURCE_OK` que **ningún
    testigo del disco decide** (un snapshot no lleva marca de arXiv ni firma de reemplazo), y un
    valor fuera de vocabulario cae por el `else` de todo `== "eprint"` en silencio (#296)."""
    assert hv.check_salvedad(BIB, {"tipo": "pdf_leido", "documento": "web"})[0] is None
    ok, det = hv.check_salvedad(BIB, {"tipo": "pdf_leido", "documento": "preprint"})
    assert ok is None and "fuera del vocabulario" in det, "`preprint` no es un valor de pdf_source"
    assert hv.check_salvedad(BIB, {"tipo": "pdf_leido", "documento": ""})[0] is None
    assert hv.check_salvedad(BIB, {"tipo": "pdf_leido", "documento": "eprint"})[0] is None, \
        "sin testigos no hay contra qué cruzar"
    # con testigo Y `web`: el no-evaluable es del VALOR, no de la falta de testigos — los dos
    # caminos llegan a `None` y hay que poder distinguirlos (D-43)
    _con_txt(toy_vault, "arXiv:2001.00001v2 [astro-ph.EP] 1 Jan 2020\n")
    ok, det = hv.check_salvedad(BIB, {"tipo": "pdf_leido", "documento": "web"})
    assert ok is None and "no lo deciden los testigos" in det
    assert hv.check_salvedad(BIB, {"tipo": "pdf_leido", "documento": "eprint"})[0] is True


def test_452_el_migrador_PROPONE_y_no_toca_la_extraccion(toy_vault):
    """⛔ #452 — la extracción es versionada y NO regenerable sin volver a leer el PDF (#311), así
    que el migrador propone la entrada lista para pegar y no escribe. Y cuando la prosa dice
    *publicado* sin que la nota declare `pdf_source`, emite el hallazgo SIN valor: entre `publisher`
    y `ads` no elige un script (#296)."""
    _con_pdf(toy_vault)
    d = extraccion()
    d["salvedades"] = ["El PDF en disco es el PREPRINT de arXiv (marca al margen).",
                       "la Fig. 3 es difícil de leer"]
    sembrar(toy_vault, d)
    antes = (cfg.EXTRACCION / "test_star" / f"{BIB}.json").read_text(encoding="utf-8")
    props = hv.propose_pdf_leido("test_star")
    assert [(b, doc) for _j, b, _t, doc, _m, _l in props] == [(BIB, "eprint")], \
        "la prosa que no habla del documento en disco NO entra"
    assert (cfg.EXTRACCION / "test_star" / f"{BIB}.json").read_text(encoding="utf-8") == antes
    # ⚠ la salvedad YA estructurada y la cadena vacía no son candidatas: la primera ya está, y la
    # segunda no dice nada. Con cualquiera de las dos adentro, la propuesta sigue siendo una sola.
    d["salvedades"] = [{"tipo": "pdf_leido", "documento": "eprint"}, "",
                       "El PDF en disco es el PREPRINT de arXiv (marca al margen)."]
    sembrar(toy_vault, d)
    assert len(hv.propose_pdf_leido("test_star")) == 1


def test_452b_el_migrador_CRUZA_EL_DISCO_antes_de_proponer(toy_vault):
    """⛔ #452, devuelto — el JSON es inmutable por diseño (#311), así que puede ser ANTERIOR a un
    `replace_pdf`: la salvedad dice preprint y en disco está la copia del editor. Medido en la
    instancia: 1 de 6 propuestas salía `eprint` sobre una nota con `pdf_reemplazo: publisher`, y el
    chequeo de la MISMA corrida la rechazaba. El hallazgo útil es la caducidad."""
    _con_pdf(toy_vault)
    d = extraccion()
    d["salvedades"] = ["El PDF en disco es el PREPRINT de arXiv (marca al margen)."]
    sembrar(toy_vault, d, fm_extra={"pdf_source": "publisher"})
    props = hv.propose_pdf_leido("test_star")
    assert [(doc, m.startswith("la salvedad quedó VIEJA"))
            for _j, _b, _t, doc, m, _l in props] == \
        [("", True)], "no se propone el valor viejo: se reporta que la salvedad caducó"
    # ⚠ y el testigo que CONFIRMA la prosa no es una caducidad: la propuesta sale con su valor
    sembrar(toy_vault, d, fm_extra={"pdf_source": "eprint"})
    assert [(doc, m) for _j, _b, _t, doc, m, _l in hv.propose_pdf_leido("test_star")] == \
        [("eprint", "")]
    # ⛔ ni lo es `web`: NINGÚN testigo del disco lo decide, así que no puede contradecir a nadie
    d["salvedades"] = ["El PDF en disco es el MANUSCRITO del autor, no el tipografiado del editor."]
    sembrar(toy_vault, d, fm_extra={"pdf_source": "publisher"})
    assert [(doc, m) for _j, _b, _t, doc, m, _l in hv.propose_pdf_leido("test_star")] == [("web", "")]


def test_452b_el_migrador_SALTEA_la_nota_sin_PDF(toy_vault):
    """⛔ #452, devuelto — «no hay archivo en disco donde buscar una marca de agua» es una afirmación
    de NO-existencia, y el ancla la matchea (`archivo` está en `_DOC_NOMBRE`). Proponer ahí afirma un
    documento que no existe. Medido: 1 de 6, con `pdf: null`."""
    d = extraccion()
    d["salvedades"] = ["No se pudo chequear si la fuente es un preprint: no hay archivo en disco "
                       "donde buscar una marca de agua."]
    sembrar(toy_vault, d)
    assert hv.propose_pdf_leido("test_star") == [], "sin PDF no hay documento del que hablar"


def test_452_la_propuesta_declara_su_poblacion_y_no_inventa_el_valor(toy_vault, capsys):
    """#452 / D-43 — el CERO se declara, y el caso que un script no puede decidir sale marcado en
    vez de con un valor inventado: entre `publisher` y `ads` no elige nadie automáticamente (#296)."""
    hv.print_pdf_leido([])
    assert "0 salvedad(es)" in capsys.readouterr().out, "el cero se declara (D-43)"
    j = cfg.EXTRACCION / "s" / "x.json"
    hv.print_pdf_leido([(j, "2020X", "El PDF en disco es …", "",
                         "la nota no declara `pdf_source`: elegí vos cuál", "")])
    out = capsys.readouterr().out
    assert "publisher|ads" in out and "elegí vos" in out
    # y el que SÍ se puede decidir sale listo para pegar, con su valor
    hv.print_pdf_leido([(j, "2020X", "El PDF …", "eprint", "", "")])
    out = capsys.readouterr().out
    assert '"documento": "eprint"' in out and "elegí vos" not in out
    # la caducidad NO sale como entrada para pegar: sale como corrección
    hv.print_pdf_leido([(j, "2020X", "El PDF …", "",
                         "la salvedad quedó VIEJA: en disco está el publicado (`pdf_source`)", "")])
    out = capsys.readouterr().out
    assert "quedó VIEJA" in out and "no la estructures tal cual" in out
    assert '"tipo": "pdf_leido"' not in out
    assert "Se PROPONE y no se escribe" in out, "la extracción es versionada y no regenerable (#311)"


def test_tipo_fuera_del_vocabulario_no_se_da_por_verificado(toy_vault):
    """#213 — vocabulario CERRADO: un typo no puede producir una salvedad que se lea como
    chequeada. Cae a no evaluable, con el motivo."""
    d = extraccion()
    d["salvedades"] = [{"tipo": "txt_perdio", "cadena": "√"}]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    body = dest.read_text(encoding="utf-8")
    assert "verificadas contra el archivo" not in body
    assert "fuera del vocabulario" in body


def test_txt_pierde_sin_cadena_no_es_verificable(toy_vault):
    """#213 — sin `cadena` no hay qué buscar: no evaluable, nunca «verificada» (D-43)."""
    _con_txt(toy_vault, "cualquier cosa")
    assert hv.check_salvedad(BIB, {"tipo": "txt_pierde"}) == (None, "sin `cadena`: no hay qué buscar")


def _nota_del_paper(texto: str):
    """La nota del paper en disco — el archivo sobre el que predica una salvedad `nota_estado`."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    nota = cfg.PAPERS / f"{cfg.note_stem(BIB)}.md"
    nota.write_text(texto, encoding="utf-8")
    return nota


def test_497_nota_estado_FALSA_se_rechaza_y_se_nombra(toy_vault):
    """⛔ #497 — la CUARTA clase de salvedad: la que predica sobre la BÓVEDA. Es la más decidible de
    todas —el archivo está a un `grep`— y era la única que no miraba nadie: `verify-citations` la
    saltea por construcción (no lleva `[[bibcode]]`), el gate de citas también (no es una cita de la
    fuente) y `check_salvedad` sólo evaluaba los tres tipos de PDF/`.txt`. Y envejece por
    construcción: el extractor la anota PORQUE algo está mal, la operación siguiente lo arregla, y
    la extracción es inmutable (#311) — medido en una bóveda real, `2011Remes` publica que su nota
    «todavía» trae un bloque de pendiente y un `## Abstract` vacío que hace rato no tiene."""
    _nota_del_paper("---\nbibcode: x\n---\n\n## Abstract\n\nel abstract transcripto del PDF.\n")
    ok, det = hv.check_salvedad(BIB, {"tipo": "nota_estado", "literal": "(no disponible)",
                                      "presente": True})
    assert ok is False and "(no disponible)" in det and "FALSA" in det, det


def test_497_nota_estado_VERDADERA_se_publica_verificada(toy_vault):
    """El control simétrico, para que no sea un apagador: con el literal presente en la nota la
    salvedad es cierta y se publica `⚙ verificada`. Y las dos direcciones se chequean igual —
    `presente: False` afirma que la nota NO lo publica, que es el mismo hecho decidible."""
    _nota_del_paper("---\nbibcode: x\n---\n\n## Abstract\n\n_(no disponible)_\n")
    ok, det = hv.check_salvedad(BIB, {"tipo": "nota_estado", "literal": "(no disponible)",
                                      "presente": True})
    assert ok is True and "SÍ publica" in det, det
    assert hv.check_salvedad(BIB, {"tipo": "nota_estado", "literal": "⏳ Fuente pendiente",
                                   "presente": False})[0] is True


def test_497_la_salvedad_no_se_aprueba_a_si_misma(toy_vault):
    """⛔ El bloque de salvedades se estampa DENTRO de la nota de la que habla, así que grepear el
    archivo entero encontraría el literal en el bullet de la propia salvedad —o en la `evidencia`
    que lo cita— y toda afirmación saldría verdadera: el chequeo se aprobaría solo. El recorte es
    estructural (las marcas de `SALVEDAD_MARCAS_LEIDAS`), no una adivinanza sobre la prosa."""
    _nota_del_paper(
        "---\nbibcode: x\n---\n\n## Abstract\n\nel abstract transcripto.\n\n"
        "## Vista — tema\n\n" + cfg.SALVEDAD_MARCAS[0] + "\n\n"
        "- ⚙ verificada: la nota SÍ publica `(no disponible)` — lo vi en el `## Abstract`\n")
    ok, det = hv.check_salvedad(BIB, {"tipo": "nota_estado", "literal": "(no disponible)",
                                      "presente": True})
    assert ok is False, det
    # ⛔ y el recorte es SÓLO el bloque: un bullet de la nota que está FUERA de él sigue contando
    # —si no, el chequeo pasaría de aprobarse solo a no ver media nota, y el literal de un `##
    # Huecos` se leería como ausente—, y el bloque termina donde termina, no en el fin del archivo
    _nota_del_paper(
        "---\nbibcode: x\n---\n\n## Abstract\n\nel abstract transcripto.\n\n"
        "## Vista — tema\n\n" + cfg.SALVEDAD_MARCAS[0] + "\n\n"
        "- ⚙ verificada: la nota SÍ publica `(no disponible)` — lo vi en el `## Abstract`\n\n"
        "## Huecos\n\n- falta el abstract: la sección dice (no disponible)\n")
    assert hv.check_salvedad(BIB, {"tipo": "nota_estado", "literal": "(no disponible)",
                                   "presente": True})[0] is True


def test_497_nota_estado_sin_literal_o_sin_presente_NO_es_verificable(toy_vault):
    """D-43 — el chequeo que no pudo correr sale *no evaluable con su motivo*, nunca «verificada».
    `presente` es obligatorio y booleano: sin él la salvedad no dice QUÉ afirma sobre la nota, y
    deducirlo de la prosa es lo que #452 midió con precisión 0/5."""
    _nota_del_paper("---\nbibcode: x\n---\n\ncuerpo\n")
    assert hv.check_salvedad(BIB, {"tipo": "nota_estado", "presente": True})[0] is None
    ok, det = hv.check_salvedad(BIB, {"tipo": "nota_estado", "literal": "x"})
    assert ok is None and "`presente`" in det, det
    # AUD-464: y BOOLEANO — `"false"` (string) es truthy, así que aceptarlo invertiría el veredicto
    for no_bool in ("false", "true", 1, 0):
        ok, det = hv.check_salvedad(BIB, {"tipo": "nota_estado", "literal": "x", "presente": no_bool})
        assert ok is None and "`presente`" in det, (no_bool, det)
    # y sin nota en disco tampoco se resuelve en contra
    (cfg.PAPERS / f"{cfg.note_stem(BIB)}.md").unlink()
    ok, det = hv.check_salvedad(BIB, {"tipo": "nota_estado", "literal": "x", "presente": True})
    assert ok is None and "no hay nota en disco" in det, det


def test_pdf_paginas_se_chequea_contra_el_pdf(toy_vault, monkeypatch):
    """#213 — el segundo tipo del vocabulario: «el PDF tiene N páginas» lo decide el propio PDF,
    vía `pdfinfo` (la MISMA dependencia de sistema que ya usa `pdftotext`: sin librería nueva)."""
    (cfg.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "test_star" / f"{BIB}.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(hv.shutil, "which", lambda _c: "/usr/bin/pdfinfo")
    monkeypatch.setattr(hv.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="Title: x\nPages:           2\n"))
    ok, detalle = hv.check_salvedad(BIB, {"tipo": "pdf_paginas", "n": 2})
    assert ok is True and "2 página(s)" in detalle
    mal, detalle = hv.check_salvedad(BIB, {"tipo": "pdf_paginas", "n": 17})
    assert mal is False and "la salvedad dice 17" in detalle


def test_pdf_paginas_sin_pdf_no_es_verificable(toy_vault):
    """#213 / D-43 — sin PDF el chequeo NO CORRIÓ; resolverlo en contra sería inventar un hallazgo.
    El motivo importa: «no hay PDF» y «no está `pdfinfo`» son dos no-evaluables distintos."""
    ok, detalle = hv.check_salvedad(BIB, {"tipo": "pdf_paginas", "n": 3})
    assert ok is None and "no hay PDF en disco" in detalle


def test_pdf_paginas_sin_pdfinfo_lo_declara(toy_vault, monkeypatch):
    """#213 / D-43 — sin la herramienta el chequeo tampoco corrió, y lo dice con SU motivo."""
    (cfg.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "test_star" / f"{BIB}.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(hv.shutil, "which", lambda _c: None)
    ok, detalle = hv.check_salvedad(BIB, {"tipo": "pdf_paginas", "n": 3})
    # «poppler-utils», no «pdfinfo» a secas: los otros no-evaluables de esta rama también nombran
    # a `pdfinfo`, así que la aserción laxa pasaba con la guarda rota (#202).
    assert ok is None and "poppler-utils" in detalle


def test_pdfinfo_sin_pages_no_es_verificable(toy_vault, monkeypatch):
    """#213 / D-43 — `pdfinfo` corrió y no devolvió `Pages:` (PDF corrupto): tercer no-evaluable
    con su motivo propio. Sin la rama, `int(m.group(1))` reventaría con `AttributeError` y el
    cosechador moriría a mitad de la cosecha por un campo secundario."""
    (cfg.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "test_star" / f"{BIB}.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(hv.shutil, "which", lambda _c: "/usr/bin/pdfinfo")
    monkeypatch.setattr(hv.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="roto\n"))
    ok, detalle = hv.check_salvedad(BIB, {"tipo": "pdf_paginas", "n": 3})
    assert ok is None and "no devolvió el número de páginas" in detalle


def test_el_txt_de_la_vista_se_cruza_contra_el_disco(toy_vault, capsys):
    """#230 — `txt` se estampaba con lo que el extractor dijera (o el slug por default), sin mirar
    el disco: 9 notas de una bóveda real declaraban `txt: ica` sin que existiera
    `raw/fulltext/ica/<bib>.txt`. El contrato lo llama «el ancla de fuente cuando el mismo bibcode
    vive bajo varios slugs», y un ancla que apunta a un archivo inexistente no ancla nada. Es la
    asimetría exacta que #207 cerró para `fuente` y que quedó abierta acá."""
    dest = sembrar(toy_vault)
    hv.harvest("test_star")
    v = read_fm(dest)["vistas"][0]
    assert "txt" not in v, "sin `.txt` en disco, «no consta» — nunca un puntero falso"
    assert "no consta" in capsys.readouterr().out


def test_el_txt_cae_a_la_copia_que_SI_existe(toy_vault):
    """#230, la otra rama: el mismo bibcode vive legítimamente bajo varios slugs con contenido
    idéntico, así que si la copia declarada no está y hay otra, se apunta a ésa — degradar
    declarando, no rechazar la lectura (rechazarla tiraría una extracción buena)."""
    dest = sembrar(toy_vault, extraccion(vista={"sujeto": "Estrella Test", "tipo": "star",
                                                "txt": "otro-slug"}))
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "test_star" / f"{BIB}.txt").write_text("texto", encoding="utf-8")
    hv.harvest("test_star")
    assert read_fm(dest)["vistas"][0]["txt"] == "test_star"


def test_la_prosa_con_barras_no_parte_la_fila(toy_vault):
    """#240 — el extractor escribe prosa en las celdas de la tabla de la vista, y esa prosa trae `|`
    todo el tiempo (matemática, columnas transcritas de una tabla del paper, una alternación de
    `grep`). Un `|` crudo PARTE la fila: las celdas de más no se renderizan, así que una afirmación
    citada y verificada queda **invisible para el lector** mientras el lint sigue contando su fila.
    Medido sobre una bóveda real: 19 filas en 13 notas de un solo tema. La regla existía (INV-99) y
    vivía sólo en el skill `verify-citations`, para la OTRA tabla."""
    dest = sembrar(toy_vault, extraccion(ground_truth=[
        {"que": "columnas de la Tabla 3", "valor": "GJ436 | tau Ceti | dominio rechazado",
         "linea": "p. 8", "regimen": "HARPS", "segunda_mano": None}]))
    hv.harvest("test_star")
    fila = [l for l in dest.read_text(encoding="utf-8").split("\n") if "GJ436" in l][0]
    assert cfg.table_shape_issues("\n".join(
        ["| Qué | Valor | Localizador | Régimen | Segunda mano |", "|---|---|---|---|---|", fila])) == []
    assert r"GJ436 \| tau Ceti" in fila


def test_dentro_de_la_matematica_va_vert_y_no_la_doble_barra(toy_vault):
    """#240, el matiz que el arreglo no puede ignorar: en LaTeX `\\|` es la DOBLE barra ‖, así que
    escapar a ciegas cambiaría la fórmula — 19 filas invisibles convertidas en 19 ecuaciones
    equivocadas, que es peor: la fila invisible se nota, la fórmula alterada no."""
    dest = sembrar(toy_vault, extraccion(ground_truth=[
        {"que": "corte", "valor": r"los bins con $|df_0/d\lambda| > 4.4$", "linea": "p. 3",
         "regimen": "HARPS", "segunda_mano": None}]))
    hv.harvest("test_star")
    fila = [l for l in dest.read_text(encoding="utf-8").split("\n") if "df_0" in l][0]
    assert r"\vert df_0/d\lambda\vert" in fila, fila
    assert r"\|" not in fila.split("$")[1], "dentro de `$…$` no puede quedar `\\|`"


def test_el_eje_contestado_vacio_se_estampa_igual(tmp_path):
    """#270 — filtrando el eje vacío, «se preguntó y no hay nada» era indistinguible de «nunca se
    preguntó»: el mismo falso limpio que #188 cierra un nivel más arriba, y sin esto el detector de
    ejes faltantes nace con centenares de ítems permanentes."""
    md = hv.render_view("tau Cet", {"ejes": {"rv": "una medición", "ml": ""}})
    assert "- **ml:** " + hv.SIN_DATOS in md
    assert "- **rv:** una medición" in md


# ── #239 · dos lecturas del mismo sujeto con lentes distintas CONVIVEN ──────────────────────────

def _nota_con_vista(tmp_path, vistas):
    import yaml
    dest = tmp_path / "p.md"
    fm = yaml.safe_dump({"bibcode": "2020a", "tags": ["paper"], "vistas": vistas},
                        sort_keys=False, allow_unicode=True)
    dest.write_text(f"---\n{fm}---\n# p\n\n## Vista — tau Cet\n\ntexto viejo\n", encoding="utf-8")
    return dest


def test_una_segunda_lente_NO_pisa_la_vista_anterior(tmp_path):
    """#239 — la identidad de una vista es `(sujeto, enfasis)`. Con la clave vieja (el sujeto a
    secas), una segunda lectura del mismo sujeto con otra lente entraba por la misma rama y
    `{**v, **vista}` **pisaba la anterior en silencio**: no es que no estuviera soportada, es que
    era destructiva."""
    dest = _nota_con_vista(tmp_path, [{"sujeto": "tau Cet", "tipo": "star", "fecha": "2026-01-01"}])
    assert hv.upsert_view(dest, {"sujeto": "tau Cet", "tipo": "star", "fecha": "2026-08-30",
                                 "enfasis": "ruido"}) is True
    vistas = cfg.split_fm(dest.read_text(encoding="utf-8"))["vistas"]
    assert len(vistas) == 2, vistas
    assert {v.get("enfasis", "") for v in vistas} == {"", "ruido"}
    assert [v for v in vistas if not v.get("enfasis")][0]["fecha"] == "2026-01-01", \
        "la lectura anterior conserva su fecha"


def test_la_misma_clave_no_cambia_un_valor_ya_escrito(tmp_path):
    """Y aun con la MISMA clave el merge es add-only: un valor distinto bajo la misma clave es otra
    lectura mal declarada, y resolverlo en silencio es lo que este issue arregla."""
    dest = _nota_con_vista(tmp_path, [{"sujeto": "tau Cet", "tipo": "star", "fecha": "2026-01-01"}])
    with pytest.raises(hv.ViewUpsertError, match="ya declara otro valor"):
        hv.upsert_view(dest, {"sujeto": "tau Cet", "tipo": "star", "fecha": "2026-08-30"})
    assert hv.upsert_view(dest, {"sujeto": "tau Cet", "tipo": "star", "fecha": "2026-08-30"},
                          force=True) is True
    assert cfg.split_fm(dest.read_text(encoding="utf-8"))["vistas"][0]["fecha"] == "2026-08-30"


def test_la_misma_clave_completa_lo_que_falta(tmp_path):
    """La otra mitad del add-only: re-cosechar la misma lectura sí puede completar campos que la
    entrada no tenía (es lo que hace idempotente al cosechador)."""
    dest = _nota_con_vista(tmp_path, [{"sujeto": "tau Cet", "tipo": "star"}])
    assert hv.upsert_view(dest, {"sujeto": "tau Cet", "tipo": "star", "fecha": "2026-08-30"}) is True
    assert cfg.split_fm(dest.read_text(encoding="utf-8"))["vistas"][0]["fecha"] == "2026-08-30"


def test_la_sub_seccion_de_lente_no_pisa_la_vista_del_sujeto(tmp_path):
    """La segunda lectura se escribe como `### Lente — …` DENTRO de `## Vista — <sujeto>`: la prosa
    de la primera queda intacta."""
    dest = _nota_con_vista(tmp_path, [{"sujeto": "tau Cet", "tipo": "star"}])
    cuerpo = hv.render_view("tau Cet", {"enfasis": "ruido", "aporte": "lo nuevo"})
    assert hv.write_view_section(dest, "tau Cet", cuerpo, theme=False, enfasis="ruido") is True
    texto = dest.read_text(encoding="utf-8")
    assert "texto viejo" in texto, "la lectura anterior no se toca"
    assert "### Lente — ruido" in texto and texto.count("## Vista — tau Cet") == 1


def test_la_sub_seccion_con_prosa_tampoco_se_pisa(tmp_path, capsys):
    """Misma regla que la sección entera, un nivel abajo: sus anclas cuelgan del texto exacto."""
    dest = _nota_con_vista(tmp_path, [{"sujeto": "tau Cet", "tipo": "star"}])
    cuerpo = hv.render_view("tau Cet", {"enfasis": "ruido", "aporte": "primera"})
    hv.write_view_section(dest, "tau Cet", cuerpo, theme=False, enfasis="ruido")
    otro = hv.render_view("tau Cet", {"enfasis": "ruido", "aporte": "segunda"})
    assert hv.write_view_section(dest, "tau Cet", otro, theme=False, enfasis="ruido") is False
    assert "NO se pisa" in capsys.readouterr().out
    assert "primera" in dest.read_text(encoding="utf-8")


def test_la_vista_registra_los_ejes_QUE_SE_PREGUNTARON(toy_vault, monkeypatch):
    """#307 — `vistas[].lente` guarda la lente vigente al leer, que es lo que hace posible el diff
    de D-49 a nivel de lectura. Con ejes propios del tema, registrar las facetas globales
    describiría una lectura que no ocurrió.

    @inv INV-146"""
    write_yaml(cfg.THEMES_YAML, {"ica_ruido": {
        "title": "ICA ruidosa", "concept": "ica-ruido", "area": "methods", "facet": "noisy ICA",
        "ejes": ["heterocedasticidad", "identificabilidad"]}})
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2002Cardoso.md").write_text(
        "---\nbibcode: 2002Cardoso\nthesis_links: [ica-ruido]\nvistas: []\n---\n\n"
        "## Abstract\n\nx\n## Vista — ica-ruido\n\n_(pendiente)_\n", encoding="utf-8")
    src = cfg.EXTRACCION / "ica_ruido"
    src.mkdir(parents=True, exist_ok=True)
    (src / "2002Cardoso.json").write_text(json.dumps({
        "bibcode": "2002Cardoso", "ejes": {"heterocedasticidad": "Σ diagonal"},
        "ground_truth": [], "aporte": "x",
        "vista": {"sujeto": "ica-ruido", "tipo": "theme", "fuente": "abstract"}}),
        encoding="utf-8")
    hv.harvest("ica_ruido", theme=True)
    fm = cfg.split_fm((cfg.PAPERS / "2002Cardoso.md").read_text(encoding="utf-8"))
    assert fm["vistas"][0]["lente"] == ["heterocedasticidad", "identificabilidad"]


# ── #331 · el remedio que imprime el cosechador tiene que CORRER ──────────────
def test_el_remedio_por_nota_faltante_lleva_theme_en_un_TEMA(toy_vault, capsys):
    """Gemelo del de `triage.py --sintesis`: con el slug pelado, en un tema el comando que se
    imprime como remedio muere con un `KeyError` que culpa a `stars.yaml` de un slug definido en
    `themes.yaml`.

    @inv INV-141"""
    write_yaml(cfg.THEMES_YAML, {"ica_ruido": {"title": "ICA ruidosa", "concept": "ica-ruido",
                                               "area": "methods", "facet": "noisy ICA"}})
    src = cfg.EXTRACCION / "ica_ruido"
    src.mkdir(parents=True, exist_ok=True)
    (src / "2002Cardoso.json").write_text(json.dumps({
        "bibcode": "2002Cardoso", "ejes": {}, "ground_truth": [], "aporte": "x",
        "vista": {"sujeto": "ica-ruido", "tipo": "theme", "fuente": "abstract"}}),
        encoding="utf-8")
    r = hv.harvest("ica_ruido", theme=True)
    assert r["sin_nota"] == 1
    assert "`python scripts/make_notes.py ica_ruido --theme`" in capsys.readouterr().out


def test_el_remedio_por_nota_faltante_NO_lleva_theme_en_una_ESTRELLA(toy_vault, capsys):
    """El simétrico, por el mismo motivo que en `triage`: el flag se resuelve."""
    d = cfg.EXTRACCION / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{BIB}.json").write_text(json.dumps(extraccion()), encoding="utf-8")
    assert hv.harvest("test_star")["sin_nota"] == 1
    out = capsys.readouterr().out
    assert "`python scripts/make_notes.py test_star`" in out and "--theme" not in out


def test_la_lente_DECLARADA_por_la_extraccion_gana_sobre_los_ejes_vigentes(toy_vault):
    """#395a — el cosechador no sabe qué ejes se preguntaron: estampaba los vigentes AL COSECHAR,
    que es otra pregunta. Medido en una bóveda real: 209 slots declarando tres facetas que la
    instancia agregó a `objective.yaml` DESPUÉS de esas lecturas, sobre papers donde nadie las
    preguntó — rompe INV-146, y el detector de #270 lee esa declaración como verdad y pide re-leer.

    Desde #395 la lente viaja en el JSON, escrita por `extraction_prompt`, que es el único que la
    sabe con certeza. Acá la declarada NO es la del objetivo, así que si el cosechador la ignorara
    el assert cae."""
    pedidos = ["rv", "un_eje_que_el_objetivo_no_declara"]
    sembrar(toy_vault, extraccion(lente=pedidos))
    hv.harvest("test_star")
    v = read_fm(cfg.PAPERS / f"{BIB}.md")["vistas"][0]
    assert v["lente"] == pedidos, v["lente"]
    assert v["lente"] != list(mn.objective_lens()[0])


def test_sin_lente_declarada_sigue_mandando_la_del_sujeto(toy_vault):
    """#395a, el recorte — una extracción PRE-#395 no trae `lente:`, y ahí el comportamiento
    anterior (#372) se mantiene tal cual: las claves de `ejes` de una lectura normal son lo
    CONTESTADO, no lo preguntado, y tomarlas encogería el denominador de #270."""
    sembrar(toy_vault, extraccion(ejes={"rv": "reporta K"}))
    hv.harvest("test_star")
    v = read_fm(cfg.PAPERS / f"{BIB}.md")["vistas"][0]
    assert v["lente"] == list(mn.objective_lens()[0])


def test_la_linea_del_abstract_transcrito_no_afirma_un_sin_abstract_QUE_NO_ESTA(toy_vault):
    """#416 — la distinción que la línea traza es real y siempre cierta (una transcripción no es la
    copia de catálogo); la cláusula que la seguía —«la nota sigue declarando `sin_abstract`»— se
    estampaba INCONDICIONALMENTE sobre un campo que la nota casi nunca tiene. Medido: 26 de las 27
    notas que la llevaban no lo tenían, y toda la bóveda tenía UNA con el campo poblado.

    Es estructural: `sin_abstract` lo escribe el carril de DESCUBRIMIENTO y la línea la estampa el
    de COSECHA, que no lo leía — y en un tema off-ADS declarado por `sources:` no corre ninguno de
    los tres backends, así que el campo no existe nunca."""
    assert "no es la copia de catálogo" in hv.transcribed_note({}), "la mitad que SIEMPRE vale"
    assert "sin_abstract" not in hv.transcribed_note({})
    assert "sin_abstract" not in hv.transcribed_note({"sin_abstract": False}), "declarado en falso"
    assert "sin_abstract" in hv.transcribed_note({"sin_abstract": True}), "y cuando SÍ está, se dice"
    assert "no es la copia de catálogo" in hv.transcribed_note({"sin_abstract": True})


def test_force_LLEGA_a_upsert_view_y_declara_el_ascenso(toy_vault, capsys):
    """#420 — `upsert_view` aceptaba `force` y el cosechador lo llamaba SIN pasarlo, así que
    `harvest_views <slug> --force` rehusaba igual con el flag puesto: un parámetro que ningún flag
    activa, la forma que este repo ya pagó en #103, #112, #256 y `--dry-run`. El caso que lo
    destapó es la ruta que #207 prescribe —una vista `fuente: abstract` es una lectura degradada y
    declarada, y el pedido es conseguir el PDF—: sin esto, no se podía ejecutar.

    Y el reemplazo se DECLARA en `previa`: sin eso la única huella de que hubo una lectura anterior
    es que la fecha cambió, indistinguible de un re-estampado espurio (D-18)."""
    vista = {"sujeto": "Estrella Test", "tipo": "star", "txt": "test_star", "fuente": "abstract"}
    dest = sembrar(toy_vault, extraccion(vista=vista))
    hv.harvest("test_star")
    v0 = read_fm(dest)["vistas"][0]
    assert v0["fuente"] == "abstract" and v0.get("fecha"), v0

    # la lectura del abstract fue hace días: el ascenso tiene que preservar ESA fecha
    dest.write_text(dest.read_text(encoding="utf-8").replace(v0["fecha"], "2026-08-01"),
                    encoding="utf-8")
    # ahora aparece el PDF y el extractor re-lee: la vista ASCIENDE (#207). Sin `--force`, choca.
    (cfg.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "test_star" / f"{BIB}.pdf").write_bytes(b"%PDF-1.4\n")
    # ⚠ se reescribe SÓLO el JSON: `sembrar` re-crea la nota, y con la nota nueva no habría choque
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(
        json.dumps(extraccion(vista={**vista, "fuente": "pdf"})), encoding="utf-8")
    hv.harvest("test_star")
    assert read_fm(dest)["vistas"][0]["fuente"] == "abstract", "sin force no pisa"
    assert "ya declara otro valor" in capsys.readouterr().out

    hv.harvest("test_star", force=True)
    v1 = read_fm(dest)["vistas"][0]
    assert v1["fuente"] == "pdf", "con force SÍ reemplaza — antes el flag no llegaba"
    assert v1["previa"]["fuente"] == "abstract", "y queda dicho de dónde vino (#207)"
    assert v1["previa"]["fecha"] == "2026-08-01", "con la fecha vieja preservada"
    assert set(v1["previa"]) == {"fecha", "fuente"}, "sólo los campos que chocaron"

    # ⛔ Y `--force` SIN choque no deja `previa`: un `previa: {}` en cada re-cosecha forzada sería
    # ruido de diff sobre un artefacto versionado, y diría «hubo un reemplazo» donde no lo hubo.
    hv.harvest("test_star", force=True)
    assert "previa" not in {k: v for k, v in read_fm(dest)["vistas"][0].items() if k != "previa"} \
        or read_fm(dest)["vistas"][0]["previa"] == v1["previa"], "no se re-escribe sin choque"

    # directo sobre la función, que es donde vive la guarda: con `force` y SIN choque, la entrada
    # se completa y no se marca — `previa: {}` en cada re-cosecha forzada sería ruido de diff sobre
    # un artefacto versionado, y diría «hubo un reemplazo» donde no lo hubo.
    d2 = cfg.PAPERS / "2021otr....2E.md"
    d2.write_text("---\ntags: [paper]\nbibcode: 2021otr....2E\n"
                  "vistas:\n  - sujeto: Estrella Test\n    tipo: star\n---\n\n# x\n",
                  encoding="utf-8")
    assert hv.upsert_view(d2, {"sujeto": "Estrella Test", "tipo": "star",
                               "fecha": "2026-09-06", "fuente": "pdf"}, force=True) is True
    v2 = read_fm(d2)["vistas"][0]
    assert v2["fuente"] == "pdf" and "previa" not in v2, "sin choque no hay `previa`"

    # ⚠ Declarado: la cláusula `force` de `if force and reemplazo:` sobrevive a `--guardas` y va a
    # seguir sobreviviendo — sin `force`, un `choques` no vacío ya levantó `ViewUpsertError` diez
    # líneas antes, así que la rama es inalcanzable con `force` en falso (red 8).


def test_paper_acota_la_cosecha_a_UNA_extraccion(toy_vault, capsys):
    """#420 — `--force` reemplaza la `fecha` de una lectura que ocurrió, así que a nivel slug
    falsifica la procedencia de todo lo demás: medido, 36/45/21 vistas con fecha en los tres slugs
    donde había que ascender UNA. El alcance por unidad es el que ya tenían `fetch_bibtex --paper`
    y `check_retractions --paper`."""
    d1 = sembrar(toy_vault, extraccion())
    d2 = sembrar(toy_vault, extraccion(bibcode="2021otr....2E"), stem="2021otr....2E")
    n = hv.harvest("test_star", paper=BIB)
    assert n["cosechadas"] == 1, n
    assert read_fm(d1)["vistas"][0].get("fecha"), "la pedida se cosechó"
    assert not read_fm(d2)["vistas"][0].get("fecha"), "la otra queda con su vista SIN leer"
    # D-43 — un `--paper` que no matchea nada lo DICE, no cosecha cero y sale como si no hubiera
    assert hv.harvest("test_star", paper="9999nada")["cosechadas"] == 0
    assert "sin extracción de `9999nada`" in capsys.readouterr().out


def test_force_sin_paper_es_un_ERROR_no_un_barrido(toy_vault, monkeypatch):
    """No se prohíbe `--force`: se pide el alcance. Correrlo sobre el slug entero re-estampa las
    vistas verificadas, que es justo lo que el flag no debería poder hacer sin que nadie lo pida."""
    monkeypatch.setattr(sys, "argv", ["harvest_views.py", "test_star", "--force"])
    with pytest.raises(SystemExit):
        hv.main()
    monkeypatch.setattr(sys, "argv",
                        ["harvest_views.py", "test_star", "--force", "--paper", "2020ext....1E"])
    assert hv.main() == 0


def test_previa_solo_marca_los_campos_de_LECTURA_no_una_migracion(toy_vault):
    """#420 — `previa` dice «hubo otra lectura antes», así que sólo la marcan los campos que dicen
    que la lectura OCURRIÓ (`fecha`, `fuente`, `txt`). `lente` describe lo que se PREGUNTÓ y
    corregirlo es una migración (#395, `--restamp-lente`, que llama `upsert_view(force=True)` sobre
    209 slots): marcarlo afirmaría un reemplazo que no hubo.

    ⛔ Lo destapó `carriers.py --check` al firmar la entrada de #420 — `make_notes` llamaba a
    `upsert_view` y la entrada lo daba por fuera de alcance."""
    d = cfg.PAPERS / "2021otr....2E.md"
    base = ("---\ntags: [paper]\nbibcode: 2021otr....2E\nvistas:\n  - sujeto: Estrella Test\n"
            "    tipo: star\n    fecha: '2026-08-01'\n    fuente: abstract\n    lente:\n"
            "      - rv\n---\n\n# x\n")
    d.write_text(base, encoding="utf-8")
    assert hv.upsert_view(d, {"sujeto": "Estrella Test", "tipo": "star",
                              "lente": ["rv", "actividad"]}, force=True) is True
    v = read_fm(d)["vistas"][0]
    assert v["lente"] == ["rv", "actividad"] and "previa" not in v, "migración, no lectura"

    d.write_text(base, encoding="utf-8")
    assert hv.upsert_view(d, {"sujeto": "Estrella Test", "tipo": "star",
                              "fuente": "pdf", "lente": ["rv", "actividad"]}, force=True) is True
    v = read_fm(d)["vistas"][0]
    assert set(v["previa"]) == {"fuente"}, "el `lente` reemplazado NO entra en `previa`"


# ── #453 · el re-estampado ACOTADO del bloque de salvedades ──────────────────

def test_453_restamp_salvedades_NO_refecha_la_lectura(toy_vault):
    """⛔ #453 — la regla: lo que un script estampa desde un artefacto tiene su re-estampado
    ACOTADO. El bloque de salvedades era la excepción, así que cobrar una salvedad estructurada
    (#452) obligaba a re-cosechar la vista, y `--force` **re-fecha la lectura**: medido, `fecha` y
    `lente` de una vista leída el 2026-08-31 reescritas al 2026-09-13 con la lente de hoy, sobre una
    lectura que no volvió a ocurrir. Eso es INV-146 roto del otro lado (#395)."""
    _con_txt(toy_vault, "el texto sin el simbolo raro")
    d = extraccion()
    d["salvedades"] = ["la Fig. 3 es difícil de leer"]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    antes_fm = cfg.split_fm(dest.read_text(encoding="utf-8"))["vistas"][0]

    # ahora se COBRA una salvedad estructurada en el JSON, como propone #452
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ_{×+×}",
                        "evidencia": "la fórmula está en la p. 4, y el `.txt` la pierde"},
                       "la Fig. 3 es difícil de leer"]
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(d), encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    body = dest.read_text(encoding="utf-8")
    assert r["tocadas"] == [BIB] and r["revisadas"] == 1
    assert "⚙ verificada" in body and "ζ_{×+×}" in body
    assert "la fórmula está en la p. 4" in body, \
        "#453 — `evidencia` es lo que el lector VIO y el chequeo no la re-deriva"
    assert "la Fig. 3 es difícil de leer" in body, "la prosa restante sigue publicada, marcada"
    assert cfg.split_fm(body)["vistas"][0] == antes_fm, \
        "⛔ la lectura no volvió a ocurrir: `fecha` y `lente` NO se tocan (INV-146)"


def test_453_restamp_salvedades_es_IDEMPOTENTE_y_declara_su_poblacion(toy_vault, capsys):
    """#453 — red nº 6 del framework: correr dos veces no cambia nada. Y el CERO se declara, con su
    denominador: «0 tocadas» sobre 0 extracciones no es lo mismo que sobre 40 (INV-40/D-43)."""
    _con_txt(toy_vault, "sin el simbolo")
    d = extraccion()
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ"}]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    hv.restamp_salvedades("test_star")
    antes = dest.read_text(encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert r["tocadas"] == [] and dest.read_text(encoding="utf-8") == antes, "IDEMPOTENTE"
    hv.print_restamp_salvedades(r, "test_star", dry_run=False)
    out = capsys.readouterr().out
    assert "0 nota(s) sobre 1 extracción(es)" in out, "el cero se declara con su denominador"
    assert "NO toca `vistas[]`" in out


def test_453_el_dry_run_NO_escribe_y_la_prosa_ajena_se_REHUSA(toy_vault):
    """⛔ #453 — dos recortes. El `--dry-run` dice qué cambiaría y no toca el disco; y si el bloque
    tiene algo que el cosechador no escribió, se REHÚSA nombrando la nota en vez de destruirlo
    (misma doctrina que `write_view_section` con la prosa redactada)."""
    _con_txt(toy_vault, "sin el simbolo")
    d = extraccion()
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ"}]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ"}, "una prosa nueva del extractor"]
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(d), encoding="utf-8")
    antes = dest.read_text(encoding="utf-8")
    r = hv.restamp_salvedades("test_star", dry_run=True)
    assert r["tocadas"] == [BIB] and dest.read_text(encoding="utf-8") == antes, "--dry-run no escribe"

    # alguien anotó a mano DENTRO del bloque: no es del cosechador → se rehúsa
    marcado = antes.replace("**Salvedades (verificadas contra el archivo):**",
                            "**Salvedades (verificadas contra el archivo):**\n\n"
                            "Ojo: esto lo escribí yo a mano.")
    assert marcado != antes
    dest.write_text(marcado, encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert [b for b, _m in r["rehusadas"]] == [BIB] and r["tocadas"] == []


def test_453_las_ramas_del_restamp_acotado(toy_vault, capsys):
    """#453 — las precondiciones, cada una con su respuesta: `--paper` acota, la nota que no existe
    o la vista sin sujeto se saltean sin contarse, la nota sin `## Vista` y la lente sin
    `### Lente` se REPORTAN (no son lo mismo que «no había nada que hacer», D-43), y el bloque que
    todavía no está se AGREGA."""
    _con_txt(toy_vault, "sin el simbolo")
    d = extraccion()
    d["salvedades"] = []
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    assert "**Salvedades" not in dest.read_text(encoding="utf-8")
    # (a) el bloque que NO existe todavía se agrega
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ"}]
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(d), encoding="utf-8")
    assert hv.restamp_salvedades("test_star")["tocadas"] == [BIB]
    assert "⚙ verificada" in dest.read_text(encoding="utf-8")
    # (b) `--paper` acota
    assert hv.restamp_salvedades("test_star", paper="otro")["revisadas"] == 0
    # (c) la vista SIN sujeto no se cuenta: no hay sección que ubicar
    d["vista"] = {"sujeto": "", "tipo": "star"}
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(d), encoding="utf-8")
    assert hv.restamp_salvedades("test_star")["revisadas"] == 0
    # (d) la nota SIN esa `## Vista` se REPORTA
    d["vista"] = {"sujeto": "Otra Estrella", "tipo": "star"}
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(d), encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert [b for b, _m in r["sin_bloque"]] == [BIB] and r["tocadas"] == []
    hv.print_restamp_salvedades(r, "test_star", dry_run=False)
    assert "no tiene `## Vista" in capsys.readouterr().out
    # (e) y la LENTE que la nota no tiene, igual (#239)
    d["vista"] = {"sujeto": "Estrella Test", "tipo": "star"}
    d["enfasis"] = "ruido"
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(d), encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert [m for _b, m in r["sin_bloque"]] == ["la vista no tiene `### Lente — ruido`"]


def test_453_la_nota_que_no_existe_no_se_cuenta(toy_vault):
    """#453 / D-43 — una extracción sin nota no es «revisada y sin cambios»: no hay dónde estampar.
    Se saltea sin inflar el denominador, que es lo que hace legible el conteo."""
    d = cfg.EXTRACCION / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2099sin....1X.json").write_text(json.dumps(
        {"bibcode": "2099sin....1X", "vista": {"sujeto": "Estrella Test", "tipo": "star"},
         "salvedades": ["algo"]}), encoding="utf-8")
    assert hv.restamp_salvedades("test_star")["revisadas"] == 0


def test_453_la_lente_se_re_estampa_SIN_tocar_la_vista_del_sujeto(toy_vault):
    """⛔ #453 + #239 — con `enfasis` la unidad es la sub-sección `### Lente — <x>`: su bloque de
    salvedades se re-estampa y el de la vista de arriba queda intacto. Dos lecturas del mismo sujeto
    conviven, y el re-estampado acotado de una no puede pisar a la otra."""
    _con_txt(toy_vault, "sin el simbolo")
    base = extraccion()
    base["salvedades"] = ["prosa de la primera lectura"]
    dest = sembrar(toy_vault, base)
    hv.harvest("test_star")
    d2 = extraccion()
    d2["enfasis"] = "ruido"
    d2["salvedades"] = ["prosa de la segunda"]
    (cfg.EXTRACCION / "test_star" / f"{BIB}__ruido.json").write_text(json.dumps(d2),
                                                                    encoding="utf-8")
    hv.harvest("test_star")
    d2["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ",
                         "evidencia": "prosa de la segunda"}]
    (cfg.EXTRACCION / "test_star" / f"{BIB}__ruido.json").write_text(json.dumps(d2),
                                                                     encoding="utf-8")
    hv.restamp_salvedades("test_star", paper=BIB)
    body = dest.read_text(encoding="utf-8")
    assert "prosa de la primera lectura" in body, "la vista del sujeto no se toca"
    assert "⚙ verificada" in body and "prosa de la segunda" in body, \
        "estructurada: el texto sigue en la nota (#453), dentro de `evidencia`"


def test_453b_el_restamp_REHUSA_si_revertiria_una_correccion(toy_vault, capsys):
    """⛔ #453 devuelto — la guarda miraba la FORMA del bloque (¿están los marcadores?) y no su
    CONTENIDO, así que la prosa corregida A MANO dentro de un bloque bien formado le era invisible.
    Y el JSON es inmutable por diseño (#311), o sea que puede ser MÁS VIEJO que la nota: medido en un
    barrido de 144 notas, **27 pasaron a afirmar un documento que sus propios testigos desmienten**
    —la corrección de #449 revertida— y 50 `⚙ verificada` desaparecieron sin que nada lo dijera."""
    _con_pdf(toy_vault)
    d = extraccion()
    d["salvedades"] = ["El PDF en disco es el PREPRINT de arXiv (marca al margen)."]
    dest = sembrar(toy_vault, d, fm_extra={"pdf_source": "eprint"})
    hv.harvest("test_star")
    assert cfg.disk_doc_conflict(dest.read_text(encoding="utf-8"),
                                 cfg.split_fm(dest.read_text(encoding="utf-8")), BIB) is None

    # el PDF se reemplazó: los testigos ahora dicen `publicado` y la nota se corrigió a mano
    body = dest.read_text(encoding="utf-8")
    # el PDF se reemplazó y alguien BORRÓ la salvedad vieja de la nota: el JSON la vuelve a traer,
    # así que el re-estampado la AGREGA (pasa la guarda de reescritura) e introduce el conflicto
    nuevo = body.replace("pdf_source: eprint", "pdf_source: publisher") \
                .replace("- El PDF en disco es el PREPRINT de arXiv (marca al margen).\n", "")
    assert "pdf_source: publisher" in nuevo and "El PDF en disco" not in nuevo
    dest.write_text(nuevo, encoding="utf-8")
    antes = dest.read_text(encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert dest.read_text(encoding="utf-8") == antes, "⛔ no se revierte la corrección"
    assert r["tocadas"] == [] and [b for b, _m in r["rehusadas"]] == [BIB]
    hv.print_restamp_salvedades(r, "test_star", dry_run=False)
    assert "INTRODUCE" in capsys.readouterr().out, "y dice que lo introduce ESTE re-estampado"


def test_453b_avisa_cuando_una_verificada_DEJA_de_serlo(toy_vault, capsys):
    """#453 devuelto — que una salvedad CHEQUEADA deje de estarlo es un cambio de estado (el PDF se
    reemplazó y el conteo de páginas ya no da), no ruido de diff: 50 se fueron sin que nada lo
    dijera."""
    _con_txt(toy_vault, "sin el simbolo")
    d = extraccion()
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ"}]
    sembrar(toy_vault, d)
    hv.harvest("test_star")
    d["salvedades"] = ["ahora es sólo prosa"]
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(d), encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert r["perdidas"] == [(BIB, 1)] and r["tocadas"] == [BIB]
    hv.print_restamp_salvedades(r, "test_star", dry_run=False)
    assert "DEJARON de estarlo" in capsys.readouterr().out


def test_453c_el_restamp_REHUSA_reescribir_una_salvedad_en_prosa(toy_vault):
    """⛔ #453, devuelto por SEGUNDA vez — el cruce de disco de v1.265.1 comparte ANCLA con el
    detector de #449, así que sólo protege las frases que ese detector sabe mirar: la corrección
    real está redactada «Esta vista se leyó del PREPRINT …», que **no ancla** (no dice «en disco»),
    pasaba limpia, y el texto falso que quedaba era encima **invisible** para `doc_en_disco`. Medido
    sobre un barrido de 65 notas: **28 salvedades reescritas**, 22 de ellas las correcciones del
    09-12, y una una CITA TEXTUAL cambiada por otra que la fuente no dice —que no caza nadie, porque
    una salvedad no lleva `[[bibcode]]` (el agujero de #213)—.

    La regla es ESTRUCTURAL y no depende de ningún ancla: una salvedad en prosa ya escrita no se
    reescribe. Medido: deja pasar 43 de 65 y frena las 22."""
    _con_pdf(toy_vault)
    d = extraccion()
    d["salvedades"] = ["El PDF en disco es el PREPRINT de arXiv (marca al margen)."]
    dest = sembrar(toy_vault, d, fm_extra={"pdf_source": "eprint"})
    hv.harvest("test_star")
    # la corrección a mano: la frase cambia y NO ancla («en disco» ya no está)
    dest.write_text(dest.read_text(encoding="utf-8").replace(
        "- El PDF en disco es el PREPRINT de arXiv (marca al margen).",
        "- Esta vista se leyó del PREPRINT de arXiv (marca al margen)."), encoding="utf-8")
    antes = dest.read_text(encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert dest.read_text(encoding="utf-8") == antes, "⛔ la corrección a mano NO se pisa"
    assert r["tocadas"] == [] and [b for b, _m in r["rehusadas"]] == [BIB]
    assert "REESCRIBIRÍA 1 salvedad(es)" in r["rehusadas"][0][1]


def test_453c_agregar_pasa_y_PERDER_una_prosa_se_rehusa(toy_vault):
    # @inv INV-162
    """⛔ #453, cuarta devolución — la regla es simétrica: agregar pasa, **reescribir y BORRAR se
    rehúsan**. Con el bloque marcado la corrección a mano quedaba como línea distinta → reescritura
    → rehusada (56 veces); con el bloque pelado no tenía contraparte en el render, así que no era
    reescritura y **se borraba**: −41 bullets sobre 29 notas, entre ellos 2 registros de curación
    que #112 pide visibles y 5 correcciones de #449.

    ⚠ Y la escotilla que mantiene vivo el cobro de #452: el bullet que se va porque se ESTRUCTURÓ no
    es un borrado — su texto sigue en la nota, dentro de la estructurada (`evidencia`)."""
    _con_txt(toy_vault, "sin el simbolo")
    d = extraccion()
    d["salvedades"] = ["la Fig. 3 es difícil de leer"]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    # AGREGAR una prosa nueva junto a la que ya está
    d["salvedades"] = ["la Fig. 3 es difícil de leer", "la Tabla 2 está partida en dos páginas"]
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(d), encoding="utf-8")
    assert hv.restamp_salvedades("test_star")["tocadas"] == [BIB]
    assert "la Tabla 2" in dest.read_text(encoding="utf-8")
    # PERDER una prosa sin contraparte: se rehúsa (la vuelta 4)
    d["salvedades"] = ["la Tabla 2 está partida en dos páginas"]
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(d), encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert r["tocadas"] == [] and "BORRARÍA 1 salvedad(es)" in r["rehusadas"][0][1]
    # ESTRUCTURARLA: el texto sigue en la nota, dentro de `evidencia` → es el cobro de #452, pasa
    d["salvedades"] = [{"tipo": "txt_pierde", "cadena": "ζ",
                        "evidencia": "la Fig. 3 es difícil de leer"},
                       "la Tabla 2 está partida en dos páginas"]
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(d), encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert r["tocadas"] == [BIB] and r["rehusadas"] == []
    body = dest.read_text(encoding="utf-8")
    assert "⚙ verificada" in body and "la Fig. 3 es difícil de leer" in body


def test_453d_el_bloque_LEGACY_se_MIGRA_en_vez_de_duplicarse(toy_vault):
    """⛔ #453, tercera devolución — el bloque pelado anterior a #213 (`**Salvedades:**`) no estaba
    en las marcas, así que `salvedades_span` devolvía `None` y la nota no caía ni en la rama que
    rehúsa ni en la que reemplaza: caía en la que AGREGA, y quedaba con los dos bloques y cada
    bullet repetido. Medido en un barrido: **25 notas duplicadas**, con el lint en lockstep
    («Salvedades sin la marca de #213» 25 → 0 y «párrafo duplicado» 0 → 25, las mismas notas) — un
    falso verde doble, porque la nota sale de la categoría de #213 **justo porque** ahora tiene el
    bloque marcado, con el contenido repetido abajo.

    Reconocerlo es el MIGRADOR de #213: se lee para reemplazarlo, nunca se vuelve a escribir."""
    _con_txt(toy_vault, "sin el simbolo")
    d = extraccion()
    d["salvedades"] = ["la Fig. 3 es difícil de leer"]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    # la nota vieja: el bloque PELADO, como lo dejaba el schema pre-#213
    dest.write_text(dest.read_text(encoding="utf-8").replace(
        cfg.SALVEDAD_MARCAS[1], cfg.SALVEDAD_MARCA_LEGACY), encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    body = dest.read_text(encoding="utf-8")
    assert r["tocadas"] == [BIB] and r["rehusadas"] == []
    assert body.count("la Fig. 3 es difícil de leer") == 1, "⛔ NO se duplica: se migra"
    assert cfg.SALVEDAD_MARCA_LEGACY not in body and cfg.SALVEDAD_MARCAS[1] in body
    # y es idempotente: la segunda pasada ya no tiene nada que migrar
    assert hv.restamp_salvedades("test_star")["tocadas"] == []


def test_453e_el_legacy_NO_PIERDE_los_bullets_que_el_JSON_no_tiene(toy_vault):
    """⛔ #453, cuarta devolución — el caso medido: migrar el bloque pelado lo reemplaza por el
    render, y todo bullet que la nota tenía y el JSON no, **desaparecía**. Medido: −41 bullets / +0
    sobre 29 notas, entre ellos **2 registros de curación** que #112 pide visibles («⚠ ARTEFACTOS
    BORRADOS … `triage.py --drop-core`») y **5 correcciones de #449**. El bloque pelado es por
    definición anterior a #213, o sea la población con más prosa que nadie volvió a escribir en
    ningún JSON: justo donde borrar duele más."""
    _con_txt(toy_vault, "sin el simbolo")
    d = extraccion()
    d["salvedades"] = ["la Fig. 3 es difícil de leer"]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    dest.write_text(dest.read_text(encoding="utf-8")
                    .replace(cfg.SALVEDAD_MARCAS[1], cfg.SALVEDAD_MARCA_LEGACY)
                    .replace("- la Fig. 3 es difícil de leer",
                             "- la Fig. 3 es difícil de leer\n- ⚠ ARTEFACTOS BORRADOS por "
                             "`triage.py --drop-core`"), encoding="utf-8")
    antes = dest.read_text(encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert dest.read_text(encoding="utf-8") == antes, "⛔ el registro de curación NO se pierde"
    assert [b for b, _m in r["rehusadas"]] == [BIB]
    assert "BORRARÍA 1 salvedad(es)" in r["rehusadas"][0][1]


def test_453d_el_legacy_con_una_CORRECCION_A_MANO_se_rehusa_igual(toy_vault):
    """#453 — migrar no puede ser un agujero en la guarda de reescritura: el bloque pelado es TODO
    juicio del extractor (no había chequeo), así que sus bullets cuentan como los de prosa y una
    corrección a mano ahí adentro se protege igual que en el bloque marcado."""
    _con_txt(toy_vault, "sin el simbolo")
    d = extraccion()
    d["salvedades"] = ["la Fig. 3 es difícil de leer"]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    dest.write_text(dest.read_text(encoding="utf-8")
                    .replace(cfg.SALVEDAD_MARCAS[1], cfg.SALVEDAD_MARCA_LEGACY)
                    .replace("- la Fig. 3 es difícil de leer",
                             "- la Fig. 3 es ilegible en la copia del editor"), encoding="utf-8")
    antes = dest.read_text(encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert dest.read_text(encoding="utf-8") == antes
    assert [b for b, _m in r["rehusadas"]] == [BIB] and "REESCRIBIRÍA" in r["rehusadas"][0][1]


def test_453e_la_escotilla_de_la_estructurada_es_por_TEXTO_y_no_por_forma(toy_vault):
    """#453 — el bullet que se va PORQUE se estructuró no es un borrado: su texto sigue en la nota,
    dentro de la estructurada. Lo decide el TEXTO, no la forma — una estructurada cualquiera no
    amnistía cualquier prosa, y un bullet vacío no amnistía nada."""
    d = {"salvedades": [{"tipo": "txt_pierde", "cadena": "ζ",
                         "evidencia": "la Fig. 3 es difícil de leer en la copia del editor"},
                        "otra prosa suelta"]}
    assert hv._estructurada("- la Fig. 3 es difícil de leer", d), "el texto vive en `evidencia`"
    assert hv._estructurada("- ζ", d), "y en cualquier campo string de la estructurada"
    assert not hv._estructurada("- una prosa que nadie estructuró", d)
    assert not hv._estructurada("- otra prosa suelta", {"salvedades": ["otra prosa suelta"]}), \
        "una salvedad en PROSA no amnistía: la que se estructuró es un dict"
    assert not hv._estructurada("-   ", d), "el bullet vacío no amnistía nada"
    # ⚠ y el campo que NO es string se saltea: `pdf_paginas` lleva un entero, y el vocabulario de
    # `SALVEDAD_TIPOS` es abierto en sus valores (la prosa del extractor entra por cualquier clave)
    assert not hv._estructurada("- 17", {"salvedades": [{"tipo": "pdf_paginas", "n": 17}]})
    assert not hv._estructurada("- algo", {}), "sin salvedades no hay contraparte"


def test_457_la_vista_CON_LENTE_se_puede_re_estampar_sin_enfasis(toy_vault):
    """⛔ #457 — `section_span` devuelve hasta el próximo `## `, así que la sección de la vista
    incluía su `### Lente` y `salvedades_span` encontraba **dos** bloques: devolvía `None`, había
    marcas, y el re-estampado rehusaba la nota culpando a «prosa que no escribió el cosechador» —
    que sí la había escrito él. Medido: 2 notas (`2001HyvarinenKarhunenOja`, `2011PLoSO...627594P`),
    las dos únicas propuestas de `--propose-pdf-leido` que no se podían cobrar por ningún camino.

    Es el simétrico de #239: con `enfasis` la unidad es la sub-sección, así que sin él la unidad es
    la vista MENOS sus lentes."""
    _con_txt(toy_vault, "sin el simbolo")
    base = extraccion()
    base["salvedades"] = ["prosa de la vista"]
    dest = sembrar(toy_vault, base)
    hv.harvest("test_star")
    # la sub-sección de la segunda lectura, con su propio bloque (#239): la nota queda con DOS
    dest.write_text(dest.read_text(encoding="utf-8").rstrip("\n")
                    + f"\n\n### Lente — ruido\n\n{cfg.SALVEDAD_MARCAS[1]}\n\n"
                      "- prosa de la lente\n", encoding="utf-8")
    assert dest.read_text(encoding="utf-8").count(cfg.SALVEDAD_MARCAS[1]) == 2, "dos bloques"

    # el re-estampado de la vista SIN enfasis ya no rehúsa, y no toca el bloque de la lente
    base["salvedades"] = ["prosa de la vista", "una salvedad nueva de la vista"]
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(base), encoding="utf-8")
    r = hv.restamp_salvedades("test_star", paper=BIB)
    body = dest.read_text(encoding="utf-8")
    assert r["rehusadas"] == [] and r["tocadas"] == [BIB]
    assert "una salvedad nueva de la vista" in body
    assert "prosa de la lente" in body, "el bloque de la lente no se toca"
    assert body.count(cfg.SALVEDAD_MARCAS[1]) == 2, "y sigue habiendo dos bloques, cada uno el suyo"


def test_457_el_dolar_suelto_se_ESCAPA_y_la_matematica_no(toy_vault):
    """⛔ #457 — el `$` de Obsidian es el `|` de una celda (#240): abre matemática y se empareja con
    el siguiente `$` de la nota. Medido: la línea de copyright de IEEE en `2004ISPL...11..470D`, una
    nota con **31** `$` más; el re-estampado proponía QUITAR el escape que la nota ya tenía, y era la
    única diferencia entre esa nota y su render."""
    _con_txt(toy_vault, "sin el simbolo")
    d = extraccion()
    d["salvedades"] = ["copyright: 1070-9908/04$20.00 © 2004 IEEE",
                       "la amplitud es $K = 2.5$ m/s"]
    dest = sembrar(toy_vault, d)
    hv.harvest("test_star")
    body = dest.read_text(encoding="utf-8")
    assert r"1070-9908/04\$20.00" in body, "el `$` suelto va escapado"
    assert "$K = 2.5$" in body, "⛔ y la matemática NO se toca: escaparla cambiaría la fórmula"


def test_457_la_seccion_de_una_vista_SIN_enfasis_termina_en_su_primera_lente():
    """#457 — el simétrico de #239, aislado: con `enfasis` la unidad es la sub-sección, así que sin
    él la unidad es la vista MENOS sus lentes. Sin esto la misma vista tiene dos bloques de
    salvedades y no se puede direccionar ninguno."""
    con = "## Vista — X\n\ncuerpo\n\n### Lente — ruido\n\notra cosa\n"
    assert hv._view_without_lenses(con) == con.index("### Lente")
    sin = "## Vista — X\n\ncuerpo\n"
    assert hv._view_without_lenses(sin) == len(sin), "sin lentes, la sección entera"



def test_456_los_DOS_EJES_de_pdf_leido_en_un_PDF_reemplazado(toy_vault):
    """⛔ #456 — `pdf_leido` conflagaba «qué se leyó» con «qué hay en disco», y en un PDF REEMPLAZADO
    —la población que creó #436— las dos cosas no coinciden, así que **no había valor correcto**:
    medido, **27 salvedades** cuyo campo diría `publisher` (lo que hay en disco) y cuya propia
    evidencia dice *preprint* (lo que se leyó), y declarar `eprint` hacía que el chequeo la
    RECHAZARA. El hecho verdadero «esta vista se leyó del preprint» no era expresable en el tipo.

    Con los dos ejes se escribe entera, y el chequeo dice lo que `_paginacion` (#436) ya marca del
    lado de la extracción: **la vista es anterior al reemplazo, sus localizadores son del documento
    viejo.**"""
    _con_pdf(toy_vault)
    firma = [{"fecha": "2026-09-12", "source": "publisher", "sha": "a", "sha_anterior": "b"}]
    sembrar(toy_vault, extraccion(), fm_extra={"pdf_source": "publisher", "pdf_reemplazo": firma})
    ok, det = hv.check_salvedad(BIB, {"tipo": "pdf_leido", "documento": "publisher",
                                      "leido": "eprint",
                                      "evidencia": "marca de agua «arXiv:0704.3841v1 …»"})
    assert ok is True, "el eje del disco es el que se verifica, y coincide"
    assert "ANTES del reemplazo del 2026-09-12" in det and "documento viejo" in det
    # el mismo documento en los dos ejes: se dice, sin inventar una caducidad
    assert "ese mismo documento" in hv.check_salvedad(
        BIB, {"tipo": "pdf_leido", "documento": "publisher", "leido": "publisher"})[1]
    # sin firma del reemplazo no consta cuándo cambió (#441), y eso se declara
    sembrar(toy_vault, extraccion(), fm_extra={"pdf_source": "publisher"})
    assert "no declara `pdf_reemplazo`" in hv.check_salvedad(
        BIB, {"tipo": "pdf_leido", "documento": "publisher", "leido": "eprint"})[1]
    # y el eje nuevo es vocabulario CERRADO, como el otro (#296)
    assert hv.check_salvedad(BIB, {"tipo": "pdf_leido", "documento": "publisher",
                                   "leido": "preprint"})[0] is None
    # ⚠ y es OPCIONAL: sin declararlo, el detalle no dice nada de la vista (no la inventa)
    _ok, sin_eje = hv.check_salvedad(BIB, {"tipo": "pdf_leido", "documento": "publisher"})
    assert "vista" not in sin_eje


def test_456_la_propuesta_emite_LOS_DOS_EJES_cuando_no_coinciden(toy_vault):
    """#456 — antes esta población salía como «la salvedad quedó VIEJA» y sin entrada para pegar,
    porque no había forma de escribirla; ahora se propone entera. ⚠ Sólo con `pdf_reemplazo`: sin la
    firma no consta cuándo cambió el documento, así que sigue siendo una corrección, no un valor."""
    _con_pdf(toy_vault)
    d = extraccion()
    d["salvedades"] = ["El PDF en disco es el PREPRINT de arXiv (marca al margen)."]
    firma = [{"fecha": "2026-09-12", "source": "publisher", "sha": "a", "sha_anterior": "b"}]
    sembrar(toy_vault, d, fm_extra={"pdf_source": "publisher", "pdf_reemplazo": firma})
    assert [(doc, leido) for _j, _b, _t, doc, _m, leido in hv.propose_pdf_leido("test_star")] == \
        [("publisher", "eprint")], "los dos ejes, cada uno con su verdad"
    # sin la firma, sigue siendo «quedó VIEJA»
    sembrar(toy_vault, d, fm_extra={"pdf_source": "publisher"})
    props = hv.propose_pdf_leido("test_star")
    assert props[0][3] == "" and "quedó VIEJA" in props[0][4]
    # ⚠ y al revés —la prosa dice *publicado* y en disco está el preprint— tampoco hay segundo eje
    # que proponer: `publicado` no distingue `publisher` de `ads`, así que sigue siendo corrección
    d["salvedades"] = ["El PDF en disco es la copia del editor."]
    sembrar(toy_vault, d, fm_extra={"pdf_source": "eprint", "pdf_reemplazo": firma})
    (cfg.FULLTEXT / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "test_star" / f"{BIB}.txt").write_text(
        "arXiv:2001.00001v1 [astro-ph.EP] 1 Jan 2020\n", encoding="utf-8")
    props = hv.propose_pdf_leido("test_star")
    assert props and props[0][5] == "" and "quedó VIEJA" in props[0][4]


def test_456_el_printer_emite_el_segundo_eje_aunque_el_primero_no_se_pueda_decidir(toy_vault, capsys):
    """#456 — entre `publisher` y `ads` no elige un script (#296), pero eso no es razón para perder
    el eje que SÍ se sabe: la propuesta sale con `leido` puesto y el otro a elección."""
    j = cfg.EXTRACCION / "s" / "x.json"
    hv.print_pdf_leido([(j, "2020X", "El PDF …", "", "", "eprint")])
    out = capsys.readouterr().out
    assert '"leido": "eprint"' in out and "publisher|ads" in out and "elegí vos" in out


def test_462_la_propuesta_muestra_la_CLAUSULA_no_el_arranque_del_bullet(toy_vault):
    """⛔ #462 — validando #456, las propuestas eran CORRECTAS y el extracto las hacía parecer lo
    contrario: la evidencia decía *preprint* y el `documento` propuesto decía *publisher*. La
    cláusula que decidió está 400 caracteres después. Medido: **10 de 37** propuestas, las 10 bien
    clasificadas. El operador no podía distinguir «la cláusula lo decidió» de «el detector se
    equivocó» sin abrir el JSON."""
    _con_pdf(toy_vault)
    d = extraccion()
    d["salvedades"] = ["Esta vista se leyó del preprint de arXiv (marca de agua). "
                       + "Relleno de la salvedad. " * 20
                       + "⚠ Actualizado: el PDF en disco es hoy la copia del editor."]
    sembrar(toy_vault, d, fm_extra={"pdf_source": "publisher"})
    [(_j, _b, texto, doc, _m, _l)] = hv.propose_pdf_leido("test_star")
    assert doc == "publisher"
    assert texto.startswith("⚠ Actualizado"), "se muestra la cláusula que produjo la clase"
    assert "se leyó del preprint" not in texto


# ── #478 · la tabla derivada declara su cobertura ─────────────────────────────────────────────

def test_la_tabla_de_documento_CUBRE_el_vocabulario_o_declara_lo_que_deja_afuera():
    """#478 — `_DOC_DE_FUENTE` mapea desde `PDF_SOURCE_OK`, y `web` queda afuera a propósito: un
    snapshot no tiene testigo, así que sale **no evaluable con su motivo** (D-43). El problema era
    que esa decisión vivía sólo en un comentario: sin este cruce, el día que el vocabulario gane un
    quinto valor ese valor cae por el mismo `.get()` y no hay cómo distinguir «deliberadamente no
    evaluable» de «se olvidaron» — la confusión que D-43 existe para no producir.

    ⛔ El assert es de PARTICIÓN, no de inclusión: `claves ⊆ vocabulario` ya se cumplía y no habría
    cazado nada. Lo que tiene que romper es el vocabulario que CRECE."""
    cubiertas, fuera = set(hv._DOC_DE_FUENTE), set(hv._SIN_TESTIGO)
    assert cubiertas | fuera == set(cfg.PDF_SOURCE_OK), (
        "un valor de `PDF_SOURCE_OK` sin lugar en la tabla ni en su complemento declarado")
    assert not (cubiertas & fuera), "un valor no puede estar cubierto Y declarado afuera"
    assert set(hv._DOC_DE_FUENTE.values()) == {"preprint", "publicado"}, (
        "el eje que los testigos deciden tiene dos valores (#452)")


def test_494_restamp_exact_text_sustituye_una_vez_y_lista_el_resto(toy_vault):
    """⛔ #494 — cambiar el localizador dentro de una salvedad ES reescribir prosa ya escrita, y
    `restamp_salvedades` lo rehúsa por diseño (#453), así que la operación que repagina no podía
    cerrar su propio último paso: medido en la repaginación real, las notas hubo que arreglarlas
    por fuera (90 salvedades en 35 notas). La sustitución es por texto EXACTO y sólo si aparece
    **una** vez; dos o ninguna significa que alguien lo editó, y entonces se lista (18 medidas)."""
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    nota = cfg.PAPERS / "2020Exacto.md"
    nota.write_text("---\nbibcode: 2020Exacto\n---\n\n- la cita cae en (p. 3)\n- y otra en (p. 9)\n",
                    encoding="utf-8")
    r = hv.restamp_exact_text("2020Exacto", [("la cita cae en (p. 3)", "la cita cae en (p. 2010)")])
    assert r["cambiados"] == 1 and not r["fuera"]
    assert "(p. 2010)" in nota.read_text(encoding="utf-8")
    fuera = hv.restamp_exact_text("2020Exacto", [("un texto que no está", "otro")])
    assert fuera["cambiados"] == 0 and "0 vez/veces" in fuera["fuera"][0][1]
    assert hv.restamp_exact_text("2020NoExiste", [("x", "y")])["fuera"][0][1] == \
        "la nota del paper no existe"


def test_494_restamp_view_locators_solo_toca_el_token_del_paquete(toy_vault):
    """La celda *Localizador* de la `## Vista` la copió la máquina del JSON (#454): re-estampa
    ACOTADA (doctrina de #453), anclada en la cita y sólo si el token sigue siendo el que el
    paquete leyó — la celda corregida a mano se lista y se deja."""
    import json as _j
    cita = "which requires the latent signals to be whitened before the model can be identified"
    (cfg.EXTRACCION / "tema").mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / "tema" / "2020Vista.json").write_text(
        _j.dumps({"bibcode": "2020Vista", "vista": {"sujeto": "tema", "tipo": "theme"}}),
        encoding="utf-8")
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    nota = cfg.PAPERS / "2020Vista.md"
    nota.write_text(f"---\nbibcode: 2020Vista\n---\n\n## Vista — tema\n\n"
                    f"| Qué | Valor | Localizador |\n|---|---|---|\n| x | «{cita}» | p. 4 |\n",
                    encoding="utf-8")
    r = hv.restamp_view_locators("tema", paper="2020Vista",
                                 cambios=[(f"«{cita}»", "p. 4", "p. 2010")])
    assert r["cambiados"] == 1 and "| p. 2010 |" in nota.read_text(encoding="utf-8")
    viejo = hv.restamp_view_locators("tema", paper="2020Vista",
                                     cambios=[(f"«{cita}»", "p. 4", "p. 2011")])
    assert viejo["cambiados"] == 0 and "ya no está adyacente" in viejo["fuera"][0][1]


def test_501_restamp_view_locators_no_toma_el_prefijo_de_la_celda_por_el_token(toy_vault):
    """⛔ #501 — con la ventana cortada a 80 fijos, una celda `p. 13` en el borde se leía `p. 1`, y
    un JSON que traía `p. 1` la «re-estampaba» dejando `p. 20103`. El token es el número entero."""
    import json as _j
    cita = "which requires the latent signals to be whitened before the model can be identified"
    (cfg.EXTRACCION / "tema").mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / "tema" / "2020Vista.json").write_text(
        _j.dumps({"bibcode": "2020Vista", "vista": {"sujeto": "tema", "tipo": "theme"}}),
        encoding="utf-8")
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    nota = cfg.PAPERS / "2020Vista.md"
    nota.write_text(f"---\nbibcode: 2020Vista\n---\n\n## Vista — tema\n\n"
                    f"| Qué | Valor | Localizador |\n|---|---|---|\n"
                    f"| x | «{cita}» | " + "y" * 70 + " | p. 13 |\n", encoding="utf-8")
    r = hv.restamp_view_locators("tema", paper="2020Vista",
                                 cambios=[(f"«{cita}»", "p. 1", "p. 2010")])
    assert r["cambiados"] == 0 and "| p. 13 |" in nota.read_text(encoding="utf-8"), r


def test_AUD470_render_view_escapa_el_dolar_suelto_de_toda_la_prosa():
    """AUD-470 — #457 sólo cubría las salvedades; la regla es «cualquier prosa que va a una nota»:
    el `$` suelto se empareja con el siguiente `$` de la nota y arrastra todo a modo matemático."""
    out = hv.render_view("ica", {
        "aporte": "cuesta US$20", "hueco": "precio $5", "ejes": {"rv": "vale $3"},
        "ground_truth": [{"que": "costo $1", "valor": "v", "linea": "p. 1"}]})
    for esc in (r"US\$20", r"precio \$5", r"vale \$3", r"costo \$1"):
        assert esc in out, (esc, out)
    assert "$x$" in hv.render_view("ica", {"aporte": "mide $x$"}), "la matemática no se toca"


def test_AUD470_las_ayudas_de_lectura_escapan_el_dolar(toy_vault):
    """AUD-470 — abstract transcripto, conclusiones y traducciones: prosa que va a la nota. El
    abstract que llega por acá lo transcribió el modelo del PDF (no es el verbatim de catálogo), y
    escapar un `$` no cambia lo que se ve."""
    mk_note(cfg.PAPERS, "2020X", {"tags": ["paper"]}, "## Vista — ica\n")
    dest = cfg.PAPERS / "2020X.md"
    hv.stamp_reading_aids(dest, {"abstract": "costs US$20", "abstract_es": "cuesta US$20",
                                 "conclusiones": "a $5 fee", "conclusiones_es": "una tasa de $5"})
    t = dest.read_text(encoding="utf-8")
    for esc in (r"costs US\$20", r"cuesta US\$20", r"a \$5 fee", r"tasa de \$5"):
        assert esc in t, (esc, t)


# ── #506 · `ica` no es la vista de `ica-ruido`, ni `ruido` la lente de `ruido-rosa` ───────────────

def test_lens_span_no_confunde_lentes_prefijo():
    """El mismo corte que `section_start` para `### Lente — <énfasis>`: era un `find` pelado."""
    sec = "## Vista — ica\n\n### Lente — ruido-rosa\n\nrosa\n"
    assert hv._lens_span(sec, "ruido") is None
    sec += "\n### Lente — ruido\n\nblanco\n"
    ini, fin = hv._lens_span(sec, "ruido")
    assert sec[ini:fin].startswith("### Lente — ruido\n") and "rosa" not in sec[ini:fin]


def test_write_view_section_escribe_ica_sin_tocar_ica_ruido(tmp_path):
    """Regresión del caso medido (#506): la nota sólo tiene la vista redactada de `ica-ruido`;
    cosechar `ica` tiene que AGREGAR su sección, no rehusar ni pisar la otra."""
    dest = tmp_path / "2014ISPM...31...18A.md"
    dest.write_text("---\nbibcode: x\n---\n# X\n\n## Vista — ica-ruido\n\nprosa redactada\n",
                    encoding="utf-8")
    assert hv.write_view_section(dest, "ica", "## Vista — ica\n\nnueva\n", theme=True) is True
    t = dest.read_text(encoding="utf-8")
    assert "prosa redactada" in t and "## Vista — ica\n\nnueva" in t

@pytest.mark.parametrize("extra", [[], ["--paper", BIB]])
def test_507_el_dry_run_de_la_COSECHA_no_escribe_nada_y_anuncia_lo_que_la_real_escribe(
        toy_vault, monkeypatch, capsys, extra):
    """#507 — `--dry-run` sólo llegaba a `--restamp-salvedades`: la cosecha normal lo IGNORABA y
    escribía frontmatter, sección, el `.txt` traído al slug y el registro (medido: 5 archivos, +177
    líneas en una «previsualización»). Ida: el árbol entero queda igual. Vuelta: sin el flag se
    escribe lo que el dry-run anunció."""
    from conftest import tree_digest
    otro = toy_vault.FULLTEXT / "otra_estrella"
    otro.mkdir(parents=True, exist_ok=True)
    (otro / f"{BIB}.txt").write_text("texto del paper\n", encoding="utf-8")
    sembrar(toy_vault)
    antes = tree_digest(toy_vault.ROOT)
    monkeypatch.setattr(sys, "argv", ["harvest_views.py", "test_star", "--dry-run", *extra])
    assert hv.main() == 0
    seco = capsys.readouterr().out
    assert tree_digest(toy_vault.ROOT) == antes, "un --dry-run no escribe un byte"
    assert "1 cosechadas" in seco and "1 .txt traídos" in seco and "dry-run" in seco
    assert f"(dry-run) {BIB}.md: +" in seco, "dice cuánto cambiaría la nota"
    monkeypatch.setattr(sys, "argv", ["harvest_views.py", "test_star", *extra])
    assert hv.main() == 0
    assert "1 cosechadas" in capsys.readouterr().out
    assert (toy_vault.FULLTEXT / "test_star" / f"{BIB}.txt").exists()
    assert any(p["paso"] == "harvest_views" for p in cfg.load_cadena("test_star"))


@pytest.mark.parametrize("modo", [["--restamp-salvedades"], ["--propose-pdf-leido"]])
def test_507_los_otros_modos_con_dry_run_tampoco_escriben(toy_vault, monkeypatch, modo):
    """#507 — la regla es POR MODO: cada modo del script que declara `--dry-run` lo respeta."""
    from conftest import tree_digest
    sembrar(toy_vault)
    antes = tree_digest(toy_vault.ROOT)
    monkeypatch.setattr(sys, "argv", ["harvest_views.py", "test_star", *modo, "--dry-run"])
    assert hv.main() == 0
    assert tree_digest(toy_vault.ROOT) == antes


def test_526_force_NO_re_escribe_lo_que_una_verificacion_REFUTO(toy_vault, capsys):
    """#526 — la nota se corrigió contra el PDF, pero el JSON inmutable (#311) conserva el texto
    refutado: `--force` lo volvía a escribir en la vista. Con `_refutado` la sección no se toca."""
    data = extraccion(aporte="usa una grilla aleatoria",
                      _refutado=[{"texto": "grilla aleatoria", "por": "x.verif#abc",
                                  "motivo": "adaptativa", "fecha": "2026-09-24"}])
    dest = sembrar(toy_vault, data, body="## Vista — Estrella Test\n\nGrilla adaptativa.\n",
                   fm_extra={"vistas": [{"sujeto": "Estrella Test", "tipo": "star",
                                         "fecha": "2026-01-01"}]})
    hv.harvest("test_star", force=True)
    assert "Grilla adaptativa." in dest.read_text(encoding="utf-8")
    # devuelto por el validador: la sección se rehusaba pero `vistas[]` se RE-FECHABA (#395),
    # declarando una lectura que no se escribió
    v = cfg.split_fm(dest.read_text(encoding="utf-8"))["vistas"][0]
    assert v["fecha"] == "2026-01-01" and "previa" not in v
    assert "grilla aleatoria" not in dest.read_text(encoding="utf-8")
    assert "la vista NO se re-escribe" in capsys.readouterr().out
    # y el re-estampado acotado de salvedades (#453), el otro camino JSON → nota, tampoco
    sembrar(toy_vault, extraccion())          # la vista cosechada sin salvedades
    hv.harvest("test_star")
    data["salvedades"] = ["la grilla aleatoria no es de la fuente"]   # AGREGAR pasa (#453)
    (cfg.EXTRACCION / "test_star" / f"{BIB}.json").write_text(json.dumps(data), encoding="utf-8")
    r = hv.restamp_salvedades("test_star")
    assert [b for b, _ in r["rehusadas"]] == [BIB] and not r["tocadas"]
