"""#397 — el BibTeX OFICIAL de cada paper en su ficha, nunca uno redactado por el modelo.

Los tres carriles se probaron **una vez contra los servicios reales** antes de escribir el cliente
(regla de método nº 1) — ADS export, content negotiation en `doi.org` y la exportación de arXiv —, y
de ahí salieron las dos formas que estos tests fijan: que ADS **no** devuelve las entradas en el
orden pedido, y que `doi.org` contesta su «DOI Not Found» como **HTML**.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import requests as real_requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_bibtex as fb   # noqa: E402
import lib_config as cfg    # noqa: E402

ENTRADA_ADS = ('@ARTICLE{1995Natur.378..355M,\n'
               '       author = {{Mayor}, Michel and {Queloz}, Didier},\n'
               '        title = "{A Jupiter-mass companion to a solar-type star}",\n'
               '         year = 1995,\n'
               '          doi = {10.1038/378355a0},\n'
               '}\n')


class Resp:
    def __init__(self, status=200, payload=None, text="", ct=""):
        self.status_code, self._payload, self.text = status, payload, text
        self.headers = {"Content-Type": ct}

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise real_requests.RequestException(f"status {self.status_code}")


def fake_net(monkeypatch, *, get=None, post=None):
    monkeypatch.setattr(fb, "requests", SimpleNamespace(
        get=get or (lambda *a, **k: Resp(404)),
        post=post or (lambda *a, **k: Resp(404)),
        RequestException=real_requests.RequestException))


# ── split_entries: la forma que ADS devuelve de verdad ──────────────────────────────────────────

def test_split_entries_indexa_por_CLAVE_no_por_posicion():
    """⛔ ADS no devuelve las entradas en el orden en que se pidieron — comprobado contra el
    servicio real: se piden `1995Natur…` y `2004ISPL…`, y vuelven al revés. Emparejarlas por
    posición le adjudicaría la entrada de un paper a otro, que es la atribución falsa que la regla
    de método nº 4 llama peor que el vacío."""
    export = "@ARTICLE{2004ISPL...11..470D,\n title = {B},\n}\n" + ENTRADA_ADS
    out = fb.split_entries(export)
    assert list(out) == ["2004ISPL...11..470D", "1995Natur.378..355M"]
    # Y cada entrada vuelve ENTERA: sin el cuerpo, un `bibtex` de una sola línea pasaría los dos
    # chequeos del lint (tiene procedencia, no contradice al frontmatter porque no dice nada) y el
    # informe se llevaría una cita sin volumen ni páginas.
    assert out["1995Natur.378..355M"] == ENTRADA_ADS
    assert "2004ISPL" not in out["1995Natur.378..355M"], "una entrada no se lleva la de al lado"


def test_split_entries_vacio_no_inventa_claves():
    assert fb.split_entries("") == {} and fb.split_entries("texto suelto") == {}


# ── el carril del resolver: un 200 no alcanza ───────────────────────────────────────────────────

def test_doi_bibtex_RECHAZA_el_html_del_resolver(monkeypatch):
    """⛔ `doi.org` sirve su «DOI Not Found» como una página HTML. Guardar eso en el frontmatter
    sería exactamente el bloque inventado que este issue existe para impedir, y encima con la firma
    de una descarga. Se exige el `Content-Type` de BibTeX, no sólo el status."""
    fake_net(monkeypatch, get=lambda *a, **k: Resp(404, text="<!DOCTYPE html>", ct="text/html"))
    assert fb.doi_bibtex("10.0/no-existe") == ("", "")
    # ⛔ Y el cuerpo que PARECE una entrada no alcanza: es justamente la forma del defecto que este
    # issue persigue —algo plausible, con cara de descargado, que nadie escribió—. Los dos lados de
    # la guarda tienen su caso: status de error con cuerpo BibTeX-oide, y 200 con `Content-Type`
    # equivocado (un proxy, un portal cautivo). Sin uno u otro, el `startswith("@")` los deja pasar.
    fake_net(monkeypatch, get=lambda *a, **k: Resp(
        404, text="@article{inventado, title={no existe}}", ct="text/html"))
    assert fb.doi_bibtex("10.0/no-existe") == ("", "")
    fake_net(monkeypatch, get=lambda *a, **k: Resp(
        200, text="@article{inventado, title={no existe}}", ct="text/html"))
    assert fb.doi_bibtex("10.0/proxy") == ("", "")
    # Y el status manda por su cuenta: un error que igual declara `application/x-bibtex` (un
    # intermediario que sirve su propia página de error con el header que le pidieron) no es una
    # entrada. Es el único caso donde `not r.ok` es lo único que separa a la ficha de una cita
    # inventada, y por eso la guarda tiene las dos cláusulas y no una.
    fake_net(monkeypatch, get=lambda *a, **k: Resp(
        503, text="@article{inventado, title={no existe}}", ct="application/x-bibtex"))
    assert fb.doi_bibtex("10.0/caido") == ("", "")


def test_doi_bibtex_devuelve_la_entrada_y_su_agencia(monkeypatch):
    def get(url, headers=None, timeout=None, allow_redirects=None):
        if "/ra/" in url:
            return Resp(200, payload=[{"DOI": "10.1038/x", "RA": "Crossref"}])
        return Resp(200, text="@article{Mayor_1995, title={X}}", ct="application/x-bibtex")
    fake_net(monkeypatch, get=get)
    entrada, fuente = fb.doi_bibtex("10.1038/x")
    assert entrada.startswith("@article{") and fuente == "crossref"


def test_doi_agency_sin_respuesta_dice_doi_y_no_adivina(monkeypatch):
    """D-43 — `doi` es el tercer estado honesto: se bajó del resolver y la agencia no se pudo
    determinar. Poner `crossref` por default sería declarar una procedencia que nadie verificó."""
    fake_net(monkeypatch, get=lambda *a, **k: Resp(500))
    assert fb.doi_agency("10.1/x") == "doi"
    fake_net(monkeypatch, get=lambda *a, **k: Resp(200, payload=[{"RA": "DataCite"}]))
    assert fb.doi_agency("10.1/x") == "datacite"
    fake_net(monkeypatch, get=lambda *a, **k: Resp(200, payload=[{"RA": "mEDRA"}]))
    assert fb.doi_agency("10.1/x") == "doi", "una agencia fuera del vocabulario no se inventa"


def test_arxiv_bibtex_lo_que_no_arranca_con_arroba_no_es_una_entrada(monkeypatch):
    fake_net(monkeypatch, get=lambda *a, **k: Resp(200, text="<html>error</html>"))
    assert fb.arxiv_bibtex("2301.00001") == ""


# ── la cascada, y el cuarto caso ────────────────────────────────────────────────────────────────

def test_bibtex_for_respeta_el_orden_de_la_cascada(monkeypatch):
    """ADS gana sobre el resolver: es la exportación autoritativa para lo que la bóveda indexa por
    bibcode. Si el carril del DOI se consultara igual, una corrida gastaría una request por paper
    para tirar el resultado."""
    llamado = []
    fake_net(monkeypatch, get=lambda *a, **k: llamado.append(a) or Resp(404))
    fm = {"bibcode": "1995Natur.378..355M", "doi": "10.1038/378355a0", "arxiv_id": "9509001"}
    entrada, fuente, motivo = fb.bibtex_for(fm, "1995Natur.378..355M",
                                            {"1995Natur.378..355M": ENTRADA_ADS})
    assert fuente == "ads" and entrada == ENTRADA_ADS and motivo == ""
    assert llamado == [], "con la entrada de ADS no se consulta ningún otro carril"


def test_bibtex_for_sin_ningun_identificador_devuelve_HUECO_con_su_motivo(monkeypatch):
    """⛔ El cuarto caso de la cascada es un hueco DECLARADO, no un relleno: un libro o un manual de
    instrumento no tienen exportación oficial, y una entrada inventada para taparlo es el defecto
    que este script existe para no cometer. El motivo dice cuál es el hueco."""
    fake_net(monkeypatch)
    entrada, fuente, motivo = fb.bibtex_for({"bibcode": "2001Libro"}, "2001Libro", {})
    assert entrada == "" and fuente == ""
    assert "sin bibcode ADS" in motivo and "sin doi" in motivo and "sin arxiv_id" in motivo


def test_ads_bibtex_declara_el_error_en_vez_de_devolver_vacio(monkeypatch):
    """Una caída a mitad de camino no se puede leer como «esos papers no tienen BibTeX»: devuelve lo
    que sí trajo y NOMBRA lo que quedó sin consultar (D-43)."""
    def post(*a, **k):
        raise real_requests.RequestException("boom")
    fake_net(monkeypatch, post=post)
    out, errores = fb.ads_bibtex(["1995Natur.378..355M"], "tok")
    assert out == {} and len(errores) == 1 and "1995Natur" in errores[0]


# ── el estampado ────────────────────────────────────────────────────────────────────────────────

def _nota(tmp_path, fm: dict, cuerpo="# p\n\n## Vista — X\n\nprosa que no se toca\n"):
    f = tmp_path / f"{fm['bibcode']}.md"
    f.write_text("---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n"
                 + cuerpo, encoding="utf-8")
    return f


def test_stamp_bibtex_no_toca_el_cuerpo_y_es_idempotente(tmp_path):
    f = _nota(tmp_path, {"bibcode": "1995Natur.378..355M", "tags": ["paper"]})
    for _ in range(2):
        texto = f.read_text(encoding="utf-8")
        fm = cfg.split_fm(texto) or {}
        fb.stamp_bibtex(f, fm, texto.split("\n---\n", 1)[-1], ENTRADA_ADS, "ads", "2026-09-05")
    salida = f.read_text(encoding="utf-8")
    fm = cfg.split_fm(salida)
    assert fm["bibtex_source"] == "ads" and fm["bibtex_accessed"] == "2026-09-05"
    assert fm["bibtex"].startswith("@ARTICLE{1995Natur")
    assert "prosa que no se toca" in salida
    assert salida.count("bibtex_source:") == 1, "idempotente: no acumula la clave"


def test_main_no_estampa_nada_sobre_el_hueco(tmp_path, monkeypatch):
    """El paper sin exportación oficial queda SIN los tres campos: nada que declarar es distinto de
    declarar vacío, y el lint lo levanta como backlog por su cuenta."""
    monkeypatch.setattr(cfg, "PAPERS", tmp_path)
    monkeypatch.setattr(cfg, "get_ads_token", lambda: "tok")
    fake_net(monkeypatch, post=lambda *a, **k: Resp(200, payload={"export": ""}))
    f = _nota(tmp_path, {"bibcode": "2001Libro", "tags": ["paper"]})
    monkeypatch.setattr(sys, "argv", ["fetch_bibtex.py"])
    assert fb.main() == 0
    assert "bibtex" not in (cfg.split_fm(f.read_text(encoding="utf-8")) or {})


def test_main_sin_notas_no_sale_verde(tmp_path, monkeypatch):
    """D-43 — «no había nada que mirar» no es «está todo bien»: rc 2, como `check_retractions`."""
    monkeypatch.setattr(cfg, "PAPERS", tmp_path)
    monkeypatch.setattr(sys, "argv", ["fetch_bibtex.py"])
    assert fb.main() == 2


def test_main_con_error_de_red_sale_2(tmp_path, monkeypatch, capsys):
    """Papers sin consultar ≠ papers sin BibTeX: la corrida no puede certificar lo que no miró."""
    monkeypatch.setattr(cfg, "PAPERS", tmp_path)
    monkeypatch.setattr(cfg, "get_ads_token", lambda: "tok")

    def post(*a, **k):
        raise real_requests.RequestException("red caída")
    fake_net(monkeypatch, post=post)
    _nota(tmp_path, {"bibcode": "1995Natur.378..355M", "tags": ["paper"]})
    monkeypatch.setattr(sys, "argv", ["fetch_bibtex.py"])
    assert fb.main() == 2
    assert "ADS export falló" in capsys.readouterr().out


# ── el lector de campos que usa el lint ─────────────────────────────────────────────────────────

def test_bibtex_fields_desenvuelve_las_llaves_de_proteccion():
    """ADS escribe `title = "{A Jupiter-mass…}"` y `author = {{Mayor}, Michel}`: comparar eso crudo
    contra el `title` del frontmatter daría una discrepancia que no existe."""
    campos = cfg.bibtex_fields(ENTRADA_ADS)
    assert campos["title"] == "A Jupiter-mass companion to a solar-type star"
    assert campos["year"] == "1995" and campos["doi"] == "10.1038/378355a0"
    assert campos["author"].startswith("Mayor, Michel")


def test_bibtex_for_baja_por_la_cascada_hasta_arxiv(monkeypatch):
    """Los tres carriles, en orden, y cada uno se toma sólo si el anterior no trajo nada. Sin este
    recorrido un carril podría estar muerto y el hueco se leería como «este paper no tiene cita»,
    que es la conclusión más cara: manda a rearmar la entrada a mano."""
    def get(url, headers=None, timeout=None, allow_redirects=None):
        if "arxiv.org" in url:
            return Resp(200, text="@misc{x, title={A}}")
        return Resp(404, text="<html>", ct="text/html")          # el resolver no lo tiene
    fake_net(monkeypatch, get=get)
    fm = {"bibcode": "2020SinADS", "doi": "10.0/no-existe", "arxiv_id": "2301.00001"}
    entrada, fuente, motivo = fb.bibtex_for(fm, "2020SinADS", {})
    assert fuente == "arxiv" and entrada.startswith("@misc{") and motivo == ""

    # y el carril del medio, cuando el resolver sí contesta
    def get_ok(url, headers=None, timeout=None, allow_redirects=None):
        if "/ra/" in url:
            return Resp(200, payload=[{"RA": "DataCite"}])
        return Resp(200, text="@dataset{y}", ct="application/x-bibtex")
    fake_net(monkeypatch, get=get_ok)
    assert fb.bibtex_for(fm, "2020SinADS", {})[1] == "datacite"


def test_notes_to_check_respeta_paper_y_slug(tmp_path, monkeypatch):
    """`--paper` mira una y `--slug` delega en el MISMO enumerador que `check_retractions` (el que
    sabe leer `ads.json` y la entrada del tema): reimplementarlo acá haría que la cadena y este paso
    miraran universos distintos sobre el mismo ingest."""
    monkeypatch.setattr(cfg, "PAPERS", tmp_path)
    _nota(tmp_path, {"bibcode": "2020aaa", "tags": ["paper"]})
    _nota(tmp_path, {"bibcode": "2020bbb", "tags": ["paper"]})
    assert len(fb.notes_to_check(SimpleNamespace(paper=None, slug=None))) == 2
    una = fb.notes_to_check(SimpleNamespace(paper="2020aaa", slug=None))
    assert [f.stem for f in una] == ["2020aaa"]
    assert fb.notes_to_check(SimpleNamespace(paper="no-existe", slug=None)) == []
    import check_retractions as cr
    monkeypatch.setattr(cr, "slug_notes", lambda s: [tmp_path / "2020bbb.md"])
    assert [f.stem for f in fb.notes_to_check(SimpleNamespace(paper=None, slug="gp"))] == ["2020bbb"]
