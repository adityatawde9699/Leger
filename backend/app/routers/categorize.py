"""Categorization: rules/LLM categorize endpoints, user corrections and bulk recategorization."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..cache import llm_cache
from ..config import settings
from ..db import get_db
from ..helpers import _client_ip, _cloud_ai_allowed, _transaction_snapshot
from ..models import Transaction
from ..rate_limit import limiter
from ..schemas import CategorizeBatchRequest, CategorizeSingleRequest, CategorizeSingleResponse, UserContext
from ..services.audit import log_event
from ..services.auto_categorizer import categorize_batch, categorize_single
from ..services.categorization_learner import get_user_overrides, record_correction
from ..services.telemetry import record_telemetry

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── New request schemas ───────────────────────────────────────────────────────
class CategoryCorrectionRequest(BaseModel):
    category: str


# ── Auto-categorize ──────────────────────────────────────────────────────────
@router.post("/categorize", response_model=CategorizeSingleResponse)
@limiter.limit(settings.categorize_rate_limit)
async def auto_categorize(
    request: Request,
    payload: CategorizeSingleRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = await categorize_single(
        payload.description, payload.tx_type, allow_cloud_ai=_cloud_ai_allowed(db, user.id)
    )
    return result


@router.post("/categorize/batch")
@limiter.limit(settings.categorize_rate_limit)
async def auto_categorize_batch(
    request: Request,
    payload: CategorizeBatchRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    results = await categorize_batch(payload.transactions, allow_cloud_ai=_cloud_ai_allowed(db, user.id))
    return results


# ── Category Correction (user feedback for learning) ─────────────────────────
@router.post("/transactions/{transaction_id}/correct-category")
def correct_transaction_category(
    transaction_id: str,
    payload: CategoryCorrectionRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """User manually corrects a transaction's category — trains the learning system."""
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    old_category = tx.category
    before = _transaction_snapshot(tx)
    tx.category = payload.category
    tx.confidence = 1.0  # User correction = full confidence
    after = _transaction_snapshot(tx)
    log_event(
        db,
        user_id=user.id,
        action="update",
        resource_type="transaction",
        resource_id=tx.id,
        details={"before": before, "after": after, "reason": "category_correction"},
        ip_address=_client_ip(request),
    )
    record_telemetry("transaction.correction", user_id=user.id, outcome="category", metadata={"status": "completed"})
    db.commit()

    # Record correction for learning pipeline
    record_correction(db, user.id, tx.description, payload.category)

    # Invalidate relevant caches for this user
    llm_cache.invalidate_user(user.id)

    logger.info(
        "category.corrected user=%s tx=%s %s→%s",
        user.id,
        transaction_id,
        old_category,
        payload.category,
    )
    return {"corrected": True, "old_category": old_category, "new_category": payload.category}


# ── Embedding Cache Stats (debug/monitoring) ──────────────────────────────────
@router.get("/debug/embedding-cache")
def embedding_cache_stats(
    user: UserContext = Depends(get_current_user),
):
    """Return embedding cache statistics for monitoring."""
    from .services.embedding_cache import embedding_cache

    return embedding_cache.get_stats()


# ── Mass Recategorize (new categories support) ────────────────────────────────
@router.post("/categorize/recategorize")
@limiter.limit(settings.categorize_rate_limit)
async def recategorize_uncategorized(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-categorize 'Other' transactions using the 4-tier AI pipeline."""
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user.id,
            Transaction.category == "Other",
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    if not txs:
        return {"updated": 0, "offset": offset}

    # Load user overrides for personalized categorization
    user_overrides = get_user_overrides(db, user.id)
    batch = [{"id": tx.id, "description": tx.description, "type": tx.type} for tx in txs]
    results = await categorize_batch(batch, user_overrides=user_overrides, allow_cloud_ai=_cloud_ai_allowed(db, user.id))

    updated = 0
    for result in results:
        if result["category"] != "Other" and result.get("confidence", 0) >= 0.6:
            tx = db.get(Transaction, result["id"])
            if tx:
                tx.category = result["category"]
                tx.confidence = result.get("confidence")
                tx.merchant_normalized = result.get("merchant")
                updated += 1
    db.commit()
    logger.info("recategorize user=%s updated=%d of %d offset=%d", user.id, updated, len(txs), offset)
    return {"updated": updated, "total_checked": len(txs), "offset": offset, "has_more": len(txs) == limit}
