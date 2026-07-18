"""Generador del logo de Almagesto — epiciclo ptolemaico, línea fina. Determinista.

Uso:  python docs/assets/make_logo.py     (regenera los 2 SVG en docs/assets/)

Produce, con fondo transparente y UNA sola tinta neutra (gris intermedio legible sobre
blanco y sobre el fondo oscuro de GitHub — el truco <picture>+prefers-color-scheme sigue el
tema del OS, no el de GitHub, y sirve la variante equivocada cuando difieren). Sin wordmark:
el título del README ya nombra al proyecto.
  - logo-animated.svg — header del README: el epiciclo recorre el deferente (24 s)
    mientras la estrella gira sobre él (6 s); la relación 4:1 hace que la estrella pase
    EXACTO sobre la traza epitrocoide k=5 del fondo (el mecanismo dibuja su propia curva).
    Animación SMIL nativa: GitHub la reproduce en el README; donde no, congela en el frame
    inicial (≈ la versión estática — degrada bien).
  - logo.svg — emblema estático (reserva: social preview, favicon, usos chicos).
"""
import math
from pathlib import Path

OUT = Path(__file__).parent
ACCENT = "#d4a017"                       # ámbar: funciona sobre claro y oscuro
INK = "#7d8590"                          # gris neutro: legible sobre blanco y sobre #0d1117
CX, CY = 160, 160


def pt(cx, cy, r, ang):
    return cx + r * math.cos(ang), cy + r * math.sin(ang)


def star4(cx, cy, r_out, r_in):
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        rad = r_out if i % 2 == 0 else r_in
        pts.append(pt(cx, cy, rad, ang))
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts) + " Z"


def epitrochoid(R, r, k, rot=0.0, n=560):
    pts = []
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        x = R * math.cos(t) + r * math.cos(k * t)
        y = R * math.sin(t) + r * math.sin(k * t)
        xr = x * math.cos(rot) - y * math.sin(rot)
        yr = x * math.sin(rot) + y * math.cos(rot)
        pts.append((CX + xr, CY + yr))
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)


def write(body, name):
    doc = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" '
           f'width="320" height="320">\n' + body + "\n</svg>\n")
    (OUT / name).write_text(doc, encoding="utf-8")
    print(f"  docs/assets/{name}")


def animated(ink):
    """Deferente 24 s + epiciclo 6 s ⇒ traza k=5 (ver header del módulo)."""
    R_DEF, R_EPI = 78, 26                # traza máx. R+r=104: entra en el lienzo
    ex = CX + R_DEF
    return f'''<path d="{epitrochoid(R_DEF, R_EPI, 5)}" stroke="{ink}" fill="none"
      stroke-width="1" opacity="0.3"/>
<circle cx="{CX}" cy="{CY}" r="{R_DEF}" stroke="{ink}" fill="none" stroke-width="1.6"
      stroke-dasharray="4 5" opacity="0.6"/>
<circle cx="{CX}" cy="{CY}" r="3.6" fill="{ink}"/>
<g>
  <animateTransform attributeName="transform" type="rotate"
    from="0 {CX} {CY}" to="360 {CX} {CY}" dur="24s" repeatCount="indefinite"/>
  <line x1="{CX}" y1="{CY}" x2="{ex}" y2="{CY}" stroke="{ink}" stroke-width="1.3"/>
  <circle cx="{ex}" cy="{CY}" r="{R_EPI}" stroke="{ink}" fill="none" stroke-width="1.8"/>
  <circle cx="{ex}" cy="{CY}" r="2.4" fill="{ink}"/>
  <g>
    <animateTransform attributeName="transform" type="rotate"
      from="0 {ex} {CY}" to="360 {ex} {CY}" dur="6s" repeatCount="indefinite"/>
    <line x1="{ex}" y1="{CY}" x2="{ex + R_EPI}" y2="{CY}" stroke="{ink}" stroke-width="1.3"/>
    <path d="{star4(ex + R_EPI, CY, 11, 4.2)}" fill="{ACCENT}"/>
  </g>
</g>'''


def static(ink):
    """Emblema V1: deferente + epiciclo + estrella, geometría limpia."""
    ex, ey = pt(CX, CY, 92, math.radians(-38))
    sx, sy = pt(ex, ey, 30, math.radians(-95))
    return f'''<g stroke="{ink}" fill="none" stroke-width="2">
  <circle cx="{CX}" cy="{CY}" r="92"/>
  <circle cx="{ex:.2f}" cy="{ey:.2f}" r="30"/>
  <line x1="{CX}" y1="{CY}" x2="{ex:.2f}" y2="{ey:.2f}" stroke-width="1.4"/>
  <line x1="{ex:.2f}" y1="{ey:.2f}" x2="{sx:.2f}" y2="{sy:.2f}" stroke-width="1.4"/>
</g>
<circle cx="{CX}" cy="{CY}" r="3.6" fill="{ink}"/>
<circle cx="{ex:.2f}" cy="{ey:.2f}" r="2.6" fill="{ink}"/>
<path d="{star4(sx, sy, 12, 4.6)}" fill="{ACCENT}"/>'''


if __name__ == "__main__":
    write(animated(INK), "logo-animated.svg")
    write(static(INK), "logo.svg")
