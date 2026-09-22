from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.advisor_facts import deterministic_answer


def tx(identifier, day, tx_type, amount, category, description):
    return SimpleNamespace(
        id=identifier,
        date=date.fromisoformat(day),
        type=tx_type,
        amount=Decimal(amount),
        category=category,
        description=description,
        merchant_normalized=None,
        created_at=None,
    )


def test_direct_fact_answer_has_math_and_evidence():
    result = deterministic_answer(
        "How much did I spend on Dining?",
        [
            tx("t1", "2026-01-02", "expense", "1000", "Dining", "Dinner"),
            tx("t2", "2026-01-03", "refund", "200", "Dining", "Refund"),
            tx("t3", "2026-01-04", "transfer", "5000", "Transfers", "Move money"),
        ],
        [],
    )
    assert result["answer_type"] == "deterministic"
    assert "₹800.00" in result["answer"]
    assert {row["transaction_id"] for row in result["evidence"]} == {"t1", "t2"}


def test_non_factual_question_is_left_for_ai():
    assert deterministic_answer("How can I feel less stressed about money?", [], []) is None


def test_comparison_question_uses_equal_windows_and_evidence():
    result = deterministic_answer(
        "Did my spending increase compared with the previous period?",
        [
            tx("old", "2026-01-05", "expense", "100", "Food", "Old"),
            tx("new", "2026-02-05", "expense", "150", "Food", "New"),
        ],
        [],
    )
    assert result["answer_type"] == "deterministic"
    assert "increased" in result["answer"]
    assert {item["transaction_id"] for item in result["evidence"]} == {"old", "new"}
