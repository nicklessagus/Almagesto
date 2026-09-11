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

# ── #437 · la extracción de un PDF REEMPLAZADO no es juez del documento en disco ─────────────────
# Los helpers `_extr_324`/`_txt_324`/`CITA_324` son los de `tests/test_lib_config.py` (donde viven los
# tests de #324); acá se importan para que estos cinco vivan en el archivo del módulo que prueban —
# es lo que `mutar --dirigida scripts/lib_quotes.py` mira.
from test_lib_config import _extr_324, _txt_324, CITA_324  # noqa: E402


def _extr_vieja(bib: str, valor: str, slug: str = "tema"):
    """Una extracción marcada `_paginacion`: describe un PDF que se REEMPLAZÓ (#436)."""
    import json
    (cfg.EXTRACCION / slug).mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / slug / f"{bib}.json").write_text(json.dumps(
        {"bibcode": bib, "ground_truth": [{"que": "x", "valor": valor}],
         "_paginacion": {"reemplazo": "2026-09-10", "motivo": "versión del editor"}}),
        encoding="utf-8")


#: #437 — la cita como la escribió el preprint y como la corrigió el editor (copyedición)
_PREPRINT_437 = CITA_324 + " under gaussian noise of known covariance"
_PUBLICADA_437 = CITA_324 + " under Gaussian noise whose covariance is known"


def _ver_437(bibs: tuple = ("citado",)) -> tuple:
    return cfg.quote_verdict(_PUBLICADA_437, ["citado"], set(bibs),
                             {b: cfg.fulltext_readings(b) for b in bibs})


# ⚠ Cuatro tests y no uno: `fulltext_readings` y el índice de extracciones se memoizan por ruta,
# así que reescribir el `.txt` o el JSON dentro del mismo test lee la versión vieja. Cada test
# arranca con un `toy_vault` nuevo, o sea caché nueva.

def test_quote_verdict_437_la_cita_corregida_verbatim_en_el_txt_NUEVO_pasa(toy_vault):
    """⛔ #437 — después de reemplazar el preprint por el publicado, corregir la cita a la redacción
    publicada la hacía «alterada»: el gate comparaba contra la extracción, que es la lectura del
    PREPRINT, así que la nota correcta bloqueaba y la incorrecta pasaba (medido: 23 pares de
    copyedición). La regla: «cambiada» se mide contra el PDF que está en disco, no contra la
    lectura vieja. Primera salida: la cita está verbatim en el `.txt` re-extraído → pasa (paso 1,
    que ya existía y que el reemplazo acotado de #436 hace posible)."""
    _txt_324("citado", f"prosa. {_PUBLICADA_437}. más prosa.")
    _extr_vieja("citado", _PREPRINT_437)
    assert _ver_437()[0] == "en_su_txt"


def test_quote_verdict_437_el_txt_nuevo_CALLA_y_la_extraccion_vieja_no_acusa_sola(toy_vault):
    """Segunda salida: el `.txt` nuevo no la encuentra y la extracción VIEJA trae el prefijo con
    otra cola. Esa cola es la redacción del preprint, no evidencia contra el documento en disco:
    no bloquea, sale con la marca `⚠verificar en el PDF` — y nunca «pasa»."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_vieja("citado", _PREPRINT_437)
    ver, det = _ver_437()
    assert ver == "extraccion_vieja" and det["bibs"] == ["citado"], (ver, det)
    assert cfg.extraction_depaginated("citado")


def test_quote_verdict_437_sin_la_marca_la_regla_de_321_sigue_INTACTA(toy_vault):
    """El control: la misma extracción SIN `_paginacion` sigue siendo el juez y bloquea (#321). La
    regla nueva está acotada a la población marcada, que es la única donde la extracción describe
    un documento que ya no está."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_324("citado", _PREPRINT_437)
    ver, det = _ver_437()
    assert ver == "alterada" and det["prefijo"] and not det.get("txt_nuevo"), (ver, det)
    assert not cfg.extraction_depaginated("citado")


def test_quote_verdict_437_el_txt_NUEVO_que_sigue_distinto_BLOQUEA(toy_vault):
    """Tercera salida: el `.txt` del PDF nuevo trae el arranque y sigue distinto → contra el
    documento en disco la cita SÍ está alterada, y bloquea. El testigo es el `.txt` nuevo
    (`txt_nuevo`), no la extracción — que sólo puede hablar del documento viejo."""
    _txt_324("citado", f"prosa. {CITA_324} under Gaussian noise of unknown covariance. y sigue.")
    _extr_vieja("citado", _PREPRINT_437)
    ver, det = _ver_437()
    assert ver == "alterada" and det.get("txt_nuevo") == "citado" and "cola_txt" in det, (ver, det)


def test_quote_verdict_437_la_atribucion_movida_bloquea_AUNQUE_el_pdf_se_haya_reemplazado(toy_vault):
    """La frase verbatim en la extracción de OTRA fuente no depende de qué documento describa la
    de la fuente citada: es atribución equivocada y bloquea igual (#318), con o sin marca."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_vieja("citado", _PREPRINT_437)
    _txt_324("ajeno", "otra prosa")
    _extr_324("ajeno", _PUBLICADA_437)
    ver, det = _ver_437(("citado", "ajeno"))
    assert ver == "alterada" and det["otro_bib"] == ["ajeno"], (ver, det)


def test_quote_verdict_437_una_extraccion_VIGENTE_con_el_prefijo_sigue_siendo_juez(toy_vault):
    """La regla está acotada a «el prefijo viene SÓLO de extracciones marcadas»: si un bloque cita dos
    fuentes y la NO marcada también trae el arranque con otra cola, ésa describe un documento que
    sí está en disco y su acusación vale (#321): bloquea."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_vieja("citado", _PREPRINT_437)
    _txt_324("vigente", "otra prosa")
    _extr_324("vigente", _PREPRINT_437)
    ver, det = cfg.quote_verdict(_PUBLICADA_437, ["citado", "vigente"], {"citado", "vigente"},
                                 {"citado": cfg.fulltext_readings("citado"),
                                  "vigente": cfg.fulltext_readings("vigente")})
    assert ver == "alterada" and det["prefijo"] and not det.get("txt_nuevo"), (ver, det)

