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
  - logo.svg — emblema estático (reserva, usos chicos): la rosa completa con Venus fijado en la
    conjunción de radio máximo.
  - favicon.svg — marca reducida (anillo/órbita + Venus) que lee a 16-32 px (la rosa completa se
    emborrona a ese tamaño).
  - social-preview.svg — tarjeta 1280×640 papel-antiguo para GitHub (Settings → Social preview).
    Usa fuentes GFS Didot + EB Garamond; el PNG se rasteriza aparte (se sube a mano).
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


def write(body, name, vb="0 0 320 320", w=320, h=320):
    doc = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" '
           f'width="{w}" height="{h}">\n' + body + "\n</svg>\n")
    (OUT / name).write_text(doc, encoding="utf-8")
    print(f"  docs/assets/{name}")


def rose_body(ink):
    """Rosa completa + Venus (ámbar) en la conjunción de radio máximo — cuerpo reutilizable."""
    pts = venus_rose()
    far = max(pts, key=lambda p: (p[0] - CX) ** 2 + (p[1] - CY) ** 2)
    return (f'<path d="{path_d(pts)}" stroke="{ink}" fill="none" stroke-width="1.25" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{CX}" cy="{CY}" r="2.6" fill="{ink}"/>'
            f'<path d="{star4(far[0], far[1], 10, 3.8)}" fill="{ACCENT}"/>')


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


def favicon():
    """Marca chica que lee a 16-32 px: anillo/órbita neutro + Venus (ámbar) arriba + centro.
    La rosa completa se emborrona a tamaño favicon; esta es su reducción legible."""
    return (f'<circle cx="32" cy="32" r="22" fill="none" stroke="{INK}" stroke-width="2.6"/>'
            f'<circle cx="32" cy="32" r="3" fill="{INK}"/>'
            f'<path d="{star4(32, 10, 9, 3.4)}" fill="{ACCENT}"/>')


def social_preview():
    """Tarjeta 1280×640 (GitHub → Settings → Social preview). Lámina papel-antiguo: la rosa
    a la izquierda, ALMAGESTO (GFS Didot) + el etimón griego ἡ Μεγίστη + tagline a la derecha,
    dentro de un marco de lámina. Requiere las fuentes GFS Didot y EB Garamond al rasterizar a
    PNG (el .png commiteado es ese render; el .svg es la fuente)."""
    PAPER, SEPIA, FRAME = "#efe6d3", "#574a35", "#8a795a"
    return (f'<rect width="1280" height="640" fill="{PAPER}"/>'
            f'<rect x="34" y="34" width="1212" height="572" fill="none" stroke="{FRAME}" stroke-width="1.5"/>'
            f'<rect x="42" y="42" width="1196" height="556" fill="none" stroke="{FRAME}" stroke-width="0.8"/>'
            f'<g transform="translate(120 60) scale({520 / 320})">{rose_body(SEPIA)}</g>'
            f'<g font-family="GFS Didot"><text x="700" y="280" font-size="72" fill="#3a2f1c" '
            f'letter-spacing="5">ALMAGESTO</text></g>'
            f'<text x="702" y="330" font-family="GFS Didot" font-size="33" fill="#8a5a1e" '
            f'font-style="italic">ἡ Μεγίστη</text>'
            f'<line x1="702" y1="356" x2="1120" y2="356" stroke="{ACCENT}" stroke-width="1.6"/>'
            f'<g font-family="EB Garamond" fill="#6b5d48" font-size="29">'
            f'<text x="702" y="402">Wiki de conocimiento astronómico</text>'
            f'<text x="702" y="440">mantenida por un LLM · patrón LLM Wiki</text></g>')


if __name__ == "__main__":
    write(animated(), "logo-animated.svg")
    write(static(), "logo.svg")
    write(favicon(), "favicon.svg", vb="0 0 64 64", w=64, h=64)
    write(social_preview(), "social-preview.svg", vb="0 0 1280 640", w=1280, h=640)
