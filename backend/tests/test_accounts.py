"""
Tests for account management endpoints.
"""

from .conftest import AUTH_HEADER


def test_create_account(client):
    """POST /accounts should create an account."""
    r = client.post(
        "/accounts",
        json={"name": "HDFC Savings", "account_type": "savings", "balance": "50000"},
        headers=AUTH_HEADER,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "HDFC Savings"
    assert data["account_type"] == "savings"
    assert data["is_active"] is True


def test_list_accounts(client):
    """GET /accounts should return user accounts."""
    client.post(
        "/accounts",
        json={"name": "SBI", "account_type": "savings", "balance": "10000"},
        headers=AUTH_HEADER,
    )
    r = client.get("/accounts", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_delete_account(client):
    """DELETE /accounts/{id} should remove the account."""
    r = client.post(
        "/accounts",
        json={"name": "Temp", "account_type": "cash", "balance": "0"},
        headers=AUTH_HEADER,
    )
    acc_id = r.json()["id"]
    r = client.delete(f"/accounts/{acc_id}", headers=AUTH_HEADER)
    assert r.status_code == 200
