"""replace_pdf: el comando que faltaba para cerrar el backlog más grande del repo (#436).

Qué protege este archivo, en una línea: **todo backlog que el lint nombra tiene que tener una salida
ejecutable**, y la de #298 —161 de 264 notas de paper en una bóveda real— mandaba a
`fetch_pdf --force`, que no aplica al caso normal (el PDF publicado está tras paywall y lo trae el
usuario). Medido reemplazando 11 preprints a mano, desde un script de scratch no versionado.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import lib_config as cfg
import lib_blocks as lb
import replace_pdf as rp
from conftest import mk_note


PREPRINT = b"%PDF-1.4\nel preprint, con su marca al margen\n"
EDITOR = b"%PDF-1.5\nla copia del editor, paginada por volumen\n"


def _copia(slug: str, bib: str, datos: bytes = PREPRINT) -> Path:
    (cfg.PDFS / slug).mkdir(parents=True, exist_ok=True)
    p = cfg.PDFS / slug / f"{bib}.pdf"
    p.write_bytes(datos)
    (cfg.FULLTEXT / slug).mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / slug / f"{bib}.txt").write_text("texto del preprint\n", encoding="utf-8")
    return p


def _nota(bib: str, **extra) -> Path:
    fm = {"bibcode": bib, "tags": ["paper"], "stars": ["Test"],
          "pdf": f"../../raw/pdfs/gj_581/{bib}.pdf", "pdf_source": "eprint",
          "eprint_version": "v1", **extra}
    return mk_note(cfg.PAPERS, bib, fm, "# p\n\n## Abstract\n\nx\n")


def _entrante(tmp_path, datos: bytes = EDITOR) -> Path:
    f = tmp_path / "entrante.pdf"
    f.write_bytes(datos)
    return f


def _paginas(monkeypatch, saliente: int | None = 33, entrante: int | None = 33) -> None:
    """El conteo de páginas es la frontera con `pdfinfo` (#437): se fija por archivo, no se corre."""
    monkeypatch.setattr(rp.cfg, "pdf_page_count",
                        lambda pdf: ((entrante if Path(pdf).name == "entrante.pdf" else saliente), "")
                        if (entrante if Path(pdf).name == "entrante.pdf" else saliente) is not None
                        else (None, "sin `pdfinfo`"))


def test_las_copias_se_enumeran_POR_SLUG_no_por_la_que_resuelve(toy_vault, tmp_path, monkeypatch):
    """⛔ #436 — la unidad del reemplazo es el PAPER y la de almacenamiento es el SLUG: un reemplazo
    que escribe una copia deja las otras leyendo el documento viejo. `cfg.pdf_slug` resuelve UNA
    (precedencia declarada, #305), que es lo correcto para leer y lo incorrecto para escribir.
    Medido: 2 de los 11 papers reemplazados vivían bajo dos slugs."""
    _copia("gj_581", "2010D"); _copia("rv-doppler", "2010D")
    _nota("2010D")
    corridas = []
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    _paginas(monkeypatch)
    monkeypatch.setattr(rp.subprocess, "run", lambda cmd, **k: corridas.append(cmd))
    assert [p.parent.name for p in rp.pdf_copies("2010D")] == ["gj_581", "rv-doppler"]
    r = rp.replace("2010D", _entrante(tmp_path), "publisher", "el editor lo mandó por mail")
    assert r["slugs"] == ["gj_581", "rv-doppler"]
    for slug in ("gj_581", "rv-doppler"):
        assert (cfg.PDFS / slug / "2010D.pdf").read_bytes() == EDITOR, slug
    # ⛔ y el `.txt` de CADA slug se re-extrae **acotado al bibcode** (#436): sin `--bibcode`, el
    # `--force` vencería las anclas de fuente de todos los papers del tema
    assert len(corridas) == 2 and r["txts"] and len(r["txts"]) == 2
    for cmd, slug in zip(corridas, ("gj_581", "rv-doppler")):
        assert cmd[1].endswith("extract_fulltext.py") and cmd[2] == slug
        assert cmd[3:] == ["--bibcode", "2010D", "--force"], cmd


def test_rehusa_el_MISMO_archivo_y_el_preprint_declarado_publicado(toy_vault, tmp_path, monkeypatch):
    """Las dos rehusadas que pasaron en la sesión medida: uno de los archivos entregados **era el
    mismo preprint** (sha igual: no hay nada que reemplazar, y seguir vencería los pares anclados
    por nada) y otro venía con `arXiv:astro-ph/0209466v1` impreso al margen.

    ⛔ La segunda es la que importa: con `pdf_source: eprint` una discrepancia numérica es candidata
    a **diferencia de versión** (#57), así que archivar un preprint como publicado hace que la nota
    mande a re-verificar contra el documento equivocado."""
    _copia("gj_581", "2010D"); _nota("2010D")
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    _paginas(monkeypatch)
    mismo = _entrante(tmp_path, PREPRINT)
    with pytest.raises(rp.ReplaceError, match="BYTE A BYTE"):
        rp.replace("2010D", mismo, "publisher", "m")
    monkeypatch.setattr(rp, "first_pages_text",
                        lambda _p: "arXiv:astro-ph/0209466v1  12 Oct 2002")
    with pytest.raises(rp.ReplaceError, match="marca de arXiv"):
        rp.replace("2010D", _entrante(tmp_path), "publisher", "m")
    # el mismo archivo declarado `eprint` NO es contradicción: es un preprint, y se dice
    assert [e for e in rp.check_incoming("2010D", _entrante(tmp_path), "eprint")] == []
    # y el vocabulario es cerrado (#296): un valor fuera de lista caería por el `else` de todo
    # `== "eprint"` en silencio, y ese campo DECIDE lecturas
    assert any("vocabulario" in e for e in
               rp.check_incoming("2010D", _entrante(tmp_path), "revista"))
    assert (cfg.PDFS / "gj_581" / "2010D.pdf").read_bytes() == PREPRINT, \
        "una rehusada no escribe NADA"
    # las dos rehusadas de ENTRADA, antes de mirar el disco de la bóveda: el archivo que no está y
    # el que no es un PDF (AUD-161: los fetchers copiaban sin mirar el magic y propagaban un
    # truncado a otro slug). Cada una corta ahí: no tiene sentido hashear lo que no se puede leer.
    assert rp.check_incoming("2010D", tmp_path / "no-existe.pdf", "publisher") == \
        [f"{tmp_path / 'no-existe.pdf'}: no existe"]
    no_pdf = tmp_path / "cosa.pdf"
    no_pdf.write_bytes(b"<html>paywall</html>")
    assert len(rp.check_incoming("2010D", no_pdf, "publisher")) == 1
    assert "%PDF" in rp.check_incoming("2010D", no_pdf, "publisher")[0]


def test_el_frontmatter_queda_coherente_con_el_documento_nuevo(toy_vault, tmp_path, monkeypatch):
    """⛔ La guarda de #383 (un `pdf_sha` distinto anula `pdf_source`/`eprint_version`) **no puede
    disparar** en la mayoría de la bóveda: medido, 247 notas con PDF y sólo 25 con `pdf_sha`, así
    que en las otras 222 el reemplazo es invisible y la nota sigue diciendo `pdf_source: eprint`
    sobre un PDF de editor. Acá el sha se escribe SIEMPRE, y `eprint_version` se va con el
    documento que describía (#383 bloquea editor + `eprint_version`)."""
    _copia("gj_581", "2010D"); nota = _nota("2010D")
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    _paginas(monkeypatch)
    monkeypatch.setattr(rp.subprocess, "run", lambda *a, **k: None)
    rp.replace("2010D", _entrante(tmp_path), "publisher", "lo trajo el usuario")
    fm = cfg.split_fm(nota.read_text(encoding="utf-8"))
    assert fm["pdf_source"] == "publisher"
    assert fm["pdf_sha"] == lb.sha10(EDITOR)
    assert fm["eprint_version"] is None, "el valor viejo describía el documento que ya no está"
    # y la nota que NO tenía `pdf_sha` (la población de 222) lo gana: es lo que hace que el
    # próximo reemplazo SÍ lo detecte solo
    assert "pdf_sha" not in _nota("2011X").read_text(encoding="utf-8")


def test_reemplazar_por_OTRO_eprint_conserva_la_version(toy_vault, tmp_path, monkeypatch):
    """`eprint_version` se va con el documento que describía, **salvo** que el nuevo también sea un
    eprint: ahí el campo sigue siendo el eje correcto (qué v se leyó) y borrarlo perdería la
    salvedad que #57 hace posible. La guarda es `source != "eprint"`, no «siempre»."""
    _copia("gj_581", "2010D"); nota = _nota("2010D")
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "arXiv:1234.5678v2")
    _paginas(monkeypatch)
    monkeypatch.setattr(rp.subprocess, "run", lambda *a, **k: None)
    rp.replace("2010D", _entrante(tmp_path), "eprint", "la v2, que corrige la tabla 3")
    fm = cfg.split_fm(nota.read_text(encoding="utf-8"))
    assert fm["pdf_source"] == "eprint" and fm["eprint_version"] == "v1", \
        "no se inventa la versión nueva: la estampa el disco al re-extraer (#57)"


def test_el_slug_SIN_txt_no_se_re_extrae_y_la_nota_que_falta_se_AVISA(toy_vault, tmp_path,
                                                                      monkeypatch, capsys):
    """Dos degradaciones declaradas: un slug que tiene el PDF y no el `.txt` no tiene nada que
    re-extraer (y pedirlo haría rehusar a `extract_fulltext --bibcode`), y un PDF sin nota se
    reemplaza igual —la verdad de disco es la verdad— pero el frontmatter no se puede estampar y
    eso **se dice**, en vez de quedar como un reemplazo a medias silencioso."""
    _copia("gj_581", "2010D")
    (cfg.FULLTEXT / "gj_581" / "2010D.txt").unlink()
    corridas = []
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    _paginas(monkeypatch)
    monkeypatch.setattr(rp.subprocess, "run", lambda cmd, **k: corridas.append(cmd))
    r = rp.replace("2010D", _entrante(tmp_path), "publisher", "m")
    assert r["txts"] == [] and corridas == [], "sin `.txt` no se re-extrae nada"
    assert "no hay nota" in capsys.readouterr().out


def test_la_EXTRACCION_queda_marcada_des_paginada(toy_vault, tmp_path, monkeypatch):
    """⛔ El hueco que no tenía forma en ninguna parte: `raw/extraccion/**` es versionado y no
    regenerable (#311), así que después del reemplazo la bóveda tiene una extracción que cita
    `p. 5` de un documento que ya no está, mientras el PDF nuevo pagina por volumen (Cardoso 1998
    arranca en la 2009). Las citas textuales siguen bien —`contrast --validar` dio **0
    alteraciones** en las cinco notas tocadas— pero **todos los localizadores quedan mal**, y eso
    no lo levanta nadie: `verify-citations` chequea que la fuente lo diga y `--validar` que la
    cadena no esté alterada; las dos cosas son ciertas con la página apuntando a la nada.

    No se reescribe ni se borra: se MARCA, la misma forma que `sweep_external` deja como `_cambios`
    en el JSON de ground-truth (AUD-42)."""
    _copia("gj_581", "2010D"); _nota("2010D")
    (cfg.EXTRACCION / "gj_581").mkdir(parents=True, exist_ok=True)
    ext = cfg.EXTRACCION / "gj_581" / "2010D.json"
    ext.write_text(json.dumps({"bibcode": "2010D", "ground_truth": [
        {"que": "P_b", "valor": "5,37 d", "linea": "p. 5"}]}), encoding="utf-8")
    lente = cfg.EXTRACCION / "gj_581" / "2010D__ruido.json"
    lente.write_text(json.dumps({"bibcode": "2010D"}), encoding="utf-8")
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    _paginas(monkeypatch)
    monkeypatch.setattr(rp.subprocess, "run", lambda *a, **k: None)
    r = rp.replace("2010D", _entrante(tmp_path), "publisher", "versión del editor")
    assert len(r["extracciones"]) == 2, "también la de la lente (#371), que es otra lectura"
    marca = json.loads(ext.read_text(encoding="utf-8"))["_paginacion"]
    assert marca["pdf_sha"] == lb.sha10(EDITOR) and marca["pdf_sha_anterior"] == lb.sha10(PREPRINT)
    assert marca["motivo"] == "versión del editor", "el motivo viaja, como el `--reason` del triage"
    assert json.loads(ext.read_text(encoding="utf-8"))["ground_truth"][0]["linea"] == "p. 5", \
        "⛔ el localizador NO se reescribe: la extracción es versionada y no regenerable (#311)"
    # un JSON que no es un mapa (o que no parsea) se saltea nombrándolo: marcarlo a mano es mejor
    # que reventar en el medio de un reemplazo que ya copió archivos
    (cfg.EXTRACCION / "gj_581" / "2010D__lista.json").write_text("[1, 2]", encoding="utf-8")
    (cfg.EXTRACCION / "gj_581" / "2010D__roto.json").write_text("{no es json", encoding="utf-8")
    assert len(rp.stamp_depagination("2010D", "a" * 10, "b" * 10, "m")) == 2, \
        "sólo los dos mapas; el que no es mapa y el roto no se tocan"


def test_emite_el_ALCANCE_de_la_re_verificacion_listo_para_pegar(toy_vault, tmp_path, monkeypatch,
                                                                 capsys):
    """El número que decide cuándo pagar la ronda: 11 reemplazos vencieron **76** pares en 6 notas,
    ~7 de mediana, y extrapolado a los 70 de prioridad alta de esa bóveda es del orden de **500**.
    Hoy nadie podía saber cuántos eran sin hacerlo. Reporta y NO re-verifica: decidir cuándo pagar
    eso no es de este script."""
    _copia("gj_581", "2010D"); _nota("2010D")
    ficha = mk_note(cfg.STARS, "test_star", {"name": "Test", "slug": "test_star", "tags": ["star"]},
                    "# f\n\nEl período es 5,37 d [[2010D]].\n")
    filas = [lb.Row(n="1", claim="El período es 5,37 d", bibcode="2010D", verdict="soportada",
                    anchor="abc1234567", source_hash="0123456789", source_kind="pdf",
                    evidence='"5.37 d" (p. 5)'),
             lb.Row(n="2", claim="otra cosa", bibcode="2011X", verdict="soportada",
                    anchor="def1234567", source_hash="9876543210", source_kind="pdf",
                    evidence='"x" (p. 1)')]
    cfg.write_text_atomic(cfg.verif_sidecar(ficha), lb.render_verif_sidecar(
        ficha, lb.render_verif_table(filas)))
    assert rp.reverification_scope("2010D") == [(ficha, 1)]
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    _paginas(monkeypatch)
    monkeypatch.setattr(rp.subprocess, "run", lambda *a, **k: None)
    assert rp.main(["2010D", str(_entrante(tmp_path)), "--source", "publisher",
                    "--reason", "el editor"]) == 0
    salida = capsys.readouterr().out
    assert "ALCANCE DE LA RE-VERIFICACIÓN: 1 par" in salida
    assert "verify_fanout.py" in salida and "--fuentes 2010D" in salida, "listo para pegar"
    assert "2011X" not in salida, "el par de OTRA fuente no vence: su archivo no cambió"


def test_rehusa_el_bibcode_SIN_copia_en_disco(toy_vault, tmp_path, monkeypatch):
    """Esto REEMPLAZA: sin copia previa no hay nada que reemplazar, y la primera bajada tiene su
    propio comando. Rehusar es lo que evita que el script se use como un `fetch_pdf` paralelo que
    no registra nada de lo que `fetch_pdf` registra."""
    _nota("2010D")
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    _paginas(monkeypatch)
    with pytest.raises(rp.ReplaceError, match="no hay ningún PDF"):
        rp.replace("2010D", _entrante(tmp_path), "publisher", "m")
    assert rp.main(["2010D", str(_entrante(tmp_path)), "--source", "publisher",
                    "--reason", "m"]) == 2, "la rehusada sale 2, no 0"


def test_el_dry_run_no_escribe_NADA(toy_vault, tmp_path, monkeypatch, capsys):
    """La red 6 en su forma más barata: la modalidad que existe para ver el alcance antes de pagarlo
    no puede tocar el disco."""
    _copia("gj_581", "2010D"); nota = _nota("2010D")
    (cfg.EXTRACCION / "gj_581").mkdir(parents=True, exist_ok=True)
    ext = cfg.EXTRACCION / "gj_581" / "2010D.json"
    ext.write_text(json.dumps({"bibcode": "2010D"}), encoding="utf-8")
    antes = (nota.read_bytes(), ext.read_bytes(), (cfg.PDFS / "gj_581" / "2010D.pdf").read_bytes())
    corridas = []
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    _paginas(monkeypatch)
    monkeypatch.setattr(rp.subprocess, "run", lambda cmd, **k: corridas.append(cmd))
    assert rp.main(["2010D", str(_entrante(tmp_path)), "--source", "publisher",
                    "--reason", "m", "--dry-run"]) == 0
    assert (nota.read_bytes(), ext.read_bytes(),
            (cfg.PDFS / "gj_581" / "2010D.pdf").read_bytes()) == antes
    assert corridas == [], "⛔ tampoco re-extrae: `extract_fulltext --force` reescribe el `.txt`"
    salida = capsys.readouterr().out
    assert "dry-run" in salida
    assert "(ninguno" in salida, "sin notas verificadas el alcance se DICE, no queda en blanco"


def test_first_pages_text_lee_DOS_paginas_y_el_fallo_es_desconocido(toy_vault, tmp_path,
                                                                    monkeypatch):
    """El alcance son **dos páginas** (INV-29), el mismo que lee `cfg.arxiv_stamp`: la marca está en
    el margen de TODAS, así que dos alcanzan, y leer más levantaría los `arXiv:` de la bibliografía
    —que son de OTROS trabajos y volverían eprint a cualquier paper—.

    ⛔ Y un `pdftotext` que falta o falla devuelve `""` = **desconocido**, nunca «no tiene marca»:
    con lo segundo, un preprint se archivaría como publicado justo cuando la herramienta no está."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(PREPRINT)
    vistos = {}

    def _fake(cmd, **kw):
        vistos["cmd"] = cmd
        return type("R", (), {"returncode": 0, "stdout": "arXiv:1234.5678v1"})()
    monkeypatch.setattr(rp.subprocess, "run", _fake)
    assert rp.first_pages_text(pdf) == "arXiv:1234.5678v1"
    assert vistos["cmd"][:6] == ["pdftotext", "-layout", "-f", "1", "-l", "2"], vistos["cmd"]

    monkeypatch.setattr(rp.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "basura"})())
    assert rp.first_pages_text(pdf) == "", "un fallo no es «no hay marca»"

    def _falta(*a, **k):
        raise FileNotFoundError("pdftotext")
    monkeypatch.setattr(rp.subprocess, "run", _falta)
    assert rp.first_pages_text(pdf) == ""


# ── #437 · el rastro firmado y la copia que puede ser PEOR ───────────────────────────────────────

def test_el_reemplazo_queda_FIRMADO_en_la_nota_y_es_add_only(toy_vault, tmp_path, monkeypatch):
    """⛔ #437 — el docstring de v1.256.0 prometía `pdf_reemplazo` y el código no lo escribía: una
    sola aparición en todo el repo, la promesa. El `--reason` sobrevivía en `_paginacion` y en stdout,
    y la nota del paper —lo que viaja y lo que lee quien consume la afirmación— no decía que ese PDF
    se reemplazó ni por qué. Ese motivo es justo lo que hizo falta cuando hubo que REVERTIR uno."""
    _copia("gj_581", "2010D"); nota = _nota("2010D")
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    monkeypatch.setattr(rp.subprocess, "run", lambda *a, **k: None)
    _paginas(monkeypatch, saliente=33, entrante=33)
    rp.replace("2010D", _entrante(tmp_path), "publisher", "lo trajo el usuario por mail")
    fm = cfg.split_fm(nota.read_text(encoding="utf-8"))
    (r,) = fm["pdf_reemplazo"]
    assert r["motivo"] == "lo trajo el usuario por mail" and r["source"] == "publisher"
    assert r["sha_anterior"] == lb.sha10(PREPRINT) and r["sha"] == lb.sha10(EDITOR)
    assert r["paginas"] == "33 → 33"
    # add-only: un segundo reemplazo (otra copia) se APILA, no pisa la historia
    _paginas(monkeypatch, saliente=33, entrante=30)
    rp.replace("2010D", _entrante(tmp_path, b"%PDF-1.7\notra copia\n"), "publisher", "la v2 del editor")
    hist = cfg.split_fm(nota.read_text(encoding="utf-8"))["pdf_reemplazo"]
    assert [h["motivo"] for h in hist] == ["lo trajo el usuario por mail", "la v2 del editor"]
    assert hist[1]["sha_anterior"] == lb.sha10(EDITOR), "el segundo parte de donde quedó el primero"
    assert hist[1]["paginas"] == "33 → 30"


def test_AVISA_si_el_entrante_tiene_menos_paginas_y_no_rehusa(toy_vault, tmp_path, monkeypatch,
                                                              capsys):
    """El único reemplazo que hubo que revertir en la sesión medida: la copia de *Science Express*
    tiene **7 páginas y no trae los Supplementary Materials**, el preprint tiene **33**, y la ficha
    cita §S1.1. Sin marca de arXiv y con otro sha, pasaba las dos rehusadas.

    ⚠ Aviso, no rehúse: una copia del editor más corta puede ser legítima (sin la carta ni los
    apéndices duplicados); el que decide es quien mira. Y es la única de las señales que NO se puede
    reconstruir después — el PDF saliente está en disco sólo en ese instante."""
    _copia("gj_581", "2014R"); _nota("2014R")
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    monkeypatch.setattr(rp.subprocess, "run", lambda *a, **k: None)
    _paginas(monkeypatch, saliente=33, entrante=7)
    assert rp.main(["2014R", str(_entrante(tmp_path)), "--source", "publisher",
                    "--reason", "Science Express"]) == 0, "AVISA, no rehúsa"
    salida = capsys.readouterr().out
    assert "26 página(s) MENOS" in salida and "7 contra 33" in salida, salida
    assert "Supplementary" in salida
    assert (cfg.PDFS / "gj_581" / "2014R.pdf").read_bytes() == EDITOR, "el reemplazo ocurrió igual"
    # las tres salidas de `page_warning`, directo: más corto · no más corto · no evaluable (D-43)
    assert rp.page_warning(Path("a.pdf"), Path("entrante.pdf")) is not None
    _paginas(monkeypatch, saliente=7, entrante=33)
    assert rp.page_warning(Path("a.pdf"), Path("entrante.pdf")) is None, "más largo no avisa"
    _paginas(monkeypatch, saliente=33, entrante=33)
    assert rp.page_warning(Path("a.pdf"), Path("entrante.pdf")) is None, "igual no avisa"
    for saliente, entrante in ((None, 33), (33, None)):
        _paginas(monkeypatch, saliente=saliente, entrante=entrante)
        aviso = rp.page_warning(Path("a.pdf"), Path("entrante.pdf"))
        assert aviso and "no se pudieron comparar" in aviso and "pdfinfo" in aviso, \
            "sin conteo de CUALQUIERA de los dos NO es «no es más corto»: no evaluable con motivo"


# ── #440 · el backfill estampa las DOS mitades ───────────────────────────────────────────────────

def test_backfill_estampa_las_DOS_mitades_sin_tocar_el_pdf(toy_vault, tmp_path, monkeypatch, capsys):
    """⛔ #440 — los 15 reemplazos hechos a mano ANTES del comando quedaron con `pdf_source: publisher`
    y nada más: `pdf_reemplazo` en 0, `_paginacion` en 0 de 288, la categoría en `(0)` sobre una
    bóveda con 15 papers cuyos localizadores sí son del documento anterior. Las dos mitades de #437
    se disparan por `_paginacion` en la EXTRACCIÓN, y la guía mandaba backfillear la nota: la mitad
    que ningún chequeo mira. El fix era correcto e inerte justo donde se midió."""
    _copia("gj_581", "2010D", EDITOR); nota = _nota("2010D", pdf_source="publisher")
    (cfg.EXTRACCION / "gj_581").mkdir(parents=True, exist_ok=True)
    ext = cfg.EXTRACCION / "gj_581" / "2010D.json"
    ext.write_text(json.dumps({"bibcode": "2010D", "ground_truth": [{"que": "P", "linea": "p. 5"}]}),
                   encoding="utf-8")
    _paginas(monkeypatch, saliente=7, entrante=7)
    antes_pdf = (cfg.PDFS / "gj_581" / "2010D.pdf").read_bytes()
    assert rp.main(["2010D", "--backfill", "--source", "publisher", "--sha-anterior", "?",
                    "--reason", "reemplazado a mano el 2026-09-10"]) == 0
    assert (cfg.PDFS / "gj_581" / "2010D.pdf").read_bytes() == antes_pdf, "no toca el PDF"
    (r,) = cfg.split_fm(nota.read_text(encoding="utf-8"))["pdf_reemplazo"]
    assert r["sha_anterior"] == "?" and r["sha"] == lb.sha10(EDITOR) and r["paginas"] == "? → 7"
    assert r["motivo"] == "reemplazado a mano el 2026-09-10"
    marca = json.loads(ext.read_text(encoding="utf-8"))["_paginacion"]
    assert marca["pdf_sha_anterior"] == "?" and marca["pdf_sha"] == lb.sha10(EDITOR)
    assert "backfill" in capsys.readouterr().out
    # y las dos mitades ya son las que los dos lectores miran: el lint la levanta…
    assert cfg.extraction_depaginated("2010D")
    # …y firmada, el backfill rehúsa repetirse: es para el reemplazo ANTERIOR al comando
    assert rp.main(["2010D", "--backfill", "--source", "publisher", "--sha-anterior", "?",
                    "--reason", "otra vez"]) == 2
    assert "ya declara `pdf_reemplazo`" in capsys.readouterr().out


def test_backfill_rehusa_sin_nota_sin_pdf_y_con_source_fuera_de_vocabulario(toy_vault, monkeypatch,
                                                                              capsys):
    """Las tres rehusadas del backfill, cada una con su motivo: firma una nota (sin ella no hay
    dónde), declara que el PDF en disco ES el reemplazo (sin PDF no hay qué declarar), y el
    vocabulario de `pdf_source` es cerrado (#296)."""
    _paginas(monkeypatch)
    with pytest.raises(rp.ReplaceError, match="no hay nota"):
        rp.backfill("2010D", "publisher", "m")
    _nota("2010D", pdf_source="publisher")
    with pytest.raises(rp.ReplaceError, match="no hay ningún PDF"):
        rp.backfill("2010D", "publisher", "m")
    _copia("gj_581", "2010D", EDITOR)
    with pytest.raises(rp.ReplaceError, match="vocabulario"):
        rp.backfill("2010D", "revista", "m")
    r = rp.backfill("2010D", "publisher", "m", sha_anterior="abc1234567", dry_run=True)
    # sin git en el toy_vault, `auto` (el default, #441) rehúsa nombrando el motivo: no firma `?` solo
    with pytest.raises(rp.ReplaceError, match="no se pudo recuperar el sha anterior de git"):
        rp.backfill("2010D", "publisher", "m")
    assert r["sha_anterior"] == "abc1234567" and "pdf_reemplazo" not in _nota("2010D").read_text(encoding="utf-8")
    assert rp.main(["2010D", "--source", "publisher", "--reason", "m"]) == 2, "sin PDF ni --backfill"
    assert "falta el PDF" in capsys.readouterr().out


# ── #441 · el sha anterior está en git ───────────────────────────────────────────────────────────

from test_lib_config import _git, _repo_con_reemplazo  # noqa: E402 — fixtures git compartidas (#441)


def test_backfill_AUTO_firma_el_sha_de_git_y_rehusa_sin_historia(toy_vault, monkeypatch, capsys):
    """El default es `auto`: el backfill firma `sha_anterior` real sin que el operador lo busque, y
    si el archivo se agregó ya publicado (sin modificación) REHÚSA en vez de firmar `?` — no hubo
    reemplazo. Y si las copias por slug tenían shas distintos, lo declara y pide elegir."""
    pdf = _repo_con_reemplazo(toy_vault)
    nota = _nota("1998Cardoso", pdf_source="publisher")
    _paginas(monkeypatch, saliente=12, entrante=12)
    assert rp.main(["1998Cardoso", "--backfill", "--source", "publisher", "--reason", "editor"]) == 0
    (r,) = cfg.split_fm(nota.read_text(encoding="utf-8"))["pdf_reemplazo"]
    assert r["sha_anterior"] == "2b" * 5 and r["sha"] == lb.sha10(pdf.read_bytes())
    assert "sha_anterior 2b2b2b2b2b" in capsys.readouterr().out
    # agregado ya publicado: sin historia de modificación → rehúsa nombrando el motivo
    root = toy_vault.ROOT
    solo = cfg.PDFS / "ica" / "2005Solo.pdf"
    solo.write_bytes(b"%PDF-1.4\nunico\n"); _git(root, "add", "-A"); _git(root, "commit", "-q", "-m", "c")
    _nota("2005Solo", pdf_source="publisher")
    with pytest.raises(rp.ReplaceError, match="NO hubo reemplazo"):
        rp.backfill("2005Solo", "publisher", "m")
    # dos copias con shas anteriores DISTINTOS → declara y pide elegir
    otra = cfg.PDFS / "gj_581" / "1998Cardoso.pdf"; otra.parent.mkdir(parents=True, exist_ok=True)
    otra.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:" + "aa" * 32 + "\nsize 1\n")
    _git(root, "add", "-A"); _git(root, "commit", "-q", "-m", "d")
    otra.write_text(pdf.read_text()); _git(root, "add", "-A"); _git(root, "commit", "-q", "-m", "e")
    cfg.set_fm_scalar(nota, "pdf_reemplazo", "null")   # des-firmar para poder volver a probar
    with pytest.raises(rp.ReplaceError, match="shas DISTINTOS"):
        rp.backfill("1998Cardoso", "publisher", "m")


def test_backfill_AUTO_rehusa_si_el_padre_tiene_el_MISMO_sha_que_el_pdf_actual(toy_vault, monkeypatch):
    """La última modificación en git dejó un contenido que después se revirtió en el árbol de
    trabajo: el padre del último `M` es igual al archivo actual, o sea que no hay reemplazo que
    firmar, y decirlo es mejor que firmar `sha_anterior == sha`."""
    # blobs planos (no pointers): en un checkout real el archivo es el PDF y su sha256 ES el `oid`;
    # en el toy repo con pointers el archivo es el pointer, así que la igualdad sólo se puede
    # ejercitar con contenido plano
    _repo_con_reemplazo(toy_vault)
    root = toy_vault.ROOT
    pdf = cfg.PDFS / "ica" / "2007Plano.pdf"
    pdf.write_bytes(PREPRINT); _git(root, "add", "-A"); _git(root, "commit", "-q", "-m", "v1")
    pdf.write_bytes(EDITOR); _git(root, "add", "-A"); _git(root, "commit", "-q", "-m", "v2")
    pdf.write_bytes(PREPRINT)                     # el árbol vuelve a v1, sin commit
    _nota("2007Plano", pdf_source="publisher")
    _paginas(monkeypatch, 10, 10)
    with pytest.raises(rp.ReplaceError, match="MISMO sha"):
        rp.backfill("2007Plano", "publisher", "m")



def test_el_txt_de_un_slug_SIN_pdf_tambien_se_regenera(toy_vault, tmp_path, monkeypatch, capsys):
    """⛔ #448 — D-18 trae el `.txt` al slug del sujeto SIN el PDF, así que los slugs de un bibcode
    son la UNIÓN de sus copias de PDF y de `.txt`. El bucle iteraba `copias` (los PDF) y el `.txt`
    del otro slug quedaba describiendo el preprint mientras el PDF describía el publicado: el
    bloqueante D-18/D-20, producido por el comando que existe para cerrar ese backlog. Medido: 3 de
    31 reemplazos en una corrida."""
    _copia("ica", "2015Voss"); _nota("2015Voss")
    (cfg.FULLTEXT / "ica-ruido").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "ica-ruido" / "2015Voss.txt").write_text("texto del preprint\n", encoding="utf-8")
    assert cfg.bibcode_slugs("2015Voss") == {"pdf": {"ica"}, "txt": {"ica", "ica-ruido"}}
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    _paginas(monkeypatch)
    corridas = []

    def _extrae(cmd, **k):          # el doble de `extract_fulltext --bibcode`: reescribe ESE `.txt`
        corridas.append(cmd)
        (cfg.FULLTEXT / cmd[2] / f"{cmd[4]}.txt").write_text("texto del editor\n", encoding="utf-8")
    monkeypatch.setattr(rp.subprocess, "run", _extrae)
    r = rp.replace("2015Voss", _entrante(tmp_path), "publisher", "copia del editor")
    assert [c[2] for c in corridas] == ["ica"], "sin PDF en `ica-ruido` no hay qué re-extraer ahí"
    assert (cfg.FULLTEXT / "ica-ruido" / "2015Voss.txt").read_bytes() == \
        (cfg.FULLTEXT / "ica" / "2015Voss.txt").read_bytes(), "las dos copias D-18 quedan iguales"
    assert r["txts_copiados"] == [str(cfg.FULLTEXT / "ica-ruido" / "2015Voss.txt")]
    rp.print_report(r, "publisher", "m")
    assert "copiados a 1 slug(s)" in capsys.readouterr().out and "ica-ruido" in r["txts_copiados"][0]
    # y con dry-run no se copia nada
    (cfg.FULLTEXT / "ica-ruido" / "2015Voss.txt").write_text("texto del preprint\n", encoding="utf-8")
    r = rp.replace("2015Voss", _entrante(tmp_path, b"%PDF-1.7\notra\n"), "publisher", "m", dry_run=True)
    assert (cfg.FULLTEXT / "ica-ruido" / "2015Voss.txt").read_text(encoding="utf-8") == "texto del preprint\n"
    assert r["txts_copiados"], "el dry-run declara lo que copiaría"


def test_si_NINGUN_slug_con_pdf_tenia_txt_se_extrae_en_el_primero_y_se_copia(toy_vault, tmp_path,
                                                                              monkeypatch, capsys):
    """#448, el borde: el slug con el PDF no tiene `.txt` y otro slug sí. La copia necesita un
    origen, así que se extrae en el primer slug con PDF (sin `--force`: no existe) y de ahí se
    copia. Si la extracción no deja nada, se AVISA y el `.txt` viejo queda (el lint lo bloquea)."""
    _copia("ica", "2015Voss"); _nota("2015Voss")
    (cfg.FULLTEXT / "ica" / "2015Voss.txt").unlink()
    (cfg.FULLTEXT / "ica-ruido").mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / "ica-ruido" / "2015Voss.txt").write_text("texto del preprint\n", encoding="utf-8")
    monkeypatch.setattr(rp, "first_pages_text", lambda _p: "sin marca")
    _paginas(monkeypatch)
    corridas = []
    monkeypatch.setattr(rp.subprocess, "run", lambda cmd, **k: corridas.append(cmd))
    rp.replace("2015Voss", _entrante(tmp_path), "publisher", "m")
    assert corridas and corridas[0][2:] == ["ica", "--bibcode", "2015Voss"], "sin `--force`: no existía"
    assert "no se pudo regenerar" in capsys.readouterr().out
    assert (cfg.FULLTEXT / "ica-ruido" / "2015Voss.txt").read_text(encoding="utf-8") == "texto del preprint\n"

    def _extrae(cmd, **k):
        (cfg.FULLTEXT / cmd[2] / f"{cmd[4]}.txt").write_text("texto del editor\n", encoding="utf-8")
    monkeypatch.setattr(rp.subprocess, "run", _extrae)
    r = rp.replace("2015Voss", _entrante(tmp_path, b"%PDF-1.7\notra\n"), "publisher", "m")
    assert (cfg.FULLTEXT / "ica-ruido" / "2015Voss.txt").read_text(encoding="utf-8") == "texto del editor\n"
    assert len(r["txts"]) == 1 and len(r["txts_copiados"]) == 1
