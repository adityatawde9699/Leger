"""Advisor conversations: history, messages, deletion and completing suggested actions."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..db import get_db
from ..helpers import _client_ip
from ..models import AIConversation, Transaction
from ..schemas import AdvisorActionRequest, ConversationOut, MessageOut, UserContext
from ..services.audit import log_event
from ..services.privacy import purge_expired_conversations
from ..services.telemetry import record_telemetry

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Conversations ─────────────────────────────────────────────────────────────
@router.post("/advisor/actions/complete")
def complete_advisor_action(
    payload: AdvisorActionRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record explicit user confirmation of a suggested navigation/review action."""
    valid_ids = {
        tx_id for (tx_id,) in db.query(Transaction.id).filter(
            Transaction.user_id == user.id,
            Transaction.id.in_(payload.transaction_ids or ["__none__"]),
        ).all()
    }
    evidence_ids = [tx_id for tx_id in payload.transaction_ids if tx_id in valid_ids]
    if payload.conversation_id:
        conversation_exists = db.query(AIConversation.id).filter(
            AIConversation.id == payload.conversation_id,
            AIConversation.user_id == user.id,
        ).first()
        if not conversation_exists:
            raise HTTPException(status_code=404, detail="Conversation not found")
    log_event(
        db,
        user_id=user.id,
        action="completed_action",
        resource_type="advisor_action",
        resource_id=payload.action_type,
        details={
            "action_type": payload.action_type,
            "evidence_count": len(evidence_ids),
            "conversation_id": payload.conversation_id,
        },
        ip_address=_client_ip(request),
    )
    record_telemetry(
        "advisor.action_completed",
        user_id=user.id,
        outcome=payload.action_type,
        metadata={"evidence_count": len(evidence_ids)},
    )
    db.commit()
    return {"ok": True, "action_type": payload.action_type, "evidence_count": len(evidence_ids)}


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    purge_expired_conversations(db, user.id, settings.ai_conversation_retention_days)
    return (
        db.query(AIConversation)
        .filter(AIConversation.user_id == user.id)
        .order_by(AIConversation.updated_at.desc())
        .limit(20)
        .all()
    )


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageOut])
def get_conversation_messages(
    conv_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(AIConversation)
        .filter(
            AIConversation.id == conv_id,
            AIConversation.user_id == user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return sorted(conv.messages, key=lambda m: m.created_at)


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(AIConversation)
        .filter(
            AIConversation.id == conv_id,
            AIConversation.user_id == user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conv)
    db.commit()
    logger.info("conversation.deleted user=%s id=%s", user.id, conv_id)
    return {"deleted": True}
