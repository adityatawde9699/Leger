import base64

from app.models import ReceiptAttachment

from .conftest import AUTH_HEADER, TEST_USER_ID, TestSession

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII="
)


def _transaction(client):
    response = client.post(
        "/transactions",
        json={"date": "2026-09-24", "type": "expense", "category": "Dining", "amount": "5.25", "description": "Lunch"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_receipt_is_private_exportable_and_deleted_with_transaction(client):
    tx_id = _transaction(client)
    attached = client.post(
        f"/transactions/{tx_id}/receipt", files={"file": ("receipt.png", PNG, "image/png")}, headers=AUTH_HEADER,
    )
    assert attached.status_code == 201
    assert attached.json()["mime_type"] == "image/png"

    downloaded = client.get(f"/transactions/{tx_id}/receipt", headers=AUTH_HEADER)
    assert downloaded.status_code == 200
    assert downloaded.content == PNG
    assert downloaded.headers["cache-control"] == "private, no-store"

    exported = client.get("/export/full", headers=AUTH_HEADER).json()
    assert exported["receipts"][0]["transaction_id"] == tx_id
    assert base64.b64decode(exported["receipts"][0]["content_base64"]) == PNG

    assert client.delete(f"/transactions/{tx_id}", headers=AUTH_HEADER).status_code == 200
    assert client.get(f"/transactions/{tx_id}/receipt", headers=AUTH_HEADER).status_code == 404
    db = TestSession()
    try:
        assert db.query(ReceiptAttachment).filter(ReceiptAttachment.user_id == TEST_USER_ID).count() == 0
    finally:
        db.close()


def test_receipt_rejects_invalid_files_and_duplicate_attachment(client):
    tx_id = _transaction(client)
    bad = client.post(
        f"/transactions/{tx_id}/receipt", files={"file": ("fake.png", b"not a PNG", "image/png")}, headers=AUTH_HEADER,
    )
    assert bad.status_code == 400
    too_large = client.post(
        f"/transactions/{tx_id}/receipt", files={"file": ("huge.png", PNG + b"x" * (5 * 1024 * 1024), "image/png")},
        headers=AUTH_HEADER,
    )
    assert too_large.status_code == 413
    assert client.post(
        f"/transactions/{tx_id}/receipt", files={"file": ("receipt.png", PNG, "image/png")}, headers=AUTH_HEADER,
    ).status_code == 201
    assert client.post(
        f"/transactions/{tx_id}/receipt", files={"file": ("receipt.png", PNG, "image/png")}, headers=AUTH_HEADER,
    ).status_code == 201
    assert client.delete(f"/transactions/{tx_id}/receipt", headers=AUTH_HEADER).status_code == 200
    assert client.get(f"/transactions/{tx_id}/receipt", headers=AUTH_HEADER).status_code == 404


def test_receipt_cannot_attach_to_another_users_transaction(client):
    response = client.post(
        "/transactions/missing-user-transaction/receipt",
        files={"file": ("receipt.png", PNG, "image/png")}, headers=AUTH_HEADER,
    )
    assert response.status_code == 404


def test_full_data_deletion_removes_receipt_bytes(client):
    tx_id = _transaction(client)
    assert client.post(
        f"/transactions/{tx_id}/receipt", files={"file": ("receipt.png", PNG, "image/png")}, headers=AUTH_HEADER,
    ).status_code == 201
    deleted = client.request("DELETE", "/profile/data", json={"confirmation": "DELETE"}, headers=AUTH_HEADER)
    assert deleted.status_code == 200
    db = TestSession()
    try:
        assert db.query(ReceiptAttachment).filter(ReceiptAttachment.user_id == TEST_USER_ID).count() == 0
    finally:
        db.close()
