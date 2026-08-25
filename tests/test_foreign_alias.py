"""Un alias declarado que resuelve a OTRO objeto no lo detecta nadie (#82, lado "de más").

El skill `ingest-star` advierte que «un alias que falta es un paper que nunca aparece — en silencio»
y por eso manda resolverlos en SIMBAD. No decía nada del alias **de más**, que mete papers de otro
objeto al corpus por la misma puerta. Caso medido en el clean-room del 2026-08-25: `HR 2102`
declarado para HD 40307 es en realidad **36 Dor** (K2III-IV). Impacto de ese caso: 0 papers
contaminados — latente, no daño, pero nada lo miraba.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_ground_truth as fgt
import lint


class _Tabla:
    """Doble de la tabla de `Simbad.query_objectids`: una columna, una fila por identificador."""
    colnames = ["ID"]

    def __init__(self, ids):
        self._ids = list(ids)

    def __len__(self):
        return len(self._ids)

    def __iter__(self):
        return iter([{"ID": i} for i in self._ids])


def _simbad(monkeypatch, tabla):
    """Inyecta la respuesta de SIMBAD sin tocar la red (el import es local a la función)."""
    import types
    mod = types.ModuleType("astroquery.simbad")
    mod.Simbad = lambda: types.SimpleNamespace(query_objectids=lambda host: tabla)
    monkeypatch.setitem(sys.modules, "astroquery", types.ModuleType("astroquery"))
    monkeypatch.setitem(sys.modules, "astroquery.simbad", mod)


def test_alias_ajeno_se_reporta(monkeypatch):
    """El caso HR 2102: declarado, y SIMBAD no lo lista para esta estrella."""
    _simbad(monkeypatch, _Tabla(["HD  40307", "GJ 2046", "HIP 27887"]))
    assert fgt.unresolved_aliases("HD 40307", ["GJ 2046", "HIP 27887", "HR 2102"]) == ["HR 2102"]


def test_el_espaciado_no_genera_falsos_positivos(monkeypatch):
    """SIMBAD escribe `HD  40307` con espaciado variable y `stars.yaml` `HD 40307`. Sin normalizar,
    TODO alias legítimo saldría reportado y el chequeo sería ruido puro."""
    _simbad(monkeypatch, _Tabla(["HD  40307", "GJ  2046"]))
    assert fgt.unresolved_aliases("HD 40307", ["GJ 2046", "hd40307"]) == []


def test_simbad_mudo_devuelve_None_no_lista_vacia(monkeypatch):
    """`None` («no contestó») ≠ `[]` («contestó y están todos»). Sin esa distinción una caída de red
    se leería como "alias verificados" — el mismo cero inventado que D-43 prohíbe."""
    _simbad(monkeypatch, None)
    assert fgt.unresolved_aliases("HD 40307", ["GJ 2046"]) is None


def test_el_lint_surface_el_alias_ajeno_como_warn(toy_vault, capsys):
    """Se persiste en el ground-truth para que el hallazgo sea **offline**: la corrida que lo
    detecta es la que tiene red, y el lint es el que se mira."""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps(
        {"star": "Test", "slug": "test_star", "host": {}, "planets": [],
         "_unresolved_aliases": ["HR 2102"]}), encoding="utf-8")
    cats = {c.clave: c for c in lint.collect().categorias}
    hits = cats["foreign_alias"].items
    assert [h[0] for h in hits] == ["test_star"] and "HR 2102" in hits[0][1], hits
    assert cats["foreign_alias"].severidad == lint.SEV_WARN, \
        "es riesgo de config, no violación de la bóveda: se revisa a mano"


def test_snapshot_sin_el_campo_no_dispara(toy_vault):
    """Un ground-truth anterior a #82 no tiene `_unresolved_aliases`: no hay nada que afirmar sobre
    él, y reportarlo sería inventar un hallazgo por ausencia de dato."""
    (toy_vault.GROUND_TRUTH / "test_star.json").write_text(json.dumps(
        {"star": "Test", "slug": "test_star", "host": {}, "planets": []}), encoding="utf-8")
    cats = {c.clave: c for c in lint.collect().categorias}
    assert cats["foreign_alias"].items == ()
