"""Sign-in: Google ID token exchange for a server session cookie, re-authentication and sign-out."""

import base64
import hashlib
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import SESSION_COOKIE, SESSION_HOURS, _verify_token, create_session, get_current_user
from ..config import settings
from ..db import get_db
from ..models import AppSession
from ..schemas import UserContext

router = APIRouter()
logger = logging.getLogger("ledger.api")


class GoogleLogin(BaseModel):
    credential: str = Field(min_length=20, max_length=8192)


@router.post("/auth/session")
def login_session(payload: GoogleLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    if settings.auth_provider != "google":
        raise HTTPException(status_code=404, detail="Unavailable")
    if request.headers.get("origin") not in settings.get_cors_origins():
        raise HTTPException(status_code=403, detail="Invalid request origin")
    user = _verify_token(payload.credential)
    old_token = request.cookies.get(SESSION_COOKIE)
    if old_token:
        db.query(AppSession).filter(AppSession.token_hash == hashlib.sha256(old_token.encode()).hexdigest()).delete()
    token = create_session(db, user)
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True,
                        secure=settings.environment == "production",
                        samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"user": user.model_dump()}


@router.get("/auth/session")
def read_session(user: UserContext = Depends(get_current_user)):
    return {"user": user.model_dump()}


@router.post("/auth/reauth")
def reauthenticate(payload: GoogleLogin, request: Request, user: UserContext = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    claims = _verify_token(payload.credential)
    try:
        encoded = payload.credential.split(".")[1]
        decoded = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (IndexError, ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Google credential") from exc
    if claims.id != user.id or not isinstance(decoded.get("iat"), (int, float)) or not (
        datetime.now(UTC).timestamp() - 300 <= decoded["iat"] <= datetime.now(UTC).timestamp() + 60
    ):
        raise HTTPException(status_code=401, detail="Recent Google authentication required")
    token = request.cookies.get(SESSION_COOKIE)
    session = db.get(AppSession, hashlib.sha256(token.encode()).hexdigest())
    session.reauthed_at = datetime.now(UTC)
    db.commit()
    return {"ok": True}


@router.delete("/auth/session")
def logout_session(request: Request, response: Response, db: Session = Depends(get_db)):
    if request.headers.get("origin") not in settings.get_cors_origins():
        raise HTTPException(status_code=403, detail="Invalid request origin")
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.query(AppSession).filter(AppSession.token_hash == hashlib.sha256(token.encode()).hexdigest()).delete()
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.environment == "production",
                           samesite="lax")
    return {"ok": True}
