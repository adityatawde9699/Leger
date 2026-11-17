"""
AI Router — streams and generates responses from a fallback chain of AI providers:
Groq -> Cerebras -> Gemini -> Cohere -> OpenRouter.

Upgrade notes (v2):
- Added generate() method (non-streaming) — fixes bill_negotiator bug
- Upgraded Groq: llama-3.3-70b-versatile (better financial reasoning)
- Gemini runs on the google-genai SDK; the model comes from GEMINI_MODEL
- generate_from_file() sends receipts and scanned PDFs through the same policy, budgets and circuit breaker
- Added per-task max_tokens tuning via task_type parameter
- Added exponential backoff retry on transient errors
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from ..config import settings
from .ai_budget import AIRequestBudget
from .privacy import redact_sensitive_text
from .telemetry import record_telemetry
from .upstash_redis import get_redis_client

logger = logging.getLogger("ledger.ai_router")

# ── Task-specific token budgets ───────────────────────────────────────────────
TASK_TOKENS = {
    "categorize": 150,
    "categorize_batch": 700,   # 15 items × ~45 tokens, with headroom
    "insights": 650,           # 7 items × ~80 tokens + JSON overhead
    "advisor": 900,
    "advisor_tools": 180,
    "negotiate": 700,          # up to 10 bills × ~60 tokens
    "receipt": 300,
    "statement_ocr": 8192,     # a full statement page set extracted as JSON rows
    "default": 512,
}

# File extraction (OCR) is slower than chat; these tasks get a longer per-call timeout.
TASK_TIMEOUT_SECONDS = {"receipt": 45.0, "statement_ocr": 120.0}


class AIProviderAuthError(RuntimeError):
    def __init__(self, provider: str, status_code: int | None, detail: str):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"{provider} authentication failed ({status_code or 'unknown'}): {detail}")


def _status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if status:
        return int(status)
    code = getattr(exc, "code", None)  # google.genai.errors.APIError
    if isinstance(code, int):
        return code
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return int(status) if status else None


async def _retry_async(coro_fn, max_retries: int = 2, base_delay: float = 0.5):
    """Retry an async function with exponential backoff on transient errors."""
    for attempt in range(max_retries + 1):
        try:
            return await coro_fn()
        except Exception as e:
            status = _status_code(e)
            # Don't retry auth errors or client errors
            if status and status < 500 and status not in (429, 503):
                raise
            if attempt == max_retries:
                raise
            delay = base_delay * (2**attempt)
            logger.debug("Retrying after %.1fs (attempt %d/%d)", delay, attempt + 1, max_retries)
            await asyncio.sleep(delay)


class GroqAdapter:
    """Calls Groq API using official SDK — upgraded to llama-3.3-70b-versatile."""

    async def is_available(self) -> bool:
        return bool(settings.groq_api_key)

    async def stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.groq_api_key)
        formatted_messages = [{"role": "system", "content": system}] + messages

        stream = await client.chat.completions.create(
            messages=formatted_messages,
            model="llama-3.3-70b-versatile",
            max_tokens=max_tokens,
            stream=True,
            temperature=0.1,  # Low temp for financial accuracy
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate(self, system: str, messages: list[dict], max_tokens: int) -> str:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.groq_api_key)
        formatted_messages = [{"role": "system", "content": system}] + messages

        response = await client.chat.completions.create(
            messages=formatted_messages,
            model="llama-3.3-70b-versatile",
            max_tokens=max_tokens,
            stream=False,
            temperature=0.1,
        )
        return response.choices[0].message.content or ""


class CerebrasAdapter:
    """Calls Cerebras API using OpenAI compatible SDK."""

    async def is_available(self) -> bool:
        return bool(settings.cerebras_api_key)

    async def stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url="https://api.cerebras.ai/v1", api_key=settings.cerebras_api_key)
        formatted_messages = [{"role": "system", "content": system}] + messages

        stream = await client.chat.completions.create(
            messages=formatted_messages,
            model="llama-3.3-70b",
            max_tokens=max_tokens,
            stream=True,
            temperature=0.1,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate(self, system: str, messages: list[dict], max_tokens: int) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url="https://api.cerebras.ai/v1", api_key=settings.cerebras_api_key)
        formatted_messages = [{"role": "system", "content": system}] + messages

        response = await client.chat.completions.create(
            messages=formatted_messages,
            model="llama-3.3-70b",
            max_tokens=max_tokens,
            stream=False,
            temperature=0.1,
        )
        return response.choices[0].message.content or ""


def _gemini_client():
    """One google-genai client per API key; it holds the HTTP connection pool."""
    from google import genai

    key = settings.gemini_api_key
    if _GEMINI_CLIENT.get("key") != key:
        _GEMINI_CLIENT.update(key=key, client=genai.Client(api_key=key))
    return _GEMINI_CLIENT["client"]


_GEMINI_CLIENT: dict = {}


class GeminiAdapter:
    """Calls Google Gemini through the google-genai SDK (model set by GEMINI_MODEL)."""

    supports_files = True

    async def is_available(self) -> bool:
        return bool(settings.gemini_api_key)

    @staticmethod
    def _contents(messages: list[dict]):
        from google.genai import types

        return [
            types.Content(role="user" if msg["role"] == "user" else "model",
                          parts=[types.Part.from_text(text=str(msg["content"]))])
            for msg in messages
        ]

    @staticmethod
    def _config(max_tokens: int, system: str | None = None, json_output: bool = False):
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=system or None,
            max_output_tokens=max_tokens,
            temperature=0.1,
            response_mime_type="application/json" if json_output else None,
        )

    async def stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        response = await _gemini_client().aio.models.generate_content_stream(
            model=settings.gemini_model, contents=self._contents(messages), config=self._config(max_tokens, system),
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text

    async def generate(self, system: str, messages: list[dict], max_tokens: int) -> str:
        response = await _gemini_client().aio.models.generate_content(
            model=settings.gemini_model, contents=self._contents(messages), config=self._config(max_tokens, system),
        )
        return response.text or ""

    async def generate_with_file(self, prompt: str, data: bytes, mime_type: str, max_tokens: int,
                                 json_output: bool = False) -> str:
        """Multimodal request: one file (image or PDF) plus an instruction."""
        from google.genai import types

        response = await _gemini_client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Part.from_bytes(data=data, mime_type=mime_type), prompt],
            config=self._config(max_tokens, json_output=json_output),
        )
        return response.text or ""


class CohereAdapter:
    """Calls Cohere API."""

    async def is_available(self) -> bool:
        return bool(settings.cohere_api_key)

    async def stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        import cohere

        client = cohere.AsyncClient(api_key=settings.cohere_api_key)

        chat_history = []
        message = ""
        for msg in messages:
            if msg["role"] == "user":
                message = msg["content"]
            else:
                chat_history.append(
                    {
                        "role": "USER" if msg["role"] == "user" else "CHATBOT",
                        "message": msg["content"],
                    }
                )

        response = await client.chat_stream(
            message=message,
            preamble=system,
            chat_history=chat_history,
            max_tokens=max_tokens,
            model="command-r-plus-08-2024",
        )

        async for event in response:
            if event.event_type == "text-generation":
                yield event.text

    async def generate(self, system: str, messages: list[dict], max_tokens: int) -> str:
        import cohere

        client = cohere.AsyncClient(api_key=settings.cohere_api_key)
        user_messages = [m for m in messages if m["role"] == "user"]
        message = user_messages[-1]["content"] if user_messages else ""

        response = await client.chat(
            message=message,
            preamble=system,
            max_tokens=max_tokens,
            model="command-r-plus-08-2024",
        )
        return response.text or ""


class OpenRouterAdapter:
    """Calls OpenRouter API using OpenAI compatible SDK."""

    async def is_available(self) -> bool:
        return bool(settings.openrouter_api_key)

    async def stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)
        formatted_messages = [{"role": "system", "content": system}] + messages

        stream = await client.chat.completions.create(
            messages=formatted_messages,
            model="meta-llama/llama-3.3-70b-instruct:free",
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate(self, system: str, messages: list[dict], max_tokens: int) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)
        formatted_messages = [{"role": "system", "content": system}] + messages

        response = await client.chat.completions.create(
            messages=formatted_messages,
            model="meta-llama/llama-3.3-70b-instruct:free",
            max_tokens=max_tokens,
            stream=False,
        )
        return response.choices[0].message.content or ""


class AIRouter:
    """
    Routes AI requests through fallback chain: Groq -> Cerebras -> Gemini -> Cohere -> OpenRouter.
    Supports both streaming (.stream()) and non-streaming (.generate()) modes.
    """

    def __init__(self):
        self.adapters = [
            ("Groq", GroqAdapter()),
            ("Cerebras", CerebrasAdapter()),
            ("Gemini", GeminiAdapter()),
            ("Cohere", CohereAdapter()),
            ("OpenRouter", OpenRouterAdapter()),
        ]
        # Process-local health state is deliberately conservative. It protects
        # this worker from repeatedly retrying a broken upstream; deployment-
        # wide provider health belongs in shared infrastructure/observability.
        self._provider_failures: dict[str, int] = {}
        self._provider_opened_at: dict[str, float] = {}
        self._provider_health: dict[str, dict[str, object]] = {}
        self._health_redis = get_redis_client()
        self._budget = AIRequestBudget(
            redis_client=get_redis_client(),
            global_limit=settings.ai_daily_request_budget,
            provider_limits=settings.ai_provider_daily_request_budgets,
        )

    def _health_entry(self, name: str) -> dict[str, object]:
        return self._provider_health.setdefault(
            name,
            {"successes": 0, "failures": 0, "last_latency_ms": None, "last_outcome": None},
        )

    def _circuit_open(self, name: str) -> bool:
        opened_at = self._provider_opened_at.get(name)
        if opened_at is None:
            return False
        cooldown = max(0.0, float(settings.ai_provider_circuit_cooldown_seconds))
        if time.monotonic() - opened_at >= cooldown:
            self._provider_opened_at.pop(name, None)
            self._provider_failures.pop(name, None)
            return False
        return True

    def _record_provider_success(self, name: str, latency_ms: float | None = None) -> None:
        health = self._health_entry(name)
        health["successes"] = int(health["successes"]) + 1
        health["last_latency_ms"] = round(latency_ms, 1) if latency_ms is not None else None
        health["last_outcome"] = "success"
        self._provider_failures.pop(name, None)
        self._provider_opened_at.pop(name, None)
        self._record_shared_health(name, "success", latency_ms)

    def _record_provider_failure(self, name: str, latency_ms: float | None = None) -> None:
        health = self._health_entry(name)
        health["failures"] = int(health["failures"]) + 1
        health["last_latency_ms"] = round(latency_ms, 1) if latency_ms is not None else None
        health["last_outcome"] = "error"
        failures = self._provider_failures.get(name, 0) + 1
        threshold = max(1, int(settings.ai_provider_circuit_failure_threshold))
        self._provider_failures[name] = failures
        if failures >= threshold:
            self._provider_opened_at.setdefault(name, time.monotonic())
            logger.warning(
                "Opening AI provider circuit for %s after %d failures (cooldown %.1fs)",
                name,
                failures,
                float(settings.ai_provider_circuit_cooldown_seconds),
            )
        self._record_shared_health(name, "failure", latency_ms)

    async def _budget_allows(self, name: str) -> bool:
        # The shared budget is an Upstash HTTP call; keep it off the event loop.
        if self._budget.uses_network(name):
            return await asyncio.to_thread(self._budget.allow, name)
        return self._budget.allow(name)

    def _record_shared_health(self, name: str, outcome: str, latency_ms: float | None) -> None:
        """Best-effort deployment-wide counters; local health remains authoritative on failure."""
        if settings.environment != "production":
            return
        if self._health_redis is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._write_shared_health(name, outcome, latency_ms)
            return
        # Four sequential Upstash HTTP calls: run them in the background in a thread
        # rather than blocking the event loop after every provider response.
        loop.run_in_executor(None, self._write_shared_health, name, outcome, latency_ms)

    def _write_shared_health(self, name: str, outcome: str, latency_ms: float | None) -> None:
        if self._health_redis is None:
            return
        try:
            key = f"ledger:ai-health:{datetime.now(UTC).date().isoformat()}:{name}"
            field = "successes" if outcome == "success" else "failures"
            self._health_redis.hincrby(key, field, 1)
            if latency_ms is not None:
                self._health_redis.hset(key, "last_latency_ms", round(latency_ms, 1))
            self._health_redis.hset(key, "last_outcome", outcome)
            self._health_redis.expire(key, 8 * 86400)
        except Exception:
            self._health_redis = None

    def _shared_health(self, name: str) -> dict[str, object]:
        if self._health_redis is None:
            return {}
        try:
            key = f"ledger:ai-health:{datetime.now(UTC).date().isoformat()}:{name}"
            values = self._health_redis.hgetall(key)
            def decode(value):
                return value.decode() if isinstance(value, bytes) else value
            return {
                "successes": int(decode(values.get(b"successes", values.get("successes", 0))) or 0),
                "failures": int(decode(values.get(b"failures", values.get("failures", 0))) or 0),
                "last_latency_ms": float(decode(values.get(b"last_latency_ms", values.get("last_latency_ms")))) if values.get(b"last_latency_ms", values.get("last_latency_ms")) is not None else None,
                "last_outcome": decode(values.get(b"last_outcome", values.get("last_outcome"))),
            }
        except Exception:
            return {}

    def provider_health(self, task_type: str = "advisor") -> list[dict[str, object]]:
        """Return safe provider health metadata without credentials or error text."""
        allowed = self._allowed_providers(task_type)
        configured = set(self.configured_providers(task_type))
        return [
            {
                "provider": name,
                "configured": name in configured,
                "allowed": allowed is None or name in allowed,
                "circuit_open": self._circuit_open(name),
                "consecutive_failures": self._provider_failures.get(name, 0),
                "successes": int(self._shared_health(name).get("successes", self._health_entry(name)["successes"])),
                "failures": int(self._shared_health(name).get("failures", self._health_entry(name)["failures"])),
                "last_latency_ms": self._shared_health(name).get("last_latency_ms", self._health_entry(name)["last_latency_ms"]),
                "last_outcome": self._shared_health(name).get("last_outcome", self._health_entry(name)["last_outcome"]),
            }
            for name, _adapter in self.adapters
        ]

    def configured_providers(self, task_type: str | None = None) -> list[str]:
        """Return provider names with configured credentials, never the credentials."""
        allowed = self._allowed_providers(task_type) if task_type else None
        return [
            name
            for name, adapter in self.adapters
            if allowed is None or name in allowed
            if (
                (name == "Groq" and settings.groq_api_key)
                or (name == "Cerebras" and settings.cerebras_api_key)
                or (name == "Gemini" and settings.gemini_api_key)
                or (name == "Cohere" and settings.cohere_api_key)
                or (name == "OpenRouter" and settings.openrouter_api_key)
            )
        ]

    def provider_retention_policy(self) -> dict[str, str]:
        try:
            policy = json.loads(settings.ai_provider_retention_policy or "{}")
            return {str(key): str(value) for key, value in policy.items()} if isinstance(policy, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def provider_regions(self) -> dict[str, str]:
        try:
            regions = json.loads(settings.ai_provider_regions or "{}")
            return {str(key): str(value) for key, value in regions.items()} if isinstance(regions, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def _allowed_providers(self, task_type: str) -> set[str] | None:
        """Resolve explicit provider policy; malformed policy fails closed."""
        allowlist = {name.strip() for name in settings.ai_provider_allowlist.split(",") if name.strip()}
        global_policy = bool(settings.ai_provider_allowlist.strip())
        policy = settings.ai_task_provider_policy.strip()
        if policy:
            try:
                task_policy = json.loads(policy)
                selected = task_policy.get(task_type, task_policy.get("default"))
                if selected is not None:
                    if not isinstance(selected, list) or not all(isinstance(name, str) for name in selected):
                        raise ValueError("provider policy values must be string arrays")
                    allowlist = set(selected)
                    global_policy = True
            except (json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
                logger.error("Invalid AI provider policy; refusing provider calls: %s", exc)
                return set()
        return allowlist if global_policy else None

    def _adapters_for(self, task_type: str):
        allowed = self._allowed_providers(task_type)
        return [
            (name, adapter)
            for name, adapter in self.adapters
            if (allowed is None or name in allowed) and not self._circuit_open(name)
        ]

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 512,
        task_type: str = "default",
        prefer_local: bool = False,
    ) -> AsyncIterator[str]:
        """Yield the reply of the first provider that completes successfully.

        Each attempt is buffered and released only when that provider finishes, so a
        provider failing mid-reply is discarded instead of being concatenated with the
        fallback provider's output (which corrupted structured JSON replies).
        """
        system = redact_sensitive_text(system)
        messages = [{**message, "content": redact_sensitive_text(str(message.get("content", "")))}
                    for message in messages]
        effective_tokens = TASK_TOKENS.get(task_type, max_tokens)

        last_error = None
        attempts = 0
        max_attempts = max(1, settings.ai_provider_max_attempts)
        for name, adapter in self._adapters_for(task_type):
            if not await adapter.is_available():
                continue
            if not await self._budget_allows(name):
                logger.warning("AI request budget exhausted for provider=%s task=%s", name, task_type)
                continue
            if attempts >= max_attempts:
                break
            attempts += 1
            started = time.perf_counter()
            try:
                logger.debug("Streaming with %s (task=%s, tokens=%d)", name, task_type, effective_tokens)
                iterator = adapter.stream(system, messages, effective_tokens)
                loop = asyncio.get_running_loop()
                deadline = loop.time() + settings.ai_provider_stream_total_seconds
                buffered: list[str] = []
                while True:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise TimeoutError(f"{name} exceeded the total stream time limit")
                    try:
                        token = await asyncio.wait_for(
                            anext(iterator), timeout=min(settings.ai_provider_timeout_seconds, remaining),
                        )
                    except StopAsyncIteration:
                        break
                    buffered.append(token)
                for token in buffered:
                    yield token
                record_telemetry(
                    "ai.provider",
                    provider=name,
                    fallback=attempts > 1,
                    parse_success=True,
                    outcome="success",
                    metadata={"task": task_type, "attempts": attempts},
                )
                self._record_provider_success(name, (time.perf_counter() - started) * 1000)
                return

            except Exception as e:
                status = _status_code(e)
                if status in (401, 403):
                    logger.error("%s auth failed status=%s", name, status)
                    last_error = AIProviderAuthError(name, status, "credential rejected")
                else:
                    logger.warning("%s stream failed status=%s", name, status)
                    last_error = e
                record_telemetry(
                    "ai.provider",
                    provider=name,
                    fallback=True,
                    parse_success=False,
                    outcome="error",
                    metadata={"task": task_type, "attempts": attempts},
                )
                self._record_provider_failure(name, (time.perf_counter() - started) * 1000)
                continue

        if last_error:
            if isinstance(last_error, AIProviderAuthError):
                yield "\n[AI Error: Authentication failed. Check your API keys.]"
            else:
                yield "\n[AI Error: All providers failed.]"
        else:
            yield "\n[AI Error: No API keys configured. Set GROQ_API_KEY or GEMINI_API_KEY in .env]"

    async def generate(
        self,
        system: str,
        messages: list[dict] | None = None,
        user_message: str | None = None,
        max_tokens: int = 512,
        task_type: str = "default",
        temperature: float = 0.1,
    ) -> str:
        """
        Non-streaming generation — returns complete response string.
        Accepts either messages list OR a single user_message string.
        """
        if messages is None:
            messages = [{"role": "user", "content": user_message or ""}]
        system = redact_sensitive_text(system)
        messages = [{**message, "content": redact_sensitive_text(str(message.get("content", "")))}
                    for message in messages]

        effective_tokens = TASK_TOKENS.get(task_type, max_tokens)
        return await self._first_success(
            task_type, lambda adapter: adapter.generate(system, messages, effective_tokens),
        )

    async def generate_from_file(
        self,
        prompt: str,
        data: bytes,
        mime_type: str,
        task_type: str,
        json_output: bool = False,
    ) -> str:
        """Extract text from an image or PDF with a file-capable provider.

        Same task policy, budgets, circuit breaker, timeouts and health tracking as
        generate(). The file itself cannot be redacted, so callers must only use this
        for users who opted in to cloud AI.
        """
        effective_tokens = TASK_TOKENS.get(task_type, 512)
        return await self._first_success(
            task_type,
            lambda adapter: adapter.generate_with_file(prompt, data, mime_type, effective_tokens, json_output),
            files=True,
        )

    async def _first_success(self, task_type: str, call, files: bool = False) -> str:
        """Try allowed providers in order and return the first non-empty result."""
        last_error = None
        attempts = 0
        max_attempts = max(1, settings.ai_provider_max_attempts)
        timeout = max(settings.ai_provider_timeout_seconds, TASK_TIMEOUT_SECONDS.get(task_type, 0.0))
        for name, adapter in self._adapters_for(task_type):
            if files and not getattr(adapter, "supports_files", False):
                continue
            if not await adapter.is_available():
                continue
            if not await self._budget_allows(name):
                logger.warning("AI request budget exhausted for provider=%s task=%s", name, task_type)
                continue
            if attempts >= max_attempts:
                break
            attempts += 1
            started = time.perf_counter()
            try:
                logger.debug("Generating with %s (task=%s)", name, task_type)
                result = await asyncio.wait_for(call(adapter), timeout=timeout)
                if result:
                    record_telemetry(
                        "ai.provider",
                        provider=name,
                        fallback=attempts > 1,
                        parse_success=True,
                        outcome="success",
                        metadata={"task": task_type, "attempts": attempts},
                    )
                    self._record_provider_success(name, (time.perf_counter() - started) * 1000)
                    return result
            except Exception as e:
                status = _status_code(e)
                if status in (401, 403):
                    logger.error("%s auth failed status=%s", name, status)
                    last_error = AIProviderAuthError(name, status, "credential rejected")
                else:
                    logger.warning("%s generate failed status=%s", name, status)
                    last_error = e
                record_telemetry(
                    "ai.provider",
                    provider=name,
                    fallback=True,
                    parse_success=False,
                    outcome="error",
                    metadata={"task": task_type, "attempts": attempts},
                )
                self._record_provider_failure(name, (time.perf_counter() - started) * 1000)
                continue

        raise RuntimeError("All AI providers failed" if last_error else "No API keys configured")


ai_router = AIRouter()
