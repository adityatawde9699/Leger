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


def test_reconcile_account_records_difference(client):
    """A real-world balance check is persisted and returned with its difference."""
    r = client.post(
        "/accounts",
        json={"name": "Reconcile me", "account_type": "savings", "balance": "10000"},
        headers=AUTH_HEADER,
    )
    account_id = r.json()["id"]
    r = client.post(
        f"/accounts/{account_id}/reconcile",
        json={"observed_balance": "9750", "note": "Checked against bank app"},
        headers=AUTH_HEADER,
    )
    assert r.status_code == 200
    assert float(r.json()["difference"]) == -250
    assert r.json()["note"] == "Checked against bank app"

    accounts = client.get("/accounts", headers=AUTH_HEADER).json()
    assert float(next(a for a in accounts if a["id"] == account_id)["balance"]) == 9750
