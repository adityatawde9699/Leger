from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.scenarios import calculate_scenario


def tx(day, tx_type, amount, category="Dining"):
    return SimpleNamespace(date=date.fromisoformat(day), type=tx_type, amount=Decimal(amount), category=category)


def test_scenario_excludes_transfers_and_applies_category_reduction():
    result = calculate_scenario(
        [
            tx("2026-01-05", "income", "60000", "Salary"),
            tx("2026-01-10", "expense", "10000", "Dining"),
            tx("2026-01-11", "refund", "1000", "Dining"),
            tx("2026-01-12", "transfer", "5000", "Transfers"),
        ],
        category="Dining",
        reduction_pct=Decimal("20"),
    )

    assert result["baseline_monthly_income"] == Decimal("60000.00")
    assert result["baseline_monthly_expenses"] == Decimal("9000.00")
    assert result["category_monthly_spend"] == Decimal("9000.00")
    assert result["monthly_savings"] == Decimal("1800.00")
    assert result["projected_monthly_net"] == Decimal("52800.00")
