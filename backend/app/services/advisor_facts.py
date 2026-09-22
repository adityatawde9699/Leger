from collections import defaultdict
from decimal import Decimal

from ..models import Budget, Transaction
from .insights import _expense_value, _is_posted, compare_periods


def _money(value: Decimal) -> str:
    return f"₹{value:,.2f}"


def _evidence(tx: Transaction) -> dict:
    return {
        "transaction_id": tx.id,
        "date": tx.date.isoformat(),
        "description": tx.merchant_normalized or tx.description,
        "amount": str(tx.amount),
        "type": tx.type,
        "category": tx.category,
    }


def _result(answer: str, facts: list[dict], evidence: list[dict], assumptions: list[str] | None = None) -> dict:
    return {
        "answer": answer,
        "answer_type": "deterministic",
        "facts": facts,
        "evidence": evidence[:20],
        "assumptions": assumptions or [],
    }


def deterministic_answer(
    question: str,
    transactions: list[Transaction],
    budgets: list[Budget],
) -> dict | None:
    """Answer direct factual questions without asking an LLM to do arithmetic."""
    text = question.casefold()
    if not transactions:
        if any(word in text for word in ("spend", "expense", "income", "save", "transaction", "budget")):
            return _result(
                "I don't have enough transaction data to calculate that yet. Add or import some transactions first.",
                [],
                [],
                ["No transactions are currently available."],
            )
        return None

    ordered = sorted(transactions, key=lambda tx: (tx.date, getattr(tx, "created_at", None) or 0), reverse=True)
    expense_rows = [tx for tx in transactions if tx.type in ("expense", "refund", "reimbursement") and _is_posted(tx)]
    expense_total = sum((_expense_value(tx) for tx in transactions), Decimal("0"))
    income_total = sum((tx.amount for tx in transactions if tx.type == "income" and _is_posted(tx)), Decimal("0"))
    category_totals: dict[str, Decimal] = defaultdict(Decimal)
    category_rows: dict[str, list[Transaction]] = defaultdict(list)
    for tx in expense_rows:
        value = _expense_value(tx)
        if value:
            category_totals[tx.category] += value
            category_rows[tx.category].append(tx)

    if any(term in text for term in ("compared", "versus", " vs ", "trend", "increased", "decreased")):
        comparison = compare_periods(transactions, days=30)
        if comparison["status"] != "ready":
            return _result(
                "I don't have transactions in both 30-day windows yet, so I won't claim a trend. Add or import more history first.",
                [],
                [],
                comparison["data_quality"]["warnings"],
            )
        change = comparison["changes"]["expenses"]
        percent = comparison["changes"]["expenses_percent"]
        direction = "increased" if change > 0 else ("decreased" if change < 0 else "was unchanged")
        percent_text = f" ({abs(percent)}%)" if percent is not None else ""
        evidence_ids = set(comparison["current"]["expense_transaction_ids"] + comparison["previous"]["expense_transaction_ids"])
        evidence = [_evidence(tx) for tx in transactions if tx.id in evidence_ids]
        return _result(
            f"Spending {direction} by {_money(abs(change))}{percent_text} in the latest 30 days compared with the previous 30 days.",
            [
                {"label": "Current-period spending", "value": str(comparison["current"]["expenses"])},
                {"label": "Previous-period spending", "value": str(comparison["previous"]["expenses"])},
                {"label": "Change", "value": str(change), "percent_change": str(percent) if percent is not None else None},
            ],
            evidence,
            ["Equal-length 30-day windows; refunds offset spending and transfers are excluded."],
        )

    if any(term in text for term in ("latest transaction", "last transaction", "most recent transaction")):
        tx = ordered[0]
        return _result(
            f"Your latest transaction was {_money(tx.amount)} {tx.type} on {tx.date.isoformat()} for {tx.description} ({tx.category}).",
            [{"label": "Latest transaction", "value": str(tx.amount), "transaction_id": tx.id}],
            [_evidence(tx)],
        )

    if any(term in text for term in ("overspending", "spent most", "spending most", "biggest expense", "largest expense")):
        if not category_totals:
            return _result("I couldn't find any expense transactions to compare.", [], [])
        category, amount = max(category_totals.items(), key=lambda item: item[1])
        rows = category_rows[category]
        return _result(
            f"{category} is your largest spending category at {_money(amount)} across {len(rows)} transaction(s).",
            [{"label": category, "value": str(amount), "transaction_count": len(rows)}],
            [_evidence(tx) for tx in rows],
            ["Refunds offset spending; transfers are excluded."] if any(tx.type == "refund" for tx in rows) else ["Transfers are excluded from spending."]
        )

    requested_category = next(
        (category for category in category_totals if category.casefold() in text),
        None,
    )
    if requested_category and any(term in text for term in ("spend", "spent", "expense", "cost")):
        amount = category_totals[requested_category]
        rows = category_rows[requested_category]
        return _result(
            f"You spent {_money(amount)} in {requested_category} across {len(rows)} transaction(s) in the available history.",
            [{"label": requested_category, "value": str(amount), "transaction_count": len(rows)}],
            [_evidence(tx) for tx in rows],
            ["This uses all available history, not a monthly average.", "Refunds offset spending; transfers are excluded."]
        )

    if any(term in text for term in ("savings rate", "how much did i save", "how much have i saved", "net savings")):
        net = income_total - expense_total
        rate = (net / income_total * 100) if income_total else None
        rate_text = f" ({rate:.1f}% savings rate)" if rate is not None else " (income data is unavailable)"
        return _result(
            f"Your net savings are {_money(net)}{rate_text} across the available history.",
            [{"label": "Income", "value": str(income_total)}, {"label": "Expenses", "value": str(expense_total)}, {"label": "Net", "value": str(net)}],
            [_evidence(tx) for tx in transactions if tx.type in ("income", "expense", "refund", "reimbursement") and _is_posted(tx)],
            ["Transfers are excluded from income and expenses."]
        )

    if any(term in text for term in ("income", "earned", "salary")) and any(term in text for term in ("how much", "total", "what is", "show")):
        rows = [tx for tx in transactions if tx.type == "income" and _is_posted(tx)]
        return _result(
            f"Recorded income is {_money(income_total)} across {len(rows)} transaction(s).",
            [{"label": "Income", "value": str(income_total), "transaction_count": len(rows)}],
            [_evidence(tx) for tx in rows],
        )

    if any(term in text for term in ("expense total", "total expenses", "how much did i spend", "total spending")):
        return _result(
            f"Recorded spending is {_money(expense_total)} across the available history.",
            [{"label": "Expenses", "value": str(expense_total), "transaction_count": len(expense_rows)}],
            [_evidence(tx) for tx in expense_rows],
            ["Refunds offset spending; transfers are excluded."]
        )

    if "budget" in text and budgets:
        rows = []
        facts = []
        for budget in budgets:
            spent = category_totals.get(budget.category, Decimal("0"))
            remaining = budget.monthly_limit - spent
            rows.append((budget.category, remaining))
            facts.append({"label": budget.category, "budget": str(budget.monthly_limit), "spent": str(spent), "remaining": str(remaining)})
        rows.sort(key=lambda item: item[1])
        category, remaining = rows[0]
        status = "over" if remaining < 0 else "remaining"
        return _result(
            f"{category} is the closest to its limit: {_money(abs(remaining))} {status}.",
            facts,
            [_evidence(tx) for tx in category_rows.get(category, [])],
            ["Budget comparison uses all available transaction history; confirm the period if you need a monthly view."]
        )

    return None
