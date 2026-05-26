"""
LLM infrastructure boundary.

LLMProvider is the Protocol that domain code depends on — it defines what
the LLM boundary can do without importing any specific SDK. The concrete
implementation (OpenAIProvider) and the process-wide singleton (get_llm_provider)
live alongside it here so the contract and its fulfilment are co-located.
"""
from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal contract for completion, streaming, and embedding calls."""

    async def complete(
        self, messages: list[dict], *, model: str, temperature: float = 0.7
    ) -> str: ...

    async def stream(
        self, messages: list[dict], *, model: str, temperature: float = 0.7
    ) -> AsyncIterator[str]: ...

    async def embed(self, text: str, *, model: str) -> list[float]: ...
