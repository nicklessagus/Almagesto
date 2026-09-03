"""contrast.py — el lector de extracciones del paso 3c (#314/#317).

Qué protege este archivo, en una línea: **la herramienta que evita el error tiene que existir, o el
error se comete** (INV-100 aplicado al único eslabón que no tenía tooling). El defecto medido fue un
digest ad-hoc con `valor[:200]` que cortó dentro de una cita textual y el modelo la completó con lo
plausible — 2 citas fabricadas sobre 139 pares, las dos en el carácter exacto del corte.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import contrast as ct  # noqa: E402
import lib_config as cfg  # noqa: E402

LARGA = ("which requires the latent signals to be whitened before the model can be identified, "
         "and that condition is not the same as knowing the noise covariance")


def _txt(slug: str, bib: str, texto: str = "prosa del paper que no dice la cita"):
    """El `.txt` de la fuente. Sin él la cita **no es evaluable** (#324): la extracción es selectiva,
    así que sin poder mirar el índice de su propio paper no se puede afirmar que la cita se movió."""
    (cfg.FULLTEXT / slug).mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / slug / f"{bib}.txt").write_text(texto, encoding="utf-8")


def _extraccion(slug: str, bib: str, **cambios):
    d = {"bibcode": bib, "ejes": {"identificabilidad": "hace falta Sigma conocida"},
         "ground_truth": [{"que": "blanqueo", "valor": LARGA, "linea": "p. 4",
                           "regimen": "ruido gaussiano", "segunda_mano": None}]}
    d.update(cambios)
    (cfg.EXTRACCION / slug).mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / slug / f"{bib}.json").write_text(json.dumps(d), encoding="utf-8")


def test_por_default_NO_trunca_la_cita(toy_vault, capsys):
    """La garantía dura de #314: cualquier recorte del `valor` cae dentro de una cita textual, y el
    modelo la completa con lo plausible. Si no entra, el remedio es filtrar menos filas."""
    _extraccion("ica_ruido", "2013Voss")
    assert ct.main(["ica_ruido"]) == 0
    out = capsys.readouterr().out
    assert LARGA in out, "la cita entera o nada"
    assert "CORTADO" not in out


def test_con_corto_el_recorte_se_MARCA_y_respeta_los_bloques(toy_vault, capsys):
    """Cuando se pide acortar, el corte usa `truncate_claim` —que ya retrocede fuera de `$…$`,
    backticks y `[[ ]]`— y queda **visible**, para que nadie cite desde ahí."""
    _extraccion("ica_ruido", "2013Voss")
    ct.main(["ica_ruido", "--corto", "--limite", "40"])
    out = capsys.readouterr().out
    assert "CORTADO: no lo cites desde acá" in out
    assert LARGA not in out


def test_la_procedencia_viaja_con_cada_valor(toy_vault, capsys):
    """Los seis errores de atribución de la corrida medida salieron de un digest que tenía el
    `linea` y el `segunda_mano` en el JSON y no los imprimía."""
    _extraccion("ica_ruido", "2004Davies", ground_truth=[
        {"que": "dureza", "valor": "the issues become significantly more complicated",
         "linea": "p. 2", "segunda_mano": "según Hyvärinen 1998"}])
    ct.main(["ica_ruido"])
    out = capsys.readouterr().out
    assert "p. 2" in out and "SEGUNDA MANO" in out


def test_filtrar_por_campo_grep_y_eje(toy_vault, capsys):
    """Contrastar es FILTRAR, no leer 32 archivos de 25 KB."""
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "2015Voss", ground_truth=[
        {"que": "otra cosa", "valor": "nada que ver con el eje", "linea": "p. 9"}])
    ct.main(["ica_ruido", "--grep", "whitened"])
    out = capsys.readouterr().out
    assert "2013Voss" in out and "2015Voss" not in out
    ct.main(["ica_ruido", "--eje"])
    out = capsys.readouterr().out
    assert "eje `identificabilidad`" in out


def test_las_filas_llevan_UNA_sola_fuente_y_la_CITA_ADENTRO(toy_vault, capsys):
    """Agrupar bibcodes bajo una glosa compartida es cómo se fabrican atribuciones (6 medidas): que
    agrupar sea una decisión explícita y no la salida natural.

    #322 — y la fila sale **con la cita adentro**, entre comillas y con su localizador: los 12
    verdaderos positivos del gate eran errores de **copiado** (6 de atribución, 6 de cola alterada),
    o sea de mover una cadena de un archivo a otro. Si el sintetizador no re-tipea, esas dos clases
    desaparecen por construcción."""
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "2004Davies")
    ct.main(["ica_ruido", "--filas"])
    salida = capsys.readouterr().out
    filas = [l for l in salida.splitlines() if l.startswith("| ")]
    assert len(filas) == 2
    assert all(l.count("[[") == 1 for l in filas), "una fila, una fuente"
    assert all(LARGA in l for l in filas), "la cadena ENTERA, del JSON, no un esqueleto"
    # ⛔ #330 — y sin comillas puestas por el script: `LARGA` no las trae, así que la fila no puede
    # presentarla como verbatim (ver los tests por forma, más abajo).
    assert all("«" not in l.split("|")[3] for l in filas)
    assert all("(p. 4)" in l for l in filas), "el localizador viaja pegado a la cita"
    assert all(ct.GLOSA in l for l in filas), "el único hueco es la glosa, y es visible"
    assert "no la re-tipees" in salida


def test_validar_caza_la_cita_ATRIBUIDA_A_LA_FUENTE_EQUIVOCADA(toy_vault, capsys):
    """#317/#321 — la mitad más frecuente de los verdaderos positivos (6 de 12): la frase está
    verbatim, pero en la extracción de OTRO paper citado por la nota. Eso es evidencia positiva de
    que la cita se movió, y no admite la excusa del `.txt` degradado."""
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "2004Davies", ground_truth=[
        {"que": "otro", "valor": "algo completamente distinto", "linea": "p. 9"}])
    _txt("ica_ruido", "2004Davies")
    nota = cfg.CONCEPTS / "methods" / "ica-ruido.md"
    nota.parent.mkdir(parents=True, exist_ok=True)
    nota.write_text("---\ntags: [concept]\n---\n\n# ICA ruidosa\n\n"
                    f"Dice «{LARGA}» [[2004Davies]], y lo discute [[2013Voss]].\n",
                    encoding="utf-8")
    assert ct.main(["--validar", str(nota)]) == 1
    out = capsys.readouterr().out
    assert "2013Voss" in out and "atribuida a la fuente equivocada" in out


def test_validar_caza_la_cita_COMPLETADA_al_copiar(toy_vault, capsys):
    """#314/#321 — la otra mitad (6 de 12): el arranque coincide con la extracción y la cola
    diverge. Es la firma del digest truncado que el modelo completó con lo plausible."""
    _extraccion("ica_ruido", "2013Voss")
    _txt("ica_ruido", "2013Voss")
    nota = cfg.CONCEPTS / "methods" / "ica-ruido.md"
    nota.parent.mkdir(parents=True, exist_ok=True)
    nota.write_text("---\ntags: [concept]\n---\n\n# ICA ruidosa\n\n"
                    f"Dice «{LARGA[:80]} y por lo tanto el problema es mucho más difícil» "
                    f"[[2013Voss]].\n", encoding="utf-8")
    assert ct.main(["--validar", str(nota)]) == 1
    assert "la cola diverge" in capsys.readouterr().out


def test_el_SILENCIO_de_la_extraccion_no_bloquea(toy_vault, capsys):
    """#321 — la extracción es una transcripción **selectiva y lenteada** (#188) y el framework manda
    citar del PDF (#205): su silencio no prueba fabricación. Medido, sólo 12 de 32 hits eran reales
    y entre los otros 20 había una cita que #315 usa como ejemplo de cita CORRECTA. Se declara como
    no evaluable (D-43), nunca como hallazgo."""
    _extraccion("ica_ruido", "2013Voss")
    _txt("ica_ruido", "2013Voss")
    nota = cfg.CONCEPTS / "methods" / "ica-ruido.md"
    nota.parent.mkdir(parents=True, exist_ok=True)
    nota.write_text("---\ntags: [concept]\n---\n\n# ICA ruidosa\n\n"
                    "El método «una frase legítima leída del PDF y no transcripta» "
                    "[[2013Voss]].\n", encoding="utf-8")
    assert ct.main(["--validar", str(nota)]) == 0
    out = capsys.readouterr().out
    assert "la transcripción es SELECTIVA" in out and "1 no evaluable" in out


def test_validar_calla_cuando_la_nota_es_FIEL_a_la_extraccion(toy_vault, capsys):
    """El control, y la diferencia con #220: la cita puede no estar en el `.txt` (degradado) y estar
    en la extracción — ahí la nota está bien y no hay nada que reportar."""
    _extraccion("ica_ruido", "2013Voss")
    nota = cfg.CONCEPTS / "methods" / "ica-ruido.md"
    nota.parent.mkdir(parents=True, exist_ok=True)
    nota.write_text("---\ntags: [concept]\n---\n\n# ICA ruidosa\n\n"
                    f"Dice «{LARGA}» [[2013Voss]].\n", encoding="utf-8")
    assert ct.main(["--validar", str(nota)]) == 0
    assert "0 cita(s) con evidencia positiva de alteración" in capsys.readouterr().out


def test_la_nota_de_filas_sale_SOLO_con_filas(toy_vault, capsys):
    """El aviso existe para que agrupar sea una decisión consciente; sin filas que mostrar sería
    ruido, y un aviso que se imprime siempre se deja de leer."""
    _extraccion("ica_ruido", "2013Voss")
    ct.main(["ica_ruido", "--filas", "--grep", "nada-que-matchee"])
    assert "ESQUELETO" not in capsys.readouterr().out
    ct.main(["ica_ruido"])                       # sin --filas tampoco
    assert "ESQUELETO" not in capsys.readouterr().out


def test_validar_no_inventa_sobre_una_fuente_SIN_extraccion(toy_vault, capsys):
    """Sin extracción de esa fuente el chequeo **no es evaluable**, y decir «la inventaste» sería el
    veredicto fabricado que D-43 prohíbe."""
    _extraccion("ica_ruido", "2013Voss")
    nota = cfg.CONCEPTS / "methods" / "ica-ruido.md"
    nota.parent.mkdir(parents=True, exist_ok=True)
    nota.write_text("---\ntags: [concept]\n---\n\n# ICA ruidosa\n\n"
                    "Dice «una cita larga de una fuente que no tiene extracción en disco» "
                    "[[2099Nadie]].\n",
                    encoding="utf-8")
    assert ct.main(["--validar", str(nota)]) == 0
    assert "sin `.txt` ni extracción en disco" in capsys.readouterr().out


def test_sin_extracciones_rehusa_en_vez_de_imprimir_cero(toy_vault, capsys):
    """D-43: un `0 valores` sobre un directorio que no existe se lee como «no hay nada que
    contrastar», que es lo contrario de «el fan-out todavía no corrió»."""
    assert ct.main(["ica_ruido"]) == 2
    assert "no hay extracciones" in capsys.readouterr().out


def test_un_json_ROTO_se_declara(toy_vault, capsys):
    """El artefacto más caro de la cadena no se saltea en silencio."""
    (cfg.EXTRACCION / "ica_ruido").mkdir(parents=True, exist_ok=True)
    (cfg.EXTRACCION / "ica_ruido" / "roto.json").write_text("{no json", encoding="utf-8")
    ct.main(["ica_ruido"])
    assert "no parsea" in capsys.readouterr().out


def test_la_atribucion_viaja_pegada_a_la_cita(toy_vault, capsys):
    """#322 — la clase medida más frecuente (6 de 12): la frase de un paper puesta bajo otro
    bibcode. Con la cita y el `[[bibcode]]` saliendo juntos del mismo JSON, elegir mal deja de ser
    posible: no hay elección."""
    _extraccion("ica_ruido", "2013Voss", ground_truth=[
        {"que": "blanqueo", "valor": "lo que dice Voss 2013", "linea": "p. 4"}])
    _extraccion("ica_ruido", "2015Voss", ground_truth=[
        {"que": "blanqueo", "valor": "lo que dice el OTRO Voss", "linea": "p. 7"}])
    ct.main(["ica_ruido", "--filas"])
    filas = [l for l in capsys.readouterr().out.splitlines() if l.startswith("| ")]
    por_bib = {l.split("[[")[1].split("]]")[0]: l for l in filas}
    assert "lo que dice Voss 2013 (p. 4)" in por_bib["2013Voss"]
    assert "lo que dice el OTRO Voss (p. 7)" in por_bib["2015Voss"]


def test_la_celda_de_la_fila_escapa_la_barra(toy_vault, capsys):
    """#240 — un `|` crudo en la cita PARTE la fila, y la afirmación queda invisible para el lector
    mientras el lint la sigue contando. Lo hace la máquina, que es el punto de #322."""
    _extraccion("ica_ruido", "2013Voss", ground_truth=[
        {"que": "norma", "valor": "el operador |x| de la ecuación", "linea": "p. 2"}])
    ct.main(["ica_ruido", "--filas"])
    fila = next(l for l in capsys.readouterr().out.splitlines() if l.startswith("| "))
    assert r"\|x\|" in fila, "el `|` de la cita sale escapado"
    # Cuatro celdas: el `|` escapado no cuenta como separador, así que GFM no parte la fila.
    assert fila.replace(r"\|", "").count("|") == 5


def _nota_323(nombre: str, cuerpo: str):
    f = cfg.CONCEPTS / "methods" / f"{nombre}.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"---\ntags: [concept]\n---\n\n# {nombre}\n\n{cuerpo}\n", encoding="utf-8")
    return f


def test_el_barrido_declara_su_POBLACION(toy_vault, capsys):
    """INV-40 — un `0` sin denominador no distingue «miré todo» de «no miré nada», y acá el segundo
    caso pasa de verdad: sin `--migrate-extracciones` la población es cero."""
    _extraccion("ica_ruido", "2013Voss")
    _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    assert ct.main(["--validar-todo"]) == 0
    out = capsys.readouterr().out
    assert "nota(s) de toda la bóveda" in out and "1 cita(s)" in out
    assert "0 cita(s) con evidencia POSITIVA de alteración ✅" in out


def test_el_barrido_sin_UNA_cita_mirada_sale_NO_EVALUADO(toy_vault, capsys):
    """D-43 — la bóveda anterior a #311 no tiene extracciones, así que el barrido no puede mirar
    nada. Un cero silencioso ahí se lee como veredicto: es el falso limpio que el framework
    persigue."""
    _nota_323("sin-citas", "Prosa sin ninguna cita textual.")
    assert ct.main(["--validar-todo"]) == 0
    out = capsys.readouterr().out
    assert "NO EVALUADO" in out and "--migrate-extracciones" in out


def test_el_barrido_es_un_GATE(toy_vault, capsys):
    """exit ≠ 0 con hallazgos bloqueantes, para que sirva en CI y en el cierre de la operación."""
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "2004Davies", ground_truth=[
        {"que": "otro", "valor": "algo distinto", "linea": "p. 9"}])
    _txt("ica_ruido", "2004Davies")
    _nota_323("ica-ruido", f"Dice «{LARGA}» [[2004Davies]], y lo discute [[2013Voss]].")
    assert ct.main(["--validar-todo"]) == 1
    assert "atribuida a la fuente equivocada" in capsys.readouterr().out


def test_el_barrido_por_SUJETO_acota_la_poblacion(toy_vault, capsys):
    """#121 — con el slug el alcance son las notas del sujeto (la entidad y los papers con extracción
    ahí). Sin slug, toda la bóveda."""
    _extraccion("ica_ruido", "2013Voss")
    _nota_323("ica_ruido", f"Dice «{LARGA}» [[2013Voss]].")
    _nota_323("otro-tema", "Prosa de otro tema.")
    ct.main(["ica_ruido", "--validar-todo"])
    acotado = capsys.readouterr().out
    ct.main(["--validar-todo"])
    entero = capsys.readouterr().out
    assert "notas de `ica_ruido`" in acotado
    assert int(acotado.split("> sobre ")[1].split(" ")[0]) < int(entero.split("> sobre ")[1].split(" ")[0])


def test_la_cita_que_SU_txt_dice_no_es_atribucion_equivocada(toy_vault, capsys):
    """#324 — el falso positivo medido, y el que más iba a doler: `--validar-todo` es paso de cierre
    con exit ≠ 0 desde #323, así que un falso positivo **frena operaciones**.

    Boilerplate de A&A («only available in electronic form at the CDS») que está verbatim en el
    `.txt` del paper que la nota cita, que la extracción **selectiva** (#188) de ese paper no
    transcribió, y que la extracción de otro paper del corpus sí. El lint no lo marcaba porque prueba
    contra el `.txt` de su fuente **primero**; `contrast` iba derecho a comparar extracciones."""
    BOILER = "only available in electronic form at the CDS via anonymous ftp"
    _extraccion("ica_ruido", "2016Diaz", ground_truth=[
        {"que": "otra cosa", "valor": "lo que este paper sí aporta", "linea": "p. 3"}])
    _extraccion("ica_ruido", "2009Nunez", ground_truth=[
        {"que": "tablas", "valor": BOILER, "linea": "p. 1"}])
    _txt("ica_ruido", "2016Diaz", f"prosa del paper. {BOILER}. más prosa.")
    _txt("ica_ruido", "2009Nunez")
    nota = _nota_323("ica-ruido", f"Las tablas están «{BOILER}» [[2016Diaz]].\n\n"
                                  f"El blanqueo lo trata [[2009Nunez]].")
    assert ct.main(["--validar", str(nota)]) == 0
    assert "atribuida a la fuente equivocada" not in capsys.readouterr().out
    # Y no sale por ninguna otra puerta: la cita está en el `.txt` de SU fuente, así que no hay NADA
    # que decir — ni «se movió» ni «el `.txt` la parte». Es el paso 1 del orden, y es el que muere si
    # alguien lo saltea.
    import lint as lt
    lt.main([])
    assert BOILER[:40] not in capsys.readouterr().out


def test_PARIDAD_con_el_lint_sobre_el_mismo_insumo(toy_vault, capsys):
    """Regla de método nº 2 y #222 — las dos implementaciones de la misma regla ya divergían (13 vs
    12 sobre el mismo corpus el mismo día). Lo que se compara son **las dos salidas sobre el mismo
    insumo**, no las dos constantes: que el número estuviera duplicado es justo lo que no se
    detectaba, y comparar constantes no habría cazado la divergencia de orden que produjo el falso
    positivo."""
    import lint as lt
    assert lt.CITA_PREFIJO is cfg.CITA_PREFIJO
    BOILER = "only available in electronic form at the CDS via anonymous ftp"
    _extraccion("ica_ruido", "2016Diaz", ground_truth=[
        {"que": "otra", "valor": "otra cosa", "linea": "p. 3"}])
    _extraccion("ica_ruido", "2009Nunez", ground_truth=[
        {"que": "tablas", "valor": BOILER, "linea": "p. 1"}])
    _txt("ica_ruido", "2016Diaz", f"prosa del paper. {BOILER}. más prosa.")
    _txt("ica_ruido", "2009Nunez")
    nota = _nota_323("ica-ruido",
                     f"Las tablas están «{BOILER}» [[2016Diaz]].\n\n"
                     f"Y además dice «{LARGA}» [[2009Nunez]].")
    lt.main([])
    reporte = capsys.readouterr().out
    de_contrast = ct.validar(nota, mostrar=False)["alteradas"]
    # ninguno de los dos marca el boilerplate: está en el `.txt` de SU fuente (#324)
    assert BOILER[:40] not in reporte
    assert not [m for _ln, m in de_contrast if BOILER[:40] in m]
    # y ninguno de los dos lo llama alterado: la extracción calla, y el silencio no es evidencia
    assert "atribuida a la fuente equivocada" not in reporte
    assert not de_contrast


# ── #386/#387 · el `log` es append-only, así que su corrección es una MARCA y no una edición ──

def _log(cuerpo: str):
    """El `log.md` de la bóveda: append-only por contrato, y por eso corregible sólo por marca."""
    cfg.LOG.parent.mkdir(parents=True, exist_ok=True)
    cfg.LOG.write_text(f"# Log\n\n{cuerpo}\n", encoding="utf-8")
    return cfg.LOG


def test_una_entrada_del_log_MARCADA_no_mueve_el_rc(toy_vault, capsys):
    """#386 — #238 manda MARCAR la entrada refutada (`⚠ corregido …`), no editarla, y `contrast`
    no conocía la marca: una entrada corregida exactamente como el framework manda seguía
    bloqueando el gate obligatorio de #323 **para siempre**, y la única salida era editar el `log`
    — justo lo que #238 prohíbe. No había salida dentro de las reglas."""
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "2004Davies", ground_truth=[
        {"que": "otro", "valor": "algo completamente distinto", "linea": "p. 9"}])
    _txt("ica_ruido", "2004Davies")
    _log(f"## 2026-08-31 — nota vieja\n\n"
         f"- Dice «{LARGA}» [[2004Davies]], y lo discute [[2013Voss]].\n"
         f"  ⚠ corregido 2026-09-01 → entrada «corrección» del 2026-09-01: la atribución va al "
         f"otro bibcode.")
    assert ct.main(["--validar-todo"]) == 0
    out = capsys.readouterr().out
    assert "declarada(s) y resuelta(s)" in out, out


def test_la_entrada_del_log_que_CITA_una_cita_defectuosa_es_MENCION(toy_vault, capsys):
    """#387 — el caso REFLEXIVO, que no tenía salida dentro de la regla: una entrada que documenta
    una cita mal formada **tiene que citarla para explicarla**, y en cuanto la cita *es* una cita
    mal formada a los ojos del chequeo. Medido en una bóveda real: la entrada que corrige el
    defecto se reportaba a sí misma. Dentro de un blockquote del `log` la cita es una MENCIÓN, no
    una afirmación de la bóveda — misma doctrina que `SECCIONES_ESTAMPADAS`."""
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "2004Davies", ground_truth=[
        {"que": "otro", "valor": "algo completamente distinto", "linea": "p. 9"}])
    _txt("ica_ruido", "2004Davies")
    _log("## 2026-09-01 — corrección de una cita del propio log (#238)\n\n"
         "La entrada vieja publicaba el bibcode del lado equivocado:\n\n"
         f"> Dice «{LARGA}» [[2004Davies]], y lo discute [[2013Voss]].")
    assert ct.main(["--validar-todo"]) == 0, capsys.readouterr().out


def test_la_marca_del_log_NO_exime_a_una_nota_normal(toy_vault, capsys):
    """El recorte que hace que la exención no sea un agujero: `⚠ corregido` es la quinta marca en
    línea y vive **sólo en `log.md`** (es la salida de un artefacto append-only). Escribirla en una
    ficha o un concepto no apaga nada — ahí la corrección se hace editando la nota."""
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "2004Davies", ground_truth=[
        {"que": "otro", "valor": "algo completamente distinto", "linea": "p. 9"}])
    _txt("ica_ruido", "2004Davies")
    _nota_323("ica-ruido", f"⚠ corregido 2026-09-01 → otra cosa. "
                           f"Dice «{LARGA}» [[2004Davies]], y lo discute [[2013Voss]].")
    assert ct.main(["--validar-todo"]) == 1


def test_PARIDAD_lint_contrast_sobre_la_marca_del_log(toy_vault, capsys):
    """#387 nombra el problema de fondo: una convención en PROSA **no compone** — cada chequeo la
    tiene que aprender por separado, hoy son dos y ya divergían. La regla vive en UNA función
    (`cfg.log_quote_exempt`) y los dos consumidores la llaman; lo que se compara son las dos
    salidas sobre el mismo insumo, no las dos constantes."""
    import lint as lt
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "2004Davies", ground_truth=[
        {"que": "otro", "valor": "algo completamente distinto", "linea": "p. 9"}])
    _txt("ica_ruido", "2004Davies")
    _log(f"## 2026-08-31 — vieja\n\n"
         f"- Dice «{LARGA}» [[2004Davies]], y lo discute [[2013Voss]].\n"
         f"  ⚠ corregido 2026-09-01 → entrada «corrección» del 2026-09-01.")
    lt.main([])
    reporte = capsys.readouterr().out
    assert LARGA[:40] not in reporte, "el lint tampoco la reporta"
    assert ct.validar(cfg.LOG, mostrar=False)["alteradas"] == []


def test_el_barrido_GLOBAL_registra_cuando_se_corrio(toy_vault, capsys):
    """#386 — el gate más fuerte del framework se corría «cuando alguien se acordaba»: `maintain`
    declara la pasada periódica de RED y ninguna de citas, y el paso 6a del skill lo corre **con el
    slug**, que devuelve 0 mientras el global devuelve 1. Medido: cuatro sujetos cerrados con
    `lint --cierre` en 0 y el gate global **nunca en verde**, sin que nada lo dijera.

    Se registra igual que la caducidad (D-46): *cuándo se miró* es información de la bóveda, no de
    la máquina, así que viaja versionada."""
    _extraccion("ica_ruido", "2013Voss")
    _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    assert ct.main(["--validar-todo"]) == 0
    reg = cfg.REGISTRO / "_citas.yaml"
    assert reg.exists(), "la pasada global no dejó registro"
    import yaml
    pasada = yaml.safe_load(reg.read_text(encoding="utf-8"))["ultima_pasada_citas"]
    assert pasada["fecha"] and pasada["version"]
    assert pasada["poblacion"]["notas"] == 1 and pasada["poblacion"]["citas"] == 1
    assert pasada["alteradas"] == 0


def test_el_barrido_ACOTADO_no_registra_la_pasada(toy_vault, capsys):
    """El recorte que evita la afirmación falsa: con slug el barrido mira **las notas del sujeto**,
    así que registrar eso como «la pasada» diría que se miró la bóveda cuando se miró un rincón. Es
    la misma distinción que `sweep_external --bibcodes`, que tampoco registra la pasada."""
    _extraccion("ica_ruido", "2013Voss")
    _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    assert ct.main(["ica_ruido", "--validar-todo"]) == 0
    assert not (cfg.REGISTRO / "_citas.yaml").exists()


# ── #329 · la curación declarada se aplica al carril de LECTURA, y sólo a ése ──

def _dropear(slug: str, bib: str, motivo: str = "polisemia: no es el ICA/BSS del tema"):
    """El `--drop-core` como lo escribe `triage.py`: registro VERSIONADO, carril `sujeto` (#112).

    Se escribe el archivo de verdad —no un `monkeypatch` de `load_decisiones`— porque lo que este
    test prueba es que `contrast` cruza la **implementación canónica** (`dropped_from_subject`), que
    es donde vive el `origen: sujeto` y el `decision: descartado`."""
    reg = cfg.load_registro(slug) or {"slug": slug}
    reg.setdefault("decisiones", {})[bib] = {
        "decision": "descartado", "origen": "sujeto", "motivo": motivo, "fecha": "2026-08-31"}
    cfg.save_registro(slug, reg)


def test_el_paper_DROPEADO_no_entra_al_material_del_3b(toy_vault, capsys):
    """#329 — medido en una bóveda real: 13 de 51 extracciones (25 %) del tema `ica` eran de papers
    que el usuario ya había sacado con `--drop-core`, y los trece eran falsos positivos de polisemia
    **declarados**. 3b es el paso que PRODUCE los ejes: servirle ese material es darle exactamente
    lo que fabrica un eje falso (#112 — la decisión de curación que el lector ignora en silencio es
    peor que no tomarla)."""
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "1982MNRAS", ground_truth=[
        {"que": "componentes independientes", "valor": "las componentes del tensor de tensiones",
         "linea": "p. 3"}])
    _dropear("ica_ruido", "1982MNRAS")
    for extra in ([], ["--filas"], ["--eje"], ["--campo", "valor"]):
        assert ct.main(["ica_ruido"] + extra) == 0
        out = capsys.readouterr().out
        assert "2013Voss" in out, f"el paper vivo sigue saliendo ({extra})"
        assert "1982MNRAS" not in out, f"el dropeado no entra al 3b ({extra})"
        assert "tensor de tensiones" not in out


def test_la_poblacion_DECLARA_cuantas_excluyo_la_curacion(toy_vault, capsys):
    """INV-40/D-43 — se marca, no se borra en silencio. La extracción se pagó (#311) y sigue en
    disco: un listado que no dice cuántas dejó afuera no distingue «no había ninguna dropeada» de
    «nadie miró la curación»."""
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "1982MNRAS")
    _dropear("ica_ruido", "1982MNRAS")
    ct.main(["ica_ruido"])
    out = capsys.readouterr().out
    assert "> sobre 2 extracción(es) del sujeto · 1 excluida(s) por `--drop-core`" in out
    assert "--incluir-dropeados" in out, "la escotilla se nombra donde se aplica el filtro"


def test_la_poblacion_declara_TAMBIEN_el_cero(toy_vault, capsys):
    """El `(0)` que nadie declara se lee como veredicto (D-43): sin la línea, «no hay dropeados» y
    «este comando no mira la curación» —el bug de #329— salen idénticos por pantalla."""
    _extraccion("ica_ruido", "2013Voss")
    ct.main(["ica_ruido"])
    assert "> sobre 1 extracción(es) del sujeto · 0 excluida(s) por `--drop-core`" \
        in capsys.readouterr().out


def test_incluir_dropeados_las_muestra_MARCADAS(toy_vault, capsys):
    """La escotilla existe porque a veces se quiere mirar el descarte; lo que no puede pasar es que
    salga mezclado con el material bueno. Cada fuente dropeada sale detrás de su propio banner."""
    _extraccion("ica_ruido", "1982MNRAS")
    _dropear("ica_ruido", "1982MNRAS")
    assert ct.main(["ica_ruido", "--incluir-dropeados"]) == 0
    out = capsys.readouterr().out
    assert "1982MNRAS" in out and "DESCARTADO del sujeto con `--drop-core`" in out
    assert "polisemia: no es el ICA/BSS del tema" in out, "el MOTIVO viaja, no la categoría"
    assert "1 DROPEADA(s) mostrada(s) por `--incluir-dropeados`" in out


def test_el_carril_de_VALIDACION_sigue_viendo_al_dropeado(toy_vault, capsys):
    """⛔ El límite del arreglo (#317/#321/#323): un paper dropeado sigue siendo un testigo válido de
    a quién pertenece una frase. Filtrarlo acá bajaría la población del detector y convertiría una
    atribución correcta en un falso «mal atribuido» — la clase de falso positivo que #324/#325
    acaban de sacar de un paso de cierre que bloquea."""
    # el TESTIGO es el paper dropeado: la nota atribuye la frase a `2013Voss` y quien la tiene
    # verbatim es la extracción de `1982MNRAS`, que el usuario sacó del sujeto.
    _extraccion("ica_ruido", "2013Voss", ground_truth=[
        {"que": "otro", "valor": "algo completamente distinto", "linea": "p. 9"}])
    _extraccion("ica_ruido", "1982MNRAS")
    _txt("ica_ruido", "2013Voss")
    _dropear("ica_ruido", "1982MNRAS")
    nota = _nota_323("ica_ruido", f"Dice «{LARGA}» [[2013Voss]], y lo discute [[1982MNRAS]].")
    assert ct.main(["--validar", str(nota)]) == 1
    out = capsys.readouterr().out
    assert "atribuida a la fuente equivocada" in out
    assert "1982MNRAS" in out, "el dropeado sigue siendo TESTIGO de a quién pertenece la frase"
    # y el barrido —que desde #323 es paso de cierre con exit ≠ 0— bloquea igual, entero y acotado
    # al sujeto: filtrar acá bajaría su población y el hallazgo real desaparecería.
    assert ct.main(["--validar-todo"]) == 1
    assert "atribuida a la fuente equivocada" in capsys.readouterr().out
    assert ct.main(["ica_ruido", "--validar-todo"]) == 1
    assert "notas de `ica_ruido`" in capsys.readouterr().out


# ── #330 · las tres formas de `valor`, y por qué el script no pone NI UNA comilla ──

CITA_A = "«As conclusion, the cost is dominated by the whitening step of the algorithm»"
GLOSA_B = "0.11 ± 0.11 (promedio de las dos líneas; el paper las llama «the two Zn lines»)"
PELADO_C = "< -0.09 (límite superior; Li no detectado)"


def _celda(slug: str, bib: str, valor: str, capsys) -> tuple[str, str]:
    """La celda del valor de la ÚNICA fila de `--filas`, más la salida entera."""
    _extraccion(slug, bib, ground_truth=[{"que": "eje", "valor": valor, "linea": "p. 4"}])
    ct.main([slug, "--filas", "--paper", bib])
    out = capsys.readouterr().out
    fila = next(l for l in out.splitlines() if l.startswith("| "))
    return fila.split("|")[3].strip(), out


def test_A_el_valor_que_YA_es_cita_no_se_DOBLA(toy_vault, capsys):
    """#330 — 686 de 1948 valores reales ya abren con `«`: envolverlos otra vez producía `««…»»`.
    No es cosmético: `«([^»]+)»` captura entonces `«As conclusion…` —con un guillemet colgado que no
    existe en ninguna fuente—, y la cita se cae de la población efectiva del gate de #323."""
    celda, _ = _celda("ica_ruido", "1994Comon", CITA_A, capsys)
    assert "««" not in celda and "»»" not in celda
    assert celda.startswith(CITA_A), "la cita del extractor, entera y sin una comilla de más"


def test_B_la_GLOSA_del_extractor_no_se_publica_como_palabras_del_paper(toy_vault, capsys):
    """La clase más grave (315 de 1948): el `valor` es la glosa del extractor **con** la cita
    adentro. Envolviéndola entera, la prosa en castellano de un LLM se publicaba como las palabras
    de un paper en inglés — exactamente el mecanismo que #322 existe para impedir."""
    celda, _ = _celda("ica_ruido", "2004Ecuvillon", GLOSA_B, capsys)
    assert not celda.startswith("«"), "la glosa NO se entrecomilla"
    assert "«the two Zn lines»" in celda, "y la cita de adentro se preserva tal cual"


def test_C_el_valor_PELADO_no_se_presenta_como_cita(toy_vault, capsys):
    """947 de 1948: un dato de tabla, sin una comilla en el JSON. El script no puede saber si es
    verbatim —eso lo sabe el extractor—, así que no lo afirma: la celda sale sin comillas, que es lo
    que el propio banner manda para lo que no es cita."""
    celda, _ = _celda("ica_ruido", "2004Israelian", PELADO_C, capsys)
    assert "«" not in celda and "»" not in celda
    assert celda.startswith(PELADO_C)


def test_el_BANNER_nombra_las_tres_formas_y_declara_lo_que_emitio(toy_vault, capsys):
    """El banner afirmaba *«la cadena entre «» ya es correcta por construcción»*, que era falso para
    el 65 % de los valores — y le ordenaba al sintetizador pegarla sin tocarla. Ahora dice cuál es
    cuál, cuántas de cada una emitió esta corrida, y que lo que sale sin comillas **no se
    entrecomilla al pegarlo**."""
    _extraccion("ica_ruido", "1994Comon", ground_truth=[
        {"que": "a", "valor": CITA_A, "linea": "p. 1"}])
    _extraccion("ica_ruido", "2004Ecuvillon", ground_truth=[
        {"que": "b", "valor": GLOSA_B, "linea": "p. 2"}])
    _extraccion("ica_ruido", "2004Israelian", ground_truth=[
        {"que": "c", "valor": PELADO_C, "linea": "p. 3"}])
    ct.main(["ica_ruido", "--filas"])
    out = capsys.readouterr().out
    assert "las comillas son las del EXTRACTOR".lower() in out.lower()
    assert "1 que abren" in out and "1 con «» adentro" in out and "1 sin «»" in out
    assert ct.FORMAS["pelado"] in out, "y dice qué hacer con la que no es cita"
    assert "no lo entrecomilles al pegarlo" in out


def test_la_fila_pegada_SIGUE_en_la_poblacion_del_gate_de_cierre(toy_vault, capsys):
    """La consecuencia medida punta a punta, y el molde de #275: con `««…»»` la cita pasaba de
    *verificada* a **no evaluable** y el barrido seguía diciendo `0 ✅` — población efectiva que cae
    sin que el veredicto lo diga. En una bóveda real ya hay 2850 de 2984 citas no evaluables, así
    que margen para perder más no hay.

    Se prueba contra el **paso 1** de `quote_verdict` (`en_su_txt`), que es donde se midió: la fuente
    tiene `.txt` y no tiene extracción —el caso mayoritario—, así que el único testigo es el archivo
    del paper, y ahí el guillemet de más **no existe**. Con la extracción presente el defecto queda
    tapado por el JSON que produjo la fila, que es justamente el testigo que no hay que creerle
    (#205/#324: la cadena que está en el `.txt` prueba que la frase es de ese paper)."""
    celda, _ = _celda("ica_ruido", "1994Comon", CITA_A, capsys)
    (cfg.EXTRACCION / "ica_ruido" / "1994Comon.json").unlink()
    _txt("ica_ruido", "1994Comon", "prosa del paper. As conclusion, the cost is dominated by the "
                                   "whitening step of the algorithm. más prosa.")
    nota = _nota_323("ica_ruido", f"El costo lo fija {celda} [[1994Comon]].")
    r = ct.validar(nota, mostrar=False)
    assert r["citas"] == 1, "la cita se mira"
    assert r["no_evaluables"] == [] and r["alteradas"] == [], "y se VERIFICA contra el `.txt`"

def test_la_poblacion_declara_lo_aprobado_con_UN_SOLO_TESTIGO(toy_vault, capsys):
    """#341 — el `0 ✅` se apoyaba en un solo testigo y no lo decía.

    La cita está en la extracción de su fuente y **no** en el `.txt` de esa misma fuente: es el paso
    2 de `quote_verdict` (`txt_degradado`), o sea una única lectura del PDF, la del LLM. El
    veredicto es correcto —el `.txt` es un índice degradado (#205)—, pero medido sobre la bóveda
    real son **40 de 169** las citas que el comando aprobaba así mientras imprimía `0 ✅` sobre las
    169. INV-40: la población se declara, en los dos modos."""
    _extraccion("ica_ruido", "2013Voss")
    _txt("ica_ruido", "2013Voss")                    # existe y NO dice la cita
    nota = _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    assert ct.validar(nota, mostrar=False)["solo_extraccion"] == 1
    ct.main(["--validar", str(nota)])
    assert "1 sólo respaldada(s) por la extracción" in capsys.readouterr().out
    ct.main(["--validar-todo"])
    barrido = capsys.readouterr().out
    assert "1 sólo respaldada(s) por la extracción" in barrido
    # y el barrido dice QUÉ significa el conteo: sin eso es un número sin doctrina y el lector no
    # sabe si el `✅` de arriba lo incluye ni qué hacer con él.
    assert "UN SOLO TESTIGO" in barrido


def test_la_poblacion_de_un_solo_testigo_declara_el_CERO(toy_vault, capsys):
    """D-43/INV-40 — una categoría que sólo aparece cuando hay algo no distingue «no hay ninguna» de
    «no se miró». Acá la cita está verbatim en el `.txt` de su fuente (paso 1, `en_su_txt`): hay dos
    testigos, así que el conteo es cero **y se imprime**."""
    _extraccion("ica_ruido", "2013Voss")
    _txt("ica_ruido", "2013Voss", f"prosa del paper. {LARGA}. más prosa.")
    nota = _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    ct.main(["--validar", str(nota)])
    assert "0 sólo respaldada(s) por la extracción" in capsys.readouterr().out
    ct.main(["--validar-todo"])
    barrido = capsys.readouterr().out
    assert "0 sólo respaldada(s) por la extracción" in barrido
    # el cero se declara en la población, pero la advertencia NO se emite: no hay ninguna página que
    # ir a mirar, y una advertencia sobre cero casos entrena a saltearla.
    assert "UN SOLO TESTIGO" not in barrido


def test_el_txt_que_CONTRADICE_al_unico_testigo_se_nombra(toy_vault, capsys):
    """#333 — la cita que nace alterada EN la extracción era invisible por construcción: el juez del
    comando **es** la extracción (#315/#317), y el `.txt` sólo podía absolver.

    Acá el `.txt` de la misma fuente trae el arranque de la cita y sigue distinto, en prosa: es la
    forma de evidencia positiva de #318/#321 aplicada al mismo bibcode entre sus dos artefactos, y
    el testigo que gana es el determinista. Medido: sobre una bóveda real fueron 3 de 25, las 3
    verdaderas — una de ellas, `2026A&A...705A.234O`, invirtiendo el sentido de la oración."""
    _extraccion("ica_ruido", "2013Voss")
    _txt("ica_ruido", "2013Voss", "prosa. " + LARGA[:LARGA.index("and that")]
         + "but the noise covariance has to be estimated first. más prosa.")
    nota = _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    r = ct.validar(nota, mostrar=False)
    assert len(r["discrepan"]) == 1 and r["solo_extraccion"] == 1
    assert r["alteradas"] == [], "no es un hallazgo bloqueante: el `.txt` es índice degradado"
    ct.main(["--validar-todo"])
    barrido = capsys.readouterr().out
    assert "1 de ellas con el `.txt` en contra" in barrido
    assert "el OTRO lector del mismo PDF dice otra cosa" in barrido


def test_la_divergencia_decidible_EMITE_la_marca_lista_para_pegar(toy_vault, capsys):
    """#341, parte 2 — cuando las dos lecturas del PDF no coinciden hoy **no pasaba nada**: el gate
    callaba y la ficha quedaba con la versión de una de las dos, sin decir cuál ni que hubo
    discrepancia. No hace falta mecanismo nuevo: `⚠verificar en el PDF (<qué se dudó>, <fecha>)` ya
    existe y tiene justo las propiedades que hacen falta.

    ⛔ Se **emite**, no se aplica: `contrast` propone y no escribe en `vault/`. Y el motivo lleva las
    **dos colas**, no una categoría — en seis meses sirve el motivo."""
    _extraccion("ica_ruido", "2013Voss")
    _txt("ica_ruido", "2013Voss", "prosa. " + LARGA[:LARGA.index("and that")]
         + "but the noise covariance has to be estimated first. más prosa.")
    nota = _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    _ln, _motivo, marca = ct.validar(nota, mostrar=False)["discrepan"][0]
    assert marca.startswith(cfg.VERIFICAR_PDF_MARK), "es LA marca, no una prosa parecida"
    assert "but the noise covariance" in marca and "and that condition" in marca
    assert nota.read_text(encoding="utf-8").count(cfg.VERIFICAR_PDF_MARK) == 0, "no la aplica"
    ct.main(["--validar", str(nota)])
    assert "pegá al final de la afirmación" in capsys.readouterr().out
    ct.main(["--validar-todo"])
    assert cfg.VERIFICAR_PDF_MARK in capsys.readouterr().out, "y también en el barrido"


def test_la_marca_que_emite_es_LA_QUE_EL_LINT_LEVANTA(toy_vault, capsys):
    """El cierre del circuito, y la razón por la que el string vive en `lib_config` desde 1.162.0: la
    marca que esta herramienta ofrece y la que el detector del lint busca son **la misma
    definición**. Con dos copias, `contrast` podría proponer una marca que nadie levanta — deuda
    escrita que se lee como agendada y no lo está."""
    import lint as lt
    assert lt.VERIFICAR_PDF_MARK is cfg.VERIFICAR_PDF_MARK
    _extraccion("ica_ruido", "2013Voss")
    _txt("ica_ruido", "2013Voss", "prosa. " + LARGA[:LARGA.index("and that")]
         + "but the noise covariance has to be estimated first. más prosa.")
    nota = _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    marca = ct.validar(nota, mostrar=False)["discrepan"][0][2]
    nota.write_text(nota.read_text(encoding="utf-8").rstrip() + f" {marca}\n", encoding="utf-8")
    levantadas = [m for _s, m in lt.collect().por_clave("verificar_pdf").items]
    assert any("chequear contra el PDF" in m for m in levantadas)


def test_el_txt_que_contradice_NO_mueve_el_rc(toy_vault, capsys):
    """#333, la restricción explícita del issue: **no** se vuelve una cuarta forma de romper el
    cierre. El `.txt` es un índice degradado y desde #323 este gate frena operaciones, así que un
    falso positivo suyo costaría lo que #324/#325 acaban de sacar."""
    _extraccion("ica_ruido", "2013Voss")
    _txt("ica_ruido", "2013Voss", "prosa. " + LARGA[:LARGA.index("and that")]
         + "but the noise covariance has to be estimated first. más prosa.")
    nota = _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    assert ct.main(["--validar", str(nota)]) == 0
    assert ct.main(["--validar-todo"]) == 0
    assert "0 cita(s) con evidencia POSITIVA de alteración ✅" in capsys.readouterr().out


def test_lo_aprobado_con_un_solo_testigo_NO_mueve_el_rc(toy_vault, capsys):
    """#341 — no es un hallazgo nuevo ni un bloqueante: es hacer visible sobre qué se apoya el `✅`.
    Si moviera el rc, el paso de cierre de #323 se frenaría en 40 de 169 citas correctas."""
    _extraccion("ica_ruido", "2013Voss")
    _txt("ica_ruido", "2013Voss")
    nota = _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    assert ct.main(["--validar", str(nota)]) == 0
    assert ct.main(["--validar-todo"]) == 0
    assert "0 cita(s) con evidencia POSITIVA de alteración ✅" in capsys.readouterr().out


# ── #344 · el hermano de auditoría no es una nota ────────────────────────────────────────────────

def test_el_barrido_NO_mira_los_hermanos_de_verificacion(toy_vault, capsys):
    """#344 — las celdas `Evidencia` del hermano son citas que el fan-out ya sacó de la fuente:
    barrerlas acá inventaría una población entera de «citas de la bóveda» sobre un artefacto que no
    afirma nada, y este gate **frena operaciones** (#323). El hermano no es una nota."""
    _extraccion("ica_ruido", "2013Voss")
    nota = _nota_323("ica-ruido", f"Dice «{LARGA}» [[2013Voss]].")
    cfg.verif_sidecar(nota).write_text(
        "# Rastro\n\n## Verificación de citas\n\n"
        "| # | Fuente | Evidencia |\n|---|---|---|\n"
        f"| 1 | [[2013Voss]] | «{LARGA} y una cola que la extracción no tiene» |\n",
        encoding="utf-8")
    assert nota in ct._notes_of(None)
    assert cfg.verif_sidecar(nota) not in ct._notes_of(None)
    ct.main(["--validar-todo"])
    assert "una cola que la extracción no tiene" not in capsys.readouterr().out
