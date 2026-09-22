from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.insights import recurring_payments


def tx(identifier, day, amount):
    return SimpleNamespace(
        id=identifier,
        date=date.fromisoformat(day),
        type="expense",
        amount=Decimal(amount),
        category="Subscriptions",
        description="Streaming service",
        merchant_normalized="StreamCo",
    )


def test_recurring_payment_reports_cadence_confidence_and_evidence():
    payments = recurring_payments([
        tx("t1", "2026-01-01", "499"),
        tx("t2", "2026-02-01", "499"),
        tx("t3", "2026-03-01", "549"),
    ])

    assert len(payments) == 1
    assert payments[0]["cadence"] == "monthly"
    assert payments[0]["minimum_amount"] == Decimal("499")
    assert payments[0]["maximum_amount"] == Decimal("549")
    assert 0 < payments[0]["confidence"] <= 1
    assert {row["transaction_id"] for row in payments[0]["evidence"]} == {"t1", "t2", "t3"}
