from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.proactive_insights import _decorate, _is_quantified_and_actionable, apply_insight_frequency


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
    assert first["analysis"]["transaction_ids"] == ["tx-1"]
    assert first["analysis"]["method"] == "evidence-linked deterministic rule"
    assert first["recommended_action"] == "Review the supporting transactions"


def test_generic_insight_requires_quantified_claim_and_action():
    evidence = [{"transaction_id": "tx-1"}]
    assert not _is_quantified_and_actionable({"text": "Review your spending", "action": "Review it", "evidence": evidence})
    assert not _is_quantified_and_actionable({"text": "Spending rose 20%", "action": None, "evidence": evidence})
    assert _is_quantified_and_actionable({"text": "Spending rose 20%", "action": "Review Food", "evidence": evidence})


def test_insight_frequency_filters_without_claiming_scheduler_support():
    insights = [{"id": "low", "priority": 3}, {"id": "high", "priority": 4}]
    assert apply_insight_frequency(insights, "off") == []
    assert apply_insight_frequency(insights, "important") == [{"id": "high", "priority": 4}]
    assert apply_insight_frequency(insights, "weekly") == insights
