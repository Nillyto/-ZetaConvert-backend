import io
from datetime import datetime
from typing import Tuple

from PIL import Image, ImageOps
from flask import Flask, request, send_file, abort
from flask_cors import CORS

# =========================
# Config & Constantes
# =========================
MAX_UPLOAD_MB = 10  # límite de subida

# Formatos de salida soportados -> (PIL_SAVE_FORMAT, MIME)
TARGETS = {
    "png":  ("PNG",  "image/png"),
    "jpg":  ("JPEG", "image/jpeg"),
    "jpeg": ("JPEG", "image/jpeg"),
    "webp": ("WEBP", "image/webp"),
    "bmp":  ("BMP",  "image/bmp"),
    "tiff": ("TIFF", "image/tiff"),
}

ALLOWED_ORIGINS = [
    "https://zetaconvert.online",
    "https://www.zetaconvert.online",
]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
CORS(app, resources={r"/convert": {"origins": ALLOWED_ORIGINS}})

# =========================
# Helpers base
# =========================
def pick_target(raw: str) -> Tuple[str, str]:
    """Valida el target y devuelve (pil_format, mime)."""
    key = (raw or "").lower().strip().lstrip(".")
    if key not in TARGETS:
        abort(415, f"Formato destino no soportado: {raw!r}")
    return TARGETS[key]

def prepare_modes(img: Image.Image, pil_fmt: str) -> Image.Image:
    """Ajusta modos/alpha según formato de salida."""
    if pil_fmt == "JPEG":
        # JPEG no soporta alpha → convertir a RGB con fondo blanco si hace falta
        if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1])
            return bg
        return img.convert("RGB")
    if img.mode not in ("RGB", "RGBA"):
        return img.convert("RGBA")
    return img

# =========================
# Remove background (sin IA)
# =========================
def hex_to_rgb(h: str):
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join([c * 2 for c in h])  # #abc -> #aabbcc
    if len(h) != 6:
        abort(400, "Color inválido; usar #RRGGBB")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def color_dist(c, ref):
    return abs(c[0] - ref[0]) + abs(c[1] - ref[1]) + abs(c[2] - ref[2])

def avg_border_color(img: Image.Image):
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    total = [0, 0, 0]; count = 0
    for x in range(w):
        for y in (0, h - 1):
          r, g, b = px[x, y][:3]
          total[0] += r; total[1] += g; total[2] += b; count += 1
    for y in range(h):
        for x in (0, w - 1):
          r, g, b = px[x, y][:3]
          total[0] += r; total[1] += g; total[2] += b; count += 1
    return (total[0] // count, total[1] // count, total[2] // count)

def remove_bg_floodfill(img: Image.Image, tolerance=30, ref_color=None):
    """
    Hace transparente lo conectado al BORDE con color similar al de referencia.
    - ref_color: (R,G,B) o None → usa promedio del borde
    - tolerance: 0..100 (mapeado interno ~0..210)
    """
    tol = max(0, min(100, int(tolerance)))
    thr = int(2.1 * tol)

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    w, h = img.size
    px = img.load()

    if ref_color is None:
        ref_color = avg_border_color(img)

    visited = [[False] * w for _ in range(h)]
    make_transp = [[False] * w for _ in range(h)]

    from collections import deque
    q = deque()

    def try_push(x, y):
        if 0 <= x < w and 0 <= y < h and not visited[y][x]:
            r, g, b, a = px[x, y]
            if color_dist((r, g, b), ref_color) <= thr:
                visited[y][x] = True
                make_transp[y][x] = True
                q.append((x, y))

    for x in range(w):
        try_push(x, 0); try_push(x, h - 1)
    for y in range(h):
        try_push(0, y); try_push(w - 1, y)

    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx]:
                r, g, b, a = px[nx, ny]
                if color_dist((r, g, b), ref_color) <= thr:
                    visited[ny][nx] = True
                    make_transp[ny][nx] = True
                    q.append((nx, ny))
                else:
                    visited[ny][nx] = True

    out = Image.new("RGBA", (w, h))
    dst = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            dst[x, y] = (r, g, b, 0) if make_transp[y][x] else (r, g, b, a)
    return out

# =========================
# Rutas
# =========================
@app.get("/")
def health():
    return {
        "ok": True,
        "service": "multi-image-convert",
        "ts": datetime.utcnow().isoformat() + "Z",
        "max_mb": MAX_UPLOAD_MB,
        "targets": sorted(TARGETS.keys()),
    }

@app.post("/convert")
def convert():
    if "file" not in request.files:
        abort(400, "No file field found")

    f = request.files["file"]
    if not f or f.filename == "":
        abort(400, "No file selected")

    target_raw = request.form.get("target") or request.args.get("target")
    if not target_raw:
        abort(400, "Falta el parámetro 'target' (png, jpg, webp, bmp, tiff)")

    remove_bg = (request.form.get("remove_bg") == "1") or (request.args.get("remove_bg") == "1")
    tolerance = int(request.form.get("tolerance", "30"))
    mode = (request.form.get("remove_bg_mode") or "auto").lower()  # "auto" | "color"
    ref_hex = request.form.get("ref_color")  # "#RRGGBB"

    pil_fmt, out_mime = pick_target(target_raw)

    try:
        img = Image.open(f.stream)
        img = ImageOps.exif_transpose(img)  # corrige orientación
    except Exception:
        abort(400, "El archivo no parece ser una imagen válida")

    if remove_bg and pil_fmt != "PNG":
        abort(400, "La opción 'eliminar fondo' solo funciona al convertir a PNG")

    img = prepare_modes(img, pil_fmt)

    if remove_bg and pil_fmt == "PNG":
        ref = None
        if mode == "color":
            ref = hex_to_rgb(ref_hex)
        img = remove_bg_floodfill(img, tolerance=tolerance, ref_color=ref)

    buf = io.BytesIO()
    save_kwargs = {}
    if pil_fmt == "PNG":
        save_kwargs.update(optimize=True)
    elif pil_fmt == "JPEG":
        save_kwargs.update(quality=90, optimize=True, progressive=True)
    elif pil_fmt == "WEBP":
        save_kwargs.update(quality=90, method=6)

    try:
        img.save(buf, format=pil_fmt, **save_kwargs)
    except Exception:
        abort(500, "No se pudo convertir la imagen al formato solicitado")

    buf.seek(0)
    base = f.filename.rsplit(".", 1)[0] or "convertido"
    out_ext = "." + (target_raw.lower().lstrip("."))
    out_name = f"{base}{out_ext}"

    return send_file(
        buf,
        mimetype=out_mime,
        as_attachment=True,
        download_name=out_name,
        max_age=0,
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
