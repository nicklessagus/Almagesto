"""fetch_web: post-clean determinista, header del snapshot, reuso de fecha, citekeys."""
import sys
from types import SimpleNamespace

import pytest

import fetch_web as fw
from conftest import read_fm

MD = ("# Título\n\nProsa citable con referencias.\n\n"
      "<video controls><source src='x.mp4'></video>\n\n\n\n"
      "<iframe src='ad'>basura</iframe>\n\n"
      "<figure>una figura con texto que SÍ se conserva</figure>\n\n"
      "<source src='suelto.mp4'/>\n\nMás prosa.\n")


# ── clean_markdown ───────────────────────────────────────────────────────────

def test_clean_saca_media_conserva_prosa():
    out, removed = fw.clean_markdown(MD)
    assert "<video" not in out and "<iframe" not in out and "<source" not in out
    assert "SÍ se conserva" in out                   # figure no se toca
    assert "Prosa citable" in out and "Más prosa." in out
    assert removed == 3                              # video (con su source), iframe, source suelto
    assert "\n\n\n" not in out                       # saltos colapsados
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_clean_es_determinista():
    assert fw.clean_markdown(MD) == fw.clean_markdown(MD)


# ── snapshot_date_of / CITEKEY_RE ────────────────────────────────────────────

def test_snapshot_date_of(tmp_path):
    p = tmp_path / "s.txt"
    p.write_text("# header\nsource_url : http://x\nretrieved  : 2026-01-02 (UTC)\n", encoding="utf-8")
    assert fw.snapshot_date_of(p) == "2026-01-02"
    p2 = tmp_path / "no.txt"
    p2.write_text("sin fecha", encoding="utf-8")
    assert fw.snapshot_date_of(p2) is None
    assert fw.snapshot_date_of(tmp_path / "inexistente.txt") is None


@pytest.mark.parametrize("key,ok", [
    ("2006RasmussenWilliams", True),
    ("1999a", True),
    ("RasmussenWilliams2006", False),
    ("20001", False),                # falta la letra tras el año
    ("200Ras", False),
])
def test_citekey_re(key, ok):
    assert bool(fw.CITEKEY_RE.match(key)) is ok


# ── main() con defuddle mockeado ─────────────────────────────────────────────

@pytest.fixture
def fake_defuddle(monkeypatch):
    state = SimpleNamespace(md=MD, fetched=[])

    def fetch(url):
        state.fetched.append(url)
        return state.md
    monkeypatch.setattr(fw, "shutil", SimpleNamespace(which=lambda c: "/usr/bin/npx"))
    monkeypatch.setattr(fw, "fetch", fetch)
    monkeypatch.setattr(fw, "defuddle_version", lambda: "1.0-fake")
    return state


def run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["fetch_web.py", *argv])
    return fw.main()


ARGS = ["gp", "2006RasmussenWilliams", "https://example.org/gp",
        "--concept", "gaussian-processes", "--title", "GP review", "--author", "Rasmussen",
        "--year", "2000", "--n-authors", "2", "--doi", "10.1/gp"]


def test_main_snapshot_y_nota(toy_vault, fake_defuddle, monkeypatch):
    assert run_main(monkeypatch, ARGS) == 0
    txt = (toy_vault.FULLTEXT / "gp" / "2006RasmussenWilliams.txt").read_text(encoding="utf-8")
    assert "source_url : https://example.org/gp" in txt
    assert "retrieved  :" in txt and "citekey    : 2006RasmussenWilliams" in txt
    assert "Prosa citable" in txt and "<video" not in txt
    note = toy_vault.PAPERS / "2006RasmussenWilliams.md"
    fm = read_fm(note)
    assert fm["bibcode"] == "2006RasmussenWilliams"
    assert fm["source_url"] == "https://example.org/gp"
    assert fm["thesis_links"] == ["gaussian-processes"]
    assert fm["doi"] == "10.1/gp" and fm["n_authors"] == 2 and fm["year"] == 2000
    assert fm["tags"] == ["paper", "web"]
    # la fecha de la nota coincide con la del snapshot
    assert f"retrieved  : {fm['accessed']}" in txt


def test_main_citekey_invalida(toy_vault, fake_defuddle, monkeypatch):
    with pytest.raises(SystemExit, match="citekey inválida"):
        run_main(monkeypatch, ["gp", "SinAnio", "https://example.org"])


def test_main_snapshot_vacio(toy_vault, fake_defuddle, monkeypatch):
    fake_defuddle.md = "   "
    assert run_main(monkeypatch, ARGS) == 1
    assert not (toy_vault.FULLTEXT / "gp" / "2006RasmussenWilliams.txt").exists()
    assert not (toy_vault.PAPERS / "2006RasmussenWilliams.md").exists()


def test_main_idempotente_reusa_fecha_del_snapshot(toy_vault, fake_defuddle, monkeypatch):
    d = toy_vault.FULLTEXT / "gp"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2006RasmussenWilliams.txt").write_text(
        "# header\nsource_url : x\nretrieved  : 2020-05-05 (UTC)\ncontenido viejo\n", encoding="utf-8")
    assert run_main(monkeypatch, ARGS) == 0
    assert fake_defuddle.fetched == []               # no re-baja
    fm = read_fm(toy_vault.PAPERS / "2006RasmussenWilliams.md")
    assert fm["accessed"] == "2020-05-05"            # la nota usa la fecha original


def test_main_no_note(toy_vault, fake_defuddle, monkeypatch):
    assert run_main(monkeypatch, [*ARGS, "--no-note"]) == 0
    assert not (toy_vault.PAPERS / "2006RasmussenWilliams.md").exists()
