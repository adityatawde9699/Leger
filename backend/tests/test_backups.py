from cryptography.fernet import Fernet

from app.services.backups import decrypt_backup, encrypt_backup


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
