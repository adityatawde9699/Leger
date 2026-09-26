from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.leakage import detect_leakage


def transaction(identifier, day, amount, merchant="streaming", category="Subscriptions"):
    return SimpleNamespace(
        id=identifier, date=day, amount=Decimal(amount), type="expense", status="posted",
        description=merchant, merchant_normalized=merchant, category=category,
    )


def test_leakage_requires_evidence_and_surfaces_price_change_and_concentration():
    rows = [
        transaction("a", date(2026, 1, 5), "10"),
        transaction("b", date(2026, 2, 5), "10"),
        transaction("c", date(2026, 3, 5), "15"),
        transaction("d", date(2026, 4, 5), "15"),
    ]
    result = detect_leakage(rows, [], as_of=date(2026, 4, 30))
    kinds = {item["kind"] for item in result["items"]}
    assert result["status"] == "ready"
    assert "price_increase" in kinds
    assert "concentration" in kinds
    price = next(item for item in result["items"] if item["kind"] == "price_increase")
    assert price["evidence"]["transaction_ids"] == ["a", "b", "c", "d"]


def test_leakage_marks_overdue_confirmed_rule_as_dormant():
    rule = SimpleNamespace(
        id="rule-1", description="Old service", category="Subscriptions", confirmed=True,
        status="active", cadence="monthly", next_expected=date(2026, 1, 1),
        evidence_transaction_ids='["old-tx"]', minimum_amount=Decimal("9"), maximum_amount=Decimal("11"),
    )
    result = detect_leakage([], [rule], as_of=date(2026, 4, 30))
    assert result["status"] == "insufficient_data"
    assert any(item["kind"] == "dormant_recurring" for item in result["items"])

    result = detect_leakage(
        [transaction("old-tx", date(2025, 12, 1), "10")], [rule], as_of=date(2026, 4, 30)
    )
    assert any(item["kind"] == "dormant_recurring" for item in result["items"])
