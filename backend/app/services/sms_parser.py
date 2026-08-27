import hashlib
import re
from datetime import date, datetime
from decimal import Decimal

from .categorizer import categorize

# ── Patterns ───────────────────────────────────────────────────────────────────

# Matches currency-prefixed amounts: Rs. 50, INR 1,234.56, ₹50
AMOUNT_PREFIX_RE = re.compile(
    r"(?:rs\.?|inr|₹)\s*([0-9,]+(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)

# Matches bare amounts after "debited by", "credited by", "for", "of", etc.
AMOUNT_BARE_RE = re.compile(
    r"(?:debited\s+by|credited\s+by|for|of)\s+([0-9,]+(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)

MERCHANT_PATTERNS = [
    # "trf to MERCHANT Refno" — catches SBI UPI style
    re.compile(
        r"trf\s+to\s+([A-Z0-9 .&_\-]{2,50}?)(?:\s+refno|\s+ref|\s+upi|$)",
        re.IGNORECASE,
    ),
    # "to MERCHANT via/on/ref/upi"
    re.compile(
        r"(?:to|at|for)\s+([A-Z0-9 .&_\-]{2,40}?)(?:\s+via|\s+on|\s+ref|\s+upi|$)",
        re.IGNORECASE,
    ),
    # "from MERCHANT via/on/ref/upi"
    re.compile(
        r"(?:from)\s+([A-Z0-9 .&_\-]{2,40}?)(?:\s+via|\s+on|\s+ref|\s+upi|$)",
        re.IGNORECASE,
    ),
]

# Date patterns found in Indian bank SMS
# e.g. "17May26", "17-05-26", "17/05/2026", "17-May-2026"
DATE_PATTERNS = [
    (re.compile(r"\b(\d{2})([A-Za-z]{3})(\d{2,4})\b"), "%d%b%y"),  # 17May26 / 17May2026
    (re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b"), "%d-%m-%Y"),  # 17-05-2026
    (re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b"), "%d/%m/%Y"),  # 17/05/2026
    (re.compile(r"\b(\d{2})-([A-Za-z]{3})-(\d{4})\b"), "%d-%b-%Y"),  # 17-May-2026
]

TRIGGER_WORDS = {"debited", "credited", "spent", "received", "paid", "deducted", "transferred"}


def _stable_hash(text: str) -> str:
    """Cryptographically stable dedup key — safe across processes and Python versions."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_amount(message: str) -> Decimal | None:
    """Try currency-prefixed pattern first, then bare 'by/for/of' pattern."""
    m = AMOUNT_PREFIX_RE.search(message)
    if m:
        amount_str = m.group(1).replace(",", "")
        try:
            return Decimal(amount_str)
        except Exception:
            pass

    m = AMOUNT_BARE_RE.search(message)
    if m:
        amount_str = m.group(1).replace(",", "")
        try:
            return Decimal(amount_str)
        except Exception:
            pass

    return None


def _extract_date(message: str) -> date | None:
    """Try to parse a date from the SMS text."""
    for pattern, fmt in DATE_PATTERNS:
        m = pattern.search(message)
        if m:
            # Reconstruct date string from groups
            raw = "".join(m.groups())
            # Handle 2-digit year: "17May26" → fmt %d%b%y
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                # Fallback: try %y suffix as 2-digit year
                try:
                    return datetime.strptime(raw, fmt.replace("%Y", "%y")).date()
                except ValueError:
                    continue
    return None


def parse_sms(message: str, fallback_date: date | None = None) -> dict | None:
    lower = message.lower()

    # Must contain at least one trigger word
    if not any(word in lower for word in TRIGGER_WORDS):
        return None

    # Must contain an amount
    amount = _extract_amount(message)
    if amount is None or amount <= 0:
        return None

    # Determine transaction direction
    tx_type = "income" if any(w in lower for w in ("credited", "received")) else "expense"

    # Extract merchant
    merchant = "UPI transaction"
    for pattern in MERCHANT_PATTERNS:
        match = pattern.search(message)
        if match:
            candidate = " ".join(match.group(1).split()).strip(" .-")
            if candidate:
                merchant = candidate
                break

    # Extract date from the SMS itself; fall back to today
    tx_date = _extract_date(message) or fallback_date or date.today()

    return {
        "date": tx_date,
        "type": tx_type,
        "amount": amount,
        "description": merchant,
        "category": categorize(merchant, tx_type),
        "source": "sms",
        "source_ref": _stable_hash(message),
    }
