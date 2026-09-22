from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.schemas import TransactionIn
from app.services.forecaster import generate_forecast
from app.services.insights import build_analysis_object, compare_periods, monthly_summary

from .conftest import AUTH_HEADER


def test_shared_analysis_claims_include_methods_and_evidence():
    transactions = [
        SimpleNamespace(id="income-1", date=date(2026, 1, 1), type="income", amount=Decimal("50000"), category="Salary", source="bank", description="Salary", merchant_normalized=None, account_id="a1"),
        SimpleNamespace(id="expense-1", date=date(2026, 1, 2), type="expense", amount=Decimal("1200"), category="Dining", source="bank", description="Dinner", merchant_normalized=None, account_id="a1"),
    ]
    summary = monthly_summary(transactions)
    analysis = build_analysis_object(transactions, summary)

    dining = next(claim for claim in analysis["claims"] if claim["id"] == "spending.dining")
    assert analysis["version"] == 1
    assert dining["evidence"]["method"] == "sum category expenses minus refunds/reimbursements"
    assert dining["evidence"]["transaction_ids"] == ["expense-1"]


def test_period_comparison_uses_equal_windows_and_exposes_evidence():
    transactions = [
        SimpleNamespace(id="old", date=date(2026, 1, 5), type="expense", amount=Decimal("100"), category="Food"),
        SimpleNamespace(id="new", date=date(2026, 2, 5), type="expense", amount=Decimal("150"), category="Food"),
    ]
    result = compare_periods(transactions, end_date=date(2026, 2, 5), days=30)
    assert result["status"] == "ready"
    assert result["current"]["period"]["days"] == result["previous"]["period"]["days"] == 30
    assert result["changes"]["expenses"] == Decimal("50")
    assert result["category_changes"][0]["transaction_ids"] == ["new", "old"]


def test_period_comparison_refuses_to_claim_a_trend_without_both_periods():
    transactions = [
        SimpleNamespace(id="new", date=date(2026, 2, 5), type="expense", amount=Decimal("150"), category="Food"),
    ]
    result = compare_periods(transactions, end_date=date(2026, 2, 5), days=30)
    assert result["status"] == "insufficient_data"
    assert result["data_quality"]["warnings"]


def test_pending_and_excluded_rows_do_not_change_committed_analysis():
    transactions = [
        SimpleNamespace(id="expense", date=date(2026, 2, 1), type="expense", status="posted", amount=Decimal("100"), category="Food", source="cash", description="Food", merchant_normalized=None),
        SimpleNamespace(id="reimbursement", date=date(2026, 2, 2), type="reimbursement", status="posted", amount=Decimal("25"), category="Food", source="cash", description="Repaid", merchant_normalized=None),
        SimpleNamespace(id="pending", date=date(2026, 2, 3), type="expense", status="pending", amount=Decimal("500"), category="Food", source="cash", description="Pending", merchant_normalized=None),
        SimpleNamespace(id="excluded", date=date(2026, 2, 4), type="expense", status="excluded", amount=Decimal("900"), category="Food", source="cash", description="Excluded", merchant_normalized=None),
    ]
    summary = monthly_summary(transactions)
    assert summary["expenses"] == Decimal("75")
    assert summary["data_quality"]["pending_count"] == 1
    assert summary["data_quality"]["excluded_count"] == 1
    assert summary["data_quality"]["income_confidence"] == "none"


def test_transaction_contract_accepts_reimbursements_and_review_statuses():
    transaction = TransactionIn(
        date=date(2026, 2, 5),
        type="reimbursement",
        status="pending",
        category="Food",
        amount=Decimal("25"),
        description="Shared lunch repayment",
    )
    assert transaction.type == "reimbursement"
    assert transaction.status == "pending"


def test_forecast_exposes_period_and_sufficiency_metadata():
    transactions = [
        SimpleNamespace(id="old", date=date(2026, 1, 5), type="expense", status="posted", amount=Decimal("100"), category="Food"),
        SimpleNamespace(id="new", date=date(2026, 2, 5), type="expense", status="posted", amount=Decimal("150"), category="Food"),
        SimpleNamespace(id="pending", date=date(2026, 2, 6), type="expense", status="pending", amount=Decimal("999"), category="Food"),
    ]
    result = generate_forecast(transactions)
    assert result["analysis"]["period_start"] == "2026-01-05"
    assert result["analysis"]["period_end"] == "2026-02-05"
    assert result["analysis"]["months_covered"] == 2
    assert result["analysis"]["sufficient"] is True
    assert result["by_category"]["Food"]["projected_30d"] < 999


def test_anomaly_endpoint_exposes_analysis_metadata(client):
    response = client.get("/analytics/anomalies?range=all", headers=AUTH_HEADER)
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["analysis"]["period_start"] is None
    assert body["analysis"]["sufficient"] is False


def test_anomaly_analysis_excludes_pending_rows(client):
    created = client.post(
        "/transactions",
        json={
            "type": "expense",
            "status": "pending",
            "category": "Food",
            "amount": "999",
            "description": "Pending purchase",
            "date": "2026-05-10",
        },
        headers=AUTH_HEADER,
    )
    assert created.status_code == 201
    body = client.get("/analytics/anomalies?range=all", headers=AUTH_HEADER).json()
    assert body["items"] == []
    assert body["analysis"]["transaction_count"] == 0
