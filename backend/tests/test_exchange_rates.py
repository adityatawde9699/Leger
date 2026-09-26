import asyncio

import pytest

from app.services.exchange_rates import convert_reference_rate, validate_currency


def test_currency_validation():
    assert validate_currency("inr") == "INR"
    with pytest.raises(ValueError):
        validate_currency("XYZ")


def test_same_currency_conversion_is_deterministic():
    result = asyncio.run(convert_reference_rate("125.50", "INR", "INR"))
    assert result["converted"] == result["amount"]
    assert result["rate"] == 1
