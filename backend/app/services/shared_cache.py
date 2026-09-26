"""Optional Redis L2 cache with a fail-open in-process fallback.

The cache only stores derived, user-scoped values. Redis is never required for
application correctness: a connection failure disables L2 for that worker and
the existing TTL cache remains authoritative for the request.
"""

import json
import logging
from collections.abc import Callable

logger = logging.getLogger("ledger.shared_cache")


class SharedTTLCache:
    """Wrap an existing local TTL cache with optional Redis read-through/write-through."""

    def __init__(
        self,
        local_cache,
        *,
        redis_url: str = "",
        redis_client=None,
        redis_factory: Callable | None = None,
        namespace: str = "ledger:derived",
    ):
        self.local = local_cache
        self.redis_url = redis_url.strip()
        self._redis = redis_client
        self._redis_factory = redis_factory
        self.namespace = namespace
        self._disabled = False

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def _client(self):
        if self._disabled or self._redis is not None:
            return self._redis
        if not self.redis_url:
            self._disabled = True
            return None
        try:
            if self._redis_factory:
                self._redis = self._redis_factory(self.redis_url)
            else:
                import redis

                self._redis = redis.Redis.from_url(
                    self.redis_url,
                    socket_connect_timeout=0.2,
                    socket_timeout=0.2,
                    decode_responses=False,
                )
            self._redis.ping()
            return self._redis
        except Exception as exc:  # Redis is an optimization, never a hard dependency.
            logger.warning("shared cache unavailable; using local cache only: %s", str(exc)[:120])
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
            logger.warning("shared cache read failed; using local cache only: %s", str(exc)[:120])
            self._disabled = True
            return None

    def put(self, key: str, value, ttl: int | None = None):
        self.local.put(key, value, ttl=ttl)
        client = self._client()
        if client is None:
            return
        try:
            effective_ttl = ttl or self.local.default_ttl
            client.setex(self._key(key), max(1, int(effective_ttl)), json.dumps(value, default=str))
        except Exception as exc:
            logger.warning("shared cache write failed; using local cache only: %s", str(exc)[:120])
            self._disabled = True

    def invalidate_user(self, user_id: str):
        self.local.invalidate_user(user_id)
        client = self._client()
        if client is None:
            return
        try:
            pattern = f"{self._key(str(user_id))}:*"
            keys = list(client.scan_iter(match=pattern, count=100))
            if keys:
                client.delete(*keys)
        except Exception as exc:
            logger.warning("shared cache invalidation failed: %s", str(exc)[:120])
            self._disabled = True
