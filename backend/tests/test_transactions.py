"""
Tests for core transaction CRUD endpoints.
"""

from .conftest import AUTH_HEADER


def test_health_check(client):
    """App should respond on /health."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_create_transaction(client):
    """POST /transactions should create and return a transaction."""
    payload = {
        "type": "expense",
        "category": "Dining",
        "amount": "250.00",
        "description": "Lunch at cafe",
        "date": "2026-05-15",
    }
    r = client.post("/transactions", json=payload, headers=AUTH_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert data["category"] == "Dining"
    assert float(data["amount"]) == 250.00
    assert data["type"] == "expense"
    assert "id" in data


def test_list_transactions_empty(client):
    """GET /transactions should return empty list initially."""
    r = client.get("/transactions", headers=AUTH_HEADER)
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total_returned"] == 0


def test_list_transactions_with_data(client):
    """GET /transactions should return created transactions."""
    client.post(
        "/transactions",
        json={
            "type": "income",
            "category": "Salary",
            "amount": "50000",
            "description": "Monthly salary",
            "date": "2026-05-01",
        },
        headers=AUTH_HEADER,
    )
    r = client.get("/transactions", headers=AUTH_HEADER)
    assert r.status_code == 200
    data = r.json()
    assert data["total_returned"] == 1
    assert data["items"][0]["category"] == "Salary"


def test_pending_transactions_are_reviewable_but_not_in_default_list(client):
    created = client.post(
        "/transactions",
        json={
            "type": "expense",
            "status": "pending",
            "category": "Dining",
            "amount": "250",
            "description": "Pending meal",
            "date": "2026-05-15",
        },
        headers=AUTH_HEADER,
    )
    assert created.status_code == 201
    assert client.get("/transactions", headers=AUTH_HEADER).json()["total_returned"] == 0
    pending = client.get("/transactions?status=pending", headers=AUTH_HEADER)
    assert pending.status_code == 200
    assert pending.json()["total_returned"] == 1


def test_delete_transaction(client):
    """DELETE /transactions/{id} should remove the transaction."""
    r = client.post(
        "/transactions",
        json={
            "type": "expense",
            "category": "Shopping",
            "amount": "1000",
            "description": "Amazon order",
            "date": "2026-05-10",
        },
        headers=AUTH_HEADER,
    )
    tx_id = r.json()["id"]

    r = client.delete(f"/transactions/{tx_id}", headers=AUTH_HEADER)
    assert r.status_code == 200

    r = client.get("/transactions", headers=AUTH_HEADER)
    assert r.json()["total_returned"] == 0


def test_update_transaction(client):
    """PUT /transactions/{id} should update fields."""
    r = client.post(
        "/transactions",
        json={
            "type": "expense",
            "category": "Other",
            "amount": "500",
            "description": "Test",
            "date": "2026-05-10",
        },
        headers=AUTH_HEADER,
    )
    tx_id = r.json()["id"]

    r = client.put(
        f"/transactions/{tx_id}",
        json={
            "type": "expense",
            "category": "Education",
            "amount": "600",
            "description": "Updated",
            "date": "2026-05-10",
        },
        headers=AUTH_HEADER,
    )
    assert r.status_code == 200
    assert r.json()["category"] == "Education"
    assert float(r.json()["amount"]) == 600.00


def test_update_transaction_can_be_undone(client):
    created = client.post(
        "/transactions",
        json={
            "type": "expense",
            "category": "Other",
            "amount": "500",
            "description": "Original",
            "date": "2026-05-10",
        },
        headers=AUTH_HEADER,
    )
    tx_id = created.json()["id"]
    updated = client.put(
        f"/transactions/{tx_id}",
        json={
            "type": "expense",
            "category": "Education",
            "amount": "600",
            "description": "Changed",
            "date": "2026-05-10",
        },
        headers=AUTH_HEADER,
    )
    assert updated.status_code == 200

    undone = client.post(f"/transactions/{tx_id}/undo", headers=AUTH_HEADER)
    assert undone.status_code == 200
    assert undone.json()["category"] == "Other"
    assert float(undone.json()["amount"]) == 500.00
    assert undone.json()["description"] == "Original"

    second_undo = client.post(f"/transactions/{tx_id}/undo", headers=AUTH_HEADER)
    assert second_undo.status_code == 409


def test_category_correction_is_reversible(client):
    created = client.post(
        "/transactions",
        json={
            "type": "expense",
            "category": "Other",
            "amount": "100",
            "description": "Merchant",
            "date": "2026-05-10",
        },
        headers=AUTH_HEADER,
    )
    tx_id = created.json()["id"]
    corrected = client.post(
        f"/transactions/{tx_id}/correct-category",
        json={"category": "Dining"},
        headers=AUTH_HEADER,
    )
    assert corrected.status_code == 200

    undone = client.post(f"/transactions/{tx_id}/undo", headers=AUTH_HEADER)
    assert undone.status_code == 200
    assert undone.json()["category"] == "Other"
    assert undone.json()["confidence"] is None


def test_unauthorized_without_header(client):
    """Endpoints reject requests without auth in production.
    In the test suite the auth dependency is globally overridden,
    so this check is validated at the integration level instead.
    """
    import pytest

    pytest.skip("Auth dependency is globally mocked in conftest — tested at integration level")


def test_bulk_delete_transactions(client):
    """POST /transactions/bulk-delete should remove multiple transactions."""
    ids = []
    for desc in ["Tx A", "Tx B", "Tx C"]:
        r = client.post(
            "/transactions",
            json={
                "type": "expense",
                "category": "Dining",
                "amount": "100",
                "description": desc,
                "date": "2026-05-10",
            },
            headers=AUTH_HEADER,
        )
        assert r.status_code == 201
        ids.append(r.json()["id"])

    payload = {"transaction_ids": ids}
    r = client.post("/transactions/bulk-delete", json=payload, headers=AUTH_HEADER)
    assert r.status_code == 200
    assert r.json()["deleted_count"] == 3

    r = client.get("/transactions", headers=AUTH_HEADER)
    assert r.status_code == 200
    items = r.json()["items"]
    for tx in items:
        assert tx["id"] not in ids


def test_refund_offsets_spending_and_transfer_is_excluded(client):
    """Refunds reduce expenses while transfers do not distort cash-flow totals."""
    for payload in [
        {"type": "income", "category": "Salary", "amount": "1000", "description": "Pay", "date": "2026-05-01"},
        {"type": "expense", "category": "Dining", "amount": "400", "description": "Meal", "date": "2026-05-02"},
        {"type": "refund", "category": "Dining", "amount": "100", "description": "Meal refund", "date": "2026-05-03"},
        {"type": "transfer", "category": "Transfer", "amount": "500", "description": "Move money", "date": "2026-05-04"},
    ]:
        r = client.post("/transactions", json=payload, headers=AUTH_HEADER)
        assert r.status_code == 201

    summary = client.get("/summary?range=all", headers=AUTH_HEADER)
    assert summary.status_code == 200
    assert float(summary.json()["income"]) == 1000
    assert float(summary.json()["expenses"]) == 300
    assert float(summary.json()["net"]) == 700


def test_transaction_rejects_another_users_account(client):
    """A transaction cannot be attached to an account owned by another user."""
    from app.models import Account, User

    from .conftest import TestSession

    other_db = TestSession()
    try:
        other_db.add(User(id="someone-else", email="other@ledger.local"))
        other_db.add(Account(user_id="someone-else", name="Private", account_type="savings", balance=0))
        other_db.commit()
        account_id = other_db.query(Account).filter(Account.user_id == "someone-else").first().id
    finally:
        other_db.close()

    r = client.post(
        "/transactions",
        json={
            "type": "expense", "category": "Dining", "amount": "100", "description": "Nope",
            "date": "2026-05-10", "account_id": account_id,
        },
        headers=AUTH_HEADER,
    )
    assert r.status_code == 400
