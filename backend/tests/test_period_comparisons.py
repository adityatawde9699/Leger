from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.insights import compare_calendar_periods


def tx(day, tx_type, amount, category="Dining", tx_id=None):
    return SimpleNamespace(
        id=tx_id or f"tx-{day}-{tx_type}",
        date=date.fromisoformat(day),
        type=tx_type,
        amount=Decimal(amount),
        category=category,
        status="posted",
    )


def test_calendar_comparisons_include_periods_deltas_and_evidence():
    rows = [
        tx("2025-09-10", "expense", "80", tx_id="old-year"),
        tx("2026-08-10", "expense", "100", tx_id="prior-month"),
        tx("2026-09-10", "expense", "150", tx_id="current-month"),
    ]

    mom = compare_calendar_periods(rows, comparison="mom", end_date=date(2026, 9, 30))
    yoy = compare_calendar_periods(rows, comparison="yoy", end_date=date(2026, 9, 30))

    assert mom["status"] == "ready"
    assert mom["current"]["expenses"] == Decimal("150")
    assert mom["previous"]["expenses"] == Decimal("100")
    assert mom["changes"]["expenses"] == Decimal("50")
    assert "current-month" in mom["category_changes"][0]["transaction_ids"]
    assert yoy["status"] == "ready"
    assert yoy["previous"]["expenses"] == Decimal("80")


def test_calendar_comparison_is_insufficient_without_both_periods():
    result = compare_calendar_periods(
        [tx("2026-09-10", "expense", "100")],
        comparison="mom",
        end_date=date(2026, 9, 30),
    )

    assert result["status"] == "insufficient_data"
    assert result["data_quality"]["warnings"]
