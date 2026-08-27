"""
Bill Negotiator v2 — fixed to use ai_router.generate() instead of non-existent .generate() method.
"""

import json
import logging
from typing import Any

from .ai_router import ai_router

logger = logging.getLogger("ledger.negotiator")

NEGOTIATOR_SYSTEM = """You are an expert bill negotiation advisor for Indian consumers.
Analyze the user's recurring payments and suggest specific, actionable negotiation strategies.

For each recurring payment, provide:
1. Whether it can be negotiated
2. Estimated savings potential (monthly INR amount)
3. A specific negotiation script/approach
4. Alternative services at lower cost

Return ONLY a JSON array:
[
  {
    "merchant": "...",
    "current_cost": 0.00,
    "negotiable": true/false,
    "savings_potential": 0.00,
    "strategy": "Step-by-step negotiation approach...",
    "alternatives": ["Alternative 1 at ₹X", "Alternative 2 at ₹Y"],
    "difficulty": "easy|medium|hard"
  }
]

JSON only. No commentary."""


async def analyze_bills(recurring_payments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Analyze recurring payments and generate negotiation strategies.
    Uses ai_router.generate() (non-streaming). Falls back to rule-based analysis.
    """
    if not recurring_payments:
        return []

    try:
        prompt = f"""Analyze these recurring payments from an Indian user and suggest negotiations:

{json.dumps(recurring_payments, indent=2, default=str)}

Focus on subscriptions, utilities, insurance, and services where negotiation or switching is viable."""

        response = await ai_router.generate(
            system=NEGOTIATOR_SYSTEM,
            user_message=prompt,
            task_type="negotiate",
        )

        results = json.loads(response)
        if isinstance(results, list):
            return results

    except Exception as e:
        logger.warning("LLM negotiator failed, using rules: %s", str(e)[:80])

    return _rule_based_analysis(recurring_payments)


def _rule_based_analysis(payments: list[dict]) -> list[dict]:
    """Rule-based bill negotiation when LLM is unavailable."""
    results = []

    NEGOTIABLE_CATEGORIES = {
        "Subscriptions": {
            "negotiable": True,
            "savings_pct": 0.20,
            "strategy": "Check for annual plans (typically 15-40% cheaper). Look for family/group plans. Use cashback portals for renewals.",
            "alternatives": ["Annual plan", "Shared subscription", "Cashback portal renewal"],
            "difficulty": "easy",
        },
        "Utilities": {
            "negotiable": True,
            "savings_pct": 0.10,
            "strategy": "Compare tariff plans on your provider's website. Switch to time-of-use plans. Consider prepaid meters for electricity.",
            "alternatives": ["Alternative provider", "Prepaid plan"],
            "difficulty": "medium",
        },
        "Insurance": {
            "negotiable": True,
            "savings_pct": 0.15,
            "strategy": "Compare premiums on PolicyBazaar. Increase deductible to lower premium. Ask for no-claim bonus discount.",
            "alternatives": ["PolicyBazaar comparison", "Higher deductible plan"],
            "difficulty": "medium",
        },
        "Health": {
            "negotiable": True,
            "savings_pct": 0.12,
            "strategy": "Switch to generic medicines. Use Tata 1mg/PharmEasy for 20-40% discounts. Negotiate lab test rates.",
            "alternatives": ["Tata 1mg", "PharmEasy", "Generic medicines"],
            "difficulty": "easy",
        },
        "Housing": {
            "negotiable": True,
            "savings_pct": 0.08,
            "strategy": "Negotiate rent during renewal citing market rates. Offer longer lease for discount. Maintain property well for leverage.",
            "alternatives": ["Market rate negotiation", "Longer lease deal"],
            "difficulty": "hard",
        },
    }

    for payment in payments:
        category = payment.get("category", "Other")
        amount = float(payment.get("average_amount", payment.get("amount", 0)))
        merchant = payment.get("description", payment.get("merchant", "Unknown"))

        rule = NEGOTIABLE_CATEGORIES.get(category)
        if rule:
            results.append(
                {
                    "merchant": merchant,
                    "current_cost": amount,
                    "negotiable": rule["negotiable"],
                    "savings_potential": round(amount * rule["savings_pct"], 2),
                    "strategy": rule["strategy"],
                    "alternatives": rule.get("alternatives", []),
                    "difficulty": rule["difficulty"],
                }
            )
        elif amount > 500:
            results.append(
                {
                    "merchant": merchant,
                    "current_cost": amount,
                    "negotiable": False,
                    "savings_potential": 0,
                    "strategy": "Review if this service is still needed. Consider downgrading to a basic plan.",
                    "alternatives": [],
                    "difficulty": "easy",
                }
            )

    return results
