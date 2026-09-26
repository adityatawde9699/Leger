from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.daily_position import calculate_daily_position

from .conftest import AUTH_HEADER

NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)


def _inputs():
    return {
        "accounts": [SimpleNamespace(
            id="cash-1", name="Checking", is_active=True, account_type="current",
            balance=Decimal("1000.00"), last_reconciled_at=NOW - timedelta(hours=1),
        )],
        "transactions": [
            SimpleNamespace(
                id="income", date=date(2026, 9, 5), type="income", status="posted",
                amount=Decimal("500"), category="Salary", account_id="cash-1",
                source="bank", created_at=NOW - timedelta(hours=2),
            ),
            SimpleNamespace(
                id="dining", date=date(2026, 9, 10), type="expense", status="posted",
                amount=Decimal("100"), category="Dining", account_id="cash-1",
                source="bank", created_at=NOW - timedelta(hours=2),
            ),
        ],
        "budgets": [
            SimpleNamespace(category="Dining", monthly_limit=Decimal("200"), updated_at=NOW - timedelta(days=2)),
            SimpleNamespace(category="Housing", monthly_limit=Decimal("250"), updated_at=NOW - timedelta(days=2)),
        ],
        "recurring_rules": [SimpleNamespace(
            description="Rent", category="Housing", status="active", confirmed=True,
            next_expected=date(2026, 9, 28), cadence="monthly", maximum_amount=Decimal("300"),
            updated_at=NOW - timedelta(days=2),
        )],
        "currency": "USD",
        "income_pattern": "regular",
        "obligations_reviewed_at": NOW - timedelta(days=1),
        "as_of": date(2026, 9, 24),
        "now": NOW,
    }


def test_daily_estimate_reserves_budgets_and_bills_without_double_counting():
    result = calculate_daily_position(**_inputs())
    assert result["status"] == "ready"
    assert result["income"] == Decimal("500")
    assert result["committed_spend"] == Decimal("0")
    assert result["flexible_spend"] == Decimal("100")
    assert result["reserve_remaining"] == Decimal("400")
    assert result["safe_to_spend_estimate"] == Decimal("600")
    assert result["upcoming_obligations"][0]["description"] == "Rent"
    assert "not a bank balance" in result["method"]


def test_daily_estimate_withholds_without_review_or_fresh_balance():
    inputs = _inputs()
    inputs["obligations_reviewed_at"] = None
    inputs["accounts"][0].last_reconciled_at = NOW - timedelta(days=12)
    result = calculate_daily_position(**inputs)
    assert result["status"] == "unavailable"
    assert result["safe_to_spend_estimate"] is None
    assert any("Reconcile" in reason for reason in result["reasons"])
    assert any("Confirm" in reason for reason in result["reasons"])


def test_daily_estimate_withholds_after_new_transaction_or_obligation_change():
    inputs = _inputs()
    inputs["transactions"][0].created_at = NOW
    inputs["budgets"][0].updated_at = NOW
    result = calculate_daily_position(**inputs)
    assert result["safe_to_spend_estimate"] is None
    assert any("latest transaction" in reason for reason in result["reasons"])
    assert any("changing a budget" in reason for reason in result["reasons"])


def test_daily_estimate_does_not_combine_mixed_currency_accounts():
    inputs = _inputs()
    inputs["currency_mismatch"] = True
    result = calculate_daily_position(**inputs)
    assert result["status"] == "unavailable"
    assert result["income"] is None
    assert result["cash_available"] is None
    assert result["safe_to_spend_estimate"] is None


def test_obligations_review_requires_explicit_confirmation_and_is_exported(client):
    before = client.get("/daily-position", headers=AUTH_HEADER)
    assert before.status_code == 200
    assert before.json()["status"] == "unavailable"
    assert before.json()["safe_to_spend_estimate"] is None
    assert client.post("/daily-position/review", json={"confirmed": False}, headers=AUTH_HEADER).status_code == 400
    reviewed = client.post("/daily-position/review", json={"confirmed": True}, headers=AUTH_HEADER)
    assert reviewed.status_code == 200
    assert client.get("/profile", headers=AUTH_HEADER).json()["obligations_reviewed_at"]
    assert client.get("/export/full", headers=AUTH_HEADER).json()["profile"]["obligations_reviewed_at"]


def test_daily_position_api_becomes_available_only_after_reconciliation_and_review(client):
    account = client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "current", "currency": "INR", "balance": "1000.00"},
        headers=AUTH_HEADER,
    )
    assert account.status_code == 201
    budget = client.put(
        "/budgets",
        json=[{"category": "Dining", "monthly_limit": "200.00", "strategy": "manual"}],
        headers=AUTH_HEADER,
    )
    assert budget.status_code == 200
    account_id = account.json()["id"]
    assert client.post(
        f"/accounts/{account_id}/reconcile",
        json={"observed_balance": "1000.00"}, headers=AUTH_HEADER,
    ).status_code == 200
    assert client.post(
        "/daily-position/review", json={"confirmed": True}, headers=AUTH_HEADER,
    ).status_code == 200
    position = client.get("/daily-position", headers=AUTH_HEADER)
    assert position.status_code == 200
    assert position.json()["status"] == "ready"
    assert position.json()["reserve_remaining"] == "200.00"
    assert position.json()["safe_to_spend_estimate"] == "800.00"

    manual_balance_edit = client.put(
        f"/accounts/{account_id}",
        json={"name": "Checking", "account_type": "current", "currency": "INR", "balance": "900.00"},
        headers=AUTH_HEADER,
    )
    assert manual_balance_edit.status_code == 200
    assert manual_balance_edit.json()["last_reconciled_at"] is None
    assert client.get("/daily-position", headers=AUTH_HEADER).json()["safe_to_spend_estimate"] is None
    assert client.post(
        f"/accounts/{account_id}/reconcile", json={"observed_balance": "900.00"}, headers=AUTH_HEADER,
    ).status_code == 200

    changed = client.put(
        "/budgets",
        json=[{"category": "Dining", "monthly_limit": "250.00", "strategy": "manual"}],
        headers=AUTH_HEADER,
    )
    assert changed.status_code == 200
    after_change = client.get("/daily-position", headers=AUTH_HEADER).json()
    assert after_change["status"] == "unavailable"
    assert after_change["safe_to_spend_estimate"] is None
