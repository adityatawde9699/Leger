from datetime import UTC, datetime, timedelta

from app.models import AIConversation
from app.services.privacy import purge_expired_conversations, redact_sensitive_text, safe_conversation_memory

from .conftest import TEST_USER_ID, TestSession


def test_ai_text_redaction_preserves_useful_prose():
    value = "Email jane@example.com, call +91 98765 43210, account 1234 5678 9012, PAN ABCDE1234F"
    redacted = redact_sensitive_text(value)

    assert "jane@example.com" not in redacted
    assert "98765" not in redacted
    assert "1234 5678 9012" not in redacted
    assert "ABCDE1234F" not in redacted
    assert "Email" in redacted
    assert "4111111111111111" not in redact_sensitive_text("card 4111111111111111")
    assert "https://bank.example" not in redact_sensitive_text("https://bank.example/account?id=123")


def test_expired_conversations_are_deleted_for_one_user():
    db = TestSession()
    try:
        old = AIConversation(
            user_id=TEST_USER_ID,
            title="Old",
            updated_at=datetime.now(UTC) - timedelta(days=100),
        )
        current = AIConversation(user_id=TEST_USER_ID, title="Current")
        db.add_all([old, current])
        db.commit()

        assert purge_expired_conversations(db, TEST_USER_ID, 90) == 1
        remaining = db.query(AIConversation).filter(AIConversation.user_id == TEST_USER_ID).all()
        assert [item.title for item in remaining] == ["Current"]
    finally:
        db.close()


def test_provider_memory_keeps_only_explicit_user_preferences_and_goals():
    messages = [
        {"role": "user", "content": "What did I spend at the supermarket last month?"},
        {"role": "assistant", "content": "You spent a calculated amount."},
        {"role": "user", "content": "My goal is to save for an emergency fund; email me@example.com"},
    ]

    memory = safe_conversation_memory(messages)

    assert len(memory) == 1
    assert memory[0]["role"] == "user"
    assert "emergency fund" in memory[0]["content"]
    assert "me@example.com" not in memory[0]["content"]
