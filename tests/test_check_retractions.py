"""check_retractions: parseo Crossref, fallback por título, estampado idempotente."""
import sys
from types import SimpleNamespace

import pytest
import requests as real_requests

import check_retractions as cr
from conftest import mk_note, read_fm


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload = status, payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def patch_net(monkeypatch, responses, calls=None):
    seq = list(responses)

    def get(url, headers=None, timeout=None):
        if calls is not None:
            calls.append(url)
        if isinstance(seq[0], Exception):
            raise seq.pop(0) if len(seq) > 1 else seq[0]
        return seq.pop(0) if len(seq) > 1 else seq[0]
    monkeypatch.setattr(cr, "requests",
                        SimpleNamespace(get=get, RequestException=real_requests.RequestException))
    monkeypatch.setattr(cr, "time", SimpleNamespace(sleep=lambda s: None))


RETRACTION_MSG = {"message": {"updated-by": [
    {"type": "Retraction", "DOI": "10.1/notice",
     "updated": {"date-parts": [[2021, 5, 3]]}, "source": "publisher"}]}}


# ── unidades ─────────────────────────────────────────────────────────────────

def test_split_note_preserva_cuerpo(tmp_path):
    body = "\n# Título\n\nProsa.\n\n---\nregla horizontal en el cuerpo\n"
    p = tmp_path / "n.md"
    p.write_text(f"---\nbibcode: x\ntags:\n- paper\n---{body}", encoding="utf-8")
    fm, got_body = cr.split_note(p.read_text(encoding="utf-8"))
    assert fm["bibcode"] == "x"
    assert got_body == body                          # maxsplit=2 preserva el --- del cuerpo


RET = {"type": "retraction", "notice_doi": "10.1/n", "date": "2021-05-03", "source": "publisher"}


def test_stamp_retraction_preserva_comentarios_y_cuerpo(tmp_path):
    """Regresión (hallazgo 3): el estampado es quirúrgico — no re-serializa el YAML,
    los comentarios/orden de la extracción LLM sobreviven."""
    body = "\ncuerpo\n\n---\nregla horizontal\n"
    p = tmp_path / "n.md"
    p.write_text("---\nbibcode: x\nmethods: [gp]  # anotado por el LLM\ntags:\n- paper\n"
                 f"---{body}", encoding="utf-8")
    fm, got_body = cr.split_note(p.read_text(encoding="utf-8"))
    cr.stamp_retraction(p, fm, got_body, RET)
    text = p.read_text(encoding="utf-8")
    assert "# anotado por el LLM" in text            # comentario intacto
    assert body in text                              # cuerpo intacto (con su ---)
    fm2, _ = cr.split_note(text)
    assert fm2["retracted"] is True and fm2["retraction"] == RET


def test_stamp_retraction_reemplaza_bloque_previo(tmp_path):
    """Re-chequeo con --force: el bloque retraction viejo se reemplaza, no se duplica."""
    p = tmp_path / "n.md"
    p.write_text("---\nbibcode: x\ntags:\n- paper\n---\ncuerpo\n", encoding="utf-8")
    fm, body = cr.split_note(p.read_text(encoding="utf-8"))
    cr.stamp_retraction(p, fm, body, RET)
    fm, body = cr.split_note(p.read_text(encoding="utf-8"))
    cr.stamp_retraction(p, fm, body, dict(RET, date="2022-01-01"))
    text = p.read_text(encoding="utf-8")
    assert text.count("retraction:") == 1 and text.count("retracted:") == 1
    fm2, _ = cr.split_note(text)
    assert fm2["retraction"]["date"] == "2022-01-01"


def test_split_note_sin_frontmatter():
    assert cr.split_note("texto plano") == (None, "texto plano")
    assert cr.split_note("---\nyaml: [roto\n---\n") == (None, "---\nyaml: [roto\n---\n")


def test_upd_date():
    assert cr._upd_date({"updated": {"date-parts": [[2021, 5, 3]]}}) == "2021-05-03"
    assert cr._upd_date({"updated": {"date-parts": [[2021]]}}) == "2021"
    assert cr._upd_date({}) is None


def test_title_says_retracted():
    assert cr.title_says_retracted("RETRACTED: On planets")
    assert cr.title_says_retracted("Retraction: something")
    assert cr.title_says_retracted("Withdrawn manuscript")
    assert not cr.title_says_retracted("Retrograde orbits")
    assert not cr.title_says_retracted(None)


def test_crossref_retraction_parsea(monkeypatch):
    patch_net(monkeypatch, [FakeResp(200, RETRACTION_MSG)])
    ret, soft = cr.crossref_retraction("10.1/x", {})
    assert ret == {"type": "retraction", "notice_doi": "10.1/notice",
                   "date": "2021-05-03", "source": "publisher"}
    assert soft == []


def test_crossref_soft_no_retracta(monkeypatch):
    patch_net(monkeypatch, [FakeResp(200, {"message": {"updated-by": [{"type": "erratum"}]}})])
    ret, soft = cr.crossref_retraction("10.1/x", {})
    assert ret is None and soft == ["erratum"]


def test_crossref_tolerante_a_errores(monkeypatch):
    patch_net(monkeypatch, [FakeResp(404)])
    assert cr.crossref_retraction("10.1/x", {}) == (None, [])
    patch_net(monkeypatch, [FakeResp(500)])
    assert cr.crossref_retraction("10.1/x", {}) == (None, [])
    patch_net(monkeypatch, [real_requests.ConnectionError("sin red")])
    assert cr.crossref_retraction("10.1/x", {}) == (None, [])
    patch_net(monkeypatch, [FakeResp(200, None)])    # 200 con cuerpo no-json
    assert cr.crossref_retraction("10.1/x", {}) == (None, [])


# ── main() ───────────────────────────────────────────────────────────────────

def run_main(monkeypatch, argv=()):
    monkeypatch.setattr(sys, "argv", ["check_retractions.py", *argv])
    return cr.main()


def test_main_marca_y_es_idempotente(toy_vault, monkeypatch, capsys):
    body = "# Paper\n\nExtracción LLM.\n\n---\nregla horizontal\n"
    mk_note(toy_vault.PAPERS, "2020retR...1..1R",
            {"bibcode": "2020retR...1..1R", "title": "Un paper", "doi": "10.1/x",
             "tags": ["paper"]}, body)
    calls = []
    patch_net(monkeypatch, [FakeResp(200, RETRACTION_MSG)], calls)
    assert run_main(monkeypatch) == 1
    note = toy_vault.PAPERS / "2020retR...1..1R.md"
    fm = read_fm(note)
    assert fm["retracted"] is True
    assert fm["retraction"]["type"] == "retraction" and fm["retraction"]["date"] == "2021-05-03"
    assert body.strip() in note.read_text(encoding="utf-8")   # cuerpo intacto
    assert len(calls) == 1
    # segunda corrida: no re-consulta, sigue saliendo 1 (sigue retractado)
    assert run_main(monkeypatch) == 1
    assert len(calls) == 1
    assert "ya marcado" in capsys.readouterr().out


def test_main_limpio_no_marca(toy_vault, monkeypatch):
    mk_note(toy_vault.PAPERS, "2020okA....1..1A",
            {"bibcode": "2020okA....1..1A", "title": "Sano", "doi": "10.1/ok", "tags": ["paper"]}, "")
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})])
    assert run_main(monkeypatch) == 0
    assert "retracted" not in read_fm(toy_vault.PAPERS / "2020okA....1..1A.md")


def test_main_fallback_por_titulo_sin_doi(toy_vault, monkeypatch, capsys):
    mk_note(toy_vault.PAPERS, "1990oldR...1..1R",
            {"bibcode": "1990oldR...1..1R", "title": "RETRACTED: Old result",
             "doi": None, "tags": ["paper"]}, "")
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], calls)
    assert run_main(monkeypatch) == 1
    fm = read_fm(toy_vault.PAPERS / "1990oldR...1..1R.md")
    assert fm["retracted"] is True
    assert "title-prefix" in fm["retraction"]["source"]
    assert calls == []                               # sin DOI no consulta Crossref


def test_main_soft_avisa_sin_marcar(toy_vault, monkeypatch, capsys):
    mk_note(toy_vault.PAPERS, "2020errE...1..1E",
            {"bibcode": "2020errE...1..1E", "title": "Con errata", "doi": "10.1/e",
             "tags": ["paper"]}, "")
    patch_net(monkeypatch, [FakeResp(200, {"message": {"updated-by": [{"type": "erratum"}]}})])
    assert run_main(monkeypatch) == 0
    assert "corrección no-retractante (erratum)" in capsys.readouterr().out
    assert "retracted" not in read_fm(toy_vault.PAPERS / "2020errE...1..1E.md")


def test_main_avisa_nota_no_parseable(toy_vault, monkeypatch, capsys):
    """Regresión (hallazgo 4): una nota con YAML roto ya no se saltea EN SILENCIO."""
    p = toy_vault.PAPERS / "2020rotoX..1..1X.md"
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: RETRACTED: sin comillas\ntags:\n- paper\n---\ncuerpo\n",
                 encoding="utf-8")
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], calls)
    assert run_main(monkeypatch) == 0
    assert "sin frontmatter parseable" in capsys.readouterr().out
    assert calls == []


def test_main_saltea_notas_no_paper(toy_vault, monkeypatch):
    mk_note(toy_vault.PAPERS, "no-paper", {"doi": "10.1/x", "tags": ["query"]}, "")
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], calls)
    assert run_main(monkeypatch) == 0
    assert calls == []


def test_main_paper_puntual(toy_vault, monkeypatch, capsys):
    mk_note(toy_vault.PAPERS, "2020unoA...1..1A",
            {"bibcode": "2020unoA...1..1A", "title": "t", "doi": "10.1/a", "tags": ["paper"]}, "")
    mk_note(toy_vault.PAPERS, "2020dosB...1..1B",
            {"bibcode": "2020dosB...1..1B", "title": "t", "doi": "10.1/b", "tags": ["paper"]}, "")
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], calls)
    assert run_main(monkeypatch, ["--paper", "2020unoA...1..1A"]) == 0
    assert len(calls) == 1
    assert run_main(monkeypatch, ["--paper", "2020nadaX..1..1X"]) == 0
    assert "no existe" in capsys.readouterr().out
