from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ..models import Budget, Transaction


def _expense_value(tx: Transaction) -> Decimal:
    """Return a transaction's contribution to spending totals.

    Refunds and reimbursements offset spending; transfers and unposted rows are
    excluded from income and expense totals so uncertain entries cannot inflate savings.
    """
    if getattr(tx, "status", "posted") != "posted":
        return Decimal("0")
    if tx.type == "expense":
        return tx.amount
    if tx.type in ("refund", "reimbursement"):
        return -tx.amount
    return Decimal("0")


def _is_posted(tx: Transaction) -> bool:
    return getattr(tx, "status", "posted") == "posted"

# ── Advisor System Prompt (v2 — structured reasoning, grounding, formatting) ──
SYSTEM_PROMPT = """You are Ledger AI, a precision financial advisor for Indian users.

Core rules:
- GROUND every claim in the provided transaction data — never invent figures
- FORMAT: Use ₹ symbol, **bold** key numbers, bullet points for lists
- SPECIFIC: Reference actual merchants, categories, and amounts from the data
- COMPARE: When asked about trends, compare current vs previous periods from the data
- HONEST: If data is insufficient to answer, say so clearly and briefly
- Cite the period and transaction evidence when making a specific claim; do not use facts outside the provided context.
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
    income = sum((t.amount for t in transactions if t.type == "income" and _is_posted(t)), Decimal("0"))
    expenses = sum((_expense_value(t) for t in transactions), Decimal("0"))
    by_category: dict[str, Decimal] = defaultdict(Decimal)
    by_day: dict[str, dict] = defaultdict(lambda: {"income": Decimal("0"), "expenses": Decimal("0")})
    by_month: dict[str, dict] = defaultdict(lambda: {"income": Decimal("0"), "expenses": Decimal("0")})
    dates = [tx.date for tx in transactions]

    cash_income = sum((t.amount for t in transactions if t.type == "income" and t.source == "cash" and _is_posted(t)), Decimal("0"))
    cash_expenses = sum((_expense_value(t) for t in transactions if t.source == "cash"), Decimal("0"))

    merchant_totals: dict[str, Decimal] = defaultdict(Decimal)

    for tx in transactions:
        day = str(tx.date)
        month = tx.date.strftime("%Y-%m")
        expense_value = _expense_value(tx)
        if expense_value:
            by_category[tx.category] += expense_value
            by_day[day]["expenses"] += expense_value
            by_month[month]["expenses"] += expense_value
            # Track merchant totals (use normalized merchant or description)
            merchant = tx.merchant_normalized or tx.description
            merchant_totals[merchant] += expense_value
        elif tx.type == "income" and _is_posted(tx):
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
        "data_quality": data_quality(transactions),
    }


def data_quality(transactions: list[Transaction]) -> dict:
    """Return user-facing completeness signals for every derived analysis."""
    dates = [tx.date for tx in transactions]
    months = {tx.date.strftime("%Y-%m") for tx in transactions}
    duplicate_groups: dict[tuple, int] = defaultdict(int)
    for tx in transactions:
        # This is deliberately conservative: equal amounts alone are common;
        # only an exact date/type/account/description match is surfaced.
        key = (
            tx.date,
            tx.type,
            getattr(tx, "account_id", None),
            str(tx.amount),
            (getattr(tx, "description", None) or "").strip().casefold(),
        )
        duplicate_groups[key] += 1
    duplicate_suspects = sum(count - 1 for count in duplicate_groups.values() if count > 1)
    expense_count = sum(1 for tx in transactions if tx.type == "expense" and _is_posted(tx))
    income_count = sum(1 for tx in transactions if tx.type == "income" and _is_posted(tx))
    uncategorized = sum(1 for tx in transactions if not tx.category or tx.category == "Other")
    categorized_pct = round(((expense_count - uncategorized) / expense_count) * 100, 1) if expense_count else None
    income_confidence = (
        "none" if income_count == 0 else
        "low" if len(months) < 2 else
        "medium" if len(months) < 3 else
        "high"
    )
    return {
        "transaction_count": len(transactions),
        "expense_count": expense_count,
        "income_count": income_count,
        "income_confidence": income_confidence,
        "pending_count": sum(1 for tx in transactions if getattr(tx, "status", "posted") == "pending"),
        "excluded_count": sum(1 for tx in transactions if getattr(tx, "status", "posted") == "excluded"),
        "months_covered": len(months),
        "period_start": min(dates).isoformat() if dates else None,
        "period_end": max(dates).isoformat() if dates else None,
        "last_transaction_date": max(dates).isoformat() if dates else None,
        "uncategorized_count": uncategorized,
        "duplicate_suspect_count": duplicate_suspects,
        "categorized_pct": categorized_pct,
        "coverage": "none" if not dates else ("limited" if len(months) < 2 else ("partial" if len(months) < 3 else "good")),
        "warnings": (["Add more history for reliable comparisons"] if len(months) < 3 else [])
        + (["Review uncategorized transactions"] if uncategorized else [])
        + ([f"Review {duplicate_suspects} possible duplicate transaction(s)"] if duplicate_suspects else []),
    }


def build_analysis_object(
    transactions: list[Transaction],
    summary: dict,
    quality: dict | None = None,
) -> dict:
    """Build the shared, evidence-bearing analysis contract for all consumers."""
    quality = quality or summary.get("data_quality") or data_quality(transactions)
    period = {
        "start": summary.get("period_start"),
        "end": summary.get("period_end"),
        "months": summary.get("months_covered", 0),
    }
    expense_ids = [tx.id for tx in transactions if tx.type in ("expense", "refund", "reimbursement") and _is_posted(tx)]
    income_ids = [tx.id for tx in transactions if tx.type == "income" and _is_posted(tx)]
    category_ids: dict[str, list[str]] = defaultdict(list)
    for tx in transactions:
        if tx.type in ("expense", "refund", "reimbursement") and _expense_value(tx):
            category_ids[tx.category].append(tx.id)

    def claim(claim_id: str, kind: str, text: str, amount: Decimal, ids: list[str], method: str) -> dict:
        return {
            "id": claim_id,
            "kind": kind,
            "claim": text,
            "evidence": {
                "period": period,
                "amount": str(amount),
                "transaction_ids": ids[:100],
                "method": method,
            },
            "confidence": "high" if quality.get("coverage") in ("good", "partial") and ids else ("low" if not ids else "medium"),
            "data_quality": quality,
        }

    claims = [
        claim("cashflow.income", "total", f"Income was {summary['income']}", summary["income"], income_ids, "sum income transactions"),
        claim("cashflow.expenses", "total", f"Expenses were {summary['expenses']}", summary["expenses"], expense_ids, "sum expenses minus refunds/reimbursements"),
        claim("cashflow.net", "total", f"Net cash flow was {summary['net']}", summary["net"], income_ids + expense_ids, "income minus expenses; transfers and unposted rows excluded"),
    ]
    for category, amount in sorted(summary.get("by_category", {}).items(), key=lambda item: item[1], reverse=True)[:10]:
        claims.append(
            claim(
                f"spending.{category.casefold().replace(' ', '_')}",
                "category_total",
                f"{category} spending was {amount}",
                amount,
                category_ids[category],
                "sum category expenses minus refunds/reimbursements",
            )
        )
    return {
        "version": 1,
        "period": period,
        "transaction_count": len(transactions),
        "data_quality": quality,
        "claims": claims,
    }


def compare_periods(
    transactions: list[Transaction],
    *,
    end_date: date | None = None,
    days: int = 30,
) -> dict:
    """Compare equal-length periods with evidence and sufficiency metadata."""
    days = max(7, min(days, 365))
    available_end = max((tx.date for tx in transactions), default=None)
    end = end_date or available_end or date.today()
    current_start = end - timedelta(days=days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)

    def window(start: date, finish: date) -> dict:
        rows = [tx for tx in transactions if start <= tx.date <= finish]
        income_rows = [tx for tx in rows if tx.type == "income" and _is_posted(tx)]
        spending_rows = [tx for tx in rows if tx.type in ("expense", "refund", "reimbursement") and _is_posted(tx)]
        income = sum((tx.amount for tx in income_rows), Decimal("0"))
        expenses = sum((_expense_value(tx) for tx in rows), Decimal("0"))
        categories: dict[str, Decimal] = defaultdict(Decimal)
        category_ids: dict[str, list[str]] = defaultdict(list)
        for tx in spending_rows:
            value = _expense_value(tx)
            if value:
                categories[tx.category] += value
                category_ids[tx.category].append(tx.id)
        return {
            "period": {"start": start.isoformat(), "end": finish.isoformat(), "days": days},
            "transaction_count": len(rows),
            "income": income,
            "expenses": expenses,
            "net": income - expenses,
            "income_transaction_ids": [tx.id for tx in income_rows][:100],
            "expense_transaction_ids": [tx.id for tx in spending_rows][:100],
            "by_category": categories,
            "category_transaction_ids": dict(category_ids),
        }

    current = window(current_start, end)
    previous = window(previous_start, previous_end)

    def percent_change(now: Decimal, before: Decimal) -> Decimal | None:
        if before == 0:
            return None
        return ((now - before) / abs(before) * Decimal("100")).quantize(Decimal("0.1"))

    category_changes = []
    for category in sorted(set(current["by_category"]) | set(previous["by_category"])):
        now = current["by_category"].get(category, Decimal("0"))
        before = previous["by_category"].get(category, Decimal("0"))
        category_changes.append(
            {
                "category": category,
                "current": now,
                "previous": before,
                "change": now - before,
                "percent_change": percent_change(now, before),
                "transaction_ids": (
                    current["category_transaction_ids"].get(category, [])
                    + previous["category_transaction_ids"].get(category, [])
                )[:100],
            }
        )
    category_changes.sort(key=lambda item: abs(item["change"]), reverse=True)

    has_current = bool(current["transaction_count"])
    has_previous = bool(previous["transaction_count"])
    warnings = []
    if not has_current:
        warnings.append("No transactions in the current comparison period")
    if not has_previous:
        warnings.append("No transactions in the previous comparison period")
    return {
        "version": 1,
        "status": "ready" if has_current and has_previous else "insufficient_data",
        "period_days": days,
        "current": current,
        "previous": previous,
        "changes": {
            "income": current["income"] - previous["income"],
            "income_percent": percent_change(current["income"], previous["income"]),
            "expenses": current["expenses"] - previous["expenses"],
            "expenses_percent": percent_change(current["expenses"], previous["expenses"]),
            "net": current["net"] - previous["net"],
            "net_percent": percent_change(current["net"], previous["net"]),
        },
        "category_changes": category_changes[:20],
        "data_quality": {
            "current_transaction_count": current["transaction_count"],
            "previous_transaction_count": previous["transaction_count"],
            "status": "good" if has_current and has_previous else "limited",
            "warnings": warnings,
        },
    }


def dynamic_budget_suggestions(transactions: list[Transaction]) -> list[dict]:
    """Suggest budgets based on observed monthly spending average at 90% cap."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    months = {tx.date.strftime("%Y-%m") for tx in transactions}
    divisor = Decimal(max(len(months), 1))
    for tx in transactions:
        value = _expense_value(tx)
        if value > 0:
            totals[tx.category] += value
    return [
        {
            "category": cat,
            "monthly_limit": round((totals[cat] / divisor) * Decimal("0.9"), 2),
            "strategy": f"dynamic_{len(months) or 1}mo_90",
        }
        for cat in sorted(totals)
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

    recent = [t for t in transactions if t.type == "expense" and _is_posted(t) and t.date >= date.today() - timedelta(days=7)]
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
    """Detect likely recurring payments with cadence, confidence, and evidence.

    Two matching charges are enough to surface a lead, but confidence remains
    low until timing and amounts are regular. This avoids presenting every
    repeated merchant as a confirmed subscription.
    """
    grouped: dict[tuple, list] = defaultdict(list)
    for tx in transactions:
        if tx.type == "expense" and _is_posted(tx):
            merchant = " ".join((tx.merchant_normalized or tx.description).casefold().split())
            grouped[(merchant, tx.category)].append(tx)
    recurring = []
    for (description, category), items in grouped.items():
        if len(items) >= 2:
            amounts = [item.amount for item in items]
            avg = sum(amounts, Decimal("0")) / len(amounts)
            dates = sorted(item.date for item in items)
            gaps = [(later - earlier).days for earlier, later in zip(dates, dates[1:], strict=False)]
            avg_gap_days = sum(gaps) / len(gaps)
            gap_variation = (max(gaps) - min(gaps)) / max(avg_gap_days, 1)
            amount_variation = float(max(amounts) - min(amounts)) / max(float(avg), 1)
            cadence = (
                "weekly" if 5 <= avg_gap_days <= 10 else
                "biweekly" if 11 <= avg_gap_days <= 18 else
                "monthly" if 25 <= avg_gap_days <= 35 else
                "quarterly" if 70 <= avg_gap_days <= 100 else
                "irregular"
            )
            timing_score = max(0.0, 1.0 - min(gap_variation, 1.0))
            amount_score = max(0.0, 1.0 - min(amount_variation, 1.0))
            count_score = min(len(items) / 4, 1.0)
            confidence = round(0.35 * count_score + 0.35 * timing_score + 0.30 * amount_score, 2)
            next_date = dates[-1] + timedelta(days=round(avg_gap_days))
            last_date = dates[-1]
            active = last_date >= date.today() - timedelta(days=max(round(avg_gap_days * 2), 45))
            recurring.append(
                {
                    "description": description.title(),
                    "category": category,
                    "average_amount": avg,
                    "count": len(items),
                    "minimum_amount": min(amounts),
                    "maximum_amount": max(amounts),
                    "cadence": cadence,
                    "confidence": confidence,
                    "status": "active" if active else "stale",
                    "last_date": last_date.isoformat(),
                    "next_expected": next_date.isoformat() if next_date else None,
                    "evidence": [
                        {"transaction_id": item.id, "date": item.date.isoformat(), "amount": str(item.amount)}
                        for item in sorted(items, key=lambda item: item.date, reverse=True)[:12]
                    ],
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
        f"  id={tx.id} | {tx.date.isoformat()} {tx.date.strftime('%a')} | {tx.type} | "
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
