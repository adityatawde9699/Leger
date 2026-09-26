"""Evidence-backed merchant and recurring-payment leakage candidates."""

import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal


def _merchant(tx) -> str:
    return " ".join((getattr(tx, "merchant_normalized", None) or tx.description or "").casefold().split())


def _tokens(value: str) -> set[str]:
    return {token for token in value.split() if len(token) > 2}


def _rule_evidence(rule) -> list[str]:
    try:
        return list(json.loads(getattr(rule, "evidence_transaction_ids", None) or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def detect_leakage(transactions: list, recurring_rules: list, *, as_of: date | None = None) -> dict:
    """Return cautious leakage candidates with evidence and recommended actions."""
    as_of = as_of or date.today()
    posted = [
        tx for tx in transactions
        if getattr(tx, "status", "posted") == "posted" and tx.type == "expense" and tx.date <= as_of
    ]
    by_merchant: dict[str, list] = defaultdict(list)
    for tx in posted:
        by_merchant[_merchant(tx)].append(tx)

    items: list[dict] = []

    # Require four observations so one unusually large purchase does not become
    # a price-increase claim.
    for merchant, rows in by_merchant.items():
        rows.sort(key=lambda tx: tx.date)
        if len(rows) < 4:
            continue
        prior = rows[-4:-2]
        recent = rows[-2:]
        prior_avg = sum((tx.amount for tx in prior), Decimal("0")) / Decimal(len(prior))
        recent_avg = sum((tx.amount for tx in recent), Decimal("0")) / Decimal(len(recent))
        if prior_avg <= 0 or recent_avg <= prior_avg * Decimal("1.10"):
            continue
        items.append({
            "id": f"price_increase:{merchant}",
            "kind": "price_increase",
            "claim": f"{merchant} is charging more than its earlier observed amounts",
            "evidence": {
                "transaction_ids": [tx.id for tx in rows[-4:]],
                "prior_average": prior_avg,
                "recent_average": recent_avg,
                "change_percent": ((recent_avg - prior_avg) / prior_avg * Decimal("100")).quantize(Decimal("0.1")),
            },
            "confidence": "medium",
            "recommended_action": "Review the recent charges and confirm whether the price change is expected.",
        })

    # A concentration signal is useful only with enough total spend to matter.
    total = sum((tx.amount for tx in posted), Decimal("0"))
    if total > 0:
        merchant_totals = {
            merchant: sum((tx.amount for tx in rows), Decimal("0"))
            for merchant, rows in by_merchant.items()
        }
        for merchant, amount in sorted(merchant_totals.items(), key=lambda item: item[1], reverse=True)[:3]:
            share = amount / total
            if share >= Decimal("0.30") and len(by_merchant[merchant]) >= 2:
                items.append({
                    "id": f"concentration:{merchant}",
                    "kind": "concentration",
                    "claim": f"{merchant} represents a large share of recorded spending",
                    "evidence": {
                        "transaction_ids": [tx.id for tx in by_merchant[merchant]][:100],
                        "amount": amount,
                        "share_percent": (share * Decimal("100")).quantize(Decimal("0.1")),
                    },
                    "confidence": "medium",
                    "recommended_action": "Review this merchant's transactions before trying to reduce unrelated categories.",
                })

    active_rules = [
        rule for rule in recurring_rules
        if getattr(rule, "confirmed", False) and getattr(rule, "status", "active") == "active"
    ]
    for rule in active_rules:
        if not rule.next_expected or rule.next_expected >= as_of:
            continue
        grace_days = {"weekly": 7, "biweekly": 10, "monthly": 21, "quarterly": 45}.get(rule.cadence, 30)
        if as_of <= rule.next_expected + timedelta(days=grace_days):
            continue
        items.append({
            "id": f"dormant:{rule.id}",
            "kind": "dormant_recurring",
            "claim": f"Confirmed recurring payment {rule.description} may be dormant",
            "evidence": {"rule_id": rule.id, "transaction_ids": _rule_evidence(rule), "next_expected": rule.next_expected},
            "confidence": "medium",
            "recommended_action": "Check the service and pause or cancel the recurring rule if it is no longer expected.",
        })

    # Potential duplicates require both close descriptions and the same
    # category; this remains a review lead, never an automatic cancellation.
    for left_index, left in enumerate(active_rules):
        for right in active_rules[left_index + 1:]:
            if left.category != right.category or left.description.casefold() == right.description.casefold():
                continue
            left_tokens = _tokens(left.description.casefold())
            right_tokens = _tokens(right.description.casefold())
            overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
            ranges_overlap = left.minimum_amount <= right.maximum_amount and right.minimum_amount <= left.maximum_amount
            if overlap < 0.5 or not ranges_overlap:
                continue
            items.append({
                "id": f"duplicate_services:{left.id}:{right.id}",
                "kind": "duplicate_services",
                "claim": f"Two confirmed {left.category} services may overlap",
                "evidence": {"transaction_ids": (_rule_evidence(left) + _rule_evidence(right))[:100]},
                "confidence": "low",
                "recommended_action": "Compare the two services before cancelling either one.",
            })

    period_start = min((tx.date for tx in posted), default=None)
    period_end = max((tx.date for tx in posted), default=None)
    for item in items:
        evidence = item.get("evidence", {})
        transaction_ids = evidence.get("transaction_ids", [])
        item["action_type"] = "open_transactions"
        item["status"] = "new"
        item["analysis"] = {
            "period": {
                "start": period_start.isoformat() if period_start else None,
                "end": period_end.isoformat() if period_end else None,
            },
            "comparison_period": None,
            "method": f"deterministic {item.get('kind', 'leakage')} review rule",
            "transaction_ids": transaction_ids[:100],
            "rule_id": evidence.get("rule_id"),
            "sufficient": bool(transaction_ids or evidence.get("rule_id")),
        }
        item["data_quality"] = {
            "posted_transaction_count": len(posted),
            "confirmed_rule_count": len(active_rules),
            "warnings": [] if posted else ["Add posted transactions before checking for leakage"],
        }

    return {
        "version": 1,
        "status": "ready" if posted else "insufficient_data",
        "items": items[:20],
        "data_quality": {
            "posted_transaction_count": len(posted),
            "confirmed_rule_count": len(active_rules),
            "warnings": [] if posted else ["Add posted transactions before checking for leakage"],
        },
    }
