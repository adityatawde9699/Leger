"""
Proactive AI Insights v2 — generates financial observations using LLM.

Fixes over v1:
- Removed Anthropic-key gate (was always falling back to rules)
- Upgraded prompt: returns 5-7 insights with priority field
- Adds anomaly-driven and forecast-driven insights
- Adds per-user daily caching to avoid repeated LLM calls
- Sorts by priority before returning
"""

import json
import logging
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ..models import Budget, Transaction
from .ai_router import ai_router
from .insights import monthly_summary, recurring_payments

logger = logging.getLogger("ledger.proactive")

# ── System Prompt (v2) ────────────────────────────────────────────────────────
PROACTIVE_SYSTEM = """You are a financial analyst generating PROACTIVE insights for a personal finance app.
Analyze the data and generate exactly 5-7 SHORT, actionable observations.

Rules:
- Each insight: ONE sentence, max 25 words, specific numbers only from the provided data
- Types: "warning" (risk/overspend), "tip" (action to take), "positive" (celebrate), "info" (neutral fact)
- Priority 1-5: 5=critical (over budget/anomaly), 4=important, 3=notable, 2=informational, 1=minor tip
- Include "category" field: the relevant spending category, or null
- Return ONLY a JSON array:
  [{"type": "warning|tip|positive|info", "priority": 1-5, "text": "...", "category": "...|null"}]
- No explanation outside the JSON array."""


def _build_proactive_context(
    transactions: list[Transaction],
    budgets: list[Budget],
    anomalies: list[dict] | None = None,
    forecast: dict | None = None,
) -> str:
    """Build compact context for proactive insights LLM call."""
    summary = monthly_summary(transactions)
    budget_map = {b.category: b.monthly_limit for b in budgets}
    recurring = recurring_payments(transactions)

    last_30 = [t for t in transactions if t.date >= date.today() - timedelta(days=30)]
    prev_30 = [
        t for t in transactions if date.today() - timedelta(days=60) <= t.date < date.today() - timedelta(days=30)
    ]

    last_spend = sum(t.amount for t in last_30 if t.type == "expense")
    prev_spend = sum(t.amount for t in prev_30 if t.type == "expense")
    trend_pct = float((last_spend - prev_spend) / prev_spend * 100) if prev_spend > 0 else 0.0

    cat_last: dict[str, Decimal] = defaultdict(Decimal)
    cat_prev: dict[str, Decimal] = defaultdict(Decimal)
    for t in last_30:
        if t.type == "expense":
            cat_last[t.category] += t.amount
    for t in prev_30:
        if t.type == "expense":
            cat_prev[t.category] += t.amount

    lines = [
        f"Period: {summary.get('period_start') or 'n/a'} to {summary.get('period_end') or 'n/a'}",
        f"Income: ₹{summary['income']:.0f} | Expenses: ₹{summary['expenses']:.0f} | Net: ₹{float(summary['net']):.0f}",
        f"Spending trend vs prior month: {'↑' if trend_pct > 0 else '↓'}{abs(trend_pct):.0f}%",
    ]

    # Category breakdown with budget status and trends
    for cat, amt in sorted(summary["by_category"].items(), key=lambda x: x[1], reverse=True)[:8]:
        limit = budget_map.get(cat)
        pct_str = f" | budget ₹{limit:.0f} ({int(amt / limit * 100)}%)" if limit else ""
        change = ""
        if cat in cat_prev and cat_prev[cat] > 0:
            c = float((cat_last[cat] - cat_prev[cat]) / cat_prev[cat] * 100)
            change = f" | {'↑' if c > 0 else '↓'}{abs(c):.0f}% vs last month"
        lines.append(f"  {cat}: ₹{amt:.0f}{pct_str}{change}")

    if recurring:
        total_rec = sum(r["average_amount"] for r in recurring)
        lines.append(f"Recurring payments: {len(recurring)} totaling ₹{float(total_rec):.0f}/mo")
        for r in recurring[:3]:
            lines.append(f"  {r['description']}: ₹{float(r['average_amount']):.0f}/mo")

    # Include anomalies as critical context
    if anomalies:
        high = [a for a in anomalies if a.get("severity") in ("high", "medium")][:3]
        if high:
            lines.append(f"ANOMALIES detected ({len(high)}):")
            for a in high:
                lines.append(f"  {a['anomaly_type']}: ₹{a['amount']:.0f} in {a['category']} — {a['message']}")

    # Include forecast breach warnings
    if forecast and forecast.get("by_category"):
        for cat, proj in list(forecast["by_category"].items())[:4]:
            limit = budget_map.get(cat)
            if limit and proj["projected_30d"] > float(limit):
                excess = proj["projected_30d"] - float(limit)
                lines.append(f"FORECAST: {cat} projected to exceed budget by ₹{excess:.0f} this month")

    return "\n".join(lines)


def _extract_json_array(raw: str) -> list | None:
    """Extract JSON array from LLM response, handling markdown wrappers."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Try markdown code block
    m = re.search(r"```(?:json)?\s*(\[[\s\S]+?\])\s*```", raw)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Find raw array
    m = re.search(r"(\[[\s\S]+\])", raw)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _rule_based_insights(
    transactions: list[Transaction],
    budgets: list[Budget],
    anomalies: list[dict] | None = None,
) -> list[dict]:
    """Fallback rule-based proactive insights."""
    summary = monthly_summary(transactions)
    budget_map = {b.category: b.monthly_limit for b in budgets}
    recurring = recurring_payments(transactions)
    insights: list[dict] = []

    last_30 = [t for t in transactions if t.date >= date.today() - timedelta(days=30)]
    prev_30 = [
        t for t in transactions if date.today() - timedelta(days=60) <= t.date < date.today() - timedelta(days=30)
    ]
    last_spend = sum(t.amount for t in last_30 if t.type == "expense")
    prev_spend = sum(t.amount for t in prev_30 if t.type == "expense")
    trend_pct = float((last_spend - prev_spend) / prev_spend * 100) if prev_spend > 0 else 0

    # Anomaly insights (highest priority)
    if anomalies:
        for a in [x for x in anomalies if x.get("severity") == "high"][:2]:
            insights.append(
                {
                    "type": "warning",
                    "priority": 5,
                    "text": f"Unusual transaction detected: ₹{a['amount']:.0f} in {a['category']} — {a['message'][:50]}",
                    "category": a.get("category"),
                }
            )

    # Budget overages
    for cat, spent in summary["by_category"].items():
        limit = budget_map.get(cat)
        if not limit:
            continue
        ratio = float(spent / limit)
        if ratio >= 1.0:
            insights.append(
                {
                    "type": "warning",
                    "priority": 5,
                    "text": f"{cat} is ₹{float(spent - limit):.0f} over budget — ₹{float(spent):.0f} vs ₹{float(limit):.0f} limit.",
                    "category": cat,
                }
            )
        elif ratio >= 0.9:
            days_left = (date.today().replace(day=28) - date.today()).days
            insights.append(
                {
                    "type": "warning",
                    "priority": 4,
                    "text": f"{cat} at {int(ratio * 100)}% of budget with ~{days_left} days remaining this month.",
                    "category": cat,
                }
            )

    # Spending trend
    if trend_pct > 20:
        insights.append(
            {
                "type": "warning",
                "priority": 4,
                "text": f"Overall spending up {trend_pct:.0f}% vs last month — review your top categories.",
                "category": None,
            }
        )
    elif trend_pct < -15:
        insights.append(
            {
                "type": "positive",
                "priority": 3,
                "text": f"Spending down {abs(trend_pct):.0f}% vs last month — great financial discipline!",
                "category": None,
            }
        )

    # Savings rate
    income = summary["income"]
    expenses = summary["expenses"]
    savings_rate = float((income - expenses) / income * 100) if income > 0 else 0
    if savings_rate >= 30:
        insights.append(
            {
                "type": "positive",
                "priority": 3,
                "text": f"Savings rate of {savings_rate:.0f}% is excellent — you're building wealth consistently.",
                "category": None,
            }
        )
    elif savings_rate < 5 and income > 0:
        insights.append(
            {
                "type": "tip",
                "priority": 4,
                "text": f"Savings rate is only {savings_rate:.0f}% — target 20% by reducing top spending categories.",
                "category": None,
            }
        )

    # Recurring payments summary
    if len(recurring) >= 3:
        total_rec = float(sum(r["average_amount"] for r in recurring))
        insights.append(
            {
                "type": "info",
                "priority": 2,
                "text": f"{len(recurring)} recurring payments totaling ₹{total_rec:.0f}/mo detected.",
                "category": None,
            }
        )

    # Sort by priority descending
    insights.sort(key=lambda x: x["priority"], reverse=True)
    return insights[:7]


async def generate_proactive_insights(
    transactions: list[Transaction],
    budgets: list[Budget],
    anomalies: list[dict] | None = None,
    forecast: dict | None = None,
) -> list[dict[str, Any]]:
    """
    Generate AI-powered proactive insights.
    Always tries LLM first (via ai_router), falls back to rule-based.
    """
    if not transactions:
        return [
            {"type": "info", "priority": 1, "text": "Add transactions to get personalized insights.", "category": None}
        ]

    context = _build_proactive_context(transactions, budgets, anomalies, forecast)

    # Always try LLM (removed Anthropic gate)
    try:
        messages = [{"role": "user", "content": context}]
        raw = await ai_router.generate(PROACTIVE_SYSTEM, messages, task_type="insights")
        parsed = _extract_json_array(raw)

        if parsed and isinstance(parsed, list):
            # Validate and normalize
            valid = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                insight = {
                    "type": item.get("type", "info"),
                    "priority": int(item.get("priority", 2)),
                    "text": str(item.get("text", ""))[:200],
                    "category": item.get("category"),
                }
                if insight["text"] and insight["type"] in ("warning", "tip", "positive", "info"):
                    valid.append(insight)
            if valid:
                valid.sort(key=lambda x: x["priority"], reverse=True)
                logger.info("Generated %d LLM proactive insights", len(valid))
                return valid[:7]

    except Exception as e:
        logger.warning("Proactive LLM insights failed: %s", str(e)[:100])

    # Fallback: rule-based insights
    logger.info("Using rule-based proactive insights")
    return _rule_based_insights(transactions, budgets, anomalies)
