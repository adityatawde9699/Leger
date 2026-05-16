import re
from fastapi import HTTPException

# Patterns that indicate prompt injection attempts
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|all|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"forget\s+everything", re.IGNORECASE),
    re.compile(r"disregard\s+(all|your|previous)", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"<\|.*?\|>"),          # Llama special tokens
    re.compile(r"\[INST\]"),           # Mistral injection pattern
    re.compile(r"###\s*system", re.IGNORECASE),
    re.compile(r"act\s+as\s+", re.IGNORECASE),
    re.compile(r"pretend\s+(you|to)\s+", re.IGNORECASE),
]

MAX_INPUT_LENGTH = 1000


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
