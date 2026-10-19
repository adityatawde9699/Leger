import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import settings
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


def test_parse_receipt_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    result = asyncio.run(parse_receipt_image(b"\xff\xd8\xfffake"))
    assert result is None


def test_parse_receipt_parses_json_and_formats_currency(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-fake-key")

    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "merchant_name": "Cafe Coffee Day",
        "date": "2026-09-15",
        "total_amount": "₹350.50",
        "category": "Dining",
        "items": [{"name": "Cappuccino", "price": 180}],
    })

    mock_model = MagicMock()
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
        with patch("google.generativeai.configure"):
            result = asyncio.run(parse_receipt_image(b"\x89PNG\r\n\x1a\nfake"))

    assert result is not None
    assert result["description"] == "Cafe Coffee Day"
    assert result["amount"] == Decimal("350.50")
    assert result["category"] == "Dining"
    assert str(result["date"]) == "2026-09-15"
    assert result["source"] == "receipt"


def test_parse_receipt_handles_markdown_wrapped_json(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-fake-key")

    mock_response = MagicMock()
    mock_response.text = """```json
{
  "merchant_name": "Supermarket",
  "total_amount": "45.00",
  "category": "Groceries"
}
```"""

    mock_model = MagicMock()
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
        with patch("google.generativeai.configure"):
            result = asyncio.run(parse_receipt_image(b"\xff\xd8\xfffake"))

    assert result is not None
    assert result["description"] == "Supermarket"
    assert result["amount"] == Decimal("45.00")
    assert result["category"] == "Groceries"
