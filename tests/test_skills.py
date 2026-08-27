"""Los `SKILL.md` como contrato: cadena única, progressive disclosure y honestidad del veredicto.

Cubre los ítems 1–4 del lote «skills». Todo lo que se asserta acá es **texto de archivos del
repo** — ni red, ni bóveda, ni símbolos de Python nuevos — porque un skill es el prompt que un
agente lee: si la prescripción no está escrita, no ocurre, y eso es decidible.

⚠ **Por qué los asserts no son `substring in texto` a secas.** Medido al escribir este archivo:
`test-hypothesis/SKILL.md` ya contiene la frase *"un veredicto sin evidencia que verify-citations no
puede chequear"* (sobre `bearing`, otro tema) y *"planteada, sin evidencia suficiente"* (la fila de
`abierta`). Un test que buscara `"sin evidencia"` en el archivo entero **pasa hoy en verde** sin que
el veredicto exista: sería andamiaje que no especifica nada. Por eso cada assert se acota al lugar
donde la afirmación **significa** algo (la enumeración de veredictos, el párrafo que lo condiciona,
la sección del paso).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"

# Ítem 1 — superficie de API FIJA por la spec: la referencia compartida de la cadena ADS vive acá,
# y los dos skills de ingesta la nombran por esta ruta literal.
CADENA_REF_REL = ".claude/skills/ingest-star/reference/cadena-ads.md"
CADENA_REF = RAIZ / CADENA_REF_REL


def _skill(nombre: str) -> str:
    return (SKILLS / nombre / "SKILL.md").read_text(encoding="utf-8")


def _skill_completo(nombre: str) -> str:
    """El skill **y su `reference/`**: lo que el agente puede llegar a leer siguiendo los punteros.

    Los contra-casos de «conserva lo que es suyo» preguntan si el material se **perdió**, no dónde
    quedó: el ítem 2 mueve casuística a `reference/` a propósito, así que buscar sólo en el cuerpo
    del `SKILL.md` haría fallar a un contra-caso por una migración que la spec pide."""
    partes = [_skill(nombre)]
    ref = SKILLS / nombre / "reference"
    if ref.is_dir():
        partes += [f.read_text(encoding="utf-8") for f in sorted(ref.glob("*.md"))]
    return "\n".join(partes)


def _seccion_paso(texto: str, patron: str) -> str:
    """El bloque de un paso numerado del skill (`3. **Extracción …**` hasta el paso siguiente).

    Acotar importa: un comando nombrado en el paso 5 no cumple lo que la spec pide del paso 3, y un
    assert sobre el archivo entero no distinguiría los dos casos."""
    lineas = texto.splitlines()
    inicio = next((i for i, ln in enumerate(lineas) if re.match(patron, ln)), None)
    assert inicio is not None, f"no se encontró el paso que matchea {patron!r} en el skill"
    for j in range(inicio + 1, len(lineas)):
        if re.match(r"^\d+[a-z]?\.\s", lineas[j]):
            return "\n".join(lineas[inicio:j])
    return "\n".join(lineas[inicio:])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Ítem 1 (#67) — la cadena ADS se describe en UN solo lugar
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# Hoy `ingest-star` e `ingest-theme` describen **cada uno** la misma cadena mecánica (rate limit de
# arXiv, cascada de `fetch_pdf`, residuo `missing_pdf.json`, `extra_core` como curación
# persistente). Dos copias de una prescripción es dos lugares donde corregirla y uno donde
# olvidarse: es el mismo modo de falla que `CLAUDE.md` ya nombra para el orden canónico de la
# cadena (*"puntero, no copia: no replicar la lista de scripts en docs/skills"*), que ahí se
# resolvió apuntando al header del orquestador.

def test_existe_la_referencia_compartida_de_la_cadena_ads():
    """El archivo único que describe la cadena mecánica de ADS, con las cinco piezas que hoy están
    duplicadas en los dos skills: guardia de expansión, `fetch_arxiv`, `fetch_pdf` con su fallback,
    el residuo `missing_pdf.json` y `extra_core` como curación persistente.

    Se chequea el **contenido** y no sólo la existencia porque un archivo vacío en esa ruta haría
    pasar el test y dejaría a los dos skills apuntando a la nada — el «mapa que atribuye mal es peor
    que uno vacío» de la regla de método #4, en su versión más barata de cometer."""
    assert CADENA_REF.exists(), f"falta {CADENA_REF_REL}"
    texto = CADENA_REF.read_text(encoding="utf-8")
    faltan = [pieza for pieza in ("guardia de expansión", "fetch_arxiv", "fetch_pdf",
                                  "missing_pdf.json", "extra_core")
              if pieza not in texto]
    assert faltan == [], f"la referencia de la cadena no describe: {faltan}"


def test_los_dos_skills_de_ingesta_apuntan_a_la_referencia_de_la_cadena():
    """`ingest-star` e `ingest-theme` **apuntan** por la ruta literal en vez de re-describir.

    La ruta es la de la spec y no se negocia: un puntero que cada skill escribe a su manera vuelve a
    ser una copia, nada más que de la ruta."""
    sin_puntero = [n for n in ("ingest-star", "ingest-theme") if CADENA_REF_REL not in _skill(n)]
    assert sin_puntero == [], (
        f"estos skills no nombran {CADENA_REF_REL}: {sin_puntero}")


# ── contra-casos del ítem 1: apuntar no es borrar ────────────────────────────────────────────────

def test_ingest_star_conserva_lo_que_es_suyo():
    """Lo específico de una estrella **no** está en la cadena compartida y no puede irse con ella:
    SIMBAD/NEA y el ground-truth, el rescate por glifo, el barrido full-text del paso 2b, la
    compuerta de triage y la matriz método×estrella.

    Es el contra-caso que distingue «factorizar» de «vaciar»: un refactor de documentación que se
    lleva por delante lo que el skill tenía de propio no se nota al leer el diff del archivo nuevo,
    se nota seis meses después cuando el agente no hace el paso."""
    texto = _skill_completo("ingest-star")
    marcadores = {
        "SIMBAD": r"SIMBAD",
        "ground-truth NEA": r"ground[_ -]truth",
        "rescate por glifo": r"glifo",
        "barrido full-text (2b)": r"--sweep",
        "compuerta de triage": r"triage",
        "matriz método×estrella": r"method_star|matriz",
    }
    faltan = [k for k, pat in marcadores.items() if not re.search(pat, texto, re.I)]
    assert faltan == [], f"`ingest-star` perdió material propio: {faltan}"


def test_ingest_theme_conserva_lo_que_es_suyo():
    """Lo propio del tema: la query Solr **co-diseñada con el usuario** (no traducida en silencio),
    el retro-tag por grep del corpus pre-existente y el modo off-ADS."""
    texto = _skill_completo("ingest-theme")
    marcadores = {
        "query Solr co-diseñada": r"[Cc]o-diseñar|co-diseñada",
        "retro-tag por grep": r"[Rr]etro-tag",
        "modo off-ADS": r"off-ADS",
    }
    faltan = [k for k, pat in marcadores.items() if not re.search(pat, texto)]
    assert faltan == [], f"`ingest-theme` perdió material propio: {faltan}"


@pytest.mark.parametrize("skill", ["ingest-star", "ingest-theme"])
def test_ningun_skill_de_ingesta_queda_sin_mencionar_la_cadena(skill):
    """«Apuntar no es borrar»: después de factorizar, el `SKILL.md` sigue diciendo que la cadena
    existe — o por el puntero a la referencia, o porque todavía la describe.

    Un skill que no la menciona de ninguna de las dos formas es un agente que no sabe que tiene que
    correrla; el test pasa hoy (la describe) y tiene que seguir pasando después (la apunta)."""
    texto = _skill(skill)
    menciona = CADENA_REF_REL in texto or ("fetch_arxiv" in texto and "fetch_pdf" in texto)
    assert menciona, f"`{skill}` no menciona la cadena ADS ni por puntero ni por descripción"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Ítem 2 (#65) — progressive disclosure
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# El cuerpo del `SKILL.md` guarda la **prescripción** (pasos, comandos, reglas duras en una línea) y
# la **casuística** (mediciones, números de issue, arqueología) baja a `reference/`, que se lee sólo
# cuando hace falta.

def _referencias_declaradas(skill: str) -> set[str]:
    """Los `reference/<archivo>.md` que el `SKILL.md` nombra, con el skill al que pertenecen.

    Dos formas conviven por diseño: la **relativa** (`reference/x.md`, dentro del propio skill) y la
    **absoluta desde la raíz** (`.claude/skills/<otro>/reference/x.md`), que es la que el ítem 1
    obliga a usar cuando el archivo vive en otro skill. Un matcher que no las distinga busca
    `cadena-ads.md` dentro de `ingest-theme/reference/` y falla por una ruta que la spec pide."""
    texto = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
    encontradas = set()
    for m in re.finditer(r"(?:\.claude/skills/([\w-]+)/)?(?<![\w/.-])reference/([\w.-]+\.md)",
                         texto):
        encontradas.add((m.group(1) or skill, m.group(2)))
    return encontradas


def _skills() -> list[str]:
    return sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))


def test_progressive_disclosure_bajo_casuistica_a_reference():
    """La spec habla de *los* `SKILL.md` grandes, en plural: el patrón tiene que existir en más de
    un skill, o no es un patrón sino el archivo suelto del ítem 1.

    ⚠ **Decisión de este test, anotada como pregunta abierta:** la spec no define un umbral de
    «grande» ni nombra qué skills tienen que partirse, así que acá se assertan **dos o más**, que es
    lo mínimo que hace verdadera la frase de la spec sin inventar una lista. Si el lote decide que
    sólo un skill se parte, este test es el lugar donde se discute — no se afloja en silencio."""
    con_reference = [s for s in _skills() if list((SKILLS / s / "reference").glob("*.md"))]
    assert len(con_reference) >= 2, (
        f"progressive disclosure sólo llegó a {con_reference or 'ningún skill'}")


def test_ningun_reference_md_queda_huerfano():
    """Un `reference/*.md` que **ningún** `SKILL.md` nombra es documentación que nadie va a abrir
    nunca: el costo de escribirla se pagó y el beneficio no llega.

    Se busca por substring (`reference/<archivo>.md`) y no por ruta relativa exacta, a propósito: la
    ruta literal del ítem 1 —`.claude/skills/ingest-star/reference/cadena-ads.md`— **contiene** esa
    forma, así que el mismo puntero satisface los dos contratos."""
    huerfanos = []
    for skill in _skills():
        propio = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
        ajenos = [(SKILLS / s / "SKILL.md").read_text(encoding="utf-8")
                  for s in _skills() if s != skill]
        for ref in sorted((SKILLS / skill / "reference").glob("*.md")):
            aguja = f"reference/{ref.name}"
            if aguja not in propio and not any(aguja in a for a in ajenos):
                huerfanos.append(f"{skill}/reference/{ref.name}")
    assert huerfanos == [], (
        "archivos de referencia que ningún SKILL.md nombra:\n  " + "\n  ".join(huerfanos))


def test_toda_referencia_que_nombra_un_skill_resuelve():
    """El dual del huérfano: un puntero a un `reference/` inexistente. Es el chequeo «F2» que este
    repo ya aplica a los comandos que la doc nombra (`test_docs_ejecutables`), extendido a los
    archivos de referencia — un skill que apunta a un archivo borrado no falla: el agente lo lee, no
    lo encuentra y hace otra cosa."""
    rotas = []
    for skill in _skills():
        for duenio, archivo in sorted(_referencias_declaradas(skill)):
            if not (SKILLS / duenio / "reference" / archivo).exists():
                rotas.append(f"{skill} → {duenio}/reference/{archivo}")
    assert rotas == [], "punteros a `reference/` que no resuelven:\n  " + "\n  ".join(rotas)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Ítem 3 (#61) — `test-hypothesis`: el veredicto «el corpus calla»
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# `no hay evidencia en el corpus` ≠ `el corpus la contradice`, exactamente como `verify-citations`
# distingue `no-soportada` (la fuente calla) de `contradice` (la fuente afirma lo contrario). Hoy el
# skill ofrece `sostiene / falla / parcial`: una hipótesis sobre la que el corpus no dice nada cae
# forzosamente en `falla`, que se lee como refutación.

def _lineas_de_veredicto() -> list[str]:
    """Las líneas donde el skill **enumera** los veredictos posibles.

    El ancla es `sostiene`, que es el único de los tres que no aparece como palabra suelta en otro
    contexto del archivo. Enumerar es donde la lista significa algo: el resto del skill puede decir
    «sin evidencia» en prosa sin que exista el veredicto (y hoy lo dice, dos veces)."""
    texto = _skill("test-hypothesis")
    return [ln for ln in texto.splitlines()
            if "sostiene" in ln and "falla" in ln]


def test_el_skill_enumera_sus_veredictos_en_algun_lado():
    """Andamiaje de los tres tests de abajo, explícito y con su propio rojo: si el skill deja de
    enumerar veredictos, quiero enterarme acá y no leer un `IndexError` adentro de otro test."""
    assert _lineas_de_veredicto(), (
        "no se encontró ninguna enumeración de veredictos en `test-hypothesis/SKILL.md`")


def test_sin_evidencia_es_un_veredicto_distinto_de_falla():
    """El corpus que **calla** no es el corpus que **contradice**. Colapsarlos convierte un hueco de
    cobertura —que se cierra ingestando— en una refutación, que es una afirmación sobre el mundo.

    Se exige en **todas** las enumeraciones (hoy son dos: el paso 3 y la sección `## Reporte`)
    porque una lista actualizada y otra no es peor que ninguna: el agente lee la que le queda más
    cerca."""
    incompletas = [ln for ln in _lineas_de_veredicto() if "sin evidencia" not in ln]
    assert incompletas == [], (
        "enumeraciones de veredicto sin `sin evidencia`:\n  " + "\n  ".join(incompletas))


def test_el_reporte_declara_el_sesgo_de_construccion():
    """«No hay evidencia» es una afirmación sobre **este** corpus, y este corpus no es una muestra
    del mundo: está filtrado por la lente del objetivo (`relevance.facets`) y por el triage.

    Es el mismo *afirmar de más* que D-34 ataca con el blockquote de alcance —que declara el
    universo *contado*—; esto declara el universo *sesgado*, que es la otra mitad y hoy no está en
    ninguna parte del skill (medido: ni «lente» ni «triage» aparecen en el archivo)."""
    texto = _skill("test-hypothesis")
    faltan = [k for k, pat in {"sesgo": r"sesgo",
                               "la lente del objetivo": r"lente",
                               "el triage": r"triage"}.items()
              if not re.search(pat, texto, re.I)]
    assert faltan == [], f"el skill no declara el sesgo de construcción; falta nombrar: {faltan}"


def test_sin_evidencia_solo_tras_agotar_la_escalera_de_matcheo():
    """El skill ya avisa que **un `grep` en 0 NO es una ausencia** hasta agotar la escalera de
    acortamiento (el `.txt` entrelaza columnas: 73 % del corpus). Sin atar el veredicto nuevo a esa
    escalera, `sin evidencia` se vuelve el nombre bonito de un falso negativo de `grep` — y acá el
    daño es peor que en `verify-citations`, porque **fabrica una ausencia** que sale al chat como
    conclusión y no deja rastro de que fue un artefacto.

    Lo que no agotó la escalera es *búsqueda no concluyente*, que **no** es lo mismo: el skill tiene
    que decirlo. Se busca por párrafo (no por archivo) para que la condición y el veredicto estén
    escritos juntos, que es la única forma en que un agente los lee juntos."""
    parrafos = re.split(r"\n\s*\n", _skill("test-hypothesis"))
    condicionan = [p for p in parrafos
                   if "sin evidencia" in p and re.search(r"agot|escalera", p, re.I)]
    assert condicionan, (
        "ningún párrafo condiciona `sin evidencia` a agotar la escalera de matcheo")
    assert any(re.search(r"no concluyente|no-concluyente|inconcluso", p, re.I)
               for p in condicionan), (
        "el skill no distingue `sin evidencia` de una búsqueda no concluyente")


def test_los_veredictos_que_ya_existen_no_se_eliminan():
    """Contra-caso: agregar un veredicto no es reemplazar los que hay. `sostiene`, `falla` y
    `parcial` siguen siendo emitibles — el corpus que contradice de verdad tiene que poder decirse."""
    lineas = _lineas_de_veredicto()
    assert lineas, "no se encontró la enumeración de veredictos"
    for termino in ("sostiene", "falla", "parcial"):
        assert any(termino in ln for ln in lineas), (
            f"el veredicto `{termino}` desapareció de la enumeración")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Ítem 4 (#62) — el paso 3 acota la extracción con los comandos que ya existen
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# «Leer los papers **clave**» no es un criterio: no dice cuántos, ni en qué orden, ni deja registro
# de qué se leyó. `triage.py` ya tiene las dos piezas —`--prioridad` para ordenar por facetas
# tocadas y `--extraccion subconjunto --reason` para declarar el recorte— y ningún skill las nombra
# juntas (`--prioridad` no aparece hoy en ningún `SKILL.md`).

@pytest.mark.parametrize("skill,patron", [
    ("ingest-star", r"^3\.\s+\*\*Extracción"),
    ("ingest-theme", r"^3\.\s+\*\*Extracción"),
])
def test_el_paso_3_nombra_como_ordenar_los_core(skill, patron):
    """Sin un orden declarado, «los papers clave» lo decide el agente en el momento y no queda
    escrito. `--prioridad` ordena los core por cuántas facetas del objetivo tocan (citas como
    desempate): es la pieza que convierte «leí los que me parecieron» en un recorte reproducible.

    El mismo tratamiento vale para `ingest-theme`, que tiene el mismo paso — por eso el test está
    parametrizado y no duplicado: un skill arreglado y el otro no es exactamente la asimetría que
    produce que el tema se ingeste peor que la estrella."""
    seccion = _seccion_paso(_skill(skill), patron)
    assert "--prioridad" in seccion, (
        f"el paso 3 de `{skill}` no nombra `python scripts/triage.py <slug> --prioridad`")


@pytest.mark.parametrize("skill,patron", [
    # `ingest-star` YA lo declara (D-13): acá es contra-caso —lo que el ítem 4 extiende no se puede
    # perder al extenderlo— y por eso va sin marca, en verde desde hoy.
    ("ingest-star", r"^3\.\s+\*\*Extracción"),
    ("ingest-theme", r"^3\.\s+\*\*Extracción"),
])
def test_el_paso_3_declara_el_recorte_con_su_criterio(skill, patron):
    """El recorte se **declara**, no se aplica implícito, y el `--reason` es obligatorio por el
    mismo motivo que en `--drop`: dentro de seis meses lo que sirve es el motivo, no la categoría.
    El lint ya lo reporta como *recorte de lectura sin declarar*, así que la red existe y lo que
    falta es que el skill nombre el comando que la cierra.

    ⚠ Este par **no está en el mismo estado en los dos skills**: `ingest-star` ya nombra
    `--extraccion subconjunto --reason` (D-13), así que su caso es contra-caso y pasa desde hoy;
    `ingest-theme` no lo nombra en absoluto —su paso 3 dice sólo «leer los papers clave del tema»—
    y por eso sólo ese caso nace `xfail`."""
    seccion = _seccion_paso(_skill(skill), patron)
    faltan = [t for t in ("--extraccion", "subconjunto", "--reason") if t not in seccion]
    assert faltan == [], f"el paso 3 de `{skill}` no declara el recorte; falta: {faltan}"


def test_ningun_skill_inventa_flags_de_triage():
    """Contra-caso: sólo se nombran los flags que `triage.py` declara. Un flag inventado en un skill
    es peor que uno faltante — el agente lo corre, argparse sale 2, y lo que el paso tenía que dejar
    registrado no se registra.

    Se lee el argparse real y no una lista copiada acá: una lista copiada es la misma duplicación
    que el ítem 1 va a sacar de los skills."""
    triage = (RAIZ / "scripts" / "triage.py").read_text(encoding="utf-8")
    declarados = set(re.findall(r"add_argument\(\s*[\"'](--[\w-]+)[\"']", triage))
    inventados = []
    for skill in _skills():
        texto = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
        for invocacion in re.findall(r"triage\.py[^\n`]*", texto):
            for flag in re.findall(r"--[\w-]+", invocacion):
                if flag not in declarados:
                    inventados.append(f"{skill}: {flag}")
    assert inventados == [], ("flags que `scripts/triage.py` no declara:\n  "
                              + "\n  ".join(sorted(set(inventados))))


# ── Ítem 5b del addendum: el skill que CONSUME `no_disputas` ─────────────────────────────────────
# ⚠ Estos tres tests existen porque el ítem 5b se implementó **sin test que lo cubriera** — el
# agente de implementación lo reportó y el árbitro no actuó. Un requisito de la spec que ningún
# test verifica es un deseo, no un contrato: el carril de persistencia puede quedar perfecto y el
# skill no consultarlo nunca, que es exactamente el defecto que #63 vino a cerrar.

def _find_contradictions() -> str:
    return (RAIZ / ".claude" / "skills" / "find-contradictions" / "SKILL.md").read_text(
        encoding="utf-8")


def test_el_skill_de_contradicciones_consulta_los_pares_ya_juzgados():
    """#63: el fan-out es caro —un subagente por par, leyendo DOS fulltext—. Si el skill no nombra
    `load_no_disputas`, cada auditoría del mismo eje vuelve a gastar en los mismos pares."""
    assert "load_no_disputas" in _find_contradictions()


def test_el_skill_excluye_las_disputas_ya_tagueadas():
    """La otra mitad de la exclusión: un desacuerdo que **ya** está en `disputes` está juzgado y
    resuelto, y volver a proponerlo es re-litigar lo aprobado."""
    t = _find_contradictions()
    assert "disputes" in t and any(
        v in t for v in ("excluye", "excluir", "excluyendo", "sin re-juzgar", "ya juzgados"))


def test_el_cierre_reporta_cuantos_pares_se_saltearon():
    """Un ahorro invisible no se puede auditar: si el barrido saltea 40 pares y no lo dice, no hay
    forma de distinguir «ya estaban juzgados» de «el barrido no los encontró» — la misma distinción
    que D-43 protege en todo el framework."""
    t = _find_contradictions()
    assert "saltear" in t or "salteados" in t or "saltearon" in t
