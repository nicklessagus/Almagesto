"""search_arxiv: backend de descubrimiento sobre la API Atom de arXiv (sin key).

La red está siempre falseada: ningún test toca arXiv de verdad."""
from __future__ import annotations

import pytest
import requests as real_requests

import query_ads as qa
import search_arxiv as sx
import lib_config as cfg

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/1404.2986v3</id>
    <updated>2014-04-11T00:00:00Z</updated>
    <published>2014-04-10T18:00:00Z</published>
    <title>A Tutorial on Independent
      Component Analysis</title>
    <summary>  This tutorial introduces ICA
  for signal separation.  </summary>
    <author><name>Jonathon Shlens</name></author>
    <arxiv:doi>10.48550/arXiv.1404.2986</arxiv:doi>
    <category term="cs.LG"/>
    <category term="astro-ph.IM"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2001.00001v1</id>
    <published>2020-01-01T00:00:00Z</published>
    <title>Radial velocity jitter</title>
    <summary>No DOI here.</summary>
    <author><name>A. Autora</name></author>
    <author><name>B. Otro</name></author>
    <category term="astro-ph.EP"/>
  </entry>
</feed>
"""


class FakeResp:
    def __init__(self, status=200, text=""):
        self.status_code, self.text = status, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.HTTPError(f"HTTP {self.status_code}")


def fake_get(monkeypatch, text=ATOM, calls=None):
    def _get(url, **kw):
        if calls is not None:
            calls.append(url)
        return FakeResp(200, text)
    monkeypatch.setattr(sx.requests, "get", _get)


def test_parsea_el_atom_y_normaliza(monkeypatch):
    fake_get(monkeypatch)
    recs = sx.search("ICA", rows=10)
    assert len(recs) == 2
    r = recs[0]
    assert r["arxiv_id"] == "1404.2986", "el id va SIN la versión: `v3` es una revisión, no otro trabajo"
    assert r["title"] == "A Tutorial on Independent Component Analysis", "el título viene con saltos de línea"
    assert r["abstract"].startswith("This tutorial introduces ICA")
    assert r["year"] == 2014
    assert r["doi"] == "10.48550/arXiv.1404.2986"
    assert r["bibcode"] == "2014Shlens"
    assert r["via"] == "arxiv"


def test_entrada_sin_doi_no_inventa_uno(monkeypatch):
    """El caso adversario: arXiv sirve entradas sin `arxiv:doi`. Un `doi` inventado rompería la
    identidad de D-19, que es justamente `doi`/`arxiv_id`."""
    fake_get(monkeypatch)
    assert sx.search("x")[1]["doi"] is None


def test_multiples_categorias_y_autores(monkeypatch):
    fake_get(monkeypatch)
    recs = sx.search("x")
    assert recs[0]["keyword"] == ["cs.LG", "astro-ph.IM"]
    assert recs[1]["authors"] == ["A. Autora", "B. Otro"]


def test_categories_entran_en_la_query(monkeypatch):
    calls = []
    fake_get(monkeypatch, calls=calls)
    sx.search("bisector", categories=["astro-ph.EP", "astro-ph.SR"], rows=25)
    url = calls[0]
    assert "cat%3Aastro-ph.EP" in url or "cat:astro-ph.EP" in url
    assert "max_results=25" in url


def test_el_registro_pasa_por_classify_record(monkeypatch):
    """Mismo schema que ADS y que OpenAlex: una sola lente para los tres backends."""
    import re
    fake_get(monkeypatch)
    monkeypatch.setattr(qa, "FACET_PATTERNS", {"method": re.compile("independent component", re.I)})
    monkeypatch.setattr(qa, "NOISE_DOCTYPES", set())
    monkeypatch.setattr(qa, "REQUIRE_FACETS", [])
    monkeypatch.setattr(qa, "MIN_FACETS", 1)
    facets, relevant = qa.classify_record(sx.search("x")[0])
    assert facets == ["method"] and relevant is True


def test_feed_vacio_no_revienta(monkeypatch):
    fake_get(monkeypatch, text='<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"/>')
    assert sx.search("nada") == []


def test_citas_desconocidas_son_None_no_cero(monkeypatch):
    """arXiv **no publica** el conteo de citas. Poner `0` es afirmar «no lo cita nadie» sobre un
    dato que nadie miró — el mismo cero inventado que INV-87 prohíbe en el lint y que #70 prohíbe
    en el frontmatter (si la autoridad calla, el campo va `null`). Y tiene consecuencia real: la
    puerta 2 de D-26 exige `citation_count >= umbral`, así que con 0 un paper fundacional
    descubierto por arXiv quedaba excluido **por construcción**."""
    fake_get(monkeypatch)
    assert sx.search("x")[0]["citation_count"] is None


def test_el_registro_trae_el_veredicto_del_clasificador():
    """«Mismo schema que `query_ads`» tiene que incluir las tres claves del **clasificador**:
    `facets`, `relevant`, `why_excluded`. Sin ellas, medido: los consumidores que indexan con
    corchetes revientan (`fetch_pdf`, `fetch_arxiv`, `make_notes`) y los que usan `.get()` dan
    **falsos limpios** — `ingest_theme` ve `core` vacío, y `make_notes` marca toda nota
    `relevance: low`, lo que además las saca de `citation_index.corpus_idents`, o sea de la puerta
    1 que estos backends existen para alimentar."""
    r = sx.to_record(sx.ET.fromstring(ATOM).findall("a:entry", sx.NS)[0])
    for campo in ("facets", "relevant", "why_excluded"):
        assert campo in r, f"falta {campo}: el registro no es del mismo schema"
    assert isinstance(r["relevant"], bool) and isinstance(r["facets"], list)


def test_main_es_preview_clasifica_con_la_lente_y_no_escribe_nada(toy_vault, monkeypatch, capsys):
    """El CLI de #95: hace visible lo que el backend trae, sin tocar la bóveda.

    El módulo estaba implementado y testeado pero **sin ninguna forma de invocarlo**, mientras
    `CLAUDE.md` lo nombra como backend de descubrimiento fuera de ADS: la promesa se leía como
    capacidad vigente y no había manera de ejercerla. Esto no lo cablea a la cadena —esa decisión
    sigue abierta— lo hace usable para poder decidirla con datos.  @inv INV-96
    """
    recs = [{"bibcode": None, "arxiv_id": "2401.00001", "title": "A radial velocity study",
             "abstract": "HARPS data", "year": "2024", "doi": None, "citekey": "2024Foo",
             "keyword": [], "doctype": "eprint", "citation_count": 0},
            {"bibcode": None, "arxiv_id": "2401.00002", "title": "Something about frogs",
             "abstract": "amphibians", "year": "2024", "doi": None, "citekey": "2024Bar",
             "keyword": [], "doctype": "eprint", "citation_count": 0}]
    monkeypatch.setattr(sx, "search", lambda *a, **k: recs)
    antes = sorted(p.name for p in cfg.WIKI.rglob("*"))
    assert sx.main(["radial velocity"]) == 0
    salida = capsys.readouterr().out
    assert "2401.00001" in salida and "2401.00002" in salida
    assert "core" in salida and "Preview" in salida
    assert sorted(p.name for p in cfg.WIKI.rglob("*")) == antes, "el preview NO puede escribir"


def test_el_preview_no_re_clasifica_con_la_funcion_equivocada(monkeypatch, capsys):
    """Issue #173 — `to_record` afirma *"Se clasifica acá con `classify_record`, la ÚNICA lente"*, y
    `main` volvía a clasificar con `query_ads.classify(r)` sobre un registro donde `title` YA es un
    string. `classify` hace `" ".join(cfg.as_list(rec.get("title")))` y `as_list("…") == []`, así que
    **el título se descartaba** — y encima pisaba `r["facets"]`/`r["relevant"]`.

    Rompe la promesa de una sola definición de core que el módulo declara como su razón de existir, y
    en la dirección peor: un tema de método cuyo fundacional se reconoce **por el título** (el caso
    ICA/Hyvärinen de D-26) salía *sin tópico* en el único preview que el framework ofrece para
    decidir si vale cablear este backend."""
    rec = {"title": "Independent Component Analysis of stellar spectra", "abstract": "",
           "keyword": [], "doctype": "eprint", "bibcode": "1999Autor", "arxiv_id": "1234.5678",
           "year": 1999, "citation_count": None}
    monkeypatch.setattr(sx, "search", lambda *a, **k: [dict(rec)])
    monkeypatch.setattr(qa, "classify_record", lambda r: (["method"], True))
    assert sx.main(["independent component analysis"]) == 0
    out = capsys.readouterr().out
    assert "1 core" in out, "el veredicto del preview es el de `classify_record`, no otro"
    assert "sin tópico" not in out
