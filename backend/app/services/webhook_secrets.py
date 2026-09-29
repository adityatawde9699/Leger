"""Encryption at rest for webhook signing keys.

WEBHOOK_ENCRYPTION_KEYS is a comma-separated key ring; the first key encrypts
new values and remaining keys allow a staged rotation.
"""
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from ..config import settings


def _cipher() -> MultiFernet:
    keys = [value.strip() for value in settings.webhook_encryption_keys.split(",") if value.strip()]
    if not keys:
        raise RuntimeError("Webhook encryption is not configured")
    return MultiFernet([Fernet(key.encode()) for key in keys])


def encrypt_secret(secret: str) -> str:
    return "enc:v1:" + _cipher().encrypt(secret.encode()).decode()


def decrypt_secret(value: str) -> str:
    if not value.startswith("enc:v1:"):
        raise RuntimeError("Unencrypted webhook secret requires migration")
    return _cipher().decrypt(value[7:].encode()).decode()


def migrate_plaintext_secrets(db) -> int:
    """Encrypt legacy rows and rewrap rows encrypted with a previous key."""
    from ..models import Webhook

    if not settings.webhook_encryption_keys:
        return 0
    primary = Fernet(settings.webhook_encryption_keys.split(",")[0].strip().encode())
    changed = 0
    for hook in db.query(Webhook).all():
        if not hook.secret.startswith("enc:v1:"):
            hook.secret = encrypt_secret(hook.secret)
            changed += 1
            continue
        try:
            primary.decrypt(hook.secret[7:].encode())
        except InvalidToken:
            hook.secret = encrypt_secret(decrypt_secret(hook.secret))
            changed += 1
    db.commit()
    return changed
