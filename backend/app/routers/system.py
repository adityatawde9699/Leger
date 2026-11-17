"""Liveness and health checks, and reference currency conversion."""

import logging
from decimal import Decimal

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..services.exchange_rates import convert_reference_rate, get_reference_rates

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Keep-alive ping (Render free tier cold-start prevention) ─────────────────
@router.get("/ping")
def ping():
    """Lightweight health check / keep-alive. No DB, no auth. ~0ms overhead."""
    return {"pong": True}


# ── Health ────────────────────────────────────────────────────────────────────
@router.get("/health")
def health():
    return {"ok": True, "version": "1.4.0"}


@router.get("/currency/convert")
async def currency_convert(
    amount: Decimal = Query(..., ge=0, le=Decimal("1000000000000")),
    base: str = Query(..., min_length=3, max_length=3),
    quote: str = Query(..., min_length=3, max_length=3),
):
    """Convert using a dated public reference rate without changing ledger data."""
    try:
        return await convert_reference_rate(amount, base, quote)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Reference exchange rate unavailable") from exc


@router.get("/currency/rates")
async def currency_rates(base: str = Query(..., min_length=3, max_length=3)):
    """Return dated public reference rates for display-only conversion."""
    try:
        return await get_reference_rates(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Reference exchange rate unavailable") from exc
