from types import SimpleNamespace

from app.services.feedback import aggregate_insight_feedback


def test_feedback_aggregation_is_text_free_and_groups_stable_families():
    result = aggregate_insight_feedback([
        SimpleNamespace(details='{"feedback":"helpful"}', resource_id="spending:secret-name"),
        SimpleNamespace(details='{"feedback":"snoozed"}', resource_id="anomaly:secret-name"),
        SimpleNamespace(details='{"feedback":"inaccurate"}', resource_id="spending:other-secret"),
        SimpleNamespace(details='{"feedback":"helpful","note":"private note"}', resource_id="ignored"),
    ])

    assert result == {
        "version": 1,
        "total": 4,
        "by_feedback": {"helpful": 2, "inaccurate": 1, "snoozed": 1},
        "by_insight_type": {"anomaly": 1, "ignored": 1, "spending": 2},
    }


def test_feedback_aggregation_ignores_malformed_or_unknown_rows():
    result = aggregate_insight_feedback([
        SimpleNamespace(details="not-json", resource_id="spending:one"),
        SimpleNamespace(details='{"feedback":"unknown"}', resource_id="spending:two"),
    ])

    assert result["total"] == 0
    assert result["by_feedback"] == {}
