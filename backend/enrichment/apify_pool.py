"""
Apify Token Pool — shared rate-limiter for all concurrent jobs.

Design:
- One semaphore per token, capacity = concurrency_per_token
- Round-robin assignment so load spreads evenly across tokens
- `async with pool.get_token() as token` — blocks if all slots for that token are busy
- Singleton via get_pool() — all jobs in the process share the same instance
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from backend.config import Config

logger = logging.getLogger(__name__)


class ApifyTokenPool:
    """
    Round-robin token pool with per-token concurrency limits.
    Total capacity = len(tokens) × concurrency_per_token.
    """

    def __init__(self, tokens: List[str], concurrency_per_token: int):
        if not tokens:
            raise ValueError("ApifyTokenPool requires at least one token")
        self._tokens = tokens
        self._concurrency = concurrency_per_token
        self._semaphores = [asyncio.Semaphore(concurrency_per_token) for _ in tokens]
        self._counter = 0
        self._lock = asyncio.Lock()
        logger.info(
            f"ApifyTokenPool ready: {len(tokens)} token(s) × "
            f"{concurrency_per_token} concurrency = "
            f"{len(tokens) * concurrency_per_token} total Apify slots"
        )

    @asynccontextmanager
    async def get_token(self):
        """
        Acquire a token slot (round-robin). Blocks if that token is at capacity.
        Yields the raw API token string for use with ApifyClient(token).
        """
        async with self._lock:
            idx = self._counter % len(self._tokens)
            self._counter += 1

        async with self._semaphores[idx]:
            yield self._tokens[idx]

    @property
    def capacity(self) -> int:
        """Total simultaneous Apify runs allowed across all tokens."""
        return len(self._tokens) * self._concurrency


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_pool: Optional[ApifyTokenPool] = None


def get_pool() -> ApifyTokenPool:
    """
    Return the shared pool. Creates it on first call using Config.
    Falls back to APIFY_API_TOKEN if APIFY_TOKENS is not set.
    """
    global _pool
    if _pool is None:
        _pool = _build_pool()
    return _pool


def _build_pool() -> ApifyTokenPool:
    tokens = Config.APIFY_TOKENS
    if not tokens and Config.APIFY_API_TOKEN:
        tokens = [Config.APIFY_API_TOKEN]
    if not tokens:
        raise RuntimeError(
            "No Apify tokens configured. "
            "Set APIFY_TOKENS or APIFY_API_TOKEN in .env"
        )
    return ApifyTokenPool(tokens, Config.APIFY_CONCURRENCY_PER_TOKEN)
