"""#197 — el aplicador de correcciones del fan-out de `verify-citations`.

Los dos modos de falla que motivan el script están **medidos** sobre una corrida real de 75
correcciones (concepto `ica`, 2026-08-27), y los dos corrompen la nota en silencio:

1. **Colisión** — un ítem de `## Huecos` que cita varias fuentes le toca a *cada* corrector de esas
   fuentes, así que llegan 2 o 3 fixes con el MISMO `viejo`. Aplicados en cadena, el segundo se
   ancla sobre el texto que dejó el primero y el ítem queda con un fragmento del anterior colgando.
2. **Bloque multilínea** — el `viejo` sale del texto **normalizado** de `lib_blocks` (líneas unidas
   con espacio) y en el archivo el bloque vive envuelto: `replace` da 0 ocurrencias. 14 de 75.
"""
import json

import pytest

import apply_fixes as af


def _note(tmp_path, body):
    p = tmp_path / "nota.md"
    p.write_text(body, encoding="utf-8")
    return p


def _fixes(tmp_path, *items):
    d = tmp_path / "fix"
    d.mkdir(exist_ok=True)
    for i, (bib, fixes) in enumerate(items):
        (d / f"{i}_{bib}.json").write_text(
            json.dumps({"bibcode": bib, "fixes": fixes}, ensure_ascii=False), encoding="utf-8")
    return d


def test_fila_de_tabla_se_reemplaza_exacta(tmp_path):
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\n| a | b |\n|---|---|\n| viejo | x |\n")
    fix = _fixes(tmp_path, ("A", [{"n": 1, "viejo": "| viejo | x |", "nuevo": "| nuevo | x |"}]))
    r = af.apply(nota, fix, write=True)
    assert r.applied == 1 and not r.failed
    assert "| nuevo | x |" in nota.read_text(encoding="utf-8")


def test_bloque_multilinea_se_localiza_por_su_forma_normalizada(tmp_path):
    """El `viejo` es una línea; en el archivo el bloque son tres. `replace` da 0 (14 de 75 medidos)."""
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\n- **Hueco.** Una frase larga\n  que sigue en otra línea\n  y termina acá.\n")
    viejo = "- **Hueco.** Una frase larga que sigue en otra línea y termina acá."
    fix = _fixes(tmp_path, ("A", [{"n": 1, "viejo": viejo, "nuevo": "- **Hueco.** Corregido, con su cita."}]))
    r = af.apply(nota, fix, write=True)
    assert r.applied == 1 and not r.failed
    assert "Corregido, con su cita." in nota.read_text(encoding="utf-8")
    assert "que sigue en otra línea" not in nota.read_text(encoding="utf-8")


def test_dos_fixes_sobre_el_mismo_bloque_NO_se_aplican(tmp_path):
    """La colisión medida: sin esta guarda el segundo pisa al primero y deja el ítem corrupto."""
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\n- **Sigma.** Lo dicen [[A]] y [[B]].\n")
    viejo = "- **Sigma.** Lo dicen [[A]] y [[B]]."
    fix = _fixes(tmp_path,
                 ("A", [{"n": 1, "viejo": viejo, "nuevo": "- **Sigma.** Versión de A."}]),
                 ("B", [{"n": 2, "viejo": viejo, "nuevo": "- **Sigma.** Versión de B."}]))
    r = af.apply(nota, fix, write=True)
    assert r.collisions, "la colisión tiene que reportarse"
    assert r.applied == 0
    assert nota.read_text(encoding="utf-8") == "# T\n\n- **Sigma.** Lo dicen [[A]] y [[B]].\n", \
        "no se escribe NADA mientras haya una colisión sin fusionar"
    # ⚠ Sin esta aserción el test pasa aunque se saque la guarda (visto): sin ella el primer fix
    # aplica, el segundo ya no encuentra su `viejo` y cae en `failed`, que también aborta la
    # escritura. Lo que distingue a la guarda es que la colisión se detecta ANTES de tocar nada,
    # así que no puede haber ningún fallo — el aplicador ni lo intentó.
    assert not r.failed, "la colisión se detecta antes de intentar aplicar, no como efecto de fallar"


def test_la_fusion_explicita_gana_y_saltea_los_originales(tmp_path):
    """Fusionar dos correcciones es juicio, no mecánica: se declara aparte y el script la respeta."""
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\n- **Sigma.** Lo dicen [[A]] y [[B]].\n")
    viejo = "- **Sigma.** Lo dicen [[A]] y [[B]]."
    fix = _fixes(tmp_path,
                 ("A", [{"n": 1, "viejo": viejo, "nuevo": "- **Sigma.** Versión de A."}]),
                 ("B", [{"n": 2, "viejo": viejo, "nuevo": "- **Sigma.** Versión de B."}]),
                 (af.MERGED, [{"n": 9, "viejo": viejo, "nuevo": "- **Sigma.** A y B fusionados."}]))
    r = af.apply(nota, fix, write=True)
    assert not r.collisions and r.applied == 1
    assert "A y B fusionados." in nota.read_text(encoding="utf-8")


def test_un_viejo_que_no_aparece_no_escribe_nada(tmp_path):
    """Un reemplazo que adivina es peor que uno que falla."""
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\ntexto vigente\n")
    fix = _fixes(tmp_path, ("A", [{"n": 1, "viejo": "texto que no está", "nuevo": "x"}]))
    r = af.apply(nota, fix, write=True)
    assert r.failed and r.applied == 0
    assert nota.read_text(encoding="utf-8") == "# T\n\ntexto vigente\n"


def test_si_UN_fix_falla_no_se_escribe_NINGUNO(tmp_path):
    """Todo o nada. Es la mitad que faltaba: con un solo fix fallando no hay nada que perder, así
    que ese caso no distingue si la escritura se aborta o no (mutación sobreviviente, vista). Acá
    uno aplica y otro falla: si el aborto no existe, la nota queda a medio corregir."""
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\n| bueno |\n\notro texto\n")
    fix = _fixes(tmp_path, ("A", [{"n": 1, "viejo": "| bueno |", "nuevo": "| corregido |"},
                                  {"n": 2, "viejo": "texto que no está", "nuevo": "x"}]))
    r = af.apply(nota, fix, write=True)
    assert r.failed and r.applied == 0
    assert "| bueno |" in nota.read_text(encoding="utf-8"), \
        "la nota quedó a medio corregir: el fix que sí aplicaba se escribió igual"


def test_un_viejo_ambiguo_no_se_aplica(tmp_path):
    """Dos ocurrencias: elegir una es adivinar."""
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\nrepetido\n\nrepetido\n")
    fix = _fixes(tmp_path, ("A", [{"n": 1, "viejo": "repetido", "nuevo": "x"}]))
    r = af.apply(nota, fix, write=True)
    assert r.failed and r.applied == 0


def test_dry_run_no_toca_el_archivo(tmp_path):
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\n| viejo |\n")
    fix = _fixes(tmp_path, ("A", [{"n": 1, "viejo": "| viejo |", "nuevo": "| nuevo |"}]))
    r = af.apply(nota, fix, write=False)
    assert r.applied == 1
    assert "viejo" in nota.read_text(encoding="utf-8")


def test_el_item_reescrito_conserva_su_sangria(tmp_path):
    """Un ítem re-envuelto sigue siendo ese ítem: sin la sangría, la lista se rompe."""
    #  @inv INV-137
    largo = "corregido " * 40
    nota = _note(tmp_path, "# T\n\n- **X.** una\n  dos\n")
    fix = _fixes(tmp_path, ("A", [{"n": 1, "viejo": "- **X.** una dos", "nuevo": f"- **X.** {largo}"}]))
    af.apply(nota, fix, write=True)
    lineas = [l for l in nota.read_text(encoding="utf-8").split("\n") if l.strip()][1:]
    assert lineas[0].startswith("- **X.**")
    assert all(l.startswith("  ") for l in lineas[1:]), "las continuaciones van sangradas"


def test_los_rechazados_del_corrector_se_reportan(tmp_path):
    """Un corrector que abrió la fuente y encontró el reporte equivocado NO corrige: lo declara."""
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\ntexto\n")
    d = tmp_path / "fix"; d.mkdir()
    (d / "A.json").write_text(json.dumps(
        {"bibcode": "A", "fixes": [], "rechazados": [{"n": 3, "motivo": "el paper no dice eso"}]}),
        encoding="utf-8")
    r = af.apply(nota, d, write=True)
    assert r.rejected == [("A", 3, "el paper no dice eso")]


def test_cli_dry_run_por_default_y_write_explicito(tmp_path, capsys, monkeypatch):
    """El CLI: sin `--write` no toca el archivo. El default deliberado es el que no escribe."""
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\n| viejo |\n")
    fix = _fixes(tmp_path, ("A", [{"n": 1, "viejo": "| viejo |", "nuevo": "| nuevo |"}]))
    assert af.main([str(nota), str(fix)]) == 0
    assert "| viejo |" in nota.read_text(encoding="utf-8")
    assert "dry-run" in capsys.readouterr().out

    assert af.main([str(nota), str(fix), "--write"]) == 0
    assert "| nuevo |" in nota.read_text(encoding="utf-8")


def test_cli_devuelve_1_y_nombra_la_colision(tmp_path, capsys):
    """El rc no puede ser 0 con una colisión sin fusionar: es lo que frena la operación."""
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\n- **S.** [[A]] y [[B]].\n")
    viejo = "- **S.** [[A]] y [[B]]."
    fix = _fixes(tmp_path, ("A", [{"n": 1, "viejo": viejo, "nuevo": "- **S.** de A."}]),
                 ("B", [{"n": 2, "viejo": viejo, "nuevo": "- **S.** de B."}]))
    assert af.main([str(nota), str(fix), "--write"]) == 1
    assert af.MERGED in capsys.readouterr().out
    assert nota.read_text(encoding="utf-8") == "# T\n\n- **S.** [[A]] y [[B]].\n"


def test_cli_devuelve_1_cuando_un_viejo_no_resuelve(tmp_path, capsys):
    #  @inv INV-137
    nota = _note(tmp_path, "# T\n\ntexto\n")
    fix = _fixes(tmp_path, ("A", [{"n": 1, "viejo": "no está", "nuevo": "x"}]))
    assert af.main([str(nota), str(fix), "--write"]) == 1
    assert "NO se escribió nada" in capsys.readouterr().out
