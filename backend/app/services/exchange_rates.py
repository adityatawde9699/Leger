"""Reference-rate currency conversion kept separate from ledger balances."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx

SUPPORTED_CURRENCIES = {
    "AUD", "BGN", "BRL", "CAD", "CHF", "CNY", "CZK", "DKK", "EUR", "GBP",
    "AED", "HKD", "HUF", "IDR", "ILS", "INR", "ISK", "JPY", "KRW", "MXN", "MYR",
    "NOK", "NZD", "PHP", "PLN", "RON", "SEK", "SGD", "THB", "TRY", "USD", "ZAR",
}


def validate_currency(code: str) -> str:
    code = (code or "").upper()
    if code not in SUPPORTED_CURRENCIES:
        raise ValueError("Unsupported currency code")
    return code


async def convert_reference_rate(amount: str | Decimal, base: str, quote: str) -> dict:
    base = validate_currency(base)
    quote = validate_currency(quote)
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Amount must be a valid number") from exc
    if value < 0 or value > Decimal("1000000000000"):
        raise ValueError("Amount must be between 0 and 1,000,000,000,000")
    if base == quote:
        return {"base": base, "quote": quote, "rate": Decimal("1"), "amount": value, "converted": value, "date": None}
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"https://api.frankfurter.dev/v2/rate/{base.lower()}/{quote.lower()}")
        response.raise_for_status()
        data = response.json()
    rate = Decimal(str(data["rate"]))
    return {
        "base": base,
        "quote": quote,
        "rate": rate,
        "amount": value,
        "converted": (value * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "date": data.get("date"),
    }


async def get_reference_rates(base: str) -> dict:
    """Return all available reference rates from one source currency."""
    base = validate_currency(base)
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"https://api.frankfurter.dev/v2/rates?base={base}")
        response.raise_for_status()
        data = response.json()
    rates = {base: Decimal("1")}
    for item in data:
        quote = item.get("currency") or item.get("quote") if isinstance(item, dict) else None
        if quote and item.get("rate") is not None:
            rates[quote.upper()] = Decimal(str(item["rate"]))
    return {"base": base, "rates": rates, "date": data[0].get("date") if data else None}
