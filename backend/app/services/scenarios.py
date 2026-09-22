from decimal import ROUND_HALF_UP, Decimal

from .insights import _expense_value, data_quality

MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def calculate_scenario(
    transactions: list,
    *,
    category: str | None = None,
    reduction_pct: Decimal = Decimal("0"),
    income_change_pct: Decimal = Decimal("0"),
    one_time_expense: Decimal = Decimal("0"),
    horizon_months: int = 1,
) -> dict:
    """Calculate a transparent monthly what-if from observed transaction history."""
    dates = [tx.date for tx in transactions]
    months = {tx.date.strftime("%Y-%m") for tx in transactions}
    divisor = Decimal(max(len(months), 1))

    income = sum((tx.amount for tx in transactions if tx.type == "income"), Decimal("0"))
    expenses = sum((_expense_value(tx) for tx in transactions), Decimal("0"))
    category_spend = sum(
        (_expense_value(tx) for tx in transactions if category and tx.category == category),
        Decimal("0"),
    )
    baseline_income = income / divisor
    baseline_expenses = expenses / divisor
    category_monthly_spend = category_spend / divisor
    monthly_savings = category_monthly_spend * (reduction_pct / Decimal("100"))
    projected_income = baseline_income * (Decimal("1") + income_change_pct / Decimal("100"))
    projected_expenses = max(Decimal("0"), baseline_expenses - monthly_savings)
    baseline_net = baseline_income - baseline_expenses
    projected_net = projected_income - projected_expenses

    return {
        "category": category,
        "reduction_pct": reduction_pct,
        "income_change_pct": income_change_pct,
        "one_time_expense": one_time_expense,
        "horizon_months": horizon_months,
        "period_start": min(dates) if dates else None,
        "period_end": max(dates) if dates else None,
        "months_observed": len(months),
        "transaction_count": len(transactions),
        "baseline_monthly_income": _money(baseline_income),
        "baseline_monthly_expenses": _money(baseline_expenses),
        "baseline_monthly_net": _money(baseline_net),
        "category_monthly_spend": _money(category_monthly_spend),
        "monthly_savings": _money(monthly_savings),
        "projected_monthly_income": _money(projected_income),
        "projected_monthly_expenses": _money(projected_expenses),
        "projected_monthly_net": _money(projected_net),
        "first_month_net_after_one_time": _money(projected_net - one_time_expense),
        "horizon_net_change": _money((projected_net - baseline_net) * horizon_months - one_time_expense),
        "data_quality": data_quality(transactions),
    }
