from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ..models import Budget, Transaction
from .categorizer import EXPENSE_CATEGORIES


SYSTEM_PROMPT = """You are Ledger AI, a sharp and practical personal finance advisor for Indian users.
You give concise, actionable advice grounded strictly in the user's real financial data.
Use plain English. Be direct but encouraging. Keep responses under 200 words.
Always ground your advice in the specific numbers provided. Format with short paragraphs."""


def monthly_summary(transactions: list[Transaction]) -> dict:
    income = sum((t.amount for t in transactions if t.type == "income"), Decimal("0"))
    expenses = sum((t.amount for t in transactions if t.type == "expense"), Decimal("0"))
    by_category: dict[str, Decimal] = defaultdict(Decimal)
    by_day: dict[str, dict] = defaultdict(lambda: {"income": Decimal("0"), "expenses": Decimal("0")})

    for tx in transactions:
        day = str(tx.date)
        if tx.type == "expense":
            by_category[tx.category] += tx.amount
            by_day[day]["expenses"] += tx.amount
        else:
            by_day[day]["income"] += tx.amount

    return {
        "income": income,
        "expenses": expenses,
        "net": income - expenses,
        "by_category": dict(by_category),
        "by_day": dict(by_day),
    }


def dynamic_budget_suggestions(transactions: list[Transaction]) -> list[dict]:
    """Suggest budgets based on 3-month spending average at 90% cap."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for tx in transactions:
        totals[tx.category] += tx.amount
    return [
        {
            "category": cat,
            "monthly_limit": round((totals[cat] / Decimal("3")) * Decimal("0.9"), 2),
            "strategy": "dynamic_3mo_90",
        }
        for cat in EXPENSE_CATEGORIES
        if totals[cat] > 0
    ]


def compute_insights(transactions: list[Transaction], budgets: list[Budget]) -> list[str]:
    summary = monthly_summary(transactions)
    insights: list[str] = []
    budget_map = {b.category: b.monthly_limit for b in budgets}

    for category, spent in summary["by_category"].items():
        budget = budget_map.get(category)
        if not budget:
            continue
        ratio = spent / budget if budget else Decimal("0")
        if ratio >= Decimal("1"):
            insights.append(f"{category} is over budget: spent ₹{spent} vs ₹{budget} limit.")
        elif ratio >= Decimal("0.8"):
            insights.append(f"{category} at {int(ratio * 100)}% of budget: ₹{spent} of ₹{budget}.")

    recent = [
        t for t in transactions
        if t.type == "expense" and t.date >= date.today() - timedelta(days=7)
    ]
    merchant_totals: dict[str, Decimal] = defaultdict(Decimal)
    for tx in recent:
        merchant_totals[tx.description] += tx.amount
    if merchant_totals:
        merchant, amount = max(merchant_totals.items(), key=lambda x: x[1])
        insights.append(f"Top weekly merchant: {merchant} at ₹{amount}.")

    return insights


def recurring_payments(transactions: list[Transaction]) -> list[dict]:
    grouped: dict[tuple, list] = defaultdict(list)
    for tx in transactions:
        if tx.type == "expense":
            grouped[(tx.description.lower(), tx.category)].append(tx)
    recurring = []
    for (description, category), items in grouped.items():
        if len(items) >= 2:
            amounts = [item.amount for item in items]
            avg = sum(amounts, Decimal("0")) / len(amounts)
            recurring.append({
                "description": description.title(),
                "category": category,
                "average_amount": avg,
                "count": len(items),
            })
    return sorted(recurring, key=lambda x: x["average_amount"], reverse=True)


def build_advisor_context(
    transactions: list[Transaction],
    budgets: list[Budget],
) -> str:
    """
    Builds a compact, token-efficient financial context string (~300 tokens).
    Never sends raw transaction lists to the LLM.
    """
    summary = monthly_summary(transactions)
    budget_map = {b.category: b.monthly_limit for b in budgets}
    recurring = recurring_payments(transactions)

    # Budget status lines
    budget_lines = []
    for cat, spent in sorted(summary["by_category"].items(), key=lambda x: x[1], reverse=True)[:8]:
        limit = budget_map.get(cat)
        if limit:
            pct = int((spent / limit) * 100)
            budget_lines.append(f"  {cat}: ₹{spent} / ₹{limit} ({pct}%)")
        else:
            budget_lines.append(f"  {cat}: ₹{spent} (no budget set)")

    recurring_lines = [
        f"  {r['description']}: ~₹{r['average_amount']:.0f}/mo ({r['count']}x)"
        for r in recurring[:4]
    ]

    context = f"""[Financial Snapshot — {date.today().strftime('%B %Y')}]
Income: ₹{summary['income']} | Expenses: ₹{summary['expenses']} | Net: ₹{summary['net']}

Top Spending by Category:
{chr(10).join(budget_lines) or '  No expense data yet.'}

Detected Recurring Payments:
{chr(10).join(recurring_lines) or '  None detected.'}

Total transactions analyzed: {len(transactions)}"""

    return context
