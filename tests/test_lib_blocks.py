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
            "temporadas de observación.")
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

| # | Afirmación | Fuente | Veredicto | Ancla | Hash fuente |
|---|---|---|---|---|---|
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
