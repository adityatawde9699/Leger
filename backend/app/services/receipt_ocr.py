"""
Receipt OCR — extract transaction data from receipt images.
Uses Google Gemini Vision capabilities to extract and structure data in one step.
"""

import json
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from ..config import settings
from .categorizer import categorize

logger = logging.getLogger("ledger.receipt")

EXTRACTION_PROMPT = """Extract the following information from this receipt image:
- merchant_name: string
- date: YYYY-MM-DD (if visible, else null)
- total_amount: number (the total/grand total)
- items: list of {name: string, price: number} (top 5 items max)
- category: one of [Dining, Groceries, Shopping, Health, Transport, Utilities, Entertainment, Subscriptions, Housing, Other]

Return ONLY valid JSON. No explanation."""


def _detect_image_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _clean_amount(val) -> Decimal | None:
    if val is None:
        return None
    raw = str(val).replace(",", "").strip()
    is_negative = raw.startswith("-") or ("(" in raw and ")" in raw)
    cleaned = re.sub(r"[^\d.]", "", raw)
    if not cleaned:
        return None
    try:
        dec = Decimal(cleaned)
        if is_negative or dec <= 0:
            return None
        return dec
    except InvalidOperation:
        return None


async def parse_receipt_image(image_bytes: bytes) -> dict | None:
    """
    Parse a receipt image into structured transaction data.
    Uses Gemini Vision capabilities.
    """
    if not settings.gemini_api_key:
        logger.warning("No Gemini API key found. Cannot parse receipt image.")
        return None

    logger.info("Sending receipt image to Gemini for extraction...")

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)

        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            generation_config={"response_mime_type": "application/json"},
        )

        mime_type = _detect_image_mime(image_bytes)
        image_part = {"mime_type": mime_type, "data": image_bytes}

        response = await model.generate_content_async([image_part, EXTRACTION_PROMPT])
        output_text = getattr(response, "text", "") or ""

        # Extract JSON block if surrounded by markdown codeblocks or plain json
        try:
            parsed_data = json.loads(output_text.strip())
        except json.JSONDecodeError:
            json_match = re.search(r"\{[\s\S]*\}", output_text)
            if json_match:
                parsed_data = json.loads(json_match.group(0))
            else:
                logger.warning("Gemini returned unparseable non-JSON text: %s", output_text[:200])
                return None

        # Validate and clean amount (handles strings, currencies, commas)
        amount_dec = _clean_amount(parsed_data.get("total_amount"))
        if not amount_dec:
            logger.warning("No valid total_amount found in parsed receipt data: %s", parsed_data.get("total_amount"))
            return None

        merchant = str(parsed_data.get("merchant_name") or "Unknown").strip() or "Unknown"
        category = parsed_data.get("category", "Other")
        parsed_date = None
        if parsed_data.get("date"):
            try:
                parsed_date = date.fromisoformat(str(parsed_data["date"]).strip())
            except ValueError:
                pass

        valid_categories = [
            "Dining",
            "Groceries",
            "Shopping",
            "Health",
            "Transport",
            "Utilities",
            "Entertainment",
            "Subscriptions",
            "Housing",
            "Other",
        ]

        return {
            "description": merchant,
            "amount": amount_dec,
            "category": category if category in valid_categories else categorize(merchant, "expense"),
            "date": parsed_date or date.today(),
            "type": "expense",
            "source": "receipt",
            "items": parsed_data.get("items", []),
            "merchant_normalized": merchant,
            "confidence": 0.8,
        }

    except Exception as e:
        logger.warning("Gemini extraction failed or returned invalid JSON: %s: %s", type(e).__name__, e, exc_info=True)
        return None
