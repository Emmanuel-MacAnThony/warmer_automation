"""
Cadence (multi-touch sequence) data access.

A sequence is a timed series of email steps for a (campaign, tier). Contacts are
enrolled, and the cadence scheduler advances each enrollment step by step.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backend.infra.db.pool import get_pool

logger = logging.getLogger(__name__)


# ── Sequences ──────────────────────────────────────────────────────────────

async def create_sequence(
    campaign_id: int,
    tier: str,
    name: str = "Sequence",
    sender_emails: Optional[list] = None,
    test_recipient: Optional[str] = None,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO sequences (campaign_id, tier, name, sender_emails, test_recipient)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            RETURNING id
            """,
            campaign_id, tier, name, json.dumps(sender_emails or []), test_recipient,
        )
    return row["id"]


async def add_sequence_step(sequence_id: int, step_number: int, delay_days: int, template_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO sequence_steps (sequence_id, step_number, delay_days, template_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (sequence_id, step_number)
            DO UPDATE SET delay_days = EXCLUDED.delay_days, template_id = EXCLUDED.template_id
            RETURNING id
            """,
            sequence_id, step_number, delay_days, template_id,
        )
    return row["id"]


async def get_sequence(sequence_id: int) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM sequences WHERE id=$1", sequence_id)
    return _sequence_row(row) if row else None


async def get_sequence_steps(sequence_id: int) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM sequence_steps WHERE sequence_id=$1 ORDER BY step_number",
            sequence_id,
        )
    return [dict(r) for r in rows]


async def list_sequences(campaign_id: int, tier: Optional[str] = None) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if tier:
            rows = await conn.fetch(
                "SELECT * FROM sequences WHERE campaign_id=$1 AND tier=$2 ORDER BY created_at DESC",
                campaign_id, tier,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM sequences WHERE campaign_id=$1 ORDER BY created_at DESC",
                campaign_id,
            )
    return [_sequence_row(r) for r in rows]


async def get_sequence_steps_detail(sequence_id: int) -> list[dict[str, Any]]:
    """Steps with their template subject + delay — for the monitoring view."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ss.step_number, ss.delay_days, ct.subject
            FROM sequence_steps ss
            JOIN campaign_templates ct ON ct.id = ss.template_id
            WHERE ss.sequence_id = $1
            ORDER BY ss.step_number
            """,
            sequence_id,
        )
    return [dict(r) for r in rows]


async def list_all_sequences_for_table(base_id: str, table_id: str) -> list[dict[str, Any]]:
    """All sequences across a base/table, newest first, with the campaign goal."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.*, oc.goal AS campaign_goal
            FROM sequences s
            JOIN outreach_campaigns oc ON oc.id = s.campaign_id
            WHERE oc.base_id = $1 AND oc.table_id = $2
            ORDER BY s.created_at DESC
            """,
            base_id, table_id,
        )
    return [_sequence_row(r) for r in rows]


async def set_sequence_status(sequence_id: int, status: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sequences SET status=$2, updated_at=now() WHERE id=$1",
            sequence_id, status,
        )


async def delete_sequence(sequence_id: int) -> bool:
    """Delete a sequence and its steps + enrollments (ON DELETE CASCADE)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM sequences WHERE id=$1", sequence_id)
    return result == "DELETE 1"


# ── Enrollment ─────────────────────────────────────────────────────────────

async def enroll_tier(sequence_id: int, campaign_id: int, tier: str, scope: str = "everyone") -> int:
    """
    Enroll a tier's contacts into the sequence. Step 1 is due immediately.
    scope='everyone' → all contacts in the tier (re-sequence even already-contacted).
    scope='unsent'   → only pending/later (not yet contacted).
    Idempotent — already-enrolled contacts skip. Returns count of new enrollments.
    """
    status_filter = "" if scope == "everyone" else "AND cc.status IN ('pending','later')"
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO sequence_enrollments (sequence_id, campaign_contact_id, current_step, next_send_at)
            SELECT $1, cc.id, 1, now()
            FROM campaign_contacts cc
            WHERE cc.campaign_id=$2 AND cc.tier=$3 {status_filter}
            ON CONFLICT (sequence_id, campaign_contact_id) DO NOTHING
            """,
            sequence_id, campaign_id, tier,
        )
    # result like "INSERT 0 N"
    try:
        return int(result.split()[-1])
    except Exception:
        return 0


async def get_due_enrollments(limit: int = 200) -> list[dict[str, Any]]:
    """
    Scheduler hot query: atomically *claim* active enrollments whose next step is
    due, in active sequences, then return the contact + sequence data to send them.

    The claim leases each row by pushing next_send_at 15 minutes into the future in
    a single locked statement (FOR UPDATE SKIP LOCKED). This makes it safe to run
    more than one scheduler against the same database (e.g. local + prod sharing one
    Neon DB): two workers can never grab the same enrollment, so no contact is
    emailed twice. A crashed worker's lease simply expires and the row is retried.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        claimed = await conn.fetch(
            """
            UPDATE sequence_enrollments
            SET next_send_at = now() + interval '15 minutes'
            WHERE id IN (
                SELECT se.id
                FROM sequence_enrollments se
                JOIN sequences s ON s.id = se.sequence_id
                WHERE se.status = 'active'
                  AND se.next_send_at <= now()
                  AND s.status = 'active'
                ORDER BY se.next_send_at
                LIMIT $1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id
            """,
            limit,
        )
        if not claimed:
            return []
        ids = [r["id"] for r in claimed]
        rows = await conn.fetch(
            """
            SELECT se.id              AS enrollment_id,
                   se.sequence_id,
                   se.current_step,
                   se.campaign_contact_id,
                   cc.contact_snapshot,
                   cc.score_breakdown,
                   cc.warm_path_data,
                   cc.tier,
                   s.campaign_id,
                   s.sender_emails,
                   s.test_recipient
            FROM sequence_enrollments se
            JOIN campaign_contacts cc ON cc.id = se.campaign_contact_id
            JOIN sequences s          ON s.id  = se.sequence_id
            WHERE se.id = ANY($1::int[])
            ORDER BY se.next_send_at
            """,
            ids,
        )
    return [_due_row(r) for r in rows]


async def get_enrollments_awaiting_reply(limit: int = 100) -> list[dict[str, Any]]:
    """
    Active enrollments that have sent at least one email (have a thread) — candidates
    for reply detection. Joined with the sequence's sender account.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT se.id AS enrollment_id, se.last_thread_id, se.campaign_contact_id,
                   s.id AS sequence_id, s.sender_emails
            FROM sequence_enrollments se
            JOIN sequences s ON s.id = se.sequence_id
            WHERE se.status = 'active'
              AND se.last_thread_id IS NOT NULL
              AND s.status = 'active'
            ORDER BY se.last_reply_check_at ASC NULLS FIRST, se.updated_at
            LIMIT $1
            """,
            limit,
        )
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("sender_emails"), str):
            d["sender_emails"] = json.loads(d["sender_emails"])
        out.append(d)
    return out


async def mark_reply_checked(enrollment_ids: list[int]) -> None:
    """Stamp last_reply_check_at so these rotate to the back of the reply-poll queue."""
    if not enrollment_ids:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sequence_enrollments SET last_reply_check_at = now() WHERE id = ANY($1::int[])",
            enrollment_ids,
        )


async def advance_enrollment(
    enrollment_id: int,
    next_step: int,
    delay_days: int,
    message_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> None:
    """Move an enrollment to its next step, scheduled delay_days out."""
    next_send_at = datetime.now(timezone.utc) + timedelta(days=delay_days)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE sequence_enrollments
            SET current_step = $2, next_send_at = $3, sent_count = sent_count + 1,
                last_message_id = COALESCE($4, last_message_id),
                last_thread_id  = COALESCE($5, last_thread_id),
                updated_at = now()
            WHERE id = $1
            """,
            enrollment_id, next_step, next_send_at, message_id, thread_id,
        )


async def finish_enrollment(enrollment_id: int, status: str = "completed",
                            message_id: Optional[str] = None, thread_id: Optional[str] = None) -> None:
    """Terminal state: completed | replied | stopped | bounced."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE sequence_enrollments
            SET status = $2, sent_count = sent_count + CASE WHEN $2='completed' THEN 1 ELSE 0 END,
                last_message_id = COALESCE($3, last_message_id),
                last_thread_id  = COALESCE($4, last_thread_id),
                updated_at = now()
            WHERE id = $1
            """,
            enrollment_id, status, message_id, thread_id,
        )


async def get_replied_contacts(sequence_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Contacts who replied to this sequence — the hot leads. Newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cc.contact_snapshot, se.updated_at
            FROM sequence_enrollments se
            JOIN campaign_contacts cc ON cc.id = se.campaign_contact_id
            WHERE se.sequence_id = $1 AND se.status = 'replied'
            ORDER BY se.updated_at DESC
            LIMIT $2
            """,
            sequence_id, limit,
        )
    out = []
    for r in rows:
        snap = r["contact_snapshot"]
        if isinstance(snap, str):
            snap = json.loads(snap)
        snap = snap or {}
        out.append({
            "name": snap.get("name") or "Unknown",
            "email": snap.get("email") or "",
            "title": snap.get("title") or "",
            "company": snap.get("company") or "",
            "replied_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        })
    return out


async def get_sequence_stats(sequence_id: int) -> dict[str, Any]:
    """Counts by enrollment status + current step — powers the monitoring view."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        status_rows = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM sequence_enrollments WHERE sequence_id=$1 GROUP BY status",
            sequence_id,
        )
        step_rows = await conn.fetch(
            """
            SELECT current_step, COUNT(*) AS n, MIN(next_send_at) AS next_at
            FROM sequence_enrollments WHERE sequence_id=$1 AND status='active'
            GROUP BY current_step ORDER BY current_step
            """,
            sequence_id,
        )
    by_status = {r["status"]: r["n"] for r in status_rows}
    next_dt = [r["next_at"] for r in step_rows if r["next_at"] is not None]
    return {
        "total":     sum(by_status.values()),
        "active":    by_status.get("active", 0),
        "replied":   by_status.get("replied", 0),
        "completed": by_status.get("completed", 0),
        "stopped":   by_status.get("stopped", 0),
        "bounced":   by_status.get("bounced", 0),
        "by_step":   {r["current_step"]: r["n"] for r in step_rows},
        "next_by_step": {
            r["current_step"]: r["next_at"].isoformat()
            for r in step_rows if r["next_at"] is not None
        },
        "next_send_at": min(next_dt).isoformat() if next_dt else None,
    }


# ── Row parsers ──────────────────────────────────────────────────────────────

def _sequence_row(row) -> dict[str, Any]:
    d = dict(row)
    if isinstance(d.get("sender_emails"), str):
        d["sender_emails"] = json.loads(d["sender_emails"])
    for k in ("created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def _due_row(row) -> dict[str, Any]:
    d = dict(row)
    for k in ("contact_snapshot", "score_breakdown", "warm_path_data", "sender_emails"):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d
