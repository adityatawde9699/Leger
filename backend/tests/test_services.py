"""
Tests for AI/analytics service endpoints (credit health, benchmarks).
"""

from .conftest import AUTH_HEADER


def test_credit_health(client):
    """GET /credit-health should return a score."""
    # Add some transactions first
    for i in range(3):
        client.post(
            "/transactions",
            json={
                "type": "expense",
                "category": "Dining",
                "amount": "500",
                "description": f"Lunch {i}",
                "date": "2026-05-15",
            },
            headers=AUTH_HEADER,
        )
    client.post(
        "/transactions",
        json={
            "type": "income",
            "category": "Salary",
            "amount": "50000",
            "description": "Salary",
            "date": "2026-05-01",
        },
        headers=AUTH_HEADER,
    )

    r = client.get("/credit-health", headers=AUTH_HEADER)
    assert r.status_code == 200
    data = r.json()
    assert 300 <= data["score"] <= 900
    assert data["grade"] in ("Excellent", "Good", "Fair", "Poor")
    assert "breakdown" in data
    assert "tips" in data


def test_benchmarks(client):
    """GET /benchmarks should return percentile data."""
    client.post(
        "/transactions",
        json={
            "type": "expense",
            "category": "Groceries",
            "amount": "3000",
            "description": "Monthly groceries",
            "date": "2026-05-10",
        },
        headers=AUTH_HEADER,
    )

    r = client.get("/benchmarks", headers=AUTH_HEADER)
    assert r.status_code == 200
    data = r.json()
    assert "overall_percentile" in data
    assert "categories" in data
    assert isinstance(data["categories"], list)


def test_credit_health_empty(client):
    """Credit health should still work with no transactions."""
    r = client.get("/credit-health", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert 300 <= r.json()["score"] <= 900


def test_auto_categorize_endpoint(client):
    """POST /categorize should return correct categories for new rules."""
    payloads = [
        {"description": "dimono upi transaction", "expected": "Dining"},
        {"description": "dominos pizza order", "expected": "Dining"},
        {"description": "zepto groceries order", "expected": "Groceries"},
        {"description": "starbucks cafe coffee", "expected": "Dining"},
        {"description": "chaloasc/yesb/chaloascdc/paym", "expected": "Transport"},
        {"description": "croma au/yesb/paytm-7466", "expected": "Shopping"},
        # coursera is correctly Education in the new 18-category taxonomy
        {"description": "coursera/airp/coursera34", "expected": "Education"},
    ]
    for p in payloads:
        r = client.post(
            "/categorize",
            json={"description": p["description"], "tx_type": "expense"},
            headers=AUTH_HEADER,
        )
        assert r.status_code == 200
        assert r.json()["category"] == p["expected"]
