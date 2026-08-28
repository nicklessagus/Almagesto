"""INV-100 — el prompt del fan-out de extracción se GENERA, no se escribe a mano.

Motivo (medido el 2026-08-25, ingest de tau Ceti): las reglas de la extracción viven en
`ingest-star`/`CLAUDE.md`, pero el prompt de cada subagente se escribía freehand por operación.
Toda regla que no entra al prompt se cae en silencio en esa frontera: sobre 79 extracciones,
**54 redescubrieron por su cuenta** el entrelazado de columnas (#44) y **23** el problema de
grafía del sujeto, y tres subagentes se pisaron el archivo de salida entre sí.
"""
from __future__ import annotations

import re
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extraction_prompt as ep
import lib_config as cfg

ALIASES = ["HD 10700", "GJ 71", "HIP 8102"]
DOS_COLUMNAS = "\n".join(
    "El objeto muestra una dispersion de 1.2 m/s en la serie" + " " * 12 +
    "y por otro lado la muestra completa da un resultado distinto"
    for _ in range(30)
)
UNA_COLUMNA = "\n".join(
    "El objeto muestra una dispersion de 1.2 m/s en la serie temporal completa del instrumento."
    for _ in range(30)
)


def test_patrones_incluyen_la_grafia_abreviada():
    """#44: los papers escriben «tau Cet», no «tau Ceti». Un patrón sólo con la forma larga
    da falso negativo, y acá el falso negativo se lee como «el paper no reporta el parámetro»."""
    # @inv INV-100
    pats = ep.subject_patterns("tau Ceti", ALIASES)
    assert "Ceti" in pats
    assert "Cet" in pats, "falta el prefijo de 3 letras: es como aparece en la mayoría de los papers"


def test_patrones_incluyen_el_numero_de_catalogo_suelto():
    """Muchos papers nombran al sujeto sólo por «HD 10700», y algunos sin el espacio."""
    pats = ep.subject_patterns("tau Ceti", ALIASES)
    assert "10700" in pats
    assert any(p.startswith("HD ?") for p in pats), "falta el patrón con espacio opcional"


def test_no_emite_numeros_cortos_sueltos():
    """«71» suelto matchearía cualquier cosa; sólo vale acompañado de su prefijo."""
    pats = ep.subject_patterns("tau Ceti", ALIASES)
    assert "71" not in pats
    assert any(p.startswith("GJ ?") for p in pats)


def test_patrones_son_cortos():
    """#44: un patrón largo cruza la canaleta entre columnas y no matchea nunca."""
    for p in ep.subject_patterns("epsilon Eridani", ["HD 22049", "GJ 144"]):
        assert len(p) <= 12, f"patrón demasiado largo para un .txt entrelazado: {p!r}"


def test_patrones_deterministas():
    a = ep.subject_patterns("tau Ceti", ALIASES)
    b = ep.subject_patterns("tau Ceti", list(reversed(ALIASES)))
    assert a == b == sorted(set(a))


def test_prompt_declara_ruta_de_salida_por_bibcode():
    """Tres subagentes se pisaron un `out.json` compartido: el fallo es silencioso y devuelve
    JSON válido del paper equivocado."""
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA)
    assert "2017AJ....154..135F.json" in p


def test_prompt_ata_el_numero_de_linea_al_entrelazado():
    """La regla #103 pide el nº de línea; #44 dice que en un .txt entrelazado ese número NO es
    un localizador único. Las dos reglas se escribieron por separado y nadie las cruzó."""
    # @inv INV-100
    dos = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, DOS_COLUMNAS)
    una = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA)
    assert "DOS COLUMNAS entrelazadas" in dos
    # #193 cambió el contrato de la rama de una columna: antes callaba, ahora DECLARA la medición
    # (una clasificación equivocada era indistinguible de una correcta). Lo que sigue sin poder
    # aparecer es el CAVEAT: declarar la medida no es inventar el entrelazado.
    assert "DOS COLUMNAS entrelazadas" not in una
    assert "no es un localizador único" not in una
    assert "UNA columna" in una and "fracción medida" in una


def test_prompt_declara_la_salvedad_ocr_solo_si_corresponde():
    """El prompt base ya nombra al OCR por otro motivo (el escaneo de ADS pierde filas de tabla),
    así que el chequeo mira la salvedad de citabilidad, no la palabra suelta."""
    MARCA = "citable **con salvedad**"
    ocr = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES,
                          ep.cfg.FULLTEXT_OCR_MARK + ": citable CON SALVEDAD\n" + UNA_COLUMNA)
    assert MARCA in ocr
    assert MARCA not in ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti",
                                        ALIASES, UNA_COLUMNA)


def test_prompt_lleva_los_patrones_generados():
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA)
    for pat in ("Cet", "10700"):
        assert pat in p


SUPLICAS = [r"s[eé] preciso", r"no inventes", r"ten[eé] cuidado", r"con mucho cuidado",
            r"be (precise|accurate|careful)", r"do not (make up|hallucinate)"]


def test_el_prompt_no_suplica_exactitud():
    """RSOS 2025 (4900 resúmenes / 10 modelos): pedir exactitud DUPLICA la sobre-generalización
    («algorithmic ironic rebound»). El skill ya lo declara; acá queda ejecutable."""
    # @inv INV-100
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, DOS_COLUMNAS).lower()
    for s in SUPLICAS:
        assert not re.search(s, p), f"el prompt suplica exactitud: {s!r}"


def test_prompt_pide_lo_verificable_de_103():
    """Lo que sí funciona es lo chequeable: nº de línea, régimen, segunda mano, tiempo verbal."""
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA).lower()
    for exigido in ("línea", "régimen", "segunda mano", "tiempo verbal", "cuantificador"):
        assert exigido in p, f"el prompt no exige {exigido!r}"


def test_prompt_declara_que_un_grep_vacio_no_prueba_ausencia():
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA).lower()
    assert "ausencia" in p


def test_un_tema_no_trunca_a_tres_letras_pero_si_conserva_la_sigla():
    """La truncación a tres letras recupera la grafía abreviada de los nombres astronómicos
    (`Ceti` → `Cet`); sobre las palabras comunes de un tema sólo produce ruido (`procesos` → `pro`).
    Lo que sirve ahí es la sigla, que la regla de ≥4 letras dejaba afuera justo cuando es el alias
    más usado."""
    # @inv INV-100
    pats = ep.subject_patterns("independent component analysis", ["ICA"], kind="theme")
    assert "ICA" in pats, "la sigla es el alias que más aparece en el texto"
    assert "ana" not in pats and "com" not in pats, "no truncar palabras comunes"
    assert "analysis" in pats
    #  la truncación sigue viva para estrellas, que es donde significa algo
    assert "Cet" in ep.subject_patterns("tau Ceti", [], kind="star")


def test_el_prompt_nombra_la_ruta_real_del_fulltext():
    """Si la ruta sale mal el subagente no lee nada, y el resultado —«la fuente no dice nada del
    sujeto»— es indistinguible de una extracción legítima que no encontró al sujeto."""
    # @inv INV-100
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA)
    esperado = "vault/raw/fulltext/tau_ceti/2017AJ....154..135F.txt"
    assert esperado in p
    assert p.count(esperado) >= 1 + len(ep.subject_patterns("tau Ceti", ALIASES)), \
        "cada patrón de grep tiene que apuntar al mismo .txt que se manda a leer"


def test_los_patrones_alfabeticos_van_anclados_a_frontera_de_palabra():
    """Medido en una corrida real: `Cet` enganchaba dentro de «Princeton» en las afiliaciones y el
    extractor tuvo que descartar el hit a mano. La frontera va sólo a la izquierda, porque `Cet`
    tiene que seguir matcheando `Ceti`."""
    # @inv INV-100
    import re
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA)
    assert r"'\bCet'" in p
    assert r"'\b10700'" not in p, "un número no necesita la frontera y ensucia el patrón"
    rx = re.compile(r"\bCet", re.I)
    assert not rx.search("Princeton University")
    assert rx.search("tau Cet") and rx.search("tau Ceti")


def test_is_extraction_distingue_la_extraccion_de_otras_salidas_con_bibcode():
    """INV-103: identificar por `bibcode` es lo que pisó 13 notas terminadas — la salida de
    `verify-citations` también lo trae, y el JSON era válido, así que nada avisó."""
    # @inv INV-103
    extr = {"bibcode": "2017AJ....154..135F", "ejes": {"rv": "x"}, "ground_truth": []}
    verif = {"bibcode": "2017AJ....154..135F", "resultados": [{"veredicto": "soportada"}]}
    assert ep.is_extraction(extr) is True
    assert ep.is_extraction(verif) is False
    assert ep.is_extraction({"ejes": {}, "ground_truth": []}) is False, "sin bibcode no se puede archivar"
    assert ep.is_extraction({"bibcode": "x", "ejes": [], "ground_truth": []}) is False
    assert ep.is_extraction({"bibcode": "x", "ejes": {}, "ground_truth": {}}) is False
    assert ep.is_extraction(None) is False and ep.is_extraction([]) is False


def test_el_prompt_manda_al_PDF_cuando_las_ECUACIONES_no_estan_en_el_txt():
    """Issue #153 — `CLAUDE.md` (#113) dice que con `symbols_lost: true` la extracción se hace **del
    PDF** y las citas de fórmulas van **por página**, no por línea del `.txt`. El generador del
    prompt no tenía ninguna rama para esa marca: la regla vivía en la doc y no llegaba al subagente,
    que es exactamente el modo de falla que INV-100 cerró para las demás.

    El modo de falla es silencioso en el peor lugar: `pdftotext` deja el marcador `(3)` y vacía su
    cuerpo, así que el `.txt` **parece** tener la fórmula. Un extractor que no sabe esto cita una
    línea que no contiene la ecuación.  @inv INV-100"""
    texto = f"{cfg.FULLTEXT_SYMBOLS_MARK} simbolos NO extraidos\nLa ecuacion (3) define el kernel.\n"
    p = ep.build_prompt("gp", "2006Rasmussen", "GP", [], texto, kind="theme")
    assert "página del PDF" in p, "la cita de fórmulas va por página del PDF"
    # ⚠ La RUTA del PDF, no sólo la palabra. El gate de mutación cazó que `_pdf_rel` sobrevivía:
    # los asserts miraban `"PDF" in p` y `"página" in p`, que un `return None` satisface igual
    # porque esas palabras están en la prosa fija del aviso. Un extractor que recibe el aviso sin
    # la ruta no sabe QUÉ archivo abrir — que es todo lo que el aviso tiene que darle.
    assert "vault/raw/pdfs/gp/2006Rasmussen.pdf" in p, \
        "el aviso tiene que decir QUÉ PDF abrir, no sólo que lo abra"


def test_sin_la_marca_el_prompt_no_habla_de_paginas():
    """La otra mitad de #153: la rama es condicional. Un aviso fijo sobre páginas en todo prompt
    contradiría la regla por defecto —citar **línea** del `.txt`— y sería ruido en el 96 % de los
    casos (medido: 13 de 343 `.txt` evaluables llevan la marca)."""
    p = ep.build_prompt("gp", "2006Rasmussen", "GP", [], "Texto limpio, sin marca.\n", kind="theme")
    assert "por página del PDF" not in p


# ── #188 paso 4 · el prompt pide LA VISTA de un sujeto, y el JSON la trae ───────────────────────

def test_el_prompt_pide_la_vista_del_sujeto():
    """La extracción SIEMPRE fue una lectura con lente —el prompt pregunta «¿qué dice sobre
    {name}?» y arma los grep con SUS alias—; lo que faltaba era que el producto lo dijera. El
    prompt nombra la sección destino y el objeto `vista` del JSON, o el subagente devuelve algo
    que el cosechador no puede estampar.

    @inv INV-134"""
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA)
    assert "## Vista — tau Ceti" in p
    assert '"vista"' in p and '"sujeto":"tau Ceti"' in p and '"tipo":"star"' in p
    assert '"txt":"tau_ceti"' in p, "de QUÉ copia del .txt se leyó (el ancla de fuente, D-18)"


def test_la_vista_de_un_tema_declara_tipo_theme():
    p = ep.build_prompt("gp", "2020X", "gaussian processes", [], UNA_COLUMNA, kind="theme",
                        sujeto="gaussian-processes")
    assert "## Vista — gaussian-processes" in p
    assert '"tipo":"theme"' in p and '"sujeto":"gaussian-processes"' in p


def test_el_sujeto_de_la_vista_puede_diferir_del_nombre_del_prompt():
    """En un tema `theme_by_slug` devuelve el SLUG, y el nombre con el que el paper lo declara en
    `thesis_links` es el `concept`. Si la vista se escribiera con el slug, `reclamo_sin_vista` la
    reportaría para siempre: dos nombres para el mismo sujeto, que es la conflación de siempre con
    otra cara.

    @inv INV-134"""
    p = ep.build_prompt("gp", "2020X", "gp", [], UNA_COLUMNA, kind="theme",
                        sujeto="gaussian-processes")
    assert '"sujeto":"gaussian-processes"' in p and '"sujeto":"gp"' not in p


def test_sin_sujeto_explicito_la_vista_usa_el_nombre():
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA)
    assert '"sujeto":"tau Ceti"' in p


# ── #192 / #193 · el prompt declara el TERCER ESTADO ────────────────────────────────────────────
#
# Los dos detectores que alimentan el prompt tienen un estado «no se pudo medir» y el prompt lo
# callaba, así que al extractor le llegaban IGUALES «el `.txt` está completo» y «nadie pudo medirlo».
# Es el falso limpio que el framework persigue en todos lados —la cobertura de `discover` distingue
# *corrió con N* / *FALLÓ* / *NO CORRIÓ*; el lint tiene la categoría `⛔ No evaluado`— y acá estaba
# justo en el eje que decide si una fórmula se cita del `.txt` o del PDF.
#
# Medido sobre 167 `.txt` de una bóveda real: **69 (41 %)** vuelven no-evaluados de `symbols_lost`,
# y **12 (7 %)** caen en la banda gris del umbral de maqueta. Dos casos verificados a mano perdieron
# TODAS sus ecuaciones sin que nada lo dijera (`1995BellSejnowski`, `2004Himberg`), y de ahí salió
# una nota que afirmaba `tanh⁻¹` donde el PDF dice `tan⁻¹`.

SIN_ECUACIONES = "Una prosa cualquiera sin marcadores de ecuacion.\n" * 40


CON_ECUACIONES = "\n".join(f"  x_{i} = A s_{i} + n_{i}     ({i})" for i in range(1, 9))


@pytest.mark.parametrize("texto,estado", [
    (SIN_ECUACIONES, "no se pudo medir"),                       # None — 41 % de un corpus real
    (CON_ECUACIONES, "NO prueba"),                              # False — 45 de 67, el bucket ciego
    (cfg.FULLTEXT_SYMBOLS_MARK + "\n" + CON_ECUACIONES, "vació"),   # True
])
def test_una_sola_regla_para_las_ecuaciones_en_los_tres_estados(texto, estado):
    """#192 + #194, resueltos con **una** regla en vez de tres redacciones.

    Los tres estados del detector terminan en la misma instrucción —confirmá la fórmula contra el
    PDF—, así que tres mensajes distintos decían lo mismo tres veces y dejaban que el extractor
    leyera dos de ellos como un permiso. Lo único que el estado cambia es el ALCANCE (con la marca
    confirmada, toda la lectura de fórmulas se muda al PDF y se cita por página); el estado medido
    viaja igual, para que se sepa qué se sabía.

    @inv INV-38"""
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, texto)
    assert "no es fuente confiable para una ECUACIÓN" in p
    assert "vault/raw/pdfs/tau_ceti/2017AJ....154..135F.pdf" in p, "decir QUÉ PDF abrir"
    assert estado in p, "el estado medido viaja, aunque la instrucción sea la misma"


def test_solo_la_marca_confirmada_muda_la_cita_a_la_pagina():
    """Contra-caso del alcance: `None` y `False` NO mandan a citar por página. La cita por defecto
    sigue siendo la línea del `.txt`, y convertir una duda en esa certeza encarecería cada
    extracción del corpus (el 86 % de los `.txt` medidos no lleva la marca)."""
    for texto in (SIN_ECUACIONES, CON_ECUACIONES):
        p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, texto)
        assert "página del PDF" not in p
    marcado = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES,
                              cfg.FULLTEXT_SYMBOLS_MARK + "\n" + CON_ECUACIONES)
    assert "página del PDF" in marcado and "NO están en este `.txt`" in marcado


def test_el_prompt_declara_la_maqueta_medida_en_las_dos_direcciones():
    """#193: el aviso de dos columnas salía sólo por encima del umbral y por debajo no salía nada,
    así que una clasificación equivocada era indistinguible de una correcta. Medido: dos errores en
    direcciones OPUESTAS, los dos pegados al umbral (0.276 clasificado una-columna siendo de dos;
    0.379 clasificado dos siendo de una). El prompt publica la fracción medida y su umbral, y pide
    que el lector avise si no coincide con lo que ve — sin inventar un umbral nuevo."""
    una = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA)
    dos = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, DOS_COLUMNAS)
    for p in (una, dos):
        assert "fracción medida" in p, "el prompt publica el NÚMERO, no sólo el veredicto"
        assert "decilo en `salvedades`" in p
    assert "UNA columna" in una and "DOS COLUMNAS" in dos


# ── #195 · el dato que vive en una imagen: 45 % del corpus, y la regla dura sólo cubría ecuaciones ──


def test_la_regla_de_la_tabla_es_dura_y_nombra_el_PDF():
    """La asimetría que #195 corrige: para las ECUACIONES había regla dura —se levanta del PDF y
    viaja con su página—, para las tablas una instrucción blanda («mirá las tablas») y para las
    figuras nada. Un valor de tabla-imagen que sostiene una afirmación corre el mismo riesgo, y son
    el 45 % de las vistas de un tema real.

    Como en #153: la RUTA, no sólo la palabra «PDF». Un extractor que recibe el aviso sin saber qué
    archivo abrir no recibió nada.  @inv INV-100"""
    # Sobre `_media_note`, NO sobre el prompt entero: la ruta del PDF también la emite la regla de
    # ecuaciones, así que un assert contra `p` pasa aunque la regla de tabla se quede sin ruta.
    # (Cazado con `mutar.py --dirigida`: la primera versión de este test sobrevivía a la mutación.)
    nota = ep._media_note("ica", "1994Comon")
    assert "TABLA" in nota
    assert "vault/raw/pdfs/ica/1994Comon.pdf" in nota, "la regla de tabla tiene que decir QUÉ PDF"
    assert "cómo verificaste la fila" in nota, (
        "falta la mitad de la regla: en una tabla multi-objeto la fila equivocada es el modo de "
        "falla, y el entrelazado de columnas parte las filas")
    assert nota in ep.build_prompt("ica", "1994Comon", "ICA", [], "Texto limpio.\n", kind="theme"), \
        "la regla existe pero no llega al subagente"


def test_la_lectura_de_figura_esta_permitida_y_declarada():
    """Permiso, no obligación, y con las tres declaraciones que la distinguen de inventar el
    número: figura + página, el `≈` explícito, y la palabra «lectura de gráfico». Es la doctrina de
    `inferencia` — la bóveda puede sostener algo que ninguna fuente escribe **siempre que declare de
    dónde salió**."""
    p = ep.build_prompt("ica", "2019Pfister", "ICA", [], "Texto limpio.\n", kind="theme")
    assert "lectura de gráfico" in p
    assert "Fig. 3, p. 7" in p, "sin el formato del localizador la marca queda a criterio de cada agente"
    assert "≈" in p, "un valor leído de una curva sin el aproximado se lee como publicado"
    assert "hueco declarado" in p, (
        "falta la escotilla: si la curva no permite leer el valor con confianza, forzarlo es peor "
        "que el hueco")


def test_la_regla_de_medios_no_depende_de_la_marca_de_simbolos():
    """A diferencia de la de ecuaciones (#113), ésta va SIEMPRE: `symbols_lost` mide si `pdftotext`
    vació las fórmulas y no dice nada sobre si las tablas del paper son imágenes."""
    limpio = ep.build_prompt("ica", "1994Comon", "ICA", [], "Texto limpio.\n", kind="theme")
    marcado = ep.build_prompt("ica", "1994Comon", "ICA", [],
                              f"{cfg.FULLTEXT_SYMBOLS_MARK} simbolos NO extraidos\nx\n", kind="theme")
    for p in (limpio, marcado):
        assert "lectura de gráfico" in p


def test_el_localizador_no_se_llama_solo_numero_de_linea():
    """Si el prompt sigue pidiendo «el nº de línea» a secas, una página o una figura no tienen dónde
    ir y vuelven como línea inventada."""
    # Contra la SECCIÓN, no contra el prompt entero: la palabra «localizador» también aparece en la
    # regla de figuras, así que el assert global pasaba con la instrucción vieja intacta.
    p = ep.build_prompt("ica", "1994Comon", "ICA", [], "Texto limpio.\n", kind="theme")
    seccion = p.split("## Cómo anotar cada valor")[1].split("## Salida")[0]
    assert "localizador" in seccion.lower(), "la sección de anotado sigue pidiendo sólo la línea"
    assert "Fig. N, p. M" in seccion, "sin el formato, una lectura de gráfico vuelve como línea"
    assert "página" in seccion, "una tabla-imagen no tiene dónde poner su página"
