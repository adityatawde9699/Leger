import json

from app.services.telemetry import record_telemetry


def test_telemetry_is_structured_and_excludes_raw_metadata(caplog):
    with caplog.at_level("INFO", logger="ledger.telemetry"):
        record_telemetry(
            "insight.feedback",
            user_id="user-1",
            latency_ms=12.345,
            provider="rules",
            metadata={"feedback": "helpful", "count": 1, "description": "Sensitive merchant text"},
        )

    message = next(record.message for record in caplog.records if record.name == "ledger.telemetry")
    payload = json.loads(message.removeprefix("telemetry "))
    assert payload["event"] == "insight.feedback"
    assert payload["latency_ms"] == 12.35
    assert payload["user_hash"] != "user-1"
    assert payload["metadata"] == {"count": 1, "feedback": "helpful"}
    assert "Sensitive merchant text" not in message
