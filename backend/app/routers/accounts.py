"""Accounts: create, update, reconcile and deactivate the user's bank, card, wallet and cash accounts."""

import logging
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..helpers import _client_ip
from ..models import Account, User
from ..schemas import AccountIn, AccountOut, ReconciliationOut, ReconciliationRequest, UserContext
from ..services.audit import log_event
from ..services.exchange_rates import validate_currency

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Accounts (Multi-Account Support) ─────────────────────────────────────────
@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Account).filter(Account.user_id == user.id, Account.is_active).order_by(Account.name).all()


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(
    payload: AccountIn,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        validate_currency(payload.currency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.currency != db_user.currency_preference:
        raise HTTPException(status_code=400, detail="Account currency must match your Ledger currency")
    acct = Account(user_id=user.id, **payload.model_dump())
    db.add(acct)
    db.commit()
    db.refresh(acct)
    logger.info("account.created user=%s id=%s", user.id, acct.id)
    return acct


@router.put("/accounts/{account_id}", response_model=AccountOut)
def update_account(
    account_id: str,
    payload: AccountIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = db.get(Account, account_id)
    if not acct or acct.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    if payload.currency != acct.currency:
        raise HTTPException(status_code=400, detail="Account currency cannot be changed without converting its history")
    balance_changed = payload.balance != acct.balance
    for k, v in payload.model_dump().items():
        setattr(acct, k, v)
    if balance_changed:
        # Editing a number is not a fresh observed-bank-balance reconciliation.
        acct.last_reconciled_at = None
        acct.last_reconciled_balance = None
        acct.reconciliation_note = None
    log_event(
        db, user_id=user.id, action="update", resource_type="account",
        resource_id=account_id, details={"reconciliation_cleared": balance_changed}, ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(acct)
    return acct


@router.post("/accounts/{account_id}/reconcile", response_model=ReconciliationOut)
def reconcile_account(
    account_id: str,
    payload: ReconciliationRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a real-world balance check and make the account balance current."""
    acct = db.get(Account, account_id)
    if not acct or acct.user_id != user.id or not acct.is_active:
        raise HTTPException(status_code=404, detail="Account not found")

    previous_balance = Decimal(str(acct.balance or 0))
    observed_balance = payload.observed_balance
    reconciled_at = datetime.now(UTC)
    acct.balance = observed_balance
    acct.last_reconciled_at = reconciled_at
    acct.last_reconciled_balance = observed_balance
    acct.reconciliation_note = payload.note
    log_event(
        db, user_id=user.id, action="reconcile", resource_type="account",
        resource_id=account_id, details={
            "previous_balance": str(previous_balance),
            "observed_balance": str(observed_balance),
            "difference": str(observed_balance - previous_balance),
        }, ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(acct)
    return {
        "account_id": acct.id,
        "previous_balance": previous_balance,
        "observed_balance": observed_balance,
        "difference": observed_balance - previous_balance,
        "reconciled_at": reconciled_at,
        "note": payload.note,
    }


@router.delete("/accounts/{account_id}")
def delete_account(
    account_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = db.get(Account, account_id)
    if not acct or acct.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    acct.is_active = False  # soft delete
    log_event(
        db, user_id=user.id, action="delete", resource_type="account",
        resource_id=account_id, ip_address=_client_ip(request),
    )
    db.commit()
    logger.info("account.deleted user=%s id=%s", user.id, account_id)
    return {"deleted": True}
