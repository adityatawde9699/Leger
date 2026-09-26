"""Privacy-safe aggregation of user feedback for insight quality work."""

import json
from collections import Counter
from collections.abc import Iterable

FEEDBACK_VALUES = (
    "helpful", "inaccurate", "irrelevant", "too_generic",
    "unsafe", "completed_action", "dismissed", "snoozed",
)


def aggregate_insight_feedback(rows: Iterable) -> dict:
    """Aggregate feedback without returning insight text, notes, or IDs."""
    by_feedback = Counter()
    by_type = Counter()
    total = 0
    for row in rows:
        try:
            details = json.loads(row.details or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        feedback = details.get("feedback")
        if feedback not in FEEDBACK_VALUES:
            continue
        total += 1
        by_feedback[feedback] += 1
        family = (row.resource_id or "unknown").split(":", 1)[0].casefold()
        by_type[family[:64] or "unknown"] += 1
    return {
        "version": 1,
        "total": total,
        "by_feedback": {key: by_feedback[key] for key in FEEDBACK_VALUES if by_feedback[key]},
        "by_insight_type": dict(sorted(by_type.items())),
    }
