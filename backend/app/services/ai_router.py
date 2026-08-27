"""
AI Router — streams and generates responses from a fallback chain of AI providers:
Groq -> Cerebras -> Gemini -> Cohere -> OpenRouter.

Upgrade notes (v2):
- Added generate() method (non-streaming) — fixes bill_negotiator bug
- Upgraded Groq: llama-3.3-70b-versatile (better financial reasoning)
- Upgraded Gemini: gemini-2.0-flash (faster, more capable)
- Added per-task max_tokens tuning via task_type parameter
- Added exponential backoff retry on transient errors
"""

import asyncio
import logging
from collections.abc import AsyncIterator

from ..config import settings

logger = logging.getLogger("ledger.ai_router")

# ── Task-specific token budgets ───────────────────────────────────────────────
TASK_TOKENS = {
    "categorize": 150,
    "insights": 400,
    "advisor": 900,
    "negotiate": 600,
    "receipt": 300,
    "default": 512,
}


class AIProviderAuthError(RuntimeError):
    def __init__(self, provider: str, status_code: int | None, detail: str):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"{provider} authentication failed ({status_code or 'unknown'}): {detail}")


def _status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if status:
        return int(status)
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


class GeminiAdapter:
    """Calls Google Gemini API — upgraded to gemini-2.0-flash."""

    async def is_available(self) -> bool:
        return bool(settings.gemini_api_key)

    async def stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=system)

        formatted_messages = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            formatted_messages.append({"role": role, "parts": [msg["content"]]})

        response = await model.generate_content_async(
            formatted_messages,
            stream=True,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.1,
            ),
        )

        async for chunk in response:
            if chunk.text:
                yield chunk.text

    async def generate(self, system: str, messages: list[dict], max_tokens: int) -> str:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=system)

        formatted_messages = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            formatted_messages.append({"role": role, "parts": [msg["content"]]})

        response = await model.generate_content_async(
            formatted_messages,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.1,
            ),
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

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 512,
        task_type: str = "default",
        prefer_local: bool = False,
    ) -> AsyncIterator[str]:
        """Stream tokens from the first available provider."""
        effective_tokens = TASK_TOKENS.get(task_type, max_tokens)

        last_error = None
        for name, adapter in self.adapters:
            if not await adapter.is_available():
                continue
            try:
                logger.debug("Streaming with %s (task=%s, tokens=%d)", name, task_type, effective_tokens)
                iterator = adapter.stream(system, messages, effective_tokens)
                try:
                    first_token = await anext(iterator)
                except StopAsyncIteration:
                    first_token = ""

                yield first_token
                async for token in iterator:
                    yield token
                return

            except Exception as e:
                status = _status_code(e)
                if status in (401, 403):
                    logger.error("%s auth failed status=%s: %s", name, status, e)
                    last_error = AIProviderAuthError(name, status, str(e))
                else:
                    logger.warning("%s stream failed status=%s: %s", name, status, str(e)[:120])
                    last_error = e
                continue

        if last_error:
            if isinstance(last_error, AIProviderAuthError):
                yield "\n[AI Error: Authentication failed. Check your API keys.]"
            else:
                yield f"\n[AI Error: All providers failed. Last: {str(last_error)[:80]}]"
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

        effective_tokens = TASK_TOKENS.get(task_type, max_tokens)

        last_error = None
        for name, adapter in self.adapters:
            if not await adapter.is_available():
                continue
            try:
                logger.debug("Generating with %s (task=%s, tokens=%d)", name, task_type, effective_tokens)
                result = await adapter.generate(system, messages, effective_tokens)
                if result:
                    return result
            except Exception as e:
                status = _status_code(e)
                if status in (401, 403):
                    logger.error("%s auth failed: %s", name, e)
                    last_error = AIProviderAuthError(name, status, str(e))
                else:
                    logger.warning("%s generate failed: %s", name, str(e)[:120])
                    last_error = e
                continue

        err_msg = str(last_error)[:100] if last_error else "No API keys configured"
        raise RuntimeError(f"All AI providers failed. Last error: {err_msg}")


ai_router = AIRouter()
