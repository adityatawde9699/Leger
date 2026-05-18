"""
AI Router — streams responses from a fallback chain of free-tier AI providers:
Groq -> Cerebras -> Gemini -> OpenRouter.
"""

import os
from collections.abc import AsyncIterator
import logging

from ..config import settings

logger = logging.getLogger("ledger.ai_router")

class GroqAdapter:
    """Calls Groq API using official SDK."""
    async def is_available(self) -> bool:
        return bool(settings.groq_api_key)

    async def stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=settings.groq_api_key)
        
        # Groq expects system message as first message
        formatted_messages = [{"role": "system", "content": system}] + messages
        
        stream = await client.chat.completions.create(
            messages=formatted_messages,
            model="llama-3.1-8b-instant",
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

class CerebrasAdapter:
    """Calls Cerebras API using OpenAI compatible SDK."""
    async def is_available(self) -> bool:
        return bool(settings.cerebras_api_key)

    async def stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            base_url="https://api.cerebras.ai/v1",
            api_key=settings.cerebras_api_key
        )
        
        formatted_messages = [{"role": "system", "content": system}] + messages
        
        stream = await client.chat.completions.create(
            messages=formatted_messages,
            model="llama-3.3-70b",
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

class GeminiAdapter:
    """Calls Google Gemini API."""
    async def is_available(self) -> bool:
        return bool(settings.gemini_api_key)

    async def stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        
        model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=system)
        
        # Convert messages to Gemini format
        formatted_messages = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            formatted_messages.append({"role": role, "parts": [msg["content"]]})
            
        response = await model.generate_content_async(
            formatted_messages,
            stream=True,
            generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens)
        )
        
        async for chunk in response:
            if chunk.text:
                yield chunk.text

class OpenRouterAdapter:
    """Calls OpenRouter API using OpenAI compatible SDK."""
    async def is_available(self) -> bool:
        return bool(settings.openrouter_api_key)

    async def stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key
        )
        
        formatted_messages = [{"role": "system", "content": system}] + messages
        
        # Using a free model on OpenRouter, e.g., meta-llama/llama-3-8b-instruct:free
        stream = await client.chat.completions.create(
            messages=formatted_messages,
            model="meta-llama/llama-3-8b-instruct:free", 
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class AIRouter:
    """Routes AI requests: Groq -> Cerebras -> Gemini -> OpenRouter."""

    def __init__(self):
        self.adapters = [
            ("Groq", GroqAdapter()),
            ("Cerebras", CerebrasAdapter()),
            ("Gemini", GeminiAdapter()),
            ("OpenRouter", OpenRouterAdapter())
        ]

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 512,
        prefer_local: bool = False, # Kept for signature compatibility
    ) -> AsyncIterator[str]:
        
        last_error = None
        for name, adapter in self.adapters:
            if await adapter.is_available():
                try:
                    logger.debug(f"Attempting stream with {name}")
                    
                    # Try to start stream and get first token
                    iterator = adapter.stream(system, messages, max_tokens)
                    try:
                        first_token = await anext(iterator)
                    except StopAsyncIteration:
                        first_token = ""
                    
                    yield first_token
                    
                    # If we got here, connection succeeded, yield the rest
                    async for token in iterator:
                        yield token
                        
                    return # Successfully completed the stream, stop fallback
                    
                except Exception as e:
                    logger.warning(f"{name} adapter failed: {e}")
                    last_error = e
                    continue

        if last_error:
            yield f"\\n[AI Service Error: All providers failed. Last error: {str(last_error)}]"
        else:
            yield "\\n[AI Service Error: No API keys configured.]"

ai_router = AIRouter()
