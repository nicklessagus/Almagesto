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
    que este script existe para no cometer. El motivo dice cuál es el hueco.

    @inv INV-151"""
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
    assert "ADS export no contestó" in capsys.readouterr().out


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


def test_el_hermano_de_verificacion_NO_cuenta_como_nota_de_paper(tmp_path, monkeypatch, capsys):
    """#397b — medido en una bóveda real con v1.212.0: el script enumeraba `papers/*.md` a mano y
    contaba los tres hermanos `<nota>.verif.md` como notas, reportando «192 nota(s) miradas» sobre
    189 y listándolos entre los papers **sin BibTeX**. No los escribe —no tienen frontmatter— pero
    el denominador y la lista mienten, que es lo que INV-40 existe para impedir.

    La regla ya tiene una sola casa desde #344 (`cfg.note_paths`): lo único que hacía falta era no
    reimplementarla. El guard estático que impide la tercera vez vive en `test_codigo_muerto.py`."""
    monkeypatch.setattr(cfg, "PAPERS", tmp_path)
    monkeypatch.setattr(cfg, "get_ads_token", lambda: "tok")
    fake_net(monkeypatch, post=lambda *a, **k: Resp(200, payload={"export": ""}))
    _nota(tmp_path, {"bibcode": "2001Libro", "tags": ["paper"]})
    (tmp_path / "2001Libro.verif.md").write_text("| # | Afirmación |\n|---|---|\n", encoding="utf-8")
    assert [f.stem for f in fb.notes_to_check(SimpleNamespace(paper=None, slug=None))] == ["2001Libro"]
    monkeypatch.setattr(sys, "argv", ["fetch_bibtex.py"])
    assert fb.main() == 0
    salida = capsys.readouterr().out
    assert "1 nota(s) de paper miradas" in salida, salida
    assert ".verif" not in salida, "el hermano no entra ni al denominador ni a la lista de huecos"


# ── #397 (cola) · el hueco que NO es tal: el DOI existe y la nota no lo lleva ────────────────────

def _cr(items):
    return Resp(200, payload={"message": {"items": items}})


def test_doi_candidate_exige_el_titulo_EXACTO(monkeypatch):
    """⛔ La doctrina del propio repo prohíbe resolver por título: `discover` lo midió en **18 de 25
    resueltos, 2 apuntando a OTRO trabajo**. Así que acá el match es exacto sobre el título
    normalizado Y sobre el apellido del primer autor, y todo lo demás devuelve el motivo sin
    candidato.

    Verificado contra el servicio real: un título exacto resuelve (Mayor 1995 → `10.1038/378355a0`)
    y uno recordado devuelve tres papers plausibles, **ninguno el buscado** — que es exactamente el
    fallo que esta severidad existe para rehusar."""
    monkeypatch.setattr(cfg, "get_mailto", lambda: "")
    fake_net(monkeypatch, get=lambda *a, **k: _cr([
        {"DOI": "10.1/otro", "title": ["Otro paper parecido del mismo autor"],
         "author": [{"family": "Mayor"}]},
        {"DOI": "10.1038/378355a0", "title": ["A Jupiter-mass companion to a solar-type star"],
         "author": [{"family": "Mayor"}], "issued": {"date-parts": [[1995]]}}]))
    doi, por_que = fb.doi_candidate("A Jupiter-mass companion to a solar-type star", "Mayor, Michel", 1995)
    assert doi == "10.1038/378355a0" and "título exacto" in por_que


def test_doi_candidate_NO_propone_por_parecido(monkeypatch):
    monkeypatch.setattr(cfg, "get_mailto", lambda: "")
    fake_net(monkeypatch, get=lambda *a, **k: _cr([
        {"DOI": "10.1/parecido", "title": ["Applications of higher order statistics in sEMG"],
         "author": [{"family": "Naik"}]}]))
    doi, por_que = fb.doi_candidate("Applications of Higher Order Statistics", "Naik", 2011)
    assert doi == "" and "ninguno con el título EXACTO" in por_que


def test_doi_candidate_descarta_el_autor_que_no_es(monkeypatch):
    """El título puede repetirse entre un paper y su comentario; el apellido del primer autor es lo
    que separa a los dos, y sin él el carril propondría el trabajo de otro."""
    monkeypatch.setattr(cfg, "get_mailto", lambda: "")
    fake_net(monkeypatch, get=lambda *a, **k: _cr([
        {"DOI": "10.1/deotro", "title": ["Un titulo identico"], "author": [{"family": "Otro"}]}]))
    assert fb.doi_candidate("Un titulo identico", "Naik", 2011)[0] == ""


def test_doi_candidate_tolera_un_ano_de_diferencia_y_no_mas(monkeypatch):
    """El depósito y la publicación discrepan un año seguido —`2011Naik` declara 2012 en su propio
    frontmatter—, así que ±1 pasa; más que eso ya es otro trabajo con el mismo título."""
    monkeypatch.setattr(cfg, "get_mailto", lambda: "")
    item = {"DOI": "10.5772/52324", "title": ["Un titulo"], "author": [{"family": "Naik"}],
            "issued": {"date-parts": [[2012]]}}
    fake_net(monkeypatch, get=lambda *a, **k: _cr([item]))
    assert fb.doi_candidate("Un titulo", "Naik", 2011)[0] == "10.5772/52324"
    assert fb.doi_candidate("Un titulo", "Naik", 2005)[0] == ""
    # Y el registro SIN año utilizable no se descarta ni revienta: Crossref devuelve `issued`
    # vacío o `date-parts: [[]]` a menudo, y un año que no consta no puede desempatar nada —
    # descartarlo sería inventar la discrepancia, y `int(None)` sería tirar la corrida entera.
    for roto in ({}, {"date-parts": [[]]}, {"date-parts": [[None]]}):
        fake_net(monkeypatch, get=lambda *a, _r=roto, **k: _cr([{**item, "issued": _r}]))
        assert fb.doi_candidate("Un titulo", "Naik", 2011)[0] == "10.5772/52324", roto


def test_doi_candidate_sin_datos_o_sin_red_lo_DICE(monkeypatch):
    """D-43 — «no se pudo preguntar» no es «no existe»: las dos ramas devuelven su motivo, que es lo
    que después viaja al reporte pegado al hueco."""
    monkeypatch.setattr(cfg, "get_mailto", lambda: "")
    assert "no hay con qué preguntar" in fb.doi_candidate("", "Naik")[1]
    assert "no hay con qué preguntar" in fb.doi_candidate("Un titulo", "")[1]

    def cae(*a, **k):
        raise real_requests.RequestException("boom")
    fake_net(monkeypatch, get=cae)
    assert "no consta" in fb.doi_candidate("Un titulo", "Naik")[1]


def test_main_PROPONE_el_doi_y_no_lo_estampa(tmp_path, monkeypatch, capsys):
    """⛔ Propone y no escribe: poblar `doi:` es curación —la decisión de que ese registro ES este
    paper— y el matcheo por título es lo que el framework prohíbe resolver solo. La nota queda
    intacta y el reporte trae el DOI para pegar."""
    monkeypatch.setattr(cfg, "PAPERS", tmp_path)
    monkeypatch.setattr(cfg, "get_ads_token", lambda: "tok")
    monkeypatch.setattr(cfg, "get_mailto", lambda: "")
    fake_net(monkeypatch,
             post=lambda *a, **k: Resp(200, payload={"export": ""}),
             get=lambda *a, **k: _cr([{"DOI": "10.5772/52324", "title": ["Un titulo"],
                                       "author": [{"family": "Naik"}]}]))
    f = _nota(tmp_path, {"bibcode": "2011Naik", "tags": ["paper"], "title": "Un titulo",
                         "first_author": "Naik, Ganesh"})
    antes = f.read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["fetch_bibtex.py"])
    assert fb.main() == 0
    salida = capsys.readouterr().out
    assert "el hueco NO es tal" in salida and "10.5772/52324" in salida, salida
    assert f.read_text(encoding="utf-8") == antes, "la nota NO se toca"


def test_el_mailto_del_polite_pool_es_OPT_IN_y_no_sale_si_no_se_declaro(monkeypatch):
    """El `mailto` es opt-in declarado (`vault/config/mailto` o `ALMAGESTO_MAILTO`) y **no** sale de
    `git config user.email`: hasta 1.73.0 se tomaba de ahí —dato personal entregado para autoría, no
    para egress a un tercero— y viajaba embebido en la URL, o sea en cualquier `raise_for_status` y
    en cualquier log de proxy. Este carril es una consulta más a Crossref, así que hereda la regla:
    sin declararlo **no se manda nada**, y con él declarado se manda para entrar al pool rápido."""
    vistos = {}

    def get(url, params=None, headers=None, timeout=None):
        vistos.update(params or {})
        return _cr([])
    monkeypatch.setattr(cfg, "get_mailto", lambda: "")
    fake_net(monkeypatch, get=get)
    fb.doi_candidate("Un titulo", "Naik")
    assert "mailto" not in vistos, "sin opt-in no sale ninguna dirección"

    vistos.clear()
    monkeypatch.setattr(cfg, "get_mailto", lambda: "yo@ejemplo.org")
    fb.doi_candidate("Un titulo", "Naik")
    assert vistos.get("mailto") == "yo@ejemplo.org"


# ── #399 · las dos salidas que leían al revés ───────────────────────────────────────────────────

def test_las_claves_SINTETICAS_no_se_le_mandan_a_ADS(monkeypatch):
    """#399 — `main` mandaba al export **todas** las claves pendientes, sintéticas incluidas. Con
    las notas con bibcode ya estampadas, el lote que queda son las 19 `AAAA+Autor`: ADS contesta 404
    al lote entero y la corrida anunciaba «⛔ ADS export falló» sobre papers que **sí** se habían
    evaluado bien — el ⛔ afirmaba «no evaluado» de algo evaluado, que es la confusión que este
    script existe para separar (D-43).

    ⚠ `BIBCODE_LIKE_RE` no alcanza: es la heurística laxa de los wikilinks y una clave sintética la
    pasa. Un bibcode de ADS son 19 caracteres exactos."""
    mandados = []

    def post(url, headers=None, json=None, timeout=None):
        mandados.extend((json or {}).get("bibcode") or [])
        return Resp(200, payload={"export": ENTRADA_ADS})
    fake_net(monkeypatch, post=post)
    out, errores = fb.ads_bibtex(["1995Natur.378..355M", "2011Naik", "1998HyvarinenICANN"], "tok")
    assert mandados == ["1995Natur.378..355M"], mandados
    assert errores == [] and "1995Natur.378..355M" in out


def test_solo_claves_sinteticas_no_llama_a_ADS_ni_reporta_error(monkeypatch):
    """El caso medido entero: nada que preguntar no es un fallo. Sin ninguna clave con forma de
    bibcode no se hace el request, y la corrida no puede salir en rc 2."""
    llamado = []
    fake_net(monkeypatch, post=lambda *a, **k: llamado.append(1) or Resp(404))
    assert fb.ads_bibtex(["2011Naik", "1998HyvarinenICANN"], "tok") == ({}, [])
    assert llamado == []


def test_el_404_de_ADS_es_una_RESPUESTA_y_el_5xx_es_no_evaluado(monkeypatch):
    """#399 — «ninguno de éstos está en ADS» es un hueco legítimo que la cascada clasifica; un
    timeout o un 5xx deja papers **sin consultar**, y ésa es la única condición que puede sacar la
    corrida en rc 2. Los dos se veían igual porque `raise_for_status` levanta para ambos."""
    fake_net(monkeypatch, post=lambda *a, **k: Resp(404))
    assert fb.ads_bibtex(["1995Natur.378..355M"], "tok") == ({}, [])
    fake_net(monkeypatch, post=lambda *a, **k: Resp(503))
    out, errores = fb.ads_bibtex(["1995Natur.378..355M"], "tok")
    assert out == {} and len(errores) == 1 and "SIN consultar" in errores[0]


def test_el_titulo_EXACTO_con_autor_distinto_sale_como_DUDOSO(monkeypatch, tmp_path, capsys):
    """#399 — `2011Naik`: Crossref tiene el DOI y el título coincide exacto, pero el registro lleva
    `family: 'R.'` (metadata rota del editor), así que la exigencia de apellido fallaba y el caso
    que motivó #397 **no aparecía en ninguna salida**.

    La severidad no se afloja —sigue sin proponerse como bueno— pero se imprime: un candidato que
    nadie ve es indistinguible de no haber buscado. Y sale por el canal de las propuestas, no
    enterrado entre los huecos."""
    monkeypatch.setattr(cfg, "get_mailto", lambda: "")
    fake_net(monkeypatch, get=lambda *a, **k: _cr([
        {"DOI": "10.5772/52324", "title": ["Introduction: Independent Component Analysis"],
         "author": [{"family": "R.", "given": "Ganesh"}], "issued": {"date-parts": [[2012]]}}]))
    doi, por_que = fb.doi_candidate("Introduction: Independent Component Analysis", "Naik", 2011)
    assert doi == "", "sigue sin proponerse como bueno"
    assert por_que.startswith("DUDOSO") and "10.5772/52324" in por_que and "«R.»" in por_que

    monkeypatch.setattr(cfg, "PAPERS", tmp_path)
    monkeypatch.setattr(cfg, "get_ads_token", lambda: "tok")
    _nota(tmp_path, {"bibcode": "2011Naik", "tags": ["paper"], "year": 2011,
                     "title": "Introduction: Independent Component Analysis",
                     "first_author": "Naik, Ganesh"})
    monkeypatch.setattr(sys, "argv", ["fetch_bibtex.py"])
    assert fb.main() == 0
    salida = capsys.readouterr().out
    assert "DUDOSO" in salida and "10.5772/52324" in salida, salida
    assert "sin BibTeX (campo VACÍO" not in salida, "no se entierra entre los huecos"
