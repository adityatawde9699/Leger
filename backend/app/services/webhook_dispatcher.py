"""
Webhook dispatcher — fires HMAC-signed events to registered URLs.
Runs in background, auto-disables after 5 consecutive failures.
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..models import Webhook

logger = logging.getLogger("ledger.webhooks")

MAX_FAILURES = 5
TIMEOUT_SECONDS = 10


async def fire_event(
    db: Session,
    user_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> int:
    """
    Fire an event to all matching active webhooks for a user.
    Returns the number of webhooks successfully notified.
    """
    hooks = db.query(Webhook).filter(
        Webhook.user_id == user_id,
        Webhook.is_active == True,
    ).all()

    matched = [h for h in hooks if event_type in h.events.split(",")]
    if not matched:
        return 0

    delivered = 0
    for hook in matched:
        try:
            await _deliver(hook, event_type, payload)
            hook.last_triggered = datetime.now(timezone.utc)
            hook.failure_count = 0
            delivered += 1
        except Exception as e:
            hook.failure_count += 1
            logger.warning(
                "webhook.failed id=%s url=%s attempt=%d error=%s",
                hook.id, hook.url[:60], hook.failure_count, str(e)[:100],
            )
            if hook.failure_count >= MAX_FAILURES:
                hook.is_active = False
                logger.warning("webhook.disabled id=%s after %d failures", hook.id, MAX_FAILURES)

    db.commit()
    return delivered


async def _deliver(hook: Webhook, event_type: str, payload: dict) -> None:
    """Send HMAC-signed POST to webhook URL."""
    body = json.dumps({
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }, default=str)

    signature = hmac.new(
        hook.secret.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(
            hook.url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Ledger-Signature": f"sha256={signature}",
                "X-Ledger-Event": event_type,
            },
        )
        response.raise_for_status()
