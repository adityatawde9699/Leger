"""Format amounts for explanations without changing their stored value."""

from decimal import Decimal


def currency_prefix(currency: str = "INR") -> str:
    return "₹" if currency == "INR" else f"{currency} "


def format_amount(value: Decimal | float | int | str, currency: str = "INR") -> str:
    return f"{currency_prefix(currency)}{Decimal(str(value)):,.2f}"
