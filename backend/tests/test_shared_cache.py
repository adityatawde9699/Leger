from app.main import TTLCache
from app.services.shared_cache import SharedTTLCache


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.deleted = []

    def ping(self):
        return True

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value.encode() if isinstance(value, str) else value
        self.ttls[key] = ttl

    def scan_iter(self, match, count=100):
        prefix = match.removesuffix("*")
        return iter([key for key in self.values if key.startswith(prefix)])

    def delete(self, *keys):
        self.deleted.extend(keys)
        for key in keys:
            self.values.pop(key, None)


def test_shared_cache_reads_other_worker_value_into_local_cache():
    redis = FakeRedis()
    writer = SharedTTLCache(TTLCache(), redis_client=redis)
    reader = SharedTTLCache(TTLCache(), redis_client=redis)

    writer.put("user-1:advisor:v1", {"answer": "safe"}, ttl=30)

    assert reader.get("user-1:advisor:v1") == {"answer": "safe"}
    assert reader.local.get("user-1:advisor:v1") == {"answer": "safe"}


def test_shared_cache_invalidates_local_and_redis_user_namespace():
    redis = FakeRedis()
    cache = SharedTTLCache(TTLCache(), redis_client=redis)
    cache.put("user-1:advisor:v1", "answer")
    cache.put("user-2:advisor:v1", "other")

    cache.invalidate_user("user-1")

    assert cache.get("user-1:advisor:v1") is None
    assert cache.get("user-2:advisor:v1") == "other"
    assert "ledger:derived:user-1:advisor:v1" in redis.deleted


def test_shared_cache_disables_failed_redis_and_keeps_local_behavior():
    class BrokenRedis:
        def ping(self):
            raise OSError("connection refused")

    cache = SharedTTLCache(TTLCache(), redis_client=BrokenRedis())
    cache.put("user-1:key", "local")

    assert cache.get("user-1:key") == "local"
    assert cache._disabled is True
