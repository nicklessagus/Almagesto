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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extraction_prompt as ep

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
    assert "columna" in dos.lower()
    assert "columna" not in una.lower(), "no inventar el caveat cuando la maqueta es de una columna"


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
