"""Personal cash-flow snapshot, not a credit score or lending assessment."""

from datetime import date
from decimal import Decimal

from .insights import data_quality, monthly_summary


def compute_credit_health(
    transactions: list, accounts: list | None = None, currency: str = "INR", currency_mismatch: bool = False,
) -> dict:
    """Preserve the legacy route while returning only verifiable ledger facts.

    The ledger has no credit limits, repayment history, or bureau data. Balances
    and spending regularity cannot be turned into a meaningful 300–900 score.
    """
    quality = data_quality(transactions)
    summary = monthly_summary(transactions)
    income = summary["income"]
    expenses = summary["expenses"]
    savings_rate = (
        round((income - expenses) / income * Decimal("100"), 1)
        if income > 0 else None
    )
    status = "ready" if quality["transaction_count"] and income > 0 else "insufficient_data"
    missing = []
    if not quality["transaction_count"]:
        missing.append("Add or import transactions to see your cash-flow picture.")
    elif income <= 0:
        missing.append("Add income transactions to calculate a savings rate.")
    if quality["months_covered"] < 3 and quality["transaction_count"]:
        missing.append("Add more history before relying on a longer-term trend.")
    if currency_mismatch:
        missing.insert(0, "Account currencies differ from your Ledger currency. Resolve this before combining cash-flow amounts.")
    credit_accounts = [account for account in (accounts or []) if account.account_type == "credit"]
    readiness_warnings: list[str] = []
    readiness_accounts: list[dict] = []
    for account in credit_accounts:
        limit = account.credit_limit
        owed = max(Decimal("0"), Decimal(str(account.balance or 0)))
        utilization = None
        if limit and limit > 0:
            utilization = (owed / limit * Decimal("100")).quantize(Decimal("0.1"))
        else:
            readiness_warnings.append(f"Add the credit limit for {account.name} before interpreting utilization.")
        if account.minimum_payment is None:
            readiness_warnings.append(f"Add the minimum payment for {account.name} before assessing payment readiness.")
        if account.payment_due_date is None:
            readiness_warnings.append(f"Add the next payment due date for {account.name} before assessing payment readiness.")
        elif account.payment_due_date < date.today() and owed > 0:
            readiness_warnings.append(f"The recorded payment due date for {account.name} has passed; verify the account.")
        readiness_accounts.append({
            "account_id": account.id,
            "name": account.name,
            "balance_owed": owed,
            "credit_limit": limit,
            "utilization_pct": utilization,
            "minimum_payment": account.minimum_payment,
            "payment_due_date": account.payment_due_date,
        })
    if credit_accounts and not readiness_warnings:
        readiness_status = "ready"
        readiness_reason = "Calculated from user-entered credit limit, amount owed, minimum payment, and due date."
    elif credit_accounts:
        readiness_status = "incomplete"
        readiness_reason = "Add the missing credit-account fields before relying on readiness details."
    else:
        readiness_status = "unavailable"
        readiness_reason = "Add a credit account with its limit and payment details for a factual readiness view."
    return {
        "status": "currency_mismatch" if currency_mismatch else status,
        "currency": currency,
        "period_start": quality["period_start"],
        "period_end": quality["period_end"],
        "transaction_count": quality["transaction_count"],
        "income": None if currency_mismatch else income,
        "expenses": None if currency_mismatch else expenses,
        "net": None if currency_mismatch else summary["net"],
        "savings_rate_pct": None if currency_mismatch else savings_rate,
        "warnings": missing + quality["warnings"],
        "credit_assessment": "recorded_obligations" if credit_accounts else "unavailable",
        "credit_reason": "Ledger reports recorded credit-account obligations only; it does not calculate a credit score or bureau assessment.",
        "credit_readiness": {
            "status": readiness_status,
            "reason": readiness_reason,
            "accounts": readiness_accounts,
            "warnings": readiness_warnings,
        },
    }
