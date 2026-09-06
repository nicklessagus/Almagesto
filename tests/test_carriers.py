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
    llaman, sosp = cr.propose("lib.regla", "PATRON", root)
    assert llaman == ["scripts/usa.py"] and sosp == ["scripts/gemelo.py"]
    assert "scripts/lib.py" not in llaman + sosp, "el DUEÑO de la regla no es portador de sí mismo"
    assert cr.propose("lib.regla", None, root)[1] == [], "sin patrón no se inventan sospechosos"


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
    monkeypatch.setattr(cr, "propose", lambda ref, pat, **kw: (["scripts/a.py"], ["scripts/b.py"]))
    assert cr.main(["--propose", "lib.regla"]) == 0
    out = capsys.readouterr().out
    assert "scripts/a.py" in out and "scripts/b.py" not in out and "sin `--patron`" in out
    assert cr.main(["--propose", "lib.regla", "--patron", "RE"]) == 0
    out = capsys.readouterr().out
    assert "scripts/b.py" in out and "fuera-de-alcance" in out
