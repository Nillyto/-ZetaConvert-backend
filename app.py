import io
from datetime import datetime

from PIL import Image
from flask import Flask, request, send_file, abort
from flask_cors import CORS

# =========================
# Config & Constantes
# =========================
MAX_UPLOAD_MB = 10
ALLOWED_MIMES = {"image/jpeg", "image/jpg"}
ALLOWED_EXTS = {".jpg", ".jpeg"}
ALLOWED_ORIGINS = [
    "https://zetaconvert.online",
    "https://www.zetaconvert.online",
]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# Permitir solo tu dominio (más seguro)
CORS(app, resources={r"/convert": {"origins": ALLOWED_ORIGINS}})


# =========================
# Helpers
# =========================
def is_allowed(filename: str, mime: str) -> bool:
    """
    Valida por extensión y mimetype conocido.
    Ojo: algunos navegadores no envían mimetype confiable;
    por eso la verificación real es abrir con PIL en el try/except.
    """
    name = (filename or "").lower()
    ext_ok = name.endswith(".jpg") or name.endswith(".jpeg")
    mime_ok = (mime or "") in ALLOWED_MIMES
    return ext_ok and (mime_ok or True)  # aceptamos aunque no venga mimetype


# =========================
# Rutas
# =========================
@app.get("/")
def health():
    return {
        "ok": True,
        "service": "jpg-to-png",
        "ts": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/convert")
def convert():
    if "file" not in request.files:
        abort(400, "No file field found")

    f = request.files["file"]
    if not f or f.filename == "":
        abort(400, "No file selected")

    # Validación liviana (igual intentamos abrir con PIL más abajo)
    if not is_allowed(f.filename, f.mimetype or ""):
        # Si quisieras cortar acá: abort(415, "Formato no soportado: use JPG/JPEG")
        pass

    # Intentamos abrir con PIL (validación real)
    try:
        img = Image.open(f.stream).convert("RGBA")  # soporta JPG progresivo, etc.
    except Exception:
        abort(400, "El archivo no parece ser un JPG válido")

    # Exportar a PNG en memoria
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    base = f.filename.rsplit(".", 1)[0] or "convertido"
    out_name = f"{base}.png"

    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name=out_name,
        max_age=0,
    )


# =========================
# Main
# =========================
if __name__ == "__main__":
    # Para correr local:
    app.run(host="0.0.0.0", port=5000, debug=True)
