"""extract_fulltext: umbrales de legibilidad, flujo pdftotext→OCR, degradación limpia."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import extract_fulltext as ef

GOOD_TEXT = "palabras normales de un paper con texto sano " * 12     # >200 chars ASCII
MOJIBAKE = "ˆÿþ" * 150                                # >200 chars, ~0% ASCII
GOOD_OCR = "texto rescatado por OCR perfectamente legible " * 10


# ── is_legible ───────────────────────────────────────────────────────────────

def test_legible_texto_sano():
    ok, why = ef.is_legible(GOOD_TEXT)
    assert ok and why == ""


def test_ilegible_casi_sin_texto():
    ok, why = ef.is_legible("   \f  \n corto ")
    assert not ok and "casi sin texto" in why


def test_ilegible_mojibake():
    ok, why = ef.is_legible(MOJIBAKE)
    assert not ok and "mojibake" in why


def test_legible_umbrales_limite():
    # valores literales a propósito (no ef.LEGIBLE_*): los umbrales son contrato documentado
    # (200 chars / 85% ASCII, compartidos con el lint) — si alguien los cambia, esto debe fallar.
    assert ef.is_legible("a" * 200)[0] is True
    assert ef.is_legible("a" * 199)[0] is False
    assert ef.is_legible("a" * 850 + "ÿ" * 150)[0] is True      # ratio == 0.85 pasa
    assert ef.is_legible("a" * 849 + "ÿ" * 151)[0] is False


# ── herramientas falsas ──────────────────────────────────────────────────────

@pytest.fixture
def fake_tools(monkeypatch):
    state = SimpleNamespace(pdftotext_out=GOOD_TEXT, pdftotext_rc=0, ocr=False,
                            tesseract_out=GOOD_OCR, calls=[])

    def which(cmd):
        if cmd == "pdftotext":
            return "/usr/bin/pdftotext"
        if cmd in ("tesseract", "pdftoppm"):
            return "/usr/bin/fake" if state.ocr else None
        return None

    def run(cmd, **kw):
        state.calls.append(cmd[0])
        if cmd[0] == "pdftotext":
            return SimpleNamespace(returncode=state.pdftotext_rc,
                                   stdout=state.pdftotext_out, stderr="err")
        if cmd[0] == "pdftoppm":
            root = Path(cmd[-1])
            (root.parent / f"{root.name}-1.png").write_bytes(b"png")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[0] == "tesseract":
            if "--version" in cmd:
                return SimpleNamespace(returncode=0, stdout="tesseract 5.0 fake", stderr="")
            return SimpleNamespace(returncode=0, stdout=state.tesseract_out, stderr="")
        raise AssertionError(f"comando inesperado: {cmd}")

    monkeypatch.setattr(ef, "shutil", SimpleNamespace(which=which))
    monkeypatch.setattr(ef, "subprocess", SimpleNamespace(run=run))
    return state


def seed_pdf(toy_vault, name="2020toy.....1A"):
    d = toy_vault.PDFS / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.pdf").write_bytes(b"%PDF-fake")
    return toy_vault.FULLTEXT / "test_star" / f"{name}.txt"


def run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["extract_fulltext.py", *argv])
    return ef.main()


# ── main() ───────────────────────────────────────────────────────────────────

def test_capa_de_texto_sana(toy_vault, fake_tools, monkeypatch):
    out = seed_pdf(toy_vault)
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert out.read_text(encoding="utf-8") == GOOD_TEXT


def test_idempotente_no_reextrae(toy_vault, fake_tools, monkeypatch):
    out = seed_pdf(toy_vault)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(GOOD_TEXT, encoding="utf-8")
    run_main(monkeypatch, ["test_star"])
    assert fake_tools.calls == []                    # ni pdftotext se corrió


def test_ilegible_sin_ocr_degrada_limpio(toy_vault, fake_tools, monkeypatch, capsys):
    """Mojibake sin tesseract: el .txt queda como evidencia, avisa, y NO frena (rc 0)."""
    out = seed_pdf(toy_vault)
    fake_tools.pdftotext_out = MOJIBAKE
    assert run_main(monkeypatch, ["test_star"]) == 0
    assert out.read_text(encoding="utf-8") == MOJIBAKE
    assert "ILEGIBLE" in capsys.readouterr().out


def test_pdftotext_falla_sin_ocr(toy_vault, fake_tools, monkeypatch):
    out = seed_pdf(toy_vault)
    fake_tools.pdftotext_rc = 1
    assert run_main(monkeypatch, ["test_star"]) == 1
    assert not out.exists()                          # no queda un .txt a medias


def test_fallback_ocr(toy_vault, fake_tools, monkeypatch, capsys):
    out = seed_pdf(toy_vault)
    fake_tools.pdftotext_out = MOJIBAKE
    fake_tools.ocr = True
    assert run_main(monkeypatch, ["test_star"]) == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith(ef.OCR_MARK)
    assert "source    : ocr" in text
    assert GOOD_OCR in text
    assert "fallback OCR" in capsys.readouterr().out


def test_flag_ocr_fuerza_aunque_capa_sana(toy_vault, fake_tools, monkeypatch):
    out = seed_pdf(toy_vault)
    fake_tools.ocr = True
    assert run_main(monkeypatch, ["test_star", "--ocr"]) == 0
    assert out.read_text(encoding="utf-8").startswith(ef.OCR_MARK)
    assert "pdftotext" not in fake_tools.calls


def test_flag_ocr_sin_tesseract_aborta(toy_vault, fake_tools, monkeypatch):
    seed_pdf(toy_vault)
    with pytest.raises(SystemExit, match="tesseract"):
        run_main(monkeypatch, ["test_star", "--ocr"])


def test_upgrade_automatico_txt_viejo_ilegible(toy_vault, fake_tools, monkeypatch):
    """Aparece tesseract → un .txt viejo mojibake se re-extrae solo por OCR."""
    out = seed_pdf(toy_vault)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(MOJIBAKE, encoding="utf-8")
    fake_tools.pdftotext_out = MOJIBAKE
    fake_tools.ocr = True
    run_main(monkeypatch, ["test_star"])
    assert out.read_text(encoding="utf-8").startswith(ef.OCR_MARK)


def test_ya_ocr_ilegible_no_se_reintenta(toy_vault, fake_tools, monkeypatch):
    out = seed_pdf(toy_vault)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ef.OCR_MARK + "\n" + MOJIBAKE, encoding="utf-8")
    fake_tools.ocr = True
    run_main(monkeypatch, ["test_star"])
    assert fake_tools.calls == []


def test_sin_pdfs(toy_vault, fake_tools, monkeypatch):
    assert run_main(monkeypatch, ["test_star"]) == 1
