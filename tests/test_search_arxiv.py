"""search_arxiv: backend de descubrimiento sobre la API Atom de arXiv (sin key).

La red está siempre falseada: ningún test toca arXiv de verdad."""
from __future__ import annotations

import pytest
import requests as real_requests

import query_ads as qa
import search_arxiv as sx

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
