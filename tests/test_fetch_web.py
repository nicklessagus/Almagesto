"""fetch_web: post-clean determinista, header del snapshot, reuso de fecha, citekeys."""
import io
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
    # @inv INV-30
    out, removed = fw.clean_markdown(MD)
    assert "<video" not in out and "<iframe" not in out and "<source" not in out
    assert "SÍ se conserva" in out                   # figure no se toca
    assert "Prosa citable" in out and "Más prosa." in out
    assert removed == 3                              # video (con su source), iframe, source suelto
    assert "\n\n\n" not in out                       # saltos colapsados
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_clean_es_idempotente():
    """AUD-46: antes era `assert clean(MD) == clean(MD)` — una tautología que se cumple para toda
    implementación determinista (verificado: con el cuerpo reemplazado por `return md, 0` el test
    seguía pasando). La propiedad que SÍ importa y sí puede fallar es la idempotencia: el snapshot
    se re-limpia al re-bajar, así que una segunda pasada no puede seguir cambiando el texto."""
    una, _ = fw.clean_markdown(MD)
    dos, removidos = fw.clean_markdown(una)
    assert dos == una and removidos == 0


# ── snapshot_retrieved (parser en lib_config, #34) / CITEKEY_RE ──────────────

def test_snapshot_retrieved(tmp_path):
    p = tmp_path / "s.txt"
    p.write_text("# header\nsource_url : http://x\nretrieved  : 2026-01-02 (UTC)\n", encoding="utf-8")
    assert fw.cfg.snapshot_retrieved(p) == "2026-01-02"
    p2 = tmp_path / "no.txt"
    p2.write_text("sin fecha", encoding="utf-8")
    assert fw.cfg.snapshot_retrieved(p2) is None
    assert fw.cfg.snapshot_retrieved(tmp_path / "inexistente.txt") is None


@pytest.mark.parametrize("key,ok", [
    ("2006RasmussenWilliams", True),
    ("1999a", True),
    ("RasmussenWilliams2006", False),
    ("20001", False),                # falta la letra tras el año
    ("200Ras", False),
])
def test_citekey_re(key, ok):
    # @inv INV-27
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
    # @inv INV-30
    d = toy_vault.FULLTEXT / "gp"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2006RasmussenWilliams.txt").write_text(
        "# header\nsource_url : https://example.org/gp\nretrieved  : 2020-05-05 (UTC)\n"
        "contenido viejo\n", encoding="utf-8")
    assert run_main(monkeypatch, ARGS) == 0
    assert fake_defuddle.fetched == []               # no re-baja
    fm = read_fm(toy_vault.PAPERS / "2006RasmussenWilliams.md")
    assert fm["accessed"] == "2020-05-05"            # la nota usa la fecha original


def test_main_no_note(toy_vault, fake_defuddle, monkeypatch):
    assert run_main(monkeypatch, [*ARGS, "--no-note"]) == 0
    assert not (toy_vault.PAPERS / "2006RasmussenWilliams.md").exists()


# ── consola no-UTF8: fetch_web muere con UnicodeEncodeError bajo ascii (medido) ──

def test_unicode_no_muere_en_consola_ascii(toy_vault, monkeypatch):
    monkeypatch.setattr(fw, "shutil", SimpleNamespace(which=lambda c: "/usr/bin/npx"))
    monkeypatch.setattr(fw, "fetch", lambda url: "")     # evita invocar defuddle de verdad
    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding="ascii", errors="strict")
    monkeypatch.setattr(sys, "stdout", wrapper)
    monkeypatch.setattr(sys, "argv", ["fetch_web.py", "gp", "2006RasmussenWilliams",
                                      "https://example.org/gp", "--no-note"])
    rc = fw.main()
    wrapper.flush()
    assert rc == 1


def test_force_rebaja_la_fuente_pero_no_pisa_la_extraccion(toy_vault, fake_defuddle, monkeypatch):
    """`--force` re-baja el SNAPSHOT y **no toca la nota de wiki**.  @inv INV-61

    AUD-36: `ingest_theme` documenta que `--force` fuerza sólo la re-bajada de fuentes y que «la
    extracción LLM se protege siempre», pero propagaba el flag hasta `write_web_paper_note`, que
    pisa la nota con un stub. Medido en la auditoría del 2026-08-24 sobre una nota real:
    `methods: [gaussian-process, marginal-likelihood] → []`, `role: [fundacional] → []`, prosa
    perdida. Es el artefacto más caro y menos regenerable de la bóveda, y el docstring es
    justamente lo que hace que alguien corra `--force` con confianza.
    """
    assert run_main(monkeypatch, ARGS) == 0
    note = toy_vault.PAPERS / "2006RasmussenWilliams.md"
    # el agente completa la extracción LLM sobre el stub
    texto = note.read_text(encoding="utf-8")
    texto = texto.replace("methods: []", "methods:\n  - gaussian-process")
    texto = texto.replace("role: []", "role:\n  - fundacional")
    note.write_text(texto + "\n## Extracción\n\nProsa cara escrita por el agente.\n", encoding="utf-8")

    fake_defuddle.md = "# Otra cosa\n\nProsa citable nueva.\n"
    assert run_main(monkeypatch, ARGS + ["--force"]) == 0

    txt = (toy_vault.FULLTEXT / "gp" / "2006RasmussenWilliams.txt").read_text(encoding="utf-8")
    assert "Prosa citable nueva" in txt, "--force SÍ tiene que re-bajar la fuente"
    fm = read_fm(note)
    assert fm["methods"] == ["gaussian-process"], "la extracción LLM no se pisa"
    assert fm["role"] == ["fundacional"]
    assert "Prosa cara escrita por el agente." in note.read_text(encoding="utf-8")


def test_colision_de_citekey_no_mezcla_dos_fuentes(toy_vault, fake_defuddle, monkeypatch):
    """AUD-170 — el `.txt` en disco es el snapshot de OTRA url y la nota se escribía con la
    metadata de la nueva: la cita apunta a una página y el archivo que `verify-citations` lee es
    otro.

    La citekey es sintética (`AAAA+Autor`) y la colisión es normal —dos trabajos del mismo autor y
    año—, así que no es hipotética."""
    d = toy_vault.FULLTEXT / "gp"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2006RasmussenWilliams.txt").write_text(
        "# header\nsource_url : https://otra.org/distinta\nretrieved  : 2020-05-05 (UTC)\ncuerpo\n",
        encoding="utf-8")
    with pytest.raises(SystemExit, match="colisión de citekey"):
        run_main(monkeypatch, ARGS)
    assert not (toy_vault.PAPERS / "2006RasmussenWilliams.md").exists()


def test_force_re_estampa_el_accessed_de_la_nota(toy_vault, fake_defuddle, monkeypatch):
    """AUD-170 — con `--force` el snapshot es nuevo y la nota conservaba el `accessed` viejo (sólo
    se reescribe con `--force-note`): publicaba un "Retrieved <fecha>" que no es el del `.txt` de
    al lado, que es el archivo que `verify-citations` lee."""
    assert run_main(monkeypatch, ARGS) == 0
    nota = toy_vault.PAPERS / "2006RasmussenWilliams.md"
    texto = nota.read_text(encoding="utf-8")
    nota.write_text(texto.replace(f"accessed: {read_fm(nota)['accessed']}", "accessed: 2020-05-05"),
                    encoding="utf-8")
    assert run_main(monkeypatch, [*ARGS, "--force"]) == 0
    fm = read_fm(nota)
    assert fm["accessed"] != "2020-05-05"
    assert str(fm["accessed"]) == fw.cfg.snapshot_retrieved(
        toy_vault.FULLTEXT / "gp" / "2006RasmussenWilliams.txt")
