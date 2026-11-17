import asyncio
import base64
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app import auth
from app import main as app_main
from app.config import Settings, settings
from app.main import _validate_statement_content
from app.models import AppSession
from app.services.ai_router import AIRouter
from app.services.backups import decrypt_backup, encrypt_backup
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


def test_production_accepts_root_slash_cors_origin_but_rejects_paths():
    config = Settings(_env_file=None, environment="production", auth_provider="google",
                      google_client_id="client", cors_origins="https://ledger-beta-two.vercel.app/",
                      backup_encryption_key=Fernet.generate_key().decode(),
                      upstash_redis_rest_url="https://redis.example",
                      upstash_redis_rest_token="rest-token")
    assert config.get_cors_origins() == ["https://ledger-beta-two.vercel.app"]
    config.validate_for_production()
    config.cors_origins = "https://ledger-beta-two.vercel.app/private/"
    with pytest.raises(SystemExit):
        config.validate_for_production()


def test_production_requires_shared_redis():
    config = Settings(_env_file=None, environment="production", auth_provider="google",
                      google_client_id="client", cors_origins="https://ledger.example",
                      backup_encryption_key=Fernet.generate_key().decode(),
                      upstash_redis_rest_url="https://redis.example",
                      upstash_redis_rest_token="rest-token")
    config.validate_for_production()
    config.upstash_redis_rest_url = "http://localhost:6379"
    with pytest.raises(SystemExit):
        config.validate_for_production()


@pytest.mark.parametrize("redis_url", [
    "redis-cli --tls -u redis://default:example-secret@redis.example:6379",
    "http://redis.example.upstash.io",
    "https://default:example-secret@redis.example.upstash.io",
])
def test_production_rejects_invalid_redis_url_without_leaking_credentials(redis_url, capsys):
    config = Settings(_env_file=None, environment="production", auth_provider="google",
                      google_client_id="client", cors_origins="https://ledger.example",
                      backup_encryption_key=Fernet.generate_key().decode(),
                      upstash_redis_rest_url=redis_url,
                      upstash_redis_rest_token="rest-token")
    with pytest.raises(SystemExit):
        config.validate_for_production()
    message = capsys.readouterr().err
    assert "UPSTASH_REDIS_REST_URL" in message
    assert "example-secret" not in message


@pytest.mark.parametrize("field,env_name", [
    ("backup_encryption_key", "BACKUP_ENCRYPTION_KEY"),
    ("backup_previous_encryption_keys", "BACKUP_PREVIOUS_ENCRYPTION_KEYS"),
])
def test_production_identifies_invalid_encryption_key_without_leaking_it(field, env_name, capsys):
    config = Settings(_env_file=None, environment="production", auth_provider="google",
                      google_client_id="client", cors_origins="https://ledger.example",
                      backup_encryption_key=Fernet.generate_key().decode(),
                      upstash_redis_rest_url="https://redis.example",
                      upstash_redis_rest_token="rest-token")
    setattr(config, field, "invalid-secret-value")
    with pytest.raises(SystemExit):
        config.validate_for_production()
    message = capsys.readouterr().err
    assert env_name in message
    assert "invalid-secret-value" not in message


def test_empty_previous_backup_keys_environment_value_remains_a_string(monkeypatch):
    monkeypatch.setenv("BACKUP_PREVIOUS_ENCRYPTION_KEYS", "")
    config = Settings(_env_file=None)
    assert config.backup_previous_encryption_keys == ""


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


def test_rate_limit_identity_keys_signed_in_users_by_session_not_ip():
    """Behind the proxy every request shares one IP; signed-in users must not share a bucket,
    and a spoofed X-Forwarded-For must not mint a new bucket for the same session."""
    from starlette.requests import Request as StarletteRequest

    from app.main import SESSION_COOKIE, _rate_limit_identity

    def request(ip: str, cookie: str | None = None) -> StarletteRequest:
        headers = [(b"cookie", f"{SESSION_COOKIE}={cookie}".encode())] if cookie else []
        return StarletteRequest({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (ip, 1234)})

    assert _rate_limit_identity(request("10.0.0.1", "token-a")) == _rate_limit_identity(request("203.0.113.9", "token-a"))
    assert _rate_limit_identity(request("10.0.0.1", "token-a")) != _rate_limit_identity(request("10.0.0.1", "token-b"))
    assert _rate_limit_identity(request("198.51.100.1")) != _rate_limit_identity(request("198.51.100.2"))
