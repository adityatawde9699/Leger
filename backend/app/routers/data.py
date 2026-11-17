"""User data portability: CSV/JSON/Tally export, full export, encrypted backup and restore, erasure."""

import base64
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth import require_recent_auth
from ..cache import llm_cache
from ..config import settings
from ..db import get_db
from ..helpers import _recurring_payload, _tx_query
from ..models import (
    Account,
    AIConversation,
    AIMessage,
    AppSession,
    AuditLog,
    Budget,
    CategoryCorrection,
    Goal,
    Holding,
    ImportJob,
    MerchantAlias,
    Notification,
    Portfolio,
    ReceiptAttachment,
    RecurringRule,
    Transaction,
    User,
    UserCategory,
)
from ..schemas import AccountIn, BackupRestoreRequest, DataDeletionRequest, TransactionIn, UserContext
from ..services.audit import log_event
from ..services.backups import decrypt_backup, encrypt_backup
from ..services.export import export_csv, export_json, export_tally_xml

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Export ─────────────────────────────────────────────────────────────────────
@router.get("/export/{fmt}")
def export_data(
    fmt: str,
    month: str | None = Query(None),
    user: UserContext = Depends(require_recent_auth),
    db: Session = Depends(get_db),
):
    # Keep the legacy parameterized route compatible with the static full-data
    # export even when route registration order puts this handler first.
    if fmt == "full":
        return export_full_data(user, db)
    transactions = _tx_query(db, user.id, month).all()
    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions to export")
    if fmt in {"csv", "json", "tally"}:
        log_event(db, user_id=user.id, action="export", resource_type="transactions", details={"format": fmt})
        db.commit()

    if fmt == "csv":
        content = export_csv(transactions)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=ledger_export.csv"},
        )
    elif fmt == "json":
        content = export_json(transactions)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=ledger_export.json"},
        )
    elif fmt == "tally":
        content = export_tally_xml(transactions)
        return Response(
            content=content,
            media_type="application/xml",
            headers={"Content-Disposition": "attachment; filename=ledger_tally.xml"},
        )
    else:
        raise HTTPException(status_code=400, detail="Format must be csv, json, or tally")


@router.get("/export/full")
def export_full_data(
    user: UserContext = Depends(require_recent_auth),
    db: Session = Depends(get_db),
):
    """Export the user's portable data without secrets or uploaded statement payloads."""
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Profile not found")
    log_event(db, user_id=user.id, action="export", resource_type="full_data")
    db.commit()
    transactions = _tx_query(db, user.id, include_unposted=True).order_by(Transaction.date.asc()).all()
    conversations = db.query(AIConversation).filter(AIConversation.user_id == user.id).all()
    payload = {
        "export_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": {
            "id": db_user.id,
            "email": db_user.email,
            "display_name": db_user.display_name,
            "avatar_url": db_user.avatar_url,
            "currency_preference": db_user.currency_preference,
            "region": db_user.region,
            "income_pattern": db_user.income_pattern,
            "pay_cycle": db_user.pay_cycle,
            "risk_comfort": db_user.risk_comfort,
            "household_mode": db_user.household_mode,
            "recurring_tolerance": db_user.recurring_tolerance,
            "onboarding_completed": db_user.onboarding_completed,
            "cloud_ai_enabled": db_user.cloud_ai_enabled,
            "insight_frequency": db_user.insight_frequency,
            "obligations_reviewed_at": db_user.obligations_reviewed_at.isoformat() if db_user.obligations_reviewed_at else None,
            "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
        },
        "accounts": [
            {
                "id": a.id, "name": a.name, "account_type": a.account_type,
                "institution": a.institution, "balance": str(a.balance), "currency": a.currency,
                "credit_limit": str(a.credit_limit) if a.credit_limit is not None else None,
                "minimum_payment": str(a.minimum_payment) if a.minimum_payment is not None else None,
                "payment_due_date": a.payment_due_date.isoformat() if a.payment_due_date else None,
                "is_active": a.is_active, "last_reconciled_at": a.last_reconciled_at.isoformat() if a.last_reconciled_at else None,
                "last_reconciled_balance": str(a.last_reconciled_balance) if a.last_reconciled_balance is not None else None,
                "reconciliation_note": a.reconciliation_note,
            }
            for a in db.query(Account).filter(Account.user_id == user.id).all()
        ],
        "transactions": json.loads(export_json(transactions))["transactions"],
        "receipts": [
            {"id": r.id, "transaction_id": r.transaction_id, "mime_type": r.mime_type,
             "content_base64": base64.b64encode(r.content).decode("ascii")}
            for r in db.query(ReceiptAttachment).filter(ReceiptAttachment.user_id == user.id).all()
        ],
        "budgets": [
            {"id": b.id, "category": b.category, "monthly_limit": str(b.monthly_limit), "strategy": b.strategy}
            for b in db.query(Budget).filter(Budget.user_id == user.id).all()
        ],
        "merchant_aliases": [
            {"id": a.id, "alias": a.alias_key, "canonical": a.canonical,
             "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in db.query(MerchantAlias).filter(MerchantAlias.user_id == user.id).all()
        ],
        "categories": [
            {"id": c.id, "name": c.name, "kind": c.kind, "reporting_group": c.reporting_group,
             "is_active": c.is_active, "created_at": c.created_at.isoformat() if c.created_at else None}
            for c in db.query(UserCategory).filter(UserCategory.user_id == user.id).all()
        ],
        "recurring_rules": [_recurring_payload(rule) for rule in db.query(RecurringRule).filter(RecurringRule.user_id == user.id).all()],
        "goals": [
            {"id": g.id, "name": g.name, "goal_type": g.goal_type, "target_amount": str(g.target_amount),
             "current_amount": str(g.current_amount), "deadline": g.deadline.isoformat() if g.deadline else None, "status": g.status}
            for g in db.query(Goal).filter(Goal.user_id == user.id).all()
        ],
        "portfolios": [
            {"id": p.id, "name": p.name, "portfolio_type": p.portfolio_type,
             "holdings": [
                 {"id": h.id, "symbol": h.symbol, "name": h.name, "quantity": str(h.quantity),
                  "buy_price": str(h.buy_price), "current_price": str(h.current_price), "asset_type": h.asset_type,
                  "purchase_date": h.purchase_date.isoformat() if h.purchase_date else None, "notes": h.notes}
                 for h in p.holdings
             ]}
            for p in db.query(Portfolio).filter(Portfolio.user_id == user.id).all()
        ],
        "conversations": [
            {"id": c.id, "title": c.title, "created_at": c.created_at.isoformat() if c.created_at else None,
             "messages": [{"id": m.id, "role": m.role, "content": m.content,
                           "created_at": m.created_at.isoformat() if m.created_at else None} for m in c.messages]}
            for c in conversations
        ],
        "imports": [
            {"id": j.id, "status": j.status, "file_name": j.file_name, "file_extension": j.file_extension,
             "account_id": j.account_id, "row_count": j.row_count, "error_message": j.error_message,
             "created_at": j.created_at.isoformat() if j.created_at else None,
             "updated_at": j.updated_at.isoformat() if j.updated_at else None}
            for j in db.query(ImportJob).filter(ImportJob.user_id == user.id).all()
        ],
        "category_corrections": [
            {"description_hash": c.description_hash, "category": c.category, "correction_count": c.correction_count}
            for c in db.query(CategoryCorrection).filter(CategoryCorrection.user_id == user.id).all()
        ],
        "audit_log": [
            {"action": a.action, "resource_type": a.resource_type, "resource_id": a.resource_id,
             "details": a.details, "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in db.query(AuditLog).filter(AuditLog.user_id == user.id).order_by(AuditLog.created_at.asc()).all()
        ],
        "notifications": [
            {"id": n.id, "kind": n.kind, "insight_id": n.insight_id, "text": n.text, "read": n.read,
             "created_at": n.created_at.isoformat() if n.created_at else None}
            for n in db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.created_at.asc()).all()
        ],
    }
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=ledger_full_export.json"},
    )


@router.get("/backup/export")
def encrypted_backup_export(
    user: UserContext = Depends(require_recent_auth),
    db: Session = Depends(get_db),
):
    """Export the portable dataset as authenticated encrypted text."""
    if not settings.backup_encryption_key:
        raise HTTPException(status_code=503, detail="Encrypted backups are not configured")
    exported = export_full_data(user, db)
    token = encrypt_backup(json.loads(exported.body), settings.backup_encryption_key)
    log_event(db, user_id=user.id, action="export", resource_type="encrypted_backup")
    db.commit()
    return {"format": "ledger-fernet-v1", "encrypted_backup": token}


def _validated_backup_records(backup: dict) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]]]:
    """Validate every backup record against the API schemas before anything is written.

    Returns (id, fields) pairs; raises 400 on the first invalid record so a bad backup
    restores nothing instead of failing half-way with a 500.
    """
    def record_id(item: dict) -> str:
        value = item.get("id")
        if not isinstance(value, str) or not 1 <= len(value) <= 36:
            raise ValueError("missing or invalid id")
        return value

    raw_accounts, raw_transactions = backup.get("accounts", []), backup.get("transactions", [])
    if not isinstance(raw_accounts, list) or not isinstance(raw_transactions, list):
        raise HTTPException(status_code=400, detail="Backup records are malformed")
    accounts, transactions = [], []
    try:
        for item in raw_accounts:
            fields = AccountIn(**{k: v for k, v in item.items() if k in AccountIn.model_fields}).model_dump()
            fields["is_active"] = bool(item.get("is_active", True))
            accounts.append((record_id(item), fields))
        for item in raw_transactions:
            fields = TransactionIn(**{k: v for k, v in item.items() if k in TransactionIn.model_fields}).model_dump()
            transactions.append((record_id(item), fields))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail="Backup contains an invalid record") from exc
    return accounts, transactions


@router.post("/backup/restore")
def encrypted_backup_restore(
    payload: BackupRestoreRequest,
    user: UserContext = Depends(require_recent_auth),
    db: Session = Depends(get_db),
):
    """Validate or restore core portable records after explicit confirmation."""
    if not settings.backup_encryption_key:
        raise HTTPException(status_code=503, detail="Encrypted backups are not configured")
    try:
        backup = decrypt_backup(payload.encrypted_backup, settings.backup_encryption_key,
                                settings.backup_previous_encryption_keys)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Backups are encrypted with one server-wide key, so the key alone does not prove
    # ownership: only restore a backup that was exported from this same account.
    profile = backup.get("profile")
    if not isinstance(profile, dict) or profile.get("id") != user.id:
        raise HTTPException(status_code=403, detail="This backup belongs to a different account")
    accounts, transactions = _validated_backup_records(backup)
    if payload.dry_run:
        log_event(db, user_id=user.id, action="validate", resource_type="backup_restore")
        db.commit()
        return {"ok": True, "dry_run": True, "accounts": len(accounts), "transactions": len(transactions)}
    restored_accounts = 0
    for record_id, account in accounts:
        if db.get(Account, record_id):
            continue
        db.add(Account(id=record_id, user_id=user.id, **account))
        restored_accounts += 1
    restored_transactions = 0
    for record_id, tx in transactions:
        if db.get(Transaction, record_id):
            continue
        account_id = tx.pop("account_id", None)
        if account_id:
            account = db.get(Account, account_id)
            if not account or account.user_id != user.id:
                account_id = None
        db.add(Transaction(id=record_id, user_id=user.id, account_id=account_id, **tx))
        restored_transactions += 1
    log_event(db, user_id=user.id, action="restore", resource_type="backup",
              details={"accounts": restored_accounts, "transactions": restored_transactions})
    db.commit()
    llm_cache.invalidate_user(user.id)
    return {"ok": True, "dry_run": False, "accounts": restored_accounts, "transactions": restored_transactions}


@router.delete("/profile/data")
def delete_all_user_data(
    payload: DataDeletionRequest,
    request: Request,
    user: UserContext = Depends(require_recent_auth),
    db: Session = Depends(get_db),
):
    """Permanently erase all Ledger data for the signed-in user after explicit confirmation."""
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Delete dependents explicitly so this remains safe on databases without
    # database-level ON DELETE CASCADE configuration.
    portfolio_ids = [p.id for p in db.query(Portfolio.id).filter(Portfolio.user_id == user.id).all()]
    if portfolio_ids:
        db.query(Holding).filter(Holding.portfolio_id.in_(portfolio_ids)).delete(synchronize_session=False)
    conversation_ids = [c.id for c in db.query(AIConversation.id).filter(AIConversation.user_id == user.id).all()]
    if conversation_ids:
        db.query(AIMessage).filter(AIMessage.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
    counts = {
        "receipts": db.query(ReceiptAttachment).filter(ReceiptAttachment.user_id == user.id).delete(synchronize_session=False),
        "transactions": db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False),
        "accounts": db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False),
        "budgets": db.query(Budget).filter(Budget.user_id == user.id).delete(synchronize_session=False),
        "merchant_aliases": db.query(MerchantAlias).filter(MerchantAlias.user_id == user.id).delete(synchronize_session=False),
        "categories": db.query(UserCategory).filter(UserCategory.user_id == user.id).delete(synchronize_session=False),
        "recurring_rules": db.query(RecurringRule).filter(RecurringRule.user_id == user.id).delete(synchronize_session=False),
        "goals": db.query(Goal).filter(Goal.user_id == user.id).delete(synchronize_session=False),
        "imports": db.query(ImportJob).filter(ImportJob.user_id == user.id).delete(synchronize_session=False),
        "portfolios": db.query(Portfolio).filter(Portfolio.user_id == user.id).delete(synchronize_session=False),
        "conversations": db.query(AIConversation).filter(AIConversation.user_id == user.id).delete(synchronize_session=False),
        "category_corrections": db.query(CategoryCorrection).filter(CategoryCorrection.user_id == user.id).delete(synchronize_session=False),
        "audit_logs": db.query(AuditLog).filter(AuditLog.user_id == user.id).delete(synchronize_session=False),
        "notifications": db.query(Notification).filter(Notification.user_id == user.id).delete(synchronize_session=False),
        "sessions": db.query(AppSession).filter(AppSession.user_id == user.id).delete(synchronize_session=False),
    }
    db.delete(db_user)
    db.commit()
    llm_cache.invalidate_user(user.id)
    logger.info("profile.data_deleted user=%s counts=%s", user.id, counts)
    return {"deleted": True, "counts": counts}
