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
from conftest import mk_note

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
    # @inv INV-100
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


# ── #281 · la figura que es un CAMPO: «el valor a x» no existe sin el NIVEL ─────────────────────


def test_la_figura_que_es_un_campo_pide_el_NIVEL():
    """#281 extiende #195, que asume que una figura es una CURVA. Cuando es un campo —contornos,
    mapa de color, densidad— «el valor a x» no está definido sin el nivel, y dos lecturas honestas
    de la misma figura devuelven números distintos. Medido sobre la Fig. H.2 de
    `2023A&A...680A..64D`: tres lecturas «irreconciliables» de la banda de 30-50 M_J (2-3, 1,8-4 y
    3,5-6 UA) eran los contornos del 10, 50 y 90 % de la MISMA figura.

    @inv INV-100"""
    nota = ep._media_note("hd40307", "2023A&A...680A..64D").lower()
    assert "contorno del" in nota, "sin el formato del nivel, la lectura de un campo no es citable"
    assert "no existe sin el nivel" in nota, \
        "la regla es que el valor NO está definido sin el nivel, no que convenga aclararlo"


def test_el_prompt_emitido_lleva_la_regla_del_campo():
    """La frontera donde INV-100 mide que las reglas se caen: la regla puede existir en
    `_media_note` y no llegar al subagente. Va con y sin PDF —el prompt ramifica por verdad de
    disco (#255)— porque leer una figura es justamente lo que se hace con el PDF abierto.

    @inv INV-100"""
    con_pdf = ep.build_prompt("ica", "1994Comon", "ICA", [], "Texto limpio.\n", kind="theme")
    sin_pdf = ep.build_prompt("test_star", "2020SinPDF", "Estrella Test", ["HD 12345"])
    for p in (con_pdf, sin_pdf):
        assert "contorno del" in p, "la regla existe pero no llega al subagente"


def test_dos_lecturas_que_no_reconcilian_apuntan_primero_a_la_figura():
    """El orden es la mitad del arreglo (#281): la salida «hueco declarado» CIERRA la puerta —dice
    «el corpus no puede responder esto» y el consumidor deja de buscar—, así que la sospecha de
    figura subespecificada tiene que leerse ANTES. En el caso medido el corpus sí tenía la
    respuesta, con más precisión que la que la ficha pedía.

    @inv INV-100"""
    nota = ep._media_note("hd40307", "2023A&A...680A..64D")
    assert "SUBESPECIFICADA" in nota
    salida = "sigue siendo un **hueco declarado**"
    assert salida in nota, "la escotilla de #195 no se reemplaza: se extiende"
    assert nota.index("SUBESPECIFICADA") < nota.index(salida), \
        "primero se sospecha de la figura; el hueco declarado es la última salida, no la primera"


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


def test_documento_LARGO_no_manda_empezar_por_las_conclusiones(toy_vault):
    """#241 — los dos campos de #80 estaban cableados de punta a punta SALVO el último tramo: el
    prompt no los leía. Una tesis de 161 páginas recibía las mismas instrucciones que un paper de
    11: «`Read` lo rasteriza, así que ves la página» (700 páginas no se rasterizan, lo dice el
    propio contrato) y «empezá por las CONCLUSIONES» (un libro no las tiene, y el mismo contrato
    prohíbe transcribirlas)."""
    from conftest import mk_note
    mk_note(toy_vault.PAPERS, "2009Wiklund",
            {"bibcode": "2009Wiklund", "tags": ["paper"], "thesis_links": ["ica"],
             "unidad_cita": "pagina", "alcance": "caps. 2-3 (formulación y métodos)"}, "# t\n")
    p = ep.build_prompt("ica", "2009Wiklund", "ica", ["ICA"], kind="theme")
    assert "empezá por el ÍNDICE" in p
    assert "empezá por las CONCLUSIONES" not in p, \
        "la estrategia de lectura que el contrato prohíbe para esta fuente"
    assert "caps. 2-3 (formulación y métodos)" in p, "el alcance declarado tiene que llegar al lector"
    assert "`conclusiones` va VACÍO" in p


def test_documento_CORTO_conserva_la_lectura_por_conclusiones(toy_vault):
    """#241, el simétrico: la rama se elige por `unidad_cita`, y el caso normal —una fuente que se
    cita por línea— no cambia en nada."""
    from conftest import mk_note
    mk_note(toy_vault.PAPERS, "2020corto", {"bibcode": "2020corto", "tags": ["paper"],
                                      "thesis_links": ["ica"]}, "# t\n")
    p = ep.build_prompt("ica", "2020corto", "ica", ["ICA"], kind="theme")
    assert "empezá por las CONCLUSIONES" in p and "empezá por el ÍNDICE" not in p


def test_documento_largo_SIN_alcance_lo_declara_en_vez_de_callar(toy_vault):
    """#241 — `ingest_theme` aborta si falta el `alcance`, pero una nota vieja o editada a mano
    puede llegar sin él. Ahí el prompt lo DICE: sin alcance no se sabe qué parte entra, y callarlo
    dejaría al extractor leyendo el libro completo sin enterarse."""
    from conftest import mk_note
    mk_note(toy_vault.PAPERS, "2010Libro", {"bibcode": "2010Libro", "tags": ["paper"],
                                      "thesis_links": ["ica"], "unidad_cita": "pagina"}, "# t\n")
    p = ep.build_prompt("ica", "2010Libro", "ica", ["ICA"], kind="theme")
    assert "NO DECLARADO" in p


# ── #254 · los ejes son la lente de ESTA bóveda, no un literal ───────────────────────────────────

def test_los_ejes_salen_de_las_facetas_del_objetivo(toy_vault):
    """#254: el esqueleto de `ejes` era un literal de cinco claves —las del `objective.yaml` de
    ejemplo del template— y `extraction_prompt` no leía `relevance.facets` en ninguna parte. Toda
    faceta que una instancia declarara de más **no se le preguntaba a ningún extractor**, y la vista
    volvía sin la clave: indistinguible de «se miró y no hay nada», el falso limpio que #188 cerró
    con `vistas[]`, reapareciendo un nivel más abajo.

    Medido sobre una bóveda cuyo objetivo declara ocho facetas, en 28 extracciones de una estrella:
    los cinco cableados 28/28, y `detection`, `ml` y `simulation` —una por capítulo de la tesis—
    entre 1 y 2 de 28, y esos pocos de extractores que fueron a leer `objective.yaml` por su cuenta.

    @inv INV-143"""
    esqueleto = ep.axes_skeleton()
    assert '"actividad":""' in esqueleto and '"rv":""' in esqueleto, \
        "las facetas del objetivo de la bóveda"
    assert '"discovery"' not in esqueleto, \
        "y NADA del literal viejo: la lente de la instancia manda, no la del template"
    assert esqueleto.index('"actividad"') < esqueleto.index('"rv"'), \
        "en el orden del YAML, para que dos corridas se comparen"


def test_el_prompt_emitido_lleva_esos_ejes(toy_vault):
    """La otra mitad: que la función exista no alcanza si el prompt sigue emitiendo el literal — es
    la frontera donde INV-100 mide que las reglas se caen.  @inv INV-143"""
    prompt = ep.build_prompt("test_star", "2020Test", "Estrella Test", ["HD 12345"])
    assert '"ejes":{"actividad":"","rv":""}' in prompt


def test_sin_facetas_legibles_el_prompt_lo_DICE(toy_vault, monkeypatch):
    """Un objetivo ilegible o con `facets` vacía no degrada al literal viejo: eso sería clasificar
    la lectura con una lente que nadie escribió, y es la misma negativa que `query_ads` opone a una
    lente ilegible (INV-80). El extractor recibe la orden de frenar, no un juego de ejes inventado.

    @inv INV-143"""
    monkeypatch.setattr(cfg, "load_objective", lambda: {"relevance": {"facets": {}}})
    esqueleto = ep.axes_skeleton()
    assert "SIN_FACETAS" in esqueleto and "NO inventes ejes" in esqueleto
    assert '"rv"' not in esqueleto, "no se rellena con la lente del template"


# ── #255 · el prompt ramifica por VERDAD DE DISCO ────────────────────────────────────────────────
#
# Los tests de arriba ejercen la rama NORMAL (PDF y `.txt` en disco), que es lo que quieren probar.
# Antes de #255 el prompt no miraba el disco, así que corrían sin artefactos y no se notaba; hoy la
# diferencia es visible y la fixture tiene que ser fiel al caso que el test describe.
PARES_CON_ARTEFACTOS = [
    ("tau_ceti", "2017AJ....154..135F"), ("gp", "2006Rasmussen"), ("gp", "2020X"),
    ("ica", "1994Comon"), ("ica", "2019Pfister"), ("ica", "2009Wiklund"), ("x", "2020A"),
    ("ica", "2001Hyvarinen"), ("libro", "2001HKO"),
    ("ica", "2020corto"), ("ica", "2010Libro"), ("ica", "2010LibroConAlcance"),
]


@pytest.fixture(autouse=True)
def _artefactos_en_disco(toy_vault):
    """PDF y `.txt` de los pares que los tests de la rama normal usan.

    Explícita a propósito: `2020SinPDF` NO está en la lista, y es el bibcode con el que los tests de
    #255 ejercen la rama sin artefactos."""
    for slug, bib in PARES_CON_ARTEFACTOS:
        pdf = cfg.PDFS / slug / f"{bib}.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4\n")
        txt = cfg.FULLTEXT / slug / f"{bib}.txt"
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text("texto\n", encoding="utf-8")




def test_sin_PDF_el_prompt_manda_al_abstract_y_no_al_PDF(toy_vault):
    """#255: el generador avisaba por **stderr** que no hay PDF y emitía por stdout un prompt cuyo
    cuerpo ordena, con ⛔ y en negrita, «Leé el PDF» — un archivo que no existe. `2>/dev/null` no es
    un caso rebuscado: es el caso normal, porque todo lo que capture la salida (un pipe, un `$(...)`,
    un subagente al que se le pasa el prompt) se queda con stdout y tira el aviso.

    Peor que el silencio de #241: el prompt no omite la instrucción, **ordena la contraria**.

    @inv INV-144"""
    prompt = ep.build_prompt("test_star", "2020SinPDF", "Estrella Test", ["HD 12345"])
    assert "Leé el PDF" not in prompt, "no se manda leer un archivo que no está"
    assert "NO HAY PDF" in prompt and "fuente: abstract" in prompt, \
        "se dice cuál es la fuente real y cómo declararla (#207)"
    assert "afirma DE MÁS" in prompt, \
        "y viaja con la advertencia de generalization bias que #207 pide para este caso"


def test_sin_txt_no_se_emiten_greps_sobre_un_archivo_inexistente(toy_vault):
    """Una docena de `grep` sobre un `.txt` que no existe vuelven todos vacíos, y un grep vacío se
    lee como «el paper no lo dice» — la inferencia que D-43 prohíbe.  @inv INV-144"""
    prompt = ep.build_prompt("test_star", "2020SinPDF", "Estrella Test", ["HD 12345"])
    assert "grep -niE" not in prompt
    assert "NO HAY ÍNDICE" in prompt and "no es «el paper no lo dice»" in prompt


def test_con_PDF_el_prompt_no_cambia(toy_vault):
    """La otra mitad: la rama normal —PDF y `.txt` en disco— sigue diciendo lo de siempre. Sin este
    test, «no mandes leer el PDF» se podría cumplir no mandándolo nunca.  @inv INV-144"""
    prompt = ep.build_prompt("tau_ceti", "2017AJ....154..135F", "tau Ceti", ALIASES, UNA_COLUMNA)
    assert "Leé el PDF" in prompt and "NO HAY PDF" not in prompt
    assert "grep -niE" in prompt and "El `.txt` NO es fuente" in prompt


# ── #245 · el prompt muestra el vocabulario que la bóveda ya tiene ──────────────────────────────

def test_el_prompt_lista_los_metodos_conocidos(toy_vault):
    """#245 — la lista canónica existe (los stems de `concepts/` + sus `aliases`) y el extractor no
    la veía: inventa una grafía por paper. Medido en una bóveda real: 136 métodos distintos, **121
    sin página destino**, muchos el mismo método con dos nombres."""
    mk_note(cfg.CONCEPTS / "methods", "bis", {"tags": ["concept"], "name": "bis",
                                              "aliases": ["bisector span"]}, "# bis\n")
    prompt = ep.build_prompt("tau-cet", "2020aaa...1..1A", "tau Cet", [])
    assert "`bis`" in prompt and "bisector span" in prompt
    assert "no está cerrado" in prompt, "cerrar el vocabulario sería peor que el problema"


def test_sin_conceptos_el_prompt_lo_DICE(toy_vault):
    """Espejo de `SIN_FACETAS` (#254): una lista vacía se leería como «esta bóveda no conoce ningún
    método», que es un cero inventado."""
    assert "todavía no tiene notas" in ep.known_methods()


def test_el_tope_de_metodos_se_DECLARA(toy_vault):
    """#107 — un corte silencioso es cómo se saca una conclusión estructural de un truncamiento que
    nadie declaró. Si hay más métodos que el tope, el prompt dice cuántos quedaron afuera."""
    for i in range(5):
        mk_note(cfg.CONCEPTS / "methods", f"m{i}", {"tags": ["concept"], "name": f"m{i}"}, "# m\n")
    salida = ep.known_methods(tope=2)
    assert "y 3 más (tope declarado: 2)" in salida, salida


# ── #305 · las dos mitades de #207 miran el MISMO disco ─────────────────────
def test_el_prompt_ve_el_PDF_que_esta_bajo_otro_slug(toy_vault):
    """#305 — `extraction_prompt` buscaba el PDF **sólo bajo el slug del sujeto** y
    `harvest_views.pdf_on_disk` bajo todos, así que el prompt mandaba declarar `fuente: abstract`
    sobre papers que SÍ están en disco: #207 al revés — en vez de cazar una lectura degradada, el
    framework la producía, y el cosechador la aceptaba porque `abstract` siempre es legal.

    Pega justo en los retro-tagueados, que por definición ya estaban en el corpus bajo OTRO sujeto:
    medido, 7 de 31, el núcleo fundacional del tema y dos libros de 500+ páginas —que desde el
    abstract no se pueden leer en absoluto—."""
    (cfg.PDFS / "ica").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "ica" / "1998Hyvarinen.pdf").write_bytes(b"%PDF-1.4\n")
    texto = ep.build_prompt("ica_ruido", "1998Hyvarinen", "ICA ruidosa", [], kind="theme")
    assert "Leé el PDF" in texto
    assert "vault/raw/pdfs/ica/1998Hyvarinen.pdf" in texto, "la ruta del archivo QUE EXISTE"
    assert "fuente: abstract" not in texto.split("## Salida")[0]


def test_el_prompt_y_el_COSECHADOR_responden_lo_mismo(toy_vault):
    """Test de PARIDAD (regla de método nº 2): las dos mitades de #207 no pueden diferir. Hoy la
    resolución es una sola función; sin esta red, dos implementaciones vuelven a divergir y el bug
    vive otra vez en la diferencia."""
    import harvest_views as hv
    (cfg.PDFS / "ica").mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / "ica" / "2002Cardoso.pdf").write_bytes(b"%PDF-1.4\n")
    for bib in ("2002Cardoso", "2020sinpdf"):
        del_prompt = cfg.pdf_slug(bib, "ica_ruido") is not None
        assert del_prompt is hv.pdf_on_disk(bib), f"las dos mitades discrepan sobre {bib}"


def test_sin_PDF_en_NINGUN_slug_el_prompt_sigue_mandando_al_abstract(toy_vault):
    """El control de #255: sin PDF en ningún lado, el prompt no puede mandar a leerlo, y la ruta que
    nombra (para el mensaje de faltante) es la del slug del sujeto."""
    texto = ep.build_prompt("ica_ruido", "2020sinpdf", "ICA ruidosa", [], kind="theme")
    assert "Leé el PDF" not in texto
    assert "vault/raw/pdfs/ica_ruido/2020sinpdf.pdf" in texto


# ── #307 · los ejes del TEMA (la mitad simétrica de D-26) ───────────────────
def test_los_ejes_salen_del_TEMA_cuando_los_declara(toy_vault, monkeypatch):
    """#307 — D-26 hizo propia la faceta del tema porque la lente global es «activamente dañina»
    ahí, y #254 derivó los ejes de lectura de la lente… global. Medido sobre 32 extracciones de un
    tema de método: `rv`/`activity`/`planet`/`discovery` poblados en **7 de 32** (los mismos 7: sus
    únicas fuentes astro), y los ejes que el tema necesitaba —identificabilidad, heterocedasticidad
    por época y por canal— **no se preguntaron nunca**, así que volvieron desparramados en `aporte`
    y sin clave con la que compararlos."""
    monkeypatch.setattr(ep.cfg, "load_objective",
                        lambda: {"relevance": {"facets": {"rv": "radial velocity",
                                                          "activity": "activity"}}})
    assert ep.axes_skeleton() == '{"rv":"","activity":""}'
    meta = {"title": "ICA ruidosa", "facet": "noisy ICA",
            "ejes": ["heterocedasticidad", "identificabilidad", "blanqueo"]}
    assert ep.axes_skeleton(meta) == \
        '{"heterocedasticidad":"","identificabilidad":"","blanqueo":""}'
    # tres estados (D-43): sin declarar hereda; declarado vacío es una DECISIÓN, no un olvido
    assert ep.axes_skeleton({"title": "T"}) == '{"rv":"","activity":""}'
    assert "SIN_EJES" in ep.axes_skeleton({"title": "T", "ejes": []})


# ── #308 · la segunda lectura con otra lente se puede PEDIR ─────────────────
def test_el_prompt_de_una_SEGUNDA_lente(toy_vault):
    """#308 — #239 construyó toda la mitad de cosecha (`### Lente — <énfasis>`, la identidad
    `(sujeto, enfasis)`, la guarda de no pisar) y **nada podía producir ese JSON**: el prompt no
    mencionaba `enfasis` ni tenía bandera, así que el único camino era escribirlo a mano — que es
    lo que INV-100 prohíbe. Misma forma que #210/INV-132: capacidad documentada, mitad cara ya
    construida, sin entrada de usuario."""
    texto = ep.build_prompt("ica_ruido", "2002Cardoso", "ICA ruidosa", [], kind="theme",
                            sujeto="ica-ruido", enfasis="ruido por canal",
                            ejes_cli=["heterocedasticidad", "canales"])
    assert "SEGUNDA lectura" in texto and "«ruido por canal»" in texto
    assert '"enfasis": "ruido por canal"' in texto
    assert "no re-narres" in texto and "## Conclusiones" in texto
    assert '"ejes":{"heterocedasticidad":"","canales":""}' in texto
    # sin `--enfasis`, el prompt es el de siempre (la primera lectura no cambia)
    normal = ep.build_prompt("ica_ruido", "2002Cardoso", "ICA ruidosa", [], kind="theme",
                             sujeto="ica-ruido")
    assert "SEGUNDA lectura" not in normal
