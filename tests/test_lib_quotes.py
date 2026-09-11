"""lib_quotes.py — el cluster de verificación de citas, extraído de `lib_config` (AUD-306).

El grueso de sus tests siguió viviendo en `tests/test_lib_config.py` (llaman por `cfg.*`, que
re-exporta); acá va lo que fija el CONTRATO del módulo nuevo: que sea importable en los dos
órdenes sin ciclo, que re-exporte lo que prometió, y unos casos directos de sus puertas."""
import importlib
import pathlib
import json
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

