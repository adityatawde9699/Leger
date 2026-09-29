"""Shared Upstash REST client factory."""

from functools import lru_cache

from ..config import settings


@lru_cache(maxsize=1)
def get_redis_client():
    """Return the process-wide REST client, or None when optional local Redis is unset."""
    url = settings.upstash_redis_rest_url.strip()
    token = settings.upstash_redis_rest_token.strip()
    if not url or not token:
        return None

    from upstash_redis import Redis

    return Redis(
        url=url,
        token=token,
        allow_telemetry=False,
        rest_retries=0,
        rest_retry_interval=0,
    )
