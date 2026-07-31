"""bench_verify: extracción de pares, siembra determinista por rotación, puntaje."""
import json
import sys

import pytest

import bench_verify as bv
import lib_config as cfg
from conftest import mk_note


def seed_fulltext(toy_vault, *bibcodes):
    d = toy_vault.FULLTEXT / "test_star"
    d.mkdir(parents=True, exist_ok=True)
    for b in bibcodes:
        (d / f"{b}.txt").write_text(f"texto legible del paper {b} " * 20, encoding="utf-8")


def seed_notes(toy_vault):
    mk_note(toy_vault.CONCEPTS / "methods", "nota-a", {"tags": ["methods"]},
            "La pendiente cromática medida es -2.6 según [[2020aaaA...1..1A]].\n"
            "- El período de rotación es 34 d [[2020bbbB...1..1B]].\n"
            "> disclaimer en blockquote citando [[2020aaaA...1..1A]] — excluido\n"
            "[[2020aaaA...1..1A]]\n"                       # link pelado: no es afirmación
            "```dataview\nTABLE [[2020bbbB...1..1B]]\n```\n"
            "Cita sin fulltext en el corpus [[1999cccC...1..1C]].\n"
            "\n## Verificación de citas (2026-01-01)\n"
            "| claim viejo | [[2020bbbB...1..1B]] | soportada | 9 | ... |\n")
    mk_note(toy_vault.QUERIES, "query-x", {"tags": ["query"]},
            "El índice CRX correlaciona con la actividad [[2020aaaA...1..1A]] y "
            "también lo reporta [[2020bbbB...1..1B]].\n")


def run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["bench_verify.py", *argv])
    return bv.main()


# ── seed ─────────────────────────────────────────────────────────────────────

def test_seed_extrae_siembra_y_es_determinista(toy_vault, monkeypatch):
    seed_fulltext(toy_vault, "2020aaaA...1..1A", "2020bbbB...1..1B")
    seed_notes(toy_vault)
    assert run(monkeypatch, "seed") == 0
    bench = cfg.ROOT / "build" / "verify_bench" / "bench.json"
    first = bench.read_text(encoding="utf-8")
    data = json.loads(first)
    real = [p for p in data["pairs"] if p["label"] == "real"]
    sown = [p for p in data["pairs"] if p["label"] == "sembrada"]
    # 4 pares reales: 2 de nota-a + 2 de query-x (una afirmación con dos citas = dos pares);
    # ni el blockquote, ni el link pelado, ni el dataview, ni el bloque de verificación,
    # ni la cita sin fulltext.
    assert data["n_real"] == 4 and len(real) == 4
    claims = "\n".join(p["claim"] for p in real)
    assert "pendiente cromática" in claims and "CRX" in claims
    assert "disclaimer" not in claims and "claim viejo" not in claims
    assert all(p["bibcode"] != "1999cccC...1..1C" for p in real)
    # sembradas: sólo las afirmaciones de nota-a (las de query-x citan A y B a la vez → cubren
    # todo el pool, no admiten cruce FALSO); bibcode rotado ∉ los citados por esa afirmación.
    assert len(sown) == 2
    assert all(s["note"] == "nota-a" for s in sown)
    cited_by_line = {}
    for p in real:
        cited_by_line.setdefault((p["note"], p["line"]), set()).add(p["bibcode"])
    for s in sown:
        assert s["bibcode"] not in cited_by_line[(s["note"], s["line"])]
        assert s["fulltext"].endswith(f"{s['bibcode']}.txt")
        assert s["verdict"] is None
    # determinista byte a byte
    run(monkeypatch, "seed")
    assert bench.read_text(encoding="utf-8") == first


def test_seed_rotacion_nunca_el_original(toy_vault, monkeypatch):
    ft = {"2020aaaA...1..1A": "a.txt", "2020bbbB...1..1B": "b.txt", "2020cccC...1..1C": "c.txt"}
    real = [{"note": "n", "line": 1, "claim": f"afirmación {b}", "bibcode": b, "fulltext": ft[b]}
            for b in ft]
    for s, r in zip(bv.seed_pairs(real, ft), real):
        assert s["bibcode"] != r["bibcode"]


def test_seed_sin_material_sale_amigable(toy_vault, monkeypatch):
    with pytest.raises(SystemExit, match="bóveda ya poblada"):
        run(monkeypatch, "seed")
    # con pares pero un solo bibcode no hay cruce posible
    seed_fulltext(toy_vault, "2020aaaA...1..1A")
    mk_note(toy_vault.QUERIES, "q", {"tags": ["query"]},
            "Una única afirmación citada acá [[2020aaaA...1..1A]].\n")
    with pytest.raises(SystemExit, match="≥2 bibcodes"):
        run(monkeypatch, "seed")


def test_seed_max_acota(toy_vault, monkeypatch):
    seed_fulltext(toy_vault, "2020aaaA...1..1A", "2020bbbB...1..1B")
    seed_notes(toy_vault)
    run(monkeypatch, "seed", "--max", "2")
    data = json.loads((cfg.ROOT / "build" / "verify_bench" / "bench.json").read_text())
    assert data["n_real"] == 2 and data["n_seeded"] == 2


def test_seed_bloques_une_hardwrap_y_protege_rotacion(toy_vault, monkeypatch):
    """Issue #19: un bullet hard-wrapped es UN claim (sin fragmentos que mezclen cláusulas de
    citas vecinas) y la rotación excluye TODOS los bibcodes citados en el bloque."""
    seed_fulltext(toy_vault, "2020aaaA...1..1A", "2020bbbB...1..1B", "2020cccC...1..1C")
    mk_note(toy_vault.CONCEPTS / "methods", "nota-w", {"tags": ["methods"]},
            "- **Realización:** [[2020aaaA...1..1A]] (tau Ceti, régimen sub-m/s)\n"
            "  y [[2020bbbB...1..1B]] (AU Mic, GP dependiente de lambda).\n"
            "\n"
            "Otra afirmación suelta que cita a [[2020cccC...1..1C]] con contenido propio.\n"
            "| fila de tabla con valor 34 d | [[2020cccC...1..1C]] |\n")
    run(monkeypatch, "seed")
    data = json.loads((cfg.ROOT / "build" / "verify_bench" / "bench.json")
                      .read_text(encoding="utf-8"))
    real = [p for p in data["pairs"] if p["label"] == "real"]
    bloque = [p for p in real if p["bibcode"] in ("2020aaaA...1..1A", "2020bbbB...1..1B")]
    assert len(bloque) == 2
    for p in bloque:
        # las dos mitades hard-wrapped quedaron unidas en el mismo claim/bloque
        assert "sub-m/s" in p["claim"] and "AU Mic" in p["claim"]
        assert p["line"] == bloque[0]["line"]
    # la fila de tabla es su propio claim atómico (no se pegó al párrafo)
    tabla = [p for p in real if "fila de tabla" in p["claim"]]
    assert len(tabla) == 1 and "Otra afirmación" not in tabla[0]["claim"]
    # rotación: para el bloque que cita A y B, el único cruce falso posible es C
    for s in (p for p in data["pairs"] if p["label"] == "sembrada"):
        if s["line"] == bloque[0]["line"]:
            assert s["bibcode"] == "2020cccC...1..1C"


def test_seed_claims_ciegos_sin_wikilinks(toy_vault, monkeypatch):
    """Issue #18: el claim se guarda CEGADO (sin [[wikilinks]]) — con el bibcode original
    inline, una sembrada se caza por mismatch de strings sin leer el paper."""
    seed_fulltext(toy_vault, "2020aaaA...1..1A", "2020bbbB...1..1B")
    seed_notes(toy_vault)
    run(monkeypatch, "seed")
    data = json.loads((cfg.ROOT / "build" / "verify_bench" / "bench.json")
                      .read_text(encoding="utf-8"))
    assert data["pairs"], "el toy vault debe producir pares"
    for p in data["pairs"]:
        assert "[[" not in p["claim"] and "]]" not in p["claim"]
        assert "  " not in p["claim"]                 # espacios colapsados
    # el contenido fáctico sobrevive al cegado
    claims = "\n".join(p["claim"] for p in data["pairs"])
    assert "pendiente cromática" in claims and "CRX" in claims


# ── score ────────────────────────────────────────────────────────────────────

def write_bench(pairs):
    bench = cfg.ROOT / "build" / "verify_bench" / "bench.json"
    bench.parent.mkdir(parents=True, exist_ok=True)
    bench.write_text(json.dumps({"n_real": 2, "n_seeded": 2, "pairs": pairs}), encoding="utf-8")


def pair(pid, label, verdict, bib="2020aaaA...1..1A"):
    return {"id": pid, "label": label, "note": "n", "line": 1, "claim": "c",
            "bibcode": bib, "fulltext": "x.txt", "verdict": verdict}


def test_score_metricas(toy_vault, monkeypatch, capsys):
    write_bench([pair("r000", "real", "soportada"),
                 pair("r001", "real", "no-soportada"),       # real caída → sospechosa
                 pair("s000", "sembrada", "no-soportada"),   # cazada
                 pair("s001", "sembrada", "soportada")])     # se le pasó
    assert run(monkeypatch, "score") == 0
    out = capsys.readouterr().out
    assert "1/2 (50%)" in out                       # recall de sembradas
    assert "Sembradas que PASARON" in out and "s001" in out
    assert "Reales caídas" in out and "r001" in out
    assert (cfg.ROOT / "outputs").glob("verify-bench-*.md")


def test_score_incompleto_rc1(toy_vault, monkeypatch, capsys):
    write_bench([pair("r000", "real", None), pair("s000", "sembrada", "vaya-uno-a-saber")])
    assert run(monkeypatch, "score") == 1
    assert "sin veredicto válido" in capsys.readouterr().out


def test_score_sin_bench(toy_vault, monkeypatch):
    with pytest.raises(SystemExit, match="seed"):
        run(monkeypatch, "score")
