"""Optional Redis L2 cache with a fail-open in-process fallback.

The cache only stores derived, user-scoped values. Redis is never required for
application correctness: a connection failure disables L2 for that worker and
the existing TTL cache remains authoritative for the request.
"""

import json
import logging

logger = logging.getLogger("ledger.shared_cache")


class SharedTTLCache:
    """Wrap an existing local TTL cache with optional Redis read-through/write-through."""

    def __init__(
        self,
        local_cache,
        *,
        redis_client=None,
        namespace: str = "ledger:derived",
    ):
        self.local = local_cache
        self._redis = redis_client
        self.namespace = namespace
        self._disabled = redis_client is None
        self._checked = False

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def _client(self):
        if self._disabled or self._redis is None:
            return None
        if self._checked:
            return self._redis
        try:
            self._redis.ping()
            self._checked = True
            return self._redis
        except Exception as exc:  # Redis is an optimization, never a hard dependency.
            logger.warning("shared cache unavailable (%s); using local cache only", type(exc).__name__)
            self._redis = None
            self._disabled = True
            return None

    def get(self, key: str):
        value = self.local.get(key)
        if value is not None:
            return value
        client = self._client()
        if client is None:
            return None
        try:
            raw = client.get(self._key(key))
            if raw is None:
                return None
            value = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            self.local.put(key, value)
            return value
        except Exception as exc:
            logger.warning("shared cache read failed (%s); using local cache only", type(exc).__name__)
            self._disabled = True
            return None

    def put(self, key: str, value, ttl: int | None = None):
        self.local.put(key, value, ttl=ttl)
        client = self._client()
        if client is None:
            return
        try:
            effective_ttl = ttl or self.local.default_ttl
            client.set(self._key(key), json.dumps(value, default=str), ex=max(1, int(effective_ttl)))
        except Exception as exc:
            logger.warning("shared cache write failed (%s); using local cache only", type(exc).__name__)
            self._disabled = True

    def invalidate_user(self, user_id: str):
        self.local.invalidate_user(user_id)
        client = self._client()
        if client is None:
            return
        try:
            pattern = f"{self._key(str(user_id))}:*"
            keys = []
            cursor = 0
            while True:
                cursor, batch = client.scan(cursor, match=pattern, count=100)
                keys.extend(batch)
                if int(cursor) == 0:
                    break
            if keys:
                client.delete(*keys)
        except Exception as exc:
            logger.warning("shared cache invalidation failed (%s)", type(exc).__name__)
            self._disabled = True
