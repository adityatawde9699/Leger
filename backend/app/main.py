"""Ledger API: application assembly.

Routes live in app/routers (one APIRouter per product area), background work in
app/workers, and shared request helpers in app/helpers. This module wires them
together: logging, migrations, middleware, exception handlers and the lifespan
that runs the import and maintenance loops.
"""

import asyncio
import contextlib
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import IntegrityError

from .config import settings
from .middleware import bound_request_body, security_headers
from .migrate import run_migrations
from .rate_limit import categorized_rate_limits, limiter
from .routers import (
    accounts,
    advisor,
    auth,
    budgets,
    categorize,
    conversations,
    data,
    imports,
    insights,
    notifications,
    personalization,
    portfolios,
    profile,
    receipts,
    reports,
    summary,
    system,
    transactions,
)
from .workers.imports import _import_recovery_loop
from .workers.maintenance import _maintenance_loop

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ledger.api")

# ── Database schema ───────────────────────────────────────────────────────────
# Schema changes are Alembic revisions in backend/migrations. Production applies them
# in entrypoint.sh (`python -m app.migrate`) and sets RUN_DB_BOOTSTRAP=false; local
# development applies them here on startup.
if settings.run_db_bootstrap:
    run_migrations()


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Run the database-backed import worker and the maintenance loop with the server."""
    background = [asyncio.create_task(_import_recovery_loop()), asyncio.create_task(_maintenance_loop())]
    try:
        yield
    finally:
        for task in background:
            task.cancel()
        for task in background:
            with contextlib.suppress(asyncio.CancelledError):
                await task


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Ledger API", version="1.4.0", lifespan=lifespan,
              docs_url=None if settings.environment == "production" else "/docs",
              redoc_url=None if settings.environment == "production" else "/redoc",
              openapi_url=None if settings.environment == "production" else "/openapi.json")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(IntegrityError)
async def _integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    # A unique or foreign-key constraint rejected the write (for example a duplicate
    # source_ref). Report a conflict instead of a 500, without echoing database details.
    logger.warning("db.integrity_error path=%s error=%s", request.url.path, type(exc.orig).__name__)
    return JSONResponse(status_code=409, content={"detail": "This conflicts with an existing record"})


# Registration order matters: the last middleware added runs first (outermost).
app.middleware("http")(security_headers)
app.middleware("http")(bound_request_body)
app.middleware("http")(categorized_rate_limits)

# Included in the order the routes were originally declared, so path matching is unchanged.
app.include_router(auth.router)
app.include_router(system.router)
app.include_router(profile.router)
app.include_router(personalization.router)
app.include_router(transactions.router)
app.include_router(budgets.router)
app.include_router(summary.router)
app.include_router(imports.router)
app.include_router(notifications.router)
app.include_router(advisor.router)
app.include_router(conversations.router)
app.include_router(accounts.router)
app.include_router(categorize.router)
app.include_router(receipts.router)
app.include_router(reports.router)
app.include_router(data.router)
app.include_router(portfolios.router)
app.include_router(insights.router)


# ── Outermost ASGI CORS Wrap ──────────────────────────────────────────────────
# We wrap the FastAPI app instance at the ASGI level. This places CORSMiddleware
# outside of Starlette's ServerErrorMiddleware, ensuring that even unhandled 500
# exceptions receive CORS headers and don't get blocked by the browser.
app = CORSMiddleware(
    app,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
