"""One transaction per (user, source, source_ref): enforced by the database and handled by every writer."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

import app.routers.transactions as transactions_router
import app.workers.imports as worker
from app.models import Transaction, User

from .conftest import AUTH_HEADER, TEST_USER_ID, TestSession

SMS = "Rs.450.00 debited from A/c XX1234 on 05-03-26 to VPA zomato@upi. Ref 612345678901"


def _tx(source_ref, *, user_id=TEST_USER_ID, source="statement", tx_id=None):
    return Transaction(id=tx_id, user_id=user_id, date=date(2026, 3, 1), type="expense", category="Food",
                       amount=Decimal("10.00"), description="Row", source=source, source_ref=source_ref)


def test_database_rejects_a_second_transaction_with_the_same_identity():
    with TestSession() as db:
        db.add(User(id="other-user", email="other@ledger.local"))
        db.add_all([
            _tx("fp-1"),
            _tx("fp-1", source="sms"),           # different source
            _tx("fp-1", user_id="other-user"),   # different user
            _tx(None), _tx(None),                # no external identity
            _tx("split:group"), _tx("split:group"),  # lines of one split share their group ref
        ])
        db.commit()
        db.add(_tx("fp-1"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_sms_batch_with_a_repeated_message_imports_it_once(client):
    response = client.post("/imports/sms", json={"messages": [SMS, SMS]}, headers=AUTH_HEADER)
    again = client.post("/imports/sms", json={"messages": [SMS]}, headers=AUTH_HEADER)

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert again.json() == []
    with TestSession() as db:
        assert db.query(Transaction).filter_by(source="sms").count() == 1


def test_offline_replay_that_loses_the_race_returns_the_stored_transaction(client, monkeypatch):
    payload = {"date": "2026-03-01", "type": "expense", "category": "Food", "amount": "25.00",
               "description": "Offline chai", "source": "cash", "source_ref": "offline:3b1f"}
    first = client.post("/transactions", json=payload, headers=AUTH_HEADER).json()

    # Simulate the race: the pre-insert lookup misses the row a concurrent request stored.
    real_lookup = transactions_router._existing_offline_transaction
    calls = []

    def lookup_misses_first_time(db, user_id, incoming):
        calls.append(1)
        return None if len(calls) == 1 else real_lookup(db, user_id, incoming)

    monkeypatch.setattr(transactions_router, "_existing_offline_transaction", lookup_misses_first_time)
    replay = client.post("/transactions", json=payload, headers=AUTH_HEADER)

    assert replay.status_code == 201
    assert replay.json()["id"] == first["id"]
    with TestSession() as db:
        assert db.query(Transaction).filter_by(source_ref="offline:3b1f").count() == 1


def test_editing_a_transaction_onto_an_existing_identity_is_a_conflict(client):
    with TestSession() as db:
        db.add_all([_tx("fp-a", tx_id="tx-a"), _tx("fp-b", tx_id="tx-b")])
        db.commit()

    response = client.put("/transactions/tx-b", json={
        "date": "2026-03-01", "type": "expense", "category": "Food", "amount": "10.00",
        "description": "Row", "source": "statement", "source_ref": "fp-a",
    }, headers=AUTH_HEADER)

    assert response.status_code == 409
    assert "fp-a" not in response.text


def test_import_batch_skips_only_rows_another_import_already_stored():
    with TestSession() as db:
        db.add(_tx("fp-2"))
        db.commit()
        saved = worker._insert_import_batch(db, [_tx("fp-1"), _tx("fp-2"), _tx("fp-3")])
        db.commit()

        assert saved == 2
        refs = sorted(ref for (ref,) in db.query(Transaction.source_ref).all())
    assert refs == ["fp-1", "fp-2", "fp-3"]
