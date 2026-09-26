import re
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

# Patterns that indicate prompt injection attempts
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|all|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"forget\s+everything", re.IGNORECASE),
    re.compile(r"disregard\s+(all|your|previous)", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"<\|.*?\|>"),  # Llama/Qwen special tokens
    re.compile(r"\[INST\]"),  # Legacy Mistral injection pattern
    re.compile(r"###\s*system", re.IGNORECASE),
    re.compile(r"act\s+as\s+", re.IGNORECASE),
    re.compile(r"pretend\s+(you|to)\s+", re.IGNORECASE),
]

MAX_INPUT_LENGTH = 1000

_MONEY_TOKEN = re.compile(
    r"(?P<code>INR|USD|EUR|GBP|AED|SGD|CAD|AUD|JPY|CHF|CNY|HKD|₹|\$|€|£)\s*"
    r"(?P<amount>\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
_DATE_TOKEN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_UUID_TOKEN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_ENTITY_CLAIM = re.compile(
    r"\b(?:merchant|category)\s+(?:is|was|named|called|:)\s*"
    r"(?:`(?P<backtick>[^`\n]{1,80})`|\"(?P<double>[^\"\n]{1,80})\"|'(?P<single>[^'\n]{1,80})'|"
    r"(?P<bare>[A-Za-z0-9][A-Za-z0-9 &/_-]{0,79}?)(?=\s+(?:and|or)\s+|[,.;!?]|$))",
    re.IGNORECASE,
)


def _amount_key(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def validate_ai_output(
    text: str,
    financial_context: str,
    currency: str,
    allowed_entities: set[str] | None = None,
) -> dict[str, object]:
    """Reject explicit claims absent from current context.

    Entity checks intentionally cover only explicitly labeled merchant/category
    claims. Ordinary prose contains many nouns that are not financial entities;
    validating every noun would create false positives and reduce usefulness.
    """
    expected_codes = {currency.upper()}
    if currency.upper() == "INR":
        expected_codes.add("₹")
    tokens = list(_MONEY_TOKEN.finditer(text or ""))
    context_amounts = {
        key for match in _MONEY_TOKEN.finditer(financial_context or "")
        if (key := _amount_key(match.group("amount"))) is not None
    }
    unsupported: list[str] = []
    wrong_currency: list[str] = []
    for match in tokens:
        code = match.group("code").upper()
        key = _amount_key(match.group("amount"))
        if code not in expected_codes:
            wrong_currency.append(match.group(0))
        elif key is not None and key not in context_amounts:
            unsupported.append(match.group(0))
    context_dates = set(_DATE_TOKEN.findall(financial_context or ""))
    unsupported_dates = [value for value in _DATE_TOKEN.findall(text or "") if value not in context_dates]
    context_ids = {value.casefold() for value in _UUID_TOKEN.findall(financial_context or "")}
    unsupported_transaction_ids = [
        value for value in _UUID_TOKEN.findall(text or "") if value.casefold() not in context_ids
    ]
    allowed_entity_keys = {value.strip().casefold() for value in (allowed_entities or set()) if value.strip()}
    unsupported_entities = []
    if allowed_entities is not None:
        for match in _ENTITY_CLAIM.finditer(text or ""):
            entity = next(
                (match.group(name) for name in ("backtick", "double", "single", "bare") if match.group(name)),
                "",
            ).strip()
            if entity.casefold() not in allowed_entity_keys:
                unsupported_entities.append(entity)
    return {
        "valid": not unsupported and not wrong_currency and not unsupported_dates and not unsupported_transaction_ids and not unsupported_entities,
        "unsupported_amounts": unsupported,
        "wrong_currency": wrong_currency,
        "unsupported_dates": unsupported_dates,
        "unsupported_transaction_ids": unsupported_transaction_ids,
        "unsupported_entities": unsupported_entities,
    }


def sanitize_user_input(text: str) -> str:
    """
    Block prompt injection attempts and enforce length limits.
    Raises HTTP 400 if injection detected.
    """
    if len(text) > MAX_INPUT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Question too long. Maximum {MAX_INPUT_LENGTH} characters.",
        )

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            raise HTTPException(
                status_code=400,
                detail="Invalid input detected.",
            )

    return text.strip()


def build_safe_messages(
    system_prompt: str,
    financial_context: str,
    user_question: str,
    history: list[dict] | None = None,
) -> list[dict]:
    """
    Constructs messages with user input structurally isolated from system context.
    User question NEVER appears in system prompt position.
    """
    messages: list[dict] = [
        {"role": "user", "content": financial_context},
        {"role": "assistant", "content": "I have reviewed your financial data and I'm ready to help."},
    ]

    # Inject conversation history (limited to last 6 exchanges)
    if history:
        for msg in history[-12:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    # User question goes last, isolated
    messages.append({"role": "user", "content": user_question})
    return messages
