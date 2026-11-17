"""HTTP middleware for security headers and request body size limits. app.main registers them."""

import logging
import uuid

from fastapi import Request
from fastapi.responses import Response
from slowapi.util import get_remote_address

from .auth import SESSION_COOKIE
from .config import settings

logger = logging.getLogger("ledger.api")


async def security_headers(request: Request, call_next):
    request_id = str(uuid.uuid4())
    response = await call_next(request)
    if response.status_code in {401, 403, 429}:
        logger.warning("security.request_denied request_id=%s status=%d path=%s ip=%s",
                       request_id, response.status_code, request.url.path, get_remote_address(request))
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.cookies.get(SESSION_COOKIE) or request.headers.get("authorization"):
        response.headers.setdefault("Cache-Control", "private, no-store")
    return response


async def bound_request_body(request: Request, call_next):
    def too_large():
        return Response(status_code=413, content="Request body too large", headers={
            "X-Request-ID": str(uuid.uuid4()), "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        })

    if request.method in {"POST", "PUT", "PATCH"}:
        content_type = request.headers.get("content-type", "").lower()
        if content_type.startswith("multipart/form-data"):
            limit = settings.max_upload_mb * 1024 * 1024 + 1024 * 1024
        elif request.url.path == "/backup/restore":
            limit = 20 * 1024 * 1024
        elif request.url.path == "/profile":
            limit = 3 * 1024 * 1024
        else:
            limit = 1024 * 1024
        length = request.headers.get("content-length", "0")
        if length.isdigit() and int(length) > limit:
            return too_large()
        chunks = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > limit:
                return too_large()
            chunks.append(chunk)
        request._body = b"".join(chunks)
    return await call_next(request)
