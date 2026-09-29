"""
Webhook dispatcher — fires HMAC-signed events to registered URLs.
Runs in background, auto-disables after 5 consecutive failures.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import ssl
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..models import Webhook
from .url_guard import validate_webhook_url
from .webhook_secrets import decrypt_secret

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
    hooks = (
        db.query(Webhook)
        .filter(
            Webhook.user_id == user_id,
            Webhook.is_active,
        )
        .all()
    )

    matched = [h for h in hooks if event_type in h.events.split(",")]
    if not matched:
        return 0

    delivered = 0
    for hook in matched:
        try:
            await _deliver(hook, event_type, payload)
            hook.last_triggered = datetime.now(UTC)
            hook.failure_count = 0
            delivered += 1
        except Exception as e:
            hook.failure_count += 1
            logger.warning(
                "webhook.failed id=%s attempt=%d error=%s",
                hook.id,
                hook.failure_count,
                type(e).__name__,
            )
            if hook.failure_count >= MAX_FAILURES:
                hook.is_active = False
                logger.warning("webhook.disabled id=%s after %d failures", hook.id, MAX_FAILURES)

    db.commit()
    return delivered


async def _deliver(hook: Webhook, event_type: str, payload: dict) -> None:
    """Send HMAC-signed POST to webhook URL."""
    # Re-validate at delivery time too — guards against DNS rebinding and any
    # rows that predate registration-time SSRF validation.
    addresses = await asyncio.wait_for(
        asyncio.to_thread(validate_webhook_url, hook.url), timeout=TIMEOUT_SECONDS,
    )
    target = urlparse(hook.url)

    timestamp = datetime.now(UTC).isoformat()
    body = json.dumps(
        {
            "event": event_type,
            "timestamp": timestamp,
            "data": payload,
        },
        default=str,
    )

    signature = hmac.new(
        decrypt_secret(hook.secret).encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()

    async def send_to_pinned_address() -> None:
        port = target.port or (443 if target.scheme == "https" else 80)
        context = ssl.create_default_context() if target.scheme == "https" else None
        reader, writer = await asyncio.open_connection(
            addresses[0], port, ssl=context,
            server_hostname=target.hostname if context else None,
        )
        try:
            host = f"[{target.hostname}]" if ":" in target.hostname else target.hostname
            path = target.path or "/"
            if target.query:
                path += f"?{target.query}"
            body_bytes = body.encode()
            headers = (
                f"POST {path} HTTP/1.1\r\nHost: {host}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body_bytes)}\r\n"
                f"X-Ledger-Signature: sha256={signature}\r\n"
                f"X-Ledger-Event: {event_type}\r\n"
                f"X-Ledger-Timestamp: {timestamp}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            writer.write(headers + body_bytes)
            await writer.drain()
            status_line = await reader.readline()
            if len(status_line) > 8192 or not status_line.startswith(b"HTTP/1."):
                raise RuntimeError("Invalid webhook response")
            parts = status_line.split(maxsplit=2)
            if len(parts) < 2 or not parts[1].isdigit() or not 200 <= int(parts[1]) < 300:
                raise RuntimeError("Webhook receiver returned a non-success status")
        finally:
            writer.close()
            await writer.wait_closed()

    await asyncio.wait_for(send_to_pinned_address(), timeout=TIMEOUT_SECONDS)
