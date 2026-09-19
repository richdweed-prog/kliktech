from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

import psycopg
import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATABASE_URL", "postgresql://kliktech:kliktech@127.0.0.1:5432/kliktech_test")
os.environ.setdefault("KLIKTECH_SECRET_KEY", "test-secret-key-at-least-32-bytes-long")
os.environ.setdefault("KLIKTECH_ADMIN_PASSWORD", "admin-test-password-123")
os.environ.setdefault("KLIKTECH_ADMIN_EMAIL", "admin@test.local")
os.environ.setdefault("KLIKTECH_ADMIN_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
os.environ.setdefault("KLIKTECH_COOKIE_SECURE", "0")
os.environ.setdefault("KLIKTECH_TRUST_PROXY", "0")
os.environ.setdefault("KLIKTECH_PUBLIC_ORIGIN", "http://localhost")
os.environ.setdefault("BRAVOPAY_WEBHOOK_SECRET", "webhook-test-secret")

from app import app, init_db  # noqa: E402


def db_connection():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=psycopg.rows.dict_row)


@pytest.fixture(scope="session", autouse=True)
def database_schema():
    with app.app_context():
        init_db()
    yield


@pytest.fixture(autouse=True)
def clean_database():
    with db_connection() as connection:
        connection.execute("TRUNCATE purchases,inventory,carts,plan_catalog,wallet_ledger,wallet_charges,access_logs,admin_events,users RESTART IDENTITY CASCADE")
        connection.execute("INSERT INTO plan_catalog(plan,gigas,tempo,price_cents,active,featured) VALUES(%s,%s,%s,%s,TRUE,TRUE)", ("30GB · 1 mês", "30GB", "1 mês", 2000))
        connection.commit()
    app.config.update(TESTING=True)
    app.config["WTF_CSRF_ENABLED"] = False
    app.view_functions["login"].__wrapped__ if False else None
    from app import LOGIN_FAILURES, RATE_BUCKETS
    LOGIN_FAILURES.clear()
    RATE_BUCKETS.clear()
    yield


@pytest.fixture
def client():
    return app.test_client()


def create_user(*, name="Cliente", email=None, balance_cents=0, is_admin=False, photo=None):
    email = email or f"{secrets.token_hex(5)}@test.local"
    with db_connection() as connection:
        row = connection.execute(
            "INSERT INTO users(email,name,password_hash,balance_cents,is_admin,public_id,profile_photo,profile_photo_mime) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (email, name, generate_password_hash("correct-password-123"), balance_cents, int(is_admin), secrets.token_urlsafe(9), photo, "image/png" if photo else None),
        ).fetchone()
        connection.commit()
    return row


def create_inventory(*, count=1, plan="30GB · 1 mês", ddd="31", photo=None):
    ids = []
    with db_connection() as connection:
        for index in range(count):
            row = connection.execute(
                "INSERT INTO inventory(plan,model,line,ddd,photo,photo_mime,smdp,activation_code) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (plan, "Test Phone", "", ddd, photo, "image/png" if photo else None, "smdp.example", f"activation-{secrets.token_hex(6)}-{index}"),
            ).fetchone()
            ids.append(row["id"])
        connection.commit()
    return ids


def authenticate(client, user_id, *, csrf="csrf-test-token"):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["csrf_token"] = csrf
    return {"Origin": "http://localhost", "X-CSRF-Token": csrf}


def get_balance(user_id):
    with db_connection() as connection:
        return connection.execute("SELECT balance_cents FROM users WHERE id=%s", (user_id,)).fetchone()["balance_cents"]
