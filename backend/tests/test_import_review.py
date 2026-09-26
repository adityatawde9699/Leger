from datetime import date
from decimal import Decimal

from app.main import _apply_import_review_overrides, _statement_row_fingerprint


def test_import_review_overrides_win_over_inference_and_reject_unknown_type():
    row = {
        "date": date(2026, 9, 20),
        "type": "expense",
        "amount": Decimal("25.00"),
        "description": "CARD 1234",
        "category": "Other",
        "merchant_normalized": "AI Merchant",
    }
    fingerprint = _statement_row_fingerprint(row, "account-1")

    _apply_import_review_overrides([row], {
        fingerprint: {
            "category": "Groceries",
            "merchant_normalized": "Trusted Merchant",
            "type": "refund",
        }
    }, "account-1")

    assert row["category"] == "Groceries"
    assert row["merchant_normalized"] == "Trusted Merchant"
    assert row["type"] == "refund"

    _apply_import_review_overrides([row], {fingerprint: {"type": "delete"}}, "account-1")
    assert row["type"] == "refund"


def test_contradictory_import_inference_is_not_authoritative_without_review_override():
    row = {
        "date": date(2026, 9, 20),
        "type": "expense",
        "amount": Decimal("25.00"),
        "description": "CARD 1234",
        "category": "AI-inferred category",
        "merchant_normalized": "AI-inferred merchant",
    }
    fingerprint = _statement_row_fingerprint(row, "account-1")

    _apply_import_review_overrides([row], {fingerprint: {}}, "account-1")

    assert row["category"] == "AI-inferred category"
    assert row["merchant_normalized"] == "AI-inferred merchant"
