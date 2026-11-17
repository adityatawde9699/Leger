import pytest
from cryptography.fernet import Fernet

from app.config import settings
from app.models import Account, Transaction
from app.services.backups import decrypt_backup, encrypt_backup

from .conftest import AUTH_HEADER, TEST_USER_ID, TestSession


def test_encrypted_backup_round_trip_and_tamper_rejection():
    key = Fernet.generate_key().decode()
    payload = {"export_version": 1, "transactions": [{"id": "tx-1"}]}
    token = encrypt_backup(payload, key)

    assert decrypt_backup(token, key) == payload
    try:
        decrypt_backup(token[:-2] + "xx", key)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered backup was accepted")


@pytest.fixture()
def backup_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "backup_encryption_key", key)
    return key


def _backup(key, owner_id, transactions):
    return encrypt_backup({"export_version": 1, "profile": {"id": owner_id}, "accounts": [],
                           "transactions": transactions}, key)


def _tx_record(record_id, **overrides):
    return {"id": record_id, "date": "2026-03-01", "type": "expense", "status": "posted", "category": "Food",
            "amount": "42.00", "description": "Restored lunch", "source": "cash", **overrides}


def test_backup_export_restores_into_the_same_account(client, backup_key):
    client.post("/accounts", json={"name": "Wallet", "account_type": "cash", "balance": "100.00", "currency": "INR"},
                headers=AUTH_HEADER)
    client.post("/transactions", json={"date": "2026-03-02", "type": "expense", "category": "Food",
                                       "amount": "15.00", "description": "Tea"}, headers=AUTH_HEADER)
    token = client.get("/backup/export", headers=AUTH_HEADER).json()["encrypted_backup"]
    with TestSession() as db:
        db.query(Transaction).delete()
        db.query(Account).delete()
        db.commit()

    restored = client.post("/backup/restore", json={"encrypted_backup": token, "confirmation": "RESTORE", "dry_run": False}, headers=AUTH_HEADER)

    assert restored.status_code == 200, restored.text
    assert restored.json()["accounts"] == 1 and restored.json()["transactions"] == 1
    with TestSession() as db:
        assert db.query(Transaction).filter_by(user_id=TEST_USER_ID, description="Tea").count() == 1


def test_backup_from_another_account_is_refused(client, backup_key):
    token = _backup(backup_key, "someone-else", [_tx_record("tx-other")])

    for dry_run in (True, False):
        response = client.post("/backup/restore", json={"encrypted_backup": token, "confirmation": "RESTORE", "dry_run": dry_run},
                               headers=AUTH_HEADER)
        assert response.status_code == 403
    with TestSession() as db:
        assert db.get(Transaction, "tx-other") is None


def test_backup_with_an_invalid_record_restores_nothing(client, backup_key):
    token = _backup(backup_key, TEST_USER_ID, [_tx_record("tx-good"), _tx_record("tx-bad", type="bogus")])

    response = client.post("/backup/restore", json={"encrypted_backup": token, "confirmation": "RESTORE", "dry_run": False}, headers=AUTH_HEADER)

    assert response.status_code == 400
    with TestSession() as db:
        assert db.get(Transaction, "tx-good") is None
