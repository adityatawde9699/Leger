"""Audit trail and GST report."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..helpers import _tx_query
from ..schemas import AuditLogOut, GSTReportOut, UserContext
from ..services.audit import get_audit_trail
from ..services.gst import generate_gst_report

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Audit Log ─────────────────────────────────────────────────────────────────
@router.get("/audit", response_model=list[AuditLogOut])
def list_audit_logs(
    resource_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_audit_trail(db, user.id, resource_type=resource_type, limit=limit, offset=offset)


# ── GST Report ────────────────────────────────────────────────────────────────
@router.get("/gst/report", response_model=GSTReportOut)
def gst_report(
    month: str | None = Query(None),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = _tx_query(db, user.id, month).all()
    return generate_gst_report(transactions)
