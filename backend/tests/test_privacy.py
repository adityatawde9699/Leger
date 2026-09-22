import json

from .conftest import AUTH_HEADER


def test_full_export_is_portable_and_excludes_secrets(client):
    account = client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "current", "balance": "1000"},
        headers=AUTH_HEADER,
    )
    assert account.status_code == 201
    response = client.get("/export/full", headers=AUTH_HEADER)
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["profile"]["id"] == "test-user-1"
    assert payload["accounts"][0]["name"] == "Checking"
    assert "file_content" not in payload
    assert "secret" not in payload


def test_delete_all_data_requires_exact_confirmation_and_removes_profile(client):
    created = client.post(
        "/transactions",
        json={
            "date": "2026-01-01",
            "type": "expense",
            "category": "Dining",
            "amount": "25",
            "description": "Test meal",
        },
        headers=AUTH_HEADER,
    )
    assert created.status_code == 201

    denied = client.request("DELETE", "/profile/data", json={"confirmation": "delete"}, headers=AUTH_HEADER)
    assert denied.status_code == 422

    deleted = client.request("DELETE", "/profile/data", json={"confirmation": "DELETE"}, headers=AUTH_HEADER)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get("/profile", headers=AUTH_HEADER).status_code == 404
