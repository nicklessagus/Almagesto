"""fetch_arxiv: resume por HTTP Range, 200-que-ignora-Range, 429, magic %PDF, main()."""
import io
import json
import sys
from pathlib import Path
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


# ═══════════════════════════════════════════════════════════════════════════
# H-07 · fetch_arxiv.py — PDF truncado congelado para siempre
# ═══════════════════════════════════════════════════════════════════════════
#
# Decisión: en vez de agregar un umbral de tamaño al chequeo "¿ya está en disco?" (que rompería
# fixtures de tests existentes con PDFs de juguete de pocos bytes, usados como "ya bajado
# válido"), se ataca la RAÍZ: la escritura del PDF final deja de ser `dest.write_bytes(...)`
# directo (no atómica: un corte a mitad deja lo que se llegó a escribir en el destino FINAL) y
# pasa a ser temporal-mismo-dir + `os.replace` (mismo patrón que `lib_config.save_registro` /
# `fetch_ground_truth.write_ground_truth`). Con esto un corte YA NO puede dejar nada truncado en
# el destino: o el PDF completo se publica, o `dest` sigue sin existir. Como remedio manual para
# un PDF YA truncado por un corte ANTERIOR a este fix (que ninguna escritura atómica de ahora en
# más puede arreglar retroactivamente), se agrega `--force`.

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


def test_no_deja_pdf_truncado_en_el_destino(tmp_path, monkeypatch):
    """Simula un corte a mitad de la publicación final del PDF. El destino FINAL nunca debe
    quedar con contenido parcial: eso es lo que la próxima corrida cuenta como "ya bajado"
    (`dest.exists()`) y congela para siempre — nada valida magic/tamaño en disco, sólo al bajar
    (H-07, medido: un PDF de 35 B nunca se reintentó)."""
    class StreamResp:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_content(self, chunk_size):
            yield b"%PDF-contenido-completo-del-paper"

    monkeypatch.setattr(fa, "requests", SimpleNamespace(
        get=lambda *a, **k: StreamResp(), RequestException=real_requests.RequestException))
    monkeypatch.setattr(fa, "time", SimpleNamespace(sleep=lambda s: None))
    dest = tmp_path / "x.pdf"
    monkeypatch.setattr(Path, "write_bytes", _interceptor_write_bytes(dest.name))
    try:
        fa.download_pdf("2101.00001", dest)
    except OSError:
        pass    # versión sin atomicidad: la excepción del corte escapa sin capturar
    assert not dest.exists(), (
        "quedó un PDF (parcial) en el destino final tras un corte de escritura — la próxima "
        "corrida lo va a contar como 'ya bajado' y nunca lo va a reintentar (H-07)")


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


def test_main_fallo_arxiv_va_al_residuo(toy_vault, no_sleep, monkeypatch):
    """Regresión #32: una bajada arXiv FALLIDA entra a missing_pdf.json (antes sólo quedaba
    en el stdout — invisible para la cascada manual y para fetch_pdf)."""
    ads_json(toy_vault.ROOT, "test_star", RECORDS)
    monkeypatch.setattr(fa, "download_pdf", lambda aid, dest: False)
    assert run_main(monkeypatch, ["test_star"]) == 0
    miss = json.loads((toy_vault.ROOT / "build" / "test_star" / "missing_pdf.json").read_text())
    assert [m["bibcode"] for m in miss] == ["1990preA....1B", "2020withA...1A"]


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


def test_main_tiene_force_para_re_bajar_lo_congelado(toy_vault, monkeypatch):
    """Sin --force, un PDF ya en disco (aunque esté truncado por un corte previo a este fix)
    nunca se reintenta — no hay escape manual. `--force` lo da (H-07)."""
    d = toy_vault.ROOT / "build" / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"star": "Estrella Test", "records": [
        {"bibcode": "2020withA...1A", "title": "x", "relevant": True,
         "arxiv_id": "2101.00001", "doi": None}]}), encoding="utf-8")
    destdir = toy_vault.PDFS / "test_star"
    destdir.mkdir(parents=True, exist_ok=True)
    (destdir / "2020withA...1A.pdf").write_bytes(b"%PDF-trunc")   # simula un truncado congelado
    bajados = []
    monkeypatch.setattr(fa, "download_pdf", lambda aid, dest: bajados.append(aid) or True)
    run_main(monkeypatch, ["test_star", "--force"])
    assert bajados == ["2101.00001"], (
        "--force no existe todavía (o no fuerza la re-bajada): un PDF truncado por un corte "
        "anterior queda congelado para siempre, sin ninguna vía manual de recuperación")


# ── consolas no-UTF8: fetch_arxiv muere con UnicodeEncodeError bajo ascii (medido) ──

def test_unicode_no_muere_en_consola_ascii(toy_vault, monkeypatch):
    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding="ascii", errors="strict")
    monkeypatch.setattr(sys, "stdout", wrapper)
    monkeypatch.setattr(sys, "argv", ["fetch_arxiv.py", "test_star"])
    rc = fa.main()
    wrapper.flush()
    assert rc == 1
    assert b"query_ads" in buf.getvalue()
