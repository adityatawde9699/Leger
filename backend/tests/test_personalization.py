from .conftest import AUTH_HEADER


def test_merchant_alias_preserves_original_description(client):
    alias = client.post("/merchant-aliases", json={"alias": "AMZN MKT", "canonical": "Amazon"}, headers=AUTH_HEADER)
    assert alias.status_code == 201

    created = client.post("/transactions", json={
        "type": "expense", "category": "Shopping", "amount": "125", "description": "AMZN MKT", "date": "2026-05-10",
    }, headers=AUTH_HEADER)
    assert created.status_code == 201
    assert created.json()["description"] == "AMZN MKT"
    assert created.json()["merchant_normalized"] == "Amazon"


def test_custom_category_can_be_added_and_deactivated(client):
    created = client.post("/categories", json={"name": "Pet Care", "kind": "expense", "reporting_group": "Lifestyle"}, headers=AUTH_HEADER)
    assert created.status_code == 201
    category_id = created.json()["id"]
    assert any(item["name"] == "Pet Care" for item in client.get("/categories", headers=AUTH_HEADER).json())

    removed = client.delete(f"/categories/{category_id}", headers=AUTH_HEADER)
    assert removed.status_code == 200
    assert not any(item["name"] == "Pet Care" for item in client.get("/categories", headers=AUTH_HEADER).json())


def test_recurring_rule_requires_owned_posted_evidence_and_can_be_confirmed(client):
    tx = client.post("/transactions", json={
        "type": "expense", "category": "Subscriptions", "amount": "499", "description": "Video Service", "date": "2026-05-01",
    }, headers=AUTH_HEADER).json()
    payload = {
        "description": "Video Service", "category": "Subscriptions", "cadence": "monthly",
        "average_amount": "499", "minimum_amount": "499", "maximum_amount": "499",
        "next_expected": "2026-06-01", "confidence": 0.9, "status": "active",
        "confirmed": True, "evidence_transaction_ids": [tx["id"]],
    }
    created = client.post("/recurring", json=payload, headers=AUTH_HEADER)
    assert created.status_code == 201
    assert created.json()["confirmed"] is True
    assert created.json()["evidence_transaction_ids"] == [tx["id"]]

    listed = client.get("/recurring", headers=AUTH_HEADER)
    assert listed.status_code == 200
    assert listed.json()[0]["description"] == "Video Service"
