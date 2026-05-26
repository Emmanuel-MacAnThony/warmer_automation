"""
asyncpg connection pool — shared by all repo modules.
"""
import logging
from typing import Optional

import asyncpg
from backend.config import Config

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def _validate_connection(conn) -> None:
    await conn.execute("SELECT 1")


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            Config.DATABASE_URL,
            min_size=2,
            max_size=20,
            max_inactive_connection_lifetime=300,
            statement_cache_size=0,  # no cached plans — prevents stale-plan errors after migrations
            command_timeout=30,      # individual queries timeout after 30 s
            setup=_validate_connection,
        )
        logger.info("DB pool created")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
