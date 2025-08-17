import io
from datetime import datetime
from PIL import Image
from flask import Flask, request, send_file, abort

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

ALLOWED_MIMES = {"image/jpeg", "image/jpg"}
ALLOWED_EXTS = {".jpg", ".jpeg"}

def is_allowed(filename: str, mime: str) -> bool:
    name = (filename or "").lower()
    return (mime in ALLOWED_MIMES) and (name.endswith(".jpg") or name.endswith(".jpeg"))

@app.route("/", methods=["GET"])
def health():
    return {"ok": True, "service": "jpg-to-png", "ts": datetime.utcnow().isoformat() + "Z"}

@app.route("/convert", methods=["POST"])
def convert():
    if "file" not in request.files:
        abort(400, "No file field found")

    f = request.files["file"]

    if not f or f.filename == "":
        abort(400, "No file selected")

    # Nota: algunos navegadores no mandan mimetype confiable; validamos por extensión + intentamos abrir con PIL.
    if not is_allowed(f.filename, f.mimetype or ""):
        # igual intentamos abrir por si viene sin mimetype; si falla, abortamos
        pass

    try:
        img = Image.open(f.stream).convert("RGBA")  # soporta JPG progresivo, etc.
    except Exception:
        abort(400, "El archivo no parece ser un JPG válido")

    # Exportar a PNG en memoria
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    # nombre de salida: mismo nombre pero .png
    base = f.filename.rsplit(".", 1)[0] or "convertido"
    out_name = f"{base}.png"

    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name=out_name,
        max_age=0,
    )

if __name__ == "__main__":
    # Para correr local:
    app.run(host="0.0.0.0", port=5000, debug=True)
