"""In-app notifications produced by the maintenance loop."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Notification
from ..schemas import UserContext

router = APIRouter()
logger = logging.getLogger("ledger.api")


@router.get("/notifications")
def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(limit).all()


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read = True
    db.commit()
    return {"ok": True, "id": notification.id, "read": True}
