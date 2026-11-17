"""Rate limiting: slowapi per-route limits and the shared Redis fixed-window limits by request category."""

import hashlib
import logging
import time
import uuid

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from .auth import SESSION_COOKIE
from .config import settings
from .db import SessionLocal
from .models import AppSession
from .services.upstash_redis import get_redis_client

logger = logging.getLogger("ledger.api")


# ── Rate limiter ──────────────────────────────────────────────────────────────
def _rate_limit_identity(request: Request) -> str:
    # Signed-in traffic is keyed on the session alone: behind the Vercel/Render proxies the
    # client IP is shared (or spoofable), so mixing it in would merge users or mint new buckets.
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        return f"session:{hashlib.sha256(session_token.encode()).hexdigest()[:24]}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_rate_limit_identity,
                  storage_uri="memory://",
                  default_limits=["120/minute"])
security_rate_store = get_redis_client() if settings.environment == "production" else None


def _security_rate_count(category: str, window: int, session_token: str | None, remote_addr: str) -> int:
    """Increment and return this request's fixed-window counter (blocking I/O)."""
    # Authenticated requests: one bucket per user, independent of IP (see
    # _rate_limit_identity). Anonymous requests: one bucket per client IP, which
    # uvicorn resolves from the proxy's X-Forwarded-For (entrypoint.sh).
    raw = f"ip:{remote_addr}"
    if session_token:
        with SessionLocal() as db:
            session = db.get(AppSession, hashlib.sha256(session_token.encode()).hexdigest())
            if session:
                raw = f"user:{session.user_id}"
    subject = hashlib.sha256(raw.encode()).hexdigest()
    key = f"security-rate:{category}:{subject}:{int(time.time()) // window}"
    pipeline = security_rate_store.pipeline()
    pipeline.incr(key)
    pipeline.expire(key, window * 2)
    count, _ = pipeline.exec()
    return count


async def categorized_rate_limits(request: Request, call_next):
    if security_rate_store is not None and request.method != "OPTIONS":
        path = request.url.path
        if path.startswith("/auth/"):
            category, limit, window = "auth", 10, 60
        elif path.startswith(("/export/", "/backup/")):
            category, limit, window = "export", 10, 3600
        elif path.startswith(("/imports/", "/receipts/")) or path.endswith("/receipt"):
            category, limit, window = "upload", 20, 3600
        elif path.startswith(("/advisor", "/insights", "/categorize")):
            category, limit, window = "ai", 30, 3600
        elif request.method not in {"GET", "HEAD"}:
            category, limit, window = "mutation", 120, 60
        else:
            category = None
        if category:
            try:
                # Session lookup and the Upstash call are blocking network I/O; run them
                # in the threadpool so one slow call cannot stall every other request.
                count = await run_in_threadpool(
                    _security_rate_count, category, window,
                    request.cookies.get(SESSION_COOKIE), get_remote_address(request),
                )
            except Exception:
                return Response(status_code=503, content="Rate limiter unavailable", headers={
                    "X-Request-ID": str(uuid.uuid4()), "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
                })
            if count > limit:
                return Response(status_code=429, content="Rate limit exceeded", headers={
                    "Retry-After": str(window), "X-Request-ID": str(uuid.uuid4()),
                    "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
                })
    return await call_next(request)
