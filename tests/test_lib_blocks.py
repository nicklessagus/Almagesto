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
    """La plantilla que publican `CLAUDE.md` y el skill `verify-citations` tiene **ocho** columnas
    (con `Score` y `Evidencia`); el parser leía las posiciones 4 y 5, que en esa plantilla son
    justamente esas dos. Resultado medido: `anchor` salía del Score y `source_hash` de la Evidencia,
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
    """Control: la forma corta (sin Score/Evidencia) es la que usa el resto de la suite."""
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
