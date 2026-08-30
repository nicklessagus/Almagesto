"""lib_blocks: partición en bloques + los dos hashes del ancla (D-4 / D-20 / INV-78).

Qué protege este archivo, en orden de importancia:

1. **La granularidad elegida es de BLOQUE, no de línea ni de sección.** Las otras dos se
   descartaron midiendo: por **línea**, las notas van hard-wrapped a ~100 columnas y reflowear
   corre todos los cortes → falsos "vencido" en masa; por **sección**, editar una frase invalida
   doce citas. Los dos casos adversarios están sembrados acá.
2. **Sobre-disparar es correcto, sub-disparar no.** Un párrafo con 3 citas da 3 pares con la misma
   ancla: tocás una frase y se re-verifican las tres. El error tiene que caer del lado caro
   (verificar de más), nunca del lado mentiroso (decir "verificado" sobre texto que nadie miró).
3. **La herencia de cita** (fila/ítem sin `[[bibcode]]` propio que lo toma del caption/párrafo que
   la introduce, ya en `CLAUDE.md`) entra en el ancla: editar el caption cambia lo que las filas
   afirman, así que tiene que vencerlas.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest

import lib_blocks as lb     # noqa: E402


# ── normalize_ws ─────────────────────────────────────────────────────────────────────────────────

def test_normalize_ws_colapsa_y_recorta():
    assert lb.normalize_ws("  a   b\n  c \n") == "a b c"


# ── el ancla: qué la mueve y qué no ──────────────────────────────────────────────────────────────

PARRAFO = ("El período de rotación es de 34 días [[2019Autor]], medido con el S-index sobre "
           "diez temporadas de observación.")


def test_reflow_no_mueve_ancla():
    """EL caso adversario de la granularidad elegida: el mismo párrafo hard-wrapped a 80 y a 100
    columnas tiene que dar el MISMO hash. Por línea, reflowear corría todos los cortes y marcaba la
    nota entera como vencida."""
    a80 = ("El período de rotación es de 34 días [[2019Autor]], medido con el\n"
           "S-index sobre diez temporadas de observación.")
    a100 = ("El período de rotación es de 34 días [[2019Autor]], medido con el S-index sobre diez\n"
            "temporadas de observación.")   # @inv INV-78
    assert lb.block_anchor(a80) == lb.block_anchor(a100)


def test_cambiar_numero_mueve_ancla():
    assert lb.block_anchor(PARRAFO) != lb.block_anchor(PARRAFO.replace("34 días", "36 días"))


def test_ancla_es_10_hex_estable():
    a = lb.block_anchor(PARRAFO)
    assert len(a) == 10 and all(c in "0123456789abcdef" for c in a)
    assert a == lb.block_anchor(PARRAFO)


# ── partición ────────────────────────────────────────────────────────────────────────────────────

NOTA = """\
# tau Ceti

Un párrafo con una cita [[2019Autor]] y prosa alrededor
que sigue en la línea siguiente.

> ⚠ Un blockquote de disclaimer [[2020Meta]].

Parámetros medidos por [[2021Tabla]]:

| Campo | Valor |
|---|---|
| P_rot | 34 d |
| Teff | 5344 K |

- Un ítem con cita propia [[2022Item]].
- Un ítem sin cita propia.

## Verificación de citas (2026-01-01)

| # | Afirmación | Fuente | Veredicto | Ancla | Hash fuente | Condición |
|---|---|---|---|---|---|---|
| 1 | P_rot 34 d | [[2019Autor]] | soportada | abc0123456 | def0123456 |
"""


def test_split_blocks_tipos():
    kinds = [b.kind for b in lb.split_blocks(NOTA)]
    assert "parrafo" in kinds and "blockquote" in kinds and "fila" in kinds and "item" in kinds


def test_bloque_de_verificacion_no_genera_pares():
    """Sus filas llevan `[[bibcode]]` y NO son afirmaciones: son el registro de auditoría. Si
    entraran, el bloque se hashearía a sí mismo y cada re-verificación lo vencería sola."""
    bibs = [p.bibcode for p in lb.pairs_of(NOTA)]
    assert "2019Autor" in bibs
    assert bibs.count("2019Autor") == 1, "la fila del bloque de verificación entró como par"


def test_separador_y_encabezado_de_tabla_no_son_pares():
    """`|---|---|` y la fila de encabezado no afirman nada; heredarían la cita del caption y
    ensuciarían el bloque de verificación con pares permanentes que nadie puede resolver."""
    textos = [b.text for b in lb.split_blocks(NOTA) if b.kind == "fila"]
    assert not any(set(t) <= set("|-: ") for t in textos)
    assert not any("Campo" in t for t in textos), "la fila de encabezado entró como bloque"


def test_tres_citas_un_bloque_tres_pares_misma_ancla():
    """Sobre-disparo deliberado: tocar la frase re-verifica las tres."""
    body = "Coinciden [[2019A]], [[2020B]] y [[2021C]] en el mismo valor."
    pares = lb.pairs_of(body)
    assert sorted(p.bibcode for p in pares) == ["2019A", "2020B", "2021C"]
    assert len({p.anchor for p in pares}) == 1


def test_editar_un_bloque_no_mueve_los_otros():
    """Adversario de la granularidad por SECCIÓN, que invalidaba doce citas por editar una frase."""
    antes = {(p.bibcode, p.anchor) for p in lb.pairs_of(NOTA)}
    despues = {(p.bibcode, p.anchor) for p in lb.pairs_of(NOTA.replace("34 d", "36 d"))}
    assert antes != despues
    assert len(antes - despues) == 1, "una edición movió más pares que el suyo"


# ── herencia (fila/ítem sin cita propia) ─────────────────────────────────────────────────────────

TABLA = """\
Parámetros medidos por [[2021Tabla]]:

| Campo | Valor |
|---|---|
| P_rot | 34 d |
| Teff | 5344 K |
"""


def test_fila_sin_cita_propia_hereda_del_caption():
    pares = lb.pairs_of(TABLA)
    assert [p.bibcode for p in pares].count("2021Tabla") == 3, (
        "el caption y sus dos filas tienen que dar un par cada uno")


def test_editar_el_caption_vence_las_filas():
    """El caption es lo que dice QUIÉN mide: si cambia, cambia lo que la fila afirma."""
    antes = {p.anchor for p in lb.pairs_of(TABLA)}
    otro = TABLA.replace("Parámetros medidos por", "Parámetros ESTIMADOS por")
    assert antes.isdisjoint({p.anchor for p in lb.pairs_of(otro)})


def test_editar_una_fila_no_vence_las_otras():
    pares = {(p.bibcode, p.anchor) for p in lb.pairs_of(TABLA)}
    otra = {(p.bibcode, p.anchor) for p in lb.pairs_of(TABLA.replace("5344 K", "5350 K"))}
    assert len(pares - otra) == 1


def test_fila_con_cita_propia_no_hereda():
    """Si la fila trae su `[[bibcode]]`, el caption no entra en su ancla: editarlo no la vence."""
    t = "Medido por [[2021Tabla]]:\n\n| Campo | Valor | Fuente |\n|---|---|---|\n| P_rot | 34 d | [[2019Autor]] |\n"
    propio = [p for p in lb.pairs_of(t) if p.bibcode == "2019Autor"]
    assert len(propio) == 1
    otro = t.replace("Medido por", "ESTIMADO por")
    assert [p.anchor for p in lb.pairs_of(otro) if p.bibcode == "2019Autor"] == [propio[0].anchor]


# ── source_hash ──────────────────────────────────────────────────────────────────────────────────

def test_source_hash_estable_y_sensible(tmp_path):
    p = tmp_path / "2019Autor.txt"
    p.write_text("El período es de 34 días.\n", encoding="utf-8")
    h = lb.source_hash(p)
    assert h == lb.source_hash(p) and len(h) == 10
    p.write_text("El período es de 36 días.\n", encoding="utf-8")
    assert lb.source_hash(p) != h


def test_sha10_permite_pasar_el_texto_ya_leido(tmp_path):
    """El lint YA lee cada `.txt` para `is_legible` (77% de sus 5,6 s sobre 908 notas): una sola
    lectura tiene que alimentar los dos chequeos. Sin esta puerta, agregar el hash de fuente
    duplicaría la parte más cara del lint."""
    p = tmp_path / "x.txt"
    p.write_text("contenido", encoding="utf-8")
    assert lb.sha10(p.read_text(encoding="utf-8")) == lb.source_hash(p)


# ── frontmatter ──────────────────────────────────────────────────────────────────────────────────

def test_frontmatter_no_genera_pares():
    """`thesis_links`, `stars`, `disputes[].ref` no son afirmaciones en prosa."""
    t = "---\ntags: [star]\ndisputes:\n- field: P_rot\n  posiciones:\n  - ref: 2019Autor\n---\n\nProsa sin citas.\n"
    assert lb.pairs_of(t) == []


def test_code_fence_no_genera_pares():
    """Los bloques ```dataview``` traen wikilinks dentro de la query — no afirman nada."""
    t = 'Prosa.\n\n```dataview\nLIST FROM [[2019Autor]]\n```\n'
    assert lb.pairs_of(t) == []


def test_item_sin_cita_hereda_del_parrafo_que_lo_introduce():
    t = "Los tres indicadores que reporta [[2021Fuente]]:\n\n- S-index.\n- H-alpha.\n"
    assert [p.bibcode for p in lb.pairs_of(t)].count("2021Fuente") == 3


def test_encabezado_de_seccion_tambien_es_ambito():
    """`CLAUDE.md` nombra tres ámbitos —caption, párrafo y **encabezado de sección**—; el tercero
    se perdía cuando la herencia se resolvía en una segunda pasada sobre los bloques citables (un
    encabezado no es un bloque citable, así que no estaba ahí para consultarlo)."""
    t = "## Valores de [[2021Fuente]]\n\n| Campo | Valor |\n|---|---|\n| P_rot | 34 d |\n"
    assert [p.bibcode for p in lb.pairs_of(t)] == ["2021Fuente"]


def test_parrafo_posterior_reemplaza_al_encabezado_como_ambito():
    """El ámbito es el MÁS CERCANO: un caption entre el encabezado y la tabla manda."""
    t = ("## Sección con [[2020Header]]\n\nMedido por [[2021Caption]]:\n\n"
         "| Campo | Valor |\n|---|---|\n| P_rot | 34 d |\n")
    filas = [p for p in lb.pairs_of(t) if p.block.kind == "fila"]
    assert [p.bibcode for p in filas] == ["2021Caption"]


# ── parse_verif_table: la tabla del bloque de verificación (issue 1.2) ───────────────────────────

BLOQUE = """\
Afirmación con cita [[2019Autor]].

## Verificación de citas (2026-01-01)

| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |
|---|---|---|---|---|---|---|
| 1 | P_rot de 34 días | [[2019Autor]] | soportada | a3f9c1e2ab | 7b40d8aa11 | — |
| 2 | Teff 5344 K | [[2020Otro]] | soportada | bbbbbbbbbb | cccccccccc | sólo para la muestra activa |
"""


def test_parse_verif_table_lee_las_filas():
    filas = lb.parse_verif_table(BLOQUE)
    assert [f.bibcode for f in filas] == ["2019Autor", "2020Otro"]
    assert filas[0].anchor == "a3f9c1e2ab" and filas[0].source_hash == "7b40d8aa11"
    assert filas[0].verdict == "soportada"
    assert filas[0].condition == "—" and filas[1].condition == "sólo para la muestra activa", \
        "la condición es un EJE propio desde 1.39.0: se lee y se conserva, no se absorbe en el veredicto"


def test_parse_verif_table_plantilla_vieja_devuelve_none():
    """Detector de plantilla vieja (sin migrador: bóveda nueva). Un bloque sin las columnas de hash
    no es "cero pares vencidos": es un bloque que no se puede evaluar — y leerlo como limpio sería
    el mismo cero inventado que D-43 prohíbe."""
    viejo = BLOQUE.replace("| Ancla | Hash fuente | Condición |", "|").replace(
        "| a3f9c1e2ab | 7b40d8aa11 |", "|").replace("| bbbbbbbbbb | cccccccccc |", "|")
    assert lb.parse_verif_table(viejo) is None


def test_bloque_sin_columna_condicion_es_plantilla_vieja():
    """1.39.0 partió `Veredicto` en dos ejes: respaldo (textual) y condición (régimen). Un bloque
    sin la columna `Condición` es **pre-1.39.0** y no se puede evaluar — registraba el veredicto y
    tiraba lo que la corrida había encontrado sobre el régimen.

    Que sea BLOQUEANTE y no una lectura tolerante es la política del repo: schema nuevo = detector,
    nunca lector permisivo. Y acá hay un motivo extra medido: en el experimento de dos corridas del
    2026-08-25, pares con veredicto idéntico traían condiciones DISTINTAS — leer un bloque viejo
    como si estuviera completo afirmaría que no había nada que declarar."""
    sin_cond = BLOQUE.replace(" | Condición |", " |").replace("|---|---|---|---|---|---|---|",
                                                              "|---|---|---|---|---|---|")
    assert lb.parse_verif_table(sin_cond) is None


def test_parcial_salio_del_vocabulario():
    """`parcial` fusionaba el eje textual con el de grado. Medido: 3 divergencias entre dos corridas
    independientes, las TRES en el borde `soportada`↔`parcial`, ninguna en `contradice`."""
    assert "parcial" not in lb.VERDICTS
    assert set(lb.VERDICTS) == {"soportada", "no-soportada", "contradice",
                                  "no verificable por extracción"}


def test_parse_verif_table_sin_bloque_devuelve_none():
    assert lb.parse_verif_table("Prosa sin bloque [[2019Autor]].\n") is None


def test_parse_verif_table_tabla_vacia_es_lista_vacia():
    """Bloque bien formado y sin filas ≠ bloque no evaluable: devuelve `[]`, y todo par del cuerpo
    queda *sin verificar*."""
    vacia = ("## Verificación de citas (2026-01-01)\n\n"
             "| # | Afirmación (extracto) | Fuente | Veredicto | Ancla | Hash fuente | Condición |\n"
             "|---|---|---|---|---|---|---|\n")
    assert lb.parse_verif_table(vacia) == []


def test_parse_lee_por_NOMBRE_de_columna_no_por_posicion():
    """La plantilla vieja tenía **ocho** columnas (con `Score` y `Evidencia`); el parser leía las
    posiciones 4 y 5, que en esa plantilla son justamente esas dos.

    ⚠ AUD-214 — `Score` **se eliminó en 1.42.0** (reintroducía un eje de grado cuyo umbral nunca se
    calibró) y la plantilla vigente no la tiene. La fixture la conserva **a propósito y dicho acá**:
    lo que este test fija no es esa columna sino la propiedad —se lee por NOMBRE— y una columna que
    el parser no conoce es el caso adversario que la prueba. Escrita sin la aclaración, la fixture
    se leía como si `Score` siguiera viva. Resultado medido: `anchor` salía del Score y `source_hash` de la Evidencia,
    **en silencio** —el detector de plantilla vieja no lo agarra porque el encabezado sí contiene
    las palabras «ancla» y «hash»— así que toda nota escrita según la documentación dejaba
    `lint.py --cierre` en **rojo permanente**, que es el cierre de toda operación que toca una nota.

    Se lee por nombre de columna: la posición deja de importar y agregar una columna no rompe nada.
    """
    bloque = (
        "## Verificación de citas (2026-08-24)\n\n"
        "| # | Afirmación (extracto) | Fuente | Veredicto | Score | Evidencia | Ancla | Hash fuente | Condición |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| 1 | P_rot = 34 d | [[2020ApJ...900...1A]] | soportada | 0.9 | \"34 d\" (L12) | abc1234567 | def8901234 | — |\n")
    filas = lb.parse_verif_table(bloque)
    assert filas is not None and len(filas) == 1
    f = filas[0]
    assert f.anchor == "abc1234567", f"leyó {f.anchor!r} — está tomando el Score"
    assert f.source_hash == "def8901234", f"leyó {f.source_hash!r} — está tomando la Evidencia"
    assert f.bibcode == "2020ApJ...900...1A" and f.verdict == "soportada"


def test_parse_sigue_leyendo_la_tabla_de_seis_columnas():
    """Control: la forma corta es la PLANTILLA VIGENTE (`Score` salió en 1.42.0)."""
    bloque = (
        "## Verificación de citas (2026-08-24)\n\n"
        "| # | Afirmación | Fuente | Veredicto | Ancla | Hash fuente | Condición |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 1 | X | [[2020ApJ...900...1A]] | soportada | abc1234567 | def8901234 | — |\n")
    f = lb.parse_verif_table(bloque)[0]
    assert (f.anchor, f.source_hash) == ("abc1234567", "def8901234")


def test_cuerpo_no_confunde_reglas_horizontales_con_frontmatter():
    """`_cuerpo` no replicaba el guard de posición-0 de `cfg.frontmatter_span`: una nota que arranca
    con `---algo` (no un delimitador, la línea tiene más contenido) pasaba el `startswith` y tomaba
    como frontmatter los dos primeros `---` sueltos del cuerpo. El cuerpo quedaba recortado desde el
    segundo y los pares anteriores **desaparecían del fan-out** — sub-dispara, que es justo el error
    que el módulo documenta prohibir."""
    texto = "---nota rara\n\nAfirmación con [[2020A]].\n\n---\n\nmás prosa\n\n---\n\nfinal\n"
    cuerpo, saltadas = lb._cuerpo(texto)
    assert cuerpo == texto and saltadas == 0, "sin frontmatter en posición 0 no se recorta nada"
    assert "[[2020A]]" in cuerpo


def test_cuerpo_si_recorta_un_frontmatter_de_verdad():
    texto = "---\nbibcode: 2020A\n---\n\nAfirmación.\n"
    cuerpo, saltadas = lb._cuerpo(texto)
    assert "bibcode" not in cuerpo and "Afirmación." in cuerpo and saltadas == 2


# ── bytes_hash: la evidencia que sale de un PDF (#113/B-2) ───────────────────────────────────────

def test_bytes_hash_de_un_pdf_es_estable_y_sensible(tmp_path):
    """Un PDF no es texto. Cuando el `.txt` de una fuente perdió el cuerpo de sus ecuaciones, la
    evidencia de esos pares es una PÁGINA del PDF, así que el archivo a vigilar es el PDF."""
    p = tmp_path / "paper.pdf"
    p.write_bytes(b"%PDF-1.4\n\x00\x01\x02 binario que no es utf-8: \xff\xfe\n")
    h = lb.bytes_hash(p)
    assert len(h) == 10 and h == lb.bytes_hash(p)
    p.write_bytes(b"%PDF-1.4\n\x00\x01\x03 otro contenido\n")
    assert lb.bytes_hash(p) != h


def test_bytes_hash_no_se_cae_con_bytes_no_utf8(tmp_path):
    """`source_hash` decodifica con errors=replace, así que dos PDFs distintos podrían colisionar
    tras la sustitución. `bytes_hash` mira los bytes crudos."""
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    a.write_bytes(b"\xff\xfe")
    b.write_bytes(b"\xff\xfd")
    assert lb.bytes_hash(a) != lb.bytes_hash(b)


def test_sha10_acepta_bytes_y_texto_en_el_mismo_espacio():
    """Un solo espacio de hashes para los dos tipos de evidencia: una fila no puede confundir el
    hash de un `.txt` con el de un PDF."""
    assert lb.sha10("hola") == lb.sha10(b"hola")


def test_un_veredicto_con_enfasis_markdown_sigue_bloqueando():
    """Issue #168 — `resueltos` comparaba el string LITERAL (`v == mal or v.startswith(mal + " ")`)
    mientras su docstring prometía un criterio semántico (*"lo que bloquea es el veredicto
    pelado"*). Poner el veredicto en **negrita** —cosa que un autor hace sin pensarlo en una tabla
    markdown— lo daba por resuelto, y con eso reabría el agujero exacto que INV-117 existe para
    cerrar: una fila `no-soportada` sentada bajo un encabezado que se lee como garantía.

    El énfasis no es una resolución: no dice qué se hizo con la falla.  @inv INV-117"""
    for celda in ("**no-soportada**", "*no-soportada*", "`contradice`", "__contradice__",
                  "no-soportada.", "**contradice**"):
        assert not lb.resueltos(celda), f"{celda!r} sigue sin resolver: sólo cambia el formato"


def test_la_resolucion_anotada_no_bloquea_lleve_o_no_espacios():
    """Issue #168, el otro lado del mismo bug: `startswith(mal + " ")` daba por SIN RESOLVER a
    `no-soportada → corregida` —la flecha con espacios, que es como se escribe a mano— mientras
    aceptaba la versión pegada. El criterio es *"¿hay una resolución anotada en la celda?"*, y eso
    no depende del espaciado.  @inv INV-117"""
    for celda in ("no-soportada→corregida", "no-soportada → corregida", "no-soportada->corregida",
                  "contradice → disputa tagueada", "no-soportada (corregida)"):
        assert lb.resueltos(celda), f"{celda!r} declara qué se hizo con la falla"


def test_el_veredicto_pelado_bloquea():
    """La otra mitad del contrato de #168: normalizar no puede volverse permisivo. Un veredicto
    solo, sin resolución anotada, sigue bloqueando.  @inv INV-117"""
    assert not lb.resueltos("no-soportada")
    assert not lb.resueltos("contradice")
    assert not lb.resueltos("  NO-SOPORTADA  ")
    assert lb.resueltos("soportada"), "el caso normal no dispara nada"
    assert lb.resueltos("no verificable por extracción"), "propiedad de la fuente, no defecto"


# ── #128 · una fila con `|` sin escapar no puede desaparecer ─────────────────────────────────────

_BLOQUE_PIPE = """\
Afirmación con cita [[2019Autor]].

## Verificación de citas (2026-01-01)

| # | Afirmación (extracto) | Fuente | Veredicto | Evidencia | Ancla | Hash fuente | Condición |
|---|---|---|---|---|---|---|---|
| 1 | P_rot de 34 días | [[2019Autor]] | no-soportada | cita: a | b (L12) | a3f9c1e2ab | txt:7b40d8aa11 | — |
"""


def test_una_fila_con_pipe_sin_escapar_no_pierde_el_veredicto():
    """Issue #128 — la fila se descartaba ENTERA (`continue`), así que un veredicto `no-soportada`
    dejaba de disparar el bloqueante de INV-117 y quedaba invisible en la pasada periódica.

    El skill `verify-citations` dice que la barra sin escapar *"es el caso normal, no el raro"* (18
    pares medidos en una ficha real). Descartar la fila es peor que leerla a medias: el veredicto
    vive a la IZQUIERDA del corrimiento y es perfectamente recuperable.  @inv INV-117"""
    filas = lb.parse_verif_table(_BLOQUE_PIPE)
    assert filas is not None and len(filas) == 1, "la fila no desaparece"
    assert filas[0].verdict == "no-soportada", "el veredicto se recupera"
    assert not lb.resueltos(filas[0].verdict), "y sigue exigiendo acción"
    assert filas[0].bibcode == "2019Autor"


def test_una_fila_corrida_no_reporta_un_ancla_ajena():
    """La otra mitad de #128, y la razón por la que el `continue` existía: con un `|` de más, las
    columnas de la DERECHA (ancla, hash, condición) están corridas, e indexarlas por posición leería
    el ancla de otra celda — el par volvería *vencido por edición* sin que nadie editara nada
    (medido: 18 pares, 2026-08-25). No se adivina: se declaran vacías.  @inv INV-99"""
    fila = lb.parse_verif_table(_BLOQUE_PIPE)[0]
    assert fila.anchor == "", "sin ancla, no un ancla ajena"
    assert fila.source_hash == "" and fila.source_kind is None


@pytest.mark.parametrize("fila, verd", [
    ('| 1 | x | [[2020a]] | no-soportada | "y" (p. 3) | aaaa | pdf:bbbb |', "no-soportada"),
    ('| 1 | x | [[2020a]] | contradice |', "contradice"),
])
def test_una_fila_con_MENOS_celdas_no_pierde_su_veredicto(fila, verd):
    """Una fila corta —típico: la `Condición` vacía omitida— se descartaba ENTERA con un `continue`,
    y con ella el `Veredicto`: un `no-soportada` dejaba de disparar el bloqueante de INV-117 y
    quedaba registrado bajo un encabezado que se lee como garantía.

    Es **el mismo defecto que #128 arregló para la dirección opuesta** (celdas de más ⇒ se recupera
    por contenido), con el mismo argumento: descartar la fila es peor que leerla a medias.
    @inv INV-117"""
    enc = ("| # | Afirmación (extracto) | Fuente | Veredicto | Evidencia | Ancla | Hash fuente | "
           "Condición |")
    t = (f"# X\n\n## Verificación de citas (2026-01-01)\n\n{enc}\n"
         f"|---|---|---|---|---|---|---|---|\n{fila}\n")
    filas = lb.parse_verif_table(t)
    assert len(filas) == 1 and filas[0].verdict == verd
    assert filas[0].bibcode == "2020a"
    assert filas[0].anchor == "", "sin ancla el par cae en «sin verificar», que es lo correcto"


def test_link_re_es_el_mismo_en_lint_y_en_lib_blocks():
    """Red #2: dos módulos que prometen la misma forma se prueban UNA vez. Los dos `LINK_RE` son
    gemelos —el mismo patrón, copiado— y el defecto del `[[` sin cerrar vivía en los dos. Si alguien
    aprieta uno y no el otro, esto lo dice."""
    import lint
    assert lint.LINK_RE.pattern == lb.LINK_RE.pattern
    t = "Mal [[ y sigo.\nEl radio vive en [[gp-kernels]]."
    assert lint.LINK_RE.findall(t) == lb.LINK_RE.findall(t) == ["gp-kernels"]


@pytest.mark.parametrize("v", ["contradise", "", "no soportada", "NO-SOPORTADA "])
def test_un_veredicto_fuera_del_vocabulario_NO_cuenta_como_resuelto(v):
    """Medido el 2026-08-28: `resueltos('contradise')`, `resueltos('')` y `resueltos('no soportada')`
    devolvían **True**, o sea que el bloqueante que INV-117 sostiene **se apagaba con una letra** —
    y la fila quedaba registrada bajo un encabezado que se lee como garantía.

    Una celda que no se puede leer no certifica nada.  @inv INV-117"""
    if v.strip().lower().rstrip() == "no-soportada":
        return                       # ése sí es válido: sólo mide el vocabulario, no el espaciado
    assert lb.resueltos(v) is False
    assert lb.verdict_valido(v) is False


@pytest.mark.parametrize("v, resuelto", [
    ("soportada", True), ("no-soportada", False), ("contradice", False),
    ("no-soportada→corregida", True), ("no verificable por extracción", True),
])
def test_el_vocabulario_valido_se_comporta_igual_que_antes(v, resuelto):
    """La otra mitad: apretar no puede cambiar el veredicto de lo que sí está en el vocabulario."""
    assert lb.verdict_valido(v) is True
    assert lb.resueltos(v) is resuelto


def test_parse_corta_en_la_seccion_SIGUIENTE():
    """AUD-215 — la rama `if corte > 0` (el bloque de verificación seguido de otra sección) no la
    tocaba ningún test.

    Sin ella el parser se comería todo lo que viene después: una tabla de `## Inventario por eje`
    empieza con `|` igual que una fila de verificación, así que sus filas entrarían como pares
    verificados — pares que nadie verificó, con anclas leídas de columnas ajenas."""
    bloque = (
        "## Verificación de citas (2026-08-24)\n\n"
        "| # | Afirmación | Fuente | Veredicto | Ancla | Hash fuente | Condición |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 1 | X | [[2020ApJ...900...1A]] | soportada | abc1234567 | pdf:def8901234 | — |\n\n"
        "## Inventario por eje\n\n"
        "| Eje | Paper | Dice | Método |\n"
        "|---|---|---|---|\n"
        "| P_rot | [[2019otroB...1..1B]] | 34 d | periodograma |\n")
    filas = lb.parse_verif_table(bloque)
    assert filas is not None and len(filas) == 1, [f.bibcode for f in (filas or [])]
    assert filas[0].bibcode == "2020ApJ...900...1A"


def test_una_seccion_propia_con_nombre_parecido_no_se_saltea():
    """#214 — `pairs_of` cortaba con un `startswith` pelado, o sea la regla VIEJA que INV-98 ya
    había arreglado dentro de `_es_estampada` y que nunca llegó acá: `## Papers relevantes para el
    método` es prosa propia y se saltaba entera, así que sus pares no se verificaban nunca."""
    texto = ("# nota\n\n## Papers relevantes para el método\n"
             "El valor es 3.4 m/s [[2020Autor]].\n")
    pares = lb.pairs_of(texto)
    assert any("2020Autor" in p.bibcode for p in pares), pares


def test_la_traduccion_estampada_sigue_exenta():
    """#214, la otra mitad: la exención que sí corresponde no se pierde al unificar la regla."""
    texto = ("# nota\n\n## Traducción del abstract\n"
             "Presentamos el método de [[2020Autor]].\n")
    assert lb.pairs_of(texto) == []


def test_un_blockquote_hard_wrapped_es_UN_bloque():
    """#224 — las notas van hard-wrapped a ~100 columnas, así que una cita textual larga vive
    partida en varias líneas y **sólo la última lleva el `[[bibcode]]`**. Emitiendo por línea, el
    único par que nacía anclaba la última línea y las demás no las cubría nadie."""
    texto = ("> *«If the hidden signals under investigation follow Gaussian distributions,\n"
             "> uncorrelatedness is equivalent to mutual independence and algorithms such as PCA\n"
             "> are able to separate them»* ([[2019AJ....158..161D]], §2.3, p. 4).\n")
    pares = lb.pairs_of(texto)
    assert len(pares) == 1
    assert "If the hidden signals" in pares[0].block.text, pares[0].block.text
    assert "uncorrelatedness is equivalent" in pares[0].block.text


def test_mutar_el_medio_de_la_cita_vence_el_par():
    """#224, el punto — sub-disparo es la única dirección de error que este módulo prohíbe. Antes,
    invertir el sentido de una línea del medio dejaba el ancla IDÉNTICA: se podía reescribir el
    contenido de una cita textual sin que el par se venciera."""
    # ⚠ La mutación va en una línea que NO lleva el bibcode: si va en la misma, el ancla cambia
    # también con el comportamiento viejo y el test pasaría por el motivo equivocado (#202).
    base = ("> *«If the hidden signals under investigation follow Gaussian distributions,\n"
            "> uncorrelatedness {} equivalent to mutual independence and algorithms such as PCA\n"
            "> are able to separate them»* ([[2019AJ....158..161D]], p. 4).\n")
    a = lb.pairs_of(base.format("is"))[0].anchor
    b = lb.pairs_of(base.format("is NOT"))[0].anchor
    assert a != b, "mutar el medio de la cita tiene que vencer el par"


def test_el_blockquote_no_pasa_a_ser_el_ambito_vigente():
    """#224, el recorte — antes el blockquote se emitía sin pasar por `flush`, así que nunca era
    ámbito de herencia. Al acumularlo como párrafo lo sería, y una fila que sigue a la cabecera
    `> _Estado — …_` empezaría a colgar de ella. El cambio es sobre el ANCLA, no sobre la herencia."""
    texto = ("> _Estado — búsqueda 2026-08-28 ([[2019AJ....158..161D]])._\n\n"
             "| A | B |\n|---|---|\n| uno | dos |\n")
    assert [p.bibcode for p in lb.pairs_of(texto)] == ["2019AJ....158..161D"]


# ── #263 · el cuarto veredicto entra al resumen ──────────────────────────────────────────────────


def _row(veredicto, cond=""):
    return lb.Row(n=1, claim="c", bibcode="2020aaa...1..1A", verdict=veredicto, evidence="e",
                  anchor="a" * 10, source_hash="pdf:" + "b" * 10, condition=cond)


def test_verif_counts_cuenta_los_no_verificables_y_los_cuatro_particionan():
    """#263 — sin el cuarto veredicto los conteos NO PARTICIONAN.

    Medido en una ficha real: 73 + 6 + 5 = 84 sobre 88 pares, y las 4 que faltaban eran
    `no verificable por extracción` **correctas** (#223: la fuente no está en disco). El lector que
    suma queda con filas sin explicar, y las dos lecturas naturales —«la tabla está cortada», «el
    conteo está mal»— son las dos falsas. Es D-43 sin aplicar a la cabecera del propio bloque."""
    filas = [_row("soportada"), _row("no-soportada→corregida"), _row("contradice→corregida"),
             _row("no verificable por extracción"), _row("no verificable por extracción")]
    c = lb.verif_counts(filas)
    assert c["no_verificables"] == 2
    assert (c["soportadas"] + c["no_soportadas"] + c["contradicen"] + c["no_verificables"]
            == c["pares"]), "los cuatro veredictos tienen que particionar las filas"


def test_verif_summary_publica_los_no_verificables_y_separa_el_eje_de_condicion():
    """El `—` separa los dos EJES: los cuatro veredictos particionan; `con_condicion` es ortogonal
    (una fila `soportada` puede tener condición). Juntarlos con `/` es lo que hacía leer el resumen
    como una partición de cinco que no cerraba."""
    linea = lb.verif_summary([_row("soportada", "acota: X"),
                              _row("no verificable por extracción")])
    assert "1 no verificables" in linea, "el cuarto veredicto no se publica"
    assert "— 1 con condición declarada" in linea, "el eje ortogonal no se separa"


def test_verif_summary_distingue_la_no_soportada_resuelta_de_la_pelada():
    """#286 — el número que bloquea el cierre era el peor etiquetado.

    Medido en una ficha real: la cabecera publicaba «9 no-soportadas» con las 9 resueltas y
    `lint --cierre` en 0, así que la lectura natural —«esta ficha tiene 9 afirmaciones que su fuente
    no respalda»— era falsa y grave. ⛔ Sin restarlas del total (#232: el número no se blanquea)."""
    filas = [_row("no-soportada→corregida"), _row("no-soportada"),
             _row("contradice→corregida"), _row("soportada")]
    c = lb.verif_counts(filas)
    assert c["no_soportadas"] == 2, "las resueltas NO se restan del total (#232)"
    assert c["no_soportadas_resueltas"] == 1
    assert c["contradicen"] == 1 and c["contradicen_resueltas"] == 1
    linea = lb.verif_summary(filas)
    assert "2 no-soportadas (1 resueltas)" in linea, linea
    assert "1 contradicen (1 resueltas)" in linea, linea


def test_verif_summary_no_promete_resueltas_donde_no_las_hay():
    """La dirección peligrosa: publicar «(N resueltas)» sobre filas peladas leería como cerrada una
    ficha que el lint bloquea."""
    linea = lb.verif_summary([_row("no-soportada"), _row("contradice")])
    assert "1 no-soportadas (0 resueltas)" in linea, linea
    assert "1 contradicen (0 resueltas)" in linea, linea


# ── #284 · la puerta de escritura, simétrica del des-escape de lectura ───────────────────────────


def _row_completa(**kw):
    base = dict(n="1", claim="Parámetros estelares", bibcode="2009A&A...493..639M",
                verdict="soportada", anchor="abc1234567", source_hash="def8901234",
                condition="contextualiza: HARPS", source_kind="pdf",
                evidence='"1.97 ± 0.11 | 2.47 ± 0.11" (p. 6)')
    base.update(kw)
    return lb.Row(**base)


def test_la_fila_escrita_se_lee_como_se_escribio_aunque_la_evidencia_traiga_barras():
    """#284 — el ciclo roto: se lee una fila (pipes ya des-escapados), se reescribe verbatim, la
    fila queda con más celdas que el encabezado y el `Ancla` se lee de la columna equivocada.

    Medido en la reconstrucción de una ficha real: **73 de 131** filas volvieron con `anchor == ""`,
    todas ellas filas cuya `Evidencia` transcribe una tabla del paper."""
    fila = _row_completa()
    tabla = lb.render_verif_table([fila])
    leidas = lb.parse_verif_table(f"{lb.VERIFY_HEADER}\n\n{tabla}\n")
    assert len(leidas) == 1
    assert leidas[0].anchor == "abc1234567", "el ancla se leyó de la columna equivocada"
    assert leidas[0].source_kind == "pdf" and leidas[0].source_hash == "def8901234"
    assert "|" in leidas[0].evidence, "el des-escape de lectura tiene que devolver la barra"


def test_la_ida_y_vuelta_es_idempotente_sobre_una_fila_ya_leida():
    """La propiedad que el flujo de #282 necesita: leer una fila y volver a escribirla no la degrada
    —si no, cada ronda de re-anclaje rompe un poco más el bloque."""
    tabla = lb.render_verif_table([_row_completa()])
    leidas = lb.parse_verif_table(f"{lb.VERIFY_HEADER}\n\n{tabla}\n")
    assert lb.render_verif_table(leidas) == tabla


def test_render_verif_table_no_publica_un_bloque_que_no_se_lee_como_se_escribio():
    """La red de #222 aplicada a #284: re-parsear lo escrito y **no publicar** si no vuelve igual.
    Sin ella, la fila sigue visible, el lint la sigue contando, y lo que se rompe es el ancla."""
    import lib_config as cfg
    orig = cfg.escape_cell
    try:
        cfg.escape_cell = lambda t: t          # un escritor que se olvida del escape (#240)
        with pytest.raises(ValueError, match="no se lee como se escribió"):
            lb.render_verif_table([_row_completa()])
    finally:
        cfg.escape_cell = orig


def test_verif_roundtrip_errors_nombra_la_fila_y_el_campo():
    """El error tiene que decir QUÉ fila y QUÉ campo, o el escritor no sabe dónde mirar."""
    fila = _row_completa(n="7")
    tabla = lb.render_verif_table([fila]).replace(r"\|", "|")   # se rompe el escape a mano
    errores = lb.verif_roundtrip_errors([fila], tabla)
    assert errores and "fila 7" in errores[0] and "anchor" in errores[0], errores


# ── #283 · la condición se lee normalizada, igual que el veredicto de al lado ────────────────────


def test_condition_kind_lee_la_clase_con_adorno_markdown():
    """#283 — `**contextualiza** — …` declara su clase para cualquier lector humano.

    Medido sobre una ficha real: 74 de 88 celdas escritas así, las 74 reportadas por el lint como
    *condición sin clasificar*, o sea 84 % de falsos positivos en la categoría que separa la
    condición que obliga a editar de la que sólo va al reporte."""
    assert lb.condition_kind("**contextualiza** — la muestra es de 4 estrellas") == "contextualiza"
    assert lb.condition_kind("**acota** — sólo para K < 2 m/s") == "acota"
    assert lb.condition_kind("`acota`: sólo bajo SNR alto") == "acota"
    assert lb.condition_kind("_contextualiza_ - HARPS, 2003-2012") == "contextualiza"
    assert lb.condition_kind("acota: X") == "acota", "el prefijo pelado sigue valiendo"


def test_condition_kind_no_inventa_clase_donde_no_la_hay():
    """La ceguera se arregla en una sola dirección: prosa sin clase sigue siendo un hallazgo, y la
    celda vacía no es una clase. Sobre-reportar acá manda a clasificar; sub-reportar apaga #221."""
    assert lb.condition_kind("promedio pesado de 4 proxies") is None
    assert lb.condition_kind("") is None
    assert lb.condition_kind("—") is None
    assert lb.condition_kind("contextualizado por el instrumento") is None


def test_paridad_de_adorno_entre_las_dos_columnas_de_la_misma_fila():
    """La red de #283: lo que `verdict_valido` tolera de adorno en `Veredicto`, `condition_kind` lo
    tolera en `Condición`. Sin la paridad, la misma fila se lee con dos criterios distintos — que es
    exactamente el estado que el issue midió."""
    for forma in ("{0}", "**{0}**", "`{0}`", "_{0}_", "{0} "):
        assert lb.verdict_valido(forma.format("soportada")), forma
        assert lb.condition_kind(forma.format("acota") + ": X") == "acota", forma
        assert lb.condition_kind(forma.format("acota") + " — X") == "acota", forma


# ── #280 · los conteos de las tres sub-secciones también se generan ──────────────────────────────


def test_verif_counts_particiona_las_condiciones():
    """Las tres clases suman `con_condicion`: es lo que hace chequeable el conteo publicado."""
    filas = [_row("soportada", "acota: X"), _row("soportada", "**contextualiza** — Y"),
             _row("soportada", "prosa sin clase"), _row("soportada", "")]
    c = lb.verif_counts(filas)
    assert c["cond_acota"] + c["cond_contextualiza"] + c["cond_sin_clase"] == c["con_condicion"] == 3


def test_verif_subsection_lines_cuenta_las_inferencias_del_CUERPO():
    """#280 — «cinco inferencias» sobre **seis** marcas en el cuerpo, con un elemento de más y uno
    de menos. El conteo sale del mismo código que después lo chequea."""
    prosa = "una (inferencia de [[2020a]]) y otra (**inferencia** de [[2021b]]) más"
    frags = lb.verif_subsection_lines([_row("soportada")], prosa)
    assert frags["Inferencias declaradas"] == "— 2 marcas en el cuerpo"


def test_verif_subsection_lines_no_inventa_un_numero_para_las_omisiones():
    """⛔ D-43 — la completitud es la mitad de JUICIO del fan-out y no está en la tabla: emitir un
    número ahí sería el cero inventado."""
    assert lb.verif_subsection_lines([_row("soportada")], "")["Omisiones en transcripciones"] is None


def test_condition_resolved_no_confunde_la_prosa_con_la_resolucion():
    """⛔ No reusa `resueltos()`: ahí «cualquier cosa después del separador» significa resuelto, y en
    una condición lo que sigue al separador es **la prosa de la condición** — daría 100 % resueltas.
    Y el token se compara ENTERO (#276: `resueltamente` no es `resuelta`)."""
    assert lb.condition_resolved("acota: sólo para K<2 m/s") is False
    assert lb.condition_resolved("**acota**→resuelta: fila en `## Régimen de validez`") is True
    assert lb.condition_resolved("acota → resuelta: X") is True
    assert lb.condition_resolved("acota→resueltamente distinto") is False


# ── #274 · higiene del bloque: el repr, el corte a media fórmula y la cadena de rondas ───────────


def test_el_corte_del_extracto_no_deja_un_dolar_huerfano():
    """#274b — medido: 10 de 88 filas cortadas a media fórmula, las únicas 10 celdas con `$` impar
    de toda la nota. En Obsidian un `$` sin cerrar se traga texto hasta el próximo `$` de la fila."""
    largo = ("sobre 135 medidas HARPS de 4,5 años, con $\\sigma(O-C) = 0{,}92$ m/s y una cola de "
             "texto que empuja el corte justo adentro de la fórmula")
    corte = lb.truncate_claim(largo, 60)
    assert corte.count("$") % 2 == 0, corte
    assert corte.endswith("…")


def test_el_corte_del_extracto_no_parte_un_wikilink():
    """#257c — un `[[` sin cerrar es **bloqueante** en el lint: el corte tiene que retroceder."""
    largo = "la señal la reporta [[2020aaa...1..1A]] y después sigue un rato largo más de prosa"
    corte = lb.truncate_claim(largo, 30)
    assert corte.count("[[") == corte.count("]]"), corte


def test_el_extracto_corto_no_se_toca_y_el_impartible_vuelve_entero():
    """Las dos direcciones seguras: no se trunca lo que entra, y si NO hay corte seguro se devuelve
    entero — una celda rota es peor que una celda larga."""
    assert lb.truncate_claim("corto", 180) == "corto"
    impartible = "$" + "x" * 200 + "$"
    assert lb.truncate_claim(impartible, 50) == impartible


def test_render_verif_row_rechaza_un_repr_de_lista():
    """#274a — la salida estructurada del fan-out serializada con `repr()` en vez de convertida a
    prosa. Medido en dos filas de una ficha real; y `\\'` no es escape de markdown, así que la misma
    celda se lee distinto en Python-Markdown que en markdown-it."""
    fila = _row_completa(evidence="['Tabla 1, fila HD 40307', 'y otra cosa']")
    with pytest.raises(ValueError, match="repr"):
        lb.render_verif_row(fila)


def test_la_cadena_de_rondas_se_lee_entera_y_no_rompe_la_particion():
    """#274c — con una sola flecha no se distingue «una ronda lo corrigió» de «tres lo pelearon».
    Medido: una nota de 8 rondas emitió 13 veredictos malos y publicó 11.

    ⛔ La partición sigue siendo por el PRIMER veredicto: contar la fila en dos baldes rompería el
    invariante de #263, que es lo que hace legible la cabecera."""
    assert lb.verdict_chain("no-soportada→contradice→corregida") == ["no-soportada", "contradice"]
    assert lb.verdict_chain("soportada") == ["soportada"]
    assert lb.resueltos("no-soportada→contradice→corregida") is True
    assert lb.verdict_valido("no-soportada→contradice→corregida") is True
    filas = [_row("no-soportada→contradice→corregida"), _row("soportada")]
    c = lb.verif_counts(filas)
    assert c["cadenas"] == 1
    assert (c["soportadas"] + c["no_soportadas"] + c["contradicen"] + c["no_verificables"]
            == c["pares"]), "la cadena no puede romper la partición de #263"
    assert "1 con más de una ronda" in lb.verif_summary(filas)


# ── #282 · re-anclaje: llevar el veredicto en vez de tirarlo ─────────────────────────────────────


def _fila(n, claim, bib, veredicto="soportada", ancla="a" * 10):
    return lb.Row(n=n, claim=claim, bibcode=bib, verdict=veredicto, evidence="e",
                  anchor=ancla, source_hash="pdf:" + "b" * 10, condition="")


def test_claim_tokens_ignora_markup_y_wikilinks():
    """#282 — el emparejamiento no puede depender del énfasis ni de los links.

    Los `[[wikilink]]` se sacan porque **no discriminan**: están en todos los pares de la misma
    fuente. Y el markup se ignora por construcción (sólo entran letras y dígitos), que es la lección
    que #168 y #276 ya pagaron dos veces con detectores ciegos al adorno."""
    a = lb.claim_tokens("El **período** de [[2016A&A...585A.134D]] es 47,9 d")
    b = lb.claim_tokens("El periodo de [[otro]] es 47,9 d")
    assert "47,9" in a and "período" in a
    assert not any("2016" in t for t in a), "el wikilink entró como token"
    assert a & b, "el adorno rompió el emparejamiento"


def test_match_prioriza_el_ancla_intacta_sobre_el_parecido():
    """El par que nadie tocó se queda con SU fila, aunque otra se le parezca más.

    Sin esta prioridad, una fila ajena con más solapamiento podía robarle la suya a un par intacto y
    dejarlo `sin_fila` — o sea inventar trabajo de re-verificación sobre algo que no cambió."""
    body = "El período orbital medido resulta ser 4,3115 días exactos.\n\n[[2020aaa...1..1A]]\n"
    pares = lb.pairs_of("## X\n\nEl período orbital medido resulta ser 4,3115 días "
                        "exactos [[2020aaa...1..1A]].\n")
    assert len(pares) == 1
    suya = _fila("1", "El período orbital medido resulta ser 4,3115 días exactos",
                "2020aaa...1..1A", ancla=pares[0].anchor)
    parecida = _fila("2", "El período orbital medido resulta ser 4,3115 días exactos y algo más",
                    "2020aaa...1..1A", ancla="zzzzzzzzzz")
    asign, sin_fila, huerf = lb.match_rows_to_pairs(pares, [parecida, suya])
    assert asign[pares[0]][0] is suya, "no ganó el ancla intacta"
    assert sin_fila == [] and huerf == [parecida]


def test_match_no_cruza_bibcodes():
    """⛔ Un par es (afirmación, FUENTE). Llevar un veredicto de una fuente a otra sería fabricar
    justamente la atribución que este framework mide como su modo de falla dominante — 7 de 13
    defectos de una operación real."""
    pares = lb.pairs_of("## X\n\nLa amplitud vale 0,50 metros por segundo [[2020aaa...1..1A]].\n")
    ajena = _fila("1", "La amplitud vale 0,50 metros por segundo", "2021bbb...2..2B")
    asign, sin_fila, huerf = lb.match_rows_to_pairs(pares, [ajena])
    assert asign == {} and sin_fila == pares and huerf == [ajena], \
        "llevó el veredicto de otra fuente"


def test_match_lleva_el_veredicto_cuando_el_extracto_sobrevive():
    """El caso que motiva #282: la corrección **agrega** una salvedad que el propio verificador
    aportó, así que el extracto de la fila sigue entero dentro del bloque nuevo. El ancla se movió;
    el veredicto vale."""
    pares = lb.pairs_of("## X\n\nLa amplitud rotacional vale 0,50 metros por segundo, medida "
                        "después de restar las señales planetarias [[2020aaa...1..1A]].\n")
    fila = _fila("1", "La amplitud rotacional vale 0,50 metros por segundo", "2020aaa...1..1A")
    asign, sin_fila, _ = lb.match_rows_to_pairs(pares, [fila])
    assert sin_fila == [] and asign[pares[0]][0] is fila
    assert asign[pares[0]][1] == 1.0, "el extracto sobrevive entero: cobertura 1,0"


def test_match_no_lleva_el_veredicto_cuando_la_afirmacion_cambio():
    """La otra mitad, y es la que protege: si la corrección **cambió lo que la afirmación dice**, el
    veredicto no vale y el par va al subconjunto. Cobertura, no Jaccard: el extracto está truncado
    por contrato (#226), así que el bloque vigente casi siempre tiene MÁS texto."""
    pares = lb.pairs_of("## X\n\nNinguna fuente aplica separación ciega de componentes "
                        "independientes [[2020aaa...1..1A]].\n")
    fila = _fila("1", "La amplitud rotacional vale 0,50 metros por segundo medida sobre diez años",
                "2020aaa...1..1A")
    asign, sin_fila, huerf = lb.match_rows_to_pairs(pares, [fila])
    assert asign == {} and sin_fila == pares and huerf == [fila]


def test_match_el_ancla_intacta_gana_aunque_otra_fila_calce_mejor():
    """Aísla la prioridad del ancla: la fila propia puede tener PEOR cobertura que una ajena —su
    extracto quedó viejo, o trae texto que la corrección sacó— y aun así es la suya. Sin la
    prioridad, una fila con menos texto (y por eso cobertura trivialmente alta) se la roba."""
    pares = lb.pairs_of("## X\n\nLa amplitud rotacional vale cero coma cincuenta "
                        "[[2020aaa...1..1A]].\n")
    suya = _fila("1", "La amplitud rotacional vale cero coma cincuenta pero además la "
                      "excentricidad resulta francamente despreciable",
                 "2020aaa...1..1A", ancla=pares[0].anchor)
    corta = _fila("2", "amplitud rotacional", "2020aaa...1..1A", ancla="zzzzzzzzzz")
    asign, sin_fila, huerf = lb.match_rows_to_pairs(pares, [corta, suya])
    assert asign[pares[0]][0] is suya, "una fila ajena con menos texto le robó la suya"
    assert huerf == [corta] and sin_fila == []


def test_match_no_reusa_una_fila_para_dos_pares():
    """Cada fila se consume una vez. Sin la guarda, una sola fila certificaría **dos** afirmaciones
    distintas — que es exactamente la certificación fabricada que el bloque existe para no producir.
    """
    pares = lb.pairs_of("## X\n\nLa amplitud rotacional vale cero coma cincuenta "
                        "[[2020aaa...1..1A]].\n\nLa amplitud rotacional vale cero coma cincuenta "
                        "también acá [[2020aaa...1..1A]].\n")
    assert len(pares) == 2
    una = _fila("1", "La amplitud rotacional vale cero coma cincuenta", "2020aaa...1..1A")
    asign, sin_fila, huerf = lb.match_rows_to_pairs(pares, [una])
    assert len(asign) == 1 and len(sin_fila) == 1, "la misma fila cubrió dos pares"
    assert huerf == []


def test_match_respeta_el_umbral_con_solapamiento_parcial():
    """Aísla el umbral: una fila que solapa **algo** pero no lo suficiente NO lleva su veredicto.
    Es la mitad que protege — sin ella, cualquier parecido remoto arrastraría una certificación."""
    pares = lb.pairs_of("## X\n\nLa amplitud rotacional vale cero coma cincuenta metros "
                        "[[2020aaa...1..1A]].\n")
    parcial = _fila("1", "amplitud rotacional pero además excentricidad francamente despreciable "
                         "sobre diez temporadas consecutivas", "2020aaa...1..1A")
    asign, sin_fila, _ = lb.match_rows_to_pairs(pares, [parcial], umbral=0.60)
    assert asign == {} and sin_fila == pares, "llevó el veredicto por un parecido remoto"
    # y con el umbral bajo, la misma fila sí califica: el corte es el parámetro, no un accidente
    asign2, sin_fila2, _ = lb.match_rows_to_pairs(pares, [parcial], umbral=0.15)
    assert sin_fila2 == [] and asign2[pares[0]][0] is parcial


def test_match_con_umbral_cero_no_inventa_una_fila_donde_no_hay():
    """La guarda `mejor is not None` sólo se distingue en el borde, y el borde es una llamada
    legítima: `umbral=0` significa «aceptá cualquier parecido». Ahí `score >= umbral` es cierto
    **siempre**, así que sin la guarda un par sin ninguna fila candidata se asignaría a `None` — o
    sea una fila inventada, que es peor que ninguna."""
    pares = lb.pairs_of("## X\n\nLa amplitud rotacional vale cero coma cincuenta "
                        "[[2020aaa...1..1A]].\n")
    asign, sin_fila, huerf = lb.match_rows_to_pairs(pares, [], umbral=0.0)
    assert asign == {} and sin_fila == pares and huerf == []


# ── #279 · la marca «segunda mano» de la vista, leída por columna ────────────────────────────────

_VISTA = """# p

## Vista — tau Cet (2026-08-30)

| Qué | Valor | Localizador | Régimen | Segunda mano |
|---|---|---|---|---|
| m_V | 7,15 | p. 3 | — | Koen et al. 2010 |
| P_rot | 34 d | p. 5 | HARPS | — |
"""


def test_second_hand_rows_lee_la_columna_por_nombre():
    """#279/#103 — el número marcado de segunda mano NO es de esa fuente, y es el mecanismo de error
    nº 1 medido. Se lee por NOMBRE de columna: una nota vieja puede traer el encabezado `Línea`
    pre-#195."""
    assert lb.second_hand_rows(_VISTA) == [("m_V", "7,15", "Koen et al. 2010")]
    assert lb.second_hand_rows(_VISTA.replace("Localizador", "Línea")) == \
        [("m_V", "7,15", "Koen et al. 2010")]


def test_second_hand_rows_sobrevive_al_pipe_escapado():
    """La celda puede traer su propia barra escapada (#240/#284): partir por `|` pelado correría las
    columnas y la última celda dejaría de ser «Segunda mano»."""
    con_pipe = _VISTA.replace("| 7,15 |", r"| 7,15 \| 7,17 |")
    assert lb.second_hand_rows(con_pipe) == [("m_V", "7,15 | 7,17", "Koen et al. 2010")]


def test_second_hand_rows_solo_mira_las_secciones_de_vista():
    """Otra tabla con la misma forma en otra sección no es una vista."""
    fuera = _VISTA.replace("## Vista — tau Cet (2026-08-30)", "## Inventario por eje")
    assert lb.second_hand_rows(fuera) == []
