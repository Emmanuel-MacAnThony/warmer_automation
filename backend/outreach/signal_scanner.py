"""
Signal scanner for batch email mode.

Single aggregate SQL query — never loads contact rows into Python.
Handles 5,000+ contacts in one round-trip.
"""
import logging
from typing import Any, Dict
from backend.infra.db.client import get_pool

logger = logging.getLogger(__name__)

SIGNAL_KEYS = [
    'giving', 'wealth', 'capacity',
    'trajectory', 'topics', 'personality', 'engagement',
]
CONTACT_KEYS = ['name', 'company', 'title', 'email']


def _sig_sql(key: str) -> str:
    """COUNT expression for a signals sub-key."""
    return (
        f"SUM(CASE WHEN contact_snapshot->'signals'->>'{key}' IS NOT NULL "
        f"         AND  contact_snapshot->'signals'->>'{key}' <> '' "
        f"    THEN 1 ELSE 0 END) AS sig_{key}"
    )


def _fld_sql(key: str) -> str:
    """COUNT expression for a top-level contact_snapshot key."""
    return (
        f"SUM(CASE WHEN contact_snapshot->>'{key}' IS NOT NULL "
        f"         AND  contact_snapshot->>'{key}' <> '' "
        f"    THEN 1 ELSE 0 END) AS fld_{key}"
    )


async def scan_tier_signals(campaign_id: int, tier: str) -> Dict[str, Any]:
    """
    Return per-variable coverage for all pending/later contacts in a tier.

    Uses a single aggregate SQL query with CASE expressions — no Python loop,
    no row fetching. Safe at any tier size.

    Returns:
      {
        total: int,
        signals: { giving: {count, pct}, ... },
        contact_fields: { name: {count, pct}, ... },
      }
    """
    pool = await get_pool()

    cols = (
        ["COUNT(*) AS total"]
        + [_sig_sql(k) for k in SIGNAL_KEYS]
        + [_fld_sql(k) for k in CONTACT_KEYS]
    )
    sql = f"""
        SELECT {', '.join(cols)}
        FROM   campaign_contacts
        WHERE  campaign_id = $1
          AND  tier        = $2
          AND  status IN ('pending', 'later')
    """

    logger.debug("signal_scanner SQL:\n%s", sql)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, campaign_id, tier)

    if row is None:
        logger.warning("signal_scanner: no row returned for campaign=%s tier=%s", campaign_id, tier)
        total = 0
    else:
        total = int(row['total'] or 0)

    denom = total or 1

    def _stat(raw) -> Dict[str, Any]:
        n = int(raw or 0)
        return {'count': n, 'pct': round(n / denom * 100, 1)}

    return {
        'total': total,
        'signals':        {k: _stat(row[f'sig_{k}'] if row else 0) for k in SIGNAL_KEYS},
        'contact_fields': {k: _stat(row[f'fld_{k}'] if row else 0) for k in CONTACT_KEYS},
    }
