import hashlib
import re
from datetime import date
from decimal import Decimal

from .categorizer import categorize

# ── Patterns ───────────────────────────────────────────────────────────────────

AMOUNT_RE = re.compile(
    r"(?:rs\.?|inr|₹)\s*([0-9,]+(?:\.[0-9]{1,2})?)", re.IGNORECASE
)

MERCHANT_PATTERNS = [
    re.compile(
        r"(?:to|at|for)\s+([A-Z0-9 .&_\-]{2,40}?)(?:\s+via|\s+on|\s+ref|\s+upi|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:from)\s+([A-Z0-9 .&_\-]{2,40}?)(?:\s+via|\s+on|\s+ref|\s+upi|$)",
        re.IGNORECASE,
    ),
]

TRIGGER_WORDS = {"debited", "credited", "spent", "received", "paid", "deducted", "transferred"}


def _stable_hash(text: str) -> str:
    """Cryptographically stable dedup key — safe across processes and Python versions."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_sms(message: str, fallback_date: date | None = None) -> dict | None:
    lower = message.lower()

    # Must contain at least one trigger word
    if not any(word in lower for word in TRIGGER_WORDS):
        return None

    # Must contain an amount
    amount_match = AMOUNT_RE.search(message)
    if not amount_match:
        return None

    # Determine transaction direction
    tx_type = "income" if any(w in lower for w in ("credited", "received")) else "expense"

    # Extract merchant
    merchant = "UPI transaction"
    for pattern in MERCHANT_PATTERNS:
        match = pattern.search(message)
        if match:
            merchant = " ".join(match.group(1).split()).strip(" .-")
            if merchant:
                break

    amount_str = amount_match.group(1).replace(",", "")
    try:
        amount = Decimal(amount_str)
    except Exception:
        return None

    if amount <= 0:
        return None

    return {
        "date": fallback_date or date.today(),
        "type": tx_type,
        "amount": amount,
        "description": merchant,
        "category": categorize(merchant, tx_type),
        "source": "sms",
        # Stable SHA-256 hash — safe across processes/Python versions
        "source_ref": _stable_hash(message),
    }
