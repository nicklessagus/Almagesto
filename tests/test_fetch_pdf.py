"""fetch_pdf: resolver ADS (esources), higiene del token, magic %PDF, residuo missing_pdf."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests as real_requests

import fetch_pdf as fp
import lib_config as cfg
from conftest import mk_note


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


def test_is_ads_host_no_acepta_lookalike():
    """`netloc.endswith("adsabs.harvard.edu")` sin chequear el punto de borde acepta
    "xadsabs.harvard.edu" como si fuera un subdominio de ADS — y el token Bearer viaja ahí
    (higiene de credenciales: la garantía documentada es que el token SÓLO va a
    *.adsabs.harvard.edu)."""
    assert fp.is_ads_host("https://xadsabs.harvard.edu/x") is False


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


@pytest.fixture(autouse=True)
def _sin_resolver_oa(monkeypatch):
    """#358: el carril ADS cae al resolver de acceso abierto al agotar los `esource`. Por default
    acá no propone nada (y no sale a la red, INV-114); los tests propios lo re-parchean."""
    monkeypatch.setattr(fp, "oa_candidates", lambda doi, title=None: iter([]))


# ── esource_records ──────────────────────────────────────────────────────────

def test_esource_records_forma_multiple(monkeypatch):
    patch_net(monkeypatch, [FakeResp(200, {"links": {"records": PROBE_RECORDS}})])
    assert fp.esource_records("1978ApJ...226..379W", "tok") == PROBE_RECORDS


def test_esource_records_forma_link_unico(monkeypatch):
    patch_net(monkeypatch, [FakeResp(200, {"action": "redirect", "link": "https://x/p.pdf",
                                           "link_type": "ESOURCE|PUB_PDF"})])
    recs = fp.esource_records("2020X", "tok")
    assert recs == [{"url": "https://x/p.pdf", "link_type": "ESOURCE|PUB_PDF"}]


def test_esource_records_tolerante(monkeypatch, capsys):
    """Tolerar la caída es correcto; fusionarla con «no hay PDF» no (AUD-162).

    Son dos estados que piden cosas distintas: *el resolver contestó y este paper no tiene PDF*
    manda a rescate manual (que es lo que el `hint` de `missing_pdf.json` propone), y *el resolver
    no contestó* manda a re-correr la cadena — no hay nada que rescatar a mano. El `[]` se mantiene
    (cambiar la firma movería a todos los llamadores) y la diferencia se DICE."""
    for respuesta in ([FakeResp(404)], [real_requests.ConnectionError("sin red")],
                      [FakeResp(200, None)]):
        capsys.readouterr()
        patch_net(monkeypatch, respuesta)
        assert fp.esource_records("x", "tok") == []
        err = capsys.readouterr().err
        assert "nadie preguntó" in err or "no es JSON" in err

    # el resolver que SÍ contestó y no tiene fuentes no dice nada: ése es el caso normal
    capsys.readouterr()
    patch_net(monkeypatch, [FakeResp(200, {"links": {"records": []}})])
    assert fp.esource_records("x", "tok") == []
    assert capsys.readouterr().err == ""


def test_esource_manda_token_al_resolver(monkeypatch):
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"links": {"records": []}})], calls)
    fp.esource_records("x", "tok-123")
    assert calls[0]["headers"]["Authorization"] == "Bearer tok-123"


def test_resolver_con_forma_inesperada_no_revienta(monkeypatch):
    """`fetch_pdf.py:116` — `recs = (data.get("links") or {}).get("records") or []`.

    El docstring de `esource_records` promete `[]` "si no hay o falla (tolerante — un resolver
    caído no aborta el barrido)", y los tests existentes cubren 404, `ConnectionError` y JSON
    ilegible. Lo que NO cubren es un JSON **legal con otra forma**: `links` escalar revienta en el
    segundo `.get`, y `records` escalar entrega los caracteres a `candidate_urls`, donde
    `r.get("link_type")` muere. Un barrido de PDFs de 900 papers se corta en el primero."""
    class FakeResp:
        status_code = 200

        def __init__(self, payload):
            self._p = payload

        def json(self):
            return self._p

    def patch(payload):
        monkeypatch.setattr(
            __import__("fetch_pdf"), "requests",
            type("R", (), {"get": staticmethod(lambda *a, **k: FakeResp(payload)),
                           "RequestException": Exception})())

    patch({"links": "https://x/p.pdf"})
    assert fp.esource_records("2020X", "tok") == []
    patch({"links": {"records": "abc"}})
    assert fp.candidate_urls(fp.esource_records("2020X", "tok")) == []


# ── download_pdf ─────────────────────────────────────────────────────────────

def test_download_pdf_ok_y_magic(monkeypatch):
    patch_net(monkeypatch, [FakeResp(200, content=b"%PDF-1.5 data")])
    assert fp.download_pdf("https://articles.adsabs.harvard.edu/pdf/x", "tok") == b"%PDF-1.5 data"
    patch_net(monkeypatch, [FakeResp(200, content=b"<html>paywall</html>")])
    assert fp.download_pdf("https://pub/x.pdf", "tok") is None      # HTML no se guarda


def test_download_pdf_token_solo_a_ads(monkeypatch):
    # @inv INV-67
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


# ── cascada manual de rescate (#50) ──────────────────────────────────────────

def test_rescue_hint_por_bibstem():
    """El bibstem del fallo orienta la rama de la cascada manual (#50)."""
    assert "Messenger" in fp.rescue_hint("Msngr", 2015)
    assert "instrumento" in fp.rescue_hint("SPIE", 2004)
    # A&A pre-arXiv: no hay preprint y aanda.org está tras DataDome → derivar al usuario
    assert "derivar al usuario" in fp.rescue_hint("A&A", 2001)
    assert "derivar al usuario" in fp.rescue_hint("A&AS", 1996)


def test_rescue_hint_fallback_generico():
    """A&A moderno (con preprint) y bibstems sin rama propia caen al genérico, no al de DataDome."""
    for stem, year in [("A&A", 2020), ("ApJ", 1978), (None, None), ("", 2001)]:
        assert "derivar al usuario" not in fp.rescue_hint(stem, year)
        assert fp.rescue_hint(stem, year)
    assert "mirror" in fp.rescue_hint("ApJ", "no-es-año")     # year basura no rompe


# ── main() ───────────────────────────────────────────────────────────────────

RECORDS = [
    {"bibcode": "1978oldW...1..1W", "title": "viejo sin arxiv", "relevant": True,
     "arxiv_id": None, "doi": "10.1/w", "bibstem": "ApJ", "year": "1978"},
    {"bibcode": "2020newA...1..1A", "title": "con arxiv", "relevant": True,
     "arxiv_id": "2101.00001", "doi": "10.1/a", "bibstem": "A&A", "year": "2020"},
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


def test_main_baja_todo_relevante_sin_pdf(toy_vault, monkeypatch):
    """Regresión #32: el barrido es por verdad de disco — cubre el sin-arXiv Y el con-arXiv cuya
    bajada falló en fetch_arxiv (antes ese quedaba invisible). El no-core nunca se intenta."""
    ads_json(toy_vault.ROOT, "test_star", RECORDS)
    pedidos = []
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: pedidos.append(bib) or
                        [{"link_type": "ESOURCE|ADS_PDF", "url": f"https://articles.adsabs.harvard.edu/pdf/{bib}"}])
    monkeypatch.setattr(fp, "download_pdf", lambda url, tok: b"%PDF-fake")
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert pedidos == ["1978oldW...1..1W", "2020newA...1..1A"]     # rescate arXiv fallido; no-core afuera
    assert (toy_vault.PDFS / "test_star" / "1978oldW...1..1W.pdf").read_bytes() == b"%PDF-fake"
    assert (toy_vault.PDFS / "test_star" / "2020newA...1..1A.pdf").read_bytes() == b"%PDF-fake"


def test_main_arxiv_ya_bajado_no_se_toca(toy_vault, monkeypatch):
    """El con-arXiv que fetch_arxiv SÍ bajó no se re-pide al resolver (verdad de disco)."""
    ads_json(toy_vault.ROOT, "test_star", RECORDS)
    destdir = toy_vault.PDFS / "test_star"
    destdir.mkdir(parents=True, exist_ok=True)
    (destdir / "2020newA...1..1A.pdf").write_bytes(b"%PDF-arxiv")
    pedidos = []
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: pedidos.append(bib) or [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert pedidos == ["1978oldW...1..1W"]


def test_main_residuo_en_missing_pdf(toy_vault, monkeypatch):
    d = ads_json(toy_vault.ROOT, "test_star", RECORDS)
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    miss = json.loads((d / "missing_pdf.json").read_text())
    assert [m["bibcode"] for m in miss] == ["1978oldW...1..1W", "2020newA...1..1A"]
    assert miss[0]["doi"] == "10.1/w"                # residuo completo del ingest (#32)
    # #50: cada entrada trae el bibstem y la rama de la cascada manual por donde seguir
    assert miss[0]["bibstem"] == "ApJ" and miss[0]["year"] == "1978"
    assert miss[0]["hint"] and miss[1]["hint"]


RECORDS_LIMIT = [
    {"bibcode": f"202{i}xxxA...1..{i}A", "title": f"paper {i}", "relevant": True,
     "arxiv_id": None, "doi": f"10.1/{i}", "bibstem": "ApJ", "year": "2020"}
    for i in range(4)
]


def test_main_limit_no_borra_el_residuo_completo(toy_vault, monkeypatch):
    """4 papers relevantes sin PDF; `--limit 1` sólo intenta el primero (y lo consigue). Antes:
    como `missing` (calculado SOLO sobre lo intentado) daba vacío, el código borraba
    `missing_pdf.json` entero — perdiendo el residuo de fetch_arxiv sobre los otros 3 papers que
    ni se miraron esta corrida. Medido en el hallazgo: "4 papers, 1 bajado, residuo borrado,
    cierre sin conseguir 0" — un residuo que el docstring llama "COMPLETO del ingest" deja de
    serlo bajo --limit, así que no debería tocarse."""
    d = ads_json(toy_vault.ROOT, "test_star", RECORDS_LIMIT)
    residuo_previo = [{"bibcode": r["bibcode"], "title": r["title"], "doi": r["doi"]}
                      for r in RECORDS_LIMIT[1:]]      # lo que fetch_arxiv habría dejado
    (d / "missing_pdf.json").write_text(json.dumps(residuo_previo), encoding="utf-8")
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok:
                        [{"link_type": "ESOURCE|ADS_PDF", "url": f"https://articles.adsabs.harvard.edu/pdf/{bib}"}])
    monkeypatch.setattr(fp, "download_pdf", lambda url, tok: b"%PDF-fake")
    assert run_main(monkeypatch, ["test_star", "--limit", "1"]) == 0
    assert (d / "missing_pdf.json").exists(), (
        "el residuo de los 3 papers sin intentar se borró: --limit no debería tocar un residuo "
        "que no puede ser completo")


def test_main_residuo_hint_por_bibstem(toy_vault, monkeypatch, capsys):
    """Un Msngr que el resolver no entrega sale orientado al archivo abierto de The Messenger."""
    d = ads_json(toy_vault.ROOT, "test_star", [
        {"bibcode": "2015Msngr.162....9L", "title": "fibras de HARPS", "relevant": True,
         "arxiv_id": None, "doi": None, "bibstem": "Msngr", "year": "2015"}])
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: [])
    assert run_main(monkeypatch, ["test_star"]) == 0
    miss = json.loads((d / "missing_pdf.json").read_text())
    assert "Messenger" in miss[0]["hint"]
    assert "Messenger" in capsys.readouterr().out          # también orienta en el stdout del ingest


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
    (destdir / "2020newA...1..1A.pdf").write_bytes(b"%PDF-ya")
    monkeypatch.setattr(fp, "esource_records",
                        lambda bib, tok: (_ for _ in ()).throw(AssertionError("no debería consultar")))
    run_main(monkeypatch, ["test_star"])
    assert "ya estaban 2" in capsys.readouterr().out
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


# ═══════════════════════════════════════════════════════════════════════════
# H-07 · fetch_pdf.py — PDF truncado congelado para siempre
# ═══════════════════════════════════════════════════════════════════════════
#
# Decisión: en vez de agregar un umbral de tamaño al chequeo "¿ya está en disco?" (que rompería
# fixtures de tests existentes con PDFs de juguete de pocos bytes, usados como "ya bajado
# válido"), se ataca la RAÍZ: la escritura del PDF final deja de ser `dest.write_bytes(...)`
# directo (no atómica: un corte a mitad deja lo que se llegó a escribir en el destino FINAL) y
# pasa a ser temporal-mismo-dir + `os.replace` (mismo patrón que `lib_config.save_registro` /
# `fetch_ground_truth.write_ground_truth`). Con esto un corte YA NO puede dejar nada truncado en
# el destino: o el PDF completo se publica, o `dest` sigue sin existir.

def _interceptor_write_bytes(dest_name: str):
    """Parcha `Path.write_bytes` para simular un corte a mitad de la escritura del PDF que
    termina en `dest_name` (exacto, la escritura vieja no-atómica) O que EMPIEZA con `dest_name`
    (el temporal `<dest>.tmpNNN` de la escritura atómica nueva) — así el mismo test funciona
    idéntico contra el código viejo (escribe directo al destino final) y el nuevo (escribe a un
    temporal y publica con `os.replace`), sin depender de qué función interna exista."""
    real_write_bytes = Path.write_bytes

    def corte(self, data, *a, **k):
        if self.name == dest_name or self.name.startswith(dest_name + ".tmp"):
            real_write_bytes(self, bytes(data)[: len(data) // 2])
            raise OSError("disco lleno a mitad del corte")
        return real_write_bytes(self, data, *a, **k)
    return corte


def test_fetch_pdf_no_deja_pdf_truncado_en_el_destino(toy_vault, monkeypatch):
    """Mismo defecto que en `fetch_arxiv.py` (ver `test_fetch_arxiv.py`), del lado de
    `fetch_pdf.py` (la otra vía de bajada, vía resolver de ADS)."""
    d = ads_json(toy_vault.ROOT, "test_star", RECORDS_LIMIT[:1])
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok:
                        [{"link_type": "ESOURCE|ADS_PDF",
                          "url": f"https://articles.adsabs.harvard.edu/pdf/{bib}"}])
    monkeypatch.setattr(fp, "download_pdf", lambda url, tok: b"%PDF-contenido-completo-del-paper")
    destdir = toy_vault.PDFS / "test_star"
    destdir.mkdir(parents=True, exist_ok=True)
    dest = destdir / f"{fp.safe_name(RECORDS_LIMIT[0]['bibcode'])}.pdf"
    monkeypatch.setattr(Path, "write_bytes", _interceptor_write_bytes(dest.name))
    try:
        run_main(monkeypatch, ["test_star"])
    except OSError:
        pass    # versión sin atomicidad: la excepción del corte escapa sin capturar
    assert not dest.exists(), (
        "quedó un PDF (parcial) en el destino final tras un corte de escritura — la próxima "
        "corrida lo va a contar como 'ya bajado' y nunca lo va a reintentar (H-07)")


# ── consolas no-UTF8: fetch_pdf muere con UnicodeEncodeError bajo ascii (medido) ──

def test_unicode_no_muere_en_consola_ascii(toy_vault, monkeypatch):
    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding="ascii", errors="strict")
    monkeypatch.setattr(sys, "stdout", wrapper)
    monkeypatch.setattr(sys, "argv", ["fetch_pdf.py", "test_star"])
    rc = fp.main()          # sin ads.json: imprime "Corré primero query_ads.py ..." (con tilde)
    wrapper.flush()
    assert rc == 1
    assert b"query_ads" in buf.getvalue()


def test_pdf_bajo_otro_slug_no_va_a_la_red(toy_vault, monkeypatch, capsys):
    """D-18: el mismo paper relevante para dos sujetos se bajaba dos veces (medido: 33 copias en la
    instancia). El PDF es idéntico —mismo bibcode— y la red es el recurso caro y el que puede
    fallar. `requests` revienta si lo llaman: el test pasa **sólo** si reusó."""
    (toy_vault.PDFS / "otro_slug").mkdir(parents=True, exist_ok=True)
    (toy_vault.PDFS / "otro_slug" / "2020aaa...1..1A.pdf").write_bytes(b"%PDF-1.4 contenido")
    ads_json(toy_vault.ROOT, "test_star",
             [{"bibcode": "2020aaa...1..1A", "relevant": True, "title": "t",
               "doi": "10.1/a", "arxiv_id": None, "bibstem": "ApJ"}])
    def boom(*a, **k):
        raise AssertionError("fue a la red teniendo el PDF en disco bajo otro slug")
    monkeypatch.setattr(fp, "requests", SimpleNamespace(get=boom, RequestException=Exception))
    assert run_main(monkeypatch, ["test_star"]) == 0
    copiado = toy_vault.PDFS / "test_star" / "2020aaa...1..1A.pdf"
    assert copiado.exists() and copiado.read_bytes() == b"%PDF-1.4 contenido"
    assert "ya estaba" in capsys.readouterr().out


# ── --force es la vía de escape para un PDF truncado (auditoría P0) ─────────

def test_force_no_reusa_la_copia_de_otro_slug(toy_vault, monkeypatch, capsys):
    """P0. El bucle de reuso D-18 no consultaba `args.force`, a diferencia de su gemelo en
    `fetch_arxiv`. `--force` es la ÚNICA vía documentada para reemplazar un PDF truncado o
    congelado, y el reuso lo sobreescribía con la copia de otro slug —sin validar `%PDF`— y lo
    sacaba de pendientes: la escotilla hacía lo contrario de lo que promete."""
    (cfg.PDFS / "otro_slug").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "otro_slug" / "2020A.pdf").write_bytes(b"%PDF-1.4 copia de otro slug")
    (cfg.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "test_star" / "2020A.pdf").write_bytes(b"%PDF-1.4 TRUNCADO")
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text(json.dumps({"slug": "test_star", "records": [
        {"bibcode": "2020A", "relevant": True, "arxiv_id": None, "doi": "10.1/a",
         "bibstem": "A&A", "title": "t", "year": 2020}]}), encoding="utf-8")

    monkeypatch.setattr(cfg, "get_ads_token", lambda: "tok")
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: [])
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["fetch_pdf.py", "test_star", "--force"])
    fp.main()
    out = capsys.readouterr().out
    assert "copiado" not in out, "con --force no se reusa: se re-intenta la bajada"
    assert "1 sin PDF → resolver de ADS" in out, "el paper tiene que llegar a `todo`"
    assert (cfg.PDFS / "test_star" / "2020A.pdf").read_bytes() == b"%PDF-1.4 TRUNCADO", \
        "sin bajada exitosa el archivo viejo queda; lo que no puede es ser pisado por el de otro slug"


def test_sin_force_sigue_reusando_entre_slugs(toy_vault, monkeypatch, capsys):
    """Regresión de D-18: el reuso es la optimización que evita 33 bajadas idénticas."""
    (cfg.PDFS / "otro_slug").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "otro_slug" / "2020A.pdf").write_bytes(b"%PDF-1.4 copia")
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text(json.dumps({"slug": "test_star", "records": [
        {"bibcode": "2020A", "relevant": True, "arxiv_id": None, "doi": "10.1/a",
         "bibstem": "A&A", "title": "t", "year": 2020}]}), encoding="utf-8")
    monkeypatch.setattr(cfg, "get_ads_token", lambda: "tok")
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: [])
    monkeypatch.setattr(sys, "argv", ["fetch_pdf.py", "test_star"])
    fp.main()
    assert "copiado" in capsys.readouterr().out
    assert (cfg.PDFS / "test_star" / "2020A.pdf").read_bytes() == b"%PDF-1.4 copia"


def test_all_no_resucita_un_descarte_vigente(toy_vault, monkeypatch, capsys):
    """AUD-137 — `--all` significa «incluí los no-relevantes», no «ignorá la curación».

    Un paper que el usuario sacó con `triage --drop-core` queda en el registro justamente para que
    siga VISIBLE (`via: manual-drop`, con su motivo), y #112 le borra los artefactos de disco a
    propósito. Ninguno de los dos fetchers consultaba `load_decisiones`, así que la escotilla
    volvía a bajar exactamente lo que la decisión mandó sacar: una decisión de curación que un
    script deshace en silencio es peor que no haberla tomado."""
    ads_json(toy_vault.ROOT, "test_star", RECORDS)
    cfg.save_decisiones("test_star", {
        "1990nonB...1..1B": {"decision": "descartado", "motivo": "off-topic", "fecha": "2026-08-28"},
        "2020newA...1..1A": {"decision": "anulada", "fecha": "2026-08-28",
                             "previa": {"decision": "descartado", "motivo": "viejo"}},
    })
    pedidos = []
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: pedidos.append(bib) or [])
    assert run_main(monkeypatch, ["test_star", "--all"]) == 0
    assert "1990nonB...1..1B" not in pedidos, "se re-pidió un descarte vigente"
    assert "2020newA...1..1A" in pedidos, "una decisión ANULADA ya no es un descarte (D-52)"
    assert "excluido(s) por decisión de curación" in capsys.readouterr().out


def test_no_re_baja_un_bibcode_que_ya_es_ALIAS_de_otra_nota(toy_vault):
    """D-19 — el preprint y el publicado son el MISMO trabajo, y el canónico ya está en disco.
    Sin esta guarda, la corrida siguiente a un `--rename-paper` re-bajaba el preprint y dejaba un
    par PDF+`.txt` que el lint reporta como artefacto colgado **para siempre**."""
    mk_note(cfg.PAPERS, "2026RASTI...5ag038F",
            {"bibcode": "2026RASTI...5ag038F", "tags": ["paper"], "stars": ["X"],
             "versions": [{"bibcode": "2026arXiv260528635F", "tipo": "eprint"}]}, "# p\n")
    recs = [{"bibcode": "2026arXiv260528635F"}, {"bibcode": "2020otro...1..1A"}]
    dentro, fuera = fp.drop_filter(recs, "ica")
    assert [r["bibcode"] for r in dentro] == ["2020otro...1..1A"]
    assert [r["bibcode"] for r in fuera] == ["2026arXiv260528635F"]


# ── #358 · el carril ADS cae al resolver de acceso abierto antes de rendirse ─────────────────────

def _oa_get(candidatos):
    """Doble de `fetch_pdf.oa_candidates` — misma forma que `discover.iter_pdf_candidates`:
    triples `(url, why, pdf_source)`."""
    return lambda doi, title=None: iter(candidatos)


def test_esource_agotado_cae_al_resolver_de_acceso_abierto(toy_vault, monkeypatch):
    """#358 — el simétrico de #313: el carril ADS sólo probaba los `esource` de ADS y se rendía sin
    preguntarle al resolver que el otro carril usa. Medido: 2 de 6 «sin conseguir» de un tema eran
    open access, y `discover.py --resolve` ya devolvía la URL de los dos."""
    ads_json(toy_vault.ROOT, "test_star", RECORDS[:1])
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: [])
    pedidos = []
    monkeypatch.setattr(fp, "oa_candidates", lambda doi, title=None: pedidos.append(doi) or
                        iter([("https://plos/x.pdf", "OpenAlex best_oa_location", "publisher")]))
    monkeypatch.setattr(fp, "download_pdf", lambda url, tok: b"%PDF-oa" if "plos" in url else None)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert pedidos == ["10.1/w"]
    assert (toy_vault.PDFS / "test_star" / "1978oldW...1..1W.pdf").read_bytes() == b"%PDF-oa"
    src = json.loads((toy_vault.ROOT / "build" / "test_star" / "pdf_source.json").read_text())
    assert src["1978oldW...1..1W"] == "publisher", "#57: la procedencia viaja con el candidato"
    assert not (toy_vault.ROOT / "build" / "test_star" / "missing_pdf.json").exists()


def test_copia_libre_bloqueada_se_distingue_de_sin_copia_libre(toy_vault, monkeypatch, capsys):
    """#358 (3) — «no hay copia libre» y «la hubo y el host la bloqueó» salían idénticos (`sin
    conseguir` + rescate manual) y piden lo contrario: `pending:` el primero, otro depósito el
    segundo. Medido: OUP devolvía un desafío de Cloudflare con 200 sobre la URL que OpenAlex
    proponía."""
    recs = [dict(RECORDS[0]), dict(RECORDS[1], arxiv_id=None)]
    ads_json(toy_vault.ROOT, "test_star", recs)
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: [])
    monkeypatch.setattr(fp, "oa_candidates", lambda doi, title=None: iter(
        [("https://oup/cloudflare.pdf", "OpenAlex best_oa_location", None)] if doi == "10.1/w" else []))
    monkeypatch.setattr(fp, "download_pdf", lambda url, tok: None)
    assert run_main(monkeypatch, ["test_star"]) == 0
    out = capsys.readouterr().out
    miss = {m["bibcode"]: m for m in json.loads(
        (toy_vault.ROOT / "build" / "test_star" / "missing_pdf.json").read_text(encoding="utf-8"))}
    assert miss["1978oldW...1..1W"]["estado"] == "bloqueado"
    assert miss["1978oldW...1..1W"]["copias_libres"] == ["https://oup/cloudflare.pdf"]
    assert miss["2020newA...1..1A"]["estado"] == "sin-copia-libre"
    assert "bloqueó" in out and "sin copia libre" in out, out
    assert "sin conseguir 2 (1 con copia libre que el host bloqueó)" in out, out


def test_sin_doi_no_se_consulta_el_resolver(toy_vault, monkeypatch):
    """#358 — sin DOI no hay por dónde empezar: no se sale a la red por nada."""
    ads_json(toy_vault.ROOT, "test_star", [dict(RECORDS[0], doi=None)])
    monkeypatch.setattr(fp, "esource_records", lambda bib, tok: [])
    monkeypatch.setattr(fp, "oa_candidates",
                        lambda doi, title=None: pytest.fail("sin DOI no se consulta"))
    assert run_main(monkeypatch, ["test_star"]) == 0


def test_un_desafio_de_cloudflare_con_200_no_se_guarda_como_pdf(monkeypatch):
    """#358 (nota) — la URL de OUP devuelve HTML con 200: una bajada ingenua escribiría la página
    de Cloudflare con extensión `.pdf`. Los dos caminos (requests y el fallback curl) validan el
    magic `%PDF`."""
    html = b"<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>"
    patch_net(monkeypatch, [FakeResp(200, content=html)])
    monkeypatch.setattr(fp, "_curl_pdf", lambda url: None)
    assert fp.download_pdf("https://academic.oup.com/x.pdf", "tok") is None
    # el fallback curl entrega el mismo HTML: tampoco pasa (`_curl_pdf` valida el magic él mismo)
    monkeypatch.setattr(fp.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(fp.shutil, "which", lambda x: "/usr/bin/curl")
    monkeypatch.setattr(fp.Path, "read_bytes", lambda self: html)
    monkeypatch.setattr(fp.Path, "exists", lambda self: True)
    assert fp._curl_pdf("https://academic.oup.com/x.pdf") is None


_OA_CANDIDATES_REAL = fp.oa_candidates      # antes de que el fixture autouse lo reemplace


def test_oa_candidates_es_la_cascada_de_discover(monkeypatch):
    """#358 — el carril ADS no reimplementa el resolver: delega en `discover.iter_pdf_candidates`,
    la ÚNICA cascada del archivo del repo (si fueran dos, divergirían como #313 y #358)."""
    import discover
    monkeypatch.setattr(discover, "iter_pdf_candidates",
                        lambda doi, title=None: iter([(f"u:{doi}:{title}", "w", None)]))
    assert list(_OA_CANDIDATES_REAL("10.1/x", "T")) == [("u:10.1/x:T", "w", None)]
