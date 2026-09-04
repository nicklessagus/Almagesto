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


# ── AUD-141: los dos bloques que el aplicador rompía o no encontraba ─────────

def test_una_fila_de_tabla_no_se_envuelve(tmp_path):
    """AUD-141 — envolver una fila a 100 columnas la parte en varias líneas y la tabla deja de ser
    una tabla.

    Importa especialmente en `## Verificación de citas`, cuyas filas llevan **las anclas**: el paso
    que existe para mantener honesta esa tabla la habría destruido. Una fila aplica como UNA línea,
    por larga que sea."""
    fila = ("| 3 | Una afirmación vieja | [[2020A]] | soportada | «cita» | abc1234567 | "
            "pdf:def4567890 | bajo SNR alto |")
    nota = _note(tmp_path, f"# t\n\n| # | Afirmación |\n|---|---|\n{fila}\n")
    nueva = fila.replace("Una afirmación vieja", "Una afirmación corregida y bastante más larga "
                                                 "que la anterior, para pasar de 100 columnas")
    # el `viejo` llega NORMALIZADO (así lo entrega `lib_blocks`), no idéntico byte a byte
    d = _fixes(tmp_path, ("2020A", [{"n": 3, "viejo": " ".join(fila.split()) + "  ", "nuevo": nueva}]))
    res = af.apply(nota, d, write=True)
    assert res.failed == [] and res.applied == 1
    filas = [l for l in nota.read_text(encoding="utf-8").split("\n") if l.startswith("| 3 |")]
    assert len(filas) == 1, "la fila se partió: la tabla quedó rota"
    # ⚠ #202 — hasta 1.87.0 esto miraba sólo `"corregida" in filas[0]` y `endswith("|")`, y la fila
    # PARTIDA los cumple los dos: la primera mitad arranca con `| 3 |` y termina en `|`, y la
    # continuación no arranca con `| 3 |`, así que ni siquiera entra en `filas`. El test sobrevivía
    # a mutar la guarda que dice proteger. Lo que lo distingue es exigir la fila ENTERA.
    assert filas[0] == nueva, "la fila no quedó completa en una sola línea"


def test_un_blockquote_se_localiza_y_conserva_sus_marcas(tmp_path):
    """AUD-141 — `lib_blocks` le entrega al corrector el bloque SIN los `>`, así que el `viejo` que
    devuelve tampoco los tiene y el matcher, que comparaba las líneas crudas, no lo encontraba
    nunca. Como un solo `failed` aborta la corrida entera, UNA cita en blockquote bloqueaba las
    setenta y cinco correcciones."""
    nota = _note(tmp_path, "# t\n\n> El disco interno muestra un exceso\n> en 24 micrones [[2020A]].\n")
    d = _fixes(tmp_path, ("2020A", [{"n": 1,
                                     "viejo": "El disco interno muestra un exceso en 24 micrones [[2020A]].",
                                     "nuevo": "El disco interno muestra un exceso en 70 micrones [[2020A]]."}]))
    res = af.apply(nota, d, write=True)
    assert res.failed == [] and res.applied == 1
    texto = nota.read_text(encoding="utf-8")
    assert "70 micrones" in texto
    assert all(l.startswith(">") for l in texto.split("\n")
               if l.strip() and not l.startswith("#")), "se perdieron las marcas del blockquote"


def test_la_escritura_pasa_por_el_writer_atomico(tmp_path, monkeypatch):
    """AUD-140 / INV-90 — `note.write_text` escribía en `vault/` esquivando el único writer del
    repo: sin tmp+rename un corte deja la nota a medias, y la fixture `sin_tocar_la_boveda_real`
    —que intercepta a `lib_config`— no lo veía pasar."""
    nota = _note(tmp_path, "# t\n\nviejo [[2020A]].\n")
    d = _fixes(tmp_path, ("2020A", [{"n": 1, "viejo": "viejo [[2020A]].",
                                     "nuevo": "nuevo [[2020A]]."}]))
    visto = []
    real = af.cfg.write_text_atomic
    monkeypatch.setattr(af.cfg, "write_text_atomic",
                        lambda p, t, **k: visto.append(p) or real(p, t, **k))
    af.apply(nota, d, write=True)
    assert visto == [nota], "la escritura no pasó por `lib_config.write_text_atomic`"
    assert "nuevo" in nota.read_text(encoding="utf-8")


def _nota222(tmp_path, cuerpo: str):
    n = tmp_path / "nota.md"
    n.write_text("---\ntags: [concept]\n---\n\n# nota\n\n" + cuerpo, encoding="utf-8")
    return n


def _fixes222(tmp_path, *entradas):
    d = tmp_path / "fx"
    d.mkdir(exist_ok=True)
    (d / "2020aaaa.json").write_text(json.dumps({
        "bibcode": "2020aaaa", "fixes": [{"n": i, "viejo": v, "nuevo": nu}
                                         for i, (v, nu) in enumerate(entradas, 1)]}),
        encoding="utf-8")
    return d


def test_un_viejo_que_abarca_DOS_items_se_rehusa(tmp_path):
    """#222 — `find_block` llamaba bloque a «corrida de líneas no vacías» y `lib_blocks` parte una
    lista en un bloque POR ÍTEM. Un `viejo` que abarca dos ítems resolvía igual y `rewrap` los
    reescribía como UN párrafo: medido, los pares de una nota real cayeron de 96 a 89 —siete
    afirmaciones citadas dejaron de existir como par verificable— sin que nada avisara."""
    nota = _nota222(tmp_path, "- primero, dice algo ([[2020aaaa]])\n- segundo, dice otra ([[2020aaaa]])\n")
    d = _fixes222(tmp_path, ("- primero, dice algo ([[2020aaaa]]) - segundo, dice otra ([[2020aaaa]])",
                          "- fundido en uno ([[2020aaaa]])"))
    res = af.apply(nota, d, write=True)
    assert res.applied == 0 and res.failed, res
    assert "abarca 2 bloques" in res.failed[0][2], res.failed
    assert "- segundo" in nota.read_text(encoding="utf-8"), "no se escribió nada"


def test_la_fila_exacta_y_el_bloque_no_se_pisan_en_cadena(tmp_path):
    """#222 — el paso 1 mutaba `lines` y el paso 2 corría `find_block` sobre el texto YA mutado, así
    que un bloque que contenía una línea tocada por el paso 1 dejaba de localizar y abortaba todo.
    Hoy se localiza TODO contra el texto original y el solape se declara."""
    nota = _nota222(tmp_path, "| a | b ([[2020aaaa]]) |\n\notro párrafo con cita ([[2020aaaa]])\n")
    d = _fixes222(tmp_path, ("| a | b ([[2020aaaa]]) |", "| a | B ([[2020aaaa]]) |"),
               ("otro párrafo con cita ([[2020aaaa]])", "otro párrafo corregido ([[2020aaaa]])"))
    res = af.apply(nota, d, write=True)
    assert res.applied == 2 and not res.failed, res
    txt = nota.read_text(encoding="utf-8")
    assert "| a | B ([[2020aaaa]]) |" in txt and "párrafo corregido" in txt


def test_dos_fixes_sobre_las_mismas_lineas_se_rehusan(tmp_path):
    """#222 — la colisión vista desde el otro lado: los `viejo` DIFIEREN (así que el chequeo por
    clave no la ve) y las LÍNEAS se pisan. Aplicarlos en cadena haría que el segundo anclara en lo
    que dejó el primero. Los dos resuelven: lo que se rehúsa es el solape, no una localización
    fallida — ése era el motivo equivocado por el que este test pasaba antes (#202)."""
    nota = _nota222(tmp_path, "un párrafo largo con cita ([[2020aaaa]])\ny su continuación ([[2020aaaa]])\n")
    d = _fixes222(tmp_path,
                  ("un párrafo largo con cita ([[2020aaaa]]) y su continuación ([[2020aaaa]])",
                   "todo el párrafo corregido ([[2020aaaa]])"),
                  ("y su continuación ([[2020aaaa]])", "sólo la segunda línea ([[2020aaaa]])"))
    res = af.apply(nota, d, write=True)
    assert res.applied == 0 and res.failed, res
    assert "se solapa" in res.failed[0][2], res.failed
    assert "y su continuación" in nota.read_text(encoding="utf-8")


def test_si_los_pares_bajan_no_se_escribe(tmp_path):
    """#222 — la red decisiva, y la única que habría cazado los siete pares perdidos sin contarlos a
    mano: una corrección NO puede hacer desaparecer una afirmación citada. Mismo principio que el
    ancla — lo que la nota afirma tiene que seguir siendo contable."""
    nota = _nota222(tmp_path, "un párrafo con dos citas ([[2020aaaa]], [[2021bbbb]])\n")
    d = _fixes222(tmp_path, ("un párrafo con dos citas ([[2020aaaa]], [[2021bbbb]])",
                          "un párrafo con una sola ([[2020aaaa]])"))
    res = af.apply(nota, d, write=True)
    assert res.applied == 0, res
    assert res.pairs_before == 2 and res.pairs_after == 1, res
    assert "2021bbbb" in nota.read_text(encoding="utf-8"), "no se escribió nada"


def test_dos_fixes_disjuntos_en_orden_INVERSO_no_se_solapan(tmp_path):
    """#222 — el detector de solape es `i1 < j2 and i2 < j1`, y hacen falta las DOS cláusulas: con
    los fixes en orden de archivo sólo se ejercita la segunda. Acá el primer fix del JSON está
    DESPUÉS en el archivo, así que es la primera cláusula la que impide el falso positivo."""
    nota = _nota222(tmp_path, "primer párrafo con cita ([[2020aaaa]])\n\n"
                              "segundo párrafo con cita ([[2020aaaa]])\n")
    d = _fixes222(tmp_path, ("segundo párrafo con cita ([[2020aaaa]])", "segundo ok ([[2020aaaa]])"),
                  ("primer párrafo con cita ([[2020aaaa]])", "primero ok ([[2020aaaa]])"))
    res = af.apply(nota, d, write=True)
    assert res.applied == 2 and not res.failed, res


def test_el_viejo_no_puede_cruzar_una_linea_en_blanco(tmp_path):
    """`find_block` corta en la línea vacía, y eso es lo que impide que un `viejo` mal armado una
    dos párrafos distintos en uno. Sin ese corte, el matcher los concatena y `rewrap` los funde —
    el mismo daño que #222 mide para los ítems de lista, un separador más arriba."""
    nota = _nota222(tmp_path, "primer párrafo ([[2020aaaa]])\n\nsegundo párrafo ([[2020aaaa]])\n")
    d = _fixes222(tmp_path, ("primer párrafo ([[2020aaaa]]) segundo párrafo ([[2020aaaa]])",
                             "fundido ([[2020aaaa]])"))
    res = af.apply(nota, d, write=True)
    assert res.applied == 0 and res.failed, res
    # ⚠ #202 — el motivo importa: sin el corte, el matcher SÍ resuelve (colapsa la línea vacía) y el
    # fix cae igual en `failed`, pero por la guarda de #222, no por ésta. Un test que sólo mirara
    # `failed` pasaría con el corte roto.
    assert "no se pudo localizar" in res.failed[0][2], res.failed
    assert "segundo párrafo" in nota.read_text(encoding="utf-8")


def test_el_reemplazo_exacto_es_VERBATIM_y_no_pasa_por_rewrap(tmp_path):
    """El camino exacto no está sólo por eficiencia: `rewrap` normaliza y envuelve a 100 columnas,
    así que un `nuevo` largo pasado por ahí vuelve con otro formato. Cuando el `viejo` es la línea
    tal cual está en el archivo, lo que el corrector escribió se escribe VERBATIM."""
    largo = ("una línea de prosa deliberadamente más larga que cien columnas para que envolverla "
             "cambie el archivo ([[2020aaaa]])")
    nota = _nota222(tmp_path, "corregime esta línea ([[2020aaaa]])\n")
    d = _fixes222(tmp_path, ("corregime esta línea ([[2020aaaa]])", largo))
    res = af.apply(nota, d, write=True)
    assert res.applied == 1 and res.exact == 1, res
    assert largo in nota.read_text(encoding="utf-8").split("\n"), "se envolvió: no fue verbatim"


# ── #389 · el contador SIMÉTRICO de #222 ──

def test_un_fix_que_AGREGA_una_cita_al_bloque_AVISA(tmp_path, capsys):
    """#389 — `apply` cuenta `pairs_of` antes y después y rehúsa si BAJARON (#222): una corrección
    no puede hacer desaparecer una afirmación citada. Faltaba la otra mitad, por bloque: los
    defectos que nacen AL CORREGIR llegan con material AGREGADO. Medido sobre 15 defectos de un
    concepto de 22 fuentes, 3 nacieron corrigiendo y los 3 entraron con una cita o una narración
    que el bloque no tenía —una de ellas, una atribución fabricada con cita verbatim y página
    correcta y referente equivocado—. Y el control natural: cuando en vez de arreglar se SACÓ el
    detalle, el defecto desapareció y no volvió.

    No bloquea: a veces agregar una cita ES el arreglo (una `inferencia` que pasa a hecho citado).
    Avisa, nombrando el bloque y la cita que entró."""
    nota = _note(tmp_path, "# T\n\nLa señal es estelar [[2020A]].\n")
    fix = _fixes(tmp_path, ("2020A", [{"n": 1, "viejo": "La señal es estelar [[2020A]].",
                                      "nuevo": "La señal es estelar [[2020A]], como confirma [[2021B]]."}]))
    r = af.apply(nota, fix, write=True)
    assert r.applied == 1 and r.failed == []
    assert r.added == [("2020A", 1, ["2021B"])], r.added


def test_un_fix_que_SUSTRAE_no_avisa(tmp_path):
    """El control: corregir por sustracción es la dirección que la medición favorece, y no puede
    salir con un aviso — si avisara igual, el aviso no distinguiría nada. ⚠ Lo que se SACA es la
    narración, no una cita: sacar un `[[bibcode]]` lo rehúsa #222, que es la otra mitad."""
    nota = _note(tmp_path, "# T\n\nLa señal es estelar [[2020A]], y el paper la llama probable.\n")
    fix = _fixes(tmp_path, ("2020A", [{"n": 1,
                                      "viejo": "La señal es estelar [[2020A]], y el paper la llama probable.",
                                      "nuevo": "La señal es estelar [[2020A]]."}]))
    r = af.apply(nota, fix, write=True)
    assert r.applied == 1 and r.added == []
