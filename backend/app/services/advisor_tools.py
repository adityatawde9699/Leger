"""Deterministic fact tools available to the advisor.

These functions are intentionally boring: they calculate facts in Python and
return compact, evidence-bearing objects. The language model may explain the
results, but it never performs the financial arithmetic.
"""

import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from ..models import Budget, Transaction
from .currency import format_amount
from .insights import compare_periods, data_quality, monthly_summary, recurring_payments
from .scenarios import calculate_scenario


def get_summary(transactions: list[Transaction], currency: str = "INR") -> dict[str, Any]:
    summary = monthly_summary(transactions)
    return {
        "tool": "get_summary",
        "status": "ready" if transactions else "insufficient_data",
        "currency": currency,
        "period": {"start": summary.get("period_start"), "end": summary.get("period_end")},
        "income": str(summary["income"]),
        "expenses": str(summary["expenses"]),
        "net": str(summary["net"]),
        "category_totals": {name: str(value) for name, value in summary["by_category"].items()},
        "evidence_transaction_ids": [tx.id for tx in transactions if getattr(tx, "id", None)][:100],
        "data_quality": data_quality(transactions),
    }


def compare_periods_tool(transactions: list[Transaction], days: int = 30) -> dict[str, Any]:
    result = compare_periods(transactions, days=days)
    return {"tool": "compare_periods", **result}


def list_evidence(
    transactions: list[Transaction],
    transaction_ids: list[str] | None = None,
    currency: str = "INR",
) -> dict[str, Any]:
    wanted = {str(value) for value in (transaction_ids or [])}
    rows = [
        {
            "transaction_id": tx.id,
            "date": tx.date.isoformat(),
            "type": tx.type,
            "category": tx.category,
            "amount": str(tx.amount),
            "currency": currency,
            "description": (tx.merchant_normalized or tx.description)[:80],
        }
        for tx in transactions
        if not wanted or str(tx.id) in wanted
    ]
    return {"tool": "list_evidence", "status": "ready" if rows else "insufficient_data", "rows": rows[:100]}


def get_recurring(transactions: list[Transaction], currency: str = "INR") -> dict[str, Any]:
    rows = recurring_payments(transactions)
    return {
        "tool": "get_recurring",
        "status": "ready" if rows else "insufficient_data",
        "currency": currency,
        "items": [
            {
                **item,
                "average_amount": format_amount(item["average_amount"], currency),
            }
            for item in rows[:20]
        ],
    }


def open_transactions(transactions: list[Transaction], category: str | None = None) -> dict[str, Any]:
    rows = [tx for tx in transactions if category is None or tx.category.casefold() == category.casefold()]
    return {
        "tool": "open_transactions",
        "status": "ready" if rows else "insufficient_data",
        "category": category,
        "transaction_ids": [tx.id for tx in rows[:100]],
    }


TOOL_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "get_summary": get_summary,
    "compare_periods": compare_periods_tool,
    "list_evidence": list_evidence,
    "get_recurring": get_recurring,
    "open_transactions": open_transactions,
}

TOOL_SELECTION_SYSTEM = """Choose at most one Ledger fact tool for the user's question.
Return ONLY JSON in this shape: {"tool":"name","arguments":{}}.
Allowed tools: get_summary, compare_periods, list_evidence, get_recurring, open_transactions, get_budgets, simulate_goal.
Use no other tool, never include financial calculations, and use empty arguments unless the question clearly supplies a category, transaction IDs, comparison days, or scenario assumptions."""


def get_budgets(budgets: list[Budget], currency: str = "INR") -> dict[str, Any]:
    return {
        "tool": "get_budgets",
        "status": "ready" if budgets else "insufficient_data",
        "currency": currency,
        "items": [{"category": b.category, "monthly_limit": str(b.monthly_limit)} for b in budgets],
    }


def simulate_goal_tool(
    transactions: list[Transaction],
    currency: str = "INR",
    *,
    category: str | None = None,
    reduction_pct: Decimal = Decimal("0"),
    income_change_pct: Decimal = Decimal("0"),
    one_time_expense: Decimal = Decimal("0"),
    horizon_months: int = 1,
) -> dict[str, Any]:
    result = calculate_scenario(
        transactions,
        category=category,
        reduction_pct=reduction_pct,
        income_change_pct=income_change_pct,
        one_time_expense=one_time_expense,
        horizon_months=horizon_months,
    )
    return {
        "tool": "simulate_goal",
        "status": "ready" if transactions else "insufficient_data",
        "currency": currency,
        "assumptions": [
            "Projection uses the average observed month in the available history.",
            "This is a what-if estimate, not a promise of future income or spending.",
        ],
        "evidence_transaction_ids": [tx.id for tx in transactions if getattr(tx, "id", None)][:100],
        **{key: str(value) if isinstance(value, Decimal) else value for key, value in result.items()},
    }


TOOL_REGISTRY["get_budgets"] = get_budgets
TOOL_REGISTRY["simulate_goal"] = simulate_goal_tool


def parse_tool_request(raw: str) -> dict[str, Any] | None:
    """Parse and validate a model tool request without trusting its arguments."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        request = json.loads(cleaned)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(request, dict) or request.get("tool") not in TOOL_REGISTRY:
        return None
    arguments = request.get("arguments", {})
    return {"tool": request["tool"], "arguments": arguments if isinstance(arguments, dict) else {}}


def execute_tool_request(
    request: dict[str, Any],
    transactions: list[Transaction],
    budgets: list[Budget],
    currency: str = "INR",
) -> dict[str, Any] | None:
    """Execute only allowlisted, bounded arguments against current user data."""
    name = request.get("tool")
    args = request.get("arguments") or {}
    if name == "get_summary":
        return get_summary(transactions, currency)
    if name == "compare_periods":
        days = args.get("days", 30)
        if not isinstance(days, int) or isinstance(days, bool) or not 7 <= days <= 365:
            days = 30
        return compare_periods_tool(transactions, days)
    if name == "list_evidence":
        ids = args.get("transaction_ids", [])
        ids = ids if isinstance(ids, list) and all(isinstance(value, str) for value in ids) else []
        valid_ids = {tx.id for tx in transactions}
        return list_evidence(transactions, [value for value in ids[:100] if value in valid_ids], currency)
    if name == "get_recurring":
        return get_recurring(transactions, currency)
    if name == "open_transactions":
        category = args.get("category")
        return open_transactions(transactions, category[:64] if isinstance(category, str) else None)
    if name == "get_budgets":
        return get_budgets(budgets, currency)
    if name == "simulate_goal":
        category = args.get("category")
        category = category[:64] if isinstance(category, str) and category.strip() else None
        def bounded_decimal(key: str, low: str, high: str) -> Decimal:
            try:
                value = Decimal(str(args.get(key, "0")))
            except Exception:
                return Decimal("0")
            return min(max(value, Decimal(low)), Decimal(high))

        horizon = args.get("horizon_months", 1)
        if not isinstance(horizon, int) or isinstance(horizon, bool):
            horizon = 1
        horizon = min(max(horizon, 1), 12)
        return simulate_goal_tool(
            transactions,
            currency,
            category=category,
            reduction_pct=bounded_decimal("reduction_pct", "0", "100"),
            income_change_pct=bounded_decimal("income_change_pct", "-100", "100"),
            one_time_expense=bounded_decimal("one_time_expense", "0", "1000000000"),
            horizon_months=horizon,
        )
    return None


def select_advisor_tools(
    question: str,
    transactions: list[Transaction],
    budgets: list[Budget],
    currency: str = "INR",
) -> list[dict[str, Any]]:
    """Resolve a conservative set of fact tools for the current question."""
    text = question.casefold()
    results = [get_summary(transactions, currency)]
    if any(term in text for term in ("compare", "versus", "trend", "increased", "decreased", "change")):
        results.append(compare_periods_tool(transactions))
    if any(term in text for term in ("subscription", "recurring", "bill", "renewal")):
        results.append(get_recurring(transactions, currency))
    if any(term in text for term in ("transaction", "evidence", "rows", "purchase")):
        results.append(list_evidence(transactions, currency=currency))
    if any(term in text for term in ("budget", "limit", "allowance")):
        results.append(get_budgets(budgets, currency))
    return results
