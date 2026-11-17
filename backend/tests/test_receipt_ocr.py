import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.services import ai_router as ai_router_module
from app.services.receipt_ocr import _clean_amount, _detect_image_mime, parse_receipt_image


def test_detect_image_mime():
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00"
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    webp_bytes = b"RIFF\x00\x00\x00\x00WEBPVP8 "
    other_bytes = b"unknown"

    assert _detect_image_mime(png_bytes) == "image/png"
    assert _detect_image_mime(jpeg_bytes) == "image/jpeg"
    assert _detect_image_mime(webp_bytes) == "image/webp"
    assert _detect_image_mime(other_bytes) == "image/jpeg"


def test_clean_amount():
    assert _clean_amount("12.50") == Decimal("12.50")
    assert _clean_amount("$12.50") == Decimal("12.50")
    assert _clean_amount("₹1,250.75") == Decimal("1250.75")
    assert _clean_amount("1,000") == Decimal("1000")
    assert _clean_amount(45.99) == Decimal("45.99")
    assert _clean_amount(100) == Decimal("100")
    assert _clean_amount("0") is None
    assert _clean_amount("-15.00") is None
    assert _clean_amount("free") is None
    assert _clean_amount(None) is None


@pytest.fixture()
def gemini(monkeypatch):
    """A configured Gemini provider whose google-genai client is a mock."""
    monkeypatch.setattr(settings, "gemini_api_key", "test-fake-key")
    monkeypatch.setattr(settings, "ai_provider_allowlist", "")
    monkeypatch.setattr(settings, "ai_task_provider_policy", "")
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock()
    monkeypatch.setattr(ai_router_module, "_gemini_client", lambda: client)
    return client.aio.models.generate_content


def _reply(text):
    response = MagicMock()
    response.text = text
    return response


def test_parse_receipt_returns_none_without_a_file_capable_provider(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    result = asyncio.run(parse_receipt_image(b"\xff\xd8\xfffake"))
    assert result is None


def test_parse_receipt_parses_json_and_formats_currency(gemini):
    gemini.return_value = _reply(json.dumps({
        "merchant_name": "Cafe Coffee Day",
        "date": "2026-09-15",
        "total_amount": "₹350.50",
        "category": "Dining",
        "items": [{"name": "Cappuccino", "price": 180}],
    }))

    result = asyncio.run(parse_receipt_image(b"\x89PNG\r\n\x1a\nfake"))

    assert result is not None
    assert result["description"] == "Cafe Coffee Day"
    assert result["amount"] == Decimal("350.50")
    assert result["category"] == "Dining"
    assert str(result["date"]) == "2026-09-15"
    assert result["source"] == "receipt"
    request = gemini.call_args.kwargs
    assert request["model"] == settings.gemini_model
    image, prompt = request["contents"]
    assert image.inline_data.mime_type == "image/png"
    assert image.inline_data.data == b"\x89PNG\r\n\x1a\nfake"
    assert "receipt" in prompt
    assert request["config"].response_mime_type == "application/json"


def test_parse_receipt_handles_markdown_wrapped_json(gemini):
    gemini.return_value = _reply("""```json
{
  "merchant_name": "Supermarket",
  "total_amount": "45.00",
  "category": "Groceries"
}
```""")

    result = asyncio.run(parse_receipt_image(b"\xff\xd8\xfffake"))

    assert result is not None
    assert result["description"] == "Supermarket"
    assert result["amount"] == Decimal("45.00")
    assert result["category"] == "Groceries"


def test_parse_receipt_returns_none_when_the_provider_fails(gemini):
    gemini.side_effect = RuntimeError("upstream error")

    assert asyncio.run(parse_receipt_image(b"\xff\xd8\xfffake")) is None


def test_scanned_pdf_extraction_goes_through_the_router(gemini):
    from app.services import statements

    gemini.return_value = _reply('{"transactions": []}')

    assert asyncio.run(statements._gemini_parse_pdf(b"%PDF-1.4 scanned")) == '{"transactions": []}'
    request = gemini.call_args.kwargs
    pdf, prompt = request["contents"]
    assert pdf.inline_data.mime_type == "application/pdf"
    assert "bank statement" in prompt
    assert request["config"].max_output_tokens == ai_router_module.TASK_TOKENS["statement_ocr"]
