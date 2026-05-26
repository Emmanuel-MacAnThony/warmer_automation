"""
Gmail OAuth token repository.
"""
import logging
from typing import Any, Optional

from backend.infra.db.pool import get_pool

logger = logging.getLogger(__name__)


async def upsert_gmail_token(
    email: str,
    access_token: str,
    refresh_token: Optional[str],
    token_expiry,
) -> None:
    """Insert or update a Gmail OAuth token row."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO gmail_tokens (email, access_token, refresh_token, token_expiry, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (email) DO UPDATE SET
                access_token  = EXCLUDED.access_token,
                refresh_token = COALESCE(EXCLUDED.refresh_token, gmail_tokens.refresh_token),
                token_expiry  = EXCLUDED.token_expiry,
                updated_at    = now()
            """,
            email, access_token, refresh_token, token_expiry,
        )


async def get_gmail_token(email: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Return the first (or named) Gmail token row, or None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if email:
            row = await conn.fetchrow(
                "SELECT * FROM gmail_tokens WHERE email=$1", email
            )
        else:
            row = await conn.fetchrow(
                "SELECT * FROM gmail_tokens ORDER BY updated_at DESC LIMIT 1"
            )
    if not row:
        return None
    d = dict(row)
    for k in ("created_at", "updated_at", "token_expiry"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


async def list_gmail_tokens() -> list[dict]:
    """Return all connected accounts ordered by most recently updated."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT email, token_expiry, updated_at FROM gmail_tokens ORDER BY updated_at DESC"
        )
    return [{"email": r["email"], "connected": True} for r in rows]


async def delete_gmail_token(email: str) -> bool:
    """Remove a Gmail token. Returns True if a row was deleted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM gmail_tokens WHERE email=$1", email
        )
    return result != "DELETE 0"
