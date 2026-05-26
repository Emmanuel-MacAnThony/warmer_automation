"""
OpenAI implementation of LLMProvider.

This is the only file in the codebase that imports openai/langchain_openai.
Domain code (analyzers, template generators) receives an LLMProvider and
never needs to know which SDK is underneath.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """
    Concrete LLMProvider backed by the OpenAI API.

    Exposes:
      - complete()      — single non-streaming completion
      - stream()        — token-by-token streaming
      - embed()         — single embedding vector
      - embed_batch()   — batch embedding (one API call)
      - raw_client      — AsyncOpenAI instance for advanced features
                          (tool calling, JSON mode, structured outputs)
      - sync_client     — Sync OpenAI instance for thread-pool execution contexts
    """

    def __init__(self, api_key: str) -> None:
        from openai import AsyncOpenAI, OpenAI
        self._async_client = AsyncOpenAI(api_key=api_key)
        self._sync_client  = OpenAI(api_key=api_key)

    async def complete(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        kwargs = dict(model=model, messages=messages, temperature=temperature)
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        resp = await self._async_client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def stream(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        s = await self._async_client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, stream=True
        )
        async for chunk in s:
            token = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if token:
                yield token

    async def embed(self, text: str, *, model: str) -> list[float]:
        resp = await self._async_client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding

    async def embed_batch(self, texts: list[str], *, model: str) -> list[list[float]]:
        resp = await self._async_client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in resp.data]

    @property
    def raw_client(self):
        """Raw AsyncOpenAI client — for tool calling, JSON mode, structured outputs."""
        return self._async_client

    @property
    def sync_client(self):
        """Sync OpenAI client — for use inside thread-pool executors."""
        return self._sync_client
