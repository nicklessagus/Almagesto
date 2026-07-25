"""Generador del demo animado del README — una sesión de ingest en terminal. Determinista.

Uso:  python docs/assets/make_demo.py     (regenera demo-animated.svg en docs/assets/)

El demo es una **ventana de terminal SVG** que reproduce, animada, la operación central del
template: el usuario pide *"bajá HD 40307"* y el agente corre la cadena mecánica → extracción
LLM → disputa tagueada → verify-citations → lint. Sin GIF ni binarios de grabación: texto SVG
con animaciones SMIL (mismo mecanismo que logo-animated.svg, que GitHub ya reproduce).

Convenciones (conservar):
  - **Fidelidad**: los hechos astronómicos son los reales de la instancia Almagesto-RV
    (HD 40307: 5 planetas b–g, K2.5 V, disputa de existencia de g por Díaz+2016
    [[2016A&A...585A.134D]], 38 no-core listados). Los conteos de plomería (papers bajados)
    son representativos, igual que el probe de ejemplo del README.
  - **Degradación**: cada línea tiene opacity=1 de base y la animación sólo la oculta al
    principio del ciclo; donde SMIL no corre, el SVG congela mostrando la sesión COMPLETA.
  - **Loop**: todas las animaciones comparten dur=T y keyTimes fraccionales → el ciclo
    reinicia sincronizado (aparece todo en ~14 s, sostiene el cuadro final y repite).
  - Paleta GitHub-dark dentro de la ventana (funciona sobre tema claro y oscuro del README):
    fondo #0d1117, tinta #7d8590/#8b949e, texto #c9d1d9, acento ámbar #d4a017 (el del logo),
    wikilinks #79c0ff, ✓ #3fb950.
"""
from pathlib import Path

OUT = Path(__file__).parent

# ── paleta ──────────────────────────────────────────────────────────────────
BG, CHROME, BORDER = "#0d1117", "#161b22", "#30363d"
INK = "#7d8590"                     # gris del logo: título de la ventana
DIM = "#8b949e"                     # salida de los scripts
FG = "#c9d1d9"                      # texto principal
AMBER = "#d4a017"                   # acento del logo: prompt, ⏺ del agente, disputa
BLUE = "#79c0ff"                    # [[wikilinks]]
GREEN = "#3fb950"                   # ✓ del lint

# ── métrica ─────────────────────────────────────────────────────────────────
W, PAD, Y0, LH, FS = 760, 22, 56, 20, 13
CH = 7.8                            # ancho de celda monospace a 13 px
T = 24.0                            # duración del ciclo (s)
FADE = 0.25                         # fade-in por línea (s)
FONT = "ui-monospace,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

CMD = "bajá HD 40307"               # lo que "tipea" el usuario
T_TYPE0, T_TYPE1 = 0.8, 2.2         # ventana de tipeo

# Guion: (segundos de aparición | None = fila en blanco, [(texto, color), ...])
BIB = "[[2016A&A...585A.134D]]"
ROWS = [
    "PROMPT",                       # fila 0: "> bajá HD 40307" (tipeada, ver abajo)
    None,
    (3.0, [("● ", AMBER), ("ingest-star — corro la cadena mecánica (idempotente):", FG)]),
    (3.6, [("  $ ", DIM), ("python scripts/ingest_star.py hd40307", FG)]),
    (4.4, [("  Consultando ADS: HD 40307  (nombres: HD 40307, GJ 2046, HIP 27887)", DIM)]),
    (5.2, [("  24 core → PDF + fulltext · 38 no-core: sólo listados (top por citas)", DIM)]),
    (6.0, [("  ground-truth NEA — planetas confirmados: 5 · sp_type: K2.5 V", DIM)]),
    (6.8, [("  star: hd40307.md · papers: 24 notas · fulltext: 24 .txt greppables", DIM)]),
    None,
    (7.8, [("● ", AMBER), ("extracción LLM — leo los fulltext y destilo la ficha:", FG)]),
    (8.6, [("  señales RV b c d f g — P/K/e/m·sini, cada valor con su ", DIM),
           ("[[bibcode]]", BLUE)]),
    (9.4, [("  ⚑\ufe0e ", AMBER), (BIB, BLUE), (" cuestiona la existencia de g", DIM)]),
    (10.0, [("    → disputes: {field: existence, ref: Díaz+2016} — NEA sigue siendo la verdad",
             DIM)]),
    None,
    (11.0, [("● ", AMBER),
            ("verify-citations — cada afirmación contra su fuente (un subagente por par)", FG)]),
    (11.8, [("  $ ", DIM), ("python scripts/lint.py", FG), ("   ✓ sin bloqueantes", GREEN)]),
    None,
    (12.8, [("✻ ", AMBER), ("ficha lista: stars/hd40307.md se entiende sin abrir ningún paper",
                            FG)]),
    None,
    "CURSOR",                       # fila final: "> " + cursor titilando
]
H = Y0 + LH * len(ROWS) + 10        # alto de la ventana


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fade(t):
    """Fade-in en t (s), dentro del ciclo de T s. Base opacity=1 → sin SMIL se ve todo."""
    k = f"0;{t / T:.4f};{min(t + FADE, T) / T:.4f};1"
    return (f'<animate attributeName="opacity" values="0;0;1;1" keyTimes="{k}" '
            f'dur="{T}s" repeatCount="indefinite"/>')


def text_at(y, parts, x=PAD):
    spans = "".join(f'<tspan fill="{c}">{esc(s)}</tspan>' for s, c in parts)
    return (f'<text x="{x}" y="{y}" xml:space="preserve" font-family="{FONT}" '
            f'font-size="{FS}">{spans}</text>')


def typing_clip():
    """El comando se revela carácter a carácter: clip-rect con pasos discretos."""
    n = len(CMD)
    widths, times = ["0", "0"], ["0", f"{T_TYPE0 / T:.4f}"]
    for i in range(1, n + 1):
        widths.append(f"{i * CH:.1f}")
        times.append(f"{(T_TYPE0 + (T_TYPE1 - T_TYPE0) * i / n) / T:.4f}")
    return (f'<clipPath id="type"><rect x="{PAD + 2 * CH:.1f}" y="{Y0 - FS - 3}" '
            f'width="{n * CH:.1f}" height="{FS + 8}">'
            f'<animate attributeName="width" calcMode="discrete" '
            f'values="{";".join(widths)}" keyTimes="{";".join(times)}" '
            f'dur="{T}s" repeatCount="indefinite"/></rect></clipPath>')


def chrome():
    """Ventana: fondo, barra de título (esquinas superiores redondeadas), borde al final."""
    dots = "".join(f'<circle cx="{22 + 18 * i}" cy="17" r="5" fill="{BORDER}"/>'
                   for i in range(3))
    return (f'<rect width="{W}" height="{H}" rx="8" fill="{BG}"/>'
            f'<rect width="{W}" height="33" rx="8" fill="{CHROME}"/>'
            f'<rect y="16" width="{W}" height="17" fill="{CHROME}"/>'
            f'<path d="M 0 33.5 H {W}" stroke="{BORDER}" stroke-width="1"/>{dots}'
            f'<text x="{W / 2}" y="21" text-anchor="middle" font-family="{FONT}" '
            f'font-size="12" fill="{INK}">mi-boveda — claude</text>'
            f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="8" '
            f'fill="none" stroke="{BORDER}"/>')


def body():
    out = [typing_clip(), chrome()]
    for i, row in enumerate(ROWS):
        y = Y0 + LH * i
        if row is None:
            continue
        if row == "PROMPT":
            out.append(text_at(y, [("> ", AMBER)]))
            out.append(f'<g clip-path="url(#type)">'
                       f'{text_at(y, [(CMD, FG)], x=round(PAD + 2 * CH, 1))}</g>')
            continue
        if row == "CURSOR":
            blink = ('<animate attributeName="opacity" calcMode="discrete" values="1;0" '
                     'keyTimes="0;0.5" dur="1.2s" repeatCount="indefinite"/>')
            out.append(f'<g opacity="1">{fade(13.8)}'
                       + text_at(y, [("> ", AMBER)])
                       + f'<rect x="{PAD + 2 * CH:.1f}" y="{y - FS}" width="{CH:.1f}" '
                         f'height="{FS + 2}" fill="{FG}">{blink}</rect></g>')
            continue
        t, parts = row
        out.append(f'<g opacity="1">{fade(t)}{text_at(y, parts)}</g>')
    return "\n".join(out)


if __name__ == "__main__":
    doc = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'width="{W}" height="{H}">\n'
           f'<title>Demo: «bajá HD 40307» → ingest → ficha verificada</title>\n'
           + body() + "\n</svg>\n")
    (OUT / "demo-animated.svg").write_text(doc, encoding="utf-8")
    print("  docs/assets/demo-animated.svg")
