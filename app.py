# ... imports existentes ...
import math

# ====== NUEVO: helper para “borrar” fondo sin IA ======
def avg_corner_bg(img):
    """Promedia color de las 4 esquinas (RGB)."""
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    corners = [
        px[0, 0],
        px[w-1, 0],
        px[0, h-1],
        px[w-1, h-1],
    ]
    # si vienen RGBA, ignoramos A al promediar
    rgb = [(c[0], c[1], c[2]) for c in corners]
    r = sum(c[0] for c in rgb) / 4
    g = sum(c[1] for c in rgb) / 4
    b = sum(c[2] for c in rgb) / 4
    return (r, g, b)

def remove_bg_simple(img, tolerance=30):
    """
    Hace transparente lo similar al color promedio de las esquinas.
    tolerance: 0-100 (usuario). Internamente mapeamos a 0-255.
    """
    tol = max(0, min(100, int(tolerance)))
    # mapear 0..100 a 0..150 (rango útil razonable)
    thr = int(1.5 * tol)  # 0..150 aprox
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    bg = avg_corner_bg(img)
    w, h = img.size
    src = img.load()

    # construimos nueva imagen con alfa
    out = Image.new("RGBA", (w, h))
    dst = out.load()

    for y in range(h):
        for x in range(w):
            r, g, b, a = src[x, y]
            # distancia manhattan (rápida y suficiente)
            d = abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])
            # si es “parecido” al fondo → alfa 0
            if d <= thr:
                dst[x, y] = (r, g, b, 0)
            else:
                dst[x, y] = (r, g, b, a)
    return out
