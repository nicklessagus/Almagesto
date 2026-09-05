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
