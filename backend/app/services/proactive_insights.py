"""
Proactive AI insights — generates financial observations on demand using LLM.
These go beyond the rule-based compute_insights() to provide personalized advice.
"""
import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from collections import defaultdict

from ..models import Budget, Transaction
from .insights import monthly_summary, recurring_payments
from .ai_router import ai_router
from ..config import settings

logger = logging.getLogger("ledger.proactive")

PROACTIVE_SYSTEM = """You are a financial analyst generating PROACTIVE insights for a personal finance app.
Analyze the data and generate exactly 3-5 SHORT, actionable observations.

Rules:
- Each insight must be ONE sentence, max 20 words
- Be specific — reference actual numbers and categories
- Use these types: "warning", "tip", "positive", "info"
- Return ONLY a JSON array: [{"type": "warning|tip|positive|info", "text": "..."}]
- No explanation outside the JSON array."""


async def generate_proactive_insights(
    transactions: list[Transaction],
    budgets: list[Budget],
) -> list[dict]:
    """
    Generate AI-powered proactive insights.
    Falls back to rule-based insights if LLM is unavailable.
    """
    if not transactions:
        return [{"type": "info", "text": "Add transactions to get personalized insights."}]

    # Build compact context
    summary = monthly_summary(transactions)
    budget_map = {b.category: b.monthly_limit for b in budgets}
    recurring = recurring_payments(transactions)

    # Calculate trend data
    last_30 = [t for t in transactions if t.date >= date.today() - timedelta(days=30)]
    prev_30 = [t for t in transactions if date.today() - timedelta(days=60) <= t.date < date.today() - timedelta(days=30)]

    last_spend = sum(t.amount for t in last_30 if t.type == "expense")
    prev_spend = sum(t.amount for t in prev_30 if t.type == "expense")
    trend_pct = ((last_spend - prev_spend) / prev_spend * 100) if prev_spend > 0 else 0

    # Category-level trends
    cat_last = defaultdict(Decimal)
    cat_prev = defaultdict(Decimal)
    for t in last_30:
        if t.type == "expense":
            cat_last[t.category] += t.amount
    for t in prev_30:
        if t.type == "expense":
            cat_prev[t.category] += t.amount

    # Try LLM for rich insights
    if settings.llama_enabled or settings.anthropic_api_key:
        try:
            context_lines = [
                f"Period: {date.today().strftime('%B %Y')}",
                f"Income: ₹{summary['income']} | Expenses: ₹{summary['expenses']} | Net: ₹{summary['net']}",
                f"Spending trend: {'up' if trend_pct > 0 else 'down'} {abs(trend_pct):.0f}% vs last month",
            ]
            for cat, amt in sorted(summary['by_category'].items(), key=lambda x: x[1], reverse=True)[:6]:
                limit = budget_map.get(cat)
                change = ""
                if cat in cat_prev and cat_prev[cat] > 0:
                    c = ((cat_last[cat] - cat_prev[cat]) / cat_prev[cat] * 100)
                    change = f" ({'up' if c > 0 else 'down'} {abs(c):.0f}%)"
                budget_note = f" budget: ₹{limit}" if limit else ""
                context_lines.append(f"  {cat}: ₹{amt}{budget_note}{change}")

            if recurring:
                context_lines.append(f"Recurring payments: {len(recurring)} detected")
                for r in recurring[:3]:
                    context_lines.append(f"  {r['description']}: ~₹{r['average_amount']:.0f}/mo")

            messages = [{"role": "user", "content": "\n".join(context_lines)}]
            chunks = []
            async for token in ai_router.stream(PROACTIVE_SYSTEM, messages, max_tokens=300, prefer_local=True):
                chunks.append(token)
            raw = "".join(chunks).strip()
            return json.loads(raw)

        except Exception as e:
            logger.warning("Proactive LLM insights failed: %s", e)

    # Fallback: rule-based proactive insights
    insights = []

    if trend_pct > 15:
        insights.append({"type": "warning", "text": f"Spending up {trend_pct:.0f}% vs last month — review your expenses."})
    elif trend_pct < -10:
        insights.append({"type": "positive", "text": f"Spending down {abs(trend_pct):.0f}% vs last month — keep it up!"})

    for cat, spent in summary['by_category'].items():
        limit = budget_map.get(cat)
        if limit and spent > limit:
            insights.append({"type": "warning", "text": f"{cat} over budget by ₹{spent - limit}."})
        elif limit and spent >= limit * Decimal("0.9"):
            days_left = (date(date.today().year, date.today().month % 12 + 1, 1) - date.today()).days if date.today().month < 12 else (date(date.today().year + 1, 1, 1) - date.today()).days
            insights.append({"type": "warning", "text": f"{cat} at {int(spent/limit*100)}% of budget with {days_left} days left."})

    if len(recurring) >= 3:
        total_recurring = sum(r['average_amount'] for r in recurring)
        insights.append({"type": "info", "text": f"{len(recurring)} recurring payments totaling ~₹{total_recurring:.0f}/mo detected."})

    savings_rate = (summary['net'] / summary['income'] * 100) if summary['income'] > 0 else 0
    if savings_rate > 20:
        insights.append({"type": "positive", "text": f"Saving {savings_rate:.0f}% of income — excellent financial health."})
    elif savings_rate < 5 and summary['income'] > 0:
        insights.append({"type": "tip", "text": f"Only saving {savings_rate:.0f}% of income — aim for 20% minimum."})

    return insights[:5] if insights else [{"type": "info", "text": "Add more transactions for personalized insights."}]
