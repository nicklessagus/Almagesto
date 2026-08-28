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


def test_prompt_pide_lo_verificable_de_103():
    """Lo que sí funciona es lo chequeable: localizador, régimen, segunda mano, tiempo verbal.
    Desde #205 el localizador es la **página** del PDF, no el nº de línea del `.txt`."""
    p = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA).lower()
    for exigido in ("página", "régimen", "segunda mano", "tiempo verbal", "cuantificador"):
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


def test_el_prompt_manda_al_PDF_SIEMPRE_y_dice_cual():
    """#205 — la fuente de lectura es el PDF, incondicionalmente.

    Hasta acá el prompt mandaba al PDF sólo con `symbols_lost: true` (#153), y esa rama condicional
    dependía de un detector que no discrimina: medido el 2026-08-28, un paper con los TRES chequeos
    en verde había perdido igual el radical `√`, la prima de `p′` y superíndices de transpuesta.
    La rama se elimina y el PDF pasa a ser la fuente.

    La RUTA, no sólo la palabra «PDF»: el gate de mutación ya cazó una vez que `_pdf_rel` sobrevivía
    porque los asserts miraban palabras de la prosa fija.  @inv INV-100"""
    for texto in ("Texto limpio, sin marca.\n",
                  f"{cfg.FULLTEXT_SYMBOLS_MARK} simbolos NO extraidos\nLa ecuacion (3).\n"):
        p = ep.build_prompt("gp", "2006Rasmussen", "GP", [], texto, kind="theme")
        assert "vault/raw/pdfs/gp/2006Rasmussen.pdf" in p, "no dice QUÉ PDF abrir"
        assert "PÁGINA del PDF" in p, "la cita va por página"


def test_el_prompt_declara_que_el_txt_NO_es_fuente():
    """La otra mitad de #205: el `.txt` sigue en el prompt —sirve para UBICAR dónde mirar— y por eso
    hay que decir explícitamente que no se cita de ahí. Sin esa frase, un extractor que ve la ruta
    del `.txt` y los patrones de `grep` razonablemente concluye que puede transcribir de ahí."""
    p = ep.build_prompt("gp", "2006Rasmussen", "GP", [], "Texto limpio.\n", kind="theme")
    plano = " ".join(p.split())          # el prompt viene reflowado: la frase cruza saltos de línea
    assert "El `.txt` NO es fuente" in plano
    assert "vault/raw/fulltext/gp/2006Rasmussen.txt" in p, "el .txt sigue nombrado, para ubicar"
    assert "índice de búsqueda" in plano


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


# ── #195 · el dato que vive en una imagen: 45 % del corpus, y la regla dura sólo cubría ecuaciones ──


def test_de_la_regla_de_tabla_sobrevive_la_fila_verificada():
    """#195 → #205. Leyendo el PDF, «levantá el valor del PDF» es redundante y se cae. Lo que NO se
    cae es el criterio de lectura: en una tabla multi-objeto **la fila equivocada es el modo de
    falla**, y eso no lo arregla cambiar de archivo."""
    nota = ep._media_note("ica", "1994Comon")
    assert "cómo la verificaste" in nota
    assert "multi-objeto" in nota
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


def test_el_prompt_manda_empezar_por_las_conclusiones_como_HIPOTESIS():
    """#124 — leer por las conclusiones es más rápido y es exactamente donde vive el «afirmar de
    más» (generalization bias, RSOS 2025). Por eso el prompt no puede pedir sólo «leelas primero»:
    tiene que decir que se **chequean contra el cuerpo**, o el paso importa el overclaim del paper
    a la nota."""
    p = ep.build_prompt("ica", "1994Comon", "ICA", [], "Texto limpio.\n", kind="theme")
    plano = " ".join(p.split())
    assert "conclusiones" in plano.lower()
    assert "hipótesis a confirmar" in plano, "sin esto son un resumen confiable, que es lo que no son"
    assert "más fuerte" in plano, "el motivo medido tiene que viajar"


def test_el_prompt_pide_las_tres_ayudas_de_lectura():
    p = ep.build_prompt("ica", "1994Comon", "ICA", [], "Texto limpio.\n", kind="theme")
    for campo in ("abstract_es", "conclusiones", "conclusiones_es"):
        assert f'"{campo}"' in p, f"el JSON de salida no pide {campo}"
    plano = " ".join(p.split())
    assert "nunca fuente de la que citar" in plano
    assert "unidad_cita: pagina" in plano, "el caso del libro tiene que estar declarado"


# ── nombres que devolvían CERO patrones (auditoría 2026-08-28) ──────────────────────────────────


@pytest.mark.parametrize("nombre", ["AU Mic", "55 Cnc", "eps Eri", "K2-18", "TRAPPIST-1"])
def test_los_nombres_cortos_ya_no_dan_cero_patrones(nombre):
    """Medido: los cinco daban `[]`, y `AU Mic` es el ejemplo del propio skill `ingest-star`. Tres
    huecos que se tapaban entre sí: `MIN_ALPHA=4` generaba la abreviatura DESDE el token largo
    (`Ceti`→`Cet`) y rechazaba el nombre **ya abreviado** —la grafía que la función existe para
    perseguir—; una designación con dígitos (`K2-18`) no es `isalpha()`; y nada devolvía el nombre
    entero cuando ningún token calificaba solo.  @inv INV-100"""
    pats = ep.subject_patterns(nombre)
    assert pats, f"{nombre!r} no genera ningún patrón: el grep no corre y se lee como «no lo reporta»"


def test_un_tema_no_baja_el_umbral_de_los_tokens_cortos():
    """La otra mitad: en un tema los tokens son palabras comunes y truncar a tres letras sólo hace
    ruido. El umbral bajo es **sólo** para estrellas."""
    assert "pro" not in ep.subject_patterns("procesos gaussianos", kind="theme")
    assert ep.subject_patterns("procesos gaussianos", kind="theme") == ["gaussianos", "procesos"]


def test_sin_patrones_el_prompt_lo_DECLARA_en_vez_de_salir_vacio():
    """El daño real no era la lista vacía: era que el prompt salía con el bloque de búsqueda en
    blanco **bajo un encabezado que promete patrones**, y el extractor concluía «no dice nada del
    sujeto» sin haber buscado.  @inv INV-100"""
    p = ep.build_prompt("x", "2020A", "", [], "texto\n")
    assert "NINGÚN patrón se pudo generar" in p
    assert "NO es «el paper no lo reporta»" in p


# ── la precondición de `main` (AUD-133) ──────────────────────────────────────

def _run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["extraction_prompt.py", *argv])
    return ep.main()


def test_la_precondicion_mira_el_PDF_no_el_txt(toy_vault, monkeypatch, capsys):
    """AUD-133 — regresión de #205: validaba el `.txt` y abortaba, mientras el prompt que emite
    dice «⛔ Leé el PDF». O sea que chequeaba el artefacto viejo y **nunca** el que se lee.

    Hoy el `.txt` es el índice de búsqueda: su ausencia degrada los `grep` del prompt y se
    **declara**, no corta. Lo que sí importa es el PDF."""
    from conftest import mk_note
    bib = "2020aaaA...1..1A"
    mk_note(toy_vault.PAPERS, bib, {"bibcode": bib, "tags": ["paper"]}, "")
    pdf = cfg.ROOT / "vault" / "raw" / "pdfs" / "test_star" / f"{bib}.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4\n")

    # con PDF y SIN `.txt`: el prompt sale igual, y la degradación se dice
    assert _run_main(monkeypatch, ["test_star", bib]) == 0
    cap = capsys.readouterr()
    assert "Leé el PDF" in cap.out, "el prompt tiene que salir"
    assert "los `grep` del prompt NO van a correr" in cap.err

    # sin PDF pero con nota: no corta — la vista sale del abstract y se declara (#207)
    pdf.unlink()
    assert _run_main(monkeypatch, ["test_star", bib]) == 0
    assert "fuente: abstract" in capsys.readouterr().err

    # sin PDF y sin nota: no hay NADA que leer
    (toy_vault.PAPERS / f"{bib}.md").unlink()
    assert _run_main(monkeypatch, ["test_star", bib]) == 1
    assert "no hay nada que" in capsys.readouterr().out
