"""
AI Router — selects local llama.cpp or cloud Anthropic based on availability.
Exposes a unified async streaming interface.
"""
import json
from typing import AsyncIterator

import httpx

from ..config import settings


class LocalAdapter:
    """Calls llama-server (llama.cpp) OpenAI-compatible endpoint."""

    async def is_available(self) -> bool:
        if not settings.llama_enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                r = await client.get(f"{settings.llama_server_url}/health")
                return r.status_code == 200
        except Exception:
            return False

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 512,
    ) -> AsyncIterator[str]:
        payload = {
            "model": "local",
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{settings.llama_server_url}/v1/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)
                        token = chunk["choices"][0]["delta"].get("content", "")
                        if token:
                            yield token
                    except (json.JSONDecodeError, KeyError):
                        continue


class AnthropicAdapter:
    """Calls Anthropic claude-3-5-sonnet with streaming."""

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 600,
    ) -> AsyncIterator[str]:
        if not settings.anthropic_api_key:
            yield "AI advisor requires an API key. Set ANTHROPIC_API_KEY in your .env file."
            return

        payload = {
            "model": "claude-3-5-sonnet-latest",
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data in ("[DONE]", ""):
                        continue
                    try:
                        event = json.loads(data)
                        if event.get("type") == "content_block_delta":
                            yield event["delta"].get("text", "")
                    except (json.JSONDecodeError, KeyError):
                        continue


class AIRouter:
    """Routes AI requests: local llama.cpp first, Anthropic fallback."""

    def __init__(self):
        self.local = LocalAdapter()
        self.cloud = AnthropicAdapter()

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 512,
        prefer_local: bool = True,
    ) -> AsyncIterator[str]:
        if prefer_local and await self.local.is_available():
            try:
                async for token in self.local.stream(system, messages, max_tokens):
                    yield token
                return
            except Exception:
                pass  # Fall through to cloud

        async for token in self.cloud.stream(system, messages, max_tokens):
            yield token


ai_router = AIRouter()
