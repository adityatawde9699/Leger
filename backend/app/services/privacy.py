"""Small, deterministic privacy controls for AI-bound text."""

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from ..models import AIConversation

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){9,14}\d(?!\d)")
_LONG_IDENTIFIER = re.compile(r"(?<![\d.])(?:\d[ -]?){12,19}(?![\d.])")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[A-Z0-9]{3,5}[ -]?){2,7}[A-Z0-9]{1,4}\b", re.IGNORECASE)
_BANK_ACCOUNT = re.compile(r"(?<!\d)\d{8,18}(?!\d)")
_URL_QUERY = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_PREFERENCE_MEMORY = re.compile(
    r"\b(prefer|preference|goal|target|save for|saving for|risk|pay cycle|income pattern|remind me|household)\b",
    re.IGNORECASE,
)


def redact_sensitive_text(value: str) -> str:
    """Remove common contact/account identifiers while retaining useful prose."""
    text = _EMAIL.sub("[redacted email]", value)
    text = _PAN.sub("[redacted tax identifier]", text)
    text = _IBAN.sub("[redacted bank identifier]", text)
    text = _URL_QUERY.sub("[redacted url]", text)
    text = _LONG_IDENTIFIER.sub("[redacted account identifier]", text)
    text = _BANK_ACCOUNT.sub("[redacted bank account]", text)
    return _PHONE.sub("[redacted phone]", text)


def safe_conversation_memory(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep only explicit user preference/goal statements for provider memory."""
    retained = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = redact_sensitive_text(str(message.get("content") or "")).strip()
        if content and _PREFERENCE_MEMORY.search(content):
            retained.append({"role": "user", "content": content[:500]})
    return retained[-4:]


def purge_expired_conversations(db: Session, user_id: str, retention_days: int) -> int:
    """Delete old conversation trees for one user and return the count removed."""
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    conversations = db.query(AIConversation).filter(
        AIConversation.user_id == user_id,
        AIConversation.updated_at < cutoff,
    ).all()
    for conversation in conversations:
        db.delete(conversation)
    if conversations:
        db.commit()
    return len(conversations)
