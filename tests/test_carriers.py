"""`tools/carriers.py`: el gate que cierra la familia «fix a la instancia, no a la clase»."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import carriers as cr          # noqa: E402


def _repo(tmp_path: Path, **modulos) -> Path:
    """Un repo de juguete con `scripts/` y `tools/`, para probar el gate sin tocar el real."""
    for rel, fuente in modulos.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(fuente, encoding="utf-8")
    return tmp_path


def _decl(tmp_path: Path, **entrada) -> Path:
    base = {"issue": 1, "regla": "r", "funcion": "lib.regla", "patron": "PATRON", "consumidores": []}
    p = tmp_path / "portadores.yaml"
    p.write_text(yaml.safe_dump({"portadores": [{**base, **entrada}]}, allow_unicode=True),
                 encoding="utf-8")
    return p


LIB = "def regla(x):\n    return x\n"


def test_calls_distingue_la_LLAMADA_de_la_mencion(tmp_path):
    """⛔ Por AST, no por `in` sobre el texto: un `grep` contaría la mención en un comentario o en
    un docstring, que es exactamente lo que #347 midió — el comentario decía «delega en X» y no
    delegaba. Cuenta las dos formas de llamar, con el alias que cada archivo le puso al módulo."""
    assert cr.calls("import lib\nlib.regla(1)\n", "lib", "regla")
    assert cr.calls("import lib as cfg\ncfg.regla(1)\n", "lib", "regla"), "con alias"
    assert cr.calls("from lib import regla\nregla(1)\n", "lib", "regla"), "importado directo"
    assert not cr.calls("import lib\n# delega en lib.regla\n", "lib", "regla"), "la MENCIÓN no"
    assert not cr.calls('import lib\nx = "lib.regla(1)"\n', "lib", "regla"), "el string tampoco"
    assert not cr.calls("import otro\notro.regla(1)\n", "lib", "regla"), "otro módulo, no"
    assert not cr.calls("import lib\nlib.otra(1)\n", "lib", "regla"), "otra función, no"
    assert not cr.calls("def (:\n", "lib", "regla"), "un archivo que no parsea no afirma nada"


# ── #476 · la regla cuyo portador compartido es una CONSTANTE ──────────────────────────────────

TABLA = "TABLA = {'a': 1}\n\n\ndef otra(x):\n    return x\n"


def test_es_callable_separa_la_funcion_de_la_constante():
    """#476 — decide CÓMO se lleva la regla: una función, llamándola; una tabla o un vocabulario
    cerrado, leyéndolo. Un archivo que no parsea cae al criterio de siempre en vez de afirmar que
    el símbolo es una constante, que mandaría la entrada al camino equivocado."""
    assert cr.es_callable(LIB, "regla") is True
    assert cr.es_callable(TABLA, "TABLA") is False
    assert cr.es_callable(TABLA, "otra") is True
    assert cr.es_callable("def (:\n", "lo_que_sea") is True, "no parsea: no decide"


def test_reads_ve_la_LECTURA_de_una_constante_que_calls_no_puede_ver():
    """#476 — `cfg.TABLA` no es nunca un `ast.Call`, así que una regla cuyo portador compartido es
    una constante era **imposible de declarar**: el gate contestaba «declarado `usa` y NO llama», y
    las dos salidas que quedaban eran malas —llamar `fuera-de-alcance` a un portador real (una
    atribución falsa) o no declarar la regla—. Medido en el template: 32 constantes de `lib_config`
    leídas por dos o más módulos, **cero** declaradas."""
    assert not cr.calls("import lib\nx = lib.TABLA['a']\n", "lib", "TABLA"), "el bug de #476"
    assert cr.reads("import lib\nx = lib.TABLA['a']\n", "lib", "TABLA")
    assert cr.reads("import lib as cfg\nif k in cfg.TABLA:\n    pass\n", "lib", "TABLA"), "alias"
    assert cr.reads("from lib import TABLA\nx = TABLA['a']\n", "lib", "TABLA"), "directo"
    assert not cr.reads("import otro\nx = otro.TABLA\n", "lib", "TABLA"), "otro módulo, no"
    assert not cr.reads("import lib\nx = lib.OTRA\n", "lib", "TABLA"), "otra constante, no"


def test_carries_ramifica_por_lo_que_el_SIMBOLO_es_no_por_el_consumidor():
    """#476 — contar la lectura para TODO haría ruido: `ROOT` y `PAPERS` los toca medio repo, así
    que una regla de función empezaría a «tener» portadores que sólo la nombran, y eso desharía
    #347. La rama la decide el símbolo declarado, y por eso el veredicto de las reglas de función
    que ya cierran en 0 no se mueve."""
    lector = "import lib\nx = lib.regla\n"
    assert not cr.carries(lector, "lib", "regla", LIB), "función: mencionarla no es llevarla"
    assert cr.carries("import lib\nlib.regla(1)\n", "lib", "regla", LIB)
    assert cr.carries("import lib\nx = lib.TABLA['a']\n", "lib", "TABLA", TABLA), "constante: sí"


def test_la_regla_con_portador_CONSTANTE_se_puede_declarar(tmp_path):
    """#476 de punta a punta: el gate acepta la entrada cuyos consumidores LEEN la tabla, y sigue
    exigiéndola en la otra dirección — quien la lee sin estar declarado, bloquea."""
    root = _repo(tmp_path, **{"scripts/lib.py": TABLA,
                              "scripts/usa.py": "import lib\nx = lib.TABLA['a']\n"})
    decl = dict(funcion="lib.TABLA", patron="TABLA")
    _, h = cr.check(root, _decl(tmp_path, **decl))
    assert len(h) == 1 and "usa.py" in h[0], "el lector sin declarar bloquea"
    _, h = cr.check(root, _decl(tmp_path, **decl, consumidores=[
        {"modulo": "scripts/usa.py", "estado": "usa", "motivo": "lee la tabla"}]))
    assert h == [], "declarado, cierra"


def test_el_portador_SIN_DECLARAR_bloquea(tmp_path):
    """La mitad que cierra la familia: alguien llama a la implementación única y nadie lo declaró."""
    root = _repo(tmp_path, **{"scripts/lib.py": LIB,
                              "scripts/usa.py": "import lib\nlib.regla(1)\n"})
    _, h = cr.check(root, _decl(tmp_path))
    assert len(h) == 1 and "LLAMA" in h[0] and "usa.py" in h[0]
    _, h = cr.check(root, _decl(tmp_path, consumidores=[
        {"modulo": "scripts/usa.py", "estado": "usa", "motivo": "m"}]))
    assert h == []


def test_el_declarado_que_NO_llama_bloquea(tmp_path):
    """#347 textual: un comentario que dice «delega en X» no delega. Es la dirección que el gate
    tiene y que un `grep` no puede tener."""
    root = _repo(tmp_path, **{"scripts/lib.py": LIB,
                              "scripts/finge.py": "import lib\n# delega en lib.regla\n"})
    _, h = cr.check(root, _decl(tmp_path, consumidores=[
        {"modulo": "scripts/finge.py", "estado": "usa", "motivo": "m"}]))
    assert len(h) == 1 and "NO llama" in h[0]


def test_el_que_MATCHEA_el_patron_y_nadie_declaro_bloquea(tmp_path):
    """El corazón del gate: el gemelo que quedó igual. El `patron` es la relación estructural
    escrita, y es lo único que hace que el barrido termine donde termina la CLASE y no donde el
    agente dejó de mirar («2 de 4», «dos más», «del mismo barrido»)."""
    root = _repo(tmp_path, **{"scripts/lib.py": LIB,
                              "scripts/gemelo.py": "x = 'PATRON aca'\n"})
    _, h = cr.check(root, _decl(tmp_path))
    assert len(h) == 1 and "gemelo.py" in h[0] and "gemelo que quedó igual" in h[0]
    # las dos salidas legítimas, y sólo ésas
    _, h = cr.check(root, _decl(tmp_path, consumidores=[
        {"modulo": "scripts/gemelo.py", "estado": "fuera-de-alcance", "motivo": "no aplica porque…"}]))
    assert h == []
    _, h = cr.check(root, _decl(tmp_path, consumidores=[
        {"modulo": "scripts/gemelo.py", "estado": "fuera-de-alcance", "motivo": "  "}]))
    assert len(h) == 1 and "sin `motivo`" in h[0], "un `fuera-de-alcance` mudo no cierra nada"
    # …y el `usa` NO necesita motivo: lo que declara es que la llamada existe, y eso se verifica
    # contra el código; el motivo obligatorio es del NO, que es el que nadie puede chequear
    root2 = _repo(tmp_path / "b", **{"scripts/lib.py": LIB,
                                     "scripts/usa.py": "import lib\nlib.regla(1)\n"})
    _, h = cr.check(root2, _decl(tmp_path, consumidores=[
        {"modulo": "scripts/usa.py", "estado": "usa"}]))
    assert h == []
    _, h = cr.check(root, _decl(tmp_path, consumidores=[
        {"modulo": "scripts/gemelo.py", "estado": "inventado", "motivo": "m"}]))
    assert len(h) == 1 and "vocabulario" in h[0]


def test_el_declarado_fuera_de_alcance_que_SI_llama_bloquea(tmp_path):
    """La contradicción al revés: la declaración dice que no aplica y el código la llama igual."""
    root = _repo(tmp_path, **{"scripts/lib.py": LIB,
                              "scripts/usa.py": "import lib\nlib.regla(1)\n"})
    _, h = cr.check(root, _decl(tmp_path, consumidores=[
        {"modulo": "scripts/usa.py", "estado": "fuera-de-alcance", "motivo": "m"}]))
    assert len(h) == 1 and "sin embargo llama" in h[0]


def test_la_entrada_incompleta_o_que_apunta_a_la_nada_bloquea(tmp_path):
    """Los cuatro campos son obligatorios porque sin ellos la entrada no dice qué se cerró ni cómo
    se reconoce a un portador; y la `funcion` que ya no existe delata un renombre que dejó la
    declaración hablando de otra cosa (un mapa que atribuye mal es peor que uno vacío)."""
    root = _repo(tmp_path, **{"scripts/lib.py": LIB})
    for campo in ("issue", "regla", "funcion", "patron"):
        _, h = cr.check(root, _decl(tmp_path, **{campo: ""}))
        assert any(f"falta `{campo}`" in x for x in h), campo
    _, h = cr.check(root, _decl(tmp_path, funcion="lib.no_existe"))
    assert len(h) == 1 and "no existe" in h[0], "el módulo está y el símbolo no"
    _, h = cr.check(root, _decl(tmp_path, funcion="modulo_fantasma.regla"))
    assert len(h) == 1 and "no existe" in h[0], "…y el módulo entero que no está"
    _, h = cr.check(root, _decl(tmp_path, funcion="sin_punto"))
    assert len(h) == 1 and "modulo.simbolo" in h[0]
    _, h = cr.check(root, _decl(tmp_path, patron="(sin cerrar"))
    assert len(h) == 1 and "no compila" in h[0]
    _, h = cr.check(root, _decl(tmp_path, consumidores=[
        {"modulo": "scripts/fantasma.py", "estado": "usa", "motivo": "m"}]))
    assert len(h) == 1 and "no existe" in h[0]


def test_sin_declaracion_es_NO_EVALUADO_no_un_verde(tmp_path, capsys):
    """D-43 en el propio gate: un archivo que no se pudo leer no es «cero portadores sin declarar»."""
    with pytest.raises(cr.DeclaracionIlegible):
        cr.load(tmp_path / "no_existe.yaml")
    roto = tmp_path / "roto.yaml"
    roto.write_text("a: [1,\nb: : :\n", encoding="utf-8")
    with pytest.raises(cr.DeclaracionIlegible):
        cr.load(roto)
    sin_lista = tmp_path / "sin.yaml"
    sin_lista.write_text("otra_cosa: 1\n", encoding="utf-8")
    with pytest.raises(cr.DeclaracionIlegible):
        cr.load(sin_lista)


def test_propose_enumera_para_que_la_lista_no_se_escriba_de_MEMORIA(tmp_path, capsys):
    """La lista no se escribe de memoria — es el modo de falla que este repo persigue en todos
    lados. `llaman` sale del AST; `sospechosos`, del patrón. Y sin `--patron` se DICE que sólo se
    está viendo la mitad que nunca fue el problema."""
    # ⚠ el dueño MATCHEA su propio patrón —`lib_config` define `FULLTEXT`, por caso— así que sin
    # exceptuarlo se propondría a sí mismo como sospechoso en cada regla del repo
    root = _repo(tmp_path, **{"scripts/lib.py": LIB + "x = 'PATRON'\n",
                              "scripts/usa.py": "import lib\nlib.regla(1)\n",
                              "scripts/gemelo.py": "x = 'PATRON'\n",
                              "scripts/ajeno.py": "x = 1\n"})
    llaman, firmados, sosp = cr.propose("lib.regla", "PATRON", root, tmp_path / "no-existe.yaml")
    assert llaman == ["scripts/usa.py"] and sosp == ["scripts/gemelo.py"] and firmados == {}
    assert "scripts/lib.py" not in llaman + sosp, "el DUEÑO de la regla no es portador de sí mismo"
    assert cr.propose("lib.regla", None, root)[2] == [], "sin patrón no se inventan sospechosos"


def test_482_propose_SEPARA_el_firmado_fuera_de_alcance_del_que_nadie_declaro(tmp_path, capsys):
    """#482: el bloque que se pega en cada issue mostraba igual al consumidor ya firmado
    `fuera-de-alcance` y al que nadie miró. Tres listas: el firmado lleva su motivo y no es deuda;
    el `sin declarar` es el único que pide acción, y vacío lo DICE (D-43)."""
    root = _repo(tmp_path, **{"scripts/lib.py": LIB + "def otra(x):\n    return x\n",
                              "scripts/firmado.py": "x = 'PATRON'\n",
                              "scripts/deuda.py": "x = 'PATRON'\n"})
    decl = _decl(tmp_path, consumidores=[
        {"modulo": "scripts/firmado.py", "estado": "fuera-de-alcance", "motivo": "lee otra cosa"}])
    llaman, firmados, sosp = cr.propose("lib.regla", "PATRON", root, decl)
    assert llaman == [] and firmados == {"scripts/firmado.py": "lee otra cosa"}
    assert sosp == ["scripts/deuda.py"]
    # otra regla con la misma firma NO la hereda: la firma es por `funcion`
    assert cr.propose("lib.otra", "PATRON", root, decl)[1] == {}
    # la declaración ilegible no tumba el reporte (el gate es --check), y todo queda «sin declarar»
    (tmp_path / "rota.yaml").write_text(": [", encoding="utf-8")
    assert cr.propose("lib.regla", "PATRON", root, tmp_path / "rota.yaml")[2] == [
        "scripts/deuda.py", "scripts/firmado.py"]
    # y el reporte: el firmado con su motivo, el otro bajo «sin declarar»
    import re as _re
    monkey = pytest.MonkeyPatch()
    monkey.setattr(cr, "propose", lambda ref, pat, **kw: ([], {"scripts/firmado.py": "lee otra cosa"},
                                                          ["scripts/deuda.py"]))
    try:
        assert cr.main(["--propose", "lib.regla", "--patron", "PATRON"]) == 0
    finally:
        monkey.undo()
    out = capsys.readouterr().out
    assert _re.search(r"firmados `fuera-de-alcance` \(1, con motivo\):\n  scripts/firmado.py — lee otra cosa", out)
    assert _re.search(r"\(1 sin declarar\).*\n  scripts/deuda.py", out)
    monkey.setattr(cr, "propose", lambda ref, pat, **kw: ([], {}, []))
    try:
        cr.main(["--propose", "lib.regla", "--patron", "PATRON"])
    finally:
        monkey.undo()
    assert "(0 sin declarar)" in capsys.readouterr().out, "vacío se dice, no desaparece (D-43)"


def test_la_declaracion_VIGENTE_del_repo_cierra():
    """⛔ El gate de verdad: `tools/portadores.yaml` contra el código de este repo. Es lo que hace
    que un issue con portadores no se pueda cerrar sin haberlos enumerado — si esto se pone rojo,
    alguien tocó una regla y dejó un portador sin declarar.

    @inv INV-154"""
    entradas, hallazgos = cr.check()
    assert entradas, "sin entradas el gate no afirma nada (D-43)"
    assert hallazgos == [], "\n".join(hallazgos)


def test_calls_no_confunde_lo_que_SE_PARECE_a_una_llamada(tmp_path):
    """Las cinco guardas del reconocedor, cada una con el caso que la distingue. Un falso positivo
    acá manda a declarar un portador que no existe; un falso negativo deja pasar al gemelo — los
    dos rompen el gate en la dirección que más duele."""
    assert not cr.calls("from otro import regla\nregla(1)\n", "lib", "regla"), \
        "importado de OTRO módulo: no es esta regla"
    assert not cr.calls("from lib import otra\notra(1)\n", "lib", "regla"), \
        "importado del módulo correcto, símbolo equivocado"
    assert not cr.calls("import lib\nregla(1)\n", "lib", "regla"), \
        "llamada suelta sin `from lib import`: es otra `regla` del archivo"
    assert not cr.calls("import lib\nx.regla(1)\n", "lib", "regla"), \
        "atributo de OTRA cosa que no es el módulo importado"
    assert not cr.calls("import lib\nlib.sub.regla(1)\n", "lib", "regla"), \
        "atributo anidado: no es `lib.regla`"
    assert cr.calls("import lib as l, os\nl.regla(1)\n", "lib", "regla"), "import múltiple"
    # con el símbolo importado DIRECTO, las dos guardas de esa rama: que la llamada sea a un nombre
    # (y no a un atributo) y que el nombre sea el del símbolo
    assert not cr.calls("from lib import regla\notra(1)\n", "lib", "regla"), "otro nombre"
    assert not cr.calls("from lib import regla\nx.regla(1)\n", "lib", "regla"), \
        "un ATRIBUTO llamado igual sobre otra cosa no es el símbolo importado"


def test_modulos_recorre_los_dos_arboles_y_saltea_el_cache(tmp_path):
    """La población del gate. Un árbol que no existe se saltea (un clon puede no tener `tools/`) y
    `__pycache__` no es código: contarlo metería un `.py` compilado como portador."""
    root = _repo(tmp_path, **{"scripts/a.py": "x = 1\n",
                              "tools/b.py": "y = 2\n",
                              "scripts/__pycache__/a.py": "z = 3\n"})
    assert sorted(cr.source_modules(root)) == ["scripts/a.py", "tools/b.py"]
    assert cr.source_modules(tmp_path / "vacio") == {}, "sin árboles no hay población, y no revienta"

    # ⚠ Declarado: el `if not base.is_dir(): continue` sobrevive a `mutar --guardas` y va a seguir
    # sobreviviendo — `Path(<inexistente>).rglob()` devuelve vacío y no levanta, así que sacarlo da
    # el mismo resultado (red 8). Se anota en vez de inventarle un test que probaría otra cosa.


def test_la_entrada_que_no_es_un_mapa_y_el_consumidor_que_no_es_un_mapa(tmp_path):
    """Forma inválida en los dos niveles: se reporta y se sigue, en vez de tumbar el gate entero
    con un `.get` sobre un string — misma política que el resto del repo ante una config rara."""
    root = _repo(tmp_path, **{"scripts/lib.py": LIB})
    p = tmp_path / "raro.yaml"
    p.write_text(yaml.safe_dump({"portadores": ["no soy un mapa"]}), encoding="utf-8")
    _, h = cr.check(root, p)
    assert h and all("falta `" in x for x in h), h
    _, h = cr.check(root, _decl(tmp_path, consumidores=["no soy un mapa"]))
    assert len(h) == 1 and "no es un mapa" in h[0]


# ── 4. el CLI: sus tres salidas piden cosas distintas ────────────────────────────────────────────

def test_main_sobre_el_repo_REAL_sale_0_y_declara_su_poblacion(capsys):
    """El comando que corre tier 0, end to end. Declara sobre cuántos módulos miró (INV-40): un
    `portadores: 2` sin denominador no distingue «se barrieron los dos árboles» de «no se barrió
    nada»."""
    assert cr.main([]) == 0
    linea = capsys.readouterr().out.splitlines()[0]
    assert linea.startswith("portadores: ") and "módulo(s) de scripts/tools" in linea


def test_main_con_hallazgos_sale_1_y_los_NOMBRA(monkeypatch, capsys):
    """Un gate que sale ≠ 0 sin decir cuál portador falta manda a leer el YAML entero."""
    monkeypatch.setattr(cr, "check", lambda: ([{"issue": 1}], ["scripts/x.py LLAMA a lib.regla"]))
    assert cr.main(["--check"]) == 1
    out = capsys.readouterr().out
    assert "scripts/x.py LLAMA" in out and "1 hallazgo(s)" in out


def test_main_con_la_declaracion_ILEGIBLE_sale_2_y_no_0(monkeypatch, capsys):
    """D-43: un chequeo que no pudo correr lo DICE. Salir 0 con el YAML roto es el falso limpio
    exacto que este gate existe para no producir — y el único estado donde la ausencia de hallazgos
    no significa nada."""
    def _revienta():
        raise cr.DeclaracionIlegible("portadores.yaml no parsea")
    monkeypatch.setattr(cr, "check", _revienta)
    assert cr.main(["--check"]) == 2
    assert "no evaluado" in capsys.readouterr().err


def test_main_propose_sin_patron_AVISA_que_falta_la_mitad(monkeypatch, capsys):
    """Sin `--patron` sólo se enumera quién YA llama, que es la mitad que nunca fue el problema: el
    portador que falta es, por definición, el que no llama a la implementación única."""
    monkeypatch.setattr(cr, "propose", lambda ref, pat, **kw: (["scripts/a.py"], {}, ["scripts/b.py"]))
    assert cr.main(["--propose", "lib.regla"]) == 0
    out = capsys.readouterr().out
    assert "scripts/a.py" in out and "scripts/b.py" not in out and "sin `--patron`" in out
    assert cr.main(["--propose", "lib.regla", "--patron", "RE"]) == 0
    out = capsys.readouterr().out
    assert "scripts/b.py" in out and "fuera-de-alcance" in out


def test_454_el_RE_EXPORT_cuenta_como_simbolo_expuesto(tmp_path):
    """⛔ #454 — `lib_config` re-exporta todo nombre público de `lib_quotes` a propósito (AUD-306),
    así que los consumidores importan `lib_config as cfg` y llaman `cfg.quote_verdict(...)`. Sin
    contar el `ImportFrom`, la regla cuya implementación vive en `lib_quotes` **no se podía
    declarar**: por el módulo real el gate decía «no llama» (nadie importa `lib_quotes`) y por el de
    la fachada, «no existe». Un gate que rehúsa las dos formas de la misma verdad deja la regla sin
    declarar, que es lo que esta herramienta existe para impedir."""
    assert cr.existe("def f():\n    pass\n", "f")
    assert cr.existe("F = 1\n", "F")
    assert cr.existe("from lib_quotes import quote_verdict\n", "quote_verdict"), "el re-export"
    assert cr.existe("from lib_quotes import quote_verdict as qv\n", "qv"), "y bajo su alias"
    assert not cr.existe("from lib_quotes import otra_cosa\n", "quote_verdict")
    assert not cr.existe("# quote_verdict en un comentario\n", "quote_verdict")


def test_AUD424_propose_con_simbolo_o_modulo_INEXISTENTE_rehusa_como_check(tmp_path, capsys):
    """AUD-424: un typo daba «0 portadores» rc 0, que se lee como enumeración hecha (D-43). `check`
    ya rehusaba el mismo caso; `--propose` rehúsa igual."""
    root = _repo(tmp_path, **{"scripts/lib.py": LIB, "scripts/usa.py": "import lib\nlib.regla(1)\n"})
    for ref in ("lib.no_existe", "lbi.regla", "sin_punto"):
        with pytest.raises(ValueError):
            cr.propose(ref, "PATRON", root, tmp_path / "no-existe.yaml")
    assert cr.main(["--propose", "lib_config.no_existe_xyz", "--patron", "zzz"]) == 2
    assert "no existe" in capsys.readouterr().err


def test_AUD415_propose_cruza_el_RE_EXPORT_de_la_fachada(tmp_path):
    """AUD-415: la regla vive en `lib_quotes` y `lib_config` la re-exporta (AUD-306); los
    consumidores llaman `cfg.X`. `--propose lib_quotes.X` daba 0 llamadores."""
    root = _repo(tmp_path, **{
        "scripts/lib_quotes.py": LIB,
        "scripts/lib_config.py": "from lib_quotes import regla  # noqa\n",
        "scripts/usa.py": "import lib_config as cfg\ncfg.regla(1)\n",
        "scripts/ajeno.py": "import lib_config as cfg\ncfg.otra(1)\n"})
    llaman, _, _ = cr.propose("lib_quotes.regla", None, root, tmp_path / "no-existe.yaml")
    assert llaman == ["scripts/usa.py"]


def _fachada(tmp_path, lib_quotes=LIB, fachada="from lib_quotes import regla  # noqa\n", **mas):
    return _repo(tmp_path, **{"scripts/lib_quotes.py": lib_quotes, "scripts/lib_config.py": fachada,
                              "scripts/usa.py": "import lib_config as cfg\ncfg.regla(1)\n", **mas})


def test_508_check_resuelve_el_RE_EXPORT_en_las_DOS_direcciones(tmp_path):
    """⛔ #508 — `--propose` cruzaba el re-export (AUD-415) y `--check` no: firmada por el módulo
    DEFINIDOR, la regla decía «declarado `usa` y NO llama» sobre quien llama `cfg.regla`, así que
    #500 se firmó por la fachada como parche. Un símbolo y su re-export son la MISMA función."""
    root = _fachada(tmp_path, **{"scripts/directo.py": "import lib_quotes\nlib_quotes.regla(1)\n"})
    usa = [{"modulo": "scripts/usa.py", "estado": "usa"},
           {"modulo": "scripts/directo.py", "estado": "usa"}]
    for ref in ("lib_quotes.regla", "lib_config.regla"):
        _, hallazgos = cr.check(root, _decl(tmp_path, funcion=ref, consumidores=usa))
        assert hallazgos == [], (ref, hallazgos)
    # y el que llama por la fachada sin declarar sigue bloqueando
    _, hallazgos = cr.check(root, _decl(tmp_path, funcion="lib_quotes.regla", consumidores=usa[1:]))
    assert any("scripts/usa.py" in h and "LLAMA" in h for h in hallazgos)


def test_508_el_re_export_con_ALIAS_se_resuelve(tmp_path):
    root = _fachada(tmp_path, fachada="from lib_quotes import regla as regla2  # noqa\n",
                    **{"scripts/usa.py": "import lib_config as cfg\ncfg.regla2(1)\n"})
    nombres, definidor = cr.names_of(cr.source_modules(root), "lib_quotes", "regla")
    assert nombres == {("lib_quotes", "regla"), ("lib_config", "regla2")}
    assert definidor == LIB
    assert cr.propose("lib_quotes.regla", None, root, tmp_path / "x.yaml")[0] == ["scripts/usa.py"]


def test_508_si_es_CONSTANTE_lo_decide_el_DEFINIDOR_no_la_fachada(tmp_path):
    """Sobre la fachada `es_callable` contesta «callable» para todo re-export: una constante
    re-exportada se llevaba LLAMÁNDOLA, y su lector era invisible."""
    root = _fachada(tmp_path, lib_quotes="TABLA = (1, 2)\n",
                    fachada="from lib_quotes import TABLA  # noqa\n",
                    **{"scripts/usa.py": "import lib_config as cfg\nx = cfg.TABLA\n"})
    _, hallazgos = cr.check(root, _decl(tmp_path, funcion="lib_config.TABLA",
                                        consumidores=[{"modulo": "scripts/usa.py", "estado": "usa"}]))
    assert hallazgos == []


def test_508_propose_por_el_definidor_ve_lo_FIRMADO_por_la_fachada(tmp_path):
    root = _fachada(tmp_path, **{"scripts/otro.py": "PATRON = 1\n"})
    decl = _decl(tmp_path, funcion="lib_config.regla", consumidores=[
        {"modulo": "scripts/otro.py", "estado": "fuera-de-alcance", "motivo": "m"}])
    _, firmados, sin_declarar = cr.propose("lib_quotes.regla", "PATRON", root, decl)
    assert firmados == {"scripts/otro.py": "m"} and sin_declarar == []
