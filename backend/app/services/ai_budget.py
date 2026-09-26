"""Deployment-wide request quota guard for paid or rate-limited AI providers."""

import json
from datetime import UTC, datetime


class AIRequestBudget:
    def __init__(self, redis_client=None, redis_url: str = "", global_limit: int = 0, provider_limits: str = ""):
        self.redis = redis_client
        self.redis_url = redis_url.strip()
        self._redis_checked = redis_client is not None
        self.global_limit = max(0, int(global_limit))
        try:
            parsed = json.loads(provider_limits or "{}")
            self.provider_limits = {str(k): max(0, int(v)) for k, v in parsed.items()}
        except (TypeError, ValueError, json.JSONDecodeError):
            self.provider_limits = {}
        self.local_counts: dict[str, int] = {}

    def _key(self, provider: str) -> str:
        return f"ledger:ai-budget:{datetime.now(UTC).date().isoformat()}:{provider}"

    def allow(self, provider: str) -> bool:
        limit = self.provider_limits.get(provider, self.global_limit)
        if not limit:
            return True
        key = self._key(provider)
        if not self._redis_checked and self.redis_url:
            self._redis_checked = True
            try:
                import redis
                client = redis.Redis.from_url(self.redis_url, socket_connect_timeout=0.2, socket_timeout=0.2)
                client.ping()
                self.redis = client
            except Exception:
                self.redis = None
        if self.redis is not None:
            try:
                count = int(self.redis.incr(key))
                if count == 1:
                    self.redis.expire(key, 86400)
                if count > limit:
                    self.redis.decr(key)
                    return False
                return True
            except Exception:
                return False
        count = self.local_counts.get(key, 0)
        if count >= limit:
            return False
        self.local_counts[key] = count + 1
        return True
