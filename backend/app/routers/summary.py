"""Monthly summary and the daily position (safe-to-spend) with obligation review."""

import logging
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..helpers import (
    _account_currency_mismatch_count,
    _client_ip,
    _get_balance_at,
    _history_start,
    _month_range,
    _tx_query,
)
from ..models import Account, Budget, ImportJob, RecurringRule, Transaction, User
from ..schemas import DailyPositionOut, ObligationsReviewIn, UserContext
from ..services.audit import log_event
from ..services.daily_position import calculate_daily_position
from ..services.insights import (
    build_analysis_object,
    compare_periods,
    compute_insight_claims,
    compute_insights,
    data_quality,
    monthly_summary,
    recurring_payments,
)

router = APIRouter()
logger = logging.getLogger("ledger.api")


@router.post("/daily-position/review")
def confirm_daily_obligations(
    payload: ObligationsReviewIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a user's explicit review, not an assertion by Ledger that bills are complete."""
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Confirm your obligations explicitly before recording a review")
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db_user.obligations_reviewed_at = datetime.now(UTC)
    log_event(
        db, user_id=user.id, action="confirm", resource_type="daily_obligations",
        details={"reviewed_at": db_user.obligations_reviewed_at.isoformat()}, ip_address=_client_ip(request),
    )
    db.commit()
    return {"reviewed_at": db_user.obligations_reviewed_at}


@router.get("/daily-position", response_model=DailyPositionOut)
def get_daily_position(
    as_of: date | None = None,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Current-month facts and a discretionary estimate only when evidence is sufficient."""
    if as_of and abs((as_of - date.today()).days) > 1:
        raise HTTPException(status_code=400, detail="as_of must be within one day of the server date")
    profile = db.get(User, user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return calculate_daily_position(
        accounts=db.query(Account).filter(Account.user_id == user.id).all(),
        transactions=_tx_query(db, user.id, include_unposted=True).all(),
        budgets=db.query(Budget).filter(Budget.user_id == user.id).all(),
        recurring_rules=db.query(RecurringRule).filter(RecurringRule.user_id == user.id).all(),
        currency=profile.currency_preference,
        income_pattern=profile.income_pattern,
        obligations_reviewed_at=profile.obligations_reviewed_at,
        pending_imports=db.query(ImportJob.id).filter(
            ImportJob.user_id == user.id, ImportJob.status.in_(("pending", "processing"))
        ).count(),
        currency_mismatch=bool(_account_currency_mismatch_count(db, user.id)),
        as_of=as_of,
    )


@router.get("/summary")
def get_summary(
    month: str | None = None,
    range: str | None = None,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _tx_query(db, user.id, month)
    if not month and range:
        start = _history_start(range)
        if start:
            q = q.filter(Transaction.date >= start)
    transactions = q.all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    db_user = db.get(User, user.id)
    currency = db_user.currency_preference if db_user else "INR"
    summary = monthly_summary(transactions)
    quality = data_quality(transactions)
    quality.update(
        {
            "unassigned_account_count": db.query(Transaction.id).filter(
                Transaction.user_id == user.id,
                Transaction.source != "cash",
                Transaction.account_id.is_(None),
            ).count(),
            "active_accounts": db.query(Account.id).filter(
                Account.user_id == user.id, Account.is_active.is_(True)
            ).count(),
            "reconciled_accounts": db.query(Account.id).filter(
                Account.user_id == user.id,
                Account.is_active.is_(True),
                Account.last_reconciled_at.isnot(None),
            ).count(),
            "pending_imports": db.query(ImportJob.id).filter(
                ImportJob.user_id == user.id, ImportJob.status.in_(("pending", "processing"))
            ).count(),
            "failed_imports": db.query(ImportJob.id).filter(
                ImportJob.user_id == user.id, ImportJob.status == "failed"
            ).count(),
            "pending_transactions": db.query(Transaction.id).filter(
                Transaction.user_id == user.id, Transaction.status == "pending"
            ).count(),
            "excluded_transactions": db.query(Transaction.id).filter(
                Transaction.user_id == user.id, Transaction.status == "excluded"
            ).count(),
            "currency_mismatch_count": _account_currency_mismatch_count(db, user.id),
        }
    )
    quality["stale_account_count"] = max(0, quality["active_accounts"] - quality["reconciled_accounts"])
    quality["account_balance_quality"] = (
        "none" if quality["active_accounts"] == 0 else
        "reconciled" if quality["stale_account_count"] == 0 else
        "mixed_or_unreconciled"
    )
    if quality["unassigned_account_count"]:
        quality["warnings"].append("Assign imported transactions to an account for reliable balances")
    if quality["failed_imports"]:
        quality["warnings"].append("Review failed statement imports")
    if quality["pending_transactions"]:
        quality["warnings"].append("Review pending transactions before relying on committed totals")
    if quality["stale_account_count"]:
        quality["warnings"].append("Reconcile active account balances for a stronger balance picture")
    if quality["currency_mismatch_count"]:
        quality["warnings"].append("Account currencies differ from your Ledger currency; combined totals are unreliable")

    summary["closing_balance"] = _get_balance_at(db, user.id, as_of_date=None)
    summary["opening_balance"] = None
    if month:
        period_start_d, period_end = _month_range(month)
        summary["closing_balance"] = _get_balance_at(db, user.id, as_of_date=period_end)
        summary["opening_balance"] = _get_balance_at(db, user.id, as_of_date=period_start_d)
    elif range:
        period_start_d = _history_start(range)
        if period_start_d:
            summary["opening_balance"] = _get_balance_at(db, user.id, as_of_date=period_start_d)

    recurring_rules = db.query(RecurringRule).filter(RecurringRule.user_id == user.id).all()
    summary["analysis"] = build_analysis_object(transactions, summary, quality, recurring_rules)
    summary["analysis"]["comparison"] = compare_periods(transactions, days=30)
    summary["analysis"]["insight_claims"] = compute_insight_claims(transactions, budgets, currency)

    return {
        **summary,
        "insights": compute_insights(transactions, budgets, currency),
        "insight_claims": summary["analysis"]["insight_claims"],
        "recurring": recurring_payments(transactions, db_user.recurring_tolerance if db_user else "standard"),
        "data_quality": quality,
    }
