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
