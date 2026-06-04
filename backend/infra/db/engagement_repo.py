"""
Engagement event repository — currently powers click tracking (Phase B).

Schema sits in email_events with both a sequence_enrollment_id and a
batch_job_id slot so the same audit table works for both send paths and
future per-source aggregations stay cheap (indexed).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from backend.infra.db.client import get_pool

logger = logging.getLogger(__name__)


async def record_click(
    *,
    sequence_enrollment_id: Optional[int],
    batch_job_id: Optional[int],
    campaign_contact_id: Optional[int],
    link_url: Optional[str],
    user_agent: Optional[str],
    ip: Optional[str],
) -> None:
    """Persist one click event. Best-effort: any failure logs and returns."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO email_events
                (sequence_enrollment_id, batch_job_id, campaign_contact_id,
                 event_type, link_url, user_agent, ip)
            VALUES ($1, $2, $3, 'click', $4, $5, $6)
            """,
            sequence_enrollment_id, batch_job_id, campaign_contact_id,
            link_url, (user_agent or "")[:512], (ip or "")[:64],
        )


async def count_clicks_for_sequence(sequence_id: int) -> int:
    """Total click events recorded against any enrollment in this sequence."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS n
            FROM email_events ev
            JOIN sequence_enrollments se ON se.id = ev.sequence_enrollment_id
            WHERE se.sequence_id = $1 AND ev.event_type = 'click'
            """,
            sequence_id,
        )
    return int(row["n"]) if row else 0


async def count_unique_clickers_for_sequence(sequence_id: int) -> int:
    """Distinct contacts who clicked anything in this sequence — the headline number."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(DISTINCT ev.campaign_contact_id) AS n
            FROM email_events ev
            JOIN sequence_enrollments se ON se.id = ev.sequence_enrollment_id
            WHERE se.sequence_id = $1
              AND ev.event_type = 'click'
              AND ev.campaign_contact_id IS NOT NULL
            """,
            sequence_id,
        )
    return int(row["n"]) if row else 0


async def list_click_contacts_for_sequence(sequence_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """
    Contacts who clicked something in this sequence — with their LAST click's
    URL + timestamp, plus their click count. Drives the SequenceCard "who
    clicked" drawer. Ordered by most recent click.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cc.contact_snapshot,
                   COUNT(*)                  AS click_count,
                   MAX(ev.occurred_at)       AS last_click_at,
                   (ARRAY_AGG(ev.link_url ORDER BY ev.occurred_at DESC))[1] AS last_link_url
            FROM email_events ev
            JOIN sequence_enrollments se ON se.id = ev.sequence_enrollment_id
            JOIN campaign_contacts cc     ON cc.id = ev.campaign_contact_id
            WHERE se.sequence_id = $1 AND ev.event_type = 'click'
            GROUP BY cc.id, cc.contact_snapshot
            ORDER BY last_click_at DESC
            LIMIT $2
            """,
            sequence_id, limit,
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        snap = r["contact_snapshot"]
        if isinstance(snap, str):
            snap = json.loads(snap)
        snap = snap or {}
        out.append({
            "name":         snap.get("name") or "Unknown",
            "email":        snap.get("email") or "",
            "title":        snap.get("title") or "",
            "company":      snap.get("company") or "",
            "click_count":  int(r["click_count"]),
            "last_link_url": r["last_link_url"],
            "last_click_at": r["last_click_at"].isoformat() if r["last_click_at"] else None,
        })
    return out
