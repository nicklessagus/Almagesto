"""CLAUDE.md has a size ratchet, not just a convention (recorte 2026-08-30).

CLAUDE.md is injected whole into every session's context, so its size is the only doc size that
costs on every operation. Measured before the trim: 2258 lines / 201 KB, with 73 % of the bytes
being development color (issue postmortems, corpus measurements) already living in the public
issues, `docs/mediciones.md` and `docs/contrato.md`. The writing rule the ceiling mechanizes: the
rule plus its one-line consequence and its anchor (#N/D-N) stay; the story moves out.

Same pattern as `tests/test_idioma_codigo.py`: the ceiling only goes down, and a value well below
it asks to be lowered — a ceiling nobody adjusts stops being a ratchet (AUD-07).
"""
from __future__ import annotations

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
RATCHET = RAIZ / "tools" / "doc-size-ratchet.yaml"
MARGEN = 0.03  # below (1 - MARGEN) * ceiling the test asks to lower the ceiling


def _medida() -> tuple[int, int]:
    texto = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
    return texto.count("\n"), len(texto.encode("utf-8"))


def test_claude_md_no_crece():
    """Above the ceiling the fix is moving the story out — to the issue and `docs/mediciones.md` —
    never raising the ceiling (that edit belongs to the template's user, with its reason in the
    commit)."""
    ratchet = yaml.safe_load(RATCHET.read_text(encoding="utf-8"))
    lineas, bytes_ = _medida()
    assert lineas <= ratchet["techo_lineas"] and bytes_ <= ratchet["techo_bytes"], (
        f"CLAUDE.md creció: {lineas} líneas / {bytes_} B contra techo "
        f"{ratchet['techo_lineas']} / {ratchet['techo_bytes']}. La regla nueva va con su "
        f"consecuencia en una línea y su ancla (#N); el porqué medido va al issue y a "
        f"docs/mediciones.md — no acá, y el techo no se sube."
    )


def test_el_techo_se_ajusta():
    """A ceiling far above the real size stops being a ratchet: it would absorb a whole regression
    silently (AUD-07). When the file shrinks past the margin, lower the ceiling in the same
    change."""
    ratchet = yaml.safe_load(RATCHET.read_text(encoding="utf-8"))
    lineas, bytes_ = _medida()
    assert lineas > ratchet["techo_lineas"] * (1 - MARGEN) or \
           bytes_ > ratchet["techo_bytes"] * (1 - MARGEN), (
        f"CLAUDE.md ({lineas} líneas / {bytes_} B) quedó más de un {MARGEN:.0%} por debajo del "
        f"techo ({ratchet['techo_lineas']} / {ratchet['techo_bytes']}): bajá el techo en "
        f"tools/doc-size-ratchet.yaml en este mismo cambio."
    )
