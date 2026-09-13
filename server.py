from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "submissions"
REVIEWS_FILE = ROOT / "data" / "reviews.json"
PORTFOLIO_DIR = ROOT / "data" / "portfolio"
DATABASE_FILE = ROOT / "data" / "omega.db"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ADMIN_TOKEN = os.environ.get("OMEGA_ADMIN_TOKEN", "")
ADMIN_REGISTRATION_CODE = os.environ.get("OMEGA_ADMIN_REGISTRATION_CODE", "")
SESSION_DAYS = 7
ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt"
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


def safe_filename(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:120] or "archivo"


def read_multipart(handler: "OmegaHandler") -> dict[str, list[dict[str, str]]]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    if content_length > MAX_UPLOAD_BYTES:
        raise ValueError("El envío supera el límite de 25 MB.")

    content_type = handler.headers.get("Content-Type", "")
    if not content_type.startswith("multipart/form-data"):
        raise ValueError("El formulario debe enviarse como multipart/form-data.")

    body = handler.rfile.read(content_length)
    message = BytesParser(policy=default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    )
    fields: dict[str, list[dict[str, str]]] = {}
    for part in message.iter_parts():
        disposition = part.get_content_disposition()
        field_name = part.get_param("name", header="content-disposition")
        if not field_name:
            continue
        filename = part.get_filename()
        value = part.get_payload(decode=True) or b""
        if filename:
            fields.setdefault(field_name, []).append({
                "filename": safe_filename(filename),
                "content_type": part.get_content_type(),
                "content": value,
            })
        elif disposition == "form-data":
            fields.setdefault(field_name, []).append({"value": value.decode("utf-8", "replace")})
    return fields


def read_urlencoded(handler: "OmegaHandler") -> dict[str, str]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    if content_length > 100_000:
        raise ValueError("La opinión supera el límite permitido.")
    body = handler.rfile.read(content_length).decode("utf-8", "replace")
    from urllib.parse import parse_qs
    return {key: values[0] for key, values in parse_qs(body).items() if values}


def load_reviews() -> list[dict]:
    if not REVIEWS_FILE.exists():
        return []
    return json.loads(REVIEWS_FILE.read_text(encoding="utf-8"))


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with database() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('customer', 'admin')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL
            );
        """)


def password_hash(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex(), digest.hex()


def password_matches(password: str, salt_hex: str, expected: str) -> bool:
    _, actual = password_hash(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(actual, expected)


def request_user(handler: "OmegaHandler") -> sqlite3.Row | None:
    cookie = SimpleCookie(handler.headers.get("Cookie", ""))
    token = cookie.get("omega_session")
    if not token:
        return None
    with database() as connection:
        return connection.execute(
            "SELECT users.id, users.name, users.email, users.role FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token = ? AND sessions.expires_at > ?",
            (token.value, datetime.now(timezone.utc).isoformat()),
        ).fetchone()


def session_cookie(token: str, max_age: int = SESSION_DAYS * 86400) -> str:
    return f"omega_session={token}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Lax"


class OmegaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, status: int, payload: dict, headers: dict[str, str] | None = None) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/register":
            try:
                fields = read_urlencoded(self)
                name = fields.get("nombre", "").strip()
                email = fields.get("correo", "").strip().lower()
                password = fields.get("password", "")
                role = fields.get("rol", "customer").strip()
                registration_code = fields.get("codigo_admin", "")
                if len(name) < 2 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                    raise ValueError("Indica un nombre y un correo válidos.")
                if len(password) < 8:
                    raise ValueError("La contraseña debe tener al menos 8 caracteres.")
                if role not in {"customer", "admin"}:
                    raise ValueError("Tipo de cuenta no válido.")
                if role == "admin" and (not ADMIN_REGISTRATION_CODE or not secrets.compare_digest(registration_code, ADMIN_REGISTRATION_CODE)):
                    raise ValueError("El código de administrador no es válido.")
                salt, hashed = password_hash(password)
                with database() as connection:
                    connection.execute(
                        "INSERT INTO users (name, email, password_hash, salt, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (name[:100], email, hashed, salt, role, datetime.now(timezone.utc).isoformat()),
                    )
                self.send_json(201, {"message": "Cuenta creada. Ya puedes iniciar sesión."})
            except sqlite3.IntegrityError:
                self.send_json(409, {"error": "Ese correo ya tiene una cuenta."})
            except (ValueError, OSError) as error:
                self.send_json(400, {"error": str(error)})
            return

        if path == "/api/login":
            try:
                fields = read_urlencoded(self)
                email = fields.get("correo", "").strip().lower()
                password = fields.get("password", "")
                with database() as connection:
                    user = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
                if not user or not password_matches(password, user["salt"], user["password_hash"]):
                    self.send_json(401, {"error": "Correo o contraseña incorrectos."})
                    return
                token = secrets.token_urlsafe(32)
                expires_at = datetime.now(timezone.utc).timestamp() + SESSION_DAYS * 86400
                expires_iso = datetime.fromtimestamp(expires_at, timezone.utc).isoformat()
                with database() as connection:
                    connection.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user["id"], expires_iso))
                self.send_json(200, {"message": "Sesión iniciada.", "user": {"name": user["name"], "email": user["email"], "role": user["role"]}}, {"Set-Cookie": session_cookie(token)})
            except (ValueError, OSError) as error:
                self.send_json(400, {"error": str(error)})
            return

        if path == "/api/logout":
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie.get("omega_session")
            if token:
                with database() as connection:
                    connection.execute("DELETE FROM sessions WHERE token = ?", (token.value,))
            self.send_json(200, {"message": "Sesión cerrada."}, {"Set-Cookie": session_cookie("", 0)})
            return

        if path == "/api/review":
            try:
                fields = read_urlencoded(self)
                name = fields.get("nombre", "").strip()
                comment = fields.get("comentario", "").strip()
                rating = fields.get("valoracion", "5").strip()
                if not name or not comment or rating not in {"1", "2", "3", "4", "5"}:
                    raise ValueError("Nombre, comentario y valoración válida son obligatorios.")
                reviews = load_reviews()
                reviews.insert(0, {
                    "id": uuid.uuid4().hex[:10],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "name": name[:80],
                    "comment": comment[:1000],
                    "rating": int(rating),
                })
                REVIEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
                REVIEWS_FILE.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
                self.send_json(201, {"message": "Gracias por compartir tu opinión."})
            except (ValueError, OSError, json.JSONDecodeError) as error:
                self.send_json(400, {"error": str(error)})
            return

        if path == "/api/portfolio":
            try:
                if not ADMIN_TOKEN or self.headers.get("X-Admin-Token") != ADMIN_TOKEN:
                    self.send_json(403, {"error": "Token de administrador inválido o no configurado."})
                    return
                fields = read_multipart(self)
                title = fields.get("titulo", [{}])[0].get("value", "Proyecto OMEGA").strip()[:120]
                uploads = fields.get("imagen", [])
                if not uploads:
                    raise ValueError("Selecciona al menos una imagen.")
                portfolio_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
                portfolio_dir = PORTFOLIO_DIR / portfolio_id
                portfolio_dir.mkdir(parents=True, exist_ok=False)
                saved = []
                for upload in uploads:
                    filename = upload["filename"]
                    if Path(filename).suffix.lower() not in IMAGE_EXTENSIONS:
                        raise ValueError(f"Solo se permiten imágenes: {filename}")
                    (portfolio_dir / filename).write_bytes(upload["content"])
                    saved.append({"name": filename, "url": f"/portfolio/{portfolio_id}/{filename}"})
                record = {"id": portfolio_id, "title": title, "images": saved}
                (portfolio_dir / "portfolio.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                self.send_json(201, {"message": "Imagen añadida al portafolio.", "item": record})
            except (ValueError, OSError) as error:
                self.send_json(400, {"error": str(error)})
            return

        if path != "/api/contact":
            self.send_json(404, {"error": "Ruta no encontrada."})
            return

        try:
            fields = read_multipart(self)
            name = fields.get("nombre", [{}])[0].get("value", "").strip()
            email = fields.get("correo", [{}])[0].get("value", "").strip()
            message = fields.get("mensaje", [{}])[0].get("value", "").strip()
            team = fields.get("equipo", [{}])[0].get("value", "Por definir").strip()
            if not name or not email or not message:
                raise ValueError("Nombre, correo y mensaje son obligatorios.")

            submission_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
            submission_dir = DATA_DIR / submission_id
            submission_dir.mkdir(parents=True, exist_ok=False)
            saved_files = []
            for upload in fields.get("adjuntos", []):
                filename = upload["filename"]
                if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
                    raise ValueError(f"Tipo de archivo no permitido: {filename}")
                file_path = submission_dir / filename
                file_path.write_bytes(upload["content"])
                saved_files.append({
                    "name": filename,
                    "content_type": upload["content_type"],
                    "size": len(upload["content"]),
                })

            record = {
                "id": submission_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "name": name,
                "email": email,
                "team": team,
                "message": message,
                "attachments": saved_files,
            }
            (submission_dir / "submission.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self.send_json(201, {"message": "Consulta recibida. Te responderemos pronto.", "id": submission_id})
        except (ValueError, OSError) as error:
            self.send_json(400, {"error": str(error)})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/omega.creative.html")
            self.end_headers()
            return
        if path == "/api/me":
            user = request_user(self)
            if not user:
                self.send_json(401, {"error": "No hay una sesión activa."})
                return
            self.send_json(200, {"user": dict(user)})
            return
        if path == "/api/reviews":
            try:
                self.send_json(200, {"reviews": load_reviews()})
            except (OSError, json.JSONDecodeError) as error:
                self.send_json(500, {"error": str(error)})
            return
        if path == "/api/portfolio":
            try:
                items = []
                if PORTFOLIO_DIR.exists():
                    for metadata in sorted(PORTFOLIO_DIR.glob("*/portfolio.json"), reverse=True):
                        items.append(json.loads(metadata.read_text(encoding="utf-8")))
                self.send_json(200, {"items": items})
            except (OSError, json.JSONDecodeError) as error:
                self.send_json(500, {"error": str(error)})
            return
        if path.startswith("/portfolio/"):
            candidate = (PORTFOLIO_DIR / path.removeprefix("/portfolio/")).resolve()
            try:
                candidate.relative_to(PORTFOLIO_DIR.resolve())
            except ValueError:
                self.send_json(403, {"error": "Ruta no permitida."})
                return
            if not candidate.exists() or candidate.is_dir():
                self.send_json(404, {"error": "Archivo no encontrado."})
                return
            self.path = str(candidate.relative_to(ROOT)).replace("\\", "/")
        super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend local de OMEGA Creative")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), OmegaHandler)
    print(f"OMEGA Creative disponible en http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
