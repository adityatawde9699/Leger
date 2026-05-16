"""
LLM-powered auto-categorization.
Uses the AI router to categorize transactions that fall into "Other".
Falls back to rule-based categorizer if LLM is unavailable.
"""
import json
import logging
from typing import Any

from ..config import settings
from .ai_router import ai_router
from .categorizer import CATEGORIES, EXPENSE_CATEGORIES, categorize as rule_categorize

logger = logging.getLogger("ledger.autocategorize")

CATEGORIZE_SYSTEM = """You are a financial transaction categorizer for an Indian personal finance app.
Given a transaction description, classify it into EXACTLY one of these categories:
{categories}

Rules:
- Return ONLY a JSON object: {{"category": "...", "confidence": 0.0-1.0, "merchant": "..."}}
- "merchant" is the normalized merchant/vendor name (e.g., "Swiggy", "Amazon", "PhonePe")
- "confidence" is your confidence from 0.0 to 1.0
- If unclear, use "Other" with low confidence
- No explanation, no extra text. JSON only."""

BATCH_CATEGORIZE_SYSTEM = """You are a financial transaction categorizer for an Indian personal finance app.
Classify each transaction into EXACTLY one of these categories:
{categories}

Return ONLY a JSON array. Each element: {{"id": "...", "category": "...", "confidence": 0.0-1.0, "merchant": "..."}}
No explanation. JSON only."""


async def categorize_single(description: str, tx_type: str = "expense") -> dict[str, Any]:
    """
    Categorize a single transaction. Tries rules first, then LLM.
    Returns: {"category": str, "confidence": float, "merchant": str|None, "source": "rules"|"llm"}
    """
    # 1. Try rules first — instant, free
    rule_result = rule_categorize(description, tx_type)
    if rule_result != "Other":
        return {
            "category": rule_result,
            "confidence": 0.95,
            "merchant": None,
            "source": "rules",
        }

    # 2. If rules returned "Other", try LLM
    if not settings.llama_enabled and not settings.anthropic_api_key:
        return {
            "category": "Other",
            "confidence": 0.1,
            "merchant": None,
            "source": "rules",
        }

    try:
        cats = ", ".join(EXPENSE_CATEGORIES if tx_type == "expense" else CATEGORIES)
        system = CATEGORIZE_SYSTEM.format(categories=cats)
        messages = [{"role": "user", "content": f"Transaction: {description}"}]

        chunks = []
        async for token in ai_router.stream(system, messages, max_tokens=100, prefer_local=True):
            chunks.append(token)
        raw = "".join(chunks).strip()

        # Parse JSON response
        result = json.loads(raw)
        category = result.get("category", "Other")
        if category not in CATEGORIES:
            category = "Other"
        return {
            "category": category,
            "confidence": min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
            "merchant": result.get("merchant"),
            "source": "llm",
        }
    except Exception as e:
        logger.warning("LLM categorization failed for '%s': %s", description[:50], e)
        return {
            "category": "Other",
            "confidence": 0.1,
            "merchant": None,
            "source": "rules",
        }


async def categorize_batch(transactions: list[dict]) -> list[dict[str, Any]]:
    """
    Categorize multiple transactions in one LLM call.
    Input: [{"id": "...", "description": "...", "type": "expense"}]
    Returns: [{"id": "...", "category": "...", "confidence": float, "merchant": str}]
    """
    # First pass: apply rules to everything
    results = {}
    needs_llm = []

    for tx in transactions:
        rule_result = rule_categorize(tx["description"], tx.get("type", "expense"))
        if rule_result != "Other":
            results[tx["id"]] = {
                "id": tx["id"],
                "category": rule_result,
                "confidence": 0.95,
                "merchant": None,
            }
        else:
            needs_llm.append(tx)

    # If nothing needs LLM or LLM unavailable, return early
    if not needs_llm or (not settings.llama_enabled and not settings.anthropic_api_key):
        for tx in needs_llm:
            results[tx["id"]] = {
                "id": tx["id"],
                "category": "Other",
                "confidence": 0.1,
                "merchant": None,
            }
        return [results[tx["id"]] for tx in transactions]

    # Batch LLM call for remaining "Other" transactions
    try:
        cats = ", ".join(EXPENSE_CATEGORIES)
        system = BATCH_CATEGORIZE_SYSTEM.format(categories=cats)
        user_content = "\n".join(
            f'- id: {tx["id"]}, description: {tx["description"]}'
            for tx in needs_llm[:20]  # limit batch size
        )
        messages = [{"role": "user", "content": user_content}]

        chunks = []
        async for token in ai_router.stream(system, messages, max_tokens=500, prefer_local=True):
            chunks.append(token)
        raw = "".join(chunks).strip()
        parsed = json.loads(raw)

        for item in parsed:
            tid = item.get("id")
            if tid and tid in {tx["id"] for tx in needs_llm}:
                cat = item.get("category", "Other")
                if cat not in CATEGORIES:
                    cat = "Other"
                results[tid] = {
                    "id": tid,
                    "category": cat,
                    "confidence": min(1.0, max(0.0, float(item.get("confidence", 0.5)))),
                    "merchant": item.get("merchant"),
                }

        # Fill any missing
        for tx in needs_llm:
            if tx["id"] not in results:
                results[tx["id"]] = {
                    "id": tx["id"],
                    "category": "Other",
                    "confidence": 0.1,
                    "merchant": None,
                }

    except Exception as e:
        logger.warning("Batch LLM categorization failed: %s", e)
        for tx in needs_llm:
            results[tx["id"]] = {
                "id": tx["id"],
                "category": "Other",
                "confidence": 0.1,
                "merchant": None,
            }

    return [results[tx["id"]] for tx in transactions]
