"""Authenticated encryption for user-owned portable backups."""

import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


def _fernet(key: str) -> Fernet:
    if not key:
        raise ValueError("BACKUP_ENCRYPTION_KEY is not configured")
    return Fernet(key.encode())


def encrypt_backup(payload: dict, key: str) -> str:
    body = json.dumps(payload, separators=(",", ":"), default=str).encode()
    return _fernet(key).encrypt(body).decode()


def decrypt_backup(token: str, key: str, previous_keys: str = "") -> dict:
    try:
        keys = [_fernet(key)] + [_fernet(old.strip()) for old in previous_keys.split(",") if old.strip()]
        payload = json.loads(MultiFernet(keys).decrypt(token.encode()))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or unreadable encrypted backup") from exc
    if not isinstance(payload, dict) or payload.get("export_version") != 1:
        raise ValueError("Unsupported backup format")
    return payload
