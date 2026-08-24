"""Las afirmaciones de la documentación sobre el código, como asserts.

`docs/contrato.md` nombra tests concretos y los `SKILL.md` nombran comandos. Hasta hoy eso lo
verificaba un humano (o un agente) leyendo: tres auditorías de esta sesión encontraron referencias
a tests inexistentes, comandos borrados y archivos renombrados. Todo eso es **decidible**, así que
es un assert y no un ritual.
"""
from __future__ import annotations

import py_compile
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"
SKILLS = RAIZ / ".claude" / "skills"

# Docs FECHADOS: son bitácora de lo que se planificó/decidió ese día, no contrato vigente. Sus
# referencias muertas son correctas (describen el estado de entonces).
HISTORICOS = ("plan-implementacion-", "revision-contrato-", "reconciliacion-")


def _vivos(patron="*.md"):
    return [f for f in sorted(DOCS.glob(patron))
            if not any(f.name.startswith(h) for h in HISTORICOS)]


def test_los_tests_que_nombra_la_doc_existen():
    """Un `tests/x.py::test_y` en la doc que no resuelve convierte al documento en un mapa roto —
    que es exactamente lo que `contrato.md` existe para no ser."""
    faltan = []
    for doc in _vivos():
        texto = doc.read_text(encoding="utf-8")
        for arch, test in re.findall(r"(tests/[\w/]+\.py)::(\w+)", texto):
            p = RAIZ / arch
            if not p.exists():
                faltan.append(f"{doc.name}: {arch} no existe")
            elif not re.search(rf"^def {re.escape(test)}\(", p.read_text(encoding="utf-8"), re.M):
                faltan.append(f"{doc.name}: {arch}::{test} no existe")
    assert faltan == [], "referencias a tests que no resuelven:\n  " + "\n  ".join(faltan)


def test_todo_comando_que_nombra_un_skill_existe_y_compila():
    """El chequeo estilo «F2» de las auditorías, que hasta hoy se corría a mano al cerrar un issue.
    Un skill que invoca un script borrado no falla: el agente lo lee y hace otra cosa."""
    faltan, rotos = [], []
    for skill in sorted(SKILLS.rglob("SKILL.md")):
        for nombre in set(re.findall(r"python scripts/(\w+)\.py", skill.read_text(encoding="utf-8"))):
            p = RAIZ / "scripts" / f"{nombre}.py"
            if not p.exists():
                faltan.append(f"{skill.parent.name}: scripts/{nombre}.py")
                continue
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as exc:
                rotos.append(f"{skill.parent.name}: scripts/{nombre}.py — {exc}")
    assert faltan == [], "scripts que un skill invoca y no existen:\n  " + "\n  ".join(faltan)
    assert rotos == [], "scripts que no compilan:\n  " + "\n  ".join(rotos)


def test_los_scripts_que_nombra_la_doc_existen():
    """Mismo criterio para `scripts/x.py` citado en prosa. Es el residuo que dejó el renombre R-5:
    `docs/operacion.md` mandaba a correr `scripts/ingest_topic.py` durante semanas."""
    faltan = []
    for doc in _vivos():
        for nombre in set(re.findall(r"scripts/(\w+)\.py", doc.read_text(encoding="utf-8"))):
            if not (RAIZ / "scripts" / f"{nombre}.py").exists():
                faltan.append(f"{doc.name}: scripts/{nombre}.py")
    assert faltan == [], "scripts nombrados por la doc que no existen:\n  " + "\n  ".join(faltan)


def test_los_archivos_de_config_que_nombra_la_doc_existen():
    """`vault/config/topics.yaml` sobrevivió a R-5 en cuatro documentos vivos, incluido el manual
    del día a día y la línea que explica qué protege `merge=ours`."""
    faltan = []
    for doc in _vivos() + [RAIZ / "README.md", RAIZ / "CLAUDE.md"]:
        for ruta in set(re.findall(r"vault/config/(\w+\.yaml)", doc.read_text(encoding="utf-8"))):
            if not (RAIZ / "vault" / "config" / ruta).exists():
                faltan.append(f"{doc.name}: vault/config/{ruta}")
    assert faltan == [], "config nombrada por la doc que no existe:\n  " + "\n  ".join(faltan)


def _flags_declarados(script: Path) -> set:
    """Los `--flag` que el argparse del script declara. Se leen del TEXTO y no importando el módulo:
    varios scripts de `scripts/` leen `objective.yaml` al importarse y abortan si la bóveda no está
    instanciada — importarlos acá haría que el test midiera el estado de la bóveda en vez de el de
    la doc."""
    txt = script.read_text(encoding="utf-8")
    return set(re.findall(r"add_argument\(\s*[\"'](--[\w-]+)[\"']", txt))


def test_todo_flag_que_nombra_la_doc_existe():
    """El hueco que este archivo tenía: validaba que el SCRIPT existiera, no que el FLAG existiera.
    Medido: `CLAUDE.md` mandaba a correr `make_notes.py --restamp-keywords`, un flag que el issue
    que lo prometió nunca implementó, y los cuatro tests de acá pasaban en verde. Un flag inventado
    es peor que un comando faltante: el script corre, ignora la instrucción o muere con un error de
    argparse, y la doc sigue leyéndose como si la feature existiera."""
    faltan = []
    fuentes = [(d.name, d) for d in _vivos()] + [("CLAUDE.md", RAIZ / "CLAUDE.md"),
                                                 ("README.md", RAIZ / "README.md")]
    fuentes += [(f"skill:{s.parent.name}", s) for s in sorted(SKILLS.rglob("SKILL.md"))]
    for etiqueta, doc in fuentes:
        if not doc.exists():
            continue
        texto = doc.read_text(encoding="utf-8")
        # `python scripts/x.py [args…] --flag` — se toman los flags que siguen en la MISMA línea
        for linea in texto.split("\n"):
            for m in re.finditer(r"scripts/(\w+)\.py([^\n`]*)", linea):
                script = RAIZ / "scripts" / f"{m.group(1)}.py"
                if not script.exists():
                    continue                      # lo cubre el test de arriba
                declarados = _flags_declarados(script)
                for flag in re.findall(r"(?<![\w-])(--[a-z][\w-]+)", m.group(2)):
                    if flag not in declarados:
                        faltan.append(f"{etiqueta}: scripts/{m.group(1)}.py {flag}")
    assert faltan == [], ("flags nombrados en la doc que el script no declara:\n  "
                          + "\n  ".join(sorted(set(faltan))))
