import asyncio

import pytest

from app.config import settings
from app.services.ai_router import AIRouter


class FakeAdapter:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    async def is_available(self):
        return True

    async def generate(self, system, messages, max_tokens):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_task_policy_and_attempt_cap_prevent_unapproved_fallback(monkeypatch):
    router = AIRouter()
    blocked = FakeAdapter(result="blocked")
    approved = FakeAdapter(result="approved")
    router.adapters = [("Blocked", blocked), ("Approved", approved)]
    monkeypatch.setattr(settings, "ai_provider_allowlist", "")
    monkeypatch.setattr(settings, "ai_task_provider_policy", '{"categorize":["Approved"]}')
    monkeypatch.setattr(settings, "ai_provider_max_attempts", 2)

    result = asyncio.run(router.generate("system", task_type="categorize"))

    assert result == "approved"
    assert blocked.calls == 0
    assert approved.calls == 1


def test_invalid_task_policy_fails_closed(monkeypatch):
    router = AIRouter()
    provider = FakeAdapter(result="must not run")
    router.adapters = [("Provider", provider)]
    monkeypatch.setattr(settings, "ai_provider_allowlist", "")
    monkeypatch.setattr(settings, "ai_task_provider_policy", "not-json")

    with pytest.raises(RuntimeError, match="No API keys configured"):
        asyncio.run(router.generate("system", task_type="advisor"))

    assert provider.calls == 0


def test_provider_timeout_falls_back_to_next_allowed_provider(monkeypatch):
    router = AIRouter()
    slow = FakeAdapter(error=TimeoutError())
    fast = FakeAdapter(result="safe fallback")
    router.adapters = [("Slow", slow), ("Fast", fast)]
    monkeypatch.setattr(settings, "ai_provider_allowlist", "Slow,Fast")
    monkeypatch.setattr(settings, "ai_task_provider_policy", "")
    monkeypatch.setattr(settings, "ai_provider_max_attempts", 2)
    monkeypatch.setattr(settings, "ai_provider_timeout_seconds", 0.01)

    result = asyncio.run(router.generate("system", task_type="advisor"))

    assert result == "safe fallback"
    assert slow.calls == 1
    assert fast.calls == 1


def test_provider_circuit_skips_repeatedly_failing_upstream(monkeypatch):
    router = AIRouter()
    failing = FakeAdapter(error=RuntimeError("upstream unavailable"))
    fallback = FakeAdapter(result="fallback")
    router.adapters = [("Failing", failing), ("Fallback", fallback)]
    monkeypatch.setattr(settings, "ai_provider_allowlist", "Failing,Fallback")
    monkeypatch.setattr(settings, "ai_task_provider_policy", "")
    monkeypatch.setattr(settings, "ai_provider_max_attempts", 2)
    monkeypatch.setattr(settings, "ai_provider_circuit_failure_threshold", 1)
    monkeypatch.setattr(settings, "ai_provider_circuit_cooldown_seconds", 60.0)

    assert asyncio.run(router.generate("system", task_type="advisor")) == "fallback"
    assert asyncio.run(router.generate("system", task_type="advisor")) == "fallback"
    assert failing.calls == 1
    assert fallback.calls == 2


def test_provider_circuit_reopens_after_cooldown(monkeypatch):
    router = AIRouter()
    failing = FakeAdapter(error=RuntimeError("temporary outage"))
    router.adapters = [("Failing", failing)]
    monkeypatch.setattr(settings, "ai_provider_allowlist", "Failing")
    monkeypatch.setattr(settings, "ai_task_provider_policy", "")
    monkeypatch.setattr(settings, "ai_provider_max_attempts", 1)
    monkeypatch.setattr(settings, "ai_provider_circuit_failure_threshold", 1)
    monkeypatch.setattr(settings, "ai_provider_circuit_cooldown_seconds", 0.0)

    with pytest.raises(RuntimeError, match="All AI providers failed"):
        asyncio.run(router.generate("system", task_type="advisor"))
    with pytest.raises(RuntimeError, match="All AI providers failed"):
        asyncio.run(router.generate("system", task_type="advisor"))
    assert failing.calls == 2


def test_provider_health_reports_safe_counters_and_latency(monkeypatch):
    router = AIRouter()
    provider = FakeAdapter(result="ok")
    router.adapters = [("TestProvider", provider)]
    monkeypatch.setattr(settings, "ai_provider_allowlist", "TestProvider")
    monkeypatch.setattr(settings, "ai_task_provider_policy", "")
    monkeypatch.setattr(settings, "ai_provider_max_attempts", 1)

    assert asyncio.run(router.generate("system", task_type="advisor")) == "ok"
    health = router.provider_health("advisor")[0]

    assert health["provider"] == "TestProvider"
    assert health["successes"] == 1
    assert health["failures"] == 0
    assert health["last_outcome"] == "success"
    assert isinstance(health["last_latency_ms"], float)
    assert "api_key" not in health
