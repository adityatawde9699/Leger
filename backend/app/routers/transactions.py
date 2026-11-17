"""Transactions: list, create (including offline replays and splits), edit, undo and delete."""

import json
import logging
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..cache import llm_cache
from ..db import get_db
from ..helpers import (
    _client_ip,
    _cursor_decode,
    _cursor_encode,
    _get_balance_at,
    _month_range,
    _resolve_merchant_alias,
    _transaction_snapshot,
)
from ..models import Account, AuditLog, Transaction
from ..schemas import (
    BulkDeleteRequest,
    PaginatedTransactions,
    SplitTransactionIn,
    SplitTransactionOut,
    TransactionIn,
    TransactionOut,
    UserContext,
)
from ..services.audit import log_event

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Transactions ──────────────────────────────────────────────────────────────
@router.get("/transactions", response_model=PaginatedTransactions)
def list_transactions(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    month: str | None = Query(None),
    category: str | None = Query(None),
    search: str | None = Query(None),
    tx_type: str | None = Query(None, alias="type"),
    tx_status: str | None = Query(None, alias="status", pattern="^(posted|pending|excluded)$"),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Transaction).filter(Transaction.user_id == user.id)

    if month:
        start, end = _month_range(month)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    if category:
        q = q.filter(Transaction.category == category)
    if tx_type and tx_type in ("income", "expense", "refund", "reimbursement", "transfer"):
        q = q.filter(Transaction.type == tx_type)
    if tx_status:
        q = q.filter(Transaction.status == tx_status)
    else:
        q = q.filter(Transaction.status == "posted")
    if search:
        pattern = f"%{search.lower()}%"
        q = q.filter(Transaction.description.ilike(pattern))
    if cursor:
        try:
            cursor_date, cursor_id = _cursor_decode(cursor)
            q = q.filter(
                (Transaction.date < cursor_date) | ((Transaction.date == cursor_date) & (Transaction.id < cursor_id))
            )
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor")

    q = q.order_by(Transaction.date.desc(), Transaction.id.desc())
    rows = q.limit(limit + 1).all()
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = _cursor_encode(items[-1]) if has_more and items else None

    return PaginatedTransactions(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total_returned=len(items),
    )


def _existing_offline_transaction(db: Session, user_id: str, payload: TransactionIn) -> Transaction | None:
    """The transaction an offline draft already created, so replays stay idempotent."""
    existing = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.source == payload.source,
        Transaction.source_ref == payload.source_ref,
    ).first()
    if existing and any((
        existing.date != payload.date,
        existing.type != payload.type,
        existing.status != payload.status,
        existing.category != payload.category,
        existing.amount != payload.amount,
        existing.description != payload.description,
        existing.account_id != payload.account_id,
    )):
        raise HTTPException(status_code=409, detail="Offline request ID was already used for a different transaction")
    return existing


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(
    payload: TransactionIn,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offline = bool(payload.source_ref and payload.source_ref.startswith("offline:"))
    if offline and (existing := _existing_offline_transaction(db, user.id, payload)):
        return existing
    if payload.account_id:
        account = db.get(Account, payload.account_id)
        if not account or account.user_id != user.id or not account.is_active:
            raise HTTPException(status_code=400, detail="Account is not available for this user")
    tx = Transaction(user_id=user.id, **payload.model_dump())
    tx.merchant_normalized = _resolve_merchant_alias(db, user.id, tx.description, tx.merchant_normalized)
    try:
        db.add(tx)
        db.flush()  # assign tx.id before backfill query

        # Backfill running_balance so the DB is always the source of truth.
        # running_balance = (last known balance) ± this transaction's amount.
        if tx.running_balance is None and tx.source != "cash":
            prior_balance = _get_balance_at(db, user.id, as_of_date=None, exclude_id=tx.id)
            if prior_balance is not None:
                if tx.type in ("income", "refund", "reimbursement") and tx.status == "posted":
                    tx.running_balance = prior_balance + tx.amount
                elif tx.type == "expense" and tx.status == "posted":
                    tx.running_balance = prior_balance - tx.amount

        db.commit()
    except IntegrityError:
        # A concurrent replay of the same offline entry won the unique index race.
        db.rollback()
        if offline and (existing := _existing_offline_transaction(db, user.id, payload)):
            return existing
        raise
    db.refresh(tx)
    logger.info("transaction.created user=%s id=%s", user.id, tx.id)
    return tx


@router.post("/transactions/split", response_model=SplitTransactionOut, status_code=201)
def create_split_transaction(
    payload: SplitTransactionIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Atomically record one purchase across multiple categories, without double-counting it."""
    cent = Decimal("0.01")
    amounts = [payload.amount, *(line.amount for line in payload.lines)]
    if any(amount != amount.quantize(cent) for amount in amounts):
        raise HTTPException(status_code=400, detail="Split amounts must have at most two decimal places")
    if sum((line.amount for line in payload.lines), Decimal("0")) != payload.amount:
        raise HTTPException(status_code=400, detail="Split line amounts must equal the total amount")
    if payload.account_id:
        account = db.get(Account, payload.account_id)
        if not account or account.user_id != user.id or not account.is_active:
            raise HTTPException(status_code=400, detail="Account is not available for this user")
    group_id = f"split:{payload.client_request_id or uuid4()}"
    if payload.client_request_id:
        existing = db.query(Transaction).filter(
            Transaction.user_id == user.id, Transaction.source_ref == group_id
        ).order_by(Transaction.id).all()
        if existing:
            if (
                len(existing) != len(payload.lines)
                or sum((tx.amount for tx in existing), Decimal("0")) != payload.amount
                or sorted((tx.category, tx.amount) for tx in existing) != sorted((line.category, line.amount) for line in payload.lines)
                or any(
                    tx.description != payload.description or tx.date != payload.date
                    or tx.status != payload.status or tx.account_id != payload.account_id
                    for tx in existing
                )
            ):
                raise HTTPException(status_code=409, detail="Client request ID was already used for a different split")
            return {"group_id": group_id, "items": existing}
    items = []
    for line in payload.lines:
        tx = Transaction(
            user_id=user.id, account_id=payload.account_id, date=payload.date,
            type="expense", status=payload.status, category=line.category,
            amount=line.amount, description=payload.description,
            source="bank" if payload.account_id else "cash", source_ref=group_id,
        )
        tx.merchant_normalized = _resolve_merchant_alias(db, user.id, tx.description, tx.merchant_normalized)
        db.add(tx)
        items.append(tx)
    db.flush()
    log_event(
        db, user_id=user.id, action="create", resource_type="split_transaction",
        resource_id=group_id.removeprefix("split:"), details={"line_count": len(items), "total": str(payload.amount)},
        ip_address=_client_ip(request),
    )
    db.commit()
    return {"group_id": group_id, "items": items}


@router.delete("/transactions/{transaction_id}")
def delete_transaction(
    transaction_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(tx)
    log_event(
        db, user_id=user.id, action="delete", resource_type="transaction",
        resource_id=transaction_id, ip_address=_client_ip(request),
    )
    db.commit()
    logger.info("transaction.deleted user=%s id=%s", user.id, transaction_id)
    return {"deleted": True}


@router.post("/transactions/bulk-delete")
def bulk_delete_transactions(
    payload: BulkDeleteRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.id.in_(payload.transaction_ids),
            Transaction.user_id == user.id,
        )
        .all()
    )
    if not txs:
        return {"deleted_count": 0}

    count = len(txs)
    for tx in txs:
        db.delete(tx)
    log_event(
        db, user_id=user.id, action="delete", resource_type="transaction",
        details={"bulk": True, "count": count}, ip_address=_client_ip(request),
    )
    db.commit()
    logger.info("transactions.bulk_deleted user=%s count=%d", user.id, count)
    return {"deleted_count": count}


# ── Transaction Update ────────────────────────────────────────────────────────
@router.put("/transactions/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: str,
    payload: TransactionIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if payload.account_id:
        account = db.get(Account, payload.account_id)
        if not account or account.user_id != user.id or not account.is_active:
            raise HTTPException(status_code=400, detail="Account is not available for this user")
    before = _transaction_snapshot(tx)
    for k, v in payload.model_dump().items():
        setattr(tx, k, v)
    tx.merchant_normalized = _resolve_merchant_alias(db, user.id, tx.description, tx.merchant_normalized)
    after = _transaction_snapshot(tx)
    log_event(
        db, user_id=user.id, action="update", resource_type="transaction",
        resource_id=tx.id, details={"before": before, "after": after}, ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(tx)
    logger.info("transaction.updated user=%s id=%s", user.id, tx.id)
    return tx


@router.post("/transactions/{transaction_id}/undo", response_model=TransactionOut)
def undo_transaction_update(
    transaction_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restore the latest transaction update, if it has not already been undone."""
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    latest_event = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == user.id,
            AuditLog.resource_type == "transaction",
            AuditLog.resource_id == transaction_id,
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .first()
    )
    if not latest_event or latest_event.action != "update" or not latest_event.details:
        raise HTTPException(status_code=409, detail="No reversible transaction update is available")
    try:
        details = json.loads(latest_event.details)
        before = details["before"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail="The latest transaction update cannot be reversed") from exc

    try:
        restored = TransactionIn(**before).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=409, detail="The saved transaction version is invalid") from exc
    if restored.get("account_id"):
        account = db.get(Account, restored["account_id"])
        if not account or account.user_id != user.id:
            raise HTTPException(status_code=409, detail="The saved account is no longer available")
    for key, value in restored.items():
        setattr(tx, key, value)
    # These fields are intentionally not accepted from ordinary user edits, but
    # they are part of the exact version being restored after a category fix.
    tx.merchant_normalized = before.get("merchant_normalized")
    tx.confidence = before.get("confidence")
    log_event(
        db,
        user_id=user.id,
        action="undo",
        resource_type="transaction",
        resource_id=tx.id,
        details={"source_audit_id": latest_event.id},
        ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(tx)
    llm_cache.invalidate_user(user.id)
    logger.info("transaction.undo user=%s id=%s source_audit=%s", user.id, tx.id, latest_event.id)
    return tx
