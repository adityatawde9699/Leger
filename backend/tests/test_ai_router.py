import asyncio

import pytest

from app.config import settings
from app.services import ai_router as ai_router_module
from app.services.ai_budget import AIRequestBudget
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


class FakeStreamAdapter:
    """Streams the given tokens, then optionally raises; can pause between tokens."""

    def __init__(self, tokens, fail_after=False, delay=0.0):
        self.tokens = tokens
        self.fail_after = fail_after
        self.delay = delay
        self.max_tokens = None

    async def is_available(self):
        return True

    async def stream(self, system, messages, max_tokens):
        self.max_tokens = max_tokens
        for token in self.tokens:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield token
        if self.fail_after:
            raise ConnectionError("provider dropped mid-reply")


def _collect(router, **kwargs):
    async def run():
        return "".join([token async for token in router.stream("system", [{"role": "user", "content": "q"}], **kwargs)])
    return asyncio.run(run())


def _allow_all(monkeypatch, names):
    monkeypatch.setattr(settings, "ai_provider_allowlist", ",".join(names))
    monkeypatch.setattr(settings, "ai_task_provider_policy", "")
    monkeypatch.setattr(settings, "ai_provider_max_attempts", 3)


def test_stream_failover_discards_partial_output_from_failed_provider(monkeypatch):
    router = AIRouter()
    router.adapters = [
        ("Flaky", FakeStreamAdapter(['{"schema": "adv', 'isor.v1", "cla'], fail_after=True)),
        ("Stable", FakeStreamAdapter(['{"ok": ', "true}"])),
    ]
    _allow_all(monkeypatch, ["Flaky", "Stable"])

    assert _collect(router) == '{"ok": true}'


def test_stream_enforces_total_time_limit_per_provider(monkeypatch):
    router = AIRouter()
    router.adapters = [
        ("Trickle", FakeStreamAdapter(["a"] * 50, delay=0.02)),
        ("Quick", FakeStreamAdapter(["done"])),
    ]
    _allow_all(monkeypatch, ["Trickle", "Quick"])
    monkeypatch.setattr(settings, "ai_provider_timeout_seconds", 1.0)
    monkeypatch.setattr(settings, "ai_provider_stream_total_seconds", 0.2)

    assert _collect(router) == "done"


def test_stream_uses_task_token_budget(monkeypatch):
    router = AIRouter()
    adapter = FakeStreamAdapter(["x"])
    router.adapters = [("Only", adapter)]
    _allow_all(monkeypatch, ["Only"])

    _collect(router, task_type="advisor")

    assert adapter.max_tokens == 900


# ── File extraction (receipts, scanned statements) ────────────────────────────
class FakeFileAdapter(FakeAdapter):
    supports_files = True

    def __init__(self, result=None, error=None, delay=0.0):
        super().__init__(result=result, error=error)
        self.delay = delay
        self.file_calls = []

    async def generate_with_file(self, prompt, data, mime_type, max_tokens, json_output=False):
        self.file_calls.append((mime_type, max_tokens, json_output))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


def _file_router(monkeypatch, adapters, policy=""):
    router = AIRouter()
    router.adapters = adapters
    monkeypatch.setattr(settings, "ai_provider_allowlist", "")
    monkeypatch.setattr(settings, "ai_task_provider_policy", policy)
    monkeypatch.setattr(settings, "ai_provider_max_attempts", 3)
    return router


def test_file_extraction_only_uses_file_capable_providers(monkeypatch):
    text_only = FakeAdapter(result="text")
    vision = FakeFileAdapter(result='{"ok": true}')
    router = _file_router(monkeypatch, [("TextOnly", text_only), ("Vision", vision)])

    result = asyncio.run(router.generate_from_file("p", b"img", "image/png", task_type="receipt", json_output=True))

    assert result == '{"ok": true}'
    assert text_only.calls == 0
    assert vision.file_calls == [("image/png", 300, True)]


def test_file_extraction_falls_back_and_respects_task_policy(monkeypatch):
    failing = FakeFileAdapter(error=ConnectionError("down"))
    backup = FakeFileAdapter(result="rows")
    blocked = FakeFileAdapter(result="not allowed")
    router = _file_router(monkeypatch, [("Blocked", blocked), ("Failing", failing), ("Backup", backup)],
                          policy='{"statement_ocr": ["Failing", "Backup"]}')

    assert asyncio.run(router.generate_from_file("p", b"%PDF", "application/pdf", task_type="statement_ocr")) == "rows"
    assert blocked.file_calls == []
    assert failing.file_calls and backup.file_calls


def test_file_extraction_counts_against_the_daily_budget(monkeypatch):
    vision = FakeFileAdapter(result="ok")
    router = _file_router(monkeypatch, [("Vision", vision)])
    router._budget = AIRequestBudget(global_limit=1)

    assert asyncio.run(router.generate_from_file("p", b"img", "image/png", task_type="receipt")) == "ok"
    with pytest.raises(RuntimeError):
        asyncio.run(router.generate_from_file("p", b"img", "image/png", task_type="receipt"))
    assert len(vision.file_calls) == 1


def test_ocr_tasks_get_a_longer_timeout_than_chat(monkeypatch):
    slow = FakeFileAdapter(result="ok", delay=0.05)
    router = _file_router(monkeypatch, [("Slow", slow)])
    monkeypatch.setattr(settings, "ai_provider_timeout_seconds", 0.01)
    monkeypatch.setitem(ai_router_module.TASK_TIMEOUT_SECONDS, "receipt", 1.0)

    assert asyncio.run(router.generate_from_file("p", b"img", "image/png", task_type="receipt")) == "ok"


def test_genai_api_error_status_is_recognised_as_an_auth_failure():
    from google.genai import errors

    assert ai_router_module._status_code(errors.ClientError(403, {"error": {"message": "denied"}})) == 403


# ── Gemini adapter request shape (google-genai SDK) ───────────────────────────
@pytest.fixture()
def genai_client(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(return_value=MagicMock(text="reply"))
    monkeypatch.setattr(ai_router_module, "_gemini_client", lambda: client)
    monkeypatch.setattr(settings, "gemini_model", "gemini-test-model")
    return client


def test_gemini_adapter_sends_system_prompt_roles_and_token_limit(genai_client):
    adapter = ai_router_module.GeminiAdapter()
    messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]

    assert asyncio.run(adapter.generate("be brief", messages, 123)) == "reply"

    request = genai_client.aio.models.generate_content.call_args.kwargs
    assert request["model"] == "gemini-test-model"
    assert [(c.role, c.parts[0].text) for c in request["contents"]] == [("user", "hi"), ("model", "hello")]
    assert request["config"].system_instruction == "be brief"
    assert request["config"].max_output_tokens == 123


def test_gemini_adapter_streams_chunks(genai_client):
    from unittest.mock import AsyncMock, MagicMock

    async def chunks():
        for text in ("a", None, "b"):
            yield MagicMock(text=text)

    genai_client.aio.models.generate_content_stream = AsyncMock(return_value=chunks())
    adapter = ai_router_module.GeminiAdapter()

    async def collect():
        return [t async for t in adapter.stream("s", [{"role": "user", "content": "q"}], 50)]

    assert asyncio.run(collect()) == ["a", "b"]
