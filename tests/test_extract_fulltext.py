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


def test_ilegible_marca_de_agua_por_pagina():
    """#50: escaneo sin capa de texto cuyo único texto es la marca de agua de ADS (el bibcode
    repetido por página). Pasa el mínimo GLOBAL de chars pero la densidad por página lo delata
    (caso medido: Baranne+1996, 378 bytes en ~20 páginas)."""
    watermark = "\f".join(["1996A&AS..119..373B"] * 20)
    assert len([c for c in watermark if not c.isspace()]) > ef.LEGIBLE_MIN_CHARS   # el global pasa
    ok, why = ef.is_legible(watermark)
    assert not ok and "por página" in why and "marca de agua" in why


def test_legible_paper_sano_multipagina():
    """Un paper sano de varias páginas no cae en el umbral por página (no hay falso positivo)."""
    ok, why = ef.is_legible("\f".join([GOOD_TEXT] * 12))
    assert ok and why == ""


def test_legible_umbrales_limite():
    # @inv INV-28
    # valores literales a propósito (no ef.LEGIBLE_*): los umbrales son contrato documentado
    # (200 chars / 85% ASCII, compartidos con el lint) — si alguien los cambia, esto debe fallar.
    assert ef.is_legible("a" * 200)[0] is True
    assert ef.is_legible("a" * 199)[0] is False
    assert ef.is_legible("a" * 850 + "ÿ" * 150)[0] is True      # ratio == 0.85 pasa
    assert ef.is_legible("a" * 849 + "ÿ" * 151)[0] is False
    # densidad por página (#50): 200 chars no-espacio por página, y sólo con 2+ páginas.
    # Forma real de pdftotext: un form feed DESPUÉS de cada página (los ff cuentan las páginas).
    assert ef.is_legible("a" * 200 + "\f" + "a" * 200 + "\f")[0] is True
    assert ef.is_legible("a" * 199 + "\f" + "a" * 199 + "\f")[0] is False
    assert ef.is_legible("a" * 400)[0] is True                  # una sola página: no aplica


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


def test_estampa_contrato_en_notas(toy_vault, fake_tools, monkeypatch):
    """Al cerrar, main() estampa fulltext:/fulltext_source: en la nota del paper — en la cadena
    el stub nace ANTES que el .txt; y un re-run idempotente migra notas pre-contrato."""
    seed_pdf(toy_vault)
    note = toy_vault.PAPERS / "2020toy.....1A.md"
    note.write_text("---\npdf: null\ntags:\n- paper\n---\ncuerpo\n", encoding="utf-8")
    assert run_main(monkeypatch, ["test_star"]) == 0
    text = note.read_text(encoding="utf-8")
    assert "fulltext: ../../raw/fulltext/test_star/2020toy.....1A.txt" in text
    assert "fulltext_source: pdftotext" in text
    assert "cuerpo" in text                          # el cuerpo no se toca


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


# ═══════════════════════════════════════════════════════════════════════════
# H-04 · un fallo TOTAL (sin OCR que rescate) queda mudo
# ═══════════════════════════════════════════════════════════════════════════
#
# Decisión: el exit code SIGUE frenando la cadena cuando no hay NINGÚN contenido rescatable (ni
# pdftotext ni OCR) — `test_pdftotext_falla_sin_ocr` de acá arriba fija ese contrato (`rc == 1`)
# y no se toca. Lo que SÍ estaba mal — y es lo que se arregla — es que ese freno era MUDO:
# `out.unlink(missing_ok=True)` + `continue`, sin una sola línea que le diga al operador qué pasó
# ni qué hacer. El "corregí y re-corré" del orquestador (ingest_star.py) es ambiguo sin esa guía:
# un re-run sin cambiar nada repite el mismo fallo para siempre. El fix agrega el aviso; no
# cambia el rc.

def test_fallo_total_sin_ocr_avisa_que_hacer(toy_vault, fake_tools, monkeypatch, capsys):
    """Sin capa de texto y sin tesseract: el .txt se unlinkea y el rc sigue siendo 1 (contrato
    fijado por el test existente), pero AHORA hay una línea explícita que dice por qué y qué
    hacer — antes no había ninguna, sólo el freno silencioso."""
    seed_pdf(toy_vault)
    fake_tools.pdftotext_rc = 1     # pdftotext falla → sin contenido rescatable
    assert run_main(monkeypatch, ["test_star"]) == 1     # contrato preexistente: sigue frenando
    salida = capsys.readouterr().out
    assert "SIN contenido rescatable" in salida
    assert "no arregla esto" in salida
    assert "pending" in salida


def test_promesa_docstring_distingue_fallo_total_de_ilegible():
    """El docstring de `extract_fulltext.py` decía sin condiciones "se AVISA sin frenar la
    cadena" para CUALQUIER fallo de OCR — pero el propio código frena (`return 1 if failed else
    0`) exactamente en el caso de fallo total. La promesa tenía que acotarse al caso
    ilegible-pero-con-contenido (que sí devuelve 0, sin frenar); el caso de CERO contenido
    frena a propósito y ahora el docstring lo dice."""
    doc = Path(ef.__file__).read_text(encoding="utf-8")
    assert "cero contenido rescatable" in doc.lower()


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
    # @inv INV-70
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


def test_txt_bajo_otro_slug_se_reusa(toy_vault, monkeypatch, capsys):
    """D-18: extraer es el paso más caro después de la red. El mismo bibcode bajo otro slug ya
    tiene su `.txt` — es el MISMO texto."""
    (toy_vault.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
    (toy_vault.PDFS / "test_star" / "2020aaa...1..1A.pdf").write_bytes(b"%PDF-1.4")
    (toy_vault.FULLTEXT / "otro").mkdir(parents=True, exist_ok=True)
    (toy_vault.FULLTEXT / "otro" / "2020aaa...1..1A.txt").write_text("prosa legible " * 60,
                                                                    encoding="utf-8")
    def boom(*a, **k):
        raise AssertionError("corrió pdftotext teniendo el .txt bajo otro slug")
    monkeypatch.setattr(ef, "subprocess", SimpleNamespace(run=boom))
    # `shutil.which` mockeado como en el test hermano de más abajo: sin esto el test depende del
    # `pdftotext` REAL de la máquina — pasa donde está instalado y muere en CI, que es exactamente
    # lo que `tests/README.md` promete que la suite no hace ("sin red ni binarios externos").
    monkeypatch.setattr(ef, "shutil", SimpleNamespace(which=lambda x: "/usr/bin/" + x))
    monkeypatch.setattr(sys, "argv", ["extract_fulltext.py", "test_star"])
    assert ef.main() == 0
    assert (toy_vault.FULLTEXT / "test_star" / "2020aaa...1..1A.txt").exists()
    assert "ya extraído bajo" in capsys.readouterr().out


def test_txt_ilegible_bajo_otro_slug_no_se_reusa(toy_vault, monkeypatch):
    """Una copia mojibake no ahorra nada: propaga el problema a otro slug y el lint lo reporta dos
    veces. Se re-extrae."""
    (toy_vault.PDFS / "test_star").mkdir(parents=True, exist_ok=True)
    (toy_vault.PDFS / "test_star" / "2020bbb...1..1B.pdf").write_bytes(b"%PDF-1.4")
    (toy_vault.FULLTEXT / "otro").mkdir(parents=True, exist_ok=True)
    (toy_vault.FULLTEXT / "otro" / "2020bbb...1..1B.txt").write_text("ˆÿþ" * 200, encoding="utf-8")
    llamado = []
    monkeypatch.setattr(ef, "subprocess", SimpleNamespace(
        run=lambda *a, **k: llamado.append(1) or SimpleNamespace(returncode=1, stdout="", stderr="")))
    monkeypatch.setattr(ef, "shutil", SimpleNamespace(which=lambda x: "/usr/bin/" + x))
    monkeypatch.setattr(sys, "argv", ["extract_fulltext.py", "test_star"])
    ef.main()
    assert llamado, "reusó una copia ilegible en vez de re-extraer"


# ── garble: la capa de texto existe pero es OCR del editor (#104) ────────────
# `is_legible` mide *extraíble*; esto mide *correcto*. Calibrado sobre 787 .txt de dos bóvedas
# reales: 749 dan exactamente 0, p99 = 0.19, y los dos únicos escaneos conocidos dan 5.55
# (Bell&Sejnowski 1995) y 2.13 (Comon 1994); el no-escaneo más alto da 0.61.
LIMPIO = ("El metodo estima las componentes independientes maximizando la no-gaussianidad "
          "de las proyecciones. " * 40)


def test_texto_limpio_no_es_garble():
    assert ef.is_garbled(LIMPIO)[0] is False
    assert ef.garble_score(LIMPIO)[0] == 0


def test_ocr_del_editor_se_detecta():
    dano = LIMPIO + " Coni~nunicatedby Ul~rz~ersity Corllp~rtafiorl wr~ttenas Ho~unrdHqhes " * 6
    garbled, why = ef.is_garbled(dano)
    assert garbled is True
    assert "OCR del editor" in why


def test_matematica_mal_extraida_no_es_garble():
    """Falso positivo real medido en 1999ApJ...510..986K: `e~ql`, `e~a2(t~t0)` son exponentes,
    no daño. Por eso el token tiene que ser largo y sin dígitos."""
    mate = LIMPIO + " e~ql e~a2(t~t0) )A(l)e~ql )e~ql/4nd2 " * 20
    assert ef.is_garbled(mate)[0] is False


def test_titulo_con_tracking_tipografico_no_es_garble():
    """`D U C T I O N`, `S O L A R` son títulos espaciados (estilo MNRAS), no OCR roto."""
    titulos = LIMPIO + " I N T R O D U C T I O N S O L A R T W I N S A M P L E " * 20
    assert ef.is_garbled(titulos)[0] is False


def test_relleno_de_tabla_no_es_garble():
    """`o o o o o` / `T T T T T` son relleno: una sola letra repetida, no palabras partidas."""
    relleno = LIMPIO + " o o o o o o o o T T T T T T " * 20
    assert ef.is_garbled(relleno)[0] is False


def test_runs_en_minuscula_con_letras_distintas_si_son_garble():
    roto = LIMPIO + " m a x i m u m n p u t q h e s " * 12
    assert ef.is_garbled(roto)[0] is True


def test_garble_es_una_densidad_no_un_conteo():
    """Un documento largo con unas pocas marcas no es un escaneo; el mismo número en uno corto sí."""
    pocas = " Coni~nunicatedby Ul~rz~ersity "
    assert ef.is_garbled(LIMPIO * 30 + pocas)[0] is False
    assert ef.is_garbled("palabra " * 20 + pocas * 6)[0] is True


def test_scanned_header_arranca_con_la_marca_que_lee_make_notes():
    """El header tiene que disparar `fulltext_source: ocr` río abajo: es lo que hace viajar la
    salvedad. Si la marca cambia, la salvedad se pierde en silencio."""
    h = ef.scanned_header("motivo de prueba")
    assert h.startswith(ef.OCR_MARK)
    assert "motivo de prueba" in h
    assert "SALVEDAD" in h.upper()


def test_scanned_header_dice_que_el_ocr_no_es_de_tesseract():
    assert "editor" in ef.scanned_header("x")


# ── backfill: el .txt YA EXTRAÍDO cuya capa de texto era OCR del editor ───────
# `is_garbled` sólo corría sobre texto recién extraído, así que un .txt escrito antes de que
# ese chequeo existiera se queda con `fulltext_source: pdftotext` para siempre: el camino de
# skip lo re-lee sólo para preguntarle si es ILEGIBLE, y un escaneo del editor es perfectamente
# legible. Medido sobre una bóveda real: 3 de los 42 .txt de un tema.
DANIO = " Coni~nunicatedby Ul~rz~ersity Corllp~rtafiorl wr~ttenas Ho~unrdHqhes " * 6


def test_backfill_no_toca_un_txt_limpio():
    assert ef.backfill_scanned_mark(LIMPIO) is None


def test_backfill_marca_el_txt_garbleado_ya_extraido():
    why = ef.backfill_scanned_mark(LIMPIO + DANIO)
    assert why is not None
    assert "OCR del editor" in why


def test_backfill_es_idempotente_sobre_un_txt_ya_marcado():
    """La segunda corrida no puede volver a estampar: el .txt ya arranca con la marca, y
    apilar headers rompería la idempotencia que el framework declara como invariante."""
    ya = ef.scanned_header("motivo previo") + LIMPIO + DANIO
    assert ef.backfill_scanned_mark(ya) is None


def test_backfill_no_pisa_el_carril_del_ILEGIBLE():
    """Un .txt ilegible es del otro camino (reintento por OCR con tesseract): si el backfill lo
    marcara `source: ocr` sin re-extraerlo, congelaría un mojibake como si fuera citable."""
    assert ef.backfill_scanned_mark("\x0c \x0c " * 50) is None


def test_backfill_estampa_el_header_que_make_notes_lee():
    why = ef.backfill_scanned_mark(LIMPIO + DANIO)
    assert ef.scanned_header(why).startswith(ef.OCR_MARK)


# ── símbolos perdidos: el .txt es ASCII limpio pero las ECUACIONES se vaciaron (#113) ──
# `is_legible` mide *extraíble* y `is_garbled` mide *correcto*; esto mide *completo*. Calibrado
# sobre 813 .txt de dos bóvedas: de los 343 con ≥4 marcadores, p95=0.33 y después un salto al
# grupo de rotos (0.98-1.00). Los dos casos conocidos (1999Hyvarinen, 1999HyvarinenNoisy) dan 100%
# y NO tienen garble: por eso hace falta este eje además del otro.
VACIAS = "\n".join(" " * 40 + f"({i})" for i in range(1, 6))
VIVAS = "\n".join(f"J(w) = E[(w^T x)^{i}] - 3       ({i}.1)" for i in range(1, 6))


