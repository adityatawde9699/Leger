"""Receipts: OCR scanning and private receipt attachments on transactions."""

import logging
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..db import get_db
from ..helpers import _client_ip
from ..models import ReceiptAttachment, Transaction, User
from ..rate_limit import limiter
from ..schemas import UserContext
from ..services.audit import log_event
from ..services.receipt_ocr import parse_receipt_image

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Receipt OCR ───────────────────────────────────────────────────────────────
@router.post("/receipts/scan")
@limiter.limit(settings.receipt_rate_limit)
async def scan_receipt(
    request: Request,
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    ext = file.filename.lower().rsplit(".", 1)[-1]
    if ext not in ("jpg", "jpeg", "png", "webp"):
        raise HTTPException(status_code=400, detail="Upload an image (jpg, png, webp)")
    if file.size and file.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 5MB)")

    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 5MB)")
    if _receipt_mime(content) not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=400, detail="Upload a PNG, JPEG, or WebP image")
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > 16_000_000:
                raise ValueError("Image dimensions exceed limit")
            image.verify()
    except (ValueError, UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise HTTPException(status_code=400, detail="Invalid receipt image") from exc
    owner = db.get(User, user.id)
    if not owner or not owner.cloud_ai_enabled:
        raise HTTPException(status_code=403, detail="Enable cloud AI in Profile before scanning a receipt")
    result = await parse_receipt_image(content)
    if not result:
        raise HTTPException(status_code=422, detail="Could not extract data from receipt")
    return result


def _receipt_mime(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    return None


@router.post("/transactions/{transaction_id}/receipt", status_code=201)
def attach_receipt(
    transaction_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Keep a small receipt private and linked to its user-owned transaction."""
    # A sync route: FastAPI runs it in the threadpool, so the database work and image
    # validation below do not block the event loop.
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Receipt too large (max 5MB)")
    mime = _receipt_mime(content)
    if not mime:
        raise HTTPException(status_code=400, detail="Upload a PNG, JPEG, WebP, or PDF receipt")
    if tx.receipt:
        if tx.receipt.content == content and tx.receipt.mime_type == mime:
            return {"id": tx.receipt.id, "transaction_id": transaction_id, "mime_type": mime, "size": len(content)}
        raise HTTPException(status_code=409, detail="Transaction already has a receipt; delete it before replacing")
    receipt = ReceiptAttachment(user_id=user.id, transaction_id=transaction_id, content=content, mime_type=mime)
    db.add(receipt)
    db.flush()
    log_event(db, user_id=user.id, action="create", resource_type="receipt", resource_id=receipt.id,
              details={"transaction_id": transaction_id, "mime_type": mime}, ip_address=_client_ip(request))
    db.commit()
    return {"id": receipt.id, "transaction_id": transaction_id, "mime_type": mime, "size": len(content)}


@router.get("/transactions/{transaction_id}/receipt")
def download_receipt(
    transaction_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    receipt = db.query(ReceiptAttachment).filter(
        ReceiptAttachment.user_id == user.id, ReceiptAttachment.transaction_id == transaction_id
    ).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return Response(
        content=receipt.content, media_type=receipt.mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Disposition": 'attachment; filename="ledger-receipt"'},
    )


@router.delete("/transactions/{transaction_id}/receipt")
def remove_receipt(
    transaction_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    receipt = db.query(ReceiptAttachment).filter(
        ReceiptAttachment.user_id == user.id, ReceiptAttachment.transaction_id == transaction_id
    ).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    receipt_id = receipt.id
    db.delete(receipt)
    log_event(db, user_id=user.id, action="delete", resource_type="receipt", resource_id=receipt_id,
              details={"transaction_id": transaction_id}, ip_address=_client_ip(request))
    db.commit()
    return {"deleted": True}
