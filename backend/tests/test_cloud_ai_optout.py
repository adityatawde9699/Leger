"""
Regression tests: users who turn cloud AI off must never have data sent to an LLM provider.

Covers categorization (single, batch, recategorize) and bill negotiation, which previously
only checked whether a provider key existed.
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models import Transaction, User
from app.services import auto_categorizer, bill_negotiator
from app.services.ai_router import ai_router

from .conftest import AUTH_HEADER, TEST_USER_ID, TestSession


@pytest.fixture()
def provider_calls(monkeypatch):
    """Pretend a provider is configured and record every call that would leave the server."""
    calls = []

    async def fake_generate(*args, **kwargs):
        calls.append(kwargs.get("task_type"))
        return '{"category": "Shopping", "confidence": 0.9, "merchant": "Acme", "reason": "test"}'

    monkeypatch.setattr(auto_categorizer, "_has_ai_provider", lambda: True)
    monkeypatch.setattr(ai_router, "generate", fake_generate)
    return calls


def _set_cloud_ai(enabled: bool) -> None:
    db = TestSession()
    try:
        db.get(User, TEST_USER_ID).cloud_ai_enabled = enabled
        db.commit()
    finally:
        db.close()


def _unmatched_description() -> str:
    # Unique per test so the process-wide category cache cannot answer it.
    # Digits only: a random hex suffix can spell a rule keyword such as "cafe" or "fee".
    return f"zqx ref {uuid4().int}"


def test_categorize_endpoints_skip_llm_when_cloud_ai_disabled(client, provider_calls):
    _set_cloud_ai(False)

    single = client.post("/categorize", json={"description": _unmatched_description()}, headers=AUTH_HEADER)
    batch = client.post(
        "/categorize/batch",
        json={"transactions": [{"id": "1", "description": _unmatched_description(), "type": "expense"}]},
        headers=AUTH_HEADER,
    )

    assert single.status_code == 200
    assert single.json()["source"] == "fallback"
    assert batch.status_code == 200
    assert provider_calls == []


def test_recategorize_skips_llm_when_cloud_ai_disabled(client, provider_calls):
    _set_cloud_ai(False)
    db = TestSession()
    try:
        db.add(Transaction(
            user_id=TEST_USER_ID, date=date.today(), type="expense", category="Other",
            amount=Decimal("120.00"), description=_unmatched_description(), source="cash",
        ))
        db.commit()
    finally:
        db.close()

    response = client.post("/categorize/recategorize", headers=AUTH_HEADER)

    assert response.status_code == 200
    assert provider_calls == []


def test_categorize_uses_llm_when_cloud_ai_enabled(client, provider_calls):
    _set_cloud_ai(True)

    response = client.post("/categorize", json={"description": _unmatched_description()}, headers=AUTH_HEADER)

    assert response.status_code == 200
    assert response.json()["source"] == "llm"
    assert provider_calls == ["categorize"]


def test_service_defaults_never_call_llm(provider_calls):
    """A caller that forgets the flag must fall back to rules, not leak data."""
    single = asyncio.run(auto_categorizer.categorize_single(_unmatched_description()))
    asyncio.run(auto_categorizer.categorize_batch([{"id": "1", "description": _unmatched_description()}]))

    assert single["source"] == "fallback"
    assert provider_calls == []


def test_bill_negotiator_skips_llm_when_cloud_ai_disabled(client, monkeypatch):
    calls = []

    async def fake_generate(*args, **kwargs):
        calls.append(kwargs.get("task_type"))
        return "[]"

    monkeypatch.setattr(bill_negotiator.ai_router, "generate", fake_generate)
    _set_cloud_ai(False)
    db = TestSession()
    try:
        for months_ago in range(4):
            db.add(Transaction(
                user_id=TEST_USER_ID, date=date.today() - timedelta(days=30 * months_ago), type="expense",
                category="Subscriptions", amount=Decimal("649.00"), description="Netflix subscription",
                merchant_normalized="Netflix", source="bank",
            ))
        db.commit()
    finally:
        db.close()

    response = client.get("/bills/negotiate", headers=AUTH_HEADER)

    assert response.status_code == 200
    assert calls == []
    assert asyncio.run(bill_negotiator.analyze_bills([{"merchant": "Netflix", "average_amount": 649}])) is not None
    assert calls == []
