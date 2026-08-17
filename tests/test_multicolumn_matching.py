"""Regresión de la estrategia de matcheo en .txt multi-columna (#44/#45).

NO necesita corpus: usa un fixture sintético a dos columnas. Pinea los invariantes que motivan la
regla del skill `verify-citations`, para que nadie los "optimice" después.

Hallazgo que estos tests documentan (#46): normalizar **por línea** —lo que #44 dejó como escape—
también colapsa la **canaleta** de esa misma línea, así que el empalme columna1→columna2 sigue
siendo alcanzable. Reduce el problema (de ~2 empalmes por línea a ~1) pero no lo cierra. Lo único
que lo cierra es **partir cada línea en la canaleta** y buscar dentro de cada segmento de columna.
Son hechos mecánicos del formato, no comportamiento a arreglar: los asserts quedan verdes antes y
después de #46 (lo que cambia con el issue es la prosa del skill, y estos tests son su porqué).
"""
import re
import sys
from pathlib import Path

# Mismo setup que conftest.py, para que el archivo también corra solo (python tests/test_...py).
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from measure_layout import CANALETA_MIN  # noqa: E402

# --- fixture: dos columnas, como las deja `pdftotext -layout` -----------------------------------
FIXTURE = "\n".join([
    "We validated the fidelity of the shift by computing              The Whittle approximation applies only in the",
    "heliocentric velocities. We find that the temporal               case of noise-free models. In this work, by",
    "variance of the residual ACF is between 2.5 and 4.5              contrast, we take additive noise into account",
    "orders of magnitude smaller than the temporal                    and estimate its covariance jointly with the",
    "variance of either ACF timeseries, at every point.               mixing matrix, which is the main contribution.",
])
LINES = FIXTURE.split("\n")

# Afirmación real: vive entera en la columna 1, partida en tres líneas físicas.
CLAIM = "the temporal variance of the residual ACF is between 2.5 and 4.5 orders of magnitude smaller"
# Frase que el paper NUNCA escribió: cruza la canaleta de la L3 (fin col.1 + arranque col.2).
SPLICE = "between 2.5 and 4.5 contrast, we take additive noise"

# La canaleta se define UNA vez, en measure_layout (single source, #46).
GUTTER_SPLIT = re.compile(rf" {{{CANALETA_MIN},}}")


def _n(s):
    return re.sub(r"\s+", " ", s).lower()


def grep_lines(pattern, lines=LINES):
    p = _n(pattern)
    for i, line in enumerate(lines, 1):
        if p in _n(line):
            return i
    return None


def split_gutter(lines=LINES):
    """Parte cada línea física en segmentos de columna. Cierra el empalme por canaleta."""
    out = []
    for line in lines:
        out.extend(seg for seg in GUTTER_SPLIT.split(line) if seg.strip())
    return out


def escalera(quote, lines=LINES):
    """#44: oración completa → acortar hasta un fragmento que quepa en una línea física."""
    w = quote.split()
    for n in range(len(w), 2, -1):
        for start in range(len(w) - n + 1):
            hit = grep_lines(" ".join(w[start:start + n]), lines)
            if hit:
                return hit, n
    return None, 0


def test_frase_entera_falla():
    """El peligro es real: la oración cruza saltos de línea y grep no la ve."""
    assert grep_lines(CLAIM) is None


def test_escalera_la_encuentra():
    """La regla funciona: acortando aparece, y el texto estaba todo el tiempo."""
    linea, n = escalera(CLAIM)
    assert linea == 3
    assert n < len(CLAIM.split()), "encontró con la frase entera; el fixture no ejerce la escalera"


def test_archivo_entero_fabrica_empalmes_por_salto_de_linea():
    """Modo peligroso 1: colapsar el archivo pega el fin de una línea con el inicio de la siguiente."""
    entero = _n(FIXTURE)
    cruce = "applies only in the heliocentric velocities"   # fin col.2 L1 + inicio col.1 L2
    assert cruce in entero
    assert grep_lines(cruce) is None, "debería no existir en ninguna línea física"


def test_por_linea_NO_cierra_el_empalme_por_canaleta():
    """Modo peligroso 2 — el residual que motiva #46.

    Normalizar por línea sigue colapsando la canaleta de esa línea, así que una frase que cruza de
    la columna 1 a la columna 2 se encuentra igual. Es mecánica del formato, no un bug a arreglar:
    el assert no se da vuelta cuando #46 cierre la prosa del skill — es su justificación.
    """
    assert grep_lines(SPLICE) is not None, (
        "el empalme por canaleta dejó de ser alcanzable — ¿cambió la normalización del test?"
    )


def test_partir_en_la_canaleta_SI_lo_cierra():
    """El arreglo completo (#46): partir cada línea en la canaleta y buscar por segmento de columna."""
    cols = split_gutter()
    assert grep_lines(SPLICE, cols) is None, "partir en la canaleta debería eliminar el empalme"
    # ...y sin perder la cita legítima:
    linea, _ = escalera(CLAIM, cols)
    assert linea is not None, "partir en la canaleta no debe romper el matcheo legítimo"


def test_de_hifenado():
    """Rama 3 de #44: el corte de línea parte palabras con guión."""
    lineas = ["la varianza es de 2.5 a 4.5 ordenes de mag-", "nitude menor que la de cualquiera"]
    assert "magnitude" not in "\n".join(lineas), "el fixture no ejerce el guionado"
    assert grep_lines("ordenes de mag-", lineas) == 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ok  {name}")
    print("\ntodos los invariantes se sostienen")
