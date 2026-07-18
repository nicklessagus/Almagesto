"""Generador del logo de Almagesto — la rosa de Venus. Determinista.

Uso:  python docs/assets/make_logo.py     (regenera los 2 SVG en docs/assets/)

El emblema es la **trayectoria geocéntrica real de Venus**: vista desde la Tierra, Venus
dibuja en el cielo una rosa de 5 pétalos que se cierra cada 8 años (8 años terrestres ≈ 13
años venusinos ≈ 5 períodos sinódicos — el "pentagrama de Venus"). Es astronomía observacional
literal, no un adorno: la curva es `posición(Venus) − posición(Tierra)` con órbitas circulares.
Encaja con Almagesto —una bóveda de literatura astronómica— y con el linaje ptolemaico del nombre
(las trayectorias aparentes que los antiguos mapeaban).

Convenciones (validadas, conservar): fondo transparente y UNA sola tinta neutra (`#7d8590`,
gris intermedio legible sobre blanco y sobre el `#0d1117` de GitHub — evita el truco frágil
`<picture>`+`prefers-color-scheme`, que sigue el tema del OS y no el de GitHub). Acento ámbar
(`#d4a017`) para Venus, funciona en ambos temas. Sin wordmark: el título del README ya nombra
al proyecto.
  - logo-animated.svg — header del README: la rosa se DIBUJA sola (stroke-dashoffset) mientras
    Venus (estrella ámbar) recorre la punta del trazo (animateMotion sobre la misma curva), 20 s
    en loop. SMIL nativo: GitHub lo reproduce; donde no, congela con la rosa completa (≈ la
    versión estática — degrada bien).
  - logo.svg — emblema estático (reserva: social preview, favicon, usos chicos): la rosa completa
    con Venus fijado en la conjunción de radio máximo.
"""
import math
from pathlib import Path

OUT = Path(__file__).parent
ACCENT = "#d4a017"                       # ámbar: Venus; funciona sobre claro y oscuro
INK = "#7d8590"                          # gris neutro: legible sobre blanco y sobre #0d1117
CX, CY = 160, 160
SCALE = 80.0                             # UA → px (radio máx R+1 ≈ 1.72 UA ⇒ ~138 px, entra en 320)
TAU = 2 * math.pi

# Efemérides usadas (órbitas circulares, co-planares): períodos siderales en años terrestres
# y semieje de Venus en UA. Fuente de la razón 8:13 ⇒ 5 pétalos.
P_VENUS = 0.61519726
A_VENUS = 0.7233
ROT_DEG = 18.0                           # orientación estética de la rosa (no altera la forma)


def pt(cx, cy, r, ang):
    return cx + r * math.cos(ang), cy + r * math.sin(ang)


def star4(cx, cy, r_out, r_in):
    """Estrella de 4 puntas (destello) centrada en (cx, cy)."""
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        rad = r_out if i % 2 == 0 else r_in
        pts.append(pt(cx, cy, rad, ang))
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts) + " Z"


def venus_rose(n=2400):
    """Trayectoria geocéntrica de Venus en 8 años: posición(Venus) − posición(Tierra)."""
    rot = math.radians(ROT_DEG)
    pts = []
    for i in range(n + 1):
        t = 8.0 * i / n                                  # años terrestres
        x = A_VENUS * math.cos(TAU * t / P_VENUS) - math.cos(TAU * t)
        y = A_VENUS * math.sin(TAU * t / P_VENUS) - math.sin(TAU * t)
        xr = x * math.cos(rot) - y * math.sin(rot)
        yr = x * math.sin(rot) + y * math.cos(rot)
        pts.append((CX + xr * SCALE, CY + yr * SCALE))
    return pts


def path_d(pts):
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)


def polyline_len(pts):
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
               for i in range(len(pts) - 1))


def write(body, name):
    doc = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" '
           f'width="320" height="320">\n' + body + "\n</svg>\n")
    (OUT / name).write_text(doc, encoding="utf-8")
    print(f"  docs/assets/{name}")


def animated():
    """La rosa se dibuja sola mientras Venus recorre la punta del trazo (20 s, loop)."""
    pts = venus_rose()
    d = path_d(pts)
    length = polyline_len(pts)
    dur = "20s"
    return f'''<path id="rose" d="{d}" stroke="{INK}" fill="none" stroke-width="1.2"
      stroke-linejoin="round" stroke-linecap="round"
      stroke-dasharray="{length:.1f}" stroke-dashoffset="{length:.1f}">
  <animate attributeName="stroke-dashoffset" from="{length:.1f}" to="0"
    dur="{dur}" repeatCount="indefinite"/>
</path>
<circle cx="{CX}" cy="{CY}" r="2.6" fill="{INK}"/>
<path d="{star4(0, 0, 10, 3.8)}" fill="{ACCENT}">
  <animateMotion dur="{dur}" repeatCount="indefinite" rotate="0">
    <mpath href="#rose"/>
  </animateMotion>
</path>'''


def static():
    """Rosa completa; Venus fijado en la conjunción de radio máximo."""
    pts = venus_rose()
    far = max(pts, key=lambda p: (p[0] - CX) ** 2 + (p[1] - CY) ** 2)
    return f'''<path d="{path_d(pts)}" stroke="{INK}" fill="none" stroke-width="1.2"
      stroke-linejoin="round" stroke-linecap="round"/>
<circle cx="{CX}" cy="{CY}" r="2.6" fill="{INK}"/>
<path d="{star4(far[0], far[1], 10, 3.8)}" fill="{ACCENT}"/>'''


if __name__ == "__main__":
    write(animated(), "logo-animated.svg")
    write(static(), "logo.svg")
