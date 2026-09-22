"""Privacy-safe structured product telemetry.

Telemetry is emitted as JSON logs so deployments can route it to their existing
log pipeline without creating a second financial-data store.  The helper only
accepts operational fields; user IDs are hashed and free-form financial text is
never accepted or serialized.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("ledger.telemetry")

_ALLOWED_METADATA = {
    "count",
    "feedback",
    "has_note",
    "task",
    "status",
    "coverage",
    "evidence_count",
    "warning_count",
}


def _user_hash(user_id: str | None) -> str | None:
    if not user_id:
        return None
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]


def record_telemetry(
    event: str,
    *,
    user_id: str | None = None,
    latency_ms: float | None = None,
    provider: str | None = None,
    fallback: bool | None = None,
    parse_success: bool | None = None,
    evidence_valid: bool | None = None,
    outcome: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit a bounded, machine-readable event with no raw financial content."""
    safe_metadata = {
        key: value
        for key, value in (metadata or {}).items()
        if key in _ALLOWED_METADATA and isinstance(value, (str, int, float, bool))
    }
    payload: dict[str, Any] = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "user_hash": _user_hash(user_id),
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
        "provider": provider,
        "fallback": fallback,
        "parse_success": parse_success,
        "evidence_valid": evidence_valid,
        "outcome": outcome,
    }
    if safe_metadata:
        payload["metadata"] = safe_metadata
    logger.info("telemetry %s", json.dumps(payload, sort_keys=True, separators=(",", ":")))
