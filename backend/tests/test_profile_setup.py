import base64
from decimal import Decimal
from io import BytesIO

from PIL import Image

from app.models import Account

from .conftest import AUTH_HEADER, TEST_USER_ID, TestSession


def test_profile_setup_preferences_are_persisted(client):
    initial = client.get("/profile", headers=AUTH_HEADER)
    assert initial.status_code == 200
    assert initial.json()["region"] == "IN"
    assert initial.json()["onboarding_completed"] is False

    updated = client.put("/profile", json={
        "currency_preference": "USD",
        "region": "US",
        "income_pattern": "irregular",
        "pay_cycle": "biweekly",
        "risk_comfort": "balanced",
        "household_mode": "shared",
        "recurring_tolerance": "strict",
        "cloud_ai_enabled": False,
        "onboarding_completed": True,
    }, headers=AUTH_HEADER)
    assert updated.status_code == 200
    assert updated.json()["currency_preference"] == "USD"
    assert updated.json()["region"] == "US"
    assert updated.json()["income_pattern"] == "irregular"
    assert updated.json()["pay_cycle"] == "biweekly"
    assert updated.json()["risk_comfort"] == "balanced"
    assert updated.json()["household_mode"] == "shared"
    assert updated.json()["recurring_tolerance"] == "strict"
    assert updated.json()["cloud_ai_enabled"] is False
    assert updated.json()["onboarding_completed"] is True

    avatar_buffer = BytesIO()
    Image.new("RGB", (1, 1)).save(avatar_buffer, format="PNG")
    avatar_update = client.put("/profile", json={"avatar_url": "data:image/png;base64," + base64.b64encode(avatar_buffer.getvalue()).decode()}, headers=AUTH_HEADER)
    assert avatar_update.status_code == 200
    assert avatar_update.json()["currency_preference"] == "USD"

    exported = client.get("/export/full", headers=AUTH_HEADER).json()["profile"]
    assert exported["region"] == "US"
    assert exported["income_pattern"] == "irregular"
    assert exported["pay_cycle"] == "biweekly"
    assert exported["risk_comfort"] == "balanced"
    assert exported["household_mode"] == "shared"
    assert exported["recurring_tolerance"] == "strict"
    assert exported["onboarding_completed"] is True


def test_profile_rejects_unknown_setup_preferences(client):
    response = client.put("/profile", json={
        "currency_preference": "INR",
        "region": "XX-NOT-A-REGION",
        "income_pattern": "sometimes",
    }, headers=AUTH_HEADER)
    assert response.status_code == 422


def test_currency_change_is_rejected_after_financial_data_is_saved(client):
    created = client.post(
        "/accounts",
        json={"name": "Main", "account_type": "savings", "balance": "123.45", "currency": "INR"},
        headers=AUTH_HEADER,
    )
    assert created.status_code == 201

    changed = client.put("/profile", json={"currency_preference": "USD"}, headers=AUTH_HEADER)
    assert changed.status_code == 200
    assert changed.json()["currency_preference"] == "USD"

    region_change = client.put("/profile", json={"region": "US"}, headers=AUTH_HEADER)
    assert region_change.status_code == 200
    assert region_change.json()["region"] == "US"


def test_account_currency_must_match_profile_and_cannot_be_relabelled(client):
    updated = client.put("/profile", json={"currency_preference": "USD"}, headers=AUTH_HEADER)
    assert updated.status_code == 200
    details = {"name": "Checking", "account_type": "current", "balance": "15.25"}

    mismatch = client.post("/accounts", json={**details, "currency": "INR"}, headers=AUTH_HEADER)
    assert mismatch.status_code == 400

    created = client.post("/accounts", json={**details, "currency": "USD"}, headers=AUTH_HEADER)
    assert created.status_code == 201
    assert created.json()["balance"] == "15.25"

    relabel = client.put(
        f"/accounts/{created.json()['id']}",
        json={**details, "currency": "INR"},
        headers=AUTH_HEADER,
    )
    assert relabel.status_code == 400
    assert client.get("/accounts", headers=AUTH_HEADER).json()[0]["currency"] == "USD"


def test_legacy_currency_mismatch_pauses_analysis_until_corrected(client):
    db = TestSession()
    try:
        db.add(Account(
            user_id=TEST_USER_ID,
            name="Legacy USD account",
            account_type="current",
            balance=Decimal("20.50"),
            currency="USD",
        ))
        db.commit()
    finally:
        db.close()

    summary = client.get("/summary?range=all", headers=AUTH_HEADER)
    assert summary.status_code == 200
    assert summary.json()["data_quality"]["currency_mismatch_count"] == 1
    assert any("combined totals are unreliable" in warning for warning in summary.json()["data_quality"]["warnings"])

    advisor = client.post("/advisor/stream", json={"question": "What is my balance?"}, headers=AUTH_HEADER)
    assert advisor.status_code == 200
    assert "I cannot give a reliable answer" in advisor.text

    corrected = client.put("/profile", json={"currency_preference": "USD"}, headers=AUTH_HEADER)
    assert corrected.status_code == 200
    assert client.get("/summary?range=all", headers=AUTH_HEADER).json()["data_quality"]["currency_mismatch_count"] == 0


def test_unused_removed_foreign_account_does_not_block_analysis(client):
    db = TestSession()
    try:
        account = Account(
            user_id=TEST_USER_ID,
            name="Unused legacy account",
            account_type="current",
            balance=Decimal("0"),
            currency="USD",
        )
        db.add(account)
        db.commit()
        account_id = account.id
    finally:
        db.close()

    assert client.get("/summary?range=all", headers=AUTH_HEADER).json()["data_quality"]["currency_mismatch_count"] == 1
    assert client.delete(f"/accounts/{account_id}", headers=AUTH_HEADER).status_code == 200
    assert client.get("/summary?range=all", headers=AUTH_HEADER).json()["data_quality"]["currency_mismatch_count"] == 0
