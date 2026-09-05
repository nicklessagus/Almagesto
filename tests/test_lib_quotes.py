"""lib_quotes.py — el cluster de verificación de citas, extraído de `lib_config` (AUD-306).

El grueso de sus tests siguió viviendo en `tests/test_lib_config.py` (llaman por `cfg.*`, que
re-exporta); acá va lo que fija el CONTRATO del módulo nuevo: que sea importable en los dos
órdenes sin ciclo, que re-exporte lo que prometió, y unos casos directos de sus puertas."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lib_quotes as lq  # noqa: E402
import lib_config as cfg  # noqa: E402


def test_los_dos_ordenes_de_import_funcionan_sin_ciclo():
    """`lib_quotes` importa `lib_config` al FINAL y `lib_config` re-exporta al final: cualquiera de
    los dos puede cargarse primero (medido al extraer: el orden inverso rompía con `from … import`).
    En SUBPROCESOS: recargar `lib_config` dentro del proceso de pytest deja a los otros módulos
    con la instancia vieja y rompe cinco tests ajenos (medido)."""
    import subprocess
    scripts = str(Path(__file__).resolve().parents[1] / "scripts")
    for orden in ("import lib_quotes, lib_config", "import lib_config, lib_quotes"):
        r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {scripts!r}); {orden}; "
                            "print(lib_config.quote_verdict is lib_quotes.quote_verdict)"],
                           capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout.strip() == "True", (orden, r.stderr[-300:])


def test_lib_config_reexporta_el_cluster_entero():
    for name in ("quote_verdict", "txt_accuses", "normalize_quote", "quote_fragments", "quotes_in",
                 "extraction_texts", "extraction_identity", "log_quote_exempt", "verificar_pdf_mark",
                 "QUOTE_MIN", "GUTTER", "CANALETA_MIN"):
        assert getattr(cfg, name) is getattr(lq, name), name


def test_las_caches_viven_en_lib_config_y_lib_quotes_las_usa_por_cfg():
    """Estado del proceso que los tests parchean por `cfg.`: si viviera en `lib_quotes`, un
    `monkeypatch.setattr(cfg, "_FULLTEXT_CACHE", {})` no lo vería."""
    for name in ("_FULLTEXT_CACHE", "_EXTRACCION_CACHE", "_EXTRACTION_INDEX"):
        assert hasattr(cfg, name) and not hasattr(lq, name), name


def test_normalize_quote_y_fragments_directos():
    assert lq.normalize_quote("La  señal  *es*  ﬁja") == lq.normalize_quote("la señal es fija")
    a, b = "una primera mitad con largo suficiente", "y una segunda mitad también larga"
    assert lq.quote_fragments(f"{a} […] {b}") == [a, b]        # por debajo de QUOTE_FRAG_MIN se descarta
    assert lq.quote_fragments("corta […] corta") == []


def test_note_own_bibcode_solo_en_papers_y_el_frontmatter_gana(tmp_path, monkeypatch):
    """#394 — el bibcode que una nota de paper ES. Fuera de `papers/` no hay tal cosa: `""`, y con
    eso `with_own_bibcode` no toca los candidatos.

    El frontmatter gana sobre el stem porque `--rename-paper` mueve el archivo y la identidad de una
    extracción es el `bibcode` de adentro (#228/#374); el stem es el fallback de la nota que el
    migrador todavía no tocó — y también el de un frontmatter que no parseó (`None`).

    ⚠ Toma el frontmatter YA PARSEADO: parsearlo acá subía el lint de ~2.0 a >2.3 `yaml.safe_load`
    por nota y lo cazó `tests/poblada/test_escala.py::test_lint_una_pasada_de_yaml` (tier 0 verde)."""
    papers = tmp_path / "papers"
    papers.mkdir()
    monkeypatch.setattr(cfg, "PAPERS", papers)
    fm = {"bibcode": "2020NUEVO..1..1X", "tags": ["paper"]}
    assert lq.note_own_bibcode(papers / "2019VIEJO..1..1X.md", fm) == "2020NUEVO..1..1X"
    assert lq.note_own_bibcode(papers / "2019VIEJO..1..1X.md", {"tags": ["paper"]}) == \
        "2019VIEJO..1..1X"                                    # sin `bibcode:`, el stem
    assert lq.note_own_bibcode(papers / "2019VIEJO..1..1X.md", None) == "2019VIEJO..1..1X"
    assert lq.note_own_bibcode(tmp_path / "stars" / "tau_cet.md", fm) == ""


def test_with_own_bibcode_SUMA_y_nunca_reemplaza_ni_duplica():
    """#373/#394 — la regla es *sumar*. Si reemplazara, la cita legítima del vecino quedaría juzgada
    contra el `.txt` propio y el falso positivo cambiaría de dirección en vez de desaparecer
    (medido: 5 hallazgos, los 5 falsos)."""
    assert lq.with_own_bibcode(["2014Artoni"], "2012embc") == ["2014Artoni", "2012embc"]
    assert lq.with_own_bibcode(["2012embc"], "2012embc") == ["2012embc"]      # no duplica
    assert lq.with_own_bibcode(["2014Artoni"], "") == ["2014Artoni"]          # sin propio, intacto
    original = ["2014Artoni"]
    lq.with_own_bibcode(original, "2012embc")
    assert original == ["2014Artoni"], "no muta la lista del llamador"


def test_log_quote_exempt_deja_UNA_exencion_y_es_estructural():
    """#391 — la marca `⚠ corregido` dejó de eximir. Era una convención en TEXTO LIBRE que decidía
    un chequeo, así que cada consumidor nuevo tenía que aprenderla; y existía porque el `log`
    llevaba una CITA TEXTUAL, que es una afirmación chequeable por máquina en el único lugar de
    `vault/wiki/` que ninguna capa de verificación audita. La salida fue sacarle el motivo, no la
    marca: la cita va a su nota, o al blockquote como mención.

    ⚠ La que queda se reconoce por `Block.kind`, no olfateando un `>`: `split_blocks` **borra** el
    marcador al construir `text`, así que un chequeo a nivel texto no dispararía nunca (#168/#276).
    Y sigue acotada al `log`: en una nota la corrección se hace editando."""
    assert lq.log_quote_exempt("log", "algo ⚠ corregido 2026-09-01 → otra entrada", "") is None
    assert lq.log_quote_exempt("log", "algo", "blockquote")
    assert lq.log_quote_exempt("log", "algo", "parrafo") is None
    assert lq.log_quote_exempt("tau_cet", "algo", "blockquote") is None, "sólo en `log.md`"
