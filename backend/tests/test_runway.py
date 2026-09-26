from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.services.runway import calculate_runway

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


def account(balance="1000"):
    return SimpleNamespace(
        id="cash-1", name="Checking", account_type="current", is_active=True,
        balance=Decimal(balance), last_reconciled_at=datetime(2026, 9, 25, tzinfo=UTC),
    )


def tx(identifier, day, kind, amount, category="Food"):
    return SimpleNamespace(
        id=identifier, date=day, type=kind, status="posted", amount=Decimal(amount),
        category=category, description=identifier, merchant_normalized=None,
    )


def test_runway_uses_reconciled_cash_and_confirmed_obligations():
    result = calculate_runway(
        accounts=[account()],
        transactions=[
            tx("income-jul", date(2026, 7, 1), "income", "2000", "Salary"),
            tx("expense-jul", date(2026, 7, 5), "expense", "700"),
            tx("income-aug", date(2026, 8, 1), "income", "2000", "Salary"),
            tx("expense-aug", date(2026, 8, 5), "expense", "700"),
            tx("expense-sep", date(2026, 9, 5), "expense", "700"),
        ],
        recurring_rules=[SimpleNamespace(
            id="rule-1", confirmed=True, status="active", cadence="monthly",
            average_amount=Decimal("300"),
        )],
        currency="USD", income_pattern="regular", as_of=date(2026, 9, 26), now=NOW,
    )
    assert result["status"] == "ready"
    assert result["starting_cash"] == Decimal("1000")
    assert result["fixed_monthly_obligations"] == Decimal("300")
    assert result["flexible_monthly_spend"] == Decimal("400")
    assert result["income_assumption"]["low"] == Decimal("2000")
    assert result["projection"][0]["balance_low"] == Decimal("2300")


def test_irregular_runway_does_not_promote_one_income_row_to_a_promise():
    result = calculate_runway(
        accounts=[account("500")],
        transactions=[
            tx("income-sep", date(2026, 9, 1), "income", "1500", "Freelance"),
            tx("expense-sep", date(2026, 9, 5), "expense", "400"),
        ],
        recurring_rules=[], currency="USD", income_pattern="irregular",
        as_of=date(2026, 9, 26), now=NOW,
    )
    assert result["status"] == "ready"
    assert result["income_assumption"]["low"] == Decimal("0")
    assert result["income_assumption"]["high"] == Decimal("1500")
    assert any("another month" in warning for warning in result["data_quality"]["warnings"])
