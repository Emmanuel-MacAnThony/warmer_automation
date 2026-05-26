"""
LLM provider factory — process-wide singleton.

Usage:
    from backend.infra.llm.factory import get_llm_provider
    provider = get_llm_provider()
    result = await provider.complete(messages, model=Config.OPENAI_MODEL)
"""
from __future__ import annotations

from typing import Optional

from backend.config import Config
from backend.infra.llm.openai_provider import OpenAIProvider

_provider: Optional[OpenAIProvider] = None


def get_llm_provider() -> OpenAIProvider:
    """Return the process-wide OpenAIProvider singleton, creating it on first call."""
    global _provider
    if _provider is None:
        _provider = OpenAIProvider(api_key=Config.OPENAI_API_KEY)
    return _provider
