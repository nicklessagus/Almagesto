"""Trazabilidad requisito ↔ código: recolecta las marcas `@inv` y genera `docs/trazabilidad.md`.

POR QUÉ ESTE SCRIPT EXISTE. `docs/contrato.md` §3 enuncia 91 invariantes falsables, pero la columna
"cómo se verifica" nombra archivos y líneas sueltas en prosa: no hay mapa consultable de qué función
implementa cada invariante ni qué test lo prueba. Las dos formas posibles se evaluaron el 2026-08-24
y se eligió ésta:

- **matriz manual en `docs/`** — barata de arrancar y se desincroniza en silencio. Es exactamente el
  modo de falla que este repo ya registró tres veces (la doc afirmando una garantía que el código
  no da).
- **marcas + recolector (elegida)** — la relación vive **en el código**, al lado de lo que la
  cumple, y el mapa se **regenera**. Un mapa que se regenera no puede mentir sobre el código de hoy;
  a lo sumo queda viejo en disco, y para eso está `--check`.

LA MARCA. Explícita y de una sola forma: `@inv INV-nn` (varios: separados por coma), en un
**comentario** o en un **docstring**, en `scripts/` o en `tests/`. Los ejemplos de sintaxis de esta
doc usan `nn`/`mm` a propósito: un id real acá haría que el recolector se auto-adjudicara cobertura
(pasó en la primera corrida — se marcaba solo INV-87 e INV-90). Mencionar `INV-nn` en prosa **no** es una marca
— el repo nombra invariantes en docstrings todo el tiempo, y recolectar por substring afirmaría
cobertura que nadie escribió. Por el mismo motivo una marca dentro de un **string literal** cualquiera
tampoco cuenta: es texto citado (código de juguete de un test, una plantilla), no una declaración
sobre el código de al lado. La marca se asocia al `def`/`class` que la contiene (el más cercano
hacia arriba), así el artefacto dice *qué símbolo* la cumple y no sólo *qué archivo*.

LAS TRES PUERTAS (exit code):

- `0` — corrió y limpio.
- `1` — bloqueante: hay una **marca huérfana** (apunta a un `INV-nn` que el contrato no declara →
  la marca queda muda, mismo modo de falla que un `thesis_links` sin página destino), o el conteo
  de invariantes sin marca supera el **techo** del ratchet, o `--check` encontró el artefacto
  desactualizado.
- `2` — **no evaluado**: el contrato no se pudo leer o §3 no trae ninguna tabla parseable. No se
  reporta "0 sin marcar": un chequeo que no pudo correr nunca contribuye un cero (D-43 / INV-87).

EL RATCHET (`docs/trazabilidad-ratchet.yaml`). Hoy los 91 invariantes están sin marcar y exigir 0
sería rojo permanente — un rojo permanente se deja de mirar. El techo es deuda MEDIDA y **sólo puede
bajar**: cada tanda del plan marca los invariantes que cierra y baja el techo. Si el conteo sube por
encima, alguien tiene que mirarlo; si baja, el artefacto lo dice y pide bajar el techo (un techo
viejo que nadie ajusta deja de ser ratchet y se vuelve decorativo).

Uso:
    python scripts/trace_invariants.py            # regenera docs/trazabilidad.md
    python scripts/trace_invariants.py --check    # no escribe; falla si lo commiteado está viejo
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTRATO = ROOT / "docs" / "contrato.md"
ARTEFACTO = ROOT / "docs" / "trazabilidad.md"
RATCHET = ROOT / "docs" / "trazabilidad-ratchet.yaml"

# Dónde se buscan marcas. `scripts/` = implementación, `tests/` = prueba; el árbol se decide por el
# primer componente de la ruta relativa, no por el nombre del archivo (un helper `scripts/lib_x.py`
# usado sólo por tests sigue siendo implementación).
ARBOLES = {"scripts": "impl", "tests": "test"}

# La marca. `@inv` obligatorio: sin él, `INV-nn` es prosa. Uno o varios ids separados por coma.
# `\d{2}` **con frontera** (`(?!\d)`). Sin ella, un `INV-100` se recolecta como **INV-10**: la
# marca queda atribuida al invariante equivocado y el mapa afirma que INV-10 está cubierto por un
# test que prueba otra cosa — "un mapa que atribuye mal es peor que uno vacío", y encima en el
# artefacto cuyo trabajo es no atribuir mal. Hoy hay 91 invariantes: la frontera está a nueve.
MARCA_RE = re.compile(r"@inv\s+(INV-\d{2}(?!\d)(?:\s*,\s*INV-\d{2}(?!\d))*)")
INV_RE = re.compile(r"INV-\d{2}(?!\d)")
# Fila de invariante de las tablas de §3: `| **INV-01** | enunciado | P0 | estado | cómo |`
FILA_RE = re.compile(r"^\|\s*\*\*(INV-\d{2}(?!\d))\*\*\s*\|(.*)$")
AREA_RE = re.compile(r"^###\s+(.+?)\s*$")
SEC3_RE = re.compile(r"^##\s+3\.\s")
SEC_RE = re.compile(r"^##\s+")
DEF_RE = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)")


@dataclass(frozen=True)
class Mark:
    """Una marca `@inv` en el código: qué invariante, en qué árbol, dónde, en qué símbolo."""
    inv: str
    kind: str        # "impl" | "test"
    path: str        # relativa a la raíz del repo
    line: int
    symbol: str      # el def/class que la contiene ("" si está a nivel módulo)


class ContratoIlegible(RuntimeError):
    """El registro canónico no se pudo leer → *no evaluado* (rc 2), nunca un cero inventado."""


# ── registro canónico ────────────────────────────────────────────────────────────────────────────

def parse_contrato(text: str) -> dict:
    """Las tablas de invariantes de §3 → `{INV-nn: {area, enunciado, prio, estado}}`.

    Sólo se leen las filas DENTRO de §3: el resto del documento nombra invariantes en prosa y en
    tablas de otra forma (§4 los discute uno por uno), y una entrada fantasma ahí inventaría un
    requisito que el contrato no enuncia.
    """
    reg: dict[str, dict] = {}
    en_sec3 = False
    area = ""
    for ln in text.splitlines():
        if SEC3_RE.match(ln):
            en_sec3 = True
            continue
        if en_sec3 and SEC_RE.match(ln):
            break
        if not en_sec3:
            continue
        m = AREA_RE.match(ln)
        if m:
            area = m.group(1)
            continue
        m = FILA_RE.match(ln)
        if m:
            cols = [c.strip() for c in m.group(2).split("|")]
            if len(cols) < 3:
                continue
            reg[m.group(1)] = {
                "area": area,
                "enunciado": cols[0],
                "prio": _limpio(cols[1]),
                "estado": _limpio(cols[2]),
            }
    return reg


def _limpio(celda: str) -> str:
    """Saca el énfasis markdown de una celda (`**HUECO** (D-53)` → `HUECO (D-53)`)."""
    return re.sub(r"\s+", " ", celda.replace("**", "").replace("`", "")).strip()


def load_registro(root: Path) -> dict:
    contrato = root / "docs" / "contrato.md"
    if not contrato.exists():
        raise ContratoIlegible(f"{contrato} no existe")
    reg = parse_contrato(contrato.read_text(encoding="utf-8"))
    if not reg:
        raise ContratoIlegible(f"{contrato}: §3 no trae ninguna tabla de invariantes parseable")
    return reg


# ── recolección ──────────────────────────────────────────────────────────────────────────────────

def lineas_declarativas(fuente: str) -> set[int]:
    """Las líneas de un módulo donde una marca CUENTA: comentarios y docstrings.

    Un `@inv` dentro de cualquier otro string literal es texto citado —el código de juguete que un
    test escribe a disco, una plantilla— y contarlo afirma cobertura que nadie declaró. Medido en la
    primera corrida real: el archivo de tests de este mismo script aportaba 7 "pruebas" de INV-01
    que no lo tocan. Si el archivo no parsea, se devuelven sólo los comentarios (`tokenize` no
    necesita un AST válido): degradar a nada dejaría marcas mudas en silencio.
    """
    ok: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(fuente).readline):
            if tok.type == tokenize.COMMENT:
                ok.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        arbol = ast.parse(fuente)
    except SyntaxError:
        return ok
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        cuerpo = getattr(nodo, "body", None)
        if not cuerpo:
            continue
        primero = cuerpo[0]
        if (isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant)
                and isinstance(primero.value.value, str)):
            ok.update(range(primero.value.lineno, (primero.value.end_lineno or primero.value.lineno) + 1))
    return ok


def collect_marks(root: Path) -> list[Mark]:
    """Todas las marcas `@inv` de `scripts/` y `tests/`, en orden estable (ruta, línea)."""
    marcas: list[Mark] = []
    for arbol, kind in sorted(ARBOLES.items()):
        base = root / arbol
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            fuente = p.read_text(encoding="utf-8")
            lineas = fuente.splitlines()
            declarativas = lineas_declarativas(fuente)
            rel = p.relative_to(root).as_posix()
            for n, ln in enumerate(lineas, 1):
                m = MARCA_RE.search(ln)
                if not m or n not in declarativas:
                    continue
                simbolo = _simbolo_de(lineas, n)
                for inv in INV_RE.findall(m.group(1)):
                    marcas.append(Mark(inv, kind, rel, n, simbolo))
    return marcas


def _simbolo_por_ast(fuente: str, n: int) -> str | None:
    """El `def`/`class` **más interno** que contiene la línea `n`, o `""` si es de módulo.
    `None` si el archivo no parsea (el llamador cae al heurístico)."""
    try:
        arbol = ast.parse(fuente)
    except (SyntaxError, ValueError):
        return None
    mejor, span = "", None
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if nodo.lineno <= n <= (nodo.end_lineno or nodo.lineno):
            ancho = (nodo.end_lineno or nodo.lineno) - nodo.lineno
            if span is None or ancho < span:
                mejor, span = nodo.name, ancho
    return mejor


def _simbolo_por_indentacion(lineas: list[str], n: int) -> str:
    """Heurístico de respaldo, para el archivo que NO parsea."""
    marca = lineas[n - 1] if 0 < n <= len(lineas) else ""
    sangria = len(marca) - len(marca.lstrip())
    if sangria == 0:
        return ""
    for i in range(n - 2, -1, -1):
        linea = lineas[i]
        if not linea.strip():
            continue
        propia = len(linea) - len(linea.lstrip())
        if propia >= sangria:
            continue
        m = DEF_RE.match(linea)
        return m.group(1) if m else ""
    return ""


def _simbolo_de(lineas: list[str], n: int) -> str:
    """El `def`/`class` que contiene la línea `n` (1-indexada). "" si es a nivel de módulo.

    **Se decide por AST**, no por texto, y la diferencia no es de pureza. Con el heurístico de
    indentación la atribución dependía de **cómo estaba escrita la marca**, no de dónde estaba:
    se midió que 23 de 77 marcas vivas conservaban su símbolo *sólo* porque el script que las
    insertó las dejó mal indentadas, y re-indentarlas —un `black`, un reindent— rompía el 30% del
    mapa **en silencio**: sin marca huérfana, sin cambio de conteo, sin `--check` en rojo, porque el
    artefacto se regenera con el símbolo perdido. Además el heurístico atribuía a una función de
    **juguete** dentro de un docstring de ejemplo, y perdía el símbolo en cuatro formas normales de
    escribir código (marca dentro de un `if`, de un dict multilínea, tras una continuación de línea,
    o bajo una firma multilínea).

    El heurístico **queda como respaldo** para el archivo que no parsea, que es justo el caso en que
    uno quiere saber qué invariante toca."""
    por_ast = _simbolo_por_ast("\n".join(lineas), n)
    return _simbolo_por_indentacion(lineas, n) if por_ast is None else por_ast

def load_techos(root: Path) -> dict:
    """Techos del ratchet. Ausente = sin techo (0): un ratchet que no está no puede aflojar nada."""
    path = root / "docs" / "trazabilidad-ratchet.yaml"
    if not path.exists():
        return {"sin_marca": 0, "sin_test": 0}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    techos = data.get("techos") if isinstance(data, dict) else None
    if not isinstance(techos, dict):
        return {"sin_marca": 0, "sin_test": 0}
    return {"sin_marca": int(techos.get("sin_marca", 0)), "sin_test": int(techos.get("sin_test", 0))}


# ── artefacto ────────────────────────────────────────────────────────────────────────────────────

def render(registro: dict, marcas: list[Mark], techos: dict) -> str:
    """El mapa consultable. Generado — se regenera, no se edita a mano."""
    por_inv: dict[str, list[Mark]] = {}
    for m in marcas:
        por_inv.setdefault(m.inv, []).append(m)

    huerfanas = [m for m in marcas if m.inv not in registro]
    sin_marca = [i for i in registro if i not in por_inv]
    sin_test = [i for i in registro if not any(m.kind == "test" for m in por_inv.get(i, []))]

    out = [
        "# Trazabilidad requisito ↔ código",
        "",
        "> ⚠ **Archivo generado** por `python scripts/trace_invariants.py`. No editar a mano: se",
        "> regenera. La relación vive en las marcas `@inv INV-nn` del código, al lado de lo que",
        "> cumple el invariante; acá sólo se recolecta. El enunciado de cada invariante y su estado",
        "> son autoridad de `docs/contrato.md` §3.",
        "",
        "## Resumen",
        "",
        f"- Invariantes en el contrato: **{len(registro)}**",
        f"- Con implementación marcada: **{len(registro) - len([i for i in registro if not any(m.kind == 'impl' for m in por_inv.get(i, []))])}**",
        f"- Con test marcado: **{len(registro) - len(sin_test)}** (techo `sin_test`: {techos['sin_test']}, hoy {len(sin_test)})",
        f"- Sin ninguna marca: **{len(sin_marca)}** (techo `sin_marca`: {techos['sin_marca']})",
        f"- Marcas huérfanas: **{len(huerfanas)}**",
        "",
    ]

    if huerfanas:
        out += [
            "## ⛔ Marcas huérfanas",
            "",
            "Una marca que apunta a un invariante que el contrato no declara queda **muda**: nadie",
            "se entera de que no cubre nada (mismo modo de falla que un `thesis_links` sin página",
            "destino). Corregir el id o agregar el invariante a `docs/contrato.md` §3.",
            "",
            "| Marca | Dónde |",
            "|---|---|",
        ]
        for m in huerfanas:
            out.append(f"| `{m.inv}` | `{m.path}:{m.line}`{f' · `{m.symbol}`' if m.symbol else ''} |")
        out.append("")

    for aviso, actual, techo in (
        ("sin_marca", len(sin_marca), techos["sin_marca"]),
        ("sin_test", len(sin_test), techos["sin_test"]),
    ):
        if actual < techo:
            out += [
                f"> ✅ `{aviso}` bajó a **{actual}** (techo {techo}) — **bajá el techo** en",
                "> `docs/trazabilidad-ratchet.yaml`: un techo que nadie ajusta deja de ser ratchet.",
                "",
            ]
        elif actual > techo:
            out += [
                f"> ⛔ `{aviso}` = **{actual}**, por encima del techo {techo}. El techo sólo puede",
                "> bajar: marcá lo que falta en vez de subirlo.",
                "",
            ]

    out += ["## El mapa", "", "| ID | Prio | Estado (contrato) | Implementa | Prueba |", "|---|---|---|---|---|"]
    for inv, meta in registro.items():
        ms = por_inv.get(inv, [])
        impl = _celda([m for m in ms if m.kind == "impl"])
        test = _celda([m for m in ms if m.kind == "test"])
        out.append(f"| **{inv}** | {meta['prio']} | {meta['estado']} | {impl} | {test} |")
    out.append("")
    return "\n".join(out)


def _celda(marcas: list[Mark]) -> str:
    if not marcas:
        return "—"
    return "<br>".join(
        f"`{m.path}:{m.line}`" + (f" · `{m.symbol}`" if m.symbol else "") for m in marcas)


# ── main ─────────────────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Recolecta las marcas @inv y genera docs/trazabilidad.md")
    ap.add_argument("--check", action="store_true",
                    help="no escribe; falla si el artefacto commiteado no es el que se generaría")
    ap.add_argument("--root", default=str(ROOT), help="raíz del repo (default: la de este script)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    try:
        registro = load_registro(root)
    except ContratoIlegible as e:
        print(f"⛔ no evaluado: {e}", file=sys.stderr)
        print("⛔ no evaluado — el registro canónico de invariantes no se pudo leer; "
              "no se afirma nada sobre la cobertura.")
        return 2

    marcas = collect_marks(root)
    techos = load_techos(root)
    texto = render(registro, marcas, techos)

    huerfanas = [m for m in marcas if m.inv not in registro]
    por_inv = {m.inv for m in marcas}
    sin_marca = [i for i in registro if i not in por_inv]
    sin_test = [i for i in registro
                if not any(m.kind == "test" and m.inv == i for m in marcas)]

    artefacto = root / "docs" / "trazabilidad.md"
    if args.check:
        vigente = artefacto.read_text(encoding="utf-8") if artefacto.exists() else None
        if vigente != texto:
            print(f"⛔ {artefacto} está desactualizado — correr `python scripts/trace_invariants.py`")
            return 1
    else:
        artefacto.parent.mkdir(parents=True, exist_ok=True)
        artefacto.write_text(texto, encoding="utf-8")
        print(f"→ {artefacto}")

    print(f"invariantes: {len(registro)} · sin marca: {len(sin_marca)} (techo {techos['sin_marca']}) "
          f"· sin test: {len(sin_test)} (techo {techos['sin_test']}) · huérfanas: {len(huerfanas)}")

    rc = 0
    if huerfanas:
        print(f"⛔ {len(huerfanas)} marca(s) huérfana(s): " +
              ", ".join(f"{m.inv} en {m.path}:{m.line}" for m in huerfanas))
        rc = 1
    if len(sin_marca) > techos["sin_marca"]:
        print(f"⛔ sin marca {len(sin_marca)} > techo {techos['sin_marca']}")
        rc = 1
    if len(sin_test) > techos["sin_test"]:
        print(f"⛔ sin test {len(sin_test)} > techo {techos['sin_test']}")
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
