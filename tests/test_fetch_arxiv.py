"""fetch_arxiv: resume por HTTP Range, 200-que-ignora-Range, 429, magic %PDF, main()."""
import json
import sys
from types import SimpleNamespace

import pytest
import requests as real_requests

import fetch_arxiv as fa


class StreamResp:
    """Respuesta streaming falsa: context manager + iter_content, corte opcional a mitad."""

    def __init__(self, status, chunks=(), cut=False):
        self.status_code, self._chunks, self._cut = status, list(chunks), cut

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, chunk_size):
        yield from self._chunks
        if self._cut:
            raise real_requests.ConnectionError("conexión cortada (throttling)")


@pytest.fixture
def no_sleep(monkeypatch):
    waits = []
    monkeypatch.setattr(fa, "time", SimpleNamespace(sleep=waits.append))
    return waits


def patch_get(monkeypatch, responses, calls=None):
    it = iter(responses)

    def get(url, headers=None, timeout=None, stream=None):
        if calls is not None:
            calls.append(dict(headers or {}))
        return next(it)
    monkeypatch.setattr(fa, "requests",
                        SimpleNamespace(get=get, RequestException=real_requests.RequestException))


# ── download_pdf ─────────────────────────────────────────────────────────────

def test_descarga_simple(tmp_path, no_sleep, monkeypatch):
    patch_get(monkeypatch, [StreamResp(200, [b"%PDF-", b"data"])])
    dest = tmp_path / "x.pdf"
    assert fa.download_pdf("2101.00001", dest) is True
    assert dest.read_bytes() == b"%PDF-data"


def test_resume_con_range(tmp_path, no_sleep, monkeypatch):
    calls = []
    patch_get(monkeypatch, [StreamResp(200, [b"%PDF-12345"], cut=True),
                            StreamResp(206, [b"-rest"])], calls)
    dest = tmp_path / "x.pdf"
    assert fa.download_pdf("2101.00001", dest) is True
    assert dest.read_bytes() == b"%PDF-12345-rest"
    assert calls[1].get("Range") == "bytes=10-"      # reanuda desde lo acumulado


def test_200_ignora_range_no_duplica(tmp_path, no_sleep, monkeypatch):
    """Si el server ignora el Range y manda el archivo ENTERO (200), el buffer se resetea."""
    patch_get(monkeypatch, [StreamResp(200, [b"%PDF-AB"], cut=True),
                            StreamResp(200, [b"%PDF-ABCD"])])
    dest = tmp_path / "x.pdf"
    assert fa.download_pdf("2101.00001", dest) is True
    assert dest.read_bytes() == b"%PDF-ABCD"


def test_429_no_apendea_cuerpo_de_error(tmp_path, no_sleep, monkeypatch):
    patch_get(monkeypatch, [StreamResp(429, [b"rate limited"]),
                            StreamResp(200, [b"%PDF-ok"])])
    dest = tmp_path / "x.pdf"
    assert fa.download_pdf("2101.00001", dest) is True
    assert dest.read_bytes() == b"%PDF-ok"
    assert 15 in no_sleep


def test_respuesta_no_pdf(tmp_path, no_sleep, monkeypatch):
    patch_get(monkeypatch, [StreamResp(200, [b"<html>procesando</html>"])])
    dest = tmp_path / "x.pdf"
    assert fa.download_pdf("2101.00001", dest) is False
    assert not dest.exists()


def test_agotamiento_de_intentos(tmp_path, no_sleep, monkeypatch):
    patch_get(monkeypatch, [StreamResp(200, [b"%PDF-x"], cut=True)] * fa.MAX_ATTEMPTS)
    dest = tmp_path / "x.pdf"
    assert fa.download_pdf("2101.00001", dest) is False
    assert not dest.exists()


# ── main() ───────────────────────────────────────────────────────────────────

def ads_json(root, slug, records):
    d = root / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"star": "Estrella Test", "records": records}),
                                encoding="utf-8")


RECORDS = [
    {"bibcode": "2020withA...1A", "title": "con arxiv", "relevant": True,
     "arxiv_id": "2101.00001", "doi": "10.1/a"},
    {"bibcode": "1990preA....1B", "title": "pre-arxiv", "relevant": True,
     "arxiv_id": None, "doi": "10.1/b"},
    {"bibcode": "2020nonC....1C", "title": "no core", "relevant": False,
     "arxiv_id": "2101.00002", "doi": None},
]


def run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["fetch_arxiv.py", *argv])
    return fa.main()


def test_main_baja_relevantes_y_lista_faltantes(toy_vault, no_sleep, monkeypatch):
    ads_json(toy_vault.ROOT, "test_star", RECORDS)
    bajados = []
    monkeypatch.setattr(fa, "download_pdf", lambda aid, dest: bajados.append(aid) or True)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert bajados == ["2101.00001"]                 # sólo el relevante con arxiv
    miss = json.loads((toy_vault.ROOT / "build" / "test_star" / "missing_pdf.json").read_text())
    assert [m["bibcode"] for m in miss] == ["1990preA....1B"]
    assert miss[0]["doi"] == "10.1/b"


def test_main_skip_existente_y_limit(toy_vault, no_sleep, monkeypatch, capsys):
    recs = [dict(RECORDS[0]), dict(RECORDS[0], bibcode="2021otro...1D", arxiv_id="2101.00009")]
    ads_json(toy_vault.ROOT, "test_star", recs)
    destdir = toy_vault.PDFS / "test_star"
    destdir.mkdir(parents=True, exist_ok=True)
    (destdir / "2020withA...1A.pdf").write_bytes(b"%PDF-ya")
    bajados = []
    monkeypatch.setattr(fa, "download_pdf", lambda aid, dest: bajados.append(aid) or True)
    run_main(monkeypatch, ["test_star"])
    assert bajados == ["2101.00009"]                 # el existente se saltea
    assert "ya estaban 1" in capsys.readouterr().out

    bajados.clear()
    (destdir / "2020withA...1A.pdf").unlink()
    run_main(monkeypatch, ["test_star", "--limit", "1"])
    assert len(bajados) == 1


def test_main_sin_ads_json(toy_vault, monkeypatch):
    assert run_main(monkeypatch, ["test_star"]) == 1
