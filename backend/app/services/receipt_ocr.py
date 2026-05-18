"""
Receipt OCR — extract transaction data from receipt images.
Uses Google Gemini 1.5 Flash Vision capabilities to extract and structure data in one step.
"""

import json
import logging
from datetime import date
from decimal import Decimal
import asyncio
import re

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

async def parse_receipt_image(image_bytes: bytes) -> dict | None:
    """
    Parse a receipt image into structured transaction data.
    Uses Gemini 1.5 Flash Vision capabilities.
    """
    if not settings.gemini_api_key:
        logger.warning("No Gemini API key found. Cannot parse receipt image.")
        return None

    logger.info("Sending receipt image to Gemini for extraction...")
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        image_part = {
            "mime_type": "image/jpeg",
            "data": image_bytes
        }
        
        response = await model.generate_content_async([image_part, EXTRACTION_PROMPT])
        output_text = response.text
        
        # Extract JSON block if surrounded by markdown codeblocks
        json_match = re.search(r'\{.*\}', output_text.replace('\n', ' '), re.DOTALL)
        if json_match:
            raw = json_match.group(0)
        else:
            raw = output_text
            
        parsed_data = json.loads(raw)

        # Validate required fields
        amount = parsed_data.get("total_amount")
        if not amount or float(amount) <= 0:
            return None

        merchant = parsed_data.get("merchant_name", "Unknown")
        category = parsed_data.get("category", "Other")
        parsed_date = None
        if parsed_data.get("date"):
            try:
                parsed_date = date.fromisoformat(parsed_data["date"])
            except ValueError:
                pass

        return {
            "description": merchant,
            "amount": Decimal(str(amount)),
            "category": category
            if category
            in [
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
            else categorize(merchant, "expense"),
            "date": parsed_date or date.today(),
            "type": "expense",
            "source": "receipt",
            "items": parsed_data.get("items", []),
            "merchant_normalized": merchant,
            "confidence": 0.8,
        }
        
    except Exception as e:
        logger.warning("Gemini extraction failed or returned invalid JSON: %s", e)
        return None
