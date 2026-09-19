from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any

import psycopg
import qrcode
from flask import Flask, Response, abort, g, jsonify, redirect, render_template, request, session
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent

def load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SECRET_KEY = os.environ.get("KLIKTECH_SECRET_KEY", "").strip()
ADMIN_PASSWORD = os.environ.get("KLIKTECH_ADMIN_PASSWORD", "").strip()
ADMIN_PATH = os.environ.get("KLIKTECH_ADMIN_PATH", "ademiroputo").strip().strip("/") or "ademiroputo"
ADMIN_TOTP_SECRET = os.environ.get("KLIKTECH_ADMIN_TOTP_SECRET", "").strip().replace(" ", "").upper()
ADMIN_TOTP_ISSUER = os.environ.get("KLIKTECH_ADMIN_TOTP_ISSUER", "KlikTech")
WEB_ORIGIN = os.environ.get("KLIKTECH_PUBLIC_ORIGIN", "").strip().rstrip("/")
COOKIE_SECURE = os.environ.get("KLIKTECH_COOKIE_SECURE", "1") == "1"
BRAVOPAY_API_KEY = os.environ.get("BRAVOPAY_API_KEY", "").strip()
BRAVOPAY_WEBHOOK_SECRET = os.environ.get("BRAVOPAY_WEBHOOK_SECRET", "").strip()
COMPANY_CNPJ = os.environ.get("KLIKTECH_CNPJ", "não informado").strip()

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não configurada. Defina uma URL PostgreSQL.")
if not SECRET_KEY:
    raise RuntimeError("KLIKTECH_SECRET_KEY não configurada. Gere uma chave forte.")
if not ADMIN_PASSWORD:
    raise RuntimeError("KLIKTECH_ADMIN_PASSWORD não configurada. Defina uma senha forte.")

app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")
app.config.update(
    SECRET_KEY=SECRET_KEY,
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    SESSION_COOKIE_SAMESITE="Lax",
    TEMPLATES_AUTO_RELOAD=False,
)


@app.context_processor
def template_context():
    return {"admin_path": ADMIN_PATH, "company_cnpj": COMPANY_CNPJ}

DEFAULT_PLANS = {
    "30GB · 1 mês": 2000,
    "45GB · 1 mês": 3000,
    "30GB · 2 meses": 4000,
    "45GB · 2 meses": 5000,
}
RATE_LIMITS = {
    "default": (60, 60),
    "login": (5, 300),
    "register": (5, 3600),
    "webhook": (30, 60),
}
RATE_BUCKETS: dict[str, list[float]] = {}
LOGIN_FAILURES: dict[str, list[float]] = {}
MAX_LOGIN_FAILURES = 5
BLOCK_DURATION = timedelta(minutes=15)
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def db():
    connection = g.get("db")
    if connection is None or connection.closed:
        connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        g.db = connection
    return connection


@app.teardown_appcontext
def close_db(_error: Any = None) -> None:
    connection = g.pop("db", None)
    if connection and not connection.closed:
        connection.close()


def sql(query: str) -> str:
    """Compatibility conversion for the few legacy SQL expressions still used."""
    query = query.replace("?", "%s")
    query = query.replace("status=\"PAID\"", "status='PAID'")
    return query


def query(statement: str, params: tuple[Any, ...] = (), *, connection=None):
    return (connection or db()).execute(sql(statement), params)


def _json_error(message: str, status: int):
    return jsonify(error=message), status


def client_ip() -> str:
    # Only trust X-Forwarded-For when explicitly configured behind the platform proxy.
    if os.environ.get("KLIKTECH_TRUST_PROXY", "1") == "1":
        return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()[:128]
    return (request.remote_addr or "unknown")[:128]


def request_origin_is_valid() -> bool:
    origin = (request.headers.get("Origin") or "").rstrip("/")
    expected = WEB_ORIGIN or request.host_url.rstrip("/")
    return bool(origin and hmac.compare_digest(origin, expected))


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def enforce_rate_limit(bucket: str, limit: int, window: int) -> bool:
    key = f"{bucket}:{client_ip()}"
    now = time.time()
    values = [stamp for stamp in RATE_BUCKETS.get(key, []) if now - stamp < window]
    allowed = len(values) < limit
    values.append(now)
    RATE_BUCKETS[key] = values[-limit - 1 :]
    return allowed


def is_state_changing() -> bool:
    return request.method in {"POST", "PUT", "PATCH", "DELETE"}


def check_totp(secret: str, code: str, *, at: int | None = None) -> bool:
    if not secret or not re.fullmatch(r"\d{6}", code or ""):
        return False
    try:
        raw_secret = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    except Exception:
        return False
    timestamp = int(at if at is not None else time.time()) // 30
    for offset in (-1, 0, 1):
        counter = (timestamp + offset).to_bytes(8, "big")
        digest = hmac.new(raw_secret, counter, hashlib.sha1).digest()
        start = digest[-1] & 0x0F
        number = int.from_bytes(digest[start : start + 4], "big") & 0x7FFFFFFF
        if hmac.compare_digest(f"{number % 1_000_000:06d}", code):
            return True
    return False


def configured_admin_2fa() -> bool:
    return bool(ADMIN_TOTP_SECRET)


def safe_user(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row.get("public_id"),
        "name": row["name"],
        "email": row["email"],
        "balance": int(row.get("balance_cents", 0)) / 100,
        "profile_photo_url": "/api/account/profile/photo" if row.get("profile_photo") else None,
    }


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return "—"
    local, domain = email.split("@", 1)
    return f"{local[:2]}***@{domain}"


def catalog_prices(active_only: bool = True) -> dict[str, int]:
    try:
        where = " WHERE active=TRUE" if active_only else ""
        rows = query(f"SELECT plan,price_cents FROM plan_catalog{where} ORDER BY id").fetchall()
        return {row["plan"]: int(row["price_cents"]) for row in rows}
    except Exception:
        return DEFAULT_PLANS.copy()


def catalog_rows(active_only: bool = True):
    where = " WHERE active=TRUE" if active_only else ""
    return query(
        f"SELECT id,plan,gigas,tempo,price_cents,active,featured,created_at FROM plan_catalog{where} ORDER BY id"
    ).fetchall()


def image_bytes(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    mime = (file_storage.mimetype or "").lower()
    if mime not in IMAGE_TYPES:
        raise ValueError("Apenas JPG, PNG ou WebP são aceitos.")
    data = file_storage.read()
    if not data or len(data) > 5 * 1024 * 1024:
        raise ValueError("A imagem está vazia ou excede 5 MB.")
    # Magic bytes are checked independently from the client-provided MIME type.
    valid = (
        (mime == "image/jpeg" and data.startswith(b"\xff\xd8\xff"))
        or (mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"))
        or (mime == "image/webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    )
    if not valid:
        raise ValueError("O conteúdo do arquivo não corresponde a uma imagem válida.")
    return data, mime


def require_own_purchase(purchase_id: int):
    row = query(
        "SELECT p.id,p.inventory_id FROM purchases p WHERE p.id=? AND p.user_id=?",
        (purchase_id, g.user["id"]),
    ).fetchone()
    if not row:
        abort(404)
    return row


def purchase_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "plan": row["plan"],
        "price": int(row["price_cents"]) / 100,
        "date": row["created_at"],
        "model": row["model"],
        "line": row["line"],
        "ddd": row["ddd"],
        "smdp": row["smdp"],
        "activation_code": row["activation_code"],
        "photo_url": f"/api/account/purchases/{row['id']}/photo" if row.get("photo") else None,
        "qr_url": f"/api/account/purchases/{row['id']}/qr",
    }


@app.before_request
def before_request():
    forwarded_proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",", 1)[0].strip().lower()
    if WEB_ORIGIN.startswith("https://") and forwarded_proto != "https" and request.endpoint != "healthz":
        target = f"{WEB_ORIGIN}{request.full_path.rstrip('?')}"
        return redirect(target, code=308)

    g.user = None
    user_id = session.get("user_id")
    if user_id:
        g.user = query("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not g.user:
            session.clear()
        elif g.user.get("blocked_at") and request.endpoint not in {"login", "logout"}:
            session.clear()
            return _json_error("Esta conta está bloqueada.", 403) if request.path.startswith("/api/") else render_template(
                "error.html", code=403, title="Conta bloqueada", message="O acesso desta conta foi bloqueado pelo administrador."
            ), 403

    if is_state_changing() and request.endpoint != "bravopay_webhook":
        if not request_origin_is_valid():
            return _json_error("Origem da requisição não autorizada.", 403)
        supplied = request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf_token", "")
        if not expected or not supplied or not hmac.compare_digest(supplied, expected):
            return _json_error("Token CSRF inválido ou ausente.", 403)

    if request.endpoint and is_state_changing() and request.endpoint != "bravopay_webhook":
        bucket = "login" if request.endpoint == "login" else "register" if request.endpoint == "register" else "default"
        limit, window = RATE_LIMITS[bucket]
        if not enforce_rate_limit(bucket, limit, window):
            return _json_error("Muitas tentativas. Aguarde e tente novamente.", 429)

    if request.endpoint == "bravopay_webhook" and not enforce_rate_limit("webhook", *RATE_LIMITS["webhook"]):
        return _json_error("Muitas requisições.", 429)

    if g.user:
        try:
            query(
                "INSERT INTO access_logs(user_id,ip,user_agent) VALUES(%s,%s,%s)",
                (g.user["id"], client_ip(), (request.headers.get("User-Agent") or "")[:500]),
            )
        except Exception:
            db().rollback()

    if request.path.startswith("/api/admin/") and not (g.user and g.user.get("is_admin")):
        return _json_error("Área administrativa protegida.", 403)

    if g.user and request.path.startswith("/api/admin/") and not session.get("admin_2fa_ok"):
        return _json_error("A autenticação de dois fatores do administrador é obrigatória.", 403)

    if g.user and g.user.get("is_admin") and request.path.startswith("/api/admin/") and not configured_admin_2fa():
        return _json_error("2FA administrativo não configurado.", 403)


def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; script-src 'self'; connect-src 'self'",
    )
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.path.startswith("/api/") or request.path.startswith(f"/{ADMIN_PATH}"):
        response.headers["Cache-Control"] = "private, no-store"
    return response


app.after_request(security_headers)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            return _json_error("Faça login para continuar.", 401)
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user or not g.user.get("is_admin"):
            return _json_error("Área administrativa protegida.", 403)
        if not configured_admin_2fa() or not session.get("admin_2fa_ok"):
            return _json_error("A autenticação de dois fatores do administrador é obrigatória.", 403)
        return view(*args, **kwargs)
    return wrapped


def init_db():
    connection = db()
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            balance_cents BIGINT NOT NULL DEFAULT 0 CHECK (balance_cents >= 0),
            is_admin INTEGER NOT NULL DEFAULT 0,
            public_id TEXT UNIQUE,
            profile_photo BYTEA,
            profile_photo_mime TEXT,
            blocked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wallet_charges (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id),
            provider_id TEXT UNIQUE NOT NULL,
            external_reference TEXT UNIQUE NOT NULL,
            amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
            status TEXT NOT NULL DEFAULT 'PENDING',
            pix_copy_paste TEXT,
            expires_at TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wallet_ledger (
            id BIGSERIAL PRIMARY KEY,
            event_id TEXT UNIQUE NOT NULL,
            user_id BIGINT NOT NULL REFERENCES users(id),
            provider_id TEXT,
            amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
            kind TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS carts (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(id),
            session_key TEXT,
            plan TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS plan_catalog (
            id BIGSERIAL PRIMARY KEY,
            plan TEXT UNIQUE NOT NULL,
            gigas TEXT NOT NULL,
            tempo TEXT NOT NULL,
            price_cents BIGINT NOT NULL CHECK (price_cents > 0),
            active BOOLEAN NOT NULL DEFAULT TRUE,
            featured BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id BIGSERIAL PRIMARY KEY,
            plan TEXT NOT NULL,
            model TEXT NOT NULL,
            line TEXT,
            ddd TEXT,
            photo BYTEA,
            photo_mime TEXT,
            smdp TEXT NOT NULL,
            activation_code TEXT UNIQUE NOT NULL,
            sold_at TIMESTAMPTZ,
            sold_to BIGINT REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS purchases (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id),
            inventory_id BIGINT NOT NULL REFERENCES inventory(id),
            plan TEXT NOT NULL,
            price_cents BIGINT NOT NULL CHECK (price_cents > 0),
            status TEXT NOT NULL DEFAULT 'approved',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (inventory_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS access_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(id),
            ip TEXT NOT NULL,
            user_agent TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS admin_events (
            id BIGSERIAL PRIMARY KEY,
            event TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]
    for statement in statements:
        connection.execute(statement)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_inventory_available ON inventory(plan, ddd) WHERE sold_at IS NULL")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id, id DESC)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_wallet_charges_provider ON wallet_charges(provider_id)")
    connection.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked_at TIMESTAMPTZ")
    admin_email = os.environ.get("KLIKTECH_ADMIN_EMAIL", "admin@kliktech.local").strip().lower()
    existing = connection.execute("SELECT id FROM users WHERE email=%s", (admin_email,)).fetchone()
    password_hash = generate_password_hash(ADMIN_PASSWORD)
    if existing:
        connection.execute(
            "UPDATE users SET name=%s,password_hash=%s,is_admin=1 WHERE id=%s",
            ("Administrador", password_hash, existing["id"]),
        )
    else:
        admin = connection.execute("SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1").fetchone()
        if admin:
            connection.execute(
                "UPDATE users SET email=%s,name=%s,password_hash=%s,is_admin=1 WHERE id=%s",
                (admin_email, "Administrador", password_hash, admin["id"]),
            )
        else:
            connection.execute(
                "INSERT INTO users(email,name,password_hash,is_admin,public_id) VALUES(%s,%s,%s,1,%s)",
                (admin_email, "Administrador", password_hash, secrets.token_urlsafe(9)),
            )
    for label, price in DEFAULT_PLANS.items():
        gigas, tempo = label.split(" · ", 1)
        connection.execute(
            "INSERT INTO plan_catalog(plan,gigas,tempo,price_cents,active,featured) VALUES(%s,%s,%s,%s,TRUE,%s) ON CONFLICT (plan) DO NOTHING",
            (label, gigas, tempo, price, label == "45GB · 1 mês"),
        )
    connection.commit()


@app.get("/")
def store():
    return render_template("index.html", csrf_token=csrf_token())


@app.get("/termos")
def terms():
    return render_template("legal.html", title="Termos de uso", heading="Termos de uso")


@app.get("/privacidade")
def privacy():
    return render_template("legal.html", title="Privacidade e LGPD", heading="Privacidade e LGPD")


@app.get("/reembolso")
def refunds():
    return render_template("legal.html", title="Política de reembolso", heading="Política de reembolso")


@app.get("/robots.txt")
def robots():
    origin = WEB_ORIGIN or request.host_url.rstrip("/")
    return Response(f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /{ADMIN_PATH}\nSitemap: {origin}/sitemap.xml\n", mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    origin = WEB_ORIGIN or request.host_url.rstrip("/")
    urls = ["/", "/termos", "/privacidade", "/reembolso"]
    xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>" + "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">" + "".join(
        f"<url><loc>{origin}{path}</loc></url>" for path in urls
    ) + "</urlset>"
    return Response(xml, mimetype="application/xml")


@app.get("/healthz")
def healthz():
    query("SELECT 1").fetchone()
    return jsonify(status="ok", service="kliktech-esim")


@app.get(f"/{ADMIN_PATH}")
def admin_root():
    allowed = bool(g.user and g.user.get("is_admin") and configured_admin_2fa() and session.get("admin_2fa_ok"))
    return render_template("admin.html", csrf_token=csrf_token()) if allowed else render_template("admin-login.html", csrf_token=csrf_token())


@app.get(f"/{ADMIN_PATH}/dashboard")
def admin_dashboard_page():
    if not g.user or not g.user.get("is_admin") or not configured_admin_2fa() or not session.get("admin_2fa_ok"):
        return redirect(f"/{ADMIN_PATH}")
    return render_template("admin.html", csrf_token=csrf_token())


# Compatibilidade com o caminho público original. O alias mantém exatamente
# as mesmas verificações de senha, sessão e 2FA da rota configurável.
if ADMIN_PATH != "ademiroputo":
    @app.get("/ademiroputo")
    def legacy_admin_root():
        return admin_root()

    @app.get("/ademiroputo/dashboard")
    def legacy_admin_dashboard_page():
        if not g.user or not g.user.get("is_admin") or not configured_admin_2fa() or not session.get("admin_2fa_ok"):
            return redirect(f"/{ADMIN_PATH}")
        return render_template("admin.html", csrf_token=csrf_token())


@app.get("/cliente")
def client_root():
    return redirect("/")


@app.get("/cliente/<path:_page>")
def client_page(_page: str):
    return redirect("/")


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, title="Acesso negado", message="Você não tem permissão para acessar esta área."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, title="Página não encontrada", message="O endereço informado não existe."), 404


@app.errorhandler(413)
def too_large(_error):
    return _json_error("O arquivo excede o limite de 6 MB.", 413) if request.path.startswith("/api/") else render_template(
        "error.html", code=413, title="Arquivo grande demais", message="Reduza o arquivo e tente novamente."
    ), 413


@app.post("/api/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    name = str(data.get("name", "")).strip()
    password = str(data.get("password", ""))
    confirmation = str(data.get("password_confirmation", ""))
    if not re.fullmatch(r"[^@\s]{1,100}@[^@\s]{1,190}\.[^@\s]{2,63}", email) or not name or len(name) > 120:
        return _json_error("Informe um nome e um e-mail válidos.", 400)
    if len(password) < 10 or len(password) > 200:
        return _json_error("A senha precisa ter entre 10 e 200 caracteres.", 400)
    if password != confirmation:
        return _json_error("As senhas não conferem.", 400)
    connection = db()
    try:
        public_id = secrets.token_urlsafe(9)
        connection.execute(
            "INSERT INTO users(email,name,password_hash,public_id) VALUES(%s,%s,%s,%s)",
            (email, name, generate_password_hash(password), public_id),
        )
        user = connection.execute("SELECT * FROM users WHERE email=%s", (email,)).fetchone()
        connection.commit()
    except UniqueViolation:
        connection.rollback()
        return _json_error("Este e-mail já está cadastrado.", 409)
    session.clear()
    session["user_id"] = user["id"]
    csrf_token()
    return jsonify(user=safe_user(user), is_admin=False)


@app.post("/api/auth/login")
def login():
    now = time.time()
    ip = client_ip()
    failures = [stamp for stamp in LOGIN_FAILURES.get(ip, []) if now - stamp < 900]
    if len(failures) >= MAX_LOGIN_FAILURES:
        return _json_error("Conta temporariamente bloqueada por excesso de tentativas. Aguarde 15 minutos.", 429)
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    user = query("SELECT * FROM users WHERE email=%s", (email,)).fetchone()
    valid = bool(user and check_password_hash(user["password_hash"], password))
    if not valid:
        failures.append(now)
        LOGIN_FAILURES[ip] = failures
        if len(failures) >= MAX_LOGIN_FAILURES and user:
            query("UPDATE users SET blocked_at=%s WHERE id=%s", (utcnow(), user["id"]))
            db().commit()
        return _json_error("E-mail ou senha inválidos.", 401)
    if user.get("blocked_at"):
        return _json_error("Esta conta está bloqueada.", 403)
    LOGIN_FAILURES.pop(ip, None)
    session.clear()
    session["user_id"] = user["id"]
    csrf_token()
    if user.get("is_admin"):
        session["admin_2fa_pending"] = True
        return jsonify(user=safe_user(user), is_admin=True, requires_2fa=True)
    return jsonify(user=safe_user(user), is_admin=False)


@app.post("/api/auth/admin-2fa")
def admin_2fa():
    if not g.user or not g.user.get("is_admin"):
        return _json_error("Área administrativa protegida.", 403)
    if not configured_admin_2fa():
        return _json_error("2FA administrativo não configurado.", 503)
    data = request.get_json(silent=True) or {}
    if not check_totp(ADMIN_TOTP_SECRET, str(data.get("code", ""))):
        return _json_error("Código 2FA inválido.", 401)
    session.pop("admin_2fa_pending", None)
    session["admin_2fa_ok"] = True
    return jsonify(ok=True)


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
def me():
    return jsonify(user=safe_user(g.user), is_admin=bool(g.user and g.user.get("is_admin")), csrf_token=csrf_token())


@app.post("/api/account/profile")
@login_required
def update_profile():
    name = str(request.form.get("name", "")).strip()
    if not name or len(name) > 120:
        return _json_error("Informe seu nome completo.", 400)
    photo_data = None
    photo_mime = None
    photo = request.files.get("photo")
    if photo and photo.filename:
        try:
            photo_data, photo_mime = image_bytes(photo)
        except ValueError as error:
            return _json_error(str(error), 400)
    connection = db()
    if photo_data:
        connection.execute("UPDATE users SET name=%s,profile_photo=%s,profile_photo_mime=%s WHERE id=%s", (name, photo_data, photo_mime, g.user["id"]))
    else:
        connection.execute("UPDATE users SET name=%s WHERE id=%s", (name, g.user["id"]))
    connection.commit()
    updated = query("SELECT * FROM users WHERE id=%s", (g.user["id"],)).fetchone()
    return jsonify(user=safe_user(updated))


@app.get("/api/account/profile/photo")
@login_required
def profile_photo():
    row = query("SELECT profile_photo,profile_photo_mime FROM users WHERE id=%s", (g.user["id"],)).fetchone()
    if not row or not row.get("profile_photo"):
        abort(404)
    return Response(row["profile_photo"], mimetype=row["profile_photo_mime"], headers={"Cache-Control": "private, no-store"})


@app.post("/api/cart")
def cart_add():
    data = request.get_json(silent=True) or {}
    plan = str(data.get("plan", ""))
    if plan not in catalog_prices():
        return _json_error("Plano inválido ou indisponível.", 400)
    cart_key = session.get("cart_key") or secrets.token_urlsafe(18)
    session["cart_key"] = cart_key
    query("INSERT INTO carts(user_id,session_key,plan) VALUES(%s,%s,%s)", (g.user["id"] if g.user else None, cart_key, plan))
    db().commit()
    return jsonify(ok=True)


@app.post("/api/wallet/create-pix")
@login_required
def create_pix():
    data = request.get_json(silent=True) or {}
    try:
        amount = int(round(float(data.get("amount", 0)) * 100))
    except (TypeError, ValueError):
        amount = 0
    if amount < 500 or amount > 1_000_000:
        return _json_error("Escolha entre R$ 5 e R$ 10.000.", 400)
    if not BRAVOPAY_API_KEY:
        return _json_error("Pagamento ainda não configurado no servidor.", 503)
    external = f"wallet:{g.user['id']}:{secrets.token_hex(8)}"
    payload = {
        "amount_cents": amount,
        "method": "pix",
        "customer": {"email": g.user["email"], "name": g.user["name"]},
        "description": "Recarga KlikTech",
        "external_reference": external,
        "metadata": {"user_id": str(g.user["id"]), "purpose": "wallet_topup"},
        "expires_in": 3600,
    }
    req = urllib.request.Request(
        "https://bravopay.club/api/v1/transactions",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {BRAVOPAY_API_KEY}", "Content-Type": "application/json", "Idempotency-Key": external},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        return _json_error("O provedor recusou a cobrança.", 502)
    except (OSError, ValueError):
        return _json_error("Não foi possível conectar ao provedor de pagamentos.", 502)
    pix = result.get("pix") or {}
    provider_id = result.get("id")
    copy_paste = pix.get("copy_paste")
    if not provider_id or not copy_paste:
        return _json_error("Resposta inválida do provedor de pagamentos.", 502)
    try:
        query(
            "INSERT INTO wallet_charges(user_id,provider_id,external_reference,amount_cents,status,pix_copy_paste,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (g.user["id"], provider_id, external, amount, result.get("status", "PENDING"), copy_paste, pix.get("expires_at")),
        )
        db().commit()
    except UniqueViolation:
        db().rollback()
        return _json_error("Esta cobrança já foi registrada.", 409)
    return jsonify(charge={"id": provider_id, "amount": amount / 100, "status": "PENDING", "copy_paste": copy_paste})


@app.post("/webhooks/bravopay")
def bravopay_webhook():
    raw = request.get_data()
    header = request.headers.get("BravoPay-Signature") or request.headers.get("X-Bravopay-Signature") or ""
    parts = dict(piece.split("=", 1) for piece in header.split(",") if "=" in piece)
    valid = False
    try:
        timestamp = parts.get("t", "0")
        expected = hmac.new(BRAVOPAY_WEBHOOK_SECRET.encode(), f"{timestamp}.".encode() + raw, hashlib.sha256).hexdigest()
        valid = bool(BRAVOPAY_WEBHOOK_SECRET) and abs(int(time.time()) - int(timestamp)) <= 300 and hmac.compare_digest(expected, parts.get("v1", ""))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        return _json_error("Assinatura inválida.", 401)
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return _json_error("Evento inválido.", 400)
    event_id = str(event.get("id", ""))
    event_type = event.get("type")
    data = event.get("data") or {}
    if not event_id:
        return _json_error("Evento sem identificador.", 400)
    connection = db()
    try:
        if connection.execute("SELECT id FROM wallet_ledger WHERE event_id=%s", (event_id,)).fetchone():
            return jsonify(ok=True)
        charge = connection.execute("SELECT * FROM wallet_charges WHERE provider_id=%s FOR UPDATE", (data.get("id"),)).fetchone()
        if not charge:
            connection.commit()
            return jsonify(ok=True)
        # Never trust amount or customer identifiers from the webhook body.
        if event_type == "transaction.paid" and charge["status"] != "PAID":
            amount = int(charge["amount_cents"])
            connection.execute("UPDATE users SET balance_cents=balance_cents+%s WHERE id=%s", (amount, charge["user_id"]))
            connection.execute("UPDATE wallet_charges SET status='PAID',paid_at=CURRENT_TIMESTAMP WHERE id=%s AND status<>'PAID'", (charge["id"],))
            connection.execute(
                "INSERT INTO wallet_ledger(event_id,user_id,provider_id,amount_cents,kind) VALUES(%s,%s,%s,%s,%s)",
                (event_id, charge["user_id"], charge["provider_id"], amount, "credit"),
            )
        elif event_type in {"transaction.expired", "transaction.failed", "transaction.refunded"}:
            status = "EXPIRED" if event_type.endswith("expired") else "REFUNDED" if event_type.endswith("refunded") else "FAILED"
            connection.execute("UPDATE wallet_charges SET status=%s WHERE id=%s AND status='PENDING'", (status, charge["id"]))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return jsonify(ok=True)


@app.get("/api/plans")
def public_plans():
    available = query("SELECT DISTINCT plan FROM inventory WHERE sold_at IS NULL").fetchall()
    available_plans = {row["plan"] for row in available}
    rows = [row for row in catalog_rows(True) if row["plan"] in available_plans]
    return jsonify(plans=[{"plan": row["plan"], "gigas": row["gigas"], "tempo": row["tempo"], "price": row["price_cents"] / 100, "featured": bool(row["featured"])} for row in rows])


@app.get("/api/auth/csrf")
def csrf():
    return jsonify(csrf_token=csrf_token())


@app.get("/api/availability")
@login_required
def availability():
    plan = request.args.get("plan", "").strip()
    ddd = request.args.get("ddd", "").strip()
    rows = query(
        "SELECT ddd,COUNT(*) AS quantity FROM inventory WHERE plan=%s AND sold_at IS NULL AND (%s='' OR ddd=%s) GROUP BY ddd ORDER BY ddd",
        (plan, ddd, ddd),
    ).fetchall()
    return jsonify(ddds=[{"ddd": row["ddd"], "quantity": row["quantity"]} for row in rows])


@app.post("/api/purchase")
@login_required
def purchase():
    data = request.get_json(silent=True) or {}
    plan = str(data.get("plan", ""))
    ddd = str(data.get("ddd", "")).strip()
    price_cents = catalog_prices().get(plan, 0)
    if not price_cents:
        return _json_error("Plano inválido.", 400)
    connection = db()
    try:
        # catalog_prices performed a read in the same connection; close that
        # implicit transaction before starting the atomic purchase transaction.
        connection.commit()
        with connection.transaction():
            user = connection.execute("SELECT id,balance_cents FROM users WHERE id=%s FOR UPDATE", (g.user["id"],)).fetchone()
            item = connection.execute(
                "SELECT * FROM inventory WHERE plan=%s AND sold_at IS NULL AND (%s='' OR ddd=%s) ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED",
                (plan, ddd, ddd),
            ).fetchone()
            if not item:
                return _json_error("Sem eSIM disponível para este plano/DDD.", 409)
            if int(user["balance_cents"]) < price_cents:
                return _json_error("Saldo insuficiente para este plano.", 402)
            updated = connection.execute(
                "UPDATE inventory SET sold_at=CURRENT_TIMESTAMP,sold_to=%s WHERE id=%s AND sold_at IS NULL",
                (user["id"], item["id"]),
            )
            if updated.rowcount != 1:
                return _json_error("Este eSIM acabou de ser reservado. Escolha outro.", 409)
            connection.execute("UPDATE users SET balance_cents=balance_cents-%s WHERE id=%s AND balance_cents >= %s", (price_cents, user["id"], price_cents))
            if connection.execute("SELECT balance_cents FROM users WHERE id=%s", (user["id"],)).fetchone()["balance_cents"] < 0:
                raise RuntimeError("Saldo negativo bloqueado pelo banco")
            connection.execute(
                "UPDATE carts SET status='converted',updated_at=CURRENT_TIMESTAMP WHERE session_key=%s AND plan=%s AND status='active'",
                (session.get("cart_key", ""), plan),
            )
            connection.execute("INSERT INTO purchases(user_id,inventory_id,plan,price_cents) VALUES(%s,%s,%s,%s)", (user["id"], item["id"], plan, price_cents))
    except psycopg.errors.UniqueViolation:
        connection.rollback()
        return _json_error("Este eSIM já foi vendido. Escolha outro.", 409)
    return jsonify(ok=True)


@app.get("/api/account/purchases")
@login_required
def my_purchases():
    rows = query(
        "SELECT p.id,p.plan,p.price_cents,p.created_at,i.model,i.line,i.ddd,i.smdp,i.activation_code,i.photo FROM purchases p JOIN inventory i ON i.id=p.inventory_id WHERE p.user_id=%s ORDER BY p.id DESC",
        (g.user["id"],),
    ).fetchall()
    return jsonify(purchases=[purchase_payload(row) for row in rows])


@app.get("/api/account/purchases/<int:purchase_id>/qr")
@login_required
def purchase_qr(purchase_id: int):
    row = query(
        "SELECT i.smdp,i.activation_code FROM purchases p JOIN inventory i ON i.id=p.inventory_id WHERE p.id=%s AND p.user_id=%s",
        (purchase_id, g.user["id"]),
    ).fetchone()
    if not row:
        abort(404)
    image = qrcode.make(f"LPA:1${row['smdp']}${row['activation_code']}")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(buffer.getvalue(), mimetype="image/png", headers={"Cache-Control": "private, no-store"})


@app.get("/api/account/purchases/<int:purchase_id>/photo")
@login_required
def purchase_photo(purchase_id: int):
    row = query(
        "SELECT i.photo,i.photo_mime FROM purchases p JOIN inventory i ON i.id=p.inventory_id WHERE p.id=%s AND p.user_id=%s",
        (purchase_id, g.user["id"]),
    ).fetchone()
    if not row or not row.get("photo"):
        abort(404)
    return Response(row["photo"], mimetype=row["photo_mime"], headers={"Cache-Control": "private, no-store"})


@app.get("/api/esim/compatibility")
def esim_compatibility():
    query_text = " ".join((request.args.get("model") or "").lower().replace("-", " ").split())
    rules = [
        ("apple", ["iphone xr", "iphone xs", "iphone 11", "iphone 12", "iphone 13", "iphone 14", "iphone 15", "iphone 16", "iphone se 2", "iphone se 3"], "iPhone XS/XR ou posterior"),
        ("samsung", ["galaxy s20", "galaxy s21", "galaxy s22", "galaxy s23", "galaxy s24", "galaxy s25", "galaxy note20", "galaxy z fold", "galaxy z flip"], "Galaxy compatível com eSIM"),
        ("google", ["pixel 4", "pixel 5", "pixel 6", "pixel 7", "pixel 8", "pixel 9"], "Google Pixel 4 ou posterior"),
        ("motorola", ["motorola razr 40", "motorola razr 50", "motorola edge 40", "motorola edge 50"], "Motorola compatível em versões específicas"),
    ]
    for brand, names, label in rules:
        if any(name in query_text for name in names):
            return jsonify(model=request.args.get("model", ""), esim_supported=True, confidence="initial", family=label, brand=brand, needs_variant_confirmation=True)
    return jsonify(model=request.args.get("model", ""), esim_supported=None, confidence="unknown", message="Modelo não localizado; confirme EID e a opção Adicionar eSIM no aparelho.")


@app.post("/api/admin/inventory")
@admin_required
def add_inventory():
    form = request.form
    plan = str(form.get("plan", "")).strip()
    smdp = str(form.get("smdp", "")).strip()
    code = str(form.get("activation_code", "")).strip()
    ddd = str(form.get("ddd", "")).strip()
    if plan not in catalog_prices(False) or not smdp or not code or not re.fullmatch(r"\d{2,3}", ddd):
        return _json_error("Preencha plano, DDD, SM-DP+ e código de ativação válidos.", 400)
    photo_data = None
    photo_mime = None
    photo = request.files.get("photo")
    if photo and photo.filename:
        try:
            photo_data, photo_mime = image_bytes(photo)
        except ValueError as error:
            return _json_error(str(error), 400)
    connection = db()
    if connection.execute("SELECT id FROM inventory WHERE activation_code=%s", (code,)).fetchone():
        return _json_error("Este código de ativação já está cadastrado.", 409)
    try:
        connection.execute(
            "INSERT INTO inventory(plan,model,line,ddd,photo,photo_mime,smdp,activation_code) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (plan, str(form.get("model", "")).strip() or "Não informado", str(form.get("line", "")).strip(), ddd, photo_data, photo_mime, smdp, code),
        )
        connection.commit()
    except UniqueViolation:
        connection.rollback()
        return _json_error("Este código de ativação já está cadastrado.", 409)
    return jsonify(ok=True)


@app.post("/api/admin/inventory/batch")
@admin_required
def add_inventory_batch():
    try:
        records = json.loads(request.form.get("records", "[]")) if not request.is_json else (request.get_json(silent=True) or {}).get("records", [])
    except json.JSONDecodeError:
        return _json_error("JSON de registros inválido.", 400)
    photos = request.files.getlist("photos") if not request.is_json else []
    if not isinstance(records, list) or not records or len(records) > 100:
        return _json_error("Envie entre 1 e 100 registros.", 400)
    if photos and len(photos) != len(records):
        return _json_error("A quantidade de fotos deve ser igual à quantidade de registros.", 400)
    errors = []
    normalized = []
    seen = set()
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            errors.append(f"Registro {index}: formato inválido.")
            continue
        plan = str(record.get("plan", "")).strip()
        gigas = str(record.get("gigas", "")).strip()
        tempo = str(record.get("tempo", "")).strip()
        if not plan and gigas and tempo:
            plan = f"{gigas} · {tempo}"
        code = str(record.get("activation_code", "")).strip()
        smdp = str(record.get("smdp", "")).strip()
        ddd = str(record.get("ddd", "")).strip()
        if plan not in catalog_prices(False):
            errors.append(f"Registro {index}: plano inválido.")
        if not smdp or not code or not re.fullmatch(r"\d{2,3}", ddd):
            errors.append(f"Registro {index}: DDD, SM-DP+ e código são obrigatórios e válidos.")
        if code in seen:
            errors.append(f"Registro {index}: código duplicado no lote.")
        seen.add(code)
        normalized.append({**record, "plan": plan, "ddd": ddd, "smdp": smdp, "activation_code": code})
    connection = db()
    for record in normalized:
        if connection.execute("SELECT id FROM inventory WHERE activation_code=%s", (record["activation_code"],)).fetchone():
            errors.append(f"Código já existente no estoque: {record['activation_code']}")
    parsed_photos = []
    if not errors:
        for index, photo in enumerate(photos, 1):
            try:
                parsed_photos.append(image_bytes(photo))
            except ValueError as error:
                errors.append(f"Foto {index}: {error}")
    if errors:
        return jsonify(error="Validação falhou.", errors=errors), 400
    try:
        for index, record in enumerate(normalized):
            photo_data, photo_mime = parsed_photos[index] if parsed_photos else (None, None)
            connection.execute(
                "INSERT INTO inventory(plan,model,line,ddd,photo,photo_mime,smdp,activation_code) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (record["plan"], str(record.get("model", "")).strip() or "Não informado", str(record.get("line", "")).strip(), record["ddd"], photo_data, photo_mime, record["smdp"], record["activation_code"]),
            )
        connection.commit()
    except UniqueViolation:
        connection.rollback()
        return _json_error("Código de ativação já cadastrado.", 409)
    return jsonify(ok=True, added=len(normalized))


@app.get("/api/admin/plans")
@admin_required
def admin_plans():
    return jsonify(plans=[{**row, "price": row["price_cents"] / 100, "active": bool(row["active"]), "featured": bool(row["featured"])} for row in catalog_rows(False)])


@app.post("/api/admin/plans")
@admin_required
def create_plan():
    data = request.get_json(silent=True) or {}
    gigas = str(data.get("gigas", "")).strip().upper()
    tempo = str(data.get("tempo", "")).strip()
    label = str(data.get("plan", "")).strip() or f"{gigas} · {tempo}"
    try:
        price_cents = int(round(float(data.get("price", 0)) * 100))
    except (TypeError, ValueError):
        price_cents = 0
    if not gigas or not tempo or not label or price_cents <= 0:
        return _json_error("Informe franquia, ciclo e preço válidos.", 400)
    try:
        query("INSERT INTO plan_catalog(plan,gigas,tempo,price_cents,active,featured) VALUES(%s,%s,%s,%s,%s,%s)", (label, gigas, tempo, price_cents, bool(data.get("active", True)), bool(data.get("featured", False))))
        db().commit()
    except UniqueViolation:
        db().rollback()
        return _json_error("Já existe um slot com esse nome.", 409)
    return jsonify(ok=True, plan=label), 201


@app.patch("/api/admin/plans/<int:plan_id>")
@admin_required
def update_plan(plan_id: int):
    data = request.get_json(silent=True) or {}
    connection = db()
    old = connection.execute("SELECT * FROM plan_catalog WHERE id=%s", (plan_id,)).fetchone()
    if not old:
        return _json_error("Slot não encontrado.", 404)
    gigas = str(data.get("gigas", old["gigas"])).strip().upper()
    tempo = str(data.get("tempo", old["tempo"])).strip()
    label = str(data.get("plan", "")).strip() or f"{gigas} · {tempo}"
    try:
        price_cents = int(round(float(data.get("price", old["price_cents"] / 100)) * 100))
    except (TypeError, ValueError):
        return _json_error("Preço inválido.", 400)
    if not gigas or not tempo or price_cents <= 0:
        return _json_error("Informe franquia, ciclo e preço válidos.", 400)
    if connection.execute("SELECT id FROM plan_catalog WHERE plan=%s AND id<>%s", (label, plan_id)).fetchone():
        return _json_error("Já existe outro slot com esse nome.", 409)
    connection.execute("UPDATE plan_catalog SET plan=%s,gigas=%s,tempo=%s,price_cents=%s,active=%s,featured=%s WHERE id=%s", (label, gigas, tempo, price_cents, bool(data.get("active", old["active"])), bool(data.get("featured", old["featured"])), plan_id))
    if label != old["plan"]:
        connection.execute("UPDATE inventory SET plan=%s WHERE plan=%s AND sold_at IS NULL", (label, old["plan"]))
    connection.commit()
    return jsonify(ok=True, plan=label)


@app.delete("/api/admin/plans/<int:plan_id>")
@admin_required
def delete_plan(plan_id: int):
    connection = db()
    result = connection.execute("DELETE FROM plan_catalog WHERE id=%s", (plan_id,))
    connection.commit()
    return jsonify(ok=True) if result.rowcount == 1 else _json_error("Slot não encontrado.", 404)


@app.get("/api/admin/dashboard")
@admin_required
def dashboard():
    connection = db()
    sales = connection.execute("SELECT COUNT(*) AS n,COALESCE(SUM(price_cents),0) AS v FROM purchases").fetchone()
    pix_pending = connection.execute("SELECT COUNT(*) AS n,COALESCE(SUM(amount_cents),0) AS v FROM wallet_charges WHERE status='PENDING'").fetchone()
    stock = connection.execute("SELECT COUNT(*) AS n FROM inventory WHERE sold_at IS NULL").fetchone()
    cutoff = utcnow() - timedelta(minutes=30)
    abandoned = connection.execute("SELECT COUNT(*) AS n FROM carts WHERE status='active' AND updated_at < %s", (cutoff,)).fetchone()
    recent = connection.execute("SELECT p.plan,p.price_cents,p.created_at,u.name,u.email FROM purchases p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 12").fetchall()
    now = utcnow()
    months = []
    for offset in range(11, -1, -1):
        year = now.year + (now.month - 1 - offset) // 12
        month = (now.month - 1 - offset) % 12 + 1
        months.append({"key": f"{year:04d}-{month:02d}", "label": f"{month:02d}/{str(year)[2:]}", "sales": 0, "revenue": 0})
    lookup = {month["key"]: month for month in months}
    for row in connection.execute("SELECT created_at,price_cents FROM purchases").fetchall():
        key = str(row["created_at"])[:7]
        if key in lookup:
            lookup[key]["sales"] += 1
            lookup[key]["revenue"] += int(row["price_cents"]) / 100
    return jsonify(
        metrics={
            "sales_count": sales["n"],
            "sales_value": sales["v"] / 100,
            "pending_pix_count": pix_pending["n"],
            "pending_pix_value": pix_pending["v"] / 100,
            "available_stock": stock["n"],
            "abandoned_carts": abandoned["n"],
        },
        monthly=months,
        recent=[{"plan": row["plan"], "price": row["price_cents"] / 100, "date": row["created_at"], "customer": row["name"], "email": mask_email(row["email"])} for row in recent],
    )


@app.get("/api/admin/pix")
@admin_required
def admin_pix():
    try:
        limit = min(max(int(request.args.get("limit", 200)), 1), 500)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        limit, offset = 200, 0
    connection = db()
    rows = connection.execute("SELECT w.id,w.amount_cents,w.status,w.expires_at,w.created_at,w.paid_at,u.public_id,u.name,u.email FROM wallet_charges w JOIN users u ON u.id=w.user_id ORDER BY w.id DESC LIMIT %s OFFSET %s", (limit, offset)).fetchall()
    total = connection.execute("SELECT COUNT(*) AS n FROM wallet_charges").fetchone()["n"]
    return jsonify(total=total, items=[{"id": row["id"], "account_id": row["public_id"], "customer": row["name"], "email": mask_email(row["email"]), "amount": row["amount_cents"] / 100, "status": row["status"], "expires_at": row["expires_at"], "created_at": row["created_at"], "paid_at": row["paid_at"]} for row in rows])


@app.get("/api/admin/abandoned")
@admin_required
def admin_abandoned():
    cutoff = utcnow() - timedelta(minutes=30)
    rows = db().execute("SELECT c.id,c.plan,c.status,c.created_at,c.updated_at,u.public_id,u.name,u.email FROM carts c LEFT JOIN users u ON u.id=c.user_id WHERE c.status='active' AND c.updated_at < %s ORDER BY c.updated_at DESC", (cutoff,)).fetchall()
    return jsonify(total=len(rows), items=[{"id": row["id"], "plan": row["plan"], "status": row["status"], "created_at": row["created_at"], "updated_at": row["updated_at"], "customer": row["name"] or "Visitante", "email": mask_email(row["email"]) if row["email"] else "—"} for row in rows])


@app.get("/api/admin/users")
@admin_required
def admin_users():
    connection = db()
    rows = connection.execute("SELECT id,public_id,name,email,is_admin,blocked_at,profile_photo IS NOT NULL AS has_photo,created_at FROM users ORDER BY id DESC").fetchall()
    result = []
    for row in rows:
        ips = connection.execute("SELECT ip,created_at FROM access_logs WHERE user_id=%s ORDER BY created_at DESC LIMIT 10", (row["id"],)).fetchall()
        result.append({"id": row["public_id"], "name": row["name"], "email": row["email"], "is_admin": bool(row["is_admin"]), "blocked": bool(row["blocked_at"]), "has_photo": bool(row["has_photo"]), "created_at": row["created_at"], "last_ip": ips[0]["ip"] if ips else "—"})
    return jsonify(users=result)


@app.patch("/api/admin/users/<public_id>/access")
@admin_required
def admin_user_access(public_id: str):
    data = request.get_json(silent=True) or {}
    blocked = bool(data.get("blocked"))
    connection = db()
    row = connection.execute("SELECT id,is_admin FROM users WHERE public_id=%s", (public_id,)).fetchone()
    if not row:
        return _json_error("Usuário não encontrado.", 404)
    if row["is_admin"] and blocked:
        return _json_error("Não é permitido bloquear uma conta administradora.", 409)
    connection.execute("UPDATE users SET blocked_at=%s WHERE id=%s", (utcnow() if blocked else None, row["id"]))
    connection.commit()
    return jsonify(ok=True, blocked=blocked)


@app.get("/api/admin/inventory")
@admin_required
def inventory():
    rows = db().execute("SELECT id,plan,model,line,ddd,sold_at IS NOT NULL AS sold,created_at FROM inventory ORDER BY id DESC").fetchall()
    return jsonify(items=[dict(row) for row in rows])


@app.get("/api/admin/inventory/<int:item_id>")
@admin_required
def inventory_detail(item_id: int):
    row = db().execute("SELECT id,plan,model,line,ddd,smdp,activation_code,photo,photo_mime,sold_at,sold_to,created_at FROM inventory WHERE id=%s", (item_id,)).fetchone()
    if not row:
        return _json_error("Item de estoque não encontrado.", 404)
    return jsonify(item={"id": row["id"], "plan": row["plan"], "model": row["model"], "line": row["line"], "ddd": row["ddd"], "smdp": row["smdp"], "activation_code": row["activation_code"], "sold": bool(row["sold_at"]), "sold_at": row["sold_at"], "sold_to": row["sold_to"], "created_at": row["created_at"], "photo_url": f"/{ADMIN_PATH}/inventory/{row['id']}/photo" if row.get("photo") else None})


@app.delete("/api/admin/inventory/<int:item_id>")
@admin_required
def delete_inventory(item_id: int):
    connection = db()
    row = connection.execute("SELECT sold_at FROM inventory WHERE id=%s", (item_id,)).fetchone()
    if not row:
        return _json_error("eSIM não encontrado.", 404)
    if row["sold_at"]:
        return _json_error("Não é possível excluir um eSIM já vendido.", 409)
    connection.execute("DELETE FROM inventory WHERE id=%s AND sold_at IS NULL", (item_id,))
    connection.commit()
    return jsonify(ok=True)


@app.get(f"/{ADMIN_PATH}/inventory/<int:item_id>/photo")
@admin_required
def inventory_detail_photo(item_id: int):
    row = db().execute("SELECT photo,photo_mime FROM inventory WHERE id=%s", (item_id,)).fetchone()
    if not row or not row.get("photo"):
        abort(404)
    return Response(row["photo"], mimetype=row["photo_mime"], headers={"Cache-Control": "private, no-store"})


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
else:
    with app.app_context():
        init_db()
