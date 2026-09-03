"""Las afirmaciones de la documentación sobre el código, como asserts.

`docs/contrato.md` nombra tests concretos y los `SKILL.md` nombran comandos. Hasta hoy eso lo
verificaba un humano (o un agente) leyendo: tres auditorías de esta sesión encontraron referencias
a tests inexistentes, comandos borrados y archivos renombrados. Todo eso es **decidible**, así que
es un assert y no un ritual.
"""
from __future__ import annotations

import json
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


def test_los_tests_citados_en_forma_ABREVIADA_tambien_existen():
    """`::test_x` sin el prefijo `tests/archivo.py` — la forma que `docs/contrato.md` usa a mano.

    El gate de arriba matchea la forma completa `tests/<archivo>.py::<test>` y **no ve** la corta, que es 79 de
    las 189 citas de test del contrato (42 %). Medido el 2026-08-28: los **tres** punteros muertos
    que dejó #205c estaban los tres en ese punto ciego, y el gate pasaba verde. Es la forma «red que
    no mira» de INV-101 aplicada a la doc, y la regla de método #4: un mapa que atribuye mal es peor
    que uno vacío."""
    vivos = {m.group(1) for p in RAIZ.glob("tests/**/test_*.py")
             for m in re.finditer(r"^def (test_\w+)", p.read_text(encoding="utf-8"), re.M)}
    faltan = []
    for doc in _vivos():
        for m in re.finditer(r"(?<![\w/.])::(test_\w+)", doc.read_text(encoding="utf-8")):
            if m.group(1) not in vivos:
                faltan.append(f"{doc.name}: ::{m.group(1)}")
    assert faltan == [], ("tests citados por la doc que no existen:\n  " + "\n  ".join(sorted(set(faltan))))


def test_los_simbolos_de_scripts_que_nombra_la_doc_existen():
    """`scripts/x.py::simbolo` — el gate validaba que el ARCHIVO exista y nunca el símbolo.

    `#205c` borró `extraction_prompt._symbols_note` y `docs/contrato.md` lo siguió citando como
    evidencia de un P0 durante toda la tanda, con el gate en verde."""
    faltan = []
    for doc in _vivos():
        for m in re.finditer(r"scripts/(\w+)\.py::(\w+)", doc.read_text(encoding="utf-8")):
            mod = RAIZ / "scripts" / f"{m.group(1)}.py"
            if mod.exists() and f"def {m.group(2)}(" not in mod.read_text(encoding="utf-8"):
                faltan.append(f"{doc.name}: scripts/{m.group(1)}.py::{m.group(2)}")
    assert faltan == [], ("símbolos de `scripts/` citados por la doc que no existen:\n  "
                          + "\n  ".join(sorted(set(faltan))))


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


# Los dos árboles cuyos flags la doc puede nombrar. `tools/` entró en #339: el universo se armaba
# con `scripts/*.py` sola, así que los siete flags de `tools/mutar.py` vivían en `FLAGS_AJENOS`, que
# los EXIME en vez de chequearlos — un typo en `--guardas` dentro de cualquier doc no lo cazaba
# nadie. ⚠ Nada que ver con el ALCANCE de la red de mutación (`mutar.ALCANCE`, también `scripts/`):
# ése decide qué se muta; éste, de qué argparse se leen los flags que la doc promete.
ARBOLES_CON_FLAGS = ("scripts", "tools")

# Flags que la doc nombra y NO son de `scripts/` ni de `tools/`: son de herramientas de terceros o
# del tooling meta. Se listan a mano, con su dueño — una lista de excepciones sin dueño se vuelve un
# colador.
FLAGS_AJENOS = {
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


_RUTA = re.compile(r"(" + "|".join(ARBOLES_CON_FLAGS) + r")/(\w+)\.py")


def comandos_de_la_linea(linea: str):
    """`(ruta del script, el resto de SU comando)` por cada comando que la línea escribe.

    ⛔ Los argumentos de un comando terminan donde empieza el siguiente, y una ruta `.py` que es un
    ARGUMENTO no es un comando (#339). `python tools/mutar.py --guardas scripts/triage.py --solo
    main` reportaba *«scripts/triage.py `--solo`»* —atribuyéndole a `triage` un flag que es de
    `mutar`— porque el patrón viejo se llevaba todo lo que siguiera a cualquier ruta hasta el fin de
    la línea. Un mapa que atribuye mal es peor que uno vacío, y acá el mapa decide si un flag que la
    doc promete existe.

    La PRIMERA ruta de un tramo encabeza el comando (la doc los escribe con `python` adelante y sin
    él, las dos formas); una posterior encabeza uno nuevo **sólo si viene detrás de `python`**, y si
    no es un argumento del comando en curso. Los tramos los separan los backticks y los separadores
    de shell, porque una línea de prosa puede llevar dos comandos citados."""
    def _ruta(m):
        return RAIZ / m.group(1) / f"{m.group(2)}.py"
    for tramo in re.split(r"[`;]|&&|\|\|", linea):
        actual = None
        for m in _RUTA.finditer(tramo):
            if actual is None:
                actual = m
            elif tramo[actual.end():m.start()].rstrip().endswith(("python", "python3")):
                yield _ruta(actual), tramo[actual.end():m.start()]
                actual = m
        if actual is not None:
            yield _ruta(actual), tramo[actual.end():]


def _universo_de_flags() -> set:
    """Todos los `--flag` que declara algún argparse de los árboles con flags.

    UNA implementación: el test de prosa y el que fija que `tools/` entre miran el mismo conjunto.
    Con dos copias, agregar un árbol en una y no en la otra dejaría media red mirando de menos."""
    return set().union(*(_flags_declarados(f) for arbol in ARBOLES_CON_FLAGS
                         for f in sorted((RAIZ / arbol).glob("*.py"))))


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
        # `python scripts/x.py [args…] --flag` — los flags de SU comando, no los de la línea entera
        for linea in texto.split("\n"):
            for script, resto in comandos_de_la_linea(linea):
                if not script.exists():
                    continue                      # lo cubre el test de arriba
                declarados = _flags_declarados(script)
                for flag in re.findall(r"(?<![\w-])(--[a-z][\w-]+)", resto):
                    if flag not in declarados:
                        faltan.append(f"{etiqueta}: {script.parent.name}/{script.name} {flag}")
        # Y los flags nombrados EN PROSA, sin el script en la misma línea: `--topic` sobrevivió a
        # R-5 en `docs/operacion.md` porque la frase decía «corre la cadena de arriba con `--topic`»
        # y el barrido de arriba, anclado en `scripts/x.py`, no lo veía. Un flag inventado en prosa
        # se copia igual que uno en un bloque de comandos.
        universo = _universo_de_flags()
        for flag in set(re.findall(r"`(--[a-z][\w-]+)`", texto)):
            if flag not in universo and flag not in FLAGS_AJENOS and flag not in FLAGS_RETIRADOS:
                faltan.append(f"{etiqueta}: `{flag}` no lo declara NINGÚN script de "
                              f"{'/ ni '.join(ARBOLES_CON_FLAGS)}/")
    assert faltan == [], ("flags nombrados en la doc que el script no declara:\n  "
                          + "\n  ".join(sorted(set(faltan))))


ESTADOS_VALIDOS = ("garantizado y medido", "garantizado sin medir", "garantizado",
                   "parcial", "HUECO", "INCUMPLIDO", "retirado")


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
        if "retirado" in estado.lower():
            c["retirado"] += 1
        elif "HUECO" in estado:
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
                  r">\s*medir\* · (\d+) \*parciales\* · (\d+) \*HUECO\* · (\d+) \*INCUMPLIDO\* · "
                  r"(\d+) \*retirados\*", texto)
    assert m, "no se encontró la línea de medición vigente en §1"
    declarado = tuple(int(x) for x in m.groups())
    real = (c["medido"], c["garantizado"], c["sin_medir"], c["parcial"], c["hueco"], c["incumplido"],
            c["retirado"])
    assert declarado == real, (
        f"el encabezado declara {declarado} y las filas dan {real} "
        f"(medidos, garantizados, sin medir, parciales, HUECO, INCUMPLIDO, retirados)")
    # #149: el TOTAL se deriva, no se escribe. El literal ya caducó una vez —el encabezado
    # decía «sobre los 104» con 126 filas— y fijarlo a mano acá sólo movía el problema de
    # lugar. Lo que este assert protege es que el desglose CUBRA todas las filas: si una
    # queda fuera de las seis categorías, la suma no da y el resumen estaría mintiendo por
    # omisión en vez de por número.
    assert sum(real) == len(_estados_del_contrato()), (
        f"el desglose suma {sum(real)} y el contrato tiene {len(_estados_del_contrato())} "
        "filas: hay estados que ninguna categoría del resumen cubre")


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


def test_ningun_help_nombra_un_valor_RETIRADO_del_vocabulario():
    """AUD-210 — el `--help` de `triage` listaba `reporte`, retirado en #206 y ausente de sus
    propios `choices`: el texto contradecía a su parser.

    Un help que nombra un valor que el parser rechaza manda al operador a un comando que no corre —
    y es el mismo modo de falla que `docs/operacion.md` tuvo con `via: reporte` (AUD-122), una capa
    más adentro. La red es que los vocabularios se interpolen desde el código, no se transcriban."""
    import contextlib
    import importlib
    import io
    import sys

    import lint

    retirados = set(lint.VIA_FUENTE_RETIRADO)
    for modulo in ("triage", "make_notes", "query_ads", "ingest_theme", "fetch_web"):
        m = importlib.import_module(modulo)
        buf = io.StringIO()
        with contextlib.suppress(SystemExit), contextlib.redirect_stdout(buf):
            sys.argv = [f"{modulo}.py", "--help"]
            m.main()
        texto = buf.getvalue()
        for valor in retirados:
            assert f"| {valor}" not in texto and f"{valor} |" not in texto, \
                f"{modulo} --help nombra `{valor}`, que es vocabulario retirado"


# ── #266 · los dos vocabularios de `via`, doc ↔ código ───────────────────────────────────────────


def test_claude_md_declara_los_dos_vocabularios_de_via():
    """#266 — `CLAUDE.md` enunciaba **un** vocabulario binario debajo de una tabla que muestra los
    **dos** carriles (`extra_core` y `sources:`), y el de `extra_core` no contiene `descubrimiento`.

    Un agente que seguía la doc escribía `via: descubrimiento` en `extra_core` y el loader lo
    rechaza duro. Es el defecto que #162 cerró en el `help=` de la CLI, sobreviviendo en la fuente
    que un agente lee **antes** de editar `stars.yaml` a mano — o sea el arreglo aplicado a la mitad
    de sus lectores. Este test ata la prosa a las dos constantes: agregar o sacar un valor mueve el
    documento en vez de esconderse.
    """
    import lib_config as cfg
    import triage
    doc = (Path(__file__).resolve().parent.parent / "CLAUDE.md").read_text(encoding="utf-8")
    assert cfg.EXTRA_CORE_VIA != triage.VIA_FUENTE, \
        "si los dos carriles convergieron, este test y el párrafo de CLAUDE.md sobran"
    for valor in cfg.EXTRA_CORE_VIA:
        assert f"`{valor}`" in doc, f"`CLAUDE.md` no nombra `{valor}` (vocabulario de `extra_core`)"
    for valor in triage.VIA_FUENTE:
        assert f"`{valor}`" in doc, f"`CLAUDE.md` no nombra `{valor}` (vocabulario de `sources:`)"
    assert "EXTRA_CORE_VIA" in doc, \
        "la doc tiene que apuntar a la constante: sin el puntero, el próximo valor nuevo la deja vieja"


# ── #292 · todo `(#N)` que el repo cita apunta a un issue que EXISTE ─────────
ISSUES_JSON = RAIZ / "tools" / "issues.json"
# ⚠ ALCANCE DECLARADO (INV-40): sólo `#N` de dos dígitos para arriba. Por debajo el repo escribe
# ordinales en prosa —«regla #0», «contrato #1», «frente #3»— y separarlos de una referencia a
# issue no es decidible textualmente. La colisión que motivó el issue vive en el rango moderno.
REF_ISSUE_RE = re.compile(r"#(\d{2,4})\b")
REF_DIRS = ("scripts", "docs", ".claude/skills", "tests", "tools")
REF_SUFIJOS = (".py", ".md", ".yaml", ".yml")


def _refs_de_issue():
    """`{número: {archivos}}` de los `#N` que el repo cita. Excluye `docs/assets/` (los colores hex
    `#30363d` matchean) y `docs/internal/`, que no se versiona."""
    fuera = {}
    for raiz in REF_DIRS:
        base = RAIZ / raiz
        if not base.exists():
            continue
        for f in sorted(base.rglob("*")):
            if f.suffix not in REF_SUFIJOS or "assets" in f.parts or "internal" in f.parts:
                continue
            try:
                texto = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for m in REF_ISSUE_RE.finditer(texto):
                fuera.setdefault(int(m.group(1)), set()).add(str(f.relative_to(RAIZ)))
    for f in (RAIZ / "CLAUDE.md", RAIZ / "README.md"):
        if f.exists():
            for m in REF_ISSUE_RE.finditer(f.read_text(encoding="utf-8")):
                fuera.setdefault(int(m.group(1)), set()).add(f.name)
    return fuera


def test_todo_numero_de_issue_que_el_repo_cita_existe():
    """#292 — medido en vivo: un `(#N)` se escribió en el código ANTES de que el issue existiera, el
    siguiente issue se llevó ese número, y cinco referencias pasaron a resolver a otra cosa.
    `CLAUDE.md` declara el `(#N)` como el mecanismo de trazabilidad del framework y la regla de
    método nº 4 dice que un mapa que atribuye mal es peor que uno vacío: el `(#N)` colgado es el
    mapa vacío; el **colisionado**, el que atribuye mal.

    La lista está **cacheada y versionada** (`tools/issues.json`) para que el chequeo corra en CI,
    offline y sin token: `python tools/refresh_issues.py` al cerrar cada tanda."""
    assert ISSUES_JSON.exists(), (
        "falta tools/issues.json — refrescala con `python tools/refresh_issues.py`. Sin la caché "
        "este chequeo no puede correr, y un verde que nadie midió es el falso limpio de D-43.")
    datos = json.loads(ISSUES_JSON.read_text(encoding="utf-8"))
    conocidos = {i["number"] for i in datos["issues"]}
    colgadas = {n: sorted(fs) for n, fs in _refs_de_issue().items() if n not in conocidos}
    assert not colgadas, (
        "referencias `#N` a issues que NO existen (¿el número se escribió antes de crear el "
        f"issue?). Si el issue es nuevo, refrescá la caché:\n  " +
        "\n  ".join(f"#{n} ← {', '.join(fs)}" for n, fs in sorted(colgadas.items())))


def test_la_cache_de_issues_no_puede_estar_vacia():
    """Una caché vacía volvería VERDE el chequeo entero — el `(0)` que nadie midió (D-43)."""
    datos = json.loads(ISSUES_JSON.read_text(encoding="utf-8"))
    assert len(datos["issues"]) > 50 and datos.get("fetched")


def test_el_grafo_no_dibuja_como_estructura_lo_que_el_lint_no_cuenta():
    """#301 — #249 estableció que las aristas del `index.md` estampado **no significan nada** (no
    cuentan como link entrante). El grafo de Obsidian no lo sabía y las dibujaba igual, con
    `graph.json` versionado y sin filtro: medido, 50 de los 54 wikilinks del índice apuntan a
    papers y su sentido es «está en el top 50 por citas» — un artefacto del orden de una tabla
    dentro de la vista que existe para mostrar estructura (7 % de las aristas de la bóveda medida,
    entre índice y log).

    ⚠ No se arregla sacando los wikilinks: el índice se materializó (#237) **para** ser navegable.
    Es display, y por eso el filtro es un default que el usuario borra en dos clics."""
    graph = json.loads((RAIZ / "vault" / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
    for excluido in ("wiki/log.md", "wiki/index.md"):
        assert f"-path:{excluido}" in graph["search"], (
            f"el grafo dibuja {excluido} como estructura; #249 ya declaró que esas aristas no lo son")


# ── #339 · los flags de `tools/` y a quién se le atribuyen ──────────────────────────────────────


def test_el_universo_de_flags_incluye_los_de_tools():
    """`tools/` estaba fuera del barrido, así que sus siete flags vivían en `FLAGS_AJENOS` — que los
    EXIME, no los chequea. Con la lista de excepciones tapando el hueco, un typo en `--guardas`
    dentro de cualquier doc no lo cazaba nadie, y la lista se leía como si estuvieran validados."""
    universo = _universo_de_flags()
    assert {"--guardas", "--dirigida", "--trazabilidad", "--ratchet"} <= universo
    assert not (universo & FLAGS_AJENOS), ("un flag que algún argparse declara no puede estar "
                                           "además exento: la exención lo dejaría sin chequear")


def test_un_flag_inventado_de_tools_no_pasa():
    """La otra mitad: que el árbol nuevo se CHEQUEE, no sólo que se lea. Sin esto, incluir `tools/`
    se cumpliría agregando el directorio y no mirándolo."""
    declarados = _flags_declarados(RAIZ / "tools" / "mutar.py")
    assert "--guardas" in declarados and "--guardaz" not in declarados
    (script, resto), = comandos_de_la_linea("python tools/mutar.py --guardaz scripts/triage.py")
    assert script == RAIZ / "tools" / "mutar.py"
    assert [f for f in re.findall(r"(?<![\w-])(--[a-z][\w-]+)", resto)
            if f not in declarados] == ["--guardaz"]


def test_el_flag_que_sigue_a_una_ruta_ARGUMENTO_no_se_le_atribuye_a_ella():
    """El defecto: el patrón viejo se llevaba TODO lo que siguiera a cualquier ruta hasta el fin de
    línea, así que `python tools/mutar.py --guardas scripts/triage.py --solo main` reportaba
    «scripts/triage.py `--solo`» — un flag de `mutar` atribuido a `triage`. Se esquivó reordenando
    `docs/mediciones.md` (el flag antes de la ruta), pero la heurística seguía."""
    linea = "python tools/mutar.py --guardas scripts/triage.py --solo main"
    salida = list(comandos_de_la_linea(linea))
    assert [s.name for s, _ in salida] == ["mutar.py"], (
        "`scripts/triage.py` es un ARGUMENTO de mutar, no un comando: tratarlo como comando le "
        "cuelga los flags que vienen después")
    assert "--solo" in salida[0][1] and "--guardas" in salida[0][1]


def test_dos_comandos_encadenados_en_una_linea_no_se_mezclan():
    """La mitad que no se puede perder al arreglar lo de arriba: dos comandos reales en la misma
    línea siguen siendo dos, cada uno con SUS flags. Sin esto, «no atribuye de más» se cumpliría
    dejando de mirar el segundo comando."""
    salida = dict((s.name, r) for s, r in comandos_de_la_linea(
        "python scripts/lint.py --cierre && python tools/mutar.py --todo"))
    assert set(salida) == {"lint.py", "mutar.py"}
    assert "--cierre" in salida["lint.py"] and "--cierre" not in salida["mutar.py"]
    assert "--todo" in salida["mutar.py"] and "--todo" not in salida["lint.py"]


def test_la_doc_no_afirma_la_exencion_que_275_saco():
    """#363 — la red 5 valida que lo que la doc **nombra** exista; no que lo que **afirma sobre el
    comportamiento** siga siendo cierto. Y ahí se coló una premisa falsa que duró 59 versiones
    menores: `pdf_source: eprint` dejó de eximir del chequeo de cita textual en 1.111.0 (#275) y
    **9 lugares en 7 archivos** seguían diciendo que exime — uno de ellos el mensaje que el lint le
    IMPRIME al usuario, en la categoría de backlog más numerosa del reporte (94 hallazgos medidos
    en una bóveda real, cada uno arrastrando la premisa falsa en su propio texto).

    El mecanismo no fue envejecer: #296 **re-afirmó** la exención el mismo día en que #275 la había
    sacado, tomando la premisa de los issues sin releer el código que #275 acababa de dejar.

    ⚠ Una línea puede hablar de la exención para decir que **se retiró** —los registros fechados
    (`docs/mediciones.md`, `docs/contrato.md`) se **marcan**, no se reescriben—: por eso la salida
    es citar `#363`, que obliga a un acto consciente en vez de a un `grep` que se aprende a
    esquivar."""
    afirma = re.compile(r"(?:es (?:la|una) \*{0,2}exenci[óo]n|exime (?:adem[áa]s )?del chequeo|"
                        r"exenci[óo]n que apaga|apaga (?:adem[áa]s )?el chequeo)", re.I)
    culpables = []
    for f in sorted(RAIZ.rglob("*")):
        if f.suffix not in (".md", ".py") or not f.is_file():
            continue
        # `docs/internal/` no se versiona (informes de auditoría fechados, con su estado de ese día)
        if any(x in f.parts for x in (".git", "build", "outputs", "__pycache__", ".claude",
                                      "internal")):
            continue
        lineas = f.read_text(encoding="utf-8", errors="replace").splitlines()
        for n, ln in enumerate(lineas, 1):
            # ⚠ Por PAR de líneas, no por línea suelta: la prosa de este repo va hard-wrapped y la
            # frase cae partida —el hard wrap corta entre el campo y el verbo—, que es justo uno
            # de los 9 lugares que #363 midió. Un detector por línea suelta lo perdía.
            ctx = ln + "\n" + (lineas[n] if n < len(lineas) else "")
            # La escotilla se busca en una ventana MÁS ANCHA que la detección: la corrección de un
            # registro fechado se escribe al lado de la frase, no necesariamente en su misma línea.
            escotilla = "\n".join(lineas[max(0, n - 2):n + 1])
            if "eprint" in ctx and afirma.search(ctx) and "#363" not in escotilla:
                donde = f"{f.relative_to(RAIZ)}:{n}"
                if culpables[-1:] != [f"{f.relative_to(RAIZ)}:{n - 1}"]:
                    culpables.append(donde)   # la ventana solapa: no contar dos veces la misma frase
    assert not culpables, (
        "#363 — afirman una exención que el código no tiene: `pdf_source: eprint` dejó de "
        "eximir del chequeo de cita textual en 1.111.0 (#275), y hoy se exime SÓLO por "
        "`.txt` ausente y `fulltext_source: ocr` "
        f"(`lint._sources_for`):\n  " + "\n  ".join(culpables))
