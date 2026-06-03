"""
Suppression + bounce-event repository.

Two tables, two responsibilities:
  email_suppressions  → the canonical dead-list (what the send-side filter reads).
                        One row per email, mutated as new bounces accrue.
  email_bounces       → audit log of every bounce *event* (one row per detection).
                        Keeps history, idempotency (dsn_message_id UNIQUE), and the
                        link back to whichever sequence enrollment or batch job
                        produced the dead send.

The send-side filter is a single SQL clause used from both enroll_tier
(sequences) and the batch contact-selection query:
    AND LOWER(cc.contact_snapshot->>'email') NOT IN (
        SELECT email FROM email_suppressions
        WHERE retry_after IS NULL OR retry_after < now()
    )
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from backend.infra.db.client import get_pool

logger = logging.getLogger(__name__)


def _norm(email: str) -> str:
    return (email or "").strip().lower()


# ── Suppression list (the active dead-list) ──────────────────────────────────


async def upsert_suppression(
    email: str,
    reason: str,
    smtp_status: Optional[str] = None,
    reason_text: Optional[str] = None,
    retry_after: Optional[datetime] = None,
) -> None:
    """
    Add or refresh an email in the suppression list.

    Idempotent: same email called twice just bumps last_seen_at + last_smtp_status.
    retry_after=None means "permanent" (the send filter excludes the email
    forever); a future timestamp means "soft bounce, retry after this moment".
    """
    email = _norm(email)
    if not email:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO email_suppressions
                (email, reason, retry_after, last_smtp_status, last_reason_text)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (email) DO UPDATE
              SET last_seen_at     = now(),
                  reason           = EXCLUDED.reason,
                  retry_after      = EXCLUDED.retry_after,
                  last_smtp_status = COALESCE(EXCLUDED.last_smtp_status, email_suppressions.last_smtp_status),
                  last_reason_text = COALESCE(EXCLUDED.last_reason_text, email_suppressions.last_reason_text)
            """,
            email, reason, retry_after, smtp_status, reason_text,
        )


async def unsuppress(email: str) -> bool:
    """Manual removal — for false positives. Returns True if a row was deleted."""
    email = _norm(email)
    if not email:
        return False
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM email_suppressions WHERE email=$1", email,
        )
    return result.endswith(" 1")


async def is_suppressed(email: str) -> bool:
    """
    Live lookup — rarely needed because the canonical guard lives in the
    send-side SQL filter. Useful for in-app checks (e.g. UI warnings).
    """
    email = _norm(email)
    if not email:
        return False
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1 FROM email_suppressions
            WHERE email=$1 AND (retry_after IS NULL OR retry_after < now())
            """,
            email,
        )
    return row is not None


async def count_active_suppressions() -> int:
    """Total currently-suppressed addresses (excludes expired soft-bounce backoffs)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS n FROM email_suppressions
            WHERE retry_after IS NULL OR retry_after < now()
            """,
        )
    return int(row["n"]) if row else 0


async def list_suppressions(
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List view for the UI suppressions page. Newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if search:
            rows = await conn.fetch(
                """
                SELECT * FROM email_suppressions
                WHERE email ILIKE $1
                ORDER BY last_seen_at DESC
                LIMIT $2 OFFSET $3
                """,
                f"%{search.lower()}%", limit, offset,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM email_suppressions
                ORDER BY last_seen_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit, offset,
            )
    return [_suppression_row(r) for r in rows]


# ── Bounce event audit log ───────────────────────────────────────────────────


async def record_bounce(
    email: str,
    source: str,
    hard: bool,
    *,
    sequence_enrollment_id: Optional[int] = None,
    batch_job_id: Optional[int] = None,
    reason: Optional[str] = None,
    smtp_status: Optional[str] = None,
    source_message_id: Optional[str] = None,
    dsn_message_id: Optional[str] = None,
) -> bool:
    """
    Insert one bounce event into the audit log.

    Returns True if a new row was inserted, False if dsn_message_id already
    existed (idempotency — the DSN poller can re-process the same message
    safely after a restart).
    """
    email = _norm(email)
    if not email:
        return False
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO email_bounces
                (email, source, sequence_enrollment_id, batch_job_id,
                 hard, reason, smtp_status, source_message_id, dsn_message_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (dsn_message_id) DO NOTHING
            """,
            email, source, sequence_enrollment_id, batch_job_id,
            hard, reason, smtp_status, source_message_id, dsn_message_id,
        )
    return result.endswith(" 1")


async def list_bounces_for_email(email: str, limit: int = 50) -> list[dict[str, Any]]:
    """Audit history for a single email — powers the suppressions-page expand row."""
    email = _norm(email)
    if not email:
        return []
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM email_bounces
            WHERE email = $1
            ORDER BY detected_at DESC
            LIMIT $2
            """,
            email, limit,
        )
    return [_bounce_row(r) for r in rows]


async def count_bounces_for_sequence(sequence_id: int) -> int:
    """How many bounces have been recorded against this sequence's enrollments."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS n
            FROM email_bounces eb
            JOIN sequence_enrollments se ON se.id = eb.sequence_enrollment_id
            WHERE se.sequence_id = $1
            """,
            sequence_id,
        )
    return int(row["n"]) if row else 0


async def count_bounces_for_batch_job(batch_job_id: int) -> int:
    """How many bounces have been recorded against this batch job."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM email_bounces WHERE batch_job_id=$1",
            batch_job_id,
        )
    return int(row["n"]) if row else 0


# ── Row parsers ──────────────────────────────────────────────────────────────


def _suppression_row(row) -> dict[str, Any]:
    d = dict(row)
    for k in ("first_seen_at", "last_seen_at", "retry_after"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def _bounce_row(row) -> dict[str, Any]:
    d = dict(row)
    if d.get("detected_at"):
        d["detected_at"] = d["detected_at"].isoformat()
    return d
