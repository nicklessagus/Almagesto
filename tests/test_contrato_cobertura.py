"""Los huecos de contrato de la auditoría del 2026-09-22 que se cruzan contra TODO el repo.

AUD-439 (el mapa categoría bloqueante → invariante, §3.L) y AUD-436 (los escritores de la
extracción). Los tests de una sola función viven en el archivo de su módulo (#439): los de
INV-161 e INV-82 están en `tests/test_write_verif_sidecar.py`.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import lint
import trace_invariants as ti

RAIZ = Path(__file__).resolve().parent.parent
CONTRATO = RAIZ / "docs" / "contrato.md"
MAPA_TITULO = "#### Mapa: categoría bloqueante → invariante"
FILA_MAPA = re.compile(r"^\|\s*`([a-z_]+)`\s*\|\s*(INV-\d{2,3}(?:\s*,\s*INV-\d{2,3})*)\s*\|")


def _mapa() -> dict:
    """`{clave: [INV-nn, …]}` de la tabla de §3.L. Sólo las filas de ESA tabla."""
    texto = CONTRATO.read_text(encoding="utf-8")
    assert MAPA_TITULO in texto, "el contrato ya no publica el mapa categoría bloqueante → invariante"
    tramo = texto.split(MAPA_TITULO, 1)[1]
    tramo = re.split(r"^#{2,4}\s", tramo, maxsplit=1, flags=re.M)[0]
    out: dict = {}
    for ln in tramo.splitlines():
        if (m := FILA_MAPA.match(ln)):
            assert m.group(1) not in out, f"`{m.group(1)}` figura dos veces en el mapa"
            out[m.group(1)] = re.findall(r"INV-\d{2,3}", m.group(2))
    return out


# ── INV-164 · toda categoría bloqueante tiene un invariante que la exige (AUD-439) ────────────────

def test_toda_categoria_BLOQUEANTE_tiene_un_invariante_vivo_que_la_exige(toy_vault):
    # @inv INV-164
    """AUD-439 (D-7/D-11): cuatro bloqueantes frenaban el cierre sin invariante que lo exigiera, y
    nada lo decía — la lista de `SEV_BLOQUEANTE` crecía por un lado y el contrato por otro. El cruce
    va en las DOS direcciones: una bloqueante nueva sin fila en el mapa rompe acá, y una fila que
    nombra una categoría que ya no bloquea (o un invariante que no existe o se retiró) también."""
    bloqueantes = {c.clave for c in lint.collect().categorias if c.severidad == lint.SEV_BLOQUEANTE}
    assert bloqueantes, "sin bloqueantes el cruce no mide nada (no evaluado ≠ verde)"
    mapa = _mapa()
    assert sorted(bloqueantes - set(mapa)) == [], "bloqueantes sin invariante en el mapa de §3.L"
    assert sorted(set(mapa) - bloqueantes) == [], "el mapa nombra categorías que no son bloqueantes"
    registro = ti.parse_contrato(CONTRATO.read_text(encoding="utf-8"))
    malos = [f"{k} → {i}" for k, invs in mapa.items() for i in invs
             if i not in registro or ti.is_retired(registro[i])]
    assert malos == [], "el mapa apunta a invariantes inexistentes o retirados"


# ── INV-160 · la extracción la reescriben sólo sus escritores declarados (AUD-436) ───────────────

#: Toda función de `scripts/`/`tools/` que ESCRIBE (write_text/atomic, rename, unlink, dump) y además
#: serializa JSON o toca `cfg.EXTRACCION`. La lista se ENUMERA por AST y cada una se declara: o es
#: uno de los escritores de la extracción que INV-160 admite, o dice adónde escribe en su lugar.
EXTRACCION_ESCRITORES = {
    "replace_pdf.stamp_depagination": "agrega `_paginacion` (#436); no toca la lectura",
    "repaginate.apply": "localizadores tras RELEER el PDF (#494), con sus guardas",
    "make_notes._move_extraction": "`--rename-paper`: mueve y reescribe SÓLO `bibcode` (#228/#374)",
    "make_notes.migrate_all_extracciones": "migrador #311: MUEVE de `build/`, sin tocar contenido",
}
OTROS_ESCRITORES = {
    "bench_verify.cmd_seed": "build/ (examen y clave del benchmark)",
    "citation_index.build": "build/ (índice de citas)",
    "fetch_arxiv.main": "build/ (faltantes del fetcher)",
    "fetch_ground_truth.write_ground_truth": "raw/ground_truth/",
    "fetch_pdf.main": "build/ (faltantes del fetcher)",
    "harvest_views.restamp_view_locators": "la NOTA (lee la extracción)",
    "harvest_views.restamp_salvedades": "la NOTA (lee la extracción)",
    "lib_config.record_pdf_source": "build/<slug>/pdf_source.json",
    "make_notes.stamp_scope": "frontmatter de la nota",
    "make_notes.migrate_all_source_fields": "frontmatter de la nota",
    "query_ads.main": "build/<slug>/ads.json",
    "repaginate.write_round": "el paquete de la ronda (fuera de raw/)",
    "reverify_subset.main": "la salida que pide `--json`",
    "verify_fanout.write_round": "el manifiesto de la ronda (build/)",
    "refresh_issues.main": "tools/issues.json",
}
_ESCRITURAS = {"write_text_atomic", "write_text", "rename", "unlink", "replace", "dump", "rmtree"}


def _escritores_candidatos() -> set:
    out = set()
    for arbol in ("scripts", "tools"):
        for f in sorted((RAIZ / arbol).glob("*.py")):
            for fn in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                llamadas = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
                nombres = {getattr(c.func, "attr", getattr(c.func, "id", "")) for c in llamadas}
                json_dumps = any(isinstance(c.func, ast.Attribute) and c.func.attr == "dumps"
                                 and getattr(c.func.value, "id", "") == "json" for c in llamadas)
                extraccion = any(isinstance(n, ast.Attribute) and n.attr == "EXTRACCION"
                                 for n in ast.walk(fn))
                if nombres & _ESCRITURAS and (json_dumps or extraccion):
                    out.add(f"{f.stem}.{fn.name}")
    return out


def test_la_EXTRACCION_la_reescriben_solo_los_escritores_declarados():
    # @inv INV-160
    """AUD-436 (D-8): `raw/extraccion/` es versionada y no regenerable (#311), y el código la
    escribe en dos lugares —`_paginacion` y la re-paginación— sin que ningún invariante dijera
    cuáles. La enumeración es por AST, no de memoria (#409): un escritor nuevo que serializa JSON o
    toca `cfg.EXTRACCION` rompe acá hasta que alguien declare adónde escribe.

    ⚠ Recorte declarado: la heurística mira la FUNCIÓN que escribe; un escritor que recibe la ruta
    de otra función y escribe texto sin `json.dumps` no entra (el borrado/renombre de la entidad
    entera, `entity.py`, es INV-19)."""
    hallados = _escritores_candidatos()
    declarados = set(EXTRACCION_ESCRITORES) | set(OTROS_ESCRITORES)
    assert sorted(hallados - declarados) == [], "escritor nuevo sin declarar adónde escribe"
    assert sorted(declarados - hallados) == [], "declarado que ya no existe (o dejó de escribir)"
