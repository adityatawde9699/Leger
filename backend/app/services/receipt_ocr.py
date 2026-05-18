"""
Receipt OCR — extract transaction data from receipt images.
Uses PaddleOCR for text extraction and a local text LLM for semantic structuring.
"""

import base64
import json
import logging
from datetime import date
from decimal import Decimal
import asyncio

import httpx

from ..config import settings
from .categorizer import categorize

logger = logging.getLogger("ledger.receipt")

EXTRACTION_PROMPT = """Extract from this receipt text:
- merchant_name: string
- date: YYYY-MM-DD (if visible, else null)
- total_amount: number (the total/grand total)
- items: list of {name: string, price: number} (top 5 items max)
- category: one of [Dining, Groceries, Shopping, Health, Transport, Utilities, Entertainment, Subscriptions, Housing, Other]

Return ONLY valid JSON. No explanation.

RECEIPT TEXT:
{ocr_text}"""


def _paddleocr_extract(image_bytes: bytes) -> str:
    """Extract raw text from receipt image using PaddleOCR."""
    try:
        import os
        os.environ['PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT'] = '0'
        from paddleocr import PaddleOCR
        import numpy as np
        from PIL import Image
        import io
    except ImportError:
        logger.warning("Required image processing libraries (paddleocr) not available.")
        return ""

    try:
        logging.getLogger("ppocr").setLevel(logging.WARNING)
        ocr = PaddleOCR(use_angle_cls=False, lang="en")
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(pil_image)
        
        result = ocr.ocr(img_array)
        texts = []
        if result and result[0]:
            for line in result[0]:
                texts.append(line[1][0])
                
        return "\n".join(texts)
    except Exception as e:
        logger.warning("PaddleOCR extraction failed: %s", e)
        return ""


async def parse_receipt_image(image_bytes: bytes) -> dict | None:
    """
    Parse a receipt image into structured transaction data.
    Uses PaddleOCR to extract text, then a text LLM to structure it.
    """
    logger.info("Attempting PaddleOCR extraction for receipt...")
    ocr_text = await asyncio.to_thread(_paddleocr_extract, image_bytes)
    
    if not ocr_text.strip():
        logger.warning("PaddleOCR returned no text for receipt.")
        return None

    if settings.llama_enabled:
        try:
            result = await _llm_text_parse(ocr_text)
            if result:
                return result
        except Exception as e:
            logger.warning("LLM text parse failed: %s", e)

    # Fallback: No LLM configured or LLM failed
    logger.info("Receipt parsing LLM unavailable — returning basic OCR text")
    return None


async def _llm_text_parse(ocr_text: str) -> dict | None:
    """Call internal LlamaEngine with a text model (Qwen2.5) to parse OCR text."""
    prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)

    from .llama_engine import llama_engine
    try:
        output_text = await llama_engine.generate(prompt=prompt, max_tokens=300)
        if not output_text:
            return None

        # Extract JSON block if surrounded by markdown codeblocks
        import re
        json_match = re.search(r'\{.*\}', output_text.replace('\n', ' '), re.DOTALL)
        if json_match:
            raw = json_match.group(0)
        else:
            raw = output_text
            
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
            "items": data.get("items", []),
            "merchant_normalized": merchant,
            "confidence": 0.8,
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Text parse error: %s", e)
        return None
