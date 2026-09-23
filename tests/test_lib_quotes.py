"""lib_quotes.py — el cluster de verificación de citas, extraído de `lib_config` (AUD-306).

El grueso de sus tests siguió viviendo en `tests/test_lib_config.py` (llaman por `cfg.*`, que
re-exporta); acá va lo que fija el CONTRATO del módulo nuevo: que sea importable en los dos
órdenes sin ciclo, que re-exporte lo que prometió, y unos casos directos de sus puertas."""
import importlib
import pathlib
import json
import sys
import pytest
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

# Fixtures compartidas con `tests/test_lib_config.py` (DATOS de prueba, no reglas): se importan
# para no duplicar la cadena de la que dependen dos archivos.
from test_lib_config import _ORACION_COL2, _PAGINA_CANALETA_IRREGULAR  # noqa: E402


# ── #439 · lo que sigue vivía en `tests/test_lib_config.py`, donde `mutar --dirigida/--guardas
# scripts/lib_quotes.py` NO mira: 9 guardas de `quote_verdict` salían «vivas» con doce tests. Un test
# vive en el archivo del módulo que prueba, o las redes que miran por módulo no lo ven.

def test_la_cita_con_matematica_en_el_medio_se_busca_de_las_DOS_formas():
    """#287 — `normalize_quote` **borra** el span `$…$` (correcto cuando la nota re-marcó una
    fórmula que el `.txt` no puede tener igual), pero eso convierte «of either $A$ and $S$» en «of
    either and», que no está en ninguna fuente **aunque el paper diga exactamente esa frase** con
    las letras sueltas. Medido al desactivar la exención de #275 sobre una bóveda real."""
    fuente = cfg.normalize_source_text(
        "…without any additional prior knowledge of either A and S. The estimation…")
    assert cfg.quote_found("without any additional prior knowledge of either $A$ and $S$", fuente)


def test_las_dos_lecturas_no_aflojan_el_chequeo():
    """⛔ La dirección peligrosa: las palabras siguen teniendo que estar en la fuente. Lo único que
    cambia es contra cuál de los dos markups de las MISMAS palabras se compara."""
    fuente = cfg.normalize_source_text("el paper habla de otra cosa completamente distinta")
    assert not cfg.quote_found("without any additional prior knowledge of either $A$ and $S$", fuente)
    assert cfg.quote_variants("sin matemática ninguna acá") == ["sin matemática ninguna acá"], \
        "sin `$…$` hay UNA sola lectura: no se duplica trabajo"


def test_quote_found_degraded_clasifica_la_cita_que_el_txt_parte():
    """#288 — números de línea de un preprint a dos columnas metidos EN MEDIO de la frase. La
    fuente dice la cita; el `.txt` la parte. Es otro trabajo y otra severidad: en la nota no hay
    nada que corregir."""
    src = cfg.normalize_source_text(
        "since wpca constructs orthogonal components by 87.0 design, real-world systematics")
    q = "since wPCA constructs orthogonal components by design, real-world systematics"
    assert not cfg.quote_found(q, src), "el chequeo estricto NO se afloja"
    assert cfg.quote_found_degraded(q, src)


def test_quote_found_degraded_no_acepta_una_cita_ajena():
    """⛔ Sólo CLASIFICA un hallazgo que ya falló: sacar números de los dos lados es exactamente lo
    que haría matchear un número equivocado, así que nunca puede aceptar por su cuenta."""
    src = cfg.normalize_source_text("el paper habla de otra cosa completamente distinta")
    assert not cfg.quote_found_degraded("since wPCA constructs orthogonal components", src)


def test_extraction_texts_memoiza_por_boveda(toy_vault, monkeypatch):
    """#320 — misma asimetría que #275 arregló en `_source_readings`: el chequeo corre **por cita**,
    así que sin caché el mismo JSON de ~25 KB se lee, recorre y normaliza decenas de veces.
    ⚠ La clave incluye el directorio: `EXTRACCION` se re-apunta, y una caché por bibcode pelado
    devolvería la extracción de otra bóveda."""
    (cfg.EXTRACCION / "ica").mkdir(parents=True, exist_ok=True)
    f = cfg.EXTRACCION / "ica" / "2013Voss.json"
    f.write_text('{"bibcode": "2013Voss", "ground_truth": [{"valor": "la frase de la fuente"}]}',
                 encoding="utf-8")
    lecturas = []
    real = pathlib.Path.read_text

    def contando(self, *a, **k):
        if self.suffix == ".json":
            lecturas.append(self.name)
        return real(self, *a, **k)
    monkeypatch.setattr(pathlib.Path, "read_text", contando)
    assert "la frase de la fuente" in cfg.extraction_texts("2013Voss")[0]
    cfg.extraction_texts("2013Voss")
    cfg.extraction_texts("2013Voss")
    assert lecturas.count("2013Voss.json") == 1, "el JSON se lee UNA vez por corrida"


def test_una_cita_con_MATEMATICA_se_encuentra_en_un_texto_normalizado_como_FUENTE():
    """#326/#373 — las dos normalizaciones son asimétricas y no había variante que las uniera: la de
    la CITA borra el span `$…$` y la de la FUENTE lo conserva desarmado (`$mathbf{a}^{1}$`). Así que
    una cita cuyo contenido es sobre todo matemática no se encontraba **nunca** en su propia fuente,
    aunque estuviera ahí carácter por carácter.

    Estaba latente: hasta #373 esas citas vivían en las `## Vista`, que ninguna capa miraba. Al
    entrar a la población el defecto salió como **7 hallazgos, los 7 falsos** sobre una bóveda real,
    los 7 «el arranque coincide y la cola diverge» contra su propia extracción — y un falso positivo
    acá **frena operaciones** (#323)."""
    q = r"one has $\mathbf{A}^{-1} = \mathbf{A}^{T}(\mathbf{I}-\Sigma)^{-1}$"
    fuente = cfg.normalize_source_text("Tras esferizar los datos «" + q + "», que en el caso ...")
    assert cfg.quote_found(q, fuente), "la cita está en su fuente, carácter por carácter"


# ── #364/#388 · bajar el RUIDO de la acusación del `.txt` sin bajar su sensibilidad ──

def test_las_comillas_TeX_no_son_una_diferencia_de_PALABRAS():
    """#364/#388 — el PDF compone las comillas dobles con **dos simples** (`\u2018\u2018…\u2019\u2019`, el modo TeX) y
    la extracción escribe `"`. Cero diferencia de palabras, y sin embargo la acusación salía: una
    lectura de PDF por hallazgo, sobre el aviso que existe justamente para cuando el determinista le
    GANA al LLM. Plegar los glifos en los dos lados no puede tapar una alteración de palabras."""
    assert cfg.normalize_quote("dice \u2018\u2018tight\u2019\u2019 cluster") == cfg.normalize_quote('dice "tight" cluster')


def test_las_ligaduras_no_son_una_diferencia_de_PALABRAS():
    """La otra mitad barata: `pdftotext` deja la ligadura tipográfica (`\ufb01`, `\ufb02`) como UN carácter,
    y la extracción escribe las dos letras. Es un carácter, no un borde de palabra, así que la
    guarda de #333 no lo veía."""
    assert cfg.normalize_source_text("the \ufb01nal \ufb02ux") == cfg.normalize_source_text("the final flux")


def test_el_EMPALME_de_columnas_no_es_una_contradiccion():
    """#388 — el caso literal medido: `pdftotext` intercala la columna de referencias renglón por
    renglón, y lo que intercala es texto real que **arranca en un borde de palabra perfecto**. Ahí
    el argumento de #333 se rompe: la guarda existe porque `pdftotext` rompe PALABRAS, y el empalme
    no rompe ninguna.

    El discriminante es que la cita **REANUDA** más adelante en la misma fuente: si el `.txt` trae
    la continuación, no está diciendo otra cosa — está diciendo lo mismo con algo metido en el
    medio. En el caso verdadero de esa misma medición la cola **seguía la misma frase** y no
    reanuda, así que el filtro no lo toca."""
    txt = cfg.normalize_source_text(
        "Speed is, however, a crucial factor because we have to run the ICA "
        "Duann, J.-R., Jung, T.-P., Sejnowski, T., Makeig, S., 2003. What is consistent in ICA "
        "algorithm many times, which is why FastICA is very suitable for this purpose.")
    assert cfg.txt_accuses(
        "Speed is, however, a crucial factor because we have to run the ICA algorithm many times, "
        "which is why FastICA is very suitable for this purpose.", [txt]) is None


def test_una_SONDA_corta_no_alcanza_para_perdonar_el_empalme():
    """El recorte del filtro de arriba: la reanudación se prueba con la COLA de la cita, y una cola
    corta matchea por casualidad —cualquier `.txt` largo contiene «of the data» en algún lado—. Con
    la sonda por debajo de `CITA_COLA_MIN` el filtro no opina y la acusación queda en pie, que es la
    dirección segura: sobre-reportar, nunca perdonar de más."""
    txt = cfg.normalize_source_text(
        "the reproducibility index is computed over the whole set of runs and then a completely "
        "different sentence follows here for a while. data of it appears again later on.")
    a = cfg.txt_accuses(
        "the reproducibility index is computed over the whole set of runs and data of it", [txt])
    assert a is not None, "la cola («data of it», 10 caracteres) no prueba reanudación"


def test_el_borde_de_palabra_sigue_acusando_lo_que_DEBE():
    """⛔ El control que impide aflojar de más: el verdadero positivo medido en `icasso` —la
    extracción escribió «power line interferences» donde el PDF dice «power line artifact», mezclando
    dos frases vecinas de la misma columna— tiene que seguir acusando."""
    txt = cfg.normalize_source_text(
        "the signal clearly corresponds to a 150 Hz harmonics due to the power line artifact. Here "
        "we encounter again the previously discussed problem of the number of components")
    a = cfg.txt_accuses("clearly corresponds to a 150 Hz harmonics due to the power line interferences", [txt])
    assert a is not None and "artifact" in a["cola_txt"]


# ── #324 · la regla compartida: `quote_verdict` y su lector de `.txt` ──────────────────────────────
# Viven acá, y no sólo en los tests de sus dos llamadores, porque la función ES el contrato: hasta
# 1.134.0 la misma regla estaba implementada dos veces (lint y contrast) y ya divergía —13 contra 12
# sobre el mismo corpus el mismo día—, con el número duplicado y un comentario que declaraba que
# tenían que coincidir. Regla de método nº 2.

def _extr_324(bib: str, valor: str, slug: str = "tema"):
    import json
    (cfg.EXTRACCION / slug).mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / slug / f"{bib}.json").write_text(
        json.dumps({"bibcode": bib, "ground_truth": [{"que": "x", "valor": valor}]}), encoding="utf-8")


def _txt_324(bib: str, texto: str, slug: str = "tema"):
    (cfg.FULLTEXT / slug).mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / slug / f"{bib}.txt").write_text(texto, encoding="utf-8")


CITA_324 = "the whitening step is not enough to identify the model"


def test_fulltext_readings_sin_txt_devuelve_vacio_no_una_negacion(toy_vault):
    """Sin `.txt` en disco la respuesta es *no evaluable*, nunca «la cita no está» (D-43)."""
    assert cfg.fulltext_readings("2013SinTxt") == []
    _txt_324("2013Voss", f"prosa. {CITA_324}. más prosa.")
    assert any(CITA_324 in t for t in cfg.fulltext_readings("2013Voss"))


def test_quote_verdict_la_cita_en_SU_txt_no_dice_nada(toy_vault):
    """#324, el paso 1 y el falso positivo medido: la cita está verbatim en el `.txt` del paper que
    la nota cita, su extracción —selectiva (#188)— no la transcribió, y la de otro paper sí. El
    `.txt` es un índice degradado (#205), no un mal testigo: encontrar la cadena ahí prueba que la
    frase es de ESE paper, y no hay nada que reportar."""
    _txt_324("citado", f"prosa. {CITA_324}. más prosa.")
    _extr_324("citado", "otra cosa que este paper aporta")
    _extr_324("ajeno", CITA_324)
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado", "ajeno"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "en_su_txt"


def test_quote_verdict_la_extraccion_la_dice_y_el_txt_no(toy_vault):
    """#315 — la extracción se hizo leyendo el PDF: si la cita está ahí, la nota es fiel y el que
    falló es el índice."""
    _txt_324("citado", "un `.txt` que perdió la frase")
    _extr_324("citado", CITA_324)
    ver, det = cfg.quote_verdict(CITA_324, ["citado"], {"citado"},
                                 {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado" and det["en_extraccion"] == ["citado"]


def test_quote_verdict_atribucion_movida_BLOQUEA(toy_vault):
    """La mitad más frecuente de los verdaderos positivos (6 de 12): la frase está verbatim en la
    extracción de otro bibcode de la misma nota, y en el `.txt` de su fuente no está."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_324("citado", "otra cosa")
    _extr_324("ajeno", CITA_324)
    ver, det = cfg.quote_verdict(CITA_324, ["citado"], {"citado", "ajeno"},
                                 {"citado": cfg.fulltext_readings("citado")})
    assert ver == "alterada" and det["otro_bib"] == ["ajeno"]


def test_quote_verdict_cola_alterada_BLOQUEA(toy_vault):
    """La otra mitad (6 de 12): coincide un prefijo largo y diverge la cola — el patrón de #314."""
    largo = CITA_324 + " under gaussian noise of known covariance"
    _txt_324("citado", "prosa que no dice la cita")
    _extr_324("citado", largo)
    ver, det = cfg.quote_verdict(largo[:len(largo) - 20] + " y una cola inventada",
                                 ["citado"], {"citado"},
                                 {"citado": cfg.fulltext_readings("citado")})
    assert ver == "alterada" and det["prefijo"] and not det["otro_bib"]


def test_quote_verdict_el_SILENCIO_no_bloquea(toy_vault):
    """#321 — la extracción es selectiva y se cita del PDF: su silencio no prueba fabricación."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_324("citado", "otra cosa")
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "no_verbatim"


def test_quote_verdict_sin_txt_es_NO_EVALUABLE(toy_vault):
    """D-43 — sin el `.txt` de su fuente no se puede descartar que la frase esté en ese paper, así
    que ni siquiera la evidencia positiva alcanza: el chequeo no pudo correr."""
    _extr_324("ajeno", CITA_324)
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado", "ajeno"}, {})
    assert ver == "no_evaluable"


def test_quote_verdict_la_cita_AMBIGUA_no_bloquea(toy_vault):
    """#316 — sin `[[bibcode]]` adyacente la cita se probó contra todas las fuentes del bloque: el
    hallazgo es más débil y no puede frenar un cierre."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_324("citado", "otra cosa")
    _extr_324("ajeno", CITA_324)
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado", "ajeno"},
                               {"citado": cfg.fulltext_readings("citado")}, ambiguo=True)
    assert ver == "no_verbatim"


def test_quote_verdict_sin_EXTRACCION_de_la_fuente_no_bloquea(toy_vault):
    """#318 — «no está en la extracción» sólo significa algo si la extracción existe. La fuente
    off-ADS sin extraer, o la bóveda pre-#311 sin migrar, no es una cita alterada: es un chequeo que
    no se pudo correr, aunque la frase aparezca en la extracción de otro paper."""
    _txt_324("citado", "prosa que no dice la cita")          # `.txt` sí, extracción no
    _extr_324("ajeno", CITA_324)
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado", "ajeno"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "no_verbatim"


def test_fulltext_readings_memoiza(toy_vault):
    """#320/#324 — el chequeo corre **por cita**, así que sin caché el mismo `.txt` se lee y
    normaliza decenas de veces en la pasada que `CLAUDE.md` describe como barata."""
    _txt_324("2013Voss", f"prosa. {CITA_324}. más prosa.")
    assert cfg.fulltext_readings("2013Voss") is cfg.fulltext_readings("2013Voss")


def test_quote_verdict_el_txt_que_PARTE_la_cita_no_es_culpa_de_la_nota(toy_vault):
    """#288 — la fuente sí la dice y el `.txt` la parte (números de línea de un preprint a dos
    columnas metidos en medio de la frase). Es otro trabajo y otra severidad: no hay nada que
    corregir en la nota. Medido sobre cinco hallazgos abiertos uno por uno, CUATRO eran esto."""
    partido = CITA_324.replace("enough", "enough 1234")     # el número que inyecta el `.txt`
    _txt_324("citado", f"prosa. {partido}. más prosa.")
    _extr_324("citado", "otra cosa")
    ver, _ = cfg.quote_verdict(CITA_324, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_parte"


def test_la_matematica_PARTE_la_cita_como_la_elipsis(toy_vault):
    """#326 — `$…$` se borraba y las dos mitades se PEGABAN, produciendo una cadena que no existe en
    ningún `.txt`: «Reaching such a high $S/N_{cont}$ is not achievable» quedaba *«reaching such a
    high is not achievable»*, con `s/ncont` en el medio del archivo. Es el mismo argumento que
    `quote_fragments` hace para la elipsis, aplicado al marcador equivocado.

    Pesa porque `CLAUDE.md` **manda** `$...$` en `vault/wiki/`: 412 de 3036 citas de una bóveda real
    lo llevan, y ninguna podía pasar el paso 1 de `quote_verdict` — el detector mandaba a corregir
    algo ya correcto, y no había corrección que lo apagara."""
    cita = ("Reaching such a high $S/N_{cont}$ is not achievable for any star and telescope that "
            "put strong constraints on the observational method")
    txt = cfg.normalize_source_text(
        "bla. reaching such a high s/ncont is not achievable for any star and telescope that put "
        "strong constraints on the observational method. fin")
    assert cfg.quote_found(cita, txt)


def test_la_matematica_partida_NO_acepta_una_cita_que_la_fuente_no_dice(toy_vault):
    """El control: partir en la matemática no afloja el chequeo — las palabras de cada lado tienen
    que seguir estando, y las piezas cortas se descartan igual (`QUOTE_FRAG_MIN`)."""
    cita = ("Reaching such a high $S/N_{cont}$ is not achievable for any star and telescope that "
            "put strong constraints on the observational method")
    txt = cfg.normalize_source_text("reaching such a high s/ncont is not achievable for any star. fin")
    assert not cfg.quote_found(cita, txt)


def test_el_backtick_y_el_wikilink_DESENVUELVEN_no_borran(toy_vault):
    """#326, la ⚠ del issue, medida: sólo `$…$` tenía el trato de «borrar y pegar». El backtick y el
    `[[wikilink]]` pierden sus DELIMITADORES y conservan el texto, así que no fabrican una cadena
    inexistente."""
    txt = cfg.normalize_source_text("el parámetro alpha vale 3 y el resto de la frase sigue acá")
    assert cfg.quote_found("el parámetro `alpha` vale 3 y el resto de la frase sigue acá", txt)


# ── #333 · el `.txt` puede ACUSAR, en un dominio acotado ─────────────────────────────────────────
# El caso real que lo produjo, medido sobre `Almagesto-Tesis` el 2026-08-31 con el cortador de #332
# ya arreglado: `2026A&A...705A.234O` dice «real-world systematics **that are not orthogonal**
# might become entangled» y la extracción transcribió «**do not become orthogonal and** might become
# entangled». La nota copió la extracción, fielmente, y `contrast --validar` daba `0 ✅` porque su
# juez ES la extracción. El `.txt` —`pdftotext`, determinista— lo tenía bien.

CITA_333 = "since wPCA constructs orthogonal components by design, real-world systematics "


def test_txt_accuses_la_cola_divergente_EN_PROSA_es_evidencia(toy_vault):
    """#333, la clase que el issue pide detectar: prefijo largo compartido y cola distinta, en prosa
    y arrancando en un borde de palabra. Gana el lector determinista sobre el LLM."""
    _txt_324("citado", "bla. " + CITA_333 + "that are not orthogonal might become entangled "
                                            "within the same vector. bla")
    _extr_324("citado", CITA_333 + "do not become orthogonal and might become entangled")
    ver, det = cfg.quote_verdict(CITA_333 + "do not become orthogonal and might become entangled",
                                 ["citado"], {"citado"},
                                 {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_acusa" and det["bib"] == "citado"
    assert det["cola_cita"].startswith("do not become orthogonal")
    assert det["cola_txt"].startswith("that are not orthogonal")


def test_txt_accuses_NO_opina_cuando_la_divergencia_toca_la_matematica(toy_vault):
    """#333, paso 2 de la regla: `$…$` es exactamente donde el `.txt` degrada (#205/#326), así que
    ahí no es testigo — la respuesta es el PDF, no una marca. Medido: los 3 casos con matemática de
    esa bóveda habrían acusado sin esta guarda, y los tres tienen la fórmula EN el punto de
    divergencia."""
    cita = CITA_333 + "the inverse covariance $V^{-1}_j$ is just a diagonal matrix"
    _txt_324("citado", "bla. " + CITA_333 + "the inverse covariance v-1 is just a diagonal ma~ "
                                            "col . note that the covariance. bla")
    _extr_324("citado", cita)
    ver, _ = cfg.quote_verdict(cita, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_la_AUSENCIA_LIMPIA_no_acusa(toy_vault):
    """#333, paso 3: el `.txt` simplemente no tiene la cadena → como siempre, `txt_degradado`. Sin
    prefijo compartido no hay evidencia positiva de nada, y ésta es la clase mayoritaria (11 de 25
    en la re-medición)."""
    _txt_324("citado", "un `.txt` que perdió la frase entera y habla de otra cosa completamente")
    _extr_324("citado", CITA_333 + "do not become orthogonal and might become entangled")
    ver, _ = cfg.quote_verdict(CITA_333 + "do not become orthogonal and might become entangled",
                               ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_la_divergencia_A_MEDIA_PALABRA_es_del_ARTEFACTO(toy_vault):
    """#333, el discriminador que compró la re-medición. `pdftotext` rompe PALABRAS —la ligadura
    `ﬁ`, la palabra partida por un espacio pelado (`mix tures`), el empalme— y un LLM que transcribe
    mal cambia PALABRAS. Sobre 7 candidatos de una bóveda real: los **4** que divergen dentro de una
    palabra eran artefactos del `.txt`, los **3** que divergen en un borde eran alteraciones reales.
    Sin esta guarda el detector nacería con 4 falsos positivos de 7."""
    _txt_324("citado", "bla. " + CITA_333 + "do not become orthogonal and might become entangled "
                                            "within the same vec tor of the run. bla")
    largo = CITA_333 + "do not become orthogonal and might become entangled within the same vector"
    _extr_324("citado", largo)
    ver, _ = cfg.quote_verdict(largo, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_el_txt_que_SE_CORTA_no_dice_otra_cosa(toy_vault):
    """#333 — una lectura que se queda sin texto (borde de página o de columna) calla, no
    contradice: sin `CITA_COLA_MIN` caracteres más, no hay divergencia que declarar. La divergencia
    cae en un borde de palabra —o sea que pasa la otra guarda— y aun así el `.txt` no acusa: lo que
    tiene después del corte no alcanza para afirmar que dice otra cosa."""
    _txt_324("citado", "bla. " + CITA_333 + "that")
    largo = CITA_333 + "do not become orthogonal and might become entangled"
    _extr_324("citado", largo)
    ver, _ = cfg.quote_verdict(largo, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_no_opina_si_la_CITA_cruza_un_borde_de_celda(toy_vault):
    """#333, la otra mitad del paso 2. Desde #240 una cita que viaja en una celda lleva su `\\|`
    escapado, y ahí lo que se está comparando ya no es prosa corrida: la respuesta es el PDF."""
    cita = CITA_333 + "do not become orthogonal \\| might become entangled here"
    _txt_324("citado", "bla. " + CITA_333 + "that are not orthogonal might become entangled. bla")
    _extr_324("citado", cita)
    ver, _ = cfg.quote_verdict(cita, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_no_opina_si_el_TXT_cruza_un_borde_de_celda(toy_vault):
    """El otro lado del mismo paso: un `.txt` normalizado colapsa los espacios, así que una tabla
    queda con forma de prosa y su «cola» son celdas vecinas, no una oración que diga otra cosa."""
    cita = CITA_333 + "do not become orthogonal and might become entangled here"
    _txt_324("citado", "bla. " + CITA_333 + "that | are | not | orthogonal | 0.12. bla")
    _extr_324("citado", cita)
    ver, _ = cfg.quote_verdict(cita, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_se_queda_con_la_MEJOR_ocurrencia(toy_vault):
    """#333 — un paper repite su propia frase, y la comparación es contra la ocurrencia que **más**
    comparte: quedarse con la primera haría que un arranque repetido en otro contexto tapara la
    lectura que de verdad contradice a la extracción."""
    corto = CITA_333[:CITA_333.index("systematics")]      # comparte menos que la ocurrencia buena
    _txt_324("citado", "bla. " + corto + "systemic drifts dominate the budget. otra cosa. "
                       + CITA_333 + "that are not orthogonal might become entangled. bla")
    largo = CITA_333 + "do not become orthogonal and might become entangled"
    _extr_324("citado", largo)
    ver, det = cfg.quote_verdict(largo, ["citado"], {"citado"},
                                 {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_acusa" and det["cola_txt"].startswith("that are not orthogonal")


def test_txt_accuses_la_cita_ENTERA_en_el_txt_no_es_divergencia(toy_vault):
    """El contrato de la función, que la misma línea del borde de palabra ya sostiene: si el `.txt`
    la tiene completa no hay cola que comparar, y una «acusación» con la cola vacía sería una marca
    sobre nada. Lo cierra `normalize_quote`, que recorta el espacio final — una coincidencia entera
    termina en una letra, nunca en un borde. (Por el llamador esto no debería llegar: el paso 1 la
    habría absuelto; la función se puede llamar sola.)"""
    lectura = cfg.normalize_source_text("bla. " + CITA_333 + "do not become orthogonal. bla")
    assert cfg.txt_accuses(CITA_333 + "do not become orthogonal", [lectura]) is None


def test_txt_accuses_la_cita_ELIDIDA_no_se_juzga_por_su_cola(toy_vault):
    """#333 — «A … B» no está verbatim en ningún lado por construcción (`quote_fragments`), así que
    su «cola divergente» sería el propio recorte. Se chequea por fragmentos o no se chequea."""
    _txt_324("citado", "bla. " + CITA_333 + "that are not orthogonal might become entangled. bla")
    cita = CITA_333 + "… and might become entangled within the same vector of the run"
    _extr_324("citado", cita)
    ver, _ = cfg.quote_verdict(cita, ["citado"], {"citado"},
                               {"citado": cfg.fulltext_readings("citado")})
    assert ver == "txt_degradado"


def test_txt_accuses_el_txt_de_OTRO_bibcode_no_acusa(toy_vault):
    """#333 — la evidencia es entre los DOS artefactos de una misma fuente. Cruzarla con el `.txt`
    de otro paper fabricaría la atribución que este framework más persigue."""
    _txt_324("ajeno", "bla. " + CITA_333 + "that are not orthogonal might become entangled. bla")
    largo = CITA_333 + "do not become orthogonal and might become entangled"
    _extr_324("citado", largo)
    _txt_324("citado", "un `.txt` que perdió la frase")
    ver, _ = cfg.quote_verdict(largo, ["citado"], {"citado", "ajeno"},
                               {"citado": cfg.fulltext_readings("citado"),
                                "ajeno": cfg.fulltext_readings("ajeno")})
    assert ver == "txt_degradado"


def test_verificar_pdf_mark_lleva_el_MOTIVO_y_la_FECHA():
    """#225/#341 — la marca es `⚠verificar en el PDF (<qué se dudó>, <fecha>)`, y las dos partes son
    del contrato: en seis meses sirve **el motivo**, no una categoría, y la fecha dice desde cuándo
    la deuda está abierta. Una sola definición, porque desde 1.162.0 la emite una herramienta
    (`contrast --validar`) y la busca otra (el detector del lint)."""
    import datetime as _dt
    m = cfg.verificar_pdf_mark("el `.txt` y la extracción difieren en la cola", "2026-08-31")
    assert m == "⚠verificar en el PDF (el `.txt` y la extracción difieren en la cola, 2026-08-31)"
    assert m.startswith(cfg.VERIFICAR_PDF_MARK)
    assert cfg.verificar_pdf_mark("x").endswith(f", {_dt.date.today().isoformat()})")


# ── #437 · la extracción de un PDF REEMPLAZADO no es juez del documento en disco ─────────────────


def _extr_vieja(bib: str, valor: str, slug: str = "tema", marca: str = "_paginacion"):
    """Una extracción que describe un PDF que se REEMPLAZÓ (#436), con la marca de la familia
    `REPLACED_DOC_MARKS` que se pida (#495: la deuda se abre con `_paginacion` y se cierra con
    `_repaginado`, y la transcripción sigue siendo la del documento viejo en los tres casos)."""
    import json
    (cfg.EXTRACCION / slug).mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / slug / f"{bib}.json").write_text(json.dumps(
        {"bibcode": bib, "ground_truth": [{"que": "x", "valor": valor}],
         marca: {"reemplazo": "2026-09-10", "fecha": "2026-09-20", "motivo": "versión del editor"}}),
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


@pytest.mark.parametrize("marca", ["_repaginado", "_repaginado_parcial"])
def test_quote_verdict_495_la_exencion_SOBREVIVE_al_cierre_de_la_deuda(toy_vault, marca):
    """⛔ #495 — repaginar (#494) actualiza los LOCALIZADORES, no la transcripción: la extracción
    sigue describiendo el documento reemplazado, pero la marca que lo decía cambia de nombre. Con
    la puerta mirando sólo `_paginacion`, la exención de #437 se apagaba justo cuando la deuda se
    cerraba BIEN — medido en una bóveda real: 0 → 4 citas alteradas (rc 0 → 1) en tres notas que
    nadie tocó, las cuatro copyedición preprint→publicado, o sea la población exacta que #437
    existe para no acusar. La nota correcta volvía a bloquear."""
    _txt_324("citado", "prosa que no dice la cita")
    _extr_vieja("citado", _PREPRINT_437, marca=marca)
    ver, det = _ver_437()
    assert ver == "extraccion_vieja" and det["bibs"] == ["citado"], (ver, det)
    assert cfg.extraction_depaginated("citado")


@pytest.mark.parametrize("marca", ["_repaginado", "_repaginado_parcial"])
def test_quote_verdict_495_la_nota_CORREGIDA_hacia_la_fuente_tampoco_bloquea(toy_vault, marca):
    """⛔ La segunda dirección, que el validador midió desde el otro lado: **corregir una nota HACIA
    la fuente sumaba un bloqueante**. En `1998Cardoso` la nota transcribía la redacción del preprint
    y la copia del editor dice otra cosa; al corregir los tres bloques, `contrast --validar-todo`
    pasó de 4 a 5 alteradas — la fila **correcta** bloqueaba y la incorrecta pasaba, porque coincide
    con el PDF en disco y diverge de la extracción, que conserva la redacción vieja. Un fix que sólo
    mirara la nota sin corregir dejaba viva justo la que castiga corregir."""
    _txt_324("citado", f"prosa. {_PUBLICADA_437}. más prosa.")
    _extr_vieja("citado", _PREPRINT_437, marca=marca)
    assert _ver_437()[0] == "en_su_txt"


@pytest.mark.parametrize("marca", ["_repaginado", "_repaginado_parcial"])
def test_quote_verdict_495_no_es_un_apagador_el_txt_NUEVO_sigue_bloqueando(toy_vault, marca):
    """El control simétrico: con la marca nueva, el `.txt` del documento EN DISCO trayendo el
    arranque y siguiendo distinto acusa igual (`txt_nuevo`). Lo que sobrevive al repaginado es la
    exención de la extracción, no la de la cita."""
    _txt_324("citado", f"prosa. {CITA_324} under Gaussian noise of unknown covariance. y sigue.")
    _extr_vieja("citado", _PREPRINT_437, marca=marca)
    ver, det = _ver_437()
    assert ver == "alterada" and det.get("txt_nuevo") == "citado", (ver, det)


def test_494_quote_pages_ubica_la_cita_y_declara_por_que_no_pudo(toy_vault):
    """⛔ #494 — UNA implementación de «dónde cae la cita y qué imprime esa página», porque tiene
    dos lectores que no pueden mirar cosas distintas (#324): el veredicto de #492, que juzga el
    localizador contra ella, y el paquete de relectura, que la usa como **GUÍA de dónde abrir el
    PDF**. Si divergieran, la guía mandaría a una página que el chequeo no reconoce.

    Y `motivo` es la otra mitad: *no se pudo ubicar* NO es *el localizador está mal* (D-43) — sin
    `.txt` en disco, o con una cita que el índice degradado no tiene (#205), el silencio no prueba
    nada (#321) y quien llama decide qué hacer con la diferencia."""
    pags = [_pagina(i, f"prosa. {CITA_492}. fin" if i == 2 else "relleno", impresa=100 + i)
            for i in range(1, 5)]
    _txt_paginado("2020Ubica", pags)
    assert cfg.quote_pages(CITA_492, "2020Ubica") == {"paginas": [2], "impresas": ["102"],
                                                      "motivo": None}
    sin_txt = cfg.quote_pages(CITA_492, "2020SinTxt")
    assert sin_txt["paginas"] == [] and "no tiene `.txt` en disco" in sin_txt["motivo"]
    ausente = cfg.quote_pages("una frase que el `.txt` no dice en ninguna página", "2020Ubica")
    assert ausente["paginas"] == [] and "índice degradado" in ausente["motivo"]


@pytest.mark.parametrize("marca,abierta", [("_paginacion", True), ("_repaginado_parcial", True),
                                           ("_repaginado", False)])
def test_494_la_deuda_ABIERTA_es_otra_pregunta_que_la_exencion(toy_vault, marca, abierta):
    """⛔ #494 — una marca, DOS preguntas. `extraction_depaginated` (#437/#495) pregunta si la
    TRANSCRIPCIÓN describe un documento que ya no está, y sobrevive al cierre de la deuda porque
    repaginar actualiza los localizadores y nunca la prosa. `extraction_pagination_open` pregunta si
    los LOCALIZADORES siguen sin releerse, y deja de ser cierta cuando se releen. Leer las dos con
    el mismo campo es lo que hacía que el lint contara deuda con el mismo dato con el que `contrast`
    eximía una cita. La ronda PARCIAL cuenta como abierta: cerró unos ítems y nombró los otros."""
    _extr_vieja("citado", _PREPRINT_437, marca=marca)
    assert cfg.extraction_pagination_open("citado") is abierta
    assert cfg.extraction_depaginated("citado") is True, "la exención mira la familia ENTERA"


def test_496_la_pagina_impresa_de_LETTERS_se_lee_y_se_juzga(toy_vault):
    """⛔ #496 — la página que IMPRIME la hoja no siempre es un entero: A&A Letters pagina `L43`–`L47`,
    ApJL `L24`, MNRAS Letters `L1`. Con la regex pidiendo dígitos pegados al `p.`, el localizador
    correcto de esa fuente no se podía escribir de forma que ninguna capa lo leyera: los 57 de
    `2007A&A...469L..43U` caían FUERA DE ALCANCE —no `mal`: invisibles, y la categoría no los
    contaba en ninguna de sus cinco clases— y `printed_pages` devolvía `[None] * 5`, o sea que
    tampoco se podía juzgar la forma con dígitos. La bóveda elegía entre escribir la verdad y
    perder el chequeo, o escribir un número que el paper no muestra y conservarlo — que pasa en
    verde, y es la peor de las dos.  @inv INV-155"""
    pags = [f"A&A 469, L43 (2007)\n\n" + (f"prosa. {CITA_492}. fin" if i == 3 else "prosa")
            + f"\n\nU. et al.: GJ 674, page L{42 + i} of 5" for i in range(1, 6)]
    # de vuelta: la numeración impresa se deriva CON su prefijo
    assert cfg.printed_pages(pags) == ["L43", "L44", "L45", "L46", "L47"]
    _txt_paginado("2007Udry", pags)
    # de ida: el par llega al veredicto y la página impresa se acepta
    assert cfg.quote_page_verdict(CITA_492, "2007Udry", [("L45", "L45")])[0] == "ok"


def test_496_el_prefijo_NO_se_pliega_ni_afloja_el_veredicto(toy_vault):
    """El control simétrico, que es lo que prueba que el fix no es un apagador: `p. 45` y `p. L45`
    son páginas DISTINTAS del mismo documento —A&A numera el cuerpo y las Letters por separado—,
    así que normalizar `L45 → 45` para poder comparar convertiría el chequeo en un aprobador de la
    convención equivocada. La vecina equivocada sigue saliendo `mal`.  @inv INV-155"""
    pags = [f"A&A 469, L43 (2007)\n\n" + (f"prosa. {CITA_492}. fin" if i == 3 else "prosa")
            + f"\n\nU. et al.: GJ 674, page L{42 + i} of 5" for i in range(1, 6)]
    _txt_paginado("2007Udry", pags)
    assert cfg.quote_page_verdict(CITA_492, "2007Udry", [("L44", "L44")])[0] == "mal"
    assert cfg.quote_page_verdict(CITA_492, "2007Udry", [("45", "45")])[0] != "ok"
    # y el rango tampoco cruza numeraciones: `L43`–`L45` son tres páginas, `12`–`L14` no es rango
    assert cfg.page_span("L43", "L45") == {"L43", "L44", "L45"}
    assert cfg.page_span("12", "L14") == {"12"}
    # lo que no es una etiqueta no nombra ninguna página, y el rango invertido vale por su
    # arranque — la misma semántica que `page_locators` le da a `pp. 14-12`
    assert cfg.page_span("s/n", "5") == set()
    assert cfg.page_span("5", "s/n") == {"5"}
    assert cfg.page_span("14", "12") == {"14"}


def test_496_el_prefijo_es_MAYUSCULA_y_la_numeracion_del_documento_desempata(toy_vault):
    """⛔ Los dos frenos que la medición sobre la bóveda real (255 fuentes) hizo falta agregar, y sin
    los cuales el fix cambiaba un hueco por un dato falso:

    1. el prefijo es **mayúscula** — en minúscula es una variable de la matemática (`= E {s1 s2}` en
       el pie de una fórmula), y leerlo con `re.I` hacía que dos páginas de un libro se leyeran
       `S1`/`S2` y que 34 perdieran su número;
    2. entre dos candidatos consecutivos gana el de la numeración **del documento** (el prefijo del
       offset): el par `J1`/`J2` de una fórmula volvía ambigua la página que la cabecera imprime al
       lado. Sin numeración dominante la ambigüedad NO se adivina (D-43).

    Resultado medido tras los dos frenos: **0 páginas perdidas** y 18 ganadas, las 18 en las dos
    fuentes que de verdad paginan con prefijo (A&A Letters y GEOPHYSICS).  @inv INV-155"""
    # (1) como el libro real: la página par imprime su número, la impar lleva título corrido, y el
    # pie de dos páginas seguidas arrastra `s1` y `s2` de una fórmula. En minúscula NO son páginas
    naik = [(f"{i}   Independent Component Analysis" if i % 2 == 0 else "Introduction: Independent")
            + "\n\nprosa de esta página\n\n"
            + ("= E { s1 s2 } - E { s1 }" if i == 3 else
               "kurt(s1 s2 ) = kurt( s2 )" if i == 4 else "fin")
            for i in range(1, 9)]
    assert cfg.printed_pages(naik)[2:4] == [None, None], "`s1`/`s2` se leyeron como páginas"
    # (2) el desempate: la cabecera imprime 453, 454… el pie arrastra los conjuntos J1/J2 de una
    # fórmula, y el offset global está CONTRADICHO (capítulo nuevo), así que no hay respaldo que
    # tape la ambigüedad — la numeración del documento es la que decide
    libro = [f"{452 + i}   CHAPTER 11\n\nprosa de esta página" +
             (f"\n\npara el conjunto J{i} ." if i in (1, 2) else "") for i in range(1, 6)] \
        + ["999   CHAPTER 12\n\nprosa\n\nfin"]
    assert cfg.printed_pages(libro)[:2] == ["453", "454"]


def test_source_texts_no_parte_una_oracion_continua_entre_dos_lecturas():
    """#332 — la oración vive ENTERA en la columna derecha; el cortador la partía en dos lecturas.

    El paso 1 de `quote_verdict` (`en_su_txt`, #324) es el que evita el falso «mal atribuido», y
    desde #323 ese gate frena operaciones: una cita que SÍ está verbatim en el `.txt` de su fuente
    no puede salir «no está» porque el cortador la repartió."""
    lecturas = cfg.source_texts(_PAGINA_CANALETA_IRREGULAR)
    assert any(cfg.quote_found(_ORACION_COL2, s) for s in lecturas), \
        "la oración de la columna derecha no está entera en ninguna lectura"


def test_source_texts_de_un_txt_en_blanco_no_devuelve_una_lectura_vacia():
    """Una lectura vacía no es una lectura: `fulltext_readings` la pasaría como fuente y
    `quote_verdict` leería «hay `.txt` y la cita no está» donde lo cierto es *no evaluable* (D-43).
    Pasa de verdad: un escaneo cuyo OCR no sacó nada deja un `.txt` de puros espacios."""
    assert cfg.source_texts("   \n  \n") == []


def test_txt_accuses_sin_txt_devuelve_None():
    """D-43 — sin lectura en disco no hay testigo, y eso no es una acusación vacía: es no evaluable."""
    assert cfg.txt_accuses(CITA_333 + "do not become orthogonal", []) is None


def test_quotes_in_devuelve_las_citas_LARGAS_de_un_bloque():
    """La única función de este módulo sin test propio (#439): las «…» de un bloque que llegan a
    `QUOTE_MIN`; una corta («no») no identifica nada y no se chequea."""
    larga = "the whitening step is not enough to identify the model and its noise"
    assert lq.quotes_in(f"Dice «{larga}» y también «no» y « {larga} ».") == [larga, larga]
    assert lq.quotes_in("sin comillas") == []



def test_454_la_cita_que_la_MAQUINA_copio_de_la_extraccion_no_se_juzga_contra_ella(toy_vault):
    """⛔ #454 — `quote_verdict` trata la extracción como TESTIGO («la transcripción hecha leyendo el
    PDF»), y eso es cierto de una cita que el sintetizador RE-TIPEÓ en una ficha, no de una que
    `harvest_views` copió verbatim del JSON: ahí el testigo y el juzgado son el mismo archivo, el
    paso 2 la encuentra siempre y el veredicto sale `txt_degradado` —«la nota tiene razón, el índice
    la perdió»— sobre una cita que nadie verificó nunca.

    Medido en `1999ITNN...10..626H` al cerrar #453: la nota decía «…the convergence is proven
    globally» (1 ocurrencia en el `.txt`) y el JSON «…it converges globally» (0), y pasó con `lint`
    rc 0 y `contrast --validar-todo` rc 0."""
    _txt_324("citado", "un `.txt` que no dice esa frase")
    _extr_324("citado", CITA_324)
    fuentes = {"citado": cfg.fulltext_readings("citado")}
    assert cfg.quote_verdict(CITA_324, ["citado"], {"citado"}, fuentes)[0] == "txt_degradado", \
        "re-tipeada por el sintetizador: la extracción SÍ es testigo (#315)"
    assert cfg.quote_verdict(CITA_324, ["citado"], {"citado"}, fuentes,
                             copiada=True)[0] == "sin_testigo_propio", \
        "copiada por la máquina DE la extracción: no hay testigo independiente"
    # ⚠ y el `.txt` sigue mandando: si la dice, no hay nada que reportar (paso 1, #324)
    _txt_324("condice", f"prosa. {CITA_324}. más prosa.")
    _extr_324("condice", CITA_324)
    assert cfg.quote_verdict(CITA_324, ["condice"], {"condice"},
                             {"condice": cfg.fulltext_readings("condice")},
                             copiada=True)[0] == "en_su_txt"


def test_454_el_predicado_del_bloque_estampado_es_UNO_SOLO():
    """#454/#324 — los dos gates de citas deciden «este bloque lo copió la máquina» con la misma
    función: con código separado ya divergieron una vez (13 contra 12 sobre el mismo corpus)."""
    marca = cfg.SALVEDAD_MARCAS[1]
    assert cfg.quote_from_stamped_block("- «una cita»", intro=marca)
    assert cfg.quote_from_stamped_block(f"{marca}\n\n- «una cita»")
    assert cfg.quote_from_stamped_block("- ⚙ verificada: x", intro=cfg.SALVEDAD_MARCAS[0])
    assert not cfg.quote_from_stamped_block("- «una cita»", intro="**Ejes:**")
    assert not cfg.quote_from_stamped_block("prosa de la ficha con «una cita» [[2020X]]")
    assert not cfg.quote_from_stamped_block("")


# ── #492 · el localizador de PÁGINA contra el `.txt` partido por form feed ────────────────────
CITA_492 = "the taxonomy of stability indices is not settled in the literature"


def _txt_paginado(bib: str, paginas: list, slug: str = "tema"):
    """Un `.txt` con un form feed por página, como el que deja `extract_fulltext` (AUD-165)."""
    _txt_324(bib, "\f".join(paginas), slug)


def _pagina(n: int, cuerpo: str, impresa: int | None = None) -> str:
    """Una página con su número IMPRESO en el pie — la cabecera/pie de la que sale el offset."""
    pie = "" if impresa is None else f"\n\n{impresa}"
    return f"A&A proofs\n\n{cuerpo}{pie}"


def _sin_digitos(i: int) -> str:
    """Cuerpo de página sin enteros: el offset se deriva del pie, no de la prosa."""
    return "prosa de relleno de esta página"


def test_492_el_localizador_adyacente_no_se_roba_el_de_la_cita_siguiente(toy_vault):
    """#492/#325 — la adyacencia es la misma regla que para el bibcode: el número que está después
    de OTRA cita no es el de ésta. Sin el corte en el `«` siguiente, una cita sin localizador se
    quedaba con el de su vecina y salía reportada por una página que nunca declaró."""
    bloque = "dice «una frase larga que alcanza el mínimo de la regla» y después «otra frase larga que también lo alcanza» (p. 9)"
    assert cfg.page_locators_after(bloque, "una frase larga que alcanza el mínimo de la regla") is None
    # …y una cita que NO está en el bloque no hereda ningún localizador: sin el `find` mandando,
    # la ventana arrancaría en un offset arbitrario y devolvería el primer `p. N` que encuentre
    assert cfg.page_locators_after("una prosa cualquiera (p. 9) y más", "ausente") is None
    assert cfg.page_locators_after(bloque, "otra frase larga que también lo alcanza") \
        == [("9", "9")]
    # las tres formas que la bóveda escribe de verdad, incluida la de #488 y la celda de una fila
    for texto, esperado in ((f"«{CITA_492}» (p. 4) [[2020X]]", [("4", "4")]),
                            (f"«{CITA_492}» ([[2020X]], p. 4)", [("4", "4")]),
                            (f"| «{CITA_492}» | p. 4 | x |", [("4", "4")]),
                            (f"«{CITA_492}» (pp. 12-14) [[2020X]]", [("12", "14")]),
                            # ⛔ defecto A del validador: el localizador COMPUESTO trae TODAS sus
                            # páginas (132 + 143 en una bóveda real) — quedarse con la primera
                            # marcaba MAL localizadores correctos
                            (f"«{CITA_492}» (p. 9 y p. 6) [[2020X]]", [("9", "9"), ("6", "6")]),
                            (f"«{CITA_492}» (pp. 179 y 190) [[2020X]]",
                             [("179", "179"), ("190", "190")]),
                            (f"«{CITA_492}» (pp. 3, 7 and 9) [[2020X]]",
                             [("3", "3"), ("7", "7"), ("9", "9")]),
                            # #496 — la página IMPRESA de A&A/ApJ/MNRAS Letters lleva prefijo
                            (f"«{CITA_492}» (pp. L43-L45) [[2020X]]", [("L43", "L45")])):
        assert cfg.page_locators_after(texto, CITA_492) == esperado, texto


def test_492_el_offset_de_la_pagina_impresa_se_deriva_o_no_se_inventa(toy_vault):
    """⛔ El desfasaje índice→impresa sale del entero de cabecera/pie que se repite, y si no se
    repite en `PAGE_OFFSET_MIN` páginas la respuesta es `None` — *no evaluable*, nunca un veredicto
    (D-43). Es la diferencia entre una numeración y dos enteros que coinciden."""
    impresas = [_pagina(i, _sin_digitos(i), impresa=1208 + i) for i in range(1, 5)]
    assert cfg.printed_page_offset(impresas) == ("", 1208)
    assert cfg.printed_page_offset([_pagina(i, _sin_digitos(i)) for i in range(1, 5)]) is None
    # ⛔ y el EMPATE tampoco se desempata: dos numeraciones igual de repetidas no se distinguen
    empatadas = [f"{100 + i}\n\n{_sin_digitos(i)}\n\n{1208 + i}" for i in range(1, 5)]
    assert cfg.printed_page_offset(empatadas) is None
    assert cfg.printed_page_offset([]) is None
    # dos páginas no son una numeración: por debajo de `PAGE_OFFSET_MIN` no se deriva nada
    assert cfg.printed_page_offset(impresas[:2]) is None


def test_492_el_localizador_que_apunta_a_otra_pagina_sale_MAL_con_la_suya(toy_vault):
    """El caso de `Almagesto-Tesis#8`: la cita estaba localizada en «p. 3» y el pasaje arranca en la
    p. 2, con la nota cerrada —`audit-note`, `lint --cierre` 0, 239/239 `soportada`—. El `.txt`
    sabe en qué página está, y el detalle trae la página que hay que escribir.  @inv INV-155"""
    _txt_paginado("2017Kairov", [_pagina(1, "intro", impresa=1),
                                 _pagina(2, f"prosa. {CITA_492}. más prosa.", impresa=2),
                                 _pagina(3, "otra cosa", impresa=3),
                                 _pagina(4, "cierre", impresa=4)])
    assert cfg.quote_page_verdict(CITA_492, "2017Kairov", [(2, 2)])[0] == "ok"
    estado, det = cfg.quote_page_verdict(CITA_492, "2017Kairov", [(3, 3)])
    assert estado == "mal" and det["impresas"] == ["2"] and det["paginas"] == [2]
    # y el rango `pp. 1-3` la cubre: un localizador de rango no es un hallazgo
    assert cfg.quote_page_verdict(CITA_492, "2017Kairov", [(1, 3)])[0] == "ok"


def test_500_el_indice_del_PDF_es_OK_y_el_MAL_sigue_siendo_MAL(toy_vault):
    """⛔ #500 — el localizador existe para que quien CHEQUEA encuentre la afirmación en el PDF de
    disco, no para que un consumidor lo copie a un `\\citep[p.~N]`: ese consumidor no existe en el
    campo de la bóveda. Preguntar CUÁL numeración cobró 518 hallazgos en una bóveda real —438 en
    papers cuyo PDF nunca se reemplazó, 413 cobrados a mano— con valor cero para el lector.
    Hoy la cita que está en la página que el localizador nombra es `ok` por cualquiera de las dos
    numeraciones. ⛔ Lo que NO se afloja: la mitad que sí vale, `mal`, sale idéntica.  @inv INV-155"""
    _txt_paginado("2002Meinecke", [_pagina(1, _sin_digitos(1), impresa=1209),
                                   _pagina(2, f"prosa. {CITA_492}. fin", impresa=1210),
                                   _pagina(3, _sin_digitos(3), impresa=1211),
                                   _pagina(4, _sin_digitos(4), impresa=1212)])
    assert cfg.quote_page_verdict(CITA_492, "2002Meinecke", [(1210, 1210)])[0] == "ok"
    # las 44 de 190 que #492 cobraba: el ÍNDICE del PDF sobre un documento que SÍ imprime número
    assert cfg.quote_page_verdict(CITA_492, "2002Meinecke", [(2, 2)])[0] == "ok"
    assert cfg.quote_page_verdict(CITA_492, "2002Meinecke", [(7, 7)])[0] == "mal"
    # …y el estado `indice` no existe más: ningún veredicto lo devuelve
    assert {cfg.quote_page_verdict(CITA_492, "2002Meinecke", [(n, n)])[0]
            for n in (1210, 2, 7)} == {"ok", "mal"}
    # ⛔ la evidencia de #493 sigue decidiendo el `mal`: «page 22 of 23» no vuelve `ok` a la p. 23
    _txt_paginado("2023Cretignier", [f"A2, page {i} of 23\n\n"
                                     + (f"prosa. {CITA_492}. fin" if i == 22 else "prosa")
                                     for i in range(1, 24)])
    assert cfg.quote_page_verdict(CITA_492, "2023Cretignier", [(22, 22)])[0] == "ok"
    assert cfg.quote_page_verdict(CITA_492, "2023Cretignier", [(23, 23)])[0] == "mal"
    # ⛔ y la etiqueta de #496 tampoco se pliega: `p. L44` sobre la hoja que imprime `L45` es `mal`
    letters = [f"A&A 469, L43 (2007)\n\n" + (f"prosa. {CITA_492}. fin" if i == 3 else "prosa")
               + f"\n\nU. et al.: GJ 674, page L{42 + i} of 5" for i in range(1, 6)]
    _txt_paginado("2007Udry", letters)
    assert cfg.quote_page_verdict(CITA_492, "2007Udry", [("L44", "L44")])[0] == "mal"


def test_492_sin_txt_sin_cita_y_sin_numeracion_impresa_es_NO_EVALUABLE(toy_vault):
    """⛔ Los dos silencios, cada uno con su motivo (D-43/#321): el `.txt` es un índice degradado
    (#205), así que no encontrar la cita NO es «el localizador está mal»; y sin numeración impresa
    derivable, un localizador que tampoco coincide con el índice no tiene contra qué decidirse."""
    estado, det = cfg.quote_page_verdict(CITA_492, "2013SinTxt", [(4, 4)])
    assert estado == "no_evaluable" and "no tiene `.txt` en disco" in det["motivo"], \
        "sin artefacto y sin la cita son dos silencios distintos: el motivo los distingue"
    _txt_paginado("2011Remes", [_pagina(1, "intro"), _pagina(2, f"prosa. {CITA_492}. fin"),
                                _pagina(3, "fin")])
    # ⛔ #500 — coincidir con el índice sobre un `.txt` sin numeración impresa derivable YA NO es
    # «no se puede decidir la convención»: no hay convención que decidir, y la cita está ahí
    assert cfg.quote_page_verdict(CITA_492, "2011Remes", [(2, 2)])[0] == "ok"
    # …y sin numeración impresa, un localizador que NO coincide con el índice tampoco es `mal`:
    # no hay contra qué decidirlo (el `.txt` podría estar numerando de otra manera)
    estado, det = cfg.quote_page_verdict(CITA_492, "2011Remes", [(7, 7)])
    assert estado == "no_evaluable" and "no se puede decidir" in det["motivo"]
    _txt_paginado("2014Du", [_pagina(1, "intro"), _pagina(2, "nada de esto"), _pagina(3, "fin")])
    estado, det = cfg.quote_page_verdict(CITA_492, "2014Du", [(2, 2)])
    assert estado == "no_evaluable" and "índice degradado" in det["motivo"]


def test_492_la_paginacion_del_txt_se_lee_UNA_vez(toy_vault):
    """El chequeo corre POR CITA y normaliza cada página por separado: sin caché, el mismo `.txt`
    se parte y se normaliza decenas de veces en la pasada que `CLAUDE.md` describe como barata
    (misma asimetría que #320 arregló en `extraction_texts`)."""
    _txt_paginado("2020Cache", [_pagina(1, "intro", impresa=1), _pagina(2, "medio", impresa=2),
                                _pagina(3, "fin", impresa=3)])
    primero = cfg.fulltext_pagination("2020Cache")
    assert primero["paginas"] and cfg.fulltext_pagination("2020Cache") is primero


def test_492_la_pagina_se_busca_con_las_COLUMNAS_partidas(toy_vault):
    """La cita que sólo aparece una vez de-interleaveadas las columnas (#275/#332) tiene que
    encontrarse acá también: si no, el chequeo reportaría el LAYOUT como un localizador mal."""
    izq = "ruido de la otra columna que no dice nada de esto en absoluto".split(" ")
    der = CITA_492.split(" ")
    pag = "\n".join(f"{a:<40}{b}" for a, b in zip(izq, der))
    _txt_paginado("2020Columnas", [_pagina(1, _sin_digitos(1), impresa=1),
                                   _pagina(2, pag, impresa=2),
                                   _pagina(3, _sin_digitos(3), impresa=3)])
    assert not any(CITA_492 in lectura for lectura in cfg.source_texts(pag.replace("\n", " "))), \
        "el fixture tiene que exigir el de-interleave: en el texto plano la cita NO está"
    assert cfg.quote_page_verdict(CITA_492, "2020Columnas", [(2, 2)])[0] == "ok"


def test_492_B_la_pagina_impresa_se_lee_DONDE_cae_la_cita_no_de_un_offset_global(toy_vault):
    """⛔ Defecto B del validador: un libro cuya numeración se reinicia por capítulo no tiene UN
    offset. Con el global (+1 en Comon–Jutten) el chequeo marcó **94 MAL, los 94 falsos** — el 14 %
    de la categoría, sobre la fuente más citada del hub. El número se lee del pie de la página donde
    cae la cita, desambiguado por consecutividad con la vecina.  @inv INV-155"""
    # cap. 1 numera 1..3 en las páginas 1..3; cap. 2 REINICIA en 1 en las páginas 4..6
    pags = [_pagina(1, "uno", impresa=1), _pagina(2, "dos", impresa=2), _pagina(3, "tres", impresa=3),
            _pagina(4, "cuatro", impresa=1), _pagina(5, f"prosa. {CITA_492}. fin", impresa=2),
            _pagina(6, "seis", impresa=3)]
    assert cfg.printed_pages(pags) == ["1", "2", "3", "1", "2", "3"]
    _txt_paginado("2010ComonJutten", pags)
    # la cita está en la p. 5 del PDF, impresa «2» del cap. 2: el offset global (0, por el cap. 1)
    # diría «5» y la marcaría MAL
    assert cfg.quote_page_verdict(CITA_492, "2010ComonJutten", [(2, 2)])[0] == "ok"
    assert cfg.quote_page_verdict(CITA_492, "2010ComonJutten", [(5, 5)])[0] == "ok"  # índice (#500)
    assert cfg.quote_page_verdict(CITA_492, "2010ComonJutten", [(7, 7)])[0] == "mal"


def test_492_B_el_offset_global_se_DESCARTA_si_una_pagina_lo_contradice(toy_vault):
    """La página sin número propio no hereda un offset que el documento mismo desmiente: sale
    `None` —no evaluable—, no `índice + offset`. Y sin contradicción, el global sigue siendo el
    respaldo de la página muda (una cabecera que el OCR se comió)."""
    con_muda = [_pagina(1, "uno", impresa=101), _pagina(2, "dos", impresa=102),
                _pagina(3, "muda"), _pagina(4, "cuatro", impresa=104)]
    assert cfg.printed_pages(con_muda) == ["101", "102", "103", "104"]
    # …y la cita que cae en la página MUDA se juzga con ese respaldo: «p. 103» es `impresa` aunque
    # la página no lleve número propio (#493: el respaldo sólo vale con secuencia real)
    con_muda[2] = _pagina(3, f"prosa. {CITA_492}. fin")
    _txt_paginado("2020Muda", con_muda)
    assert cfg.quote_page_verdict(CITA_492, "2020Muda", [(103, 103)])[0] == "ok"
    contradicho = [_pagina(1, "uno", impresa=101), _pagina(2, "dos", impresa=102),
                   _pagina(3, "tres", impresa=103), _pagina(4, "muda"),
                   _pagina(5, "cinco", impresa=7), _pagina(6, "seis", impresa=8)]
    assert cfg.printed_pages(contradicho) == ["101", "102", "103", None, "7", "8"]
    # y la ambigüedad local no se adivina: dos candidatos consecutivos en la misma página → None
    ambigua = [f"10\n\nprosa\n\n{200}", f"11\n\nprosa\n\n{201}", f"12\n\nprosa\n\n{202}"]
    assert cfg.printed_pages(ambigua) == [None, None, None]


def test_493_el_numero_IMPRESO_en_la_pagina_hallada_gana_a_cualquier_offset(toy_vault):
    """#493 — el residuo de #492 en `2012Naik`: la página 8 lleva «10» en la cabecera, sus vecinas
    llevan el título corrido sin número (la consecutividad no confirma), y el offset global era `0`
    por coincidencia de enteros que no son páginas. El número declarado, impreso EN la página donde
    cae la cita, es evidencia más fuerte que todo lo demás.  @inv INV-155"""
    # 22 páginas: enteros de ecuación en los bordes que dan offset 0 tres veces; sólo la p. 8 lleva
    # su número impreso (10); las vecinas, título corrido
    pags = []
    for i in range(1, 23):
        borde = f"({i})" if i in (3, 12, 20) else "Introduction:        Independent"
        cuerpo = f"prosa. {CITA_492}. fin" if i == 8 else "prosa de relleno"
        pie = "\n\n10" if i == 8 else ""
        pags.append(f"{borde}\n\n{cuerpo}{pie}")
    assert cfg.printed_page_offset(pags) is None, \
        "un offset que ningún par de páginas vecinas sostiene no es una paginación"
    _txt_paginado("2012Naik", pags)
    assert cfg.quote_page_verdict(CITA_492, "2012Naik", [(10, 10)])[0] == "ok"
    # …y el offset con secuencia real sigue derivándose
    con_secuencia = [_pagina(i, _sin_digitos(i), impresa=100 + i) for i in range(1, 5)]
    assert cfg.printed_page_offset(con_secuencia) == ("", 100)


def test_493_la_evidencia_de_pagina_NO_es_cualquier_entero_del_borde(toy_vault):
    """Devuelto por el validador: aceptar cualquier entero del borde flipeó 19 hallazgos a
    «impresa», **18 falsos** — el total del artículo en el pie de A&A (`A2, page 22 of 23`: toda
    cita con «p. 23» pasaba), una fecha del pie (Cambiaso 2024), un `4` suelto (Mayor 2009). Sólo
    cuenta la X de «page X of Y» y la línea que es sólo un entero; un año, no.  @inv INV-155"""
    assert cfg.page_number_evidence(["A2, page 22 of 23\n\nprosa\n\nA&A 680, A2 (2023)"]) == [{"22"}]
    assert cfg.page_number_evidence(["10\n\nprosa"]) == [{"10"}]
    assert cfg.page_number_evidence(["Received 10 January 2024\n\nprosa\n\n2024"]) == [set()]
    assert cfg.page_number_evidence(["Fig. 4 shows\n\nprosa"]) == [set()]
    # …y en el veredicto: la cita en la p. 22 de 23 — «p. 22» impresa, «p. 23» MAL, no «impresa»
    pags = [f"A2, page {i} of 23\n\n" + (f"prosa. {CITA_492}. fin" if i == 22 else "prosa")
            for i in range(1, 24)]
    _txt_paginado("2023Cretignier", pags)
    assert cfg.quote_page_verdict(CITA_492, "2023Cretignier", [(22, 22)])[0] == "ok"
    assert cfg.quote_page_verdict(CITA_492, "2023Cretignier", [(23, 23)])[0] == "mal"
    # una fecha en el pie no rescata al localizador del preprint (índice 3, «p. 10» declarado)
    pags = [f"Draft version\n\n" + (f"prosa. {CITA_492}. fin" if i == 3 else "prosa")
            + "\n\nReceived 10 January 2024" for i in range(1, 6)]
    _txt_paginado("2024Cambiaso", pags)
    estado, det = cfg.quote_page_verdict(CITA_492, "2024Cambiaso", [(10, 10)])
    assert estado != "ok", (estado, det)


def test_501_la_ventana_del_localizador_termina_en_borde_de_token(toy_vault):
    """⛔ #501 — la ventana de 80 caracteres acota dónde ARRANCA el localizador, no dónde termina:
    cortada a mitad del número, `p. 2021` se leía `p. 2` (medido: 31 de 13 760 citas de una bóveda
    real, 2 de sus 62 `MAL`)."""
    for pagina in ("13", "2021"):
        for relleno in range(60, 80):
            texto = f"| «{CITA_492}» | " + "x" * relleno + f" | p. {pagina} |"
            loc = cfg.page_locators_after(texto, CITA_492)
            if loc is not None:
                assert loc == [(pagina, pagina)], (relleno, loc)
    # …y lo que ARRANCA fuera de la ventana sigue sin ser adyacente
    lejos = f"«{CITA_492}» " + "x" * 90 + " (p. 4)"
    assert cfg.page_locators_after(lejos, CITA_492) is None


def test_504_el_localizador_es_el_de_AL_LADO_no_el_de_la_afirmacion_vecina(toy_vault):
    """⛔ #504 — un localizador pertenece a la cita que tiene al lado. Mirando sólo los 80
    caracteres POSTERIORES, en prosa se tomaba el `(p. N)` de la afirmación siguiente (53 de 68 MAL
    releídos en una bóveda real) y nunca el que va ANTES («la p. 5 dice «…»»)."""
    c = CITA_492
    casos = (
        # el previo es el de la cita; el de después es de otra afirmación
        (f"el texto de la p. 5 dice que «{c}», pero la Tabla 1 (p. 6) lista otra cosa", [("5", "5")]),
        (f"p. 293 («{c}»), p. 303 («otra frase larga que también alcanza el mínimo»)", [("293", "293")]),
        (f"de pp. 6-7 dice «{c}» (p. 7)", [("7", "7")]),       # los dos adyacentes: manda el de después
        # prosa entre la cita y el número → de otra afirmación → no evaluable (None), nunca MAL
        (f"el abstract dice «{c}», y el cuerpo lo desarrolla (p. 9)", None),
        (f"«{c}», mientras que la Tabla 1 (p. 6) lista otra cosa", None),
        # las formas adyacentes que la bóveda escribe siguen funcionando
        (f"«{c}» (p. 27) [[2023X]]", [("27", "27")]),
        (f"«{c}» [[2023X]] (p. 27)", [("27", "27")]),
        (f"«{c}» ([[2023X]], p. 4)", [("4", "4")]),
        (f"«{c}» (Tabla 5, p. 12)", [("12", "12")]),
        (f"«{c}» (Fig. 3, p. 7)", [("7", "7")]),
        (f"| «{c}» | p. 4 | x |", [("4", "4")]),
        (f"| «{c}» | Tabla 2, p. 4 | x |", [("4", "4")]),
        (f"el cuerpo lo explica en p. 4: «{c}»", [("4", "4")]),
        # ⛔ «(…, p. N), «…»»: el número cierra la afirmación ANTERIOR (la ecuación), no es de ésta
        (f"la CCF (Ec. 14, p. 18), «{c}». Sigue", None),
        # el `(p. 3)` que cierra la afirmación ANTERIOR, separado por punto, no es de ésta
        (f"otra cosa (p. 3). Luego «{c}» sin localizador", None),
    )
    for texto, esperado in casos:
        assert cfg.page_locators_after(texto, c) == esperado, texto


def test_AUD474_el_localizador_que_INTRODUCE_la_cita_siguiente_no_es_de_la_anterior(toy_vault):
    """⛔ AUD-474 (cierre de #504) — el simétrico de #504: el `(p. N)` que va seguido de `):`, `: «`
    o de un verbo que introduce («dice «») es el PREFIJO de la cita siguiente, y adjudicárselo a la
    anterior la acusaba con la página de otra (tres casos medidos en una bóveda real, los tres
    correctos en la nota)."""
    c, otra = CITA_492, "another quotation long enough to be a quote of its own right"
    casos = (
        (f"Abstract: «{c}»; conclusiones (p. 21): «{otra}»", None, [("21", "21")]),
        (f"Conclusions (p. 1) dice que el índice «{c}»; §4.5 (p. 11), sobre el único par, "
         f"dice «{otra}»", None, None),
        (f"p. 4: «{c}»; y en la discusión p. 8: «{otra}»", [("4", "4")], [("8", "8")]),
        # sin `;` ni `):` el número pegado a la cita sigue siendo de ella
        (f"«{c}» (p. 4), y la conclusión dice «{otra}»", [("4", "4")], None),
        # ⛔ medido en la instancia: en una FILA el `:` que presenta la cita siguiente está en OTRA
        # celda, así que no le quita a ésta el localizador de su celda
        (f"| «{c}» | p. 13 (ec. 41); p. 15 (rango) | el paper marca una excepción: «{otra}» (p. 15) |",
         [("13", "13"), ("15", "15")], [("15", "15")]),
    )
    for texto, esperado, esperado_otra in casos:
        assert cfg.page_locators_after(texto, c) == esperado, texto
        assert cfg.page_locators_after(texto, otra) == esperado_otra, texto


def test_AUD402_el_numero_tras_coma_es_pagina_solo_con_BORDE_de_localizador():
    """⛔ AUD-402 — `(p. 7, 3 sigma)` leía las páginas 7 y 3 (un `ok` por coincidencia si la cita
    está en la 3), `(p. 4, 2012)` tomaba el año y `p. 20210` se leía `p. 2021`."""
    assert cfg.page_locators("«x» (p. 7, 3 sigma)") == [("7", "7")]
    assert cfg.page_locators("«x» (p. 4, 2012) [[b]]") == [("4", "4")]
    assert cfg.page_locators("en p. 20210 del catálogo") == []
    # lo que sí es compuesto sigue siéndolo
    assert cfg.page_locators("(p. 9, 6)") == [("9", "9"), ("6", "6")]
    assert cfg.page_locators("(pp. 179, 190 y 191)") == [("179", "179"), ("190", "190"),
                                                           ("191", "191")]
    assert cfg.page_locators("p. 9, p. 6 del PDF") == [("9", "9"), ("6", "6")]
    assert cfg.page_locators("(pp. 12-14 del PDF)") == [("12", "14")]
    # medido sobre la instancia (255 fuentes): lo que el borde NO puede perder…
    assert cfg.page_locators("pp. 2056, 2061") == [("2056", "2056"), ("2061", "2061")]
    assert cfg.page_locators("| p. 139, 144 PDF (tesis p. 115, 119) |")[:2] == [
        ("139", "139"), ("144", "144")]
    assert cfg.page_locators("| p. 16, 18 (Figs. 7 y 9) |") == [("16", "16"), ("18", "18")]
    assert cfg.page_locators("no se leyeron pp. 8-9, 12 ni el apéndice") == [("8", "9"),
                                                                            ("12", "12")]
    # …y lo que sí tiene que soltar: una coma decimal y la figura `5a`
    assert cfg.page_locators("0,36 km/s en p. 9, 0,45 km/s en p. 6") == [("9", "9"), ("6", "6")]
    assert cfg.page_locators("las Figs. 4a p. 7, 5a p. 9") == [("7", "7"), ("9", "9")]


_LARGA_516 = ("which requires the latent signals to be whitened before the model can be identified, "
              "and that condition is not the same as knowing the noise covariance")


def test_516_la_firma_cubre_LA_cita_y_LA_fuente(toy_vault):
    """#516 — la firma es por cita (prefijo normalizado, como la corta el reporte) y por `ref`: otra
    cita u otra fuente no la heredan; sin PDF en disco o con atribución ambigua (#316) no se ofrece
    firma; y la forma dura rechaza el escalar, la lista de strings y la entrada sin `motivo`."""
    pdf = cfg.PDFS / "s" / "2013Voss.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF x")
    sha = lq.quote_pdf_sha("2013Voss")
    firmas = lq.load_reviewed_quotes({"cita_revisada": [
        {"ref": "2013Voss", "cita": _LARGA_516[:60] + "…", "pdf_sha": sha, "pagina": "p. 4",
         "motivo": "verbatim"}]})
    assert lq.reviewed_quote(firmas, ["2013Voss"], _LARGA_516)
    assert not lq.reviewed_quote(firmas, ["2019Otro"], _LARGA_516), "otra fuente no la hereda"
    assert not lq.reviewed_quote(firmas, ["2013Voss"], "otra cita " + _LARGA_516), "otra cita tampoco"
    assert sha in lq.reviewed_quote_entry(["2013Voss"], _LARGA_516), "la entrada lleva el ESTADO"
    assert lq.reviewed_quote_entry(["2019SinPdf"], _LARGA_516) == ""
    assert lq.reviewed_quote_entry(["2013Voss", "2019Otro"], _LARGA_516) == ""
    pdf.write_bytes(b"%PDF y, reemplazado")
    assert not lq.reviewed_quote(firmas, ["2013Voss"], _LARGA_516), "otro PDF: la firma no cubre"
    for mala in ("un motivo suelto", ["una", "lista"],
                 [{"ref": "2013Voss", "cita": _LARGA_516, "pdf_sha": sha, "pagina": "4"}]):
        with pytest.raises(cfg.VistasError):
            lq.load_reviewed_quotes({"cita_revisada": mala})
