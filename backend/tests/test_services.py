"""
Tests for AI/analytics service endpoints (credit health, benchmarks).
"""

from decimal import Decimal

from app.models import Account

from .conftest import AUTH_HEADER, TEST_USER_ID, TestSession


def test_credit_health(client):
    """Financial picture uses recorded facts, not a fabricated bureau score."""
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
    assert data["status"] == "ready"
    assert data["income"] == "50000.00"
    assert data["expenses"] == "1500.00"
    assert data["net"] == "48500.00"
    assert data["savings_rate_pct"] == "97.0"
    assert data["credit_assessment"] == "unavailable"
    assert "score" not in data


def test_benchmarks(client):
    """Peer comparison cannot imply a sampled population we do not have."""
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
    assert data["comparison_status"] == "unavailable"
    assert "No verified" in data["reason"]
    assert data["total_spending"] == "3000.00"
    assert data["categories"] == [{"category": "Groceries", "your_spend": "3000.00"}]
    assert "overall_percentile" not in data
    assert "sample_size" not in data


def test_credit_health_empty(client):
    """Empty history must not receive a numeric score or savings rate."""
    r = client.get("/credit-health", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert r.json()["status"] == "insufficient_data"
    assert r.json()["savings_rate_pct"] is None
    assert "score" not in r.json()


def test_credit_readiness_uses_only_entered_account_facts(client):
    account = client.post(
        "/accounts",
        json={
            "name": "Card", "account_type": "credit", "balance": "200.00", "currency": "INR",
            "credit_limit": "1000.00", "minimum_payment": "50.00", "payment_due_date": "2026-10-05",
        },
        headers=AUTH_HEADER,
    )
    assert account.status_code == 201
    health = client.get("/credit-health", headers=AUTH_HEADER).json()
    assert health["credit_assessment"] == "recorded_obligations"
    assert health["credit_readiness"]["status"] == "ready"
    assert health["credit_readiness"]["accounts"][0]["utilization_pct"] == "20.0"
    assert "score" not in health


def test_financial_picture_uses_posted_net_spending(client):
    for kind, amount, status in (
        ("income", "100.00", "posted"),
        ("expense", "30.00", "posted"),
        ("refund", "5.00", "posted"),
        ("expense", "90.00", "pending"),
        ("transfer", "50.00", "posted"),
    ):
        response = client.post(
            "/transactions",
            json={
                "date": "2026-05-15", "type": kind, "status": status,
                "category": "Dining", "amount": amount, "description": f"{kind} item",
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 201

    health = client.get("/credit-health", headers=AUTH_HEADER).json()
    assert health["income"] == "100.00"
    assert health["expenses"] == "25.00"
    assert health["net"] == "75.00"
    assert health["savings_rate_pct"] == "75.0"
    assert health["transaction_count"] == 4

    peers = client.get("/benchmarks", headers=AUTH_HEADER).json()
    assert peers["total_spending"] == "25.00"
    assert peers["categories"] == [{"category": "Dining", "your_spend": "25.00"}]


def test_financial_picture_hides_totals_when_account_currencies_conflict(client):
    db = TestSession()
    try:
        db.add(Account(
            user_id=TEST_USER_ID, name="Legacy USD account", account_type="current",
            balance=Decimal("20.50"), currency="USD",
        ))
        db.commit()
    finally:
        db.close()

    health = client.get("/credit-health", headers=AUTH_HEADER).json()
    peers = client.get("/benchmarks", headers=AUTH_HEADER).json()
    assert health["status"] == "currency_mismatch"
    assert health["income"] is None
    assert health["savings_rate_pct"] is None
    assert peers["total_spending"] is None
    assert peers["categories"] == []


def test_summary_fixed_flexible_analysis_uses_confirmed_rule_evidence(client):
    """Committed spending must be evidence-linked, not category-wide guesswork."""
    subscription = client.post(
        "/transactions",
        json={
            "type": "expense", "category": "Subscriptions", "amount": "100.00",
            "description": "Video service", "date": "2026-05-05",
        },
        headers=AUTH_HEADER,
    ).json()
    client.post(
        "/transactions",
        json={
            "type": "expense", "category": "Subscriptions", "amount": "30.00",
            "description": "Other service", "date": "2026-05-06",
        },
        headers=AUTH_HEADER,
    )
    recurring = client.post(
        "/recurring",
        json={
            "description": "video service", "category": "Subscriptions", "cadence": "monthly",
            "average_amount": "100.00", "minimum_amount": "90.00", "maximum_amount": "110.00",
            "next_expected": "2026-06-05", "confidence": 0.95, "confirmed": True,
            "evidence_transaction_ids": [subscription["id"]],
        },
        headers=AUTH_HEADER,
    )
    assert recurring.status_code == 201

    analysis = client.get("/summary?range=all", headers=AUTH_HEADER).json()["analysis"]["fixed_flexible"]
    assert analysis["status"] == "ready"
    assert analysis["fixed_amount"] == 100.0
    assert analysis["flexible_amount"] == 30.0
    assert analysis["fixed_transaction_ids"] == [subscription["id"]]
    assert analysis["flexible_transaction_ids"]


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
