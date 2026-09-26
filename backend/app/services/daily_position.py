"""Conservative, evidence-backed daily money position.

This is not a bank balance. A discretionary estimate is withheld until the
user has reviewed obligations and every cash balance is freshly reconciled.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from .insights import _expense_value

CASH_ACCOUNT_TYPES = {"savings", "current", "wallet", "cash"}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _month_end(day: date) -> date:
    next_month = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def _next_date(day: date, cadence: str) -> date | None:
    if cadence == "weekly":
        return day + timedelta(days=7)
    if cadence == "biweekly":
        return day + timedelta(days=14)
    if cadence in ("monthly", "quarterly"):
        months = 1 if cadence == "monthly" else 3
        month_index = day.year * 12 + day.month - 1 + months
        year, month_zero = divmod(month_index, 12)
        month = month_zero + 1
        last_day = _month_end(date(year, month, 1)).day
        return date(year, month, min(day.day, last_day))
    return None


def calculate_daily_position(
    *,
    accounts: list,
    transactions: list,
    budgets: list,
    recurring_rules: list,
    currency: str,
    income_pattern: str | None,
    obligations_reviewed_at: datetime | None,
    pending_imports: int = 0,
    currency_mismatch: bool = False,
    as_of: date | None = None,
    now: datetime | None = None,
) -> dict:
    """Calculate current-month cash flow and reserve only when inputs are trustworthy."""
    now = _aware(now) or datetime.now(UTC)
    as_of = as_of or now.date()
    start = as_of.replace(day=1)
    end = _month_end(as_of)
    posted = [tx for tx in transactions if getattr(tx, "status", "posted") == "posted" and start <= tx.date <= as_of]
    income = sum((tx.amount for tx in posted if tx.type == "income"), Decimal("0"))
    spend_by_category: dict[str, Decimal] = defaultdict(Decimal)
    for tx in posted:
        spend_by_category[tx.category] += _expense_value(tx)
    active_rules = [rule for rule in recurring_rules if rule.status == "active" and rule.confirmed]
    committed_categories = {rule.category for rule in active_rules}
    committed_spend = sum((amount for category, amount in spend_by_category.items() if category in committed_categories), Decimal("0"))
    flexible_spend = sum((amount for category, amount in spend_by_category.items() if category not in committed_categories), Decimal("0"))

    reasons: list[str] = []
    if currency_mismatch:
        reasons.append("Account currencies differ from the ledger currency; resolve this before combining money.")
    if pending_imports:
        reasons.append("Finish or cancel pending statement imports before trusting this estimate.")
    if any(getattr(tx, "status", "posted") == "pending" for tx in transactions):
        reasons.append("Review pending transactions before relying on committed spending.")
    if any(tx.account_id is None and tx.source != "cash" for tx in transactions):
        reasons.append("Assign non-cash transactions to their accounts.")
    if not budgets:
        reasons.append("Set budgets for the spending you expect before showing discretionary money.")

    cash_accounts = [account for account in accounts if account.is_active and account.account_type in CASH_ACCOUNT_TYPES]
    if not cash_accounts:
        reasons.append("Add and reconcile a cash, wallet, checking, or savings account.")
    for account in cash_accounts:
        reconciled_at = _aware(account.last_reconciled_at)
        if not reconciled_at or reconciled_at < now - timedelta(days=7):
            reasons.append(f"Reconcile {account.name}; its balance is not a fresh observed snapshot.")
            continue
        newest = max((_aware(tx.created_at) for tx in transactions if tx.account_id == account.id), default=None)
        if newest and newest > reconciled_at:
            reasons.append(f"Reconcile {account.name} after its latest transaction.")
    if any(account.is_active and account.account_type == "credit" for account in accounts):
        reasons.append("Credit-card amounts due are not yet verified; review them before using a discretionary estimate.")

    reviewed_at = _aware(obligations_reviewed_at)
    if not reviewed_at or reviewed_at < now - timedelta(days=7):
        reasons.append("Confirm that this month's bills and budgets include your expected obligations.")
    else:
        changed_at = max(
            (_aware(item.updated_at) for item in [*budgets, *recurring_rules] if item.updated_at),
            default=None,
        )
        if changed_at and changed_at > reviewed_at:
            reasons.append("Review obligations again after changing a budget or recurring payment.")

    upcoming: list[dict] = []
    upcoming_by_category: dict[str, Decimal] = defaultdict(Decimal)
    for rule in active_rules:
        if not rule.next_expected or rule.next_expected < as_of:
            reasons.append(f"Update the next expected date for {rule.description} before estimating available money.")
            continue
        due = rule.next_expected
        for _ in range(6):
            if due > end:
                break
            amount = Decimal(str(rule.maximum_amount))
            upcoming.append({"description": rule.description, "category": rule.category, "due_date": due, "amount": amount})
            upcoming_by_category[rule.category] += amount
            next_due = _next_date(due, rule.cadence)
            if next_due is None:
                reasons.append(f"Set a predictable cadence for {rule.description} before estimating available money.")
                break
            due = next_due
    upcoming.sort(key=lambda item: (item["due_date"], item["description"]))

    # A budget may already cover a bill in the same category. Reserve the larger
    # of the two, not both. Unbudgeted confirmed bills are reserved separately.
    remaining_budget: dict[str, Decimal] = {}
    for budget in budgets:
        remaining_budget[budget.category] = max(
            Decimal("0"), Decimal(str(budget.monthly_limit)) - spend_by_category[budget.category]
        )
    reserved = sum(
        (max(remaining_budget.get(category, Decimal("0")), upcoming_by_category.get(category, Decimal("0")))
         for category in set(remaining_budget) | set(upcoming_by_category)),
        Decimal("0"),
    )
    available_cash = sum((Decimal(str(account.balance)) for account in cash_accounts), Decimal("0"))
    if income_pattern in ("irregular", "mixed"):
        reasons.append("Variable future income is not counted; this estimate uses only cash observed now.")

    blocking_reasons = [reason for reason in reasons if not reason.startswith("Variable future income")]
    return {
        "as_of": as_of,
        "month_end": end,
        "currency": currency,
        "income": None if currency_mismatch else income,
        "committed_spend": None if currency_mismatch else committed_spend,
        "flexible_spend": None if currency_mismatch else flexible_spend,
        "cash_available": None if blocking_reasons else available_cash,
        "upcoming_obligations": [] if currency_mismatch else upcoming,
        "reserve_remaining": None if blocking_reasons else reserved,
        "safe_to_spend_estimate": None if blocking_reasons else available_cash - reserved,
        "status": "unavailable" if blocking_reasons else "ready",
        "reasons": reasons,
        "method": "Fresh reconciled cash-account snapshots minus the greater of each category's remaining budget or confirmed upcoming bills. Future income is excluded. This is an estimate, not a bank balance.",
        "obligations_reviewed_at": reviewed_at,
    }
