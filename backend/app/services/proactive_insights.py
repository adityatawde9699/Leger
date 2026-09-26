"""Proactive AI Insights v2 — evidence-backed observations using rules and optional AI.

Behavior:
- Returns at most five insights and may fall back to deterministic rules
- Requires evidence for model-generated insights
- Includes anomaly-driven and forecast-driven context
- Uses per-user caching and sorts by priority
"""

import hashlib
import json
import logging
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ..models import Budget, Transaction
from .ai_router import ai_router
from .currency import format_amount
from .insights import data_quality, monthly_summary, recurring_payments

logger = logging.getLogger("ledger.proactive")


def apply_insight_frequency(insights: list[dict[str, Any]], frequency: str) -> list[dict[str, Any]]:
    """Apply the user's delivery preference without inventing a scheduler."""
    if frequency == "off":
        return []
    if frequency == "important":
        return [item for item in insights if int(item.get("priority", 0)) >= 4]
    return insights

# ── System Prompt (v2) ────────────────────────────────────────────────────────
PROACTIVE_SYSTEM = """You are a financial analyst generating PROACTIVE insights for a personal finance app.
Analyze the data and generate at most 5 SHORT, actionable observations. Return fewer if the data does not support more.

Rules:
- Each insight: ONE sentence, max 25 words, specific numbers only from the provided data
- Types: "warning" (risk/overspend), "tip" (action to take), "positive" (celebrate), "info" (neutral fact)
- Priority 1-5: 5=critical (over budget/anomaly), 4=important, 3=notable, 2=informational, 1=minor tip
- Include "category" field: the relevant spending category, or null
- Include "evidence_ids": a list containing only transaction IDs from the provided data that support the insight
- Include "action": one concrete next step, or null when no action is warranted
- Use only the currency code specified in the data context. Never convert or relabel amounts.
- Return ONLY a JSON array:
  [{"type": "warning|tip|positive|info", "priority": 1-5, "text": "...", "category": "...|null", "evidence_ids": ["..."], "action": "...|null"}]
- No explanation outside the JSON array."""


def _data_quality(transactions: list[Transaction]) -> dict[str, Any]:
    """Describe how much trustworthy data supports an insight."""
    quality = data_quality(transactions)
    return {
        **quality,
        "transactions": quality["transaction_count"],
        "expenses": quality["expense_count"],
        "income": quality["income_count"],
        "months": quality["months_covered"],
        "uncategorized": quality["uncategorized_count"],
    }


def _evidence(transactions: list[Transaction], category: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Return compact, linkable facts for a rule-based insight."""
    matching = [
        tx for tx in transactions
        if tx.type == "expense" and (category is None or tx.category == category)
    ]
    matching.sort(key=lambda tx: (tx.date, tx.amount), reverse=True)
    return [
        {"transaction_id": tx.id, "date": tx.date.isoformat(), "amount": float(tx.amount), "category": tx.category,
         "merchant": tx.merchant_normalized or tx.description[:80]}
        for tx in matching[:limit]
    ]


def _decorate(insight: dict[str, Any], transactions: list[Transaction], source: str = "rules") -> dict[str, Any]:
    """Apply a consistent trust contract to every proactive insight."""
    if not insight.get("id"):
        stable_key = "|".join(
            str(insight.get(value) or "") for value in ("type", "category", "text", "action_type")
        )
        insight["id"] = f"insight_{hashlib.sha256(stable_key.encode()).hexdigest()[:16]}"
    evidence = insight.get("evidence") or _evidence(transactions, insight.get("category"))
    insight["evidence"] = evidence
    insight["source"] = source
    insight["confidence"] = insight.get("confidence") or ("high" if evidence else "low")
    insight["data_quality"] = _data_quality(transactions)
    if not insight.get("action"):
        insight["action"] = "Review the supporting transactions" if evidence else "Add or import more history"
    insight.setdefault("action_type", "view_transactions" if evidence else None)
    quality = insight["data_quality"]
    insight["analysis"] = {
        "period": {
            "start": quality.get("period_start"),
            "end": quality.get("period_end"),
        },
        "comparison_period": insight.get("comparison_period"),
        "method": insight.get(
            "method",
            "evidence-linked model observation" if source == "ai" else "evidence-linked deterministic rule",
        ),
        "transaction_ids": [row.get("transaction_id") for row in evidence if row.get("transaction_id")],
        "sufficient": bool(evidence) and not any(
            warning == "Add more history for reliable comparisons" for warning in quality.get("warnings", [])
        ),
    }
    insight["recommended_action"] = insight["action"]
    insight["status"] = insight.get("status", "new")
    return insight


def _is_quantified_and_actionable(insight: dict[str, Any]) -> bool:
    """Reject generic insight prose that has no measurable reason or next step."""
    text = str(insight.get("text") or "")
    action = str(insight.get("action") or "").strip()
    # A cited row is necessary but not sufficient: the claim itself must
    # contain a measurable value, percentage, count, or date.
    quantified = bool(re.search(r"(?:\d|%|₹|INR\b|USD\b|EUR\b|GBP\b|AED\b|CAD\b|AUD\b|JPY\b)", text))
    return bool(text and action and quantified and insight.get("evidence"))


def _build_proactive_context(
    transactions: list[Transaction],
    budgets: list[Budget],
    anomalies: list[dict] | None = None,
    forecast: dict | None = None,
    currency: str = "INR",
    recurring_tolerance: str = "standard",
) -> str:
    """Build compact context for proactive insights LLM call."""
    summary = monthly_summary(transactions)
    budget_map = {b.category: b.monthly_limit for b in budgets}
    recurring = recurring_payments(transactions, recurring_tolerance)

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
        f"Currency: {currency}; all amounts below use {currency}.",
        f"Income: {format_amount(summary['income'], currency)} | Expenses: {format_amount(summary['expenses'], currency)} | Net: {format_amount(summary['net'], currency)}",
        f"Spending trend vs prior month: {'↑' if trend_pct > 0 else '↓'}{abs(trend_pct):.0f}%",
    ]

    # Category breakdown with budget status and trends
    for cat, amt in sorted(summary["by_category"].items(), key=lambda x: x[1], reverse=True)[:8]:
        limit = budget_map.get(cat)
        pct_str = f" | budget {format_amount(limit, currency)} ({int(amt / limit * 100)}%)" if limit else ""
        change = ""
        if cat in cat_prev and cat_prev[cat] > 0:
            c = float((cat_last[cat] - cat_prev[cat]) / cat_prev[cat] * 100)
            change = f" | {'↑' if c > 0 else '↓'}{abs(c):.0f}% vs last month"
        lines.append(f"  {cat}: {format_amount(amt, currency)}{pct_str}{change}")

    if recurring:
        total_rec = sum(r["average_amount"] for r in recurring)
        lines.append(f"Recurring payments: {len(recurring)} totaling {format_amount(total_rec, currency)}/mo")
        for r in recurring[:3]:
            lines.append(f"  {r['description']}: {format_amount(r['average_amount'], currency)}/mo")

    # Include anomalies as critical context
    if anomalies:
        high = [a for a in anomalies if a.get("severity") in ("high", "medium")][:3]
        if high:
            lines.append(f"ANOMALIES detected ({len(high)}):")
            for a in high:
                lines.append(f"  {a['anomaly_type']}: {format_amount(a['amount'], currency)} in {a['category']} — {a['message']}")

    # Include forecast breach warnings
    if forecast and forecast.get("by_category"):
        for cat, proj in list(forecast["by_category"].items())[:4]:
            limit = budget_map.get(cat)
            if limit and proj["projected_30d"] > float(limit):
                excess = proj["projected_30d"] - float(limit)
                lines.append(f"FORECAST: {cat} projected to exceed budget by {format_amount(excess, currency)} this month")

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
    currency: str = "INR",
    recurring_tolerance: str = "standard",
) -> list[dict]:
    """Fallback rule-based proactive insights."""
    summary = monthly_summary(transactions)
    budget_map = {b.category: b.monthly_limit for b in budgets}
    recurring = recurring_payments(transactions, recurring_tolerance)
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
                    "text": f"Unusual transaction detected: {format_amount(a['amount'], currency)} in {a['category']} — {a['message'][:50]}",
                    "category": a.get("category"),
                    "evidence": [{"transaction_id": a.get("transaction_id"), "date": a.get("date"),
                                  "amount": a.get("amount"), "category": a.get("category")}],
                    "action": "Review this unusual transaction",
                    "action_type": "view_transaction",
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
                    "text": f"{cat} is {format_amount(spent - limit, currency)} over budget — {format_amount(spent, currency)} vs {format_amount(limit, currency)} limit.",
                    "category": cat,
                    "action": f"Review {cat} transactions and adjust the budget or pause discretionary spending",
                    "action_type": "view_category",
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
                    "action": f"Review {cat} transactions before spending more this month",
                    "action_type": "view_category",
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
                "action": "Review your top spending categories",
                "action_type": "view_analytics",
            }
        )
    elif trend_pct < -15:
        insights.append(
            {
                "type": "positive",
                "priority": 3,
                "text": f"Spending down {abs(trend_pct):.0f}% vs last month — great financial discipline!",
                "category": None,
                "action": "Keep the current spending pattern and check your goal progress",
                "action_type": "view_goals",
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
                "action": "Set a savings goal and review your largest flexible categories",
                "action_type": "view_budgets",
            }
        )
    elif savings_rate < 5 and income > 0:
        insights.append(
            {
                "type": "tip",
                "priority": 4,
                "text": f"Savings rate is only {savings_rate:.0f}% — target 20% by reducing top spending categories.",
                "category": None,
                "action": "Review recurring payments for services you no longer use",
                "action_type": "view_transactions",
            }
        )

    # Recurring payments summary
    if len(recurring) >= 3:
        total_rec = float(sum(r["average_amount"] for r in recurring))
        insights.append(
            {
                "type": "info",
                "priority": 2,
                "text": f"{len(recurring)} recurring payments totaling {format_amount(total_rec, currency)}/mo detected.",
                "category": None,
            }
        )

    insights = [_decorate(item, transactions) for item in insights]
    insights = [item for item in insights if _is_quantified_and_actionable(item)]
    # Sort by priority descending
    insights.sort(key=lambda x: x["priority"], reverse=True)
    return insights[:5]


async def generate_proactive_insights(
    transactions: list[Transaction],
    budgets: list[Budget],
    anomalies: list[dict] | None = None,
    forecast: dict | None = None,
    currency: str = "INR",
    allow_ai: bool = True,
    recurring_tolerance: str = "standard",
) -> list[dict[str, Any]]:
    """
    Generate AI-powered proactive insights.
    Always tries LLM first (via ai_router), falls back to rule-based.
    """
    if not transactions:
        return [_decorate({
            "type": "info", "priority": 1, "text": "Add transactions to get personalized insights.",
            "category": None, "confidence": "low", "source": "rules", "evidence": [],
            "action": "Add your first transaction", "action_type": "add_transaction",
        }, [])]

    context = _build_proactive_context(transactions, budgets, anomalies, forecast, currency, recurring_tolerance)

    # Try the configured router; deterministic rules remain the fallback.
    try:
        if not allow_ai:
            logger.info("Cloud AI disabled by user; using deterministic proactive insights")
            return _rule_based_insights(transactions, budgets, anomalies, currency, recurring_tolerance)
        # Include IDs in the context so the model can cite facts instead of inventing them.
        context += "\nEvidence transaction IDs:\n" + "\n".join(
            f"  {tx.id} | {tx.date.isoformat()} | {format_amount(tx.amount, currency)} | {tx.category} | {tx.merchant_normalized or tx.description[:50]}"
            for tx in transactions[:100]
        )
        messages = [{"role": "user", "content": context}]
        raw = await ai_router.generate(PROACTIVE_SYSTEM, messages, task_type="insights")
        parsed = _extract_json_array(raw)

        if parsed and isinstance(parsed, list):
            # Validate and normalize
            valid = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                raw_ids = item.get("evidence_ids", [])
                if not isinstance(raw_ids, list):
                    raw_ids = []
                evidence_ids = {str(tx.id) for tx in transactions}
                cited = [str(tx_id) for tx_id in raw_ids if str(tx_id) in evidence_ids]
                has_model_action = bool(str(item.get("action") or "").strip())
                evidence = [
                    {"transaction_id": tx.id, "date": tx.date.isoformat(), "amount": float(tx.amount),
                     "category": tx.category, "merchant": tx.merchant_normalized or tx.description[:80]}
                    for tx in transactions if str(tx.id) in cited
                ]
                insight = {
                    "type": item.get("type", "info"),
                    "priority": max(1, min(5, int(item.get("priority", 2)))),
                    "text": str(item.get("text", ""))[:200],
                    "category": item.get("category"),
                    "evidence": evidence,
                    "action": str(item.get("action"))[:200] if item.get("action") else None,
                    "action_type": "view_transactions" if evidence else None,
                    "confidence": "medium" if evidence else "low",
                }
                # Do not surface model-generated filler without at least one verifiable fact.
                mentioned_codes = set(re.findall(r"\b(?:INR|USD|EUR|GBP|AED|SGD|CAD|AUD|JPY|CHF|CNY|HKD)\b", insight["text"]))
                wrong_currency = bool(mentioned_codes - {currency}) or (currency != "INR" and "₹" in insight["text"])
                if insight["text"] and evidence and not wrong_currency and insight["type"] in ("warning", "tip", "positive", "info"):
                    insight = _decorate(insight, transactions, source="ai")
                    if has_model_action and _is_quantified_and_actionable(insight):
                        valid.append(insight)
            if valid:
                valid.sort(key=lambda x: x["priority"], reverse=True)
                logger.info("Generated %d LLM proactive insights", len(valid))
                return valid[:5]

    except Exception as e:
        logger.warning("Proactive LLM insights failed: %s", str(e)[:100])

    # Fallback: rule-based insights
    logger.info("Using rule-based proactive insights")
    return _rule_based_insights(transactions, budgets, anomalies, currency, recurring_tolerance)
