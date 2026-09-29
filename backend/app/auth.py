import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from threading import Lock

from fastapi import Depends, Header, HTTPException, Request
from google.auth.exceptions import TransportError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AppSession, User
from .schemas import UserContext

_google_verify_lock = Lock()
SESSION_COOKIE = "ledger_session"
SESSION_HOURS = 12
logger = logging.getLogger("ledger.auth")


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@lru_cache(maxsize=1)
def _get_google_request():
    """Reuse Google's signing certificates according to their cache headers."""
    import requests
    from cachecontrol import CacheControl
    from google.auth.transport.requests import Request as GoogleRequest

    cached_session = CacheControl(requests.Session())
    return GoogleRequest(session=cached_session)


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return authorization.split(" ", 1)[1].strip()


def _verify_token(token: str) -> UserContext:
    provider = settings.auth_provider.lower()

    if provider == "dev":
        # Dev mode: token value IS the user ID. Warned at startup.
        if not token:
            raise HTTPException(status_code=401, detail="Token required even in dev mode")
        return UserContext(id=token, email=f"{token}@dev.ledger.local")

    if provider == "google":
        try:
            from google.oauth2 import id_token

            if not settings.google_client_id:
                raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID not configured")

            # A newly started worker can receive many dashboard requests at once.
            # Serialize verification so only the first request fills the shared
            # certificate cache; subsequent requests validate locally.
            with _google_verify_lock:
                decoded = id_token.verify_oauth2_token(
                    token,
                    _get_google_request(),
                    settings.google_client_id,
                )
            invalid_claims = []
            if decoded.get("email_verified") is not True:
                invalid_claims.append("email_unverified")
            if decoded.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
                invalid_claims.append("issuer_invalid")
            if decoded.get("aud") != settings.google_client_id:
                invalid_claims.append("audience_mismatch")
            if not isinstance(decoded.get("sub"), str) or not (1 <= len(decoded["sub"]) <= 64):
                invalid_claims.append("subject_invalid")
            if not isinstance(decoded.get("email"), str) or not decoded.get("email"):
                invalid_claims.append("email_missing")
            if not isinstance(decoded.get("exp"), (int, float)) or decoded["exp"] <= datetime.now(UTC).timestamp():
                invalid_claims.append("token_expired")
            if invalid_claims:
                logger.warning("auth.google_token_rejected reasons=%s", ",".join(invalid_claims))
                raise HTTPException(status_code=401, detail="Google ID token has invalid claims")
            return UserContext(
                id=decoded["sub"],
                email=decoded.get("email"),
                name=decoded.get("name"),
                picture=decoded.get("picture")
            )
        except HTTPException:
            raise
        except TransportError as e:
            raise HTTPException(
                status_code=503,
                detail="Google signing keys are temporarily unavailable",
            ) from e
        except Exception as e:
            raise HTTPException(status_code=401, detail="Google ID token is invalid or expired") from e

    raise HTTPException(status_code=500, detail=f"Unsupported AUTH_PROVIDER: {provider}. Use google or dev.")


def create_session(db: Session, user: UserContext) -> str:
    existing = db.get(User, user.id)
    if not existing:
        db.add(User(id=user.id, email=user.email, display_name=user.name, avatar_url=user.picture))
        db.flush()
    else:
        existing.email = user.email
        if not existing.display_name and user.name:
            existing.display_name = user.name
        if not existing.avatar_url and user.picture:
            existing.avatar_url = user.picture
    token = secrets.token_urlsafe(48)
    db.add(AppSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                      expires_at=datetime.now(UTC) + timedelta(hours=SESSION_HOURS)))
    db.commit()
    return token


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UserContext:
    if settings.auth_provider == "google":
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise HTTPException(status_code=401, detail="Session required")
        session = db.get(AppSession, hashlib.sha256(token.encode()).hexdigest())
        if not session or _as_utc(session.expires_at) <= datetime.now(UTC):
            raise HTTPException(status_code=401, detail="Session expired")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin not in settings.get_cors_origins():
                raise HTTPException(status_code=403, detail="Invalid request origin")
        record = db.get(User, session.user_id)
        if not record:
            raise HTTPException(status_code=401, detail="Session user unavailable")
        return UserContext(id=record.id, email=record.email, name=record.display_name, picture=record.avatar_url)
    user = _verify_token(_bearer(authorization))
    # Upsert user record
    existing = db.get(User, user.id)
    if not existing:
        db.add(User(
            id=user.id,
            email=user.email,
            display_name=user.name,
            avatar_url=user.picture
        ))
        db.commit()
    else:
        updated = False
        if not existing.display_name and user.name:
            existing.display_name = user.name
            updated = True
        if not existing.avatar_url and user.picture:
            existing.avatar_url = user.picture
            updated = True
        if updated:
            db.commit()
    return user


def require_recent_auth(request: Request, user: UserContext = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> UserContext:
    if settings.auth_provider != "google":
        return user
    token = request.cookies.get(SESSION_COOKIE)
    session = db.get(AppSession, hashlib.sha256(token.encode()).hexdigest()) if token else None
    if not session or not session.reauthed_at or _as_utc(session.reauthed_at) < datetime.now(UTC) - timedelta(minutes=5):
        raise HTTPException(status_code=428, detail="Recent Google authentication required")
    return user
