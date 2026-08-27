from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ..models import Budget, Transaction
from .categorizer import EXPENSE_CATEGORIES

# ── Advisor System Prompt (v2 — structured reasoning, grounding, formatting) ──
SYSTEM_PROMPT = """You are Ledger AI, a precision financial advisor for Indian users.

Core rules:
- GROUND every claim in the provided transaction data — never invent figures
- FORMAT: Use ₹ symbol, **bold** key numbers, bullet points for lists
- SPECIFIC: Reference actual merchants, categories, and amounts from the data
- COMPARE: When asked about trends, compare current vs previous periods from the data
- HONEST: If data is insufficient to answer, say so clearly and briefly
- CONCISE: Max 150 words unless user asks for detail. Lead with the most important insight.

Financial expertise:
- Savings advice must cite the user's actual savings rate from context
- Budget warnings must reference specific over-budget categories with exact amounts
- Recurring payment analysis must list detected subscriptions from context
- Investment advice must be general (you don't have live market data)

Output format:
- Use ₹ not INR for currency
- Bold key figures: **₹12,450**
- Use → for comparisons: "₹8,000 → ₹12,000"
- Never use placeholders or make up transactions"""


def monthly_summary(transactions: list[Transaction]) -> dict:
    income = sum((t.amount for t in transactions if t.type == "income"), Decimal("0"))
    expenses = sum((t.amount for t in transactions if t.type == "expense"), Decimal("0"))
    by_category: dict[str, Decimal] = defaultdict(Decimal)
    by_day: dict[str, dict] = defaultdict(lambda: {"income": Decimal("0"), "expenses": Decimal("0")})
    by_month: dict[str, dict] = defaultdict(lambda: {"income": Decimal("0"), "expenses": Decimal("0")})
    dates = [tx.date for tx in transactions]

    cash_income = sum((t.amount for t in transactions if t.type == "income" and t.source == "cash"), Decimal("0"))
    cash_expenses = sum((t.amount for t in transactions if t.type == "expense" and t.source == "cash"), Decimal("0"))

    merchant_totals: dict[str, Decimal] = defaultdict(Decimal)

    for tx in transactions:
        day = str(tx.date)
        month = tx.date.strftime("%Y-%m")
        if tx.type == "expense":
            by_category[tx.category] += tx.amount
            by_day[day]["expenses"] += tx.amount
            by_month[month]["expenses"] += tx.amount
            # Track merchant totals (use normalized merchant or description)
            merchant = tx.merchant_normalized or tx.description
            merchant_totals[merchant] += tx.amount
        else:
            by_day[day]["income"] += tx.amount
            by_month[month]["income"] += tx.amount

    start_date = min(dates).isoformat() if dates else None
    end_date = max(dates).isoformat() if dates else None

    # Top merchants by spend
    top_merchants = sorted(
        [{"merchant": m, "amount": float(a)} for m, a in merchant_totals.items()],
        key=lambda x: x["amount"],
        reverse=True,
    )[:8]

    return {
        "income": income,
        "expenses": expenses,
        "net": income - expenses,
        "opening_balance": None,
        "closing_balance": None,
        "cash_income": cash_income,
        "cash_expenses": cash_expenses,
        "cash_net": cash_income - cash_expenses,
        "by_category": dict(by_category),
        "by_day": dict(by_day),
        "by_month": dict(by_month),
        "top_merchants": top_merchants,
        "period_start": start_date,
        "period_end": end_date,
        "months_covered": len({d.strftime("%Y-%m") for d in dates}),
    }


def dynamic_budget_suggestions(transactions: list[Transaction]) -> list[dict]:
    """Suggest budgets based on observed monthly spending average at 90% cap."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    months = {tx.date.strftime("%Y-%m") for tx in transactions}
    divisor = Decimal(max(len(months), 1))
    for tx in transactions:
        totals[tx.category] += tx.amount
    return [
        {
            "category": cat,
            "monthly_limit": round((totals[cat] / divisor) * Decimal("0.9"), 2),
            "strategy": f"dynamic_{len(months) or 1}mo_90",
        }
        for cat in EXPENSE_CATEGORIES
        if totals[cat] > 0
    ]


def compute_insights(transactions: list[Transaction], budgets: list[Budget]) -> list[str]:
    """Rule-based insights for dashboard display."""
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

    recent = [t for t in transactions if t.type == "expense" and t.date >= date.today() - timedelta(days=7)]
    merchant_totals: dict[str, Decimal] = defaultdict(Decimal)
    for tx in recent:
        merchant = tx.merchant_normalized or tx.description
        merchant_totals[merchant] += tx.amount
    if merchant_totals:
        merchant, amount = max(merchant_totals.items(), key=lambda x: x[1])
        insights.append(f"Top weekly merchant: {merchant[:40]} at ₹{amount}.")

    # Savings rate insight
    income = summary["income"]
    expenses = summary["expenses"]
    if income > 0:
        savings_rate = int(((income - expenses) / income) * 100)
        if savings_rate < 10:
            insights.append(f"Savings rate is only {savings_rate}% — aim for at least 20%.")
        elif savings_rate >= 30:
            insights.append(f"Excellent savings rate of {savings_rate}% this period.")

    return insights


def recurring_payments(transactions: list[Transaction]) -> list[dict]:
    """Detect recurring payments (same description + category, 2+ occurrences)."""
    grouped: dict[tuple, list] = defaultdict(list)
    for tx in transactions:
        if tx.type == "expense":
            grouped[(tx.description.lower(), tx.category)].append(tx)
    recurring = []
    for (description, category), items in grouped.items():
        if len(items) >= 2:
            amounts = [item.amount for item in items]
            avg = sum(amounts, Decimal("0")) / len(amounts)
            dates = sorted(item.date for item in items)
            # Estimate next payment date
            if len(dates) >= 2:
                avg_gap_days = (dates[-1] - dates[0]).days // (len(dates) - 1)
                next_date = dates[-1] + timedelta(days=avg_gap_days)
            else:
                next_date = None
            recurring.append(
                {
                    "description": description.title(),
                    "category": category,
                    "average_amount": avg,
                    "count": len(items),
                    "last_date": dates[-1].isoformat(),
                    "next_expected": next_date.isoformat() if next_date else None,
                }
            )
    return sorted(recurring, key=lambda x: x["average_amount"], reverse=True)


def _compute_savings_trend(summary: dict) -> str:
    """Compare most recent month savings rate vs prior months average."""
    months = sorted(summary["by_month"].items())
    if len(months) < 2:
        return ""
    recent_month = months[-1][1]
    prior_months = months[:-1]
    recent_rate = float(recent_month["income"] - recent_month["expenses"]) / max(float(recent_month["income"]), 1)
    prior_rates = [
        (float(m["income"] - m["expenses"]) / max(float(m["income"]), 1))
        for _, m in prior_months
        if float(m["income"]) > 0
    ]
    if not prior_rates:
        return ""
    avg_prior = sum(prior_rates) / len(prior_rates)
    delta = recent_rate - avg_prior
    if delta > 0.05:
        return f"Savings improving: {avg_prior * 100:.0f}% → {recent_rate * 100:.0f}%"
    elif delta < -0.05:
        return f"Savings declining: {avg_prior * 100:.0f}% → {recent_rate * 100:.0f}%"
    return f"Savings stable at ~{recent_rate * 100:.0f}%"


def build_advisor_context(
    transactions: list[Transaction],
    budgets: list[Budget],
    anomalies: list[dict] | None = None,
    forecast: dict | None = None,
) -> str:
    """Build a rich, token-efficient financial context string for the advisor."""
    summary = monthly_summary(transactions)
    budget_map = {b.category: b.monthly_limit for b in budgets}
    recurring = recurring_payments(transactions)

    # Budget vs spend lines (top 10 by spend)
    budget_lines = []
    for cat, spent in sorted(summary["by_category"].items(), key=lambda x: x[1], reverse=True)[:10]:
        limit = budget_map.get(cat)
        if limit:
            pct = int((spent / limit) * 100)
            status = " ⚠️ OVER" if pct >= 100 else (" ⚡ NEAR" if pct >= 80 else "")
            budget_lines.append(f"  {cat}: ₹{spent:.0f} / ₹{limit:.0f} ({pct}%){status}")
        else:
            budget_lines.append(f"  {cat}: ₹{spent:.0f} (no budget)")

    # Top merchants
    merchant_lines = [f"  {r['merchant'][:35]}: ₹{r['amount']:.0f}" for r in summary["top_merchants"][:5]]

    # Recurring payments
    recurring_lines = [
        f"  {r['description'][:30]}: ~₹{r['average_amount']:.0f}/mo (next ~{r['next_expected'] or 'unknown'})"
        for r in recurring[:5]
    ]

    # Latest 20 transactions (richer detail)
    latest = sorted(transactions, key=lambda tx: (tx.date, tx.created_at), reverse=True)[:20]
    latest_lines = [
        f"  {tx.date.isoformat()} {tx.date.strftime('%a')} | {tx.type} | "
        f"₹{tx.amount} | {tx.category} | {(tx.merchant_normalized or tx.description)[:60]}"
        for tx in latest
    ]

    # Monthly breakdown
    month_lines = [
        f"  {month}: income ₹{row['income']:.0f} | expenses ₹{row['expenses']:.0f} | "
        f"net ₹{float(row['income']) - float(row['expenses']):.0f}"
        for month, row in sorted(summary["by_month"].items())
    ]

    period = (
        f"{summary['period_start']} to {summary['period_end']}"
        if summary["period_start"] and summary["period_end"]
        else "No transactions"
    )

    today_str = date.today().isoformat()
    last_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    lm_stats = summary["by_month"].get(last_month, {"income": Decimal("0"), "expenses": Decimal("0")})
    savings_trend = _compute_savings_trend(summary)

    opening_bal = summary.get("opening_balance")
    closing_bal = summary.get("closing_balance")
    if closing_bal is not None:
        balance_line = f"  Opening: ₹{opening_bal if opening_bal is not None else 'N/A'} | Closing: ₹{closing_bal}"
    else:
        balance_line = f"  Net Cash Flow: ₹{summary['net']} (no bank balance data)"

    income = summary["income"]
    expenses = summary["expenses"]
    savings_rate_pct = int((float(income - expenses) / max(float(income), 1)) * 100)

    # Anomaly section
    anomaly_section = ""
    if anomalies:
        high_anomalies = [a for a in anomalies if a.get("severity") in ("high", "medium")][:3]
        if high_anomalies:
            anomaly_lines = [
                f"  ⚠️ {a['anomaly_type']}: ₹{a['amount']:.0f} ({a['category']}) — {a['message']}"
                for a in high_anomalies
            ]
            anomaly_section = "\nDetected Anomalies:\n" + "\n".join(anomaly_lines)

    # Forecast section
    forecast_section = ""
    if forecast and forecast.get("by_category"):
        breach_warnings = []
        for cat, proj in forecast["by_category"].items():
            limit = budget_map.get(cat)
            if limit and proj["projected_30d"] > float(limit):
                excess = proj["projected_30d"] - float(limit)
                breach_warnings.append(
                    f"  🔴 {cat}: projected ₹{proj['projected_30d']:.0f} vs budget ₹{float(limit):.0f} (+₹{excess:.0f})"
                )
        if breach_warnings:
            forecast_section = "\nBudget Breach Forecasts (next 30 days):\n" + "\n".join(breach_warnings[:3])

    context = f"""[Financial Snapshot — {period}]
Today: {today_str}
Period: {summary["months_covered"]} month(s) — {period}

Overall:
  Income: ₹{income:.0f} | Expenses: ₹{expenses:.0f} | Net: ₹{float(income - expenses):.0f}
  Savings Rate: {savings_rate_pct}% | {savings_trend}
Balance:
{balance_line}

Last Month ({last_month}):
  Income: ₹{lm_stats["income"]:.0f} | Expenses: ₹{lm_stats["expenses"]:.0f}

Top Spending (category vs budget):
{chr(10).join(budget_lines) or "  No expense data."}

Top Merchants:
{chr(10).join(merchant_lines) or "  No data."}

Monthly Breakdown:
{chr(10).join(month_lines) or "  No monthly data."}

Last 20 Transactions:
{chr(10).join(latest_lines) or "  No transactions found."}

Recurring Payments:
{chr(10).join(recurring_lines) or "  None detected."}{anomaly_section}{forecast_section}

Total transactions: {len(transactions)}"""

    return context
