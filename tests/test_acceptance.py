from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg

from app import app
from tests.conftest import authenticate, create_inventory, create_user, db_connection, get_balance


def admin_session(client):
    admin = create_user(name="Administrador", email="admin-acceptance@test.local", is_admin=True)
    headers = authenticate(client, admin["id"])
    with client.session_transaction() as session:
        session["admin_2fa_ok"] = True
    return headers


def insert_charge(user_id, provider="provider-acceptance"):
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO wallet_charges(user_id,provider_id,external_reference,amount_cents,status) VALUES(%s,%s,%s,%s,'PENDING')",
            (user_id, provider, f"ref-{provider}", 3000),
        )
        connection.commit()


def signed_webhook(payload, event_id="event-1", timestamp=None):
    raw = json.dumps({"id": event_id, **payload}, separators=(",", ":")).encode()
    timestamp = str(timestamp or int(time.time()))
    signature = hmac.new(os.environ["BRAVOPAY_WEBHOOK_SECRET"].encode(), f"{timestamp}.".encode() + raw, hashlib.sha256).hexdigest()
    return raw, {"BravoPay-Signature": f"t={timestamp},v1={signature}"}


def test_five_wrong_passwords_block_and_correct_password_is_rejected(client):
    user = create_user(email="lockout@test.local")
    client.get("/")
    with client.session_transaction() as session:
        token = session.get("csrf_token", "")
    headers = {"Origin": "http://localhost", "X-CSRF-Token": token}
    for _ in range(5):
        response = client.post("/api/auth/login", json={"email": user["email"], "password": "wrong-password"}, headers=headers)
        assert response.status_code == 401
    response = client.post("/api/auth/login", json={"email": user["email"], "password": "correct-password-123"}, headers=headers)
    assert response.status_code in {403, 429}
    with db_connection() as connection:
        assert connection.execute("SELECT blocked_at FROM users WHERE id=%s", (user["id"],)).fetchone()["blocked_at"] is not None


def test_429_limits_for_login_register_default_and_webhook(client):
    with client.session_transaction() as session:
        session["csrf_token"] = "rate-token"
    headers = {"Origin": "http://localhost", "X-CSRF-Token": "rate-token"}
    login_statuses = [client.post("/api/auth/login", json={"email": "none@test.local", "password": "bad"}, headers=headers).status_code for _ in range(6)]
    assert 429 in login_statuses

    register_statuses = [client.post("/api/auth/register", json={"email": "invalid", "name": "Teste", "password": "password-12345", "password_confirmation": "password-12345"}, headers=headers).status_code for _ in range(6)]
    assert 429 in register_statuses

    # Reset the IP bucket only to exercise the generic state-changing limiter.
    from app import RATE_BUCKETS
    RATE_BUCKETS.clear()
    user = create_user(email="rate-cart@test.local")
    authenticate(client, user["id"], csrf="cart-token")
    cart_headers = {"Origin": "http://localhost", "X-CSRF-Token": "cart-token"}
    statuses = [client.post("/api/cart", json={"plan": "30GB · 1 mês"}, headers=cart_headers).status_code for _ in range(61)]
    assert 429 in statuses

    from app import RATE_BUCKETS
    RATE_BUCKETS.clear()
    raw, wh_headers = signed_webhook({"type": "transaction.created", "data": {"id": "missing-provider"}}, event_id="limit-event")
    statuses = [client.post("/webhooks/bravopay", data=raw, headers=wh_headers).status_code for _ in range(31)]
    assert 429 in statuses


def test_mutating_request_without_csrf_or_origin_is_rejected(client):
    with client.session_transaction() as session:
        session["csrf_token"] = "csrf-token"
    response = client.post("/api/auth/register", json={"email": "csrf@test.local", "name": "Teste", "password": "password-12345", "password_confirmation": "password-12345"})
    assert response.status_code == 403
    response = client.post("/api/cart", json={"plan": "30GB · 1 mês"}, headers={"Origin": "http://localhost"})
    assert response.status_code == 403


def test_idor_denies_purchase_qr_and_photo(client):
    photo = b"\x89PNG\r\n\x1a\n" + b"fake-png-content"
    user_a = create_user(email="a@test.local", balance_cents=2000)
    user_b = create_user(email="b@test.local", balance_cents=2000)
    inventory_id = create_inventory(photo=photo)[0]
    headers_a = authenticate(client, user_a["id"])
    purchase = client.post("/api/purchase", json={"plan": "30GB · 1 mês", "ddd": "31"}, headers=headers_a)
    assert purchase.status_code == 200
    with db_connection() as connection:
        purchase_id = connection.execute("SELECT id FROM purchases WHERE user_id=%s", (user_a["id"],)).fetchone()["id"]
    headers_b = authenticate(client, user_b["id"], csrf="b-csrf")
    assert client.get(f"/api/account/purchases/{purchase_id}/qr", headers=headers_b).status_code == 404
    assert client.get(f"/api/account/purchases/{purchase_id}/photo", headers=headers_b).status_code == 404
    assert inventory_id > 0


def test_twenty_concurrent_purchases_keep_balance_nonnegative_and_unique():
    user = create_user(email="concurrent@test.local", balance_cents=20 * 2000)
    create_inventory(count=20)

    def buy_once(index):
        local_client = app.test_client()
        headers = authenticate(local_client, user["id"], csrf=f"thread-{index}")
        response = local_client.post("/api/purchase", json={"plan": "30GB · 1 mês", "ddd": "31"}, headers=headers)
        return response.status_code

    with ThreadPoolExecutor(max_workers=20) as executor:
        statuses = list(executor.map(buy_once, range(20)))
    assert statuses.count(200) == 20
    with db_connection() as connection:
        assert connection.execute("SELECT COUNT(*) AS n FROM purchases WHERE user_id=%s", (user["id"],)).fetchone()["n"] == 20
        assert connection.execute("SELECT COUNT(DISTINCT inventory_id) AS n FROM purchases WHERE user_id=%s", (user["id"],)).fetchone()["n"] == 20
    assert get_balance(user["id"]) == 0


def test_repeated_or_tampered_webhook_never_double_credits(client):
    user = create_user(email="webhook@test.local")
    insert_charge(user["id"], "provider-webhook")
    payload = {"type": "transaction.paid", "data": {"id": "provider-webhook", "amount_cents": 999999, "metadata": {"user_id": "attacker"}}}
    raw, headers = signed_webhook(payload, event_id="paid-event")
    first = client.post("/webhooks/bravopay", data=raw, headers=headers)
    second = client.post("/webhooks/bravopay", data=raw, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert get_balance(user["id"]) == 3000
    tampered = raw.replace(b"provider-webhook", b"other-provider")
    assert client.post("/webhooks/bravopay", data=tampered, headers=headers).status_code == 401
    assert get_balance(user["id"]) == 3000


def test_admin_data_is_rendered_by_text_not_html_interpolation(client):
    admin_session(client)
    user = create_user(name="<script>alert(1)</script>", email="xss@test.local")
    response = client.get("/api/admin/users")
    assert response.status_code == 200
    matching = next(user for user in response.json["users"] if user["email"] == "xss@test.local")
    assert matching["name"] == "<script>alert(1)</script>"
    script = Path("static/js/admin.js").read_text(encoding="utf-8")
    assert "user.name" in script
    assert "innerHTML" not in script
    assert user["id"]


def test_svg_and_fake_image_uploads_are_rejected(client):
    admin_session(client)
    headers = {"Origin": "http://localhost", "X-CSRF-Token": "csrf-test-token"}
    form = {"plan": "30GB · 1 mês", "ddd": "31", "smdp": "smdp.example", "activation_code": "svg-code"}
    svg = (io.BytesIO(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"), "attack.svg", "image/svg+xml")
    assert client.post("/api/admin/inventory", data={**form, "photo": svg}, headers=headers, content_type="multipart/form-data").status_code == 400
    fake = (io.BytesIO(b"not-a-png"), "fake.png", "image/png")
    assert client.post("/api/admin/inventory", data={**form, "activation_code": "fake-code", "photo": fake}, headers=headers, content_type="multipart/form-data").status_code == 400


def test_admin_without_2fa_is_denied(client):
    admin = create_user(name="Admin", email="no-2fa@test.local", is_admin=True)
    authenticate(client, admin["id"])
    response = client.get("/api/admin/dashboard")
    assert response.status_code == 403


def test_site_works_with_strict_csp_without_inline_code(client):
    response = client.get("/")
    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    html = response.get_data(as_text=True)
    assert "<style" not in html
    assert "style=" not in html
    assert '<script>' not in html
