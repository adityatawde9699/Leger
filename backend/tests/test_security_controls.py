import asyncio
import base64
import hashlib
import hmac
import io
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app import auth
from app import main as app_main
from app.config import Settings, settings
from app.main import _validate_statement_content
from app.models import AppSession, Webhook
from app.services import url_guard, webhook_dispatcher
from app.services.ai_router import AIRouter
from app.services.backups import decrypt_backup, encrypt_backup
from app.services.webhook_secrets import decrypt_secret, encrypt_secret, migrate_plaintext_secrets
from tests.conftest import TestSession, fastapi_app


@pytest.mark.parametrize("claims", [
    {"iss": "https://evil.example", "aud": "client", "exp": 9999999999, "sub": "user", "email": "test@example.com", "email_verified": True},
    {"iss": "https://accounts.google.com", "aud": "wrong", "exp": 9999999999, "sub": "user", "email": "test@example.com", "email_verified": True},
    {"iss": "https://accounts.google.com", "aud": "client", "exp": 1, "sub": "user", "email": "test@example.com", "email_verified": True},
    {"iss": "https://accounts.google.com", "aud": "client", "exp": 9999999999, "sub": "", "email": "test@example.com", "email_verified": True},
    {"iss": "https://accounts.google.com", "aud": "client", "exp": 9999999999, "sub": "user", "email": "test@example.com", "email_verified": False},
])
def test_google_claims_fail_closed(monkeypatch, claims):
    from google.oauth2 import id_token

    monkeypatch.setattr(settings, "auth_provider", "google")
    monkeypatch.setattr(settings, "google_client_id", "client")
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *args: claims)
    monkeypatch.setattr(auth, "_get_google_request", lambda: object())
    with pytest.raises(HTTPException) as error:
        auth._verify_token("credential")
    assert error.value.status_code == 401


def test_session_is_hashed_and_expires(monkeypatch):
    monkeypatch.setattr(settings, "auth_provider", "dev")
    with TestSession() as db:
        token = auth.create_session(db, auth.UserContext(id="test-user-1"))
        row = db.query(AppSession).one()
        assert token != row.token_hash
        assert len(row.token_hash) == 64
        assert row.expires_at.replace(tzinfo=UTC) > datetime.now(UTC) + timedelta(hours=11)


def test_webhook_secret_is_encrypted_and_legacy_rows_migrate(monkeypatch):
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "webhook_encryption_keys", old_key)
    encrypted = encrypt_secret("some-long-signing-secret")
    assert "some-long-signing-secret" not in encrypted
    assert decrypt_secret(encrypted) == "some-long-signing-secret"
    with TestSession() as db:
        db.add(Webhook(user_id="test-user-1", url="https://example.com", events="created", secret="legacy-secret"))
        db.commit()
        assert migrate_plaintext_secrets(db) == 1
        assert decrypt_secret(db.query(Webhook).one().secret) == "legacy-secret"
        monkeypatch.setattr(settings, "webhook_encryption_keys", f"{new_key},{old_key}")
        assert migrate_plaintext_secrets(db) == 1
        monkeypatch.setattr(settings, "webhook_encryption_keys", new_key)
        assert decrypt_secret(db.query(Webhook).one().secret) == "legacy-secret"


def test_backup_reads_previous_key_after_rotation():
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    token = encrypt_backup({"export_version": 1, "accounts": []}, old_key)
    assert decrypt_backup(token, new_key, old_key)["accounts"] == []


def test_production_rejects_localhost_cors():
    config = Settings(_env_file=None, environment="production", auth_provider="google",
                      cors_origins="http://localhost:5173")
    with pytest.raises(SystemExit):
        config.validate_for_production()


def test_production_requires_distinct_keys_and_shared_redis():
    key = Fernet.generate_key().decode()
    config = Settings(_env_file=None, environment="production", auth_provider="google",
                      google_client_id="client", cors_origins="https://ledger.example",
                      webhook_encryption_keys=key, backup_encryption_key=key,
                      redis_url="rediss://redis.example:6379/0")
    with pytest.raises(SystemExit):
        config.validate_for_production()
    config.backup_encryption_key = Fernet.generate_key().decode()
    config.redis_url = "redis://localhost:6379/0"
    with pytest.raises(SystemExit):
        config.validate_for_production()


@pytest.mark.parametrize("content,extension", [
    (b"not-a-pdf", "pdf"),
    (b"not-an-excel-file", "xls"),
    (b"bad\x00csv", "csv"),
    (b"not-a-zip", "xlsx"),
])
def test_statement_rejects_invalid_content(content, extension):
    with pytest.raises(HTTPException):
        _validate_statement_content(content, extension)


def test_receipt_scan_rejects_oversized_file(client):
    response = client.post("/receipts/scan", files={"file": ("receipt.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024)), "image/png")})
    assert response.status_code == 413


def test_large_json_and_invalid_avatar_are_rejected(client):
    assert client.put("/profile", content=b"{" + b" " * (3 * 1024 * 1024 + 1) + b"}",
                      headers={"Content-Type": "application/json"}).status_code == 413
    assert client.put("/profile", json={"avatar_url": "data:image/png;base64,AA=="}).status_code == 400


def test_receipt_scan_does_not_send_opted_out_image(client, monkeypatch):
    async def provider_must_not_run(*args):
        raise AssertionError("Receipt was sent to cloud AI")

    monkeypatch.setattr(app_main, "parse_receipt_image", provider_must_not_run)
    image = BytesIO()
    Image.new("RGB", (1, 1)).save(image, format="PNG")
    response = client.post("/receipts/scan", files={"file": ("receipt.png", image.getvalue(), "image/png")})
    assert response.status_code == 403


def test_pdf_without_opt_in_skips_cloud_provider(monkeypatch):
    import pdfplumber

    from app.services import statements

    class FakePdf:
        pages = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    async def provider_must_not_run(*args):
        raise AssertionError("Statement was sent to cloud AI")

    monkeypatch.setattr(pdfplumber, "open", lambda *_: FakePdf())
    monkeypatch.setattr(statements, "_mistral_ocr_pdf", provider_must_not_run)
    monkeypatch.setattr(statements, "_gemini_parse_pdf", provider_must_not_run)
    assert asyncio.run(statements.parse_pdf(b"%PDF-test", allow_cloud_ai=False)) == []


def test_webhook_delivery_uses_validated_ip_without_second_dns_lookup(monkeypatch):
    monkeypatch.setattr(settings, "webhook_encryption_keys", Fernet.generate_key().decode())
    monkeypatch.setattr(webhook_dispatcher, "validate_webhook_url", lambda _: ["93.184.215.14"])
    connected = []
    sent = []

    class Reader:
        async def readline(self):
            return b"HTTP/1.1 200 OK\r\n"

    class Writer:
        def write(self, data):
            assert b"Host: example.com\r\n" in data
            sent.append(data)

        async def drain(self):
            return None

        def close(self):
            return None

        async def wait_closed(self):
            return None

    async def fake_connect(host, port, **kwargs):
        connected.append((host, port, kwargs["server_hostname"]))
        return Reader(), Writer()

    monkeypatch.setattr(webhook_dispatcher.asyncio, "open_connection", fake_connect)
    hook = SimpleNamespace(url="https://example.com/hook", secret=encrypt_secret("signing-secret"))
    asyncio.run(webhook_dispatcher._deliver(hook, "webhook.test", {}))
    assert connected == [("93.184.215.14", 443, "example.com")]
    headers, body = sent[0].split(b"\r\n\r\n", 1)
    signature = hmac.new(b"signing-secret", body, hashlib.sha256).hexdigest().encode()
    assert b"X-Ledger-Signature: sha256=" + signature in headers
    assert json.loads(body)["timestamp"].encode() in headers


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"])
def test_webhook_rejects_private_dns_answers(monkeypatch, address):
    monkeypatch.setattr(url_guard.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, (address, 443))])
    with pytest.raises(url_guard.UnsafeURLError):
        url_guard.validate_webhook_url("https://example.com/hook")


def test_webhook_rejects_unusual_port():
    with pytest.raises(url_guard.UnsafeURLError):
        url_guard.validate_webhook_url("https://example.com:8443/hook")


def test_ai_router_redacts_before_provider(monkeypatch):
    class CaptureAdapter:
        async def is_available(self):
            return True

        async def generate(self, system, messages, max_tokens):
            assert "person@example.com" not in system
            assert "person@example.com" not in messages[0]["content"]
            return "safe"

    router = AIRouter()
    router.adapters = [("Capture", CaptureAdapter())]
    monkeypatch.setattr(settings, "ai_provider_allowlist", "Capture")
    monkeypatch.setattr(settings, "ai_task_provider_policy", "")
    assert asyncio.run(router.generate("Contact person@example.com", user_message="Email person@example.com")) == "safe"


def test_webhook_rotation_only_activates_after_test_delivery(client, monkeypatch):
    monkeypatch.setattr(settings, "webhook_encryption_keys", Fernet.generate_key().decode())
    with TestSession() as db:
        db.add(Webhook(id="rotation-hook", user_id="test-user-1", url="https://example.com/hook",
                       events="transaction.created", secret=encrypt_secret("old-signing-secret")))
        db.commit()

    async def failed_delivery(*args):
        raise RuntimeError("receiver unavailable")

    monkeypatch.setattr(app_main, "_deliver", failed_delivery)
    payload = {"url": "https://example.com/hook", "events": "transaction.created", "secret": "new-signing-secret"}
    assert client.post("/webhooks/rotation-hook/rotate", json=payload).status_code == 502
    with TestSession() as db:
        assert decrypt_secret(db.get(Webhook, "rotation-hook").secret) == "old-signing-secret"

    async def successful_delivery(*args):
        return None

    monkeypatch.setattr(app_main, "_deliver", successful_delivery)
    assert client.post("/webhooks/rotation-hook/rotate", json=payload).status_code == 200
    with TestSession() as db:
        assert decrypt_secret(db.get(Webhook, "rotation-hook").secret) == "new-signing-secret"


def test_cookie_session_origin_logout_and_headers(monkeypatch):
    monkeypatch.setattr(settings, "auth_provider", "google")
    monkeypatch.setattr(app_main, "_verify_token", lambda _: auth.UserContext(id="test-user-1", email="test@ledger.local"))
    original = fastapi_app.dependency_overrides.pop(auth.get_current_user)
    try:
        with TestClient(fastapi_app) as client:
            origin = {"Origin": "http://localhost:5173"}
            login = client.post("/auth/session", json={"credential": "x" * 20}, headers=origin)
            assert login.status_code == 200, login.text
            assert "httponly" in login.headers["set-cookie"].lower()
            assert "samesite=lax" in login.headers["set-cookie"].lower()
            profile = client.get("/profile")
            assert profile.status_code == 200
            assert profile.headers["cache-control"] == "private, no-store"
            assert profile.headers["x-content-type-options"] == "nosniff"
            assert profile.headers["x-request-id"]
            token = client.cookies.get(auth.SESSION_COOKIE)
            with TestSession() as db:
                row = db.get(AppSession, hashlib.sha256(token.encode()).hexdigest())
                row.reauthed_at = datetime.now(UTC) - timedelta(minutes=10)
                db.commit()
            assert client.get("/export/full").status_code == 428
            payload = base64.urlsafe_b64encode(json.dumps({"iat": int(datetime.now(UTC).timestamp())}).encode()).decode().rstrip("=")
            credential = f"header.{payload}.signature"
            assert client.post("/auth/reauth", json={"credential": credential}, headers=origin).status_code == 200
            assert client.get("/export/full").status_code == 200
            assert client.put("/profile", json={"display_name": "Blocked"}).status_code == 403
            assert client.put("/profile", json={"display_name": "Allowed"}, headers=origin).status_code == 200
            assert client.delete("/auth/session", headers=origin).status_code == 200
            assert client.get("/profile").status_code == 401
    finally:
        fastapi_app.dependency_overrides[auth.get_current_user] = original
