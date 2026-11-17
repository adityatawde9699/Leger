"""In-process TTL cache backed by shared Redis, plus the per-user cache version used in insight cache keys."""

import logging
import time

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .models import AuditLog
from .services.shared_cache import SharedTTLCache
from .services.upstash_redis import get_redis_client

logger = logging.getLogger("ledger.api")


# ── Tiered TTL Cache (L1: in-memory with TTL) ─────────────────────────────────
class TTLCache:
    """LRU cache with per-entry TTL expiry and user-scoped keys."""

    def __init__(self, maxsize: int = 512, default_ttl: int = 3600):
        self._cache: dict[str, dict] = {}
        self.maxsize = maxsize
        self.default_ttl = default_ttl

    def _evict_expired(self):
        now = time.time()
        expired = [k for k, v in self._cache.items() if v["expires"] < now]
        for k in expired:
            del self._cache[k]

    def get(self, key: str):
        entry = self._cache.get(key)
        if not entry:
            return None
        if entry["expires"] < time.time():
            del self._cache[key]
            return None
        # Move to end (LRU)
        val = self._cache.pop(key)
        self._cache[key] = val
        return val["data"]

    def put(self, key: str, value, ttl: int | None = None):
        self._evict_expired()
        if key in self._cache:
            self._cache.pop(key)
        self._cache[key] = {
            "data": value,
            "expires": time.time() + (ttl or self.default_ttl),
        }
        if len(self._cache) > self.maxsize:
            self._cache.pop(next(iter(self._cache)))

    def invalidate_user(self, user_id: str):
        """Invalidate all cache entries for a specific user."""
        keys = [k for k in self._cache if k.startswith(f"{user_id}:")]
        for k in keys:
            del self._cache[k]


llm_cache = SharedTTLCache(
    TTLCache(maxsize=512, default_ttl=settings.llm_cache_ttl_seconds),
    redis_client=get_redis_client(),
)


def _user_cache_version(db: Session, user_id: str) -> str:
    """Return a DB-visible mutation version so separate workers avoid stale L1 values."""
    count, latest = db.query(
        func.count(AuditLog.id),
        func.max(AuditLog.created_at),
    ).filter(AuditLog.user_id == user_id).one()
    return f"{count}:{latest or 'none'}"
