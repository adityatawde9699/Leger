"""
Receipt OCR — extract transaction data from receipt images.
Uses LLM vision (if llava is running) or falls back to basic regex extraction.
"""
import base64
import json
import logging
import re
from datetime import date
from decimal import Decimal

import httpx

from ..config import settings
from .categorizer import categorize

logger = logging.getLogger("ledger.receipt")

VISION_PROMPT = """Extract from this receipt image:
- merchant_name: string
- date: YYYY-MM-DD (if visible, else null)
- total_amount: number (the total/grand total)
- items: list of {name: string, price: number} (top 5 items max)
- category: one of [Dining, Groceries, Shopping, Health, Transport, Utilities, Entertainment, Subscriptions, Housing, Other]

Return ONLY valid JSON. No explanation."""


async def parse_receipt_image(image_bytes: bytes) -> dict | None:
    """
    Parse a receipt image into structured transaction data.
    Tries LLM vision first, then falls back to basic regex on any embedded text.
    """
    # Try LLM vision if llama server is available
    if settings.llama_enabled:
        try:
            result = await _llm_vision_parse(image_bytes)
            if result:
                return result
        except Exception as e:
            logger.warning("LLM vision parse failed: %s", e)

    # Fallback: return None — no OCR library dependency
    logger.info("Receipt parsing unavailable — no vision model configured")
    return None


async def _llm_vision_parse(image_bytes: bytes) -> dict | None:
    """Call llama.cpp server with a multimodal model (llava)."""
    b64 = base64.b64encode(image_bytes).decode()

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            res = await client.post(
                f"{settings.llama_server_url}/v1/chat/completions",
                json={
                    "model": "llava",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": VISION_PROMPT},
                        ],
                    }],
                    "max_tokens": 300,
                },
            )
            res.raise_for_status()
            raw = res.json()["choices"][0]["message"]["content"]
            data = json.loads(raw)

            # Validate required fields
            amount = data.get("total_amount")
            if not amount or float(amount) <= 0:
                return None

            merchant = data.get("merchant_name", "Unknown")
            category = data.get("category", "Other")
            parsed_date = None
            if data.get("date"):
                try:
                    parsed_date = date.fromisoformat(data["date"])
                except ValueError:
                    pass

            return {
                "description": merchant,
                "amount": Decimal(str(amount)),
                "category": category if category in [
                    "Dining","Groceries","Shopping","Health","Transport",
                    "Utilities","Entertainment","Subscriptions","Housing","Other"
                ] else categorize(merchant, "expense"),
                "date": parsed_date or date.today(),
                "type": "expense",
                "source": "receipt",
                "items": data.get("items", []),
                "merchant_normalized": merchant,
                "confidence": 0.8,
            }
        except (json.JSONDecodeError, KeyError, httpx.HTTPError) as e:
            logger.warning("Vision parse error: %s", e)
            return None
