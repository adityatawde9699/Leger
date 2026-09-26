import json

from app.services.advisor_contract import validate_advisor_response

TX_ID = "123e4567-e89b-12d3-a456-426614174000"
CONTEXT = f"Currency: USD; category=Dining; merchant=Blue Cafe; USD 10.00; date=2026-09-30; transaction_id={TX_ID}"


def response(claim_text="Dining cost USD 10.00.", evidence_ids=None):
    return json.dumps({
        "answer": "Review the cited spending.",
        "claims": [{"text": claim_text, "evidence_ids": evidence_ids or [TX_ID]}],
        "assumptions": [],
        "uncertainties": [],
        "suggested_actions": [],
    })


def test_structured_advisor_response_requires_evidence_and_accepts_grounded_claim():
    result = validate_advisor_response(response(), CONTEXT, "USD", {TX_ID}, {"Dining", "Blue Cafe"})
    assert result["valid"] is True
    assert result["evidence_coverage"] == 1.0


def test_structured_advisor_response_rejects_unknown_evidence_and_prose():
    unknown = validate_advisor_response(response(evidence_ids=["123e4567-e89b-12d3-a456-426614174001"]), CONTEXT, "USD", {TX_ID}, {"Dining"})
    assert unknown["valid"] is False

    prose = validate_advisor_response("You spent USD 10.00.", CONTEXT, "USD", {TX_ID}, {"Dining"})
    assert prose["valid"] is False


def test_structured_advisor_response_rejects_unsupported_amount_in_claim():
    result = validate_advisor_response(response("Dining cost USD 999.00."), CONTEXT, "USD", {TX_ID}, {"Dining"})
    assert result["valid"] is False
