from decimal import Decimal

from .conftest import AUTH_HEADER


def _payload():
    return {
        "date": "2026-09-24", "status": "posted", "amount": "12.75",
        "description": "Market basket",
        "lines": [
            {"category": "Groceries", "amount": "10.25"},
            {"category": "Health", "amount": "2.50"},
        ],
    }


def test_split_saves_atomic_category_lines_without_double_counting(client):
    response = client.post("/transactions/split", json=_payload(), headers=AUTH_HEADER)
    assert response.status_code == 201
    body = response.json()
    assert body["group_id"].startswith("split:")
    assert len(body["items"]) == 2
    assert {item["source_ref"] for item in body["items"]} == {body["group_id"]}

    summary = client.get("/summary?range=all", headers=AUTH_HEADER).json()
    assert Decimal(str(summary["expenses"])) == Decimal("12.75")
    assert Decimal(str(summary["by_category"]["Groceries"])) == Decimal("10.25")
    assert Decimal(str(summary["by_category"]["Health"])) == Decimal("2.50")


def test_invalid_split_does_not_create_partial_rows(client):
    payload = _payload()
    payload["lines"][1]["amount"] = "3.00"
    response = client.post("/transactions/split", json=payload, headers=AUTH_HEADER)
    assert response.status_code == 400
    assert client.get("/transactions", headers=AUTH_HEADER).json()["items"] == []


def test_split_retry_with_same_client_request_id_is_idempotent(client):
    payload = {**_payload(), "client_request_id": "11111111-1111-4111-8111-111111111111"}
    first = client.post("/transactions/split", json=payload, headers=AUTH_HEADER)
    second = client.post("/transactions/split", json=payload, headers=AUTH_HEADER)
    assert first.status_code == 201
    assert second.status_code == 201
    assert {item["id"] for item in first.json()["items"]} == {item["id"] for item in second.json()["items"]}
    assert client.get("/transactions", headers=AUTH_HEADER).json()["total_returned"] == 2
    changed = {**payload, "description": "Different basket"}
    assert client.post("/transactions/split", json=changed, headers=AUTH_HEADER).status_code == 409


def test_split_rejects_account_owned_by_another_user(client):
    payload = _payload()
    payload["account_id"] = "missing-account"
    response = client.post("/transactions/split", json=payload, headers=AUTH_HEADER)
    assert response.status_code == 400
