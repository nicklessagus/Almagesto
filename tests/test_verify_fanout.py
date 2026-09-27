"""`verify_fanout.py` — el generador del fan-out de verify sube a `scripts/` (#369).

El único eslabón de la cadena de verify sin herramienta era justo el que decide sobre qué corre el
gate: el reparto por fuente y el conteo se hacían a mano, y el `--esperados` de la barrera salía de
leer un «TOTAL 60 en 16 fuentes» y transcribirlo. Medido: 15 subagentes para 16 fuentes.
"""
from __future__ import annotations

import json
import re
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lib_blocks as lb          # noqa: E402
import verify_fanout as vf       # noqa: E402

NOTA = ("---\ntags: [concept]\n---\n\n# X\n\n"
        "La señal es estelar según «la actividad domina» [[2020A]].\n\n"
        "Y el período es de 34 días [[2020A]], mientras que [[2021B]] mide 36.\n")


def _nota(tmp_path):
    p = tmp_path / "x.md"
    p.write_text(NOTA, encoding="utf-8")
    return p


def test_escribe_un_prompt_por_FUENTE_y_el_manifiesto(tmp_path):
    out = tmp_path / "r1"
    m = vf.write_round(_nota(tmp_path), out)
    pares = lb.pairs_of(NOTA)
    assert m["pares"] == len(pares) and m["pares"] > 0
    assert set(m["fuentes"]) == {p.bibcode for p in pares}
    assert sorted(f.stem for f in (out / "prompts").glob("*.md")) == sorted(m["fuentes"])
    assert json.loads((out / vf.MANIFEST).read_text(encoding="utf-8")) == m


def test_cada_prompt_lleva_sus_pares_el_fence_y_la_salida(tmp_path):
    """Lo que hace que el reparto sea REPRODUCIBLE: cada prompt trae sus anclas tal cual, el fence
    generado (no tipeado) con la regla de claves cerradas (#365), y el path exacto que el subagente
    debe escribir — que es lo que la barrera va a buscar."""
    out = tmp_path / "r1"
    vf.write_round(_nota(tmp_path), out)
    texto = (out / "prompts" / "2020A.md").read_text(encoding="utf-8")
    anclas = [p.anchor for p in lb.pairs_of(NOTA) if p.bibcode == "2020A"]
    assert all(a in texto for a in anclas) and "Pares a juzgar: 2" in texto
    assert "```json" in texto and "NINGUNA OTRA" in texto
    assert (out / "2020A.json").as_posix() in texto
    assert vf.JUEZ in texto, "las reglas no se caen en el fan-out: el prompt manda leerlas"


def test_el_prompt_del_juez_no_lleva_arqueologia_de_mediciones(tmp_path):
    """docs/desarrollo.md § «Texto que lee un agente»: the judge prompt travels in every subagent
    of the fan-out, so it carries rules, not measurement dates or precision counts."""
    from conftest import PROMPT_ARCHAEOLOGY_RE
    out = tmp_path / "r1"
    vf.write_round(_nota(tmp_path), out)
    leidos = set()
    for f in (out / "prompts").glob("*.md"):
        texto = f.read_text(encoding="utf-8")
        assert not PROMPT_ARCHAEOLOGY_RE.findall(texto), f.name
        leidos |= set(re.findall(r"\.claude/skills/[\w./-]+\.md", texto))
    # #540 — the file the prompt SENDS the judge to read is prompt too: moving the rules there
    # took them out of this net, and the ratchet on skills only tolerates what was already there.
    # AUD-544 — and so is every file THAT file sends it to: the net follows the chain, not one hop.
    assert vf.JUEZ in leidos
    raiz = Path(__file__).resolve().parents[1]
    pendientes, vistos = sorted(leidos), set()
    while pendientes:
        rel = pendientes.pop()
        if rel in vistos:
            continue
        vistos.add(rel)
        texto = (raiz / rel).read_text(encoding="utf-8")
        assert not PROMPT_ARCHAEOLOGY_RE.findall(texto), rel
        pendientes += re.findall(r"\.claude/skills/[\w./-]+\.md", texto)
    assert ".claude/skills/verify-citations/reference/convenciones-fulltext.md" in vistos, \
        "juez.md manda a leer convenciones-fulltext.md: la red tiene que llegar"


def test_una_nota_sin_pares_no_es_un_cierre_en_verde(tmp_path, capsys):
    p = tmp_path / "vacia.md"
    p.write_text("---\ntags: [x]\n---\n\n# V\n\nSin citas.\n", encoding="utf-8")
    assert vf.main([str(p), "--out", str(tmp_path / "r1")]) == 1
    assert "0 pares" in capsys.readouterr().out


def test_el_manifiesto_es_lo_que_la_barrera_lee(tmp_path):
    """Los dos extremos de la cadena comparten el nombre del archivo, o el plan se escribe y nadie
    lo lee (regla de método 2)."""
    import check_verify_fanout as cvf
    assert vf.MANIFEST == cvf.MANIFEST


def test_la_ronda_ACOTADA_lleva_su_alcance_en_el_manifiesto(tmp_path):
    """#407 — #282 prescribe la ronda acotada y el generador sólo sabía rondas completas, así que la
    correcta no podía pasar la barrera («faltan 114»). El alcance viaja EN el manifiesto, al lado del
    total de la nota: `fuentes`/`pares` son lo que la barrera cuenta, `alcance` dice cómo se eligió
    y `nota_total` qué hay — una ronda acotada se lee como acotada, nunca como una completa que
    volvió corta (D-43)."""
    nota = _nota(tmp_path)
    todas = vf.write_round(nota, tmp_path / "full")
    assert todas["alcance"] == {"modo": "completa", "fuentes": sorted(todas["fuentes"])}
    assert todas["nota_total"] == {"pares": todas["pares"], "fuentes": len(todas["fuentes"])}

    una = sorted(todas["fuentes"])[0]
    m = vf.write_round(nota, tmp_path / "r2", fuentes=[una])
    assert set(m["fuentes"]) == {una} and m["alcance"] == {"modo": "fuentes", "fuentes": [una]}
    assert m["pares"] == todas["fuentes"][una] and m["nota_total"] == todas["nota_total"]
    assert sorted(p.stem for p in (tmp_path / "r2" / "prompts").glob("*.md")) == [una], \
        "sólo se generan los prompts del alcance"

    with pytest.raises(vf.ScopeError, match="no cita"):
        vf.write_round(nota, tmp_path / "r3", fuentes=["2099Nadie"])


def test_solo_nuevos_sin_hermano_es_la_ronda_completa_y_lo_DICE(tmp_path):
    """#407 — sin bloque evaluable `reverify_subset` manda TODOS los pares al subconjunto (D-43: eso
    no es «nada que re-verificar»), así que `--solo-nuevos` equivale a la ronda completa; el
    manifiesto conserva el modo pedido, que es lo que permite distinguirlo después."""
    nota = _nota(tmp_path)
    m = vf.write_round(nota, tmp_path / "r1", solo_nuevos=True)
    assert m["alcance"]["modo"] == "solo-nuevos"
    assert m["pares"] == m["nota_total"]["pares"]


def test_el_cli_acepta_el_alcance_y_rehusa_la_fuente_desconocida(tmp_path, capsys):
    nota = _nota(tmp_path)
    assert vf.main([str(nota), "--out", str(tmp_path / "r1"), "--fuentes", "2099Nadie"]) == 2
    assert "no cita" in capsys.readouterr().out
    una = sorted(vf.by_source(lb.pairs_of(nota.read_text(encoding="utf-8"))))[0]
    assert vf.main([str(nota), "--out", str(tmp_path / "r2"), "--fuentes", una]) == 0
    out = capsys.readouterr().out
    assert "alcance `fuentes`" in out and "FUERA" in out and "re-anclan" in out


def test_la_regex_de_arqueologia_caza_lo_que_declara():
    """AUD-550 — los dos usos de `PROMPT_ARCHAEOLOGY_RE` son asserts NEGATIVOS: una regex que no
    matchea nada los deja verdes. Control positivo: las formas que declara, y el localizador que
    declara dejar pasar."""
    from conftest import PROMPT_ARCHAEOLOGY_RE as R
    for forma in ("Medido el 2026-08-24", "medido sobre 40 pares", "Medido: 7 de 13",
                  "precisión **12/15", "cambió en 1.39.0"):
        assert R.search(forma), forma
    assert not R.search("p. 3 de 12"), "un «N de M» pelado es un localizador"
