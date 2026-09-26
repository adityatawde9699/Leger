import pytest
from pydantic import ValidationError

from app.schemas import AdvisorActionRequest


def test_advisor_action_contract_allows_only_review_flows():
    action = AdvisorActionRequest(
        action_type="review_evidence",
        transaction_ids=["tx-1"],
        conversation_id="conversation-1",
    )
    assert action.action_type == "review_evidence"
    assert action.transaction_ids == ["tx-1"]

    with pytest.raises(ValidationError):
        AdvisorActionRequest(action_type="delete_transaction")
