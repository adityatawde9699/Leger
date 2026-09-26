"""Deterministic cash-flow runway with explicit income uncertainty."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from .daily_position import CASH_ACCOUNT_TYPES
from .insights import _expense_value


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _monthly_rule_amount(rule) -> Decimal:
    amount = Decimal(str(rule.average_amount))
    return {
        "weekly": amount * Decimal("52") / Decimal("12"),
        "biweekly": amount * Decimal("26") / Decimal("12"),
        "monthly": amount,
        "quarterly": amount / Decimal("3"),
    }.get(rule.cadence, amount)


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    if not ordered:
        return Decimal("0")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def calculate_runway(
    *,
    accounts: list,
    transactions: list,
    recurring_rules: list,
    currency: str,
    income_pattern: str | None,
    as_of: date | None = None,
    now: datetime | None = None,
    horizon_months: int = 3,
) -> dict:
    """Project cash using observed balances and a bounded income assumption.

    Future income is never presented as a fact. Regular income uses the
    observed average; irregular/mixed income reports a low/typical/high range
    and uses zero as the conservative lower bound when history is thin.
    """
    now = _aware(now) or datetime.now(UTC)
    as_of = as_of or now.date()
    horizon_months = max(1, min(horizon_months, 12))
    reasons: list[str] = []

    cash_accounts = [
        account for account in accounts
        if getattr(account, "is_active", False) and account.account_type in CASH_ACCOUNT_TYPES
    ]
    fresh_accounts = [
        account for account in cash_accounts
        if _aware(getattr(account, "last_reconciled_at", None))
        and _aware(account.last_reconciled_at) >= now - timedelta(days=7)
    ]
    if not cash_accounts:
        reasons.append("Add a cash, wallet, checking, or savings account before estimating runway.")
    elif len(fresh_accounts) != len(cash_accounts):
        reasons.append("Reconcile every active cash account before relying on runway.")

    posted = [
        tx for tx in transactions
        if getattr(tx, "status", "posted") == "posted" and tx.date <= as_of
    ]
    income_by_month: dict[str, Decimal] = defaultdict(Decimal)
    expense_by_month: dict[str, Decimal] = defaultdict(Decimal)
    for tx in posted:
        month = tx.date.strftime("%Y-%m")
        if tx.type == "income":
            income_by_month[month] += tx.amount
        else:
            value = _expense_value(tx)
            if value > 0:
                expense_by_month[month] += value

    income_values = [value for _, value in sorted(income_by_month.items())]
    expense_values = [value for _, value in sorted(expense_by_month.items())]
    if not expense_values:
        reasons.append("Add posted spending history before relying on runway.")

    active_rules = [
        rule for rule in recurring_rules
        if getattr(rule, "confirmed", False) and getattr(rule, "status", "active") == "active"
    ]
    fixed_monthly = sum((_monthly_rule_amount(rule) for rule in active_rules), Decimal("0"))
    historical_monthly = sum(expense_values[-3:], Decimal("0")) / Decimal(max(len(expense_values[-3:]), 1))
    flexible_monthly = max(Decimal("0"), historical_monthly - fixed_monthly)

    income_typical = _median(income_values[-3:]) if income_values else Decimal("0")
    if income_pattern in ("irregular", "mixed"):
        income_low = Decimal("0") if len(income_values) < 3 else min(income_values[-3:])
        income_high = max(income_values[-3:], default=Decimal("0"))
        income_method = "irregular-income range from recent posted monthly income; lower bound excludes uncertain future income"
    else:
        income_low = income_typical
        income_high = income_typical
        income_method = "observed posted monthly income average"

    starting_cash = sum((Decimal(str(account.balance)) for account in fresh_accounts), Decimal("0"))
    monthly_outflow = fixed_monthly + flexible_monthly
    projection = []
    low_balance = starting_cash
    high_balance = starting_cash
    low_runway_month = None
    high_runway_month = None
    for month_number in range(1, horizon_months + 1):
        low_balance += income_low - monthly_outflow
        high_balance += income_high - monthly_outflow
        if low_runway_month is None and low_balance < 0:
            low_runway_month = month_number
        if high_runway_month is None and high_balance < 0:
            high_runway_month = month_number
        projection.append({
            "month_number": month_number,
            "income_low": income_low,
            "income_typical": income_typical,
            "income_high": income_high,
            "fixed_obligations": fixed_monthly,
            "flexible_spend": flexible_monthly,
            "balance_low": low_balance,
            "balance_high": high_balance,
        })

    if len(income_values) < 2:
        reasons.append("Add another month of posted income before treating the runway as reliable.")
    if len(expense_values) < 2:
        reasons.append("Runway uses less than two months of spending history.")
    status = "ready" if fresh_accounts and expense_values else "insufficient_data"
    return {
        "status": status,
        "as_of": as_of,
        "currency": currency,
        "starting_cash": starting_cash if fresh_accounts else None,
        "horizon_months": horizon_months,
        "fixed_monthly_obligations": fixed_monthly,
        "flexible_monthly_spend": flexible_monthly,
        "income_assumption": {
            "low": income_low,
            "typical": income_typical,
            "high": income_high,
            "method": income_method,
        },
        "projection": projection if fresh_accounts else [],
        "runway_months_low": low_runway_month,
        "runway_months_high": high_runway_month,
        "data_quality": {
            "reconciled_cash_accounts": len(fresh_accounts),
            "cash_accounts": len(cash_accounts),
            "income_months": len(income_values),
            "spending_months": len(expense_values),
            "warnings": reasons,
        },
        "method": "Fresh reconciled cash snapshots minus observed flexible spend and confirmed recurring obligations. Future income is shown as an assumption range, not a promise.",
    }
