"""Request helpers shared by several routers and the workers: queries, fingerprints, balances, formatting."""

import base64
import hashlib
import json
import logging
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .models import Account, MerchantAlias, RecurringRule, Transaction, User
from .services.currency import format_amount

logger = logging.getLogger("ledger.api")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _month_range(month: str) -> tuple[date, date]:
    try:
        if len(month) != 7:
            raise ValueError(month)
        start = date.fromisoformat(f"{month}-01")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format") from exc
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start, end


def _cloud_ai_allowed(db: Session, user_id: str) -> bool:
    """True only when the user has opted in to sending data to cloud AI providers."""
    owner = db.get(User, user_id)
    return bool(owner and owner.cloud_ai_enabled)


def _tx_query(db: Session, user_id: str, month: str | None = None, *, include_unposted: bool = False):
    q = db.query(Transaction).filter(Transaction.user_id == user_id)
    if not include_unposted:
        q = q.filter(Transaction.status == "posted")
    if month:
        start, end = _month_range(month)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    return q.order_by(Transaction.date.desc(), Transaction.created_at.desc())


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _statement_row_fingerprint(row: dict, account_id: str | None = None) -> str:
    """Stable row identity that preserves legitimate same-value transactions across accounts."""
    row_date = row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"])
    description = " ".join(str(row.get("description", "")).casefold().split())
    raw = f"statement:v2|{account_id or 'unassigned'}|{row_date}|{row.get('type', 'expense')}|{row['amount']}|{description}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _apply_import_review_overrides(
    rows: list[dict],
    review_overrides: dict,
    account_id: str | None,
) -> None:
    """Apply user-confirmed inferred fields after model inference, in place."""
    for row in rows:
        original_fingerprint = _statement_row_fingerprint(row, account_id)
        override = review_overrides.get(original_fingerprint, {})
        if not isinstance(override, dict):
            continue
        category = override.get("category")
        if isinstance(category, str) and category.strip() and len(category.strip()) <= 64:
            row["category"] = category.strip()
        merchant = override.get("merchant_normalized")
        if isinstance(merchant, str) and len(merchant.strip()) <= 128:
            row["merchant_normalized"] = merchant.strip() or None
        tx_type = override.get("type")
        if tx_type in {"income", "expense", "refund", "reimbursement", "transfer"}:
            row["type"] = tx_type


def _merchant_key(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _resolve_merchant_alias(db: Session, user_id: str, description: str, proposed: str | None = None) -> str | None:
    """Apply a user alias while retaining the original statement description."""
    candidates = {_merchant_key(description)}
    if proposed:
        candidates.add(_merchant_key(proposed))
    alias = (
        db.query(MerchantAlias)
        .filter(MerchantAlias.user_id == user_id, MerchantAlias.alias_key.in_(candidates))
        .order_by(MerchantAlias.created_at.desc())
        .first()
    )
    return alias.canonical if alias else proposed


def _merchant_alias_map(db: Session, user_id: str) -> dict[str, tuple[datetime, str]]:
    """All of a user's aliases in one query, for resolving many rows in memory."""
    return {
        alias.alias_key: (alias.created_at, alias.canonical)
        for alias in db.query(MerchantAlias).filter(MerchantAlias.user_id == user_id)
    }


def _alias_from_map(aliases: dict[str, tuple[datetime, str]], description: str, proposed: str | None) -> str | None:
    """In-memory equivalent of _resolve_merchant_alias: the newest matching alias wins."""
    keys = {_merchant_key(description)} | ({_merchant_key(proposed)} if proposed else set())
    matches = [aliases[key] for key in keys if key in aliases]
    if not matches:
        return proposed
    # SQLite returns naive datetimes and PostgreSQL aware ones; compare as timestamps.
    return max(matches, key=lambda match: match[0].timestamp() if match[0] else 0.0)[1]


def _recurring_payload(rule: RecurringRule) -> dict:
    return {
        "id": rule.id,
        "description": rule.description,
        "category": rule.category,
        "cadence": rule.cadence,
        "average_amount": rule.average_amount,
        "minimum_amount": rule.minimum_amount,
        "maximum_amount": rule.maximum_amount,
        "next_expected": rule.next_expected,
        "confidence": rule.confidence,
        "status": rule.status,
        "confirmed": rule.confirmed,
        "evidence_transaction_ids": json.loads(rule.evidence_transaction_ids or "[]"),
        "confirmed_at": rule.confirmed_at,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _get_balance_at(
    db: Session,
    user_id: str,
    as_of_date: date | None = None,
    exclude_id: str | None = None,
) -> Decimal | None:
    """
    Returns the true running balance for a user as of (but NOT including)
    `as_of_date`. If `as_of_date` is None, returns the current balance.

    Strategy (pure SQL, no Python ordering tricks):
    1. Find the LAST transaction that has a bank-reported running_balance,
       ordered strictly by (date DESC, created_at DESC, stmt_seq DESC NULLS LAST).
       This is our "anchor" — the most recently known authoritative balance.
    2. Sum all transactions that came in STRICTLY AFTER the anchor row
       (same ordering criteria, using anchors values as the inequality boundary)
       to compute the net_change since that anchor.
    3. Return anchor.running_balance + net_change.
    """
    from sqlalchemy import and_, case, func, or_

    # ── Step 1: find the anchor row ──
    anchor_q = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.status == "posted",
        Transaction.running_balance.isnot(None),
        Transaction.source != "cash",
    )
    if as_of_date:
        anchor_q = anchor_q.filter(Transaction.date < as_of_date)
    if exclude_id:
        anchor_q = anchor_q.filter(Transaction.id != exclude_id)

    anchor = anchor_q.order_by(
        Transaction.date.desc(),
        Transaction.created_at.desc(),
        Transaction.stmt_seq.desc().nulls_last(),
    ).first()

    if anchor is None:
        return None

    # ── Step 2: sum all transactions AFTER the anchor ──
    # "after" means: date > anchor.date
    #              OR (date == anchor.date AND created_at > anchor.created_at)
    #              OR (date == anchor.date AND created_at == anchor.created_at
    #                  AND COALESCE(stmt_seq, MAX_INT) > COALESCE(anchor.stmt_seq, MAX_INT))
    anchor_seq = anchor.stmt_seq if anchor.stmt_seq is not None else 2_147_483_647

    after_filter = or_(
        Transaction.date > anchor.date,
        and_(
            Transaction.date == anchor.date,
            Transaction.created_at > anchor.created_at,
        ),
        and_(
            Transaction.date == anchor.date,
            Transaction.created_at == anchor.created_at,
            func.coalesce(Transaction.stmt_seq, 2147483647) > anchor_seq,
        ),
    )

    # Single SQL aggregate (income + refund - expense) instead of pulling every row into
    # Python and summing. Avoids O(n²) work when this is called per-row during
    # statement import, and keeps memory flat regardless of history size.
    signed_amount = case(
        (Transaction.type.in_(("income", "refund", "reimbursement")), Transaction.amount),
        (Transaction.type == "expense", -Transaction.amount),
        else_=0,
    )
    net_q = db.query(func.coalesce(func.sum(signed_amount), 0)).filter(
        Transaction.user_id == user_id,
        Transaction.status == "posted",
        Transaction.id != anchor.id,
        Transaction.source != "cash",
        after_filter,
    )
    if as_of_date:
        net_q = net_q.filter(Transaction.date < as_of_date)
    if exclude_id:
        net_q = net_q.filter(Transaction.id != exclude_id)

    net_change = Decimal(str(net_q.scalar() or 0))

    return anchor.running_balance + net_change


def _history_start(range_key: str | None) -> date | None:
    from datetime import date as dt_date
    from datetime import timedelta

    today = dt_date.today()
    if range_key == "this_month":
        return today.replace(day=1)
    if range_key == "30d":
        return today - timedelta(days=30)
    if range_key == "current_year":
        return today.replace(month=1, day=1)
    if not range_key or range_key == "3m":
        return today - timedelta(days=92)
    if range_key == "1y":
        return today - timedelta(days=365)
    if range_key == "all":
        return None
    raise HTTPException(status_code=400, detail="range must be this_month, 30d, 3m, current_year, 1y, or all")


def _cursor_encode(tx: Transaction) -> str:
    return base64.urlsafe_b64encode(f"{tx.date}|{tx.id}".encode()).decode()


def _cursor_decode(cursor: str) -> tuple[date, str]:
    decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
    date_str, tx_id = decoded.split("|", 1)
    return date.fromisoformat(date_str), tx_id


def _wants_last_transaction(question: str) -> bool:
    text = question.lower()
    return "last transaction" in text or "latest transaction" in text or "most recent transaction" in text


def _wants_overspending(question: str) -> bool:
    text = question.lower()
    return "overspending" in text or "spending most" in text or "spent most" in text or "most spend" in text


def _format_transaction(tx: Transaction, currency: str = "INR") -> str:
    direction = {"income": "income", "expense": "expense", "refund": "refund", "transfer": "transfer"}.get(tx.type, tx.type)
    return (
        f"Your latest transaction is {direction} of {format_amount(tx.amount, currency)} on {tx.date.isoformat()} "
        f"for {tx.description} in {tx.category}."
    )


def _format_overspending(transactions: list[Transaction], currency: str = "INR") -> str:
    from collections import defaultdict

    totals = defaultdict(lambda: {"amount": 0, "count": 0})
    dates = [tx.date for tx in transactions]
    for tx in transactions:
        if tx.type != "expense":
            continue
        totals[tx.category]["amount"] += float(tx.amount)
        totals[tx.category]["count"] += 1
    if not totals:
        return "No expense transactions were found for this signed-in account."
    ranked = sorted(totals.items(), key=lambda item: item[1]["amount"], reverse=True)
    top = ranked[0]
    runners = ", ".join(f"{cat}: {format_amount(data['amount'], currency)}" for cat, data in ranked[1:4])
    extra = f" Next highest: {runners}." if runners else ""
    period = f" from {min(dates).isoformat()} to {max(dates).isoformat()}" if dates else ""
    return (
        f"You are spending most{period} in {top[0]}: {format_amount(top[1]['amount'], currency)} "
        f"across {top[1]['count']} transactions.{extra}"
    )


def _transaction_snapshot(tx: Transaction) -> dict:
    """Serialize the editable transaction fields for an auditable one-step undo."""
    return {
        "date": tx.date.isoformat(),
        "type": tx.type,
        "status": getattr(tx, "status", "posted"),
        "category": tx.category,
        "amount": str(tx.amount),
        "description": tx.description,
        "merchant_normalized": tx.merchant_normalized,
        "confidence": tx.confidence,
        "source": tx.source,
        "source_ref": tx.source_ref,
        "account_id": tx.account_id,
        "tags": tx.tags,
        "notes": tx.notes,
        "running_balance": str(tx.running_balance) if tx.running_balance is not None else None,
        "stmt_seq": tx.stmt_seq,
    }


# ── Summary ───────────────────────────────────────────────────────────────────
def _account_currency_mismatch_count(db: Session, user_id: str) -> int:
    db_user = db.get(User, user_id)
    if not db_user:
        return 0
    return db.query(Account.id).filter(
        Account.user_id == user_id,
        Account.is_active.is_(True),
        Account.currency != db_user.currency_preference,
    ).count()
