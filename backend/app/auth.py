import json
import sys

import httpx
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User
from .schemas import UserContext

# ── JWKS cache (in-process for now; Redis in Phase 2) ───────────────────────
_jwks_cache: dict | None = None


def _get_jwks_sync() -> dict:
    """Fetch Supabase JWKS. Cached in module-level var after first call."""
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache
    if not settings.supabase_jwks_url:
        raise HTTPException(status_code=500, detail="SUPABASE_JWKS_URL not configured")
    try:
        resp = httpx.get(settings.supabase_jwks_url, timeout=10)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        return _jwks_cache
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch JWKS: {e}")


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

    if provider == "firebase":
        try:
            import firebase_admin
            from firebase_admin import auth as firebase_auth
            if not firebase_admin._apps:
                firebase_admin.initialize_app()
            decoded = firebase_auth.verify_id_token(token)
            return UserContext(id=decoded["uid"], email=decoded.get("email"))
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Firebase auth failed: {e}")

    if provider == "supabase":
        try:
            from jose import JWTError, jwt
            jwks = _get_jwks_sync()
            decoded = jwt.decode(
                token, jwks,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            return UserContext(id=decoded["sub"], email=decoded.get("email"))
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Token invalid: {e}")

    raise HTTPException(status_code=500, detail=f"Unknown AUTH_PROVIDER: {provider}")


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UserContext:
    user = _verify_token(_bearer(authorization))
    # Upsert user record
    existing = db.get(User, user.id)
    if not existing:
        db.add(User(id=user.id, email=user.email))
        db.commit()
    return user
