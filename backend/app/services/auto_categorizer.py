"""
LLM-powered auto-categorization — v2 upgrade.

Pipeline (in order of priority):
  1. User-specific override dict (from manual corrections) — highest confidence
  2. Rule-based categorizer (instant, free, 300+ rules)
  3. Embedding similarity cache (semantic match, local, zero-cost)
  4. LLM batch call (only for genuinely ambiguous transactions)

Improvements over v1:
  - Embedding cache tier between rules and LLM
  - Send to LLM when confidence < threshold (not just generic UPI)
  - JSON extraction with regex fallback for markdown-wrapped responses
  - User override integration
  - `reason` field in output for explainability
  - Chunk large batches with parallel async calls
"""

import asyncio
import json
import logging
import re
from typing import Any

from ..config import settings
from .ai_router import ai_router
from .categorizer import (
    CATEGORIES,
    EXPENSE_CATEGORIES,
    extract_upi_merchant,
)
from .categorizer import categorize as rule_categorize
from .embedding_cache import embedding_cache

logger = logging.getLogger("ledger.autocategorize")

# ── Configuration ──────────────────────────────────────────────────────────────
RULES_CONFIDENCE = 0.95  # Confidence assigned to rule matches
EMBEDDING_CONFIDENCE = 0.88  # Confidence floor for embedding matches
LLM_TRIGGER_THRESHOLD = 0.85  # Send to LLM if confidence below this
LLM_BATCH_SIZE = 15  # Transactions per LLM batch call
LLM_PARALLEL_BATCHES = 3  # Max parallel batch calls

# ── System Prompts ──────────────────────────────────────────────────────────────
CATEGORIZE_SYSTEM = """You are a financial transaction categorizer for an Indian personal finance app.
Given a transaction description, classify it into EXACTLY one of these categories:
{categories}

Few-shot examples (format: description -> JSON):
"UPI/DR/123/SWIGGY INDIA" -> {{"category": "Dining", "confidence": 0.98, "merchant": "Swiggy", "reason": "Swiggy is a food delivery app"}}
"NEFT/ZERODHA BROKING LTD" -> {{"category": "Investments", "confidence": 0.97, "merchant": "Zerodha", "reason": "Zerodha is a stock broker"}}
"AMAZON PAY ICICI" -> {{"category": "Shopping", "confidence": 0.90, "merchant": "Amazon", "reason": "Amazon is an e-commerce platform"}}
"IRCTC TICKET BOOKING" -> {{"category": "Transport", "confidence": 0.99, "merchant": "IRCTC", "reason": "IRCTC handles Indian railway bookings"}}
"NETFLIX SUBSCRIPTION" -> {{"category": "Subscriptions", "confidence": 0.99, "merchant": "Netflix", "reason": "Netflix is a video streaming service"}}

Rules:
- Return ONLY a JSON object: {{"category": "...", "confidence": 0.0-1.0, "merchant": "...", "reason": "one sentence"}}
- "merchant" is the normalized merchant name (e.g., "Swiggy", "Amazon", "PhonePe")
- "confidence" is your certainty from 0.0 to 1.0
- "reason" is a brief explanation (max 10 words)
- Use "Other" with low confidence only if truly ambiguous
- No explanation, no extra text. JSON only."""

BATCH_CATEGORIZE_SYSTEM = """You are a financial transaction categorizer for an Indian personal finance app.
Classify each transaction into EXACTLY one of these categories:
{categories}

Few-shot examples:
"UPI/DR/SWIGGY INDIA" -> Dining | "IRCTC BOOKING" -> Transport | "NETFLIX" -> Subscriptions
"ZERODHA" -> Investments | "STAR HEALTH" -> Insurance | "UDEMY COURSE" -> Education

Return ONLY a JSON array. Each element:
{{"id": "...", "category": "...", "confidence": 0.0-1.0, "merchant": "...", "reason": "brief"}}
No explanation. JSON only."""


def _extract_json(raw: str) -> Any:
    """
    Robustly extract JSON from LLM response.
    Handles: clean JSON, markdown code blocks, partial JSON.
    """
    if not raw:
        return None

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to extract from markdown code block
    code_block = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try to find JSON object or array within text
    # Find first { or [ to last } or ]
    obj_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", raw)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def _has_ai_provider() -> bool:
    """Check if any AI provider is configured."""
    return any(
        [
            settings.groq_api_key,
            settings.cerebras_api_key,
            settings.gemini_api_key,
            settings.cohere_api_key,
            settings.openrouter_api_key,
        ]
    )


async def categorize_single(
    description: str,
    tx_type: str = "expense",
    user_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Categorize a single transaction using the 4-tier pipeline.

    Returns:
        {category, confidence, merchant, source, reason}
        source: "override" | "rules" | "embedding_cache" | "llm" | "fallback"
    """
    # ── Tier 1: User-specific override ─────────────────────────────────────
    if user_overrides:
        import hashlib

        key = hashlib.sha256(description.lower().strip().encode()).hexdigest()
        if key in user_overrides:
            return {
                "category": user_overrides[key],
                "confidence": 1.0,
                "merchant": extract_upi_merchant(description),
                "source": "override",
                "reason": "User manually corrected",
            }

    # ── Tier 2: Rule-based categorizer ─────────────────────────────────────
    rule_result = rule_categorize(description, tx_type)
    if rule_result != "Other":
        result = {
            "category": rule_result,
            "confidence": RULES_CONFIDENCE,
            "merchant": extract_upi_merchant(description),
            "source": "rules",
            "reason": "Matched keyword rule",
        }
        # Store successful rule matches in embedding cache for future similarity lookups
        embedding_cache.put(description, rule_result, RULES_CONFIDENCE, result["merchant"])
        return result

    # ── Tier 3: Embedding similarity cache ─────────────────────────────────
    if embedding_cache.is_available():
        sim_result = embedding_cache.find_similar(description)
        if sim_result and sim_result["confidence"] >= EMBEDDING_CONFIDENCE:
            return {
                "category": sim_result["category"],
                "confidence": sim_result["confidence"],
                "merchant": sim_result.get("merchant") or extract_upi_merchant(description),
                "source": "embedding_cache",
                "reason": f"Similar to cached transaction (sim={sim_result['similarity']:.2f})",
            }

    # ── Tier 4: LLM (only if provider available and description is ambiguous) ──
    if not _has_ai_provider():
        return {
            "category": "Other",
            "confidence": 0.1,
            "merchant": extract_upi_merchant(description),
            "source": "fallback",
            "reason": "No AI provider configured",
        }

    # Send to LLM if: it's a generic UPI OR we just have no good match
    try:
        cats = ", ".join(EXPENSE_CATEGORIES if tx_type == "expense" else CATEGORIES)
        system = CATEGORIZE_SYSTEM.format(categories=cats)
        messages = [{"role": "user", "content": f"Transaction: {description}"}]

        raw = await ai_router.generate(system, messages, task_type="categorize")
        result_data = _extract_json(raw)

        if result_data and isinstance(result_data, dict):
            category = result_data.get("category", "Other")
            if category not in CATEGORIES:
                category = "Other"
            merchant = result_data.get("merchant") or extract_upi_merchant(description)
            confidence = min(1.0, max(0.0, float(result_data.get("confidence", 0.5))))

            response = {
                "category": category,
                "confidence": confidence,
                "merchant": merchant,
                "source": "llm",
                "reason": result_data.get("reason", "LLM classification"),
            }

            # Cache result in embedding cache for future
            if category != "Other" and confidence >= 0.6:
                embedding_cache.put(description, category, confidence, merchant)

            return response
    except Exception as e:
        logger.warning("LLM categorization failed for '%s...': %s", description[:50], e)

    return {
        "category": "Other",
        "confidence": 0.1,
        "merchant": extract_upi_merchant(description),
        "source": "fallback",
        "reason": "Could not determine category",
    }


async def categorize_batch(
    transactions: list[dict],
    user_overrides: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """
    Categorize multiple transactions using the 4-tier pipeline.

    Input: [{"id": "...", "description": "...", "type": "expense"}]
    Returns: [{"id": "...", "category": "...", "confidence": float, "merchant": str, "reason": str}]
    """
    import hashlib

    results: dict[str, dict] = {}
    needs_llm: list[dict] = []

    for tx in transactions:
        tid = tx["id"]
        desc = tx["description"]
        ttype = tx.get("type", "expense")

        # Tier 1: User override
        if user_overrides:
            key = hashlib.sha256(desc.lower().strip().encode()).hexdigest()
            if key in user_overrides:
                results[tid] = {
                    "id": tid,
                    "category": user_overrides[key],
                    "confidence": 1.0,
                    "merchant": extract_upi_merchant(desc),
                    "reason": "User override",
                }
                continue

        # Tier 2: Rules
        rule_result = rule_categorize(desc, ttype)
        if rule_result != "Other":
            merchant = extract_upi_merchant(desc)
            results[tid] = {
                "id": tid,
                "category": rule_result,
                "confidence": RULES_CONFIDENCE,
                "merchant": merchant,
                "reason": "Keyword rule match",
            }
            embedding_cache.put(desc, rule_result, RULES_CONFIDENCE, merchant)
            continue

        # Tier 3: Embedding cache
        if embedding_cache.is_available():
            sim_result = embedding_cache.find_similar(desc)
            if sim_result and sim_result["confidence"] >= EMBEDDING_CONFIDENCE:
                results[tid] = {
                    "id": tid,
                    "category": sim_result["category"],
                    "confidence": sim_result["confidence"],
                    "merchant": sim_result.get("merchant") or extract_upi_merchant(desc),
                    "reason": "Embedding similarity match",
                }
                continue

        # Tier 4: Needs LLM
        needs_llm.append(tx)

    # Process LLM batch in parallel chunks
    if needs_llm and _has_ai_provider():
        chunks = [needs_llm[i : i + LLM_BATCH_SIZE] for i in range(0, len(needs_llm), LLM_BATCH_SIZE)]
        tasks = [_llm_batch_chunk(chunk) for chunk in chunks]
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

        for chunk_result in chunk_results:
            if isinstance(chunk_result, Exception):
                logger.warning("Batch LLM chunk failed: %s", chunk_result)
                continue
            for tid, data in chunk_result.items():
                results[tid] = data

    # Fill any remaining (LLM unavailable or failed)
    for tx in needs_llm:
        if tx["id"] not in results:
            results[tx["id"]] = {
                "id": tx["id"],
                "category": "Other",
                "confidence": 0.1,
                "merchant": extract_upi_merchant(tx["description"]),
                "reason": "Could not classify",
            }

    return [results[tx["id"]] for tx in transactions]


async def _llm_batch_chunk(transactions: list[dict]) -> dict[str, dict]:
    """Send a single batch chunk to the LLM and parse results."""
    cats = ", ".join(EXPENSE_CATEGORIES)
    system = BATCH_CATEGORIZE_SYSTEM.format(categories=cats)
    user_content = "\n".join(f"- id: {tx['id']}, description: {tx['description']}" for tx in transactions)
    messages = [{"role": "user", "content": user_content}]

    results = {}
    try:
        raw = await ai_router.generate(system, messages, task_type="categorize", max_tokens=LLM_BATCH_SIZE * 30)
        parsed = _extract_json(raw)

        if not isinstance(parsed, list):
            return results

        valid_ids = {tx["id"] for tx in transactions}
        tx_map = {tx["id"]: tx for tx in transactions}

        for item in parsed:
            tid = item.get("id")
            if not tid or tid not in valid_ids:
                continue
            cat = item.get("category", "Other")
            if cat not in CATEGORIES:
                cat = "Other"
            merchant = item.get("merchant") or extract_upi_merchant(tx_map[tid]["description"])
            confidence = min(1.0, max(0.0, float(item.get("confidence", 0.5))))

            results[tid] = {
                "id": tid,
                "category": cat,
                "confidence": confidence,
                "merchant": merchant,
                "reason": item.get("reason", "LLM batch"),
            }

            # Cache good results
            if cat != "Other" and confidence >= 0.6:
                embedding_cache.put(tx_map[tid]["description"], cat, confidence, merchant)

    except Exception as e:
        logger.warning("LLM batch chunk failed: %s", str(e)[:100])

    return results
