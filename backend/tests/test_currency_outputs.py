import asyncio
import json
from datetime import date
from decimal import Decimal

from app.models import Budget, Transaction
from app.services.anomaly_detector import detect_anomalies
from app.services.insights import build_advisor_context
from app.services.proactive_insights import generate_proactive_insights

from .conftest import AUTH_HEADER, TEST_USER_ID, TestSession


def _usd_ledger(client):
    assert client.put(
        "/profile", json={"currency_preference": "USD", "region": "US"}, headers=AUTH_HEADER
    ).status_code == 200
    for kind, amount in (("expense", "10.25"), ("refund", "2.25")):
        response = client.post(
            "/transactions",
            json={
                "date": date.today().isoformat(),
                "type": kind,
                "category": "Dining",
                "amount": amount,
                "description": "Lunch",
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 201


def test_usd_summary_and_factual_advisor_do_not_relabel_money(client):
    _usd_ledger(client)
    db = TestSession()
    try:
        transactions = db.query(Transaction).filter(Transaction.user_id == TEST_USER_ID).all()
        context = build_advisor_context(transactions, [], currency="USD")
    finally:
        db.close()
    assert "Currency: USD" in context
    assert "USD 8.00" in context
    assert "Ledger-calculated facts" in context
    assert '"currency": "USD"' in context
    assert "₹" not in context

    summary = client.get("/summary?range=all", headers=AUTH_HEADER)
    assert summary.status_code == 200
    assert all("₹" not in insight for insight in summary.json()["insights"])

    answer = client.post(
        "/advisor/stream",
        json={"question": "How much did I spend on Dining?"},
        headers=AUTH_HEADER,
    )
    assert answer.status_code == 200
    assert '"currency": "USD"' in answer.text
    assert '"response_contract": "advisor.v1"' in answer.text
    assert '"suggested_actions"' in answer.text
    assert '"source_links"' in answer.text
    assert "USD 8.00" in answer.text
    assert "₹" not in answer.text


def test_wrong_currency_model_insight_falls_back_to_usd_rules(client, monkeypatch):
    _usd_ledger(client)
    from app.services.proactive_insights import ai_router

    db = TestSession()
    try:
        transactions = db.query(Transaction).filter(Transaction.user_id == TEST_USER_ID).all()
        budgets = [Budget(user_id=TEST_USER_ID, category="Dining", monthly_limit=5)]

        async def wrong_currency(*args, **kwargs):
            return json.dumps([{
                "type": "warning", "priority": 5, "text": "You spent ₹10.25 on Dining.",
                "category": "Dining", "evidence_ids": [transactions[0].id],
            }])

        monkeypatch.setattr(ai_router, "generate", wrong_currency)
        insights = asyncio.run(generate_proactive_insights(transactions, budgets, currency="USD"))
    finally:
        db.close()

    assert insights
    assert all(item["source"] == "rules" for item in insights)
    assert any("USD 8.00" in item["text"] for item in insights)
    assert all("₹" not in item["text"] for item in insights)


def test_anomaly_messages_use_selected_currency(client):
    _usd_ledger(client)
    duplicate = client.post(
        "/transactions",
        json={
            "date": date.today().isoformat(), "type": "expense", "category": "Dining",
            "amount": "10.25", "description": "Second lunch",
        },
        headers=AUTH_HEADER,
    )
    assert duplicate.status_code == 201
    db = TestSession()
    try:
        transactions = db.query(Transaction).filter(Transaction.user_id == TEST_USER_ID).all()
        anomalies = detect_anomalies(transactions, currency="USD")
    finally:
        db.close()
    assert anomalies
    assert any("USD 10.25" in item["message"] for item in anomalies)
    assert all(item["id"].startswith("anomaly:") for item in anomalies)
    assert all(item["analysis"]["method"] for item in anomalies)
    assert all(item["recommended_action"] for item in anomalies)
    assert all("INR" not in item["message"] and "₹" not in item["message"] for item in anomalies)


def test_cloud_ai_disabled_uses_rules_without_calling_router(monkeypatch):
    transactions = [
        Transaction(
            id="tx-cloud-off",
            user_id=TEST_USER_ID,
            date=date.today(),
            type="expense",
            status="posted",
            category="Dining",
            amount=Decimal("10.25"),
            description="Lunch",
        )
    ]
    budgets = [Budget(user_id=TEST_USER_ID, category="Dining", monthly_limit=Decimal("5"))]

    async def should_not_run(*args, **kwargs):
        raise AssertionError("cloud provider was called while disabled")

    from app.services.proactive_insights import ai_router
    monkeypatch.setattr(ai_router, "generate", should_not_run)
    insights = asyncio.run(generate_proactive_insights(
        transactions, budgets, currency="USD", allow_ai=False,
    ))

    assert insights
    assert all(item["source"] == "rules" for item in insights)
