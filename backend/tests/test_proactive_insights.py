from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.proactive_insights import _decorate


def test_proactive_insight_gets_stable_id_without_leaking_financial_text():
    transactions = [
        SimpleNamespace(
            id="tx-1",
            date=date(2026, 2, 5),
            type="expense",
            amount=Decimal("100"),
            category="Food",
            account_id="account-1",
            description="Lunch at Example Cafe",
            merchant_normalized=None,
        )
    ]
    first = _decorate(
        {"type": "tip", "category": "Food", "text": "Review food spending", "action_type": "view_transactions"},
        transactions,
    )
    second = _decorate(
        {"type": "tip", "category": "Food", "text": "Review food spending", "action_type": "view_transactions"},
        transactions,
    )
    assert first["id"] == second["id"]
    assert first["id"].startswith("insight_")
    assert "Example Cafe" not in first["id"]
