import json
from functools import lru_cache

import httpx
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User
from .schemas import UserContext


@lru_cache(maxsize=1)
def _get_supabase_jwks(url: str):
    response = httpx.get(url, timeout=10.0)
    response.raise_for_status()
    return response.json()


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

    if provider in ("firebase", "google"):
        try:
            import firebase_admin
            from firebase_admin import auth as firebase_auth
            from firebase_admin import credentials

            if not firebase_admin._apps:
                if settings.firebase_service_account_json:
                    service_account = json.loads(settings.firebase_service_account_json)
                    firebase_admin.initialize_app(
                        credentials.Certificate(service_account),
                        {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None,
                    )
                else:
                    options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None
                    if options:
                        firebase_admin.initialize_app(options=options)
                    else:
                        firebase_admin.initialize_app()
            decoded = firebase_auth.verify_id_token(token)
            return UserContext(
                id=decoded["uid"],
                email=decoded.get("email"),
                name=decoded.get("name"),
                picture=decoded.get("picture")
            )
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Firebase auth failed: {e}")

    if provider == "supabase":
        try:
            from jose import jwt

            if not settings.supabase_jwks_url:
                raise HTTPException(status_code=500, detail="SUPABASE_JWKS_URL not configured")

            jwks = _get_supabase_jwks(settings.supabase_jwks_url)

            decoded = jwt.decode(
                token,
                jwks,
                algorithms=["ES256", "RS256", "HS256"],
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
