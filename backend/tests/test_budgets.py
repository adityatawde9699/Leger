"""
Tests for budget endpoints.
Budgets use PUT /budgets (upsert with list), not POST.
"""

from .conftest import AUTH_HEADER


def test_upsert_budget(client):
    """PUT /budgets should create/update budgets."""
    r = client.put(
        "/budgets",
        json=[{"category": "Dining", "monthly_limit": "5000"}],
        headers=AUTH_HEADER,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["category"] == "Dining"
    assert float(data[0]["monthly_limit"]) == 5000.00


def test_list_budgets(client):
    """GET /budgets should return user's budgets."""
    client.put(
        "/budgets",
        json=[{"category": "Groceries", "monthly_limit": "8000"}],
        headers=AUTH_HEADER,
    )
    r = client.get("/budgets", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_upsert_multiple_budgets(client):
    """PUT /budgets should handle multiple budgets at once."""
    r = client.put(
        "/budgets",
        json=[
            {"category": "Dining", "monthly_limit": "5000"},
            {"category": "Transport", "monthly_limit": "3000"},
        ],
        headers=AUTH_HEADER,
    )
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_upsert_updates_existing(client):
    """PUT /budgets should update existing budget for same category."""
    client.put(
        "/budgets",
        json=[{"category": "Dining", "monthly_limit": "5000"}],
        headers=AUTH_HEADER,
    )
    r = client.put(
        "/budgets",
        json=[{"category": "Dining", "monthly_limit": "7000"}],
        headers=AUTH_HEADER,
    )
    assert r.status_code == 200
    assert float(r.json()[0]["monthly_limit"]) == 7000.00

    # Should still be only 1 budget
    r = client.get("/budgets", headers=AUTH_HEADER)
    assert len(r.json()) == 1
