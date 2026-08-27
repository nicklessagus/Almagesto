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

# Docs FECHADOS: bitácora de lo que se planificó/decidió ese día, no contrato vigente — sus
# referencias muertas son correctas (describen el estado de entonces). Desde 1.36.0 viven en
# `docs/internal/`, que **no se versiona**: hablan en lenguaje interno (issues, "tandas", D-N) y un
# plan es lo que se iba a hacer, no lo que el sistema garantiza. El prefijo se conserva por si
# alguno vuelve a `docs/`, y porque el barrido de abajo sólo mira `docs/*.md` (no `docs/internal/`).
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


# Flags que la doc nombra y NO son de `scripts/`: son de herramientas de terceros o del tooling
# meta. Se listan a mano, con su dueño — una lista de excepciones sin dueño se vuelve un colador.
FLAGS_AJENOS = {
    "--check",        # `trace_invariants.py --check` … y `tools/mutar.py`
    "--diff", "--todo", "--ratchet",   # tools/mutar.py
    "--markdown",     # npx defuddle parse --markdown
    "--no-verify",    # git commit
    "--help",         # lo agrega argparse solo, no aparece en ningún `add_argument`
}

# Flags que la doc nombra **precisamente porque ya no existen**. No van con los ajenos: el motivo es
# otro y la distinción importa — un flag retirado que se documenta como retirado es correcto, y uno
# retirado que la doc sigue mandando a usar es un bug. Cada uno con su decisión.
FLAGS_RETIRADOS = {
    "--no-triage": "D-48 — se eliminó: permitía que un candidato ya descartado volviera a entrar "
                   "en silencio. La doc lo nombra para decir que no está.",
}


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
        # Y los flags nombrados EN PROSA, sin el script en la misma línea: `--topic` sobrevivió a
        # R-5 en `docs/operacion.md` porque la frase decía «corre la cadena de arriba con `--topic`»
        # y el barrido de arriba, anclado en `scripts/x.py`, no lo veía. Un flag inventado en prosa
        # se copia igual que uno en un bloque de comandos.
        universo = set().union(*(_flags_declarados(f) for f in sorted((RAIZ / "scripts").glob("*.py"))))
        for flag in set(re.findall(r"`(--[a-z][\w-]+)`", texto)):
            if flag not in universo and flag not in FLAGS_AJENOS and flag not in FLAGS_RETIRADOS:
                faltan.append(f"{etiqueta}: `{flag}` no lo declara NINGÚN script de scripts/")
    assert faltan == [], ("flags nombrados en la doc que el script no declara:\n  "
                          + "\n  ".join(sorted(set(faltan))))


ESTADOS_VALIDOS = ("garantizado y medido", "garantizado sin medir", "garantizado",
                   "parcial", "HUECO", "INCUMPLIDO")


def _estados_del_contrato() -> dict:
    """`{INV-nn: estado}` leído de las tablas de §3 de `contrato.md`."""
    texto = (DOCS / "contrato.md").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^\| \*\*(INV-\d{2,3}(?!\d))\*\* \|(.*)$", texto, re.M):
        cols = [x.strip() for x in m.group(2).split("|")]
        if len(cols) > 2:
            out[m.group(1)] = cols[2]
    return out


def test_ningun_estado_inventado_por_fila():
    """§2 define un vocabulario CERRADO de estados. Tres filas lo evadían con un paréntesis ad-hoc
    —`garantizado y medido (con brecha nombrada)`, `(mitad determinista)`, `(con deuda)`— y una de
    ellas admitía en su propio texto que contradecía el «todos los carriles» de su enunciado. Un
    estado inventado por fila es cómo un documento empieza a mentir sin decir nada falso: la fila
    se lee como garantizada y el paréntesis, que dice lo contrario, no entra en ningún conteo."""
    malos = []
    for inv, estado in _estados_del_contrato().items():
        limpio = re.sub(r"\s*\([^)]*\)", "", estado).replace("*", "").strip()
        if limpio not in ESTADOS_VALIDOS:
            malos.append(f"{inv}: {estado!r}")
        # el paréntesis puede matizar, pero no puede CONTRADECIR la palabra que lo precede
        if "garantizado" in limpio and re.search(r"\((?:[^)]*\b(?:brecha|deuda|mitad|parcial)\b[^)]*)\)",
                                                 estado, re.I):
            malos.append(f"{inv}: el paréntesis contradice el estado — {estado!r}")
    assert malos == [], ("estados fuera del vocabulario cerrado de §2:\n  " + "\n  ".join(malos))


def test_el_conteo_del_encabezado_es_el_de_las_filas():
    """El encabezado de §1 publica cuántos invariantes hay en cada estado. Si el número lo escribe
    una mano y las filas otra, el resumen envejece solo y "un mapa que atribuye mal es peor que uno
    vacío" — con el agravante de que acá el mapa es el documento que mide a todos los demás."""
    from collections import Counter
    c = Counter()
    for estado in _estados_del_contrato().values():
        if "HUECO" in estado:
            c["hueco"] += 1
        elif "INCUMPLIDO" in estado:
            c["incumplido"] += 1
        elif "parcial" in estado.lower():
            c["parcial"] += 1
        elif "sin medir" in estado.lower():
            c["sin_medir"] += 1
        elif "medido" in estado.lower():
            c["medido"] += 1
        else:
            c["garantizado"] += 1
    texto = (DOCS / "contrato.md").read_text(encoding="utf-8")
    m = re.search(r">\s*(\d+) \*garantizados y medidos\* · (\d+) \*garantizados\*[^·]*· (\d+) \*sin\s*\n"
                  r">\s*medir\* · (\d+) \*parciales\* · (\d+) \*HUECO\* · (\d+) \*INCUMPLIDO\*", texto)
    assert m, "no se encontró la línea de medición vigente en §1"
    declarado = tuple(int(x) for x in m.groups())
    real = (c["medido"], c["garantizado"], c["sin_medir"], c["parcial"], c["hueco"], c["incumplido"])
    assert declarado == real, (
        f"el encabezado declara {declarado} y las filas dan {real} "
        f"(medidos, garantizados, sin medir, parciales, HUECO, INCUMPLIDO)")
    assert sum(real) == len(_estados_del_contrato()) == 121


def test_los_flags_retirados_siguen_retirados():
    """La lista de excepciones no puede convertirse en un colador: si un flag "retirado" vuelve a
    existir, la excepción lo estaría tapando — y el motivo por el que se retiró (que `--no-triage`
    dejaba entrar en silencio un candidato ya descartado) es justamente lo que no debe volver."""
    universo = set().union(*(_flags_declarados(f)
                             for f in sorted((RAIZ / "scripts").glob("*.py"))))
    vivos = [f"{f}: {motivo}" for f, motivo in FLAGS_RETIRADOS.items() if f in universo]
    assert vivos == [], ("flags declarados retirados que volvieron a existir:\n  "
                         + "\n  ".join(vivos))


def test_la_doc_no_apunta_a_codigo_por_numero_de_linea():
    """Un puntero `archivo.py:N` **deriva en silencio**: el archivo crece y el número sigue en
    rango, apuntando a otra cosa. Medido: los siete de `contrato.md` apuntaban todos al renglón
    equivocado —INV-10 citaba la m·sini y ahí había el vocabulario de `role`, o sea otro
    invariante—. Un mapa que atribuye mal es peor que uno vacío, y acá el mapa es el documento que
    mide a todos los demás. Los nombres de símbolo no derivan: se usan ésos."""
    # `trazabilidad.md` está EXENTO: lo **genera** `trace_invariants.py` en cada corrida, así que sus
    # punteros se re-derivan del AST y no pueden envejecer — y ahí el número de línea es lo útil
    # (lleva directo al símbolo marcado). La regla es para la doc escrita a mano.
    GENERADOS = {"trazabilidad.md"}
    malos = []
    for doc in _vivos() + [RAIZ / "CLAUDE.md", RAIZ / "README.md"]:
        if not doc.exists() or doc.name in GENERADOS:
            continue
        for m in re.finditer(r"`(?:scripts/)?(\w+)\.py:(\d+)", doc.read_text(encoding="utf-8")):
            if (RAIZ / "scripts" / f"{m.group(1)}.py").exists():
                malos.append(f"{doc.name}: {m.group(0)}` → usá el NOMBRE del símbolo")
    assert malos == [], ("punteros por número de línea a código de `scripts/`:\n  "
                         + "\n  ".join(sorted(set(malos))))


def test_el_diagrama_de_la_cadena_respeta_el_orden_canonico():
    """`CLAUDE.md` dice que el orden canónico vive en el header del orquestador —*"puntero, no
    copia: no replicar la lista de scripts en docs/skills"*— y `docs/ingesta.md` lo replicaba **mal**:
    ponía `extract_fulltext` antes de `make_notes` y omitía `check_retractions`. No es cosmético:
    `extract_fulltext` llama a `make_notes.stamp_fulltext`, que devuelve `False` si la nota todavía
    no existe, así que el diagrama enseñaba un orden en el que ese paso no hace nada."""
    import lib_config as cfg
    texto = (DOCS / "ingesta.md").read_text(encoding="utf-8")
    bloque = texto[texto.index("ingest-star · astro-only"):texto.index("ingest-theme · despacha")]
    posiciones = {}
    for paso in cfg.CADENA_ESTRELLA:
        i = bloque.find(paso)
        assert i >= 0, f"el diagrama de la cadena no nombra `{paso}`"
        posiciones[paso] = i
    orden_doc = [p for p, _ in sorted(posiciones.items(), key=lambda kv: kv[1])]
    assert orden_doc == list(cfg.CADENA_ESTRELLA), (
        f"el diagrama ordena {orden_doc} y la cadena canónica es {list(cfg.CADENA_ESTRELLA)}")


def test_todo_script_invocado_en_la_doc_tiene_main():
    """Un comando que la doc publica como `python scripts/X.py` tiene que ser INVOCABLE.

    `citation_index.py` se documentaba así desde que nació y no tenía `if __name__ == "__main__"`:
    corría, no imprimía nada y **salía 0** sin construir el índice — el operador creía haberlo
    construido y `cited_by_corpus` levantaba `RuntimeError` después. El resto de este archivo valida
    que lo que la doc nombra EXISTA; esto valida que se pueda correr (AUD-05)."""
    docs = [RAIZ / "README.md", RAIZ / "CLAUDE.md"]
    docs += sorted((RAIZ / "docs").glob("*.md"))
    docs += sorted((RAIZ / ".claude" / "skills").glob("*/SKILL.md"))
    invocados = set()
    for d in docs:
        invocados |= set(re.findall(r"python scripts/([a-z_]+)\.py", d.read_text(encoding="utf-8")))
    sin_main = sorted(n for n in invocados
                      if "__main__" not in (RAIZ / "scripts" / f"{n}.py").read_text(encoding="utf-8"))
    assert not sin_main, f"la doc los invoca como script y no tienen __main__: {sin_main}"


def test_el_alcance_de_hipotesis_tiene_invariante_propio():
    """La garantía de D-34 —un veredicto negativo sin alcance declarado se lee como universal— vive
    en `lint.alcance_declarado`/`corpus_vigente`, que llevaban `@inv INV-83`: otro enunciado (el
    recorte de lectura del ingest). El mapa atribuía mal y el conteo «con implementación marcada»
    quedaba inflado — regla de método #4. Se cerró enunciando **INV-92** (AUD-06/AUD-30).

    ⚠ Este test **nació verde** con un assert más laxo, que aceptaba «alcance declarado» y matcheaba
    INV-58 (sobre el diff de lente). El término que discrimina es «hipótesis»: no lo aflojes."""
    contrato = (RAIZ / "docs" / "contrato.md").read_text(encoding="utf-8")
    filas_inv = [l for l in contrato.splitlines() if re.match(r"\|\s*\*\*INV-\d+\*\*", l)]
    cubren = [l for l in filas_inv if "hipótesis" in l.lower() or "hipotesis" in l.lower()]
    assert cubren, "ningún invariante enuncia el alcance de hipótesis (D-34), que el lint ya implementa"


# ── La plantilla del bloque de verificación es la que el parser lee ───────────

def _encabezado_plantilla() -> list[str]:
    """La fila de encabezado de la plantilla que publica el skill `verify-citations`."""
    txt = (SKILLS / "verify-citations" / "SKILL.md").read_text(encoding="utf-8")
    for ln in txt.split("\n"):
        if ln.startswith("| # | Afirmación"):
            return [c.strip() for c in ln.strip().strip("|").split("|")]
    raise AssertionError("no se encontró la fila de encabezado de la plantilla en el skill")


def test_la_plantilla_no_tiene_columna_de_grado():
    """`Score` 0–10 salió en 1.42.0: reintroducía el eje de grado que `parcial` había dejado.

    El campo tampoco gradúa —FActScore etiqueta binario, y los que suman un tercer valor usan
    vocabulario cerrado (`supported`/`inconclusive`/`contradictory`), no una escala—, que es
    exactamente la forma del vocabulario de acá. El guardia existe porque una columna de grado es
    fácil de volver a agregar "para dar más información", y su costo no se ve en la fila: se ve
    cuando dos corridas discrepan y nadie sabe dónde estaba el umbral.
    """
    cols = _encabezado_plantilla()
    assert not any("score" in c.lower() or "puntaje" in c.lower() for c in cols), \
        f"volvió una columna de grado a la plantilla: {cols}"


def test_la_plantilla_y_el_parser_hablan_de_las_mismas_columnas():
    """Red #5: la plantilla que la doc publica tiene que ser legible por el código que la chequea.

    Hasta 1.38.x no lo era —la doc publicaba ocho columnas y el parser leía posiciones fijas 4 y 5—,
    y el efecto medido fue `lint.py --cierre` en rojo permanente sobre toda nota escrita según la
    documentación. Acá se ejercita el camino entero: encabezado de la doc → fila → `parse_verif_table`.
    """
    import lib_blocks as lb

    cols = _encabezado_plantilla()
    fila = {"Afirmación (extracto)": "claim", "Fuente": "[[2009Uno.....1..1M]]",
            "Veredicto": "soportada", "Evidencia": '"cita" (L1)',
            "Ancla": "aaaaaaaaaa", "Hash fuente": "bbbbbbbbbb", "Condición": "—"}
    celdas = ["1"] + [fila[c] for c in cols[1:]]
    nota = ("---\nname: X\n---\n# X\n\n## Verificación de citas (2026-08-25)\n\n"
            + "| " + " | ".join(cols) + " |\n"
            + "|" + "---|" * len(cols) + "\n"
            + "| " + " | ".join(celdas) + " |\n")
    filas = lb.parse_verif_table(nota)
    assert filas is not None and len(filas) == 1
    assert (filas[0].verdict, filas[0].anchor, filas[0].source_hash) == \
        ("soportada", "aaaaaaaaaa", "bbbbbbbbbb")
