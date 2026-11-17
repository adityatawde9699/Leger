"""The user's profile, preferences, retention policy and profile statistics."""

import base64
import logging
from decimal import Decimal
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..cache import llm_cache
from ..config import settings
from ..db import get_db
from ..models import Account, Budget, Transaction, User
from ..schemas import ProfileStatsOut, UserContext, UserProfileIn, UserProfileOut

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Profile ───────────────────────────────────────────────────────────────────
def _relevant_account_currencies(db: Session, user_id: str) -> list[str]:
    linked_account_ids = db.query(Transaction.account_id).filter(
        Transaction.user_id == user_id,
        Transaction.account_id.isnot(None),
    )
    return [currency for (currency,) in db.query(Account.currency).filter(
        Account.user_id == user_id,
        or_(Account.is_active.is_(True), Account.id.in_(linked_account_ids)),
    ).all()]


@router.get("/profile", response_model=UserProfileOut)
def get_profile(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@router.get("/privacy/retention")
def get_retention_policy(user: UserContext = Depends(get_current_user)):
    return {"ai_conversation_days": settings.ai_conversation_retention_days,
            "financial_records": "until_deleted", "external_backups": "user_or_operator_managed"}


@router.put("/profile", response_model=UserProfileOut)
def update_profile(
    payload: UserProfileIn,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.display_name is not None:
        db_user.display_name = payload.display_name.strip() or None
    if payload.avatar_url is not None:
        if payload.avatar_url.startswith("data:"):
            try:
                prefix, encoded = payload.avatar_url.split(",", 1)
                if prefix not in {"data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"}:
                    raise ValueError("Unsupported avatar type")
                raw = base64.b64decode(encoded, validate=True)
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError("Avatar too large")
                with Image.open(BytesIO(raw)) as image:
                    if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > 16_000_000:
                        raise ValueError("Invalid avatar dimensions or format")
                    image.verify()
            except (ValueError, UnidentifiedImageError, OSError, SyntaxError) as exc:
                raise HTTPException(status_code=400, detail="Invalid avatar image") from exc
        elif payload.avatar_url and not (payload.avatar_url.startswith("https://") and len(payload.avatar_url) <= 2048):
            raise HTTPException(status_code=400, detail="Invalid avatar URL")
        db_user.avatar_url = payload.avatar_url
    if payload.currency_preference is not None:
        db_user.currency_preference = payload.currency_preference
    if payload.region is not None:
        db_user.region = payload.region
    if payload.income_pattern is not None:
        db_user.income_pattern = payload.income_pattern
    if payload.pay_cycle is not None:
        db_user.pay_cycle = payload.pay_cycle
    if payload.risk_comfort is not None:
        db_user.risk_comfort = payload.risk_comfort
    if payload.household_mode is not None:
        db_user.household_mode = payload.household_mode
    if payload.recurring_tolerance is not None:
        db_user.recurring_tolerance = payload.recurring_tolerance
    if payload.onboarding_completed is not None:
        db_user.onboarding_completed = payload.onboarding_completed
    if payload.cloud_ai_enabled is not None:
        db_user.cloud_ai_enabled = payload.cloud_ai_enabled
    if payload.insight_frequency is not None:
        db_user.insight_frequency = payload.insight_frequency
    if payload.quiet_hours_start is not None:
        db_user.quiet_hours_start = payload.quiet_hours_start
    if payload.quiet_hours_end is not None:
        db_user.quiet_hours_end = payload.quiet_hours_end
    if payload.proactive_daily_cap is not None:
        db_user.proactive_daily_cap = payload.proactive_daily_cap
    db.commit()
    db.refresh(db_user)
    llm_cache.invalidate_user(user.id)
    logger.info("profile.updated user=%s", user.id)
    return db_user


@router.get("/profile/stats", response_model=ProfileStatsOut)
def get_profile_stats(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    # SQLite-compatible separate aggregate queries
    total_txns = db.query(func.count(Transaction.id)).filter(Transaction.user_id == user.id).scalar() or 0
    total_income = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.user_id == user.id, Transaction.status == "posted", Transaction.type == "income"
    ).scalar() or Decimal("0")
    signed_expense = case(
        (Transaction.type == "expense", Transaction.amount),
        (Transaction.type.in_(("refund", "reimbursement")), -Transaction.amount),
        else_=0,
    )
    total_expenses = db.query(func.coalesce(func.sum(signed_expense), 0)).filter(
        Transaction.user_id == user.id, Transaction.status == "posted", Transaction.type.in_(("expense", "refund", "reimbursement"))
    ).scalar() or Decimal("0")
    accounts_count = (
        db.query(func.count(Account.id)).filter(Account.user_id == user.id, Account.is_active.is_(True)).scalar() or 0
    )
    budgets_count = db.query(func.count(Budget.id)).filter(Budget.user_id == user.id).scalar() or 0

    return ProfileStatsOut(
        total_transactions=total_txns,
        total_income=total_income,
        total_expenses=total_expenses,
        net_balance=total_income - total_expenses,
        accounts_count=accounts_count,
        budgets_count=budgets_count,
    )
