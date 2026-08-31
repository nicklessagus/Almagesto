"""CLAUDE.md has a size ratchet, not just a convention (recorte 2026-08-30).

CLAUDE.md is injected whole into every session's context, so its size is the only doc size that
costs on every operation. Measured before the trim: 2258 lines / 201 KB, with 73 % of the bytes
being development color (issue postmortems, corpus measurements) already living in the public
issues, `docs/mediciones.md` and `docs/contrato.md`. The writing rule the ceiling mechanizes: the
rule plus its one-line consequence and its anchor (#N/D-N) stay; the story moves out.

Same pattern as `tests/test_idioma_codigo.py`: a value well below the ceiling asks to be lowered — a
ceiling nobody adjusts stops being a ratchet (AUD-07).

⛔ The ceiling CAN be raised, and never in silence (#340). Until 1.150.0 it could only go down. That
worked while there was postmortem left to move out; measured on 2026-08-31 only **3 %** of the file
carries a postmortem mark (43 of 1620 lines), so «only down» had turned into «no new rule can ever
be written» — and it had already decided, silently, three times in the #329-#335 batch. Now a raise
is allowed and must leave its entry in `crecimientos` (date, anchor, reason); what stays forbidden
is the file growing without anyone signing for it, which is what the ratchet exists to stop.
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
    and if the rule still does not fit, raising the ceiling **with its declared entry** (#340) —
    never editing the number on its own."""
    ratchet = yaml.safe_load(RATCHET.read_text(encoding="utf-8"))
    lineas, bytes_ = _medida()
    assert lineas <= ratchet["techo_lineas"] and bytes_ <= ratchet["techo_bytes"], (
        f"CLAUDE.md creció: {lineas} líneas / {bytes_} B contra techo "
        f"{ratchet['techo_lineas']} / {ratchet['techo_bytes']}. La regla nueva va con su "
        f"consecuencia en una línea y su ancla (#N); el porqué medido va al issue y a "
        f"docs/mediciones.md. Si la regla igual no entra, el techo SE PUEDE subir (#340) — "
        f"agregando su entrada a `crecimientos` con fecha, ancla y motivo. Lo que no se puede "
        f"es que crezca sin que nadie firme."
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


def test_la_suba_del_techo_esta_declarada():
    """A raise is allowed; an undeclared one is not (#340).

    The ceiling must be the one the last `crecimientos` entry declares, so every raise carries its
    date, its anchor and its reason. Without this the change of 1.150.0 —from a wall to a warning—
    would just be «the ceiling can be edited», which is the acretion the ratchet exists to stop."""
    ratchet = yaml.safe_load(RATCHET.read_text(encoding="utf-8"))
    subas = ratchet.get("crecimientos") or []
    assert subas, ("`crecimientos` está vacía: el techo vigente no tiene quién lo firme. "
                   "Toda suba deja su entrada con fecha, ancla y motivo (#340).")
    ultima = subas[-1]
    faltan = [k for k in ("fecha", "ancla", "motivo", "techo_lineas", "techo_bytes")
              if not ultima.get(k)]
    assert not faltan, f"la última entrada de `crecimientos` no declara {faltan} (#340)"
    assert (ratchet["techo_lineas"] == ultima["techo_lineas"]
            and ratchet["techo_bytes"] == ultima["techo_bytes"]), (
        f"el techo vigente ({ratchet['techo_lineas']} / {ratchet['techo_bytes']}) no es el que "
        f"declara la última suba ({ultima['techo_lineas']} / {ultima['techo_bytes']}, "
        f"{ultima['fecha']} {ultima['ancla']}): subilo agregando su entrada, o bajalo ajustando "
        f"las dos cosas juntas."
    )
