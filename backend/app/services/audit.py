"""
Audit logging service — records all data mutations for compliance.
Every create/update/delete on transactions, budgets, accounts is logged.
"""
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditLog

logger = logging.getLogger("ledger.audit")


def log_event(
    db: Session,
    *,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """
    Record an audit event. This is append-only — no updates or deletes.
    
    Args:
        action: "create", "update", "delete"
        resource_type: "transaction", "budget", "account", "import", "webhook"
        details: Any JSON-serializable diff/context
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=json.dumps(details) if details else None,
        ip_address=ip_address,
    )
    db.add(entry)
    # Don't commit here — let the caller's transaction commit it together
    logger.debug(
        "audit.%s user=%s %s/%s",
        action, user_id, resource_type, resource_id or "—",
    )
    return entry


def get_audit_trail(
    db: Session,
    user_id: str,
    *,
    resource_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    """Query audit trail with optional filtering."""
    q = db.query(AuditLog).filter(AuditLog.user_id == user_id)
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    return q.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
