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


def test_las_filas_llevan_UNA_sola_fuente(toy_vault, capsys):
    """Agrupar bibcodes bajo una glosa compartida es cómo se fabrican atribuciones (6 medidas): que
    agrupar sea una decisión explícita y no la salida natural de la herramienta."""
    _extraccion("ica_ruido", "2013Voss")
    _extraccion("ica_ruido", "2004Davies")
    ct.main(["ica_ruido", "--filas"])
    salida = capsys.readouterr().out
    filas = [l for l in salida.splitlines() if l.startswith("| ")]
    assert len(filas) == 2
    assert all(l.count("[[") == 1 for l in filas), "una fila, una fuente"
    assert "ESQUELETO" in salida and "se copia ENTERA" in salida


def test_validar_caza_la_cita_que_la_extraccion_NO_respalda(toy_vault, capsys):
    """#317 — la comparación decidible que nadie hacía: la extracción es la transcripción hecha
    **leyendo el PDF**, así que una cita del concepto que no está ahí la fabricó el sintetizador, y
    eso no admite la excusa del `.txt` degradado. Es exactamente el defecto medido."""
    _extraccion("ica_ruido", "2013Voss")
    nota = cfg.CONCEPTS / "methods" / "ica-ruido.md"
    nota.parent.mkdir(parents=True, exist_ok=True)
    nota.write_text("---\ntags: [concept]\n---\n\n# ICA ruidosa\n\n"
                    "El método «which requires the noise covariance to be known» según "
                    "[[2013Voss]].\n", encoding="utf-8")
    assert ct.main(["ica_ruido", "--validar", str(nota)]) == 1
    out = capsys.readouterr().out
    assert "NO está en la extracción" in out and "se alteró al sintetizar" in out


def test_validar_calla_cuando_la_nota_es_FIEL_a_la_extraccion(toy_vault, capsys):
    """El control, y la diferencia con #220: la cita puede no estar en el `.txt` (degradado) y estar
    en la extracción — ahí la nota está bien y no hay nada que reportar."""
    _extraccion("ica_ruido", "2013Voss")
    nota = cfg.CONCEPTS / "methods" / "ica-ruido.md"
    nota.parent.mkdir(parents=True, exist_ok=True)
    nota.write_text("---\ntags: [concept]\n---\n\n# ICA ruidosa\n\n"
                    f"Dice «{LARGA}» [[2013Voss]].\n", encoding="utf-8")
    assert ct.main(["ica_ruido", "--validar", str(nota)]) == 0
    assert "0 cita(s) que la extracción no respalda ✅" in capsys.readouterr().out


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
                    "Dice «una cita de una fuente sin extracción» [[2099Nadie]].\n",
                    encoding="utf-8")
    assert ct.main(["ica_ruido", "--validar", str(nota)]) == 0


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
