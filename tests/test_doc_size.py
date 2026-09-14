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

import re
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


# --- #465: budget, not just ceiling ---------------------------------------------------------

SKILLS = RAIZ / ".claude" / "skills"


def _ratchet() -> dict:
    return yaml.safe_load(RATCHET.read_text(encoding="utf-8"))


def _skill_sizes() -> dict:
    return {p.parent.name: len(p.read_bytes()) for p in sorted(SKILLS.glob("*/SKILL.md"))}


def test_ninguna_firma_se_pierde_al_parsear():
    """#465 (secondary finding) — one `crecimientos` entry was missing its `- ` and YAML folded it
    into the previous one: 44 `ancla:` keys, 43 entries, and the merge signature of #344 silently
    replaced by #345's. The gate compared only the LAST entry, so it never saw it. Cheap net: the
    number of `ancla:` keys written is the number of parsed entries — `ancla:`, not `- fecha:`,
    because the nested entry had NO `fecha` line at all: counting `- fecha:` gave 43 = 43 and
    missed the original defect (checked by re-nesting it)."""
    texto = RATCHET.read_text(encoding="utf-8")
    escritas = len(re.findall(r"^\s*ancla:", texto, re.M))
    parseadas = len(_ratchet().get("crecimientos") or []) + len(_ratchet().get("crecimientos_skills") or [])
    assert escritas == parseadas, (
        f"{escritas} claves `ancla:` escritas y {parseadas} entradas parseadas en "
        f"tools/doc-size-ratchet.yaml: una entrada sin `- ` quedó anidada en la anterior y su "
        f"firma se perdió (#465)."
    )


def test_toda_suba_declara_que_sale():
    """#465 — the raise of #340 was a ratchet with a tooth on one side only: every entry answered
    «does this rule fit?» and none «at the cost of what?». From `sale_obligatorio_desde` on, an
    entry declares what leaves CLAUDE.md, or why nothing can (same rule as `--reason`)."""
    r = _ratchet()
    desde = str(r.get("sale_obligatorio_desde") or "")
    assert desde, "tools/doc-size-ratchet.yaml no declara `sale_obligatorio_desde` (#465)"
    mudas = [f"{e.get('fecha')} {e.get('ancla')}" for e in r["crecimientos"]
             if str(e.get("fecha")) >= desde and not str(e.get("sale") or "").strip()]
    assert not mudas, (
        "entradas de `crecimientos` sin `sale:` (qué sale de CLAUDE.md, o por qué nada puede "
        f"salir) — #465:\n  " + "\n  ".join(mudas)
    )


def test_la_pendiente_se_ve():
    """#465 — the 3 % margin only looks DOWN, so no line of code could observe +28 kB in 14 days.
    This is an ALARM, not a red: N signed raises inside a rolling window of D days ending at the
    last raise warns. The window is anchored to the last entry, not to today, so the verdict does
    not drift with the calendar."""
    import datetime as dt
    import warnings
    r = _ratchet()
    cfg = r.get("pendiente") or {}
    assert cfg.get("ventana_dias") and cfg.get("max_subas"), "falta `pendiente:` en el ratchet (#465)"
    fechas = sorted(dt.date.fromisoformat(str(e["fecha"])) for e in r["crecimientos"]
                    if "BAJA" not in str(e.get("motivo", ""))[:12])
    if not fechas:
        return
    fin = fechas[-1]
    ventana = [f for f in fechas if (fin - f).days < int(cfg["ventana_dias"])]
    if len(ventana) >= int(cfg["max_subas"]):
        warnings.warn(
            f"CLAUDE.md: {len(ventana)} subas firmadas en los {cfg['ventana_dias']} días que "
            f"terminan el {fin} (alarma ≥ {cfg['max_subas']}, #465). Cada una se juzgó sola; "
            f"ésta es la única línea que mira la tendencia.", UserWarning)


def test_los_skills_no_crecen():
    """#465 (carrier 1) — a `SKILL.md` enters the context WHOLE when invoked: same economy as
    CLAUDE.md, and `test_claude_md_no_crece` hardcoded one file. Measured: the four big ones went
    from 13 kB (2026-07-01) to 185 kB (2026-09-14). A new skill declares its ceiling at birth."""
    techos = _ratchet().get("skills") or {}
    sizes = _skill_sizes()
    sin_techo = sorted(set(sizes) - set(techos))
    assert not sin_techo, (
        f"SKILL.md sin techo en tools/doc-size-ratchet.yaml `skills:` — declaralo al nacer: {sin_techo}")
    pasados = {n: (b, techos[n]) for n, b in sizes.items() if b > int(techos[n])}
    assert not pasados, (
        "SKILL.md por encima de su techo (#465) — la regla nueva va con su ancla y su consecuencia; "
        "si igual no entra, subilo con su entrada en `crecimientos_skills` (fecha, skill, ancla, "
        "motivo, sale, techo_bytes):\n  " +
        "\n  ".join(f"{n}: {b} B contra {t}" for n, (b, t) in sorted(pasados.items()))
    )


def test_el_techo_de_cada_skill_se_ajusta():
    """Same as `test_el_techo_se_ajusta`, per skill (AUD-07): a ceiling far above the file absorbs
    a regression silently."""
    techos = _ratchet().get("skills") or {}
    sizes = _skill_sizes()
    flojos = {n: (b, techos[n]) for n, b in sizes.items()
              if n in techos and b <= int(techos[n]) * (1 - MARGEN)}
    assert not flojos, (
        f"techo de skill más de un {MARGEN:.0%} por encima del archivo: bajalo en "
        "tools/doc-size-ratchet.yaml `skills:` en este mismo cambio:\n  " +
        "\n  ".join(f"{n}: {b} B contra {t}" for n, (b, t) in sorted(flojos.items()))
    )


def test_la_suba_del_techo_de_un_skill_esta_declarada():
    """#340 applied to skills: the ceiling in `skills:` must be the one the last
    `crecimientos_skills` entry for that skill declares — a raise nobody signed is the accretion
    the ratchet exists to stop. Skills with no entry keep their birth ceiling."""
    r = _ratchet()
    techos = r.get("skills") or {}
    ultima: dict = {}
    for e in r.get("crecimientos_skills") or []:
        faltan = [k for k in ("fecha", "skill", "ancla", "motivo", "sale", "techo_bytes") if not e.get(k)]
        assert not faltan, f"entrada de `crecimientos_skills` sin {faltan}: {e}"
        ultima[e["skill"]] = e
    desync = {n: (techos.get(n), e["techo_bytes"]) for n, e in ultima.items()
              if techos.get(n) != e["techo_bytes"]}
    assert not desync, (
        "techo de `skills:` distinto del que declara la última suba firmada:\n  " +
        "\n  ".join(f"{n}: {a} contra {b}" for n, (a, b) in sorted(desync.items()))
    )
