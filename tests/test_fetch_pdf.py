"""fetch_pdf: resolver ADS (esources), higiene del token, magic %PDF, residuo missing_pdf."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests as real_requests

import fetch_pdf as fp


# ── candidatos desde el resolver ─────────────────────────────────────────────

# forma real vista en el probe 2026-07-17 (Wilson 1978): placeholders $SIMBAD$, ADS_SCAN
# (visor HTML), PUB_PDF como DOI pelado.
PROBE_RECORDS = [
    {"link_type": "ESOURCE|ADS_PDF", "url": "https://articles.adsabs.harvard.edu/pdf/1978ApJ...226..379W"},
    {"link_type": "ESOURCE|ADS_SCAN", "url": "http://articles.adsabs.harvard.edu/full/1978ApJ...226..379W"},
    {"link_type": "ESOURCE|EPRINT_HTML", "url": "http://$SIMBAD$/simbo.pl?bibcode=1978ApJ...226..379W"},
    {"link_type": "ESOURCE|EPRINT_PDF", "url": "http://$SIMBAD$/simbo.pl?bibcode=1978ApJ...226..379W"},
    {"link_type": "ESOURCE|PUB_PDF", "url": "10.1086/156618"},
]


def test_candidate_urls_filtra_y_ordena():
    cands = fp.candidate_urls(PROBE_RECORDS)
    # EPRINT_PDF era placeholder $SIMBAD$ → afuera; ADS_SCAN es HTML → afuera
    assert cands == [
        ("ADS_PDF", "https://articles.adsabs.harvard.edu/pdf/1978ApJ...226..379W"),
        ("PUB_PDF", "https://doi.org/10.1086/156618"),      # DOI pelado → resolvible
    ]


def test_candidate_urls_prefiere_eprint():
    recs = [{"link_type": "ESOURCE|PUB_PDF", "url": "https://pub/x.pdf"},
            {"link_type": "ESOURCE|EPRINT_PDF", "url": "https://arxiv.org/pdf/x"}]
    assert [t for t, _ in fp.candidate_urls(recs)] == ["EPRINT_PDF", "PUB_PDF"]


def test_candidate_urls_vacio():
    assert fp.candidate_urls([]) == []
    assert fp.candidate_urls([{"link_type": "ESOURCE|PUB_HTML", "url": "https://x"}]) == []


def test_is_ads_host():
    assert fp.is_ads_host("https://articles.adsabs.harvard.edu/pdf/x")
    assert fp.is_ads_host("https://api.adsabs.harvard.edu/v1/resolver/x")
    assert not fp.is_ads_host("https://iopscience.iop.org/article/x/pdf")
    assert not fp.is_ads_host("https://evil.com/adsabs.harvard.edu/x")


# ── red falsa ────────────────────────────────────────────────────────────────

class FakeResp:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code, self._payload, self.content = status, payload, content

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def patch_net(monkeypatch, responses, calls=None):
    seq = list(responses)

    def get(url, headers=None, timeout=None, allow_redirects=True):
        if calls is not None:
            calls.append({"url": url, "headers": dict(headers or {})})
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, Exception):
            raise item
        return item
    monkeypatch.setattr(fp, "requests",
                        SimpleNamespace(get=get, RequestException=real_requests.RequestException))
    monkeypatch.setattr(fp, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(fp, "_curl_pdf", lambda url: None)   # sin curl por default; tests propios lo re-parchean


# ── esource_records ──────────────────────────────────────────────────────────

def test_esource_records_forma_multiple(monkeypatch):
    patch_net(monkeypatch, [FakeResp(200, {"links": {"records": PROBE_RECORDS}})])
    assert fp.esource_records("1978ApJ...226..379W", "tok") == PROBE_RECORDS


def test_esource_records_forma_link_unico(monkeypatch):
    patch_net(monkeypatch, [FakeResp(200, {"action": "redirect", "link": "https://x/p.pdf",
                                           "link_type": "ESOURCE|PUB_PDF"})])
    recs = fp.esource_records("2020X", "tok")
    assert recs == [{"url": "https://x/p.pdf", "link_type": "ESOURCE|PUB_PDF"}]


def test_esource_records_tolerante(monkeypatch):
    patch_net(monkeypatch, [FakeResp(404)])
    assert fp.esource_records("x", "tok") == []
    patch_net(monkeypatch, [real_requests.ConnectionError("sin red")])
    assert fp.esource_records("x", "tok") == []
    patch_net(monkeypatch, [FakeResp(200, None)])
    assert fp.esource_records("x", "tok") == []


def test_esource_manda_token_al_resolver(monkeypatch):
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"links": {"records": []}})], calls)
    fp.esource_records("x", "tok-123")
    assert calls[0]["headers"]["Authorization"] == "Bearer tok-123"


# ── download_pdf ─────────────────────────────────────────────────────────────

def test_download_pdf_ok_y_magic(monkeypatch):
    patch_net(monkeypatch, [FakeResp(200, content=b"%PDF-1.5 data")])
    assert fp.download_pdf("https://articles.adsabs.harvard.edu/pdf/x", "tok") == b"%PDF-1.5 data"
    patch_net(monkeypatch, [FakeResp(200, content=b"<html>paywall</html>")])
    assert fp.download_pdf("https://pub/x.pdf", "tok") is None      # HTML no se guarda


def test_download_pdf_token_solo_a_ads(monkeypatch):
    calls = []
    patch_net(monkeypatch, [FakeResp(200, content=b"%PDF")], calls)
    fp.download_pdf("https://articles.adsabs.harvard.edu/pdf/x", "tok-123")
    assert calls[0]["headers"].get("Authorization") == "Bearer tok-123"
    calls.clear()
    patch_net(monkeypatch, [FakeResp(200, content=b"%PDF")], calls)
    fp.download_pdf("https://iopscience.iop.org/article/x/pdf", "tok-123")
    assert "Authorization" not in calls[0]["headers"]               # nunca al publisher


def test_download_pdf_retry_en_corte_y_429(monkeypatch):
    patch_net(monkeypatch, [real_requests.ConnectionError("ráfaga"),
                            FakeResp(429),
                            FakeResp(200, content=b"%PDF-ok")])
    assert fp.download_pdf("https://articles.adsabs.harvard.edu/pdf/x", "t") == b"%PDF-ok"


def test_download_pdf_agotado_o_denegado(monkeypatch):
    patch_net(monkeypatch, [real_requests.ConnectionError("x")] * 3)
    assert fp.download_pdf("https://a.adsabs.harvard.edu/x", "t") is None
    patch_net(monkeypatch, [FakeResp(403)])
    assert fp.download_pdf("https://pub/x", "t") is None            # 403 no se reintenta


def test_download_pdf_fallback_curl_solo_publishers(monkeypatch):
    """WAF que desafía a requests (Radware/IOP, medido): el publisher cae a curl; ADS no."""
    curled = []
    patch_net(monkeypatch, [FakeResp(200, content=b"<html>challenge</html>")])
    monkeypatch.setattr(fp, "_curl_pdf", lambda url: curled.append(url) or b"%PDF-via-curl")
    assert fp.download_pdf("https://iopscience.iop.org/x/pdf", "t") == b"%PDF-via-curl"
    assert curled == ["https://iopscience.iop.org/x/pdf"]
    curled.clear()
    patch_net(monkeypatch, [FakeResp(403)])
    monkeypatch.setattr(fp, "_curl_pdf", lambda url: curled.append(url) or b"%PDF-x")
    assert fp.download_pdf("https://articles.adsabs.harvard.edu/pdf/x", "t") is None
    assert curled == []                                             # a ADS nunca via curl


def test_curl_pdf_unit(monkeypatch, tmp_path):
    monkeypatch.setattr(fp, "shutil", SimpleNamespace(which=lambda c: None))
    assert fp._curl_pdf("https://pub/x") is None                    # sin curl instalado

    def fake_run(cmd, capture_output=None, text=None):
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"%PDF-curl ok")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(fp, "shutil", SimpleNamespace(which=lambda c: "/usr/bin/curl"))
    monkeypatch.setattr(fp, "subprocess", SimpleNamespace(run=fake_run))
    assert fp._curl_pdf("https://pub/x") == b"%PDF-curl ok"


# ── main() ───────────────────────────────────────────────────────────────────

RECORDS = [
    {"bibcode": "1978oldW...1..1W", "title": "viejo sin arxiv", "relevant": True,
     "arxiv_id": None, "doi": "10.1/w"},
    {"bibcode": "2020newA...1..1A", "title": "con arxiv", "relevant": True,
     "arxiv_id": "2101.00001", "doi": "10.1/a"},
    {"bibcode": "1990nonB...1..1B", "title": "no core", "relevant": False,
     "arxiv_id": None, "doi": None},
]


def ads_json(root, slug, records):
    d = root / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"star": "Estrella Test", "records": records}),
                                encoding="utf-8")
    return d


def run_main(monkeypatch, argv):
    monkeypatch.setenv("ADS_DEV_KEY", "tok-test")
    monkeypatch.setattr(fp, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(sys, "argv", ["fetch_pdf.py", *argv])
    return fp.main()


def test_main_baja_solo_sin_arxiv(toy_vault, monkeypatch):
    ads_json(toy_vault.ROOT, "test_star", RECORDS)
    pedidos = []
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: pedidos.append(bib) or
                        [{"link_type": "ESOURCE|ADS_PDF", "url": f"https://articles.adsabs.harvard.edu/pdf/{bib}"}])
    monkeypatch.setattr(fp, "download_pdf", lambda url, tok: b"%PDF-fake")
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert pedidos == ["1978oldW...1..1W"]           # ni el arXiv ni el no-core
    assert (toy_vault.PDFS / "test_star" / "1978oldW...1..1W.pdf").read_bytes() == b"%PDF-fake"


def test_main_residuo_en_missing_pdf(toy_vault, monkeypatch):
    d = ads_json(toy_vault.ROOT, "test_star", RECORDS)
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    miss = json.loads((d / "missing_pdf.json").read_text())
    assert [m["bibcode"] for m in miss] == ["1978oldW...1..1W"]
    assert miss[0]["doi"] == "10.1/w"


def test_main_todo_conseguido_limpia_residuo_viejo(toy_vault, monkeypatch):
    d = ads_json(toy_vault.ROOT, "test_star", RECORDS)
    (d / "missing_pdf.json").write_text("[]", encoding="utf-8")     # residuo de fetch_arxiv
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok:
                        [{"link_type": "ESOURCE|PUB_PDF", "url": "https://pub/x.pdf"}])
    monkeypatch.setattr(fp, "download_pdf", lambda url, tok: b"%PDF-x")
    run_main(monkeypatch, ["test_star"])
    assert not (d / "missing_pdf.json").exists()


def test_main_idempotente_y_fallback_de_fuentes(toy_vault, monkeypatch, capsys):
    ads_json(toy_vault.ROOT, "test_star", RECORDS)
    destdir = toy_vault.PDFS / "test_star"
    destdir.mkdir(parents=True, exist_ok=True)
    (destdir / "1978oldW...1..1W.pdf").write_bytes(b"%PDF-ya")
    monkeypatch.setattr(fp, "esource_records",
                        lambda bib, tok: (_ for _ in ()).throw(AssertionError("no debería consultar")))
    run_main(monkeypatch, ["test_star"])
    assert "ya estaban 1" in capsys.readouterr().out
    # fallback: la primera fuente no entrega PDF, la segunda sí
    (destdir / "1978oldW...1..1W.pdf").unlink()
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok:
                        [{"link_type": "ESOURCE|ADS_PDF", "url": "https://articles.adsabs.harvard.edu/pdf/x"},
                         {"link_type": "ESOURCE|PUB_PDF", "url": "https://pub/x.pdf"}])
    monkeypatch.setattr(fp, "download_pdf",
                        lambda url, tok: b"%PDF-pub" if "pub" in url else None)
    run_main(monkeypatch, ["test_star"])
    assert (destdir / "1978oldW...1..1W.pdf").read_bytes() == b"%PDF-pub"


def test_main_sin_ads_json(toy_vault, monkeypatch):
    assert run_main(monkeypatch, ["test_star"]) == 1
