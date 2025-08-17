import io
from datetime import datetime
from typing import Tuple

from PIL import Image, ImageOps
from flask import Flask, request, send_file, abort
from flask_cors import CORS

# =========================
# Config & Constantes
# =========================
MAX_UPLOAD_MB = 10

# Aceptamos imágenes comunes; la verificación real la hace PIL al abrir.
ALLOWED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}

# Salidas soportadas -> (PIL_SAVE_FORMAT, MIME)
TARGETS = {
    "png":  ("PNG",  "image/png"),
    "jpg":  ("JPEG", "image/jpeg"),
    "jpeg": ("JPEG", "image/jpeg"),
    "webp": ("WEBP", "image/webp"),
    "bmp":  ("BMP",  "image/bmp"),
    "tiff": ("TIFF", "image/tiff"),
}

# Para sugerir opciones según el input (lo usa el frontend, pero dejamos guía)
SUGGESTIONS = {
    ".jpg":  ["png", "webp", "bmp", "tiff"],
    ".jpeg": ["png", "webp", "bmp", "tiff"],
    ".png":  ["jpg", "webp", "bmp", "tiff"],
    ".webp": ["jpg", "png", "bmp", "tiff"],
    ".bmp":  ["jpg", "png", "webp", "tiff"],
    ".tif":  ["jpg", "png", "webp", "bmp"],
    ".tiff": ["jpg", "png", "webp", "bmp"],
    ".gif":  ["png", "webp", "jpg"],  # si es animado, solo primera frame
}

ALLOWED_ORIGINS = [
    "https://zetaconvert.online",
    "https://www.zetaconvert.online",
]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
CORS(app, resources={r"/convert": {"origins": ALLOWED_ORIGINS}})


# =========================
# Helpers
# =========================
def _ext(name: str) -> str:
    return "." + (name.rsplit(".", 1)[-1].lower() if "." in name else "")

def pick_target(raw: str) -> Tuple[str, str]:
    """Valida el target y devuelve (pil_format, mime)."""
    key = (raw or "").lower().strip().lstrip(".")
    if key not in TARGETS:
        abort(415, f"Formato destino no soportado: {raw!r}")
    return TARGETS[key]

def prepare_modes(img: Image.Image, pil_fmt: str) -> Image.Image:
    """Ajusta modos/alpha según formato de salida."""
    if pil_fmt == "JPEG":
        # JPEG no soporta alpha → a RGB con fondo blanco
        if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1])
            return bg
        return img.convert("RGB")
    # Para otros, conservamos alpha si existe
    if img.mode not in ("RGB", "RGBA"):
        # Si trae paleta u otros modos raros, convertimos a RGBA para más robustez
        return img.convert("RGBA")
    return img


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

    pil_fmt, out_mime = pick_target(target_raw)

    # Abrimos y re-orientamos si trae EXIF
    try:
        img = Image.open(f.stream)
        img = ImageOps.exif_transpose(img)
    except Exception:
        abort(400, "El archivo no parece ser una imagen válida")

    # Preparar modo según salida
    img = prepare_modes(img, pil_fmt)

    # Exportar a buffer
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
# =========================
# Main
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
